"""As telas das demandas entre setores (12/11/2026): o bloco no alto da Caixa de entrada, a Nova demanda, cada passo, o
anexo, as OS da usina para o formulário e os Temas do setor. A conta mora em `nexus/comando/demandas.py` e
`demandas_regras.py`; o desenho, em docs/superpowers/specs/2026-11-12-demandas-entre-setores-design.md.

As rotas ficam debaixo de `/t/comando/caixa-de-entrada/demandas/...`: herdam a permissão da Caixa de entrada, que é de
todos (`de_todos`); debaixo de `/t/comando/demandas/` o portão por setor não acharia a tela e barraria quem só tem a Caixa.
Fica num módulo à parte, importado no fim do `__init__` da torre (como as Ocorrências e a Visão do cliente do Campo).
"""
from datetime import datetime, timedelta, timezone

from flask import abort, current_app, jsonify, redirect, render_template, request, send_file, session
from werkzeug.exceptions import RequestEntityTooLarge

from ...comando import demandas as D
from ...comando import demandas_regras as R
from ...prefixo import na_raiz
from . import _AVISO, TORRE, _codigo, _form_venceu, _meu_hmac, bp

_BRT = timezone(timedelta(hours=-3))
CAIXA = "/t/comando/caixa-de-entrada"
ABAS = (("para", "Para mim"), ("pedi", "Que eu pedi"), ("setor", "Do meu setor"))


def _usuario() -> dict:
    u = session.get("usuario")
    return u if isinstance(u, dict) else {}


def _meu_setor() -> dict | None:
    """{"id", "nome"} do setor da pessoa do login. Pelas decisões de Base → Acessos → Pessoas e setores, e não pelo
    `acesso()`: esse só diz o setor com o portão por setor ligado, e a demanda vale com o portão ligado ou não."""
    if hasattr(request, "_dm_setor"):
        return request._dm_setor
    from ...auth import setor_telas as ST
    from ...dados.conexao import banco
    email = str(_usuario().get("email") or "").strip().lower()
    setor = None
    if email:
        try:
            setor = ST.acesso().get("setor") or ST.setor_da_pessoa(current_app.config, email, *banco())
        except Exception:        # noqa: BLE001 — sem saber o setor, a aba "Do meu setor" sai vazia
            current_app.logger.exception("demandas: o setor da pessoa não leu")
    request._dm_setor = setor
    return setor


def _hoje():
    return datetime.now(_BRT).date()


_DIAS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


def dia_txt(d) -> str:
    """'sex, 13/11': o prazo se lê pelo dia da semana (o mockup aprovado)."""
    return f"{_DIAS[d.weekday()]}, {d.strftime('%d/%m')}" if d else ""


def _pendente(d: dict) -> str:
    """A última linha da linha do tempo: o que falta acontecer, e até quando."""
    e, quem = d["estado"], d["de_nome"] or "quem pediu"
    sit = e["situacao"]
    if sit == "aguardando":
        return f"O prazo está parado até {quem} responder ao pedido de informação"
    if sit == "finalizada":
        ate = R.somar_dias_uteis(e["respondida_em"], R.CONCLUI_SOZINHA_DIAS) if e["respondida_em"] else None
        return f"Esperando o ok de {quem} para concluir" + (f"; sem resposta, conclui sozinha em {dia_txt(ate)}"
                                                           if ate else "")
    if sit == "concluida":
        return (f"Concluída sozinha: {R.CONCLUI_SOZINHA_DIAS} dias úteis sem o ok de quem pediu" if e["sozinha"]
                else "")
    if not e["prazo"]:
        return ""
    if e["vencida"]:
        return f"Venceu em {dia_txt(e['prazo'])}: quem recebeu e o setor dele foram avisados"
    return f"{'Novo prazo' if sit == 'devolvida' else 'Resposta até'} {dia_txt(e['prazo'])}"


def contexto() -> dict:
    """O que o bloco das demandas da Caixa de entrada mostra: as três abas (todas na página; o JS troca sem recarregar),
    as contas de cada filtro, o formulário da Nova demanda e o que falta para gravar."""
    from ...casca import sugestoes as SUG
    falta = D.faltam_chaves()
    meu, setor = _meu_hmac(), _meu_setor()
    admin = bool(session.get("admin"))
    hoje = _hoje()
    out = {"abas": ABAS, "filtros": D.FILTROS, "aba": request.args.get("dem") or "para",
           "sel": (request.args.get("d") or "") if D.ID_DEMANDA.fullmatch(request.args.get("d") or "") else "", "falta": falta, "tem_login": bool(meu), "erro": "", "meu": meu,
           "listas": {}, "contas": {}, "itens": {}, "temas": [], "usinas": [],
           "novo_id": D.novo_id("d"), "novo_evento": lambda: D.novo_id("e"), "setor_id": (setor or {}).get("id"),
           "setor_nome": (setor or {}).get("nome") or "", "admin": admin, "dia_txt": dia_txt,
           "sozinha_dias": R.CONCLUI_SOZINHA_DIAS,
           "anexo": {"aceitos": SUG.aceitos(), "max_mb": SUG.MAX_MB_ARQUIVO, "max_arquivos": SUG.MAX_ARQUIVOS,
                     "max_total": SUG.MAX_MB_TOTAL},
           "limites": {"titulo": D.TITULO_MAX, "texto": D.TEXTO_MAX, "passo": D.PASSO_MAX}}
    if out["aba"] not in dict(ABAS):
        out["aba"] = "para"
    if falta:
        return out
    try:
        lst = D.lista(hoje)
        out["erro"] = D.ler()["erro"]
    except Exception as ex:      # noqa: BLE001 — banco fora: a Caixa abre com o aviso
        current_app.logger.exception("demandas: a lista não abriu")
        return dict(out, erro=type(ex).__name__)
    setor_id = out["setor_id"]
    for aba, _rot in ABAS:
        # o administrador pela senha (sem pessoa) vê tudo no "Do meu setor": é por onde ele acompanha as demandas
        itens = lst if (aba == "setor" and admin and not meu) else D.da_aba(lst, aba, meu, setor_id)
        out["listas"][aba] = [d["demanda_id"] for d in itens]
        out["contas"][aba] = D.contas(itens)
        for d in itens:
            if d["demanda_id"] not in out["itens"]:
                out["itens"][d["demanda_id"]] = dict(
                    d, filtros=D.filtros_da(d), pendente=_pendente(d),
                    eu_recebo=bool(meu) and d["para_hmac"] == meu, eu_pedi=bool(meu) and d["de_hmac"] == meu)
    no_setor = [out["itens"][i] for i in out["listas"]["setor"]]
    out["filtro_pessoas"] = sorted({(d["para_hmac"], d["para_nome"]) for d in no_setor if d["para_nome"]},
                                   key=lambda p: p[1].lower())
    out["filtro_temas"] = sorted({(d["tema_id"], d["tema_nome"]) for d in no_setor if d["tema_nome"]},
                                 key=lambda t: t[1].lower())
    out["temas"] = [dict(t, ate=dia_txt(R.somar_dias_uteis(hoje, t["prazo_dias_uteis"]))) for t in D.temas()]
    try:
        from ...campo import visao
        b = visao._Base()
        out["usinas"] = sorted(((uid, f.get("nome") or "") for uid, f in b.por_id.items() if uid in b.mobilizadas),
                               key=lambda u: u[1].lower())
    except Exception:            # noqa: BLE001
        out["usinas"] = []
    return out


def _volta(aba: str = "", did: str = "") -> str:
    q = []
    if aba:
        q.append(f"dem={aba}")
    if did:
        q.append(f"d={did}")
    return na_raiz(CAIXA) + ("?" + "&".join(q) if q else "") + "#demandas"


@bp.route("/caixa-de-entrada/demandas/nova", methods=["POST"])
def demanda_nova():
    """`POST` da Nova demanda (multipart, com os anexos). O tamanho é conferido antes de ler o corpo, como as Sugestões."""
    from ...casca import sugestoes as SUG
    destino = _volta("pedi")
    # o tamanho ANTES de ler o corpo (o `_form_venceu` lê o formulário): o pedido maior que o teto não chega a ocupar a
    # memória nem o disco, e o sem tamanho declarado para no teto (a regra das Sugestões; revisão de 12/11/2026)
    teto = SUG.MAX_MB_TOTAL * SUG.MB + SUG.MB
    grande = ("erro", f"Os anexos passam de {SUG.MAX_MB_TOTAL} MB juntos. Nada foi enviado.")
    if (request.content_length or 0) > teto:
        session[_AVISO] = grande
        return redirect(destino, code=303)
    request.max_content_length = teto
    try:
        venceu = _form_venceu(destino)
        if venceu:
            return venceu
        form = {k: request.form.get(k, "") for k in ("para_hmac", "para_setor_id", "tema_id", "titulo", "descricao",
                                                     "os", "novo_id")}
        form["usinas"] = request.form.getlist("usinas")
        arquivos = [(f.filename, f.stream) for f in request.files.getlist("anexos")]
    except RequestEntityTooLarge:
        session[_AVISO] = grande
        return redirect(destino, code=303)
    try:
        d = D.abrir(form, arquivos, _usuario())
        session[_AVISO] = ("ok", "Demanda enviada. Ela aparece em \"Que eu pedi\", e quem recebeu é avisado no sininho.")
        return redirect(_volta("pedi", d.get("demanda_id") or ""), code=303)
    except D.Recusada as ex:
        session[_AVISO] = ("erro", f"{ex}. Nada foi enviado{'; anexe os arquivos de novo' if arquivos else ''}.")
    except Exception as ex:      # noqa: BLE001 — banco fora, rede: a pessoa sabe que não foi
        current_app.logger.exception("demanda não gravada")
        session[_AVISO] = ("erro", f"Não consegui gravar agora ({type(ex).__name__}). Nada foi enviado.")
    return redirect(destino, code=303)


@bp.route("/caixa-de-entrada/demandas/<demanda_id>/passo", methods=["POST"])
def demanda_passo(demanda_id):
    """Um passo da demanda: o botão diz qual (`acao`); o texto vai junto quando o passo pede."""
    aba = request.form.get("aba") or "para"
    destino = _volta(aba, demanda_id)
    venceu = _form_venceu(destino)
    if venceu:
        return venceu
    acao = request.form.get("acao") or ""
    try:
        D.registrar(demanda_id, acao, request.form.get("texto") or "", _usuario(), request.form.get("novo_id"))
        session[_AVISO] = ("ok", f"Feito: {D.ROTULO_PASSO.get(acao, acao)}.")
    except D.Recusada as ex:
        session[_AVISO] = ("erro", f"{ex}. Nada foi gravado.")
    except Exception as ex:      # noqa: BLE001
        current_app.logger.exception("passo da demanda não gravado")
        session[_AVISO] = ("erro", f"Não consegui gravar agora ({type(ex).__name__}). Nada foi gravado.")
    return redirect(destino, code=303)


def _pode_ver(d: dict) -> bool:
    if session.get("admin"):
        return True
    meu = _meu_hmac()
    setor = (_meu_setor() or {}).get("id")
    return bool(meu) and (d["de_hmac"] == meu or d["para_hmac"] == meu) or (setor is not None
                                                                            and d["para_setor_id"] == setor)


@bp.route("/caixa-de-entrada/demandas/<demanda_id>/anexo/<int:n>")
def demanda_anexo(demanda_id, n):
    """O anexo, só para quem pediu, quem recebeu, o setor de quem recebeu e o administrador (o resto, 404)."""
    from ...casca import sugestoes as SUG
    d = next((x for x in D.lista(_hoje()) if x["demanda_id"] == demanda_id), None)
    if not d or not _pode_ver(d):
        abort(404)
    achado = D.arquivo(demanda_id, n)
    if not achado:
        abort(404)
    caminho, a = achado
    imagem = SUG.eh_imagem(caminho.name)
    return send_file(caminho, mimetype=SUG.tipo_servido(caminho.name), as_attachment=not imagem,
                     download_name=a.get("nome") or caminho.name)


@bp.route("/caixa-de-entrada/demandas/pessoas")
def demanda_pessoas():
    """Quem pode receber (as pessoas com setor, menos quem pede): [{hmac, nome, setor_id, setor_nome}] para a Nova demanda.
    Vem ao abrir o formulário, e não com a Caixa: os nomes são do pessoal do Fracttal (cópia de 1 hora)."""
    meu = _meu_hmac()
    try:
        ps = [p for p in D.pessoas_com_setor() if p["hmac"] != meu]
    except Exception:            # noqa: BLE001 — o formulário diz que não leu
        current_app.logger.exception("demandas: a lista de pessoas não abriu")
        return jsonify(ok=False, pessoas=[])
    return jsonify(ok=True, pessoas=ps)


@bp.route("/caixa-de-entrada/demandas/os")
def demanda_os():
    """As OS das usinas escolhidas no formulário (`?usinas=1,2`): [{os, rotulo}] para o campo da OS."""
    ids = [x for x in (request.args.get("usinas") or "").split(",") if x.strip().isdigit()]
    try:
        lst = D.os_das_usinas(ids)
    except Exception:            # noqa: BLE001 — sem o retrato, o campo fica vazio e diz
        return jsonify(ok=False, os=[])
    return jsonify(ok=True, os=[{"os": o["os"], "rotulo": f"OS {o['os']} · {o['tipo'] or 'OS'}"} for o in lst])


# ── os temas do setor ────────────────────────────────────────────────────────────────────────────────────────────────
def _setor_da_tela():
    """(setor_id, setor_nome, setores) da tela: o setor da pessoa; o administrador escolhe qualquer um (`?setor=`)."""
    from ...auth import setor_telas as ST
    from ...cadastro import setores as S
    from ...dados.conexao import banco
    st = ST._setores_no_clique(*banco())
    ativos = [(s["setor_id"], s["nome"]) for s in S.ativos(st.get("setores") or [])]
    meu = _meu_setor()
    if session.get("admin"):
        pedido = request.values.get("setor", type=int)
        sid = pedido if pedido in dict(ativos) else ((meu or {}).get("id") or (ativos[0][0] if ativos else None))
    else:
        sid = (meu or {}).get("id")
    return sid, dict(ativos).get(sid, ""), ativos


@bp.route("/temas-do-setor")
def temas_do_setor():
    """Comando › Temas do setor: o que os outros setores podem pedir ao seu, e o prazo de cada tema em dias úteis."""
    falta = D.faltam_chaves()
    sid, nome, ativos = (None, "", []) if falta else _setor_da_tela()
    temas = D.temas(sid, so_ativos=False) if sid else []
    return render_template("comando/temas_setor.html", torre=TORRE, tela=TORRE.tela("temas-do-setor"), temas=temas,
                           setor_id=sid, setor_nome=nome, setores=ativos, admin=bool(session.get("admin")),
                           falta=falta, codigo=_codigo(), tem_login=bool(_meu_hmac()), aviso=session.pop(_AVISO, None),
                           prazo_min=D.PRAZO_MIN, prazo_max=D.PRAZO_MAX, novo_tema=D.novo_id("m"))


@bp.route("/temas-do-setor/salvar", methods=["POST"])
def temas_do_setor_salvar():
    sid = request.form.get("setor_id", type=int)
    destino = na_raiz("/t/comando/temas-do-setor") + (f"?setor={sid}" if session.get("admin") and sid else "")
    venceu = _form_venceu(destino)
    if venceu:
        return venceu
    meu = (_meu_setor() or {}).get("id")
    if not session.get("admin") and sid != meu:
        abort(403)
    try:
        D.salvar_tema(sid, request.form.get("nome"), request.form.get("prazo"), _usuario(),
                      tema_id=request.form.get("tema_id") or None, ativo=request.form.get("ativo") != "nao",
                      novo=request.form.get("novo_id"))
        session[_AVISO] = ("ok", "Tema salvo.")
    except D.Recusada as ex:
        session[_AVISO] = ("erro", f"{ex}. Nada foi gravado.")
    except Exception as ex:      # noqa: BLE001
        current_app.logger.exception("tema não gravado")
        session[_AVISO] = ("erro", f"Não consegui gravar agora ({type(ex).__name__}). Nada foi gravado.")
    return redirect(destino, code=303)
