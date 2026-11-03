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
             "Itens de trabalho do Nexus (insights, OS, chamados, solicitações)", de_todos=True),
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


def _com_estado(insights: list[dict], est: dict, meu: str, minhas: set | None, convs: dict | None = None) -> list[dict]:
    """Cada insight com o dono (novo, assumido por quem, concluído), se é meu, as áreas notificadas com o retorno de
    cada uma, os pedidos para as minhas áreas que esperam a minha resposta e a conversa dele (Fase 2)."""
    nomes, out, convs = _nomes_das_torres(), [], convs or {}
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
                        para_mim=[p for p in pedidos if p["minha"] and p["status"] != "resolvido"],
                        ob="insight:" + i["id"], conv=_com_conversa(convs.get("insight:" + i["id"]), meu)))
    return out


def _leitura():
    """(leitura, insights, regras, gerado_em). Sem a cópia do motor, a leitura é None e a lista vem vazia: a conta corre
    por trás (`MO.sem_esperar`) e a tela avisa, em vez de segurar o pedido."""
    lei = MO.sem_esperar()
    if lei is None:
        return None, [], {}, None
    d = lei.dados or {}
    return lei, d.get("insights") or [], d.get("regras") or {}, d.get("gerado_em")


def _contexto(**kw) -> dict:
    return dict(kw, nomes_torres=_nomes_das_torres(), areas=_areas(), codigo=_codigo(), aviso=session.pop(_AVISO, None),
                abrir=request.args.get("abrir") or "",
                tem_login=bool(_meu_hmac()), voltar=request.full_path.rstrip("?"), retornos=ES.RETORNOS)


@bp.route("/insights")
def insights():
    """Nexus Insights: tudo o que as regras apontaram agora, com a evidência, a ação, a torre dona, as áreas notificadas
    e os retornos; e o catálogo das regras com quantas vezes cada uma disparou e a fonte que não leu."""
    lei, todos, status, gerado = _leitura()
    from ...comando import conversa as CV
    lista = _com_estado(todos, ES.atual(), _meu_hmac(), MO.torres_da_pessoa(), CV.atual())
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
        calculando=lei is None,
        regras=RG.REGRAS, erro_estado=ES.ler()["erro"]))


@bp.route("/caixa-de-entrada")
def caixa_de_entrada():
    """Caixa de entrada: os pedidos que outras áreas mandaram para o setor da pessoa (esperando o retorno dele); o que
    ela assumiu; e os insights das torres do setor sem dono e com outra pessoa. Sem os concluídos."""
    from ...comando import conversa as CV
    lei, todos, status, gerado = _leitura()
    torres, meu, convs = MO.torres_da_pessoa(), _meu_hmac(), CV.atual()
    lista = [i for i in _com_estado(todos, ES.atual(), meu, torres, convs) if i["estado"] != "concluiu"]
    # as menções que ainda não li (Fase 2): a pessoa pelo código do e-mail, ou uma área que o setor dela vê
    usinas, mencoes = _usinas(), []
    for x in CV.para_mim(convs, meu, torres):
        titulo, link = _titulo(x["objeto"], todos, usinas)
        mencoes.append(dict(x, titulo=titulo, link=link, conversa=na_raiz(
            "/t/comando/conversa/" + x["objeto"].replace(":", "/", 1)),
            por_area_nomes=[_nomes_das_torres().get(a, a) for a in x["por_area"]]))
    pedidos = [i for i in lista if i["para_mim"]]
    das_minhas = MO.das_torres(lista, torres)
    meus = [i for i in das_minhas if i["meu"]]
    sem_dono = [i for i in das_minhas if not i["meu"] and i["estado"] == "novo"]
    com_dono = [i for i in das_minhas if not i["meu"] and i["estado"] == "assumiu"]
    nomes = _nomes_das_torres()
    return render_template("comando/caixa.html", **_contexto(
        torre=TORRE, tela=TORRE.tela("caixa-de-entrada"), lei=lei, pedidos=pedidos, meus=meus, sem_dono=sem_dono,
        com_dono=com_dono, gerado=gerado, mencoes=mencoes, usinas_lista=sorted(usinas.items(), key=lambda u: u[1]),
        erro_conversa=CV.ler()["erro"], calculando=lei is None,
        minhas_torres=sorted(nomes.get(t, t) for t in torres if t not in FORA_DE_NOTIFICAR) if torres is not None else None,
        falhas=[r for r, x in status.items() if x.get("erro")]))


# o miolo e as ações de um insight em /insight/ (no singular): /insights/... casa com a tela Insights no portão por setor,
# e quem só tem a Caixa de entrada (todo setor, 03/11/2026) não abriria o insight nem gravaria o Assumir; o endereço antigo
# segue valendo para quem tem a tela
@bp.route("/insight/corpo")
@bp.route("/insights/corpo")
def insights_corpo():
    """O miolo de um insight (provas, áreas, retornos, conversa), pedido quando a pessoa abre a linha: a lista vem só
    com as linhas (ver `_insight.html`). O `voltar` é o da página que pediu, para os formulários voltarem a ela."""
    from ...comando import conversa as CV
    _lei, todos, _st, _g = _leitura()
    alvo = next((i for i in todos if i["id"] == (request.args.get("id") or "")), None)
    if alvo is not None and not _ve_o_insight(alvo):
        alvo = None
    if alvo is None:
        return ('<p class="mudo ins-nota">Este insight não está mais na lista (a regra parou de apontar, ou a conta está '
                'sendo refeita): recarregue a página.</p>'), 404
    voltar = request.args.get("voltar") or ""
    i = _com_estado([alvo], ES.atual(), _meu_hmac(), MO.torres_da_pessoa(), CV.atual())[0]
    # sem o `_contexto`: ele tira o aviso da sessão, que é da página
    return render_template("comando/_corpo.html", i=i, nomes_torres=_nomes_das_torres(), areas=_areas(),
                           codigo=_codigo(), tem_login=bool(_meu_hmac()), retornos=ES.RETORNOS,
                           voltar=voltar if voltar.startswith("/t/comando/") else "/t/comando/insights")


def _ve_o_insight(i: dict) -> bool:
    """Quem tem a tela Insights vê todos; quem só tem a Caixa, os das torres do setor e os que pedem retorno a ele."""
    from ...auth import setor_telas
    a = setor_telas.acesso()
    if a["tudo"] or setor_telas.chave("comando", "insights") in a["telas"]:
        return True
    torres = MO.torres_da_pessoa() or set()
    return i["torre"] in torres or any(t in torres for t in ((ES.atual().get(i["id"]) or {}).get("pedidos") or {}))


@bp.route("/insight/acao", methods=["POST"])
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
        if _lei is None:
            raise ES.Recusada("A conta dos insights está sendo feita agora (o Nexus acabou de subir): tente de novo em "
                              "meio minuto")
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


# ── a conversa com @menção (Fase 2, 03/11/2026) ──────────────────────────────────────────────────────────────────────
def _usinas() -> dict:
    """usina_id -> nome, do cadastro do Nexus (o mesmo das regras). Sem o cadastro, vazio: a conversa da usina mostra o
    código."""
    from ...campo import visao
    from ...dados import fatos as D
    try:
        return {D._id(k): str(v.get("nome") or "") for k, v in visao._Base().por_id.items() if v.get("nome")}
    except Exception:            # noqa: BLE001 — o cadastro fora: a conversa segue com o código
        return {}


def _titulo(ob: str, insights: list[dict], usinas: dict) -> tuple[str, str]:
    """(o título da conversa, o link para o objeto)."""
    tipo, _, oid = ob.partition(":")
    if tipo == "insight":
        i = next((x for x in insights if x["id"] == oid), None)
        return ((i["titulo"] if i else f"Insight {oid} (a regra não aponta mais)"),
                na_raiz("/t/comando/insights") + f"#ins-{oid.replace(':', '-')}")
    if tipo == "os":
        return f"OS {oid}", ""
    return f"Usina {usinas.get(int(oid)) or oid}", ""


def _com_conversa(c: dict | None, meu: str) -> dict:
    """A conversa para a tela: as mensagens com os nomes das áreas e das pessoas mencionadas (o nome sai de quem já
    escreveu na conversa; a pessoa nunca vista fica "uma pessoa")."""
    c = c or {"mensagens": [], "leu": {}}
    nomes, por_hmac = _nomes_das_torres(), {m["pessoa_hmac"]: m["por"] for m in c["mensagens"] if m["por"]}
    msgs = [dict(m, minha=bool(meu) and m["pessoa_hmac"] == meu,
                 areas_nomes=[nomes.get(a, a) for a in m["areas"]],
                 pessoas_nomes=["você" if p == meu else por_hmac.get(p, "uma pessoa") for p in m["pessoas"]])
            for m in c["mensagens"]]
    return {"mensagens": msgs, "n": len(msgs)}


@bp.route("/conversa/<tipo>/<path:oid>")
def conversa(tipo, oid):
    """A conversa de um objeto (insight, OS ou usina), com o formulário e as menções."""
    from ...comando import conversa as CV
    ob = CV.objeto(tipo, oid)
    if not ob:
        abort(404)
    _lei, todos, _st, _g = _leitura()
    titulo, link = _titulo(ob, todos, _usinas())
    meu = _meu_hmac()
    lido = CV.ler()
    return render_template("comando/conversa.html", **_contexto(
        torre=TORRE, tela=TORRE.tela("caixa-de-entrada"), ob=ob, tipo_nome=CV.TIPOS[tipo], titulo=titulo, link=link,
        conv=_com_conversa(CV.atual().get(ob), meu), erro_conversa=lido["erro"]))


@bp.route("/conversa/pessoas")
def conversa_pessoas():
    """Quem pode ser mencionado (as pessoas com setor e as áreas): a tela pede só quando alguém digita @."""
    from ...comando import conversa as CV
    try:
        pessoas, erro = CV.pessoas_mencionaveis(), ""
    except Exception as ex:      # noqa: BLE001 — o Fracttal ou o banco fora: as áreas seguem
        current_app.logger.warning("conversa: a lista de pessoas não leu (%s)", ex)
        pessoas, erro = [], "Não consegui ler as pessoas agora: as áreas seguem."
    return {"pessoas": pessoas, "areas": [{"id": t, "nome": n} for t, n in _areas()], "erro": erro}


@bp.route("/conversa/acao", methods=["POST"])
def conversa_acao():
    """Escrever na conversa de um objeto (com as menções) ou marcar as menções dele como lidas. Volta à tela de onde
    veio, na conversa."""
    from ...comando import conversa as CV
    voltar = request.form.get("voltar") or ""
    destino = na_raiz(voltar) if voltar.startswith("/t/comando/") else na_raiz("/t/comando/caixa-de-entrada")
    certo = session.get(_CODIGO) or ""
    enviado = request.form.get("codigo") or ""
    if _de_outro_site() or not certo or not hmac.compare_digest(enviado.encode(), certo.encode()):
        session[_AVISO] = ("erro", "O formulário venceu (a sessão mudou desde que a tela abriu): abra a tela de novo. "
                                   "Nada foi gravado.")
        return redirect(destino, code=303)
    acao = request.form.get("acao") or ""
    ob = CV.objeto(*(request.form.get("objeto") or "").partition(":")[::2])
    if acao == "nova":           # a conversa nova da Caixa: a OS pelo número, a usina pela lista
        tipo = request.form.get("tipo") or ""
        ob = CV.objeto(tipo, request.form.get("os" if tipo == "os" else "usina") or "")
        destino = na_raiz(f"/t/comando/conversa/{ob.replace(':', '/', 1)}") if ob else destino
    nomes = _nomes_das_torres()
    try:
        if not ob:
            raise CV.Recusada("Diga sobre o quê: o número da OS ou a usina")
        if acao in ("mensagem", "nova"):
            areas = [t for t in request.form.getlist("area") if t in nomes and t not in FORA_DE_NOTIFICAR]
            feito = CV.registrar(ob, "mensagem", session.get("usuario"), request.form.get("texto") or "",
                                 request.form.getlist("pessoa"), areas)
            n = sum(len(feito[k].split(",")) for k in ("mencoes_pessoas", "mencoes_areas") if feito.get(k))
            avisadas = "" if not n else (": 1 menção avisada." if n == 1 else f": {n} menções avisadas.")
            session[_AVISO] = ("ok", ("Mensagem enviada" + (avisadas or ".")) if feito
                               else "Esta mensagem já estava na conversa.")
        elif acao == "leu":
            CV.registrar(ob, "leu", session.get("usuario"))
            session[_AVISO] = ("ok", "Marcado como lido.")
        else:
            raise CV.Recusada("Ação desconhecida")
    except CV.Recusada as ex:
        session[_AVISO] = ("erro", f"{ex}. Nada foi gravado.")
    except Exception as ex:      # noqa: BLE001 — banco fora: a pessoa sabe que não foi
        current_app.logger.exception("conversa: a mensagem não gravou")
        session[_AVISO] = ("erro", f"Não consegui gravar agora ({type(ex).__name__}). Nada foi gravado.")
    ancora = f"#conv-{ob.replace(':', '-')}" if ob and "/conversa/" not in destino else ""
    return redirect(destino + ancora, code=303)
