"""As contas da tela Engenharia > Confiabilidade (06/10/2026; Levi: "traga a aba Confiabilidade do pcm.gridco.com.br,
não referenciando diretamente esse caminho mas construindo algo nosso!").

As regras são as do robô do PCM (`gerar_engenharia_json.py` e `gerar_confiabilidade_json.py` do gridco-pcm-data), para
os números baterem; o que muda é o dado e a ligação:
- a fonte é a nossa leitura das OS de falha do Fracttal (`os_falhas.py`), não o JSON do site;
- o ativo é o CÓDIGO dele, que já traz a usina (IBI200-INVR1.3). No PCM o MTBF de cada ativo era casado pelo NOME (26
  letras), sem a usina: o "Inversor 1.3" de Ibirapuã 2 saía com o MTBF de 8.406 h do "Inversor 1.3" de Cipó Guaçu
  (o dele é 466 h). 318 dos 1.338 nomes se repetem entre usinas;
- usina, cliente, cluster e a data de mobilização vêm do cadastro do Nexus (o registro mestre), pelo de-para do
  Fracttal; sem ligação, o que o Fracttal escreve;
- OS cancelada não entra em nada (no PCM ela entrava nos sinais dos 30 dias).

Sinais (30 dias, só corretiva e corretiva emergencial; serviço registrado como corretiva não conta como falha):
  A = falhas em 30 dias; B = falhas em 7 dias; D = falhas acima do P90 da família (o padrão é 2).
  Nível: crítico se A >= 4 ou B >= 3; atenção se A >= 3 ou B >= 2 ou acima do P90; monitorar se A >= 2. Criticidade A
  sobe monitorar para atenção. Só serviço (nenhuma falha e 2 OS ou mais) fica em monitorar, para reclassificar.
Método do Power BI (por ativo; corretiva, corretiva emergencial, religamento e religamento remoto, desde 20/10/2025):
  MTBF = (horas desde a mobilização efetiva - horas paradas) / nº de falhas; MTTR = média por falha, do incidente ao
  fim (dias x 24 até 1 dia, dias x 12 acima: 12 h de sol por dia); disponibilidade = MTBF / (MTBF + MTTR).
"""
import collections
import re
import statistics
from datetime import datetime, timedelta, timezone

JANELA_DIAS = 30
META_DISP = 0.85
TIPOS_SINAL = {"corretiva", "corretiva emergencial"}
INICIO_METODO = datetime(2025, 10, 20, tzinfo=timezone(timedelta(hours=-3)))
MAX_OS = 8
OS_URL = "https://one.fracttal.com/tasks/wo/{id}"
RX_SERVICO = re.compile(
    r"limpeza|ensaio|teste\b|testes\b|revis[ãa]o|readequa|projeto|avcb|ajuste de antena|"
    r"\breset\b|vistoria|inventári|levantamento|instala[çc][ãa]o de|treinamento|acompanhamento", re.I)
RX_TESTE = re.compile(r"\bTESTE\b", re.I)
RX_TESTE_COD = re.compile(r"^TESTE|TESTE\d|\bTESTE\b", re.I)
RX_COD = re.compile(r"\{\s*([A-Z0-9][A-Z0-9\-\.]+)\s*\}")
# Criticidade por família, enquanto a matriz real não existe: 5 critérios de 0 a 3 multiplicados.
# 0-55 = A, 56-161 = B, 162-243 = C (a mesma do PCM).
CRIT_PROXY = {"Transformador": (1, 1, 2, 1, 1), "Cabine": (1, 2, 2, 1, 1), "Inversor": (2, 2, 2, 2, 2),
              "QGBT": (2, 2, 2, 2, 2), "Tracker": (3, 3, 3, 2, 3), "Outros": (2, 3, 3, 2, 3)}
NIVEIS = (("critico", "Crítico", "critico"), ("atencao", "Atenção", "alerta"), ("monitorar", "Monitorar", "info"))
FAMILIAS = ("Inversor", "Tracker", "Cabine", "Transformador", "QGBT", "Outros")


def familia(cod: str, nome: str) -> str:
    s = f"{cod} {nome}"
    if re.search(r"INV|inversor", s, re.I):
        return "Inversor"
    if re.search(r"TRK|ETKR|tracker", s, re.I):
        return "Tracker"
    if re.search(r"CAB|cabine", s, re.I):
        return "Cabine"
    if re.search(r"TRF|SKID|transformador", s, re.I):
        return "Transformador"
    if re.search(r"QGBT", s, re.I):
        return "QGBT"
    return "Outros"


def criticidade(fam: str) -> tuple[int, str]:
    v = 1
    for x in CRIT_PROXY.get(fam, (2, 2, 2, 2, 2)):
        v *= x
    return v, ("A" if v <= 55 else "B" if v <= 161 else "C")


def _dt(v):
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _horas(a, b) -> float:
    return max(0.0, (b - a).total_seconds() / 3600.0) if a and b else 0.0


def _teste(r) -> bool:
    return bool(RX_TESTE.search(str(r.get("items_log_description") or ""))
                or RX_TESTE_COD.search(str(r.get("code") or ""))
                or RX_TESTE_COD.search(str(r.get("groups_1_description") or "")))


def _codigo(r) -> str:
    nome = str(r.get("items_log_description") or "")
    m = RX_COD.search(nome)
    return m.group(1) if m else str(r.get("code") or "").strip()


def metodo(falhas: list[dict], mob_eff: datetime, agora: datetime) -> dict:
    """MTBF, MTTR e disponibilidade de um conjunto de falhas (o `bloco` do Power BI)."""
    ini = [(_dt(r.get("initial_date")), _dt(r.get("final_date"))) for r in falhas]
    parado = sum(_horas(i, f or agora) for i, f in ini if i and i >= mob_eff)
    uptime = max(0.0, _horas(mob_eff, agora) - parado)
    n = sum(1 for i, _f in ini if i and i >= INICIO_METODO)
    mtbf = uptime / n if n else None
    reparos = []
    for r in falhas:
        ev, fim = _dt(r.get("event_date")), _dt(r.get("final_date"))
        if ev and fim and fim >= ev:
            d = (fim - ev).total_seconds() / 86400.0
            reparos.append(d * 12 if d * 24 > 24 else d * 24)
    mttr = sum(reparos) / len(reparos) if reparos else None
    disp = mtbf / (mtbf + mttr) if (mtbf and mttr is not None and mtbf + mttr > 0) else None
    return {"mtbf": mtbf, "mttr": mttr, "disp": disp, "n": n}


def _mediana(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def calcular(linhas: list[dict], onde, agora: datetime | None = None) -> dict:
    """`linhas`: as OS de falha (`os_falhas.linhas()`); `onde(texto_usina, codigo)` -> {usina_id, usina, cliente,
    cluster, mobilizacao, ligada_por}: a ligação com o cadastro (a torre passa a do Campo · App)."""
    agora = agora or datetime.now(timezone.utc)
    inicio_janela = agora - timedelta(days=JANELA_DIAS)
    por = collections.defaultdict(list)
    sem_codigo = 0
    for r in linhas:
        if _teste(r):
            continue
        cod = _codigo(r)
        if not cod:
            sem_codigo += 1
            continue
        por[cod].append(r)

    ativos = {}
    for cod, rs in por.items():
        r0 = max(rs, key=lambda r: str(r.get("creation_date") or ""))
        # sem o código e sem a marca ou o endereço que vêm depois de 2+ espaços (o limpa_ativo do PCM)
        nome = re.split(r"\s{2,}", RX_COD.sub("", str(r0.get("items_log_description") or "")).strip())[0] or cod
        lug = onde(str(r0.get("groups_1_description") or ""), cod)
        mob = lug.get("mobilizacao")
        mob_eff = max(mob, INICIO_METODO) if mob else INICIO_METODO
        m = metodo(rs, mob_eff, agora)
        fam = familia(cod, nome)
        cv, cl = criticidade(fam)
        janela = []
        for r in rs:
            cr = _dt(r.get("creation_date"))
            if cr and cr >= inicio_janela and str(r.get("tasks_log_task_type_main") or "").strip().lower() in TIPOS_SINAL:
                texto = f"{r.get('description') or ''} {r.get('task_note') or ''}"
                janela.append(dict(r, _cr=cr, _servico=bool(RX_SERVICO.search(texto))))
        pai = [s.strip() for s in str(r0.get("parent_description") or "").split("/") if s.strip()]
        ativos[cod] = {"cod": cod, "nome": nome[:60], "fam": fam, "crit": cl, "critVal": cv, **lug,
                       "circuito": " / ".join(pai[2:]) if len(pai) > 2 else "", **m, "janela": janela}

    # P90 por família, contando só as falhas (serviço fora)
    fam_ns = collections.defaultdict(list)
    for a in ativos.values():
        nf = sum(1 for r in a["janela"] if not r["_servico"])
        if nf:
            fam_ns[a["fam"]].append(nf)
    p90 = {f: sorted(n)[int(round(.9 * (len(n) - 1)))] for f, n in fam_ns.items()}

    sinais, crit_dist = [], collections.Counter()
    com_corretiva = 0
    for a in ativos.values():
        rs = sorted(a["janela"], key=lambda r: r["_cr"], reverse=True)
        if not rs:
            continue
        com_corretiva += 1
        crit_dist[a["crit"]] += 1
        falhas = [r for r in rs if not r["_servico"]]
        n = len(falhas)
        n7 = sum(1 for r in falhas if (agora - r["_cr"]).days <= 7)
        pf = p90.get(a["fam"], 2)
        nivel = ("critico" if (n >= 4 or n7 >= 3) else
                 "atencao" if (n >= 3 or n7 >= 2 or n > pf) else
                 "monitorar" if n >= 2 else None)
        if nivel == "monitorar" and a["crit"] == "A":
            nivel = "atencao"
        so_servico = n == 0 and len(rs) >= 2
        if so_servico:
            nivel = "monitorar"
        if not nivel:
            continue
        por_que = []
        if n >= 3:
            por_que.append(f"{n} falhas em {JANELA_DIAS} dias")
        if n7 >= 2:
            por_que.append(f"{n7} falhas em 7 dias")
        if n > pf:
            por_que.append(f"acima do P90 da família {a['fam']} ({pf})")
        if nivel == "atencao" and a["crit"] == "A" and not por_que:
            por_que.append("criticidade A: 2 falhas já pedem atenção")
        if so_servico:
            por_que = [f"{len(rs)} OS registradas como corretiva, todas de serviço (reclassificar)"]
        sinais.append({k: v for k, v in a.items() if k != "janela"} | {
            "n30": len(rs), "nFalha": n, "nServico": len(rs) - n, "n7": n7, "p90": pf, "nivel": nivel,
            "soServico": so_servico, "porQue": por_que,
            "os": [{"os": str(r.get("wo_folio") or ""), "t": str(r.get("description") or "")[:80],
                    "nota": str(r.get("task_note") or "")[:220],
                    "url": OS_URL.format(id=r["id_work_order"]) if r.get("id_work_order") else "",
                    "d": r["_cr"].astimezone(timezone(timedelta(hours=-3))).strftime("%d/%m %H:%M"),
                    "tipo": str(r.get("tasks_log_task_type_main") or ""), "st": str(r.get("task_status") or ""),
                    "quem": str(r.get("personnel_description") or r.get("requested_by") or "").strip(),
                    "prio": str(r.get("priorities_description") or ""), "servico": r["_servico"]}
                   for r in rs[:MAX_OS]]})
    ordem = {"critico": 0, "atencao": 1, "monitorar": 2}
    sinais.sort(key=lambda a: (ordem[a["nivel"]], a["soServico"], -a["nFalha"], -a["n30"]))

    confi = [a for a in ativos.values() if a["n"]]
    disps = [a["disp"] for a in confi if a["disp"] is not None]
    kpi = {"disp": _mediana(disps), "mtbf": _mediana([a["mtbf"] for a in confi]),
           "mttr": _mediana([a["mttr"] for a in confi]), "abaixo": sum(1 for x in disps if x < META_DISP),
           "ativosConf": len(disps), "corretivas": sum(len(a["janela"]) for a in ativos.values()),
           "ativosCorretiva": com_corretiva, "ativosSinal": len(sinais),
           "criticos": sum(1 for a in sinais if a["nivel"] == "critico")}
    # onde está o problema: por família, as falhas dos 30 dias (serviço fora), os ativos com corretiva e com sinal
    fams = collections.defaultdict(lambda: {"falhas": 0, "ativos": 0, "sinais": 0})
    for a in ativos.values():
        if a["janela"]:
            fams[a["fam"]]["ativos"] += 1
            fams[a["fam"]]["falhas"] += sum(1 for r in a["janela"] if not r["_servico"])
    for s in sinais:
        fams[s["fam"]]["sinais"] += 1
    familias = sorted(({"fam": f, **v, "p90": p90.get(f, 2)} for f, v in fams.items()), key=lambda x: -x["falhas"])
    return {"kpi": kpi, "p90": p90, "critDist": dict(crit_dist), "sinais": sinais, "familias": familias,
            "ativos": [{k: v for k, v in a.items() if k != "janela"} for a in confi], "semCodigo": sem_codigo,
            "periodo": {"de": inicio_janela, "ate": agora}}


def indicadores(ativos: list[dict], sinais: list[dict], por: str) -> list[dict]:
    """Por cliente ou por usina: ativos com histórico, as medianas de disponibilidade, MTBF e MTTR DOS ATIVOS e os
    sinais. Mediana dos ativos, e não a conta do grupo inteiro: no PCM a disponibilidade agregada somava as falhas da
    frota toda e dava Athon 14% (o aviso fixo de lá)."""
    g = collections.defaultdict(lambda: {"ativos": [], "sinais": 0, "criticos": 0, "falhas30": 0})
    for a in ativos:
        g[a.get(por) or "—"]["ativos"].append(a)
    for s in sinais:
        x = g[s.get(por) or "—"]
        x["sinais"] += 1
        x["criticos"] += s["nivel"] == "critico"
        x["falhas30"] += s["nFalha"]
    out = []
    for nome, x in g.items():
        ds = [a["disp"] for a in x["ativos"] if a["disp"] is not None]
        out.append({"nome": nome, "ativos": len(x["ativos"]), "disp": _mediana(ds),
                    "usinas": len({a.get("usina") for a in x["ativos"] if a.get("usina")}),
                    "eventos": sum(a.get("n") or 0 for a in x["ativos"]),
                    "mtbf": _mediana([a["mtbf"] for a in x["ativos"]]), "mttr": _mediana([a["mttr"] for a in x["ativos"]]),
                    "abaixo": sum(1 for d in ds if d < META_DISP), "sinais": x["sinais"], "criticos": x["criticos"],
                    "falhas30": x["falhas30"]})
    return sorted(out, key=lambda r: (-r["criticos"], -r["sinais"], r["nome"]))
