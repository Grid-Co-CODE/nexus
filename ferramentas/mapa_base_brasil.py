"""O mapa base do Brasil do Mapa de equipe (11/11/2026): recorta o Brasil do mapa do mundo do Protomaps (o build diário,
https://build.protomaps.com/AAAAMMDD.pmtiles, dados do OpenStreetMap, ODbL) num PMTiles próprio, lendo por pedaços
(HTTP Range) só os blocos do Brasil.

Por que assim: o guia do Willian sugere gerar com o Planetiler a partir do extrato da Geofabrik, mas o Planetiler só se
baixa pelos arquivos de release do GitHub, que esta rede derruba. O Protomaps já entrega o mundo pronto, no mesmo formato
(PMTiles), e o recorte baixa só o Brasil.

O que entra: até o zoom 6, todo bloco da caixa do Brasil; do 7 em diante, só os descendentes dos blocos de zoom 7 que
encostam num estado do Brasil (o contorno do IBGE). O que é de outro país fica coberto
pela máscara no estilo do mapa ("só o Brasil", pedido do Levi em 11/11/2026).

Uso (fora do OneDrive, numa pasta com ~5 GB livres): python ferramentas/mapa_base_brasil.py --build AAAAMMDD --maxzoom 14
[--estimar] --saida brasil.pmtiles. O arquivo pronto sobe em Base > Mapa base (só administrador). Medido em 11/11/2026, build
20261110: 2,39 GB até o zoom 14 (5,8 GB até o 15), 1,78 milhão de conteúdos, baixado em ~70 s a 35 MB/s.
"""
import argparse
import bisect
import gzip
import hashlib
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests  # noqa: E402
# o pmtiles (o pacote do PyPI, o leitor e gravador oficial do formato) só esta ferramenta usa: pip install pmtiles
from pmtiles.tile import (Compression, deserialize_directory, deserialize_header, zxy_to_tileid)  # noqa: E402
from pmtiles.writer import finalize_header  # noqa: E402

UFS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "clima" / "ibge-ufs-minima.geojson"
CAIXA = (-74.6, -34.4, -28.4, 5.9)          # o Brasil (com Fernando de Noronha) e uma folga
Z_ANCORA = 7
S = requests.Session()


def lon_lat_do_bloco(z, x, y):
    import math
    n = 1 << z
    lon0, lon1 = x / n * 360 - 180, (x + 1) / n * 360 - 180
    lat = lambda yy: math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))  # noqa: E731
    return lon0, lat(y + 1), lon1, lat(y)


def bloco_de(z, lon, lat):
    import math
    n = 1 << z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def poligonos():
    g = json.loads(UFS.read_text(encoding="utf-8"))
    out = []
    for f in g["features"]:
        geo = f["geometry"]
        pols = geo["coordinates"] if geo["type"] == "MultiPolygon" else [geo["coordinates"]]
        out += [p[0] for p in pols]                  # o anel de fora basta (com a folga de um bloco)
    return out


def dentro(lon, lat, anel):
    d = False
    j = len(anel) - 1
    for i in range(len(anel)):
        xi, yi = anel[i]
        xj, yj = anel[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            d = not d
        j = i
    return d


def ancoras():
    """Os blocos de zoom 7 que encostam num estado do Brasil."""
    aneis = poligonos()
    x0, y0 = bloco_de(Z_ANCORA, CAIXA[0], CAIXA[3])
    x1, y1 = bloco_de(Z_ANCORA, CAIXA[2], CAIXA[1])
    tocados = set()
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            a, b, c, d = lon_lat_do_bloco(Z_ANCORA, x, y)
            amostras = [(a + (c - a) * i / 6, b + (d - b) * j / 6) for i in range(7) for j in range(7)]
            if any(dentro(lo, la, anel) for lo, la in amostras for anel in aneis) or any(
                    a <= lo <= c and b <= la <= d for anel in aneis for lo, la in anel[::5]):
                tocados.add((x, y))
    # sem folga: o teste já pega o bloco que só encosta no contorno (a amostra dentro e o vértice no bloco)
    return tocados


def faixas(maxzoom):
    """As faixas [ini, fim) de tile_id do recorte, em ordem e sem sobrepor."""
    base = lambda z: ((1 << (z * 2)) - 1) // 3  # noqa: E731
    out = []
    for z in range(0, min(Z_ANCORA, maxzoom + 1)):
        x0, y0 = bloco_de(z, CAIXA[0], CAIXA[3])
        x1, y1 = bloco_de(z, CAIXA[2], CAIXA[1])
        out += [(t, t + 1) for t in (zxy_to_tileid(z, x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1))]
    anc = ancoras()
    for z in range(Z_ANCORA, maxzoom + 1):
        k = 1 << (2 * (z - Z_ANCORA))
        for x, y in anc:
            d7 = zxy_to_tileid(Z_ANCORA, x, y) - base(Z_ANCORA)
            ini = base(z) + d7 * k
            out.append((ini, ini + k))
    out.sort()
    juntas = []
    for a, b in out:
        if juntas and a <= juntas[-1][1]:
            juntas[-1] = (juntas[-1][0], max(juntas[-1][1], b))
        else:
            juntas.append((a, b))
    return juntas, anc


def conferir_hilbert():
    """A faixa dos descendentes de um bloco de zoom 7 é contígua e bate com a conta (a prova, no zoom 9)."""
    from pmtiles.tile import tileid_to_zxy
    base = lambda z: ((1 << (z * 2)) - 1) // 3  # noqa: E731
    for x, y in ((10, 20), (60, 70), (127, 0), (45, 66)):
        d7 = zxy_to_tileid(7, x, y) - base(7)
        ini = base(9) + d7 * 16
        filhos = {tileid_to_zxy(t)[1:] for t in range(ini, ini + 16)}
        assert filhos == {(x * 4 + i, y * 4 + j) for i in range(4) for j in range(4)}, (x, y)


def pegar(url, ini, tam, tentativas=6):
    for n in range(tentativas):
        try:
            r = S.get(url, headers={"Range": f"bytes={ini}-{ini + tam - 1}"}, timeout=120)
            if r.status_code == 206 and len(r.content) == tam:
                return r.content
            raise IOError(f"HTTP {r.status_code}, {len(r.content)} de {tam} bytes")
        except Exception as e:      # noqa: BLE001
            if n == tentativas - 1:
                raise
            print("  de novo:", type(e).__name__, str(e)[:80], flush=True)
            time.sleep(2 * (n + 1))


def descomprime(h, b):
    return gzip.decompress(b) if h["internal_compression"] == Compression.GZIP else b


def entradas_do_recorte(url, h, juntas):
    """As entradas (tile_id, offset, length, run_length) do mundo que caem nas faixas do recorte, já cortadas nelas."""
    inis = [a for a, _b in juntas]

    def cruza(a, b):
        i = bisect.bisect_right(inis, a) - 1
        for k in range(max(i, 0), len(juntas)):
            ja, jb = juntas[k]
            if ja >= b:
                return False
            if jb > a:
                return True
        return False

    def cortes(a, b):
        i = max(bisect.bisect_right(inis, a) - 1, 0)
        for k in range(i, len(juntas)):
            ja, jb = juntas[k]
            if ja >= b:
                break
            lo, hi = max(a, ja), min(b, jb)
            if lo < hi:
                yield lo, hi

    out = []
    pilha = [(h["root_offset"], h["root_length"], 0, 1 << 62)]
    lidas = 0
    while pilha:
        off, tam, a0, b0 = pilha.pop()
        ents = deserialize_directory(pegar(url, off, tam))       # o pmtiles já descomprime o diretório
        lidas += 1
        for i, e in enumerate(ents):
            fim = ents[i + 1].tile_id if i + 1 < len(ents) else b0
            if e.run_length == 0:
                if cruza(e.tile_id, fim):
                    pilha.append((h["leaf_directory_offset"] + e.offset, e.length, e.tile_id, fim))
            else:
                for lo, hi in cortes(e.tile_id, e.tile_id + e.run_length):
                    out.append((lo, e.offset, e.length, hi - lo))
        if lidas % 50 == 0:
            print(f"  diretórios lidos: {lidas}, entradas: {len(out)}", flush=True)
    out.sort()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", required=True)
    ap.add_argument("--maxzoom", type=int, default=14)
    ap.add_argument("--saida", default="brasil.pmtiles")
    ap.add_argument("--estimar", action="store_true")
    args = ap.parse_args()
    conferir_hilbert()
    url = f"https://build.protomaps.com/{args.build}.pmtiles"
    h = deserialize_header(pegar(url, 0, 127))
    meta = json.loads(descomprime(h, pegar(url, h["metadata_offset"], h["metadata_length"])))
    print("mundo:", args.build, "| zoom", h["min_zoom"], "a", h["max_zoom"], "| blocos", h["tile_compression"],
          "| tipo", h["tile_type"], flush=True)
    juntas, anc = faixas(args.maxzoom)
    print("blocos de zoom 7 no recorte:", len(anc), "| faixas:", len(juntas), flush=True)
    ents = entradas_do_recorte(url, h, juntas)
    unicos = {}
    for t, off, ln, rl in ents:
        unicos.setdefault(off, ln)
    total = sum(unicos.values())
    print(f"entradas: {len(ents)} | blocos endereçados: {sum(e[3] for e in ents)} | conteúdos únicos: {len(unicos)} | "
          f"a baixar: {total / 1e9:.2f} GB", flush=True)
    if args.estimar:
        return
    # a ordem nova dos conteúdos: a da 1ª aparição pelo tile_id (o arquivo fica "clustered")
    novo, pos = {}, 0
    for t, off, ln, rl in ents:
        if off not in novo:
            novo[off] = pos
            pos += ln
    dados = Path(args.saida + ".dados")
    with open(dados, "wb") as f:
        f.truncate(pos)
    # os pedaços: conteúdos vizinhos no mundo juntos num pedido só (até 32 MB, buraco de até 256 KB)
    offs = sorted(unicos)
    pedacos, atual = [], None
    for o in offs:
        fim = o + unicos[o]
        if atual and o - atual[1] <= 256 * 1024 and fim - atual[0] <= 32 * 1024 * 1024:
            atual[1] = max(atual[1], fim)
            atual[2].append(o)
        else:
            atual = [o, fim, [o]]
            pedacos.append(atual)
    print("pedidos:", len(pedacos), flush=True)
    feito = [0, 0]
    t0 = time.time()

    def baixar(p):
        a, b, lista = p
        buf = pegar(url, h["tile_data_offset"] + a, b - a)
        with open(dados, "r+b") as f:
            for o in lista:
                f.seek(novo[o])
                f.write(buf[o - a:o - a + unicos[o]])
        return b - a
    with ThreadPoolExecutor(max_workers=8) as ex:
        for n in ex.map(baixar, pedacos):
            feito[0] += 1
            feito[1] += n
            if feito[0] % 25 == 0 or feito[0] == len(pedacos):
                v = feito[1] / max(time.time() - t0, 1) / 1e6
                print(f"  {feito[0]}/{len(pedacos)} pedidos, {feito[1] / 1e9:.2f} GB, {v:.1f} MB/s", flush=True)
    from pmtiles.tile import Entry
    entradas = []
    for t, off, ln, rl in ents:
        if entradas and entradas[-1].offset == novo[off] and entradas[-1].tile_id + entradas[-1].run_length == t:
            entradas[-1].run_length += rl
        else:
            entradas.append(Entry(t, novo[off], ln, rl))
    cab = dict(h)
    cab["max_zoom"] = args.maxzoom
    cab["min_lon_e7"], cab["min_lat_e7"] = int(CAIXA[0] * 1e7), int(CAIXA[1] * 1e7)
    cab["max_lon_e7"], cab["max_lat_e7"] = int(CAIXA[2] * 1e7), int(CAIXA[3] * 1e7)
    cab["center_zoom"], cab["center_lon_e7"], cab["center_lat_e7"] = 4, int(-52.0 * 1e7), int(-14.5 * 1e7)
    meta = {**meta, "name": "Brasil (Mapa de equipe do Nexus)", "description":
            f"Recorte do Brasil do build {args.build} do Protomaps, até o zoom {args.maxzoom}."}
    addressed = sum(e.run_length for e in entradas)
    cab_b, raiz, meta_b, folhas = finalize_header(cab, addressed, entradas, len(novo), meta, True, pos)
    with open(args.saida, "wb") as f:
        f.write(cab_b)
        f.write(raiz)
        f.write(meta_b)
        f.write(folhas)
        with open(dados, "rb") as d:
            while True:
                b = d.read(16 * 1024 * 1024)
                if not b:
                    break
                f.write(b)
    dados.unlink()
    sha = hashlib.sha256()
    with open(args.saida, "rb") as f:
        for b in iter(lambda: f.read(16 * 1024 * 1024), b""):
            sha.update(b)
    print("pronto:", args.saida, f"{Path(args.saida).stat().st_size / 1e9:.2f} GB", "sha256", sha.hexdigest(), flush=True)


if __name__ == "__main__":
    main()
