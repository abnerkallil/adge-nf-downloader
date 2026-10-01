"""Teste de fumaça da interface: abre as janelas, simula uma busca com um ADN falso e confere os totais.
Roda no Windows do GitHub Actions (e em Linux com xvfb). Sai com código != 0 se algo falhar."""
import pathlib
import sys
import tempfile
import time
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from adge_nf import app as A  # noqa: E402
from adge_nf import core  # noqa: E402
from adge_nf.store import Armazenamento  # noqa: E402
from fixtures import SessaoFalsa, item, xml_nfse  # noqa: E402

CNPJ = "11222333000181"
mensagens = []
A.messagebox.showerror = lambda *a, **k: mensagens.append(("erro", a))
A.messagebox.showwarning = lambda *a, **k: mensagens.append(("aviso", a))
A.messagebox.askyesno = lambda *a, **k: (mensagens.append(("pergunta", a)) or True)
A.abrir_pasta = lambda *_: None
A.messagebox.showinfo = lambda *a, **k: mensagens.append(("info", a))


class CofreFalso:
    d = {}
    def get_password(self, s, u): return self.d.get((s, u))
    def set_password(self, s, u, p): self.d[(s, u)] = p
    def delete_password(self, s, u): self.d.pop((s, u), None)


def esperar(cond, app, segundos=10):
    fim = time.time() + segundos
    while time.time() < fim:
        app.update()
        if cond():
            return True
        time.sleep(0.05)
    return False


def passo(nome):
    print("ok -", nome, flush=True)


def principal():
    with tempfile.TemporaryDirectory() as t:
        t = pathlib.Path(t)
        (t / "cli").mkdir()
        pfx = t / "c.pfx"
        pfx.write_bytes(b"x")
        store = Armazenamento(t / "dados", keyring_mod=CofreFalso())
        store.preferencias["verificar_atualizacao"] = False  # o teste não conversa com o GitHub de verdade
        app = A.App(store)
        app.update()
        passo("janela principal abre")

        # --- cadastro de empresa
        core.ler_certificado = lambda *_: {"cnpj": CNPJ, "nome": "EMPRESA TESTE", "valido_ate": __import__("datetime").date(2099, 1, 1)}
        d = A.DialogoEmpresa(app, store)
        d.update()
        d.v_pfx.set(str(pfx)); d.v_senha.set("segredo"); d._validar()
        assert d.v_cnpj.get() == "11.222.333/0001-81", d.v_cnpj.get()
        assert d.v_nome.get() == "EMPRESA TESTE"
        d.v_destino.set(str(t / "cli")); d.cb_est.current(1)  # ano_mes
        d._salvar()
        assert d.salvou, d.l_erro.cget("text")
        assert "segredo" not in (t / "dados" / "empresas.json").read_text(encoding="utf-8")
        app._atualizar_lista(d.emp["id"])
        assert len(app.tv.get_children()) == 1
        passo("cadastro de empresa salva e lista atualiza")

        # --- busca
        emp = store.empresas[0]
        eu = dict(emit_cnpj=CNPJ, emit_nome="EMPRESA TESTE")
        sessao = SessaoFalsa([(0, [
            item(1, xml_nfse("1" * 50, valor="1000.00", dh="2026-09-01T10:00:00-03:00", num="1", **eu)),
            item(2, xml_nfse("2" * 50, valor="250.50", dh="2026-09-30T10:00:00-03:00", num="2", **eu)),
            item(3, xml_nfse("3" * 50, valor="80.00", dh="2026-09-02T10:00:00-03:00", num="3", toma_cnpj=CNPJ, toma_nome="EMPRESA TESTE")),
        ])])
        b = A.DialogoBusca(app, store, emp, sessao=sessao)
        b.update()
        assert b.v_mes.get() in core.MESES_TELA
        assert b.ano == __import__("datetime").date.today().year
        b.v_mes.set("Setembro"); b.ano = 2026; b._atualizar_periodo()
        assert b.l_periodo.cget("text") == "01/09/2026 a 30/09/2026", b.l_periodo.cget("text")
        b._buscar()
        assert esperar(lambda: b.resultado is not None, app), f"busca não terminou: {mensagens}"
        r = b.resultado
        assert abs(r["resumo"]["servico_prestado"]["valor"] - 1250.50) < 0.001
        assert len(b.tv.get_children()) == 3
        assert "1.250,50" in b.cards["prestado"][1].cget("text"), b.cards["prestado"][1].cget("text")
        passo("busca mostra faturamento e lista de notas")
        # saldo líquido (prestado − tomado): verde se positivo; totais e botões no mesmo bloco
        assert b.l_saldo_v.cget("text") == "R$ 1.170,50", b.l_saldo_v.cget("text")
        assert str(b.c_saldo.cget("bg")).upper() == "#E3F5E9"
        assert b.c_saldo.winfo_ismapped()
        assert b.b_copiar.master is b.f_acoes_totais and b.b_avancado.master is b.f_acoes_totais
        assert b.f_acoes_totais.master is b.f_bloco and b.b_copiar.winfo_ismapped()
        assert "Saldo líquido" in b._texto_totais() and "1.170,50" in b._texto_totais()
        neg = SessaoFalsa([(0, [
            item(1, xml_nfse("4" * 50, valor="100.00", dh="2026-09-03T10:00:00-03:00", num="4", **eu)),
            item(2, xml_nfse("5" * 50, valor="500.00", dh="2026-09-04T10:00:00-03:00", num="5", toma_cnpj=CNPJ, toma_nome="EMPRESA TESTE")),
        ])])
        bn = A.DialogoBusca(app, store, emp, sessao=neg)
        bn.v_mes.set("Setembro"); bn.ano = 2026; bn._atualizar_periodo(); bn._buscar()
        assert esperar(lambda: bn.resultado is not None, app)
        assert bn.l_saldo_v.cget("text") == "-R$ 400,00", bn.l_saldo_v.cget("text")
        assert str(bn.c_saldo.cget("bg")).upper() == "#FDE7E7" and str(bn.l_saldo_v.cget("fg")).upper() == "#C0392B"
        bn.destroy()
        passo("saldo líquido muda de cor (positivo/negativo)")

        b._copiar()
        assert "1.250,50" in app.clipboard_get()
        try:
            import openpyxl
        except ImportError:
            openpyxl = None
        if openpyxl:
            alvo = t / "export.xlsx"
            A.filedialog.asksaveasfilename = lambda **k: str(alvo)
            b._exportar_planilha()
            wbk = openpyxl.load_workbook(alvo)
            assert wbk.sheetnames == ["Geral", "Prestado", "Tomado", "Canceladas"], wbk.sheetnames
            assert abs(wbk["Geral"]["C3"].value - 1250.50) < 0.001
            passo("exportar planilha Excel")
        b._gravar()
        pasta = t / "cli" / "2026" / "09-Setembro"
        nomes = [p.name for p in pasta.iterdir()]
        assert len(nomes) == 4, nomes  # 3 XMLs + relatório
        passo("gravação cria pasta ano/mês e arquivos")

        # --- só calcular não exige destino
        emp2 = dict(emp, acao="calcular", destino="")
        b2 = A.DialogoBusca(app, store, emp2, sessao=sessao)
        b2.v_mes.set("Setembro"); b2.ano = 2026
        b2._buscar()
        assert esperar(lambda: b2.resultado is not None, app)
        assert not b2.b_gravar.winfo_ismapped()
        b2.destroy()
        passo("modo só calcular")

        # --- informações avançadas: gráfico + comparativo de regimes
        from adge_nf import avancado as AV
        AV.DialogoAvancado._fluxo_dados = lambda self: None          # sem janelas bloqueantes no teste
        assert b.b_avancado.winfo_ismapped()
        b._avancado()
        av = [w for w in b.winfo_toplevel().winfo_children() if isinstance(w, AV.DialogoAvancado)][0]
        av.update()
        assert [x[0] for x in av.itens][0].startswith("CLIENTE") or av.itens, av.itens
        av.v_modo.set("tipo"); av._mudou()
        assert {x[0] for x in av.itens} == {"Serviços prestados", "Serviços tomados"}, av.itens
        av._clicar(0)
        assert "R$" in av.l_detalhe.cget("text")
        # sem dados fiscais: pede para informar
        assert any("Informar dados fiscais" in str(w.cget("text")) for w in av.f_comp.winfo_children() if w.winfo_class() == "TButton")
        d = AV.DialogoDadosFiscais(av, store, av.emp)
        d.v_rbt.set("360.000,00"); d.v_folha.set("120.000,00"); d.v_regime.set("Lucro Presumido"); d.v_iss.set("5")
        d._salvar()
        assert d.salvou, d.l_erro.cget("text")
        assert store.obter(av.emp["id"])["fiscal"]["regime"] == "presumido"
        av._render_comparativo()
        av.update()
        txt = []
        def varre(w):
            try:
                txt.append(str(w.cget("text")))
            except tk.TclError:
                pass
            for f in w.winfo_children():
                varre(f)
        import tkinter as tk
        varre(av.f_comp)
        junto = " ".join(txt)
        assert "Simples Nacional" in junto and "Lucro Real" in junto and "IBS/CBS" in junto, junto[:400]
        assert "Mais econômico" in junto
        passo("informações avançadas: pizza, dados fiscais e comparativo")
        av.destroy()

        # --- pasta fora do padrão Adge: não trava, deixa escolher outra pasta
        (t / "cliente_sem_padrao").mkdir()
        emp3 = dict(emp, estrutura="adge", destino=str(t / "cliente_sem_padrao"))
        b3 = A.DialogoBusca(app, store, emp3, sessao=sessao)
        b3.v_mes.set("Setembro"); b3.ano = 2026
        b3._buscar()
        assert esperar(lambda: b3.resultado is not None, app)
        assert str(b3.b_gravar.cget("state")) == "disabled"
        assert "Escolher pasta" in b3.l_destino.cget("text"), b3.l_destino.cget("text")
        assert b3.b_pasta.winfo_ismapped()
        (t / "livre").mkdir()
        A.filedialog.askdirectory = lambda **k: str(t / "livre")
        b3._escolher_pasta()
        assert str(b3.b_gravar.cget("state")) == "normal"
        b3._gravar()
        assert len(list((t / "livre").iterdir())) == 4, list((t / "livre").iterdir())
        b3.destroy()
        passo("pasta fora do padrão Adge permite escolher outra pasta")

        # --- erro do ADN aparece sem travar
        class Ruim:
            def get(self, *a, **k):
                return type("R", (), {"status_code": 403, "json": lambda s: {}})()
        b3 = A.DialogoBusca(app, store, emp, sessao=Ruim())
        b3._buscar()
        assert esperar(lambda: any(m[0] == "erro" for m in mensagens), app)
        assert not b3.trabalhando
        b3.destroy()
        passo("erro do ADN vira mensagem")

        # --- atualização: aviso, baixar com integridade, instalar, lembrar depois, pular
        import hashlib
        from adge_nf import atualizacao
        from adge_nf import REPO_GITHUB
        conteudo = b"msi-de-teste" * 5000
        sha = hashlib.sha256(conteudo).hexdigest()
        url = f"https://github.com/{REPO_GITHUB}/releases/download/v9.9.9/App.msi"

        class RespA:
            def __init__(self, code=200, j=None, c=b""):
                self.status_code, self._j, self._c, self.headers = code, j, c, {"Content-Length": str(len(c))}
            def json(self): return self._j
            def iter_content(self, n):
                for i in range(0, len(self._c), n):
                    yield self._c[i:i + n]

        class SessaoA:
            def __init__(self, c=conteudo): self.c = c
            def get(self, u, **k):
                if u.endswith("/releases/latest"):
                    return RespA(200, {"tag_name": "v9.9.9", "html_url": "https://x", "body": "Agora suporta NF-e",
                                       "assets": [{"name": "App.msi", "browser_download_url": url, "size": len(conteudo), "digest": "sha256:" + sha}]})
                return RespA(200, c=self.c)

        app.sessao_att = SessaoA()
        abertos = []
        orig = A.DialogoAtualizacao
        def fabrica(pai, st, info, **k):
            d = orig(pai, st, info, ao_instalar=lambda caminho: abertos.append(caminho), pode_instalar=True, sessao=app.sessao_att)
            d.after(100, d._atualizar)           # simula o clique em "Atualizar agora"
            d.after(2500, lambda: d.winfo_exists() and d.destroy())
            return d
        A.DialogoAtualizacao = fabrica
        app._checar_atualizacao(manual=True)
        assert esperar(lambda: abertos, app, 15), f"instalação não foi disparada: {mensagens}"
        assert pathlib.Path(abertos[0]).read_bytes() == conteudo
        passo("atualização baixa, confere a integridade e dispara a instalação")
        A.DialogoAtualizacao = orig

        # arquivo adulterado: recusa e não instala
        abertos.clear()
        app.sessao_att = SessaoA(conteudo[:-1] + b"X")
        app.info_att = None
        A.DialogoAtualizacao = fabrica
        app._checar_atualizacao(manual=True)
        esperar(lambda: False, app, 4)
        assert not abertos
        A.DialogoAtualizacao = orig
        passo("arquivo adulterado não é instalado")

        # lembrar depois e pular
        info = atualizacao.consultar(SessaoA(), versao="1.0.0")
        d = orig(app, store, info, pode_instalar=False)
        d.update()
        assert "Agora suporta NF-e" in d.txt.get("1.0", "end")
        assert d.b_ok.cget("text") == "Abrir a página de download"
        d._depois()
        assert not atualizacao.deve_avisar(info, store.preferencias)
        store.preferencias["atualizacao"].pop("lembrar_ate")
        d = orig(app, store, info, pode_instalar=True)
        d.update()
        assert d.b_ok.cget("text") == "Atualizar agora"
        d._pular()
        assert store.preferencias["atualizacao"]["pular"] == "v9.9.9"
        passo("lembrar depois e pular versão")

        # --- configurações
        store.trocar_modo("mestra123")
        app._atualizar_seguranca()
        assert "senha mestra" in app.l_seg.cget("text").lower()
        passo("configurações")
        # a aba de configurações tem rolagem e botão de apagar dados
        assert any(isinstance(w, A.AbaRolavel) for w in app.abas.winfo_children())
        app._apagar_dados()
        assert store.empresas == [] and not (t / "dados" / "empresas.json").exists()
        passo("apagar todos os dados")  # o app fecha sozinho depois de apagar


try:
    principal()
    print("SMOKE OK")
except Exception:
    traceback.print_exc()
    sys.exit(1)
