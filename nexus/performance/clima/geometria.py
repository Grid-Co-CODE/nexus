"""Geometria sem dependência: ponto em polígono do INMET e distância entre dois pontos.

Por que não shapely: o Nexus não ganha dependência para isto (Levi/controle, 06/10/2026). O aviso do INMET chega como
GeoJSON `Polygon` (anel de fora + buracos) e pode vir `MultiPolygon`; um par-ímpar com borda resolve os dois.

Coordenadas na ordem do GeoJSON: x = longitude, y = latitude.
"""
import math

RAIO_TERRA_KM = 6371.0          # o mesmo do pacote de referência (gridco_meteo/alertas.py)
_EPS = 1e-12

FORA, DENTRO, BORDA = 0, 1, 2


def distancia_km(lat1, lon1, lat2, lon2) -> float:
    """Haversine: distância em linha reta sobre a esfera, em km."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * RAIO_TERRA_KM * math.asin(min(1.0, math.sqrt(a)))


def _sobre_o_segmento(x, y, x1, y1, x2, y2) -> bool:
    if abs((x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)) > _EPS:
        return False
    return min(x1, x2) - _EPS <= x <= max(x1, x2) + _EPS and min(y1, y2) - _EPS <= y <= max(y1, y2) + _EPS


def _no_anel(x, y, anel) -> int:
    """FORA, DENTRO ou BORDA. Par-ímpar com o raio para a direita; `(y1 > y) != (y2 > y)` conta o vértice por cima só
    uma vez (o raio que passa justo por um vértice é o caso que erra o par-ímpar ingênuo)."""
    dentro = False
    x2, y2 = anel[-1][0], anel[-1][1]
    for ponto in anel:
        x1, y1 = x2, y2
        x2, y2 = ponto[0], ponto[1]
        if _sobre_o_segmento(x, y, x1, y1, x2, y2):
            return BORDA
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            dentro = not dentro
    return DENTRO if dentro else FORA


def _no_poligono(x, y, aneis) -> bool:
    """O primeiro anel é o de fora, os outros são buracos. A borda de qualquer anel conta como dentro."""
    if not aneis:
        return False
    de_fora = _no_anel(x, y, aneis[0])
    if de_fora == FORA:
        return False
    if de_fora == BORDA:
        return True
    return all(_no_anel(x, y, buraco) != DENTRO for buraco in aneis[1:])


def _poligonos(geometria):
    """Os polígonos (listas de anéis) de um `Polygon` ou `MultiPolygon`; qualquer outra coisa não tem polígono."""
    if not isinstance(geometria, dict):
        return []
    tipo, coords = geometria.get("type"), geometria.get("coordinates")
    if tipo == "Polygon" and isinstance(coords, list):
        return [coords]
    if tipo == "MultiPolygon" and isinstance(coords, list):
        return [p for p in coords if isinstance(p, list)]
    return []


def contem(geometria, lon, lat) -> bool:
    """O ponto está dentro (ou na borda) do `Polygon`/`MultiPolygon`? Outra geometria não contém nada."""
    try:
        return any(_no_poligono(lon, lat, p) for p in _poligonos(geometria))
    except (TypeError, IndexError, ValueError):
        return False


def caixa(geometria) -> tuple:
    """(lon mínima, lat mínima, lon máxima, lat máxima). Levanta ValueError se a geometria não for um polígono bem
    formado: quem lê o aviso conta o ignorado, em vez de deixar um aviso sem forma passar por "sem alerta"."""
    poligonos = _poligonos(geometria)
    if not poligonos:
        raise ValueError("geometria sem Polygon nem MultiPolygon")
    xs, ys = [], []
    for aneis in poligonos:
        if not aneis:
            raise ValueError("polígono sem anel")
        for anel in aneis:
            if not isinstance(anel, list) or len(anel) < 3:
                raise ValueError("anel com menos de 3 pontos")
            for ponto in anel:
                if (not isinstance(ponto, (list, tuple)) or len(ponto) < 2
                        or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                                   for v in ponto[:2])):
                    raise ValueError("ponto fora do formato [lon, lat]")
                xs.append(ponto[0])
                ys.append(ponto[1])
    return min(xs), min(ys), max(xs), max(ys)
