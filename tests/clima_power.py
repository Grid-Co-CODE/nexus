"""NASA POWER de mentira (07/10/2026): a mesma forma da resposta real medida ao vivo no dia (`properties.parameter.
ALLSKY_SFC_SW_DWN`, as unidades em `parameters`, `-999` nos dias ainda não publicados e num buraco no meio da série).

Nenhum teste vai à rede: a sessão devolve uma série inventada para a janela que o pedido pede (lida da própria URL).
"""
import json
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

from clima_cog import Resposta

UNIDADE = "kW-hr/m^2/day"


def corpo_power(serie: dict, *, unidade=UNIDADE, fill=-999.0, sem_unidade=False, **extra) -> bytes:
    """O JSON como a NASA manda. `serie`: {"AAAAMMDD": valor}."""
    dias = sorted(serie)
    js = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [-47.93, -15.78, 984.96]},
          "properties": {"parameter": {"ALLSKY_SFC_SW_DWN": serie}},
          "header": {"title": "NASA/POWER Source Native Resolution Daily Data", "api": {"version": "v2.10.0", "name": "POWER Daily API"},
                     "sources": ["FLASHFLUX"], "fill_value": fill, "time_standard": "LST",
                     "start": dias[0] if dias else "", "end": dias[-1] if dias else ""},
          "messages": [], "times": {"data": 0.049, "process": 0.01}}
    if not sem_unidade:
        js["parameters"] = {"ALLSKY_SFC_SW_DWN": {"units": unidade, "longname": "All Sky Surface Shortwave Downward Irradiance"}}
    js.update(extra)
    return json.dumps(js).encode()


def valor_padrao(d: date) -> float:
    """Um GHI que muda de dia para dia (4,0 a 6,4), sempre dentro do que o Brasil vê."""
    return round(4.0 + (d.toordinal() % 9) * 0.3, 4)


class SessaoPower:
    """Serve a série de `valor(d)` para a janela `start`..`end` do pedido, -999 depois de `publicado_ate` e nos `buracos`.
    `status`/`corpo` forçam outra resposta; `erro` levanta no `get` (rede caída)."""

    def __init__(self, publicado_ate: date, *, valor=valor_padrao, buracos=(), status=200, corpo=None, erro=None,
                 atraso_s=0.0, ao_pedir=None):
        self.publicado_ate, self.valor, self.buracos = publicado_ate, valor, set(buracos)
        self.status, self.corpo, self.erro = status, corpo, erro
        self.atraso_s, self.ao_pedir = atraso_s, ao_pedir
        self.pedidos = []                                   # as URLs, na ordem

    def serie(self, inicio: date, fim: date) -> dict:
        saida, d = {}, inicio
        while d <= fim:
            sem = d > self.publicado_ate or d in self.buracos
            saida[d.strftime("%Y%m%d")] = -999.0 if sem else self.valor(d)
            d += timedelta(days=1)
        return saida

    def get(self, url, params=None, headers=None, timeout=None):
        self.pedidos.append(url)
        if self.ao_pedir:
            self.ao_pedir(url)
        if self.atraso_s:
            import time
            time.sleep(self.atraso_s)
        if self.erro is not None:
            raise self.erro
        if self.status != 200 or self.corpo is not None:
            return Resposta(self.status, self.corpo if self.corpo is not None else b'{"messages": ["erro"]}')
        q = parse_qs(urlsplit(url).query)
        if "start" in q:
            inicio = datetime.strptime(q["start"][0], "%Y%m%d").date()
            fim = datetime.strptime(q["end"][0], "%Y%m%d").date()
        else:                                                # endereço trocado por um espelho: devolve os dois últimos dias
            inicio, fim = self.publicado_ate - timedelta(days=1), self.publicado_ate
        return Resposta(200, corpo_power(self.serie(inicio, fim)), {"Content-Type": "application/json"})

    def consulta(self, i=-1) -> dict:
        """Os parâmetros do pedido `i`, como a NASA os recebe: {nome: valor}."""
        return {k: v[0] for k, v in parse_qs(urlsplit(self.pedidos[i]).query).items()}
