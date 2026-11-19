"""Monta a DPS a partir da configuração fixa da empresa (`empresa["emissao"]`, schema do Dev A em
`config_schema.py`), do perfil de serviço escolhido, do tomador casado (se houver) e do
lançamento. `montar_campos` devolve um dict normalizado; `montar_xml` serializa esse dict no XML
oficial (`<DPS versao="1.01"><infDPS Id="...">...</infDPS></DPS>`, sem a assinatura — isso é
`assinatura.assinar_dps`).

Leiaute confirmado contra o XSD oficial baixado em
https://www.gov.br/nfse/.../nfse-esquemas_xsd-v1-01-20260209.zip (`DPS_v1.01.xsd` +
`tiposComplexos_v1.01.xsd` + `tiposSimples_v1.01.xsd`), não de memória — `tests/test_emissao_dps_xml.py`
valida o XML gerado contra esse schema de verdade.

Limitações conhecidas, deliberadas (não chutar dado que não temos):
- `prest/end` e `toma/end` (endereço estruturado, com código IBGE do município) ficam de fora: o
  cadastro da empresa não guarda CEP/logradouro do prestador, e o cadastro de tomador (PR #2) não
  guarda o código IBGE do município (só o nome). Os dois grupos são opcionais no leiaute (`end`
  minOccurs="0"), então a nota sai sem eles até esse campo existir no schema — avisado ao Dev A.
- `IBSCBS`, `obra`, `atvEvento`, `comExt`, `interm`, `subst`, `vDedRed` não são usados ainda (fora
  do escopo atual: emissão simples pelo prestador, sem IBS/CBS, obra, evento ou comércio exterior).
- `cLocPrestacao` usa o município do PRESTADOR por padrão (mesma limitação do endereço do tomador
  acima); ajustar quando o schema do tomador tiver o código IBGE.
"""
from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET

from ..core import ErroAdge, limites_mes
from . import config_schema as es

NS_DPS = "http://www.sped.fazenda.gov.br/nfse"
VERSAO_LEIAUTE = "1.01"

TP_AMB_PRODUCAO, TP_AMB_HOMOLOGACAO = "1", "2"

_OP_SIMP_NAC = {"mei": "2", "simples": "3"}  # presumido/real/ausente: 1 (Não Optante)
_REG_ESP_TRIB_NENHUM = "0"


def _so_digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _dec(valor: float) -> str:
    return f"{float(valor or 0):.2f}"


def _codigo(valor: str) -> str:
    """`perfil["ctn"]`/`perfil["nbs"]` guardam "código - descrição" (ex.: "99.01.01 - Serviços sem
    incidência..."), do jeito que o portal mostra no combo. Isola só o código, sem pontuação."""
    primeira_parte = re.split(r"\s[-–]\s", str(valor or ""), maxsplit=1)[0]
    return re.sub(r"\D", "", primeira_parte)


def _pis_cofins(empresa_emissao: dict, perfil: dict, lancamento) -> dict | None:
    """None quando o grupo não entra na nota. MEI: proibido (RN 518), mesmo que o perfil esteja mal
    configurado. Presumido/Real: obrigatório — perfil sem `incluir` é erro de configuração, não
    "nota sem PIS/COFINS". Simples (ME/EPP): opcional, segue o perfil."""
    regra = es.pis_cofins_regra(empresa_emissao.get("regime", ""))
    pc = perfil.get("pis_cofins") or {}
    if regra == "proibido":
        return None
    if not pc.get("incluir"):
        if regra == "obrigatorio":
            raise ErroAdge(
                f'Regime "{empresa_emissao.get("regime")}" exige PIS/COFINS na nota, mas o perfil '
                f'"{perfil.get("nome", perfil.get("id"))}" não está configurado para incluir.')
        return None
    aliq_pis, aliq_cofins = pc.get("aliquota_pis", 0.0), pc.get("aliquota_cofins", 0.0)
    retido = lancamento.retencao_pis_cofins_csll
    tp_ret = (3 if retido else 0) if retido is not None else pc.get("tp_ret_pis_cofins", 0)
    return {
        "cst_pis": pc.get("cst_pis") or "01", "cst_cofins": pc.get("cst_cofins") or "01",
        "aliquota_pis": aliq_pis, "aliquota_cofins": aliq_cofins,
        "valor_pis": round(lancamento.valor * aliq_pis / 100, 2),
        "valor_cofins": round(lancamento.valor * aliq_cofins / 100, 2),
        "tp_ret_pis_cofins": tp_ret,
    }


def montar_campos(empresa: dict, empresa_emissao: dict, perfil: dict, tomador: dict | None, lancamento) -> dict:
    """`empresa`: cadastro geral (nome, cnpj); `empresa_emissao`: `empresa["emissao"]`; `tomador`:
    registro casado de `empresa_emissao["tomadores"]`, ou None quando a prévia aplicou o perfil na
    mão sem salvar regra. Levanta `ErroAdge` se faltar algo essencial do perfil ou da config."""
    if not perfil.get("ctn") or not perfil.get("nbs"):
        raise ErroAdge(f'Perfil "{perfil.get("nome", perfil.get("id"))}" está sem CTN ou NBS configurado.')
    if not empresa_emissao.get("codigo_municipio_ibge"):
        raise ErroAdge("Falta o código IBGE do município da empresa na configuração de emissão.")
    ano, mes = int(lancamento.competencia[:4]), int(lancamento.competencia[5:7])
    data_emissao = lancamento.data_prestacao or limites_mes(ano, mes)[1].isoformat()
    return {
        "prestador": {
            "cnpj": _so_digitos(empresa.get("cnpj", "")),
            "nome": empresa.get("nome", ""),
            "inscricao_municipal": empresa_emissao.get("inscricao_municipal", ""),
            "codigo_municipio_ibge": empresa_emissao.get("codigo_municipio_ibge", ""),
            "regime": empresa_emissao.get("regime", ""),
        },
        "tomador": {
            "nome": lancamento.tomador_nome, "documento": lancamento.tomador_documento,
            "tipo_documento": lancamento.tipo_documento,
        },
        "servico": {
            "ctn": _codigo(perfil["ctn"]), "nbs": _codigo(perfil["nbs"]),
            "issqn": dict(perfil.get("issqn") or es.issqn_padrao()),
        },
        "valores": {"valor_servico": lancamento.valor, "pis_cofins": _pis_cofins(empresa_emissao, perfil, lancamento)},
        "descricao": es.descricao_efetiva(perfil, tomador, mes, ano),
        "informacoes_complementares": es.informacoes_complementares_efetivas(perfil, tomador),
        "competencia": lancamento.competencia,
        "data_emissao": data_emissao,
    }


# ------------------------------------------------------------------------------------------- XML


def _id_dps(cod_mun_emi: str, documento_prestador: str, serie: str, numero: int) -> str:
    """"DPS" + Cód.Mun.Emi.(7) + Tipo de Inscrição Federal(1, 1=CPF 2=CNPJ) + Inscrição Federal
    (14, CPF completa com 000 à esquerda) + Série(5) + Núm. DPS(15) — 45 posições, regra de
    negócio nº 139 da planilha oficial (`regras-negocio-dps.csv`), confirmada contra o XSD."""
    doc = _so_digitos(documento_prestador)
    tipo = "1" if len(doc) == 11 else "2"
    inscricao = doc.zfill(14)
    return f"DPS{cod_mun_emi.zfill(7)}{tipo}{inscricao}{str(serie).zfill(5)}{str(numero).zfill(15)}"


def _sub(pai, tag, texto=None, **attrs):
    el = ET.SubElement(pai, tag, attrs)
    if texto is not None:
        el.text = str(texto)
    return el


def montar_xml(campos: dict, *, serie: str = "1", numero: int = 1, ambiente: str = TP_AMB_HOMOLOGACAO,
                dh_emi: dt.datetime | None = None, versao_app: str = "") -> str:
    """Serializa `campos` (de `montar_campos`) no XML da DPS, sem assinatura. `numero`/`serie`
    identificam essa DPS (ver `historico.proximo_numero_dps`); `ambiente` é `TP_AMB_HOMOLOGACAO`
    (produção restrita, padrão) ou `TP_AMB_PRODUCAO` — nunca produção sem aprovação explícita do
    Abner (ver `transmissao.PRODUCAO_REAL_LIBERADA`)."""
    prest = campos["prestador"]
    cod_mun = prest["codigo_municipio_ibge"]
    doc_prest = prest["cnpj"]
    dh_emi = dh_emi or dt.datetime.now().astimezone()

    root = ET.Element("DPS", {"xmlns": NS_DPS, "versao": VERSAO_LEIAUTE})
    inf = ET.SubElement(root, "infDPS", {"Id": _id_dps(cod_mun, doc_prest, serie, numero)})

    _sub(inf, "tpAmb", ambiente)
    _sub(inf, "dhEmi", dh_emi.strftime("%Y-%m-%dT%H:%M:%S") + dh_emi.strftime("%z")[:3] + ":" + dh_emi.strftime("%z")[3:])
    _sub(inf, "verAplic", (versao_app or "adge-nf-downloader")[:20])
    _sub(inf, "serie", serie)
    _sub(inf, "nDPS", str(numero))
    _sub(inf, "dCompet", campos["data_emissao"])
    _sub(inf, "tpEmit", "1")  # só prestador emitindo, único fluxo suportado
    _sub(inf, "cLocEmi", cod_mun)

    el_prest = _sub(inf, "prest")
    if len(doc_prest) == 11:
        _sub(el_prest, "CPF", doc_prest)
    else:
        _sub(el_prest, "CNPJ", doc_prest)
    if prest.get("inscricao_municipal"):
        _sub(el_prest, "IM", prest["inscricao_municipal"])
    if prest.get("nome"):
        _sub(el_prest, "xNome", prest["nome"][:150])
    # prest/end fica de fora: ver limitação no topo do módulo
    reg_trib = _sub(el_prest, "regTrib")
    _sub(reg_trib, "opSimpNac", _OP_SIMP_NAC.get(prest["regime"], "1"))
    _sub(reg_trib, "regEspTrib", _REG_ESP_TRIB_NENHUM)

    toma = campos["tomador"]
    el_toma = _sub(inf, "toma")
    if toma["tipo_documento"] == "cpf":
        _sub(el_toma, "CPF", toma["documento"])
    elif toma["tipo_documento"] == "cnpj":
        _sub(el_toma, "CNPJ", toma["documento"])
    _sub(el_toma, "xNome", (toma["nome"] or "")[:150])
    # toma/end fica de fora: ver limitação no topo do módulo

    serv = _sub(inf, "serv")
    loc_prest = _sub(serv, "locPrest")
    _sub(loc_prest, "cLocPrestacao", cod_mun)  # assunção: município do prestador, ver limitação no topo
    c_serv = _sub(serv, "cServ")
    _sub(c_serv, "cTribNac", campos["servico"]["ctn"].zfill(6))
    _sub(c_serv, "xDescServ", (campos["descricao"] or "")[:2000] or "Serviço prestado")
    if campos["servico"]["nbs"]:
        _sub(c_serv, "cNBS", campos["servico"]["nbs"].zfill(9))
    if campos.get("informacoes_complementares"):
        info_compl = _sub(serv, "infoCompl")
        _sub(info_compl, "xInfComp", campos["informacoes_complementares"][:2000])

    valores = _sub(inf, "valores")
    v_serv_prest = _sub(valores, "vServPrest")
    _sub(v_serv_prest, "vServ", _dec(campos["valores"]["valor_servico"]))
    trib = _sub(valores, "trib")
    issqn = campos["servico"]["issqn"]
    trib_mun = _sub(trib, "tribMun")
    _sub(trib_mun, "tribISSQN", str(issqn.get("trib_issqn", 1)))
    _sub(trib_mun, "tpRetISSQN", str(issqn.get("tp_ret_issqn", 1)))
    pc = campos["valores"]["pis_cofins"]
    if pc:
        trib_fed = _sub(trib, "tribFed")
        pis_cofins = _sub(trib_fed, "piscofins")
        _sub(pis_cofins, "CST", pc["cst_pis"])
        _sub(pis_cofins, "vBCPisCofins", _dec(campos["valores"]["valor_servico"]))
        _sub(pis_cofins, "pAliqPis", _dec(pc["aliquota_pis"]))
        _sub(pis_cofins, "pAliqCofins", _dec(pc["aliquota_cofins"]))
        _sub(pis_cofins, "vPis", _dec(pc["valor_pis"]))
        _sub(pis_cofins, "vCofins", _dec(pc["valor_cofins"]))
        _sub(pis_cofins, "tpRetPisCofins", str(pc["tp_ret_pis_cofins"]))
    tot_trib = _sub(trib, "totTrib")
    if prest["regime"] == "simples":
        raise ErroAdge(
            "totTrib para Simples Nacional (ME/EPP) ainda não implementado: precisa do percentual "
            "aproximado dos tributos (pTotTribSN), que não está no cadastro hoje.")
    _sub(tot_trib, "indTotTrib", "0")

    return ET.tostring(root, encoding="unicode")
