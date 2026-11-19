"""Tela de emissão de notas: lançar (manual, planilha ou documento do cliente) e conferir antes
de transmitir. Aberta pelo botão "Emitir Notas" do cartão da empresa (ver app.py), ao lado do
botão "Configurar para Emissão de Notas" da tela de configuração (Dev A).

A transmissão de verdade ainda não está pronta (`emissao/transmissao.py`, `emissao/assinatura.py`
e `emissao/dps.montar_xml` aguardam a pesquisa da API) — por isso o botão "Transmitir" fica
desligado e avisa o motivo, mas todo o lançamento e a prévia já funcionam de ponta a ponta."""
import datetime as dt
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from . import ui
from .core import ErroAdge
from .emissao import importador_documento as impdoc
from .emissao import planilha_emissao as pe
from .emissao import previa, regras
from .emissao.lancamento import Lancamento
from .store import Armazenamento
from .ui import P, Botao, Campo, Cartao, Modal, Segmentado, F, px, rotulo

STATUS_TEXTO = {previa.PRONTO: "Pronto", previa.PRECISA_PERFIL: "Precisa de perfil", previa.EXCLUIDO: "Excluído"}
COLUNAS = (("tomador", "Tomador", 220, "w"), ("documento", "Documento", 130, "w"), ("valor", "Valor", 100, "e"),
           ("competencia", "Competência", 100, "w"), ("perfil", "Perfil", 180, "w"), ("status", "Situação", 140, "w"))


def moeda(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _mes_atual() -> str:
    hoje = dt.date.today()
    return f"{hoje.year:04d}-{hoje.month:02d}"


class DialogoEmissao(Modal):
    def __init__(self, pai, store: Armazenamento, emp: dict):
        super().__init__(pai, f"Emitir notas — {emp['nome']}", margem=22)
        self.store, self.emp = store, dict(emp)
        self.emissao_cfg = self.emp.get("emissao") or {}
        self.lancamentos = []
        self.itens = []
        self.resizable(True, True)
        self._montar()
        tela_h = self.winfo_screenheight()
        self.geometry(f"{px(980)}x{min(px(760), tela_h - px(90))}")
        self.minsize(px(820), px(560))
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda *_: self.destroy())
        self.mostrar()

    # ------------------------------------------------------------------ montagem
    def _montar(self):
        ui.titulo(self, f"Emitir notas — {self.emp['nome']}",
                  "Lance as notas do mês e confira tudo antes de transmitir.").pack(anchor="w", pady=(0, 10))
        if not self.emissao_cfg.get("perfis"):
            rotulo(self, 'Esta empresa ainda não tem nenhum "perfil de serviço" configurado. '
                        'Abra "Configurar para Emissão de Notas" no cartão da empresa primeiro.',
                  10, cor="erro", largura=px(880)).pack(anchor="w", pady=(0, 10))

        self.v_aba = tk.StringVar(value="manual")
        Segmentado(self, [("manual", "Digitar"), ("planilha", "Planilha"), ("documento", "Documento do cliente")],
                  self.v_aba, self._trocar_aba).pack(anchor="w", pady=(0, 10))
        self.area = tk.Frame(self, bg=P.fundo)
        self.area.pack(fill="x")
        self.f_manual = self._aba_manual(self.area)
        self.f_planilha = self._aba_planilha(self.area)
        self.f_documento = self._aba_documento(self.area)
        self.f_manual.pack(fill="x")

        ui.secao(self, "Prévia — nada é transmitido sem confirmar aqui").pack(anchor="w", pady=(14, 6))
        self._montar_tabela()

        rodape = tk.Frame(self, bg=P.fundo)
        rodape.pack(fill="x", pady=(10, 0))
        Botao(rodape, "Fechar", self.destroy).pack(side="right")
        Botao(rodape, "Excluir selecionada(s)", self._excluir_selecao).pack(side="right", padx=(0, 8))
        Botao(rodape, "Definir perfil da selecionada", self._definir_perfil, estilo="secundario").pack(side="right", padx=(0, 8))
        self.b_transmitir = Botao(rodape, "Transmitir notas prontas", self._transmitir, estilo="primario")
        self.b_transmitir.pack(side="left")
        self.b_transmitir.configure(state="disabled")
        rotulo(rodape, "Transmissão real ainda não disponível nesta versão (aguardando a pesquisa da API).",
              9, cor="suave").pack(side="left", padx=(10, 0))

    def _trocar_aba(self):
        abas = {"manual": self.f_manual, "planilha": self.f_planilha, "documento": self.f_documento}
        for nome, f in abas.items():
            (f.pack(fill="x") if nome == self.v_aba.get() else f.pack_forget())

    # ------------------------------------------------------------------ aba: digitar
    def _aba_manual(self, pai):
        f = Cartao(pai)
        c = f.corpo
        v = lambda x="": tk.StringVar(value=x)
        self.v_nome, self.v_doc, self.v_end = v(), v(), v()
        self.v_valor, self.v_comp, self.v_data, self.v_obs = v(), v(_mes_atual()), v(), v()
        linhas = [("Tomador (nome)", self.v_nome), ("Documento (CPF ou CNPJ)", self.v_doc), ("Endereço", self.v_end),
                  ("Valor", self.v_valor), ("Competência (AAAA-MM)", self.v_comp),
                  ("Data da prestação (opcional)", self.v_data), ("Observações", self.v_obs)]
        for r, (rot, var) in enumerate(linhas):
            rotulo(c, rot, 10, cor="suave").grid(row=r, column=0, sticky="w", pady=4, padx=(0, 10))
            Campo(c, var, largura=34).grid(row=r, column=1, sticky="w", pady=4)
        Botao(c, "Adicionar à prévia", self._adicionar_manual, estilo="primario").grid(
            row=len(linhas), column=1, sticky="w", pady=(10, 0))
        return f

    def _adicionar_manual(self):
        try:
            lanc = Lancamento(tomador_nome=self.v_nome.get(), tomador_documento=self.v_doc.get(),
                              endereco=self.v_end.get(), valor=pe.valor_numerico(self.v_valor.get()),
                              competencia=self.v_comp.get().strip(), data_prestacao=self.v_data.get().strip(),
                              observacoes=self.v_obs.get().strip(), origem="manual")
        except ErroAdge as e:
            ui.erro(self, "Não consegui adicionar", str(e))
            return
        erros = lanc.validar()
        if erros:
            ui.erro(self, "Confira os dados", "\n".join(erros))
            return
        self.lancamentos.append(lanc)
        for var in (self.v_nome, self.v_doc, self.v_end, self.v_valor, self.v_data, self.v_obs):
            var.set("")
        self._atualizar_previa()

    # ------------------------------------------------------------------ aba: planilha
    def _aba_planilha(self, pai):
        f = Cartao(pai)
        c = f.corpo
        rotulo(c, "Uma linha por nota. Baixe o modelo, preencha e importe de volta.", 10, cor="suave",
              largura=px(700)).grid(row=0, column=0, sticky="w", pady=(0, 10))
        linha = tk.Frame(c, bg=P.superficie)
        linha.grid(row=1, column=0, sticky="w")
        Botao(linha, "Baixar modelo (.xlsx)", self._baixar_modelo).pack(side="left")
        Botao(linha, "Importar planilha preenchida", self._importar_planilha, estilo="primario").pack(
            side="left", padx=(8, 0))
        return f

    def _baixar_modelo(self):
        caminho = filedialog.asksaveasfilename(parent=self, defaultextension=".xlsx",
                                               initialfile="Modelo de lançamentos.xlsx",
                                               filetypes=[("Planilha Excel", "*.xlsx")])
        if not caminho:
            return
        pe.gerar_modelo_xlsx(caminho)
        ui.informar(self, "Modelo salvo", f"Modelo salvo em:\n{caminho}")
        ui.abrir_pasta(Path(caminho).parent)

    def _importar_planilha(self):
        caminho = filedialog.askopenfilename(parent=self, filetypes=[("Planilha Excel", "*.xlsx")])
        if not caminho:
            return
        try:
            novos, erros = pe.importar_xlsx(caminho)
        except ErroAdge as e:
            ui.erro(self, "Não consegui importar", str(e))
            return
        self.lancamentos.extend(novos)
        self._atualizar_previa()
        if erros:
            ui.avisar(self, f"{len(novos)} lançamento(s) importado(s), com avisos", "\n".join(erros))
        else:
            ui.informar(self, "Importado", f"{len(novos)} lançamento(s) adicionado(s) à prévia.")

    # ------------------------------------------------------------------ aba: documento do cliente
    def _aba_documento(self, pai):
        f = Cartao(pai)
        c = f.corpo
        rotulo(c, "Qualquer documento do cliente com uma tabela (PDF, .xlsx ou .csv): você liga cada "
                  "coluna a um campo na próxima tela.", 10, cor="suave", largura=px(700)).grid(
            row=0, column=0, sticky="w", pady=(0, 10))
        Botao(c, "Importar documento...", self._importar_documento, estilo="primario").grid(row=1, column=0, sticky="w")
        return f

    def _importar_documento(self):
        caminho = filedialog.askopenfilename(
            parent=self, filetypes=[("Documentos suportados", "*.pdf *.xlsx *.xlsm *.csv")])
        if not caminho:
            return
        try:
            cabecalho, linhas = impdoc.extrair_tabela(caminho)
        except ErroAdge as e:
            ui.erro(self, "Não consegui ler o documento", str(e))
            return
        if not linhas:
            ui.avisar(self, "Nada para importar", "Não encontrei nenhuma linha de dados nessa tabela.")
            return
        mapeamento_sugerido = impdoc.sugerir_mapeamento(cabecalho)
        DialogoMapeamentoColunas(self, cabecalho, mapeamento_sugerido, lambda m: self._concluir_importacao_documento(
            cabecalho, linhas, m))

    def _concluir_importacao_documento(self, cabecalho, linhas, mapeamento):
        novos, erros = impdoc.construir_lancamentos(cabecalho, linhas, mapeamento, competencia_padrao=_mes_atual())
        for l in novos:
            l.origem = "documento"
        self.lancamentos.extend(novos)
        self._atualizar_previa()
        if erros:
            ui.avisar(self, f"{len(novos)} lançamento(s) importado(s), com avisos", "\n".join(erros))
        else:
            ui.informar(self, "Importado", f"{len(novos)} lançamento(s) adicionado(s) à prévia.")

    # ------------------------------------------------------------------ prévia
    def _montar_tabela(self):
        corpo = tk.Frame(self, bg=P.fundo)
        corpo.pack(fill="both", expand=True)
        cols = [c for c, *_ in COLUNAS]
        self.tv = ttk.Treeview(corpo, columns=cols, show="headings", height=10, selectmode="extended")
        for c, t, w, an in COLUNAS:
            self.tv.heading(c, text=t)
            self.tv.column(c, width=px(w), anchor=an)
        sb = ttk.Scrollbar(corpo, orient="vertical", command=self.tv.yview, style="Adge.Vertical.TScrollbar")
        self.tv.configure(yscrollcommand=sb.set)
        self.tv.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.tv.tag_configure("pronto", foreground=P.pos_texto)
        self.tv.tag_configure("precisa_perfil", foreground=P.aviso_texto)
        self.tv.tag_configure("excluido", foreground=P.suave)

    def _atualizar_previa(self):
        self.itens = previa.preparar_previa(self.emissao_cfg, self.lancamentos)
        self.tv.delete(*self.tv.get_children())
        for i, item in enumerate(self.itens):
            l = item.lancamento
            nome_perfil = next((p["nome"] for p in self.emissao_cfg.get("perfis", []) if p["id"] == item.perfil_id), "—")
            situacao = STATUS_TEXTO[item.status] + (f" ({'; '.join(item.erros)})" if item.erros else "")
            self.tv.insert("", "end", iid=str(i), tags=(item.status,),
                           values=(l.tomador_nome, l.tomador_documento, moeda(l.valor), l.competencia,
                                   nome_perfil, situacao))

    def _selecao(self):
        return [self.itens[int(iid)] for iid in self.tv.selection()]

    # ------------------------------------------------------------------ ações sobre a prévia
    def _definir_perfil(self):
        sel = self._selecao()
        if not sel:
            ui.avisar(self, "Nada selecionado", "Selecione uma nota na prévia primeiro.")
            return
        perfis = previa.perfis_ativos(self.emissao_cfg)
        if not perfis:
            ui.avisar(self, "Sem perfis", "Esta empresa ainda não tem nenhum perfil de serviço ativo.")
            return

        def aplicar(perfil_id, salvar_regra):
            for item in sel:
                novo_tomador = previa.aplicar_perfil(item, perfil_id, self.emissao_cfg, salvar_regra=salvar_regra)
                if novo_tomador:
                    self.emissao_cfg.setdefault("tomadores", []).append(novo_tomador)
            if salvar_regra:
                self.emp["emissao"] = self.emissao_cfg
                self.store.salvar_empresa(self.emp)
            self._atualizar_previa()

        DialogoEscolherPerfil(self, perfis, salvar_regra_disponivel=len(sel) == 1, ao_confirmar=aplicar)

    def _excluir_selecao(self):
        sel = self._selecao()
        if not sel:
            return
        if not ui.perguntar(self, "Excluir da emissão?", f"{len(sel)} nota(s) não vão ser emitidas."):
            return
        for item in sel:
            previa.excluir(item)
        self._atualizar_previa()

    def _transmitir(self):
        ui.avisar(self, "Transmissão ainda não disponível",
                 "O envio de verdade (assinatura e POST /nfse) ainda não foi implementado nesta "
                 "versão - está aguardando a pesquisa oficial da API. A prévia já está pronta para "
                 "quando essa parte for concluída.")


class DialogoMapeamentoColunas(Modal):
    """Liga cada coluna do documento a um campo do lançamento. `ao_confirmar(mapeamento)` recebe
    {indice: campo} só com as colunas que o usuário deixou mapeadas."""

    def __init__(self, pai, cabecalho, mapeamento_sugerido, ao_confirmar):
        super().__init__(pai, "Ligar colunas do documento")
        self.ao_confirmar = ao_confirmar
        ui.titulo(self, "Ligar colunas do documento",
                  "Cada coluna do documento vira um campo do lançamento.").pack(anchor="w", pady=(0, 10))
        c = Cartao(self).corpo
        self.vars = []
        opcoes = list(impdoc.CAMPOS)
        for i, titulo_coluna in enumerate(cabecalho):
            rotulo(c, titulo_coluna or f"Coluna {i + 1}", 10).grid(row=i, column=0, sticky="w", pady=4, padx=(0, 14))
            var = tk.StringVar(value=mapeamento_sugerido.get(i, "ignorar"))
            cb = ttk.Combobox(c, textvariable=var, values=opcoes, state="readonly", width=20)
            cb.grid(row=i, column=1, sticky="w", pady=4)
            self.vars.append(var)
        rodape = tk.Frame(self, bg=P.fundo)
        rodape.pack(fill="x", pady=(14, 0))
        Botao(rodape, "Cancelar", self.destroy).pack(side="right")
        Botao(rodape, "Importar", self._confirmar, estilo="primario").pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda *_: self.destroy())
        self.mostrar()

    def _confirmar(self):
        mapeamento = {i: v.get() for i, v in enumerate(self.vars) if v.get() != "ignorar"}
        self.destroy()
        self.ao_confirmar(mapeamento)


class DialogoEscolherPerfil(Modal):
    def __init__(self, pai, perfis, salvar_regra_disponivel, ao_confirmar):
        super().__init__(pai, "Escolher perfil de serviço")
        self.ao_confirmar = ao_confirmar
        rotulo(self, "Perfil de serviço", 10, cor="suave").pack(anchor="w")
        self.v_perfil = tk.StringVar(value=perfis[0]["id"])
        nomes = {p["nome"]: p["id"] for p in perfis}
        self.v_nome = tk.StringVar(value=perfis[0]["nome"])
        cb = ttk.Combobox(self, textvariable=self.v_nome, values=list(nomes), state="readonly", width=34)
        cb.pack(anchor="w", pady=(4, 10))
        self._nomes = nomes
        self.v_salvar = tk.BooleanVar(value=False)
        if salvar_regra_disponivel:
            tk.Checkbutton(self, text="Salvar como regra para este tomador (próximas notas aplicam sozinho)",
                          variable=self.v_salvar, bg=P.fundo, fg=P.texto, selectcolor=P.campo,
                          activebackground=P.fundo, font=F(9)).pack(anchor="w")
        rodape = tk.Frame(self, bg=P.fundo)
        rodape.pack(fill="x", pady=(14, 0))
        Botao(rodape, "Cancelar", self.destroy).pack(side="right")
        Botao(rodape, "Confirmar", self._confirmar, estilo="primario").pack(side="right", padx=(0, 8))
        self.bind("<Escape>", lambda *_: self.destroy())
        self.mostrar()

    def _confirmar(self):
        perfil_id = self._nomes[self.v_nome.get()]
        salvar = self.v_salvar.get()
        self.destroy()
        self.ao_confirmar(perfil_id, salvar)
