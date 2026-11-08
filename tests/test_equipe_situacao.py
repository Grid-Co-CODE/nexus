"""A situação de cada técnico no Mapa de equipe (08/11/2026; `nexus/campo/equipe/situacao.py`).

As decisões do Levi (08/11/2026): "na usina" é parado a até 1 km da usina; "sem sinal" a partir de 30 min sem ponto; as
cores (deslocamento = info, na usina = ok, fora de usina = neutro, sem sinal = alerta, sem permissão = crítico); "parado
fora de usina" nunca vai ao mapa nem tem rota (o painel diz o estado e a distância até a usina mais perto); o Abrir rota
é o link do Google Maps montado no servidor. Ponto com mais de 7 dias nunca é usado nem mostrado.

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
    # parado a 5 km: fora de usina, com o estado e sem o ponto (nem no mapa, nem na rota)
    s = SI.situacao(_estado(_ponto(*FORA)), USINAS, AGORA)
    assert (s["chave"], s["tom"], s["no_mapa"], s["rota"]) == ("fora_usina", "neutro", False, False)
    assert s["uf"] == "GO" and s["rotulo"] == "Parado fora de usina"
    assert s["usina_perto"][0] == "7" and SI.km_texto(s["usina_perto"][1]) == "5,0 km"
    assert not {"lat", "lon"} & set(s) and not any(d in repr(s) for d in DIGITOS)
    # o último ponto há 31 min: sem sinal
    s = SI.situacao(_estado(_ponto(*NA_USINA, minutos=31)), USINAS, AGORA)
    assert (s["chave"], s["tom"], s["idade_min"], s["rotulo"]) == ("sem_sinal", "alerta", 31, "Sem sinal há 31 min")
    # o técnico negou a localização "o tempo todo"
    s = SI.situacao(_estado(None, permissao="sem", desde=AGORA - timedelta(hours=2)), USINAS, AGORA)
    assert (s["chave"], s["tom"], s["no_mapa"], s["rota"]) == ("sem_permissao", "critico", False, False)
    assert s["rotulo"] == "Sem permissão de localização" and s["desde"] == AGORA - timedelta(hours=2)
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
    """O ponto que ficou velho não muda de natureza: na usina ou andando, ele vai ao mapa (no âmbar) e a rota sai dele;
    parado fora de usina, segue fora do mapa e sem rota, para o mapa não mostrar a casa nem o hotel."""
    s = SI.situacao(_estado(_ponto(*NA_USINA, minutos=40)), USINAS, AGORA)
    assert (s["chave"], s["base"], s["no_mapa"], s["rota"]) == ("sem_sinal", "na_usina", True, True)
    s = SI.situacao(_estado(_ponto(*NA_ESTRADA, minutos=40, mov=True)), USINAS, AGORA)
    assert (s["chave"], s["base"], s["no_mapa"], s["rota"]) == ("sem_sinal", "deslocamento", True, True)
    s = SI.situacao(_estado(_ponto(*FORA, minutos=40)), USINAS, AGORA)
    assert (s["chave"], s["base"], s["no_mapa"], s["rota"]) == ("sem_sinal", "fora_usina", False, False)
    assert s["uf"] == "GO"


def test_sem_permissao_nunca_tem_rota_e_so_vai_ao_mapa_do_ponto_de_usina_ou_estrada():
    for ponto, no_mapa in ((_ponto(*NA_USINA), True), (_ponto(*NA_ESTRADA, mov=True), True), (_ponto(*FORA), False)):
        s = SI.situacao(_estado(ponto, permissao="sem", desde=AGORA), USINAS, AGORA)
        assert (s["chave"], s["no_mapa"], s["rota"]) == ("sem_permissao", no_mapa, False), ponto


def test_o_ponto_de_ontem_e_sem_posicao_hoje():
    """A coleta para às 22h e volta na 1ª abertura do App: o ponto de ontem não diz onde o técnico está hoje. A hora
    dele (dentro dos 7 dias) aparece; a usina e o mapa, não."""
    ontem = _ponto(*NA_USINA, minutos=14 * 60)                       # 22:00 de ontem em Brasília
    s = SI.situacao(_estado(ontem), USINAS, AGORA)
    assert (s["chave"], s["no_mapa"], s["rota"], s["usina_perto"]) == ("sem_posicao", False, False, None)
    assert s["ultima"] == AGORA - timedelta(hours=14)


def test_sem_as_usinas_ninguem_esta_na_usina_e_o_parado_fica_fora_do_mapa():
    s = SI.situacao(_estado(_ponto(*NA_USINA)), {}, AGORA)
    assert (s["chave"], s["no_mapa"], s["usina_perto"]) == ("fora_usina", False, None)
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
    assert SI.url_da_rota((-16.605173, -49.187654), (-17.334571, -48.712389)) == (
        "https://www.google.com/maps/dir/?api=1&origin=-16.605173,-49.187654&destination=-17.334571,-48.712389"
        "&travelmode=driving")
    with pytest.raises(ValueError):
        SI.url_da_rota((float("nan"), -49.0), (-17.0, -48.0))


def test_a_distancia_e_o_tempo_em_texto():
    assert SI.km_texto(0.7975) == "0,8 km" and SI.km_texto(9.96) == "10 km" and SI.km_texto(23.4) == "23 km"
    assert SI.tempo_texto(31) == "31 min" and SI.tempo_texto(60) == "1 h 00" and SI.tempo_texto(125) == "2 h 05"
    assert SI.texto_perto(haversine_km(*NA_USINA, *USINAS["7"][:2]), "UFV Teste") == "a 0,8 km da UFV Teste"


def test_o_desenho_so_tem_x_e_y():
    d = SI.desenho(USINAS, [(1, *NA_USINA, "ok"), (2, *NA_ESTRADA, "info"), (3, *NA_USINA, "critico")])
    assert d["viewbox"].startswith("0 0 1000 ") and {f["sigla"] for f in d["ufs"]} >= {"GO"}
    assert [u["usina_id"] for u in d["usinas"]] == ["7", "8"]
    assert [p["pessoa_id"] for p in d["pontos"]] == [2, 1, 3]            # o crítico por último, desenhado por cima
    assert all(set(p) == {"pessoa_id", "x", "y", "tom"} for p in d["pontos"])
    assert not any(dg in repr(d) for dg in DIGITOS)
    assert SI.desenho({}, [])["viewbox"] is None
