"""Tela de emissão de notas: lançar (manual, planilha ou documento do cliente), conferir e
transmitir de verdade (assinatura + POST /nfse ao Sefin Nacional). Aberta pelo botão "Emitir Notas"
do cartão da empresa (ver app.py), ao lado do botão "Configurar para Emissão de Notas" (Dev A).

Enquanto `transmissao.PRODUCAO_REAL_LIBERADA` for False, toda transmissão sai em homologação/
produção restrita (`transmissao.ambiente_ativo()`), nunca em produção real — só o Abner liga isso,
depois de testar. Cada nota é conferida (`DialogoConferenciaNota`) antes de ser enviada."""
import datetime as dt
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from . import core, ui
from .core import ErroAdge
from .emissao import arquivo, assinatura, config_schema as es, dps, eventos, historico, transmissao
from .emissao import dados_oficiais as do
from .emissao import importador_documento as impdoc
from .emissao import planilha_emissao as pe
from .emissao import previa, regras
from .emissao.lancamento import Lancamento
from .emissao.ui_configuracao import campo_busca, campo_rotulado, caixa_texto
from .store import Armazenamento
from .ui import P, Botao, Campo, Cartao, Interruptor, Modal, Rolavel, Segmentado, F, px, rotulo

STATUS_TEXTO = {previa.PRONTO: "Pronto", previa.PRECISA_PERFIL: "Precisa de perfil", previa.EXCLUIDO: "Excluído"}
COLUNAS = (("tomador", "Tomador", 220, "w"), ("documento", "Documento", 130, "w"), ("valor", "Valor", 100, "e"),
           ("competencia", "Competência", 100, "w"), ("perfil", "Perfil", 180, "w"), ("status", "Situação", 140, "w"))


def moeda(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _mes_atual() -> str:
    hoje = dt.date.today()
    return f"{hoje.year:04d}-{hoje.month:02d}"


class DialogoEmissao(Modal):
    def __init__(self, pai, store: Armazenamento, emp: dict):
        super().__init__(pai, f"Emitir notas — {emp['nome']}", margem=22)
        self.store, self.emp = store, dict(emp)
        self.emissao_cfg = self.emp.get("emissao") or {}
        self.lancamentos = []
        self.itens = []
        self._status_transmissao = {}  # lancamento.id -> (sucesso: bool, mensagem: str)
        self.resizable(True, True)
        self._montar()
        tela_h = self.winfo_screenheight()
        self.geometry(f"{px(980)}x{min(px(760), tela_h - px(90))}")
        self.minsize(px(820), px(560))
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda *_: self.destroy())
        self.mostrar()

    # ------------------------------------------------------------------ montagem
    def _montar(self):
        ui.titulo(self, f"Emitir notas — {self.emp['nome']}",
                  "Lance as notas do mês e confira tudo antes de transmitir.").pack(anchor="w", pady=(0, 10))
        if not self.emissao_cfg.get("perfis"):
            rotulo(self, 'Esta empresa ainda não tem nenhum "perfil de serviço" configurado. '
                        'Abra "Configurar para Emissão de Notas" no cartão da empresa primeiro.',
                  10, cor="erro", largura=px(880)).pack(anchor="w", pady=(0, 10))

        self.v_aba = tk.StringVar(value="manual")
        Segmentado(self, [("manual", "Digitar"), ("planilha", "Planilha"), ("documento", "Documento do cliente")],
                  self.v_aba, self._trocar_aba).pack(anchor="w", pady=(0, 10))
        self.area = tk.Frame(self, bg=P.fundo)
        self.area.pack(fill="x")
        self.f_manual = self._aba_manual(self.area)
        self.f_planilha = self._aba_planilha(self.area)
        self.f_documento = self._aba_documento(self.area)
        self.f_manual.pack(fill="x")

        ui.secao(self, "Prévia — nada é transmitido sem confirmar aqui").pack(anchor="w", pady=(14, 6))
        self._montar_tabela()

        rodape = tk.Frame(self, bg=P.fundo)
        rodape.pack(fill="x", pady=(10, 0))
        Botao(rodape, "Fechar", self.destroy).pack(side="right")
        Botao(rodape, "Notas emitidas / cancelar", self._abrir_historico, estilo="secundario").pack(side="right", padx=(0, 8))
        Botao(rodape, "Excluir selecionada(s)", self._excluir_selecao).pack(side="right", padx=(0, 8))
        Botao(rodape, "Definir perfil da selecionada", self._definir_perfil, estilo="secundario").pack(side="right", padx=(0, 8))
        self.b_transmitir = Botao(rodape, "Transmitir notas prontas", self._transmitir, estilo="primario")
        self.b_transmitir.pack(side="left")
        ambiente_txt = ("PRODUÇÃO REAL" if transmissao.ambiente_ativo() == transmissao.TP_AMB_PRODUCAO
                        else "homologação/produção restrita")
        rotulo(rodape, f"Ambiente ativo: {ambiente_txt}.", 9, cor="suave").pack(side="left", padx=(10, 0))

    def _trocar_aba(self):
        abas = {"manual": self.f_manual, "planilha": self.f_planilha, "documento": self.f_documento}
        for nome, f in abas.items():
            (f.pack(fill="x") if nome == self.v_aba.get() else f.pack_forget())

    # ------------------------------------------------------------------ aba: digitar (assistente passo a passo)
    ETAPAS_ASSISTENTE = [("tomador", "1. Tomador"), ("perfil", "2. Perfil"), ("dados", "3. Dados da nota"),
                         ("ibscbs", "4. IBS/CBS"), ("revisao", "5. Revisão")]

    def _aba_manual(self, pai):
        f = tk.Frame(pai, bg=P.fundo)
        v = lambda x="": tk.StringVar(value=x)
        self._tomadores_por_nome = {t.get("nome") or "(sem nome)": t for t in self.emissao_cfg.get("tomadores", [])}
        self._perfis_por_nome = {p.get("nome") or "(sem nome)": p for p in self.emissao_cfg.get("perfis", [])}
        self.v_assist_tomador = tk.StringVar(value="(novo tomador)")
        self.v_nome, self.v_doc, self.v_end = v(), v(), v()
        self.v_estrangeiro = tk.BooleanVar(value=False)
        self.v_nif = v()
        self.v_motivo_sem_nif = v()
        self.v_assist_perfil = tk.StringVar(value=next(iter(self._perfis_por_nome), ""))
        self.v_valor, self.v_comp, self.v_data, self.v_obs = v(), v(_mes_atual()), v(), v()
        self.v_retencao_pc = v("Perguntar automaticamente")
        self.v_mostrar_avancado = tk.BooleanVar(value=False)
        self.v_desc_incond, self.v_desc_cond, self.v_deducao = v(), v(), v()
        self.v_ret_cp, self.v_ret_irrf, self.v_ret_csll = v(), v(), v()
        self.v_interm_nome, self.v_interm_doc = v(), v()
        self.v_subst_chave, self.v_subst_motivo = v(), v()
        self.v_obra_codigo, self.v_obra_cib, self.v_obra_insc = v(), v(), v()
        self.v_obra_end_cep, self.v_obra_end_log, self.v_obra_end_num = v(), v(), v()
        self.v_obra_end_compl, self.v_obra_end_bairro = v(), v()
        self.v_obra_exterior = tk.BooleanVar(value=False)
        self.v_obra_end_postal_ext, self.v_obra_end_cidade_ext, self.v_obra_end_estado_ext = v(), v(), v()
        self.v_export_moeda, self.v_export_valor = v(), v()
        self.v_ibscbs = v("Não")
        self.v_ibscbs_cclasstrib = v()
        self.v_ibscbs_sugestao = v("")
        self.v_ibscbs_ind_dest = tk.BooleanVar(value=False)
        self.v_ibscbs_dest_doc, self.v_ibscbs_dest_nome = v(), v()
        self.v_ibscbs_imovel = tk.BooleanVar(value=False)
        self.v_ibscbs_imovel_mun, self.v_ibscbs_imovel_valor, self.v_ibscbs_imovel_cop = v(), v(), v("100")
        self.v_ibscbs_unid_insc, self.v_ibscbs_unid_cib = v(), v()
        self.v_ibscbs_unid_cep, self.v_ibscbs_unid_log, self.v_ibscbs_unid_num = v(), v(), v()
        self.v_ibscbs_unid_compl, self.v_ibscbs_unid_bairro = v(), v()
        self._ibscbs_ajustes = []   # [(tipo_var, valor_var, frame)]
        self._ibscbs_bens_moveis = []  # [(ncm_var, desc_var, qtd_var, frame)]

        self.v_etapa_assistente = tk.StringVar(value="tomador")
        Segmentado(f, self.ETAPAS_ASSISTENTE, self.v_etapa_assistente, self._trocar_etapa_assistente).pack(
            anchor="w", pady=(0, 10))
        self.area_assistente = Rolavel(f)
        self.area_assistente.pack(fill="both", expand=True)
        corpo = self.area_assistente.corpo
        self._etapas_assistente = {
            "tomador": self._etapa_tomador(corpo), "perfil": self._etapa_perfil(corpo),
            "dados": self._etapa_dados(corpo), "ibscbs": self._etapa_ibscbs(corpo),
            "revisao": self._etapa_revisao(corpo),
        }
        self._etapas_assistente["tomador"].pack(fill="x")
        self.v_assist_tomador.trace_add("write", lambda *_: self._atualizar_etapa_tomador())
        self._atualizar_etapa_tomador()
        return f

    def _trocar_etapa_assistente(self):
        etapa = self.v_etapa_assistente.get()
        for nome, fr in self._etapas_assistente.items():
            (fr.pack(fill="x") if nome == etapa else fr.pack_forget())
        if etapa == "revisao":
            self._atualizar_revisao()

    # ---- etapa 1: tomador
    def _etapa_tomador(self, pai):
        f = Cartao(pai)
        c = f.corpo
        c.columnconfigure(0, weight=1)
        nomes = ["(novo tomador)"] + list(self._tomadores_por_nome)
        rotulo(c, "Tomador cadastrado", 9, "bold", "suave").grid(row=0, column=0, sticky="w", pady=(0, 3))
        ttk.Combobox(c, textvariable=self.v_assist_tomador, values=nomes, state="readonly", width=40, font=F(10)).grid(
            row=1, column=0, sticky="ew", pady=(0, 10))
        self.f_tomador_novo = tk.Frame(c, bg=P.superficie)
        self.f_tomador_novo.grid(row=2, column=0, sticky="ew")
        self.f_tomador_novo.columnconfigure(0, weight=1)
        campo_rotulado(self.f_tomador_novo, 0, "Nome", Campo(self.f_tomador_novo, self.v_nome, largura=40))
        campo_rotulado(self.f_tomador_novo, 3, "Documento (CPF ou CNPJ)", Campo(self.f_tomador_novo, self.v_doc, largura=22))
        campo_rotulado(self.f_tomador_novo, 6, "Endereço", Campo(self.f_tomador_novo, self.v_end, largura=40),
                       dica="Opcional, mas obrigatório se não tiver documento, NIF ou motivo de ausência de NIF.")
        Interruptor(self.f_tomador_novo, "Tomador estrangeiro, sem CPF/CNPJ", self.v_estrangeiro,
                   self._atualizar_estrangeiro).grid(row=9, column=0, sticky="w", pady=(10, 0))
        self.f_estrangeiro = tk.Frame(self.f_tomador_novo, bg=P.superficie)
        self.f_estrangeiro.grid(row=10, column=0, sticky="ew")
        self.f_estrangeiro.columnconfigure(0, weight=1)
        campo_rotulado(self.f_estrangeiro, 0, "NIF (identificação fiscal no exterior)", Campo(self.f_estrangeiro, self.v_nif, largura=30),
                       dica="Deixe vazio e escolha um motivo abaixo se o tomador não tiver NIF.")
        rotulo(self.f_estrangeiro, "Sem NIF — motivo", 9, "bold", "suave").grid(row=3, column=0, sticky="w", pady=(10, 3))
        ttk.Combobox(self.f_estrangeiro, textvariable=self.v_motivo_sem_nif, values=list(es.NIF_MOTIVOS.values()),
                    state="readonly", width=40, font=F(10)).grid(row=4, column=0, sticky="ew")
        self.f_estrangeiro.grid_remove()
        self.l_tomador_cadastrado = rotulo(c, "", 10, cor="suave", largura=px(560))
        self.l_tomador_cadastrado.grid(row=2, column=0, sticky="w")
        return f

    def _atualizar_estrangeiro(self):
        (self.f_estrangeiro.grid if self.v_estrangeiro.get() else self.f_estrangeiro.grid_remove)()

    def _atualizar_etapa_tomador(self):
        novo = self.v_assist_tomador.get() == "(novo tomador)"
        if novo:
            self.f_tomador_novo.grid()
            self.l_tomador_cadastrado.grid_remove()
        else:
            self.f_tomador_novo.grid_remove()
            t = self._tomadores_por_nome.get(self.v_assist_tomador.get(), {})
            ref = t.get("documento") or es.endereco_completo(t) or "—"
            self.l_tomador_cadastrado.configure(text=f"Documento/endereço: {ref}")
            self.l_tomador_cadastrado.grid()
            perfil_id = t.get("perfil_id")
            nome_perfil = next((n for n, p in self._perfis_por_nome.items() if p["id"] == perfil_id), None)
            if nome_perfil:
                self.v_assist_perfil.set(nome_perfil)

    # ---- etapa 2: perfil
    def _etapa_perfil(self, pai):
        f = Cartao(pai)
        c = f.corpo
        c.columnconfigure(0, weight=1)
        rotulo(c, "Perfil de serviço", 9, "bold", "suave").grid(row=0, column=0, sticky="w", pady=(0, 3))
        if not self._perfis_por_nome:
            rotulo(c, "Esta empresa não tem nenhum perfil cadastrado.", 10, cor="erro").grid(row=1, column=0, sticky="w")
        else:
            ttk.Combobox(c, textvariable=self.v_assist_perfil, values=list(self._perfis_por_nome), state="readonly",
                        width=40, font=F(10)).grid(row=1, column=0, sticky="ew")
            rotulo(c, "Sugerido pelo tomador escolhido; pode trocar aqui.", 9, cor="suave").grid(
                row=2, column=0, sticky="w", pady=(2, 0))
        return f

    # ---- etapa 3: dados da nota
    def _etapa_dados(self, pai):
        f = Cartao(pai)
        c = f.corpo
        c.columnconfigure(0, weight=1)
        c.columnconfigure(1, weight=1)
        campo_rotulado(c, 0, "Valor", Campo(c, self.v_valor, largura=18), col=0, columnspan=1)
        campo_rotulado(c, 0, "Competência (AAAA-MM)", Campo(c, self.v_comp, largura=18), col=1, columnspan=1)
        campo_rotulado(c, 3, "Data da prestação (opcional)", Campo(c, self.v_data, largura=18), col=0, columnspan=1)
        rotulo(c, "Retenção de PIS/COFINS/CSLL", 9, "bold", "suave").grid(row=3, column=1, sticky="w", pady=(10, 3))
        ttk.Combobox(c, textvariable=self.v_retencao_pc, values=["Perguntar automaticamente", "Sim", "Não"],
                    state="readonly", width=24, font=F(10)).grid(row=4, column=1, sticky="ew")
        campo_rotulado(c, 6, "Observações", Campo(c, self.v_obs, largura=46))
        Interruptor(c, "Mais opções (desconto, retenções, intermediário, substituição de nota)",
                   self.v_mostrar_avancado, self._atualizar_avancado).grid(row=9, column=0, columnspan=2, sticky="w", pady=(14, 0))
        self.f_avancado = tk.Frame(c, bg=P.superficie)
        self.f_avancado.grid(row=10, column=0, columnspan=2, sticky="ew")
        self.f_avancado.columnconfigure(0, weight=1)
        self.f_avancado.columnconfigure(1, weight=1)
        campo_rotulado(self.f_avancado, 0, "Desconto incondicionado (R$)", Campo(self.f_avancado, self.v_desc_incond, largura=16), col=0, columnspan=1)
        campo_rotulado(self.f_avancado, 0, "Desconto condicionado (R$)", Campo(self.f_avancado, self.v_desc_cond, largura=16), col=1, columnspan=1)
        campo_rotulado(self.f_avancado, 3, "Dedução da base (R$)", Campo(self.f_avancado, self.v_deducao, largura=16), col=0, columnspan=1,
                       dica="Valor simples (vDR); não cobre a lista detalhada de documentos de dedução.")
        campo_rotulado(self.f_avancado, 6, "Retenção de CP/INSS (R$)", Campo(self.f_avancado, self.v_ret_cp, largura=16), col=0, columnspan=1)
        campo_rotulado(self.f_avancado, 6, "Retenção de IRRF (R$)", Campo(self.f_avancado, self.v_ret_irrf, largura=16), col=1, columnspan=1)
        campo_rotulado(self.f_avancado, 9, "Retenção de CSLL (R$)", Campo(self.f_avancado, self.v_ret_csll, largura=16), col=0, columnspan=1)
        rotulo(self.f_avancado, "Intermediário do serviço (opcional)", 9, "bold", "suave").grid(
            row=12, column=0, columnspan=2, sticky="w", pady=(10, 3))
        campo_rotulado(self.f_avancado, 13, "Nome do intermediário", Campo(self.f_avancado, self.v_interm_nome, largura=30), col=0, columnspan=1)
        campo_rotulado(self.f_avancado, 13, "CPF ou CNPJ do intermediário", Campo(self.f_avancado, self.v_interm_doc, largura=22), col=1, columnspan=1)
        rotulo(self.f_avancado, "Substituição de NFS-e (corrigir nota já emitida)", 9, "bold", "suave").grid(
            row=16, column=0, columnspan=2, sticky="w", pady=(10, 3))
        campo_rotulado(self.f_avancado, 17, "Chave da nota substituída (50 dígitos)", Campo(self.f_avancado, self.v_subst_chave, largura=46))
        rotulo(self.f_avancado, "Motivo da substituição", 9, "bold", "suave").grid(row=19, column=0, columnspan=2, sticky="w", pady=(10, 3))
        ttk.Combobox(self.f_avancado, textvariable=self.v_subst_motivo, values=list(es.MOTIVOS_SUBSTITUICAO.values()),
                    state="readonly", width=60, font=F(10)).grid(row=20, column=0, columnspan=2, sticky="ew")
        self.caixa_subst_texto = caixa_texto(self.f_avancado, altura=2, largura=60)
        rotulo(self.f_avancado, "Detalhe do motivo (opcional, mín. 15 caracteres se preencher)", 9, cor="suave").grid(
            row=21, column=0, columnspan=2, sticky="w", pady=(8, 2))
        self.caixa_subst_texto.grid(row=22, column=0, columnspan=2, sticky="ew")
        rotulo(self.f_avancado, "Obra/imóvel (só serviço de construção civil)", 9, "bold", "suave").grid(
            row=23, column=0, columnspan=2, sticky="w", pady=(10, 3))
        rotulo(self.f_avancado, "Preencha CNO/CEI OU CIB OU o endereço da obra — só um dos três.",
              9, cor="suave", largura=px(560)).grid(row=24, column=0, columnspan=2, sticky="w", pady=(0, 3))
        campo_rotulado(self.f_avancado, 25, "CNO/CEI da obra (INSS)", Campo(self.f_avancado, self.v_obra_codigo, largura=22), col=0, columnspan=1)
        campo_rotulado(self.f_avancado, 25, "CIB (8 caracteres)", Campo(self.f_avancado, self.v_obra_cib, largura=10), col=1, columnspan=1)
        campo_rotulado(self.f_avancado, 28, "Inscrição imobiliária/IPTU (opcional)", Campo(self.f_avancado, self.v_obra_insc, largura=22))
        rotulo(self.f_avancado, "Endereço da obra (alternativa ao CNO/CEI/CIB acima)", 9, cor="suave").grid(
            row=31, column=0, columnspan=2, sticky="w", pady=(6, 3))
        Interruptor(self.f_avancado, "Obra no exterior", self.v_obra_exterior, self._atualizar_obra_exterior).grid(
            row=32, column=0, columnspan=2, sticky="w")
        self.f_obra_end_nacional = tk.Frame(self.f_avancado, bg=P.superficie)
        self.f_obra_end_nacional.grid(row=33, column=0, columnspan=2, sticky="ew")
        self.f_obra_end_nacional.columnconfigure(0, weight=1)
        self.f_obra_end_nacional.columnconfigure(1, weight=1)
        campo_rotulado(self.f_obra_end_nacional, 0, "CEP", Campo(self.f_obra_end_nacional, self.v_obra_end_cep, largura=12), col=0, columnspan=1)
        campo_rotulado(self.f_obra_end_nacional, 0, "Número", Campo(self.f_obra_end_nacional, self.v_obra_end_num, largura=12), col=1, columnspan=1)
        campo_rotulado(self.f_obra_end_nacional, 3, "Logradouro", Campo(self.f_obra_end_nacional, self.v_obra_end_log, largura=40))
        self.f_obra_end_exterior = tk.Frame(self.f_avancado, bg=P.superficie)
        self.f_obra_end_exterior.grid(row=34, column=0, columnspan=2, sticky="ew")
        self.f_obra_end_exterior.columnconfigure(0, weight=1)
        campo_rotulado(self.f_obra_end_exterior, 0, "Código postal no exterior", Campo(self.f_obra_end_exterior, self.v_obra_end_postal_ext, largura=22))
        campo_rotulado(self.f_obra_end_exterior, 3, "Cidade no exterior", Campo(self.f_obra_end_exterior, self.v_obra_end_cidade_ext, largura=30))
        campo_rotulado(self.f_obra_end_exterior, 6, "Estado/província/região", Campo(self.f_obra_end_exterior, self.v_obra_end_estado_ext, largura=30))
        self.f_obra_end_exterior.grid_remove()
        campo_rotulado(self.f_avancado, 36, "Complemento", Campo(self.f_avancado, self.v_obra_end_compl, largura=40), col=0, columnspan=1)
        campo_rotulado(self.f_avancado, 36, "Bairro", Campo(self.f_avancado, self.v_obra_end_bairro, largura=22), col=1, columnspan=1)
        rotulo(self.f_avancado, "Exportação de serviço (moeda estrangeira)", 9, "bold", "suave").grid(
            row=39, column=0, columnspan=2, sticky="w", pady=(10, 3))
        campo_rotulado(self.f_avancado, 40, "Moeda", campo_busca(self.f_avancado, self.v_export_moeda, do.buscar_moeda, largura=28),
                       col=0, columnspan=1, dica="Busque por nome (ex. \"dólar\"), código (USD) ou número (840).")
        campo_rotulado(self.f_avancado, 40, "Valor na moeda estrangeira", Campo(self.f_avancado, self.v_export_valor, largura=16), col=1, columnspan=1)
        self.f_avancado.grid_remove()
        return f

    def _atualizar_obra_exterior(self):
        if self.v_obra_exterior.get():
            self.f_obra_end_nacional.grid_remove()
            self.f_obra_end_exterior.grid()
        else:
            self.f_obra_end_exterior.grid_remove()
            self.f_obra_end_nacional.grid()

    def _atualizar_avancado(self):
        (self.f_avancado.grid if self.v_mostrar_avancado.get() else self.f_avancado.grid_remove)()

    # ---- etapa 4: IBS/CBS
    def _etapa_ibscbs(self, pai):
        f = Cartao(pai)
        c = f.corpo
        rotulo(c, "IBS/CBS (reforma tributária)", 12, "bold", "verde_escuro").pack(anchor="w")
        rotulo(c, "Grupo opcional da DPS, validado contra o leiaute de produção restrita/homologação "
                  "(ainda não é o de produção vigente). Deixe em \"Não\" enquanto isso não entrar em produção.",
              10, cor="suave", largura=px(620)).pack(anchor="w", pady=(4, 10))
        ttk.Combobox(c, textvariable=self.v_ibscbs, values=["Não", "Sim"], state="readonly", width=12, font=F(10)).pack(anchor="w")
        self.f_ibscbs_corpo = tk.Frame(c, bg=P.superficie)
        self.f_ibscbs_corpo.pack(fill="x", pady=(10, 0))
        self.v_ibscbs.trace_add("write", lambda *_: self._atualizar_ibscbs())

        g = self.f_ibscbs_corpo
        g.columnconfigure(0, weight=1)
        g.columnconfigure(1, weight=1)
        rotulo(g, "Tributação do IBS/CBS", 9, "bold", "suave").grid(row=0, column=0, columnspan=2, sticky="w")
        campo_rotulado(g, 1, "cClassTrib", campo_busca(g, self.v_ibscbs_cclasstrib, do.buscar_cclasstrib, largura=40,
                       ao_escolher=self._ao_escolher_cclasstrib), col=0, columnspan=2,
                       dica="Sugestão vem do Anexo VIII da Receita (referência não oficial) a partir do NBS do perfil "
                            "escolhido; sempre editável. O CST correspondente é preenchido sozinho.")
        self.l_ibscbs_sugestao = rotulo(g, "", 9, cor="suave", largura=px(560))
        self.l_ibscbs_sugestao.grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 10))

        Interruptor(g, "Destinatário diferente do tomador", self.v_ibscbs_ind_dest, self._atualizar_ibscbs_dest).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.f_ibscbs_dest = tk.Frame(g, bg=P.superficie)
        self.f_ibscbs_dest.grid(row=5, column=0, columnspan=2, sticky="ew")
        self.f_ibscbs_dest.columnconfigure(0, weight=1)
        self.f_ibscbs_dest.columnconfigure(1, weight=1)
        campo_rotulado(self.f_ibscbs_dest, 0, "Nome do destinatário", Campo(self.f_ibscbs_dest, self.v_ibscbs_dest_nome, largura=30), col=0, columnspan=1)
        campo_rotulado(self.f_ibscbs_dest, 0, "CPF ou CNPJ", Campo(self.f_ibscbs_dest, self.v_ibscbs_dest_doc, largura=22), col=1, columnspan=1)
        self.f_ibscbs_dest.grid_remove()

        Interruptor(g, "Operação com bem imóvel (ex.: locação) — necessário para o redutor social",
                   self.v_ibscbs_imovel, self._atualizar_ibscbs_imovel).grid(row=6, column=0, columnspan=2, sticky="w", pady=(10, 4))
        self.f_ibscbs_imovel = tk.Frame(g, bg=P.superficie)
        self.f_ibscbs_imovel.grid(row=7, column=0, columnspan=2, sticky="ew")
        gi = self.f_ibscbs_imovel
        gi.columnconfigure(0, weight=1)
        gi.columnconfigure(1, weight=1)
        campo_rotulado(gi, 0, "Município do imóvel", campo_busca(gi, self.v_ibscbs_imovel_mun, do.buscar_municipio, largura=28),
                       col=0, columnspan=1)
        campo_rotulado(gi, 0, "% de copropriedade", Campo(gi, self.v_ibscbs_imovel_cop, largura=10), col=1, columnspan=1,
                       dica="100% se só houver um locador/cedente/arrendador.")
        campo_rotulado(gi, 3, "Valor total da operação (R$)", Campo(gi, self.v_ibscbs_imovel_valor, largura=18))
        rotulo(gi, "Unidade imobiliária", 9, "bold", "suave").grid(row=6, column=0, columnspan=2, sticky="w", pady=(10, 3))
        campo_rotulado(gi, 7, "Inscrição imobiliária/IPTU (opcional)", Campo(gi, self.v_ibscbs_unid_insc, largura=22), col=0, columnspan=1)
        campo_rotulado(gi, 7, "CIB (8 caracteres, se tiver)", Campo(gi, self.v_ibscbs_unid_cib, largura=12), col=1, columnspan=1)
        rotulo(gi, "Sem CIB, informe o endereço do imóvel:", 9, cor="suave").grid(row=10, column=0, columnspan=2, sticky="w", pady=(4, 2))
        campo_rotulado(gi, 11, "CEP", Campo(gi, self.v_ibscbs_unid_cep, largura=12), col=0, columnspan=1)
        campo_rotulado(gi, 11, "Número", Campo(gi, self.v_ibscbs_unid_num, largura=12), col=1, columnspan=1)
        campo_rotulado(gi, 14, "Logradouro", Campo(gi, self.v_ibscbs_unid_log, largura=40))
        campo_rotulado(gi, 17, "Complemento", Campo(gi, self.v_ibscbs_unid_compl, largura=22), col=0, columnspan=1)
        campo_rotulado(gi, 17, "Bairro", Campo(gi, self.v_ibscbs_unid_bairro, largura=22), col=1, columnspan=1)
        rotulo(gi, "Ajustes da base de cálculo (ex.: redutor social, IPTU incluso)", 9, "bold", "suave").grid(
            row=20, column=0, columnspan=2, sticky="w", pady=(12, 3))
        self.f_ibscbs_ajustes = tk.Frame(gi, bg=P.superficie)
        self.f_ibscbs_ajustes.grid(row=21, column=0, columnspan=2, sticky="ew")
        self.f_ibscbs_ajustes.columnconfigure(0, weight=1)
        Botao(gi, "+ Adicionar ajuste", lambda: self._adicionar_linha_ajuste(), estilo="suave").grid(
            row=22, column=0, sticky="w", pady=(4, 0))
        self.f_ibscbs_imovel.grid_remove()

        rotulo(g, "Bens móveis objeto de locação (opcional)", 9, "bold", "suave").grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(14, 3))
        self.f_ibscbs_bens = tk.Frame(g, bg=P.superficie)
        self.f_ibscbs_bens.grid(row=9, column=0, columnspan=2, sticky="ew")
        self.f_ibscbs_bens.columnconfigure(0, weight=1)
        Botao(g, "+ Adicionar bem móvel", lambda: self._adicionar_linha_bem_movel(), estilo="suave").grid(
            row=10, column=0, sticky="w", pady=(4, 0))

        self.f_ibscbs_corpo.pack_forget()
        return f

    def _atualizar_ibscbs(self):
        if self.v_ibscbs.get() == "Sim":
            self.f_ibscbs_corpo.pack(fill="x", pady=(10, 0))
            self._sugerir_cclasstrib_do_perfil()
        else:
            self.f_ibscbs_corpo.pack_forget()

    def _ao_escolher_cclasstrib(self):
        reg = do.cclasstrib_por_texto_formatado(self.v_ibscbs_cclasstrib.get())
        if not reg:
            self.l_ibscbs_sugestao.configure(text="")
            return
        info = do.info_legal_cclasstrib(reg["cclasstrib"])
        partes = [f"CST: {reg['cst']}"]
        if info.get("p_red_ibs") or info.get("p_red_cbs"):
            partes.append(f"Redução: IBS {info.get('p_red_ibs', 0)}% / CBS {info.get('p_red_cbs', 0)}%")
        if info.get("link_lei"):
            partes.append(f"Base legal: {info['link_lei']}")
        self.l_ibscbs_sugestao.configure(text=" — ".join(partes))

    def _sugerir_cclasstrib_do_perfil(self):
        perfil = self._perfis_por_nome.get(self.v_assist_perfil.get())
        if not perfil or not perfil.get("nbs"):
            return
        sugestoes = do.sugerir_cclasstrib_por_nbs(perfil["nbs"])
        if sugestoes and not self.v_ibscbs_cclasstrib.get():
            self.v_ibscbs_cclasstrib.set(sugestoes[0])
            self._ao_escolher_cclasstrib()

    def _atualizar_ibscbs_dest(self):
        (self.f_ibscbs_dest.grid if self.v_ibscbs_ind_dest.get() else self.f_ibscbs_dest.grid_remove)()

    def _atualizar_ibscbs_imovel(self):
        (self.f_ibscbs_imovel.grid if self.v_ibscbs_imovel.get() else self.f_ibscbs_imovel.grid_remove)()

    def _adicionar_linha_ajuste(self, tipo="04", valor=""):
        linha = tk.Frame(self.f_ibscbs_ajustes, bg=P.superficie)
        linha.pack(fill="x", pady=(0, 4))
        v_tipo = tk.StringVar(value=es.IBSCBS_TP_AJUSTE_BC_LOC_IMOVEIS.get(tipo, next(iter(es.IBSCBS_TP_AJUSTE_BC_LOC_IMOVEIS.values()))))
        v_valor = tk.StringVar(value=valor)
        ttk.Combobox(linha, textvariable=v_tipo, values=list(es.IBSCBS_TP_AJUSTE_BC_LOC_IMOVEIS.values()),
                    state="readonly", width=46, font=F(10)).pack(side="left")
        Campo(linha, v_valor, largura=14).pack(side="left", padx=(6, 0))
        item = [v_tipo, v_valor, linha]
        Botao(linha, "Remover", lambda: self._remover_linha(self._ibscbs_ajustes, item), estilo="suave").pack(side="left", padx=(6, 0))
        self._ibscbs_ajustes.append(item)

    def _adicionar_linha_bem_movel(self, ncm="", desc="", qtd="1"):
        linha = tk.Frame(self.f_ibscbs_bens, bg=P.superficie)
        linha.pack(fill="x", pady=(0, 4))
        v_ncm, v_desc, v_qtd = tk.StringVar(value=ncm), tk.StringVar(value=desc), tk.StringVar(value=qtd)
        Campo(linha, v_ncm, largura=10).pack(side="left")
        Campo(linha, v_desc, largura=30).pack(side="left", padx=(6, 0))
        Campo(linha, v_qtd, largura=6).pack(side="left", padx=(6, 0))
        item = [v_ncm, v_desc, v_qtd, linha]
        Botao(linha, "Remover", lambda: self._remover_linha(self._ibscbs_bens_moveis, item), estilo="suave").pack(side="left", padx=(6, 0))
        self._ibscbs_bens_moveis.append(item)

    def _remover_linha(self, lista, item):
        item[-1].destroy()
        lista.remove(item)

    def _coletar_campos_ibscbs(self) -> dict:
        """Monta os kwargs `ibscbs_*` do `Lancamento` a partir do estado da etapa IBS/CBS."""
        nome_para_tp_ajuste = {v: k for k, v in es.IBSCBS_TP_AJUSTE_BC_LOC_IMOVEIS.items()}
        reg_cclasstrib = do.cclasstrib_por_texto_formatado(self.v_ibscbs_cclasstrib.get())
        campos = {
            "ibscbs_cclasstrib": reg_cclasstrib["cclasstrib"] if reg_cclasstrib else "",
            "ibscbs_cst": reg_cclasstrib["cst"] if reg_cclasstrib else "",
            "ibscbs_ind_dest": "1" if self.v_ibscbs_ind_dest.get() else "0",
        }
        if self.v_ibscbs_ind_dest.get():
            campos["ibscbs_dest_nome"] = self.v_ibscbs_dest_nome.get().strip()
            campos["ibscbs_dest_documento"] = self.v_ibscbs_dest_doc.get().strip()
        if self.v_ibscbs_imovel.get():
            municipio = do.municipio_por_texto_formatado(self.v_ibscbs_imovel_mun.get())
            campos["ibscbs_imovel_cmun"] = (municipio or {}).get("codigo_ibge", "")
            campos["ibscbs_imovel_vtotoper"] = pe.valor_numerico(self.v_ibscbs_imovel_valor.get())
            try:
                campos["ibscbs_imovel_pcopropriedade"] = float((self.v_ibscbs_imovel_cop.get() or "100").replace(",", "."))
            except ValueError:
                campos["ibscbs_imovel_pcopropriedade"] = 100.0
            ajustes = [{"tipo": nome_para_tp_ajuste.get(t.get(), "99"), "descricao": "", "valor": pe.valor_numerico(val.get())}
                       for t, val, _ in self._ibscbs_ajustes]
            campos["ibscbs_unidades_imobiliarias"] = [{
                "inscimobfisc": self.v_ibscbs_unid_insc.get().strip(), "cib": self.v_ibscbs_unid_cib.get().strip(),
                "endereco": {"cep": self.v_ibscbs_unid_cep.get().strip(), "logradouro": self.v_ibscbs_unid_log.get().strip(),
                             "numero": self.v_ibscbs_unid_num.get().strip(), "complemento": self.v_ibscbs_unid_compl.get().strip(),
                             "bairro": self.v_ibscbs_unid_bairro.get().strip()},
                "ajustes": ajustes,
            }]
        if self._ibscbs_bens_moveis:
            campos["ibscbs_bens_moveis"] = [
                {"ncm": ncm.get().strip(), "descricao": desc.get().strip(), "quantidade": int(pe.valor_numerico(qtd.get()) or 1)}
                for ncm, desc, qtd, _ in self._ibscbs_bens_moveis]
        return campos

    def _limpar_etapa_ibscbs(self):
        self.v_ibscbs.set("Não")
        self.v_ibscbs_cclasstrib.set("")
        self.l_ibscbs_sugestao.configure(text="")
        self.v_ibscbs_ind_dest.set(False)
        self._atualizar_ibscbs_dest()
        self.v_ibscbs_dest_doc.set("")
        self.v_ibscbs_dest_nome.set("")
        self.v_ibscbs_imovel.set(False)
        self._atualizar_ibscbs_imovel()
        for var in (self.v_ibscbs_imovel_mun, self.v_ibscbs_imovel_valor, self.v_ibscbs_unid_insc, self.v_ibscbs_unid_cib,
                    self.v_ibscbs_unid_cep, self.v_ibscbs_unid_log, self.v_ibscbs_unid_num, self.v_ibscbs_unid_compl,
                    self.v_ibscbs_unid_bairro):
            var.set("")
        self.v_ibscbs_imovel_cop.set("100")
        for item in list(self._ibscbs_ajustes):
            self._remover_linha(self._ibscbs_ajustes, item)
        for item in list(self._ibscbs_bens_moveis):
            self._remover_linha(self._ibscbs_bens_moveis, item)
        self._atualizar_ibscbs()

    # ---- etapa 5: revisão
    def _etapa_revisao(self, pai):
        f = Cartao(pai)
        self.l_revisao = rotulo(f.corpo, "", 10, largura=px(620))
        self.l_revisao.pack(anchor="w")
        Botao(f.corpo, "Adicionar à prévia", self._adicionar_assistente, estilo="primario").pack(anchor="w", pady=(14, 0))
        return f

    def _atualizar_revisao(self):
        if self.v_assist_tomador.get() == "(novo tomador)":
            tomador_txt = self.v_nome.get().strip() or "(sem nome)"
        else:
            tomador_txt = self.v_assist_tomador.get()
        linhas = [
            f"Tomador: {tomador_txt}", f"Perfil: {self.v_assist_perfil.get() or '—'}",
            f"Valor: {self.v_valor.get() or '—'}", f"Competência: {self.v_comp.get() or '—'}",
            f"IBS/CBS: {self.v_ibscbs.get()}" + (f" (cClassTrib {self.v_ibscbs_cclasstrib.get().split(' - ')[0]})"
                                                   if self.v_ibscbs.get() == "Sim" and self.v_ibscbs_cclasstrib.get() else ""),
        ]
        if self.v_mostrar_avancado.get():
            linhas.append("Tem opções avançadas preenchidas (desconto/retenção/intermediário/substituição).")
        self.l_revisao.configure(text="\n".join(linhas))

    # ---- montar e adicionar o lançamento
    def _adicionar_assistente(self):
        nome_para_motivo_subst = {v: k for k, v in es.MOTIVOS_SUBSTITUICAO.items()}
        nome_para_motivo_nif = {v: k for k, v in es.NIF_MOTIVOS.items()}
        nif, motivo_sem_nif = "", ""
        if self.v_assist_tomador.get() == "(novo tomador)":
            nome, doc, end = self.v_nome.get(), self.v_doc.get(), self.v_end.get()
            if self.v_estrangeiro.get():
                nif = self.v_nif.get().strip()
                motivo_sem_nif = nome_para_motivo_nif.get(self.v_motivo_sem_nif.get(), "")
        else:
            tomador_cadastrado = self._tomadores_por_nome.get(self.v_assist_tomador.get(), {})
            nome = tomador_cadastrado.get("nome", "")
            doc = tomador_cadastrado.get("documento", "")
            end = es.endereco_completo(tomador_cadastrado)
        retido = {"Sim": True, "Não": False}.get(self.v_retencao_pc.get())
        perfil = self._perfis_por_nome.get(self.v_assist_perfil.get())
        incluir_ibscbs = self.v_ibscbs.get() == "Sim"
        ibscbs_campos = self._coletar_campos_ibscbs() if incluir_ibscbs else {}
        try:
            lanc = Lancamento(
                tomador_nome=nome, tomador_documento=doc, endereco=end, nif=nif, motivo_sem_nif=motivo_sem_nif,
                valor=pe.valor_numerico(self.v_valor.get()), competencia=self.v_comp.get().strip(),
                data_prestacao=self.v_data.get().strip(), observacoes=self.v_obs.get().strip(),
                perfil_nome=perfil.get("nome", "") if perfil else "",
                retencao_pis_cofins_csll=retido,
                desconto_incondicionado=pe.valor_numerico(self.v_desc_incond.get()),
                desconto_condicionado=pe.valor_numerico(self.v_desc_cond.get()),
                deducao_valor=pe.valor_numerico(self.v_deducao.get()),
                retencao_cp=pe.valor_numerico(self.v_ret_cp.get()),
                retencao_irrf=pe.valor_numerico(self.v_ret_irrf.get()),
                retencao_csll_outros=pe.valor_numerico(self.v_ret_csll.get()),
                intermediario_nome=self.v_interm_nome.get().strip(), intermediario_documento=self.v_interm_doc.get().strip(),
                substituicao_chave=self.v_subst_chave.get().strip(),
                substituicao_motivo=nome_para_motivo_subst.get(self.v_subst_motivo.get(), ""),
                substituicao_motivo_texto=self.caixa_subst_texto.texto.get("1.0", "end-1c").strip(),
                obra_codigo=self.v_obra_codigo.get().strip(), obra_cib=self.v_obra_cib.get().strip(),
                obra_inscricao_imobiliaria=self.v_obra_insc.get().strip(),
                obra_end_cep=self.v_obra_end_cep.get().strip(), obra_end_logradouro=self.v_obra_end_log.get().strip(),
                obra_end_numero=self.v_obra_end_num.get().strip(), obra_end_complemento=self.v_obra_end_compl.get().strip(),
                obra_end_bairro=self.v_obra_end_bairro.get().strip(),
                obra_end_postal_exterior=self.v_obra_end_postal_ext.get().strip(),
                obra_end_cidade_exterior=self.v_obra_end_cidade_ext.get().strip(),
                obra_end_estado_exterior=self.v_obra_end_estado_ext.get().strip(),
                exportacao_moeda=(do.moeda_por_texto_formatado(self.v_export_moeda.get()) or {}).get("codigo_numerico", ""),
                exportacao_valor_moeda=pe.valor_numerico(self.v_export_valor.get()),
                incluir_ibscbs=incluir_ibscbs,
                origem="manual", **ibscbs_campos,
            )
        except ErroAdge as e:
            ui.erro(self, "Não consegui adicionar", str(e))
            return
        erros = lanc.validar()
        if erros:
            ui.erro(self, "Confira os dados", "\n".join(erros))
            return
        self.lancamentos.append(lanc)
        for var in (self.v_nome, self.v_doc, self.v_end, self.v_nif, self.v_motivo_sem_nif, self.v_valor,
                    self.v_data, self.v_obs, self.v_desc_incond, self.v_desc_cond, self.v_deducao, self.v_ret_cp,
                    self.v_ret_irrf, self.v_ret_csll, self.v_interm_nome, self.v_interm_doc, self.v_subst_chave,
                    self.v_subst_motivo, self.v_obra_codigo, self.v_obra_cib, self.v_obra_insc,
                    self.v_obra_end_cep, self.v_obra_end_log, self.v_obra_end_num, self.v_obra_end_compl,
                    self.v_obra_end_bairro, self.v_obra_end_postal_ext, self.v_obra_end_cidade_ext,
                    self.v_obra_end_estado_ext, self.v_export_moeda, self.v_export_valor):
            var.set("")
        self.caixa_subst_texto.texto.delete("1.0", "end")
        self.v_mostrar_avancado.set(False)
        self._atualizar_avancado()
        self.v_estrangeiro.set(False)
        self._atualizar_estrangeiro()
        self.v_obra_exterior.set(False)
        self._atualizar_obra_exterior()
        self.v_assist_tomador.set("(novo tomador)")
        self._limpar_etapa_ibscbs()
        self.v_etapa_assistente.set("tomador")
        self._trocar_etapa_assistente()
        self._atualizar_previa()

    # ------------------------------------------------------------------ aba: planilha
    def _aba_planilha(self, pai):
        f = Cartao(pai)
        c = f.corpo
        rotulo(c, "Uma linha por nota. Baixe o modelo, preencha e importe de volta.", 10, cor="suave",
              largura=px(700)).grid(row=0, column=0, sticky="w", pady=(0, 10))
        linha = tk.Frame(c, bg=P.superficie)
        linha.grid(row=1, column=0, sticky="w")
        Botao(linha, "Baixar modelo (.xlsx)", self._baixar_modelo).pack(side="left")
        Botao(linha, "Importar planilha preenchida", self._importar_planilha, estilo="primario").pack(
            side="left", padx=(8, 0))
        return f

    def _baixar_modelo(self):
        caminho = filedialog.asksaveasfilename(parent=self, defaultextension=".xlsx",
                                               initialfile="Modelo de lançamentos.xlsx",
                                               filetypes=[("Planilha Excel", "*.xlsx")])
        if not caminho:
            return
        pe.gerar_modelo_xlsx(caminho)
        ui.informar(self, "Modelo salvo", f"Modelo salvo em:\n{caminho}")
        ui.abrir_pasta(Path(caminho).parent)

    def _importar_planilha(self):
        caminho = filedialog.askopenfilename(parent=self, filetypes=[("Planilha Excel", "*.xlsx")])
        if not caminho:
            return
        try:
            novos, erros = pe.importar_xlsx(caminho)
        except ErroAdge as e:
            ui.erro(self, "Não consegui importar", str(e))
            return
        self.lancamentos.extend(novos)
        self._atualizar_previa()
        if erros:
            ui.avisar(self, f"{len(novos)} lançamento(s) importado(s), com avisos", "\n".join(erros))
        else:
            ui.informar(self, "Importado", f"{len(novos)} lançamento(s) adicionado(s) à prévia.")

    # ------------------------------------------------------------------ aba: documento do cliente
    def _aba_documento(self, pai):
        f = Cartao(pai)
        c = f.corpo
        rotulo(c, "Qualquer documento do cliente com uma tabela (PDF, .xlsx ou .csv): você liga cada "
                  "coluna a um campo na próxima tela.", 10, cor="suave", largura=px(700)).grid(
            row=0, column=0, sticky="w", pady=(0, 10))
        Botao(c, "Importar documento...", self._importar_documento, estilo="primario").grid(row=1, column=0, sticky="w")
        return f

    def _importar_documento(self):
        caminho = filedialog.askopenfilename(
            parent=self, filetypes=[("Documentos suportados", "*.pdf *.xlsx *.xlsm *.csv")])
        if not caminho:
            return
        try:
            cabecalho, linhas = impdoc.extrair_tabela(caminho)
        except ErroAdge as e:
            ui.erro(self, "Não consegui ler o documento", str(e))
            return
        if not linhas:
            ui.avisar(self, "Nada para importar", "Não encontrei nenhuma linha de dados nessa tabela.")
            return
        mapeamento_sugerido = impdoc.sugerir_mapeamento(cabecalho)
        DialogoMapeamentoColunas(self, cabecalho, mapeamento_sugerido, lambda m: self._concluir_importacao_documento(
            cabecalho, linhas, m))

    def _concluir_importacao_documento(self, cabecalho, linhas, mapeamento):
        novos, erros = impdoc.construir_lancamentos(cabecalho, linhas, mapeamento, competencia_padrao=_mes_atual())
        for l in novos:
            l.origem = "documento"
        self.lancamentos.extend(novos)
        self._atualizar_previa()
        if erros:
            ui.avisar(self, f"{len(novos)} lançamento(s) importado(s), com avisos", "\n".join(erros))
        else:
            ui.informar(self, "Importado", f"{len(novos)} lançamento(s) adicionado(s) à prévia.")

    # ------------------------------------------------------------------ prévia
    def _montar_tabela(self):
        corpo = tk.Frame(self, bg=P.fundo)
        corpo.pack(fill="both", expand=True)
        cols = [c for c, *_ in COLUNAS]
        self.tv = ttk.Treeview(corpo, columns=cols, show="headings", height=10, selectmode="extended")
        for c, t, w, an in COLUNAS:
            self.tv.heading(c, text=t)
            self.tv.column(c, width=px(w), anchor=an)
        sb = ttk.Scrollbar(corpo, orient="vertical", command=self.tv.yview, style="Adge.Vertical.TScrollbar")
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tv.tag_configure("pronto", foreground=P.pos_texto)
        self.tv.tag_configure("precisa_perfil", foreground=P.aviso_texto)
        self.tv.tag_configure("excluido", foreground=P.suave)

    def _atualizar_previa(self):
        self.itens = previa.preparar_previa(self.emissao_cfg, self.lancamentos)
        self.tv.delete(*self.tv.get_children())
        for i, item in enumerate(self.itens):
            l = item.lancamento
            nome_perfil = next((p["nome"] for p in self.emissao_cfg.get("perfis", []) if p["id"] == item.perfil_id), "—")
            transmissao_status = self._status_transmissao.get(l.id)
            if transmissao_status is not None:
                sucesso, msg = transmissao_status
                situacao = "Transmitido com sucesso" if sucesso else f"Erro: {msg}"
                tag = "pronto" if sucesso else "precisa_perfil"
            else:
                situacao = STATUS_TEXTO[item.status] + (f" ({'; '.join(item.erros)})" if item.erros else "")
                tag = item.status
            self.tv.insert("", "end", iid=str(i), tags=(tag,),
                           values=(l.tomador_nome, l.tomador_documento, moeda(l.valor), l.competencia,
                                   nome_perfil, situacao))

    def _selecao(self):
        return [self.itens[int(iid)] for iid in self.tv.selection()]

    # ------------------------------------------------------------------ ações sobre a prévia
    def _definir_perfil(self):
        sel = self._selecao()
        if not sel:
            ui.avisar(self, "Nada selecionado", "Selecione uma nota na prévia primeiro.")
            return
        perfis = previa.perfis_ativos(self.emissao_cfg)
        if not perfis:
            ui.avisar(self, "Sem perfis", "Esta empresa ainda não tem nenhum perfil de serviço ativo.")
            return

        def aplicar(perfil_id, salvar_regra):
            for item in sel:
                novo_tomador = previa.aplicar_perfil(item, perfil_id, self.emissao_cfg, salvar_regra=salvar_regra)
                if novo_tomador:
                    self.emissao_cfg.setdefault("tomadores", []).append(novo_tomador)
            if salvar_regra:
                self.emp["emissao"] = self.emissao_cfg
                self.store.salvar_empresa(self.emp)
            self._atualizar_previa()

        DialogoEscolherPerfil(self, perfis, salvar_regra_disponivel=len(sel) == 1, ao_confirmar=aplicar)

    def _excluir_selecao(self):
        sel = self._selecao()
        if not sel:
            return
        if not ui.perguntar(self, "Excluir da emissão?", f"{len(sel)} nota(s) não vão ser emitidas."):
            return
        for item in sel:
            previa.excluir(item)
        self._atualizar_previa()

    def _abrir_historico(self):
        DialogoHistoricoEmissao(self, self.store, self.emp)

    def _transmitir(self):
        prontos = previa.prontos_para_transmitir(self.itens)
        if not prontos:
            ui.avisar(self, "Nada para transmitir", "Nenhuma nota está pronta (confira perfil/erros na prévia).")
            return
        pfx = self.emp.get("pfx", "")
        if not Path(pfx).is_file():
            ui.erro(self, "Sem certificado", "Esta empresa não tem um certificado A1 (.pfx) cadastrado.")
            return
        senha = self.store.senha_da_empresa(self.emp)
        if not senha:
            senha = ui.pedir_texto(self, "Senha do certificado", f"Digite a senha do certificado de {self.emp['nome']}:", oculto=True)
            if senha is None:
                return
        ambiente = transmissao.ambiente_ativo()
        aviso_amb = ("PRODUÇÃO REAL" if ambiente == transmissao.TP_AMB_PRODUCAO else "HOMOLOGAÇÃO/produção restrita")
        if not ui.perguntar(self, "Confirmar transmissão",
                             f"Vou transmitir {len(prontos)} nota(s) em {aviso_amb}, uma de cada vez, "
                             "mostrando o resumo antes de cada envio. Continuar?"):
            return
        try:
            sessao = core.sessao_com_certificado(pfx, senha)
        except ErroAdge as e:
            ui.erro(self, "Certificado recusado", str(e))
            return
        for item in prontos:
            self._transmitir_um(item, sessao, ambiente)
        self._atualizar_previa()

    def _transmitir_um(self, item, sessao, ambiente: str):
        lanc = item.lancamento
        perfil = es.perfil_por_id(self.emissao_cfg, item.perfil_id)
        try:
            campos = dps.montar_campos(self.emp, self.emissao_cfg, perfil, item.tomador, lanc)
        except ErroAdge as e:
            self._status_transmissao[lanc.id] = (False, str(e))
            return
        if not DialogoConferenciaNota.perguntar(self, campos):
            return  # "Corrigir": pula esta nota, segue pras próximas
        serie = "1"
        numero = historico.proximo_numero_dps(self.store.pasta, self.emp["id"], serie)
        try:
            xml = dps.montar_xml(campos, serie=serie, numero=numero, ambiente=ambiente)
            xml_assinado = assinatura.assinar_dps(xml, self.emp["pfx"], self.store.senha_da_empresa(self.emp) or "")
        except ErroAdge as e:
            self._status_transmissao[lanc.id] = (False, str(e))
            return
        resultado = transmissao.enviar(xml_assinado, sessao, tp_amb=ambiente)
        registro = {
            "lancamento_id": lanc.id, "competencia": lanc.competencia, "tomador_nome": lanc.tomador_nome,
            "tomador_documento": lanc.tomador_documento, "valor": lanc.valor,
            "status": "emitida" if resultado.sucesso else "pendente",
            "numero": numero, "serie": serie, "chave": resultado.chave, "erro": resultado.erro,
            "data_hora": dt.datetime.now().isoformat(timespec="seconds"),
        }
        historico.registrar(self.store.pasta, self.emp["id"], registro)
        if not resultado.sucesso:
            self._status_transmissao[lanc.id] = (False, resultado.erro)
            return
        try:
            caminho, _ = arquivo.salvar_xml_emitido(self.emp, lanc, resultado.xml_retorno,
                                                     numero=resultado.numero, chave=resultado.chave)
        except Exception as e:
            self._status_transmissao[lanc.id] = (True, f"Transmitida, mas não consegui salvar o XML: {e}")
            return
        self._status_transmissao[lanc.id] = (True, "")


def _resumo_conferencia(campos: dict) -> str:
    """Texto de conferência de uma nota antes de transmitir — tudo que vai na DPS, parecido com o
    resumo do portal antes de emitir (pedido explícito do Abner)."""
    p, t, s, v = campos["prestador"], campos["tomador"], campos["servico"], campos["valores"]
    linhas = [
        "PRESTADOR", f"  {p['nome']} — {p['cnpj']}", "",
        "TOMADOR", f"  {t['nome'] or '(sem nome)'} — {t['documento'] or t.get('nif') or '(sem documento)'}",
    ]
    end_t = t.get("endereco") or {}
    if end_t.get("logradouro"):
        linhas.append(f"  Endereço: {end_t.get('logradouro')}, {end_t.get('numero', '')} - {end_t.get('municipio', '')}/{end_t.get('uf', '')}")
    linhas += ["", "SERVIÇO", f"  CTN: {s['ctn']}", f"  NBS: {s['nbs'] or '—'}",
               f"  Descrição: {campos['descricao'] or '(padrão)'}", "",
               "VALORES", f"  Valor do serviço: {moeda(v['valor_servico'])}"]
    if v.get("desconto_incondicionado"):
        linhas.append(f"  Desconto incondicionado: {moeda(v['desconto_incondicionado'])}")
    if v.get("desconto_condicionado"):
        linhas.append(f"  Desconto condicionado: {moeda(v['desconto_condicionado'])}")
    issqn = s["issqn"]
    linhas.append(f"  ISSQN: {es.TRIB_ISSQN.get(issqn.get('trib_issqn'), '—')} / {es.TP_RET_ISSQN.get(issqn.get('tp_ret_issqn'), '—')}")
    pc = v.get("pis_cofins")
    if pc:
        linhas.append(f"  PIS: {moeda(pc['valor_pis'])} ({pc['aliquota_pis']}%) — COFINS: {moeda(pc['valor_cofins'])} ({pc['aliquota_cofins']}%)")
    for campo, rotulo_v in (("retencao_cp", "Retenção CP/INSS"), ("retencao_irrf", "Retenção IRRF"), ("retencao_csll_outros", "Retenção CSLL")):
        if v.get(campo):
            linhas.append(f"  {rotulo_v}: {moeda(v[campo])}")
    ibscbs = campos.get("ibscbs")
    if ibscbs:
        linhas += ["", "IBS/CBS", f"  CST: {ibscbs['cst']} — cClassTrib: {ibscbs['cclasstrib']}"]
        info = do.info_legal_cclasstrib(ibscbs["cclasstrib"])
        if info.get("p_red_ibs") or info.get("p_red_cbs"):
            linhas.append(f"  Redução oficial: IBS {info.get('p_red_ibs', 0)}% / CBS {info.get('p_red_cbs', 0)}%")
        if ibscbs.get("imovel"):
            linhas.append(f"  Operação com imóvel (município IBGE {ibscbs['imovel']['cmun']})")
        if ibscbs.get("dest"):
            linhas.append(f"  Destinatário diferente do tomador: {ibscbs['dest'].get('nome')}")
    return "\n".join(linhas)


class DialogoConferenciaNota(Modal):
    """Resumo de uma nota antes de transmitir, uma por vez — "Corrigir" pula esta nota (sem
    transmitir), "Confirmar e transmitir" segue com o envio."""

    def __init__(self, pai, campos: dict):
        super().__init__(pai, "Conferir antes de transmitir", largura=560, altura=560)
        self.resposta = False
        self.resizable(True, True)
        rolagem = Rolavel(self)
        rolagem.pack(fill="both", expand=True)
        texto = tk.Text(rolagem.corpo, wrap="word", height=22, width=62, bg=P.superficie, fg=P.texto,
                        font=F(10), relief="flat", borderwidth=0)
        texto.insert("1.0", _resumo_conferencia(campos))
        texto.configure(state="disabled")
        texto.pack(fill="both", expand=True)
        rodape = tk.Frame(self, bg=P.fundo)
        rodape.pack(fill="x", pady=(10, 0))
        Botao(rodape, "Corrigir", self._corrigir).pack(side="right")
        Botao(rodape, "Confirmar e transmitir", self._confirmar, estilo="primario").pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda *_: self._corrigir())
        self.mostrar()

    def _confirmar(self):
        self.resposta = True
        self.destroy()

    def _corrigir(self):
        self.resposta = False
        self.destroy()

    @classmethod
    def perguntar(cls, pai, campos: dict) -> bool:
        d = cls(pai, campos)
        d.wait_window()
        return d.resposta


class DialogoHistoricoEmissao(Modal):
    """Lista as notas já emitidas por esta empresa (`historico.listar`) e permite cancelar uma de
    cada vez (evento e101101) — "qualquer coisa é só cancelar a nota" (Abner)."""

    def __init__(self, pai, store: Armazenamento, emp: dict):
        super().__init__(pai, "Notas emitidas", largura=760, altura=520)
        self.store, self.emp = store, emp
        self.resizable(True, True)
        ui.titulo(self, "Notas emitidas", "Notas transmitidas com sucesso por esta empresa. Cancelar é irreversível.").pack(
            anchor="w", pady=(0, 10))
        corpo = tk.Frame(self, bg=P.fundo)
        corpo.pack(fill="both", expand=True)
        cols = ("data", "tomador", "valor", "numero", "chave", "status")
        self.tv = ttk.Treeview(corpo, columns=cols, show="headings", height=14, selectmode="browse")
        for c, t, w in (("data", "Data", 130), ("tomador", "Tomador", 180), ("valor", "Valor", 90),
                        ("numero", "Número", 70), ("chave", "Chave", 160), ("status", "Status", 110)):
            self.tv.heading(c, text=t)
            self.tv.column(c, width=px(w), anchor="w")
        self.tv.pack(side="left", fill="both", expand=True)
        rodape = tk.Frame(self, bg=P.fundo)
        rodape.pack(fill="x", pady=(10, 0))
        Botao(rodape, "Fechar", self.destroy).pack(side="right")
        Botao(rodape, "Cancelar nota selecionada", self._cancelar, estilo="perigo").pack(side="right", padx=(0, 8))
        self._registros = []
        self._carregar()
        self.bind("<Escape>", lambda *_: self.destroy())
        self.mostrar()

    def _carregar(self):
        self.tv.delete(*self.tv.get_children())
        self._registros = [r for r in historico.listar(self.store.pasta, self.emp["id"]) if r.get("status") == "emitida"]
        for i, r in enumerate(self._registros):
            self.tv.insert("", "end", iid=str(i), values=(
                r.get("data_hora", "")[:16].replace("T", " "), r.get("tomador_nome", ""),
                moeda(r.get("valor", 0.0)), r.get("numero", ""), r.get("chave", ""), "Emitida"))

    def _cancelar(self):
        sel = self.tv.selection()
        if not sel:
            ui.avisar(self, "Nada selecionado", "Selecione uma nota na lista primeiro.")
            return
        registro = self._registros[int(sel[0])]
        motivo_nome = ui.pedir_texto(self, "Motivo do cancelamento",
                                     "Por que esta nota está sendo cancelada? (mín. 15 caracteres)")
        if motivo_nome is None or len(motivo_nome.strip()) < 15:
            if motivo_nome is not None:
                ui.erro(self, "Motivo muito curto", "O motivo precisa ter pelo menos 15 caracteres.")
            return
        if not ui.perguntar(self, "Cancelar esta nota?",
                             f"A NFS-e nº {registro.get('numero')} será cancelada. Isso não pode ser desfeito.",
                             sim="Cancelar nota", perigo=True):
            return
        pfx = self.emp.get("pfx", "")
        senha = self.store.senha_da_empresa(self.emp) or ui.pedir_texto(
            self, "Senha do certificado", f"Digite a senha do certificado de {self.emp['nome']}:", oculto=True)
        if not senha:
            return
        try:
            sessao = core.sessao_com_certificado(pfx, senha)
            xml = eventos.montar_cancelamento_xml(registro["chave"], self.emp.get("cnpj", ""), "1", motivo_nome.strip())
            xml_assinado = assinatura.assinar_pedido_evento(xml, pfx, senha)
        except ErroAdge as e:
            ui.erro(self, "Não consegui cancelar", str(e))
            return
        resultado = transmissao.cancelar(xml_assinado, registro["chave"], sessao, tp_amb=transmissao.ambiente_ativo())
        if not resultado.sucesso:
            ui.erro(self, "Sefin Nacional recusou o cancelamento", resultado.erro)
            return
        registro_cancel = dict(registro)
        registro_cancel.update({"status": "cancelada", "data_hora": dt.datetime.now().isoformat(timespec="seconds")})
        historico.registrar(self.store.pasta, self.emp["id"], registro_cancel)
        ui.informar(self, "Cancelada", "Nota cancelada com sucesso.")
        self._carregar()


class DialogoMapeamentoColunas(Modal):
    """Liga cada coluna do documento a um campo do lançamento. `ao_confirmar(mapeamento)` recebe
    {indice: campo} só com as colunas que o usuário deixou mapeadas."""

    def __init__(self, pai, cabecalho, mapeamento_sugerido, ao_confirmar):
        super().__init__(pai, "Ligar colunas do documento")
        self.ao_confirmar = ao_confirmar
        ui.titulo(self, "Ligar colunas do documento",
                  "Cada coluna do documento vira um campo do lançamento.").pack(anchor="w", pady=(0, 10))
        c = Cartao(self).corpo
        self.vars = []
        opcoes = list(impdoc.CAMPOS)
        for i, titulo_coluna in enumerate(cabecalho):
            rotulo(c, titulo_coluna or f"Coluna {i + 1}", 10).grid(row=i, column=0, sticky="w", pady=4, padx=(0, 14))
            var = tk.StringVar(value=mapeamento_sugerido.get(i, "ignorar"))
            cb = ttk.Combobox(c, textvariable=var, values=opcoes, state="readonly", width=20)
            cb.grid(row=i, column=1, sticky="w", pady=4)
            self.vars.append(var)
        rodape = tk.Frame(self, bg=P.fundo)
        rodape.pack(fill="x", pady=(14, 0))
        Botao(rodape, "Cancelar", self.destroy).pack(side="right")
        Botao(rodape, "Importar", self._confirmar, estilo="primario").pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda *_: self.destroy())
        self.mostrar()

    def _confirmar(self):
        mapeamento = {i: v.get() for i, v in enumerate(self.vars) if v.get() != "ignorar"}
        self.destroy()
        self.ao_confirmar(mapeamento)


class DialogoEscolherPerfil(Modal):
    def __init__(self, pai, perfis, salvar_regra_disponivel, ao_confirmar):
        super().__init__(pai, "Escolher perfil de serviço")
        self.ao_confirmar = ao_confirmar
        rotulo(self, "Perfil de serviço", 10, cor="suave").pack(anchor="w")
        self.v_perfil = tk.StringVar(value=perfis[0]["id"])
        nomes = {p["nome"]: p["id"] for p in perfis}
        self.v_nome = tk.StringVar(value=perfis[0]["nome"])
        cb = ttk.Combobox(self, textvariable=self.v_nome, values=list(nomes), state="readonly", width=34)
        cb.pack(anchor="w", pady=(4, 10))
        self._nomes = nomes
        self.v_salvar = tk.BooleanVar(value=False)
        if salvar_regra_disponivel:
            tk.Checkbutton(self, text="Salvar como regra para este tomador (próximas notas aplicam sozinho)",
                          variable=self.v_salvar, bg=P.fundo, fg=P.texto, selectcolor=P.campo,
                          activebackground=P.fundo, font=F(9)).pack(anchor="w")
        rodape = tk.Frame(self, bg=P.fundo)
        rodape.pack(fill="x", pady=(14, 0))
        Botao(rodape, "Cancelar", self.destroy).pack(side="right")
        Botao(rodape, "Confirmar", self._confirmar, estilo="primario").pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda *_: self.destroy())
        self.mostrar()

    def _confirmar(self):
        perfil_id = self._nomes[self.v_nome.get()]
        salvar = self.v_salvar.get()
        self.destroy()
        self.ao_confirmar(perfil_id, salvar)
