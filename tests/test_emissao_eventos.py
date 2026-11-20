"""Valida o `<pedRegEvento>` de cancelamento (`eventos.montar_cancelamento_xml`) contra o XSD
oficial de produção restrita/homologação (`tests/fixtures/xsd_ibscbs/pedRegEvento_v1.01.xsd`)."""
import functools
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.core import ErroAdge
from adge_nf.emissao import eventos

XSD_DIR = pathlib.Path(__file__).resolve().parent / "fixtures" / "xsd_ibscbs"
CHAVE_VALIDA = "411370" + "12345678000195".zfill(14) + "0" * 30  # TSChaveNFSe: 6+14+30=50 dígitos


@functools.lru_cache(maxsize=1)
def _esquema_evento():
    from lxml import etree
    return etree.XMLSchema(etree.parse(str(XSD_DIR / "pedRegEvento_v1.01.xsd")))


def validar(xml: str):
    from lxml import etree
    doc = etree.fromstring(xml.encode("utf-8"))
    schema = _esquema_evento()
    return schema.validate(doc), schema.error_log


class MontarCancelamento(unittest.TestCase):
    def test_cancelamento_valido_contra_o_xsd(self):
        xml = eventos.montar_cancelamento_xml(
            CHAVE_VALIDA, documento_autor="12345678000195", motivo_codigo="1",
            motivo_texto="Nota emitida com valor errado por engano.")
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<cMotivo>1</cMotivo>", xml)
        self.assertIn("<xDesc>Cancelamento de NFS-e</xDesc>", xml)
        self.assertIn("<CNPJAutor>12345678000195</CNPJAutor>", xml)

    def test_autor_pessoa_fisica(self):
        xml = eventos.montar_cancelamento_xml(
            CHAVE_VALIDA, documento_autor="123.456.789-01", motivo_codigo="2",
            motivo_texto="Serviço não foi prestado ao tomador.")
        valido, erros = validar(xml)
        self.assertTrue(valido, msg=str(erros))
        self.assertIn("<CPFAutor>12345678901</CPFAutor>", xml)

    def test_motivo_codigo_invalido_levanta_erro(self):
        with self.assertRaises(ErroAdge):
            eventos.montar_cancelamento_xml(CHAVE_VALIDA, "12345678000195", "5", "Motivo qualquer bem explicado aqui.")

    def test_motivo_texto_curto_demais_levanta_erro(self):
        with self.assertRaises(ErroAdge):
            eventos.montar_cancelamento_xml(CHAVE_VALIDA, "12345678000195", "1", "curto")

    def test_documento_invalido_levanta_erro(self):
        with self.assertRaises(ErroAdge):
            eventos.montar_cancelamento_xml(CHAVE_VALIDA, "123", "1", "Motivo qualquer bem explicado aqui.")


if __name__ == "__main__":
    unittest.main()
