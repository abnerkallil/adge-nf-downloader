"""A planilha modelo completa (docs/emissao/planilha-modelo/) empacota, por cima do modelo oficial
de `planilha_emissao`, abas de apoio (Instruções/Exemplo) e uma coluna extra "Conferir". Estes
testes garantem que ela nunca diverge das colunas reais do motor e que a aba de exemplo sempre
importa limpa."""
import importlib.util
import pathlib
import sys
import tempfile
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from adge_nf.emissao import planilha_emissao as pe  # noqa: E402

CAMINHO_GERADOR = RAIZ / "docs" / "emissao" / "planilha-modelo" / "gerar_planilha_modelo_completa.py"
_spec = importlib.util.spec_from_file_location("gerar_planilha_modelo_completa", CAMINHO_GERADOR)
gpm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gpm)


class PlanilhaModeloCompleta(unittest.TestCase):
    def test_tem_as_tres_abas(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "modelo.xlsx"
            gpm.gerar(caminho)
            import openpyxl
            wb = openpyxl.load_workbook(caminho)
            self.assertEqual(wb.sheetnames, ["Instruções", "Lançamentos", "Exemplo"])

    def test_aba_lancamentos_tem_exatamente_as_colunas_oficiais_mais_conferir(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "modelo.xlsx"
            gpm.gerar(caminho)
            import openpyxl
            wb = openpyxl.load_workbook(caminho)
            ws = wb["Lançamentos"]
            cabecalho = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
            self.assertEqual(cabecalho, list(pe.COLUNAS) + [gpm.COLUNA_CONFERIR])

    def test_aba_exemplo_importa_sem_erros_pelo_importador_oficial(self):
        with tempfile.TemporaryDirectory() as tmp:
            caminho = pathlib.Path(tmp) / "modelo.xlsx"
            gpm.gerar(caminho)
            import openpyxl
            wb = openpyxl.load_workbook(caminho)
            wb.active = wb.sheetnames.index("Exemplo")
            caminho_exemplo = pathlib.Path(tmp) / "exemplo.xlsx"
            wb.save(caminho_exemplo)
            lancamentos, erros = pe.importar_xlsx(caminho_exemplo)
            self.assertEqual(erros, [])
            self.assertEqual(len(lancamentos), len(gpm.EXEMPLO_LINHAS))

    def test_toda_coluna_oficial_tem_texto_de_ajuda(self):
        faltando = [c for c in pe.COLUNAS if c not in gpm.AJUDA_COLUNAS]
        self.assertEqual(faltando, [], f"Colunas novas do motor sem explicação na aba Instruções: {faltando}")


if __name__ == "__main__":
    unittest.main()
