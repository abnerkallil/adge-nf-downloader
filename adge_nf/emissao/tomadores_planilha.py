"""Planilha modelo para cadastrar vários tomadores recorrentes de uma vez. Gerar e importar usam
as mesmas colunas, então o modelo baixado sempre volta certo.

Só o nome é obrigatório; tudo o mais é opcional e nunca trava a importação — uma informação que
falta só limita o que aquele tomador consegue fazer sozinho (ex.: sem documento nem endereço, o
casamento automático não encontra essa nota)."""
from __future__ import annotations

from pathlib import Path

from ..core import ErroAdge
from . import config_schema as es

COLUNAS = ["Nome", "Documento (CPF ou CNPJ)", "Identificação na nota", "Perfil de serviço (nome, opcional)",
           "CEP", "Logradouro", "Número", "Complemento", "Bairro", "Município", "UF",
           "Código IBGE do município", "Endereço (texto livre, opcional)",
           "Descrição para este tomador (opcional)", "Informações complementares (opcional)", "Ativo (Sim/Não)"]

_IDENTIFICACAO_PLANILHA = {
    "herdar": "Padrão da empresa",
    "documento": "Só documento (CPF/CNPJ)",
    "endereco": "Documento e endereço completo",
}
_PLANILHA_IDENTIFICACAO = {v: k for k, v in _IDENTIFICACAO_PLANILHA.items()}

LINHA_EXEMPLO = ["Fulano de Tal", "123.456.789-01", _IDENTIFICACAO_PLANILHA["herdar"], "",
                  "86010-000", "Rua das Flores", "100", "", "Centro", "Londrina", "PR", "4113700",
                  "", "", "", "Sim"]


def gerar_modelo_xlsx(caminho, perfis: list | None = None) -> Path:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = openpyxl.Workbook()
    ws_instrucoes = wb.active
    ws_instrucoes.title = "Instruções"
    _montar_instrucoes(ws_instrucoes, perfis or [])

    ws = wb.create_sheet("Tomadores")
    for i, nome in enumerate(COLUNAS, 1):
        c = ws.cell(1, i, nome)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="1F9D5B")
        c.alignment = Alignment(horizontal="left", wrap_text=True)
        ws.column_dimensions[chr(64 + i)].width = 22
    for i, v in enumerate(LINHA_EXEMPLO, 1):
        ws.cell(2, i, v)
    caminho = Path(caminho)
    wb.save(caminho)
    return caminho


def _montar_instrucoes(ws, perfis: list):
    from openpyxl.styles import Alignment, Font

    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 90
    linhas = [
        ("Como preencher", ""),
        ("", "Uma linha por tomador, na aba \"Tomadores\". Só \"Nome\" é obrigatório — "
             "deixe o resto em branco quando não souber ou não se aplicar: nenhum campo opcional "
             "vazio impede a importação."),
        ("", ""),
        ("Coluna", "Obrigatório? / O que é"),
        ("Nome", "Obrigatório. Nome do tomador (pessoa ou empresa)."),
        ("Documento (CPF ou CNPJ)", "Opcional, mas é preciso ter documento OU endereço completo "
                                      "(logradouro + município) preenchido — é por aí que a nota reconhece o tomador."),
        ("Identificação na nota", "Opcional. \"Padrão da empresa\" (usa a regra geral da empresa), "
                                    "\"Só documento\" ou \"Documento e endereço completo\" (obriga logradouro e "
                                    "município nesta linha). Em branco = Padrão da empresa."),
        ("Perfil de serviço (nome, opcional)", "Opcional. Nome de um perfil já cadastrado na empresa. "
                                                 "Em branco = usa o perfil padrão da empresa. Nome que não existir "
                                                 "é avisado na importação, mas não impede o resto da linha."),
        ("CEP / Logradouro / Número / Complemento / Bairro / Município / UF", "Opcionais, exceto quando "
             "\"Identificação na nota\" = \"Documento e endereço completo\" (Logradouro e Município passam a "
             "ser obrigatórios nessa linha)."),
        ("Código IBGE do município", "Opcional. Só é usado se a nota desse tomador precisar do endereço completo."),
        ("Endereço (texto livre, opcional)", "Opcional. Texto livre, útil para casar a nota quando o endereço "
                                               "estruturado não é suficiente (ex.: nome popular de um imóvel)."),
        ("Descrição para este tomador (opcional)", "Opcional. Em branco = usa a descrição do perfil de serviço."),
        ("Informações complementares (opcional)", "Opcional. Em branco = usa as informações do perfil de serviço."),
        ("Ativo (Sim/Não)", "Opcional. Em branco = Sim. \"Não\" cadastra o tomador mas o deixa fora do "
                              "casamento automático."),
    ]
    for r, (a, b) in enumerate(linhas, 1):
        ca = ws.cell(r, 1, a)
        cb = ws.cell(r, 2, b)
        cb.alignment = Alignment(wrap_text=True, vertical="top")
        if r in (1,):
            ca.font = Font(bold=True, size=13)
        elif r == 4:
            ca.font = Font(bold=True)
            cb.font = Font(bold=True)
        elif a:
            ca.font = Font(bold=True)
    if perfis:
        r = len(linhas) + 2
        ws.cell(r, 1, "Perfis já cadastrados nesta empresa").font = Font(bold=True, size=12)
        for p in perfis:
            r += 1
            ws.cell(r, 1, p.get("nome") or "(sem nome)")


def _texto(v) -> str:
    return str(v).strip() if v is not None else ""


def _ativo_de(celula) -> bool:
    s = _texto(celula).lower()
    return s not in ("não", "nao", "n", "não.", "0", "false")


def importar_xlsx(caminho, perfis: list, identificacao_padrao_empresa: str = "documento") -> tuple:
    """Lê a planilha modelo (ou qualquer .xlsx com essas colunas, em qualquer ordem, pelo cabeçalho
    da primeira linha com essas colunas — procura a aba certa mesmo que não seja a primeira).
    Devolve (tomadores, erros); erros aponta a linha (1-based, contando o cabeçalho) de quem não
    pôde virar tomador. Um tomador com perfil não encontrado ainda é importado (usa o perfil padrão
    da empresa), só entra em `erros` como aviso."""
    import openpyxl
    import zipfile

    try:
        wb = openpyxl.load_workbook(caminho, data_only=True)
    except (OSError, KeyError, zipfile.BadZipFile) as e:
        raise ErroAdge(f"Não consegui abrir a planilha: {e}") from e
    ws = _aba_de_tomadores(wb)
    if ws is None:
        raise ErroAdge('Não encontrei uma aba com as colunas "Nome" e "Documento (CPF ou CNPJ)" nesta planilha.')
    linhas = list(ws.iter_rows(values_only=True))
    cabecalho = [_texto(c).lower() for c in linhas[0]]

    def col(*nomes):
        for n in nomes:
            if n in cabecalho:
                return cabecalho.index(n)
        return None

    idx = {
        "nome": col("nome"),
        "documento": col("documento (cpf ou cnpj)", "documento", "cpf/cnpj", "cpf ou cnpj"),
        "identificacao": col("identificação na nota", "identificacao na nota", "identificação", "identificacao"),
        "perfil_nome": col("perfil de serviço (nome, opcional)", "perfil de serviço", "perfil de servico", "perfil"),
        "cep": col("cep"),
        "logradouro": col("logradouro"),
        "numero": col("número", "numero"),
        "complemento": col("complemento"),
        "bairro": col("bairro"),
        "municipio": col("município", "municipio"),
        "uf": col("uf"),
        "ibge": col("código ibge do município", "codigo ibge do municipio", "código ibge", "codigo ibge"),
        "endereco_livre": col("endereço (texto livre, opcional)", "endereco (texto livre, opcional)", "endereço livre", "endereco livre"),
        "descricao": col("descrição para este tomador (opcional)", "descricao para este tomador (opcional)", "descrição", "descricao"),
        "info": col("informações complementares (opcional)", "informacoes complementares (opcional)",
                     "informações complementares", "informacoes complementares"),
        "ativo": col("ativo (sim/não)", "ativo (sim/nao)", "ativo"),
    }

    def celula(linha, campo):
        i = idx[campo]
        return linha[i] if i is not None and i < len(linha) else None

    nomes_perfis = {(p.get("nome") or "").strip().lower(): p["id"] for p in perfis}

    tomadores, erros = [], []
    for n, linha in enumerate(linhas[1:], start=2):
        if all(v in (None, "") for v in linha):
            continue
        nome = _texto(celula(linha, "nome"))
        if not nome:
            erros.append(f"Linha {n}: sem nome, ignorada")
            continue
        doc = _texto(celula(linha, "documento"))
        endereco = {
            "cep": _texto(celula(linha, "cep")), "logradouro": _texto(celula(linha, "logradouro")),
            "numero": _texto(celula(linha, "numero")), "complemento": _texto(celula(linha, "complemento")),
            "bairro": _texto(celula(linha, "bairro")), "municipio": _texto(celula(linha, "municipio")),
            "uf": _texto(celula(linha, "uf")).upper(), "codigo_municipio_ibge": _texto(celula(linha, "ibge")),
        }
        tem_endereco = bool(endereco["logradouro"] and endereco["municipio"])
        modo_txt = _texto(celula(linha, "identificacao"))
        modo = _PLANILHA_IDENTIFICACAO.get(modo_txt, "herdar")
        modo_efetivo = modo if modo != "herdar" else identificacao_padrao_empresa
        if not doc and not tem_endereco:
            erros.append(f"Linha {n} ({nome}): sem documento e sem endereço completo, ignorada "
                          "— é por aí que a nota reconhece o tomador.")
            continue
        if modo_efetivo == "endereco" and not tem_endereco:
            erros.append(f"Linha {n} ({nome}): identificação exige endereço completo, mas faltou "
                          "logradouro ou município, ignorada.")
            continue
        perfil_nome = _texto(celula(linha, "perfil_nome"))
        perfil_id = None
        if perfil_nome:
            perfil_id = nomes_perfis.get(perfil_nome.lower())
            if perfil_id is None:
                erros.append(f"Linha {n} ({nome}): perfil \"{perfil_nome}\" não encontrado, "
                              "importado com o perfil padrão da empresa.")
        descricao_txt = _texto(celula(linha, "descricao"))
        info_txt = _texto(celula(linha, "info"))
        tomador = {
            **es.tomador_padrao(nome), "documento": doc, "modo_identificacao": modo,
            "endereco": endereco, "endereco_livre": _texto(celula(linha, "endereco_livre")),
            "perfil_id": perfil_id, "ativo": _ativo_de(celula(linha, "ativo")),
            "descricao": {"modo": "fixo", "texto": descricao_txt} if descricao_txt else {"modo": "herdar", "texto": ""},
            "informacoes_complementares": {"modo": "fixo", "texto": info_txt} if info_txt else {"modo": "herdar", "texto": ""},
        }
        tomadores.append(tomador)
    return tomadores, erros


def _aba_de_tomadores(wb):
    for ws in wb.worksheets:
        primeira = next(ws.iter_rows(min_row=1, max_row=1, values_only=True), None)
        if not primeira:
            continue
        cabecalho = [_texto(c).lower() for c in primeira]
        if "nome" in cabecalho and any(c.startswith("documento") for c in cabecalho):
            return ws
    return None
