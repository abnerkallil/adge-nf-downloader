"""Casamento do lançamento com os tomadores cadastrados (`empresa["emissao"]["tomadores"]`,
schema do Dev A). Prioridade documento > nome normalizado > endereço normalizado; campo em
branco no tomador não entra no casamento por esse critério (contrato combinado na thread
"Criar tela de configuração de emissão na V2.0")."""
from __future__ import annotations

import re

from ..core import norm


def _so_digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def casar_tomador(lancamento, tomadores: list) -> dict | None:
    """Devolve o tomador cadastrado que casa com o lançamento, ou None. `tomadores` já filtrados
    por empresa; tomadores inativos (`ativo` False) são ignorados."""
    ativos = [t for t in (tomadores or []) if t.get("ativo", True)]
    doc_lanc = _so_digitos(lancamento.tomador_documento)
    if doc_lanc:
        for t in ativos:
            doc_t = _so_digitos(t.get("documento", ""))
            if doc_t and doc_t == doc_lanc:
                return t
    nome_lanc = norm(lancamento.tomador_nome)
    if nome_lanc:
        for t in ativos:
            nome_t = norm(t.get("nome", ""))
            if nome_t and nome_t == nome_lanc:
                return t
    end_lanc = norm(lancamento.endereco)
    if end_lanc:
        for t in ativos:
            end_t = norm(t.get("endereco", ""))
            if end_t and end_t == end_lanc:
                return t
    return None


def tomador_de_lancamento(lancamento, perfil_id: str, id_: str = None) -> dict:
    """Monta um novo registro de `tomadores` a partir de um lançamento confirmado na prévia,
    pronto para `Armazenamento.salvar_empresa` (quem gera o `id` definitivo é o config_schema;
    aqui fica um palpite para uso imediato na tela)."""
    import uuid
    return {
        "id": id_ or uuid.uuid4().hex[:12],
        "nome": lancamento.tomador_nome.strip(),
        "documento": lancamento.tomador_documento,
        "endereco": lancamento.endereco.strip(),
        "perfil_id": perfil_id,
        "descricao": {"modo": "herdar"},
        "informacoes_complementares": {"modo": "herdar"},
        "ativo": True,
    }
