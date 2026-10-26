"""A ponte do inventário com o login do Fracttal, no `/os/_nexus/inventario` (revisão das Tasks 5 e 6, 26/10/2026).

O defeito que criou este arquivo: o login do Fracttal mora no cookie `os_sessao`, que o Nexus grava com `Path=<raiz>/os`
(`nexus/auth/__init__.py`, `os_cookie_path`: "só os pedidos de /os trazem o cookie do OS Creator"). O navegador NÃO o manda para
`/t/pcm/...`, então o `estoque_da_sessao(app)` chamado numa rota de `/t/pcm` dava `SemLogin` SEMPRE em produção, e o Sistema do
inventário nunca aparecia. Os testes não pegaram: trocavam o `estoque_da_sessao` ou mandavam o cookie à mão.

A regra (a mesma da Engenharia, `torres/oscreator/ponte.py`, `/os/_nexus/engenharia/os/<id>/comentar`): TODA operação que precisa
do login do Fracttal roda numa rota debaixo de `/os/_nexus/inventario/...`, num blueprint na RAIZ do app (a torre PCM mora em
`/t/pcm`), registrado junto com a torre (`registrar`, idempotente). As páginas continuam em `/t/pcm/pecas/inventario/...` (abas,
menu, casca) e buscam ou gravam o que depende do Fracttal por `fetch(nexusRota("/os/_nexus/inventario/..."))`. O portão de login
do Nexus vale (nada aqui é público), e o setor PCM (`pode_programar`) também: o portão por setor só olha `/t/...`, e sem esta
checagem qualquer pessoa logada leria o saldo da empresa. O que NÃO precisa do Fracttal (a lista, a revisão, o `estado.json` da
gravação, registrar a régua, "é a peça X", confirmar, descartar) fica em `/t/pcm/...`.

Cada rota daqui: só administrador e setor PCM, pedido só da própria página (`_de_outro_site`), o login do Fracttal de quem pediu
(`estoque_da_sessao`); sem ele, 401 com `{"erro", "login"}` (o `/os/login` do OS Creator, com a volta à página). Cada tarefa põe as
rotas dela num bloco próprio: o lote da contagem (Tasks 5 e 6), a régua (Task 8), a curadoria (Task 9), a gravação (Task 7).
"""
from __future__ import annotations

import logging
from urllib.parse import quote, urlencode

from flask import Blueprint, current_app, jsonify, render_template, request, session

from ...dados import almoxarifado as A
from ...prefixo import na_raiz
from .. import telas
from . import curadoria, erros, quem, regua
from . import estoque as E

bp = Blueprint("pcm_inventario_ponte", __name__, url_prefix="/os/_nexus/inventario")
bp_raiz = bp                     # o nome que a Task 6 usou; um blueprint só

ENTRAR = "Para ler o saldo e gravar, entre pelo Fracttal."


def registrar(bp_torre) -> None:
    """Registra a ponte no app, na raiz (o cookie do Fracttal só vai para /os; debaixo do `/t/pcm` a rota nunca o veria).
    Idempotente: a aba Inventário e a torre chamam os dois, e registrar duas vezes não levanta."""
    def _no_app(estado):
        if bp.name not in estado.app.blueprints:
            estado.app.register_blueprint(bp)
    bp_torre.record_once(_no_app)


# ── o que toda rota da ponte faz antes e depois ─────────────────────────────────────────────────────────────────────────
def login_do_fracttal(volta: str) -> str:
    """O /os/login do OS Creator com a volta à página `volta` (um caminho do Nexus): o clone só devolve para /os/..., então a
    volta passa pelo /os/_nexus/card/voltar, que leva à tela de onde a pessoa saiu (a mesma do card da OS e da Engenharia)."""
    return na_raiz("/os/login") + "?next=" + quote("/os/_nexus/card/voltar?" + urlencode({"de": volta}, safe="/"), safe="")


_login = login_do_fracttal


def _sem_cache(resposta):
    """O saldo da empresa não fica guardado no navegador nem em quem estiver no meio."""
    resposta.headers["Cache-Control"] = "no-store"
    return resposta


def _json(corpo: dict, status: int):
    return _sem_cache(jsonify(corpo)), status


def _barrar():
    """None se a pessoa pode; senão a resposta 403. Só administrador e setor PCM, e só a partir de uma página do Nexus."""
    if not telas.pode_programar() or telas._de_outro_site():
        return jsonify({"erro": "Só administrador ou o setor PCM grava no Fracttal, e só pela página do Nexus. Nada foi "
                                "gravado."}), 403
    return None


def _com_o_fracttal(de: str, fazer, ao: str | None = None):
    """Roda `fazer(estoque)` com o login do Fracttal de quem apertou e devolve a resposta JSON (`ao`: o que se faz, para o texto
    do erro de rede, `erros.resposta`). `fazer` devolve o texto que a página mostra ao recarregar. Sem login do Fracttal na
    sessão (a senha de administrador não tem; ou o `os_sessao` não veio): 401 com o link do login. O que o Fracttal ou o livro
    recusam sobe pela tabela de `erros.resposta`."""
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


# ── o lote da contagem: o Sistema lido agora, o Δ, a situação e os seis grupos (Tasks 5 e 6) ─────────────────────────────
@bp.route("/<contagem_id>/lote")
def lote(contagem_id: str):
    """O pedaço da contagem aberta que depende do Fracttal, como HTML (`pcm/_inventario_lote.html`), para a página buscar por
    `fetch`. O Sistema vem do `estoque_da_sessao` DE VERDADE, com o login de quem pede (aqui o cookie `os_sessao` chega). O botão
    "Gravar N alterações" vem neste pedaço, com o N e a `assinatura` do lote que ele mostra (Task 7): o gravar os confere contra
    o saldo lido de novo, e quem só viu o contado não grava.

    200 o HTML; 401 sem o login do Fracttal, com o link para entrar (`login`); 403 de outro site ou de quem não é do setor PCM;
    404 contagem que não existe; 409 contagem que não se aprova ou fora do contrato (não há o que ler, e a cota do Fracttal é de
    toda a empresa); 429 a pausa do Fracttal; 502 o Fracttal que falhou ou os livros que não leram. Nunca 500 por culpa do
    Fracttal; o corpo dos erros é JSON `{"erro", "login"?}`."""
    from ...dados import fato_inventario as F
    from ..telas import _de_outro_site, pode_programar
    from . import gravacao as G
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
            return _json({"erro": ENTRAR, "login": login_do_fracttal(f"/t/pcm/pecas/inventario/{contagem_id}")}, 401)
        return _json({"erro": ex.mensagem}, 429 if ex.estado == "pausa" else 502)
    except F.Recusada as ex:
        return _json({"erro": str(ex)}, 502)
    return _sem_cache(current_app.make_response(render_template("pcm/_inventario_lote.html",
                                                                assinatura=G.assinatura(ctx["itens"]), **ctx)))


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


# ── a gravação da contagem no Fracttal: gravar, continuar, encerrar (Task 7) ─────────────────────────────────────────────
# Respostas em `{"ok", "erro"?, "login"?, "mensagem"?, "estado"?}`. Além do `_barrar` (403), a gravação confere a PESSOA: ela vai
# no nome de quem aprova (`pessoa_hmac`), então a senha de administrador, que não é uma pessoa, leva 409; e a conta do Fracttal
# do cookie tem de ser a da sessão do Nexus (o cookie do OS Creator sobrevive à troca de pessoa no mesmo navegador, e a gravação
# iria no nome de uma pessoa e no login de outra: 409, entre de novo).
OUTRA_CONTA = "A sessão do Fracttal é de outra conta; entre de novo pelo Fracttal."


def _de_volta(contagem_id: str) -> str:
    return f"/t/pcm/pecas/inventario/{quote(contagem_id, safe='')}"


def _email() -> str | None:
    usuario = session.get("usuario")
    return usuario.get("email") if isinstance(usuario, dict) else None


def _sem_login(contagem_id: str):
    return jsonify(ok=False, erro=ENTRAR, login=_login(_de_volta(contagem_id))), 401


def _estoque_da_pessoa(contagem_id: str):
    """(o estoque com o login do Fracttal de quem está no pedido, None) ou (None, a resposta de recusa): sem o JWT, 401 com o
    link do login; a conta do Fracttal que não é a pessoa do Nexus, 409. `E.estoque_da_sessao` pelo módulo, no momento do
    pedido (o teste que prova o cookie o deixa ser o de verdade)."""
    from ...torres.oscreator import ponte
    app = current_app._get_current_object()
    try:
        s = ponte.sessao_do_os(app)
    except Exception as ex:      # noqa: BLE001 — o clone do OS Creator que não sobe: nada foi gravado
        logging.error("inventário: a sessão do OS Creator não abriu: %s", type(ex).__name__)
        return None, (jsonify(ok=False, erro="O OS Creator não respondeu agora: tente de novo. Nada foi gravado."), 503)
    if not str(s.get("jwt") or ""):
        return None, _sem_login(contagem_id)
    conta = str((s.get("conta") or {}).get("email") or "").strip().lower()
    if not conta or conta != str(_email() or "").strip().lower():
        return None, (jsonify(ok=False, erro=OUTRA_CONTA, login=_login(_de_volta(contagem_id))), 409)
    try:
        return E.estoque_da_sessao(app), None
    except E.SemLogin:
        return None, _sem_login(contagem_id)


def _recusa(ex):
    """A `Recusada` da gravação traz o status (400, 403, 404, 409); a do livro, sem ele, é o banco que não respondeu (503)."""
    return jsonify(ok=False, erro=str(ex)), getattr(ex, "status", 503)


@bp.route("/<contagem_id>/gravar", methods=["POST"])
def gravar(contagem_id):
    """O "Gravar N alterações": aprova o lote que a tela mostrou (`{"n": N, "assinatura": ...}`, os dois obrigatórios, vindos do
    pedaço do `lote`) e começa a gravação no Fracttal, em segundo plano, no login de quem aprova. A tela acompanha pelo
    `estado.json` de `/t/pcm`."""
    from ...dados import fato_inventario as F
    from . import gravacao as G
    from . import revisao as R
    recusa = _barrar()
    if recusa:
        return recusa
    cfg = current_app.config
    pessoa = R.pessoa(cfg, _email())
    if pessoa is None:
        return jsonify(ok=False, erro=G.SEM_PESSOA), 409
    est, recusa = _estoque_da_pessoa(contagem_id)
    if recusa:
        return recusa
    corpo = request.get_json(silent=True)
    corpo = corpo if isinstance(corpo, dict) else {}
    try:
        d = G.aprovar(cfg, contagem_id, est, pessoa, n_visto=corpo.get("n"), assinatura_vista=corpo.get("assinatura"))
    except E.SemLogin:
        return _sem_login(contagem_id)
    except F.Recusada as ex:
        return _recusa(ex)
    return jsonify(ok=True, mensagem="Gravação começada: acompanhe o andamento nesta página.", estado=d)


def _da_contagem(contagem_id):
    """A gravação desta contagem existe e se lê? A resposta de recusa (404 sem gravação; 409 com o controle ilegível, e não
    "só quem aprovou", que ninguém sabe), ou None."""
    from ...dados import fato_inventario as F
    from . import gravacao as G
    try:
        if not G.existe(current_app.config, contagem_id):
            return jsonify(ok=False, erro="Esta contagem não tem gravação."), 404
    except F.Recusada as ex:
        return _recusa(ex)
    return None


@bp.route("/<contagem_id>/continuar", methods=["POST"])
def continuar(contagem_id):
    """O "Continuar" da gravação parada (ou interrompida pelo Nexus reiniciando): só quem aprovou, no login dele."""
    from ...dados import fato_inventario as F
    from . import gravacao as G
    from . import revisao as R
    recusa = _barrar() or _da_contagem(contagem_id)
    if recusa:
        return recusa
    cfg = current_app.config
    if not G.e_o_aprovador(cfg, contagem_id, {"email": _email()}):
        return jsonify(ok=False, erro=f"Não continuei: {G.SO_QUEM_APROVOU}."), 403
    pessoa = R.pessoa(cfg, _email())
    if pessoa is None:
        return jsonify(ok=False, erro=G.SEM_PESSOA), 409
    est, recusa = _estoque_da_pessoa(contagem_id)
    if recusa:
        return recusa
    try:
        d = G.continuar(cfg, contagem_id, est, pessoa)
    except F.Recusada as ex:
        return _recusa(ex)
    return jsonify(ok=True, mensagem="Gravação retomada: acompanhe o andamento nesta página.", estado=d)


@bp.route("/<contagem_id>/encerrar", methods=["POST"])
def encerrar(contagem_id):
    """O "Encerrar" da gravação parada que ninguém vai continuar (Levi, 26/10/2026): quem aprovou a qualquer hora, o
    administrador depois de 24 h parada, com o motivo (`{"motivo"}`), e só com o almoxarifado fora do modo 2, lido agora
    no Fracttal (por isso mora na ponte)."""
    from ...dados import fato_inventario as F
    from . import gravacao as G
    from . import revisao as R
    recusa = _barrar() or _da_contagem(contagem_id)
    if recusa:
        return recusa
    cfg = current_app.config
    pessoa = R.pessoa(cfg, _email())
    if pessoa is None:
        return jsonify(ok=False, erro=G.SEM_PESSOA), 409
    admin = bool(session.get("admin"))
    try:
        G.conferir_quem_encerra(cfg, contagem_id, pessoa, admin)      # antes do Fracttal: quem não pode nem chega lá
    except F.Recusada as ex:
        return _recusa(ex)
    est, recusa = _estoque_da_pessoa(contagem_id)
    if recusa:
        return recusa
    corpo = request.get_json(silent=True)
    motivo = corpo.get("motivo") if isinstance(corpo, dict) else None
    try:
        d = G.encerrar(cfg, contagem_id, est, pessoa, motivo, admin=admin)
    except E.SemLogin:
        return _sem_login(contagem_id)
    except F.Recusada as ex:
        return _recusa(ex)
    return jsonify(ok=True, mensagem="Gravação encerrada: as peças que faltavam ficaram de fora, com o motivo na auditoria.",
                   estado=d)
