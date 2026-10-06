"""Torre Campo · App: a visão do Nexus sobre o trabalho de campo. Leia o CLAUDE.md desta pasta antes de mexer.

Levi, 05/10/2026: "quero parar de referenciar o Azure e ter uma visão nossa!". Nenhuma tela abre mais o painel do App
(que mora no Azure) nem aponta para ele: todas leem o banco do Nexus (API db_performace) — os livros que o próprio App
grava de hora em hora e o cadastro do Nexus. Aprovação, Ordens e Triagem usam a cópia das regras do painel do App
(`nexus/campo/regras_app.py`); Central de atenção, PT, Rondas, Zeladoria e Ranking são contas NOSSAS
(`nexus/campo/visao.py`). Imagens da ronda e Rotas do dia ficam no placeholder: o dado delas ainda não chega ao banco.
"""
from datetime import datetime, timedelta
from urllib.parse import urlencode, urlsplit

from flask import Response, redirect, render_template, request, session
from markupsafe import Markup, escape

from ...campo import aprovacao as campo_aprovacao
from ...campo import fonte_pg as campo_fonte
from ...campo import ordens as campo_ordens
from ...campo import triagem as campo_triagem
from ...campo import regras_app, visao
from ...campo import decisao_pt, pt_fracttal, ronda_checklist
from ..modelo import Tela, Torre
from .assinatura import bp_assinatura

FONTE_APP = "Livros que o App de Campo grava no banco do Nexus + cadastro do Nexus"

TORRE = Torre(
    id="campo",
    nome="Campo · App",
    ordem=90,
    icone="hard-hat",
    descricao="Visão do Nexus sobre o campo: aprovação, PT, rondas, zeladoria e qualidade.",
    telas=[
        Tela("atencao", "Central de atenção",
             "O que no campo pede ação agora: usina sem ronda, PT parada, ronda sem OS?", FONTE_APP),
        Tela("aprovacao", "Aprovação de OS",
             "Que OS em revisão posso aprovar em lote e qual pede meu olho?",
             "Fila de verificação do Fracttal + notas do App no banco do Nexus"),
        # Levi, 04/10/2026: "crie para PT, ZELADORIA". A PT fica junto da aprovação de OS porque as duas são fila de
        # decisão do supervisor. A "APR e PT" da torre HSEQ é outra pergunta (OS de risco sem APR ou PT assinada).
        Tela("pt", "Permissões de trabalho",
             "Que PT está esperando o De acordo do supervisor, e há quanto tempo?", FONTE_APP),
        Tela("os", "Ordens de serviço", "As OS estão sendo fechadas com evidência?", FONTE_APP),
        Tela("rondas", "Rondas", "Que usina está sem ronda de campo há mais tempo?", FONTE_APP),
        Tela("zeladoria", "Zeladoria",
             "Que serviço de terceiro está parado, sem diária hoje ou com EPI pendente?", FONTE_APP),
        Tela("ranking", "Ranking", "Qual região tem qualidade e cobertura melhores?", FONTE_APP),
        Tela("triagem", "Triagem de qualidade", "O que exige ação hoje na qualidade do fechamento?", FONTE_APP),
        Tela("imagens", "Imagens da ronda", "Que foto de ronda mostra um problema?",
             "Fotos da ronda: ainda só no App; entram quando ele mandar ao banco do Nexus"),
        Tela("rotas", "Rotas do dia", "Qual a melhor ordem de visitas para cada equipe?",
             "Programação do PCM + localização das usinas"),
    ],
)

bp = TORRE.criar_blueprint(__name__)
# as rotas de quem assina a PT moram em /os/_nexus (o cookie do login do Fracttal do OS Creator só vale em /os)
bp.record_once(lambda estado: estado.app.register_blueprint(bp_assinatura))


def _url(**mudar) -> str:
    """O endereço desta tela com os filtros de agora, trocando só o que se pede (None tira o filtro)."""
    args = {k: v for k, v in request.args.items() if v}
    for k, v in mudar.items():
        if v in (None, ""):
            args.pop(k, None)
        else:
            args[k] = v
    return "?" + urlencode(args) if args else "?"


def _dia_curto(iso) -> str:
    s = str(iso or "")
    return f"{s[8:10]}/{s[5:7]}" if len(s) >= 10 else "—"


def _lido(leitura) -> str:
    return datetime.fromtimestamp(leitura.lido_em).strftime("%H:%M")


def _dias(validos, padrao) -> int:
    v = request.args.get("dias")
    return int(v) if v in {str(x) for x in validos} else padrao


def _coleta() -> str:
    """Até quando vão as notas que a fonte serve (o fechamento mais recente do livro do App), "05/10 14:25", no horário
    de Brasília: o App grava em UTC e a tela mostrava 01:23 para um fechamento das 22:23."""
    d = visao._dt(campo_fonte.coleta())
    return d.strftime("%d/%m %H:%M") if d else ""


def _comum(tela_id, leitura, **k):
    return dict(torre=TORRE, tela=TORRE.tela(tela_id), leitura=leitura, d=leitura.dados, lido=_lido(leitura), url=_url,
                dia_curto=_dia_curto, **k)


# ── Central de atenção (visão nossa) ─────────────────────────────────────────────────────────────────────────────
# Três visões (Levi, 05/10/2026): ronda e PT separadas, e as rondas pendentes antes do histórico.
# Só o que está PENDENTE (Levi, 05/10: "na parte de atenção quero só o que for pendente"): as rondas feitas, com o que
# ficou faltando nelas, moram na tela Rondas (aba Registros, filtro de pendência).
VISTAS = (("pendentes", "Rondas pendentes"), ("pt", "Permissões de trabalho"))
STATUS_DA_VISTA = {"pendentes": visao.PENDENTE, "pt": visao.PT_STATUS}


def _status(vista, x) -> str:
    return {"pendentes": x.get("tipo"),
            "pt": "parada" if x.get("parada") else "aguardando"}[vista]


def _idade_min(m) -> str:
    m = int(m or 0)
    if m >= 1440:
        return f"{m // 1440} d {(m % 1440) // 60} h"
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"


ORDEM_DOS_CARTOES = {"pendentes": lambda c: (-c["pendentes"], c["pct_feitas"] or 0, c["equipe"]),
                     "pt": lambda c: (-c["parada"], -c["pts"], c["equipe"])}


@bp.route("/atencao")
def atencao():
    """Duas visões em cada aba (Levi, 05/10: "tem que ter a visão por equipe (CARDS grandes agrupados) e a visão da
    tabela!"): cartões por equipe ou a tabela. Filtro pela região do Brasil; o cartão leva à tabela da equipe."""
    dias = _dias((7, 14, 30), 14)
    leitura = visao.atencao(dias)
    d = leitura.dados
    ids = [v[0] for v in VISTAS]
    vista = request.args.get("vista") if request.args.get("vista") in ids else "pendentes"
    f, regiao, equipe = request.args.get("f", ""), request.args.get("regiao", ""), request.args.get("equipe", "")
    supervisor = request.args.get("supervisor", "")
    modo = "tabela" if request.args.get("modo") == "tabela" or equipe else "equipes"
    q = request.args.get("q", "").strip().lower()
    campos = ("usina", "cidade", "equipe", "obs", "feito_por", "solicitante", "os", "numero", "tarefa")

    def filtra(lista):
        return [x for x in lista if (not regiao or x.get("regiao_br") == regiao)
                and (not equipe or x.get("equipe") == equipe)
                and (not supervisor or x.get("supervisor") == supervisor)
                and (not q or q in " ".join(str(x.get(c) or "") for c in campos).lower())]
    fontes = {"pendentes": filtra(d.get("pendentes") or []),
              "pt": filtra(d.get("pts") or [])}
    base = fontes[vista]
    contagem = {}
    for x in base:
        contagem[_status(vista, x)] = contagem.get(_status(vista, x), 0) + 1
    lista = [x for x in base if not f or _status(vista, x) == f]
    cartoes = visao.por_equipe(filtra(d.get("usinas") or []), fontes["pendentes"], [], fontes["pt"],
                               d.get("times") or {})
    if vista == "pt":
        cartoes = [c for c in cartoes if c["pts"]]
    cartoes.sort(key=ORDEM_DOS_CARTOES[vista])
    return render_template("campo/atencao.html", **_comum(
        "atencao", leitura, dias=dias, vista=vista, vistas=[(v, n, len(fontes[v])) for v, n in VISTAS],
        status=STATUS_DA_VISTA[vista], status_de=lambda x: _status(vista, x), contagem=contagem, total=len(base),
        lista=lista, f=f, regiao=regiao, equipe=equipe, modo=modo, cartoes=cartoes, regioes=visao.REGIOES,
        supervisor=supervisor, supervisores=sorted({x.get("supervisor") for x in (d.get("usinas") or []) + (d.get("pts") or [])
                                                    if x.get("supervisor")}),
        q=request.args.get("q", ""), idade_min=_idade_min))


# ── Permissões de trabalho (visão nossa) ─────────────────────────────────────────────────────────────────────────
SITUACAO_PT = {"aguardando": ("Aguardando", "alerta"), "de_acordo": ("De acordo", "ok"),
               "negada": ("Não autorizada", "critico"), "vencida": ("Vencida", "neutro")}


@bp.route("/pt")
def pt():
    """Duas abas (Levi, 05/10): as PT esperando o De acordo (por equipe ou em tabela, a linha abre o detalhe) e o
    histórico das decididas. Filtro de supervisor; a equipe vem do cartão."""
    leitura = visao.pts()
    d = leitura.dados
    aba = "historico" if request.args.get("aba") == "historico" else "esperando"
    supervisor, equipe = request.args.get("supervisor", ""), request.args.get("equipe", "")
    sit, q = request.args.get("sit", ""), request.args.get("q", "").strip().lower()
    modo = "tabela" if request.args.get("modo") == "tabela" or equipe or aba == "historico" else "equipes"
    dias = _dias((7, 30, 90), 30)
    piso = visao._agora() - timedelta(days=dias)
    campos = ("os", "numero", "tarefa", "usina", "ativo", "codigo", "equipe", "solicitante", "decidida_por")

    def filtra(lista):
        return [p for p in lista if (not supervisor or p.get("supervisor") == supervisor)
                and (not equipe or p.get("equipe") == equipe)
                and (not q or q in " ".join(str(p.get(c) or "") for c in campos).lower())]
    aguardando = filtra(d.get("aguardando") or [])
    historico = [p for p in filtra(d.get("historico") or []) if (p.get("criada") or piso) >= piso]
    contagem = {}
    for p in historico:
        contagem[p["situacao"]] = contagem.get(p["situacao"], 0) + 1
    historico = [p for p in historico if not sit or p.get("situacao") == sit]
    todas = (d.get("aguardando") or []) + (d.get("historico") or [])
    return render_template("campo/pt.html", **_comum(
        "pt", leitura, aba=aba, modo=modo, aguardando=aguardando, historico=historico, contagem=contagem, sit=sit,
        dias=dias, supervisor=supervisor, equipe=equipe, q=request.args.get("q", ""), situacoes=SITUACAO_PT,
        idade_min=_idade_min, cartoes=visao.pts_por_equipe(aguardando, d.get("times") or {}),
        supervisores=sorted({p.get("supervisor") for p in todas if p.get("supervisor")})))


@bp.route("/pt/<numero>/pdf")
def pt_pdf(numero):
    """O PDF da PT como o App anexou no Fracttal no De acordo, com a assinatura do técnico e a de quem aceitou (Levi,
    05/10: "exportar o anexo do PDF ... conforme estava no Azure"). O Nexus baixa e entrega: o link do Fracttal não
    sai para o navegador."""
    p = visao.pt(numero)
    try:
        if not p or not p.get("os"):
            raise pt_fracttal.SemArquivo(f"{numero} não está no livro do App")
        corpo = pt_fracttal.pdf(p["os"], p["numero"])
    except pt_fracttal.SemArquivo as e:
        session["pt_aviso"] = f"Sem PDF: {e}."
        return redirect(url_for_pt(numero))
    except Exception as e:      # noqa: BLE001 — Fracttal fora ou recusando
        session["pt_aviso"] = f"Não consegui buscar o PDF no Fracttal ({type(e).__name__}). Tente de novo em instantes."
        return redirect(url_for_pt(numero))
    return Response(corpo, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{p["numero"]}.pdf"'})


def url_for_pt(numero) -> str:
    from urllib.parse import quote
    return f"/t/campo/pt/{quote(str(numero), safe='')}"


@bp.route("/pt/<numero>")
def pt_aprovar(numero):
    """A aprovação da PT no Nexus: a PT inteira e a decisão, assinada com o login do Fracttal do OS Creator."""
    leitura = visao.pts()
    p = visao.pt(numero) if not leitura.erro else None
    nexus, erro_nexus = None, ""
    if p:
        try:
            nexus = decisao_pt.da_pt(p["numero"])
        except Exception as e:      # noqa: BLE001 — sem o livro de decisões, a tela abre e diz
            erro_nexus = f"Não consegui ler as decisões do Nexus ({type(e).__name__})"
    return render_template("campo/pt_aprovar.html", **_comum(
        "pt", leitura, p=p, numero=numero, nexus=nexus, erro_nexus=erro_nexus, situacoes=SITUACAO_PT,
        idade_min=_idade_min, decisoes=decisao_pt.DECISOES, aviso=session.pop("pt_aviso", ""),
        gravada=request.args.get("gravada") == "1", quando=visao._dt))


# ── Rondas, Zeladoria e Ranking (visão nossa) ────────────────────────────────────────────────────────────────────
ABAS_RONDAS = (("registros", "Registros"), ("sujidade", "Sujidade e vegetação"), ("cobertura", "Cobertura"),
               ("trackers", "Trackers"), ("quem", "Quem ronda"))
FILTROS_SUJIDADE = (("", "Todas"), ("sujidade", "Sujidade alta"), ("vegetacao", "Vegetação alta"),
                    ("sensores", "Sensor sujo"), ("vala", "Vala de drenagem"))
LIMITE_LINHAS = 300


def _duracao(m) -> str:
    """27 min, 1h04: como o painel de rondas mostrava (Levi, 05/10)."""
    if m is None:
        return "—"
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m} min"


def _iniciais(nome) -> str:
    partes = [p for p in str(nome or "").split() if p]
    return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper() if partes else "?"


@bp.route("/rondas")
def rondas():
    """Cobertura, duração e qualidade da ronda (Levi, 05/10: o estilo do painel de rondas, no tema do Nexus): seis
    indicadores do período e quatro abas. Filtros de região do Brasil e de supervisor; Exportar CSV dos registros."""
    dias = _dias((7, 14, 30), 30)
    leitura = visao.rondas()
    d = leitura.dados
    regiao, supervisor = request.args.get("regiao", ""), request.args.get("supervisor", "")
    aba = request.args.get("aba") if request.args.get("aba") in dict(ABAS_RONDAS) else "registros"
    dur, q = request.args.get("dur", ""), request.args.get("q", "").strip().lower()
    pend = request.args.get("pend", "") if request.args.get("pend") in visao.FEITA else ""
    # os indicadores filtram a tabela (Levi, 05/10: "quero que esses botões sejam clicáveis e filtre a tabela")
    ind = request.args.get("ind", "") if request.args.get("ind") in ("hoje", "qualidade", "duracao") else ""
    cob = request.args.get("cob", "") if request.args.get("cob") in ("sem", "atrasadas") else ""

    def filtra(lista):
        return [x for x in lista if (not regiao or x.get("regiao_br") == regiao)
                and (not supervisor or x.get("supervisor") == supervisor)]
    cobertura = filtra(d.get("cobertura") or [])
    painel = visao.painel_rondas(filtra(d.get("todas") or []), cobertura, dias, d.get("hoje") or visao._agora().date().isoformat())
    lim = painel["kpi"]["dur_min"]
    registros = [r for r in painel["periodo"]
                 if (dur != "curta" or (r["dur_min"] is not None and r["dur_min"] < lim))
                 and (dur != "longa" or (r["dur_min"] or 0) > 120)
                 and (not pend or r["pendencia"] == pend)
                 and (ind != "hoje" or r["data"] == painel["hoje"])
                 and (ind != "qualidade" or (r["nota"] is not None and r["nota"] < painel["kpi"]["limite"]))
                 and (not q or q in " ".join(str(r.get(c) or "") for c in ("tecnico", "usina", "equipe", "os")).lower())]
    if ind == "duracao":
        registros.sort(key=lambda r: -(r["dur_min"] if r["dur_min"] is not None else -1))
    if cob == "sem":
        cobertura = [c for c in cobertura if c["dias"] >= dias]
    elif cob == "atrasadas":
        cobertura = [c for c in cobertura if c["dias"] >= visao.DIAS_SEM_RONDA_ALERTA]
    if request.args.get("csv") == "1":
        import csv
        import io
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Data", "Técnico", "Usina", "Equipe", "Estado", "Região", "Tipo", "Início", "Fim", "Duração (min)",
                    "Qualidade (%)", "Veredito", "Trackers apontados", "Trackers respondidos", "OS", "Pendências"])
        # (a coluna Pendências do CSV leva tudo o que o App anotou, inclusive a ronda longa pendente)
        for r in registros:
            w.writerow([r["data"], r["tecnico"], r["usina"], r["equipe"], r["uf"], r["regiao_br"], r["tipo"], r["ini_hm"],
                        r["fim_hm"], r["dur_min"] if r["dur_min"] is not None else "", r["nota"] if r["nota"] is not None else "",
                        r["veredito"][1], r["trk_apontados"], r["trk_respondidos"], r["os"] or "", r["falhas"]])
        return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="rondas-{dias}d.csv"'})
    supervisores = sorted({c.get("supervisor") for c in d.get("cobertura") or [] if c.get("supervisor")})
    suj, suj_estado, suj_f = None, None, request.args.get("sv", "")
    if aba == "sujidade":
        # as respostas vêm das OS de ronda no Fracttal: as aprovadas, relidas em segundo plano, e as em verificação,
        # que já estão na fila da Aprovação de OS (nunca espera o Fracttal)
        campo_aprovacao._pedir_releitura()
        ronda_checklist.pedir_releitura()
        suj = visao.sujidade_vegetacao(filtra(d.get("todas") or []), cobertura, ronda_checklist.respostas(), dias,
                                       d.get("hoje") or visao._agora().date().isoformat())
        suj_estado = ronda_checklist.estado()
        alto = lambda n: n is not None and n > 3
        filtro = {"sujidade": lambda x: alto(x["sujidade"]), "vegetacao": lambda x: alto(x["vegetacao"]),
                  "sensores": lambda x: x["sensores_sujos"],
                  "vala": lambda x: x["vala"] and visao._norm_txt(x["vala"]) not in ("limpa", "ok", "nao se aplica")}.get(suj_f)
        suj["filtradas"] = [x for x in suj["linhas"] if not filtro or filtro(x)]
    return render_template("campo/rondas.html", **_comum(
        "rondas", leitura, dias=dias, regiao=regiao, supervisor=supervisor, aba=aba, abas=ABAS_RONDAS, dur=dur,
        pend=pend, pendencias={k: v for k, v in visao.FEITA.items() if k != "ok"}, ind=ind, cob=cob,
        n_pend={k: sum(1 for r in painel["periodo"] if r["pendencia"] == k) for k in ("sem_os", "incompleta")},
        q=request.args.get("q", ""), k=painel["kpi"], registros=registros, limite=LIMITE_LINHAS, cobertura=cobertura,
        trackers=painel["trackers"], quem=painel["quem"], regioes=visao.REGIOES, supervisores=supervisores,
        duracao=_duracao, iniciais=_iniciais, suj=suj, suj_estado=suj_estado, suj_f=suj_f,
        filtros_sujidade=FILTROS_SUJIDADE))


@bp.route("/zeladoria")
def zeladoria():
    return render_template("campo/zeladoria.html", **_comum("zeladoria", visao.zeladoria()))


@bp.route("/ranking")
def ranking():
    dias = _dias((7, 30, 90), 30)
    return render_template("campo/ranking.html", **_comum("ranking", visao.ranking(dias), dias=dias,
                                                          vista=request.args.get("vista", "")))


# ── Aprovação de OS (a fila e os grupos são os do App, nexus/campo/aprovacao.py) ─────────────────────────────────
GRUPOS = (("completa", "Evidência completa", "ok",
           "Subtarefas respondidas, nota alta, tempo dentro do previsto, nenhuma foto marcada. Não pede análise, "
           "pede decisão."),
          ("olho", "Precisa do seu olho", "alerta",
           "Nota abaixo de 80, tempo muito fora do previsto, foto marcada pelo motor ou já devolvida antes."),
          ("fora_do_app", "Fechadas fora do App", "neutro",
           "Sem evidência para julgar por aqui. Encolhe conforme a equipe adota o App, e é essa a métrica deste "
           "grupo."))


def _cor_espera(dias) -> str:
    n = int(dias or 0)
    return "critico" if n >= 30 else ("alerta" if n >= 7 else "ok")


IDADES = (("0-2", "até 2 dias", 0, 2), ("3-7", "3 a 7 dias", 3, 7), ("8-30", "8 a 30 dias", 8, 30),
          ("31-60", "31 a 60 dias", 31, 60), ("61-", "mais de 60 dias", 61, 10 ** 6))
VISTAS_APROVACAO = (("supervisores", "Por supervisor"), ("tecnicos", "Por técnico"), ("fila", "Fila"))
SEM_CADASTRO = "Sem cadastro"


def _agrupa_fila(linhas, chave) -> list[dict]:
    """Uma linha por supervisor (ou técnico): o tamanho da fila, os três grupos do App, a idade e o uso do App."""
    g = {}
    for x in linhas:
        k = chave(x) or SEM_CADASTRO
        a = g.setdefault(k, {"nome": k, "os": set(), "tarefas": 0, "completa": 0, "olho": 0, "fora_do_app": 0,
                             "aged7": 0, "aged30": 0, "espera_max": 0, "pelo_app": 0, "notas": [], "devolvidas": 0,
                             "equipes": {}, "tecnicos": set(), "supervisores": {}})
        a["os"].add(x["os"])
        a["tarefas"] += 1
        a[x["balde"]] = a.get(x["balde"], 0) + 1
        e = x.get("espera_d") or 0
        a["aged7"] += e >= 7
        a["aged30"] += e >= 30
        a["espera_max"] = max(a["espera_max"], e)
        a["pelo_app"] += bool(x.get("pelo_app"))
        if x.get("pelo_app") and x.get("qualidade") is not None:
            a["notas"].append(int(x["qualidade"]))
        a["devolvidas"] += bool(x.get("foi_devolvida"))
        a["equipes"][x.get("equipe_cad") or SEM_CADASTRO] = a["equipes"].get(x.get("equipe_cad") or SEM_CADASTRO, 0) + 1
        a["supervisores"][x.get("supervisor_cad") or SEM_CADASTRO] = a["supervisores"].get(x.get("supervisor_cad") or SEM_CADASTRO, 0) + 1
        a["tecnicos"].add(x.get("tecnico") or "—")
    for a in g.values():
        a["ordens"] = len(a.pop("os"))
        a["uso_app"] = round(100 * a["pelo_app"] / a["tarefas"]) if a["tarefas"] else None
        a["nota"] = round(sum(a["notas"]) / len(a["notas"])) if a["notas"] else None
        del a["notas"]
        a["equipe"] = max(a["equipes"], key=a["equipes"].get)
        a["supervisor"] = max(a["supervisores"], key=a["supervisores"].get)
        a["n_equipes"], a["n_tecnicos"] = len(a["equipes"]), len(a.pop("tecnicos"))
    return list(g.values())


@bp.route("/aprovacao")
def aprovacao():
    """A fila de verificação do Fracttal para tirar insight (Levi, 05/10: "refaça essa parte de aprovação de OS para
    retirada de bons insights"). Os números e os grupos são os do App (a fila inteira pela `_fila_supervisao`); a
    equipe e o supervisor de cada tarefa vêm do cadastro do Nexus, pela usina do Fracttal (de-para "Fracttal ·
    Classificação 1"). Três visões: por supervisor (quem acumula), por técnico e a fila. Os indicadores e a barra da
    idade filtram a fila."""
    equipe, supervisor = request.args.get("equipe", ""), request.args.get("supervisor", "")
    dias = _dias((7, 30, 60, 90), 30)
    mapa = visao.usinas_do_fracttal()
    opcoes = mapa.dados or {}
    usinas = None
    if equipe and equipe in (opcoes.get("equipes") or {}):
        usinas = set(opcoes["equipes"][equipe])
    if supervisor and supervisor in (opcoes.get("supervisores") or {}):
        usinas = set(opcoes["supervisores"][supervisor]) & (usinas if usinas is not None else set(opcoes["supervisores"][supervisor]))
    leitura = campo_aprovacao.fila_toda({"dias": dias}, usinas)
    d = leitura.dados or {}
    por_nome = opcoes.get("por_nome") or {}
    todas = d.get("linhas") or []
    for x in todas:
        cad = por_nome.get(regras_app._norm(x.get("usina_fx"))) or {}
        x["usina_cad"], x["equipe_cad"] = cad.get("usina") or x.get("usina_fx") or "", cad.get("equipe") or ""
        x["supervisor_cad"], x["regiao_br"] = cad.get("supervisor") or "", cad.get("regiao_br") or ""
    vista = request.args.get("vista") if request.args.get("vista") in dict(VISTAS_APROVACAO) else "supervisores"
    balde = request.args.get("balde") if request.args.get("balde") in ("completa", "olho", "fora_do_app") else ""
    idade = next((i for i in IDADES if i[0] == request.args.get("idade")), None)
    q = request.args.get("q", "").strip().lower()
    if balde or idade or q:
        vista = "fila"
    fila = [x for x in todas if (not balde or x["balde"] == balde)
            and (not idade or idade[2] <= (x.get("espera_d") or 0) <= idade[3])
            and (not q or q in " ".join(str(x.get(c) or "") for c in ("os", "tarefa", "tecnico", "usina_cad")).lower())]
    if request.args.get("csv") == "1":
        import csv
        import io
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["OS", "Tarefa", "Técnico", "Usina", "Equipe", "Supervisor", "Região", "Fechada em", "Espera (dias)",
                    "Nota do registro", "Grupo", "Devolvida"])
        for x in fila:
            w.writerow([x["os"], x.get("tarefa"), x.get("tecnico"), x.get("usina_cad"), x.get("equipe_cad"),
                        x.get("supervisor_cad"), x.get("regiao_br"), str(x.get("fim") or "")[:10], x.get("espera_d"),
                        x.get("qualidade") if x.get("pelo_app") else "", dict((g[0], g[1]) for g in GRUPOS).get(x["balde"]),
                        "sim" if x.get("foi_devolvida") else ""])
        return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="aprovacao-os-{dias}d.csv"'})
    r = d.get("resumo") or {}
    mais_antiga = max(todas, key=lambda x: x.get("espera_d") or 0) if todas else None
    k = {"ordens": r.get("ordens", 0), "tarefas": r.get("tarefas", 0), "baldes": d.get("baldes") or {},
         "aged30": sum(1 for x in todas if (x.get("espera_d") or 0) >= 30),
         "aged30_os": len({x["os"] for x in todas if (x.get("espera_d") or 0) >= 30}),
         "espera_max": r.get("espera_max", 0), "mais_antiga": mais_antiga,
         "uso_app": round(100 * r.get("pelo_app", 0) / r["tarefas"]) if r.get("tarefas") else None}
    idades = [(i, sum(1 for x in todas if i[2] <= (x.get("espera_d") or 0) <= i[3])) for i in IDADES]
    supervisores_g = sorted(_agrupa_fila(todas, lambda x: x.get("supervisor_cad")),
                            key=lambda a: (-a["aged30"], -a["tarefas"], a["nome"]))
    tecnicos_g = sorted(_agrupa_fila(todas, lambda x: x.get("tecnico")), key=lambda a: (-a["tarefas"], a["nome"]))
    return render_template("campo/aprovacao.html", **_comum(
        "aprovacao", leitura, grupos=GRUPOS, nome_grupo={g[0]: (g[1], g[2]) for g in GRUPOS}, balde=balde,
        cor_espera=_cor_espera, coleta=_coleta(), fila=campo_aprovacao.estado(), equipe=equipe, supervisor=supervisor,
        equipes=sorted(opcoes.get("equipes") or {}), supervisores=sorted(opcoes.get("supervisores") or {}),
        mapa_erro=mapa.erro, dias=dias, vista=vista, vistas=VISTAS_APROVACAO, k=k, idades=idades, idade=idade,
        q=request.args.get("q", ""), linhas_fila=fila, limite=LIMITE_LINHAS, por_supervisor=supervisores_g,
        por_tecnico=tecnicos_g, iniciais=_iniciais, motivos=campo_aprovacao.motivos))


@bp.route("/aprovacao/<int:id_wo>/tirar", methods=["POST"])
def aprovacao_tirar(id_wo):
    """Depois de o supervisor aprovar pelo Concluir do OS Creator, a OS sai da fila guardada do Nexus."""
    origem = request.headers.get("Origin")
    if origem and urlsplit(origem).netloc != request.host:
        return "Origem recusada.", 403
    return {"ok": True, "tarefas": campo_aprovacao.tirar_da_fila(id_wo)}


# ── Ordens de serviço (os números e a lista são os do App, nexus/campo/ordens.py) ────────────────────────────────
FAIXAS_OS = (("", "Todas"), ("bad", "Não está bom"), ("warn", "Atenção"), ("ok", "Bom"), ("dev", "Devolvidas"))


def _situacao_os(x) -> tuple[str, str]:
    if x.get("devolvida"):
        return "Devolvida", "critico"
    q = int(x.get("qualidade") or 0)
    return ("Bom", "ok") if q >= 85 else (("Atenção", "alerta") if q >= 70 else ("Não está bom", "critico"))


def _na_faixa(x, faixa) -> bool:
    q = int(x.get("qualidade") or 0)
    return {"": True, "dev": bool(x.get("devolvida")), "bad": q < 70, "warn": 70 <= q < 85, "ok": q >= 85}.get(faixa, True)


@bp.route("/os")
def ordens():
    dias = _dias((7, 30, 90), 7)
    leitura = campo_ordens.painel(dias)
    atual = leitura.dados.get("atual") or {}
    faixa, regiao, q = request.args.get("faixa", ""), request.args.get("regiao", ""), request.args.get("q", "").strip()
    todas = atual.get("linhas") or []
    lista = [x for x in todas if _na_faixa(x, faixa) and (not regiao or x.get("cluster") == regiao)
             and (not q or q.lower() in " ".join(str(x.get(k) or "") for k in ("os", "tarefa", "tecnico", "usina")).lower())]
    return render_template("campo/ordens.html", **_comum(
        "os", leitura, dias=dias, r=atual.get("resumo") or {}, ra=leitura.dados.get("anterior") or {}, lista=lista,
        total=len(todas), faixas=FAIXAS_OS, faixa=faixa, regiao=regiao, q=q, situacao=_situacao_os, coleta=_coleta(),
        regioes=sorted({x.get("cluster") for x in todas if x.get("cluster")})))


# ── Triagem de qualidade (a mesa de triagem do App, nexus/campo/triagem.py) ──────────────────────────────────────
def _rot_item(i) -> str:
    if i.get("tipo") == "os":
        return f"OS {i.get('id')}"
    if i.get("tipo") == "ronda":
        return f"Ronda {_dia_curto(i.get('data') or i.get('quando') or i.get('id'))}"
    if i.get("tipo") in ("usina", "usina_nunca"):
        return i.get("onde") or "Cobertura"
    return i.get("quem") or str(i.get("id") or "")


def _motivo(texto) -> Markup:
    """O motivo vem das regras do App com <b> no número que importa: escapa tudo e devolve só o negrito."""
    return Markup(str(escape(texto or "")).replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>"))


@bp.route("/triagem")
def triagem():
    dias = _dias((7, 30, 90), 30)
    return render_template("campo/triagem.html", **_comum("triagem", campo_triagem.painel(dias), dias=dias,
                                                          rot_item=_rot_item, motivo=_motivo, coleta=_coleta()))
