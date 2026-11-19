# Planilha modelo de lançamentos — emissão de notas (NFS-e Nacional)

Planilha usada para lançar várias notas de uma vez no módulo de emissão (V2.0) do ADGE NF
Downloader. É a mesma estrutura que `adge_nf/emissao/planilha_emissao.py` gera e importa — este
pacote (`gerar_planilha_modelo_completa.py`) só acrescenta, por cima do modelo oficial, duas
abas de apoio ("Instruções" e "Exemplo") e uma coluna "Conferir" para revisão humana. **A aba
"Lançamentos" nunca tem uma coluna a mais ou a menos do que `planilha_emissao.COLUNAS`** (exceto
"Conferir", que o importador ignora) — gerar de novo (`python gerar_planilha_modelo_completa.py`)
sempre busca a lista de colunas vigente no motor, então o modelo nunca fica desalinhado dele.

Arquivo gerado: `Planilha Modelo - Emissao de Notas.xlsx` (3 abas: Instruções, Lançamentos,
Exemplo).

## Dois jeitos de chegar numa planilha pronta para importar

1. **Abner preenche direto** a aba "Lançamentos" a partir do modelo baixado no app.
2. **Claude preenche**, numa conversa, a partir de um print, foto ou PDF que o Abner mandar com
   as notas do mês. É esse o fluxo que o procedimento abaixo descreve.

Os dois casos terminam no mesmo lugar: uma planilha `.xlsx` com a aba "Lançamentos" pronta para
importar no app (botão "Emitir Notas" → "Lançar por planilha").

## Procedimento para transcrever um print/PDF/foto na planilha (Claude)

Use isto sempre que o Abner mandar um documento do cliente (PDF, foto, print de tela, tabela
colada no chat) pedindo para preencher a planilha de lançamentos.

1. **Entenda o documento inteiro antes de preencher qualquer coisa.** Veja quantas linhas de
   nota existem, quais colunas o documento tem, e se há uma linha de total (que não vira
   lançamento) ou observações soltas fora da tabela.
2. **Confirme com o Abner, antes de preencher, qualquer coisa que o documento não deixe claro
   por si só** e que mude o resultado fiscal da nota — típico: qual perfil de serviço se aplica
   quando a empresa tem mais de um (ex.: locação residencial x não residencial) e o endereço por
   si só não garante a resposta. Se o Abner já respondeu isso na própria conversa (ex.: "todas são
   residenciais, menos uma"), aplique a resposta dele diretamente nas linhas correspondentes —
   não pergunte de novo, mas também não deixe de registrar isso na coluna "Conferir" de cada
   linha afetada, para ele conferir de relance.
3. **Preencha linha por linha, nunca em bloco por estimativa.** Para cada nota:
   - `Tomador (nome)` e `Documento (CPF ou CNPJ)`: copie exatamente como está no documento. Um
     campo composto (ex.: uma coluna "Inquilino" com nome, CPF, telefone e e-mail juntos) — pegue
     só o nome (primeira linha do texto) e o CPF/CNPJ embutido; não invente o que não está ali.
   - `Endereço`: opcional, mas preencha quando o documento trouxer (ajuda a identificar o imóvel
     em casos de locação, e ajuda na conferência).
   - `Valor`: o valor da nota. **Uma nota com valor 0, ou que o documento diga que não foi paga,
     continua na planilha** com valor 0 e o motivo em `Observações` — o sistema já exclui
     sozinho notas de valor 0 da emissão, mas o Abner precisa ver que ela existiu e por quê.
   - `Competência (AAAA-MM)` e `Data da prestação`: use o mês que o Abner informou para o lote
     (normalmente um só, para todas as notas); só preencha data exata se o documento trouxer uma
     data por nota.
   - `Perfil de serviço (nome, opcional)`: preencha só quando a empresa tiver mais de um perfil
     cadastrado **e** você souber, pelo documento ou pela resposta do Abner, qual se aplica a essa
     nota específica. Em branco, o sistema decide pelo tomador já cadastrado ou pergunta na tela —
     não é obrigatório preencher.
   - `Observações`: qualquer nota, dúvida ou ressalva do próprio documento de origem.
4. **Nunca invente dado que não esteja no documento nem tenha sido confirmado pelo Abner no
   chat.** Dado que falta (CPF ilegível, endereço cortado, nome sem sobrenome) fica em branco na
   coluna correspondente, com uma explicação curta em `Conferir` dizendo o que falta e, se for o
   caso, o que você decidiu fazer (ex.: "CPF não aparece no print, deixei em branco").
5. **Preencha `Conferir` sempre que algo não veio 100% direto do documento** — mesmo que você
   tenha resolvido sozinho com uma regra óbvia (ex.: separar nome e CPF de um campo composto) não
   precisa marcar; marque quando houve dedução, suposição ou resposta aplicada de uma pergunta
   anterior. Linha sem nada a conferir fica com a célula vazia.
6. **Bata o total.** Some os valores da planilha e confira contra o total que o documento de
   origem informa (quando houver uma linha de total), antes de entregar.
7. **Na resposta ao Abner**, não devolva só o arquivo: resuma quantas notas, o total, e liste
   pontualmente o que está marcado em "Conferir" — ele não deve precisar abrir a planilha inteira
   para saber o que checar.
8. **Retenção de PIS/COFINS/CSLL do lote inteiro é perguntada uma vez só, na tela do sistema, na
   hora de importar a planilha** (decisão do Abner, 19/11/2026) — não existe e não deve existir
   coluna de retenção nesta planilha. Se o Abner pedir uma coluna de retenção por nota, isso muda
   o lançamento manual, não este modelo; avise que a regra combinada hoje é "uma vez por lote".

## Dados reais x dados de teste

Esta pasta (e `/mnt/project-files/adge-nf-downloader-v2/planilha-modelo/`) guarda só o modelo e o
exemplo fictício. Uma planilha preenchida com notas reais de um cliente (ex.: o lote mensal da
Ferreira Maria) é entregue ao Abner na thread/pasta do cliente, nunca commitada no repositório.
