import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.core import ErroAdge
from adge_nf.emissao import dps
from adge_nf.emissao.lancamento import Lancamento

EMPRESA = {"nome": "ADGE SERVIÇOS LTDA", "cnpj": "11.222.333/0001-81"}
EMPRESA_EMISSAO_PRESUMIDO = {"regime": "presumido", "inscricao_municipal": "123", "municipio": "Londrina", "uf": "PR",
                             "codigo_municipio_ibge": "4113700"}
EMPRESA_EMISSAO_MEI = {"regime": "mei", "inscricao_municipal": "", "municipio": "Londrina", "uf": "PR"}

PERFIL_RESIDENCIAL = {
    "id": "residencial", "nome": "Locação residencial", "ctn": "17.09.01", "nbs": "110021000",
    "tributacao_iss": {"codigo": "X"}, "retencao_iss": False,
    "pis_cofins": {"incluir": True, "regime": "cumulativo", "cst_pis": "01", "cst_cofins": "01",
                   "aliquota_pis": 0.65, "aliquota_cofins": 3.0},
    "descricao": {"modo": "fixo", "texto": "Locação de imóvel residencial"},
    "informacoes_complementares": "Sem retenções.",
}

LANC = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901", valor=1250.0,
                  competencia="2026-11", data_prestacao="2026-11-05")


class CamposEssenciais(unittest.TestCase):
    def test_perfil_sem_ctn_ou_nbs_levanta_erro_claro(self):
        with self.assertRaises(ErroAdge):
            dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, {"id": "x", "nome": "Incompleto"}, None, LANC)

    def test_monta_prestador_tomador_e_servico(self):
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, PERFIL_RESIDENCIAL, None, LANC)
        self.assertEqual(campos["prestador"]["cnpj"], "11222333000181")
        self.assertEqual(campos["tomador"]["documento"], "12345678901")
        self.assertEqual(campos["servico"]["nbs"], "110021000")
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

    def test_nunca_entra_para_mei_mesmo_se_o_perfil_mandar_incluir(self):
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_MEI, PERFIL_RESIDENCIAL, None, LANC)
        self.assertIsNone(campos["valores"]["pis_cofins"])

    def test_fora_quando_perfil_nao_pede(self):
        perfil = dict(PERFIL_RESIDENCIAL, pis_cofins={"incluir": False})
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, perfil, None, LANC)
        self.assertIsNone(campos["valores"]["pis_cofins"])


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

    def test_modo_mes_ano_chama_aplicar_marcadores(self):
        perfil = dict(PERFIL_RESIDENCIAL, descricao={"modo": "mes_ano", "texto": "Aluguel de {mes}/{ano}"})
        chamadas = []

        def fake_aplicar(texto, mes, ano):
            chamadas.append((texto, mes, ano))
            return f"Aluguel de Novembro/2026"

        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, perfil, None, LANC, aplicar_marcadores=fake_aplicar)
        self.assertEqual(campos["descricao"], "Aluguel de Novembro/2026")
        self.assertEqual(chamadas, [("Aluguel de {mes}/{ano}", 11, 2026)])

    def test_modo_mes_ano_sem_aplicar_marcadores_levanta_erro_claro(self):
        perfil = dict(PERFIL_RESIDENCIAL, descricao={"modo": "mes_ano", "texto": "Aluguel de {mes}"})
        with self.assertRaises(ErroAdge):
            dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, perfil, None, LANC)


class InformacoesComplementares(unittest.TestCase):
    def test_usa_a_do_perfil_por_padrao(self):
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, PERFIL_RESIDENCIAL, None, LANC)
        self.assertEqual(campos["informacoes_complementares"], "Sem retenções.")

    def test_tomador_pode_sobrescrever(self):
        tomador = {"informacoes_complementares": {"modo": "fixo", "texto": "Texto próprio"}}
        campos = dps.montar_campos(EMPRESA, EMPRESA_EMISSAO_PRESUMIDO, PERFIL_RESIDENCIAL, tomador, LANC)
        self.assertEqual(campos["informacoes_complementares"], "Texto próprio")


class MontarXmlAindaNaoImplementado(unittest.TestCase):
    def test_levanta_not_implemented_com_mensagem_clara(self):
        with self.assertRaises(NotImplementedError):
            dps.montar_xml({})


if __name__ == "__main__":
    unittest.main()
