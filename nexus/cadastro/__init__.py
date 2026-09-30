"""Cadastro do Nexus: o BD_Operações fora da planilha (Fase 1: usinas, pessoas, equipes e listas).

Desenho aprovado pelo Levi em 29/09/2026: cadastro por esquema (cada campo declarado uma vez em esquema.py),
dado sensível cifrado campo a campo (o registro inteiro, no caso das pessoas), ensaio antes da virada.
Nesta fase o armazenamento é LOCAL (armazem.py); a API db_performace entra quando o Levi autorizar criar o
workbook, que é permanente (a API não apaga workbook).
"""
