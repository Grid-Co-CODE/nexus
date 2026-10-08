"""Torre Campo · App: a visão do Nexus sobre o trabalho de campo. Leia o CLAUDE.md desta pasta antes de mexer.

Levi, 05/10/2026: "quero parar de referenciar o Azure e ter uma visão nossa!". Nenhuma tela abre mais o painel do App
(que mora no Azure) nem aponta para ele: todas leem o banco do Nexus (API db_performace) — os livros que o próprio App
grava de hora em hora e o cadastro do Nexus. Aprovação e Triagem usam a cópia das regras do painel do App
(`nexus/campo/regras_app.py`); Central de atenção, PT, Rondas e Zeladoria são contas NOSSAS (`nexus/campo/visao.py`).
Rotas do dia fica no placeholder: o dado dela ainda não chega ao banco. Ordens de serviço, Imagens da ronda e Ranking
saíram em 08/10/2026 (Levi: "ordens de serviço e imagens da ronda e ranking são redundantes"); o endereço antigo leva
à Central.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from flask import Response, redirect, render_template, request, session
from markupsafe import Markup, escape
from werkzeug.datastructures import ImmutableMultiDict

from ...campo import aprovacao as campo_aprovacao
from ...campo import fonte_pg as campo_fonte
from ...campo import triagem as campo_triagem
from ...campo import regras_app, visao
from ...campo import decisao_pt, pt_fracttal, ronda_avulsa, ronda_checklist, ronda_fotos
from ..modelo import Tela, Torre
from .aprovar_os import bp_aprovar_os, pode_na_tela
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
             "Que OS esperam a aprovação de cada supervisor, qual dá para aprovar já e qual pede meu olho?",
             "Fila de verificação do Fracttal + notas do App no banco do Nexus"),
        # Levi, 04/10/2026: "crie para PT, ZELADORIA". A PT fica junto da aprovação de OS porque as duas são fila de
        # decisão do supervisor. A "APR e PT" da torre HSEQ é outra pergunta (OS de risco sem APR ou PT assinada).
        Tela("pt", "Permissões de trabalho",
             "Que PT está esperando o De acordo do supervisor, e há quanto tempo?", FONTE_APP),
        # Ordens de serviço, Ranking e Imagens da ronda saíram em 08/10/2026 (Levi: "ordens de serviço e imagens da
        # ronda e ranking são redundantes"): a qualidade do fechamento está na Aprovação e na Triagem, a comparação
        # por região e equipe no Painel das Rondas e as fotos no histórico da usina. O endereço antigo leva à Central
        # (TELAS_QUE_SAIRAM).
        Tela("rondas", "Rondas", "Que usina está sem ronda de campo há mais tempo?", FONTE_APP),
        Tela("zeladoria", "Zeladoria",
             "Que serviço de terceiro está parado, sem diária hoje ou com EPI pendente?", FONTE_APP),
        Tela("triagem", "Triagem de qualidade", "O que exige ação hoje na qualidade do fechamento?", FONTE_APP),
        Tela("rotas", "Rotas do dia", "Qual a melhor ordem de visitas para cada equipe?",
             "Programação do PCM + localização das usinas"),
    ],
)

bp = TORRE.criar_blueprint(__name__)
# as rotas de quem assina a PT moram em /os/_nexus (o cookie do login do Fracttal do OS Creator só vale em /os)
bp.record_once(lambda estado: estado.app.register_blueprint(bp_assinatura))
# e o portão de quem aprova a OS também (Levi, 08/10/2026: "só o supervisor ou ADM consegue aprovar a OS logando pelo
# Fracttal"), pelo mesmo motivo: é ali que o servidor sabe quem entrou no Fracttal
bp.record_once(lambda estado: estado.app.register_blueprint(bp_aprovar_os))

# Ordens de serviço, Ranking e Imagens da ronda saíram do menu em 08/10/2026: quem guardou o endereço cai na Central
TELAS_QUE_SAIRAM = ("os", "ranking", "imagens")


def _tela_que_saiu():
    return redirect("/t/campo/atencao")


for _id in TELAS_QUE_SAIRAM:
    bp.add_url_rule(f"/{_id}", f"saiu_{_id}", _tela_que_saiu)


TODOS = "*"
_BRT = timezone(timedelta(hours=-3))


def _supervisor() -> str:
    """O filtro de supervisor: o que a pessoa escolheu; sem escolha, o dela, se ela entrou pelo Fracttal e é
    supervisor no cadastro (Levi, 06/10: "Quando um supervisor logar, o filtro supervisor já fica para a pessoa
    automaticamente, mas ela pode mudar o filtro se quiser"). "Todos" é uma escolha também: vai como "*"."""
    v = request.args.get("supervisor")
    if v is None:
        return session.get("supervisor_padrao", "")
    return "" if v == TODOS else v


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
# Por supervisor (Levi, 08/10/2026: "além de por equipe e tabela, adicione mais um botão (por supervisor)"): a mesma
# ordem dos cartões de equipe; o "sem supervisor no cadastro" fica sempre por último, num cartão próprio
ORDEM_DOS_SUPERVISORES = {
    "pendentes": lambda s: (s["supervisor"] == visao.SEM_SUPERVISOR, -s["pendentes"], s["pct_feitas"] or 0, s["supervisor"]),
    "pt": lambda s: (s["supervisor"] == visao.SEM_SUPERVISOR, -s["parada"], -s["pts"], s["supervisor"])}


def _modo(equipe, historico=False) -> str:
    """As três visões da Central e da tela de PT: cartões por equipe (o padrão), por supervisor, ou a tabela (a equipe
    escolhida no cartão abre a tabela dela)."""
    pedido = request.args.get("modo")
    if pedido == "tabela" or equipe or historico:
        return "tabela"
    return "supervisores" if pedido == "supervisores" else "equipes"


def _do_supervisor(x, supervisor) -> bool:
    """A linha é do supervisor escolhido. Linha sem supervisor (PT sem usina ligada ao cadastro, equipe sem técnico)
    conta como "Sem supervisor": é o que o cartão próprio mostra, e o clique nele tem de achar as mesmas linhas."""
    return not supervisor or (x.get("supervisor") or visao.SEM_SUPERVISOR) == supervisor


@bp.route("/atencao")
def atencao():
    """Três visões em cada aba (Levi, 05/10: "tem que ter a visão por equipe (CARDS grandes agrupados) e a visão da
    tabela!"; 08/10: "adicione mais um botão (por supervisor)"): cartões por equipe, por supervisor, ou a tabela. Filtro
    pela região do Brasil; o cartão da equipe leva à tabela da equipe, o do supervisor à tabela do supervisor."""
    dias = _dias((7, 14, 30), 14)
    leitura = visao.atencao(dias)
    d = leitura.dados
    ids = [v[0] for v in VISTAS]
    vista = request.args.get("vista") if request.args.get("vista") in ids else "pendentes"
    f, regiao, equipe = request.args.get("f", ""), request.args.get("regiao", ""), request.args.get("equipe", "")
    supervisor = _supervisor()
    modo = _modo(equipe)
    q = request.args.get("q", "").strip().lower()
    campos = ("usina", "cidade", "equipe", "obs", "feito_por", "solicitante", "os", "numero", "tarefa")

    def filtra(lista):
        return [x for x in lista if (not regiao or x.get("regiao_br") == regiao)
                and (not equipe or x.get("equipe") == equipe)
                and _do_supervisor(x, supervisor)
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
    # os cartões por supervisor somam os de equipe (já filtrados): o número do supervisor é o da soma das equipes dele
    cartoes_sup = sorted(visao.por_supervisor(cartoes), key=ORDEM_DOS_SUPERVISORES[vista])
    return render_template("campo/atencao.html", **_comum(
        "atencao", leitura, dias=dias, vista=vista, vistas=[(v, n, len(fontes[v])) for v, n in VISTAS],
        status=STATUS_DA_VISTA[vista], status_de=lambda x: _status(vista, x), contagem=contagem, total=len(base),
        lista=lista, f=f, regiao=regiao, equipe=equipe, modo=modo, cartoes=cartoes, regioes=visao.REGIOES,
        cartoes_sup=cartoes_sup, sem_supervisor=visao.SEM_SUPERVISOR, situacoes=SITUACAO_PT,
        supervisor=supervisor, supervisores=_opcoes_supervisor((d.get("usinas") or []) + (d.get("pts") or []), supervisor),
        q=request.args.get("q", ""), idade_min=_idade_min))


def _opcoes_supervisor(linhas, escolhido) -> list[str]:
    """Os supervisores do filtro. O escolhido entra sempre: o cartão "Sem supervisor no cadastro" leva a um supervisor
    que pode não estar escrito em nenhuma linha (a PT sem usina ligada ao cadastro vem sem supervisor)."""
    return sorted({x.get("supervisor") for x in linhas if x.get("supervisor")} | ({escolhido} if escolhido else set()))


# ── Permissões de trabalho (visão nossa) ─────────────────────────────────────────────────────────────────────────
SITUACAO_PT = {"aguardando": ("Aguardando", "alerta"), "de_acordo": ("De acordo", "ok"),
               "negada": ("Não autorizada", "critico"), "vencida": ("Vencida", "neutro")}


@bp.route("/pt")
def pt():
    """Duas abas (Levi, 05/10): as PT esperando o De acordo (por equipe, por supervisor ou em tabela, a linha abre o
    detalhe) e o histórico das decididas. Filtro de supervisor; a equipe vem do cartão."""
    leitura = visao.pts()
    d = leitura.dados
    aba = "historico" if request.args.get("aba") == "historico" else "esperando"
    supervisor, equipe = _supervisor(), request.args.get("equipe", "")
    sit, q = request.args.get("sit", ""), request.args.get("q", "").strip().lower()
    modo = _modo(equipe, historico=aba == "historico")
    dias = _dias((7, 30, 90), 30)
    piso = visao._agora() - timedelta(days=dias)
    campos = ("os", "numero", "tarefa", "usina", "ativo", "codigo", "equipe", "solicitante", "decidida_por")

    def filtra(lista):
        return [p for p in lista if _do_supervisor(p, supervisor)
                and (not equipe or p.get("equipe") == equipe)
                and (not q or q in " ".join(str(p.get(c) or "") for c in campos).lower())]
    aguardando = filtra(d.get("aguardando") or [])
    # a aba Esperando é a MESMA da Central de atenção > Permissões de trabalho (Levi, 05/10)
    f = request.args.get("f", "") if request.args.get("f") in visao.PT_STATUS else ""
    regiao = request.args.get("regiao", "")
    if regiao:
        aguardando = [p for p in aguardando if p.get("regiao_br") == regiao]
    contagem_pt = {s: sum(1 for p in aguardando if _status("pt", p) == s) for s in visao.PT_STATUS}
    cartoes_pt = sorted((c for c in visao.por_equipe([], [], [], aguardando, d.get("times") or {}) if c["pts"]),
                        key=ORDEM_DOS_CARTOES["pt"])
    cartoes_sup = sorted(visao.por_supervisor(cartoes_pt), key=ORDEM_DOS_SUPERVISORES["pt"])
    lista_pt = [p for p in aguardando if not f or _status("pt", p) == f]
    historico = [p for p in filtra(d.get("historico") or []) if (p.get("criada") or piso) >= piso]
    contagem = {}
    for p in historico:
        contagem[p["situacao"]] = contagem.get(p["situacao"], 0) + 1
    historico = [p for p in historico if not sit or p.get("situacao") == sit]
    todas = (d.get("aguardando") or []) + (d.get("historico") or [])
    return render_template("campo/pt.html", **_comum(
        "pt", leitura, aba=aba, modo=modo, aguardando=aguardando, historico=historico, contagem_hist=contagem, sit=sit,
        dias=dias, supervisor=supervisor, equipe=equipe, q=request.args.get("q", ""), situacoes=SITUACAO_PT,
        idade_min=_idade_min, cartoes=cartoes_pt, lista=lista_pt, contagem=contagem_pt, total=len(aguardando), f=f,
        cartoes_sup=cartoes_sup, sem_supervisor=visao.SEM_SUPERVISOR,
        status=visao.PT_STATUS, regiao=regiao, regioes=visao.REGIOES,
        supervisores=_opcoes_supervisor(todas, supervisor)))


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


# ── Rondas e Zeladoria (visão nossa) ─────────────────────────────────────────────────────────────────────────────
# Levi, 08/10/2026: a aba Cobertura saiu ("já não faz sentido tendo o histórico da usina") e entrou a "Sem ronda"; o
# Painel é a "visão a mais, dashboards que mostre de fato" quem está melhor. Os botões de filtro da Sujidade saíram:
# "se a pessoa quiser ordenar ela clica na coluna que ordena e já era!" (o clique no cabeçalho, `_ordenar.html`).
ABAS_RONDAS = (("registros", "Registros"), ("painel", "Painel"), ("sujidade", "Sujidade e vegetação"),
               ("sem", "Sem ronda"), ("trackers", "Trackers"), ("quem", "Quem ronda"))
# a aba Sem ronda: sem ronda no período (o padrão), há 7 dias ou mais, ou nunca em todo o registro
FILTROS_SEM_RONDA = ("sem", "atrasadas", "nunca")
LIMITE_LINHAS = 300


def _duracao(m) -> str:
    """27 min, 1h04: como o painel de rondas mostrava (Levi, 05/10)."""
    if m is None:
        return "—"
    return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m} min"


def _iniciais(nome) -> str:
    partes = [p for p in str(nome or "").split() if p]
    return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper() if partes else "?"


def _ordem_sem_ronda(c):
    """A mais esquecida primeiro: há mais dias sem ronda (nunca = 999); no empate, a última OS mais antiga (ou nenhuma)."""
    return (-c["dias"], (c.get("ultima_os") or {}).get("data") or "", c["usina"])


@bp.route("/rondas")
def rondas():
    """Cobertura, duração e qualidade da ronda (Levi, 05/10: o estilo do painel de rondas, no tema do Nexus): sete
    indicadores do período e seis abas (Registros, Painel, Sujidade e vegetação, Sem ronda, Trackers, Quem ronda).
    Filtros de região do Brasil, cliente, supervisor e equipe (a equipe vem do Painel); Exportar CSV dos registros."""
    dias = _dias((7, 14, 30), 30)
    leitura = visao.rondas()
    d = leitura.dados
    regiao, supervisor = request.args.get("regiao", ""), _supervisor()
    # cliente pelo cadastro (Levi, 05/10: "filtro por cliente e a cobertura das rondas das UFVs do cliente. Essas usinas
    # tem que bater com as mesmas do registro mestre"): filtra as rondas E a base da cobertura
    cliente, cluster, equipe = request.args.get("cliente", ""), request.args.get("cluster", ""), request.args.get("equipe", "")
    pedida = "sem" if request.args.get("aba") == "cobertura" else request.args.get("aba")     # endereço antigo
    aba = pedida if pedida in dict(ABAS_RONDAS) else "registros"
    dur, q = request.args.get("dur", ""), request.args.get("q", "").strip().lower()
    pend = request.args.get("pend", "") if request.args.get("pend") in visao.FEITA else ""
    # os indicadores filtram a tabela (Levi, 05/10: "quero que esses botões sejam clicáveis e filtre a tabela")
    ind = request.args.get("ind", "") if request.args.get("ind") in ("hoje", "qualidade", "duracao") else ""
    cob = request.args.get("cob", "") if request.args.get("cob") in FILTROS_SEM_RONDA else ""
    # Quem ronda em blocos (o padrão) ou em tabela (Levi, 08/10: "traga também uma visão em blocos para que fique mais
    # visual para os supervisores!")
    ver = "tabela" if request.args.get("ver") == "tabela" else "blocos"

    def filtra(lista):
        return [x for x in lista if (not regiao or x.get("regiao_br") == regiao)
                and (not supervisor or x.get("supervisor") == supervisor)
                and (not cliente or x.get("cliente") == cliente)
                and (not equipe or x.get("equipe") == equipe)]
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
    # a aba Sem ronda (Levi, 08/10: "troque por uma tabela chamada 'Sem ronda' que mostrará usina, equipe, técnicos,
    # supervisor e última OS feita na usina"): sem ronda no período (padrão), há 7 dias ou mais, ou nunca
    na_aba_sem = {"atrasadas": lambda c: c["dias"] >= visao.DIAS_SEM_RONDA_ALERTA,
                  "nunca": lambda c: c.get("nunca", c["dias"] >= 999)}.get(cob, lambda c: c["dias"] >= dias)
    sem_ronda = sorted((c for c in cobertura if na_aba_sem(c)), key=_ordem_sem_ronda)
    n_sem = {"sem": sum(1 for c in cobertura if c["dias"] >= dias),
             "atrasadas": sum(1 for c in cobertura if c["dias"] >= visao.DIAS_SEM_RONDA_ALERTA),
             "nunca": painel["kpi"]["nunca"]}
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
    clientes = sorted({c.get("cliente") for c in d.get("cobertura") or [] if c.get("cliente")})
    cluster_aberto = next((c for c in painel["clusters"] if c["cluster"] == cluster), None) if cluster else None
    suj, suj_estado = None, None
    if aba == "sujidade":
        # as respostas vêm das OS de ronda no Fracttal: as aprovadas, relidas em segundo plano, e as em verificação,
        # que já estão na fila da Aprovação de OS (nunca espera o Fracttal)
        campo_aprovacao._pedir_releitura()
        ronda_checklist.pedir_releitura()
        # + a validação por foto (Levi, 08/10/2026): a leitura da usina naquele dia, no lugar da ronda do mesmo dia
        suj = visao.sujidade_vegetacao(filtra(d.get("todas") or []), cobertura, ronda_checklist.respostas(), dias,
                                       d.get("hoje") or visao._agora().date().isoformat(),
                                       filtra(d.get("validacoes") or []))
        suj_estado = ronda_checklist.estado()
    comparativos = visao.comparativos(painel["periodo"], cobertura) if aba == "painel" else None
    return render_template("campo/rondas.html", **_comum(
        "rondas", leitura, dias=dias, regiao=regiao, supervisor=supervisor, aba=aba, abas=ABAS_RONDAS, dur=dur,
        pend=pend, pendencias={k: v for k, v in visao.FEITA.items() if k != "ok"}, ind=ind, cob=cob,
        n_pend={k: sum(1 for r in painel["periodo"] if r["pendencia"] == k) for k in ("sem_os", "incompleta")},
        q=request.args.get("q", ""), k=painel["kpi"], registros=registros, limite=LIMITE_LINHAS, cobertura=cobertura,
        sem_ronda=sem_ronda, n_sem=n_sem, registro_desde=d.get("registro_desde") or "",
        trackers=painel["trackers"], quem=painel["quem"], regioes=visao.REGIOES, supervisores=supervisores,
        duracao=_duracao, iniciais=_iniciais, suj=suj, suj_estado=suj_estado, equipe=equipe, ver=ver,
        cliente=cliente, clientes=clientes, clusters=painel["clusters"], cluster_aberto=cluster_aberto,
        comparativos=comparativos, dimensoes=visao.DIMENSOES, base_pequena=visao.BASE_PEQUENA,
        filtro_da_dimensao={"regiao_br": "regiao", "equipe": "equipe", "cliente": "cliente", "supervisor": "supervisor"},
        explicacao_avulsa=ronda_avulsa.EXPLICACAO, explicacao_validada=visao.VALIDADA_EXPLICACAO))


@bp.route("/rondas/usina/<int:usina_id>")
def rondas_usina(usina_id):
    """O histórico de rondas de uma usina, com data, sujidade e vegetação (Levi, 05/10: "quando clicarmos no nome da
    usina já aparece o histórico de rondas ... essas informações são importantes!")."""
    leitura = visao.rondas()
    d = leitura.dados or {}
    ronda_checklist.pedir_releitura()
    campo_aprovacao._pedir_releitura()
    hist = visao.historico_usina(d.get("todas") or [], ronda_checklist.respostas(), usina_id, d.get("validacoes") or [])
    usina = next((c for c in d.get("cobertura") or [] if c["usina_id"] == usina_id), None) or (hist[0] if hist else None)
    # a validação por foto (08/10/2026) é leitura, não ronda: fora da contagem de rondas; a ronda que ela revisou fica
    # fora da evolução (no dia dela, vale o valor validado)
    rondas_hist = [r for r in hist if not r.get("validada")]
    lidas = [r for r in hist if (r["sujidade"] is not None or r["vegetacao"] is not None) and not r.get("revisada")]
    return render_template("campo/rondas_usina.html", **_comum(
        "rondas", leitura, usina=usina, usina_id=usina_id, hist=hist, rondas_hist=rondas_hist, lidas=lidas,
        duracao=_duracao, iniciais=_iniciais, suj_estado=ronda_checklist.estado(),
        explicacao_avulsa=ronda_avulsa.EXPLICACAO, explicacao_validada=visao.VALIDADA_EXPLICACAO))


@bp.route("/rondas/avulsa", methods=["GET", "POST"])
def ronda_avulsa_lancar():
    """Lançar uma ronda avulsa (Levi, 07/10/2026: "a pessoa loga pelo fractal dela ... não terá imagens, só informações
    da tabela, salva nome da pessoa, data e hora e diz que foi avulso"). Recusa volta com o motivo e o que foi digitado
    (400); o lançamento gravado e conferido no banco volta para esta página com o aviso (303)."""
    usuario = session.get("usuario")
    erro = None
    if request.method == "POST":
        try:
            nova = ronda_avulsa.lancar(request.form, usuario)
            session["avulsa_aviso"] = f"Ronda avulsa lançada: {_dia_curto(nova['data'])}, das {nova['inicio'][11:16]} às {nova['fim'][11:16]}."
            return redirect("/t/campo/rondas/avulsa", code=303)
        except ronda_avulsa.Recusada as e:
            erro = str(e)
        except Exception as e:      # noqa: BLE001 — banco fora: a tela diz, nada some calado
            erro = f"Não consegui gravar no banco ({type(e).__name__}). Tente de novo em instantes."
    leitura = visao.rondas()
    from ...campo.ligacao_cadastro import codigo_da_pessoa
    from flask import current_app
    meu = codigo_da_pessoa(current_app.config.get("NEXUS_PESSOA_HMAC"), (usuario or {}).get("email") or "") if usuario else ""
    minhas = [r for r in (leitura.dados or {}).get("todas") or [] if r.get("avulsa") and meu and r.get("avulsa_hmac") == meu]
    html = render_template("campo/ronda_avulsa.html", **_comum(
        "rondas", leitura, usuario=usuario, erro=erro, aviso=session.pop("avulsa_aviso", None),
        form=request.form if erro else ImmutableMultiDict(), usinas=ronda_avulsa.usinas_para_escolher() if usuario else [],
        minhas=minhas, explicacao_avulsa=ronda_avulsa.EXPLICACAO, hoje=visao._agora().date().isoformat(),
        piso=(visao._agora().date() - timedelta(days=ronda_avulsa.DIAS_ATRAS)).isoformat(),
        tipos=ronda_avulsa.TIPOS, valas=ronda_avulsa.VALAS, sensores=ronda_avulsa.SENSORES,
        estados_sensor=ronda_avulsa.ESTADOS_SENSOR, duracao=_duracao, comentario_max=ronda_avulsa.COMENTARIO_MAX))
    return (html, 400) if erro else html


@bp.route("/rondas/avulsa/<rid>/anular", methods=["POST"])
def ronda_avulsa_anular(rid):
    """Anular a própria ronda avulsa: vira outra linha no banco (o banco não apaga)."""
    try:
        ronda_avulsa.anular(rid, session.get("usuario"))
    except ronda_avulsa.Recusada as e:
        return render_template("campo/ronda_avulsa.html", **_comum(
            "rondas", visao.rondas(), usuario=session.get("usuario"), erro=str(e), aviso=None, form=ImmutableMultiDict(), usinas=[],
            minhas=[], explicacao_avulsa=ronda_avulsa.EXPLICACAO, hoje="", piso="", tipos=(), valas=(), sensores=[],
            duracao=_duracao, comentario_max=ronda_avulsa.COMENTARIO_MAX)), 400
    session["avulsa_aviso"] = "Ronda avulsa anulada: ela sai das telas e a anulação fica registrada no banco."
    return redirect("/t/campo/rondas/avulsa", code=303)


@bp.route("/rondas/os/<int:os_>/fotos")
def ronda_fotos_os(os_):
    """As fotos da OS de ronda, separadas em sujidade, vegetação e as demais (Levi, 06/10: "ao clicar no botão aparecer
    os anexos, separando vegetação e sujidade"). Pedaço de HTML que o botão Fotos do histórico carrega."""
    try:
        gs = ronda_fotos.grupos(os_)
        erro = ""
        ronda_fotos.preparar(os_, ronda_checklist.em_segundo_plano)     # nos testes, na hora
    except Exception as e:      # noqa: BLE001 — Fracttal fora ou recusando: o pedaço diz, a página segue
        gs = []
        erro = ("O Fracttal recusou agora por excesso de pedidos; tente de novo em 1 minuto."
                if "429" in str(e) else f"Não consegui ler os anexos da OS no Fracttal ({type(e).__name__}).")
    return render_template("campo/_ronda_fotos.html", os_=os_, grupos=gs, erro=erro,
                           total=sum(len(g["fotos"]) for g in gs))


@bp.route("/rondas/os/<int:os_>/foto/<int:i>")
def ronda_foto(os_, i):
    """Uma foto da OS de ronda: o Nexus baixa do Fracttal e entrega (o link assinado não sai para o navegador)."""
    try:
        corpo, mime = (ronda_fotos.miniatura if request.args.get("mini") else ronda_fotos.foto)(os_, i)
    except ronda_fotos.SemFoto as e:
        return Response(str(e), status=404, mimetype="text/plain")
    except Exception as e:      # noqa: BLE001
        return Response(f"Fracttal: {type(e).__name__}", status=502, mimetype="text/plain")
    return Response(corpo, mimetype=mime, headers={"Cache-Control": "private, max-age=3600"})


@bp.route("/zeladoria")
def zeladoria():
    return render_template("campo/zeladoria.html", **_comum("zeladoria", visao.zeladoria()))


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
# O cartão "Paradas há 30 dias ou mais" filtra as MESMAS OS que conta (30 dias ou mais). Levava à faixa "31 a 60 dias":
# com a fila inteira (Levi, 08/10/2026: "não deve ter filtro 'OS fechadas nos X dias'") a OS parada há 120 dias contava
# no cartão e sumia no clique. Só o cartão usa esta faixa; a barra de idade segue com as cinco de cima.
IDADE_PARADAS = ("30-", "há 30 dias ou mais", 30, 10 ** 6)
# As visões "por técnico" e "fila" saíram em 08/10/2026 (Levi: "a visão de por técnico e fila pode matar, pode tirar que
# é irrelevante!"): fica a de supervisor, e o cartão abre a tabela das OS dele (`ver=`), onde se aprova.
SEM_CADASTRO = "Sem cadastro"


# O grupo da OS sai das tarefas dela: quem aprova, aprova a OS inteira (Levi, 05/10: "ele não consegue aprovar uma
# tarefa em si, e sim uma PT ou uma OS"). Basta uma tarefa pedir olho para a OS pedir; sem isso, uma tarefa fechada fora
# do App já tira a OS de "completa"; completa é só a OS com TODAS as tarefas completas.
ORDEM_DO_GRUPO = ("olho", "fora_do_app", "completa")


def _por_os(linhas) -> list[dict]:
    """Uma linha por OS, a partir das tarefas da fila (cada tarefa com o grupo e os motivos do App)."""
    g = {}
    for x in linhas:
        o = g.setdefault(x["os"], {"os": x["os"], "id_wo": None, "tarefas": []})
        o["tarefas"].append(x)
        o["id_wo"] = o["id_wo"] or x.get("id_wo")
    for o in g.values():
        ts = o["tarefas"]
        baldes = {t["balde"] for t in ts}
        o["balde"] = next(b for b in ORDEM_DO_GRUPO if b in baldes)
        o["espera_d"] = max(t.get("espera_d") or 0 for t in ts)              # a tarefa mais antiga
        o["fim"] = max(str(t.get("fim") or "") for t in ts)
        o["tecnicos"] = sorted({t.get("tecnico") or "—" for t in ts})
        primeira = next((t for t in ts if t.get("usina_cad")), ts[0])
        for c in ("usina_cad", "equipe_cad", "supervisor_cad", "regiao_br"):
            o[c] = primeira.get(c) or ""
        notas = [int(t["qualidade"]) for t in ts if t.get("pelo_app") and t.get("qualidade") is not None]
        o["nota"] = min(notas) if notas else None                            # a pior tarefa
        o["pelo_app"] = all(t.get("pelo_app") for t in ts)
        o["n_app"] = sum(1 for t in ts if t.get("pelo_app"))
        o["devolvida"] = any(t.get("foi_devolvida") for t in ts)
        o["ronda"] = any(t.get("ronda") for t in ts)
        o["n_por_grupo"] = {b: sum(1 for t in ts if t["balde"] == b) for b in ORDEM_DO_GRUPO}
        # as colunas da tabela do supervisor (Levi, 08/10/2026: "a OS, dia, data da criação da OS, data fim, supervisor,
        # prontas, pedem olho, fora do App, uso do App, nota média e devolvidas"): contadas nas tarefas da OS
        o["criada"] = min((str(t.get("criada")) for t in ts if t.get("criada")), default="")
        o["uso_app"] = round(100 * o["n_app"] / len(ts))
        o["nota_media"] = round(sum(notas) / len(notas)) if notas else None
        o["n_devolvidas"] = sum(1 for t in ts if t.get("foi_devolvida"))
    return sorted(g.values(), key=lambda o: -o["espera_d"])


def _data_br(iso) -> str:
    """dd/mm/aa no horário de Brasília. O Fracttal fala UTC: a data de fim vem sem fuso (o App corta em 19 caracteres)
    e a de criação com "+00:00"; sem converter, a OS fechada às 22 h de Brasília aparecia no dia seguinte."""
    s = str(iso or "").strip().replace("Z", "+00:00")
    if not s:
        return "—"
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return s[:10]
    d = d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return d.astimezone(_BRT).strftime("%d/%m/%y")


def _agrupa_os(oss, chaves) -> list[dict]:
    """Um cartão por supervisor (a chave que `chaves` der): as OS esperando, os três grupos, a idade e o uso do App,
    em OS. (A nota, as devolvidas, a equipe e o supervisor "da maioria" serviam só à tabela por técnico, que saiu em
    08/10/2026; o que é da OS está na tabela do supervisor, `_por_os`.)"""
    g = {}
    for o in oss:
        for k in chaves(o):
            k = k or SEM_CADASTRO
            a = g.setdefault(k, {"nome": k, "ordens": 0, "tarefas": 0, "completa": 0, "olho": 0, "fora_do_app": 0,
                                 "aged7": 0, "aged30": 0, "espera_max": 0, "pelo_app": 0, "equipes": set(),
                                 "tecnicos": set()})
            a["ordens"] += 1
            a["tarefas"] += len(o["tarefas"])
            a[o["balde"]] += 1
            a["aged7"] += o["espera_d"] >= 7
            a["aged30"] += o["espera_d"] >= 30
            a["espera_max"] = max(a["espera_max"], o["espera_d"])
            a["pelo_app"] += o["pelo_app"]
            a["equipes"].add(o.get("equipe_cad") or SEM_CADASTRO)
            a["tecnicos"].update(o["tecnicos"])
    for a in g.values():
        a["uso_app"] = round(100 * a["pelo_app"] / a["ordens"]) if a["ordens"] else None
        a["n_equipes"], a["n_tecnicos"] = len(a.pop("equipes")), len(a.pop("tecnicos"))
    return list(g.values())


@bp.route("/aprovacao")
def aprovacao():
    """A fila de verificação do Fracttal para tirar insight (Levi, 05/10: "refaça essa parte de aprovação de OS para
    retirada de bons insights"), contada por OS, que é o que se aprova. Os grupos de cada tarefa são os do App (a fila
    inteira pela `_fila_supervisao`); a equipe e o supervisor vêm do cadastro do Nexus, pela usina do Fracttal (de-para
    "Fracttal · Classificação 1").
    Desde 08/10/2026 (Levi): a fila INTEIRA, sem "OS fechadas nos X dias"; uma visão só, os cartões por supervisor; o
    cartão abre a tabela das OS dele (`ver=`), uma linha por OS que abre o porquê do grupo e o Aprovar, que só o
    supervisor da OS ou um administrador usa (`aprovar_os.py`). Os indicadores e a barra da idade filtram cartões e
    tabela."""
    equipe, supervisor = request.args.get("equipe", ""), _supervisor()
    mapa = visao.usinas_do_fracttal()
    opcoes = mapa.dados or {}
    usinas = None
    if equipe and equipe in (opcoes.get("equipes") or {}):
        usinas = set(opcoes["equipes"][equipe])
    if supervisor and supervisor in (opcoes.get("supervisores") or {}):
        usinas = set(opcoes["supervisores"][supervisor]) & (usinas if usinas is not None else set(opcoes["supervisores"][supervisor]))
    leitura = campo_aprovacao.fila_toda(campo_aprovacao.FILA_INTEIRA, usinas)
    d = leitura.dados or {}
    por_nome = opcoes.get("por_nome") or {}
    todas = d.get("linhas") or []
    for x in todas:
        cad = por_nome.get(regras_app._norm(x.get("usina_fx"))) or {}
        x["usina_cad"], x["equipe_cad"] = cad.get("usina") or x.get("usina_fx") or "", cad.get("equipe") or ""
        x["supervisor_cad"], x["regiao_br"] = cad.get("supervisor") or "", cad.get("regiao_br") or ""
    oss = _por_os(todas)
    balde = request.args.get("balde") if request.args.get("balde") in ORDEM_DO_GRUPO else ""
    idade = next((i for i in IDADES + (IDADE_PARADAS,) if i[0] == request.args.get("idade")), None)
    # os indicadores e a idade filtram os cartões e a tabela; os números do topo seguem sobre a fila inteira
    filtradas = [o for o in oss if (not balde or o["balde"] == balde)
                 and (not idade or idade[2] <= o["espera_d"] <= idade[3])]
    # o supervisor aberto (Levi, 08/10: "nessa visão por supervisor deve ser clicável, quando clica aparece a OS ...")
    ver = request.args.get("ver", "")
    tabela = [o for o in filtradas if (o.get("supervisor_cad") or SEM_CADASTRO) == ver] if ver else []
    nome_grupo = {g[0]: g[1] for g in GRUPOS}
    if request.args.get("csv") == "1":
        import csv
        import io
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["OS", "Dias esperando", "Criação da OS", "Data fim", "Supervisor", "Equipe", "Usina", "Técnicos",
                    "Tarefas", "Prontas", "Pedem olho", "Fora do App", "Uso do App (%)", "Nota média",
                    "Devolvidas", "Grupo da OS"])
        for o in (tabela if ver else filtradas):
            n = o["n_por_grupo"]
            w.writerow([o["os"], o["espera_d"], _data_br(o["criada"]) if o["criada"] else "", _data_br(o["fim"]),
                        o["supervisor_cad"], o["equipe_cad"], o["usina_cad"], ", ".join(o["tecnicos"]),
                        len(o["tarefas"]), n["completa"], n["olho"], n["fora_do_app"], o["uso_app"],
                        "" if o["nota_media"] is None else o["nota_media"], o["n_devolvidas"],
                        nome_grupo.get(o["balde"])])
        return Response("\ufeff" + buf.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="aprovacao-os.csv"'})
    mais_antiga = oss[0] if oss else None
    k = {"ordens": len(oss), "tarefas": len(todas), "baldes": {b: sum(1 for o in oss if o["balde"] == b) for b in ORDEM_DO_GRUPO},
         "aged30": sum(1 for o in oss if o["espera_d"] >= 30), "espera_max": mais_antiga["espera_d"] if mais_antiga else 0,
         "mais_antiga": mais_antiga, "uso_app": round(100 * sum(o["pelo_app"] for o in oss) / len(oss)) if oss else None}
    idades = [(i, sum(1 for o in oss if i[2] <= o["espera_d"] <= i[3])) for i in IDADES]
    supervisores_g = sorted(_agrupa_os(filtradas, lambda o: [o.get("supervisor_cad")]),
                            key=lambda a: (-a["aged30"], -a["ordens"], a["nome"]))
    aberto = next((a for a in supervisores_g if a["nome"] == ver), None) if ver else None
    return render_template("campo/aprovacao.html", **_comum(
        "aprovacao", leitura, grupos=GRUPOS, nome_grupo={g[0]: (g[1], g[2]) for g in GRUPOS}, balde=balde,
        cor_espera=_cor_espera, coleta=_coleta(), fila=campo_aprovacao.estado(), equipe=equipe, supervisor=supervisor,
        equipes=sorted(opcoes.get("equipes") or {}), supervisores=sorted(opcoes.get("supervisores") or {}),
        mapa_erro=mapa.erro, k=k, idades=idades, idade=idade, ver=ver, aberto=aberto, tabela=tabela,
        limite=LIMITE_LINHAS, por_supervisor=supervisores_g, sem_cadastro=SEM_CADASTRO, data_br=_data_br,
        pode_aprovar=pode_na_tela, motivos=campo_aprovacao.motivos))


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
