"""A casca: Início, troca de cadeira e de tema, saúde e o que todo template recebe (menu, cadeira, tema)."""
import os
import subprocess
from functools import lru_cache

from flask import (Blueprint, abort, current_app, jsonify, redirect, render_template, request,
                   session)

from ..auth import next_seguro
from ..cadeiras import CADEIRAS
from ..torres import montar_menu, telas_com_conteudo

bp = Blueprint("casca", __name__)

# Tema (08/10/2026, Levi: "precisamos de um tema claro também"): o escuro navy é o padrão; o claro é escolha da pessoa,
# guardada no cookie (o servidor já desenha o <html data-tema> certo, sem piscar o tema errado ao carregar) e no
# localStorage do navegador (reserva, aplicada pelo _tema_cabeca.html). Cookie desconhecido ou ausente = escuro.
COOKIE_TEMA = "nexus_tema"
TEMAS = ("escuro", "claro")
UM_ANO_S = 365 * 24 * 3600


def tema_do_pedido() -> str:
    tema = request.cookies.get(COOKIE_TEMA, "")
    return tema if tema in TEMAS else "escuro"


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


@bp.route("/tema", methods=["POST"])
def tema():
    """A troca de tema sem JavaScript (o botão do topo é um formulário). Com JavaScript a troca é na hora, no navegador,
    que grava o mesmo cookie; aqui ele é gravado pelo servidor e a pessoa volta para a mesma tela."""
    escolhido = request.form.get("tema", "")
    if escolhido not in TEMAS:
        abort(400)
    resp = redirect(next_seguro(request.form.get("voltar")))
    # sem HttpOnly de propósito: o botão troca o tema no navegador e grava este mesmo cookie
    resp.set_cookie(COOKIE_TEMA, escolhido, max_age=UM_ANO_S, path="/", samesite="Lax",
                    secure=bool(current_app.config.get("SESSION_COOKIE_SECURE")))
    return resp


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
            # a volta do formulário do tema (sem JavaScript) para a mesma tela, com os filtros
            "caminho_completo": request.full_path.rstrip("?"),
            "tema": tema_do_pedido(),
        }
