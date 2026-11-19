"""Envio da DPS por nota ao ADN (`POST /nfse`) e tratamento de erro: nota com erro fica pendente
(registrada no histórico com `status="pendente"` e o motivo) e as outras seguem, igual ao
comportamento que o Downloader já tem para lotes de NSU. Transmissão real **desligada por
padrão** - só liga quando o Abner confirmar em produção restrita.

Ainda não implementada: falta o endpoint/payload exatos de `POST /nfse` (pesquisa em andamento) e
`assinatura.assinar_dps`. O contrato (uma chamada por nota, devolvendo sucesso ou erro recuperável)
já fica fixado para a tela de prévia e o histórico poderem ser construídos em cima dele agora."""
from __future__ import annotations

from dataclasses import dataclass

AMBIENTE_RESTRITO = "https://adn.producaorestrita.nfse.gov.br/contribuintes"
AMBIENTE_PRODUCAO = "https://adn.nfse.gov.br/contribuintes"

PRODUCAO_REAL_LIBERADA = False  # trava de segurança: só o Abner muda isto, e só depois de testar


@dataclass
class ResultadoTransmissao:
    sucesso: bool
    numero: str = ""
    chave: str = ""
    xml_retorno: str = ""
    erro: str = ""


def enviar(xml_assinado: str, sessao, ambiente: str = AMBIENTE_RESTRITO) -> ResultadoTransmissao:
    """Envia uma DPS já assinada. `sessao`: a mesma sessão com certificado de
    `core.sessao_com_certificado` (mTLS), para reaproveitar o canal já usado na busca."""
    raise NotImplementedError(
        "Envio ao ADN (POST /nfse) ainda não implementado - aguardando o payload/resposta exatos "
        'da thread de pesquisa "Pesquisar campos e API da NFS-e Nacional".')


def ambiente_ativo() -> str:
    return AMBIENTE_PRODUCAO if PRODUCAO_REAL_LIBERADA else AMBIENTE_RESTRITO
