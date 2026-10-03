# Adge Group - NF Downloader

Programa **gratuito** para Windows, criado pela [Adge](https://adge.com.br/), que baixa as **NFS-e Nacional**
(emitidas e recebidas) e, se a empresa quiser, as **NF-e (modelo 55)** de uma empresa usando o **certificado digital A1** dela. Ele soma o faturamento do mês,
calcula o saldo entre serviços prestados e tomados, salva os XMLs já renomeados e organizados em pastas, gera uma
planilha Excel do período e oferece uma análise avançada com gráfico e comparativo de regimes tributários.

- Funciona **somente no computador do usuário**. Não existe servidor, conta, nuvem nem coleta de dados.
- O certificado é usado apenas para se comunicar com o ADN oficial (`adn.nfse.gov.br`) e, se a NF-e estiver ligada, com a
  Distribuição de DF-e da SEFAZ (`nfe.fazenda.gov.br`), as APIs do governo.
- Cada empresa precisa do **próprio** certificado A1, pois o ADN só entrega as notas do CNPJ do certificado.

## Principais recursos
- Download dos XMLs de **serviços prestados** e **serviços tomados** de qualquer mês.
- Totais do período: faturamento, serviços tomados e **saldo líquido** (prestado − tomado, antes dos impostos),
  em verde quando positivo e vermelho quando negativo.
- **NF-e (modelo 55)**, opcional e desligada por padrão: compras, devoluções e (pelo **Responsável**) vendas entram no mesmo
  relatório, com marcas para escolher o que conta nos totais, no gráfico e na análise de regimes. Veja a seção **NF-e** abaixo.
- **Consulta de períodos em lote** (v1.7.5): uma caixa abaixo da lista de meses, desmarcada por padrão, inclui na mesma busca cada
  mês clicado. As fontes são consultadas uma vez só e o resultado mostra cada mês, com o total do lote; gravar salva todos.
- **RBT12 sugerido** (v1.7.5): em **Informações avançadas**, a receita dos 12 meses anteriores é sugerida a partir das NFS-e
  prestadas já baixadas na consulta, sem consulta extra (não inclui NF-e de mercadorias nem notas fora do Ambiente Nacional).
- **Responsável** (v1.7.6), primeira opção do menu lateral: cadastra o CPF ou o CNPJ de quem o emitente cita no autXML das notas
  (por exemplo, o contador) e o certificado A1 dele, para puxar as NF-e de venda. Veja a seção **Responsável** abaixo.
- **Nota Paulistana** (Prefeitura de São Paulo), busca separada do Ambiente Nacional, só para conferência. Veja a seção abaixo.
- Organização automática dos arquivos em pastas por cliente, ano e mês, com nomes padronizados.
- **Planilha Excel (.xlsx)** com aba geral colorida, abas separadas por tipo de nota e aba de notas canceladas.
- **Informações avançadas**: gráfico de pizza e comparativo de regimes adequado ao enquadramento da empresa
  (Simples: DAS unificado × regime regular de IBS/CBS; Presumido e Real: um contra o outro, hoje e com a reforma),
  com estimativa de créditos das notas tomadas.
- Cadastro de várias empresas em **cartões**, com senhas protegidas no Cofre do Windows e aviso de validade do certificado.
- **Histórico** das consultas salvas: reabre lendo a pasta onde as notas foram guardadas, sem consultar de novo.
- Visual claro ou **modo escuro**, com menu lateral e telas que se ajustam ao tamanho da janela.
- **Atualização dentro do programa**, com verificação de integridade do instalador.

## Instalação
1. Baixar o `.msi` mais recente na página de **Releases** do projeto no GitHub.
2. Dar duplo clique e seguir o instalador. Ele já inclui tudo o que o programa precisa (não é necessário instalar Python).
3. Abrir o **Adge Group - NF Downloader** pelo atalho da Área de Trabalho ou do Menu Iniciar.

> Como o instalador não é assinado digitalmente, o Windows pode exibir "O Windows protegeu o computador"
> (SmartScreen). Basta clicar em **Mais informações → Executar assim mesmo**. A assinatura de código é paga e
> fica para uma versão futura.

## Como usar
1. Na tela **Empresas**, clicar em **Adicionar empresa**.
2. Escolher o arquivo do certificado (`.pfx` ou `.p12`) em **Procurar...**, informar a senha e clicar em
   **Validar certificado**. O CNPJ e o nome da empresa são preenchidos automaticamente, e a validade do certificado é exibida.
3. Marcar o que será baixado (**Serviço prestado**, **Serviço tomado**) e a ação desejada: calcular o total,
   baixar os XMLs ou ambos.
4. Em **Onde salvar os XMLs**, definir a pasta e a forma de organização, e salvar.
5. No cartão da empresa, clicar em **Buscar notas** (ou dar duplo clique no cartão), escolher o **mês** na grade
   (o ano muda com ‹ e ›; há atalhos para **Mês anterior** e **Este mês**) e clicar em **Buscar notas**.
6. Conferir os totais e a lista de notas, que pode ser filtrada e ordenada. Em seguida, **Baixar XMLs para a pasta**
   grava os arquivos, **Exportar planilha** gera o Excel e **Copiar totais** leva o resumo para a área de transferência.

Atalhos: **Ctrl+N** adiciona uma empresa e **Enter** abre a busca da empresa selecionada. A tela **Histórico** lista as
últimas 30 consultas **salvas** em pasta e reabre cada uma lendo os XMLs dessa pasta (**Abrir**), sem consultar nada de novo.
Fechar a busca sem salvar mostra um aviso: consulta não salva não entra no histórico. Em **Configurações** ficam o
modo escuro, a senha mestra, as pastas e as atualizações; em **Sobre**, a apresentação do projeto e os links para avaliar.

O período é sempre do **primeiro ao último dia do mês** escolhido (28, 29, 30 ou 31).

## NF-e (modelo 55)
Na empresa, a opção **NF-e (modelo 55)** vem desligada; ao ligar, um aviso explica o que muda. A consulta usa a
Distribuição de DF-e do Ambiente Nacional da SEFAZ, com o mesmo certificado A1. Ela traz as notas **tomadas** (compras e
devoluções): a SEFAZ **não** entrega à empresa as NF-e que ela mesma emite (veja **Responsável**).
- **Consulta por sequência (NSU)**, não por mês. O programa guarda o último NSU e baixa só o novo; depois filtra pelo mês escolhido.
- **Limite da SEFAZ**: sem nota nova, ela só libera outra consulta depois de cerca de 1 hora. O limite é da SEFAZ, não do programa.
  A tela mostra um contador e, enquanto a SEFAZ está bloqueada, a NF-e fica **desligada e travada** na busca (consultar de novo só
  reiniciaria a espera); ela volta sozinha quando o prazo acaba.
- **O NSU só avança ao salvar**: as notas e o último NSU entram no controle do programa quando os XMLs são salvos numa pasta. Quem
  consulta e sai sem salvar não perde nada, porque a próxima consulta recomeça do mesmo NSU. O horário de bloqueio da SEFAZ, porém,
  vale desde a consulta.
- **Ciência da Operação** (opção separada, desligada por padrão): registra o evento 210210 das compras para a SEFAZ liberar o XML completo.
  É um ato em nome da empresa; o aviso explica os riscos e que ele não é um risco fiscal por si só. Só a ciência é enviada.
- **Notas sem ciência** chegam só em resumo: ficam em aba separada da planilha e só entram nos totais se marcadas (como compra, pelo valor total).
- **Categorias** com marca: serviço prestado, serviço tomado, NF-e de venda, de compra, devoluções, outras operações e NF-e sem ciência.
  A seleção vale para cartões, tabela, saldo, gráfico, regimes e planilha. O CFOP decide a categoria; remessas, transferências e
  bonificações ficam em "outras operações" e não somam. O valor é o total da nota (vNF).

## Responsável (v1.7.6)
A SEFAZ não entrega a uma empresa as NF-e que ela mesma emite. Elas só chegam a quem o emitente cita na própria nota, no campo
**autXML** (CPF ou CNPJ, por exemplo o do contador). Por isso existe a primeira opção do menu lateral, **Responsável**:
- Cadastre o CPF (e-CPF) ou o CNPJ (e-CNPJ) do responsável e o certificado A1 dele. A página explica para que serve, pede três
  confirmações de ciência (autXML só vale para notas emitidas depois de configurado, autorização do cliente/LGPD, dados só locais)
  e confere se o certificado é mesmo do documento informado. **Sem necessidade de venda por autXML, não precisa cadastrar.**
- Tudo fica **só neste computador** (senha cifrada como as das empresas); nada vai a servidor da Adge. Desinstalar o programa não
  apaga esses dados: use **Remover responsável** ou **Apagar todos os meus dados salvos** antes.
- Na busca de cada empresa com NF-e ligada, **Certificado da NF-e** permite escolher **Da empresa** (compras, com ciência
  opcional), **Do responsável** (vendas e notas que o citam) ou **Os dois** (duas consultas à SEFAZ, cada uma com o seu NSU e
  o seu limite de 1 hora). As notas do responsável chegam de várias empresas juntas; cada busca separa as da empresa consultada.
- A SEFAZ e a Receita não informam "quais empresas este certificado acessa". A página lista as empresas que **de fato enviaram**
  NF-e citando o responsável, vistas nas consultas feitas neste computador, e marca quais já estão cadastradas.
- Limites: é preciso certificado **A1** (A3 não funciona) e o emitente (o sistema de emissão do cliente) precisa incluir o
  CPF/CNPJ no autXML; sem isso nenhuma nota chega.

## Nota Paulistana (conferência)
A chave **Nota Paulistana (Prefeitura de SP, só conferência)** fica no cadastro da empresa (Nova e Editar) e na janela de busca, e consulta o web service da própria prefeitura
(nfews.prefeitura.sp.gov.br), com o mesmo certificado A1. Serve para empresas da capital quando o sistema contábil e a Paulistana divergem.
- **Fonte separada**: as notas da Paulistana nunca se misturam com as do Ambiente Nacional e começam **desmarcadas** nos totais.
  Marcar as duas fontes ao mesmo tempo soma ambas.
- **Prestadas** vêm de ConsultaNFeEmitidas (a Inscrição Municipal é descoberta com ConsultaCNPJ) e **tomadas** de ConsultaNFeRecebidas,
  página a página (50 notas por página). Notas canceladas ou extraviadas ficam fora dos totais.
- **Conferência**: se há NFS-e do Ambiente Nacional na mesma busca, os avisos listam os números que aparecem só em uma das fontes
  (comparação por número, CNPJ da outra parte e valor).
- Se um lado falha (por exemplo, certificado sem acesso à Paulistana), o erro vira aviso e o resto da busca continua.

## Planilha Excel
A planilha é gerada na mesma pasta dos XMLs e contém:
- **Geral**: um resumo no topo (categoria, quantidade de notas, valor e canceladas) seguido de todas as notas, em verde
  quando o dinheiro entra na empresa (serviço prestado) e em vermelho quando sai (serviço tomado);
- **Prestado** e **Tomado**: uma aba por tipo, sem cores, cada uma com o próprio resumo;
- **Canceladas**: as notas canceladas no período, que não entram nos totais.

Arquivos existentes nunca são sobrescritos: se já houver uma planilha com o mesmo nome, a nova recebe o sufixo `(2)`.

## Informações avançadas
Depois de buscar as notas, o botão **Informações avançadas** abre:
- **Gráfico de pizza** do período, com legenda ao lado. O centro mostra o saldo líquido: o que entra soma, o que sai reduz, e muda
  a cada marca ligada ou desligada. Pode ser visto por cliente/fornecedor, por tipo de serviço
  (itens da Lei Complementar 116, lidos do código de tributação da própria nota) ou por prestado × tomado.
- **Comparativo de regimes**, sempre dentro do que faz sentido para a empresa:
  - **Simples Nacional**: manter o DAS unificado (IBS/CBS dentro do DAS) ou optar pelo regime regular de IBS/CBS
    (LC 214/2025, art. 41 §3º), em 2027 e em 2033. Lucro Presumido e Lucro Real só aparecem se a receita passar do limite do Simples.
  - **Lucro Presumido e Lucro Real**: um contra o outro hoje, em 2027 (CBS e IBS em transição) e em 2033 (IBS/CBS pleno).
    O Simples não é oferecido.
- **Créditos das notas tomadas**: estimados pelo item da LC 116 do serviço e pelo regime do fornecedor (a NFS-e não traz CFOP,
  que existe na NF-e de mercadorias), e usados no cálculo do Lucro Real e do IBS/CBS. Mostra também quanto do faturamento
  foi para clientes com CNPJ, que podem aproveitar crédito.

Na primeira vez, o programa solicita os dados fiscais da empresa (regime atual, receita e folha dos últimos 12 meses,
entre outros). Eles ficam salvos apenas no computador e, nas consultas seguintes, são exibidos para confirmação.

Trata-se de uma **simulação estimada**: não considera retenções, benefícios, créditos reais, RAT/terceiros nem tributação
de dividendos, e não substitui a análise de um contador. As alíquotas ficam em `adge_nf/regimes.py` (tabela `ALIQUOTAS`),
com a data de referência. A CBS de 2027 é uma estimativa até a alíquota oficial ser fixada.

## Organização dos arquivos
Para cada empresa é possível escolher:
- **Padrão Adge**: `Cliente \ Departamento Fiscal \ Notas Fiscais \ AAAA \ MM-Mês` (os nomes das pastas são localizados
  por aproximação; o programa cria apenas o que faltar e nunca cria a pasta *Departamento Fiscal*);
- **Ano e mês**: `Pasta \ AAAA \ MM-Mês`;
- **Direto**: tudo na pasta escolhida.

Se a pasta da empresa não tiver a estrutura esperada, o programa não trava: o botão **Escolher pasta...** na tela de
resultado permite indicar manualmente onde salvar.

Todas as notas ficam **direto na pasta do mês**, sem subpastas por tipo. Nome do arquivo:
`NOTA FISCAL DE SERVIÇO PRESTADO - EMITENTE para TOMADOR em DD-MM-AAAA no valor de R$1.234,56.xml`
(`SERVIÇO TOMADO` para as recebidas). O início do nome pode ser personalizado por empresa
(por exemplo, `NOTA FISCAL DE SERVIÇO PRESTADO DE ALUGUEL`). O programa nunca sobrescreve arquivos: se já existir um
igual, ele é ignorado; se for diferente e tiver o mesmo nome, é gravado como `nome (2).xml`.
Notas **canceladas** não são baixadas nem somadas.

## Atualizações
Ao abrir, o programa verifica (no máximo uma vez por dia) se há uma versão nova na página de Releases do projeto.
Quando há, é exibido um aviso com **o que mudou em cada versão nova**, item por item, no formato `Nome (ITEM-NN)` com o tipo
da mudança (Novo, Melhoria ou Correção), e um link para o relatório completo no GitHub. Quem pulou versões vê as novidades de todas elas.
As opções são:
- **Atualizar agora**: baixa o instalador, confere o código de verificação (SHA-256) publicado na Release, fecha o
  programa, instala a versão nova (o Windows pede permissão de administrador) e reabre. Empresas e senhas salvas são mantidas.
- **Lembrar depois**: o aviso volta em 3 dias.
- **Pular esta versão**: não avisa sobre essa versão; uma versão mais nova volta a avisar.

Em **Configurações** é possível desligar a verificação ou clicar em **Verificar agora**. Se o arquivo baixado não
corresponder ao código publicado, a instalação é cancelada. O programa nunca atualiza sozinho sem confirmação do usuário.

## Segurança e privacidade
- As senhas dos certificados são **cifradas** (AES via Fernet) e a chave fica no **Cofre do Windows**
  (Gerenciador de Credenciais), vinculada à conta do Windows. Nada é gravado em texto puro.
- Em **Configurações** é possível exigir uma **senha mestra** ao abrir o programa. Se ela for esquecida, será necessário
  cadastrar novamente as senhas dos certificados.
- Os dados ficam em `%APPDATA%\AdgeGroup\NFDownloader`. O arquivo `.pfx` não é copiado: apenas o caminho é guardado.
- O programa não envia informações para a Adge nem para terceiros. A única comunicação externa é com o ADN
  (para buscar as notas), com a SEFAZ (se a NF-e estiver ligada), com a Prefeitura de São Paulo (se a Paulistana estiver ligada)
  e com a página de Releases do GitHub (para verificar atualizações).
- O cadastro do **Responsável** (documento, nome, caminho do certificado e senha cifrada) segue a mesma regra: só neste computador.
- Nunca se deve compartilhar o certificado, a senha nem o arquivo `empresas.json`.

## Desinstalação
Desinstalar o programa **não apaga** as empresas, os certificados e as senhas salvos no computador.
Para removê-los, abrir **Configurações → Apagar todos os meus dados salvos** antes de desinstalar.

## Limites desta versão
- **NFS-e Nacional** (prestado e tomado) e **NF-e modelo 55**. NFC-e e CT-e ficam de fora. A classificação por CFOP, os pesos de crédito e
  as tabelas do Simples (Anexos I e II) são uma orientação: o contador confere.
- **NF-e de venda** só chega com o **Responsável** e se o emitente incluir o CPF/CNPJ dele no autXML (e só nas notas emitidas depois).
  Certificado A3 (token/cartão) não funciona: é preciso arquivo A1.
- Somente **XML**: o PDF/DANFSe exige captcha no portal e não há API oficial sem ele.
- O período usa a data de processamento da nota no ADN. O valor somado é o **valor do serviço (vServ)**,
  antes de retenções e deduções.
- Municípios que ainda não aderiram ao padrão nacional não aparecem no ADN.

## Sobre a Adge
A [Adge](https://adge.com.br/) é uma empresa de contabilidade. Este programa é uma **iniciativa sem fins lucrativos**, criada para
ajudar contadores e auxiliares de contabilidade no dia a dia, sem que precisem pagar por uma função básica a cada vez, e para resolver
problemas de pequenas empresas de forma gratuita.

Na primeira abertura, o programa mostra um cartão de boas-vindas com essa apresentação (ele pode ser revisto em
**Sobre**). Quem quiser contribuir pode deixar uma avaliação aqui no GitHub ou no perfil da Adge no Google.

## Para desenvolvedores
```
pip install -r requirements-build.txt
python -m unittest discover -s tests -p "test_*.py" -v   # núcleo, planilha, regimes, relatórios e armazenamento
python tests/smoke_gui.py                                 # abre a janela e simula uma busca
python adge_nf_downloader.pyw                             # executa o programa
python setup.py bdist_msi                                 # gera o MSI (somente no Windows)
```

### Itens e relatórios de atualização
Cada função do programa tem um código fixo (`ITEM-NN`), listado em `adge_nf/itens.py`. Cada versão tem um relatório em
`docs/atualizacoes/vX.Y.Z.md` (veja `docs/atualizacoes/README.md` para o formato). A seção **Resumo** vira o texto do aviso de
atualização do programa e o arquivo inteiro vira o texto da Release. Os testes conferem o formato e os códigos.

## Licença
MIT.
