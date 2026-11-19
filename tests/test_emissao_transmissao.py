"""Envio da DPS assinada (`transmissao.enviar`): host/recurso fixos confirmados pela pesquisa,
envelope gzip+base64, trava de produção, e tratamento de erro sem levantar por nota ruim — a
sessão com certificado é mockada aqui (`Sessao`/`Resposta` fake), nunca uma rede de verdade."""
import base64
import gzip
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.core import ErroAdge
from adge_nf.emissao import transmissao

XML_RESPOSTA_SUCESSO = (
    '<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse">'
    '<infNFSe Id="NFS41137000123456780001900000010000000000000011">'
    '<nNFSe>11</nNFSe></infNFSe></NFSe>'
)


class Resposta:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text


class SessaoFalsa:
    """Registra a chamada feita por `enviar()` em vez de bater numa rede de verdade."""

    def __init__(self, resposta: Resposta):
        self.resposta = resposta
        self.chamadas = []

    def post(self, url, data=None, headers=None, timeout=None):
        self.chamadas.append({"url": url, "data": data, "headers": headers, "timeout": timeout})
        return self.resposta


class SessaoQueLevantaExcecao:
    def post(self, *a, **k):
        raise ConnectionError("rede fora do ar (simulado)")


class ConstantesConfirmadasPelaPesquisa(unittest.TestCase):
    def test_host_e_recurso(self):
        self.assertEqual(transmissao.HOST_SEFIN, "https://sefin.nfse.gov.br/SefinNacional")
        self.assertEqual(transmissao.RECURSO_NFSE, "https://sefin.nfse.gov.br/SefinNacional/nfse")


class TravaDeProducao(unittest.TestCase):
    def test_desligada_por_padrao(self):
        self.assertFalse(transmissao.PRODUCAO_REAL_LIBERADA)

    def test_ambiente_ativo_e_homologacao_enquanto_travado(self):
        self.assertEqual(transmissao.ambiente_ativo(), transmissao.TP_AMB_HOMOLOGACAO)

    def test_enviar_em_producao_recusa_quando_travado(self):
        sessao = SessaoFalsa(Resposta(200, XML_RESPOSTA_SUCESSO))
        with self.assertRaises(ErroAdge):
            transmissao.enviar("<DPS/>", sessao, tp_amb=transmissao.TP_AMB_PRODUCAO)
        self.assertEqual(sessao.chamadas, [])  # nem chega a tentar mandar

    def test_enviar_em_homologacao_nao_e_afetado_pela_trava(self):
        sessao = SessaoFalsa(Resposta(200, XML_RESPOSTA_SUCESSO))
        resultado = transmissao.enviar("<DPS/>", sessao, tp_amb=transmissao.TP_AMB_HOMOLOGACAO)
        self.assertTrue(resultado.sucesso)


class EnvioComSucesso(unittest.TestCase):
    def test_manda_pro_recurso_certo_compactado_em_gzip_base64(self):
        sessao = SessaoFalsa(Resposta(200, XML_RESPOSTA_SUCESSO))
        transmissao.enviar("<DPS>conteudo</DPS>", sessao)
        self.assertEqual(len(sessao.chamadas), 1)
        chamada = sessao.chamadas[0]
        self.assertEqual(chamada["url"], transmissao.RECURSO_NFSE)
        self.assertEqual(chamada["headers"], {"Content-Type": "text/plain"})
        descompactado = gzip.decompress(base64.b64decode(chamada["data"])).decode("utf-8")
        self.assertEqual(descompactado, "<DPS>conteudo</DPS>")

    def test_resultado_traz_numero_e_chave_da_resposta(self):
        sessao = SessaoFalsa(Resposta(200, XML_RESPOSTA_SUCESSO))
        resultado = transmissao.enviar("<DPS/>", sessao)
        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.numero, "11")
        self.assertEqual(resultado.chave, "41137000123456780001900000010000000000000011")
        self.assertEqual(resultado.erro, "")


class EnvioComErro(unittest.TestCase):
    def test_http_diferente_de_200_201_nao_levanta_fica_pendente(self):
        sessao = SessaoFalsa(Resposta(400, "erro de negócio qualquer"))
        resultado = transmissao.enviar("<DPS/>", sessao)
        self.assertFalse(resultado.sucesso)
        self.assertIn("400", resultado.erro)

    def test_falha_de_rede_nao_levanta_fica_pendente(self):
        resultado = transmissao.enviar("<DPS/>", SessaoQueLevantaExcecao())
        self.assertFalse(resultado.sucesso)
        self.assertIn("Sefin Nacional", resultado.erro)

    def test_resposta_201_tambem_e_sucesso(self):
        sessao = SessaoFalsa(Resposta(201, XML_RESPOSTA_SUCESSO))
        resultado = transmissao.enviar("<DPS/>", sessao)
        self.assertTrue(resultado.sucesso)

    def test_resposta_ilegivel_nao_levanta_devolve_sucesso_sem_numero(self):
        sessao = SessaoFalsa(Resposta(200, "isso não é XML nenhum"))
        resultado = transmissao.enviar("<DPS/>", sessao)
        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.numero, "")


if __name__ == "__main__":
    unittest.main()
