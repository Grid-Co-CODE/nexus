"""Mapa de equipe: os deslocamentos entre usinas, calculados dos pontos (sem coordenada na saída).

Regra (08/11/2026): por pessoa, os pontos em ordem de hora. O ponto está "na usina U" quando cai a até RAIO_USINA_KM da
coordenada de U (a mais próxima, se mais de uma couber no raio). O deslocamento A -> B vai do ÚLTIMO ponto em A até o 1º
ponto em B (B diferente de A). Voltar à mesma usina não é deslocamento, e ponto que nunca esteve numa usina não gera
nada. O id é um hash do que identifica o trecho (pessoa, saída, as duas usinas): recalcular o mês e republicar não
duplica linha. O livro é o do mês da CHEGADA (hora de Brasília).
"""
import hashlib
import math
from datetime import datetime, timedelta, timezone

from nexus.campo.equipe import CAB_DESLOC, RAIO_USINA_KM

_BRT = timezone(timedelta(hours=-3))
_R_TERRA_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    f1, f2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((f2 - f1) / 2) ** 2
         + math.cos(f1) * math.cos(f2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * _R_TERRA_KM * math.asin(min(1.0, math.sqrt(a)))


def _instante(texto: str) -> datetime:
    return datetime.strptime(texto, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _usina_do_ponto(p: dict, usinas: dict, raio_km: float):
    melhor, menor = None, raio_km
    for uid, (lat, lon, *_resto) in usinas.items():
        d = haversine_km(p["lat"], p["lon"], lat, lon)
        if d <= menor:
            melhor, menor = uid, d
    return melhor


def deslocamento_id(pessoa_id, saida: str, usina_saida, usina_chegada) -> str:
    # letra + hexadecimal: a API do banco infere o tipo da coluna e só algarismos voltaria número
    h = hashlib.sha1(f"{pessoa_id}|{saida}|{usina_saida}|{usina_chegada}".encode("utf-8")).hexdigest()
    return "D" + h[:11]


def deslocamentos(pontos: list[dict], usinas: dict, raio_km: float = RAIO_USINA_KM) -> list[list]:
    """Linhas de CAB_DESLOC. `pontos`: dicts com pessoa_id, instante (UTC, com Z), lat e lon. `usinas`:
    {usina_id: (lat, lon, uf)}."""
    por_pessoa: dict = {}
    for p in pontos:
        por_pessoa.setdefault(p["pessoa_id"], []).append(p)
    linhas = []
    for pessoa_id, lista in por_pessoa.items():
        lista.sort(key=lambda p: p["instante"])
        ultimo = None                        # (usina, índice do último ponto nela)
        for i, p in enumerate(lista):
            u = _usina_do_ponto(p, usinas, raio_km)
            if u is None:
                continue
            if ultimo is not None and ultimo[0] != u:
                j = ultimo[1]
                trecho = lista[j:i + 1]
                km = sum(haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) for a, b in zip(trecho, trecho[1:]))
                saida, chegada = lista[j]["instante"], p["instante"]
                min_ = round((_instante(chegada) - _instante(saida)).total_seconds() / 60)
                d = {"deslocamento_id": deslocamento_id(pessoa_id, saida, ultimo[0], u),
                     "data_id": int(_instante(chegada).astimezone(_BRT).strftime("%Y%m%d")),
                     "pessoa_id": pessoa_id, "usina_id_saida": int(ultimo[0]), "usina_id_chegada": int(u),
                     "saida": saida, "chegada": chegada, "duracao_min": int(min_), "distancia_km": round(km, 1)}
                linhas.append([d[c] for c in CAB_DESLOC])
            ultimo = (u, i)
    return linhas
