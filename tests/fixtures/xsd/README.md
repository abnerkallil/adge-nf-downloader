# XSD oficial da DPS/NFS-e Nacional (v1.01, produção)

Arquivos baixados sem alteração de
`https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/documentacao-atual/nfse-esquemas_xsd-v1-01-20260209.zip`
(09/02/2026, layout de produção vigente em 19/11/2026 — não o de produção restrita/homologação,
que já tem o grupo IBS/CBS do redutor social, ainda não válido em produção).

Usados por `tests/test_emissao_dps_xml.py` para validar de verdade o XML que `dps.montar_xml`
gera, em vez de confiar só na leitura da planilha de leiaute.

## Bug conhecido do XSD oficial

`TSSerieDPS` (em `tiposSimples_v1.01.xsd`) usa o padrão `^0{0,4}\d{1,5}$`. Regex do XML Schema
(W3C XSD Part 2) **não tem ancoragem** — `^` e `$` são caracteres literais, não início/fim de
string — então esse padrão, como está, só aceita um valor que contenha literalmente os caracteres
`^` e `$` (ex.: `"^1$"`), nunca uma série de verdade como `"1"`. É um erro de quem escreveu o XSD
(uso comum, mas errado, de uma sintaxe de regex Perl/PCRE num contexto XSD). `tests/fixtures/xsd_schema.py`
neutraliza esse padrão só em memória (nunca altera este arquivo) antes de validar, documentando o
porquê — nunca usar um valor com `^`/`$` literais numa DPS de verdade.
