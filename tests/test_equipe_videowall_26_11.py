"""O vídeo wall em três colunas (26/11/2026; `campo/equipe/parede.py`).

O Levi aprovou o protótipo do Mapa de equipe redesenhado ("ok sobe"), com a referência do COS (a sugestão 10, "Videowall
do COS: ocorrências, mapa e timeline em três colunas", do Fillipe, 08/11/2026) e os pedidos dele em cima dela:
- "do lado esquerdo [...] as usinas com problema agora, e aí tem quanto tempo, e do lado direito vai ter os eventos de hoje
  focados nas ocorrências [...] foca nas ocorrências do COS [...] mostra informações, tipo assim, técnico na usina";
- "a cada 20 segundos vai mudar [...] alarmes, chuva e equipes"; "pode até clicar e dar um zoom automático. Mas é
  importante ter um botão para voltar pro mapa".

A conta é pura: quem está na usina (a situação do mapa, a até 1 km) e desde quando (a chegada do dia), quem está a
caminho (a saída com o destino da programação e a chegada prevista), a linha do tempo de hoje das usinas com ocorrência
aberta (a abertura e a última nota do COS, o técnico chegando, saindo ou a caminho) e a contagem do mapa."""
from datetime import datetime, timedelta, timezone

from nexus.campo.equipe import parede as PA

AGORA = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)              # 15:00 de Brasília
BRT = timezone(timedelta(hours=-3))


def _em(h, m, dia=0):
    """O instante de hoje (ou de `dia` dias atrás) às h:m de Brasília, em ISO."""
    return (datetime(2026, 11, 26, h, m, tzinfo=BRT) - timedelta(days=dia)).isoformat()


def _utc(h, m):
    return datetime(2026, 11, 26, h, m, tzinfo=BRT).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ev(pid, tipo, h, m, usina=None, destino=None, prevista=None):
    return {"pessoa_id": pid, "tipo": tipo, "hora": f"{h:02d}:{m:02d}", "instante": _utc(h, m), "usina_id": usina,
            "destino_usina_id": destino, "chegada_prevista": _utc(*prevista) if prevista else None,
            "nome": {1: "Ana Teste", 2: "Bia Teste", 3: "Caio Teste"}[pid]}


LINHAS = [{"pid": 1, "nome": "Ana Teste", "s": {"chave": "na_usina", "usina_perto": (7, 0.3)}},
          {"pid": 2, "nome": "Bia Teste", "s": {"chave": "deslocamento", "usina_perto": None}},
          {"pid": 3, "nome": "Caio Teste", "s": {"chave": "fora_usina", "usina_perto": (12, 4.2)}}]
# do mais novo ao mais velho, como o `_eventos_do_dia` entrega
EVENTOS = [_ev(1, "chegou", 14, 45, usina=7), _ev(2, "saiu", 14, 19, usina=None, destino=8, prevista=(15, 40)),
           _ev(1, "saiu", 11, 0, usina=7, destino=None), _ev(3, "chegou", 10, 30, usina=12),
           _ev(1, "inicio", 7, 0, usina=7)]


def test_quem_esta_na_usina_e_quem_esta_a_caminho():
    t = PA.tecnicos_nas_usinas(LINHAS, EVENTOS)
    # a Ana está na usina 7 desde a ÚLTIMA chegada (14:45; saiu às 11:00 e voltou); a Bia vai à 8 e chega 15:40
    assert t == {"7": [{"nome": "Ana Teste", "tipo": "na_usina", "texto": "Ana Teste na usina desde 14:45"}],
                 "8": [{"nome": "Bia Teste", "tipo": "a_caminho", "texto": "Bia Teste a caminho, chega 15:40"}]}
    # sem o evento da chegada (o primeiro ponto do dia já na usina conta como chegada), só "na usina"
    sem_ev = PA.tecnicos_nas_usinas(LINHAS[:1], [])
    assert sem_ev == {"7": [{"nome": "Ana Teste", "tipo": "na_usina", "texto": "Ana Teste na usina"}]}
    assert PA.tecnicos_nas_usinas(LINHAS[:1], [_ev(1, "inicio", 7, 0, usina=7)])["7"][0]["texto"] == "Ana Teste na usina desde 07:00"


def _oc(**mudar):
    o = {"os": "", "tipo_tarefa": "Corretiva", "tipo_falha": "", "problema": "", "etapa": "", "falha": "",
         "equipamentos": [], "aguardando": [], "ultima_nota": None, "usina_cod": "", "abertura": _em(9, 0, dia=2)}
    o.update(mudar)
    return o


COS = {"ocs": {7: [_oc(tipo_tarefa="Religamento", tipo_falha="Desligamento de usina", problema="usina", os="18858",
                       falha="Queda total, trip 27", usina_cod="APR100", abertura=_em(13, 0),
                       ultima_nota={"quando": _em(14, 30), "texto": "Técnico a caminho"})],
               8: [_oc(tipo_falha="Inversor desligado", problema="inv", os="18851", falha="Falha de isolamento",
                       ultima_nota={"quando": _em(9, 10), "texto": "Peça pedida"})],
               9: [_oc(tipo_falha="Falha de comunicação", problema="com", abertura=_em(22, 0, dia=1),
                       ultima_nota={"quando": _em(23, 0, dia=1), "texto": "Sem retorno"})]},
       "lidas": [7, 8, 9, 12], "leitura": "14:58"}
NOMES = {"7": "Alto Paraná 1", "8": "Tanabi", "9": "Cipó Guaçu", "12": "Colorado 2"}


def test_as_ocorrencias_mais_recentes_com_o_tecnico():
    """A coluna da direita (27/11/2026, Levi: "É interessante mostrar as ocorrências atuais, as que aconteceram agora, as
    ocorrências mais recentes do COS, e aí mostrar se o técnico chegou, se ele está chegando, se ele está em
    deslocamento"): cada ocorrência aberta, da mais nova para a mais velha, com a abertura, há quanto tempo, a falha, a
    OS, a última nota do COS e o técnico ligado a ela (na usina desde, ou a caminho com a chegada prevista)."""
    tec = PA.tecnicos_nas_usinas(LINHAS, EVENTOS)
    oc = PA.ocorrencias_recentes(COS, ["7", "8", "9", "12"], NOMES.get, lambda u: {}, tec, AGORA)
    assert [(o["uid"], o["quando"], o["ha"]) for o in oc] == [
        ("7", "13:00", PA.duracao(120)), ("9", "25/11 22:00", PA.duracao(17 * 60)), ("8", "24/11 09:00", PA.duracao(54 * 60))]
    a = oc[0]
    assert (a["usina"], a["codigo"], a["texto"], a["os"], a["nota"], a["tom"]) == (
        "Alto Paraná 1", "APR100", "Usina parada: Queda total, trip 27", "OS 18858", "14:30 · Técnico a caminho", "critico")
    assert a["tecnicos"] == [{"nome": "Ana Teste", "tipo": "na_usina", "texto": "Ana Teste na usina desde 14:45"}]
    assert oc[2]["tecnicos"] == [{"nome": "Bia Teste", "tipo": "a_caminho", "texto": "Bia Teste a caminho, chega 15:40"}]
    assert oc[1]["tecnicos"] == [] and oc[1]["nota"] == "25/11 23:00 · Sem retorno" and oc[1]["tom"] == "semcom"
    # sem a leitura do COS, nada
    assert PA.ocorrencias_recentes(None, ["7"], NOMES.get, lambda u: {}, tec, AGORA) == []


def test_a_contagem_do_mapa():
    agora = {"7": {"tom": "critico"}, "8": {"tom": "alerta"}, "9": {"tom": "semcom"}, "12": {"tom": "ok"},
             "13": {"tom": "ok"}, "14": {"tom": "neutro"}}
    # as palavras do Agora de Comando > Usinas (a mesma régua de cor), cada uma com o que engloba em poucas palavras
    # (27/11/2026, Levi: "unir o texto [...] de explicação com esse usinas, alarmes e equipes e tentar deixar o texto mais
    # resumido, porque deixou o mapa pequeno")
    c = PA.contagem(agora)
    assert [(x["id"], x["n"], x["rotulo"]) for x in c] == [("critico", 1, "críticas"), ("alerta", 1, "em atenção"),
                                                            ("semcom", 1, "sem comunicação"), ("ok", 2, "normais"),
                                                            ("neutro", 1, "sem leitura")]
    assert all(x["explica"] and len(x["explica"]) <= 40 for x in c)


def test_as_equipes_em_deslocamento():
    """A lista "Equipes em deslocamento" do mapa (a referência do COS): quem saiu, a que horas, para onde (o destino da
    programação) e a chegada prevista; sem destino programado, diz isso."""
    d = PA.deslocamentos(LINHAS, EVENTOS, NOMES.get)
    assert d == [{"nome": "Bia Teste", "saiu": "14:19", "uid": "8", "para": "Tanabi", "chega": "15:40"}]
    sem_destino = [{"pid": 2, "nome": "Bia Teste", "s": {"chave": "deslocamento", "usina_perto": None}}]
    ev = [_ev(2, "saiu", 13, 5, usina=7)]
    assert PA.deslocamentos(sem_destino, ev, NOMES.get) == [
        {"nome": "Bia Teste", "saiu": "13:05", "uid": "", "para": "", "chega": ""}]


# ── a tela (a rota do mapa com ?tv=1) ──────────────────────────────────────────────────────────────────────────────────
from test_equipe_mapa_ml import _dados, com_mapa_base  # noqa: E402,F401
from test_equipe_parede import _cos_falso  # noqa: E402
from test_equipe_tela import EMAIL as EMAIL_T, PCM, _entrar, _html, banco, pontos, relogio, setor  # noqa: E402,F401


def test_o_video_wall_em_tres_colunas(cliente, pontos, setor, com_mapa_base, monkeypatch):  # noqa: F811
    _cos_falso(monkeypatch)
    st, html = _html(_entrar(cliente, EMAIL_T[PCM]), query_string={"tv": "1"})
    assert st == 200
    cos = html.split('class="eqtv-cos"', 1)[1].split('class="eqtv-mapa"', 1)[0]
    mapa = html.split('class="eqtv-mapa"', 1)[1].split('class="eqtv-tl"', 1)[0]
    tl = html.split('class="eqtv-tl"', 1)[1]
    # à esquerda, a usina com problema e o técnico que está nela (a Naira, a 0,8 km da Alfa, primeira posição do dia)
    assert "Queda total" in cos and "Naira Teste na usina desde" in cos and 'data-tv-uid="7"' in cos
    # no meio, o tipo do mapa (gira a cada 20 s), o Brasil inteiro e o Sair sempre à vista, e a contagem
    # 27/11/2026 (Levi: "Eu quero que abra focado nas usinas [...] ênfase em usinas"): o 1º tipo é Usinas, e abre nele
    for tipo in ("usinas", "chuva", "equipes"):
        assert f'data-tv-tipo="{tipo}"' in mapa
    assert 'data-tv-tipo="alarmes"' not in mapa and 'data-tv-tipo="usinas" aria-pressed="true"' in mapa
    assert "Usinas, alarmes e equipes" in mapa
    # o que cada cor engloba, junto da contagem no alto do mapa e curto (27/11/2026: a legenda separada encolhia o mapa)
    assert 'class="eqtv-legenda"' not in html
    for termo in ("usina desligada", "inversor", "o COS não enxerga", "sem ocorrência aberta", "o COS não trouxe"):
        assert termo in mapa, termo
    # a linha do tempo não rola sozinha (Levi: "não precisa ficar rolando automático não"): rola na mão
    assert "data-eqtv-rola-tl" not in html
    assert "data-tv-brasil" in mapa and "data-tv-gira" in mapa and "Sair" in mapa
    assert "críticas" in mapa and "normais" in mapa and "Equipes em deslocamento" in mapa
    # à direita, as ocorrências mais recentes do COS com o técnico de cada uma (27/11/2026): a Naira na Alfa
    assert "Ocorrências mais recentes" in tl and "Queda total" in tl and "Naira Teste na usina desde" in tl
    assert "Eventos de hoje" not in tl and "chegou na usina" not in tl
    # as duas visões da coluna (27/11/2026, "Visão técnico, visão ocorrências"): abre nas Ocorrências; a dos técnicos traz
    # a Naira na Usina Alfa, com a ocorrência aberta dela
    assert 'data-tv-visao-bt="ocorrencias" aria-pressed="true"' in tl and 'data-tv-visao-bt="tecnicos"' in tl
    tec = tl.split('data-tv-visao-so="tecnicos" hidden>', 2)[-1]
    assert "Técnicos agora" in tl and "Naira Teste" in tec and "na Usina Alfa Teste desde" in tec
    assert "ocorrência aberta: Usina parada" in tec and 'data-tv-pid="1"' in tec
    d = _dados(html)
    # o mapa do vídeo wall: o radar pelo Nexus, o que dizer de cada usina no zoom e o clima (avisos) para a vez da Chuva
    assert d["radar"]["lista"] == "/t/campo/equipe/radar.json" and d["radar"]["bloco"] == "/t/campo/equipe/radar/"
    assert any("Naira Teste na usina" in x for x in d["tv_usinas"]["7"])


def test_a_visao_dos_tecnicos():
    """A 2ª visão da coluna da direita (27/11/2026, Levi: "Visão técnico, visão ocorrências, do lado direito [...] para a
    gente ter essas duas opções"): cada técnico do Nexus Field por situação, com onde está (a usina e desde quando, o
    destino e a chegada prevista, a cidade) e a ocorrência aberta da usina dele, se houver."""
    linhas = [{"pid": 1, "nome": "Ana Teste", "equipe": "Centro", "hora": "14:57", "onde": "", "perto": "", "desde": "",
               "s": {"chave": "na_usina", "usina_perto": (7, 0.3), "rotulo": "Na usina", "tom": "ok"}},
              {"pid": 2, "nome": "Bia Teste", "equipe": "Leste", "hora": "14:56", "onde": "", "perto": "", "desde": "",
               "s": {"chave": "deslocamento", "usina_perto": None, "rotulo": "Em deslocamento", "tom": "info"}},
              {"pid": 3, "nome": "Caio Teste", "equipe": "", "hora": "14:49", "onde": "Tanabi/SP",
               "perto": "a 4,2 km da Colorado 2", "desde": "",
               "s": {"chave": "fora_usina", "usina_perto": (12, 4.2), "rotulo": "Parado fora de usina", "tom": "neutro"}},
              {"pid": 4, "nome": "Duda Teste", "equipe": "Centro", "hora": "13:10", "onde": "", "perto": "a 0,3 km da Tanabi",
               "desde": "", "s": {"chave": "sem_sinal", "usina_perto": (8, 0.3), "rotulo": "Sem sinal há 1 h 50", "tom": "alerta"}}]
    v = PA.visao_tecnicos(linhas, EVENTOS, {"7": "Usina parada", "8": "Inversores desligados"}, NOMES.get)
    assert [g["id"] for g in v] == ["na_usina", "deslocamento", "fora_usina", "sem_sinal"]
    na, desl, fora, sinal = (g["itens"][0] for g in v)
    assert (na["nome"], na["texto"], na["uid"], na["oc"], na["pid"]) == ("Ana Teste", "na Alto Paraná 1 desde 14:45", "7", "Usina parada", 1)
    assert (desl["texto"], desl["uid"], desl["oc"]) == ("para Tanabi, chega 15:40", "8", "Inversores desligados")
    assert (fora["texto"], fora["uid"], fora["oc"]) == ("Tanabi/SP · a 4,2 km da Colorado 2", "", "")
    assert (sinal["texto"], sinal["rotulo"], sinal["tom"]) == ("última posição 13:10 · a 0,3 km da Tanabi", "Sem sinal há 1 h 50", "alerta")
    assert v[0]["titulo"] == "Na usina" and v[1]["titulo"] == "Em deslocamento"
