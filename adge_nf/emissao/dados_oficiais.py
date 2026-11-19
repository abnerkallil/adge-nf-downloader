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


def _normalizar_codigo(texto: str) -> str:
    """Só letras e números, pra buscar "990101" e achar "99.01.01" (ou "110021000" e achar
    "1.1002.10.00") — a pontuação do código não importa pra quem está digitando."""
    return re.sub(r"[^0-9a-z]", "", _normalizar_busca(texto))


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
    """Filtra CTN por código (com ou sem pontuação: "990101" acha "99.01.01") ou por palavra na
    descrição (busca tipo o portal, sem acento)."""
    alvo = _normalizar_busca(texto)
    alvo_codigo = _normalizar_codigo(texto)
    if not alvo:
        return listar_ctn()[:limite]
    achados = [
        formatar_ctn(r) for r in _ctn_lista()
        if alvo in _normalizar_busca(r["descricao"])
        or (alvo_codigo and alvo_codigo in _normalizar_codigo(r["codigo"]))
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
    """Sugestões de NBS (lista do Anexo VIII, não é a tabela oficial completa de NBS). Código
    aceito com ou sem pontuação: "110021000" acha "1.1002.10.00"."""
    alvo = _normalizar_busca(texto)
    alvo_codigo = _normalizar_codigo(texto)
    base = _nbs_sugestoes()
    if alvo:
        base = [r for r in base if alvo in _normalizar_busca(r["descricao"])
                or (alvo_codigo and alvo_codigo in _normalizar_codigo(r["nbs"]))]
    return [formatar_nbs(r) for r in base[:limite]]


@lru_cache(maxsize=1)
def _municipios() -> list[dict]:
    """Tabela oficial dos 5.571 municípios do IBGE (nome, UF e código de 7 dígitos), baixada da
    API `servicodados.ibge.gov.br/api/v1/localidades/municipios` em 19/11/2026 — embutida porque
    o código IBGE do município é obrigatório na DPS (`prest/end/cMun`, `toma/end/cMun`) e não dá
    pra pedir pro usuário decorar ou procurar fora do app."""
    with open(_PASTA_DADOS / "municipios_ibge.json", encoding="utf-8") as f:
        return json.load(f)


def formatar_municipio(registro: dict) -> str:
    return f"{registro['municipio']} - {registro['uf']}"


def buscar_municipio(texto: str, limite: int = 30) -> list[str]:
    """Município por nome (sem acento/pontuação) ou pelo próprio código IBGE de 7 dígitos.
    Texto vazio não devolve a lista inteira (5.571 municípios não cabem num combo) — só depois
    de digitar algo."""
    alvo = _normalizar_busca(texto)
    if not alvo:
        return []
    alvo_codigo = _normalizar_codigo(texto)
    achados = [
        formatar_municipio(r) for r in _municipios()
        if alvo in _normalizar_busca(f"{r['municipio']} {r['uf']}")
        or (len(alvo_codigo) >= 4 and alvo_codigo in r["codigo_ibge"])
    ]
    return achados[:limite]


def municipio_por_texto_formatado(texto_formatado: str) -> dict | None:
    """Acha o registro (município, UF, código IBGE) a partir do texto "Município - UF" que
    o combo de busca devolve. None se não bater com nenhum (texto digitado à mão, por exemplo)."""
    alvo = _normalizar_busca(texto_formatado or "")
    for r in _municipios():
        if _normalizar_busca(formatar_municipio(r)) == alvo:
            return r
    return None


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
