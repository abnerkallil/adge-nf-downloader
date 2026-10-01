"""Aviso (opcional) de versão nova: consulta a última Release pública do projeto no GitHub."""
import re

from . import REPO_GITHUB, VERSAO


def _tupla(v: str):
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def versao_nova(sessao=None):
    """Devolve (tag, url) da versão mais nova que a instalada, ou None."""
    if not REPO_GITHUB:
        return None
    import requests
    r = (sessao or requests).get(f"https://api.github.com/repos/{REPO_GITHUB}/releases/latest", timeout=10)
    if r.status_code != 200:
        return None
    j = r.json()
    tag = j.get("tag_name", "")
    if tag and _tupla(tag) > _tupla(VERSAO):
        return tag, j.get("html_url", f"https://github.com/{REPO_GITHUB}/releases")
    return None
