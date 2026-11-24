"""Matriz explícita campo x cenário -> enviar/proibido/opcional, com a regra de negócio oficial de
cada um (Anexo I - SEFIN_ADN-DPS_NFSe-SNNFSe, versão de produção v1.01-20260209, baixado direto do
gov.br em 24/11/2026). Isto documenta - e `tests/test_matriz_campos.py` confere contra o XML real -
o princípio por trás do gerador: o que sai na nota vem do cadastro e é decidido pelas regras
oficiais, nunca escolhido no escuro.

Este app só suporta `tpEmit=1` (o próprio prestador emitindo) - por isso a matriz do prestador não
tem uma coluna de tpEmit: ela já é toda para esse único caso. As regras marcadas com "E" são
rejeições reais confirmadas (`Cód. Erro` da planilha oficial); "XSD" é limitação do leiaute, não
regra de negócio.
"""
from __future__ import annotations

# ----------------------------------------------------------------------------------- prestador
# `prest/*` quando o emitente da DPS é o próprio prestador (tpEmit=1, único fluxo suportado).
MATRIZ_PRESTADOR = {
    "CPF ou CNPJ": {
        "decisao": "enviar sempre",
        "regra": "Identificador obrigatório do prestador (TCInfoPrestador, choice).",
    },
    "NIF / cNaoNIF": {
        "decisao": "nunca enviar",
        "regra": "E0112/E0114 - com tpEmit=1 o prestador só pode ser identificado por CNPJ ou CPF, "
                 "nunca por NIF (esse caminho é só para prestador estrangeiro emitindo por si, fora "
                 "do escopo deste app).",
    },
    "IM (Inscrição Municipal)": {
        "decisao": "enviar se houver no cadastro",
        "regra": "Opcional no leiaute (minOccurs=0); E0116/E0119/E0120/E0124 decidem se pode/deve "
                 "existir conforme o CNC do município - depende de cadastro externo, não é possível "
                 "confirmar localmente.",
    },
    "xNome (nome/razão social)": {
        "decisao": "nunca enviar",
        "regra": "E0121 - redundante com o cadastro nacional do CNPJ/CPF quando o prestador é o "
                 "próprio emitente (confirmado em produção real, teste da Aparecida em 24/11).",
    },
    "end (endereço)": {
        "decisao": "nunca enviar",
        "regra": "E0128 - mesma lógica do xNome (confirmado em produção real, teste da Aparecida).",
    },
    "fone (telefone)": {
        "decisao": "enviar se houver no cadastro",
        "regra": "Sem proibição por tpEmit (só xNome/E0121 e end/E0128 são proibidos) - confirmado "
                 "comparando com nota real emitida manualmente pelo Abner, que traz o telefone.",
    },
    "email": {
        "decisao": "enviar se houver no cadastro",
        "regra": "Mesma observação do telefone - confirmado contra a nota real manual.",
    },
    "regTrib (opSimpNac, regEspTrib)": {
        "decisao": "enviar sempre",
        "regra": "Obrigatório no leiaute (TCRegTrib, sem minOccurs=0 em opSimpNac).",
    },
}

# ----------------------------------------------------------------------------------- tomador
# `toma/*` - o tomador nunca é o emitente neste app (tpEmit sempre 1), então as regras que dependem
# de "tomador=emitente" (E0222-E0237, tpEmit=2) não se aplicam aqui.
MATRIZ_TOMADOR = {
    "CPF/CNPJ/NIF/cNaoNIF": {
        "decisao": "enviar conforme o documento cadastrado",
        "regra": "TCInfoPessoa é um choice - um e só um identificador por tomador (CPF nacional, "
                 "CNPJ nacional, NIF estrangeiro ou cNaoNIF quando não há NIF a informar). Quando é "
                 "NIF, o endereço no exterior (end/endExt) é obrigatório (E0242) - implementado, "
                 "bloqueia com erro claro se faltar. PRECISA DE TESTE REAL - nunca usado com um "
                 "tomador estrangeiro de verdade.",
    },
    "xNome": {
        "decisao": "enviar sempre que houver nome cadastrado",
        "regra": "E0233 torna obrigatório quando o tomador tem NIF; para CPF/CNPJ não é proibido "
                 "nem a planilha manda omitir - mantido sempre, por utilidade (nome aparece na "
                 "DANFSe) e porque nenhuma regra impede.",
    },
    "end/endNac (endereço)": {
        "decisao": "obrigatório (bloqueia a emissão se faltar) quando tomador é CNPJ ou há "
                   "retenção do ISSQN pelo tomador; senão, enviar se o cadastro tiver endereço "
                   "estruturado completo",
        "regra": "Opcional no leiaute em geral, mas três regras de negócio oficiais podem torná-lo "
                 "obrigatório: E0235 (tomador identificado por CNPJ, com tpEmit=1 - sempre o nosso "
                 "caso), E0237 (ISSQN retido pelo tomador, tpRetISSQN=2) e E0234 (incidência do "
                 "ISSQN no domicílio do tomador, tabela MUN.INCID_INFO.SERV.). E0235/E0237 estão "
                 "implementados (bloqueiam a emissão com erro claro se faltar o endereço). E0234 "
                 "NÃO está implementado - conferida a planilha oficial inteira (341 subitens), só "
                 "o código 170501 (\"Fornecimento de mão-de-obra\") tem essa marcação, e este app "
                 "não oferece esse tipo de serviço hoje; risco residual muito baixo, mas avisar o "
                 "Abner se um dia um perfil de serviço usar esse código.",
    },
}

# ----------------------------------------------------------------------------------- totTrib
# `trib/totTrib` (Lei 12.741/2012) é um choice; a opção certa depende da situação da empresa
# perante o Simples Nacional (`prest.regime`).
MATRIZ_TOT_TRIB = {
    "mei": {
        "decisao": "indTotTrib = 0 (fixo)",
        "regra": "Único valor que o leiaute aceita para indTotTrib; E0710 proíbe pTotTribSN pro MEI.",
    },
    "simples": {
        "decisao": "pTotTribSN = aliquota_mes do cadastro (Configurar emissão → Empresa), x100",
        "regra": "E0712 proíbe indTotTrib pra ME/EPP optante; reaproveita a alíquota efetiva do "
                 "Simples do mês já cadastrada pro PGDAS-D (`cfg[\"simples\"][\"aliquota_mes\"]`) - "
                 "bloqueia a emissão com erro claro se estiver zerada/não preenchida, porque 0% "
                 "seria uma alíquota falsa, não \"sem estimativa\" (diferente do caso do não "
                 "optante, onde o Decreto 8.264/2014 permite 0%). PRECISA DE TESTE REAL com um "
                 "cliente do Simples - nunca testado contra a Sefin de verdade.",
    },
    "presumido": {
        "decisao": "pTotTrib (percentuais aproximados: federal configurável, estadual/municipal=0)",
        "regra": "E0713 proíbe indTotTrib E pTotTribSN pra quem não é optante do SN. Padrão federal "
                 "11,33% = PIS 0,65% + COFINS 3% + IRPJ 15%x32% (presunção) = 4,80% + CSLL 9%x32% = "
                 "2,88% (confirmado pelo Abner contra o valor do próprio portal manual, 24/11) - "
                 "editável por empresa em \"Configurar emissão\".",
    },
    "real": {
        "decisao": "mesma regra do presumido",
        "regra": "Lucro Real também é \"Não Optante\" do SN pros fins desta regra (E0713) - mesma "
                 "composição federal serve de ponto de partida, editável por empresa.",
    },
}
