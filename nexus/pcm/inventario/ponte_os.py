"""A ponte do inventário em `/os/_nexus/inventario/...`: as operações que precisam do login do Fracttal (26/10/2026, ruling
do controlador sobre a revisão das Tasks 5/6).

O JWT do Fracttal mora no cookie `os_sessao` do OS Creator embutido, gravado com `Path=<raiz>/os`
(`nexus/auth/__init__.py`, `os_cookie_path`): o navegador NUNCA o manda para `/t/pcm/...`. Uma rota da tela do PCM que
chamasse `estoque_da_sessao(app)` daria sempre `SemLogin` em produção, e os testes que trocam o `estoque_da_sessao` ou mandam
o cookie à mão não pegariam. Por isso gravar e continuar moram aqui, como o comentário da Engenharia
(`nexus/torres/oscreator/ponte.py`, `engenharia_comentar`): outro site, 403; quem não é do setor PCM (nem administrador),
403; sem o JWT, 401 com o link do login do Fracttal e a volta para a contagem. O portão de login do Nexus vale aqui como em
qualquer rota (nada em `ROTAS_PUBLICAS`), e o portão dos setores deixa passar `/os/_nexus/` (quem decide é a rota).

O que não precisa do Fracttal fica em `/t/pcm/pecas/inventario/...` (`__init__.py`): as páginas, a revisão e o
`estado.json` da gravação. O blueprint é registrado na raiz pelo `registrar` do pacote, como o `bp_raiz` do OS Creator.
"""
from urllib.parse import quote, urlencode

from flask import Blueprint, current_app, jsonify, request, session

from ...prefixo import na_raiz

bp = Blueprint("pcm_inventario_ponte_os", __name__, url_prefix="/os/_nexus/inventario")

ENTRAR = "Para ler o saldo e gravar, entre pelo Fracttal."
SO_PCM = "Só o setor PCM grava o inventário no Fracttal."


def _login(contagem_id: str) -> str:
    """O login do Fracttal do próprio OS Creator (`/os/login`), com a volta para a contagem pelo `/os/_nexus/card/voltar`
    (o clone só devolve para /os/...), o mesmo caminho do card da OS e do comentário da Engenharia."""
    de = f"/t/pcm/pecas/inventario/{quote(contagem_id, safe='')}"
    return na_raiz("/os/login") + "?next=" + quote("/os/_nexus/card/voltar?" + urlencode({"de": de}, safe="/"), safe="")


def _email() -> str | None:
    usuario = session.get("usuario")
    return usuario.get("email") if isinstance(usuario, dict) else None


def _portao():
    """Outro site ou quem não é do PCM: a resposta de recusa; senão None."""
    from ...torres.moldura import _de_outro_site
    from ..telas import pode_programar
    if _de_outro_site():
        return jsonify(ok=False, erro="Pedido de outro site: nada foi gravado."), 403
    if not pode_programar():
        return jsonify(ok=False, erro=SO_PCM), 403
    return None


def _estoque(contagem_id: str):
    """O estoque com o login do Fracttal de quem está no pedido, ou a resposta 401 com o link do login. `E.estoque_da_sessao`
    pelo módulo, no momento do pedido."""
    from . import estoque as E
    try:
        return E.estoque_da_sessao(current_app._get_current_object()), None
    except E.SemLogin:
        return None, (jsonify(ok=False, erro=ENTRAR, login=_login(contagem_id)), 401)


def _recusa(ex):
    status = getattr(ex, "status", 503)
    return jsonify(ok=False, erro=str(ex)), status


@bp.route("/<contagem_id>/gravar", methods=["POST"])
def gravar(contagem_id):
    """O "Gravar N alterações": aprova o lote que a tela mostrou (`{"n": N}`) e começa a gravação no Fracttal, em segundo
    plano, no login de quem aprova. A tela acompanha pelo `estado.json`."""
    from ...dados import fato_inventario as F
    from . import estoque as E
    from . import gravacao as G
    from . import revisao as R
    recusa = _portao()
    if recusa:
        return recusa
    cfg = current_app.config
    pessoa = R.pessoa(cfg, _email())
    if pessoa is None:
        return jsonify(ok=False, erro=G.SEM_PESSOA), 409
    est, sem_login = _estoque(contagem_id)
    if sem_login:
        return sem_login
    corpo = request.get_json(silent=True)
    n = corpo.get("n") if isinstance(corpo, dict) else None
    try:
        d = G.aprovar(cfg, contagem_id, est, pessoa, n_visto=n)
    except E.SemLogin:
        return jsonify(ok=False, erro=ENTRAR, login=_login(contagem_id)), 401
    except F.Recusada as ex:
        return _recusa(ex)
    return jsonify(ok=True, mensagem="Gravação começada: acompanhe o andamento nesta página.", estado=d)


@bp.route("/<contagem_id>/continuar", methods=["POST"])
def continuar(contagem_id):
    """O "Continuar" da gravação parada (ou interrompida pelo Nexus reiniciando): só quem aprovou, no login dele."""
    from ...dados import fato_inventario as F
    from . import gravacao as G
    from . import revisao as R
    recusa = _portao()
    if recusa:
        return recusa
    cfg = current_app.config
    if G.estado(cfg, contagem_id) is None:
        return jsonify(ok=False, erro="Esta contagem não tem gravação para continuar."), 404
    if not G.e_o_aprovador(cfg, contagem_id, {"email": _email()}):
        return jsonify(ok=False, erro=f"Não continuei: {G.SO_QUEM_APROVOU}."), 403
    pessoa = R.pessoa(cfg, _email())
    if pessoa is None:
        return jsonify(ok=False, erro=G.SEM_PESSOA), 409
    est, sem_login = _estoque(contagem_id)
    if sem_login:
        return sem_login
    try:
        d = G.continuar(cfg, contagem_id, est, pessoa)
    except F.Recusada as ex:
        return _recusa(ex)
    return jsonify(ok=True, mensagem="Gravação retomada: acompanhe o andamento nesta página.", estado=d)
