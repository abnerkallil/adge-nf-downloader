"""Assinatura XML (enveloped signature, XML-DSig) da DPS com o certificado A1 da empresa, do
mesmo jeito que `core.sessao_com_certificado`/`core.ler_certificado` já abrem o .pfx para a
consulta. Ainda não implementada: falta confirmar, na pesquisa da API, se a DPS pede assinatura
própria além do mTLS da conexão (ver memória do projeto - "não confirmado se a DPS em si precisa
de assinatura XML própria"). O contrato já fica fixado para não travar `transmissao.py`."""
from __future__ import annotations

from ..core import ErroAdge


def assinar_dps(xml: str, pfx: str, senha: str) -> str:
    """Devolve o XML da DPS com a assinatura embutida, pronta para `transmissao.enviar`."""
    raise NotImplementedError(
        "Assinatura da DPS ainda não implementada - falta confirmar, na pesquisa da API, se a "
        "DPS exige assinatura XML própria além do certificado da conexão (mTLS).")
