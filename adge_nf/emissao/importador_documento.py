"""Importa lançamentos de um documento qualquer do cliente (PDF com tabela, .xlsx ou .csv fora
do modelo, cada um com suas próprias colunas) — não só da planilha modelo. Em duas etapas:
1) `extrair_tabela` lê a tabela "crua" (cabeçalho + linhas de texto);
2) a tela de mapeamento liga cada coluna a um campo do lançamento (um palpite de
   `sugerir_mapeamento` já vem marcado, mas quem confirma é o usuário) e `construir_lancamentos`
   aplica esse mapeamento.
Casos como o da Ferreira Maria (coluna "Inquilino" com nome, CPF, telefone e e-mail no mesmo
texto) usam o campo composto `nome_documento`, que separa nome e CPF/CNPJ automaticamente."""
from __future__ import annotations

import csv
import re

from ..core import ErroAdge
from .lancamento import Lancamento

CAMPOS = ("nome", "documento", "nome_documento", "endereco", "valor", "competencia", "data",
          "perfil_nome", "observacoes", "ignorar")

_PALAVRAS_CHAVE = {
    "nome_documento": ("inquilino", "cliente/inquilino"),
    "nome": ("tomador", "cliente", "nome", "razão social", "razao social", "contratante"),
    "documento": ("cpf", "cnpj", "documento"),
    "endereco": ("endereço", "endereco", "casa", "imóvel", "imovel", "local"),
    "valor": ("valor recebido", "valor pago", "valor", "total"),
    "competencia": ("competência", "competencia", "mês", "mes"),
    "data": ("data",),
    "perfil_nome": ("perfil de serviço", "perfil de servico", "perfil"),
    "observacoes": ("dúvidas", "duvidas", "observaç", "obs"),
}

_RE_CPF = re.compile(r"(?<!\d)(\d{3}\.?\d{3}\.?\d{3}-?\d{2})(?!\d)")
_RE_CNPJ = re.compile(r"(?<!\d)(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})(?!\d)")


def extrair_tabela(caminho) -> tuple:
    """Devolve (cabecalho: list[str], linhas: list[list[str]]) da maior tabela encontrada.
    PDF: junta as tabelas de todas as páginas que repetirem o mesmo cabeçalho (listas longas
    costumam quebrar de página); cada célula mantém as quebras de linha internas."""
    caminho = str(caminho)
    if caminho.lower().endswith(".pdf"):
        return _extrair_pdf(caminho)
    if caminho.lower().endswith(".csv"):
        return _extrair_csv(caminho)
    if caminho.lower().endswith((".xlsx", ".xlsm")):
        return _extrair_xlsx(caminho)
    raise ErroAdge("Formato não suportado para importar documento: use PDF, .xlsx ou .csv.")


def _limpar_celula(v) -> str:
    return re.sub(r"\s+\n", "\n", str(v).strip()) if v is not None else ""


def _extrair_pdf(caminho) -> tuple:
    import pdfplumber

    cabecalho, linhas = None, []
    try:
        with pdfplumber.open(caminho) as pdf:
            for pagina in pdf.pages:
                for tabela in pagina.extract_tables() or []:
                    if not tabela:
                        continue
                    cab_pagina = [_limpar_celula(c) for c in tabela[0]]
                    corpo = [[_limpar_celula(c) for c in linha] for linha in tabela[1:]]
                    if cabecalho is None:
                        cabecalho = cab_pagina
                        linhas.extend(corpo)
                    elif cab_pagina == cabecalho:
                        linhas.extend(corpo)                      # mesma tabela continuando na página seguinte
                    else:
                        linhas.append(cab_pagina)                 # tabela sem cabeçalho repetido: trata como dado
                        linhas.extend(corpo)
    except Exception as e:
        raise ErroAdge(f"Não consegui ler a tabela do PDF: {e}") from e
    if cabecalho is None:
        raise ErroAdge("Não encontrei nenhuma tabela nesse PDF.")
    return cabecalho, linhas


def _extrair_csv(caminho) -> tuple:
    with open(caminho, newline="", encoding="utf-8-sig") as f:
        linhas = [linha for linha in csv.reader(f) if any(c.strip() for c in linha)]
    if not linhas:
        raise ErroAdge("Planilha CSV vazia.")
    return linhas[0], linhas[1:]


def _extrair_xlsx(caminho) -> tuple:
    import openpyxl

    wb = openpyxl.load_workbook(caminho, data_only=True)
    linhas = [[("" if c is None else c) for c in linha] for linha in wb.active.iter_rows(values_only=True)
              if any(c not in (None, "") for c in linha)]
    if not linhas:
        raise ErroAdge("Planilha vazia.")
    return linhas[0], linhas[1:]


def sugerir_mapeamento(cabecalho: list) -> dict:
    """{indice_da_coluna: campo} com o palpite automático por palavra-chave do cabeçalho; colunas
    sem palpite ficam de fora (a tela trata como "ignorar" até o usuário escolher)."""
    mapeamento = {}
    for i, titulo in enumerate(cabecalho):
        titulo_norm = (titulo or "").strip().lower()
        for campo, chaves in _PALAVRAS_CHAVE.items():
            if any(chave in titulo_norm for chave in chaves):
                mapeamento[i] = campo
                break
    return mapeamento


def _extrair_documento_embutido(texto: str) -> str:
    m = _RE_CNPJ.search(texto) or _RE_CPF.search(texto)
    return re.sub(r"\D", "", m[1]) if m else ""


def _primeira_linha(texto: str) -> str:
    return next((l.strip() for l in texto.splitlines() if l.strip()), "")


def construir_lancamentos(cabecalho: list, linhas: list, mapeamento: dict, competencia_padrao: str = "") -> tuple:
    """`mapeamento`: {indice: campo}, um dos valores de `CAMPOS` (como `sugerir_mapeamento`
    devolve, ajustado pelo usuário na tela). Devolve (lançamentos, erros)."""
    lancamentos, erros = [], []
    for n, linha in enumerate(linhas, start=2):  # 2: linha 1 é o cabeçalho
        valores = {"nome": "", "documento": "", "endereco": "", "valor": "", "competencia": competencia_padrao,
                   "data": "", "perfil_nome": "", "observacoes": ""}
        for i, campo in mapeamento.items():
            if campo in (None, "ignorar") or i >= len(linha):
                continue
            texto = str(linha[i] or "").strip()
            if not texto:
                continue
            if campo == "nome_documento":
                valores["nome"] = _primeira_linha(texto)
                doc = _extrair_documento_embutido(texto)
                if doc:
                    valores["documento"] = doc
            elif campo == "documento":
                valores["documento"] = re.sub(r"\D", "", texto)
            else:
                valores[campo] = texto
        if not valores["nome"] and not any(v for k, v in valores.items() if k != "competencia"):
            continue  # linha totalmente em branco
        if not valores["nome"]:
            erros.append(f"Linha {n}: sem nome do tomador, ignorada")
            continue
        from .planilha_emissao import valor_numerico
        try:
            lanc = Lancamento(
                tomador_nome=valores["nome"],
                tomador_documento=valores["documento"],
                endereco=valores["endereco"],
                valor=valor_numerico(valores["valor"]),
                competencia=valores["competencia"] or competencia_padrao,
                data_prestacao=valores["data"],
                perfil_nome=valores["perfil_nome"],
                observacoes=valores["observacoes"],
                origem="documento",
                linha_origem=n,
                motivo_exclusao=valores["observacoes"] if valores["observacoes"] and valores["observacoes"] != "-" else "",
            )
        except ErroAdge as e:
            erros.append(f"Linha {n}: {e}")
            continue
        lancamentos.append(lanc)
    return lancamentos, erros
