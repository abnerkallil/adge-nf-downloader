import importlib.util
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.emissao import importador_documento as imp

CABECALHO_FM = ["Casa", "Inquilino", "Valor recebido", "Dúvidas"]
LINHA_FM = ["Rua das Flores, nº1 - Frente",
            "Fulano de Tal\nCPF: 918.042.489-91\nData de nascimento: 21/10/1975\nTelefone: 43 998519062\nEmail: -",
            "1250,00", "-"]
LINHA_FM_SEM_PAGAMENTO = ["Rua das Flores, nº2",
                          "Ciclana da Silva\nCPF: 029.765.792-74\nData de nascimento: 01/01/1997", "0,00",
                          "Não conseguiu pagar"]


class SugestaoDeMapeamento(unittest.TestCase):
    def test_reconhece_colunas_do_modelo_ferreira_maria(self):
        m = imp.sugerir_mapeamento(CABECALHO_FM)
        self.assertEqual(m[0], "endereco")
        self.assertEqual(m[1], "nome_documento")
        self.assertEqual(m[2], "valor")
        self.assertEqual(m[3], "observacoes")

    def test_coluna_sem_palavra_chave_fica_de_fora(self):
        m = imp.sugerir_mapeamento(["Código interno"])
        self.assertNotIn(0, m)


class CampoCompostoNomeDocumento(unittest.TestCase):
    def test_separa_nome_e_cpf_do_mesmo_texto(self):
        mapeamento = {0: "endereco", 1: "nome_documento", 2: "valor", 3: "observacoes"}
        lancamentos, erros = imp.construir_lancamentos(CABECALHO_FM, [LINHA_FM], mapeamento, competencia_padrao="2026-11")
        self.assertEqual(erros, [])
        self.assertEqual(len(lancamentos), 1)
        l = lancamentos[0]
        self.assertEqual(l.tomador_nome, "Fulano de Tal")
        self.assertEqual(l.tomador_documento, "91804248991")
        self.assertEqual(l.endereco, "Rua das Flores, nº1 - Frente")
        self.assertEqual(l.valor, 1250.0)
        self.assertEqual(l.competencia, "2026-11")
        self.assertFalse(l.excluir)

    def test_valor_zero_com_observacao_vira_motivo_de_exclusao(self):
        mapeamento = {0: "endereco", 1: "nome_documento", 2: "valor", 3: "observacoes"}
        lancamentos, _ = imp.construir_lancamentos(CABECALHO_FM, [LINHA_FM_SEM_PAGAMENTO], mapeamento, "2026-11")
        l = lancamentos[0]
        self.assertTrue(l.excluir)
        self.assertEqual(l.motivo_exclusao, "Não conseguiu pagar")
        self.assertEqual(l.tomador_documento, "02976579274")

    def test_linha_em_branco_e_ignorada_sem_virar_erro(self):
        mapeamento = {0: "endereco", 1: "nome_documento", 2: "valor", 3: "observacoes"}
        lancamentos, erros = imp.construir_lancamentos(CABECALHO_FM, [["", "", "", ""]], mapeamento, "2026-11")
        self.assertEqual(lancamentos, [])
        self.assertEqual(erros, [])

    def test_sem_nome_vira_erro_apontando_a_linha(self):
        mapeamento = {0: "endereco", 1: "nome_documento", 2: "valor", 3: "observacoes"}
        linha = ["Rua Y, 1", "", "500,00", "-"]
        lancamentos, erros = imp.construir_lancamentos(CABECALHO_FM, [linha], mapeamento, "2026-11")
        self.assertEqual(lancamentos, [])
        self.assertIn("Linha 2", erros[0])


class ExtracaoDeCsv(unittest.TestCase):
    def test_extrai_cabecalho_e_linhas_de_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "doc.csv"
            caminho.write_text("Inquilino,Valor\nFulano,100\n", encoding="utf-8")
            cabecalho, linhas = imp.extrair_tabela(caminho)
            self.assertEqual(cabecalho, ["Inquilino", "Valor"])
            self.assertEqual(linhas, [["Fulano", "100"]])

    def test_formato_nao_suportado_leva_a_erro_claro(self):
        from adge_nf.core import ErroAdge
        with self.assertRaises(ErroAdge):
            imp.extrair_tabela("documento.docx")


@unittest.skipUnless(importlib.util.find_spec("reportlab"), "reportlab só é usado para montar o PDF de teste")
class ExtracaoDePdfDeVerdade(unittest.TestCase):
    def test_extrai_tabela_de_um_pdf_real(self):
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "teste.pdf"
            doc = SimpleDocTemplate(str(caminho))
            tabela = Table([CABECALHO_FM, LINHA_FM])
            tabela.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
            doc.build([tabela])
            cabecalho, linhas = imp.extrair_tabela(caminho)
            self.assertEqual(cabecalho, CABECALHO_FM)
            self.assertEqual(len(linhas), 1)
            self.assertIn("Fulano de Tal", linhas[0][1])


if __name__ == "__main__":
    unittest.main()
