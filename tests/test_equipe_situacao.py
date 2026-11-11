"""A situação de cada técnico no Mapa de equipe (08/11/2026; `nexus/campo/equipe/situacao.py`).

As decisões do Levi (08/11/2026): "na usina" é parado a até 1 km da usina; "sem sinal" a partir de 30 min sem ponto; as
cores (deslocamento = info, na usina = ok, fora de usina = neutro, sem sinal = alerta, sem permissão = crítico); o Abrir
rota é o link do Google Maps montado no servidor. Ponto com mais de 7 dias nunca é usado nem mostrado.

10/11/2026 (Levi, pela sessão Nexus Field: "se tem dados de localização tem que estar mostrando no nexus"): o mapa mostra a
última posição de cada técnico no lugar exato em TODAS as situações, também o parado fora de usina e o ponto de outro dia
(este marcado `velho`); a decisão de 08/11 ("o mapa não mostra onde o técnico mora") foi trocada por ele. O percurso de um
período sai desenhado no servidor (`desenho_percurso`), só com x/y.

Coordenadas inventadas, com casas incomuns: se alguma aparecer num texto, o teste acha. Nada vai à rede."""
from datetime import datetime, timedelta, timezone

import pytest

from nexus.campo.equipe import situacao as SI
from nexus.campo.equipe.deslocamentos import haversine_km

AGORA = datetime(2026, 11, 8, 15, 0, tzinfo=timezone.utc)          # 12:00 em Brasília
# duas usinas em Goiás, longe das divisas (o estado sai do contorno do IBGE, não da usina)
USINAS = {"7": (-16.612345, -49.187654, "GO"), "8": (-17.334571, -48.712389, "GO")}
NA_USINA = (-16.605173, -49.187654)          # 0,8 km ao norte da usina 7
FORA = (-16.567381, -49.187643)              # 5 km ao norte da usina 7
NA_ESTRADA = (-16.981237, -48.954321)        # entre as duas usinas
DIGITOS = ("612345", "187654", "334571", "712389", "605173", "567381", "187643", "981237", "954321")


def _ponto(lat, lon, minutos=2, dias=0, mov=False):
    inst = AGORA - timedelta(minutes=minutos, days=dias)
    return {"ponto_id": "P0", "instante": inst.strftime("%Y-%m-%dT%H:%M:%SZ"), "pessoa_id": 1, "lat": lat, "lon": lon,
            "prec_m": 8.0, "vel_ms": 1.4 if mov else 0.0, "mov": mov}


def _estado(ponto=None, permissao="ok", desde=None):
    return {"ultimo": ponto, "permissao": permissao, "desde": desde}


def test_a_situacao_de_cada_tecnico():
    # em deslocamento: o último ponto andando, há 2 min
    s = SI.situacao(_estado(_ponto(*NA_ESTRADA, mov=True)), USINAS, AGORA)
    assert (s["chave"], s["tom"], s["no_mapa"], s["rota"]) == ("deslocamento", "info", True, True)
    assert s["rotulo"] == "Em deslocamento" and s["idade_min"] == 2
    # parado a 0,8 km de uma usina: na usina, com a distância até ela
    s = SI.situacao(_estado(_ponto(*NA_USINA)), USINAS, AGORA)
    assert (s["chave"], s["tom"], s["no_mapa"], s["rota"]) == ("na_usina", "ok", True, True)
    uid, km = s["usina_perto"]
    assert uid == "7" and SI.texto_perto(km, "Usina Alfa Teste") == "a 0,8 km da Usina Alfa Teste"
    # parado a 5 km: fora de usina, com o estado; desde 10/11/2026 no mapa e com rota, como os outros
    s = SI.situacao(_estado(_ponto(*FORA)), USINAS, AGORA)
    assert (s["chave"], s["tom"], s["no_mapa"], s["rota"], s["velho"]) == ("fora_usina", "neutro", True, True, False)
    assert s["uf"] == "GO" and s["rotulo"] == "Parado fora de usina"
    assert s["usina_perto"][0] == "7" and SI.km_texto(s["usina_perto"][1]) == "5,0 km"
    assert not {"lat", "lon"} & set(s) and not any(d in repr(s) for d in DIGITOS)
    # o último ponto há 31 min: sem sinal
    s = SI.situacao(_estado(_ponto(*NA_USINA, minutos=31)), USINAS, AGORA)
    assert (s["chave"], s["tom"], s["idade_min"], s["rotulo"]) == ("sem_sinal", "alerta", 31, "Sem sinal há 31 min")
    # o técnico negou a localização "o tempo todo"
    s = SI.situacao(_estado(None, permissao="sem", desde=AGORA - timedelta(hours=2)), USINAS, AGORA)
    assert (s["chave"], s["tom"], s["no_mapa"], s["rota"]) == ("sem_permissao", "critico", False, False)
    assert s["rotulo"] == "Sem permissão no celular" and s["desde"] == AGORA - timedelta(hours=2)
    # ponto de 8 dias: sem posição, e nem a hora nem a usina dele aparecem
    s = SI.situacao(_estado(_ponto(*NA_USINA, dias=8)), USINAS, AGORA)
    assert (s["chave"], s["no_mapa"], s["rota"]) == ("sem_posicao", False, False)
    assert s["ultima"] is None and s["usina_perto"] is None and s["idade_min"] is None
    assert s["rotulo"] == "Sem posição hoje"


def test_sem_sinal_a_partir_de_30_min():
    """"Sem sinal" a partir de 30 minutos (decisão do Levi): 29 min ainda é a situação do ponto, 30 já é sem sinal."""
    assert SI.situacao(_estado(_ponto(*NA_USINA, minutos=29)), USINAS, AGORA)["chave"] == "na_usina"
    assert SI.situacao(_estado(_ponto(*NA_USINA, minutos=30)), USINAS, AGORA)["chave"] == "sem_sinal"
    s = SI.situacao(_estado(_ponto(*NA_USINA, minutos=125)), USINAS, AGORA)
    assert s["rotulo"] == "Sem sinal há 2 h 05"


def test_sem_sinal_guarda_o_que_o_ultimo_ponto_era():
    """O ponto que ficou velho não muda de natureza (a `base`), e vai ao mapa no âmbar com a rota saindo dele, qualquer
    que fosse: desde 10/11/2026 também o parado fora de usina."""
    s = SI.situacao(_estado(_ponto(*NA_USINA, minutos=40)), USINAS, AGORA)
    assert (s["chave"], s["base"], s["no_mapa"], s["rota"]) == ("sem_sinal", "na_usina", True, True)
    s = SI.situacao(_estado(_ponto(*NA_ESTRADA, minutos=40, mov=True)), USINAS, AGORA)
    assert (s["chave"], s["base"], s["no_mapa"], s["rota"]) == ("sem_sinal", "deslocamento", True, True)
    s = SI.situacao(_estado(_ponto(*FORA, minutos=40)), USINAS, AGORA)
    assert (s["chave"], s["base"], s["no_mapa"], s["rota"]) == ("sem_sinal", "fora_usina", True, True)
    assert s["uf"] == "GO"


def test_sem_permissao_nunca_tem_rota_e_o_ultimo_ponto_vai_ao_mapa():
    """Quem negou a localização não tem a posição mandada ao Google (sem rota), mas o último ponto de hoje, de antes da
    negação, aparece no mapa no vermelho (10/11/2026), seja na usina, na estrada ou fora de usina."""
    for ponto in (_ponto(*NA_USINA), _ponto(*NA_ESTRADA, mov=True), _ponto(*FORA)):
        s = SI.situacao(_estado(ponto, permissao="sem", desde=AGORA), USINAS, AGORA)
        assert (s["chave"], s["tom"], s["no_mapa"], s["rota"]) == ("sem_permissao", "critico", True, False), ponto


def test_o_ponto_de_ontem_e_sem_posicao_hoje():
    """A coleta para às 22h e volta na 1ª abertura do App: o ponto de ontem não diz onde o técnico está hoje. A hora
    dele (dentro dos 7 dias) aparece; a usina e o mapa, não."""
    ontem = _ponto(*NA_USINA, minutos=14 * 60)                       # 22:00 de ontem em Brasília
    s = SI.situacao(_estado(ontem), USINAS, AGORA)
    assert (s["chave"], s["rota"], s["usina_perto"]) == ("sem_posicao", False, None)
    assert s["ultima"] == AGORA - timedelta(hours=14)
    # desde 10/11/2026 a última posição de outro dia (dentro dos 7) vai ao mapa, marcada `velho`, sem rota (o ponto de
    # ontem não é de onde o técnico sai hoje): o trajeto de teste de 09/11 chegou ao banco e o mapa não mostrou nada
    assert (s["no_mapa"], s["velho"], s["tom"]) == (True, True, "neutro")


def test_sem_as_usinas_ninguem_esta_na_usina_e_o_parado_vai_ao_mapa_como_fora_de_usina():
    s = SI.situacao(_estado(_ponto(*NA_USINA)), {}, AGORA)
    assert (s["chave"], s["no_mapa"], s["usina_perto"]) == ("fora_usina", True, None)
    assert SI.situacao(_estado(_ponto(*NA_ESTRADA, mov=True)), {}, AGORA)["no_mapa"] is True


@pytest.mark.parametrize("lat, lon, uf", [
    (-15.79, -47.88, "DF"),          # Brasília: dentro do anel de Goiás, mas o anel de Goiás contorna o DF
    (-16.68, -49.25, "GO"),
    (-8.12, -34.89, "PE"),           # Boa Viagem: o contorno "mínimo" do IBGE põe a praia no mar (a 0,4 km)
    (-22.97, -43.18, "RJ"),          # Copacabana: a 3,9 km do contorno
    (-20.0, -30.0, None),            # o meio do oceano: nenhum estado
])
def test_o_estado_pelo_contorno_do_ibge(lat, lon, uf):
    assert SI.uf_do_ponto(lat, lon) == uf


def test_o_ponto_no_poligono_respeita_o_buraco():
    fora = ((0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0))
    buraco = ((4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0), (4.0, 4.0))
    assert SI.no_poligono(2.0, 2.0, (fora, buraco)) is True
    assert SI.no_poligono(5.0, 5.0, (fora, buraco)) is False
    assert SI.no_poligono(11.0, 5.0, (fora, buraco)) is False


def test_a_url_da_rota_e_do_google_maps():
    # 5 casas (~1 m) bastam para a rota; a 6ª é o centímetro, que ao Google não serve (revisão final de 08/11/2026)
    assert SI.url_da_rota((-16.605173, -49.187654), (-17.334571, -48.712389)) == (
        "https://www.google.com/maps/dir/?api=1&origin=-16.60517,-49.18765&destination=-17.33457,-48.71239"
        "&travelmode=driving")
    with pytest.raises(ValueError):
        SI.url_da_rota((float("nan"), -49.0), (-17.0, -48.0))


def test_a_distancia_e_o_tempo_em_texto():
    assert SI.km_texto(0.7975) == "0,8 km" and SI.km_texto(9.96) == "10 km" and SI.km_texto(23.4) == "23 km"
    assert SI.tempo_texto(31) == "31 min" and SI.tempo_texto(60) == "1 h 00" and SI.tempo_texto(125) == "2 h 05"
    assert SI.texto_perto(haversine_km(*NA_USINA, *USINAS["7"][:2]), "UFV Teste") == "a 0,8 km da UFV Teste"
    # o km inteiro do parado fora de usina (que escondia a casa) saiu em 10/11/2026: o ponto está no mapa
    assert SI.texto_perto(4.96, "UFV Teste") == "a 5,0 km da UFV Teste"


def test_o_desenho_so_tem_x_e_y():
    d = SI.desenho(USINAS, [(1, *NA_USINA, "ok", False), (2, *NA_ESTRADA, "info", False),
                            (3, *NA_USINA, "critico", False), (4, *FORA, "neutro", True)])
    assert d["viewbox"].startswith("0 0 1000 ") and {f["sigla"] for f in d["ufs"]} >= {"GO"}
    assert [u["usina_id"] for u in d["usinas"]] == ["7", "8"]
    # o de outro dia primeiro (embaixo), o crítico por último, desenhado por cima
    assert [p["pessoa_id"] for p in d["pontos"]] == [4, 2, 1, 3]
    assert all(set(p) == {"pessoa_id", "x", "y", "tom", "velho"} for p in d["pontos"])
    assert [p["velho"] for p in d["pontos"]] == [True, False, False, False]
    assert not any(dg in repr(d) for dg in DIGITOS)
    assert SI.desenho({}, [])["viewbox"] is None


# ── o percurso (10/11/2026) ──────────────────────────────────────────────────────────────────────────────────────────
def _trilha(*pares, inicio=AGORA - timedelta(hours=2), passo_min=10):
    return [{**_ponto(lat, lon, mov=i % 2 == 0),
             "instante": (inicio + timedelta(minutes=passo_min * i)).strftime("%Y-%m-%dT%H:%M:%SZ")}
            for i, (lat, lon) in enumerate(pares)]


def _municipio(nome, lon0, lat0, lon1, lat1):
    anel = ((lon0, lat0), (lon1, lat0), (lon1, lat1), (lon0, lat1), (lon0, lat0))
    return (nome, ((anel,),), (lon0, lat0, lon1, lat1))


def test_o_percurso_abre_no_mapa_inteiro_e_so_tem_x_e_y():
    """Levi, 10/11/2026: "No deslocamento pode mostrar o mapa inteiro primeiro, e aí a pessoa pode ir dando zoom e
    mostrando as cidades e municípios de forma leve e fluída". O desenho do percurso usa o MESMO recorte do mapa dos
    técnicos (os estados com usina), com a linha na ordem dos pontos e a hora de cada um; o zoom é do navegador (troca o
    viewBox), e o servidor diz o foco (a caixa do percurso), quantos km vale cada unidade e a menor vista. Só x/y."""
    trilha = _trilha(NA_USINA, NA_ESTRADA, FORA)
    d = SI.desenho_percurso(USINAS, trilha)
    assert d["viewbox"] == SI.desenho(USINAS, [])["viewbox"]                     # o mapa inteiro, o mesmo dos técnicos
    assert [u["usina_id"] for u in d["usinas"]] == ["7", "8"] and {f["sigla"] for f in d["ufs"]} >= {"GO"}
    assert [m["hora"] for m in d["marcas"]] == ["10:00", "10:10", "10:20"]       # Brasília, na ordem
    assert [m["mov"] for m in d["marcas"]] == [True, False, True] and [m["n"] for m in d["marcas"]] == [1, 2, 3]
    assert d["linha"] == " ".join(f"{m['x']},{m['y']}" for m in d["marcas"])
    # o foco é a caixa do percurso, em unidades do desenho, dentro do mapa
    x0, y0, x1, y1 = (float(v) for v in d["foco"].split())
    xs, ys = [float(m["x"]) for m in d["marcas"]], [float(m["y"]) for m in d["marcas"]]
    assert (x0, y0, x1, y1) == (min(xs), min(ys), max(xs), max(ys))
    # a escala: os dois pontos a 0,8 km + 4,2 km... a distância no desenho x km por unidade bate com o haversine
    km = d["km"]
    dist = ((xs[0] - xs[2]) ** 2 + (ys[0] - ys[2]) ** 2) ** 0.5 * km
    assert dist == pytest.approx(haversine_km(*NA_USINA, *FORA), rel=0.02)
    assert d["min"] == pytest.approx(SI.VISTA_MIN_KM / km) and d["niveis"] == ",".join(str(int(n)) for n in SI.NIVEIS_KM)
    assert not any(dg in repr(d) for dg in DIGITOS)
    # o percurso de mais de um dia leva o dia na hora
    trilha = _trilha(NA_USINA, NA_ESTRADA, inicio=AGORA - timedelta(days=1, hours=2), passo_min=24 * 60)
    assert [m["hora"] for m in SI.desenho_percurso(USINAS, trilha)["marcas"]] == ["07/11 10:00", "08/11 10:00"]
    assert SI.desenho_percurso(USINAS, [])["viewbox"] is None


def test_os_pontos_e_as_horas_aparecem_por_nivel_de_zoom():
    """No mapa inteiro, um percurso de cidade cabe em poucas unidades: desenhar todos os pontos e todas as horas viraria
    um borrão. Cada ponto e cada hora dizem o NÍVEL de zoom em que aparecem (0 = o mapa inteiro; os níveis são larguras
    da vista em km, `NIVEIS_KM`): o 1º e o último sempre; os do meio, quando a vista aproxima o bastante para caberem
    sem se amontoar. Parado no mesmo lugar, a hora sai escrita só no 1º (as outras ficam na lista do painel)."""
    trilha = _trilha(NA_USINA, NA_USINA, NA_USINA, NA_ESTRADA, FORA)
    d = SI.desenho_percurso(USINAS, trilha)
    m = d["marcas"]
    assert (m[0]["np"], m[0]["nr"], m[-1]["np"], m[-1]["nr"]) == (0, 0, 0, 0)
    assert all(0 <= x["np"] <= len(SI.NIVEIS_KM) for x in m)
    # a ~42 km dos outros, o ponto da estrada aparece cedo (a vista de 1.200 km já o separa)
    assert m[3]["np"] <= 2 and m[3]["nr"] is not None and m[3]["nr"] >= m[3]["np"]
    # os dois repetidos no mesmo lugar: o ponto só no último nível, e a hora nunca escrita no desenho
    assert m[1]["np"] == m[2]["np"] == len(SI.NIVEIS_KM) and m[1]["nr"] is None and m[2]["nr"] is None
    # a hora vai a um lado do trecho (em "em" do texto, que não cresce com o zoom) e diz para que lado cresce
    assert all({"ox", "oy", "ancora"} <= set(x) and x["ancora"] in ("start", "middle", "end") for x in m)


def test_os_municipios_do_fundo_aparecem_com_o_zoom():
    """O contorno dos municípios (a malha do IBGE já no disco) só aparece com a vista perto (o nível das cidades), e o
    nome: o dos municípios por onde o percurso passa primeiro, o dos vizinhos um nível depois. "Passou por" na ordem."""
    municipios = [_municipio("Norte Teste", -49.3, -16.7, -49.0, -16.5),        # tem o NA_USINA e o FORA
                  _municipio("Sul Teste", -49.0, -17.1, -48.8, -16.7),          # tem o NA_ESTRADA
                  _municipio("Vizinho Teste", -49.6, -16.7, -49.3, -16.5)]      # perto, sem ponto do percurso
    d = SI.desenho_percurso(USINAS, _trilha(NA_USINA, NA_ESTRADA, FORA), municipios)
    por = {m["nome"]: m for m in d["municipios"]}
    assert set(por) == {"Norte Teste", "Sul Teste", "Vizinho Teste"} and all(m["d"].startswith("M") for m in por.values())
    assert all(m["nb"] == SI.NIVEL_CIDADES for m in por.values())                 # o contorno de todos no nível das cidades
    assert (por["Norte Teste"]["n"], por["Vizinho Teste"]["n"]) == (SI.NIVEL_CIDADES, SI.NIVEL_CIDADES + 1)
    assert por["Norte Teste"]["rota"] and not por["Vizinho Teste"]["rota"]
    assert all(m["x"] is not None for m in por.values())                         # todo município tem onde escrever o nome
    assert d["cidades"] == ["Norte Teste", "Sul Teste"]


def test_a_distancia_do_percurso():
    trilha = _trilha(NA_USINA, NA_ESTRADA, FORA)
    esperado = haversine_km(*NA_USINA, *NA_ESTRADA) + haversine_km(*NA_ESTRADA, *FORA)
    assert SI.distancia_km(trilha) == pytest.approx(esperado)
    assert SI.distancia_km(trilha[:1]) == 0 and SI.distancia_km([]) == 0
