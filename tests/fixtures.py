"""XMLs sintéticos no layout da NFS-e Nacional v1.01 (sem dados de clientes reais)."""
import base64
import gzip


def xml_nfse(chave, emit_cnpj="11111111000111", emit_nome="EMPRESA TESTE LTDA", toma_cnpj="22222222000122",
             toma_nome="CLIENTE EXEMPLO LTDA", valor="100.00", dh="2026-09-10T10:00:00-03:00", num="1", ctrib="", xtrib="", simples=""):
    return (f'<?xml version="1.0" encoding="utf-8"?><NFSe versao="1.01" xmlns="http://www.sped.fazenda.gov.br/nfse">'
            f'<infNFSe Id="NFS{chave}"><nNFSe>{num}</nNFSe><dhProc>{dh}</dhProc>'
            f'<xTribNac>{xtrib}</xTribNac>'
            f'<emit><CNPJ>{emit_cnpj}</CNPJ><xNome>{emit_nome}</xNome></emit><valores><vLiq>{valor}</vLiq></valores>'
            f'<DPS versao="1.01"><infDPS Id="DPS1"><dhEmi>{dh}</dhEmi><dCompet>{dh[:10]}</dCompet>'
            f'<prest>' + (f'<regTrib><opSimpNac>{simples}</opSimpNac></regTrib>' if simples else '') + '</prest>'
            f'<toma><CNPJ>{toma_cnpj}</CNPJ><xNome>{toma_nome}</xNome></toma>'
            f'<serv><cServ><cTribNac>{ctrib}</cTribNac></cServ></serv>'
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


# ----------------------------------------------------------------------------- NF-e (modelo 55) e SEFAZ falsa
def chave_nfe(emit_cnpj="33333333000133", num=1, aamm="2609"):
    c = f"41{aamm}{emit_cnpj}55001{int(num):09d}1123456780"
    assert len(c) == 44, len(c)
    return c


def xml_nfe(emit_cnpj, dest_cnpj, itens=(("5102", 1000.0),), num=1, dh="2026-09-10T10:00:00-03:00", crt="3", icms=0.0,
            nat="VENDA DE MERCADORIA", tp_nf="1", cstat="100", emit_nome="EMITENTE TESTE", dest_nome="DESTINATARIO TESTE"):
    chave = chave_nfe(emit_cnpj, num, dh[2:4] + dh[5:7])
    dets = "".join(f'<det nItem="{n}"><prod><cProd>{n}</cProd><xProd>PRODUTO {n}</xProd><NCM>12345678</NCM><CFOP>{cf}</CFOP>'
                   f'<vProd>{v:.2f}</vProd></prod></det>' for n, (cf, v) in enumerate(itens, 1))
    total = sum(v for _, v in itens)
    return (f'<?xml version="1.0" encoding="UTF-8"?><nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00"><NFe>'
            f'<infNFe Id="NFe{chave}" versao="4.00"><ide><mod>55</mod><serie>1</serie><nNF>{num}</nNF><dhEmi>{dh}</dhEmi>'
            f'<natOp>{nat}</natOp><tpNF>{tp_nf}</tpNF><finNFe>1</finNFe></ide>'
            f'<emit><CNPJ>{emit_cnpj}</CNPJ><xNome>{emit_nome}</xNome><CRT>{crt}</CRT></emit>'
            f'<dest><CNPJ>{dest_cnpj}</CNPJ><xNome>{dest_nome}</xNome></dest>{dets}'
            f'<total><ICMSTot><vProd>{total:.2f}</vProd><vICMS>{icms:.2f}</vICMS><vNF>{total:.2f}</vNF></ICMSTot></total></infNFe>'
            f'</NFe><protNFe><infProt><chNFe>{chave}</chNFe><nProt>1</nProt><cStat>{cstat}</cStat></infProt></protNFe></nfeProc>')


def xml_resnfe(emit_cnpj, valor=500.0, num=1, dh="2026-09-12T10:00:00-03:00", emit_nome="FORNECEDOR RESUMO", sit="1"):
    return (f'<resNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01"><chNFe>{chave_nfe(emit_cnpj, num, dh[2:4] + dh[5:7])}</chNFe>'
            f'<CNPJ>{emit_cnpj}</CNPJ><xNome>{emit_nome}</xNome><IE>1</IE><dhEmi>{dh}</dhEmi><tpNF>1</tpNF><vNF>{valor:.2f}</vNF>'
            f'<digVal>x</digVal><dhRecbto>{dh}</dhRecbto><nProt>1</nProt><cSitNFe>{sit}</cSitNFe></resNFe>')


def xml_evento(chave, tp="110111"):
    return (f'<procEventoNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00"><evento versao="1.00"><infEvento>'
            f'<chNFe>{chave}</chNFe><tpEvento>{tp}</tpEvento></infEvento></evento></procEventoNFe>')


SCHEMAS_NFE = {"proc": "procNFe_v4.00.xsd", "res": "resNFe_v1.01.xsd", "evento": "procEventoNFe_v1.00.xsd"}


def doc_nfe(nsu, xml, tipo="proc"):
    return {"nsu": nsu, "tipo": tipo, "schema": SCHEMAS_NFE[tipo], "xml": xml}


def soap_dist(cstat, docs=(), ult=0, maxi=0, motivo="ok"):
    """Resposta SOAP da distribuição: docs = [(nsu, schema, xml)]."""
    zips = "".join(f'<docZip NSU="{n:015d}" schema="{s}">{empacotar(x)}</docZip>' for n, s, x in docs)
    lote = f"<loteDistDFeInt>{zips}</loteDistDFeInt>" if zips else ""
    return (f'<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"><soap:Body><nfeDistDFeInteresseResponse '
            f'xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe"><nfeDistDFeInteresseResult>'
            f'<retDistDFeInt xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.01"><tpAmb>1</tpAmb><verAplic>1</verAplic>'
            f'<cStat>{cstat}</cStat><xMotivo>{motivo}</xMotivo><ultNSU>{ult:015d}</ultNSU><maxNSU>{maxi:015d}</maxNSU>{lote}'
            f'</retDistDFeInt></nfeDistDFeInteresseResult></nfeDistDFeInteresseResponse></soap:Body></soap:Envelope>')


def soap_evento(resultados, lote="128"):
    """resultados: {chave: cStat}."""
    rets = "".join(f'<retEvento versao="1.00"><infEvento><cStat>{c}</cStat><xMotivo>m</xMotivo><chNFe>{k}</chNFe></infEvento></retEvento>'
                   for k, c in resultados.items())
    return (f'<soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope"><soap:Body><nfeResultMsg>'
            f'<retEnvEvento xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00"><idLote>1</idLote><cStat>{lote}</cStat>'
            f'<xMotivo>Lote processado</xMotivo>{rets}</retEnvEvento></nfeResultMsg></soap:Body></soap:Envelope>')


class RespSoap:
    def __init__(self, texto, code=200):
        self.content, self.status_code = texto.encode("utf-8"), code


class SessaoSefazFalsa:
    """Responde, em ordem, as respostas SOAP combinadas; guarda o que foi enviado. Sem resposta sobrando, responde 137."""

    def __init__(self, respostas=()):
        self.respostas, self.enviados = list(respostas), []

    def post(self, url, data=None, headers=None, timeout=0):
        self.enviados.append((url, data.decode("utf-8"), headers))
        return RespSoap(self.respostas.pop(0) if self.respostas else soap_dist("137", motivo="Nenhum documento localizado"))


# ----------------------------------------------------------------------------- Nota Paulistana
def xml_nfe_sp(im, num, emissao, valor, prestador, tomador, status="N", iss=None, nome_p="PRESTADORA LTDA", nome_t="TOMADORA SA"):
    iss = valor * 0.05 if iss is None else iss
    return (f'<NFe xmlns="http://www.prefeitura.sp.gov.br/nfe"><ChaveNFe><InscricaoPrestador>{im}</InscricaoPrestador>'
            f'<NumeroNFe>{num}</NumeroNFe><CodigoVerificacao>ABCD1234</CodigoVerificacao></ChaveNFe>'
            f'<DataEmissaoNFe>{emissao}T10:00:00</DataEmissaoNFe><StatusNFe>{status}</StatusNFe>'
            f'<CPFCNPJPrestador><CNPJ>{prestador}</CNPJ></CPFCNPJPrestador><RazaoSocialPrestador>{nome_p}</RazaoSocialPrestador>'
            f'<ValorServicos>{valor:.2f}</ValorServicos><ValorDeducoes>0.00</ValorDeducoes><CodigoServico>02496</CodigoServico>'
            f'<AliquotaServicos>0.05</AliquotaServicos><ValorISS>{iss:.2f}</ValorISS><ISSRetido>false</ISSRetido>'
            f'<CPFCNPJTomador><CNPJ>{tomador}</CNPJ></CPFCNPJTomador><RazaoSocialTomador>{nome_t}</RazaoSocialTomador>'
            f'<Discriminacao>Serviços de consultoria</Discriminacao></NFe>')


def soap_sp(metodo, notas=(), sucesso=True, erro=None, detalhes=()):
    """Resposta SOAP 1.1 da Paulistana; o retorno vai escapado dentro de <RetornoXML>."""
    from xml.sax.saxutils import escape
    erros = f"<Erro><Codigo>{erro[0]}</Codigo><Descricao>{erro[1]}</Descricao></Erro>" if erro else ""
    det = "".join(f"<Detalhe><InscricaoMunicipal>{i}</InscricaoMunicipal><EmiteNFe>true</EmiteNFe></Detalhe>" for i in detalhes)
    raiz = "RetornoConsultaCNPJ" if metodo == "ConsultaCNPJ" else "RetornoConsulta"
    interno = (f'<{raiz} xmlns="http://www.prefeitura.sp.gov.br/nfe"><Cabecalho Versao="2"><Sucesso>{str(sucesso).lower()}</Sucesso>'
               f'</Cabecalho>{erros}{det}{"".join(notas)}</{raiz}>')
    return (f'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body><{metodo}Response '
            f'xmlns="http://www.prefeitura.sp.gov.br/nfe"><RetornoXML>{escape(interno)}</RetornoXML></{metodo}Response></soap:Body></soap:Envelope>')


def assinador_falso():
    import base64 as b64
    import datetime as d
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import Encoding
    from cryptography.x509.oid import NameOID
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TESTE")])
    cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave.public_key())
            .serial_number(1).not_valid_before(d.datetime(2024, 1, 1)).not_valid_after(d.datetime(2034, 1, 1)).sign(chave, hashes.SHA256()))
    return {"chave": chave, "certificado_b64": b64.b64encode(cert.public_bytes(Encoding.DER)).decode(), "cert": cert}
