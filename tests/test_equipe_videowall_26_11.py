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


def test_a_linha_do_tempo_de_hoje_das_ocorrencias():
    lt = PA.linha_do_tempo(COS, ["7", "8", "9", "12"], NOMES.get, lambda u: {}, EVENTOS, AGORA)
    assert [(e["hora"], e["uid"], e["tag"], e["texto"]) for e in lt] == [
        ("14:45", "7", "Técnico na usina", "Ana Teste chegou na usina"),
        ("14:30", "7", "Atualizada", "Técnico a caminho"),
        ("14:19", "8", "Técnico a caminho", "Bia Teste a caminho, chegada prevista 15:40"),
        ("13:00", "7", "Nova · OS 18858", "Usina parada: Queda total, trip 27"),
        ("11:00", "7", "Técnico saiu", "Ana Teste saiu da usina"),
        ("09:10", "8", "Atualizada", "Peça pedida"),
        ("07:00", "7", "Técnico na usina", "Ana Teste chegou na usina")]
    # a abertura e a nota de ontem não são de hoje; o técnico da usina 12 (sem ocorrência aberta) não entra
    assert all(e["uid"] != "9" and e["uid"] != "12" for e in lt)
    assert lt[0]["usina"] == "Alto Paraná 1" and lt[3]["codigo"] == "APR100" and lt[3]["tom"] == "critico"
    assert {e["fonte"] for e in lt} == {"Ronda COS", "Nexus Field"}
    # sem a leitura do COS, nada (nem o técnico: sem saber qual usina tem ocorrência)
    assert PA.linha_do_tempo(None, ["7"], NOMES.get, lambda u: {}, EVENTOS, AGORA) == []


def test_a_contagem_do_mapa():
    agora = {"7": {"tom": "critico"}, "8": {"tom": "alerta"}, "9": {"tom": "semcom"}, "12": {"tom": "ok"},
             "13": {"tom": "ok"}, "14": {"tom": "neutro"}}
    # as palavras do Agora de Comando > Usinas (a mesma régua de cor): crítico, atenção, sem comunicação, normal
    assert PA.contagem(agora) == [{"id": "critico", "n": 1, "rotulo": "críticas"}, {"id": "alerta", "n": 1, "rotulo": "em atenção"},
                                  {"id": "semcom", "n": 1, "rotulo": "sem comunicação"}, {"id": "ok", "n": 2, "rotulo": "normais"}]


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
    # a legenda acima do mapa ("explicasse, ó, crítico engloba isso, a atenção engloba isso..."), pela régua do Comando
    leg = html.split('class="eqtv-legenda"', 1)[1].split("</dl>", 1)[0]
    for termo in ("Crítico", "Atenção", "Sem comunicação", "Normal", "Sem leitura", "religamento em campo", "Inversor",
                  "Falha de comunicação", "Nenhuma ocorrência aberta"):
        assert termo in leg, termo
    # a linha do tempo não rola sozinha (Levi: "não precisa ficar rolando automático não"): rola na mão
    assert "data-eqtv-rola-tl" not in html
    assert "data-tv-brasil" in mapa and "data-tv-gira" in mapa and "Sair" in mapa
    assert "críticas" in mapa and "normais" in mapa and "Equipes em deslocamento" in mapa
    # à direita, os eventos de hoje das ocorrências: a Naira chegando na Alfa (a usina com ocorrência)
    assert "Eventos de hoje nas ocorrências" in tl and "Naira Teste chegou na usina" in tl and "Técnico na usina" in tl
    d = _dados(html)
    # o mapa do vídeo wall: o radar pelo Nexus, o que dizer de cada usina no zoom e o clima (avisos) para a vez da Chuva
    assert d["radar"]["lista"] == "/t/campo/equipe/radar.json" and d["radar"]["bloco"] == "/t/campo/equipe/radar/"
    assert any("Naira Teste na usina" in x for x in d["tv_usinas"]["7"])
