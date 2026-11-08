"""Mapa de equipe: os deslocamentos entre usinas, dos pontos (08/11/2026). Coordenadas e pessoas de mentira."""
from nexus.campo.equipe import CAB_DESLOC, RAIO_USINA_KM
from nexus.campo.equipe.deslocamentos import deslocamentos, haversine_km

# A e B a uns 11 km uma da outra (0,1 grau de latitude), C a 55 km
A, B, C = (-23.00, -46.00, "SP"), (-23.10, -46.00, "SP"), (-23.50, -46.00, "SP")
USINAS = {"1": A, "2": B, "3": C}


def _p(pessoa, hhmm, lat, lon):
    return {"pessoa_id": pessoa, "instante": f"2026-11-08T{hhmm}:00Z", "lat": lat, "lon": lon}


def _d(linha):
    return dict(zip(CAB_DESLOC, linha))


def test_um_deslocamento_e_da_saida_de_uma_usina_a_chegada_na_outra():
    pts = [_p(7, "12:00", -23.001, -46.0),      # em A
           _p(7, "12:10", -23.002, -46.0),      # ainda em A: é a SAÍDA (o último em A)
           _p(7, "12:20", -23.05, -46.0),       # no caminho
           _p(7, "12:30", -23.099, -46.0),      # em B: a CHEGADA (o 1º em B)
           _p(7, "12:40", -23.10, -46.0)]
    linhas = deslocamentos(pts, USINAS)
    assert len(linhas) == 1
    d = _d(linhas[0])
    assert (d["usina_id_saida"], d["usina_id_chegada"], d["pessoa_id"]) == (1, 2, 7)
    assert (d["saida"], d["chegada"]) == ("2026-11-08T12:10:00Z", "2026-11-08T12:30:00Z")
    assert d["duracao_min"] == 20 and d["data_id"] == 20261108
    esperado = (haversine_km(-23.002, -46.0, -23.05, -46.0) + haversine_km(-23.05, -46.0, -23.099, -46.0))
    assert d["distancia_km"] == round(esperado, 1)
    assert d["deslocamento_id"].startswith("D") and len(d["deslocamento_id"]) == 12


def test_voltar_para_a_mesma_usina_nao_e_deslocamento():
    pts = [_p(7, "12:00", -23.0, -46.0), _p(7, "12:10", -23.05, -46.0), _p(7, "12:20", -23.001, -46.0)]
    assert deslocamentos(pts, USINAS) == []


def test_parado_fora_de_usina_nao_conta():
    pts = [_p(7, "12:00", -23.3, -46.0), _p(7, "12:30", -23.31, -46.0), _p(7, "13:00", -23.32, -46.0)]
    assert deslocamentos(pts, USINAS) == []


def test_cada_pessoa_tem_o_seu_rastro_e_o_id_e_estavel():
    pts = [_p(7, "12:00", -23.0, -46.0), _p(8, "12:05", -23.1, -46.0), _p(7, "12:30", -23.1, -46.0),
           _p(8, "12:40", -23.0, -46.0)]
    a = deslocamentos(pts, USINAS)
    achados = sorted((_d(l)["pessoa_id"], _d(l)["usina_id_saida"], _d(l)["usina_id_chegada"]) for l in a)
    assert achados == [(7, 1, 2), (8, 2, 1)]
    assert sorted(l[0] for l in a) == sorted(l[0] for l in deslocamentos(list(reversed(pts)), USINAS))


def test_o_raio_conta_a_partir_da_usina():
    # a 0,5 km de A cabe no raio de 1 km; no raio de 0,3 km já não é "na usina"
    assert RAIO_USINA_KM == 1.0
    pts = [_p(7, "12:00", -23.0045, -46.0), _p(7, "12:30", -23.1, -46.0)]
    assert len(deslocamentos(pts, USINAS)) == 1
    assert deslocamentos(pts, USINAS, raio_km=0.3) == []


def test_atravessar_a_meia_noite_de_brasilia_nao_e_deslocamento():
    # o último ponto em A às 18:50 (21:50Z) e o primeiro em B no dia seguinte às 07:10 (10:10Z): a coleta para às 22h e
    # recomeça na 1ª abertura do App; entre os dois dias não houve trajeto observado
    pts = [{"pessoa_id": 7, "instante": "2026-11-07T21:50:00Z", "lat": -23.0, "lon": -46.0},
           {"pessoa_id": 7, "instante": "2026-11-08T10:10:00Z", "lat": -23.1, "lon": -46.0}]
    assert deslocamentos(pts, USINAS) == []
    # o mesmo trecho dentro de um dia só continua sendo deslocamento
    pts[1]["instante"] = "2026-11-07T22:30:00Z"
    assert len(deslocamentos(pts, USINAS)) == 1
