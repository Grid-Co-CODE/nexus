"""Torre Contratos e clientes: SLA, entregáveis e comunicação com cada cliente.

Telas vivas: **Contestações** (13/10/2026, Levi: "em contratos e clientes no Nexus pode ter um lugar para essas
contestações separando setores!"), pelo livro que o Dashboard Thopen grava no banco (nexus/contratos/contestacoes.py),
com o acompanhamento de cada demanda (15/10/2026: "Pegar para mim" e as atualizações do responsável,
nexus/contratos/tratamento.py), e **Acessos dos clientes** (14/10/2026, o login por pessoa do Dashboard Thopen:
nexus/contratos/acessos_clientes.py). As outras telas ainda caem no placeholder da casca: a view com a mesma rota vence
a genérica. Leia o CLAUDE.md desta pasta antes de mexer.
"""
import hmac
import logging
import secrets

from flask import abort, current_app, redirect, render_template, request, session

from ...contratos import acessos_clientes as AC
from ...contratos import contestacoes as CT
from ...contratos import tratamento as TR
from ..modelo import Tela, Torre

TORRE = Torre(
    id="contratos",
    nome="Contratos e clientes",
    ordem=60,
    icone="handshake",
    descricao="SLA, entregáveis e comunicação com cada cliente.",
    telas=[
        Tela("clientes", "Clientes",
             "Algum contrato está em risco de penalidade ou renovação?",
             "Gestão de contratos (a estruturar)"),
        Tela("contestacoes", "Contestações",
             "O que os clientes contestaram nos dashboards, e para qual setor?",
             "Dashboard Thopen: a contestação de cada dia, gravada cifrada no banco (livro thopen_contestacoes)"),
        Tela("acessos", "Acessos dos clientes",
             "Quem do cliente entra no Dashboard Thopen, e o que cada um vê?",
             "Contas por pessoa (livro nexus_acessos_clientes, cifrado); a senha, a pessoa define no painel"),
        Tela("onboarding", "Onboarding de cliente",
             "Em que etapa está a entrada do cliente novo?",
             "Checklist de onboarding do Nexus"),
        Tela("comunicacao", "Comunicação por cliente",
             "O que cada cliente quer receber, quando e por onde?",
             "Perfil de comunicação do Nexus (spec R13)"),
        Tela("portal", "Portal do cliente",
             "O que o cliente vê sobre as usinas dele?",
             "Texto público das ocorrências e relatórios"),
    ],
)

bp = TORRE.criar_blueprint(__name__)


_log = logging.getLogger(__name__)
_AVISO, _ERRO = "contestacoes_aviso", "contestacoes_erro"


def _sem_acento(txt) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(txt or "")) if unicodedata.category(c) != "Mn").strip().lower()


def _setores_visiveis() -> tuple:
    """Os setores de contestação que a sessão vê (Levi, 15/10/2026: "O setor só vê a contestação do próprio setor, exceto
    administrador"). Administrador: todos. Quem tem setor: só o de mesmo nome (os setores do Nexus se chamam
    Performance, COS e Zeladoria, como os das contestações); outro setor, nenhum. Portão por setor desligado
    (NEXUS_ACESSO_POR_SETOR=0, testes): todos, como antes."""
    if session.get("admin"):
        return tuple(s for s, _ in CT.SETORES)
    from ...auth import setor_telas as ST
    a = ST.acesso()
    if a.get("setor"):
        nome = _sem_acento(a["setor"].get("nome"))
        return tuple(s for s, _ in CT.SETORES if s == nome)
    return tuple(s for s, _ in CT.SETORES) if a.get("tudo") else ()


def _achar(linha_id: str):
    """(a contestação, as visíveis) — a linha só se é de um setor que a sessão vê; senão 404 (nem diz que existe)."""
    d = CT.contestacoes()
    vis = _setores_visiveis()
    for s in vis:
        for x in d["por_setor"].get(s) or []:
            if str(x["id"]) == str(linha_id):
                return x, d
    abort(404)


@bp.route("/contestacoes")
def contestacoes():
    """Uma aba por setor que a sessão vê (Performance, COS, Zeladoria), a contestação mais nova em cima: quando chegou, a
    usina, o dia contestado, o que o cliente contestou, quem é e como responder, a mensagem e o que ele via na tela
    naquele dia, se o Teams do setor recebeu o aviso e quem é o responsável (ou o "Pegar para mim"). A linha abre o card
    das atualizações. Nome, contato e mensagem só com a chave privada deste Nexus."""
    d = CT.contestacoes()
    vis = _setores_visiveis()
    setores = [(s, rot) for s, rot in CT.SETORES if s in vis]
    setor = request.args.get("setor") if request.args.get("setor") in vis else (setores[0][0] if setores else None)
    try:
        trat, trat_erro = TR.estado(), None
    except Exception as e:      # noqa: BLE001 — sem o livro do acompanhamento, a lista segue sem os responsáveis
        trat, trat_erro = {}, f"Não consegui ler o acompanhamento ({type(e).__name__})"
    lista = (d["por_setor"].get(setor) or []) if setor else []
    from ...auth import setor_telas as ST
    meu_setor = (ST.acesso().get("setor") or {}).get("nome") if not session.get("admin") else None
    return render_template("contratos/contestacoes.html", torre=TORRE, tela=TORRE.tela("contestacoes"), d=d,
                           setores=setores, setor=setor, lista=lista, trat=trat, trat_erro=trat_erro,
                           meu=TR.codigo(session.get("usuario")), admin=bool(session.get("admin")), meu_setor=meu_setor,
                           aviso=session.pop(_AVISO, None), erro=session.pop(_ERRO, None))


@bp.route("/contestacoes/<linha_id>/pegar", methods=["POST"])
def contestacao_pegar(linha_id):
    """'Pegar para mim': a pessoa do login vira a responsável pela demanda e volta à lista do setor."""
    from ..moldura import _de_outro_site
    if _de_outro_site():
        abort(403)
    x, _ = _achar(linha_id)
    try:
        TR.pegar(x["id"], x["setor"], session.get("usuario"), bool(session.get("admin")))
        session[_AVISO] = f"A contestação de {x['usina']} agora é sua."
    except TR.Recusada as e:
        session[_ERRO] = str(e)
    except Exception as e:      # noqa: BLE001 — banco fora: a tela diz, nada mudou
        _log.exception("Contestações: pegar a demanda %s não gravou", linha_id)
        session[_ERRO] = f"Não consegui gravar no banco ({type(e).__name__}). Nada mudou; tente de novo em instantes."
    from ...prefixo import na_raiz
    return redirect(na_raiz(f"/t/contratos/contestacoes?setor={x['setor']}"), code=303)


def _card(x, aviso="", erro="", texto=""):
    try:
        t = TR.estado().get(str(x["id"])) or {"responsavel": None, "atualizacoes": []}
        lido = None
    except Exception as e:      # noqa: BLE001 — banco fora: o card diz, sem um "nenhuma atualização" falso
        t, lido = {"responsavel": None, "atualizacoes": []}, f"Não consegui ler o acompanhamento ({type(e).__name__})"
    meu = TR.codigo(session.get("usuario"))
    resp = t["responsavel"]
    return render_template("contratos/_contestacao_card.html", x=x, t=t, resp=resp, lido=lido,
                           sou_resp=bool(resp and meu and resp["hmac"] == meu), admin=bool(session.get("admin")),
                           com_login=bool(meu), aviso=aviso, erro=erro, texto=texto,
                           setor_rot=dict(CT.SETORES).get(x["setor"], x["setor"]))


@bp.route("/contestacoes/<linha_id>/card")
def contestacao_card(linha_id):
    """O card por cima da lista (o pedaço de página que o <dialog> mostra): a contestação, o responsável e as
    atualizações com a data e a hora; o campo de escrever só para o responsável."""
    x, _ = _achar(linha_id)
    return _card(x)


@bp.route("/contestacoes/<linha_id>/atualizacao", methods=["POST"])
def contestacao_atualizar(linha_id):
    """Grava a atualização do responsável e devolve o card de novo (com a nova, ou com o motivo e o texto digitado)."""
    from ..moldura import _de_outro_site
    if _de_outro_site():
        abort(403)
    x, _ = _achar(linha_id)
    texto = request.form.get("texto") or ""
    try:
        TR.atualizar(x["id"], x["setor"], session.get("usuario"), texto)
    except TR.Recusada as e:
        return _card(x, erro=str(e), texto=texto)
    except Exception as e:      # noqa: BLE001 — banco fora: o texto digitado não se perde
        _log.exception("Contestações: a atualização da demanda %s não gravou", linha_id)
        return _card(x, erro=f"Não consegui gravar no banco ({type(e).__name__}). Tente de novo em instantes.",
                     texto=texto)
    return _card(x, aviso="Atualização salva")


# ── Acessos dos clientes (14/10/2026) ─────────────────────────────────────────────────────────────────────────────────
# chaves próprias na sessão: a tela Contestações usa _AVISO/_ERRO, e o aviso de uma não pode aparecer na outra
_AC_CODIGO, _AC_AVISO, _AC_LINK = "acessos_clientes_codigo", "acessos_clientes_aviso", "acessos_clientes_link"


def _codigo() -> str:
    if not session.get(_AC_CODIGO):
        session[_AC_CODIGO] = secrets.token_urlsafe(24)
    return session[_AC_CODIGO]


def _acessos(erro=None, status=200, form=None):
    d = AC.contas()
    resp = current_app.make_response((render_template(
        "contratos/acessos.html", torre=TORRE, tela=TORRE.tela("acessos"), d=d, admin=bool(session.get("admin")),
        carteiras=AC.CARTEIRAS, papeis=AC.PAPEIS, codigo=_codigo(), erro=erro, form=form or {},
        aviso=session.pop(_AC_AVISO, None), link=session.pop(_AC_LINK, None), horas=AC.CONVITE_HORAS), status))
    resp.headers["Cache-Control"] = "no-store"         # o link de definir senha aparece uma vez: nada de cópia em cache
    return resp


@bp.route("/acessos", methods=["GET", "POST"])
def acessos():
    """As contas do Dashboard Thopen: quem é, que carteiras vê, se está ativa, quando definiu a senha e se há link
    pendente. Só administrador age (nova conta, gerar link, desativar, reativar); POST só da própria página e com o código
    do formulário da sessão. O link aparece uma vez (guardado na sessão até a volta do 303)."""
    if request.method == "GET":
        return _acessos()
    from ..moldura import _de_outro_site
    if not session.get("admin"):
        return _acessos(erro="Só um administrador do Nexus cria e muda as contas.", status=403)
    if _de_outro_site():
        return _acessos(erro="Pedido de outro site: nada foi gravado.", status=403)
    certo, enviado = session.get(_AC_CODIGO) or "", request.form.get("codigo") or ""
    if not certo or not hmac.compare_digest(enviado.encode(), certo.encode()):
        return _acessos(erro="O formulário venceu (a sessão mudou desde que a tela abriu): abra a tela de novo. Nada foi "
                             "gravado.", status=403)
    acao, cid, quem = request.form.get("acao"), request.form.get("conta_id") or "", session.get("usuario")
    form = {}
    try:
        if acao == "criar":
            form = {"nome": request.form.get("nome") or "", "email": request.form.get("email") or "",
                    "carteiras": request.form.getlist("carteira"), "papel": request.form.get("papel") or "cliente"}
            conta, link = AC.criar(form["nome"], form["email"], form["carteiras"], form["papel"], quem)
            session[_AC_LINK] = {"link": link, "nome": conta["nome"], "email": conta["email"]}
            session[_AC_AVISO] = f"Conta de {conta['nome']} criada."
        elif acao == "link":
            link = AC.gerar_link(cid, quem)
            nome = next((c["nome"] or c["email"] for c in AC.contas()["contas"] if c["conta_id"] == cid), "")
            session[_AC_LINK] = {"link": link, "nome": nome, "email": ""}
            session[_AC_AVISO] = "Link novo gerado; o anterior deixou de valer."
        elif acao in ("desativar", "reativar"):
            AC.definir_status(cid, acao == "reativar", quem)
            session[_AC_AVISO] = ("Conta reativada. Se ela não lembra a senha, gere um link." if acao == "reativar" else
                               "Conta desativada: sai do painel em até 2 minutos.")
        else:
            raise AC.Recusada("Ação desconhecida: nada mudou.")
    except AC.Recusada as e:
        return _acessos(erro=str(e), status=400, form=form)
    except Exception as e:      # noqa: BLE001 — banco fora: a tela diz, o que foi digitado não se perde
        _log.exception("Acessos dos clientes: a ação %s não gravou", acao)
        return _acessos(erro=f"Não consegui gravar no banco ({type(e).__name__}). Nada mudou; tente de novo em instantes.",
                        status=502, form=form)
    from ...prefixo import na_raiz
    return redirect(na_raiz("/t/contratos/acessos"), code=303)
