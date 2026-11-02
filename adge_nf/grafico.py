"""Agrupamentos para o gráfico de pizza e conversão de números digitados em português."""
from __future__ import annotations

from . import cfop as cfop_mod
from . import classificacao, core

# Cores do gráfico derivadas da paleta da Adge. A ordem alterna verdes,
# neutros e azuis secundários para manter leitura sem sair da identidade.
PALETA = [
    "#52A045",  # verde Adge
    "#3F4E53",  # azul-pedra
    "#B86E4B",  # terracota
    "#3F6620",  # verde escuro
    "#A79B55",  # oliva
    "#1D1D1B",  # preto estrutural
    "#677C82",  # azul ardósia
    "#8AAE45",  # verde claro
    "#7E8083",  # cinza
    "#B3C8A4",  # sage
]
COR_OUTROS = "#BEC7BC"
MODOS = {"parte": "Cliente / fornecedor", "servico": "Serviço (LC 116) ou CFOP", "tipo": "Tipo de nota"}
FILTROS = {"ambos": "Prestados e tomados", "prestado": "Só prestados", "tomado": "Só tomados"}   # só para chamadas antigas
ROTULO_TIPO = {"servico_prestado": "Serviços prestados", "servico_tomado": "Serviços tomados"}


def parse_brl(texto) -> float:
    """'R$ 1.234,56' -> 1234.56 ; '1234.56' -> 1234.56 ; '' -> 0."""
    t = str(texto or "").replace("R$", "").replace(" ", "").strip()
    if not t:
        return 0.0
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1 or (t.count(".") == 1 and len(t.rsplit(".", 1)[1]) == 3):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        raise ValueError(f"Número inválido: {texto}")


def _selecao(filtro):
    """Aceita o formato antigo ('ambos'/'prestado'/'tomado') ou um conjunto de categorias. None = tudo."""
    if filtro is None or filtro == "ambos":
        return None
    if isinstance(filtro, str):
        lado = "receita" if filtro == "prestado" else "custo"
        return {c for c, v in core.CATEGORIAS.items() if v["lado"] == lado}
    return set(filtro)


def _rotulo_servico(a: dict) -> str:
    d = a["doc"]
    if a["cat"].startswith("nfe_") and a["cat"] != "nfe_resumo":
        cod = cfop_mod.formatar(d.get("cfop"))
        nat = (d.get("natureza") or "").strip()
        return f"CFOP {cod} · {nat}" if cod and nat else (f"CFOP {cod}" if cod else "NF-e sem CFOP")
    if a["cat"] == "nfe_resumo":
        return "NF-e sem ciência (sem CFOP)"
    return classificacao.rotulo_servico(d)


def agrupar(arquivos: list, modo: str = "parte", filtro=None, top: int = 8, liquido: bool = False) -> list:
    """Devolve [(rótulo, valor, percentual)] em ordem decrescente; o que passa do `top` vira 'Outros'.
    `filtro`: conjunto de categorias marcadas (ou 'ambos'/'prestado'/'tomado', das chamadas antigas).
    `liquido`: o valor de cada fatia leva sinal. O que entra (vendas, serviços prestados) soma, o que sai (compras, serviços tomados)
    reduz, e devoluções invertem o sinal da própria nota. Operações neutras (outras operações) ficam de fora. O percentual
    é a fatia no total em módulo, porque uma pizza só desenha tamanhos."""
    ativas = _selecao(filtro)
    arquivos = [a for a in arquivos if ativas is None or a["cat"] in ativas]
    if liquido:
        arquivos = [a for a in arquivos if core.CATEGORIAS[a["cat"]]["lado"] in ("receita", "custo")]
    lados = {core.CATEGORIAS[a["cat"]]["lado"] for a in arquivos}
    soma: dict = {}
    for a in arquivos:
        info = core.CATEGORIAS[a["cat"]]
        d = a["doc"]
        if modo == "tipo":
            chave = ROTULO_TIPO.get(a["cat"]) or info["rotulo"]
        elif modo == "servico":
            chave = _rotulo_servico(a)
        else:
            receita = info["lado"] == "receita"
            nome = (d["tomador_nome"] or d["tomador_doc"]) if receita else (d["emitente_nome"] or d["emitente_doc"])
            chave = (nome or "(sem nome)").strip()
            if "receita" in lados and "custo" in lados:
                chave += " · cliente" if receita else " · fornecedor"
        v = a["doc"]["valor"]
        if liquido:
            v = v * info["sinal"] * (1 if info["lado"] == "receita" else -1)
        soma[chave] = soma.get(chave, 0.0) + v
    itens = sorted(((k, round(v, 2)) for k, v in soma.items() if (v != 0 if liquido else v > 0)), key=lambda t: -abs(t[1]))
    if len(itens) > top + 1:
        resto = itens[top:]
        itens = itens[:top] + [(f"Outros ({len(resto)})", round(sum(v for _, v in resto), 2), sum(abs(v) for _, v in resto))]
    itens = [(i[0], i[1], i[2] if len(i) > 2 else abs(i[1])) for i in itens]
    total = sum(m for _, _, m in itens)
    return [(k, v, (m / total * 100 if total else 0.0)) for k, v, m in itens]


def cor_da_fatia(rotulo: str, indice: int) -> str:
    return COR_OUTROS if rotulo.startswith("Outros (") else PALETA[indice % len(PALETA)]


def angulos(itens: list) -> list:
    """[(início, extensão)] em graus no sentido horário a partir do topo, no padrão do Tk (extensão negativa)."""
    saida, atual = [], 90.0
    for _, _, pct in itens:
        ext = pct / 100 * 360
        saida.append((atual, -ext))
        atual -= ext
    return saida
