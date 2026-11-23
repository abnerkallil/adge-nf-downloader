"""Assinatura XML (enveloped XML-DSig, padrão DF-e) da DPS com o certificado A1 da empresa, do
mesmo jeito que `core.sessao_com_certificado`/`core.ler_certificado` já abrem o .pfx para a
consulta — aqui é a assinatura do CONTEÚDO da DPS, confirmada como obrigatória pela pesquisa da
API (`api-emissao.md`: assinatura própria do `infDPS`, separada do mTLS da conexão) e pelas regras
de negócio oficiais (`regras-negocio-dps.csv` nº 642/644-647: assinatura obrigatória para envio ao
Web Service, deve usar o certificado do emitente, E0714/E0716-E0718).

Algoritmo (RSA-SHA256/SHA256, C14N 1.1 — padrões do `signxml`): a pesquisa não achou essa definição
no leiaute nem na API; empiricamente a confirmar na produção restrita. Se a Sefin Nacional rejeitar
por algoritmo, trocar aqui (`signxml.XMLSigner(signature_algorithm=..., digest_algorithm=...)`)."""
from __future__ import annotations

from lxml import etree

from ..core import ErroAdge

NS_DS = "http://www.w3.org/2000/09/xmldsig#"


def assinar_dps(xml: str, pfx: str, senha: str) -> str:
    """Devolve o XML da DPS (de `dps.montar_xml`) com a assinatura embutida em `infDPS`, pronta
    para `transmissao.enviar`. Assinatura enveloped: `<Signature>` entra como último filho de
    `<DPS>` (irmão de `infDPS`, conforme o XSD oficial), referenciando o `Id` do `infDPS`."""
    return _assinar(xml, pfx, senha, "infDPS")


def assinar_pedido_evento(xml: str, pfx: str, senha: str) -> str:
    """Mesma lógica de `assinar_dps`, mas para o `<pedRegEvento>` (ex.: cancelamento de NFS-e,
    `eventos.montar_cancelamento_xml`) — `<Signature>` vira irmão de `infPedReg`, referenciando o
    `Id` dele (`TCPedRegEvt`/`TCInfPedReg`, mesmo padrão enveloped da DPS)."""
    return _assinar(xml, pfx, senha, "infPedReg")


def _assinar(xml: str, pfx: str, senha: str, elemento_a_referenciar: str) -> str:
    """Assinatura enveloped XML-DSig: `<Signature>` entra como último filho da raiz, referenciando
    o `Id` de `elemento_a_referenciar` (`infDPS` ou `infPedReg`, irmão dela no XSD oficial)."""
    from cryptography.hazmat.primitives.serialization import pkcs12
    from pathlib import Path
    import signxml

    try:
        dados = Path(pfx).read_bytes()
    except OSError as e:
        raise ErroAdge(f"Não consegui abrir o arquivo do certificado: {e}") from e
    try:
        chave, cert, _ = pkcs12.load_key_and_certificates(dados, senha.encode("utf-8") if senha else None)
    except Exception as e:
        raise ErroAdge("Senha incorreta ou arquivo de certificado inválido.") from e
    if chave is None or cert is None:
        raise ErroAdge("O arquivo do certificado não tem chave privada e certificado juntos.")

    root = etree.fromstring(xml.encode("utf-8"))
    inf = next((el for el in root if etree.QName(el).localname == elemento_a_referenciar), None)
    if inf is None:
        raise ErroAdge(f"XML sem o elemento {elemento_a_referenciar} - não há o que assinar.")
    id_inf = inf.get("Id")
    if not id_inf:
        raise ErroAdge(f"{elemento_a_referenciar} sem atributo Id - não há referência para a assinatura.")

    # Sem placeholder: sem um <Signature> já no documento, o signxml anexa o `<ds:Signature>`
    # gerado como último filho da raiz — exatamente onde o XSD espera (irmão do elemento referenciado).
    signer = signxml.XMLSigner(method=signxml.methods.enveloped,
                                signature_algorithm=signxml.SignatureMethod.RSA_SHA256,
                                digest_algorithm=signxml.DigestAlgorithm.SHA256)
    try:
        assinado = signer.sign(root, key=chave, cert=[cert], reference_uri=f"#{id_inf}")
    except Exception as e:
        raise ErroAdge(f"Falha ao assinar: {e}") from e
    # `encoding="unicode"` nunca inclui a declaração `<?xml version="1.0" encoding="UTF-8"?>` — a
    # Sefin Nacional recusa isso (erro E1229), mesmo com o conteúdo já em UTF-8 correto. A
    # declaração fica fora do que a assinatura cobre (C14N sempre a exclui), então isso não invalida nada.
    return etree.tostring(assinado, xml_declaration=True, encoding="UTF-8").decode("utf-8")
