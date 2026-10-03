"""v1.7.4: histórico que lê a pasta salva, Paulistana na empresa e log da verificação de atualização."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from adge_nf import atualizacao as A  # noqa: E402
from adge_nf import core, nfe  # noqa: E402
from adge_nf.store import empresa_padrao  # noqa: E402
from fixtures import xml_nfe, xml_nfe_sp, xml_nfse  # noqa: E402

CNPJ, CLI = "11111111000111", "44444444000144"


def preparar(pasta: pathlib.Path):
    (pasta / "1 - nfse.xml").write_text(xml_nfse("1" * 50, valor="1000.00", num="1"), encoding="utf-8")
    (pasta / "2 - nfe.xml").write_text(xml_nfe(CNPJ, CLI, [("5102", 2000.0)], num=1), encoding="utf-8")
    (pasta / "3 - paulistana.xml").write_text(xml_nfe_sp("999", 77, "2026-09-20", 1234.0, CNPJ, CLI), encoding="utf-8")
    (pasta / "4 - estragado.xml").write_text("<NFSe><infNFSe", encoding="utf-8")
    (pasta / "5 - outro.xml").write_text("<qualquer><coisa/></qualquer>", encoding="utf-8")
    (pasta / "relatorio.txt").write_text("não é XML", encoding="utf-8")


class TestPastaSalva(unittest.TestCase):
    def test_classifica_cada_xml_e_ignora_o_resto(self):
        with tempfile.TemporaryDirectory() as t:
            preparar(pathlib.Path(t))
            adn, nf, sp = core.carregar_pasta(t, CNPJ)
        self.assertEqual((len(adn), len(nf), len(sp)), (1, 1, 1))
        self.assertEqual(sp[0]["lado"], "prestado")

    def test_paulistana_nao_vira_nfe(self):
        """A nota da Paulistana também tem <NFe> na raiz, mas não tem infNFe: não pode ser lida como NF-e da SEFAZ."""
        self.assertEqual(nfe.parse_documento(xml_nfe_sp("999", 77, "2026-09-20", 10.0, CNPJ, CLI))["kind"], "desconhecido")
        self.assertEqual(nfe.parse_documento(xml_nfe(CNPJ, CLI))["kind"], "nfe")

    def test_totais_voltam_iguais_aos_da_consulta(self):
        with tempfile.TemporaryDirectory() as t:
            preparar(pathlib.Path(t))
            adn, nf, sp = core.carregar_pasta(t, CNPJ)
        emp = dict(empresa_padrao(), acao="calcular")
        arquivos, resumo, _ = core.planejar(emp, adn, CNPJ, 2026, 9, None, {}, docs_nfe=nf, docs_paulistana=sp)
        self.assertAlmostEqual(resumo["servico_prestado"]["valor"], 1000.0)
        self.assertAlmostEqual(resumo["nfe_saida"]["valor"], 2000.0)
        self.assertAlmostEqual(resumo["paulistana_prestado"]["valor"], 1234.0)
        self.assertEqual(len(arquivos), 3)

    def test_pasta_que_sumiu(self):
        with self.assertRaises(core.ErroAdge) as e:
            core.carregar_pasta("/nao/existe/mesmo", CNPJ)
        self.assertIn("não existe mais", str(e.exception))


class TestEmpresaEHistorico(unittest.TestCase):
    def test_paulistana_comeca_desligada(self):
        self.assertIs(empresa_padrao()["paulistana"], False)

    def test_historico_guarda_a_pasta(self):
        try:
            import tkinter  # noqa: F401
        except ImportError:
            self.skipTest("sem tkinter neste Python (o teste roda no CI e na simulação da tela)")
        from adge_nf.busca import registrar_historico

        class Loja:
            preferencias = {}
            def salvar(self): pass

        loja = Loja()
        emp = {"id": "e1", "nome": "Empresa"}
        registrar_historico(loja, emp, 2026, 9, {"servico_prestado": {"valor": 10.0}}, 3, pasta="C:/clientes/x/2026/09")
        h = loja.preferencias["historico"]
        self.assertEqual(h[0]["pasta"], "C:/clientes/x/2026/09")
        registrar_historico(loja, emp, 2026, 9, {}, 4, faturamento=5.0, pasta="D:/outra")      # mesmo mês: substitui
        self.assertEqual((len(h), h[0]["pasta"], h[0]["notas"]), (1, "D:/outra", 4))


class Resp:
    def __init__(self, code, j=None):
        self.status_code, self._j = code, j

    def json(self):
        return self._j


class SessaoGH:
    def __init__(self, tag, code=200):
        self.tag, self.code = tag, code

    def get(self, url, **k):
        if url.endswith("/releases/latest"):
            return Resp(self.code, {"tag_name": self.tag, "html_url": "https://x", "body": "", "assets": []})
        return Resp(200, [])


class TestLogAtualizacao(unittest.TestCase):
    def rodar(self, tag, versao="1.7.3", code=200):
        etapas = []
        info = A.consultar(SessaoGH(tag, code), repo="a/b", versao=versao, log=etapas.append)
        return info, " | ".join(etapas)

    def test_sem_atualizacao(self):
        info, log = self.rodar("v1.7.3")
        self.assertIsNone(info)
        self.assertLess(log.index("Checando github.com"), log.index("Avaliando"))
        self.assertIn("Nenhuma atualização necessária", log)
        self.assertNotIn("Atualização necessária:", log)

    def test_com_atualizacao_conta_cada_etapa_em_ordem(self):
        info, log = self.rodar("v1.7.4")
        self.assertEqual(info["tag"], "v1.7.4")
        ordem = ["Checando github.com", "Avaliando", "Atualização necessária: v1.7.4", "Lendo as novidades", "Conferindo o instalador", "Pronto"]
        pos = [log.index(x) for x in ordem]
        self.assertEqual(pos, sorted(pos))

    def test_erro_do_github_nao_diz_que_esta_tudo_certo(self):
        with self.assertRaises(core.ErroAdge):
            self.rodar("v9", code=403)


if __name__ == "__main__":
    unittest.main()
