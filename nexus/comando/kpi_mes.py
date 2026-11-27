"""O PR e a disponibilidade de cada usina em cada mês, com e sem o expurgo do contrato, já calculados (27/11/2026).

Levi, 27/11/2026, sobre a aba Indicadores dos contratos: "Eu tô sentindo falta do PR ponderado, PR expurgado [...] Pode
até criar um book sobre isso para você não ficar carregando, calculando toda vez que abre"; "Disponibilidade expurgada
também, mesma lógica do PR expurgado"; "Pense que a gente está fazendo uma visão gerencial para o CEO, para os heads".

- **Grão:** 1 linha = 1 usina × 1 mês. Foto periódica: o mês em curso muda a cada volta; o mês fechado congela.
- **De onde vem:** a conta da Visão gerencial (`gerencial.montar`, a mesma do Comando), que junta o PR e a meta do mês
  da Performance (`fato_meta_usina_mes`, desde 10/2026), a disponibilidade do Fracttal e do COS e o expurgo do contrato
  (`expurgos.aplicar`: a queda da rede e a limitação imposta saem da conta; `pr_exp = pr × (prod + E) ÷ prod`). O chat da
  Performance confirmou em 26/11/2026 que não há outro: é o `com_expurgo` da Visão gerencial.
- **O mês congela** no dia `CONGELA_DIA` do mês seguinte (o fechamento do Dashboard Thopen é no dia 10): depois dele, a
  linha que está no banco fica como foi gravada. Antes, cada volta troca a linha pela conta nova. A linha que está no
  banco e não veio na conta (a usina que saiu do cadastro) fica: o livro não encolhe.
- **Quem grava:** o laço do app (`ligar`), de hora em hora no :47, na máquina que tiver o token do banco; grava só se a
  última gravação tiver mais de 50 min e se as linhas mudaram (o sha na `atualizacao`). `NEXUS_KPI_PUBLICAR=0` desliga.
- **Quem lê:** a aba Indicadores (`ler`), pela cópia de 10 min; sem o livro, a aba faz a conta como antes.
- **Sem nome, sem texto livre:** só IDs, o cliente (código) e números (regra 8). O texto do expurgo fica na conta viva.
- **O histórico antes de 10/2026** (Levi, 27/11/2026: "por que não temos dados antes do livro. Tem muitos que a gente tem
  esse dado [...] faz o cálculo, bota lá no livro"): o banco de performance publicado pela Plataforma só tem os meses
  desde 10/2026 (a disponibilidade, desde 09/2026), mas o `nexus_geracao · fato_geracao_usina_dia` (a geração, a
  irradiação e a disponibilidade de cada usina e dia, das BDs) vai até 01/2025. `linhas_do_historico` faz o mês dali,
  marcado `fonte = historico bd`, uma vez (o mês fica congelado):
  - o PR = a energia do mês ÷ (a irradiação ÷ 1 kW/m² × a potência que a Performance usa, a `pot_kwp` da conta), com a
    irradiação do DIA pela média das abas (a usina de duas abas, "Coração 1 e 2", somava as duas e o PR caía à metade) e
    20 dias ou mais com irradiação. SÓ na usina em que a mesma conta bate com o PR da Performance nos meses em comum
    (`CONFERE_PR`, 3 pontos): medido em 27/11/2026, 77 de 97 usinas em 10/2026 e 64 de 78 em 11/2026; as que não batem
    são quase todas da Thopen, cuja irradiação na BD não é a que a Performance usa, e ficam sem o histórico (não se chuta);
  - a disponibilidade = a média do dia da BD (em fração: 0,98 = 98%), com 20 dias ou mais, e o mês todo zerado fica fora
    (a BD da Thopen tem out e nov/26 zerados: ainda não lançados). Conferida em 09/2026 contra a disponibilidade da
    Performance: 74 de 74 usinas da Thopen iguais;
  - o expurgo não tem registro antes de 10/2026 (o COS começa em 01/10/2026): as colunas expurgadas ficam vazias.
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import threading
import time
from datetime import date, datetime, timedelta, timezone

from ..dados import livros

log = logging.getLogger("nexus.comando.kpi_mes")

LIVRO, ABA = "nexus_kpi_usina_mes", "fato_kpi_usina_mes"
NOME_LIVRO = "Nexus · o PR e a disponibilidade de cada usina em cada mês, com e sem o expurgo do contrato"
FATO, TIPO = "kpi_usina_mes", "snapshot_periodico"
GRAO = "1 linha = 1 usina × 1 mês (o PR e a disponibilidade do mês, com e sem o expurgo do contrato)"
CHAVE = ("kpi_id",)
FONTES = (("nexus_performance", "fato_meta_usina_mes"), ("falhas_performance", "disponibilidade_dia"),
          ("nexus_cos_normalizacoes", "fato_normalizacao"), ("nexus_geracao", "fato_geracao_usina_dia"))
JANELA_ORIGEM = "desde 10/2026 pela Visão gerencial e antes disso pelo histórico das BDs (nexus_geracao, desde 01/2025)"
LIGADA_POR = "visao gerencial"   # a usina já vem ligada na conta (o cadastro), regra 5
LIGADA_POR_HIST = "nexus_geracao"
FONTE_CONTA, FONTE_HIST = "visao gerencial", "historico bd"
INICIO_CONTA = "2026-10"         # o 1º mês do banco de performance (`diagnostico_mes.PRIMEIRO_MES`)
CONFERE_PR = 3.0                 # pontos de PR entre a conta da BD e a da Performance nos meses em comum
DIAS_MIN = 20
CAB = ["kpi_id", "data_id_mes", "usina_id", "usina_ligada_por", "cliente", "potencia_kwp", "pr_pct", "pr_exp_pct", "disp_pct",
       "disp_exp_pct", "prod_kwh", "meta_kwh", "mes_fechado", "calculado_em", "fonte"]
# (coluna, unidade, soma). Nenhuma soma entre usinas: o PR e a disponibilidade do contrato são a média pela potência.
# a potencia_kwp é atributo da linha (o peso da média do contrato), não medida: o kWp não é unidade da regra 3
MEDIDAS = (("pr_pct", "%", "nao"), ("pr_exp_pct", "%", "nao"), ("disp_pct", "%", "nao"),
           ("disp_exp_pct", "%", "nao"), ("prod_kwh", "kWh", "aditiva"), ("meta_kwh", "kWh", "aditiva"),
           ("mes_fechado", "1/0", "nao"))
CAB_ATUALIZACAO = ["gerado_em", "linhas", "sha_linhas", "meses_congelados", "como_ler"]
COMO_LER = ("1 linha = 1 usina × 1 mês; data_id_mes = o dia 1º do mês (AAAAMM01); pr_exp_pct e disp_exp_pct com o "
            "expurgo do contrato (a queda da rede e a limitação imposta); o contrato pondera pela potencia_kwp; "
            "mes_fechado 1 = congelado")
PR_MAX = 100.0                   # o PR acima de 100% é leitura errada (a régua da Visão gerencial)
CONGELA_DIA = 11                 # o mês fechado congela no dia 11 do seguinte (o Thopen fecha no dia 10)
INTERVALO_MIN = 50
PRIMEIRA_S = 900                 # a 1ª volta 15 min depois de subir: a conta da Visão gerencial esquenta antes
MINUTO_DA_HORA = 47
DESENCONTRO_MAX_S = 300
COPIA_S = 600
_BRT = timezone(timedelta(hours=-3))
_LACO = {"thread": None, "parar": threading.Event(), "ultimo": None}
_COPIA: dict = {}


# ── a conta (pura) ─────────────────────────────────────────────────────────────────────────────────────────────────
def _num(v, casas=2):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    return round(f, casas)


def _pct(v):
    f = _num(v)
    return f if f != "" and 0 < f <= PR_MAX else ""


def congelado(mes: str, hoje: date) -> bool:
    """O mês "AAAA-MM" já fechou e passou do dia `CONGELA_DIA` do seguinte."""
    a, m = int(mes[:4]), int(mes[5:7])
    a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return hoje >= date(a, m, CONGELA_DIA)


def linhas_do_portfolio(g: dict, agora: datetime) -> list[list]:
    """As linhas do livro a partir da conta da Visão gerencial (`gerencial.montar`): uma por usina e mês que tem PR ou
    disponibilidade. O mês que ainda não chegou fica fora."""
    hoje, iso = agora.date(), agora.isoformat(timespec="seconds")
    mes_hoje = hoje.isoformat()[:7]
    out = []
    for c in g.get("clientes") or []:
        for u in c.get("usinas") or []:
            uid = u.get("uid")
            if uid in (None, ""):
                continue
            kwp_cad = _num((u.get("mwp") or 0) * 1000, 0) if u.get("mwp") else ""
            for mid, mm in sorted((u.get("meses") or {}).items()):
                if mid > mes_hoje:
                    continue
                mm = mm or {}
                kwp = _num(mm.get("pot_kwp"), 0) if mm.get("pot_kwp") else kwp_cad
                ex = (u.get("com_expurgo") or {}).get(mid) or {}
                pr, disp = _pct(mm.get("pr")), _pct(mm.get("disp"))
                pr_e, disp_e = _pct(ex.get("pr")), _pct(ex.get("disp"))
                if pr == "" and disp == "" and pr_e == "" and disp_e == "":
                    continue
                out.append([f"{uid}-{mid.replace('-', '')}", int(mid.replace("-", "") + "01"), int(uid), LIGADA_POR,
                            str(c.get("cliente") or ""), kwp, pr, pr_e if pr_e != "" else pr, disp,
                            disp_e if disp_e != "" else disp, _num(mm.get("prod_kwh"), 0), _num(mm.get("meta_kwh"), 0),
                            1 if mid < mes_hoje else 0, iso, FONTE_CONTA])
    return sorted(out, key=lambda l: (l[1], l[2]))


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def linhas_do_historico(geracao: list[dict], g: dict, agora: datetime) -> tuple[list[list], dict]:
    """(as linhas dos meses antes de `INICIO_CONTA`, o relatório só com contagens) a partir do `fato_geracao_usina_dia`
    e da conta da Visão gerencial (a potência, o cliente e o PR da Performance para conferir). Ver o cabeçalho."""
    iso = agora.isoformat(timespec="seconds")
    info = {}                                    # uid: (cliente, kWp da Performance, {mês: PR da Performance})
    for c in g.get("clientes") or []:
        for u in c.get("usinas") or []:
            try:
                uid = int(u.get("uid"))
            except (TypeError, ValueError):
                continue
            meses = u.get("meses") or {}
            kwp = next((_f(mm.get("pot_kwp")) for _m, mm in sorted(meses.items(), reverse=True) if (mm or {}).get("pot_kwp")), None)
            kwp = kwp or ((_f(u.get("mwp")) or 0) * 1000 or None)
            info[uid] = (str(c.get("cliente") or ""), kwp,
                         {mid: _f(mm.get("pr")) for mid, mm in meses.items() if _f((mm or {}).get("pr")) and 0 < _f(mm.get("pr")) <= PR_MAX})
    dia: dict = {}
    for r in geracao or []:
        try:
            uid, d = int(r.get("usina_id")), str(int(r.get("data_id")))
        except (TypeError, ValueError):
            continue
        x = dia.setdefault((uid, d), {"e": None, "h": [], "disp": []})
        e = _f(r.get("energia_medidor_kwh"))
        e = e if e is not None else _f(r.get("energia_inversores_kwh"))
        if e is not None:
            x["e"] = (x["e"] or 0) + e
        h = _f(r.get("ipoa_kwh_m2"))
        if h and h > 0:
            x["h"].append(h)
        v = _f(r.get("disponibilidade_pct"))
        if v is not None:
            x["disp"].append(v * 100 if v <= 1.5 else v)
    mes: dict = {}
    for (uid, d), x in dia.items():
        m = mes.setdefault((uid, f"{d[:4]}-{d[4:6]}"), {"e": 0.0, "h": 0.0, "dias_h": 0, "e_tot": 0.0, "disp": []})
        if x["e"] is not None:
            m["e_tot"] += x["e"]
            if x["h"]:
                m["e"] += x["e"]
                m["h"] += sum(x["h"]) / len(x["h"])        # a irradiação do dia: a média das abas, não a soma
                m["dias_h"] += 1
        if x["disp"]:
            m["disp"].append(sum(x["disp"]) / len(x["disp"]))

    def pr_de(uid, m):
        kwp = (info.get(uid) or (None, None))[1]
        if not kwp or m["dias_h"] < DIAS_MIN or m["h"] <= 0:
            return None
        v = m["e"] / (m["h"] * kwp) * 100
        return round(v, 2) if 0 < v <= PR_MAX else None
    # a conferência: a mesma conta contra o PR da Performance nos meses em comum
    confere: dict = {}
    for (uid, mid), m in mes.items():
        if mid < INICIO_CONTA or uid not in info or mid not in info[uid][2]:
            continue
        v = pr_de(uid, m)
        if v is not None:
            confere.setdefault(uid, []).append(abs(v - info[uid][2][mid]) <= CONFERE_PR)
    validas = {uid for uid, oks in confere.items() if oks and all(oks)}
    out, rel = [], {"usinas_pr": set(), "usinas_disp": set(), "pr_sem_conferir": len({u for u in info} - set(confere)),
                    "pr_nao_bate": len(set(confere) - validas)}
    for (uid, mid), m in sorted(mes.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if mid >= INICIO_CONTA or uid not in info:
            continue
        pr = pr_de(uid, m) if uid in validas else None
        disp = None
        if len(m["disp"]) >= DIAS_MIN and any(v > 0 for v in m["disp"]):        # o mês todo zerado não foi lançado
            disp = round(sum(m["disp"]) / len(m["disp"]), 2)
        if pr is None and disp is None:
            continue
        rel["usinas_pr"].update([uid] if pr is not None else [])
        rel["usinas_disp"].update([uid] if disp is not None else [])
        kwp = info[uid][1]
        out.append([f"{uid}-{mid.replace('-', '')}", int(mid.replace("-", "") + "01"), uid, LIGADA_POR_HIST, info[uid][0],
                    _num(kwp, 0) if kwp else "", pr if pr is not None else "", "", disp if disp is not None else "", "",
                    _num(m["e_tot"], 0) if m["e_tot"] else "", "", 1, iso, FONTE_HIST])
    rel = {k: (len(v) if isinstance(v, set) else v) for k, v in rel.items()}
    rel["meses"] = sorted({l[1] // 100 for l in out})
    return out, rel


def mesclar(banco: list[dict], novas: list[list], hoje: date, refazer=()) -> tuple[list[list], int]:
    """(as linhas a gravar, quantas ficaram congeladas do banco). O mês congelado que está no banco fica como está; o
    que não está no banco entra pela conta (o 1º retrato dele). A linha do banco que não veio na conta fica. `refazer` =
    os meses ("AAAA-MM") que a conta troca mesmo congelados (o conserto de um mês gravado errado)."""
    i = {c: n for n, c in enumerate(CAB)}
    do_banco = {str(r.get("kpi_id")): [r.get(c, "") for c in CAB] for r in banco or [] if r.get("kpi_id")}
    out, congeladas = dict(do_banco), 0
    for l in novas:
        k = l[i["kpi_id"]]
        mes = str(l[i["data_id_mes"]])
        if k in do_banco and congelado(f"{mes[:4]}-{mes[4:6]}", hoje) and f"{mes[:4]}-{mes[4:6]}" not in refazer:
            congeladas += 1
            continue
        out[k] = l
    return sorted(out.values(), key=lambda l: (int(l[i["data_id_mes"]] or 0), int(l[i["usina_id"]] or 0))), congeladas


def sha(linhas: list[list]) -> str:
    """O sha das linhas sem a hora do cálculo: o mesmo número de antes não regrava o livro."""
    corte = CAB.index("calculado_em")
    return hashlib.sha1(json.dumps([l[:corte] for l in linhas], default=str).encode()).hexdigest()[:16]


def por_usina(linhas: list[dict]) -> dict:
    """{usina_id: {"AAAA-MM": {pr, pr_exp, disp, disp_exp, kwp, prod_kwh, meta_kwh, cliente}}} a partir das linhas do
    livro (como a API devolve: números podem vir como texto)."""
    out: dict = {}
    for r in linhas or []:
        try:
            uid, mes = int(r.get("usina_id")), str(int(r.get("data_id_mes")))
        except (TypeError, ValueError):
            continue

        def f(c):
            v = _num(r.get(c))
            return None if v == "" else v
        out.setdefault(uid, {})[f"{mes[:4]}-{mes[4:6]}"] = {
            "pr": f("pr_pct"), "pr_exp": f("pr_exp_pct"), "disp": f("disp_pct"), "disp_exp": f("disp_exp_pct"),
            "kwp": f("potencia_kwp"), "prod_kwh": f("prod_kwh"), "meta_kwh": f("meta_kwh"),
            "cliente": str(r.get("cliente") or ""), "fonte": str(r.get("fonte") or FONTE_CONTA)}
    return out


# ── o banco ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _base(config) -> str:
    from ..cadastro.ligacoes import BASE_API
    return (config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")


def _ultima(base, sessao) -> datetime | None:
    v = livros.atualizado_em(base, sessao, LIVRO)
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00")) if v else None
    except ValueError:
        return None
    return d if d is None or d.tzinfo else d.replace(tzinfo=timezone.utc)


# a conta sem uma das fontes do expurgo gravaria o expurgado igual ao bruto: em 27/11/2026 o livro foi gravado do PC, que
# não tem a carga dos contratos (sem a cláusula de expurgo, nada sai da conta), e outubro congelou sem o expurgo. Com um
# destes avisos na conta, a volta não grava
AVISOS_QUE_TRAVAM = ("os contratos", "expurgo")


def publicar(config, portfolio: dict | None = None, *, sessao=None, agora=None, forcar=False, historico=False,
             geracao: list[dict] | None = None, refazer=()) -> dict:
    """Uma volta: confere a última gravação, faz a conta (ou usa o `portfolio` dado, nos testes), mescla com o banco e
    grava se mudou. Devolve só contagens."""
    import requests
    s = sessao or requests.Session()
    base = _base(config)
    agora = agora or datetime.now(_BRT)
    if not config.get("GRIDCO_SQL_TOKEN"):
        return {"erro": "sem GRIDCO_SQL_TOKEN: não grava"}
    if not forcar:
        u = _ultima(base, s)
        if u and agora - u < timedelta(minutes=INTERVALO_MIN):
            return {"pulou": f"a última gravação é de {u.astimezone(_BRT).isoformat(timespec='minutes')}"}
    if portfolio is None:
        from ..torres.comando.gerencial_tela import dados_gerencial
        portfolio = dados_gerencial()
    falta = [a for a in portfolio.get("avisos") or [] if any(t in str(a) for t in AVISOS_QUE_TRAVAM)]
    if falta:
        return {"recusou": "a conta saiu sem uma fonte do expurgo (" + "; ".join(falta) + "): o livro fica como está"}
    novas = linhas_do_portfolio(portfolio, agora)
    if not novas:
        return {"recusou": "a conta da Visão gerencial saiu sem nenhum mês: o livro fica como está"}
    banco = livros.ler(base, s, LIVRO, ABA)
    rel_hist = {}
    if historico or not any(str(r.get("fonte") or "") == FONTE_HIST for r in banco):
        # o histórico das BDs entra uma vez (o mês dele já está congelado); `historico=True` refaz
        hist, rel_hist = linhas_do_historico(geracao if geracao is not None else livros.ler(base, s, "nexus_geracao", "fato_geracao_usina_dia"),
                                             portfolio, agora)
        chaves = {l[0] for l in novas}
        novas = novas + [l for l in hist if l[0] not in chaves]
    todas, congeladas = mesclar(banco, novas, agora.date(), refazer)
    if len({l[0] for l in todas}) != len(todas):
        return {"recusou": "usina e mês repetidos: o grão quebrou; o livro fica como está"}
    h = sha(todas)
    antes = next((str(r.get("sha_linhas") or "") for r in livros.ler(base, s, LIVRO, "atualizacao")), "")
    rel = {"linhas": len(todas), "da_conta": len(novas), "congeladas": congeladas, **({"historico": rel_hist} if rel_hist else {})}
    if h == antes and not forcar:
        return dict(rel, pulou="as linhas não mudaram")
    atu = [agora.isoformat(timespec="seconds"), len(todas), h, congeladas, COMO_LER]
    rel["gravado"] = livros.publicar(LIVRO, NOME_LIVRO, {ABA: (CAB, todas), "atualizacao": (CAB_ATUALIZACAO, [atu])},
                                     base=base, token=config["GRIDCO_SQL_TOKEN"], sessao=s)
    _COPIA.clear()
    return rel


def ler(config) -> dict:
    """{usina_id: {"AAAA-MM": {...}}} do livro, na cópia de 10 min; {} quando o livro não existe ou não abre (a aba
    faz a conta como antes)."""
    if config.get("TESTING"):
        return {}                    # teste não fala com a rede (quem quer o livro troca esta função)
    if _COPIA.get("dados") is not None and time.time() - _COPIA.get("ts", 0) < COPIA_S:
        return _COPIA["dados"]
    import requests
    try:
        dados = por_usina(livros.ler(_base(config), requests.Session(), LIVRO, ABA))
    except Exception as e:           # noqa: BLE001 — o banco fora: a aba faz a conta
        log.warning("o livro dos KPIs não abriu: %s", type(e).__name__)
        dados = {}
    _COPIA.update(dados=dados, ts=time.time())
    return dados


def ligar(app):
    """O laço: a 1ª volta 15 min depois de subir, depois a cada hora, no :47 mais o atraso sorteado. Não liga onde
    `NEXUS_KPI_PUBLICAR=0`. Quem chama é o app.py e o servir.py, nunca o create_app: teste não fala com a rede."""
    if _LACO["thread"] is not None or str(app.config.get("NEXUS_KPI_PUBLICAR", "1")).strip() == "0":
        return
    desencontro = random.uniform(0, DESENCONTRO_MAX_S)

    def espera():
        agora = datetime.now(_BRT)
        alvo = agora.replace(minute=MINUTO_DA_HORA, second=0, microsecond=0) + timedelta(seconds=desencontro)
        if alvo <= agora:
            alvo += timedelta(hours=1)
        return (alvo - agora).total_seconds()

    def laco():
        primeira = True
        while not _LACO["parar"].wait(PRIMEIRA_S if primeira else espera()):
            primeira = False
            with app.app_context():
                try:
                    _LACO["ultimo"] = publicar(app.config)
                    log.info("KPIs de usina e mês no banco: %s", {k: v for k, v in _LACO["ultimo"].items() if k != "gravado"})
                except Exception as e:      # noqa: BLE001 — o laço não morre por uma volta
                    _LACO["ultimo"] = {"erro": f"{type(e).__name__}: {e}"[:300]}
                    log.warning("KPIs de usina e mês: a volta falhou: %s", _LACO["ultimo"]["erro"])
    t = threading.Thread(target=laco, name="nexus-kpi-mes", daemon=True)
    _LACO["thread"] = t
    t.start()
