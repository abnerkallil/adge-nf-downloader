import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.emissao import config_schema as es
from adge_nf.emissao import tomadores_planilha as tp


def _escrever(caminho, linhas: list):
    """`linhas`: lista de dicts {nome_da_coluna: valor}; colunas omitidas ficam em branco.
    Independente de pedir pra robustez contra reordenar/adicionar colunas no motor."""
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Tomadores"
    for i, nome in enumerate(tp.COLUNAS, 1):
        ws.cell(1, i, nome)
    for r, linha in enumerate(linhas, 2):
        for i, nome_col in enumerate(tp.COLUNAS, 1):
            if nome_col in linha:
                ws.cell(r, i, linha[nome_col])
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
            self.assertEqual(tomadores[0]["telefone"], "43999999999")
            self.assertEqual(tomadores[0]["email"], "fulano@exemplo.com.br")


class ImportarXlsx(unittest.TestCase):
    def test_so_com_nome_e_documento_importa(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            _escrever(caminho, [{"Nome": "Maria", "Documento (CPF ou CNPJ)": "123.456.789-01"}])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertEqual(erros, [])
            self.assertEqual(len(tomadores), 1)
            self.assertEqual(tomadores[0]["documento"], "123.456.789-01")
            self.assertTrue(tomadores[0]["ativo"])
            self.assertEqual(tomadores[0]["telefone"], "")
            self.assertEqual(tomadores[0]["email"], "")
            self.assertEqual(tomadores[0]["descricao"], {"modo": "herdar", "texto": ""})

    def test_telefone_e_email_importados(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            _escrever(caminho, [{"Nome": "Maria", "Documento (CPF ou CNPJ)": "123.456.789-01",
                                 "Telefone (opcional)": "(43) 99999-9999", "E-mail (opcional)": "maria@exemplo.com"}])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertEqual(erros, [])
            self.assertEqual(tomadores[0]["telefone"], "43999999999")
            self.assertEqual(tomadores[0]["email"], "maria@exemplo.com")

    def test_sem_nome_e_ignorada_com_erro(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            _escrever(caminho, [{"Documento (CPF ou CNPJ)": "123.456.789-01"}])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertEqual(tomadores, [])
            self.assertEqual(len(erros), 1)
            self.assertIn("sem nome", erros[0])

    def test_sem_documento_e_sem_endereco_e_ignorada_com_erro(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            _escrever(caminho, [{"Nome": "Maria"}])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertEqual(tomadores, [])
            self.assertEqual(len(erros), 1)

    def test_identificacao_endereco_sem_endereco_e_ignorada(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            _escrever(caminho, [{"Nome": "Maria", "Documento (CPF ou CNPJ)": "123.456.789-01",
                                 "Identificação na nota": "Documento e endereço completo"}])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertEqual(tomadores, [])
            self.assertEqual(len(erros), 1)
            self.assertIn("endereço completo", erros[0])

    def test_identificacao_endereco_com_endereco_importa(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            _escrever(caminho, [{"Nome": "Maria", "Identificação na nota": "Documento e endereço completo",
                                 "CEP": "86010000", "Logradouro": "Rua das Flores", "Número": "100",
                                 "Bairro": "Centro", "Município": "Londrina", "UF": "PR",
                                 "Código IBGE do município": "4113700"}])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertEqual(erros, [])
            self.assertEqual(len(tomadores), 1)
            self.assertEqual(tomadores[0]["modo_identificacao"], "endereco")
            self.assertEqual(tomadores[0]["endereco"]["logradouro"], "Rua das Flores")

    def test_perfil_encontrado_pelo_nome(self):
        perfil = es.perfil_padrao("Locação residencial")
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            _escrever(caminho, [{"Nome": "Maria", "Documento (CPF ou CNPJ)": "123.456.789-01",
                                 "Perfil de serviço (nome, opcional)": "Locação residencial"}])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[perfil])
            self.assertEqual(erros, [])
            self.assertEqual(tomadores[0]["perfil_id"], perfil["id"])

    def test_perfil_nao_encontrado_avisa_mas_importa(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            _escrever(caminho, [{"Nome": "Maria", "Documento (CPF ou CNPJ)": "123.456.789-01",
                                 "Perfil de serviço (nome, opcional)": "Perfil Inexistente"}])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertEqual(len(tomadores), 1)
            self.assertIsNone(tomadores[0]["perfil_id"])
            self.assertEqual(len(erros), 1)
            self.assertIn("não encontrado", erros[0])

    def test_ativo_nao_desativa_o_tomador(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            _escrever(caminho, [{"Nome": "Maria", "Documento (CPF ou CNPJ)": "123.456.789-01",
                                 "Ativo (Sim/Não)": "Não"}])
            tomadores, erros = tp.importar_xlsx(caminho, perfis=[])
            self.assertFalse(tomadores[0]["ativo"])

    def test_linhas_em_branco_sao_ignoradas_sem_erro(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "t.xlsx"
            _escrever(caminho, [{}, {"Nome": "Maria", "Documento (CPF ou CNPJ)": "123.456.789-01"}])
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
