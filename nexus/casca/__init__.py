"""A casca: Início, troca de tema, saúde e o que todo template recebe (menu, setor, tema). A cadeira saiu em 12/10/2026:
os setores (Base → Acessos) dizem o que cada pessoa vê."""
import os
import subprocess
from functools import lru_cache

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request

from ..auth import destino_seguro, setor_telas
from ..prefixo import raiz
from ..torres import montar_menu, telas_com_conteudo
# no topo, e não dentro do Início: o "no ar desde" do cartão da versão é a hora do import, a do boot (13/10/2026)
from . import versao

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
    (`telas_com_conteudo`); o cartão leva à 1ª tela PRONTA da torre, e a torre sem nenhuma não vira link.

    A aba Atualizações é `/?aba=atualizacoes` (13/10/2026): nasceu em /atualizacoes, e no servidor o Caddy só manda ao
    Nexus a raiz exata e os caminhos do Nexus (DEPLOY.md, 5b): /atualizacoes ia à plataforma, que respondia "Not Found"
    (tests/test_rotas_no_caminho_do_nexus.py)."""
    if request.args.get("aba") == "atualizacoes":
        return _atualizacoes()
    app = current_app._get_current_object()
    liberadas = setor_telas.liberadas_do_menu()
    # só as torres e as telas que o setor da pessoa vê (o administrador vê tudo)
    torres = [t for t in app.extensions["nexus_torres"]
              if liberadas is None or any(f"{t.id}/{s.id}" in liberadas for s in t.telas)]
    prontas = _telas_prontas(app)
    cartoes = []
    for t in torres:
        urls = [f"/t/{t.id}/{s.id}" for s in t.telas if liberadas is None or f"{t.id}/{s.id}" in liberadas]
        das_prontas = [u for u in urls if u in prontas]
        cartoes.append({"torre": t, "url": das_prontas[0] if das_prontas else None, "prontas": len(das_prontas),
                        "total": len(urls)})
    if liberadas is not None:
        prontas = frozenset(u for u in prontas if u[3:] in liberadas)
    return render_template("inicio.html", torres=torres, cartoes=cartoes, total_prontas=len(prontas),
                           total_telas=sum(len([s for s in t.telas if liberadas is None or f"{t.id}/{s.id}" in liberadas])
                                           for t in torres),
                           # a versão no ar: a hora do commit e desde quando está no ar; leva às Atualizações
                           # (casca/versao.py, 13/10/2026). Os pedidos presos saíram do cartão a pedido do Levi
                           # ("tire ... preso em 24hrs"): seguem no log, pelo casca/presos.py
                           versao=versao.cartao(app), aba="inicio")


def _atualizacoes():
    """A aba Atualizações do Início (13/10/2026, Levi: "Inclua no início uma sub aba de atualizações mostrando as últimas
    atualizações dos commits e o que mudou! Ao clicar em versão no ar já leva para lá!"): os últimos commits desta pasta,
    por dia, com o que mudou."""
    itens = versao.historico()
    return render_template("atualizacoes.html", dias=versao.dias(itens), total=len(itens), versao=versao.cartao(
        current_app._get_current_object()), aba="atualizacoes")


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
        a = setor_telas.acesso()
        return {
            "menu": montar_menu(app.extensions["nexus_torres"], torre_atual, _telas_prontas(app),
                                None if a["tudo"] else a["telas"]),
            # o setor da pessoa, no topo (Base → Integração Fracttal); o administrador sem setor não mostra nada
            "setor": a["setor"],
            "caminho": request.path,
            # a volta do formulário do tema (sem JavaScript) para a mesma tela, com os filtros
            "caminho_completo": request.full_path.rstrip("?"),
            "tema": tema_do_pedido(),
            # o prefixo em que o Nexus roda ('' na raiz, '/nexus' no servidor): todo href/src/action absoluto dos templates
            # começa por ele, e o JavaScript o recebe em window.NEXUS_RAIZ (_raiz_js.html). Ver nexus/prefixo.py
            "raiz": raiz(),
        }
