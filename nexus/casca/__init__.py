"""A casca: Início, troca de cadeira e de tema, saúde e o que todo template recebe (menu, cadeira, tema)."""
import os
import subprocess
from functools import lru_cache

from flask import (Blueprint, abort, current_app, jsonify, redirect, render_template, request,
                   session)

from ..auth import destino_seguro
from ..prefixo import raiz
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


def _telas_prontas(app) -> frozenset[str]:
    """As telas com conteúdo (o verde do menu), calculadas uma vez: o mapa de rotas não muda depois do boot."""
    if "nexus_telas_prontas" not in app.extensions:
        app.extensions["nexus_telas_prontas"] = telas_com_conteudo(app)
    return app.extensions["nexus_telas_prontas"]


@bp.route("/")
def inicio():
    """O Início, a primeira página de todos. Honesto (auditoria A3 da porta única, 10/10/2026): até então dizia "fase 0"
    e "Com dado real: 0" com 40 telas prontas no ar, e cada cartão abria a 1ª tela da torre, que em Comando, COS,
    Contratos e Relatórios é "Em construção". O número agora é o das telas prontas, pela mesma conta do verde do menu
    (`telas_com_conteudo`); o cartão leva à 1ª tela PRONTA da torre, e a torre sem nenhuma não vira link."""
    app = current_app._get_current_object()
    torres = app.extensions["nexus_torres"]
    prontas = _telas_prontas(app)
    cartoes = []
    for t in torres:
        urls = [f"/t/{t.id}/{s.id}" for s in t.telas]
        das_prontas = [u for u in urls if u in prontas]
        cartoes.append({"torre": t, "url": das_prontas[0] if das_prontas else None, "prontas": len(das_prontas)})
    return render_template("inicio.html", torres=torres, cartoes=cartoes, total_prontas=len(prontas),
                           total_telas=sum(len(t.telas) for t in torres))


@bp.route("/cadeira", methods=["POST"])
def cadeira():
    escolhida = request.form.get("cadeira", "")
    if escolhida and escolhida not in CADEIRAS:
        abort(400)
    session["cadeira"] = escolhida or None
    return redirect(destino_seguro(request.form.get("voltar")))


@bp.route("/tema", methods=["POST"])
def tema():
    """A troca de tema sem JavaScript (o botão do topo é um formulário). Com JavaScript a troca é na hora, no navegador,
    que grava o mesmo cookie; aqui ele é gravado pelo servidor e a pessoa volta para a mesma tela."""
    escolhido = request.form.get("tema", "")
    if escolhido not in TEMAS:
        abort(400)
    resp = redirect(destino_seguro(request.form.get("voltar")))
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
        return {
            "menu": montar_menu(app.extensions["nexus_torres"], cadeira_id, torre_atual, _telas_prontas(app)),
            "cadeira": CADEIRAS.get(cadeira_id) if cadeira_id else None,
            "cadeiras": list(CADEIRAS.values()),
            "caminho": request.path,
            # a volta do formulário do tema (sem JavaScript) para a mesma tela, com os filtros
            "caminho_completo": request.full_path.rstrip("?"),
            "tema": tema_do_pedido(),
            # o prefixo em que o Nexus roda ('' na raiz, '/nexus' no servidor): todo href/src/action absoluto dos templates
            # começa por ele, e o JavaScript o recebe em window.NEXUS_RAIZ (_raiz_js.html). Ver nexus/prefixo.py
            "raiz": raiz(),
        }
