"""Atualização do programa pela página de Releases do projeto no GitHub.

Fluxo: consultar() -> aviso com botões -> baixar() confere o SHA-256 publicado na Release -> instalar_e_reabrir().
Nunca instala sozinho: só depois de a pessoa clicar em "Atualizar agora".
"""
import datetime as dt
import hashlib
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from . import REPO_GITHUB, VERSAO
from .core import Cancelado, ErroAdge
from .itens import PADRAO as _PADRAO_ITEM

HEX64 = re.compile(r"\b([0-9a-fA-F]{64})\b")


def _tupla(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def _hoje(hoje=None) -> dt.date:
    return hoje or dt.date.today()


def notas_legiveis(md: str) -> str:
    """Tira a marcação do Markdown das notas da Release para mostrar como texto simples."""
    linhas = []
    for l in (md or "").replace("\r", "").split("\n"):
        l = re.sub(r"^\s{0,3}#{1,6}\s*", "", l)                  # títulos
        l = re.sub(r"^\s*[-*+]\s+", "\u2022 ", l)                  # listas
        l = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", l)           # [texto](link)
        l = re.sub(r"(\*\*|__|`)", "", l)                         # negrito e código
        linhas.append(l.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(linhas)).strip()


TIPOS = {"NOVO": "Novo", "MELHORIA": "Melhoria", "CORRECAO": "Correção"}
_LINHA_ITEM = re.compile(r"^\s*[-*+]\s*\[([^\]]+)\]\s*(.+?)\s*\((ITEM-\d{2,3})\)\s*[:\-\u2013\u2014]\s*(.+?)\s*$")


def _tipo(txt: str):
    t = re.sub(r"[^A-Z]", "", txt.upper().replace("\u00c7", "C").replace("\u00c3", "A"))
    return t if t in TIPOS else None


def extrair_itens(md: str) -> list:
    """Lê a seção "## Resumo" do relatório da versão (docs/atualizacoes/vX.Y.Z.md).
    Cada linha: `- [NOVO] Nome do item (ITEM-NN): o que mudou.` Tipos: NOVO, MELHORIA, CORREÇÃO."""
    itens, dentro = [], False
    for l in (md or "").replace("\r", "").split("\n"):
        if re.match(r"^\s{0,3}##\s+", l):
            dentro = bool(re.match(r"^\s{0,3}##\s+resumo\b", l, re.I))
            continue
        if not dentro:
            continue
        m = _LINHA_ITEM.match(l)
        if m and _tipo(m[1]) and _PADRAO_ITEM.match(m[3]):
            itens.append({"tipo": _tipo(m[1]), "nome": m[2], "codigo": m[3], "texto": m[4]})
    return itens


def url_relatorio(repo: str, tags: list) -> str:
    """Link do relatório completo no GitHub: o arquivo da versão, ou a pasta quando são várias."""
    if len(tags) == 1:
        return f"https://github.com/{repo}/blob/{tags[0]}/docs/atualizacoes/{tags[0]}.md"
    return f"https://github.com/{repo}/tree/{tags[0]}/docs/atualizacoes"


# ----------------------------------------------------------------------------- consulta
def consultar(sessao=None, repo: str = None, versao: str = VERSAO, log=lambda *_: None):
    """Devolve os dados da última Release se ela for mais nova que `versao`; senão None.
    {tag, url, notas, msi: {nome, url, tamanho, sha256} | None}
    `log(texto)` conta cada etapa à medida que acontece (a tela mostra "checando o GitHub...", "avaliando a versão...")."""
    repo = REPO_GITHUB if repo is None else repo
    if not repo:
        return None
    log("Checando github.com (página de versões do projeto)...")
    s = sessao
    if s is None:
        import requests
        s = requests
    r = s.get(f"https://api.github.com/repos/{repo}/releases/latest", timeout=10,
              headers={"Accept": "application/vnd.github+json"})
    if r.status_code == 404:
        log("O projeto ainda não publicou nenhuma versão. Nada a atualizar.")
        return None  # o repositório ainda não tem nenhuma Release
    if r.status_code != 200:
        # limite de consultas do GitHub (403/429), erro do servidor etc.: não é "sem novidade", então avisa que não conseguiu
        raise ErroAdge(f"O GitHub não respondeu à consulta de versões (HTTP {r.status_code}).")
    j = r.json()
    tag = j.get("tag_name", "")
    log(f"GitHub respondeu. Avaliando a versão instalada (v{versao}) contra a última publicada ({tag or '?'})...")
    if not tag or _tupla(tag) <= _tupla(versao):
        log("Nenhuma atualização necessária: você já está na versão mais recente.")
        return None
    log(f"Atualização necessária: {tag} é mais nova que a v{versao}.")
    log("Lendo as novidades das versões que você ainda não tem...")
    info = {"tag": tag, "url": j.get("html_url") or f"https://github.com/{repo}/releases",
            "notas": notas_legiveis(j.get("body") or ""), "msi": None, "repo": repo}
    info["versoes"] = _versoes_novas(s, repo, versao, j)
    if info["versoes"]:
        info["relatorio_url"] = url_relatorio(repo, [v["tag"] for v in info["versoes"]])
    log("Conferindo o instalador (MSI) e o código de verificação (SHA-256)...")
    assets = j.get("assets", [])
    msi = next((a for a in assets if a.get("name", "").lower().endswith(".msi")), None)
    if msi:
        sha = None
        dig = str(msi.get("digest") or "")
        if dig.lower().startswith("sha256:"):
            sha = dig.split(":", 1)[1].strip().lower()
        if not sha:
            arq = next((a for a in assets if a.get("name", "").lower() == msi["name"].lower() + ".sha256"), None)
            if arq:
                try:
                    m = HEX64.search(s.get(arq["browser_download_url"], timeout=10).text)
                    sha = m[1].lower() if m else None
                except Exception:
                    sha = None
        info["msi"] = {"nome": msi["name"], "url": msi["browser_download_url"], "tamanho": msi.get("size"), "sha256": sha}
    log(f"Pronto: a versão {tag} está disponível para instalar.")
    return info


def _versoes_novas(s, repo: str, versao: str, ultima: dict) -> list:
    """Novidades (itens com código) de todas as versões acima da instalada, da mais nova para a mais antiga.
    Quem pulou versões vê o que cada uma trouxe. Versões sem resumo em itens ficam de fora."""
    corpos = {ultima.get("tag_name", ""): ultima.get("body") or ""}
    try:
        r = s.get(f"https://api.github.com/repos/{repo}/releases", params={"per_page": 15}, timeout=10,
                  headers={"Accept": "application/vnd.github+json"})
        lista = r.json() if r.status_code == 200 else None
        for rel in lista if isinstance(lista, list) else []:
            t = rel.get("tag_name", "")
            if t and not rel.get("draft") and not rel.get("prerelease") and _tupla(t) > _tupla(versao):
                corpos.setdefault(t, rel.get("body") or "")
    except Exception:
        pass  # a lista é um extra: sem ela, vale só a última versão
    saida = []
    for t in sorted(corpos, key=_tupla, reverse=True):
        if _tupla(t) <= _tupla(versao):
            continue
        itens = extrair_itens(corpos[t])
        if itens:
            saida.append({"tag": t, "itens": itens})
    return saida


# ----------------------------------------------------------------------------- preferências (quando avisar)
def _prefs(prefs: dict) -> dict:
    return prefs.setdefault("atualizacao", {})


def deve_checar(prefs: dict, hoje=None) -> bool:
    """No máximo uma consulta por dia."""
    return _prefs(prefs).get("ultima_checagem") != _hoje(hoje).isoformat()


def marcar_checagem(prefs: dict, hoje=None):
    _prefs(prefs)["ultima_checagem"] = _hoje(hoje).isoformat()


def deve_avisar(info: dict, prefs: dict, hoje=None) -> bool:
    p = _prefs(prefs)
    if p.get("pular") == info["tag"]:
        return False
    ate = p.get("lembrar_ate")
    return not (ate and _hoje(hoje).isoformat() <= ate)


def lembrar_depois(prefs: dict, dias: int = 3, hoje=None):
    _prefs(prefs)["lembrar_ate"] = (_hoje(hoje) + dt.timedelta(days=dias)).isoformat()


def pular_versao(prefs: dict, tag: str):
    _prefs(prefs)["pular"] = tag


# ----------------------------------------------------------------------------- download e instalação
def baixar(msi: dict, progresso=lambda feito, total: None, cancelar=lambda: False, sessao=None, pasta=None, repo: str = None) -> Path:
    """Baixa o MSI, confere o SHA-256 publicado na Release e devolve o caminho. Apaga o arquivo se algo não bater."""
    repo = REPO_GITHUB if repo is None else repo
    if not msi.get("sha256"):
        raise ErroAdge("Essa versão não traz o código de verificação (SHA-256), então não vou instalá-la automaticamente. "
                       "Use \"Abrir a página de download\".")
    if not str(msi["url"]).startswith(f"https://github.com/{repo}/releases/download/"):
        raise ErroAdge("O endereço de download não é o da página oficial de versões do projeto.")
    s = sessao
    if s is None:
        import requests
        s = requests
    pasta = Path(pasta or tempfile.mkdtemp(prefix="adge-nf-update-"))
    destino = pasta / re.sub(r"[^\w.\-]", "_", msi["nome"])
    parcial = destino.with_suffix(".part")
    h = hashlib.sha256()
    feito = 0
    try:
        r = s.get(msi["url"], stream=True, timeout=30)
        if r.status_code != 200:
            raise ErroAdge(f"Não consegui baixar a atualização (HTTP {r.status_code}).")
        total = int(r.headers.get("Content-Length") or msi.get("tamanho") or 0)
        with open(parcial, "wb") as f:
            for bloco in r.iter_content(65536):
                if cancelar():
                    raise Cancelado()
                f.write(bloco)
                h.update(bloco)
                feito += len(bloco)
                progresso(feito, total)
        if msi.get("tamanho") and feito != msi["tamanho"]:
            raise ErroAdge("O download veio incompleto. Tente de novo.")
        if h.hexdigest().lower() != msi["sha256"].lower():
            raise ErroAdge("A verificação de integridade falhou: o arquivo baixado não é o publicado. A instalação foi cancelada.")
        parcial.replace(destino)
        return destino
    except ErroAdge:
        parcial.unlink(missing_ok=True)
        raise
    except Cancelado:
        parcial.unlink(missing_ok=True)
        raise
    except Exception as e:
        parcial.unlink(missing_ok=True)
        raise ErroAdge(f"Não consegui baixar a atualização: {e}") from e


def comando_instalacao(msi: Path, exe: str = None) -> str:
    """Linha de comando do Windows: espera o app fechar, roda o instalador (UAC) e reabre o programa."""
    c = 'ping -n 3 127.0.0.1 >nul & msiexec /i "{}" /passive /norestart'.format(msi)
    if exe:
        c += ' & start "" "{}"'.format(exe)
    return 'cmd.exe /d /s /c "{}"'.format(c)


def instalar_e_reabrir(msi: Path, exe: str = None):
    """Dispara o instalador desacoplado do app. Quem chamou deve fechar o programa logo depois."""
    if os.name != "nt":
        raise ErroAdge("A instalação automática só funciona no Windows.")
    exe = exe or (sys.executable if getattr(sys, "frozen", False) else None)
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(comando_instalacao(msi, exe), creationflags=flags, close_fds=True)


def pode_instalar_sozinho() -> bool:
    """Só no programa instalado (.exe), nunca rodando do código-fonte."""
    return os.name == "nt" and bool(getattr(sys, "frozen", False))
