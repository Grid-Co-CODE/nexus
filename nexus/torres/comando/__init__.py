"""Torre Comando: sala de comando, fila única de ações e o que pede decisão.

Insights e Caixa de entrada (03/11/2026; Levi: "construa o que você sugere", os setores conversando): o motor de regras
(nexus/comando/regras.py e motor.py) aponta o problema com evidência, ação e torre dona; a Caixa de entrada mostra o das
torres que o setor da pessoa vê; "Assumir" e "Concluir" gravam no livro nexus_insights (nexus/comando/estado.py). O sino
do topo (base.html) conta pela mesma cópia. As outras telas ainda caem no placeholder da casca. Para dar vida a uma tela, crie uma
view com a mesma rota (ela vence a genérica), por exemplo:

    @bp.route("/sala-de-comando")
    def sala_de_comando():
        return render_template("comando/sala-de-comando.html")
"""
import hmac
import secrets

from flask import abort, current_app, redirect, render_template, request, session, url_for

from ...comando import estado as ES
from ...comando import motor as MO
from ...comando import regras as RG
from ...prefixo import na_raiz
from ..modelo import Tela, Torre
from ..moldura import _de_outro_site

TORRE = Torre(
    id="comando",
    nome="Comando",
    ordem=0,
    icone="squares-four",
    descricao="Sala de comando, fila única de ações e o que pede decisão.",
    telas=[
        Tela("sala-de-comando", "Sala de comando",
             "Onde estou perdendo dinheiro esta semana e quem está segurando?",
             "Motor de correlação do Nexus + Performance, PCM e Fracttal"),
        Tela("caixa-de-entrada", "Caixa de entrada",
             "O que é meu para fazer hoje, por prazo e valor?",
             "Itens de trabalho do Nexus (insights, OS, chamados, solicitações)"),
        Tela("kanban", "Kanban",
             "Onde as ações nascidas no Nexus estão travando?",
             "Itens de trabalho do Nexus"),
        Tela("insights", "Nexus Insights",
             "Que regra cruzou as fontes e apontou um problema com dono?",
             "Regras R01 a R13 do motor de correlação"),
        Tela("usinas", "Usinas",
             "Qual é o prontuário de cada usina, com todos os apelidos?",
             "Registro mestre (BD_Performance, BD_Thopen e de-para, via API)"),
        Tela("metas", "Metas do book",
             "Quais KPIs do book R02 estão fora da meta e piorando?",
             "Aba KPIs do Plano de Documentação"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

_CODIGO, _AVISO = "insights_codigo", "insights_aviso"
# as áreas que se notifica: as torres de operação (o Comando e o OS Creator não recebem pedido)
FORA_DE_NOTIFICAR = ("comando", "os")


def _codigo() -> str:
    """O código do formulário desta sessão (outro site não o conhece; o login troca a sessão e o código)."""
    if not session.get(_CODIGO):
        session[_CODIGO] = secrets.token_urlsafe(24)
    return session[_CODIGO]


def _meu_hmac() -> str:
    u = session.get("usuario")
    email = str(u.get("email") or "").strip().lower() if isinstance(u, dict) else ""
    if not email:
        return ""
    from ...campo.ligacao_cadastro import codigo_da_pessoa
    return (codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), email) or "").lower()


def _nomes_das_torres() -> dict:
    return {t.id: t.nome for t in current_app.extensions["nexus_torres"]}


def _areas() -> list[tuple[str, str]]:
    return [(t.id, t.nome) for t in sorted(current_app.extensions["nexus_torres"], key=lambda t: t.ordem)
            if t.id not in FORA_DE_NOTIFICAR]


def _com_estado(insights: list[dict], est: dict, meu: str, minhas: set | None) -> list[dict]:
    """Cada insight com o dono (novo, assumido por quem, concluído), se é meu, as áreas notificadas com o retorno de
    cada uma e os pedidos para as minhas áreas que esperam a minha resposta."""
    nomes, out = _nomes_das_torres(), []
    for i in insights:
        e = est.get(i["id"]) or {}
        ev = e.get("evento") if e.get("evento") != "reabriu" else ""
        pedidos = []
        for t, p in (e.get("pedidos") or {}).items():
            rot, tom = ES.RETORNOS[p["status"]]
            pedidos.append(dict(p, torre=t, nome=nomes.get(t, t), rotulo=rot, tom=tom,
                                minha=minhas is None or t in minhas))
        out.append(dict(i, estado=ev or "novo", por=e.get("por", ""), quando_txt=e.get("quando_txt", ""),
                        meu=bool(meu) and e.get("pessoa_hmac") == meu and ev == "assumiu",
                        sev_rot=RG.SEVERIDADES[i["sev"]][0], sev_tom=RG.SEVERIDADES[i["sev"]][1],
                        regra_nome=RG.REGRAS[i["regra"]]["nome"], avisar=RG.REGRAS[i["regra"]].get("avisar") or [],
                        pedidos=pedidos, resolvidos=sum(1 for p in pedidos if p["status"] == "resolvido"),
                        para_mim=[p for p in pedidos if p["minha"] and p["status"] != "resolvido"]))
    return out


def _leitura():
    lei = MO.ler()
    d = lei.dados or {}
    return lei, d.get("insights") or [], d.get("regras") or {}, d.get("gerado_em")


def _contexto(**kw) -> dict:
    return dict(kw, nomes_torres=_nomes_das_torres(), areas=_areas(), codigo=_codigo(), aviso=session.pop(_AVISO, None),
                tem_login=bool(_meu_hmac()), voltar=request.full_path.rstrip("?"), retornos=ES.RETORNOS)


@bp.route("/insights")
def insights():
    """Nexus Insights: tudo o que as regras apontaram agora, com a evidência, a ação, a torre dona, as áreas notificadas
    e os retornos; e o catálogo das regras com quantas vezes cada uma disparou e a fonte que não leu."""
    lei, todos, status, gerado = _leitura()
    lista = _com_estado(todos, ES.atual(), _meu_hmac(), MO.torres_da_pessoa())
    a = request.args
    sev = a.get("sev", "") if a.get("sev") in RG.SEVERIDADES else ""
    regra = a.get("regra", "") if a.get("regra") in RG.REGRAS else ""
    torre = a.get("torre", "")
    ver_concluidos = a.get("concluidos") == "1"
    filtrada = [i for i in lista if (not sev or i["sev"] == sev) and (not regra or i["regra"] == regra)
                and (not torre or i["torre"] == torre) and (ver_concluidos or i["estado"] != "concluiu")]
    vivos = [i for i in lista if i["estado"] != "concluiu"]
    contas = {k: sum(1 for i in vivos if i["sev"] == k) for k in RG.SEVERIDADES}
    contas["notificados"] = sum(1 for i in vivos if i["pedidos"])
    contas["aguardando"] = sum(1 for i in vivos for p in i["pedidos"] if p["status"] == "pendente")
    catalogo = [dict(RG.REGRAS[r], id=r, **(status.get(r) or {"n": 0, "erro": ""})) for r in RG.REGRAS]
    return render_template("comando/insights.html", **_contexto(
        torre=TORRE, tela=TORRE.tela("insights"), lei=lei, itens=filtrada, contas=contas, catalogo=catalogo,
        gerado=gerado, sev=sev, regra=regra, torre_f=torre, ver_concluidos=ver_concluidos, severidades=RG.SEVERIDADES,
        regras=RG.REGRAS, erro_estado=ES.ler()["erro"]))


@bp.route("/caixa-de-entrada")
def caixa_de_entrada():
    """Caixa de entrada: os pedidos que outras áreas mandaram para o setor da pessoa (esperando o retorno dele); o que
    ela assumiu; e os insights das torres do setor sem dono e com outra pessoa. Sem os concluídos."""
    lei, todos, status, gerado = _leitura()
    torres = MO.torres_da_pessoa()
    lista = [i for i in _com_estado(todos, ES.atual(), _meu_hmac(), torres) if i["estado"] != "concluiu"]
    pedidos = [i for i in lista if i["para_mim"]]
    das_minhas = MO.das_torres(lista, torres)
    meus = [i for i in das_minhas if i["meu"]]
    sem_dono = [i for i in das_minhas if not i["meu"] and i["estado"] == "novo"]
    com_dono = [i for i in das_minhas if not i["meu"] and i["estado"] == "assumiu"]
    nomes = _nomes_das_torres()
    return render_template("comando/caixa.html", **_contexto(
        torre=TORRE, tela=TORRE.tela("caixa-de-entrada"), lei=lei, pedidos=pedidos, meus=meus, sem_dono=sem_dono,
        com_dono=com_dono, gerado=gerado,
        minhas_torres=sorted(nomes.get(t, t) for t in torres) if torres is not None else None,
        falhas=[r for r, x in status.items() if x.get("erro")]))


@bp.route("/insights/acao", methods=["POST"])
def insights_acao():
    """Assumir, Concluir, Reabrir, Notificar áreas ou Responder (pela área notificada) um insight que o motor aponta
    agora. Volta à tela de onde veio."""
    voltar = request.form.get("voltar") or ""
    destino = na_raiz(voltar) if voltar.startswith("/t/comando/") else na_raiz("/t/comando/caixa-de-entrada")
    certo = session.get(_CODIGO) or ""
    enviado = request.form.get("codigo") or ""
    if _de_outro_site() or not certo or not hmac.compare_digest(enviado.encode(), certo.encode()):
        session[_AVISO] = ("erro", "O formulário venceu (a sessão mudou desde que a tela abriu): abra a tela de novo. "
                                   "Nada foi gravado.")
        return redirect(destino, code=303)
    acao = request.form.get("acao") or ""
    evento = {"assumir": "assumiu", "concluir": "concluiu", "reabrir": "reabriu", "notificar": "notificou",
              "responder": "respondeu"}.get(acao)
    iid = request.form.get("insight") or ""
    _lei, todos, _st, _g = _leitura()
    alvo = next((i for i in todos if i["id"] == iid), None)
    nomes = _nomes_das_torres()
    try:
        if not evento:
            raise ES.Recusada("Ação desconhecida")
        if alvo is None:
            raise ES.Recusada("Este insight não está mais na lista (a regra parou de apontar): recarregue a página")
        para, status = [], ""
        if evento == "notificou":
            para = [t for t in request.form.getlist("para") if t in nomes and t not in FORA_DE_NOTIFICAR]
        if evento == "respondeu":
            para, status = [request.form.get("area") or ""], request.form.get("status") or ""
            minhas = MO.torres_da_pessoa()
            if minhas is not None and para[0] not in minhas:
                raise ES.Recusada("Só quem é da área notificada responde por ela")
        feito = ES.registrar(alvo, evento, session.get("usuario"), request.form.get("nota") or "", para, status)
        if evento == "notificou":
            msg = (f"Notificado: {', '.join(nomes.get(t, t) for t in (feito.get('para') or '').split(',') if t)}. "
                   "O retorno de cada área aparece no insight.") if feito else "Essas áreas já estavam notificadas."
        else:
            msg = {"assumiu": "Assumido: agora é seu.", "concluiu": "Concluído: saiu da Caixa de entrada.",
                   "reabriu": "Reaberto.", "respondeu": "Retorno enviado: quem notificou já vê."}[evento]
        session[_AVISO] = ("ok", msg)
    except ES.Recusada as ex:
        session[_AVISO] = ("erro", f"{ex}. Nada foi gravado.")
    except Exception as ex:      # noqa: BLE001 — banco fora: a pessoa sabe que não foi
        current_app.logger.exception("insight: o evento não gravou")
        session[_AVISO] = ("erro", f"Não consegui gravar agora ({type(ex).__name__}). Nada foi gravado.")
    return redirect(destino + f"#ins-{iid.replace(':', '-')}", code=303)
