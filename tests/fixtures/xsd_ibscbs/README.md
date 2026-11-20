# XSD oficial da DPS/NFS-e Nacional — produção RESTRITA/homologação (grupo IBS/CBS)

Arquivos baixados sem alteração de
`https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica/producao-restrita/esquemas_prod_restrita_20261020.zip`
("NFSe-ESQUEMAS_XSD-PRODREST-v1.01-20261020", página "Documentação Técnica (Homologação/testes)",
atualizada em 20/10/2026 — baixado em 20/11/2026).

Usado só por `tests/test_emissao_dps_xml.py` para validar o grupo `IBSCBS` da DPS (reforma
tributária, LC 214/2025 com redação da LC 227/2026). **Este grupo não existe** no XSD de produção
vigente em `tests/fixtures/xsd/` (ver README ali) — por isso é um pacote XSD separado, baixado de
uma página diferente do portal (produção restrita/homologação, não produção vigente). O resto da
DPS (prestador, tomador, serviço, valores normais) é idêntico entre os dois pacotes; só o grupo
IBSCBS muda.

Diferente do pacote de produção vigente, `tiposSimples_v1.01.xsd` deste pacote já corrige o bug do
padrão de `TSSerieDPS` sozinho (sem precisar do patch em memória que `xsd_schema.py` aplica para o
outro pacote) — por isso `esquema_dps_ibscbs()` não precisa desse patch.

Campos do leiaute v1.04.01 (planilha `AnexoVI-LeiautesRN_RTC_IBSCBS`) que ainda NÃO existem em
nenhum XSD oficial publicado (nem este, nem o de produção vigente) — confirmado por busca direta
neste pacote: `condominios`, `gPgtoVinc` (pagamento vinculado/PSP), `indZFMALC`, `indDoacao`,
`gEstornoCred`, `gPagAntecipado`. Esses campos ficam de fora da emissão (`dps.py` não monta), só
documentados em `config_schema.py` — não dá para validar contra um XSD que ainda não os aceita.
