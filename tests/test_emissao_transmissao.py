import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.emissao import assinatura, transmissao


class AindaNaoImplementado(unittest.TestCase):
    def test_assinar_dps_levanta_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            assinatura.assinar_dps("<DPS/>", "cert.pfx", "senha")

    def test_enviar_levanta_not_implemented(self):
        with self.assertRaises(NotImplementedError):
            transmissao.enviar("<DPS/>", sessao=None)


class ProducaoRestritaPorPadrao(unittest.TestCase):
    def test_ambiente_ativo_e_o_restrito_enquanto_nao_for_liberado(self):
        self.assertFalse(transmissao.PRODUCAO_REAL_LIBERADA)
        self.assertEqual(transmissao.ambiente_ativo(), transmissao.AMBIENTE_RESTRITO)


if __name__ == "__main__":
    unittest.main()
