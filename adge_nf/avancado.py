"""Janela "Informações avançadas": gráfico de pizza do período e comparativo de regimes tributários (simulação)."""
import math
import tkinter as tk
from tkinter import ttk

from . import NOME_APP, SITE_ADGE, core, credito, grafico, regimes, totais
from . import ui
from .core import ErroAdge
from .ui import P, Botao, Cartao, Chip, Interruptor, Marcador, Modal, Rolavel, F, px, rotulo

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
        ui.titulo(self, "Confirme os dados da empresa",
                  "A análise usa estas informações, que ficaram salvas neste computador. Se algo mudou, edite antes de continuar."
                  ).pack(anchor="w", pady=(0, 12))
        f = {**regimes.fiscal_padrao(), **fiscal}
        linhas = [("Regime atual", regimes.NOMES.get(f["regime"], "—")),
                  ("Receita bruta dos últimos 12 meses", "R$ " + num_br(f["rbt12"])),
                  ("Folha de pagamento dos últimos 12 meses", "R$ " + num_br(f["folha12"])),
                  ("Simples: anexo", "Conforme o Fator R (III ou V)" if f["fator_r"] else f"Anexo {f['anexo']}"),
                  ("ISS do município", pct(f["iss_aliquota"])),
                  ("Presunção (Lucro Presumido)", f"{f['presuncao']}%"),
                  ("Outras despesas mensais", "R$ " + num_br(f["outras_despesas"])),
                  ("Profissão regulamentada (reforma)", "Sim" if f["profissao_regulamentada"] else "Não")]
        cartao = Cartao(self, fundo="verde_claro", borda="verde_claro")
        cartao.pack(fill="x")
        q = cartao.corpo
        q.columnconfigure(1, weight=1)
        for i, (k, v) in enumerate(linhas):
            rotulo(q, k, 10, cor="verde_escuro").grid(row=i, column=0, sticky="w", pady=3)
            rotulo(q, v, 10, "bold", "verde_escuro", anchor="e").grid(row=i, column=1, sticky="e", padx=(28, 0))
        lin = tk.Frame(self, bg=P.fundo)
        lin.pack(fill="x", pady=(16, 0))
        Botao(lin, "Agora não", self.destroy).pack(side="right")
        Botao(lin, "Editar dados", lambda: self._fim("editar")).pack(side="right", padx=(0, 8))
        Botao(lin, "Usar estes dados", lambda: self._fim("usar"), estilo="primario").pack(side="right", padx=(0, 8))
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
        ui.titulo(self, "Dados fiscais da empresa",
                  "Usados só para a simulação de regimes. Ficam salvos neste computador, junto com a empresa, "
                  "e a busca de notas continua de onde parou.").pack(anchor="w", pady=(0, 12))
        cartao = Cartao(self)
        cartao.pack(fill="x")
        g = cartao.corpo
        g.columnconfigure(1, weight=1)
        self.v_regime = tk.StringVar(value=regimes.NOMES.get(f["regime"], regimes.NOMES["simples"]))
        self.v_rbt = tk.StringVar(value=num_br(f["rbt12"]) if f["rbt12"] else "")
        self.v_folha = tk.StringVar(value=num_br(f["folha12"]) if f["folha12"] else "")
        self.v_anexo = tk.StringVar(value=f["anexo"])
        self.v_fator = tk.BooleanVar(value=f["fator_r"])
        self.v_iss = tk.StringVar(value=f"{f['iss_aliquota'] * 100:.2f}".replace(".", ","))
        self.v_presuncao = tk.StringVar(value=f"{f['presuncao']}%")
        self.v_outras = tk.StringVar(value=num_br(f["outras_despesas"]) if f["outras_despesas"] else "")
        self.v_prof = tk.BooleanVar(value=f["profissao_regulamentada"])

        def linha(r, texto, widget, dica=""):
            rotulo(g, texto, 10).grid(row=r, column=0, sticky="w", pady=5, padx=(0, 16))
            widget.grid(row=r, column=1, sticky="w", pady=5)
            if dica:
                rotulo(g, dica, 9, cor="suave").grid(row=r, column=2, sticky="w", padx=(10, 0))

        linha(0, "Regime atual", ttk.Combobox(g, textvariable=self.v_regime, values=list(regimes.NOMES.values()),
                                              state="readonly", width=22, font=F(10)))
        linha(1, "Receita bruta dos últimos 12 meses (R$)", ui.Campo(g, self.v_rbt, largura=18), "obrigatório")
        linha(2, "Folha de pagamento dos últimos 12 meses (R$)", ui.Campo(g, self.v_folha, largura=18), "salários + pró-labore")
        linha(3, "Simples: anexo", ttk.Combobox(g, textvariable=self.v_anexo, values=["III", "IV", "V"], state="readonly",
                                                width=6, font=F(10)))
        linha(4, "", Interruptor(g, "Atividade sujeita ao Fator R (III ou V, conforme a folha)", self.v_fator))
        linha(5, "ISS do município (%)", ui.Campo(g, self.v_iss, largura=8), "entre 2% e 5%")
        linha(6, "Presunção do Lucro Presumido", ttk.Combobox(g, textvariable=self.v_presuncao, values=["32%", "16%", "8%"],
                                                              state="readonly", width=6, font=F(10)), "32% serviços em geral")
        linha(7, "Outras despesas mensais (R$)", ui.Campo(g, self.v_outras, largura=18), "para o Lucro Real")
        linha(8, "", Interruptor(g, "Profissão regulamentada (redução de 30% na reforma)", self.v_prof))
        self.l_erro = rotulo(self, "", 10, cor="erro", largura=px(560))
        self.l_erro.pack(anchor="w", pady=(8, 0))
        lin = tk.Frame(self, bg=P.fundo)
        lin.pack(fill="x", pady=(8, 0))
        Botao(lin, "Cancelar", self.destroy).pack(side="right")
        Botao(lin, "Salvar e continuar", self._salvar, estilo="primario").pack(side="right", padx=(0, 8))
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
    def __init__(self, pai, store, emp: dict, resultado: dict, selecao=None):
        super().__init__(pai, f"Informações avançadas — {emp['nome']}", margem=0)
        self.store, self.emp, self.r = store, emp, resultado
        self.resizable(True, True)
        self.geometry(f"{px(1040)}x{px(800)}")
        self.minsize(px(900), px(600))
        arqs = resultado["arquivos"]
        self.cats = [c for c in core.ORDEM_CATEGORIAS if any(a["cat"] == c for a in arqs)]
        # a mesma seleção da janela de busca: marcar aqui também muda lá, e vice-versa
        self.sel = selecao or totais.Selecao(totais.padrao_ativos(self.cats))
        self.v_modo = tk.StringVar(value="parte")
        self.destaque = None
        self.itens = []
        self.marcas = {}
        self.rolagem = Rolavel(self, pad=24)
        self.rolagem.pack(fill="both", expand=True)
        self.corpo = self.rolagem.corpo
        self._topo()
        self._grafico()
        self.f_comp = tk.Frame(self.corpo, bg=P.fundo)
        self.f_comp.pack(fill="x", pady=(20, 0))
        self._rodape()
        self.sel.ao_mudar(self._mudou_selecao)
        self._atualizar_grafico()
        self._render_comparativo()
        self.bind("<Escape>", lambda *_: self.destroy())
        self.bind("<Destroy>", self._ao_destruir, add="+")
        self.mostrar()
        self.after(250, self._fluxo_dados)

    def _ao_destruir(self, e):
        if e.widget is self:
            self.sel.esquecer(self._mudou_selecao)

    def _mudou_selecao(self):
        if not self.winfo_exists():
            return
        for c, var in self.marcas.items():
            if var.get() != self.sel.ativa(c):
                var.set(self.sel.ativa(c))
        self.destaque = None
        self._atualizar_grafico()
        self._render_comparativo()
        self._atualizar_topo()

    # ------------------------------------------------------------------ partes
    def _topo(self):
        ui.titulo(self.corpo, "Informações avançadas",
                  f"{self.emp['nome']} · {core.mes_exibicao(self.r['mes'])}/{self.r['ano']}").pack(anchor="w", pady=(0, 8))
        self.l_qtd = rotulo(self.corpo, "", 10, cor="suave", largura=px(960))
        self.l_qtd.pack(anchor="w")
        if len(self.cats) > 1:
            rotulo(self.corpo, "Considerar no gráfico e na análise de regimes", 10, "bold", "verde_escuro").pack(anchor="w", pady=(8, 4))
            f = tk.Frame(self.corpo, bg=P.fundo)
            f.pack(fill="x", pady=(0, 10))
            por, ws = totais.por_categoria(self.r["arquivos"]), []
            for c in self.cats:
                info = core.CATEGORIAS[c]
                x = por.get(c, {"qtd": 0, "valor": 0.0})
                tom = "amarelo" if c == "nfe_resumo" else {"receita": "verde", "custo": "vermelho"}.get(info["lado"], "neutro")
                var = tk.BooleanVar(value=self.sel.ativa(c))
                self.marcas[c] = var
                ws.append(Marcador(f, f"{info['rotulo']} · {x['qtd']} · R$ {num_br(x['valor'])}", var,
                                   lambda c=c, v=var: self.sel.definir(c, v.get()), tom=tom, tam=9))
            ui.fluxo(f, ws)
        self._atualizar_topo()

    def _atualizar_topo(self):
        n = len(totais.filtrar(self.r["arquivos"], self.sel.ativos))
        self.l_qtd.config(text=f"{n} nota(s) consideradas de {len(self.r['arquivos'])} encontradas.")

    def _grafico(self):
        ui.secao(self.corpo, "Para onde vai o dinheiro e de onde ele vem").pack(anchor="w", pady=(0, 8))
        cartao = Cartao(self.corpo)
        cartao.pack(fill="x")
        area = cartao.corpo
        esq = tk.Frame(area, bg=P.superficie)
        esq.pack(side="left", anchor="n")
        self.tam = px(340)
        self.tela = tk.Canvas(esq, width=self.tam, height=self.tam, bg=P.superficie, highlightthickness=0)
        self.tela.pack()
        self.l_detalhe = rotulo(esq, "Passe o mouse ou clique em uma fatia.", 10, cor="suave", largura=px(330), justify="center",
                                anchor="center")
        self.l_detalhe.pack(pady=(4, 0))
        dir_ = tk.Frame(area, bg=P.superficie)
        dir_.pack(side="left", fill="both", expand=True, anchor="n", padx=(24, 0))
        rotulo(dir_, "Ver por", 11, "bold", "verde_escuro").pack(anchor="w")
        for k, nome in grafico.MODOS.items():
            ui.radio(dir_, nome, k, self.v_modo, self._mudou).pack(anchor="w", pady=1)
        rotulo(dir_, "Legenda", 11, "bold", "verde_escuro").pack(anchor="w", pady=(12, 2))
        self.f_legenda = tk.Frame(dir_, bg=P.superficie)
        self.f_legenda.pack(fill="x")

    def _rodape(self):
        ui.divisor(self.corpo, (20, 12))
        rotulo(self.corpo, AVISO_LEGAL, 9, cor="suave", largura=px(900)).pack(anchor="w")
        cta = Cartao(self.corpo, fundo="verde_claro", borda="verde_claro", pad=14)
        cta.pack(fill="x", pady=(14, 4))
        rotulo(cta.corpo, "Quer saber qual regime vale mais para a sua empresa?", 11, "bold", "verde_escuro").pack(side="left")
        Botao(cta.corpo, "Fale com a Adge", lambda: ui.abrir_link(SITE_ADGE), estilo="primario").pack(side="right")
        rotulo(self.corpo, f"{NOME_APP} · {SITE_ADGE}", 9, cor="suave").pack(anchor="w", pady=(6, 10))

    # ------------------------------------------------------------------ gráfico
    def _mudou(self):
        self.destaque = None
        self._atualizar_grafico()

    def _atualizar_grafico(self):
        self.itens = grafico.agrupar(self.r["arquivos"], self.v_modo.get(), set(self.sel.ativos))
        self._desenhar()
        self._legenda()

    def _desenhar(self):
        t = self.tela
        t.delete("all")
        cx = cy = self.tam / 2
        raio = self.tam * 0.43
        if not self.itens:
            t.create_text(cx, cy, text="Nenhuma categoria marcada." if not self.sel.ativos else "Sem notas para esta seleção.", fill=P.suave, font=F(11))
            return
        angs = grafico.angulos(self.itens)
        for i, ((rot, valor, p), (ini, ext)) in enumerate(zip(self.itens, angs)):
            cor = grafico.cor_da_fatia(rot, i)
            meio = math.radians(ini + ext / 2)
            off = px(12) if self.destaque == i else 0
            dx, dy = math.cos(meio) * off, -math.sin(meio) * off
            caixa = (cx - raio + dx, cy - raio + dy, cx + raio + dx, cy + raio + dy)
            if len(self.itens) == 1:
                item = t.create_oval(*caixa, fill=cor, outline=P.superficie, width=2)
            else:
                item = t.create_arc(*caixa, start=ini, extent=ext, style="pieslice", fill=cor, outline=P.superficie, width=2)
            t.tag_bind(item, "<Enter>", lambda e, i=i: self._hover(i))
            t.tag_bind(item, "<Leave>", lambda e: self._hover(None))
            t.tag_bind(item, "<Button-1>", lambda e, i=i: self._clicar(i))
            if p >= 6:
                tx, ty = cx + math.cos(meio) * raio * 0.68 + dx, cy - math.sin(meio) * raio * 0.68 + dy
                texto = t.create_text(tx, ty, text=f"{p:.0f}%", fill="#FFFFFF", font=F(11, "bold"))
                t.tag_bind(texto, "<Button-1>", lambda e, i=i: self._clicar(i))
        r2 = raio * 0.42
        t.create_oval(cx - r2, cy - r2, cx + r2, cy + r2, fill=P.superficie, outline=P.superficie)
        total = sum(v for _, v, _ in self.itens)
        t.create_text(cx, cy - px(10), text="Total", fill=P.suave, font=F(9))
        t.create_text(cx, cy + px(10), text="R$ " + num_br(total), fill=P.verde_escuro, font=F(11, "bold"))

    def _texto_fatia(self, i):
        rot, valor, p = self.itens[i]
        return f"{rot}\nR$ {num_br(valor)} · {f'{p:.1f}'.replace('.', ',')}%"

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
        bg = P.superficie
        for i, (rot, valor, p) in enumerate(self.itens):
            lin = tk.Frame(self.f_legenda, bg=bg, cursor="hand2")
            lin.pack(fill="x", pady=2)
            quad = tk.Label(lin, bg=grafico.cor_da_fatia(rot, i), width=2)
            quad.pack(side="left", padx=(0, 8))
            tx = tk.Label(lin, text=rot, bg=bg, fg=P.texto, font=F(10), anchor="w", justify="left", wraplength=px(300))
            tx.pack(side="left", fill="x", expand=True)
            vl = tk.Label(lin, text=f"{f'{p:.1f}'.replace('.', ',')}%  ·  R$ {num_br(valor)}", bg=bg, fg=P.suave,
                          font=F(9), anchor="e")
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
        ui.secao(self.f_comp, "Seu regime tributário no período").pack(anchor="w", pady=(0, 8))
        f = self.emp.get("fiscal") or {}
        ativ = totais.atividades(self.r["arquivos"], self.sel.ativos)
        if ativ["faturamento"] <= 0:
            rotulo(self.f_comp, "Para comparar regimes é preciso ter faturamento: marque serviços prestados ou NF-e de venda "
                                "(e busque esses tipos de nota, se ainda não buscou).", 10, cor="suave", largura=px(900)).pack(anchor="w")
            return
        if not regimes.fiscal_completo(f):
            rotulo(self.f_comp, "Informe os dados fiscais da empresa (regime atual, receita e folha dos últimos 12 meses) "
                                "para ver quanto ela pagaria em cada regime.", 10, cor="suave", largura=px(900)).pack(anchor="w")
            Botao(self.f_comp, "Informar dados fiscais", self._editar_dados, estilo="primario").pack(anchor="w", pady=(10, 0))
            return
        filtrados = totais.filtrar(self.r["arquivos"], self.sel.ativos)
        cred = credito.estimar(filtrados)
        pj = credito.participacao_pj(filtrados)
        self.faturamento, self.tomados = ativ["faturamento"], ativ["tomados"]
        res = regimes.comparar(self.faturamento, self.tomados, f, cred["pis_cofins"], cred["ibs_cbs"], pj,
                               receitas=ativ["receitas"],
                               icms={"debito": ativ["icms_debito"], "credito": ativ["icms_credito"]})
        self.res = res
        cen = {c["chave"]: c for c in res["cenarios"]}
        atual = cen.get(res["atual"])
        resumo = Cartao(self.f_comp, fundo="verde_claro", borda="verde_claro")
        resumo.pack(fill="x")
        c = resumo.corpo
        rotulo(c, f"Faturamento considerado: R$ {num_br(self.faturamento)} · compras e serviços tomados: R$ {num_br(self.tomados)}",
               11, "bold", "verde_escuro").pack(anchor="w")
        if res["grupo"] == "simples":
            comp = "Comparação para quem está no Simples Nacional: DAS unificado × opção pelo regime regular de IBS/CBS."
        else:
            comp = "Comparação entre Lucro Presumido e Lucro Real, hoje e com a reforma tributária."
        rotulo(c, comp, 10, cor="verde_escuro", largura=px(860)).pack(anchor="w", pady=(4, 0))
        if atual and atual["elegivel"]:
            rotulo(c, f"Hoje, em {regimes.NOMES.get(f.get('regime'), '')}: R$ {num_br(atual['total'])} ({pct(atual['efetiva'])} do faturamento).",
                   10, cor="verde_escuro").pack(anchor="w", pady=(4, 0))
        s1 = res["secoes"][0]
        if s1["melhor"]:
            ordem = sorted((cen[k] for k in s1["chaves"] if cen[k]["elegivel"]), key=lambda x: x["total"])
            dif = ordem[1]["total"] - ordem[0]["total"]
            msg = (f"Neste período, {ordem[0]['nome']} é a opção mais econômica: R$ {num_br(dif)} a menos no mês "
                   f"(cerca de R$ {num_br(dif * 12)} por ano) que {ordem[1]['nome']}.")
            rotulo(c, msg, 10, "bold", "verde_escuro", largura=px(860)).pack(anchor="w", pady=(4, 0))
        for a_ in res["avisos"]:
            rotulo(self.f_comp, "⚠ " + a_, 10, cor="erro", largura=px(900)).pack(anchor="w", pady=(6, 0))
        for i_ in res["insights"]:
            rotulo(self.f_comp, "• " + i_, 10, cor="suave", largura=px(900)).pack(anchor="w", pady=(4, 0))
        for sec in res["secoes"]:
            rotulo(self.f_comp, sec["titulo"], 12, "bold", "verde_escuro").pack(anchor="w", pady=(16, 0))
            rotulo(self.f_comp, sec["nota"], 9, cor="suave").pack(anchor="w", pady=(0, 6))
            self._barras(sec, cen)
            linha = tk.Frame(self.f_comp, bg=P.fundo)
            linha.pack(fill="x", pady=(8, 0))
            for i, ch in enumerate(sec["chaves"]):
                self._cartao(linha, i, cen[ch], ch == sec["atual"], ch == sec["melhor"])
        self._creditos(cred)
        Botao(self.f_comp, "Editar dados fiscais", self._editar_dados).pack(anchor="w", pady=(16, 0))

    def _creditos(self, cred):
        if not cred["linhas"]:
            return
        rotulo(self.f_comp, "Créditos considerados nas notas tomadas", 12, "bold", "verde_escuro").pack(anchor="w", pady=(16, 0))
        rotulo(self.f_comp, "Estimados pelo item da LC 116 (serviços, que não trazem CFOP) e pelo CFOP de cada item (mercadorias), e pelo regime do fornecedor. "
                            "O direito ao crédito depende do uso do serviço na atividade: confirme com o contador.",
               9, cor="suave", largura=px(900)).pack(anchor="w", pady=(0, 6))
        cartao = Cartao(self.f_comp, pad=12)
        cartao.pack(fill="x")
        g = cartao.corpo
        g.columnconfigure(0, weight=1)
        for i, (rot, valor, qtd) in enumerate(cred["linhas"]):
            rotulo(g, f"{rot} ({qtd} nota(s))", 10).grid(row=i, column=0, sticky="w", pady=2)
            rotulo(g, "R$ " + num_br(valor), 10, "bold", anchor="e").grid(row=i, column=1, sticky="e")
        n = len(cred["linhas"])
        if cred["de_simples"]:
            rotulo(g, f"R$ {num_br(cred['de_simples'])} vieram de fornecedores do Simples, cujo crédito de IBS/CBS é reduzido.",
                   9, cor="suave", largura=px(820)).grid(row=n, column=0, columnspan=2, sticky="w", pady=(6, 0))

    def _barras(self, sec, cen):
        """Barras horizontais com o total de cada opção da seção: dá para comparar de relance."""
        elegiveis = [cen[k] for k in sec["chaves"] if cen[k]["elegivel"]]
        if len(elegiveis) < 2:
            return
        maior = max(c["total"] for c in elegiveis) or 1.0
        cartao = Cartao(self.f_comp, pad=14)
        cartao.pack(fill="x")
        g = cartao.corpo
        g.columnconfigure(1, weight=1)
        for i, c in enumerate(elegiveis):
            melhor, atual = c["chave"] == sec["melhor"], c["chave"] == sec["atual"]
            rotulo(g, c["nome"], 10, "bold" if atual else "normal", largura=px(300)).grid(row=i, column=0, sticky="w", pady=5, padx=(0, 14))
            barra = tk.Canvas(g, height=px(16), bg=P.superficie, highlightthickness=0, bd=0)
            barra.grid(row=i, column=1, sticky="ew", pady=5)

            def desenhar(e=None, b=barra, c=c, melhor=melhor):
                b.delete("all")
                w = b.winfo_width()
                if w < 4:
                    return
                h = px(16)
                ui.arredondado(b, 0, 0, w, h, h / 2, fill=P.hover, outline=P.hover)
                ui.arredondado(b, 0, 0, max(h, w * c["total"] / maior), h, h / 2,
                               fill=P.verde if melhor else P.borda_forte, outline=P.verde if melhor else P.borda_forte)
            barra.bind("<Configure>", desenhar)
            rotulo(g, "R$ " + num_br(c["total"]), 10, "bold", anchor="e").grid(row=i, column=2, sticky="e", padx=(14, 0))
            if melhor:
                Chip(g, "Mais econômico", "verde").grid(row=i, column=3, padx=(10, 0))

    def _cartao(self, pai, col, c, atual, melhor):
        pai.columnconfigure(col, weight=1, uniform="cartao")
        card = Cartao(pai, borda="verde" if atual else None, pad=14)
        card.grid(row=0, column=col, sticky="nsew", padx=(0 if col == 0 else 8, 0))
        corpo = card.corpo
        rotulo(corpo, c["nome"], 11, "bold", "verde_escuro", largura=px(440)).pack(anchor="w")
        tags = tk.Frame(corpo, bg=P.superficie)
        if atual:
            Chip(tags, "Seu regime", "verde").pack(side="left", padx=(0, 4))
        if melhor:
            Chip(tags, "Mais econômico", "azul").pack(side="left")
        if atual or melhor:
            tags.pack(anchor="w", pady=(4, 0))
        if not c["elegivel"]:
            rotulo(corpo, c["motivo"], 9, cor="suave", largura=px(440)).pack(anchor="w", pady=(8, 0))
            return
        rotulo(corpo, "R$ " + num_br(c["total"]), 18, "bold").pack(anchor="w", pady=(6, 0))
        rotulo(corpo, f"{pct(c['efetiva'])} do faturamento", 9, cor="suave").pack(anchor="w")
        tabela = tk.Frame(corpo, bg=P.superficie)
        tabela.pack(fill="x", pady=(8, 0))
        for i, (nome, valor) in enumerate(c["itens"]):
            rotulo(tabela, nome, 9, largura=px(300)).grid(row=i, column=0, sticky="w", pady=1)
            rotulo(tabela, "R$ " + num_br(valor), 9, anchor="e").grid(row=i, column=1, sticky="e", padx=(8, 0))
        tabela.columnconfigure(0, weight=1)
        for o in c.get("obs", []):
            rotulo(corpo, "• " + o, 8, cor="suave", largura=px(440)).pack(anchor="w", pady=(4, 0))
