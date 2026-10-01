# Adge Group - NF Downloader

Programa **gratuito** para Windows que baixa as **NFS-e Nacional** (emitidas e recebidas) de uma empresa usando o
**certificado A1** dela, soma o faturamento do mês e salva os XMLs já renomeados e organizados.

- Roda **só no seu computador**. Não existe servidor, conta ou nuvem do projeto.
- O certificado é usado apenas para conversar com o ADN oficial (`adn.nfse.gov.br`), a API do governo.
- Cada empresa precisa do **próprio** certificado A1 (o ADN só entrega as notas do CNPJ do certificado).

## Instalar
1. Baixe o `.msi` mais recente na página de **Releases** do projeto no GitHub.
2. Dê duplo clique e siga o instalador. Ele traz tudo o que o programa precisa (não precisa instalar Python).
3. Abra **Adge Group - NF Downloader** pelo atalho da Área de Trabalho ou do Menu Iniciar.

> Como o instalador não é assinado digitalmente, o Windows pode mostrar "O Windows protegeu o computador"
> (SmartScreen). Clique em **Mais informações → Executar assim mesmo**. Assinatura de código é paga e fica para depois.

## Usar
1. Aba **Empresas salvas → Adicionar empresa**.
2. **Procurar...** o arquivo do certificado (`.pfx`/`.p12`), digite a senha e clique em **Validar certificado**
   (o CNPJ e o nome são preenchidos sozinhos e o app mostra a validade do certificado).
3. Marque o que baixar (**Serviço prestado**, **Serviço tomado**) e o que fazer: calcular o total, baixar os XMLs ou os dois.
4. Em **Onde salvar os XMLs**, escolha a pasta e a organização. Salve.
5. Selecione a empresa (ou dê duplo clique) → escolha o **mês** na lista (o ano atual vem do relógio do computador;
   para outro ano use **Alterar ano**, formato AAAA) → **Buscar notas**.
6. Confira o **faturamento** e a lista de notas. Clique em **Baixar XMLs para a pasta** para gravar.
   Também dá para **Copiar totais** ou **Exportar CSV** (abre no Excel).

O período é sempre do **primeiro ao último dia do mês** escolhido (28, 29, 30 ou 31).

## Organização dos arquivos
Por empresa você escolhe:
- **Padrão Adge**: `Cliente \ Departamento Fiscal \ Notas Fiscais \ AAAA \ MM-Mês` (nomes achados por aproximação;
  cria só o que faltar, nunca a pasta *Departamento Fiscal*);
- **Ano e mês**: `Pasta \ AAAA \ MM-Mês`;
- **Direto**: tudo na pasta escolhida.

Todas as notas ficam **direto na pasta do mês**, sem subpastas por tipo. Nome do arquivo:
`NOTA FISCAL DE SERVIÇO PRESTADO - EMITENTE para TOMADOR em DD-MM-AAAA no valor de R$1.234,56.xml`
(`SERVIÇO TOMADO` para as recebidas). O início do nome pode ser trocado por empresa
(ex.: `NOTA FISCAL DE SERVIÇO PRESTADO DE ALUGUEL`). Nunca sobrescreve arquivos: se já existir igual, ignora;
se for diferente com o mesmo nome, grava como `nome (2).xml`. Notas **canceladas** não são baixadas nem somadas.

## Segurança das senhas
- As senhas dos certificados são **cifradas** (AES via Fernet) e a chave fica no **Cofre do Windows**
  (Gerenciador de Credenciais), preso à sua conta do Windows. Nada é gravado em texto.
- Em **Configurações** dá para exigir uma **senha mestra** ao abrir o programa. Se esquecê-la, será preciso
  cadastrar as senhas dos certificados de novo.
- Os dados ficam em `%APPDATA%\AdgeGroup\NFDownloader`. O arquivo `.pfx` não é copiado: só o caminho é guardado.
- Nunca compartilhe o certificado nem a senha, e não envie `empresas.json` para ninguém.

## Limites desta versão
- Só **NFS-e Nacional** (prestado e tomado). **NF-e** (compra e venda) usa outro serviço da SEFAZ e fica para uma próxima versão.
- Só **XML** (o PDF/DANFSe exige captcha no portal e não há API oficial sem ele).
- O período usa a data de processamento da nota no ADN. O valor somado é o **valor do serviço (vServ)**,
  antes de retenções e deduções.
- Municípios que ainda não aderiram ao padrão nacional não aparecem no ADN.

## Para desenvolvedores
```
pip install -r requirements-build.txt
python -m unittest discover -s tests -p "test_*.py" -v   # núcleo e armazenamento
python tests/smoke_gui.py                                 # abre a janela e simula uma busca
python adge_nf_downloader.pyw                             # roda o programa
python setup.py bdist_msi                                 # gera o MSI (somente no Windows)
```
O MSI é gerado automaticamente pelo GitHub Actions (`.github/workflows/build.yml`): crie uma tag `v1.0.0`
e o instalador aparece na página de Releases.

Para ativar o aviso de versão nova, preencha `REPO_GITHUB` em `adge_nf/__init__.py` (ex.: `"usuario/adge-nf-downloader"`).

Licença MIT.
