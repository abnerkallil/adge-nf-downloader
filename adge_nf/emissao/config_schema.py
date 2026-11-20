"""Schema versionado da configuração fixa de emissão de NFS-e por empresa (V2.0).

Fica em `empresa["emissao"]`, ao lado de `empresa["fiscal"]` (simulação de regimes, não mexe aqui).
Este módulo só define a forma dos dados e migrações entre versões: não faz nenhuma chamada à API
da NFS-e Nacional nem monta a DPS (isso é do motor de emissão).

Campos e enums batidos com o leiaute oficial da DPS em produção (anexo_i-sefin_adn-dps_nfse-snnfse-v1-01-20260209.xlsx,
lido pela thread de pesquisa, não de memória): `TRIB_ISSQN` (`tribMun/tribISSQN`), `TP_RET_ISSQN` (`tribMun/tpRetISSQN`)
e `TP_RET_PISCOFINS` (`tribFed/piscofins/tpRetPisCofins`, 0-9 — confirmado pela thread do motor de emissão direto no
XSD oficial, `TSTipoRetPISCofins` em `tiposSimples_v1.01.xsd`). `cst_pis`/`cst_cofins` ainda ficam texto livre: o CST
não é uma faixa contínua (é uma lista fechada de 34 valores confirmada no XSD, `TSTipoCST`) — vira combobox quando
tivermos as descrições de cada código.

Reservado para quando sair de homologação: `perfil["ibscbs_futuro"]` (ex.: tpAjusteBCLocImoveis, cClassTrib) —
hoje fica sempre `{}`, sem tela própria ainda.
"""
from __future__ import annotations

import uuid

VERSAO_ATUAL = 1

TRIB_ISSQN = {
    1: "Operação tributável",
    2: "Imunidade",
    3: "Exportação de serviço",
    4: "Não incidência",
}

TP_RET_ISSQN = {
    1: "Não retido",
    2: "Retido pelo tomador",
    3: "Retido pelo intermediário",
}

TP_RET_PISCOFINS = {
    0: "PIS/COFINS/CSLL não retidos",
    1: "PIS/COFINS retidos",
    2: "PIS/COFINS não retidos",
    3: "PIS/COFINS/CSLL retidos",
    4: "PIS/COFINS retidos, CSLL não retido",
    5: "PIS retido, COFINS/CSLL não retido",
    6: "COFINS retido, PIS/CSLL não retido",
    7: "PIS não retido, COFINS/CSLL retidos",
    8: "PIS/COFINS não retidos, CSLL retido",
    9: "COFINS não retido, PIS/CSLL retidos",
}

REGIMES = {
    "mei": "MEI",
    "simples": "Simples Nacional (ME/EPP)",
    "presumido": "Lucro Presumido",
    "real": "Lucro Real",
}

REGIME_ESPECIAL_TRIBUTACAO = {
    0: "Nenhum",
    1: "Ato Cooperado (Cooperativa)",
    2: "Estimativa",
    3: "Microempresa Municipal",
    4: "Notário ou Registrador",
    5: "Profissional Autônomo",
    6: "Sociedade de Profissionais",
    9: "Outros",
}
"""`prest/regTrib/regEspTrib` (leiaute oficial, `TSRegEspTrib`) — 0 é o padrão (nenhum regime
especial); os demais só se aplicam a empresas que realmente se encaixam nessas categorias."""

CST_PISCOFINS_VALIDOS = frozenset((
    "00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "49", "50", "51", "52", "53", "54", "55", "56",
    "60", "61", "62", "63", "64", "65", "66", "67", "70", "71", "72", "73", "74", "75", "98", "99",
))
"""Lista fechada de 34 códigos de CST do PIS/COFINS, confirmada pela thread do motor de emissão
direto no XSD oficial (`TSTipoCST`, `tiposSimples_v1.01.xsd`) — não é uma faixa contínua 00-99."""

PIS_COFINS_REGIMES = {
    "cumulativo": "Cumulativo",
    "nao_cumulativo": "Não cumulativo",
}

DESCRICAO_MODOS = {
    "fixo": "Texto fixo, sem alterações",
    "mes_ano": "Troca {MES}/{ANO} pela competência a cada emissão",
}

TOMADOR_DESCRICAO_MODOS = {
    "herdar": "Usar a descrição do perfil",
    "fixo": "Texto fixo deste tomador",
    "mes_ano": "Texto deste tomador, trocando {MES}/{ANO}",
}

TOMADOR_INFO_MODOS = {
    "herdar": "Usar as informações complementares do perfil",
    "fixo": "Texto fixo deste tomador",
}

MODOS_IDENTIFICACAO = {
    "documento": "Só documento (CPF/CNPJ) — o endereço vem do cadastro do tomador",
    "endereco": "Documento e endereço completo (precisa constar na nota, ex.: locação de imóvel)",
}
TOMADOR_IDENTIFICACAO_MODOS = {"herdar": "Usar o padrão da empresa", **MODOS_IDENTIFICACAO}

MOTIVOS_SUBSTITUICAO = {
    "01": "Desenquadramento de NFS-e do Simples Nacional",
    "02": "Enquadramento de NFS-e no Simples Nacional",
    "03": "Inclusão Retroativa de Imunidade/Isenção para NFS-e",
    "04": "Exclusão Retroativa de Imunidade/Isenção para NFS-e",
    "05": "Rejeição de NFS-e pelo tomador ou pelo intermediário se responsável pelo recolhimento do tributo",
    "99": "Outros",
}
"""`infoDPS/subst/cMotivo` (leiaute oficial, `TSCodJustSubst`) — só usado quando esta nota
substitui uma NFS-e anterior (chave de 50 dígitos em `subst/chSubstda`)."""

NIF_MOTIVOS = {
    "0": "Não informado na nota de origem",
    "1": "Dispensado do NIF",
    "2": "Não exigência do NIF",
}
"""`toma/cNaoNIF` (leiaute oficial, `TSCodNaoNIF`) — só usado quando o tomador é estrangeiro, não
tem CPF/CNPJ nem NIF, e algum desses motivos justifica a ausência."""

MARCADORES = ("{MES}", "{ANO}")

MESES_PT = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
            "Setembro", "Outubro", "Novembro", "Dezembro")


def _id(prefixo: str) -> str:
    return f"{prefixo}_{uuid.uuid4().hex[:10]}"


def pis_cofins_regra(regime: str) -> str:
    """'proibido' (grupo tribFed inteiro proibido pra MEI, RN 518), 'obrigatorio' (Presumido/Real)
    ou 'opcional' (Simples ME/EPP)."""
    if regime == "mei":
        return "proibido"
    if regime in ("presumido", "real"):
        return "obrigatorio"
    return "opcional"


def issqn_regra(regime: str) -> str:
    """'nao_aplica': pra MEI o grupo valores/trib/tribMun inteiro é proibido (RN 49) — o ISS do MEI é
    o valor fixo do DAS-MEI, não entra por nota. 'aplica': todo o resto."""
    return "nao_aplica" if regime == "mei" else "aplica"


# ------------------------------------------------------------------------------------------- padrões
def pis_cofins_padrao() -> dict:
    return {"incluir": False, "regime": "cumulativo", "cst_pis": "", "cst_cofins": "",
            "aliquota_pis": 0.0, "aliquota_cofins": 0.0, "tp_ret_pis_cofins": 0}


def issqn_padrao() -> dict:
    return {"trib_issqn": 1, "tp_ret_issqn": 1}


def perfil_padrao(nome: str = "") -> dict:
    """`ctn` e `nbs` guardam código + descrição juntos, do jeito que o portal mostra no combo
    (ex.: "99.01.01 - Serviços sem a incidência de ISSQN e ICMS"), pra copiar e colar direto.

    `issqn` são os campos oficiais `tribMun/tribISSQN` (1 Tributável, 2 Imunidade, 3 Exportação,
    4 Não incidência) e `tribMun/tpRetISSQN` (1 Não retido, 2 Retido pelo tomador, 3 pelo intermediário).
    """
    return {
        "id": _id("perfil"), "nome": nome, "ativo": True,
        "ctn": "", "nbs": "",
        "issqn": issqn_padrao(),
        "pis_cofins": pis_cofins_padrao(),
        "descricao": {"modo": "fixo", "texto": ""},
        "informacoes_complementares": "",
        "ibscbs_futuro": {},
    }


def endereco_padrao() -> dict:
    return {"cep": "", "logradouro": "", "numero": "", "complemento": "", "bairro": "", "municipio": "", "uf": "",
            "codigo_municipio_ibge": ""}


def endereco_rua_padrao() -> dict:
    """Só a parte de logradouro: usada no endereço do prestador (`cfg["endereco"]`), cujo
    município/UF/código IBGE já ficam direto em `cfg["municipio"]`/`cfg["uf"]`/`cfg["codigo_municipio_ibge"]`
    (não duplica)."""
    return {"cep": "", "logradouro": "", "numero": "", "complemento": "", "bairro": ""}


def tomador_padrao(nome: str = "") -> dict:
    """`modo_identificacao`: "herdar" (usa o padrão da empresa), "documento" (só CPF/CNPJ, endereço vem do
    cadastro) ou "endereco" (a nota precisa do endereço completo, ex.: locação de imóvel). `endereco` só é
    obrigatório preencher quando o modo efetivo for "endereco"; o texto livre dele é só pra ajudar no casamento."""
    return {
        "id": _id("tomador"), "nome": nome, "documento": "",
        "modo_identificacao": "herdar", "endereco": endereco_padrao(), "endereco_livre": "",
        "telefone": "", "email": "",
        "nif": "", "motivo_sem_nif": "",  # tomador estrangeiro sem CPF/CNPJ (raro) — ver NIF_MOTIVOS
        "perfil_id": None,
        "descricao": {"modo": "herdar", "texto": ""},
        "informacoes_complementares": {"modo": "herdar", "texto": ""},
        "ativo": True,
    }


def configuracao_padrao() -> dict:
    perfil = perfil_padrao("Padrão")
    return {
        "versao": VERSAO_ATUAL,
        "regime": "simples", "regime_especial_tributacao": 0,
        "inscricao_municipal": "", "municipio": "", "uf": "", "codigo_municipio_ibge": "",
        "endereco": endereco_rua_padrao(),
        "simples": {"aliquota_mes": 0.0},
        "identificacao_tomador_padrao": "documento",
        "perfis": [perfil],
        "perfil_padrao_id": perfil["id"],
        "tomadores": [],
    }


# ------------------------------------------------------------------------------------------- migração
def migrar(bruto: dict | None) -> dict:
    """Preenche o que falta com o padrão e devolve na versão atual. Não apaga campos desconhecidos
    (uma versão futura pode já ter gravado algo que esta não conhece)."""
    cfg = {**configuracao_padrao(), **(bruto or {})}
    if not cfg.get("perfis"):
        p = perfil_padrao("Padrão")
        cfg["perfis"] = [p]
        cfg["perfil_padrao_id"] = p["id"]
    cfg["perfis"] = [{**perfil_padrao(), **p} for p in cfg["perfis"]]
    for p in cfg["perfis"]:
        p["pis_cofins"] = {**pis_cofins_padrao(), **(p.get("pis_cofins") or {})}
        p["issqn"] = {**issqn_padrao(), **(p.get("issqn") or {})}
        p["descricao"] = {**{"modo": "fixo", "texto": ""}, **(p.get("descricao") or {})}
    ids_perfis = {p["id"] for p in cfg["perfis"]}
    if cfg.get("perfil_padrao_id") not in ids_perfis:
        cfg["perfil_padrao_id"] = cfg["perfis"][0]["id"]
    cfg["tomadores"] = [{**tomador_padrao(), **t} for t in (cfg.get("tomadores") or [])]
    for t in cfg["tomadores"]:
        t["descricao"] = {**{"modo": "herdar", "texto": ""}, **(t.get("descricao") or {})}
        t["informacoes_complementares"] = {**{"modo": "herdar", "texto": ""}, **(t.get("informacoes_complementares") or {})}
        t["endereco"] = {**endereco_padrao(), **(t.get("endereco") or {})}
        if t.get("modo_identificacao") not in ("herdar", *MODOS_IDENTIFICACAO):
            t["modo_identificacao"] = "herdar"
        if t.get("perfil_id") not in ids_perfis:
            t["perfil_id"] = None
    cfg["endereco"] = {**endereco_rua_padrao(), **(cfg.get("endereco") or {})}
    cfg["simples"] = {**{"aliquota_mes": 0.0}, **(cfg.get("simples") or {})}
    if cfg.get("identificacao_tomador_padrao") not in MODOS_IDENTIFICACAO:
        cfg["identificacao_tomador_padrao"] = "documento"
    cfg["versao"] = VERSAO_ATUAL
    return cfg


# ------------------------------------------------------------------------------------------- validação
def perfil_completo(perfil: dict) -> bool:
    return bool(perfil.get("ctn") and perfil.get("nbs"))


def configuracao_completa(cfg: dict) -> bool:
    """Já tem o mínimo para tentar uma emissão: regime, município, endereço do prestador
    e pelo menos um perfil ativo e completo. A Inscrição Municipal (`prest/IM`) é opcional no
    XSD oficial (`minOccurs="0"`, RN 201: só é exigida de quem tem cadastro complementar no CNC
    do município) — não entra na validação. O grupo `prest/end` também é opcional no leiaute
    (`minOccurs="0"`, confirmado pela thread do motor de emissão) — exigir o endereço aqui é
    uma decisão própria do ADGE (a nota fica mais completa), não uma obrigação do leiaute."""
    if not cfg or cfg.get("regime") not in REGIMES:
        return False
    if not cfg.get("municipio"):
        return False
    if not cfg.get("endereco", {}).get("logradouro"):
        return False
    ativos = [p for p in cfg.get("perfis", []) if p.get("ativo")]
    return any(perfil_completo(p) for p in ativos)


def perfil_por_id(cfg: dict, perfil_id: str) -> dict | None:
    return next((p for p in cfg.get("perfis", []) if p["id"] == perfil_id), None)


def perfil_efetivo(cfg: dict, tomador: dict | None) -> dict | None:
    """O perfil que vale para um tomador: o dele, se tiver; senão o perfil padrão da empresa."""
    if tomador and tomador.get("perfil_id"):
        p = perfil_por_id(cfg, tomador["perfil_id"])
        if p:
            return p
    return perfil_por_id(cfg, cfg.get("perfil_padrao_id"))


# ------------------------------------------------------------------------------------------- texto
def aplicar_marcadores(texto: str, mes: int, ano: int) -> str:
    """Troca {MES} (nome do mês, ex. 'Outubro') e {ANO} pela competência informada."""
    if not texto:
        return texto
    nome_mes = MESES_PT[mes - 1] if 1 <= mes <= 12 else ""
    return texto.replace("{MES}", nome_mes).replace("{ANO}", str(ano))


def descricao_efetiva(perfil: dict, tomador: dict | None, mes: int, ano: int) -> str:
    """Resolve a descrição final: tomador (se não for 'herdar') tem prioridade sobre a do perfil."""
    bloco = (tomador or {}).get("descricao", {"modo": "herdar"})
    if bloco.get("modo") == "herdar" or not tomador:
        bloco = perfil.get("descricao", {})
    texto = bloco.get("texto", "")
    return aplicar_marcadores(texto, mes, ano) if bloco.get("modo") in ("mes_ano",) else texto


def informacoes_complementares_efetivas(perfil: dict, tomador: dict | None) -> str:
    bloco = (tomador or {}).get("informacoes_complementares", {"modo": "herdar"})
    if bloco.get("modo") == "herdar" or not tomador:
        return perfil.get("informacoes_complementares", "")
    return bloco.get("texto", "")


# ------------------------------------------------------------------------------------------- identificação/endereço
def modo_identificacao_efetivo(cfg: dict, tomador: dict) -> str:
    """"documento" ou "endereco": o modo do tomador, ou o padrão da empresa quando ele estiver em "herdar"."""
    modo = tomador.get("modo_identificacao", "herdar")
    return modo if modo in MODOS_IDENTIFICACAO else cfg.get("identificacao_tomador_padrao", "documento")


def endereco_completo(tomador: dict) -> str:
    """Endereço do tomador como uma linha só, pra exibir na tela e pra casar com o texto do lançamento."""
    e = tomador.get("endereco") or {}
    partes = [e.get("logradouro", ""), e.get("numero", ""), e.get("complemento", ""), e.get("bairro", ""),
              e.get("municipio", ""), e.get("uf", ""), e.get("cep", "")]
    partes = [p for p in partes if p]
    livre = tomador.get("endereco_livre", "")
    return ", ".join(partes) if partes else livre


# ------------------------------------------------------------------------------------------- casamento de tomador
def _normalizar(texto: str) -> str:
    return " ".join((texto or "").upper().split())


def _normalizar_documento(doc: str) -> str:
    return "".join(c for c in (doc or "") if c.isdigit())


def encontrar_tomador(cfg: dict, documento: str = "", nome: str = "", endereco: str = "") -> dict | None:
    """Casa um lançamento com um tomador recorrente já cadastrado. Prioridade: documento exato,
    depois nome normalizado, depois endereço normalizado (campo estruturado ou texto livre, o que
    o tomador tiver preenchido). Campo em branco no cadastro não entra no casamento por esse critério.
    Só considera tomadores ativos."""
    ativos = [t for t in cfg.get("tomadores", []) if t.get("ativo", True)]
    doc = _normalizar_documento(documento)
    if doc:
        for t in ativos:
            if _normalizar_documento(t.get("documento")) == doc:
                return t
    nome_n = _normalizar(nome)
    if nome_n:
        for t in ativos:
            if _normalizar(t.get("nome")) == nome_n:
                return t
    end_n = _normalizar(endereco)
    if end_n:
        for t in ativos:
            if _normalizar(endereco_completo(t)) == end_n:
                return t
    return None
