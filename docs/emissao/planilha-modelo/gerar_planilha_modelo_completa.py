"""Gera a planilha modelo COMPLETA de lançamentos para emissão de notas: a mesma aba que
`adge_nf.emissao.planilha_emissao` gera/importa (para nunca divergir do motor), mais uma coluna
"Conferir" (só para revisão humana, ignorada na importação) e duas abas de apoio: "Instruções" e
"Exemplo". Rode com `python gerar_planilha_modelo_completa.py` a partir desta pasta.

Por quê um gerador à parte em vez de só chamar `gerar_modelo_xlsx`: aquela função cuida só da
aba "Lançamentos" que o motor importa de volta (não pode fugir dali, senão desalinha do
importador). As abas "Instruções" e "Exemplo" são só para quem preenche a planilha (Claude ou o
Abner), então ficam num gerador separado, por cima do modelo oficial.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from adge_nf.emissao import planilha_emissao as pe  # noqa: E402

COLUNA_CONFERIR = "Conferir (preenchido por quem transcreveu; não é lido pelo sistema)"

# Texto de ajuda por coluna. Casa pelo texto exato do cabeçalho que `planilha_emissao.COLUNAS`
# define hoje; uma coluna nova que o motor adicionar e não estiver aqui ainda aparece na planilha
# (gerada a partir de COLUNAS, nunca hardcoded) só sem explicação detalhada — sinal de que este
# texto precisa de atualização.
AJUDA_COLUNAS = {
    "Tomador (nome)": "Obrigatório. Nome completo (pessoa física) ou razão social (pessoa jurídica) de quem recebeu o serviço.",
    "Documento (CPF ou CNPJ)": "Obrigatório. CPF (11 dígitos) ou CNPJ (14 dígitos) do tomador. Pode digitar com ou sem pontuação.",
    "Endereço": "Opcional. Endereço completo do tomador ou do imóvel do serviço, quando o documento de origem trouxer.",
    "Valor": "Obrigatório. Valor do serviço, em reais. Notas com valor 0 (ou não pago) ficam marcadas para excluir automaticamente — não pular a linha, só preencher 0 e explicar em Observações.",
    "Competência (AAAA-MM)": "Mês de referência da nota (ex.: 2026-11). Pode deixar em branco se preencher a Data da prestação: o sistema completa pelo mês dela.",
    "Data da prestação (AAAA-MM-DD, opcional)": "Opcional. Data exata do serviço. Em branco, o sistema usa o último dia da competência.",
    "Perfil de serviço (nome, opcional)": (
        "Opcional. Nome do perfil de serviço já cadastrado na empresa (ex.: \"Locação residencial\" x "
        "\"Locação não residencial\"), quando a empresa tiver mais de um e o documento de origem permitir "
        "saber qual se aplica a essa nota. Em branco, o sistema tenta casar pelo tomador cadastrado e, se "
        "não achar, pergunta na tela antes de emitir — não é obrigatório preencher aqui."
    ),
    "Observações": "Texto livre: motivo de não ter pago, dúvida sobre o lançamento, ou qualquer informação que não caiba nas outras colunas.",
}

LEGENDA_CONFERIR = (
    "Preenchida por quem transcreveu (Claude ou você mesmo) sempre que um dado não veio claro do "
    "documento de origem e teve que ser deduzido, perguntado ou deixado em branco. Exemplos: "
    '"CPF ilegível no print, confirmar com o tomador"; "Endereço sugere uso comercial (\\"Salão\\"), '
    'assumi não residencial, confirmar"; "Mês não informado no documento, usei a competência que você '
    'passou no chat". Vazio = nada a conferir nessa linha. Essa coluna é só para revisão humana antes '
    "de importar; o sistema não lê ela."
)

EXEMPLO_LINHAS = [
    # Tomador, Documento, Endereço, Valor, Competência, Data, Perfil, Observações, Conferir
    ["Maria da Silva Pereira", "123.456.789-00", "Rua das Acácias, nº 50 - Centro - Londrina - PR",
     1200.00, "2026-11", "", "Locação residencial", "", ""],
    ["João Carlos Oliveira", "987.654.321-00", "Av. Brasil, nº 900, sala 2 - Londrina - PR",
     2500.00, "2026-11", "", "Locação não residencial",
     "Endereço é uma sala comercial", ""],
    ["Comércio Fictício de Roupas LTDA", "12.345.678/0001-90", "", 3400.00, "2026-11", "", "",
     "", "Perfil não informado no documento de origem; empresa só tem 1 perfil cadastrado, então deixei em branco"],
    ["Ana Paula Rodrigues", "111.222.333-44", "Rua Fictícia, nº 10 - Fundos - Londrina - PR",
     0.00, "2026-11", "", "Locação residencial", "Não conseguiu pagar em novembro", ""],
    ["Pedro Henrique Souza", "", "Rua Fictícia, nº 77", 980.00, "2026-11", "", "",
     "Documento do tomador não veio no print enviado", "CPF/CNPJ ausente - preencher antes de importar"],
]


def _ajuda(coluna: str) -> str:
    return AJUDA_COLUNAS.get(coluna, "")


def gerar(caminho) -> Path:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    caminho = Path(caminho)
    wb = openpyxl.Workbook()

    # --- Aba 1: Instruções -------------------------------------------------
    ws_i = wb.active
    ws_i.title = "Instruções"
    titulo = ws_i.cell(1, 1, "Planilha modelo — Lançamento de notas para emissão (NFS-e Nacional)")
    titulo.font = Font(bold=True, size=14, color="1F9D5B")
    ws_i.cell(2, 1, "Preencha a aba \"Lançamentos\" com uma linha por nota a emitir. A aba \"Exemplo\" mostra o "
                     "preenchimento com dados fictícios.")
    linha = 4
    ws_i.cell(linha, 1, "Colunas da aba \"Lançamentos\"").font = Font(bold=True)
    linha += 1
    for coluna in pe.COLUNAS:
        c = ws_i.cell(linha, 1, coluna)
        c.font = Font(bold=True)
        ws_i.cell(linha, 2, _ajuda(coluna)).alignment = Alignment(wrap_text=True, vertical="top")
        linha += 1
    c = ws_i.cell(linha, 1, COLUNA_CONFERIR)
    c.font = Font(bold=True, color="B45309")
    ws_i.cell(linha, 2, LEGENDA_CONFERIR).alignment = Alignment(wrap_text=True, vertical="top")
    linha += 2

    ws_i.cell(linha, 1, "Pontos importantes").font = Font(bold=True)
    linha += 1
    avisos = [
        "Retenção de PIS/COFINS/CSLL do lote inteiro é perguntada uma vez só, na tela do sistema, "
        "na hora de importar esta planilha — não existe coluna de retenção aqui.",
        "Uma nota com valor 0 (cliente não pagou, por exemplo) deve continuar na planilha com o valor "
        "0 e uma explicação em Observações; o sistema marca essa nota como \"excluir\" sozinho, mas ela "
        "fica registrada e visível na conferência.",
        "Nunca invente dado que não esteja no documento de origem nem tenha sido confirmado por você no "
        "chat. Informação que falta fica em branco e é sinalizada na coluna \"Conferir\".",
        "Quando o perfil de serviço da nota não for óbvio pelo documento (ex.: locação residencial x "
        "não residencial) e a empresa tiver mais de um perfil cadastrado, quem está transcrevendo "
        "pergunta antes de preencher — nunca decide sozinho por suposição.",
    ]
    for aviso in avisos:
        ws_i.cell(linha, 1, f"• {aviso}").alignment = Alignment(wrap_text=True, vertical="top")
        ws_i.merge_cells(start_row=linha, start_column=1, end_row=linha, end_column=2)
        ws_i.row_dimensions[linha].height = 45
        linha += 1
    ws_i.column_dimensions["A"].width = 46
    ws_i.column_dimensions["B"].width = 70

    # --- Aba 2: Lançamentos (igual ao modelo oficial do motor) --------------
    ws_l = wb.create_sheet("Lançamentos")
    colunas_completas = list(pe.COLUNAS) + [COLUNA_CONFERIR]
    for i, nome in enumerate(colunas_completas, 1):
        c = ws_l.cell(1, i, nome)
        c.font = Font(bold=True, color="FFFFFF")
        cor = "1F9D5B" if nome != COLUNA_CONFERIR else "B45309"
        c.fill = PatternFill("solid", fgColor=cor)
        c.alignment = Alignment(horizontal="left", wrap_text=True)
        ws_l.column_dimensions[chr(64 + i)].width = 28
    ws_l.freeze_panes = "A2"
    # validação simples de formato para reduzir erro de digitação (não trava, só avisa)
    idx_competencia = colunas_completas.index("Competência (AAAA-MM)") + 1
    dv_competencia = DataValidation(type="custom", formula1='=OU(J2="",EXATO(J2,TEXTO(J2,"0000-00")))',
                                     showErrorMessage=False)
    try:
        letra = chr(64 + idx_competencia)
        dv_valor = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0",
                                   showErrorMessage=True, errorTitle="Valor inválido",
                                   error="O valor da nota precisa ser 0 ou maior.")
        idx_valor = colunas_completas.index("Valor") + 1
        letra_valor = chr(64 + idx_valor)
        dv_valor.add(f"{letra_valor}2:{letra_valor}5000")
        ws_l.add_data_validation(dv_valor)
    except ValueError:
        pass

    # --- Aba 3: Exemplo (dados fictícios) -----------------------------------
    ws_e = wb.create_sheet("Exemplo")
    for i, nome in enumerate(colunas_completas, 1):
        c = ws_e.cell(1, i, nome)
        c.font = Font(bold=True, color="FFFFFF")
        cor = "1F9D5B" if nome != COLUNA_CONFERIR else "B45309"
        c.fill = PatternFill("solid", fgColor=cor)
        c.alignment = Alignment(horizontal="left", wrap_text=True)
        ws_e.column_dimensions[chr(64 + i)].width = 28
    ws_e.freeze_panes = "A2"
    n_colunas_modelo = len(pe.COLUNAS)
    for lin, valores in enumerate(EXEMPLO_LINHAS, 2):
        for i, v in enumerate(valores[:n_colunas_modelo + 1], 1):
            ws_e.cell(lin, i, v)

    wb.save(caminho)
    return caminho


if __name__ == "__main__":
    destino = Path(__file__).with_name("Planilha Modelo - Emissao de Notas.xlsx")
    gerar(destino)
    print(f"Gerado: {destino}")
