"""O Mapa de risco (07/10/2026): o contorno dos estados, a projeção e o recorte de cada região, sem Flask.

Levi, 07/10: "ia ficar pica" — a lista do Clima e risco ganhou um mapa do Brasil com as usinas na cor do nível, os avisos do
INMET e os focos do INPE. O SVG nasce no servidor: nada de biblioteca de JavaScript, de mapa de terceiros ou de dependência
nova, e nenhuma busca ao IBGE em tempo de execução.

O contorno é o do IBGE (Malhas territoriais, API v3, `qualidade=minima`, divisão por UF), baixado UMA vez e guardado em
`nexus/static/clima/ibge-ufs-minima.geojson` (98 KB, 27 UFs, ~5.500 vértices com 4 casas). Como refazê-lo e a fonte: seção
"Mapa de risco" de `nexus/performance/CLAUDE.md`. O arquivo "mínimo" é só o continente: sem Trindade nem Fernando de Noronha,
que alargariam o recorte do Brasil em uns 15% de oceano (o teste `test_o_contorno_e_so_o_continente...` avisa se trocarem).

Projeção equiretangular com a correção de cos(latitude média): o x é a longitude vezes o cosseno da latitude do MEIO do
recorte, o y é a latitude. Sem o cosseno o Brasil ficaria 3% mais largo; no Sul (28 graus), 13%. Cada recorte usa a latitude
média dele e refaz o viewBox, que tem sempre 1000 de largura: o tamanho dos pontos e dos traços, que o CSS decide em unidades
do SVG, vale igual em todas as vistas. A conta fica em graus de latitude (1 = ~111 km) e a `Vista` a leva para o SVG.

Função pura: nada aqui lê cadastro, fonte ou relógio. Quem junta isso com as usinas e as fontes é o `montar` (adiante).
"""
import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

ARQUIVO_UFS = Path(__file__).resolve().parents[2] / "static" / "clima" / "ibge-ufs-minima.geojson"
LARGURA = 1000                     # a largura do viewBox de TODA vista; a altura sai da geografia
MARGEM = 0.03                      # folga em volta do recorte, para o traço da borda e o ponto da usina não serem cortados
BRASIL = "brasil"
REGIOES = {"norte": "Norte", "nordeste": "Nordeste", "centro-oeste": "Centro-Oeste", "sudeste": "Sudeste", "sul": "Sul"}

# O IBGE manda só `codarea` (o código da UF), sem sigla nem nome: a tabela é a oficial da divisão política.
UFS = {
    "11": ("RO", "Rondônia", "norte"), "12": ("AC", "Acre", "norte"), "13": ("AM", "Amazonas", "norte"),
    "14": ("RR", "Roraima", "norte"), "15": ("PA", "Pará", "norte"), "16": ("AP", "Amapá", "norte"),
    "17": ("TO", "Tocantins", "norte"),
    "21": ("MA", "Maranhão", "nordeste"), "22": ("PI", "Piauí", "nordeste"), "23": ("CE", "Ceará", "nordeste"),
    "24": ("RN", "Rio Grande do Norte", "nordeste"), "25": ("PB", "Paraíba", "nordeste"),
    "26": ("PE", "Pernambuco", "nordeste"), "27": ("AL", "Alagoas", "nordeste"), "28": ("SE", "Sergipe", "nordeste"),
    "29": ("BA", "Bahia", "nordeste"),
    "31": ("MG", "Minas Gerais", "sudeste"), "32": ("ES", "Espírito Santo", "sudeste"),
    "33": ("RJ", "Rio de Janeiro", "sudeste"), "35": ("SP", "São Paulo", "sudeste"),
    "41": ("PR", "Paraná", "sul"), "42": ("SC", "Santa Catarina", "sul"), "43": ("RS", "Rio Grande do Sul", "sul"),
    "50": ("MS", "Mato Grosso do Sul", "centro-oeste"), "51": ("MT", "Mato Grosso", "centro-oeste"),
    "52": ("GO", "Goiás", "centro-oeste"), "53": ("DF", "Distrito Federal", "centro-oeste"),
}


# ── o contorno do IBGE ───────────────────────────────────────────────────────────────────────────────────────────────

class Estado(NamedTuple):
    sigla: str
    nome: str
    regiao: str
    poligonos: tuple          # polígonos; cada um é uma tupla de anéis (o de fora e os buracos); cada anel, de (lon, lat)
    caixa: tuple              # (lon mínima, lat mínima, lon máxima, lat máxima)
    centro: tuple             # (lon, lat) onde escrever a sigla: o centroide do maior pedaço


def _area_do_anel(anel) -> float:
    """Área com sinal (fórmula do cadarço, de Gauss) em graus quadrados; só serve para comparar pedaços e achar o centroide."""
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(anel, anel[1:] + anel[:1])) / 2


def _centroide(anel) -> tuple:
    area = _area_do_anel(anel)
    if abs(area) < 1e-12:                                  # anel sem área: o meio da caixa, em vez de dividir por zero
        xs, ys = [p[0] for p in anel], [p[1] for p in anel]
        return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(anel, anel[1:] + anel[:1]):
        f = x1 * y2 - x2 * y1
        cx += (x1 + x2) * f
        cy += (y1 + y2) * f
    return cx / (6 * area), cy / (6 * area)


def _anel(bruto) -> tuple:
    anel = tuple((float(p[0]), float(p[1])) for p in bruto)
    if len(anel) < 4:
        raise ValueError("anel com menos de 4 pontos")
    return anel


def _estado(codigo: str, geometria: dict) -> Estado:
    tipo, coords = geometria.get("type"), geometria.get("coordinates")
    if tipo == "Polygon":
        brutos = [coords]
    elif tipo == "MultiPolygon":
        brutos = coords
    else:
        raise ValueError(f"o código {codigo} do IBGE não traz Polygon nem MultiPolygon")
    poligonos = tuple(tuple(_anel(a) for a in poligono) for poligono in brutos)
    pontos = [p for poligono in poligonos for anel in poligono for p in anel]
    caixa = (min(p[0] for p in pontos), min(p[1] for p in pontos), max(p[0] for p in pontos), max(p[1] for p in pontos))
    maior = max(poligonos, key=lambda poligono: abs(_area_do_anel(poligono[0])))
    sigla, nome, regiao = UFS[codigo]
    return Estado(sigla, nome, regiao, poligonos, caixa, _centroide(maior[0]))


@lru_cache(maxsize=4)
def estados(arquivo=ARQUIVO_UFS) -> tuple:
    """As 27 UFs do arquivo do IBGE, na ordem dos códigos. Arquivo que não seja isto (código estranho, UF faltando, geometria
    que não é polígono, JSON quebrado) levanta ValueError: um mapa sem um estado é pior que a tela dizer que não abriu."""
    try:
        dados = json.loads(Path(arquivo).read_text(encoding="utf-8"))
        achados = {}
        for f in dados["features"]:
            codigo = str(f["properties"]["codarea"])
            if codigo not in UFS:
                raise ValueError(f"o arquivo do IBGE traz o código {codigo}, que não é de nenhuma UF")
            achados[codigo] = _estado(codigo, f["geometry"])
    except (KeyError, TypeError, AttributeError, IndexError) as e:
        raise ValueError(f"o arquivo do IBGE não tem o formato esperado ({type(e).__name__})") from None
    faltam = [UFS[c][0] for c in UFS if c not in achados]
    if faltam:
        raise ValueError("o arquivo do IBGE não traz: " + ", ".join(faltam))
    return tuple(achados[c] for c in UFS)


# ── a projeção e a vista ─────────────────────────────────────────────────────────────────────────────────────────────

def projetar(lat: float, lon: float, lat_media: float) -> tuple:
    """Equiretangular com a correção do cosseno: (x, y) em graus de latitude. O x encolhe pelo cosseno da latitude média (um
    grau de longitude mede cos(lat) de um de latitude), e o y cresce para baixo, como no SVG."""
    return lon * math.cos(math.radians(lat_media)), -lat


def _n(v: float) -> str:
    """Número do SVG: uma casa (0,1 unidade = ~0,4 km no Brasil inteiro e menos nas regiões), sem ".0" e sem "-0"."""
    s = f"{v:.1f}"
    if s in ("0.0", "-0.0"):
        return "0"
    return s[:-2] if s.endswith(".0") else s


@dataclass(frozen=True)
class Vista:
    """Um recorte do mapa: a caixa em graus (já com a margem) e como ela vira o viewBox "0 0 LARGURA altura"."""
    id: str
    nome: str
    lon_oeste: float
    lon_leste: float
    lat_sul: float
    lat_norte: float
    lat_media: float
    escala: float             # unidades do SVG por grau de latitude
    largura: float
    altura: float
    x0: float                 # o canto de cima, à esquerda, no plano da projeção
    y0: float

    @property
    def viewbox(self) -> str:
        return f"0 0 {_n(self.largura)} {_n(self.altura)}"

    def ponto(self, lat: float, lon: float) -> tuple:
        x, y = projetar(lat, lon, self.lat_media)
        return (x - self.x0) * self.escala, (y - self.y0) * self.escala

    def dentro(self, x: float, y: float, folga: float = 0.0) -> bool:
        """O ponto do SVG cai no viewBox (com `folga` unidades a mais de cada lado)?"""
        return -folga <= x <= self.largura + folga and -folga <= y <= self.altura + folga

    def cruza(self, caixa: tuple) -> bool:
        """A caixa em graus (lon mín., lat mín., lon máx., lat máx.) encosta no recorte?"""
        x0, y0, x1, y1 = caixa
        return not (x1 < self.lon_oeste or x0 > self.lon_leste or y1 < self.lat_sul or y0 > self.lat_norte)


def vista_de_caixa(id_: str, nome: str, lon_min: float, lat_min: float, lon_max: float, lat_max: float,
                   margem: float = MARGEM) -> Vista:
    """O recorte que enquadra a caixa em graus, com `margem` (fração do lado) de folga. A latitude média é a do meio do
    recorte: a escala do x é a que o cosseno dela dá, e o viewBox tem LARGURA de largura."""
    dlon, dlat = (lon_max - lon_min) * margem, (lat_max - lat_min) * margem
    oeste, leste, sul, norte = lon_min - dlon, lon_max + dlon, lat_min - dlat, lat_max + dlat
    lat_media = (sul + norte) / 2
    x0, y0 = projetar(norte, oeste, lat_media)
    x1, _ = projetar(norte, leste, lat_media)
    escala = LARGURA / (x1 - x0)
    return Vista(id_, nome, oeste, leste, sul, norte, lat_media, escala, float(LARGURA), (norte - sul) * escala, x0, y0)


@lru_cache(maxsize=None)
def _vista(chave: str) -> Vista:
    nome = REGIOES.get(chave, "Brasil")
    caixas = [e.caixa for e in estados() if chave == BRASIL or e.regiao == chave]
    return vista_de_caixa(chave, nome, min(c[0] for c in caixas), min(c[1] for c in caixas),
                          max(c[2] for c in caixas), max(c[3] for c in caixas))


def vista(regiao=None) -> Vista:
    """O recorte pedido (`?regiao=`). Vazio, desconhecido ou de outro tipo cai no Brasil, sem erro: o mesmo trato do
    filtro de cliente da tela principal. Caixa e espaço em volta não contam."""
    chave = str(regiao or "").strip().lower()
    return _vista(chave if chave in REGIOES else BRASIL)


# ── o desenho dos estados ────────────────────────────────────────────────────────────────────────────────────────────

def caminho(aneis, v: Vista) -> str:
    """O `d` do SVG para uma lista de anéis de (lon, lat): `M x y l dx dy dx dy ... z` por anel, com os deslocamentos medidos
    do ponto JÁ arredondado anterior (a soma nunca deriva do desenho). Vértices que arredondam para o mesmo ponto saem, e o
    anel que não sobra com 3 pontos não é escrito: um polígono do INMET tem vértice a cada 10 m, e o SVG a 0,4 km por
    unidade só pesaria sem desenhar nada. Os deslocamentos pesam a metade das coordenadas absolutas."""
    partes = []
    for anel in aneis:
        pontos = []
        for lon, lat in anel:
            x, y = v.ponto(lat, lon)
            p = (round(x, 1), round(y, 1))
            if not pontos or p != pontos[-1]:
                pontos.append(p)
        if len(pontos) > 1 and pontos[0] == pontos[-1]:       # o GeoJSON repete o primeiro ponto no fim; o `z` já fecha
            pontos.pop()
        if len(pontos) < 3:
            continue
        anterior, deslocamentos = pontos[0], []
        for p in pontos[1:]:
            deslocamentos.append(f"{_n(p[0] - anterior[0])} {_n(p[1] - anterior[1])}")
            anterior = p
        partes.append(f"M{_n(pontos[0][0])} {_n(pontos[0][1])}l{' '.join(deslocamentos)}z")
    return "".join(partes)


class UfNoMapa(NamedTuple):
    sigla: str
    nome: str
    d: str
    x: str | None             # onde escrever a sigla, ou None se o centro do estado cai fora desta vista
    y: str | None


def _caixa_do_poligono(poligono) -> tuple:
    xs, ys = [p[0] for p in poligono[0]], [p[1] for p in poligono[0]]
    return min(xs), min(ys), max(xs), max(ys)


@lru_cache(maxsize=8)
def ufs_da_vista(v: Vista) -> tuple:
    """Os estados que aparecem no recorte, com o caminho de cada um (só os pedaços que o recorte encosta) e o ponto da
    sigla. Calculado uma vez por vista: o contorno não muda."""
    saida = []
    for e in estados():
        if not v.cruza(e.caixa):
            continue
        d = "".join(caminho(p, v) for p in e.poligonos if v.cruza(_caixa_do_poligono(p)))
        if not d:
            continue
        x, y = v.ponto(e.centro[1], e.centro[0])
        com_rotulo = v.dentro(x, y)
        saida.append(UfNoMapa(e.sigla, e.nome, d, _n(x) if com_rotulo else None, _n(y) if com_rotulo else None))
    return tuple(saida)
