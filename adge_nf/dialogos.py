"""Janelas do programa: cadastro de empresa, aviso de atualização e boas-vindas."""
import datetime as dt
import os
import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from . import NOME_APP, SITE_ADGE, URL_GITHUB, URL_GOOGLE_ADGE, VERSAO, atualizacao, core
from . import ui
from .core import Cancelado, ErroAdge
from .nfe_ui import DialogoAtivarCiencia, DialogoAtivarNFe
from .store import Armazenamento, empresa_padrao
from .ui import P, Botao, Campo, Cartao, Chip, Interruptor, Modal, Segmentado, F, px, rotulo

formatar_cnpj = ui.formatar_cnpj


# ============================================================================= cadastro da empresa
class DialogoEmpresa(Modal):
    def __init__(self, pai, store: Armazenamento, emp: dict = None):
        super().__init__(pai, "Editar empresa" if emp else "Nova empresa")
        self.store = store
        self.novo = emp is None
        self.emp = dict(emp) if emp else empresa_padrao()
        self.salvou = False
        self._validade = None
        self._pfx_original = self.emp.get("pfx", "")
        e = self.emp
        v = lambda x: tk.StringVar(value=x)
        self.v_nome, self.v_cnpj, self.v_pfx = v(e["nome"]), v(formatar_cnpj(e["cnpj"])), v(e["pfx"])
        self.v_senha, self.v_destino = v(""), v(e["destino"])
        self.v_estrutura = v(e["estrutura"])
        self.v_prest = tk.BooleanVar(value=e["tipos"].get("prestado", True))
        self.v_tom = tk.BooleanVar(value=e["tipos"].get("tomado", True))
        self.v_nfe = tk.BooleanVar(value=bool(e.get("nfe")))
        self.v_ciencia = tk.BooleanVar(value=bool(e.get("nfe_ciencia")) and bool(e.get("nfe")))
        self.v_acao = v(e["acao"])
        self.v_rel, self.v_csv = tk.BooleanVar(value=e["relatorio"]), tk.BooleanVar(value=e.get("planilha", e.get("csv", False)))
        self.v_lembrar = tk.BooleanVar(value=bool(e["senha_cifrada"]) or self.novo)
        self.v_pref_prest, self.v_pref_tom = v(e["prefixo_prestado"]), v(e["prefixo_tomado"])
        self.v_ver = tk.BooleanVar(value=False)
        self.v_aba = v("empresa")
        self._montar()
        self.bind("<Escape>", lambda *_: self.destroy())
        self.mostrar()

    def _montar(self):
        ui.titulo(self, "Editar empresa" if not self.novo else "Nova empresa",
                  "O certificado e a senha ficam guardados só neste computador.").pack(anchor="w", pady=(0, 12))
        self.seg = Segmentado(self, [("empresa", "Empresa e certificado"), ("destino", "Onde salvar os XMLs")],
                              self.v_aba, self._trocar_aba)
        self.seg.pack(anchor="w", pady=(0, 12))
        self.area = tk.Frame(self, bg=P.fundo)
        self.area.pack(fill="both", expand=True)
        self.f_empresa = self._aba_empresa(self.area)
        self.f_destino = self._aba_destino(self.area)
        self.f_empresa.pack(fill="both", expand=True)

        self.l_erro = rotulo(self, "", 10, cor="erro", largura=px(700))
        self.l_erro.pack(anchor="w", pady=(10, 0))
        b = tk.Frame(self, bg=P.fundo)
        b.pack(fill="x", pady=(8, 0))
        Botao(b, "Cancelar", self.destroy).pack(side="right")
        self.b_salvar = Botao(b, "Salvar empresa", self._salvar, estilo="primario")
        self.b_salvar.pack(side="right", padx=(0, 8))
        self._atualizar()

    def _trocar_aba(self):
        mostrar, esconder = (self.f_empresa, self.f_destino) if self.v_aba.get() == "empresa" else (self.f_destino, self.f_empresa)
        esconder.pack_forget()
        mostrar.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ aba 1
    def _aba_empresa(self, pai):
        f = tk.Frame(pai, bg=P.fundo)
        f.columnconfigure(0, weight=3, uniform="e")
        f.columnconfigure(1, weight=2, uniform="e")
        esq = Cartao(f)
        esq.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        dir_ = Cartao(f)
        dir_.grid(row=0, column=1, sticky="nsew")
        c = esq.corpo
        c.columnconfigure(0, weight=1)

        def campo_linha(r, texto, widget_fn):
            cx = tk.Frame(c, bg=P.superficie)
            cx.grid(row=r, column=0, sticky="ew", pady=(0, 10))
            cx.columnconfigure(0, weight=1)
            rotulo(cx, texto, 9, "bold", "suave").grid(row=0, column=0, sticky="w", pady=(0, 3), columnspan=2)
            widget_fn(cx)
            return cx

        campo_linha(0, "Nome da empresa", lambda cx: Campo(cx, self.v_nome, largura=30).grid(row=1, column=0, sticky="ew"))

        def pfx(cx):
            Campo(cx, self.v_pfx, largura=22).grid(row=1, column=0, sticky="ew")
            Botao(cx, "Procurar...", self._procurar_pfx).grid(row=1, column=1, padx=(8, 0))
        campo_linha(1, "Certificado A1 (.pfx/.p12)", pfx)

        def senha(cx):
            self.campo_senha = Campo(cx, self.v_senha, largura=22, mostrar="●")
            self.campo_senha.grid(row=1, column=0, sticky="ew")
            Interruptor(cx, "Mostrar", self.v_ver, lambda: self.campo_senha.configure(
                show="" if self.v_ver.get() else "●")).grid(row=1, column=1, padx=(10, 0))
            if not self.novo and self.emp["senha_cifrada"]:
                rotulo(cx, "Já há uma senha salva. Deixe em branco para mantê-la.", 9, cor="suave").grid(
                    row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        campo_linha(2, "Senha do certificado", senha)

        Interruptor(c, "Lembrar a senha neste computador (fica cifrada)", self.v_lembrar, tam=9).grid(
            row=3, column=0, sticky="w", pady=(0, 10))
        lin = tk.Frame(c, bg=P.superficie)
        lin.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        Botao(lin, "Validar certificado", self._validar, estilo="suave").pack(side="left")
        self.l_cert = rotulo(lin, "", 9, cor="suave", largura=px(260))
        self.l_cert.pack(side="left", padx=10)
        campo_linha(5, "CNPJ", lambda cx: Campo(cx, self.v_cnpj, largura=22).grid(row=1, column=0, sticky="w"))

        d = dir_.corpo
        rotulo(d, "O que baixar", 11, "bold", "verde_escuro").pack(anchor="w", pady=(0, 6))
        Interruptor(d, "Serviço prestado (NFS-e emitidas)", self.v_prest).pack(anchor="w", pady=3)
        Interruptor(d, "Serviço tomado (NFS-e recebidas)", self.v_tom).pack(anchor="w", pady=3)
        Interruptor(d, "NF-e de compra e venda (modelo 55)", self.v_nfe, self._ligar_nfe).pack(anchor="w", pady=3)
        Interruptor(d, "Registrar a Ciência da Operação automaticamente", self.v_ciencia, self._ligar_ciencia, tam=9).pack(
            anchor="w", pady=(0, 3), padx=(px(26), 0))
        ui.divisor(d, (12, 12))
        rotulo(d, "O que fazer", 11, "bold", "verde_escuro").pack(anchor="w", pady=(0, 6))
        for valor, txt in (("ambos", "Calcular o total e baixar os XMLs"), ("calcular", "Só calcular o total do período"),
                           ("baixar", "Só baixar os XMLs")):
            ui.radio(d, txt, valor, self.v_acao, self._atualizar).pack(anchor="w", pady=2)
        return f

    # ------------------------------------------------------------------ NF-e (começa desligada; ligar abre um aviso)
    def _ligar_nfe(self):
        if self.v_nfe.get():
            d = DialogoAtivarNFe(self)
            self.wait_window(d)
            if not d.resultado:
                self.v_nfe.set(False)
            self.grab_set()
        else:
            self.v_ciencia.set(False)

    def _ligar_ciencia(self):
        if not self.v_ciencia.get():
            return
        if not self.v_nfe.get():
            ui.avisar(self, "Ative a busca de NF-e primeiro", "A ciência da operação só vale para empresas com a busca de NF-e ligada.")
            self.v_ciencia.set(False)
            self.grab_set()
            return
        d = DialogoAtivarCiencia(self)
        self.wait_window(d)
        if not d.resultado:
            self.v_ciencia.set(False)
        self.grab_set()

    # ------------------------------------------------------------------ aba 2
    def _aba_destino(self, pai):
        f = tk.Frame(pai, bg=P.fundo)
        cartao = Cartao(f)
        cartao.pack(fill="x")
        c = cartao.corpo
        c.columnconfigure(0, weight=1)
        rotulo(c, "Pasta", 9, "bold", "suave").grid(row=0, column=0, sticky="w", pady=(0, 3))
        Campo(c, self.v_destino, largura=40).grid(row=1, column=0, sticky="ew")
        Botao(c, "Procurar...", self._procurar_destino).grid(row=1, column=1, padx=(8, 0))
        rotulo(c, "Organização das pastas", 9, "bold", "suave").grid(row=2, column=0, sticky="w", pady=(12, 3))
        self.cb_est = ttk.Combobox(c, state="readonly", values=list(core.ESTRUTURAS.values()), font=F(10))
        self.cb_est.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.cb_est.current(list(core.ESTRUTURAS).index(self.v_estrutura.get()))
        o = tk.Frame(c, bg=P.superficie)
        o.grid(row=4, column=0, columnspan=2, sticky="w", pady=(14, 0))
        Interruptor(o, "Criar o relatório de organização (.txt)", self.v_rel).pack(anchor="w", pady=3)
        Interruptor(o, "Criar planilha Excel com resumo e abas (.xlsx)", self.v_csv).pack(anchor="w", pady=3)
        rotulo(c, "Início do nome dos arquivos", 11, "bold", "verde_escuro").grid(row=5, column=0, columnspan=2, sticky="w", pady=(16, 4))
        av = tk.Frame(c, bg=P.superficie)
        av.grid(row=6, column=0, columnspan=2, sticky="ew")
        av.columnconfigure(1, weight=1)
        rotulo(av, "Prestado", 9, "bold", "suave").grid(row=0, column=0, sticky="w", padx=(0, 12))
        Campo(av, self.v_pref_prest, largura=30).grid(row=0, column=1, sticky="ew", pady=(0, 6))
        rotulo(av, "Tomado", 9, "bold", "suave").grid(row=1, column=0, sticky="w", padx=(0, 12))
        Campo(av, self.v_pref_tom, largura=30).grid(row=1, column=1, sticky="ew")
        rotulo(c, 'Em branco usa "NOTA FISCAL DE SERVIÇO PRESTADO" / "TOMADO". Exemplo: "NOTA FISCAL DE SERVIÇO PRESTADO DE ALUGUEL".',
               9, cor="suave", largura=px(620)).grid(row=7, column=0, columnspan=2, sticky="w", pady=(6, 0))
        return f

    # ------------------------------------------------------------------ ações
    def _atualizar(self):
        sem_destino = self.v_acao.get() == "calcular"
        self.seg.desabilitar("destino", sem_destino)
        if sem_destino and self.v_aba.get() == "destino":
            self.v_aba.set("empresa")
            self._trocar_aba()

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

    def _msg_cert(self, texto, cor="suave"):
        self.l_cert.config(text=texto, fg=P.__dict__.get(cor, cor))

    def _validar(self, silencioso=False):
        pfx, senha = self.v_pfx.get().strip(), self.v_senha.get()
        if not senha and not self.novo and self.emp["senha_cifrada"]:
            try:
                senha = self.store.senha_da_empresa(self.emp)
            except ErroAdge:
                senha = ""
        if not pfx or not senha:
            self._msg_cert("Escolha o arquivo e digite a senha.", "erro")
            return None
        try:
            info = core.ler_certificado(pfx, senha)
        except ErroAdge as e:
            self._msg_cert(str(e), "erro")
            return None
        hoje = dt.date.today()
        venc = info["valido_ate"]
        self._validade = venc
        if venc < hoje:
            self._msg_cert(f"Certificado VENCIDO em {venc:%d/%m/%Y}.", "erro")
        else:
            self._msg_cert(f"Certificado válido até {venc:%d/%m/%Y}.", "verde_escuro")
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
        problema, aba = None, "empresa"
        if not nome:
            problema = "Dê um nome para a empresa."
        elif not pfx or not Path(pfx).is_file():
            problema = "Escolha o arquivo do certificado (.pfx ou .p12)."
        elif len(cnpj) != 14:
            problema = "O CNPJ precisa ter 14 dígitos. Use \"Validar certificado\" para preencher sozinho."
        elif not (self.v_prest.get() or self.v_tom.get() or self.v_nfe.get()):
            problema = "Marque pelo menos um tipo de nota."
        elif acao != "calcular" and (not self.v_destino.get().strip() or not Path(self.v_destino.get().strip()).is_dir()):
            problema, aba = "Escolha a pasta onde os XMLs serão salvos.", "destino"
        elif self.novo and not self.v_senha.get():
            problema = "Digite a senha do certificado."
        if problema:
            self.l_erro.config(text=problema)
            if self.v_aba.get() != aba:
                self.v_aba.set(aba)
                self._trocar_aba()
            return
        senha_nova = self.v_senha.get()
        if senha_nova:
            try:
                info = core.ler_certificado(pfx, senha_nova)
                self._validade = info["valido_ate"]
            except ErroAdge as ex:
                self.l_erro.config(text=str(ex))
                return
        e.update({"nome": nome, "cnpj": cnpj, "pfx": pfx, "destino": self.v_destino.get().strip(),
                  "estrutura": estrutura, "tipos": {"prestado": self.v_prest.get(), "tomado": self.v_tom.get()},
                  "nfe": self.v_nfe.get(), "nfe_ciencia": self.v_ciencia.get() and self.v_nfe.get(), "acao": acao, "relatorio": self.v_rel.get(), "planilha": self.v_csv.get(),
                  "prefixo_prestado": self.v_pref_prest.get().strip(), "prefixo_tomado": self.v_pref_tom.get().strip()})
        if self._validade:
            e["cert_validade"] = self._validade.isoformat()
        elif pfx != self._pfx_original:
            e.pop("cert_validade", None)
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
        ui.titulo(self, "Nova versão disponível", f"{self.info['tag']}  (você está na v{VERSAO})").pack(anchor="w")
        cab = tk.Frame(self, bg=P.fundo)
        cab.pack(fill="x", pady=(12, 4))
        ui.secao(cab, "Novidades").pack(side="left")
        if self.info.get("relatorio_url"):
            lk = rotulo(cab, "Ver relatório completo no GitHub", 9, cor="verde_escuro", cursor="hand2")
            lk.config(font=F(9) + ("underline",))
            lk.pack(side="right")
            lk.bind("<Button-1>", lambda *_: ui.abrir_link(self.info["relatorio_url"]))
            self.l_relatorio = lk
        cartao = Cartao(self, pad=6)
        cartao.pack(fill="both", expand=True)
        caixa = cartao.corpo
        self.txt = tk.Text(caixa, width=76, height=14, wrap="word", bg=P.superficie, fg=P.texto, relief="flat", bd=0,
                           highlightthickness=0, font=F(10), padx=10, pady=8, insertbackground=P.texto)
        sb = ttk.Scrollbar(caixa, orient="vertical", command=self.txt.yview, style="Adge.Vertical.TScrollbar")
        self.txt.configure(yscrollcommand=sb.set)
        self.txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self._preencher_novidades()
        self.txt.config(state="disabled")
        self.l_status = rotulo(self, "", 10, cor="suave", largura=px(560))
        self.l_status.pack(anchor="w", pady=(10, 0))
        self.barra = ui.Barra(self)
        linha = tk.Frame(self, bg=P.fundo)
        linha.pack(fill="x", pady=(12, 0))
        self.f_botoes = linha
        msi = self.info.get("msi")
        if self.pode_instalar and msi and msi.get("sha256"):
            self.b_ok = Botao(linha, "Atualizar agora", self._atualizar, estilo="primario")
            aviso = "O Windows vai pedir permissão de administrador. Suas empresas e senhas salvas são mantidas."
        else:
            self.b_ok = Botao(linha, "Abrir a página de download", self._abrir_pagina, estilo="primario")
            aviso = ("Esta cópia do programa não pode se atualizar sozinha. Baixe o instalador na página."
                     if not self.pode_instalar else "Esta versão não tem verificação de integridade; baixe pela página.")
        self.l_status.config(text=aviso)
        self.b_ok.pack(side="left")
        self.b_depois = Botao(linha, "Lembrar depois", self._depois)
        self.b_depois.pack(side="left", padx=(8, 0))
        self.b_pular = Botao(linha, "Pular esta versão", self._pular, estilo="fantasma")
        self.b_pular.pack(side="right")

    def _preencher_novidades(self):
        """Mostra cada versão nova com seus itens no formato "Nome (ITEM-NN)"; sem resumo em itens, mostra o texto da Release."""
        t = self.txt
        t.tag_configure("versao", font=F(11, "bold"), foreground=P.verde_escuro, spacing1=8, spacing3=2)
        t.tag_configure("item", font=F(10, "bold"))
        t.tag_configure("codigo", foreground=P.suave, font=F(9))
        t.tag_configure("texto", lmargin1=16, lmargin2=16, spacing3=4)
        cores = {"NOVO": P.pos_texto, "MELHORIA": P.azul, "CORRECAO": P.neg_texto}
        for k, c in cores.items():
            t.tag_configure("t_" + k, foreground=c, font=F(9, "bold"))
        versoes = self.info.get("versoes") or []
        if not versoes:
            t.insert("1.0", self.info.get("notas") or "Esta versão não traz descrição das novidades.")
            return
        for i, v in enumerate(versoes):
            t.insert("end", ("\n" if i else "") + f"Versão {v['tag'].lstrip('v')}\n", "versao")
            for it in v["itens"]:
                t.insert("end", "• ", "item")
                t.insert("end", atualizacao.TIPOS[it["tipo"]].upper() + "  ", "t_" + it["tipo"])
                t.insert("end", it["nome"], "item")
                t.insert("end", f" ({it['codigo']})\n", "codigo")
                t.insert("end", it["texto"] + "\n", "texto")

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
        ui.abrir_link(self.info["url"])
        self._fechar()

    def _atualizar(self):
        self.baixando = True
        self.cancelar_flag = False
        for b in (self.b_ok, self.b_depois, self.b_pular):
            b.config(state="disabled")
        self.b_cancelar = Botao(self.f_botoes, "Cancelar download", lambda: setattr(self, "cancelar_flag", True))
        self.b_cancelar.pack(side="left", padx=(8, 0))
        self.barra.pack(fill="x", pady=(8, 0), before=self.f_botoes)
        self.barra.iniciar()
        self.l_status.config(text="Baixando a atualização...", fg=P.suave)

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
        self.barra.parar()
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
                        self.barra.definir(feito / total)
                        self.l_status.config(text=f"Baixando a atualização... {feito / 1048576:.1f} de {total / 1048576:.1f} MB")
                elif tipo == "ok":
                    self.l_status.config(text="Download conferido. Iniciando a instalação...")
                    self.update_idletasks()
                    try:
                        self.ao_instalar(dado)
                    except ErroAdge as e:
                        self._fim_download()
                        self.l_status.config(text=str(e), fg=P.erro)
                    return
                elif tipo == "erro":
                    self._fim_download()
                    self.l_status.config(text=dado, fg=P.erro)
                elif tipo == "cancelado":
                    self._fim_download()
                    self.l_status.config(text="Download cancelado.", fg=P.suave)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._ler_fila)

    def _fechar(self):
        if self.baixando:
            self.cancelar_flag = True
        self.destroy()


# ============================================================================= boas-vindas
PREF_BOAS_VINDAS = "boas_vindas_vista"


def boas_vindas_pendente(prefs: dict) -> bool:
    """O cartão de boas-vindas aparece uma única vez (depois, só pelo botão em Sobre)."""
    return not prefs.get(PREF_BOAS_VINDAS)


TEXTOS_MISSAO = (
    ("Para quem é",
     "Contadores e auxiliares de contabilidade que baixam, conferem e organizam notas fiscais todo mês e não "
     "deveriam precisar colocar a mão no bolso toda vez que precisam de uma função básica."),
    ("Por que existe",
     "Este programa é uma iniciativa sem fins lucrativos da Adge. A ideia é resolver, de forma gratuita, "
     "problemas do dia a dia de pequenas empresas e de quem cuida da contabilidade delas."),
    ("Seus dados ficam com você",
     "Tudo roda só neste computador. Não há conta, servidor nem coleta de dados."),
)


class DialogoBoasVindas(Modal):
    """Cartão da primeira abertura: o que é o projeto, para quem é e como contribuir."""

    TEXTOS = TEXTOS_MISSAO

    def __init__(self, pai, store: Armazenamento, ao_adicionar=None):
        super().__init__(pai, "Bem-vindo")
        self.store, self.ao_adicionar = store, ao_adicionar
        self._montar()
        self.protocol("WM_DELETE_WINDOW", self._fechar)
        self.bind("<Escape>", lambda *_: self._fechar())
        self.mostrar()

    def _montar(self):
        ui.titulo(self, "Bem-vindo ao Adge Group - NF Downloader",
                  "Uma iniciativa sem fins lucrativos para quem faz contabilidade").pack(anchor="w", pady=(0, 12))
        cartao = Cartao(self, fundo="verde_claro", borda="verde_claro", pad=18)
        cartao.pack(fill="x")
        for i, (titulo, texto) in enumerate(self.TEXTOS):
            rotulo(cartao.corpo, titulo, 11, "bold", "verde_escuro").pack(anchor="w", pady=(0 if i == 0 else 12, 2))
            rotulo(cartao.corpo, texto, 10, cor="verde_escuro", largura=px(500)).pack(anchor="w")
        rotulo(self, "Quer ajudar?", 12, "bold", "verde_escuro").pack(anchor="w", pady=(18, 2))
        rotulo(self, "Se o programa te ajudou, deixe uma avaliação no GitHub ou no perfil da Adge no Google. "
                     "É a melhor forma de contribuir, e não custa nada.", 10, cor="suave", largura=px(540)).pack(anchor="w")
        links = tk.Frame(self, bg=P.fundo)
        links.pack(fill="x", pady=(12, 0))
        self.b_github = Botao(links, "Avaliar no GitHub", lambda: ui.abrir_link(URL_GITHUB))
        self.b_github.pack(side="left")
        self.b_google = Botao(links, "Avaliar no Google", lambda: ui.abrir_link(URL_GOOGLE_ADGE))
        self.b_google.pack(side="left", padx=(8, 0))
        self.b_site = Botao(links, "Conhecer a Adge", lambda: ui.abrir_link(SITE_ADGE))
        self.b_site.pack(side="left", padx=(8, 0))
        if not URL_GITHUB:
            self.b_github.pack_forget()
        fim = tk.Frame(self, bg=P.fundo)
        fim.pack(fill="x", pady=(20, 0))
        self.b_ok = Botao(fim, "Começar", self._fechar, estilo="primario")
        self.b_ok.pack(side="right")
        self.b_primeira = None
        if self.ao_adicionar and not self.store.empresas:
            self.b_primeira = Botao(fim, "Adicionar minha primeira empresa", self._adicionar, estilo="suave")
            self.b_primeira.pack(side="right", padx=(0, 8))

    def _marcar(self):
        self.store.preferencias[PREF_BOAS_VINDAS] = True
        try:
            self.store.salvar()
        except OSError:
            pass

    def _fechar(self):
        self._marcar()
        self.destroy()

    def _adicionar(self):
        self._marcar()
        self.destroy()
        self.ao_adicionar()
