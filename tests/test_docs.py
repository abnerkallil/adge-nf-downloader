import pathlib
import re
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from adge_nf import VERSAO, atualizacao as A, itens

PASTA = RAIZ / "docs" / "atualizacoes"
RELATORIOS = sorted(PASTA.glob("v*.md"))


class Catalogo(unittest.TestCase):
    def test_codigos_validos_e_nomes_unicos(self):
        for c in itens.CATALOGO:
            self.assertRegex(c, itens.PADRAO)
        self.assertEqual(len(set(itens.CATALOGO.values())), len(itens.CATALOGO))

    def test_formatar(self):
        self.assertEqual(itens.formatar("ITEM-10"), "Informações avançadas (ITEM-10)")

    def test_tabela_do_readme_tem_todos_os_codigos(self):
        txt = (PASTA / "README.md").read_text(encoding="utf-8")
        for c, n in itens.CATALOGO.items():
            self.assertIn(f"| {c} | {n} |", txt)


class Relatorios(unittest.TestCase):
    def test_existe_relatorio_da_versao_atual(self):
        self.assertTrue((PASTA / f"v{VERSAO}.md").exists(), f"falta docs/atualizacoes/v{VERSAO}.md")

    def test_cada_relatorio_tem_resumo_valido_e_detalhes(self):
        self.assertTrue(RELATORIOS)
        for arq in RELATORIOS:
            md = arq.read_text(encoding="utf-8")
            lista = A.extrair_itens(md)
            self.assertTrue(lista, f"{arq.name}: sem itens no Resumo")
            linhas = [l for l in md.split("## Resumo")[1].split("## Detalhes")[0].splitlines() if l.strip().startswith("-")]
            self.assertEqual(len(lista), len(linhas), f"{arq.name}: linha do Resumo fora do formato")
            for it in lista:
                self.assertIn(it["codigo"], itens.CATALOGO, f"{arq.name}: {it['codigo']} não existe no catálogo")
                self.assertEqual(it["nome"], itens.nome(it["codigo"]), f"{arq.name}: nome diferente do catálogo")
                self.assertIn(f"### {itens.formatar(it['codigo'])}", md, f"{arq.name}: falta detalhe de {it['codigo']}")


class Extracao(unittest.TestCase):
    def test_extrai_tipos_e_ignora_o_resto(self):
        md = ("# V\n## Resumo\n- [NOVO] Planilha Excel (ITEM-09): gera xlsx.\n* [Correção] Saldo líquido (ITEM-05) - ajuste\n"
              "- linha solta\n- [XPTO] Coisa (ITEM-01): não vale\n## Detalhes\n- [NOVO] Fora (ITEM-02): não conta\n")
        r = A.extrair_itens(md)
        self.assertEqual([(i["tipo"], i["codigo"]) for i in r], [("NOVO", "ITEM-09"), ("CORRECAO", "ITEM-05")])
        self.assertEqual(r[1]["texto"], "ajuste")

    def test_sem_resumo(self):
        self.assertEqual(A.extrair_itens("só texto"), [])
        self.assertEqual(A.extrair_itens(None), [])

    def test_url_relatorio(self):
        self.assertEqual(A.url_relatorio("a/b", ["v1.3.2"]), "https://github.com/a/b/blob/v1.3.2/docs/atualizacoes/v1.3.2.md")
        self.assertEqual(A.url_relatorio("a/b", ["v1.3.3", "v1.3.2"]), "https://github.com/a/b/tree/v1.3.3/docs/atualizacoes")


if __name__ == "__main__":
    unittest.main()
