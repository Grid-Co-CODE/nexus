"""canto_disco.py: um arquivo da pasta de dados do OS Creator escrito de uma vez só (31/10/2026, etapa 3 do canto central).

As cópias em disco do canto central (o catálogo de ativos, `ativos_disco.py`, e a lista de OS, `os_central.py`) e os estados
pequenos que sobrevivem ao reinício passam por aqui: escreve-se num rascunho AO LADO e troca-se de uma vez (`os.replace`, que
no mesmo disco é atômico). O servidor reinicia a cada push na `main` (~10 vezes por dia útil); quem reinicia no meio de uma
gravação nunca lê um arquivo pela metade, e uma gravação que falha no meio deixa a cópia de antes como estava. Era o
`ativos_disco._trocar_de_uma_vez` (etapa 2); virou comum na etapa 3 para não haver duas cópias da mesma regra.
"""
from __future__ import annotations

import os
import threading


def trocar_de_uma_vez(destino: str, escrever) -> None:
    """`escrever(rascunho)` escreve o arquivo inteiro num rascunho ao lado de `destino`, que então troca o de antes de uma vez
    (`os.replace`). O rascunho que sobrar de uma falha é apagado. Levanta o erro do disco para quem chama dizer onde (o estado
    de cada cópia guarda o motivo)."""
    tmp = "%s.%d.%d.tmp" % (destino, os.getpid(), threading.get_ident())
    try:
        os.makedirs(os.path.dirname(destino), exist_ok=True)
        escrever(tmp)
        os.replace(tmp, destino)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
