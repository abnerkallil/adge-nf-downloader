import base64
import datetime as dt
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adge_nf import cfop, core, nfe, nfe_cache, totais  # noqa: E402
from adge_nf.core import ErroAdge  # noqa: E402
from fixtures import (SessaoSefazFalsa, chave_nfe, doc_nfe, soap_dist, soap_evento, xml_evento, xml_nfe, xml_resnfe)  # noqa: E402

EU = "11111111000111"
OUTRO = "33333333000133"
CLI = "22222222000122"


class TestCfop(unittest.TestCase):
    def test_operacoes(self):
        self.assertEqual(cfop.operacao("5102"), "venda")
        self.assertEqual(cfop.operacao("6.101"), "venda")
        self.assertEqual(cfop.operacao("1102"), "compra")
        self.assertEqual(cfop.operacao("2556"), "compra")
        self.assertEqual(cfop.operacao("1202"), "devolucao_venda")
        self.assertEqual(cfop.operacao("5202"), "devolucao_compra")
        for c in ("5949", "5152", "5910", "5915", "1949", ""):
            self.assertEqual(cfop.operacao(c), "outras", c)

    def test_atividade_e_credito(self):
        self.assertEqual(cfop.atividade_da_venda("5101"), "industria")
        self.assertEqual(cfop.atividade_da_venda("5102"), "comercio")
        self.assertEqual(cfop.peso_credito("1102"), (1.0, 1.0))
        self.assertEqual(cfop.peso_credito("1551"), (0.0, 1.0))
        self.assertEqual(cfop.peso_credito("1556"), (0.0, 0.5))


class TestLeitura(unittest.TestCase):
    def test_parse_nfe_e_resumo(self):
        d = nfe.parse_documento(xml_nfe(EU, CLI, [("5102", 600.0), ("5102", 400.0)], num=7, icms=120.0))
        self.assertEqual((d["kind"], d["numero"], d["valor"], d["icms"], d["cfops"]), ("nfe", "7", 1000.0, 120.0, ["5102"]))
        self.assertEqual(d["emitente_simples"], "")
        self.assertEqual(nfe.parse_nfe(xml_nfe(EU, CLI, crt="1"))["emitente_simples"], "3")
        r = nfe.parse_documento(xml_resnfe(OUTRO, 321.5, num=9))
        self.assertEqual((r["kind"], r["valor"], r["numero"]), ("nfe_resumo", 321.5, "9"))
        self.assertTrue(nfe.parse_documento(xml_evento(chave_nfe(OUTRO, 1), "110111"))["cancelamento"])
        self.assertTrue(nfe.parse_documento(xml_evento(chave_nfe(OUTRO, 1), "210210"))["ciencia"])

    def test_classificacao(self):
        self.assertEqual(nfe.classificar_nfe(nfe.parse_nfe(xml_nfe(EU, CLI, [("5102", 10)])), EU), "nfe_saida")
        self.assertEqual(nfe.classificar_nfe(nfe.parse_nfe(xml_nfe(OUTRO, EU, [("5102", 10)])), EU), "nfe_entrada")
        self.assertEqual(nfe.classificar_nfe(nfe.parse_nfe(xml_nfe(EU, CLI, [("5949", 10)])), EU), "nfe_outras")
        self.assertEqual(nfe.classificar_nfe(nfe.parse_nfe(xml_nfe(EU, CLI, [("5202", 10)])), EU), "nfe_devolucao_compra")
        self.assertEqual(nfe.classificar_nfe(nfe.parse_nfe(xml_nfe(EU, CLI, [("1202", 10)])), EU), "nfe_devolucao_venda")
        self.assertIsNone(nfe.classificar_nfe(nfe.parse_nfe(xml_nfe(OUTRO, CLI)), EU))
        d = nfe.parse_nfe(xml_nfe(EU, CLI, [("5101", 900), ("5949", 100)]))
        self.assertEqual(nfe.classificar_nfe(d, EU), "nfe_saida")
        self.assertEqual(d["atividade"], "industria")
        self.assertTrue(d["cat_mista"])


class TestPlano(unittest.TestCase):
    def docs(self):
        canc = xml_nfe(EU, CLI, [("5102", 50)], num=5)
        return [doc_nfe(1, xml_nfe(EU, CLI, [("5102", 1000)], num=1, icms=100)),
                doc_nfe(2, xml_nfe(OUTRO, EU, [("5102", 400)], num=2, icms=40)),
                doc_nfe(3, xml_nfe(EU, CLI, [("5949", 70)], num=3)),
                doc_nfe(4, xml_nfe(EU, CLI, [("5102", 99)], num=4, dh="2026-08-31T10:00:00-03:00")),   # fora do mês
                doc_nfe(5, canc), doc_nfe(6, xml_evento(chave_nfe(EU, 5, "2609"), "110111"), "evento"),
                doc_nfe(7, xml_resnfe(OUTRO, 250.0, num=8), "res")]

    def test_plano_por_categoria(self):
        extras = {}
        arq, res, avisos = nfe.montar_plano_nfe(self.docs(), EU, 2026, 9, extras=extras)
        self.assertEqual(res["nfe_saida"]["qtd"], 1)
        self.assertEqual(res["nfe_saida"]["canceladas"], 1)
        self.assertEqual(res["nfe_saida"]["valor"], 1000.0)
        self.assertEqual(res["nfe_entrada"]["valor"], 400.0)
        self.assertEqual(res["nfe_outras"]["valor"], 70.0)
        self.assertEqual(res["nfe_resumo"]["valor"], 250.0)
        self.assertEqual(len(extras["canceladas"]), 1)
        resumo = [a for a in arq if a["cat"] == "nfe_resumo"][0]
        self.assertTrue(resumo["sem_xml"])
        self.assertEqual(len([a for a in arq if not a.get("sem_xml")]), 3)

    def test_totais_com_selecao(self):
        arq, _, _ = nfe.montar_plano_nfe(self.docs(), EU, 2026, 9)
        padrao = totais.padrao_ativos({a["cat"] for a in arq})
        self.assertNotIn("nfe_resumo", padrao)
        self.assertNotIn("nfe_outras", padrao)
        t = totais.totais(arq, padrao)
        self.assertEqual((t["faturamento"], t["compras"], t["saldo"]), (1000.0, 400.0, 600.0))
        t2 = totais.totais(arq, padrao | {"nfe_resumo"})
        self.assertEqual(t2["compras"], 650.0)
        t3 = totais.totais(arq, padrao | {"nfe_outras"})
        self.assertEqual((t3["faturamento"], t3["compras"]), (1000.0, 400.0))      # outras operações não somam
        a = totais.atividades(arq, padrao | {"nfe_resumo"})
        self.assertEqual((a["receitas"]["comercio"], a["compras"]["mercadorias"], a["icms_debito"], a["icms_credito"]),
                         (1000.0, 650.0, 100.0, 40.0))

    def test_devolucoes_abatem(self):
        docs = [doc_nfe(1, xml_nfe(EU, CLI, [("5102", 1000)], num=1)), doc_nfe(2, xml_nfe(CLI, EU, [("5202", 100)], num=2)),
                doc_nfe(3, xml_nfe(OUTRO, EU, [("5102", 300)], num=3)), doc_nfe(4, xml_nfe(EU, OUTRO, [("5202", 50)], num=4))]
        arq, res, _ = nfe.montar_plano_nfe(docs, EU, 2026, 9)
        self.assertEqual(res["nfe_devolucao_venda"]["valor"], 100.0)
        t = totais.totais(arq, set(res))
        self.assertEqual((t["faturamento"], t["compras"]), (900.0, 250.0))

    def test_pendentes_ciencia(self):
        docs = self.docs() + [doc_nfe(8, xml_resnfe(OUTRO, 10, num=11), "res"), doc_nfe(9, xml_nfe(OUTRO, EU, num=11, dh="2026-09-12T10:00:00-03:00")),
                              doc_nfe(10, xml_resnfe(OUTRO, 10, num=12), "res")]
        pend = nfe.pendentes_ciencia(docs, EU, 2026, 9, enviadas={chave_nfe(OUTRO, 12)})
        self.assertEqual(pend, [chave_nfe(OUTRO, 8)])        # a 11 já veio completa, a 12 já teve ciência


class TestSefaz(unittest.TestCase):
    def test_consulta_varios_lotes_e_bloqueio(self):
        x = xml_nfe(EU, CLI, num=1)
        s = SessaoSefazFalsa([soap_dist("138", [(1, "procNFe_v4.00.xsd", x)], 1, 2),
                              soap_dist("138", [(2, "resNFe_v1.01.xsd", xml_resnfe(OUTRO))], 2, 2)])
        agora = dt.datetime(2026, 10, 1, 10, 0)
        r = nfe.consultar_distribuicao(s, EU, 0, esperar=lambda _: None, agora=lambda: agora)
        self.assertEqual([d["tipo"] for d in r["docs"]], ["proc", "res"])
        self.assertEqual((r["ult_nsu"], r["situacao"]), (2, "novidades"))
        self.assertEqual(r["bloqueado_ate"], agora + dt.timedelta(hours=1))
        self.assertIn("<ultNSU>000000000000000</ultNSU>", s.enviados[0][1])
        self.assertIn("<ultNSU>000000000000001</ultNSU>", s.enviados[1][1])
        self.assertIn(f"<CNPJ>{EU}</CNPJ>", s.enviados[0][1])

    def test_137_e_656(self):
        agora = dt.datetime(2026, 10, 1, 10, 0)
        r = nfe.consultar_distribuicao(SessaoSefazFalsa([soap_dist("137", ult=5, maxi=5)]), EU, 5, agora=lambda: agora)
        self.assertEqual((r["situacao"], r["docs"]), ("sem_novidade", []))
        self.assertIsNotNone(r["bloqueado_ate"])
        r = nfe.consultar_distribuicao(SessaoSefazFalsa([soap_dist("656", motivo="Consumo Indevido")]), EU, 5, agora=lambda: agora)
        self.assertEqual(r["situacao"], "bloqueado")
        with self.assertRaises(ErroAdge):
            nfe.consultar_distribuicao(SessaoSefazFalsa([soap_dist("215", motivo="Falha de schema")]), EU, 0)

    def test_cancelar_e_falha_de_rede(self):
        with self.assertRaises(core.Cancelado):
            nfe.consultar_distribuicao(SessaoSefazFalsa(), EU, 0, cancelar=lambda: True)

        class Cai:
            def post(self, *a, **k):
                raise OSError("sem rede")
        with self.assertRaises(ErroAdge):
            nfe.consultar_distribuicao(Cai(), EU, 0)

    def test_ciencia_so_envia_210210(self):
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding, rsa
            from cryptography.hazmat.primitives.serialization import Encoding
            from cryptography.x509.oid import NameOID
        except ImportError:
            self.skipTest("sem cryptography")
        chave_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TESTE")])
        cert = (x509.CertificateBuilder().subject_name(nome).issuer_name(nome).public_key(chave_priv.public_key()).serial_number(1)
                .not_valid_before(dt.datetime(2026, 1, 1)).not_valid_after(dt.datetime(2030, 1, 1)).sign(chave_priv, hashes.SHA256()))
        ass = {"chave": chave_priv, "certificado_b64": base64.b64encode(cert.public_bytes(Encoding.DER)).decode()}
        chaves = [chave_nfe(OUTRO, n) for n in (1, 2)]
        s = SessaoSefazFalsa([soap_evento({chaves[0]: "135", chaves[1]: "573"})])
        res = nfe.enviar_ciencia(s, EU, chaves, ass)
        self.assertTrue(all(ok for _, _, ok in res.values()))
        corpo = s.enviados[0][1]
        self.assertEqual(corpo.count("<tpEvento>210210</tpEvento>"), 2)
        for proibido in ("210200", "210220", "210240"):
            self.assertNotIn(proibido, corpo)
        # a assinatura confere (digest do infEvento e RSA do SignedInfo), canonicalizando como o verificador faz
        ev = nfe.assinar_evento(EU, chaves[0], "1", ass, dt.datetime(2026, 10, 1, 10, 0, 0))
        inf = ev[ev.index("<infEvento"):ev.index("</infEvento>") + len("</infEvento>")]
        digest = base64.b64encode(hashlib.sha1(nfe._c14n(nfe._com_ns(inf, nfe.NS_NFE))).digest()).decode()
        self.assertIn(f"<DigestValue>{digest}</DigestValue>", ev)
        info = ev[ev.index("<SignedInfo>"):ev.index("</SignedInfo>") + len("</SignedInfo>")]
        valor = base64.b64decode(ev[ev.index("<SignatureValue>") + 16:ev.index("</SignatureValue>")])
        chave_priv.public_key().verify(valor, nfe._c14n(nfe._com_ns(info, "http://www.w3.org/2000/09/xmldsig#")), padding.PKCS1v15(), hashes.SHA1())

    def test_ciencia_recusada(self):
        ass = {"chave": None, "certificado_b64": ""}
        orig = nfe.assinar_evento
        nfe.assinar_evento = lambda *a, **k: "<evento/>"
        try:
            c = chave_nfe(OUTRO, 1)
            res = nfe.enviar_ciencia(SessaoSefazFalsa([soap_evento({c: "494"})]), EU, [c], ass)
            self.assertFalse(res[c][2])
            with self.assertRaises(ErroAdge):
                nfe.enviar_ciencia(SessaoSefazFalsa([soap_evento({}, lote="215")]), EU, [c], ass)
        finally:
            nfe.assinar_evento = orig


class TestHistorico(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.agora = dt.datetime(2026, 10, 1, 10, 0)
        self.emp = {"nome": "Empresa: Teste/LTDA", "cnpj": "11.111.111/0001-11"}
        self.h = nfe_cache.HistoricoNFe(self.emp, base=self.t.name, agora=lambda: self.agora)

    def tearDown(self):
        self.t.cleanup()

    def test_pasta_tem_nome_social(self):
        self.assertIn("Empresa", self.h.pasta.name)
        self.assertTrue(self.h.pasta.name.endswith(EU))
        self.assertTrue(self.h.pasta_padrao)

    def test_salvar_carregar_sem_duplicar(self):
        docs = [doc_nfe(3, xml_nfe(EU, CLI)), doc_nfe(4, xml_resnfe(OUTRO), "res"), {"nsu": 0, "tipo": "proc", "schema": "", "xml": xml_nfe(EU, CLI, num=2)}]
        self.assertEqual(self.h.salvar_docs(docs), 3)
        self.assertEqual(self.h.salvar_docs(docs), 0)
        self.assertEqual(self.h.quantidade(), 3)
        self.assertEqual(sorted(d["tipo"] for d in self.h.carregar_docs()), ["proc", "proc", "res"])

    def test_bloqueio_e_contador(self):
        self.assertFalse(self.h.bloqueado())
        self.h.registrar_consulta(10, 10, self.agora + dt.timedelta(hours=1), (2026, 9))
        h2 = nfe_cache.HistoricoNFe(self.emp, base=self.t.name, agora=lambda: self.agora)     # persistiu em disco
        self.assertTrue(h2.bloqueado())
        self.assertIn("1 h 00 min", h2.texto_bloqueio())
        self.assertEqual(h2.estado["ult_nsu"], 10)
        self.agora += dt.timedelta(hours=1, minutes=1)
        self.assertFalse(h2.bloqueado())
        self.assertEqual(h2.texto_bloqueio(), "Consulta de NF-e liberada.")
        self.assertEqual(h2.periodo_texto(), "Setembro de 2026")

    def test_decisoes(self):
        self.h.salvar_docs([doc_nfe(1, xml_nfe(EU, CLI))])
        self.h.registrar_consulta(1, 1, None, (2026, 9))
        self.h.decidir("pendente")
        self.assertEqual(self.h.quantidade(), 1)                       # fechou sem responder: continua guardado
        outra = tempfile.TemporaryDirectory()
        try:
            self.h.decidir("manter", outra.name)
            self.assertEqual(self.h.quantidade(), 1)
            self.assertFalse(self.h.pasta_padrao)
            self.assertTrue(str(self.h.pasta_docs).startswith(outra.name))
            self.assertEqual(len(self.h.carregar_docs()), 1)
        finally:
            outra.cleanup()
        self.h.decidir("descartar")
        self.assertEqual((self.h.quantidade(), self.h.estado["ult_nsu"]), (0, 0))

    def test_ciencia_marcada(self):
        self.h.marcar_ciencia(["a", "b"])
        self.assertEqual(nfe_cache.HistoricoNFe(self.emp, base=self.t.name).ciencias(), {"a", "b"})


if __name__ == "__main__":
    unittest.main()
