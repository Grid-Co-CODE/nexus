"""Tela Base → Governança de dados: a matriz de barramento viva (do catálogo) e a qualidade da última carga.

Levi, 05/10/2026: "prioridade 0 para a governança e controle de dados". A tela mostra o que existe, de onde vem, o que
é cada linha (grão) e quanto de cada fato liga por ID. A qualidade vem do banco (`nexus_fatos · qualidade`, gravada pela
carga de hora em hora); sem ela, a tela mostra só o catálogo e avisa.
"""
import time
from datetime import datetime

from flask import current_app, render_template

from . import carga, catalogo, livros

_CACHE = {"t": 0.0, "v": None}
TTL_S = 300


def _ultima_qualidade():
    if _CACHE["v"] is not None and time.time() - _CACHE["t"] < TTL_S:
        return _CACHE["v"]
    import requests
    s = current_app.extensions.get("nexus_dados_sessao")
    if s is None and current_app.config.get("TESTING"):
        return {"qualidade": {}, "atualizacao": {}, "erro": "teste sem banco"}     # teste nunca vai à rede
    s = s or requests.Session()
    base = carga._base(current_app.config)
    try:
        q = {l.get("fato"): l for l in livros.ler(base, s, carga.LIVRO_FATOS, "qualidade")}
        at = next(iter(livros.ler(base, s, carga.LIVRO_FATOS, "atualizacao")), {})
        v = {"qualidade": q, "atualizacao": at, "erro": None}
    except Exception as e:      # noqa: BLE001 — banco fora do ar: a tela mostra o catálogo
        v = {"qualidade": {}, "atualizacao": {}, "erro": f"{type(e).__name__}"}
    _CACHE.update(t=time.time(), v=v)
    return v


def _hora(iso) -> str:
    try:
        return datetime.fromisoformat(str(iso)).strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return ""


def registrar_governanca(bp):
    @bp.route("/governanca")
    def governanca():
        v = _ultima_qualidade()
        grupos = {}
        for f in catalogo.FATOS:
            grupos.setdefault(f.area, []).append(f)
        return render_template("dados/governanca.html", torre=bp.name, catalogo=catalogo, grupos=grupos,
                               resumo=catalogo.resumo(), q=v["qualidade"], atualizacao=v["atualizacao"],
                               erro=v["erro"], hora=_hora)
