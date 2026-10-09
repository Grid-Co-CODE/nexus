"""Leitor mínimo do GeoTIFF do risco de fogo do INPE, sem rasterio e sem GDAL (06/10/2026).

Por que um leitor próprio: os quatro arquivos `RF.PREV.T0..T3.tif` (17 a 18 MB cada) são Cloud-Optimized GeoTIFF de 64
bits (BitsPerSample 64, SampleFormat 3, LZW, tiles de 256 x 256, 8699 x 8899 pixels, WGS 84, 0,01 grau), e o Pillow, que
o plano pedia, não os abre: o plugin TIFF só tem modo para float de 32 bits (`UnidentifiedImageError`, "unknown pixel
mode"; medido com o Pillow 12.2). rasterio e shapely estão vetados (o Nexus não ganha dependência), então a leitura mora
aqui, em ~150 linhas de Python puro.

Como é COG, o desenho tira proveito do formato em vez de baixar 18 MB por dia de previsão: lê o cabeçalho (o IFD e os
vetores de offsets cabem em 12 KB) e, por `Range`, SÓ a tile em que cai cada usina (7 a 95 KB), decodifica o LZW dela e
lê o double. Os quatro dias custam ~1 MB para uma dezena de pontos, contra 74 MB pelos arquivos inteiros.

Aceita exatamente o formato medido: TIFF clássico little-endian, tiles, LZW sem predictor, um plano de 1 amostra de
ponto flutuante de 64 bits, EPSG:4326, PixelIsArea, ModelPixelScale + ModelTiepoint no canto (0, 0). O que mudar disso
(compressão, tipo da amostra, tiles, georreferência) levanta `GeoTiffErro` com o que foi achado: a tela diz que o
formato do INPE mudou, em vez de mostrar um número lido do jeito errado.

Verificado em 06/10/2026 contra o arquivo real: o decodificador LZW daqui devolve bytes idênticos aos do decodificador do
Pillow nas 1190 tiles do T0 (10 s no arquivo inteiro), e o mapa decodificado tem a América do Sul com o norte em cima.
"""
import math
import struct
import sys
from array import array
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from email.utils import parsedate_to_datetime

JANELA_PADRAO = 64 * 1024      # o IFD do arquivo real acaba em 12 KB; o resto da janela é folga
TILES_NA_MEMORIA = 8           # uma tile decodificada de 256 x 256 doubles tem 512 KB
TRABALHADORES = 4              # pedidos de tile ao mesmo tempo: poucos, o servidor é público
TEMPO_LIMITE_S = 60

# código do struct e bytes de cada tipo de tag TIFF
_TIPOS = {1: ("B", 1), 2: ("s", 1), 3: ("H", 2), 4: ("I", 4), 6: ("b", 1), 8: ("h", 2), 9: ("i", 4), 11: ("f", 4),
          12: ("d", 8)}
# as tags que o leitor usa; as outras (GDAL_METADATA, de 2 KB, por exemplo) nem são buscadas
_LIDAS = {256, 257, 258, 259, 277, 284, 317, 322, 323, 324, 325, 339, 33550, 33922, 34264, 34735, 42113}


class GeoTiffErro(Exception):
    """O arquivo não é o que o leitor sabe ler (o formato mudou) ou a leitura não fechou. A mensagem vai para a tela."""


@dataclass(frozen=True)
class Amostra:
    """O valor de um ponto: `origem` diz de onde veio.

    ponto          o pixel do ponto tem dado
    entorno        o pixel do ponto é nodata (o INPE não dá risco onde não há vegetação) e o valor é o maior do entorno
    sem_dado       nem o pixel nem o entorno têm dado
    fora_da_grade  o ponto está fora do raster
    """
    valor: float | None
    origem: str


def descomprimir_lzw(dados: bytes, esperado: int) -> bytes:
    """LZW do TIFF: códigos de 9 a 12 bits, bit mais significativo primeiro, 256 = limpar a tabela, 257 = fim, e a largura
    sobe um código antes do que seria preciso ("early change"). Para ao chegar a `esperado` bytes. Devolve menos se o fluxo
    acabou antes (quem chama confere o tamanho); levanta GeoTiffErro se um código não existe."""
    tabela = [bytes((i,)) for i in range(256)] + [b"", b""]
    saida = bytearray()
    acumulado = nbits = 0
    largura = 9
    anterior = None
    for byte in dados:
        acumulado = (acumulado << 8) | byte
        nbits += 8
        while nbits >= largura:
            nbits -= largura
            codigo = (acumulado >> nbits) & ((1 << largura) - 1)
            acumulado &= (1 << nbits) - 1
            if codigo == 257:                                  # fim
                return bytes(saida[:esperado])
            if codigo == 256:                                  # limpar
                del tabela[258:]
                largura, anterior = 9, None
                continue
            if anterior is None:
                if codigo > 255:
                    raise GeoTiffErro("fluxo LZW inválido: o primeiro código depois de limpar não é um byte")
                entrada = tabela[codigo]
            else:
                if codigo < len(tabela):
                    entrada = tabela[codigo]
                elif codigo == len(tabela):                    # o código que está sendo criado agora (caso KwKwK)
                    entrada = anterior + anterior[:1]
                else:
                    raise GeoTiffErro("fluxo LZW inválido: código fora da tabela")
                if len(tabela) < 4096:
                    tabela.append(anterior + entrada[:1])
            saida += entrada
            anterior = entrada
            n = len(tabela) + 1
            largura = 9 if n < 512 else 10 if n < 1024 else 11 if n < 2048 else 12
            if len(saida) >= esperado:
                return bytes(saida[:esperado])
    return bytes(saida)


class GeoTiff:
    """Um COG lido por HTTP com `Range`. `sessao` tem `get(url, headers=..., timeout=...)` (um `requests.Session`; nos testes,
    uma sessão falsa). Nada vai à rede até o primeiro uso.

    `piso`: valor abaixo do qual o pixel não é dado (como o nodata). O risco de fogo vale de 0 a 1: um valor negativo que não é
    o nodata declarado (-999) é "sem dado" SÓ naquele ponto, e o entorno de 5 x 5 vale no lugar, em vez de derrubar o dia."""

    def __init__(self, url, sessao, *, janela=JANELA_PADRAO, trabalhadores=TRABALHADORES, timeout=TEMPO_LIMITE_S,
                 piso=None):
        self.url, self.sessao, self.timeout, self.piso = url, sessao, timeout, piso
        self._modificado_http = None          # o Last-Modified da 1ª resposta, como veio: vai no If-Range dos pedidos seguintes
        self._janela_n, self.trabalhadores = int(janela), int(trabalhadores)
        self._nome = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1] or url
        self._janela = b""                    # os primeiros bytes do arquivo, o cabeçalho
        self._inteiro = None                  # o arquivo todo, se o servidor ignorar o Range
        self._aberto = False
        self._comprimidas = {}                # tile -> bytes do fluxo LZW (pequenas; nunca se busca a mesma duas vezes)
        self._decodificadas = OrderedDict()   # tile -> bytes dos doubles (512 KB cada, poucas)
        self.modificado = None                # datetime UTC do Last-Modified do arquivo

    @property
    def validador(self):
        """O Last-Modified da 1ª resposta, como o servidor o escreveu (None sem ele): diz se o arquivo é o mesmo de antes."""
        return self._modificado_http

    # ── rede ──────────────────────────────────────────────────────────────────────────────────────────────────────────

    def _pedir(self, ini, n):
        cabecalhos = {"Range": f"bytes={ini}-{ini + n - 1}"}
        if self._modificado_http:
            # O cabeçalho (os offsets das tiles) é de UM arquivo. O INPE publica de novo todo dia, às ~06:30: se o arquivo
            # trocar entre o cabeçalho e a tile, a tile do arquivo novo, lida pelos offsets do velho, daria lixo ou, pior, um
            # número plausível de outro dia. Com If-Range o servidor só atende o Range se o arquivo é o mesmo.
            cabecalhos["If-Range"] = self._modificado_http
        r = self.sessao.get(self.url, headers=cabecalhos, timeout=self.timeout)
        if r.status_code == 200:
            if self._modificado_http and (getattr(r, "headers", None) or {}).get("Last-Modified") != self._modificado_http:
                raise GeoTiffErro(f"{self._nome} foi trocado no meio da leitura (o INPE publicou de novo): a tela tenta "
                                  "outra vez")
            # O servidor ignorou o Range e mandou o arquivo inteiro (18 MB), e é o mesmo arquivo: fica com ele e fatia
            # daqui para a frente, em vez de baixar de novo a cada tile.
            self._inteiro = r.content
            return self._inteiro[ini:ini + n], r
        if r.status_code != 206:
            raise GeoTiffErro(f"HTTP {r.status_code} ao ler {self._nome}")
        return r.content, r

    def _faixa(self, ini, n, o_que="cabeçalho"):
        """Os bytes [ini, ini + n) do arquivo, da memória se já os tem; levanta se vierem menos que o pedido."""
        if self._inteiro is not None:
            dados = self._inteiro[ini:ini + n]
        elif ini + n <= len(self._janela):
            dados = self._janela[ini:ini + n]
        else:
            dados, _ = self._pedir(ini, n)
        if len(dados) != n:
            raise GeoTiffErro(f"{o_que} truncado em {self._nome}: pedi {n} bytes a partir de {ini} e vieram {len(dados)}")
        return dados

    # ── cabeçalho ─────────────────────────────────────────────────────────────────────────────────────────────────────

    def abrir(self):
        """Lê e confere o cabeçalho (uma vez só). Levanta GeoTiffErro se o formato não for o medido."""
        if self._aberto:
            return
        dados, resposta = self._pedir(0, self._janela_n)
        self._janela = dados
        bruto = (getattr(resposta, "headers", None) or {}).get("Last-Modified")
        self._modificado_http = bruto or None
        try:
            self.modificado = parsedate_to_datetime(bruto) if bruto else None
        except (TypeError, ValueError):
            self.modificado = None
        marca = dados[:4]
        if marca[:2] == b"MM":
            raise GeoTiffErro("TIFF big-endian: o leitor só lê little-endian (o arquivo do INPE é little-endian)")
        if marca == b"II+\x00":
            raise GeoTiffErro("BigTIFF: o leitor só lê TIFF clássico (o arquivo do INPE é clássico)")
        if marca != b"II*\x00":
            raise GeoTiffErro(f"{self._nome} não é um TIFF (os primeiros bytes não são os de um TIFF)")
        self._validar(self._ler_tags())
        self._aberto = True

    def _ler_tags(self) -> dict:
        off = struct.unpack("<I", self._faixa(4, 4))[0]
        n = struct.unpack("<H", self._faixa(off, 2))[0]
        if not 1 <= n <= 256:
            raise GeoTiffErro(f"IFD com {n} entradas: não parece um TIFF")
        entradas = self._faixa(off + 2, 12 * n)
        tags = {}
        for i in range(n):
            tag, tipo, cont = struct.unpack_from("<HHI", entradas, i * 12)
            if tag not in _LIDAS:
                continue
            if tipo not in _TIPOS:
                raise GeoTiffErro(f"tag {tag} com tipo {tipo}, que o leitor não conhece")
            fmt, tam = _TIPOS[tipo]
            total = tam * cont
            if total > 32 * 1024 * 1024:
                raise GeoTiffErro(f"tag {tag} com {total} bytes: grande demais para ser um cabeçalho")
            if total <= 4:
                bruto = entradas[i * 12 + 8: i * 12 + 8 + total]
            else:
                bruto = self._faixa(struct.unpack_from("<I", entradas, i * 12 + 8)[0], total)
            tags[tag] = bruto.rstrip(b"\x00").decode("latin-1") if tipo == 2 else struct.unpack("<" + fmt * cont, bruto)
        return tags

    def _validar(self, t: dict) -> None:
        def um(tag, nome, padrao=None):
            v = t.get(tag)
            if v is None:
                if padrao is not None:
                    return padrao
                raise GeoTiffErro(f"falta {nome} (tag {tag}) no GeoTIFF do INPE")
            return v[0] if len(v) == 1 else v

        if um(277, "SamplesPerPixel", 1) != 1:
            raise GeoTiffErro(f"{um(277, 'SamplesPerPixel', 1)} amostras por pixel: o leitor lê 1")
        if um(339, "SampleFormat", 1) != 3:
            raise GeoTiffErro(f"formato de amostra {um(339, 'SampleFormat', 1)}: o leitor lê 3 (ponto flutuante)")
        if um(258, "BitsPerSample") != 64:
            raise GeoTiffErro(f"BitsPerSample {um(258, 'BitsPerSample')}: o leitor lê float de 64 bits")
        if um(259, "Compression") != 5:
            raise GeoTiffErro(f"compressão {um(259, 'Compression')}: o leitor lê só LZW (código 5)")
        if um(317, "Predictor", 1) != 1:
            raise GeoTiffErro(f"predictor {um(317, 'Predictor', 1)}: o leitor lê LZW sem predictor")
        if um(284, "PlanarConfiguration", 1) != 1:
            raise GeoTiffErro(f"PlanarConfiguration {um(284, 'PlanarConfiguration', 1)}: o leitor lê 1")
        largura, altura = um(256, "ImageWidth"), um(257, "ImageLength")
        if not (isinstance(largura, int) and isinstance(altura, int) and largura > 0 and altura > 0):
            raise GeoTiffErro(f"dimensões inválidas: {largura} x {altura}")
        if t.get(322) is None or t.get(323) is None or t.get(324) is None or t.get(325) is None:
            raise GeoTiffErro("o arquivo não está dividido em tiles (o do INPE é um COG em tiles de 256): o leitor não lê faixas")
        tw, th = um(322, "TileWidth"), um(323, "TileLength")
        if not (isinstance(tw, int) and isinstance(th, int) and tw > 0 and th > 0):
            raise GeoTiffErro(f"tamanho de tile inválido: {tw} x {th}")
        ao_lado, abaixo = math.ceil(largura / tw), math.ceil(altura / th)
        if len(t[324]) != ao_lado * abaixo or len(t[325]) != ao_lado * abaixo:
            raise GeoTiffErro(f"vetor de tiles com {len(t[324])} offsets e {len(t[325])} tamanhos; a grade pede "
                              f"{ao_lado * abaixo} tiles")
        # georreferência: ModelPixelScale + ModelTiepoint no canto, em graus de WGS 84
        if t.get(34264) is not None:
            raise GeoTiffErro("ModelTransformation (matriz de transformação) sem suporte: o leitor lê ModelPixelScale e "
                              "ModelTiepoint")
        escala = t.get(33550)
        if escala is None or len(escala) != 3:
            raise GeoTiffErro("falta a escala do pixel (ModelPixelScale, tag 33550)")
        dx, dy = escala[0], escala[1]
        if not (math.isfinite(dx) and math.isfinite(dy) and 1e-6 < dx < 5 and 1e-6 < dy < 5):
            raise GeoTiffErro(f"escala do pixel inválida: {dx} x {dy} (o leitor lê o norte em cima, em graus positivos)")
        ponto = t.get(33922)
        if ponto is None:
            raise GeoTiffErro("falta o ModelTiepoint (tag 33922)")
        if len(ponto) != 6:
            raise GeoTiffErro(f"ModelTiepoint com {len(ponto) // 6} pontos de amarração: o leitor lê um só")
        if (ponto[0], ponto[1]) != (0, 0):
            raise GeoTiffErro(f"ModelTiepoint amarra o pixel ({ponto[0]}, {ponto[1]}): o leitor lê o canto (0, 0)")
        x0, y0 = ponto[3], ponto[4]
        if not (-180 <= x0 <= 180 and -90 <= y0 <= 90 and x0 + largura * dx <= 180.001 and y0 - altura * dy >= -90.001):
            raise GeoTiffErro(f"georreferência fora do planeta: canto superior esquerdo em ({x0}, {y0})")
        geokeys = t.get(34735)
        if geokeys is None or len(geokeys) < 4:
            raise GeoTiffErro("faltam as GeoKeys (tag 34735): sem elas não se sabe o sistema de coordenadas")
        chaves = {geokeys[i]: geokeys[i + 3] for i in range(4, 4 + 4 * geokeys[3], 4)
                  if i + 3 < len(geokeys) and geokeys[i + 1] == 0}
        if chaves.get(2048) != 4326:
            raise GeoTiffErro(f"sistema de coordenadas EPSG {chaves.get(2048)}: o leitor lê EPSG 4326 (graus de lat e lon)")
        if chaves.get(1025, 1) != 1:
            raise GeoTiffErro(f"GTRasterType {chaves.get(1025)}: o leitor lê PixelIsArea (1), com o ponto no canto do pixel")
        nodata = None
        if t.get(42113):
            try:
                nodata = float(t[42113].strip())
            except ValueError:
                raise GeoTiffErro(f"valor de nodata ilegível: {t[42113][:20]!r}") from None
        self.largura, self.altura, self.tile = largura, altura, (tw, th)
        self.origem, self.escala, self.nodata = (x0, y0), (dx, dy), nodata
        self._ao_lado, self._offsets, self._bytes = ao_lado, t[324], t[325]

    # ── leitura ───────────────────────────────────────────────────────────────────────────────────────────────────────

    def pixel(self, lat, lon):
        """(coluna, linha) do pixel que contém o ponto, ou None se está fora da grade. O norte está em cima."""
        self.abrir()
        try:
            lat, lon = float(lat), float(lon)
        except (TypeError, ValueError):
            return None
        if not (math.isfinite(lat) and math.isfinite(lon)):
            return None
        col = math.floor((lon - self.origem[0]) / self.escala[0])
        lin = math.floor((self.origem[1] - lat) / self.escala[1])
        return (col, lin) if 0 <= col < self.largura and 0 <= lin < self.altura else None

    def _baixar_tile(self, idx):
        if self._bytes[idx] == 0:
            raise GeoTiffErro(f"tile {idx} vazia (esparsa, 0 bytes): o leitor não sabe se vale nodata ou zero")
        return self._faixa(self._offsets[idx], self._bytes[idx], f"tile {idx}")

    def _baixar_varias(self, indices):
        faltam = [i for i in indices if i not in self._comprimidas]
        if self.trabalhadores > 1 and len(faltam) > 1:
            with ThreadPoolExecutor(max_workers=min(self.trabalhadores, len(faltam))) as pool:
                for i, dados in zip(faltam, pool.map(self._baixar_tile, faltam)):
                    self._comprimidas[i] = dados
        else:
            for i in faltam:
                self._comprimidas[i] = self._baixar_tile(i)

    def _tile(self, idx) -> bytes:
        if idx in self._decodificadas:
            self._decodificadas.move_to_end(idx)
            return self._decodificadas[idx]
        if idx not in self._comprimidas:
            self._comprimidas[idx] = self._baixar_tile(idx)
        esperado = self.tile[0] * self.tile[1] * 8
        bruto = descomprimir_lzw(self._comprimidas[idx], esperado)
        if len(bruto) < esperado:
            raise GeoTiffErro(f"tile {idx} truncada: o LZW rendeu {len(bruto)} dos {esperado} bytes")
        self._decodificadas[idx] = bruto
        while len(self._decodificadas) > TILES_NA_MEMORIA:
            self._decodificadas.popitem(last=False)
        return bruto

    def _valor(self, col, lin):
        """O valor do pixel, ou None se está fora da grade ou é nodata."""
        if not (0 <= col < self.largura and 0 <= lin < self.altura):
            return None
        tw, th = self.tile
        bruto = self._tile((lin // th) * self._ao_lado + col // tw)
        v = struct.unpack_from("<d", bruto, ((lin % th) * tw + col % tw) * 8)[0]
        if not math.isfinite(v) or (self.nodata is not None and v == self.nodata):
            return None
        if self.piso is not None and v < self.piso:
            return None
        return v

    def amostrar(self, lat, lon, raio=2) -> Amostra:
        """O valor no ponto. Se o pixel dele é nodata (o INPE mascara o que não tem vegetação, e uma usina é terreno
        aberto), vale o MAIOR valor do quadrado de (2 * raio + 1) pixels de lado em volta (raio 2 = 5 x 5, ~2 km)."""
        p = self.pixel(lat, lon)
        if p is None:
            return Amostra(None, "fora_da_grade")
        col, lin = p
        v = self._valor(col, lin)
        if v is not None:
            return Amostra(v, "ponto")
        melhor = None
        for dl in range(-raio, raio + 1):
            for dc in range(-raio, raio + 1):
                if dl or dc:
                    w = self._valor(col + dc, lin + dl)
                    if w is not None and (melhor is None or w > melhor):
                        melhor = w
        return Amostra(melhor, "entorno") if melhor is not None else Amostra(None, "sem_dado")

    def amostrar_varios(self, pontos, raio=2) -> dict:
        """`pontos`: [(chave, lat, lon)]. {chave: Amostra}. Busca as tiles dos pontos em paralelo, uma vez cada, e lê os
        pontos em ordem de tile, para decodificar cada tile uma vez só."""
        self.abrir()
        com_pixel = []
        for chave, lat, lon in pontos:
            p = self.pixel(lat, lon)
            tile = None if p is None else (p[1] // self.tile[1]) * self._ao_lado + p[0] // self.tile[0]
            com_pixel.append((tile if tile is not None else -1, chave, lat, lon))
        self._baixar_varias(sorted({t for t, *_ in com_pixel if t >= 0}))
        return {chave: self.amostrar(lat, lon, raio) for _, chave, lat, lon in sorted(com_pixel, key=lambda x: x[0])}

    # ── a área inteira, em blocos (o mapa de calor do Mapa de risco, 09/10/2026) ──────────────────────────────────────

    def somar_em_blocos(self, caixa, passo, *, precisa=None, teto=None) -> dict:
        """A soma e a contagem dos pixels COM dado em blocos de `passo` graus (o bloco é um número inteiro de pixels, alinhado à
        origem do arquivo), na `caixa` (lon mín., lat mín., lon máx., lat máx.). `precisa(oeste, sul, leste, norte)` diz se uma
        tile é preciso ler (None = todas as da caixa): o mapa só pede as que encostam no Brasil.

        Para que serve (Levi, 09/10/2026, "uma outra visão tipo um mapa de calor"): o risco por usina lê só a tile de cada usina;
        o mapa de calor precisa da área. Medido em 09/10/2026 no arquivo real: a caixa do Brasil são 289 tiles e 11,8 MB por dia,
        e o LZW em Python leva de 3 a 54 ms por tile. Pixel sem dado (nodata, abaixo do `piso`, NaN) não entra na soma nem na
        contagem: o bloco sem nenhum pixel com dado fica com contagem 0, e quem desenha diz "sem dado" (nunca inventa 0).
        Valor acima do `teto` levanta GeoTiffErro: uma escala trocada (0 a 100) acenderia o mapa inteiro.

        Devolve {"oeste", "norte", "dlon", "dlat", "ncols", "nrows", "soma": array('d'), "n": array('I'), "px_por_bloco",
        "tiles": quantas foram lidas, "bytes": quanto veio da rede}; a célula (linha r, coluna c) é o índice r * ncols + c."""
        self.abrir()
        (x0, y0), (dx, dy) = self.origem, self.escala
        bx, by = max(1, round(passo / dx)), max(1, round(passo / dy))
        lon0, lat0, lon1, lat1 = caixa
        col0 = max(0, math.floor((lon0 - x0) / dx))
        col1 = min(self.largura - 1, math.floor((lon1 - x0) / dx))
        lin0 = max(0, math.floor((y0 - lat1) / dy))
        lin1 = min(self.altura - 1, math.floor((y0 - lat0) / dy))
        if col0 > col1 or lin0 > lin1:
            raise GeoTiffErro(f"{self._nome} não cobre a área pedida")
        bc0, bc1, br0, br1 = col0 // bx, col1 // bx, lin0 // by, lin1 // by
        ncols, nrows = bc1 - bc0 + 1, br1 - br0 + 1
        # os pixels que os blocos cobrem (o último bloco pode passar da borda do arquivo: só conta o que existe)
        pc0, pc1 = bc0 * bx, min(self.largura, (bc1 + 1) * bx)
        pl0, pl1 = br0 * by, min(self.altura, (br1 + 1) * by)
        tw, th = self.tile
        tiles = []
        for ty in range(pl0 // th, (pl1 - 1) // th + 1):
            for tx in range(pc0 // tw, (pc1 - 1) // tw + 1):
                caixa_tile = (x0 + tx * tw * dx, y0 - (ty + 1) * th * dy, x0 + (tx + 1) * tw * dx, y0 - ty * th * dy)
                if precisa is None or precisa(*caixa_tile):
                    tiles.append((ty, tx))
        indices = [ty * self._ao_lado + tx for ty, tx in tiles]
        self._baixar_varias(indices)
        soma = array("d", [0.0]) * (ncols * nrows)
        n = array("I", [0]) * (ncols * nrows)
        for (ty, tx), idx in zip(tiles, indices):
            self._somar_tile(ty, tx, idx, soma, n, (bc0, br0, ncols, bx, by), (pc0, pc1, pl0, pl1), teto)
            self._comprimidas.pop(idx, None)               # 8 a 12 MB de tiles comprimidas: solta cada uma depois de usar
        return {"oeste": x0 + bc0 * bx * dx, "norte": y0 - br0 * by * dy, "dlon": bx * dx, "dlat": by * dy, "ncols": ncols,
                "nrows": nrows, "soma": soma, "n": n, "px_por_bloco": bx * by, "tiles": len(tiles),
                "bytes": sum(self._bytes[i] for i in indices)}

    def _valido(self, v, teto) -> bool:
        if not math.isfinite(v) or (self.nodata is not None and v == self.nodata):
            return False
        if self.piso is not None and v < self.piso:
            return False
        if teto is not None and v > teto:
            raise GeoTiffErro(f"valor {v:g} acima de {teto:g} em {self._nome}: o INPE mudou a escala?")
        return True

    def _somar_tile(self, ty, tx, idx, soma, n, blocos, pixels, teto) -> None:
        """Soma os pixels de uma tile nos blocos. Uma linha da tile inteira limpa (sem nodata, sem NaN, dentro do piso e do teto)
        vai pelo caminho rápido (a `sum` do Python em cada pedaço de bloco); só a linha que mistura dado e nodata (costa, cidade,
        água) é olhada pixel a pixel. Sem isso, as ~200 tiles do Brasil levavam o triplo."""
        bc0, br0, ncols, bx, by = blocos
        pc0, pc1, pl0, pl1 = pixels
        tw, th = self.tile
        bruto = descomprimir_lzw(self._comprimidas[idx], tw * th * 8)
        if len(bruto) < tw * th * 8:
            raise GeoTiffErro(f"tile {idx} truncada: o LZW rendeu {len(bruto)} dos {tw * th * 8} bytes")
        valores = array("d")
        valores.frombytes(bruto)
        if sys.byteorder == "big":                          # o arquivo é little-endian (conferido no cabeçalho)
            valores.byteswap()
        c_ini, c_fim = max(pc0, tx * tw), min(pc1, (tx + 1) * tw)
        if c_ini >= c_fim:
            return
        for ly in range(th):
            lin = ty * th + ly
            if lin < pl0 or lin >= pl1:
                continue
            base = (lin // by - br0) * ncols - bc0
            linha = valores[ly * tw + c_ini - tx * tw: ly * tw + c_fim - tx * tw]
            sem_dado = linha.count(self.nodata) if self.nodata is not None else 0
            if sem_dado == len(linha):
                continue
            total = sum(linha)
            limpa = (sem_dado == 0 and math.isfinite(total) and (self.piso is None or min(linha) >= self.piso)
                     and (teto is None or max(linha) <= teto))
            c = c_ini
            while c < c_fim:
                fim = min(c_fim, (c // bx + 1) * bx)
                pedaco = linha[c - c_ini: fim - c_ini]
                k = base + c // bx
                if limpa:
                    soma[k] += sum(pedaco)
                    n[k] += len(pedaco)
                else:
                    for v in pedaco:
                        if self._valido(v, teto):
                            soma[k] += v
                            n[k] += 1
                c = fim
