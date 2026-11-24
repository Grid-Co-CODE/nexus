"""Base › E-mails automáticos (24/11/2026): o que o App de Campo manda sozinho por e-mail, para quem, se saiu, e o
controle de cada um. Só administrador (Levi, 24/11/2026: "Só admin").

- Lê os livros que o App publica (`email_tipos_app_campo · Tipos`, `email_todos_envios_app_campo · Todos os envios` e,
  enquanto este não existir, o `email_app_campo · Envios` do semanal): as regras em `nexus/campo/emails_app.py`.
- Escreve a regra de cada tipo no livro `nexus_email_controle · fato_email_regra` (só acréscimo, cifrada e assinada),
  que o App relê a cada 5 minutos: `nexus/campo/emails_controle.py`.
O contrato inteiro com o App: `nexus/cadastro/CLAUDE.md`, seção "E-mails automáticos"."""
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from flask import abort, current_app, redirect, render_template, request, session, url_for

from ...auth.origem import de_outro_site
from ...campo import emails_app as EA
from ...campo import emails_controle as EC

_BRT = timezone(timedelta(hours=-3))
_PARES = ((EA.LIVRO_TIPOS, EA.ABA_TIPOS), (EA.LIVRO_TODOS, EA.ABA_TODOS), (EA.LIVRO_SEMANAL, EA.ABA_SEMANAL))
_CHAVE_FORM, _CHAVE_AVISO = "emails_auto_form", "emails_auto_aviso"


def _hora(d) -> str:
    """A hora de Brasília, como o Nexus mostra: "24/11 07:15"; sem data, "—". Aceita o ISO do livro."""
    if isinstance(d, str):
        d = EA._quando(d)
    return d.astimezone(_BRT).strftime("%d/%m %H:%M") if d else "—"


def _so_admin():
    if not session.get("admin"):
        abort(403)


def _livros() -> tuple[dict, str]:
    """({(livro, aba): linhas ou None}, o erro da leitura). None = o livro ainda não existe (o App não publicou). Uma
    listagem do banco para os três (`visao.carregar`, a cópia de 2 min das telas de campo)."""
    from ...campo import visao
    try:
        visao.carregar(_PARES)
        out = {}
        for livro, aba in _PARES:
            abas = (visao._LIVROS.get(("_abas", livro)) or (0, {}))[1]
            out[(livro, aba)] = visao._livro(livro, aba) if aba in abas else None
        return out, ""
    except Exception as ex:      # noqa: BLE001 — o banco fora: a tela diz e mostra os tipos sem número
        current_app.logger.exception("E-mails automáticos: os livros do App não abriram")
        return {p: None for p in _PARES}, type(ex).__name__


def _pessoas() -> list[dict]:
    """[{nome, email}] de quem pode receber: as fichas do Registro mestre com e-mail e o pessoal do Fracttal (a cópia de
    Base → Acessos → Pessoas e setores, sem ler o Fracttal na hora). Um por e-mail; a ficha vence o Fracttal no nome."""
    out: dict[str, str] = {}
    try:
        from ...cadastro.telas import servico
        for p in servico().registros("pessoas"):
            e = str(p.valores.get("email") or "").strip().lower()
            if "@" in e and p.valores.get("nome"):
                out.setdefault(e, " ".join(str(p.valores["nome"]).split()))
    except Exception:            # noqa: BLE001 — sem o Registro mestre, fica o Fracttal
        current_app.logger.warning("E-mails automáticos: o Registro mestre não abriu para as pessoas")
    try:
        from ...cadastro.telas_fracttal import copia_sem_esperar
        for x in copia_sem_esperar()["rel"].get("linhas") or []:
            e = str(x.get("email") or "").strip().lower()
            if "@" in e and x.get("nome"):
                out.setdefault(e, " ".join(str(x["nome"]).split()))
    except Exception:            # noqa: BLE001 — sem o Fracttal, fica o Registro mestre
        current_app.logger.warning("E-mails automáticos: o pessoal do Fracttal não abriu")
    return [{"email": e, "nome": n} for e, n in sorted(out.items(), key=lambda t: t[1].lower())]


def _nomes(pessoas: list[dict], extras=()) -> dict:
    """{código da pessoa: nome}: as pessoas acima, o cadastro do App (no semanal de 24/11/2026, 3 dos 8 destinatários só
    estavam no Registro mestre) e, para o e-mail das regras que não é de ninguém (a caixa do COS), o próprio e-mail: a
    tela é só de administrador, e é o nome que ela tem."""
    from ...cadastro.ligacao_campo import codigo_da_pessoa
    from ...campo import livros_app
    chave = current_app.config.get("NEXUS_PESSOA_HMAC")
    out = {}
    for e in extras:
        if c := codigo_da_pessoa(chave, e):
            out[c] = e
    try:
        out.update({c: v[1] for c, v in livros_app.pessoas_por_codigo(chave).items()})
    except Exception:            # noqa: BLE001 — sem o cadastro do App, o destinatário sai pelo Registro mestre
        pass
    for p in pessoas:
        if c := codigo_da_pessoa(chave, p["email"]):
            out[c] = p["nome"]
    return out


def _controle() -> tuple[list[dict], dict, str]:
    """(as linhas do livro de controle, as regras que valem, o erro da leitura)."""
    cfg = current_app.config
    est = EC.ler(cfg)
    return est["linhas"], EC.vigentes(est["linhas"], cfg.get("NEXUS_PESSOA_HMAC")), est["erro"]


def _usuario() -> dict:
    u = session.get("usuario")
    return u if isinstance(u, dict) else {}


def _quem_hmac() -> str:
    from ...cadastro.ligacao_campo import codigo_da_pessoa
    return codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), _usuario().get("email")) or ""


def _codigo_form() -> str:
    c = session.get(_CHAVE_FORM)
    if not c:
        c = session[_CHAVE_FORM] = secrets.token_urlsafe(16)
    return c


def _pagina(tipo: str | None = None, erro_form: str = "", status: int = 200, form: dict | None = None):
    lv, erro = _livros()
    linhas, regras, erro_ctl = _controle()
    agora = datetime.now(timezone.utc)
    dados = EA.montar(lv[_PARES[0]], lv[_PARES[1]], lv[_PARES[2]], agora, regras)
    ctx = {"d": dados, "erro": erro, "erro_ctl": erro_ctl, "dias": EA.DIAS, "situacao": EA.SITUACAO, "hora": _hora,
           "efeito": EC.efeito, "aviso": session.pop(_CHAVE_AVISO, None), "sem_chave":
           not str(current_app.config.get("NEXUS_PESSOA_HMAC") or "").strip()}
    if tipo is None:
        return render_template("emails_automaticos.html", **ctx), status
    t = next((x for x in dados["tipos"] if x["tipo"] == tipo), None)
    if t is None or tipo not in EC.TIPOS:
        abort(404)
    pessoas = _pessoas()
    da_regra = sorted({e for r in regras.values() for e in r["destinatarios"]})
    nomes = _nomes(pessoas, da_regra)
    por_email = {p["email"]: p["nome"] for p in pessoas}
    mudancas = EC.historico(linhas, current_app.config.get("NEXUS_PESSOA_HMAC"), tipo)
    for m in mudancas:
        m["quem"] = nomes.get(m["quem_hmac"]) or ("administrador (senha)" if not m["quem_hmac"] else "Fora do cadastro")
    rg = t["regra"]
    if form is None:
        form = {"ligado": rg["ligado"] if rg else True, "modo": rg["modo"] if rg else "normal",
                "dest": list(rg["destinatarios"]) if rg else [], "substitui": rg["substitui"] if rg else False,
                "motivo": ""}
    ctx.update(t=t, envios=EA.historico(lv[_PARES[1]], lv[_PARES[2]], tipo, nomes, agora),
               historico_dias=EA.HISTORICO_DIAS, mudancas=mudancas, por_email=por_email, form=form,
               opcoes=[f"{p['nome']} · {p['email']}" for p in pessoas],
               erro_form=erro_form, codigo=_codigo_form(), quem_deixa=EA.QUEM_DEIXA_DE_SABER.get(tipo, ""))
    return render_template("emails_automaticos.html", **ctx), status


def registrar_emails(bp) -> None:
    @bp.route("/emails-automaticos")
    def emails_automaticos():
        _so_admin()
        return _pagina()

    @bp.route("/emails-automaticos/<tipo>")
    def emails_automaticos_tipo(tipo):
        _so_admin()
        return _pagina(tipo)

    @bp.route("/emails-automaticos/<tipo>/regra", methods=["POST"])
    def emails_automaticos_regra(tipo):
        """Publica a regra do tipo (1 linha a mais no livro). Recusa: 400/403/409 na própria página, com o formulário
        como veio; gravou: 303 de volta (F5 não repete)."""
        _so_admin()
        if tipo not in EC.TIPOS:
            abort(404)
        f = request.form
        padrao = f.get("acao") == "padrao"
        form = {"ligado": True if padrao else f.get("ligado") == "sim", "modo": "normal" if padrao else
                (f.get("modo") or "normal"), "dest": [] if padrao else [x[:200] for x in f.getlist("dest")][:60],
                "substitui": False if padrao else f.get("substitui") == "sim", "motivo": (f.get("motivo") or "")[:400]}
        if de_outro_site():
            return _pagina(tipo, "Pedido de outro site: nada foi gravado.", 403, form)
        certo, enviado = session.get(_CHAVE_FORM) or "", f.get("codigo") or ""
        if not certo or not hmac.compare_digest(enviado.encode(), certo.encode()):
            return _pagina(tipo, "O formulário venceu (a sessão mudou desde que a tela abriu): abra a tela de novo. "
                                 "Nada foi gravado.", 403, form)
        pessoas = _pessoas()
        try:
            r = EC.publicar(current_app.config, tipo=tipo, ligado=form["ligado"], modo=form["modo"],
                            destinatarios=form["dest"], substitui=form["substitui"], motivo=form["motivo"],
                            quem_hmac=_quem_hmac(), nomes=[p["nome"] for p in pessoas],
                            conhecidos=[p["email"] for p in pessoas], confirmou_critico=f.get("confirmo") == "1",
                            criticos=EA.CRITICOS)
        except EC.Recusada as ex:
            return _pagina(tipo, str(ex), 409, form)
        except Exception as ex:  # noqa: BLE001 — a publicação no banco falhou: nada mudou (o livro é trocado inteiro)
            current_app.logger.error("E-mails automáticos: a gravação da regra falhou (%s: %s)", type(ex).__name__, ex)
            return _pagina(tipo, f"Não consegui gravar no banco ({type(ex).__name__}): nada mudou. Tente de novo; se "
                                 "continuar, avise a T.I.", 500, form)
        current_app.logger.info("E-mails automáticos: regra de %s publicada (mudou=%s)", tipo, r["mudou"])
        session[_CHAVE_AVISO] = (("Regra publicada: " + EC.efeito(r["regra"]) + ". O App relê o controle a cada 5 "
                                  "minutos; a lista de cima confirma quando ele publicar os Tipos (de hora em hora).")
                                 if r["mudou"] else "Nada mudou: a regra já era esta.")
        return redirect(url_for("torre_base.emails_automaticos_tipo", tipo=tipo), code=303)
