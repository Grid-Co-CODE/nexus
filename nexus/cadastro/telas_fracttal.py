"""Tela Base > Integração Fracttal (12/10/2026): o pessoal do Fracttal ligado ao cadastro de pessoas do Nexus, e o setor
de cada pessoa. As regras estão em `fracttal_pessoal.py` (a ligação) e `setores.py` (o setor, no banco). Só
administrador: a tela tem o nome e o e-mail de todo o pessoal do Fracttal e grava no banco.

Gravar (o setor de uma pessoa, o das marcadas e a lista de setores) é POST da própria página (`_de_outro_site`, a mesma
régua da moldura e da tela Acessos; o cookie `Lax` já barra o POST de outro site). O setor de UMA pessoa vai por fetch e
não recarrega a página (Levi atribui setor numa lista de 150: recarregar perdia a rolagem); sem JavaScript, e nas
marcadas e na lista de setores, o formulário volta por 303 à mesma lista, com os filtros e o aviso.
"""
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode

from flask import current_app, jsonify, redirect, render_template, request, session, url_for

from . import fracttal_pessoal as FP
from . import setores as S

log = logging.getLogger(__name__)

_BRT = timezone(timedelta(hours=-3))
LIGACOES = (("", "Todas"), ("ligadas", "Com ficha no Nexus"), ("sem_ficha", "Sem ficha no Nexus"))
FILTROS = ("q", "ligacao", "acesso", "origem", "setor", "todas_fichas")     # o que a volta leva, e nada além
_CHAVE_AVISO = "fracttal_aviso"


def _meu_email() -> str:
    u = session.get("usuario")
    return str(u.get("email") or "").strip().lower() if isinstance(u, dict) else ""


def _sem_permissao():
    return render_template("cadastro/sem_permissao.html", titulo="Integração Fracttal", eyebrow="Base · Integração Fracttal",
                           area="A Integração Fracttal", email=_meu_email()), 403


def _de_outro_site() -> bool:
    from ..torres.moldura import _de_outro_site as regra
    return regra()


def _volta(qs: str = "", ancora: str = "") -> str:
    """A mesma lista, com os filtros de antes: só os conhecidos (nunca um endereço vindo do formulário)."""
    pares = [(k, v[:120]) for k, v in parse_qsl(qs or "") if k in FILTROS]
    return url_for("torre_base.fracttal") + ("?" + urlencode(pares) if pares else "") + (f"#{ancora}" if ancora else "")


def _relacao(cfg, lido: dict) -> tuple[dict, str]:
    """A ligação do pessoal do Fracttal com as fichas do cadastro (lido do banco) e o erro da leitura do cadastro."""
    from ..campo import visao
    from ..dados import fatos as D
    erro_cadastro = ""
    try:
        pessoas_cad = visao._livro("cadastro_nexus", "pessoas")
        equipes = visao._livro("cadastro_nexus", "equipes")
    except Exception as ex:      # noqa: BLE001 — banco fora (ou teste sem banco): a tela diz e mostra só o Fracttal
        pessoas_cad, equipes, erro_cadastro = [], [], f"{type(ex).__name__}: {str(ex)[:160]}"
    nome_equipe = {D._id(e.get("equipe_id")): str(e.get("nome") or "") for e in equipes}
    rel = FP.ligar(lido["pessoas"], FP.fichas(pessoas_cad, cfg.get("NEXUS_CHAVE_CADASTRO")), nome_equipe)
    return rel, erro_cadastro


def _ler_setores(forcar: bool = False) -> dict:
    from ..campo import visao
    try:
        return S.ler(visao._base(), visao._sessao(), forcar=forcar)
    except Exception as ex:      # noqa: BLE001 — sem banco (teste): a tela diz e não deixa gravar
        return {"setores": [], "decisoes": [], "lido_em": None, "erro": f"{type(ex).__name__}: {str(ex)[:160]}"}


def contexto(cfg, args) -> dict:
    reler = args.get("reler") == "1"
    lido = FP.ler_pessoal(forcar=reler)
    rel, erro_cadastro = _relacao(cfg, lido)
    st = _ler_setores(forcar=reler)
    vig = S.vigentes(st["decisoes"])
    nome_setor = {s["setor_id"]: s["nome"] for s in st["setores"]}
    n_setor: dict = {}
    for x in rel["linhas"]:
        sid = vig.get(x["id"])
        x["setor_id"], x["setor"] = sid, (nome_setor.get(sid) or f"setor {sid}") if sid else ""
        if sid:
            n_setor[sid] = n_setor.get(sid, 0) + 1
    setores = [dict(s, n=n_setor.get(s["setor_id"], 0)) for s in S.ativos(st["setores"])]
    q = str(args.get("q") or "").strip()[:120]
    ligacao = args.get("ligacao") if args.get("ligacao") in dict(LIGACOES) else ""
    acessos = sorted({x["acesso"] for x in rel["linhas"]})
    acesso = args.get("acesso") if args.get("acesso") in acessos else ""
    origem = args.get("origem") if args.get("origem") in FP.ORIGENS else ""
    setor = args.get("setor") if args.get("setor") in ({"sem"} | {str(s["setor_id"]) for s in setores}) else ""
    linhas = FP.filtrar(rel["linhas"], q, ligacao, acesso, origem, setor)
    sem_ficha = [x for x in rel["linhas"] if not x["ficha"]]
    lido_em = datetime.fromtimestamp(lido["lido_em"], _BRT).strftime("%d/%m às %H:%M") if lido.get("lido_em") else ""
    so_ativas = args.get("todas_fichas") != "1"
    sem_conta = [f for f in rel["sem_conta"] if not so_ativas or f["status"].lower() == "ativo"]
    filtros = {"q": q, "ligacao": ligacao, "acesso": acesso, "origem": origem, "setor": setor,
               "todas_fichas": "" if so_ativas else "1"}
    aviso = session.pop(_CHAVE_AVISO, None)
    return {"rel": rel, "linhas": linhas, "total": len(lido["pessoas"]), "erro": lido.get("erro") or "",
            "erro_cadastro": erro_cadastro,
            "velha": lido.get("velha", False), "lido_em": lido_em, "sem_chave": not cfg.get("NEXUS_CHAVE_CADASTRO"),
            "q": q, "ligacao": ligacao, "ligacoes": LIGACOES, "acesso": acesso, "acessos": acessos,
            "sem_conta": sem_conta, "origem": origem, "origens": FP.ORIGENS,
            "sem_ficha_grid": sum(1 for x in sem_ficha if x["origem"] == FP.ORIGENS[0]),
            "sem_ficha_ext": sum(1 for x in sem_ficha if x["origem"] != FP.ORIGENS[0]),
            "sem_conta_total": len(rel["sem_conta"]), "so_ativas": so_ativas,
            "admins": sum(1 for x in lido["pessoas"] if x["acesso"] == "Administrador"),
            "leitura": sum(1 for x in lido["pessoas"] if x["acesso"] == "Leitura"),
            "sem_acesso": sum(1 for x in lido["pessoas"] if not x["conta_ativa"]),
            # o setor
            "setores": setores, "ids_setores": {s["setor_id"] for s in setores}, "setor": setor,
            "sem_setor": sum(1 for x in rel["linhas"] if not x["setor_id"]),
            "erro_setores": st.get("erro") or "", "setores_velha": st.get("velha", False),
            "sem_token": not cfg.get("GRIDCO_SQL_TOKEN"),
            "pode_gravar_setor": not st.get("erro") and bool(cfg.get("GRIDCO_SQL_TOKEN")),
            "volta": urlencode([(k, v) for k, v in filtros.items() if v]),
            "aviso": aviso, "abrir_setores": bool(aviso and aviso.get("painel"))}


def _responder(ok: bool, texto: str, status: int = 200, ancora: str = "", painel: bool = False, **extra):
    """JSON para o fetch da página; sem ele (formulário), 303 de volta à lista com o aviso guardado na sessão."""
    if "application/json" in (request.headers.get("Accept") or ""):
        r = jsonify(dict(ok=ok, aviso=texto if ok else "", erro="" if ok else texto, **extra))
        r.status_code = status
        return r
    session[_CHAVE_AVISO] = {"tom": "ok" if ok else "critico", "texto": texto, "painel": painel}
    return redirect(_volta(request.form.get("volta") or "", ancora), code=303)


def _gravar_setor():
    """POST de pessoa(s) + setor_id ("" = tira do setor). As pessoas são as da leitura do Fracttal de agora, ligadas às
    fichas como a tela as mostra: id que não está nela recusa (a página estava velha)."""
    from ..campo import visao
    from ..dados import fatos as D
    cfg = current_app.config
    if _de_outro_site():
        return _responder(False, "Pedido de outro site: nada foi gravado.", 403)
    ids = list(dict.fromkeys(i for i in (D._id(v) for v in request.form.getlist("pessoa")[:S.LOTE_MAX + 1]) if i))
    bruto = (request.form.get("setor_id") or "").strip()
    setor_id = D._id(bruto) if bruto else None
    if bruto and not setor_id:
        return _responder(False, "Setor inválido: nada foi gravado.", 400)
    lido = FP.ler_pessoal()
    if not lido["pessoas"]:
        return _responder(False, f"Não consegui ler o Fracttal ({lido.get('erro') or 'vazio'}): nada foi gravado.", 503)
    rel, erro_cadastro = _relacao(cfg, lido)
    if erro_cadastro:
        return _responder(False, "Não consegui ler o cadastro de pessoas do banco: nada foi gravado (a decisão leva a "
                                 "ficha da pessoa).", 503)
    por_id = {x["id"]: x for x in rel["linhas"]}
    pessoas = [por_id[i] for i in ids if i in por_id]
    if len(pessoas) != len(ids):
        return _responder(False, "Há pessoa fora da lista do Fracttal de agora: atualize a página. Nada foi gravado.", 400)
    try:
        r = S.definir(pessoas, setor_id, cfg, visao._base(), visao._sessao(), quem_email=_meu_email())
    except S.Recusada as ex:
        return _responder(False, str(ex), 409)
    except Exception as ex:      # noqa: BLE001 — a gravação ou a conferência falhou: a tela diz, nada some calado
        log.error("Setores: a gravação falhou (%s: %s).", type(ex).__name__, ex)
        return _responder(False, f"A gravação no banco falhou ({type(ex).__name__}). Releia a página: se o setor não "
                                 "mudou, tente de novo.", 500)
    destino = f"no setor {r['setor']}" if setor_id else "sem setor"
    if len(pessoas) == 1:
        texto = f"{pessoas[0]['nome']}: {'já estava ' if not r['gravadas'] else ''}{destino}."
    else:
        texto = (f"{r['gravadas']} {'pessoa' if r['gravadas'] == 1 else 'pessoas'} {destino}"
                 + (f"; {r['iguais']} já estavam." if r["iguais"] else "."))
    return _responder(True, texto, ancora=f"p-{pessoas[0]['id']}" if len(pessoas) == 1 else "",
                      gravadas=r["gravadas"], setor=r["setor"], setor_id=setor_id)


def _gravar_lista():
    """POST da lista de setores: acao = criar (nome), renomear (setor_id, nome) ou excluir (setor_id)."""
    from ..campo import visao
    from ..dados import fatos as D
    cfg = current_app.config
    if _de_outro_site():
        return _responder(False, "Pedido de outro site: nada foi gravado.", 403, painel=True)
    acao, quem = request.form.get("acao"), _meu_email() or "senha de administrador"
    nome, sid = (request.form.get("nome") or "")[:200], D._id(request.form.get("setor_id"))
    try:
        base, sessao = visao._base(), visao._sessao()
        if acao == "criar":
            texto = f"Setor {S.criar(nome, cfg, base, sessao, quem)['nome']} criado."
        elif acao == "renomear" and sid:
            texto = f"O setor agora se chama {S.renomear(sid, nome, cfg, base, sessao, quem)['nome']}."
        elif acao == "excluir" and sid:
            texto = f"Setor {S.excluir(sid, cfg, base, sessao, quem)['nome']} excluído."
        else:
            return _responder(False, "Ação desconhecida: nada foi gravado.", 400, painel=True)
    except S.Recusada as ex:
        return _responder(False, str(ex), 409, painel=True)
    except Exception as ex:      # noqa: BLE001
        log.error("Setores: a lista não foi gravada (%s: %s).", type(ex).__name__, ex)
        return _responder(False, f"A gravação no banco falhou ({type(ex).__name__}). Releia a página e tente de novo.",
                          500, painel=True)
    return _responder(True, texto, painel=True)


def registrar_fracttal(bp) -> None:
    """Pendura a tela na torre Base (`/t/base/fracttal`), vencendo o placeholder, e os dois POST do setor."""
    @bp.route("/fracttal")
    def fracttal():
        if not session.get("admin"):
            return _sem_permissao()
        return render_template("cadastro/fracttal.html", **contexto(current_app.config, request.args))

    @bp.route("/fracttal/setor", methods=["POST"])
    def fracttal_setor():
        if not session.get("admin"):
            return _sem_permissao()
        return _gravar_setor()

    @bp.route("/fracttal/setores", methods=["POST"])
    def fracttal_setores():
        if not session.get("admin"):
            return _sem_permissao()
        return _gravar_lista()
