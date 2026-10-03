"""Responsável (v1.7.6): quem consulta a SEFAZ com o próprio certificado (e-CPF ou e-CNPJ) para receber as NF-e em que o emitente o
citou no campo autXML, o caso das NF-e de VENDA da empresa, que a SEFAZ não entrega à própria empresa.

Este módulo não usa tela: validação de CPF/CNPJ, conferência do certificado, pasta do histórico do responsável e a lista das
empresas que, de fato, mandaram notas a ele. Tudo é local: nada vai a servidor da Adge.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from . import nfe
from .core import ErroAdge


def so_digitos(txt: str) -> str:
    return re.sub(r"\D", "", txt or "")


def cpf_valido(cpf: str) -> bool:
    c = so_digitos(cpf)
    if len(c) != 11 or len(set(c)) == 1:
        return False
    for n in (9, 10):
        soma = sum(int(c[i]) * (n + 1 - i) for i in range(n))
        if int(c[n]) != (soma * 10 % 11) % 10:
            return False
    return True


def cnpj_valido(cnpj: str) -> bool:
    c = so_digitos(cnpj)
    if len(c) != 14 or len(set(c)) == 1:
        return False
    for n, pesos in ((12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]), (13, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])):
        resto = sum(int(c[i]) * pesos[i] for i in range(n)) % 11
        if int(c[n]) != (0 if resto < 2 else 11 - resto):
            return False
    return True


def tipo_do_documento(doc: str) -> str:
    """'cpf', 'cnpj' ou '' (quantidade de dígitos errada)."""
    return {11: "cpf", 14: "cnpj"}.get(len(so_digitos(doc)), "")


def documento_valido(doc: str) -> bool:
    t = tipo_do_documento(doc)
    return cpf_valido(doc) if t == "cpf" else cnpj_valido(doc) if t == "cnpj" else False


def formatar_documento(doc: str) -> str:
    d = so_digitos(doc)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return doc or ""


def conferir_certificado(info: dict, documento: str) -> str:
    """Compara o documento digitado com o do certificado. Devolve '' se está tudo certo ou a mensagem do problema.
    A SEFAZ só atende a consulta se o certificado for da mesma pessoa (CPF) ou da mesma empresa (mesma raiz de 8 dígitos do CNPJ)."""
    doc = so_digitos(documento)
    tipo = tipo_do_documento(doc)
    if not tipo:
        return "Informe um CPF (11 dígitos) ou um CNPJ (14 dígitos)."
    if not documento_valido(doc):
        return f"O {tipo.upper()} informado não é válido (confira os dígitos)."
    if not info.get("documento"):
        return ("Não encontrei o CPF nem o CNPJ dentro do certificado. A SEFAZ só aceita a consulta com um certificado e-CPF ou "
                "e-CNPJ (ICP-Brasil) A1.")
    if tipo == "cpf":
        if info.get("tipo") != "cpf":
            return "Você informou um CPF, mas o certificado é de uma empresa (e-CNPJ). Use o e-CPF, ou cadastre o CNPJ."
        if info["cpf"] != doc:
            return f"O CPF do certificado ({formatar_documento(info['cpf'])}) é diferente do CPF informado."
        return ""
    if info.get("tipo") != "cnpj":
        return "Você informou um CNPJ, mas o certificado é de uma pessoa (e-CPF). Use o e-CNPJ, ou cadastre o CPF."
    if info["cnpj"][:8] != doc[:8]:
        return f"O CNPJ do certificado ({formatar_documento(info['cnpj'])}) é de outra empresa."
    return ""


def emp_do_responsavel(resp: dict) -> dict:
    """Dados mínimos para o controle de NSU/bloqueio do responsável (a SEFAZ conta as consultas por quem consulta)."""
    return {"nome": f"Responsavel {resp.get('nome') or ''}".strip(), "cnpj": so_digitos(resp.get("documento", ""))}


def empresas_que_enviaram(docs: list, responsavel_doc: str, cadastradas: list = ()) -> list:
    """Empresas que aparecem como EMITENTES das NF-e completas recebidas pelo responsável (as que o citaram no autXML).
    A SEFAZ não informa 'quais empresas este certificado acessa': esta lista vem do que de fato chegou nas consultas feitas aqui.
    Devolve [{documento, nome, qtd, ultima, cadastrada}] da mais recente para a mais antiga."""
    resp = so_digitos(responsavel_doc)
    cad = {so_digitos(e.get("cnpj", "")): e.get("nome", "") for e in cadastradas}
    por_emp, vistas = {}, set()
    for x in docs:
        if not x.get("xml"):
            continue
        try:
            d = nfe.parse_documento(x["xml"], x.get("schema", ""))
        except ET.ParseError:
            continue
        if d.get("kind") != "nfe" or not d.get("chave") or d["chave"] in vistas:
            continue
        vistas.add(d["chave"])
        emit = so_digitos(d.get("emitente_doc", ""))
        if not emit or emit == resp or so_digitos(d.get("tomador_doc", "")) == resp:
            continue                       # nota do próprio responsável (ou comprada por ele): não é de "empresa que o citou"
        r = por_emp.setdefault(emit, {"documento": emit, "nome": d.get("emitente_nome", ""), "qtd": 0, "ultima": ""})
        r["qtd"] += 1
        r["ultima"] = max(r["ultima"], (d.get("emissao") or "")[:10])
        if d.get("emitente_nome"):
            r["nome"] = d["emitente_nome"]
    saida = []
    for r in por_emp.values():
        r["cadastrada"] = r["documento"] in cad
        if r["cadastrada"] and cad[r["documento"]]:
            r["nome_cadastro"] = cad[r["documento"]]
        saida.append(r)
    return sorted(saida, key=lambda r: (r["ultima"], r["qtd"]), reverse=True)


def aviso_sem_autxml(qtd_docs: int, qtd_empresas: int) -> str:
    """Texto curto para a tela quando a consulta do responsável não trouxe empresa nenhuma."""
    if qtd_empresas:
        return ""
    if qtd_docs:
        return "Chegaram documentos, mas nenhuma NF-e completa de empresa que tenha citado este responsável."
    return ("Nenhuma NF-e chegou para este responsável ainda. Isso é esperado enquanto o emitente (o sistema que emite as notas do "
            "cliente) não incluir o CPF/CNPJ do responsável no autXML: só valem as notas emitidas depois disso.")


__all__ = ["ErroAdge", "so_digitos", "cpf_valido", "cnpj_valido", "tipo_do_documento", "documento_valido", "formatar_documento",
           "conferir_certificado", "emp_do_responsavel", "empresas_que_enviaram", "aviso_sem_autxml"]
