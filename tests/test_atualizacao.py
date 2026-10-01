import datetime as dt
import hashlib
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from adge_nf import atualizacao as A
from adge_nf.core import Cancelado, ErroAdge

REPO = "dono/projeto"
CONTEUDO = b"conteudo-do-msi" * 1000
SHA = hashlib.sha256(CONTEUDO).hexdigest()
URL = f"https://github.com/{REPO}/releases/download/v1.1.0/App-1.1.0.msi"


class Resp:
    def __init__(self, code=200, json=None, texto="", conteudo=b""):
        self.status_code, self._j, self.text, self._c = code, json, texto, conteudo
        self.headers = {"Content-Length": str(len(conteudo))}

    def json(self):
        return self._j

    def iter_content(self, n):
        for i in range(0, len(self._c), n):
            yield self._c[i:i + n]


class Sessao:
    def __init__(self, release=None, conteudo=CONTEUDO, code_release=200):
        self.release, self.conteudo, self.code = release, conteudo, code_release
        self.urls = []

    def get(self, url, **k):
        self.urls.append(url)
        if url.endswith("/releases/latest"):
            return Resp(self.code, self.release)
        if url.endswith(".sha256"):
            return Resp(200, texto=f"{SHA}  App-1.1.0.msi\n")
        return Resp(200, conteudo=self.conteudo)


def release(tag="v1.1.0", digest=True, sha_asset=False):
    msi = {"name": "App-1.1.0.msi", "browser_download_url": URL, "size": len(CONTEUDO)}
    if digest:
        msi["digest"] = "sha256:" + SHA
    assets = [msi]
    if sha_asset:
        assets.append({"name": "App-1.1.0.msi.sha256", "browser_download_url": URL + ".sha256"})
    return {"tag_name": tag, "html_url": "https://github.com/dono/projeto/releases/tag/" + tag, "body": "Novidades: NF-e", "assets": assets}


class Consulta(unittest.TestCase):
    def test_versao_nova_com_digest(self):
        i = A.consultar(Sessao(release()), repo=REPO, versao="1.0.0")
        self.assertEqual(i["tag"], "v1.1.0")
        self.assertEqual(i["notas"], "Novidades: NF-e")
        self.assertEqual(A.notas_legiveis("## Novidades\n- **Suporte** a `NF-e`\n* [Veja](http://x) tudo\n\n\n\nfim"),
                         "Novidades\n\u2022 Suporte a NF-e\n\u2022 Veja tudo\n\nfim")
        self.assertEqual(i["msi"]["sha256"], SHA)

    def test_sha_pelo_arquivo_sha256(self):
        i = A.consultar(Sessao(release(digest=False, sha_asset=True)), repo=REPO, versao="1.0.0")
        self.assertEqual(i["msi"]["sha256"], SHA)

    def test_sem_sha_fica_none(self):
        i = A.consultar(Sessao(release(digest=False)), repo=REPO, versao="1.0.0")
        self.assertIsNone(i["msi"]["sha256"])

    def test_mesma_ou_menor_versao(self):
        self.assertIsNone(A.consultar(Sessao(release("v1.0.0")), repo=REPO, versao="1.0.0"))
        self.assertIsNone(A.consultar(Sessao(release("v0.9.0")), repo=REPO, versao="1.0.0"))
        self.assertIsNotNone(A.consultar(Sessao(release("v1.10.0")), repo=REPO, versao="1.9.0"))  # 10 > 9, não texto

    def test_sem_release_ou_sem_repo(self):
        self.assertIsNone(A.consultar(Sessao(code_release=404), repo=REPO, versao="1.0.0"))
        self.assertIsNone(A.consultar(Sessao(release()), repo="", versao="1.0.0"))


CORPO = "## Resumo\n- [NOVO] {n} ({c}): {t}\n\n## Detalhes\n"


class SessaoLista(Sessao):
    """Além da última Release, devolve a lista de Releases (para quem pulou versões)."""
    def __init__(self, lista, **k):
        super().__init__(**k)
        self.lista = lista

    def get(self, url, **k):
        if url.endswith("/releases"):
            self.urls.append(url)
            return Resp(200, self.lista)
        return super().get(url, **k)


class Novidades(unittest.TestCase):
    def test_junta_as_versoes_puladas_da_mais_nova_para_a_mais_antiga(self):
        r = release("v1.3.3")
        r["body"] = CORPO.format(n="Boas-vindas da primeira abertura", c="ITEM-19", t="cartão")
        lista = [
            {"tag_name": "v1.3.3", "body": r["body"]},
            {"tag_name": "v1.3.2", "body": CORPO.format(n="Novidades no aviso de atualização", c="ITEM-18", t="resumo")},
            {"tag_name": "v1.3.1", "body": "notas automáticas sem resumo"},
            {"tag_name": "v1.2.0", "body": CORPO.format(n="Planilha Excel", c="ITEM-09", t="velha"), "draft": False},
            {"tag_name": "v1.4.0-beta", "body": CORPO.format(n="X", c="ITEM-01", t="x"), "prerelease": True},
        ]
        i = A.consultar(SessaoLista(lista, release=r), repo=REPO, versao="1.3.1")
        self.assertEqual([v["tag"] for v in i["versoes"]], ["v1.3.3", "v1.3.2"])
        self.assertEqual(i["versoes"][1]["itens"][0]["codigo"], "ITEM-18")
        self.assertTrue(i["relatorio_url"].endswith("/tree/v1.3.3/docs/atualizacoes"))

    def test_uma_versao_so_aponta_para_o_arquivo(self):
        r = release("v1.3.2")
        r["body"] = CORPO.format(n="Planilha Excel", c="ITEM-09", t="ok")
        i = A.consultar(Sessao(r), repo=REPO, versao="1.3.1")  # sem lista: a sessão devolve lixo e isso é ignorado
        self.assertEqual([v["tag"] for v in i["versoes"]], ["v1.3.2"])
        self.assertTrue(i["relatorio_url"].endswith("/blob/v1.3.2/docs/atualizacoes/v1.3.2.md"))

    def test_release_sem_resumo_cai_no_texto(self):
        i = A.consultar(Sessao(release()), repo=REPO, versao="1.0.0")
        self.assertEqual(i["versoes"], [])
        self.assertNotIn("relatorio_url", i)
        self.assertEqual(i["notas"], "Novidades: NF-e")


class Preferencias(unittest.TestCase):
    def test_uma_consulta_por_dia(self):
        p, hoje = {}, dt.date(2026, 10, 1)
        self.assertTrue(A.deve_checar(p, hoje))
        A.marcar_checagem(p, hoje)
        self.assertFalse(A.deve_checar(p, hoje))
        self.assertTrue(A.deve_checar(p, hoje + dt.timedelta(days=1)))

    def test_lembrar_depois_e_pular(self):
        info, p, hoje = {"tag": "v1.1.0"}, {}, dt.date(2026, 10, 1)
        self.assertTrue(A.deve_avisar(info, p, hoje))
        A.lembrar_depois(p, 3, hoje)
        self.assertFalse(A.deve_avisar(info, p, dt.date(2026, 10, 3)))
        self.assertFalse(A.deve_avisar(info, p, dt.date(2026, 10, 4)))
        self.assertTrue(A.deve_avisar(info, p, dt.date(2026, 10, 5)))
        A.pular_versao(p, "v1.1.0")
        self.assertFalse(A.deve_avisar(info, p, dt.date(2026, 12, 1)))
        self.assertTrue(A.deve_avisar({"tag": "v1.2.0"}, p, dt.date(2026, 12, 1)))  # outra versão volta a avisar


class Download(unittest.TestCase):
    def msi(self, **k):
        d = {"nome": "App-1.1.0.msi", "url": URL, "tamanho": len(CONTEUDO), "sha256": SHA}
        d.update(k)
        return d

    def test_baixa_e_confere(self):
        with tempfile.TemporaryDirectory() as t:
            marcas = []
            c = A.baixar(self.msi(), progresso=lambda f, tot: marcas.append((f, tot)), sessao=Sessao(), pasta=t, repo=REPO)
            self.assertEqual(c.read_bytes(), CONTEUDO)
            self.assertEqual(marcas[-1][0], len(CONTEUDO))
            self.assertFalse(list(pathlib.Path(t).glob("*.part")))

    def test_arquivo_adulterado_e_recusado_e_apagado(self):
        with tempfile.TemporaryDirectory() as t:
            ruim = bytearray(CONTEUDO)
            ruim[10] ^= 1
            with self.assertRaises(ErroAdge) as cm:
                A.baixar(self.msi(), sessao=Sessao(conteudo=bytes(ruim)), pasta=t, repo=REPO)
            self.assertIn("integridade", str(cm.exception))
            self.assertEqual(list(pathlib.Path(t).iterdir()), [])

    def test_download_incompleto(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ErroAdge):
                A.baixar(self.msi(), sessao=Sessao(conteudo=CONTEUDO[:-5]), pasta=t, repo=REPO)

    def test_sem_sha_nao_instala(self):
        with self.assertRaises(ErroAdge):
            A.baixar(self.msi(sha256=None), sessao=Sessao(), repo=REPO)

    def test_endereco_de_outro_dono_e_recusado(self):
        with self.assertRaises(ErroAdge):
            A.baixar(self.msi(url="https://exemplo.com/App.msi"), sessao=Sessao(), repo=REPO)
        with self.assertRaises(ErroAdge):
            A.baixar(self.msi(url="https://github.com/outro/repo/releases/download/v1/App.msi"), sessao=Sessao(), repo=REPO)

    def test_cancelar_apaga_parcial(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(Cancelado):
                A.baixar(self.msi(), cancelar=lambda: True, sessao=Sessao(), pasta=t, repo=REPO)
            self.assertEqual(list(pathlib.Path(t).iterdir()), [])


class Instalacao(unittest.TestCase):
    def test_comando(self):
        c = A.comando_instalacao(pathlib.PureWindowsPath(r"C:\Temp\App 1.1.msi"), r"C:\Program Files\Adge\App.exe")
        self.assertIn(r'msiexec /i "C:\Temp\App 1.1.msi" /passive /norestart', c)
        self.assertIn(r'start "" "C:\Program Files\Adge\App.exe"', c)
        self.assertTrue(c.startswith('cmd.exe /d /s /c "') and c.endswith('"'))
        self.assertNotIn('start ""', A.comando_instalacao(pathlib.PureWindowsPath(r"C:\a.msi")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
