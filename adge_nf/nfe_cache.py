"""Histórico local das consultas de NF-e: o que a SEFAZ devolveu, o último NSU e o horário em que ela libera outra consulta.

Por que existe: a SEFAZ entrega as NF-e por NSU (sequencial), guarda só alguns meses e limita as consultas (cerca de 1 hora
entre consultas sem novidade). O limite é da própria SEFAZ, não do programa. Para o mês continuar disponível, o que chega é
guardado numa pasta do sistema (por empresa) em vez de ir direto para a pasta do cliente; a pasta do cliente só recebe os XMLs
quando a pessoa pede "Baixar XMLs".
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
from pathlib import Path

from . import core

SCHEMAS = {"proc": "procNFe_v4.00.xsd", "res": "resNFe_v1.01.xsd", "evento": "procEventoNFe_v1.00.xsd",
           "resevento": "resEvento_v1.01.xsd", "outro": ""}
# decisao: "nenhuma" (ainda não perguntou), "pendente" (fechou sem responder: guardado até a próxima consulta),
#          "manter" (a pessoa pediu para guardar) ou "descartar" (não guardar: o histórico é apagado)
DECISOES = ("nenhuma", "pendente", "manter", "descartar")


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
        return {"ult_nsu": 0, "max_nsu": 0, "bloqueio_ate": None, "ultima_consulta": None, "decisao": "nenhuma",
                "pasta_xml": None, "periodo": None, "ciencia": {}}

    def _ler(self) -> dict:
        e = self._padrao()
        try:
            e.update(json.loads(self.arquivo.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        if e["decisao"] not in DECISOES:
            e["decisao"] = "nenhuma"
        return e

    def salvar_estado(self):
        self.pasta.mkdir(parents=True, exist_ok=True)
        tmp = self.arquivo.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.estado, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.arquivo)

    @property
    def pasta_docs(self) -> Path:
        return Path(self.estado["pasta_xml"]) if self.estado.get("pasta_xml") else self.pasta / "xml"

    @property
    def pasta_padrao(self) -> bool:
        return not self.estado.get("pasta_xml")

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
    def registrar_consulta(self, ult_nsu: int, max_nsu: int, bloqueado_ate, periodo=None):
        self.estado.update({"ult_nsu": int(ult_nsu), "max_nsu": int(max_nsu),
                            "bloqueio_ate": bloqueado_ate.isoformat(timespec="seconds") if bloqueado_ate else None,
                            "ultima_consulta": self.agora().isoformat(timespec="seconds")})
        if periodo:
            self.estado["periodo"] = [int(periodo[0]), int(periodo[1])]
        self.salvar_estado()

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

    # ------------------------------------------------------------------ decisão da pessoa
    def periodo_texto(self) -> str:
        p = self.estado.get("periodo")
        return f"{core.mes_exibicao(p[1])} de {p[0]}" if p else "o último período consultado"

    def decidir(self, decisao: str, pasta=None):
        """manter: guarda (na pasta do sistema ou na escolhida). descartar: apaga o histórico e zera o NSU, para que a próxima
        consulta comece do início (dentro do que a SEFAZ ainda guarda). pendente: fechou sem responder, fica guardado."""
        if decisao == "descartar":
            self.apagar_docs()
            self.estado.update({"ult_nsu": 0, "max_nsu": 0, "ciencia": {}})
        elif decisao == "manter" and pasta:
            self.mudar_pasta(pasta)
        self.estado["decisao"] = decisao
        self.salvar_estado()

    def mudar_pasta(self, nova_base):
        """Leva o histórico para a pasta escolhida (cria uma subpasta com o nome da empresa)."""
        destino = Path(nova_base) / f"Historico NF-e - {self.pasta.name}"
        antigo = self.pasta_docs
        destino.mkdir(parents=True, exist_ok=True)
        if antigo.is_dir() and antigo.resolve() != destino.resolve():
            for f in antigo.glob("*.xml"):
                alvo = destino / f.name
                if not alvo.exists():
                    shutil.move(str(f), str(alvo))
                else:
                    f.unlink()
        self.estado["pasta_xml"] = str(destino)
        self.salvar_estado()

    def apagar_docs(self):
        pasta = self.pasta_docs
        if pasta.is_dir():
            for f in pasta.glob("*.xml"):
                try:
                    f.unlink()
                except OSError:
                    pass

    # ------------------------------------------------------------------ ciência já enviada
    def ciencias(self) -> set:
        return set(self.estado.get("ciencia", {}))

    def marcar_ciencia(self, chaves):
        agora = self.agora().isoformat(timespec="seconds")
        for c in chaves:
            self.estado.setdefault("ciencia", {})[c] = agora
        self.salvar_estado()
