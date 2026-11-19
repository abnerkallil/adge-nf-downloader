"""Motor de emissão de NFS-e Nacional (DPS -> ADN).

Lê a configuração fixa de cada empresa (``empresa["emissao"]``, schema em
``config_schema.py``) e lança notas a partir de três entradas possíveis:
digitação manual, planilha modelo (.xlsx) ou um documento do próprio cliente
(.xlsx/.csv/.pdf com tabela), sempre passando por uma tela de prévia antes de
qualquer transmissão.
"""
