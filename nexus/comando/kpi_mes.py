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
          ("nexus_cos_normalizacoes", "fato_normalizacao"))
JANELA_ORIGEM = "desde 10/2026 (o banco de performance); este livro guarda o mês fechado como foi"
LIGADA_POR = "visao gerencial"   # a usina já vem ligada na conta (o cadastro), regra 5
CAB = ["kpi_id", "data_id_mes", "usina_id", "usina_ligada_por", "cliente", "potencia_kwp", "pr_pct", "pr_exp_pct", "disp_pct",
       "disp_exp_pct", "prod_kwh", "meta_kwh", "mes_fechado", "calculado_em"]
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
            kwp = _num((u.get("mwp") or 0) * 1000, 0) if u.get("mwp") else ""
            for mid, mm in sorted((u.get("meses") or {}).items()):
                if mid > mes_hoje:
                    continue
                mm = mm or {}
                ex = (u.get("com_expurgo") or {}).get(mid) or {}
                pr, disp = _pct(mm.get("pr")), _pct(mm.get("disp"))
                pr_e, disp_e = _pct(ex.get("pr")), _pct(ex.get("disp"))
                if pr == "" and disp == "" and pr_e == "" and disp_e == "":
                    continue
                out.append([f"{uid}-{mid.replace('-', '')}", int(mid.replace("-", "") + "01"), int(uid), LIGADA_POR,
                            str(c.get("cliente") or ""), kwp, pr, pr_e if pr_e != "" else pr, disp,
                            disp_e if disp_e != "" else disp, _num(mm.get("prod_kwh"), 0), _num(mm.get("meta_kwh"), 0),
                            1 if mid < mes_hoje else 0, iso])
    return sorted(out, key=lambda l: (l[1], l[2]))


def mesclar(banco: list[dict], novas: list[list], hoje: date) -> tuple[list[list], int]:
    """(as linhas a gravar, quantas ficaram congeladas do banco). O mês congelado que está no banco fica como está; o
    que não está no banco entra pela conta (o 1º retrato dele). A linha do banco que não veio na conta fica."""
    i = {c: n for n, c in enumerate(CAB)}
    do_banco = {str(r.get("kpi_id")): [r.get(c, "") for c in CAB] for r in banco or [] if r.get("kpi_id")}
    out, congeladas = dict(do_banco), 0
    for l in novas:
        k = l[i["kpi_id"]]
        mes = str(l[i["data_id_mes"]])
        if k in do_banco and congelado(f"{mes[:4]}-{mes[4:6]}", hoje):
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
            "cliente": str(r.get("cliente") or "")}
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


def publicar(config, portfolio: dict | None = None, *, sessao=None, agora=None, forcar=False) -> dict:
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
    novas = linhas_do_portfolio(portfolio, agora)
    if not novas:
        return {"recusou": "a conta da Visão gerencial saiu sem nenhum mês: o livro fica como está"}
    banco = livros.ler(base, s, LIVRO, ABA)
    todas, congeladas = mesclar(banco, novas, agora.date())
    if len({l[0] for l in todas}) != len(todas):
        return {"recusou": "usina e mês repetidos: o grão quebrou; o livro fica como está"}
    h = sha(todas)
    antes = next((str(r.get("sha_linhas") or "") for r in livros.ler(base, s, LIVRO, "atualizacao")), "")
    rel = {"linhas": len(todas), "da_conta": len(novas), "congeladas": congeladas}
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
