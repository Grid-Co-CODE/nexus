"""Base › E-mails automáticos (24/11/2026): o que o App de Campo manda sozinho por e-mail, para quem e se saiu. Só
administrador (Levi, 24/11/2026: "Só admin"). As regras e o contrato com o App: `nexus/campo/emails_app.py`.

Nesta 1ª fase a tela só lê: os livros `email_app_campo` (Tipos, Todos os envios e, enquanto a aba nova não existir, a
Envios do e-mail semanal da Segurança). A edição (ligar e desligar, modo teste, destinatários, com motivo e histórico)
vem pelo livro `nexus_email_controle · fato_email_regra`, depois de o App ler o controle."""
from datetime import datetime, timedelta, timezone

from flask import abort, current_app, render_template, session

from ...campo import emails_app as EA


_BRT = timezone(timedelta(hours=-3))


def _hora(d) -> str:
    """A hora de Brasília, como o Nexus mostra: "24/11 07:15"; sem data, "—"."""
    return d.astimezone(_BRT).strftime("%d/%m %H:%M") if d else "—"


def _so_admin():
    if not session.get("admin"):
        abort(403)


def _livros() -> tuple[dict, str]:
    """({aba: linhas ou None}, o erro da leitura). None = a aba ainda não existe (o App não publicou)."""
    from ...campo import visao
    from ...dados import livros
    try:
        base, sessao = visao._base(), visao._sessao()
        abas = livros.abas(base, sessao, EA.LIVRO) or {}
        out = {}
        for aba in (EA.ABA_TIPOS, EA.ABA_TODOS, EA.ABA_SEMANAL):
            out[aba] = livros.ler(base, sessao, EA.LIVRO, aba) if aba in abas else None
        return out, ""
    except Exception as ex:      # noqa: BLE001 — o banco fora: a tela diz e mostra os tipos sem número
        current_app.logger.exception("E-mails automáticos: o livro do App não abriu")
        return {aba: None for aba in (EA.ABA_TIPOS, EA.ABA_TODOS, EA.ABA_SEMANAL)}, type(ex).__name__


def _nomes() -> dict:
    """{código da pessoa: nome}: o cadastro do App e, para quem não está nele, as fichas do Registro mestre com e-mail
    (no semanal de 24/11/2026, 3 dos 8 destinatários só estavam no Registro mestre)."""
    from ...cadastro.ligacao_campo import codigo_da_pessoa
    from ...campo import livros_app
    chave = current_app.config.get("NEXUS_PESSOA_HMAC")
    out = {}
    try:
        from ...cadastro.telas import servico
        for p in servico().registros("pessoas"):
            cod = codigo_da_pessoa(chave, p.valores.get("email")) if p.valores.get("email") else None
            if cod and p.valores.get("nome"):
                out[cod] = p.valores["nome"]
    except Exception:            # noqa: BLE001 — sem o Registro mestre, fica só o cadastro do App
        current_app.logger.warning("E-mails automáticos: o Registro mestre não abriu para os nomes")
    try:
        out.update({c: v[1] for c, v in livros_app.pessoas_por_codigo(chave).items()})
    except Exception:            # noqa: BLE001 — sem o cadastro do App, o destinatário sai sem nome
        pass
    return out


def registrar_emails(bp) -> None:
    @bp.route("/emails-automaticos")
    def emails_automaticos():
        _so_admin()
        lv, erro = _livros()
        agora = datetime.now(timezone.utc)
        dados = EA.montar(lv[EA.ABA_TIPOS], lv[EA.ABA_TODOS], lv[EA.ABA_SEMANAL], agora)
        return render_template("emails_automaticos.html", d=dados, erro=erro, dias=EA.DIAS, situacao=EA.SITUACAO,
                               hora=_hora)

    @bp.route("/emails-automaticos/<tipo>")
    def emails_automaticos_tipo(tipo):
        _so_admin()
        lv, erro = _livros()
        agora = datetime.now(timezone.utc)
        dados = EA.montar(lv[EA.ABA_TIPOS], lv[EA.ABA_TODOS], lv[EA.ABA_SEMANAL], agora)
        t = next((x for x in dados["tipos"] if x["tipo"] == tipo), None)
        if t is None:
            abort(404)
        envios = EA.historico(lv[EA.ABA_TODOS], lv[EA.ABA_SEMANAL], tipo, _nomes(), agora)
        return render_template("emails_automaticos.html", d=dados, t=t, envios=envios, erro=erro, dias=EA.DIAS,
                               historico_dias=EA.HISTORICO_DIAS, situacao=EA.SITUACAO, hora=_hora)
