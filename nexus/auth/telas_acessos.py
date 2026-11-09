"""Tela Base → Acessos (11/10/2026): quem é administrador do Nexus, dar e tirar pela tela, e quem entrou em 30 dias.

Só administrador vê e grava (quem não é recebe a página "só para administradores" do Cadastro, com o porquê). O dado e
as regras moram em `acessos.py`; aqui ficam a página e o portão do POST:
- só da própria página: o `Sec-Fetch-Site`/`Origin` com a mesma régua da moldura da Performance (`_de_outro_site`) e um
  código do formulário guardado na sessão (o cookie `Lax` já barra o POST de outro site; dar administrador é a ação
  mais sensível do Nexus, então confere duas vezes);
- POST que grava volta por 303 à tela (F5 não repete), com o aviso guardado na sessão.

Telas por setor (12/10/2026, Levi: "uma seção no BASE > ACESSOS onde eu possa controlar o que cada pessoa de setor pode
ver ao logar no Nexus"): um setor por vez, com a árvore do menu em caixas de marcar; o Salvar grava só o que mudou no
livro `nexus_setor_telas` (regras e portão em `setor_telas.py`). O setor de cada pessoa é o da aba Pessoas e setores de Base → Acessos;
aqui aparece também na lista de quem entrou, pelo código do e-mail (sem o e-mail ir ao banco).

A aba Administradores do App de Campo (05/11/2026, `?aba=admins_app`; as contas em `telas_admins_app.py`, o dado em
`nexus/pcm/admins_app.py`): o pôr (da lista ou, desde a 2ª volta de 05/11/2026, pelo e-mail: o avulso) e o tirar vêm por
este mesmo POST, com o mesmo código do formulário e a mesma régua de origem (dar administrador do App é tão sensível
quanto dar o do Nexus); recusa volta à aba com o motivo e 409.
"""
import hmac
import logging
import secrets
from collections import Counter

from flask import current_app, redirect, render_template, request, session, url_for

from ..cadastro import setor_ids as SID
from ..cadastro import setores as S
from . import acessos as A
from . import clientes as CL
from . import admins_do_servidor
from . import setor_telas as ST
from .sessao import email_da_sessao as _meu_email
from .origem import de_outro_site as _de_outro_site

log = logging.getLogger(__name__)

_CHAVE_CODIGO = "acessos_codigo"
_CHAVE_AVISO = "acessos_aviso"
_CHAVE_AVISO_APP = "acessos_app_aviso"
ABA_APP = "admins_app"
ABA_CLIENTES = "clientes"
_CHAVE_LINK = "acessos_cliente_link"
_ACOES_CLIENTES = ("cliente_adicionar", "cliente_link", "cliente_remover")
_ACOES_APP = ("admin_app_por", "admin_app_por_email", "admin_app_tirar")


def _quem() -> str:
    """Quem fez a mudança, para a lista e a auditoria: o e-mail do Fracttal, ou "senha de administrador"."""
    return _meu_email() or A.SENHA_DE_ADMIN


def _codigo() -> str:
    """O código do formulário desta sessão (nasce na 1ª visita; o login limpa a sessão e troca o código)."""
    if not session.get(_CHAVE_CODIGO):
        session[_CHAVE_CODIGO] = secrets.token_urlsafe(24)
    return session[_CHAVE_CODIGO]


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


def _secao_setores(escolhido: int | None, logins: list[dict], admins: list[dict]) -> dict:
    """A seção Telas por setor: os setores (com quantas pessoas e telas), a árvore do menu marcada para o setor escolhido
    e o que cada setor vê (para o "Copiar de"). Põe também o setor em cada login de 30 dias e em cada administrador."""
    from ..cadastro.ligacao_campo import codigo_da_pessoa
    from ..casca import _telas_prontas
    app = current_app._get_current_object()
    cfg = current_app.config
    st, tl = _ler_setores()
    torres = _torres()
    todas = {ST.chave(t.id, s.id) for t in torres for s in t.telas}
    prontas = _telas_prontas(app)
    matriz = ST.vigentes(tl["decisoes"])
    pessoas = Counter(v for v in S.vigentes(st["decisoes"]).values() if v)
    # a conta de cada setor leva as telas que são DELE (Tela.do_setor, 13/10/2026): ele as vê sem marcar
    setores = [{"id": s["setor_id"], "nome": s["nome"], "pessoas": pessoas.get(s["setor_id"], 0),
                "telas": len((matriz.get(s["setor_id"], set()) | ST.das_do_setor({"id": s["setor_id"], "nome": s["nome"]}))
                             & todas)}
               for s in S.ativos(st["setores"])]
    # o setor dos clientes (07/11/2026): não está no dim_setor; vê só as telas que recortam pelas usinas do cliente
    possiveis = ST.telas_do_cliente_possiveis()
    if setores or not st.get("erro"):
        contas = CL.estado(cfg)["contas"]
        setores.append({"id": SID.CLIENTES, "nome": "Clientes", "cliente": True,
                        "pessoas": sum(1 for c in contas if c.get("status") == "ativa"),
                        # a conta é a das telas que o cliente JÁ vê (marcadas e com o filtro pronto)
                        "telas": len(matriz.get(SID.CLIENTES, set()) & possiveis)})
    sel = next((s for s in setores if s["id"] == escolhido), None) or (setores[0] if setores else None)
    do_setor = ST.das_do_setor(sel) if sel and not sel.get("cliente") else set()
    marcadas = (matriz.get(sel["id"], set()) if sel else set()) | do_setor
    arvore = []
    for t in torres:
        telas = [{"chave": ST.chave(t.id, s.id), "nome": s.nome, "pronta": f"/t/{t.id}/{s.id}" in prontas,
                  "marcada": ST.chave(t.id, s.id) in marcadas, "do_setor": ST.chave(t.id, s.id) in do_setor,
                  "de_todos": s.de_todos,
                  # no setor Clientes (08/11/2026, Levi: "a ideia é liberar os campos e conforme for o cliente
                  # aparecerá as usinas só daquele cliente"): toda tela se marca; a que ainda não recorta pelas usinas
                  # do cliente leva o aviso "falta o filtro" e não abre para ele até o filtro dela ficar pronto
                  "falta_filtro": bool(sel and sel.get("cliente")) and not s.do_cliente}
                 # a tela só do cliente (a Visão do cliente, 09/11/2026) não se marca para um setor da Grid
                 for s in t.telas if not s.so_do_cliente or (sel and sel.get("cliente"))]
        arvore.append({"id": t.id, "nome": t.nome, "icone": t.icone, "telas": telas,
                       "marcadas": sum(x["marcada"] for x in telas)})
    # o setor de quem entrou e de cada administrador: pelo código do e-mail, o mesmo que a decisão de setor grava (o
    # e-mail não vai ao banco). Administrador com setor segue vendo tudo: o setor só aparece, não restringe.
    por_codigo = ST.setor_de_cada_codigo(st["decisoes"])
    nome_do = {s["id"]: s["nome"] for s in setores}
    chave_hmac = cfg.get("NEXUS_PESSOA_HMAC")
    de_clientes = {c["email"] for c in CL.estado(cfg)["contas"]}
    for x in logins + admins:
        cod = None if x.get("senha") else codigo_da_pessoa(chave_hmac, x["email"])
        x["setor"] = nome_do.get(por_codigo.get(cod)) if cod else None
        if not x["setor"] and x.get("email") in de_clientes:
            x["setor"] = "Clientes"            # quem entrou pelo acesso de cliente (07/11/2026) não é "sem setor"
    ilegivel = not st.get("lido_em") or not tl.get("lido_em")
    from . import pre_carga as PC
    pc = PC.resumo(app)
    if pc["volta"]:
        from datetime import datetime, timedelta, timezone
        nomes = {f"{t.id}/{s.id}": f"{t.nome} → {s.nome}" for t in torres for s in t.telas}
        v = pc["volta"]
        v["hora"] = datetime.fromtimestamp(v["fim"], timezone(timedelta(hours=-3))).strftime("%d/%m %H:%M")
        v["lenta"] = (nomes.get(v["mais_lenta"][0], v["mais_lenta"][0]), f"{v['mais_lenta'][1]:.1f}".replace(".", ","))
        v["s_txt"] = f"{v['s']:.1f}".replace(".", ",")
    return {
        "pre_carga": pc,
        "portao": ST.estado(cfg), "setores": setores, "setor_sel": sel, "arvore": arvore,
        "total_telas_menu": len(todas), "marcadas_sel": len(marcadas & todas),
        "matriz_setores": {str(s["id"]): sorted(matriz.get(s["id"], set()) & todas) for s in setores},
        "pessoas_com_setor": sum(pessoas.get(s["id"], 0) for s in setores),
        "setores_erro": " · ".join(e for e in (st.get("erro"), tl.get("erro")) if e),
        "pode_gravar_setores": bool(cfg.get("GRIDCO_SQL_TOKEN")) and not ilegivel,
        "sem_token": not cfg.get("GRIDCO_SQL_TOKEN"), "tem_hmac": bool(chave_hmac),
        "sem_setor_30d": sum(1 for x in logins if not x["senha"] and not x["setor"] and not x["admin"]),
    }


def _pagina_admins_app(erro: str | None = None, status: int = 200, email_digitado: str = ""):
    """A aba Administradores do App de Campo (05/11/2026). Na recusa do avulso, o e-mail digitado volta ao campo."""
    from . import telas_admins_app as TAA
    return render_template("acessos/acessos.html", aba=ABA_APP, **TAA.contexto(current_app.config), codigo=_codigo(),
                           erro=erro, aviso=session.pop(_CHAVE_AVISO_APP, None),
                           email_digitado=email_digitado), status


def _pagina(erro: str | None = None, status: int = 200, email_digitado: str = "", setor_escolhido: int | None = None):
    cfg = current_app.config
    if request.method == "GET" and request.args.get("aba") == "pessoas":
        # a aba Pessoas e setores (25/10/2026: era a tela Base > Acessos > Pessoas e setores); ela lê o Fracttal, e a dos
        # administradores do App usa a cópia dela (a aba de telas não lê)
        from ..cadastro import telas_fracttal as TF
        return render_template("acessos/acessos.html", aba="pessoas", **TF.contexto(cfg, request.args)), status
    if request.method == "GET" and request.args.get("aba") == ABA_APP:
        return _pagina_admins_app(erro, status)
    if request.method == "GET" and request.args.get("aba") == ABA_CLIENTES:
        return _pagina_clientes(erro, status)
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
    admins = _linhas_de_admins(servidor, est, ultimo)
    secao = _secao_setores(setor_escolhido, logins, admins)
    contexto = {
        "admins": admins, "auditoria": [dict(x, quando_br=A.hora_br(x.get("quando"))) for x in est["auditoria"]],
        "logins": logins, "sem_pasta": est["sem_pasta"], "arquivo_erro": est["erro"],
        "total_servidor": len(servidor), "total_tela": len(da_tela - servidor), "n_tela": len(da_tela),
        "pessoas_30d": sum(1 for x in logins if not x["senha"]),
        "admins_30d": sum(1 for x in logins if x["admin"] in ("do servidor", "pela tela")),
        "codigo": _codigo(), "erro": erro, "aviso": session.pop(_CHAVE_AVISO, None),
        "email_digitado": email_digitado, "eu": _meu_email(), "max_logins": A.MAX_LOGINS,
        "pode_gravar": not est["sem_pasta"] and not est["erro"],
        **secao,
    }
    # a aba Histórico e registros (07/11/2026) usa a mesma conta: o registro de mudanças e quem entrou em 30 dias
    aba = "historico" if request.method == "GET" and request.args.get("aba") == "historico" else "telas"
    return render_template("acessos/acessos.html", aba=aba, **contexto), status


def _sem_permissao():
    return render_template("cadastro/sem_permissao.html", titulo="Acessos", eyebrow="Base · Acessos",
                           area="A tela Acessos", email=_meu_email()), 403


def _gravar():
    acao = request.form.get("acao")
    # a recusa volta à aba de onde o pedido veio
    pagina = (_pagina_admins_app if acao in _ACOES_APP else _pagina_clientes if acao in _ACOES_CLIENTES
              else _pagina)
    if _de_outro_site():
        return pagina(erro="Pedido de outro site: nada foi gravado.", status=403)
    certo = session.get(_CHAVE_CODIGO) or ""
    enviado = request.form.get("codigo") or ""
    if not certo or not hmac.compare_digest(enviado.encode(), certo.encode()):
        return pagina(erro="O formulário venceu (a sessão mudou desde que a tela abriu): abra a tela de novo. Nada foi "
                           "gravado.", status=403)
    cfg = current_app.config
    if acao == "telas_setor":
        return _gravar_telas()
    if acao in _ACOES_APP:
        return _gravar_admins_app(acao)
    if acao in _ACOES_CLIENTES:
        return _gravar_clientes(acao)
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


def _gravar_admins_app(acao: str):
    """Pôr (da lista ou pelo e-mail, o avulso) ou tirar um administrador do App de Campo. Recusa (sem código, pessoa fora
    da lista, o e-mail de outro domínio, a lista que mudou, sem a NEXUS_PESSOA_HMAC): 409 com o motivo, na própria aba.
    Gravou: 303 de volta à aba (F5 não repete)."""
    from ..pcm import admins_app as AA
    from . import telas_admins_app as TAA
    cfg = current_app.config
    usuario = session.get("usuario") if isinstance(session.get("usuario"), dict) else None
    obs = (request.form.get("obs") or "")[:2000]
    email = ""
    try:
        if acao == "admin_app_por":
            # o rádio se chama `pessoa` desde a 2ª volta de 05/11/2026 (o número da ficha ou o código de quem não tem);
            # o `pessoa_id` é o da página aberta antes do deploy, que só tinha fichas
            escolha = (request.form.get("pessoa") or request.form.get("pessoa_id") or "").strip()[:120]
            if not escolha:
                return _pagina_admins_app(erro="Escolha a pessoa: nada foi gravado.", status=400)
            texto = TAA.por(cfg, escolha, obs, usuario)
        elif acao == "admin_app_por_email":
            email = (request.form.get("email") or "")[:300]
            if not email.strip():
                return _pagina_admins_app(erro="Digite o e-mail da pessoa: nada foi gravado.", status=400)
            texto = TAA.por_email(cfg, email, obs, usuario)
        else:
            texto = TAA.tirar(cfg, (request.form.get("pessoa_hmac") or "")[:80], usuario)
    except AA.Recusada as ex:
        return _pagina_admins_app(erro=str(ex), status=409, email_digitado=email.strip())
    except Exception as ex:      # noqa: BLE001 — a publicação no banco falhou: nada mudou (o livro é trocado inteiro)
        log.error("Administradores do App: a gravação falhou (%s: %s); nada mudou.", type(ex).__name__, ex)
        return _pagina_admins_app(erro=f"Não consegui gravar no banco ({type(ex).__name__}): nada mudou. Tente de novo; "
                                       "se continuar, avise a T.I.", status=500)
    log.info("Administradores do App: %s (por %s).", acao, _quem())
    session[_CHAVE_AVISO_APP] = texto
    return redirect(url_for("torre_base.acessos", aba=ABA_APP), code=303)


def _gravar_telas():
    """O Salvar da seção Telas por setor: as caixas marcadas são as telas que o setor vê; a que não veio marcada fecha."""
    cfg = current_app.config
    sid = request.form.get("setor", type=int)
    marcadas = request.form.getlist("tela")
    if sid == SID.CLIENTES:
        return _gravar_telas_clientes(marcadas)
    try:
        base, sessao = ST._banco()
        st = S.ler(base, sessao, forcar=True)
        if st.get("erro"):
            raise ST.Recusada(f"Não consegui ler os setores no banco ({st['erro'][:80]}): nada foi gravado.")
        setor = next((s for s in S.ativos(st["setores"]) if s["setor_id"] == sid), None)
        if not setor:
            raise ST.Recusada("Setor desconhecido ou excluído (a lista mudou desde que a tela abriu): nada foi gravado.")
        # as telas que são DO setor (Tela.do_setor) não passam pela matriz: ele as vê sempre, marcadas ou não
        do_setor = ST.das_do_setor({"id": setor["setor_id"], "nome": setor["nome"]})
        r = ST.gravar(sid, [m for m in marcadas if m not in do_setor], _todas_as_telas() - do_setor, cfg, base, sessao,
                      _meu_email())
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


def _gravar_telas_clientes(marcadas: list[str]):
    """O Salvar do setor Clientes: qualquer tela se marca (08/11/2026); o cliente só abre as marcadas que já recortam
    pelas usinas dele (Tela.do_cliente; `setor_telas._acesso_do_cliente`), e a marca das outras espera o filtro."""
    cfg = current_app.config
    possiveis = ST.telas_do_cliente_possiveis()
    todas = _todas_as_telas()
    try:
        if not set(marcadas) <= todas:
            raise ST.Recusada("Tela desconhecida na matriz: nada foi gravado.")
        base, sessao = ST._banco()
        r = ST.gravar(SID.CLIENTES, marcadas, todas, cfg, base, sessao, _meu_email())
    except ST.Recusada as ex:
        return _pagina(erro=str(ex), status=400, setor_escolhido=SID.CLIENTES)
    except Exception as ex:      # noqa: BLE001
        log.error("Telas por setor (Clientes): a gravação falhou (%s: %s); nada mudou.", type(ex).__name__, ex)
        return _pagina(erro=f"Não consegui gravar no banco ({type(ex).__name__}): nada mudou.", status=500,
                       setor_escolhido=SID.CLIENTES)
    prontas = len(set(marcadas) & possiveis)
    esperam = len(set(marcadas) - possiveis)
    txt = ("nenhuma tela" if not prontas else "1 tela" if prontas == 1 else f"{prontas} telas")
    espera = (f" {esperam} {'marcada espera' if esperam == 1 else 'marcadas esperam'} o filtro por cliente e "
              f"{'aparece' if esperam == 1 else 'aparecem'} quando ele ficar pronto." if esperam else "")
    session[_CHAVE_AVISO] = ((f"Clientes agora veem {txt}." if r["gravadas"] else f"Nada mudou: Clientes já viam {txt}.")
                             + espera)
    return redirect(url_for("torre_base.acessos", setor=SID.CLIENTES, _anchor="ace-setores"), code=303)


# ── a aba Clientes (07/11/2026): as contas de acesso dos clientes ──────────────────────────────────────────────
def _clientes_do_cadastro() -> tuple[list[tuple[int, str]], str]:
    """[(cliente_id, nome)] do cadastro do Nexus, em ordem de nome; e o erro, se o cadastro não abriu."""
    try:
        from ..campo import visao
        nomes = visao._Base().nome_cliente
        return sorted(((i, n) for i, n in nomes.items() if i and n), key=lambda x: x[1].lower()), ""
    except Exception as ex:      # noqa: BLE001 — sem o cadastro, a aba avisa e não cria conta
        return [], type(ex).__name__


def _pagina_clientes(erro: str | None = None, status: int = 200, email_digitado: str = ""):
    cfg = current_app.config
    est = CL.estado(cfg)
    opcoes, erro_cadastro = _clientes_do_cadastro()
    contas = []
    for c in sorted(est["contas"], key=lambda x: (x.get("status") != "ativa", x.get("cliente") or "", x["email"])):
        expira = A._de_iso(c.get("convite_expira"))
        situacao = ("removida" if c.get("status") != "ativa" else "ativa" if c.get("senha")
                    else "convite" if expira and expira > A._agora() else "convite_vencido")
        contas.append({**c, "situacao": situacao, "criada_br": A.hora_br(c.get("criada_em")),
                       "senha_br": A.hora_br(c.get("senha_em")), "expira_br": A.hora_br(c.get("convite_expira"))})
    return render_template("acessos/acessos.html", aba=ABA_CLIENTES, contas_clientes=contas, opcoes_clientes=opcoes,
                           erro_cadastro=erro_cadastro, sem_pasta=est["sem_pasta"], arquivo_erro=est["erro"],
                           link_cliente=session.pop(_CHAVE_LINK, None), codigo=_codigo(), erro=erro,
                           aviso=session.pop(_CHAVE_AVISO, None), email_digitado=email_digitado,
                           pode_gravar=not est["sem_pasta"] and not est["erro"],
                           auditoria_clientes=[dict(x, quando_br=A.hora_br(x.get("quando")))
                                               for x in reversed(est["auditoria"])]), status


def _link_do_convite(token: str) -> str:
    from ..prefixo import na_raiz
    return request.host_url.rstrip("/") + na_raiz("/entrar") + "?convite=" + token


def _gravar_clientes(acao: str):
    """Criar a conta (com o link), gerar um link novo ou remover o acesso de um cliente."""
    cfg = current_app.config
    digitado = (request.form.get("email") or "")[:300]
    try:
        if acao == "cliente_adicionar":
            cid = request.form.get("cliente_id", type=int)
            opcoes = dict(_clientes_do_cadastro()[0])
            if cid not in opcoes:
                raise CL.Recusado("Escolha o cliente do cadastro: é por ele que o Nexus mostra só as usinas dele.")
            e, token = CL.adicionar(cfg, digitado, cid, opcoes[cid], _quem())
            session[_CHAVE_LINK] = {"email": e, "link": _link_do_convite(token), "novo": True}
            aviso = f"{e} agora tem acesso de cliente ({opcoes[cid]}). Mande o link abaixo: ele cria a senha por ele."
        elif acao == "cliente_link":
            e = A.email_normal(digitado)
            token = CL.gerar_link(cfg, e, _quem())
            session[_CHAVE_LINK] = {"email": e, "link": _link_do_convite(token), "novo": False}
            aviso = f"Link novo para {e}. O anterior deixou de valer."
        else:
            e = CL.remover(cfg, digitado, _quem())
            aviso = f"{e} não tem mais acesso. Se estiver dentro do Nexus, sai no próximo clique."
    except CL.Recusado as ex:
        return _pagina_clientes(erro=str(ex), status=400, email_digitado=digitado if acao == "cliente_adicionar" else "")
    except CL.Ilegivel as ex:
        return _pagina_clientes(erro=f"Não gravei: {ex}. Gravar agora apagaria o que está nele; avise a T.I.", status=409)
    except OSError as ex:
        log.error("Clientes: a gravação falhou (%s: %s); nada mudou.", type(ex).__name__, ex)
        return _pagina_clientes(erro=f"Não consegui gravar no disco ({type(ex).__name__}): nada mudou.", status=500)
    log.info("Clientes: %s %s (por %s).", acao, e, _quem())
    session[_CHAVE_AVISO] = aviso
    return redirect(url_for("torre_base.acessos", aba=ABA_CLIENTES), code=303)


def registrar_acessos(bp) -> None:
    """Pendura a tela na torre Base (`/t/base/acessos`), vencendo o placeholder."""
    @bp.route("/acessos", methods=["GET", "POST"])
    def acessos():
        if not session.get("admin"):
            return _sem_permissao()
        if request.method == "POST":
            return _gravar()
        return _pagina()
