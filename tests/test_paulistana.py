import base64
import hashlib
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adge_nf import core, paulistana, totais  # noqa: E402
from adge_nf.core import ErroAdge  # noqa: E402
from fixtures import RespSoap, assinador_falso, soap_sp, xml_nfe_sp  # noqa: E402

EU = "11111111000111"
CLI = "22222222000122"
IM = "12345678"


class SessaoSP:
    def __init__(self, respostas):
        self.respostas, self.enviados = list(respostas), []

    def post(self, url, data=None, headers=None, timeout=0):
        self.enviados.append((url, data.decode("utf-8"), headers))
        return RespSoap(self.respostas.pop(0))


class TestAssinatura(unittest.TestCase):
    def test_assinatura_confere(self):
        a = assinador_falso()
        msg = paulistana.pedido_periodo(EU, EU, IM, core.limites_mes(2026, 8)[0], core.limites_mes(2026, 8)[1], 2, a)
        raiz = ET.fromstring(msg)
        ns = {"d": paulistana.DSIG, "n": paulistana.NS}
        self.assertEqual(raiz.find("n:Cabecalho/n:NumeroPagina", ns).text, "2")
        self.assertEqual(raiz.find("n:Cabecalho/n:dtInicio", ns).text, "2026-08-01")
        self.assertEqual(raiz.find("n:Cabecalho/n:Inscricao", ns).text, IM)
        self.assertEqual(raiz.find("n:Cabecalho/n:CPFCNPJ/n:CNPJ", ns).text, EU)
        sig = raiz.find("d:Signature", ns)
        self.assertIsNotNone(sig)
        # digest: documento sem a assinatura, canonicalizado
        sem = msg[:msg.index("<Signature")] + msg[msg.index("</Signature>") + len("</Signature>"):]
        dig = base64.b64encode(hashlib.sha1(ET.canonicalize(sem).encode()).digest()).decode()
        self.assertEqual(sig.find("d:SignedInfo/d:Reference/d:DigestValue", ns).text, dig)
        self.assertEqual(sig.find("d:SignedInfo/d:Reference", ns).get("URI"), "")
        # assinatura RSA-SHA1 do SignedInfo
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        info = msg[msg.index("<SignedInfo>"):msg.index("</SignedInfo>") + len("</SignedInfo>")]
        valor = base64.b64decode(sig.find("d:SignatureValue", ns).text)
        a["cert"].public_key().verify(valor, ET.canonicalize(paulistana._com_ns(info, paulistana.DSIG)).encode(),
                                      padding.PKCS1v15(), hashes.SHA1())

    def test_soap_e_cabecalhos(self):
        s = paulistana.soap("recebidas", "2", "<A/>")
        self.assertIn("<ConsultaNFeRecebidasRequest", s)
        self.assertIn("&lt;A/&gt;", s)
        self.assertEqual(paulistana._cabecalhos("emitidas")["SOAPAction"], '"http://www.prefeitura.sp.gov.br/nfe/ws/consultaNFeEmitidas"')
        self.assertEqual(paulistana._cabecalhos("cnpj")["SOAPAction"], '"http://www.prefeitura.sp.gov.br/nfe/ws/consultaCNPJ"')


class TestConsulta(unittest.TestCase):
    def setUp(self):
        self.a = assinador_falso()

    def test_paginacao_e_lados(self):
        pagina1 = [xml_nfe_sp(IM, n, "2026-08-10", 100.0, CLI, EU) for n in range(1, 51)]
        pagina2 = [xml_nfe_sp(IM, 51, "2026-08-11", 200.0, CLI, EU)]
        emitida = [xml_nfe_sp(IM, 9, "2026-08-12", 500.0, EU, CLI), xml_nfe_sp(IM, 10, "2026-08-13", 70.0, EU, CLI, status="C")]
        s = SessaoSP([soap_sp("ConsultaNFeRecebidas", pagina1), soap_sp("ConsultaNFeRecebidas", pagina2),
                      soap_sp("ConsultaCNPJ", detalhes=[IM]), soap_sp("ConsultaNFeEmitidas", emitida)])
        r = paulistana.consultar(s, EU, 2026, 8, self.a)
        self.assertEqual(r["msgs"], [])
        self.assertEqual(len([d for d in r["docs"] if d["lado"] == "tomado"]), 51)
        self.assertEqual(len([d for d in r["docs"] if d["lado"] == "prestado"]), 2)
        self.assertIn("<NumeroPagina>2</NumeroPagina>", ET.fromstring(s.enviados[1][1]).find(".//{*}MensagemXML").text)
        arq, res, av = paulistana.montar_plano(r["docs"], EU, 2026, 8)
        self.assertEqual(res["paulistana_tomado"]["qtd"], 51)
        self.assertEqual(res["paulistana_prestado"]["qtd"], 1)
        self.assertEqual(res["paulistana_prestado"]["canceladas"], 1)
        self.assertEqual(res["paulistana_prestado"]["valor"], 500.0)
        self.assertEqual(res["paulistana_prestado"]["iss"], 25.0)
        # sem aparecer nos totais por padrão (fonte de conferência)
        self.assertEqual(totais.padrao_ativos(list(res)), set())

    def test_erro_de_um_lado_nao_derruba_o_outro(self):
        s = SessaoSP([soap_sp("ConsultaNFeRecebidas", sucesso=False, erro=("1234", "Certificado sem acesso")),
                      soap_sp("ConsultaCNPJ", detalhes=[IM]),
                      soap_sp("ConsultaNFeEmitidas", [xml_nfe_sp(IM, 9, "2026-08-12", 500.0, EU, CLI)])])
        r = paulistana.consultar(s, EU, 2026, 8, self.a)
        self.assertEqual(len(r["docs"]), 1)
        self.assertEqual(len(r["msgs"]), 1)
        self.assertIn("1234 - Certificado sem acesso", r["msgs"][0])

    def test_tenta_layout_anterior(self):
        s = SessaoSP([soap_sp("ConsultaNFeRecebidas", sucesso=False, erro=("1100", "Versão do schema inválida")),
                      soap_sp("ConsultaNFeRecebidas", [xml_nfe_sp(IM, 1, "2026-08-10", 10.0, CLI, EU)])])
        r = paulistana.consultar(s, EU, 2026, 8, self.a, prestadas=False)
        self.assertEqual(len(r["docs"]), 1)
        self.assertIn("<VersaoSchema>2</VersaoSchema>", s.enviados[0][1])
        self.assertIn("<VersaoSchema>1</VersaoSchema>", s.enviados[1][1])

    def test_fault_vira_mensagem(self):
        fault = ('<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body><soap:Fault>'
                 '<faultstring>Acesso negado</faultstring></soap:Fault></soap:Body></soap:Envelope>')
        r = paulistana.consultar(SessaoSP([fault]), EU, 2026, 8, self.a, prestadas=False)
        self.assertEqual(r["docs"], [])
        self.assertIn("Acesso negado", r["msgs"][0])


class TestPlanoEComparacao(unittest.TestCase):
    def test_periodo_e_comparacao_com_adn(self):
        docs = [{"xml": xml_nfe_sp(IM, 1, "2026-08-10", 100.0, EU, CLI), "lado": "prestado"},
                {"xml": xml_nfe_sp(IM, 2, "2026-08-11", 200.0, EU, CLI), "lado": "prestado"},
                {"xml": xml_nfe_sp(IM, 3, "2026-09-01", 300.0, EU, CLI), "lado": "prestado"}]   # fora do mês
        arq, res, _ = paulistana.montar_plano(docs, EU, 2026, 8)
        self.assertEqual(len(arq), 2)
        self.assertTrue(arq[0]["nome"].startswith("NOTA FISCAL PAULISTANA DE SERVIÇO PRESTADO"))
        adn = [{"cat": "servico_prestado", "doc": {"numero": "1", "tomador_doc": CLI, "emitente_doc": EU, "valor": 100.0}},
               {"cat": "servico_prestado", "doc": {"numero": "7", "tomador_doc": CLI, "emitente_doc": EU, "valor": 50.0}}]
        c = paulistana.comparar(arq + adn)
        self.assertEqual(c["em_ambos"], 1)
        self.assertEqual([a["doc"]["numero"] for a in c["so_adn"]], ["7"])
        self.assertEqual([a["doc"]["numero"] for a in c["so_paulistana"]], ["2"])

    def test_planejar_junta_as_fontes(self):
        emp = {"tipos": {"prestado": True, "tomado": True}}
        docs = [{"xml": xml_nfe_sp(IM, 1, "2026-08-10", 100.0, EU, CLI), "lado": "prestado"}]
        arq, res, _ = core.planejar(emp, [], EU, 2026, 8, docs_paulistana=docs)
        self.assertEqual([a["cat"] for a in arq], ["paulistana_prestado"])
        self.assertEqual(res["paulistana_prestado"]["qtd"], 1)


if __name__ == "__main__":
    unittest.main()
