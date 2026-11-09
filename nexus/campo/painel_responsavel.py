"""O Painel do responsável (Levi, 28/10/2026): "com base no que já temos no acompanhamento do responsável quero uma tela
feita mesmo para o responsável que não seja um tabelão. Então eu escolheria o responsável, vai ter o nome do responsável
como [título] e mostrará: Usinas abaixo da performance, chamados abertos, PTs pendentes, Ranking das equipes do maior
para menor, acompanhamento de rondas! (...) uma tela inicial claro, se for para se aprofundar aí é outro nível".

Nenhum número novo e nenhuma régua nova: cada quadro reorganiza o que a Visão do responsável já calcula por usina
(`responsaveis.montar`, a conta guardada de 5 min). **Nada fica de
fora** (Levi, no mesmo dia, ao ver a 1ª versão com 5 linhas e "e mais N": "poderia ter um scroll para o que não cabe no
card (...) Tem que ter todas as usinas e equipes daquele supervisor, não podemos deixar nada de fora"): cada quadro traz
a lista inteira, a que mais pede em cima, e a tela rola dentro do quadro. A Performance e as Rondas trazem TODAS as usinas
do responsável (as em dia no fim); os chamados, todas as em aberto; as PT, todas as pendentes; o Ranking, todas as equipes.
O detalhe é o outro nível: a Visão geral com o filtro do quadro e as janelas que a Visão já abre por cima.
A 2ª rodada (28/10/2026, Levi ao ver no ar): os chamados por usina, com o ativo sem a marca e o status do chamado, e o
clique abre a tela do chamado de Garantias por cima; o número das Rondas é o das usinas sem ronda há 7 dias ou mais; o
texto das PT enxuto; o Ranking do mês vigente; e o 6º quadro, as usinas com extintor vencido.
Em 09/11/2026 (Levi, pelo Scrum master) o Ranking das equipes saiu ("Pode remover o ranking das equipes de 'Visão do
Responsável'") e as Pendências de OS entraram no lugar dele ("Em Visão do responsável > Painel deve ter um acompanhamento
de pendências de OSs com OSs e motivos!").
"""
import collections

from . import responsaveis as R
from . import visao


def _situacao_da_meta(u: dict) -> str:
    a = (u.get("meta") or {}).get("atingimento")
    if a is None:
        return "sem_meta"
    return "critico" if a < R.META_ATENCAO else ("alerta" if a < R.META_NA_META else "ok")


def _cls_nivel(campo: str, nivel) -> str:
    """A cor de um nível de sujidade ou de vegetação na régua das Rondas (`visao.criticidade`: o 5 crítico, o 4 atenção;
    abaixo, sem alerta); sem leitura, neutro."""
    if nivel is None:
        return "neutro"
    itens = visao.criticidade({campo: nivel})[1]
    return itens[0][1] if itens else "ok"


def performance(usinas: list[dict]) -> dict:
    """Todas as usinas pela meta do mês, da pior para a melhor (`ordem_da_meta`; sem meta publicada no fim), na régua da
    Visão gerencial: abaixo de 90% crítico, abaixo de 97% atenção; com o PR contra o previsto, a disponibilidade e a
    última sujidade e vegetação."""
    linhas = []
    for u in sorted(usinas, key=R.ordem_da_meta):
        m, d = u.get("meta") or {}, u.get("disp") or {}
        # o PR e a disponibilidade como a Visão já os escreve e colore na linha da usina (`linha_performance`: o PR
        # contra o previsto, a disponibilidade na régua da tela dona); o card largo do Painel mostra os dois em coluna
        val = (u.get("perf") or {}).get("valores") or {}
        pr_v, disp_v = val.get("pr") or {}, val.get("disp") or {}
        # a última sujidade e vegetação da usina (Levi, 29/10/2026: "em performance mostre última sujidade e vegetação
        # de todas as usinas. Pode aparecer depois de disponibilidade"): a leitura que a Visão já tem (`responsaveis.
        # limpeza`, a conta das Rondas, a última em 90 dias), na régua das Rondas
        lim = u.get("limpeza") or {}
        suj, veg = lim.get("sujidade"), lim.get("vegetacao")
        linhas.append({"usina_id": u["usina_id"], "usina": u["usina"], "cliente": u.get("cliente") or "",
                       "atingimento": m.get("atingimento"), "situacao": _situacao_da_meta(u),
                       "anomalia": m.get("anomalia") or "", "pr": m.get("pr"), "pr_meta": m.get("pr_meta"),
                       "pr_abaixo": m.get("pr") is not None and m.get("pr_meta") is not None and m["pr"] < m["pr_meta"],
                       "disp": d.get("disp"), "pr_cls": pr_v.get("cls") or "neutro",
                       "disp_cls": disp_v.get("cls") or "neutro",
                       "sujidade": suj, "sujidade_cls": _cls_nivel("sujidade", suj),
                       "vegetacao": veg, "vegetacao_cls": _cls_nivel("vegetacao", veg),
                       "limpeza_data": lim.get("data") or ""})
    cont = collections.Counter(x["situacao"] for x in linhas)
    return {"usinas": len(usinas), "com_meta": len(usinas) - cont["sem_meta"], "abaixo": cont["critico"] + cont["alerta"],
            "criticas": cont["critico"], "na_meta": cont["ok"], "sem_meta": cont["sem_meta"],
            "meta_grupo": R.soma("", usinas)["meta_pct"], "linhas": linhas}


def _mais_velho(itens) -> int | None:
    return max((x["dias"] for x in itens if x.get("dias") is not None), default=None)


def chamados(usinas: list[dict]) -> dict:
    """Todos os chamados de garantia em aberto (`fato_chamado`, o quadro Acompanhamento de chamados), POR USINA (Levi,
    28/10/2026: "Ao invés de ficar repetindo o nome da UFV pode só botar o nome da UFV uma vez e dizer qual os ativos
    daquela UFV"): a usina do chamado mais antigo primeiro e, dentro dela, o ativo (sem a marca: "Não precisa mostrar a
    marca do ativo") com o status do chamado ("Seria bom mostrar o status do chamado"), o mais antigo primeiro. Concluído
    não entra ("As concluídas não mostra"; é o Finalizados do quadro); os em verificação só na contagem."""
    grupos, verif = [], 0
    for u in usinas:
        c = u.get("chamados") or {}
        verif += c.get("verificacao") or 0
        itens = [{"os": x.get("os"), "ativo": x.get("ativo") or x.get("equip") or "equipamento",
                  "status": x.get("status") or "", "dias": x.get("dias")}
                 for x in c.get("lista") or () if x.get("situacao") == "aberto"]
        if not itens:
            continue
        itens.sort(key=lambda x: (x["dias"] is None, -(x["dias"] or 0), x["os"] or 0))
        grupos.append({"usina_id": u["usina_id"], "usina": u["usina"], "cliente": u.get("cliente") or "",
                       "mais_antigo": _mais_velho(itens), "itens": itens})
    grupos.sort(key=lambda g: (g["mais_antigo"] is None, -(g["mais_antigo"] or 0), g["usina"]))
    return {"abertos": sum(len(g["itens"]) for g in grupos), "verificacao": verif, "usinas": len(grupos),
            "mais_antigo": _mais_velho([{"dias": g["mais_antigo"]} for g in grupos]), "grupos": grupos}


def pts(usinas: list[dict]) -> dict:
    """Todas as PT esperando o De acordo (`visao.pts`): a parada de hoje primeiro (técnico parado agora), depois as
    paradas de outros dias, depois as que esperam há menos de 2 h; em cada grupo, a que espera há mais tempo."""
    itens = [{**p, "usina_id": u["usina_id"], "usina": u["usina"]} for u in usinas
             for p in (u.get("pt") or {}).get("lista") or ()]
    itens.sort(key=lambda p: (0 if p.get("parada") and p.get("hoje") else (1 if p.get("parada") else 2),
                              -(p.get("idade_min") or 0)))
    return {"aguardando": len(itens), "paradas": sum(1 for p in itens if p.get("parada")),
            "agora": sum(1 for p in itens if p.get("parada") and p.get("hoje")), "linhas": itens}


def pendencias_os(usinas: list[dict], hoje=None) -> dict:
    """As OS pendentes das usinas da tela, cada uma com o número e o motivo (Levi, 09/11/2026: "um acompanhamento de
    pendências de OSs com OSs e motivos!"). Nenhuma régua nova: são as listas INTEIRAS do bloco Manutenção da Visão
    (`manutencao.por_usina`: `todas_atrasadas` e `todas_paradas`; a linha da Visão geral mostra só as 5 primeiras, e o
    Painel não deixa nada de fora). A atrasada é a tarefa programada há mais de 10 dias e não feita (a régua do PCM); a
    pausada é a tarefa tirada da programação por um motivo do PCM ou justificada pelo técnico no App, com o motivo, desde
    quando e quem. Por usina, a da pendência mais antiga primeiro; dentro dela, a atrasada mais antiga e depois a pausada
    mais antiga. O número do quadro é o das OS (uma OS com duas tarefas pendentes conta uma vez), e as duas contas de
    baixo também são de OS: com tarefa atrasada e com tarefa pausada (a OS com as duas entra nas duas; na bancada de
    09/11/2026, "158 atrasadas e 96 pausadas" de 187 OS misturava OS e tarefas)."""
    hoje = hoje or visao._agora().date()
    grupos, todas, com_atr, com_par = [], set(), set(), set()
    for u in usinas:
        m = u.get("manutencao") or {}
        itens = []
        for x in m.get("todas_atrasadas") or ():
            tipo = str(x.get("tipo") or "").replace("_", " ")
            itens.append({"os": x["os"], "wid": x.get("wid"), "situacao": "Atrasada", "dias": x.get("dias"),
                          "motivo": f"programada há {x.get('dias')} dias e não feita" + (f" · {tipo}" if tipo else "")})
        for x in m.get("todas_paradas") or ():
            desde = x.get("desde")
            motivo = str(x.get("motivo") or "").strip() or "pausada sem motivo escrito"
            itens.append({"os": x["os"], "wid": x.get("wid"), "situacao": "Pausada",
                          "dias": (hoje - desde).days if desde else None,
                          "motivo": motivo + (f" · por {x['quem']}" if x.get("quem") else "")})
        if not itens:
            continue
        com_atr |= {(u["usina_id"], i["os"]) for i in itens if i["situacao"] == "Atrasada"}
        com_par |= {(u["usina_id"], i["os"]) for i in itens if i["situacao"] == "Pausada"}
        todas |= {(u["usina_id"], i["os"]) for i in itens}
        itens.sort(key=lambda i: (i["situacao"] != "Atrasada", -(i["dias"] if i["dias"] is not None else -1)))
        grupos.append({"usina_id": u["usina_id"], "usina": u["usina"], "itens": itens,
                       "pior": max((i["dias"] for i in itens if i["dias"] is not None), default=-1)})
    grupos.sort(key=lambda g: (-g["pior"], g["usina"]))
    return {"os": len(todas), "atrasadas": len(com_atr), "pausadas": len(com_par), "grupos": grupos}


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
    # o número do quadro (Levi, 28/10/2026: "o número do KPI deve falar quantas usinas estão sem ronda a 7 dias ou mais"):
    # soma as que nunca tiveram ronda pelo App desde a mobilização (decisão dele no mesmo dia, "Somar as que nunca
    # tiveram"); a linha de baixo diz quantas são
    return {"usinas": total, "em_dia": cont["em_dia"], "sem_ronda": cont["sem_ronda"], "nunca": cont["nunca"],
            "sem_7": cont["sem_ronda"] + cont["nunca"], "longa": cont["longa_pendente"], "sem_dado": cont["sem_dado"],
            "em_dia_pct": round(100 * cont["em_dia"] / total) if total else None, "linhas": linhas}


def extintores(usinas: list[dict]) -> dict:
    """As usinas com extintor vencido (Levi, 28/10/2026: "quero que mostre também as usinas com extintores vencidos
    daquele supervisor"): a conta do HSEQ que a Visão já lê (`responsaveis.extintores`: vencido = a validade passou), a
    usina com mais vencidos primeiro; o "a vencer" e o pior extintor vão na linha, de contexto."""
    linhas = []
    for u in usinas:
        e = u.get("extintores") or {}
        if not e.get("vencidos"):
            continue
        pior = next((x for x in e.get("lista") or () if x.get("ordem") == 0), None)
        linhas.append({"usina_id": u["usina_id"], "usina": u["usina"], "vencidos": e["vencidos"],
                       "a_vencer": e.get("a_vencer") or 0, "total": e.get("total") or 0,
                       "pior": (pior or {}).get("txt") or "", "pior_ext": (pior or {}).get("ext") or ""})
    linhas.sort(key=lambda x: (-x["vencidos"], x["usina"]))
    com = [u for u in usinas if (u.get("extintores") or {}).get("total")]
    return {"usinas": len(linhas), "com_extintor": len(com), "vencidos": sum(x["vencidos"] for x in linhas),
            "a_vencer": sum((u.get("extintores") or {}).get("a_vencer") or 0 for u in com), "linhas": linhas}


def montar(nome: str, usinas: list[dict], hoje=None) -> dict:
    """O painel de um responsável (ou de todos, sem escolha): o cabeçalho, o número das PT (à esquerda da faixa "Parada
    agora", desde 29/10/2026) e os cinco quadros (as Pendências de OS no lugar do Ranking desde 09/11/2026)."""
    clientes = sorted({u.get("cliente") for u in usinas if u.get("cliente")})
    equipes = sorted({u.get("equipe") for u in usinas if u.get("equipe") and u.get("equipe") != visao.SEM_EQUIPE})
    return {"nome": nome, "usinas": len(usinas), "clientes": clientes, "equipes": equipes,
            "perf": performance(usinas), "chamados": chamados(usinas), "pts": pts(usinas),
            "pendencias": pendencias_os(usinas, hoje), "rondas": rondas(usinas), "extintores": extintores(usinas)}
