"""Base › E-mails automáticos › Novo e-mail (25/11/2026, a fase 4 dos e-mails do Nexus): criar, editar, ver a prévia,
mandar a prévia para si e mandar agora um e-mail montado com dados do Nexus. Só administrador. A regra do modelo (o que
ele é, onde mora, como monta): `nexus/emails/modelos.py`; o editor nasce sempre desligado (`modelos.salvar`)."""
from datetime import datetime, timezone

from flask import abort, current_app, render_template, request

from ...campo import emails_controle as EC


def _t():
    from . import emails_tela as T
    return T


def _form(f) -> dict:
    """O modelo como o formulário manda (a conferência é a do `modelos.normalizar`)."""
    def lista(papel, emails):
        out = list(f.getlist(papel))
        out += [x.strip() for x in str(f.get(emails) or "").replace(";", ",").replace("\n", ",").split(",") if x.strip()]
        return out[:40]
    return {"nome": f.get("nome", ""), "assunto": f.get("assunto", ""), "texto": f.get("texto", ""),
            "fontes": f.getlist("fontes"), "envio": f.get("envio", "um_so"),
            "para": lista("para_papel", "para_emails"), "cc": lista("cc_papel", "cc_emails"),
            "agenda": {"freq": f.get("freq", "manual"), "hora": f.get("hora", "07:00"), "dia": f.get("dia") or 0,
                       "uteis": f.get("uteis") == "1"},
            "pular_vazio": f.get("pular_vazio") == "1"}


def _editor(m: dict | None, modelo_id: str = "", erro: str = "", status: int = 200):
    from ...emails import fontes as F
    from ...emails import modelos as MO
    from ...emails import papeis as P
    T = _t()
    m = m or {"nome": "", "assunto": "", "texto": "", "fontes": [], "envio": "por_responsavel", "para": [], "cc": [],
              "agenda": {"freq": "manual", "hora": "07:00", "uteis": True}, "pular_vazio": True}
    papeis = P.nomes()
    return render_template(
        "emails_modelo.html", m=m, modelo_id=modelo_id, erro=erro, fontes=F.FONTES, envios=MO.ENVIOS, freqs=MO.FREQ,
        dias_semana=MO.DIAS_SEMANA, papeis=papeis, da_usina=P.DA_USINA, codigo=T._codigo_form(),
        para_emails=", ".join(x for x in m.get("para") or [] if x not in papeis),
        cc_emails=", ".join(x for x in m.get("cc") or [] if x not in papeis)), status


def _modelo_ou_404(modelo_id: str) -> dict:
    from ...emails import modelos as MO
    m = MO.vigentes(current_app.config).get(modelo_id)
    if not m:
        abort(404)
    return m


def registrar(bp) -> None:
    @bp.route("/emails-automaticos/novo")
    def emails_modelo_novo():
        _t()._so_admin()
        return _editor(None)

    @bp.route("/emails-automaticos/<modelo_id>/editar")
    def emails_modelo_editar(modelo_id):
        _t()._so_admin()
        return _editor(_modelo_ou_404(modelo_id), modelo_id)

    @bp.route("/emails-automaticos/modelo/salvar", methods=["POST"])
    def emails_modelo_salvar():
        """Grava uma versão do modelo. O novo nasce desligado: a tela leva à página dele, com a prévia à mão."""
        T = _t()
        T._so_admin()
        from ...emails import modelos as MO
        modelo_id = request.form.get("modelo_id", "")
        dados = _form(request.form)
        recusa = T._form_valido()
        if recusa:
            return _editor(dados, modelo_id, recusa, 403)
        pessoas = T._pessoas()
        try:
            r = MO.salvar(current_app.config, dados, quem_hmac=T._quem_hmac(), modelo_id=modelo_id,
                          conhecidos=[p["email"] for p in pessoas], nomes=[p["nome"] for p in pessoas])
        except (MO.Recusado, EC.Recusada) as ex:
            return _editor(dados, modelo_id, str(ex), 409)
        except Exception as ex:  # noqa: BLE001
            current_app.logger.error("E-mails do Nexus: o modelo não gravou (%s: %s)", type(ex).__name__, ex)
            return _editor(dados, modelo_id, f"Não consegui gravar no banco ({type(ex).__name__}): nada mudou.", 500)
        return T._avisar("E-mail criado, desligado: confira a prévia e ligue na Regra quando estiver certo."
                         if r["novo"] else "E-mail salvo: a próxima rodada já sai assim.", r["id"])

    @bp.route("/emails-automaticos/<modelo_id>/excluir", methods=["POST"])
    def emails_modelo_excluir(modelo_id):
        T = _t()
        T._so_admin()
        from ...emails import modelos as MO
        recusa = T._form_valido()
        if recusa:
            return T._pagina(modelo_id, recusa, 403)
        try:
            MO.excluir(current_app.config, modelo_id, quem_hmac=T._quem_hmac())
        except MO.Recusado as ex:
            return T._pagina(modelo_id, str(ex), 409)
        return T._avisar("E-mail excluído: não sai mais. O que já saiu continua no registro.")

    @bp.route("/emails-automaticos/<modelo_id>/previa")
    def emails_modelo_previa(modelo_id):
        """A prévia: as mensagens que sairiam agora, uma por vez (?g=), com quem recebe pelo nome e o e-mail como chega."""
        T = _t()
        T._so_admin()
        from ...emails import modelos as MO
        m = _modelo_ou_404(modelo_id)
        agora = datetime.now(timezone.utc)
        try:
            res = MO.montar(current_app.config, m, agora, rodada="previa")
        except Exception as ex:  # noqa: BLE001 — a Visão fora
            current_app.logger.exception("E-mails do Nexus: a prévia de %s não montou", modelo_id)
            res = {"mensagens": [], "avisos": [f"a prévia não montou agora ({type(ex).__name__})"]}
        msgs = res["mensagens"]
        try:
            g = min(max(int(request.args.get("g") or 0), 0), max(len(msgs) - 1, 0))
        except ValueError:
            g = 0
        por_email = {p["email"]: p["nome"] for p in T._pessoas()}
        return render_template("emails_previa.html", m=m, modelo_id=modelo_id, msgs=msgs, g=g,
                               msg=msgs[g] if msgs else None, avisos=res["avisos"], por_email=por_email,
                               codigo=T._codigo_form(), meu_email=str(T._usuario().get("email") or ""))

    @bp.route("/emails-automaticos/<modelo_id>/previa-para-mim", methods=["POST"])
    def emails_modelo_previa_para_mim(modelo_id):
        """A mensagem da prévia que está na tela, só para um e-mail (o de quem entrou): como chega no Outlook."""
        T = _t()
        T._so_admin()
        from ...emails import envio, fila
        from ...emails import modelos as MO
        from ...emails.tipos import mensagem
        m = _modelo_ou_404(modelo_id)
        cfg = current_app.config
        recusa = T._form_valido()
        if recusa:
            return T._pagina(modelo_id, recusa, 403)
        if not (envio.envia_nesta_maquina(cfg) or cfg.get("NEXUS_EMAIL_SAIDA_PASTA")):
            return T._pagina(modelo_id, "Esta máquina não envia os e-mails do Nexus: a prévia não sai daqui.", 409)
        try:
            para = T._email_de_teste(request.form.get("para"), [p["email"] for p in T._pessoas()])
        except EC.Recusada as ex:
            return T._pagina(modelo_id, str(ex), 409)
        agora = datetime.now(timezone.utc)
        msgs = MO.montar(cfg, m, agora, rodada="previa")["mensagens"]
        try:
            g = min(max(int(request.form.get("g") or 0), 0), max(len(msgs) - 1, 0))
        except ValueError:
            g = 0
        if not msgs:
            return T._pagina(modelo_id, "A prévia não tem mensagem agora (ninguém com e-mail, ou nada a mandar).", 409)
        fila.enfileirar(cfg, mensagem(tipo="nx_teste", referencia=f"prévia de {modelo_id}",
                                      chave=f"previa|{modelo_id}|{agora.isoformat()}",
                                      para=[{"email": para, "papel": "quem pediu a prévia"}],
                                      assunto="[Prévia] " + msgs[g]["assunto"], html=msgs[g]["html"]), agora)
        return T._avisar("A prévia entrou na fila, só para você: sai em até 20 segundos.", modelo_id)

    @bp.route("/emails-automaticos/<modelo_id>/mandar-agora", methods=["POST"])
    def emails_modelo_mandar_agora(modelo_id):
        """Manda agora, para todos, fora da agenda (o modelo "só quando alguém manda" sai só por aqui). A regra vale: o
        desligado é registrado como desligado e não sai."""
        T = _t()
        T._so_admin()
        from ...emails import envio, fila
        from ...emails import modelos as MO
        m = _modelo_ou_404(modelo_id)
        cfg = current_app.config
        recusa = T._form_valido()
        if recusa:
            return T._pagina(modelo_id, recusa, 403)
        if not (envio.envia_nesta_maquina(cfg) or cfg.get("NEXUS_EMAIL_SAIDA_PASTA")):
            return T._pagina(modelo_id, "Esta máquina não envia os e-mails do Nexus: nada saiu daqui.", 409)
        agora = datetime.now(timezone.utc)
        res = MO.montar(cfg, m, agora, rodada="agora " + agora.strftime("%Y-%m-%dT%H:%M:%S"))
        n = 0
        for msg in res["mensagens"]:
            msg.pop("_quem", None)
            n += fila.enfileirar(cfg, msg, agora)
        return T._avisar(f"{n} e-mail(s) na fila: saem em até 20 segundos (a regra vale: desligado não sai)."
                         + (f" Ficou de fora: {'; '.join(res['avisos'])}." if res["avisos"] else ""), modelo_id)
