"""O vídeo wall do Mapa de equipe (12/11/2026). Levi, com o mockup do COS ("Usinas com problema agora"): "Prepare um modo
vídeo wall que apareça informações como no anexo 1 do lado esquerdo do mapa!". As escolhas dele no mesmo dia: todas as
ocorrências abertas, agrupadas; a tela se atualiza a cada 2 minutos; a lista que não cabe rola sozinha, devagar.

A conta do painel é pura (`campo/equipe/parede.py`) e lê a MESMA fotografia da Ronda COS que dá a cor das usinas no mapa
(a régua de Comando > Usinas); a rota é a do mapa com `?tv=1`, com o mesmo portão e o mesmo registro da LGPD."""
from datetime import datetime, timedelta, timezone

from test_equipe_mapa_ml import _dados, com_mapa_base  # noqa: F401
from test_equipe_tela import (EMAIL, PCM, USINA_A, USINA_B, _acessos, _entrar, _html, banco, pontos,  # noqa: F401
                              relogio, setor)

from nexus.campo.equipe import parede as PA

AGORA = datetime(2026, 11, 12, 3, 0, tzinfo=timezone.utc)              # 00:00 de Brasília


def _oc(min_atras, **mudar):
    o = {"os": "18858", "tipo_tarefa": "Corretiva", "tipo_falha": "", "problema": "", "etapa": "Técnico acionado",
         "falha": "", "equipamentos": [], "aguardando": [], "ultima_nota": None, "usina_cod": "",
         "abertura": (AGORA - timedelta(minutes=min_atras)).isoformat()}
    o.update(mudar)
    return o


PARADA = dict(tipo_tarefa="Religamento", tipo_falha="Desligamento de usina", problema="usina")
REDE = dict(tipo_tarefa="Corretiva", tipo_falha="Falta de energia da concessionária", problema="rede")
INVERSOR = dict(tipo_falha="Inversor desligado", problema="inv")
COM = dict(tipo_falha="Falha de comunicação", problema="com")
FURTO = dict(tipo_falha="Furto", problema="furto")


def test_o_grupo_de_cada_ocorrencia_pela_regua_do_comando():
    """O grupo do painel refina a régua de Comando > Usinas (`classificar`): o crítico que é falta de energia da rede vai
    à Rede concessionária, o outro crítico é usina parada (o religamento em campo também); o inversor, a comunicação e o
    que sobra (furto, outra corretiva) têm o grupo deles."""
    assert PA.grupo(_oc(5, **PARADA)) == "parada"
    assert PA.grupo(_oc(5, tipo_falha="Atuação de proteção", problema="")) == "parada"
    assert PA.grupo(_oc(5, **REDE)) == "rede"
    # o religamento de uma usina que a rede derrubou é Rede concessionária, como o placar da Ronda COS a conta
    assert PA.grupo(_oc(5, tipo_tarefa="Religamento", tipo_falha="Desligamento de usina", problema="rede")) == "rede"
    assert PA.grupo(_oc(5, **INVERSOR)) == "inversor"
    assert PA.grupo(_oc(5, **COM)) == "com"
    assert PA.grupo(_oc(5, **FURTO)) == "outras"


def test_a_duracao_como_o_mockup_conta():
    assert [PA.duracao(m) for m in (0, 12, 48, 132, 60 * 28, 60 * 48, 60 * 24 * 6 + 30)] == \
        ["agora", "12 min", "48 min", "2 h 12", "1 d 4 h", "2 d", "6 d"]


def test_o_painel_um_cartao_por_usina_no_grupo_da_pior():
    cos = {"ocs": {7: [_oc(132, **PARADA, usina_cod="APR100", falha="Queda total, trip 27", os="18858",
                           ultima_nota={"quando": (AGORA - timedelta(minutes=12)).isoformat(),
                                        "texto": "Equipe a caminho"}),
                       _oc(600, **COM)],
                   8: [_oc(60 * 28, **INVERSOR, usina_cod="RDR200", equipamentos=["Inversor 3"], falha="Sem gerar",
                           etapa="Aguardando peça", os="R-abc")],
                   9: [_oc(60 * 24 * 6, **REDE, usina_cod="CLR100")],
                   12: [_oc(30, **INVERSOR)]},
           "lidas": {7, 8, 9, 10, 12}, "leitura": "23:37"}
    fichas = {7: {"codigo": "THPN-APR100", "potencia_contratual": "3.2"}, 8: {"potencia_contratual": "0,9"}}
    p = PA.montar(cos, uids=["7", "8", "9", "10", "11"], nome_de=lambda u: f"Usina {u}",
                  ficha_de=lambda u: fichas.get(int(u), {}), agora=AGORA)
    assert p["ligada"] and p["leitura"] == "23:37"
    # a usina 12 não está no mapa (sem coordenada): fica fora do painel e das contas
    assert [(k["id"], k["n"]) for k in p["kpis"]] == [("abertas", 3), ("parada", 1), ("inversor", 1), ("rede", 1),
                                                      ("com", 0), ("outras", 0)]
    assert [g["id"] for g in p["grupos"]] == ["parada", "inversor", "rede"]           # só os grupos com cartão
    c = p["grupos"][0]["cartoes"][0]
    assert (c["codigo"], c["nome"], c["mwp"], c["dur"], c["os"], c["mais"]) == \
        ("APR100", "Usina 7", "3,2 MWp", "2 h 12", "OS 18858", 1)
    assert c["falha"] == "Queda total, trip 27" and c["nota"] == "11/11 23:48 · Equipe a caminho"           # de outro dia: com a data
    assert (c["etapa"], c["etapa_tom"]) == ("Técnico acionado", "info")
    c = p["grupos"][1]["cartoes"][0]
    assert (c["codigo"], c["mwp"], c["dur"], c["os"], c["etapa_tom"]) == ("RDR200", "0,9 MWp", "1 d 4 h", "ainda sem OS",
                                                                          "alerta")
    assert c["falha"] == "Sem gerar · Inversor 3"
    assert p["grupos"][2]["cartoes"][0]["dur"] == "6 d"
    assert p["rodape"] == {"sem_ocorrencia": 1, "sem_leitura": 1}


def test_a_ordem_no_grupo_e_a_mais_antiga_primeiro():
    cos = {"ocs": {1: [_oc(30, **INVERSOR)], 2: [_oc(300, **INVERSOR)], 3: [_oc(90, **INVERSOR)]}, "lidas": {1, 2, 3}}
    p = PA.montar(cos, uids=["1", "2", "3"], nome_de=str, ficha_de=lambda u: {}, agora=AGORA)
    assert [c["uid"] for c in p["grupos"][0]["cartoes"]] == ["2", "3", "1"]


def test_sem_a_leitura_do_cos_o_painel_diz():
    p = PA.montar(None, uids=["1"], nome_de=str, ficha_de=lambda u: {}, agora=AGORA)
    assert not p["ligada"] and p["grupos"] == [] and p["kpis"] == []


# ── a rota ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _cos_falso(monkeypatch):
    from nexus.torres.campo import equipe_tela as ET
    monkeypatch.setattr(ET, "_cos_por_usina", lambda b: {
        "ocs": {USINA_A: [_oc(132, **PARADA, usina_cod="ALF100", falha="Queda total")]},
        "lidas": {USINA_A, USINA_B}, "leitura": "11:40"})


def test_o_video_wall_abre_sem_a_casca_com_o_painel_e_o_mapa(cliente, pontos, setor, com_mapa_base, monkeypatch):
    _cos_falso(monkeypatch)
    st, html = _html(_entrar(cliente, EMAIL[PCM]), query_string={"tv": "1"})
    assert st == 200 and "data-eq-tv" in html
    assert 'class="casca' not in html and "ph-sidebar-simple" not in html                 # sem o menu do Nexus
    painel = html.split('class="eqtv-cos"', 1)[1].split('class="eqtv-mapa"', 1)[0]
    assert "Usinas com problema agora" in painel and "leitura 11:40" in painel
    assert "Usina parada" in painel and "ALF100" in painel and "Queda total" in painel
    assert "1 usina sem ocorrência aberta no COS" in painel
    d = _dados(html)
    assert d["modo"] == "tecnicos" and d["tv"] is True and d["tecnicos"]
    # a tela se atualiza sozinha a cada 2 minutos (com e sem JavaScript) e a lista que não cabe rola sozinha
    assert 'data-recarrega-s="120"' in html and '<meta http-equiv="refresh" content="120">' in html
    assert "data-eqtv-rola" in html
    # cada abertura (e cada atualização) do vídeo wall é um acesso no registro da LGPD, como a do mapa
    assert [a["acao"] for a in _acessos(pontos)] == ["abriu_mapa"]


def test_o_botao_video_wall_na_tela_do_mapa(cliente, pontos, setor, com_mapa_base):
    _, html = _html(_entrar(cliente, EMAIL[PCM]))
    assert 'data-eq-videowall' in html
    botao = html.split("data-eq-videowall", 1)[1].split("</a>", 1)[0]
    assert "tv=1" in botao and "Vídeo wall" in botao


def test_sem_o_mapa_base_nao_ha_video_wall(cliente, pontos, setor):
    _, html = _html(_entrar(cliente, EMAIL[PCM]), query_string={"tv": "1"})
    assert "data-eq-tv" not in html and "data-eq-videowall" not in html


def test_sem_o_cos_o_painel_diz_e_o_mapa_segue(cliente, pontos, setor, com_mapa_base, monkeypatch):
    from nexus.torres.campo import equipe_tela as ET
    monkeypatch.setattr(ET, "_cos_por_usina", lambda b: None)
    st, html = _html(_entrar(cliente, EMAIL[PCM]), query_string={"tv": "1"})
    painel = html.split('class="eqtv-cos"', 1)[1].split('class="eqtv-mapa"', 1)[0]
    assert st == 200 and "Sem a leitura do COS" in painel and _dados(html)["usinas"]
