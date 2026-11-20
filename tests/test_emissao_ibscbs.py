"""Valida o grupo `IBSCBS` da DPS (reforma tributária) contra o XSD oficial de produção
RESTRITA/homologação (`tests/fixtures/xsd_ibscbs/`, ver README ali — esse grupo não existe no XSD
de produção vigente que `test_emissao_dps_xml.py` usa)."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "fixtures"))

from adge_nf.emissao import config_schema as es
from adge_nf.emissao import dps
from adge_nf.emissao.lancamento import Lancamento
from xsd_schema import esquema_dps_ibscbs

EMPRESA = {"nome": "FERREIRA MARIA HOLDING LTDA", "cnpj": "12.345.678/0001-90"}


def empresa_emissao(**over):
    base = es.migrar({"regime": "presumido", "inscricao_municipal": "123456",
                       "municipio": "Londrina", "uf": "PR", "codigo_municipio_ibge": "4113700"})
    base.update(over)
    return base


def perfil_locacao_residencial(**over):
    p = es.perfil_padrao("Locação residencial")
    p.update({
        "ctn": "17.09.01 - Locação de bens móveis", "nbs": "1.1002.10.00 - Locação residencial",
        "issqn": {"trib_issqn": 1, "tp_ret_issqn": 1},
        "pis_cofins": {"incluir": True, "cst_pis": "01", "cst_cofins": "01",
                        "aliquota_pis": 0.65, "aliquota_cofins": 3.0, "tp_ret_pis_cofins": 0},
        "descricao": {"modo": "fixo", "texto": "Aluguel de imóvel residencial"},
    })
    p.update(over)
    return p


def validar(xml: str):
    from lxml import etree
    doc = etree.fromstring(xml.encode("utf-8"))
    schema = esquema_dps_ibscbs()
    return schema.validate(doc), schema.error_log


class RedutorSocialLocacaoResidencial(unittest.TestCase):
    """Caso real: locação residencial com redutor social (Art. 260, LC 214/2025) — mesmo cenário
    da Joise/Ferreira Maria já usado no resto do app."""

    def test_redutor_social_valido_contra_o_xsd(self):
        lanc = Lancamento(
            tomador_nome="Joise", tomador_documento="12345678901", valor=1800.0,
            competencia="2026-11", data_prestacao="2026-11-05",
            incluir_ibscbs=True, ibscbs_ind_dest="0",
            ibscbs_imovel_cmun="4113700", ibscbs_imovel_vtotoper=1800.0,
            ibscbs_unidades_imobiliarias=[{
                "inscimobfisc": "IPTU-0001", "cib": "",
                "endereco": {"cep": "86010000", "logradouro": "Rua das Flores", "numero": "100", "bairro": "Centro"},
                "ajustes": [{"tipo": "04", "descricao": "", "valor": 600.0}],
            }],
            ibscbs_cst="200", ibscbs_cclasstrib="200001",
        )
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao_residencial(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=1)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<tpAjusteBCLocImoveis>04</tpAjusteBCLocImoveis>", xml)
        self.assertIn("<vAjusteBCLocImoveis>600.00</vAjusteBCLocImoveis>", xml)
        self.assertNotIn("<cCIB>", xml)  # sem CIB neste caso (usa endereço)
        self.assertIn("<CST>200</CST>", xml)
        self.assertIn("<cClassTrib>200001</cClassTrib>", xml)
        self.assertIn("<indDest>0</indDest>", xml)

    def test_unidade_com_cib(self):
        lanc = Lancamento(
            tomador_nome="Joise", tomador_documento="12345678901", valor=1800.0,
            competencia="2026-11", data_prestacao="2026-11-05",
            incluir_ibscbs=True, ibscbs_imovel_cmun="4113700", ibscbs_imovel_vtotoper=1800.0,
            ibscbs_unidades_imobiliarias=[{"cib": "12345678", "endereco": {}, "ajustes": []}],
            ibscbs_cst="200", ibscbs_cclasstrib="200001",
        )
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao_residencial(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=2)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<cCIB>12345678</cCIB>", xml)

    def test_unidade_incompleta_e_omitida(self):
        """Sem CIB e sem endereço válido: a unidade não entra no XML (evita grupo quebrado)."""
        lanc = Lancamento(
            tomador_nome="Joise", tomador_documento="12345678901", valor=1800.0,
            competencia="2026-11", data_prestacao="2026-11-05",
            incluir_ibscbs=True, ibscbs_imovel_cmun="4113700", ibscbs_imovel_vtotoper=1800.0,
            ibscbs_unidades_imobiliarias=[{"cib": "", "endereco": {}, "ajustes": []}],
            ibscbs_cst="200", ibscbs_cclasstrib="200001",
        )
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao_residencial(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=3)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertNotIn("<gUnidImob>", xml)


class SemImovelNemBensMoveis(unittest.TestCase):
    def test_nota_simples_so_com_cst_e_cclasstrib(self):
        lanc = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=500.0,
                           competencia="2026-11", data_prestacao="2026-11-05",
                           incluir_ibscbs=True, ibscbs_cst="000", ibscbs_cclasstrib="000001")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao_residencial(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=4)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertNotIn("<imovel>", xml)
        self.assertNotIn("<bensMoveis>", xml)

    def test_sem_incluir_ibscbs_omite_o_grupo_inteiro(self):
        lanc = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=500.0,
                           competencia="2026-11", data_prestacao="2026-11-05", incluir_ibscbs=False)
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao_residencial(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=5)
        self.assertNotIn("<IBSCBS>", xml)


class BensMoveis(unittest.TestCase):
    def test_bem_movel_objeto_de_locacao(self):
        lanc = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=900.0,
                           competencia="2026-11", data_prestacao="2026-11-05",
                           incluir_ibscbs=True, ibscbs_cst="000", ibscbs_cclasstrib="000001",
                           ibscbs_bens_moveis=[{"ncm": "87032310", "descricao": "Automóvel de passeio", "quantidade": 1}])
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao_residencial(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=6)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<cNCMBemMovel>87032310</cNCMBemMovel>", xml)
        self.assertIn("<qtdNCMBemMovel>1</qtdNCMBemMovel>", xml)


class DestinatarioDiferenteDoTomador(unittest.TestCase):
    def test_ind_dest_1_com_grupo_dest(self):
        lanc = Lancamento(
            tomador_nome="Empresa Intermediária", tomador_documento="12345678000195", valor=1000.0,
            competencia="2026-11", data_prestacao="2026-11-05",
            incluir_ibscbs=True, ibscbs_ind_dest="1",
            ibscbs_dest_documento="98765432100", ibscbs_dest_nome="Pessoa Física Destinatária",
            ibscbs_cst="000", ibscbs_cclasstrib="000001",
        )
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao_residencial(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=7)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<indDest>1</indDest>", xml)
        self.assertIn("<xNome>Pessoa Física Destinatária</xNome>", xml)

    def test_sem_nome_do_destinatario_omite_o_grupo_dest(self):
        """`dest/xNome` é obrigatório no XSD quando o grupo entra — sem nome, melhor omitir o
        grupo inteiro (indDest=1 sozinho é válido) do que montar um `dest` quebrado."""
        lanc = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=500.0,
                           competencia="2026-11", data_prestacao="2026-11-05",
                           incluir_ibscbs=True, ibscbs_ind_dest="1",
                           ibscbs_cst="000", ibscbs_cclasstrib="000001")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao_residencial(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=8)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertNotIn("<dest>", xml)


class TributacaoRegularEDiferimento(unittest.TestCase):
    def test_gtribregular_e_gdif(self):
        lanc = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=500.0,
                           competencia="2026-11", data_prestacao="2026-11-05",
                           incluir_ibscbs=True, ibscbs_cst="000", ibscbs_cclasstrib="000001",
                           ibscbs_cst_reg="000", ibscbs_cclasstrib_reg="000002",
                           ibscbs_p_dif_uf=10.0, ibscbs_p_dif_mun=10.0, ibscbs_p_dif_cbs=10.0,
                           ibscbs_c_cred_pres="01")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao_residencial(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=9)
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<cClassTribReg>000002</cClassTribReg>", xml)
        self.assertIn("<pDifUF>10.00</pDifUF>", xml)
        self.assertIn("<cCredPres>01</cCredPres>", xml)


class ValidacaoDoLancamento(unittest.TestCase):
    def test_incluir_sem_cst_nem_cclasstrib_da_erro(self):
        lanc = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=500.0,
                           competencia="2026-11", incluir_ibscbs=True)
        erros = lanc.validar()
        self.assertIn("IBS/CBS: falta o CST", erros)
        self.assertIn("IBS/CBS: falta o cClassTrib", erros)

    def test_sem_incluir_nao_exige_nada(self):
        lanc = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=500.0,
                           competencia="2026-11", incluir_ibscbs=False)
        self.assertEqual(lanc.validar(), [])


if __name__ == "__main__":
    unittest.main()
