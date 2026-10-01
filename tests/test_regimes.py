import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf import classificacao, credito, grafico, regimes


def cen(r, chave):
    return next(c for c in r["cenarios"] if c["chave"] == chave)


def itens(r, chave):
    return {n.split(" (")[0]: v for n, v in cen(r, chave)["itens"]}


class Simples(unittest.TestCase):
    def test_aliquota_efetiva_conhecida(self):
        self.assertAlmostEqual(regimes.aliquota_efetiva_simples("III", 360_000), 0.086, places=6)
        self.assertAlmostEqual(regimes.aliquota_efetiva_simples("III", 100_000), 0.06, places=6)
        self.assertAlmostEqual(regimes.aliquota_efetiva_simples("V", 360_000), 0.1675, places=6)
        self.assertIsNone(regimes.aliquota_efetiva_simples("III", 5_000_000))

    def test_repartição_soma_com_o_resto_do_das(self):
        for anexo, faixas in regimes.REPARTICAO.items():
            self.assertEqual(len(faixas), 6)
            for pc, iss in faixas:
                self.assertTrue(0 < pc < 0.3 and 0 <= iss < 0.5)
        self.assertEqual(regimes.repartir("III", 100_000), (0.156, 0.335))
        self.assertEqual(regimes.repartir("V", 4_000_000), (0.2, 0.0))

    def test_fator_r(self):
        f = {"fator_r": True, "folha12": 100_000}
        self.assertEqual(regimes.anexo_efetivo(f, 300_000)[0], "III")   # 33%
        self.assertEqual(regimes.anexo_efetivo(f, 500_000)[0], "V")     # 20%

    def test_simples_compara_das_x_regime_regular(self):
        r = regimes.comparar(30_000, 0, {"regime": "simples", "rbt12": 360_000, "anexo": "III"})
        self.assertEqual(r["grupo"], "simples")
        self.assertEqual({c["chave"] for c in r["cenarios"]}, {"simples_das", "simples_regular_2027", "simples_regular_2033"})
        self.assertAlmostEqual(cen(r, "simples_das")["total"], 30_000 * 0.086, places=2)
        self.assertEqual(r["atual"], "simples_das")
        self.assertEqual(r["secoes"][0]["chaves"], ["simples_das", "simples_regular_2027"])

    def test_simples_nao_mostra_presumido_nem_real(self):
        r = regimes.comparar(30_000, 0, {"regime": "simples", "rbt12": 360_000})
        self.assertFalse(any(c["chave"].startswith(("presumido", "real")) for c in r["cenarios"]))

    def test_regime_regular_tira_pis_cofins_do_das_e_cobra_ibs_cbs(self):
        f = {"regime": "simples", "rbt12": 360_000, "anexo": "III"}
        r = regimes.comparar(30_000, 10_000, f, credito_ibs=6_000)
        das = 30_000 * 0.086
        reg = itens(r, "simples_regular_2027")
        self.assertAlmostEqual(reg["DAS sem PIS/Cofins"], das * (1 - 0.1710), places=2)   # 2ª faixa do Anexo III
        self.assertAlmostEqual(reg["CBS"], 24_000 * (0.0921 - 0.001), places=2)            # base = faturamento − crédito
        self.assertAlmostEqual(reg["IBS"], 24_000 * 0.001, places=2)
        pleno = itens(r, "simples_regular_2033")
        self.assertAlmostEqual(pleno["DAS sem PIS/Cofins e ISS"], das * (1 - 0.1710 - 0.3200), places=2)

    def test_mais_credito_reduz_o_regime_regular(self):
        f = {"regime": "simples", "rbt12": 360_000}
        sem = cen(regimes.comparar(30_000, 20_000, f, credito_ibs=0), "simples_regular_2027")["total"]
        com = cen(regimes.comparar(30_000, 20_000, f, credito_ibs=20_000), "simples_regular_2027")["total"]
        self.assertGreater(sem, com)

    def test_estourou_o_limite_vira_presumido_x_real(self):
        r = regimes.comparar(500_000, 0, {"regime": "simples", "rbt12": 6_000_000})
        self.assertTrue(r["fora_do_simples"])
        self.assertEqual(r["grupo"], "lucro")
        self.assertIsNone(r["atual"])
        self.assertTrue(any("não pode permanecer no Simples" in a for a in r["avisos"]))

    def test_insight_de_clientes_pj(self):
        r = regimes.comparar(30_000, 0, {"regime": "simples", "rbt12": 360_000}, clientes_pj=0.8)
        self.assertTrue(any("80%" in i for i in r["insights"]))


class PresumidoReal(unittest.TestCase):
    def test_so_presumido_e_real_fora_do_simples(self):
        r = regimes.comparar(100_000, 0, {"regime": "presumido", "rbt12": 1_200_000})
        self.assertEqual(r["grupo"], "lucro")
        self.assertEqual({c["chave"] for c in r["cenarios"]}, {f"{b}_{h}" for b in ("presumido", "real") for h in ("hoje", "2027", "2033")})
        self.assertEqual(r["atual"], "presumido_hoje")
        self.assertEqual([s["atual"] for s in r["secoes"]], ["presumido_hoje", "presumido_2027", "presumido_2033"])
        r2 = regimes.comparar(100_000, 0, {"regime": "real", "rbt12": 1_200_000})
        self.assertEqual(r2["atual"], "real_hoje")

    def test_presumido_servicos(self):
        r = regimes.comparar(100_000, 0, {"regime": "presumido", "rbt12": 1_200_000, "iss_aliquota": 0.05})
        p = itens(r, "presumido_hoje")
        self.assertAlmostEqual(p["PIS"], 650.0)
        self.assertAlmostEqual(p["COFINS"], 3000.0)
        self.assertAlmostEqual(p["ISS"], 5000.0)
        self.assertAlmostEqual(p["IRPJ"], 32_000 * 0.15 + 12_000 * 0.10)   # base 32% + adicional acima de 20 mil
        self.assertAlmostEqual(p["CSLL"], 32_000 * 0.09)

    def test_real_credita_pis_cofins_pelo_credito_estimado(self):
        r = regimes.comparar(100_000, 40_000, {"regime": "real", "rbt12": 1_200_000, "iss_aliquota": 0.0})   # sem estimativa: tudo credita
        self.assertAlmostEqual(itens(r, "real_hoje")["PIS"], 60_000 * 0.0165)
        self.assertAlmostEqual(itens(r, "real_hoje")["COFINS"], 60_000 * 0.076)
        r = regimes.comparar(100_000, 40_000, {"regime": "real", "rbt12": 1_200_000, "iss_aliquota": 0.0}, credito_pc=10_000)
        self.assertAlmostEqual(itens(r, "real_hoje")["PIS"], 90_000 * 0.0165)

    def test_real_sem_lucro_nao_paga_irpj(self):
        r = regimes.comparar(10_000, 20_000, {"regime": "real", "rbt12": 120_000, "iss_aliquota": 0.0})
        self.assertEqual(itens(r, "real_hoje")["IRPJ"], 0.0)
        self.assertEqual(itens(r, "real_hoje")["CSLL"], 0.0)

    def test_reforma_credita_tambem_no_presumido(self):
        f = {"regime": "presumido", "rbt12": 1_200_000, "iss_aliquota": 0.05}
        r = regimes.comparar(100_000, 20_000, f)
        for ch in ("presumido_2033", "real_2033"):
            ibs_cbs = sum(v for n, v in cen(r, ch)["itens"] if n.startswith(("CBS", "IBS")))
            self.assertAlmostEqual(ibs_cbs, 80_000 * (0.0921 + 0.1870), places=2)
        self.assertFalse(any(n.startswith("ISS") for n, _ in cen(r, "presumido_2033")["itens"]))   # ISS extinto em 2033
        self.assertTrue(any(n.startswith("ISS") for n, _ in cen(r, "presumido_2027")["itens"]))    # ainda existe em 2027
        reg = regimes.comparar(100_000, 20_000, {**f, "profissao_regulamentada": True})
        v = sum(v for n, v in cen(reg, "presumido_2033")["itens"] if n.startswith(("CBS", "IBS")))
        self.assertAlmostEqual(v, 80_000 * (0.0921 + 0.1870) * 0.7, places=2)

    def test_presumido_acima_de_78_milhoes_nao_elegivel(self):
        r = regimes.comparar(8_000_000, 0, {"regime": "real", "rbt12": 90_000_000})
        self.assertFalse(cen(r, "presumido_hoje")["elegivel"])
        self.assertIsNone(r["secoes"][0]["melhor"])

    def test_avisos_sem_dados(self):
        r = regimes.comparar(10_000, 0, {"regime": "simples"})
        self.assertTrue(any("12 meses" in a for a in r["avisos"]))

    def test_melhor_por_secao(self):
        r = regimes.comparar(30_000, 0, {"regime": "presumido", "rbt12": 360_000, "iss_aliquota": 0.05})
        self.assertIn(r["melhor"], ("presumido_hoje", "real_hoje"))
        self.assertEqual(r["melhor"], r["secoes"][0]["melhor"])


class Credito(unittest.TestCase):
    def arq(self, cat, valor, cod="", simples="", toma="22222222000122"):
        return {"cat": cat, "doc": {"valor": valor, "servico_cod": cod, "emitente_simples": simples, "tomador_doc": toma}}

    def test_categorias_por_item_da_lc116(self):
        self.assertEqual(credito.categoria({"servico_cod": "010701"}), "provavel")
        self.assertEqual(credito.categoria({"servico_cod": "060101"}), "improvavel")
        self.assertEqual(credito.categoria({"servico_cod": "040101"}), "depende")
        self.assertEqual(credito.categoria({}), "depende")

    def test_estimar_aplica_pesos_e_fornecedor_do_simples(self):
        r = credito.estimar([self.arq("servico_tomado", 1000, "170101"), self.arq("servico_tomado", 1000, "040101"),
                             self.arq("servico_tomado", 1000, "060101"), self.arq("servico_tomado", 1000, "170101", simples="3"),
                             self.arq("servico_prestado", 9999, "170101")])
        self.assertEqual(r["tomados"], 4000)
        self.assertAlmostEqual(r["pis_cofins"], 1000 + 500 + 0 + 1000)       # fornecedor do Simples não muda PIS/Cofins
        self.assertAlmostEqual(r["ibs_cbs"], 1000 + 500 + 0 + 1000 * 0.15)   # mas reduz o crédito de IBS/CBS
        self.assertEqual(r["de_simples"], 1000)

    def test_participacao_pj(self):
        r = credito.participacao_pj([self.arq("servico_prestado", 300), self.arq("servico_prestado", 100, toma="12345678901"),
                                     self.arq("servico_tomado", 500)])
        self.assertAlmostEqual(r, 0.75)
        self.assertIsNone(credito.participacao_pj([]))


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
