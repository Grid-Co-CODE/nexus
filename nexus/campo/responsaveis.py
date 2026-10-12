"""Visão do responsável (12/10/2026): as usinas de cada Responsável O&M, com a meta do mês, a disponibilidade, os ativos
que estão falhando, o tempo do COS para abrir a OS, os chamados abertos, as rondas e as PT, e onde ele deve focar e o
que pode esperar.

Levi, 12/10/2026: "Agora temos em um canto só as metas da performance, a disponibilidade, o tanto que o ativo parou, o
tempo que o COS demora para abrir a OS, os chamados, rondas, PTs e APRs / Precisamos criar uma visão que os supervisores
irão usar, uma visão que ele olha as usinas, as metas, os problemas, onde ele deve focar, no que ele deve deixar. No caso
seria separado por responsável".

NENHUM indicador é refeito aqui com régua nova: cada número é o da tela dona dele, da mesma fonte, e cada alerta usa a
régua da tela dona (`REGUAS`, que a tela mostra). O que é nosso é só juntar tudo pela usina do cadastro (`usina_id`) e
ordenar o foco. As fontes:
- meta do mês: o Gerencial da plataforma publicado no banco (`nexus_performance · fato_meta_usina_mes`,
  plataforma/gerencial_publicar.py), os números da Visão gerencial;
- disponibilidade: o diário do Gerencial › Disponibilidade (`falhas_performance · disponibilidade_dia`); o mês é a média
  dos dias (a régua de lá é 12 h de sol por dia, então a média dos dias é a disponibilidade do mês);
- ativos que falham: os sinais da Engenharia › Confiabilidade (OS de falha do Fracttal, últimos 30 dias);
- tempo do COS: a régua do Acompanhamento COS da plataforma (`mtta.py`), portada em `_mtta`, sobre as mesmas OS de falha;
- chamados: as ocorrências sem fim nas abas Strings indisp e Trackers do `tickets_performance`;
- rondas e PT: as contas da Central de atenção e de APR e PT (`visao.atencao`, `visao.pts`).

Cada fonte é lida à parte (regra 13 da casa: peça que falha não para as outras): a que falhou some da conta, e a tela diz
qual foi. Responsável O&M = o da ficha da usina (`usinas.responsavel_om_id`), o mesmo da Central de atenção. Só usina
MOBILIZADA (a régua das rondas). Cópia de 5 min, refeita em segundo plano (`visao._ler`).
"""
import collections
import re
import statistics
import unicodedata
from datetime import datetime, timedelta, timezone

from . import visao

LIVRO_META, ABA_META = "nexus_performance", "fato_meta_usina_mes"
LIVRO_DISP, ABA_DISP = "falhas_performance", "disponibilidade_dia"
LIVRO_TICKETS = "tickets_performance"
ABAS_CHAMADOS = (("Strings indisp", "strings"), ("Trackers", "trackers"))
# Na aba Trackers, "Em conformidade" na coluna Status é o check periódico, não ocorrência (734 das 1.094 linhas eram
# check em 31/08; ver nexus/torres/oscreator/os_creator/tickets_diario.py): só as outras são chamado
TRACKER_CHECK = "EM CONFORMIDADE"
# os sistemas do de-para em que a chave é o NOME da usina como a planilha escreve (o Gerencial, o diário da
# disponibilidade e os tickets usam esses nomes: "Santa Bárbara I", "Boa Esperança do Sul 1 e 2")
SISTEMAS_NOME = ("BD_Thopen · aba", "BD_Performance · aba", "BD_Thopen · Dados Gerais Usinas",
                 "BD_Performance · Base UFV", "Tickets · Base de dados - Usinas")

# ── As réguas (cada uma é a da tela dona; a tela mostra este texto) ───────────────────────────────────────────────
META_NA_META = 97        # Visão gerencial (atgTag): 97% ou mais = "Na meta"
META_ATENCAO = 90        # de 90% a 97% = "Atenção"; abaixo de 90% = "Abaixo"
DISP_OK = 99             # Disponibilidade (classePill): 99% ou mais = verde
DISP_CRITICO = 80        # abaixo de 80% = vermelho; entre os dois, âmbar
MTTA_ATENCAO_MIN = 60    # o COS não tem meta: a faixa da tela vai até "1 a 2 h"; mediana acima de 1 h pede atenção
MTTA_DIAS = 30
MTTA_TIPOS = ("religamento", "religamento remoto", "corretiva emergencial")   # os da Disponibilidade e do COS
MTTA_CARIMBO_S = 10      # evento até 10 s antes da criação = carimbo do app, não reconhecimento (mtta.py)
STATUS_CANCELADA = 4

REGUAS = (
    ("meta", "Meta do mês", "Visão gerencial da plataforma: atingimento abaixo de 90% é crítico (Abaixo), de 90% a 97% é "
                            "atenção, 97% ou mais está na meta. PR abaixo do PR previsto é atenção."),
    ("disp", "Disponibilidade", "Gerencial › Disponibilidade: abaixo de 80% é crítico, de 80% a 99% é atenção, 99% ou "
                                "mais está ok. O mês é a média dos dias fechados."),
    ("ativos", "Ativos falhando", "Engenharia › Confiabilidade, últimos 30 dias: crítico com 4 falhas em 30 dias ou 3 em "
                                  "7; atenção com 3 em 30, 2 em 7 ou acima do P90 da família; monitorar pode esperar."),
    ("mtta", "Tempo do COS", "Acompanhamento COS, a mesma régua (do evento até a OS no Fracttal; religamentos e "
                             "corretiva emergencial; cada queda conta uma vez). O COS não tem meta: mediana dos últimos "
                             "30 dias acima de 1 h é atenção."),
    ("chamados", "Chamados", "Tickets de performance: ocorrência de string ou de tracker sem fim registrado é atenção."),
    ("ronda", "Rondas", "Central de atenção: nunca teve ronda, ou sem ronda há 7 dias ou mais, é crítico; ronda longa "
                        "pendente é atenção."),
    ("pt", "PT e APR", "APR e PT: PT esperando o De acordo há mais de 2 h é crítico; se é de hoje, vai para o topo "
                       "(técnico parado no campo agora). Esperando há menos de 2 h, atenção."),
)
ROTULO_AREA = {a: r for a, r, _t in REGUAS}
# O foco: PT parada DE HOJE vem antes de tudo (é gente parada no campo agora); depois crítico e atenção. A PT parada de
# dias anteriores continua crítica (a régua da Central), mas sem o "agora": medido em 12/10/2026, 33 das 34 PT esperando
# eram de 1 a 6 dias atrás (nunca decididas no App), e todas no topo enterravam a única de hoje
PESO = {"agora": 20, "critico": 10, "atencao": 3}
NIVEIS = ("critico", "atencao", "ok")


# ── Nome da planilha -> usina do cadastro ───────────────────────────────────────────────────────────────────────
_ROMANOS = {"I": "1", "II": "2", "III": "3", "IV": "4", "V": "5", "VI": "6", "VII": "7", "VIII": "8", "IX": "9",
            "X": "10", "XI": "11", "XII": "12"}


def norm_nome(s) -> str:
    """Sem acento, sem caixa, pontuação vira espaço e romano vira número ("Santa Bárbara I" = "santa barbara 1"): é a
    regra que a Disponibilidade da plataforma usa para casar o PG com o BD (`norm2`)."""
    t = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().upper()
    return " ".join(_ROMANOS.get(p, p) for p in re.sub(r"[^A-Z0-9]+", " ", t).split())


class Nomes:
    """Liga o nome que a planilha escreve à usina do cadastro. Ordem: o de-para publicado dos sistemas de nome
    (`SISTEMAS_NOME`), o nome do cadastro e, por último, o nome do Fracttal (de-para "Fracttal · Classificação 1") ou o
    código do ativo. Nome que serve a duas usinas não liga (regra 4: ligação errada é pior que faltando). Medido em
    12/10/2026 com o Gerencial: 139 das 161 usinas ligam (131 pelo de-para, 4 pelo nome, 4 pelo Fracttal); as 22 que
    sobram são usinas fora do Full O&M (Ouro Branco, Delmiro Gouveia), que não estão mobilizadas no cadastro."""

    def __init__(self, b):
        por = collections.defaultdict(set)
        for d in b.de_para:
            uid = visao.D._id(d.get("usina_id"))
            if uid and str(d.get("sistema") or "").strip() in SISTEMAS_NOME and norm_nome(d.get("chave_externa")):
                por[norm_nome(d.get("chave_externa"))].add(uid)
        self.por_de_para = {k: next(iter(v)) for k, v in por.items() if len(v) == 1}
        nomes = collections.defaultdict(set)
        for uid, u in b.por_id.items():
            if str(u.get("excluido") or "").strip().lower() != "sim" and norm_nome(u.get("nome")):
                nomes[norm_nome(u.get("nome"))].add(uid)
        self.por_nome = {k: next(iter(v)) for k, v in nomes.items() if len(v) == 1}
        self.lig = b.lig

    def usina(self, nome, fracttal="", codigo="") -> tuple:
        n = norm_nome(nome)
        if n and n in self.por_de_para:
            return self.por_de_para[n], "de-para"
        if n and n in self.por_nome:
            return self.por_nome[n], "nome do cadastro"
        c = norm_nome(codigo)
        if c and c in self.por_de_para:
            return self.por_de_para[c], "de-para"
        # por último, o Fracttal (o nome "Cliente - Usina - UF" do de-para) ou o código: medido em 12/10/2026, a aba
        # Strings indisp escreve o código no lugar do nome em boa parte das linhas ("ACB100", "MRJ100"), e o
        # "Código da usina" vem vazio; o código do cadastro só liga quando é de UMA usina
        uid, como = self.lig.usina(str(fracttal or nome or ""), str(codigo or nome or ""))
        return (uid, como) if uid else (None, None)


def _num(v):
    if isinstance(v, bool) or v in (None, ""):
        return None
    try:
        x = float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _int(v):
    x = _num(v)
    return int(x) if x is not None else None


# ── Meta do mês (Gerencial da plataforma, publicado no banco) ───────────────────────────────────────────────────
def metas(nomes: Nomes, mes_id: int) -> tuple[dict, dict]:
    """{usina_id: produção, meta, atingimento, PR e PR previsto do mês} pelas linhas do Gerencial. Usina do cadastro
    com duas linhas no Gerencial (Santarém 1 e Santarém 2 são a "Santarém 1 e 2"): a produção e a meta somam e o
    atingimento é refeito sobre a soma (o Gerencial faz atingimento = produção ÷ meta); o PR é a média das linhas
    pesada pela meta. Uma linha só: os números dela, sem conta."""
    todas = visao._livro(LIVRO_META, ABA_META)
    do_mes = [r for r in todas if _int(r.get("mes_id")) == mes_id]
    por, sem = collections.defaultdict(list), []
    for r in do_mes:
        uid, _como = nomes.usina(r.get("usina"))
        if uid:
            por[uid].append(r)
        else:
            sem.append(str(r.get("usina") or ""))
    out = {}
    for uid, rs in por.items():
        if len(rs) == 1:
            r = rs[0]
            ating, pr, prm = _num(r.get("atingimento_pct")), _num(r.get("pr_pct")), _num(r.get("pr_meta_pct"))
        else:
            com_meta = [r for r in rs if _num(r.get("meta_kwh")) and _num(r.get("prod_kwh")) is not None]
            m = sum(_num(r["meta_kwh"]) for r in com_meta)
            ating = round(100 * sum(_num(r["prod_kwh"]) for r in com_meta) / m, 1) if m else None
            com_pr = [r for r in com_meta if _num(r.get("pr_pct")) is not None and _num(r.get("pr_meta_pct")) is not None]
            mp = sum(_num(r["meta_kwh"]) for r in com_pr)
            pr = round(sum(_num(r["pr_pct"]) * _num(r["meta_kwh"]) for r in com_pr) / mp, 1) if mp else None
            prm = round(sum(_num(r["pr_meta_pct"]) * _num(r["meta_kwh"]) for r in com_pr) / mp, 1) if mp else None
        prod = [_num(r.get("prod_kwh")) for r in rs if _num(r.get("prod_kwh")) is not None]
        meta = [_num(r.get("meta_kwh")) for r in rs if _num(r.get("meta_kwh")) is not None]
        cob = [_int(r.get("dias_cobertos_qtd")) for r in rs if _int(r.get("dias_cobertos_qtd")) is not None]
        out[uid] = {"prod_kwh": sum(prod) if prod else None, "meta_kwh": sum(meta) if meta else None,
                    "atingimento": ating, "pr": pr, "pr_meta": prm, "dias_cob": min(cob) if cob else None,
                    "dias_mes": _int(rs[0].get("dias_mes_qtd")), "full_om": any(_int(r.get("full_om")) == 1 for r in rs),
                    "linhas": [str(r.get("usina") or "") for r in rs]}
    meses = sorted({_int(r.get("mes_id")) for r in todas if _int(r.get("mes_id"))})
    return out, {"publicado": bool(todas), "linhas": len(do_mes), "ligadas": sum(len(v) for v in por.values()),
                 "sem_usina": sorted(sem), "ultimo_mes": meses[-1] if meses else None}


# ── Disponibilidade (Gerencial › Disponibilidade, o diário publicado) ───────────────────────────────────────────
def disponibilidade(nomes: Nomes, mes: str) -> tuple[dict, dict]:
    """{usina_id: disponibilidade do mês (%), horas perdidas, dias, potência}. Por usina do Gerencial, a média dos dias
    fechados (a régua de lá: 100·(1 − h/12) por dia, e 12 h × dias no mês: a média dos dias é o mês). Usina do cadastro
    com duas do Gerencial (Aparecida do Taboado 1 e 2): pesadas pela potência, como o resumo por cliente de lá."""
    linhas = [r for r in visao._livro(LIVRO_DISP, ABA_DISP) if str(r.get("mes") or "") == mes]
    por_nome = {}
    for r in linhas:
        n = str(r.get("usina") or "").strip()
        d = _num(r.get("disp"))
        if not n or d is None:
            continue
        x = por_nome.setdefault(n, {"dias": [], "h": 0.0, "pot": _num(r.get("pot_kwp")),
                                    "fracttal": str(r.get("usina_fracttal") or "")})
        x["dias"].append(d)
        x["h"] += _num(r.get("h_perdidas")) or 0.0
    por, sem = collections.defaultdict(list), []
    for n, x in por_nome.items():
        uid, _como = nomes.usina(n, fracttal=x["fracttal"])
        if uid:
            por[uid].append(x)
        else:
            sem.append(n)
    out = {}
    for uid, xs in por.items():
        pesos = [(x["pot"] or 1.0) for x in xs]
        tot = sum(pesos)
        disp = sum(p * (sum(x["dias"]) / len(x["dias"])) for p, x in zip(pesos, xs)) / tot
        out[uid] = {"disp": round(disp, 2), "h_perdidas": round(sum(p * x["h"] for p, x in zip(pesos, xs)) / tot, 1),
                    "dias": max(len(x["dias"]) for x in xs), "pot_kwp": sum(x["pot"] or 0 for x in xs) or None}
    ate = max((str(r.get("dia") or "") for r in linhas), default="")
    return out, {"publicado": bool(linhas), "ate": ate, "usinas": len(por_nome), "sem_usina": sorted(sem)}


# ── Ativos falhando (Engenharia › Confiabilidade) ───────────────────────────────────────────────────────────────
def _engenharia() -> dict:
    """Os dados da Confiabilidade, com a cópia dela (as OS de falha do Fracttal lidas em segundo plano)."""
    from ..torres import engenharia
    return engenharia._dados()


def ativos() -> tuple[dict, dict]:
    """{usina_id: quantos ativos em crítico, atenção e monitorar, e os 3 piores}: os sinais da Confiabilidade, sem
    régua nova (o nível é o de lá). Ativo sem usina no cadastro fica fora (não há de quem ele seja)."""
    from ..engenharia import os_falhas
    g = _engenharia()
    d = g.get("dados") or {}
    por = collections.defaultdict(lambda: {"critico": 0, "atencao": 0, "monitorar": 0, "lista": []})
    for s in d.get("sinais") or []:
        uid = s.get("usina_id")
        if not uid or s.get("nivel") not in ("critico", "atencao", "monitorar"):
            continue
        x = por[uid]
        x[s["nivel"]] += 1
        x["lista"].append({"nome": s.get("nome") or s.get("cod") or "", "cod": s.get("cod") or "", "fam": s.get("fam") or "",
                           "nivel": s["nivel"], "porque": "; ".join(s.get("porQue") or []),
                           "falhas": s.get("nFalha") or 0, "url": ((s.get("os") or [{}])[0] or {}).get("url", "")})
    est = os_falhas.estado()
    return dict(por), {"completa": est.get("completa", False), "lendo": est.get("lendo", False),
                       "sem_cadastro": g.get("sem_cadastro", False), "sinais": len(d.get("sinais") or [])}


# ── Tempo do COS (a régua do Acompanhamento COS, plataforma/mtta.py) ────────────────────────────────────────────
_BRT = timezone(timedelta(hours=-3))


def _dt_fx(s):
    """ISO do Fracttal -> datetime com fuso; sem fuso, Brasília (o `mtta.dt` da plataforma)."""
    if not s:
        return None
    try:
        x = datetime.fromisoformat(str(s).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return x if x.tzinfo else x.replace(tzinfo=_BRT)


def _eh_teste(w) -> bool:
    cod = str(w.get("code") or "").upper()
    return cod.startswith("TESTE") or cod == "THPN-TESTE" or "TESTE - PA" in str(w.get("parent_description") or "")


def _site(w) -> str:
    """O site da OS: o `groups_1_description`, ou o 2º trecho do caminho do ativo, ou o próprio ativo (`mtta.site_de`)."""
    s = " ".join(str(w.get("groups_1_description") or "").split())
    if s:
        return s
    segs = [p.strip() for p in str(w.get("parent_description") or "").strip("/ ").split("/") if p.strip()]
    if len(segs) >= 2:
        return " ".join(segs[1].split())
    ild = re.sub(r"\s*\{[^}]*\}\s*$", "", str(w.get("items_log_description") or ""))
    return " ".join(re.split(r"\s{2,}", ild, maxsplit=1)[0].split())


def mtta(b, linhas, agora) -> tuple[dict, dict]:
    """{usina_id: mediana, quantas quedas e a maior, em minutos}: do evento até a OS aparecer no Fracttal, nos últimos
    30 dias, pela régua da plataforma (`mtta.montar`): Religamento, Religamento Remoto e Corretiva Emergencial; cancelada
    e planta de teste fora; OS com várias tarefas usa o evento mais antigo; evento depois da criação, ou carimbado no
    segundo da criação, não é reconhecimento (fora); e cada queda conta uma vez (o lote: o mesmo operador, o mesmo site e
    o mesmo minuto de evento em várias OS, a caixa "lote conta 1 vez" da tela do COS). A usina vem do site pelo de-para
    do Fracttal (ou do código do ativo)."""
    por_os = {}
    for w in linhas:
        if " ".join(str(w.get("tasks_log_task_type_main") or "").split()).lower() not in MTTA_TIPOS:
            continue
        f = str(w.get("wo_folio") or "")
        if not f or _int(w.get("id_status_work_order")) == STATUS_CANCELADA or _eh_teste(w):
            continue
        e = _dt_fx(w.get("event_date"))
        if e is not None and (f not in por_os or e < por_os[f][0]):
            por_os[f] = (e, w)
    piso = agora - timedelta(days=MTTA_DIAS)
    oss = []
    for f, (e, w) in por_os.items():
        c = _dt_fx(w.get("creation_date"))
        if c is None or e < piso:
            continue
        seg = (c - e).total_seconds()
        if seg < MTTA_CARIMBO_S:
            continue
        site = _site(w)
        uid, _como = b.lig.usina(site, str(w.get("code") or ""))
        oss.append((c, re.sub(r"\s", "", str(w.get("created_by") or "")).casefold(), site,
                    e.replace(second=0, microsecond=0), seg / 60, uid))
    vistos, por_uid, sem = set(), collections.defaultdict(list), 0
    for c, op, site, ev_min, minutos, uid in sorted(oss, key=lambda o: o[0]):
        if (op, site, ev_min) in vistos:
            continue
        vistos.add((op, site, ev_min))
        if uid:
            por_uid[uid].append(minutos)
        else:
            sem += 1
    out = {uid: {"mediana_min": round(statistics.median(v), 1), "n": len(v), "max_min": round(max(v), 1)}
           for uid, v in por_uid.items()}
    return out, {"quedas": sum(len(v) for v in por_uid.values()), "sem_usina": sem}


# ── Chamados (tickets de performance sem fim) ───────────────────────────────────────────────────────────────────
def _dia(v) -> str:
    s = str(v or "").strip()
    return s[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else ""


def _com_prefixo(prefixo: str, valor) -> str:
    """ "Inversor 5.4" a partir de "5.4" ou de "Inversor 5.4" (a planilha escreve dos dois jeitos: sem isto, a tela
    mostrava "Inversor Inversor 5.4")."""
    v = str(valor or "").strip() or "—"
    return v if v.lower().startswith(prefixo.lower()) else f"{prefixo} {v}"


def chamados(nomes: Nomes, hoje_iso: str) -> tuple[dict, dict]:
    """{usina_id: abertos, de strings e de trackers, o mais antigo e a lista}: as ocorrências sem "Fim da ocorrência"
    nas abas Strings indisp e Trackers (na de trackers, sem o check periódico "Em conformidade"). A usina liga pelo
    nome que a planilha escreve (`Nomes`; o "Código da usina" quase sempre vem vazio)."""
    por = collections.defaultdict(lambda: {"abertos": 0, "strings": 0, "trackers": 0, "mais_antigo": "", "lista": []})
    sem = collections.Counter()
    for aba, tipo in ABAS_CHAMADOS:
        for r in visao._livro(LIVRO_TICKETS, aba):
            nome = str(r.get("Usina") or "").strip()
            if not nome or str(r.get("Fim da ocorrência") or "").strip():
                continue
            if tipo == "trackers" and norm_nome(r.get("Status")) == TRACKER_CHECK:
                continue
            uid, _como = nomes.usina(nome, codigo=r.get("Código da usina"))
            if not uid:
                sem[nome] += 1
                continue
            x = por[uid]
            ini = _dia(r.get("Início da ocorrência"))
            x["abertos"] += 1
            x[tipo] += 1
            if ini and (not x["mais_antigo"] or ini < x["mais_antigo"]):
                x["mais_antigo"] = ini
            if tipo == "strings":
                o_que = _com_prefixo("Inversor", r.get("Inversor"))
                qtd = _int(r.get("Quantidade de strings no afetadas"))
                if qtd:
                    o_que += f" · {qtd} string{'s' if qtd != 1 else ''}"
            else:
                o_que = _com_prefixo("Tracker", r.get("Nº do tracker / Identificação"))
                qtd = _int(r.get("Quantidade de trackers parados"))
                if qtd and qtd > 1:
                    o_que += f" · {qtd} parados"
            x["lista"].append({"tipo": tipo, "o_que": o_que, "inicio": ini,
                               "causa": str(r.get("Causa raiz") or "").strip()[:80]})
    hoje = datetime.fromisoformat(hoje_iso).date()
    for x in por.values():
        x["lista"].sort(key=lambda c: c["inicio"] or "9999")
        x["dias"] = (hoje - datetime.fromisoformat(x["mais_antigo"]).date()).days if x["mais_antigo"] else None
    return dict(por), {"sem_usina": sum(sem.values()), "nomes_sem_usina": sorted(sem)[:30]}


# ── Juntar por usina, os alertas e o foco ───────────────────────────────────────────────────────────────────────
def _pct(x, casas=0) -> str:
    if x is None:
        return "—"
    return (f"{x:.{casas}f}".replace(".", ",")) + "%"


def _duracao(m) -> str:
    m = int(round(m or 0))
    if m >= 1440:
        return f"{m // 1440} d {(m % 1440) // 60} h"
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


def alertas(u: dict) -> tuple[list[dict], list[str]]:
    """Os alertas da usina (o que pede ação, com o nível da régua da tela dona) e o que está bem (para dizer por que ela
    pode esperar). Fonte sem dado da usina não alerta nem elogia: fica "—" na tabela."""
    al, bem = [], []
    m = u.get("meta")
    if m and m.get("atingimento") is not None:
        a = m["atingimento"]
        if a < META_ATENCAO:
            al.append({"area": "meta", "nivel": "critico", "titulo": f"Meta do mês em {_pct(a)}",
                       "detalhe": "abaixo de 90% (a Visão gerencial chama de Abaixo)"})
        elif a < META_NA_META:
            al.append({"area": "meta", "nivel": "atencao", "titulo": f"Meta do mês em {_pct(a)}",
                       "detalhe": "entre 90% e 97%"})
        else:
            bem.append(f"na meta ({_pct(a)})")
    if m and m.get("pr") is not None and m.get("pr_meta") is not None and m["pr"] < m["pr_meta"]:
        al.append({"area": "meta", "nivel": "atencao", "titulo": f"PR {_pct(m['pr'], 1)} abaixo do previsto",
                   "detalhe": f"previsto {_pct(m['pr_meta'], 1)}"})
    d = u.get("disp")
    if d and d.get("disp") is not None:
        x = d["disp"]
        h = f"{d['h_perdidas']:.1f}".replace(".", ",") + " h paradas no mês"
        if x < DISP_CRITICO:
            al.append({"area": "disp", "nivel": "critico", "titulo": f"Disponibilidade {_pct(x, 1)}", "detalhe": h})
        elif x < DISP_OK:
            al.append({"area": "disp", "nivel": "atencao", "titulo": f"Disponibilidade {_pct(x, 1)}", "detalhe": h})
        else:
            bem.append(f"disponibilidade {_pct(x, 1)}")
    at = u.get("ativos") or {}
    for nivel in ("critico", "atencao"):
        lista = [a for a in at.get("lista") or [] if a["nivel"] == nivel]
        if lista:
            # o nome do ativo vai uma vez só, nos itens, com o porquê (no detalhe e nos itens ele aparecia duas vezes)
            al.append({"area": "ativos", "nivel": nivel,
                       "titulo": f"{len(lista)} ativo{'s' if len(lista) != 1 else ''} "
                                 f"{'em crítico' if nivel == 'critico' else 'pedindo atenção'}",
                       "detalhe": "", "itens": lista[:3], "n_itens": len(lista)})
    if at and not at.get("critico") and not at.get("atencao"):
        bem.append("nenhum ativo em crítico ou atenção")
    t = u.get("mtta")
    if t and t.get("mediana_min") is not None:
        if t["mediana_min"] > MTTA_ATENCAO_MIN:
            al.append({"area": "mtta", "nivel": "atencao", "titulo": f"COS leva {_duracao(t['mediana_min'])} para abrir a OS",
                       "detalhe": f"mediana de {t['n']} queda{'s' if t['n'] != 1 else ''} em 30 dias"})
        else:
            bem.append(f"COS abre a OS em {_duracao(t['mediana_min'])}")
    c = u.get("chamados") or {}
    if c.get("abertos"):
        partes = [f"{c[k]} de {k}" for k in ("strings", "trackers") if c.get(k)]
        al.append({"area": "chamados", "nivel": "atencao",
                   "titulo": f"{c['abertos']} chamado{'s' if c['abertos'] != 1 else ''} aberto{'s' if c['abertos'] != 1 else ''}",
                   "detalhe": " e ".join(partes) + (f"; o mais antigo há {c['dias']} dias" if c.get("dias") else ""),
                   "itens": c.get("lista", [])[:3], "n_itens": len(c.get("lista", []))})
    else:
        bem.append("sem chamado aberto")
    r = u.get("ronda") or {}
    if r.get("tipo") in ("nunca", "sem_ronda"):
        al.append({"area": "ronda", "nivel": "critico",
                   "titulo": "Nunca teve ronda" if r["tipo"] == "nunca" else f"Sem ronda há {r['dias']} dias",
                   "detalhe": r.get("obs") or ""})
    elif r.get("tipo") == "longa_pendente":
        al.append({"area": "ronda", "nivel": "atencao", "titulo": "Ronda longa pendente", "detalhe": r.get("obs") or ""})
    elif r.get("dias") is not None and r["dias"] < 999:
        bem.append("ronda " + ("hoje" if r["dias"] == 0 else ("ontem" if r["dias"] == 1 else f"há {r['dias']} dias")))
    p = u.get("pt") or {}
    grupos_pt = (("agora", lambda x: x["hoje"] and x["parada"], "técnico esperando o De acordo"),
                 ("critico", lambda x: not x["hoje"] and x["parada"], "confira se ainda está aberta no App"),
                 ("atencao", lambda x: not x["parada"], "há menos de 2 h"))
    for nivel, de_quem, detalhe in grupos_pt:
        lista = [x for x in p.get("lista", []) if de_quem(x)]
        if not lista:
            continue
        n = len(lista)
        titulo = {"agora": f"{n} PT parada{'s' if n != 1 else ''} há mais de 2 h",
                  "critico": f"{n} PT sem decisão desde {_dm(p.get('desde'))}",
                  "atencao": f"{n} PT esperando o De acordo"}[nivel]
        al.append({"area": "pt", "nivel": nivel, "titulo": titulo, "detalhe": detalhe, "itens": lista[:3],
                   "n_itens": n})
    return al, bem


def _dm(iso) -> str:
    s = str(iso or "")
    return f"{s[8:10]}/{s[5:7]}" if len(s) >= 10 else "—"


def _nivel(al) -> str:
    if any(a["nivel"] in ("agora", "critico") for a in al):
        return "critico"
    return "atencao" if al else "ok"


def foco(u: dict) -> int:
    return sum(PESO[a["nivel"]] for a in u["alertas"])


def ordem_do_foco(u: dict):
    """A usina que mais pede o responsável em cima: o peso dos alertas; no empate, a mais longe da meta e o nome."""
    ating = (u.get("meta") or {}).get("atingimento")
    return (-u["foco"], ating if ating is not None else 999, u["usina"])


def _pt_vazia() -> dict:
    return {"aguardando": 0, "paradas": 0, "paradas_hoje": 0, "paradas_antigas": 0, "desde": "", "lista": []}


def montar(b, usinas_ronda, pendentes, pts, fontes, hoje) -> list[dict]:
    """Uma linha por usina MOBILIZADA, com o que cada fonte diz dela, os alertas, o que está bem e o peso do foco.
    `hoje` = o dia de Brasília (a PT parada de hoje é a do técnico parado agora)."""
    ronda = {u.get("usina_id"): u for u in usinas_ronda}
    pend = {x.get("usina_id"): x for x in pendentes}
    pt = collections.defaultdict(_pt_vazia)
    for x in pts:
        if x.get("usina_id"):
            p = pt[x["usina_id"]]
            criada = x.get("criada")
            dia = criada.astimezone(_BRT).date().isoformat() if hasattr(criada, "astimezone") else ""
            de_hoje = dia == hoje.isoformat()
            p["aguardando"] += 1
            if x.get("parada"):
                p["paradas"] += 1
                p["paradas_hoje" if de_hoje else "paradas_antigas"] += 1
                if not de_hoje and dia and (not p["desde"] or dia < p["desde"]):
                    p["desde"] = dia
            p["lista"].append({"numero": x.get("numero"), "codigo": x.get("codigo"), "os": x.get("os"),
                               "tarefa": str(x.get("tarefa") or "")[:70], "idade_min": x.get("idade_min"),
                               "parada": bool(x.get("parada")), "hoje": de_hoje, "dia": dia})
    out = []
    for uid in b.mobilizadas:
        o = b.onde(uid)
        r = dict(ronda.get(uid) or {})
        if uid in pend:
            r.update(tipo=pend[uid].get("tipo"), obs=pend[uid].get("obs"))
        u = {"usina_id": uid, **{k: o[k] for k in ("usina", "uf", "cidade", "equipe", "cliente", "regiao_campo",
                                                  "gestor", "responsavel", "cluster")},
             "meta": fontes["metas"].get(uid), "disp": fontes["disp"].get(uid), "ativos": fontes["ativos"].get(uid),
             "mtta": fontes["mtta"].get(uid), "chamados": fontes["chamados"].get(uid), "ronda": r,
             "pt": pt.get(uid) or _pt_vazia()}
        u["alertas"], u["bem"] = alertas(u)
        u["alertas"].sort(key=lambda a: -PESO[a["nivel"]])
        u["nivel"], u["foco"] = _nivel(u["alertas"]), foco(u)
        out.append(u)
    out.sort(key=ordem_do_foco)
    return out


def soma(nome: str, usinas: list[dict]) -> dict:
    """O resumo de um grupo de usinas (um responsável, ou o filtro da tela): quantas pedem foco (crítico), quantas pedem
    acompanhamento (atenção) e quantas podem esperar; a meta do grupo (produção ÷ meta das usinas com meta, a conta do
    Gerencial), a disponibilidade média pesada pela potência (o resumo por cliente de lá), as PT esperando, paradas e
    paradas de hoje, as rondas pendentes, os chamados abertos, os ativos em crítico e a mediana do COS (das quedas de
    todas as usinas do grupo não dá: a tela dona não publica a queda; é a mediana das medianas, dito na nota)."""
    s = {"responsavel": nome, "usinas": len(usinas), "critico": 0, "atencao": 0, "ok": 0, "pts": 0, "paradas": 0,
         "agora": 0, "rondas": 0, "chamados": 0, "ativos_criticos": 0, "pior": []}
    prod = meta = disp_p = pot = 0.0
    cos = []
    for u in usinas:
        s[u["nivel"]] += 1
        m = u.get("meta") or {}
        if m.get("prod_kwh") is not None and m.get("meta_kwh"):
            prod += m["prod_kwh"]
            meta += m["meta_kwh"]
        d = u.get("disp") or {}
        if d.get("disp") is not None:
            p = d.get("pot_kwp") or 1.0
            disp_p += p * d["disp"]
            pot += p
        if (u.get("mtta") or {}).get("mediana_min") is not None:
            cos.append(u["mtta"]["mediana_min"])
        s["pts"] += u["pt"]["aguardando"]
        s["paradas"] += u["pt"]["paradas"]
        s["agora"] += u["pt"]["paradas_hoje"]
        s["rondas"] += (u.get("ronda") or {}).get("tipo") in ("nunca", "sem_ronda", "longa_pendente")
        s["chamados"] += (u.get("chamados") or {}).get("abertos", 0)
        s["ativos_criticos"] += (u.get("ativos") or {}).get("critico", 0)
    s["pior"] = [u["usina"] for u in sorted((u for u in usinas if u["nivel"] == "critico"), key=ordem_do_foco)[:3]]
    s["meta_pct"] = round(100 * prod / meta, 1) if meta else None
    s["disp"] = round(disp_p / pot, 1) if pot else None
    s["cos_min"] = round(statistics.median(cos), 1) if cos else None
    s["nivel"] = "critico" if s["critico"] else ("atencao" if s["atencao"] else "ok")
    return s


def por_responsavel(usinas: list[dict]) -> list[dict]:
    """Um cartão por Responsável O&M (`soma` das usinas dele, já filtradas pela tela). "Sem responsável O&M" por último;
    antes, quem tem mais usinas pedindo foco."""
    g = collections.defaultdict(list)
    for u in usinas:
        g[u.get("responsavel") or visao.SEM_RESPONSAVEL].append(u)
    out = [soma(nome, us) for nome, us in g.items()]
    out.sort(key=lambda s: (s["responsavel"] == visao.SEM_RESPONSAVEL, -s["critico"], -s["atencao"], s["responsavel"]))
    return out


def _ler_fonte(nome, f, erros):
    """Uma fonte (regra 13): a que falha volta vazia, e a tela diz qual foi e por quê."""
    try:
        return f()
    except Exception as e:      # noqa: BLE001 — fonte fora: as outras seguem
        erros[nome] = f"{type(e).__name__}: {str(e)[:120]}"
        return {}, {}


def visao_responsaveis() -> "visao.leitura.Leitura":
    """A conta da tela, numa cópia de 5 min (`visao._ler`)."""
    def calcular():
        b = visao._Base()
        agora = visao._agora()
        hoje = agora.date()
        at = visao.atencao(visao.DIAS_COBERTURA)
        if at.erro:
            raise visao.SemBanco(at.erro)
        pts = visao.pts()
        erros = {}
        nomes = Nomes(b)
        mes_id, mes = hoje.year * 100 + hoje.month, hoje.strftime("%Y-%m")
        met, met_i = _ler_fonte("metas", lambda: metas(nomes, mes_id), erros)
        dsp, dsp_i = _ler_fonte("disp", lambda: disponibilidade(nomes, mes), erros)
        atv, atv_i = _ler_fonte("ativos", ativos, erros)

        def _do_cos():
            from ..engenharia import os_falhas
            return mtta(b, os_falhas.linhas(), agora)
        cos, cos_i = _ler_fonte("mtta", _do_cos, erros)
        cha, cha_i = _ler_fonte("chamados", lambda: chamados(nomes, hoje.isoformat()), erros)
        if pts.erro:
            erros["pt"] = pts.erro
        fontes = {"metas": met, "disp": dsp, "ativos": atv, "mtta": cos, "chamados": cha}
        usinas = montar(b, at.dados.get("usinas") or [], at.dados.get("pendentes") or [],
                        (pts.dados or {}).get("aguardando") or [], fontes, hoje)
        responsaveis_por_pessoa = {}
        for uid in b.mobilizadas:
            pid = visao.D._id((b.por_id.get(uid) or {}).get("responsavel_om_id"))
            if pid:
                responsaveis_por_pessoa[pid] = b.responsavel_da_usina(uid)
        return {"usinas": usinas, "mes_id": mes_id, "hoje": hoje.isoformat(), "erros": erros,
                "info": {"metas": met_i, "disp": dsp_i, "ativos": atv_i, "mtta": cos_i, "chamados": cha_i},
                "responsaveis_por_pessoa": responsaveis_por_pessoa, "sem_mobilizacao": b.sem_mobilizacao,
                "fatos": at.dados.get("fatos") or {}, **visao._estrutura(b)}
    return visao._ler(("visao_responsaveis",), calcular)
