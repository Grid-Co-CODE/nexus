"""Quem está aprovado no Radar entra na Zeladoria do Nexus (Levi, 11/11/2026, na troca: "Aprovado no Radar entra").

O time da zeladoria se cadastrava no próprio Radar, e o HEAD aprovava na tela Usuários. No Nexus, quem vê uma torre é o
setor (Base → Acessos), e em 11/11/2026 9 dos 14 aprovados do Radar não tinham setor: entrariam e veriam só "Sem setor".
Agora o portão (`nexus/auth/setor_telas.acesso`) pergunta aqui: aprovado no `perfis` da cópia sem setor no Nexus vale
como do setor Zeladoria; com outro setor, ganha as telas da Zeladoria além das dele. O HEAD cuida do time pelo Radar,
sem depender do administrador do Nexus.

O portão roda a cada pedido de todo mundo, então isto nunca espera o banco: usa a cópia que já está em memória (a do
gravador, com a gravação ligada, ou a da leitura) e, sem nenhuma, pede a carga por trás e responde "não" até ela chegar.
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger(__name__)

_APROV = {"chave": None, "emails": frozenset(), "pedido_em": 0.0}
RECARGA_S = 60              # a carga por trás não se repete mais que uma vez por minuto
VELHA_S = 900


def _carregar_em_fundo(app) -> None:
    if app.config.get("TESTING") or time.time() - _APROV["pedido_em"] < RECARGA_S:
        return
    _APROV["pedido_em"] = time.time()

    def tarefa():
        from . import gravacao, leitura
        try:
            with app.app_context():
                if gravacao.ativo(app.config):
                    gravacao.do_app(app.config)
                else:
                    leitura.estado(app.config)
        except Exception:        # noqa: BLE001 — sem a cópia, ninguém entra por aqui; o setor continua valendo
            log.warning("zeladoria: a cópia não carregou para o acesso dos aprovados do Radar", exc_info=True)

    threading.Thread(target=tarefa, daemon=True, name="nexus-zeladoria-acesso").start()


def _estado_em_memoria(app) -> dict | None:
    from . import gravacao, leitura
    if gravacao.ativo(app.config):
        g = gravacao._DO_APP.get("g")
        if g is None:
            _carregar_em_fundo(app)
        return g.estado if g is not None else None
    # ausente ou velha (15 min; o portão é de todo mundo, a recarga é só para quem entra pelo Radar): recarrega por trás
    # e, enquanto isso, vale a velha
    if leitura._CACHE["estado"] is None or time.time() - leitura._CACHE["em"] > max(leitura.CACHE_S, VELHA_S):
        _carregar_em_fundo(app)
    return leitura._CACHE["estado"]


def aprovados(app) -> frozenset:
    """Os e-mails (minúsculos) aprovados no `perfis` da cópia que está em memória."""
    est = _estado_em_memoria(app)
    if est is None:
        return _APROV["emails"]
    perfis = est["abas"].get("perfis", [])
    chave = (id(est), id(perfis), est.get("versao"))
    if _APROV["chave"] != chave:
        _APROV.update(chave=chave, emails=frozenset(
            str(p.get("email") or "").strip().lower() for p in perfis
            if p.get("status") == "aprovado" and str(p.get("email") or "").strip()))
    return _APROV["emails"]


def aprovado(app, email: str | None) -> bool:
    e = str(email or "").strip().lower()
    return bool(e) and e in aprovados(app)


def telas(app) -> set[str]:
    """As chaves `zeladoria/<tela>` de todas as telas da torre."""
    torre = next((t for t in app.extensions.get("nexus_torres", []) if t.id == "zeladoria"), None)
    return {f"zeladoria/{t.id}" for t in torre.telas} if torre else set()


def esquecer() -> None:
    _APROV.update(chave=None, emails=frozenset(), pedido_em=0.0)
