import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.emissao import arquivo, historico
from adge_nf.emissao.lancamento import Lancamento

EMPRESA = {"nome": "ADGE SERVIÇOS LTDA", "cnpj": "11.222.333/0001-81", "destino": "", "estrutura": "direto"}


class NomeDoArquivo(unittest.TestCase):
    def test_segue_o_padrao_servico_prestado_do_downloader(self):
        l = Lancamento(tomador_nome="Fulano de Tal", tomador_documento="12345678901", valor=1250.0,
                       competencia="2026-11", data_prestacao="2026-11-05")
        nome = arquivo.nome_xml(EMPRESA, l)
        self.assertTrue(nome.startswith("NOTA FISCAL DE SERVIÇO PRESTADO - ADGE SERVIÇOS LTDA para Fulano de Tal"))
        self.assertIn("05-11-2026", nome)
        self.assertIn("R$1.250,00", nome)

    def test_sem_data_de_prestacao_usa_o_ultimo_dia_da_competencia(self):
        l = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=100.0, competencia="2026-02")
        nome = arquivo.nome_xml(EMPRESA, l)
        self.assertIn("28-02-2026", nome)  # 2026 não é bissexto

    def test_prefixo_personalizado_da_empresa_e_respeitado(self):
        empresa = dict(EMPRESA, prefixo_prestado="NOTA FISCAL DE SERVIÇO PRESTADO DE ALUGUEL")
        l = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=100.0, competencia="2026-11")
        self.assertTrue(arquivo.nome_xml(empresa, l).startswith("NOTA FISCAL DE SERVIÇO PRESTADO DE ALUGUEL - "))


class GravacaoEmDisco(unittest.TestCase):
    def test_grava_na_pasta_do_ano_mes_sem_sobrescrever(self):
        with tempfile.TemporaryDirectory() as tmp:
            empresa = dict(EMPRESA, destino=tmp, estrutura="ano_mes")
            l = Lancamento(tomador_nome="Fulano", tomador_documento="12345678901", valor=100.0, competencia="2026-11")
            caminho, status = arquivo.salvar_xml_emitido(empresa, l, "<NFSe>1</NFSe>")
            self.assertEqual(status, "gravado")
            self.assertTrue(caminho.exists())
            self.assertIn("2026", str(caminho))
            self.assertIn("11-Novembro", str(caminho))
            _, status2 = arquivo.salvar_xml_emitido(empresa, l, "<NFSe>1</NFSe>")
            self.assertEqual(status2, "ja_existia")


class HistoricoDeEmissao(unittest.TestCase):
    def test_registra_e_lista_na_ordem(self):
        with tempfile.TemporaryDirectory() as tmp:
            historico.registrar(tmp, "emp1", {"lancamento_id": "a", "status": "emitida", "valor": 100.0})
            historico.registrar(tmp, "emp1", {"lancamento_id": "b", "status": "pendente", "erro": "timeout"})
            registros = historico.listar(tmp, "emp1")
            self.assertEqual([r["lancamento_id"] for r in registros], ["a", "b"])

    def test_empresas_diferentes_nao_se_misturam(self):
        with tempfile.TemporaryDirectory() as tmp:
            historico.registrar(tmp, "emp1", {"lancamento_id": "a", "status": "emitida"})
            self.assertEqual(historico.listar(tmp, "emp2"), [])

    def test_ja_emitido(self):
        with tempfile.TemporaryDirectory() as tmp:
            historico.registrar(tmp, "emp1", {"lancamento_id": "a", "status": "emitida"})
            self.assertTrue(historico.ja_emitido(tmp, "emp1", "a"))
            self.assertFalse(historico.ja_emitido(tmp, "emp1", "b"))


if __name__ == "__main__":
    unittest.main()
