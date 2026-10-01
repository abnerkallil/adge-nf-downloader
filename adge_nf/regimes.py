"""Simulação de carga tributária por regime (serviços). Resultado ESTIMADO, para orientar a conversa com o contador:
não substitui apuração, planejamento tributário nem parecer. Tudo que muda com a legislação fica em ALIQUOTAS / SIMPLES_ANEXOS."""
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


# ---------------------------------------------------------------------------------------------- Simples
def faixa_simples(anexo: str, rbt12: float):
    for lim, nominal, deduzir in SIMPLES_ANEXOS[anexo]:
        if rbt12 <= lim:
            return nominal, deduzir
    return None


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


def _simples(F, T, f, rbt12):
    anexo, razao = anexo_efetivo(f, rbt12)
    ef = aliquota_efetiva_simples(anexo, rbt12)
    if ef is None:
        return {"elegivel": False, "motivo": f"Receita dos 12 meses acima de R$ {ALIQUOTAS['limite_simples']:,.0f} (limite do Simples)."
                .replace(",", ".")}
    itens = [(f"DAS (Anexo {anexo}, alíquota efetiva {ef * 100:.2f}%)", F * ef)]
    folha_mes = float(f.get("folha12") or 0) / 12
    if anexo == "IV":
        itens.append(("INSS patronal sobre a folha (fora do DAS)", folha_mes * ALIQUOTAS["cpp_patronal"]))
    obs = []
    if razao is not None:
        obs.append(f"Fator R de {razao * 100:.1f}%: tributado pelo Anexo {anexo}.".replace(".", ","))
    if rbt12 > ALIQUOTAS["sublimite_simples"]:
        obs.append("Acima do sublimite de R$ 3,6 milhões o ISS é recolhido fora do DAS (não somado aqui).")
    return {"elegivel": True, "itens": itens, "obs": obs}


# ---------------------------------------------------------------------------------------------- Presumido / Real
def _irpj_csll_presumido(F, f):
    pi, pc = PRESUNCAO.get(str(f.get("presuncao") or "32"), PRESUNCAO["32"])
    base_ir, base_cs = F * pi, F * pc
    irpj = base_ir * ALIQUOTAS["irpj"] + max(0.0, base_ir - ALIQUOTAS["irpj_adicional_limite_mensal"]) * ALIQUOTAS["irpj_adicional"]
    return irpj, base_cs * ALIQUOTAS["csll"], pi


def _presumido(F, T, f, rbt12):
    if rbt12 > ALIQUOTAS["limite_presumido"]:
        return {"elegivel": False, "motivo": "Receita acima de R$ 78 milhões (limite do Lucro Presumido)."}
    irpj, csll, pi = _irpj_csll_presumido(F, f)
    folha_mes = float(f.get("folha12") or 0) / 12
    itens = [("PIS (0,65%)", F * ALIQUOTAS["pis_cumulativo"]), ("COFINS (3%)", F * ALIQUOTAS["cofins_cumulativo"]),
             (f"ISS ({float(f.get('iss_aliquota') or 0) * 100:.2f}%)", F * float(f.get("iss_aliquota") or 0)),
             (f"IRPJ (presunção de {pi * 100:.0f}%)", irpj), ("CSLL", csll),
             ("INSS patronal sobre a folha", folha_mes * ALIQUOTAS["cpp_patronal"])]
    return {"elegivel": True, "itens": itens, "obs": ["IRPJ/CSLL são trimestrais; aqui aparecem divididos por mês."]}


def _real(F, T, f, rbt12):
    folha_mes = float(f.get("folha12") or 0) / 12
    outras = float(f.get("outras_despesas") or 0)
    iss = F * float(f.get("iss_aliquota") or 0)
    pis = max(0.0, F - T) * ALIQUOTAS["pis_nao_cumulativo"]
    cofins = max(0.0, F - T) * ALIQUOTAS["cofins_nao_cumulativo"]
    cpp = folha_mes * ALIQUOTAS["cpp_patronal"]
    lucro = F - pis - cofins - iss - T - folha_mes - cpp - outras
    base = max(0.0, lucro)
    irpj = base * ALIQUOTAS["irpj"] + max(0.0, base - ALIQUOTAS["irpj_adicional_limite_mensal"]) * ALIQUOTAS["irpj_adicional"]
    itens = [("PIS (1,65%, com créditos)", pis), ("COFINS (7,6%, com créditos)", cofins),
             (f"ISS ({float(f.get('iss_aliquota') or 0) * 100:.2f}%)", iss),
             (f"IRPJ (lucro estimado de R$ {lucro:,.2f})".replace(",", "X").replace(".", ",").replace("X", "."), irpj),
             ("CSLL", base * ALIQUOTAS["csll"]), ("INSS patronal sobre a folha", cpp)]
    return {"elegivel": True, "itens": itens,
            "obs": ["Créditos de PIS/COFINS estimados sobre todas as notas tomadas (na prática nem todas dão crédito).",
                    "Lucro = faturamento − notas tomadas − folha − encargos − outras despesas informadas."]}


# ---------------------------------------------------------------------------------------------- reforma (IBS/CBS)
def _reforma(F, T, f, pleno: bool):
    """Regime regular de IBS/CBS (não cumulativo: paga sobre faturamento − compras com crédito). Ilustrativo."""
    cbs = ALIQUOTAS["cbs_estimada"]
    ibs = ALIQUOTAS["ibs_estimado_pleno"] if pleno else ALIQUOTAS["ibs_transicao_2027"]
    fator = 1 - (ALIQUOTAS["reducao_profissao_regulamentada"] if f.get("profissao_regulamentada") else 0.0)
    base = max(0.0, F - T)
    ibs_v, cbs_v = base * ibs * fator, base * cbs * fator
    # IRPJ/CSLL continuam: usa a base do Lucro Real se o regime atual for Real; senão, a do Presumido
    if f.get("regime") == "real":
        r = _real(F, T, f, 0)
        extra = [(n, v) for n, v in r["itens"] if n.startswith(("IRPJ", "CSLL", "INSS"))]
    else:
        irpj, csll, pi = _irpj_csll_presumido(F, f)
        extra = [(f"IRPJ (presunção de {pi * 100:.0f}%)", irpj), ("CSLL", csll),
                 ("INSS patronal sobre a folha", float(f.get("folha12") or 0) / 12 * ALIQUOTAS["cpp_patronal"])]
    itens = [(f"CBS ({cbs * 100:.2f}%, estimativa)", cbs_v), (f"IBS ({ibs * 100:.2f}%{'' if pleno else ', oficial na transição'})", ibs_v)]
    if not pleno:
        itens.append((f"ISS ({float(f.get('iss_aliquota') or 0) * 100:.2f}%, em vigor até 2028)", F * float(f.get("iss_aliquota") or 0)))
    itens += extra
    obs = ["Simulação ilustrativa: PIS/COFINS deixam de existir em 2027; ISS é extinto gradualmente (2029 a 2033).",
           "Créditos considerados sobre todas as notas tomadas."]
    if f.get("profissao_regulamentada"):
        obs.append("Redução de 30% para profissões regulamentadas aplicada.")
    return {"elegivel": True, "itens": itens, "obs": obs}


# ---------------------------------------------------------------------------------------------- comparação
def comparar(faturamento: float, tomados: float, fiscal: dict) -> dict:
    """Devolve {'cenarios': [...], 'atual': chave, 'melhor': chave, 'avisos': [...]}. Valores do MÊS pesquisado."""
    f = {**fiscal_padrao(), **(fiscal or {})}
    avisos = []
    rbt12 = float(f.get("rbt12") or 0)
    if rbt12 <= 0:
        rbt12 = faturamento * 12
        avisos.append("Receita dos 12 meses não informada: usei o faturamento do mês × 12 (resultado menos preciso).")
    if f.get("fator_r") and not float(f.get("folha12") or 0):
        avisos.append("Folha dos 12 meses não informada: o Fator R ficou em 0% (Anexo V).")
    if not float(f.get("folha12") or 0):
        avisos.append("Sem folha informada, o INSS patronal e o Fator R não foram considerados.")
    blocos = [("simples", NOMES["simples"], _simples(faturamento, tomados, f, rbt12)),
              ("presumido", NOMES["presumido"], _presumido(faturamento, tomados, f, rbt12)),
              ("real", NOMES["real"], _real(faturamento, tomados, f, rbt12)),
              ("reforma2027", "Regime regular IBS/CBS · 2027 (transição)", _reforma(faturamento, tomados, f, False)),
              ("reforma2033", "Regime regular IBS/CBS · 2033 (pleno)", _reforma(faturamento, tomados, f, True))]
    cenarios = []
    for chave, nome, r in blocos:
        c = {"chave": chave, "nome": nome, **r}
        if r["elegivel"]:
            c["total"] = round(sum(v for _, v in r["itens"]), 2)
            c["efetiva"] = (c["total"] / faturamento) if faturamento else 0.0
        cenarios.append(c)
    atuais = [c for c in cenarios if c["chave"] == f["regime"]]
    pool = [c for c in cenarios[:3] if c["elegivel"]]
    melhor = min(pool, key=lambda c: c["total"])["chave"] if pool else None
    return {"cenarios": cenarios, "atual": f["regime"], "melhor": melhor, "avisos": avisos,
            "total_atual": atuais[0].get("total") if atuais and atuais[0]["elegivel"] else None}
