# Relatórios de atualização

Um arquivo por versão (`vX.Y.Z.md`), com tudo o que mudou e por quê. O texto desse arquivo vira o texto da Release
no GitHub, e a seção **Resumo** é o que aparece no aviso de atualização do programa.

## Como escrever o relatório de uma versão

1. Copie o arquivo da versão anterior e renomeie para a nova tag (por exemplo, `v1.4.0.md`).
2. Na seção `## Resumo`, uma linha por mudança, sempre neste formato:
   `- [NOVO] Nome do item (ITEM-NN): o que mudou em uma frase.`
   Os tipos aceitos são `NOVO`, `MELHORIA` e `CORREÇÃO`. O nome e o código precisam existir em `adge_nf/itens.py`.
3. Na seção `## Detalhes`, um bloco por item com **O que mudou** e **Por que**.
4. Se criou uma função nova, registre o próximo código livre em `adge_nf/itens.py` e na tabela abaixo.

Os testes (`tests/test_docs.py`) conferem o formato, os códigos e se existe relatório da versão atual.

## Códigos dos itens

| Código | Item |
| --- | --- |
| ITEM-01 | Empresas salvas |
| ITEM-02 | Certificado A1 e validação |
| ITEM-03 | Busca de notas por mês |
| ITEM-04 | Totais do período |
| ITEM-05 | Saldo líquido |
| ITEM-06 | Download dos XMLs |
| ITEM-07 | Organização das pastas |
| ITEM-08 | Escolher pasta de destino |
| ITEM-09 | Planilha Excel |
| ITEM-10 | Informações avançadas |
| ITEM-11 | Comparativo de regimes |
| ITEM-12 | Copiar totais |
| ITEM-13 | Senhas e senha mestra |
| ITEM-14 | Atualização do programa |
| ITEM-15 | Apagar dados salvos |
| ITEM-16 | Relatório do download (.txt) |
| ITEM-17 | Notas canceladas |
| ITEM-18 | Novidades no aviso de atualização |
| ITEM-19 | Boas-vindas da primeira abertura |
| ITEM-20 | Janela principal e configurações |
| ITEM-21 | Histórico de consultas |
| ITEM-22 | Modo escuro |
| ITEM-23 | Validade do certificado |
| ITEM-24 | Sobre o projeto e contato com a Adge |
| ITEM-25 | Mensagens e janelas de aviso |
| ITEM-26 | Créditos das notas tomadas |
| ITEM-27 | Busca de NF-e (modelo 55) |
| ITEM-28 | Ciência da Operação |
| ITEM-29 | Histórico de NF-e e limite da SEFAZ |
| ITEM-30 | Seleção do que entra nos relatórios |
| ITEM-31 | Planilha com NF-e e notas sem ciência |
| ITEM-32 | Regimes com mercadorias e ICMS |
| ITEM-33 | Operações e créditos por CFOP |
| ITEM-34 | Nota Fiscal Paulistana (Prefeitura de São Paulo) |
| ITEM-35 | Conferência entre Ambiente Nacional e Paulistana |
