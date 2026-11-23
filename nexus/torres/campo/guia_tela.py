"""Usinas 360° › Guia do App de Campo (21/11/2026): a tela. O conteúdo é do App de Campo (`nexus/campo/guia_app.py`, o
pacote em `static/guia-app/`); aqui só o HTTP. Fica num módulo à parte, importado no fim do `__init__` da torre, porque
precisa do `bp` (como o `equipe_tela`).

O "incerto" de cada pergunta (o que o código não resolve sozinho e o PCM precisa conferir) só aparece para o
administrador e para quem é do setor PCM: o README do pacote pede ("o campo incerto é para o administrador e o PCM, não
para o técnico")."""
from flask import render_template, session

from ...auth import setor_telas
from ...cadastro import setor_ids as SID
from ...campo import guia_app as G
from . import TORRE, bp


def _ve_o_incerto() -> bool:
    if session.get("admin"):
        return True
    try:
        return ((setor_telas.acesso().get("setor") or {}).get("id")) == SID.PCM
    except Exception:            # noqa: BLE001 — sem saber o setor, não mostra
        return False


@bp.route("/guia-app")
def guia_app():
    g = G.carregar()
    return render_template("campo/guia_app.html", torre=TORRE, tela=TORRE.tela("guia-app"), guia=g,
                           ve_incerto=_ve_o_incerto())
