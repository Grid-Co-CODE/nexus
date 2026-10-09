"""O Mapa de risco (07/10/2026): o contorno dos estados, a projeção e o recorte de cada região, sem Flask.

Pedido do Levi (07/10): a lista do Clima e risco ganha um mapa do Brasil, com as usinas na cor do nível, os avisos do INMET e
os focos do INPE. O SVG nasce no servidor: nada de biblioteca de mapa, de mapa de terceiros ou de dependência nova, e nenhuma
busca ao IBGE em tempo de execução. Desde 09/10/2026 (Levi: "Quero o mapa mais interativo", "visão de tela cheia para colocar no
video wall", "uma outra visão tipo um mapa de calor") o mesmo SVG ganha as camadas de calor (`calor.py`) e o estado da tela no
endereço (camada de fundo, camadas de cima, dia, cliente, filtros, modo TV); o zoom, a dica e o resto da interação são do
`static/clima-mapa.js`, que só enfeita o que o servidor já desenhou (sem JavaScript, o mapa e os links continuam valendo).

O contorno é o do IBGE (Malhas territoriais, API v3, `qualidade=minima`, divisão por UF), baixado UMA vez e guardado em
`nexus/static/clima/ibge-ufs-minima.geojson` (98 KB, 27 UFs, ~5.500 vértices com 4 casas). Como refazê-lo e a fonte: seção
"Mapa de risco" de `nexus/performance/CLAUDE.md`. O arquivo "mínimo" é só o continente: sem Trindade nem Fernando de Noronha,
que alargariam o recorte do Brasil em uns 15% de oceano (o teste `test_o_contorno_e_so_o_continente...` avisa se trocarem).

Projeção equiretangular com a correção de cos(latitude média): o x é a longitude vezes o cosseno da latitude do MEIO do
recorte, o y é a latitude. Sem o cosseno o Brasil ficaria 3% mais largo; no Sul (28 graus), 13%. Cada recorte usa a latitude
média dele e refaz o viewBox, que tem sempre 1000 de largura: o tamanho dos pontos e dos traços, que o CSS decide em unidades
do SVG, vale igual em todas as vistas. A conta fica em graus de latitude (1 = ~111 km) e a `Vista` a leva para o SVG.

A primeira metade do módulo é geometria pura (contorno, projeção, vista, caminho). O `montar`, no fim, junta isso com as usinas
do cadastro e as leituras das três fontes (as MESMAS da tela principal, pelo mesmo cache) e devolve o que o template desenha.
"""
import json
import logging
import math
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple
from urllib.parse import quote

from ...cadastro.servico import chave_texto
from . import alertas as A
from . import calor as C
from . import explica as E
from . import fontes as F
from . import leitura as L
from . import visao as V

log = logging.getLogger(__name__)
ARQUIVO_UFS = Path(__file__).resolve().parents[2] / "static" / "clima" / "ibge-ufs-minima.geojson"
LARGURA = 1000                     # a largura do viewBox de TODA vista; a altura sai da geografia
MARGEM = 0.03                      # folga em volta do recorte, para o traço da borda e o ponto da usina não serem cortados
BRASIL = "brasil"
# Só para o contorno que não abre: o continente (lon mín., lat mín., lon máx., lat máx.) sem depender do arquivo, para o mapa sair
# sem as divisas em vez de 500. Um teste confere que cobre o contorno do IBGE e não sobra mais de 1 grau.
LIMITES_BRASIL = (-74.0, -33.8, -34.7, 5.3)
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


# Número do SVG: uma casa (0,1 unidade = ~0,4 km no Brasil inteiro e menos nas regiões), sem ".0" e sem "-0". Mora no calor.py
# (que desenha as faixas das camadas de calor com o mesmo número) e vale aqui com o nome de sempre.
_n = C.numero_svg


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
    filtro de cliente da tela principal. Maiúscula e espaço em volta não contam."""
    chave = str(regiao or "").strip().lower()
    return _vista(chave if chave in REGIOES else BRASIL)


# ── o desenho dos estados ────────────────────────────────────────────────────────────────────────────────────────────

def caminho(aneis, v: Vista) -> str:
    """O `d` do SVG para uma lista de anéis de (lon, lat): `M x y l dx dy dx dy ... z` por anel, com os deslocamentos medidos
    do ponto JÁ arredondado anterior (a soma nunca deriva do desenho). Vértices que arredondam para o mesmo ponto saem, e o
    anel que não sobra com 3 pontos não é escrito: com ~0,4 km por unidade no Brasil inteiro, um vértice mais perto que isso
    do anterior só pesaria sem desenhar nada (um aviso pequeno, ou um estado de contorno detalhado, vira um risco). Os
    deslocamentos pesam a metade das coordenadas absolutas."""
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


# ── o que a tela desenha ─────────────────────────────────────────────────────────────────────────────────────────────

URL_USINA = "/t/performance/clima/usina/{}"          # a página da usina (a tela principal a serve; o mapa só aponta para ela)
NX = "nx"                                            # nível de quem ficaria "Sem alerta" mas teve fonte sem leitura
ROTULO_NX = "Sem leitura completa"
ORDEM_DE_DESENHO = {NX: 0, A.SEM_ALERTA: 1, A.ATENCAO: 2, A.AGIR: 3}     # o que pede ação por último: fica por cima
# a ordem da tabela ao lado do mapa (09/10/2026): quem pede ação primeiro; quem não teve leitura completa antes de quem
# está sem alerta (o cinza não é "tudo bem")
ORDEM_DA_TABELA = {A.AGIR: 0, A.ATENCAO: 1, NX: 2, A.SEM_ALERTA: 3}
# Raios em unidades do SVG (o viewBox tem 1000 de largura): a usina que pede ação é maior que a que está bem, e o anel do foco
# cobre o ponto da usina que está a até 5 km dele. No celular o CSS os multiplica (o SVG ali tem uns 340 px, não 700).
R_USINA = {A.AGIR: 7.5, A.ATENCAO: 6.0, A.SEM_ALERTA: 5.0, NX: 5.0}
R_ALVO = 2.2                                         # o círculo invisível que aumenta a área de toque: R_ALVO vezes o raio
R_ANEL = 12.0
FOLGA_PONTO = 4.0                                    # foco um pouco fora do viewBox ainda desenha (o ponto tem espessura)
MOTIVOS_NO_TITULO = 3
_FONTES = ("inmet", "focos", "risco")                # a ordem do painel das fontes (os nomes, por extenso, são os de visao.NOME_LONGO)

# As camadas (Levi, 09/10/2026: "Além de tempestade conseguimos uma outra visão tipo um mapa de calor no mapa? quanto mais
# versatilidade melhor!"). A camada de FUNDO é uma por vez: duas camadas de área juntas (o vermelho do aviso e o do calor) viram uma
# mancha só, e ninguém sabe o que está lendo. Por cima dela, as usinas, os focos e as siglas ligam e desligam à vontade.
FUNDOS = {"avisos": "Avisos meteorológicos", "risco": "Risco de fogo", "densidade": "Densidade de focos", "nenhum": "Nenhuma"}
FUNDO_PADRAO = "avisos"
GIRO = ("avisos", "risco", "densidade")              # o que o modo TV alterna sozinho (`girar`)
SOBRE = {"usinas": "Usinas", "focos": "Focos", "siglas": "Siglas dos estados"}
NIVEIS = (A.AGIR, A.ATENCAO, A.SEM_ALERTA, NX)
GIRAR_MIN_S, GIRAR_MAX_S = 10, 600
_SLUG = re.compile(r"^[a-z0-9-]{1,60}$")


def _juntar(nomes: list) -> str:
    """["a", "b", "c"] -> "a, b e c" (o mesmo da tela principal)."""
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def slug_do_evento(evento) -> str:
    """"Baixa Umidade" -> "baixa-umidade": a chave do evento no endereço (`sem_eventos`) e no atributo do desenho."""
    return re.sub(r"[^a-z0-9]+", "-", chave_texto(evento)).strip("-")[:60] or "evento"


def _lista(bruto, validos) -> frozenset:
    return frozenset(x for x in (p.strip().lower() for p in str(bruto or "").split(",")) if x in validos)


def estado_da_tela(args) -> dict:
    """O estado da tela pelos parâmetros do endereço: o endereço guarda tudo (é assim que o video wall abre na camada certa, e o
    recarregar não perde o que a pessoa escolheu). O que não é conhecido cai no padrão, sem erro, como a região."""
    fundo = str(args.get("fundo") or "").strip().lower()
    dia = str(args.get("dia") or "").strip()
    girar = str(args.get("girar") or "").strip()
    girar_s = int(girar) if girar.isdigit() and GIRAR_MIN_S <= int(girar) <= GIRAR_MAX_S else None
    ver = args.get("ver")
    return {"regiao": str(args.get("regiao") or ""), "fundo": fundo if fundo in FUNDOS else FUNDO_PADRAO,
            "ver": None if ver is None else _lista(ver, SOBRE), "dia": int(dia) if dia in ("0", "1", "2", "3") else None,
            "cliente": str(args.get("cliente") or "").strip(), "ocultar": _lista(args.get("ocultar"), NIVEIS),
            "sem_eventos": frozenset(p.strip() for p in str(args.get("sem_eventos") or "").split(",") if _SLUG.match(p.strip())),
            "tv": str(args.get("tv") or "") == "1", "girar": girar_s}


def parametros(estado: dict, **trocas) -> dict:
    """Os parâmetros do endereço do estado (com as `trocas`), só o que não é o padrão e numa ordem fixa: os links da tela (região,
    camada, filtro) levam o resto do estado junto, e o estado padrão não acrescenta nada (o Brasil é o endereço puro)."""
    e = {**estado, **trocas}
    p = {}
    if e.get("regiao") in REGIOES:
        p["regiao"] = e["regiao"]
    if e.get("fundo", FUNDO_PADRAO) != FUNDO_PADRAO:
        p["fundo"] = e["fundo"]
    if e.get("ver") is not None and set(e["ver"]) != set(SOBRE):
        p["ver"] = ",".join(k for k in SOBRE if k in e["ver"])
    if e.get("dia") is not None:
        p["dia"] = e["dia"]
    if e.get("cliente"):
        p["cliente"] = e["cliente"]
    if e.get("ocultar"):
        p["ocultar"] = ",".join(k for k in NIVEIS if k in e["ocultar"])
    if e.get("sem_eventos"):
        p["sem_eventos"] = ",".join(sorted(e["sem_eventos"]))
    if e.get("tv"):
        p["tv"] = 1
    if e.get("girar"):
        p["girar"] = e["girar"]
    return p


def _alterna(conjunto, item) -> frozenset:
    conjunto = frozenset(conjunto)
    return conjunto - {item} if item in conjunto else conjunto | {item}


def _links(estado: dict, eventos: list) -> dict:
    """Os parâmetros de cada controle da tela (o template só chama `url_for` com eles): funcionam sem JavaScript, e o JavaScript
    os usa para trocar a tela sem recarregar."""
    ver = frozenset(SOBRE) if estado["ver"] is None else estado["ver"]
    return {
        "regiao": {r: parametros(estado, regiao=(r if r != BRASIL else "")) for r in (BRASIL, *REGIOES)},
        "fundo": {f: parametros(estado, fundo=f) for f in FUNDOS},
        "ver": {s: parametros(estado, ver=_alterna(ver, s)) for s in SOBRE},
        "ocultar": {n: parametros(estado, ocultar=_alterna(estado["ocultar"], n)) for n in NIVEIS},
        "dia": {d: parametros(estado, dia=d) for d in range(4)},
        "sem_eventos": {e["ev"]: parametros(estado, sem_eventos=_alterna(estado["sem_eventos"], e["ev"])) for e in eventos},
        "tv": parametros(estado, tv=True), "sair_tv": parametros(estado, tv=False, girar=None),
        "girar": {s: parametros(estado, girar=s) for s in (None, 15, 30, 60, 120)},
        "aqui": parametros(estado),
    }


def _aneis_do_aviso(geometria_) -> list:
    """Todos os anéis de um Polygon ou MultiPolygon do INMET (o de fora e os buracos de cada pedaço): o `evenodd` do SVG faz
    do buraco um buraco. O `Aviso` só nasce com geometria que o `geometria.caixa` já aceitou."""
    coords = geometria_["coordinates"]
    poligonos = [coords] if geometria_["type"] == "Polygon" else coords
    return [anel for poligono in poligonos for anel in poligono]


def _estado_da_camada(leitura) -> str:
    return "ok" if leitura.dados is not None else ("lendo" if leitura.erro == L.LENDO else "fora")


def _camada_avisos(avisos_l, v: Vista, ref, qualifica: list, sem_eventos=frozenset()) -> dict:
    """Os polígonos do INMET que valem agora ou valerão (o vencido não desenha) e encostam no recorte, em grupos por nível e por
    "já em vigor" ou "ainda vai começar": o grupo vira uma camada translúcida do CSS, e o aviso que ainda não começou vai só no
    contorno. Do mais leve para o mais grave, que fica por cima. Cada polígono leva o evento (`ev`) para o filtro por evento da
    legenda (09/10/2026), e `eventos` conta os do recorte, um por evento, do que manda agir ao que só pede atenção."""
    camada = {"estado": _estado_da_camada(avisos_l), "grupos": [], "n_vigor": 0, "n_futuros": 0, "ignorados": 0,
              "qualifica": qualifica, "eventos": [], "lido": ""}
    if avisos_l.dados is None:
        return camada
    camada["ignorados"] = len(avisos_l.dados["ignorados"])
    # cada camada diz de quando é (09/10/2026): a legenda repete o "lido às" do painel das fontes
    camada["lido"] = V.hora(datetime.fromtimestamp(avisos_l.lido_em, V.BRT), ref) if avisos_l.lido_em else ""
    grupos, eventos = {}, {}
    for a in avisos_l.dados["avisos"]:
        if (a.fim is not None and a.fim < ref) or not v.cruza(a.caixa):
            continue
        d = caminho(_aneis_do_aviso(a.geometria), v)
        if not d:
            continue
        futuro = not A.em_vigor(a, ref)
        ev = slug_do_evento(a.evento)
        grupos.setdefault((futuro, a.nivel), []).append(
            {"d": d, "titulo": f"{a.evento} · {a.severidade} · {V._validade(a, ref)}", "ev": ev, "oculto": ev in sem_eventos})
        e = eventos.setdefault(ev, {"ev": ev, "nome": E.nome_amigavel(a.evento), "n": 0, "nivel": 0, "agir": False,
                                    "oculto": ev in sem_eventos})
        e["n"] += 1
        e["nivel"] = max(e["nivel"], a.nivel)
        e["agir"] = e["agir"] or A.aviso_manda_agir(a)
    for (futuro, nivel), itens in sorted(grupos.items()):
        camada["grupos"].append({"nivel": nivel, "futuro": futuro, "itens": itens})
        camada["n_futuros" if futuro else "n_vigor"] += len(itens)
    camada["eventos"] = sorted(eventos.values(), key=lambda e: (not e["agir"], -e["nivel"], -e["n"], e["nome"]))
    return camada


def _camada_focos(focos_l, indice, usinas: list, v: Vista, qualifica: list, ref=None) -> dict:
    """Todos os focos da última hora, cada um um ponto do tamanho do traço (o caminho `h.01` com ponta redonda: uns 5 mil focos
    num `<path>` só pesam 70 KB, e como `<circle>` seriam 190 KB), e o anel nos que estão a até 5 km de ALGUMA usina do cadastro
    (dentro ou fora do recorte: o foco é que tem de estar na vista). Foco em cima de foco, no desenho, vira um ponto só."""
    camada = {"estado": _estado_da_camada(focos_l), "d": "", "n": 0, "n_perto": 0, "aneis": [], "r_anel": R_ANEL,
              "qualifica": qualifica, "lido": ""}
    if indice is None:
        return camada
    camada["lido"] = V.hora(datetime.fromtimestamp(focos_l.lido_em, V.BRT), ref or V.agora()) if focos_l.lido_em else ""
    pontos = set()
    for f in focos_l.dados["focos"]:
        x, y = v.ponto(f.lat, f.lon)
        if v.dentro(x, y, FOLGA_PONTO):
            camada["n"] += 1
            pontos.add((round(x, 1), round(y, 1)))
    camada["d"] = "".join(f"M{_n(x)} {_n(y)}h.01" for x, y in sorted(pontos))
    aneis = set()
    for u in usinas:
        for _km, f in indice.no_raio(u.lat, u.lon):
            x, y = v.ponto(f.lat, f.lon)
            if v.dentro(x, y, FOLGA_PONTO):
                aneis.add((round(x, 1), round(y, 1)))
    camada["aneis"] = [{"x": _n(x), "y": _n(y), "r": R_ANEL} for x, y in sorted(aneis)]
    camada["n_perto"] = len(aneis)
    return camada


# ── as camadas de calor (09/10/2026) ─────────────────────────────────────────────────────────────────────────────────

# A grade fixa que escolhe as tiles do INPE que encostam no Brasil (a máscara do contorno, em quadrados de 0,08 grau).
_GRADE_BRASIL = C.grade_de_caixa(*LIMITES_BRASIL, F.GRADE_GRAUS)
_DESENHOS: dict = {}                                 # o desenho de cada camada de calor, por leitura e por recorte
_DESENHOS_MAX = 16


def _guardado(chave, fazer):
    """O desenho da camada de calor é a conta pesada da tela (até ~0,3 s no Brasil inteiro): sai uma vez por leitura da fonte e por
    recorte, e as visitas seguintes (e o modo TV, que relê a página) o reaproveitam."""
    if chave in _DESENHOS:
        return _DESENHOS[chave]
    valor = fazer()
    while len(_DESENHOS) >= _DESENHOS_MAX:
        _DESENHOS.pop(next(iter(_DESENHOS)), None)
    _DESENHOS[chave] = valor
    return valor


@lru_cache(maxsize=1)
def aneis_do_brasil() -> tuple:
    """Todos os anéis dos 27 estados (o de fora e os buracos), para a máscara do calor: o desenho entra até a costa e a fronteira,
    e o recorte do SVG corta no contorno."""
    return tuple(anel for e in estados() for poligono in e.poligonos for anel in poligono)


@lru_cache(maxsize=8)
def divisas_da_vista(v: Vista) -> str:
    """O contorno dos estados num caminho só, desenhado POR CIMA de uma camada de calor (que cobre a terra inteira)."""
    return "".join(u.d for u in ufs_da_vista(v))


def _pct(n: int, total: int) -> str:
    if not total or not n:
        return "0%"
    p = 100 * n / total
    return "menos de 1%" if p < 0.5 else f"{round(p)}%"


def _desenhar_classes(classes, grade, v: Vista, aneis, tabela) -> dict:
    desenhar = C.mascara(grade, aneis, 1) if aneis else None
    contar = C.mascara(grade, aneis, 0) if aneis else None
    f = C.faixas(classes, grade, v, desenhar=desenhar, contar=contar)
    total = f["com_dado"] + f["sem_dado"]
    return {"altura": f["altura"], "sem_dado_pct": _pct(f["sem_dado"], total), "com_dado": f["com_dado"],
            "classes": [{**c, "d": f["caminhos"].get(c["id"], ""), "n": f["contagem"][c["id"]],
                         "pct": _pct(f["contagem"][c["id"]], total)} for c in tabela],
            "lado_km": round(grade.dlat * C.KM_POR_GRAU)}


def _dia_padrao(rotulos: list) -> int:
    """O dia "Hoje" do arquivo do INPE: o 0 quando o arquivo é de hoje, o 1 quando ainda é o de ontem (antes das ~06:30)."""
    return rotulos.index("Hoje") if "Hoje" in rotulos else 0


def _camada_risco(config, sessao, v: Vista, dia, ref, arquivo_dos_pontos, aneis) -> dict:
    """O risco de fogo do INPE em quadrados, no dia escolhido (hoje por padrão; os quatro dias da previsão), lido ao fundo: a
    primeira visita diz "lendo" e a tela se atualiza quando a leitura termina. O que a cor quer dizer, a data da previsão, a hora
    da leitura e quanto da área ficou sem dado vão na legenda."""
    precisa = C.precisa_de_tile(_GRADE_BRASIL, aneis) if aneis else None
    # o dia padrão é o "Hoje" do arquivo que o risco por usina já leu; os nomes dos dias saem da data do arquivo do mapa de calor
    # (no meio da troca diária os dois podem ser de dias diferentes por uns minutos, e o nome continua certo para o que se vê)
    base = arquivo_dos_pontos
    dia = _dia_padrao(V.rotulos_dos_dias(base, ref)) if dia is None else dia
    leitura = L.risco_grade(config, dia, LIMITES_BRASIL, precisa, sessao)
    dados = leitura.dados
    if dados and dados.get("modificado"):
        base = dados["modificado"]
    nomes = V.dias_amigaveis(base, ref)
    nome_fonte = f"{F.extenso('inpe')} · risco de fogo"
    camada = {"estado": _estado_da_camada(leitura), "dia": dia, "dia_nome": nomes[dia],
              "dias": [{"i": i, "nome": nomes[i], "atual": i == dia} for i in range(len(nomes))], "classes": [], "altura": "",
              "texto": "", "detalhe": "", "qualifica": [], "sem_dado_pct": "", "lado_km": 0, "leitura": leitura}
    falha = V._falha(nome_fonte, leitura, ref)
    if dados is None:
        camada["texto"] = (f"{nome_fonte}: lendo a área do Brasil no arquivo do INPE (leva alguns segundos; o mapa se atualiza "
                           "sozinho)" if leitura.erro == L.LENDO else falha[1])
        camada["detalhe"] = falha[2]
        return camada
    if falha is not None:                                         # a última leitura boa, dita velha, com a hora
        camada["texto"], camada["detalhe"] = falha[1], falha[2]
        camada["qualifica"].append(f"dado de {V.hora(datetime.fromtimestamp(leitura.lido_em, V.BRT), ref)}")
    modificado = dados.get("modificado")
    lido = V.hora(datetime.fromtimestamp(leitura.lido_em, V.BRT), ref)
    if modificado is None:
        camada["qualifica"].append("sem data do arquivo")
        texto = f"{nome_fonte}: previsão para {nomes[dia]} · sem data do arquivo · lido às {lido}"
    else:
        a = modificado.astimezone(V.BRT)
        texto = f"{nome_fonte}: previsão para {nomes[dia]}, do arquivo de {a:%d/%m} às {a:%H:%M} · lido às {lido}"
        if a.date() != ref.astimezone(V.BRT).date():
            camada["qualifica"].append(f"previsão de {a:%d/%m}")
    if falha is None:
        camada["texto"] = texto
    k = C.JUNTA_NO_BRASIL if v.id == BRASIL else 1
    chave = ("risco", dados.get("validador") or id(dados["grade"]), dados.get("url"), v.id, k)

    def desenhar():
        grade, soma, n = C.juntar(dados["grade"], k)
        classes = C.classes_do_risco(soma, n, dados["grade"]["px_por_bloco"] * k * k)
        return _desenhar_classes(classes, grade, v, aneis, C.CLASSES_RISCO)
    camada.update(_guardado(chave, desenhar))
    return camada


def _camada_densidade(focos_l, v: Vista, aneis, qualifica: list, ref) -> dict:
    """A densidade dos focos da última hora (o núcleo de 25 km), dos MESMOS focos da camada de pontos: sem leitura dos focos, sem
    camada, e a legenda diz por quê."""
    raio = C.RAIO_KM_BRASIL if v.id == BRASIL else C.RAIO_KM
    pico = 3.0 / (math.pi * raio * raio) * C.POR_AREA_KM2       # o que um foco sozinho dá no centro dele (a régua da legenda)
    camada = {"estado": _estado_da_camada(focos_l), "classes": [], "altura": "", "texto": "", "qualifica": qualifica,
              "raio_km": raio, "pico_um": V.numero(pico, 2 if pico < 1 else 1), "n_focos": 0, "sem_dado_pct": "", "lado_km": 0}
    nome_fonte = f"focos de queimada do {F.extenso('inpe')}"
    if focos_l.dados is None:
        camada["texto"] = (f"Lendo os {nome_fonte}: a densidade aparece quando a leitura terminar" if focos_l.erro == L.LENDO
                           else f"Sem leitura boa dos {nome_fonte}: a densidade não aparece")
        return camada
    focos = focos_l.dados["focos"]
    camada["n_focos"] = sum(1 for f in focos if v.lon_oeste <= f.lon <= v.lon_leste and v.lat_sul <= f.lat <= v.lat_norte)
    ate = V.hora(focos_l.dados["ate"], ref)
    lido = V.hora(datetime.fromtimestamp(focos_l.lido_em, V.BRT), ref)
    camada["texto"] = (f"Calculada no Nexus com os {V.milhar(camada['n_focos'])} {'foco' if camada['n_focos'] == 1 else 'focos'} "
                       f"da última hora do {F.extenso('inpe')} (arquivos até {ate}, lidos às {lido}): cada foco pesa até "
                       f"{raio:g} km em volta dele.")
    k = C.JUNTA_NO_BRASIL if v.id == BRASIL else 1
    margem = raio / C.KM_POR_GRAU
    grade = C.grade_de_caixa(v.lon_oeste - margem, v.lat_sul - margem, v.lon_leste + margem, v.lat_norte + margem,
                             F.GRADE_GRAUS * k)
    chave = ("densidade", focos_l.lido_em, len(focos), id(focos), v.id, k, raio)

    def desenhar():
        return _desenhar_classes(C.classes_da_densidade(C.densidade(focos, grade, raio)), grade, v, aneis,
                                 C.CLASSES_DENSIDADE)
    camada.update(_guardado(chave, desenhar))
    return camada


# ── a usina ──────────────────────────────────────────────────────────────────────────────────────────────────────────

def _motivos(avisos: list, foco, dias: list, ref) -> str:
    """Por que a usina está no nível dela, em uma linha para o `<title>`: o foco, os avisos (os que mandam agir antes) e os dias
    de risco de fogo alto. Sem repetir e com no máximo MOTIVOS_NO_TITULO: lista de 8 avisos de baixa umidade não cabe num balão."""
    itens = []
    if foco:
        itens.append(f"foco de queimada a {V.numero(foco['km'], 1)} km")
    for a in sorted(avisos, key=lambda a: not A.aviso_manda_agir(a)):
        itens.append(f"{a.evento} ({a.severidade}, {V._validade(a, ref)})")
    com_risco = [c for c in dias if c["nivel"] > 0]
    if com_risco:
        classe = "crítico" if any(c["classe"] == "crítico" for c in com_risco) else "alto"
        itens.append(f"risco de fogo {classe} ({', '.join(c['rotulo'] for c in com_risco)})")
    itens = list(dict.fromkeys(itens))
    if len(itens) > MOTIVOS_NO_TITULO:
        itens = itens[:MOTIVOS_NO_TITULO] + [f"e mais {len(itens) - MOTIVOS_NO_TITULO}"]
    return "; ".join(itens)


def _fontes_que_pesaram(avisos, foco, dias, ref, sem_leitura_de: str, completa: bool) -> list:
    """As fontes que pesaram no nível da usina, cada uma com o nome por extenso e o que ela trouxe (a dica do mapa, 09/10/2026:
    "dica ao passar o mouse na usina (nome, nível, o motivo, as fontes que pesaram)"). [[fonte, o que trouxe], ...]."""
    itens = []
    for e in V.por_evento(V.agrupar_avisos(avisos, ref), ref):
        itens.append([F.extenso("inmet"), f"{e['nome']} ({e['severidade']}), {e['quando']}"])
    if foco:
        itens.append([F.extenso("inpe"), f"foco de queimada a {V.numero(foco['km'], 1)} km, visto pelo satélite "
                                         f"{foco['satelite']} às {V.hora(foco['hora'], ref)}"])
    com_numero = [c for c in dias if c.get("_num") is not None]
    if V.risco_curto(dias):
        maior = max(c["_num"] for c in dias if c["nivel"] > 0)
        itens.append([F.extenso("inpe"), f"{V.risco_curto(dias).lower()} (até {V.numero(maior)})"])
    if itens:
        return itens
    if sem_leitura_de:
        return [["", f"Sem leitura de {sem_leitura_de}: não dá para dizer que não há alerta"]]
    maior = max((c["_num"] for c in com_numero), default=None)
    risco = f"; risco de fogo até {V.numero(maior)}" if maior is not None else ""
    return [["", "Nenhum aviso, nenhum foco a até 5 km e risco de fogo abaixo de alto" + ("" if completa else
             " nas fontes lidas") + risco]]


def montar(config, *, cadastro=None, erro_cadastro=None, regiao="", ref=None, sessao=None, fundo=FUNDO_PADRAO, ver=None,
           dia=None, cliente="", ocultar=frozenset(), sem_eventos=frozenset(), tv=False, girar=None) -> dict:
    """Tudo o que o template do mapa precisa. `cadastro` é o `usinas.Cadastro` (ou None com `erro_cadastro` dizendo por quê); o
    resto é o estado da tela (`estado_da_tela`): a camada de fundo, as de cima, o dia do risco de fogo, o cliente, os níveis e os
    eventos escondidos, e o modo TV com o giro das camadas.

    O mapa lê as MESMAS três fontes da tela principal, pelo mesmo cache (uma visita a uma e outra não vai duas vezes à rede), e
    o nível de cada usina vem da mesma regra (`alertas.nivel_da_usina`). O painel de frescor é o mesmo código da tela principal
    (`visao._fonte_*`): o mapa não reescreve o texto de "lido às", "parcial" ou "fora agora". As camadas de calor (09/10/2026) vêm
    das mesmas fontes: o risco de fogo, do mesmo arquivo do INPE, lido na área (só quando a camada está ligada), e a densidade, dos
    mesmos focos.

    A honestidade da tela principal vale aqui: a camada de uma fonte sem leitura some e a legenda diz por quê, e a usina que
    ficaria "Sem alerta" com uma fonte sem leitura fica cinza ("Sem leitura completa"), nunca verde: sem ler os avisos, não
    dá para dizer que não há aviso.
    """
    ref = ref or V.agora()
    try:
        v = vista(regiao)
        ufs = ufs_da_vista(v)
        aneis = aneis_do_brasil()
        erro_contorno = ""
    except (ValueError, OSError):
        # O contorno é um arquivo do repositório: se faltar ou vier quebrado, o mapa sai sem as divisas (e sem o recorte por
        # região, que sai das caixas dos estados), e a tela diz; o motivo vai ao log. Antes disto seria um 500.
        log.exception("clima: o contorno dos estados do IBGE não abriu")
        v, ufs, aneis = vista_de_caixa(BRASIL, "Brasil", *LIMITES_BRASIL), (), ()
        erro_contorno = ("O contorno dos estados não abriu (o motivo está no log do servidor): o mapa sai sem as divisas e sem o "
                         "recorte por região.")
    fundo = fundo if fundo in FUNDOS else FUNDO_PADRAO
    ver = frozenset(SOBRE) if ver is None else frozenset(ver) & frozenset(SOBRE)
    girar = girar if tv else None
    # O que o SVG desenha: a camada de fundo escolhida; no modo TV com giro, as três (a troca é do navegador, sem pedir de novo).
    fundos_no_svg = list(GIRO) if girar else ([fundo] if fundo != "nenhum" else [])
    estado = {"regiao": v.id if v.id != BRASIL else "", "fundo": fundo, "ver": None if ver == frozenset(SOBRE) else ver,
              "dia": dia, "cliente": "", "ocultar": frozenset(ocultar) & frozenset(NIVEIS), "sem_eventos": frozenset(sem_eventos),
              "tv": bool(tv), "girar": girar}
    m = {"erro_cadastro": erro_cadastro, "erro_contorno": erro_contorno, "atualizada": V.hora(ref, ref), "regiao": v.id,
         "regiao_nome": v.nome,
         "regioes": [{"id": BRASIL, "nome": "Brasil", "atual": v.id == BRASIL},
                     *({"id": r, "nome": n, "atual": v.id == r} for r, n in REGIOES.items())],
         "viewbox": v.viewbox, "ufs": ufs, "usinas": [], "contagem": {A.AGIR: 0, A.ATENCAO: 0, A.SEM_ALERTA: 0, NX: 0},
         "n_usinas": 0, "n_no_recorte": 0, "fora_do_recorte": 0, "sem_usinas": False, "rotulo_sem": "Sem alerta",
         "sem_leitura_de": "", "camada_avisos": None, "camada_focos": None, "fontes": [], "faltando": [], "lendo": [],
         "completa": True, "recarrega_em": V.RECARGA_S, "sem_coordenada": [], "fora_do_brasil": [], "ilegiveis": 0,
         "tabela": [], "fundo": fundo, "fundos": FUNDOS, "fundos_no_svg": fundos_no_svg, "giro": GIRO, "ver": ver,
         "sobre": SOBRE, "ocultar": estado["ocultar"], "tv": bool(tv), "girar": girar, "calor_risco": None,
         "calor_densidade": None, "divisas": "", "clientes": [], "cliente": "", "dados_js": {}, "proxima_s": V.RECARGA_S,
         "nomes": {k: F.extenso(k) for k in F.NOMES}, "estado": estado, "links": _links(estado, [])}
    if cadastro is None:
        return m
    m["clientes"] = cadastro.clientes()
    m["cliente"] = estado["cliente"] = cliente if cliente in m["clientes"] else ""

    def pertence(u):
        return not m["cliente"] or u.cliente == m["cliente"]

    usinas = [u for u in cadastro.usinas if pertence(u)]
    m["sem_coordenada"] = [u.nome for u in cadastro.sem_coordenada if pertence(u)]
    m["fora_do_brasil"] = [u.nome for u in cadastro.fora_do_brasil if pertence(u)]
    m["ilegiveis"] = cadastro.ilegiveis
    m["n_usinas"] = len(usinas)
    m["links"] = _links(estado, [])
    if not usinas:
        m["sem_usinas"] = True            # nada a cruzar: nem se vai à rede
        return m

    avisos_l = L.avisos(config, sessao)
    focos_l = L.focos(config, sessao)
    # o risco de fogo é lido para TODAS as usinas com coordenada (o cache vale pelo conjunto de pontos); o filtro é da tela
    risco_l = L.risco(config, cadastro.pontos(), sessao)
    indice = A.IndiceFocos(focos_l.dados["focos"]) if focos_l.dados else None
    arquivo = V._arquivo_t0(risco_l.dados) if risco_l.dados else None
    rotulos, amigaveis = V.rotulos_dos_dias(arquivo, ref), V.dias_amigaveis(arquivo, ref)
    fontes = [V._fonte_inmet(avisos_l, ref), V._fonte_focos(focos_l, ref), V._fonte_risco(risco_l, ref, rotulos)]
    por_id = {f["id"]: f for f in fontes}
    leituras = {"inmet": avisos_l, "focos": focos_l, "risco": risco_l}
    ausentes = [V.NOME_LONGO[i] for i in _FONTES if leituras[i].dados is None]       # na ordem do painel das fontes
    m["fontes"] = fontes
    m["lendo"] = [V.NOME_LONGO[i] for i in _FONTES if leituras[i].dados is None and leituras[i].erro == L.LENDO]
    m["faltando"] = [V.NOME_LONGO[i] for i in _FONTES if leituras[i].dados is None and leituras[i].erro != L.LENDO]
    m["completa"] = all(f["estado"] == "ok" for f in fontes)
    m["recarrega_em"] = V.RECARGA_LENDO_S if m["lendo"] else V.RECARGA_S
    m["sem_leitura_de"] = _juntar(ausentes) if ausentes else ""
    m["rotulo_sem"] = "Sem alerta" if m["completa"] else "Sem alerta nas fontes lidas"
    m["camada_avisos"] = _camada_avisos(avisos_l, v, ref, por_id["inmet"]["qualifica"], estado["sem_eventos"])
    m["camada_focos"] = _camada_focos(focos_l, indice, usinas, v, por_id["focos"]["qualifica"], ref)
    m["links"] = _links(estado, m["camada_avisos"]["eventos"])
    usadas = [avisos_l, focos_l, risco_l]
    if "risco" in fundos_no_svg:
        m["calor_risco"] = _camada_risco(config, sessao, v, dia, ref, arquivo, aneis)
        usadas.append(m["calor_risco"].pop("leitura"))
    if "densidade" in fundos_no_svg:
        m["calor_densidade"] = _camada_densidade(focos_l, v, aneis, por_id["focos"]["qualifica"], ref)
    if ufs and any(c and c.get("classes") for c in (m["calor_risco"], m["calor_densidade"])):
        m["divisas"] = divisas_da_vista(v)           # só com uma camada de calor desenhada: ela cobre a terra e as divisas da terra
    # a próxima atualização do mapa (e do modo TV): quando o cache da primeira fonte vencer, nunca antes (09/10/2026)
    m["proxima_s"] = V.proxima_leitura_s(usadas)

    todos_os_avisos = avisos_l.dados["avisos"] if avisos_l.dados else []
    rotulo_do_nivel = {**A.ROTULO_NIVEL, A.SEM_ALERTA: m["rotulo_sem"], NX: ROTULO_NX}
    desenhadas, dicas = [], {}
    for u in usinas:
        x, y = v.ponto(u.lat, u.lon)
        if not v.dentro(x, y):
            m["fora_do_recorte"] += 1
            continue
        avisos = A.avisos_que_contem(u.lat, u.lon, todos_os_avisos, ref)
        foco = indice.perto(u.lat, u.lon) if indice is not None else None
        dias = ([V.celula_de_risco(i, a, rotulos, amigaveis) for i, a in enumerate(risco_l.dados["por_ponto"].get(u.id, []))]
                if risco_l.dados else [])
        nivel = A.nivel_da_usina(avisos, foco is not None, any(c["nivel"] > 0 for c in dias))
        if nivel == A.SEM_ALERTA:
            if ausentes:
                nivel = NX
                motivo = f"sem leitura de {m['sem_leitura_de']}; não dá para dizer que não há alerta"
                curto = f"Sem leitura de {m['sem_leitura_de']}"
            else:
                motivo = "nenhum aviso, foco a até 5 km nem risco de fogo alto" + ("" if m["completa"] else " nas fontes lidas")
                curto = "Nada previsto" + ("" if m["completa"] else " nas fontes lidas")
        else:
            motivo = _motivos(avisos, foco, dias, ref)
            curto = V.motivo_curto(avisos, foco, dias, ref)
        m["contagem"][nivel] += 1
        gravidade = max([a.nivel for a in avisos] + [3 if foco else 0] + [c["nivel"] for c in dias] + [0])
        desenhadas.append({
            "id": u.id, "nome": u.nome, "nivel": nivel, "x": _n(x), "y": _n(y), "r": R_USINA[nivel],
            "r_alvo": round(R_USINA[nivel] * R_ALVO, 1), "href": URL_USINA.format(quote(str(u.id), safe="")),
            "titulo": f"{u.nome}\nCliente: {u.cliente}\nNível: {rotulo_do_nivel[nivel]}\nMotivo: {motivo}",
            # a tabela ao lado do mapa (Levi, 09/10/2026: "na direita uma tabela com o nome das usinas, os riscos e uma forma
            # resumida do motivo do risco"): o mesmo motivo curto da tabela da Atenção da lista
            "onde": f"{u.cliente} · {u.uf}" if u.uf else u.cliente, "rotulo": rotulo_do_nivel[nivel], "motivo_curto": curto,
            "_ordem": (ORDEM_DA_TABELA[nivel], -gravidade, u.nome.casefold())})
        # a dica do mapa (09/10/2026): o nome, o nível, o motivo e as fontes que pesaram, cada uma por extenso. Vai num JSON da
        # página (escapado pelo |tojson), lido pelo JavaScript; texto de terceiros entra no balão por textContent, nunca como HTML.
        dicas[u.id] = {"n": u.nome, "o": desenhadas[-1]["onde"], "v": nivel, "r": rotulo_do_nivel[nivel], "m": curto,
                       "f": _fontes_que_pesaram(avisos, foco, dias, ref, m["sem_leitura_de"] if nivel == NX else "",
                                                m["completa"])}
    m["tabela"] = sorted(desenhadas, key=lambda d: d["_ordem"])
    desenhadas.sort(key=lambda d: (ORDEM_DE_DESENHO[d["nivel"]], d["nome"].casefold()))
    m["usinas"] = desenhadas
    m["n_no_recorte"] = len(desenhadas)
    m["dados_js"] = _dados_js(m, v, dicas)
    return m


def _caixa_svg(v: Vista, caixa) -> list:
    """A caixa (lon mín., lat mín., lon máx., lat máx.) em unidades do SVG, [x0, y0, x1, y1]: o zoom do clique no estado."""
    x0, y0 = v.ponto(caixa[3], caixa[0])
    x1, y1 = v.ponto(caixa[1], caixa[2])
    return [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]


def _dados_js(m: dict, v: Vista, dicas: dict) -> dict:
    """O que o JavaScript do mapa lê da página: as dicas das usinas, o nome e a caixa (em unidades do desenho) de cada estado
    para o clique aproximar, o que cada classe de calor quer dizer, os nomes das fontes por extenso e o giro do modo TV (a próxima
    atualização vai no atributo data-proxima-s da página).
    Nenhum número de latitude ou longitude: só posições no desenho, como o `cx`/`cy` dos pontos."""
    caixas = {}
    try:
        caixas = {e.sigla: {"nome": e.nome, "caixa": _caixa_svg(v, e.caixa)} for e in estados() if v.cruza(e.caixa)}
    except (ValueError, OSError):
        pass
    calor = {}
    for chave, camada, unidade in (("risco", m["calor_risco"], "risco de fogo de 0 a 1"),
                                   ("densidade", m["calor_densidade"], "focos por 1.000 km²")):
        if camada and camada.get("classes"):
            calor[chave] = {"classes": {str(c["id"]): f"{c['rotulo']}: {c['faixa']} ({unidade})" for c in camada["classes"]},
                            "lado_km": camada["lado_km"]}
    return {"usinas": dicas, "ufs": caixas, "calor": calor, "nomes": m["nomes"], "regiao": m["regiao"],
            "giro": list(GIRO) if m["girar"] else [], "girar": m["girar"] or 0}
