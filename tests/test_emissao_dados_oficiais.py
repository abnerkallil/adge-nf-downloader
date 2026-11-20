import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.emissao import dados_oficiais as do


class CtnLista(unittest.TestCase):
    def test_lista_tem_os_338_codigos_do_anexo_b(self):
        self.assertEqual(len(do.listar_ctn()), 338)

    def test_existe_com_codigo_e_descricao_juntos(self):
        self.assertTrue(do.ctn_existe("99.01.01 - Serviços sem a incidência de ISSQN e ICMS"))

    def test_existe_so_com_o_codigo(self):
        self.assertTrue(do.ctn_existe("99.01.01"))

    def test_nao_existe_codigo_inventado(self):
        self.assertFalse(do.ctn_existe("00.00.99 - Isso não existe"))

    def test_texto_vazio_nao_e_erro_de_existencia(self):
        self.assertTrue(do.ctn_existe(""))

    def test_busca_por_pedaco_do_codigo(self):
        achados = do.buscar_ctn("01.01")
        self.assertTrue(any(a.startswith("01.01.01") for a in achados))

    def test_busca_por_palavra_da_descricao_sem_acento(self):
        achados = do.buscar_ctn("analise")
        self.assertTrue(any("Análise" in a for a in achados))

    def test_busca_vazia_devolve_lista_cheia_limitada(self):
        self.assertEqual(len(do.buscar_ctn("", limite=5)), 5)

    def test_busca_sem_pontuacao_acha_codigo_com_pontuacao(self):
        achados = do.buscar_ctn("990101")
        self.assertTrue(any(a.startswith("99.01.01") for a in achados))


class NbsSugestoes(unittest.TestCase):
    def test_busca_por_palavra_sem_acento(self):
        achados = do.buscar_nbs("locacao")
        self.assertTrue(any("Locação" in a for a in achados))

    def test_busca_sem_match_devolve_vazio(self):
        self.assertEqual(do.buscar_nbs("isso não existe de jeito nenhum 12345"), [])

    def test_busca_sem_pontuacao_acha_codigo_com_pontuacao(self):
        achados = do.buscar_nbs("110021000")
        self.assertTrue(any(a.startswith("1.1002.10.00") for a in achados))


class MunicipiosIbge(unittest.TestCase):
    def test_busca_vazia_nao_devolve_a_lista_inteira(self):
        self.assertEqual(do.buscar_municipio(""), [])

    def test_busca_por_nome_sem_acento(self):
        achados = do.buscar_municipio("londrina")
        self.assertTrue(any(a.startswith("Londrina - PR") for a in achados))

    def test_busca_pelo_codigo_ibge(self):
        achados = do.buscar_municipio("4113700")
        self.assertTrue(any(a.startswith("Londrina - PR") for a in achados))

    def test_resolve_texto_formatado_para_o_registro(self):
        reg = do.municipio_por_texto_formatado("Londrina - PR")
        self.assertIsNotNone(reg)
        self.assertEqual(reg["codigo_ibge"], "4113700")
        self.assertEqual(reg["uf"], "PR")

    def test_texto_nao_encontrado_devolve_none(self):
        self.assertIsNone(do.municipio_por_texto_formatado("Isso não é um município - XX"))


class MoedasIso4217(unittest.TestCase):
    def test_busca_por_nome_em_portugues(self):
        achados = do.buscar_moeda("dolar americano")
        self.assertTrue(any(a.startswith("840 -") for a in achados))

    def test_busca_pelo_codigo_iso(self):
        achados = do.buscar_moeda("USD")
        self.assertTrue(any(a.startswith("840 -") for a in achados))

    def test_busca_pelo_codigo_numerico(self):
        achados = do.buscar_moeda("840")
        self.assertTrue(any("USD" in a for a in achados))

    def test_resolve_texto_formatado_para_o_registro(self):
        achados = do.buscar_moeda("840")
        reg = do.moeda_por_texto_formatado(achados[0])
        self.assertIsNotNone(reg)
        self.assertEqual(reg["codigo_numerico"], "840")
        self.assertEqual(reg["codigo_iso"], "USD")

    def test_busca_vazia_nao_devolve_a_lista_inteira(self):
        self.assertEqual(do.buscar_moeda(""), [])


class CClassTribLista(unittest.TestCase):
    def test_lista_tem_os_173_codigos_oficiais(self):
        self.assertEqual(len(do.listar_cclasstrib()), 173)

    def test_busca_por_codigo_sem_pontuacao(self):
        achados = do.buscar_cclasstrib("000001")
        self.assertTrue(any(a.startswith("000001") for a in achados))

    def test_busca_por_palavra_do_nome(self):
        achados = do.buscar_cclasstrib("integral")
        self.assertTrue(len(achados) > 0)

    def test_cst_por_cclasstrib(self):
        self.assertEqual(do.cst_por_cclasstrib("000001"), "000")

    def test_cst_por_cclasstrib_inexistente_devolve_vazio(self):
        self.assertEqual(do.cst_por_cclasstrib("999999"), "")

    def test_info_legal_tem_link_da_lei(self):
        info = do.info_legal_cclasstrib("000001")
        self.assertIn("planalto.gov.br", info["link_lei"])

    def test_cclasstrib_por_texto_formatado_resolve_o_registro(self):
        achados = do.buscar_cclasstrib("000001")
        reg = do.cclasstrib_por_texto_formatado(achados[0])
        self.assertIsNotNone(reg)
        self.assertEqual(reg["cclasstrib"], "000001")

    def test_lista_cst_ibscbs_e_fechada(self):
        cst = do.listar_cst_ibscbs()
        self.assertTrue(any(c.startswith("000 -") for c in cst))
        self.assertEqual(len(cst), len({c.split(" - ")[0] for c in cst}))


class SugestaoCClassTribPorNbs(unittest.TestCase):
    def test_nbs_fora_do_anexo_viii_devolve_vazio(self):
        """O Anexo VIII (rascunho da Receita) não cobre todo NBS — ex.: locação residencial
        (1.1002.10.00) não está nele hoje. Nunca trava: só não sugere nada."""
        self.assertEqual(do.sugerir_cclasstrib_por_nbs("1.1002.10.00 - Locação residencial"), [])

    def test_nbs_coberto_devolve_sugestao_formatada(self):
        sugestoes = do.sugerir_cclasstrib_por_nbs("1.1502.10.00 - Serviços de projeto")
        self.assertTrue(any(s.startswith("000001") for s in sugestoes))


class IndicadorDeOperacao(unittest.TestCase):
    def test_busca_por_palavra(self):
        achados = do.buscar_indop("imovel")
        self.assertTrue(len(achados) > 0)

    def test_busca_pelo_codigo(self):
        achados = do.buscar_indop("020101")
        self.assertTrue(any(a.startswith("020101") for a in achados))


class AlertaRegime(unittest.TestCase):
    def test_sem_pista_nenhuma_nao_avisa(self):
        # 99.01.01 é o "sem incidência" genérico: não tem cod_ativ_sn associado no Anexo VIII.
        self.assertEqual(do.alerta_ctn_regime("99.01.01", "presumido"), "")

    def test_ctn_tipicamente_simples_numa_empresa_presumido_avisa(self):
        # 01.01.01 (TI) aparece no Anexo VIII associado ao Fator R / Anexo III ou V do Simples.
        aviso = do.alerta_ctn_regime("01.01.01", "presumido")
        self.assertIn("Simples Nacional", aviso)
        self.assertIn("Anexo VIII", aviso)

    def test_mesmo_ctn_numa_empresa_do_simples_nao_avisa(self):
        self.assertEqual(do.alerta_ctn_regime("01.01.01", "simples"), "")

    def test_codigo_curto_nao_quebra(self):
        self.assertEqual(do.alerta_ctn_regime("9", "presumido"), "")

    def test_texto_formatado_tambem_funciona(self):
        aviso = do.alerta_ctn_regime("01.01.01 - Análise e desenvolvimento de sistemas.", "real")
        self.assertIn("Simples Nacional", aviso)


if __name__ == "__main__":
    unittest.main()
