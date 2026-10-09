"""Telas da programação semanal, penduradas na torre PCM (a torre chama registrar_pcm(bp)).

Etapa 1: Semana e Tarefas e OS mostram a programação que está valendo (a mesma do App de Campo).
Etapa 2: Gerar a semana roda o motor do PCM no Nexus, em sombra, e compara com a semana oficial do PCM.
Etapa 3 (09/10/2026, Levi: "semana que vem já quero full nexus sem falta"): Publicar no App manda a semana gerada para o
repositório do PCM, pelo mesmo caminho do PC do PCM (`publicar.py`): só administrador, com a tela de confirmação.
Quadro da semana (09/10/2026): o quadro da aba Semana do painel do PCM e a reprogramação de tarefas (`quadro.py`).
"""
import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from flask import abort, current_app, jsonify, redirect, render_template, request, session

from . import fonte, geracao, gestao as G, historico_banco as HB, insumos as I, observacoes as O, publicar as PB
from . import quadro as Q, semana as S

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
    app_sel = None
    if sel and sel.get("publicacao"):
        leitura = fonte.ler(cfg)                    # a semana já chegou ao App? (o banco_dados.json que ele lê)
        app_sel = {"semana": PB.semana_no_app(leitura.dados, sel["semana"]), "erro": leitura.erro}
    return {"conf": geracao.conferir(cfg, semana), "ultimas": geracao.ultimas(cfg), "sel": sel,
            "admin": bool(session.get("admin")), "app_sel": app_sel,
            "pode_publicar": bool(sel) and not PB.motivos_para_nao_publicar(cfg, sel["id"]),
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


def _ctx_publicar(cfg, st: dict, motivos: list, erro: str | None = None) -> dict:
    """O que a pessoa precisa ver antes de mandar a semana para o campo."""
    pasta = geracao.pasta_trabalho(cfg) / "geracoes" / st["id"]
    try:
        regras = O.ler((pasta / I.OBSERVACOES).read_text(encoding="utf-8"))
    except OSError:
        regras = []
    horas = None
    try:
        fim = datetime.fromisoformat(st.get("fim") or st.get("inicio"))
        horas = int((datetime.now(_BRT) - fim).total_seconds() // 3600)
    except (TypeError, ValueError):
        pass
    return {"st": st, "motivos": motivos, "erro": erro, "negado": False, "conf": st.get("conferencia") or {},
            "obs": O.resumo(regras), "repo": PB.estado_no_repositorio(cfg, st["semana"]),
            "planilha": PB.nome_planilha(st["semana"]), "horas_desde": horas, "ja_comecou": PB.ja_comecou(st["semana"])}


def _semana_do_form() -> str | None:
    s = (request.form.get("semana") or "").strip()
    return s if geracao.SEMANA_RE.match(s) else None


def registrar_pcm(bp) -> None:
    @bp.route("/gerar", methods=["GET", "POST"])
    def gerar():
        cfg = current_app.config
        if request.method == "GET":
            avisos = {"importado": "Importado da pasta do PCM.", "observacoes": "Observações salvas.",
                      "copiado": "Observações copiadas da semana anterior.",
                      "importado_repo": "Observações importadas do repositório do PCM.",
                      "publicada": "Semana publicada no repositório do PCM. O robô do PCM regrava o banco_dados.json do "
                                   "App em 5 a 10 minutos."}
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

    @bp.route("/gerar/importar-repositorio", methods=["POST"])
    def gerar_importar_repositorio():
        """As observações que estão no repositório do PCM (o Observacoes_Semana.txt que o PC do PCM ou o painel mandou)
        entram na semana escolhida. Funciona no servidor, onde a pasta do PCM não existe."""
        cfg = current_app.config
        semana = _semana_do_form()
        if not semana:
            return render_template("pcm/gerar.html", **_ctx_gerar(cfg, erro="Semana inválida. Use o formato 2026-W41.")), 400
        ler = geracao.leitor_do_repositorio(cfg)
        try:
            dados = ler(I.OBSERVACOES) if ler else None
        except Exception as ex:      # noqa: BLE001
            return render_template("pcm/gerar.html", **_ctx_gerar(cfg, semana=semana,
                                   erro=f"Não consegui ler o repositório do PCM ({type(ex).__name__}).")), 502
        if not dados:
            return render_template("pcm/gerar.html", **_ctx_gerar(cfg, semana=semana,
                                   erro="O repositório do PCM não tem o Observacoes_Semana.txt.")), 404
        repo, ramo = fonte.repositorio(cfg)
        I.salvar_observacoes(geracao.pasta_trabalho(cfg), semana, dados.decode("utf-8", errors="replace"),
                             autor="repositório do PCM", origem={"arquivo": f"{repo} · {I.OBSERVACOES}",
                                                                  "importado_em": I._agora()})
        return redirect(f"/t/pcm/gerar?semana={semana}&feito=importado_repo", code=303)

    @bp.route("/gerar/publicar", methods=["GET", "POST"])
    def gerar_publicar():
        """Publicar no App: a confirmação (GET) e o envio (POST). Só administrador: muda a semana de todo o campo."""
        cfg = current_app.config
        rid = (request.values.get("rodada") or "").strip()
        st = geracao.ler_status(cfg, rid)
        if st is None:
            abort(404)
        if not session.get("admin"):
            return render_template("pcm/publicar.html", st=st, negado=True), 403
        motivos = PB.motivos_para_nao_publicar(cfg, rid)
        if request.method == "POST":
            repo_ja_tem = request.form.get("repo_ja_tem") == "1"
            comecou = PB.ja_comecou(st["semana"])
            if (not request.form.get("confirmo") or (repo_ja_tem and not request.form.get("substituir"))
                    or (comecou and not request.form.get("ciente_comecou"))):
                return render_template("pcm/publicar.html", **_ctx_publicar(cfg, st, motivos,
                                       erro="Marque a confirmação para publicar.")), 400
            quem = (session.get("usuario") or {}).get("email") or "administrador (senha)"
            try:
                PB.publicar(cfg, rid, quem)
            except PB.PublicacaoErro as ex:
                return render_template("pcm/publicar.html", **_ctx_publicar(cfg, st, motivos,
                                       erro=f"Não publiquei: {ex}.")), 400
            except Exception as ex:      # noqa: BLE001 — rede, GitHub fora: a tela diz e nada muda na rodada
                return render_template("pcm/publicar.html", **_ctx_publicar(cfg, st, motivos,
                                       erro=f"O GitHub não respondeu ({type(ex).__name__}): nada foi publicado, ou "
                                            f"só parte; confira o repositório antes de tentar de novo.")), 502
            return redirect(f"/t/pcm/gerar?rodada={rid}&feito=publicada", code=303)
        return render_template("pcm/publicar.html", **_ctx_publicar(cfg, st, motivos))

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

    @bp.route("/quadro")
    def quadro():
        ctx = _ctx_quadro(current_app.config, request.args)
        if ctx is None:
            abort(404)
        return render_template("pcm/quadro.html", **ctx)

    @bp.route("/quadro/reprogramar", methods=["POST"])
    def quadro_reprogramar():
        """Grava a fila de reprogramação da página. Só administrador. Semana que o Nexus gera: nas observações dela no
        Nexus, direto. Semana em curso: nos ajustes da semana em curso do repositório do PCM, depois da confirmação."""
        cfg = current_app.config
        if not session.get("admin"):
            abort(403)
        f = request.form
        base = _quadro_semana(cfg, (f.get("semana") or "").strip() or None, (f.get("rodada") or "").strip() or None)
        sem = base["sem"]
        if sem is None:
            abort(404)
        try:
            itens = json.loads(f.get("itens") or "[]")
        except ValueError:
            itens = []
        linhas, problemas = Q.linhas_da_fila(sem, itens)
        dest = _destino_quadro(cfg, base)
        quem = (session.get("usuario") or {}).get("email") or "administrador (senha)"
        volta = {"semana": sem["week"]}
        if base["rodada"]:
            volta["rodada"] = base["rodada"]
        # os filtros da tela voltam junto: quem reprogramou a equipe dele continua nela
        volta.update({k: str(f.get("f_" + k))[:160] for k in Q.FILTROS if f.get("f_" + k)})
        if dest["id"] == "nexus":
            if problemas or not linhas:
                ctx = _ctx_quadro(cfg, volta, erro="Nada foi gravado: " + ("; ".join(problemas) if problemas
                                                                              else "a fila está vazia") + ".")
                return render_template("pcm/quadro.html", **ctx), 400
            Q.salvar_no_nexus(cfg, sem["week"], linhas, quem)
            return redirect("/t/pcm/quadro?" + urlencode(dict(volta, feito="salvo", n=len(linhas))), code=303)
        if dest["id"] != "atual":
            ctx = _ctx_quadro(cfg, volta, erro="Esta semana não aceita gravar reprogramação: " + dest["texto"])
            return render_template("pcm/quadro.html", **ctx), 400
        itens_json = json.dumps(itens if isinstance(itens, list) else [], ensure_ascii=False)
        if not f.get("confirmo"):
            return render_template("pcm/reprogramar.html", **_ctx_reprogramar(cfg, sem["week"], linhas, problemas,
                                                                              itens_json))
        if problemas or not linhas:
            return render_template("pcm/reprogramar.html", **_ctx_reprogramar(
                cfg, sem["week"], linhas, problemas, itens_json, erro="Nada foi gravado.")), 400
        try:
            res = Q.aplicar_na_semana_em_curso(cfg, sem["week"], linhas, quem, f.get("sha_visto") or "",
                                               apagar_sem_semana=f.get("apagar") == "1")
        except (Q.QuadroErro, PB.PublicacaoErro) as ex:
            return render_template("pcm/reprogramar.html", **_ctx_reprogramar(
                cfg, sem["week"], linhas, problemas, itens_json, erro=f"Não gravei: {ex}.")), 409
        except Exception as ex:      # noqa: BLE001 — rede, GitHub fora: a tela diz e nada muda
            return render_template("pcm/reprogramar.html", **_ctx_reprogramar(
                cfg, sem["week"], linhas, problemas, itens_json,
                erro=f"O GitHub não respondeu ({type(ex).__name__}): confira o repositório antes de tentar de novo.")), 502
        return redirect("/t/pcm/quadro?" + urlencode(dict(volta, feito="aplicado", n=len(linhas),
                                                           commit=res.get("commit") or "")), code=303)


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


# ── Quadro da semana (09/10/2026): o quadro da aba Semana do painel do PCM e a reprogramação (nexus/pcm/quadro.py) ────
def _quadro_semana(cfg, semana_pedida: str | None, rodada_pedida: str | None) -> dict:
    """A semana que o quadro mostra: a pedida (publicada no App ou rascunho do Nexus); sem pedir, a semana em curso do
    App. Devolve {sem, fonte_sem ("publicada" | "rascunho"), rodada, st, publicadas, rasc, leitura, dia}."""
    leitura = fonte.ler(cfg)
    dados = leitura.dados or {}
    publicadas = [s for s in dados.get("semanas") or [] if isinstance(s, dict) and s.get("week")]
    dia = Q.hoje()
    rasc = Q.rascunhos(cfg, dia)
    out = {"leitura": leitura, "publicadas": publicadas, "rasc": rasc, "sem": None, "fonte_sem": "", "rodada": None,
           "st": None, "dia": dia}
    st = Q.rodada_ok(cfg, rodada_pedida) if rodada_pedida else None
    if st is None and semana_pedida and not any(s["week"] == semana_pedida for s in publicadas):
        r = next((x for x in rasc if x["semana"] == semana_pedida), None)
        st = Q.rodada_ok(cfg, r["rodada"]) if r else None
    if st is None and not semana_pedida and not publicadas and rasc:
        st = Q.rodada_ok(cfg, rasc[-1]["rodada"])
    if st is not None:
        pasta = Q.pasta_da_rodada(cfg, st["id"])
        out.update(sem=Q.semana_do_rascunho(pasta / "saida" / "sombra.xlsx", st["semana"]), fonte_sem="rascunho",
                   rodada=st["id"], st=st)
        return out
    if semana_pedida:
        sem = next((s for s in publicadas if s["week"] == semana_pedida), None)
    else:
        ativa = dados.get("semana_ativa")
        sem = next((s for s in publicadas if s["week"] == ativa), None) or \
            (max(publicadas, key=lambda s: s["week"]) if publicadas else None)
    if sem is not None:
        out.update(sem=sem, fonte_sem="publicada")
    return out


def _destino_quadro(cfg, base) -> dict:
    w = base["sem"]["week"]
    return Q.destino(w, base["fonte_sem"], base["fonte_sem"] == "rascunho" or Q.nexus_gera(cfg, w), base["dia"])


def _num_semana(w: str) -> int:
    return HB.segunda(w).isocalendar()[1]


def _chips_quadro(base, extra: dict) -> list[dict]:
    """As semanas para escolher: as do arquivo do App e os rascunhos do Nexus que ainda não foram ao App. Os filtros
    vão junto (o gestor que entrou filtrado continua filtrado ao trocar de semana)."""
    dia, sel = base["dia"], base["sem"]
    chips = []
    for s in base["publicadas"]:
        seg = HB.segunda(s["week"])
        quando = " · em curso" if seg <= dia <= seg + timedelta(days=4) else (" · próxima" if seg > dia else "")
        chips.append({"w": s["week"], "o": 1, "rotulo": f"Semana {_num_semana(s['week'])}{quando}",
                      "href": "?" + urlencode(dict(extra, semana=s["week"])),
                      "atual": base["fonte_sem"] == "publicada" and sel is not None and sel["week"] == s["week"]})
    no_app = {s["week"] for s in base["publicadas"]}
    for r in base["rasc"]:
        if r["semana"] in no_app and r["publicada"] and r["rodada"] != base["rodada"]:
            continue
        chips.append({"w": r["semana"], "o": 0, "rotulo": f"Semana {_num_semana(r['semana'])} · rascunho do Nexus",
                      "href": "?" + urlencode(dict(extra, rodada=r["rodada"])), "atual": base["rodada"] == r["rodada"]})
    if base["rodada"] and not any(c["atual"] for c in chips):          # rodada de prova aberta pelo endereço
        w = base["sem"]["week"]
        chips.append({"w": w, "o": 0, "rotulo": f"Semana {_num_semana(w)} · rodada de prova", "atual": True,
                      "href": "?" + urlencode(dict(extra, rodada=base["rodada"]))})
    return sorted(chips, key=lambda c: (c["w"], -c["o"]), reverse=True)


def _gestor_da_sessao(sem) -> str:
    """O gestor de contrato que entrou (estrutura de O&M de 10/2026), como ele aparece na coluna Responsável da
    programação: o nome inteiro ou o primeiro e o último nome. Vazio se não casar com nenhum."""
    sup = session.get("supervisor_padrao") or {}
    if sup.get("papel") != "gestor" or not sup.get("nome"):
        return ""
    alvo = S._norm(sup["nome"]).split()
    for r in sorted({str(x.get("responsavel") or "").strip() for x in sem.get("rows") or []} - {""}):
        n = S._norm(r).split()
        if n == alvo or (len(alvo) >= 2 and len(n) >= 2 and n[0] == alvo[0] and n[-1] == alvo[-1]):
            return r
    return ""


def _ctx_quadro(cfg, args, erro: str | None = None) -> dict | None:
    pedida = (args.get("semana") or "").strip() or None
    base = _quadro_semana(cfg, pedida, (args.get("rodada") or "").strip() or None)
    ctx = _contexto_fonte(base["leitura"])
    sem = base["sem"]
    if sem is None:
        if pedida and base["leitura"].dados is not None:
            return None
        return dict(ctx, sem=None, chips=[], erro=erro, ok=None)
    filtros = {k: str(args.get(k) or "").strip()[:160] for k in Q.FILTROS}
    filtro_gestor = False
    if not pedida and not any(filtros.values()) and not args.get("rodada"):
        g = _gestor_da_sessao(sem)
        if g:
            filtros["resp"], filtro_gestor = g, True
    todos = args.get("todos") == "1"
    q = Q.montar(sem, base["publicadas"], filtros, todos=todos, mostrar_pendentes=True if args.get("pend") == "1" else None)
    dest = _destino_quadro(cfg, base)
    admin = bool(session.get("admin"))
    extra = {k: v for k, v in filtros.items() if v}
    sel_qs = dict(extra, **({"rodada": base["rodada"]} if base["rodada"] else {"semana": sem["week"]}))
    feito = args.get("feito") or ""
    n = int(args.get("n")) if str(args.get("n") or "").isdigit() else 0
    commit = args.get("commit") if re.fullmatch(r"[0-9a-f]{4,40}", str(args.get("commit") or "")) else ""
    ok = None
    if feito == "salvo":
        ok = (f"{n} {'linha gravada' if n == 1 else 'linhas gravadas'} nas observações da {sem['week']}. Valem na próxima "
              f"geração da semana: gere de novo em Gerar a semana.")
    elif feito == "aplicado":
        ok = (f"{n} {'linha gravada' if n == 1 else 'linhas gravadas'} nos ajustes da semana em curso"
              f"{f' (commit {commit})' if commit else ''}. O robô do PCM aplica na rodada seguinte (até 15 minutos); "
              f"o quadro muda quando ele regravar a programação.")
    if base["fonte_sem"] == "rascunho":
        st = base["st"] or {}
        quando = str(st.get("fim") or st.get("inicio") or "")
        origem_txt = (f"rascunho do Nexus, gerado em {quando[8:10]}/{quando[5:7]} às {quando[11:16]}"
                      + (", publicado no App" if st.get("publicacao") else ", ainda não publicado")
                      + (" (rodada de prova)" if len(base["rodada"]) > 24 else ""))
    else:
        g = _quando(sem.get("geradaEm"))
        origem_txt = "publicada no App" + (f", gerada em {g}" if g else "")
    dados = {"semana": sem["week"], "rodada": base["rodada"] or "", "destino": dest["id"], "admin": admin,
             "dias": [[d, Q.NOMES_DIA[d]] for d in Q.DIAS_REPROGRAMAR], "turnos": list(Q.TURNOS), "itens": q["itens"],
             "oss": q["oss"],
             "feito": feito in ("salvo", "aplicado")}
    ctx["fonte_frase"] = ("Reprogramar daqui não muda nada na hora: vira linha de observação, que só o PCM grava, e vale "
                          "onde a fila diz.")
    ctx["ok_link"] = f"/t/pcm/gerar?semana={sem['week']}" if feito == "salvo" else ""
    return dict(ctx, sem=sem, q=q, filtros=filtros, filtro_gestor=filtro_gestor, destino=dest, admin=admin,
                rodada=base["rodada"], chips=_chips_quadro(base, extra), origem_txt=origem_txt, dados=dados,
                tem_filtro=any(filtros.values()),
                url_limpar="?" + urlencode({k: v for k, v in sel_qs.items() if k in ("semana", "rodada")}),
                url_todos="?" + urlencode(dict(sel_qs, todos="1")),
                url_pendentes="?" + urlencode(dict(sel_qs, pend="1", **({"todos": "1"} if todos else {}))) + "#pendentes",
                abrir_pendentes=args.get("pend") == "1" or (any(filtros.values()) and q["pend_sel"] <= 80),
                dias_rp=[(d, Q.NOMES_DIA[d]) for d in Q.DIAS_REPROGRAMAR], turnos=Q.TURNOS,
                gravadas=Q.gravadas(cfg, sem["week"]) if admin else [], ok=ok, erro=erro)


def _ctx_reprogramar(cfg, semana: str, linhas: list, problemas: list, itens_json: str, erro: str | None = None) -> dict:
    atual = Q.ler_atual(cfg)
    novo, res = ("", {"saem": [], "saem_outra_semana": []})
    if not atual["erro"] and linhas:
        novo, res = Q.novo_texto_atual(atual["texto"], semana, linhas)
    return {"semana": semana, "linhas": linhas, "problemas": problemas, "itens_json": itens_json, "atual": atual,
            "novo": novo, "res": res, "erro": erro}
