"""Histórico de emissão por empresa: um registro por nota transmitida (sucesso ou pendência),
para a tela mostrar o que já foi enviado e para não reenviar o mesmo lançamento duas vezes.
Fica em `%APPDATA%\\AdgeGroup\\NFDownloader\\emissoes\\<id-da-empresa>.json` (mesma pasta de dados
das empresas, ver `store.pasta_dados`), separado do `empresas.json` para não crescer sem limite."""
from __future__ import annotations

import json
from pathlib import Path


def _arquivo(pasta_dados: Path, empresa_id: str) -> Path:
    pasta = Path(pasta_dados) / "emissoes"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta / f"{empresa_id}.json"


def listar(pasta_dados: Path, empresa_id: str) -> list:
    arq = _arquivo(pasta_dados, empresa_id)
    if not arq.exists():
        return []
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except ValueError:
        return []


def registrar(pasta_dados: Path, empresa_id: str, registro: dict) -> None:
    """`registro` esperado: {lancamento_id, competencia, tomador_nome, tomador_documento, valor,
    status ("emitida"|"pendente"), chave, numero, erro, data_hora}."""
    arq = _arquivo(pasta_dados, empresa_id)
    registros = listar(pasta_dados, empresa_id)
    registros.append(registro)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(arq)


def ja_emitido(pasta_dados: Path, empresa_id: str, lancamento_id: str) -> bool:
    return any(r.get("lancamento_id") == lancamento_id and r.get("status") == "emitida"
              for r in listar(pasta_dados, empresa_id))


def proximo_numero_dps(pasta_dados: Path, empresa_id: str, serie: str = "1") -> int:
    """Próximo nDPS da série: maior número já usado (emitido ou pendente, para não colidir com
    uma transmissão em andamento) + 1. Números nunca são reaproveitados, mesmo que uma nota
    pendente seja depois abandonada — mais seguro do que arriscar duplicidade de nDPS."""
    usados = [int(r["numero"]) for r in listar(pasta_dados, empresa_id)
              if r.get("serie", "1") == serie and str(r.get("numero", "")).isdigit()]
    return max(usados, default=0) + 1
