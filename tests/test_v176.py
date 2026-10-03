"""v1.7.6: Responsável (CPF/CNPJ), consulta da SEFAZ pelo certificado dele e separação das notas por empresa."""
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from adge_nf import core, nfe, nfe_resp as R  # noqa: E402
from adge_nf.store import Armazenamento  # noqa: E402
from fixtures import (SessaoSefazFalsa, doc_nfe, soap_dist, xml_nfe, xml_resnfe)  # noqa: E402
from test_store import CofreFalso, gerar_pfx  # noqa: E402

EMPRESA = "11222333000181"            # cliente que emite as notas (a empresa consultada no programa)
OUTRA = "37890671000185"              # outro cliente que também citou o responsável
CLI = "44444444000144"
CPF = "52998224725"


class TestDocumento(unittest.TestCase):
    def test_cpf_e_cnpj_validos(self):
        self.assertTrue(R.cpf_valido(CPF))
        self.assertTrue(R.cpf_valido("529.982.247-25"))
        self.assertFalse(R.cpf_valido("52998224724"))
        self.assertFalse(R.cpf_valido("11111111111"))
        self.assertTrue(R.cnpj_valido(EMPRESA))
        self.assertTrue(R.cnpj_valido("11.222.333/0001-81"))
        self.assertFalse(R.cnpj_valido("11222333000182"))
        self.assertFalse(R.cnpj_valido("00000000000000"))

    def test_tipo_e_formatacao(self):
        self.assertEqual((R.tipo_do_documento(CPF), R.tipo_do_documento(EMPRESA), R.tipo_do_documento("123")), ("cpf", "cnpj", ""))
        self.assertEqual(R.formatar_documento(CPF), "529.982.247-25")
        self.assertEqual(R.formatar_documento(EMPRESA), "11.222.333/0001-81")


class TestCertificado(unittest.TestCase):
    def info(self, cn):
        with tempfile.TemporaryDirectory() as t:
            p = pathlib.Path(t) / "c.pfx"
            gerar_pfx(p, "s", cn)
            return core.ler_certificado(str(p), "s")

    def test_e_cpf(self):
        i = self.info(f"FULANO DE TAL:{CPF}")
        self.assertEqual((i["tipo"], i["cpf"], i["cnpj"], i["documento"], i["nome"]), ("cpf", CPF, "", CPF, "FULANO DE TAL"))

    def test_e_cnpj_continua_igual(self):
        i = self.info(f"EMPRESA TESTE LTDA:{EMPRESA}")
        self.assertEqual((i["tipo"], i["cnpj"], i["cpf"], i["nome"]), ("cnpj", EMPRESA, "", "EMPRESA TESTE LTDA"))

    def test_sem_documento_no_certificado(self):
        i = self.info("TESTE SEM NUMERO")
        self.assertEqual((i["tipo"], i["documento"]), ("", ""))
        self.assertIn("e-CPF ou e-CNPJ", R.conferir_certificado(i, CPF))

    def test_conferir_certificado(self):
        cpf, cnpj = self.info(f"FULANO:{CPF}"), self.info(f"EMPRESA:{EMPRESA}")
        self.assertEqual(R.conferir_certificado(cpf, CPF), "")
        self.assertEqual(R.conferir_certificado(cnpj, "11.222.333/0001-81"), "")
        self.assertIn("diferente", R.conferir_certificado(cpf, "11144477735"))
        self.assertIn("é de uma empresa", R.conferir_certificado(cnpj, CPF))
        self.assertIn("é de uma pessoa", R.conferir_certificado(cpf, EMPRESA))
        self.assertIn("outra empresa", R.conferir_certificado(cnpj, OUTRA))
        self.assertIn("não é válido", R.conferir_certificado(cpf, "52998224724"))
        self.assertIn("Informe", R.conferir_certificado(cpf, "123"))

    def test_mesma_raiz_de_cnpj_vale_para_filial(self):
        filial = "11222333000262"          # mesma raiz (8 dígitos) da matriz do certificado
        self.assertTrue(R.cnpj_valido(filial))
        self.assertEqual(R.conferir_certificado(self.info(f"EMPRESA:{EMPRESA}"), filial), "")


class TestConsultaPorCpf(unittest.TestCase):
    def test_xml_usa_a_tag_certa(self):
        self.assertIn(f"<CPF>{CPF}</CPF>", nfe.xml_distribuicao(CPF, 5))
        self.assertNotIn("<CNPJ>", nfe.xml_distribuicao(CPF, 5))
        self.assertIn(f"<CNPJ>{EMPRESA}</CNPJ>", nfe.xml_distribuicao(EMPRESA, 5))
        self.assertIn(f"<CPF>{CPF}</CPF>", nfe.xml_distribuicao("529.982.247-25", 0, "1" * 44))

    def test_consulta_envia_o_cpf_e_le_as_notas(self):
        doc = xml_nfe(EMPRESA, CLI, [("5102", 1000.0)], num=7)
        s = SessaoSefazFalsa([soap_dist("138", [(10, "procNFe_v4.00.xsd", doc)], ult=10, maxi=10)])
        r = nfe.consultar_distribuicao(s, CPF, 9, esperar=lambda _: None)
        self.assertEqual(len(r["docs"]), 1)
        self.assertIn(f"<CPF>{CPF}</CPF>", s.enviados[0][1])
        self.assertIn("<ultNSU>000000000000009</ultNSU>", s.enviados[0][1])


class TestSepararPorEmpresa(unittest.TestCase):
    def docs(self):
        venda = xml_nfe(EMPRESA, CLI, [("5102", 1000.0)], num=1)                      # venda da empresa consultada
        outra = xml_nfe(OUTRA, CLI, [("5102", 7777.0)], num=2)                        # venda de OUTRO cliente (mesmo responsável)
        resumo = xml_resnfe(CLI, 500.0, num=3)                                        # resumo sem dono conhecido
        d = [doc_nfe(1, venda), doc_nfe(2, outra), doc_nfe(3, resumo, "res")]
        for x in d:
            x["fonte"] = "responsavel"
        return d

    def test_so_as_notas_da_empresa_consultada_entram_e_sem_aviso_de_terceiros(self):
        arq, res, avisos = nfe.montar_plano_nfe(self.docs(), EMPRESA, 2026, 9)
        self.assertEqual(res["nfe_saida"]["valor"], 1000.0)
        self.assertEqual([a["cat"] for a in arq], ["nfe_saida"])
        self.assertEqual(avisos, [])                       # o responsável recebe notas de várias empresas: não é aviso
        self.assertNotIn("nfe_resumo", res)

    def test_outra_empresa_do_mesmo_responsavel(self):
        _, res, _ = nfe.montar_plano_nfe(self.docs(), OUTRA, 2026, 9)
        self.assertEqual(res["nfe_saida"]["valor"], 7777.0)

    def test_sem_a_marca_do_responsavel_o_aviso_de_terceiros_continua(self):
        d = self.docs()
        for x in d:
            x.pop("fonte")
        _, _, avisos = nfe.montar_plano_nfe(d, EMPRESA, 2026, 9)
        self.assertTrue(any("não têm o CNPJ da empresa" in a for a in avisos))

    def test_documentos_das_duas_fontes_somam_sem_duplicar_a_mesma_nota(self):
        da_empresa = [doc_nfe(5, xml_nfe(CLI, EMPRESA, [("5102", 300.0)], num=9))]      # compra, pelo certificado da empresa
        venda = self.docs()
        venda_dup = [dict(venda[0], nsu=5)]                                             # a mesma venda chegando de novo (NSU diferente)
        _, res, _ = nfe.montar_plano_nfe(da_empresa + venda + venda_dup, EMPRESA, 2026, 9)
        self.assertEqual((res["nfe_saida"]["valor"], res["nfe_entrada"]["valor"]), (1000.0, 300.0))


class TestEmpresasQueEnviaram(unittest.TestCase):
    def test_agrupa_por_emitente_e_marca_as_cadastradas(self):
        docs = [doc_nfe(1, xml_nfe(EMPRESA, CLI, num=1, dh="2026-09-01T10:00:00-03:00", emit_nome="LR TESTE")),
                doc_nfe(2, xml_nfe(EMPRESA, CLI, num=2, dh="2026-09-20T10:00:00-03:00", emit_nome="LR TESTE")),
                doc_nfe(3, xml_nfe(OUTRA, CLI, num=3, dh="2026-08-05T10:00:00-03:00", emit_nome="OUTRO CLIENTE")),
                doc_nfe(4, xml_resnfe(CLI, 10.0, num=4), "res"),                         # resumo não conta como empresa
                doc_nfe(5, xml_nfe(CLI, "11122233344", num=5))]                         # nota comprada pelo próprio responsável (CPF)
        docs[4]["xml"] = docs[4]["xml"].replace("11122233344", CPF)
        lista = R.empresas_que_enviaram(docs, CPF, [{"cnpj": EMPRESA, "nome": "LR cadastrada"}])
        self.assertEqual([(e["documento"], e["qtd"], e["ultima"], e["cadastrada"]) for e in lista],
                         [(EMPRESA, 2, "2026-09-20", True), (OUTRA, 1, "2026-08-05", False)])
        self.assertEqual(lista[0]["nome"], "LR TESTE")

    def test_sem_notas_explica_o_autxml(self):
        self.assertEqual(R.empresas_que_enviaram([], CPF), [])
        self.assertIn("autXML", R.aviso_sem_autxml(0, 0))
        self.assertEqual(R.aviso_sem_autxml(3, 1), "")


class TestStoreResponsavel(unittest.TestCase):
    def loja(self, t):
        return Armazenamento(pathlib.Path(t), keyring_mod=CofreFalso())

    def resp(self):
        return {"tipo": "cpf", "documento": CPF, "nome": "CONTADOR", "pfx": "x.pfx", "ciente_em": "2026-10-03T10:00:00"}

    def test_salva_cifra_e_le(self):
        with tempfile.TemporaryDirectory() as t:
            s = self.loja(t)
            self.assertIsNone(s.responsavel)
            s.salvar_responsavel(self.resp(), "segredo")
            texto = (pathlib.Path(t) / "empresas.json").read_text(encoding="utf-8")
            self.assertNotIn("segredo", texto)
            self.assertEqual(s.senha_do_responsavel(), "segredo")
            self.assertEqual(s.responsavel["documento"], CPF)

    def test_none_mantem_a_senha_e_vazio_apaga(self):
        with tempfile.TemporaryDirectory() as t:
            s = self.loja(t)
            s.salvar_responsavel(self.resp(), "segredo")
            r = dict(s.responsavel, nome="NOVO NOME")
            s.salvar_responsavel(r)
            self.assertEqual(s.senha_do_responsavel(), "segredo")
            s.salvar_responsavel(dict(r), "")
            self.assertEqual(s.senha_do_responsavel(), "")

    def test_senha_mestra_recifra_a_senha_do_responsavel(self):
        with tempfile.TemporaryDirectory() as t:
            s = self.loja(t)
            s.salvar_responsavel(self.resp(), "segredo")
            antes = s.responsavel["senha_cifrada"]
            s.trocar_modo("mestra123")
            self.assertNotEqual(s.responsavel["senha_cifrada"], antes)
            novo = self.loja(t)
            novo.abrir("mestra123")
            self.assertEqual(novo.senha_do_responsavel(), "segredo")

    def test_excluir_e_apagar_tudo(self):
        with tempfile.TemporaryDirectory() as t:
            s = self.loja(t)
            s.salvar_responsavel(self.resp(), "segredo")
            s.excluir_responsavel()
            self.assertIsNone(s.responsavel)
            s.salvar_responsavel(self.resp(), "segredo")
            s.apagar_tudo()
            self.assertIsNone(s.responsavel)
            self.assertIsNone(self.loja(t).responsavel)


class TestHistoricoDoResponsavel(unittest.TestCase):
    def test_pasta_propria_e_independente_da_empresa(self):
        from adge_nf.nfe_cache import HistoricoNFe
        with tempfile.TemporaryDirectory() as t:
            resp = {"nome": "CONTADOR TESTE", "documento": CPF}
            hr = HistoricoNFe(R.emp_do_responsavel(resp), base=t)
            he = HistoricoNFe({"nome": "LR TESTE", "cnpj": EMPRESA}, base=t)
            self.assertNotEqual(hr.pasta, he.pasta)
            self.assertTrue(hr.pasta.name.endswith(CPF))
            hr.confirmar([doc_nfe(4, xml_nfe(EMPRESA, CLI))], 4, 4)
            self.assertEqual(HistoricoNFe(R.emp_do_responsavel(resp), base=t).estado["ult_nsu"], 4)
            self.assertEqual(HistoricoNFe({"nome": "LR TESTE", "cnpj": EMPRESA}, base=t).estado["ult_nsu"], 0)   # NSU de cada consultante


if __name__ == "__main__":
    unittest.main()
