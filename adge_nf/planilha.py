"""Planilha Excel (.xlsx) do período: aba Geral colorida, uma aba por tipo de nota e uma de canceladas."""
from __future__ import annotations

import datetime as dt

from . import NOME_APP, SITE_ADGE, core

VERDE_FUNDO, VERMELHO_FUNDO = "E3F5E9", "FDE7E7"        # paleta A: tons claros, para não poluir
VERDE_TEXTO, VERMELHO_TEXTO = "1F9D5B", "C0392B"
BANNER, CABECALHO_RESUMO, TEXTO_RESUMO = "1F9D5B", "EEF3F0", "1B5E3B"
FORMATO_REAL = '"R$" #,##0.00'

COLUNAS = [("Tipo", 32), ("Nº", 12), ("Emissão", 13), ("Emitente", 38), ("CNPJ emitente", 20), ("Tomador", 38),
           ("CNPJ tomador", 20), ("Valor", 16), ("Valor líquido", 16), ("ISS", 14), ("Chave", 54)]
ROTULOS = {"servico_prestado": "Serviço prestado", "servico_tomado": "Serviço tomado"}
ABAS = {"servico_prestado": "Prestado", "servico_tomado": "Tomado"}


def _linha(a) -> list:
    d = a["doc"]
    return [ROTULOS[a["cat"]], _numero(d["numero"]), core.data_do_doc(d), d["emitente_nome"], d["emitente_doc"],
            d["tomador_nome"], d["tomador_doc"], d["valor"], d["valor_liquido"], d["iss"], d["chave"]]


def _ordenar(itens):
    return sorted(itens, key=lambda a: (core.data_do_doc(a["doc"]) or dt.date.min, str(a["doc"]["numero"]).zfill(12)))


def _numero(n):
    return int(n) if str(n).isdigit() else n


def _cabecalho(ws, linha, estilos):
    Font, Border, Side, Alignment = estilos["Font"], estilos["Border"], estilos["Side"], estilos["Alignment"]
    for i, (nome, largura) in enumerate(COLUNAS, 1):
        c = ws.cell(linha, i, nome)
        c.font = Font(bold=True)
        c.border = Border(bottom=Side(style="medium", color="808080"))
        c.alignment = Alignment(horizontal="right" if nome in ("Valor", "Valor líquido", "ISS") else "left",
                                indent=1 if nome == "Chave" else 0)
        ws.column_dimensions[chr(64 + i)].width = largura


def _tabela(ws, primeira, itens, estilos, colorir):
    PatternFill, Alignment = estilos["PatternFill"], estilos["Alignment"]
    for k, a in enumerate(itens):
        r = primeira + k
        fundo = None
        if colorir:
            fundo = PatternFill("solid", fgColor=VERDE_FUNDO if a["cat"] == "servico_prestado" else VERMELHO_FUNDO)
        for i, v in enumerate(_linha(a), 1):
            c = ws.cell(r, i, v)
            if fundo:
                c.fill = fundo
            if i == 3:
                c.number_format = "dd/mm/yyyy"
                c.alignment = Alignment(horizontal="left")
            elif i in (8, 9, 10):
                c.number_format = FORMATO_REAL
            elif i in (5, 7, 11):
                c.number_format = "@"
                c.value = str(v or "")
                if i == 11:
                    c.alignment = Alignment(horizontal="left", indent=1)
    return primeira + len(itens)


def _banner(ws, titulo, colunas, estilos):
    Font, PatternFill, Alignment = estilos["Font"], estilos["PatternFill"], estilos["Alignment"]
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=colunas)
    c = ws.cell(1, 1, titulo)
    c.font, c.fill = Font(bold=True, color="FFFFFF", size=13), PatternFill("solid", fgColor=BANNER)
    c.alignment = Alignment(vertical="center", indent=1)
    ws.row_dimensions[1].height = 26


def _rodape(ws, linha, estilos):
    c = ws.cell(linha, 1, f"Gerado pelo {NOME_APP} · {SITE_ADGE}")
    c.font = estilos["Font"](color="808080", size=9)
    c.hyperlink = SITE_ADGE


def gerar_xlsx(caminho, empresa: str, ano: int, mes: int, arquivos: list, resumo: dict, canceladas: list = None):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    estilos = dict(Alignment=Alignment, Border=Border, Font=Font, PatternFill=PatternFill, Side=Side)
    periodo = f"{core.mes_exibicao(mes)}/{ano}"
    cats = [c for c in ("servico_prestado", "servico_tomado") if c in resumo]
    ordenadas = _ordenar(arquivos)

    wb = Workbook()
    ws = wb.active
    ws.title = "Geral"
    ws.sheet_view.showGridLines = False
    for i, (_, larg) in enumerate(COLUNAS, 1):
        ws.column_dimensions[chr(64 + i)].width = larg
    _banner(ws, f"RESUMO · {empresa} · {periodo}", 4, estilos)
    for i, t in enumerate(["Categoria", "Qtd notas", "Valor", "Canceladas (fora)"], 1):
        c = ws.cell(2, i, t)
        c.font, c.fill = Font(bold=True, color=TEXTO_RESUMO), PatternFill("solid", fgColor=CABECALHO_RESUMO)
        c.alignment = Alignment(horizontal="left" if i == 1 else "right", indent=1)
    for k, cat in enumerate(cats):
        r, dados = 3 + k, resumo[cat]
        prest = cat == "servico_prestado"
        fundo, cor = (VERDE_FUNDO, VERDE_TEXTO) if prest else (VERMELHO_FUNDO, VERMELHO_TEXTO)
        ws.row_dimensions[r].height = 24
        for i, v in enumerate([ROTULOS[cat] + (" (faturamento)" if prest else ""), dados["qtd"], dados["valor"], dados["canceladas"]], 1):
            c = ws.cell(r, i, v)
            c.fill, c.font = PatternFill("solid", fgColor=fundo), Font(bold=True, color=cor, size=12 if i == 3 else 11)
            c.alignment = Alignment(horizontal="left" if i == 1 else "right", vertical="center", indent=1)
            if i == 3:
                c.number_format = FORMATO_REAL
    topo = 3 + len(cats) + 1
    _cabecalho(ws, topo, estilos)
    fim = _tabela(ws, topo + 1, ordenadas, estilos, colorir=True)
    ws.auto_filter.ref = f"A{topo}:{chr(64 + len(COLUNAS))}{max(fim - 1, topo)}"
    _rodape(ws, fim + 1, estilos)

    for cat in cats:                                     # uma aba por tipo, sem cores
        itens = [a for a in ordenadas if a["cat"] == cat]
        dados = resumo[cat]
        w = wb.create_sheet(ABAS[cat])
        w.sheet_view.showGridLines = False
        _banner(w, f"RESUMO · {ROTULOS[cat]} · {empresa} · {periodo}", 5, estilos)
        for i, t in enumerate(["Qtd notas", "Valor", "Valor líquido", "ISS", "Canceladas (fora)"], 1):
            c = w.cell(2, i, t)
            c.font, c.fill = Font(bold=True, color=TEXTO_RESUMO), PatternFill("solid", fgColor=CABECALHO_RESUMO)
            c.alignment = Alignment(horizontal="right")
        for i, v in enumerate([dados["qtd"], dados["valor"], dados["liquido"], dados["iss"], dados["canceladas"]], 1):
            c = w.cell(3, i, v)
            c.font, c.alignment = Font(bold=True, size=12), Alignment(horizontal="right")
            if i in (2, 3, 4):
                c.number_format = FORMATO_REAL
        _cabecalho(w, 5, estilos)
        f = _tabela(w, 6, itens, estilos, colorir=False)
        w.auto_filter.ref = f"A5:{chr(64 + len(COLUNAS))}{max(f - 1, 5)}"
        _rodape(w, f + 1, estilos)

    wc = wb.create_sheet("Canceladas")
    wc.sheet_view.showGridLines = False
    _banner(wc, f"NOTAS CANCELADAS (fora dos totais) · {empresa} · {periodo}", 5, estilos)
    _cabecalho(wc, 3, estilos)
    lista = _ordenar(canceladas or [])
    f = _tabela(wc, 4, lista, estilos, colorir=False)
    if not lista:
        wc.cell(2, 1, "Nenhuma nota cancelada neste período.").font = Font(italic=True, color="808080")
    _rodape(wc, f + 1, estilos)
    from openpyxl.worksheet.properties import PageSetupProperties
    for w in wb.worksheets:                              # imprime em paisagem, cabendo na largura da página
        w.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
        w.page_setup.orientation, w.page_setup.fitToWidth, w.page_setup.fitToHeight = "landscape", 1, 0
    wb.save(str(caminho))
