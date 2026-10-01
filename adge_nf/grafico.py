"""Agrupamentos para o gráfico de pizza e conversão de números digitados em português."""
from __future__ import annotations

from . import classificacao

PALETA = ["#1B9E5A", "#2F80ED", "#F2994A", "#9B51E0", "#EB5757", "#2DB7C9", "#E0B000", "#7BC47F", "#C2599B", "#4F6D7A"]
COR_OUTROS = "#B8C2BC"
MODOS = {"parte": "Cliente / fornecedor", "servico": "Tipo de serviço (LC 116)", "tipo": "Prestado × Tomado"}
FILTROS = {"ambos": "Prestados e tomados", "prestado": "Só prestados", "tomado": "Só tomados"}


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


def agrupar(arquivos: list, modo: str = "parte", filtro: str = "ambos", top: int = 8) -> list:
    """Devolve [(rótulo, valor, percentual)] em ordem decrescente; o que passa do `top` vira 'Outros'."""
    soma: dict = {}
    for a in arquivos:
        prestado = a["cat"] == "servico_prestado"
        if modo != "tipo" and filtro != "ambos" and (filtro == "prestado") != prestado:
            continue
        d = a["doc"]
        if modo == "tipo":
            chave = "Serviços prestados" if prestado else "Serviços tomados"
        elif modo == "servico":
            chave = classificacao.rotulo_servico(d)
        else:
            nome = (d["tomador_nome"] or d["tomador_doc"]) if prestado else (d["emitente_nome"] or d["emitente_doc"])
            chave = (nome or "(sem nome)").strip()
            if filtro == "ambos":
                chave += " · cliente" if prestado else " · fornecedor"
        soma[chave] = soma.get(chave, 0.0) + a["doc"]["valor"]
    itens = sorted(((k, round(v, 2)) for k, v in soma.items() if v > 0), key=lambda t: -t[1])
    if len(itens) > top + 1:
        resto = itens[top:]
        itens = itens[:top] + [(f"Outros ({len(resto)})", round(sum(v for _, v in resto), 2))]
    total = sum(v for _, v in itens)
    return [(k, v, (v / total * 100 if total else 0.0)) for k, v in itens]


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
