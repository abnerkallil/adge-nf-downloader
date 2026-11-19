"""Nome e gravação do XML de uma nota emitida, no mesmo padrão do Downloader (mesma pasta,
mesma regra de nome e de não sobrescrever — reaproveita `core.nome_xml`/`core.gravar`, trocando
só o `vem_de`: aqui é o que a nota devolveu, em vez do que o ADN entregou numa busca)."""
from __future__ import annotations

from pathlib import Path

from .. import core


def _ultimo_dia_da_competencia(competencia: str) -> str:
    ano, mes = int(competencia[:4]), int(competencia[5:7])
    return core.limites_mes(ano, mes)[1].isoformat()


def doc_para_nome(empresa: dict, lancamento, numero: str = "", chave: str = "") -> dict:
    """Monta o dict que `core.nome_xml`/`core.montar_nome` esperam, a partir da empresa e do
    lançamento. `numero`/`chave`: devolvidos pela API na transmissão (vazios antes disso)."""
    return {
        "emitente_nome": empresa.get("nome", ""),
        "emitente_doc": "".join(c for c in empresa.get("cnpj", "") if c.isdigit()),
        "tomador_nome": lancamento.tomador_nome,
        "tomador_doc": lancamento.tomador_documento,
        "emissao": lancamento.data_prestacao or _ultimo_dia_da_competencia(lancamento.competencia),
        "valor": lancamento.valor,
        "numero": numero,
        "chave": chave,
    }


def nome_xml(empresa: dict, lancamento, numero: str = "", chave: str = "") -> str:
    prefixos = core.prefixos_da_empresa(empresa)
    return core.nome_xml("servico_prestado", doc_para_nome(empresa, lancamento, numero, chave), prefixos)


def salvar_xml_emitido(empresa: dict, lancamento, xml: str, ano: int = None, mes: int = None,
                       numero: str = "", chave: str = "") -> tuple:
    """Grava o XML retornado pela transmissão na pasta da empresa (mesma estrutura/ano/mês das
    notas baixadas). Devolve (caminho_do_arquivo, status) — status é "gravado", "renomeado" ou
    "ja_existia" (ver `core.gravar`)."""
    if ano is None or mes is None:
        ano, mes = int(lancamento.competencia[:4]), int(lancamento.competencia[5:7])
    destino, _ = core.resolver_destino(Path(empresa["destino"]), empresa.get("estrutura", "adge"), ano, mes, criar=True)
    nome = nome_xml(empresa, lancamento, numero, chave)
    arquivo, status = core.gravar(destino, nome, xml)
    return destino / arquivo, status
