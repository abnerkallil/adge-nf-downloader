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
    nif: str = ""                         # toma/NIF — tomador estrangeiro sem CPF/CNPJ; sobrepõe o NIF do cadastro
    motivo_sem_nif: str = ""              # toma/cNaoNIF — ver es.NIF_MOTIVOS; só usado se não houver documento nem NIF
    valor: float = 0.0
    competencia: str = ""                 # "AAAA-MM"
    data_prestacao: str = ""              # "AAAA-MM-DD"; vazio -> usa o último dia da competência
    endereco: str = ""                    # usado no casamento de tomador e, se o perfil pedir, na descrição
    observacoes: str = ""                 # texto livre vindo da origem (ex.: "Não conseguiu pagar")
    perfil_nome: str = ""                 # override explícito (ex.: coluna da planilha); vazio = casar tomador/perguntar
    retencao_pis_cofins_csll: bool | None = None  # None = ainda não perguntado; batch pergunta 1x p/ o lote, manual pergunta por nota
    desconto_incondicionado: float = 0.0  # vDescIncond — abate a base do ISSQN
    desconto_condicionado: float = 0.0    # vDescCond — não abate a base, só o valor líquido
    retencao_cp: float = 0.0              # vRetCP — Contribuição Previdenciária (INSS) retida pelo tomador
    retencao_irrf: float = 0.0            # vRetIRRF
    retencao_csll_outros: float = 0.0     # vRetCSLL (grupo tribFed, distinto do CSLL do bloco PIS/COFINS)
    deducao_valor: float = 0.0            # vDedRed/vDR — dedução/redução simples da base (valor monetário)
    intermediario_nome: str = ""          # interm/xNome — vazio = nota sem intermediário
    intermediario_documento: str = ""     # interm/CPF ou CNPJ, só dígitos
    substituicao_chave: str = ""          # subst/chSubstda — chave (50 dígitos) da NFS-e substituída
    substituicao_motivo: str = ""         # subst/cMotivo — ver es.MOTIVOS_SUBSTITUICAO
    substituicao_motivo_texto: str = ""   # subst/xMotivo — opcional, mín. 15 caracteres se preenchido
    # ---------------------------------------------------------------------------------- IBS/CBS
    # Grupo DPS/infDPS/IBSCBS (reforma tributária) — só é montado quando `incluir_ibscbs=True`.
    # Campos batidos com o XSD oficial de produção restrita/homologação (ver config_schema.py).
    incluir_ibscbs: bool = False
    ibscbs_ind_final: str = ""            # IBSCBS/indFinal — es.IBSCBS_IND_FINAL
    ibscbs_c_ind_op: str = ""             # IBSCBS/cIndOp — código de 6 dígitos (tabela oficial ANEXO_C-INDOP)
    ibscbs_tp_oper: str = ""              # IBSCBS/tpOper — es.IBSCBS_TP_OPER (ente governamental/imóvel)
    ibscbs_tp_ente_gov: str = ""          # IBSCBS/tpEnteGov — es.IBSCBS_TP_ENTE_GOV
    ibscbs_ref_nfse: list = field(default_factory=list)     # IBSCBS/gRefNFSe/refNFSe — chaves de NFS-e referenciadas
    ibscbs_ind_dest: str = "0"            # IBSCBS/indDest — es.IBSCBS_IND_DEST (obrigatório quando incluir_ibscbs)
    # IBSCBS/dest — só quando ibscbs_ind_dest == "1" (destinatário diferente do tomador)
    ibscbs_dest_documento: str = ""       # CNPJ ou CPF do destinatário, só dígitos
    ibscbs_dest_nif: str = ""
    ibscbs_dest_motivo_sem_nif: str = ""  # es.NIF_MOTIVOS
    ibscbs_dest_nome: str = ""
    ibscbs_dest_endereco: dict = field(default_factory=dict)   # cep/logradouro/numero/complemento/bairro/municipio/uf/codigo_municipio_ibge
    ibscbs_dest_telefone: str = ""
    ibscbs_dest_email: str = ""
    # IBSCBS/imovel — operações com bem imóvel (exceto obra), ex.: locação
    ibscbs_imovel_cmun: str = ""          # código IBGE do município do imóvel
    ibscbs_imovel_pcopropriedade: float = 100.0   # gLocacao/pCopropriedade — 100% se só houver um locador
    ibscbs_imovel_vtotoper: float = 0.0           # gLocacao/vTotOper
    ibscbs_imovel_vdescincondtot: float = 0.0     # gLocacao/vDescIncondTot
    ibscbs_imovel_vdesccondtot: float = 0.0       # gLocacao/vDescCondTot
    ibscbs_imovel_dvencorig: str = ""             # gLocacao/dVencOrig — "AAAA-MM-DD"
    # gUnidImob (até 99): cada item {inscimobfisc, cib, endereco{...}, ajustes: [{tipo, descricao, valor}]}
    # endereco (quando não há cib): cep/logradouro/numero/complemento/bairro — TCEnderImovel
    ibscbs_unidades_imobiliarias: list = field(default_factory=list)
    # bensMoveis (até 1000): cada item {ncm, descricao, quantidade} — bens móveis objeto de locação
    ibscbs_bens_moveis: list = field(default_factory=list)
    # IBSCBS/valores/trib — tributação do IBS/CBS (obrigatório quando incluir_ibscbs)
    ibscbs_cst: str = ""                  # CST — es.CST_IBSCBS / dados_oficiais.cst_ibscbs
    ibscbs_cclasstrib: str = ""           # cClassTrib — sugerido pelo Anexo VIII (não oficial), sempre editável
    ibscbs_c_cred_pres: str = ""          # gIBSCBS/cCredPres — código do crédito presumido (2 dígitos)
    ibscbs_cst_reg: str = ""              # gTribRegular/CSTReg — tributação regular alternativa (operações com diferimento)
    ibscbs_cclasstrib_reg: str = ""       # gTribRegular/cClassTribReg
    ibscbs_p_dif_uf: float = 0.0          # gDif/pDifUF — percentual de diferimento do IBS estadual
    ibscbs_p_dif_mun: float = 0.0         # gDif/pDifMun
    ibscbs_p_dif_cbs: float = 0.0         # gDif/pDifCBS
    obra_codigo: str = ""                 # serv/obra/cObra — CNO ou CEI do INSS (serviço de construção civil)
    obra_cib: str = ""                    # serv/obra/cCIB — Cadastro Imobiliário Brasileiro
    obra_inscricao_imobiliaria: str = ""   # serv/obra/inscImobFisc — opcional, junto de cObra/cCIB/endereço
    # serv/obra/end — alternativa a cObra/cCIB: o endereço do imóvel da obra (nacional, CEP+logradouro)
    obra_end_cep: str = ""
    obra_end_logradouro: str = ""
    obra_end_numero: str = ""
    obra_end_complemento: str = ""
    obra_end_bairro: str = ""
    # serv/obra/end/endExt — endereço da obra no exterior (alternativa ao CEP nacional acima)
    obra_end_postal_exterior: str = ""
    obra_end_cidade_exterior: str = ""
    obra_end_estado_exterior: str = ""
    exportacao_moeda: str = ""            # serv/comExt/tpMoeda — código NUMÉRICO de 3 dígitos da tabela do Banco
                                           # Central (não é o código ISO de letras, ex. "USD"); vazio = nota nacional
    exportacao_valor_moeda: float = 0.0   # serv/comExt/vServMoeda
    origem: str = "manual"
    linha_origem: int = 0                 # linha na planilha/documento, para apontar erros; 0 = manual
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    excluir: bool = False                 # não gera nota (ex.: valor zerado); editável na prévia
    motivo_exclusao: str = ""

    def __post_init__(self):
        self.tomador_documento = _so_digitos(self.tomador_documento)
        self.intermediario_documento = _so_digitos(self.intermediario_documento)
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
        if self.tipo_documento == "" and not self.nif and not self.motivo_sem_nif:
            erros.append("Documento do tomador inválido (precisa de CPF, CNPJ, NIF ou motivo de ausência de NIF)")
        if not re.match(r"^\d{4}-\d{2}$", self.competencia or ""):
            erros.append("Competência inválida (use AAAA-MM)")
        if self.valor < 0:
            erros.append("Valor negativo")
        if self.incluir_ibscbs:
            if not self.ibscbs_cst:
                erros.append("IBS/CBS: falta o CST")
            if not self.ibscbs_cclasstrib:
                erros.append("IBS/CBS: falta o cClassTrib")
            if self.ibscbs_ind_dest == "1" and not self.ibscbs_dest_nome.strip():
                erros.append("IBS/CBS: destinatário diferente do tomador precisa de nome")
        return erros
