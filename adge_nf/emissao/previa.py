"""Tela de prévia/conferência: liga cada lançamento a um perfil de serviço antes de qualquer
transmissão. Primeiro tenta casar um tomador cadastrado (`regras.casar_tomador`); sem casamento,
fica pendente até o usuário escolher um perfil na tela (e pode salvar a escolha como regra)."""
from __future__ import annotations

from dataclasses import dataclass, field

from . import regras

PRONTO, PRECISA_PERFIL, EXCLUIDO = "pronto", "precisa_perfil", "excluido"


@dataclass
class ItemPrevia:
    lancamento: object
    tomador: dict = None
    perfil_id: str = None
    status: str = PRECISA_PERFIL
    erros: list = field(default_factory=list)


def perfis_ativos(empresa_emissao: dict) -> list:
    return [p for p in (empresa_emissao or {}).get("perfis", []) if p.get("ativo", True)]


def _perfil_existe(empresa_emissao: dict, perfil_id: str) -> bool:
    return any(p["id"] == perfil_id for p in perfis_ativos(empresa_emissao))


def _status_de(item: ItemPrevia, empresa_emissao: dict) -> str:
    if item.lancamento.excluir:
        return EXCLUIDO
    item.erros = item.lancamento.validar()
    if item.erros:
        return PRECISA_PERFIL
    if not item.perfil_id or not _perfil_existe(empresa_emissao, item.perfil_id):
        return PRECISA_PERFIL
    return PRONTO


def preparar_previa(empresa_emissao: dict, lancamentos: list) -> list:
    """Um `ItemPrevia` por lançamento, já com o tomador casado (se houver) e o status inicial."""
    itens = []
    for lanc in lancamentos:
        tomador = None if lanc.excluir else regras.casar_tomador(lanc, (empresa_emissao or {}).get("tomadores", []))
        # só aplica o perfil sem perguntar quando um tomador cadastrado casou; sem casamento, o
        # perfil padrão da empresa NÃO é usado sozinho (Abner: "perguntar só quando nenhuma regra casar")
        perfil_id = tomador["perfil_id"] if tomador else None
        item = ItemPrevia(lancamento=lanc, tomador=tomador, perfil_id=perfil_id)
        item.status = _status_de(item, empresa_emissao)
        itens.append(item)
    return itens


def aplicar_perfil(item: ItemPrevia, perfil_id: str, empresa_emissao: dict, salvar_regra: bool = False) -> dict:
    """Define o perfil escolhido na tela para este lançamento. Com `salvar_regra=True`, devolve o
    novo registro de `tomadores` para o chamador acrescentar à configuração e persistir
    (esta função não grava nada sozinha); sem isso devolve None."""
    item.perfil_id = perfil_id
    item.status = _status_de(item, empresa_emissao)
    if not salvar_regra:
        return None
    novo_tomador = regras.tomador_de_lancamento(item.lancamento, perfil_id)
    item.tomador = novo_tomador
    return novo_tomador


def excluir(item: ItemPrevia, motivo: str = ""):
    item.lancamento.excluir = True
    item.lancamento.motivo_exclusao = motivo or item.lancamento.motivo_exclusao
    item.status = EXCLUIDO


def prontos_para_transmitir(itens: list) -> list:
    return [i for i in itens if i.status == PRONTO]
