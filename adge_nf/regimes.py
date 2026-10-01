"""Simulação de carga tributária por regime (serviços). Resultado ESTIMADO, para orientar a conversa com o contador:
não substitui apuração, planejamento tributário nem parecer. Tudo que muda com a legislação fica em ALIQUOTAS / SIMPLES_ANEXOS.

A comparação respeita o enquadramento da empresa:
- Simples Nacional (receita dentro do limite): DAS unificado x opção pelo regime regular de IBS/CBS (LC 214/2025, art. 41 §3º),
  em que PIS/Cofins (2027) e depois ISS (2033) saem do DAS e IBS/CBS são recolhidos à parte, com crédito sobre as compras.
- Lucro Presumido e Lucro Real: comparados entre si hoje, em 2027 (CBS/IBS) e em 2033 (IBS/CBS pleno).
Simples não é oferecido a quem já está no Presumido/Real, e Presumido/Real não são oferecidos a quem está no Simples,
a não ser que a receita dos 12 meses tenha passado do limite do Simples."""
from __future__ import annotations

# ---------------------------------------------------------------------------------------------- tabelas
ALIQUOTAS = {
    "referencia": "Valores em vigor em out/2026. CBS 2027 é estimativa (a alíquota oficial deve ser fixada pelo Senado até dez/2026).",
    "pis_cumulativo": 0.0065, "cofins_cumulativo": 0.03,                      # Lucro Presumido
    "pis_nao_cumulativo": 0.0165, "cofins_nao_cumulativo": 0.076,             # Lucro Real
    "irpj": 0.15, "irpj_adicional": 0.10, "irpj_adicional_limite_mensal": 20000.0,   # R$ 60 mil/trimestre
    "csll": 0.09,
    "cpp_patronal": 0.20,                                                      # INSS patronal sobre a folha (sem RAT/terceiros)
    "limite_simples": 4_800_000.0, "sublimite_simples": 3_600_000.0, "limite_presumido": 78_000_000.0,
    "fator_r": 0.28,
    # Reforma tributária (LC 214/2025)
    "cbs_estimada": 0.0921,          # estimativa mais recente (Receita -> TCU, set/2026); faixa citada: 8,8% a 9,3%
    "ibs_transicao_2027": 0.001,     # IBS oficial na transição (2026 a 2028)
    "ibs_estimado_pleno": 0.1870,    # estimativa do Comitê Gestor do IBS (Res. 14/2026) para 2033
    "reducao_profissao_regulamentada": 0.30,
    "cbs_reducao_transicao": 0.001,  # em 2027-2028 a CBS de referência cai 0,1 p.p. (LC 214/2025)
}

# Simples Nacional (LC 123/2006, anexos III, IV e V): (limite superior da RBT12, alíquota nominal, parcela a deduzir)
SIMPLES_ANEXOS = {
    "III": [(180_000, 0.060, 0), (360_000, 0.112, 9_360), (720_000, 0.135, 17_640),
            (1_800_000, 0.160, 35_640), (3_600_000, 0.210, 125_640), (4_800_000, 0.330, 648_000)],
    "IV": [(180_000, 0.045, 0), (360_000, 0.090, 8_100), (720_000, 0.102, 12_420),
           (1_800_000, 0.140, 39_780), (3_600_000, 0.220, 183_780), (4_800_000, 0.330, 828_000)],
    "V": [(180_000, 0.155, 0), (360_000, 0.180, 4_500), (720_000, 0.195, 9_900),
          (1_800_000, 0.205, 17_100), (3_600_000, 0.230, 62_100), (4_800_000, 0.305, 540_000)],
}
PRESUNCAO = {"32": (0.32, 0.32), "16": (0.16, 0.12), "8": (0.08, 0.12)}      # % da receita: (IRPJ, CSLL)
NOMES = {"simples": "Simples Nacional", "presumido": "Lucro Presumido", "real": "Lucro Real"}


def fiscal_padrao() -> dict:
    return {"regime": "simples", "rbt12": 0.0, "folha12": 0.0, "anexo": "III", "fator_r": False, "iss_aliquota": 0.05,
            "presuncao": "32", "outras_despesas": 0.0, "profissao_regulamentada": False}


def fiscal_completo(f: dict) -> bool:
    """Já tem o mínimo para uma simulação confiável (regime e receita dos 12 meses)."""
    return bool(f) and f.get("regime") in NOMES and float(f.get("rbt12") or 0) > 0



# Repartição do DAS por anexo e faixa (LC 123/2006, Resolução CGSN 140): (PIS+COFINS, ISS) como fração da alíquota efetiva.
# Na 6ª faixa o ISS é recolhido fora do DAS.
REPARTICAO = {
    "III": [(0.1560, 0.3350), (0.1710, 0.3200), (0.1660, 0.3250), (0.1660, 0.3250), (0.1560, 0.3350), (0.1950, 0.0)],
    "IV": [(0.2150, 0.4450), (0.2500, 0.4000), (0.2400, 0.4000), (0.2300, 0.4000), (0.2245, 0.3950), (0.2500, 0.0)],
    "V": [(0.1715, 0.1400), (0.1715, 0.1700), (0.1815, 0.1900), (0.1915, 0.2100), (0.1715, 0.2350), (0.2000, 0.0)],
}


# ---------------------------------------------------------------------------------------------- Simples
def _indice_faixa(anexo: str, rbt12: float):
    for i, (lim, _, _) in enumerate(SIMPLES_ANEXOS[anexo]):
        if rbt12 <= lim:
            return i
    return None


def faixa_simples(anexo: str, rbt12: float):
    i = _indice_faixa(anexo, rbt12)
    return None if i is None else SIMPLES_ANEXOS[anexo][i][1:]


def repartir(anexo: str, rbt12: float):
    """(fração do DAS que é PIS/COFINS, fração que é ISS) na faixa da empresa."""
    i = _indice_faixa(anexo, rbt12)
    return REPARTICAO[anexo][i] if i is not None else (0.0, 0.0)


def aliquota_efetiva_simples(anexo: str, rbt12: float):
    faixa = faixa_simples(anexo, rbt12)
    if faixa is None:
        return None
    nominal, deduzir = faixa
    return (rbt12 * nominal - deduzir) / rbt12 if rbt12 > 0 else nominal


def anexo_efetivo(f: dict, rbt12: float):
    if f.get("fator_r"):
        razao = (float(f.get("folha12") or 0) / rbt12) if rbt12 > 0 else 0.0
        return ("III" if razao >= ALIQUOTAS["fator_r"] else "V"), razao
    return f.get("anexo") or "III", None


def _fmt(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _iss(f) -> float:
    return float(f.get("iss_aliquota") or 0)


def _fator_prof(f) -> float:
    return 1 - (ALIQUOTAS["reducao_profissao_regulamentada"] if f.get("profissao_regulamentada") else 0.0)


def _ibs_cbs(F, cred, f, pleno: bool):
    """Regime regular de IBS/CBS (não cumulativo): paga sobre faturamento − compras com crédito. Estimativa."""
    cbs = ALIQUOTAS["cbs_estimada"] - (0.0 if pleno else ALIQUOTAS["cbs_reducao_transicao"])
    ibs = ALIQUOTAS["ibs_estimado_pleno"] if pleno else ALIQUOTAS["ibs_transicao_2027"]
    base, fator = max(0.0, F - cred), _fator_prof(f)
    return [(f"CBS ({cbs * 100:.2f}%, estimativa)", base * cbs * fator),
            (f"IBS ({ibs * 100:.2f}%{'' if pleno else ', oficial na transição'})", base * ibs * fator)]


def _simples_das(F, f, rbt12):
    """Devolve (itens, obs, partes) do DAS de hoje, ou None se a receita passou do limite do Simples."""
    anexo, razao = anexo_efetivo(f, rbt12)
    ef = aliquota_efetiva_simples(anexo, rbt12)
    if ef is None:
        return None
    das = F * ef
    obs = []
    if razao is not None:
        obs.append(f"Fator R de {razao * 100:.1f}%: tributado pelo Anexo {anexo}.".replace(".", ","))
    if rbt12 > ALIQUOTAS["sublimite_simples"]:
        obs.append("Acima do sublimite de R$ 3,6 milhões o ISS (e, na reforma, o IBS) é recolhido fora do DAS e não está somado aqui.")
    extra = []
    if anexo == "IV":
        extra.append(("INSS patronal sobre a folha (fora do DAS)", float(f.get("folha12") or 0) / 12 * ALIQUOTAS["cpp_patronal"]))
    return {"anexo": anexo, "ef": ef, "das": das, "obs": obs, "extra": extra, "rep": repartir(anexo, rbt12)}


def _cenario_simples(F, f, rbt12, base, modo, cred_ibs):
    if base is None:
        return {"elegivel": False, "motivo": f"Receita dos 12 meses acima de R$ {_fmt(ALIQUOTAS['limite_simples']).split(',')[0]} (limite do Simples)."}
    anexo, ef, das = base["anexo"], base["ef"], base["das"]
    pc, iss = base["rep"]
    if modo == "das":
        itens = [(f"DAS (Anexo {anexo}, alíquota efetiva {ef * 100:.2f}%) — IBS/CBS dentro do DAS", das)]
        obs = ["Opção padrão: o DAS continua único. Em 2027 a CBS substitui a parcela de PIS/Cofins dentro do DAS, sem custo a mais.",
               "Clientes no regime regular só aproveitam como crédito o IBS/CBS efetivamente recolhido no DAS."]
    else:
        pleno = modo == "regular_2033"
        retirado = pc + (iss if pleno else 0.0)
        itens = [(f"DAS sem {'PIS/Cofins e ISS' if pleno else 'PIS/Cofins'} (Anexo {anexo})", das * (1 - retirado))]
        itens += _ibs_cbs(F, cred_ibs, f, pleno)
        obs = ["Opção híbrida (LC 214/2025, art. 41 §3º): IRPJ, CSLL e CPP continuam no DAS; IBS/CBS saem e são apurados com crédito sobre as compras.",
               "Cliente no regime regular passa a aproveitar crédito integral, o que pode compensar o custo maior na venda B2B.",
               "A escolha vale por semestre e é irretratável no período; o Comitê Gestor e o CGSN podem detalhar prazos."]
        if not pleno:
            obs.append("Até 2028 o ISS segue dentro do DAS.")
        else:
            obs.append("Em 2033 o ISS já foi extinto: a parcela dele sai do DAS (simulação ilustrativa).")
        if f.get("profissao_regulamentada"):
            obs.append("Redução de 30% para profissões regulamentadas aplicada ao IBS/CBS.")
    itens += base["extra"]
    return {"elegivel": True, "itens": itens, "obs": base["obs"] + obs}


# ---------------------------------------------------------------------------------------------- Presumido / Real
def _irpj_csll_presumido(F, f):
    pi, pc = PRESUNCAO.get(str(f.get("presuncao") or "32"), PRESUNCAO["32"])
    base_ir, base_cs = F * pi, F * pc
    irpj = base_ir * ALIQUOTAS["irpj"] + max(0.0, base_ir - ALIQUOTAS["irpj_adicional_limite_mensal"]) * ALIQUOTAS["irpj_adicional"]
    return irpj, base_cs * ALIQUOTAS["csll"], pi


def _irpj_csll_real(lucro):
    base = max(0.0, lucro)
    irpj = base * ALIQUOTAS["irpj"] + max(0.0, base - ALIQUOTAS["irpj_adicional_limite_mensal"]) * ALIQUOTAS["irpj_adicional"]
    return irpj, base * ALIQUOTAS["csll"]


def _fmt_rs(v):
    return "R$ " + _fmt(v)


def _cenario_lucro(F, T, f, rbt12, base, horizonte, cred_pc, cred_ibs):
    """base: 'presumido' | 'real'; horizonte: 'hoje' | '2027' | '2033'."""
    if base == "presumido" and rbt12 > ALIQUOTAS["limite_presumido"]:
        return {"elegivel": False, "motivo": "Receita acima de R$ 78 milhões (limite do Lucro Presumido)."}
    folha_mes = float(f.get("folha12") or 0) / 12
    cpp = folha_mes * ALIQUOTAS["cpp_patronal"]
    outras = float(f.get("outras_despesas") or 0)
    iss = F * _iss(f)
    iss_nome = f"ISS ({_iss(f) * 100:.2f}%)"
    obs = []
    if horizonte == "hoje":
        if base == "presumido":
            irpj, csll, pi = _irpj_csll_presumido(F, f)
            itens = [("PIS (0,65%)", F * ALIQUOTAS["pis_cumulativo"]), ("COFINS (3%)", F * ALIQUOTAS["cofins_cumulativo"]),
                     (iss_nome, iss), (f"IRPJ (presunção de {pi * 100:.0f}%)", irpj), ("CSLL", csll), ("INSS patronal sobre a folha", cpp)]
            obs = ["PIS/Cofins cumulativos: não há crédito sobre as compras.", "IRPJ/CSLL são trimestrais; aqui aparecem divididos por mês."]
        else:
            pis = max(0.0, F - cred_pc) * ALIQUOTAS["pis_nao_cumulativo"]
            cof = max(0.0, F - cred_pc) * ALIQUOTAS["cofins_nao_cumulativo"]
            lucro = F - pis - cof - iss - T - folha_mes - cpp - outras
            irpj, csll = _irpj_csll_real(lucro)
            itens = [("PIS (1,65%, com créditos)", pis), ("COFINS (7,6%, com créditos)", cof), (iss_nome, iss),
                     (f"IRPJ (lucro estimado de {_fmt_rs(lucro)})", irpj), ("CSLL", csll), ("INSS patronal sobre a folha", cpp)]
            obs = [f"Créditos de PIS/Cofins estimados em {_fmt_rs(cred_pc)} sobre {_fmt_rs(T)} de notas tomadas (pelo item da LC 116).",
                   "Lucro = faturamento − notas tomadas − folha − encargos − outras despesas informadas."]
    else:
        pleno = horizonte == "2033"
        itens = _ibs_cbs(F, cred_ibs, f, pleno)
        iss_v = 0.0 if pleno else iss
        if not pleno:
            itens.append((iss_nome + ", em vigor até 2028", iss_v))
        if base == "presumido":
            irpj, csll, pi = _irpj_csll_presumido(F, f)
            itens += [(f"IRPJ (presunção de {pi * 100:.0f}%)", irpj), ("CSLL", csll)]
        else:
            lucro = F - iss_v - T - folha_mes - cpp - outras
            irpj, csll = _irpj_csll_real(lucro)
            itens += [(f"IRPJ (lucro estimado de {_fmt_rs(lucro)})", irpj), ("CSLL", csll)]
        itens.append(("INSS patronal sobre a folha", cpp))
        obs = ["Simulação ilustrativa: PIS/Cofins deixam de existir em 2027 e o ISS é extinto gradualmente (2029 a 2033).",
               f"IBS/CBS no regime regular, obrigatório para Presumido e Real; créditos estimados em {_fmt_rs(cred_ibs)} "
               f"sobre {_fmt_rs(T)} de notas tomadas, já que o Presumido também passa a creditar."]
        if f.get("profissao_regulamentada"):
            obs.append("Redução de 30% para profissões regulamentadas aplicada ao IBS/CBS.")
    return {"elegivel": True, "itens": itens, "obs": obs}


# ---------------------------------------------------------------------------------------------- comparação
SECOES_SIMPLES = [
    ("Hoje e a partir de 2027 (transição)", "Opção do Simples: manter o DAS ou recolher IBS/CBS pelo regime regular.",
     ["simples_das", "simples_regular_2027"]),
    ("2033 (IBS/CBS pleno), ilustrativo", "Com o ISS já extinto e o IBS na alíquota cheia.", ["simples_das", "simples_regular_2033"]),
]
SECOES_LUCRO = [
    ("Hoje (2026)", "PIS/Cofins e ISS em vigor.", ["presumido_hoje", "real_hoje"]),
    ("2027 (CBS e IBS em transição)", "IBS/CBS regular é obrigatório; PIS/Cofins deixam de existir.", ["presumido_2027", "real_2027"]),
    ("2033 (IBS/CBS pleno), ilustrativo", "Com o ISS extinto e o IBS na alíquota cheia.", ["presumido_2033", "real_2033"]),
]
ATUAL_POR_SECAO = {"simples": "simples_das", "presumido": "presumido_{h}", "real": "real_{h}"}


def comparar(faturamento: float, tomados: float, fiscal: dict, credito_pc=None, credito_ibs=None, clientes_pj=None) -> dict:
    """Compara só o que faz sentido para o enquadramento da empresa. Valores do MÊS pesquisado.
    credito_pc / credito_ibs: créditos estimados (veja credito.estimar); sem eles, todas as notas tomadas geram crédito.
    Devolve {'grupo', 'cenarios', 'secoes', 'atual', 'melhor', 'avisos', 'insights', 'total_atual'}."""
    f = {**fiscal_padrao(), **(fiscal or {})}
    F, T = faturamento, tomados
    cred_pc = T if credito_pc is None else credito_pc
    cred_ibs = T if credito_ibs is None else credito_ibs
    avisos, insights = [], []
    rbt12 = float(f.get("rbt12") or 0)
    if rbt12 <= 0:
        rbt12 = F * 12
        avisos.append("Receita dos 12 meses não informada: usei o faturamento do mês × 12 (resultado menos preciso).")
    if f.get("fator_r") and not float(f.get("folha12") or 0):
        avisos.append("Folha dos 12 meses não informada: o Fator R ficou em 0% (Anexo V).")
    if not float(f.get("folha12") or 0):
        avisos.append("Sem folha informada, o INSS patronal e o Fator R não foram considerados.")

    regime = f["regime"]
    base_simples = _simples_das(F, f, rbt12)
    estourou = regime == "simples" and base_simples is None
    grupo = "simples" if (regime == "simples" and not estourou) else "lucro"
    if estourou:
        avisos.append(f"A receita dos 12 meses passou de R$ {_fmt(ALIQUOTAS['limite_simples']).split(',')[0]}: a empresa não pode "
                      "permanecer no Simples Nacional. A comparação abaixo é entre Lucro Presumido e Lucro Real.")
    if regime == "simples" and base_simples and rbt12 > ALIQUOTAS["sublimite_simples"]:
        avisos.append("Receita acima do sublimite de R$ 3,6 milhões: o IBS/ISS passam a ser recolhidos fora do DAS.")

    cen = {}
    if grupo == "simples":
        cen["simples_das"] = ("Simples Nacional · DAS unificado", _cenario_simples(F, f, rbt12, base_simples, "das", cred_ibs))
        cen["simples_regular_2027"] = ("Simples com IBS/CBS no regime regular · 2027",
                                       _cenario_simples(F, f, rbt12, base_simples, "regular_2027", cred_ibs))
        cen["simples_regular_2033"] = ("Simples com IBS/CBS no regime regular · 2033",
                                       _cenario_simples(F, f, rbt12, base_simples, "regular_2033", cred_ibs))
        modelo = SECOES_SIMPLES
        sufixo_atual = lambda h: "simples_das"  # noqa: E731
    else:
        for b in ("presumido", "real"):
            for h, rot in (("hoje", "hoje"), ("2027", "2027 (IBS/CBS)"), ("2033", "2033 (IBS/CBS pleno)")):
                cen[f"{b}_{h}"] = (f"{NOMES[b]} · {rot}", _cenario_lucro(F, T, f, rbt12, b, h, cred_pc, cred_ibs))
        modelo = SECOES_LUCRO
        sufixo_atual = lambda h: f"{regime}_{h}" if regime in ("presumido", "real") else None  # noqa: E731

    cenarios = []
    for chave, (nome, r) in cen.items():
        c = {"chave": chave, "nome": nome, **r}
        if r["elegivel"]:
            c["total"] = round(sum(v for _, v in r["itens"]), 2)
            c["efetiva"] = (c["total"] / F) if F else 0.0
        cenarios.append(c)
    por_chave = {c["chave"]: c for c in cenarios}

    secoes = []
    for titulo, nota, chaves in modelo:
        horizonte = chaves[-1].rsplit("_", 1)[-1]
        eleg = [k for k in chaves if por_chave[k]["elegivel"]]
        melhor = min(eleg, key=lambda k: por_chave[k]["total"]) if len(eleg) >= 2 else None
        atual = sufixo_atual(horizonte if grupo == "lucro" else "")
        secoes.append({"titulo": titulo, "nota": nota, "chaves": chaves, "melhor": melhor,
                       "atual": atual if atual in chaves else None})

    if grupo == "simples":
        if clientes_pj is not None:
            insights.append(f"{clientes_pj * 100:.0f}% do faturamento do período foi para clientes com CNPJ (que podem aproveitar crédito). "
                            + ("Vendas B2B em maior parte tendem a favorecer o regime regular." if clientes_pj >= 0.6
                               else "Com poucas vendas B2B, o crédito para o cliente pesa menos na decisão."))
        if T:
            insights.append(f"Créditos estimados sobre as notas tomadas: {_fmt_rs(cred_ibs)} de {_fmt_rs(T)} (IBS/CBS).")
    else:
        if T:
            insights.append(f"Créditos estimados: {_fmt_rs(cred_pc)} para PIS/Cofins (Lucro Real) e {_fmt_rs(cred_ibs)} para IBS/CBS, "
                            f"sobre {_fmt_rs(T)} de notas tomadas.")
    s1 = secoes[0]
    principal = s1["atual"]
    total_atual = por_chave[principal].get("total") if principal and por_chave[principal]["elegivel"] else None
    return {"grupo": grupo, "cenarios": cenarios, "secoes": secoes, "atual": principal, "melhor": s1["melhor"],
            "avisos": avisos, "insights": insights, "total_atual": total_atual, "fora_do_simples": estourou}
