"""As camadas de calor do Mapa de risco (09/10/2026): o risco de fogo do INPE em quadrados (a leitura da área no GeoTIFF, a média dos
pixels com dado, as classes) e a densidade dos focos (o núcleo quártico), a máscara do Brasil e o desenho em faixas. Sem rede: o COG
é montado no teste (clima_cog.py) e servido pela sessão falsa, como nos outros testes do Clima e risco."""
import math
import re
from datetime import datetime, timezone

import pytest

from nexus.performance.clima import alertas as A
from nexus.performance.clima import calor as C
from nexus.performance.clima import fontes as F
from nexus.performance.clima import leitura as L
from nexus.performance.clima import mapa as M
from nexus.performance.clima.fontes import Foco
from nexus.performance.clima.geotiff import GeoTiff, GeoTiffErro

from clima_cog import SessaoArquivos, montar_cog
from test_tema import SELETOR_CLARO, SELETOR_ESCURO, _rgba, _razao, _tokens

URL = "https://inpe.exemplo.test/risco/RF.PREV.T0.tif"
X0, Y0, D = -50.0, -10.0, 0.01            # 40 x 30 pixels de 0,01 grau: blocos de 8 x 8 pixels (0,08 grau)
UTC = timezone.utc


def grade_conhecida():
    """Blocos com conta fácil: o bloco (0, 0) todo 0,80; o (0, 1) metade 0,20 e metade nodata; o (1, 0) com um único pixel com dado
    (abaixo do mínimo de 1/4); o (1, 1) com um NaN e um valor negativo (não são dado) e o resto 0,50; o resto 0,05."""
    g = [[0.05] * 40 for _ in range(30)]
    for lin in range(8):
        for col in range(8):
            g[lin][col] = 0.80
            g[lin][8 + col] = 0.20 if col < 4 else None
            g[8 + lin][col] = None
            g[8 + lin][8 + col] = 0.50
    g[8][0] = 0.90
    g[8][8] = float("nan")
    g[9][9] = -0.5
    return g


def cog(grade=None, **kw):
    return montar_cog(grade or grade_conhecida(), origem=(X0, Y0), escala=D, **kw)


def sessao(conteudo=None, modificado="Fri, 09 Oct 2026 09:32:00 GMT"):
    return SessaoArquivos({URL: conteudo or cog()}, modificado=modificado)


# ── a leitura da área no GeoTIFF ─────────────────────────────────────────────────────────────────────────────────────

def test_somar_em_blocos_soma_so_o_que_e_dado_e_conta_os_pixels():
    gt = GeoTiff(URL, sessao(), piso=F.PISO_RISCO)
    b = gt.somar_em_blocos((X0, Y0 - 0.30, X0 + 0.40, Y0), 0.08)
    assert (b["ncols"], b["nrows"], b["px_por_bloco"]) == (5, 4, 64)
    assert b["oeste"] == X0 and b["norte"] == Y0 and b["dlon"] == pytest.approx(0.08) and b["dlat"] == pytest.approx(0.08)
    soma, n = b["soma"], b["n"]
    assert n[0] == 64 and soma[0] == pytest.approx(64 * 0.80)                   # todo com dado
    assert n[1] == 32 and soma[1] == pytest.approx(32 * 0.20)                   # metade nodata: não entra na soma nem na conta
    assert n[5] == 1 and soma[5] == pytest.approx(0.90)                         # um pixel só
    assert n[6] == 62 and soma[6] == pytest.approx(62 * 0.50)                   # o NaN e o negativo não são dado
    # a última linha de blocos só tem 6 linhas de pixels (o arquivo tem 30): conta só o que existe
    assert n[15] == 6 * 8 and soma[15] == pytest.approx(48 * 0.05)


def test_valor_acima_de_1_derruba_a_leitura_em_vez_de_acender_o_mapa():
    g = grade_conhecida()
    g[20][20] = 37.0                                                             # escala trocada (0 a 100)
    gt = GeoTiff(URL, sessao(cog(g)), piso=F.PISO_RISCO)
    with pytest.raises(GeoTiffErro, match="acima de 1"):
        gt.somar_em_blocos((X0, Y0 - 0.30, X0 + 0.40, Y0), 0.08, teto=1 + 1e-9)


def test_so_as_tiles_que_o_brasil_precisa_sao_pedidas():
    s = sessao()
    gt = GeoTiff(URL, s, piso=F.PISO_RISCO, janela=512)                          # janela pequena: cada tile vem por Range
    # tiles de 16 pixels: 3 x 2 na grade; só as que encostam na metade oeste da caixa
    b = gt.somar_em_blocos((X0, Y0 - 0.30, X0 + 0.40, Y0), 0.08, precisa=lambda o, s_, l, n: o < X0 + 0.16)
    faixas = [f for _, f in s.pedidos if f and not f.startswith("bytes=0-")]
    assert b["tiles"] == 2 and len(faixas) == 2                                  # as duas tiles da coluna da esquerda
    assert b["n"][0] == 64 and b["n"][3] == 0                                    # o que não foi lido fica sem dado (contagem 0)


def test_a_mesma_leitura_nao_baixa_tile_de_novo_se_o_arquivo_nao_mudou():
    s = sessao()
    caixa = (X0, Y0 - 0.30, X0 + 0.40, Y0)
    primeira = F.inpe_risco_grade(s, URL, caixa)
    assert primeira["conferido"] is False and primeira["validador"] == "Fri, 09 Oct 2026 09:32:00 GMT"
    antes = len(s.pedidos)
    segunda = F.inpe_risco_grade(s, URL, caixa, anterior=primeira)
    assert segunda["conferido"] is True and segunda["grade"] is primeira["grade"]
    assert len(s.pedidos) - antes == 1                                           # só o cabeçalho (64 KB)
    s.modificado = "Sat, 10 Oct 2026 09:32:00 GMT"                               # o INPE publicou de novo
    terceira = F.inpe_risco_grade(s, URL, caixa, anterior=primeira)
    assert terceira["conferido"] is False and terceira["validador"] == "Sat, 10 Oct 2026 09:32:00 GMT"


def test_o_cache_do_mapa_de_calor_le_ao_fundo_e_a_primeira_visita_ouve_lendo(monkeypatch):
    L.limpar_cache()
    tarefas = []
    L.usar_executor(tarefas.append)                                              # a "thread" fica na fila até o teste rodar
    try:
        cfg = {"TESTING": True, "NEXUS_CLIMA_RISCO_URL": "https://inpe.exemplo.test/risco/RF.PREV.T{d}.tif"}
        s = sessao()
        caixa = (X0, Y0 - 0.30, X0 + 0.40, Y0)
        primeira = L.risco_grade(cfg, 0, caixa, sessao=s)
        assert primeira.dados is None and primeira.erro == L.LENDO and len(tarefas) == 1
        assert L.risco_grade(cfg, 0, caixa, sessao=s).erro == L.LENDO and len(tarefas) == 1     # uma busca por vez
        tarefas.pop()()                                                          # a leitura termina
        pronta = L.risco_grade(cfg, 0, caixa, sessao=s)
        assert pronta.dados["grade"]["n"][0] == 64 and pronta.vence_em is not None
    finally:
        L.usar_executor(None)
        L.limpar_cache()


def test_nos_testes_sem_sessao_o_mapa_de_calor_nao_vai_a_rede():
    L.limpar_cache()
    l = L.risco_grade({"TESTING": True}, 0, M.LIMITES_BRASIL)
    assert l.dados is None and l.erro == L.SEM_FONTE_NOS_TESTES


# ── as classes ───────────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("valor,classe", [(0.0, 1), (0.149, 1), (0.15, 2), (0.399, 2), (0.40, 3), (0.6999999999999, 4),
                                          (0.70, 4), (0.95, 4), (0.9500001, 5), (1.0, 5), (None, 0)])
def test_a_classe_do_quadrado_e_a_regua_do_inpe_da_regra_das_usinas(valor, classe):
    assert C.classe_do_risco(valor) == classe


def test_a_faixa_escrita_na_legenda_bate_com_a_regua():
    # o que a legenda escreve e a régua das usinas (alertas.classe_risco_fogo), lado a lado: mudou uma, o teste diz
    assert [(c["classe"], c["faixa"]) for c in C.CLASSES_RISCO] == [
        ("mínimo", "abaixo de 0,15"), ("baixo", "de 0,15 a 0,40"), ("médio", "de 0,40 a 0,70"), ("alto", "de 0,70 a 0,95"),
        ("crítico", "acima de 0,95")]
    for x, classe in [(0.149, "mínimo"), (0.15, "baixo"), (0.399, "baixo"), (0.40, "médio"), (0.699, "médio"), (0.70, "alto"),
                      (0.95, "alto"), (0.951, "crítico")]:
        assert A.classe_risco_fogo(x) == classe


def test_quadrado_com_menos_de_um_quarto_dos_pixels_com_dado_fica_sem_cor():
    soma = [64 * 0.8, 15 * 0.8, 16 * 0.8, 0.0]
    n = [64, 15, 16, 0]
    assert list(C.classes_do_risco(soma, n, 64)) == [4, 0, 4, 0]                 # 15 de 64 é menos de 1/4: sem cor, mesmo com 0,8


def test_juntar_pondera_pelos_pixels_com_dado_e_nao_faz_media_de_media():
    blocos = {"oeste": 0.0, "norte": 0.0, "dlon": 1.0, "dlat": 1.0, "ncols": 2, "nrows": 2,
              "soma": [64 * 1.0, 1 * 0.0, 0.0, 0.0], "n": [64, 1, 0, 0], "px_por_bloco": 64}
    grade, soma, n = C.juntar(blocos, 2)
    assert (grade.ncols, grade.nrows, grade.dlon) == (1, 1, 2.0)
    assert n[0] == 65 and soma[0] / n[0] == pytest.approx(64 / 65)               # não 0,5 (a média das médias)


# ── a densidade dos focos ────────────────────────────────────────────────────────────────────────────────────────────

def _foco(lat, lon):
    return Foco(lat, lon, "GOES-19", datetime(2026, 10, 9, 17, 50, tzinfo=UTC))


def test_um_foco_no_centro_do_quadrado_da_o_pico_do_nucleo_e_zero_fora_do_raio():
    g = C.Grade(-46.0, -10.0, 0.04, 0.04, 61, 61)
    lat, lon = g.lat(30), g.lon(30)
    v = C.densidade([_foco(lat, lon)], g, 25.0)
    pico = 3 / (math.pi * 25.0 ** 2) * 1000
    assert v[30 * 61 + 30] == pytest.approx(pico)
    for r in range(61):
        for c in range(61):
            dy = (g.lat(r) - lat) * C.KM_POR_GRAU
            dx = (g.lon(c) - lon) * C.KM_POR_GRAU * math.cos(math.radians(lat))
            d = math.hypot(dx, dy)
            if d >= 25.0:
                assert v[r * 61 + c] == 0, (r, c, d)                              # sem foco no raio: zero, e o quadrado fica sem cor
            else:
                assert v[r * 61 + c] == pytest.approx(pico * (1 - (d / 25.0) ** 2) ** 2)


def test_dois_focos_no_mesmo_lugar_dao_o_dobro_e_a_soma_da_grade_e_o_numero_de_focos():
    g = C.Grade(-46.0, -10.0, 0.01, 0.01, 121, 121)
    lat, lon = g.lat(60), g.lon(60)
    um = C.densidade([_foco(lat, lon)], g, 25.0)
    dois = C.densidade([_foco(lat, lon), _foco(lat, lon)], g, 25.0)
    assert dois[60 * 121 + 60] == pytest.approx(2 * um[60 * 121 + 60])
    area = (0.01 * C.KM_POR_GRAU) * (0.01 * C.KM_POR_GRAU * math.cos(math.radians(lat)))
    assert sum(dois) / 1000 * area == pytest.approx(2.0, rel=0.03)                # o núcleo integra 1: cada foco vale 1


@pytest.mark.parametrize("v,classe", [(0, 0), (1e-9, 1), (0.49, 1), (0.5, 2), (1.99, 2), (2.0, 3), (5.0, 4), (19.9, 4), (20.0, 5)])
def test_as_classes_da_densidade(v, classe):
    assert C.classe_da_densidade(v) == classe


# ── a máscara do Brasil e o desenho ──────────────────────────────────────────────────────────────────────────────────

def test_a_mascara_do_brasil_pega_o_continente_e_deixa_o_mar_e_o_vizinho_de_fora():
    aneis = M.aneis_do_brasil()
    g = C.grade_de_caixa(*M.LIMITES_BRASIL, 0.08)
    m0, m1 = C.mascara(g, aneis, 0), C.mascara(g, aneis, 1)

    def em(m, lat, lon):
        r, c = g.celula(lat, lon)
        return m[r * g.ncols + c]
    assert em(m0, -15.79, -47.88) == 1                                           # Brasília
    assert em(m0, -3.10, -60.02) == 1                                            # Manaus
    assert em(m0, -10.0, -35.0) == 0                                             # o Atlântico, ao largo de Alagoas
    assert em(m0, -25.3, -57.6) == 0                                             # Assunção, no Paraguai
    assert sum(m1) > sum(m0)                                                     # a dilatação pega a costa e a fronteira
    # a área do Brasil na grade: ~8,5 milhões de km² (com a célula de 0,08 grau, o erro da borda é pequeno)
    km2 = sum(m0[r * g.ncols + c] * (0.08 * C.KM_POR_GRAU) ** 2 * math.cos(math.radians(g.lat(r)))
              for r in range(g.nrows) for c in range(g.ncols))
    assert 8.2e6 < km2 < 8.8e6


def _corridas(d):
    """O caminho das faixas de volta em [(x0, x1, y)]: M x y h w e m dx 0 h w."""
    saida, x, y = [], 0.0, 0.0
    for m in re.finditer(r"([Mm])(-?[\d.]+) (-?[\d.]+)h(-?[\d.]+)", d):
        cmd, a, b, w = m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4))
        if cmd == "M":
            x, y = a, b
        else:
            x, y = x + a, y + b
        saida.append((round(x, 1), round(x + w, 1), round(y, 1)))
        x += w
    return saida


def test_o_desenho_em_faixas_volta_a_grade_sem_deriva():
    v = M.vista()
    g = C.Grade(-50.0, -10.0, 0.16, 0.16, 20, 6)
    classes = bytearray(20 * 6)
    for r in range(6):
        for c in range(20):
            classes[r * 20 + c] = (c // 4) % 6                                   # corridas de 4 quadrados, com buracos (classe 0)
    f = C.faixas(classes, g, v)
    xs = [round(v.ponto(0.0, g.oeste + c * g.dlon)[0], 1) for c in range(21)]
    ys = [round((v.ponto(g.norte - r * g.dlat, 0.0)[1] + v.ponto(g.norte - (r + 1) * g.dlat, 0.0)[1]) / 2, 1) for r in range(6)]
    assert sorted(f["caminhos"]) == [1, 2, 3, 4]                                 # a classe que não aparece não vira caminho vazio
    for k in range(1, 5):
        esperado = [(xs[c0], xs[c0 + 4], ys[r]) for r in range(6) for c0 in range(0, 20, 4) if (c0 // 4) % 6 == k]
        assert _corridas(f["caminhos"][k]) == esperado, k
    assert float(f["altura"]) == pytest.approx(0.16 * v.escala + C.SOBREPOR, abs=0.01)  # o traço cobre a linha e sobrepõe a vizinha
    assert f["contagem"][1] == 6 * 4 and f["sem_dado"] == 6 * 4                  # a classe 0 é contada como sem dado


def test_sem_dado_nao_vira_cor_e_a_mascara_corta_o_que_nao_e_brasil():
    v = M.vista()
    g = C.Grade(-50.0, -10.0, 0.16, 0.16, 4, 2)
    assert C.faixas(bytearray(8), g, v)["caminhos"] == {}                         # nada com dado: nenhum caminho, nenhuma cor
    desenhar = bytearray([1, 1, 0, 0, 1, 1, 0, 0])
    f = C.faixas(bytearray([3] * 8), g, v, desenhar=desenhar)
    assert len(_corridas(f["caminhos"][3])) == 2 and all(x1 < v.ponto(0, -49.6)[0] for _x0, x1, _y in _corridas(f["caminhos"][3]))


def test_quadrado_fora_do_recorte_nem_e_escrito():
    v = M.vista("sul")
    g = C.Grade(-74.0, 5.3, 1.0, 1.0, 40, 40)                                    # o Brasil inteiro em graus
    f = C.faixas(bytearray([2] * 1600), g, v)
    meia = v.escala / 2                                                          # meia altura de um quadrado de 1 grau, no desenho
    corridas = _corridas(f["caminhos"][2])
    assert corridas and len({y for _x0, _x1, y in corridas}) < 40                # as linhas fora do recorte do Sul não saem
    for x0, x1, y in corridas:
        assert x1 >= -8.0 and x0 <= v.largura + 8.0 and y + meia >= -8.0 and y - meia <= v.altura + 8.0


# ── as rampas de cor ─────────────────────────────────────────────────────────────────────────────────────────────────

def _oklch(rgb):
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(x) for x in rgb[:3])
    l_ = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b) ** (1 / 3)
    m_ = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b) ** (1 / 3)
    s_ = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b) ** (1 / 3)
    L_ = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    a = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    b2 = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L_, math.hypot(a, b2), math.degrees(math.atan2(b2, a)) % 360


@pytest.mark.parametrize("seletor", [SELETOR_ESCURO, SELETOR_CLARO], ids=["escuro", "claro"])
@pytest.mark.parametrize("camada", ["risco", "densidade"])
def test_cada_rampa_de_calor_e_uma_rampa_de_verdade_nos_dois_temas(seletor, camada):
    # O método do skill de dataviz para uma rampa (o validador em --ordinal): um matiz só (até 40 graus), luminosidade que só sobe
    # (ou só desce) e passos de pelo menos 0,06. O primeiro passo pode encostar na terra (é mapa de calor), mas não pode ser a
    # terra: o "sem dado" é a terra sem cor, e tem de dar para ver a diferença.
    t = _tokens(seletor)
    passos = [_rgba(t[f"--calor-{camada}-{i}"]) for i in range(1, 6)]
    L_ = [_oklch(p)[0] for p in passos]
    escuro = seletor == SELETOR_ESCURO
    assert L_ == (sorted(L_) if escuro else sorted(L_, reverse=True)), L_      # no escuro o mais alto brilha; no claro, escurece
    assert all(abs(b - a) >= 0.06 for a, b in zip(L_, L_[1:])), L_
    matizes = [_oklch(p)[2] for p in passos]
    abertura = max(matizes) - min(matizes)
    assert min(abertura, 360 - abertura) <= 40, matizes
    terra = _rgba(t["--mapa-terra"])
    assert _razao(passos[0], terra) >= 1.25
