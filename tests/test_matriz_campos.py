"""Confere o XML real da DPS contra `matriz_campos.MATRIZ_*` - para cada cenário de prestador
(MEI, Simples, não optante) e tomador (CPF, CNPJ), verifica se cada campo sai ou não conforme a
decisão documentada na matriz. Não repete as validações de XSD (isso já é `test_emissao_dps_xml.py`/
`test_emissao_ibscbs.py`) - o foco aqui é "o campo certo entra/não entra pelo cenário certo"."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.core import ErroAdge
from adge_nf.emissao import config_schema as es
from adge_nf.emissao import dps
from adge_nf.emissao.lancamento import Lancamento
from adge_nf.emissao.matriz_campos import MATRIZ_PRESTADOR, MATRIZ_TOMADOR, MATRIZ_TOT_TRIB

EMPRESA = {"nome": "FERREIRA MARIA HOLDING LTDA", "cnpj": "12.345.678/0001-90"}


def empresa_emissao(**over):
    base = es.migrar({"regime": "presumido", "inscricao_municipal": "123456", "telefone": "4334343434",
                       "email": "contato@ferreiramaria.com.br", "municipio": "Londrina", "uf": "PR",
                       "codigo_municipio_ibge": "4113700"})
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
    })
    p.update(over)
    return p


class MatrizPrestadorContraOXmlReal(unittest.TestCase):
    """Cada entrada de `MATRIZ_PRESTADOR` precisa bater com o que `dps.montar_xml` gera (sempre
    tpEmit=1, único fluxo suportado)."""

    def _xml(self, **over_empresa_emissao):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(**over_empresa_emissao), perfil_locacao(), None, lanc)
        return dps.montar_xml(campos)

    def test_cpf_ou_cnpj_sempre_sai(self):
        self.assertEqual(MATRIZ_PRESTADOR["CPF ou CNPJ"]["decisao"], "enviar sempre")
        xml = self._xml()
        self.assertRegex(xml, r"<prest><(CNPJ|CPF)>")

    def test_im_so_sai_se_houver_no_cadastro(self):
        self.assertEqual(MATRIZ_PRESTADOR["IM (Inscrição Municipal)"]["decisao"], "enviar se houver no cadastro")
        self.assertIn("<IM>123456</IM>", self._xml())
        self.assertNotIn("<IM>", self._xml(inscricao_municipal=""))

    def test_xnome_nunca_sai(self):
        self.assertEqual(MATRIZ_PRESTADOR["xNome (nome/razão social)"]["decisao"], "nunca enviar")
        xml = self._xml()
        self.assertNotIn("FERREIRA MARIA", xml)

    def test_endereco_nunca_sai(self):
        self.assertEqual(MATRIZ_PRESTADOR["end (endereço)"]["decisao"], "nunca enviar")
        xml = self._xml(endereco={"cep": "86050000", "logradouro": "Av. Teste", "numero": "1", "bairro": "Centro"})
        self.assertNotIn("Av. Teste", xml)
        self.assertNotIn("<prest><CNPJ>12345678000190</CNPJ><IM>123456</IM><end>", xml)

    def test_fone_sai_se_houver_no_cadastro(self):
        self.assertEqual(MATRIZ_PRESTADOR["fone (telefone)"]["decisao"], "enviar se houver no cadastro")
        self.assertIn("<fone>4334343434</fone>", self._xml())
        self.assertNotIn("<fone>", self._xml(telefone=""))

    def test_email_sai_se_houver_no_cadastro(self):
        self.assertEqual(MATRIZ_PRESTADOR["email"]["decisao"], "enviar se houver no cadastro")
        self.assertIn("<email>contato@ferreiramaria.com.br</email>", self._xml())
        self.assertNotIn("<email>", self._xml(email=""))

    def test_regtrib_sempre_sai(self):
        self.assertEqual(MATRIZ_PRESTADOR["regTrib (opSimpNac, regEspTrib)"]["decisao"], "enviar sempre")
        self.assertIn("<regTrib>", self._xml())

    def test_nif_nunca_sai_prestador_so_tem_cpf_ou_cnpj(self):
        # Este app nunca monta NIF/cNaoNIF pro prestador (só CPF/CNPJ) - não tem como testar a
        # ausência "escolhida" porque a opção nem existe no gerador; documentado como garantia de
        # desenho, não comportamento condicional.
        xml = self._xml()
        self.assertNotIn("<prest><NIF>", xml)
        self.assertNotIn("<prest><cNaoNIF>", xml)


class MatrizTomadorContraOXmlReal(unittest.TestCase):
    def test_tomador_cpf(self):
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        xml = dps.montar_xml(campos)
        self.assertIn("<toma><CPF>12345678901</CPF>", xml)
        self.assertIn("<xNome>Fulano de Tal</xNome>", xml)

    def test_tomador_cnpj_com_endereco_completo(self):
        tomador = {"endereco": {"cep": "86010000", "logradouro": "Rua das Flores", "numero": "50",
                                 "bairro": "Centro", "codigo_municipio_ibge": "4113700"}}
        lanc = Lancamento(tomador_nome="Empresa Tomadora LTDA", tomador_documento="98765432000199",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), tomador, lanc)
        xml = dps.montar_xml(campos)
        self.assertIn("<toma><CNPJ>98765432000199</CNPJ>", xml)
        self.assertIn("<xNome>Empresa Tomadora LTDA</xNome>", xml)
        self.assertIn("<xLgr>Rua das Flores</xLgr>", xml)

    def test_tomador_cnpj_sem_endereco_bloqueia_a_emissao(self):
        """E0235: tomador identificado por CNPJ precisa de endereço nacional completo - sem ele,
        bloqueia com erro claro em vez de mandar uma DPS incompleta."""
        lanc = Lancamento(tomador_nome="Empresa Tomadora LTDA", tomador_documento="98765432000199",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        with self.assertRaises(ErroAdge):
            dps.montar_xml(campos)

    def test_tomador_nif_exterior_com_endereco_completo(self):
        """E0242: tomador por NIF exige `toma/end/endExt` - implementado."""
        tomador = {"endereco": {"pais": "US", "codigo_postal": "10001", "cidade": "New York",
                                 "estado_provincia": "NY", "logradouro": "5th Avenue", "numero": "1"}}
        lanc = Lancamento(tomador_nome="Cliente Exterior", tomador_documento="", nif="123456789",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), tomador, lanc)
        xml = dps.montar_xml(campos)
        self.assertIn("<NIF>123456789</NIF>", xml)
        self.assertIn("<cPais>US</cPais>", xml)

    def test_tomador_nif_sem_endereco_exterior_bloqueado(self):
        """Sem o endereço no exterior completo, bloqueia com erro claro."""
        lanc = Lancamento(tomador_nome="Cliente Exterior", tomador_documento="", nif="123456789",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(), None, lanc)
        with self.assertRaises(ErroAdge):
            dps.montar_xml(campos)

    def test_tomador_cpf_com_retencao_de_issqn_exige_endereco(self):
        """E0237: ISSQN retido pelo tomador (tpRetISSQN=2) exige endereço nacional, mesmo com CPF."""
        lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(), perfil_locacao(issqn={"trib_issqn": 1, "tp_ret_issqn": 2}),
                                    None, lanc)
        with self.assertRaises(ErroAdge):
            dps.montar_xml(campos)


class MatrizTotTribContraOXmlReal(unittest.TestCase):
    def _lanc(self):
        return Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                           valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")

    def test_mei_usa_indtottrib(self):
        self.assertEqual(MATRIZ_TOT_TRIB["mei"]["decisao"], "indTotTrib = 0 (fixo)")
        campos = dps.montar_campos(EMPRESA, empresa_emissao(regime="mei"), perfil_locacao(), None, self._lanc())
        xml = dps.montar_xml(campos)
        self.assertIn("<indTotTrib>0</indTotTrib>", xml)
        self.assertNotIn("pTotTrib", xml)

    def test_simples_sem_aliquota_cadastrada_bloqueia(self):
        campos = dps.montar_campos(EMPRESA, empresa_emissao(regime="simples"), perfil_locacao(), None, self._lanc())
        with self.assertRaises(ErroAdge):
            dps.montar_xml(campos)

    def test_simples_usa_ptottribsn_da_aliquota_cadastrada(self):
        campos = dps.montar_campos(
            EMPRESA, empresa_emissao(regime="simples", simples={"aliquota_mes": 0.075}),
            perfil_locacao(), None, self._lanc())
        xml = dps.montar_xml(campos)
        self.assertIn("<pTotTribSN>7.50</pTotTribSN>", xml)
        self.assertNotIn("indTotTrib", xml)

    def test_presumido_usa_ptottrib_com_percentual_configurado(self):
        campos = dps.montar_campos(
            EMPRESA, empresa_emissao(regime="presumido", percentual_tributos_federais=11.33),
            perfil_locacao(), None, self._lanc())
        xml = dps.montar_xml(campos)
        self.assertIn("<pTotTrib><pTotTribFed>11.33</pTotTribFed>", xml)
        self.assertNotIn("indTotTrib", xml)

    def test_real_usa_a_mesma_regra_do_presumido(self):
        campos = dps.montar_campos(
            EMPRESA, empresa_emissao(regime="real", percentual_tributos_federais=20.0),
            perfil_locacao(), None, self._lanc())
        xml = dps.montar_xml(campos)
        self.assertIn("<pTotTrib><pTotTribFed>20.00</pTotTribFed>", xml)


if __name__ == "__main__":
    unittest.main()
