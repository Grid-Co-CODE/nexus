"""Clima e risco: ponto em polígono e distância, em Python puro (sem shapely). Tudo com figuras inventadas."""
import pytest

from nexus.performance.clima import geometria as G

QUADRADO = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]
BURACO = [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]


def poligono(*aneis):
    return {"type": "Polygon", "coordinates": [list(a) for a in aneis]}


def test_ponto_dentro_e_fora():
    p = poligono(QUADRADO)
    assert G.contem(p, 5, 5)
    assert not G.contem(p, 11, 5)
    assert not G.contem(p, 5, -0.001)


def test_borda_conta_como_dentro():
    # Aviso que encosta na usina vale: perder um alerta custa mais que um alarme a mais. O shapely (`contains`, no pacote
    # de referência) exclui a borda; aqui é de propósito diferente, e este teste prende a escolha.
    p = poligono(QUADRADO)
    assert G.contem(p, 0, 5)          # lado esquerdo
    assert G.contem(p, 5, 10)         # lado de cima
    assert G.contem(p, 0, 0)          # vértice
    assert G.contem(p, 10, 10)


def test_anel_sem_o_ponto_de_fechamento_vale_igual():
    aberto = poligono(QUADRADO[:-1])
    assert G.contem(aberto, 5, 5) and not G.contem(aberto, 12, 5)


def test_buraco_exclui_o_ponto():
    p = poligono(QUADRADO, BURACO)
    assert not G.contem(p, 5, 5)      # dentro do buraco
    assert G.contem(p, 1, 1)          # no corpo
    assert G.contem(p, 4, 5)          # a borda do buraco é borda do polígono
    assert not G.contem(p, 11, 5)


def test_multipoligono_vale_em_qualquer_parte():
    segundo = [[20, 0], [30, 0], [30, 10], [20, 10], [20, 0]]
    m = {"type": "MultiPolygon", "coordinates": [[QUADRADO], [segundo, [[24, 4], [26, 4], [26, 6], [24, 6], [24, 4]]]]}
    assert G.contem(m, 5, 5)
    assert G.contem(m, 21, 5)
    assert not G.contem(m, 15, 5)     # entre as duas partes
    assert not G.contem(m, 25, 5)     # buraco da segunda parte


def test_poligono_concavo():
    ele = [[0, 0], [10, 0], [10, 3], [3, 3], [3, 10], [0, 10], [0, 0]]
    p = poligono(ele)
    assert G.contem(p, 1, 9)          # na haste de cima
    assert G.contem(p, 9, 1)          # na base
    assert not G.contem(p, 8, 8)      # no vazio do L


def test_raio_que_passa_por_vertice_nao_conta_duas_vezes():
    # O raio horizontal por (-1, 5) bate nos vértices (0, 5) e (10, 5) do losango: o caso clássico que erra o par-ímpar.
    losango = poligono([[0, 5], [5, 0], [10, 5], [5, 10], [0, 5]])
    assert G.contem(losango, 2, 5)
    assert not G.contem(losango, -1, 5)
    assert not G.contem(losango, 11, 5)
    assert G.contem(losango, 5, 5)


def test_coordenada_de_gente_de_verdade():
    # lon, lat com muitas casas, como o INMET manda; um retângulo de ~2 graus.
    p = poligono([[-41.572266, -3.951941], [-39.0, -3.951941], [-39.0, -5.5], [-41.572266, -5.5], [-41.572266, -3.951941]])
    assert G.contem(p, -40.03418, -4.127285)
    assert not G.contem(p, -42.0, -4.127285)


def test_geometria_que_nao_e_poligono_nao_contem_nada():
    assert not G.contem({"type": "Point", "coordinates": [1, 1]}, 1, 1)
    assert not G.contem({"type": "Polygon", "coordinates": []}, 1, 1)
    assert not G.contem({}, 1, 1)


def test_caixa_do_poligono_e_do_multipoligono():
    assert G.caixa(poligono(QUADRADO)) == (0, 0, 10, 10)
    m = {"type": "MultiPolygon", "coordinates": [[QUADRADO], [[[20, -5], [30, -5], [30, 2], [20, -5]]]]}
    assert G.caixa(m) == (0, -5, 30, 10)


@pytest.mark.parametrize("ruim", [
    {"type": "Polygon", "coordinates": "x"},
    {"type": "Polygon", "coordinates": [[[0, 0], [1]]]},
    {"type": "Polygon", "coordinates": [[["a", 0], [1, 1], [2, 0], ["a", 0]]]},
    {"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]},          # anel com menos de 3 pontos
    {"type": "Point", "coordinates": [1, 1]},
    {"type": "Polygon"},
    None,
    [],
])
def test_caixa_recusa_geometria_malformada(ruim):
    with pytest.raises(ValueError):
        G.caixa(ruim)


def test_distancia_zero_e_simetrica():
    assert G.distancia_km(-10, -40, -10, -40) == 0
    assert G.distancia_km(-10, -40, -11, -41) == pytest.approx(G.distancia_km(-11, -41, -10, -40))


def test_distancia_de_um_grau_no_equador():
    assert G.distancia_km(0, 0, 0, 1) == pytest.approx(111.19, abs=0.05)
    assert G.distancia_km(0, 0, 1, 0) == pytest.approx(111.19, abs=0.05)


def test_distancia_entre_duas_capitais():
    # São Paulo -> Rio de Janeiro, conferida por OUTRA fórmula (lei esférica dos cossenos), não por um número de memória.
    import math
    f1, f2, dl = math.radians(-23.5505), math.radians(-22.9068), math.radians(-43.1729 + 46.6333)
    esperado = 6371.0 * math.acos(math.sin(f1) * math.sin(f2) + math.cos(f1) * math.cos(f2) * math.cos(dl))
    assert G.distancia_km(-23.5505, -46.6333, -22.9068, -43.1729) == pytest.approx(esperado, abs=0.01)
    assert 355 < esperado < 365


def test_distancia_a_5_km_no_meridiano_e_no_paralelo():
    um_grau_lat = 111.195
    assert G.distancia_km(-10, -40, -10 + 5 / um_grau_lat, -40) == pytest.approx(5.0, abs=0.01)
    # em -10 graus de latitude, 1 grau de longitude vale ~109,5 km (cos 10 = 0,9848)
    assert G.distancia_km(-10, -40, -10, -40 + 5 / (um_grau_lat * 0.98481)) == pytest.approx(5.0, abs=0.02)
