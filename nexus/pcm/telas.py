"""Telas da programação semanal, penduradas na torre PCM (a torre chama registrar_pcm(bp)).

Etapa 1: Semana e Tarefas e OS mostram a programação que está valendo (a mesma do App de Campo).
Etapa 2: Gerar a semana roda o motor do PCM no Nexus, em sombra, e compara com a semana oficial do PCM.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from flask import abort, current_app, jsonify, redirect, render_template, request

from . import fonte, geracao, gestao as G, insumos as I, observacoes as O, semana as S

POR_PAGINA = 150
_BRT = timezone(timedelta(hours=-3))
SITUACOES = [("feita", "Finalizada"), ("andamento", "Em andamento"), ("nao_iniciada", "Não iniciada")]


def _h(v) -> str:
    """Horas no jeito brasileiro: 7,5 h; inteiro sem casa decimal."""
    v = round(float(v or 0), 1)
    return (("%d" % v) if v == int(v) else ("%.1f" % v).replace(".", ",")) + " h"


def _quando(iso: str | None) -> str:
    try:
        dt = datetime.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).astimezone(_BRT)
        return dt.strftime("%d/%m às %H:%M")
    except (TypeError, ValueError):
        return ""


def _contexto_fonte(leitura) -> dict:
    d = leitura.dados or {}
    return {"fonte_erro": leitura.erro, "fonte_velha": leitura.velha,
            "fonte_gerada": _quando(d.get("geradoEm")),
            "fonte_padrao": leitura.fonte == fonte.URL_PADRAO}


def _dias(sem) -> list[dict]:
    datas = sem.get("dates") or {}
    return [{"id": d, "nome": S.NOMES_DIA[d], "data": datas.get(d, "")} for d in S.DIAS]


def _ctx_gerar(cfg, rodada=None, erro=None, semana=None, ok=None) -> dict:
    sel = geracao.ler_status(cfg, rodada) if rodada else None
    if sel and sel.get("estado") == "rodando" and not geracao.ativa(cfg, sel["id"]):
        sel = dict(sel, estado="interrompida")
    semana = semana if semana and geracao.SEMANA_RE.match(semana) else (sel or {}).get("semana") or geracao.semana_padrao()
    origem = geracao.pasta_origem(cfg)
    trab = geracao.pasta_trabalho(cfg)
    # semana sem nada salvo mostra os dias por usina da última salva (o mesmo texto que o motor recebe)
    texto_obs, herdada_de = I.observacoes_efetivas(trab, semana)
    regras = O.ler(texto_obs)
    anterior = O.semana_anterior(semana)
    # Todas as usinas do Fracttal, do cache que o motor grava ao ler o Fracttal (pasta do PCM ou rodada do Nexus)
    rodadas = sorted((trab / "geracoes").glob("*/")) if (trab / "geracoes").is_dir() else []
    # a pasta de trabalho entra também: no servidor não há pasta do PCM, e o cache vai junto com os dados
    nomes_fr, quando_fr = O.ler_usinas_fracttal([origem, trab] + rodadas)
    usinas = O.usinas_por_dia(regras, nomes_fr)
    clientes = {}
    for u in usinas:
        c = clientes.setdefault(u["cliente"], {"nome": u["cliente"], "usinas": 0, "restritas": 0})
        c["usinas"] += 1
        c["restritas"] += len(u["dias"]) < len(O.DIAS)
    return {"conf": geracao.conferir(cfg, semana), "ultimas": geracao.ultimas(cfg), "sel": sel,
            "log": geracao.log(cfg, sel["id"], 40) if sel else "", "semana_sugerida": semana,
            "observacoes": texto_obs, "herdada_de": herdada_de,
            "regras": list(enumerate(regras)), "obs_resumo": O.resumo(regras),
            "dias": O.DIAS, "nomes_dia": O.NOMES_DIA, "turnos": O.TURNOS,
            "semana_anterior": anterior, "tem_anterior": bool(I.observacoes(trab, anterior).strip()),
            "usinas": usinas, "clientes": sorted(clientes.values(), key=lambda c: (-c["usinas"], c["nome"])),
            "sem_usina": O.regras_sem_usina(regras, usinas) if usinas else [],
            "usinas_por_dia": {d: sum(1 for u in usinas if d in u["dias"]) for d in O.DIAS},
            "usinas_restritas": sum(1 for u in usinas if len(u["dias"]) < len(O.DIAS)),
            "fracttal_em": datetime.fromtimestamp(quando_fr, _BRT).strftime("%d/%m %H:%M") if quando_fr else "",
            "tem_origem": bool(origem and origem.is_dir()),
            "campo": geracao.horario_de_campo(), "erro": erro, "ok": ok}


def _semana_do_form() -> str | None:
    s = (request.form.get("semana") or "").strip()
    return s if geracao.SEMANA_RE.match(s) else None


def registrar_pcm(bp) -> None:
    @bp.route("/gerar", methods=["GET", "POST"])
    def gerar():
        cfg = current_app.config
        if request.method == "GET":
            avisos = {"importado": "Importado da pasta do PCM.", "observacoes": "Observações salvas.",
                      "copiado": "Observações copiadas da semana anterior."}
            return render_template("pcm/gerar.html", **_ctx_gerar(
                cfg, rodada=request.args.get("rodada"), semana=request.args.get("semana"),
                ok=avisos.get(request.args.get("feito") or "")))
        semana_pedida = (request.form.get("semana") or "").strip()
        if not geracao.SEMANA_RE.match(semana_pedida):
            return render_template("pcm/gerar.html", **_ctx_gerar(cfg, erro="Semana inválida. Use o formato 2026-W41.")), 400
        if geracao.horario_de_campo() and not request.form.get("confirmo"):
            return render_template("pcm/gerar.html", **_ctx_gerar(
                cfg, erro="No horário de campo o motor divide a cota do Fracttal com o App de Campo. Marque a "
                          "confirmação para rodar mesmo assim.")), 400
        try:
            r = geracao.iniciar(cfg, semana_pedida)
        except geracao.NaoPronto as ex:
            return render_template("pcm/gerar.html", **_ctx_gerar(cfg, erro=f"Ainda não dá para gerar: {ex}.")), 400
        except geracao.Ocupado as ex:
            return render_template("pcm/gerar.html", **_ctx_gerar(
                cfg, erro=f"Já tem uma geração rodando (rodada {ex}). Espere ela terminar.")), 409
        return redirect("/t/pcm/gerar?rodada=" + r["id"], code=303)

    @bp.route("/gerar/importar", methods=["POST"])
    def gerar_importar():
        """Na sombra, traz para o Nexus os arquivos que a pasta do PCM tem hoje: as duas gerações partem do mesmo dado.
        As observações entram na semana escolhida."""
        cfg = current_app.config
        semana = _semana_do_form()
        if not semana:
            return render_template("pcm/gerar.html", **_ctx_gerar(cfg, erro="Semana inválida. Use o formato 2026-W41.")), 400
        origem = geracao.pasta_origem(cfg)
        if not (origem and origem.is_dir()):
            return render_template("pcm/gerar.html", **_ctx_gerar(cfg, semana=semana,
                                   erro="A pasta do PCM não está nesta máquina.")), 400
        try:
            I.importar(geracao.pasta_trabalho(cfg), origem, semana)
        except I.InsumoErro as ex:
            return render_template("pcm/gerar.html", **_ctx_gerar(cfg, semana=semana,
                                   erro=f"Não importei: {ex}")), 400
        return redirect(f"/t/pcm/gerar?semana={semana}&feito=importado", code=303)

    @bp.route("/gerar/observacoes", methods=["POST"])
    def gerar_observacoes():
        cfg = current_app.config
        semana = _semana_do_form()
        if not semana:
            return render_template("pcm/gerar.html", **_ctx_gerar(cfg, erro="Semana inválida. Use o formato 2026-W41.")), 400
        I.salvar_observacoes(geracao.pasta_trabalho(cfg), semana, request.form.get("texto") or "", autor="admin")
        return redirect(f"/t/pcm/gerar?semana={semana}&feito=observacoes", code=303)

    @bp.route("/gerar/observacoes/copiar", methods=["POST"])
    def gerar_observacoes_copiar():
        """Os dias de atendimento das usinas quase não mudam de uma semana para outra: começa pela anterior. Só
        copia para semana VAZIA, para nunca apagar o que alguém já escreveu."""
        cfg = current_app.config
        semana = _semana_do_form()
        if not semana:
            return render_template("pcm/gerar.html", **_ctx_gerar(cfg, erro="Semana inválida. Use o formato 2026-W41.")), 400
        trab = geracao.pasta_trabalho(cfg)
        anterior = O.semana_anterior(semana)
        if I.observacoes(trab, semana).strip():
            return render_template("pcm/gerar.html", **_ctx_gerar(cfg, semana=semana,
                                   erro=f"A semana {semana} já tem observações: não copiei por cima.")), 409
        texto = I.observacoes(trab, anterior)
        if not texto.strip():
            return render_template("pcm/gerar.html", **_ctx_gerar(cfg, semana=semana,
                                   erro=f"A semana {anterior} não tem observações para copiar.")), 400
        I.salvar_observacoes(trab, semana, texto, autor="admin")
        return redirect(f"/t/pcm/gerar?semana={semana}&feito=copiado", code=303)

    @bp.route("/gerar/estado")
    def gerar_estado():
        cfg = current_app.config
        st = geracao.ler_status(cfg, request.args.get("rodada") or "")
        if st is None:
            abort(404)
        estado = st.get("estado")
        if estado == "rodando" and not geracao.ativa(cfg, st["id"]):
            estado = "interrompida"
        return jsonify({"id": st["id"], "estado": estado, "duracao_s": st.get("duracao_s")})

    @bp.route("/semana")
    def semana():
        leitura = fonte.ler(current_app.config)
        ctx = _contexto_fonte(leitura)
        if leitura.dados is None:
            return render_template("pcm/semana.html", sem=None, **ctx)
        pedida = request.args.get("semana") or None
        sem = S.achar(leitura.dados, pedida)
        if sem is None:
            abort(404)
        equipes = S.por_equipe(sem)
        for e in equipes:
            e["horas_txt"] = {d: (_h(h) if h else "") for d, h in e["horas_dia"].items()}
            e["noite_txt"] = {d: (_h(h) if h else "") for d, h in e["horas_noite"].items()}
        res = S.resumo(sem)
        res["horas_txt"] = _h(res["horas"])
        return render_template("pcm/semana.html", sem=sem, semanas=S.semanas(leitura.dados), resumo=res,
                               equipes=equipes, dias=_dias(sem), capacidade=_h(S.CAPACIDADE_H), **ctx)

    @bp.route("/tarefas")
    def tarefas():
        leitura = fonte.ler(current_app.config)
        ctx = _contexto_fonte(leitura)
        if leitura.dados is None:
            return render_template("pcm/tarefas.html", sem=None, **ctx)
        a = request.args
        sem = S.achar(leitura.dados, a.get("semana") or None)
        if sem is None:
            abort(404)
        filtros = {"equipe": a.get("equipe") or None, "dia": a.get("dia") or None, "status": a.get("status") or None,
                   "tipo": a.get("tipo") or None, "busca": a.get("q") or None,
                   "horario": "fora" if a.get("horario") == "fora" else None}
        todas = S.tarefas(sem, **filtros)
        try:
            pagina = max(1, int(a.get("pagina") or 1))
        except ValueError:
            pagina = 1
        paginas = max(1, -(-len(todas) // POR_PAGINA))
        pagina = min(pagina, paginas)
        linhas = []
        for r in todas[(pagina - 1) * POR_PAGINA: pagina * POR_PAGINA]:
            d = S.dia_curto(r.get("dia"))
            linhas.append(dict(r, _dia=S.NOMES_DIA.get(d, r.get("dia") or ""), _situacao=S.situacao(r),
                               _duracao=_h(r.get("duracao"))))
        rows = sem.get("rows") or []
        opcoes = {
            "equipes": sorted({str(r.get("cluster")) for r in rows if r.get("cluster")}),
            "tipos": sorted({str(r.get("tipo")) for r in rows if r.get("tipo")}),
            "dias": [(d, S.NOMES_DIA[d]) for d in S.DIAS], "situacoes": SITUACOES,
        }
        return render_template("pcm/tarefas.html", sem=sem, semanas=S.semanas(leitura.dados), linhas=linhas,
                               total=len(todas), total_semana=len(rows), pagina=pagina, paginas=paginas,
                               filtros=filtros, q=a.get("q") or "", opcoes=opcoes, **ctx)

    @bp.route("/gestao")
    def gestao():
        return render_template("pcm/gestao.html", **_ctx_gestao(current_app.config, request.args))


# ── Gestão PCM: o bloco "Manutenções — Plano & Fila" do painel (nexus/pcm/gestao.py) ──────────────────────────
# As 28 mil tarefas do gestao_pcm.json não precisam ser revarridas a cada clique: o escopo e a base atômica ficam
# guardados pela versão do arquivo (dataHash) e pelos filtros de cima; a Gerencial decifrada, pela versão do mpas.json.
_G_CACHE: dict = {}


def _guardado(chave, fazer):
    # sem ler duas vezes do dicionário: outra requisição pode limpá-lo no meio (o servidor atende em paralelo)
    v = _G_CACHE.get(chave)
    if v is None:
        v = fazer()
        if len(_G_CACHE) > 40:
            _G_CACHE.clear()
        _G_CACHE[chave] = v
    return v


def _gerencial(cfg) -> tuple[dict | None, str]:
    """A planilha da Gerencial aberta com a senha do .env (só em memória: nunca vai para o banco nem para a página)."""
    senha = cfg.get("NEXUS_PCM_MPAS_SENHA")
    if not senha:
        return None, "sem_chave"
    lm = fonte.ler_mpas(cfg)
    if lm.dados is None:
        return None, f"não consegui ler o mpas.json ({lm.erro})"
    try:
        return _guardado(("mpas", lm.dados.get("geradoEm"), lm.dados["ct"][:64]), lambda: G.decifrar(lm.dados, senha)), ""
    except Exception:      # noqa: BLE001 — senha errada ou pacote novo: a tela diz, e a Fila segue com o Fracttal
        return None, "a senha da Gerencial do .env não abriu o mpas.json"


def _ctx_gestao(cfg, args) -> dict:
    leitura = fonte.ler_gestao(cfg)
    d = leitura.dados or {}
    ctx = {"fonte_erro": leitura.erro, "fonte_velha": leitura.velha, "fonte_gerada": _quando(d.get("geradoEm")),
           "dados": leitura.dados is not None}
    if leitura.dados is None:
        return ctx
    h = G.hoje()
    meses = G.meses(h)
    o = G.opcoes(args, meses)
    versao = d.get("dataHash") or d.get("geradoEm")
    # arquivo novo do robô: o que foi guardado da versão anterior sai inteiro. Cada versão prende ~49 MB de tarefas
    # (medido em 08/10/2026); sem isto, até 8 versões velhas ficariam na memória antes de o teto de 40 limpar
    if _G_CACHE.get("versao") != versao:
        _G_CACHE.clear()
        _G_CACHE["versao"] = versao
    escopo = _guardado(("escopo", versao), lambda: G.escopo(d.get("tarefas")))
    escolhas = _guardado(("escolhas", versao), lambda: G.escolhas_topo(escopo))
    topo = {k: str(args.get(k) or "")[:160] for k in G.TOPO}
    tarefas = _guardado(("topo", versao, *topo.values()), lambda: G.filtrar_topo(escopo, **topo))
    base = _guardado(("base", versao, *topo.values(), *meses), lambda: G.base(tarefas, meses))
    mp, ger_erro = _gerencial(cfg)
    # a Fila inteira (antes dos filtros do bloco): é dela que saem o par de números do topo e os KPIs. Sem a
    # Gerencial, é o lado do Fracttal, e o par mostra as atrasadas pela Data Programada (o painel só mostra o cadeado)
    # o atraso conta do meio-dia (regra do painel): a cópia guardada vale por meio dia, não pelo dia inteiro
    ver_ger, meio_dia = (mp or {}).get("geradoEm"), G.agora().hour >= 12
    fila = _guardado(("fila", versao, ver_ger, mp is not None, h, meio_dia, *topo.values()),
                     lambda: G.fila_universo(tarefas, mp, topo, h))

    def url(**mud):
        q = {k: v for k, v in args.items() if v not in ("", None)}
        for k, v in mud.items():
            if v is None:
                q.pop(k, None)
            else:
                q[k] = v
        return "?" + urlencode(q) if q else "?"

    ctx.update(o=o, meses=meses, rot_mes=G.rot_mes, par=G.par_topo(base, meses, fila), tem_ger=mp is not None,
               ger_erro=ger_erro, topo=topo, url=url, primarios=G.PRIMARIOS, mais=G.MAIS, rot_tipo=G.ROT_TIPO,
               sub_siglas=[("prev", "Todas")] + [(s, s) for s in G.SIGLAS], dims=G.DIMS, valores=G.VALORES,
               val_rot=G.VAL_ROT, pendencias=G.PENDENCIAS, mes_ops=[("todos", "Todos")] + [(m, G.rot_mes(m)) for m in meses],
               em_prev=o.tipo == "prev" or o.tipo in G.SIGLAS, eh_demanda=G.eh_demanda(o.tipo), data_curta=G.data_curta,
               faixa_atraso=G.faixa_atraso, kpis=G.kpis_fila(fila), escolhas=escolhas,
               tem_topo=any(topo.values()), corte=d.get("corteData"))
    if o.modo == "plano":
        ctx.update(mx=G.plano(base, o, meses, G.crit_obs(mp) if mp is not None else None), rot_col=G.rot_col,
                   faixa=G.faixa)
    else:
        ctx.update(fila=G.fila_filtrada(fila, o))
    return ctx
