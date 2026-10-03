"""Página "Responsável" (v1.7.6): cadastro de quem recebe, por autXML, as NF-e de venda das empresas (por exemplo o contador),
com o certificado A1 dessa pessoa (e-CPF) ou da empresa dele (e-CNPJ). Tudo fica só neste computador."""
import datetime as dt
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from . import core, nfe, nfe_resp
from . import ui
from .core import Cancelado, ErroAdge
from .nfe_cache import HistoricoNFe, formatar_espera
from .ui import P, Botao, Campo, Cartao, Chip, Interruptor, Rolavel, Segmentado, px, rotulo

LARG = 700        # largura do texto dentro dos cartões (cabe na janela mínima sem cortar)


def texto_dados_locais(pasta) -> str:
    return (f"O cadastro do responsável, o caminho do certificado e a senha (cifrada) ficam salvos SÓ neste computador, na pasta de dados do "
            f"programa ({pasta}). Nada disso é enviado a nenhum servidor da Adge: a consulta vai direto deste computador para a SEFAZ. "
            "O arquivo do certificado (.pfx) continua onde você o guardou; o programa só guarda o caminho dele. "
            "Desinstalar o programa NÃO apaga esses dados, nem as empresas e senhas salvas. Para removê-los, use \"Remover responsável\" "
            "aqui ou \"Apagar todos os meus dados salvos\" em Configurações, antes de desinstalar.")


CIENTES = (
    "Ciente: só chegam notas em que o emitente incluiu o CPF/CNPJ do responsável no autXML",
    "Ciente: o dono do certificado autorizou o uso e o cliente autorizou o acesso às notas (LGPD)",
    "Ciente: tudo fica salvo só neste computador, não vai a servidor da Adge e não some ao desinstalar",
)


class PaginaResponsavel(tk.Frame):
    def __init__(self, pai, app, store, base_historico=None, sessao_nfe=None):
        super().__init__(pai, bg=P.fundo)
        self.app, self.store = app, store
        self.base_historico, self.sessao_teste = base_historico, sessao_nfe     # os testes injetam uma SEFAZ falsa
        self.fila: "queue.Queue" = queue.Queue()
        self.trabalhando = False
        self.editando = False
        self.v_ciente = [tk.BooleanVar(value=False) for _ in CIENTES]
        self.v_tipo = tk.StringVar(value="cpf")
        self.v_doc, self.v_nome, self.v_pfx, self.v_senha = (tk.StringVar() for _ in range(4))
        self.v_ver, self.v_lembrar = tk.BooleanVar(value=False), tk.BooleanVar(value=True)
        self._validade = None
        app._cabecalho_pagina(self, "Responsável",
                              "Para puxar as NF-e de venda (ou qualquer nota que cite o CPF/CNPJ do responsável).")
        self.rol = Rolavel(self)
        self.rol.pack(fill="both", expand=True, padx=(px(32), px(24)), pady=(0, px(16)))
        self.corpo = self.rol.corpo
        self.after(200, self._ler_fila)
        self.atualizar()

    # ------------------------------------------------------------------ montagem
    def _bloco(self, titulo, linhas, tom=None, cor_titulo=None):
        rotulo(self.corpo, titulo, 12, "bold", "verde_escuro").pack(anchor="w", pady=(0, 6))
        c = Cartao(self.corpo, fundo=tom, borda=tom, pad=16) if tom else Cartao(self.corpo, pad=16)
        c.pack(fill="x", pady=(0, 16))
        cor = {"verde_claro": "verde_escuro", "aviso_fundo": "aviso_texto"}.get(tom, "suave")
        for l in linhas:
            rotulo(c.corpo, l, 10, cor=cor, largura=px(LARG)).pack(anchor="w", pady=(0, 6))
        return c.corpo

    def atualizar(self):
        for w in self.corpo.winfo_children():
            w.destroy()
        self._explicacao()
        if self.store.responsavel and not self.editando:
            self._cadastrado()
        else:
            self._formulario()

    def _explicacao(self):
        self._bloco("Para que serve", [
            "Serve para buscar as NF-e de VENDA das empresas e as notas em que o CPF ou o CNPJ do responsável (por exemplo, o contador) "
            "foi incluído pelo emitente na própria nota, no campo autXML.",
            "A SEFAZ não entrega a uma empresa as NF-e que ela mesma emite. Elas só chegam a quem o emitente citou na nota, e por isso "
            "a consulta é feita com o certificado do responsável.",
            "Se você não precisa puxar NF-e de venda nem notas que tenham o CPF/CNPJ do responsável, NÃO é necessário cadastrar ninguém aqui. "
            "As NFS-e e as NF-e de compra continuam funcionando normalmente, com o certificado de cada empresa."], tom="verde_claro")
        self._bloco("O que é preciso", [
            "• Um certificado digital A1 (arquivo .pfx ou .p12) do responsável: e-CPF (da pessoa) ou e-CNPJ (da empresa dele). "
            "Certificado A3 (token ou cartão) não funciona neste programa.",
            "• O emitente das notas (o sistema que emite as NF-e do cliente) precisa incluir o CPF ou o CNPJ do responsável no autXML, "
            "e isso só vale para as notas emitidas depois de configurado. É preciso a autorização do cliente (LGPD).",
            "• Depois de cadastrar, na busca de cada empresa dá para escolher o certificado da NF-e: o da empresa, o do responsável ou os dois."])
        self._bloco("Onde ficam seus dados", [texto_dados_locais(self.store.pasta)], tom="aviso_fundo")

    # ------------------------------------------------------------------ formulário
    def _formulario(self):
        atual = self.store.responsavel if self.editando else None
        novo = atual is None
        rotulo(self.corpo, "Cadastrar o responsável" if novo else "Editar o responsável", 12, "bold", "verde_escuro").pack(anchor="w", pady=(0, 6))
        c = Cartao(self.corpo, pad=16)
        c.pack(fill="x", pady=(0, 16))
        k = c.corpo
        if novo:
            rotulo(k, "Antes de cadastrar, marque que está ciente:", 10, "bold").pack(anchor="w", pady=(0, 4))
            for var, txt in zip(self.v_ciente, CIENTES):
                Interruptor(k, txt, var, self._atualizar_salvar, tam=9).pack(anchor="w", pady=2)
            ui.divisor(k, (10, 10))
        else:
            ciente = (atual.get("ciente_em") or "")[:10]
            rotulo(k, "Ciência registrada neste computador" + (f" em {dt.date.fromisoformat(ciente):%d/%m/%Y}." if ciente else "."),
                   9, cor="suave").pack(anchor="w", pady=(0, 6))
        rotulo(k, "Certificado do responsável", 10, "bold").pack(anchor="w", pady=(0, 4))
        lin = tk.Frame(k, bg=P.superficie)
        lin.pack(anchor="w", pady=(0, 8))
        rotulo(lin, "O responsável é", 10, cor="suave").pack(side="left", padx=(0, 10))
        Segmentado(lin, [("cpf", "Pessoa (CPF)"), ("cnpj", "Empresa (CNPJ)")], self.v_tipo, self._mudou_tipo, tam=9, pady=4).pack(side="left")
        self.g = tk.Frame(k, bg=P.superficie)
        self.g.pack(fill="x")
        self.g.columnconfigure(1, weight=1)
        self.l_doc = rotulo(self.g, "", 9, "bold", "suave")
        self.l_doc.grid(row=0, column=0, sticky="w", pady=(0, 3), padx=(0, 12))
        Campo(self.g, self.v_doc, largura=24).grid(row=1, column=0, sticky="w", padx=(0, 12))
        rotulo(self.g, "Nome do responsável", 9, "bold", "suave").grid(row=0, column=1, sticky="w", pady=(0, 3))
        Campo(self.g, self.v_nome, largura=34).grid(row=1, column=1, sticky="ew")
        rotulo(self.g, "Arquivo do certificado A1 (.pfx/.p12)", 9, "bold", "suave").grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 3))
        pf = tk.Frame(self.g, bg=P.superficie)
        pf.grid(row=3, column=0, columnspan=2, sticky="ew")
        Campo(pf, self.v_pfx, largura=46).pack(side="left", fill="x", expand=True)
        Botao(pf, "Procurar...", self._procurar_pfx).pack(side="left", padx=(8, 0))
        rotulo(self.g, "Senha do certificado", 9, "bold", "suave").grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 3))
        sf = tk.Frame(self.g, bg=P.superficie)
        sf.grid(row=5, column=0, columnspan=2, sticky="w")
        self.campo_senha = Campo(sf, self.v_senha, largura=26, mostrar="●")
        self.campo_senha.pack(side="left")
        Interruptor(sf, "Mostrar", self.v_ver, lambda: self.campo_senha.configure(show="" if self.v_ver.get() else "●")).pack(side="left", padx=(10, 0))
        if atual and atual.get("senha_cifrada"):
            rotulo(self.g, "Já há uma senha salva. Deixe em branco para mantê-la.", 9, cor="suave").grid(row=6, column=0, columnspan=2, sticky="w", pady=(4, 0))
        Interruptor(k, "Lembrar a senha neste computador (fica cifrada)", self.v_lembrar, tam=9).pack(anchor="w", pady=(10, 4))
        v = tk.Frame(k, bg=P.superficie)
        v.pack(anchor="w", pady=(4, 0))
        Botao(v, "Validar certificado", self._validar, estilo="suave").pack(side="left")
        self.l_cert = rotulo(v, "", 9, cor="suave", largura=px(520))
        self.l_cert.pack(side="left", padx=10)
        self.l_erro = rotulo(k, "", 10, cor="erro", largura=px(LARG))
        self.l_erro.pack(anchor="w", pady=(8, 0))
        bt = tk.Frame(k, bg=P.superficie)
        bt.pack(anchor="w", pady=(8, 0))
        self.b_salvar = Botao(bt, "Salvar responsável", self._salvar, estilo="primario")
        self.b_salvar.pack(side="left")
        if not novo:
            Botao(bt, "Cancelar", self._cancelar_edicao).pack(side="left", padx=(8, 0))
        if atual:
            self.v_tipo.set(atual.get("tipo", "cpf"))
            self.v_doc.set(nfe_resp.formatar_documento(atual.get("documento", "")))
            self.v_nome.set(atual.get("nome", ""))
            self.v_pfx.set(atual.get("pfx", ""))
            self._validade = None
        self._mudou_tipo()
        self._atualizar_salvar()

    def _mudou_tipo(self):
        self.l_doc.config(text="CPF do responsável" if self.v_tipo.get() == "cpf" else "CNPJ do responsável")

    def _atualizar_salvar(self):
        if not hasattr(self, "b_salvar") or not self.b_salvar.winfo_exists():
            return
        ok = self.store.responsavel is not None and self.editando or all(v.get() for v in self.v_ciente)
        self.b_salvar.config(state="normal" if ok else "disabled")

    def _cancelar_edicao(self):
        self.editando = False
        self.atualizar()

    def _procurar_pfx(self):
        base = self.store.preferencias.get("pasta_certificados") or self.store.preferencias.get("raiz_padrao") or str(Path.home())
        c = filedialog.askopenfilename(parent=self, title="Escolha o certificado A1 do responsável", initialdir=base,
                                       filetypes=[("Certificado digital", "*.pfx *.p12"), ("Todos os arquivos", "*.*")])
        if c:
            self.v_pfx.set(os.path.normpath(c))
            self.store.preferencias["pasta_certificados"] = str(Path(c).parent)

    def _msg_cert(self, texto, cor="suave"):
        self.l_cert.config(text=texto, fg=P.__dict__.get(cor, cor))

    def _senha_digitada_ou_salva(self) -> str:
        senha = self.v_senha.get()
        if not senha and self.store.responsavel:
            try:
                senha = self.store.senha_do_responsavel()
            except ErroAdge:
                senha = ""
        return senha

    def _validar(self):
        """Abre o certificado e confere se ele é do documento informado. Preenche documento e nome quando estão em branco."""
        pfx, senha = self.v_pfx.get().strip(), self._senha_digitada_ou_salva()
        if not pfx or not senha:
            self._msg_cert("Escolha o arquivo e digite a senha.", "erro")
            return None
        try:
            info = core.ler_certificado(pfx, senha)
        except ErroAdge as e:
            self._msg_cert(str(e), "erro")
            return None
        if not nfe_resp.so_digitos(self.v_doc.get()) and info.get("documento"):
            self.v_tipo.set(info["tipo"])
            self.v_doc.set(nfe_resp.formatar_documento(info["documento"]))
            self._mudou_tipo()
        if info.get("nome") and not self.v_nome.get().strip():
            self.v_nome.set(info["nome"])
        problema = nfe_resp.conferir_certificado(info, self.v_doc.get())
        if problema:
            self._msg_cert(problema, "erro")
            return None
        self._validade = info["valido_ate"]
        if info["valido_ate"] < dt.date.today():
            self._msg_cert(f"Certificado VENCIDO em {info['valido_ate']:%d/%m/%Y}.", "erro")
        else:
            self._msg_cert(f"Certificado válido até {info['valido_ate']:%d/%m/%Y} e confere com o documento informado.", "verde_escuro")
        return info

    def _salvar(self):
        atual = self.store.responsavel if self.editando else None
        doc = nfe_resp.so_digitos(self.v_doc.get())
        pfx = self.v_pfx.get().strip()
        problema = None
        if atual is None and not all(v.get() for v in self.v_ciente):
            problema = "Marque as três confirmações de ciência para cadastrar."
        elif not nfe_resp.documento_valido(doc):
            problema = "Informe um CPF (11 dígitos) ou um CNPJ (14 dígitos) válido."
        elif nfe_resp.tipo_do_documento(doc) != self.v_tipo.get():
            problema = f"O documento tem {len(doc)} dígitos, mas você marcou {'CPF' if self.v_tipo.get() == 'cpf' else 'CNPJ'}."
        elif not self.v_nome.get().strip():
            problema = "Dê um nome para o responsável."
        elif not pfx or not Path(pfx).is_file():
            problema = "Escolha o arquivo do certificado (.pfx ou .p12)."
        elif atual is None and not self.v_senha.get():
            problema = "Digite a senha do certificado."
        if problema:
            self.l_erro.config(text=problema)
            return
        senha_nova = self.v_senha.get()
        info = None
        if senha_nova or self._senha_digitada_ou_salva():
            info = self._validar()
            if info is None:
                self.l_erro.config(text=self.l_cert.cget("text") or "Não consegui validar o certificado.")
                return
        resp = {"tipo": self.v_tipo.get(), "documento": doc, "nome": self.v_nome.get().strip(), "pfx": pfx,
                "ciente_em": (atual or {}).get("ciente_em") or dt.datetime.now().isoformat(timespec="seconds"),
                "senha_cifrada": (atual or {}).get("senha_cifrada", "")}
        if info:
            resp["cert_validade"] = info["valido_ate"].isoformat()
        elif atual and atual.get("cert_validade") and pfx == atual.get("pfx"):
            resp["cert_validade"] = atual["cert_validade"]
        try:
            if not self.v_lembrar.get():
                self.store.salvar_responsavel(resp, "")
            elif senha_nova:
                self.store.salvar_responsavel(resp, senha_nova)
            else:
                self.store.salvar_responsavel(resp)
        except ErroAdge as e:
            self.l_erro.config(text=str(e))
            return
        self.editando = False
        for v in self.v_ciente:
            v.set(False)
        self.v_senha.set("")
        self.atualizar()

    # ------------------------------------------------------------------ responsável cadastrado
    def _cadastrado(self):
        r = self.store.responsavel
        rotulo(self.corpo, "Responsável cadastrado", 12, "bold", "verde_escuro").pack(anchor="w", pady=(0, 6))
        c = Cartao(self.corpo, pad=16)
        c.pack(fill="x", pady=(0, 16))
        k = c.corpo
        rotulo(k, r.get("nome") or "—", 13, "bold").pack(anchor="w")
        rotulo(k, f"{'CPF' if r.get('tipo') == 'cpf' else 'CNPJ'} {nfe_resp.formatar_documento(r.get('documento', ''))}", 10, cor="suave").pack(anchor="w", pady=(1, 8))
        chips = tk.Frame(k, bg=P.superficie)
        chips.pack(anchor="w")
        from .app import situacao_certificado
        sel = situacao_certificado(r.get("cert_validade"))
        if sel:
            Chip(chips, sel[0], sel[1]).pack(side="left", padx=(0, 5))
        Chip(chips, "Senha salva (cifrada)" if r.get("senha_cifrada") else "Senha não salva: será pedida a cada busca", "neutro").pack(side="left")
        rotulo(k, "O arquivo do certificado e a senha ficam só neste computador. Na busca de cada empresa, em \"Certificado da NF-e\", "
                  "escolha entre o da empresa, o do responsável ou os dois.", 9, cor="suave", largura=px(LARG)).pack(anchor="w", pady=(10, 8))
        bt = tk.Frame(k, bg=P.superficie)
        bt.pack(anchor="w")
        Botao(bt, "Editar", self._editar).pack(side="left")
        Botao(bt, "Remover responsável", self._remover, estilo="perigo").pack(side="left", padx=(8, 0))
        self._lista_empresas(r)

    def _editar(self):
        self.editando = True
        self.atualizar()

    def _remover(self):
        if not ui.perguntar(self, "Remover o responsável?",
                            "O cadastro e a senha salva dele são apagados deste computador. O arquivo do certificado e os XMLs já gravados não são "
                            "apagados, nem as NF-e já guardadas no histórico de consultas.", sim="Remover", nao="Cancelar", perigo=True):
            return
        self.store.excluir_responsavel()
        self.atualizar()

    # ------------------------------------------------------------------ empresas que enviaram notas
    def _historico(self, r) -> HistoricoNFe:
        return HistoricoNFe(nfe_resp.emp_do_responsavel(r), base=getattr(self.app, "base_historico_resp", None) or self.base_historico)

    def _lista_empresas(self, r):
        rotulo(self.corpo, "Empresas que enviaram notas para este responsável", 12, "bold", "verde_escuro").pack(anchor="w", pady=(0, 6))
        c = Cartao(self.corpo, pad=16)
        c.pack(fill="x", pady=(0, 16))
        k = c.corpo
        rotulo(k, "A SEFAZ e a Receita não oferecem uma consulta de \"quais empresas este certificado pode acessar\". O que dá para mostrar, "
                  "e é mais confiável, são as empresas que de fato mandaram NF-e citando este responsável no autXML, vistas nas consultas feitas "
                  "neste computador. Uma empresa só aparece depois que o emitente passa a incluir o CPF/CNPJ do responsável e a primeira nota "
                  "chega.", 9, cor="suave", largura=px(LARG)).pack(anchor="w", pady=(0, 8))
        h = self._historico(r)
        docs = h.carregar_docs()
        empresas = nfe_resp.empresas_que_enviaram(docs, r["documento"], self.store.empresas)
        if not empresas:
            rotulo(k, nfe_resp.aviso_sem_autxml(len(docs), 0), 10, cor="aviso_texto", largura=px(LARG)).pack(anchor="w", pady=(0, 8))
        for e in empresas:
            lin = tk.Frame(k, bg=P.superficie)
            lin.pack(fill="x", pady=3)
            esq = tk.Frame(lin, bg=P.superficie)
            esq.pack(side="left")
            rotulo(esq, e["nome"] or "(sem nome)", 10, "bold", largura=px(430)).pack(anchor="w")
            ultima = f" · última emissão {dt.date.fromisoformat(e['ultima']):%d/%m/%Y}" if e["ultima"] else ""
            rotulo(esq, f"{nfe_resp.formatar_documento(e['documento'])} · {e['qtd']} nota(s){ultima}", 9, cor="suave").pack(anchor="w")
            Chip(lin, "Cadastrada no programa" if e["cadastrada"] else "Ainda não cadastrada", "verde" if e["cadastrada"] else "amarelo").pack(side="right")
        rodape = tk.Frame(k, bg=P.superficie)
        rodape.pack(anchor="w", pady=(10, 0), fill="x")
        resto = h.bloqueio_restante()
        self.b_atualizar = Botao(rodape, "Atualizar a lista agora (consulta a SEFAZ)", self._atualizar_lista_sefaz, estilo="suave")
        self.b_atualizar.config(state="disabled" if resto or self.trabalhando else "normal")
        self.b_atualizar.pack(side="left")
        self.l_status = rotulo(rodape, "", 9, cor="suave", largura=px(440))
        self.l_status.pack(side="left", padx=10)
        if resto:
            self.l_status.config(text=f"A SEFAZ libera outra consulta às {h.liberado_as():%H:%M} (em {formatar_espera(resto)}).")
        elif h.estado.get("ultima_consulta"):
            self.l_status.config(text=f"Última consulta do responsável: {h.estado['ultima_consulta'][:16].replace('T', ' ')}.")

    def _atualizar_lista_sefaz(self):
        if self.trabalhando:
            return
        r = self.store.responsavel
        if not ui.perguntar(self, "Consultar a SEFAZ pelo responsável?",
                            "O programa consulta a SEFAZ com o certificado do responsável e guarda as notas recebidas só neste computador, "
                            "no histórico do responsável; elas depois entram nas buscas das empresas. A SEFAZ limita as consultas: sem nota "
                            "nova, só libera outra depois de cerca de 1 hora (limite dela, não da Adge).", sim="Consultar", nao="Cancelar"):
            return
        try:
            senha = self.store.senha_do_responsavel(r)
        except ErroAdge as e:
            ui.avisar(self, "Não consegui usar a senha salva", str(e))
            senha = ""
        if not senha:
            senha = ui.pedir_texto(self, "Senha do certificado do responsável", f"Digite a senha do certificado de {r.get('nome') or 'responsável'}:",
                                   oculto=True, validar=lambda t: None if t else "Digite a senha.")
            if not senha:
                return
        self.trabalhando = True
        self.b_atualizar.config(state="disabled")
        self.l_status.config(text="Consultando a SEFAZ...")

        def trabalho():
            try:
                h = self._historico(r)
                sessao = getattr(self.app, "sessao_nfe_resp", None) or self.sessao_teste or nfe.sessao_nfe(r["pfx"], senha)
                res = nfe.consultar_distribuicao(sessao, r["documento"], h.estado["ult_nsu"],
                                                 log=lambda m: self.fila.put(("log", m)))
                h.registrar_bloqueio(res["max_nsu"], res["bloqueado_ate"])
                # as notas ficam no histórico do responsável (cópia local): o NSU avança junto, sem perder nada
                h.confirmar(res["docs"], res["ult_nsu"], res["max_nsu"])
                self.fila.put(("ok", res))
            except Cancelado:
                self.fila.put(("erro", "Consulta cancelada."))
            except ErroAdge as e:
                self.fila.put(("erro", str(e)))
            except Exception as e:  # nunca deixar a página travada
                self.fila.put(("erro", f"Erro inesperado: {e}"))

        threading.Thread(target=trabalho, daemon=True).start()

    def _ler_fila(self):
        try:
            while True:
                tipo, dado = self.fila.get_nowait()
                if tipo == "log" and self.winfo_exists() and getattr(self, "l_status", None) and self.l_status.winfo_exists():
                    self.l_status.config(text=dado)
                elif tipo == "ok":
                    self.trabalhando = False
                    self.atualizar()
                    if dado["situacao"] == "bloqueado":
                        ui.avisar(self, "A SEFAZ pediu para esperar", "A SEFAZ recusou a consulta por excesso de consultas (limite dela). "
                                                                       "Tente de novo depois do horário que a tela informa.")
                elif tipo == "erro":
                    self.trabalhando = False
                    self.atualizar()
                    ui.erro(self, "Não consegui consultar pelo responsável", dado)
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(200, self._ler_fila)
