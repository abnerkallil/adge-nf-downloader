"""Visual do programa: paleta (claro/escuro), fontes e componentes de cantos arredondados.

Tudo é Tkinter puro (Canvas), sem imagens nem bibliotecas extras: o instalador não cresce e o programa continua leve.
Regra de uso: os componentes pegam a cor de fundo do "pai" na hora de criar, então crie sempre os widgets dentro de
`tk.Frame`/`Cartao` (e não `ttk.Frame`). Ao trocar de tema, a janela principal é reconstruída.
"""
import os
import re
import sys
import tkinter as tk
import webbrowser
from pathlib import Path
import tkinter.font as tkfont
from tkinter import ttk

from . import NOME_APP

# ----------------------------------------------------------------------------- paleta
TEMAS = {
    "claro": {
        "fundo": "#F3F6F4", "superficie": "#FFFFFF", "campo": "#FFFFFF", "borda": "#DDE6E0", "borda_forte": "#C5D3CA",
        "texto": "#1F2933", "suave": "#667085", "verde": "#1B9E5A", "verde_hover": "#168A4E", "verde_escuro": "#127A44",
        "verde_claro": "#E7F6EE", "hover": "#ECF3EE", "erro": "#B42318", "erro_claro": "#FDE7E7",
        "aviso_fundo": "#FFF6D6", "aviso_texto": "#7A5B00", "azul": "#1D4ED8", "azul_claro": "#E4ECFD",
        "lateral": "#0F5C36", "lateral_hover": "#17704A", "lateral_ativo": "#1B9E5A", "lateral_texto": "#E3F5E9",
        "lateral_suave": "#A9D9BF",
        "pos_fundo": "#E3F5E9", "pos_texto": "#1F9D5B", "neg_fundo": "#FDE7E7", "neg_texto": "#C0392B",
        "linha_alt": "#F8FBF9", "selecao": "#DDF1E5",
    },
    "escuro": {
        "fundo": "#101713", "superficie": "#18221C", "campo": "#101713", "borda": "#27352D", "borda_forte": "#35473C",
        "texto": "#E8EEEA", "suave": "#9AABA1", "verde": "#2DBE74", "verde_hover": "#26A866", "verde_escuro": "#5BD39A",
        "verde_claro": "#1B3A2A", "hover": "#1F2C25", "erro": "#F08A80", "erro_claro": "#3A1D1D",
        "aviso_fundo": "#3A3115", "aviso_texto": "#F3D675", "azul": "#8DB1FF", "azul_claro": "#1D2A4A",
        "lateral": "#0A3822", "lateral_hover": "#0F4A2D", "lateral_ativo": "#1B9E5A", "lateral_texto": "#E3F5E9",
        "lateral_suave": "#8CC4A6",
        "pos_fundo": "#16352A", "pos_texto": "#5BD39A", "neg_fundo": "#3A1D1D", "neg_texto": "#F08A80",
        "linha_alt": "#141D18", "selecao": "#1F3A2B",
    },
}


class _Paleta:
    nome = "claro"


P = _Paleta()


def definir_tema(nome: str):
    nome = nome if nome in TEMAS else "claro"
    for k, v in TEMAS[nome].items():
        setattr(P, k, v)
    P.nome = nome


definir_tema("claro")

# ----------------------------------------------------------------------------- utilidades
def formatar_cnpj(c: str) -> str:
    d = re.sub(r"\D", "", c or "")
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}" if len(d) == 14 else (c or "")


def abrir_pasta(caminho):
    try:
        if sys.platform == "win32":
            os.startfile(str(caminho))  # noqa
        else:
            webbrowser.open(Path(caminho).as_uri())
    except Exception:
        pass


def abrir_link(url: str):
    webbrowser.open(url)


# ----------------------------------------------------------------------------- escala (telas com zoom de 125%, 150%...)
ESCALA = 1.0


def iniciar_dpi():
    """Chame antes de criar a janela: no Windows evita o texto "borrado" em telas com zoom."""
    if sys.platform == "win32":
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def configurar_escala(raiz: tk.Misc):
    global ESCALA
    try:
        ESCALA = max(1.0, raiz.winfo_fpixels("1i") / 96.0)
    except tk.TclError:
        ESCALA = 1.0


def px(n: float) -> int:
    return int(round(n * ESCALA))


# ----------------------------------------------------------------------------- fontes
_FAMILIA = None


def _familia(raiz=None) -> str:
    global _FAMILIA
    if _FAMILIA is None:
        try:
            nomes = set(tkfont.families(raiz))
        except tk.TclError:
            nomes = set()
        _FAMILIA = "Segoe UI" if "Segoe UI" in nomes else ("DejaVu Sans" if "DejaVu Sans" in nomes else "Helvetica")
    return _FAMILIA


def F(tam: int = 10, peso: str = "normal"):
    """Fonte do app. peso: 'normal', 'bold' (semi-negrito no Windows) ou 'italic'."""
    fam = _familia()
    if peso == "bold":
        return ("Segoe UI Semibold", tam) if fam == "Segoe UI" else (fam, tam, "bold")
    if peso == "italic":
        return (fam, tam, "italic")
    return (fam, tam)


def _bg(w) -> str:
    try:
        return w.cget("bg")
    except (tk.TclError, AttributeError):
        return P.fundo


def _cor(c: str) -> str:
    """Aceita o nome de uma cor da paleta ('suave', 'verde_escuro'...) ou um valor "#RRGGBB"."""
    return getattr(P, c, c) if not str(c).startswith("#") else c


def pontos_arredondados(x1, y1, x2, y2, r):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
            x1, y1 + r, x1, y1]


def arredondado(canvas: tk.Canvas, x1, y1, x2, y2, r, **kw):
    return canvas.create_polygon(pontos_arredondados(x1, y1, x2, y2, r), smooth=True, **kw)


# ----------------------------------------------------------------------------- rótulos e divisores
def rotulo(pai, texto="", tam=10, peso="normal", cor="texto", largura=None, justify="left", anchor="w", **kw):
    """Label que herda o fundo do pai. `cor` é uma chave da paleta ('suave', 'erro'...) ou "#RRGGBB"."""
    opcoes = dict(text=texto, bg=_bg(pai), fg=_cor(cor), font=F(tam, peso), justify=justify, anchor=anchor, bd=0)
    if largura:
        opcoes["wraplength"] = largura
    opcoes.update(kw)
    return tk.Label(pai, **opcoes)


def titulo(pai, texto, sub=None):
    f = tk.Frame(pai, bg=_bg(pai))
    rotulo(f, texto, 20, "bold", "verde_escuro").pack(anchor="w")
    if sub:
        rotulo(f, sub, 10, cor="suave", largura=px(720)).pack(anchor="w", pady=(2, 0))
    return f


def secao(pai, texto):
    return rotulo(pai, texto, 12, "bold", "verde_escuro")


def divisor(pai, pady=(10, 10)):
    d = tk.Frame(pai, bg=P.borda, height=1)
    d.pack(fill="x", pady=pady)
    return d


def radio(pai, texto, valor, variavel, comando=None, **kw):
    bg = _bg(pai)
    return tk.Radiobutton(pai, text=texto, value=valor, variable=variavel, command=comando, bg=bg, fg=P.texto,
                          activebackground=bg, activeforeground=P.texto, selectcolor=P.campo, font=F(10), anchor="w",
                          highlightthickness=0, bd=0, cursor="hand2", **kw)


# ----------------------------------------------------------------------------- cartão
class Cartao(tk.Canvas):
    """Quadro de cantos arredondados. Coloque o conteúdo em `.corpo` (um tk.Frame com o fundo do cartão)."""

    def __init__(self, pai, fundo=None, borda=None, raio=14, pad=16, pady=None, **kw):
        self.fundo = _cor(fundo) if fundo else P.superficie
        self.cor_borda = _cor(borda) if borda else P.borda
        self.raio, self.pad = px(raio), px(pad)
        self.pady = px(pady) if pady is not None else self.pad
        super().__init__(pai, bg=_bg(pai), highlightthickness=0, bd=0, height=px(40), **kw)
        self.corpo = tk.Frame(self, bg=self.fundo)
        self._janela = self.create_window(self.pad, self.pady, window=self.corpo, anchor="nw")
        self.bind("<Configure>", self._redesenhar)
        self.corpo.bind("<Configure>", self._ajustar_altura)
        self._largura = 0

    def _redesenhar(self, e=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        self._largura = w
        self.delete("fundo")
        arredondado(self, 1, 1, w - 1, h - 1, self.raio, fill=self.fundo, outline=self.cor_borda, tags="fundo")
        self.tag_lower("fundo")
        self.itemconfigure(self._janela, width=max(10, w - 2 * self.pad))

    def _ajustar_altura(self, e=None):
        h = self.corpo.winfo_reqheight() + 2 * self.pady
        if int(self.cget("height")) != h:
            self.configure(height=h)

    def pintar(self, fundo, borda=None):
        """Troca as cores do cartão (usado no saldo: verde/vermelho)."""
        self.fundo = _cor(fundo)
        if borda:
            self.cor_borda = _cor(borda)
        self.corpo.configure(bg=self.fundo)
        self._pintar_filhos(self.corpo)
        self._redesenhar()

    def _pintar_filhos(self, w):
        for f in w.winfo_children():
            try:
                f.configure(bg=self.fundo)
            except tk.TclError:
                pass
            self._pintar_filhos(f)


# ----------------------------------------------------------------------------- botão
class Botao(tk.Canvas):
    ESTILOS = {
        "primario": ("verde", "verde_hover", "verde", "#FFFFFF", "#FFFFFF"),
        "secundario": ("superficie", "hover", "borda_forte", "texto", "texto"),
        "suave": ("verde_claro", "verde_claro", "verde_claro", "verde_escuro", "verde_escuro"),
        "perigo": ("superficie", "erro_claro", "borda_forte", "erro", "erro"),
        "fantasma": (None, "hover", None, "suave", "texto"),
        "nav": (None, "lateral_hover", None, "lateral_texto", "#FFFFFF"),
        "nav_ativo": ("lateral_ativo", "lateral_ativo", None, "#FFFFFF", "#FFFFFF"),
        "lateral": ("lateral_hover", "lateral_ativo", None, "#FFFFFF", "#FFFFFF"),
    }

    def __init__(self, pai, texto="", comando=None, estilo="secundario", tam=10, padx=18, pady=9, raio=10,
                 largura=None, alinhar="center", **kw):
        self._texto, self._comando, self._estilo, self._estado = texto, comando, estilo, "normal"
        self._raio, self._alinhar, self._tam, self._padx = px(raio), alinhar, tam, px(padx)
        self._fonte = F(tam, "bold" if estilo in ("primario", "nav_ativo") else "normal")
        self._hover = False
        self._foco = False
        medida = tkfont.Font(family=self._fonte[0], size=self._fonte[1], weight="bold" if len(self._fonte) > 2 else "normal")
        w = medida.measure(texto) + 2 * self._padx
        if largura:
            w = max(w, px(largura))
        h = medida.metrics("linespace") + 2 * px(pady)
        super().__init__(pai, bg=_bg(pai), highlightthickness=0, bd=0, width=w, height=h, cursor="hand2", takefocus=1, **kw)
        self._medida = medida
        self._pady = px(pady)
        self.bind("<Configure>", lambda e: self._desenhar())
        self.bind("<Enter>", lambda e: self._mudar(hover=True))
        self.bind("<Leave>", lambda e: self._mudar(hover=False))
        self.bind("<ButtonRelease-1>", self._soltou)
        self.bind("<FocusIn>", lambda e: self._mudar(foco=True))
        self.bind("<FocusOut>", lambda e: self._mudar(foco=False))
        self.bind("<space>", lambda e: self.invoke())
        self.bind("<Return>", lambda e: self.invoke())

    # -- aparência
    def _cores(self):
        fundo, fundo_h, borda, txt, txt_h = self.ESTILOS[self._estilo]
        if self._estado == "disabled":
            ligado = self._estilo in ("primario", "nav_ativo", "suave")
            return (P.borda if ligado else None), None, P.borda_forte if self._estilo == "secundario" else None, P.suave
        f = fundo_h if self._hover else fundo
        return (_cor(f) if f else None), None, (_cor(borda) if borda else None), _cor(txt_h if self._hover else txt)

    def _mudar(self, hover=None, foco=None):
        if hover is not None:
            self._hover = hover and self._estado != "disabled"
        if foco is not None:
            self._foco = foco
        self._desenhar()

    def _desenhar(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        self.configure(bg=_bg(self.master))
        self.delete("all")
        fundo, _, borda, txt = self._cores()
        if fundo or borda:
            arredondado(self, 1, 1, w - 1, h - 1, self._raio, fill=fundo or "", outline=borda or fundo or "")
        if self._foco and self._estado != "disabled":
            arredondado(self, 2, 2, w - 2, h - 2, self._raio, fill="", outline=P.verde, width=2)
        if self._alinhar == "w":
            self.create_text(self._padx, h / 2, text=self._texto, font=self._fonte, fill=txt, anchor="w")
        else:
            self.create_text(w / 2, h / 2, text=self._texto, font=self._fonte, fill=txt)
        self.configure(cursor="hand2" if self._estado != "disabled" else "arrow")

    def _soltou(self, e):
        if self._estado == "disabled":
            return
        if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
            self.invoke()

    # -- interface parecida com a do ttk.Button (o resto do código usa .config(state=...), .invoke(), .cget("text"))
    def configure(self, cnf=None, **kw):
        if isinstance(cnf, dict):
            kw.update(cnf)
        redesenhar = False
        if "text" in kw:
            self._texto = kw.pop("text")
            largura = self._medida.measure(self._texto) + 2 * self._padx
            if largura > int(self.cget("width")) or not self._texto:
                super().configure(width=largura)
            redesenhar = True
        if "state" in kw:
            self._estado = kw.pop("state")
            if self._estado == "disabled":
                self._hover = False
            redesenhar = True
        if "command" in kw:
            self._comando = kw.pop("command")
        if "style" in kw:
            self._estilo = kw.pop("style")
            redesenhar = True
        r = super().configure(**kw) if kw else None
        if redesenhar:
            self._desenhar()
        return r

    config = configure

    def cget(self, chave):
        if chave == "text":
            return self._texto
        if chave == "state":
            return self._estado
        return super().cget(chave)

    def state(self, estados=None):  # compatível com ttk: b.state(["disabled"])
        if estados:
            self.configure(state="disabled" if "disabled" in estados else "normal")

    def invoke(self):
        if self._estado != "disabled" and self._comando:
            return self._comando()


# ----------------------------------------------------------------------------- campo de texto
class Campo(tk.Canvas):
    """Campo de texto de cantos arredondados. O tk.Entry fica em `.entry`."""

    def __init__(self, pai, variavel=None, largura=24, mostrar="", tam=10, raio=10, **kw):
        super().__init__(pai, bg=_bg(pai), highlightthickness=0, bd=0, **kw)
        self._raio, self._pad = px(raio), px(10)
        self.entry = tk.Entry(self, textvariable=variavel, show=mostrar, relief="flat", bd=0, highlightthickness=0,
                              font=F(tam), bg=P.campo, fg=P.texto, insertbackground=P.texto, width=largura,
                              disabledbackground=P.campo, disabledforeground=P.suave,
                              selectbackground=P.selecao, selectforeground=P.texto)
        self._pady = px(8)
        self._janela = self.create_window(self._pad, self._pady, window=self.entry, anchor="nw")
        self.configure(height=self.entry.winfo_reqheight() + 2 * self._pady,
                       width=self.entry.winfo_reqwidth() + 2 * self._pad)
        self._foco = False
        self.bind("<Configure>", self._redesenhar)
        self.entry.bind("<FocusIn>", lambda e: self._foco_mudou(True))
        self.entry.bind("<FocusOut>", lambda e: self._foco_mudou(False))

    def _foco_mudou(self, sim):
        self._foco = sim
        self._redesenhar()

    def _redesenhar(self, e=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        self.configure(bg=_bg(self.master))
        self.delete("fundo")
        desabilitado = str(self.entry.cget("state")) == "disabled"
        arredondado(self, 1, 1, w - 1, h - 1, self._raio, fill=P.campo, tags="fundo",
                    outline=P.verde if self._foco else P.borda_forte, width=2 if self._foco else 1)
        self.tag_lower("fundo")
        self.itemconfigure(self._janela, width=max(10, w - 2 * self._pad))
        self.entry.configure(bg=P.campo)

    def get(self):
        return self.entry.get()

    def focus_set(self):
        self.entry.focus_set()

    def configure(self, cnf=None, **kw):
        if "show" in kw:
            self.entry.configure(show=kw.pop("show"))
        if "state" in kw:
            self.entry.configure(state=kw.pop("state"))
            self._redesenhar()
        return super().configure(cnf, **kw) if (kw or cnf) else None

    config = configure


# ----------------------------------------------------------------------------- etiqueta (chip)
class Chip(tk.Canvas):
    TONS = {"verde": ("verde_claro", "verde_escuro"), "vermelho": ("erro_claro", "erro"), "neutro": ("hover", "suave"),
            "amarelo": ("aviso_fundo", "aviso_texto"), "azul": ("azul_claro", "azul")}

    def __init__(self, pai, texto, tom="neutro", tam=9):
        self._tom, self._texto = tom, texto
        self._fonte = F(tam, "bold")
        self._medida = tkfont.Font(family=self._fonte[0], size=self._fonte[1], weight="bold" if len(self._fonte) > 2 else "normal")
        w = self._medida.measure(texto) + px(20)
        h = self._medida.metrics("linespace") + px(8)
        super().__init__(pai, bg=_bg(pai), highlightthickness=0, bd=0, width=w, height=h)
        self.bind("<Configure>", lambda e: self._desenhar())

    def _desenhar(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        fundo, texto = self.TONS[self._tom]
        self.configure(bg=_bg(self.master))
        self.delete("all")
        arredondado(self, 0, 0, w - 1, h - 1, h / 2, fill=_cor(fundo), outline=_cor(fundo))
        self.create_text(w / 2, h / 2, text=self._texto, font=self._fonte, fill=_cor(texto))

    def cget(self, chave):
        return self._texto if chave == "text" else super().cget(chave)


def fluxo(frame, widgets, hgap=6, vgap=6):
    """Dispõe os widgets em linhas que quebram sozinhas conforme a largura de `frame` (como texto que desce de linha)."""
    def refluir(e=None):
        if not frame.winfo_exists():
            return
        largura = frame.winfo_width()
        if largura < 50:
            return
        for w in widgets:
            w.grid_forget()
        x = linha = coluna = 0
        for w in widgets:
            lw = w.winfo_reqwidth() + px(hgap)
            if coluna and x + lw > largura:
                linha, coluna, x = linha + 1, 0, 0
            w.grid(row=linha, column=coluna, padx=(0, px(hgap)), pady=(0, px(vgap)), sticky="w")
            x += lw
            coluna += 1
    frame.bind("<Configure>", refluir, add="+")
    frame.after_idle(refluir)
    return refluir


# ----------------------------------------------------------------------------- marcador (chip com marca de seleção)
class Marcador(tk.Canvas):
    """Chip clicável: ligado mostra o ✓ e a cor da categoria; desligado fica apagado. Usado para escolher o que entra nos números."""
    TONS = {"verde": ("verde_claro", "verde_escuro"), "vermelho": ("erro_claro", "erro"), "neutro": ("hover", "texto"),
            "amarelo": ("aviso_fundo", "aviso_texto"), "azul": ("azul_claro", "azul")}

    def __init__(self, pai, texto, variavel: tk.BooleanVar, comando=None, tom="verde", tam=10):
        self._tom, self._texto, self.var, self.comando = tom, texto, variavel, comando
        self._fonte = F(tam, "bold")
        self._medida = tkfont.Font(family=self._fonte[0], size=self._fonte[1], weight="bold")
        w = self._medida.measure("✓  " + texto) + px(26)
        h = self._medida.metrics("linespace") + px(14)
        super().__init__(pai, bg=_bg(pai), highlightthickness=0, bd=0, width=w, height=h, cursor="hand2")
        self.bind("<Configure>", lambda e: self._desenhar())
        self.bind("<Button-1>", self._alternar)
        self._traco = variavel.trace_add("write", lambda *_: self._desenhar())

    def _desenhar(self):
        if not self.winfo_exists():
            return
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        fundo, texto = self.TONS[self._tom]
        ligado = bool(self.var.get())
        self.configure(bg=_bg(self.master))
        self.delete("all")
        if ligado:
            arredondado(self, 1, 1, w - 2, h - 2, h / 2, fill=_cor(fundo), outline=_cor(texto))
            self.create_text(w / 2, h / 2, text="✓  " + self._texto, font=self._fonte, fill=_cor(texto))
        else:
            arredondado(self, 1, 1, w - 2, h - 2, h / 2, fill=_cor("superficie"), outline=_cor("borda_forte"))
            self.create_text(w / 2, h / 2, text="    " + self._texto, font=F(self._fonte[1], "normal"), fill=_cor("suave"))

    def _alternar(self, e=None):
        self.var.set(not self.var.get())
        if self.comando:
            self.comando()

    def cget(self, chave):
        return self._texto if chave == "text" else super().cget(chave)


# ----------------------------------------------------------------------------- interruptor (sim/não)
class Interruptor(tk.Frame):
    def __init__(self, pai, texto, variavel: tk.BooleanVar, comando=None, tam=10, desabilitado=False):
        super().__init__(pai, bg=_bg(pai))
        self.var, self.comando, self._desab = variavel, comando, desabilitado
        self.tela = tk.Canvas(self, width=px(40), height=px(22), bg=_bg(pai), highlightthickness=0, bd=0,
                              cursor="hand2" if not desabilitado else "arrow")
        self.tela.pack(side="left")
        self.rot = rotulo(self, texto, tam, cor="suave" if desabilitado else "texto", cursor="hand2" if not desabilitado else "arrow")
        self.rot.pack(side="left", padx=(10, 0))
        for w in (self.tela, self.rot):
            w.bind("<Button-1>", self._alternar)
        self.var.trace_add("write", lambda *_: self._desenhar())
        self._desenhar()

    def _desenhar(self):
        if not self.winfo_exists():
            return
        t = self.tela
        t.delete("all")
        w, h = px(40), px(22)
        ligado = bool(self.var.get())
        cor = P.verde if ligado else P.borda_forte
        if self._desab:
            cor = P.borda
        arredondado(t, 1, 1, w - 1, h - 1, h / 2, fill=cor, outline=cor)
        r = h / 2 - px(3)
        cx = w - h / 2 if ligado else h / 2
        t.create_oval(cx - r, h / 2 - r, cx + r, h / 2 + r, fill="#FFFFFF", outline="#FFFFFF")

    def _alternar(self, e=None):
        if self._desab:
            return
        self.var.set(not self.var.get())
        if self.comando:
            self.comando()


# ----------------------------------------------------------------------------- seletor em pílulas
class Segmentado(tk.Canvas):
    """Grupo de opções lado a lado (um só escolhido). opcoes = [(valor, texto), ...]."""

    def __init__(self, pai, opcoes, variavel: tk.StringVar, comando=None, tam=10, padx=14, pady=7):
        self.opcoes, self.var, self.comando = list(opcoes), variavel, comando
        self._fonte = F(tam)
        self._fonte_sel = F(tam, "bold")
        medida = tkfont.Font(family=self._fonte[0], size=self._fonte[1])
        self._larguras = [medida.measure(t) + 2 * px(padx) for _, t in self.opcoes]
        self._h = medida.metrics("linespace") + 2 * px(pady) + px(6)
        self._off = set()
        super().__init__(pai, bg=_bg(pai), highlightthickness=0, bd=0, width=sum(self._larguras) + px(8), height=self._h)
        self.bind("<Configure>", lambda e: self._desenhar())
        self.bind("<Button-1>", self._clicou)
        self.var.trace_add("write", lambda *_: self.winfo_exists() and self._desenhar())

    def desabilitar(self, valor, sim=True):
        (self._off.add if sim else self._off.discard)(valor)
        self._desenhar()

    def _desenhar(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        self.configure(bg=_bg(self.master))
        self.delete("all")
        arredondado(self, 1, 1, w - 1, h - 1, px(11), fill=P.hover, outline=P.borda)
        x = px(4)
        for (valor, texto), largura in zip(self.opcoes, self._larguras):
            sel = self.var.get() == valor
            if sel:
                arredondado(self, x, px(3), x + largura, h - px(3), px(9), fill=P.superficie, outline=P.borda_forte)
            cor = P.suave if valor in self._off else (P.verde_escuro if sel else P.suave)
            self.create_text(x + largura / 2, h / 2, text=texto, font=self._fonte_sel if sel else self._fonte, fill=cor)
            x += largura
        self.configure(cursor="hand2")

    def _clicou(self, e):
        x = px(4)
        for (valor, _), largura in zip(self.opcoes, self._larguras):
            if x <= e.x <= x + largura and valor not in self._off:
                self.var.set(valor)
                if self.comando:
                    self.comando()
                return
            x += largura


# ----------------------------------------------------------------------------- barra de progresso
class Barra(tk.Canvas):
    def __init__(self, pai, altura=8):
        super().__init__(pai, bg=_bg(pai), highlightthickness=0, bd=0, height=px(altura))
        self._ativa, self._pos, self._frac = False, 0.0, None
        self.bind("<Configure>", lambda e: self._desenhar())

    def iniciar(self):
        self._ativa, self._frac = True, None
        self._passo()

    def parar(self):
        self._ativa = False
        self._desenhar()

    def definir(self, frac):
        self._ativa, self._frac = False, max(0.0, min(1.0, frac))
        self._desenhar()

    def _passo(self):
        if not self._ativa or not self.winfo_exists():
            return
        self._pos = (self._pos + 0.022) % 1.4
        self._desenhar()
        self.after(30, self._passo)

    def _desenhar(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        self.configure(bg=_bg(self.master))
        self.delete("all")
        arredondado(self, 0, 0, w, h, h / 2, fill=P.verde_claro, outline=P.verde_claro)
        if self._ativa:
            x1 = (self._pos - 0.4) * w
            a, b = max(0, x1), min(w, x1 + 0.4 * w)
            if b > a:
                arredondado(self, a, 0, b, h, h / 2, fill=P.verde, outline=P.verde)
        elif self._frac:
            arredondado(self, 0, 0, max(h, w * self._frac), h, h / 2, fill=P.verde, outline=P.verde)


# ----------------------------------------------------------------------------- área com rolagem
class Rolavel(tk.Frame):
    """Frame com barra de rolagem vertical fina. O conteúdo vai em `.corpo`."""

    def __init__(self, pai, fundo=None, pad=0):
        self.fundo = _cor(fundo) if fundo else _bg(pai)
        super().__init__(pai, bg=self.fundo)
        self.tela = tk.Canvas(self, bg=self.fundo, highlightthickness=0, bd=0)
        self.barra = ttk.Scrollbar(self, orient="vertical", command=self.tela.yview, style="Adge.Vertical.TScrollbar")
        self.tela.configure(yscrollcommand=self._barra)
        self.tela.pack(side="left", fill="both", expand=True)
        self.corpo = tk.Frame(self.tela, bg=self.fundo, padx=px(pad), pady=px(pad))
        self._id = self.tela.create_window((0, 0), window=self.corpo, anchor="nw")
        self.corpo.bind("<Configure>", lambda e: self.tela.configure(scrollregion=self.tela.bbox("all")))
        self.tela.bind("<Configure>", lambda e: self.tela.itemconfigure(self._id, width=e.width))
        self.bind("<Enter>", lambda e: self.tela.bind_all("<MouseWheel>", self._roda))
        self.bind("<Leave>", lambda e: self.tela.unbind_all("<MouseWheel>"))

    def _barra(self, a, b):
        self.barra.set(a, b)
        if float(a) <= 0.0 and float(b) >= 1.0:
            self.barra.pack_forget()
        elif not self.barra.winfo_ismapped():
            self.barra.pack(side="right", fill="y", padx=(4, 0))

    def _roda(self, e):
        if self.corpo.winfo_reqheight() > self.tela.winfo_height():
            self.tela.yview_scroll(-1 if e.delta > 0 else 1, "units")

    def topo(self):
        self.tela.yview_moveto(0)


# ----------------------------------------------------------------------------- janelas
def centralizar(janela: tk.Toplevel, pai: tk.Misc):
    janela.update_idletasks()
    x = pai.winfo_rootx() + (pai.winfo_width() - janela.winfo_width()) // 2
    y = pai.winfo_rooty() + (pai.winfo_height() - janela.winfo_height()) // 3
    janela.geometry(f"+{max(0, x)}+{max(0, y)}")


class Modal(tk.Toplevel):
    """Janela modal, centralizada sobre a janela de origem."""

    def __init__(self, pai, titulo, largura=None, altura=None, margem=24):
        super().__init__(pai)
        self.pai = pai
        self.title(titulo)
        self.configure(bg=P.fundo, padx=px(margem), pady=px(max(margem - 4, 0)))
        self.transient(pai.winfo_toplevel())
        self.resizable(False, False)
        if largura and altura:
            self.geometry(f"{px(largura)}x{px(altura)}")

    def mostrar(self):
        centralizar(self, self.pai.winfo_toplevel())
        self.grab_set()
        self.focus_set()


class _Caixa(Modal):
    ICONES = {"info": ("i", "azul", "azul_claro"), "aviso": ("!", "aviso_texto", "aviso_fundo"),
              "erro": ("×", "erro", "erro_claro"), "pergunta": ("?", "verde_escuro", "verde_claro")}

    def __init__(self, pai, titulo, texto, tipo, botoes):
        super().__init__(pai, NOME_APP)
        self.resposta = None
        cab = tk.Frame(self, bg=P.fundo)
        cab.pack(fill="x")
        letra, cor, fundo = self.ICONES[tipo]
        ic = tk.Canvas(cab, width=px(44), height=px(44), bg=P.fundo, highlightthickness=0)
        ic.create_oval(1, 1, px(44) - 1, px(44) - 1, fill=_cor(fundo), outline=_cor(fundo))
        ic.create_text(px(22), px(22), text=letra, font=F(16, "bold"), fill=_cor(cor))
        ic.pack(side="left", anchor="n")
        txt = tk.Frame(cab, bg=P.fundo)
        txt.pack(side="left", padx=(14, 0), fill="x", expand=True)
        rotulo(txt, titulo, 13, "bold", "texto", largura=px(380)).pack(anchor="w")
        if texto:
            rotulo(txt, texto, 10, cor="suave", largura=px(380)).pack(anchor="w", pady=(4, 0))
        linha = tk.Frame(self, bg=P.fundo)
        linha.pack(fill="x", pady=(18, 0))
        for i, (rot, valor, estilo) in enumerate(reversed(botoes)):
            b = Botao(linha, rot, lambda v=valor: self._fim(v), estilo=estilo)
            b.pack(side="right", padx=(0 if i == 0 else 8, 0))
            if estilo == "primario" or (i == 0 and len(botoes) == 1):
                self.padrao = b
        self.protocol("WM_DELETE_WINDOW", lambda: self._fim(None))
        self.bind("<Escape>", lambda e: self._fim(None))
        self.bind("<Return>", lambda e: getattr(self, "padrao", None) and self.padrao.invoke())
        self.mostrar()

    def _fim(self, valor):
        self.resposta = valor
        self.destroy()


def _mostrar(pai, titulo, texto, tipo, botoes):
    d = _Caixa(pai, titulo, texto, tipo, botoes)
    d.wait_window()
    return d.resposta


def informar(pai, titulo, texto=""):
    _mostrar(pai, titulo, texto, "info", [("OK", True, "primario")])


def avisar(pai, titulo, texto=""):
    _mostrar(pai, titulo, texto, "aviso", [("OK", True, "primario")])


def erro(pai, titulo, texto=""):
    _mostrar(pai, titulo, texto, "erro", [("OK", True, "primario")])


def perguntar(pai, titulo, texto="", sim="Sim", nao="Não", perigo=False, padrao_sim=True):
    """Pergunta de sim/não. Devolve True/False."""
    botoes = [(nao, False, "secundario"), (sim, True, "perigo" if perigo else "primario")]
    return bool(_mostrar(pai, titulo, texto, "aviso" if perigo else "pergunta", botoes))


def pedir_texto(pai, titulo, mensagem, oculto=False, validar=None, inicial=""):
    """Caixa simples com um campo. Devolve o texto ou None."""
    j = Modal(pai, titulo)
    rotulo(j, mensagem, 10, largura=px(380)).pack(anchor="w", pady=(0, 10))
    var = tk.StringVar(value=inicial)
    campo = Campo(j, var, largura=36, mostrar="●" if oculto else "")
    campo.pack(fill="x")
    erro_ = rotulo(j, "", 10, cor="erro", largura=px(380))
    erro_.pack(anchor="w", pady=(6, 0))
    saida = {"v": None}

    def ok(*_):
        v = var.get()
        if validar:
            msg = validar(v)
            if msg:
                erro_.config(text=msg)
                return
        saida["v"] = v
        j.destroy()

    linha = tk.Frame(j, bg=P.fundo)
    linha.pack(fill="x", pady=(14, 0))
    Botao(linha, "Cancelar", j.destroy).pack(side="right")
    Botao(linha, "OK", ok, estilo="primario").pack(side="right", padx=(0, 8))
    j.bind("<Return>", ok)
    j.bind("<Escape>", lambda *_: j.destroy())
    j.mostrar()
    campo.focus_set()
    j.wait_window()
    return saida["v"]


# ----------------------------------------------------------------------------- estilos ttk (tabelas, listas, rolagem)
def aplicar_estilos(raiz: tk.Tk):
    raiz.configure(bg=P.fundo)
    s = ttk.Style(raiz)
    try:
        s.theme_use("clam")
    except tk.TclError:
        pass
    s.configure(".", background=P.superficie, foreground=P.texto, font=F(10), bordercolor=P.borda, focuscolor=P.superficie)
    s.configure("Treeview", rowheight=px(34), background=P.superficie, fieldbackground=P.superficie, foreground=P.texto,
                borderwidth=0, relief="flat", font=F(10))
    s.configure("Treeview.Heading", background=P.superficie, foreground=P.suave, font=F(9, "bold"), borderwidth=0,
                relief="flat", padding=(px(8), px(8)))
    s.map("Treeview", background=[("selected", P.selecao)], foreground=[("selected", P.texto)])
    s.map("Treeview.Heading", background=[("active", P.hover)])
    s.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
    s.configure("TCombobox", fieldbackground=P.campo, background=P.campo, foreground=P.texto, bordercolor=P.borda_forte,
                lightcolor=P.campo, darkcolor=P.campo, arrowcolor=P.suave, padding=px(8), arrowsize=px(14))
    s.map("TCombobox", fieldbackground=[("readonly", P.campo)], selectbackground=[("readonly", P.campo)],
          selectforeground=[("readonly", P.texto)], bordercolor=[("focus", P.verde)])
    raiz.option_add("*TCombobox*Listbox.background", P.campo)
    raiz.option_add("*TCombobox*Listbox.foreground", P.texto)
    raiz.option_add("*TCombobox*Listbox.selectBackground", P.selecao)
    raiz.option_add("*TCombobox*Listbox.selectForeground", P.texto)
    raiz.option_add("*TCombobox*Listbox.font", F(10))
    s.layout("Adge.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
        ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    s.configure("Adge.Vertical.TScrollbar", background=P.borda_forte, troughcolor=P.fundo, bordercolor=P.fundo,
                lightcolor=P.borda_forte, darkcolor=P.borda_forte, gripcount=0, width=px(8))
    s.map("Adge.Vertical.TScrollbar", background=[("active", P.suave)])
