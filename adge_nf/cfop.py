"""CFOP das NF-e: o que cada código significa para totais, anexo do Simples e crédito.

O CFOP tem 4 dígitos: o primeiro diz a direção (1/2/3 entrada, 5/6/7 saída; 1 e 5 no estado, 2 e 6 em outros estados, 3 e 7
exterior) e os três últimos dizem a natureza da operação. Tudo que é interpretação fica nas tabelas abaixo, em um só lugar,
porque o CFOP é extenso e a classificação é uma ORIENTAÇÃO: o contador confere. O que não está nas tabelas vira "outras operações"
e fica fora dos totais por padrão (remessas, transferências, bonificações, consertos, demonstrações etc.).
"""
from __future__ import annotations

import re

ENTRADA, SAIDA = "123", "567"

# --- saídas (CFOP 5/6/7) ----------------------------------------------------------------------------------
# Vendas: x.1xx (menos transferências 151-159) e x.4xx de substituição tributária (401-405); combustíveis 651-667.
_VENDA_SAIDA_EXTRAS = {"401", "402", "403", "404", "405"} | {f"{n}" for n in range(651, 668)}
_TRANSFERENCIA_1XX = {f"{n}" for n in range(151, 160)}
# Devolução de compra (a empresa devolve ao fornecedor): x.201, 202, 205, 206, 207, 210 e as de substituição tributária.
_DEVOLUCAO_COMPRA = {"201", "202", "205", "206", "207", "210", "410", "411", "412", "413"}
# Venda de produção própria (indústria, Anexo II do Simples). As demais vendas são de mercadoria adquirida (comércio, Anexo I).
_INDUSTRIA = {"101", "103", "105", "107", "109", "111", "113", "116", "118", "122", "124", "125", "401", "402"}

# --- entradas (CFOP 1/2/3) --------------------------------------------------------------------------------
# Compras: x.1xx (menos transferências), x.4xx de ST (401-406), ativo (551) e uso e consumo (556), combustíveis 651-667.
_COMPRA_ENTRADA_EXTRAS = {"401", "402", "403", "404", "405", "406", "551", "556"} | {f"{n}" for n in range(651, 668)}
# Devolução de venda (o cliente devolveu): x.201 a 204, ST (410-413) e ativo (553).
_DEVOLUCAO_VENDA = {"201", "202", "203", "204", "410", "411", "412", "413", "553"}

OPERACOES = ("venda", "compra", "devolucao_venda", "devolucao_compra", "outras")


def normalizar(cfop) -> str:
    d = re.sub(r"\D", "", str(cfop or ""))
    return d[:4] if len(d) >= 4 else ""


def direcao(cfop) -> str:
    """'entrada', 'saida' ou ''."""
    c = normalizar(cfop)
    if not c:
        return ""
    return "entrada" if c[0] in ENTRADA else ("saida" if c[0] in SAIDA else "")


def operacao(cfop) -> str:
    """Natureza da operação pelo CFOP, do ponto de vista de quem emitiu: venda, compra, devolucao_venda, devolucao_compra ou outras."""
    c = normalizar(cfop)
    if not c:
        return "outras"
    suf = c[1:]
    if c[0] in SAIDA:
        if (suf.startswith("1") and suf not in _TRANSFERENCIA_1XX) or suf in _VENDA_SAIDA_EXTRAS:
            return "venda"
        if suf in _DEVOLUCAO_COMPRA:
            return "devolucao_compra"
        return "outras"
    if c[0] in ENTRADA:
        if (suf.startswith("1") and suf not in _TRANSFERENCIA_1XX) or suf in _COMPRA_ENTRADA_EXTRAS:
            return "compra"
        if suf in _DEVOLUCAO_VENDA:
            return "devolucao_venda"
        return "outras"
    return "outras"


def atividade_da_venda(cfop) -> str:
    """Para uma venda de mercadoria: 'industria' (produção própria, Anexo II) ou 'comercio' (revenda, Anexo I)."""
    c = normalizar(cfop)
    return "industria" if c and c[1:] in _INDUSTRIA else "comercio"


# --- crédito das compras ----------------------------------------------------------------------------------
# Fração do valor da compra que tende a gerar crédito: (PIS/Cofins no Lucro Real, IBS/CBS na reforma).
# Revenda e insumo geram crédito pleno; ativo só no IBS/CBS; uso e consumo, parcial; o resto, a meio caminho.
def peso_credito(cfop) -> tuple:
    c = normalizar(cfop)
    suf = c[1:] if c else ""
    if suf == "551":
        return 0.0, 1.0
    if suf == "556":
        return 0.0, 0.5
    if suf.startswith("1") or suf in _COMPRA_ENTRADA_EXTRAS:
        return 1.0, 1.0
    return 0.5, 0.5


def formatar(cfop) -> str:
    c = normalizar(cfop)
    return f"{c[0]}.{c[1:]}" if c else ""
