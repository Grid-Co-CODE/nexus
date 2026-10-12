"""Programação semanal no Nexus, etapa 1: ler a programação que está valendo (o banco_dados.json que o App de Campo
e o painel do PCM leem). Regras puras em nexus/pcm/semana.py; telas em nexus/pcm/telas.py. A tela Semana saiu em
12/10/2026 com o código dela (Levi: "pode excluir essa seção e o código dela"); as regras que ficam são as das telas
Tarefas e OS, Quadro da semana e Gerar a semana.

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


def test_fora_do_horario_conta_a_madrugada_mas_nao_a_mpa():
    sem = S.achar(banco())
    # a MPM das 00:00 é fora do horário; a MPA das 15:30 é janela própria
    assert [t["os_id"] for t in S.tarefas(sem, horario="fora")] == ["15033"]


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


def test_tela_semana_saiu_do_pcm(logado, fonte):
    """Levi, 12/10/2026: "PCM > Semana -> pode excluir essa seção e o código dela!"."""
    assert logado.get("/t/pcm/semana").status_code == 404
    html = logado.get("/t/pcm/tarefas").get_data(as_text=True)
    assert 'href="/t/pcm/semana"' not in html and 'href="/t/pcm/quadro"' in html
    assert not hasattr(S, "resumo") and not hasattr(S, "por_equipe")


def test_tela_tarefas_filtra_por_equipe(logado, fonte):
    html = logado.get("/t/pcm/tarefas?equipe=SP+Leste+02").get_data(as_text=True)
    assert "Tarefas e OS" in html
    assert "15020" in html and "15022" in html and "15031" not in html


def test_fonte_fora_do_ar_vira_aviso_e_nao_quebra(logado, app, tmp_path):
    app.config["NEXUS_PCM_FONTE"] = str(tmp_path / "nao-existe.json")
    resp = logado.get("/t/pcm/tarefas")
    assert resp.status_code == 200
    assert "Não consegui ler a programação" in resp.get_data(as_text=True)


def test_tela_sem_login_para_no_portao(cliente):
    resp = cliente.get("/t/pcm/tarefas")
    assert resp.status_code == 302 and "/entrar" in resp.headers["Location"]


# ── filtros em cascata (Levi, 09/10/2026: "Os filtros tem que se auto filtrar também") ─────────────────────
def test_filtros_de_tarefas_em_cascata():
    sem = S.achar(banco(), "2026-W40")
    f = {"equipe": "BA Sul 01", "dia": None, "status": None, "tipo": None, "busca": None, "horario": None}
    fac = S.facetas(sem, f)
    # com a equipe escolhida, Tipo e Dia só contam o que é dela
    assert fac["tipo"] == {"MPS": 1, "Handover": 1, "MPM": 1} and set(fac["dia"]) == {"qua", "qui"}
    # a equipe não se restringe a si mesma: dá para trocar de equipe sem limpar o resto
    assert fac["equipe"] == {"SP Leste 02": 4, "BA Sul 01": 3}
    assert S.facetas(sem, dict(f, equipe=None, tipo="MPA"))["equipe"] == {"SP Leste 02": 1}


def test_tela_tarefas_lista_so_as_opcoes_da_equipe(logado, fonte):
    html = logado.get("/t/pcm/tarefas?equipe=BA+Sul+01").get_data(as_text=True)
    tipo = html.split('id="f-tipo"', 1)[1].split("</select>", 1)[0]
    assert ">MPS (1)<" in tipo and "Corretiva" not in tipo and "MPA" not in tipo
    equipe = html.split('id="f-equipe"', 1)[1].split("</select>", 1)[0]
    assert ">SP Leste 02 (4)<" in equipe and ">BA Sul 01 (3)<" in equipe
