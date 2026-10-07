"""Os três clientes públicos do Clima e risco: avisos do INMET, focos de queimada do INPE e risco de fogo do INPE.

Todos são só leitura (GET), sem chave e de uso livre; o formato abaixo é o medido em 06/10/2026, e o que fugir dele vira
`FonteErro` (a tela diz que a fonte falhou) em vez de número lido do jeito errado. Quem recebe a sessão é quem chama: a
sessão de verdade em produção, uma falsa nos testes (nenhum teste vai à rede).

Atribuição que a tela mostra no rodapé: "Dados: INMET, INPE (Programa Queimadas)". O endereço do INMET não é documentado
oficialmente (é o que o próprio site de avisos usa); se ele sumir, a tela mostra o INMET como fora do ar.
"""
import csv
import io
import json
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import requests

from . import geometria
from .geotiff import Amostra, GeoTiff, GeoTiffErro

UTC = timezone.utc
BRT = timezone(timedelta(hours=-3))      # o INMET escreve o horário dos avisos em Brasília
TEMPO_LIMITE_S = 30

# Endereços padrão; cada um pode ser trocado na configuração (`enderecos`), por exemplo para um espelho interno.
INMET_AVISOS = "https://apiprevmet3.inmet.gov.br/avisos/ativos"
INPE_FOCOS = "https://dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/10min/"
INPE_RISCO_FOGO = ("https://dataserver-coids.inpe.br/queimadas/queimadas/riscofogo_meteorologia/previsto/risco_fogo/"
                   "RF.PREV.T{d}.tif")

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


class Aviso:
    """Um aviso do INMET já localizável: tem polígono bem formado. Não guarda o `icone` (base64, 90% do corpo)."""

    def __init__(self, id, quando, evento, severidade, nivel, inicio, fim, geometria_, caixa):
        self.id, self.quando, self.evento, self.severidade, self.nivel = id, quando, evento, severidade, nivel
        self.inicio, self.fim, self.geometria, self.caixa = inicio, fim, geometria_, caixa


def enderecos(config) -> dict:
    cfg = config or {}
    focos = (cfg.get("NEXUS_CLIMA_FOCOS_URL") or INPE_FOCOS).strip()
    return {"inmet": (cfg.get("NEXUS_CLIMA_INMET_URL") or INMET_AVISOS).strip(),
            "focos": focos if focos.endswith("/") else focos + "/",
            "risco": (cfg.get("NEXUS_CLIMA_RISCO_URL") or INPE_RISCO_FOGO).strip()}


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
