"""Tela de emissão de notas: lançar (manual, planilha ou documento do cliente) e conferir antes
de transmitir. Aberta pelo botão "Emitir Notas" do cartão da empresa (ver app.py), ao lado do
botão "Configurar para Emissão de Notas" da tela de configuração (Dev A).

A transmissão de verdade ainda não está pronta (`emissao/transmissao.py`, `emissao/assinatura.py`
e `emissao/dps.montar_xml` aguardam a pesquisa da API) — por isso o botão "Transmitir" fica
desligado e avisa o motivo, mas todo o lançamento e a prévia já funcionam de ponta a ponta."""
import datetime as dt
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from . import ui
from .core import ErroAdge
from .emissao import config_schema as es
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
        Botao(rodape, "Excluir selecionada(s)", self._excluir_selecao).pack(side="right", padx=(0, 8))
        Botao(rodape, "Definir perfil da selecionada", self._definir_perfil, estilo="secundario").pack(side="right", padx=(0, 8))
        self.b_transmitir = Botao(rodape, "Transmitir notas prontas", self._transmitir, estilo="primario")
        self.b_transmitir.pack(side="left")
        self.b_transmitir.configure(state="disabled")
        rotulo(rodape, "Transmissão real ainda não disponível nesta versão (aguardando a pesquisa da API).",
              9, cor="suave").pack(side="left", padx=(10, 0))

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
        rotulo(c, "Ainda não desenvolvido nesta versão: marcar \"Sim\" não muda a nota emitida. "
                  "Deixe em \"Não\" até esse grupo entrar de verdade.", 10, cor="suave", largura=px(620)).pack(
            anchor="w", pady=(4, 10))
        ttk.Combobox(c, textvariable=self.v_ibscbs, values=["Não", "Sim"], state="readonly", width=12, font=F(10)).pack(anchor="w")
        return f

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
            f"IBS/CBS: {self.v_ibscbs.get()}",
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
                incluir_ibscbs=self.v_ibscbs.get() == "Sim",
                origem="manual",
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
        self.v_ibscbs.set("Não")
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
            situacao = STATUS_TEXTO[item.status] + (f" ({'; '.join(item.erros)})" if item.erros else "")
            self.tv.insert("", "end", iid=str(i), tags=(item.status,),
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

    def _transmitir(self):
        ui.avisar(self, "Transmissão ainda não disponível",
                 "O envio de verdade (assinatura e POST /nfse) ainda não foi implementado nesta "
                 "versão - está aguardando a pesquisa oficial da API. A prévia já está pronta para "
                 "quando essa parte for concluída.")


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
