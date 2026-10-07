"""Mapa de risco: o contorno do IBGE, a projeção e o recorte de cada região (07/10/2026). Puro: sem Flask e sem rede.

O arquivo do IBGE é público e está no repositório (`nexus/static/clima/`): os testes o leem de verdade, porque é ele que
precisa estar certo. Nenhuma coordenada aqui é de usina; os pontos são inventados."""
import json
import math
import re
from collections import Counter

import pytest

from nexus.performance.clima import geometria
from nexus.performance.clima import mapa as M


# ── o arquivo do IBGE ────────────────────────────────────────────────────────────────────────────────────────────────

def test_o_arquivo_do_ibge_e_pequeno_e_traz_as_27_ufs():
    assert M.ARQUIVO_UFS.is_file()
    assert M.ARQUIVO_UFS.stat().st_size <= 300_000                  # o limite do pedido: simplificar se passar
    todos = M.estados()
    assert len(todos) == 27 and len({e.sigla for e in todos}) == 27
    assert Counter(e.regiao for e in todos) == {"norte": 7, "nordeste": 9, "centro-oeste": 4, "sudeste": 4, "sul": 3}


@pytest.mark.parametrize("codigo,sigla,regiao", [
    ("11", "RO", "norte"), ("13", "AM", "norte"), ("17", "TO", "norte"), ("22", "PI", "nordeste"),
    ("29", "BA", "nordeste"), ("31", "MG", "sudeste"), ("35", "SP", "sudeste"), ("41", "PR", "sul"),
    ("43", "RS", "sul"), ("50", "MS", "centro-oeste"), ("52", "GO", "centro-oeste"), ("53", "DF", "centro-oeste"),
])
def test_cada_codigo_do_ibge_vira_a_sigla_e_a_regiao_certas(codigo, sigla, regiao):
    assert M.UFS[codigo][0] == sigla and M.UFS[codigo][2] == regiao


def test_o_contorno_e_so_o_continente_sem_ilhas_oceanicas():
    # `qualidade=minima` não traz Trindade nem Fernando de Noronha. Se o arquivo for trocado por um com ilhas, o recorte do
    # Brasil se alarga uns 15% de oceano: este teste avisa, e quem trocou decide.
    x0 = min(e.caixa[0] for e in M.estados())
    y0 = min(e.caixa[1] for e in M.estados())
    x1 = max(e.caixa[2] for e in M.estados())
    y1 = max(e.caixa[3] for e in M.estados())
    assert -74.1 <= x0 <= -73.8 and -34.9 <= x1 <= -34.7
    assert -33.9 <= y0 <= -33.6 and 5.2 <= y1 <= 5.4


def test_todo_anel_do_contorno_esta_fechado_e_dentro_do_brasil():
    for e in M.estados():
        assert e.poligonos, e.sigla
        for poligono in e.poligonos:
            for anel in poligono:
                assert len(anel) >= 4 and anel[0] == anel[-1], e.sigla
                assert all(-75 <= lon <= -28 and -35 <= lat <= 6 for lon, lat in anel), e.sigla


def test_a_caixa_de_cada_estado_e_a_dos_seus_pontos():
    for e in M.estados():
        pontos = [p for poligono in e.poligonos for anel in poligono for p in anel]
        assert e.caixa == (min(p[0] for p in pontos), min(p[1] for p in pontos),
                           max(p[0] for p in pontos), max(p[1] for p in pontos))


def test_o_rotulo_de_cada_estado_cai_dentro_do_proprio_estado():
    for e in M.estados():
        lon, lat = e.centro
        achou = any(geometria.contem({"type": "Polygon", "coordinates": [list(a) for a in poligono]}, lon, lat)
                    for poligono in e.poligonos)
        assert achou, e.sigla


def _arquivo(tmp_path, features, nome="ufs.geojson"):
    caminho = tmp_path / nome
    caminho.write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    return caminho


def _feature(codigo, anel=((-50, -10), (-49, -10), (-49, -9), (-50, -10)), tipo="Polygon"):
    coords = [[list(p) for p in anel]]
    return {"type": "Feature", "properties": {"codarea": codigo},
            "geometry": {"type": tipo, "coordinates": coords if tipo == "Polygon" else [coords]}}


def test_arquivo_com_codigo_que_nao_e_de_uf_falha_alto(tmp_path):
    todos = [_feature(c) for c in M.UFS]
    todos[3] = _feature("99")
    with pytest.raises(ValueError, match="99"):
        M.estados(_arquivo(tmp_path, todos))


def test_arquivo_sem_alguma_uf_falha_alto_e_diz_qual(tmp_path):
    with pytest.raises(ValueError, match="RS"):
        M.estados(_arquivo(tmp_path, [_feature(c) for c in M.UFS if c != "43"]))


def test_arquivo_fora_do_formato_falha_alto(tmp_path):
    (tmp_path / "ruim.geojson").write_text("não é json", encoding="utf-8")
    with pytest.raises(ValueError):
        M.estados(tmp_path / "ruim.geojson")
    with pytest.raises(ValueError):
        M.estados(_arquivo(tmp_path, [{"type": "Feature", "properties": {}, "geometry": None}], "sem_codigo.geojson"))
    ponto = _feature("11")
    ponto["geometry"] = {"type": "Point", "coordinates": [0, 0]}
    with pytest.raises(ValueError):
        M.estados(_arquivo(tmp_path, [ponto] + [_feature(c) for c in M.UFS if c != "11"], "ponto.geojson"))


def test_anel_com_menos_de_4_pontos_falha_alto(tmp_path):
    curto = _feature("11", anel=((-50, -10), (-49, -10), (-50, -10)))
    with pytest.raises(ValueError, match="menos de 4"):
        M.estados(_arquivo(tmp_path, [curto] + [_feature(c) for c in M.UFS if c != "11"], "curto.geojson"))


def test_o_rotulo_fica_no_centroide_e_nao_no_meio_da_caixa(tmp_path):
    triangulo = ((0, 0), (6, 0), (0, 3), (0, 0))                          # o centroide é (2, 1); o meio da caixa, (3, 1,5)
    todos = [_feature("11", triangulo)] + [_feature(c) for c in M.UFS if c != "11"]
    ro = next(e for e in M.estados(_arquivo(tmp_path, todos, "triangulo.geojson")) if e.sigla == "RO")
    assert ro.centro == pytest.approx((2.0, 1.0))


def test_anel_sem_area_nao_divide_por_zero_e_o_rotulo_vai_para_o_meio_da_caixa(tmp_path):
    reto = ((0, 0), (4, 2), (2, 1), (0, 0))                               # três pontos na mesma reta: área zero
    todos = [_feature("11", reto)] + [_feature(c) for c in M.UFS if c != "11"]
    ro = next(e for e in M.estados(_arquivo(tmp_path, todos, "reto.geojson")) if e.sigla == "RO")
    assert ro.centro == pytest.approx((2.0, 1.0))


def test_multipolygon_e_aceito_e_o_rotulo_usa_o_maior_pedaco(tmp_path):
    grande = ((-50, -10), (-40, -10), (-40, 0), (-50, 0), (-50, -10))
    ilha = ((-30, -10), (-29, -10), (-29, -9), (-30, -9), (-30, -10))
    mp = {"type": "Feature", "properties": {"codarea": "11"},
          "geometry": {"type": "MultiPolygon", "coordinates": [[[list(p) for p in ilha]], [[list(p) for p in grande]]]}}
    todos = [mp] + [_feature(c) for c in M.UFS if c != "11"]
    ro = next(e for e in M.estados(_arquivo(tmp_path, todos, "mp.geojson")) if e.sigla == "RO")
    assert len(ro.poligonos) == 2
    assert ro.centro == pytest.approx((-45.0, -5.0))


# ── a projeção ───────────────────────────────────────────────────────────────────────────────────────────────────────

def test_projecao_equiretangular_encolhe_a_longitude_pelo_cosseno_da_latitude_media():
    assert M.projetar(-10.0, -50.0, 0.0) == (-50.0, 10.0)               # no equador, 1 grau de longitude vale 1 de latitude
    x, y = M.projetar(30.0, 10.0, 60.0)                                  # a 60 graus, vale a metade
    assert x == pytest.approx(5.0) and y == -30.0                        # y cresce para baixo, como no SVG


def test_projecao_mantem_a_proporcao_real_entre_longitude_e_latitude_na_latitude_media():
    # Um grau de longitude na latitude média mede cos(lat) de um grau de latitude: confere com o haversine do Nexus.
    lat = -14.0
    km_lon = geometria.distancia_km(lat, -50.0, lat, -49.0)
    km_lat = geometria.distancia_km(lat, -50.0, lat + 1.0, -50.0)
    (x0, _), (x1, _) = M.projetar(lat, -50.0, lat), M.projetar(lat, -49.0, lat)
    assert (x1 - x0) == pytest.approx(km_lon / km_lat, abs=1e-3)


def test_vista_de_uma_caixa_conhecida():
    v = M.vista_de_caixa("x", "X", -5.0, 0.0, 5.0, 10.0, margem=0)       # 10 graus de lado, centrada no equador... em lon -5..5
    assert v.lat_media == 5.0
    assert v.largura == 1000 and v.altura == pytest.approx(1000 / math.cos(math.radians(5.0)))
    assert v.ponto(10.0, -5.0) == pytest.approx((0.0, 0.0))              # o canto de cima, à esquerda
    x, y = v.ponto(0.0, 5.0)                                             # o canto de baixo, à direita
    assert x == pytest.approx(1000.0) and y == pytest.approx(v.altura)


def test_vista_no_equador_tem_a_escala_igual_nos_dois_eixos():
    v = M.vista_de_caixa("x", "X", 0.0, -5.0, 10.0, 5.0, margem=0)
    assert v.lat_media == 0.0 and v.escala == pytest.approx(100.0)
    assert v.viewbox == "0 0 1000 1000"
    assert v.ponto(0.0, 5.0) == pytest.approx((500.0, 500.0))            # o centro
    assert v.ponto(5.0, 0.0) == pytest.approx((0.0, 0.0))
    assert v.ponto(-5.0, 10.0) == pytest.approx((1000.0, 1000.0))


def test_vista_em_latitude_alta_gasta_menos_x_por_grau_de_longitude():
    v = M.vista_de_caixa("x", "X", 0.0, 55.0, 10.0, 65.0, margem=0)      # lat média 60: cos = 0,5
    assert v.escala == pytest.approx(200.0) and v.altura == pytest.approx(2000.0)
    (xa, ya), (xb, yb) = v.ponto(60.0, 3.0), v.ponto(61.0, 4.0)
    assert (xb - xa) == pytest.approx(100.0) and (yb - ya) == pytest.approx(-200.0)   # 1 grau de lon = metade de 1 de lat


def test_a_margem_afasta_a_geografia_da_borda():
    sem = M.vista_de_caixa("x", "X", 0.0, -5.0, 10.0, 5.0, margem=0)
    com = M.vista_de_caixa("x", "X", 0.0, -5.0, 10.0, 5.0, margem=0.1)
    assert com.ponto(5.0, 0.0)[0] > sem.ponto(5.0, 0.0)[0] and com.ponto(5.0, 0.0)[1] > sem.ponto(5.0, 0.0)[1]
    assert com.largura == 1000                                          # a largura do viewBox é sempre a mesma


def test_dentro_e_cruza_dizem_o_que_aparece_no_viewbox():
    v = M.vista_de_caixa("x", "X", 0.0, -5.0, 10.0, 5.0, margem=0)
    assert v.dentro(500, 500) and v.dentro(0, 0) and v.dentro(1000, 1000)
    assert not v.dentro(-1, 500) and not v.dentro(500, 1001)
    assert v.dentro(-10, 500, folga=10)
    assert v.cruza((-3.0, -3.0, 2.0, 3.0)) and not v.cruza((11.0, -3.0, 12.0, 3.0)) and not v.cruza((1.0, 6.0, 2.0, 7.0))


# ── as regiões ───────────────────────────────────────────────────────────────────────────────────────────────────────

def test_as_regioes_sao_as_cinco_do_ibge_e_o_brasil():
    assert list(M.REGIOES) == ["norte", "nordeste", "centro-oeste", "sudeste", "sul"]
    assert M.REGIOES["centro-oeste"] == "Centro-Oeste"
    assert M.vista().id == "brasil" and M.vista().nome == "Brasil"
    assert [M.vista(r).id for r in M.REGIOES] == list(M.REGIOES)


@pytest.mark.parametrize("pedido", [None, "", "  ", "marte", "norte,sul", "brasil", "BRASIL", 7, ["sul"]])
def test_regiao_vazia_ou_desconhecida_cai_no_brasil(pedido):
    assert M.vista(pedido) is M.vista()


def test_regiao_pedida_em_outra_caixa_ou_com_espaco_vale():
    assert M.vista(" SUL ") is M.vista("sul") and M.vista("Centro-Oeste").id == "centro-oeste"


@pytest.mark.parametrize("regiao", ["brasil", "norte", "nordeste", "centro-oeste", "sudeste", "sul"])
def test_todo_ponto_dos_estados_da_regiao_cai_dentro_do_viewbox(regiao):
    v = M.vista(regiao)
    assert re.fullmatch(r"0 0 1000 \d+(\.\d)?", v.viewbox), v.viewbox
    for e in M.estados():
        if regiao != "brasil" and e.regiao != regiao:
            continue
        for poligono in e.poligonos:
            for lon, lat in poligono[0]:
                x, y = v.ponto(lat, lon)
                assert v.dentro(x, y), (regiao, e.sigla)


def test_o_viewbox_de_cada_regiao_tem_o_formato_da_geografia_dela():
    razao = {r: M.vista(r).altura / M.vista(r).largura for r in ("brasil", *M.REGIOES)}
    assert razao["norte"] < 1.0                                          # o Norte é bem mais largo que alto
    assert razao["nordeste"] > 1.0 and razao["sul"] > 1.0                # o Nordeste e o Sul são mais altos que largos
    assert 0.9 < razao["brasil"] < 1.15                                  # o país é quase um quadrado
    assert len({M.vista(r).viewbox for r in ("brasil", *M.REGIOES)}) == 6    # cada recorte refaz o viewBox


def test_a_regiao_usa_a_latitude_media_do_proprio_recorte():
    # O Sul está a ~28 graus: com o cosseno do Brasil inteiro (~14 graus) ele ficaria 10% mais largo do que é.
    assert M.vista("sul").lat_media < M.vista().lat_media < M.vista("norte").lat_media
    assert M.vista().lat_media == pytest.approx(-14.2, abs=0.3)
    assert M.vista("sul").lat_media == pytest.approx(-28.1, abs=0.5)


def test_o_recorte_do_brasil_cobre_o_continente_inteiro():
    v = M.vista()
    assert (v.lon_oeste, v.lon_leste) == pytest.approx((-75.2, -33.6), abs=0.2)      # o continente (-74,0 a -34,8) mais 3% de folga
    assert (v.lat_sul, v.lat_norte) == pytest.approx((-34.9, 6.4), abs=0.2)


# ── o caminho SVG ────────────────────────────────────────────────────────────────────────────────────────────────────

def _ler_caminho(d):
    """Os vértices absolutos de cada subcaminho de um `d` com M, l e z (o único dialeto que o mapa escreve)."""
    saida = []
    for sub in re.findall(r"M[^z]*z", d):
        m = re.match(r"M(-?[\d.]+) (-?[\d.]+)l(.*)z", sub)
        x, y = float(m.group(1)), float(m.group(2))
        pontos = [(x, y)]
        numeros = [float(n) for n in m.group(3).split()]
        assert len(numeros) % 2 == 0
        for i in range(0, len(numeros), 2):
            x, y = x + numeros[i], y + numeros[i + 1]
            pontos.append((round(x, 1), round(y, 1)))
        saida.append(pontos)
    return saida


V10 = M.vista_de_caixa("x", "X", 0.0, -5.0, 10.0, 5.0, margem=0)       # 100 unidades por grau, x = lon * 100, y = (5 - lat) * 100


def test_caminho_escreve_deslocamentos_a_partir_do_primeiro_ponto_e_fecha_o_anel():
    anel = [(0, 5), (2, 5), (2, 3), (0, 3), (0, 5)]
    d = M.caminho([anel], V10)
    assert d.startswith("M0 0l") and d.endswith("z") and d.count("M") == 1
    assert _ler_caminho(d) == [[(0.0, 0.0), (200.0, 0.0), (200.0, 200.0), (0.0, 200.0)]]    # o ponto repetido do fim saiu


def test_caminho_com_buraco_vira_dois_subcaminhos_no_mesmo_d():
    fora = [(0, 5), (8, 5), (8, -3), (0, -3), (0, 5)]
    buraco = [(2, 3), (2, 0), (5, 0), (5, 3), (2, 3)]
    d = M.caminho([fora, buraco], V10)
    assert d.count("M") == 2 and len(_ler_caminho(d)) == 2


def test_caminho_junta_vertices_que_arredondam_para_o_mesmo_ponto():
    # 0,001 de longitude = 0,1 unidade: o vértice colado no anterior some, em vez de pesar a página sem desenhar nada
    anel = [(0, 5), (0.0004, 5), (2, 5), (2, 3), (0, 3), (0, 5)]
    assert _ler_caminho(M.caminho([anel], V10)) == [[(0.0, 0.0), (200.0, 0.0), (200.0, 200.0), (0.0, 200.0)]]


def test_caminho_descarta_o_anel_que_nao_sobra_nada_para_desenhar():
    ponto_so = [(1, 1), (1.0001, 1), (1, 1.0001), (1, 1)]
    assert M.caminho([ponto_so], V10) == ""
    assert M.caminho([], V10) == ""


def test_caminho_descarta_o_anel_que_virou_um_risco_de_dois_pontos():
    risco = [(1, 1), (2, 1), (1.0001, 1.0001), (1, 1)]                    # ida e volta na mesma reta: não tem área
    assert M.caminho([risco], V10) == ""


def test_os_deslocamentos_reconstroem_o_desenho_sem_acumular_erro():
    # 500 vértices de uma circunferência de 3 graus (300 unidades): somar 500 deslocamentos arredondados não pode derivar
    anel = [(5 + 3 * math.cos(t), 3 * math.sin(t)) for t in (i * 2 * math.pi / 500 for i in range(500))]
    anel.append(anel[0])
    esperado = []
    for lon, lat in anel[:-1]:
        x, y = V10.ponto(lat, lon)
        p = (round(x, 1), round(y, 1))
        if not esperado or p != esperado[-1]:
            esperado.append(p)
    if esperado[0] == esperado[-1]:
        esperado.pop()
    lido, = _ler_caminho(M.caminho([anel], V10))
    assert len(lido) == len(esperado) > 100
    assert all(abs(a - c) < 1e-6 and abs(b - d) < 1e-6 for (a, b), (c, d) in zip(lido, esperado))


def test_o_numero_do_svg_tem_no_maximo_uma_casa_e_nunca_menos_zero():
    d = M.caminho([[(0.123456, 4.999), (2.5, 4.999), (2.5, 3.0), (0.123456, 3.0), (0.123456, 4.999)]], V10)
    assert not re.search(r"\d\.\d\d", d) and "-0 " not in d and "-0z" not in d and ".0" not in d


# ── os estados em cada vista ─────────────────────────────────────────────────────────────────────────────────────────

def test_o_brasil_desenha_os_27_estados_e_uma_regiao_so_os_que_aparecem_nela():
    assert len(M.ufs_da_vista(M.vista())) == 27
    sul = {u.sigla for u in M.ufs_da_vista(M.vista("sul"))}
    assert {"RS", "SC", "PR"} <= sul                                     # os dela
    assert not ({"AM", "PA", "RN", "AC", "RR", "CE"} & sul)              # longe do recorte
    norte = {u.sigla for u in M.ufs_da_vista(M.vista("norte"))}
    assert {"AM", "PA", "RO", "AC", "RR", "AP", "TO"} <= norte and "RS" not in norte


def test_cada_estado_vem_com_nome_caminho_e_o_ponto_do_rotulo_dentro_do_viewbox():
    v = M.vista()
    for u in M.ufs_da_vista(v):
        assert u.d.startswith("M") and u.d.endswith("z") and u.nome
        assert u.x is not None and v.dentro(float(u.x), float(u.y)), u.sigla


def test_na_regiao_o_estado_cortado_pelo_recorte_perde_o_rotulo_que_ficou_de_fora():
    v = M.vista("sul")
    mg = next(u for u in M.ufs_da_vista(v) if u.sigla == "MG")           # só a beirada sul de Minas aparece no recorte do Sul
    assert mg.d and mg.x is None and mg.y is None
    sp = next(u for u in M.ufs_da_vista(v) if u.sigla == "SP")           # o centro de São Paulo cabe: a sigla fica
    assert sp.x is not None


def test_o_desenho_do_brasil_e_leve():
    total = sum(len(u.d) for u in M.ufs_da_vista(M.vista()))
    assert total < 50_000, total                                         # ~5.500 vértices em deslocamentos de 0,1 (42 mil; em absoluto, o dobro)


def test_os_estados_de_uma_vista_sao_calculados_uma_vez():
    assert M.ufs_da_vista(M.vista("sul")) is M.ufs_da_vista(M.vista("sul"))
