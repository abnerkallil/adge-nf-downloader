"""v1.7.5: consulta de períodos em lote e RBT12 básico calculado com as notas já consultadas."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from adge_nf import core  # noqa: E402
from fixtures import evento_cancelamento, xml_nfse  # noqa: E402

CNPJ, CLI = "11111111000111", "44444444000144"


def doc(nsu, xml):
    return {"nsu": nsu, "chave": "", "tipo": "NFSE", "tipo_evento": "", "gerado_em": "", "xml": xml}


def nfse(n, valor, dh, **kw):
    return doc(n, xml_nfse(str(n).rjust(50, "0"), valor=valor, dh=dh, num=str(n), **kw))


class TestLote(unittest.TestCase):
    def test_alternar_periodo_marca_e_desmarca(self):
        s = {(2026, 9)}
        s = core.alternar_periodo(s, 2026, 8)
        self.assertEqual(s, {(2026, 8), (2026, 9)})
        s = core.alternar_periodo(s, 2026, 9)
        self.assertEqual(s, {(2026, 8)})

    def test_o_ultimo_mes_nao_sai(self):
        self.assertEqual(core.alternar_periodo({(2026, 9)}, 2026, 9), {(2026, 9)})

    def test_meses_de_anos_diferentes_convivem(self):
        s = core.alternar_periodo({(2026, 1)}, 2025, 12)
        self.assertEqual(sorted(s), [(2025, 12), (2026, 1)])

    def test_formatar_periodos(self):
        self.assertEqual(core.formatar_periodos([(2026, 9)]), "Set de 2026")
        self.assertEqual(core.formatar_periodos([(2026, 9), (2026, 7), (2026, 8)]), "Jul, Ago e Set de 2026")
        self.assertEqual(core.formatar_periodos([(2026, 1), (2025, 12)]), "Dez/2025 e Jan/2026")
        self.assertEqual(core.formatar_periodos([]), "")

    def test_cada_mes_do_lote_sai_da_mesma_lista_de_documentos(self):
        """Uma consulta só: os mesmos documentos servem para todos os meses marcados."""
        docs = [nfse(1, "100.00", "2026-08-10T10:00:00-03:00", emit_cnpj=CNPJ), nfse(2, "200.00", "2026-09-10T10:00:00-03:00", emit_cnpj=CNPJ)]
        emp = {"tipos": {"prestado": True, "tomado": True}}
        v = {}
        for a, m in ((2026, 8), (2026, 9)):
            arq, res, _ = core.planejar(emp, docs, CNPJ, a, m, None, {})
            v[(a, m)] = res["servico_prestado"]["valor"]
        self.assertEqual(v, {(2026, 8): 100.0, (2026, 9): 200.0})


class TestRBT12(unittest.TestCase):
    def test_soma_os_12_meses_anteriores_sem_o_mes_consultado(self):
        docs = [nfse(1, "1000.00", "2025-09-15T10:00:00-03:00", emit_cnpj=CNPJ),      # primeiro mês da janela
                nfse(2, "2000.00", "2026-08-31T10:00:00-03:00", emit_cnpj=CNPJ),      # último mês da janela
                nfse(3, "500.00", "2025-08-31T10:00:00-03:00", emit_cnpj=CNPJ),       # 13 meses atrás: fora
                nfse(4, "9999.00", "2026-09-10T10:00:00-03:00", emit_cnpj=CNPJ)]      # mês consultado: fora
        r = core.rbt12_nfse(docs, CNPJ, 2026, 9)
        self.assertEqual(r["valor"], 3000.0)
        self.assertEqual((r["de"], r["ate"]), ((2025, 9), (2026, 8)))
        self.assertEqual((r["qtd"], r["meses_com_notas"], len(r["por_mes"])), (2, 2, 12))

    def test_virada_de_ano(self):
        r = core.rbt12_nfse([nfse(1, "10.00", "2025-12-05T10:00:00-03:00", emit_cnpj=CNPJ)], CNPJ, 2026, 1)
        self.assertEqual((r["de"], r["ate"], r["valor"]), ((2025, 1), (2025, 12), 10.0))

    def test_so_servico_prestado_sem_cancelada_e_sem_duplicada(self):
        a = nfse(1, "100.00", "2026-03-10T10:00:00-03:00", emit_cnpj=CNPJ)
        canc = nfse(2, "700.00", "2026-04-10T10:00:00-03:00", emit_cnpj=CNPJ)
        tomada = nfse(3, "300.00", "2026-05-10T10:00:00-03:00", emit_cnpj=CLI, toma_cnpj=CNPJ)
        evento = doc(4, evento_cancelamento("2".rjust(50, "0")))
        r = core.rbt12_nfse([a, a, canc, tomada, evento], CNPJ, 2026, 9)
        self.assertEqual((r["valor"], r["qtd"]), (100.0, 1))

    def test_sem_notas_nao_sugere_nada(self):
        r = core.rbt12_nfse([], CNPJ, 2026, 9)
        self.assertEqual((r["valor"], r["meses_com_notas"]), (0.0, 0))


if __name__ == "__main__":
    unittest.main()
