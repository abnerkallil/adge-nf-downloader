"""Estimativa dos créditos que as notas TOMADAS podem gerar (PIS/COFINS no Lucro Real e IBS/CBS a partir de 2027).

Importante: a NFS-e não traz CFOP (ele existe na NF-e de mercadorias). Aqui o crédito é estimado pelo item da Lei
Complementar 116 do serviço (cTribNac) e pelo regime do fornecedor (campo opSimpNac da própria nota). É uma
ORIENTAÇÃO: o direito real ao crédito depende do uso do serviço na atividade da empresa, e quem decide é o contador.
Nas NF-e (mercadorias) o CFOP de cada item entra como critério (veja cfop.peso_credito). Notas só com resumo (sem ciência) não têm
CFOP nem itens: contam como compra, mas sem crédito estimado. Tudo que pode mudar fica nas tabelas abaixo."""
from . import cfop as cfop_mod
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


def _classe_cfop(cod: str) -> str:
    suf = cfop_mod.normalizar(cod)[1:]
    if suf == "551":
        return "NF-e: ativo imobilizado (crédito só no IBS/CBS)"
    if suf == "556":
        return "NF-e: uso e consumo (crédito parcial no IBS/CBS)"
    if cfop_mod.peso_credito(cod) == (1.0, 1.0):
        return "NF-e: revenda e insumos (crédito provável)"
    return "NF-e: outros CFOPs (a confirmar)"


def estimar(arquivos: list) -> dict:
    """Soma os créditos estimados das compras: NFS-e tomadas (item da LC 116), NF-e de compra (CFOP dos itens) e devoluções de compra.
    Devolve {tomados, pis_cofins, ibs_cbs, linhas: [(rótulo, valor, qtd)], de_simples: valor das notas de fornecedores do Simples}."""
    tomados = pc = ibs = simples = 0.0
    por_cat = {k: [0.0, 0] for k in PESO}
    outras = {}                                     # rótulo -> [valor, qtd] das NF-e
    for a in arquivos:
        cat, d = a.get("cat"), a["doc"]
        v = float(d.get("valor") or 0)
        if cat == "servico_tomado":
            c = categoria(d)
            tomados += v
            por_cat[c][0] += v
            por_cat[c][1] += 1
            base_pc = base_ibs = v * PESO[c]
        elif cat == "nfe_entrada":
            tomados += v
            itens = d.get("itens") or []
            soma = sum(float(i.get("valor") or 0) for i in itens)
            base_pc = base_ibs = 0.0
            vistas = set()                                  # a nota conta uma vez em cada classe em que tem itens
            for i in itens or [{"cfop": d.get("cfop", ""), "valor": v}]:
                parte = (v * float(i.get("valor") or 0) / soma) if soma else v
                w_pc, w_ibs = cfop_mod.peso_credito(i.get("cfop", ""))
                base_pc += parte * w_pc
                base_ibs += parte * w_ibs
                classe = _classe_cfop(i.get("cfop", ""))
                r = outras.setdefault(classe, [0.0, 0])
                r[0] += parte
                if classe not in vistas:
                    vistas.add(classe)
                    r[1] += 1
        elif cat == "nfe_resumo":
            tomados += v
            r = outras.setdefault("NF-e sem ciência (sem CFOP: sem crédito estimado)", [0.0, 0])
            r[0] += v
            r[1] += 1
            continue
        elif cat == "nfe_devolucao_compra":
            tomados -= v
            pc -= v
            ibs -= v
            r = outras.setdefault("NF-e devolução de compra (abate o crédito)", [0.0, 0])
            r[0] -= v
            r[1] += 1
            continue
        else:
            continue
        pc += base_pc
        fr = FRACAO_FORNECEDOR_SIMPLES.get(str(d.get("emitente_simples") or ""), 1.0)
        if fr != 1.0:
            simples += v
        ibs += base_ibs * fr
    linhas = [(ROTULO[k], round(x[0], 2), x[1]) for k, x in por_cat.items() if x[1]]
    linhas += [(k, round(x[0], 2), x[1]) for k, x in outras.items()]
    return {"tomados": round(max(0.0, tomados), 2), "pis_cofins": round(max(0.0, pc), 2), "ibs_cbs": round(max(0.0, ibs), 2),
            "de_simples": round(simples, 2), "linhas": linhas}


def participacao_pj(arquivos: list):
    """Fração do faturamento (serviços prestados e NF-e de venda) emitida para clientes com CNPJ, que podem aproveitar crédito de IBS/CBS.
    None se não houver nota prestada."""
    total = pj = 0.0
    for a in arquivos:
        if a.get("cat") not in ("servico_prestado", "nfe_saida"):
            continue
        v = float(a["doc"].get("valor") or 0)
        total += v
        if len("".join(c for c in str(a["doc"].get("tomador_doc") or "") if c.isdigit())) == 14:
            pj += v
    return (pj / total) if total else None
