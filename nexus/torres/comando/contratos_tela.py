"""Comando › Contratos (18/11/2026): a visão do contrato, editável e com histórico.

Era a "Prévia: visão do contrato" (12/11/2026), um mockup numa moldura que passou a mostrar a planilha de controle de
obrigações (16/11/2026) e as fichas lidas dos PDFs dos contratos (18/11/2026), ambas subidas por campos de importação. Levi,
18/11/2026: "Tire essas opções de subir arquivos [...] Eu quero que essas informações sejam editáveis [...] Só gestores de
contrato ou administradores podem editar, e tudo com histórico" e "deixar muita informação em cima [...] rouba metade do
espaço da tela [...] Arrume isso". Virou página do Nexus (sem moldura, sem o cabeçalho dobrado), com o nome Contratos; o
que foi importado é a carga inicial, e daí em diante tudo muda aqui (`nexus/contratos/edicao.py`).

Leitura só para quem está logado e não é cliente; edição só do gestor do contrato ou do administrador (a regra mora em
`edicao.pode_editar`, e a página só mostra o lápis para quem pode). O endereço antigo leva ao novo.
"""
import json
import logging

from flask import abort, jsonify, redirect, render_template, request, send_file, session

from ...auth.origem import de_outro_site as _de_outro_site
from ...contratos import edicao as E
from ...prefixo import na_raiz
from . import TORRE, bp

_log = logging.getLogger(__name__)
CONTRATOS = "/t/comando/contratos"


def _pasta_contratos():
    from flask import current_app

    from ...cadastro.ligacoes import pasta_dados
    return pasta_dados(current_app.config) / "contratos"


def _json_da_pasta(nome: str) -> dict | None:
    """Um dos dois arquivos da carga inicial (a planilha de 16/11 e as fichas de 18/11), ou None."""
    try:
        p = _pasta_contratos() / nome
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except Exception:            # noqa: BLE001 — arquivo estragado: a tela segue sem ele, e o log diz
        _log.exception("Contratos: não li %s", nome)
        return None


def _base() -> dict:
    from ...contratos import controle as K
    from ...contratos import fichas as F
    return E.carga(_json_da_pasta(K.ARQUIVO), _json_da_pasta(F.ARQUIVO))


def _so_interno():
    from ...auth import setor_telas as ST
    if session.get("via") == "cliente" or ST.em_modo_cliente():
        abort(403)


def _usuario() -> dict:
    u = session.get("usuario")
    return u if isinstance(u, dict) else {}


def _meu_hmac() -> str | None:
    from flask import current_app

    from ...cadastro.ligacao_campo import codigo_da_pessoa
    email = str(_usuario().get("email") or "").strip().lower()
    return codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), email) if email else None


def _pessoas() -> list[dict]:
    """[{hmac, nome}] das pessoas com setor (a lista das Demandas): é dela que sai o gestor de cada contrato. Fora do ar,
    vazio: ninguém fica gestor pelo nome, e só o administrador edita até voltar."""
    try:
        from ...comando import demandas as D
        return [{"hmac": p["hmac"], "nome": p["nome"]} for p in D.pessoas_com_setor()]
    except Exception:            # noqa: BLE001
        _log.warning("Contratos: a lista de pessoas não veio; só o administrador edita agora")
        return []


def _radar() -> list[dict] | None:
    """As linhas de `zeladoria_contratual` do Radar da Zeladoria (o que o contrato de cada cliente pede de zeladoria, com o
    alerta escrito por quem levantou), lidas da cópia em memória da torre (5 min). Fora do ar ou sem a cópia: None, e a
    aba Pontos diz que os da Zeladoria não vieram agora (nunca some calado)."""
    try:
        from flask import current_app

        from ...zeladoria import leitura
        return list((leitura.estado(current_app.config).get("abas") or {}).get("zeladoria_contratual") or [])
    except Exception as e:       # noqa: BLE001 — o Radar fora não derruba os contratos
        _log.warning("Contratos: os pontos do Radar da Zeladoria não vieram agora (%s: %s)", type(e).__name__, e)
        return None


@bp.route("/contratos")
def contratos():
    """A página: o JavaScript pede o dados.json e desenha. Sem a carga inicial no servidor, a página diz isso."""
    _so_interno()
    from ...contratos import controle as K
    try:
        tem = (_pasta_contratos() / K.ARQUIVO).exists()
    except Exception:            # noqa: BLE001 — sem a pasta de dados (o teste sem NEXUS_DADOS): a página diz que não chegou
        tem = False
    return render_template("comando/contratos.html", torre=TORRE, tela=TORRE.tela("contratos"), tem_carga=tem)


@bp.route("/visao-do-contrato", defaults={"resto": ""})
@bp.route("/visao-do-contrato/<path:resto>")
def visao_do_contrato_mudou(resto):
    """O endereço de antes (a Prévia, até 18/11/2026) leva à tela nova, com a busca."""
    q = request.query_string.decode("utf-8")
    return redirect(na_raiz(CONTRATOS) + (f"?{q}" if q else ""), code=308)


@bp.route("/contratos/dados.json")
def contratos_dados():
    """O estado de agora (a carga + as mudanças), com as contas de hoje, quem pode editar cada contrato e, para o
    administrador, as pessoas que podem ser gestoras."""
    from ...campo import visao
    _so_interno()
    base = _base()
    if not base["itens"]["cliente"]:
        resp = jsonify(ok=False)
    else:
        admin = bool(session.get("admin"))
        pessoas = _pessoas()
        try:
            mud = E.abrir(E.ler_banco())
            erro = None
        except Exception as e:   # noqa: BLE001 — banco fora: a carga sem as mudanças seria dado velho; a tela avisa
            _log.exception("Contratos: não li as edições do banco")
            mud, erro = [], f"Não li as edições do banco ({type(e).__name__}): o que aparece pode estar sem as últimas mudanças"
        st = E.aplicar(base, mud)
        out = E.visao(base, st, visao._agora().date(), pessoas, _meu_hmac(), admin, radar=_radar())
        out.update(ok=True, erro_edicoes=erro, campos={t: [list(c[:3]) + [list(c[3]) if isinstance(c[3], tuple) else c[3]]
                                                           for c in E.CAMPOS[t]] for t in E.CAMPOS},
                   pessoas=pessoas if admin else [], eu=_usuario().get("nome") or "")
        resp = jsonify(out)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ── a aba Indicadores (26/11/2026; a conta em `nexus/contratos/indicadores.py`) ──────────────────────────────────────
INDICADORES_S = 60                   # a cópia por contrato e ano: as fontes já têm as delas, esta poupa a montagem


def _fontes_da_ligacao(cliente: str, uids: set, ano: dict) -> tuple[dict, dict, dict, dict, list[str]]:
    """(pcm, zel, zel_min, ligacao, avisos) do cliente no ano: as tarefas do PCM e o cronograma do Radar ligados à usina
    pelo nome (`responsaveis.Nomes`, a régua de todo o Nexus: nome que serve a duas usinas não liga). Fonte que não abre
    vira aviso, e o resto vale."""
    from flask import current_app

    from ...campo import responsaveis as R
    from ...campo import visao
    from ...comando.gerencial import chave_cliente
    from ...pcm import fonte as PF
    from ...pcm import gestao as PG
    avisos, ligacao = [], {}
    pcm, zel, zel_min = {}, {}, {}
    nomes = R.Nomes(visao._Base())
    chave = chave_cliente(cliente)
    meses = set()
    a, m = int(ano["ini"][:4]), int(ano["ini"][5:7])
    for _ in range(12):
        meses.add(f"{a:04d}-{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    # MPM, MPS e MPA: as tarefas do ano do PCM (a cópia que já está na memória; sem ela, a leitura vem por trás)
    try:
        lei = PF.ler_gestao_sem_esperar(current_app.config)
        if lei is None:
            avisos.append("as tarefas do PCM ainda estão chegando: as preventivas aparecem em instantes")
        else:
            lig = tot = 0
            for tr in (lei.dados or {}).get("tarefas") or []:
                sm = PG.classificar(tr)
                if not sm or sm[0] not in ("MPM", "MPS", "MPA") or sm[1] not in meses:
                    continue
                do_cliente = chave_cliente(tr.get("cliente")) == chave
                uid = nomes.usina(tr.get("usina"), fracttal=tr.get("usina"))[0]
                if uid not in uids:
                    tot += 1 if do_cliente else 0
                    continue
                tot += 1
                lig += 1
                c = pcm.setdefault(uid, {}).setdefault(sm[0], {}).setdefault(sm[1], [0, 0])
                c[0] += 1 if str(tr.get("estado") or "") == "Finalizada" else 0
                c[1] += 1
            ligacao["pcm"] = {"ligadas": lig, "total": tot}
    except Exception:                    # noqa: BLE001 — sem o PCM, as preventivas ficam fora e a aba diz
        _log.exception("Contratos · Indicadores: as tarefas do PCM não abriram")
        avisos.append("as tarefas do PCM (MPM, MPS e MPA)")
    # a supressão vegetal e a lavagem: o cronograma do Radar da Zeladoria e o contratual dele (o mínimo por ano)
    try:
        from ...contratos.indicadores import SERVICOS
        from ...zeladoria import leitura
        est = leitura.estado(current_app.config)
        linha = next((x for x in est["abas"].get("cronograma_publico", []) if str(x.get("id")) == "cronograma"), None)
        snap = (linha or {}).get("dados") or {}
        lig = tot = 0
        for u in snap.get("usinas") or []:
            uid = nomes.usina(u.get("usina"))[0]
            if uid not in uids:
                tot += 1 if chave_cliente(u.get("cliente")) == chave else 0
                continue
            tot += 1
            lig += 1
            for h in u.get("historico") or []:
                for k, servs in SERVICOS.items():
                    if h.get("servico") in servs and h.get("data"):
                        zel.setdefault(uid, {}).setdefault(k, []).append(str(h["data"])[:10])
        ligacao["radar"] = {"ligadas": lig, "total": tot}
        geral = {}
        for r in est["abas"].get("zeladoria_contratual") or []:
            if chave_cliente(r.get("cliente")) != chave:
                continue
            mins = {k: int(float(r[campo])) for k, campo in (("rocada", "rocagens_ano"), ("lavagem", "lavagens_ano"))
                    if r.get(campo + "_tipo") == "fixo" and r.get(campo) not in (None, "")}
            uid = nomes.usina(r.get("ufv"))[0]
            if uid in uids:
                zel_min[uid] = mins
            elif mins:
                geral = mins               # a linha do portfólio ("82 UFVs", "Todas as SGDs"): vale para as sem linha própria
        for uid in uids:
            zel_min.setdefault(uid, geral)
    except Exception:                    # noqa: BLE001 — sem o Radar, a zeladoria fica fora e a aba diz
        _log.exception("Contratos · Indicadores: o Radar da Zeladoria não abriu")
        avisos.append("o cronograma do Radar da Zeladoria (a supressão vegetal e a lavagem)")
    return pcm, zel, zel_min, ligacao, avisos


@bp.route("/contratos/indicadores.json")
def contratos_indicadores():
    """A aba Indicadores de um contrato num ano contratual (`?cliente=&ano=`, o 1º ano é 1; sem ano, o de hoje). Enquanto
    a conta da Visão gerencial ainda monta (o Nexus acabou de subir), volta `montando` e a página pede de novo."""
    import time

    from flask import current_app

    from ...campo import visao
    from ...comando import diagnostico_mes as DM
    from ...comando.gerencial import chave_cliente
    from ...contratos import controle as K
    from ...contratos import indicadores as I
    from .gerencial_tela import dados_gerencial_sem_esperar
    _so_interno()
    cliente = request.args.get("cliente", "")
    n = request.args.get("ano", type=int)
    copias = current_app.extensions.setdefault("nexus_contratos_indicadores", {})
    ch = (cliente, n)
    if ch in copias and time.time() - copias[ch][0] < INDICADORES_S:
        resp = jsonify(copias[ch][1])
    else:
        hoje = visao._agora().date()
        base = _base()
        st = E.aplicar(base, E.abrir(E.ler_banco()))
        vis = E.visao(base, st, hoje, [], None, False)
        c = next((x for x in vis["contratos"] if x["cliente"] == cliente), None)
        if not c:
            abort(404)
        # sem `ano`, os últimos 12 meses (o padrão; vale também para o contrato sem início da vigência); com `ano`, aquele
        # ano contratual (o que fechou, o do relatório de aniversário)
        prim = K._d(c.get("inicio"))
        ano = K.ano_contratual(prim, hoje, n) if n else I.ultimos_12_meses(hoje)
        if not ano:
            out = {"ok": True, "sem_inicio": True}
        else:
            g = dados_gerencial_sem_esperar()
            if g is None:
                resp = jsonify(ok=True, montando=True)
                resp.headers["Cache-Control"] = "no-store"
                return resp
            cg = next((x for x in g.get("clientes") or [] if chave_cliente(x.get("cliente")) == chave_cliente(cliente)), None)
            usinas = (cg or {}).get("usinas") or []
            pcm, zel, zel_min, ligacao, avisos = _fontes_da_ligacao(cliente, {u.get("uid") for u in usinas}, ano)
            if not cg:
                avisos.append("o cliente não tem usina mobilizada no cadastro com este nome")
            com_dado = {m for m in (x["id"] for x in g.get("meses") or [])}
            out = I.montar(c, (vis.get("fichas") or {}).get(cliente), ano, usinas, pcm, zel, zel_min, hoje, com_dado,
                           ligacao, avisos + [x for x in g.get("avisos") or []      # só os avisos das fontes desta aba
                                              if any(p in x for p in ("histórico", "disponibilidade", "expurgo", "limitaç", "religamento"))])
            atual = K.ano_contratual(prim, hoje)
            out["anos"] = [{"n": i, "ini": K.ano_contratual(prim, hoje, i)["ini"], "fim": K.ano_contratual(prim, hoje, i)["fim"]}
                           for i in range(1, atual["n"] + 1)] if atual else []
            out["primeiro_mes_com_dado"] = DM.PRIMEIRO_MES if hasattr(DM, "PRIMEIRO_MES") else None
        copias[ch] = (time.time(), out)
        resp = jsonify(out)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/contratos/historico.json")
def contratos_historico():
    """O histórico de um cliente: cada mudança com quem, quando, o que era e o que ficou, o motivo e a prova."""
    _so_interno()
    cliente = request.args.get("cliente", "")
    base = _base()
    mud = E.abrir(E.ler_banco())
    out = E.historico(base, mud, cliente)
    for h in out:
        for a in h["anexos"]:
            a["url"] = na_raiz(f"{CONTRATOS}/anexo/{h['edicao_id']}/{a['n']}")
    resp = jsonify(ok=True, historico=out)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.route("/contratos/editar", methods=["POST"])
def contratos_editar():
    """Uma mudança (incluir, alterar ou retirar um item), com o motivo e a prova. Só da própria página; a resposta é
    JSON e a página relê o estado."""
    if _de_outro_site():
        abort(403)
    _so_interno()
    f = request.form
    try:
        valores = json.loads(f.get("valores") or "{}")
        if not isinstance(valores, dict):
            raise ValueError
    except ValueError:
        return jsonify(ok=False, erro="Mudança inválida"), 400
    arquivos = [(a.filename, a.stream) for a in request.files.getlist("provas")]
    try:
        r = E.gravar(_base(), f.get("item_tipo", ""), f.getlist("item_id"), f.get("evento", ""), f.get("cliente", ""),
                     valores, f.get("motivo", ""), f.get("prova_texto", ""), arquivos, _usuario(),
                     bool(session.get("admin")), _pessoas())
    except E.Recusada as e:
        return jsonify(ok=False, erro=str(e)), 400
    except Exception as e:       # noqa: BLE001 — banco fora: nada mudou, a tela diz
        _log.exception("Contratos: a mudança não gravou")
        return jsonify(ok=False, erro=f"Não consegui gravar no banco ({type(e).__name__}). Nada mudou; tente de novo."), 503
    return jsonify(ok=True, **r)


@bp.route("/contratos/carga-fichas", methods=["POST"])
def contratos_carga_fichas():
    """Mais fichas lidas dos PDFs na carga inicial (18/11/2026 à tarde: o Levi mandou os PDFs de mais clientes depois que a
    importação saiu da tela). Caminho interno do administrador, sem botão na tela (Levi: "Tire essas opções de subir
    arquivos"): quem lê os PDFs fora do Nexus manda o .json por aqui. Cliente novo entra; cliente que já tinha ficha é
    trocado só se ninguém editou um contrato lido ou uma regra dele (`edicao.juntar_fichas`). JSON na resposta."""
    import os

    from ...campo import visao
    from ...contratos import controle as K
    from ...contratos import fichas as F
    if _de_outro_site():
        abort(403)
    _so_interno()
    if not session.get("admin"):
        abort(403)
    f = request.files.get("fichas")
    if not f or not f.filename:
        return jsonify(ok=False, erro="Mande o arquivo das fichas (.json)"), 400
    conteudo = f.read(20 * 1024 * 1024 + 1)
    if len(conteudo) > 20 * 1024 * 1024:
        return jsonify(ok=False, erro="O arquivo passa de 20 MB"), 400
    try:
        novas = F.ler(json.loads(conteudo.decode("utf-8-sig")))
    except (ValueError, UnicodeDecodeError) as ex:
        return jsonify(ok=False, erro=str(ex) if isinstance(ex, F.FichasInvalidas) else "não é um .json válido"), 400
    controle = _json_da_pasta(K.ARQUIVO) or {}
    try:
        mud = E.abrir(E.ler_banco())
    except Exception as e:       # noqa: BLE001 — sem saber das edições, não troca nada
        return jsonify(ok=False, erro=f"Não li as edições do banco ({type(e).__name__}): nada foi trocado"), 503
    u = _usuario()
    doc, entraram, recusados = E.juntar_fichas(_json_da_pasta(F.ARQUIVO), novas, [c["cliente"] for c in controle.get("contratos") or []],
                                               mud, visao._agora().strftime("%Y-%m-%dT%H:%M"), u.get("nome") or u.get("email") or "",
                                               os.path.basename(f.filename))
    p = _pasta_contratos() / F.ARQUIVO
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return jsonify(ok=True, entraram=entraram, recusados=recusados,
                   regras=sum(len(c.get("regras") or []) for x in novas if x["cliente"] in entraram for c in x["contratos"]))


@bp.route("/contratos/anexo/<edicao_id>/<int:n>")
def contratos_anexo(edicao_id, n):
    """A prova de uma mudança, para quem é da Grid (o cliente não abre)."""
    _so_interno()
    if not E.ID_EDICAO.fullmatch(edicao_id):
        abort(404)
    achado = E.arquivo(edicao_id, n, E.abrir(E.ler_banco()))
    if not achado:
        abort(404)
    caminho, a = achado
    ext = caminho.suffix.lower()
    imagem = ext in (".png", ".jpg", ".jpeg", ".webp")
    return send_file(caminho, mimetype=E.SERVIDO.get(ext, "application/octet-stream"), as_attachment=not imagem and ext != ".pdf",
                     download_name=a.get("nome") or caminho.name)
