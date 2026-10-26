"""A ponte do inventário com o login do Fracttal (revisão das Tasks 5 e 6, 26/10/2026).

O defeito que criou este arquivo: o login do Fracttal mora no cookie `os_sessao`, que o Nexus grava com `Path=<raiz>/os`
(`nexus/auth/__init__.py`, `os_cookie_path`: "só os pedidos de /os trazem o cookie do OS Creator"). O navegador NÃO o manda para
`/t/pcm/...`, então o `estoque_da_sessao(app)` chamado numa rota de `/t/pcm` dava `SemLogin` SEMPRE em produção, e o Sistema do
inventário nunca aparecia. Os testes não pegaram: trocavam o `estoque_da_sessao` ou mandavam o cookie à mão.

A regra (a mesma da Engenharia, `torres/oscreator/ponte.py`, `/os/_nexus/engenharia/os/<id>/comentar`): TODA operação que precisa
do login do Fracttal roda numa rota debaixo de `/os/_nexus/inventario/...`, num blueprint na RAIZ do app (a torre PCM mora em
`/t/pcm`), registrado junto com a torre (`registrar` no `__init__`). As páginas continuam em `/t/pcm/pecas/inventario/...` (abas,
menu, casca) e buscam o que depende do Fracttal por `fetch(nexusRota("/os/_nexus/inventario/..."))`. O portão de login do Nexus
vale (nada aqui é público), e o setor PCM (`pode_programar`) também: o portão por setor só olha `/t/...`, e sem esta checagem
qualquer pessoa logada leria o saldo da empresa. O que NÃO precisa do Fracttal (a lista, a revisão, o estado da gravação) fica em
`/t/pcm/...`.

Cada rota é um bloco abaixo, com o próprio cabeçalho (a gravação, a régua e a curadoria acrescentam os seus).
"""
from __future__ import annotations

from urllib.parse import quote, urlencode

from flask import Blueprint, current_app, jsonify, render_template

from ...prefixo import na_raiz

bp_raiz = Blueprint("pcm_inventario_ponte", __name__, url_prefix="/os/_nexus/inventario")


def login_do_fracttal(volta: str) -> str:
    """O /os/login do OS Creator com a volta à página `volta` (um caminho do Nexus): o clone só devolve para /os/..., então a
    volta passa pelo /os/_nexus/card/voltar, que leva à tela de onde a pessoa saiu (a mesma do card da OS e da Engenharia)."""
    return na_raiz("/os/login") + "?next=" + quote("/os/_nexus/card/voltar?" + urlencode({"de": volta}, safe="/"), safe="")


def _sem_cache(resposta):
    """O saldo da empresa não fica guardado no navegador nem em quem estiver no meio."""
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


def _json(corpo: dict, status: int):
    return _sem_cache(jsonify(corpo)), status


# ── o lote da contagem: o Sistema lido agora, o Δ, a situação e os seis grupos ─────────────────────────────────────────────
@bp_raiz.route("/<contagem_id>/lote")
def lote(contagem_id: str):
    """O pedaço da contagem aberta que depende do Fracttal, como HTML (`pcm/_inventario_lote.html`), para a página buscar por
    `fetch`. O Sistema vem do `estoque_da_sessao` DE VERDADE, com o login de quem pede (aqui o cookie `os_sessao` chega).

    200 o HTML; 401 sem o login do Fracttal, com o link para entrar (`login`); 403 de outro site ou de quem não é do setor PCM;
    404 contagem que não existe; 409 contagem que não se aprova ou fora do contrato (não há o que ler, e a cota do Fracttal é de
    toda a empresa); 429 a pausa do Fracttal; 502 o Fracttal que falhou ou os livros que não leram. Nunca 500 por culpa do
    Fracttal; o corpo dos erros é JSON `{"erro", "login"?}`."""
    from ...dados import fato_inventario as F
    from ..telas import _de_outro_site, pode_programar
    from . import estoque as E
    from . import revisao as R
    if _de_outro_site():
        return _json({"erro": "Pedido de outro site."}, 403)
    if not pode_programar():
        return _json({"erro": R.SO_PCM}, 403)
    app = current_app._get_current_object()
    # `E.estoque_da_sessao` pelo módulo, no momento do pedido: o teste que prova o cookie o deixa ser o de verdade, e os outros o
    # trocam pelo `EstoqueFalso`
    try:
        ctx = R.montar_lote(app.config, contagem_id, lambda id_almox: E.estoque_da_sessao(app).ler(id_almox), True)
    except R.Recusa as ex:
        return _json({"erro": ex.mensagem}, ex.status)
    except R.SemSistema as ex:
        if ex.estado == "sem_login":
            return _json({"erro": "Para ler o saldo e gravar, entre pelo Fracttal.",
                          "login": login_do_fracttal(f"/t/pcm/pecas/inventario/{contagem_id}")}, 401)
        return _json({"erro": ex.mensagem}, 429 if ex.estado == "pausa" else 502)
    except F.Recusada as ex:
        return _json({"erro": str(ex)}, 502)
    return _sem_cache(current_app.make_response(render_template("pcm/_inventario_lote.html", **ctx)))
