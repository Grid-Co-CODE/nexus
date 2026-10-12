"""Tela Base > Integração Fracttal (12/10/2026): o pessoal do Fracttal ligado ao cadastro de pessoas do Nexus. As regras
estão em `fracttal_pessoal.py`. Só administrador: a tela tem o nome e o e-mail de todo o pessoal do Fracttal."""
from datetime import datetime, timedelta, timezone

from flask import current_app, render_template, request, session

from . import fracttal_pessoal as FP

_BRT = timezone(timedelta(hours=-3))
LIGACOES = (("", "Todas"), ("ligadas", "Com ficha no Nexus"), ("sem_ficha", "Sem ficha no Nexus"))


def _sem_permissao():
    u = session.get("usuario")
    email = str(u.get("email") or "") if isinstance(u, dict) else ""
    return render_template("cadastro/sem_permissao.html", titulo="Integração Fracttal", eyebrow="Base · Integração Fracttal",
                           area="A Integração Fracttal", email=email), 403


def contexto(cfg, args) -> dict:
    from ..campo import visao
    lido = FP.ler_pessoal(forcar=args.get("reler") == "1")
    erro_cadastro = ""
    try:
        pessoas_cad = visao._livro("cadastro_nexus", "pessoas")
        equipes = visao._livro("cadastro_nexus", "equipes")
    except Exception as ex:      # noqa: BLE001 — banco fora (ou teste sem banco): a tela diz e mostra só o Fracttal
        pessoas_cad, equipes, erro_cadastro = [], [], f"{type(ex).__name__}: {str(ex)[:160]}"
    from ..dados import fatos as D
    nome_equipe = {D._id(e.get("equipe_id")): str(e.get("nome") or "") for e in equipes}
    chave = cfg.get("NEXUS_CHAVE_CADASTRO")
    rel = FP.ligar(lido["pessoas"], FP.fichas(pessoas_cad, chave), nome_equipe)
    q = str(args.get("q") or "").strip()[:120]
    ligacao = args.get("ligacao") if args.get("ligacao") in dict(LIGACOES) else ""
    acessos = sorted({x["acesso"] for x in rel["linhas"]})
    acesso = args.get("acesso") if args.get("acesso") in acessos else ""
    origem = args.get("origem") if args.get("origem") in FP.ORIGENS else ""
    linhas = FP.filtrar(rel["linhas"], q, ligacao, acesso, origem)
    sem_ficha = [x for x in rel["linhas"] if not x["ficha"]]
    lido_em = datetime.fromtimestamp(lido["lido_em"], _BRT).strftime("%d/%m às %H:%M") if lido.get("lido_em") else ""
    so_ativas = args.get("todas_fichas") != "1"
    sem_conta = [f for f in rel["sem_conta"] if not so_ativas or f["status"].lower() == "ativo"]
    return {"rel": rel, "linhas": linhas, "total": len(lido["pessoas"]), "erro": lido.get("erro") or "",
            "erro_cadastro": erro_cadastro,
            "velha": lido.get("velha", False), "lido_em": lido_em, "sem_chave": not chave, "q": q, "ligacao": ligacao,
            "ligacoes": LIGACOES, "acesso": acesso, "acessos": acessos, "sem_conta": sem_conta,
            "origem": origem, "origens": FP.ORIGENS,
            "sem_ficha_grid": sum(1 for x in sem_ficha if x["origem"] == FP.ORIGENS[0]),
            "sem_ficha_ext": sum(1 for x in sem_ficha if x["origem"] != FP.ORIGENS[0]),
            "sem_conta_total": len(rel["sem_conta"]), "so_ativas": so_ativas,
            "admins": sum(1 for x in lido["pessoas"] if x["acesso"] == "Administrador"),
            "leitura": sum(1 for x in lido["pessoas"] if x["acesso"] == "Leitura"),
            "sem_acesso": sum(1 for x in lido["pessoas"] if not x["conta_ativa"])}


def registrar_fracttal(bp) -> None:
    """Pendura a tela na torre Base (`/t/base/fracttal`), vencendo o placeholder."""
    @bp.route("/fracttal")
    def fracttal():
        if not session.get("admin"):
            return _sem_permissao()
        return render_template("cadastro/fracttal.html", **contexto(current_app.config, request.args))
