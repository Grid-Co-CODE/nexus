"""Visão do responsável (12/10/2026): as usinas de cada Responsável O&M em DOIS BLOCOS, Performance (meta, PR e
disponibilidade) e Acompanhamento (rondas, PT, chamados e extintores), cada usina numa linha compacta que abre o detalhe,
e em cada bloco onde focar e o que pode esperar.

Levi, 12/10/2026: "Precisamos criar uma visão que os supervisores irão usar, uma visão que ele olha as usinas, as metas,
os problemas, onde ele deve focar, no que ele deve deixar. No caso seria separado por responsável". Depois do 1º
desenho: "aposte em um formato reduzido que quando eu expanda aparece mais informações / Separe a visão em dois blocos
(...) Seria interessante também incluir os extintores nesse acompanhamento!", aprovado no protótipo com "só tira a parte
de Tempo do COS". E: "O nexus é um ambiente centralizado e precisamos ter os dados se conversando!".

NENHUM indicador é refeito aqui com régua nova: cada número é o da tela dona dele, da MESMA fonte que o Nexus já usa, e
cada alerta usa a régua da tela dona (`REGUAS`, que a tela mostra). O que é nosso é só juntar pela usina do cadastro
(`usina_id`) e ordenar o foco. As fontes:
- Performance
  - meta do mês: o Gerencial da plataforma publicado no banco (`nexus_performance · fato_meta_usina_mes`,
    plataforma/gerencial_publicar.py), os números da Visão gerencial;
  - disponibilidade: o diário do Gerencial › Disponibilidade (`falhas_performance · disponibilidade_dia`); o mês é a
    média dos dias (a régua de lá é 12 h de sol por dia, então a média dos dias é a disponibilidade do mês);
  - ativos que falham: os sinais da Engenharia › Confiabilidade (OS de falha do Fracttal, últimos 30 dias).
- Acompanhamento
  - rondas e PT: as contas da Central de atenção e de APR e PT (`visao.atencao`, `visao.pts`);
  - chamados: as OS de acompanhamento de chamado no banco (`nexus_chamados · fato_chamado`, o mesmo dado do quadro
    Acompanhamento de chamados; `nexus/campo/chamados_acompanhamento.py`). Até 12/10 vinham da planilha de tickets
    (`tickets_performance`): mais de 1.000 "abertos", contra 18 do quadro;
  - extintores: a conta do HSEQ (`nexus/hseq/extintores.py`, o livro que o App publica).
O Tempo do COS saiu no protótipo aprovado (12/10/2026): a régua continua na tela do COS.

Cada fonte é lida à parte (regra 13 da casa: peça que falha não para as outras): a que falhou some da conta, e a tela diz
qual foi. Responsável O&M = o da ficha da usina (`usinas.responsavel_om_id`), o mesmo da Central de atenção. Só usina
MOBILIZADA (a régua das rondas). Cópia de 5 min, refeita em segundo plano (`visao._ler`).
"""
import collections
import re
import unicodedata
from datetime import date, timedelta, timezone

from . import visao

LIVRO_META, ABA_META = "nexus_performance", "fato_meta_usina_mes"
LIVRO_DISP, ABA_DISP = "falhas_performance", "disponibilidade_dia"
LIVRO_CHAMADOS, ABA_CHAMADOS = "nexus_chamados", "fato_chamado"
LIVRO_EQUIP, ABA_EQUIP = "nexus_equipamentos", "dim_equipamento"
# os sistemas do de-para em que a chave é o NOME da usina como a planilha escreve (o Gerencial e o diário da
# disponibilidade usam esses nomes: "Santa Bárbara I", "Boa Esperança do Sul 1 e 2")
SISTEMAS_NOME = ("BD_Thopen · aba", "BD_Performance · aba", "BD_Thopen · Dados Gerais Usinas",
                 "BD_Performance · Base UFV", "Tickets · Base de dados - Usinas")

# ── As réguas (cada uma é a da tela dona; a tela mostra este texto) ───────────────────────────────────────────────
META_NA_META = 97        # Visão gerencial (atgTag): 97% ou mais = "Na meta"
META_ATENCAO = 90        # de 90% a 97% = "Atenção"; abaixo de 90% = "Abaixo"
DISP_OK = 99             # Disponibilidade (classePill): 99% ou mais = verde
DISP_CRITICO = 80        # abaixo de 80% = vermelho; entre os dois, âmbar
BLOCOS = (("perf", "Performance", "Meta, PR e disponibilidade do mês"),
          ("acomp", "Acompanhamento", "Rondas, PT, chamados e extintores"))
REGUAS = (
    ("perf", "meta", "Meta do mês", "Visão gerencial da plataforma: atingimento abaixo de 90% é crítico (Abaixo), de 90% "
                                    "a 97% é atenção, 97% ou mais está na meta. PR abaixo do PR previsto é atenção."),
    ("perf", "disp", "Disponibilidade", "Gerencial › Disponibilidade: abaixo de 80% é crítico, de 80% a 99% é atenção, "
                                        "99% ou mais está ok. O mês é a média dos dias fechados."),
    ("perf", "ativos", "Ativos falhando", "Engenharia › Confiabilidade, últimos 30 dias: crítico com 4 falhas em 30 dias "
                                          "ou 3 em 7; atenção com 3 em 30, 2 em 7 ou acima do P90 da família; monitorar "
                                          "pode esperar."),
    ("acomp", "ronda", "Rondas", "Central de atenção: nunca teve ronda, ou sem ronda há 7 dias ou mais, é crítico; ronda "
                                 "longa pendente é atenção."),
    ("acomp", "pt", "PT e APR", "APR e PT: PT esperando o De acordo há mais de 2 h é crítico; se é de hoje, vai para o "
                                "topo (técnico parado no campo agora). Esperando há menos de 2 h, atenção."),
    ("acomp", "chamados", "Chamados", "Acompanhamento de chamados: chamado de garantia em aberto com o fabricante é "
                                      "atenção (o mesmo dado do quadro, publicado no banco de hora em hora)."),
    ("acomp", "extintores", "Extintores", "Segurança · HSEQ › Extintores: recarga ou teste hidrostático vencido é "
                                          "crítico; vence em até 30 dias ou sem conferência há mais de 30 dias é atenção."),
)
ROTULO_AREA = {a: r for _b, a, r, _t in REGUAS}
BLOCO_DA_AREA = {a: b for b, a, _r, _t in REGUAS}
# O foco: PT parada DE HOJE vem antes de tudo (é gente parada no campo agora); depois crítico e atenção. A PT parada de
# dias anteriores continua crítica (a régua da Central), mas sem o "agora": medido em 12/10/2026, 33 das 34 PT esperando
# eram de 1 a 6 dias atrás (nunca decididas no App), e todas no topo enterravam a única de hoje
PESO = {"agora": 20, "critico": 10, "atencao": 3}
NIVEIS = ("critico", "atencao", "ok")
_BRT = timezone(timedelta(hours=-3))


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
    código. Nome que serve a duas usinas não liga (regra 4: ligação errada é pior que faltando). Medido em 12/10/2026
    com o Gerencial: 139 das 161 usinas ligam (131 pelo de-para, 4 pelo nome, 4 pelo Fracttal); as 22 que sobram são
    usinas fora do Full O&M (Ouro Branco, Delmiro Gouveia), que não estão mobilizadas no cadastro."""

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
        # por último, o Fracttal (o nome "Cliente - Usina - UF" do de-para) ou o código do cadastro (só de UMA usina)
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


def _dia_do_id(v) -> date | None:
    """20261012 -> date(2026, 10, 12)."""
    i = _int(v)
    try:
        return date(i // 10000, (i // 100) % 100, i % 100) if i else None
    except ValueError:
        return None


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
    com duas do Gerencial (Aparecida do Taboado 1 e 2): pesadas pela potência, como o resumo por cliente de lá. Provado
    em 12/10/2026: 129 de 130 usinas iguais à tela da plataforma (a 130ª porque a tela ao vivo revarreu depois)."""
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
    """{usina_id: quantos ativos em crítico, atenção e monitorar, e os piores}: os sinais da Confiabilidade, sem régua
    nova (o nível é o de lá). Ativo sem usina no cadastro fica fora (não há de quem ele seja)."""
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
                           "nivel": s["nivel"], "porque": "; ".join(s.get("porQue") or []), "falhas": s.get("nFalha") or 0})
    est = os_falhas.estado()
    return dict(por), {"completa": est.get("completa", False), "lendo": est.get("lendo", False),
                       "sem_cadastro": g.get("sem_cadastro", False), "sinais": len(d.get("sinais") or [])}


# ── Chamados (as OS de acompanhamento de chamado, no banco) ─────────────────────────────────────────────────────
def chamados(hoje: date) -> tuple[dict, dict]:
    """{usina_id: abertos, em verificação e a lista}: o fato `nexus_chamados · fato_chamado` (o mesmo dado do quadro
    Acompanhamento de chamados). O nome do equipamento sai da dimensão de equipamento pelo `equipamento_id` (sem ele, o
    código do ativo). Concluído não conta: é o Finalizados do quadro."""
    linhas = visao._livro(LIVRO_CHAMADOS, ABA_CHAMADOS)
    nome_equip = {}
    if linhas:
        nome_equip = {visao.D._id(r.get("equipamento_id")): str(r.get("descricao") or "").strip()
                      for r in visao._livro(LIVRO_EQUIP, ABA_EQUIP) if visao.D._id(r.get("equipamento_id"))}
    por = collections.defaultdict(lambda: {"abertos": 0, "verificacao": 0, "lista": []})
    sem = 0
    for r in linhas:
        sit = str(r.get("situacao") or "")
        if sit not in ("aberto", "verificacao"):
            continue
        uid = visao.D._id(r.get("usina_id"))
        if not uid:
            sem += sit == "aberto"
            continue
        x = por[uid]
        x["abertos" if sit == "aberto" else "verificacao"] += 1
        ini = _dia_do_id(r.get("data_id_abertura"))
        eid = visao.D._id(r.get("equipamento_id"))
        x["lista"].append({"os": _int(r.get("os")), "situacao": sit, "dias": (hoje - ini).days if ini else None,
                           "equip": (nome_equip.get(eid) or str(r.get("codigo_ativo") or "") or "equipamento")[:48],
                           "fabricante": str(r.get("fabricante") or ""), "componente": str(r.get("componente") or "")})
    for x in por.values():
        x["lista"].sort(key=lambda c: (c["situacao"] != "aberto", -(c["dias"] or 0)))
        x["mais_antigo"] = max((c["dias"] for c in x["lista"] if c["situacao"] == "aberto" and c["dias"] is not None),
                               default=None)
    return dict(por), {"publicado": bool(linhas), "abertos": sum(x["abertos"] for x in por.values()) + sem,
                       "sem_usina": sem}


# ── Extintores (Segurança · HSEQ) ───────────────────────────────────────────────────────────────────────────────
def extintores() -> tuple[dict, dict]:
    """{usina_id: total, vencidos, a vencer, sem conferência e os piores}: a conta do HSEQ (`hseq/extintores.py`, as
    situações exclusivas e a "sem atualização" à parte), sem régua nova."""
    from ..hseq import extintores as E
    lei = E.extintores()
    if lei.erro:
        raise visao.SemBanco(lei.erro)
    d = lei.dados or {}
    por = collections.defaultdict(lambda: {"total": 0, "vencidos": 0, "a_vencer": 0, "sem_conferir": 0,
                                           "sem_validade": 0, "lista": []})
    for x in d.get("extintores") or []:
        uid = x.get("usina_id")
        if not uid:
            continue
        e = por[uid]
        e["total"] += 1
        e["vencidos"] += x["situacao"] == "atrasado"
        e["a_vencer"] += x["situacao"] == "perto"
        e["sem_validade"] += x["situacao"] == "sem_validade"
        e["sem_conferir"] += bool(x.get("sem_atualizacao"))
        if x["situacao"] in ("atrasado", "perto") or x.get("sem_atualizacao"):
            onde = " · ".join(v for v in (x.get("local") or "", x.get("posicao") or "") if v)
            if x["situacao"] == "atrasado":
                txt = f"{x.get('vence_qual') or 'validade'} venceu em {_dm(x.get('vence'))}"
            elif x["situacao"] == "perto":
                txt = f"{x.get('vence_qual') or 'validade'} vence em {x.get('dias_vence')} dias"
            else:
                txt = (f"sem conferência há {x.get('dias_conferencia')} dias" if x.get("dias_conferencia") is not None
                       else "nunca conferido")
            e["lista"].append({"ext": x.get("ext") or x.get("codigo") or "", "onde": onde[:40], "txt": txt,
                               "ordem": {"atrasado": 0, "perto": 1}.get(x["situacao"], 2)})
    for e in por.values():
        e["lista"].sort(key=lambda i: (i["ordem"], i["ext"]))
    return dict(por), {"publicado": bool(d.get("livro_existe")), "extintores": sum(e["total"] for e in por.values())}


# ── Os alertas de cada bloco ────────────────────────────────────────────────────────────────────────────────────
def _pct(x, casas=0) -> str:
    if x is None:
        return "—"
    return (f"{x:.{casas}f}".replace(".", ",")) + "%"


def _virgula(x, casas=1) -> str:
    return "—" if x is None else f"{x:.{casas}f}".replace(".", ",")


def _mwh(kwh) -> str:
    return "—" if kwh is None else f"{kwh / 1000:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _duracao(m) -> str:
    m = int(round(m or 0))
    if m >= 1440:
        return f"{m // 1440} d {(m % 1440) // 60} h"
    return f"{m // 60} h {m % 60:02d} min" if m >= 60 else f"{m} min"


def _dm(d) -> str:
    s = d.isoformat() if hasattr(d, "isoformat") else str(d or "")
    return f"{s[8:10]}/{s[5:7]}" if len(s) >= 10 else "—"


def cls_meta(a) -> str:
    return "neutro" if a is None else ("ok" if a >= META_NA_META else ("alerta" if a >= META_ATENCAO else "critico"))


def cls_disp(x) -> str:
    return "neutro" if x is None else ("ok" if x >= DISP_OK else ("alerta" if x >= DISP_CRITICO else "critico"))


def alertas_performance(u: dict) -> tuple[list[dict], list[str]]:
    """Os alertas de Performance (meta, PR, disponibilidade, ativos) e o que está bem. Fonte sem dado da usina não
    alerta nem elogia: fica "—"."""
    al, bem = [], []
    m = u.get("meta") or {}
    a = m.get("atingimento")
    if a is not None:
        if a < META_ATENCAO:
            al.append({"area": "meta", "nivel": "critico", "titulo": f"Meta do mês em {_pct(a)}",
                       "detalhe": "abaixo de 90% (a Visão gerencial chama de Abaixo)"})
        elif a < META_NA_META:
            al.append({"area": "meta", "nivel": "atencao", "titulo": f"Meta do mês em {_pct(a)}", "detalhe": "entre 90% e 97%"})
        else:
            bem.append(f"na meta ({_pct(a)})")
    if m.get("pr") is not None and m.get("pr_meta") is not None and m["pr"] < m["pr_meta"]:
        al.append({"area": "meta", "nivel": "atencao", "titulo": f"PR {_pct(m['pr'], 1)} abaixo do previsto",
                   "detalhe": f"previsto {_pct(m['pr_meta'], 1)}"})
    d = u.get("disp") or {}
    if d.get("disp") is not None:
        x = d["disp"]
        h = f"{_virgula(d.get('h_perdidas'))} h paradas no mês"
        if x < DISP_CRITICO:
            al.append({"area": "disp", "nivel": "critico", "titulo": f"Disponibilidade {_pct(x, 1)}", "detalhe": h})
        elif x < DISP_OK:
            al.append({"area": "disp", "nivel": "atencao", "titulo": f"Disponibilidade {_pct(x, 1)}", "detalhe": h})
        else:
            bem.append(f"disponibilidade {_pct(x, 1)}")
    at = u.get("ativos") or {}
    for nivel in ("critico", "atencao"):
        lista = [x for x in at.get("lista") or [] if x["nivel"] == nivel]
        if lista:
            al.append({"area": "ativos", "nivel": nivel,
                       "titulo": f"{len(lista)} ativo{'s' if len(lista) != 1 else ''} "
                                 f"{'em crítico' if nivel == 'critico' else 'pedindo atenção'}"})
    if at and not at.get("critico") and not at.get("atencao"):
        bem.append("nenhum ativo em crítico ou atenção")
    return al, bem


def alertas_acompanhamento(u: dict) -> tuple[list[dict], list[str]]:
    """Os alertas de Acompanhamento (ronda, PT, chamados, extintores) e o que está bem."""
    al, bem = [], []
    r = u.get("ronda") or {}
    if r.get("tipo") in ("nunca", "sem_ronda"):
        al.append({"area": "ronda", "nivel": "critico",
                   "titulo": "Nunca teve ronda" if r["tipo"] == "nunca" else f"Sem ronda há {r['dias']} dias"})
    elif r.get("tipo") == "longa_pendente":
        al.append({"area": "ronda", "nivel": "atencao", "titulo": "Ronda longa pendente"})
    elif r.get("dias") is not None and r["dias"] < 999:
        bem.append("ronda " + ("hoje" if r["dias"] == 0 else ("ontem" if r["dias"] == 1 else f"há {r['dias']} dias")))
    p = u.get("pt") or {}
    grupos_pt = (("agora", lambda x: x["hoje"] and x["parada"]), ("critico", lambda x: not x["hoje"] and x["parada"]),
                 ("atencao", lambda x: not x["parada"]))
    for nivel, de_quem in grupos_pt:
        n = sum(1 for x in p.get("lista", []) if de_quem(x))
        if n:
            al.append({"area": "pt", "nivel": nivel,
                       "titulo": {"agora": f"{n} PT parada{'s' if n != 1 else ''} há mais de 2 h",
                                  "critico": f"{n} PT sem decisão desde {_dm(p.get('desde'))}",
                                  "atencao": f"{n} PT esperando o De acordo"}[nivel]})
    c = u.get("chamados") or {}
    if c.get("abertos"):
        al.append({"area": "chamados", "nivel": "atencao",
                   "titulo": f"{c['abertos']} chamado{'s' if c['abertos'] != 1 else ''} em aberto"})
    else:
        bem.append("sem chamado aberto")
    e = u.get("extintores") or {}
    if e.get("vencidos"):
        al.append({"area": "extintores", "nivel": "critico",
                   "titulo": f"{e['vencidos']} extintor{'es' if e['vencidos'] != 1 else ''} vencido{'s' if e['vencidos'] != 1 else ''}"})
    if e.get("a_vencer"):
        al.append({"area": "extintores", "nivel": "atencao",
                   "titulo": f"{e['a_vencer']} extintor{'es' if e['a_vencer'] != 1 else ''} vence{'m' if e['a_vencer'] != 1 else ''} em até 30 dias"})
    if e.get("sem_conferir") and not e.get("vencidos") and not e.get("a_vencer"):
        al.append({"area": "extintores", "nivel": "atencao",
                   "titulo": f"{e['sem_conferir']} extintor{'es' if e['sem_conferir'] != 1 else ''} sem conferência há mais de 30 dias"})
    if e.get("total") and not e.get("vencidos") and not e.get("a_vencer") and not e.get("sem_conferir"):
        bem.append(f"{e['total']} extintor{'es' if e['total'] != 1 else ''} em dia")
    return al, bem


def _nivel(al) -> str:
    if any(a["nivel"] in ("agora", "critico") for a in al):
        return "critico"
    return "atencao" if al else "ok"


# ── O que a linha compacta mostra e o detalhe que ela abre ──────────────────────────────────────────────────────
def _v(txt, cls, sub="") -> dict:
    return {"txt": txt, "cls": cls, "sub": sub}


def linha_performance(u: dict) -> dict:
    """Os valores da linha (meta, PR × previsto, disponibilidade; a etiqueta do ativo) e o detalhe (cada item:
    rótulo, o principal em destaque, o resto e os itens)."""
    m, d, at = u.get("meta") or {}, u.get("disp") or {}, u.get("ativos") or {}
    pr, prm = m.get("pr"), m.get("pr_meta")
    valores = {"meta": _v(_pct(m.get("atingimento")), cls_meta(m.get("atingimento"))),
               "pr": (_v(_virgula(pr), "alerta" if pr < prm else "ok", f"/ {_virgula(prm)}") if pr is not None and prm is not None
                      else _v(_virgula(pr), "neutro") if pr is not None else _v("—", "neutro")),
               "disp": _v(_pct(d.get("disp"), 1), cls_disp(d.get("disp")))}
    tag = None
    if at.get("critico"):
        tag = ("critico", f"{at['critico']} ativo{'s' if at['critico'] != 1 else ''} crítico{'s' if at['critico'] != 1 else ''}")
    elif at.get("atencao"):
        tag = ("alerta", f"{at['atencao']} ativo{'s' if at['atencao'] != 1 else ''} em atenção")
    det = []
    if m.get("meta_kwh"):
        det.append({"rot": "Meta do mês", "forte": f"{_mwh(m.get('prod_kwh'))} de {_mwh(m['meta_kwh'])} MWh",
                    "resto": f"{_pct(m.get('atingimento'))} · meta até {m.get('dias_cob') or '—'} dias cobertos", "itens": []})
    else:
        det.append({"rot": "Meta do mês", "forte": "", "resto": "sem meta publicada para esta usina", "itens": []})
    if pr is not None:
        det.append({"rot": "PR", "forte": _pct(pr, 1), "resto": f"previsto {_pct(prm, 1)}" if prm is not None else "",
                    "alerta": "abaixo do previsto" if prm is not None and pr < prm else "", "itens": []})
    if d.get("disp") is not None:
        det.append({"rot": "Disponibilidade", "forte": _pct(d["disp"], 1),
                    "resto": f"{_virgula(d.get('h_perdidas'))} h paradas no mês", "itens": []})
    falhando = [x for x in at.get("lista") or [] if x["nivel"] in ("critico", "atencao")]
    if falhando:
        det.append({"rot": "Ativos falhando", "forte": "",
                    "resto": f"{len(falhando)} com sinal na Confiabilidade",
                    "itens": [{"forte": x["nome"], "txt": x["porque"]} for x in falhando[:3]],
                    "mais": max(0, len(falhando) - 3)})
    return {"valores": valores, "tag": tag, "det": det}


def linha_acompanhamento(u: dict) -> dict:
    """Os valores da linha (ronda, PT, chamados, extintores) e o detalhe."""
    r, p, c, e = u.get("ronda") or {}, u.get("pt") or {}, u.get("chamados") or {}, u.get("extintores") or {}
    if r.get("tipo") == "nunca":
        ronda, ronda_txt = _v("nunca", "critico"), "Nunca teve ronda pelo App desde a mobilização"
    elif r.get("tipo") == "sem_ronda":
        ronda, ronda_txt = _v(f"há {r['dias']} d", "critico"), f"Sem ronda há {r['dias']} dias (última em {_dm(r.get('ultima'))})"
    elif r.get("tipo") == "longa_pendente":
        ronda, ronda_txt = _v("longa pend.", "alerta"), f"Ronda longa pendente · última ronda em {_dm(r.get('ultima'))}"
    elif r.get("dias") is not None and r["dias"] < 999:
        ronda = _v("hoje" if r["dias"] == 0 else f"há {r['dias']} d", "ok")
        ronda_txt = f"Em dia · última ronda em {_dm(r.get('ultima'))}"
    else:
        ronda, ronda_txt = _v("—", "neutro"), ""
    if p.get("paradas_hoje"):
        pt = _v(f"{p['paradas_hoje']} agora", "critico")
    elif p.get("paradas_antigas"):
        pt = _v(f"{p['paradas_antigas']} s/ decisão", "critico")
    elif p.get("aguardando"):
        pt = _v(f"{p['aguardando']} esperando", "alerta")
    else:
        pt = _v("—", "neutro")
    if c.get("abertos"):
        ch = _v(f"{c['abertos']} aberto{'s' if c['abertos'] != 1 else ''}", "alerta")
    elif c.get("verificacao"):
        ch = _v("em verificação", "neutro")
    else:
        ch = _v("—", "neutro")
    if e.get("vencidos"):
        ext = _v(f"{e['vencidos']} vencido{'s' if e['vencidos'] != 1 else ''}", "critico")
    elif e.get("a_vencer"):
        ext = _v(f"{e['a_vencer']} a vencer", "alerta")
    elif e.get("sem_conferir"):
        ext = _v(f"{e['sem_conferir']} s/ conf.", "alerta")
    elif e.get("total"):
        ext = _v(f"{e['total']} ok", "ok")
    else:
        ext = _v("—", "neutro")
    det = []
    if ronda_txt:
        det.append({"rot": "Ronda", "forte": "", "resto": ronda_txt, "itens": []})
    if p.get("aguardando"):
        det.append({"rot": "PT e APR", "forte": "", "resto": f"{p['aguardando']} esperando o De acordo",
                    "itens": [{"forte": f"OS {x['os'] or x['numero']}", "txt": f"há {_duracao(x['idade_min'])}",
                               "agora": x["hoje"] and x["parada"],
                               "sem_decisao": f"sem decisão desde {_dm(x['dia'])}" if x["parada"] and not x["hoje"] else "",
                               "numero": x["numero"], "codigo": x["codigo"], "titulo": x["tarefa"]} for x in p["lista"][:3]],
                    "mais": max(0, len(p["lista"]) - 3)})
    if c.get("abertos") or c.get("verificacao"):
        det.append({"rot": "Chamados", "forte": "", "resto": f"{c.get('abertos', 0)} em aberto no Acompanhamento de chamados"
                    + (f" · {c['verificacao']} em verificação" if c.get("verificacao") else ""),
                    "itens": [{"forte": x["equip"], "txt": " · ".join(v for v in (
                        x["fabricante"], f"aberto há {x['dias']} d" if x["situacao"] == "aberto" and x["dias"] is not None
                        else ("em verificação" if x["situacao"] == "verificacao" else ""), f"OS {x['os']}") if v)}
                              for x in c["lista"][:3]],
                    "mais": max(0, len(c["lista"]) - 3)})
    if e.get("total"):
        det.append({"rot": "Extintores", "forte": "",
                    "resto": f"{e['total']} cadastrados · {e['vencidos']} vencido{'s' if e['vencidos'] != 1 else ''} · "
                             f"{e['a_vencer']} a vencer · {e['sem_conferir']} sem conferência há mais de 30 dias",
                    "itens": [{"forte": f"Extintor {x['ext']}", "txt": (f"({x['onde']}) " if x["onde"] else "") + x["txt"]}
                              for x in e["lista"][:3]],
                    "mais": max(0, len(e["lista"]) - 3)})
    return {"valores": {"ronda": ronda, "pt": pt, "chamados": ch, "extintores": ext}, "tag": None, "det": det}


def _pt_vazia() -> dict:
    return {"aguardando": 0, "paradas": 0, "paradas_hoje": 0, "paradas_antigas": 0, "desde": "", "lista": []}


def montar(b, usinas_ronda, pendentes, pts, fontes, hoje) -> list[dict]:
    """Uma linha por usina MOBILIZADA, com o que cada fonte diz dela e os dois blocos (alertas, o que está bem, o nível
    e o peso de cada um; os valores da linha compacta e o detalhe). `hoje` = o dia de Brasília (a PT parada de hoje é a
    do técnico parado agora)."""
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
             "chamados": fontes["chamados"].get(uid), "extintores": fontes["extintores"].get(uid), "ronda": r,
             "pt": pt.get(uid) or _pt_vazia()}
        for bloco, alertas, linha in (("perf", alertas_performance, linha_performance),
                                      ("acomp", alertas_acompanhamento, linha_acompanhamento)):
            al, bem = alertas(u)
            al.sort(key=lambda a: -PESO[a["nivel"]])
            u[bloco] = {"alertas": al, "bem": bem, "nivel": _nivel(al), "peso": sum(PESO[a["nivel"]] for a in al),
                        **linha(u)}
        u["nivel"] = min((u["perf"]["nivel"], u["acomp"]["nivel"]), key=NIVEIS.index)
        u["foco"] = u["perf"]["peso"] + u["acomp"]["peso"]
        out.append(u)
    out.sort(key=ordem_do_foco)
    return out


def ordem_do_foco(u: dict):
    """A usina que mais pede o responsável em cima: o peso dos dois blocos; no empate, a mais longe da meta e o nome."""
    ating = (u.get("meta") or {}).get("atingimento")
    return (-u["foco"], ating if ating is not None else 999, u["usina"])


def bloco(usinas: list[dict], qual: str) -> dict:
    """As linhas de um bloco: as que pedem algo (crítico, depois atenção, pelo peso do bloco; na Performance, no empate,
    a mais longe da meta), as que podem esperar (em dia) e a triagem."""
    def chave(u):
        ating = (u.get("meta") or {}).get("atingimento")
        return (-u[qual]["peso"], (ating if ating is not None else 999) if qual == "perf" else 0, u["usina"])
    pedem = sorted((u for u in usinas if u[qual]["nivel"] != "ok"), key=chave)
    em_dia = sorted((u for u in usinas if u[qual]["nivel"] == "ok"), key=lambda u: u["usina"])
    tri = collections.Counter(u[qual]["nivel"] for u in usinas)
    return {"linhas": pedem, "em_dia": em_dia, "tri": {n: tri.get(n, 0) for n in NIVEIS}}


def soma(nome: str, usinas: list[dict]) -> dict:
    """O resumo de um grupo de usinas (um responsável, ou o filtro da tela), por bloco: a triagem (focar, acompanhar,
    pode esperar); na Performance, a meta do grupo (produção ÷ meta das usinas com meta, a conta do Gerencial), as
    usinas abaixo de 97% e com PR abaixo do previsto, e a disponibilidade média pesada pela potência (o resumo por
    cliente de lá); no Acompanhamento, as rondas pendentes, as PT esperando (paradas e paradas de hoje), os chamados em
    aberto e os extintores vencidos. E os ativos em crítico e as 3 usinas que mais pedem."""
    s = {"responsavel": nome, "usinas": len(usinas), "pts": 0, "paradas": 0, "agora": 0, "rondas": 0, "chamados": 0,
         "ext_vencidos": 0, "ativos_criticos": 0, "abaixo_meta": 0, "pr_abaixo": 0}
    prod = meta = disp_p = pot = 0.0
    for u in usinas:
        m = u.get("meta") or {}
        if m.get("prod_kwh") is not None and m.get("meta_kwh"):
            prod += m["prod_kwh"]
            meta += m["meta_kwh"]
        if m.get("atingimento") is not None and m["atingimento"] < META_NA_META:
            s["abaixo_meta"] += 1
        if m.get("pr") is not None and m.get("pr_meta") is not None and m["pr"] < m["pr_meta"]:
            s["pr_abaixo"] += 1
        d = u.get("disp") or {}
        if d.get("disp") is not None:
            p = d.get("pot_kwp") or 1.0
            disp_p += p * d["disp"]
            pot += p
        s["pts"] += u["pt"]["aguardando"]
        s["paradas"] += u["pt"]["paradas"]
        s["agora"] += u["pt"]["paradas_hoje"]
        s["rondas"] += (u.get("ronda") or {}).get("tipo") in ("nunca", "sem_ronda", "longa_pendente")
        s["chamados"] += (u.get("chamados") or {}).get("abertos", 0)
        s["ext_vencidos"] += (u.get("extintores") or {}).get("vencidos", 0)
        s["ativos_criticos"] += (u.get("ativos") or {}).get("critico", 0)
    for qual in ("perf", "acomp"):
        tri = collections.Counter(u[qual]["nivel"] for u in usinas)
        s[qual] = {n: tri.get(n, 0) for n in NIVEIS}
    s["meta_pct"] = round(100 * prod / meta, 1) if meta else None
    s["disp"] = round(disp_p / pot, 1) if pot else None
    s["pior"] = [u["usina"] for u in sorted((u for u in usinas if u["nivel"] == "critico"), key=ordem_do_foco)[:3]]
    s["nivel"] = min(("critico" if s[q]["critico"] else ("atencao" if s[q]["atencao"] else "ok")
                      for q in ("perf", "acomp")), key=NIVEIS.index)
    return s


def por_responsavel(usinas: list[dict]) -> list[dict]:
    """Um cartão por Responsável O&M (`soma` das usinas dele, já filtradas pela tela). "Sem responsável O&M" por último;
    antes, quem tem mais usinas pedindo foco."""
    g = collections.defaultdict(list)
    for u in usinas:
        g[u.get("responsavel") or visao.SEM_RESPONSAVEL].append(u)
    out = [soma(nome, us) for nome, us in g.items()]
    out.sort(key=lambda s: (s["responsavel"] == visao.SEM_RESPONSAVEL, -(s["perf"]["critico"] + s["acomp"]["critico"]),
                            -(s["perf"]["atencao"] + s["acomp"]["atencao"]), s["responsavel"]))
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
        cha, cha_i = _ler_fonte("chamados", lambda: chamados(hoje), erros)
        ext, ext_i = _ler_fonte("extintores", extintores, erros)
        if pts.erro:
            erros["pt"] = pts.erro
        fontes = {"metas": met, "disp": dsp, "ativos": atv, "chamados": cha, "extintores": ext}
        usinas = montar(b, at.dados.get("usinas") or [], at.dados.get("pendentes") or [],
                        (pts.dados or {}).get("aguardando") or [], fontes, hoje)
        responsaveis_por_pessoa = {}
        for uid in b.mobilizadas:
            pid = visao.D._id((b.por_id.get(uid) or {}).get("responsavel_om_id"))
            if pid:
                responsaveis_por_pessoa[pid] = b.responsavel_da_usina(uid)
        return {"usinas": usinas, "mes_id": mes_id, "hoje": hoje.isoformat(), "erros": erros,
                "info": {"metas": met_i, "disp": dsp_i, "ativos": atv_i, "chamados": cha_i, "extintores": ext_i},
                "responsaveis_por_pessoa": responsaveis_por_pessoa, "sem_mobilizacao": b.sem_mobilizacao,
                "fatos": at.dados.get("fatos") or {}, **visao._estrutura(b)}
    return visao._ler(("visao_responsaveis",), calcular)
