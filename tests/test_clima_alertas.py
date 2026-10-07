"""Clima e risco: as regras de alerta. Figuras e coordenadas inventadas; hora sempre com fuso."""
import math
import random
from datetime import datetime, timedelta, timezone

import pytest

from nexus.performance.clima import alertas as A
from nexus.performance.clima import geometria
from nexus.performance.clima.fontes import Aviso, Foco

BRT = timezone(timedelta(hours=-3))
UTC = timezone.utc
AGORA = datetime(2026, 10, 6, 15, 0, tzinfo=BRT)

QUADRADO = {"type": "Polygon", "coordinates": [[[-41.0, -5.0], [-39.0, -5.0], [-39.0, -3.0], [-41.0, -3.0], [-41.0, -5.0]]]}
# um L: o canto de cima, à direita, está dentro da caixa mas fora do polígono
ELE = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 3], [3, 3], [3, 10], [0, 10], [0, 0]]]}


def aviso(id=1, geo=QUADRADO, nivel=2, severidade="Perigo", evento="Tempestade", inicio=None, fim=None):
    inicio = inicio or AGORA - timedelta(hours=2)
    fim = fim or AGORA + timedelta(hours=10)
    return Aviso(id, "hoje", evento, severidade, nivel, inicio, fim, geo, geometria.caixa(geo))


# ── risco de fogo ────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("v,classe", [
    (0.0, "mínimo"), (0.14, "mínimo"), (0.15, "baixo"), (0.39, "baixo"), (0.40, "médio"), (0.69, "médio"),
    (0.70, "alto"), (0.95, "alto"), (0.96, "crítico"), (1.0, "crítico"),
    (None, "sem dado"), (float("nan"), "sem dado"),
])
def test_classe_do_risco_de_fogo(v, classe):
    assert A.classe_risco_fogo(v) == classe


def test_as_faixas_do_inpe_sao_as_do_pacote_de_referencia():
    # alto >= 0,7 e crítico > 0,95 (config.ALERTA do gridco_meteo): o 0,95 ainda é alto
    assert A.RISCO_ALTO == 0.7 and A.RISCO_CRITICO == 0.95
    assert A.classe_risco_fogo(0.7) == "alto" and A.classe_risco_fogo(0.95) == "alto"
    assert A.classe_risco_fogo(0.9500001) == "crítico"


def test_risco_com_ruido_de_ponto_flutuante_na_divisa_nao_muda_de_classe():
    assert A.classe_risco_fogo(0.7 - 1e-12) == "alto"          # 0,70 gravado em double pode vir 0,6999999999999
    assert A.classe_risco_fogo(0.4 - 1e-12) == "médio"
    assert A.classe_risco_fogo(0.95 + 1e-12) == "alto"


def test_nivel_do_risco_so_acende_de_alto_para_cima():
    assert [A.nivel_do_risco(c) for c in ("sem dado", "mínimo", "baixo", "médio", "alto", "crítico")] == [0, 0, 0, 0, 2, 3]


# ── aviso do INMET ───────────────────────────────────────────────────────────────────────────────────────────────────

def test_aviso_que_contem_a_usina():
    a = aviso()
    assert A.avisos_que_contem(-4.0, -40.0, [a], AGORA) == [a]
    assert A.avisos_que_contem(-4.0, -42.0, [a], AGORA) == []         # fora, a oeste


def test_a_caixa_nao_basta_o_ponto_dentro_da_caixa_e_fora_do_poligono_nao_conta():
    a = aviso(geo=ELE)
    assert geometria.caixa(ELE) == (0, 0, 10, 10)
    assert A.avisos_que_contem(8, 8, [a], AGORA) == []                # dentro da caixa, no vazio do L
    assert A.avisos_que_contem(1, 9, [a], AGORA) == [a]


def test_aviso_vencido_nao_conta_mas_o_que_ainda_vai_comecar_conta():
    vencido = aviso(1, fim=AGORA - timedelta(minutes=1))
    futuro = aviso(2, inicio=AGORA + timedelta(hours=5), fim=AGORA + timedelta(hours=20))
    sem_fim = aviso(3)
    sem_fim.fim = None
    r = A.avisos_que_contem(-4.0, -40.0, [vencido, futuro, sem_fim], AGORA)
    assert [a.id for a in r] == [3, 2]            # mesmo nível: o que já está valendo vem antes do que ainda vai começar


def test_avisos_do_mais_grave_para_o_menos():
    leve, grave, medio = aviso(1, nivel=1), aviso(2, nivel=3, severidade="Grande Perigo"), aviso(3, nivel=2)
    assert [a.id for a in A.avisos_que_contem(-4.0, -40.0, [leve, grave, medio], AGORA)] == [2, 3, 1]


def test_aviso_em_vigor_e_aviso_que_ainda_vai_comecar():
    assert A.em_vigor(aviso(), AGORA) is True
    assert A.em_vigor(aviso(inicio=AGORA + timedelta(hours=1)), AGORA) is False
    sem_inicio = aviso()
    sem_inicio.inicio = None
    assert A.em_vigor(sem_inicio, AGORA) is True


def test_multipoligono_do_aviso():
    multi = {"type": "MultiPolygon", "coordinates": [QUADRADO["coordinates"], [[[10, 10], [12, 10], [12, 12], [10, 10]]]]}
    a = aviso(geo=multi)
    assert A.avisos_que_contem(-4.0, -40.0, [a], AGORA) == [a]
    assert A.avisos_que_contem(10.5, 11.5, [a], AGORA) == [a]            # lat 10,5, lon 11,5: dentro do triângulo
    assert A.avisos_que_contem(0, 0, [a], AGORA) == []


# ── focos de queimada ────────────────────────────────────────────────────────────────────────────────────────────────

UM_GRAU = 111.195


def foco(lat, lon, sat="GOES-19", hh=18, mm=50):
    return Foco(lat, lon, sat, datetime(2026, 10, 6, hh, mm, tzinfo=UTC))


def test_foco_ate_5_km_conta_e_alem_disso_nao():
    idx = A.IndiceFocos([foco(-10 + 4.9 / UM_GRAU, -40), foco(-10 + 5.1 / UM_GRAU, -40)])
    r = idx.perto(-10, -40)
    assert r["n"] == 1 and r["km"] == pytest.approx(4.9, abs=0.02)


def test_sem_foco_perto_devolve_none():
    assert A.IndiceFocos([foco(-9, -40)]).perto(-10, -40) is None
    assert A.IndiceFocos([]).perto(-10, -40) is None


def test_foco_resumo_quantos_o_mais_perto_satelite_e_hora():
    longe = foco(-10 + 4.0 / UM_GRAU, -40, "NOAA-21", 16, 16)
    perto = foco(-10 + 1.2 / UM_GRAU, -40, "GOES-19", 18, 50)
    meio = foco(-10, -40 + 2.5 / (UM_GRAU * math.cos(math.radians(10))), "MSG-03", 17, 30)
    r = A.IndiceFocos([longe, perto, meio]).perto(-10, -40)
    assert r["n"] == 3
    assert r["km"] == pytest.approx(1.2, abs=0.02) and r["satelite"] == "GOES-19"
    assert r["hora"] == datetime(2026, 10, 6, 18, 50, tzinfo=UTC)
    assert r["ultima"] == datetime(2026, 10, 6, 18, 50, tzinfo=UTC)


def test_ultima_deteccao_pode_ser_de_um_foco_que_nao_e_o_mais_perto():
    perto_antigo = foco(-10 + 1.0 / UM_GRAU, -40, "NOAA-21", 16, 0)
    longe_recente = foco(-10 + 4.0 / UM_GRAU, -40, "GOES-19", 19, 0)
    r = A.IndiceFocos([perto_antigo, longe_recente]).perto(-10, -40)
    assert r["satelite"] == "NOAA-21" and r["hora"].hour == 16 and r["ultima"].hour == 19


def test_foco_na_divisa_da_celula_do_indice_e_achado():
    # a usina e o foco ficam em lados opostos da grade de 0,1 grau do índice, a menos de 5 km um do outro
    usina = (-10.0999, -40.0999)
    f = foco(-10.1001, -40.1001)
    assert A.IndiceFocos([f]).perto(*usina)["n"] == 1


def test_foco_a_5_km_no_paralelo_numa_latitude_alta_tambem_e_achado():
    # a 30 graus de latitude, 5 km de longitude valem 0,0519 grau: mais que 0,045; a busca de vizinhas tem de cobrir
    lat = -30.0
    dlon = 4.9 / (UM_GRAU * math.cos(math.radians(30)))
    assert A.IndiceFocos([foco(lat, -50 + dlon)]).perto(lat, -50)["n"] == 1


def test_a_busca_de_vizinhas_cresce_com_o_raio_e_com_a_latitude():
    # a 60 graus de latitude, 1 grau de longitude vale a metade: 19 km a leste são 0,34 grau, 3 células de 0,1 de distância.
    # Uma busca que não escalasse a longitude pelo cosseno da latitude pararia em 2 células e perderia este foco.
    dlon = 19 / (UM_GRAU * 0.5)
    assert A.IndiceFocos([foco(-60.0, -40.0 + dlon)]).perto(-60.0, -40.0, raio_km=20)["n"] == 1


def test_indice_de_focos_confere_com_a_conta_por_forca_bruta():
    r = random.Random(61006)
    focos = [foco(r.uniform(-12, -8), r.uniform(-44, -40), hh=r.randrange(16, 20), mm=r.randrange(60)) for _ in range(3000)]
    idx = A.IndiceFocos(focos)
    for _ in range(40):
        lat, lon = r.uniform(-12, -8), r.uniform(-44, -40)
        dentro = [(geometria.distancia_km(lat, lon, f.lat, f.lon), f) for f in focos]
        dentro = [(d, f) for d, f in dentro if d <= 5.0]
        got = idx.perto(lat, lon)
        if not dentro:
            assert got is None
        else:
            assert got["n"] == len(dentro) and got["km"] == pytest.approx(min(d for d, _ in dentro), abs=1e-6)
            assert got["ultima"] == max(f.data for _, f in dentro)


def test_raio_se_escolhe():
    idx = A.IndiceFocos([foco(-10 + 8.0 / UM_GRAU, -40)])
    assert idx.perto(-10, -40) is None
    assert idx.perto(-10, -40, raio_km=10)["n"] == 1


# ── os três níveis da usina (07/10/2026) ─────────────────────────────────────────────────────────────────────────────

SEIS = ["Tempestade", "Chuvas Intensas", "Acumulado de Chuva", "Vendaval", "Ventos Costeiros", "Granizo"]


def test_os_eventos_que_estragam_usina_sao_os_seis_combinados_com_o_levi():
    assert A.EVENTOS_QUE_ESTRAGAM_USINA == frozenset(
        {"tempestade", "chuvas intensas", "acumulado de chuva", "vendaval", "ventos costeiros", "granizo"})


@pytest.mark.parametrize("evento", SEIS + ["TEMPESTADE", "  chuvas   intensas ", "ventos COSTEIROS", "Acúmulado de Chuvá"])
def test_evento_que_estraga_usina_compara_sem_acento_sem_caixa_e_sem_espaco_sobrando(evento):
    assert A.evento_estraga_usina(evento) is True


@pytest.mark.parametrize("evento", ["Baixa Umidade", "Onda de Calor", "Onda de Frio", "Geada", "Nevoeiro", "Ressaca", "",
                                    None, "Tempestade Solar", "Chuva", "Vento"])
def test_evento_desconhecido_ou_que_nao_estraga_usina_nao_conta(evento):
    assert A.evento_estraga_usina(evento) is False


@pytest.mark.parametrize("evento", SEIS + ["Baixa Umidade", "Onda de Calor", "", "Evento Novo"])
def test_grande_perigo_manda_agir_de_qualquer_evento(evento):
    assert A.aviso_manda_agir(aviso(nivel=3, severidade="Grande Perigo", evento=evento)) is True


@pytest.mark.parametrize("evento", SEIS)
def test_perigo_dos_eventos_que_estragam_usina_manda_agir(evento):
    assert A.aviso_manda_agir(aviso(nivel=2, evento=evento)) is True


@pytest.mark.parametrize("evento", ["Baixa Umidade", "Onda de Calor", "Geada", "Evento Novo", ""])
def test_perigo_de_evento_desconhecido_nao_manda_agir_vai_para_atencao(evento):
    assert A.aviso_manda_agir(aviso(nivel=2, evento=evento)) is False


@pytest.mark.parametrize("evento", SEIS + ["Baixa Umidade"])
def test_perigo_potencial_nunca_manda_agir_nem_de_tempestade(evento):
    assert A.aviso_manda_agir(aviso(nivel=1, severidade="Perigo Potencial", evento=evento)) is False


def test_foco_manda_agir_sozinho():
    assert A.nivel_da_usina([], True, False) == "agir"
    assert A.nivel_da_usina([], True, True) == "agir"


def test_aviso_que_manda_agir_basta_e_vale_o_futuro():
    assert A.nivel_da_usina([aviso(nivel=2, evento="Granizo")], False, False) == "agir"
    futuro = aviso(nivel=3, severidade="Grande Perigo", evento="Onda de Calor", inicio=AGORA + timedelta(days=2))
    assert A.nivel_da_usina([futuro], False, False) == "agir"


def test_outro_aviso_ou_risco_alto_e_atencao():
    potencial = aviso(nivel=1, severidade="Perigo Potencial", evento="Tempestade")
    assert A.nivel_da_usina([potencial], False, False) == "atencao"
    assert A.nivel_da_usina([aviso(nivel=2, evento="Onda de Calor")], False, False) == "atencao"
    assert A.nivel_da_usina([], False, True) == "atencao"
    assert A.nivel_da_usina([potencial], False, True) == "atencao"


def test_agir_vence_atencao_quando_os_dois_aparecem():
    leve = aviso(nivel=1, severidade="Perigo Potencial", evento="Baixa Umidade")
    assert A.nivel_da_usina([leve, aviso(nivel=2, evento="Vendaval")], False, True) == "agir"
    assert A.nivel_da_usina([leve], True, True) == "agir"


def test_sem_nada_e_sem_alerta():
    assert A.nivel_da_usina([], False, False) == "sem"


def test_rotulos_dos_niveis():
    assert A.ROTULO_NIVEL == {"agir": "Agir agora", "atencao": "Atenção", "sem": "Sem alerta"}
