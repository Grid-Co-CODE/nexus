"""As camadas de calor do Mapa de risco (09/10/2026): o risco de fogo do INPE em quadrados e a densidade dos focos de queimada,
sem Flask.

Levi, 09/10/2026: "Além de tempestade conseguimos uma outra visão tipo um mapa de calor no mapa? quanto mais versatilidade
melhor!". As duas camadas saem das fontes que o Nexus JÁ lê, sem saída nova para a internet:

- Risco de fogo (INPE): o mesmo GeoTIFF do risco por usina, agora lido na área do Brasil (`fontes.inpe_risco_grade`) e resumido
  em quadrados de ~9 km (~18 km no Brasil inteiro): a MÉDIA dos pixels de ~1 km com dado, nas cinco classes do INPE. Quadrado com
  menos de 1/4 dos pixels com dado (cidade, água, sem vegetação) fica SEM COR: o INPE não calculou ali, e o mapa não inventa. A
  usina usa o pixel dela (ou o maior do entorno de 2 km), então a cor da usina pode ser outra que a do quadrado: a legenda diz.
- Densidade de focos (INPE): os focos da última hora (o mesmo CSV) somados por um núcleo quártico (50 km no Brasil inteiro, 25 km
  numa região), em focos por 1.000 km². Sem foco no raio do centro do quadrado a densidade é zero e o quadrado fica sem cor (é
  dado: nenhum foco perto).

O desenho é vetorial: cada classe é UM `<path>` de faixas horizontais (o traço tem a altura do quadrado), recortado no SVG pelo
contorno do Brasil. A cor é da classe (o CSS dá o token, nos dois temas), nunca do Python.
"""
import math
from array import array
from dataclasses import dataclass
from functools import lru_cache

from . import alertas as A

KM_POR_GRAU = 111.195            # o mesmo raio da Terra da `geometria.distancia_km` (6371 km)
JUNTA_NO_BRASIL = 2              # no Brasil inteiro, 2 x 2 quadrados-base (0,16 grau): ~4 unidades do viewBox de 1000 cada
SOBREPOR = 0.3                   # o traço de cada linha passa 0,15 unidade para cada lado: com o centro arredondado a 1 casa, linhas
                                 # vizinhas deixavam uma fresta (uma risca escura cruzando o país inteiro, vista em 09/10/2026)
MINIMO_COM_DADO = 0.25           # quadrado com menos de 1/4 dos pixels com dado fica sem cor ("sem dado"), não vira média de 2 pixels
RAIO_KM = 25.0                   # o núcleo da densidade num recorte de região: a 25 km o foco já não pesa
RAIO_KM_BRASIL = 50.0            # no Brasil inteiro, 50 km: com 25 km cada foco virava um pontinho de 2 pixels, e não se via onde
                                 # o fogo se concentra (o raio vai escrito na legenda)
POR_AREA_KM2 = 1000.0            # a densidade sai em focos por 1.000 km²
LIMITES_DENSIDADE = (0.5, 2.0, 5.0, 20.0)   # as divisas das cinco classes, em focos por 1.000 km²

# As cinco classes do INPE, com as faixas da regra de `alertas.classe_risco_fogo` (o teste confere cada divisa).
CLASSES_RISCO = (
    {"id": 1, "classe": "mínimo", "rotulo": "Mínimo", "faixa": "abaixo de 0,15"},
    {"id": 2, "classe": "baixo", "rotulo": "Baixo", "faixa": "de 0,15 a 0,40"},
    {"id": 3, "classe": "médio", "rotulo": "Médio", "faixa": "de 0,40 a 0,70"},
    {"id": 4, "classe": "alto", "rotulo": "Alto", "faixa": "de 0,70 a 0,95"},
    {"id": 5, "classe": "crítico", "rotulo": "Crítico", "faixa": "acima de 0,95"},
)
_ID_DA_CLASSE = {c["classe"]: c["id"] for c in CLASSES_RISCO}
# Um foco sozinho dá até 1,5 focos por 1.000 km² no centro dele (3 / (pi x 25²) x 1.000): as classes partem daí para quem lê ter
# uma régua ("um foco isolado" fica na 2ª classe; uns 10 focos juntos, na 4ª).
CLASSES_DENSIDADE = (
    {"id": 1, "rotulo": "Muito baixa", "faixa": "até 0,5"},
    {"id": 2, "rotulo": "Baixa", "faixa": "de 0,5 a 2"},
    {"id": 3, "rotulo": "Média", "faixa": "de 2 a 5"},
    {"id": 4, "rotulo": "Alta", "faixa": "de 5 a 20"},
    {"id": 5, "rotulo": "Muito alta", "faixa": "20 ou mais"},
)


def numero_svg(v: float) -> str:
    """Número do SVG: uma casa (0,1 unidade = ~0,4 km no Brasil inteiro e menos nas regiões), sem ".0" e sem "-0"."""
    s = f"{v:.1f}"
    if s in ("0.0", "-0.0"):
        return "0"
    return s[:-2] if s.endswith(".0") else s


# ── a grade ──────────────────────────────────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Grade:
    """Quadrados de `dlon` x `dlat` graus a partir do canto noroeste (`oeste`, `norte`); a célula (r, c) é o índice r * ncols + c,
    com a linha 0 no norte."""
    oeste: float
    norte: float
    dlon: float
    dlat: float
    ncols: int
    nrows: int

    def lon(self, c: int) -> float:
        return self.oeste + (c + 0.5) * self.dlon

    def lat(self, r: int) -> float:
        return self.norte - (r + 0.5) * self.dlat

    def celula(self, lat: float, lon: float):
        """(r, c) do quadrado que contém o ponto, ou None fora da grade."""
        c, r = math.floor((lon - self.oeste) / self.dlon), math.floor((self.norte - lat) / self.dlat)
        return (r, c) if 0 <= r < self.nrows and 0 <= c < self.ncols else None


def grade_de_caixa(lon_min, lat_min, lon_max, lat_max, passo) -> Grade:
    """Os quadrados de `passo` graus que cobrem a caixa (a densidade usa; o risco segue o alinhamento do arquivo do INPE)."""
    return Grade(lon_min, lat_max, passo, passo, max(1, math.ceil((lon_max - lon_min) / passo - 1e-9)),
                 max(1, math.ceil((lat_max - lat_min) / passo - 1e-9)))


def grade_dos_blocos(blocos: dict) -> Grade:
    """A grade de `GeoTiff.somar_em_blocos`."""
    return Grade(blocos["oeste"], blocos["norte"], blocos["dlon"], blocos["dlat"], blocos["ncols"], blocos["nrows"])


def juntar(blocos: dict, k: int):
    """(grade, soma, contagem) com k x k blocos-base por quadrado: a soma e a contagem se somam (a média sai depois, ponderada pelos
    pixels com dado de cada bloco, nunca média de médias)."""
    g = grade_dos_blocos(blocos)
    if k <= 1:
        return g, blocos["soma"], blocos["n"]
    ncols, nrows = math.ceil(g.ncols / k), math.ceil(g.nrows / k)
    soma, n = array("d", [0.0]) * (ncols * nrows), array("I", [0]) * (ncols * nrows)
    s0, n0 = blocos["soma"], blocos["n"]
    for r in range(g.nrows):
        destino = (r // k) * ncols
        origem = r * g.ncols
        for c in range(g.ncols):
            if n0[origem + c]:
                soma[destino + c // k] += s0[origem + c]
                n[destino + c // k] += n0[origem + c]
    return Grade(g.oeste, g.norte, g.dlon * k, g.dlat * k, ncols, nrows), soma, n


# ── as classes ───────────────────────────────────────────────────────────────────────────────────────────────────────

def classe_do_risco(media) -> int:
    """1 a 5 (Mínimo a Crítico) pela régua do INPE de `alertas.classe_risco_fogo`; 0 sem valor."""
    return _ID_DA_CLASSE.get(A.classe_risco_fogo(media), 0)


def classes_do_risco(soma, n, px_por_celula: int) -> bytearray:
    """A classe de cada quadrado pela MÉDIA dos pixels com dado; 0 (sem cor) se menos de `MINIMO_COM_DADO` dos pixels têm dado."""
    minimo = max(1, math.ceil(MINIMO_COM_DADO * px_por_celula))
    saida = bytearray(len(n))
    for i, k in enumerate(n):
        if k >= minimo:
            saida[i] = classe_do_risco(soma[i] / k)
    return saida


def classe_da_densidade(v: float) -> int:
    """0 sem foco no raio (densidade zero); 1 a 5 pelas divisas de `LIMITES_DENSIDADE`."""
    if v <= 0:
        return 0
    return 1 + sum(v >= limite for limite in LIMITES_DENSIDADE)


def densidade(focos, grade: Grade, raio_km: float = RAIO_KM) -> array:
    """Focos por 1.000 km² no centro de cada quadrado: a soma do núcleo quártico K(d) = 3/(pi h²) (1 - d²/h²)² dos focos a menos de
    `raio_km` (h). A distância é a do plano local do foco (o grau de longitude encolhe pelo cosseno da latitude): a 25 km, o erro
    contra a haversine fica abaixo de 0,1%. Um foco sozinho dá 3 / (pi h²) x 1.000 no centro dele e zero a partir de h; somada na
    grade, cada foco vale 1 (o núcleo integra 1), então a soma de tudo vezes a área do quadrado é o número de focos."""
    h2 = raio_km * raio_km
    pico = 3.0 / (math.pi * h2) * POR_AREA_KM2
    v = array("d", [0.0]) * (grade.ncols * grade.nrows)
    graus_lat = raio_km / KM_POR_GRAU
    for f in focos:
        cos_lat = max(math.cos(math.radians(f.lat)), 0.05)
        graus_lon = raio_km / (KM_POR_GRAU * cos_lat)
        r0 = max(0, math.ceil((grade.norte - (f.lat + graus_lat)) / grade.dlat - 0.5))
        r1 = min(grade.nrows - 1, math.floor((grade.norte - (f.lat - graus_lat)) / grade.dlat - 0.5))
        c0 = max(0, math.ceil((f.lon - graus_lon - grade.oeste) / grade.dlon - 0.5))
        c1 = min(grade.ncols - 1, math.floor((f.lon + graus_lon - grade.oeste) / grade.dlon - 0.5))
        for r in range(r0, r1 + 1):
            dy = (grade.lat(r) - f.lat) * KM_POR_GRAU
            dy2 = dy * dy
            if dy2 >= h2:
                continue
            base = r * grade.ncols
            for c in range(c0, c1 + 1):
                dx = (grade.lon(c) - f.lon) * KM_POR_GRAU * cos_lat
                d2 = dx * dx + dy2
                if d2 < h2:
                    t = 1.0 - d2 / h2
                    v[base + c] += pico * t * t
    return v


def classes_da_densidade(valores) -> bytearray:
    return bytearray(classe_da_densidade(x) for x in valores)


# ── o Brasil na grade ────────────────────────────────────────────────────────────────────────────────────────────────

def _intervalos_por_linha(grade: Grade, aneis) -> list:
    """Para cada linha da grade, as colunas [(c0, c1)] cujo centro cai dentro do Brasil: varredura por linha (par-ímpar sobre
    todos os anéis dos estados, buracos inclusive), com cada aresta posta só nas linhas que ela cruza. O contorno não muda: quem
    chama guarda o resultado."""
    cruzamentos = [[] for _ in range(grade.nrows)]
    for anel in aneis:
        n = len(anel)
        for i in range(n):
            (x1, y1), (x2, y2) = anel[i], anel[(i + 1) % n]
            if y1 == y2:
                continue
            ymin, ymax = (y1, y2) if y1 < y2 else (y2, y1)
            r_ini = max(0, math.ceil((grade.norte - ymax) / grade.dlat - 0.5) - 1)
            r_fim = min(grade.nrows - 1, math.floor((grade.norte - ymin) / grade.dlat - 0.5) + 1)
            for r in range(r_ini, r_fim + 1):
                y = grade.lat(r)
                if ymin <= y < ymax:
                    cruzamentos[r].append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    saida = []
    for xs in cruzamentos:
        xs.sort()
        linha = []
        for a, b in zip(xs[0::2], xs[1::2]):
            c0 = max(0, math.ceil((a - grade.oeste) / grade.dlon - 0.5))
            c1 = min(grade.ncols - 1, math.floor((b - grade.oeste) / grade.dlon - 0.5))
            if c0 <= c1:
                linha.append((c0, c1))
        saida.append(linha)
    return saida


@lru_cache(maxsize=32)          # as grades do risco (com e sem juntar), as da densidade (uma por recorte) e a das tiles
def mascara(grade: Grade, aneis: tuple, dilatar: int = 1) -> bytearray:
    """1 no quadrado cujo centro está no Brasil e, com `dilatar`, nos vizinhos dele: o quadrado da costa e da fronteira entra no
    desenho e o recorte do SVG (o contorno do IBGE) corta no lugar certo. `aneis`: todos os anéis (lon, lat) dos estados."""
    linhas = _intervalos_por_linha(grade, aneis)
    m = bytearray(grade.ncols * grade.nrows)
    for r in range(grade.nrows):
        juntos = []
        for rr in range(max(0, r - dilatar), min(grade.nrows, r + dilatar + 1)):
            juntos += [(max(0, c0 - dilatar), min(grade.ncols - 1, c1 + dilatar)) for c0, c1 in linhas[rr]]
        base = r * grade.ncols
        for c0, c1 in juntos:
            m[base + c0: base + c1 + 1] = b"\x01" * (c1 - c0 + 1)
    return m


def precisa_de_tile(grade_brasil: Grade, aneis: tuple):
    """A função que diz se uma tile do INPE (caixa oeste, sul, leste, norte) encosta no Brasil, pela máscara numa grade fixa: das
    289 tiles da caixa do Brasil, só as que têm terra brasileira são baixadas."""
    m = mascara(grade_brasil, aneis, 1)
    g = grade_brasil

    def precisa(oeste, sul, leste, norte) -> bool:
        c0, c1 = max(0, math.floor((oeste - g.oeste) / g.dlon)), min(g.ncols - 1, math.floor((leste - g.oeste) / g.dlon))
        r0, r1 = max(0, math.floor((g.norte - norte) / g.dlat)), min(g.nrows - 1, math.floor((g.norte - sul) / g.dlat))
        if c0 > c1 or r0 > r1:
            return False
        return any(1 in m[r * g.ncols + c0: r * g.ncols + c1 + 1] for r in range(r0, r1 + 1))
    return precisa


# ── o desenho ────────────────────────────────────────────────────────────────────────────────────────────────────────

def faixas(classes: bytearray, grade: Grade, vista, *, desenhar=None, contar=None, n_classes: int = 5,
           folga: float = 8.0) -> dict:
    """O desenho de uma camada de calor no recorte `vista`: para cada classe, UM caminho de faixas horizontais (`M x y h w`, as
    seguintes da mesma linha por deslocamento `m dx 0 h w`, medido do ponto JÁ arredondado: a soma nunca deriva), com o traço da
    altura do quadrado (`altura`, em unidades do SVG). `desenhar` (máscara dilatada) diz o que entra no desenho; `contar` (máscara
    sem dilatar) diz o que entra na conta da legenda. Quadrado fora do recorte (mais `folga` unidades) nem é escrito.

    {"altura": "4.18", "caminhos": {classe: d}, "contagem": {classe: quadrados}, "com_dado": n, "sem_dado": n}."""
    xs = [vista.ponto(0.0, grade.oeste + c * grade.dlon)[0] for c in range(grade.ncols + 1)]
    ys = [vista.ponto(grade.norte - r * grade.dlat, 0.0)[1] for r in range(grade.nrows + 1)]
    largura, altura_svg = vista.largura, vista.altura
    cols = [c for c in range(grade.ncols) if xs[c + 1] >= -folga and xs[c] <= largura + folga]
    caminhos = {k: [] for k in range(1, n_classes + 1)}
    fim_anterior = {k: None for k in caminhos}              # (x, y) arredondado onde o último traço da classe parou
    contagem = {k: 0 for k in caminhos}
    sem_dado = 0
    for r in range(grade.nrows):
        if ys[r + 1] < -folga or ys[r] > altura_svg + folga:
            continue
        y = round((ys[r] + ys[r + 1]) / 2, 1)
        base = r * grade.ncols
        corrida = None                                       # [classe, coluna inicial, coluna final]
        corridas = []
        for c in cols:
            i = base + c
            k = classes[i] if desenhar is None or desenhar[i] else 0
            if contar is None or contar[i]:
                if classes[i]:
                    contagem[classes[i]] += 1
                else:
                    sem_dado += 1
            if corrida is not None and k == corrida[0] and c == corrida[2] + 1:
                corrida[2] = c
                continue
            if corrida is not None and corrida[0]:
                corridas.append(corrida)
            corrida = [k, c, c]
        if corrida is not None and corrida[0]:
            corridas.append(corrida)
        for k, c0, c1 in corridas:
            xa, xb = round(xs[c0], 1), round(xs[c1 + 1], 1)
            antes = fim_anterior[k]
            if antes is not None and antes[1] == y:
                caminhos[k].append(f"m{numero_svg(xa - antes[0])} 0h{numero_svg(xb - xa)}")
            else:
                caminhos[k].append(f"M{numero_svg(xa)} {numero_svg(y)}h{numero_svg(xb - xa)}")
            fim_anterior[k] = (xb, y)
    passo_y = (ys[1] - ys[0]) if grade.nrows else 0.0
    return {"altura": f"{passo_y + SOBREPOR:.2f}", "caminhos": {k: "".join(v) for k, v in caminhos.items() if v},
            "contagem": contagem, "com_dado": sum(contagem.values()), "sem_dado": sem_dado}
