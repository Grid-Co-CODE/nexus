"""Torre Campo · App: a visão do Nexus sobre o trabalho de campo. Leia o CLAUDE.md desta pasta antes de mexer.

Levi, 05/10/2026: "quero parar de referenciar o Azure e ter uma visão nossa!". Nenhuma tela abre mais o painel do App
(que mora no Azure) nem aponta para ele: todas leem o banco do Nexus (API db_performace) — os livros que o próprio App
grava de hora em hora e o cadastro do Nexus. Aprovação, Ordens e Triagem usam a cópia das regras do painel do App
(`nexus/campo/regras_app.py`); Central de atenção, PT, Rondas, Zeladoria e Ranking são contas NOSSAS
(`nexus/campo/visao.py`). Imagens da ronda e Rotas do dia ficam no placeholder: o dado delas ainda não chega ao banco.
"""
from datetime import datetime, timedelta
from urllib.parse import urlencode

from flask import Response, redirect, render_template, request, session
from markupsafe import Markup, escape

from ...campo import aprovacao as campo_aprovacao
from ...campo import fonte_pg as campo_fonte
from ...campo import ordens as campo_ordens
from ...campo import triagem as campo_triagem
from ...campo import visao
from ...campo import decisao_pt, pt_fracttal
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
VISTAS = (("pendentes", "Rondas pendentes"), ("feitas", "Rondas feitas"), ("pt", "Permissões de trabalho"))
STATUS_DA_VISTA = {"pendentes": visao.PENDENTE, "feitas": visao.FEITA, "pt": visao.PT_STATUS}


def _status(vista, x) -> str:
    return {"pendentes": x.get("tipo"), "feitas": x.get("status"),
            "pt": "parada" if x.get("parada") else "aguardando"}[vista]


def _idade_min(m) -> str:
    m = int(m or 0)
    if m >= 1440:
        return f"{m // 1440} d {(m % 1440) // 60} h"
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"


ORDEM_DOS_CARTOES = {"pendentes": lambda c: (-c["pendentes"], c["pct_feitas"] or 0, c["equipe"]),
                     "feitas": lambda c: (-c["rondas"], c["equipe"]),
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
    fontes = {"pendentes": filtra(d.get("pendentes") or []), "feitas": filtra(d.get("feitas") or []),
              "pt": filtra(d.get("pts") or [])}
    base = fontes[vista]
    contagem = {}
    for x in base:
        contagem[_status(vista, x)] = contagem.get(_status(vista, x), 0) + 1
    lista = [x for x in base if not f or _status(vista, x) == f]
    cartoes = visao.por_equipe(filtra(d.get("usinas") or []), fontes["pendentes"], fontes["feitas"], fontes["pt"],
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
@bp.route("/rondas")
def rondas():
    dias = _dias((7, 14, 30), 14)
    return render_template("campo/rondas.html", **_comum("rondas", visao.rondas(dias), dias=dias))


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


@bp.route("/aprovacao")
def aprovacao():
    leitura = campo_aprovacao.fila(request.args)
    return render_template("campo/aprovacao.html", **_comum(
        "aprovacao", leitura, grupos=GRUPOS, nome_grupo={g[0]: (g[1], g[2]) for g in GRUPOS},
        balde=request.args.get("balde", ""), cor_espera=_cor_espera, coleta=_coleta(), fila=campo_aprovacao.estado()))


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
