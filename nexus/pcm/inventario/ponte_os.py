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
(`estoque_da_sessao`); sem ele, 401 com `{"erro", "login"}` (o `/os/login` do OS Creator, com a volta à página). O que GRAVA no
Fracttal (a régua, o cadastro da curadoria, gravar, continuar, encerrar) confere também a PESSOA (`_estoque_da_pessoa`): a senha de
administrador não é uma pessoa (409), e a conta do Fracttal do cookie tem de ser a pessoa da sessão do Nexus (409; a revisão final
de 27/10/2026 achou a régua e o cadastro sem essa conferência). Cada tarefa põe as rotas dela num bloco próprio: o lote da contagem
(Tasks 5 e 6), a régua (Task 8; desde 11/11/2026 também todos os acordados do almoxarifado de uma vez), a curadoria (Task 9; desde
12/11/2026 também as opções do Tipo e das Classificações, com a mesma conferência da pessoa), a gravação (Task 7).
"""
from __future__ import annotations

import logging
from urllib.parse import quote, urlencode

from flask import Blueprint, current_app, jsonify, render_template, request, session

from ...dados import almoxarifado as A
from ...prefixo import na_raiz
from .. import telas
from . import classificacao as CL
from . import curadoria, erros, quem, regua
from . import estoque as E

bp = Blueprint("pcm_inventario_ponte", __name__, url_prefix="/os/_nexus/inventario")

ENTRAR = "Para ler o saldo e gravar, entre pelo Fracttal."
SEM_PESSOA = ("Não sei quem está gravando no Fracttal: entre no Nexus com o seu login do Fracttal (o que se grava fica no nome de "
              "quem grava, e a senha de administrador não é uma pessoa). Nada foi gravado.")


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
    do erro de rede, `erros.resposta`). `fazer` devolve o texto que a página mostra ao recarregar. Passa pelo `_estoque_da_pessoa`,
    como a gravação: a senha de administrador (sem pessoa) leva 409, o `os_sessao` que não veio leva 401 com o link do login, e
    a conta do Fracttal que não é a pessoa da sessão do Nexus leva 409 (a régua e o cadastro iam no login de quem usou o navegador
    antes; a revisão final de 27/10/2026). O que o Fracttal ou o livro recusam sobe pela tabela de `erros.resposta`."""
    barrado = _barrar()
    if barrado is not None:
        return barrado
    est, recusa = _estoque_da_pessoa(de)
    if recusa:
        return recusa
    try:
        texto = fazer(est)
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
    outro, 409 "a régua mudou desde que você abriu a tela". Como no botão de todos (a re-revisão de 11/11/2026), 409 com a vez do
    almoxarifado presa por uma gravação de contagem ou com ele fora do modo 0 no Fracttal."""
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


@bp.route("/regua/gravar_todos", methods=["POST"])
def regua_gravar_todos():
    """O "Gravar no Fracttal todos os acordados deste almoxarifado" (11/11/2026, item 2 da 2ª rodada): `regua.iniciar_lote`, no
    login de quem apertou, com as recusas de sempre da ponte (`_com_o_fracttal`). O lote roda em segundo plano (a revisão de
    11/11/2026: no pedido, 100 peças levavam uns 2 min e o restart do deploy no meio deixava peças sem o evento): a resposta volta
    logo, e a página da régua acompanha o andamento. A gravação de contagem e o lote se excluem: com a vez do almoxarifado presa
    (uma gravação andando, ou parada no meio) ou o almoxarifado fora do modo 0 no Fracttal, 409, e nada é enviado. O controle do
    lote que o disco não deixa gravar é 503 com o porquê (o `iniciar_lote` não começa; a re-revisão de 11/11/2026: aqui chegava
    None, e a página levava um 500)."""
    almox = A._id(request.form.get("almox"))
    de = "/t/pcm/pecas/inventario/regua" + ("?" + urlencode({"almox": almox}) if almox else "")
    r = _com_o_fracttal(de, lambda est: regua.iniciar_lote(current_app.config, almox, est,
                                                           quem.colunas(current_app.config, quem.do_pedido())), ao="regua")
    if not isinstance(r, dict):
        return r
    return _sem_cache(jsonify({"ok": True, "mensagem": "Mandando os acordados ao Fracttal em segundo plano: acompanhe nesta "
                                                       "página.", "volta": na_raiz(de), "estado": r.get("estado")}))


# ── a curadoria: cadastrar a peça nova no Fracttal (Task 9) ─────────────────────────────────────────────────────────────
CURADORIA = "/t/pcm/pecas/inventario/curadoria"


@bp.route("/curadoria/cadastrar", methods=["POST"])
def curadoria_cadastrar():
    """Cria a peça no Fracttal (`criar_peca`, com o código reservado antes, sem duplicar) e grava a decisão `cadastrar`. As
    outras decisões da curadoria só gravam no livro e ficam em `/t/pcm/pecas/inventario/curadoria/decidir`. Desde 12/11/2026 o
    formulário traz também o Tipo e as Classificações (`tipo`, `classificacao_1`, `classificacao_2`: o id da opção, ou vazio
    para "sem"), conferidos contra as opções do Fracttal (a mesma cópia de 1 h da rota `classificacoes`) antes de criar: o id que
    não está nelas é 400 e nada vai ao Fracttal."""
    f = request.form
    grupos = {c: f.get(c) for c in CL.CAMPOS if f.get(c) is not None}
    r = _com_o_fracttal(CURADORIA, lambda est: curadoria.decidir(
        current_app.config, str(f.get("contagem") or "").strip(), str(f.get("linha") or "").strip(), "cadastrar",
        sigla=f.get("sigla"), nome=f.get("nome"), unidade=f.get("unidade"), estoque=est, pessoa=quem.do_pedido(),
        grupos=grupos, opcoes_grupos=lambda: CL.guardadas(est))["texto"], ao="cadastro")
    return r if not isinstance(r, str) else _ok("pcm_curadoria_aviso", r, CURADORIA)


@bp.route("/classificacoes")
def curadoria_classificacoes():
    """As opções do Tipo e das Classificações da peça (12/11/2026, item 3 da 2ª rodada), para a página da curadoria encher as
    três seleções do cadastrar: `{"ok", "opcoes": {campo: [{"id", "descricao", "chave"}]}}` (`classificacao.guardadas`, as das
    próprias peças do Fracttal, numa cópia de 1 h na memória do processo). As recusas de toda rota da ponte (`_com_o_fracttal`):
    403 de outro site ou de outro setor, 409 a senha de administrador (não é uma pessoa) e a conta do Fracttal de outra pessoa,
    401 sem o login do Fracttal, 429 e 502 do Fracttal. A página que não consegue as opções esconde as seleções e diz que o
    Tipo e a Classificação ficam para o Fracttal."""
    r = _com_o_fracttal(CURADORIA, lambda est: {"opcoes": CL.guardadas(est)})
    if not isinstance(r, dict):
        return r
    return _json({"ok": True, "opcoes": r["opcoes"]}, 200)


# ── as requisições de material: a fila, aceitar, recusar e o automático (12/11/2026, item 6 da 2ª rodada) ───────────────
# A página fica em /t/pcm/pecas/requisicoes (`requisicoes.registrar`) e busca aqui a lista (HTML pronto) e o que grava. As recusas
# de toda rota da ponte (`_com_o_fracttal`: 403 outro site ou setor, 409 a senha de administrador e a conta do Fracttal de outra
# pessoa, 401 sem o login); o passo do aceite que o Fracttal não fez vem como `{"erro"}` com o status dele (`requisicoes.Falhou`).
REQUISICOES = "/t/pcm/pecas/requisicoes"


def _dono(est) -> tuple[dict | None, dict | None]:
    """(a conta, o responsável) do Fracttal de quem está no pedido: a aprovação vai no nome da conta, e a saída leva o
    responsável. Achados pelo e-mail da sessão do Nexus (que a ponte já conferiu ser o da conta do Fracttal do cookie)."""
    from ...torres.oscreator import ponte
    from . import requisicoes as RQ
    try:
        nome = str((ponte.sessao_do_os(current_app._get_current_object()).get("conta") or {}).get("nome") or "")
    except Exception:        # noqa: BLE001 — o nome da sessão só completa o do catálogo
        nome = ""
    return RQ.conta_do_fracttal(_email(), nome), RQ.responsavel_de(est, _email())


def _falhou_ou(r, volta: str, chave_aviso: str):
    """A resposta da ponte para o aceite e a recusa: o passo que o Fracttal não fez (`{"erro"}` com o status dele; 401 com o
    link do login), ou o ok com o aviso que a página mostra ao recarregar (o `tom`: confirmado pela releitura ou não)."""
    if not isinstance(r, dict):
        return r
    if "falhou" in r:
        corpo = {"ok": False, "erro": r["falhou"]}
        if r["status"] == 401:
            corpo["login"] = _login(volta)
        return _json(corpo, r["status"])
    session[chave_aviso] = {"texto": r["mensagem"], "ok": bool(r.get("confirmada"))}
    return _json({"ok": True, "mensagem": r["mensagem"], "confirmada": bool(r.get("confirmada")), "volta": na_raiz(volta)}, 200)


@bp.route("/requisicoes")
def requisicoes_lista():
    """A fila das requisições (`requisicoes.montar`), como HTML (`pcm/_requisicoes.html`), para a página buscar por `fetch`."""
    from . import requisicoes as RQ
    cfg = current_app.config
    r = _com_o_fracttal(REQUISICOES, lambda est: {"d": RQ.montar(cfg, est, RQ.contexto(cfg, CL.mapa_guardado(est)))})
    if not isinstance(r, dict):
        return r
    from .. import telas as T
    return _sem_cache(current_app.make_response(render_template(
        "pcm/_requisicoes.html", d=r["d"], auto=RQ.estado_automatico(cfg), andando=RQ.andando(),
        raio_x=T._pode_ver("/t/engenharia/equipe/os/1"))))


@bp.route("/requisicoes/<id_req>/aceitar", methods=["POST"])
def requisicao_aceitar(id_req):
    """O "Aceitar" do PCM (`requisicoes.aceitar`, `por` "pcm"): `{"comentario"?}`. A aprovação, a saída ligada e a Entrega
    total de uma vez, no login de quem apertou."""
    from . import requisicoes as RQ
    cfg = current_app.config
    corpo = request.get_json(silent=True)
    corpo = corpo if isinstance(corpo, dict) else {}

    def fazer(est):
        conta, resp = _dono(est)
        try:
            return RQ.aceitar(cfg, est, id_req, por="pcm", ctx=RQ.contexto(cfg, CL.mapa_guardado(est)),
                              quem_=quem.colunas(cfg, quem.do_pedido()),
                              conta=conta, responsavel=resp, comentario=corpo.get("comentario") or "")
        except RQ.Falhou as ex:
            return {"falhou": ex.mensagem, "status": ex.status}
    return _falhou_ou(_com_o_fracttal(REQUISICOES, fazer, ao="requisicao"), REQUISICOES, "pcm_requisicoes_aviso")


@bp.route("/requisicoes/<id_req>/recusar", methods=["POST"])
def requisicao_recusar(id_req):
    """O "Recusar" (`requisicoes.recusar`): `{"comentario"}` obrigatório; sem saída. PROVA PENDENTE no Fracttal de verdade."""
    from . import requisicoes as RQ
    cfg = current_app.config
    corpo = request.get_json(silent=True)
    corpo = corpo if isinstance(corpo, dict) else {}

    def fazer(est):
        conta, _resp = _dono(est)
        try:
            return RQ.recusar(cfg, est, id_req, ctx=RQ.contexto(cfg, CL.mapa_guardado(est)),
                              quem_=quem.colunas(cfg, quem.do_pedido()), conta=conta,
                              comentario=corpo.get("comentario") or "")
        except RQ.Falhou as ex:
            return {"falhou": ex.mensagem, "status": ex.status}
    return _falhou_ou(_com_o_fracttal(REQUISICOES, fazer, ao="requisicao"), REQUISICOES, "pcm_requisicoes_aviso")


@bp.route("/requisicoes/automatico", methods=["POST"])
def requisicoes_automatico():
    """Aceita sozinho, em segundo plano e na sessão de quem pediu, as pendentes só de Rank B e C conhecidas
    (`requisicoes.iniciar_automatico`). A página pede ao abrir (e o botão "Aceitar agora"); a resposta volta logo, e a página
    acompanha o andamento. Com o livro do inventário que não se lê agora, não começa: sem saber das falhas, tentaria de novo
    as que o Fracttal já recusou."""
    from . import requisicoes as RQ
    cfg = current_app.config

    def fazer(est):
        ctx = RQ.contexto(cfg, CL.mapa_guardado(est))
        d = RQ.montar(cfg, est, ctx)
        if not d["livro_lido"]:
            raise erros.Conflito("O livro do inventário não se lê agora: o automático espera (sem ele não sei as falhas). "
                                 "Nada foi enviado.")
        conta, resp = _dono(est)
        return {"estado": RQ.iniciar_automatico(cfg, est, d["ids_sozinhas"], ctx=ctx, quem_=quem.colunas(cfg, quem.do_pedido()),
                                                conta=conta, responsavel=resp)}
    r = _com_o_fracttal(REQUISICOES, fazer, ao="requisicao")
    if not isinstance(r, dict):
        return r
    return _json({"ok": True, "mensagem": "Aceitando sozinho as de Rank B e C: acompanhe nesta página.",
                  "estado": r["estado"].get("estado")}, 200)


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


def _estoque_da_pessoa(volta: str):
    """(o estoque com o login do Fracttal de quem está no pedido, None) ou (None, a resposta de recusa). `volta`: a página a que o
    link do login devolve. Sem pessoa na sessão do Nexus (a senha de administrador), 409; sem o JWT, 401 com o link do login; a
    conta do Fracttal que não é a pessoa do Nexus, 409. `E.estoque_da_sessao` pelo módulo, no momento do pedido (o teste que
    prova o cookie o deixa ser o de verdade)."""
    from ...torres.oscreator import ponte
    if not str(_email() or "").strip():
        return None, (jsonify(ok=False, erro=SEM_PESSOA), 409)
    app = current_app._get_current_object()
    try:
        s = ponte.sessao_do_os(app)
    except Exception as ex:      # noqa: BLE001 — o clone do OS Creator que não sobe: nada foi gravado
        logging.error("inventário: a sessão do OS Creator não abriu: %s", type(ex).__name__)
        return None, (jsonify(ok=False, erro="O OS Creator não respondeu agora: tente de novo. Nada foi gravado."), 503)
    sem_login = (jsonify(ok=False, erro=ENTRAR, login=_login(volta)), 401)
    if not str(s.get("jwt") or ""):
        return None, sem_login
    conta = str((s.get("conta") or {}).get("email") or "").strip().lower()
    if not conta or conta != str(_email() or "").strip().lower():
        return None, (jsonify(ok=False, erro=OUTRA_CONTA, login=_login(volta)), 409)
    try:
        return E.estoque_da_sessao(app), None
    except E.SemLogin:
        return None, sem_login


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
    est, recusa = _estoque_da_pessoa(_de_volta(contagem_id))
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
    est, recusa = _estoque_da_pessoa(_de_volta(contagem_id))
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
    est, recusa = _estoque_da_pessoa(_de_volta(contagem_id))
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
