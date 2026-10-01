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
from adge_nf.store import Armazenamento, empresa_padrao  # noqa: E402
from fixtures import SessaoFalsa, item, xml_nfse  # noqa: E402

CNPJ = "45890721000152"
mensagens = []
A.messagebox.showerror = lambda *a, **k: mensagens.append(("erro", a))
A.messagebox.showwarning = lambda *a, **k: mensagens.append(("aviso", a))
A.messagebox.askyesno = lambda *a, **k: (mensagens.append(("pergunta", a)) or True)
A.abrir_pasta = lambda *_: None


class CofreFalso:
    d = {}
    def get_password(self, s, u): return self.d.get((s, u))
    def set_password(self, s, u, p): self.d[(s, u)] = p


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
        app = A.App(store)
        app.update()
        passo("janela principal abre")

        # --- cadastro de empresa
        core.ler_certificado = lambda *_: {"cnpj": CNPJ, "nome": "EMPRESA TESTE", "valido_ate": __import__("datetime").date(2099, 1, 1)}
        d = A.DialogoEmpresa(app, store)
        d.update()
        d.v_pfx.set(str(pfx)); d.v_senha.set("segredo"); d._validar()
        assert d.v_cnpj.get() == "45.890.721/0001-52", d.v_cnpj.get()
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

        b._copiar()
        assert "1.250,50" in app.clipboard_get()
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

        # --- configurações
        store.trocar_modo("mestra123")
        app._atualizar_seguranca()
        assert "senha mestra" in app.l_seg.cget("text").lower()
        passo("configurações")
        b.destroy()
        app.destroy()


try:
    principal()
    print("SMOKE OK")
except Exception:
    traceback.print_exc()
    sys.exit(1)
