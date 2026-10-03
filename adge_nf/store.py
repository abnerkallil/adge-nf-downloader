"""Empresas salvas e senhas dos certificados.

As senhas dos certificados NUNCA ficam em texto: são cifradas (Fernet/AES) e a chave fica
  - no Cofre do Windows (Gerenciador de Credenciais), ou
  - derivada de uma senha mestra que a pessoa digita ao abrir o app (a chave não é gravada).
Tudo fica no computador da pessoa, em %APPDATA%\\AdgeGroup\\NFDownloader.
"""
import base64
import json
import os
import uuid
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .core import ErroAdge

SERVICO_COFRE = "AdgeGroup-NFDownloader"
USUARIO_COFRE = "chave-das-senhas"
ITERACOES = 480_000


def pasta_dados() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    p = Path(base) / "AdgeGroup" / "NFDownloader"
    p.mkdir(parents=True, exist_ok=True)
    return p


def empresa_padrao() -> dict:
    return {
        "id": uuid.uuid4().hex[:12], "nome": "", "cnpj": "", "pfx": "", "senha_cifrada": "",
        "destino": "", "estrutura": "ano_mes",
        "tipos": {"prestado": True, "tomado": True}, "nfe": False, "nfe_ciencia": False, "paulistana": False,
        "acao": "ambos",              # ambos | calcular | baixar
        "relatorio": True, "planilha": False,
        "prefixo_prestado": "", "prefixo_tomado": "",
        "fiscal": {},                 # dados da simulação de regimes (preenchidos em "Informações avançadas")
    }


class Armazenamento:
    def __init__(self, pasta: Path = None, keyring_mod=None):
        self.pasta = Path(pasta) if pasta else pasta_dados()
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.arquivo = self.pasta / "empresas.json"
        self._keyring = keyring_mod
        self._fernet = None
        self.dados = self._ler()

    # ------------------------------------------------------------------ arquivo
    def _ler(self) -> dict:
        if self.arquivo.exists():
            try:
                return json.loads(self.arquivo.read_text(encoding="utf-8"))
            except ValueError:
                (self.pasta / "empresas.corrompido.json").write_bytes(self.arquivo.read_bytes())
        return {"versao": 1, "seguranca": {"modo": "cofre"}, "empresas": [], "preferencias": {}}

    def salvar(self):
        tmp = self.arquivo.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.dados, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.arquivo)

    # ------------------------------------------------------------------ chave
    def _kr(self):
        if self._keyring is None:
            try:
                import keyring
                if os.name == "nt":  # no .exe congelado a descoberta automática pode falhar: fixa o Cofre do Windows
                    from keyring.backends.Windows import WinVaultKeyring
                    keyring.set_keyring(WinVaultKeyring())
                self._keyring = keyring
            except ImportError as e:
                raise ErroAdge("Cofre do Windows indisponível. Defina uma senha mestra em Configurações.") from e
        return self._keyring

    @property
    def modo(self) -> str:
        return self.dados.get("seguranca", {}).get("modo", "cofre")

    @property
    def precisa_mestra(self) -> bool:
        return self.modo == "mestra" and self._fernet is None

    def _chave_do_cofre(self, criar=True) -> bytes:
        kr = self._kr()
        try:
            k = kr.get_password(SERVICO_COFRE, USUARIO_COFRE)
            if not k and criar:
                k = Fernet.generate_key().decode()
                kr.set_password(SERVICO_COFRE, USUARIO_COFRE, k)
        except ErroAdge:
            raise
        except Exception as e:
            raise ErroAdge(f"Não consegui usar o Cofre do Windows: {e}") from e
        if not k:
            raise ErroAdge("A chave do Cofre do Windows não foi encontrada (as senhas salvas não podem ser lidas).")
        return k.encode()

    @staticmethod
    def _chave_da_mestra(senha: str, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERACOES)
        return base64.urlsafe_b64encode(kdf.derive(senha.encode("utf-8")))

    def abrir(self, mestra: str = None):
        """Deixa as senhas utilizáveis. No modo senha mestra, `mestra` é obrigatória."""
        seg = self.dados["seguranca"]
        if self.modo == "mestra":
            if not mestra:
                raise ErroAdge("Digite a senha mestra.")
            chave = self._chave_da_mestra(mestra, base64.b64decode(seg["salt"]))
            try:
                Fernet(chave).decrypt(seg["verificador"].encode())
            except InvalidToken:
                raise ErroAdge("Senha mestra incorreta.") from None
            self._fernet = Fernet(chave)
        else:
            self._fernet = Fernet(self._chave_do_cofre())

    # ------------------------------------------------------------------ senhas
    def cifrar(self, senha: str) -> str:
        if self._fernet is None:
            self.abrir()
        return self._fernet.encrypt(senha.encode("utf-8")).decode()

    def decifrar(self, token: str) -> str:
        if not token:
            return ""
        if self._fernet is None:
            self.abrir()
        try:
            return self._fernet.decrypt(token.encode()).decode("utf-8")
        except InvalidToken:
            raise ErroAdge("Não consegui abrir a senha salva (chave diferente). Digite a senha do certificado de novo.") from None

    def trocar_modo(self, nova_mestra: str = None):
        """Sem `nova_mestra`: volta para o Cofre do Windows. Com ela: passa a exigir senha mestra.
        Reencripta todas as senhas salvas (o app precisa estar aberto/desbloqueado)."""
        if self._fernet is None:
            self.abrir()
        alvos = list(self.dados["empresas"]) + ([self.dados["responsavel"]] if self.dados.get("responsavel") else [])
        antigas = [(e, self.decifrar(e.get("senha_cifrada", ""))) for e in alvos]
        if nova_mestra:
            salt = os.urandom(16)
            chave = self._chave_da_mestra(nova_mestra, salt)
            self.dados["seguranca"] = {"modo": "mestra", "salt": base64.b64encode(salt).decode(),
                                       "verificador": Fernet(chave).encrypt(b"ok").decode()}
            self._fernet = Fernet(chave)
        else:
            self.dados["seguranca"] = {"modo": "cofre"}
            self._fernet = Fernet(self._chave_do_cofre())
        for e, senha in antigas:
            e["senha_cifrada"] = self.cifrar(senha) if senha else ""
        self.salvar()

    # ------------------------------------------------------------------ empresas
    @property
    def empresas(self) -> list:
        return self.dados["empresas"]

    def obter(self, id_: str) -> dict:
        return next(e for e in self.empresas if e["id"] == id_)

    def apagar_tudo(self):
        """Apaga empresas, o responsável, preferências e a chave do Cofre do Windows. Não toca nos certificados nem nos XMLs."""
        try:
            self._kr().delete_password(SERVICO_COFRE, USUARIO_COFRE)
        except ErroAdge:
            pass
        except Exception:
            pass  # chave já inexistente: segue
        for f in (self.arquivo, self.arquivo.with_suffix(".tmp"), self.pasta / "empresas.corrompido.json"):
            try:
                f.unlink()
            except FileNotFoundError:
                pass
            except OSError as e:
                raise ErroAdge(f"Não consegui apagar {f.name}: {e}") from e
        self._fernet = None
        self.dados = {"versao": 1, "seguranca": {"modo": "cofre"}, "empresas": [], "preferencias": {}}

    def salvar_empresa(self, emp: dict, senha: str = None):
        """`senha`: None mantém a salva; "" apaga; texto novo cifra."""
        if senha is not None:
            emp["senha_cifrada"] = self.cifrar(senha) if senha else ""
        for i, e in enumerate(self.empresas):
            if e["id"] == emp["id"]:
                self.empresas[i] = emp
                break
        else:
            self.empresas.append(emp)
        self.empresas.sort(key=lambda e: e.get("nome", "").lower())
        self.salvar()

    def excluir_empresa(self, id_: str):
        self.dados["empresas"] = [e for e in self.empresas if e["id"] != id_]
        self.salvar()

    def senha_da_empresa(self, emp: dict) -> str:
        return self.decifrar(emp.get("senha_cifrada", ""))

    # ------------------------------------------------------------------ responsável (v1.7.6)
    @property
    def responsavel(self):
        """Cadastro do responsável (CPF ou CNPJ de quem recebe, por autXML, as notas das empresas) ou None. Fica só neste computador."""
        return self.dados.get("responsavel") or None

    def salvar_responsavel(self, resp: dict, senha: str = None):
        """`senha`: None mantém a salva; "" apaga; texto novo cifra (mesma proteção das senhas das empresas)."""
        if senha is not None:
            resp["senha_cifrada"] = self.cifrar(senha) if senha else ""
        self.dados["responsavel"] = resp
        self.salvar()

    def excluir_responsavel(self):
        self.dados.pop("responsavel", None)
        self.salvar()

    def senha_do_responsavel(self, resp: dict = None) -> str:
        resp = resp or self.responsavel
        return self.decifrar((resp or {}).get("senha_cifrada", ""))

    @property
    def preferencias(self) -> dict:
        return self.dados.setdefault("preferencias", {})
