"""Lançamento: uma nota a emitir, antes de virar DPS. Vem da digitação manual, da planilha modelo
ou de um documento do cliente (ver `importador_documento.py`), sempre com os mesmos campos."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from ..core import ErroAdge

ORIGENS = ("manual", "planilha", "documento")


def _so_digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


@dataclass
class Lancamento:
    tomador_nome: str = ""
    tomador_documento: str = ""           # CPF (11) ou CNPJ (14), só dígitos
    valor: float = 0.0
    competencia: str = ""                 # "AAAA-MM"
    data_prestacao: str = ""              # "AAAA-MM-DD"; vazio -> usa o último dia da competência
    endereco: str = ""                    # usado no casamento de tomador e, se o perfil pedir, na descrição
    observacoes: str = ""                 # texto livre vindo da origem (ex.: "Não conseguiu pagar")
    perfil_nome: str = ""                 # override explícito (ex.: coluna da planilha); vazio = casar tomador/perguntar
    retencao_pis_cofins_csll: bool | None = None  # None = ainda não perguntado; batch pergunta 1x p/ o lote, manual pergunta por nota
    origem: str = "manual"
    linha_origem: int = 0                 # linha na planilha/documento, para apontar erros; 0 = manual
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    excluir: bool = False                 # não gera nota (ex.: valor zerado); editável na prévia
    motivo_exclusao: str = ""

    def __post_init__(self):
        self.tomador_documento = _so_digitos(self.tomador_documento)
        if self.origem not in ORIGENS:
            raise ErroAdge(f"Origem de lançamento desconhecida: {self.origem}")
        if not self.excluir and self.valor <= 0:
            self.excluir = True
            self.motivo_exclusao = self.motivo_exclusao or "Valor zerado ou não informado"

    @property
    def tipo_documento(self) -> str:
        n = len(self.tomador_documento)
        return "cnpj" if n == 14 else "cpf" if n == 11 else ""

    def validar(self) -> list:
        """Lista de problemas (strings) que impedem a emissão; vazia = pronto, fora a exclusão manual."""
        erros = []
        if not self.tomador_nome.strip():
            erros.append("Tomador sem nome")
        if self.tipo_documento == "":
            erros.append("Documento do tomador inválido (precisa de CPF ou CNPJ)")
        if not re.match(r"^\d{4}-\d{2}$", self.competencia or ""):
            erros.append("Competência inválida (use AAAA-MM)")
        if self.valor < 0:
            erros.append("Valor negativo")
        return erros
