"""O Mapa de risco (07/10/2026): o contorno dos estados, a projeção e o recorte de cada região, sem Flask.

Pedido do Levi (07/10): a lista do Clima e risco ganha um mapa do Brasil, com as usinas na cor do nível, os avisos do INMET e
os focos do INPE. O SVG nasce no servidor: nada de biblioteca de JavaScript, de mapa de terceiros ou de dependência nova, e
nenhuma busca ao IBGE em tempo de execução.

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
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple
from urllib.parse import quote

from . import alertas as A
from . import leitura as L
from . import visao as V

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
# Raios em unidades do SVG (o viewBox tem 1000 de largura): a usina que pede ação é maior que a que está bem, e o anel do foco
# cobre o ponto da usina que está a até 5 km dele. No celular o CSS os multiplica (o SVG ali tem uns 340 px, não 700).
R_USINA = {A.AGIR: 7.5, A.ATENCAO: 6.0, A.SEM_ALERTA: 5.0, NX: 5.0}
R_ALVO = 2.2                                         # o círculo invisível que aumenta a área de toque: R_ALVO vezes o raio
R_ANEL = 12.0
FOLGA_PONTO = 4.0                                    # foco um pouco fora do viewBox ainda desenha (o ponto tem espessura)
MOTIVOS_NO_TITULO = 3
_NOMES_DAS_FONTES = (("avisos do INMET", "inmet"), ("focos do INPE", "focos"), ("risco de fogo do INPE", "risco"))


def _juntar(nomes: list) -> str:
    """["a", "b", "c"] -> "a, b e c" (o mesmo da tela principal)."""
    return nomes[0] if len(nomes) == 1 else ", ".join(nomes[:-1]) + " e " + nomes[-1]


def _aneis_do_aviso(geometria_) -> list:
    """Todos os anéis de um Polygon ou MultiPolygon do INMET (o de fora e os buracos de cada pedaço): o `evenodd` do SVG faz
    do buraco um buraco. O `Aviso` só nasce com geometria que o `geometria.caixa` já aceitou."""
    coords = geometria_["coordinates"]
    poligonos = [coords] if geometria_["type"] == "Polygon" else coords
    return [anel for poligono in poligonos for anel in poligono]


def _estado_da_camada(leitura) -> str:
    return "ok" if leitura.dados is not None else ("lendo" if leitura.erro == L.LENDO else "fora")


def _camada_avisos(avisos_l, v: Vista, ref, qualifica: list) -> dict:
    """Os polígonos do INMET que valem agora ou valerão (o vencido não desenha) e encostam no recorte, em grupos por nível e por
    "já em vigor" ou "ainda vai começar": o grupo vira uma camada translúcida do CSS, e o aviso que ainda não começou vai só no
    contorno. Do mais leve para o mais grave, que fica por cima."""
    camada = {"estado": _estado_da_camada(avisos_l), "grupos": [], "n_vigor": 0, "n_futuros": 0, "ignorados": 0,
              "qualifica": qualifica}
    if avisos_l.dados is None:
        return camada
    camada["ignorados"] = len(avisos_l.dados["ignorados"])
    grupos = {}
    for a in avisos_l.dados["avisos"]:
        if (a.fim is not None and a.fim < ref) or not v.cruza(a.caixa):
            continue
        d = caminho(_aneis_do_aviso(a.geometria), v)
        if not d:
            continue
        futuro = not A.em_vigor(a, ref)
        grupos.setdefault((futuro, a.nivel), []).append(
            {"d": d, "titulo": f"{a.evento} · {a.severidade} · {V._validade(a, ref)}"})
    for (futuro, nivel), itens in sorted(grupos.items()):
        camada["grupos"].append({"nivel": nivel, "futuro": futuro, "itens": itens})
        camada["n_futuros" if futuro else "n_vigor"] += len(itens)
    return camada


def _camada_focos(focos_l, indice, usinas: list, v: Vista, qualifica: list) -> dict:
    """Todos os focos da última hora, cada um um ponto do tamanho do traço (o caminho `h.01` com ponta redonda: uns 5 mil focos
    num `<path>` só pesam 70 KB, e como `<circle>` seriam 190 KB), e o anel nos que estão a até 5 km de ALGUMA usina do cadastro
    (dentro ou fora do recorte: o foco é que tem de estar na vista). Foco em cima de foco, no desenho, vira um ponto só."""
    camada = {"estado": _estado_da_camada(focos_l), "d": "", "n": 0, "n_perto": 0, "aneis": [], "r_anel": R_ANEL,
              "qualifica": qualifica}
    if indice is None:
        return camada
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


def montar(config, *, cadastro=None, erro_cadastro=None, regiao="", ref=None, sessao=None) -> dict:
    """Tudo o que o template do mapa precisa. `cadastro` é o `usinas.Cadastro` (ou None com `erro_cadastro` dizendo por quê).

    O mapa lê as MESMAS três fontes da tela principal, pelo mesmo cache (uma visita a uma e outra não vai duas vezes à rede), e
    o nível de cada usina vem da mesma regra (`alertas.nivel_da_usina`). O painel de frescor é o mesmo código da tela principal
    (`visao._fonte_*`): o mapa não reescreve o texto de "lido às", "parcial" ou "fora agora".

    A honestidade da tela principal vale aqui: a camada de uma fonte sem leitura some e a legenda diz por quê, e a usina que
    ficaria "Sem alerta" com uma fonte sem leitura fica cinza ("Sem leitura completa"), nunca verde: sem ler os avisos, não
    dá para dizer que não há aviso.
    """
    ref = ref or V.agora()
    v = vista(regiao)
    m = {"erro_cadastro": erro_cadastro, "atualizada": V.hora(ref, ref), "regiao": v.id, "regiao_nome": v.nome,
         "regioes": [{"id": BRASIL, "nome": "Brasil", "atual": v.id == BRASIL},
                     *({"id": r, "nome": n, "atual": v.id == r} for r, n in REGIOES.items())],
         "viewbox": v.viewbox, "ufs": (), "usinas": [], "contagem": {A.AGIR: 0, A.ATENCAO: 0, A.SEM_ALERTA: 0, NX: 0},
         "n_usinas": 0, "n_no_recorte": 0, "fora_do_recorte": 0, "sem_usinas": False, "rotulo_sem": "Sem alerta",
         "sem_leitura_de": "", "camada_avisos": None, "camada_focos": None, "fontes": [], "faltando": [], "lendo": [],
         "completa": True, "recarrega_em": V.RECARGA_S, "sem_coordenada": [], "fora_do_brasil": [], "ilegiveis": 0}
    if cadastro is None:
        return m
    m["sem_coordenada"] = [u.nome for u in cadastro.sem_coordenada]
    m["fora_do_brasil"] = [u.nome for u in cadastro.fora_do_brasil]
    m["ilegiveis"] = cadastro.ilegiveis
    m["n_usinas"] = len(cadastro.usinas)
    if not cadastro.usinas:
        m["sem_usinas"] = True            # nada a cruzar: nem se vai à rede
        return m

    avisos_l = L.avisos(config, sessao)
    focos_l = L.focos(config, sessao)
    risco_l = L.risco(config, cadastro.pontos(), sessao)
    indice = A.IndiceFocos(focos_l.dados["focos"]) if focos_l.dados else None
    rotulos = V.rotulos_dos_dias(V._arquivo_t0(risco_l.dados) if risco_l.dados else None, ref)
    fontes = [V._fonte_inmet(avisos_l, ref), V._fonte_focos(focos_l, ref), V._fonte_risco(risco_l, ref, rotulos)]
    por_id = {f["id"]: f for f in fontes}
    leituras = {"inmet": avisos_l, "focos": focos_l, "risco": risco_l}
    ausentes = [n for n, id_ in _NOMES_DAS_FONTES if leituras[id_].dados is None]       # na ordem do painel das fontes
    m["fontes"] = fontes
    m["lendo"] = [n for n, id_ in _NOMES_DAS_FONTES if leituras[id_].dados is None and leituras[id_].erro == L.LENDO]
    m["faltando"] = [n for n, id_ in _NOMES_DAS_FONTES if leituras[id_].dados is None and leituras[id_].erro != L.LENDO]
    m["completa"] = all(f["estado"] == "ok" for f in fontes)
    m["recarrega_em"] = V.RECARGA_LENDO_S if m["lendo"] else V.RECARGA_S
    m["sem_leitura_de"] = _juntar(ausentes) if ausentes else ""
    m["rotulo_sem"] = "Sem alerta" if m["completa"] else "Sem alerta nas fontes lidas"
    m["camada_avisos"] = _camada_avisos(avisos_l, v, ref, por_id["inmet"]["qualifica"])
    m["camada_focos"] = _camada_focos(focos_l, indice, cadastro.usinas, v, por_id["focos"]["qualifica"])

    todos_os_avisos = avisos_l.dados["avisos"] if avisos_l.dados else []
    rotulo_do_nivel = {**A.ROTULO_NIVEL, A.SEM_ALERTA: m["rotulo_sem"], NX: ROTULO_NX}
    desenhadas = []
    for u in cadastro.usinas:
        x, y = v.ponto(u.lat, u.lon)
        if not v.dentro(x, y):
            m["fora_do_recorte"] += 1
            continue
        avisos = A.avisos_que_contem(u.lat, u.lon, todos_os_avisos, ref)
        foco = indice.perto(u.lat, u.lon) if indice is not None else None
        dias = ([V.celula_de_risco(i, a, rotulos) for i, a in enumerate(risco_l.dados["por_ponto"].get(u.id, []))]
                if risco_l.dados else [])
        nivel = A.nivel_da_usina(avisos, foco is not None, any(c["nivel"] > 0 for c in dias))
        if nivel == A.SEM_ALERTA:
            if ausentes:
                nivel = NX
                motivo = f"sem leitura de {m['sem_leitura_de']}; não dá para dizer que não há alerta"
            else:
                motivo = "nenhum aviso, foco a até 5 km nem risco de fogo alto" + ("" if m["completa"] else " nas fontes lidas")
        else:
            motivo = _motivos(avisos, foco, dias, ref)
        m["contagem"][nivel] += 1
        desenhadas.append({
            "id": u.id, "nome": u.nome, "nivel": nivel, "x": _n(x), "y": _n(y), "r": R_USINA[nivel],
            "r_alvo": round(R_USINA[nivel] * R_ALVO, 1), "href": URL_USINA.format(quote(str(u.id), safe="")),
            "titulo": f"{u.nome}\nCliente: {u.cliente}\nNível: {rotulo_do_nivel[nivel]}\nMotivo: {motivo}"})
    desenhadas.sort(key=lambda d: (ORDEM_DE_DESENHO[d["nivel"]], d["nome"].casefold()))
    m["usinas"] = desenhadas
    m["n_no_recorte"] = len(desenhadas)
    m["ufs"] = ufs_da_vista(v)
    return m
