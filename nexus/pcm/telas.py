"""Telas da programação semanal, penduradas na torre PCM (a torre chama registrar_pcm(bp)).

Etapa 1: Semana e Tarefas e OS mostram a programação que está valendo (a mesma do App de Campo).
Etapa 2: Gerar a semana roda o motor do PCM no Nexus, em sombra, e compara com a semana oficial do PCM.
Etapa 3 (09/10/2026, Levi: "semana que vem já quero full nexus sem falta"): Publicar no App manda a semana gerada para o
repositório do PCM, pelo mesmo caminho do PC do PCM (`publicar.py`): administrador ou setor PCM (`pode_programar`,
16/10/2026), com a tela de confirmação.
Quadro da semana (09/10/2026): o quadro da aba Semana do painel do PCM e a reprogramação de tarefas (`quadro.py`).
"""
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from markupsafe import Markup, escape

from flask import abort, current_app, jsonify, redirect, render_template, request, session

from . import fonte, geracao, gestao as G, historico_banco as HB, insumos as I, motivos as M, motivos_app as MA
from . import observacoes as O
from . import publicar as PB, quadro as Q, semana as S
from ..auth import setor_telas as ST
from ..prefixo import na_raiz

POR_PAGINA = 150
SETOR_PCM = "pcm"
# quem marca e tira o motivo de uma tarefa (16/10/2026, Levi: "PCM no Nexus" e "Supervisores no Nexus"), pelo nome do
# setor sem acento nem caixa; o administrador também
SETORES_MARCAM = ("pcm", "responsaveis ufv")


def pode_programar() -> bool:
    """Publicar a semana no App e gravar a reprogramação do Quadro: administrador ou pessoa do setor PCM (16/10/2026,
    Levi: "mude as configurações para administradores e pessoas do setor de PCM conseguir gerar uma programação
    semanal!"). O setor é o da pessoa do login (Base → Integração Fracttal, `setor_telas.acesso`), pelo nome, sem acento
    nem caixa. Gerar e as observações já eram de quem abre a tela Gerar a semana, que agora é do setor PCM."""
    if session.get("admin"):
        return True
    if not session.get("logado"):
        return False
    try:
        setor = ST.acesso().get("setor")
    except Exception:      # noqa: BLE001 — sem saber o setor, só o administrador
        return False
    return bool(setor) and ST._sem_acento(setor.get("nome")) == SETOR_PCM


def pode_marcar() -> bool:
    """Marcar e tirar o motivo de uma tarefa (16/10/2026): administrador, setor PCM e setor Responsáveis UFV (os
    supervisores). O cadastro dos motivos é de quem `pode_programar` (Levi: "Administrador e setor PCM")."""
    if session.get("admin"):
        return True
    if not session.get("logado"):
        return False
    try:
        setor = ST.acesso().get("setor")
    except Exception:      # noqa: BLE001 — sem saber o setor, só o administrador
        return False
    return bool(setor) and ST._sem_acento(setor.get("nome")) in SETORES_MARCAM


def _usuario() -> dict | None:
    u = session.get("usuario")
    return u if isinstance(u, dict) else None


def _de_outro_site() -> bool:
    from ..torres.moldura import _de_outro_site as regra
    return regra()


def _quem() -> str:
    return (session.get("usuario") or {}).get("email") or "administrador (senha)"
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
    # a lista do backoffice (16/10/2026, Levi: "Lista fixa no Nexus", editável aqui) e o aviso do que se gravou nela
    est_m = M.ler(cfg)
    aviso_m = session.pop("pcm_motivos_aviso", None) or {}
    ok, erro = ok or aviso_m.get("ok"), erro or aviso_m.get("erro")
    return {"conf": geracao.conferir(cfg, semana), "ultimas": geracao.ultimas(cfg), "sel": sel,
            "admin": bool(session.get("admin")), "pode": pode_programar(), "app_sel": app_sel,
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
            "backoffice": M.backoffice(cfg, est_m), "backoffice_erro": est_m.get("erro") or "",
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
        return redirect(na_raiz("/t/pcm/gerar?rodada=") + r["id"], code=303)

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
        return redirect(na_raiz(f"/t/pcm/gerar?semana={semana}&feito=importado"), code=303)

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
        return redirect(na_raiz(f"/t/pcm/gerar?semana={semana}&feito=importado_repo"), code=303)

    @bp.route("/gerar/publicar", methods=["GET", "POST"])
    def gerar_publicar():
        """Publicar no App: a confirmação (GET) e o envio (POST). Administrador ou setor PCM (`pode_programar`): muda a
        semana de todo o campo."""
        cfg = current_app.config
        rid = (request.values.get("rodada") or "").strip()
        st = geracao.ler_status(cfg, rid)
        if st is None:
            abort(404)
        if not pode_programar():
            return render_template("pcm/publicar.html", st=st, negado=True), 403
        motivos = PB.motivos_para_nao_publicar(cfg, rid)
        if request.method == "POST":
            repo_ja_tem = request.form.get("repo_ja_tem") == "1"
            comecou = PB.ja_comecou(st["semana"])
            if (not request.form.get("confirmo") or (repo_ja_tem and not request.form.get("substituir"))
                    or (comecou and not request.form.get("ciente_comecou"))):
                return render_template("pcm/publicar.html", **_ctx_publicar(cfg, st, motivos,
                                       erro="Marque a confirmação para publicar.")), 400
            quem = _quem()
            try:
                PB.publicar(cfg, rid, quem)
            except PB.PublicacaoErro as ex:
                return render_template("pcm/publicar.html", **_ctx_publicar(cfg, st, motivos,
                                       erro=f"Não publiquei: {ex}.")), 400
            except Exception as ex:      # noqa: BLE001 — rede, GitHub fora: a tela diz e nada muda na rodada
                return render_template("pcm/publicar.html", **_ctx_publicar(cfg, st, motivos,
                                       erro=f"O GitHub não respondeu ({type(ex).__name__}): nada foi publicado, ou "
                                            f"só parte; confira o repositório antes de tentar de novo.")), 502
            return redirect(na_raiz(f"/t/pcm/gerar?rodada={rid}&feito=publicada"), code=303)
        return render_template("pcm/publicar.html", **_ctx_publicar(cfg, st, motivos))

    @bp.route("/gerar/observacoes", methods=["POST"])
    def gerar_observacoes():
        cfg = current_app.config
        semana = _semana_do_form()
        if not semana:
            return render_template("pcm/gerar.html", **_ctx_gerar(cfg, erro="Semana inválida. Use o formato 2026-W41.")), 400
        I.salvar_observacoes(geracao.pasta_trabalho(cfg), semana, request.form.get("texto") or "", autor=_quem())
        return redirect(na_raiz(f"/t/pcm/gerar?semana={semana}&feito=observacoes"), code=303)

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
        I.salvar_observacoes(trab, semana, texto, autor=_quem())
        return redirect(na_raiz(f"/t/pcm/gerar?semana={semana}&feito=copiado"), code=303)

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
        sem = _tipo_do_fracttal(current_app.config, sem)
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
        # as opções de cada filtro com os OUTROS aplicados, e quantas tarefas cada uma tem (09/10/2026)
        fac = S.facetas(sem, filtros)

        def _com(lista, campo):
            return [x for x in lista if fac[campo].get(x[0]) or x[0] == filtros.get(campo)]

        opcoes = {
            "equipes": _com([(e, fac["equipe"][e]) for e in sorted(set(fac["equipe"]) | {filtros["equipe"]} - {None})],
                            "equipe"),
            "tipos": _com([(t, fac["tipo"][t]) for t in sorted(set(fac["tipo"]) | {filtros["tipo"]} - {None})], "tipo"),
            "dias": _com([(d, S.NOMES_DIA[d], fac["dia"][d]) for d in S.DIAS], "dia"),
            "situacoes": _com([(v, rot, fac["status"][v]) for v, rot in SITUACOES], "status"),
        }
        return render_template("pcm/tarefas.html", sem=sem, semanas=S.semanas(leitura.dados), linhas=linhas,
                               total=len(todas), total_semana=len(rows), pagina=pagina, paginas=paginas,
                               filtros=filtros, q=a.get("q") or "", opcoes=opcoes, **ctx)

    @bp.route("/gestao")
    def gestao():
        # as tarefas pendentes de uma célula do Plano, para o painel lateral (12/10/2026): o mesmo endereço com
        # pu=<usina>&pc=<coluna>, pedido pelo fetch da própria tela
        if request.args.get("pu") is not None:
            ctx = _ctx_pendentes(current_app.config, request.args)
            if ctx is None:
                return render_template("pcm/_gestao_pendentes_erro.html"), 503
            return render_template("pcm/_gestao_pendentes.html", **ctx)
        return render_template("pcm/gestao.html", **_ctx_gestao(current_app.config, request.args))

    @bp.route("/quadro")
    def quadro():
        ctx = _ctx_quadro(current_app.config, request.args)
        if ctx is None:
            abort(404)
        return render_template("pcm/quadro.html", **ctx)

    @bp.route("/quadro/reprogramar", methods=["POST"])
    def quadro_reprogramar():
        """Grava a fila de reprogramação da página. Administrador ou setor PCM (`pode_programar`). Semana que o Nexus
        gera: nas observações dela no Nexus, direto. Semana em curso: nos ajustes da semana em curso do repositório do
        PCM, depois da confirmação."""
        cfg = current_app.config
        if not pode_programar():
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
        quem = _quem()
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
            return redirect(na_raiz("/t/pcm/quadro?") + urlencode(dict(volta, feito="salvo", n=len(linhas))), code=303)
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
        return redirect(na_raiz("/t/pcm/quadro?") + urlencode(dict(volta, feito="aplicado", n=len(linhas),
                                                           commit=res.get("commit") or "")), code=303)

    # ── os motivos das tarefas e o backoffice (16/10/2026, nexus/pcm/motivos.py) ──────────────────────────────────
    @bp.route("/quadro/motivo", methods=["POST"])
    def quadro_motivo():
        """Marca, troca ou tira o motivo de uma tarefa pela janela da OS. JSON {semana, rodada, os, tarefa, codigo,
        motivo_id, obs, tirar}. A tarefa vem da SEMANA (a página só diz qual): OS e tarefa que a semana não tem não
        gravam. Com a marca feita pela OS (vale em todos os ativos dela), trocar ou tirar mexe nela."""
        cfg = current_app.config
        if not pode_marcar() or _de_outro_site():
            abort(403)
        d = request.get_json(silent=True) or {}
        base = _quadro_semana(cfg, str(d.get("semana") or "").strip() or None, str(d.get("rodada") or "").strip() or None)
        sem = base["sem"]
        if sem is None:
            return jsonify(ok=False, erro="A semana não foi achada: atualize a página."), 404
        linha = _tarefa_da_semana(sem, d)
        if linha is None:
            return jsonify(ok=False, erro="Esta tarefa não está nesta semana: atualize a página."), 400
        tirar = bool(d.get("tirar"))
        if not tirar and not str(d.get("motivo_id") or "").strip():
            return jsonify(ok=False, erro="Escolha o motivo."), 400
        est = M.ler(cfg, forcar=True)
        if est.get("erro"):
            return jsonify(ok=False, erro=f"Não consegui ler os motivos no banco ({est['erro']}): nada foi gravado."), 503
        antes = M.indice(M.vigentes(cfg, est))
        atual = M.motivo_de(antes, linha["os"], linha["codigo"], linha["tarefa"])
        # a marca que vale na linha é a da OS (sem código): trocar ou tirar mexe nela, em todos os ativos
        alvo = dict(linha, codigo="") if atual and not atual["codigo"] else linha
        try:
            r = M.marcar(cfg, alvo, None if tirar else d.get("motivo_id"), "" if tirar else str(d.get("obs") or ""),
                         _usuario(), semana=sem["week"], origem="quadro")
        except M.Recusada as ex:
            return jsonify(ok=False, erro=str(ex)), 400
        arq = _publicar_arquivo(cfg) if r["gravou"] else {"ok": True, "texto": ""}
        marca = r["marca"]
        geral = not alvo["codigo"]
        os_, t_ = linha["os"], M.norm(linha["tarefa"])
        # a que passou a valer na linha: a do ativo vence a da OS
        efetiva = ((antes.get((os_, M.canon(linha["codigo"]), t_)) if linha["codigo"] else None) or marca) if geral             else (marca or antes.get((os_, "", t_)))
        return jsonify(ok=True, gravou=r["gravou"], geral=geral, marca=_marca_curta(marca) if marca else None,
                       efetiva=_marca_curta(efetiva) if efetiva else None, arquivo=arq,
                       efeito=_efeito(efetiva, _destino_quadro(cfg, base)["id"], tirou=tirar and not efetiva))

    @bp.route("/motivos/app", methods=["POST"])
    def motivo_do_app():
        """A marca do técnico pelo App de Campo (16/10/2026, Levi: "Sim, e já vale"; `motivos_app.py`). Sem sessão: vale
        a assinatura (a rota está em `auth.ROTAS_PUBLICAS`). Com a marca da OS valendo na tarefa, trocar ou tirar mexe
        nela, como na janela do Quadro."""
        cfg = current_app.config
        status, d = MA.conferir(cfg, request.headers.get("X-Nexus-Ts"), request.headers.get("X-Nexus-Assinatura"),
                                request.get_data())
        if status != 200:
            return jsonify(ok=False, erro=d), status
        linha = _tarefa_do_app(cfg, d)
        if linha is None:
            return jsonify(ok=False, erro="a tarefa não está na programação nem aberta na Gestão PCM"), 404
        est = M.ler(cfg)
        if est.get("erro"):
            return jsonify(ok=False, erro=f"não consegui ler os motivos no banco ({est['erro']})"), 503
        atual = M.motivo_de(M.indice(M.vigentes(cfg, est)), linha["os"], linha["codigo"], linha["tarefa"])
        alvo = dict(linha, codigo="") if atual and not atual["codigo"] else linha
        try:
            r = M.marcar(cfg, alvo, d["motivo"], "" if d["motivo"] is None else d["obs"],
                         {"nome": d["tecnico_nome"]}, semana=linha.get("semana") or "", origem="app",
                         quem_hmac=d["tecnico_hmac"])
        except M.Recusada as ex:
            return jsonify(ok=False, erro=str(ex)), 400
        arq = _publicar_arquivo(cfg) if r["gravou"] else {"ok": True, "texto": ""}
        marca = r["marca"]
        # o arquivo do robô vai em instantes, fora do pedido (`arquivo_em_dia` fica por compatibilidade: null)
        return jsonify(ok=True, gravou=r["gravou"], marca=_marca_curta(marca) if marca else None,
                       arquivo="em instantes" if r["gravou"] else "sem mudança", arquivo_em_dia=None)

    @bp.route("/fora-da-programacao")
    def fora():
        cfg = current_app.config
        if request.args.get("ver") == "cadastro":
            return render_template("pcm/motivos_cadastro.html", **_ctx_cadastro(cfg))
        return render_template("pcm/fora.html", **_ctx_fora(cfg, request.args))

    @bp.route("/fora-da-programacao/marcar", methods=["POST"])
    def fora_marcar():
        """Do painel, numa tarefa que já tem motivo (`item`): troca o motivo marcado pelo PCM (na própria célula Motivo),
        edita a observação (na própria célula Observação) ou tira o motivo. O motivo que o técnico mandou pelo App não
        se troca aqui (Levi, 16/10/2026: "se o técnico disse tá dito"); a observação e o "Tirar motivo", sim. O
        "Marcar pela OS" saiu ("atrapalha mais que ajuda"): marca-se no Quadro da semana e pelo App."""
        cfg = current_app.config
        if not pode_marcar() or _de_outro_site():
            abort(403)
        f = request.form
        volta = {"motivo": str(f.get("v_motivo"))[:20]} if f.get("v_motivo") else {}
        tirar = f.get("tirar") == "1"
        try:
            iid = (f.get("item") or "").strip()
            if not iid or iid.startswith("_"):
                raise M.Recusada("A tarefa não foi achada: atualize a página.")
            est = M.ler(cfg, forcar=True)
            if est.get("erro"):
                raise M.Recusada(f"Não consegui ler os motivos no banco ({est['erro']}): nada foi gravado.")
            m = M.vigentes(cfg, est).get(iid)
            if not m:
                raise M.Recusada("Essa tarefa não tem mais motivo (alguém mudou agora): atualize a página.")
            alvo = {k: m[k] for k in ("os", "codigo", "tarefa", "usina", "cliente", "tipo", "cluster", "data_prog")}
            pedido = str(f.get("motivo_id") or "").strip()
            motivo_id = pedido or m["motivo_id"]
            if not tirar and m["origem_motivo"] == "app" and str(motivo_id) != str(m["motivo_id"]):
                raise M.Recusada("O motivo que o técnico mandou pelo App não se troca: dá para editar a observação ou "
                                 "tirar o motivo.")
            obs = f.get("obs") if f.get("obs") is not None else m["obs"]
            r = M.marcar(cfg, alvo, None if tirar else motivo_id, "" if tirar else obs, _usuario(), origem="painel")
        except M.Recusada as ex:
            session["pcm_motivos_aviso"] = {"erro": str(ex)}
        else:
            arq = _publicar_arquivo(cfg) if r["gravou"] else {"ok": True, "texto": ""}
            nova = r["marca"]
            ok = ("Nada mudou." if not r["gravou"] else
                  f"Motivo tirado da OS {alvo['os']}." if tirar else
                  f"OS {alvo['os']}: {nova['motivo']}." if nova and nova["motivo_id"] != m["motivo_id"] else
                  f"OS {alvo['os']}: observação salva.")
            session["pcm_motivos_aviso"] = {"ok": " ".join(x for x in (ok, arq["texto"] if arq["ok"] else "") if x),
                                            "erro": "" if arq["ok"] else arq["texto"]}
        return redirect(na_raiz("/t/pcm/fora-da-programacao") + ("?" + urlencode(volta) if volta else ""), code=303)

    @bp.route("/fora-da-programacao/cadastro", methods=["POST"])
    def fora_cadastro():
        """O cadastro dos motivos: incluir, editar (nome, descrição, se tira da programação) e tirar. Administrador e
        setor PCM (Levi, 16/10/2026: "Administrador e setor PCM")."""
        cfg = current_app.config
        if not pode_programar() or _de_outro_site():
            abort(403)
        f = request.form
        acao = f.get("acao") or ""
        try:
            r = M.cadastro(cfg, acao, _usuario(), motivo_id=f.get("motivo_id"), nome=f.get("nome"),
                           descricao=f.get("descricao"), tira=f.get("tira") == "1")
        except M.Recusada as ex:
            session["pcm_motivos_aviso"] = {"erro": str(ex)}
        else:
            mudou = acao != "editar" or r.get("mudou")
            arq = _publicar_arquivo(cfg) if mudou else {"ok": True, "texto": ""}
            ok = {"criar": f"Motivo {r['nome']} incluído.", "excluir": f"Motivo {r['nome']} tirado do cadastro.",
                  "editar": f"Motivo {r['nome']} salvo." if mudou else "Nada mudou."}.get(acao, "Salvo.")
            session["pcm_motivos_aviso"] = {"ok": " ".join(x for x in (ok, arq["texto"] if arq["ok"] else "") if x),
                                            "erro": "" if arq["ok"] else arq["texto"]}
        return redirect(na_raiz("/t/pcm/fora-da-programacao?ver=cadastro"), code=303)

    @bp.route("/fora-da-programacao/publicar", methods=["POST"])
    def fora_publicar():
        """Manda de novo o arquivo do robô (quando a última marca não chegou ao repositório do PCM)."""
        cfg = current_app.config
        if not pode_marcar() or _de_outro_site():
            abort(403)
        arq = _publicar_arquivo(cfg, agora=True)
        session["pcm_motivos_aviso"] = ({"ok": arq["texto"] or "O arquivo do robô já estava em dia."} if arq["ok"]
                                        else {"erro": arq["texto"]})
        return redirect(na_raiz("/t/pcm/fora-da-programacao"), code=303)

    @bp.route("/gerar/backoffice", methods=["POST"])
    def gerar_backoffice():
        """A lista do backoffice (Gerar a semana, bloco 1): pôr ou tirar um nome. Quem abre a tela Gerar mexe nela,
        como nas observações."""
        cfg = current_app.config
        if _de_outro_site():
            abort(403)
        semana = _semana_do_form() or ""
        f = request.form
        try:
            r = M.backoffice_definir(cfg, f.get("nome"), f.get("acao") == "por", _usuario())
        except M.Recusada as ex:
            session["pcm_motivos_aviso"] = {"erro": str(ex)}
        else:
            arq = _publicar_arquivo(cfg) if r["gravou"] else {"ok": True, "texto": ""}
            ok = (f"{r['nome']} {'entrou na' if f.get('acao') == 'por' else 'saiu da'} lista do backoffice."
                  if r["gravou"] else "Nada mudou.")
            session["pcm_motivos_aviso"] = {"ok": " ".join(x for x in (ok, arq["texto"] if arq["ok"] else "") if x),
                                            "erro": "" if arq["ok"] else arq["texto"]}
        return redirect(na_raiz("/t/pcm/gerar?") + urlencode({"semana": semana}) + "#backoffice", code=303)


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
    """A planilha da Gerencial aberta com a senha do .env (só em memória: nunca vai para o banco). Para a página, só a
    Fila do Relatório executivo (o `manut` e o `bd`, nexus/pcm/relatorio_exec, 14/10/2026), porque o JS do painel faz a
    conta no navegador, como o painel faz com a senha do login de administrador; e só para quem a tela deixa entrar."""
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


def _ctx_pendentes(cfg, args) -> dict | None:
    """As tarefas pendentes de UMA célula do Plano (Levi, 12/10/2026: "Na versão antiga ao clicar em cima do % do que
    tem pendente aparecia as tarefas pendentes"): a mesma leitura, os mesmos filtros de cima (a cópia guardada da tela)
    e os mesmos recortes da matriz. `pu` = a usina; `pc` = a coluna (sigla, CORR ou mês) ou "*" (a coluna Pendentes).
    Coluna que a matriz não tem = 404. None = o arquivo não está legível."""
    leitura = fonte.ler_gestao(cfg)
    d = leitura.dados
    if d is None:
        return None
    meses = G.meses(G.hoje())
    o = G.opcoes(args, meses)
    versao = d.get("dataHash") or d.get("geradoEm")
    if _G_CACHE.get("versao") != versao:
        _G_CACHE.clear()
        _G_CACHE["versao"] = versao
    escopo = _guardado(("escopo", versao), lambda: G.escopo(d.get("tarefas")))
    topo = {k: str(args.get(k) or "")[:160] for k in G.TOPO}
    tarefas = _guardado(("topo", versao, *topo.values()), lambda: G.filtrar_topo(escopo, **topo))
    col = str(args.get("pc") or "")[:12]
    if col != "*" and col not in G.colunas(o, meses):
        abort(404)
    p = G.pendentes(tarefas, o, meses, str(args.get("pu") or "")[:200], col)
    rot = "Geral" if col == "*" else G.rot_col(col)
    return {"p": p, "rot_col": rot, "data_curta": G.data_curta}


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
    topo = {k: str(args.get(k) or "")[:160] for k in G.TOPO}
    # as opções de cada filtro de cima com os OUTROS aplicados (09/10/2026: "os filtros tem que se auto filtrar")
    escolhas = _guardado(("escolhas", versao, *topo.values()), lambda: G.escolhas_topo(escopo, topo))
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
                   faixa=G.faixa, tom=G.tom)
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


def _tipo_do_fracttal(cfg, sem: dict) -> dict:
    """O "Zeladoria" das semanas geradas antes do motor corrigido (pelo nome da tarefa) volta ao tipo do Fracttal
    (`quadro.tipo_do_fracttal`), no Quadro e em Tarefas e OS. As tarefas da Gestão PCM só são lidas quando a semana tem
    zeladoria; fora do ar, a tela abre com o tipo da planilha."""
    if not Q.tem_zeladoria(sem):
        return sem
    try:
        return Q.tipo_do_fracttal(sem, (fonte.ler_gestao(cfg).dados or {}).get("tarefas"))[0]
    except Exception:      # noqa: BLE001 — a Gestão PCM fora do ar não derruba a tela
        return sem


def _ctx_quadro(cfg, args, erro: str | None = None) -> dict | None:
    pedida = (args.get("semana") or "").strip() or None
    base = _quadro_semana(cfg, pedida, (args.get("rodada") or "").strip() or None)
    ctx = _contexto_fonte(base["leitura"])
    sem = base["sem"]
    if sem is None:
        if pedida and base["leitura"].dados is not None:
            return None
        return dict(ctx, sem=None, chips=[], erro=erro, ok=None)
    sem = _tipo_do_fracttal(cfg, sem)
    filtros = {k: str(args.get(k) or "").strip()[:160] for k in Q.FILTROS}
    filtro_gestor = False
    if not pedida and not any(filtros.values()) and not args.get("rodada"):
        g = _gestor_da_sessao(sem)
        if g:
            filtros["resp"], filtro_gestor = g, True
    todos = args.get("todos") == "1"
    q = Q.montar(sem, base["publicadas"], filtros, todos=todos, mostrar_pendentes=True if args.get("pend") == "1" else None)
    mot = _motivos_no_quadro(cfg, q)
    dest = _destino_quadro(cfg, base)
    pode = pode_programar()
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
    dados = {"semana": sem["week"], "rodada": base["rodada"] or "", "destino": dest["id"], "pode": pode,
             "dias": [[d, Q.NOMES_DIA[d]] for d in Q.DIAS_REPROGRAMAR], "turnos": list(Q.TURNOS), "itens": q["itens"],
             "oss": q["oss"],
             "feito": feito in ("salvo", "aplicado"),
             # os motivos (16/10/2026): o cadastro para a janela e quem marca (PCM, Responsáveis UFV, administrador)
             "motivos": mot["lista"], "pode_marcar": pode_marcar() and not mot["erro"],
             "url_motivo": na_raiz("/t/pcm/quadro/motivo")}
    # para onde vai a reprogramação desta semana, dito com o nome do lugar (Levi, 09/10/2026, sobre a frase anterior,
    # "vira linha de observação, que só o PCM grava, e vale onde a fila diz": "Onde o PCM tem essa informação?")
    ctx["fonte_frase"] = {
        "atual": "Reprogramar não muda o quadro na hora: o PCM grava a fila nos ajustes da semana em curso (o "
                 "Observacoes_Semana_Atual.txt do repositório do PCM) e o robô do PCM aplica na rodada seguinte. O que já "
                 "foi gravado fica em \"Já gravadas para esta semana\", no fim da página.",
        "nexus": "Reprogramar não muda o quadro na hora: o PCM grava a fila nas observações desta semana no Nexus (Gerar "
                 "a semana, bloco 2), que valem na próxima geração. O que já foi gravado fica em \"Já gravadas para esta "
                 "semana\", no fim da página.",
        "copiar": "Esta semana foi gerada no PC do PCM: a fila de reprogramação é para copiar e colar no painel do PCM.",
    }.get(dest["id"], "A semana já acabou: aqui é só para consulta.")
    ctx["ok_link"] = f"/t/pcm/gerar?semana={sem['week']}" if feito == "salvo" else ""
    return dict(ctx, sem=sem, q=q, filtros=filtros, filtro_gestor=filtro_gestor, destino=dest, pode=pode,
                rodada=base["rodada"], chips=_chips_quadro(base, extra), origem_txt=origem_txt, dados=dados,
                tem_filtro=any(filtros.values()),
                url_limpar="?" + urlencode({k: v for k, v in sel_qs.items() if k in ("semana", "rodada")}),
                url_todos="?" + urlencode(dict(sel_qs, todos="1")),
                url_pendentes="?" + urlencode(dict(sel_qs, pend="1", **({"todos": "1"} if todos else {}))) + "#pendentes",
                abrir_pendentes=args.get("pend") == "1" or (any(filtros.values()) and q["pend_sel"] <= 80),
                dias_rp=[(d, Q.NOMES_DIA[d]) for d in Q.DIAS_REPROGRAMAR], turnos=Q.TURNOS,
                gravadas=Q.gravadas(cfg, sem["week"]), ok=ok, erro=erro, motivos_erro=mot["erro"])


def _ctx_reprogramar(cfg, semana: str, linhas: list, problemas: list, itens_json: str, erro: str | None = None) -> dict:
    atual = Q.ler_atual(cfg)
    novo, res = ("", {"saem": [], "saem_outra_semana": []})
    if not atual["erro"] and linhas:
        novo, res = Q.novo_texto_atual(atual["texto"], semana, linhas)
    return {"semana": semana, "linhas": linhas, "problemas": problemas, "itens_json": itens_json, "atual": atual,
            "novo": novo, "res": res, "erro": erro}


# ── os motivos das tarefas e o backoffice (16/10/2026, nexus/pcm/motivos.py) ──────────────────────────────────────
def _tarefa_da_semana(sem: dict, d: dict) -> dict | None:
    """A tarefa que a página apontou, tirada da SEMANA: a linha (agenda ou pendentes) com a mesma OS, a mesma tarefa e
    o mesmo código do ativo (a pendente do App ainda vem sem código). None se a semana não a tem."""
    os_s = M.os_de(d.get("os"))
    tarefa = str(d.get("tarefa") or "")
    cod = M.canon(d.get("codigo"))
    if not os_s.isdigit() or not tarefa:
        return None
    for r in (sem.get("rows") or []) + (sem.get("pendentes") or []):
        if M.os_de(r.get("os_id")) != os_s or str(r.get("tarefa") or "") != tarefa or M.canon(r.get("codigo")) != cod:
            continue
        d = Q.dia_de(r.get("dia"))
        data_prog = (HB.segunda(sem["week"]) + timedelta(days=Q.DIAS.index(d))).isoformat()             if d in Q.DIAS and sem.get("week") else ""
        return {"os": os_s, "codigo": str(r.get("codigo") or "").strip(), "tarefa": tarefa,
                "usina": str(r.get("usina") or "").strip(), "cliente": str(r.get("cliente") or "").strip(),
                "tipo": str(r.get("tipo") or "").strip(), "cluster": str(r.get("cluster") or "").strip(),
                "data_prog": data_prog}
    return None


def _tarefa_do_app(cfg, d: dict) -> dict | None:
    """A tarefa que o App apontou: a linha da programação publicada (a semana ativa primeiro; agenda ou pendentes), pela
    OS, pelo nome e pelo código como o motor compara (sem acento, caixa e espaço a mais); senão, a tarefa ABERTA da
    Gestão PCM com a OS e o nome (a OS avulsa do App), com o código que o App mandou. None se não existir."""
    os_s, t, cod = d["os"], M.norm(d["tarefa"]), M.canon(d.get("codigo"))
    dados = fonte.ler(cfg).dados or {}
    semanas = sorted((s for s in dados.get("semanas") or [] if isinstance(s, dict)),
                     key=lambda s: s.get("week") != dados.get("semana_ativa"))
    for s in semanas:
        for r in (s.get("rows") or []) + (s.get("pendentes") or []):
            if M.os_de(r.get("os_id")) == os_s and M.norm(r.get("tarefa")) == t and M.canon(r.get("codigo")) == cod:
                linha = _tarefa_da_semana(s, {"os": os_s, "tarefa": str(r.get("tarefa") or ""),
                                              "codigo": str(r.get("codigo") or "")})
                if linha:
                    return dict(linha, semana=str(s.get("week") or ""))
    g = _gestao_tarefas(cfg)
    ts = [x for x in (g or {}).get("por_os", {}).get(os_s, [])
          if M.norm(x.get("tarefa")) == t and not _finalizada(x.get("estado"))]
    if not ts:
        return None
    x = ts[0]
    return {"os": os_s, "codigo": str(d.get("codigo") or "").strip(), "tarefa": str(x.get("tarefa") or "").strip(),
            "usina": str(x.get("usina") or "").strip(), "cliente": str(x.get("cliente") or "").strip(),
            "tipo": str(x.get("tipo") or "").strip(), "cluster": str(x.get("cluster") or "").strip(), "data_prog": ""}


_GT: dict = {}


def _finalizada(estado) -> bool:
    return M.norm(estado) == "finalizada"


def _gestao_tarefas(cfg) -> dict | None:
    """As tarefas da Gestão PCM (o gestao_pcm.json que o robô do PCM regrava) por OS e por (OS, nome): o painel tira a
    tarefa FINALIZADA (Levi, 16/10/2026: "Sai do painel sozinha") e marca pelo número da OS. None quando a Gestão PCM não
    abre: o painel mostra todas e diz."""
    try:
        d = fonte.ler_gestao(cfg).dados or {}
    except Exception:      # noqa: BLE001 — fora do ar: o painel segue sem ela
        return None
    tarefas = d.get("tarefas")
    if not isinstance(tarefas, list):
        return None
    chave = (str(d.get("dataHash") or ""), len(tarefas), id(tarefas))   # a cópia da fonte é trocada inteira
    g = _GT.get("x")
    if g and g["chave"] == chave:
        return g
    por_os: dict[str, list[dict]] = {}
    por_tarefa: dict[tuple[str, str], list[str]] = {}
    for t in tarefas:
        if not isinstance(t, dict):
            continue
        o = M.os_de(t.get("os"))
        por_os.setdefault(o, []).append(t)
        por_tarefa.setdefault((o, M.norm(t.get("tarefa"))), []).append(str(t.get("estado") or ""))
    g = {"chave": chave, "por_os": por_os, "por_tarefa": por_tarefa}
    _GT["x"] = g
    return g


def _marca_curta(m: dict) -> dict:
    d = M._brt(m["desde"])
    return {"item": m["item_id"], "id": m["motivo_id"], "n": m["motivo"], "tira": m["tira"],
            "desde": d.strftime("%d/%m/%Y") if d else "", "quem": m.get("quem_motivo") or m["quem"], "obs": m["obs"],
            "geral": not m["codigo"], "app": m.get("origem_motivo", m.get("origem")) == "app"}


def _efeito(marca: dict | None, destino: str | None, tirou: bool = False) -> str:
    """O que a marca faz na programação, dito na hora (a janela e o aviso)."""
    if tirou or not marca:
        return "Sem motivo: a tarefa volta a ser programada na próxima geração da semana."
    if not marca["tira"]:
        return "A tarefa continua na programação; o motivo aparece no Quadro e no App de Campo."
    if destino == "atual":
        return ("Sai da programação: o robô do PCM tira a tarefa da semana em curso na próxima rodada (até 30 minutos) e "
                "não a inclui de novo enquanto o motivo valer.")
    if destino == "nexus":
        return "Sai da programação: a próxima geração desta semana não a programa (gere de novo em Gerar a semana)."
    return "Sai da programação a partir da próxima geração da semana."


def _publicar_arquivo(cfg, agora: bool = False) -> dict:
    """Manda o estado novo ao repositório do PCM (o robô lê de lá). Depois de uma marca, fora do pedido
    (`motivos.publicar_depois`, 16/10/2026: com o GitHub dentro do pedido, o Justificar do App passava de 20 s); o botão
    "Mandar o arquivo de novo" (`agora`) espera e diz o resultado. A marca já está no banco: falhar aqui não desfaz
    nada; a tela diz e o painel Fora da programação tem o botão de mandar de novo."""
    if not agora:
        M.publicar_depois(cfg)
        return {"ok": True, "texto": ""}
    try:
        r = M.publicar_arquivo(cfg)
    except Exception as ex:      # noqa: BLE001 — sem token, GitHub fora: a tela diz
        msg = str(ex) if isinstance(ex, (M.Recusada, PB.PublicacaoErro)) else f"o GitHub não respondeu ({type(ex).__name__})"
        return {"ok": False, "texto": f"Gravado no Nexus, mas o arquivo do robô do PCM não foi atualizado: {msg}. No "
                                      "painel Fora da programação há o botão para mandar de novo."}
    finally:
        M.esquecer_estado_no_repositorio()
    return {"ok": True, "texto": "" if r["igual"] else f"Arquivo do robô do PCM atualizado (commit {r['commit'][:7]})."}


def _motivos_no_quadro(cfg, q: dict) -> dict:
    """O motivo de cada tarefa do quadro (a janela da OS, o selo do cartão e da pendente) e o cadastro para marcar. O
    banco fora do ar não derruba o quadro: sai sem os motivos, com o aviso."""
    est = M.ler(cfg)
    try:
        idx = M.indice(M.vigentes(cfg, est))
    except Exception:      # noqa: BLE001
        idx = {}
    for it in q["itens"]:
        m = M.motivo_de(idx, it.get("os"), it.get("cod"), it.get("t"))
        if m:
            it["mp"] = _marca_curta(m)
    for k in [k for c in q["colunas"] for k in c["cartoes"]] + [p for g in q["pendentes"] for p in g["itens"]]:
        mp = q["itens"][k["i"]].get("mp")
        if mp:
            k["mp"], k["mpt"] = mp["n"], mp["tira"]
    return {"lista": [[m["id"], m["nome"], m["tira"]] for m in M.ativos(est)], "erro": est.get("erro") or ""}


def _num_arg(v) -> int | None:
    s = str(v or "").strip()
    return int(s) if s.isdigit() and int(s) > 0 else None


_NUM_OS = re.compile(r"(?<!\d)(\d{5,6})(?!\d)")      # o nº de uma OS no texto: "OS16290", "OS 16290", "16290"


def _nome_da_usina(nome) -> str:
    """'Thopen - Parelhas 1 - RN' -> 'Parelhas 1' (Levi, 16/10/2026: "Em usina só o nome da usina, sem o nome do cliente
    no início"): o meio do nome do Fracttal (cliente - usina - UF). Fora desse formato, como veio."""
    t = str(nome or "").strip()
    p = [x.strip() for x in re.split(r"\s+-\s*|\s*-\s+", t) if x.strip()]
    return " - ".join(p[1:-1]) if len(p) >= 3 else t


def _botao_os(n: str, g: dict | None) -> str:
    """O nº da OS como botão que abre o card da OS do OS Creator por cima da tela (Levi, 16/10/2026: "quando a pessoa
    clicar vai sobrepor na tela a mesma tela que aparece quando você clica na OS no histórico de OS do OS Creator Web").
    Com a OS na Gestão PCM vão o id do Fracttal e o status do card (como a Gestão PCM abre); sem ela, só o número."""
    ts = (g or {}).get("por_os", {}).get(n) or []
    wid = next((str(t.get("idWO")) for t in ts if t.get("idWO")), "")
    st = next((str(t.get("osStatus") or "") for t in ts if t.get("osStatus")), "")
    st = G.STATUS_DO_CARD.get(G.sem_acento(st).strip(), st)
    return (f'<button type="button" class="fp-os-n" data-os="{escape(n)}"'
            + (f' data-wid="{escape(wid)}"' if wid else "") + (f' data-status="{escape(st)}"' if st else "")
            + f' title="Abrir a OS {escape(n)}">{escape(n)}</button>')


def _com_os(texto, g: dict | None) -> Markup:
    """O texto (a observação) com cada número de 5 a 6 dígitos como botão da OS (`_botao_os`). O texto é escapado antes:
    só o número vira botão."""
    return Markup(_NUM_OS.sub(lambda x: _botao_os(x.group(1), g), str(escape(texto or ""))))


def _ctx_fora(cfg, args) -> dict:
    """O painel Fora da programação: as tarefas com um motivo que tira da programação e TODA justificativa que veio do
    App, de qualquer motivo, menos as finalizadas no Fracttal; o filtro é só o Motivo (Levi, 16/10/2026). A justificativa
    é do App pelo motivo (`origem_motivo`): a observação editada pelo PCM não a tira daqui nem troca quem marcou."""
    est = M.ler(cfg)
    vig = M.vigentes(cfg, est)
    ilegiveis = vig.pop("_ilegiveis", 0)
    motivos = M.ativos(est)
    g = _gestao_tarefas(cfg)
    hoje = Q.hoje()
    linhas, finalizadas = [], 0
    for m in vig.values():
        # a marca do PCM só aparece se tira; a do App, sempre (16/10/2026: as 10 justificativas "Prioridade" do técnico,
        # que não tira, estavam gravadas e não apareciam em lugar nenhum; Levi escolheu mostrá-las aqui)
        if not (m["tira"] or m["origem_motivo"] == "app"):
            continue
        estados = (g or {}).get("por_tarefa", {}).get((m["os"], M.norm(m["tarefa"])))
        if estados and all(_finalizada(e) for e in estados):
            finalizadas += 1
            continue
        d = M._brt(m["desde"])
        # a usina vem da linha marcada; sem ela (a pendente do App não traz), da Gestão PCM pela OS
        usina = m["usina"] or next((str(t.get("usina") or "") for t in (g or {}).get("por_os", {}).get(m["os"], [])), "")
        # quantas vezes a tarefa foi justificada (uma por dia e motivo), a do ativo e a da tarefa em todos os ativos da OS
        hist = [dict(h, quando_txt=M._brt(h["quando"]).strftime("%d/%m/%Y %H:%M") if M._brt(h["quando"]) else "",
                     do_app=h["origem"] == "app", obs_html=_com_os(h["obs"], g))
                for h in M.historico(cfg, est, {m["item_id"], M.item_id(m["os"], "", m["tarefa"])})]
        linhas.append(dict(m, usina=usina, usina_nome=_nome_da_usina(usina), vezes=len(hist), historico=hist,
                           desde_txt=d.strftime("%d/%m/%Y %H:%M") if d else "", os_html=Markup(_botao_os(m["os"], g)),
                           obs_html=_com_os(m["obs"], g),
                           dias=max(0, (hoje - d.date()).days) if d else None, do_app=m["origem_motivo"] == "app",
                           quem_mostra=m["quem_motivo"] or m["quem"],
                           estado_fr=" · ".join(sorted({e for e in estados or [] if e})),
                           fora_da_gestao=g is not None and not estados))
    conta = Counter(l["motivo_id"] for l in linhas)
    sel = _num_arg(args.get("motivo"))
    mostradas = sorted((l for l in linhas if not sel or l["motivo_id"] == sel),
                       key=lambda l: (l["desde"], int(l["os"]) if l["os"].isdigit() else 0, M.norm(l["tarefa"])))
    opcoes = [(m, conta.get(m["id"], 0)) for m in motivos if conta.get(m["id"]) or m["id"] == sel]
    aviso = session.pop("pcm_motivos_aviso", None) or {}
    return {"linhas": mostradas, "total": len(linhas), "motivos": motivos, "opcoes": opcoes, "sel": sel,
            "n_tira": sum(1 for l in mostradas if l["tira"]),
            "finalizadas": finalizadas, "ilegiveis": ilegiveis, "erro_banco": est.get("erro") or "",
            "gestao_ok": g is not None, "pode": pode_marcar(), "pode_cadastro": pode_programar(),
            "repo": M.estado_no_repositorio(cfg, est),
            "ok": aviso.get("ok"), "erro": aviso.get("erro")}


def _ctx_cadastro(cfg) -> dict:
    """O cadastro dos motivos, com quantas tarefas estão com cada um agora."""
    est = M.ler(cfg)
    vig = M.vigentes(cfg, est)
    vig.pop("_ilegiveis", None)
    conta = Counter(m["motivo_id"] for m in vig.values())
    aviso = session.pop("pcm_motivos_aviso", None) or {}
    return {"motivos": [dict(m, n=conta.get(m["id"], 0)) for m in M.ativos(est)], "inicial": est.get("inicial"),
            "erro_banco": est.get("erro") or "", "pode": pode_programar(), "ok": aviso.get("ok"),
            "erro": aviso.get("erro")}
