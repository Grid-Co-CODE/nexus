"""A casca: Início, troca de cadeira, saúde e o que todo template recebe (menu, cadeira)."""
import os
import subprocess
from functools import lru_cache

from flask import (Blueprint, abort, current_app, jsonify, redirect, render_template, request,
                   session)

from ..auth import next_seguro
from ..cadeiras import CADEIRAS
from ..torres import montar_menu, telas_com_conteudo

bp = Blueprint("casca", __name__)


@lru_cache(maxsize=1)
def _commit() -> str:
    """Commit em execução. No servidor vem de NEXUS_COMMIT; local, do git; sem git, 'local'."""
    if os.environ.get("NEXUS_COMMIT"):
        return os.environ["NEXUS_COMMIT"][:7]
    try:
        saida = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                               text=True, timeout=3, cwd=os.path.dirname(__file__))
        return saida.stdout.strip() or "local"
    except (OSError, subprocess.SubprocessError):
        return "local"


@bp.route("/")
def inicio():
    torres = current_app.extensions["nexus_torres"]
    total_telas = sum(len(t.telas) for t in torres)
    return render_template("inicio.html", torres=torres, total_telas=total_telas)


@bp.route("/cadeira", methods=["POST"])
def cadeira():
    escolhida = request.form.get("cadeira", "")
    if escolhida and escolhida not in CADEIRAS:
        abort(400)
    session["cadeira"] = escolhida or None
    return redirect(next_seguro(request.form.get("voltar")))


@bp.route("/saude")
def saude():
    # Público de propósito (monitoramento do servidor). Não diz nada além de "está de pé" e o commit.
    return jsonify(ok=True, commit=_commit())


def instalar_contexto(app) -> None:
    @app.context_processor
    def _contexto():
        blueprint = request.blueprint or ""
        torre_atual = blueprint.removeprefix("torre_") if blueprint.startswith("torre_") else None
        cadeira_id = session.get("cadeira")
        # O mapa de rotas não muda depois do boot: calcula uma vez, na primeira página.
        if "nexus_telas_prontas" not in app.extensions:
            app.extensions["nexus_telas_prontas"] = telas_com_conteudo(app)
        return {
            "menu": montar_menu(app.extensions["nexus_torres"], cadeira_id, torre_atual,
                                app.extensions["nexus_telas_prontas"]),
            "cadeira": CADEIRAS.get(cadeira_id) if cadeira_id else None,
            "cadeiras": list(CADEIRAS.values()),
            "caminho": request.path,
        }
