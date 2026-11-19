import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.emissao import config_schema as es
from adge_nf.emissao import tomadores_planilha as tp


def _escrever(caminho, linhas):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Tomadores"
    for i, nome in enumerate(tp.COLUNAS, 1):
        ws.cell(1, i, nome)
    for r, linha in enumerate(linhas, 2):
        for i, v in enumerate(linha, 1):
            ws.cell(r, i, v)
    wb.save(caminho)


class GerarModelo(unittest.TestCase):
    def test_gera_as_abas_instrucoes_e_tomadores(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "modelo.xlsx"
            tp.gerar_modelo_xlsx(caminho)
            import openpyxl
            wb = openpyxl.load_workbook(caminho)
            self.assertEqual(wb.sheetnames, ["Instruções", "Tomadores"])
            cabecalho = [c.value for c in next(wb["Tomadores"].iter_rows(min_row=1, max_row=1))]
            self.assertEqual(cabecalho, tp.COLUNAS)

    def test_linha_de_exemplo_importa_sem_erros(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "modelo.xlsx"
            tp.gerar_modelo_xlsx(caminho)
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertEqual(erros, [])
            self.assertEqual(len(tomadores), 1)
            self.assertEqual(tomadores[0]["nome"], "Fulano de Tal")


class ImportarXlsx(unittest.TestCase):
    def test_so_com_nome_e_documento_importa(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            _escrever(caminho, [["Maria", "123.456.789-01", "", "", "", "", "", "", "", "", "", "", "", "", "", ""]])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertEqual(erros, [])
            self.assertEqual(len(tomadores), 1)
            self.assertEqual(tomadores[0]["documento"], "123.456.789-01")
            self.assertTrue(tomadores[0]["ativo"])
            self.assertEqual(tomadores[0]["descricao"], {"modo": "herdar", "texto": ""})

    def test_sem_nome_e_ignorada_com_erro(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            _escrever(caminho, [["", "123.456.789-01"] + [""] * 14])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertEqual(tomadores, [])
            self.assertEqual(len(erros), 1)
            self.assertIn("sem nome", erros[0])

    def test_sem_documento_e_sem_endereco_e_ignorada_com_erro(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            _escrever(caminho, [["Maria", ""] + [""] * 14])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertEqual(tomadores, [])
            self.assertEqual(len(erros), 1)

    def test_identificacao_endereco_sem_endereco_e_ignorada(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            linha = ["Maria", "123.456.789-01", "Documento e endereço completo"] + [""] * 13
            _escrever(caminho, [linha])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertEqual(tomadores, [])
            self.assertEqual(len(erros), 1)
            self.assertIn("endereço completo", erros[0])

    def test_identificacao_endereco_com_endereco_importa(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            linha = ["Maria", "", "Documento e endereço completo", "", "86010000", "Rua das Flores",
                     "100", "", "Centro", "Londrina", "PR", "4113700", "", "", "", ""]
            _escrever(caminho, [linha])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertEqual(erros, [])
            self.assertEqual(len(tomadores), 1)
            self.assertEqual(tomadores[0]["modo_identificacao"], "endereco")
            self.assertEqual(tomadores[0]["endereco"]["logradouro"], "Rua das Flores")

    def test_perfil_encontrado_pelo_nome(self):
        perfil = es.perfil_padrao("Locação residencial")
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            linha = ["Maria", "123.456.789-01", "", "Locação residencial"] + [""] * 12
            _escrever(caminho, [linha])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[perfil])
            self.assertEqual(erros, [])
            self.assertEqual(tomadores[0]["perfil_id"], perfil["id"])

    def test_perfil_nao_encontrado_avisa_mas_importa(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            linha = ["Maria", "123.456.789-01", "", "Perfil Inexistente"] + [""] * 12
            _escrever(caminho, [linha])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertEqual(len(tomadores), 1)
            self.assertIsNone(tomadores[0]["perfil_id"])
            self.assertEqual(len(erros), 1)
            self.assertIn("não encontrado", erros[0])

    def test_ativo_nao_desativa_o_tomador(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            linha = ["Maria", "123.456.789-01"] + [""] * 13 + ["Não"]
            _escrever(caminho, [linha])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertFalse(tomadores[0]["ativo"])

    def test_linhas_em_branco_sao_ignoradas_sem_erro(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            _escrever(caminho, [[""] * 16, ["Maria", "123.456.789-01"] + [""] * 14])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertEqual(erros, [])
            self.assertEqual(len(tomadores), 1)

    def test_planilha_sem_colunas_certas_levanta_erro_claro(self):
        import openpyxl
        from adge_nf.core import ErroAdge
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            wb = openpyxl.Workbook()
            wb.active.cell(1, 1, "Qualquer coisa")
            wb.save(caminho)
            with self.assertRaises(ErroAdge):
                tp.importar_xlsx(caminho, perfis=[])


if __name__ == "__main__":
    unittest.main()
