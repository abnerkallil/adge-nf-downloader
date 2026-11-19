import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.emissao import planilha_emissao as pe


class ModeloEImportacao(unittest.TestCase):
    def test_gerar_e_reimportar_linha_de_exemplo(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "modelo.xlsx"
            pe.gerar_modelo_xlsx(caminho)
            lancamentos, erros = pe.importar_xlsx(caminho)
            self.assertEqual(erros, [])
            self.assertEqual(len(lancamentos), 1)
            l = lancamentos[0]
            self.assertEqual(l.tomador_nome, "Fulano de Tal")
            self.assertEqual(l.tomador_documento, "12345678901")
            self.assertEqual(l.valor, 1250.0)
            self.assertEqual(l.competencia, "2026-11")
            self.assertEqual(l.origem, "planilha")
            self.assertEqual(l.linha_origem, 2)

    def test_importa_varias_linhas_e_ignora_linha_em_branco(self):
        import openpyxl
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "varias.xlsx"
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(pe.COLUNAS)
            ws.append(["Maria", "111.222.333-44", "Rua A, 1", "900,50", "2026-11", "", ""])
            ws.append([None] * 7)
            ws.append(["João", "", "Rua B, 2", 0, "2026-11", "", "Não conseguiu pagar"])
            wb.save(caminho)
            lancamentos, erros = pe.importar_xlsx(caminho)
            self.assertEqual(erros, [])
            self.assertEqual(len(lancamentos), 2)
            self.assertEqual(lancamentos[0].valor, 900.50)
            self.assertTrue(lancamentos[1].excluir)  # valor zero

    def test_linha_sem_nome_vira_erro_e_nao_vira_lancamento(self):
        import openpyxl
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "semnome.xlsx"
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(pe.COLUNAS)
            ws.append(["", "111.222.333-44", "Rua A, 1", 900, "2026-11", "", ""])
            wb.save(caminho)
            lancamentos, erros = pe.importar_xlsx(caminho)
            self.assertEqual(lancamentos, [])
            self.assertEqual(len(erros), 1)
            self.assertIn("Linha 2", erros[0])

    def test_planilha_sem_colunas_obrigatorias(self):
        import openpyxl
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "errada.xlsx"
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(["Coluna Qualquer"])
            wb.save(caminho)
            lancamentos, erros = pe.importar_xlsx(caminho)
            self.assertEqual(lancamentos, [])
            self.assertTrue(erros)

    def test_competencia_aceita_mm_barra_aaaa(self):
        import openpyxl
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "mmaaaa.xlsx"
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(pe.COLUNAS)
            ws.append(["Maria", "111.222.333-44", "", 900, "11/2026", "", ""])
            wb.save(caminho)
            lancamentos, _ = pe.importar_xlsx(caminho)
            self.assertEqual(lancamentos[0].competencia, "2026-11")


if __name__ == "__main__":
    unittest.main()
