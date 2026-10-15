"""O mapa do Acompanhamento do PCM: as usinas do cadastro no desenho do Brasil, sem que a coordenada saia do servidor.

No painel do PCM a latitude e a longitude iam para o navegador, que desenhava o mapa e media a distância. No Nexus a
coordenada é campo sensível do cadastro (cifrada no armazém; a regra está em `nexus/performance/CLAUDE.md`, seção do
Mapa de risco: "o NÚMERO de latitude ou longitude nunca vira texto"). Então o servidor entrega o desenho pronto (o
contorno dos estados e o ponto de cada usina, na MESMA projeção do Mapa de risco, `performance/clima/mapa.py`) e a
distância já medida (`km`, `perto`): o navegador nunca recebe a coordenada.

A usina do Fracttal ("Thopen - Altair 1 - SP") acha a do cadastro pelo de-para publicado (sistema "Fracttal ·
Classificação 1", o mesmo que liga as telas do Campo) e, sem ele, pelo nome ("Cliente - Usina", sem a UF).
"""
import math
import re

from ...performance.clima import mapa as M
from .dados import norm

R_TERRA_KM = 6371.0


def _sem_uf(nome: str) -> str:
    return re.sub(r"\s*-\s*[A-Z]{2}\s*$", "", str(nome or "")).strip()


def haversine(a: tuple, b: tuple) -> float:
    (la1, lo1), (la2, lo2) = a, b
    p = math.pi / 180
    s = math.sin((la2 - la1) * p / 2) ** 2 + math.cos(la1 * p) * math.cos(la2 * p) * math.sin((lo2 - lo1) * p / 2) ** 2
    return 2 * R_TERRA_KM * math.asin(math.sqrt(s))


class Geo:
    """`usinas` = as do cadastro em operação com coordenada (`performance.clima.usinas.Usina`: id, nome, cliente, lat,
    lon); `por_fracttal` = {nome do Fracttal normalizado: usina_id} do de-para publicado."""

    def __init__(self, usinas: list, por_fracttal: dict, fracttal_de: dict | None = None):
        self._por_id = {str(u.id): u for u in usinas}
        self._por_nome = {norm(f"{u.cliente} - {u.nome}"): u for u in usinas}
        self._por_fracttal = {k: str(v) for k, v in (por_fracttal or {}).items()}
        # o nome do Fracttal de cada usina do cadastro (para listar as que não têm carga com o mesmo nome das outras)
        self._nome_fracttal = dict(fracttal_de or {})
        self._vista = M.vista()

    def _usina(self, nome: str):
        u = self._por_id.get(self._por_fracttal.get(norm(nome), ""))
        return u or self._por_nome.get(norm(_sem_uf(nome)))

    def _coord(self, nome: str):
        u = self._usina(nome)
        return (u.lat, u.lon) if u and u.lat is not None and u.lon is not None else None

    def ponto(self, nome: str) -> list | None:
        """[x, y] da usina no desenho (o viewBox do `desenho`), ou None sem coordenada no cadastro."""
        c = self._coord(nome)
        if not c:
            return None
        x, y = self._vista.ponto(c[0], c[1])
        return [round(x, 1), round(y, 1)]

    def nomes(self) -> list[str]:
        """As usinas do cadastro com coordenada, pelo nome do Fracttal quando o de-para o tem ("Cliente - Usina")."""
        return [self._nome_fracttal.get(str(u.id)) or f"{u.cliente} - {u.nome}" for u in self._por_id.values()]

    def km(self, a: str, b: str) -> float | None:
        ca, cb = self._coord(a), self._coord(b)
        return round(haversine(ca, cb), 1) if ca and cb else None

    def perto(self, a: str, candidatas: list[str], n: int = 6) -> list[dict]:
        """As `n` usinas de `candidatas` mais perto de `a`, em linha reta: [{"usina", "km"}]."""
        ca = self._coord(a)
        if not ca:
            return []
        out = []
        for c in candidatas:
            if c == a:
                continue
            cc = self._coord(c)
            if cc:
                out.append({"usina": c, "km": round(haversine(ca, cc), 1)})
        return sorted(out, key=lambda x: x["km"])[:n]

    def desenho(self) -> dict:
        """O contorno dos estados na vista do Brasil: {"viewbox", "ufs": [{"d", "sigla", "regiao", "x", "y"}]}."""
        regiao = {e.sigla: e.regiao for e in M.estados()}
        return {"viewbox": self._vista.viewbox,
                "ufs": [{"d": u.d, "sigla": u.sigla, "regiao": regiao.get(u.sigla, ""), "x": u.x, "y": u.y}
                        for u in M.ufs_da_vista(self._vista)]}
