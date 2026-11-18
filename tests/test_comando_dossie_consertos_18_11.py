"""Os consertos do dossiê e do parecer do prontuário (Levi, 18/11/2026, depois de mandar conferir o dossiê da Mandaguaçu:
"pode fazer todos os consertos necessários!"). O que a conferência achou, com o dossiê real da usina:

1. O parecer contava o mesmo ponto duas vezes: "1 extintor vencido" e "Sem ronda há 42 dias" vinham da Visão do
   responsável E do Insight (R07, R11) com o mesmo título, e a frase dizia "11 pontos críticos" onde eram 9.
2. "Luvas de alta tensão: nunca verificadas na ronda; última verificação em 07/10/2026": a situação "sem_verificacao"
   da Segurança vale para quem nunca verificou e para quem verificou há mais de 30 dias; o dossiê escrevia "nunca".
3. "Mandaguaçu: sem comunicação há 283 dias" (R05) era a falha de comunicação de UM inversor (o INV2.8), aberta no COS
   desde 07/02; o texto dizia a usina inteira, e a IA repetia.
4. A tabela dos equipamentos tinha 30 linhas só com as duas OS de preventiva (cabines, QGBT, transformadores...), que
   o §5 já lista em cada OS: viram uma linha, com os nomes agrupados pela OS."""
import re

from test_comando_dossie import AGORA, NOMES, _ctx  # noqa: F401
from test_campo_responsaveis import tela  # noqa: F401  (fixture)
from test_campo_visao import banco  # noqa: F401  (fixture)

from nexus.comando import dossie as DS
from nexus.comando import prontuario as PR
from nexus.comando import regras as R


# ── 1. o parecer sem contar em dobro ─────────────────────────────────────────────────────────────────────────────────
def test_o_insight_com_o_mesmo_titulo_da_visao_nao_conta_duas_vezes():
    u = {"acomp": {"alertas": [{"nivel": "critico", "titulo": "sem ronda há 42 dias", "detalhe": "", "area": "ronda"},
                               {"nivel": "critico", "titulo": "1 extintor vencido", "detalhe": "", "area": "extintores"},
                               {"nivel": "alerta", "titulo": "12 chamados em aberto", "detalhe": "", "area": "chamados"}]}}
    insights = [{"sev": "critico", "titulo": "Usina X: sem ronda há 42 dias", "acao": "Programar a ronda com o PCM."},
                {"sev": "atencao", "titulo": "1 extintor vencido.", "acao": "Programar a recarga."},
                {"sev": "critico", "titulo": "Chamado da OS 17316 aguardando o fabricante há 190 dias", "acao": "Cobrar."}]
    itens = PR.atencao(u, [], insights, usina="Usina X")
    assert [i["titulo"] for i in itens] == ["Sem ronda há 42 dias", "1 extintor vencido",
                                           "Chamado da OS 17316 aguardando o fabricante há 190 dias", "12 chamados em aberto"]
    # o ponto fica uma vez, na seção da tela dona, com a ação do Insight no detalhe (a Visão não trazia detalhe)
    ronda, ext = itens[0], itens[1]
    assert ronda["secao"] == "rondas" and ronda["detalhe"] == "Programar a ronda com o PCM."
    assert ext["tom"] == "critico" and ext["detalhe"] == "Programar a recarga."       # o tom é o pior dos dois
    assert PR.parecer(itens)["frase"].startswith("3 pontos críticos e 1 de atenção.")
    # o detalhe que a Visão já trazia fica; o Insight de título diferente segue como ponto próprio
    u["acomp"]["alertas"][0]["detalhe"] = "última em 07/10"
    assert PR.atencao(u, [], insights, usina="Usina X")[0]["detalhe"] == "última em 07/10"


# ── 2. as luvas ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _luvas(logado, lv):
    ctx = _ctx(logado)
    ctx["p"]["luvas"] = lv
    return next(l for l in DS.montar(ctx, AGORA)["texto"].splitlines() if l.startswith("- Luvas de alta tensão"))


def test_as_luvas_verificadas_ha_muito_tempo_nao_sao_nunca(tela, logado):
    velha = {"situacao": "sem_verificacao", "dias": 42, "ultima": {"dia": "2026-10-07", "os": "15672", "tecnico": NOMES[3]}}
    assert _luvas(logado, velha) == "- Luvas de alta tensão: sem verificação há 42 dias; última verificação em 07/10/2026, OS 15672"
    nunca = {"situacao": "sem_verificacao", "dias": None, "ultima": None}
    assert _luvas(logado, nunca) == "- Luvas de alta tensão: nunca verificadas na ronda"


# ── 3. a R05 diz o equipamento ───────────────────────────────────────────────────────────────────────────────────────
def test_r05_com_equipamento_citado_e_do_equipamento_e_nao_da_usina():
    nomes = {1: "Usina Exemplo Um"}.get
    abertas = [{"registro": "rg1", "os": "17109", "usina_id": 1, "tipo_falha": "FALHA_COMUNICACAO", "dias_aberta_qtd": 283,
                "data_id_inicio": 20260207, "equipamentos_citados": "INV2.8", "equipamentos_qtd": 1},
               {"registro": "rg2", "os": "17200", "usina_id": 1, "tipo_falha": "FALHA_COMUNICACAO", "dias_aberta_qtd": 4,
                "data_id_inicio": 20261114, "equipamentos_citados": "", "equipamentos_qtd": 0}]
    out = {i["id"]: i for i in R.r05_sem_comunicacao(abertas, nomes)}
    eq, usina = out["R05:rg1"], out["R05:rg2"]
    assert eq["titulo"] == "Usina Exemplo Um: INV2.8 sem comunicação há 283 dias"
    assert "aberta no COS em 07/02/2026" in eq["evid"] and "OS 17109" in eq["evid"]
    assert "equipamento" in eq["acao"] and "a usina some do tempo real" not in eq["acao"]
    # sem equipamento citado, é a usina, como antes
    assert usina["titulo"] == "Usina Exemplo Um: sem comunicação há 4 dias" and "a usina some do tempo real" in usina["acao"]
    assert "aberta no COS em 14/11/2026" in usina["evid"]


# ── 4. a tabela dos equipamentos sem as 30 linhas de preventiva ──────────────────────────────────────────────────────
def _equip(nome, cod, os_, tipos, abertas=1, pausadas=0, chamado=None):
    return {"nome": nome, "codigo": cod, "abertas": abertas, "pausadas": pausadas, "os": os_, "tipos": tipos, "chamado": chamado}


def test_os_equipamentos_so_de_preventiva_viram_uma_linha(tela, logado):
    ctx = _ctx(logado)
    so_prev = [_equip(f"Cabine {n}", f"X-CABN{n}", ["8466", "19302"], ["preventiva"], 2) for n in (1, 2, 3)] + \
              [_equip("Fossa Séptica", "X-FSEP", ["8466"], ["preventiva"]), _equip("Nobreak 4", "X-NBRK4", ["19302"], ["preventiva"])]
    com_sinal = [_equip("Inversor 1.7", "X-INVR1.7", ["17550"], ["corretiva"]),
                 _equip("Tracker 07", "X-TKR7", ["17647"], ["administrativa"], chamado={"os": "17647", "fabricante": "STI", "situacao": "aberto"}),
                 _equip("Cabine 9", "X-CABN9", ["8466"], ["preventiva"], pausadas=1)]            # pausada: fica na tabela
    ctx["p"]["equip_todos"] = {"itens": com_sinal + so_prev}
    sec = DS.montar(ctx, AGORA)["texto"].split("## 7. Equipamentos com OS ou chamado aberto", 1)[1].split("\n## 8.", 1)[0]
    linhas = [l for l in sec.splitlines() if l.startswith("| ") and not l.startswith("| ---") and not l.startswith("| Equipamento")]
    assert [l.split(" | ")[0].strip("| ") for l in linhas] == ["Inversor 1.7", "Tracker 07", "Cabine 9"]
    resto = next(l for l in sec.splitlines() if l.startswith("- Só com tarefa de preventiva"))
    assert resto == ("- Só com tarefa de preventiva aberta, sem corretiva, pausa nem chamado (5 equipamentos): "
                     "OS 8466 e 19302: Cabine 1, Cabine 2, Cabine 3; OS 8466: Fossa Séptica; OS 19302: Nobreak 4")
    # com poucos (menos de 5), a tabela fica inteira
    ctx["p"]["equip_todos"] = {"itens": com_sinal + so_prev[:4]}
    sec = DS.montar(ctx, AGORA)["texto"].split("## 7. Equipamentos com OS ou chamado aberto", 1)[1].split("\n## 8.", 1)[0]
    assert "Só com tarefa de preventiva" not in sec and "| Fossa Séptica | X-FSEP |" in sec
