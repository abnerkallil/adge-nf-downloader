"""Totais por categoria e seleção do que entra nos números.

Cada nota tem uma categoria (veja core.CATEGORIAS): NFS-e prestada/tomada e NF-e de venda, compra, devoluções, outras operações
e "sem ciência" (só resumo). A pessoa marca quais categorias quer considerar; cartões, saldo, gráfico, comparativo de regimes
e planilha usam a MESMA seleção, para os números nunca divergirem entre as telas.
"""
from __future__ import annotations

from . import core

CATEGORIAS = core.CATEGORIAS


def rotulo(cat: str) -> str:
    return CATEGORIAS[cat]["rotulo"]


def lado(a: dict) -> str:
    return CATEGORIAS[a["cat"]]["lado"]


def sinal(a: dict) -> int:
    return CATEGORIAS[a["cat"]]["sinal"]


def padrao_ativos(categorias) -> set:
    """Categorias marcadas de início: as que fazem parte do dia a dia. Outras operações e notas sem ciência começam desmarcadas."""
    return {c for c in categorias if CATEGORIAS[c]["padrao"]}


def por_categoria(arquivos: list) -> dict:
    """{cat: {qtd, valor, icms}} de tudo que foi encontrado, sem olhar a seleção (sinal não aplicado)."""
    saida = {}
    for a in arquivos:
        r = saida.setdefault(a["cat"], {"qtd": 0, "valor": 0.0, "icms": 0.0})
        r["qtd"] += 1
        r["valor"] += float(a["doc"].get("valor") or 0)
        r["icms"] += float(a["doc"].get("icms") or 0)
    for r in saida.values():
        r["valor"], r["icms"] = round(r["valor"], 2), round(r["icms"], 2)
    return saida


def filtrar(arquivos: list, ativos) -> list:
    return [a for a in arquivos if a["cat"] in ativos]


def totais(arquivos: list, ativos) -> dict:
    """Faturamento (receitas − devoluções de venda), compras e serviços tomados (− devoluções de compra) e o saldo entre eles.
    Categorias neutras (outras operações) aparecem na lista, mas não entram na conta."""
    fat = comp = 0.0
    por_cat = {}
    for a in filtrar(arquivos, ativos):
        v = float(a["doc"].get("valor") or 0)
        r = por_cat.setdefault(a["cat"], {"qtd": 0, "valor": 0.0})
        r["qtd"] += 1
        r["valor"] += v
        if lado(a) == "receita":
            fat += sinal(a) * v
        elif lado(a) == "custo":
            comp += sinal(a) * v
    for r in por_cat.values():
        r["valor"] = round(r["valor"], 2)
    return {"faturamento": round(fat, 2), "compras": round(comp, 2), "saldo": round(fat - comp, 2), "por_cat": por_cat}


def atividades(arquivos: list, ativos) -> dict:
    """Separa o que entrou na seleção por tipo de atividade, para o comparativo de regimes.
    receitas: servicos (NFS-e prestadas), comercio (vendas de mercadoria adquirida, Anexo I), industria (produção própria, Anexo II).
    compras: servicos (NFS-e tomadas) e mercadorias (NF-e de compra e notas só com resumo). Devoluções abatem.
    icms: débito das vendas e crédito das compras, conforme o ICMS destacado nas NF-e."""
    r = {"servicos": 0.0, "comercio": 0.0, "industria": 0.0}
    c = {"servicos": 0.0, "mercadorias": 0.0}
    deb = cred = 0.0
    dev_v = dev_c = 0.0
    for a in filtrar(arquivos, ativos):
        v, icms, cat = float(a["doc"].get("valor") or 0), float(a["doc"].get("icms") or 0), a["cat"]
        if cat == "servico_prestado":
            r["servicos"] += v
        elif cat == "nfe_saida":
            r["industria" if a["doc"].get("atividade") == "industria" else "comercio"] += v
            deb += icms
        elif cat == "nfe_devolucao_venda":
            dev_v += v
            deb -= icms
        elif cat == "servico_tomado":
            c["servicos"] += v
        elif cat in ("nfe_entrada", "nfe_resumo"):
            c["mercadorias"] += v
            cred += icms
        elif cat == "nfe_devolucao_compra":
            dev_c += v
            cred -= icms
    mercadorias = r["comercio"] + r["industria"]
    if dev_v:
        if mercadorias > 0:
            r["comercio"] -= dev_v * r["comercio"] / mercadorias
            r["industria"] -= dev_v * r["industria"] / mercadorias
        else:
            r["comercio"] -= dev_v
    c["mercadorias"] -= dev_c
    for d in (r, c):
        for k in d:
            d[k] = round(max(0.0, d[k]), 2)
    return {"receitas": r, "compras": c, "faturamento": round(sum(r.values()), 2), "tomados": round(sum(c.values()), 2),
            "icms_debito": round(max(0.0, deb), 2), "icms_credito": round(max(0.0, cred), 2)}


class Selecao:
    """Conjunto de categorias marcadas, compartilhado entre a janela de busca e a de informações avançadas."""

    def __init__(self, ativos=()):
        self.ativos = set(ativos)
        self._ouvintes = []

    def ativa(self, cat: str) -> bool:
        return cat in self.ativos

    def definir(self, cat: str, ligado: bool):
        antes = set(self.ativos)
        (self.ativos.add if ligado else self.ativos.discard)(cat)
        if antes != self.ativos:
            self._avisar()

    def alternar(self, cat: str):
        self.definir(cat, cat not in self.ativos)

    def ao_mudar(self, funcao):
        self._ouvintes.append(funcao)

    def esquecer(self, funcao):
        self._ouvintes = [f for f in self._ouvintes if f is not funcao]

    def _avisar(self):
        for f in list(self._ouvintes):
            try:
                f()
            except Exception:       # uma janela já fechada não pode derrubar as outras
                self._ouvintes = [x for x in self._ouvintes if x is not f]
