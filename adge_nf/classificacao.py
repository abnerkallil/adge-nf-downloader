"""Classificação oficial dos serviços: lista anexa à Lei Complementar 116/2003 (itens 1 a 40).
Na NFS-e Nacional o código de tributação nacional (cTribNac, 6 dígitos) começa pelo item da lista."""

ITENS_LC116 = {
    1: "Informática e congêneres", 2: "Pesquisa e desenvolvimento", 3: "Locação e cessão de direito de uso",
    4: "Saúde e assistência médica", 5: "Medicina veterinária e zootecnia", 6: "Cuidados pessoais e estética",
    7: "Engenharia, arquitetura e construção", 8: "Educação e ensino", 9: "Hospedagem e turismo",
    10: "Intermediação e agenciamento", 11: "Guarda, estacionamento e vigilância", 12: "Diversões e lazer",
    13: "Fonografia, fotografia e reprografia", 14: "Reparação e conservação de bens", 15: "Serviços financeiros",
    16: "Transporte municipal", 17: "Apoio técnico, administrativo, jurídico e contábil", 18: "Regulação de sinistros",
    19: "Bilhetes e loterias", 20: "Portos e aeroportos", 21: "Serviços de registros públicos e cartórios",
    22: "Exploração de rodovias", 23: "Programação e comunicação visual", 24: "Chaveiros, placas e congêneres",
    25: "Serviços funerários", 26: "Correspondência e entregas", 27: "Assistência social", 28: "Avaliação de bens",
    29: "Biblioteconomia", 30: "Biologia, biotecnologia e química", 31: "Serviços técnicos em edificações e eletrônica",
    32: "Desenhos técnicos", 33: "Despachantes e desembaraço aduaneiro", 34: "Investigações particulares",
    35: "Jornalismo e assessoria de imprensa", 36: "Meteorologia", 37: "Artistas, atletas e modelos",
    38: "Museologia", 39: "Ourivesaria e lapidação", 40: "Obras de arte sob encomenda",
}
SEM_CLASSIFICACAO = "Sem classificação"


def item_lc116(codigo: str):
    """'070201' -> 7. Devolve None se o código não começa por um item válido."""
    d = "".join(c for c in str(codigo or "") if c.isdigit())
    if len(d) >= 2 and 1 <= int(d[:2]) <= 40:
        return int(d[:2])
    return None


def rotulo_servico(doc: dict) -> str:
    item = item_lc116(doc.get("servico_cod", ""))
    if item is None:
        return SEM_CLASSIFICACAO
    return f"{item:02d} · {ITENS_LC116[item]}"
