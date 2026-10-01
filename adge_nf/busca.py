"""Janela de busca de notas: escolhe o mês, consulta o ADN, mostra totais e notas e grava os XMLs."""
import datetime as dt
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from . import NOME_APP, core
from . import ui
from .core import Cancelado, ErroAdge
from .store import Armazenamento
from .ui import P, Botao, Campo, Cartao, Chip, Interruptor, Modal, Segmentado, F, px, rotulo

formatar_cnpj = ui.formatar_cnpj
HISTORICO_MAX = 30


def moeda(v: float) -> str:
    return core.formatar_valor(v).replace("R$", "R$ ")


def mes_anterior(hoje: dt.date = None):
    hoje = hoje or dt.date.today()
    return (hoje.year - 1, 12) if hoje.month == 1 else (hoje.year, hoje.month - 1)


def registrar_historico(store: Armazenamento, emp: dict, ano: int, mes: int, resumo: dict, qtd: int):
    """Guarda a consulta no histórico (só um resumo: sem notas, sem senhas). Máximo de 30 entradas, a mais nova primeiro."""
    prest = resumo.get("servico_prestado", {}).get("valor")
    tom = resumo.get("servico_tomado", {}).get("valor")
    h = store.preferencias.setdefault("historico", [])
    h[:] = [x for x in h if not (x.get("empresa_id") == emp["id"] and x.get("ano") == ano and x.get("mes") == mes)]
    h.insert(0, {"empresa_id": emp["id"], "nome": emp["nome"], "ano": ano, "mes": mes, "notas": qtd,
                 "quando": dt.datetime.now().isoformat(timespec="minutes"), "prestado": prest, "tomado": tom})
    del h[HISTORICO_MAX:]
    try:
        store.salvar()
    except OSError:
        pass


class DialogoBusca(Modal):
    COLUNAS = (("tipo", "Tipo", 90, "w"), ("numero", "Nº", 70, "e"), ("data", "Data", 92, "w"),
               ("parte", "Cliente / Fornecedor", 330, "w"), ("valor", "Valor", 120, "e"))

    def __init__(self, pai, store: Armazenamento, emp: dict, sessao=None, periodo=None, auto=False):
        super().__init__(pai, f"Buscar notas — {emp['nome']}", margem=22)
        self.store, self.emp, self.sessao_teste = store, dict(emp), sessao
        self.fila: "queue.Queue" = queue.Queue()
        self.cancelar_flag = False
        self.trabalhando = False
        self.resultado = None
        self.pasta_manual = ""
        self.ordem = (None, False)
        self.ano, mes = periodo if periodo else mes_anterior()
        self.v_mes = tk.StringVar(value=core.MESES_TELA[mes - 1])
        self.v_prest = tk.BooleanVar(value=emp["tipos"].get("prestado", True))
        self.v_tom = tk.BooleanVar(value=emp["tipos"].get("tomado", True))
        self.v_nfe = tk.BooleanVar(value=False)
        self.v_acao = tk.StringVar(value=emp["acao"])
        self.v_filtro = tk.StringVar(value="todas")
        self.v_texto = tk.StringVar()
        self.resizable(True, True)
        self._montar()
        tela_h = self.winfo_screenheight()
        self.geometry(f"{px(1080)}x{min(px(800), tela_h - px(90))}")
        self.minsize(px(900), px(560))
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self.bind("<Escape>", lambda *_: self._fechar())
        self.bind("<Control-e>", lambda *_: self.resultado and self._exportar_planilha())
        self.bind("<F5>", lambda *_: self._buscar())
        self.mostrar()
        self.after(150, self._ler_fila)
        if auto:
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
        self.l_periodo = rotulo(esq, "", 10, cor="suave")
        self.l_periodo.pack(anchor="w", pady=(2, 0))

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
        Interruptor(tipos, "Serviço tomado", self.v_tom).pack(side="left")
        rotulo(dir_, "O que fazer", 11, "bold", "verde_escuro").pack(anchor="w", pady=(12, 4))
        self.seg_acao = Segmentado(dir_, [("ambos", "Total e XMLs"), ("calcular", "Só o total"), ("baixar", "Só os XMLs")], self.v_acao)
        self.seg_acao.pack(anchor="w")
        self._atualizar_meses()

        st = tk.Frame(self, bg=P.fundo)
        st.pack(fill="x", pady=(10, 0))
        self.l_status = rotulo(st, "", 10, cor="suave")
        self.l_status.pack(side="left")
        self.b_cancelar = Botao(st, "Cancelar busca", self._cancelar_busca, pady=4)
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
        self.f_bloco = tk.Frame(pai, bg=P.fundo)
        self.f_bloco.pack(fill="x", pady=(12, 0))
        cards = tk.Frame(self.f_bloco, bg=P.fundo)
        cards.pack(fill="x")
        for c in range(3):
            cards.columnconfigure(c, weight=1, uniform="tot")
        self.cards = {}
        for col, (chave, nome, cor) in enumerate((("prestado", "Faturamento (serviços prestados)", "pos_texto"),
                                                  ("tomado", "Serviços tomados", "neg_texto"))):
            c = Cartao(cards, pad=12)
            rotulo(c.corpo, nome, 9, "bold", "suave").pack(anchor="w")
            v = rotulo(c.corpo, "—", 19, "bold", cor)
            v.pack(anchor="w")
            d = rotulo(c.corpo, "", 9, cor="suave")
            d.pack(anchor="w")
            self.cards[chave] = (c, v, d, col)
        self.c_saldo = Cartao(cards, fundo="pos_fundo", borda="pos_fundo", pad=12)
        self.l_saldo_t = rotulo(self.c_saldo.corpo, "Saldo líquido", 9, "bold", "pos_texto")
        self.l_saldo_v = rotulo(self.c_saldo.corpo, "—", 19, "bold", "pos_texto")
        self.l_saldo_d = rotulo(self.c_saldo.corpo, "Prestado − tomado, antes dos impostos", 9, cor="pos_texto")
        for w in (self.l_saldo_t, self.l_saldo_v, self.l_saldo_d):
            w.pack(anchor="w")
        self.cards_pos = cards
        self.f_acoes_totais = tk.Frame(self.f_bloco, bg=P.fundo)
        self.b_avancado = Botao(self.f_acoes_totais, "Informações avançadas", self._avancado, estilo="suave", pady=6)
        self.b_copiar = Botao(self.f_acoes_totais, "Copiar totais", self._copiar, pady=6)
        self.l_aviso = rotulo(pai, "", 10, cor="aviso_texto", largura=px(900))
        self.l_aviso.pack(anchor="w", pady=(8, 0))

        barra = tk.Frame(pai, bg=P.fundo)
        barra.pack(fill="x", pady=(10, 6))
        self.seg_filtro = Segmentado(barra, [("todas", "Todas"), ("prestado", "Prestado"), ("tomado", "Tomado")],
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
        self.tv.tag_configure("alt", background=P.linha_alt)
        self.tv.bind("<<TreeviewSelect>>", lambda *_: self._detalhe())
        self.l_detalhe = rotulo(pai, "Selecione uma nota para ver os detalhes.", 10, cor="suave", largura=px(900))
        self.l_detalhe.pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------------ período
    def _mes_num(self) -> int:
        return core.MESES_TELA.index(self.v_mes.get()) + 1

    def _atualizar_meses(self):
        sel = self._mes_num()
        for i, b in enumerate(self.b_meses):
            b.config(style="primario" if i + 1 == sel else "secundario")
        ini, fim = core.limites_mes(self.ano, sel)
        self.l_periodo.config(text=f"{core.MESES_TELA[sel - 1]} de {self.ano}  ·  de {ini:%d/%m/%Y} a {fim:%d/%m/%Y}")
        self.l_ano.config(text=str(self.ano))

    def _atualizar_periodo(self):
        self._atualizar_meses()

    def _escolher_mes(self, i):
        self.v_mes.set(core.MESES_TELA[i])
        self._atualizar_meses()

    def _mudar_ano(self, d):
        novo = self.ano + d
        if 2000 <= novo <= 2100:
            self.ano = novo
            self._atualizar_meses()

    def _ir_mes_anterior(self):
        self.ano, m = mes_anterior()
        self.v_mes.set(core.MESES_TELA[m - 1])
        self._atualizar_meses()

    def _ir_este_mes(self):
        h = dt.date.today()
        self.ano = h.year
        self.v_mes.set(core.MESES_TELA[h.month - 1])
        self._atualizar_meses()

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
        if not (emp["tipos"]["prestado"] or emp["tipos"]["tomado"]):
            ui.avisar(self, "Marque pelo menos um tipo de nota", "Escolha serviço prestado, serviço tomado ou os dois.")
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
        self.f_res.pack_forget()
        self.f_botoes.pack_forget()
        self.l_destino.pack_forget()
        self.cancelar_flag = False
        self._ocupado(True)
        mes, ano = self._mes_num(), self.ano
        self.consulta = (emp, ano, mes)

        def trabalho():
            try:
                docs, cnpj = core.buscar(emp, senha, ano, mes, log=lambda m: self.fila.put(("log", m)),
                                         cancelar=lambda: self.cancelar_flag, sessao=self.sessao_teste)
                self.fila.put(("ok", (docs, cnpj)))
            except Cancelado:
                self.fila.put(("cancelado", None))
            except ErroAdge as e:
                self.fila.put(("erro", str(e)))
            except Exception as e:  # nunca deixar a janela travada
                self.fila.put(("erro", f"Erro inesperado: {e}"))

        threading.Thread(target=trabalho, daemon=True).start()

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

    # ------------------------------------------------------------------ resultado
    def _concluir(self, docs, cnpj):
        emp, ano, mes = self.consulta
        destino_prev, aviso_dest = None, ""
        if self.pasta_manual:
            emp = dict(emp, destino=self.pasta_manual, estrutura="direto")
        if emp["acao"] != "calcular":
            try:
                if not str(emp["destino"]).strip():
                    raise ErroAdge("Esta empresa não tem pasta de destino definida.")
                destino_prev, trilha = core.resolver_destino(Path(emp["destino"]), emp["estrutura"], ano, mes, criar=False)
                aviso_dest = "Destino: " + " \\ ".join([Path(emp["destino"]).name] + [n + (" (será criada)" if novo else "") for n, novo in trilha])
            except ErroAdge as e:
                aviso_dest = f"⚠ {e} Use \"Escolher pasta...\" para indicar onde salvar os XMLs."
        extras = {}
        arquivos, resumo, avisos = core.planejar(emp, docs, cnpj, ano, mes, destino_prev, extras)
        self.resultado = {"emp": emp, "docs": docs, "cnpj": cnpj, "ano": ano, "mes": mes, "arquivos": arquivos,
                          "resumo": resumo, "avisos": avisos, "canceladas": extras.get("canceladas", []),
                          "destino_ok": destino_prev is not None}
        if not self.pasta_manual:
            registrar_historico(self.store, self.emp, ano, mes, resumo, len(arquivos))
        self.l_status.config(text=f"{len(docs)} documento(s) consultados.")
        mostrar_totais = emp["acao"] != "baixar"
        for chave, cat in (("prestado", "servico_prestado"), ("tomado", "servico_tomado")):
            card, v, d, col = self.cards[chave]
            card.grid_forget()
            if mostrar_totais and cat in resumo:
                r = resumo[cat]
                v.config(text=moeda(r["valor"]))
                d.config(text=f"{r['qtd']} nota(s)" + (f" · {r['canceladas']} cancelada(s) fora" if r["canceladas"] else ""))
                card.grid(row=0, column=col, sticky="nsew", padx=(0, 10))
        self.c_saldo.grid_forget()
        saldo = self._saldo(resumo)
        if mostrar_totais and saldo is not None:
            fundo, cor = ("pos_fundo", "pos_texto") if saldo >= 0 else ("neg_fundo", "neg_texto")
            self.c_saldo.pintar(fundo, fundo)
            for w in (self.l_saldo_t, self.l_saldo_v, self.l_saldo_d):
                w.config(fg=ui._cor(cor))
            self.l_saldo_v.config(text=self._formatar_saldo(saldo))
            self.c_saldo.grid(row=0, column=2, sticky="nsew")
        msgs = list(avisos)
        if not arquivos:
            msgs.insert(0, "Nenhuma nota encontrada nesse período.")
        self.l_aviso.config(text="\n".join(msgs))
        self._preencher_tabela()
        self.l_detalhe.config(text="Selecione uma nota para ver os detalhes.")

        for w in (self.b_avancado, self.b_copiar, self.b_gravar, self.b_pasta, self.b_csv):
            w.pack_forget()
        self.f_acoes_totais.pack_forget()
        self.l_destino.pack_forget()
        if emp["acao"] != "baixar":
            if arquivos:
                self.b_avancado.pack(side="left")
            self.b_copiar.pack(side="left", padx=(8, 0) if arquivos else (0, 0))
            self.f_acoes_totais.pack(fill="x", pady=(10, 0))
        # a barra de baixo é empacotada primeiro (side="bottom") para nunca ficar sem espaço quando a lista é grande
        self.f_botoes.pack(side="bottom", fill="x", pady=(12, 0))
        if emp["acao"] != "calcular" and aviso_dest:
            self.l_destino.config(text=aviso_dest, fg=P.erro if aviso_dest.startswith("⚠") else P.suave)
            self.l_destino.pack(side="bottom", anchor="w", pady=(8, 0))
        self.f_res.pack(fill="both", expand=True, pady=(4, 0))
        if emp["acao"] != "calcular":
            self.b_gravar.config(state="normal" if arquivos and self.resultado["destino_ok"] else "disabled")
            self.b_gravar.pack(side="left")
            self.b_pasta.pack(side="left", padx=(8, 0))
        if emp["acao"] != "baixar":
            self.b_csv.pack(side="left", padx=(8, 0))
        self.update_idletasks()

    # tabela ------------------------------------------------------------
    def _linhas(self):
        r = self.resultado
        if not r:
            return []
        filtro, txt = self.v_filtro.get(), self.v_texto.get().strip().lower()
        saida = []
        for i, a in enumerate(r["arquivos"]):
            d = a["doc"]
            prestado = a["cat"] == "servico_prestado"
            if (filtro == "prestado" and not prestado) or (filtro == "tomado" and prestado):
                continue
            parte = (d.get("tomador_nome") if prestado else d.get("emitente_nome")) or ""
            linha = {"i": i, "tipo": "Prestado" if prestado else "Tomado", "numero": d.get("numero") or "",
                     "data": core.formatar_data(d.get("emissao")).replace("-", "/"), "parte": parte, "valor": d.get("valor") or 0.0,
                     "iso": d.get("emissao") or ""}
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
            tags = ["prest" if x["tipo"] == "Prestado" else "tom"] + (["alt"] if n % 2 else [])
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
        d = a["doc"]
        prestado = a["cat"] == "servico_prestado"
        partes = [f"Nota {d.get('numero', '')} — {'prestada a' if prestado else 'tomada de'} "
                  f"{(d.get('tomador_nome') if prestado else d.get('emitente_nome')) or '—'}",
                  f"Emitida em {core.formatar_data(d.get('emissao')).replace('-', '/')}", f"Valor {moeda(d.get('valor') or 0)}"]
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
        DialogoAvancado(self, self.store, self.emp, self.resultado)

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
        self._concluir(r["docs"], r["cnpj"])

    def _gravar(self):
        r = self.resultado
        if not r:
            return
        n = len(r["arquivos"])
        if not ui.perguntar(self, f"Gravar {n} XML(s)?", f"Pasta:\n{self.l_destino.cget('text').replace('Destino: ', '')}\n\n"
                                                         "Arquivos que já existirem não serão sobrescritos.", sim="Gravar", nao="Cancelar"):
            return
        try:
            destino, contagem = core.salvar_notas(r["emp"], r["arquivos"], r["resumo"], r["cnpj"], r["ano"], r["mes"],
                                                  canceladas=r["canceladas"])
        except (ErroAdge, OSError) as e:
            ui.erro(self, "Não consegui gravar os arquivos", str(e))
            return
        resumo = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in contagem.items())
        if ui.perguntar(self, "Pronto!", f"{resumo}.\n\nPasta:\n{destino}", sim="Abrir a pasta", nao="Fechar"):
            ui.abrir_pasta(destino)

    @staticmethod
    def _saldo(resumo: dict):
        """Prestado − tomado (sem impostos). None se faltar um dos dois tipos."""
        if "servico_prestado" in resumo and "servico_tomado" in resumo:
            return round(resumo["servico_prestado"]["valor"] - resumo["servico_tomado"]["valor"], 2)
        return None

    @staticmethod
    def _formatar_saldo(v: float) -> str:
        return ("-" if v < 0 else "") + moeda(abs(v))

    def _texto_totais(self) -> str:
        r = self.resultado
        linhas = [f"{r['emp']['nome']} — {core.mes_exibicao(r['mes'])}/{r['ano']}"]
        for cat, nome in (("servico_prestado", "Faturamento (serviços prestados)"), ("servico_tomado", "Serviços tomados")):
            if cat in r["resumo"]:
                x = r["resumo"][cat]
                linhas.append(f"{nome}: {moeda(x['valor'])} ({x['qtd']} nota(s))")
        saldo = self._saldo(r["resumo"])
        if saldo is not None:
            linhas.append(f"Saldo líquido (prestado − tomado, antes dos impostos): {self._formatar_saldo(saldo)}")
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
            planilha.gerar_xlsx(caminho, r["emp"]["nome"], r["ano"], r["mes"], r["arquivos"], r["resumo"], r["canceladas"])
        except PermissionError:
            ui.erro(self, "Não consegui salvar a planilha", "Se ela estiver aberta no Excel, feche-a e tente de novo.")
            return
        except (OSError, ImportError) as e:
            ui.erro(self, "Não consegui criar a planilha", str(e))
            return
        self.l_status.config(text="Planilha salva.")
        if ui.perguntar(self, "Planilha salva", "Quer abrir a pasta onde ela ficou?", sim="Abrir a pasta", nao="Agora não"):
            ui.abrir_pasta(Path(caminho).parent)

    def _fechar(self):
        if self.trabalhando:
            self.cancelar_flag = True
        self.destroy()
