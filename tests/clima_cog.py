"""COG pequeno montado dentro do teste: nenhum binário no repositório (06/10/2026).

O GeoTIFF do risco de fogo do INPE é float de 64 bits, LZW e em tiles, e o Pillow não o abre (ver `nexus/performance/clima/
geotiff.py`). O teste monta um com o mesmo desenho, em miniatura: o contêiner (cabeçalho, IFD, tiles, tags de
georreferência) é escrito aqui à mão, e o fluxo LZW de cada tile é comprimido pelo PILLOW (libtiff), um codificador
independente do decodificador que está sob teste. Para o Pillow, os bytes dos doubles de uma linha da tile são uma linha
de pixels de 8 bits; sem predictor, o LZW comprime só bytes e não sabe de que tamanho é a amostra.

Também traz a sessão falsa que serve esses bytes por `Range`, para nenhum teste ir à rede.
"""
import io
import math
import struct

from PIL import Image

NODATA = -999.0

# tipo TIFF -> código do struct (o 2, ASCII, vai como bytes)
_STRUCT = {1: "B", 3: "H", 4: "I", 12: "d"}


def fluxos_lzw(dados: bytes, largura_bytes: int) -> list[tuple[bytes, int]]:
    """Comprime com o LZW do Pillow e devolve [(fluxo LZW, bytes originais)], uma entrada por faixa que ele escreveu.
    Imagem pequena sai numa faixa só; de 64 KB para cima, em várias (cada faixa é um fluxo LZW independente)."""
    altura = len(dados) // largura_bytes
    buf = io.BytesIO()
    Image.frombytes("L", (largura_bytes, altura), dados).save(buf, format="TIFF", compression="tiff_lzw")
    bruto = buf.getvalue()
    tags = Image.open(io.BytesIO(bruto)).tag_v2
    linhas_por_faixa = tags[278][0] if isinstance(tags[278], tuple) else tags[278]
    restam, saida = len(dados), []
    for off, n in zip(tags[273], tags[279]):
        originais = min(linhas_por_faixa * largura_bytes, restam)
        saida.append((bruto[off:off + n], originais))
        restam -= originais
    return saida


def fluxo_da_tile(bruto: bytes, largura_bytes: int) -> bytes:
    (fluxo, _), = fluxos_lzw(bruto, largura_bytes)       # uma tile = um fluxo (falha alto se o Pillow a dividir)
    return fluxo


def _codificar(tipo, valores) -> tuple[int, bytes]:
    """(contagem, bytes) de um valor de tag."""
    if tipo == 2:
        dados = valores if isinstance(valores, bytes) else valores.encode("latin-1")
        return len(dados), dados
    valores = list(valores) if isinstance(valores, (list, tuple)) else [valores]
    return len(valores), struct.pack("<" + _STRUCT[tipo] * len(valores), *valores)


def montar_cog(grade, *, tile=16, origem=(-50.0, 10.0), escala=0.01, nodata=NODATA, tags=None, remover=(),
               epsg=4326, area=True, cabecalho=b"II*\x00") -> bytes:
    """`grade[linha][coluna]` em float (None = nodata). `tags` troca ou acrescenta {tag: (tipo TIFF, valores)}; `remover`
    tira tags; `cabecalho` troca os 4 primeiros bytes (BigTIFF ou big-endian de mentira); `escala` é um número ou (dx, dy)."""
    h, w = len(grade), len(grade[0])
    ao_lado, abaixo = math.ceil(w / tile), math.ceil(h / tile)
    cheio = nodata
    cargas = []
    for ty in range(abaixo):
        for tx in range(ao_lado):
            linhas = []
            for ly in range(tile):
                lin = ty * tile + ly
                linha = [(grade[lin][tx * tile + lx] if lin < h and tx * tile + lx < w else None) for lx in range(tile)]
                linhas.append(struct.pack(f"<{tile}d", *[cheio if v is None else v for v in linha]))
            cargas.append(fluxo_da_tile(b"".join(linhas), tile * 8))
    dx, dy = escala if isinstance(escala, tuple) else (escala, escala)
    chaves = [(1024, 0, 1, 2), (1025, 0, 1, 1 if area else 2), (2048, 0, 1, epsg)]
    geokeys = [1, 1, 0, len(chaves)] + [x for c in chaves for x in c]
    sem_dado = "nan" if isinstance(nodata, float) and math.isnan(nodata) else f"{nodata:g}"
    campos = {
        256: (3, w), 257: (3, h), 258: (3, 64), 259: (3, 5), 262: (3, 1), 277: (3, 1), 284: (3, 1), 317: (3, 1),
        322: (3, tile), 323: (3, tile), 324: (4, [0] * len(cargas)), 325: (4, [len(c) for c in cargas]), 339: (3, 3),
        33550: (12, [dx, dy, 0.0]), 33922: (12, [0, 0, 0, origem[0], origem[1], 0]), 34735: (3, geokeys),
        42113: (2, sem_dado + "\x00"),
    }
    campos.update(tags or {})
    for t in remover:
        campos.pop(t, None)
    entradas = sorted(campos)
    inicio_extras = 8 + 2 + 12 * len(entradas) + 4
    # onde cai cada valor que não cabe nos 4 bytes da entrada (o tamanho de cada um não depende dos offsets das tiles)
    posicao, p = {}, inicio_extras
    for t in entradas:
        _, dados = _codificar(*campos[t])
        if len(dados) > 4:
            posicao[t] = p
            p += len(dados) + len(dados) % 2
    offsets, q = [], p
    for c in cargas:
        offsets.append(q)
        q += len(c)
    if 324 in campos and 324 not in (tags or {}):
        campos[324] = (4, offsets)
    ifd, extras = struct.pack("<H", len(entradas)), b""
    for t in entradas:
        tipo = campos[t][0]
        cont, dados = _codificar(*campos[t])
        if len(dados) <= 4:
            ifd += struct.pack("<HHI", t, tipo, cont) + dados.ljust(4, b"\x00")
        else:
            ifd += struct.pack("<HHII", t, tipo, cont, posicao[t])
            extras += dados + b"\x00" * (len(dados) % 2)
    ifd += struct.pack("<I", 0)
    return cabecalho + struct.pack("<I", 8) + ifd + extras + b"".join(cargas)


def tiles_do_cog(cog: bytes) -> tuple[tuple, tuple]:
    """(TileOffsets, TileByteCounts) lidos pelo carregador de IFD do Pillow, que não depende do leitor sob teste."""
    from PIL import TiffImagePlugin
    ifd = TiffImagePlugin.ImageFileDirectory_v2(ifh=cog[:8])
    fp = io.BytesIO(cog)
    fp.seek(8)
    ifd.load(fp)
    return tuple(ifd[324]), tuple(ifd[325])


class Resposta:
    def __init__(self, status=200, corpo=b"", cabecalhos=None):
        self.status_code, self.content, self.headers = status, corpo, dict(cabecalhos or {})

    @property
    def text(self):
        return self.content.decode("utf-8", "replace")

    def json(self):
        import json
        return json.loads(self.content)

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")


class SessaoArquivos:
    """Sessão falsa: serve bytes por URL, com `Range` (206) ou, se `ignora_range`, o arquivo inteiro (200)."""

    def __init__(self, arquivos, ignora_range=False, modificado="Tue, 06 Oct 2026 09:32:00 GMT"):
        self.arquivos, self.ignora_range, self.modificado = dict(arquivos), ignora_range, modificado
        self.pedidos = []                     # (url, faixa pedida ou None)

    def get(self, url, params=None, headers=None, timeout=None):
        faixa = (headers or {}).get("Range")
        self.pedidos.append((url, faixa))
        if url not in self.arquivos:
            return Resposta(404, b"nao ha")
        corpo = self.arquivos[url]
        cab = {"Last-Modified": self.modificado, "Content-Type": "image/tiff"}
        if faixa and not self.ignora_range:
            ini, fim = (int(x) for x in faixa.removeprefix("bytes=").split("-"))
            fatia = corpo[ini:fim + 1]
            cab["Content-Range"] = f"bytes {ini}-{ini + len(fatia) - 1}/{len(corpo)}"
            return Resposta(206, fatia, cab)
        return Resposta(200, corpo, cab)
