"""Janela de busca de notas: escolhe o mês, consulta o ADN, mostra totais e notas e grava os XMLs."""
import datetime as dt
import os
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from . import NOME_APP, core, nfe, nfe_resp, paulistana, totais
from . import ui
from .core import Cancelado, ErroAdge
from .nfe_cache import HistoricoNFe, formatar_espera
from .store import Armazenamento
from .ui import P, Botao, Campo, Cartao, Chip, Interruptor, Marcador, Modal, Segmentado, F, px, rotulo

formatar_cnpj = ui.formatar_cnpj
HISTORICO_MAX = 30


def moeda(v: float) -> str:
    return core.formatar_valor(v).replace("R$", "R$ ")


def mes_anterior(hoje: dt.date = None):
    hoje = hoje or dt.date.today()
    return (hoje.year - 1, 12) if hoje.month == 1 else (hoje.year, hoje.month - 1)


def registrar_historico(store: Armazenamento, emp: dict, ano: int, mes: int, resumo: dict, qtd: int,
                        faturamento: float = None, compras: float = None, pasta: str = None):
    """Guarda a consulta no histórico (só um resumo e o caminho da pasta onde as notas foram salvas: sem notas, sem senhas).
    Máximo de 30 entradas, a mais nova primeiro. Só é chamada depois de salvar: sem pasta salva não há histórico.
    Com NF-e, faturamento e compras vêm da seleção padrão (NFS-e + NF-e); sem eles valem os totais das NFS-e."""
    prest = faturamento if faturamento is not None else resumo.get("servico_prestado", {}).get("valor")
    tom = compras if compras is not None else resumo.get("servico_tomado", {}).get("valor")
    h = store.preferencias.setdefault("historico", [])
    h[:] = [x for x in h if not (x.get("empresa_id") == emp["id"] and x.get("ano") == ano and x.get("mes") == mes)]
    h.insert(0, {"empresa_id": emp["id"], "nome": emp["nome"], "ano": ano, "mes": mes, "notas": qtd,
                 "quando": dt.datetime.now().isoformat(timespec="minutes"), "prestado": prest, "tomado": tom,
                 "pasta": str(pasta) if pasta else None})
    del h[HISTORICO_MAX:]
    try:
        store.salvar()
    except OSError:
        pass


class DialogoBusca(Modal):
    COLUNAS = (("tipo", "Tipo", 108, "w"), ("numero", "Nº", 70, "e"), ("data", "Data", 92, "w"),
               ("parte", "Cliente / Fornecedor", 312, "w"), ("valor", "Valor", 120, "e"))

    def __init__(self, pai, store: Armazenamento, emp: dict, sessao=None, periodo=None, auto=False, sessao_nfe=None,
                 base_historico=None, sessao_paulistana=None, da_pasta=None, sessao_nfe_resp=None):
        super().__init__(pai, f"Buscar notas — {emp['nome']}", margem=22)
        self.store, self.emp, self.sessao_teste = store, dict(emp), sessao
        self.sessao_nfe_teste, self.base_historico, self.hist = sessao_nfe, base_historico, None
        self.sessao_paulistana_teste = sessao_paulistana
        self.sessao_nfe_resp_teste, self.hist_resp = sessao_nfe_resp, None     # NF-e pelo certificado do responsável (v1.7.6)
        self.v_cert_nfe = tk.StringVar(value=self._cert_nfe_inicial())
        self.sel = totais.Selecao()
        self.sel.ao_mudar(self._mudou_selecao)
        self.fila: "queue.Queue" = queue.Queue()
        self.cancelar_flag = False
        self.trabalhando = False
        self.resultado = None
        self.pasta_manual = ""
        self.cats = []
        self.ordem = (None, False)
        self.ano, mes = periodo if periodo else mes_anterior()
        self.v_mes = tk.StringVar(value=core.MESES_TELA[mes - 1])
        self.v_lote = tk.BooleanVar(value=False)              # consulta de períodos em lote: desmarcada por padrão
        self.periodos_sel = {(self.ano, mes)}                 # meses marcados (só vale mais de um com o lote ligado)
        self.lote_periodos, self.lote_dados, self.lote_planos = [], None, {}
        self._cats_vistas = set()
        self.v_prest = tk.BooleanVar(value=emp["tipos"].get("prestado", True))
        self.v_tom = tk.BooleanVar(value=emp["tipos"].get("tomado", True))
        self.v_nfe = tk.BooleanVar(value=bool(emp.get("nfe")))
        self.v_paul = tk.BooleanVar(value=bool(emp.get("paulistana")))
        self.docs_paul, self.msgs_paul = None, []
        self.da_pasta = str(da_pasta) if da_pasta else None   # reabertura pelo histórico: lê da pasta salva, sem consultar nada
        self.salvo, self.pasta_salva = False, None
        self._nfe_travada = None                              # None = ainda não aplicado; True/False = estado atual do interruptor
        self.v_acao = tk.StringVar(value=emp["acao"])
        self.v_filtro = tk.StringVar(value="todas")
        self.v_texto = tk.StringVar()
        self.resizable(True, True)
        self._montar()
        tela_h = self.winfo_screenheight()
        self.geometry(f"{px(1080)}x{min(px(920), tela_h - px(90))}")
        self.minsize(px(900), px(560))
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self.bind("<Escape>", lambda *_: self._fechar())
        self.bind("<Control-e>", lambda *_: self.resultado and self._exportar_planilha())
        self.bind("<F5>", lambda *_: self._buscar())
        self.mostrar()
        self.after(150, self._ler_fila)
        self._tic_nfe()
        if self.da_pasta:
            self.after(250, self._abrir_da_pasta)
        elif auto:
            self.after(250, self._buscar)

    # ------------------------------------------------------------------ montagem
    def _montar(self):
        cab = tk.Frame(self, bg=P.fundo)
        cab.pack(fill="x")
        ui.titulo(cab, self.emp["nome"], f"CNPJ {formatar_cnpj(self.emp['cnpj'])}").pack(side="left")

        topo = Cartao(self, pad=14)
        topo.pack(fill="x", pady=(10, 0))
        t = topo.corpo
        esq = tk.Frame(t, bg=P.superficie)
        esq.pack(side="left", anchor="n")
        lin = tk.Frame(esq, bg=P.superficie)
        lin.pack(anchor="w")
        rotulo(lin, "Período", 11, "bold", "verde_escuro").pack(side="left", padx=(0, 14))
        self.b_ano_menos = Botao(lin, "‹", lambda: self._mudar_ano(-1), estilo="secundario", padx=10, pady=3)
        self.b_ano_menos.pack(side="left")
        self.l_ano = rotulo(lin, str(self.ano), 11, "bold", anchor="center", width=6)
        self.l_ano.pack(side="left", padx=4)
        self.b_ano_mais = Botao(lin, "›", lambda: self._mudar_ano(1), estilo="secundario", padx=10, pady=3)
        self.b_ano_mais.pack(side="left")
        self.b_anterior = Botao(lin, "Mês anterior", self._ir_mes_anterior, estilo="fantasma", pady=3)
        self.b_anterior.pack(side="left", padx=(14, 0))
        self.b_este = Botao(lin, "Este mês", self._ir_este_mes, estilo="fantasma", pady=3)
        self.b_este.pack(side="left")
        grade = tk.Frame(esq, bg=P.superficie)
        grade.pack(anchor="w", pady=(8, 0))
        self.b_meses = []
        for i, nome in enumerate(core.MESES_TELA):
            b = Botao(grade, nome[:3], lambda i=i: self._escolher_mes(i), estilo="secundario", padx=6, pady=5, largura=54, tam=10)
            b.grid(row=i // 6, column=i % 6, padx=(0, 5), pady=(0, 5))
            self.b_meses.append(b)
        self.m_lote = Marcador(esq, "Consulta de períodos em lote", self.v_lote, self._alternar_lote, tom="azul", tam=9)
        self.m_lote.pack(anchor="w", pady=(2, 0))
        self.l_periodo = rotulo(esq, "", 10, cor="suave", largura=px(420))
        self.l_periodo.pack(anchor="w", pady=(4, 0))

        acao = tk.Frame(t, bg=P.superficie)
        acao.pack(side="right", anchor="s", padx=(16, 0))
        self.b_buscar = Botao(acao, "Buscar notas", self._buscar, estilo="primario", padx=26, pady=11, tam=11)
        self.b_buscar.pack()
        dir_ = tk.Frame(t, bg=P.superficie)
        dir_.pack(side="left", anchor="n", padx=(36, 0), fill="x", expand=True)
        rotulo(dir_, "Tipos de nota", 11, "bold", "verde_escuro").pack(anchor="w")
        tipos = tk.Frame(dir_, bg=P.superficie)
        tipos.pack(anchor="w", pady=(4, 0))
        Interruptor(tipos, "Serviço prestado", self.v_prest).pack(side="left", padx=(0, 14))
        Interruptor(tipos, "Serviço tomado", self.v_tom).pack(side="left", padx=(0, 14))
        tipos2 = tk.Frame(dir_, bg=P.superficie)
        tipos2.pack(anchor="w", pady=(6, 0))
        self.sw_nfe = Interruptor(tipos2, "NF-e (modelo 55)", self.v_nfe, desabilitado=not self.emp.get("nfe"))
        self.sw_nfe.pack(side="left", padx=(0, 14))
        Interruptor(tipos2, "Nota Paulistana (Prefeitura de SP, só conferência)", self.v_paul).pack(side="left")
        self.f_cert_nfe = tk.Frame(dir_, bg=P.superficie)
        if self.store.responsavel and self.emp.get("nfe"):
            self.f_cert_nfe.pack(anchor="w", pady=(8, 0))
            rotulo(self.f_cert_nfe, "Certificado da NF-e", 9, "bold", "suave").pack(anchor="w")
            self.seg_cert = Segmentado(self.f_cert_nfe, [("empresa", "Da empresa"), ("responsavel", "Do responsável"), ("ambos", "Os dois")],
                                       self.v_cert_nfe, self._mudou_cert_nfe, tam=9, pady=4)
            self.seg_cert.pack(anchor="w", pady=(3, 0))
            self.l_cert_dica = rotulo(self.f_cert_nfe, "", 9, cor="suave", largura=px(400))
            self.l_cert_dica.pack(anchor="w", pady=(3, 0))
            self._mudou_cert_nfe()
        rotulo(dir_, "O que fazer", 11, "bold", "verde_escuro").pack(anchor="w", pady=(12, 4))
        self.seg_acao = Segmentado(dir_, [("ambos", "Total e XMLs"), ("calcular", "Só o total"), ("baixar", "Só os XMLs")], self.v_acao)
        self.seg_acao.pack(anchor="w")
        self._atualizar_meses()

        st = tk.Frame(self, bg=P.fundo)
        st.pack(fill="x", pady=(10, 0))
        self.l_status = rotulo(st, "", 10, cor="suave")
        self.l_status.pack(side="left")
        self.b_cancelar = Botao(st, "Cancelar busca", self._cancelar_busca, pady=4)
        # contador da SEFAZ numa linha só, ao lado do status: não rouba altura da lista de notas
        self.l_nfe_timer = rotulo(st, "", 10, "bold", "verde_escuro")
        self.l_nfe_info = self.l_nfe_timer
        if self.emp.get("nfe"):
            self.l_nfe_timer.pack(side="right")
        self.barra = ui.Barra(self)

        self.f_res = tk.Frame(self, bg=P.fundo)
        self._montar_resultado(self.f_res)
        self.f_botoes = tk.Frame(self, bg=P.fundo)
        self.l_destino = rotulo(self, "", 10, cor="suave", largura=px(900))
        self.b_gravar = Botao(self.f_botoes, "Baixar XMLs para a pasta", self._gravar, estilo="primario")
        self.b_pasta = Botao(self.f_botoes, "Escolher pasta...", self._escolher_pasta)
        self.b_csv = Botao(self.f_botoes, "Exportar planilha...", self._exportar_planilha)
        Botao(self.f_botoes, "Fechar", self._fechar, estilo="fantasma").pack(side="right")

    def _montar_resultado(self, pai):
        self.f_lote = tk.Frame(pai, bg=P.fundo)               # só aparece depois de uma consulta em lote
        rotulo(self.f_lote, "Meses desta consulta (clique para ver cada um; \"Baixar XMLs\" grava todos)", 10, "bold", "verde_escuro").pack(anchor="w")
        self.f_lote_botoes = tk.Frame(self.f_lote, bg=P.fundo)
        self.l_lote_resumo = rotulo(self.f_lote, "", 9, cor="suave", largura=px(980))
        self.f_bloco = tk.Frame(pai, bg=P.fundo)
        self.f_bloco.pack(fill="x", pady=(12, 0))
        cards = tk.Frame(self.f_bloco, bg=P.fundo)
        cards.pack(fill="x")
        for c in range(3):
            cards.columnconfigure(c, weight=1, uniform="tot")
        self.cards = {}
        for col, (chave, nome, cor) in enumerate((("fat", "Faturamento (serviços prestados)", "pos_texto"),
                                                  ("comp", "Serviços tomados", "neg_texto"))):
            c = Cartao(cards, pad=12)
            t = rotulo(c.corpo, nome, 9, "bold", "suave")
            t.pack(anchor="w")
            v = rotulo(c.corpo, "—", 19, "bold", cor)
            v.pack(anchor="w")
            d = rotulo(c.corpo, "", 9, cor="suave")
            d.pack(anchor="w")
            self.cards[chave] = (c, v, d, col, t)
        self.c_saldo = Cartao(cards, fundo="pos_fundo", borda="pos_fundo", pad=12)
        self.l_saldo_t = rotulo(self.c_saldo.corpo, "Saldo líquido", 9, "bold", "pos_texto")
        self.l_saldo_v = rotulo(self.c_saldo.corpo, "—", 19, "bold", "pos_texto")
        self.l_saldo_d = rotulo(self.c_saldo.corpo, "Prestado − tomado, antes dos impostos", 9, cor="pos_texto")
        for w in (self.l_saldo_t, self.l_saldo_v, self.l_saldo_d):
            w.pack(anchor="w")
        self.cards_pos = cards
        # o que entra nos números: as mesmas marcas valem para cartões, tabela, gráfico, análise de regimes e planilha
        self.f_cats = tk.Frame(self.f_bloco, bg=P.fundo)
        rotulo(self.f_cats, "Considerar nos totais, no gráfico e na análise de regimes", 10, "bold", "verde_escuro").pack(anchor="w", pady=(0, 6))
        self.f_marcas = tk.Frame(self.f_cats, bg=P.fundo)
        self.f_marcas.pack(fill="x")
        self.l_marcas_dica = rotulo(self.f_cats, "", 9, cor="suave", largura=px(980))
        self.l_marcas_dica.pack(anchor="w")
        self.marcas = {}
        self.f_acoes_totais = tk.Frame(self.f_bloco, bg=P.fundo)
        self.b_avancado = Botao(self.f_acoes_totais, "Informações avançadas", self._avancado, estilo="suave", pady=6)
        self.b_copiar = Botao(self.f_acoes_totais, "Copiar totais", self._copiar, pady=6)
        self.l_aviso = rotulo(pai, "", 10, cor="aviso_texto", largura=px(980))
        self.l_aviso.pack(anchor="w", pady=(8, 0))

        barra = tk.Frame(pai, bg=P.fundo)
        barra.pack(fill="x", pady=(10, 6))
        self.seg_filtro = Segmentado(barra, [("todas", "Todas"), ("receita", "Faturamento"), ("custo", "Compras e tomados")],
                                     self.v_filtro, self._preencher_tabela, pady=4)
        self.seg_filtro.pack(side="left")
        self.campo_texto = Campo(barra, self.v_texto, largura=26)
        self.campo_texto.pack(side="right")
        rotulo(barra, "Filtrar:", 10, cor="suave").pack(side="right", padx=(0, 8))
        self.v_texto.trace_add("write", lambda *_: self._preencher_tabela())

        self.tab = tk.Frame(pai, bg=P.superficie, highlightbackground=P.borda_forte, highlightthickness=1)
        self.tab.pack(fill="both", expand=True)
        cols = [c[0] for c in self.COLUNAS]
        self.tv = ttk.Treeview(self.tab, columns=cols, show="headings", height=7, selectmode="browse")
        for c, t, w, an in self.COLUNAS:
            self.tv.heading(c, text=t, anchor=an, command=lambda c=c: self._ordenar(c))
            self.tv.column(c, width=px(w), anchor=an, stretch=(c == "parte"))
        sb = ttk.Scrollbar(self.tab, orient="vertical", command=self.tv.yview, style="Adge.Vertical.TScrollbar")
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tv.tag_configure("prest", foreground=P.pos_texto)
        self.tv.tag_configure("tom", foreground=P.neg_texto)
        self.tv.tag_configure("neutro", foreground=P.suave)
        self.tv.tag_configure("semciencia", foreground=P.aviso_texto, background=P.aviso_fundo)
        self.tv.tag_configure("alt", background=P.linha_alt)
        self.tv.bind("<<TreeviewSelect>>", lambda *_: self._detalhe())
        self.l_detalhe = rotulo(pai, "Selecione uma nota para ver os detalhes.", 10, cor="suave", largura=px(980))
        self.l_detalhe.pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------------ período
    def _mes_num(self) -> int:
        return core.MESES_TELA.index(self.v_mes.get()) + 1

    def _periodos(self) -> list:
        """Períodos da busca: o mês escolhido ou, com o lote ligado, todos os meses marcados (em ordem)."""
        if self.v_lote.get() and self.periodos_sel:
            return sorted(self.periodos_sel)
        return [(self.ano, self._mes_num())]

    def _atualizar_meses(self):
        sel = self._periodos()
        marcados = set(sel)
        for i, b in enumerate(self.b_meses):
            b.config(style="primario" if (self.ano, i + 1) in marcados else "secundario")
        if len(sel) == 1:
            ano, mes = sel[0]
            ini, fim = core.limites_mes(ano, mes)
            self.l_periodo.config(text=f"{core.MESES_TELA[mes - 1]} de {ano}  ·  de {ini:%d/%m/%Y} a {fim:%d/%m/%Y}")
        else:
            self.l_periodo.config(text=f"{len(sel)} meses em lote: {core.formatar_periodos(sel)}")
        self.l_ano.config(text=str(self.ano))

    def _atualizar_periodo(self):
        self._atualizar_meses()

    def _alternar_lote(self):
        """Liga/desliga o lote. Ligando, o mês que estava escolhido continua marcado; desligando, volta a valer um mês só."""
        if self.v_lote.get():
            self.periodos_sel = {(self.ano, self._mes_num())}
        else:
            ano, mes = (sorted(self.periodos_sel)[0] if self.periodos_sel else (self.ano, self._mes_num()))
            self.ano = ano
            self.v_mes.set(core.MESES_TELA[mes - 1])
            self.periodos_sel = {(ano, mes)}
        self._atualizar_meses()

    def _escolher_mes(self, i):
        if self.v_lote.get():
            self.periodos_sel = core.alternar_periodo(self.periodos_sel, self.ano, i + 1)
            if (self.ano, i + 1) in self.periodos_sel:
                self.v_mes.set(core.MESES_TELA[i])
        else:
            self.v_mes.set(core.MESES_TELA[i])
            self.periodos_sel = {(self.ano, i + 1)}
        self._atualizar_meses()

    def _mudar_ano(self, d):
        novo = self.ano + d
        if 2000 <= novo <= 2100:
            self.ano = novo
            self._atualizar_meses()

    def _ir_mes_anterior(self):
        self.ano, m = mes_anterior()
        self.v_mes.set(core.MESES_TELA[m - 1])
        self.periodos_sel = {(self.ano, m)}
        self._atualizar_meses()

    def _ir_este_mes(self):
        h = dt.date.today()
        self.ano = h.year
        self.v_mes.set(core.MESES_TELA[h.month - 1])
        self.periodos_sel = {(self.ano, h.month)}
        self._atualizar_meses()

    # ------------------------------------------------------------------ NF-e: contador da SEFAZ
    def _historico(self) -> HistoricoNFe:
        """Histórico da empresa (relido do disco: outra janela pode ter consultado)."""
        if self.hist is None:
            self.hist = HistoricoNFe(self.emp, base=self.base_historico)
        else:
            self.hist.estado = self.hist._ler()
        return self.hist

    # ------------------------------------------------------------------ NF-e: de qual certificado (empresa, responsável ou os dois)
    def _cert_nfe_inicial(self) -> str:
        if not self.store.responsavel:
            return "empresa"
        v = self.store.preferencias.get("cert_nfe", {}).get(self.emp["id"], "empresa")
        return v if v in ("empresa", "responsavel", "ambos") else "empresa"

    def _mudou_cert_nfe(self):
        nome = (self.store.responsavel or {}).get("nome") or "o responsável"
        self.l_cert_dica.config(text={
            "empresa": "Compras e notas tomadas pela empresa (com a ciência da operação, se estiver ligada).",
            "responsavel": f"NF-e de venda e notas que citam {nome} no autXML, consultadas com o certificado do responsável.",
            "ambos": "Compras pela empresa e vendas pelo responsável, no mesmo relatório (duas consultas à SEFAZ, cada uma com o seu limite)."}
            [self.v_cert_nfe.get()])
        self._nfe_travada = None            # refaz o contador e o interruptor da NF-e com a(s) fonte(s) escolhida(s)

    def _fontes_nfe(self) -> list:
        if not self.emp.get("nfe"):
            return []
        esc = self.v_cert_nfe.get() if self.store.responsavel else "empresa"
        return {"empresa": ["empresa"], "responsavel": ["responsavel"], "ambos": ["empresa", "responsavel"]}.get(esc, ["empresa"])

    def _historico_resp(self) -> HistoricoNFe:
        """Controle de NSU e bloqueio do responsável (a SEFAZ conta as consultas por quem consulta, não por empresa)."""
        if self.hist_resp is None:
            self.hist_resp = HistoricoNFe(nfe_resp.emp_do_responsavel(self.store.responsavel), base=self.base_historico)
        else:
            self.hist_resp.estado = self.hist_resp._ler()
        return self.hist_resp

    def _hist_da_fonte(self, fonte: str) -> HistoricoNFe:
        return self._historico() if fonte == "empresa" else self._historico_resp()

    def _tic_nfe(self):
        """A cada segundo: mostra o contador da SEFAZ e trava/destrava o interruptor da NF-e. Com a SEFAZ bloqueada a NF-e fica
        desligada e sem opção de religar (consultar de novo só reinicia a espera de 1 hora); quando o prazo acaba ela volta sozinha."""
        if not self.winfo_exists():
            return
        if self.emp.get("nfe") and not self.da_pasta:
            fontes = self._fontes_nfe()
            hs = {f: self._hist_da_fonte(f) for f in fontes}
            travada = all(h.bloqueio_restante() is not None for h in hs.values())
            if travada != self._nfe_travada:
                self._nfe_travada = travada
                self.sw_nfe.desabilitar(travada)
                self.v_nfe.set(not travada)
            ciencia = "ciência automática" if self.emp.get("nfe_ciencia") else "sem ciência"
            if fontes == ["empresa"]:
                h = hs["empresa"]
                if not travada:
                    self.l_nfe_timer.config(text=f"NF-e: consulta liberada na SEFAZ ({ciencia}).", fg=ui._cor("verde_escuro"))
                else:
                    self.l_nfe_timer.config(
                        text=f"NF-e desligada: a SEFAZ libera outra consulta em {formatar_espera(h.bloqueio_restante() or dt.timedelta(0))} "
                             f"(às {h.liberado_as():%H:%M}). Volta sozinha. Limite da SEFAZ, não da Adge.",
                        fg=ui._cor("aviso_texto"))
            else:
                partes = []
                for f, h in hs.items():
                    nome = "empresa" if f == "empresa" else "responsável"
                    resto = h.bloqueio_restante()
                    partes.append(f"{nome}: liberada" if resto is None else f"{nome}: espera de {formatar_espera(resto)} (às {h.liberado_as():%H:%M})")
                if travada:
                    texto = "NF-e desligada: " + "; ".join(partes) + ". Volta sozinha. Limite da SEFAZ, não da Adge."
                else:
                    texto = "NF-e: " + "; ".join(partes) + ("; a que está em espera fica de fora desta busca." if any("espera" in p for p in partes) else ".")
                self.l_nfe_timer.config(text=texto, fg=ui._cor("aviso_texto" if travada or "espera" in texto else "verde_escuro"))
        self.after(1000, self._tic_nfe)

    # ------------------------------------------------------------------ busca
    def _emp_da_busca(self) -> dict:
        e = dict(self.emp)
        e["tipos"] = {"prestado": self.v_prest.get(), "tomado": self.v_tom.get()}
        e["acao"] = self.v_acao.get()
        return e

    def _buscar(self):
        if self.trabalhando:
            return
        emp = self._emp_da_busca()
        escolhidas = self._fontes_nfe() if self.v_nfe.get() else []
        fontes_nfe = [f for f in escolhidas if not self._hist_da_fonte(f).bloqueado()]    # a fonte em espera fica de fora
        puladas = [f for f in escolhidas if f not in fontes_nfe]
        usar_nfe = bool(fontes_nfe)
        if emp.get("nfe"):
            self._historico()               # o controle da empresa existe mesmo quando só o responsável é consultado
        usar_paul = bool(self.v_paul.get())
        if not (emp["tipos"]["prestado"] or emp["tipos"]["tomado"] or usar_nfe or usar_paul):
            ui.avisar(self, "Marque pelo menos um tipo de nota", "Escolha serviço prestado, serviço tomado, NF-e, Nota Paulistana ou mais de um.")
            return
        try:
            senha = self.store.senha_da_empresa(emp)
        except ErroAdge as e:
            ui.avisar(self, "Não consegui usar a senha salva", str(e))
            senha = ""
        if not senha:
            senha = ui.pedir_texto(self, "Senha do certificado", f"Digite a senha do certificado de {emp['nome']}:", oculto=True,
                                   validar=lambda t: None if t else "Digite a senha.")
            if not senha:
                return
        senha_resp = ""
        if "responsavel" in fontes_nfe:
            resp = self.store.responsavel
            try:
                senha_resp = self.store.senha_do_responsavel(resp)
            except ErroAdge as e:
                ui.avisar(self, "Não consegui usar a senha salva do responsável", str(e))
            if not senha_resp:
                senha_resp = ui.pedir_texto(self, "Senha do certificado do responsável",
                                            f"Digite a senha do certificado de {resp.get('nome') or 'responsável'}:", oculto=True,
                                            validar=lambda t: None if t else "Digite a senha.")
                if not senha_resp:
                    return
        if self.store.responsavel and self.emp.get("nfe"):         # lembra a escolha do certificado para a próxima busca desta empresa
            self.store.preferencias.setdefault("cert_nfe", {})[self.emp["id"]] = self.v_cert_nfe.get()
            try:
                self.store.salvar()
            except OSError:
                pass
        self.f_res.pack_forget()
        self.f_botoes.pack_forget()
        self.l_destino.pack_forget()
        self.cancelar_flag = False
        self._ocupado(True)
        periodos = self._periodos()
        ano, mes = periodos[0]
        self.lote_periodos = periodos if len(periodos) > 1 else []
        self.lote_dados, self.lote_planos, self._cats_vistas = None, {}, set()
        self.consulta = (emp, ano, mes)
        tem_nfse = bool(emp["tipos"]["prestado"] or emp["tipos"]["tomado"])
        self.docs_paul, self.msgs_paul = None, []
        self.salvo, self.pasta_salva, self.da_pasta = False, None, None   # busca nova: nada salvo ainda

        def trabalho():
            try:
                if tem_nfse:
                    docs, cnpj = core.buscar(emp, senha, ano, mes, log=lambda m: self.fila.put(("log", m)),
                                             cancelar=lambda: self.cancelar_flag, sessao=self.sessao_teste)
                else:
                    docs, cnpj = [], re.sub(r"\D", "", emp["cnpj"])
                ctx = (self._trabalho_nfe(emp, senha, cnpj, ano, mes, periodos, fontes_nfe, senha_resp, puladas) if usar_nfe else None)
                if usar_paul:
                    self._trabalho_paulistana(emp, senha, cnpj, ano, mes, periodos)
                if len(periodos) > 1:     # as fontes já foram consultadas uma vez só; aqui só se separa cada mês
                    self.lote_planos = {(a, m): core.planejar(emp, docs, cnpj, a, m, None, {}, docs_nfe=ctx["docs"] if ctx else None,
                                                              docs_paulistana=self.docs_paul)[0] for a, m in periodos}
                self.fila.put(("ok", (docs, cnpj, ctx)))
            except Cancelado:
                self.fila.put(("cancelado", None))
            except ErroAdge as e:
                self.fila.put(("erro", str(e)))
            except Exception as e:  # nunca deixar a janela travada
                self.fila.put(("erro", f"Erro inesperado: {e}"))

        threading.Thread(target=trabalho, daemon=True).start()

    def _trabalho_paulistana(self, emp, senha, cnpj, ano, mes, periodos=None):
        """Busca separada na Prefeitura de São Paulo (um mês por vez; em lote, repete para cada mês marcado).
        Falha aqui vira aviso: não derruba as outras fontes."""
        log = lambda m: self.fila.put(("log", m))   # noqa: E731
        try:
            sessao = self.sessao_paulistana_teste or paulistana.sessao_paulistana(emp["pfx"], senha)
            assinador = nfe.carregar_assinador(emp["pfx"], senha)
            docs, msgs = [], []
            for a, m in (periodos or [(ano, mes)]):
                log(f"Consultando a Nota Paulistana na Prefeitura de São Paulo ({core.mes_exibicao(m)}/{a})...")
                r = paulistana.consultar(sessao, cnpj, a, m, assinador, prestadas=True, tomadas=True, log=log,
                                         cancelar=lambda: self.cancelar_flag)
                docs += r["docs"]
                msgs += [x for x in r["msgs"] if x not in msgs]
            self.docs_paul, self.msgs_paul = docs, msgs
        except ErroAdge as e:
            self.docs_paul, self.msgs_paul = [], [f"Nota Paulistana: {e}"]
        except ImportError as e:
            self.docs_paul, self.msgs_paul = [], [f"Nota Paulistana: instalação incompleta (falta um componente): {e}"]

    def _trabalho_nfe(self, emp, senha, cnpj, ano, mes, periodos=None, fontes=("empresa",), senha_resp="", puladas=()) -> dict:
        """Parte da NF-e da busca (roda fora da tela). Erros da SEFAZ não derrubam as NFS-e: viram avisos.
        O bloqueio da SEFAZ é gravado na hora; o NSU e os XMLs ficam na memória (`pend_docs`) até a pessoa salvar as notas.
        `fontes`: 'empresa' (certificado da empresa: compras, com ciência opcional) e/ou 'responsavel' (certificado do responsável:
        NF-e de venda e notas que o citam no autXML). Cada fonte tem o seu NSU e o seu limite de consultas na SEFAZ."""
        h = self.hist
        ctx = {"msgs": [], "novos": 0, "ciencia": 0, "consultou": False, "pend_docs": [], "confirmado": "empresa" not in fontes,
               "ult_nsu": h.estado["ult_nsu"], "max_nsu": h.estado["max_nsu"], "resp": None}
        log = lambda m: self.fila.put(("log", m))   # noqa: E731
        cancelar = lambda: self.cancelar_flag       # noqa: E731
        for f in puladas:
            ctx["msgs"].append(f"NF-e pelo certificado {'da empresa' if f == 'empresa' else 'do responsável'}: a SEFAZ ainda está em espera "
                               "(limite dela), então essa fonte ficou de fora desta busca.")
        docs_empresa = []
        if "empresa" in fontes:
            try:
                sessao = self.sessao_nfe_teste or nfe.sessao_nfe(emp["pfx"], senha)
                log("Consultando as NF-e na SEFAZ...")
                r = nfe.consultar_distribuicao(sessao, cnpj, h.estado["ult_nsu"], log=log, cancelar=cancelar)
                h.registrar_bloqueio(r["max_nsu"], r["bloqueado_ate"], (ano, mes))
                ctx.update(consultou=True, ult_nsu=r["ult_nsu"], max_nsu=r["max_nsu"], novos=len(r["docs"]), pend_docs=list(r["docs"]))
                if r["situacao"] == "bloqueado":
                    ctx["msgs"].append("A SEFAZ recusou a consulta de NF-e por excesso de consultas (limite dela, não do sistema; cStat 656"
                                       + (f": {r['mensagem']}" if r.get("mensagem") else "") + ").")
                if emp.get("nfe_ciencia"):
                    self._ciencia(sessao, emp, senha, cnpj, ano, mes, ctx, log, cancelar, periodos)
            except Cancelado:
                raise
            except ErroAdge as e:
                ctx["msgs"].append(f"NF-e não consultada: {e}")
            docs_empresa = self._juntar_docs(h.carregar_docs(), ctx["pend_docs"])
        docs_resp = []
        if "responsavel" in fontes:
            docs_resp = self._trabalho_nfe_resp(ctx, ano, mes, senha_resp, log, cancelar)
        ctx["docs"] = docs_empresa + docs_resp
        if not ctx["docs"] and not ctx["msgs"]:
            ctx["msgs"].append("Nenhuma NF-e encontrada para esta empresa.")
        return ctx

    def _trabalho_nfe_resp(self, ctx, ano, mes, senha_resp, log, cancelar) -> list:
        """Consulta a SEFAZ com o certificado do responsável (CPF ou CNPJ). Devolve os documentos dele (cache + novos), marcados como
        `fonte: responsavel`: as notas de várias empresas chegam juntas e cada busca só separa as da empresa consultada."""
        resp = self.store.responsavel
        hr = self._historico_resp()
        sub = {"consultou": False, "pend_docs": [], "confirmado": False, "ult_nsu": hr.estado["ult_nsu"], "max_nsu": hr.estado["max_nsu"],
               "novos": 0}
        ctx["resp"] = sub
        try:
            sessao = self.sessao_nfe_resp_teste or nfe.sessao_nfe(resp["pfx"], senha_resp)
            log("Consultando as NF-e pelo certificado do responsável...")
            r = nfe.consultar_distribuicao(sessao, resp["documento"], hr.estado["ult_nsu"], log=log, cancelar=cancelar)
            hr.registrar_bloqueio(r["max_nsu"], r["bloqueado_ate"], (ano, mes))
            sub.update(consultou=True, ult_nsu=r["ult_nsu"], max_nsu=r["max_nsu"], novos=len(r["docs"]), pend_docs=list(r["docs"]))
            ctx["novos"] += len(r["docs"])
            if r["situacao"] == "bloqueado":
                ctx["msgs"].append("A SEFAZ recusou a consulta de NF-e do responsável por excesso de consultas (limite dela, não do sistema; "
                                   "cStat 656" + (f": {r['mensagem']}" if r.get("mensagem") else "") + ").")
        except Cancelado:
            raise
        except ErroAdge as e:
            ctx["msgs"].append(f"NF-e pelo responsável não consultada: {e}")
        docs = self._juntar_docs(hr.carregar_docs(), sub["pend_docs"])
        for d in docs:
            d["fonte"] = "responsavel"
        return docs

    @staticmethod
    def _juntar_docs(guardados: list, novos: list) -> list:
        """NF-e já confirmadas em consultas anteriores + as desta consulta (que só entram no controle ao salvar)."""
        vistos, saida = set(), []
        for d in list(guardados) + list(novos):
            k = (int(d.get("nsu") or 0), d.get("tipo"), None if int(d.get("nsu") or 0) else hash(d.get("xml")))
            if k not in vistos:
                vistos.add(k)
                saida.append(d)
        return saida

    def _ciencia(self, sessao, emp, senha, cnpj, ano, mes, ctx, log, cancelar, periodos=None):
        h = self.hist
        todos = self._juntar_docs(h.carregar_docs(), ctx["pend_docs"])
        pend = []
        for a, m in (periodos or [(ano, mes)]):          # em lote, a ciência vale para todos os meses marcados (sem repetir chave)
            pend += [c for c in nfe.pendentes_ciencia(todos, cnpj, a, m, h.ciencias()) if c not in pend]
        if not pend:
            return
        log(f"Registrando a Ciência da Operação de {len(pend)} nota(s)...")
        assinador = nfe.carregar_assinador(emp["pfx"], senha)
        res = nfe.enviar_ciencia(sessao, cnpj, pend, assinador, log=log, cancelar=cancelar)
        ok = [c for c, (_, _, certo) in res.items() if certo]
        h.marcar_ciencia(ok)
        ctx["ciencia"] = len(ok)
        falhas = len(pend) - len(ok)
        if falhas:
            ctx["msgs"].append(f"A SEFAZ não aceitou a ciência de {falhas} nota(s); elas seguem só com o resumo.")
        trazidos = []
        for chave in ok[:40]:                    # tenta trazer o XML completo logo depois da ciência
            if cancelar():
                raise Cancelado()
            try:
                r = nfe.consultar_chave(sessao, cnpj, chave)
            except ErroAdge:
                break
            if r["cstat"] == "656":
                break
            if r["cstat"] == "138":
                trazidos += r["docs"]
            time.sleep(self.pausa_chave)
        if trazidos:
            ctx["pend_docs"] += trazidos
            ctx["novos"] += len(trazidos)
        pendentes_xml = len(ok) - sum(1 for d in trazidos if d.get("tipo") == "proc")
        if pendentes_xml > 0:
            ctx["msgs"].append(f"Ciência registrada em {len(ok)} nota(s); {pendentes_xml} ainda sem o XML completo (a SEFAZ costuma "
                               "liberar em alguns minutos: consulte de novo quando o contador permitir).")

    pausa_chave = 0.4

    def _ocupado(self, sim: bool):
        self.trabalhando = sim
        self.b_buscar.config(state="disabled" if sim else "normal")
        for b in self.b_meses + [self.b_ano_menos, self.b_ano_mais, self.b_anterior, self.b_este]:
            b.config(state="disabled" if sim else "normal")
        if sim:
            self.l_status.config(text="Conectando ao ADN...", fg=P.suave)
            self.barra.pack(fill="x", pady=(6, 0), after=self.l_status.master)
            self.barra.iniciar()
            self.b_cancelar.pack(side="right")
        else:
            self.barra.parar()
            self.barra.pack_forget()
            self.b_cancelar.pack_forget()

    def _cancelar_busca(self):
        self.cancelar_flag = True
        self.l_status.config(text="Cancelando...")

    def _ler_fila(self):
        try:
            while True:
                tipo, dado = self.fila.get_nowait()
                if tipo == "log":
                    self.l_status.config(text=dado)
                elif tipo == "ok":
                    self._ocupado(False)
                    self._concluir(*dado)
                elif tipo == "erro":
                    self._ocupado(False)
                    self.l_status.config(text="")
                    ui.erro(self, "Não foi possível buscar as notas", dado)
                elif tipo == "cancelado":
                    self._ocupado(False)
                    self.l_status.config(text="Busca cancelada.")
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(150, self._ler_fila)

    # ------------------------------------------------------------------ histórico: reabrir pela pasta salva
    def _abrir_da_pasta(self):
        """Reabre uma consulta do histórico lendo os XMLs da pasta onde ela foi salva. Não consulta ADN, SEFAZ nem Prefeitura
        e não pede a senha do certificado; só "Buscar notas" faz uma consulta nova."""
        cnpj = re.sub(r"\D", "", self.emp["cnpj"])
        try:
            adn, nf, sp = core.carregar_pasta(self.da_pasta, cnpj)
        except ErroAdge as e:
            self.da_pasta = None
            ui.erro(self, "Não consegui abrir a pasta salva", str(e))
            return
        self.f_res.pack_forget()
        self.f_botoes.pack_forget()
        self.l_destino.pack_forget()
        emp = dict(self.emp, acao="calcular", tipos={"prestado": True, "tomado": True})
        self.lote_periodos, self.lote_dados, self.lote_planos, self._cats_vistas = [], None, {}, set()
        self.consulta = (emp, self.ano, self._mes_num())
        self.docs_paul, self.msgs_paul = (sp if sp else None), []
        ctx = {"docs": nf, "msgs": [], "novos": 0, "ciencia": 0, "consultou": False, "pend_docs": [], "confirmado": True,
               "ult_nsu": 0, "max_nsu": 0} if nf else None
        self.salvo, self.pasta_salva = True, self.da_pasta
        self._concluir(adn, cnpj, ctx)

    # ------------------------------------------------------------------ resultado
    def _categorias_presentes(self, arquivos, resumo) -> list:
        return [c for c in core.ORDEM_CATEGORIAS
                if any(a["cat"] == c for a in arquivos)
                or (c in resumo and ((core.CATEGORIAS[c]["grupo"] == "nfse" and not core.CATEGORIAS[c].get("origem")) or resumo[c]["qtd"] or resumo[c]["canceladas"]))]

    def _avisos_paulistana(self, arquivos, tem_adn) -> list:
        av = ["Nota Paulistana: fonte separada, só para conferência. Fica desmarcada nos totais; marque-a para ver as notas "
              "(marcar junto com as NFS-e do Ambiente Nacional soma as duas fontes)."]
        if not tem_adn:
            return av
        c = paulistana.comparar(arquivos)
        if not c["so_adn"] and not c["so_paulistana"]:
            av.append(f"Conferência: as {c['em_ambos']} nota(s) de serviço batem entre o Ambiente Nacional e a Paulistana.")
            return av
        def lista(itens):
            nums = [str(a["doc"].get("numero") or "?") for a in itens[:8]]
            return ", ".join(nums) + (f" e mais {len(itens) - 8}" if len(itens) > 8 else "")
        av.append(f"Conferência: {c['em_ambos']} nota(s) batem entre as fontes.")
        if c["so_adn"]:
            av.append(f"Só no Ambiente Nacional ({len(c['so_adn'])}): nº {lista(c['so_adn'])}.")
        if c["so_paulistana"]:
            av.append(f"Só na Paulistana ({len(c['so_paulistana'])}): nº {lista(c['so_paulistana'])}.")
        return av

    def _concluir(self, docs, cnpj, ctx=None, reset=True):
        emp, ano, mes = self.consulta
        destino_prev, aviso_dest = None, ""
        if self.pasta_manual:       # em lote, cada mês ganha a sua subpasta (ano\mês) dentro da pasta escolhida
            emp = dict(emp, destino=self.pasta_manual, estrutura="ano_mes" if self.lote_periodos else "direto")
        if self.da_pasta:
            aviso_dest = f"Notas lidas da pasta onde foram salvas: {self.da_pasta}. Nenhuma consulta nova foi feita."
        elif emp["acao"] == "calcular" and not self.pasta_manual:
            aviso_dest = "Só o total: as notas ainda não foram salvas. Use \"Escolher pasta...\" se quiser guardar os XMLs e manter esta consulta no histórico."
        if emp["acao"] != "calcular" or self.pasta_manual:
            try:
                if not str(emp["destino"]).strip():
                    raise ErroAdge("Esta empresa não tem pasta de destino definida.")
                destino_prev, trilha = core.resolver_destino(Path(emp["destino"]), emp["estrutura"], ano, mes, criar=False)
                aviso_dest = "Destino: " + " \\ ".join([Path(emp["destino"]).name] + [n + (" (será criada)" if novo else "") for n, novo in trilha])
            except ErroAdge as e:
                aviso_dest = f"⚠ {e} Use \"Escolher pasta...\" para indicar onde salvar os XMLs."
        extras = {}
        arquivos, resumo, avisos = core.planejar(emp, docs, cnpj, ano, mes, destino_prev, extras,
                                                 docs_nfe=ctx["docs"] if ctx else None, docs_paulistana=self.docs_paul)
        if ctx:
            avisos = list(avisos) + list(ctx["msgs"])
        if self.docs_paul is not None:
            avisos = list(avisos) + list(self.msgs_paul) + self._avisos_paulistana(arquivos, bool(emp["tipos"]["prestado"] or emp["tipos"]["tomado"]))
        # RBT12 básico aproveitando a mesma consulta (o ADN entrega todo o histórico): só com NFS-e prestadas e sem ler de pasta salva
        rbt12 = core.rbt12_nfse(docs, cnpj, ano, mes) if (emp["tipos"]["prestado"] and not self.da_pasta and docs) else None
        self.resultado = {"emp": emp, "docs": docs, "cnpj": cnpj, "ano": ano, "mes": mes, "arquivos": arquivos,
                          "resumo": resumo, "avisos": avisos, "canceladas": extras.get("canceladas", []),
                          "destino_ok": destino_prev is not None, "nfe": ctx, "aviso_dest": aviso_dest, "rbt12_nfse": rbt12}
        self.cats = self._categorias_presentes(arquivos, resumo)
        if reset:
            self.sel.ativos.clear()
            self.sel.ativos |= totais.padrao_ativos(self.cats)
        else:
            self.sel.ativos &= set(self.cats)
            self.sel.ativos |= totais.padrao_ativos([c for c in self.cats if c not in self._cats_vistas])   # categoria nova de outro mês
        self._cats_vistas |= set(self.cats)
        if self.lote_periodos:
            self.lote_dados = (docs, cnpj, ctx)
        if self.da_pasta:
            self.l_status.config(text="Notas lidas da pasta salva (sem nova consulta).")
        else:
            self.l_status.config(text=f"{len(docs)} documento(s) consultados." + (f" · {len(ctx['docs'])} documento(s) de NF-e." if ctx else "")
                                 + (f" · {len(self.lote_periodos)} meses em uma só consulta." if self.lote_periodos else ""))
        self._montar_marcadores()
        self._montar_lote()
        self.l_detalhe.config(text="Selecione uma nota para ver os detalhes.")

        for w in (self.b_avancado, self.b_copiar, self.b_gravar, self.b_pasta, self.b_csv):
            w.pack_forget()
        self.f_acoes_totais.pack_forget()
        self.f_cats.pack_forget()
        self.l_destino.pack_forget()
        mostra_totais = emp["acao"] != "baixar"
        if mostra_totais and len(self.cats) > 1:
            self.f_cats.pack(fill="x", pady=(10, 0), after=self.cards_pos)
        if mostra_totais:
            self.b_avancado.pack(side="left")
            self.b_copiar.pack(side="left", padx=(8, 0))
            self.f_acoes_totais.pack(fill="x", pady=(10, 0))
        # a barra de baixo é empacotada primeiro (side="bottom") para nunca ficar sem espaço quando a lista é grande
        self.f_botoes.pack(side="bottom", fill="x", pady=(12, 0))
        if aviso_dest:
            self.l_destino.config(text=aviso_dest, fg=P.erro if aviso_dest.startswith("⚠") else P.suave)
            self.l_destino.pack(side="bottom", anchor="w", pady=(8, 0))
        self.f_res.pack(fill="both", expand=True, pady=(4, 0))
        if not self.da_pasta:
            if emp["acao"] != "calcular" or self.pasta_manual:
                self.b_gravar.pack(side="left")
            self.b_pasta.pack(side="left", padx=(8, 0))
        if emp["acao"] != "baixar":
            self.b_csv.pack(side="left", padx=(8, 0))
        self._mudou_selecao()
        self.update_idletasks()

    def _tem_lado(self, lado: str) -> bool:
        return any(core.CATEGORIAS[c]["lado"] == lado for c in getattr(self, "cats", []))

    def _montar_marcadores(self):
        for w in self.f_marcas.winfo_children():
            w.destroy()
        self.marcas, ws = {}, []
        por = totais.por_categoria(self.resultado["arquivos"])
        for c in self.cats:
            info = core.CATEGORIAS[c]
            r = por.get(c, {"qtd": 0, "valor": 0.0})
            tom = "amarelo" if c == "nfe_resumo" else {"receita": "verde", "custo": "vermelho"}.get(info["lado"], "neutro")
            var = tk.BooleanVar(value=self.sel.ativa(c))
            self.marcas[c] = var
            ws.append(Marcador(self.f_marcas, f"{info['rotulo']} · {r['qtd']} · {moeda(r['valor'])}", var,
                               lambda c=c, v=var: self.sel.definir(c, v.get()), tom=tom, tam=9))
        ui.fluxo(self.f_marcas, ws)
        dicas = []
        if "nfe_outras" in self.cats:
            dicas.append("Outras operações (remessas, transferências etc.) aparecem na tabela, mas não entram no faturamento, nas compras nem no gráfico.")
        if "nfe_resumo" in self.cats:
            dicas.append("NF-e sem ciência só têm o resumo (sem CFOP nem itens): se marcadas, entram como compra pelo valor total, sem crédito.")
        self.l_marcas_dica.config(text="  ".join(dicas))
        (self.l_marcas_dica.pack if dicas else self.l_marcas_dica.pack_forget)(**({"anchor": "w"} if dicas else {}))

    def _montar_lote(self):
        """Consulta em lote: uma linha de botões (um por mês consultado) para alternar o mês mostrado e o resumo de todos os meses."""
        self.f_lote.pack_forget()
        for w in self.f_lote_botoes.winfo_children():
            w.destroy()
        if not self.lote_periodos or not self.resultado:
            return
        atual = (self.resultado["ano"], self.resultado["mes"])
        ws = []
        for a, m in self.lote_periodos:
            ws.append(Botao(self.f_lote_botoes, f"{core.MESES_TELA[m - 1][:3]}/{a}", lambda a=a, m=m: self._mostrar_periodo(a, m),
                            estilo="primario" if (a, m) == atual else "secundario", padx=10, pady=4, tam=9))
        ui.fluxo(self.f_lote_botoes, ws)
        self.f_lote_botoes.pack(fill="x", pady=(4, 0))
        self.l_lote_resumo.pack(anchor="w")
        self.f_lote.pack(fill="x", pady=(10, 0), before=self.f_bloco)
        self._atualizar_lote()

    def _atualizar_lote(self):
        """Resumo mês a mês (com a seleção atual das categorias) e o total do lote."""
        if not self.lote_periodos or not self.lote_planos:
            return
        linhas, fat, comp = [], 0.0, 0.0
        for a, m in self.lote_periodos:
            soma = totais.totais(self.lote_planos.get((a, m), []), self.sel.ativos)
            fat += soma["faturamento"]
            comp += soma["compras"]
            partes = []
            if self._tem_lado("receita"):
                partes.append(f"faturamento {moeda(soma['faturamento'])}")
            if self._tem_lado("custo"):
                partes.append(f"compras {moeda(soma['compras'])}")
            linhas.append(f"{core.MESES_TELA[m - 1][:3]}/{a}: " + " · ".join(partes))
        tot = []
        if self._tem_lado("receita"):
            tot.append(f"faturamento {moeda(fat)}")
        if self._tem_lado("custo"):
            tot.append(f"compras {moeda(comp)}")
        self.l_lote_resumo.config(text="   |   ".join(linhas) + "\nTotal do lote: " + " · ".join(tot))

    def _mostrar_periodo(self, ano, mes):
        """Troca o mês exibido de uma consulta em lote, sem consultar nada de novo."""
        if self.trabalhando or not self.lote_dados or (ano, mes) == (self.resultado["ano"], self.resultado["mes"]):
            return
        docs, cnpj, ctx = self.lote_dados
        self.consulta = (self.consulta[0], ano, mes)
        self._concluir(docs, cnpj, ctx, reset=False)

    def _mudou_selecao(self):
        """Qualquer mudança nas marcas refaz cartões, tabela e botões; a janela de informações avançadas escuta a mesma seleção."""
        if not self.resultado:
            return
        for c, var in self.marcas.items():
            if var.get() != self.sel.ativa(c):
                var.set(self.sel.ativa(c))
        self._atualizar_totais()
        self._preencher_tabela()
        self._atualizar_botoes()
        self._atualizar_lote()

    def _atualizar_totais(self):
        r = self.resultado
        emp = r["emp"]
        for _, (card, *_r) in self.cards.items():
            card.grid_forget()
        self.c_saldo.grid_forget()
        if emp["acao"] == "baixar":
            return
        soma = totais.totais(r["arquivos"], self.sel.ativos)
        so_nfse = all(core.CATEGORIAS[c]["grupo"] == "nfse" for c in self.cats)
        nomes = {"fat": "Faturamento (serviços prestados)" if so_nfse else "Faturamento",
                 "comp": "Serviços tomados" if so_nfse else "Compras e serviços tomados"}
        for chave, lado, valor in (("fat", "receita", soma["faturamento"]), ("comp", "custo", soma["compras"])):
            card, v, d, col, t = self.cards[chave]
            if not self._tem_lado(lado):
                continue
            cats = [c for c in self.cats if core.CATEGORIAS[c]["lado"] == lado and self.sel.ativa(c)]
            qtd = sum(soma["por_cat"].get(c, {}).get("qtd", 0) for c in cats)
            canc = sum(r["resumo"].get(c, {}).get("canceladas", 0) for c in cats)
            t.config(text=nomes[chave])
            v.config(text=moeda(valor))
            d.config(text=f"{qtd} nota(s)" + (f" · {canc} cancelada(s) fora" if canc else "") if cats else "nenhuma categoria marcada")
            card.grid(row=0, column=col, sticky="nsew", padx=(0, 10))
        if self._tem_lado("receita") and self._tem_lado("custo"):
            saldo = soma["saldo"]
            fundo, cor = ("pos_fundo", "pos_texto") if saldo >= 0 else ("neg_fundo", "neg_texto")
            self.c_saldo.pintar(fundo, fundo)
            for w in (self.l_saldo_t, self.l_saldo_v, self.l_saldo_d):
                w.config(fg=ui._cor(cor))
            self.l_saldo_v.config(text=self._formatar_saldo(saldo))
            self.l_saldo_d.config(text=("Prestado − tomado, antes dos impostos" if so_nfse
                                        else "Faturamento − compras e tomados, antes dos impostos"))
            self.c_saldo.grid(row=0, column=2, sticky="nsew")
        msgs = list(r["avisos"])
        if not any(a["cat"] in self.sel.ativos for a in r["arquivos"]):
            msgs.insert(0, "Nenhuma nota encontrada nesse período." if not r["arquivos"] else "Nenhuma categoria marcada: marque o que quer considerar.")
        self.l_aviso.config(text="\n".join(msgs))
        if msgs:
            self.l_aviso.pack(anchor="w", pady=(8, 0), after=self.f_bloco)
        else:
            self.l_aviso.pack_forget()

    def _atualizar_botoes(self):
        r = self.resultado
        if not r:
            return
        com_xml = [a for a in r["arquivos"] if a["cat"] in self.sel.ativos and not a.get("sem_xml")]
        self.b_gravar.config(state="normal" if com_xml and r["destino_ok"] else "disabled")

    # tabela ------------------------------------------------------------
    @staticmethod
    def _parte(a, cnpj):
        """A outra ponta da nota: se a empresa emitiu, é o tomador/destinatário; senão, o emitente."""
        d = a["doc"]
        return (d.get("tomador_nome") if d.get("emitente_doc") == cnpj else d.get("emitente_nome")) or ""

    def _linhas(self):
        r = self.resultado
        if not r:
            return []
        filtro, txt = self.v_filtro.get(), self.v_texto.get().strip().lower()
        saida = []
        for i, a in enumerate(r["arquivos"]):
            if a["cat"] not in self.sel.ativos:
                continue
            info = core.CATEGORIAS[a["cat"]]
            if filtro in ("receita", "custo") and info["lado"] != filtro:
                continue
            d = a["doc"]
            linha = {"i": i, "tipo": info["tipo"], "numero": d.get("numero") or "",
                     "data": core.formatar_data(d.get("emissao")).replace("-", "/"), "parte": self._parte(a, r["cnpj"]),
                     "valor": d.get("valor") or 0.0, "iso": d.get("emissao") or "", "cat": a["cat"], "lado": info["lado"]}
            if txt and txt not in " ".join(str(linha[k]) for k in ("tipo", "numero", "data", "parte")).lower() \
                    and txt not in moeda(linha["valor"]).lower():
                continue
            saida.append(linha)
        col, desc = self.ordem
        if col:
            def chave(x):
                if col == "valor":
                    return x["valor"]
                if col == "data":
                    return x["iso"]
                if col == "numero":
                    n = str(x["numero"])
                    return (0, int(n)) if n.isdigit() else (1, n)
                return str(x[col]).lower()
            saida.sort(key=chave, reverse=desc)
        return saida

    def _preencher_tabela(self):
        self.tv.delete(*self.tv.get_children())
        for n, x in enumerate(self._linhas()):
            tag = "semciencia" if x["cat"] == "nfe_resumo" else {"receita": "prest", "custo": "tom"}.get(x["lado"], "neutro")
            tags = [tag] + (["alt"] if n % 2 and tag != "semciencia" else [])
            self.tv.insert("", "end", iid=str(x["i"]), tags=tags,
                           values=(x["tipo"], x["numero"], x["data"], x["parte"], moeda(x["valor"])))

    def _ordenar(self, col):
        atual, desc = self.ordem
        self.ordem = (col, not desc) if atual == col else (col, False)
        for c, t, *_ in self.COLUNAS:
            seta = (" ▼" if self.ordem[1] else " ▲") if c == self.ordem[0] else ""
            self.tv.heading(c, text=t + seta)
        self._preencher_tabela()

    def _detalhe(self):
        sel = self.tv.selection()
        if not sel or not self.resultado:
            return
        a = self.resultado["arquivos"][int(sel[0])]
        d, info = a["doc"], core.CATEGORIAS[a["cat"]]
        parte = self._parte(a, self.resultado["cnpj"]) or "—"
        data = core.formatar_data(d.get("emissao")).replace("-", "/")
        if a["cat"] == "nfe_resumo":
            ciencia = "ciência enviada, aguardando o XML completo" if d.get("ciencia_enviada") else "sem ciência da operação"
            self.l_detalhe.config(text=f"NF-e {d.get('numero', '')} — só o resumo ({ciencia}): sem CFOP, itens ou impostos  ·  "
                                       f"Emitente {parte}  ·  Emitida em {data}  ·  Valor {moeda(d.get('valor') or 0)}")
            return
        if info["grupo"] == "nfe":
            partes = [f"NF-e {d.get('numero', '')} série {d.get('serie') or '—'} — {info['rotulo']} · {parte}",
                      f"Emitida em {data}", f"Valor {moeda(d.get('valor') or 0)}"]
            if d.get("cfops"):
                partes.append("CFOP " + ", ".join(f"{c[0]}.{c[1:]}" for c in d["cfops"]))
            if d.get("natureza"):
                partes.append(str(d["natureza"])[:60])
            if d.get("icms"):
                partes.append(f"ICMS {moeda(d['icms'])}")
            if d.get("cat_mista"):
                partes.append("operação mista: classificada pela maior parte")
            self.l_detalhe.config(text="  ·  ".join(partes))
            return
        prestado = info["lado"] == "receita"
        partes = [f"Nota {d.get('numero', '')} — {'prestada a' if prestado else 'tomada de'} {parte}",
                  f"Emitida em {data}", f"Valor {moeda(d.get('valor') or 0)}"]
        if d.get("iss"):
            al = d.get("iss_aliquota")
            partes.append(f"ISS {moeda(d['iss'])}" + (f" ({str(al).replace('.', ',')}%)" if al else ""))
        if d.get("servico_cod") or d.get("servico_desc"):
            partes.append(f"Serviço: {d.get('servico_cod') or ''} {str(d.get('servico_desc') or '')[:140]}".strip())
        self.l_detalhe.config(text="  ·  ".join(partes))

    # ------------------------------------------------------------------ ações
    def _avancado(self):
        if not self.resultado or not self.resultado["arquivos"]:
            return
        from .avancado import DialogoAvancado
        DialogoAvancado(self, self.store, self.emp, self.resultado, self.sel)

    def _escolher_pasta(self):
        if not self.resultado:
            return
        base = self.pasta_manual or self.resultado["emp"].get("destino") or self.store.preferencias.get("raiz_padrao") or str(Path.home())
        c = filedialog.askdirectory(parent=self, title="Escolha a pasta onde salvar os XMLs",
                                    initialdir=base if Path(base).is_dir() else str(Path.home()))
        if not c:
            return
        self.pasta_manual = os.path.normpath(c)
        r = self.resultado
        self._concluir(r["docs"], r["cnpj"], r.get("nfe"), reset=False)

    def _gravar(self):
        r = self.resultado
        if not r:
            return
        if self.lote_periodos and self.lote_dados:
            self._gravar_lote()
            return
        n = len([a for a in r["arquivos"] if a["cat"] in self.sel.ativos and not a.get("sem_xml")])
        if not n:
            return
        if not ui.perguntar(self, f"Gravar {n} XML(s)?", f"Pasta:\n{self.l_destino.cget('text').replace('Destino: ', '')}\n\n"
                                                         "Arquivos que já existirem não serão sobrescritos.", sim="Gravar", nao="Cancelar"):
            return
        try:
            destino, contagem = core.salvar_notas(r["emp"], r["arquivos"], r["resumo"], r["cnpj"], r["ano"], r["mes"],
                                                  canceladas=r["canceladas"], ativos=self.sel.ativos)
        except (ErroAdge, OSError) as e:
            ui.erro(self, "Não consegui gravar os arquivos", str(e))
            return
        self.salvo, self.pasta_salva = True, str(destino)
        self._registrar_salvo(destino)
        resumo = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in contagem.items())
        if ui.perguntar(self, "Pronto!", f"{resumo}.\n\nPasta:\n{destino}", sim="Abrir a pasta", nao="Fechar"):
            ui.abrir_pasta(destino)

    def _gravar_lote(self):
        """Consulta em lote: grava cada mês marcado na sua pasta (mesma regra de pastas de um mês só), registra cada um no
        histórico e só no fim confirma o NSU da NF-e (uma vez, pois a SEFAZ foi consultada uma vez só)."""
        r = self.resultado
        docs, cnpj, ctx = self.lote_dados
        emp = r["emp"]
        if not ui.perguntar(self, f"Gravar os XMLs de {len(self.lote_periodos)} meses?",
                            f"Meses: {core.formatar_periodos(self.lote_periodos)}.\n\nCada mês vai para a sua pasta, do mesmo jeito que numa consulta de um mês só "
                            "(com \"Escolher pasta...\", dentro da pasta escolhida, em ano\\mês). Arquivos que já existirem não serão sobrescritos.",
                            sim="Gravar", nao="Cancelar"):
            return
        gravados, vazios, falhas, pastas = 0, [], [], []
        for a, m in self.lote_periodos:
            nome = f"{core.MESES_TELA[m - 1][:3]}/{a}"
            try:
                destino_prev, _ = core.resolver_destino(Path(emp["destino"]), emp["estrutura"], a, m, criar=False)
                extras = {}
                arquivos, resumo, _av = core.planejar(emp, docs, cnpj, a, m, destino_prev, extras,
                                                      docs_nfe=ctx["docs"] if ctx else None, docs_paulistana=self.docs_paul)
                if not any(x["cat"] in self.sel.ativos and not x.get("sem_xml") for x in arquivos):
                    vazios.append(nome)
                    continue
                destino, contagem = core.salvar_notas(emp, arquivos, resumo, cnpj, a, m, canceladas=extras.get("canceladas", []),
                                                      ativos=self.sel.ativos)
            except (ErroAdge, OSError) as e:
                falhas.append(f"{nome}: {e}")
                continue
            gravados += sum(contagem.values())
            pastas.append(str(destino))
            self._registrar_salvo_periodo(a, m, arquivos, resumo, destino)
        if pastas:
            self.salvo, self.pasta_salva = True, pastas[-1]
            self._confirmar_nsu(self.resultado)
        texto = f"{gravados} XML(s) em {len(pastas)} mês(es)."
        if vazios:
            texto += f"\nSem notas marcadas (nada a gravar): {', '.join(vazios)}."
        if falhas:
            texto += "\n\nNão consegui gravar:\n" + "\n".join(falhas)
        if pastas:
            texto += f"\n\nÚltima pasta:\n{pastas[-1]}"
            if ui.perguntar(self, "Pronto!", texto, sim="Abrir a pasta", nao="Fechar"):
                ui.abrir_pasta(pastas[-1])
        else:
            ui.erro(self, "Não consegui gravar os arquivos", texto)

    def _registrar_salvo_periodo(self, ano, mes, arquivos, resumo, destino):
        """Entrada do histórico de um mês (só depois de salvar)."""
        soma = totais.totais(arquivos, self.sel.ativos)
        registrar_historico(self.store, self.emp, ano, mes, resumo, len(arquivos),
                            soma["faturamento"] if self._tem_lado("receita") else None,
                            soma["compras"] if self._tem_lado("custo") else None, pasta=str(destino))

    def _registrar_salvo(self, destino):
        """Só depois de salvar: a consulta entra no histórico (com o caminho da pasta) e o NSU da NF-e avança."""
        r = self.resultado
        self._registrar_salvo_periodo(r["ano"], r["mes"], r["arquivos"], r["resumo"], destino)
        self._confirmar_nsu(r)

    def _confirmar_nsu(self, r):
        ctx = r.get("nfe")
        if ctx and ctx.get("consultou") and not ctx.get("confirmado") and self.hist is not None:
            try:
                self.hist.confirmar(ctx["pend_docs"], ctx["ult_nsu"], ctx["max_nsu"])
                ctx["confirmado"] = True
            except OSError as e:
                ui.avisar(self, "Não consegui guardar o controle da NF-e", f"{e}\n\nAs notas foram salvas na pasta, mas a próxima consulta "
                                                                              "de NF-e vai repetir as mesmas notas.")
        sub = ctx.get("resp") if ctx else None
        if sub and sub.get("consultou") and not sub.get("confirmado") and self.hist_resp is not None:
            try:
                self.hist_resp.confirmar(sub["pend_docs"], sub["ult_nsu"], sub["max_nsu"])
                sub["confirmado"] = True
            except OSError as e:
                ui.avisar(self, "Não consegui guardar o controle da NF-e do responsável",
                          f"{e}\n\nAs notas foram salvas na pasta, mas a próxima consulta pelo responsável vai repetir as mesmas notas.")

    def _fontes_pendentes(self, ctx) -> list:
        """Históricos de NF-e (empresa e/ou responsável) consultados nesta busca cujo NSU ainda não foi confirmado (nada salvo)."""
        saida = []
        if ctx and ctx.get("consultou") and not ctx.get("confirmado") and self.hist is not None:
            saida.append(self.hist)
        sub = ctx.get("resp") if ctx else None
        if sub and sub.get("consultou") and not sub.get("confirmado") and self.hist_resp is not None:
            saida.append(self.hist_resp)
        return saida

    @staticmethod
    def _formatar_saldo(v: float) -> str:
        return ("-" if v < 0 else "") + moeda(abs(v))

    def _texto_totais(self) -> str:
        r = self.resultado
        soma = totais.totais(r["arquivos"], self.sel.ativos)
        so_nfse = all(core.CATEGORIAS[c]["grupo"] == "nfse" for c in self.cats)
        linhas = [f"{r['emp']['nome']} — {core.mes_exibicao(r['mes'])}/{r['ano']}"]
        for lado, nome in (("receita", "Faturamento (serviços prestados)" if so_nfse else "Faturamento"),
                           ("custo", "Serviços tomados" if so_nfse else "Compras e serviços tomados")):
            if self._tem_lado(lado):
                v = soma["faturamento"] if lado == "receita" else soma["compras"]
                cats = [c for c in self.cats if core.CATEGORIAS[c]["lado"] == lado and self.sel.ativa(c)]
                qtd = sum(soma["por_cat"].get(c, {}).get("qtd", 0) for c in cats)
                linhas.append(f"{nome}: {moeda(v)} ({qtd} nota(s))")
        if self._tem_lado("receita") and self._tem_lado("custo"):
            linhas.append(f"Saldo líquido (antes dos impostos): {self._formatar_saldo(soma['saldo'])}")
        marc = [core.CATEGORIAS[c]["rotulo"] for c in self.cats if self.sel.ativa(c)]
        if marc:
            linhas.append("Considerado: " + ", ".join(marc))
        return "\n".join(linhas)

    def _copiar(self):
        if self.resultado:
            self.clipboard_clear()
            self.clipboard_append(self._texto_totais())
            self.l_status.config(text="Totais copiados.")

    def _exportar_planilha(self):
        r = self.resultado
        if not r:
            return
        caminho = filedialog.asksaveasfilename(parent=self, defaultextension=".xlsx", filetypes=[("Planilha Excel", "*.xlsx")],
                                               initialfile=core.nome_planilha(r["mes"], r["ano"]))
        if not caminho:
            return
        try:
            from . import planilha
            planilha.gerar_xlsx(caminho, r["emp"]["nome"], r["ano"], r["mes"], r["arquivos"], r["resumo"], r["canceladas"], ativos=self.sel.ativos)
        except PermissionError:
            ui.erro(self, "Não consegui salvar a planilha", "Se ela estiver aberta no Excel, feche-a e tente de novo.")
            return
        except (OSError, ImportError) as e:
            ui.erro(self, "Não consegui criar a planilha", str(e))
            return
        self.l_status.config(text="Planilha salva.")
        if ui.perguntar(self, "Planilha salva", "Quer abrir a pasta onde ela ficou?", sim="Abrir a pasta", nao="Agora não"):
            ui.abrir_pasta(Path(caminho).parent)

    def _tem_nao_salvo(self) -> bool:
        r = self.resultado
        if not r or self.salvo or self.da_pasta:
            return False
        return any(a["cat"] in self.sel.ativos and not a.get("sem_xml") for a in r["arquivos"])

    def _fechar(self):
        if self.trabalhando:
            self.cancelar_flag = True
        elif self._tem_nao_salvo():
            texto = ("Você ainda não salvou as notas desta consulta em nenhuma pasta.\n\n"
                     "Se sair agora, esta consulta não entra no histórico e, para ver estas notas de novo, o sistema terá de consultar tudo outra vez.")
            bloqueados = [h for h in self._fontes_pendentes(self.resultado.get("nfe")) if h.bloqueado()]
            if bloqueados:
                texto += (f"\n\nAtenção: a SEFAZ já bloqueou novas consultas de NF-e (libera às {max(h.liberado_as() for h in bloqueados):%H:%M}). "
                          "Sem salvar, as NF-e desta consulta só voltam depois disso.")
            escolha = ui.escolher(self, "As notas não foram salvas", texto,
                                  [("Voltar", "voltar", "secundario"), ("Sair sem salvar", "sair", "secundario"),
                                   ("Salvar numa pasta", "salvar", "primario")])
            if escolha == "salvar":
                self._salvar_e_fechar()
                return
            if escolha != "sair":
                return
        self.destroy()

    def _salvar_e_fechar(self):
        r = self.resultado
        if not self.pasta_manual and (r["emp"]["acao"] == "calcular" or not r["destino_ok"]):
            self._escolher_pasta()
            if not self.pasta_manual:
                return
        self._gravar()
        if self.salvo:
            self.destroy()
