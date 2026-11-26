"""A coleta de dados de geração no dia da data programada (reunião do PCM, 24/11/2026; `_dia_da_coleta` no motor).

Quem programa escolhe o dia da coleta pela presença do time na usina, em geral no começo do mês, para coletar o mês
anterior; o motor escolhia o dia sem olhar a data e adiantava a coleta (a W49 começa na segunda 30/11, antes de o mês
fechar). Provado na W41 real, pela foto de 02/10: as 48 coletas da semana no dia programado, nenhuma antes; 21 forçadas
com [EXCEDE HH] (todas com data na segunda). O que estes testes seguram: quem é coleta de geração; o dia sai da data só
dentro da semana; no escalonador ela cai no dia, nunca antes, mesmo forçada; feriado vai para o próximo dia útil e, sem
dia útil depois, para as pendências (entra na próxima semana como atrasada); o pin das observações vence."""
import ast
import unicodedata
from datetime import date, datetime

import pandas as pd

from test_pcm_motor_fim_do_mes import MOTOR, _escalonador, _tarefa


def _funcoes_da_coleta(semana: date) -> dict:
    arvore = ast.parse(MOTOR.read_text(encoding="utf-8"))
    nos = [n for n in arvore.body if isinstance(n, ast.FunctionDef)
           and n.name in ("_sem_acento", "eh_coleta_de_geracao", "_dia_da_coleta")]
    ns = {"unicodedata": unicodedata, "pd": pd, "WEEK_START": semana}
    exec(compile(ast.Module(body=nos, type_ignores=[]), str(MOTOR), "exec"), ns)   # noqa: S102 — o código do motor
    return ns


def _coleta(os_id, usina, dia, n=0, dur_h=0.5):
    tk = _tarefa(os_id, usina, n, cat="OUTRA", dur_h=dur_h)
    tk.update(tarefa_txt="[Grid Co.] - Coleta de Dados de Geração", tipo_bd="Administrativa", tier=5, mp_order=5,
              coleta_dia=dia)
    return tk


def test_quem_e_coleta_de_geracao():
    f = _funcoes_da_coleta(date(2026, 11, 30))["eh_coleta_de_geracao"]
    for sim in ("Coleta de Dados de Geração", "[Athon][X] - Coleta de Dados de Geração", "THOPEN - Coleta diária de Geração",
                "[Grid Co.] - Coleta e análise de dados de geração", "Coleta de Geração - Solicitação Thopen"):
        assert f(sim), sim
    for nao in ("Coleta de Óleo - Transformador", "[Axis] - Coleta e análise de dados", "Inspeção Geral do Inversor", ""):
        assert not f(nao), nao


def test_o_dia_sai_da_data_so_dentro_da_semana():
    d = _funcoes_da_coleta(date(2026, 11, 30))["_dia_da_coleta"]
    linha = lambda quando, t="Coleta de Dados de Geração": {"Tarefa": t, "Data Programada": pd.Timestamp(quando)}  # noqa: E731
    assert d(linha(datetime(2026, 12, 1, 8, 0))) == 1            # terça 01/12
    assert d(linha(datetime(2026, 11, 30, 17, 31))) == 0         # segunda, com hora
    assert d(linha(datetime(2026, 12, 4))) == 4                  # sexta
    assert d(linha(datetime(2026, 12, 5))) is None               # sábado: fica para a próxima semana (atrasada)
    assert d(linha(datetime(2026, 11, 27))) is None              # atrasada: vai pela fila, sem dia preso
    assert d(linha(datetime(2026, 12, 1), "Coleta de Óleo - Transformador")) is None
    assert d({"Tarefa": "Coleta de Dados de Geração", "Data Programada": pd.NaT}) is None


def test_a_coleta_cai_no_dia_programado_e_nunca_antes():
    ns = _escalonador(date(2026, 11, 30))
    tarefas = [_coleta(20001, "Usina A", 3)] + [_tarefa(20002, "Usina A", n, dur_h=0.5) for n in range(4)]
    rows, pend = ns["schedule_team"]("PA Teste", tarefas)
    coleta = [r for r in rows if "Coleta" in str(r["Tarefa"])]
    assert pend == [] and len(coleta) == 1 and coleta[0]["DiaIdx"] == 3, [(r["Tarefa"], r["DiaIdx"]) for r in rows]


def test_dia_cheio_de_coletas_entra_forcado_no_mesmo_dia():
    ns = _escalonador(date(2026, 11, 30))
    tarefas = [_coleta(20100 + n, "Usina A", 0, n, dur_h=1.0) for n in range(12)]   # 12 h numa segunda
    rows, pend = ns["schedule_team"]("PA Teste", tarefas)
    assert pend == [] and len(rows) == 12
    assert {r["DiaIdx"] for r in rows} == {0}
    assert any("EXCEDE HH" in r["Dia"] for r in rows)


def test_feriado_vai_para_o_proximo_dia_util_e_sem_ele_para_a_proxima_semana():
    ns = _escalonador(date(2026, 11, 30))
    ns["_is_feriado_para_equipe"] = lambda d, e: d.weekday() == 2          # quarta é feriado
    rows, pend = ns["schedule_team"]("PA Teste", [_coleta(20201, "Usina A", 2)])
    assert pend == [] and [r["DiaIdx"] for r in rows] == [3]                # quinta, nunca a terça
    ns = _escalonador(date(2026, 11, 30))
    ns["_is_feriado_para_equipe"] = lambda d, e: d.weekday() >= 3          # quinta e sexta
    rows, pend = ns["schedule_team"]("PA Teste", [_coleta(20202, "Usina A", 3)])
    assert rows == [] and len(pend) == 1 and "próxima semana" in str(pend[0])


def _com_constante(ns, nome):
    """Põe no escalonador do teste uma constante do motor que o carregador do fim do mês não traz."""
    arvore = ast.parse(MOTOR.read_text(encoding="utf-8"))
    nos = [n for n in arvore.body if isinstance(n, ast.Assign) and any(getattr(a, "id", "") == nome for a in n.targets)]
    exec(compile(ast.Module(body=nos, type_ignores=[]), str(MOTOR), "exec"), ns)   # noqa: S102 — o código do motor
    return ns


def test_o_pin_das_observacoes_vence_a_data():
    ns = _com_constante(_com_constante(_escalonador(date(2026, 11, 30)), "SIGLAS_MULTI"), "_RE_SIGLA")
    ns["OS_PINS"] = {20301: [{"dia": 1, "tarefas": None, "start_min": None}]}
    tk = _coleta(20301, "Usina A", 3)
    tk["pin"] = ns["OS_PINS"][20301]
    rows, pend = ns["schedule_team"]("PA Teste", [tk])
    assert pend == [] and [r["DiaIdx"] for r in rows] == [1]
