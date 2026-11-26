"""A agenda dos e-mails criados pela tela (25/11/2026): a cada rodada da fila (20 s, só na máquina que envia), o modelo
que tem a hora vencida hoje e ainda não entrou na fila monta as mensagens e entra. A chave de cada mensagem leva o dia
(`modelos.montar`), e a fila não aceita a mesma chave duas vezes: o reinício não manda de novo.

O modelo DESLIGADO na regra nem monta: a montagem lê a Visão do responsável, e não há por que gastá-la para registrar
"desligado" a cada dia (o registro diz o que saiu; a tela diz que está desligado)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from . import fila

log = logging.getLogger(__name__)
_FEITAS: set = set()          # (modelo, dia) que esta máquina já montou: não relê a Visão a cada 20 s


def rodar(cfg, agora: datetime | None = None) -> int:
    """Quantas mensagens entraram na fila nesta rodada."""
    from ..campo import emails_controle as EC
    from . import modelos
    agora = agora or datetime.now(timezone.utc)
    vig = modelos.vigentes(cfg)
    if not vig:
        return 0
    est = EC.ler(cfg, alvo=EC.NEXUS)
    if est["erro"] and not est["linhas"]:
        return 0                # sem saber se está desligado, não monta (a próxima rodada tenta)
    regras = EC.vigentes(est["linhas"], cfg.get("NEXUS_PESSOA_HMAC"), EC.NEXUS)
    n = 0
    for mid, m in vig.items():
        dia = modelos.devido(m, agora)
        if not dia or (mid, dia) in _FEITAS:
            continue
        r = regras.get(mid)
        if r is not None and not r["ligado"]:
            continue
        try:
            res = modelos.montar(cfg, m, agora, rodada=dia)
        except Exception:      # noqa: BLE001 — a Visão fora: tenta na próxima rodada
            log.exception("E-mails do Nexus: o modelo %s não montou", mid)
            continue
        for msg in res["mensagens"]:
            msg.pop("_quem", None)
            n += fila.enfileirar(cfg, msg, agora)
        _FEITAS.add((mid, dia))
        if res["avisos"]:
            log.warning("E-mails do Nexus: %s, %s: %s", mid, dia, "; ".join(res["avisos"])[:400])
    return n
