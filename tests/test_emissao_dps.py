import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.core import ErroAdge
from adge_nf.emissao import config_schema as es
from adge_nf.emissao import dps
from adge_nf.emissao.lancamento import Lancamento

EMPRESA = {"nome": "ADGE SERVIÇOS LTDA", "cnpj": "11.222.333/0001-81"}


def empresa_emissao(**over):
    base = es.migrar({"regime": "presumido", "inscricao_municipal": "123", "municipio": "Londrina",
                       "uf": "PR", "codigo_municipio_ibge": "4113700"})
    base.update(over)
    return base


EMPRESA_EMISSAO_PRESUMIDO = empresa_emissao()
EMPRESA_EMISSAO_MEI = empresa_emissao(regime="mei")
EMPRESA_EMISSAO_SIMPLES = empresa_emissao(regime="simples")


def perfil_residencial(**over):
    p = es.perfil_padrao("Locação residencial")
    p.update({
        "ctn": "17.09.01 - Locação de bens móveis", "nbs": "110021000 - Locação residencial",
        "issqn": {"trib_issqn": 4, "tp_ret_issqn": 1},
        "pis_cofins": {"incluir": True, "cst_pis": "01", "cst_cofins": "01",
                        "aliquota_pis": 0.65, "aliquota_cofins": 3.0, "tp_ret_pis_cofins": 0},
        "descricao": {"modo": "fixo", "texto": "Locação de imóvel residencial"},
        "informacoes_complementares": "Sem retenções.",
    })
    p.update(over)
    return p


PERFIL_RESIDENCIAL = perfil_residencial()

LANC = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901", valor=1250.0,
                  competencia="2026-11", data_prestacao="2026-11-05")


class CamposEssenciais(unittest.TestCase):
    def test_perfil_sem_ctn_ou_nbs_levanta_erro_claro(self):
        with self.assertRaises(ErroAdge):
            dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, es.perfil_padrao("Incompleto"), None, LANC)

    def test_sem_codigo_ibge_da_empresa_levanta_erro_claro(self):
        with self.assertRaises(ErroAdge):
            dps.montar_campos(EMPRESA, empresa_emissao(codigo_municipio_ibge=""), PERFIL_RESIDENCIAL, None, LANC)

    def test_monta_prestador_tomador_e_servico(self):
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, PERFIL_RESIDENCIAL, None, LANC)
        self.assertEqual(campos["prestador"]["cnpj"], "11222333000181")
        self.assertEqual(campos["tomador"]["documento"], "12345678901")
        self.assertEqual(campos["servico"]["nbs"], "110021000")
        self.assertEqual(campos["servico"]["ctn"], "170901")
        self.assertEqual(campos["valores"]["valor_servico"], 1250.0)
        self.assertEqual(campos["competencia"], "2026-11")
        self.assertEqual(campos["data_emissao"], "2026-11-05")


class PisCofins(unittest.TestCase):
    def test_entra_quando_perfil_pede_e_empresa_nao_e_mei(self):
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, PERFIL_RESIDENCIAL, None, LANC)
        pc = campos["valores"]["pis_cofins"]
        self.assertIsNotNone(pc)
        self.assertEqual(pc["valor_pis"], round(1250.0 * 0.65 / 100, 2))
        self.assertEqual(pc["valor_cofins"], round(1250.0 * 3.0 / 100, 2))
        self.assertEqual(pc["tp_ret_pis_cofins"], 0)

    def test_nunca_entra_para_mei_mesmo_se_o_perfil_mandar_incluir(self):
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_MEI, PERFIL_RESIDENCIAL, None, LANC)
        self.assertIsNone(campos["valores"]["pis_cofins"])

    def test_obrigatorio_no_presumido_sem_incluir_e_erro_de_configuracao(self):
        perfil = perfil_residencial(pis_cofins={"incluir": False})
        with self.assertRaises(ErroAdge):
            dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, perfil, None, LANC)

    def test_opcional_no_simples_sem_incluir_fica_fora_sem_erro(self):
        perfil = perfil_residencial(pis_cofins={"incluir": False})
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_SIMPLES, perfil, None, LANC)
        self.assertIsNone(campos["valores"]["pis_cofins"])

    def test_retencao_do_lancamento_sobrescreve_tp_ret_pis_cofins(self):
        lanc = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=1000.0,
                          competencia="2026-11", retencao_pis_cofins_csll=True)
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, PERFIL_RESIDENCIAL, None, lanc)
        self.assertEqual(campos["valores"]["pis_cofins"]["tp_ret_pis_cofins"], 3)

    def test_sem_resposta_de_retencao_usa_padrao_do_perfil(self):
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, PERFIL_RESIDENCIAL, None, LANC)
        self.assertEqual(campos["valores"]["pis_cofins"]["tp_ret_pis_cofins"],
                         PERFIL_RESIDENCIAL["pis_cofins"]["tp_ret_pis_cofins"])


class DataEmissaoSemDataDePrestacao(unittest.TestCase):
    """Rejeição real em produção (E0015, 24/11): sem data de prestação, o padrão era o último dia
    da competência, mas isso cai depois de hoje (dhEmi) sempre que a competência é o mês corrente
    e ele ainda não terminou. `montar_campos` agora limita isso a hoje."""

    def test_competencia_do_mes_corrente_usa_hoje_nao_o_fim_do_mes(self):
        import datetime as dt

        hoje = dt.date.today()
        lanc = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=1000.0,
                           competencia=hoje.strftime("%Y-%m"))
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, PERFIL_RESIDENCIAL, None, lanc)
        self.assertEqual(campos["data_emissao"], hoje.isoformat())

    def test_competencia_de_mes_encerrado_continua_usando_o_fim_do_mes(self):
        lanc = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=1000.0,
                           competencia="2020-01")
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, PERFIL_RESIDENCIAL, None, lanc)
        self.assertEqual(campos["data_emissao"], "2020-01-31")

    def test_data_de_prestacao_informada_continua_tendo_prioridade(self):
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, PERFIL_RESIDENCIAL, None, LANC)
        self.assertEqual(campos["data_emissao"], "2026-11-05")


class Descricao(unittest.TestCase):
    def test_usa_a_descricao_fixa_do_perfil_sem_tomador(self):
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, PERFIL_RESIDENCIAL, None, LANC)
        self.assertEqual(campos["descricao"], "Locação de imóvel residencial")

    def test_tomador_com_descricao_fixa_propria_tem_prioridade(self):
        tomador = {"descricao": {"modo": "fixo", "texto": "Texto específico deste tomador"}}
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, PERFIL_RESIDENCIAL, tomador, LANC)
        self.assertEqual(campos["descricao"], "Texto específico deste tomador")

    def test_tomador_herdar_usa_a_do_perfil(self):
        tomador = {"descricao": {"modo": "herdar"}}
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, PERFIL_RESIDENCIAL, tomador, LANC)
        self.assertEqual(campos["descricao"], "Locação de imóvel residencial")

    def test_modo_mes_ano_troca_marcadores(self):
        perfil = perfil_residencial(descricao={"modo": "mes_ano", "texto": "Aluguel de {MES}/{ANO}"})
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, perfil, None, LANC)
        self.assertEqual(campos["descricao"], "Aluguel de Novembro/2026")


class InformacoesComplementares(unittest.TestCase):
    def test_usa_a_do_perfil_por_padrao(self):
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, PERFIL_RESIDENCIAL, None, LANC)
        self.assertEqual(campos["informacoes_complementares"], "Sem retenções.")

    def test_tomador_pode_sobrescrever(self):
        tomador = {"informacoes_complementares": {"modo": "fixo", "texto": "Texto próprio"}}
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, PERFIL_RESIDENCIAL, tomador, LANC)
        self.assertEqual(campos["informacoes_complementares"], "Texto próprio")


if __name__ == "__main__":
    unittest.main()
