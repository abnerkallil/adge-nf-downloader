"""NF-e (modelo 55) pela Distribuição de DF-e do Ambiente Nacional (SEFAZ), com o mesmo certificado A1 das NFS-e.

Como funciona (resumo):
- A consulta é por NSU (número sequencial), não por mês: o programa guarda o último NSU de cada empresa e baixa só o que é novo.
- Notas tomadas já manifestadas chegam com o XML completo (procNFe); sem manifestação chegam só como resumo (resNFe: chave,
  emitente, valor, tipo). A SEFAZ NÃO entrega à empresa as NF-e que ela mesma emite: essas só chegam a quem o emitente citou
  na própria nota (campo autXML), por exemplo o CPF/CNPJ do contador, consultando com o certificado dessa pessoa (v1.7.6).
- A SEFAZ limita as consultas: sem documento novo, só libera outra consulta depois de cerca de 1 hora (cStat 137/656).
  O limite é da própria SEFAZ, não do programa.
- A Ciência da Operação (evento 210210) é opcional e fica desligada por padrão: registra, em nome da empresa, que ela tomou
  conhecimento da nota, e faz a SEFAZ liberar o XML completo. Nunca é enviada Confirmação, Desconhecimento nem Operação não realizada.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import re
import time
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from . import cfop as cfop_mod
from . import core
from .core import Cancelado, ErroAdge, _achar, _local, _num, _txt

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_DIST = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeDistribuicaoDFe"
NS_EVENTO = "http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4"
URLS = {
    "1": {"dist": "https://www1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
          "evento": "https://www.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx"},
    "2": {"dist": "https://hom1.nfe.fazenda.gov.br/NFeDistribuicaoDFe/NFeDistribuicaoDFe.asmx",
          "evento": "https://hom1.nfe.fazenda.gov.br/NFeRecepcaoEvento4/NFeRecepcaoEvento4.asmx"},
}
HORAS_BLOQUEIO = 1                      # a SEFAZ pede cerca de 1 hora entre consultas sem novidade
EVENTO_CIENCIA = "210210"
EVENTOS_CANCELAMENTO = {"110111", "110112"}
CST_EVENTO_OK = {"135", "136", "573"}   # registrado (com/sem vínculo) ou duplicidade (já havia ciência)
LOTE_EVENTOS = 20                       # a SEFAZ aceita até 20 eventos por lote
CRT_PARA_SIMPLES = {"1": "3", "2": "3", "4": "2"}   # CRT da NF-e -> opSimpNac da NFS-e (3 ME/EPP, 2 MEI)


# ----------------------------------------------------------------------------- leitura dos XMLs
def _todos(el, nome):
    return [e for e in el.iter() if _local(e.tag) == nome] if el is not None else []


def _data_iso(txt: str) -> str:
    return txt or ""


def tipo_do_schema(schema: str) -> str:
    s = (schema or "").lower()
    if s.startswith("procnfe") or s.startswith("nfeproc"):
        return "proc"
    if s.startswith("resnfe"):
        return "res"
    if s.startswith("proceventonfe"):
        return "evento"
    if s.startswith("resevento"):
        return "resevento"
    return "outro"


def parse_nfe(xml_texto) -> dict:
    """NF-e completa (procNFe ou NFe). Devolve o mesmo formato das NFS-e, com campos extras de NF-e."""
    raiz = ET.fromstring(xml_texto.encode("utf-8") if isinstance(xml_texto, str) else xml_texto)
    inf = _achar(raiz, "infNFe")
    if inf is None:
        return {"kind": "desconhecido"}
    ide, emit, dest = _achar(inf, "ide"), _achar(inf, "emit"), _achar(inf, "dest")
    tot = _achar(inf, "ICMSTot")
    itens = []
    for det in _todos(inf, "det"):
        prod = _achar(det, "prod")
        itens.append({"cfop": cfop_mod.normalizar(_txt(prod, "CFOP")), "valor": _num(_txt(prod, "vProd")),
                      "descricao": _txt(prod, "xProd"), "ncm": _txt(prod, "NCM")})
    cfops = []
    for i in itens:
        if i["cfop"] and i["cfop"] not in cfops:
            cfops.append(i["cfop"])
    prot = _achar(raiz, "infProt")
    crt = _txt(emit, "CRT")
    return {
        "kind": "nfe",
        "chave": re.sub(r"^NFe", "", inf.get("Id", "")) or _txt(prot, "chNFe"),
        "numero": _txt(ide, "nNF"), "serie": _txt(ide, "serie"), "modelo": _txt(ide, "mod"),
        "emissao": _data_iso(_txt(ide, "dhEmi") or _txt(ide, "dEmi")), "processamento": "",
        "natureza": _txt(ide, "natOp"), "tp_nf": _txt(ide, "tpNF"), "fin_nfe": _txt(ide, "finNFe"),
        "emitente_doc": _txt(emit, "CNPJ") or _txt(emit, "CPF"), "emitente_nome": _txt(emit, "xNome"),
        "emitente_crt": crt, "emitente_simples": CRT_PARA_SIMPLES.get(crt, ""),
        "tomador_doc": _txt(dest, "CNPJ") or _txt(dest, "CPF") or _txt(dest, "idEstrangeiro"),
        "tomador_nome": _txt(dest, "xNome"),
        "valor": _num(_txt(tot, "vNF")), "valor_liquido": _num(_txt(tot, "vNF")), "iss": 0.0,
        "valor_produtos": _num(_txt(tot, "vProd")), "desconto": _num(_txt(tot, "vDesc")), "frete": _num(_txt(tot, "vFrete")),
        "seguro": _num(_txt(tot, "vSeg")), "outras_despesas": _num(_txt(tot, "vOutro")), "ipi": _num(_txt(tot, "vIPI")),
        "st": _num(_txt(tot, "vST")), "icms": _num(_txt(tot, "vICMS")), "pis": _num(_txt(tot, "vPIS")),
        "cofins": _num(_txt(tot, "vCOFINS")),
        "itens": itens, "cfops": cfops, "cfop": cfops[0] if cfops else "",
        "servico_cod": "", "servico_desc": "", "iss_aliquota": 0.0,
        "protocolo": _txt(prot, "nProt"), "situacao_prot": _txt(prot, "cStat"),
    }


def parse_resumo(xml_texto) -> dict:
    """resNFe: só chave, emitente, valor e tipo (entrada/saída). Notas tomadas sem ciência chegam assim."""
    raiz = ET.fromstring(xml_texto.encode("utf-8") if isinstance(xml_texto, str) else xml_texto)
    if _local(raiz.tag) != "resNFe":
        return {"kind": "desconhecido"}
    return {
        "kind": "nfe_resumo", "chave": _txt(raiz, "chNFe"), "numero": _txt(raiz, "chNFe")[25:34].lstrip("0"),
        "serie": _txt(raiz, "chNFe")[22:25].lstrip("0"), "emissao": _txt(raiz, "dhEmi"), "processamento": "",
        "emitente_doc": _txt(raiz, "CNPJ") or _txt(raiz, "CPF"), "emitente_nome": _txt(raiz, "xNome"),
        "tp_nf": _txt(raiz, "tpNF"), "situacao": _txt(raiz, "cSitNFe"), "valor": _num(_txt(raiz, "vNF")),
        "valor_liquido": _num(_txt(raiz, "vNF")), "iss": 0.0, "tomador_doc": "", "tomador_nome": "",
        "emitente_simples": "", "servico_cod": "", "servico_desc": "", "iss_aliquota": 0.0, "cfop": "", "cfops": [], "itens": [],
        "icms": 0.0,
    }


def parse_evento(xml_texto) -> dict:
    raiz = ET.fromstring(xml_texto.encode("utf-8") if isinstance(xml_texto, str) else xml_texto)
    tp = _txt(raiz, "tpEvento")
    return {"kind": "evento_nfe", "chave": _txt(raiz, "chNFe"), "tp_evento": tp,
            "cancelamento": tp in EVENTOS_CANCELAMENTO, "ciencia": tp == EVENTO_CIENCIA}


def parse_documento(xml_texto, schema: str = "") -> dict:
    raiz = ET.fromstring(xml_texto.encode("utf-8") if isinstance(xml_texto, str) else xml_texto)
    nome = _local(raiz.tag)
    if nome == "nfeProc" or _achar(raiz, "infNFe") is not None:
        return parse_nfe(xml_texto)
    if nome == "resNFe":
        return parse_resumo(xml_texto)
    if nome in ("procEventoNFe", "resEvento", "evento", "retEvento") or _achar(raiz, "tpEvento") is not None:
        return parse_evento(xml_texto)
    return {"kind": "desconhecido"}


# ----------------------------------------------------------------------------- classificação
def classificar_nfe(d: dict, cnpj: str):
    """Devolve a categoria da NF-e (chave de core.CATEGORIAS) ou None se a empresa não é emitente nem destinatária.
    Usa o CFOP dos itens (vale a categoria que concentra mais valor; d['cat_mista'] lista as demais) e preenche
    d['atividade'] ('comercio'/'industria') nas vendas."""
    eu_emito = d.get("emitente_doc") == cnpj
    eu_recebo = d.get("tomador_doc") == cnpj
    if not (eu_emito or eu_recebo):
        return None
    itens = d.get("itens") or []
    soma, ativ = {}, {}
    for i in itens or [{"cfop": d.get("cfop", ""), "valor": d.get("valor", 0.0)}]:
        cod = i.get("cfop", "")
        op = cfop_mod.operacao(cod)
        direc = cfop_mod.direcao(cod)
        if eu_emito:
            cat = {("saida", "venda"): "nfe_saida", ("saida", "devolucao_compra"): "nfe_devolucao_compra",
                   ("entrada", "compra"): "nfe_entrada", ("entrada", "devolucao_venda"): "nfe_devolucao_venda"}.get((direc, op), "nfe_outras")
        else:   # a nota é de um terceiro: o CFOP está do ponto de vista dele (saída dele = compra minha)
            cat = {("saida", "venda"): "nfe_entrada", ("saida", "devolucao_compra"): "nfe_devolucao_venda"}.get((direc, op), "nfe_outras")
        soma[cat] = soma.get(cat, 0.0) + float(i.get("valor") or 0)
        if cat == "nfe_saida":
            a = cfop_mod.atividade_da_venda(cod)
            ativ[a] = ativ.get(a, 0.0) + float(i.get("valor") or 0)
    if not soma:
        return "nfe_outras"
    cat = max(soma, key=soma.get)
    d["cat_mista"] = sorted(soma) if len(soma) > 1 else []
    if ativ:
        d["atividade"] = max(ativ, key=ativ.get)
    return cat


def data_da_nfe(d: dict):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", d.get("emissao") or "")
    return dt.date(int(m[1]), int(m[2]), int(m[3])) if m else None


def montar_plano_nfe(docs: list, cnpj: str, ano: int, mes: int, limite_nome: int = core.LIMITE_NOME, extras: dict = None):
    """docs: [{nsu, schema, xml}] vindos do cache/consulta. Devolve (arquivos, resumo_por_categoria, avisos).
    Aplica período (data de emissão), cancelamentos e agrupa por categoria. Resumos sem XML ficam em 'nfe_resumo'."""
    ini, fim = core.limites_mes(ano, mes)
    avisos, completas, resumos, canceladas, com_ciencia, ilegiveis = [], {}, {}, set(), set(), 0
    for x in sorted(docs, key=lambda t: t.get("nsu", 0)):
        if not x.get("xml"):
            continue
        try:
            d = parse_documento(x["xml"], x.get("schema", ""))
        except ET.ParseError:
            ilegiveis += 1
            continue
        k = d.get("kind")
        if k == "nfe" and d["chave"]:
            completas[d["chave"]] = (x, d)
        elif k == "nfe_resumo" and d["chave"]:
            resumos[d["chave"]] = (x, d)
        elif k == "evento_nfe":
            if d["cancelamento"]:
                canceladas.add(d["chave"])
            if d["ciencia"]:
                com_ciencia.add(d["chave"])
    if ilegiveis:
        avisos.append(f"{ilegiveis} documento(s) de NF-e ilegíveis foram ignorados.")
    arquivos, usados, resumo, terceiros = [], set(), {}, 0

    def conta(cat):
        return resumo.setdefault(cat, {"qtd": 0, "canceladas": 0, "valor": 0.0, "liquido": 0.0, "iss": 0.0, "icms": 0.0})

    for chave, (x, d) in sorted(completas.items(), key=lambda t: (t[1][1]["emissao"], t[1][1]["numero"])):
        dia = data_da_nfe(d)
        if dia is None or not (ini <= dia <= fim):
            continue
        cat = classificar_nfe(d, cnpj)
        if cat is None:
            if x.get("fonte") != "responsavel":       # o responsável recebe notas de várias empresas: as de outras são esperadas
                terceiros += 1
            continue
        r = conta(cat)
        if chave in canceladas or d.get("situacao_prot") in ("101", "151", "135"):
            r["canceladas"] += 1
            if extras is not None:
                extras.setdefault("canceladas", []).append({"nome": "", "xml": x["xml"], "cat": cat, "doc": d})
            continue
        r["qtd"] += 1
        r["valor"] += d["valor"]
        r["liquido"] += d["valor"]
        r["icms"] += d["icms"]
        arquivos.append({"nome": core.unico(core.nome_xml(cat, d, None, limite_nome), usados), "xml": x["xml"], "cat": cat, "doc": d})
    for chave, (x, d) in sorted(resumos.items(), key=lambda t: (t[1][1]["emissao"], t[1][1]["numero"])):
        if chave in completas:
            continue                                  # já há o XML completo desta nota
        dia = data_da_nfe(d)
        if dia is None or not (ini <= dia <= fim):
            continue
        if x.get("fonte") == "responsavel":
            continue                                  # resumo recebido pelo responsável: não se sabe se é compra desta empresa
        if d["emitente_doc"] == cnpj:
            continue                                  # resumo de nota emitida pela própria empresa: não é nota tomada (a empresa não recebe as notas que emite)
        r = conta("nfe_resumo")
        if chave in canceladas or d.get("situacao") == "3":
            r["canceladas"] += 1
            continue
        if d.get("situacao") == "2":                  # denegada: não vale como operação
            continue
        d["tomador_doc"] = cnpj
        d["ciencia_enviada"] = chave in com_ciencia
        r["qtd"] += 1
        r["valor"] += d["valor"]
        r["liquido"] += d["valor"]
        arquivos.append({"nome": "", "xml": x["xml"], "cat": "nfe_resumo", "doc": d, "sem_xml": True})
    if terceiros:
        avisos.append(f"{terceiros} NF-e do período não têm o CNPJ da empresa como emitente nem destinatário e foram ignoradas.")
    for r in resumo.values():
        for k in ("valor", "liquido", "iss", "icms"):
            r[k] = round(r[k], 2)
    return arquivos, resumo, avisos


def pendentes_ciencia(docs: list, cnpj: str, ano: int, mes: int, enviadas=()) -> list:
    """Chaves de NF-e tomadas do mês que só têm resumo, ainda sem ciência registrada (candidatas ao evento 210210)."""
    ini, fim = core.limites_mes(ano, mes)
    completas, resumos, com_ciencia = set(), {}, set(enviadas)
    for x in docs:
        if not x.get("xml"):
            continue
        try:
            d = parse_documento(x["xml"], x.get("schema", ""))
        except ET.ParseError:
            continue
        if d.get("kind") == "nfe":
            completas.add(d["chave"])
        elif d.get("kind") == "nfe_resumo":
            resumos[d["chave"]] = d
        elif d.get("kind") == "evento_nfe":
            if d["ciencia"]:
                com_ciencia.add(d["chave"])
            if d["cancelamento"]:
                com_ciencia.add(d["chave"])
    saida = []
    for chave, d in resumos.items():
        dia = data_da_nfe(d)
        if (chave in completas or chave in com_ciencia or d["emitente_doc"] == cnpj or d.get("situacao") in ("2", "3")
                or dia is None or not (ini <= dia <= fim)):
            continue
        saida.append(chave)
    return sorted(saida)


# ----------------------------------------------------------------------------- SOAP
def _envelope(corpo: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?><soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
            f'<soap12:Body>{corpo}</soap12:Body></soap12:Envelope>')


def xml_distribuicao(cnpj: str, ultimo_nsu: int = 0, chave: str = "", ambiente: str = "1") -> str:
    """`cnpj` aceita também um CPF (11 dígitos): quem consulta pelo certificado de uma pessoa (o responsável) usa a tag <CPF>."""
    doc = re.sub(r"\D", "", cnpj)
    tag = "CPF" if len(doc) == 11 else "CNPJ"
    if chave:
        escolha = f"<consChNFe><chNFe>{escape(chave)}</chNFe></consChNFe>"
    else:
        escolha = f"<distNSU><ultNSU>{int(ultimo_nsu):015d}</ultNSU></distNSU>"
    return (f'<distDFeInt xmlns="{NS_NFE}" versao="1.01"><tpAmb>{ambiente}</tpAmb><{tag}>{doc}</{tag}>{escolha}</distDFeInt>')


def _soap_dist(interno: str) -> str:
    return _envelope(f'<nfeDistDFeInteresse xmlns="{NS_DIST}"><nfeDadosMsg>{interno}</nfeDadosMsg></nfeDistDFeInteresse>')


def _soap_evento(interno: str) -> str:
    return _envelope(f'<nfeRecepcaoEvento xmlns="{NS_EVENTO}"><nfeDadosMsg>{interno}</nfeDadosMsg></nfeRecepcaoEvento>')


def _cabecalhos(ns: str, metodo: str) -> dict:
    return {"Content-Type": f'application/soap+xml; charset=utf-8; action="{ns}/{metodo}"'}


def _post(sessao, url, corpo, ns, metodo, timeout=60):
    try:
        r = sessao.post(url, data=corpo.encode("utf-8"), headers=_cabecalhos(ns, metodo), timeout=timeout)
    except Exception as e:
        raise ErroAdge(f"Não consegui falar com a SEFAZ: {e}") from e
    texto = getattr(r, "content", None) or getattr(r, "text", "")
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError:
        raise ErroAdge(f"A SEFAZ respondeu em formato inesperado (HTTP {getattr(r, 'status_code', '?')}).")
    if _achar(raiz, "Fault") is not None:
        raise ErroAdge("A SEFAZ recusou a requisição: " + (_txt(raiz, "Text") or _txt(raiz, "faultstring") or "erro de serviço") + ".")
    return raiz


def resposta_distribuicao(raiz) -> dict:
    ret = _achar(raiz, "retDistDFeInt")
    if ret is None:
        raise ErroAdge("Resposta da SEFAZ sem o retorno da distribuição de documentos.")
    docs = []
    for z in _todos(ret, "docZip"):
        try:
            xml = core.decodificar_arquivo((z.text or "").strip())
        except Exception:
            continue
        schema = z.get("schema", "")
        docs.append({"nsu": int(z.get("NSU") or 0), "schema": schema, "tipo": tipo_do_schema(schema), "xml": xml})
    return {"cstat": _txt(ret, "cStat"), "motivo": _txt(ret, "xMotivo"), "ult_nsu": int(_txt(ret, "ultNSU") or 0),
            "max_nsu": int(_txt(ret, "maxNSU") or 0), "docs": docs}


def consultar_distribuicao(sessao, cnpj: str, ultimo_nsu: int = 0, ambiente: str = "1", log=lambda *_: None,
                           cancelar=lambda: False, pausa: float = 1.0, esperar=time.sleep, agora=dt.datetime.now,
                           limite_lotes: int = 200) -> dict:
    """Baixa tudo que há de novo a partir de `ultimo_nsu`.
    Devolve {docs, ult_nsu, max_nsu, bloqueado_ate (datetime|None), situacao: 'novidades'|'sem_novidade'|'bloqueado', mensagem}.
    Depois de esgotar os documentos (ou de um 137/656) a SEFAZ só deve ser consultada de novo após `bloqueado_ate`."""
    url, docs, ult, maxi = URLS[ambiente]["dist"], [], int(ultimo_nsu), int(ultimo_nsu)
    situacao, mensagem, bloqueio = "sem_novidade", "", None
    for _ in range(limite_lotes):
        if cancelar():
            raise Cancelado()
        r = resposta_distribuicao(_post(sessao, url, _soap_dist(xml_distribuicao(cnpj, ult, "", ambiente)), NS_DIST, "nfeDistDFeInteresse"))
        cst = r["cstat"]
        if cst == "656":                                   # consumo indevido: consultou cedo demais
            situacao, mensagem = "bloqueado", r["motivo"]
            bloqueio = agora() + dt.timedelta(hours=HORAS_BLOQUEIO)
            break
        if cst == "137":                                   # nenhum documento localizado
            maxi = max(maxi, r["max_nsu"])
            ult = max(ult, r["ult_nsu"])
            bloqueio = agora() + dt.timedelta(hours=HORAS_BLOQUEIO)
            break
        if cst != "138":
            raise ErroAdge(f"A SEFAZ recusou a consulta de NF-e (cStat {cst}): {r['motivo'] or 'sem detalhe'}.")
        docs.extend(r["docs"])
        ult, maxi = r["ult_nsu"], r["max_nsu"]
        situacao = "novidades"
        log(f"NF-e: {len(docs)} documento(s) recebidos até agora...")
        if ult >= maxi:
            bloqueio = agora() + dt.timedelta(hours=HORAS_BLOQUEIO)
            break
        esperar(pausa)
    return {"docs": docs, "ult_nsu": ult, "max_nsu": maxi, "bloqueado_ate": bloqueio, "situacao": situacao, "mensagem": mensagem}


def consultar_chave(sessao, cnpj: str, chave: str, ambiente: str = "1") -> dict:
    """Pede a uma nota específica (útil logo depois da ciência, para já trazer o XML completo)."""
    r = resposta_distribuicao(_post(sessao, URLS[ambiente]["dist"], _soap_dist(xml_distribuicao(cnpj, 0, chave, ambiente)),
                                    NS_DIST, "nfeDistDFeInteresse"))
    return r


# ----------------------------------------------------------------------------- Ciência da Operação (evento 210210)
def _inf_evento(cnpj: str, chave: str, ambiente: str, agora: dt.datetime) -> tuple:
    """(Id, infEvento sem xmlns próprio). O xmlns do evento vem do envEvento que o envolve."""
    ident = f"ID{EVENTO_CIENCIA}{chave}01"
    dh = agora.astimezone().isoformat(timespec="seconds")
    xml = (f'<infEvento Id="{ident}"><cOrgao>91</cOrgao><tpAmb>{ambiente}</tpAmb><CNPJ>{cnpj}</CNPJ>'
           f'<chNFe>{chave}</chNFe><dhEvento>{dh}</dhEvento><tpEvento>{EVENTO_CIENCIA}</tpEvento><nSeqEvento>1</nSeqEvento>'
           f'<verEvento>1.00</verEvento><detEvento versao="1.00"><descEvento>Ciencia da Operacao</descEvento></detEvento></infEvento>')
    return ident, xml


def _c14n(xml: str) -> bytes:
    return ET.canonicalize(xml).encode("utf-8")


def _com_ns(xml: str, ns: str) -> str:
    """Põe o xmlns no elemento raiz: é assim que ele existe dentro do documento, e é isso que a assinatura cobre."""
    fim = xml.index(">")
    ponto = fim - 1 if xml[fim - 1] == "/" else fim
    return xml[:ponto].rstrip() + f' xmlns="{ns}"' + xml[ponto:]


def assinar_evento(cnpj: str, chave: str, ambiente: str, assinador: dict, agora: dt.datetime = None) -> str:
    """Monta e assina (XMLDSig, RSA-SHA1, C14N) o evento de ciência de uma nota. `assinador` vem de carregar_assinador().
    Devolve <evento versao="1.00">...</evento>, para entrar dentro de <envEvento xmlns="...nfe">."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    dsig = "http://www.w3.org/2000/09/xmldsig#"
    c14n = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
    ident, inf = _inf_evento(cnpj, chave, ambiente, agora or dt.datetime.now())
    digest = base64.b64encode(hashlib.sha1(_c14n(_com_ns(inf, NS_NFE))).digest()).decode()
    info = (f'<SignedInfo><CanonicalizationMethod Algorithm="{c14n}"></CanonicalizationMethod>'
            f'<SignatureMethod Algorithm="{dsig}rsa-sha1"></SignatureMethod><Reference URI="#{ident}"><Transforms>'
            f'<Transform Algorithm="{dsig}enveloped-signature"></Transform><Transform Algorithm="{c14n}"></Transform></Transforms>'
            f'<DigestMethod Algorithm="{dsig}sha1"></DigestMethod><DigestValue>{digest}</DigestValue></Reference></SignedInfo>')
    valor = base64.b64encode(assinador["chave"].sign(_c14n(_com_ns(info, dsig)), padding.PKCS1v15(), hashes.SHA1())).decode()
    assinatura = (f'<Signature xmlns="{dsig}">{info}<SignatureValue>{valor}</SignatureValue>'
                  f'<KeyInfo><X509Data><X509Certificate>{assinador["certificado_b64"]}</X509Certificate></X509Data></KeyInfo></Signature>')
    return f'<evento versao="1.00">{inf}{assinatura}</evento>'


def resposta_evento(raiz) -> dict:
    """{chave: (cStat, motivo)} de cada evento do lote; 'lote' traz o cStat do lote."""
    saida = {"lote": _txt(_achar(raiz, "retEnvEvento"), "cStat") if _achar(raiz, "retEnvEvento") is not None else ""}
    for ret in _todos(raiz, "retEvento"):
        inf = _achar(ret, "infEvento")
        saida[_txt(inf, "chNFe")] = (_txt(inf, "cStat"), _txt(inf, "xMotivo"))
    return saida


def enviar_ciencia(sessao, cnpj: str, chaves: list, assinador: dict, ambiente: str = "1", log=lambda *_: None,
                   cancelar=lambda: False, agora=dt.datetime.now) -> dict:
    """Envia SOMENTE a Ciência da Operação (210210) das chaves, em lotes. Devolve {chave: (cStat, motivo, ok)}."""
    resultado = {}
    for i in range(0, len(chaves), LOTE_EVENTOS):
        if cancelar():
            raise Cancelado()
        lote = chaves[i:i + LOTE_EVENTOS]
        eventos = "".join(assinar_evento(cnpj, c, ambiente, assinador, agora()) for c in lote)
        interno = f'<envEvento xmlns="{NS_NFE}" versao="1.00"><idLote>{int(time.time()) % 10**14}</idLote>{eventos}</envEvento>'
        raiz = _post(sessao, URLS[ambiente]["evento"], _soap_evento(interno), NS_EVENTO, "nfeRecepcaoEvento")
        ret = resposta_evento(raiz)
        if ret["lote"] and ret["lote"] != "128":
            motivo = _txt(_achar(raiz, "retEnvEvento"), "xMotivo")
            raise ErroAdge(f"A SEFAZ recusou o lote de ciência (cStat {ret['lote']}): {motivo or 'sem detalhe'}.")
        for c in lote:
            cst, motivo = ret.get(c, ("", "sem retorno"))
            resultado[c] = (cst, motivo, cst in CST_EVENTO_OK)
        log(f"Ciência da Operação enviada para {min(i + LOTE_EVENTOS, len(chaves))} de {len(chaves)} nota(s)...")
    return resultado


# ----------------------------------------------------------------------------- sessão com certificado
def bundle_confianca(destino=None):
    """Arquivo .pem com as autoridades certificadoras do pacote certifi + as instaladas no Windows.
    Os servidores da SEFAZ usam a cadeia ICP-Brasil, que o Windows conhece e o pacote do Python nem sempre.
    A verificação do servidor continua ligada: só ampliamos a lista de autoridades confiáveis."""
    import os
    import ssl
    if os.name != "nt":
        return None
    try:
        import certifi
        partes = [open(certifi.where(), encoding="ascii", errors="ignore").read()]
    except Exception:
        partes = []
    for loja in ("ROOT", "CA"):
        try:
            for cert, enc, _ in ssl.enum_certificates(loja):
                if enc == "x509_asn":
                    partes.append(ssl.DER_cert_to_PEM_cert(cert))
        except Exception:
            continue
    if not partes:
        return None
    from pathlib import Path
    from .store import pasta_dados
    alvo = Path(destino) if destino else pasta_dados() / "autoridades-confiaveis.pem"
    try:
        alvo.write_text("\n".join(partes), encoding="ascii")
    except OSError:
        return None
    return str(alvo)


def sessao_nfe(pfx: str, senha: str, ambiente: str = "1"):
    import requests
    from requests_pkcs12 import Pkcs12Adapter
    s = requests.Session()
    for host in {u.split("/NFe")[0] for u in URLS[ambiente].values()}:
        s.mount(host, Pkcs12Adapter(pkcs12_filename=pfx, pkcs12_password=senha))
    ver = bundle_confianca()
    if ver:
        s.verify = ver
    return s


def carregar_assinador(pfx: str, senha: str) -> dict:
    """Chave privada e certificado do A1, só para assinar a ciência (nada disso é gravado)."""
    from cryptography.hazmat.primitives.serialization import Encoding, pkcs12
    from pathlib import Path
    try:
        chave, cert, _ = pkcs12.load_key_and_certificates(Path(pfx).read_bytes(), senha.encode("utf-8") if senha else None)
    except Exception as e:
        raise ErroAdge("Senha incorreta ou arquivo de certificado inválido.") from e
    if chave is None or cert is None:
        raise ErroAdge("O certificado não contém a chave privada necessária para assinar a ciência.")
    return {"chave": chave, "certificado_b64": base64.b64encode(cert.public_bytes(Encoding.DER)).decode()}
