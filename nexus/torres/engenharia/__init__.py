"""Torre Engenharia: Confiabilidade dos ativos, criticidade e causa raiz.

A Confiabilidade é nossa desde 06/10/2026 (Levi: "traga a aba Confiabilidade do pcm.gridco.com.br, não referenciando
diretamente esse caminho mas construindo algo nosso!"): o Nexus lê as OS de falha do Fracttal (`nexus/engenharia/
os_falhas.py`) e faz as contas (`nexus/engenharia/confiabilidade.py`). As outras telas seguem no placeholder da casca.
Leia o CLAUDE.md desta pasta antes de mexer.
"""
import time
from datetime import date, datetime, timedelta, timezone
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
ESPERA_VERIFICACAO = 7      # dias: a OS feita esperando a verificação há mais que isso pinta o número de âmbar


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


def _dias(n: int) -> str:
    return "1 dia" if n == 1 else f"{n} dias"


def faixa_kpis(oss: list[dict], hoje, janela: int = JANELA_CONCLUIDAS) -> list[dict]:
    """A faixa de números do quadro no modelo do Acompanhamento de chamados do OS Creator (Levi, 08/10/2026: "Precisamos
    padronizar a estética ... o card de KPIS eu gostei mais do de chamados"): o rótulo em cima, o número grande colorido
    pela gravidade e, ao lado, o detalhe que diz por onde começar (a OS mais atrasada, a próxima a vencer, a que espera a
    verificação há mais tempo). As contagens são as dos supercards: a coluna e o prazo de cada OS vêm do os_equipe.

    Cada item: {rotulo, valor, grav ("critico" | "alerta" | "ok" | ""), nota: [(texto, negrito)]}. A nota vai em pedaços
    para o template pôr o nº da OS em negrito sem montar HTML aqui (o título vem do Fracttal e é escapado lá)."""
    col = {c: [o for o in oss if o["coluna"] == c] for c in ("fazer", "execucao", "verificacao", "concluida")}
    abertas = col["fazer"] + col["execucao"]
    piso = (hoje - timedelta(days=janela)).isoformat()
    atrasadas = sorted((o for o in abertas if o["prazo"] == "atrasada"), key=lambda o: (o["dias"], o["os"]))
    vencem = sorted((o for o in abertas if o["prazo"] == "vence"), key=lambda o: (o["dias"], o["os"]))
    fechadas = sorted((o for o in col["concluida"] if (o["fim_iso"] or "") >= piso), key=lambda o: o["fim_iso"], reverse=True)
    # em verificação a OS já foi feita: espera desde o fim da execução (a tarefa fechada); sem ele, a data programada
    verif = sorted(col["verificacao"], key=lambda o: (o["fim_iso"] or o["programada_iso"] or "9999", o["os"]))
    carga = len(abertas) + len(col["verificacao"])

    def os_(o):
        return (f"OS {o['os']}", True)

    k_aberto = {"rotulo": "Em aberto", "valor": carga, "grav": "",
                "nota": [(str(len(col["fazer"])), True), (" a fazer, ", False), (str(len(col["execucao"])), True),
                         (" em execução e ", False), (str(len(col["verificacao"])), True), (" em verificação", False)]
                if carga else [("nenhuma OS em aberto", False)]}
    k_atraso = {"rotulo": "Atrasadas", "valor": len(atrasadas), "grav": "critico" if atrasadas else "",
                "nota": [("a mais atrasada: ", False), os_(atrasadas[0]), (f", {_dias(-atrasadas[0]['dias'])}", False)]
                if atrasadas else [("nenhuma passou da data programada", False)]}
    if vencem:
        d = vencem[0]["dias"]
        nota_vence = [("a próxima: ", False), os_(vencem[0]),
                      (", vence " + ("hoje" if d == 0 else "amanhã" if d == 1 else f"em {_dias(d)}"), False)]
    else:
        nota_vence = [(f"nenhuma até {hoje + timedelta(days=2):%d/%m}", False)]
    k_vence = {"rotulo": "Vencem em 2 dias", "valor": len(vencem), "grav": "alerta" if vencem else "", "nota": nota_vence}
    grav_verif, nota_verif = "", [("nenhuma esperando", False)]
    if verif:
        o = verif[0]
        desde = o["fim_iso"] or o["programada_iso"]
        espera = max(0, (hoje - date.fromisoformat(desde)).days) if desde else None
        if o["fim_iso"]:
            quando = "feita hoje" if espera == 0 else "feita ontem" if espera == 1 else f"feita há {_dias(espera)}"
        else:
            quando = f"programada {o['programada'][:5]}" if o["programada"] else "sem data"
        nota_verif = [("a mais antiga: ", False), os_(o), (f", {quando}", False)]
        grav_verif = "alerta" if espera is not None and espera > ESPERA_VERIFICACAO else ""
    k_verif = {"rotulo": "Esperando verificação", "valor": len(verif), "grav": grav_verif, "nota": nota_verif}
    k_fechadas = {"rotulo": f"Fechadas em {janela} dias", "valor": len(fechadas), "grav": "ok" if fechadas else "",
                  "nota": [("a última: ", False), os_(fechadas[0]), (f", em {fechadas[0]['fim'][:5]}", False)]
                  if fechadas else [(f"nenhuma nos últimos {janela} dias", False)]}
    return [k_aberto, k_atraso, k_vence, k_verif, k_fechadas]


@bp.route("/equipe")
def equipe():
    """O clique numa OS abre o card dela do OS Creator, o mesmo do Histórico (Levi, 08/10/2026: "Ao clicar na OS quero
    que abra o mesmo card que aparece quando clicamos em uma OS no histórico do OS Creator Web ... precisamos fazer os
    setores se conversarem"). Quem muda a OS por ele volta com ?atualizar=1, e o quadro relê o Fracttal na hora."""
    from ...engenharia import os_equipe
    os_equipe.marcar_uso()          # o quadro segue relido por trás nas próximas 2 h (`os_equipe.manter_quente`)
    if request.args.get("atualizar") == "1":
        os_equipe.pedir_releitura(esperar=True, forcar=True)
    else:
        os_equipe.pedir_releitura(esperar=not os_equipe.dados()["lido"])
    d = os_equipe.dados()
    hoje = datetime.now(BRT).date()
    cards = supercards(d["os"], d["equipe"], hoje)
    cor = {c["id"]: c["cor"] for c in cards}
    ini = {c["id"]: c["iniciais"] for c in cards}          # as do supercard (pelo nome no Fracttal)
    oss = [dict(o, cor=cor.get(o["pid"], CORES_PESSOA[-1]), iniciais=ini.get(o["pid"]) or _iniciais(o["pessoa"]))
           for o in d["os"]]
    piso = (hoje - timedelta(days=JANELA_CONCLUIDAS)).isoformat()
    return render_template(
        "engenharia/equipe.html", torre=TORRE, tela=TORRE.tela("equipe"), cards=cards, oss=oss,
        kpis=faixa_kpis(oss, hoje, JANELA_CONCLUIDAS),
        faltam=d["faltam"], erro=d["erro"], colunas=os_equipe.COLUNAS,
        hoje=hoje.isoformat(), piso_concluidas=piso, janela=JANELA_CONCLUIDAS, dias_faixa=DIAS_FAIXA,
        lido=datetime.fromtimestamp(d["lido"], BRT).strftime("%H:%M") if d["lido"] else "—")
