# Planilha modelo de tomadores recorrentes — emissão de notas (NFS-e Nacional)

Planilha usada para cadastrar vários tomadores recorrentes de uma vez na aba "Tomadores
recorrentes" da tela "Configurar para Emissão de Notas" (V2.0.1) do ADGE NF Downloader. É a mesma
estrutura que `adge_nf/emissao/tomadores_planilha.py` gera e importa — gerar de novo
(`gerar_modelo_xlsx`) sempre busca a lista de colunas vigente no motor, então o modelo nunca fica
desalinhado dele.

Arquivo gerado: `Planilha Modelo - Tomadores.xlsx` (2 abas: Instruções, Tomadores).

## Dois jeitos de chegar numa planilha pronta para importar

1. **Abner preenche direto** a aba "Tomadores" a partir do modelo baixado no app (botão "Baixar
   modelo" na aba "Tomadores recorrentes").
2. **Claude preenche**, numa conversa, a partir de uma lista de clientes que o Abner mandar em
   lote. É esse o fluxo que o procedimento abaixo descreve.

Os dois casos terminam no mesmo lugar: uma planilha `.xlsx` com a aba "Tomadores" pronta para
importar no app (botão "Importar planilha" na aba "Tomadores recorrentes" da tela de
configuração).

## Só o nome é obrigatório

Todo o resto é opcional e **nunca trava a importação inteira** — uma linha com um campo opcional
em branco só limita o que aquele tomador consegue fazer sozinho:

- **Nome**: obrigatório.
- **Documento (CPF ou CNPJ)**: opcional, mas é preciso ter documento OU endereço completo
  (logradouro + município) — é por aí que a nota reconhece o tomador automaticamente.
- **Identificação na nota**: "Padrão da empresa" (em branco), "Só documento" ou "Documento e
  endereço completo" (esta última exige logradouro e município na mesma linha).
- **Perfil de serviço (nome, opcional)**: nome de um perfil já cadastrado na empresa. Em branco
  usa o perfil padrão. Nome que não bate com nenhum perfil cadastrado é avisado na prévia, mas o
  tomador é importado mesmo assim (com o perfil padrão).
- **CEP / Logradouro / Número / Complemento / Bairro / Município / UF / Código IBGE**: opcionais,
  exceto quando "Identificação na nota" = "Documento e endereço completo".
- **Endereço (texto livre)**, **Descrição** e **Informações complementares**: opcionais; em
  branco, o tomador usa o que está configurado no perfil de serviço.
- **Ativo (Sim/Não)**: em branco = Sim.

A linha vira erro (e é ignorada, sem travar as outras) só quando falta o nome, ou quando não há
documento nem endereço completo suficiente para identificar o tomador.

## Procedimento para transcrever uma lista de clientes na planilha (Claude)

Use isto sempre que o Abner mandar uma lista de clientes (print, PDF, tabela colada no chat)
pedindo para cadastrar vários tomadores de uma vez.

1. **Entenda a lista inteira antes de preencher.** Quantos clientes, que dados cada um tem, e se
   algum precisa de endereço completo (ex.: locação de imóvel) em vez de só documento.
2. **Confirme com o Abner, antes de preencher, qualquer coisa que a lista não deixe clara** e
   que mude qual perfil de serviço se aplica, quando a empresa tem mais de um.
3. **Preencha linha por linha.** Nunca invente documento, endereço ou código IBGE que não esteja
   na lista nem tenha sido confirmado pelo Abner no chat — deixe em branco.
4. **Na resposta ao Abner**, resuma quantos tomadores, e avise se algum ficou sem documento e sem
   endereço completo (esse não entra na importação) — ele confere na prévia do app antes de
   gravar, mas é bom já avisar.

## Dados reais x dados de teste

Esta pasta guarda só o modelo vazio. Uma planilha preenchida com tomadores reais de um cliente é
entregue ao Abner na thread/pasta do cliente, nunca commitada no repositório.
