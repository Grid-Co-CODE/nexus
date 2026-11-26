"""Os relatórios do PCM no Nexus sem as OS do backoffice (reunião do PCM, 24/11/2026: "as pessoas do backoffice não
devem aparecer no relatório"). A marca é a do robô do PCM ("bo" na tarefa da Gestão PCM, pelo responsável da OS); a OS
sai das linhas, das pendentes e das tarefas, como no relatório executivo (`rexBoOS`)."""
import copy

from nexus.pcm.relatorios import dados as D

BD = {"geradoEm": "x", "semanas": [{"week": "2026-W47",
                                     "rows": [{"os_id": 100, "tarefa": "a"}, {"os_id": "200", "tarefa": "b"},
                                              {"os_id": "300.0", "tarefa": "c"}],
                                     "pendentes": [{"os_id": "200"}, {"os_id": "400"}]}]}
GESTAO = {"tarefas": [{"os": 200, "bo": True}, {"os": "300", "bo": True}, {"os": 100}, {"os": 400}]}


def test_tira_a_os_do_backoffice_de_tudo_sem_mexer_na_copia_lida():
    bd, gestao = copy.deepcopy(BD), copy.deepcopy(GESTAO)
    m = D.montar(bd, gestao)
    w = m["bd"]["semanas"][0]
    assert [r["os_id"] for r in w["rows"]] == [100]
    assert [p["os_id"] for p in w["pendentes"]] == ["400"]
    assert [t["os"] for t in m["gestao"]["tarefas"]] == [100, 400]
    assert m["bd"]["geradoEm"] == "x" and w["week"] == "2026-W47"
    # o que o `fonte` leu é a cópia de 5 min de todos: não se mexe nela
    assert bd == BD and gestao == GESTAO


def test_sem_a_marca_nada_muda():
    gestao = {"tarefas": [{"os": 100}]}
    m = D.montar(BD, gestao)
    assert m["bd"] is BD and m["gestao"] is gestao
