"""Endereço antigo da ligação por ID do Campo com o cadastro. O código mora em `nexus/cadastro/ligacao_campo.py` desde
08/11/2026 (o mapa do desembaraço: a chave comum é do cadastro). Fica para os ramos em andamento que ainda importam
daqui; sai quando ninguém mais importar."""
from ..cadastro.ligacao_campo import (  # noqa: F401 (o que se importava daqui)
    SISTEMA_FRACTTAL, WORKBOOK_CADASTRO, _abas, _norm, codigo_da_pessoa, mapas, mapas_de, pessoa_id,
    pessoa_id_do_codigo, usina_id,
)
