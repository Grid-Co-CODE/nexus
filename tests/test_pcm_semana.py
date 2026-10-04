"""Programação semanal no Nexus, etapa 1: ler a programação que está valendo (o banco_dados.json que o App de Campo
e o painel do PCM leem) e mostrá-la por equipe e dia. Regras puras em nexus/pcm/semana.py; telas em nexus/pcm/telas.py.

Nenhum teste aqui vai à rede: a fonte é um arquivo local com o mesmo formato do banco_dados.json.
"""
import json

import pytest

from nexus.pcm import semana as S

DIAS = {"seg": "28/09", "ter": "29/09", "qua": "30/09", "qui": "01/10", "sex": "02/10"}


def linha(equipe, usina, dia, h_ini, h_fim, duracao, status, tipo, os_id="15000", tarefa="Tarefa", reprog="Não",
          nova_os="", responsavel="Pessoa Teste"):
    return {"cliente": usina.split(" - ")[0], "usina": usina, "cluster": equipe, "tipo": tipo, "dia": dia,
            "os_id": os_id, "codigo": "COD-1", "tarefa": tarefa, "responsavel": responsavel, "resp_os": "",
            "criticidade": "Médio", "etiquetas": "", "status_bd": status, "status": status, "duracao": duracao,
            "h_ini": h_ini, "h_fim": h_fim, "desloc": 0.0, "reprog": reprog, "vezes": 1, "termo": "Não",
            "paralelo": "Não", "nova_os": nova_os, "solic_orig": "", "rolagem": "", "relatorio": "", "historico": [],
            "dataProgramada": "", "statusPai": ""}


def banco():
    w40 = [
        linha("SP Leste 02", "Thopen - Altair 1 - SP", "Segunda-feira", "07:30", "09:00", 1.5, "Finalizados",
              "Corretiva", os_id="15020", tarefa="Fusível queimado", reprog="Sim"),
        linha("SP Leste 02", "Thopen - Altair 1 - SP", "Segunda-feira", "09:15", "15:15", 6.0, "Não Iniciada", "MPM",
              os_id="15021", tarefa="MPM das cabines"),
        linha("SP Leste 02", "Thopen - Altair 1 - SP", "Terça-feira", "15:30", "19:30", 4.0, "Não Iniciada", "MPA",
              os_id="15023", tarefa="MPA da usina"),
        linha("SP Leste 02", "Thopen - Altair 1 - SP", "Terça-feira", "07:30", "08:36", 1.1, "Em progresso", "MPM",
              os_id="15022", tarefa="MPM cabine"),
        linha("BA Sul 01", "Semp - Tucano 1 - BA", "Quarta-feira", "07:30", "08:48", 1.3, "Finalizados", "MPS",
              os_id="15031", tarefa="MPS inversores", nova_os="Sim (BD)"),
        linha("BA Sul 01", "Semp - Tucano 1 - BA", "Quarta-feira", "09:03", "09:42", 0.65, "pausado", "Handover",
              os_id="15032", tarefa="Handover da usina"),
        # medido na semana 40: 264 de 1.373 tarefas começavam antes das 07:00 ou depois das 17:00 (sem MPA e zeladoria)
        linha("BA Sul 01", "Semp - Tucano 1 - BA", "Quinta-feira", "00:00", "01:06", 1.1, "Não Iniciada", "MPM",
              os_id="15033", tarefa="MPM empurrada para a madrugada"),
    ]
    w39 = [linha("BA Sul 01", "Semp - Tucano 1 - BA", "Sexta-feira", "07:30", "09:00", 1.5, "Finalizados",
                 "Corretiva", os_id="14900")]
    return {
        "geradoEm": "2026-09-30T18:00:00Z", "fonte": "teste", "semana_ativa": "2026-W40",
        "semanas": [
            {"week": "2026-W40", "num": 40, "label": "Semana 40 · 28 Set – 02 Out 2026", "dates": DIAS,
             "geradaEm": "2026-09-25T22:28:18Z", "resumo": {}, "rows": w40, "qualidade": [],
             "pendentes": [{"cliente": "Semp", "cluster": "BA Sul 01", "duracao": 1.5, "motivo": "não coube",
                            "os_id": "15099", "tarefa": "Corretiva que sobrou", "tipo": "Corretiva",
                            "usina": "Semp - Tucano 1 - BA"}]},
            {"week": "2026-W39", "num": 39, "label": "Semana 39 · 21–25 Set 2026", "dates": DIAS,
             "geradaEm": "2026-09-18T00:41:50Z", "resumo": {}, "rows": w39, "pendentes": [], "qualidade": []},
        ],
        "alertas": {}, "motivos": [],
    }


# ── regras ───────────────────────────────────────────────────────────────────────────────────────────────

def test_semanas_da_mais_nova_para_a_mais_velha_com_a_ativa_marcada():
    L = S.semanas(banco())
    assert [s["week"] for s in L] == ["2026-W40", "2026-W39"]
    assert L[0]["ativa"] and not L[1]["ativa"]


def test_achar_semana():
    d = banco()
    assert S.achar(d)["week"] == "2026-W40"              # sem pedir: a ativa
    assert S.achar(d, "2026-W39")["num"] == 39
    assert S.achar(d, "2026-W99") is None


def test_dia_curto_ignora_acento_e_o_resto():
    assert S.dia_curto("Terça-feira") == "ter"
    assert S.dia_curto("Segunda-feira (28/09) [NOTURNO]") == "seg"
    assert S.dia_curto("") == ""


def test_resumo_da_semana():
    r = S.resumo(S.achar(banco()))
    assert (r["linhas"], r["os"], r["usinas"], r["equipes"]) == (7, 7, 2, 2)
    assert (r["feitas"], r["em_andamento"], r["nao_iniciadas"]) == (2, 2, 3)
    assert r["aderencia"] == 29                           # 2 de 7 finalizadas
    assert r["horas"] == pytest.approx(15.65, abs=0.01)
    assert (r["pendentes"], r["reprogramadas"], r["novas"]) == (1, 1, 1)


def test_fora_do_horario_conta_a_madrugada_mas_nao_a_mpa():
    sem = S.achar(banco())
    assert S.resumo(sem)["fora_horario"] == 1             # a MPM das 00:00; a MPA das 15:30 é janela própria
    assert [t["os_id"] for t in S.tarefas(sem, horario="fora")] == ["15033"]


def test_por_equipe_mostra_horas_por_dia_e_o_dia_que_passa_da_capacidade():
    eqs = S.por_equipe(S.achar(banco()))
    assert [e["equipe"] for e in eqs] == ["BA Sul 01", "SP Leste 02"]
    sp = eqs[1]
    assert (sp["linhas"], sp["feitas"], sp["aderencia"], sp["usinas"]) == (4, 1, 25, 1)
    assert sp["horas_dia"]["seg"] == pytest.approx(7.5)
    assert sp["estourou"] == ["seg"]                     # 7,5 h > 7 h de capacidade (80% do dia)
    assert eqs[0]["pendentes"] == 1 and sp["pendentes"] == 0


def test_mpa_fica_na_janela_da_noite_e_fora_da_capacidade_do_dia():
    """Medido na semana 40: com a MPA na conta, 93 de 193 dias de equipe passavam de 7 h; sem ela, 46. A MPA roda
    das 15:30 à 01:30 (o gerador trunca o dia às 15:30), então não disputa as 7 h do dia."""
    sp = S.por_equipe(S.achar(banco()))[1]
    assert sp["horas_dia"]["ter"] == pytest.approx(1.1)   # só a MPM; a MPA de 4 h não entra
    assert sp["horas_noite"]["ter"] == pytest.approx(4.0)
    assert "ter" not in sp["estourou"]


def test_tarefas_filtradas_e_na_ordem_do_dia():
    sem = S.achar(banco())
    sp = S.tarefas(sem, equipe="SP Leste 02")
    assert [t["os_id"] for t in sp] == ["15020", "15021", "15022", "15023"]
    assert len(S.tarefas(sem, status="feita")) == 2
    assert len(S.tarefas(sem, status="andamento")) == 2
    assert {t["os_id"] for t in S.tarefas(sem, busca="tucano")} == {"15031", "15032", "15033"}
    assert {t["os_id"] for t in S.tarefas(sem, dia="qua")} == {"15031", "15032"}
    assert [t["os_id"] for t in S.tarefas(sem, busca="15021")] == ["15021"]


# ── telas ────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def fonte(app, tmp_path):
    arq = tmp_path / "banco_dados.json"
    arq.write_text(json.dumps(banco(), ensure_ascii=False), encoding="utf-8")
    app.config["NEXUS_PCM_FONTE"] = str(arq)
    return arq


def test_tela_semana_mostra_a_semana_ativa_por_equipe(logado, fonte):
    html = logado.get("/t/pcm/semana").get_data(as_text=True)
    assert "Semana 40" in html and "SP Leste 02" in html and "BA Sul 01" in html
    assert "29%" in html                                  # aderência da semana
    assert "horario=fora" in html                         # o atalho para as tarefas fora do horário
    assert "+4 h de MPA" in html                          # a noite da terça, à parte
    assert "pcm-estourou" in html                         # a segunda da SP Leste 02 passou de 7 h
    assert "Em construção" not in html


def test_tela_semana_troca_de_semana(logado, fonte):
    html = logado.get("/t/pcm/semana?semana=2026-W39").get_data(as_text=True)
    assert "Semana 39" in html
    assert logado.get("/t/pcm/semana?semana=2026-W99").status_code == 404


def test_tela_tarefas_filtra_por_equipe(logado, fonte):
    html = logado.get("/t/pcm/tarefas?equipe=SP+Leste+02").get_data(as_text=True)
    assert "Tarefas e OS" in html
    assert "15020" in html and "15022" in html and "15031" not in html


def test_fonte_fora_do_ar_vira_aviso_e_nao_quebra(logado, app, tmp_path):
    app.config["NEXUS_PCM_FONTE"] = str(tmp_path / "nao-existe.json")
    resp = logado.get("/t/pcm/semana")
    assert resp.status_code == 200
    assert "Não consegui ler a programação" in resp.get_data(as_text=True)


def test_tela_sem_login_para_no_portao(cliente):
    resp = cliente.get("/t/pcm/semana")
    assert resp.status_code == 302 and "/entrar" in resp.headers["Location"]
