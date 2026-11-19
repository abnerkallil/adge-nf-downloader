"""Planilha modelo para lançar várias notas de uma vez: uma linha por nota. Gerar e importar usam
as mesmas colunas, então o modelo baixado sempre volta certo."""
from __future__ import annotations

import datetime as dt
import re
import zipfile
from pathlib import Path

from ..core import ErroAdge
from .lancamento import Lancamento

COLUNAS = ["Tomador (nome)", "Documento (CPF ou CNPJ)", "Endereço", "Valor", "Competência (AAAA-MM)",
           "Data da prestação (AAAA-MM-DD, opcional)", "Observações"]

LINHA_EXEMPLO = ["Fulano de Tal", "123.456.789-01", "Rua Exemplo, 100", 1250.00, "2026-11", "", ""]


def gerar_modelo_xlsx(caminho) -> Path:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Lançamentos"
    for i, nome in enumerate(COLUNAS, 1):
        c = ws.cell(1, i, nome)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F9D5B")
        c.alignment = Alignment(horizontal="left", wrap_text=True)
        ws.column_dimensions[chr(64 + i)].width = 26
    for i, v in enumerate(LINHA_EXEMPLO, 1):
        ws.cell(2, i, v)
    caminho = Path(caminho)
    wb.save(caminho)
    return caminho


def _texto(v) -> str:
    return str(v).strip() if v is not None else ""


def _competencia_de(valor_celula, data_prestacao: str) -> str:
    if valor_celula not in (None, ""):
        s = _texto(valor_celula)
        m = re.match(r"^(\d{4})-(\d{1,2})$", s) or re.match(r"^(\d{1,2})/(\d{4})$", s)
        if m:
            a, mm = (m[1], m[2]) if len(m[1]) == 4 else (m[2], m[1])
            return f"{a}-{int(mm):02d}"
        return s
    if data_prestacao:
        return data_prestacao[:7]
    return ""


def _data_de(celula) -> str:
    if celula is None or celula == "":
        return ""
    if isinstance(celula, (dt.date, dt.datetime)):
        return celula.strftime("%Y-%m-%d")
    return _texto(celula)


def _valor_de(celula) -> float:
    if celula in (None, ""):
        return 0.0
    if isinstance(celula, (int, float)):
        return float(celula)
    s = re.sub(r"[^\d,.\-]", "", str(celula))
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def importar_xlsx(caminho) -> tuple:
    """Lê a planilha modelo (ou qualquer .xlsx com essas colunas, em qualquer ordem, pelo
    cabeçalho da primeira linha). Devolve (lançamentos, erros); erros aponta a linha (1-based,
    contando o cabeçalho) de quem não pôde virar lançamento."""
    import openpyxl

    try:
        wb = openpyxl.load_workbook(caminho, data_only=True)
    except (OSError, KeyError, zipfile.BadZipFile) as e:
        raise ErroAdge(f"Não consegui abrir a planilha: {e}") from e
    ws = wb.active
    linhas = list(ws.iter_rows(values_only=True))
    if not linhas:
        return [], ["Planilha vazia"]
    cabecalho = [_texto(c).lower() for c in linhas[0]]

    def col(*nomes):
        for n in nomes:
            if n in cabecalho:
                return cabecalho.index(n)
        return None

    idx = {
        "nome": col("tomador (nome)", "tomador", "nome"),
        "documento": col("documento (cpf ou cnpj)", "documento", "cpf/cnpj", "cpf ou cnpj"),
        "endereco": col("endereço", "endereco"),
        "valor": col("valor"),
        "competencia": col("competência (aaaa-mm)", "competencia", "competência"),
        "data": col("data da prestação (aaaa-mm-dd, opcional)", "data da prestação", "data"),
        "observacoes": col("observações", "observacoes", "dúvidas", "duvidas"),
    }
    if idx["nome"] is None or idx["valor"] is None:
        return [], ['A planilha precisa das colunas "Tomador (nome)" e "Valor".']

    def valor_de(linha, campo):
        i = idx[campo]
        return linha[i] if i is not None and i < len(linha) else None

    lancamentos, erros = [], []
    for n, linha in enumerate(linhas[1:], start=2):
        if all(v in (None, "") for v in linha):
            continue
        nome = _texto(valor_de(linha, "nome"))
        if not nome:
            erros.append(f"Linha {n}: sem nome do tomador, ignorada")
            continue
        data_prestacao = _data_de(valor_de(linha, "data"))
        try:
            lanc = Lancamento(
                tomador_nome=nome,
                tomador_documento=_texto(valor_de(linha, "documento")),
                endereco=_texto(valor_de(linha, "endereco")),
                valor=_valor_de(valor_de(linha, "valor")),
                competencia=_competencia_de(valor_de(linha, "competencia"), data_prestacao),
                data_prestacao=data_prestacao,
                observacoes=_texto(valor_de(linha, "observacoes")),
                origem="planilha",
                linha_origem=n,
            )
        except ErroAdge as e:
            erros.append(f"Linha {n}: {e}")
            continue
        lancamentos.append(lanc)
    return lancamentos, erros
