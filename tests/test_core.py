import datetime as dt
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from adge_nf import core
from fixtures import SessaoFalsa, evento_cancelamento, item, xml_nfse

CNPJ = "11222333000181"
NOME = "EMPRESA EXEMPLO LTDA"


def c(n):
    return str(n) * 50


class Nomes(unittest.TestCase):
    def test_padrao_adge(self):
        d = core.parse_documento(xml_nfse(c(1), emit_nome="PRESTADOR EXEMPLO LTDA", toma_nome="CLIENTE EXEMPLO LTDA",
                                          valor="1618.00", dh="2026-09-01T19:28:27-03:00"))
        self.assertEqual(core.nome_xml("servico_prestado", d),
                         "NOTA FISCAL DE SERVIÇO PRESTADO - PRESTADOR EXEMPLO LTDA para CLIENTE EXEMPLO LTDA em 01-09-2026 no valor de R$1.618,00.xml")
        self.assertTrue(core.nome_xml("servico_tomado", d).startswith("NOTA FISCAL DE SERVIÇO TOMADO - "))

    def test_prefixo_personalizado_aluguel(self):
        d = core.parse_documento(xml_nfse(c(1)))
        n = core.nome_xml("servico_prestado", d, {"servico_prestado": "NOTA FISCAL DE SERVIÇO PRESTADO DE ALUGUEL"})
        self.assertTrue(n.startswith("NOTA FISCAL DE SERVIÇO PRESTADO DE ALUGUEL - "))

    def test_nome_longo_nao_corta_palavra_nem_o_proprio_nome(self):
        d = core.parse_documento(xml_nfse(c(1), emit_nome="FORNECEDOR EXEMPLO DE SERVICOS MEDICOS LTDA " + "X" * 0,
                                          toma_nome=NOME, valor="861.98", dh="2026-09-01T10:00:00-03:00"))
        n = core.nome_xml("servico_tomado", d)
        self.assertIn(NOME, n)  # nome completo da Exemplo preservado (antes saía "...DO TRABALHO LT")
        self.assertLessEqual(len(n), core.LIMITE_NOME)

    def test_nome_gigante_corta_em_palavra_inteira(self):
        longo = " ".join(["PALAVRA"] * 40)
        d = core.parse_documento(xml_nfse(c(1), emit_nome=longo, toma_nome=longo))
        n = core.nome_xml("servico_prestado", d, limite=120)
        self.assertLessEqual(len(n), 120)
        for parte in n.split(" - ", 1)[1].split(" para ")[0].split():
            self.assertEqual(parte, "PALAVRA")

    def test_valor_e_data(self):
        self.assertEqual(core.formatar_valor(11472), "R$11.472,00")
        self.assertEqual(core.formatar_valor(570.72), "R$570,72")
        self.assertEqual(core.formatar_data("2026-08-06T13:26:40-03:00"), "06-08-2026")

    def test_unico(self):
        u = set()
        self.assertEqual([core.unico("a.xml", u) for _ in range(3)], ["a.xml", "a (2).xml", "a (3).xml"])


class Adn(unittest.TestCase):
    def test_paginacao_ate_404(self):
        s = SessaoFalsa([(0, [item(1, xml_nfse(c(1))), item(2, xml_nfse(c(2)))]),
                         (2, [item(2, xml_nfse(c(2))), item(3, xml_nfse(c(3)))]), (3, [item(3, "<x/>")])])
        docs = core.baixar_dfe(s, CNPJ, pausa=0, esperar=lambda *_: None)
        self.assertEqual([d["nsu"] for d in docs], [1, 2, 3])
        self.assertEqual(s.chamadas[0][1], {"cnpjConsulta": CNPJ, "lote": "true"})

    def test_certificado_recusado(self):
        class S:
            def get(self, *a, **k):
                return type("R", (), {"status_code": 403, "json": lambda s: {}})()
        with self.assertRaises(core.ErroAdge):
            core.baixar_dfe(S(), CNPJ, esperar=lambda *_: None)

    def test_instabilidade_tem_limite(self):
        class S:
            n = 0
            def get(self, *a, **k):
                S.n += 1
                return type("R", (), {"status_code": 503, "json": lambda s: {}})()
        with self.assertRaises(core.ErroAdge):
            core.baixar_dfe(S(), CNPJ, esperar=lambda *_: None)
        self.assertLess(S.n, 30)

    def test_cancelar(self):
        s = SessaoFalsa([(0, [item(1, xml_nfse(c(1)))])])
        with self.assertRaises(core.Cancelado):
            core.baixar_dfe(s, CNPJ, cancelar=lambda: True)


class Servico(unittest.TestCase):
    def test_codigo_de_tributacao_no_documento(self):
        d = core.parse_documento(xml_nfse(c(1), emit_cnpj=CNPJ, ctrib="070201", xtrib="Execução de obra"))
        self.assertEqual(d["servico_cod"], "070201")
        self.assertEqual(d["servico_desc"], "Execução de obra")
        self.assertEqual(core.parse_documento(xml_nfse(c(2)))["servico_cod"], "")


class Plano(unittest.TestCase):
    def docs(self):
        eu = dict(emit_cnpj=CNPJ, emit_nome=NOME)
        return [
            {"nsu": 1, "xml": xml_nfse(c(1), valor="1000.50", num="1", **eu)},
            {"nsu": 2, "xml": xml_nfse(c(2), valor="2500.00", num="2", **eu)},
            {"nsu": 3, "xml": xml_nfse(c(3), valor="700.00", num="3", **eu)},
            {"nsu": 4, "xml": evento_cancelamento(c(3))},                                    # cancela a 3
            {"nsu": 5, "xml": xml_nfse(c(1), valor="1000.50", num="1", **eu)},               # duplicada
            {"nsu": 6, "xml": xml_nfse(c(6), valor="300.25", toma_cnpj=CNPJ, toma_nome=NOME, num="6")},  # tomada
            {"nsu": 7, "xml": xml_nfse(c(7), valor="50.00", dh="2026-08-31T23:00:00-03:00", num="7", **eu)},  # agosto
            {"nsu": 8, "xml": xml_nfse(c(8), valor="10.00", num="8")},                       # de terceiros
            {"nsu": 9, "xml": xml_nfse(c(9), valor="5.00", dh="2026-09-30T23:59:00-03:00", num="9", **eu)},  # último dia
        ]

    def test_totais_periodo_cancelamento_duplicada(self):
        arqs, resumo, avisos = core.montar_plano(self.docs(), CNPJ, 2026, 9, {"prestado", "tomado"})
        self.assertEqual(resumo["servico_prestado"], {"qtd": 3, "canceladas": 1, "valor": 3505.5, "liquido": 3505.5, "iss": 0.0})
        self.assertEqual(resumo["servico_tomado"]["qtd"], 1)
        self.assertEqual(len(arqs), 4)
        self.assertEqual(len(avisos), 1)
        self.assertEqual(len({a["nome"] for a in arqs}), 4)

    def test_filtro_de_tipo(self):
        arqs, resumo, _ = core.montar_plano(self.docs(), CNPJ, 2026, 9, {"prestado"})
        self.assertEqual(len(arqs), 3)
        self.assertNotIn("servico_tomado", resumo)
        arqs, resumo, _ = core.montar_plano(self.docs(), CNPJ, 2026, 9, {"tomado"})
        self.assertEqual(len(arqs), 1)

    def test_tipo_sem_notas_aparece_zerado(self):
        _, resumo, _ = core.montar_plano([], CNPJ, 2026, 9, {"prestado", "tomado"})
        self.assertEqual(resumo["servico_prestado"]["valor"], 0.0)

    def test_limites_do_mes(self):
        self.assertEqual(core.limites_mes(2024, 2)[1].day, 29)
        self.assertEqual(core.limites_mes(2026, 2)[1].day, 28)
        self.assertEqual(core.limites_mes(2026, 12)[1], dt.date(2026, 12, 31))
        self.assertEqual(core.limites_mes(2026, 9)[1].day, 30)


class Pastas(unittest.TestCase):
    def test_padrao_adge_e_aproximada(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            (t / "cli1/Departamento_Fiscal/notas fiscais/2026/08-Agosto").mkdir(parents=True)
            (t / "cli2/departamento fiscal").mkdir(parents=True)
            (t / "cli3/Atos").mkdir(parents=True)
            d1, tr1 = core.resolver_destino(t / "cli1", "adge", 2026, 8, False)
            self.assertEqual([n for n, _ in tr1], ["Departamento_Fiscal", "notas fiscais", "2026", "08-Agosto"])
            self.assertFalse(any(novo for _, novo in tr1))
            d2, _ = core.resolver_destino(t / "cli2", "adge", 2026, 3, True)
            self.assertEqual(d2.name, "03-Marco")
            self.assertTrue(d2.is_dir())
            with self.assertRaises(core.ErroAdge):
                core.resolver_destino(t / "cli3", "adge", 2026, 9, False)
            self.assertFalse((t / "cli3/Departamento Fiscal").exists())  # nunca cria o Departamento Fiscal

    def test_outras_estruturas(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            d, _ = core.resolver_destino(t, "ano_mes", 2026, 9, True)
            self.assertEqual(d, t / "2026" / "09-Setembro")
            self.assertEqual(core.resolver_destino(t, "direto", 2026, 9, True)[0], t)
            with self.assertRaises(core.ErroAdge):
                core.resolver_destino(t / "nao-existe", "direto", 2026, 9, False)

    def test_gravar_nao_sobrescreve(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            self.assertEqual(core.gravar(t, "a.xml", "<x/>"), ("a.xml", "gravado"))
            self.assertEqual(core.gravar(t, "a.xml", "<x/>"), ("a.xml", "ja_existia"))
            self.assertEqual(core.gravar(t, "a.xml", "<y/>"), ("a (2).xml", "renomeado"))
            self.assertEqual(core.gravar(t, "a.xml", "<y/>"), ("a (2).xml", "ja_existia"))

    def test_limite_por_caminho(self):
        self.assertEqual(core.limite_para_destino(pathlib.Path("C:/x")), core.LIMITE_NOME)
        self.assertLess(core.limite_para_destino(pathlib.Path("C:/" + "a" * 120)), core.LIMITE_NOME)


class Fluxo(unittest.TestCase):
    def test_buscar_planejar_salvar(self):
        with tempfile.TemporaryDirectory() as t:
            t = pathlib.Path(t)
            (t / "cli").mkdir()
            pfx = t / "c.pfx"
            pfx.write_bytes(b"x")
            emp = {"nome": "Exemplo", "cnpj": "11.222.333/0001-81", "pfx": str(pfx), "destino": str(t / "cli"), "estrutura": "ano_mes",
                   "tipos": {"prestado": True, "tomado": True}, "relatorio": True, "planilha": True, "prefixo_prestado": "", "prefixo_tomado": ""}
            s = SessaoFalsa([(0, [item(1, xml_nfse(c(1), emit_cnpj=CNPJ, emit_nome=NOME, valor="390.00", dh="2026-09-01T10:00:00-03:00")),
                                  item(2, xml_nfse(c(2), toma_cnpj=CNPJ, toma_nome=NOME, valor="100.00", dh="2026-09-02T10:00:00-03:00"))])])
            docs, cnpj = core.buscar(emp, "senha", 2026, 9, sessao=s)
            self.assertEqual(cnpj, CNPJ)
            dest_prev, _ = core.resolver_destino(t / "cli", "ano_mes", 2026, 9, False)
            arqs, resumo, _ = core.planejar(emp, docs, cnpj, 2026, 9, dest_prev)
            self.assertEqual(resumo["servico_prestado"]["valor"], 390.0)
            destino, cont = core.salvar_notas(emp, arqs, resumo, cnpj, 2026, 9)
            nomes = sorted(p.name for p in destino.iterdir())
            self.assertEqual(len(nomes), 4)  # 2 XMLs + relatório + planilha
            self.assertTrue(any(n.startswith("[Sucesso] Relatorio de Organizacao") for n in nomes))
            self.assertEqual(core.salvar_notas(emp, arqs, resumo, cnpj, 2026, 9)[1], {"ja_existia": 2})

    def test_certificado_inexistente(self):
        with self.assertRaises(core.ErroAdge):
            core.buscar({"cnpj": CNPJ, "pfx": "/nao/existe.pfx"}, "x", 2026, 9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
