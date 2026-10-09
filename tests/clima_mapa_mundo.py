"""O mundo inventado do Mapa de risco, para os testes do modelo (`test_clima_mapa_camadas`) e da tela
(`test_torre_performance_mapa`) falarem do mesmo lugar: seis usinas em pontos do Brasil que não são de usina nenhuma
(repositório público), com avisos e focos postos de propósito em cima delas. Leituras prontas no lugar das fontes."""
import math
from datetime import datetime, timedelta, timezone

from nexus.performance.clima import geometria
from nexus.performance.clima import leitura as L
from nexus.performance.clima import mapa as M
from nexus.performance.clima.fontes import Aviso, Foco
from nexus.performance.clima.geotiff import Amostra
from nexus.performance.clima.usinas import Cadastro, Usina

BRT = timezone(timedelta(hours=-3))
UTC = timezone.utc
REF = datetime(2026, 10, 7, 15, 0, tzinfo=BRT)
LIDO = REF.timestamp()
UM_GRAU = 111.195

# Posições inventadas, com casas de sobra: o teste que procura coordenada impressa na tela acha o número inteiro (3 casas ou mais).
ALFA = (-7.50417, -41.50342)       # Nordeste
BETA = (-7.60283, -41.40519)       # Nordeste, a ~15 km da Alfa
GAMA = (-28.00461, -52.00127)      # Sul
DELTA = (-20.00538, -45.00269)     # Sudeste
EPSILON = (-3.00718, -60.00391)    # Norte
TETA = (-23.00826, -46.00154)      # Sudeste


def usina(id_, nome, pos, cliente="Cliente X", uf="PI"):
    return Usina(id_, nome, cliente, uf, "Cidade", pos[0], pos[1])


def mundo_de_usinas():
    return [usina("1", "Usina Alfa", ALFA), usina("2", "Usina Beta", BETA), usina("3", "Usina Gama", GAMA),
            usina("4", "Usina Delta", DELTA), usina("5", "Usina Epsilon", EPSILON), usina("6", "Usina Teta", TETA)]


def cadastro(*usinas, sem=(), fora=()):
    return Cadastro(list(usinas), list(sem), list(fora), len(usinas) + len(sem) + len(fora))


def em_volta(pos, meia=0.03):
    lat, lon = pos
    return {"type": "Polygon", "coordinates": [[[lon - meia, lat - meia], [lon + meia, lat - meia], [lon + meia, lat + meia],
                                                [lon - meia, lat + meia], [lon - meia, lat - meia]]]}


def aviso(nivel, evento, pos, inicio=None, fim=None, quando="hoje", id_=None, geo=None):
    sev = {1: "Perigo Potencial", 2: "Perigo", 3: "Grande Perigo"}[nivel]
    geo = geo or em_volta(pos)
    return Aviso(id_ or f"{evento}-{pos}", quando, evento, sev, nivel, inicio or REF - timedelta(hours=1),
                 fim or REF + timedelta(hours=8), geo, geometria.caixa(geo))


def lei_avisos(*avisos, ignorados=()):
    return L.Leitura({"avisos": list(avisos), "ignorados": list(ignorados), "lidos": len(avisos)}, LIDO)


def foco_a(km, pos, sat="GOES-19", dlon_km=0.0, hh=17):
    lat, lon = pos
    return Foco(lat + km / UM_GRAU, lon + dlon_km / (UM_GRAU * math.cos(math.radians(lat))), sat,
                datetime(2026, 10, 7, hh, 50, tzinfo=UTC))


def foco_em(lat, lon, sat="NOAA-21"):
    return Foco(lat, lon, sat, datetime(2026, 10, 7, 17, 40, tzinfo=UTC))


def lei_focos(*focos, ate=None, falhos=(), ruins=0):
    ate = ate or datetime(2026, 10, 7, 17, 50, tzinfo=UTC)
    return L.Leitura({"focos": list(focos), "arquivos": ["a.csv"], "falhos": list(falhos), "ate": ate, "linhas_ruins": ruins}, LIDO)


def lei_risco(por_ponto, arquivos=None, erros=None):
    arquivos = {0: datetime(2026, 10, 7, 9, 32, tzinfo=UTC)} if arquivos is None else arquivos
    return L.Leitura({"por_ponto": por_ponto, "arquivos": arquivos, "erros": erros or {}}, LIDO)


def dias(*valores, origem="ponto"):
    return [Amostra(v, origem if v is not None else "sem_dado") for v in valores]


def risco_baixo(ids=("1", "2", "3", "4", "5", "6")):
    return {i: dias(0.1, 0.1, 0.1, 0.1) for i in ids}


def instalar_leituras(monkeypatch):
    """O `instalar(avisos, focos, risco, grade)` das leituras prontas: as fontes do `leitura.py` passam a devolver o que o teste
    manda (o que não vier é "fonte fora"), sem rede. `grade` é o mapa de calor do risco de fogo (09/10/2026), uma Leitura ou um
    {dia: Leitura}. Cada teste o embrulha numa fixture `leituras`. Devolve a lista das fontes que foram pedidas."""
    chamadas = []

    def instalar(avisos=None, focos=None, risco=None, grade=None):
        vazio = L.Leitura(None, None, erro="sem fonte nos testes")
        monkeypatch.setattr(L, "avisos", lambda config, sessao=None: chamadas.append("avisos") or avisos or vazio)
        monkeypatch.setattr(L, "focos", lambda config, sessao=None: chamadas.append("focos") or focos or vazio)
        monkeypatch.setattr(L, "risco", lambda config, pontos, sessao=None: chamadas.append("risco") or risco or vazio)

        def da_grade(config, dia, caixa, precisa=None, sessao=None):
            chamadas.append(f"grade{dia}")
            g = grade.get(dia) if isinstance(grade, dict) else grade
            return g or vazio
        monkeypatch.setattr(L, "risco_grade", da_grade)
        return chamadas
    return instalar


def lei_grade(valor, caixa=(-46.0, -24.0, -36.0, -4.0), passo=0.08, modificado=None, vence_em=None, **kw):
    """O mapa de calor do risco de fogo pronto: blocos de `passo` graus na `caixa`, cada um com 64 pixels e o valor `valor(lat, lon)`
    (None = sem dado). `modificado`: a data do arquivo do INPE (padrão: hoje, 06:32)."""
    from array import array
    lon0, lat0, lon1, lat1 = caixa
    ncols, nrows = round((lon1 - lon0) / passo), round((lat1 - lat0) / passo)
    soma, n = array("d", [0.0]) * (ncols * nrows), array("I", [0]) * (ncols * nrows)
    for r in range(nrows):
        for c in range(ncols):
            v = valor(lat1 - (r + 0.5) * passo, lon0 + (c + 0.5) * passo)
            if v is not None:
                soma[r * ncols + c], n[r * ncols + c] = 64 * v, 64
    blocos = {"oeste": lon0, "norte": lat1, "dlon": passo, "dlat": passo, "ncols": ncols, "nrows": nrows, "soma": soma, "n": n,
              "px_por_bloco": 64, "tiles": 1, "bytes": 1}
    modificado = modificado or datetime(2026, 10, 7, 9, 32, tzinfo=UTC)
    return L.Leitura({"modificado": modificado, "validador": "teste", "url": "u", "grade": blocos, "conferido": False}, LIDO,
                     vence_em=vence_em, **kw)


def tudo_instalado(leituras, avisos=None, focos=None, risco=None):
    """O mundo completo: as três fontes lidas. O que não vem é "nada a avisar" (e não "fonte fora")."""
    return leituras(avisos=avisos or lei_avisos(), focos=focos or lei_focos(), risco=risco or lei_risco(risco_baixo()))


def por_nome(m):
    return {u["nome"]: u for u in m["usinas"]}


def montar(**kw):
    kw.setdefault("cadastro", cadastro(*mundo_de_usinas()))
    kw.setdefault("ref", REF)
    return M.montar({}, **kw)


def mundo_completo(leituras):
    """O mundo de todos os testes de camada: Alfa em Grande Perigo e Beta em Perigo (Baixa Umidade) no Nordeste, Gama com um aviso
    que ainda vai começar, dois focos a menos de 5 km da Delta e dois longe de tudo, e risco de fogo alto hoje na Epsilon."""
    return tudo_instalado(
        leituras,
        avisos=lei_avisos(aviso(3, "Vendaval", ALFA), aviso(2, "Baixa Umidade", BETA),
                          aviso(1, "Onda de Calor", GAMA, inicio=REF + timedelta(days=1), fim=REF + timedelta(days=2),
                                quando="futuro")),
        focos=lei_focos(foco_a(1.0, DELTA), foco_a(3.0, DELTA, "NOAA-21", dlon_km=1.0), foco_em(-3.0, -61.0),
                        foco_em(-9.0, -40.0)),
        risco=lei_risco({**risco_baixo(), "5": dias(0.8, 0.1, 0.1, 0.1)}))


def quebrar_contorno(monkeypatch, erro=None):
    """O arquivo do IBGE some ou vem quebrado: `estados()` levanta (ValueError se o conteúdo não é o esperado, FileNotFoundError se
    o arquivo não está lá). As vistas e os estados são guardados (lru_cache), então limpa antes: sem isso o teste herdaria o
    resultado de outro. Quem chama limpa de novo no fim (a fixture do teste)."""
    erro = erro or ValueError("o arquivo do IBGE não traz: RS")

    def quebrado(*args, **kwargs):
        raise erro
    M._vista.cache_clear()
    M.ufs_da_vista.cache_clear()
    monkeypatch.setattr(M, "estados", quebrado)
