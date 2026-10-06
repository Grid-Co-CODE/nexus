"""Leitor mínimo do GeoTIFF do INPE (risco de fogo): COG de 64 bits, LZW, em tiles, lido por Range (06/10/2026).

O Pillow 12.2 não abre esse arquivo (BitsPerSample 64 não tem modo no OPEN_INFO). Os testes montam um COG pequeno com o
mesmo desenho (`clima_cog.montar_cog`: contêiner à mão, LZW do Pillow) e provam: a georreferência, só a tile do ponto
sair da rede, o entorno de 5 x 5 e o erro explícito quando o formato muda. Nenhum teste fala com a rede.
"""
import math
import struct
from datetime import datetime, timezone

import pytest

from nexus.performance.clima import geotiff as GT

from clima_cog import NODATA, SessaoArquivos, fluxos_lzw, montar_cog, tiles_do_cog

URL = "https://inpe.exemplo.test/risco/RF.PREV.T0.tif"
X0, Y0, D = -50.0, 10.0, 0.01


def valor(r, c):
    return float(r * 1000 + c)


def grade(w=40, h=30):
    return [[valor(r, c) for c in range(w)] for r in range(h)]


def vazia(w=40, h=30):
    return [[None] * w for _ in range(h)]


def centro(c, r):
    """(lat, lon) do centro do pixel (coluna, linha)."""
    return Y0 - (r + 0.5) * D, X0 + (c + 0.5) * D


def abrir(g=None, janela=512, **kw):
    cog = montar_cog(g if g is not None else grade(), origem=(X0, Y0), escala=D, **kw)
    sessao = SessaoArquivos({URL: cog})
    return GT.GeoTiff(URL, sessao, janela=janela), sessao, cog


# ── georreferência e leitura ─────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("c,r", [(0, 0), (15, 15), (16, 15), (15, 16), (16, 16), (39, 29), (20, 3), (33, 29)])
def test_le_o_pixel_pela_georreferencia(c, r):
    gt, _, _ = abrir()
    assert gt.amostrar(*centro(c, r)) == GT.Amostra(valor(r, c), "ponto")
    assert gt.pixel(*centro(c, r)) == (c, r)


def test_o_norte_fica_em_cima():
    gt, _, _ = abrir()
    lat, lon = centro(10, 10)
    assert gt.pixel(lat + 0.05, lon) == (10, 5)         # 5 pixels ao norte = 5 linhas acima
    assert gt.pixel(lat, lon + 0.05) == (15, 10)        # 5 pixels ao leste = 5 colunas à direita


def test_cantos_do_pixel_pertencem_a_ele():
    gt, _, _ = abrir()
    assert gt.pixel(Y0 - 0.0001, X0 + 0.0001) == (0, 0)          # canto superior esquerdo da grade
    assert gt.pixel(Y0 - 0.2999, X0 + 0.3999) == (39, 29)        # canto inferior direito


def test_fora_da_grade_nao_e_sem_dado():
    gt, _, _ = abrir()
    # inclui a meio pixel de fora (truncar para zero, em vez de arredondar para baixo, o poria dentro da coluna 0)
    for lat, lon in [(Y0 + 0.01, X0 + 0.1), (Y0 - 0.31, X0 + 0.1), (Y0 - 0.1, X0 - 0.01), (Y0 - 0.1, X0 + 0.41),
                     (Y0 + 0.004, X0 + 0.1), (Y0 - 0.1, X0 - 0.004)]:
        assert gt.pixel(lat, lon) is None
        assert gt.amostrar(lat, lon) == GT.Amostra(None, "fora_da_grade")


def test_coordenada_que_nao_e_numero_fica_fora_da_grade():
    gt, _, _ = abrir()
    assert gt.amostrar(float("nan"), X0) == GT.Amostra(None, "fora_da_grade")
    assert gt.amostrar(Y0, float("inf")) == GT.Amostra(None, "fora_da_grade")


def test_tiles_das_bordas_cortadas_leem_certo():
    # 40 x 30 com tile de 16: a coluna 39 e a linha 29 caem em tiles que sobram do arquivo (preenchidas com nodata)
    gt, _, _ = abrir()
    assert gt.amostrar(*centro(39, 29)).valor == valor(29, 39)


def test_expoe_a_grade_lida_do_arquivo():
    gt, _, _ = abrir()
    gt.abrir()
    assert (gt.largura, gt.altura, gt.tile) == (40, 30, (16, 16))
    assert gt.origem == (X0, Y0) and gt.escala == (D, D) and gt.nodata == NODATA


def test_data_do_arquivo_vem_do_last_modified():
    gt, _, _ = abrir()
    gt.abrir()
    assert gt.modificado == datetime(2026, 10, 6, 9, 32, tzinfo=timezone.utc)


# ── o que sai da rede ────────────────────────────────────────────────────────────────────────────────────────────────

def test_pede_so_o_cabecalho_e_a_tile_do_ponto():
    gt, sessao, cog = abrir()
    offs, cnts = tiles_do_cog(cog)
    gt.amostrar(*centro(20, 3))                          # coluna 20, linha 3 -> tile (1, 0) = índice 1
    assert sessao.pedidos[0] == (URL, "bytes=0-511")
    assert sessao.pedidos[1:] == [(URL, f"bytes={offs[1]}-{offs[1] + cnts[1] - 1}")]


def test_a_mesma_tile_nao_e_buscada_duas_vezes():
    gt, sessao, _ = abrir()
    gt.amostrar(*centro(20, 3))
    gt.amostrar(*centro(21, 4))
    assert len(sessao.pedidos) == 2


def test_cabecalho_maior_que_a_janela_pede_o_resto():
    gt, sessao, _ = abrir(janela=100)                    # o IFD (e os vetores) não cabem nos primeiros 100 bytes
    assert gt.amostrar(*centro(2, 2)).valor == valor(2, 2)
    assert sessao.pedidos[0] == (URL, "bytes=0-99")
    assert len(sessao.pedidos) > 2


def test_servidor_que_ignora_o_range_manda_o_arquivo_inteiro_e_basta_um_pedido():
    cog = montar_cog(grade(), origem=(X0, Y0), escala=D)
    sessao = SessaoArquivos({URL: cog}, ignora_range=True)
    gt = GT.GeoTiff(URL, sessao, janela=512)
    assert gt.amostrar(*centro(33, 29)).valor == valor(29, 33)
    assert gt.amostrar(*centro(2, 2)).valor == valor(2, 2)
    assert len(sessao.pedidos) == 1


def test_amostrar_varios_busca_cada_tile_uma_vez_e_em_paralelo():
    gt, sessao, cog = abrir()
    pontos = [("a", *centro(1, 1)), ("b", *centro(2, 2)), ("c", *centro(20, 3)), ("d", *centro(33, 29)),
              ("e", *centro(1, 20)), ("f", Y0 + 1, X0), ("g", *centro(21, 4))]
    res = gt.amostrar_varios(pontos)
    assert res["a"].valor == valor(1, 1) and res["b"].valor == valor(2, 2) and res["c"].valor == valor(3, 20)
    assert res["d"].valor == valor(29, 33) and res["e"].valor == valor(20, 1) and res["g"].valor == valor(4, 21)
    assert res["f"] == GT.Amostra(None, "fora_da_grade")
    # 1 cabeçalho + as tiles (0,0), (1,0), (2,1) e (0,1): quatro, uma vez cada
    tiles = [p for p in sessao.pedidos[1:]]
    assert len(tiles) == 4 and len(set(tiles)) == 4


def test_pontos_embaralhados_entre_as_tiles_nao_buscam_a_mesma_tile_duas_vezes():
    # 3 x 2 tiles; sete pontos que caem em quatro tiles: cada tile sai da rede uma vez só, qualquer que seja a ordem
    gt, sessao, _ = abrir()
    pontos = [(i, *centro(c, r)) for i, (c, r) in enumerate([(1, 1), (33, 20), (20, 3), (2, 18), (3, 2), (34, 21), (21, 4)])]
    gt.amostrar_varios(pontos)
    tiles = sessao.pedidos[1:]
    assert len(tiles) == len(set(tiles)) == 4
    for p in pontos:                                      # e depois, ponto a ponto, nada mais sai da rede
        gt.amostrar(p[1], p[2])
    assert len(sessao.pedidos) == 5


# ── pixel sem dado: o maior valor do entorno de 5 x 5 ────────────────────────────────────────────────────────────────

def com(celulas, w=40, h=30):
    g = vazia(w, h)
    for (c, r), v in celulas.items():
        g[r][c] = v
    return g


def test_pixel_valido_nao_olha_o_entorno_e_nem_o_busca():
    g = com({(20, 15): 0.4, (21, 15): 0.99})
    gt, sessao, _ = abrir(g)
    assert gt.amostrar(*centro(20, 15)) == GT.Amostra(0.4, "ponto")
    assert len(sessao.pedidos) == 2                      # cabeçalho + a tile do ponto; nada do entorno


def test_pixel_sem_dado_usa_o_maior_valor_do_entorno():
    g = com({(19, 14): 0.5, (22, 17): 0.9, (18, 13): 0.3, (21, 16): 0.2})
    gt, _, _ = abrir(g)
    assert gt.amostrar(*centro(20, 15)) == GT.Amostra(0.9, "entorno")    # o MAIOR, não o mais perto nem a média


def test_o_entorno_vai_ate_dois_pixels_e_nao_mais():
    gt, _, _ = abrir(com({(23, 15): 0.99, (20, 18): 0.99, (17, 12): 0.99}))     # todos a 3 pixels
    assert gt.amostrar(*centro(20, 15)) == GT.Amostra(None, "sem_dado")
    gt, _, _ = abrir(com({(22, 13): 0.4}))                                       # canto do quadrado de 5 x 5: entra
    assert gt.amostrar(*centro(20, 15)) == GT.Amostra(0.4, "entorno")


def test_tudo_sem_dado_no_entorno():
    gt, _, _ = abrir(vazia())
    assert gt.amostrar(*centro(20, 15)) == GT.Amostra(None, "sem_dado")


def test_o_entorno_atravessa_a_divisa_de_tile():
    # (15, 15) é o último pixel da tile (0, 0); o único valor está na tile (1, 1), na diagonal
    gt, sessao, _ = abrir(com({(17, 16): 0.7}))
    assert gt.amostrar(*centro(15, 15)) == GT.Amostra(0.7, "entorno")
    assert len(sessao.pedidos) > 2                       # foi buscar as tiles vizinhas


def test_o_entorno_na_borda_da_grade_ignora_o_que_esta_fora():
    gt, _, _ = abrir(com({(2, 2): 0.6, (1, 0): 0.2}))
    assert gt.amostrar(*centro(0, 0)) == GT.Amostra(0.6, "entorno")
    gt, _, _ = abrir(vazia())
    assert gt.amostrar(*centro(39, 29)) == GT.Amostra(None, "sem_dado")


def test_o_raio_do_entorno_se_escolhe():
    gt, _, _ = abrir(com({(23, 15): 0.8}))
    assert gt.amostrar(*centro(20, 15), raio=3) == GT.Amostra(0.8, "entorno")


def test_nan_tambem_e_sem_dado():
    g = com({(20, 15): 0.3}, w=40, h=30)
    gt, _, _ = abrir(g, nodata=float("nan"))
    gt.abrir()
    assert math.isnan(gt.nodata)
    assert gt.amostrar(*centro(19, 15)) == GT.Amostra(0.3, "entorno")


def test_sem_a_tag_de_nodata_so_nan_e_sem_dado():
    gt, _, _ = abrir(com({(20, 15): -999.0}), remover=(42113,))
    assert gt.amostrar(*centro(20, 15)) == GT.Amostra(-999.0, "ponto")     # sem a tag, -999 é um valor como outro
    assert gt.nodata is None


# ── o formato mudou: erro explícito, nunca número errado ────────────────────────────────────────────────────────────

MUDANCAS = [
    ("compressão deflate", dict(tags={259: (3, 8)}), "compress"),
    ("sem compressão", dict(tags={259: (3, 1)}), "compress"),
    ("float de 32 bits", dict(tags={258: (3, 32)}), "bits"),
    ("amostra inteira", dict(tags={339: (3, 2)}), "amostra"),
    ("em faixas, sem tiles", dict(remover=(322, 323, 324, 325)), "tiles"),
    ("predictor de ponto flutuante", dict(tags={317: (3, 3)}), "predictor"),
    ("várias amostras por pixel", dict(tags={277: (3, 3)}), "amostras por pixel"),
    ("planos separados", dict(tags={284: (3, 2)}), "planar"),
    ("sistema projetado", dict(epsg=3857), "4326"),
    ("PixelIsPoint", dict(area=False), "PixelIsArea"),
    ("sem GeoKeys", dict(remover=(34735,)), "GeoKey"),
    ("sem escala do pixel", dict(remover=(33550,)), "escala"),
    ("sem tiepoint", dict(remover=(33922,)), "tiepoint"),
    ("dois tiepoints", dict(tags={33922: (12, [0, 0, 0, -50, 10, 0, 5, 5, 0, -49, 9, 0])}), "tiepoint"),
    ("tiepoint fora do canto", dict(tags={33922: (12, [3, 4, 0, -50, 10, 0])}), "tiepoint"),
    ("matriz de transformação", dict(tags={34264: (12, [0.01, 0, 0, -50, 0, -0.01, 0, 10, 0, 0, 0, 0, 0, 0, 0, 1])}),
     "ModelTransformation"),
    ("escala negativa", dict(escala=(0.01, -0.01)), "escala"),
    ("escala zero", dict(escala=(0.0, 0.01)), "escala"),
    ("BigTIFF", dict(cabecalho=b"II+\x00"), "BigTIFF"),
    ("big-endian", dict(cabecalho=b"MM\x00*"), "big-endian"),
    ("número de tiles que não bate", dict(tags={324: (4, [1, 2, 3])}), "tiles"),
    ("coordenada do canto fora do planeta", dict(origem=(-500.0, 10.0)), "georreferência"),
]


@pytest.mark.parametrize("nome,kw,trecho", MUDANCAS, ids=[m[0] for m in MUDANCAS])
def test_formato_diferente_do_medido_e_erro_explicito(nome, kw, trecho):
    kw = dict(kw)
    kw.setdefault("origem", (X0, Y0))
    cog = montar_cog(grade(), escala=kw.pop("escala", D), **kw)
    gt = GT.GeoTiff(URL, SessaoArquivos({URL: cog}), janela=512)
    with pytest.raises(GT.GeoTiffErro) as e:
        gt.amostrar(*centro(3, 3))
    assert trecho.lower() in str(e.value).lower(), str(e.value)


def test_resposta_que_nao_e_tiff_e_erro():
    sessao = SessaoArquivos({URL: b"<html><body>manutencao</body></html>" * 20})
    with pytest.raises(GT.GeoTiffErro) as e:
        GT.GeoTiff(URL, sessao).amostrar(-10, -50)
    assert "TIFF" in str(e.value)


def test_http_de_erro_diz_o_codigo_e_o_arquivo():
    with pytest.raises(GT.GeoTiffErro) as e:
        GT.GeoTiff("https://inpe.exemplo.test/risco/RF.PREV.T9.tif", SessaoArquivos({})).amostrar(-10, -50)
    assert "404" in str(e.value) and "RF.PREV.T9.tif" in str(e.value)


def test_tile_truncada_ou_corrompida_e_erro():
    cog = bytearray(montar_cog(grade(), origem=(X0, Y0), escala=D))
    offs, cnts = tiles_do_cog(bytes(cog))
    metade = offs[0] + cnts[0] // 2
    cog[metade:offs[0] + cnts[0]] = b"\x00" * (offs[0] + cnts[0] - metade)       # a segunda metade do fluxo vira lixo
    gt = GT.GeoTiff(URL, SessaoArquivos({URL: bytes(cog)}), janela=512)
    with pytest.raises(GT.GeoTiffErro):
        gt.amostrar(*centro(1, 1))


def test_tile_pedida_fora_do_arquivo_e_erro():
    cog = montar_cog(grade(), origem=(X0, Y0), escala=D)
    gt = GT.GeoTiff(URL, SessaoArquivos({URL: cog[:-50]}), janela=512)             # o arquivo foi cortado no fim
    with pytest.raises(GT.GeoTiffErro) as e:
        gt.amostrar(*centro(33, 29))                                                # a última tile
    assert "tile" in str(e.value).lower()


def test_tile_esparsa_de_zero_bytes_e_erro_explicito():
    cog = montar_cog(grade(), origem=(X0, Y0), escala=D, tags={325: (4, [0, 192, 192, 192, 192, 192])})
    gt = GT.GeoTiff(URL, SessaoArquivos({URL: cog}), janela=512)
    with pytest.raises(GT.GeoTiffErro) as e:
        gt.amostrar(*centro(1, 1))
    assert "esparsa" in str(e.value).lower() or "vazia" in str(e.value).lower()


# ── LZW do TIFF ──────────────────────────────────────────────────────────────────────────────────────────────────────

def _dados_variados(n_linhas=256, largura=2048):
    """Trechos repetitivos (o código que acabou de ser criado é o próximo: o caso KwKwK) e ruído (enche a tabela de 12 bits
    e obriga o codificador a mandar o código de limpar)."""
    import random
    r = random.Random(20261006)
    linhas = []
    for i in range(n_linhas):
        if i % 4 == 0:
            linhas.append(bytes([i % 251]) * largura)                              # corrida longa de um byte só
        elif i % 4 == 1:
            linhas.append((b"\x00\x00\x00\x00\x00\x00\xf0\x3f" * (largura // 8)))    # o double 1.0, repetido
        else:
            linhas.append(bytes(r.randrange(256) for _ in range(largura)))
    return b"".join(linhas)


def test_lzw_le_o_que_o_pillow_comprime_com_tabela_cheia_e_limpeza():
    dados = _dados_variados()
    faixas = fluxos_lzw(dados, 2048)
    assert len(faixas) > 1                               # o Pillow separa em faixas de 64 KB: cada uma é um fluxo
    pos = 0
    for fluxo, originais in faixas:
        assert GT.descomprimir_lzw(fluxo, originais) == dados[pos:pos + originais]
        pos += originais
    assert pos == len(dados)


def test_lzw_para_no_tamanho_esperado():
    dados = bytes(range(256)) * 8
    (fluxo, _), = fluxos_lzw(dados, 256)
    assert GT.descomprimir_lzw(fluxo, 100) == dados[:100]


def _bits(codigos):
    """Empacota códigos de 9 bits, bit mais significativo primeiro (como o LZW do TIFF), para montar fluxos inválidos."""
    acc, n, saida = 0, 0, bytearray()
    for c in codigos:
        acc = (acc << 9) | c
        n += 9
        while n >= 8:
            n -= 8
            saida.append((acc >> n) & 0xFF)
            acc &= (1 << n) - 1
    if n:
        saida.append((acc << (8 - n)) & 0xFF)
    return bytes(saida)


def test_lzw_com_codigo_fora_da_tabela_e_erro():
    with pytest.raises(GT.GeoTiffErro):
        GT.descomprimir_lzw(_bits([256, 65, 400, 257]), 10)           # 400 não existe: a tabela tem 259 entradas


def test_lzw_depois_da_limpeza_o_primeiro_codigo_e_um_byte():
    with pytest.raises(GT.GeoTiffErro):
        GT.descomprimir_lzw(_bits([256, 300, 257]), 10)


def test_lzw_curto_devolve_o_que_deu_e_quem_chama_confere_o_tamanho():
    (fluxo, _), = fluxos_lzw(bytes(range(200)) * 5, 200)
    assert len(GT.descomprimir_lzw(fluxo[:len(fluxo) // 2], 1000)) < 1000
