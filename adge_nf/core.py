"""Núcleo (sem interface): ADN, leitura do XML, nomes, plano do período, pastas e gravação."""
import base64
import datetime as dt
import gzip
import io
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

ADN = "https://adn.nfse.gov.br/contribuintes"

MESES = ["Janeiro", "Fevereiro", "Marco", "Abril", "Maio", "Junho", "Julho", "Agosto",
         "Setembro", "Outubro", "Novembro", "Dezembro"]
MESES_TELA = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto",
              "Setembro", "Outubro", "Novembro", "Dezembro"]


def mes_exibicao(m: int) -> str:
    return MESES_TELA[m - 1]


CATEGORIAS = {
    # lado: "receita" (entra no faturamento), "custo" (entra nas compras/tomados) ou "neutro"; sinal: +1 soma, -1 subtrai (devoluções)
    "servico_prestado": {"prefixo": "NOTA FISCAL DE SERVIÇO PRESTADO", "relatorio": "Serviço Prestado", "rotulo": "NFS-e prestadas",
                         "tipo": "Prestado", "lado": "receita", "sinal": 1, "grupo": "nfse", "padrao": True},
    "servico_tomado": {"prefixo": "NOTA FISCAL DE SERVIÇO TOMADO", "relatorio": "Serviço Tomado", "rotulo": "NFS-e tomadas",
                       "tipo": "Tomado", "lado": "custo", "sinal": 1, "grupo": "nfse", "padrao": True},
    "paulistana_prestado": {"prefixo": "NOTA FISCAL PAULISTANA DE SERVIÇO PRESTADO", "relatorio": "Paulistana Prestado",
                            "rotulo": "Paulistana prestadas", "tipo": "Paulistana prest.", "lado": "receita", "sinal": 1,
                            "grupo": "nfse", "padrao": False, "origem": "paulistana"},
    "paulistana_tomado": {"prefixo": "NOTA FISCAL PAULISTANA DE SERVIÇO TOMADO", "relatorio": "Paulistana Tomado",
                          "rotulo": "Paulistana tomadas", "tipo": "Paulistana tom.", "lado": "custo", "sinal": 1,
                          "grupo": "nfse", "padrao": False, "origem": "paulistana"},
    "nfe_saida": {"prefixo": "NOTA FISCAL ELETRÔNICA DE VENDA", "relatorio": "NF-e de Venda", "rotulo": "NF-e de venda",
                  "tipo": "Venda", "lado": "receita", "sinal": 1, "grupo": "nfe", "padrao": True},
    "nfe_entrada": {"prefixo": "NOTA FISCAL ELETRÔNICA DE COMPRA", "relatorio": "NF-e de Compra", "rotulo": "NF-e de compra",
                    "tipo": "Compra", "lado": "custo", "sinal": 1, "grupo": "nfe", "padrao": True},
    "nfe_devolucao_venda": {"prefixo": "NOTA FISCAL ELETRÔNICA DE DEVOLUÇÃO DE VENDA", "relatorio": "NF-e Devolução de Venda",
                            "rotulo": "NF-e devolução de venda", "tipo": "Devol. venda", "lado": "receita", "sinal": -1,
                            "grupo": "nfe", "padrao": True},
    "nfe_devolucao_compra": {"prefixo": "NOTA FISCAL ELETRÔNICA DE DEVOLUÇÃO DE COMPRA", "relatorio": "NF-e Devolução de Compra",
                             "rotulo": "NF-e devolução de compra", "tipo": "Devol. compra", "lado": "custo", "sinal": -1,
                             "grupo": "nfe", "padrao": True},
    "nfe_outras": {"prefixo": "NOTA FISCAL ELETRÔNICA DE OUTRAS OPERAÇÕES", "relatorio": "NF-e Outras Operações",
                   "rotulo": "NF-e outras operações", "tipo": "Outras op.", "lado": "neutro", "sinal": 0, "grupo": "nfe",
                   "padrao": False},
    "nfe_resumo": {"prefixo": "RESUMO DE NOTA FISCAL ELETRÔNICA", "relatorio": "NF-e só com resumo", "rotulo": "NF-e sem ciência",
                   "tipo": "Sem ciência", "lado": "custo", "sinal": 1, "grupo": "nfe", "padrao": False},
}
ORDEM_CATEGORIAS = list(CATEGORIAS)

# Estruturas de pasta de destino
ESTRUTURAS = {
    "adge": "Padrão Adge: Cliente \\ Departamento Fiscal \\ Notas Fiscais \\ AAAA \\ MM-Mês",
    "ano_mes": "Ano e mês: Pasta \\ AAAA \\ MM-Mês (cria o que faltar)",
    "direto": "Direto: todas as notas na pasta escolhida",
}


class ErroAdge(Exception):
    """Erro com mensagem pronta para mostrar ao usuário."""


class Cancelado(Exception):
    pass


# ----------------------------------------------------------------------------- nomes
def norm(s: str) -> str:
    """minúsculas, sem acento, sem espaço/underscore/pontuação."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def formatar_valor(v: float) -> str:
    return "R$" + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_data(iso: str) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", iso or "")
    return f"{m[3]}-{m[2]}-{m[1]}" if m else "sem-data"


def limpar_nome(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", s or "")
    return re.sub(r"\s+", " ", s).strip()


LIMITE_NOME = 200  # teto do nome do arquivo; o real também respeita o limite de caminho do Windows


def _encurtar(texto: str, tirar: int) -> str:
    """Tira `tirar` caracteres do fim, preferindo cortar numa palavra inteira."""
    alvo = max(10, len(texto) - tirar)
    corte = texto[:alvo]
    if len(texto) > alvo and texto[alvo] != " " and " " in corte.strip():
        corte = corte[:corte.rstrip().rfind(" ")]
    return corte.strip()


def montar_nome(inicio: str, d: dict, ext: str, limite: int = LIMITE_NOME) -> str:
    de = limpar_nome(d["emitente_nome"]) or d["emitente_doc"]
    para = limpar_nome(d["tomador_nome"]) or d["tomador_doc"]
    fim = f" em {formatar_data(d['emissao'])} no valor de {formatar_valor(d['valor'])}{ext}"
    nome = f"{inicio} - {de} para {para}{fim}"
    while len(nome) > limite:
        # encurta sempre o nome mais comprido, sem cortar palavra ao meio
        antes = len(nome)
        if len(de) >= len(para) and len(de) > 10:
            de = _encurtar(de, antes - limite)
        elif len(para) > 10:
            para = _encurtar(para, antes - limite)
        else:
            break
        nome = f"{inicio} - {de} para {para}{fim}"
        if len(nome) >= antes:
            break
    return nome


def nome_xml(categoria: str, d: dict, prefixos: dict = None, limite: int = LIMITE_NOME) -> str:
    prefixo = (prefixos or {}).get(categoria) or CATEGORIAS[categoria]["prefixo"]
    return montar_nome(prefixo, d, ".xml", limite)


def unico(nome: str, usados: set) -> str:
    if nome.lower() not in usados:
        usados.add(nome.lower())
        return nome
    base, ext = nome.rsplit(".", 1) if "." in nome else (nome, "")
    i = 2
    while True:
        cand = f"{base} ({i}){'.' + ext if ext else ''}"
        if cand.lower() not in usados:
            usados.add(cand.lower())
            return cand
        i += 1


# ----------------------------------------------------------------------------- XML
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _achar(el, nome):
    if el is None:
        return None
    for e in el.iter():
        if _local(e.tag) == nome:
            return e
    return None


def _txt(el, nome) -> str:
    e = _achar(el, nome)
    return (e.text or "").strip() if e is not None and e.text else ""


def _num(s: str) -> float:
    try:
        return float(str(s).replace(",", "."))
    except ValueError:
        return 0.0


def parse_documento(xml_texto) -> dict:
    """kind: nfse | evento | desconhecido (layout da NFS-e Nacional v1.01)."""
    raiz = ET.fromstring(xml_texto.encode("utf-8") if isinstance(xml_texto, str) else xml_texto)
    inf = _achar(raiz, "infNFSe")
    if inf is not None:
        dps = _achar(inf, "infDPS")
        emit, toma = _achar(inf, "emit"), _achar(dps, "toma")
        return {
            "kind": "nfse",
            "chave": re.sub(r"^NFS", "", inf.get("Id", "")),
            "numero": _txt(inf, "nNFSe"),
            "emissao": _txt(dps, "dhEmi") or _txt(inf, "dhProc"),
            "processamento": _txt(inf, "dhProc"),
            "competencia": _txt(dps, "dCompet"),
            "emitente_doc": _txt(emit, "CNPJ") or _txt(emit, "CPF"),
            "emitente_nome": _txt(emit, "xNome"),
            "emitente_simples": _txt(dps, "opSimpNac"),                  # 1 não optante, 2 MEI, 3 ME/EPP optante do Simples
            "tomador_doc": _txt(toma, "CNPJ") or _txt(toma, "CPF"),
            "tomador_nome": _txt(toma, "xNome"),
            "valor": _num(_txt(dps, "vServ")),
            "valor_liquido": _num(_txt(inf, "vLiq")),
            "iss": _num(_txt(inf, "vISSQN")),
            "servico_cod": _txt(dps, "cTribNac"),                       # código de tributação nacional (começa pelo item da LC 116)
            "servico_desc": _txt(inf, "xTribNac") or _txt(dps, "xDescServ"),
            "iss_aliquota": _num(_txt(inf, "pAliqAplic") or _txt(dps, "pAliq")),
        }
    if re.search(r"evento|pedreg", _local(raiz.tag), re.I) or _achar(raiz, "chNFSe") is not None:
        return {"kind": "evento", "chave": _txt(raiz, "chNFSe"),
                "cancelamento": _achar(raiz, "e101101") is not None or _txt(raiz, "tpEvento") == "101101"}
    return {"kind": "desconhecido"}


# ----------------------------------------------------------------------------- ADN (API oficial)
def _campo(d: dict, *nomes):
    baixo = {k.lower(): v for k, v in d.items()}
    for n in nomes:
        if n.lower() in baixo:
            return baixo[n.lower()]
    return None


def decodificar_arquivo(b64: str) -> str:
    return gzip.decompress(base64.b64decode(b64)).decode("utf-8")


def baixar_dfe(sessao, cnpj: str, nsu_inicial: int = 0, pausa: float = 0.5, log=lambda *_: None,
               cancelar=lambda: False, limite_lotes: int = 2000, esperar=time.sleep):
    """Percorre a distribuição de DF-e por NSU e devolve [{nsu, chave, tipo, tipo_evento, gerado_em, xml}]."""
    docs, vistos, nsu, tentativas = [], set(), nsu_inicial, 0
    for _ in range(limite_lotes):
        if cancelar():
            raise Cancelado()
        try:
            r = sessao.get(f"{ADN}/DFe/{nsu}", params={"cnpjConsulta": cnpj, "lote": "true"}, timeout=90)
        except Exception as e:  # rede fora, certificado recusado no handshake etc.
            raise ErroAdge(f"Não consegui falar com o ADN: {e}") from e
        corpo = {}
        try:
            corpo = r.json()
        except ValueError:
            pass
        status = str(_campo(corpo, "StatusProcessamento") or "") if isinstance(corpo, dict) else ""
        if r.status_code == 404 or "NENHUM_DOCUMENTO" in status.upper():
            break
        if r.status_code in (401, 403):
            raise ErroAdge(f"O ADN recusou o certificado (HTTP {r.status_code}). Confira se o A1 é do CNPJ certo e está válido.")
        if r.status_code in (429, 500, 502, 503, 504):
            tentativas += 1
            if tentativas > 12:
                raise ErroAdge(f"O ADN continua instável (HTTP {r.status_code}). Tente de novo mais tarde.")
            log(f"ADN instável (HTTP {r.status_code}), aguardando...")
            esperar(5)
            continue
        if r.status_code != 200 or "REJEICAO" in status.upper():
            raise ErroAdge(f"Resposta inesperada do ADN (HTTP {r.status_code}): {str(corpo)[:300]}")
        tentativas = 0
        novos = 0
        for item in _campo(corpo, "LoteDFe") or []:
            n = int(_campo(item, "NSU") or 0)
            if n in vistos:
                continue
            vistos.add(n)
            novos += 1
            arq = _campo(item, "ArquivoXml")
            docs.append({
                "nsu": n,
                "chave": _campo(item, "ChaveAcesso") or "",
                "tipo": str(_campo(item, "TipoDocumento") or ""),
                "tipo_evento": str(_campo(item, "TipoEvento") or ""),
                "gerado_em": str(_campo(item, "DataHoraGeracao") or ""),
                "xml": decodificar_arquivo(arq) if arq else "",
            })
        if novos == 0:
            break
        nsu = max(vistos)
        log(f"{len(docs)} documento(s) recebidos até agora...")
        esperar(pausa)
    return docs


def sessao_com_certificado(pfx: str, senha: str):
    import requests
    from requests_pkcs12 import Pkcs12Adapter
    s = requests.Session()
    s.mount("https://adn.nfse.gov.br", Pkcs12Adapter(pkcs12_filename=pfx, pkcs12_password=senha))
    return s


def ler_certificado(pfx: str, senha: str) -> dict:
    """Abre o .pfx/.p12 e devolve {cnpj, cpf, documento, tipo, nome, valido_ate} (e-CNPJ traz o cnpj; e-CPF traz o cpf). Levanta ErroAdge se a senha/arquivo estiver errado."""
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.x509.oid import NameOID
    try:
        dados = Path(pfx).read_bytes()
    except OSError as e:
        raise ErroAdge(f"Não consegui abrir o arquivo do certificado: {e}") from e
    try:
        _, cert, _ = pkcs12.load_key_and_certificates(dados, senha.encode("utf-8") if senha else None)
    except Exception as e:
        raise ErroAdge("Senha incorreta ou arquivo de certificado inválido.") from e
    if cert is None:
        raise ErroAdge("O arquivo não contém um certificado.")
    cn = next((a.value for a in cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)), "")
    m = re.search(r"(\d{14})", cn)
    cnpj = m[1] if m else ""
    m2 = None if cnpj else re.search(r"(?<!\d)(\d{11})(?!\d)", cn)        # e-CPF: "NOME:12345678901"
    cpf = m2[1] if m2 else ""
    nome = re.sub(r":?\d{11,14}$", "", cn).strip(": ")
    return {"cnpj": cnpj, "cpf": cpf, "documento": cnpj or cpf, "tipo": "cnpj" if cnpj else "cpf" if cpf else "",
            "nome": nome, "valido_ate": cert.not_valid_after_utc.date()}


# ----------------------------------------------------------------------------- período e plano
def alternar_periodo(selecionados, ano: int, mes: int) -> set:
    """Consulta em lote: clicar num mês marca ou desmarca o par (ano, mês). A seleção nunca fica vazia (o último mês não sai)."""
    novo = set(selecionados)
    novo ^= {(int(ano), int(mes))}
    return novo or set(selecionados)


def formatar_periodos(periodos) -> str:
    """[(2026,1),(2026,2),(2026,3)] -> 'Jan, Fev e Mar de 2026'; com anos diferentes: 'Dez/2025 e Jan/2026'."""
    ps = sorted({(int(a), int(m)) for a, m in periodos})
    if not ps:
        return ""
    curto = lambda m: MESES_TELA[m - 1][:3]   # noqa: E731
    if len({a for a, _ in ps}) == 1:
        nomes = [curto(m) for _, m in ps]
        junto = nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]
        return f"{junto} de {ps[0][0]}"
    nomes = [f"{curto(m)}/{a}" for a, m in ps]
    return ", ".join(nomes[:-1]) + " e " + nomes[-1]


def limites_mes(ano: int, mes: int):
    ini = dt.date(ano, mes, 1)
    fim = dt.date(ano + (mes == 12), mes % 12 + 1, 1) - dt.timedelta(days=1)
    return ini, fim


def data_do_doc(d: dict):
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", d.get("processamento") or d.get("emissao") or "")
    return dt.date(int(m[1]), int(m[2]), int(m[3])) if m else None


def classificar(d: dict, cnpj: str):
    if d["emitente_doc"] == cnpj:
        return "servico_prestado"
    if d["tomador_doc"] == cnpj:
        return "servico_tomado"
    return None


def rbt12_nfse(docs: list, cnpj: str, ano: int, mes: int) -> dict:
    """RBT12 básico, sem nenhuma consulta a mais: soma das NFS-e prestadas (Ambiente Nacional) dos 12 meses ANTERIORES ao mês
    consultado, usando os documentos que a consulta já baixou (o ADN entrega todo o histórico a cada busca). Não inclui NF-e de
    mercadorias nem notas emitidas fora do Ambiente Nacional. Devolve {valor, qtd, meses_com_notas, por_mes: {(ano, mes): valor},
    de, ate}; com `valor` 0 não há o que sugerir."""
    meses, a, m = [], ano, mes
    for _ in range(12):
        m -= 1
        if m == 0:
            a, m = a - 1, 12
        meses.append((a, m))
    meses.reverse()
    ini, fim = limites_mes(*meses[0])[0], limites_mes(*meses[-1])[1]
    canceladas, lidos = set(), []
    for x in docs:
        if not x.get("xml"):
            continue
        try:
            d = parse_documento(x["xml"])
        except ET.ParseError:
            continue
        if d["kind"] == "evento" and d.get("cancelamento"):
            canceladas.add(d["chave"])
        elif d["kind"] == "nfse":
            lidos.append(d)
    por_mes, vistos, qtd = {k: 0.0 for k in meses}, set(), 0
    for d in lidos:
        dia = data_do_doc(d)
        if dia is None or not (ini <= dia <= fim) or classificar(d, cnpj) != "servico_prestado":
            continue
        if d["chave"] in vistos or d["chave"] in canceladas:
            continue
        vistos.add(d["chave"])
        por_mes[(dia.year, dia.month)] += d["valor"]
        qtd += 1
    por_mes = {k: round(v, 2) for k, v in por_mes.items()}
    return {"valor": round(sum(por_mes.values()), 2), "qtd": qtd, "por_mes": por_mes, "de": meses[0], "ate": meses[-1],
            "meses_com_notas": sum(1 for v in por_mes.values() if v > 0)}


def montar_plano(docs: list, cnpj: str, ano: int, mes: int, tipos: set, prefixos: dict = None,
                 limite_nome: int = LIMITE_NOME, extras: dict = None):
    """Aplica período, tipos ('prestado'/'tomado'), cancelamentos e nomes. Devolve (arquivos, resumo, avisos)."""
    ini, fim = limites_mes(ano, mes)
    avisos, lidos, canceladas, terceiros = [], [], set(), 0
    for x in docs:
        if not x["xml"]:
            continue
        try:
            d = parse_documento(x["xml"])
        except ET.ParseError:
            avisos.append(f"XML ilegível (NSU {x['nsu']})")
            continue
        if d["kind"] == "evento" and d.get("cancelamento"):
            canceladas.add(d["chave"])
        elif d["kind"] == "nfse":
            lidos.append((x, d))
    arquivos, usados, vistos, resumo = [], set(), set(), {}
    quer = {"servico_prestado": "prestado" in tipos, "servico_tomado": "tomado" in tipos}
    for x, d in sorted(lidos, key=lambda t: (t[1]["emissao"], t[1]["numero"])):
        dia = data_do_doc(d)
        if dia is None or not (ini <= dia <= fim):
            continue
        cat = classificar(d, cnpj)
        if cat is None:
            terceiros += 1
            continue
        if not quer[cat] or d["chave"] in vistos:
            continue
        vistos.add(d["chave"])
        r = resumo.setdefault(cat, {"qtd": 0, "canceladas": 0, "valor": 0.0, "liquido": 0.0, "iss": 0.0})
        if d["chave"] in canceladas:
            r["canceladas"] += 1
            if extras is not None:
                extras.setdefault("canceladas", []).append({"nome": "", "xml": x["xml"], "cat": cat, "doc": d})
            continue
        r["qtd"] += 1
        r["valor"] += d["valor"]
        r["liquido"] += d["valor_liquido"]
        r["iss"] += d["iss"]
        arquivos.append({"nome": unico(nome_xml(cat, d, prefixos, limite_nome), usados),
                         "xml": x["xml"], "cat": cat, "doc": d})
    if terceiros:
        avisos.append(f"{terceiros} nota(s) do período não têm o CNPJ da empresa como emitente nem tomador e foram ignoradas.")
    for r in resumo.values():
        for k in ("valor", "liquido", "iss"):
            r[k] = round(r[k], 2)
    for cat in ("servico_prestado", "servico_tomado"):
        if quer[cat]:
            resumo.setdefault(cat, {"qtd": 0, "canceladas": 0, "valor": 0.0, "liquido": 0.0, "iss": 0.0})
    return arquivos, resumo, avisos


# ----------------------------------------------------------------------------- pastas
def _achar_dir(pai: Path, pontuar):
    melhor, pontos = None, 0
    for f in sorted(pai.iterdir()):
        if f.is_dir():
            p = pontuar(norm(f.name))
            if p > pontos:
                melhor, pontos = f, p
    return melhor


def _teste_mes(mes):
    mm, nome = f"{mes:02d}", norm(MESES[mes - 1])
    return lambda n: 3 if n == mm + nome else 2 if n.startswith(mm) else 1 if nome in n else 0


def resolver_destino(base: Path, estrutura: str, ano: int, mes: int, criar: bool):
    """Devolve (pasta_final, trilha[(nome, será_criada)]). Busca aproximada de nomes (maiúsculas, acento, _)."""
    base = Path(base)
    if not base.is_dir():
        raise ErroAdge(f"A pasta de destino não existe: {base}")
    if estrutura == "direto":
        return base, []
    mes_nome = f"{mes:02d}-{MESES[mes - 1]}"
    if estrutura == "ano_mes":
        passos = [(str(ano), lambda n: 1 if n == str(ano) else 0, True), (mes_nome, _teste_mes(mes), True)]
    else:
        passos = [
            ("Departamento Fiscal", lambda n: 1 if re.match(r"^(departamento|depto|dep)fiscal", n) else 0, False),
            ("Notas Fiscais", lambda n: 3 if n == "notasfiscais" else 2 if re.match(r"^notas?(fiscais|fiscal)?$", n) else 0, True),
            (str(ano), lambda n: 1 if n == str(ano) else 0, True),
            (mes_nome, _teste_mes(mes), True),
        ]
    atual, existe, trilha = base, True, []
    for rotulo, teste, criavel in passos:
        ach = _achar_dir(atual, teste) if existe else None
        if ach:
            trilha.append((ach.name, False))
            atual = ach
            continue
        if not criavel:
            raise ErroAdge(f'Não encontrei a pasta "{rotulo}" dentro de "{base.name}". Confira se escolheu a pasta do cliente certo.')
        atual = atual / rotulo
        if criar:
            atual.mkdir(parents=True, exist_ok=True)
        existe = False
        trilha.append((rotulo, True))
    return atual, trilha


def limite_para_destino(destino: Path) -> int:
    """Maior nome de arquivo que cabe no limite de 259 caracteres do caminho do Windows."""
    return max(60, min(LIMITE_NOME, 255 - len(str(destino)) - 1))


def gravar(destino: Path, nome: str, dados) -> tuple:
    """Não sobrescreve: igual -> 'ja_existia'; diferente com o mesmo nome -> 'nome (2).ext'."""
    binario = dados.encode("utf-8") if isinstance(dados, str) else dados
    base, ext = (nome.rsplit(".", 1)[0], "." + nome.rsplit(".", 1)[1]) if "." in nome else (nome, "")
    alvo, n = Path(destino) / nome, 1
    while alvo.exists():
        if alvo.read_bytes() == binario:
            return alvo.name, "ja_existia"
        n += 1
        alvo = Path(destino) / f"{base} ({n}){ext}"
    alvo.write_bytes(binario)
    return alvo.name, ("renomeado" if n > 1 else "gravado")


# ----------------------------------------------------------------------------- relatórios
def texto_relatorio(empresa, cnpj, mes, ano, linhas, ok=True):
    agora = dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    return "\r\n".join([
        "--- RELATÓRIO DE ORGANIZAÇÃO FISCAL ---", f"Empresa: {empresa} (CNPJ: {cnpj})",
        f"Competência: {mes_exibicao(mes)} de {ano}", f"Status Final: {'SUCESSO' if ok else 'COM ERROS'}",
        f"Data de Processamento: {agora}", "-" * 80, "", *linhas, ""])


# ----------------------------------------------------------------------------- fluxo completo
def tipos_da_empresa(emp: dict) -> set:
    return {t for t in ("prestado", "tomado") if emp.get("tipos", {}).get(t)}


def buscar(emp: dict, senha: str, ano: int, mes: int, log=lambda *_: None, cancelar=lambda: False, sessao=None):
    """Consulta o ADN e devolve (docs, cnpj). `sessao` permite injetar um dublê nos testes."""
    cnpj = re.sub(r"\D", "", emp["cnpj"])
    pfx = emp.get("pfx", "")
    if not Path(pfx).is_file():
        raise ErroAdge(f"Certificado não encontrado: {pfx}")
    if sessao is None:
        try:
            sessao = sessao_com_certificado(pfx, senha)
        except ImportError as e:
            raise ErroAdge(f"Instalação incompleta (falta um componente): {e}") from e
    docs = baixar_dfe(sessao, cnpj, log=log, cancelar=cancelar)
    return docs, cnpj


def prefixos_da_empresa(emp: dict) -> dict:
    return {k: v for k, v in (("servico_prestado", emp.get("prefixo_prestado", "").strip()),
                              ("servico_tomado", emp.get("prefixo_tomado", "").strip())) if v}


def planejar(emp: dict, docs: list, cnpj: str, ano: int, mes: int, destino: Path = None, extras: dict = None,
             docs_nfe: list = None, docs_paulistana: list = None):
    """Plano do período. `docs_nfe` (documentos de NF-e vindos do histórico/consulta) soma as NF-e ao mesmo resultado."""
    limite = limite_para_destino(destino) if destino else LIMITE_NOME
    arquivos, resumo, avisos = montar_plano(docs, cnpj, ano, mes, tipos_da_empresa(emp), prefixos_da_empresa(emp), limite, extras)
    if docs_nfe is not None:
        from . import nfe
        a2, r2, av2 = nfe.montar_plano_nfe(docs_nfe, cnpj, ano, mes, limite, extras)
        arquivos = sorted(arquivos + a2, key=lambda a: (a["doc"].get("emissao") or "", str(a["doc"].get("numero") or "")))
        resumo.update(r2)
        avisos = avisos + av2
    if docs_paulistana is not None:
        from . import paulistana
        a3, r3, av3 = paulistana.montar_plano(docs_paulistana, cnpj, ano, mes, limite, extras)
        arquivos = sorted(arquivos + a3, key=lambda a: (a["doc"].get("emissao") or "", str(a["doc"].get("numero") or "")))
        resumo.update(r3)
        avisos = avisos + av3
    return arquivos, resumo, avisos


def nome_planilha(mes: int, ano: int) -> str:
    return f"Resumo Notas - {mes:02d}-{ano}.xlsx"


def salvar_notas(emp: dict, arquivos: list, resumo: dict, cnpj: str, ano: int, mes: int, log=lambda *_: None,
                 canceladas: list = None, ativos=None):
    """Grava os XMLs (e relatório/planilha, se ligados). Devolve (pasta, contagem)."""
    destino, _ = resolver_destino(Path(emp["destino"]), emp.get("estrutura", "adge"), ano, mes, criar=True)
    contagem, linhas, so_resumo = {}, [], []
    for f in arquivos:
        if f.get("sem_xml"):                              # NF-e só com resumo: não há XML para gravar
            so_resumo.append(f)
            continue
        if ativos is not None and f["cat"] not in ativos:  # só os XMLs das categorias marcadas na tela
            continue
        _, status = gravar(destino, f["nome"], f["xml"])
        contagem[status] = contagem.get(status, 0) + 1
        linhas.append(f"Sucesso - XML {CATEGORIAS[f['cat']]['relatorio']} - "
                      f"{formatar_valor(f['doc']['valor']).replace('R$', 'R$ ')} - {formatar_data(f['doc']['emissao'])} - {f['doc']['chave']}")
    for f in so_resumo:
        d = f["doc"]
        linhas.append(f"Sem XML - NF-e só com resumo (sem ciência da operação) - {formatar_valor(d['valor']).replace('R$', 'R$ ')} - "
                      f"{formatar_data(d['emissao'])} - {d['emitente_nome']} - {d['chave']}")
    empresa = next((f["doc"]["emitente_nome"] for f in arquivos if f["doc"]["emitente_doc"] == cnpj), emp.get("nome", ""))
    if emp.get("relatorio", True) and (arquivos or so_resumo):
        gravar(destino, f"[Sucesso] Relatorio de Organizacao - {limpar_nome(empresa)[:30].strip()} - {mes_exibicao(mes)} de {ano}.txt",
               texto_relatorio(empresa, cnpj, mes, ano, linhas))
    if emp.get("planilha", emp.get("csv", False)) and (arquivos or so_resumo):
        from . import planilha
        alvo = Path(destino) / nome_planilha(mes, ano)
        n = 2
        while alvo.exists():                              # não sobrescreve: "(2)", "(3)"...
            alvo = Path(destino) / f"Resumo Notas - {mes:02d}-{ano} ({n}).xlsx"
            n += 1
        planilha.gerar_xlsx(alvo, empresa, ano, mes, arquivos, resumo, canceladas, ativos)
    return destino, contagem


def carregar_pasta(pasta, cnpj: str):
    """Relê os XMLs de uma pasta onde as notas já foram salvas (é assim que o histórico reabre uma consulta, sem ir ao ADN, à
    SEFAZ ou à Prefeitura). Devolve (docs_nfse, docs_nfe, docs_paulistana) no mesmo formato da consulta, pronto para `planejar`.
    Cancelamentos e NF-e só com resumo não viram XML na gravação, então não voltam por aqui (ficam no relatório da pasta)."""
    pasta = Path(pasta)
    if not pasta.is_dir():
        raise ErroAdge(f"A pasta onde as notas foram salvas não existe mais: {pasta}")
    from . import paulistana
    adn, nf, sp = [], [], []
    for i, arq in enumerate(sorted(pasta.glob("*.xml")), 1):
        try:
            texto = arq.read_text(encoding="utf-8")
            raiz = ET.fromstring(texto.encode("utf-8"))
        except (OSError, UnicodeDecodeError, ET.ParseError):
            continue
        if _achar(raiz, "infNFSe") is not None:
            adn.append({"nsu": i, "chave": "", "tipo": "NFSE", "tipo_evento": "", "gerado_em": "", "xml": texto})
        elif _achar(raiz, "infNFe") is not None:
            nf.append({"nsu": i, "tipo": "proc", "schema": "procNFe_v4.00.xsd", "xml": texto})
        elif _local(raiz.tag) == "NFe" and _achar(raiz, "ChaveNFe") is not None:
            d = paulistana.parse_nfe(raiz)
            sp.append({"lado": "prestado" if d["emitente_doc"] == cnpj else "tomado", "xml": texto})
    return adn, nf, sp
