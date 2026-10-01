"""Janelas da NF-e: avisos ao ligar a busca e a ciência da operação, e as perguntas sobre o histórico guardado."""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from . import ui
from .nfe_cache import HistoricoNFe, formatar_espera
from .ui import P, Botao, Cartao, Interruptor, Modal, px, rotulo

TEXTO_LIMITE = ("O limite de consultas é da própria SEFAZ (Ambiente Nacional da NF-e), e não do sistema da Adge: sem nota nova, "
                "ela só libera outra consulta depois de cerca de 1 hora.")


def _bloco(pai, titulo, linhas, tom=None, largura=540):
    """Cartão com um título e parágrafos (ou itens com ‘•’)."""
    larg_c = px(largura + 28)    # o Cartao é um Canvas: sem largura própria ele corta o texto na largura padrão
    c = Cartao(pai, fundo=tom, borda=tom, pad=14, width=larg_c) if tom else Cartao(pai, pad=14, width=larg_c)
    c.pack(fill="x", pady=(0, 8))
    cor = {"verde_claro": "verde_escuro", "aviso_fundo": "aviso_texto"}.get(tom, "suave")
    if titulo:
        rotulo(c.corpo, titulo, 10, "bold", cor if tom else "texto").pack(anchor="w")
    for l in linhas:
        rotulo(c.corpo, l, 10, cor=cor, largura=px(largura)).pack(anchor="w", pady=(4, 0))
    return c


# ============================================================================= ligar a busca de NF-e
class DialogoAtivarNFe(Modal):
    """Aviso ao ligar a NF-e na empresa. resultado = True se a pessoa confirmou."""

    def __init__(self, pai):
        super().__init__(pai, "Ativar a busca de NF-e")
        self.resultado = False
        ui.titulo(self, "Ativar a busca de NF-e (modelo 55)?",
                  "Antes de ligar, vale saber como isso funciona.").pack(anchor="w", pady=(0, 10))
        _bloco(self, "O que muda", [
            "• Além das NFS-e, o programa passa a consultar as NF-e da empresa no Ambiente Nacional da SEFAZ, com o mesmo certificado A1: "
            "notas de venda, de compra e devoluções.",
            "• As NF-e entram no mesmo relatório: totais, saldo, gráfico, planilha e análise de regimes. Você marca o que quer considerar."])
        _bloco(self, "Limites da SEFAZ", [
            "• " + TEXTO_LIMITE,
            "• O programa mostra um contador. Enquanto a SEFAZ não libera, ele usa o histórico guardado no computador.",
            "• A SEFAZ entrega por sequência (NSU) e guarda só alguns meses; por isso o que ela devolve fica guardado numa pasta do "
            "sistema (você escolhe manter, trocar a pasta ou apagar)."], tom="aviso_fundo")
        _bloco(self, "Notas de compra sem Ciência da Operação", [
            "A SEFAZ entrega só o resumo (sem CFOP nem itens). Elas ficam separadas, em planilha à parte, e só entram nos totais se você marcar. "
            "Para receber o XML completo é preciso registrar a Ciência da Operação, que é uma opção à parte e também começa desligada."])
        rotulo(self, "Ligar a busca só lê informações: não envia nada à SEFAZ.", 10, "bold", "verde_escuro").pack(anchor="w", pady=(2, 0))
        lin = tk.Frame(self, bg=P.fundo)
        lin.pack(fill="x", pady=(14, 0))
        self.b_ok = Botao(lin, "Ativar a busca de NF-e", lambda: self._fim(True), estilo="primario")
        self.b_ok.pack(side="right")
        self.b_nao = Botao(lin, "Agora não", lambda: self._fim(False))
        self.b_nao.pack(side="right", padx=(0, 8))
        self.protocol("WM_DELETE_WINDOW", lambda: self._fim(False))
        self.bind("<Escape>", lambda *_: self._fim(False))
        self.mostrar()

    def _fim(self, v):
        self.resultado = v
        self.destroy()


# ============================================================================= ligar a ciência
class DialogoAtivarCiencia(Modal):
    """Aviso ao ligar a Ciência da Operação automática. resultado = True só se a pessoa marcou a confirmação e ativou."""

    def __init__(self, pai):
        super().__init__(pai, "Ciência da Operação automática")
        self.resultado = False
        self.v_ok = tk.BooleanVar(value=False)
        ui.titulo(self, "Registrar a Ciência da Operação automaticamente?",
                  "É um ato feito em nome da empresa. Leia com atenção.").pack(anchor="w", pady=(0, 10))
        _bloco(self, "O que o programa vai fazer", [
            "Enviar, assinado com o certificado A1 da empresa, o evento de Ciência da Operação (210210) das NF-e de compra do mês consultado "
            "que chegaram só em resumo. A SEFAZ então libera o XML completo."], tom="verde_claro")
        _bloco(self, "Riscos, de forma direta", [
            "• O evento fica registrado no Ambiente Nacional, em nome da empresa, e o emitente da nota pode vê-lo. Não dá para desfazer; só dá para complementar com outra manifestação.",
            "• Se a nota for indevida (fraude, ou CNPJ usado por engano), a ciência registra que a empresa tomou conhecimento dela. Ainda é possível registrar o Desconhecimento depois, mas não ligue isso para quem recebe notas que você não confia.",
            "• Todas as NF-e de compra do mês consultado, ainda sem ciência, recebem o evento. Não há escolha nota a nota.",
            "• A empresa, ou o contador responsável, precisa ter autorizado esse procedimento.",
            "• O programa envia somente a Ciência. Nunca envia Confirmação da Operação, Desconhecimento nem Operação não realizada."],
               tom="aviso_fundo")
        _bloco(self, "Isso não é um risco fiscal por si só", [
            "A Ciência não confirma nem recusa a operação, não gera imposto, não cria nem anula crédito e não altera a escrituração. "
            "É só o registro de que a empresa tomou conhecimento da nota. Mesmo assim, por ser um ato em nome dela, fica desligada até você confirmar."])
        Interruptor(self, "Entendi os riscos e a empresa autorizou esse registro", self.v_ok, self._atualiza, tam=10).pack(anchor="w", pady=(4, 0))
        lin = tk.Frame(self, bg=P.fundo)
        lin.pack(fill="x", pady=(14, 0))
        self.b_ok = Botao(lin, "Ativar a ciência automática", lambda: self._fim(True), estilo="primario")
        self.b_ok.pack(side="right")
        self.b_nao = Botao(lin, "Cancelar", lambda: self._fim(False))
        self.b_nao.pack(side="right", padx=(0, 8))
        self.b_ok.config(state="disabled")
        self.protocol("WM_DELETE_WINDOW", lambda: self._fim(False))
        self.bind("<Escape>", lambda *_: self._fim(False))
        self.mostrar()

    def _atualiza(self):
        self.b_ok.config(state="normal" if self.v_ok.get() else "disabled")

    def _fim(self, v):
        self.resultado = bool(v and self.v_ok.get())
        self.destroy()


# ============================================================================= histórico guardado automaticamente
class DialogoUsarHistorico(Modal):
    """Na consulta seguinte a um fechamento sem resposta: usar o histórico guardado ou consultar de novo.
    resultado = 'usar', 'nova' ou None (fechou: a busca não segue)."""

    def __init__(self, pai, hist: HistoricoNFe):
        super().__init__(pai, "Histórico de NF-e guardado")
        self.hist, self.resultado = hist, None
        n = hist.quantidade()
        ui.titulo(self, "Há um histórico de NF-e guardado",
                  hist.emp.get("nome", "")).pack(anchor="w", pady=(0, 10))
        _bloco(self, None, [
            f"O sistema guardou automaticamente o histórico de NF-e referente a {hist.periodo_texto()} ({n} documento(s)) "
            "na consulta anterior desta empresa.",
            "Deseja usar esse histórico ou fazer uma nova consulta à SEFAZ?"])
        c = Cartao(self, fundo="aviso_fundo", borda="aviso_fundo", pad=14, width=px(568))
        c.pack(fill="x", pady=(0, 8))
        self.l_timer = rotulo(c.corpo, "", 10, "bold", "aviso_texto", largura=px(540))
        self.l_timer.pack(anchor="w")
        rotulo(c.corpo, TEXTO_LIMITE, 9, cor="aviso_texto", largura=px(540)).pack(anchor="w", pady=(4, 0))
        lin = tk.Frame(self, bg=P.fundo)
        lin.pack(fill="x", pady=(10, 0))
        self.b_nova = Botao(lin, "Nova consulta", lambda: self._fim("nova"))
        self.b_nova.pack(side="right")
        self.b_usar = Botao(lin, "Usar o histórico guardado", lambda: self._fim("usar"), estilo="primario")
        self.b_usar.pack(side="right", padx=(0, 8))
        self.protocol("WM_DELETE_WINDOW", lambda: self._fim(None))
        self.bind("<Escape>", lambda *_: self._fim(None))
        self._tic()
        self.mostrar()

    def _tic(self):
        if not self.winfo_exists():
            return
        resto = self.hist.bloqueio_restante()
        if resto is None:
            self.l_timer.config(text="A SEFAZ já liberou uma nova consulta.")
            self.b_nova.config(state="normal")
        else:
            self.l_timer.config(text=f"Nova consulta liberada em {formatar_espera(resto)} (às {self.hist.liberado_as():%H:%M}).")
            self.b_nova.config(state="disabled")
        self.after(1000, self._tic)

    def _fim(self, v):
        self.resultado = v
        self.destroy()


class DialogoManterHistorico(Modal):
    """Depois de cada consulta com NF-e: explica o limite da SEFAZ e pergunta se o histórico fica guardado no sistema.
    resultado = ('manter', None) | ('manter', pasta) | ('descartar', None) | None (fechou sem responder: fica guardado até a próxima consulta)."""

    def __init__(self, pai, hist: HistoricoNFe, novos: int = 0):
        super().__init__(pai, "Guardar o histórico de NF-e?")
        self.hist, self.resultado = hist, None
        ui.titulo(self, "Guardar o histórico de NF-e deste computador?",
                  hist.emp.get("nome", "")).pack(anchor="w", pady=(0, 10))
        _bloco(self, "Por que perguntamos", [
            "• " + TEXTO_LIMITE,
            "• A SEFAZ entrega as NF-e por sequência e guarda só alguns meses. Guardar o que ela devolveu permite refazer o relatório "
            "enquanto ela bloqueia novas consultas e consultar meses que ela já não devolve.",
            f"• {hist.quantidade()} documento(s) estão guardados agora" + (f" ({novos} novo(s) nesta consulta)." if novos else ".")])
        padrao = "pasta de histórico do sistema" if hist.pasta_padrao else "pasta escolhida"
        c = Cartao(self, fundo="verde_claro", borda="verde_claro", pad=14, width=px(568))
        c.pack(fill="x", pady=(0, 8))
        rotulo(c.corpo, f"Local ({padrao}):", 10, "bold", "verde_escuro").pack(anchor="w")
        rotulo(c.corpo, str(hist.pasta_docs), 9, cor="verde_escuro", largura=px(540)).pack(anchor="w", pady=(2, 0))
        rotulo(self, "Se você fechar esta janela sem escolher, o histórico fica guardado no sistema até a próxima consulta desta empresa.",
               9, cor="suave", largura=px(560)).pack(anchor="w", pady=(2, 0))
        lin = tk.Frame(self, bg=P.fundo)
        lin.pack(fill="x", pady=(14, 0))
        Botao(lin, "Não guardar", lambda: self._fim(("descartar", None))).pack(side="right")
        Botao(lin, "Escolher pasta...", self._escolher).pack(side="right", padx=(0, 8))
        Botao(lin, "Sim, guardar", lambda: self._fim(("manter", None)), estilo="primario").pack(side="right", padx=(0, 8))
        self.protocol("WM_DELETE_WINDOW", lambda: self._fim(None))
        self.bind("<Escape>", lambda *_: self._fim(None))
        self.mostrar()

    def _escolher(self):
        base = str(self.hist.pasta_docs.parent) if self.hist.pasta_docs.parent.is_dir() else str(Path.home())
        c = filedialog.askdirectory(parent=self, title="Escolha a pasta onde guardar o histórico de NF-e", initialdir=base)
        if c:
            self._fim(("manter", c))

    def _fim(self, v):
        self.resultado = v
        self.destroy()
