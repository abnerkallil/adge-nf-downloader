"""Janela "Informações avançadas": gráfico de pizza do período e comparativo de regimes tributários (simulação)."""
import math
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk

from . import NOME_APP, SITE_ADGE, core, grafico, regimes
from .app import BORDA, BRANCO, CINZA, ERRO, TEXTO, VERDE, VERDE_CLARO, VERDE_ESC, AbaRolavel, Modal, botao, centralizar
from .core import ErroAdge

AVISO_LEGAL = ("Simulação estimada, feita com as notas do período e os dados informados. Não considera retenções, benefícios, "
               "créditos reais, RAT/terceiros nem a tributação de lucros e dividendos, e não substitui a análise de um contador. "
               "Alíquotas e regras conforme out/2026; a CBS de 2027 é uma estimativa (a alíquota oficial será fixada pelo Senado).")


def num_br(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v: float) -> str:
    return f"{v * 100:.2f}".replace(".", ",") + "%"


# ============================================================================= dados fiscais
class DialogoConfirmaFiscal(Modal):
    """Mostra os dados já cadastrados e pede para confirmar antes de usá-los."""

    def __init__(self, pai, fiscal: dict):
        super().__init__(pai, "Dados usados na análise")
        self.resultado = None
        ttk.Label(self, text="Confirme os dados da empresa", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(self, style="Muted.TLabel", wraplength=420, justify="left",
                  text="A análise usa estas informações, que ficaram salvas neste computador. Se algo mudou, edite antes de continuar."
                  ).pack(anchor="w", pady=(2, 10))
        f = {**regimes.fiscal_padrao(), **fiscal}
        linhas = [("Regime atual", regimes.NOMES.get(f["regime"], "—")),
                  ("Receita bruta dos últimos 12 meses", "R$ " + num_br(f["rbt12"])),
                  ("Folha de pagamento dos últimos 12 meses", "R$ " + num_br(f["folha12"])),
                  ("Simples: anexo", "Conforme o Fator R (III ou V)" if f["fator_r"] else f"Anexo {f['anexo']}"),
                  ("ISS do município", pct(f["iss_aliquota"])),
                  ("Presunção (Lucro Presumido)", f"{f['presuncao']}%"),
                  ("Outras despesas mensais", "R$ " + num_br(f["outras_despesas"])),
                  ("Profissão regulamentada (reforma)", "Sim" if f["profissao_regulamentada"] else "Não")]
        quadro = ttk.Frame(self, style="Card.TFrame", padding=12)
        quadro.pack(fill="x")
        for i, (k, v) in enumerate(linhas):
            ttk.Label(quadro, text=k, style="Card.TLabel").grid(row=i, column=0, sticky="w", pady=2)
            ttk.Label(quadro, text=v, style="Card.TLabel", font=("Segoe UI Semibold", 10)).grid(row=i, column=1, sticky="e", padx=(24, 0))
        quadro.columnconfigure(1, weight=1)
        lin = ttk.Frame(self)
        lin.pack(fill="x", pady=(14, 0))
        botao(lin, "Agora não", self.destroy).pack(side="right")
        botao(lin, "Editar dados", lambda: self._fim("editar")).pack(side="right", padx=(0, 8))
        botao(lin, "Usar estes dados", lambda: self._fim("usar"), primario=True).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda *_: self.destroy())
        self.mostrar()

    def _fim(self, r):
        self.resultado = r
        self.destroy()


class DialogoDadosFiscais(Modal):
    def __init__(self, pai, store, emp: dict):
        super().__init__(pai, "Dados fiscais da empresa")
        self.store, self.emp, self.salvou = store, emp, False
        f = {**regimes.fiscal_padrao(), **(emp.get("fiscal") or {})}
        ttk.Label(self, text="Dados fiscais da empresa", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(self, style="Muted.TLabel", wraplength=480, justify="left",
                  text="Usados só para a simulação de regimes. Ficam salvos neste computador, junto com a empresa, "
                       "e a busca de notas continua de onde parou."
                  ).pack(anchor="w", pady=(2, 10))
        g = ttk.Frame(self)
        g.pack(fill="x")
        self.v_regime = tk.StringVar(value=regimes.NOMES.get(f["regime"], regimes.NOMES["simples"]))
        self.v_rbt = tk.StringVar(value=num_br(f["rbt12"]) if f["rbt12"] else "")
        self.v_folha = tk.StringVar(value=num_br(f["folha12"]) if f["folha12"] else "")
        self.v_anexo = tk.StringVar(value=f["anexo"])
        self.v_fator = tk.BooleanVar(value=f["fator_r"])
        self.v_iss = tk.StringVar(value=f"{f['iss_aliquota'] * 100:.2f}".replace(".", ","))
        self.v_presuncao = tk.StringVar(value=f"{f['presuncao']}%")
        self.v_outras = tk.StringVar(value=num_br(f["outras_despesas"]) if f["outras_despesas"] else "")
        self.v_prof = tk.BooleanVar(value=f["profissao_regulamentada"])

        def linha(r, rotulo, widget, dica=""):
            ttk.Label(g, text=rotulo).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 12))
            widget.grid(row=r, column=1, sticky="w", pady=4)
            if dica:
                ttk.Label(g, text=dica, style="Muted.TLabel").grid(row=r, column=2, sticky="w", padx=(8, 0))

        cb = ttk.Combobox(g, textvariable=self.v_regime, values=list(regimes.NOMES.values()), state="readonly", width=22)
        linha(0, "Regime atual", cb)
        linha(1, "Receita bruta dos últimos 12 meses (R$)", ttk.Entry(g, textvariable=self.v_rbt, width=24), "obrigatório")
        linha(2, "Folha de pagamento dos últimos 12 meses (R$)", ttk.Entry(g, textvariable=self.v_folha, width=24), "salários + pró-labore")
        linha(3, "Simples: anexo", ttk.Combobox(g, textvariable=self.v_anexo, values=["III", "IV", "V"], state="readonly", width=6))
        linha(4, "", ttk.Checkbutton(g, text="Atividade sujeita ao Fator R (III ou V, conforme a folha)", variable=self.v_fator))
        linha(5, "ISS do município (%)", ttk.Entry(g, textvariable=self.v_iss, width=8), "entre 2% e 5%")
        linha(6, "Presunção do Lucro Presumido", ttk.Combobox(g, textvariable=self.v_presuncao, values=["32%", "16%", "8%"],
                                                              state="readonly", width=6), "32% serviços em geral")
        linha(7, "Outras despesas mensais (R$)", ttk.Entry(g, textvariable=self.v_outras, width=24), "para o Lucro Real")
        linha(8, "", ttk.Checkbutton(g, text="Profissão regulamentada (redução de 30% na reforma)", variable=self.v_prof))
        self.l_erro = ttk.Label(self, text="", style="Erro.TLabel", wraplength=480, justify="left")
        self.l_erro.pack(anchor="w", pady=(6, 0))
        lin = ttk.Frame(self)
        lin.pack(fill="x", pady=(10, 0))
        botao(lin, "Cancelar", self.destroy).pack(side="right")
        botao(lin, "Salvar e continuar", self._salvar, primario=True).pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda *_: self.destroy())
        self.mostrar()

    def _salvar(self):
        try:
            rbt, folha, outras = (grafico.parse_brl(v.get()) for v in (self.v_rbt, self.v_folha, self.v_outras))
            iss = grafico.parse_brl(self.v_iss.get()) / 100
        except ValueError as e:
            self.l_erro.config(text=str(e))
            return
        if rbt <= 0:
            self.l_erro.config(text="Informe a receita bruta dos últimos 12 meses.")
            return
        if not 0 <= iss <= 0.05:
            self.l_erro.config(text="O ISS do município fica entre 0% e 5%.")
            return
        nome_para_chave = {v: k for k, v in regimes.NOMES.items()}
        fiscal = {"regime": nome_para_chave[self.v_regime.get()], "rbt12": rbt, "folha12": folha, "anexo": self.v_anexo.get(),
                  "fator_r": self.v_fator.get(), "iss_aliquota": iss, "presuncao": self.v_presuncao.get().rstrip("%"),
                  "outras_despesas": outras, "profissao_regulamentada": self.v_prof.get()}
        try:
            real = next((e for e in self.store.empresas if e["id"] == self.emp["id"]), None)
            if real is not None:
                real["fiscal"] = fiscal
                self.store.salvar_empresa(real)
        except ErroAdge as e:
            self.l_erro.config(text=str(e))
            return
        self.emp["fiscal"] = fiscal
        self.salvou = True
        self.destroy()


# ============================================================================= janela principal
class DialogoAvancado(Modal):
    def __init__(self, pai, store, emp: dict, resultado: dict):
        super().__init__(pai, f"Informações avançadas — {emp['nome']}")
        self.store, self.emp, self.r = store, emp, resultado
        self.configure(padx=0, pady=0)
        self.resizable(True, True)
        self.geometry("1040x800")
        self.minsize(900, 600)
        self.faturamento = resultado["resumo"].get("servico_prestado", {}).get("valor", 0.0)
        self.tomados = resultado["resumo"].get("servico_tomado", {}).get("valor", 0.0)
        arqs = resultado["arquivos"]
        self.tem = {"prestado": any(a["cat"] == "servico_prestado" for a in arqs),
                    "tomado": any(a["cat"] == "servico_tomado" for a in arqs)}
        self.v_modo = tk.StringVar(value="parte")
        self.v_filtro = tk.StringVar(value="ambos" if all(self.tem.values()) else ("prestado" if self.tem["prestado"] else "tomado"))
        self.destaque = None
        self.itens = []
        self.rolagem = AbaRolavel(self)
        self.rolagem.pack(fill="both", expand=True)
        self.corpo = self.rolagem.corpo
        self._topo()
        self._grafico()
        self.f_comp = ttk.Frame(self.corpo)
        self.f_comp.pack(fill="x", pady=(18, 0))
        self._rodape()
        self._atualizar_grafico()
        self._render_comparativo()
        self.bind("<Escape>", lambda *_: self.destroy())
        self.mostrar()
        self.after(250, self._fluxo_dados)

    # ------------------------------------------------------------------ partes
    def _topo(self):
        ttk.Label(self.corpo, text="Informações avançadas", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(self.corpo, style="Muted.TLabel",
                  text=f"{self.emp['nome']} · {core.mes_exibicao(self.r['mes'])}/{self.r['ano']} · "
                       f"{len(self.r['arquivos'])} nota(s) consideradas").pack(anchor="w", pady=(0, 10))

    def _grafico(self):
        ttk.Label(self.corpo, text="Para onde vai o dinheiro e de onde ele vem", style="Sec.TLabel").pack(anchor="w", pady=(0, 6))
        area = ttk.Frame(self.corpo)
        area.pack(fill="x")
        esq = ttk.Frame(area)
        esq.pack(side="left", anchor="n")
        self.tela = tk.Canvas(esq, width=360, height=360, bg=BRANCO, highlightthickness=0)
        self.tela.pack()
        self.l_detalhe = ttk.Label(esq, text="Passe o mouse ou clique em uma fatia.", style="Muted.TLabel", wraplength=340,
                                   justify="center")
        self.l_detalhe.pack(pady=(4, 0))
        dir_ = ttk.Frame(area, padding=(24, 0, 0, 0))
        dir_.pack(side="left", fill="both", expand=True, anchor="n")
        ttk.Label(dir_, text="Ver por", style="Sec.TLabel").pack(anchor="w")
        for k, nome in grafico.MODOS.items():
            ttk.Radiobutton(dir_, text=nome, value=k, variable=self.v_modo, command=self._mudou).pack(anchor="w", pady=1)
        ttk.Label(dir_, text="Notas", style="Sec.TLabel").pack(anchor="w", pady=(10, 0))
        self.rb_filtro = {}
        for k, nome in grafico.FILTROS.items():
            rb = ttk.Radiobutton(dir_, text=nome, value=k, variable=self.v_filtro, command=self._mudou)
            rb.pack(anchor="w", pady=1)
            self.rb_filtro[k] = rb
            if (k == "ambos" and not all(self.tem.values())) or (k in self.tem and not self.tem[k]):
                rb.state(["disabled"])
        ttk.Label(dir_, text="Legenda", style="Sec.TLabel").pack(anchor="w", pady=(12, 2))
        self.f_legenda = ttk.Frame(dir_)
        self.f_legenda.pack(fill="x")

    def _rodape(self):
        ttk.Separator(self.corpo).pack(fill="x", pady=(18, 10))
        ttk.Label(self.corpo, text=AVISO_LEGAL, style="Muted.TLabel", wraplength=900, justify="left").pack(anchor="w")
        cta = ttk.Frame(self.corpo, style="Card.TFrame", padding=(16, 12))
        cta.pack(fill="x", pady=(12, 4))
        ttk.Label(cta, text="Quer saber qual regime vale mais para a sua empresa?", style="Card.TLabel",
                  font=("Segoe UI Semibold", 11)).pack(side="left")
        botao(cta, "Fale com a Adge", lambda: webbrowser.open(SITE_ADGE), primario=True).pack(side="right")
        ttk.Label(self.corpo, text=f"{NOME_APP} · {SITE_ADGE}", style="Muted.TLabel").pack(anchor="w", pady=(6, 10))

    # ------------------------------------------------------------------ gráfico
    def _mudou(self):
        self.destaque = None
        self._atualizar_grafico()

    def _atualizar_grafico(self):
        modo, filtro = self.v_modo.get(), self.v_filtro.get()
        self.itens = grafico.agrupar(self.r["arquivos"], modo, filtro)
        self._desenhar()
        self._legenda()

    def _desenhar(self):
        t = self.tela
        t.delete("all")
        cx = cy = 180
        raio = 150
        if not self.itens:
            t.create_text(cx, cy, text="Sem notas para este filtro.", fill=CINZA, font=("Segoe UI", 11))
            return
        angs = grafico.angulos(self.itens)
        for i, ((rotulo, valor, p), (ini, ext)) in enumerate(zip(self.itens, angs)):
            cor = grafico.cor_da_fatia(rotulo, i)
            meio = math.radians(ini + ext / 2)
            off = 12 if self.destaque == i else 0
            dx, dy = math.cos(meio) * off, -math.sin(meio) * off
            caixa = (cx - raio + dx, cy - raio + dy, cx + raio + dx, cy + raio + dy)
            if len(self.itens) == 1:
                item = t.create_oval(*caixa, fill=cor, outline=BRANCO, width=2)
            else:
                item = t.create_arc(*caixa, start=ini, extent=ext, style="pieslice", fill=cor, outline=BRANCO, width=2)
            t.tag_bind(item, "<Enter>", lambda e, i=i: self._hover(i))
            t.tag_bind(item, "<Leave>", lambda e: self._hover(None))
            t.tag_bind(item, "<Button-1>", lambda e, i=i: self._clicar(i))
            if p >= 6:
                tx, ty = cx + math.cos(meio) * raio * 0.68 + dx, cy - math.sin(meio) * raio * 0.68 + dy
                texto = t.create_text(tx, ty, text=f"{p:.0f}%", fill=BRANCO, font=("Segoe UI Semibold", 11))
                t.tag_bind(texto, "<Button-1>", lambda e, i=i: self._clicar(i))
        t.create_oval(cx - 62, cy - 62, cx + 62, cy + 62, fill=BRANCO, outline=BRANCO)
        total = sum(v for _, v, _ in self.itens)
        t.create_text(cx, cy - 10, text="Total", fill=CINZA, font=("Segoe UI", 9))
        t.create_text(cx, cy + 10, text="R$ " + num_br(total), fill=VERDE_ESC, font=("Segoe UI Semibold", 11))

    def _texto_fatia(self, i):
        rotulo, valor, p = self.itens[i]
        return f"{rotulo}\nR$ {num_br(valor)} · {f'{p:.1f}'.replace('.', ',')}%"

    def _hover(self, i):
        if i is not None:
            self.l_detalhe.config(text=self._texto_fatia(i))
        elif self.destaque is not None:
            self.l_detalhe.config(text=self._texto_fatia(self.destaque))
        else:
            self.l_detalhe.config(text="Passe o mouse ou clique em uma fatia.")

    def _clicar(self, i):
        self.destaque = None if self.destaque == i else i
        self._desenhar()
        self._hover(None)

    def _legenda(self):
        for w in self.f_legenda.winfo_children():
            w.destroy()
        for i, (rotulo, valor, p) in enumerate(self.itens):
            lin = tk.Frame(self.f_legenda, bg=BRANCO, cursor="hand2")
            lin.pack(fill="x", pady=2)
            quad = tk.Label(lin, bg=grafico.cor_da_fatia(rotulo, i), width=2)
            quad.pack(side="left", padx=(0, 8))
            tx = tk.Label(lin, text=rotulo, bg=BRANCO, fg=TEXTO, font=("Segoe UI", 10), anchor="w", justify="left", wraplength=300)
            tx.pack(side="left", fill="x", expand=True)
            vl = tk.Label(lin, text=f"{f'{p:.1f}'.replace('.', ',')}%  ·  R$ {num_br(valor)}", bg=BRANCO, fg=CINZA,
                          font=("Segoe UI", 9), anchor="e")
            vl.pack(side="right", padx=(8, 0))
            for w in (lin, quad, tx, vl):
                w.bind("<Button-1>", lambda e, i=i: self._clicar(i))
                w.bind("<Enter>", lambda e, i=i: self._hover(i))
                w.bind("<Leave>", lambda e: self._hover(None))

    # ------------------------------------------------------------------ dados fiscais
    def _fluxo_dados(self):
        f = self.emp.get("fiscal") or {}
        if regimes.fiscal_completo(f):
            d = DialogoConfirmaFiscal(self, f)
            self.wait_window(d)
            if d.resultado == "editar":
                self._editar_dados()
        else:
            self._editar_dados()
        self._render_comparativo()

    def _editar_dados(self):
        d = DialogoDadosFiscais(self, self.store, self.emp)
        self.wait_window(d)
        self._render_comparativo()
        self.grab_set()

    # ------------------------------------------------------------------ comparativo
    def _render_comparativo(self):
        for w in self.f_comp.winfo_children():
            w.destroy()
        ttk.Label(self.f_comp, text="Seu regime tributário no período", style="Sec.TLabel").pack(anchor="w", pady=(0, 6))
        f = self.emp.get("fiscal") or {}
        if not self.tem["prestado"]:
            ttk.Label(self.f_comp, style="Muted.TLabel", wraplength=900, justify="left",
                      text="Para comparar regimes é preciso ter o faturamento: busque também os serviços prestados.").pack(anchor="w")
            return
        if not regimes.fiscal_completo(f):
            ttk.Label(self.f_comp, style="Muted.TLabel", wraplength=900, justify="left",
                      text="Informe os dados fiscais da empresa (regime atual, receita e folha dos últimos 12 meses) "
                           "para ver quanto ela pagaria em cada regime.").pack(anchor="w")
            botao(self.f_comp, "Informar dados fiscais", self._editar_dados, primario=True).pack(anchor="w", pady=(8, 0))
            return
        res = regimes.comparar(self.faturamento, self.tomados, f)
        cen = {c["chave"]: c for c in res["cenarios"]}
        atual, melhor = cen[res["atual"]], cen.get(res["melhor"])
        resumo = ttk.Frame(self.f_comp, style="Card.TFrame", padding=(16, 12))
        resumo.pack(fill="x")
        ttk.Label(resumo, style="Card.TLabel", font=("Segoe UI Semibold", 11),
                  text=f"Faturamento do período: R$ {num_br(self.faturamento)} · notas tomadas: R$ {num_br(self.tomados)}").pack(anchor="w")
        if atual["elegivel"]:
            ttk.Label(resumo, style="Card.TLabel",
                      text=f"Hoje, em {atual['nome']}: R$ {num_br(atual['total'])} ({pct(atual['efetiva'])} do faturamento).").pack(anchor="w", pady=(4, 0))
        if melhor and atual["elegivel"]:
            if melhor["chave"] == atual["chave"]:
                msg = "Entre os regimes simulados, o seu atual é o mais econômico neste período."
            else:
                dif = atual["total"] - melhor["total"]
                msg = (f"Mais econômico neste período: {melhor['nome']}, com R$ {num_br(melhor['total'])} "
                       f"(diferença de R$ {num_br(dif)} no mês, cerca de R$ {num_br(dif * 12)} por ano).")
            ttk.Label(resumo, style="Card.TLabel", font=("Segoe UI Semibold", 10), text=msg, wraplength=880, justify="left").pack(anchor="w", pady=(4, 0))
        for a in res["avisos"]:
            ttk.Label(self.f_comp, text="⚠ " + a, style="Erro.TLabel", wraplength=900, justify="left").pack(anchor="w", pady=(4, 0))
        ttk.Label(self.f_comp, text="Hoje", style="Sec.TLabel").pack(anchor="w", pady=(12, 4))
        linha1 = ttk.Frame(self.f_comp)
        linha1.pack(fill="x")
        for i, ch in enumerate(("simples", "presumido", "real")):
            self._cartao(linha1, i, cen[ch], ch == res["atual"], ch == res["melhor"])
        ttk.Label(self.f_comp, text="Reforma tributária (IBS e CBS) — simulação ilustrativa", style="Sec.TLabel").pack(anchor="w", pady=(14, 4))
        linha2 = ttk.Frame(self.f_comp)
        linha2.pack(fill="x")
        for i, ch in enumerate(("reforma2027", "reforma2033")):
            self._cartao(linha2, i, cen[ch], False, False)
        botao(self.f_comp, "Editar dados fiscais", self._editar_dados).pack(anchor="w", pady=(12, 0))

    def _cartao(self, pai, col, c, atual, melhor):
        pai.columnconfigure(col, weight=1, uniform="cartao")
        borda = VERDE if atual else BORDA
        card = tk.Frame(pai, bg=BRANCO, highlightbackground=borda, highlightthickness=3 if atual else 1)
        card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 0))
        corpo = tk.Frame(card, bg=BRANCO, padx=12, pady=10)
        corpo.pack(fill="both", expand=True)
        tk.Label(corpo, text=c["nome"], bg=BRANCO, fg=VERDE_ESC, font=("Segoe UI Semibold", 11), anchor="w", justify="left",
                 wraplength=250).pack(anchor="w")
        tags = []
        if atual:
            tags.append("Seu regime hoje")
        if melhor:
            tags.append("Mais econômico")
        if tags:
            tk.Label(corpo, text=" · ".join(tags), bg=VERDE_CLARO, fg=VERDE_ESC, font=("Segoe UI Semibold", 9), padx=6).pack(anchor="w", pady=(3, 0))
        if not c["elegivel"]:
            tk.Label(corpo, text=c["motivo"], bg=BRANCO, fg=CINZA, wraplength=250, justify="left", font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 0))
            return
        tk.Label(corpo, text="R$ " + num_br(c["total"]), bg=BRANCO, fg=TEXTO, font=("Segoe UI Semibold", 18)).pack(anchor="w", pady=(6, 0))
        tk.Label(corpo, text=f"{pct(c['efetiva'])} do faturamento", bg=BRANCO, fg=CINZA, font=("Segoe UI", 9)).pack(anchor="w")
        tabela = tk.Frame(corpo, bg=BRANCO)
        tabela.pack(fill="x", pady=(8, 0))
        for i, (nome, valor) in enumerate(c["itens"]):
            tk.Label(tabela, text=nome, bg=BRANCO, fg=TEXTO, font=("Segoe UI", 9), anchor="w", justify="left", wraplength=170).grid(row=i, column=0, sticky="w", pady=1)
            tk.Label(tabela, text="R$ " + num_br(valor), bg=BRANCO, fg=TEXTO, font=("Segoe UI", 9), anchor="e").grid(row=i, column=1, sticky="e", padx=(8, 0))
        tabela.columnconfigure(0, weight=1)
        for o in c.get("obs", []):
            tk.Label(corpo, text="• " + o, bg=BRANCO, fg=CINZA, wraplength=250, justify="left", font=("Segoe UI", 8)).pack(anchor="w", pady=(4, 0))
