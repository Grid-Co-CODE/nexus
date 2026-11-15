"""Quem recebe em cada área de um setor (15/11/2026).

Levi: "na parte de caixa de entrada nova demanda, quando escolher o setor chamados, vai ficar filtrado só" as duas pessoas
da garantia. A área (`temas_padrao.AREAS`: hoje "Chamados", dentro da Performance) é mais uma escolha de setor na Nova
demanda; aqui mora quem do setor recebe nela.

- Guardado em `<NEXUS_DADOS>/demandas/areas.json`: {"<setor_id>:<Área>": [código da pessoa (HMAC do e-mail), ...]}. Só
  códigos, nunca nomes nem e-mails (os nomes vêm do pessoal do Fracttal na hora, como na Nova demanda).
- Quem marca: o próprio setor ou o administrador, na aba Temas do setor (a mesma regra de quem mexe nos temas).
- Área sem ninguém marcado: recebe todo o setor (como antes). Com gente marcada, a Nova demanda mostra só ela, e a
  gravação (`demandas.abrir`) recusa outra pessoa.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)
_BRT = timezone(timedelta(hours=-3))
_TRAVA = threading.Lock()


def _arquivo(cfg) -> Path | None:
    if cfg.get("TESTING") and not cfg.get("NEXUS_DADOS"):
        return None
    from ..cadastro.ligacoes import DADOS_PADRAO
    return Path(cfg.get("NEXUS_DADOS") or DADOS_PADRAO) / "demandas" / "areas.json"


def chave(setor_id, area: str) -> str:
    return f"{int(setor_id)}:{' '.join(str(area or '').split())}"


def ler(cfg) -> dict[str, list[str]]:
    arq = _arquivo(cfg)
    try:
        d = json.loads(arq.read_text(encoding="utf-8")) if arq and arq.exists() else {}
    except (OSError, ValueError):
        log.error("Áreas das demandas: o areas.json não abriu; vale o setor inteiro.")
        return {}
    return {k: [str(h).lower() for h in (v.get("pessoas") if isinstance(v, dict) else v) or []] for k, v in d.items()}


def pessoas(cfg, setor_id, area: str) -> set[str]:
    """Os códigos de quem recebe na área; vazio = o setor inteiro."""
    return set(ler(cfg).get(chave(setor_id, area), []))


def areas_da_pessoa(mapa: dict[str, list[str]], setor_id, hmac: str) -> list[str]:
    """As áreas do setor em que a pessoa está marcada."""
    pre = f"{int(setor_id)}:"
    return [k[len(pre):] for k, hs in mapa.items() if k.startswith(pre) and str(hmac).lower() in hs]


def gravar(cfg, setor_id, area: str, hmacs, quem: str) -> list[str]:
    arq = _arquivo(cfg)
    if not arq:
        raise ValueError("Este Nexus não tem a pasta de dados (NEXUS_DADOS): nada foi gravado")
    lista = sorted({str(h).strip().lower() for h in hmacs or [] if str(h).strip()})
    with _TRAVA:
        try:
            d = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
        except (OSError, ValueError):
            d = {}
        d[chave(setor_id, area)] = {"pessoas": lista, "por": quem, "em": datetime.now(_BRT).isoformat(timespec="seconds")}
        arq.parent.mkdir(parents=True, exist_ok=True)
        tmp = arq.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(arq)
    log.info("Áreas das demandas: %s com %d pessoa(s), por %s.", chave(setor_id, area), len(lista), quem)
    return lista
