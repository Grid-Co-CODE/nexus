"""PCM → Insights do PCM (25/11/2026, `nexus/pcm/insights_pcm.py`): cinco frases com as regras da planilha de controle
semanal do PCM ("Menos é mais... Se a informação se repete, a gente mantém só uma informação"). O que se prova: aberta é
a de OS fora de Finalizados e Verificação; religamento só acima de 7 dias; MPM só a do mês, vencida e aberta; handover
só a usina com tarefa vencida; usina de teste e OS do backoffice fora; a OS parada é a conta do Radar; a tela mostra os
cinco cartões, o "Em dia" quando não há nada e o erro quando a Gestão PCM não abre."""
import json
from datetime import date

from nexus.pcm import insights_pcm as I

HOJE = date(2026, 11, 25)


def _t(os_, tipo, dias, usina="Cli - Usina A - SP", os_status="Em processo", aberta=True, **k):
    t = {"os": os_, "tipo": tipo, "dias": dias, "usina": usina, "osStatus": os_status, "aberta": aberta,
         "estado": "Não Iniciada" if aberta else "Finalizada", "tarefa": k.pop("tarefa", f"{tipo} {os_}"),
         "dataProg": k.pop("dataProg", "2026-11-10"), "criacao": k.pop("criacao", "2026-09-01"), "cluster": "SP 01",
         "responsavel": "Pessoa Teste", "atrasado": dias > 0}
    t.update(k)
    return t


def test_religamento_so_o_aberto_de_verdade_e_acima_de_7_dias():
    ts = [_t(1, "Religamento", 77, usina="Cli - Usina R - PA"), _t(2, "Religamento Remoto", 8), _t(3, "Religamento", 7),
          _t(4, "Religamento", 40, os_status="Verificação"),           # em verificação = concluída (regra da planilha)
          _t(5, "Religamento", 30, aberta=False)]
    r = I.religamentos(ts)
    assert [x["os"] for x in r["linhas"]] == ["1", "2"] and r["n"] == 2 and r["abertas"] == 3
    assert r["linhas"][0] == {"os": "1", "usina": "Usina R", "tipo": "Religamento", "dias": 77}


def test_handover_so_a_usina_com_tarefa_vencida():
    ts = [_t(10, "Handover", 100, usina="Cli - Usina H - SC"), _t(10, "Handover", 50, usina="Cli - Usina H - SC"),
          _t(11, "Handover", -5, usina="Cli - Usina N - SC")]             # handover aberto mas ainda no prazo
    h = I.handovers(ts)
    assert h["n"] == 1 and h["linhas"][0]["usina"] == "Usina H"
    assert (h["linhas"][0]["vencidas"], h["linhas"][0]["abertas"], h["linhas"][0]["dias"]) == (2, 2, 100)


def test_mpm_so_a_do_mes_vencida_e_aberta():
    ts = [_t(20, "Preventiva", 5, tarefa="[Grid] - MPM - Inversor", usina="Cli - Usina M - AL"),
          _t(20, "Preventiva", 0, tarefa="[Grid] - MPM - Cabine", usina="Cli - Usina M - AL", os_status="Verificação"),
          _t(21, "Preventiva", 3, tarefa="[Grid] - MPM - Inversor", usina="Cli - Usina O - AL", dataProg="2026-10-10"),
          _t(22, "Preventiva", -3, tarefa="[Grid] - MPM - Inversor", usina="Cli - Usina F - AL"),   # do mês, no prazo
          _t(23, "Preventiva", 9, tarefa="[Grid] - MPA - Inversor", usina="Cli - Usina A2 - AL")]
    m = I.mpm_do_mes(ts, HOJE)
    assert m["mes"] == "novembro" and m["n"] == 1
    assert m["linhas"][0] == {"usina": "Usina M", "total": 2, "feitas": 1, "vencidas": 1}


def test_usina_de_teste_e_backoffice_ficam_fora():
    g = {"tarefas": [_t(30, "Religamento", 20, usina="Cli - Usina TESTE - SP"), _t(31, "Religamento", 20, bo=True),
                     _t(31, "Corretiva", 20), _t(32, "Religamento", 20)]}
    assert [x["os"] for x in I.montar(g, {}, HOJE)["religamento"]["linhas"]] == ["32"]


def test_parada_e_a_conta_do_radar_e_rolagem_a_do_acompanhamento():
    g = {"tarefas": [_t(40, "Corretiva", 60, criacao="2026-09-01"), _t(41, "Corretiva", 2, criacao="2026-11-20")]}
    bd = {"semanas": [{"week": "2026-W48", "rows": [{"os_id": 40, "vezes": 6}, {"os_id": 41, "vezes": 4}]}]}
    d = I.montar(g, bd, HOJE)
    assert d["parada"]["n"] == 1 and d["parada"]["pior"]["os"] == "40"
    assert [(x["os"], x["vezes"]) for x in d["rolagem"]["linhas"]] == [("40", 6)]


def _fonte(app, tmp_path, gestao):
    (tmp_path / "g.json").write_text(json.dumps(gestao), encoding="utf-8")
    (tmp_path / "bd.json").write_text(json.dumps({"semanas": []}), encoding="utf-8")
    app.config.update(NEXUS_PCM_GESTAO_FONTE=str(tmp_path / "g.json"), NEXUS_PCM_FONTE=str(tmp_path / "bd.json"))


def test_a_tela_com_os_cinco_cartoes(app, logado, tmp_path):
    _fonte(app, tmp_path, {"geradoEm": "2026-11-25T01:23:00", "tarefas": [
        _t(50, "Religamento", 77, usina="Cli - Usina R - PA"), _t(51, "Handover", 30, usina="Cli - Usina H - SC")]})
    html = logado.get("/t/pcm/insights").get_data(as_text=True)
    assert html.count('class="ins-c ') == 5
    assert "religamento aberto há mais de 7 dias" in html and "Usina R, 77 dias" in html
    assert "/t/comando/conversa/os/50" in html                       # as observações do time: a conversa da OS
    assert "Nenhuma MPM de" in html and "Em dia" in html                # o que não tem nada diz "Em dia"
    assert "Gestão PCM de 25/11 às 01:23" in html


def test_a_tela_sem_a_gestao_diz_o_erro(app, logado, tmp_path):
    app.config.update(NEXUS_PCM_GESTAO_FONTE=str(tmp_path / "nao_existe.json"),
                      NEXUS_PCM_FONTE=str(tmp_path / "nao_existe_bd.json"))
    html = logado.get("/t/pcm/insights").get_data(as_text=True)
    assert "Não consegui ler a Gestão PCM" in html and 'class="ins-c ' not in html
