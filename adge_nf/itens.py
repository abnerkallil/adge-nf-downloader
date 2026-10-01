"""Catálogo de itens do programa: cada função, tela ou recurso tem um código fixo (ITEM-NN).

O código nunca muda nem é reaproveitado. Ele é usado nos relatórios de atualização (docs/atualizacoes/*.md) e no aviso
de versão nova do programa, sempre no formato "Nome (ITEM-NN)", para ficar fácil saber onde cada mudança aconteceu.
Ao criar uma função nova, acrescente uma linha aqui com o próximo código livre.
"""
import re

CATALOGO = {
    "ITEM-01": "Empresas salvas",
    "ITEM-02": "Certificado A1 e validação",
    "ITEM-03": "Busca de notas por mês",
    "ITEM-04": "Totais do período",
    "ITEM-05": "Saldo líquido",
    "ITEM-06": "Download dos XMLs",
    "ITEM-07": "Organização das pastas",
    "ITEM-08": "Escolher pasta de destino",
    "ITEM-09": "Planilha Excel",
    "ITEM-10": "Informações avançadas",
    "ITEM-11": "Comparativo de regimes",
    "ITEM-12": "Copiar totais",
    "ITEM-13": "Senhas e senha mestra",
    "ITEM-14": "Atualização do programa",
    "ITEM-15": "Apagar dados salvos",
    "ITEM-16": "Relatório do download (.txt)",
    "ITEM-17": "Notas canceladas",
    "ITEM-18": "Novidades no aviso de atualização",
    "ITEM-19": "Boas-vindas da primeira abertura",
    "ITEM-20": "Janela principal e configurações",
}

PADRAO = re.compile(r"^ITEM-\d{2,3}$")


def nome(codigo: str) -> str:
    """Nome do item (ou o próprio código, se ele não existir no catálogo)."""
    return CATALOGO.get(codigo, codigo)


def formatar(codigo: str) -> str:
    """'Informações avançadas (ITEM-10)'."""
    return f"{nome(codigo)} ({codigo})"
