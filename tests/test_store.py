import datetime as dt
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

from adge_nf import core
from adge_nf.store import Armazenamento, empresa_padrao


class CofreFalso:
    def __init__(self):
        self.d = {}

    def get_password(self, s, u):
        return self.d.get((s, u))

    def set_password(self, s, u, p):
        self.d[(s, u)] = p


def gerar_pfx(caminho, senha="segredo", cn="EMPRESA TESTE LTDA:11222333000181", dias=365):
    chave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    agora = dt.datetime.now(dt.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave.public_key())
            .serial_number(1).not_valid_before(agora - dt.timedelta(days=1)).not_valid_after(agora + dt.timedelta(days=dias))
            .sign(chave, hashes.SHA256()))
    caminho.write_bytes(pkcs12.serialize_key_and_certificates(b"t", chave, cert, None, serialization.BestAvailableEncryption(senha.encode())))


class Certificado(unittest.TestCase):
    def test_le_cnpj_nome_validade(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "c.pfx"
            gerar_pfx(p)
            info = core.ler_certificado(str(p), "segredo")
            self.assertEqual(info["cnpj"], "11222333000181")
            self.assertEqual(info["nome"], "EMPRESA TESTE LTDA")
            self.assertGreater(info["valido_ate"], dt.date.today())

    def test_senha_errada_e_arquivo_ruim(self):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "c.pfx"
            gerar_pfx(p)
            with self.assertRaises(core.ErroAdge):
                core.ler_certificado(str(p), "errada")
            (pathlib.Path(t) / "x.pfx").write_bytes(b"lixo")
            with self.assertRaises(core.ErroAdge):
                core.ler_certificado(str(pathlib.Path(t) / "x.pfx"), "segredo")
            with self.assertRaises(core.ErroAdge):
                core.ler_certificado(str(pathlib.Path(t) / "nao.pfx"), "x")


class Armazenamento_(unittest.TestCase):
    def novo(self, t, kr=None):
        return Armazenamento(pathlib.Path(t), keyring_mod=kr or CofreFalso())

    def test_senha_nunca_em_texto_no_arquivo(self):
        with tempfile.TemporaryDirectory() as t:
            kr = CofreFalso()
            a = self.novo(t, kr)
            e = empresa_padrao(); e["nome"] = "Exemplo"
            a.salvar_empresa(e, "minha-senha-secreta")
            bruto = (pathlib.Path(t) / "empresas.json").read_text(encoding="utf-8")
            self.assertNotIn("minha-senha-secreta", bruto)
            b = self.novo(t, kr)  # reabrir
            self.assertEqual(b.senha_da_empresa(b.empresas[0]), "minha-senha-secreta")

    def test_chave_diferente_nao_abre(self):
        with tempfile.TemporaryDirectory() as t:
            a = self.novo(t)
            e = empresa_padrao(); a.salvar_empresa(e, "x1")
            b = self.novo(t, CofreFalso())  # outro cofre (outro PC/usuário)
            with self.assertRaises(core.ErroAdge):
                b.senha_da_empresa(b.empresas[0])

    def test_manter_e_apagar_senha(self):
        with tempfile.TemporaryDirectory() as t:
            a = self.novo(t)
            e = empresa_padrao(); a.salvar_empresa(e, "abc")
            a.salvar_empresa(a.obter(e["id"]))           # None mantém
            self.assertEqual(a.senha_da_empresa(a.obter(e["id"])), "abc")
            a.salvar_empresa(a.obter(e["id"]), "")       # "" apaga
            self.assertEqual(a.senha_da_empresa(a.obter(e["id"])), "")

    def test_senha_mestra(self):
        with tempfile.TemporaryDirectory() as t:
            kr = CofreFalso()
            a = self.novo(t, kr)
            e = empresa_padrao(); a.salvar_empresa(e, "abc")
            a.trocar_modo("mestra123")
            self.assertEqual(a.modo, "mestra")
            b = self.novo(t, kr)
            self.assertTrue(b.precisa_mestra)
            with self.assertRaises(core.ErroAdge):
                b.abrir("errada")
            with self.assertRaises(core.ErroAdge):
                b.abrir("")
            b.abrir("mestra123")
            self.assertEqual(b.senha_da_empresa(b.empresas[0]), "abc")
            b.trocar_modo(None)                          # volta ao cofre
            c = self.novo(t, kr)
            self.assertFalse(c.precisa_mestra)
            self.assertEqual(c.senha_da_empresa(c.empresas[0]), "abc")

    def test_excluir_e_ordem(self):
        with tempfile.TemporaryDirectory() as t:
            a = self.novo(t)
            for n in ("Zeta", "alfa"):
                e = empresa_padrao(); e["nome"] = n; a.salvar_empresa(e, "")
            self.assertEqual([x["nome"] for x in a.empresas], ["alfa", "Zeta"])
            a.excluir_empresa(a.empresas[0]["id"])
            self.assertEqual(len(a.empresas), 1)

    def test_arquivo_corrompido_nao_derruba(self):
        with tempfile.TemporaryDirectory() as t:
            (pathlib.Path(t) / "empresas.json").write_text("{quebrado")
            a = self.novo(t)
            self.assertEqual(a.empresas, [])
            self.assertTrue((pathlib.Path(t) / "empresas.corrompido.json").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
