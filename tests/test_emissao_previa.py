import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.emissao import previa
from adge_nf.emissao.lancamento import Lancamento

EMPRESA_EMISSAO = {
    "perfis": [
        {"id": "residencial", "nome": "Locação residencial", "ativo": True},
        {"id": "nao_residencial", "nome": "Locação não residencial", "ativo": True},
        {"id": "antigo", "nome": "Descontinuado", "ativo": False},
    ],
    "perfil_padrao_id": "residencial",
    "tomadores": [
        {"id": "t1", "nome": "Aparecida Adriana dos Santos", "documento": "91804248991", "endereco": "",
         "perfil_id": "residencial", "ativo": True},
    ],
}


class Preparo(unittest.TestCase):
    def test_lancamento_com_tomador_cadastrado_fica_pronto_sem_perguntar(self):
        l = Lancamento(tomador_nome="outro nome", tomador_documento="91804248991", valor=1250.0, competencia="2026-11")
        itens = previa.preparar_previa(EMPRESA_EMISSAO, [l])
        self.assertEqual(itens[0].status, previa.PRONTO)
        self.assertEqual(itens[0].perfil_id, "residencial")

    def test_lancamento_sem_tomador_cadastrado_fica_pendente(self):
        l = Lancamento(tomador_nome="Desconhecido", tomador_documento="22222222222", valor=900.0, competencia="2026-11")
        itens = previa.preparar_previa(EMPRESA_EMISSAO, [l])
        self.assertEqual(itens[0].status, previa.PRECISA_PERFIL)
        self.assertIsNone(itens[0].perfil_id)

    def test_lancamento_valor_zero_fica_excluido(self):
        l = Lancamento(tomador_nome="Não pagou", tomador_documento="33333333333", valor=0.0, competencia="2026-11")
        itens = previa.preparar_previa(EMPRESA_EMISSAO, [l])
        self.assertEqual(itens[0].status, previa.EXCLUIDO)


class RespostaNaTela(unittest.TestCase):
    def test_aplicar_perfil_sem_salvar_regra_nao_altera_tomadores(self):
        l = Lancamento(tomador_nome="Novo", tomador_documento="44444444444", valor=800.0, competencia="2026-11")
        item = previa.preparar_previa(EMPRESA_EMISSAO, [l])[0]
        novo = previa.aplicar_perfil(item, "nao_residencial", EMPRESA_EMISSAO, salvar_regra=False)
        self.assertIsNone(novo)
        self.assertEqual(item.status, previa.PRONTO)

    def test_aplicar_perfil_com_salvar_regra_devolve_registro_de_tomador(self):
        l = Lancamento(tomador_nome="Novo", tomador_documento="44444444444", valor=800.0, competencia="2026-11")
        item = previa.preparar_previa(EMPRESA_EMISSAO, [l])[0]
        novo = previa.aplicar_perfil(item, "nao_residencial", EMPRESA_EMISSAO, salvar_regra=True)
        self.assertEqual(novo["documento"], "44444444444")
        self.assertEqual(novo["perfil_id"], "nao_residencial")

    def test_perfil_inativo_nao_conta_como_pronto(self):
        l = Lancamento(tomador_nome="Novo", tomador_documento="55555555555", valor=800.0, competencia="2026-11")
        item = previa.preparar_previa(EMPRESA_EMISSAO, [l])[0]
        previa.aplicar_perfil(item, "antigo", EMPRESA_EMISSAO)
        self.assertEqual(item.status, previa.PRECISA_PERFIL)

    def test_excluir_marca_lancamento_e_item(self):
        l = Lancamento(tomador_nome="Novo", tomador_documento="66666666666", valor=800.0, competencia="2026-11")
        item = previa.preparar_previa(EMPRESA_EMISSAO, [l])[0]
        previa.excluir(item, "Cliente pediu para não emitir")
        self.assertEqual(item.status, previa.EXCLUIDO)
        self.assertTrue(l.excluir)
        self.assertEqual(l.motivo_exclusao, "Cliente pediu para não emitir")


class ProntosParaTransmitir(unittest.TestCase):
    def test_filtra_so_os_prontos(self):
        pronto = Lancamento(tomador_nome="x", tomador_documento="91804248991", valor=100.0, competencia="2026-11")
        pendente = Lancamento(tomador_nome="y", tomador_documento="77777777777", valor=100.0, competencia="2026-11")
        itens = previa.preparar_previa(EMPRESA_EMISSAO, [pronto, pendente])
        self.assertEqual(len(previa.prontos_para_transmitir(itens)), 1)


if __name__ == "__main__":
    unittest.main()
