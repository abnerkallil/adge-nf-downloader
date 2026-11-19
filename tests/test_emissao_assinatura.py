"""Assinatura real da DPS (`assinatura.assinar_dps`): gera um certificado A1 sintético em memória
(nunca um certificado real), assina uma DPS de teste, valida o resultado contra o XSD oficial
(`tests/fixtures/xsd/`) e verifica a assinatura criptograficamente com `signxml.XMLVerifier` — prova
de ponta a ponta, não só que o código roda sem erro."""
import datetime
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "fixtures"))

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from lxml import etree

from adge_nf.core import ErroAdge
from adge_nf.emissao import assinatura
from adge_nf.emissao import config_schema as es
from adge_nf.emissao import dps
from adge_nf.emissao.lancamento import Lancamento
from xsd_schema import esquema_dps

SENHA = "senha-de-teste-123"


def gerar_certificado_sintetico():
    """Certificado A1 autoassinado só para teste — nunca usar fora daqui. Devolve (chave, cert)."""
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EMPRESA TESTE LTDA:12345678000190")])
    agora = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(nome).issuer_name(nome).public_key(chave.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(agora - datetime.timedelta(minutes=5))
            .not_valid_after(agora + datetime.timedelta(days=1))
            .sign(chave, hashes.SHA256()))
    return chave, cert


def escrever_pfx(chave, cert, senha: str) -> str:
    pfx_bytes = pkcs12.serialize_key_and_certificates(
        name=b"teste", key=chave, cert=cert, cas=None,
        encryption_algorithm=serialization.BestAvailableEncryption(senha.encode("utf-8")))
    arq = tempfile.NamedTemporaryFile(suffix=".pfx", delete=False)
    arq.write(pfx_bytes)
    arq.close()
    return arq.name


def xml_dps_de_teste() -> str:
    empresa = {"nome": "FERREIRA MARIA HOLDING LTDA", "cnpj": "12.345.678/0001-90"}
    empresa_emissao = es.migrar({"regime": "presumido", "inscricao_municipal": "123456",
                                  "municipio": "Londrina", "uf": "PR", "codigo_municipio_ibge": "4113700"})
    perfil = es.perfil_padrao("Locação de imóvel")
    perfil.update({
        "ctn": "17.09.01 - Locação de bens móveis", "nbs": "110021000 - Locação residencial",
        "pis_cofins": {"incluir": True, "cst_pis": "01", "cst_cofins": "01",
                        "aliquota_pis": 0.65, "aliquota_cofins": 3.0, "tp_ret_pis_cofins": 0},
        "descricao": {"modo": "fixo", "texto": "Aluguel de imóvel"},
    })
    lanc = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901",
                       valor=1250.0, competencia="2026-11", data_prestacao="2026-11-05")
    campos = dps.montar_campos(empresa, empresa_emissao, perfil, None, lanc)
    return dps.montar_xml(campos)


class AssinaturaDps(unittest.TestCase):
    def setUp(self):
        self.chave, self.cert = gerar_certificado_sintetico()
        self.pfx_path = escrever_pfx(self.chave, self.cert, SENHA)

    def tearDown(self):
        pathlib.Path(self.pfx_path).unlink(missing_ok=True)

    def test_assina_valida_contra_xsd_e_verifica_criptograficamente(self):
        import signxml

        assinado = assinatura.assinar_dps(xml_dps_de_teste(), self.pfx_path, SENHA)
        doc = etree.fromstring(assinado.encode("utf-8"))

        schema = esquema_dps()
        self.assertTrue(schema.validate(doc), msg=str(schema.error_log))

        self.assertIsNotNone(signxml.XMLVerifier().verify(doc, x509_cert=self.cert))

    def test_assinatura_entra_como_ultimo_filho_de_dps_irma_de_infdps(self):
        assinado = assinatura.assinar_dps(xml_dps_de_teste(), self.pfx_path, SENHA)
        doc = etree.fromstring(assinado.encode("utf-8"))
        filhos = [etree.QName(el).localname for el in doc]
        self.assertEqual(filhos, ["infDPS", "Signature"])

    def test_senha_errada_levanta_erro_claro(self):
        with self.assertRaises(ErroAdge):
            assinatura.assinar_dps(xml_dps_de_teste(), self.pfx_path, "senha-errada")

    def test_arquivo_de_certificado_inexistente_levanta_erro_claro(self):
        with self.assertRaises(ErroAdge):
            assinatura.assinar_dps(xml_dps_de_teste(), "/caminho/que/nao/existe.pfx", SENHA)


if __name__ == "__main__":
    unittest.main()
