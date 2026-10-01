import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf import classificacao, grafico, regimes


class Simples(unittest.TestCase):
    def test_aliquota_efetiva_conhecida(self):
        self.assertAlmostEqual(regimes.aliquota_efetiva_simples("III", 360_000), 0.086, places=6)
        self.assertAlmostEqual(regimes.aliquota_efetiva_simples("III", 100_000), 0.06, places=6)
        self.assertAlmostEqual(regimes.aliquota_efetiva_simples("V", 360_000), 0.1675, places=6)
        self.assertIsNone(regimes.aliquota_efetiva_simples("III", 5_000_000))

    def test_fator_r(self):
        f = {"fator_r": True, "folha12": 100_000}
        self.assertEqual(regimes.anexo_efetivo(f, 300_000)[0], "III")   # 33%
        self.assertEqual(regimes.anexo_efetivo(f, 500_000)[0], "V")     # 20%

    def test_das_do_mes(self):
        r = regimes.comparar(30_000, 0, {"regime": "simples", "rbt12": 360_000, "anexo": "III"})
        s = next(c for c in r["cenarios"] if c["chave"] == "simples")
        self.assertAlmostEqual(s["total"], 30_000 * 0.086, places=2)
        self.assertEqual(r["atual"], "simples")

    def test_inelegivel_acima_do_limite(self):
        r = regimes.comparar(500_000, 0, {"regime": "presumido", "rbt12": 6_000_000})
        self.assertFalse(next(c for c in r["cenarios"] if c["chave"] == "simples")["elegivel"])


class PresumidoReal(unittest.TestCase):
    def test_presumido_servicos(self):
        r = regimes.comparar(100_000, 0, {"regime": "presumido", "rbt12": 1_200_000, "iss_aliquota": 0.05})
        p = {n.split(" (")[0]: v for n, v in next(c for c in r["cenarios"] if c["chave"] == "presumido")["itens"]}
        self.assertAlmostEqual(p["PIS"], 650.0)
        self.assertAlmostEqual(p["COFINS"], 3000.0)
        self.assertAlmostEqual(p["ISS"], 5000.0)
        self.assertAlmostEqual(p["IRPJ"], 32_000 * 0.15 + 12_000 * 0.10)   # base 32% + adicional acima de 20 mil
        self.assertAlmostEqual(p["CSLL"], 32_000 * 0.09)

    def test_real_credita_tomados(self):
        r = regimes.comparar(100_000, 40_000, {"regime": "real", "rbt12": 1_200_000, "iss_aliquota": 0.0})
        itens = {n.split(" (")[0]: v for n, v in next(c for c in r["cenarios"] if c["chave"] == "real")["itens"]}
        self.assertAlmostEqual(itens["PIS"], 60_000 * 0.0165)
        self.assertAlmostEqual(itens["COFINS"], 60_000 * 0.076)

    def test_real_sem_lucro_nao_paga_irpj(self):
        r = regimes.comparar(10_000, 20_000, {"regime": "real", "rbt12": 120_000, "iss_aliquota": 0.0})
        itens = dict((n.split(" (")[0], v) for n, v in next(c for c in r["cenarios"] if c["chave"] == "real")["itens"])
        self.assertEqual(itens["IRPJ"], 0.0)
        self.assertEqual(itens["CSLL"], 0.0)

    def test_reforma(self):
        r = regimes.comparar(100_000, 20_000, {"regime": "presumido", "rbt12": 1_200_000, "iss_aliquota": 0.05})
        pleno = next(c for c in r["cenarios"] if c["chave"] == "reforma2033")
        ibs_cbs = sum(v for n, v in pleno["itens"] if n.startswith(("CBS", "IBS")))
        self.assertAlmostEqual(ibs_cbs, 80_000 * (0.0921 + 0.1870), places=2)
        reg = regimes.comparar(100_000, 20_000, {"regime": "presumido", "rbt12": 1_200_000, "profissao_regulamentada": True})
        pleno2 = next(c for c in reg["cenarios"] if c["chave"] == "reforma2033")
        self.assertAlmostEqual(sum(v for n, v in pleno2["itens"] if n.startswith(("CBS", "IBS"))), ibs_cbs * 0.7, places=2)

    def test_avisos_sem_dados(self):
        r = regimes.comparar(10_000, 0, {"regime": "simples"})
        self.assertTrue(any("12 meses" in a for a in r["avisos"]))

    def test_melhor_regime(self):
        r = regimes.comparar(30_000, 0, {"regime": "presumido", "rbt12": 360_000, "iss_aliquota": 0.05})
        self.assertEqual(r["melhor"], "simples")


class Classificacao(unittest.TestCase):
    def test_item(self):
        self.assertEqual(classificacao.item_lc116("070201"), 7)
        self.assertEqual(classificacao.item_lc116("17.01"), 17)
        self.assertIsNone(classificacao.item_lc116(""))
        self.assertIsNone(classificacao.item_lc116("990101"))
        self.assertEqual(classificacao.rotulo_servico({"servico_cod": "010701"}), "01 · Informática e congêneres")
        self.assertEqual(classificacao.rotulo_servico({}), "Sem classificação")


class Grafico(unittest.TestCase):
    def arq(self, cat, valor, tomador="CLIENTE A", emitente="FORN B", cod=""):
        return {"cat": cat, "doc": {"valor": valor, "tomador_nome": tomador, "tomador_doc": "1", "emitente_nome": emitente,
                                    "emitente_doc": "2", "servico_cod": cod}}

    def test_parse_brl(self):
        self.assertEqual(grafico.parse_brl("R$ 1.234,56"), 1234.56)
        self.assertEqual(grafico.parse_brl("1234.56"), 1234.56)
        self.assertEqual(grafico.parse_brl("1.234"), 1234.0)
        self.assertEqual(grafico.parse_brl(""), 0.0)
        with self.assertRaises(ValueError):
            grafico.parse_brl("abc")

    def test_agrupar_por_parte_e_filtro(self):
        arqs = [self.arq("servico_prestado", 300), self.arq("servico_prestado", 100, tomador="CLIENTE B"),
                self.arq("servico_tomado", 50)]
        r = grafico.agrupar(arqs, "parte", "prestado")
        self.assertEqual([x[0] for x in r], ["CLIENTE A", "CLIENTE B"])
        self.assertAlmostEqual(r[0][2], 75.0)
        ambos = grafico.agrupar(arqs, "parte", "ambos")
        self.assertIn("FORN B · fornecedor", [x[0] for x in ambos])

    def test_agrupar_servico_e_tipo(self):
        arqs = [self.arq("servico_prestado", 200, cod="070201"), self.arq("servico_prestado", 100),
                self.arq("servico_tomado", 100, cod="170101")]
        r = dict((k, v) for k, v, _ in grafico.agrupar(arqs, "servico"))
        self.assertEqual(r["07 · Engenharia, arquitetura e construção"], 200)
        self.assertEqual(r["Sem classificação"], 100)
        t = dict((k, v) for k, v, _ in grafico.agrupar(arqs, "tipo"))
        self.assertEqual(t, {"Serviços prestados": 300, "Serviços tomados": 100})

    def test_outros_e_angulos(self):
        arqs = [self.arq("servico_prestado", 100 - i, tomador=f"C{i}") for i in range(12)]
        r = grafico.agrupar(arqs, "parte", "prestado", top=8)
        self.assertEqual(len(r), 9)
        self.assertTrue(r[-1][0].startswith("Outros ("))
        self.assertAlmostEqual(sum(x[2] for x in r), 100.0)
        ang = grafico.angulos(r)
        self.assertAlmostEqual(sum(e for _, e in ang), -360.0)


if __name__ == "__main__":
    unittest.main()
