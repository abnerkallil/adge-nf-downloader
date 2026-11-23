"""Valida de verdade o XML que `dps.montar_xml` gera contra o XSD oficial (`tests/fixtures/xsd/`,
ver README.md ali) — não só a leitura da planilha de leiaute. Casos cobertos: Ferreira Maria
(Lucro Presumido, piloto do fluxo ponta a ponta) e um caso MEI (PIS/COFINS proibido)."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "fixtures"))

from adge_nf.core import ErroAdge
from adge_nf.emissao import config_schema as es
from adge_nf.emissao import dps
from adge_nf.emissao.lancamento import Lancamento
from xsd_schema import esquema_dps

EMPRESA = {"nome": "FERREIRA MARIA HOLDING LTDA", "cnpj": "12.345.678/0001-90"}


def empresa_emissao(**over):
    base = es.migrar({"regime": "presumido", "inscricao_municipal": "123456",
                       "municipio": "Londrina", "uf": "PR", "codigo_municipio_ibge": "4113700"})
    base.update(over)
    return base


def perfil_locacao(**over):
    p = es.perfil_padrao("Locação de imóvel")
    p.update({
        "ctn": "17.09.01 - Locação de bens móveis", "nbs": "110021000 - Locação residencial",
        "issqn": {"trib_issqn": 1, "tp_ret_issqn": 1},
        "pis_cofins": {"incluir": True, "cst_pis": "01", "cst_cofins": "01",
                        "aliquota_pis": 0.65, "aliquota_cofins": 3.0, "tp_ret_pis_cofins": 0},
        "descricao": {"modo": "fixo", "texto": "Aluguel de imóvel"},
        "informacoes_complementares": "",
    })
    p.update(over)
    return p


def validar(xml: str):
    from lxml import etree
    doc = etree.fromstring(xml.encode("utf-8"))
    schema = esquema_dps()
    valido = schema.validate(doc)
    return valido, schema.error_log


class ValidacaoContraOXsdOficial(unittest.TestCase):
    def test_ferreira_maria_presumido_com_pis_cofins(self):
        empresa_emissao_fm = empresa_emissao()
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao_fm, perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=1)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))

    def test_mei_sem_pis_cofins(self):
        empresa_emissao_mei = empresa_emissao(regime="mei")
        lanc = Lancamento(tomador_nome="Cliente MEI", tomador_documento="12345678000195",
                           valor=500.0, competencia="2026-11", data_prestacao="2026-11-10")
        campos = dps.montar_campos(EMPRESA, empresa_emissao_mei, perfil_locacao(), None, lanc)
        self.assertIsNone(campos["valores"]["pis_cofins"])
        xml = dps.montar_xml(campos, serie="1", numero=2)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))

    def test_sem_inscricao_municipal_omite_a_tag_im(self):
        """IM é opcional (`prest/IM`, minOccurs="0", RN 201) — sem ela, a tag some do XML
        e a nota continua válida contra o XSD oficial."""
        empresa_emissao_sem_im = empresa_emissao(inscricao_municipal="")
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao_sem_im, perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=3)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertNotIn("<IM>", xml)

    def test_telefone_e_email_do_prestador(self):
        empresa_emissao_com_contato = empresa_emissao(telefone="(43) 99999-9999", email="contato@ferreiramaria.com.br")
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao_com_contato, perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=26)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<fone>43999999999</fone>", xml)
        self.assertIn("<email>contato@ferreiramaria.com.br</email>", xml)

    def test_sem_telefone_nem_email_omite_as_tags_do_prestador(self):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=27)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertNotIn("<fone>", xml)

    def test_obra_com_cobra_e_inscricao_imobiliaria(self):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901", valor=1250.0,
                           competencia="2026-11", data_prestacao="2026-11-05",
                           obra_codigo="CNO123456789", obra_inscricao_imobiliaria="IPTU-0001")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=19)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<cObra>CNO123456789</cObra>", xml)
        self.assertIn("<inscImobFisc>IPTU-0001</inscImobFisc>", xml)

    def test_obra_com_cib(self):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05", obra_cib="12345678")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=20)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<cCIB>12345678</cCIB>", xml)

    def test_sem_obra_omite_o_grupo(self):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=21)
        self.assertNotIn("<obra>", xml)

    def test_obra_com_endereco_nacional(self):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901", valor=1250.0,
                           competencia="2026-11", data_prestacao="2026-11-05",
                           obra_end_cep="86010000", obra_end_logradouro="Rua das Flores",
                           obra_end_numero="100", obra_end_bairro="Centro")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=24)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<CEP>86010000</CEP>", xml)
        self.assertIn("<xBairro>Centro</xBairro>", xml)

    def test_obra_com_endereco_no_exterior(self):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901", valor=1250.0,
                           competencia="2026-11", data_prestacao="2026-11-05",
                           obra_end_logradouro="Main Street", obra_end_numero="42", obra_end_bairro="Downtown",
                           obra_end_postal_exterior="10001", obra_end_cidade_exterior="New York",
                           obra_end_estado_exterior="NY")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=25)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<cEndPost>10001</cEndPost>", xml)
        self.assertIn("<xCidade>New York</xCidade>", xml)

    def test_exportacao_com_moeda_estrangeira(self):
        """tpMoeda é o código NUMÉRICO de 3 dígitos da tabela do Banco Central (não o código ISO
        de letras) — "220" é o dólar americano nessa tabela."""
        lanc = Lancamento(tomador_nome="Cliente Estrangeiro", tomador_documento="12345678901", valor=1250.0,
                           competencia="2026-11", data_prestacao="2026-11-05",
                           exportacao_moeda="220", exportacao_valor_moeda=250.0)
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=22)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<tpMoeda>220</tpMoeda>", xml)
        self.assertIn("<vServMoeda>250.00</vServMoeda>", xml)

    def test_sem_exportacao_omite_comext(self):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=23)
        self.assertNotIn("<comExt>", xml)

    def test_intermediario_do_servico(self):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901", valor=1250.0,
                           competencia="2026-11", data_prestacao="2026-11-05",
                           intermediario_nome="Plataforma XYZ", intermediario_documento="12345678000195")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=15)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<interm>", xml)
        self.assertIn("<xNome>Plataforma XYZ</xNome>", xml)

    def test_sem_intermediario_omite_o_grupo(self):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=16)
        self.assertNotIn("<interm>", xml)

    def test_substituicao_de_nfse(self):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901", valor=1250.0,
                           competencia="2026-11", data_prestacao="2026-11-05",
                           substituicao_chave="1" * 50, substituicao_motivo="99",
                           substituicao_motivo_texto="Corrigindo valor lançado errado na nota anterior")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=17)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn(f"<chSubstda>{'1' * 50}</chSubstda>", xml)
        self.assertIn("<cMotivo>99</cMotivo>", xml)

    def test_deducao_simples_de_base(self):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901", valor=1250.0,
                           competencia="2026-11", data_prestacao="2026-11-05", deducao_valor=100.0)
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=18)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<vDR>100.00</vDR>", xml)

    def test_tomador_estrangeiro_com_nif(self):
        tomador = {"nif": "FR123456789"}
        lanc = Lancamento(tomador_nome="Client Étranger", tomador_documento="", valor=1250.0,
                           competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), tomador, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=12)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<NIF>FR123456789</NIF>", xml)

    def test_tomador_estrangeiro_sem_nif_com_motivo(self):
        tomador = {"motivo_sem_nif": "1"}
        lanc = Lancamento(tomador_nome="Client Étranger", tomador_documento="", valor=1250.0,
                           competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), tomador, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=13)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<cNaoNIF>1</cNaoNIF>", xml)

    def test_tomador_sem_documento_nif_ou_motivo_levanta_erro_claro(self):
        lanc = Lancamento(tomador_nome="Sem Identificação", tomador_documento="", valor=1250.0,
                           competencia="2026-11", data_prestacao="2026-11-05")
        with self.assertRaises(ErroAdge):
            campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
            dps.montar_xml(campos, serie="1", numero=14)

    def test_desconto_incondicionado_e_condicionado(self):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901", valor=1250.0,
                           competencia="2026-11", data_prestacao="2026-11-05",
                           desconto_incondicionado=50.0, desconto_condicionado=20.0)
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=8)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<vDescIncond>50.00</vDescIncond>", xml)
        self.assertIn("<vDescCond>20.00</vDescCond>", xml)

    def test_sem_desconto_omite_o_grupo(self):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=9)
        self.assertNotIn("vDescCondIncond", xml)

    def test_retencao_de_cp_irrf_csll(self):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901", valor=1250.0,
                           competencia="2026-11", data_prestacao="2026-11-05",
                           retencao_cp=137.50, retencao_irrf=18.75, retencao_csll_outros=12.0)
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=10)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<vRetCP>137.50</vRetCP>", xml)
        self.assertIn("<vRetIRRF>18.75</vRetIRRF>", xml)
        self.assertIn("<vRetCSLL>12.00</vRetCSLL>", xml)

    def test_mei_nao_leva_retencao_de_cp_mesmo_se_informada(self):
        """tribFed inteiro é proibido pro MEI (RN 518) — a retenção de CP/IRRF/CSLL não pode
        montar esse grupo, mesmo que o lançamento (por engano) traga um valor."""
        lanc = Lancamento(tomador_nome="Cliente MEI", tomador_documento="12345678000195", valor=500.0,
                           competencia="2026-11", data_prestacao="2026-11-10", retencao_cp=50.0)
        campos = dps.montar_campos(EMPRESA, empresa_emissao(regime="mei"), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=11)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertNotIn("tribFed", xml)

    def test_regime_especial_de_tributacao_entra_na_regtrib(self):
        """`prest/regTrib/regEspTrib` (TSRegEspTrib, 0-9) reflete o que foi cadastrado pra empresa,
        em vez de ficar sempre em "0" (nenhum)."""
        empresa_emissao_cooperativa = empresa_emissao(regime_especial_tributacao=1)
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao_cooperativa, perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=7)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<regEspTrib>1</regEspTrib>", xml)

    def test_telefone_e_email_do_tomador_quando_preenchidos(self):
        """`toma/fone`/`toma/email` (ambos opcionais no XSD, `TCInfoPessoa`) entram quando o
        tomador cadastrado tem telefone/e-mail."""
        tomador = {"telefone": "(43) 99999-9999", "email": "fulano@exemplo.com.br"}
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), tomador, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=5)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<fone>43999999999</fone>", xml)
        self.assertIn("<email>fulano@exemplo.com.br</email>", xml)

    def test_sem_telefone_e_email_omite_as_tags(self):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=6)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertNotIn("<fone>", xml)
        self.assertNotIn("<email>", xml)

    def test_endereco_do_prestador_e_do_tomador_quando_preenchidos(self):
        """`prest/end`/`toma/end` (ambos opcionais no XSD) entram quando os dados existem — gap
        fechado pelo Dev A em v2/config-emissao (commit 36caf9b)."""
        empresa_emissao_fm = empresa_emissao(
            endereco={"cep": "86050000", "logradouro": "Av. Higienópolis", "numero": "100",
                       "complemento": "Sala 2", "bairro": "Centro"})
        tomador = {"endereco": {"cep": "86010000", "logradouro": "Rua das Flores", "numero": "50",
                                 "bairro": "Centro", "codigo_municipio_ibge": "4113700"}}
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao_fm, perfil_locacao(), tomador, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=4)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<xLgr>Av. Higienópolis</xLgr>", xml)
        self.assertIn("<xLgr>Rua das Flores</xLgr>", xml)
        self.assertIn("<cLocPrestacao>4113700</cLocPrestacao>", xml)

    def test_simples_sem_totTrib_levanta_erro_claro(self):
        from adge_nf.core import ErroAdge
        empresa_emissao_simples = empresa_emissao(regime="simples")
        perfil = perfil_locacao(pis_cofins={"incluir": False})
        lanc = Lancamento(tomador_nome="Cliente Simples", tomador_documento="12345678901",
                           valor=800.0, competencia="2026-11", data_prestacao="2026-11-12")
        campos = dps.montar_campos(EMPRESA, empresa_emissao_simples, perfil, None, lanc)
        with self.assertRaises(ErroAdge):
            dps.montar_xml(campos, serie="1", numero=3)


if __name__ == "__main__":
    unittest.main()
