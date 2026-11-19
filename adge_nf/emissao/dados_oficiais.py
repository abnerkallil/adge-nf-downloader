"""Dados oficiais para validação de CTN/NBS na tela de emissão (V2.0).

Fontes (lidas pela thread de pesquisa, 19/11/2026, não de memória):

- `dados/ctn_lista.json`: lista COMPLETA e oficial dos 338 CTN do Anexo B vigente
  (`anexo_b-nbs2-lista_servico_nacional-snnfse-v1-01-20260122.xlsx`). Usada para a busca
  de CTN e para bloquear código inexistente (regra de negócio E0310 do leiaute oficial).

- `dados/nbs_sugestoes.json`: NBS que aparecem no Anexo VIII (tabela de correlação
  Item×NBS×cClassTrib). NÃO é a lista oficial completa de NBS (essa não foi extraída
  nesta pesquisa) — serve só de sugestão para a busca, nunca para bloquear "NBS
  inexistente".

- `dados/alerta_regime_simples.json`: por item.subitem da LC 116 (4 dígitos), quais
  códigos de atividade do Simples Nacional (`cod_ativ_sn`, do Anexo VIII) costumam
  aparecer associados a ele — ex. "9" = Anexo III/V, "IMP" = atividade impeditiva ao
  Simples Nacional. A própria Receita Federal diz, na página oficial do Anexo VIII, que
  ele "NÃO HÁ REGRAS DE NEGÓCIO BASEADAS NESTE ANEXO NO AMBIENTE DO PILOTO RTC
  (PRODUÇÃO RESTRITA) NEM EM PRODUÇÃO" — então isso é só um ALERTA próprio do ADGE NF
  Downloader (apoiado numa tabela de referência da Receita), nunca uma rejeição do
  leiaute nacional.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

_PASTA_DADOS = Path(__file__).resolve().parent / "dados"


def _normalizar_busca(texto: str) -> str:
    """Minúsculas e sem acento, pra buscar "analise" e achar "análise"."""
    sem_acento = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).lower()


@lru_cache(maxsize=1)
def _ctn_lista() -> list[dict]:
    with open(_PASTA_DADOS / "ctn_lista.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _ctn_por_codigo() -> dict[str, dict]:
    return {r["cTribNac"]: r for r in _ctn_lista()}


@lru_cache(maxsize=1)
def _nbs_sugestoes() -> list[dict]:
    with open(_PASTA_DADOS / "nbs_sugestoes.json", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _alerta_regime() -> dict[str, list[dict]]:
    with open(_PASTA_DADOS / "alerta_regime_simples.json", encoding="utf-8") as f:
        return json.load(f)


def _so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def formatar_ctn(registro: dict) -> str:
    return f"{registro['codigo']} - {registro['descricao']}"


def listar_ctn() -> list[str]:
    """Todas as opções de CTN formatadas "código - descrição", na ordem oficial."""
    return [formatar_ctn(r) for r in _ctn_lista()]


def buscar_ctn(texto: str, limite: int = 30) -> list[str]:
    """Filtra CTN por código ou por palavra na descrição (busca tipo o portal, sem acento)."""
    alvo = _normalizar_busca(texto)
    if not alvo:
        return listar_ctn()[:limite]
    achados = [
        formatar_ctn(r) for r in _ctn_lista()
        if alvo in _normalizar_busca(r["codigo"]) or alvo in _normalizar_busca(r["descricao"])
    ]
    return achados[:limite]


def extrair_codigo_ctn(texto_formatado: str) -> str:
    """Tira o código ("99.01.01") do início do texto "código - descrição"."""
    return (texto_formatado or "").split(" - ", 1)[0].strip()


def ctn_existe(texto_ou_codigo: str) -> bool:
    """True se o CTN (código "99.01.01" ou os 6 dígitos) está na lista oficial do Anexo B.
    Texto vazio não é considerado erro de existência (é tratado como campo não preenchido)."""
    codigo = extrair_codigo_ctn(texto_ou_codigo)
    if not codigo:
        return True
    return _so_digitos(codigo) in _ctn_por_codigo()


def formatar_nbs(registro: dict) -> str:
    return f"{registro['nbs']} - {registro['descricao']}"


def buscar_nbs(texto: str, limite: int = 30) -> list[str]:
    """Sugestões de NBS (lista do Anexo VIII, não é a tabela oficial completa de NBS)."""
    alvo = _normalizar_busca(texto)
    base = _nbs_sugestoes()
    if alvo:
        base = [r for r in base if alvo in _normalizar_busca(r["nbs"]) or alvo in _normalizar_busca(r["descricao"])]
    return [formatar_nbs(r) for r in base[:limite]]


def alerta_ctn_regime(texto_ou_codigo_ctn: str, regime: str) -> str:
    """Aviso próprio do ADGE (não é rejeição do leiaute): quando o CTN escolhido costuma
    aparecer associado a um Anexo do Simples Nacional (ou é impeditivo ao Simples) e a
    empresa está num regime diferente. Devolve "" quando não há nada a avisar."""
    codigo = _so_digitos(extrair_codigo_ctn(texto_ou_codigo_ctn))
    if len(codigo) < 4:
        return ""
    pistas = _alerta_regime().get(codigo[:4], [])
    if not pistas:
        return ""
    impeditivas = [p for p in pistas if p["cod_ativ_sn"] == "IMP"]
    if impeditivas and regime in ("simples", "mei"):
        return ("Alerta do ADGE (referência Anexo VIII da Receita, não é regra do leiaute "
                "nacional): este CTN costuma ser uma atividade IMPEDITIVA ao Simples Nacional. "
                "Confira se esta empresa pode mesmo estar no Simples/MEI com este serviço.")
    if regime not in ("simples", "mei"):
        anexos = sorted({p["descricao_ativ_sn"] for p in pistas if p["cod_ativ_sn"] != "IMP" and p["descricao_ativ_sn"]})
        if anexos:
            return ("Alerta do ADGE (referência Anexo VIII da Receita, não é regra do leiaute "
                     "nacional): este CTN costuma aparecer associado ao Simples Nacional (" +
                     "; ".join(anexos) + "), mas a empresa está no regime " + regime +
                     ". Confira se o CTN está certo para este caso.")
    return ""
