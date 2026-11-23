"""Cancelamento de NFS-e (evento `e101101`). Leiaute confirmado contra o XSD oficial de produção
RESTRITA/homologação (`tests/fixtures/xsd_ibscbs/pedRegEvento_v1.01.xsd` + `tiposEventos_v1.01.xsd`
— ver README em `tests/fixtures/xsd_ibscbs/`) e a API confirmada no manual oficial ("Manual dos
Contribuintes - Sistema Nacional NFS-e", seção 1.5 "API Eventos", `documentacao-atual`, gov.br/nfse):
só o cliente monta e assina o `<pedRegEvento>` (`TCPedRegEvt`: `infPedReg` + `Signature` opcional no
XSD, mas sempre assinado aqui, como a DPS); o `<TCEvento>` completo (com `ambGer`/`nSeqEvento`/
`dhProc`) é gerado pelo SISTEMA depois de aceitar o pedido — não é algo que o emitente constrói.

NÃO confirmado contra o manual oficial (ele não dá o schema exato do envelope JSON) — convergência
de fontes de mercado (mesma base de `transmissao.py`): corpo JSON
`{"pedidoRegistroEventoXmlGZipB64": "<base64 do gzip do XML assinado>"}`, no mesmo recurso
`POST /nfse/{chaveAcesso}/eventos` confirmado pelo manual oficial. **Ajustar no primeiro teste em
homologação, junto com `transmissao.enviar`.**

A construção do atributo `Id` de `infPedReg` (`TSIdPedRegEvt`, regex `PRE[0-9]{8}(1[0-9]{14}|
2[0-9A-Z]{14})[0-9]{33}`) é best-effort a partir da chave de acesso — a anotação do próprio XSD
("chave de acesso completa + tipo + sequencial") não bate em tamanho com o regex dele mesmo
(50+6+3=59 caracteres depois de "PRE", mas o regex só aceita 56); construído aqui batendo com o
regex (que é o que o validador de verdade confere), não com a prosa. Conferir no primeiro teste."""
from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET

from ..core import ErroAdge

NS_EVT = "http://www.sped.fazenda.gov.br/nfse"
VERSAO_LEIAUTE = "1.01"

MOTIVOS_CANCELAMENTO = {
    "1": "Erro na Emissão",
    "2": "Serviço não Prestado",
    "9": "Outros",
}
"""`e101101/cMotivo` (`TSCodJustCanc`)."""


def _so_digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _sub(pai, tag, texto=None, **attrs):
    el = ET.SubElement(pai, tag, attrs)
    if texto is not None:
        el.text = str(texto)
    return el


def _id_pedregevt(chave_acesso: str, tipo_evento: str, n_pedregevento: int) -> str:
    chave = (chave_acesso or "").ljust(50, "0")[:50]
    indicador = chave[8] if len(chave) > 8 and chave[8] in "12" else "1"
    miolo14 = (chave[9:23] or "").ljust(14, "0")[:14]
    resto33 = (str(tipo_evento) + str(n_pedregevento).zfill(3)).zfill(33)[-33:]
    return f"PRE{chave[:8]}{indicador}{miolo14}{resto33}"


def montar_cancelamento_xml(chave_acesso: str, documento_autor: str, motivo_codigo: str, motivo_texto: str, *,
                             tp_amb: str = "2", n_pedregevento: int = 1,
                             dh_evento: dt.datetime | None = None, versao_app: str = "") -> str:
    """Monta o `<pedRegEvento>` (evento `e101101`, cancelamento), sem assinatura — assinar com
    `assinatura.assinar_pedido_evento` antes de enviar. `documento_autor`: CPF/CNPJ de quem está
    cancelando (normalmente o prestador que emitiu a nota). `motivo_codigo`: ver
    `MOTIVOS_CANCELAMENTO`; `motivo_texto`: mínimo 15 caracteres (regra do leiaute, `TSMotivo`)."""
    if motivo_codigo not in MOTIVOS_CANCELAMENTO:
        raise ErroAdge(f"Código de motivo de cancelamento inválido: {motivo_codigo!r} (use {list(MOTIVOS_CANCELAMENTO)}).")
    if len(motivo_texto.strip()) < 15:
        raise ErroAdge("Motivo do cancelamento precisa ter pelo menos 15 caracteres (regra do leiaute oficial).")
    doc = _so_digitos(documento_autor)
    if len(doc) not in (11, 14):
        raise ErroAdge("Documento do autor do cancelamento precisa ser um CPF ou CNPJ válido.")
    dh_evento = dh_evento or dt.datetime.now().astimezone()

    root = ET.Element("pedRegEvento", {"xmlns": NS_EVT, "versao": VERSAO_LEIAUTE})
    inf = ET.SubElement(root, "infPedReg", {"Id": _id_pedregevt(chave_acesso, "101101", n_pedregevento)})
    _sub(inf, "tpAmb", tp_amb)
    _sub(inf, "verAplic", (versao_app or "adge-nf-downloader")[:20])
    _sub(inf, "dhEvento", dh_evento.strftime("%Y-%m-%dT%H:%M:%S") + dh_evento.strftime("%z")[:3] + ":" + dh_evento.strftime("%z")[3:])
    if len(doc) == 11:
        _sub(inf, "CPFAutor", doc)
    else:
        _sub(inf, "CNPJAutor", doc)
    _sub(inf, "chNFSe", chave_acesso)
    e101101 = _sub(inf, "e101101")
    _sub(e101101, "xDesc", "Cancelamento de NFS-e")
    _sub(e101101, "cMotivo", motivo_codigo)
    _sub(e101101, "xMotivo", motivo_texto.strip()[:255])

    # Mesma correção do E1229 aplicada em dps.py: declaração UTF-8 explícita.
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True).decode("utf-8")
