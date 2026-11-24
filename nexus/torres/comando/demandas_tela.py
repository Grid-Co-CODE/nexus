"""As telas das demandas entre setores (12/11/2026): o bloco no alto da Caixa de entrada, a Nova demanda, cada passo, o
anexo, as OS da usina para o formulário e os Temas do setor. A conta mora em `nexus/comando/demandas.py` e
`demandas_regras.py`; o desenho, em docs/superpowers/specs/2026-11-12-demandas-entre-setores-design.md.

As rotas ficam debaixo de `/t/comando/caixa-de-entrada/demandas/...`: herdam a permissão da Caixa de entrada, que é de
todos (`de_todos`); debaixo de `/t/comando/demandas/` o portão por setor não acharia a tela e barraria quem só tem a Caixa.
Fica num módulo à parte, importado no fim do `__init__` da torre (como as Ocorrências e a Visão do cliente do Campo).
"""
import re
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
    # a aba dos Temas do setor (13/11/2026): os temas do setor de quem abre (o administrador escolhe o setor, `?setor=`)
    out["ts"] = temas_contexto()
    if out["aba"] not in dict(ABAS) and out["aba"] != "temas":
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
    # vinda da janela da conversa da usina, no prontuário (13/11/2026): volta à janela, e não à Caixa de entrada
    jan = request.args.get("usina_jan", "")
    jan = jan if jan.isdigit() else ""
    # vinda do chamado de Garantias (24/11/2026): volta ao Raio X do chamado, com o aviso na própria página
    ch = request.args.get("chamado", "")
    ch = ch if ch.isdigit() else ""
    destino = (na_raiz(f"/t/comando/conversa/usina/{jan}/janela?aba=pedir") if jan else
               _no_chamado(ch, "erro", "O formulário venceu: abra o chamado de novo. Nada foi enviado.") if ch else
               _volta("pedi"))
    # o tamanho ANTES de ler o corpo (o `_form_venceu` lê o formulário): o pedido maior que o teto não chega a ocupar a
    # memória nem o disco, e o sem tamanho declarado para no teto (a regra das Sugestões; revisão de 12/11/2026)
    teto = SUG.MAX_MB_TOTAL * SUG.MB + SUG.MB
    grande = ("erro", f"Os anexos passam de {SUG.MAX_MB_TOTAL} MB juntos. Nada foi enviado.")
    if (request.content_length or 0) > teto:
        session[_AVISO] = grande
        return redirect(_no_chamado(ch, *grande) if ch else destino, code=303)
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
        return redirect(_no_chamado(ch, *grande) if ch else destino, code=303)
    try:
        d = D.abrir(form, arquivos, _usuario())
        if ch:
            return redirect(_no_chamado(ch, "ok", "Demanda enviada: quem recebeu é avisado no sininho e a vê na Caixa de "
                                                  "entrada; a resposta volta para este chamado."), code=303)
        if jan:
            session[_AVISO] = ("ok", "Demanda enviada. Quem recebeu é avisado no sininho; ela está aqui e em \"Que eu "
                                     "pedi\", na Caixa de entrada.")
            return redirect(na_raiz(f"/t/comando/conversa/usina/{jan}/janela?aba=demandas"), code=303)
        session[_AVISO] = ("ok", "Demanda enviada. Ela aparece em \"Que eu pedi\", e quem recebeu é avisado no sininho.")
        return redirect(_volta("pedi", d.get("demanda_id") or ""), code=303)
    except D.Recusada as ex:
        if ch:
            return redirect(_no_chamado(ch, "erro", f"{ex}. Nada foi enviado"
                                                    f"{'; anexe os arquivos de novo' if arquivos else ''}."), code=303)
        session[_AVISO] = ("erro", f"{ex}. Nada foi enviado{'; anexe os arquivos de novo' if arquivos else ''}.")
    except Exception as ex:      # noqa: BLE001 — banco fora, rede: a pessoa sabe que não foi
        current_app.logger.exception("demanda não gravada")
        if ch:
            return redirect(_no_chamado(ch, "erro", f"Não consegui gravar agora ({type(ex).__name__}). Nada foi "
                                                    "enviado."), code=303)
        session[_AVISO] = ("erro", f"Não consegui gravar agora ({type(ex).__name__}). Nada foi enviado.")
    return redirect(destino, code=303)


def _no_chamado(folio: str, tipo: str, texto: str, did: str = "") -> str:
    """O Raio X do chamado de Garantias, com o aviso na página (o `?ok=`/`?erro=` que ele mostra) e no bloco das demandas;
    com a demanda (`did`), ela volta aberta."""
    from urllib.parse import urlencode
    q = {"de": "garantias", tipo: texto}
    if did:
        q["dm"] = did
    return na_raiz(f"/t/engenharia/equipe/os/{folio}") + "?" + urlencode(q) + (f"#dm-{did}" if did else "#demandas")


# ── a demanda que sai do chamado de Garantias (24/11/2026) ──────────────────────────────────────────────────────────
# Pedido da equipe de chamados ("um chatzinho com os supervisores" dentro do chamado, no lugar do Teams, onde cinco
# chamados se misturavam no mesmo canal) e o desenho que o Levi aprovou no mockup: no lugar do chat solto, a Nova demanda
# da Caixa de entrada dentro do chamado. "Quando a pessoa escolhe supervisor de campo, já puxa automaticamente o
# supervisor de campo daquela usina"; a usina e a OS vão vinculadas sozinhas, do chamado; o tema "Acompanhamento de
# chamado", de 3 dias úteis, já vem escolhido. A demanda é a de sempre (o mesmo livro, os mesmos passos, a mesma Caixa).
_RESERVA = re.compile(r"(Supervisor|Respons[aá]vel) \d+")    # o nome de reserva do cadastro, sem a chave


def _supervisor_da_usina(b, uid) -> str:
    """O nome de quem a Nova demanda do chamado já traz em "Para quem" (a tela acha a pessoa na Supervisão Campo pelo
    nome; sem achar, fica em branco). Primeiro o Supervisor de Campo da região da usina; sem ele, o Responsável O&M da
    usina (os supervisores de antes). Medido em 24/11/2026: as 8 regiões de campo do cadastro estão com a vaga de
    supervisor aberta, e só pela região nenhum chamado trazia ninguém; pelo responsável, 74 das 144 usinas trazem uma
    pessoa da Supervisão Campo. Nome de reserva do cadastro ("Supervisor 92", sem a chave) não vale."""
    from ...campo import visao
    r = b.info_regiao(b.regiao_da_usina(uid))
    for nome in ((r["supervisor"] if r.get("supervisor_id") else ""), b.responsavel_da_usina(uid)):
        nome = (nome or "").strip()
        if nome and nome not in (visao.VAGA, visao.SEM_RESPONSAVEL) and not _RESERVA.fullmatch(nome):
            return nome
    return ""


def contexto_do_chamado(folio: int) -> dict:
    """O bloco "Demandas do chamado" do Raio X e a Nova demanda dele: os setores e os temas (para as listas digitáveis),
    a usina e a OS do chamado, o supervisor de campo da usina (o nome: a tela acha a pessoa na lista de quem tem setor) e
    as demandas que citam a OS."""
    from ...cadastro import setor_ids as SID
    from ...casca import sugestoes as SUG
    from ...comando import temas_padrao as TP
    falta = D.faltam_chaves()
    out = {"falta": falta, "erro": "", "tem_login": bool(_meu_hmac()), "codigo": _codigo(), "novo_id": D.novo_id("d"),
           "folio": int(folio), "usina": None, "supervisor": "", "setor_sugerido": str(SID.SUPERVISAO_CAMPO),
           "tema_padrao": "", "setores": [], "temas": [], "demandas": [], "abertas": 0, "proximo": "",
           "acao": na_raiz(f"/t/comando/caixa-de-entrada/demandas/nova?chamado={int(folio)}"),
           "pessoas_url": na_raiz("/t/comando/caixa-de-entrada/demandas/pessoas"),
           "anexo": {"aceitos": SUG.aceitos(), "max_mb": SUG.MAX_MB_ARQUIVO, "max_arquivos": SUG.MAX_ARQUIVOS,
                     "max_total": SUG.MAX_MB_TOTAL},
           "limites": {"titulo": D.TITULO_MAX, "texto": D.TEXTO_MAX}}
    if falta:
        return out
    hoje = _hoje()
    try:
        lido = D.ler()
        lst = D.lista(hoje, lido)
        temas = D.temas()
    except Exception as ex:      # noqa: BLE001 — o banco fora: o bloco diz, o chamado abre igual
        current_app.logger.exception("demandas do chamado: a lista não abriu")
        return dict(out, erro=type(ex).__name__)
    meu, aberta = _meu_hmac(), request.args.get("dm") or ""
    doc = [dict(d, pendente=_pendente(d), caixa=na_raiz(CAIXA) + f"?d={d['demanda_id']}#demandas",
                eu_recebo=bool(meu) and d["para_hmac"] == meu, eu_pedi=bool(meu) and d["de_hmac"] == meu,
                aberta_agora=d["demanda_id"] == aberta,
                passo_url=na_raiz(f"{CAIXA}/demandas/{d['demanda_id']}/passo?chamado={int(folio)}"))
           for d in lst if int(folio) in (d.get("oss") or [])]
    abertas = [d for d in doc if d["estado"]["aberta"]]
    prox = min((d["estado"]["prazo"] for d in abertas if d["estado"]["prazo"]), default=None)
    # os setores que recebem (os que têm tema) e as áreas deles ("Chamados", dentro da Performance)
    try:
        from ...auth import setor_telas as ST
        from ...dados.conexao import banco
        nome_setor = {s["setor_id"]: s["nome"] for s in (ST._setores_no_clique(*banco()).get("setores") or [])}
    except Exception:            # noqa: BLE001 — sem os nomes, os setores saem pelo número
        nome_setor = {}
    setores = {}
    for t in temas:
        sid = t["setor_id"]
        valor = f"{sid}:{t['area']}" if t.get("area") else str(sid)
        setores.setdefault(valor, t["area"] or nome_setor.get(sid) or f"Setor {sid}")
    padrao = TP.codigo(SID.SUPERVISAO_CAMPO, *TP.TEMA_DO_CHAMADO)
    out.update(demandas=doc, abertas=len(abertas), proximo=dia_txt(prox) if prox else "",
               novo_evento=lambda: D.novo_id("e"), sozinha_dias=R.CONCLUI_SOZINHA_DIAS, passo_max=D.PASSO_MAX,
               setores=sorted(setores.items(), key=lambda kv: kv[1].lower()),
               temas=[{"tema_id": t["tema_id"], "setor": (f"{t['setor_id']}:{t['area']}" if t.get("area")
                                                          else str(t["setor_id"])),
                       "nome": f"{t['nome']} ({t['prazo_dias_uteis']} {'dia útil' if t['prazo_dias_uteis'] == 1 else 'dias úteis'})"}
                      for t in temas],
               tema_padrao=padrao if any(t["tema_id"] == padrao for t in temas) else "")
    # a usina do chamado (o retrato das OS abertas) e o supervisor de campo dela (a região de campo da usina)
    try:
        from ...campo import visao
        uid = D.usina_da_os(folio)
        if uid:
            b = visao._Base()
            out["usina"] = (uid, (b.por_id.get(uid) or {}).get("nome") or f"usina {uid}")
            out["supervisor"] = _supervisor_da_usina(b, uid)
    except Exception:            # noqa: BLE001 — sem a usina, a demanda vai sem ela e sem a OS
        current_app.logger.exception("demandas do chamado: a usina da OS %s não saiu", folio)
    return out


@bp.route("/caixa-de-entrada/demandas/<demanda_id>/passo", methods=["POST"])
def demanda_passo(demanda_id):
    """Um passo da demanda: o botão diz qual (`acao`); o texto vai junto quando o passo pede."""
    aba = request.form.get("aba") or "para"
    # vindo do chamado de Garantias (24/11/2026): volta ao Raio X do chamado, com a demanda aberta e o aviso na página
    ch = request.args.get("chamado", "")
    ch = ch if ch.isdigit() else ""
    did = demanda_id if D.ID_DEMANDA.fullmatch(demanda_id or "") else ""
    destino = (_no_chamado(ch, "erro", "O formulário venceu: abra o chamado de novo. Nada foi gravado.", did) if ch
               else _volta(aba, demanda_id))
    venceu = _form_venceu(destino)
    if venceu:
        return venceu
    acao = request.form.get("acao") or ""
    try:
        os_n = request.form.get("os", type=int)
        D.registrar(demanda_id, acao, request.form.get("texto") or "", _usuario(), request.form.get("novo_id"), os=os_n)
        feito = f"Feito: {D.ROTULO_PASSO.get(acao, acao)}" + (f", com a OS {os_n} atrelada." if os_n else ".")
        if ch:
            return redirect(_no_chamado(ch, "ok", feito, did), code=303)
        session[_AVISO] = ("ok", feito)
    except D.Recusada as ex:
        if ch:
            return redirect(_no_chamado(ch, "erro", f"{ex}. Nada foi gravado.", did), code=303)
        session[_AVISO] = ("erro", f"{ex}. Nada foi gravado.")
    except Exception as ex:      # noqa: BLE001
        current_app.logger.exception("passo da demanda não gravado")
        if ch:
            return redirect(_no_chamado(ch, "erro", f"Não consegui gravar agora ({type(ex).__name__}). Nada foi gravado.",
                                        did), code=303)
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
    from ...comando import areas as AR
    meu = _meu_hmac()
    try:
        ps = [p for p in D.pessoas_com_setor() if p["hmac"] != meu]
    except Exception:            # noqa: BLE001 — o formulário diz que não leu
        current_app.logger.exception("demandas: a lista de pessoas não abriu")
        return jsonify(ok=False, pessoas=[])
    # as áreas de cada pessoa (15/11/2026: na área Chamados, a Nova demanda mostra só quem o setor marcou)
    mapa = AR.ler(current_app.config)
    for p in ps:
        p["areas"] = AR.areas_da_pessoa(mapa, p["setor_id"], p["hmac"])
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


def temas_contexto() -> dict:
    """Os temas do setor para a aba deles na Caixa de entrada (comando/_temas_setor.html): o setor de quem abre, e o que o
    administrador escolheu (`?setor=`). O cadastro que não abre vira o aviso da aba, e a Caixa segue."""
    falta = D.faltam_chaves()
    out = {"temas": [], "setor_id": None, "setor_nome": "", "setores": [], "admin": bool(session.get("admin")),
           "falta": falta, "erro": "", "prazo_min": D.PRAZO_MIN, "prazo_max": D.PRAZO_MAX, "novo_tema": D.novo_id("m"),
           "em_uso": 0}
    if falta:
        return out
    try:
        sid, nome, ativos = _setor_da_tela()
        temas = D.temas(sid, so_ativos=False) if sid else []
    except Exception as ex:      # noqa: BLE001 — o banco fora: a aba diz, a Caixa segue
        current_app.logger.exception("demandas: os temas do setor não abriram")
        return dict(out, erro=type(ex).__name__)
    # os temas padrão que faltam em todos os setores (só o administrador cria; 14/11/2026)
    faltam = []
    if session.get("admin"):
        from ...comando import temas_padrao as TP
        try:
            faltam = TP.para_criar([{"setor_id": s, "nome": n} for s, n in ativos], D.temas(so_ativos=False))
        except Exception:        # noqa: BLE001 — sem a conta, sem o botão
            current_app.logger.exception("demandas: a conta dos temas padrão falhou")
    from ...comando import areas as AR
    from ...comando import temas_padrao as TP
    # quem do setor recebe em cada área (15/11/2026, Levi: "quando escolher o setor chamados, vai ficar filtrado só" as
    # pessoas da garantia): as pessoas do setor, marcadas as da área
    area_pessoas = []
    if TP.areas_do_setor(nome):
        try:
            do_setor = [p for p in D.pessoas_com_setor() if p["setor_id"] == sid]
        except Exception:        # noqa: BLE001 — sem as pessoas, a área fica sem a lista
            current_app.logger.exception("demandas: as pessoas do setor não abriram")
            do_setor = []
        for a in TP.areas_do_setor(nome):
            marcadas = AR.pessoas(current_app.config, sid, a)
            area_pessoas.append({"area": a, "pessoas": [dict(p, marcada=p["hmac"] in marcadas) for p in do_setor],
                                 "n": len(marcadas)})
    return dict(out, temas=temas, setor_id=sid, setor_nome=nome, setores=ativos,
                em_uso=sum(1 for t in temas if t.get("ativo")), padrao_faltam=len(faltam),
                areas=TP.areas_do_setor(nome), area_pessoas=area_pessoas)


def _temas_na_caixa(sid=None) -> str:
    """A aba dos Temas do setor na Caixa de entrada (o administrador volta ao setor que escolheu)."""
    return na_raiz(CAIXA) + "?dem=temas" + (f"&setor={sid}" if session.get("admin") and sid else "") + "#demandas"


@bp.route("/temas-do-setor")
def temas_do_setor():
    """Comando › Temas do setor: desde 13/11/2026 é uma aba das Demandas entre setores, na Caixa de entrada (Levi: "eu
    gostaria que temas por setor fosse mais uma aba do demanda entre setores [...] Deixa dentro da caixa de entrada").
    O endereço de antes leva à aba."""
    return redirect(_temas_na_caixa(request.args.get("setor", type=int)))


@bp.route("/temas-do-setor/padrao", methods=["POST"])
def temas_do_setor_padrao():
    """Cria os temas padrão que faltam em todos os setores (só o administrador; 14/11/2026, Levi: "crie temas padrões
    para setores"). Uma gravação só; rodar de novo não duplica (`demandas.criar_temas_padrao`)."""
    sid = request.form.get("setor_id", type=int)
    destino = _temas_na_caixa(sid)
    venceu = _form_venceu(destino)
    if venceu:
        return venceu
    if not session.get("admin"):
        abort(403)
    try:
        _sid, _nome, ativos = _setor_da_tela()
        feitos = D.criar_temas_padrao([{"setor_id": s, "nome": n} for s, n in ativos], _usuario())
        session[_AVISO] = ("ok", f"{len(feitos)} {'tema padrão criado' if len(feitos) == 1 else 'temas padrão criados'}."
                           if feitos else "Os temas padrão já estavam criados.")
    except D.Recusada as ex:
        session[_AVISO] = ("erro", f"{ex}. Nada foi gravado.")
    except Exception as ex:      # noqa: BLE001
        current_app.logger.exception("temas padrão não gravados")
        session[_AVISO] = ("erro", f"Não consegui gravar agora ({type(ex).__name__}). Nada foi gravado.")
    return redirect(destino, code=303)


@bp.route("/temas-do-setor/area", methods=["POST"])
def temas_do_setor_area():
    """Quem do setor recebe na área (15/11/2026: Chamados, dentro da Performance). O próprio setor ou o administrador,
    como nos temas."""
    from ...comando import areas as AR
    from ...comando import temas_padrao as TP
    sid = request.form.get("setor_id", type=int)
    destino = _temas_na_caixa(sid)
    venceu = _form_venceu(destino)
    if venceu:
        return venceu
    meu = (_meu_setor() or {}).get("id")
    if not session.get("admin") and sid != meu:
        abort(403)
    area = request.form.get("area") or ""
    _s, nome, _a = _setor_da_tela()
    if area not in TP.areas_do_setor(dict(_a).get(sid, nome)):
        session[_AVISO] = ("erro", "Área desconhecida neste setor. Nada foi gravado.")
        return redirect(destino, code=303)
    try:
        do_setor = {p["hmac"] for p in D.pessoas_com_setor() if p["setor_id"] == sid}
        lista = AR.gravar(current_app.config, sid, area, [h for h in request.form.getlist("pessoa") if h in do_setor],
                          _meu_hmac() or "administrador")
        session[_AVISO] = ("ok", f"{area}: {len(lista)} {'pessoa recebe' if len(lista) == 1 else 'pessoas recebem'}"
                           if lista else f"{area}: ninguém marcado, recebe o setor inteiro.")
    except Exception as ex:      # noqa: BLE001
        current_app.logger.exception("área das demandas não gravada")
        session[_AVISO] = ("erro", f"Não consegui gravar agora ({type(ex).__name__}). Nada foi gravado.")
    return redirect(destino, code=303)


@bp.route("/temas-do-setor/salvar", methods=["POST"])
def temas_do_setor_salvar():
    sid = request.form.get("setor_id", type=int)
    destino = _temas_na_caixa(sid)
    venceu = _form_venceu(destino)
    if venceu:
        return venceu
    meu = (_meu_setor() or {}).get("id")
    if not session.get("admin") and sid != meu:
        abort(403)
    try:
        # o campo é `tema` desde 12/11/2026 (o `nome` chamava o preenchimento automático do navegador); o `nome` segue
        # aceito para a página que ficou aberta de antes
        D.salvar_tema(sid, request.form.get("tema") or request.form.get("nome"), request.form.get("prazo"), _usuario(),
                      tema_id=request.form.get("tema_id") or None, ativo=request.form.get("ativo") != "nao",
                      novo=request.form.get("novo_id"),
                      area=request.form.get("area") if "area" in request.form else None)
        session[_AVISO] = ("ok", "Tema salvo.")
    except D.Recusada as ex:
        session[_AVISO] = ("erro", f"{ex}. Nada foi gravado.")
    except Exception as ex:      # noqa: BLE001
        current_app.logger.exception("tema não gravado")
        session[_AVISO] = ("erro", f"Não consegui gravar agora ({type(ex).__name__}). Nada foi gravado.")
    return redirect(destino, code=303)
