import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.emissao import regras
from adge_nf.emissao.lancamento import Lancamento

TOMADORES = [
    {"id": "t1", "nome": "Aparecida Adriana dos Santos", "documento": "91804248991",
     "endereco_livre": "Rua dos Lírios, nº338 - Frente", "perfil_id": "residencial", "ativo": True},
    {"id": "t2", "nome": "Empresa Exemplo Ltda", "documento": "", "endereco_livre": "Rua das Petúnias, nº 114 - 1 Salão",
     "perfil_id": "nao_residencial", "ativo": True},
    {"id": "t3", "nome": "Inativo Antigo", "documento": "11111111111", "endereco_livre": "", "perfil_id": "residencial",
     "ativo": False},
]
EMPRESA_EMISSAO = {"tomadores": TOMADORES}


class CasamentoPorDocumento(unittest.TestCase):
    def test_casa_por_documento_mesmo_com_pontuacao_diferente(self):
        l = Lancamento(tomador_nome="outro nome qualquer", tomador_documento="918.042.489-91")
        self.assertEqual(regras.casar_tomador(l, EMPRESA_EMISSAO)["id"], "t1")

    def test_tomador_inativo_nao_casa(self):
        l = Lancamento(tomador_nome="x", tomador_documento="11111111111")
        self.assertIsNone(regras.casar_tomador(l, EMPRESA_EMISSAO))


class CasamentoPorNomeOuEndereco(unittest.TestCase):
    def test_sem_documento_casa_por_nome_normalizado(self):
        l = Lancamento(tomador_nome="APARECIDA ADRIANA DOS SANTOS", tomador_documento="")
        self.assertEqual(regras.casar_tomador(l, EMPRESA_EMISSAO)["id"], "t1")

    def test_sem_nome_nem_documento_casa_por_endereco(self):
        l = Lancamento(tomador_nome="Alguém Novo", tomador_documento="", endereco="Rua das Petúnias, nº 114 - 1 Salão")
        self.assertEqual(regras.casar_tomador(l, EMPRESA_EMISSAO)["id"], "t2")

    def test_sem_nenhum_criterio_nao_casa(self):
        l = Lancamento(tomador_nome="Desconhecido", tomador_documento="22222222222", endereco="Rua Nova, 1")
        self.assertIsNone(regras.casar_tomador(l, EMPRESA_EMISSAO))

    def test_documento_tem_prioridade_sobre_nome(self):
        # nome bate com t1, mas documento bate (diferente) com outro cadastro
        tomadores = TOMADORES + [{"id": "t4", "nome": "Aparecida Adriana dos Santos", "documento": "99999999999",
                                  "endereco_livre": "", "perfil_id": "outro", "ativo": True}]
        l = Lancamento(tomador_nome="Aparecida Adriana dos Santos", tomador_documento="99999999999")
        self.assertEqual(regras.casar_tomador(l, {"tomadores": tomadores})["id"], "t4")


class NovoRegistroDeTomador(unittest.TestCase):
    def test_tomador_de_lancamento_monta_registro_pronto_para_salvar(self):
        l = Lancamento(tomador_nome=" Fulano ", tomador_documento="12345678901", endereco=" Rua X, 1 ")
        t = regras.tomador_de_lancamento(l, perfil_id="residencial")
        self.assertEqual(t["nome"], "Fulano")
        self.assertEqual(t["endereco_livre"], "Rua X, 1")
        self.assertEqual(t["modo_identificacao"], "endereco")
        self.assertEqual(t["perfil_id"], "residencial")
        self.assertTrue(t["ativo"])
        self.assertTrue(t["id"])

    def test_sem_endereco_usa_modo_documento(self):
        l = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901")
        t = regras.tomador_de_lancamento(l, perfil_id="residencial")
        self.assertEqual(t["modo_identificacao"], "documento")


if __name__ == "__main__":
    unittest.main()
