import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.core import ErroAdge
from adge_nf.emissao.lancamento import Lancamento


class Normalizacao(unittest.TestCase):
    def test_documento_so_digitos(self):
        self.assertEqual(Lancamento(tomador_documento="123.456.789-01").tomador_documento, "12345678901")
        self.assertEqual(Lancamento(tomador_documento="12.345.678/0001-95").tomador_documento, "12345678000195")

    def test_tipo_documento(self):
        self.assertEqual(Lancamento(tomador_documento="12345678901").tipo_documento, "cpf")
        self.assertEqual(Lancamento(tomador_documento="12345678000195").tipo_documento, "cnpj")
        self.assertEqual(Lancamento(tomador_documento="123").tipo_documento, "")

    def test_origem_invalida(self):
        with self.assertRaises(ErroAdge):
            Lancamento(origem="whatsapp")


class ExclusaoAutomatica(unittest.TestCase):
    def test_valor_zero_exclui_com_motivo(self):
        l = Lancamento(tomador_nome="Fulano", valor=0.0)
        self.assertTrue(l.excluir)
        self.assertIn("zerado", l.motivo_exclusao)

    def test_valor_positivo_nao_exclui(self):
        l = Lancamento(tomador_nome="Fulano", valor=100.0)
        self.assertFalse(l.excluir)

    def test_motivo_explicito_do_documento_preservado(self):
        l = Lancamento(tomador_nome="Fulano", valor=0.0, motivo_exclusao="Não conseguiu pagar")
        self.assertTrue(l.excluir)
        self.assertEqual(l.motivo_exclusao, "Não conseguiu pagar")


class Validacao(unittest.TestCase):
    def test_lancamento_completo_sem_erros(self):
        l = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=100.0, competencia="2026-11")
        self.assertEqual(l.validar(), [])

    def test_sem_nome_sem_documento_sem_competencia(self):
        l = Lancamento(valor=100.0, competencia="11/2026")
        erros = l.validar()
        self.assertIn("Tomador sem nome", erros)
        self.assertIn("Documento do tomador inválido (precisa de CPF ou CNPJ)", erros)
        self.assertIn("Competência inválida (use AAAA-MM)", erros)


if __name__ == "__main__":
    unittest.main()
