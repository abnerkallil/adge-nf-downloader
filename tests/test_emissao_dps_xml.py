"""Valida de verdade o XML que `dps.montar_xml` gera contra o XSD oficial (`tests/fixtures/xsd/`,
ver README.md ali) — não só a leitura da planilha de leiaute. Casos cobertos: Ferreira Maria
(Lucro Presumido, piloto do fluxo ponta a ponta) e um caso MEI (PIS/COFINS proibido)."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "fixtures"))

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
