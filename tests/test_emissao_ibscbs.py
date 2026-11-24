"""Valida o grupo `IBSCBS` da DPS (reforma tributária) contra o XSD oficial de PRODUÇÃO vigente
(`tests/fixtures/xsd/`, o mesmo que `test_emissao_dps_xml.py` usa) — o grupo IBSCBS já existe lá
(achado na auditoria de 24/11, que corrigiu `finNFSe`/`gIBSCBS` de lugar; a crença anterior de que
só existia em homologação, `tests/fixtures/xsd_ibscbs/`, estava errada)."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "fixtures"))

from adge_nf.emissao import config_schema as es
from adge_nf.emissao import dps
from adge_nf.emissao.lancamento import Lancamento
from xsd_schema import esquema_dps, esquema_dps_ibscbs

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
    schema = esquema_dps()
    return schema.validate(doc), schema.error_log


def validar_homologacao(xml: str):
    """Só usado pelos testes abaixo marcados `@unittest.skip` - mantido pra quando essa parte do
    leiaute entrar em produção de verdade."""
    from lxml import etree
    doc = etree.fromstring(xml.encode("utf-8"))
    schema = esquema_dps_ibscbs()
    return schema.validate(doc), schema.error_log


_MOTIVO_SKIP_REDUTOR_SOCIAL = (
    "Achado na auditoria de 24/11, rodando o XML real contra o XSD de produção vigente: o grupo "
    "IBSCBS/imovel de produção só aceita um `cCIB` OU um `end` (nada de unidades imobiliárias, "
    "copropriedade, valor total da operação, ajustes de base ou bens móveis - isso só existe no "
    "XSD de produção RESTRITA/homologação, mais novo). Ligar o interruptor \"Operação com bem "
    "imóvel\" numa nota real hoje sai com uma dessas tags extras, que a Sefin Nacional rejeita "
    "('elemento inesperado'). Avisar o Abner: enquanto o XSD de produção não tiver essa parte do "
    "leiaute, esse interruptor não pode ser usado numa emissão de verdade - só CST/cClassTrib "
    "sozinhos (sem o grupo `imovel`) validam."
)


class RedutorSocialLocacaoResidencial(unittest.TestCase):
    """Caso real: locação residencial com redutor social (Art. 260, LC 214/2025) — mesmo cenário
    da Joise/Ferreira Maria já usado no resto do app. Testes aqui ainda validam contra o XSD de
    homologação (onde esse grupo existe de verdade) - ver `_MOTIVO_SKIP_REDUTOR_SOCIAL` sobre por
    que isso não pode ir pra produção ainda."""

    @unittest.skip(_MOTIVO_SKIP_REDUTOR_SOCIAL)
    def test_redutor_social_valido_contra_o_xsd(self):
        lanc = Lancamento(
            tomador_nome="Joise", tomador_documento="12345678901", valor=1800.0,
            competencia="2026-11", data_prestacao="2026-11-05",
            incluir_ibscbs=True, ibscbs_c_ind_op="020101", ibscbs_ind_dest="0",
            ibscbs_imovel_cmun="4113700", ibscbs_imovel_vtotoper=1800.0,
            ibscbs_unidades_imobiliarias=[{
                "inscimobfisc": "IPTU-0001", "cib": "",
                "endereco": {"cep": "86010000", "logradouro": "Rua das Flores", "numero": "100", "bairro": "Centro"},
                "ajustes": [{"tipo": "04", "descricao": "", "valor": 600.0}],
            }],
            ibscbs_cst="200", ibscbs_cclasstrib="200027",  # Art. 261, locação de imóveis, redução de 70%
        )
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao_residencial(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=1)
        valido, erros = validar_homologacao(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<tpAjusteBCLocImoveis>04</tpAjusteBCLocImoveis>", xml)
        self.assertIn("<vAjusteBCLocImoveis>600.00</vAjusteBCLocImoveis>", xml)
        self.assertNotIn("<cCIB>", xml)  # sem CIB neste caso (usa endereço)
        self.assertIn("<CST>200</CST>", xml)
        self.assertIn("<cClassTrib>200027</cClassTrib>", xml)
        self.assertIn("<indDest>0</indDest>", xml)

    @unittest.skip(_MOTIVO_SKIP_REDUTOR_SOCIAL)
    def test_unidade_com_cib(self):
        lanc = Lancamento(
            tomador_nome="Joise", tomador_documento="12345678901", valor=1800.0,
            competencia="2026-11", data_prestacao="2026-11-05",
            incluir_ibscbs=True, ibscbs_c_ind_op="020101", ibscbs_imovel_cmun="4113700", ibscbs_imovel_vtotoper=1800.0,
            ibscbs_unidades_imobiliarias=[{"cib": "12345678", "endereco": {}, "ajustes": []}],
            ibscbs_cst="200", ibscbs_cclasstrib="200027",  # Art. 261, locação de imóveis, redução de 70%
        )
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao_residencial(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=2)
        valido, erros = validar_homologacao(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<cCIB>12345678</cCIB>", xml)

    @unittest.skip(_MOTIVO_SKIP_REDUTOR_SOCIAL)
    def test_unidade_incompleta_e_omitida(self):
        """Sem CIB e sem endereço válido: a unidade não entra no XML (evita grupo quebrado)."""
        lanc = Lancamento(
            tomador_nome="Joise", tomador_documento="12345678901", valor=1800.0,
            competencia="2026-11", data_prestacao="2026-11-05",
            incluir_ibscbs=True, ibscbs_c_ind_op="020101", ibscbs_imovel_cmun="4113700", ibscbs_imovel_vtotoper=1800.0,
            ibscbs_unidades_imobiliarias=[{"cib": "", "endereco": {}, "ajustes": []}],
            ibscbs_cst="200", ibscbs_cclasstrib="200027",  # Art. 261, locação de imóveis, redução de 70%
        )
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao_residencial(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=3)
        valido, erros = validar_homologacao(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertNotIn("<gUnidImob>", xml)


class SemImovelNemBensMoveis(unittest.TestCase):
    def test_nota_simples_so_com_cst_e_cclasstrib(self):
        lanc = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=500.0,
                           competencia="2026-11", data_prestacao="2026-11-05",
                           incluir_ibscbs=True, ibscbs_c_ind_op="020101", ibscbs_cst="000", ibscbs_cclasstrib="000001")
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
    @unittest.skip(_MOTIVO_SKIP_REDUTOR_SOCIAL)
    def test_bem_movel_objeto_de_locacao(self):
        lanc = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=900.0,
                           competencia="2026-11", data_prestacao="2026-11-05",
                           incluir_ibscbs=True, ibscbs_c_ind_op="020101", ibscbs_cst="000", ibscbs_cclasstrib="000001",
                           ibscbs_bens_moveis=[{"ncm": "87032310", "descricao": "Automóvel de passeio", "quantidade": 1}])
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao_residencial(), None, lanc)
        xml = dps.montar_xml(campos, serie="1", numero=6)
        valido, erros = validar_homologacao(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<cNCMBemMovel>87032310</cNCMBemMovel>", xml)
        self.assertIn("<qtdNCMBemMovel>1</qtdNCMBemMovel>", xml)


class DestinatarioDiferenteDoTomador(unittest.TestCase):
    def test_ind_dest_1_com_grupo_dest(self):
        tomador = {"endereco": {"cep": "86010000", "logradouro": "Rua das Flores", "numero": "50",
                                 "bairro": "Centro", "codigo_municipio_ibge": "4113700"}}
        lanc = Lancamento(
            tomador_nome="Empresa Intermediária", tomador_documento="12345678000195", valor=1000.0,
            competencia="2026-11", data_prestacao="2026-11-05",
            incluir_ibscbs=True, ibscbs_c_ind_op="020101", ibscbs_ind_dest="1",
            ibscbs_dest_documento="98765432100", ibscbs_dest_nome="Pessoa Física Destinatária",
            ibscbs_cst="000", ibscbs_cclasstrib="000001",
        )
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao_residencial(), tomador, lanc)
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
                           incluir_ibscbs=True, ibscbs_c_ind_op="020101", ibscbs_ind_dest="1",
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
                           incluir_ibscbs=True, ibscbs_c_ind_op="020101", ibscbs_cst="000", ibscbs_cclasstrib="000001",
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
                           competencia="2026-11", incluir_ibscbs=True, ibscbs_c_ind_op="020101")
        erros = lanc.validar()
        self.assertIn("IBS/CBS: falta o CST", erros)
        self.assertIn("IBS/CBS: falta o cClassTrib", erros)

    def test_sem_incluir_nao_exige_nada(self):
        lanc = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=500.0,
                           competencia="2026-11", incluir_ibscbs=False)
        self.assertEqual(lanc.validar(), [])

    def test_sem_cind_op_da_erro(self):
        lanc = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=500.0,
                           competencia="2026-11", incluir_ibscbs=True,
                           ibscbs_cst="000", ibscbs_cclasstrib="000001")
        self.assertIn("IBS/CBS: falta o código indicador da operação (cIndOp)", lanc.validar())

    def test_operacao_com_bem_imovel_ainda_nao_e_aceita_em_producao(self):
        """O grupo `IBSCBS/imovel` de produção (achado na auditoria de 24/11) só tem CIB/endereço -
        nada de `cMun`/`gLocacao`/`bensMoveis`. Ligar o interruptor "Operação com bem imóvel" na
        tela hoje sempre passa `ibscbs_imovel_cmun`, então isso tem que ser bloqueado aqui."""
        lanc = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=500.0,
                           competencia="2026-11", incluir_ibscbs=True, ibscbs_c_ind_op="020101",
                           ibscbs_cst="200", ibscbs_cclasstrib="200027", ibscbs_imovel_cmun="4113700")
        erros = lanc.validar()
        self.assertTrue(any("redutor social" in e for e in erros), erros)


if __name__ == "__main__":
    unittest.main()
