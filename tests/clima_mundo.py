"""O "mundo inventado" das telas do Clima e risco (06/10/2026): sete usinas numa grade de 40 x 30 pixels, um aviso do INMET por cima de
duas delas, um foco perto de uma, o risco de fogo em quatro dias e, para a página da usina, uma NASA POWER de mentira. Tudo por
sessão falsa (nenhum teste vai à rede) e relógio de mentira. Importado por `test_torre_performance_clima.py` e
`test_torre_performance_clima_usina.py` (os fixtures vêm junto)."""
import json
import re
from datetime import date, datetime, timedelta, timezone

import pytest

from nexus import create_app
from nexus.cadastro.cifra import gerar_chave
from nexus.cadastro.servico import Carga
from nexus.performance.clima import leitura as L
from nexus.performance.clima import visao as V

from clima_cog import SessaoArquivos, montar_cog
from clima_power import SessaoPower
from conftest import SENHA_TESTE

BRT = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 10, 6, 15, 0, tzinfo=BRT)
URL_INMET = "https://inmet.exemplo.test/ativos"
BASE_FOCOS = "https://inpe.exemplo.test/focos/"
RISCO = "https://inpe.exemplo.test/risco/RF.PREV.T{d}.tif"
URL_POWER = ("https://power.exemplo.test/api/temporal/daily/point?parameters=ALLSKY_SFC_SW_DWN&community=RE"
             "&longitude={lon}&latitude={lat}&start={inicio}&end={fim}&format=JSON")
BASE_FIRMS = "https://firms.exemplo.test/active_fire/"
CAB_VIIRS = "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight"
CAB_MODIS = "latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,confidence,version,bright_t31,frp,daynight"
X0, Y0, D = -45.0, -5.0, 0.01


def centro(col, lin):
    """(lat, lon) do centro do pixel; o cadastro de teste usa estes pontos."""
    return Y0 - (lin + 0.5) * D, X0 + (col + 0.5) * D


# coluna e linha de cada usina na grade do INPE
A, B, C, DD, F, G = (5, 5), (10, 10), (15, 15), (20, 20), (25, 25), (35, 5)


def caixa_aviso(id_, nome, severidade, lon0, lon1, lat0, lat1, evento="Tempestade", inicio="2026-10-06 09:10",
                fim="2026-10-06 23:59"):
    ring = [[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]
    return {"id": id_, "descricao": evento or nome, "severidade": severidade, "inicio": inicio, "fim": fim,
            "poligono": json.dumps({"type": "Polygon", "coordinates": [ring]})}


def inmet(extra_hoje=(), extra_futuro=()):
    # nível 1 (Baixa Umidade) sobre A e B; nível 2 (Tempestade) só sobre A
    leve = caixa_aviso(1, "leve", "Perigo Potencial", -45.0, -44.88, -5.15, -5.0, evento="Baixa Umidade")
    forte = caixa_aviso(2, "forte", "Perigo", -45.0, -44.93, -5.08, -5.02)
    return json.dumps({"hoje": [leve, forte, *extra_hoje], "futuro": list(extra_futuro)}).encode()


def nome_foco(hh, mm):
    return f"focos_10min_20261006_{hh:02d}{mm:02d}.csv"


def focos():
    lat_a, lon_a = centro(*A)
    perto = f"{lat_a + 1.2 / 111.195:.6f}, {lon_a:.6f},GOES-19,2026-10-06 17:50:00"           # 1,2 km de A (14:50 em Brasília)
    longe = "-9.000000, -40.000000,NOAA-21,2026-10-06 17:40:00"
    arquivos = {nome_foco(17, 50): ("lat,lon,satelite,data\n" + perto + "\n" + longe + "\n").encode()}
    indice = "".join(f'<a href="{n}">{n}</a>' for n in arquivos).encode()
    return {BASE_FOCOS: indice, **{BASE_FOCOS + n: c for n, c in arquivos.items()}}


def firms(linhas_viirs=()):
    """Os quatro arquivos do FIRMS (10/10/2026): lidos, cada um com um foco longe de tudo e recente (o mundo padrão é "a NASA não viu
    fogo perto"); `linhas_viirs` entram no arquivo do NOAA-20."""
    from nexus.performance.clima.fontes import FIRMS_ARQUIVOS
    longe_viirs = "-9.00000,-40.00000,330.0,0.40,0.40,2026-10-06,1630,{sat},nominal,2.0NRT,295.0,3.10,D"
    longe_modis = "-9.10000,-40.10000,320.0,1.00,1.00,2026-10-06,1600,A,70,6.1NRT,300.0,8.20,D"
    a = {}
    for sat, caminho in FIRMS_ARQUIVOS.items():
        if sat == "MODIS":
            corpo = CAB_MODIS + "\n" + longe_modis + "\n"
        else:
            codigo = {"S-NPP": "N", "NOAA-20": "N20", "NOAA-21": "N21"}[sat]
            extra = "".join(l + "\n" for l in linhas_viirs) if sat == "NOAA-20" else ""
            corpo = CAB_VIIRS + "\n" + longe_viirs.format(sat=codigo) + "\n" + extra
        a[BASE_FIRMS + caminho] = corpo.encode()
    return a


def grade_risco(dia):
    g = [[0.05] * 40 for _ in range(30)]
    g[A[1]][A[0]] = 0.97
    g[B[1]][B[0]] = 0.30
    g[C[1]][C[0]] = [0.75, 0.80, 0.60, 0.40][dia]
    g[DD[1]][DD[0]] = 0.10
    g[F[1]][F[0]] = None                                       # pixel mascarado; só o vizinho tem valor
    g[F[1]][F[0] + 1] = 0.85
    for dl in range(-2, 3):                                    # G: nada de dado num raio de 2 pixels
        for dc in range(-2, 3):
            g[G[1] + dl][G[0] + dc] = None
    return g


def arquivos_do_mundo(inmet_bytes=None, risco=True, nasa=True):
    a = {URL_INMET: inmet_bytes if inmet_bytes is not None else inmet(), **focos(), **(firms() if nasa else {})}
    if risco:
        for d in range(4):
            a[RISCO.format(d=d)] = montar_cog(grade_risco(d), origem=(X0, Y0), escala=D)
    return a


def u(id_, nome, cliente, pos, uf="PI"):
    v = {"nome": nome, "status": "OPERAÇÃO", "cliente": cliente, "uf": uf, "cidade": "Cidade"}
    if pos:
        v["latitude"], v["longitude"] = centro(*pos)
    return {"id": id_, "ordem": int(id_), "valores": v}


def carga():
    return Carga(
        entidades={
            "clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Cliente X"}},
                         {"id": "2", "ordem": 2, "valores": {"nome": "Cliente Y"}}],
            "usinas": [u("1", "Usina Alfa", "1", A), u("2", "Usina Beta", "1", B), u("3", "Usina Gama", "2", C),
                       u("4", "Usina Delta", "2", DD), u("5", "Usina Epsilon", "1", None), u("6", "Usina Zeta", "2", F),
                       u("7", "Usina Eta", "1", G)],
        },
        listas={"status_usina": ["OPERAÇÃO"], "uf": ["PI"]})


class Relogio:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


class SessaoMista:
    """Uma sessão só para as quatro fontes: o que é da NASA (o endereço de mentira `URL_POWER`) vai para a NASA de mentira, o resto
    para os arquivos do INMET e do INPE."""

    def __init__(self, arquivos, power):
        self.arquivos, self.power = arquivos, power

    def get(self, url, **kw):
        return (self.power if url.startswith("https://power.exemplo.test/") else self.arquivos).get(url, **kw)


def _mundo(tmp_path, monkeypatch, carga_, arquivos, power=None):
    chave = gerar_chave()
    app = create_app({"NEXUS_SECRET_KEY": "k", "NEXUS_SENHA_ADMIN": SENHA_TESTE, "NEXUS_CHAVE_CADASTRO": chave,
                      "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "cadastro.json"),
                      "NEXUS_CLIMA_INMET_URL": URL_INMET, "NEXUS_CLIMA_FOCOS_URL": BASE_FOCOS, "NEXUS_CLIMA_RISCO_URL": RISCO,
                      "NEXUS_CLIMA_POWER_URL": URL_POWER, "NEXUS_CLIMA_FIRMS_URL": BASE_FIRMS})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    with app.app_context():
        from nexus.cadastro.telas import servico
        servico().aplicar_carga(carga_)
    sessao = SessaoArquivos(arquivos)
    L.limpar_cache()
    L.usar_relogio(Relogio(AGORA.timestamp()))
    L.usar_sessao(SessaoMista(sessao, power) if power is not None else sessao)
    monkeypatch.setattr(V, "agora", lambda: AGORA)
    cliente = app.test_client()
    assert cliente.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return cliente, sessao, app


@pytest.fixture
def mundo(tmp_path, monkeypatch):
    yield _mundo(tmp_path, monkeypatch, carga(), arquivos_do_mundo())
    L.usar_sessao(None)
    L.usar_relogio(None)
    L.limpar_cache()


def carga_de_25():
    """25 usinas na mesma faixa de pixels (linha 22), todas debaixo de UM aviso Perigo Potencial e com risco baixo."""
    usinas = [u(str(i), f"Usina {i:02d}", "1", (i - 1, 22)) for i in range(1, 26)]
    return Carga(entidades={"clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Cliente X"}}], "usinas": usinas},
                 listas={"status_usina": ["OPERAÇÃO"], "uf": ["PI"]})


@pytest.fixture
def mundo25(tmp_path, monkeypatch):
    sobre_todas = caixa_aviso(1, "leve", "Perigo Potencial", -45.0, -44.70, -5.30, -5.20, evento="Baixa Umidade")
    yield _mundo(tmp_path, monkeypatch, carga_de_25(), arquivos_do_mundo(json.dumps({"hoje": [sobre_todas], "futuro": []}).encode()))
    L.usar_sessao(None)
    L.usar_relogio(None)
    L.limpar_cache()


def pagina(c, url="/t/performance/clima", **consulta):
    r = c.get(url, query_string=consulta or None)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def texto(html):
    """O texto visível, sem marcação, para conferir frases."""
    sem_css = re.sub(r"<(style|script)\b.*?</\1>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", sem_css))


PUBLICADO_ATE = date(2026, 10, 2)


@pytest.fixture
def mundo_usina(tmp_path, monkeypatch):
    """O mesmo `mundo`, mais a NASA de mentira (a série vai até 02/10; em outubro o valor de cada dia é o seu número, 1,0 em 01/10 e
    2,0 em 02/10, e antes disso é 4,0 todo dia, dentro do que o cliente aceita): devolve (cliente, sessão dos arquivos, app, NASA)."""
    power = SessaoPower(PUBLICADO_ATE, valor=lambda d: float(d.day) if d.month == 10 else 4.0)
    yield (*_mundo(tmp_path, monkeypatch, carga(), arquivos_do_mundo(), power), power)
    L.usar_sessao(None)
    L.usar_relogio(None)
    L.limpar_cache()
