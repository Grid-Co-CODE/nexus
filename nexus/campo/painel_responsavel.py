"""O Painel do responsável (Levi, 28/10/2026): "com base no que já temos no acompanhamento do responsável quero uma tela
feita mesmo para o responsável que não seja um tabelão. Então eu escolheria o responsável, vai ter o nome do responsável
como [título] e mostrará: Usinas abaixo da performance, chamados abertos, PTs pendentes, Ranking das equipes do maior
para menor, acompanhamento de rondas! (...) uma tela inicial claro, se for para se aprofundar aí é outro nível".

Nenhum número novo e nenhuma régua nova: cada quadro reorganiza o que a Visão do responsável já calcula por usina
(`responsaveis.montar`, a conta guardada de 5 min) e o Ranking das equipes (`ranking_equipes.cartoes`). **Nada fica de
fora** (Levi, no mesmo dia, ao ver a 1ª versão com 5 linhas e "e mais N": "poderia ter um scroll para o que não cabe no
card (...) Tem que ter todas as usinas e equipes daquele supervisor, não podemos deixar nada de fora"): cada quadro traz
a lista inteira, a que mais pede em cima, e a tela rola dentro do quadro. A Performance e as Rondas trazem TODAS as usinas
do responsável (as em dia no fim); os chamados, todas as em aberto; as PT, todas as pendentes; o Ranking, todas as equipes.
O detalhe é o outro nível: a Visão geral com o filtro do quadro e as janelas que a Visão já abre por cima.
"""
import collections

from . import responsaveis as R
from . import visao


def _situacao_da_meta(u: dict) -> str:
    a = (u.get("meta") or {}).get("atingimento")
    if a is None:
        return "sem_meta"
    return "critico" if a < R.META_ATENCAO else ("alerta" if a < R.META_NA_META else "ok")


def performance(usinas: list[dict]) -> dict:
    """Todas as usinas pela meta do mês, da pior para a melhor (`ordem_da_meta`; sem meta publicada no fim), na régua da
    Visão gerencial: abaixo de 90% crítico, abaixo de 97% atenção; com o PR contra o previsto e a disponibilidade."""
    linhas = []
    for u in sorted(usinas, key=R.ordem_da_meta):
        m, d = u.get("meta") or {}, u.get("disp") or {}
        linhas.append({"usina_id": u["usina_id"], "usina": u["usina"], "cliente": u.get("cliente") or "",
                       "atingimento": m.get("atingimento"), "situacao": _situacao_da_meta(u),
                       "anomalia": m.get("anomalia") or "", "pr": m.get("pr"), "pr_meta": m.get("pr_meta"),
                       "pr_abaixo": m.get("pr") is not None and m.get("pr_meta") is not None and m["pr"] < m["pr_meta"],
                       "disp": d.get("disp")})
    cont = collections.Counter(x["situacao"] for x in linhas)
    return {"usinas": len(usinas), "com_meta": len(usinas) - cont["sem_meta"], "abaixo": cont["critico"] + cont["alerta"],
            "criticas": cont["critico"], "na_meta": cont["ok"], "sem_meta": cont["sem_meta"],
            "meta_grupo": R.soma("", usinas)["meta_pct"], "linhas": linhas}


def chamados(usinas: list[dict]) -> dict:
    """Todos os chamados de garantia em aberto (`fato_chamado`, o quadro Acompanhamento de chamados), o mais antigo
    primeiro; os em verificação só na contagem."""
    abertos, verif = [], 0
    for u in usinas:
        c = u.get("chamados") or {}
        verif += c.get("verificacao") or 0
        for x in c.get("lista") or ():
            if x.get("situacao") == "aberto":
                abertos.append({**x, "usina_id": u["usina_id"], "usina": u["usina"]})
    abertos.sort(key=lambda x: (-(x.get("dias") if x.get("dias") is not None else -1), x["usina"]))
    return {"abertos": len(abertos), "verificacao": verif, "usinas": len({x["usina_id"] for x in abertos}),
            "mais_antigo": abertos[0].get("dias") if abertos else None, "linhas": abertos}


def pts(usinas: list[dict]) -> dict:
    """Todas as PT esperando o De acordo (`visao.pts`): a parada de hoje primeiro (técnico parado agora), depois as
    paradas de outros dias, depois as que esperam há menos de 2 h; em cada grupo, a que espera há mais tempo."""
    itens = [{**p, "usina_id": u["usina_id"], "usina": u["usina"]} for u in usinas
             for p in (u.get("pt") or {}).get("lista") or ()]
    itens.sort(key=lambda p: (0 if p.get("parada") and p.get("hoje") else (1 if p.get("parada") else 2),
                              -(p.get("idade_min") or 0)))
    return {"aguardando": len(itens), "paradas": sum(1 for p in itens if p.get("parada")),
            "agora": sum(1 for p in itens if p.get("parada") and p.get("hoje")), "linhas": itens}


def ranking(rk: dict | None) -> dict:
    """Todas as equipes das usinas da tela, da maior nota do App para a menor (Levi: "do maior para menor"); a posição é
    a do ranking de TODAS as equipes (`ranking_equipes.classificar`). Sem nota no fim. As usinas sem equipe no cadastro
    vêm por último, como no Ranking (o conserto é no cadastro), para nenhuma usina ficar de fora."""
    cartoes = list((rk or {}).get("cartoes") or ())
    eq = sorted((c for c in cartoes if not c.get("sem_equipe")),
                key=lambda c: (c.get("nota") is None, -(c.get("nota") or 0), c["equipe"]))
    return {"equipes": eq + [c for c in cartoes if c.get("sem_equipe")], "total": (rk or {}).get("total") or 0}


def _situacao_da_ronda(u: dict) -> str:
    r = u.get("ronda") or {}
    if r.get("tipo") in R.RONDA_ORDEM:
        return r["tipo"]
    dias = r.get("dias")
    return "em_dia" if isinstance(dias, (int, float)) and dias < 999 else "sem_dado"


def rondas(usinas: list[dict]) -> dict:
    """Todas as usinas pela ronda, na régua da Central de atenção (nunca teve, sem ronda há 7 dias ou mais, longa
    pendente, em dia, sem dado), a que mais pede em cima (`ordem_da_ronda`: em dia, a mais antiga primeiro)."""
    cont = collections.Counter(_situacao_da_ronda(u) for u in usinas)
    linhas = []
    for u in sorted(usinas, key=R.ordem_da_ronda):
        r = u.get("ronda") or {}
        linhas.append({"usina_id": u["usina_id"], "usina": u["usina"], "situacao": _situacao_da_ronda(u),
                       "dias": r.get("dias") if isinstance(r.get("dias"), (int, float)) and r.get("dias") < 999 else None,
                       "ultima": r.get("ultima") or "", "os": r.get("os") or "", "tecnico": r.get("tecnico") or ""})
    total = len(usinas)
    return {"usinas": total, "em_dia": cont["em_dia"], "sem_ronda": cont["sem_ronda"], "nunca": cont["nunca"],
            "longa": cont["longa_pendente"], "sem_dado": cont["sem_dado"],
            "em_dia_pct": round(100 * cont["em_dia"] / total) if total else None, "linhas": linhas}


def montar(nome: str, usinas: list[dict], rk: dict | None) -> dict:
    """O painel de um responsável (ou de todos, sem escolha): o cabeçalho e os cinco quadros."""
    clientes = sorted({u.get("cliente") for u in usinas if u.get("cliente")})
    equipes = sorted({u.get("equipe") for u in usinas if u.get("equipe") and u.get("equipe") != visao.SEM_EQUIPE})
    return {"nome": nome, "usinas": len(usinas), "clientes": clientes, "equipes": equipes,
            "perf": performance(usinas), "chamados": chamados(usinas), "pts": pts(usinas), "ranking": ranking(rk),
            "rondas": rondas(usinas)}
