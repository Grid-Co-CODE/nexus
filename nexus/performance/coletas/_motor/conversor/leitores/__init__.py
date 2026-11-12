# -*- coding: utf-8 -*-
"""Lista de leitores (um por fonte). Fonte nova = um módulo aqui + uma linha em _MODULOS.

A ordem importa só no empate: o primeiro leitor que reconhece o arquivo fica com ele. Leitor que quebra ao importar
não derruba o app (os outros seguem) — o erro aparece na tela como aviso."""
import importlib

_MODULOS = [
    "sal",            # Portal Sal Energia (INV - GERAÇÃO, Irradiação diária) -> BD_Performance
    "apolo",          # SmartLogger (PerformanceData) e SCADA/datalogger da Apolo -> BD_Performance
    "huawei_emi",     # EMI da Huawei (Macaíba) -> BD_Performance
    "neowind",        # NeoWind / Inverter History da Cascavel (Sunpower) -> BD_Performance
    "fusion_mensal",  # Relatório mensal INV do portal -> BD_Thopen
    "polaris",        # Relatório de inversor diário (Polaris, Canarana), ETM das usinas Polaris -> BD_Thopen
]

ERROS = []


def carregar():
    out = []
    ERROS.clear()
    for m in _MODULOS:
        try:
            mod = importlib.import_module("conversor.leitores." + m)
        except Exception as e:                       # noqa: BLE001 — um leitor quebrado não pode derrubar os outros
            ERROS.append("Leitor %s não carregou: %s: %s" % (m, type(e).__name__, e))
            continue
        out += [cls() for cls in getattr(mod, "LEITORES", [])]
    return out
