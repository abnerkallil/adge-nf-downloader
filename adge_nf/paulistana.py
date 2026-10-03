"""Nota Fiscal Paulistana (NFS-e da Prefeitura de São Paulo), consultada no web service da própria prefeitura.

Fonte separada do Ambiente Nacional (ADN): as notas daqui nunca se misturam com as de lá, nem entram nos totais por padrão.
Serve para conferência quando o sistema contábil e a Paulistana divergem.

Como funciona (resumo):
- Web service SOAP em nfews.prefeitura.sp.gov.br/lotenfe.asmx, com TLS e certificado A1 (ICP-Brasil), o mesmo da empresa.
- Cada pedido é um XML assinado (XMLDSig enveloped, RSA-SHA1, C14N) dentro de <MensagemXML>.
- Notas tomadas: ConsultaNFeRecebidas (CNPJ do tomador). Notas prestadas: ConsultaNFeEmitidas (CNPJ + Inscrição Municipal,
  que o programa descobre com ConsultaCNPJ). Até 50 notas por página; o programa pede página após página.
- O limite de período por consulta não é fixo no manual; o programa consulta de uma vez o mês inteiro.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from . import core
from .core import Cancelado, ErroAdge, _achar, _local, _num, _txt

NS = "http://www.prefeitura.sp.gov.br/nfe"
URL = "https://nfews.prefeitura.sp.gov.br/lotenfe.asmx"
HOST = "https://nfews.prefeitura.sp.gov.br"
DSIG = "http://www.w3.org/2000/09/xmldsig#"
C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
POR_PAGINA = 50
LIMITE_PAGINAS = 200
VERSOES = ("2", "1")                    # layout da reforma tributária (2) e o anterior (1), se a prefeitura recusar o primeiro
ORIGEM = "paulistana"
ET.register_namespace("", NS)           # os XMLs gravados ficam com xmlns padrão, sem prefixo ns0

# metodo -> (elemento do pedido, elemento do retorno)
METODOS = {"recebidas": "ConsultaNFeRecebidas", "emitidas": "ConsultaNFeEmitidas", "cnpj": "ConsultaCNPJ"}


# ----------------------------------------------------------------------------- pedidos assinados
def _c14n(xml: str) -> bytes:
    return ET.canonicalize(xml).encode("utf-8")


def _com_ns(xml: str, ns: str) -> str:
    fim = xml.index(">")
    ponto = fim - 1 if xml[fim - 1] == "/" else fim
    return xml[:ponto].rstrip() + f' xmlns="{ns}"' + xml[ponto:]


def assinar(raiz_xml: str, assinador: dict) -> str:
    """Assina a mensagem inteira (Reference URI=""), com a assinatura dentro do elemento raiz, no fim.
    `raiz_xml` já traz o xmlns da prefeitura no elemento raiz."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    digest = base64.b64encode(hashlib.sha1(_c14n(raiz_xml)).digest()).decode()
    info = (f'<SignedInfo><CanonicalizationMethod Algorithm="{C14N}"></CanonicalizationMethod>'
            f'<SignatureMethod Algorithm="{DSIG}rsa-sha1"></SignatureMethod><Reference URI=""><Transforms>'
            f'<Transform Algorithm="{DSIG}enveloped-signature"></Transform></Transforms>'
            f'<DigestMethod Algorithm="{DSIG}sha1"></DigestMethod><DigestValue>{digest}</DigestValue></Reference></SignedInfo>')
    valor = base64.b64encode(assinador["chave"].sign(_c14n(_com_ns(info, DSIG)), padding.PKCS1v15(), hashes.SHA1())).decode()
    assinatura = (f'<Signature xmlns="{DSIG}">{info}<SignatureValue>{valor}</SignatureValue>'
                  f'<KeyInfo><X509Data><X509Certificate>{assinador["certificado_b64"]}</X509Certificate></X509Data></KeyInfo></Signature>')
    fim = raiz_xml.rindex("</")
    return raiz_xml[:fim] + assinatura + raiz_xml[fim:]


def _doc(cnpj: str) -> str:
    return f"<CNPJ>{cnpj}</CNPJ>"


# No esquema da prefeitura só a raiz e a assinatura têm namespace: o Cabecalho e tudo dentro dele não (elementFormDefault padrão),
# por isso o xmlns="" no Cabecalho. Sem isso a prefeitura recusa o XML (erro 1001, "invalid child element 'Cabecalho'").
def pedido_periodo(remetente: str, cnpj: str, inscricao: str, ini: dt.date, fim: dt.date, pagina: int, assinador: dict,
                   versao: str = "2") -> str:
    insc = f"<Inscricao>{int(inscricao)}</Inscricao>" if inscricao else ""
    corpo = (f'<PedidoConsultaNFePeriodo xmlns="{NS}"><Cabecalho Versao="{versao}" xmlns="">'
             f'<CPFCNPJRemetente>{_doc(remetente)}</CPFCNPJRemetente><CPFCNPJ>{_doc(cnpj)}</CPFCNPJ>{insc}'
             f'<dtInicio>{ini.isoformat()}</dtInicio><dtFim>{fim.isoformat()}</dtFim><NumeroPagina>{int(pagina)}</NumeroPagina>'
             f'</Cabecalho></PedidoConsultaNFePeriodo>')
    return assinar(corpo, assinador)


def pedido_cnpj(remetente: str, cnpj: str, assinador: dict, versao: str = "2") -> str:
    corpo = (f'<PedidoConsultaCNPJ xmlns="{NS}"><Cabecalho Versao="{versao}" xmlns=""><CPFCNPJRemetente>{_doc(remetente)}</CPFCNPJRemetente>'
             f'</Cabecalho><CNPJContribuinte xmlns="">{_doc(cnpj)}</CNPJContribuinte></PedidoConsultaCNPJ>')
    return assinar(corpo, assinador)


# ----------------------------------------------------------------------------- SOAP
def soap(metodo: str, versao: str, mensagem: str) -> str:
    nome = METODOS[metodo]
    return ('<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            f'<soap:Body><{nome}Request xmlns="{NS}"><VersaoSchema>{versao}</VersaoSchema>'
            f'<MensagemXML>{escape(mensagem)}</MensagemXML></{nome}Request></soap:Body></soap:Envelope>')


def _cabecalhos(metodo: str) -> dict:
    nome = METODOS[metodo]
    return {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{NS}/ws/{nome[0].lower()}{nome[1:]}"'}


def _enviar(sessao, metodo: str, versao: str, mensagem: str, timeout=90):
    try:
        r = sessao.post(URL, data=soap(metodo, versao, mensagem).encode("utf-8"), headers=_cabecalhos(metodo), timeout=timeout)
    except Exception as e:
        raise ErroAdge(f"Não consegui falar com a Prefeitura de São Paulo: {e}") from e
    texto = getattr(r, "content", None) or getattr(r, "text", "")
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError:
        raise ErroAdge(f"A Prefeitura de São Paulo respondeu em formato inesperado (HTTP {getattr(r, 'status_code', '?')}).")
    if _achar(raiz, "Fault") is not None:
        raise ErroAdge("A Prefeitura de São Paulo recusou a requisição: "
                       + (_txt(raiz, "faultstring") or _txt(raiz, "Text") or "erro de serviço") + ".")
    interno = _achar(raiz, "RetornoXML")
    if interno is None or not (interno.text or "").strip():
        raise ErroAdge("Resposta da Prefeitura de São Paulo sem o retorno da consulta.")
    try:
        return ET.fromstring(interno.text.strip())
    except ET.ParseError:
        raise ErroAdge("Resposta da Prefeitura de São Paulo ilegível (XML do retorno inválido).")


# ----------------------------------------------------------------------------- leitura do retorno
def _eventos(raiz, nome: str) -> list:
    out = []
    for e in raiz.iter():
        if _local(e.tag) == nome:
            out.append(f"{_txt(e, 'Codigo')} - {_txt(e, 'Descricao')}".strip(" -"))
    return out


def parse_nfe(el) -> dict:
    """Um <NFe> do retorno -> o mesmo formato das NFS-e (campos que a tela e a planilha usam)."""
    pre = _achar(el, "ChaveNFe")
    insc, numero = _txt(pre, "InscricaoPrestador"), _txt(pre, "NumeroNFe")
    prest, toma = _achar(el, "CPFCNPJPrestador"), _achar(el, "CPFCNPJTomador")
    valor = _num(_txt(el, "ValorServicos"))
    deducoes = _num(_txt(el, "ValorDeducoes"))
    emissao = _txt(el, "DataEmissaoNFe") or _txt(el, "DataFatoGeradorNFe")
    return {
        "kind": ORIGEM, "chave": f"SP-{insc}-{numero}", "numero": numero.lstrip("0") or numero, "inscricao": insc,
        "codigo_verificacao": _txt(pre, "CodigoVerificacao"), "chave_nacional": _txt(pre, "ChaveNotaNacional"),
        "emissao": emissao, "processamento": "", "status": _txt(el, "StatusNFe") or "N",
        "emitente_doc": _txt(prest, "CNPJ") or _txt(prest, "CPF"), "emitente_nome": _txt(el, "RazaoSocialPrestador"),
        "tomador_doc": _txt(toma, "CNPJ") or _txt(toma, "CPF"), "tomador_nome": _txt(el, "RazaoSocialTomador"),
        "valor": valor, "valor_liquido": round(valor - deducoes, 2), "iss": _num(_txt(el, "ValorISS")),
        "iss_aliquota": _num(_txt(el, "AliquotaServicos")) * 100 if 0 < _num(_txt(el, "AliquotaServicos")) < 1 else _num(_txt(el, "AliquotaServicos")),
        "iss_retido": _txt(el, "ISSRetido").lower() == "true", "servico_cod": _txt(el, "CodigoServico"),
        "servico_desc": _txt(el, "Discriminacao"), "emitente_simples": "", "icms": 0.0, "cfop": "", "cfops": [], "itens": [],
    }


def resposta(raiz) -> dict:
    sucesso = _txt(raiz, "Sucesso").lower() == "true"
    nfes = [e for e in raiz.iter() if _local(e.tag) == "NFe"]
    return {"sucesso": sucesso, "erros": _eventos(raiz, "Erro"), "alertas": _eventos(raiz, "Alerta"),
            "nfes": [{"xml": ET.tostring(e, encoding="unicode"), "doc": parse_nfe(e)} for e in nfes]}


def _erro_de_versao(erros: list) -> bool:
    t = " ".join(erros).lower()
    return any(p in t for p in ("vers", "schema", "xsd"))


def _consultar(sessao, metodo: str, montar, log=lambda *_: None) -> dict:
    """Tenta o layout 2 e, se a prefeitura reclamar de versão/schema, o layout 1."""
    ultimo = None
    for versao in VERSOES:
        raiz = _enviar(sessao, metodo, versao, montar(versao))
        r = resposta(raiz)
        r["versao"] = versao
        if r["sucesso"] or not _erro_de_versao(r["erros"]):
            return r
        ultimo = r
        log(f"A prefeitura recusou o layout {versao}; tentando o outro...")
    return ultimo


def inscricoes(sessao, remetente: str, cnpj: str, assinador: dict, log=lambda *_: None) -> list:
    """Inscrições Municipais (CCM) ligadas ao CNPJ que emitem NFS-e."""
    def monta(v):
        return pedido_cnpj(remetente, cnpj, assinador, v)
    erros = []
    for versao in VERSOES:
        raiz = _enviar(sessao, "cnpj", versao, monta(versao))
        if _txt(raiz, "Sucesso").lower() == "true":
            return [_txt(d, "InscricaoMunicipal") for d in raiz.iter()
                    if _local(d.tag) == "Detalhe" and _txt(d, "EmiteNFe").lower() != "false" and _txt(d, "InscricaoMunicipal")]
        erros = _eventos(raiz, "Erro")
        if not _erro_de_versao(erros):
            raise ErroAdge("A Prefeitura de São Paulo não informou a Inscrição Municipal do CNPJ: " + ("; ".join(erros) or "sem detalhe") + ".")
    raise ErroAdge("A Prefeitura de São Paulo recusou a consulta da Inscrição Municipal: " + ("; ".join(erros) or "sem detalhe") + ".")


def baixar_lado(sessao, metodo: str, remetente: str, cnpj: str, inscricao: str, ini: dt.date, fim: dt.date, assinador: dict,
                log=lambda *_: None, cancelar=lambda: False) -> tuple:
    """Todas as páginas de um lado. Devolve (notas, avisos). Erro da prefeitura na 1ª página vira ErroAdge."""
    notas, avisos, versao = [], [], VERSOES[0]
    for pagina in range(1, LIMITE_PAGINAS + 1):
        if cancelar():
            raise Cancelado()
        log(f"Nota Paulistana ({'tomadas' if metodo == 'recebidas' else 'prestadas'}): página {pagina}...")

        def monta(v, p=pagina):
            return pedido_periodo(remetente, cnpj, inscricao, ini, fim, p, assinador, v)
        r = _consultar(sessao, metodo, monta, log) if pagina == 1 else _enviar_pagina(sessao, metodo, versao, monta)
        versao = r.get("versao", versao)
        if not r["sucesso"]:
            raise ErroAdge("A Prefeitura de São Paulo recusou a consulta: " + ("; ".join(r["erros"]) or "sem detalhe") + ".")
        avisos += r["alertas"]
        notas += r["nfes"]
        if len(r["nfes"]) < POR_PAGINA:
            break
    return notas, avisos


def _enviar_pagina(sessao, metodo, versao, monta):
    r = resposta(_enviar(sessao, metodo, versao, monta(versao)))
    r["versao"] = versao
    return r


def consultar(sessao, cnpj: str, ano: int, mes: int, assinador: dict, prestadas: bool = True, tomadas: bool = True,
              log=lambda *_: None, cancelar=lambda: False) -> dict:
    """Consulta o mês na Paulistana. Devolve {docs: [{xml, lado}], msgs: [...]}; um lado que falha vira mensagem, não derruba o outro."""
    ini, fim = core.limites_mes(ano, mes)
    docs, msgs = [], []
    if tomadas:
        try:
            notas, av = baixar_lado(sessao, "recebidas", cnpj, cnpj, "", ini, fim, assinador, log, cancelar)
            docs += [{"xml": n["xml"], "lado": "tomado"} for n in notas]
            msgs += [f"Paulistana (tomadas): {a}" for a in av]
        except ErroAdge as e:
            msgs.append(f"Nota Paulistana, notas tomadas: {e}")
    if prestadas:
        try:
            ims = inscricoes(sessao, cnpj, cnpj, assinador, log)
            if not ims:
                msgs.append("Nota Paulistana, notas prestadas: a prefeitura não informou Inscrição Municipal emissora para este CNPJ.")
            for im in ims:
                notas, av = baixar_lado(sessao, "emitidas", cnpj, cnpj, im, ini, fim, assinador, log, cancelar)
                docs += [{"xml": n["xml"], "lado": "prestado"} for n in notas]
                msgs += [f"Paulistana (prestadas, IM {im}): {a}" for a in av]
        except ErroAdge as e:
            msgs.append(f"Nota Paulistana, notas prestadas: {e}")
    return {"docs": docs, "msgs": msgs}


# ----------------------------------------------------------------------------- plano (mesmo formato das outras fontes)
CAT_LADO = {"prestado": "paulistana_prestado", "tomado": "paulistana_tomado"}


def montar_plano(docs: list, cnpj: str, ano: int, mes: int, limite_nome: int = core.LIMITE_NOME, extras: dict = None):
    """docs: [{xml, lado}]. Aplica o período (data de emissão), tira canceladas/extraviadas e agrupa por categoria."""
    ini, fim = core.limites_mes(ano, mes)
    arquivos, resumo, avisos, usados, vistos, ilegiveis = [], {}, [], set(), set(), 0
    parsed = []
    for x in docs:
        try:
            parsed.append((x, parse_nfe(ET.fromstring(x["xml"]))))
        except ET.ParseError:
            ilegiveis += 1
    if ilegiveis:
        avisos.append(f"{ilegiveis} nota(s) da Paulistana ilegíveis foram ignoradas.")
    for x, d in sorted(parsed, key=lambda t: (t[1]["emissao"], t[1]["numero"])):
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", d["emissao"] or "")
        if not m or not (ini <= dt.date(int(m[1]), int(m[2]), int(m[3])) <= fim):
            continue
        cat = CAT_LADO[x["lado"]]
        if (cat, d["chave"]) in vistos:
            continue
        vistos.add((cat, d["chave"]))
        r = resumo.setdefault(cat, {"qtd": 0, "canceladas": 0, "valor": 0.0, "liquido": 0.0, "iss": 0.0, "icms": 0.0})
        if d["status"] != "N":
            r["canceladas"] += 1
            if extras is not None:
                extras.setdefault("canceladas", []).append({"nome": "", "xml": x["xml"], "cat": cat, "doc": d})
            continue
        r["qtd"] += 1
        r["valor"] += d["valor"]
        r["liquido"] += d["valor_liquido"]
        r["iss"] += d["iss"]
        arquivos.append({"nome": core.unico(core.nome_xml(cat, d, None, limite_nome), usados), "xml": x["xml"], "cat": cat, "doc": d})
    for r in resumo.values():
        for k in ("valor", "liquido", "iss", "icms"):
            r[k] = round(r[k], 2)
    return arquivos, resumo, avisos


# ----------------------------------------------------------------------------- comparação com o Ambiente Nacional
def comparar(arquivos: list) -> dict:
    """Notas de serviço presentes só no ADN ou só na Paulistana (mesmo lado): pelo número + CNPJ da outra parte + valor.
    Devolve {"so_adn": [...], "so_paulistana": [...], "em_ambos": n}."""
    def chave(a):
        d = a["doc"]
        outra = d.get("tomador_doc") if a["cat"].endswith("prestado") else d.get("emitente_doc")
        return (a["cat"].replace("paulistana_", "servico_"), str(d.get("numero") or "").lstrip("0"), outra, round(float(d.get("valor") or 0), 2))
    adn = {chave(a): a for a in arquivos if a["cat"] in ("servico_prestado", "servico_tomado")}
    sp = {chave(a): a for a in arquivos if a["cat"] in CAT_LADO.values()}
    return {"so_adn": [adn[k] for k in adn if k not in sp], "so_paulistana": [sp[k] for k in sp if k not in adn],
            "em_ambos": len(set(adn) & set(sp))}


# ----------------------------------------------------------------------------- sessão com certificado
def sessao_paulistana(pfx: str, senha: str):
    import requests
    from requests_pkcs12 import Pkcs12Adapter
    from .nfe import bundle_confianca
    s = requests.Session()
    s.mount(HOST, Pkcs12Adapter(pkcs12_filename=pfx, pkcs12_password=senha))
    ver = bundle_confianca()
    if ver:
        s.verify = ver
    return s
