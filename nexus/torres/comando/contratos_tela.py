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
import re

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
        # quem cuida de quê (a visão reduzida, `contratos/setores.py`): só os ids das regras, a página já tem o texto
        from ...contratos import setores as S
        out["quem_cuida"] = S.montar(out.get("fichas") or {})
        out.update(ok=True, erro_edicoes=erro, campos={t: [list(c[:3]) + [list(c[3]) if isinstance(c[3], tuple) else c[3]]
                                                           for c in E.CAMPOS[t]] for t in E.CAMPOS},
                   pessoas=pessoas if admin else [], eu=_usuario().get("nome") or "")
        resp = jsonify(out)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ── a aba Indicadores (26/11/2026; a conta em `nexus/contratos/indicadores.py`) ──────────────────────────────────────
INDICADORES_S = 60                   # a cópia por contrato e ano: as fontes já têm as delas, esta poupa a montagem


def _servicos_feitos(uids: set, nomes, hoje_iso: str, tarefas, abas_radar) -> dict:
    """{uid: [{tipo, data, servico, rotulo, os, id}]}: a supressão e a lavagem
    feitas, do Radar (como o Histórico de Serviços as junta) e das OS finalizadas do Fracttal (o arquivo do ano do
    PCM), sem contar duas vezes o mesmo serviço (`indicadores.juntar_servicos`)."""
    from ...contratos import indicadores as I
    radar: dict = {}
    for sv in I.servicos_do_radar(abas_radar or {}, hoje_iso):
        uid = nomes.usina(sv["usina"], codigo=sv["codigo"])[0]
        if uid in uids:
            radar.setdefault(uid, []).append({**sv, "id": None})
    frac: dict = {}
    memo: dict = {}
    for tr in tarefas or []:
        if str(tr.get("estado") or "") != "Finalizada":
            continue
        tipo = I.tipo_da_tarefa(tr.get("tarefa"))
        data = str(tr.get("dataFinal") or "")[:10]
        if not tipo or len(data) != 10 or data > hoje_iso:
            continue
        nome = tr.get("usina")
        if nome not in memo:
            memo[nome] = nomes.usina(nome, fracttal=nome)[0]
        if memo[nome] in uids:
            frac.setdefault(memo[nome], []).append({"tipo": tipo, "data": data, "servico": re.sub(r"^(\[[^\]]*\]\s*)+", "", str(tr.get("tarefa") or "")).strip(" -")[:80],
                                                   "rotulo": "OS do Fracttal", "os": str(tr.get("os") or ""), "id": tr.get("idWO")})
    return {uid: I.juntar_servicos(radar.get(uid, []), frac.get(uid, [])) for uid in set(radar) | set(frac)}


def _zel_desde(config) -> str | None:
    """O 1º mês ("AAAA-MM") das tarefas do arquivo do ano do PCM: antes dele, o mês sem supressão ou lavagem é "sem dado"
    (em 26/11/2026 o arquivo começava em 01/2026)."""
    from ...pcm import fonte as PF
    lei = PF.ler_gestao_sem_esperar(config)
    ms = [str(t.get("dataProg") or "")[:7] for t in ((lei.dados or {}).get("tarefas") or [])] if lei else []
    ms = [m for m in ms if len(m) == 7]
    return min(ms) if ms else None


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
    tarefas = []
    try:
        lei = PF.ler_gestao_sem_esperar(current_app.config)
        tarefas = ((lei.dados or {}).get("tarefas") or []) if lei else []
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
        from ...campo import visao as V
        from ...contratos.indicadores import servicos_do_radar
        from ...zeladoria import leitura
        est = leitura.estado(current_app.config)
        # os serviços feitos: o Radar (como o Histórico de Serviços os junta) e as OS finalizadas do Fracttal; a usina do
        # Radar liga à do Nexus pelo nome ou pelo código
        hoje_iso = V._agora().date().isoformat()
        vistas, ligadas = set(), set()
        for sv in servicos_do_radar(est["abas"], hoje_iso):
            uid = nomes.usina(sv["usina"], codigo=sv["codigo"])[0]
            if uid in uids or chave_cliente(sv["cliente"]) == chave:
                vistas.add(sv["usina_radar"])
            if uid in uids:
                ligadas.add(sv["usina_radar"])
        ligacao["radar"] = {"ligadas": len(ligadas), "total": len(vistas)}
        for uid, lista in _servicos_feitos(uids, nomes, hoje_iso, tarefas, est["abas"]).items():
            for sv in lista:
                zel.setdefault(uid, {}).setdefault(sv["tipo"], []).append(sv["data"])
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


def _metas_pr_bd(uids: set, nomes) -> dict:
    """{uid: {"AAAA-MM": PR previsto em %}} (26/11/2026, Levi: "As metas de PR, você vai entrar na BD Performance"): o "PR
    Previsto 1° Ano" da aba Info Mensal da BD Performance e o "PR (2026)" da aba Dados Mensais 2026 da BD Thopen, por
    usina e mês, ligados pelo nome (`responsaveis.Nomes`, que já conhece as abas das duas BDs). Fonte que não abre fica
    de fora (o log diz), e a meta daquele cliente some da célula."""
    from ...campo import visao
    out: dict = {}
    for livro, aba, col in (("bd_performance", "Info Mensal", "PR Previsto 1° Ano (%)"), ("bd_thopen", "Dados Mensais 2026", "PR (2026)")):
        try:
            linhas = visao._livro(livro, aba)
        except Exception:                # noqa: BLE001
            _log.exception("Contratos · Indicadores: a meta de PR (%s · %s) não abriu", livro, aba)
            continue
        for r in linhas:
            uid = nomes.usina(r.get("Usina"))[0]
            mes = str(r.get("Mês") or "")[:7]
            try:
                v = float(r.get(col))
            except (TypeError, ValueError):
                continue
            if uid in uids and len(mes) == 7 and 0 < v <= 1.5:
                out.setdefault(uid, {})[mes] = round(v * 100 if v <= 1.5 else v, 1)
    return out


def _uid(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return v


def _usinas_kpi(cliente: str):
    """(as usinas do cliente [{uid, usina, mwp, meses, com_expurgo}], os meses com dado, os avisos da conta) ou None
    enquanto nada está pronto. O PR e a disponibilidade, com e sem o expurgo, vêm do livro `nexus_kpi_usina_mes`
    (`comando/kpi_mes.py`, 27/11/2026, Levi: "Pode até criar um book sobre isso para você não ficar carregando,
    calculando toda vez que abre"): o mês fechado é o do livro (congelado); o mês em curso, o da conta da Visão gerencial
    quando ela está pronta (o livro é de até uma hora atrás). Sem a conta (o Nexus acabou de subir), as usinas do
    cliente e os números saem só do livro, e a aba abre sem esperar."""
    from flask import current_app

    from ...campo import visao
    from ...comando import kpi_mes as KM
    from ...comando.gerencial import chave_cliente
    from .gerencial_tela import dados_gerencial_sem_esperar
    g = dados_gerencial_sem_esperar()
    kpi = KM.ler(current_app.config)
    mes_hoje = visao._agora().date().isoformat()[:7]
    if g is not None:
        cg = next((x for x in g.get("clientes") or [] if chave_cliente(x.get("cliente")) == chave_cliente(cliente)), None)
        usinas = [dict(u, uid=_uid(u.get("uid"))) for u in (cg or {}).get("usinas") or []]
        com_dado = {m["id"] for m in g.get("meses") or []}
        avisos = [x for x in g.get("avisos") or []      # só os avisos das fontes desta aba
                  if any(p in x for p in ("histórico", "disponibilidade", "expurgo", "limitaç", "religamento"))]
    elif kpi:
        base = visao._Base()
        usinas, com_dado, avisos = [], set(), []
        for uid, meses in kpi.items():
            if not any(chave_cliente(v.get("cliente")) == chave_cliente(cliente) for v in meses.values()):
                continue
            kwp = next((v.get("kwp") for v in meses.values() if v.get("kwp")), None)
            usinas.append({"uid": uid, "usina": str((base.por_id.get(uid) or {}).get("nome") or uid),
                           "mwp": round(kwp / 1000, 3) if kwp else None, "meses": {}, "com_expurgo": {}})
    else:
        return None
    for u in usinas:
        meses, exp = dict(u.get("meses") or {}), dict(u.get("com_expurgo") or {})
        for mid, v in (kpi.get(u["uid"]) or {}).items():
            com_dado.add(mid)
            if g is not None and mid >= mes_hoje and (meses.get(mid) or {}).get("pr") is not None:
                continue                         # o mês em curso: a conta de agora, mais nova que o livro
            meses[mid] = {**(meses.get(mid) or {}), "pr": v["pr"], "disp": v["disp"]}
            exp[mid] = {"pr": v["pr_exp"], "disp": v["disp_exp"]}
        u["meses"], u["com_expurgo"] = meses, exp
    return usinas, com_dado, avisos


@bp.route("/contratos/indicadores.json")
def contratos_indicadores():
    """A aba Indicadores de um contrato num ano contratual (`?cliente=&ano=`, o 1º ano é 1; sem ano, o de hoje). Enquanto
    a conta da Visão gerencial ainda monta (o Nexus acabou de subir), volta `montando` e a página pede de novo."""
    import time

    from flask import current_app

    from ...campo import visao
    from ...comando import diagnostico_mes as DM
    from ...contratos import controle as K
    from ...contratos import indicadores as I
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
            pronto = _usinas_kpi(cliente)
            if pronto is None:
                resp = jsonify(ok=True, montando=True)
                resp.headers["Cache-Control"] = "no-store"
                return resp
            usinas, com_dado, avisos_g = pronto
            uids = {u.get("uid") for u in usinas}
            pcm, zel, zel_min, ligacao, avisos = _fontes_da_ligacao(cliente, uids, ano)
            from ...campo import responsaveis as R
            try:
                metas_pr = _metas_pr_bd(uids, R.Nomes(visao._Base()))
            except Exception:            # noqa: BLE001 — sem o cadastro, a meta de PR da BD fica de fora e a aba diz
                _log.exception("Contratos · Indicadores: a meta de PR da BD Performance não abriu")
                metas_pr = {}
                avisos.append("a meta de PR da BD Performance")
            if not usinas:
                avisos.append("o cliente não tem usina mobilizada no cadastro com este nome")
            out = I.montar(c, (vis.get("fichas") or {}).get(cliente), ano, usinas, pcm, zel, zel_min, hoje, com_dado,
                           ligacao, avisos + avisos_g, metas_pr=metas_pr, zel_desde=_zel_desde(current_app.config))
            atual = K.ano_contratual(prim, hoje)
            out["anos"] = [{"n": i, "ini": K.ano_contratual(prim, hoje, i)["ini"], "fim": K.ano_contratual(prim, hoje, i)["fim"]}
                           for i in range(1, atual["n"] + 1)] if atual else []
            out["primeiro_mes_com_dado"] = DM.PRIMEIRO_MES if hasattr(DM, "PRIMEIRO_MES") else None
        copias[ch] = (time.time(), out)
        resp = jsonify(out)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ── a gaveta da célula (26/11/2026) ────────────────────────────────────────────────────────────────────────────────
# Levi, vendo a aba no ar: "esses botões coloridos aí fossem clicáveis e aparecesse a confirmação da resposta no card
# lateral [...] ia explicar o dado, qual é a OS e tudo mais. A OS clicável para eu conseguir abrir o card da OS". Cada
# célula (usina ou o contrato inteiro, uma linha, um mês ou o acumulado) se explica: as OS do PCM com o estado e as
# datas, os serviços de zeladoria com a data, o PR e a disponibilidade com a meta, o expurgo e a conta. Só lê: as fontes
# são as mesmas da aba, nas cópias que já estão na memória.
_ROT_LINHA = {"MPM": "MPM", "MPS": "MPS", "MPA": "MPA", "rocada": "Supressão vegetal", "lavagem": "Lavagem de módulos",
              "pr": "PR", "pr_exp": "PR expurgado", "disp": "Disponibilidade", "disp_exp": "Disponibilidade expurgada"}


def _br(v, casas=1):
    return "—" if v is None else f"{float(v):.{casas}f}".replace(".", ",")


@bp.route("/contratos/indicadores/celula.json")
def contratos_indicadores_celula():
    """`?cliente=&ano=&uid=&linha=&mes=`: uid "t" = o contrato inteiro; mes "acum" = a janela toda."""
    from flask import current_app

    from ...campo import responsaveis as R
    from ...campo import visao
    from ...contratos import controle as K
    from ...contratos import indicadores as I
    _so_interno()
    cliente, linha, mes = request.args.get("cliente", ""), request.args.get("linha", ""), request.args.get("mes", "")
    n = request.args.get("ano", type=int)
    uid_txt = request.args.get("uid", "")
    if linha not in _ROT_LINHA:
        abort(404)
    hoje = visao._agora().date()
    base = _base()
    vis = E.visao(base, E.aplicar(base, E.abrir(E.ler_banco())), hoje, [], None, False)
    c = next((x for x in vis["contratos"] if x["cliente"] == cliente), None)
    if not c:
        abort(404)
    ano = K.ano_contratual(K._d(c.get("inicio")), hoje, n) if n else I.ultimos_12_meses(hoje)
    if not ano:
        abort(404)
    meses = I.meses_do_ano(ano)
    ids = [m["id"] for m in meses] if mes == "acum" else [mes]
    if any(i not in {m["id"] for m in meses} for i in ids):
        abort(404)
    rot_mes = "a janela toda (" + meses[0]["rot"] + " a " + meses[-1]["rot"] + ")" if mes == "acum" else next(m["rot"] for m in meses if m["id"] == mes)
    usinas = {u["uid"]: u for u in (_usinas_kpi(cliente) or ([], set(), []))[0]}
    if uid_txt == "t":
        alvo, nome_alvo = set(usinas), f"{cliente} (contrato inteiro)"
    else:
        try:
            uid = int(uid_txt)
        except ValueError:
            abort(404)
        if uid not in usinas:
            abort(404)
        alvo, nome_alvo = {uid}, usinas[uid].get("usina")
    out = {"ok": True, "titulo": f"{_ROT_LINHA[linha]} · {nome_alvo} · {rot_mes}", "os": [], "servicos": [], "numeros": [],
           "usinas": [], "textos": [], "fonte": ""}
    nomes = R.Nomes(visao._Base())
    memo: dict = {}

    def uid_de(nome):
        if nome not in memo:
            memo[nome] = nomes.usina(nome, fracttal=nome)[0]
        return memo[nome]

    if linha in ("MPM", "MPS", "MPA"):
        from ...pcm import fonte as PF
        from ...pcm import gestao as PG
        lei = PF.ler_gestao_sem_esperar(current_app.config)
        for tr in ((lei.dados or {}).get("tarefas") or []) if lei else []:
            sm = PG.classificar(tr)
            if not sm or sm[0] != linha or sm[1] not in ids:
                continue
            u = uid_de(tr.get("usina"))
            if u not in alvo:
                continue
            out["os"].append({"os": str(tr.get("os") or ""), "id": tr.get("idWO"), "tarefa": PG.curto(tr.get("tarefa")) if hasattr(PG, "curto") else str(tr.get("tarefa") or ""),
                              "estado": str(tr.get("estado") or ""), "prog": str(tr.get("dataProg") or "")[:10],
                              "final": str(tr.get("dataFinal") or "")[:10], "usina": (usinas.get(u) or {}).get("usina") or ""})
        feitas = sum(1 for o in out["os"] if o["estado"] == "Finalizada")
        out["os"].sort(key=lambda o: (o["estado"] == "Finalizada", o["prog"], o["usina"]))
        # o PCM conta TAREFA a tarefa (uma OS de MPM traz a cabine, o inversor, a segurança…); a gaveta agrupa por OS
        out["numeros"] = [{"rot": "OS", "val": str(len({o["os"] for o in out["os"]}))}, {"rot": "Tarefas feitas", "val": str(feitas)},
                          {"rot": "Tarefas planejadas", "val": str(len(out["os"]))}, {"rot": "Tarefas abertas", "val": str(len(out["os"]) - feitas)}]
        out["fonte"] = (f"As tarefas do PCM (o arquivo do ano do Fracttal): a {linha} conta no mês da Data Programada, e "
                        "feita é a Finalizada. A OS abre o card do Fracttal.")
        if lei is None:
            out["textos"].append("As tarefas do PCM ainda estão chegando: abra de novo em instantes.")
    elif linha in ("rocada", "lavagem"):
        from ...pcm import fonte as PF
        from ...zeladoria import leitura
        est = leitura.estado(current_app.config)
        lei = PF.ler_gestao_sem_esperar(current_app.config)
        tarefas = ((lei.dados or {}).get("tarefas") or []) if lei else []
        for uu, lista in _servicos_feitos(alvo, nomes, hoje.isoformat(), tarefas, est["abas"]).items():
            for sv in lista:
                if sv["tipo"] == linha and sv["data"][:7] in ids:
                    out["servicos"].append({"data": sv["data"], "servico": sv["servico"][:1].upper() + sv["servico"][1:].lower() if sv["rotulo"] != "OS do Fracttal" else sv["servico"],
                                            "origem": sv["rotulo"], "os": sv["os"], "id": sv.get("id"), "usina": (usinas.get(uu) or {}).get("usina") or ""})
        out["servicos"].sort(key=lambda s: (s["data"], s["usina"]))
        # as atrasadas pelo prazo do contrato da zeladoria, lidas da conta da aba que já está na memória (a mesma célula,
        # a mesma dica); na usina, também os meses sem o serviço com a data da última
        copia = (current_app.extensions.get("nexus_contratos_indicadores") or {}).get((cliente, n))
        for u in ((copia or [0, {}])[1].get("usinas") or []):
            if u.get("uid") not in alvo:
                continue
            ln = next((x for x in u["linhas"] if x["id"] == linha), None) or {}
            for mid in ids:
                cel = (ln.get("cels") or {}).get(mid) or {}
                if cel.get("txt") == "atrasada" or (uid_txt != "t" and cel.get("txt") == "—"):
                    out["usinas"].append({"usina": u.get("usina"), "mes": next(m["rot"] for m in meses if m["id"] == mid),
                                          "val": cel.get("txt"), "tom": cel.get("tom") or "", "extra": cel.get("dica") or ""})
        nome_sv = "supressão" if linha == "rocada" else "lavagem"
        out["usinas_titulo"] = (f"Com a {nome_sv} atrasada pelo prazo do contrato" if uid_txt == "t" else f"Os meses sem {nome_sv}")
        atrasadas = sum(1 for x in out["usinas"] if x["val"] == "atrasada")
        out["numeros"] = [{"rot": "Feitas", "val": str(len(out["servicos"]))}, {"rot": "Atrasadas", "val": str(atrasadas)}]
        out["fonte"] = ("Os serviços feitos do Radar da Zeladoria, como o Histórico de Serviços os junta (o histórico de serviços, "
                        "a cotação com a execução terminada, a rota da equipe e a OS de contrato), e as OS finalizadas do Fracttal "
                        "(as tarefas de limpeza de módulos e de supressão vegetal do ano). A OS do Fracttal a até 10 dias de um "
                        "serviço do Radar é o mesmo serviço. O prazo é o do contrato da zeladoria de cada UFV: o mínimo do ano "
                        "vira o intervalo (2 por ano, uma a cada 6 meses); passou do intervalo desde a última sem o serviço, "
                        "atrasada. A UFV sem prazo no contrato só mostra as datas.")
    else:
        e_pr, expurgado = linha.startswith("pr"), linha.endswith("_exp")
        mt = I.metas(c, (vis.get("fichas") or {}).get(cliente))
        meta = (mt["pr"] if e_pr else mt["disp"]) or {}
        metas_bd = _metas_pr_bd(alvo, nomes) if e_pr and not meta else {}
        for u in sorted((usinas[x] for x in alvo), key=lambda x: -(x.get("mwp") or 0)):
            for mid in ids:
                mm = (u.get("meses") or {}).get(mid) or {}
                ex = (u.get("com_expurgo") or {}).get(mid) or {}
                if e_pr:
                    v = ex.get("pr") if expurgado and ex.get("pr") is not None else mm.get("pr")
                    v = v if v is not None and 0 < v <= I.PR_MAX else None
                    extra = ((f"sem o expurgo {_br(mm.get('pr'))}% · " if expurgado and ex.get("pr") is not None and mm.get("pr") is not None
                              and round(ex["pr"], 2) != round(mm["pr"], 2) else "")
                             + (f"geração {_br(mm.get('prod_kwh'), 0)} kWh de {_br(mm.get('meta_kwh'), 0)} kWh previstos"
                                if mm.get("prod_kwh") is not None else "")) if mm else ""
                else:
                    v = ex.get("disp") if expurgado and ex.get("disp") is not None else mm.get("disp")
                    extra = f"sem o expurgo {_br(mm.get('disp'))}%" if expurgado and mm.get("disp") is not None else ""
                    item = next((i for i in ((u.get("score") or {}).get(mid) or {}).get("itens") or [] if i.get("nome") == "Disponibilidade"), None)
                    if item and item.get("expurgo") and uid_txt != "t":
                        out["textos"].append(f"{next(m['rot'] for m in meses if m['id'] == mid)}: {item['expurgo']}")
                if v is None and not mm:
                    continue
                mu = meta.get("pct") if meta else (metas_bd.get(u.get("uid")) or {}).get(mid)
                if e_pr and not meta:
                    extra = (f"meta {_br(mu)}% (BD Performance)" if mu is not None else "sem meta na BD") + (" · " + extra if extra else "")
                out["usinas"].append({"usina": u.get("usina"), "mes": next(m["rot"] for m in meses if m["id"] == mid),
                                      "val": _br(v) + "%" if v is not None else "s/d", "tom": I.tom_kpi(v, mu), "extra": extra})
        out["numeros"] = [{"rot": "Meta do contrato" if meta else "Meta", "val": (_br(meta["pct"]) + "%") if meta.get("pct") is not None
                           else ("por usina, da BD Performance" if e_pr else "sem meta")}]
        out["fonte"] = ("O livro do PR e da disponibilidade de cada usina e mês (a conta da Visão gerencial já feita, de hora em "
                        "hora; o mês fechado congela no dia 11 do seguinte): o PR que a Performance publica (desde 10/2026) e a "
                        "disponibilidade do Fracttal e do COS. " + ("Com o expurgo do contrato: a queda da rede e a limitação "
                        "imposta saem da conta. " if expurgado else "Sem o expurgo do contrato. ") + "O contrato pondera pela potência. "
                        "Meta: " + (meta.get("origem") or ("a da BD Performance (Info Mensal) e da BD Thopen (Dados Mensais 2026), por usina e mês" if e_pr else "o contrato não traz")) + ".")
        if any(i < "2026-10" for i in ids):
            out["textos"].append("Antes de 10/2026 o banco não tem o PR nem a disponibilidade por mês: esses meses ficam sem dado.")
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
