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


class NbsSugestoes(unittest.TestCase):
    def test_busca_por_palavra_sem_acento(self):
        achados = do.buscar_nbs("locacao")
        self.assertTrue(any("Locação" in a for a in achados))

    def test_busca_sem_match_devolve_vazio(self):
        self.assertEqual(do.buscar_nbs("isso não existe de jeito nenhum 12345"), [])


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
