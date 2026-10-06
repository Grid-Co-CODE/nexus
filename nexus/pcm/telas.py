"""Telas da programação semanal, penduradas na torre PCM (a torre chama registrar_pcm(bp)).

Etapa 1: Semana e Tarefas e OS mostram a programação que está valendo (a mesma do App de Campo).
Etapa 2: Gerar a semana roda o motor do PCM no Nexus, em sombra, e compara com a semana do Fabrício.
"""
from datetime import datetime, timedelta, timezone

from flask import abort, current_app, jsonify, redirect, render_template, request

from . import fonte, geracao, insumos as I, observacoes as O, semana as S

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
        """Na sombra, traz para o Nexus os arquivos que o Fabrício tem hoje: as duas gerações partem do mesmo dado.
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
