"""Tela Base → Acessos (11/10/2026): quem é administrador do Nexus, dar e tirar pela tela, e quem entrou em 30 dias.

Só administrador vê e grava (quem não é recebe a página "só para administradores" do Cadastro, com o porquê). O dado e
as regras moram em `acessos.py`; aqui ficam a página e o portão do POST:
- só da própria página: o `Sec-Fetch-Site`/`Origin` com a mesma régua da moldura da Performance (`_de_outro_site`) e um
  código do formulário guardado na sessão (o cookie `Lax` já barra o POST de outro site; dar administrador é a ação
  mais sensível do Nexus, então confere duas vezes);
- POST que grava volta por 303 à tela (F5 não repete), com o aviso guardado na sessão.

Telas por setor (12/10/2026, Levi: "uma seção no BASE > ACESSOS onde eu possa controlar o que cada pessoa de setor pode
ver ao logar no Nexus"): um setor por vez, com a árvore do menu em caixas de marcar; o Salvar grava só o que mudou no
livro `nexus_setor_telas` (regras e portão em `setor_telas.py`). O setor de cada pessoa é o da tela Integração Fracttal;
aqui aparece também na lista de quem entrou, pelo código do e-mail (sem o e-mail ir ao banco).
"""
import hmac
import logging
import secrets
from collections import Counter

from flask import current_app, redirect, render_template, request, session, url_for

from ..cadastro import setores as S
from . import acessos as A
from . import admins_do_servidor
from . import setor_telas as ST

log = logging.getLogger(__name__)

_CHAVE_CODIGO = "acessos_codigo"
_CHAVE_AVISO = "acessos_aviso"


def _meu_email() -> str:
    u = session.get("usuario")
    return str(u.get("email") or "").strip().lower() if isinstance(u, dict) else ""


def _quem() -> str:
    """Quem fez a mudança, para a lista e a auditoria: o e-mail do Fracttal, ou "senha de administrador"."""
    return _meu_email() or A.SENHA_DE_ADMIN


def _codigo() -> str:
    """O código do formulário desta sessão (nasce na 1ª visita; o login limpa a sessão e troca o código)."""
    if not session.get(_CHAVE_CODIGO):
        session[_CHAVE_CODIGO] = secrets.token_urlsafe(24)
    return session[_CHAVE_CODIGO]


def _de_outro_site() -> bool:
    from ..torres.moldura import _de_outro_site as regra
    return regra()


def _linhas_de_admins(servidor: set[str], est: dict, ultimo: dict) -> list[dict]:
    eu = _meu_email()
    linhas = [{"email": e, "origem": "servidor", "por": "", "quando": "", "ultimo": ultimo.get(e, ""),
               "eu": e == eu} for e in sorted(servidor)]
    for a in sorted(est["admins"], key=lambda x: x["email"]):
        linhas.append({"email": a["email"], "origem": "tela", "por": a["por"], "quando": A.hora_br(a["quando"]),
                       "ultimo": ultimo.get(a["email"], ""), "eu": a["email"] == eu,
                       "tambem_servidor": a["email"] in servidor})
    return linhas


def _torres():
    """As torres do menu, na ordem dele: a árvore que a matriz de cada setor marca."""
    return sorted(current_app.extensions["nexus_torres"], key=lambda t: t.ordem)


def _todas_as_telas() -> set[str]:
    return {ST.chave(t.id, s.id) for t in _torres() for s in t.telas}


def _ler_setores():
    """(setores, telas) do banco, cada um {"...", "erro", "lido_em"}; o banco fora vira erro na tela, nunca exceção."""
    try:
        base, sessao = ST._banco()
        return S.ler(base, sessao), ST.ler(base, sessao)
    except Exception as ex:      # noqa: BLE001 — sem o endereço do banco, por exemplo
        erro = type(ex).__name__
        return ({"setores": [], "decisoes": [], "erro": erro, "lido_em": None},
                {"decisoes": [], "erro": erro, "lido_em": None})


def _secao_setores(escolhido: int | None, logins: list[dict]) -> dict:
    """A seção Telas por setor: os setores (com quantas pessoas e telas), a árvore do menu marcada para o setor escolhido
    e o que cada setor vê (para o "Copiar de"). Põe também o setor em cada login de 30 dias."""
    from ..campo.ligacao_cadastro import codigo_da_pessoa
    from ..casca import _telas_prontas
    app = current_app._get_current_object()
    cfg = current_app.config
    st, tl = _ler_setores()
    torres = _torres()
    todas = {ST.chave(t.id, s.id) for t in torres for s in t.telas}
    prontas = _telas_prontas(app)
    matriz = ST.vigentes(tl["decisoes"])
    pessoas = Counter(v for v in S.vigentes(st["decisoes"]).values() if v)
    setores = [{"id": s["setor_id"], "nome": s["nome"], "admin": ST.eh_administrador(s["nome"]),
                "pessoas": pessoas.get(s["setor_id"], 0), "telas": len(matriz.get(s["setor_id"], set()) & todas)}
               for s in S.ativos(st["setores"])]
    comuns = [s for s in setores if not s["admin"]]
    sel = (next((s for s in setores if s["id"] == escolhido), None)
           or (comuns[0] if comuns else setores[0] if setores else None))
    marcadas = matriz.get(sel["id"], set()) if sel else set()
    arvore = []
    for t in torres:
        telas = [{"chave": ST.chave(t.id, s.id), "nome": s.nome, "pronta": f"/t/{t.id}/{s.id}" in prontas,
                  "marcada": ST.chave(t.id, s.id) in marcadas} for s in t.telas]
        arvore.append({"id": t.id, "nome": t.nome, "icone": t.icone, "telas": telas,
                       "marcadas": sum(x["marcada"] for x in telas)})
    # o setor de quem entrou: pelo código do e-mail, o mesmo que a decisão de setor grava (o e-mail não vai ao banco)
    por_codigo = ST.setor_de_cada_codigo(st["decisoes"])
    nome_do = {s["id"]: s["nome"] for s in setores}
    chave_hmac = cfg.get("NEXUS_PESSOA_HMAC")
    for x in logins:
        cod = None if x["senha"] else codigo_da_pessoa(chave_hmac, x["email"])
        x["setor"] = nome_do.get(por_codigo.get(cod)) if cod else None
        if x["setor"] and ST.eh_administrador(x["setor"]) and not x["admin"]:
            x["admin"] = "pelo setor"
    ilegivel = not st.get("lido_em") or not tl.get("lido_em")
    return {
        "portao": ST.estado(cfg), "setores": setores, "setor_sel": sel, "arvore": arvore,
        "total_telas_menu": len(todas), "marcadas_sel": len(marcadas & todas),
        "matriz_setores": {str(s["id"]): sorted(matriz.get(s["id"], set()) & todas) for s in comuns},
        "n_comuns": len(comuns),
        "pessoas_com_setor": sum(pessoas.get(s["id"], 0) for s in setores),
        "setores_erro": " · ".join(e for e in (st.get("erro"), tl.get("erro")) if e),
        "pode_gravar_setores": bool(cfg.get("GRIDCO_SQL_TOKEN")) and not ilegivel,
        "sem_token": not cfg.get("GRIDCO_SQL_TOKEN"), "tem_hmac": bool(chave_hmac),
        "sem_setor_30d": sum(1 for x in logins if not x["senha"] and not x["setor"] and not x["admin"]),
    }


def _pagina(erro: str | None = None, status: int = 200, email_digitado: str = "", setor_escolhido: int | None = None):
    cfg = current_app.config
    servidor = admins_do_servidor()
    est = A.estado(cfg)
    da_tela = {a["email"] for a in est["admins"]}
    logins = [dict(x, quando_br=A.hora_br(x["quando"])) for x in A.logins_recentes(cfg)]
    ultimo = {x["email"]: x["quando_br"] for x in logins}
    for x in logins:
        x["senha"] = x["email"] == A.SENHA_DE_ADMIN
        x["admin"] = ("sempre" if x["senha"] else "do servidor" if x["email"] in servidor
                      else "pela tela" if x["email"] in da_tela else "")
    if setor_escolhido is None:
        setor_escolhido = request.args.get("setor", type=int)
    secao = _secao_setores(setor_escolhido, logins)
    admins = _linhas_de_admins(servidor, est, ultimo)
    contexto = {
        "admins": admins, "auditoria": [dict(x, quando_br=A.hora_br(x.get("quando"))) for x in est["auditoria"]],
        "logins": logins, "sem_pasta": est["sem_pasta"], "arquivo_erro": est["erro"],
        "total_servidor": len(servidor), "total_tela": len(da_tela - servidor), "n_tela": len(da_tela),
        "pessoas_30d": sum(1 for x in logins if not x["senha"]),
        "admins_30d": sum(1 for x in logins if x["admin"] in ("do servidor", "pela tela", "pelo setor")),
        "codigo": _codigo(), "erro": erro, "aviso": session.pop(_CHAVE_AVISO, None),
        "email_digitado": email_digitado, "eu": _meu_email(), "max_logins": A.MAX_LOGINS,
        "pode_gravar": not est["sem_pasta"] and not est["erro"],
        **secao,
    }
    return render_template("acessos/acessos.html", **contexto), status


def _sem_permissao():
    return render_template("cadastro/sem_permissao.html", titulo="Acessos", eyebrow="Base · Acessos",
                           area="A tela Acessos", email=_meu_email()), 403


def _gravar():
    if _de_outro_site():
        return _pagina(erro="Pedido de outro site: nada foi gravado.", status=403)
    certo = session.get(_CHAVE_CODIGO) or ""
    enviado = request.form.get("codigo") or ""
    if not certo or not hmac.compare_digest(enviado.encode(), certo.encode()):
        return _pagina(erro="O formulário venceu (a sessão mudou desde que a tela abriu): abra a tela de novo. Nada foi "
                            "gravado.", status=403)
    cfg = current_app.config
    acao = request.form.get("acao")
    if acao == "telas_setor":
        return _gravar_telas()
    digitado = (request.form.get("email") or "")[:300]
    try:
        if acao == "adicionar":
            e = A.adicionar(cfg, digitado, _quem(), admins_do_servidor())
            aviso = (f"{e} agora é administrador do Nexus. Vale no próximo clique da pessoa no Nexus, sem precisar "
                     "sair e entrar.")
        elif acao == "remover":
            e = A.remover(cfg, digitado, _quem(), admins_do_servidor(), eu=_meu_email(),
                          confirmo=request.form.get("confirmo") == "1")
            aviso = f"{e} deixou de ser administrador do Nexus. Vale no próximo clique da pessoa no Nexus."
        else:
            return _pagina(erro="Ação desconhecida: nada foi gravado.", status=400)
    except A.Recusado as ex:
        return _pagina(erro=str(ex), status=400, email_digitado=digitado if acao == "adicionar" else "")
    except A.Ilegivel as ex:
        return _pagina(erro=f"Não gravei: {ex}. Gravar agora apagaria o que está nele; avise a T.I.", status=409)
    except OSError as ex:
        log.error("Acessos: a gravação falhou (%s: %s); nada mudou.", type(ex).__name__, ex)
        return _pagina(erro=f"Não consegui gravar no disco ({type(ex).__name__}): nada mudou. Tente de novo; se "
                            "continuar, avise a T.I.", status=500)
    log.info("Acessos: %s %s (por %s).", "adicionou" if acao == "adicionar" else "removeu", e, _quem())
    if e == _meu_email() and acao == "remover":
        # tirou o próprio acesso: a tela já não abre para ele no próximo pedido; o Início não tem por que recusar
        return redirect(url_for("casca.inicio"), code=303)
    session[_CHAVE_AVISO] = aviso
    return redirect(url_for("torre_base.acessos"), code=303)


def _gravar_telas():
    """O Salvar da seção Telas por setor: as caixas marcadas são as telas que o setor vê; a que não veio marcada fecha."""
    cfg = current_app.config
    sid = request.form.get("setor", type=int)
    marcadas = request.form.getlist("tela")
    try:
        base, sessao = ST._banco()
        st = S.ler(base, sessao, forcar=True)
        if st.get("erro"):
            raise ST.Recusada(f"Não consegui ler os setores no banco ({st['erro'][:80]}): nada foi gravado.")
        setor = next((s for s in S.ativos(st["setores"]) if s["setor_id"] == sid), None)
        if not setor:
            raise ST.Recusada("Setor desconhecido ou excluído (a lista mudou desde que a tela abriu): nada foi gravado.")
        if ST.eh_administrador(setor["nome"]):
            raise ST.Recusada(f'O setor "{setor["nome"]}" vê todas as telas: não há o que marcar.')
        r = ST.gravar(sid, marcadas, _todas_as_telas(), cfg, base, sessao, _meu_email())
    except ST.Recusada as ex:
        return _pagina(erro=str(ex), status=400, setor_escolhido=sid)
    except Exception as ex:      # noqa: BLE001 — a publicação no banco falhou: nada mudou (o livro é trocado inteiro)
        log.error("Telas por setor: a gravação falhou (%s: %s); nada mudou.", type(ex).__name__, ex)
        return _pagina(erro=f"Não consegui gravar no banco ({type(ex).__name__}): nada mudou. Tente de novo; se "
                            "continuar, avise a T.I.", status=500, setor_escolhido=sid)
    n = r["liberadas"]
    telas = "nenhuma tela" if not n else "1 tela" if n == 1 else f"{n} telas"
    if r["gravadas"]:
        aviso = (f"{setor['nome']} agora vê {telas} ({r['gravadas']} mudança{'s' if r['gravadas'] != 1 else ''}). "
                 "Vale no próximo clique de quem é do setor (até 1 minuto).")
    else:
        aviso = f"Nada mudou: {setor['nome']} já via {telas}."
    session[_CHAVE_AVISO] = aviso
    return redirect(url_for("torre_base.acessos", setor=sid, _anchor="ace-setores"), code=303)


def registrar_acessos(bp) -> None:
    """Pendura a tela na torre Base (`/t/base/acessos`), vencendo o placeholder."""
    @bp.route("/acessos", methods=["GET", "POST"])
    def acessos():
        if not session.get("admin"):
            return _sem_permissao()
        if request.method == "POST":
            return _gravar()
        return _pagina()
