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
- `prest/end` (opcional no leiaute, `end` minOccurs="0") só entra se `empresa_emissao["endereco"]`
  tiver logradouro preenchido (campo do Dev A, `v2/config-emissao` commit 36caf9b).
- `toma/end` (também opcional) só entra se o tomador casado tiver endereço estruturado completo
  (logradouro + código IBGE do município) — tomador não casado ou cadastrado só com documento fica
  sem esse grupo, o que é válido no leiaute.
- `cLocPrestacao` usa o código IBGE do ENDEREÇO DO TOMADOR quando disponível (ex.: locação de imóvel,
  onde o serviço ocorre no município do imóvel) e cai para o município do prestador quando não há
  esse dado — mesma limitação de antes, mas só nos casos em que o tomador não tem o IBGE cadastrado.
- `atvEvento` não é usado ainda (fora do escopo atual).
- `IBSCBS` (grupo opcional, reforma tributária) é montado por `_montar_ibscbs` quando
  `lancamento.incluir_ibscbs=True` — validado contra o XSD de produção RESTRITA/homologação
  (`tests/fixtures/xsd_ibscbs/`), porque esse grupo ainda não existe no XSD de produção vigente
  usado pelo resto deste arquivo. Campos do leiaute v1.04.01 sem XSD oficial publicado (condomínios,
  pagamento vinculado/PSP, indZFMALC, indDoacao, estorno de crédito, pagamento antecipado) ficam
  de fora — ver `config_schema.py`.
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


def _so_digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def _dec(valor: float) -> str:
    return f"{float(valor or 0):.2f}"


def _tipo_documento(documento: str) -> str:
    n = len(_so_digitos(documento))
    return "cnpj" if n == 14 else "cpf" if n == 11 else ""


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
    # Sem data de prestação informada, o padrão é o último dia da competência - mas a Sefin
    # Nacional rejeita (E0015) um dCompet depois do dhEmi (data/hora de emissão), e isso acontece
    # sempre que a competência é o mês corrente e ainda não chegou no fim do mês (achado no teste
    # real da Aparecida em 24/11: competência 2026-11, sem data de prestação -> caiu em 30/11,
    # depois de hoje). `min(..., hoje)` corrige isso sem mudar nada para competências já encerradas
    # (onde o último dia do mês já é <= hoje de qualquer forma).
    data_emissao = lancamento.data_prestacao or min(limites_mes(ano, mes)[1], dt.date.today()).isoformat()
    return {
        "prestador": {
            "cnpj": _so_digitos(empresa.get("cnpj", "")),
            "nome": empresa.get("nome", ""),
            "inscricao_municipal": empresa_emissao.get("inscricao_municipal", ""),
            "codigo_municipio_ibge": empresa_emissao.get("codigo_municipio_ibge", ""),
            "regime": empresa_emissao.get("regime", ""),
            "regime_especial_tributacao": empresa_emissao.get("regime_especial_tributacao", 0),
            "percentual_tributos_federais": empresa_emissao.get("percentual_tributos_federais", 0.0),
            "percentual_tributos_estaduais": empresa_emissao.get("percentual_tributos_estaduais", 0.0),
            "percentual_tributos_municipais": empresa_emissao.get("percentual_tributos_municipais", 0.0),
            "aliquota_simples_mes": (empresa_emissao.get("simples") or {}).get("aliquota_mes", 0.0),
            "endereco": dict(empresa_emissao.get("endereco") or {}),
            "telefone": empresa_emissao.get("telefone", ""), "email": empresa_emissao.get("email", ""),
        },
        "tomador": {
            "nome": lancamento.tomador_nome, "documento": lancamento.tomador_documento,
            "tipo_documento": lancamento.tipo_documento,
            "endereco": dict((tomador or {}).get("endereco") or {}),
            "telefone": (tomador or {}).get("telefone", ""), "email": (tomador or {}).get("email", ""),
            "nif": lancamento.nif or (tomador or {}).get("nif", ""),
            "motivo_sem_nif": lancamento.motivo_sem_nif or (tomador or {}).get("motivo_sem_nif", ""),
        },
        "intermediario": {
            "nome": lancamento.intermediario_nome, "documento": lancamento.intermediario_documento,
            "tipo_documento": _tipo_documento(lancamento.intermediario_documento),
        } if lancamento.intermediario_nome else None,
        "substituicao": {
            "chave": lancamento.substituicao_chave, "motivo": lancamento.substituicao_motivo,
            "motivo_texto": lancamento.substituicao_motivo_texto,
        } if lancamento.substituicao_chave else None,
        "servico": {
            "ctn": _codigo(perfil["ctn"]), "nbs": _codigo(perfil["nbs"]),
            "issqn": dict(perfil.get("issqn") or es.issqn_padrao()),
            "obra_codigo": lancamento.obra_codigo, "obra_cib": lancamento.obra_cib,
            "obra_inscricao_imobiliaria": lancamento.obra_inscricao_imobiliaria,
            "obra_endereco": {
                "cep": lancamento.obra_end_cep, "logradouro": lancamento.obra_end_logradouro,
                "numero": lancamento.obra_end_numero, "complemento": lancamento.obra_end_complemento,
                "bairro": lancamento.obra_end_bairro,
                "cod_postal_exterior": lancamento.obra_end_postal_exterior,
                "cidade_exterior": lancamento.obra_end_cidade_exterior,
                "estado_exterior": lancamento.obra_end_estado_exterior,
            },
            "exportacao_moeda": lancamento.exportacao_moeda, "exportacao_valor_moeda": lancamento.exportacao_valor_moeda,
        },
        "valores": {
            "valor_servico": lancamento.valor, "pis_cofins": _pis_cofins(empresa_emissao, perfil, lancamento),
            "desconto_incondicionado": lancamento.desconto_incondicionado, "desconto_condicionado": lancamento.desconto_condicionado,
            "deducao_valor": lancamento.deducao_valor,
            # tribFed inteiro é proibido pro MEI (RN 518) — zera as retenções pra não montar o grupo.
            "retencao_cp": 0.0 if es.pis_cofins_regra(empresa_emissao.get("regime", "")) == "proibido" else lancamento.retencao_cp,
            "retencao_irrf": 0.0 if es.pis_cofins_regra(empresa_emissao.get("regime", "")) == "proibido" else lancamento.retencao_irrf,
            "retencao_csll_outros": 0.0 if es.pis_cofins_regra(empresa_emissao.get("regime", "")) == "proibido" else lancamento.retencao_csll_outros,
        },
        "descricao": es.descricao_efetiva(perfil, tomador, mes, ano),
        "informacoes_complementares": es.informacoes_complementares_efetivas(perfil, tomador),
        "competencia": lancamento.competencia,
        "data_emissao": data_emissao,
        "ibscbs": _ibscbs(lancamento) if lancamento.incluir_ibscbs else None,
    }


def _ibscbs(lancamento) -> dict:
    """Monta o dict normalizado do grupo IBSCBS a partir dos campos `ibscbs_*` do lançamento
    (ver `lancamento.py`). Só chamada quando `incluir_ibscbs=True`; `montar_xml` decide o que de
    fato emitir (campos vazios/grupos incompletos são omitidos, nunca emitidos quebrados)."""
    ind_dest = lancamento.ibscbs_ind_dest or "0"
    dest = None
    if ind_dest == "1":
        dest = {
            "documento": lancamento.ibscbs_dest_documento, "nif": lancamento.ibscbs_dest_nif,
            "motivo_sem_nif": lancamento.ibscbs_dest_motivo_sem_nif, "nome": lancamento.ibscbs_dest_nome,
            "endereco": dict(lancamento.ibscbs_dest_endereco or {}),
            "telefone": lancamento.ibscbs_dest_telefone, "email": lancamento.ibscbs_dest_email,
        }
    imovel = None
    if lancamento.ibscbs_imovel_cmun:
        imovel = {
            "cmun": lancamento.ibscbs_imovel_cmun,
            "locacao": {
                "pcopropriedade": lancamento.ibscbs_imovel_pcopropriedade,
                "vtotoper": lancamento.ibscbs_imovel_vtotoper,
                "vdescincondtot": lancamento.ibscbs_imovel_vdescincondtot,
                "vdesccondtot": lancamento.ibscbs_imovel_vdesccondtot,
                "dvencorig": lancamento.ibscbs_imovel_dvencorig,
            } if lancamento.ibscbs_imovel_vtotoper else None,
            "unidades": [dict(u) for u in (lancamento.ibscbs_unidades_imobiliarias or [])],
        }
    return {
        "ind_final": lancamento.ibscbs_ind_final, "c_ind_op": lancamento.ibscbs_c_ind_op,
        "tp_oper": lancamento.ibscbs_tp_oper, "ref_nfse": list(lancamento.ibscbs_ref_nfse or []),
        "tp_ente_gov": lancamento.ibscbs_tp_ente_gov, "ind_dest": ind_dest, "dest": dest, "imovel": imovel,
        "bens_moveis": [dict(b) for b in (lancamento.ibscbs_bens_moveis or [])],
        "cst": lancamento.ibscbs_cst, "cclasstrib": lancamento.ibscbs_cclasstrib,
        "c_cred_pres": lancamento.ibscbs_c_cred_pres,
        "cst_reg": lancamento.ibscbs_cst_reg, "cclasstrib_reg": lancamento.ibscbs_cclasstrib_reg,
        "p_dif_uf": lancamento.ibscbs_p_dif_uf, "p_dif_mun": lancamento.ibscbs_p_dif_mun,
        "p_dif_cbs": lancamento.ibscbs_p_dif_cbs,
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


def _end_nacional(pai, endereco: dict, cod_mun_ibge: str):
    """`TCEndereco`: `endNac` (cMun + CEP) seguido de xLgr/nro/xCpl?/xBairro — mesma estrutura do
    XSD tanto pra `prest/end` quanto `toma/end`. Só chamar quando `logradouro` e `cod_mun_ibge`
    estiverem preenchidos (o grupo inteiro é opcional; não dá pra mandar incompleto)."""
    end = _sub(pai, "end")
    end_nac = _sub(end, "endNac")
    _sub(end_nac, "cMun", cod_mun_ibge)
    _sub(end_nac, "CEP", _so_digitos(endereco.get("cep", "")))
    _sub(end, "xLgr", endereco["logradouro"][:255])
    _sub(end, "nro", (endereco.get("numero") or "S/N")[:10])
    if endereco.get("complemento"):
        _sub(end, "xCpl", endereco["complemento"][:60])
    _sub(end, "xBairro", (endereco.get("bairro") or "Centro")[:60])


def _end_exterior(pai, endereco: dict):
    """`TCEndereco`: `endExt` (país, código postal, cidade, estado/província - todos obrigatórios
    em `TCEnderExt`) seguido de xLgr/nro/xCpl?/xBairro, mesmo grupo compartilhado do endereço
    nacional. Usado só pro tomador identificado por NIF (E0242) - este app não tem isso pro
    prestador nem intermediário."""
    end = _sub(pai, "end")
    end_ext = _sub(end, "endExt")
    _sub(end_ext, "cPais", endereco["pais"][:2].upper())
    _sub(end_ext, "cEndPost", endereco["codigo_postal"][:11])
    _sub(end_ext, "xCidade", endereco["cidade"][:60])
    _sub(end_ext, "xEstProvReg", endereco["estado_provincia"][:60])
    _sub(end, "xLgr", endereco["logradouro"][:255])
    _sub(end, "nro", (endereco.get("numero") or "S/N")[:10])
    if endereco.get("complemento"):
        _sub(end, "xCpl", endereco["complemento"][:60])
    _sub(end, "xBairro", (endereco.get("bairro") or "Centro")[:60])


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

    subst = campos.get("substituicao")
    if subst:
        el_subst = _sub(inf, "subst")
        _sub(el_subst, "chSubstda", subst["chave"])
        _sub(el_subst, "cMotivo", subst["motivo"] or "99")
        if subst.get("motivo_texto"):
            _sub(el_subst, "xMotivo", subst["motivo_texto"][:255])

    # Rejeição real em produção (E0121/E0128, teste da Aparecida em 24/11): quando o emitente da
    # DPS é o próprio prestador (tpEmit=1, único fluxo suportado por este programa), o nome/razão
    # social e o endereço do prestador NÃO PODEM entrar no XML (regra de negócio oficial - o
    # cadastro nacional do CNPJ já tem esses dados, enviar de novo é redundância que a Sefin
    # recusa). Telefone e e-mail NÃO entram nessa proibição (só xNome/E0121 e end/E0128) -
    # confirmado comparando com uma nota real emitida manualmente pelo Abner, que traz os dois.
    el_prest = _sub(inf, "prest")
    if len(doc_prest) == 11:
        _sub(el_prest, "CPF", doc_prest)
    else:
        _sub(el_prest, "CNPJ", doc_prest)
    if prest.get("inscricao_municipal"):
        _sub(el_prest, "IM", prest["inscricao_municipal"])
    fone_prest = _so_digitos(prest.get("telefone", ""))
    if len(fone_prest) >= 6:
        _sub(el_prest, "fone", fone_prest[:20])
    if prest.get("email"):
        _sub(el_prest, "email", prest["email"][:80])
    reg_trib = _sub(el_prest, "regTrib")
    _sub(reg_trib, "opSimpNac", _OP_SIMP_NAC.get(prest["regime"], "1"))
    _sub(reg_trib, "regEspTrib", str(prest.get("regime_especial_tributacao") or 0))

    toma = campos["tomador"]
    el_toma = _sub(inf, "toma")
    toma_e_nif = False
    if toma["tipo_documento"] == "cpf":
        _sub(el_toma, "CPF", toma["documento"])
    elif toma["tipo_documento"] == "cnpj":
        _sub(el_toma, "CNPJ", toma["documento"])
    elif toma.get("nif"):
        _sub(el_toma, "NIF", toma["nif"][:40])
        toma_e_nif = True
    elif toma.get("motivo_sem_nif"):
        _sub(el_toma, "cNaoNIF", str(toma["motivo_sem_nif"]))
    else:
        raise ErroAdge("Tomador sem CPF/CNPJ, NIF ou motivo de ausência de NIF — a nota precisa de um deles.")
    _sub(el_toma, "xNome", (toma["nome"] or "")[:150])
    end_toma = toma.get("endereco") or {}
    cod_mun_toma = _so_digitos(end_toma.get("codigo_municipio_ibge", ""))
    tem_end_nacional_toma = bool(end_toma.get("logradouro") and cod_mun_toma)
    tem_end_exterior_toma = bool(end_toma.get("logradouro") and end_toma.get("pais")
                                  and end_toma.get("codigo_postal") and end_toma.get("cidade")
                                  and end_toma.get("estado_provincia"))
    if toma_e_nif:
        # E0242: com o prestador identificado por CNPJ (sempre o caso aqui) e o tomador por NIF,
        # `toma/end/endExt` é obrigatório - sem exceção, porque este app não emite pelo tomador/
        # intermediário (tpEmit sempre 1).
        if not tem_end_exterior_toma:
            raise ErroAdge(
                "Tomador identificado por NIF precisa do endereço no exterior completo na DPS "
                "(país, código postal, cidade, estado/província, logradouro e número) - "
                "complete o cadastro do tomador (E0242).")
        _end_exterior(el_toma, end_toma)
    else:
        if not tem_end_nacional_toma:
            # Endereço do tomador é opcional no leiaute em geral, mas duas regras de negócio
            # oficiais (confirmadas na auditoria de 24/11) o tornam OBRIGATÓRIO: E0235 (tomador
            # identificado por CNPJ, com tpEmit=1) e E0237 (ISSQN retido pelo tomador,
            # tpRetISSQN=2 - exceto quando o próprio tomador é o emitente, o que não acontece
            # neste app). Bloquear com erro claro em vez de mandar uma DPS incompleta.
            if toma["tipo_documento"] == "cnpj":
                raise ErroAdge(
                    "Tomador com CNPJ precisa de endereço nacional completo na DPS (E0235) — "
                    "complete o cadastro do tomador.")
            if campos["servico"]["issqn"].get("tp_ret_issqn") == 2:
                raise ErroAdge(
                    "ISSQN retido pelo tomador exige o endereço nacional completo do tomador na "
                    "DPS (E0237) — complete o cadastro do tomador.")
        if tem_end_nacional_toma:
            _end_nacional(el_toma, end_toma, cod_mun_toma)
    fone_toma = _so_digitos(toma.get("telefone", ""))
    if len(fone_toma) >= 6:
        _sub(el_toma, "fone", fone_toma[:20])
    if toma.get("email"):
        _sub(el_toma, "email", toma["email"][:80])

    interm = campos.get("intermediario")
    if interm:
        el_interm = _sub(inf, "interm")
        if interm["tipo_documento"] == "cpf":
            _sub(el_interm, "CPF", interm["documento"])
        elif interm["tipo_documento"] == "cnpj":
            _sub(el_interm, "CNPJ", interm["documento"])
        else:
            raise ErroAdge("Intermediário informado sem CPF/CNPJ válido.")
        _sub(el_interm, "xNome", (interm["nome"] or "")[:150])

    serv = _sub(inf, "serv")
    loc_prest = _sub(serv, "locPrest")
    # Município do serviço: o do endereço do tomador quando tiver IBGE cadastrado (ex.: locação de
    # imóvel, onde o serviço ocorre no município do imóvel), senão o do prestador (ver limitação no topo).
    _sub(loc_prest, "cLocPrestacao", cod_mun_toma or cod_mun)
    c_serv = _sub(serv, "cServ")
    _sub(c_serv, "cTribNac", campos["servico"]["ctn"].zfill(6))
    _sub(c_serv, "xDescServ", (campos["descricao"] or "")[:2000] or "Serviço prestado")
    # `cNBS` vem DEPOIS de `xDescServ` (ordem confirmada contra o XSD de produção vigente,
    # `TCServ`) - a análise anterior achava que essa ordem só valia pra homologação e que
    # produção queria `cNBS` antes; estava errada (rodei o XML real contra os dois XSDs em 24/11
    # e só esta ordem valida nos dois).
    if campos["servico"]["nbs"]:
        _sub(c_serv, "cNBS", campos["servico"]["nbs"].zfill(9))
    moeda = campos["servico"].get("exportacao_moeda")
    if moeda:
        com_ext = _sub(serv, "comExt")
        _sub(com_ext, "mdPrestacao", "0")   # Desconhecido — não perguntado nesta versão
        _sub(com_ext, "vincPrest", "0")     # Sem vínculo entre as partes — padrão
        _sub(com_ext, "tpMoeda", _so_digitos(moeda).zfill(3)[:3])
        _sub(com_ext, "vServMoeda", _dec(campos["servico"].get("exportacao_valor_moeda")))
        _sub(com_ext, "mecAFComexP", "01")  # Nenhum mecanismo de fomento — padrão
        _sub(com_ext, "mecAFComexT", "01")  # Nenhum mecanismo de fomento — padrão
        _sub(com_ext, "movTempBens", "1")   # Não há movimentação temporária de bens — padrão
        _sub(com_ext, "mdic", "0")          # Não compartilhar com o MDIC — padrão
    obra_codigo, obra_cib = campos["servico"].get("obra_codigo"), campos["servico"].get("obra_cib")
    obra_end = campos["servico"].get("obra_endereco") or {}
    cep_obra = _so_digitos(obra_end.get("cep", ""))
    tem_obra_end_nacional = bool(cep_obra and obra_end.get("logradouro") and obra_end.get("bairro"))
    tem_obra_end_exterior = bool(obra_end.get("cod_postal_exterior") and obra_end.get("cidade_exterior")
                                  and obra_end.get("estado_exterior") and obra_end.get("logradouro")
                                  and obra_end.get("bairro"))
    if obra_codigo or obra_cib or tem_obra_end_nacional or tem_obra_end_exterior:
        el_obra = _sub(serv, "obra")
        if campos["servico"].get("obra_inscricao_imobiliaria"):
            _sub(el_obra, "inscImobFisc", campos["servico"]["obra_inscricao_imobiliaria"][:30])
        if obra_codigo:
            _sub(el_obra, "cObra", obra_codigo[:30])
        elif obra_cib:
            _sub(el_obra, "cCIB", obra_cib)  # TSCodCIB: exatamente 8 caracteres, sem truncar
        else:
            el_end_obra = _sub(el_obra, "end")
            if tem_obra_end_nacional:
                _sub(el_end_obra, "CEP", cep_obra[:8])
            else:
                end_ext = _sub(el_end_obra, "endExt")
                _sub(end_ext, "cEndPost", obra_end["cod_postal_exterior"][:15])
                _sub(end_ext, "xCidade", obra_end["cidade_exterior"][:60])
                _sub(end_ext, "xEstProvReg", obra_end["estado_exterior"][:60])
            _sub(el_end_obra, "xLgr", obra_end.get("logradouro", "")[:125])
            _sub(el_end_obra, "nro", (obra_end.get("numero") or "S/N")[:10])
            if obra_end.get("complemento"):
                _sub(el_end_obra, "xCpl", obra_end["complemento"][:60])
            _sub(el_end_obra, "xBairro", obra_end.get("bairro", "")[:60])
    if campos.get("informacoes_complementares"):
        info_compl = _sub(serv, "infoCompl")
        _sub(info_compl, "xInfComp", campos["informacoes_complementares"][:2000])

    valores = _sub(inf, "valores")
    v_serv_prest = _sub(valores, "vServPrest")
    _sub(v_serv_prest, "vServ", _dec(campos["valores"]["valor_servico"]))
    desc_incond = campos["valores"].get("desconto_incondicionado") or 0.0
    desc_cond = campos["valores"].get("desconto_condicionado") or 0.0
    if desc_incond or desc_cond:
        v_desc = _sub(valores, "vDescCondIncond")
        if desc_incond:
            _sub(v_desc, "vDescIncond", _dec(desc_incond))
        if desc_cond:
            _sub(v_desc, "vDescCond", _dec(desc_cond))
    deducao = campos["valores"].get("deducao_valor") or 0.0
    if deducao:
        v_ded = _sub(valores, "vDedRed")
        _sub(v_ded, "vDR", _dec(deducao))
    trib = _sub(valores, "trib")
    issqn = campos["servico"]["issqn"]
    trib_mun = _sub(trib, "tribMun")
    _sub(trib_mun, "tribISSQN", str(issqn.get("trib_issqn", 1)))
    _sub(trib_mun, "tpRetISSQN", str(issqn.get("tp_ret_issqn", 1)))
    pc = campos["valores"]["pis_cofins"]
    ret_cp = campos["valores"].get("retencao_cp") or 0.0
    ret_irrf = campos["valores"].get("retencao_irrf") or 0.0
    ret_csll_outros = campos["valores"].get("retencao_csll_outros") or 0.0
    if pc or ret_cp or ret_irrf or ret_csll_outros:
        trib_fed = _sub(trib, "tribFed")
        if pc:
            pis_cofins = _sub(trib_fed, "piscofins")
            _sub(pis_cofins, "CST", pc["cst_pis"])
            _sub(pis_cofins, "vBCPisCofins", _dec(campos["valores"]["valor_servico"]))
            _sub(pis_cofins, "pAliqPis", _dec(pc["aliquota_pis"]))
            _sub(pis_cofins, "pAliqCofins", _dec(pc["aliquota_cofins"]))
            _sub(pis_cofins, "vPis", _dec(pc["valor_pis"]))
            _sub(pis_cofins, "vCofins", _dec(pc["valor_cofins"]))
            _sub(pis_cofins, "tpRetPisCofins", str(pc["tp_ret_pis_cofins"]))
        if ret_cp:
            _sub(trib_fed, "vRetCP", _dec(ret_cp))
        if ret_irrf:
            _sub(trib_fed, "vRetIRRF", _dec(ret_irrf))
        if ret_csll_outros:
            _sub(trib_fed, "vRetCSLL", _dec(ret_csll_outros))
    # `trib/totTrib` é um choice e a opção certa depende da situação da empresa perante o Simples
    # Nacional (confirmado contra as regras de negócio oficiais E0710/E0712/E0713 - rejeição real em
    # produção, teste da Aparecida em 24/11): MEI usa só indTotTrib (fixo em "0"); ME/EPP optante usa
    # só pTotTribSN (percentual da alíquota efetiva do Simples do mês, já cadastrado em
    # `cfg["simples"]["aliquota_mes"]` pro PGDAS-D - reaproveitado aqui, nunca 0% porque seria uma
    # alíquota falsa); quem não é optante (presumido/real) não pode usar NENHUM dos dois - só
    # vTotTrib ou pTotTrib (valores aproximados da Lei 12.741/2012, aceitando 0% quando não há
    # estimativa melhor no cadastro - essa parte, sim, o Decreto 8.264/2014 permite).
    tot_trib = _sub(trib, "totTrib")
    if prest["regime"] == "simples":
        aliquota_simples = prest.get("aliquota_simples_mes") or 0.0
        if not aliquota_simples:
            raise ErroAdge(
                "Falta a alíquota do Simples Nacional do mês (Configurar emissão → Empresa) - "
                "obrigatória para quem é optante do Simples (ME/EPP), pTotTribSN não pode ir vazio "
                "nem com 0% (seria uma alíquota falsa, diferente da aliquota_mes já usada no "
                "PGDAS-D) - preencha antes de emitir.")
        _sub(tot_trib, "pTotTribSN", _dec(aliquota_simples * 100))
    elif prest["regime"] == "mei":
        _sub(tot_trib, "indTotTrib", "0")
    else:
        p_tot_trib = _sub(tot_trib, "pTotTrib")
        _sub(p_tot_trib, "pTotTribFed", _dec(prest.get("percentual_tributos_federais") or 0.0))
        _sub(p_tot_trib, "pTotTribEst", _dec(prest.get("percentual_tributos_estaduais") or 0.0))
        _sub(p_tot_trib, "pTotTribMun", _dec(prest.get("percentual_tributos_municipais") or 0.0))

    ibscbs = campos.get("ibscbs")
    if ibscbs:
        _montar_ibscbs(inf, ibscbs)

    # `encoding="unicode"` nunca inclui `<?xml version="1.0" encoding="UTF-8"?>` — a Sefin Nacional
    # recusa isso de verdade (erro E1229 "Xml não está utilizando codificação UTF-8", confirmado em
    # transmissão real em 20/11/2026), mesmo o XML por dentro já sendo UTF-8 correto. `encoding="UTF-8"`
    # + `xml_declaration=True` resolve: continua batendo com o XSD (a declaração não muda o conteúdo).
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True).decode("utf-8")


def _montar_ibscbs(inf, ibscbs: dict) -> None:
    """`IBSCBS` (sibling de `valores`, último filho de `infDPS`) — ordem e grupos batidos com o
    XSD oficial de PRODUÇÃO vigente (`tests/fixtures/xsd/tiposComplexos_v1.01.xsd`, `TCRTCInfoIBSCBS`
    dentro de `TCInfDPS`): o grupo IBSCBS JÁ EXISTE lá (confirmado rodando o XML real da Ferreira
    Maria contra esse XSD em 24/11 - análise anterior, que achava que não existia e validava só
    contra homologação/`tests/fixtures/xsd_ibscbs/`, estava errada). `finNFSe` é o PRIMEIRO campo
    de dentro do próprio `IBSCBS` (não um campo de `infDPS`, como a análise anterior também errou) -
    por isso entra aqui, e não lá em cima junto de `tpEmit`/`cLocEmi`. `CST`/`cClassTrib` são
    obrigatórios (`Lancamento.validar` já bloqueia nota sem eles); o resto é omitido quando incompleto."""
    el = _sub(inf, "IBSCBS")
    _sub(el, "finNFSe", "0")  # indicador de finalidade - só "0" (regular) existe hoje
    if ibscbs.get("ind_final"):
        _sub(el, "indFinal", ibscbs["ind_final"])
    if ibscbs.get("c_ind_op"):
        _sub(el, "cIndOp", _so_digitos(ibscbs["c_ind_op"]).zfill(6)[:6])
    if ibscbs.get("tp_oper"):
        _sub(el, "tpOper", ibscbs["tp_oper"])
    refs = [r for r in (ibscbs.get("ref_nfse") or []) if r]
    if refs:
        g_ref = _sub(el, "gRefNFSe")
        for chave in refs:
            _sub(g_ref, "refNFSe", chave)
    if ibscbs.get("tp_ente_gov"):
        _sub(el, "tpEnteGov", ibscbs["tp_ente_gov"])
    _sub(el, "indDest", ibscbs.get("ind_dest") or "0")

    dest = ibscbs.get("dest")
    if dest and (dest.get("nome") or "").strip():
        el_dest = _sub(el, "dest")
        tipo_dest = _tipo_documento(dest.get("documento", ""))
        if tipo_dest == "cpf":
            _sub(el_dest, "CPF", _so_digitos(dest["documento"]))
        elif tipo_dest == "cnpj":
            _sub(el_dest, "CNPJ", _so_digitos(dest["documento"]))
        elif dest.get("nif"):
            _sub(el_dest, "NIF", dest["nif"][:40])
        elif dest.get("motivo_sem_nif"):
            _sub(el_dest, "cNaoNIF", str(dest["motivo_sem_nif"]))
        else:
            raise ErroAdge("IBS/CBS: destinatário diferente do tomador sem CPF/CNPJ, NIF ou motivo de ausência de NIF.")
        _sub(el_dest, "xNome", dest["nome"][:150])
        end_dest = dest.get("endereco") or {}
        cod_mun_dest = _so_digitos(end_dest.get("codigo_municipio_ibge", ""))
        if end_dest.get("logradouro") and cod_mun_dest:
            _end_nacional(el_dest, end_dest, cod_mun_dest)
        fone_dest = _so_digitos(dest.get("telefone", ""))
        if len(fone_dest) >= 6:
            _sub(el_dest, "fone", fone_dest[:20])
        if dest.get("email"):
            _sub(el_dest, "email", dest["email"][:80])

    imovel = ibscbs.get("imovel")
    if imovel and imovel.get("cmun"):
        el_imovel = _sub(el, "imovel")
        _sub(el_imovel, "cMun", imovel["cmun"])
        locacao = imovel.get("locacao")
        if locacao:
            el_loc = _sub(el_imovel, "gLocacao")
            _sub(el_loc, "pCopropriedade", _dec(locacao.get("pcopropriedade") or 100.0))
            _sub(el_loc, "vTotOper", _dec(locacao["vtotoper"]))
            if locacao.get("vdescincondtot"):
                _sub(el_loc, "vDescIncondTot", _dec(locacao["vdescincondtot"]))
            if locacao.get("vdesccondtot"):
                _sub(el_loc, "vDescCondTot", _dec(locacao["vdesccondtot"]))
            if locacao.get("dvencorig"):
                _sub(el_loc, "dVencOrig", locacao["dvencorig"])
        for unidade in imovel.get("unidades") or []:
            endereco_un = unidade.get("endereco") or {}
            end_valido = bool(endereco_un.get("cep") and endereco_un.get("logradouro"))
            if not unidade.get("cib") and not end_valido:
                continue  # unidade incompleta (sem CIB nem endereço válido) — não monta quebrada
            el_un = _sub(el_imovel, "gUnidImob")
            if unidade.get("inscimobfisc"):
                _sub(el_un, "inscImobFisc", unidade["inscimobfisc"][:30])
            if unidade.get("cib"):
                _sub(el_un, "cCIB", unidade["cib"])
            else:
                el_end_un = _sub(el_un, "end")
                _sub(el_end_un, "CEP", _so_digitos(endereco_un.get("cep", "")).zfill(8)[:8])
                _sub(el_end_un, "xLgr", endereco_un["logradouro"][:255])
                _sub(el_end_un, "nro", (endereco_un.get("numero") or "S/N")[:60])
                if endereco_un.get("complemento"):
                    _sub(el_end_un, "xCpl", endereco_un["complemento"][:156])
                if endereco_un.get("bairro"):
                    _sub(el_end_un, "xBairro", endereco_un["bairro"][:60])
            for ajuste in unidade.get("ajustes") or []:
                if not ajuste.get("tipo"):
                    continue
                el_aj = _sub(el_un, "gAjusteBCLocImoveis")
                _sub(el_aj, "tpAjusteBCLocImoveis", ajuste["tipo"])
                if ajuste.get("descricao"):
                    _sub(el_aj, "xTpAjusteBCLocImoveis", ajuste["descricao"][:150])
                _sub(el_aj, "vAjusteBCLocImoveis", _dec(ajuste.get("valor")))

    for bem in ibscbs.get("bens_moveis") or []:
        if not bem.get("ncm"):
            continue
        el_bem = _sub(el, "bensMoveis")
        _sub(el_bem, "cNCMBemMovel", _so_digitos(bem["ncm"]).zfill(8)[:8])
        _sub(el_bem, "xNCMBemMovel", (bem.get("descricao") or "")[:150])
        _sub(el_bem, "qtdNCMBemMovel", str(int(bem.get("quantidade") or 1)))

    if not ibscbs.get("cst") or not ibscbs.get("cclasstrib"):
        raise ErroAdge("IBS/CBS: falta o CST ou o cClassTrib (Lancamento.validar deveria ter bloqueado antes).")
    # `IBSCBS/valores/trib/gIBSCBS` é obrigatório e é onde CST/cClassTrib realmente moram (achado na
    # auditoria de 24/11, rodando o XML real contra o XSD de produção vigente: a versão anterior
    # deste código colocava CST/cClassTrib direto em `trib`, fora de `gIBSCBS`, e só criava
    # `gIBSCBS` quando havia crédito presumido/tributação regular/diferimento - por isso validava
    # contra o XSD de homologação, que tolerava isso, mas não contra o de produção).
    el_valores = _sub(el, "valores")
    el_trib = _sub(el_valores, "trib")
    el_g = _sub(el_trib, "gIBSCBS")
    _sub(el_g, "CST", ibscbs["cst"].zfill(3)[:3])
    _sub(el_g, "cClassTrib", ibscbs["cclasstrib"].zfill(6)[:6])
    if ibscbs.get("c_cred_pres"):
        _sub(el_g, "cCredPres", ibscbs["c_cred_pres"].zfill(2)[:2])
    if ibscbs.get("cst_reg") and ibscbs.get("cclasstrib_reg"):
        el_reg = _sub(el_g, "gTribRegular")
        _sub(el_reg, "CSTReg", ibscbs["cst_reg"].zfill(3)[:3])
        _sub(el_reg, "cClassTribReg", ibscbs["cclasstrib_reg"].zfill(6)[:6])
    if ibscbs.get("p_dif_uf") or ibscbs.get("p_dif_mun") or ibscbs.get("p_dif_cbs"):
        el_dif = _sub(el_g, "gDif")
        _sub(el_dif, "pDifUF", _dec(ibscbs.get("p_dif_uf")))
        _sub(el_dif, "pDifMun", _dec(ibscbs.get("p_dif_mun")))
        _sub(el_dif, "pDifCBS", _dec(ibscbs.get("p_dif_cbs")))
