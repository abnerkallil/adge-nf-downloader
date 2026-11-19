import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.emissao import config_schema as es


class ConfiguracaoPadrao(unittest.TestCase):
    def test_tem_um_perfil_padrao_valido(self):
        cfg = es.configuracao_padrao()
        self.assertEqual(len(cfg["perfis"]), 1)
        self.assertEqual(cfg["perfil_padrao_id"], cfg["perfis"][0]["id"])
        self.assertEqual(cfg["versao"], es.VERSAO_ATUAL)

    def test_nao_esta_completa_sem_dados(self):
        self.assertFalse(es.configuracao_completa(es.configuracao_padrao()))

    def test_completa_com_regime_im_municipio_endereco_e_perfil(self):
        cfg = es.configuracao_padrao()
        cfg["regime"], cfg["inscricao_municipal"], cfg["municipio"] = "simples", "12345", "Londrina"
        cfg["endereco"]["logradouro"] = "Rua Teste"
        cfg["perfis"][0].update({"ctn": "0107", "nbs": "110021000"})
        self.assertTrue(es.configuracao_completa(cfg))

    def test_sem_endereco_do_prestador_nao_esta_completa(self):
        cfg = es.configuracao_padrao()
        cfg["regime"], cfg["inscricao_municipal"], cfg["municipio"] = "simples", "12345", "Londrina"
        cfg["perfis"][0].update({"ctn": "0107", "nbs": "110021000"})
        self.assertFalse(es.configuracao_completa(cfg))

    def test_perfil_inativo_nao_conta(self):
        cfg = es.configuracao_padrao()
        cfg["regime"], cfg["inscricao_municipal"], cfg["municipio"] = "simples", "12345", "Londrina"
        cfg["endereco"]["logradouro"] = "Rua Teste"
        cfg["perfis"][0].update({"ctn": "0107", "nbs": "110021000", "ativo": False})
        self.assertFalse(es.configuracao_completa(cfg))


class PisCofinsRegra(unittest.TestCase):
    def test_mei_proibido(self):
        self.assertEqual(es.pis_cofins_regra("mei"), "proibido")

    def test_simples_opcional(self):
        self.assertEqual(es.pis_cofins_regra("simples"), "opcional")

    def test_presumido_e_real_obrigatorio(self):
        self.assertEqual(es.pis_cofins_regra("presumido"), "obrigatorio")
        self.assertEqual(es.pis_cofins_regra("real"), "obrigatorio")


class IssqnRegra(unittest.TestCase):
    def test_mei_nao_aplica(self):
        self.assertEqual(es.issqn_regra("mei"), "nao_aplica")

    def test_demais_regimes_aplicam(self):
        for regime in ("simples", "presumido", "real"):
            self.assertEqual(es.issqn_regra(regime), "aplica")


class EnumsOficiais(unittest.TestCase):
    def test_perfil_padrao_usa_tributavel_e_nao_retido(self):
        p = es.perfil_padrao()
        self.assertEqual(p["issqn"], {"trib_issqn": 1, "tp_ret_issqn": 1})
        self.assertEqual(es.TRIB_ISSQN[1], "Operação tributável")
        self.assertEqual(es.TP_RET_ISSQN[1], "Não retido")

    def test_ferreira_maria_e_nao_incidencia(self):
        p = es.perfil_padrao("Locação residencial")
        p["ctn"], p["nbs"] = "99.01.01", "110021000"
        p["issqn"]["trib_issqn"] = 4
        self.assertEqual(es.TRIB_ISSQN[p["issqn"]["trib_issqn"]], "Não incidência")

    def test_pis_cofins_padrao_nao_retido(self):
        self.assertEqual(es.pis_cofins_padrao()["tp_ret_pis_cofins"], 0)
        self.assertEqual(es.TP_RET_PISCOFINS[0], "PIS/COFINS/CSLL não retidos")

    def test_ibscbs_futuro_reservado_e_vazio(self):
        self.assertEqual(es.perfil_padrao()["ibscbs_futuro"], {})


class Migracao(unittest.TestCase):
    def test_dict_vazio_vira_configuracao_padrao_valida(self):
        cfg = es.migrar({})
        self.assertEqual(cfg["versao"], es.VERSAO_ATUAL)
        self.assertEqual(len(cfg["perfis"]), 1)

    def test_none_tambem_funciona(self):
        cfg = es.migrar(None)
        self.assertEqual(len(cfg["perfis"]), 1)

    def test_preenche_subchaves_que_faltam_num_perfil_salvo_antigo(self):
        bruto = {"versao": 1, "regime": "presumido", "perfis": [{"id": "perfil_x", "nome": "Serviço", "ctn": "0107"}]}
        cfg = es.migrar(bruto)
        p = cfg["perfis"][0]
        self.assertEqual(p["id"], "perfil_x")
        self.assertEqual(p["ctn"], "0107")
        self.assertIn("pis_cofins", p)
        self.assertEqual(p["pis_cofins"]["incluir"], False)
        self.assertEqual(p["issqn"], es.issqn_padrao())

    def test_perfil_padrao_id_orfao_e_corrigido(self):
        bruto = {"perfis": [{"id": "perfil_x"}], "perfil_padrao_id": "nao_existe"}
        cfg = es.migrar(bruto)
        self.assertEqual(cfg["perfil_padrao_id"], "perfil_x")

    def test_tomador_com_perfil_id_orfao_fica_sem_perfil(self):
        bruto = {"perfis": [{"id": "perfil_x"}], "tomadores": [{"id": "t1", "perfil_id": "sumiu"}]}
        cfg = es.migrar(bruto)
        self.assertIsNone(cfg["tomadores"][0]["perfil_id"])

    def test_nao_perde_chave_desconhecida_de_versao_futura(self):
        cfg = es.migrar({"algo_novo_do_futuro": 42})
        self.assertEqual(cfg["algo_novo_do_futuro"], 42)

    def test_preenche_endereco_do_prestador_que_falta(self):
        cfg = es.migrar({"endereco": {"logradouro": "Rua X"}})
        self.assertEqual(cfg["endereco"]["logradouro"], "Rua X")
        self.assertEqual(cfg["endereco"]["cep"], "")

    def test_endereco_do_tomador_ganha_codigo_municipio_ibge_que_faltava(self):
        cfg = es.migrar({"tomadores": [{"id": "t1", "endereco": {"logradouro": "Rua X"}}]})
        self.assertEqual(cfg["tomadores"][0]["endereco"]["codigo_municipio_ibge"], "")


class Marcadores(unittest.TestCase):
    def test_troca_mes_e_ano(self):
        self.assertEqual(es.aplicar_marcadores("Serviços de {MES}/{ANO}", 10, 2026), "Serviços de Outubro/2026")

    def test_texto_sem_marcador_fica_igual(self):
        self.assertEqual(es.aplicar_marcadores("Serviços de consultoria", 10, 2026), "Serviços de consultoria")

    def test_texto_vazio(self):
        self.assertEqual(es.aplicar_marcadores("", 1, 2026), "")


class DescricaoEInfoEfetivas(unittest.TestCase):
    def setUp(self):
        self.perfil = es.perfil_padrao("Locação residencial")
        self.perfil["descricao"] = {"modo": "mes_ano", "texto": "Aluguel de {MES}/{ANO}"}
        self.perfil["informacoes_complementares"] = "Sem incidência de ISS (imóvel residencial)."

    def test_sem_tomador_usa_o_perfil(self):
        self.assertEqual(es.descricao_efetiva(self.perfil, None, 11, 2026), "Aluguel de Novembro/2026")
        self.assertEqual(es.informacoes_complementares_efetivas(self.perfil, None), "Sem incidência de ISS (imóvel residencial).")

    def test_tomador_herdando_usa_o_perfil(self):
        t = es.tomador_padrao("Fulano")
        self.assertEqual(es.descricao_efetiva(self.perfil, t, 11, 2026), "Aluguel de Novembro/2026")

    def test_tomador_com_descricao_fixa_propria_sobrepoe(self):
        t = es.tomador_padrao("Fulano")
        t["descricao"] = {"modo": "fixo", "texto": "Texto exclusivo deste tomador"}
        self.assertEqual(es.descricao_efetiva(self.perfil, t, 11, 2026), "Texto exclusivo deste tomador")

    def test_tomador_com_info_fixa_propria_sobrepoe(self):
        t = es.tomador_padrao("Fulano")
        t["informacoes_complementares"] = {"modo": "fixo", "texto": "Nota específica"}
        self.assertEqual(es.informacoes_complementares_efetivas(self.perfil, t), "Nota específica")


class EncontrarTomador(unittest.TestCase):
    def setUp(self):
        self.cfg = es.configuracao_padrao()
        t1 = es.tomador_padrao("Aparecida Adriana dos Santos")
        t1.update({"documento": "918.042.489-91", "modo_identificacao": "documento",
                   "endereco_livre": "Rua dos Lírios, nº338 - Frente"})
        t2 = es.tomador_padrao("Sem documento")
        t2.update({"documento": "", "modo_identificacao": "endereco", "endereco_livre": "Rua Teste, 10"})
        self.cfg["tomadores"] = [t1, t2]

    def test_casa_por_documento_mesmo_com_formatacao_diferente(self):
        achado = es.encontrar_tomador(self.cfg, documento="91804248991")
        self.assertEqual(achado["nome"], "Aparecida Adriana dos Santos")

    def test_casa_por_nome_quando_documento_nao_bate(self):
        achado = es.encontrar_tomador(self.cfg, documento="00000000000", nome="aparecida adriana dos santos")
        self.assertEqual(achado["nome"], "Aparecida Adriana dos Santos")

    def test_casa_por_endereco_quando_nao_ha_documento_cadastrado(self):
        achado = es.encontrar_tomador(self.cfg, documento="", nome="Outra Pessoa", endereco="rua teste, 10")
        self.assertEqual(achado["nome"], "Sem documento")

    def test_sem_casamento_devolve_none(self):
        self.assertIsNone(es.encontrar_tomador(self.cfg, documento="12312312312", nome="Ninguém", endereco="Nenhum lugar"))

    def test_tomador_inativo_nao_casa(self):
        self.cfg["tomadores"][0]["ativo"] = False
        self.assertIsNone(es.encontrar_tomador(self.cfg, documento="91804248991"))


class IdentificacaoTomador(unittest.TestCase):
    def test_herda_o_padrao_da_empresa_por_padrao(self):
        cfg = es.configuracao_padrao()
        t = es.tomador_padrao("Qualquer um")
        self.assertEqual(es.modo_identificacao_efetivo(cfg, t), "documento")

    def test_tomador_pode_sobrepor_para_endereco(self):
        cfg = es.configuracao_padrao()
        t = es.tomador_padrao("Ferreira Maria - inquilino")
        t["modo_identificacao"] = "endereco"
        self.assertEqual(es.modo_identificacao_efetivo(cfg, t), "endereco")

    def test_endereco_completo_junta_as_partes_preenchidas(self):
        t = es.tomador_padrao("Inquilino")
        t["endereco"].update({"logradouro": "Rua dos Lírios", "numero": "338", "bairro": "Ouro Branco",
                              "municipio": "Londrina", "uf": "PR"})
        self.assertEqual(es.endereco_completo(t), "Rua dos Lírios, 338, Ouro Branco, Londrina, PR")

    def test_endereco_completo_cai_no_texto_livre_sem_campos_estruturados(self):
        t = es.tomador_padrao("Inquilino")
        t["endereco_livre"] = "Rua Teste, 10"
        self.assertEqual(es.endereco_completo(t), "Rua Teste, 10")

    def test_migracao_preenche_endereco_estruturado_que_falta(self):
        cfg = es.migrar({"tomadores": [{"id": "t1", "endereco": {"logradouro": "Rua X"}}]})
        self.assertEqual(cfg["tomadores"][0]["endereco"]["uf"], "")
        self.assertEqual(cfg["tomadores"][0]["endereco"]["logradouro"], "Rua X")

    def test_modo_identificacao_invalido_vira_herdar(self):
        cfg = es.migrar({"tomadores": [{"id": "t1", "modo_identificacao": "lixo"}]})
        self.assertEqual(cfg["tomadores"][0]["modo_identificacao"], "herdar")


if __name__ == "__main__":
    unittest.main()
