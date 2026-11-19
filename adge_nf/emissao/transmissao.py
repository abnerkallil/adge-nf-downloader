"""Envio da DPS assinada ao Sefin Nacional (`POST /nfse`) e tratamento de erro: nota com erro fica
pendente (quem chama grava `status="pendente"` no histórico, com o motivo) e as outras seguem,
igual ao comportamento que o Downloader já tem para lotes de NSU — uma chamada por nota, devolvendo
sucesso ou erro recuperável, nunca levantando por uma nota ruim sozinha.

Host/recurso confirmados pela pesquisa (`api-emissao.md`, duas fontes independentes: notícia
oficial de 31/10/2026 e o Guia do Emissor Web): `sefin.nfse.gov.br/SefinNacional`, recurso `/nfse`
(POST emite, GET consulta por chave de acesso) — **diferente** do host usado para baixar notas
(`adn.nfse.gov.br/contribuintes`, distribuição de DF-e, outra API).

NÃO confirmado, mesmo após tentar (ver abaixo) — ajustar aqui quando o Abner testar com certificado
de verdade, antes de ligar `PRODUCAO_REAL_LIBERADA`:
- Prefixo de versão no path, se houver, além de `/nfse`.
- Formato exato do corpo do POST: a pesquisa só confirma "assinar → compactar (gzip) → codificar em
  base64 → mandar no corpo do POST", sem mostrar o esquema JSON da chamada. Implementado aqui como
  o texto base64 puro no corpo (`Content-Type: text/plain`), a leitura mais literal dessa frase —
  **pode estar errado**; a documentação interativa (Swagger, `docs/index#operation/NFSe_Post`)
  resolveria isso, mas todas as rotas do host (até `/docs`) devolvem 403 sem certificado mTLS válido
  (testado em 19/11/2026 - é a "validação do certificado de transmissão" da RN_RECEPCAO_DPS,
  que roda antes de qualquer coisa), então só dá pra confirmar com o certificado real do cliente.
- Formato da resposta de sucesso: assumido como o XML da NFS-e em texto puro (não compactado) —
  a pesquisa não confirmou se a resposta também vem em base64/gzip.

Ambiente: a pesquisa não achou um host de homologação separado para o lado de emissão (só achou
um para o lado de distribuição, `adn.producaorestrita.nfse.gov.br`, host diferente). Por isso o
ambiente aqui é controlado pelo campo `tpAmb` DENTRO da DPS (`dps.montar_xml(..., ambiente=...)`),
não por uma URL diferente. `PRODUCAO_REAL_LIBERADA` é a trava de segurança: enquanto for False,
`enviar()` recusa `tp_amb="1"` mesmo que o XML já esteja marcado como produção."""
from __future__ import annotations

import base64
import gzip
from dataclasses import dataclass

from ..core import ErroAdge

HOST_SEFIN = "https://sefin.nfse.gov.br/SefinNacional"
RECURSO_NFSE = f"{HOST_SEFIN}/nfse"

TP_AMB_PRODUCAO, TP_AMB_HOMOLOGACAO = "1", "2"

PRODUCAO_REAL_LIBERADA = False  # trava de segurança: só o Abner muda isto, e só depois de testar


@dataclass
class ResultadoTransmissao:
    sucesso: bool
    numero: str = ""
    chave: str = ""
    xml_retorno: str = ""
    erro: str = ""


def _compactar(xml_assinado: str) -> str:
    """Assinar -> compactar (gzip) -> codificar em base64 — o inverso de `core.decodificar_arquivo`
    (`gzip.decompress(base64.b64decode(...))`), confirmado pela RN_RECEPCAO_DPS em `api-emissao.md`."""
    return base64.b64encode(gzip.compress(xml_assinado.encode("utf-8"))).decode("ascii")


def enviar(xml_assinado: str, sessao, tp_amb: str = TP_AMB_HOMOLOGACAO) -> ResultadoTransmissao:
    """Envia uma DPS já assinada (`assinatura.assinar_dps`). `sessao`: a mesma sessão com
    certificado de `core.sessao_com_certificado` (mTLS, montado em todo `https://`). `tp_amb` deve
    bater com o `tpAmb` já escrito dentro do XML (`TP_AMB_HOMOLOGACAO` por padrão); `TP_AMB_PRODUCAO`
    só é aceito se `PRODUCAO_REAL_LIBERADA` estiver True. Nunca levanta por erro de negócio/rede —
    devolve `ResultadoTransmissao(sucesso=False, erro=...)` para a nota ficar pendente e as outras
    seguirem; só levanta `ErroAdge` para a trava de produção, que é erro de configuração, não de nota."""
    if tp_amb == TP_AMB_PRODUCAO and not PRODUCAO_REAL_LIBERADA:
        raise ErroAdge(
            "Transmissão em produção real está desligada (PRODUCAO_REAL_LIBERADA=False). "
            "Só o Abner libera isso, depois de testar em homologação/produção restrita.")
    try:
        resp = sessao.post(RECURSO_NFSE, data=_compactar(xml_assinado),
                            headers={"Content-Type": "text/plain"}, timeout=90)
    except Exception as e:  # rede fora, certificado recusado no handshake etc.
        return ResultadoTransmissao(sucesso=False, erro=f"Não consegui falar com o Sefin Nacional: {e}")
    if resp.status_code not in (200, 201):
        return ResultadoTransmissao(sucesso=False,
                                     erro=f"Sefin Nacional recusou (HTTP {resp.status_code}): {resp.text[:1000]}")
    from .. import core
    try:
        dados = core.parse_documento(resp.text)
    except Exception:
        dados = {}
    return ResultadoTransmissao(sucesso=True, numero=dados.get("numero", ""),
                                 chave=dados.get("chave", ""), xml_retorno=resp.text)


def ambiente_ativo() -> str:
    return TP_AMB_PRODUCAO if PRODUCAO_REAL_LIBERADA else TP_AMB_HOMOLOGACAO
