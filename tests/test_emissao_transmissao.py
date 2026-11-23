"""Envio da DPS assinada (`transmissao.enviar`): host/recurso fixos confirmados contra o manual
oficial do Emissor Público Nacional + convergência de fontes de mercado (ver docstring do módulo),
envelope JSON com gzip+base64, trava de produção, e tratamento de erro sem levantar por nota ruim —
a sessão com certificado é mockada aqui (`SessaoFalsa`/`Resposta` fake), nunca uma rede de verdade."""
import base64
import gzip
import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf.core import ErroAdge
from adge_nf.emissao import transmissao

XML_NFSE_SUCESSO = (
    '<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse">'
    '<infNFSe Id="NFS41137000123456780001900000010000000000000011">'
    '<nNFSe>11</nNFSe></infNFSe></NFSe>'
)


def _corpo_sucesso(xml_nfse: str = XML_NFSE_SUCESSO, chave: str = "") -> str:
    b64 = base64.b64encode(gzip.compress(xml_nfse.encode("utf-8"))).decode("ascii")
    corpo = {"codigoStatus": 100, "nfseXmlGZipB64": b64}
    if chave:
        corpo["chaveAcesso"] = chave
    return json.dumps(corpo)


class Resposta:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text

    def json(self):
        return json.loads(self.text)


class SessaoFalsa:
    """Registra a chamada feita por `enviar()`/`consultar_por_chave()` em vez de bater numa rede."""

    def __init__(self, resposta: Resposta):
        self.resposta = resposta
        self.chamadas = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.chamadas.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return self.resposta

    def get(self, url, headers=None, timeout=None):
        self.chamadas.append({"url": url, "headers": headers, "timeout": timeout})
        return self.resposta


class SessaoQueLevantaExcecao:
    def post(self, *a, **k):
        raise ConnectionError("rede fora do ar (simulado)")

    def get(self, *a, **k):
        raise ConnectionError("rede fora do ar (simulado)")


class ConstantesConfirmadasPelaPesquisa(unittest.TestCase):
    def test_hosts_producao_e_homologacao(self):
        self.assertEqual(transmissao.HOST_SEFIN_PRODUCAO, "https://sefin.nfse.gov.br/API/SefinNacional")
        self.assertEqual(transmissao.HOST_SEFIN_HOMOLOGACAO, "https://sefin.producaorestrita.nfse.gov.br/API/SefinNacional")


class TravaDeProducao(unittest.TestCase):
    def test_desligada_por_padrao(self):
        self.assertFalse(transmissao.PRODUCAO_REAL_LIBERADA)

    def test_ambiente_ativo_e_homologacao_enquanto_travado(self):
        self.assertEqual(transmissao.ambiente_ativo(), transmissao.TP_AMB_HOMOLOGACAO)

    def test_enviar_em_producao_recusa_quando_travado(self):
        sessao = SessaoFalsa(Resposta(200, _corpo_sucesso()))
        with self.assertRaises(ErroAdge):
            transmissao.enviar("<DPS/>", sessao, tp_amb=transmissao.TP_AMB_PRODUCAO)
        self.assertEqual(sessao.chamadas, [])  # nem chega a tentar mandar

    def test_enviar_em_homologacao_nao_e_afetado_pela_trava(self):
        sessao = SessaoFalsa(Resposta(200, _corpo_sucesso()))
        resultado = transmissao.enviar("<DPS/>", sessao, tp_amb=transmissao.TP_AMB_HOMOLOGACAO)
        self.assertTrue(resultado.sucesso)


class EnvioComSucesso(unittest.TestCase):
    def test_manda_pro_recurso_certo_em_json_gzip_base64(self):
        sessao = SessaoFalsa(Resposta(200, _corpo_sucesso()))
        transmissao.enviar("<DPS>conteudo</DPS>", sessao)
        self.assertEqual(len(sessao.chamadas), 1)
        chamada = sessao.chamadas[0]
        self.assertEqual(chamada["url"], f"{transmissao.HOST_SEFIN_HOMOLOGACAO}/nfse")
        self.assertEqual(chamada["headers"]["Content-Type"], "application/json; charset=utf-8")
        self.assertEqual(chamada["headers"]["User-Agent"], transmissao.USER_AGENT)
        self.assertIn("dpsXmlGZipB64", chamada["json"])
        descompactado = gzip.decompress(base64.b64decode(chamada["json"]["dpsXmlGZipB64"])).decode("utf-8")
        self.assertEqual(descompactado, "<DPS>conteudo</DPS>")

    def test_resultado_traz_numero_e_chave_da_resposta(self):
        sessao = SessaoFalsa(Resposta(200, _corpo_sucesso()))
        resultado = transmissao.enviar("<DPS/>", sessao)
        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.numero, "11")
        self.assertEqual(resultado.chave, "41137000123456780001900000010000000000000011")
        self.assertEqual(resultado.erro, "")

    def test_chave_cai_pro_campo_da_resposta_quando_o_xml_nao_tem(self):
        xml_sem_chave = '<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse"><infNFSe><nNFSe>5</nNFSe></infNFSe></NFSe>'
        sessao = SessaoFalsa(Resposta(200, _corpo_sucesso(xml_sem_chave, chave="chave-da-resposta")))
        resultado = transmissao.enviar("<DPS/>", sessao)
        self.assertEqual(resultado.chave, "chave-da-resposta")


class EnvioComErro(unittest.TestCase):
    def test_http_diferente_de_200_201_nao_levanta_fica_pendente(self):
        sessao = SessaoFalsa(Resposta(400, "erro de negócio qualquer"))
        resultado = transmissao.enviar("<DPS/>", sessao)
        self.assertFalse(resultado.sucesso)
        self.assertIn("400", resultado.erro)

    def test_falha_de_rede_nao_levanta_e_pede_para_conferir_antes_de_reenviar(self):
        resultado = transmissao.enviar("<DPS/>", SessaoQueLevantaExcecao())
        self.assertFalse(resultado.sucesso)
        self.assertIn("Conexão interrompida", resultado.erro)

    def test_resposta_201_tambem_e_sucesso(self):
        sessao = SessaoFalsa(Resposta(201, _corpo_sucesso()))
        resultado = transmissao.enviar("<DPS/>", sessao)
        self.assertTrue(resultado.sucesso)

    def test_resposta_sem_o_campo_esperado_nao_levanta_fica_pendente(self):
        sessao = SessaoFalsa(Resposta(200, json.dumps({"codigoStatus": 100})))
        resultado = transmissao.enviar("<DPS/>", sessao)
        self.assertFalse(resultado.sucesso)
        self.assertIn("formato inesperado", resultado.erro)


class ErroComPaginaHtml(unittest.TestCase):
    """Bloqueio de rede/servidor (ex.: 403 do IIS) não vem em JSON — vira uma página HTML genérica.
    O motivo precisa ficar legível (o título da página), não o HTML cru, e precisa deixar claro que
    isso não é uma rejeição de negócio da DPS."""
    HTML_403 = ('<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN">\r\n<html><head>'
                '<title>403 - Forbidden: Access is denied.</title></head><body>...</body></html>')

    def test_403_com_pagina_html_do_iis(self):
        sessao = SessaoFalsa(Resposta(403, self.HTML_403))
        resultado = transmissao.enviar("<DPS/>", sessao)
        self.assertFalse(resultado.sucesso)
        self.assertIn("403 - Forbidden: Access is denied.", resultado.erro)
        self.assertNotIn("<html>", resultado.erro)
        self.assertIn("não é uma rejeição da DPS", resultado.erro)

    def test_erro_de_negocio_json_continua_mostrando_o_codigo(self):
        sessao = SessaoFalsa(Resposta(400, '{"erros": [{"Codigo": "E1229", "Descricao": "Xml não UTF-8."}]}'))
        resultado = transmissao.enviar("<DPS/>", sessao)
        self.assertIn("E1229", resultado.erro)
        self.assertIn("Xml não UTF-8.", resultado.erro)


class ConsultaPorChave(unittest.TestCase):
    def test_consulta_com_sucesso(self):
        sessao = SessaoFalsa(Resposta(200, _corpo_sucesso()))
        resultado = transmissao.consultar_por_chave("41137000123456780001900000010000000000000011", sessao)
        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.numero, "11")
        self.assertEqual(sessao.chamadas[0]["headers"]["User-Agent"], transmissao.USER_AGENT)

    def test_404_nao_levanta_fica_erro_recuperavel(self):
        sessao = SessaoFalsa(Resposta(404, ""))
        resultado = transmissao.consultar_por_chave("chave-inexistente", sessao)
        self.assertFalse(resultado.sucesso)
        self.assertIn("Nenhuma NFS-e", resultado.erro)


class Cancelar(unittest.TestCase):
    def test_cancelamento_com_sucesso_manda_user_agent(self):
        sessao = SessaoFalsa(Resposta(200, "{}"))
        resultado = transmissao.cancelar("<pedRegEvento/>", "chave-qualquer", sessao)
        self.assertTrue(resultado.sucesso)
        self.assertEqual(resultado.chave, "chave-qualquer")
        chamada = sessao.chamadas[0]
        self.assertTrue(chamada["url"].endswith("/nfse/chave-qualquer/eventos"))
        self.assertEqual(chamada["headers"]["User-Agent"], transmissao.USER_AGENT)
        self.assertIn("pedidoRegistroEventoXmlGZipB64", chamada["json"])

    def test_cancelamento_recusado_nao_levanta(self):
        sessao = SessaoFalsa(Resposta(403, "<html><title>403 - Forbidden: Access is denied.</title></html>"))
        resultado = transmissao.cancelar("<pedRegEvento/>", "chave-qualquer", sessao)
        self.assertFalse(resultado.sucesso)
        self.assertIn("403 - Forbidden", resultado.erro)


if __name__ == "__main__":
    unittest.main()
