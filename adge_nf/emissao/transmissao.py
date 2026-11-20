"""Envio da DPS assinada ao Sefin Nacional (`POST /nfse`) e tratamento de erro: nota com erro fica
pendente (quem chama grava `status="pendente"` no histórico, com o motivo) e as outras seguem,
igual ao comportamento que o Downloader já tem para lotes de NSU — uma chamada por nota, devolvendo
sucesso ou erro recuperável, nunca levantando por uma nota ruim sozinha.

Host/recursos confirmados em 20/11/2026 contra o manual oficial ("Manual dos Contribuintes -
Sistema Nacional NFS-e: Guia para utilização das API's do Emissor Público Nacional", v1.0,
17/03/2025, gov.br/nfse/.../documentacao-tecnica/documentacao-atual) — seção 1.3.2:
- `POST /nfse`: "Geração SÍNCRONA de NFS-e" — a resposta do próprio POST já vem com a NFS-e gerada
  ou o erro de rejeição (não precisa consultar depois, exceto se a conexão cair no meio).
- `GET /nfse/{chaveAcesso}`: consulta por chave de acesso.
- `GET/HEAD /dps/{id}`: recupera a chave de acesso a partir do identificador da DPS (útil quando a
  conexão cai e não dá pra saber se a nota foi gerada — ver `consultar_por_identificador_dps`).
- Seção 1.6: existe um ambiente de PRODUÇÃO RESTRITA/homologação separado para este lado (emissão),
  `sefin.producaorestrita.nfse.gov.br` — a pesquisa anterior achou só o de distribuição
  (`adn.producaorestrita.nfse.gov.br`, outra API) e concluiu (errado) que não havia homologação
  para emissão.

NÃO confirmado contra o manual oficial (ele não dá o schema exato do corpo/resposta) — a Swagger
oficial (`adn.producaorestrita.nfse.gov.br/contribuintes/docs/index.html`) devolve erro de TLS sem
certificado mTLS válido, então só dá pra confirmar com o certificado real do cliente, testando
primeiro no ambiente de homologação abaixo. Implementado aqui pela convergência de três fontes
independentes (biblioteca ACBr, usada pela maioria dos ERPs fiscais do Brasil; documentação da
Macroflex; e o projeto heviane/nfse-nacional-api no GitHub, spec 0002): corpo JSON
`{"dpsXmlGZipB64": "<base64 do gzip do XML assinado>"}`, resposta de sucesso HTTP 200 com
`{"codigoStatus": 100, "chaveAcesso": "...", "nfseXmlGZipB64": "<base64 do gzip do XML da NFS-e>"}`.
**Ajustar aqui se o primeiro envio de teste (com o Abner acompanhando) mostrar outro formato.**"""
from __future__ import annotations

import base64
import gzip
from dataclasses import dataclass

from ..core import ErroAdge

HOST_SEFIN_PRODUCAO = "https://sefin.nfse.gov.br/API/SefinNacional"
HOST_SEFIN_HOMOLOGACAO = "https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional"

TP_AMB_PRODUCAO, TP_AMB_HOMOLOGACAO = "1", "2"

PRODUCAO_REAL_LIBERADA = False  # trava de segurança: só o Abner muda isto, e só depois de testar em homologação


def _host(tp_amb: str) -> str:
    return HOST_SEFIN_PRODUCAO if tp_amb == TP_AMB_PRODUCAO else HOST_SEFIN_HOMOLOGACAO


@dataclass
class ResultadoTransmissao:
    sucesso: bool
    numero: str = ""
    chave: str = ""
    xml_retorno: str = ""
    erro: str = ""


def _compactar(xml: str) -> str:
    """gzip + base64 — o inverso de `_descompactar`."""
    return base64.b64encode(gzip.compress(xml.encode("utf-8"))).decode("ascii")


def _descompactar(texto_b64: str) -> str:
    return gzip.decompress(base64.b64decode(texto_b64)).decode("utf-8")


def enviar(xml_assinado: str, sessao, tp_amb: str = TP_AMB_HOMOLOGACAO) -> ResultadoTransmissao:
    """Envia uma DPS já assinada (`assinatura.assinar_dps`). `sessao`: a mesma sessão com
    certificado de `core.sessao_com_certificado` (mTLS, montado em todo `https://`). `tp_amb` deve
    bater com o `tpAmb` já escrito dentro do XML (`TP_AMB_HOMOLOGACAO` por padrão, único ambiente
    testável antes do Abner liberar produção); `TP_AMB_PRODUCAO` só é aceito se
    `PRODUCAO_REAL_LIBERADA` estiver True. Nunca levanta por erro de negócio/rede — devolve
    `ResultadoTransmissao(sucesso=False, erro=...)` para a nota ficar pendente e as outras seguirem;
    só levanta `ErroAdge` para a trava de produção, que é erro de configuração, não de nota.
    Se a conexão cair sem resposta clara, o erro recomenda conferir com `ja_foi_gerada` antes de
    reenviar (síncrono: reenviar sem checar pode gerar NFS-e duplicada)."""
    if tp_amb == TP_AMB_PRODUCAO and not PRODUCAO_REAL_LIBERADA:
        raise ErroAdge(
            "Transmissão em produção real está desligada (PRODUCAO_REAL_LIBERADA=False). "
            "Só o Abner libera isso, depois de testar em homologação/produção restrita.")
    try:
        resp = sessao.post(f"{_host(tp_amb)}/nfse", json={"dpsXmlGZipB64": _compactar(xml_assinado)},
                            headers={"Content-Type": "application/json; charset=utf-8", "Accept": "application/json"},
                            timeout=90)
    except Exception as e:  # rede fora, certificado recusado no handshake, timeout etc.
        return ResultadoTransmissao(
            sucesso=False,
            erro=f"Conexão interrompida, verificar: não deu pra confirmar se a nota foi gerada ({e}). "
                 "Consulte pela chave/identificador da DPS antes de tentar transmitir de novo.")
    if resp.status_code not in (200, 201):
        return ResultadoTransmissao(sucesso=False,
                                     erro=f"Sefin Nacional recusou (HTTP {resp.status_code}): {resp.text[:1000]}")
    try:
        corpo = resp.json()
        xml_nfse = _descompactar(corpo["nfseXmlGZipB64"])
    except Exception as e:
        return ResultadoTransmissao(sucesso=False, erro=f"Resposta do Sefin Nacional em formato inesperado: {e}")
    from .. import core
    try:
        dados = core.parse_documento(xml_nfse)
    except Exception:
        dados = {}
    return ResultadoTransmissao(sucesso=True, numero=dados.get("numero", ""),
                                 chave=dados.get("chave") or corpo.get("chaveAcesso", ""), xml_retorno=xml_nfse)


def consultar_por_chave(chave_acesso: str, sessao, tp_amb: str = TP_AMB_HOMOLOGACAO) -> ResultadoTransmissao:
    """`GET /nfse/{chaveAcesso}` — usada para confirmar se uma nota já foi gerada antes de
    retransmitir (ex.: depois de "conexão interrompida, verificar")."""
    try:
        resp = sessao.get(f"{_host(tp_amb)}/nfse/{chave_acesso}", timeout=60)
    except Exception as e:
        return ResultadoTransmissao(sucesso=False, erro=f"Não consegui consultar o Sefin Nacional: {e}")
    if resp.status_code == 404:
        return ResultadoTransmissao(sucesso=False, erro="Nenhuma NFS-e encontrada com esta chave.")
    if resp.status_code != 200:
        return ResultadoTransmissao(sucesso=False, erro=f"Sefin Nacional recusou a consulta (HTTP {resp.status_code}): {resp.text[:500]}")
    try:
        corpo = resp.json()
        xml_nfse = _descompactar(corpo["nfseXmlGZipB64"])
    except Exception as e:
        return ResultadoTransmissao(sucesso=False, erro=f"Resposta de consulta em formato inesperado: {e}")
    from .. import core
    try:
        dados = core.parse_documento(xml_nfse)
    except Exception:
        dados = {}
    return ResultadoTransmissao(sucesso=True, numero=dados.get("numero", ""), chave=chave_acesso, xml_retorno=xml_nfse)


def ambiente_ativo() -> str:
    return TP_AMB_PRODUCAO if PRODUCAO_REAL_LIBERADA else TP_AMB_HOMOLOGACAO


def cancelar(xml_pedregevt_assinado: str, chave_acesso: str, sessao, tp_amb: str = TP_AMB_HOMOLOGACAO) -> ResultadoTransmissao:
    """`POST /nfse/{chaveAcesso}/eventos` (seção 1.5 "API Eventos" do manual oficial, ver
    `eventos.montar_cancelamento_xml`). Mesma trava de produção e mesmo tratamento de erro de
    `enviar` — nunca levanta por erro de negócio/rede."""
    if tp_amb == TP_AMB_PRODUCAO and not PRODUCAO_REAL_LIBERADA:
        raise ErroAdge(
            "Transmissão em produção real está desligada (PRODUCAO_REAL_LIBERADA=False). "
            "Só o Abner libera isso, depois de testar em homologação/produção restrita.")
    try:
        resp = sessao.post(f"{_host(tp_amb)}/nfse/{chave_acesso}/eventos",
                            json={"pedidoRegistroEventoXmlGZipB64": _compactar(xml_pedregevt_assinado)},
                            headers={"Content-Type": "application/json; charset=utf-8", "Accept": "application/json"},
                            timeout=90)
    except Exception as e:
        return ResultadoTransmissao(
            sucesso=False,
            erro=f"Conexão interrompida, verificar: não deu pra confirmar se o cancelamento foi registrado ({e}). "
                 "Consulte os eventos desta chave antes de tentar de novo.")
    if resp.status_code not in (200, 201):
        return ResultadoTransmissao(sucesso=False,
                                     erro=f"Sefin Nacional recusou o cancelamento (HTTP {resp.status_code}): {resp.text[:1000]}")
    return ResultadoTransmissao(sucesso=True, chave=chave_acesso)
