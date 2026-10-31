"""canto_disco.py: um arquivo da pasta de dados do OS Creator escrito de uma vez só (31/10/2026, etapa 3 do canto central).

As cópias em disco do canto central (o catálogo de ativos, `ativos_disco.py`, e a lista de OS, `os_central.py`) e os estados
pequenos que sobrevivem ao reinício passam por aqui: escreve-se num rascunho AO LADO e troca-se de uma vez (`os.replace`, que
no mesmo disco é atômico). O servidor reinicia a cada push na `main` (~10 vezes por dia útil); quem reinicia no meio de uma
gravação nunca lê um arquivo pela metade, e uma gravação que falha no meio deixa a cópia de antes como estava. Era o
`ativos_disco._trocar_de_uma_vez` (etapa 2); virou comum na etapa 3 para não haver duas cópias da mesma regra.

O ARQUIVO PRESO (rodada 1 da revisão da 3.1+3.2): no Windows (o PC também grava as cópias), o antivírus ou o indexador seguram
por um instante o arquivo recém-escrito, e o `os.replace` seguinte falha com acesso negado. Visto no teste das pendentes mortas,
com uma gravação colada na outra: 2 de 8 rodadas, e a pendente que tinha saído da fila voltava no reinício. A troca tenta de
novo depois de cada espera de `ESPERAS_DA_TROCA` antes de desistir (no Linux do servidor isso não acontece).
"""
from __future__ import annotations

import os
import threading
import time

ESPERAS_DA_TROCA = (0.05, 0.2, 0.5)
_replace = os.replace                   # pelo nome do módulo, para o teste prender o arquivo


def trocar_de_uma_vez(destino: str, escrever) -> None:
    """`escrever(rascunho)` escreve o arquivo inteiro num rascunho ao lado de `destino`, que então troca o de antes de uma vez
    (`os.replace`; o arquivo preso por um instante, ver o topo, é tentado de novo). O rascunho que sobrar de uma falha é
    apagado. Levanta o erro do disco para quem chama dizer onde (o estado de cada cópia guarda o motivo)."""
    tmp = "%s.%d.%d.tmp" % (destino, os.getpid(), threading.get_ident())
    try:
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        escrever(tmp)
        for espera in ESPERAS_DA_TROCA + (None,):
            try:
                _replace(tmp, destino)
                break
            except PermissionError:
                if espera is None:
                    raise
                time.sleep(espera)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
