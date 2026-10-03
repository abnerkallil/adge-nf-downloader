"""Controle local das consultas de NF-e: o último NSU confirmado, o horário em que a SEFAZ libera outra consulta e as NF-e
de outros meses que vieram no mesmo lote.

Por que existe: a SEFAZ entrega as NF-e por NSU (sequencial), guarda só alguns meses e limita as consultas (cerca de 1 hora
entre consultas sem novidade). O limite é da própria SEFAZ, não do programa.

Regra da 1.7.4: o NSU só avança (e os XMLs só entram aqui) quando a pessoa SALVA as notas numa pasta. Quem consulta e sai sem
salvar não perde nada: a próxima consulta recomeça do mesmo NSU. Já o horário de bloqueio da SEFAZ é gravado na hora da
consulta, porque ele vale mesmo que as notas não tenham sido salvas.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from pathlib import Path

from . import core

SCHEMAS = {"proc": "procNFe_v4.00.xsd", "res": "resNFe_v1.01.xsd", "evento": "procEventoNFe_v1.00.xsd",
           "resevento": "resEvento_v1.01.xsd", "outro": ""}


def formatar_espera(td: dt.timedelta) -> str:
    s = max(0, int(td.total_seconds()))
    h, resto = divmod(s, 3600)
    m, seg = divmod(resto, 60)
    if h:
        return f"{h} h {m:02d} min"
    if m:
        return f"{m} min {seg:02d} s"
    return f"{seg} s"


class HistoricoNFe:
    def __init__(self, emp: dict, base=None, agora=dt.datetime.now):
        from .store import pasta_dados
        self.emp, self.agora = emp, agora
        cnpj = re.sub(r"\D", "", emp.get("cnpj", ""))
        self.base = Path(base) if base else pasta_dados() / "Historico de consultas"
        self.pasta = self.base / f"{core.limpar_nome(emp.get('nome', '') or 'Empresa')[:60].strip()} - {cnpj}"
        self.arquivo = self.pasta / "estado.json"
        self.estado = self._ler()

    # ------------------------------------------------------------------ estado
    @staticmethod
    def _padrao() -> dict:
        return {"ult_nsu": 0, "max_nsu": 0, "bloqueio_ate": None, "ultima_consulta": None,
                "pasta_xml": None, "periodo": None, "ciencia": {}}

    def _ler(self) -> dict:
        e = self._padrao()
        try:
            e.update(json.loads(self.arquivo.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        e.pop("decisao", None)              # campo das versões 1.6 a 1.7.3 (histórico "manter/descartar"), não existe mais
        return e

    def salvar_estado(self):
        self.pasta.mkdir(parents=True, exist_ok=True)
        tmp = self.arquivo.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.estado, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.arquivo)

    @property
    def pasta_docs(self) -> Path:
        return Path(self.estado["pasta_xml"]) if self.estado.get("pasta_xml") else self.pasta / "xml"

    # ------------------------------------------------------------------ documentos
    @staticmethod
    def _nome(d: dict) -> str:
        nsu, tipo = int(d.get("nsu") or 0), d.get("tipo") or "outro"
        if nsu > 0:
            return f"{nsu:015d}-{tipo}.xml"
        return f"avulso-{hashlib.sha1(d['xml'].encode('utf-8')).hexdigest()[:16]}-{tipo}.xml"

    def salvar_docs(self, docs: list) -> int:
        """Grava os documentos novos (os que já existem ficam como estão). Devolve quantos foram gravados."""
        if not docs:
            return 0
        pasta = self.pasta_docs
        pasta.mkdir(parents=True, exist_ok=True)
        n = 0
        for d in docs:
            if not d.get("xml"):
                continue
            alvo = pasta / self._nome(d)
            if not alvo.exists():
                alvo.write_text(d["xml"], encoding="utf-8")
                n += 1
        return n

    def carregar_docs(self) -> list:
        pasta = self.pasta_docs
        if not pasta.is_dir():
            return []
        docs = []
        for f in sorted(pasta.glob("*.xml")):
            m = re.match(r"^(\d{15}|avulso-[0-9a-f]{16})-(\w+)\.xml$", f.name)
            if not m:
                continue
            tipo = m[2]
            try:
                xml = f.read_text(encoding="utf-8")
            except OSError:
                continue
            docs.append({"nsu": int(m[1]) if m[1].isdigit() else 0, "tipo": tipo, "schema": SCHEMAS.get(tipo, ""), "xml": xml})
        return docs

    def quantidade(self) -> int:
        pasta = self.pasta_docs
        return len(list(pasta.glob("*.xml"))) if pasta.is_dir() else 0

    # ------------------------------------------------------------------ consultas e bloqueio
    def registrar_bloqueio(self, max_nsu: int, bloqueado_ate, periodo=None):
        """Grava na hora da consulta o limite da SEFAZ (vale mesmo sem salvar as notas). NÃO mexe no último NSU."""
        self.estado.update({"max_nsu": int(max_nsu),
                            "bloqueio_ate": bloqueado_ate.isoformat(timespec="seconds") if bloqueado_ate else None,
                            "ultima_consulta": self.agora().isoformat(timespec="seconds")})
        if periodo:
            self.estado["periodo"] = [int(periodo[0]), int(periodo[1])]
        self.salvar_estado()

    def confirmar(self, docs: list, ult_nsu: int, max_nsu: int = None) -> int:
        """Chamado SÓ depois de as notas serem salvas numa pasta: guarda os XMLs deste lote (inclusive os de outros meses, que
        a SEFAZ não entrega de novo) e então avança o NSU. Os XMLs vêm antes do NSU: se algo falhar no meio, o NSU não anda."""
        n = self.salvar_docs(docs)
        self.estado["ult_nsu"] = max(int(self.estado.get("ult_nsu") or 0), int(ult_nsu))
        if max_nsu is not None:
            self.estado["max_nsu"] = max(int(self.estado.get("max_nsu") or 0), int(max_nsu))
        self.salvar_estado()
        return n

    def liberado_as(self):
        b = self.estado.get("bloqueio_ate")
        try:
            return dt.datetime.fromisoformat(b) if b else None
        except ValueError:
            return None

    def bloqueio_restante(self):
        """timedelta até a SEFAZ liberar outra consulta; None se já está liberada."""
        ate = self.liberado_as()
        if ate is None:
            return None
        resto = ate - self.agora()
        return resto if resto > dt.timedelta(0) else None

    def bloqueado(self) -> bool:
        return self.bloqueio_restante() is not None

    def texto_bloqueio(self) -> str:
        resto = self.bloqueio_restante()
        if resto is None:
            return "Consulta de NF-e liberada."
        return f"Consulta de NF-e bloqueada pela SEFAZ por mais {formatar_espera(resto)} (liberada às {self.liberado_as():%H:%M})."

    def periodo_texto(self) -> str:
        p = self.estado.get("periodo")
        return f"{core.mes_exibicao(p[1])} de {p[0]}" if p else "o último período consultado"

    # ------------------------------------------------------------------ ciência já enviada
    def ciencias(self) -> set:
        return set(self.estado.get("ciencia", {}))

    def marcar_ciencia(self, chaves):
        agora = self.agora().isoformat(timespec="seconds")
        for c in chaves:
            self.estado.setdefault("ciencia", {})[c] = agora
        self.salvar_estado()
