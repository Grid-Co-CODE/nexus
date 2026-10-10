"""Os clientes públicos do Clima e risco: avisos do INMET, focos de queimada do INPE, risco de fogo do INPE, a irradiação diária
da NASA POWER e, desde 10/10/2026, o fogo das últimas 24 h dos satélites da NASA (FIRMS), com a força e a confiança de cada foco.

Todos são só leitura (GET), sem chave e de uso livre; o formato abaixo é o medido em 06/10/2026 (a NASA POWER, em 07/10), e o
que fugir dele vira `FonteErro` (a tela diz que a fonte falhou) em vez de número lido do jeito errado. Quem recebe a sessão é
quem chama: a sessão de verdade em produção, uma falsa nos testes (nenhum teste vai à rede).

Atribuição que a tela mostra no rodapé: o nome de cada fonte por extenso, com a sigla (`NOMES`, abaixo), o Programa Queimadas
do INPE e "NASA LaRC POWER" na página da usina. O endereço do INMET não é documentado oficialmente (é o que o próprio site de
avisos usa); se ele sumir, a tela mostra o INMET como fora do ar.
"""
import csv
import io
import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import NamedTuple

import requests

from . import geometria
from .geotiff import Amostra, GeoTiff, GeoTiffErro

UTC = timezone.utc
BRT = timezone(timedelta(hours=-3))      # o INMET escreve o horário dos avisos em Brasília
TEMPO_LIMITE_S = 30

# ── os nomes das fontes, por extenso (09/10/2026) ──────────────────────────────────────────────────────────────────────
# Levi, 09/10/2026, olhando o bloco "Fontes" do Mapa de risco ("INMET · avisos", "INPE · focos de queimada"): "Quero as fontes
# por extenso também, não só sigla". UM lugar só: a lista do Clima e risco, o mapa (fontes, legendas e dicas), o modo TV e a
# página da usina escrevem o nome pelo `extenso()` daqui, e `tests/test_clima_nomes.py` falha se o nome por extenso aparecer
# escrito à mão em outro arquivo do Nexus. A sigla sozinha só fica em mensagem de erro e no log (a linha da fonte que a mostra
# na tela já começa pelo nome por extenso).
NOMES = {
    "inmet": {"sigla": "INMET", "nome": "Instituto Nacional de Meteorologia"},
    "inpe": {"sigla": "INPE", "nome": "Instituto Nacional de Pesquisas Espaciais"},
    # o projeto da NASA tem o nome dele por extenso (POWER = Prediction Of Worldwide Energy Resources); a citação que a NASA
    # pede ("NASA LaRC POWER", do Centro de Pesquisa Langley) continua no rodapé da página da usina
    "nasa_power": {"sigla": "NASA POWER", "nome": "Prediction Of Worldwide Energy Resources, projeto da NASA"},
    "ibge": {"sigla": "IBGE", "nome": "Instituto Brasileiro de Geografia e Estatística"},
    # FIRMS = Fire Information for Resource Management System (10/10/2026): os focos dos satélites VIIRS e MODIS da NASA, com a força
    # (FRP) e a confiança de cada um
    "nasa_firms": {"sigla": "NASA FIRMS", "nome": "Fire Information for Resource Management System, sistema da NASA"},
}


def sigla_de(orgao: str) -> str:
    return NOMES[orgao]["sigla"]


def nome_de(orgao: str) -> str:
    return NOMES[orgao]["nome"]


def extenso(orgao: str) -> str:
    """"Instituto Nacional de Meteorologia (INMET)": o nome por extenso com a sigla, como a tela escreve toda fonte."""
    return f"{nome_de(orgao)} ({sigla_de(orgao)})"

# Endereços padrão; cada um pode ser trocado na configuração (`enderecos`), por exemplo para um espelho interno.
INMET_AVISOS = "https://apiprevmet3.inmet.gov.br/avisos/ativos"
INPE_FOCOS = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/10min/"
INPE_RISCO_FOGO = ("https://dataserver-coids.inpe.br/queimadas/queimadas/riscofogo_meteorologia/previsto/risco_fogo/"
                   "RF.PREV.T{d}.tif")

# NASA POWER (07/10/2026): irradiação global horizontal (GHI) diária num ponto. Medida contra as ETMs de 40 usinas (mai a set/2026,
# 2.642 dias válidos): erro mediano 7,4% no dia e 3,9% no mês, 84% dos meses dentro de 10%. Grátis, sem chave, de uso livre.
NASA_POWER = ("https://power.larc.nasa.gov/api/temporal/daily/point?parameters=ALLSKY_SFC_SW_DWN&community=RE"
              "&longitude={lon}&latitude={lat}&start={inicio}&end={fim}&format=JSON")
POWER_PARAMETRO = "ALLSKY_SFC_SW_DWN"
POWER_UNIDADE = "kW-hr/m^2/day"          # kWh/m² por dia; é o que `parameters.ALLSKY_SFC_SW_DWN.units` diz hoje
POWER_SEM_DADO = -999                    # dia ainda não publicado (a NASA atrasa uns 5 dias) ou buraco isolado: NUNCA vira zero
POWER_MAXIMO = 15.0                      # kWh/m²/dia: acima disto não é GHI de superfície (o máximo físico passa pouco de 12)
POWER_CASAS = 2                          # a coordenada vai com 2 casas (~1 km): a grade da NASA é de dezenas de km, e a posição
                                         # exata da usina não precisa chegar a um servidor de fora

# NASA FIRMS (10/10/2026, Levi: "veja se é viável para o que fazemos agora, se sim melhore e inclua coisas no mapa"). Os arquivos
# públicos de focos ativos da América do Sul, um por satélite, com as últimas passagens (na prática de 24 a 40 h de dado): grátis, SEM
# chave e de uso livre com citação. Medido em 10/10/2026 (seca): 2,5 a 2,9 MB por satélite VIIRS (~30 mil linhas, 95% na caixa do
# Brasil) e 0,6 MB o MODIS. O servidor devolve ETag e Last-Modified mas IGNORA o If-None-Match e o If-Modified-Since (conferido em
# 10/10/2026: 200 com o arquivo inteiro): por isso a releitura pergunta primeiro com um HEAD e só baixa o arquivo cujo ETag mudou
# (muda a cada passagem, umas 4 vezes por dia por satélite). A API por área com MAP_KEY não ajuda aqui: uma caixa que pega todas as
# usinas é quase o Brasil inteiro, o mesmo arquivo. Ela vale para o histórico por usina (outra fase).
FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/data/active_fire/"
FIRMS_ARQUIVOS = {                       # o satélite (ou o par, no MODIS) -> o arquivo, relativo a FIRMS_BASE
    "S-NPP": "suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_South_America_24h.csv",
    "NOAA-20": "noaa-20-viirs-c2/csv/J1_VIIRS_C2_South_America_24h.csv",
    "NOAA-21": "noaa-21-viirs-c2/csv/J2_VIIRS_C2_South_America_24h.csv",
    "MODIS": "modis-c6.1/csv/MODIS_C6_1_South_America_24h.csv",
}
FIRMS_COLUNAS = ("latitude", "longitude", "scan", "track", "acq_date", "acq_time", "satellite", "confidence", "frp", "daynight")
FIRMS_CAIXA = (-75.0, -35.0, -33.0, 6.5)  # oeste, sul, leste, norte: o Brasil com folga; o resto do continente não é lido
# o código do satélite na coluna `satellite`: VIIRS escreve N (S-NPP), N20 e N21; o MODIS, A (Aqua) e T (Terra)
_FIRMS_SATELITE = {"N": ("S-NPP", "VIIRS"), "N20": ("NOAA-20", "VIIRS"), "N21": ("NOAA-21", "VIIRS"),
                   "A": ("Aqua", "MODIS"), "AQUA": ("Aqua", "MODIS"), "T": ("Terra", "MODIS"), "TERRA": ("Terra", "MODIS")}
# a confiança: o VIIRS escreve low/nominal/high (ou l/n/h); o MODIS, de 0 a 100 (a divisa da própria NASA: < 30 baixa, < 80 nominal)
_FIRMS_CONFIANCA = {"low": "baixa", "l": "baixa", "nominal": "nominal", "n": "nominal", "high": "alta", "h": "alta"}
FIRMS_FRP_MAX = 50000.0                  # MW: acima disto não é o FRP de um pixel (o maior medido em 10/10/2026 foi 1.257)

FOCOS_ARQUIVOS = 6                       # seis arquivos de 10 min = a última hora
DIAS_DE_RISCO = (0, 1, 2, 3)             # RF.PREV.T0..T3: hoje e D+1 a D+3
TRABALHADORES_POR_DIA = 2                # tiles pedidas ao mesmo tempo em cada dia; os 4 dias vão juntos: 8 conexões no máximo
PISO_RISCO = -1e-9                       # o risco vale de 0 a 1: abaixo disto o pixel não é dado (ver GeoTiff.piso)
_NIVEL_INMET = {"perigo potencial": 1, "perigo": 2, "grande perigo": 3}   # amarelo, laranja, vermelho


class FonteErro(Exception):
    """A fonte respondeu, mas não no formato que o cliente sabe ler. A mensagem vai para a tela."""


class Foco(NamedTuple):
    lat: float
    lon: float
    satelite: str
    data: datetime                       # UTC, a hora da detecção


class FocoNasa(NamedTuple):
    """Um foco do FIRMS: o pixel de 375 m (VIIRS) ou de 1 km (MODIS) onde o satélite viu fogo."""
    lat: float
    lon: float
    satelite: str                        # S-NPP, NOAA-20, NOAA-21, Aqua ou Terra
    data: datetime                       # UTC, a hora da passagem (acq_date + acq_time)
    sensor: str                          # VIIRS ou MODIS
    confianca: str                       # baixa, nominal ou alta
    frp: float                           # a força do fogo: a energia que ele irradia, em MW
    dia: bool                            # passagem de dia (a de noite vê menos reflexo de sol, e o fogo de noite é mais certo)


class Aviso:
    """Um aviso do INMET já localizável: tem polígono bem formado. Não guarda o `icone` (base64, 90% do corpo)."""

    def __init__(self, id, quando, evento, severidade, nivel, inicio, fim, geometria_, caixa):
        self.id, self.quando, self.evento, self.severidade, self.nivel = id, quando, evento, severidade, nivel
        self.inicio, self.fim, self.geometria, self.caixa = inicio, fim, geometria_, caixa


def enderecos(config) -> dict:
    """Os quatro endereços: o padrão, ou o da configuração (`NEXUS_CLIMA_*_URL`, por exemplo um espelho interno). Valor em branco
    vale o padrão."""
    cfg = config or {}

    def de(chave, padrao):
        return str(cfg.get(chave) or "").strip() or padrao

    focos = de("NEXUS_CLIMA_FOCOS_URL", INPE_FOCOS)
    firms = de("NEXUS_CLIMA_FIRMS_URL", FIRMS_BASE)
    return {"inmet": de("NEXUS_CLIMA_INMET_URL", INMET_AVISOS),
            "focos": focos if focos.endswith("/") else focos + "/",
            "risco": de("NEXUS_CLIMA_RISCO_URL", INPE_RISCO_FOGO),
            "power": de("NEXUS_CLIMA_POWER_URL", NASA_POWER),
            "firms": firms if firms.endswith("/") else firms + "/"}


_sessao = None


def sessao_padrao():
    """A sessão de produção, a mesma para as três fontes (reaproveita a conexão)."""
    global _sessao
    if _sessao is None:
        s = requests.Session()
        s.headers["User-Agent"] = "Nexus-GridCo/1.0 (clima e risco; leitura de dados publicos)"
        _sessao = s
    return _sessao


def resumo_do_erro(e: Exception) -> str:
    """O erro como a tela o diz: curto, sem pilha e sem endereço comprido de conexão."""
    if isinstance(e, requests.Timeout):
        return "tempo esgotado"
    if isinstance(e, requests.ConnectionError):
        return "sem conexão com o servidor"
    if isinstance(e, requests.HTTPError):
        resposta = getattr(e, "response", None)
        return f"HTTP {resposta.status_code}" if resposta is not None else str(e)[:100]
    if isinstance(e, (FonteErro, GeoTiffErro)):
        return str(e)[:300]
    return f"{type(e).__name__}: {str(e)[:120]}"


def _chave(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def _texto(valor, limite, padrao) -> str:
    t = re.sub(r"\s+", " ", str(valor)).strip() if valor is not None else ""
    return t[:limite] if t else padrao


_SO_DATA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _hora_brasilia(valor, *, fim_do_dia=False):
    """O INMET escreve início e fim em horário de Brasília (UTC-3, sem horário de verão desde 2019) e sem fuso no texto: o
    texto sem fuso é Brasília. Uma DATA sem hora no FIM vale até o fim do dia (23:59:59), e não até 00:00: "2026-10-06"
    como fim fazia o aviso sumir da tela no primeiro minuto do dia em que ainda vale."""
    texto = str(valor).strip() if valor is not None else ""
    try:
        d = datetime.fromisoformat(texto.replace(" ", "T"))
    except ValueError:
        return None
    if fim_do_dia and _SO_DATA.match(texto):
        d = d.replace(hour=23, minute=59, second=59)
    return d if d.tzinfo else d.replace(tzinfo=BRT)


# ── INMET ────────────────────────────────────────────────────────────────────────────────────────────────────────────

def _ler_poligono(valor):
    """(geometria, None) ou (None, motivo). O polígono vem como TEXTO de JSON; "" e "null" são "sem polígono"."""
    if valor is None:
        return None, "sem polígono"
    if isinstance(valor, str):
        if valor.strip() in ("", "null"):
            return None, "sem polígono"
        try:
            return json.loads(valor), None
        except ValueError:
            return None, "polígono ilegível"
    return valor, None


def inmet_avisos(sessao, url=INMET_AVISOS, *, timeout=TEMPO_LIMITE_S) -> dict:
    """{"avisos": [Aviso], "ignorados": [motivo], "lidos": n}. O JSON é {"hoje": [...], "futuro": [...]}; o polígono de cada
    aviso vem como TEXTO de JSON. Aviso que não dá para localizar (sem polígono, ilegível, forma que não é Polygon nem
    MultiPolygon) fica em `ignorados`, com o motivo: sumir calado seria "sem alerta" onde pode haver."""
    r = sessao.get(url, headers={"Accept": "application/json"}, timeout=timeout)
    r.raise_for_status()
    try:
        js = json.loads(r.content)
    except ValueError:
        raise FonteErro("a resposta do INMET não é JSON") from None
    if not isinstance(js, dict) or not ("hoje" in js or "futuro" in js):
        raise FonteErro("a resposta do INMET não traz as listas hoje e futuro")
    avisos, ignorados, vistos, lidos = [], [], set(), 0
    for quando in ("hoje", "futuro"):
        lista = js.get(quando)
        if lista is None:
            continue
        if not isinstance(lista, list):
            raise FonteErro(f"a lista {quando} da resposta do INMET não é uma lista")
        for bruto in lista:
            lidos += 1
            if not isinstance(bruto, dict):
                ignorados.append(f"aviso fora do formato na lista {quando}")
                continue
            id_ = bruto.get("id", bruto.get("id_aviso"))
            geo, motivo = _ler_poligono(bruto.get("poligono"))
            # O mesmo aviso nas duas listas conta uma vez (ignorado ou não); o mesmo id com polígono ou vigência diferente é
            # OUTRO aviso (juntar pelo id sozinho sumia com um alerta de verdade). O polígono entra na chave já lido, para
            # o mesmo desenho escrito de outro jeito (chaves em outra ordem) continuar sendo o mesmo.
            chave = (id_, json.dumps(geo, sort_keys=True, default=str) if geo is not None else str(bruto.get("poligono")).strip(),
                     str(bruto.get("inicio")), str(bruto.get("fim")))
            if chave in vistos:
                lidos -= 1
                continue
            vistos.add(chave)
            if geo is None:
                ignorados.append(f"aviso {id_}: {motivo}")
                continue
            try:
                caixa = geometria.caixa(geo)
            except ValueError as e:
                ignorados.append(f"aviso {id_}: polígono fora do formato ({e})")
                continue
            severidade = _texto(bruto.get("severidade"), 60, "sem severidade")
            avisos.append(Aviso(id_, quando, _texto(bruto.get("descricao"), 120, "Aviso"), severidade,
                                _NIVEL_INMET.get(_chave(severidade), 1), _hora_brasilia(bruto.get("inicio")),
                                _hora_brasilia(bruto.get("fim"), fim_do_dia=True), geo, caixa))
    if lidos and not avisos:
        # Avisos vieram e nenhum dá para localizar: não é "nenhum aviso ativo". É a fonte que mudou (ou falhou), e a tela
        # serve a última leitura boa com o erro em vez de mostrar "0 avisos" em verde.
        raise FonteErro(f"nenhum dos {lidos} avisos do INMET tem polígono utilizável ({ignorados[0]})")
    return {"avisos": avisos, "ignorados": ignorados, "lidos": lidos}


# ── INPE: focos de queimada ──────────────────────────────────────────────────────────────────────────────────────────

_ARQUIVO_FOCO = re.compile(r'href="(focos_10min_(\d{8})_(\d{4})\.csv)"')


def _hora_do_arquivo(nome):
    m = _ARQUIVO_FOCO.search(f'href="{nome}"')
    return datetime.strptime(m.group(2) + m.group(3), "%Y%m%d%H%M").replace(tzinfo=UTC)


def inpe_focos(sessao, url=INPE_FOCOS, *, ultimos=FOCOS_ARQUIVOS, timeout=TEMPO_LIMITE_S) -> dict:
    """{"focos": [Foco], "arquivos": [nomes lidos], "falhos": [nomes], "ate": hora UTC do arquivo mais novo lido,
    "linhas_ruins": n}. O INPE publica um CSV a cada 10 min (`lat,lon,satelite,data`, número com espaço na frente, hora em
    UTC); os seis últimos são a última hora. Um arquivo que não veio fica dito em `falhos` e os outros valem; cabeçalho
    diferente do esperado é FonteErro (o formato mudou), nunca "arquivo falho"."""
    r = sessao.get(url, timeout=timeout)
    r.raise_for_status()
    indice = r.content.decode("utf-8", "replace")
    nomes = sorted({m.group(1) for m in _ARQUIVO_FOCO.finditer(indice)})[-ultimos:]
    if not nomes:
        raise FonteErro("o índice do INPE não lista nenhum arquivo de focos")
    focos, vistos, lidos, falhos, ruins, ultimo_erro = [], set(), [], [], 0, None
    for nome in nomes:
        try:
            resposta = sessao.get(url + nome, timeout=timeout)
            resposta.raise_for_status()
        except (requests.RequestException, OSError) as e:
            falhos.append(nome)
            ultimo_erro = e
            continue
        leitor = csv.reader(io.StringIO(resposta.content.decode("utf-8-sig", "replace")), skipinitialspace=True)
        cabecalho = next(leitor, None)
        if cabecalho is None or [c.strip().lower() for c in cabecalho][:4] != ["lat", "lon", "satelite", "data"]:
            raise FonteErro(f"cabeçalho inesperado em {nome}: o leitor espera lat,lon,satelite,data")
        for linha in leitor:
            if not linha:
                continue
            try:
                lat, lon = float(linha[0]), float(linha[1])
                data = datetime.strptime(linha[3].strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError("coordenada fora da faixa")
            except (ValueError, IndexError):
                ruins += 1
                continue
            foco = Foco(lat, lon, linha[2].strip(), data)
            if foco not in vistos:
                vistos.add(foco)
                focos.append(foco)
        lidos.append(nome)
    if not lidos:
        raise FonteErro(f"nenhum dos {len(nomes)} arquivos de focos pôde ser lido ({resumo_do_erro(ultimo_erro)})")
    if ruins and not focos:
        # Todas as linhas ilegíveis (a data em outro formato, por exemplo) não é "0 focos": é o formato que mudou.
        raise FonteErro(f"{ruins} linhas dos arquivos de focos não puderam ser lidas e nenhum foco foi lido: o formato dos "
                        "dados mudou?")
    return {"focos": focos, "arquivos": lidos, "falhos": falhos, "ate": _hora_do_arquivo(lidos[-1]),
            "linhas_ruins": ruins}


# ── NASA FIRMS: o fogo das últimas 24 h, com força e confiança (10/10/2026) ──────────────────────────────────────────

def _confianca_firms(bruto: str, sensor: str) -> str:
    t = str(bruto or "").strip().lower()
    if sensor == "MODIS":
        n = int(float(t))                        # ValueError se não for número: a linha conta como ilegível
        if not 0 <= n <= 100:
            raise ValueError("confiança do MODIS fora de 0 a 100")
        return "baixa" if n < 30 else "nominal" if n < 80 else "alta"
    if t not in _FIRMS_CONFIANCA:
        raise ValueError("confiança do VIIRS desconhecida")
    return _FIRMS_CONFIANCA[t]


def _ler_firms(conteudo: bytes, nome: str) -> tuple:
    """(focos na caixa do Brasil, linhas ilegíveis) de um arquivo do FIRMS. A coluna é achada pelo NOME (o VIIRS e o MODIS têm
    colunas diferentes no meio: bright_ti4 e brightness); faltou uma das que o leitor usa, o formato mudou (FonteErro)."""
    leitor = csv.reader(io.StringIO(conteudo.decode("utf-8-sig", "replace")))
    cabecalho = [c.strip().lower() for c in next(leitor, None) or []]
    faltam = [c for c in FIRMS_COLUNAS if c not in cabecalho]
    if faltam:
        raise FonteErro(f"cabeçalho inesperado no arquivo {nome} do FIRMS: faltam {', '.join(faltam)}")
    i = {c: cabecalho.index(c) for c in FIRMS_COLUNAS}
    oeste, sul, leste, norte = FIRMS_CAIXA
    focos, ruins = [], 0
    for linha in leitor:
        if not linha:
            continue
        try:
            lat, lon = float(linha[i["latitude"]]), float(linha[i["longitude"]])
            if not (sul <= lat <= norte and oeste <= lon <= leste):
                continue                             # fora do Brasil: nem guarda
            satelite, sensor = _FIRMS_SATELITE[linha[i["satellite"]].strip().upper()]
            hhmm = linha[i["acq_time"]].strip().zfill(4)
            data = datetime.strptime(linha[i["acq_date"]].strip() + hhmm, "%Y-%m-%d%H%M").replace(tzinfo=UTC)
            frp = float(linha[i["frp"]])
            if not 0 <= frp <= FIRMS_FRP_MAX:
                raise ValueError("FRP fora da faixa")
            dia = linha[i["daynight"]].strip().upper()
            if dia not in ("D", "N"):
                raise ValueError("dia/noite desconhecido")
            focos.append(FocoNasa(lat, lon, satelite, data, sensor, _confianca_firms(linha[i["confidence"]], sensor), frp,
                                  dia == "D"))
        except (ValueError, IndexError, KeyError):
            ruins += 1
    return focos, ruins


def nasa_firms(sessao, base=FIRMS_BASE, *, anterior=None, arquivos=None, timeout=TEMPO_LIMITE_S) -> dict:
    """{"focos": [FocoNasa], "arquivos": {satélite: {"etag", "modificado", "focos"}}, "falhos": {satélite: motivo}, "ate": a hora
    UTC do foco mais novo (ou None), "linhas_ruins": n}. Os arquivos (`FIRMS_ARQUIVOS`) vão juntos; `anterior` é a leitura boa de
    antes: o arquivo cujo ETag não mudou (perguntado com um HEAD, porque o servidor ignora o If-None-Match) volta como estava, sem
    baixar e sem reler. Um arquivo que falha fica em `falhos` e os outros valem; cabeçalho diferente do esperado é FonteErro (o
    formato mudou); nenhum arquivo lido também. Só ficam os focos na caixa do Brasil (`FIRMS_CAIXA`); a janela de 24 h é de quem
    usa."""
    arquivos = FIRMS_ARQUIVOS if arquivos is None else arquivos
    antes = (anterior or {}).get("arquivos") or {}

    def um(par):
        satelite, caminho = par
        velho = antes.get(satelite)
        cabeca = getattr(sessao, "head", None)
        if velho and velho.get("etag") and callable(cabeca):
            try:
                h = cabeca(base + caminho, timeout=timeout)
                if h.status_code == 200 and h.headers.get("ETag") == velho["etag"]:
                    return satelite, velho, 0, None         # o mesmo arquivo: nem baixa
            except (requests.RequestException, OSError):
                pass                                        # o HEAD falhou: o GET decide
        try:
            r = sessao.get(base + caminho, headers={"Accept": "text/csv"}, timeout=timeout)
            r.raise_for_status()
        except (requests.RequestException, OSError) as e:
            return satelite, None, 0, resumo_do_erro(e)
        focos, ruins = _ler_firms(r.content, caminho.rsplit("/", 1)[-1])
        modificado = None
        try:
            modificado = parsedate_to_datetime(r.headers.get("Last-Modified")) if r.headers.get("Last-Modified") else None
        except (TypeError, ValueError):
            modificado = None
        return satelite, {"etag": r.headers.get("ETag"), "modificado": modificado, "focos": focos}, ruins, None

    with ThreadPoolExecutor(max_workers=len(arquivos) or 1) as pool:
        feitos = list(pool.map(um, arquivos.items()))
    lidos, falhos, ruins = {}, {}, 0
    for satelite, dados, n_ruins, erro in feitos:
        if erro is not None:
            falhos[satelite] = erro
        else:
            lidos[satelite] = dados
            ruins += n_ruins
    if not lidos:
        raise FonteErro("nenhum arquivo do FIRMS pôde ser lido: " + "; ".join(f"{s}: {m}" for s, m in falhos.items()))
    focos = [f for d in lidos.values() for f in d["focos"]]
    if ruins and not focos:
        raise FonteErro(f"{ruins} linhas do FIRMS não puderam ser lidas e nenhum foco foi lido: o formato dos dados mudou?")
    return {"focos": focos, "arquivos": lidos, "falhos": falhos, "ate": max((f.data for f in focos), default=None),
            "linhas_ruins": ruins}


# ── INPE: risco de fogo ──────────────────────────────────────────────────────────────────────────────────────────────

def inpe_risco_fogo(pontos, sessao, modelo_url=INPE_RISCO_FOGO, *, dias=DIAS_DE_RISCO, janela=None,
                    timeout=TEMPO_LIMITE_S) -> dict:
    """`pontos`: [(chave, lat, lon)]. {"por_ponto": {chave: [Amostra por dia]}, "arquivos": {dia: data do arquivo},
    "erros": {dia: motivo}}. Um dia que falha (arquivo ausente, formato mudado, valor fora de 0 a 1) vira
    `Amostra(None, "indisponivel")` com o motivo em `erros`, e os outros dias valem; se nenhum dia for lido, é FonteErro.
    Valor ACIMA de 1 derruba o dia: uma escala trocada (0 a 100) acenderia o "crítico" em toda usina. Valor NEGATIVO que
    não é o nodata (-999) é "sem dado" só naquele ponto (vale o entorno), não prova de escala trocada."""
    pontos = list(pontos)
    if "{d}" not in modelo_url:
        raise FonteErro("o endereço do risco de fogo precisa de {d} (o dia, de 0 a 3)")
    if not pontos:
        return {"por_ponto": {}, "arquivos": {}, "erros": {}}
    extra = {} if janela is None else {"janela": janela}
    dias = tuple(dias)

    def um_dia(d):
        try:
            gt = GeoTiff(modelo_url.format(d=d), sessao, timeout=timeout, trabalhadores=TRABALHADORES_POR_DIA,
                         piso=PISO_RISCO, **extra)
            resultado = gt.amostrar_varios(pontos)
            for a in resultado.values():
                if a.valor is not None and not -1e-9 <= a.valor <= 1 + 1e-9:
                    raise FonteErro(f"valor {a.valor:g} fora da faixa de 0 a 1: o INPE mudou a escala do risco?")
        except (GeoTiffErro, FonteErro, requests.RequestException, OSError) as e:
            return d, None, None, resumo_do_erro(e)
        return d, gt.modificado, resultado, None

    # Os quatro dias são arquivos independentes: em fila, 160 usinas levavam 10 s na primeira visita (medido em 06/10/2026);
    # juntos, o tempo é o do dia mais lento.
    with ThreadPoolExecutor(max_workers=len(dias)) as pool:
        feitos = list(pool.map(um_dia, dias))
    por_ponto = {chave: [] for chave, _, _ in pontos}
    arquivos, erros = {}, {}
    for d, modificado, resultado, erro in feitos:
        if erro is not None:
            erros[d] = erro
            for chave in por_ponto:
                por_ponto[chave].append(Amostra(None, "indisponivel"))
            continue
        arquivos[d] = modificado
        for chave in por_ponto:
            por_ponto[chave].append(resultado[chave])
    if len(erros) == len(dias):
        raise FonteErro("nenhum dia do risco de fogo pôde ser lido: " + "; ".join(f"D{d}: {m}" for d, m in erros.items()))
    return {"por_ponto": por_ponto, "arquivos": arquivos, "erros": erros}


# ── INPE: risco de fogo em toda a área, para o mapa de calor (09/10/2026) ──────────────────────────────────────────────

GRADE_GRAUS = 0.08                       # o quadrado-base do mapa de calor: 8 pixels de 0,01 grau (~9 km); o Brasil inteiro junta 2 x 2
TRABALHADORES_GRADE = 4                  # tiles pedidas ao mesmo tempo na leitura da área (o servidor é público: poucas)


def inpe_risco_grade(sessao, url, caixa, *, passo=GRADE_GRAUS, precisa=None, anterior=None,
                     timeout=TEMPO_LIMITE_S) -> dict:
    """O risco de fogo de UM dia (o arquivo `url`, já com o dia) em blocos de `passo` graus na `caixa`: a soma e a contagem dos
    pixels com dado de cada bloco (`GeoTiff.somar_em_blocos`), para o mapa de calor do Mapa de risco. É o mesmo arquivo que o
    risco por usina lê; nenhuma saída nova para a internet.

    `anterior` é a leitura boa de antes: se o arquivo do INPE não mudou (o mesmo Last-Modified, que o cabeçalho de 64 KB já
    traz), ela volta como está e nenhuma tile é baixada. O arquivo muda uma vez por dia (~06:30); sem isto, a releitura de
    15 em 15 min antes da publicação baixaria ~8 MB a cada vez para achar o mesmo arquivo.

    {"modificado": datetime UTC do arquivo ou None, "validador": o Last-Modified como veio, "url", "grade": os blocos (ver
    `somar_em_blocos`), "conferido": True quando veio da `anterior`}. Formato diferente do medido é GeoTiffErro, como no ponto."""
    gt = GeoTiff(url, sessao, timeout=timeout, trabalhadores=TRABALHADORES_GRADE, piso=PISO_RISCO)
    gt.abrir()
    validador = gt.validador
    if anterior and validador and anterior.get("validador") == validador and anterior.get("url") == url:
        return {**anterior, "conferido": True}
    grade = gt.somar_em_blocos(caixa, passo, precisa=precisa, teto=1 + 1e-9)
    return {"modificado": gt.modificado, "validador": validador, "url": url, "grade": grade, "conferido": False}


# ── NASA POWER: irradiação diária ────────────────────────────────────────────────────────────────────────────────────

def nasa_power(lat, lon, inicio: date, fim: date, sessao, modelo_url=NASA_POWER, *, timeout=TEMPO_LIMITE_S) -> dict:
    """O GHI diário (kWh/m²/dia) da NASA POWER num ponto, de `inicio` a `fim` (datas de Brasília). {"dias": {data: valor ou
    None}, "publicado_ate": a última data com valor, ou None}. O -999 da NASA (dia ainda não publicado, ou um buraco no meio da
    série) vira None, nunca zero; os dias que ela devolve cobrem a janela inteira. `modelo_url` leva {lat}, {lon}, {inicio} e
    {fim} (AAAAMMDD). Formato diferente do medido em 07/10/2026 (não JSON, sem a série, data fora de AAAAMMDD, valor que não é
    número, fora de 0 a 15, unidade que não é kWh/m²/dia, outro valor de preenchimento) é FonteErro, nunca número lido do jeito
    errado. A coordenada vai com `POWER_CASAS` casas: a posição exata da usina não precisa chegar à NASA."""
    if fim < inicio:
        raise ValueError("a janela da NASA POWER termina antes de começar")
    if not all(f"{{{nome}}}" in modelo_url for nome in ("lat", "lon", "inicio", "fim")):
        raise FonteErro("o endereço da NASA POWER precisa de {lat}, {lon}, {inicio} e {fim}")
    try:
        url = modelo_url.format(lat=f"{lat:.{POWER_CASAS}f}", lon=f"{lon:.{POWER_CASAS}f}", inicio=inicio.strftime("%Y%m%d"),
                                fim=fim.strftime("%Y%m%d"))
    except (KeyError, IndexError, ValueError):
        raise FonteErro("o endereço da NASA POWER só pode ter {lat}, {lon}, {inicio} e {fim} entre chaves") from None
    r = sessao.get(url, headers={"Accept": "application/json"}, timeout=timeout)
    r.raise_for_status()
    try:
        js = json.loads(r.content)
    except ValueError:
        raise FonteErro("a resposta da NASA POWER não é JSON") from None
    if not isinstance(js, dict):
        raise FonteErro("a resposta da NASA POWER não é um objeto JSON")
    try:
        serie = js["properties"]["parameter"][POWER_PARAMETRO]
    except (KeyError, TypeError):
        raise FonteErro(f"a resposta da NASA POWER não traz {POWER_PARAMETRO} em properties.parameter") from None
    if not isinstance(serie, dict) or not serie:
        raise FonteErro("a série diária da NASA POWER veio vazia ou fora do formato")
    parametros = js.get("parameters") if isinstance(js.get("parameters"), dict) else {}
    do_parametro = parametros.get(POWER_PARAMETRO)
    unidade = do_parametro.get("units") if isinstance(do_parametro, dict) else None
    if unidade is None:
        raise FonteErro("a NASA POWER não informou a unidade da irradiação")
    if unidade != POWER_UNIDADE:
        raise FonteErro(f"a unidade da NASA POWER mudou (esperava {POWER_UNIDADE}, veio {str(unidade)[:40]})")
    cabecalho = js.get("header") if isinstance(js.get("header"), dict) else {}
    preenchimento = cabecalho.get("fill_value", POWER_SEM_DADO)
    if preenchimento != POWER_SEM_DADO:
        raise FonteErro(f"o valor de preenchimento da NASA POWER mudou (esperava {POWER_SEM_DADO}, veio {str(preenchimento)[:20]})")
    dias = {}
    for chave, valor in serie.items():
        try:
            dia = datetime.strptime(chave, "%Y%m%d").date()
        except (ValueError, TypeError):
            raise FonteErro(f"data fora do formato AAAAMMDD na NASA POWER: {str(chave)[:20]!r}") from None
        if isinstance(valor, bool) or not isinstance(valor, (int, float)):
            raise FonteErro(f"valor que não é número na NASA POWER ({str(chave)[:20]})")
        if valor == POWER_SEM_DADO:
            dias[dia] = None
        elif 0 <= valor <= POWER_MAXIMO:
            dias[dia] = float(valor)
        else:
            raise FonteErro(f"valor {valor:g} fora da faixa de 0 a {POWER_MAXIMO:g} kWh/m²/dia: a NASA mudou a unidade?")
    publicados = [d for d, v in dias.items() if v is not None]
    return {"dias": dias, "publicado_ate": max(publicados) if publicados else None}
