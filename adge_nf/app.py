"""Interface (Tkinter) do Adge Group - NF Downloader. Branco e verde, tudo local."""
import datetime as dt
import os
import queue
import re
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import NOME_APP, VERSAO, atualizacao, core
from .core import Cancelado, ErroAdge
from .store import Armazenamento, empresa_padrao

VERDE, VERDE_ESC, VERDE_CLARO = "#1B9E5A", "#127A44", "#E7F6EE"
TEXTO, CINZA, BORDA, BRANCO, ERRO = "#1F2933", "#6B7280", "#D5E0D9", "#FFFFFF", "#B42318"
FONTE = ("Segoe UI", 10)


def formatar_cnpj(c: str) -> str:
    d = re.sub(r"\D", "", c or "")
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}" if len(d) == 14 else (c or "")


def aplicar_tema(raiz: tk.Misc):
    raiz.configure(bg=BRANCO)
    s = ttk.Style(raiz)
    try:
        s.theme_use("clam")
    except tk.TclError:
        pass
    s.configure(".", background=BRANCO, foreground=TEXTO, font=FONTE, bordercolor=BORDA, focuscolor=BRANCO)
    s.configure("TFrame", background=BRANCO)
    s.configure("Card.TFrame", background=VERDE_CLARO)
    s.configure("TLabel", background=BRANCO, foreground=TEXTO)
    s.configure("Muted.TLabel", foreground=CINZA)
    s.configure("Titulo.TLabel", font=("Segoe UI Semibold", 16), foreground=VERDE_ESC)
    s.configure("Sec.TLabel", font=("Segoe UI Semibold", 11), foreground=VERDE_ESC)
    s.configure("Card.TLabel", background=VERDE_CLARO, foreground=VERDE_ESC)
    s.configure("CardValor.TLabel", background=VERDE_CLARO, foreground=VERDE_ESC, font=("Segoe UI Semibold", 18))
    s.configure("Erro.TLabel", foreground=ERRO)
    s.configure("Ok.TLabel", foreground=VERDE_ESC)
    s.configure("TCheckbutton", background=BRANCO)
    s.configure("TRadiobutton", background=BRANCO)
    s.map("TCheckbutton", background=[("active", BRANCO)])
    s.map("TRadiobutton", background=[("active", BRANCO)])
    s.configure("TButton", padding=(12, 6), background="#F4F7F5", bordercolor=BORDA)
    s.map("TButton", background=[("active", VERDE_CLARO)])
    s.configure("Primary.TButton", background=VERDE, foreground=BRANCO, bordercolor=VERDE, padding=(14, 7),
                font=("Segoe UI Semibold", 10))
    s.map("Primary.TButton", background=[("active", VERDE_ESC), ("disabled", "#9BD3B5")],
          foreground=[("disabled", BRANCO)])
    s.configure("TEntry", fieldbackground=BRANCO, padding=4)
    s.configure("TCombobox", fieldbackground=BRANCO, padding=4)
    s.configure("TNotebook", background=BRANCO, borderwidth=0)
    s.configure("TNotebook.Tab", padding=(18, 8), background="#F4F7F5", font=("Segoe UI Semibold", 10))
    s.map("TNotebook.Tab", background=[("selected", BRANCO)], foreground=[("selected", VERDE_ESC)])
    s.configure("Treeview", rowheight=26, background=BRANCO, fieldbackground=BRANCO, bordercolor=BORDA)
    s.configure("Treeview.Heading", background=VERDE_CLARO, foreground=VERDE_ESC, font=("Segoe UI Semibold", 10),
                relief="flat")
    s.map("Treeview", background=[("selected", VERDE)], foreground=[("selected", BRANCO)])
    s.configure("Horizontal.TProgressbar", background=VERDE, troughcolor=VERDE_CLARO, bordercolor=BORDA)


def botao(pai, texto, comando, primario=False, **kw):
    return ttk.Button(pai, text=texto, command=comando, style="Primary.TButton" if primario else "TButton", **kw)


def centralizar(janela: tk.Toplevel, pai: tk.Misc):
    janela.update_idletasks()
    x = pai.winfo_rootx() + (pai.winfo_width() - janela.winfo_width()) // 2
    y = pai.winfo_rooty() + (pai.winfo_height() - janela.winfo_height()) // 3
    janela.geometry(f"+{max(0, x)}+{max(0, y)}")


def abrir_pasta(caminho):
    try:
        if sys.platform == "win32":
            os.startfile(str(caminho))  # noqa
        else:
            webbrowser.open(Path(caminho).as_uri())
    except Exception:
        pass


class Modal(tk.Toplevel):
    """Janela modal branca, centralizada sobre a janela de origem."""

    def __init__(self, pai, titulo, largura=None, altura=None):
        super().__init__(pai)
        self.pai = pai
        self.title(titulo)
        self.configure(bg=BRANCO, padx=22, pady=18)
        self.transient(pai.winfo_toplevel())
        self.resizable(False, False)
        if largura and altura:
            self.geometry(f"{largura}x{altura}")

    def mostrar(self):
        centralizar(self, self.pai.winfo_toplevel())
        self.grab_set()
        self.focus_set()


def pedir_texto(pai, titulo, mensagem, oculto=False, validar=None, inicial=""):
    """Caixa simples com um campo. Devolve o texto ou None."""
    j = Modal(pai, titulo)
    ttk.Label(j, text=mensagem, wraplength=360, justify="left").pack(anchor="w", pady=(0, 8))
    var = tk.StringVar(value=inicial)
    e = ttk.Entry(j, textvariable=var, width=40, show="●" if oculto else "")
    e.pack(fill="x")
    erro = ttk.Label(j, text="", style="Erro.TLabel")
    erro.pack(anchor="w", pady=(4, 0))
    saida = {"v": None}

    def ok(*_):
        v = var.get()
        if validar:
            msg = validar(v)
            if msg:
                erro.config(text=msg)
                return
        saida["v"] = v
        j.destroy()

    linha = ttk.Frame(j)
    linha.pack(fill="x", pady=(12, 0))
    botao(linha, "Cancelar", j.destroy).pack(side="right")
    botao(linha, "OK", ok, primario=True).pack(side="right", padx=(0, 8))
    j.bind("<Return>", ok)
    j.bind("<Escape>", lambda *_: j.destroy())
    j.mostrar()
    e.focus_set()
    j.wait_window()
    return saida["v"]


# ============================================================================= cadastro da empresa
class DialogoEmpresa(Modal):
    def __init__(self, pai, store: Armazenamento, emp: dict = None):
        super().__init__(pai, "Editar empresa" if emp else "Nova empresa")
        self.store = store
        self.novo = emp is None
        self.emp = dict(emp) if emp else empresa_padrao()
        self.salvou = False
        e = self.emp
        v = lambda x: tk.StringVar(value=x)
        self.v_nome, self.v_cnpj, self.v_pfx = v(e["nome"]), v(formatar_cnpj(e["cnpj"])), v(e["pfx"])
        self.v_senha, self.v_destino = v(""), v(e["destino"])
        self.v_estrutura = v(e["estrutura"])
        self.v_prest = tk.BooleanVar(value=e["tipos"].get("prestado", True))
        self.v_tom = tk.BooleanVar(value=e["tipos"].get("tomado", True))
        self.v_nfe = tk.BooleanVar(value=False)
        self.v_acao = v(e["acao"])
        self.v_rel, self.v_csv = tk.BooleanVar(value=e["relatorio"]), tk.BooleanVar(value=e["csv"])
        self.v_lembrar = tk.BooleanVar(value=bool(e["senha_cifrada"]) or self.novo)
        self.v_pref_prest, self.v_pref_tom = v(e["prefixo_prestado"]), v(e["prefixo_tomado"])
        self._montar()
        self.bind("<Escape>", lambda *_: self.destroy())
        self.mostrar()

    def _linha(self, pai, rotulo, r):
        ttk.Label(pai, text=rotulo).grid(row=r, column=0, sticky="w", pady=4, padx=(0, 12))

    def _montar(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        f = ttk.Frame(self.nb, padding=(14, 12))
        self.nb.add(f, text="  Empresa e certificado  ")
        f.columnconfigure(1, weight=1)
        ttk.Label(f, text="Dados da empresa", style="Sec.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

        self._linha(f, "Nome da empresa", 1)
        ttk.Entry(f, textvariable=self.v_nome, width=52).grid(row=1, column=1, columnspan=2, sticky="ew")

        self._linha(f, "Certificado A1 (.pfx/.p12)", 2)
        ttk.Entry(f, textvariable=self.v_pfx).grid(row=2, column=1, sticky="ew")
        botao(f, "Procurar...", self._procurar_pfx).grid(row=2, column=2, padx=(8, 0))

        self._linha(f, "Senha do certificado", 3)
        self.e_senha = ttk.Entry(f, textvariable=self.v_senha, show="●")
        self.e_senha.grid(row=3, column=1, sticky="ew")
        self.v_ver = tk.BooleanVar(value=False)
        ttk.Checkbutton(f, text="Mostrar", variable=self.v_ver, command=lambda: self.e_senha.config(
            show="" if self.v_ver.get() else "●")).grid(row=3, column=2, padx=(8, 0))
        if not self.novo and self.emp["senha_cifrada"]:
            ttk.Label(f, text="Já há uma senha salva. Deixe em branco para mantê-la.", style="Muted.TLabel").grid(
                row=4, column=1, columnspan=2, sticky="w")

        ttk.Checkbutton(f, text="Lembrar a senha neste computador (fica cifrada)", variable=self.v_lembrar).grid(
            row=5, column=1, columnspan=2, sticky="w", pady=(2, 0))

        lin = ttk.Frame(f)
        lin.grid(row=6, column=1, columnspan=2, sticky="w", pady=(6, 0))
        botao(lin, "Validar certificado", self._validar).pack(side="left")
        self.l_cert = ttk.Label(lin, text="", style="Muted.TLabel")
        self.l_cert.pack(side="left", padx=10)

        self._linha(f, "CNPJ", 7)
        ttk.Entry(f, textvariable=self.v_cnpj, width=24).grid(row=7, column=1, sticky="w")

        ttk.Separator(f).grid(row=8, column=0, columnspan=3, sticky="ew", pady=12)
        ttk.Label(f, text="O que baixar", style="Sec.TLabel").grid(row=9, column=0, columnspan=3, sticky="w", pady=(0, 4))
        t = ttk.Frame(f)
        t.grid(row=10, column=0, columnspan=3, sticky="w")
        ttk.Checkbutton(t, text="Serviço prestado (NFS-e emitidas)", variable=self.v_prest).pack(anchor="w")
        ttk.Checkbutton(t, text="Serviço tomado (NFS-e recebidas)", variable=self.v_tom).pack(anchor="w")
        nfe = ttk.Checkbutton(t, text="NF-e de compra e venda (em breve)", variable=self.v_nfe, state="disabled")
        nfe.pack(anchor="w")

        ttk.Label(f, text="O que fazer", style="Sec.TLabel").grid(row=11, column=0, columnspan=3, sticky="w", pady=(12, 4))
        a = ttk.Frame(f)
        a.grid(row=12, column=0, columnspan=3, sticky="w")
        for valor, txt in (("ambos", "Calcular o total do período e baixar os XMLs"),
                           ("calcular", "Só calcular o total do período"),
                           ("baixar", "Só baixar os XMLs")):
            ttk.Radiobutton(a, text=txt, value=valor, variable=self.v_acao, command=self._atualizar).pack(anchor="w")

        self.f_destino = ttk.Frame(self.nb, padding=(14, 12))
        self.nb.add(self.f_destino, text="  Onde salvar os XMLs  ")
        self.f_destino.columnconfigure(1, weight=1)
        ttk.Label(self.f_destino, text="Onde salvar os XMLs", style="Sec.TLabel").grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 4))
        ttk.Label(self.f_destino, text="Pasta").grid(row=1, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(self.f_destino, textvariable=self.v_destino).grid(row=1, column=1, sticky="ew")
        botao(self.f_destino, "Procurar...", self._procurar_destino).grid(row=1, column=2, padx=(8, 0))
        ttk.Label(self.f_destino, text="Organização").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.cb_est = ttk.Combobox(self.f_destino, state="readonly", values=list(core.ESTRUTURAS.values()))
        self.cb_est.grid(row=2, column=1, columnspan=2, sticky="ew", pady=(6, 0))
        self.cb_est.current(list(core.ESTRUTURAS).index(self.v_estrutura.get()))
        o = ttk.Frame(self.f_destino)
        o.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Checkbutton(o, text="Criar o relatório de organização (.txt)", variable=self.v_rel).pack(anchor="w")
        ttk.Checkbutton(o, text="Criar resumo em CSV (abre no Excel)", variable=self.v_csv).pack(anchor="w")
        av = ttk.Frame(self.f_destino)
        av.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        av.columnconfigure(1, weight=1)
        ttk.Label(av, text="Início do nome (prestado)", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12))
        ttk.Entry(av, textvariable=self.v_pref_prest).grid(row=0, column=1, sticky="ew")
        ttk.Label(av, text="Início do nome (tomado)", style="Muted.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(4, 0))
        ttk.Entry(av, textvariable=self.v_pref_tom).grid(row=1, column=1, sticky="ew", pady=(4, 0))
        ttk.Label(av, text='Em branco usa "NOTA FISCAL DE SERVIÇO PRESTADO" / "TOMADO". Exemplo: '
                           '"NOTA FISCAL DE SERVIÇO PRESTADO DE ALUGUEL".', style="Muted.TLabel", wraplength=520,
                  justify="left").grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

        self.l_erro = ttk.Label(self, text="", style="Erro.TLabel", wraplength=560, justify="left")
        self.l_erro.pack(anchor="w", pady=(10, 0))
        b = ttk.Frame(self)
        b.pack(fill="x", pady=(10, 0))
        botao(b, "Cancelar", self.destroy).pack(side="right")
        botao(b, "Salvar empresa", self._salvar, primario=True).pack(side="right", padx=(0, 8))
        self._atualizar()

    # ------------------------------------------------------------------ ações
    def _atualizar(self):
        self.nb.tab(self.f_destino, state="disabled" if self.v_acao.get() == "calcular" else "normal")

    def _inicial(self):
        return self.store.preferencias.get("pasta_certificados") or self.store.preferencias.get("raiz_padrao") or str(Path.home())

    def _procurar_pfx(self):
        c = filedialog.askopenfilename(parent=self, title="Escolha o certificado A1", initialdir=self._inicial(),
                                       filetypes=[("Certificado digital", "*.pfx *.p12"), ("Todos os arquivos", "*.*")])
        if c:
            self.v_pfx.set(os.path.normpath(c))
            self.store.preferencias["pasta_certificados"] = str(Path(c).parent)

    def _procurar_destino(self):
        c = filedialog.askdirectory(parent=self, title="Escolha a pasta de destino",
                                    initialdir=self.v_destino.get() or self.store.preferencias.get("raiz_padrao") or str(Path.home()))
        if c:
            self.v_destino.set(os.path.normpath(c))

    def _validar(self, silencioso=False):
        pfx, senha = self.v_pfx.get().strip(), self.v_senha.get()
        if not senha and not self.novo and self.emp["senha_cifrada"]:
            try:
                senha = self.store.senha_da_empresa(self.emp)
            except ErroAdge:
                senha = ""
        if not pfx or not senha:
            self.l_cert.config(text="Escolha o arquivo e digite a senha.", style="Erro.TLabel")
            return None
        try:
            info = core.ler_certificado(pfx, senha)
        except ErroAdge as e:
            self.l_cert.config(text=str(e), style="Erro.TLabel")
            return None
        hoje = dt.date.today()
        venc = info["valido_ate"]
        if venc < hoje:
            self.l_cert.config(text=f"Certificado VENCIDO em {venc:%d/%m/%Y}.", style="Erro.TLabel")
        else:
            self.l_cert.config(text=f"Certificado válido até {venc:%d/%m/%Y}.", style="Ok.TLabel")
        if info["cnpj"] and not re.sub(r"\D", "", self.v_cnpj.get()):
            self.v_cnpj.set(formatar_cnpj(info["cnpj"]))
        if info["nome"] and not self.v_nome.get().strip():
            self.v_nome.set(info["nome"])
        return info

    def _salvar(self):
        e = self.emp
        nome = self.v_nome.get().strip()
        cnpj = re.sub(r"\D", "", self.v_cnpj.get())
        pfx = self.v_pfx.get().strip()
        acao = self.v_acao.get()
        estrutura = list(core.ESTRUTURAS)[self.cb_est.current()]
        problema = None
        if not nome:
            problema = "Dê um nome para a empresa."
        elif not pfx or not Path(pfx).is_file():
            problema = "Escolha o arquivo do certificado (.pfx ou .p12)."
        elif len(cnpj) != 14:
            problema = "O CNPJ precisa ter 14 dígitos. Use \"Validar certificado\" para preencher sozinho."
        elif not (self.v_prest.get() or self.v_tom.get()):
            problema = "Marque pelo menos um tipo de nota."
        elif acao != "calcular" and (not self.v_destino.get().strip() or not Path(self.v_destino.get().strip()).is_dir()):
            problema = "Escolha a pasta onde os XMLs serão salvos."
        elif self.novo and not self.v_senha.get():
            problema = "Digite a senha do certificado."
        if problema:
            self.l_erro.config(text=problema)
            if problema.startswith("Escolha a pasta"):
                self.nb.select(self.f_destino)
            return
        senha_nova = self.v_senha.get()
        if senha_nova:
            try:
                core.ler_certificado(pfx, senha_nova)
            except ErroAdge as ex:
                self.l_erro.config(text=str(ex))
                return
        e.update({"nome": nome, "cnpj": cnpj, "pfx": pfx, "destino": self.v_destino.get().strip(),
                  "estrutura": estrutura, "tipos": {"prestado": self.v_prest.get(), "tomado": self.v_tom.get()},
                  "nfe": False, "acao": acao, "relatorio": self.v_rel.get(), "csv": self.v_csv.get(),
                  "prefixo_prestado": self.v_pref_prest.get().strip(), "prefixo_tomado": self.v_pref_tom.get().strip()})
        try:
            if not self.v_lembrar.get():
                self.store.salvar_empresa(e, "")
            elif senha_nova:
                self.store.salvar_empresa(e, senha_nova)
            else:
                self.store.salvar_empresa(e)
        except ErroAdge as ex:
            self.l_erro.config(text=str(ex))
            return
        self.salvou = True
        self.destroy()


# ============================================================================= busca de notas
class DialogoBusca(Modal):
    def __init__(self, pai, store: Armazenamento, emp: dict, sessao=None):
        super().__init__(pai, f"Buscar notas — {emp['nome']}")
        self.store, self.emp, self.sessao_teste = store, dict(emp), sessao
        self.fila: "queue.Queue" = queue.Queue()
        self.cancelar_flag = False
        self.trabalhando = False
        self.resultado = None
        self.pasta_manual = ""
        hoje = dt.date.today()
        self.ano = hoje.year
        self.v_mes = tk.StringVar(value=core.MESES_TELA[max(hoje.month - 2, 0)])  # padrão: mês anterior
        self.v_ano_txt = tk.StringVar()
        self.v_prest = tk.BooleanVar(value=emp["tipos"].get("prestado", True))
        self.v_tom = tk.BooleanVar(value=emp["tipos"].get("tomado", True))
        self.v_nfe = tk.BooleanVar(value=False)
        self.v_acao = tk.StringVar(value=emp["acao"])
        self._montar()
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self.bind("<Escape>", lambda *_: self._fechar())
        self.mostrar()
        self.after(150, self._ler_fila)

    def _montar(self):
        ttk.Label(self, text=self.emp["nome"], style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(self, text=f"CNPJ {formatar_cnpj(self.emp['cnpj'])}", style="Muted.TLabel").pack(anchor="w", pady=(0, 10))

        topo = ttk.Frame(self)
        topo.pack(fill="x")
        col1 = ttk.Frame(topo)
        col1.pack(side="left", anchor="n")
        ttk.Label(col1, text="Período", style="Sec.TLabel").pack(anchor="w")
        ano = ttk.Frame(col1)
        ano.pack(anchor="w", pady=(4, 0))
        ttk.Label(ano, text="Ano:").pack(side="left")
        self.l_ano = ttk.Label(ano, text=str(self.ano), font=("Segoe UI Semibold", 10))
        self.l_ano.pack(side="left", padx=(6, 8))
        botao(ano, "Alterar ano", self._alterar_ano).pack(side="left")
        ttk.Label(col1, text="Mês:").pack(anchor="w", pady=(8, 2))
        self.cb_mes = ttk.Combobox(col1, state="readonly", values=core.MESES_TELA, textvariable=self.v_mes, width=18)
        self.cb_mes.pack(anchor="w")
        self.l_periodo = ttk.Label(col1, text="", style="Muted.TLabel")
        self.l_periodo.pack(anchor="w", pady=(4, 0))
        self.cb_mes.bind("<<ComboboxSelected>>", lambda *_: self._atualizar_periodo())

        col2 = ttk.Frame(topo)
        col2.pack(side="left", anchor="n", padx=40)
        ttk.Label(col2, text="Tipos de nota", style="Sec.TLabel").pack(anchor="w")
        ttk.Checkbutton(col2, text="Serviço prestado", variable=self.v_prest).pack(anchor="w", pady=(4, 0))
        ttk.Checkbutton(col2, text="Serviço tomado", variable=self.v_tom).pack(anchor="w")
        ttk.Checkbutton(col2, text="NF-e (em breve)", variable=self.v_nfe, state="disabled").pack(anchor="w")

        col3 = ttk.Frame(topo)
        col3.pack(side="left", anchor="n")
        ttk.Label(col3, text="O que fazer", style="Sec.TLabel").pack(anchor="w")
        for valor, txt in (("ambos", "Calcular o total e baixar os XMLs"), ("calcular", "Só calcular o total"),
                           ("baixar", "Só baixar os XMLs")):
            ttk.Radiobutton(col3, text=txt, value=valor, variable=self.v_acao).pack(anchor="w", pady=(2, 0))

        acao = ttk.Frame(self)
        acao.pack(fill="x", pady=(14, 0))
        self.b_buscar = botao(acao, "Buscar notas", self._buscar, primario=True)
        self.b_buscar.pack(side="left")
        self.b_cancelar = botao(acao, "Cancelar busca", self._cancelar_busca)
        self.l_status = ttk.Label(acao, text="", style="Muted.TLabel")
        self.l_status.pack(side="left", padx=12)
        self.barra = ttk.Progressbar(self, mode="indeterminate")

        self.f_res = ttk.Frame(self)  # resultados (aparece após a busca)
        cards = ttk.Frame(self.f_res)
        cards.pack(fill="x", pady=(14, 8))
        self.cards = {}
        for chave, rotulo in (("prestado", "Faturamento (serviços prestados)"), ("tomado", "Serviços tomados")):
            c = ttk.Frame(cards, style="Card.TFrame", padding=(16, 10))
            c.pack(side="left", padx=(0, 12))
            ttk.Label(c, text=rotulo, style="Card.TLabel").pack(anchor="w")
            v = ttk.Label(c, text="—", style="CardValor.TLabel")
            v.pack(anchor="w")
            d = ttk.Label(c, text="", style="Card.TLabel")
            d.pack(anchor="w")
            self.cards[chave] = (c, v, d)
        self.l_aviso = ttk.Label(self.f_res, text="", style="Muted.TLabel", wraplength=720, justify="left")
        self.l_aviso.pack(anchor="w")
        cols = ("tipo", "numero", "data", "parte", "valor")
        self.tv = ttk.Treeview(self.f_res, columns=cols, show="headings", height=9)
        for c, t, w, an in (("tipo", "Tipo", 100, "w"), ("numero", "Nº", 70, "e"), ("data", "Data", 90, "w"),
                            ("parte", "Cliente / Fornecedor", 360, "w"), ("valor", "Valor", 110, "e")):
            self.tv.heading(c, text=t)
            self.tv.column(c, width=w, anchor=an)
        sb = ttk.Scrollbar(self.f_res, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.f_botoes = ttk.Frame(self)
        self.l_destino = ttk.Label(self, text="", style="Muted.TLabel", wraplength=720, justify="left")
        self.b_gravar = botao(self.f_botoes, "Baixar XMLs para a pasta", self._gravar, primario=True)
        self.b_csv = botao(self.f_botoes, "Exportar CSV...", self._exportar_csv)
        self.b_copiar = botao(self.f_botoes, "Copiar totais", self._copiar)
        self.b_pasta = botao(self.f_botoes, "Escolher pasta...", self._escolher_pasta)
        botao(self.f_botoes, "Fechar", self._fechar).pack(side="right")
        self._atualizar_periodo()

    # ------------------------------------------------------------------ período
    def _mes_num(self) -> int:
        return core.MESES_TELA.index(self.v_mes.get()) + 1

    def _atualizar_periodo(self):
        ini, fim = core.limites_mes(self.ano, self._mes_num())
        self.l_periodo.config(text=f"{ini:%d/%m/%Y} a {fim:%d/%m/%Y}")

    def _alterar_ano(self):
        def valida(t):
            return None if re.fullmatch(r"(19|20)\d{2}", t.strip()) else "Digite o ano com 4 dígitos (AAAA), por exemplo 2026."
        v = pedir_texto(self, "Alterar ano", "Digite o ano no formato AAAA:", validar=valida, inicial=str(self.ano))
        if v:
            self.ano = int(v.strip())
            self.l_ano.config(text=str(self.ano))
            self._atualizar_periodo()

    # ------------------------------------------------------------------ busca
    def _emp_da_busca(self) -> dict:
        e = dict(self.emp)
        e["tipos"] = {"prestado": self.v_prest.get(), "tomado": self.v_tom.get()}
        e["acao"] = self.v_acao.get()
        return e

    def _buscar(self):
        emp = self._emp_da_busca()
        if not (emp["tipos"]["prestado"] or emp["tipos"]["tomado"]):
            messagebox.showwarning(NOME_APP, "Marque pelo menos um tipo de nota.", parent=self)
            return
        try:
            senha = self.store.senha_da_empresa(emp)
        except ErroAdge as e:
            messagebox.showwarning(NOME_APP, str(e), parent=self)
            senha = ""
        if not senha:
            senha = pedir_texto(self, "Senha do certificado", f"Digite a senha do certificado de {emp['nome']}:", oculto=True,
                                validar=lambda t: None if t else "Digite a senha.")
            if not senha:
                return
        self.f_res.pack_forget(); self.f_botoes.pack_forget(); self.l_destino.pack_forget()
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
        if sim:
            self.l_status.config(text="Conectando ao ADN...", style="Muted.TLabel")
            self.barra.pack(fill="x", pady=(8, 0))
            self.barra.start(12)
            self.b_cancelar.pack(side="left")
        else:
            self.barra.stop()
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
                    messagebox.showerror(NOME_APP, dado, parent=self)
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
        arquivos, resumo, avisos = core.planejar(emp, docs, cnpj, ano, mes, destino_prev)
        self.resultado = {"emp": emp, "docs": docs, "cnpj": cnpj, "ano": ano, "mes": mes, "arquivos": arquivos,
                          "resumo": resumo, "avisos": avisos, "destino_ok": destino_prev is not None}
        self.l_status.config(text=f"{len(docs)} documento(s) consultados.")
        mostrar_totais = emp["acao"] != "baixar"
        for chave, cat in (("prestado", "servico_prestado"), ("tomado", "servico_tomado")):
            card, v, d = self.cards[chave]
            card.pack_forget()
            if mostrar_totais and cat in resumo:
                r = resumo[cat]
                v.config(text=core.formatar_valor(r["valor"]).replace("R$", "R$ "))
                extra = f"{r['qtd']} nota(s)" + (f" · {r['canceladas']} cancelada(s) fora" if r["canceladas"] else "")
                d.config(text=extra)
                card.pack(side="left", padx=(0, 12))
        msgs = list(avisos)
        if not arquivos:
            msgs.insert(0, "Nenhuma nota encontrada nesse período.")
        self.l_aviso.config(text="\n".join(msgs))
        self.tv.delete(*self.tv.get_children())
        for a in arquivos:
            d = a["doc"]
            prestado = a["cat"] == "servico_prestado"
            parte = d["tomador_nome"] if prestado else d["emitente_nome"]
            self.tv.insert("", "end", values=("Prestado" if prestado else "Tomado", d["numero"],
                                              core.formatar_data(d["emissao"]).replace("-", "/"), parte,
                                              core.formatar_valor(d["valor"]).replace("R$", "R$ ")))
        self.f_res.pack(fill="both", expand=True, pady=(4, 0))
        if emp["acao"] != "calcular" and aviso_dest:
            self.l_destino.config(text=aviso_dest, style="Erro.TLabel" if aviso_dest.startswith("⚠") else "Muted.TLabel")
            self.l_destino.pack(anchor="w", pady=(8, 0))
        for w in self.f_botoes.winfo_children():
            if w not in (self.b_gravar, self.b_csv, self.b_copiar, self.b_pasta):
                continue
            w.pack_forget()
        if emp["acao"] != "calcular":
            self.b_gravar.config(state="normal" if arquivos and self.resultado["destino_ok"] else "disabled")
            self.b_gravar.pack(side="left")
            self.b_pasta.pack(side="left", padx=(8, 0))
        if emp["acao"] != "baixar":
            self.b_copiar.pack(side="left", padx=(8, 0))
            self.b_csv.pack(side="left", padx=(8, 0))
        self.f_botoes.pack(fill="x", pady=(12, 0))
        self.update_idletasks()
        centralizar(self, self.pai.winfo_toplevel())

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
        if not messagebox.askyesno(NOME_APP, f"Gravar {n} XML(s) em:\n{self.l_destino.cget('text').replace('Destino: ', '')}\n\n"
                                   "Arquivos que já existirem não serão sobrescritos.", parent=self):
            return
        try:
            destino, contagem = core.salvar_notas(r["emp"], r["arquivos"], r["resumo"], r["cnpj"], r["ano"], r["mes"])
        except (ErroAdge, OSError) as e:
            messagebox.showerror(NOME_APP, f"Não consegui gravar: {e}", parent=self)
            return
        resumo = ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in contagem.items())
        if messagebox.askyesno(NOME_APP, f"Pronto! {resumo}.\n\nPasta:\n{destino}\n\nAbrir a pasta agora?", parent=self):
            abrir_pasta(destino)

    def _texto_totais(self) -> str:
        r = self.resultado
        linhas = [f"{r['emp']['nome']} — {core.mes_exibicao(r['mes'])}/{r['ano']}"]
        for cat, nome in (("servico_prestado", "Faturamento (serviços prestados)"), ("servico_tomado", "Serviços tomados")):
            if cat in r["resumo"]:
                x = r["resumo"][cat]
                linhas.append(f"{nome}: {core.formatar_valor(x['valor']).replace('R$', 'R$ ')} ({x['qtd']} nota(s))")
        return "\n".join(linhas)

    def _copiar(self):
        if self.resultado:
            self.clipboard_clear()
            self.clipboard_append(self._texto_totais())
            self.l_status.config(text="Totais copiados.")

    def _exportar_csv(self):
        r = self.resultado
        if not r:
            return
        caminho = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", filetypes=[("CSV (Excel)", "*.csv")],
                                               initialfile=f"Resumo Notas - {r['mes']:02d}-{r['ano']}.csv")
        if caminho:
            Path(caminho).write_text(core.gerar_csv(r["arquivos"], r["resumo"]), encoding="utf-8")
            self.l_status.config(text="CSV salvo.")

    def _fechar(self):
        if self.trabalhando:
            self.cancelar_flag = True
        self.destroy()


# ============================================================================= atualização
class DialogoAtualizacao(Modal):
    """Aviso de versão nova com Atualizar agora / Lembrar depois / Pular esta versão."""

    def __init__(self, pai, store: Armazenamento, info: dict, ao_instalar=None, sessao=None, pode_instalar=None):
        super().__init__(pai, "Atualização disponível")
        self.store, self.info, self.sessao = store, info, sessao
        self.ao_instalar = ao_instalar or (lambda caminho: (atualizacao.instalar_e_reabrir(caminho), pai.winfo_toplevel().destroy()))
        self.pode_instalar = atualizacao.pode_instalar_sozinho() if pode_instalar is None else pode_instalar
        self.fila: "queue.Queue" = queue.Queue()
        self.cancelar_flag = False
        self.baixando = False
        self._montar()
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self.bind("<Escape>", lambda *_: self._fechar())
        self.mostrar()
        self.after(100, self._ler_fila)

    def _montar(self):
        ttk.Label(self, text="Nova versão disponível", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(self, text=f"{self.info['tag']}  (você está na v{VERSAO})", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        ttk.Label(self, text="Novidades", style="Sec.TLabel").pack(anchor="w")
        caixa = ttk.Frame(self)
        caixa.pack(fill="both", expand=True, pady=(4, 0))
        self.txt = tk.Text(caixa, width=70, height=9, wrap="word", bg=BRANCO, fg=TEXTO, relief="solid", bd=1,
                           highlightthickness=0, font=FONTE, padx=8, pady=6)
        sb = ttk.Scrollbar(caixa, orient="vertical", command=self.txt.yview)
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.txt.insert("1.0", self.info.get("notas") or "Esta versão não traz descrição das novidades.")
        self.txt.config(state="disabled")
        self.l_status = ttk.Label(self, text="", style="Muted.TLabel", wraplength=520, justify="left")
        self.l_status.pack(anchor="w", pady=(10, 0))
        self.barra = ttk.Progressbar(self, mode="determinate", maximum=100)
        linha = ttk.Frame(self)
        linha.pack(fill="x", pady=(12, 0))
        self.f_botoes = linha
        msi = self.info.get("msi")
        if self.pode_instalar and msi and msi.get("sha256"):
            self.b_ok = botao(linha, "Atualizar agora", self._atualizar, primario=True)
            aviso = "O Windows vai pedir permissão de administrador. Suas empresas e senhas salvas são mantidas."
        else:
            self.b_ok = botao(linha, "Abrir a página de download", self._abrir_pagina, primario=True)
            aviso = ("Esta cópia do programa não pode se atualizar sozinha. Baixe o instalador na página."
                     if not self.pode_instalar else "Esta versão não tem verificação de integridade; baixe pela página.")
        self.l_status.config(text=aviso)
        self.b_ok.pack(side="left")
        self.b_depois = botao(linha, "Lembrar depois", self._depois)
        self.b_depois.pack(side="left", padx=(8, 0))
        self.b_pular = botao(linha, "Pular esta versão", self._pular)
        self.b_pular.pack(side="right")

    # ------------------------------------------------------------------ escolhas
    def _salvar_prefs(self):
        try:
            self.store.salvar()
        except OSError:
            pass

    def _depois(self):
        atualizacao.lembrar_depois(self.store.preferencias, 3)
        self._salvar_prefs()
        self._fechar()

    def _pular(self):
        atualizacao.pular_versao(self.store.preferencias, self.info["tag"])
        self._salvar_prefs()
        self._fechar()

    def _abrir_pagina(self):
        webbrowser.open(self.info["url"])
        self._fechar()

    def _atualizar(self):
        self.baixando = True
        self.cancelar_flag = False
        for b in (self.b_ok, self.b_depois, self.b_pular):
            b.config(state="disabled")
        self.b_cancelar = botao(self.f_botoes, "Cancelar download", lambda: setattr(self, "cancelar_flag", True))
        self.b_cancelar.pack(side="left", padx=(8, 0))
        self.barra.pack(fill="x", pady=(8, 0))
        self.l_status.config(text="Baixando a atualização...", style="Muted.TLabel")

        def trabalho():
            try:
                caminho = atualizacao.baixar(self.info["msi"], progresso=lambda f, t: self.fila.put(("p", (f, t))),
                                             cancelar=lambda: self.cancelar_flag, sessao=self.sessao, repo=self.info.get("repo"))
                self.fila.put(("ok", caminho))
            except Cancelado:
                self.fila.put(("cancelado", None))
            except ErroAdge as e:
                self.fila.put(("erro", str(e)))
            except Exception as e:
                self.fila.put(("erro", f"Erro inesperado: {e}"))
        threading.Thread(target=trabalho, daemon=True).start()

    def _fim_download(self):
        self.baixando = False
        self.barra.pack_forget()
        self.b_cancelar.destroy()
        for b in (self.b_ok, self.b_depois, self.b_pular):
            b.config(state="normal")

    def _ler_fila(self):
        try:
            while True:
                tipo, dado = self.fila.get_nowait()
                if tipo == "p":
                    feito, total = dado
                    if total:
                        self.barra.config(value=feito * 100 / total)
                        self.l_status.config(text=f"Baixando a atualização... {feito / 1048576:.1f} de {total / 1048576:.1f} MB")
                elif tipo == "ok":
                    self.l_status.config(text="Download conferido. Iniciando a instalação...")
                    self.update_idletasks()
                    try:
                        self.ao_instalar(dado)
                    except ErroAdge as e:
                        self._fim_download()
                        self.l_status.config(text=str(e), style="Erro.TLabel")
                    return
                elif tipo == "erro":
                    self._fim_download()
                    self.l_status.config(text=dado, style="Erro.TLabel")
                elif tipo == "cancelado":
                    self._fim_download()
                    self.l_status.config(text="Download cancelado.", style="Muted.TLabel")
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._ler_fila)

    def _fechar(self):
        if self.baixando:
            self.cancelar_flag = True
        self.destroy()


# ============================================================================= janela principal
class AbaRolavel(ttk.Frame):
    """Frame com barra de rolagem vertical: o conteúdo vai em `.corpo`."""

    def __init__(self, pai, **kw):
        super().__init__(pai, **kw)
        self.tela = tk.Canvas(self, bg=BRANCO, highlightthickness=0, borderwidth=0)
        self.barra = ttk.Scrollbar(self, orient="vertical", command=self.tela.yview)
        self.tela.configure(yscrollcommand=self.barra.set)
        self.barra.pack(side="right", fill="y")
        self.tela.pack(side="left", fill="both", expand=True)
        self.corpo = ttk.Frame(self.tela, padding=18)
        self._id = self.tela.create_window((0, 0), window=self.corpo, anchor="nw")
        self.corpo.bind("<Configure>", lambda e: self.tela.configure(scrollregion=self.tela.bbox("all")))
        self.tela.bind("<Configure>", lambda e: self.tela.itemconfigure(self._id, width=e.width))
        self.bind("<Enter>", lambda e: self.tela.bind_all("<MouseWheel>", self._roda))
        self.bind("<Leave>", lambda e: self.tela.unbind_all("<MouseWheel>"))

    def _roda(self, e):
        if self.corpo.winfo_reqheight() > self.tela.winfo_height():
            self.tela.yview_scroll(-1 if e.delta > 0 else 1, "units")


class App(tk.Tk):
    def __init__(self, store: Armazenamento = None):
        super().__init__()
        self.title(NOME_APP)
        self.geometry("920x620")
        self.minsize(820, 540)
        aplicar_tema(self)
        icone = next((c for c in (Path(sys.executable).with_name("icone.ico"), Path(__file__).with_name("icone.ico")) if c.exists()), None)
        if icone and sys.platform == "win32":
            try:
                self.iconbitmap(str(icone))
            except tk.TclError:
                pass
        self.store = store or Armazenamento()
        self._desbloquear()
        self._cabecalho()
        self.abas = ttk.Notebook(self)
        self.abas.pack(fill="both", expand=True, padx=20, pady=(8, 16))
        self._aba_empresas()
        self._aba_config()
        self._atualizar_lista()
        self.fila_att: "queue.Queue" = queue.Queue()
        self.sessao_att = None  # os testes injetam uma sessão falsa
        self.after(300, self._ler_fila_att)
        if self.store.preferencias.get("verificar_atualizacao", True) and atualizacao.deve_checar(self.store.preferencias):
            self._checar_atualizacao()

    # ------------------------------------------------------------------ início
    def _desbloquear(self):
        while self.store.precisa_mestra:
            self.withdraw()
            senha = pedir_texto(self, "Senha mestra", "Digite a senha mestra para abrir o Adge Group - NF Downloader:", oculto=True)
            if senha is None:
                self.destroy()
                raise SystemExit(0)
            try:
                self.store.abrir(senha)
            except ErroAdge as e:
                messagebox.showerror(NOME_APP, str(e), parent=self)
        self.deiconify()

    def _cabecalho(self):
        barra = tk.Frame(self, bg=VERDE, height=62)
        barra.pack(fill="x")
        barra.pack_propagate(False)
        tk.Label(barra, text="Adge Group", bg=VERDE, fg=BRANCO, font=("Segoe UI Semibold", 18)).pack(side="left", padx=(22, 8))
        tk.Label(barra, text="NF Downloader", bg=VERDE, fg="#D7F2E3", font=("Segoe UI", 14)).pack(side="left")
        tk.Label(barra, text=f"v{VERSAO}", bg=VERDE, fg="#D7F2E3", font=("Segoe UI", 9)).pack(side="right", padx=22)
        self.faixa = tk.Frame(self, bg="#FFF6D6")
        self.l_faixa = tk.Label(self.faixa, text="", bg="#FFF6D6", fg="#7A5B00", cursor="hand2", font=FONTE)
        self.l_faixa.pack(padx=12, pady=6)
        self.info_att = None
        self.l_faixa.bind("<Button-1>", lambda *_: self._abrir_dialogo_att())

    # ------------------------------------------------------------------ aba Empresas
    def _aba_empresas(self):
        aba = ttk.Frame(self.abas, padding=18)
        self.abas.add(aba, text="  Empresas salvas  ")
        ttk.Label(aba, text="Empresas salvas", style="Titulo.TLabel").pack(anchor="w")
        ttk.Label(aba, text="Escolha uma empresa e clique em Buscar notas. O certificado e a senha ficam guardados só neste computador.",
                  style="Muted.TLabel").pack(anchor="w", pady=(0, 10))
        meio = ttk.Frame(aba)
        meio.pack(fill="both", expand=True)
        self.tv = ttk.Treeview(meio, columns=("nome", "cnpj", "tipos", "acao"), show="headings", selectmode="browse")
        for c, t, w in (("nome", "Empresa", 330), ("cnpj", "CNPJ", 150), ("tipos", "Tipos", 170), ("acao", "Ação", 190)):
            self.tv.heading(c, text=t)
            self.tv.column(c, width=w, anchor="w")
        self.tv.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(meio, orient="vertical", command=self.tv.yview)
        self.tv.configure(yscrollcommand=sb.set)
        sb.pack(side="left", fill="y")
        self.tv.bind("<Double-1>", lambda *_: self._buscar())
        self.tv.bind("<<TreeviewSelect>>", lambda *_: self._estado_botoes())
        self.l_vazio = ttk.Label(aba, text="Nenhuma empresa ainda. Clique em \"Adicionar empresa\" para começar.", style="Muted.TLabel")
        lado = ttk.Frame(aba)
        lado.pack(fill="x", pady=(12, 0))
        botao(lado, "Adicionar empresa", self._adicionar).pack(side="left")
        self.b_edit = botao(lado, "Editar", self._editar)
        self.b_edit.pack(side="left", padx=(8, 0))
        self.b_del = botao(lado, "Excluir", self._excluir)
        self.b_del.pack(side="left", padx=(8, 0))
        self.b_busca = botao(lado, "Buscar notas", self._buscar, primario=True)
        self.b_busca.pack(side="right")
        self._estado_botoes()

    def _selecionada(self):
        sel = self.tv.selection()
        return self.store.obter(sel[0]) if sel else None

    def _estado_botoes(self):
        t = "normal" if self.tv.selection() else "disabled"
        for b in (self.b_edit, self.b_del, self.b_busca):
            b.config(state=t)

    def _atualizar_lista(self, escolher=None):
        self.tv.delete(*self.tv.get_children())
        nomes_acao = {"ambos": "Calcular + baixar", "calcular": "Só calcular", "baixar": "Só baixar"}
        for e in self.store.empresas:
            tipos = " e ".join(n for n, k in (("Prestado", "prestado"), ("Tomado", "tomado")) if e["tipos"].get(k))
            self.tv.insert("", "end", iid=e["id"], values=(e["nome"], formatar_cnpj(e["cnpj"]), tipos, nomes_acao[e["acao"]]))
        if escolher and self.tv.exists(escolher):
            self.tv.selection_set(escolher)
        if self.store.empresas:
            self.l_vazio.pack_forget()
        else:
            self.l_vazio.pack(anchor="w", pady=(10, 0))
        self._estado_botoes()

    def _adicionar(self):
        d = DialogoEmpresa(self, self.store)
        self.wait_window(d)
        if d.salvou:
            self.store.salvar()
            self._atualizar_lista(d.emp["id"])

    def _editar(self):
        e = self._selecionada()
        if e:
            d = DialogoEmpresa(self, self.store, e)
            self.wait_window(d)
            if d.salvou:
                self._atualizar_lista(d.emp["id"])

    def _excluir(self):
        e = self._selecionada()
        if e and messagebox.askyesno(NOME_APP, f"Excluir \"{e['nome']}\" e a senha salva dela?\n\nOs XMLs já gravados não são apagados.", parent=self):
            self.store.excluir_empresa(e["id"])
            self._atualizar_lista()

    def _buscar(self):
        e = self._selecionada()
        if e:
            self.wait_window(DialogoBusca(self, self.store, e))

    # ------------------------------------------------------------------ aba Configurações
    def _aba_config(self):
        rolavel = AbaRolavel(self.abas)
        self.abas.add(rolavel, text="  Configurações  ")
        aba = rolavel.corpo
        ttk.Label(aba, text="Configurações", style="Titulo.TLabel").pack(anchor="w")

        ttk.Label(aba, text="Segurança das senhas", style="Sec.TLabel").pack(anchor="w", pady=(14, 2))
        self.l_seg = ttk.Label(aba, text="", style="Muted.TLabel", wraplength=720, justify="left")
        self.l_seg.pack(anchor="w")
        self.f_seg = ttk.Frame(aba)
        self.f_seg.pack(anchor="w", pady=(6, 0))
        self.b_mestra = botao(self.f_seg, "", self._alternar_mestra)
        self.b_mestra.pack(side="left")
        self._atualizar_seguranca()

        ttk.Label(aba, text="Pastas", style="Sec.TLabel").pack(anchor="w", pady=(18, 2))
        lin = ttk.Frame(aba)
        lin.pack(anchor="w", fill="x")
        ttk.Label(lin, text="Pasta padrão para escolher destinos:").pack(side="left")
        self.v_raiz = tk.StringVar(value=self.store.preferencias.get("raiz_padrao", ""))
        ttk.Entry(lin, textvariable=self.v_raiz, width=44).pack(side="left", padx=8)
        botao(lin, "Procurar...", self._escolher_raiz).pack(side="left")
        botao(aba, "Abrir a pasta dos dados do app", lambda: abrir_pasta(self.store.pasta)).pack(anchor="w", pady=(8, 0))

        ttk.Label(aba, text="Atualizações", style="Sec.TLabel").pack(anchor="w", pady=(18, 2))
        self.v_att = tk.BooleanVar(value=self.store.preferencias.get("verificar_atualizacao", True))
        ttk.Checkbutton(aba, text="Avisar quando houver versão nova (consulta só a página de versões do projeto no GitHub)",
                        variable=self.v_att, command=self._salvar_att).pack(anchor="w")
        lin2 = ttk.Frame(aba)
        lin2.pack(anchor="w", pady=(6, 0))
        botao(lin2, "Verificar agora", lambda: self._checar_atualizacao(manual=True)).pack(side="left")
        self.l_att = ttk.Label(lin2, text="", style="Muted.TLabel")
        self.l_att.pack(side="left", padx=10)

        ttk.Label(aba, text="Dados salvos", style="Sec.TLabel").pack(anchor="w", pady=(18, 2))
        ttk.Label(aba, style="Muted.TLabel", wraplength=720, justify="left",
                  text="Desinstalar o programa não apaga as empresas, os certificados e as senhas salvos neste computador. "
                       "Se quiser removê-los (por exemplo, em um computador compartilhado), use o botão abaixo antes de desinstalar.").pack(anchor="w")
        botao(aba, "Apagar todos os meus dados salvos...", self._apagar_dados).pack(anchor="w", pady=(6, 0))

        ttk.Label(aba, text="Sobre", style="Sec.TLabel").pack(anchor="w", pady=(18, 2))
        ttk.Label(aba, justify="left", style="Muted.TLabel", wraplength=760,
                  text=f"{NOME_APP} v{VERSAO} — gratuito. Roda só no seu computador: não há servidor nem conta. "
                       "O certificado A1 é usado apenas para conversar com o ADN oficial da NFS-e Nacional (adn.nfse.gov.br).\n"
                       "Nunca compartilhe o arquivo do certificado nem a senha.").pack(anchor="w")

    def _atualizar_seguranca(self):
        if self.store.modo == "mestra":
            self.l_seg.config(text="As senhas dos certificados estão protegidas por uma senha mestra, que o app pede ao abrir.")
            self.b_mestra.config(text="Voltar ao Cofre do Windows")
        else:
            self.l_seg.config(text="As senhas dos certificados ficam cifradas e a chave fica no Cofre do Windows (sua conta do Windows). "
                                   "Opcionalmente, defina uma senha mestra pedida a cada abertura.")
            self.b_mestra.config(text="Definir senha mestra...")

    def _alternar_mestra(self):
        try:
            if self.store.modo == "mestra":
                if messagebox.askyesno(NOME_APP, "Voltar a proteger as senhas só pelo Cofre do Windows?", parent=self):
                    self.store.trocar_modo(None)
            else:
                nova = pedir_texto(self, "Definir senha mestra", "Escolha uma senha mestra (mínimo 6 caracteres).\n"
                                   "Se você esquecer, será preciso cadastrar as senhas dos certificados de novo.", oculto=True,
                                   validar=lambda t: None if len(t) >= 6 else "Use pelo menos 6 caracteres.")
                if not nova:
                    return
                conf = pedir_texto(self, "Confirmar senha mestra", "Digite a senha mestra de novo:", oculto=True,
                                   validar=lambda t: None if t == nova else "As senhas não são iguais.")
                if conf is None:
                    return
                self.store.trocar_modo(nova)
        except ErroAdge as e:
            messagebox.showerror(NOME_APP, str(e), parent=self)
        self._atualizar_seguranca()

    def _apagar_dados(self):
        n = len(self.store.empresas)
        if not messagebox.askyesno(
                NOME_APP, f"Isso apaga PARA SEMPRE, só neste computador:\n\n• as {n} empresa(s) salva(s);\n"
                          "• as senhas dos certificados;\n• a chave de proteção no Cofre do Windows;\n• as preferências do app.\n\n"
                          "Os certificados (.pfx) e os XMLs já baixados NÃO são apagados.\n\nDeseja continuar?",
                icon="warning", default="no", parent=self):
            return
        if not messagebox.askyesno(NOME_APP, "Confirma apagar tudo? Esta ação não pode ser desfeita.", icon="warning",
                                   default="no", parent=self):
            return
        try:
            self.store.apagar_tudo()
        except ErroAdge as e:
            messagebox.showerror(NOME_APP, str(e), parent=self)
            return
        messagebox.showinfo(NOME_APP, "Dados apagados. O programa será fechado.", parent=self)
        self.destroy()

    def _escolher_raiz(self):
        c = filedialog.askdirectory(parent=self, title="Escolha a pasta padrão", initialdir=self.v_raiz.get() or str(Path.home()))
        if c:
            self.v_raiz.set(os.path.normpath(c))
            self.store.preferencias["raiz_padrao"] = self.v_raiz.get()
            self.store.salvar()

    def _salvar_att(self):
        self.store.preferencias["verificar_atualizacao"] = self.v_att.get()
        self.store.salvar()

    def _checar_atualizacao(self, manual=False):
        """Consulta em segundo plano; o resultado volta pela fila (a janela só mexe na tela no fio principal)."""
        if manual:
            self.l_att.config(text="Verificando...")

        def trabalho():
            try:
                info = atualizacao.consultar(sessao=self.sessao_att)
                self.fila_att.put(("info", (info, manual)))
            except Exception:
                self.fila_att.put(("falha", manual))
        threading.Thread(target=trabalho, daemon=True).start()

    def _ler_fila_att(self):
        self.after(300, self._ler_fila_att)
        try:
            while True:
                tipo, dado = self.fila_att.get_nowait()
                if tipo == "falha":
                    if dado:
                        self.l_att.config(text="Não consegui verificar agora. Confira a internet.")
                    continue
                info, manual = dado
                if not manual:
                    atualizacao.marcar_checagem(self.store.preferencias)
                    try:
                        self.store.salvar()
                    except OSError:
                        pass
                if not info:
                    if manual:
                        self.l_att.config(text=f"Você já está na versão mais recente (v{VERSAO}).")
                    continue
                self.info_att = info
                if manual:
                    self.l_att.config(text=f"Versão {info['tag']} disponível.")
                    self._abrir_dialogo_att()
                elif atualizacao.deve_avisar(info, self.store.preferencias):
                    self.l_faixa.config(text=f"Versão {info['tag']} disponível. Clique para atualizar.")
                    self.faixa.pack(fill="x", after=self.winfo_children()[0])
                    self._abrir_dialogo_att()
        except queue.Empty:
            pass

    def _abrir_dialogo_att(self):
        if not self.info_att:
            return
        d = DialogoAtualizacao(self, self.store, self.info_att, sessao=self.sessao_att)
        self.wait_window(d)
        if not atualizacao.deve_avisar(self.info_att, self.store.preferencias):
            self.faixa.pack_forget()


def main():
    App().mainloop()
