"""Monta os campos da DPS a partir da configuração fixa da empresa (`empresa["emissao"]`,
schema do Dev A), do perfil de serviço escolhido, do tomador casado (se houver) e do
lançamento. `montar_campos` devolve um dict normalizado, não o XML em si: a tag exata de cada
campo depende do leiaute oficial (Anexo I, RN_DPS_NFSe-SNNFSe), que a thread de pesquisa
"Pesquisar campos e API da NFS-e Nacional" ainda está levantando. `montar_xml` fica como ponto
de extensão claro para quando esse mapeamento chegar — propositalmente não implementado ainda,
para não inventar tag."""
from __future__ import annotations

import datetime as dt

from ..core import ErroAdge, limites_mes


def _descricao(perfil: dict, tomador: dict, mes: int, ano: int, aplicar_marcadores) -> str:
    """Prioridade: descrição do tomador (se não for "herdar") > descrição do perfil."""
    desc = (tomador or {}).get("descricao") or {"modo": "herdar"}
    if desc.get("modo") == "herdar" or not desc.get("texto"):
        desc = perfil.get("descricao") or {"modo": "fixo", "texto": ""}
    if desc.get("modo") == "mes_ano":
        if aplicar_marcadores is None:
            raise ErroAdge("Descrição automática por mês/ano pede `aplicar_marcadores` (config_schema do Dev A).")
        return aplicar_marcadores(desc.get("texto", ""), mes, ano)
    return desc.get("texto", "")


def _informacoes_complementares(perfil: dict, tomador: dict) -> str:
    info_tomador = (tomador or {}).get("informacoes_complementares") or {"modo": "herdar"}
    if info_tomador.get("modo") == "fixo" and info_tomador.get("texto"):
        return info_tomador["texto"]
    return perfil.get("informacoes_complementares", "") or ""


def _pis_cofins(empresa_emissao: dict, perfil: dict, valor: float) -> dict:
    """None quando não entra na nota (MEI nunca entra, mesmo que o perfil esteja mal configurado;
    fora isso segue o que o perfil manda)."""
    pc = perfil.get("pis_cofins") or {}
    if empresa_emissao.get("regime") == "mei" or not pc.get("incluir"):
        return None
    aliq_pis, aliq_cofins = pc.get("aliquota_pis", 0.0), pc.get("aliquota_cofins", 0.0)
    return {
        "regime": pc.get("regime", "cumulativo"),
        "cst_pis": pc.get("cst_pis", ""), "cst_cofins": pc.get("cst_cofins", ""),
        "aliquota_pis": aliq_pis, "aliquota_cofins": aliq_cofins,
        "valor_pis": round(valor * aliq_pis / 100, 2), "valor_cofins": round(valor * aliq_cofins / 100, 2),
    }


def montar_campos(empresa: dict, empresa_emissao: dict, perfil: dict, tomador: dict, lancamento,
                  aplicar_marcadores=None) -> dict:
    """`empresa`: cadastro geral (nome, cnpj); `empresa_emissao`: `empresa["emissao"]`; `tomador`:
    registro casado de `empresa_emissao["tomadores"]`, ou None quando a prévia aplicou o perfil
    na mão sem salvar regra. Levanta `ErroAdge` se faltar algo essencial do perfil."""
    if not perfil.get("ctn") or not perfil.get("nbs"):
        raise ErroAdge(f'Perfil "{perfil.get("nome", perfil.get("id"))}" está sem CTN ou NBS configurado.')
    ano, mes = int(lancamento.competencia[:4]), int(lancamento.competencia[5:7])
    data_emissao = lancamento.data_prestacao or limites_mes(ano, mes)[1].isoformat()
    return {
        "prestador": {
            "cnpj": "".join(c for c in empresa.get("cnpj", "") if c.isdigit()),
            "nome": empresa.get("nome", ""),
            "inscricao_municipal": empresa_emissao.get("inscricao_municipal", ""),
            "municipio": empresa_emissao.get("municipio", ""), "uf": empresa_emissao.get("uf", ""),
            "codigo_municipio_ibge": empresa_emissao.get("codigo_municipio_ibge", ""),
            "regime": empresa_emissao.get("regime", ""),
        },
        "tomador": {"nome": lancamento.tomador_nome, "documento": lancamento.tomador_documento,
                    "tipo_documento": lancamento.tipo_documento, "endereco": lancamento.endereco},
        "servico": {
            "ctn": perfil["ctn"], "item_complementar_nbs": perfil.get("item_complementar_nbs", ""),
            "nbs": perfil["nbs"], "tributacao_iss": perfil.get("tributacao_iss") or {},
            "retencao_iss": bool(perfil.get("retencao_iss", False)),
        },
        "valores": {"valor_servico": lancamento.valor, "pis_cofins": _pis_cofins(empresa_emissao, perfil, lancamento.valor)},
        "descricao": _descricao(perfil, tomador, mes, ano, aplicar_marcadores),
        "informacoes_complementares": _informacoes_complementares(perfil, tomador),
        "competencia": lancamento.competencia,
        "data_emissao": data_emissao,
    }


def montar_xml(campos: dict) -> str:
    """Serializa `campos` no XML da DPS (Anexo I / RN_DPS_NFSe-SNNFSe). Ainda não implementado:
    aguardando a lista fechada de tags da thread de pesquisa, para não inventar."""
    raise NotImplementedError(
        "Montagem do XML da DPS ainda não implementada - aguardando o leiaute oficial "
        '(thread "Pesquisar campos e API da NFS-e Nacional"). `montar_campos` já está pronto.')
