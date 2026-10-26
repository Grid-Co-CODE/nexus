"""A ponte do inventário no `/os/_nexus/inventario` (26/10/2026): as rotas que falam com o Fracttal.

Por quê (ruling do controlador, 26/10, revisão da Task 5/6): o login do Fracttal mora no cookie `os_sessao`, gravado com
`Path=<raiz>/os` (`auth.os_cookie_path`). O navegador NÃO o manda para `/t/pcm/...`, então `estoque_da_sessao` chamado numa rota
`/t/pcm/...` seria sempre `SemLogin` em produção (os testes que trocam a função, ou que mandam o cookie à mão, não pegam isso).
Toda operação que precisa do login do Fracttal roda aqui, debaixo de `/os/_nexus/inventario/`, como a Engenharia faz com o
comentário da OS (`nexus/torres/oscreator/ponte.py`, `engenharia_comentar`). As páginas continuam em `/t/pcm/pecas/inventario/...`
e chamam a ponte por `fetch(nexusRota(...))` (`static/pcm-ponte-inventario.js`); o que só grava no livro do Nexus (registrar a
régua, "é a peça X", confirmar, descartar) fica em `/t/pcm`.

Cada rota daqui: só administrador e setor PCM (`pode_programar`), pedido só da própria página (`_de_outro_site`), o login do
Fracttal de quem apertou (`estoque_da_sessao`), e a resposta é JSON: `{"ok": true, "mensagem", "volta"}` ou `{"erro"}` com o status
(`erros.resposta`); sem login do Fracttal, 401 com `{"erro", "login"}` (o `/os/login` do OS Creator, com a volta à página). O
aviso do que foi feito vai na sessão do Nexus, e a página o mostra ao recarregar. O portão de login do Nexus vale (nada aqui é
público) e o do setor deixa passar `/os/_nexus/` (a régua de cada ação é o `pode_programar`).

Um blueprint só para o inventário (`bp`, prefixo `/os/_nexus/inventario`), registrado no app como o `bp_raiz` do OS Creator
(`registrar`), e cada tarefa põe as rotas dela num bloco próprio.
"""
from __future__ import annotations

from urllib.parse import quote, urlencode

from flask import Blueprint, current_app, jsonify, request, session

from ...dados import almoxarifado as A
from ...prefixo import na_raiz
from .. import telas
from . import curadoria, erros, quem, regua
from . import estoque as E

bp = Blueprint("pcm_inventario_ponte", __name__, url_prefix="/os/_nexus/inventario")


def registrar(bp_torre) -> None:
    """Registra a ponte no app, na raiz (o cookie do Fracttal só vai para /os; debaixo do `/t/pcm` a rota nunca o veria).
    Idempotente: registrar duas vezes (a torre e outro módulo) não levanta."""
    def _no_app(estado):
        if bp.name not in estado.app.blueprints:
            estado.app.register_blueprint(bp)
    bp_torre.record_once(_no_app)


# ── o que toda rota da ponte faz antes e depois ─────────────────────────────────────────────────────────────────────────
def _login(de: str) -> str:
    """O login do Fracttal do OS Creator (`/os/login`) com a volta à página de onde a pessoa saiu (`/os/_nexus/card/voltar`: o
    clone só devolve para /os/...). A mesma volta do comentário da Engenharia."""
    return na_raiz("/os/login") + "?next=" + quote("/os/_nexus/card/voltar?" + urlencode({"de": de}, safe="/"), safe="")


def _barrar():
    """None se a pessoa pode; senão a resposta 403. Só administrador e setor PCM, e só a partir de uma página do Nexus."""
    if not telas.pode_programar() or telas._de_outro_site():
        return jsonify({"erro": "Só administrador ou o setor PCM grava no Fracttal, e só pela página do Nexus. Nada foi "
                                "gravado."}), 403
    return None


def _com_o_fracttal(de: str, fazer, ao: str | None = None):
    """Roda `fazer(estoque)` com o login do Fracttal de quem apertou e devolve a resposta JSON (`ao`: o que se faz, para o texto
    do erro de rede, `erros.resposta`). `fazer` devolve o texto que a
    página mostra ao recarregar. Sem login do Fracttal na sessão (a senha de administrador não tem; ou o `os_sessao` não
    veio): 401 com o link do login. O que o Fracttal ou o livro recusam sobe pela tabela de `erros.resposta`."""
    barrado = _barrar()
    if barrado is not None:
        return barrado
    try:
        texto = fazer(E.estoque_da_sessao(current_app._get_current_object()))
    except (ValueError, OSError, E.Limite, E.SemLogin, E.ErroFracttal) as ex:
        status, msg = erros.resposta(ex, ao=ao)
        corpo = {"erro": msg}
        if status == 401:
            corpo["login"] = _login(de)
        return jsonify(corpo), status
    return texto


def _ok(chave_aviso: str, texto: str, de: str):
    session[chave_aviso] = texto
    return jsonify({"ok": True, "mensagem": texto, "volta": na_raiz(de)})


# ── a régua: gravar o acordado no Fracttal (Task 8) ─────────────────────────────────────────────────────────────────────
@bp.route("/regua/gravar", methods=["POST"])
def regua_gravar():
    """Manda o acordado registrado ao Fracttal, relê e anota (`regua.gravar_acordado`). Só o que está no livro vai: o formulário
    traz o almoxarifado, a peça e o acordado que a tela MOSTRAVA (`aco_min`, `aco_max`), só para conferir: se o registrado agora é
    outro, 409 "a régua mudou desde que você abriu a tela"."""
    f = request.form
    almox, item = A._id(f.get("almox")), A._id(f.get("item"))
    de = "/t/pcm/pecas/inventario/regua" + ("?" + urlencode({"almox": almox}) if almox else "")

    def gravar(est):
        if "aco_min" not in f or "aco_max" not in f:
            raise ValueError("A página não mandou o acordado que mostrava: recarregue a página. Nada foi enviado.")
        esperado = (regua.nivel(f.get("aco_min"), "O acordado que a tela mostrava, mínimo"),
                    regua.nivel(f.get("aco_max"), "O acordado que a tela mostrava, máximo"))
        return regua.gravar_acordado(current_app.config, almox, item, est, quem.do_pedido(), esperado=esperado)
    r = _com_o_fracttal(de, gravar, ao="regua")
    return r if not isinstance(r, str) else _ok("pcm_regua_aviso", r, de)


# ── a curadoria: cadastrar a peça nova no Fracttal (Task 9) ─────────────────────────────────────────────────────────────
@bp.route("/curadoria/cadastrar", methods=["POST"])
def curadoria_cadastrar():
    """Cria a peça no Fracttal (`criar_peca`, com o código reservado antes, sem duplicar) e grava a decisão `cadastrar`. As
    outras decisões da curadoria só gravam no livro e ficam em `/t/pcm/pecas/inventario/curadoria/decidir`."""
    f = request.form
    de = "/t/pcm/pecas/inventario/curadoria"
    r = _com_o_fracttal(de, lambda est: curadoria.decidir(
        current_app.config, str(f.get("contagem") or "").strip(), str(f.get("linha") or "").strip(), "cadastrar",
        sigla=f.get("sigla"), nome=f.get("nome"), unidade=f.get("unidade"), estoque=est, pessoa=quem.do_pedido())["texto"],
        ao="cadastro")
    return r if not isinstance(r, str) else _ok("pcm_curadoria_aviso", r, de)
