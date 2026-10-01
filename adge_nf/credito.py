"""Estimativa dos créditos que as notas TOMADAS podem gerar (PIS/COFINS no Lucro Real e IBS/CBS a partir de 2027).

Importante: a NFS-e não traz CFOP (ele existe na NF-e de mercadorias). Aqui o crédito é estimado pelo item da Lei
Complementar 116 do serviço (cTribNac) e pelo regime do fornecedor (campo opSimpNac da própria nota). É uma
ORIENTAÇÃO: o direito real ao crédito depende do uso do serviço na atividade da empresa, e quem decide é o contador.
Quando o programa passar a ler NF-e, o CFOP entra aqui como mais um critério. Tudo que pode mudar fica nas tabelas abaixo."""
from . import classificacao

# Itens da LC 116 e a chance de gerarem crédito para uma empresa de serviços.
PROVAVEL = {1, 2, 10, 11, 14, 16, 17, 23, 26, 31, 32, 33, 35, 36}        # insumos típicos da atividade
IMPROVAVEL = {6, 12, 19, 25, 34}                                          # em regra uso/consumo pessoal ou lazer
PESO = {"provavel": 1.0, "depende": 0.5, "improvavel": 0.0}
ROTULO = {"provavel": "Crédito provável", "depende": "Depende do uso na atividade", "improvavel": "Em regra sem crédito"}

# Fornecedor do Simples Nacional: no IBS/CBS o crédito do adquirente fica limitado ao que o fornecedor recolheu no DAS.
# Estimativa grosseira da fração do crédito "cheio" (opSimpNac: 2 = MEI, 3 = ME/EPP). Para PIS/COFINS não há diferença.
FRACAO_FORNECEDOR_SIMPLES = {"3": 0.15, "2": 0.05}


def categoria(doc: dict) -> str:
    item = classificacao.item_lc116(doc.get("servico_cod", ""))
    if item in PROVAVEL:
        return "provavel"
    if item in IMPROVAVEL:
        return "improvavel"
    return "depende"


def estimar(arquivos: list) -> dict:
    """Soma os créditos estimados das notas tomadas.
    Devolve {tomados, pis_cofins, ibs_cbs, linhas: [(categoria, valor, qtd)], de_simples: valor das notas de fornecedores do Simples}."""
    tomados = pc = ibs = simples = 0.0
    por_cat = {k: [0.0, 0] for k in PESO}
    for a in arquivos:
        if a.get("cat") != "servico_tomado":
            continue
        d = a["doc"]
        v = float(d.get("valor") or 0)
        cat = categoria(d)
        tomados += v
        por_cat[cat][0] += v
        por_cat[cat][1] += 1
        base = v * PESO[cat]
        pc += base
        fr = FRACAO_FORNECEDOR_SIMPLES.get(str(d.get("emitente_simples") or ""), 1.0)
        if fr != 1.0:
            simples += v
        ibs += base * fr
    return {"tomados": round(tomados, 2), "pis_cofins": round(pc, 2), "ibs_cbs": round(ibs, 2),
            "de_simples": round(simples, 2),
            "linhas": [(ROTULO[k], round(v[0], 2), v[1]) for k, v in por_cat.items() if v[1]]}


def participacao_pj(arquivos: list):
    """Fração do faturamento (serviços prestados) emitida para clientes com CNPJ, que podem aproveitar crédito de IBS/CBS.
    None se não houver nota prestada."""
    total = pj = 0.0
    for a in arquivos:
        if a.get("cat") != "servico_prestado":
            continue
        v = float(a["doc"].get("valor") or 0)
        total += v
        if len("".join(c for c in str(a["doc"].get("tomador_doc") or "") if c.isdigit())) == 14:
            pj += v
    return (pj / total) if total else None
