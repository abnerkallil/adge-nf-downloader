"""Tela "Configurar para Emissão de Notas": regime da empresa, perfis de serviço e tomadores recorrentes.

Grava em `empresa["emissao"]` (ver `config_schema.py`). Não mexe na busca/download de notas nem em
`empresa["fiscal"]` (simulação de regimes), que são outras telas.
"""
import tkinter as tk
from tkinter import ttk

from .. import grafico, ui
from ..core import ErroAdge
from ..ui import P, Botao, Campo, Cartao, Chip, Interruptor, Modal, Rolavel, Segmentado, F, px, rotulo
from . import config_schema as es
from . import dados_oficiais as do


def caixa_texto(pai, altura=3, largura=40) -> tk.Frame:
    """Campo de texto multilinha. A moldura é o widget a posicionar; o Text fica em `.texto`."""
    moldura = tk.Frame(pai, bg=P.borda_forte, padx=1, pady=1)
    texto = tk.Text(moldura, height=altura, width=largura, relief="flat", bd=0, font=F(10), bg=P.campo, fg=P.texto,
                    insertbackground=P.texto, wrap="word", selectbackground=P.selecao, selectforeground=P.texto,
                    padx=px(8), pady=px(6))
    texto.pack(fill="both", expand=True)
    moldura.texto = texto
    return moldura


def inserir_marcador(texto_widget: tk.Text, marcador: str):
    texto_widget.insert("insert", marcador)
    texto_widget.focus_set()


def campo_rotulado(pai, row, texto, widget, dica="", col=0, columnspan=2):
    rotulo(pai, texto, 9, "bold", "suave").grid(row=row, column=col, sticky="w", pady=(10, 3), columnspan=columnspan)
    widget.grid(row=row + 1, column=col, sticky="ew", columnspan=columnspan)
    if dica:
        rotulo(pai, dica, 9, cor="suave").grid(row=row + 2, column=col, sticky="w", pady=(2, 0), columnspan=columnspan)
    return row + (3 if dica else 2)


def campo_busca(pai, variavel, funcao_busca, largura=40, linhas_lista=5):
    """Campo de texto com busca embaixo, tipo o combo do portal: filtra as opções enquanto
    digita e clicar numa opção substitui o texto do campo por ela (código + descrição)."""
    moldura = tk.Frame(pai, bg=ui._bg(pai))
    campo = Campo(moldura, variavel, largura=largura)
    campo.pack(fill="x")
    lista = tk.Listbox(moldura, height=linhas_lista, font=F(9), relief="flat", bd=1, highlightthickness=1,
                       highlightbackground=P.borda_forte, bg=P.campo, fg=P.texto,
                       selectbackground=P.selecao, selectforeground=P.texto)

    def atualizar(*_a):
        texto = variavel.get()
        opcoes = funcao_busca(texto)
        lista.delete(0, "end")
        for o in opcoes:
            lista.insert("end", o)
        if opcoes:
            lista.pack(fill="x", pady=(2, 0))
        else:
            lista.pack_forget()

    def escolher(_e=None):
        sel = lista.curselection()
        if sel:
            variavel.set(lista.get(sel[0]))
            lista.pack_forget()

    campo.entry.bind("<KeyRelease>", atualizar)
    campo.entry.bind("<FocusIn>", atualizar)
    lista.bind("<<ListboxSelect>>", escolher)
    moldura.campo = campo
    moldura.lista = lista
    return moldura


def caixa_aviso(pai, texto, largura=560):
    """Caixa amarela de aviso (nunca bloqueia salvar — é só pra chamar atenção)."""
    caixa = tk.Frame(pai, bg=P.aviso_fundo)
    rotulo(caixa, texto, 9, cor="aviso_texto", largura=px(largura), bg=P.aviso_fundo).pack(
        anchor="w", padx=px(10), pady=px(8))
    return caixa


# ============================================================================= perfil de serviço
class DialogoPerfilServico(Modal):
    def __init__(self, pai, perfil: dict, regime_empresa: str):
        super().__init__(pai, "Perfil de serviço", largura=640, altura=760)
        self.resizable(True, True)
        self.minsize(px(560), px(520))
        self.resultado = None
        self.perfil = {**es.perfil_padrao(), **perfil, "issqn": {**es.issqn_padrao(), **perfil.get("issqn", {})},
                       "pis_cofins": {**es.pis_cofins_padrao(), **perfil.get("pis_cofins", {})},
                       "descricao": {**{"modo": "fixo", "texto": ""}, **perfil.get("descricao", {})}}
        self.regime_empresa = regime_empresa
        self.regra_pis_cofins = es.pis_cofins_regra(regime_empresa)
        self.regra_issqn = es.issqn_regra(regime_empresa)
        self._montar()
        self.bind("<Escape>", lambda *_: self.destroy())
        self.mostrar()

    def _montar(self):
        ui.titulo(self, "Perfil de serviço",
                  "Os dados que o portal da NFS-e Nacional pede para emitir notas deste tipo de serviço.").pack(anchor="w", pady=(0, 12))
        self.rolagem = Rolavel(self)
        self.rolagem.pack(fill="both", expand=True)
        corpo = self.rolagem.corpo
        p = self.perfil

        self.v_nome = tk.StringVar(value=p["nome"])
        self.v_ativo = tk.BooleanVar(value=p["ativo"])
        self.v_ctn = tk.StringVar(value=p["ctn"])
        self.v_nbs = tk.StringVar(value=p["nbs"])
        iq = p["issqn"]
        self.v_trib_issqn = tk.StringVar(value=es.TRIB_ISSQN[iq["trib_issqn"]])
        self.v_tp_ret_issqn = tk.StringVar(value=es.TP_RET_ISSQN[iq["tp_ret_issqn"]])
        pc = p["pis_cofins"]
        self.v_pc_incluir = tk.BooleanVar(value=pc["incluir"])
        self.v_pc_regime = tk.StringVar(value=es.PIS_COFINS_REGIMES.get(pc["regime"], es.PIS_COFINS_REGIMES["cumulativo"]))
        self.v_cst_pis = tk.StringVar(value=pc["cst_pis"])
        self.v_cst_cofins = tk.StringVar(value=pc["cst_cofins"])
        self.v_aliq_pis = tk.StringVar(value=self._pct_str(pc["aliquota_pis"]))
        self.v_aliq_cofins = tk.StringVar(value=self._pct_str(pc["aliquota_cofins"]))
        self.v_tp_ret_pc = tk.StringVar(value=es.TP_RET_PISCOFINS[pc["tp_ret_pis_cofins"]])
        self.v_desc_modo = tk.StringVar(value=p["descricao"]["modo"])

        cartao1 = Cartao(corpo)
        cartao1.pack(fill="x")
        g = cartao1.corpo
        g.columnconfigure(0, weight=1)
        rotulo(g, "Nome do perfil", 9, "bold", "suave").grid(row=0, column=0, sticky="w", pady=(0, 3))
        Campo(g, self.v_nome, largura=36).grid(row=1, column=0, sticky="ew")
        Interruptor(g, "Perfil ativo (aparece para escolha na emissão)", self.v_ativo).grid(row=2, column=0, sticky="w", pady=(10, 0))

        ui.secao(corpo, "Como o portal classifica o serviço").pack(anchor="w", pady=(16, 6))
        cartao2 = Cartao(corpo)
        cartao2.pack(fill="x")
        g2 = cartao2.corpo
        g2.columnconfigure(0, weight=1)
        r = campo_rotulado(g2, 0, "Código de Tributação Nacional (CTN)",
                           campo_busca(g2, self.v_ctn, do.buscar_ctn, largura=40),
                           "Busca pelo código ou por palavra da descrição, igual ao combo do portal.")
        self.l_alerta_ctn = caixa_aviso(g2, "")
        self.l_alerta_ctn.grid(row=r, column=0, sticky="ew", pady=(0, 8))
        self.l_alerta_ctn.grid_remove()
        r += 1
        r = campo_rotulado(g2, r, "Item da NBS correspondente ao serviço",
                           campo_busca(g2, self.v_nbs, do.buscar_nbs, largura=40),
                           "Sugestões a partir do Anexo VIII — ainda não é a lista oficial completa de NBS; "
                           "se o seu serviço não aparecer, copie do combo do portal mesmo assim.")
        if self.regra_issqn == "nao_aplica":
            rotulo(g2, "Empresa MEI: o ISS é o valor fixo do DAS-MEI — a nota não declara tributação por item.",
                  9, cor="suave", largura=px(560)).grid(row=r, column=0, sticky="w", pady=(10, 0))
        else:
            ttk.Combobox(g2, textvariable=self.v_trib_issqn, values=list(es.TRIB_ISSQN.values()), state="readonly",
                        width=30, font=F(10)).grid(row=r, column=0, sticky="w", pady=(10, 3))
            rotulo(g2, "Tributação do ISSQN (\"é caso de imunidade, exportação ou não incidência?\")", 9, cor="suave").grid(
                row=r + 1, column=0, sticky="w")
            self.cb_tp_ret_issqn = ttk.Combobox(g2, textvariable=self.v_tp_ret_issqn, values=list(es.TP_RET_ISSQN.values()),
                        state="readonly", width=30, font=F(10))
            self.cb_tp_ret_issqn.grid(row=r + 2, column=0, sticky="w", pady=(10, 3))
            rotulo(g2, "Retenção do ISSQN (bloqueado em \"Não retido\" quando não é operação tributável — regra oficial E0580)",
                  9, cor="suave", largura=px(560)).grid(row=r + 3, column=0, sticky="w")
            self.v_trib_issqn.trace_add("write", lambda *_: self._atualizar_tp_ret_issqn())
            self._atualizar_tp_ret_issqn()

        self.v_ctn.trace_add("write", lambda *_: self._atualizar_alerta_ctn())
        self._atualizar_alerta_ctn()
        self._secao_pis_cofins(corpo)
        self._secao_descricao(corpo, p)
        self._secao_info_complementares(corpo, p)

        self.l_erro = rotulo(self, "", 10, cor="erro", largura=px(560))
        self.l_erro.pack(anchor="w", pady=(8, 0))
        lin = tk.Frame(self, bg=P.fundo)
        lin.pack(fill="x", pady=(8, 0))
        Botao(lin, "Cancelar", self.destroy).pack(side="right")
        Botao(lin, "Usar este perfil", self._salvar, estilo="primario").pack(side="right", padx=(0, 8))

    @staticmethod
    def _pct_str(v: float) -> str:
        return f"{v:.2f}".replace(".", ",") if v else ""

    def _secao_pis_cofins(self, corpo):
        ui.secao(corpo, "PIS/COFINS").pack(anchor="w", pady=(16, 6))
        if self.regra_pis_cofins == "proibido":
            cartao = Cartao(corpo, pad=12)
            cartao.pack(fill="x")
            rotulo(cartao.corpo, "Empresa MEI: a NFS-e não leva grupo de PIS/COFINS.", 10, cor="suave").pack(anchor="w")
            return
        cartao = Cartao(corpo)
        cartao.pack(fill="x")
        g = cartao.corpo
        g.columnconfigure(0, weight=1)
        obrigatorio = self.regra_pis_cofins == "obrigatorio"
        chk = Interruptor(g, "Incluir PIS/COFINS nesta nota" + (" (obrigatório neste regime)" if obrigatorio else ""),
                          self.v_pc_incluir, self._atualizar_pis_cofins)
        chk.grid(row=0, column=0, sticky="w")
        if obrigatorio:
            self.v_pc_incluir.set(True)
            chk.desabilitar(True)
        self.f_pc = tk.Frame(g, bg=P.superficie)
        self.f_pc.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.f_pc.columnconfigure(0, weight=1)
        self.f_pc.columnconfigure(1, weight=1)
        ttk.Combobox(self.f_pc, textvariable=self.v_pc_regime, values=list(es.PIS_COFINS_REGIMES.values()),
                    state="readonly", width=18, font=F(10)).grid(row=0, column=0, sticky="w", pady=(0, 8))
        linha1 = tk.Frame(self.f_pc, bg=P.superficie)
        linha1.grid(row=1, column=0, columnspan=2, sticky="ew")
        rotulo(linha1, "CST PIS", 9, cor="suave").pack(anchor="w")
        Campo(linha1, self.v_cst_pis, largura=10).pack(anchor="w", pady=(2, 8))
        rotulo(linha1, "CST COFINS", 9, cor="suave").pack(anchor="w")
        Campo(linha1, self.v_cst_cofins, largura=10).pack(anchor="w", pady=(2, 8))
        rotulo(linha1, "Alíquota PIS (%)", 9, cor="suave").pack(anchor="w")
        Campo(linha1, self.v_aliq_pis, largura=10).pack(anchor="w", pady=(2, 8))
        rotulo(linha1, "Alíquota COFINS (%)", 9, cor="suave").pack(anchor="w")
        Campo(linha1, self.v_aliq_cofins, largura=10).pack(anchor="w", pady=(2, 0))
        rotulo(linha1, "Retenção de PIS/COFINS/CSLL", 9, cor="suave").pack(anchor="w")
        ttk.Combobox(linha1, textvariable=self.v_tp_ret_pc, values=list(es.TP_RET_PISCOFINS.values()), state="readonly",
                    width=38, font=F(10)).pack(anchor="w", pady=(2, 0))
        rotulo(g, "CST do PIS/COFINS: 2 dígitos (00-09, 49-56, 60-67, 70-75, 98 ou 99 — lista fechada do XSD).",
              9, cor="suave", largura=px(560)).grid(row=2, column=0, sticky="w", pady=(8, 0))
        self._atualizar_pis_cofins()

    def _atualizar_pis_cofins(self):
        estado = "normal" if self.v_pc_incluir.get() else "disabled"
        for w in self.f_pc.winfo_children():
            self._definir_estado(w, estado)

    def _definir_estado(self, w, estado):
        try:
            w.configure(state=estado)
        except tk.TclError:
            pass
        for filho in w.winfo_children():
            self._definir_estado(filho, estado)

    def _atualizar_tp_ret_issqn(self):
        """RN oficial E0580: não é permitido haver retenção do ISSQN quando o serviço não é
        operação tributável (imunidade, exportação ou não incidência) — força "Não retido" e
        trava o campo nesses casos."""
        if not hasattr(self, "cb_tp_ret_issqn"):
            return
        tributavel = self.v_trib_issqn.get() == es.TRIB_ISSQN[1]
        if not tributavel:
            self.v_tp_ret_issqn.set(es.TP_RET_ISSQN[1])
        self.cb_tp_ret_issqn.configure(state="readonly" if tributavel else "disabled")

    def _atualizar_alerta_ctn(self):
        """Aviso próprio do ADGE (não bloqueia salvar) quando o CTN escolhido costuma ser do
        Simples Nacional (ou impeditivo a ele) e a empresa está noutro regime — ver dados_oficiais.py."""
        aviso = do.alerta_ctn_regime(self.v_ctn.get(), self.regime_empresa)
        for w in self.l_alerta_ctn.winfo_children():
            w.destroy()
        if aviso:
            rotulo(self.l_alerta_ctn, aviso, 9, cor="aviso_texto", largura=px(540), bg=P.aviso_fundo).pack(
                anchor="w", padx=px(10), pady=px(8))
            self.l_alerta_ctn.grid()
        else:
            self.l_alerta_ctn.grid_remove()

    def _secao_descricao(self, corpo, p):
        ui.secao(corpo, "Descrição do serviço").pack(anchor="w", pady=(16, 6))
        cartao = Cartao(corpo)
        cartao.pack(fill="x")
        g = cartao.corpo
        ui.radio(g, "Texto fixo (igual todo mês)", "fixo", self.v_desc_modo).pack(anchor="w")
        ui.radio(g, "Trocar {MES} e {ANO} pela competência a cada emissão", "mes_ano", self.v_desc_modo).pack(anchor="w", pady=(2, 8))
        self.caixa_desc = caixa_texto(g, altura=3, largura=50)
        self.caixa_desc.texto.insert("1.0", p["descricao"]["texto"])
        self.caixa_desc.pack(fill="x")
        marc = tk.Frame(g, bg=P.superficie)
        marc.pack(anchor="w", pady=(6, 0))
        rotulo(marc, "Inserir:", 9, cor="suave").pack(side="left", padx=(0, 6))
        for m in es.MARCADORES:
            Botao(marc, m, lambda m=m: inserir_marcador(self.caixa_desc.texto, m), estilo="suave", pady=4).pack(side="left", padx=(0, 6))

    def _secao_info_complementares(self, corpo, p):
        ui.secao(corpo, "Informações complementares").pack(anchor="w", pady=(16, 6))
        cartao = Cartao(corpo)
        cartao.pack(fill="x")
        self.caixa_info = caixa_texto(cartao.corpo, altura=3, largura=50)
        self.caixa_info.texto.insert("1.0", p["informacoes_complementares"])
        self.caixa_info.pack(fill="x")

    def _salvar(self):
        nome = self.v_nome.get().strip()
        if not nome:
            self.l_erro.config(text="Dê um nome para o perfil (ex.: \"Locação residencial\").")
            return
        ctn, nbs = self.v_ctn.get().strip(), self.v_nbs.get().strip()
        if not ctn or not nbs:
            self.l_erro.config(text="Informe pelo menos o CTN e o NBS.")
            return
        if not do.ctn_existe(ctn):
            self.l_erro.config(text="Este CTN não existe na lista oficial do Anexo B (regra do leiaute E0310). "
                                     "Escolha um da lista de busca.")
            return
        try:
            aliq_pis = grafico.parse_brl(self.v_aliq_pis.get()) if hasattr(self, "v_aliq_pis") else 0.0
            aliq_cofins = grafico.parse_brl(self.v_aliq_cofins.get()) if hasattr(self, "v_aliq_cofins") else 0.0
        except ValueError as e:
            self.l_erro.config(text=str(e))
            return
        if self.regra_pis_cofins != "proibido" and self.v_pc_incluir.get():
            if not (0 <= aliq_pis <= 100) or not (0 <= aliq_cofins <= 100):
                self.l_erro.config(text="Alíquota de PIS/COFINS tem que estar entre 0% e 100% (regra do leiaute E0686/E0692).")
                return
            for rotulo_cst, cst in (("PIS", self.v_cst_pis.get().strip()), ("COFINS", self.v_cst_cofins.get().strip())):
                if cst and cst not in es.CST_PISCOFINS_VALIDOS:
                    self.l_erro.config(text=f"CST do {rotulo_cst} \"{cst}\" não existe (lista fechada do XSD oficial). "
                                             "Veja a dica abaixo do campo.")
                    return
        nome_para_chave_pc = {v: k for k, v in es.PIS_COFINS_REGIMES.items()}
        nome_para_trib_issqn = {v: k for k, v in es.TRIB_ISSQN.items()}
        nome_para_tp_ret_issqn = {v: k for k, v in es.TP_RET_ISSQN.items()}
        nome_para_tp_ret_pc = {v: k for k, v in es.TP_RET_PISCOFINS.items()}
        self.perfil.update({
            "nome": nome, "ativo": self.v_ativo.get(), "ctn": ctn, "nbs": nbs,
            "descricao": {"modo": self.v_desc_modo.get(), "texto": self.caixa_desc.texto.get("1.0", "end-1c")},
            "informacoes_complementares": self.caixa_info.texto.get("1.0", "end-1c"),
        })
        if self.regra_issqn != "nao_aplica":
            self.perfil["issqn"] = {
                "trib_issqn": nome_para_trib_issqn.get(self.v_trib_issqn.get(), 1),
                "tp_ret_issqn": nome_para_tp_ret_issqn.get(self.v_tp_ret_issqn.get(), 1),
            }
        else:
            self.perfil["issqn"] = es.issqn_padrao()
        if self.regra_pis_cofins != "proibido":
            self.perfil["pis_cofins"] = {
                "incluir": self.v_pc_incluir.get() or self.regra_pis_cofins == "obrigatorio",
                "regime": nome_para_chave_pc.get(self.v_pc_regime.get(), "cumulativo"),
                "cst_pis": self.v_cst_pis.get().strip(), "cst_cofins": self.v_cst_cofins.get().strip(),
                "aliquota_pis": aliq_pis, "aliquota_cofins": aliq_cofins,
                "tp_ret_pis_cofins": nome_para_tp_ret_pc.get(self.v_tp_ret_pc.get(), 0),
            }
        else:
            self.perfil["pis_cofins"] = es.pis_cofins_padrao()
        self.resultado = self.perfil
        self.destroy()


# ============================================================================= tomador recorrente
class DialogoTomador(Modal):
    def __init__(self, pai, tomador: dict, perfis: list, identificacao_padrao_empresa: str = "documento"):
        super().__init__(pai, "Tomador recorrente", largura=560, altura=720)
        self.resizable(True, True)
        self.minsize(px(500), px(520))
        self.resultado = None
        self.perfis = perfis
        self.identificacao_padrao_empresa = identificacao_padrao_empresa
        self.tomador = {**es.tomador_padrao(), **tomador,
                        "endereco": {**es.endereco_padrao(), **tomador.get("endereco", {})},
                        "descricao": {**{"modo": "herdar", "texto": ""}, **tomador.get("descricao", {})},
                        "informacoes_complementares": {**{"modo": "herdar", "texto": ""}, **tomador.get("informacoes_complementares", {})}}
        self._montar()
        self.bind("<Escape>", lambda *_: self.destroy())
        self.mostrar()

    def _montar(self):
        ui.titulo(self, "Tomador recorrente",
                  "Quando uma nota bater com este cadastro (pelo documento, nome ou endereço), o perfil é aplicado sozinho."
                  ).pack(anchor="w", pady=(0, 12))
        self.rolagem = Rolavel(self)
        self.rolagem.pack(fill="both", expand=True)
        corpo = self.rolagem.corpo
        t = self.tomador
        e = t["endereco"]
        self.v_nome = tk.StringVar(value=t["nome"])
        self.v_doc = tk.StringVar(value=t["documento"])
        self.v_identificacao = tk.StringVar(value=es.TOMADOR_IDENTIFICACAO_MODOS[t["modo_identificacao"]])
        self.v_cep = tk.StringVar(value=e["cep"])
        self.v_logradouro = tk.StringVar(value=e["logradouro"])
        self.v_numero = tk.StringVar(value=e["numero"])
        self.v_complemento = tk.StringVar(value=e["complemento"])
        self.v_bairro = tk.StringVar(value=e["bairro"])
        self.v_end_municipio = tk.StringVar(value=e["municipio"])
        self.v_end_uf = tk.StringVar(value=e["uf"])
        self.v_end_ibge = tk.StringVar(value=e["codigo_municipio_ibge"])
        self.v_ativo = tk.BooleanVar(value=t["ativo"])
        nomes_perfis = ["(usar o perfil padrão da empresa)"] + [p["nome"] or "(sem nome)" for p in self.perfis]
        self._id_por_nome = {p["nome"] or "(sem nome)": p["id"] for p in self.perfis}
        atual = next((p["nome"] or "(sem nome)" for p in self.perfis if p["id"] == t.get("perfil_id")), nomes_perfis[0])
        self.v_perfil = tk.StringVar(value=atual)
        self.v_desc_modo = tk.StringVar(value=t["descricao"]["modo"])
        self.v_info_modo = tk.StringVar(value=t["informacoes_complementares"]["modo"])

        cartao = Cartao(corpo)
        cartao.pack(fill="x")
        g = cartao.corpo
        g.columnconfigure(0, weight=1)
        campo_rotulado(g, 0, "Nome", Campo(g, self.v_nome, largura=40))
        r = campo_rotulado(g, 3, "CPF ou CNPJ", Campo(g, self.v_doc, largura=22))
        rotulo(g, "Como identificar este tomador na nota", 9, "bold", "suave").grid(row=r, column=0, sticky="w", pady=(10, 3))
        ttk.Combobox(g, textvariable=self.v_identificacao, values=list(es.TOMADOR_IDENTIFICACAO_MODOS.values()),
                    state="readonly", width=48, font=F(10)).grid(row=r + 1, column=0, sticky="ew")
        padrao_nome = es.MODOS_IDENTIFICACAO[self.identificacao_padrao_empresa]
        rotulo(g, f"Padrão da empresa hoje: {padrao_nome}", 9, cor="suave", largura=px(480)).grid(
            row=r + 2, column=0, sticky="w", pady=(2, 0))
        r += 3
        rotulo(g, "Perfil de serviço deste tomador", 9, "bold", "suave").grid(row=r, column=0, sticky="w", pady=(10, 3))
        ttk.Combobox(g, textvariable=self.v_perfil, values=nomes_perfis, state="readonly", width=34, font=F(10)).grid(
            row=r + 1, column=0, sticky="ew")
        Interruptor(g, "Tomador ativo (entra no casamento automático)", self.v_ativo).grid(row=r + 2, column=0, sticky="w", pady=(10, 0))

        ui.secao(corpo, "Endereço completo (obrigatório quando a identificação é por endereço)").pack(anchor="w", pady=(16, 6))
        cartao_end = Cartao(corpo)
        cartao_end.pack(fill="x")
        ge = cartao_end.corpo
        ge.columnconfigure(0, weight=1)
        ge.columnconfigure(1, weight=1)
        campo_rotulado(ge, 0, "CEP", Campo(ge, self.v_cep, largura=12), col=0, columnspan=1)
        campo_rotulado(ge, 0, "Número", Campo(ge, self.v_numero, largura=12), col=1, columnspan=1)
        campo_rotulado(ge, 3, "Logradouro", Campo(ge, self.v_logradouro, largura=40))
        campo_rotulado(ge, 6, "Complemento", Campo(ge, self.v_complemento, largura=40))
        campo_rotulado(ge, 9, "Bairro", Campo(ge, self.v_bairro, largura=22), col=0, columnspan=1)
        linha_mun = tk.Frame(ge, bg=P.superficie)
        Campo(linha_mun, self.v_end_municipio, largura=18).pack(side="left")
        Campo(linha_mun, self.v_end_uf, largura=4).pack(side="left", padx=(6, 0))
        campo_rotulado(ge, 9, "Município e UF", linha_mun, col=1, columnspan=1)
        campo_rotulado(ge, 12, "Código IBGE do município", Campo(ge, self.v_end_ibge, largura=12), col=0, columnspan=1,
                       dica="Necessário para a nota (campo cMun). Busque em ibge.gov.br/explica/codigos-dos-municipios.")

        ui.secao(corpo, "Descrição para este tomador").pack(anchor="w", pady=(16, 6))
        cartao2 = Cartao(corpo)
        cartao2.pack(fill="x")
        g2 = cartao2.corpo
        for valor, txt in es.TOMADOR_DESCRICAO_MODOS.items():
            ui.radio(g2, txt, valor, self.v_desc_modo, self._atualizar_descricao).pack(anchor="w", pady=1)
        self.caixa_desc = caixa_texto(g2, altura=2, largura=46)
        self.caixa_desc.texto.insert("1.0", t["descricao"]["texto"])
        self.caixa_desc.pack(fill="x", pady=(6, 0))
        marc = tk.Frame(g2, bg=P.superficie)
        marc.pack(anchor="w", pady=(6, 0))
        rotulo(marc, "Inserir:", 9, cor="suave").pack(side="left", padx=(0, 6))
        for m in es.MARCADORES:
            Botao(marc, m, lambda m=m: inserir_marcador(self.caixa_desc.texto, m), estilo="suave", pady=4).pack(side="left", padx=(0, 6))

        ui.secao(corpo, "Informações complementares para este tomador").pack(anchor="w", pady=(16, 6))
        cartao3 = Cartao(corpo)
        cartao3.pack(fill="x")
        g3 = cartao3.corpo
        for valor, txt in es.TOMADOR_INFO_MODOS.items():
            ui.radio(g3, txt, valor, self.v_info_modo, self._atualizar_info).pack(anchor="w", pady=1)
        self.caixa_info = caixa_texto(g3, altura=2, largura=46)
        self.caixa_info.texto.insert("1.0", t["informacoes_complementares"]["texto"])
        self.caixa_info.pack(fill="x", pady=(6, 0))

        self._atualizar_descricao()
        self._atualizar_info()
        self.l_erro = rotulo(self, "", 10, cor="erro", largura=px(500))
        self.l_erro.pack(anchor="w", pady=(8, 0))
        lin = tk.Frame(self, bg=P.fundo)
        lin.pack(fill="x", pady=(8, 0))
        Botao(lin, "Cancelar", self.destroy).pack(side="right")
        Botao(lin, "Salvar tomador", self._salvar, estilo="primario").pack(side="right", padx=(0, 8))

    def _atualizar_descricao(self):
        self.caixa_desc.texto.configure(state="normal" if self.v_desc_modo.get() != "herdar" else "disabled")

    def _atualizar_info(self):
        self.caixa_info.texto.configure(state="normal" if self.v_info_modo.get() != "herdar" else "disabled")

    def _salvar(self):
        nome = self.v_nome.get().strip()
        doc = self.v_doc.get().strip()
        nome_para_modo = {v: k for k, v in es.TOMADOR_IDENTIFICACAO_MODOS.items()}
        modo = nome_para_modo.get(self.v_identificacao.get(), "herdar")
        modo_efetivo = modo if modo != "herdar" else self.identificacao_padrao_empresa
        endereco = {"cep": self.v_cep.get().strip(), "logradouro": self.v_logradouro.get().strip(),
                    "numero": self.v_numero.get().strip(), "complemento": self.v_complemento.get().strip(),
                    "bairro": self.v_bairro.get().strip(), "municipio": self.v_end_municipio.get().strip(),
                    "uf": self.v_end_uf.get().strip().upper(), "codigo_municipio_ibge": self.v_end_ibge.get().strip()}
        tem_endereco = bool(endereco["logradouro"] and endereco["municipio"])
        if not nome:
            self.l_erro.config(text="Dê um nome para o tomador.")
            return
        if not doc and not tem_endereco:
            self.l_erro.config(text="Informe o documento ou o endereço completo: é por aí que a nota é reconhecida.")
            return
        if modo_efetivo == "endereco" and not tem_endereco:
            self.l_erro.config(text="Este tomador está configurado para exigir endereço completo: informe pelo menos logradouro e município.")
            return
        self.tomador.update({
            "nome": nome, "documento": doc, "modo_identificacao": modo, "endereco": endereco, "ativo": self.v_ativo.get(),
            "perfil_id": self._id_por_nome.get(self.v_perfil.get()),
            "descricao": {"modo": self.v_desc_modo.get(), "texto": self.caixa_desc.texto.get("1.0", "end-1c")},
            "informacoes_complementares": {"modo": self.v_info_modo.get(), "texto": self.caixa_info.texto.get("1.0", "end-1c")},
        })
        self.resultado = self.tomador
        self.destroy()


# ============================================================================= configuração da empresa
class DialogoConfiguracaoEmissao(Modal):
    def __init__(self, pai, store, emp: dict):
        super().__init__(pai, f"Configurar emissão - {emp['nome']}", largura=760, altura=820)
        self.resizable(True, True)
        self.minsize(px(640), px(540))
        self.store, self.emp, self.salvou = store, emp, False
        self.cfg = es.migrar(emp.get("emissao"))
        self.v_aba = tk.StringVar(value="empresa")
        self._montar()
        self.bind("<Escape>", lambda *_: self.destroy())
        self.mostrar()

    def _montar(self):
        ui.titulo(self, f"Configurar emissão — {self.emp['nome']}",
                  "Preenchido uma vez, usado em todas as emissões desta empresa.").pack(anchor="w", pady=(0, 12))
        self.seg = Segmentado(self, [("empresa", "Empresa"), ("perfis", "Perfis de serviço"), ("tomadores", "Tomadores recorrentes")],
                              self.v_aba, self._trocar_aba)
        self.seg.pack(anchor="w", pady=(0, 12))
        self.area = tk.Frame(self, bg=P.fundo)
        self.area.pack(fill="both", expand=True)
        self.f_empresa = self._aba_empresa(self.area)
        self.f_perfis = self._aba_perfis(self.area)
        self.f_tomadores = self._aba_tomadores(self.area)
        self.f_empresa.pack(fill="both", expand=True)

        self.l_erro = rotulo(self, "", 10, cor="erro", largura=px(700))
        self.l_erro.pack(anchor="w", pady=(10, 0))
        lin = tk.Frame(self, bg=P.fundo)
        lin.pack(fill="x", pady=(8, 0))
        Botao(lin, "Cancelar", self.destroy).pack(side="right")
        Botao(lin, "Salvar configuração", self._salvar, estilo="primario").pack(side="right", padx=(0, 8))

    def _trocar_aba(self):
        for f in (self.f_empresa, self.f_perfis, self.f_tomadores):
            f.pack_forget()
        {"empresa": self.f_empresa, "perfis": self.f_perfis, "tomadores": self.f_tomadores}[self.v_aba.get()].pack(fill="both", expand=True)

    # ------------------------------------------------------------------ aba Empresa
    def _aba_empresa(self, pai):
        f = Rolavel(pai)
        corpo = f.corpo
        cfg = self.cfg
        self.v_regime = tk.StringVar(value=es.REGIMES.get(cfg["regime"], es.REGIMES["simples"]))
        self.v_im = tk.StringVar(value=cfg["inscricao_municipal"])
        self.v_municipio = tk.StringVar(value=cfg["municipio"])
        self.v_uf = tk.StringVar(value=cfg["uf"])
        self.v_cod_ibge = tk.StringVar(value=cfg["codigo_municipio_ibge"])
        end = cfg["endereco"]
        self.v_end_cep = tk.StringVar(value=end["cep"])
        self.v_end_logradouro = tk.StringVar(value=end["logradouro"])
        self.v_end_numero = tk.StringVar(value=end["numero"])
        self.v_end_complemento = tk.StringVar(value=end["complemento"])
        self.v_end_bairro = tk.StringVar(value=end["bairro"])
        self.v_aliq_simples = tk.StringVar(value=f"{cfg['simples']['aliquota_mes']:.4f}".replace(".", ",") if cfg["simples"]["aliquota_mes"] else "")
        self.v_identificacao_padrao = tk.StringVar(
            value=es.MODOS_IDENTIFICACAO.get(cfg.get("identificacao_tomador_padrao", "documento"), es.MODOS_IDENTIFICACAO["documento"]))

        cartao = Cartao(corpo)
        cartao.pack(fill="x")
        g = cartao.corpo
        g.columnconfigure(0, weight=1)
        g.columnconfigure(1, weight=1)
        rotulo(g, "Regime tributário", 9, "bold", "suave").grid(row=0, column=0, sticky="w", pady=(0, 3), columnspan=2)
        ttk.Combobox(g, textvariable=self.v_regime, values=list(es.REGIMES.values()), state="readonly", width=26, font=F(10)).grid(
            row=1, column=0, sticky="w", columnspan=2, pady=(0, 10))
        campo_rotulado(g, 2, "Inscrição Municipal (IM)", Campo(g, self.v_im, largura=22), col=0, columnspan=1)
        campo_rotulado(g, 2, "Município e UF do prestador", self._linha_municipio(g), col=1, columnspan=1)
        self.f_simples = tk.Frame(g, bg=P.superficie)
        self.f_simples.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        rotulo(self.f_simples, "Alíquota do Simples do mês (%)", 9, "bold", "suave").pack(anchor="w")
        Campo(self.f_simples, self.v_aliq_simples, largura=10).pack(anchor="w", pady=(3, 0))
        rotulo(self.f_simples, "Tirada do PGDAS-D do mês da competência: muda a cada emissão de guia.", 9, cor="suave",
              largura=px(600)).pack(anchor="w", pady=(2, 0))
        rotulo(g, "Como identificar o tomador por padrão", 9, "bold", "suave").grid(row=7, column=0, columnspan=2, sticky="w", pady=(16, 3))
        ttk.Combobox(g, textvariable=self.v_identificacao_padrao, values=list(es.MODOS_IDENTIFICACAO.values()),
                    state="readonly", width=56, font=F(10)).grid(row=8, column=0, columnspan=2, sticky="w")
        rotulo(g, "Vale para os tomadores cadastrados como \"usar o padrão da empresa\". Cada tomador pode sobrepor.",
              9, cor="suave", largura=px(600)).grid(row=9, column=0, columnspan=2, sticky="w", pady=(2, 0))

        ui.secao(corpo, "Endereço do prestador (obrigatório na nota)").pack(anchor="w", pady=(16, 6))
        cartao_end = Cartao(corpo)
        cartao_end.pack(fill="x")
        ge = cartao_end.corpo
        ge.columnconfigure(0, weight=1)
        ge.columnconfigure(1, weight=1)
        campo_rotulado(ge, 0, "CEP", Campo(ge, self.v_end_cep, largura=12), col=0, columnspan=1)
        campo_rotulado(ge, 0, "Número", Campo(ge, self.v_end_numero, largura=12), col=1, columnspan=1)
        campo_rotulado(ge, 3, "Logradouro", Campo(ge, self.v_end_logradouro, largura=40))
        campo_rotulado(ge, 6, "Complemento", Campo(ge, self.v_end_complemento, largura=40))
        campo_rotulado(ge, 9, "Bairro", Campo(ge, self.v_end_bairro, largura=22), col=0, columnspan=1)
        campo_rotulado(ge, 9, "Código IBGE do município", Campo(ge, self.v_cod_ibge, largura=12), col=1, columnspan=1,
                       dica="Necessário pra nota (campo cMun). Busque em ibge.gov.br/explica/codigos-dos-municipios.")

        self.v_regime.trace_add("write", lambda *_: self._atualizar_regime())
        self._atualizar_regime()
        return f

    def _linha_municipio(self, g):
        linha = tk.Frame(g, bg=P.superficie)
        Campo(linha, self.v_municipio, largura=18).pack(side="left")
        Campo(linha, self.v_uf, largura=4).pack(side="left", padx=(6, 0))
        return linha

    def _atualizar_regime(self):
        chave = {v: k for k, v in es.REGIMES.items()}.get(self.v_regime.get(), "simples")
        if chave == "simples":
            self.f_simples.grid()
        else:
            self.f_simples.grid_remove()

    def _regime_chave(self) -> str:
        return {v: k for k, v in es.REGIMES.items()}.get(self.v_regime.get(), "simples")

    # ------------------------------------------------------------------ aba Perfis
    def _aba_perfis(self, pai):
        f = tk.Frame(pai, bg=P.fundo)
        cab = tk.Frame(f, bg=P.fundo)
        cab.pack(fill="x", pady=(0, 10))
        rotulo(cab, "Cada perfil tem seu próprio CTN, NBS, tributação e descrição. Empresas com um único tipo de serviço "
                    "precisam de só um perfil.", 10, cor="suave", largura=px(620)).pack(side="left", anchor="w")
        Botao(cab, "+  Novo perfil", self._novo_perfil, estilo="primario").pack(side="right", anchor="n")
        self.rol_perfis = Rolavel(f)
        self.rol_perfis.pack(fill="both", expand=True)
        self._lista_perfis()
        return f

    def _lista_perfis(self):
        corpo = self.rol_perfis.corpo
        for w in corpo.winfo_children():
            w.destroy()
        if not self.cfg["perfis"]:
            rotulo(corpo, "Nenhum perfil cadastrado ainda.", 10, cor="suave").pack(anchor="w", pady=(10, 0))
            return
        for p in self.cfg["perfis"]:
            c = Cartao(corpo, pad=12)
            c.pack(fill="x", pady=(0, 8))
            k = c.corpo
            k.columnconfigure(0, weight=1)
            topo = tk.Frame(k, bg=P.superficie)
            topo.grid(row=0, column=0, sticky="ew")
            rotulo(topo, p["nome"] or "(sem nome)", 12, "bold", "verde_escuro").pack(side="left")
            if p["id"] == self.cfg.get("perfil_padrao_id"):
                Chip(topo, "Padrão", "verde").pack(side="left", padx=(8, 0))
            if not p["ativo"]:
                Chip(topo, "Inativo", "neutro").pack(side="left", padx=(8, 0))
            rotulo(k, f"CTN {p['ctn'] or '—'} · NBS {p['nbs'] or '—'}", 9, cor="suave").grid(row=1, column=0, sticky="w", pady=(2, 8))
            bt = tk.Frame(k, bg=P.superficie)
            bt.grid(row=2, column=0, sticky="w")
            Botao(bt, "Editar", lambda pid=p["id"]: self._editar_perfil(pid), pady=6).pack(side="left")
            if p["id"] != self.cfg.get("perfil_padrao_id"):
                Botao(bt, "Tornar padrão", lambda pid=p["id"]: self._tornar_padrao(pid), pady=6).pack(side="left", padx=(8, 0))
            Botao(bt, "Excluir", lambda pid=p["id"]: self._excluir_perfil(pid), estilo="perigo", pady=6).pack(side="left", padx=(8, 0))

    def _novo_perfil(self):
        novo = es.perfil_padrao()
        d = DialogoPerfilServico(self, novo, self._regime_chave())
        self.wait_window(d)
        self.grab_set()
        if d.resultado:
            self.cfg["perfis"].append(d.resultado)
            if not self.cfg.get("perfil_padrao_id"):
                self.cfg["perfil_padrao_id"] = d.resultado["id"]
            self._lista_perfis()

    def _editar_perfil(self, perfil_id):
        atual = es.perfil_por_id(self.cfg, perfil_id)
        if not atual:
            return
        d = DialogoPerfilServico(self, dict(atual), self._regime_chave())
        self.wait_window(d)
        self.grab_set()
        if d.resultado:
            self.cfg["perfis"] = [d.resultado if p["id"] == perfil_id else p for p in self.cfg["perfis"]]
            self._lista_perfis()

    def _tornar_padrao(self, perfil_id):
        self.cfg["perfil_padrao_id"] = perfil_id
        self._lista_perfis()

    def _excluir_perfil(self, perfil_id):
        if len(self.cfg["perfis"]) <= 1:
            ui.avisar(self, "Pelo menos um perfil", "A empresa precisa de ao menos um perfil de serviço.")
            self.grab_set()
            return
        em_uso = [t["nome"] for t in self.cfg["tomadores"] if t.get("perfil_id") == perfil_id]
        if em_uso and not ui.perguntar(
                self, "Perfil em uso por tomadores",
                f"{', '.join(em_uso)} usa(m) este perfil e passará(ão) a usar o perfil padrão da empresa. Excluir mesmo assim?",
                sim="Excluir", nao="Cancelar", perigo=True):
            self.grab_set()
            return
        self.cfg["perfis"] = [p for p in self.cfg["perfis"] if p["id"] != perfil_id]
        for t in self.cfg["tomadores"]:
            if t.get("perfil_id") == perfil_id:
                t["perfil_id"] = None
        if self.cfg.get("perfil_padrao_id") == perfil_id:
            self.cfg["perfil_padrao_id"] = self.cfg["perfis"][0]["id"]
        self._lista_perfis()

    # ------------------------------------------------------------------ aba Tomadores
    def _aba_tomadores(self, pai):
        f = tk.Frame(pai, bg=P.fundo)
        cab = tk.Frame(f, bg=P.fundo)
        cab.pack(fill="x", pady=(0, 10))
        rotulo(cab, "Quando uma nota bater com o documento, nome ou endereço de um tomador cadastrado, o perfil dele "
                    "é usado sem perguntar.", 10, cor="suave", largura=px(620)).pack(side="left", anchor="w")
        Botao(cab, "+  Novo tomador", self._novo_tomador, estilo="primario").pack(side="right", anchor="n")
        self.rol_tomadores = Rolavel(f)
        self.rol_tomadores.pack(fill="both", expand=True)
        self._lista_tomadores()
        return f

    def _lista_tomadores(self):
        corpo = self.rol_tomadores.corpo
        for w in corpo.winfo_children():
            w.destroy()
        if not self.cfg["tomadores"]:
            rotulo(corpo, "Nenhum tomador recorrente cadastrado. Sem isso, a emissão pergunta o perfil nota a nota.",
                  10, cor="suave", largura=px(600)).pack(anchor="w", pady=(10, 0))
            return
        nomes_perfis = {p["id"]: p["nome"] for p in self.cfg["perfis"]}
        for t in self.cfg["tomadores"]:
            c = Cartao(corpo, pad=12)
            c.pack(fill="x", pady=(0, 8))
            k = c.corpo
            k.columnconfigure(0, weight=1)
            topo = tk.Frame(k, bg=P.superficie)
            topo.grid(row=0, column=0, sticky="ew")
            rotulo(topo, t["nome"] or "(sem nome)", 12, "bold", "verde_escuro").pack(side="left")
            if not t.get("ativo", True):
                Chip(topo, "Inativo", "neutro").pack(side="left", padx=(8, 0))
            perfil_nome = nomes_perfis.get(t.get("perfil_id"), "perfil padrão da empresa")
            identificacao = es.modo_identificacao_efetivo(self.cfg, t)
            referencia = es.endereco_completo(t) if identificacao == "endereco" else t["documento"]
            rotulo(k, f"{referencia or '—'} · perfil: {perfil_nome}", 9, cor="suave").grid(
                row=1, column=0, sticky="w", pady=(2, 8))
            bt = tk.Frame(k, bg=P.superficie)
            bt.grid(row=2, column=0, sticky="w")
            Botao(bt, "Editar", lambda tid=t["id"]: self._editar_tomador(tid), pady=6).pack(side="left")
            Botao(bt, "Excluir", lambda tid=t["id"]: self._excluir_tomador(tid), estilo="perigo", pady=6).pack(side="left", padx=(8, 0))

    def _novo_tomador(self):
        d = DialogoTomador(self, es.tomador_padrao(), self.cfg["perfis"], self.cfg.get("identificacao_tomador_padrao", "documento"))
        self.wait_window(d)
        self.grab_set()
        if d.resultado:
            self.cfg["tomadores"].append(d.resultado)
            self._lista_tomadores()

    def _editar_tomador(self, tomador_id):
        atual = next((t for t in self.cfg["tomadores"] if t["id"] == tomador_id), None)
        if not atual:
            return
        d = DialogoTomador(self, dict(atual), self.cfg["perfis"], self.cfg.get("identificacao_tomador_padrao", "documento"))
        self.wait_window(d)
        self.grab_set()
        if d.resultado:
            self.cfg["tomadores"] = [d.resultado if t["id"] == tomador_id else t for t in self.cfg["tomadores"]]
            self._lista_tomadores()

    def _excluir_tomador(self, tomador_id):
        self.cfg["tomadores"] = [t for t in self.cfg["tomadores"] if t["id"] != tomador_id]
        self._lista_tomadores()

    # ------------------------------------------------------------------ salvar
    def _salvar(self):
        im, municipio = self.v_im.get().strip(), self.v_municipio.get().strip()
        if not im or not municipio:
            self.l_erro.config(text="Informe a Inscrição Municipal e o município do prestador.")
            self.v_aba.set("empresa")
            self._trocar_aba()
            return
        try:
            aliq_simples = grafico.parse_brl(self.v_aliq_simples.get()) / 100 if self.v_aliq_simples.get().strip() else 0.0
        except ValueError as e:
            self.l_erro.config(text=str(e))
            self.v_aba.set("empresa")
            self._trocar_aba()
            return
        nome_para_identificacao = {v: k for k, v in es.MODOS_IDENTIFICACAO.items()}
        self.cfg.update({
            "regime": self._regime_chave(), "inscricao_municipal": im, "municipio": municipio,
            "uf": self.v_uf.get().strip().upper(), "codigo_municipio_ibge": self.v_cod_ibge.get().strip(),
            "endereco": {"cep": self.v_end_cep.get().strip(), "logradouro": self.v_end_logradouro.get().strip(),
                        "numero": self.v_end_numero.get().strip(), "complemento": self.v_end_complemento.get().strip(),
                        "bairro": self.v_end_bairro.get().strip()},
            "simples": {"aliquota_mes": aliq_simples},
            "identificacao_tomador_padrao": nome_para_identificacao.get(self.v_identificacao_padrao.get(), "documento"),
        })
        self.cfg = es.migrar(self.cfg)
        real = next((e for e in self.store.empresas if e["id"] == self.emp["id"]), None)
        if real is None:
            self.l_erro.config(text="Esta empresa não existe mais.")
            return
        real["emissao"] = self.cfg
        try:
            self.store.salvar_empresa(real)
        except ErroAdge as e:
            self.l_erro.config(text=str(e))
            return
        self.emp["emissao"] = self.cfg
        self.salvou = True
        self.destroy()
