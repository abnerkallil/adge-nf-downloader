"""Gera o instalador MSI (Windows):   python setup.py bdist_msi
O MSI instala o programa com tudo dentro (inclusive o Python), cria atalhos no Menu Iniciar e na Área de Trabalho
e atualiza versões antigas sozinho (mesmo UpgradeCode)."""
import sys

from cx_Freeze import Executable, setup

from adge_nf import NOME_APP, VERSAO

UPGRADE_CODE = "{4AE14496-2E7A-428C-B8EE-72324E2CD79F}"  # nunca mude: é o que permite atualizar por cima
EXE = "AdgeNFDownloader.exe"

# Atalhos: (id, pasta, nome, componente, alvo, args, descrição, hotkey, ícone, índice do ícone, janela, pasta de trabalho)
atalhos = [
    ("AtalhoMenu", "ProgramMenuFolder", NOME_APP, "TARGETDIR", f"[TARGETDIR]{EXE}", None,
     "Baixa e organiza NFS-e Nacional", None, None, None, None, "TARGETDIR"),
    ("AtalhoDesktop", "DesktopFolder", NOME_APP, "TARGETDIR", f"[TARGETDIR]{EXE}", None,
     "Baixa e organiza NFS-e Nacional", None, None, None, None, "TARGETDIR"),
]

build_exe = {
    "packages": ["adge_nf", "tkinter", "requests", "requests_pkcs12", "keyring", "keyring.backends", "win32ctypes",
                 "openpyxl", "et_xmlfile", "cryptography", "certifi", "urllib3", "idna", "charset_normalizer"],
    "includes": ["keyring.backends.Windows"],
    "include_files": [("adge_nf/icone.ico", "icone.ico")],
    "excludes": ["unittest", "pydoc", "test", "distutils"],
    "include_msvcr": True,
}

bdist_msi = {
    "upgrade_code": UPGRADE_CODE,
    "initial_target_dir": rf"[ProgramFilesFolder]\Adge Group\{NOME_APP}",
    "all_users": True,
    "data": {"Shortcut": atalhos},
    "summary_data": {"author": "Adge Group", "comments": "Baixa e organiza NFS-e Nacional (uso local)"},
    "install_icon": "adge_nf/icone.ico",
}

setup(
    name=NOME_APP,
    version=VERSAO,
    description="Baixa e organiza NFS-e Nacional com o certificado A1 da empresa",
    author="Adge Group",
    options={"build_exe": build_exe, "bdist_msi": bdist_msi},
    executables=[Executable("adge_nf_downloader.pyw", base="gui" if sys.platform == "win32" else None,
                            target_name=EXE, icon="adge_nf/icone.ico")],
)
