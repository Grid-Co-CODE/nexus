"""Torre Engenharia: Confiabilidade dos ativos, criticidade e causa raiz.

A Confiabilidade é nossa desde 06/10/2026 (Levi: "traga a aba Confiabilidade do pcm.gridco.com.br, não referenciando
diretamente esse caminho mas construindo algo nosso!"): o Nexus lê as OS de falha do Fracttal (`nexus/engenharia/
os_falhas.py`) e faz as contas (`nexus/engenharia/confiabilidade.py`). As outras telas seguem no placeholder da casca.
Leia o CLAUDE.md desta pasta antes de mexer.
"""
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from flask import render_template, request

from ..modelo import Tela, Torre

TORRE = Torre(
    id="engenharia",
    nome="Engenharia",
    ordem=40,
    icone="gear-six",
    descricao="Confiabilidade dos ativos, criticidade e causa raiz.",
    telas=[
        Tela("confiabilidade", "Confiabilidade",
             "Quais ativos falham mais e demoram mais a voltar?",
             "OS de falha do Fracttal, lidas pelo Nexus"),
        Tela("equipe", "Quadro da equipe",
             "Quem da engenharia está com o quê, o que atrasou e o que vem por aí?",
             "OS do Fracttal dos responsáveis da engenharia"),
        Tela("criticidade", "Matriz de criticidade",
             "Qual ativo, se parar, dói mais?",
             "engenharia.json do painel PCM"),
        Tela("fmea", "FMEA e causa raiz",
             "Por que a falha acontece e o que a elimina?",
             "Planilha de confiabilidade (a migrar)"),
        Tela("laudos", "Laudos MPS/MPA",
             "Que laudos estão pendentes ou vencidos?",
             "engenharia.json do painel PCM"),
    ],
)

bp = TORRE.criar_blueprint(__name__)

BRT = timezone(timedelta(hours=-3))
CACHE_S = 300
_CACHE: dict = {}
ABAS = (("ativos", "Ativos"), ("indicadores", "Indicadores"))


def _url(**mudar) -> str:
    args = {k: v for k, v in request.args.items() if v}
    for k, v in mudar.items():
        if v in (None, ""):
            args.pop(k, None)
        else:
            args[k] = v
    return "?" + urlencode(args) if args else "?"


def _onde_do_cadastro():
    """A ligação com o cadastro do Nexus (o registro mestre): a mesma do Campo · App, pelo de-para do Fracttal."""
    from ...campo import visao
    try:
        b = visao._Base()
    except Exception as e:  # noqa: BLE001 — banco fora: segue com o que o Fracttal escreve, e a tela avisa
        import logging
        logging.warning("confiabilidade: o cadastro não respondeu (%s: %s)", type(e).__name__, str(e)[:160])
        b = None
    memo = {}

    def onde(texto: str, cod: str) -> dict:
        chave = (texto, cod.split("-")[0])
        if chave in memo:
            return memo[chave]
        uid, como = b.lig.usina(texto, cod) if b else (None, None)
        u = (b.por_id.get(uid) or {}) if b else {}
        if u:
            mob = None
            try:
                mob = datetime.fromisoformat(str(u.get("data_mobilizacao") or "")[:10]).replace(tzinfo=BRT)
            except ValueError:
                pass
            o = b.onde(uid)
            r = {"usina_id": uid, "usina": o["usina"], "cliente": o["cliente"] or "—", "cluster": o["cluster"],
                 "uf": o["uf"], "equipe": o["equipe"], "mobilizacao": mob, "ligada_por": como}
        else:
            partes = [p.strip() for p in texto.split(" - ")]
            r = {"usina_id": None, "usina": " - ".join(partes[1:]) if len(partes) > 1 else texto or "—",
                 "cliente": partes[0] if partes and partes[0] else "—", "cluster": "", "uf": "", "equipe": "",
                 "mobilizacao": None, "ligada_por": None}
        memo[chave] = r
        return r
    onde.sem_cadastro = b is None
    return onde


def _dados() -> dict:
    """As contas, refeitas quando a leitura do Fracttal muda ou a cada 5 min (são ~13 mil linhas: menos de 1 s)."""
    from ...engenharia import confiabilidade, os_falhas
    os_falhas.pedir_releitura()
    est = os_falhas.estado()
    marca = (est["n"], est["vivas_em"])
    g = _CACHE.get("conf")
    # sem o cadastro, a conta vale só 30 s: a próxima visita tenta de novo
    if g and g["marca"] == marca and time.time() - g["em"] < (30 if g.get("sem_cadastro") else CACHE_S):
        return g
    onde = _onde_do_cadastro()
    d = confiabilidade.calcular(os_falhas.linhas(), onde)
    g = {"marca": marca, "em": time.time(), "dados": d, "sem_cadastro": getattr(onde, "sem_cadastro", False)}
    _CACHE["conf"] = g
    return g


def _h(x) -> str:
    """Horas: 5.737 h, 25,9 h."""
    if x is None:
        return "—"
    return f"{x:,.0f}".replace(",", ".") + " h" if x >= 100 else f"{x:.1f}".replace(".", ",") + " h"


def _pct(x) -> str:
    return "—" if x is None else f"{100 * x:.1f}".replace(".", ",") + "%"


@bp.route("/confiabilidade")
def confiabilidade():
    from ...engenharia import confiabilidade as C
    from ...engenharia import os_falhas
    g = _dados()
    d = g["dados"]
    f = {k: request.args.get(k, "") for k in ("cliente", "usina", "fam", "crit", "nivel", "q")}
    esconder = request.args.get("servico") == "0"
    aba = request.args.get("aba") if request.args.get("aba") in dict(ABAS) else "ativos"
    q = f["q"].strip().lower()

    def passa(a, com_nivel=True):
        return ((not f["cliente"] or a.get("cliente") == f["cliente"]) and (not f["usina"] or a.get("usina") == f["usina"])
                and (not f["fam"] or a["fam"] == f["fam"]) and (not f["crit"] or a["crit"] == f["crit"])
                and (not com_nivel or not f["nivel"] or a.get("nivel") == f["nivel"])
                and (not q or q in f"{a['cod']} {a['nome']} {a.get('usina')} {a.get('cliente')}".lower()))
    sinais = [a for a in d["sinais"] if passa(a) and not (esconder and a["soServico"])]
    ativos = [a for a in d["ativos"] if passa(a, com_nivel=False)]
    por = request.args.get("por") if request.args.get("por") in ("cliente", "usina") else "cliente"
    clientes = sorted({a.get("cliente") for a in d["ativos"] + d["sinais"] if a.get("cliente")})
    usinas = sorted({a.get("usina") for a in d["ativos"] + d["sinais"] if a.get("usina")
                     and (not f["cliente"] or a.get("cliente") == f["cliente"])})
    # o painel ao lado: os clientes com mais ativos com sinal (com os filtros de agora)
    por_cliente = {}
    for a in sinais:
        x = por_cliente.setdefault(a.get("cliente") or "—", {"nome": a.get("cliente") or "—", "sinais": 0, "criticos": 0})
        x["sinais"] += 1
        x["criticos"] += a["nivel"] == "critico"
    top_clientes = sorted(por_cliente.values(), key=lambda x: (-x["sinais"], -x["criticos"], x["nome"]))[:6]
    return render_template(
        "engenharia/confiabilidade.html", fams=d.get("familias") or [], crit_dist=d.get("critDist") or {},
        top_clientes=top_clientes, torre=TORRE, tela=TORRE.tela("confiabilidade"), d=d, k=d["kpi"],
        sinais=sinais, total_sinais=len(d["sinais"]), ativos=ativos, f=f, esconder=esconder, aba=aba, abas=ABAS,
        por=por, indicadores=C.indicadores(ativos, sinais, por) if aba == "indicadores" else [],
        clientes=clientes, usinas=usinas, familias=C.FAMILIAS, niveis=C.NIVEIS, meta=C.META_DISP,
        janela=C.JANELA_DIAS, url=_url, h=_h, pct=_pct, est=os_falhas.estado(), sem_cadastro=g.get("sem_cadastro"),
        lido=datetime.fromtimestamp(g["em"], BRT).strftime("%H:%M"),
        periodo=f"{d['periodo']['de'].astimezone(BRT):%d/%m} a {d['periodo']['ate'].astimezone(BRT):%d/%m/%Y}")


# ── Quadro da equipe (06/10/2026) ───────────────────────────────────────────────────────────────────────────────────
# Levi: "uma tela que fique no setor de engenharia que agregue todas as OSs que estão abertas ou já foram fechadas ou
# que serão abertas para essas pessoas" e "FAÇA UMA TELA DINÂMICA, ESTILO KANBAN E SUPERCARDS, DEIXE ALGO BOM DE
# GERENCIAR!". A leitura está em nexus/engenharia/os_equipe.py; aqui, os supercards (por pessoa) e o quadro.
CORES_PESSOA = ("#7fb8ff", "#a3d900", "#f2b84b", "#4fd1c5", "#ff8a65", "#e88fb4", "#c7cede")
DIAS_FAIXA = 14
JANELA_CONCLUIDAS = 30


def _iniciais(nome: str) -> str:
    p = [x for x in str(nome or "").split() if x]
    return (p[0][0] + (p[-1][0] if len(p) > 1 else "")).upper() if p else "?"


def supercards(oss: list[dict], equipe: list[dict], hoje) -> list[dict]:
    """Um supercard por pessoa: a carga por etapa, o que atrasou, o que fechou em 30 dias e a faixa dos próximos 14 dias
    (as OS a fazer pela data programada: o "que serão abertas")."""
    piso = (hoje - timedelta(days=JANELA_CONCLUIDAS)).isoformat()
    out = []
    for i, p in enumerate(equipe):
        minhas = [o for o in oss if o["pid"] == p["id"]]
        cont = {c: sum(1 for o in minhas if o["coluna"] == c) for c in ("fazer", "execucao", "verificacao", "concluida", "cancelada")}
        faixa = []
        for d in range(DIAS_FAIXA):
            dia = hoje + timedelta(days=d)
            n = [o for o in minhas if o["coluna"] in ("fazer", "execucao") and o["programada_iso"] == dia.isoformat()]
            faixa.append({"dia": dia.strftime("%d/%m"), "sem": "STQQSSD"[dia.weekday()], "fim_de_semana": dia.weekday() >= 5,
                          "n": len(n), "oss": ", ".join(o["os"] for o in n)})
        abertas = [o for o in minhas if o["coluna"] in ("fazer", "execucao")]
        proxima = min((o for o in abertas if o["dias"] is not None and o["dias"] >= 0), key=lambda o: o["dias"], default=None)
        out.append({"id": p["id"], "nome": p["nome"], "nome_fracttal": p.get("nome_fracttal") or p["nome"],
                    "iniciais": _iniciais(p.get("nome_fracttal") or p["nome"]), "cor": CORES_PESSOA[i % len(CORES_PESSOA)],
                    "cont": cont, "carga": cont["fazer"] + cont["execucao"] + cont["verificacao"],
                    "atrasadas": sum(1 for o in abertas if o["prazo"] == "atrasada"),
                    "vence": sum(1 for o in abertas if o["prazo"] == "vence"),
                    "fechadas30": sum(1 for o in minhas if o["coluna"] == "concluida" and (o["fim_iso"] or "") >= piso),
                    "faixa": faixa, "proxima": proxima, "total": len(minhas)})
    return out


@bp.route("/equipe")
def equipe():
    from ...engenharia import os_equipe
    os_equipe.pedir_releitura(esperar=not os_equipe.dados()["lido"])
    d = os_equipe.dados()
    hoje = datetime.now(BRT).date()
    cards = supercards(d["os"], d["equipe"], hoje)
    cor = {c["id"]: c["cor"] for c in cards}
    ini = {c["id"]: c["iniciais"] for c in cards}          # as do supercard (pelo nome no Fracttal)
    oss = [dict(o, cor=cor.get(o["pid"], CORES_PESSOA[-1]), iniciais=ini.get(o["pid"]) or _iniciais(o["pessoa"]))
           for o in d["os"]]
    piso = (hoje - timedelta(days=JANELA_CONCLUIDAS)).isoformat()
    total = {"carga": sum(c["carga"] for c in cards), "atrasadas": sum(c["atrasadas"] for c in cards),
             "vence": sum(c["vence"] for c in cards), "fechadas30": sum(c["fechadas30"] for c in cards),
             "verificacao": sum(c["cont"]["verificacao"] for c in cards)}
    return render_template(
        "engenharia/equipe.html", torre=TORRE, tela=TORRE.tela("equipe"), cards=cards, oss=oss, total=total,
        faltam=d["faltam"], erro=d["erro"], colunas=os_equipe.COLUNAS,
        hoje=hoje.isoformat(), piso_concluidas=piso, janela=JANELA_CONCLUIDAS, dias_faixa=DIAS_FAIXA,
        lido=datetime.fromtimestamp(d["lido"], BRT).strftime("%H:%M") if d["lido"] else "—")
