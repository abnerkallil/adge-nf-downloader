"""Casamento do lançamento com os tomadores cadastrados (`empresa["emissao"]["tomadores"]`).
Delega para `config_schema.encontrar_tomador` (schema final do Dev A, PR #2) em vez de duplicar a
lógica de normalização/prioridade aqui — documento > nome > endereço, a mesma regra combinada na
thread "Criar tela de configuração de emissão na V2.0"."""
from __future__ import annotations

from . import config_schema as es


def casar_tomador(lancamento, empresa_emissao: dict) -> dict | None:
    """Devolve o tomador cadastrado que casa com o lançamento, ou None."""
    return es.encontrar_tomador(empresa_emissao or {}, documento=lancamento.tomador_documento,
                                 nome=lancamento.tomador_nome, endereco=lancamento.endereco)


def tomador_de_lancamento(lancamento, perfil_id: str) -> dict:
    """Monta um novo registro de `tomadores` a partir de um lançamento confirmado na prévia,
    pronto para `Armazenamento.salvar_empresa`. Usa `endereco_livre` para o texto do lançamento
    (o cadastro não tem como separar logradouro/número/bairro de um texto livre) e
    `modo_identificacao="endereco"` quando houver endereço, para a nota levar o endereço completo
    (ex.: locação de imóvel) — "herdar" ficaria ambíguo, já que o padrão da empresa pode ser outro."""
    novo = es.tomador_padrao(lancamento.tomador_nome.strip())
    novo["documento"] = lancamento.tomador_documento
    novo["endereco_livre"] = lancamento.endereco.strip()
    novo["modo_identificacao"] = "endereco" if lancamento.endereco.strip() else "documento"
    novo["perfil_id"] = perfil_id
    return novo
