"""A última semana do mês no motor do PCM (23/10/2026, Levi: "o programador da w44 jogou a maioria das tarefas para
segunda-feira sem distribuir corretamente, corrija").

A W44 (26 a 30/10) tem o dia 30: é a última semana do mês, e nela a MPM "recebe prioridade de corretiva". O motor fazia
isso FORÇANDO cada MPM no dia da usina, logo no passe 1: a usina ganha os dias pela soma das horas, e uma OS de MPM com
29 subtarefas de 10 min soma 5 h (1 dia), mas ocupa 12 h na agenda (cada tarefa leva os 15 min de troca). Tudo ia para
a segunda com [EXCEDE HH] até as 23 h, e o resto da semana ficava vazio: na W44 publicada, 193 MPM com [EXCEDE HH] e
393 tarefas na segunda contra 79 na sexta (na W43, nenhuma MPM com [EXCEDE HH]).

O que estes testes seguram: na última semana, a MPM tenta caber como as outras e a sobra vai para os dias livres (o
passe de preenchimento); só a que não cabe em dia nenhum entra forçada, no dia da usina com mais folga, e nunca vira
pendência (a regra continua). A corretiva segue forçada no dia da usina, como sempre.

O motor roda tudo no import (lê o Fracttal), então o escalonador é tirado do arquivo pelo `ast`: as funções e as
constantes de horário, com a semana e as regras do teste no lugar das que ele carrega."""
import ast
import math
import os
import re
import unicodedata
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

MOTOR = Path(__file__).resolve().parents[1] / "nexus" / "pcm" / "motor" / "programacao_v7.py"
FUNCOES = {"DayCapacity", "alloc_diurno", "commit_diurno", "alloc_noturno", "agendar_mpa_janela", "commit_noturno",
           "distribute_days", "assign_days_to_usinas", "schedule_team", "_row", "_pend", "t", "norm",
           "haversine_km", "_usina_match", "_norm_usina", "_usina_pode_no_dia", "_os_eh_multi", "_casa_tarefa",
           "_tarefa_excluida"}
CONSTANTES = re.compile(r"^(WORK_|FIRST_OS|LUNCH_|PCM_END|NIGHT_|TERMO_|GAP_|TRAVEL_|DESLOC_|CARGA_MAX|USEFUL_|MPA_|TIER_"
                        r"|PREVENTIVA_ORDER)")


def _escalonador(semana_inicio: date):
    """O `schedule_team` do motor com a semana dada, sem feriado, sem pin e sem deslocamento."""
    arvore = ast.parse(MOTOR.read_text(encoding="utf-8"))
    nos = []
    for no in arvore.body:
        if isinstance(no, (ast.FunctionDef, ast.ClassDef)) and no.name in FUNCOES:
            nos.append(no)
        elif isinstance(no, ast.Assign) and all(isinstance(a, ast.Name) and CONSTANTES.match(a.id) for a in no.targets):
            nos.append(no)
    dias = [semana_inicio + timedelta(days=i) for i in range(5)]
    ns = {"math": math, "re": re, "os": os, "unicodedata": unicodedata, "pd": pd, "DAYS": dias,
          "DAY_NAMES": ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira"],
          "ULTIMA_SEMANA_MES": any(d.day >= 30 for d in dias), "OS_PINS": {}, "USINA_DIAS": {}, "historico": {},
          "AGING_DIAS": 10, "_is_feriado_para_equipe": lambda d, e: False, "_mun_dias_bloqueados": lambda u: set()}
    exec(compile(ast.Module(body=nos, type_ignores=[]), str(MOTOR), "exec"), ns)   # noqa: S102 — o código do motor
    ns["DESLOC_CALCULA"] = ns["DESLOC_CONSOME"] = False    # sem coordenada no teste: o deslocamento não entra
    return ns


def _tarefa(os_id, usina, n, cat="MPM", corretiva=False, dur_h=10 / 60):
    return {"os_id": os_id, "codigo": f"{usina[:3].upper()}-{n}", "task_key": f"{os_id}|{n}", "ativo": usina,
            "cidade": usina, "coord": None, "tarefa_txt": f"[Grid Co.] - MPM - Item {n}", "estado_antes": "Não Iniciada",
            "tipo_bd": "", "corretiva": corretiva, "zeladoria": False, "termo": False, "mp_cat": cat,
            "mp_order": -1 if corretiva else 3, "rpn": 20, "reprog": False, "tier": 2 if corretiva else 4,
            "aging": False, "idade_dias": None, "boost_mes": False, "dur_h": dur_h, "etiquetas": "", "pin": None}


def _equipe_pa():
    """Como a PA Norte 01 na W44: uma usina com a OS de MPM de 29 subtarefas de 10 min e uma corretiva, e outra usina
    com 5 tarefas."""
    a = [_tarefa(15568, "Usina A", n) for n in range(29)] + [_tarefa(17047, "Usina A", 99, "OUTRA", True, 1.0)]
    b = [_tarefa(15107, "Usina B", n) for n in range(5)]
    return a + b


def _hm(txt):
    h, m = txt.split(" ")[0].split(":")
    return int(h) * 60 + int(m)


def test_ultima_semana_do_mes_espalha_a_mpm_pelos_dias_livres():
    ns = _escalonador(date(2026, 10, 26))                    # a W44: tem o dia 30
    assert ns["ULTIMA_SEMANA_MES"]
    rows, pend = ns["schedule_team"]("PA Teste", _equipe_pa())
    assert pend == []                                          # a MPM do fim do mês continua sem virar pendência
    assert len(rows) == 35
    excede = [r for r in rows if "EXCEDE HH" in r["Dia"]]
    assert excede == [], [(r["Dia"], r["Hora Fim"]) for r in excede]
    assert all(_hm(r["Hora Fim"]) <= 17 * 60 for r in rows)
    por_dia = {}
    for r in rows:
        por_dia[r["DiaIdx"]] = por_dia.get(r["DiaIdx"], 0) + 1
    assert len(por_dia) >= 3 and max(por_dia.values()) < 29, por_dia     # não fica tudo num dia só


def test_a_mpm_que_nao_cabe_em_dia_nenhum_entra_forcada_no_dia_com_mais_folga():
    """Mais MPM do que a semana inteira comporta: a sobra entra com [EXCEDE HH] (a regra do fim do mês), mas
    distribuída, e não empilhada no primeiro dia."""
    ns = _escalonador(date(2026, 10, 26))
    tarefas = [_tarefa(15568, "Usina A", n, dur_h=1.0) for n in range(40)]
    rows, pend = ns["schedule_team"]("PA Teste", tarefas)
    assert pend == [] and len(rows) == 40
    excede = [r for r in rows if "EXCEDE HH" in r["Dia"]]
    assert excede, "40 h numa semana de ~30 h: alguma tem de exceder"
    dias_excede = {r["DiaIdx"] for r in excede}
    assert len(dias_excede) >= 2, dias_excede


def test_fora_da_ultima_semana_nada_muda_a_mpm_que_sobra_e_pendencia():
    ns = _escalonador(date(2026, 10, 19))                    # a W43: sem o dia 30
    assert not ns["ULTIMA_SEMANA_MES"]
    tarefas = [_tarefa(15568, "Usina A", n, dur_h=1.0) for n in range(40)]
    rows, pend = ns["schedule_team"]("PA Teste", tarefas)
    assert not [r for r in rows if "EXCEDE HH" in r["Dia"]]
    assert len(rows) + len(pend) >= 40 and pend


@pytest.mark.parametrize("semana", [date(2026, 10, 26), date(2026, 10, 19)])
def test_a_corretiva_segue_forcada_no_dia_da_usina(semana):
    ns = _escalonador(semana)
    tarefas = [_tarefa(900 + n, "Usina A", n, "OUTRA", True, 4.0) for n in range(3)]   # 12 h de corretiva, 1 usina
    rows, pend = ns["schedule_team"]("PA Teste", tarefas)
    assert pend == [] and len(rows) == 3


@pytest.mark.parametrize("semana", [date(2026, 10, 26), date(2026, 10, 19)])
def test_o_preenchimento_respeita_o_dia_fixo_da_usina(semana):
    """"@usina X = qua" nas observações: a sobra da usina não vai para outro dia livre (na W44, a Santa Bárbara 1, fixada
    na quarta, ganhou 14 tarefas na sexta pelo passe de preenchimento). Na última semana do mês ela entra forçada na
    quarta; fora dela, vira pendência, como sempre."""
    ns = _escalonador(semana)
    ns["USINA_DIAS"] = {"usina a": {2}}
    tarefas = [_tarefa(15765, "Usina A", n, dur_h=1.0) for n in range(12)] + [_tarefa(15305, "Usina B", 0)]
    rows, pend = ns["schedule_team"]("SP Teste", tarefas)
    dias_a = {r["DiaIdx"] for r in rows if r["Ativo (Usina)"] == "Usina A"}
    assert dias_a == {2}, dias_a
    if ns["ULTIMA_SEMANA_MES"]:
        assert pend == [] and sum(r["Ativo (Usina)"] == "Usina A" for r in rows) == 12
    else:
        assert pend and all(p["Ativo"] == "Usina A" for p in pend)
