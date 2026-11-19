"""Carrega o XSD oficial da DPS (`tests/fixtures/xsd/`, ver README.md ali) para validar de verdade
o XML que `dps.montar_xml` gera. Neutraliza em memória o bug conhecido do `TSSerieDPS` (padrão com
`^`/`$` literais, que torna o padrão insatisfazível por qualquer série real — ver README.md);
nunca grava essa correção em disco."""
from __future__ import annotations

import functools
from pathlib import Path

from lxml import etree

XSD_DIR = Path(__file__).parent / "xsd"
_PADRAO_SERIE_QUEBRADO = r"^0{0,4}\d{1,5}$"
_PADRAO_SERIE_CORRIGIDO = r"0{0,4}\d{1,5}"


@functools.lru_cache(maxsize=1)
def esquema_dps() -> etree.XMLSchema:
    tipos_simples = etree.parse(XSD_DIR / "tiposSimples_v1.01.xsd")
    for el in tipos_simples.iter("{http://www.w3.org/2001/XMLSchema}pattern"):
        if el.get("value") == _PADRAO_SERIE_QUEBRADO:
            el.set("value", _PADRAO_SERIE_CORRIGIDO)

    # XMLSchema precisa resolver os `xs:include` a partir de um parser que já tenha a árvore
    # corrigida em memória para tiposSimples; o jeito mais simples e robusto é registrar essa
    # árvore num resolvedor customizado pelo caminho original do arquivo.
    class _Resolvedor(etree.Resolver):
        def resolve(self, url, pubid, context):
            if url.endswith("tiposSimples_v1.01.xsd"):
                return self.resolve_string(etree.tostring(tipos_simples), context)
            return None

    parser = etree.XMLParser()
    parser.resolvers.add(_Resolvedor())
    dps_doc = etree.parse(str(XSD_DIR / "DPS_v1.01.xsd"), parser=parser)
    return etree.XMLSchema(dps_doc)
