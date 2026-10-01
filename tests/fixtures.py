"""XMLs sintéticos no layout da NFS-e Nacional v1.01 (sem dados de clientes reais)."""
import base64
import gzip


def xml_nfse(chave, emit_cnpj="11111111000111", emit_nome="EMPRESA TESTE LTDA", toma_cnpj="22222222000122",
             toma_nome="CLIENTE EXEMPLO LTDA", valor="100.00", dh="2026-09-10T10:00:00-03:00", num="1"):
    return (f'<?xml version="1.0" encoding="utf-8"?><NFSe versao="1.01" xmlns="http://www.sped.fazenda.gov.br/nfse">'
            f'<infNFSe Id="NFS{chave}"><nNFSe>{num}</nNFSe><dhProc>{dh}</dhProc>'
            f'<emit><CNPJ>{emit_cnpj}</CNPJ><xNome>{emit_nome}</xNome></emit><valores><vLiq>{valor}</vLiq></valores>'
            f'<DPS versao="1.01"><infDPS Id="DPS1"><dhEmi>{dh}</dhEmi><dCompet>{dh[:10]}</dCompet>'
            f'<toma><CNPJ>{toma_cnpj}</CNPJ><xNome>{toma_nome}</xNome></toma>'
            f'<valores><vServPrest><vServ>{valor}</vServ></vServPrest></valores></infDPS></DPS></infNFSe></NFSe>')


def evento_cancelamento(chave):
    return (f'<pedRegEvento xmlns="http://www.sped.fazenda.gov.br/nfse"><infPedReg><chNFSe>{chave}</chNFSe>'
            f'<e101101><xDesc>Cancelamento</xDesc></e101101></infPedReg></pedRegEvento>')


def empacotar(xml: str) -> str:
    return base64.b64encode(gzip.compress(xml.encode("utf-8"))).decode()


class Resp:
    def __init__(self, code, body):
        self.status_code, self._b = code, body

    def json(self):
        if self._b is None:
            raise ValueError
        return self._b


class SessaoFalsa:
    """lotes: lista de (nsu_inicial, [itens]). Qualquer outro NSU responde 404."""

    def __init__(self, lotes):
        self.lotes, self.chamadas = lotes, []

    def get(self, url, params=None, timeout=0):
        nsu = int(url.rsplit("/", 1)[1])
        self.chamadas.append((nsu, params))
        for ini, itens in self.lotes:
            if nsu == ini:
                return Resp(200, {"StatusProcessamento": "DOCUMENTOS_LOCALIZADOS", "LoteDFe": itens})
        return Resp(404, {"StatusProcessamento": "NENHUM_DOCUMENTO_LOCALIZADO"})


def item(nsu, xml, chave="k"):
    return {"NSU": nsu, "ChaveAcesso": chave, "TipoDocumento": "NFSE", "ArquivoXml": empacotar(xml)}
