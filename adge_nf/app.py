"""Janela principal do Adge Group - NF Downloader: menu lateral, empresas, histórico, configurações e sobre."""
import datetime as dt
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from . import NOME_APP, SITE_ADGE, URL_GITHUB, URL_GOOGLE_ADGE, VERSAO, atualizacao, core
from . import ui
from .busca import DialogoBusca
from .nfe_cache import HistoricoNFe
from .core import ErroAdge
from .dialogos import (PREF_BOAS_VINDAS, TEXTOS_MISSAO, DialogoAtualizacao, DialogoBoasVindas, DialogoEmpresa,  # noqa: F401
                       boas_vindas_pendente)
from .store import Armazenamento
from .ui import P, Botao, Cartao, Chip, Interruptor, Rolavel, F, px, rotulo

formatar_cnpj = ui.formatar_cnpj
ACOES = {"ambos": "Calcular + baixar", "calcular": "Só calcular", "baixar": "Só baixar"}
PAGINAS = (("empresas", "Empresas"), ("historico", "Histórico"), ("config", "Configurações"), ("sobre", "Sobre"))


def quando_humano(iso: str, agora: dt.datetime = None) -> str:
    """'hoje 14:30', 'ontem 09:10' ou '12/09/2026 16:00'."""
    try:
        t = dt.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ""
    agora = agora or dt.datetime.now()
    dias = (agora.date() - t.date()).days
    if dias == 0:
        return f"hoje {t:%H:%M}"
    if dias == 1:
        return f"ontem {t:%H:%M}"
    return f"{t:%d/%m/%Y %H:%M}"


def situacao_certificado(iso: str, hoje: dt.date = None):
    """(texto, tom) do selo de validade do certificado, ou None se a validade ainda não é conhecida."""
    try:
        venc = dt.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    dias = (venc - (hoje or dt.date.today())).days
    if dias < 0:
        return f"Certificado vencido em {venc:%d/%m/%Y}", "vermelho"
    if dias <= 60:
        return f"Certificado vence em {dias} dia(s)" if dias else "Certificado vence hoje", "amarelo"
    return f"Certificado válido até {venc:%d/%m/%Y}", "verde"


class App(tk.Tk):
    def __init__(self, store: Armazenamento = None):
        ui.iniciar_dpi()
        self.store = store or Armazenamento()
        ui.definir_tema(self.store.preferencias.get("tema", "claro"))
        super().__init__()
        ui.configurar_escala(self)
        self.title(NOME_APP)
        self.geometry(f"{px(1100)}x{px(720)}")
        self.minsize(px(900), px(600))
        icone = next((c for c in (Path(sys.executable).with_name("icone.ico"), Path(__file__).with_name("icone.ico")) if c.exists()), None)
        if icone and sys.platform == "win32":
            try:
                self.iconbitmap(str(icone))
            except tk.TclError:
                pass
        self._desbloquear()
        self.fila_att: "queue.Queue" = queue.Queue()
        self.fila_cert: "queue.Queue" = queue.Queue()
        self.sessao_att = None  # os testes injetam uma sessão falsa
        self.info_att = None
        self.pagina = "empresas"
        self.selecionada_id = None
        self._montar()
        self.bind("<Control-n>", lambda *_: self._adicionar())
        self.bind("<Return>", self._enter)
        self.after(300, self._ler_fila_att)
        self.after(250, self._abertura)
        self.after(1500, self._atualizar_validades)

    # ------------------------------------------------------------------ início
    def _abertura(self):
        """Primeira abertura: boas-vindas. Depois, a consulta diária de versão nova (sem sobrepor janelas)."""
        if not self.winfo_exists():
            return
        if boas_vindas_pendente(self.store.preferencias):
            self.wait_window(DialogoBoasVindas(self, self.store, ao_adicionar=self._adicionar))
        if not self.winfo_exists():
            return
        if self.store.preferencias.get("verificar_atualizacao", True) and atualizacao.deve_checar(self.store.preferencias):
            self._checar_atualizacao()

    def _desbloquear(self):
        while self.store.precisa_mestra:
            self.withdraw()
            ui.aplicar_estilos(self)
            senha = ui.pedir_texto(self, "Senha mestra", "Digite a senha mestra para abrir o Adge Group - NF Downloader:", oculto=True)
            if senha is None:
                self.destroy()
                raise SystemExit(0)
            try:
                self.store.abrir(senha)
            except ErroAdge as e:
                ui.erro(self, "Senha mestra incorreta", str(e))
        self.deiconify()

    # ------------------------------------------------------------------ estrutura (menu lateral + páginas)
    def _montar(self):
        for w in self.winfo_children():
            w.destroy()
        ui.aplicar_estilos(self)
        self.lateral = tk.Frame(self, bg=P.lateral, width=px(220))
        self.lateral.pack(side="left", fill="y")
        self.lateral.pack_propagate(False)
        self._lateral()
        self.direita = tk.Frame(self, bg=P.fundo)
        self.direita.pack(side="left", fill="both", expand=True)
        self.faixa = tk.Frame(self.direita, bg=P.aviso_fundo)
        self.l_faixa = tk.Label(self.faixa, text="", bg=P.aviso_fundo, fg=P.aviso_texto, cursor="hand2", font=F(10, "bold"))
        self.l_faixa.pack(padx=12, pady=7)
        self.l_faixa.bind("<Button-1>", lambda *_: self._abrir_dialogo_att())
        self.conteudo = tk.Frame(self.direita, bg=P.fundo)
        self.conteudo.pack(fill="both", expand=True)
        self.paginas = {}
        self._pagina_empresas()
        self._pagina_historico()
        self._pagina_config()
        self._pagina_sobre()
        self._ir(self.pagina)
        if self.info_att and atualizacao.deve_avisar(self.info_att, self.store.preferencias):
            self._mostrar_faixa()

    def _lateral(self):
        marca = tk.Frame(self.lateral, bg=P.lateral)
        marca.pack(fill="x", padx=px(20), pady=(px(26), px(22)))
        rotulo(marca, "Adge Group", 18, "bold", "#FFFFFF").pack(anchor="w")
        rotulo(marca, "NF Downloader", 11, cor="lateral_suave").pack(anchor="w")
        self.nav = {}
        for chave, nome in PAGINAS:
            b = Botao(self.lateral, nome, lambda c=chave: self._ir(c), estilo="nav", alinhar="w", largura=186, pady=10, tam=11, padx=16)
            b.pack(padx=px(16), pady=2, anchor="w")
            self.nav[chave] = b
        rodape = tk.Frame(self.lateral, bg=P.lateral)
        rodape.pack(side="bottom", fill="x", padx=px(16), pady=(0, px(18)))
        self.b_fale = Botao(rodape, "Fale com a Adge", lambda: ui.abrir_link(SITE_ADGE), estilo="lateral", largura=186, pady=9)
        self.b_fale.pack(anchor="w")
        site = rotulo(rodape, SITE_ADGE.replace("https://", "").rstrip("/"), 9, cor="lateral_suave", cursor="hand2")
        site.pack(anchor="w", pady=(10, 0))
        site.bind("<Button-1>", lambda *_: ui.abrir_link(SITE_ADGE))
        rotulo(rodape, f"Versão {VERSAO}", 9, cor="lateral_suave").pack(anchor="w")

    def _ir(self, nome):
        self.pagina = nome
        for chave, b in self.nav.items():
            b.config(style="nav_ativo" if chave == nome else "nav")
        for chave, f in self.paginas.items():
            f.pack_forget()
        self.paginas[nome].pack(fill="both", expand=True)
        if nome == "empresas":
            self._atualizar_lista(self.selecionada_id)
        elif nome == "historico":
            self._atualizar_historico()

    def _cabecalho_pagina(self, pai, titulo, sub, acao=None):
        cab = tk.Frame(pai, bg=P.fundo)
        cab.pack(fill="x", padx=px(32), pady=(px(26), px(14)))
        ui.titulo(cab, titulo, sub).pack(side="left", anchor="w")
        if acao:
            acao(cab).pack(side="right", anchor="n")
        return cab

    # ------------------------------------------------------------------ página Empresas
    def _pagina_empresas(self):
        f = tk.Frame(self.conteudo, bg=P.fundo)
        self.paginas["empresas"] = f
        self._cabecalho_pagina(
            f, "Empresas salvas",
            "Escolha uma empresa e clique em Buscar. O certificado e a senha ficam guardados só neste computador.",
            lambda cab: Botao(cab, "+  Adicionar empresa", self._adicionar, estilo="primario", tam=10))
        self.rolagem = Rolavel(f)
        self.rolagem.pack(fill="both", expand=True, padx=(px(32), px(24)), pady=(0, px(16)))
        self.f_cards = tk.Frame(self.rolagem.corpo, bg=P.fundo)
        self.f_cards.pack(fill="x", anchor="n")
        self._cartoes = []
        self._colunas = 0
        self.rolagem.tela.bind("<Configure>", self._redimensionou, add="+")

    def _selecionada(self):
        if not self.selecionada_id:
            return None
        return next((e for e in self.store.empresas if e["id"] == self.selecionada_id), None)

    def _ultima_consulta(self, id_):
        for h in self.store.preferencias.get("historico", []):
            if h.get("empresa_id") == id_:
                return f"Última consulta: {core.MESES_TELA[h['mes'] - 1]}/{h['ano']} · {quando_humano(h.get('quando'))}"
        return "Nenhuma consulta ainda"

    def _atualizar_lista(self, escolher=None):
        for w in self.f_cards.winfo_children():
            w.destroy()
        self._cartoes = []
        self._colunas = 0
        if escolher is not None:
            self.selecionada_id = escolher
        if not any(e["id"] == self.selecionada_id for e in self.store.empresas):
            self.selecionada_id = None
        if not self.store.empresas:
            self._vazio()
            return
        for e in self.store.empresas:
            self._cartoes.append((e["id"], self._cartao_empresa(e)))
        self._pintar_selecao()
        self._layout_cartoes()

    def _vazio(self):
        c = Cartao(self.f_cards, pad=28)
        c.pack(fill="x", pady=(px(20), 0))
        rotulo(c.corpo, "Nenhuma empresa por aqui ainda", 15, "bold", "verde_escuro").pack(anchor="w")
        rotulo(c.corpo, "Cadastre a primeira empresa com o certificado A1 dela. Depois é só escolher o mês e buscar as notas, "
                        "sem digitar a senha toda vez.", 10, cor="suave", largura=px(620)).pack(anchor="w", pady=(6, 14))
        self.b_primeira = Botao(c.corpo, "+  Adicionar a primeira empresa", self._adicionar, estilo="primario", tam=11, pady=11)
        self.b_primeira.pack(anchor="w")
        self.cartao_vazio = c

    def _cartao_empresa(self, e):
        c = Cartao(self.f_cards, pad=16)
        k = c.corpo
        rotulo(k, e["nome"], 13, "bold", largura=px(300)).pack(anchor="w")
        rotulo(k, f"CNPJ {formatar_cnpj(e['cnpj'])}", 10, cor="suave").pack(anchor="w", pady=(1, 8))
        chips = tk.Frame(k, bg=P.superficie)
        chips.pack(anchor="w")
        for chave, nome, tom in (("prestado", "Prestado", "verde"), ("tomado", "Tomado", "vermelho")):
            if e["tipos"].get(chave):
                Chip(chips, nome, tom).pack(side="left", padx=(0, 5))
        if e.get("nfe"):
            Chip(chips, "NF-e", "azul").pack(side="left", padx=(0, 5))
        Chip(chips, ACOES.get(e["acao"], e["acao"]), "neutro").pack(side="left")
        if e.get("nfe"):
            try:
                texto = HistoricoNFe(e).texto_bloqueio()
            except OSError:
                texto = ""
            if texto and not texto.endswith("liberada."):
                Chip(k, "NF-e: consulta bloqueada pela SEFAZ", "amarelo").pack(anchor="w", pady=(6, 0))
        sel = situacao_certificado(e.get("cert_validade"))
        if sel:
            Chip(k, sel[0], sel[1]).pack(anchor="w", pady=(6, 0))
        rotulo(k, self._ultima_consulta(e["id"]), 9, cor="suave").pack(anchor="w", pady=(8, 10))
        bt = tk.Frame(k, bg=P.superficie)
        bt.pack(fill="x")
        Botao(bt, "Buscar notas", lambda i=e["id"]: self._buscar(i), estilo="primario", pady=7).pack(side="left")
        Botao(bt, "Editar", lambda i=e["id"]: self._editar(i), pady=7).pack(side="left", padx=(8, 0))
        Botao(bt, "Excluir", lambda i=e["id"]: self._excluir(i), estilo="perigo", pady=7).pack(side="left", padx=(8, 0))
        self._ligar_cliques(c, e["id"])
        return c

    def _ligar_cliques(self, w, id_):
        if not isinstance(w, Botao):
            w.bind("<Button-1>", lambda ev, i=id_: self._selecionar(i), add="+")
            w.bind("<Double-Button-1>", lambda ev, i=id_: self._buscar(i), add="+")
            for f in w.winfo_children():
                self._ligar_cliques(f, id_)

    def _selecionar(self, id_):
        self.selecionada_id = id_
        self._pintar_selecao()

    def _pintar_selecao(self):
        for id_, c in self._cartoes:
            if id_ == self.selecionada_id:
                c.pintar("hover", "verde")
            else:
                c.pintar("superficie", "borda")

    def _redimensionou(self, e=None):
        if self._cartoes:
            self._layout_cartoes()

    def _layout_cartoes(self):
        largura = max(self.rolagem.tela.winfo_width(), px(400))
        cols = max(1, min(3, largura // px(380)))
        if cols == self._colunas:
            return
        self._colunas = cols
        for c in range(4):
            self.f_cards.columnconfigure(c, weight=1 if c < cols else 0, uniform="cartao" if c < cols else "")
        for i, (_, c) in enumerate(self._cartoes):
            c.grid(row=i // cols, column=i % cols, sticky="nsew", padx=(0, 12 if i % cols < cols - 1 else 0), pady=(0, 12))

    def _enter(self, e=None):
        """Enter abre a busca da empresa selecionada (se o foco não estiver em um campo ou botão)."""
        foco = self.focus_get()
        if self.pagina == "empresas" and self.selecionada_id and not isinstance(foco, (tk.Entry, tk.Text, Botao)):
            self._buscar(self.selecionada_id)

    def _adicionar(self):
        d = DialogoEmpresa(self, self.store)
        self.wait_window(d)
        if d.salvou:
            self.store.salvar()
            self.selecionada_id = d.emp["id"]
            self._ir("empresas")

    def _editar(self, id_=None):
        e = self.store.obter(id_) if id_ else self._selecionada()
        if e:
            d = DialogoEmpresa(self, self.store, e)
            self.wait_window(d)
            if d.salvou:
                self.selecionada_id = d.emp["id"]
                self._atualizar_lista(d.emp["id"])

    def _excluir(self, id_=None):
        e = self.store.obter(id_) if id_ else self._selecionada()
        if e and ui.perguntar(self, f"Excluir \"{e['nome']}\"?", "A senha salva dela também é apagada. Os XMLs já gravados não são apagados.",
                              sim="Excluir", nao="Cancelar", perigo=True):
            self.store.excluir_empresa(e["id"])
            self._atualizar_lista()

    def _buscar(self, id_=None, periodo=None, auto=False):
        e = self.store.obter(id_) if id_ else self._selecionada()
        if e:
            self.selecionada_id = e["id"]
            self.wait_window(DialogoBusca(self, self.store, e, periodo=periodo, auto=auto))
            if self.winfo_exists() and self.pagina == "empresas":
                self._atualizar_lista(e["id"])

    # ------------------------------------------------------------------ página Histórico
    def _pagina_historico(self):
        f = tk.Frame(self.conteudo, bg=P.fundo)
        self.paginas["historico"] = f
        self._cabecalho_pagina(
            f, "Histórico", "As últimas consultas feitas neste computador. Só ficam os totais: as notas não são guardadas.",
            lambda cab: Botao(cab, "Limpar histórico", self._limpar_historico, estilo="perigo"))
        self.rol_hist = Rolavel(f)
        self.rol_hist.pack(fill="both", expand=True, padx=(px(32), px(24)), pady=(0, px(16)))

    def _atualizar_historico(self):
        corpo = self.rol_hist.corpo
        for w in corpo.winfo_children():
            w.destroy()
        hist = self.store.preferencias.get("historico", [])
        if not hist:
            c = Cartao(corpo, pad=24)
            c.pack(fill="x", pady=(px(10), 0))
            rotulo(c.corpo, "Ainda não há consultas", 14, "bold", "verde_escuro").pack(anchor="w")
            rotulo(c.corpo, "Depois de buscar as notas de uma empresa, a consulta aparece aqui e você pode abri-la de novo com um clique.",
                   10, cor="suave", largura=px(620)).pack(anchor="w", pady=(4, 0))
            return
        for h in hist:
            c = Cartao(corpo, pad=12)
            c.pack(fill="x", pady=(0, 8))
            k = c.corpo
            k.columnconfigure(0, weight=1)
            esq = tk.Frame(k, bg=P.superficie)
            esq.grid(row=0, column=0, sticky="w")
            rotulo(esq, h["nome"], 11, "bold").pack(anchor="w")
            rotulo(esq, f"{core.MESES_TELA[h['mes'] - 1]}/{h['ano']}  ·  consultado {quando_humano(h.get('quando'))}", 9, cor="suave").pack(anchor="w")
            tot = tk.Frame(k, bg=P.superficie)
            tot.grid(row=0, column=1, padx=16)
            if h.get("prestado") is not None:
                Chip(tot, "Prestado " + core.formatar_valor(h["prestado"]).replace("R$", "R$ "), "verde").pack(side="left", padx=3)
            if h.get("tomado") is not None:
                Chip(tot, "Tomado " + core.formatar_valor(h["tomado"]).replace("R$", "R$ "), "vermelho").pack(side="left", padx=3)
            Botao(k, "Abrir de novo", lambda x=h: self._abrir_historico(x), estilo="suave", pady=7).grid(row=0, column=2)

    def _abrir_historico(self, h):
        e = next((x for x in self.store.empresas if x["id"] == h["empresa_id"]), None)
        if not e:
            ui.avisar(self, "Empresa não encontrada", "Esta empresa foi excluída. Cadastre-a de novo para consultar.")
            return
        self._buscar(e["id"], periodo=(h["ano"], h["mes"]), auto=True)
        if self.winfo_exists() and self.pagina == "historico":
            self._atualizar_historico()

    def _limpar_historico(self):
        if self.store.preferencias.get("historico") and ui.perguntar(
                self, "Limpar o histórico?", "Somente a lista de consultas é apagada. Empresas e XMLs não são afetados.",
                sim="Limpar", nao="Cancelar", perigo=True):
            self.store.preferencias["historico"] = []
            self.store.salvar()
            self._atualizar_historico()

    # ------------------------------------------------------------------ página Configurações
    def _bloco(self, pai, titulo):
        rotulo(pai, titulo, 12, "bold", "verde_escuro").pack(anchor="w", pady=(0, 6))
        c = Cartao(pai, pad=16)
        c.pack(fill="x", pady=(0, 16))
        return c.corpo

    def _pagina_config(self):
        f = tk.Frame(self.conteudo, bg=P.fundo)
        self.paginas["config"] = f
        self._cabecalho_pagina(f, "Configurações", "Segurança, pastas, atualizações e aparência do programa.")
        rol = Rolavel(f)
        rol.pack(fill="both", expand=True, padx=(px(32), px(24)), pady=(0, px(16)))
        aba = rol.corpo

        k = self._bloco(aba, "Aparência")
        self.v_escuro = tk.BooleanVar(value=P.nome == "escuro")
        Interruptor(k, "Modo escuro", self.v_escuro, self._alternar_tema).pack(anchor="w")

        k = self._bloco(aba, "Segurança das senhas")
        self.l_seg = rotulo(k, "", 10, cor="suave", largura=px(700))
        self.l_seg.pack(anchor="w")
        self.f_seg = tk.Frame(k, bg=P.superficie)
        self.f_seg.pack(anchor="w", pady=(10, 0))
        self.b_mestra = Botao(self.f_seg, "Definir senha mestra...", self._alternar_mestra)
        self.b_mestra.pack(side="left")
        self._atualizar_seguranca()

        k = self._bloco(aba, "Pastas")
        lin = tk.Frame(k, bg=P.superficie)
        lin.pack(anchor="w", fill="x")
        rotulo(lin, "Pasta padrão para escolher destinos", 9, "bold", "suave").pack(anchor="w", pady=(0, 3))
        self.v_raiz = tk.StringVar(value=self.store.preferencias.get("raiz_padrao", ""))
        l2 = tk.Frame(lin, bg=P.superficie)
        l2.pack(anchor="w", fill="x")
        ui.Campo(l2, self.v_raiz, largura=44).pack(side="left", fill="x", expand=True)
        Botao(l2, "Procurar...", self._escolher_raiz).pack(side="left", padx=(8, 0))
        Botao(k, "Abrir a pasta dos dados do app", lambda: ui.abrir_pasta(self.store.pasta)).pack(anchor="w", pady=(10, 0))

        k = self._bloco(aba, "Atualizações")
        self.v_att = tk.BooleanVar(value=self.store.preferencias.get("verificar_atualizacao", True))
        Interruptor(k, "Avisar quando houver versão nova (consulta só a página de versões do projeto no GitHub)",
                    self.v_att, self._salvar_att).pack(anchor="w")
        lin2 = tk.Frame(k, bg=P.superficie)
        lin2.pack(anchor="w", pady=(10, 0))
        Botao(lin2, "Verificar agora", lambda: self._checar_atualizacao(manual=True)).pack(side="left")
        self.l_att = rotulo(lin2, "", 10, cor="suave")
        self.l_att.pack(side="left", padx=12)

        k = self._bloco(aba, "Dados salvos")
        rotulo(k, "Desinstalar o programa não apaga as empresas, os certificados e as senhas salvos neste computador. "
                  "Se quiser removê-los (por exemplo, em um computador compartilhado), use o botão abaixo antes de desinstalar.",
               10, cor="suave", largura=px(700)).pack(anchor="w")
        Botao(k, "Apagar todos os meus dados salvos...", self._apagar_dados, estilo="perigo").pack(anchor="w", pady=(10, 0))

    def _alternar_tema(self):
        self.store.preferencias["tema"] = "escuro" if self.v_escuro.get() else "claro"
        try:
            self.store.salvar()
        except OSError:
            pass
        ui.definir_tema(self.store.preferencias["tema"])
        self.after(50, self._montar)

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
                if ui.perguntar(self, "Voltar ao Cofre do Windows?", "As senhas passam a ser protegidas só pelo Cofre do Windows, sem senha mestra."):
                    self.store.trocar_modo(None)
            else:
                nova = ui.pedir_texto(self, "Definir senha mestra", "Escolha uma senha mestra (mínimo 6 caracteres).\n"
                                      "Se você esquecer, será preciso cadastrar as senhas dos certificados de novo.", oculto=True,
                                      validar=lambda t: None if len(t) >= 6 else "Use pelo menos 6 caracteres.")
                if not nova:
                    return
                conf = ui.pedir_texto(self, "Confirmar senha mestra", "Digite a senha mestra de novo:", oculto=True,
                                      validar=lambda t: None if t == nova else "As senhas não são iguais.")
                if conf is None:
                    return
                self.store.trocar_modo(nova)
        except ErroAdge as e:
            ui.erro(self, "Não foi possível mudar a proteção", str(e))
        self._atualizar_seguranca()

    def _apagar_dados(self):
        n = len(self.store.empresas)
        if not ui.perguntar(
                self, "Apagar todos os dados salvos?",
                f"Isso apaga PARA SEMPRE, só neste computador: as {n} empresa(s) salva(s), as senhas dos certificados, "
                "a chave de proteção no Cofre do Windows e as preferências do app.\n\n"
                "Os certificados (.pfx) e os XMLs já baixados NÃO são apagados.", sim="Continuar", nao="Cancelar", perigo=True):
            return
        if not ui.perguntar(self, "Confirma apagar tudo?", "Esta ação não pode ser desfeita.", sim="Apagar tudo", nao="Cancelar", perigo=True):
            return
        try:
            self.store.apagar_tudo()
        except ErroAdge as e:
            ui.erro(self, "Não consegui apagar os dados", str(e))
            return
        ui.informar(self, "Dados apagados", "O programa será fechado.")
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

    # ------------------------------------------------------------------ página Sobre
    def _pagina_sobre(self):
        f = tk.Frame(self.conteudo, bg=P.fundo)
        self.paginas["sobre"] = f
        self._cabecalho_pagina(f, "Sobre", f"{NOME_APP}  ·  versão {VERSAO}")
        rol = Rolavel(f)
        rol.pack(fill="both", expand=True, padx=(px(32), px(24)), pady=(0, px(16)))
        aba = rol.corpo
        c = Cartao(aba, fundo="verde_claro", borda="verde_claro", pad=20)
        c.pack(fill="x", pady=(0, 16))
        for i, (t, txt) in enumerate(TEXTOS_MISSAO):
            rotulo(c.corpo, t, 11, "bold", "verde_escuro").pack(anchor="w", pady=(0 if i == 0 else 12, 2))
            rotulo(c.corpo, txt, 10, cor="verde_escuro", largura=px(680)).pack(anchor="w")
        rotulo(aba, "Quer ajudar?", 12, "bold", "verde_escuro").pack(anchor="w", pady=(0, 4))
        rotulo(aba, "Se o programa te ajudou, deixe uma avaliação no GitHub ou no perfil da Adge no Google. É a melhor forma de "
                    "contribuir, e não custa nada.", 10, cor="suave", largura=px(680)).pack(anchor="w")
        lk = tk.Frame(aba, bg=P.fundo)
        lk.pack(anchor="w", pady=(10, 16))
        if URL_GITHUB:
            self.b_github = Botao(lk, "Avaliar no GitHub", lambda: ui.abrir_link(URL_GITHUB))
            self.b_github.pack(side="left", padx=(0, 8))
        self.b_google = Botao(lk, "Avaliar no Google", lambda: ui.abrir_link(URL_GOOGLE_ADGE))
        self.b_google.pack(side="left", padx=(0, 8))
        self.b_site = Botao(lk, "Conhecer a Adge", lambda: ui.abrir_link(SITE_ADGE), estilo="suave")
        self.b_site.pack(side="left", padx=(0, 8))
        self.b_apresentacao = Botao(lk, "Ver a apresentação do projeto", lambda: DialogoBoasVindas(self, self.store), estilo="fantasma")
        self.b_apresentacao.pack(side="left")
        rotulo(aba, "Como funciona", 12, "bold", "verde_escuro").pack(anchor="w", pady=(0, 4))
        rotulo(aba, "O programa roda só neste computador: não há servidor nem conta. O certificado A1 é usado apenas para conversar com "
                    "o ADN oficial da NFS-e Nacional (adn.nfse.gov.br). Nunca compartilhe o arquivo do certificado nem a senha.",
               10, cor="suave", largura=px(680)).pack(anchor="w")

    # ------------------------------------------------------------------ validade dos certificados (em segundo plano, 1x por dia)
    def _atualizar_validades(self):
        """Lê a validade de cada certificado salvo e guarda no cadastro. Só as senhas já lembradas são usadas."""
        if not self.winfo_exists():
            return
        hoje = dt.date.today().isoformat()
        tarefas = []
        for e in self.store.empresas:
            if e.get("cert_checado") == hoje or not e.get("senha_cifrada") or not Path(e.get("pfx") or "").is_file():
                continue
            try:
                tarefas.append((e["id"], e["pfx"], self.store.senha_da_empresa(e)))
            except ErroAdge:
                continue
        if not tarefas:
            return

        def trabalho():
            for id_, pfx, senha in tarefas:
                try:
                    info = core.ler_certificado(pfx, senha)
                    self.fila_cert.put((id_, info["valido_ate"].isoformat()))
                except Exception:
                    continue
        threading.Thread(target=trabalho, daemon=True).start()
        self.after(800, self._ler_fila_cert)

    def _ler_fila_cert(self, tentativas=0):
        mudou = False
        try:
            while True:
                id_, venc = self.fila_cert.get_nowait()
                e = next((x for x in self.store.empresas if x["id"] == id_), None)
                if e:
                    e["cert_validade"], e["cert_checado"] = venc, dt.date.today().isoformat()
                    mudou = True
        except queue.Empty:
            pass
        if mudou:
            try:
                self.store.salvar()
            except OSError:
                pass
            if self.pagina == "empresas":
                self._atualizar_lista(self.selecionada_id)
        if self.winfo_exists() and tentativas < 20:
            self.after(800, lambda: self._ler_fila_cert(tentativas + 1))

    # ------------------------------------------------------------------ atualização do programa
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

    def _mostrar_faixa(self):
        self.l_faixa.config(text=f"Versão {self.info_att['tag']} disponível. Clique para atualizar.")
        self.faixa.pack(fill="x", before=self.conteudo)

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
                    self._mostrar_faixa()
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
