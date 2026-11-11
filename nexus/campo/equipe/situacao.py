"""Mapa de equipe: a situação de cada técnico a partir do último ponto dele, e o desenho do mapa (08/11/2026).

As decisões do Levi (08/11/2026, no plano `docs/superpowers/plans/2026-11-08-mapa-de-equipe.md`):
- "na usina" = parado a até RAIO_USINA_KM (1 km) da coordenada de uma usina do cadastro;
- "sem sinal" = o último ponto tem SEM_SINAL_MIN (30 min) ou mais;
- as cores: em deslocamento = info, na usina = ok, parado fora de usina = neutro, sem sinal = alerta, sem permissão de
  localização = crítico; "sem posição hoje" só na lista do painel, fora do mapa;
- o painel diz, do parado fora de usina, a cidade e o estado (a malha do IBGE, `municipios.py`) e a distância até a
  usina mais perto. O ponto que ficou velho não muda de natureza (a `base`);
- o Abrir rota sai do último ponto de HOJE em qualquer situação, menos no "sem permissão" (quem negou a localização não
  tem a posição mandada ao Google); o ponto de outro dia não dá rota (não é de onde o técnico sai hoje).

**10/11/2026 (Levi, pela sessão Nexus Field):** "Isso precisa ser visual, se tem dados de localização tem que estar
mostrando no nexus" e "mostra só o ponto de localização e caso a pessoa queira, consegue ver o percurso que aquela pessoa
fez em determinado período de dias e horas!". O trajeto de teste de 09/11 chegou inteiro ao banco e o mapa
não mostrou nada: só ia ao mapa o ponto de hoje em deslocamento ou na usina. A decisão de 08/11 ("parado fora de usina, a
casa, o hotel, NUNCA vai ao mapa") foi trocada por ele: a última posição de cada técnico (até 7 dias) vai ao mapa no lugar
exato, em toda situação; a de outro dia vai marcada `velho`. O percurso de um período sai em `desenho_percurso`.

"Hoje" é o dia de Brasília: a coleta para às 22h e volta na 1ª abertura do App, e o ponto de ontem não diz onde o
técnico está agora (é "sem posição hoje"; a hora dele ainda aparece). Ponto com mais de 7 dias nunca é usado, nem a
hora dele, mesmo que chegue aqui (o serviço já o corta; aqui vale de novo, a regra é da LGPD).

Nada daqui devolve coordenada: a situação leva a usina mais perto e a distância; o desenho e o percurso, só o x/y do SVG.
A latitude e a longitude ficam na memória do processo e só saem no clique do Abrir rota, para o Google (`url_da_rota`).
"""
import math
from datetime import datetime, timedelta, timezone

from nexus.campo.equipe import GUARDA_PONTOS_DIAS, RAIO_USINA_KM, SEM_SINAL_MIN
from nexus.campo.equipe.deslocamentos import haversine_km
from nexus.performance.clima import mapa as M

_BRT = timezone(timedelta(hours=-3))
KM_POR_GRAU = 6371.0088 * math.pi / 180          # o mesmo raio da Terra do `haversine_km`
# O contorno "mínimo" do IBGE (o do Mapa de risco) simplifica o litoral: medido em 08/11/2026, Boa Viagem cai a
# 0,4 km do desenho de Pernambuco, Pajuçara a 0,1 km do de Alagoas e Copacabana a 3,9 km do do Rio, todos no "mar". O
# ponto fora de todo estado fica com o estado de borda mais perto até esta folga; mais longe (o oceano, outro país),
# sem estado.
FOLGA_UF_KM = 20.0
MIN_GRAUS = 3.0                         # o recorte de uma usina só não vira um zoom de rua (o mesmo da Visão geral)
# O percurso (10/11/2026) abre no MAPA INTEIRO, o mesmo recorte do mapa dos técnicos, e a pessoa aproxima (Levi: "pode
# mostrar o mapa inteiro primeiro, e aí a pessoa pode ir dando zoom e mostrando as cidades e municípios de forma leve e
# fluída"). O zoom é do navegador (troca o viewBox, como o Mapa de risco da Performance); o servidor diz, de cada ponto,
# hora e município, o NÍVEL em que aparece. Um nível é uma largura da vista em km: 0 = qualquer vista (o mapa inteiro);
# o nível i vale quando a vista tem até NIVEIS_KM[i-1] km de largura.
NIVEIS_KM = (1200.0, 500.0, 150.0, 40.0, 8.0)
NIVEL_CIDADES = 2                # o contorno dos municípios e o nome dos do percurso: a vista de até 500 km (na bancada de
                                 # 10/11/2026, com 250 km, o percurso de 261 km enquadrado ainda não mostrava cidade nenhuma)
NOME_FRACAO = 0.09               # dois nomes de município do percurso ficam a pelo menos 9% da largura da vista
VISTA_MIN_MAPA_KM = 8.0          # a menor vista do mapa dos técnicos e das usinas (11/11/2026, quando ele ganhou o zoom):
#                                  sem os municípios no fundo, mais perto que isso só sobra o ponto
VISTA_MIN_KM = 1.5               # a menor vista (o zoom máximo): um bairro; mais perto, o contorno do IBGE só pixela
ROTULO_FRACAO = 0.04             # duas horas escritas ficam a pelo menos 4% da largura da vista uma da outra
PONTO_FRACAO = 0.012             # e dois pontos, a 1,2%
ROTULO_AFASTA_EM = 1.1           # a hora fica a 1,1 "em" do ponto, na perpendicular do trecho (o texto não cresce com o zoom)

CHAVES = ("deslocamento", "na_usina", "fora_usina", "sem_sinal", "sem_permissao", "sem_posicao")
TOM = {"deslocamento": "info", "na_usina": "ok", "fora_usina": "neutro", "sem_sinal": "alerta",
       "sem_permissao": "critico", "sem_posicao": "neutro"}
ROTULO = {"deslocamento": "Em deslocamento", "na_usina": "Na usina", "fora_usina": "Parado fora de usina",
          "sem_sinal": "Sem sinal", "sem_permissao": "Sem permissão no celular", "sem_posicao": "Sem posição hoje"}
# o que pede ação é desenhado por último, por cima dos outros
ORDEM_TOM = {"neutro": 0, "info": 1, "ok": 2, "alerta": 3, "critico": 4}


def _instante(texto) -> datetime | None:
    try:
        return datetime.strptime(str(texto), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def usina_mais_perto(lat: float, lon: float, usinas: dict):
    """(usina_id, km) da usina mais perto do ponto, ou None sem usina. `usinas` = {usina_id: (lat, lon, uf)}."""
    melhor = None
    for uid, (ulat, ulon, *_resto) in usinas.items():
        km = haversine_km(lat, lon, ulat, ulon)
        if melhor is None or km < melhor[1]:
            melhor = (uid, km)
    return melhor


# ── o ponto no polígono (o estado aqui; o município na Task 7b) ──────────────────────────────────────────────────────
def _arestas(anel):
    return zip(anel, anel[1:] + anel[:1])


def no_poligono(lon: float, lat: float, poligono) -> bool:
    """O ponto cai dentro do polígono do GeoJSON (anéis de (lon, lat): o de fora e os buracos)? Raio par-ímpar sobre
    TODOS os anéis: o ponto num buraco cruza a borda de fora e a do buraco, e fica fora (o enclave é de outro
    município)."""
    dentro = False
    for anel in poligono:
        for (x1, y1), (x2, y2) in _arestas(tuple(anel)):
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                dentro = not dentro
    return dentro


def km_da_borda(lon: float, lat: float, poligono) -> float:
    """A distância do ponto à borda mais perto do polígono, em km (plano local: a longitude encolhe pelo cosseno)."""
    c = math.cos(math.radians(lat))
    px, menor = lon * c, math.inf
    for anel in poligono:
        for (x1, y1), (x2, y2) in _arestas(tuple(anel)):
            ax, bx = x1 * c, x2 * c
            dx, dy = bx - ax, y2 - y1
            t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (lat - y1) * dy) / (dx * dx + dy * dy)))
            menor = min(menor, math.hypot(px - (ax + t * dx), lat - (y1 + t * dy)))
    return menor * KM_POR_GRAU


def perto_da_caixa(lon, lat, caixa, km) -> bool:
    """O ponto cai na caixa (lon mín., lat mín., lon máx., lat máx.) com `km` de folga em volta? O corte barato antes
    do ponto no polígono."""
    folga = km / KM_POR_GRAU
    folga_lon = folga / max(math.cos(math.radians(lat)), 0.1)
    return caixa[0] - folga_lon <= lon <= caixa[2] + folga_lon and caixa[1] - folga <= lat <= caixa[3] + folga


def uf_do_ponto(lat: float, lon: float) -> str | None:
    """A sigla do estado onde o ponto cai, pelo contorno do IBGE que o Nexus já guarda (nada sai do servidor). O
    desenho de Goiás contorna o do Distrito Federal: o ponto de Brasília é só do DF. Fora de todos: o de borda mais
    perto até FOLGA_UF_KM (o litoral simplificado)."""
    try:
        estados = M.estados()
    except ValueError:                  # o arquivo do contorno que não abre: sem estado, o resto da situação vale
        return None
    for e in estados:
        if perto_da_caixa(lon, lat, e.caixa, 0) and any(no_poligono(lon, lat, p) for p in e.poligonos):
            return e.sigla
    melhor, menor = None, FOLGA_UF_KM
    for e in estados:
        if not perto_da_caixa(lon, lat, e.caixa, FOLGA_UF_KM):
            continue
        km = min(km_da_borda(lon, lat, p) for p in e.poligonos)
        if km <= menor:
            melhor, menor = e.sigla, km
    return melhor


# ── a situação ───────────────────────────────────────────────────────────────────────────────────────────────────────
def situacao(estado: dict, usinas: dict, agora_utc: datetime, *, cidade=None) -> dict:
    """A situação do técnico pelo `estado` do serviço (`Servico.estado_de`: o último ponto, a permissão e desde quando).
    `usinas` = {usina_id: (lat, lon, uf)} (`mapa_responsaveis.coordenadas`). Devolve {chave, rotulo, tom, idade_min,
    usina_perto: (usina_id, km) | None, uf, cidade, base, no_mapa, velho, rota, ultima, desde}, sem coordenada nenhuma:
    - `base`: o que o último ponto de hoje era (deslocamento, na_usina ou fora_usina), também quando ele envelheceu;
    - `no_mapa`: há um último ponto dos 7 dias para desenhar (10/11/2026: toda situação); `velho`: ele é de outro dia;
    - `rota`: o Abrir rota vale (o ponto de hoje, sem o "sem permissão");
    - `uf` e `cidade`: o estado e o município do ponto parado fora de usina (só nele: os outros estão no mapa). A cidade
      vem de `cidade(lat, lon, uf) -> nome | None` (`municipios.cidade`, a malha do IBGE no servidor); sem ela, ou com
      ela falhando, None, e o painel mostra só o estado;
    - `ultima`: o instante do último ponto (até 7 dias), para a hora de Brasília no painel."""
    u = estado.get("ultimo")
    inst = _instante(u.get("instante")) if u else None
    if inst is not None and inst < agora_utc - timedelta(days=GUARDA_PONTOS_DIAS):
        u, inst = None, None                    # ponto com mais de 7 dias: nem a hora dele
    de_hoje = inst is not None and inst.astimezone(_BRT).date() == agora_utc.astimezone(_BRT).date()
    idade = max(0.0, (agora_utc - inst).total_seconds() / 60) if de_hoje else None
    base = perto = None
    if de_hoje:
        perto = usina_mais_perto(u["lat"], u["lon"], usinas)
        if u.get("mov"):
            base = "deslocamento"
        elif perto is not None and perto[1] <= RAIO_USINA_KM:
            base = "na_usina"
        else:
            base = "fora_usina"
    if estado.get("permissao") == "sem":
        chave = "sem_permissao"
    elif not de_hoje:
        chave = "sem_posicao"
    elif idade >= SEM_SINAL_MIN:
        chave = "sem_sinal"
    else:
        chave = base
    no_mapa = inst is not None
    rota = de_hoje and chave != "sem_permissao"
    rotulo = ROTULO[chave]
    if chave == "sem_sinal":
        rotulo += " há " + tempo_texto(int(idade))
    uf = nome_cidade = None
    if base == "fora_usina":
        uf = uf_do_ponto(u["lat"], u["lon"])
        if uf and cidade is not None:
            try:
                nome_cidade = cidade(u["lat"], u["lon"], uf)
            except Exception:       # noqa: BLE001 — a cidade é enfeite do painel: sem ela, o estado basta
                nome_cidade = None
    return {"chave": chave, "rotulo": rotulo, "tom": TOM[chave], "idade_min": int(idade) if idade is not None else None,
            "usina_perto": perto, "uf": uf, "cidade": nome_cidade, "base": base, "no_mapa": no_mapa,
            "velho": no_mapa and not de_hoje, "rota": rota, "ultima": inst, "desde": estado.get("desde")}


# ── o texto ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def km_texto(km: float) -> str:
    """"0,8 km" (uma casa, com vírgula) até 10 km; daí em diante o km inteiro ("23 km")."""
    r = round(float(km), 1)
    return f"{r:.1f}".replace(".", ",") + " km" if r < 10 else f"{round(km)} km"


def texto_perto(km: float, nome: str) -> str:
    """A distância até a usina, como o desenho pede: "a 2,3 km da UFV X". O km inteiro do parado fora de usina (que
    escondia a casa do mapa, revisão final de 08/11/2026) saiu em 10/11/2026: o ponto dele está no mapa."""
    return f"a {km_texto(km)} da {nome}"


def tempo_texto(minutos: int) -> str:
    """31 -> "31 min"; 125 -> "2 h 05"."""
    m = max(0, int(minutos))
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d}"


# ── o Abrir rota ─────────────────────────────────────────────────────────────────────────────────────────────────────
def _grau(v) -> str:
    # 5 casas (~1 m) bastam para a rota de carro; a 6ª é o centímetro, que o Google não usa e só entrega a posição mais
    # fina do que é preciso (revisão final de 08/11/2026)
    x = float(v)
    if not math.isfinite(x):
        raise ValueError("coordenada que não é número")
    return format(x, ".5f").rstrip("0").rstrip(".")


def url_da_rota(origem: tuple, destino: tuple) -> str:
    """O link do Google Maps do técnico (`origem`) até a usina (`destino`), de carro. Montado no servidor e mandado só
    no redirecionamento de quem clicou: a página nunca o tem (a coordenada iria junto). O Waze ficou de fora (desenho,
    seção 9): o link dele só leva o destino e traça a rota a partir de quem clica, e no escritório sairia do
    escritório."""
    return (f"https://www.google.com/maps/dir/?api=1&origin={_grau(origem[0])},{_grau(origem[1])}"
            f"&destination={_grau(destino[0])},{_grau(destino[1])}&travelmode=driving")


# ── o desenho ────────────────────────────────────────────────────────────────────────────────────────────────────────
def vista_do_mapa(usinas: dict, pontos: list):
    """O recorte do mapa (o dos técnicos, o das usinas e o do percurso): os estados com usina e todo ponto (lat, lon)
    desenhado. É pública desde 11/11/2026: a tela pede o clima (`clima.mapa.montar`) nesta mesma vista, e a mesma
    entrada dá a mesma vista. Sem usina e sem ponto, ValueError (não há o que enquadrar)."""
    if not usinas and not pontos:
        raise ValueError("sem usina e sem ponto: não há o que enquadrar")
    ufs = {c[2] for c in usinas.values() if len(c) > 2 and c[2]}
    caixas = [e.caixa for e in M.estados() if e.sigla in ufs]
    caixas += [(c[1], c[0], c[1], c[0]) for c in usinas.values()]
    caixas += [(lon, lat, lon, lat) for lat, lon in pontos]
    lon0, lat0 = min(x[0] for x in caixas), min(x[1] for x in caixas)
    lon1, lat1 = max(x[2] for x in caixas), max(x[3] for x in caixas)
    if lon1 - lon0 < MIN_GRAUS:
        meio = (lon0 + lon1) / 2
        lon0, lon1 = meio - MIN_GRAUS / 2, meio + MIN_GRAUS / 2
    if lat1 - lat0 < MIN_GRAUS:
        meio = (lat0 + lat1) / 2
        lat0, lat1 = meio - MIN_GRAUS / 2, meio + MIN_GRAUS / 2
    return M.vista_de_caixa("equipe", "Mapa de equipe", lon0, lat0, lon1, lat1, margem=0.06)


def desenho(usinas: dict, pontos: list) -> dict:
    """O mapa no padrão da Visão geral (`mapa_responsaveis.desenho`): o contorno dos estados do IBGE, as usinas como
    marca discreta e cada técnico como um ponto já projetado. `usinas` = {usina_id: (lat, lon, uf)}; `pontos` =
    [(pessoa_id, lat, lon, tom, velho)] de quem vai ao mapa (`situacao.no_mapa`; `velho` = o ponto é de outro dia). O
    recorte cobre os estados com usina e todo ponto desenhado. Devolve {"viewbox", "ufs": [{"d", "sigla", "x", "y"}],
    "usinas": [{"usina_id", "x", "y"}], "pontos": [{"pessoa_id", "x", "y", "tom", "velho"}], "km", "min"}, só com o
    x/y do SVG; sem nada a desenhar, `viewbox` None. O ponto de outro dia vai embaixo, e o que pede ação por cima. `km`
    (km por unidade do desenho) e `min` (a menor largura da vista) são do zoom do navegador (11/11/2026)."""
    vazio = {"viewbox": None, "ufs": [], "usinas": [], "pontos": [], "km": 0.0, "min": 0.0}
    if not usinas and not pontos:
        return vazio
    v = vista_do_mapa(usinas, [(p[1], p[2]) for p in pontos])

    def xy(lat, lon):
        x, y = v.ponto(lat, lon)
        return M._n(round(x, 1)), M._n(round(y, 1))

    marcas = []
    for uid, (lat, lon, *_resto) in usinas.items():
        x, y = xy(lat, lon)
        marcas.append({"usina_id": uid, "x": x, "y": y})
    tecnicos = []
    for pid, lat, lon, tom, velho in sorted(pontos, key=lambda p: (not p[4], ORDEM_TOM.get(p[3], 0))):
        x, y = xy(lat, lon)
        tecnicos.append({"pessoa_id": pid, "x": x, "y": y, "tom": tom, "velho": bool(velho)})
    km_un = KM_POR_GRAU / v.escala
    return {"viewbox": v.viewbox, "usinas": marcas, "pontos": tecnicos, "km": round(km_un, 6),
            "min": VISTA_MIN_MAPA_KM / km_un,
            "ufs": [{"d": f.d, "sigla": f.sigla, "x": f.x, "y": f.y} for f in M.ufs_da_vista(v)]}


# ── o percurso (10/11/2026) ──────────────────────────────────────────────────────────────────────────────────────────
def distancia_km(trilha: list) -> float:
    """A soma das distâncias em linha reta entre os pontos seguidos do percurso (o caminho de carro é mais longo)."""
    return sum(haversine_km(a["lat"], a["lon"], b["lat"], b["lon"]) for a, b in zip(trilha, trilha[1:]))


def _fino(v: float, casas: int = 3) -> str:
    """Número do SVG do percurso: no mapa inteiro uma unidade vale ~4 km, e o `numero_svg` (uma casa, ~400 m) serrilharia a
    linha de um percurso de cidade quando a vista aproxima. Três casas (~4 m) nos pontos, duas (~40 m) nos municípios."""
    t = f"{v:.{casas}f}".rstrip("0").rstrip(".")
    return "0" if t in ("", "-0") else t


def _caminho_fino(aneis, v) -> str:
    partes = []
    for anel in aneis:
        pts = []
        for lon, lat in anel:
            x, y = v.ponto(lat, lon)
            p = (round(x, 2), round(y, 2))
            if not pts or p != pts[-1]:
                pts.append(p)
        if len(pts) >= 3:
            partes.append("M" + " ".join(f"{_fino(x, 2)},{_fino(y, 2)}" for x, y in pts) + "Z")
    return "".join(partes)


def _niveis(pts: list, km_un: float, fracao: float) -> list:
    """O nível de zoom em que cada ponto do percurso aparece: o 1º e o último no 0 (sempre); os outros, no primeiro nível
    em que ficam a pelo menos `fracao` da largura da vista dos vizinhos já mostrados (o anterior e o seguinte na ordem do
    percurso); o que nunca se separa (parado no mesmo lugar) fica None."""
    import bisect
    n = len(pts)
    nivel = [None] * n
    for i in {0, n - 1}:
        nivel[i] = 0
    mostrados = sorted({0, n - 1})
    for L, largura in enumerate(NIVEIS_KM, start=1):
        minimo = fracao * largura / km_un                    # em unidades do desenho
        for i in range(n):
            if nivel[i] is not None:
                continue
            j = bisect.bisect(mostrados, i)
            vizinhos = [mostrados[k] for k in (j - 1, j) if 0 <= k < len(mostrados)]
            if all(math.hypot(pts[i][0] - pts[k][0], pts[i][1] - pts[k][1]) >= minimo for k in vizinhos):
                nivel[i] = L
                mostrados.insert(j, i)
    return nivel


def desenho_percurso(usinas: dict, trilha: list, municipios=()) -> dict:
    """O percurso de um técnico num período (Levi, 10/11/2026: "consegue ver o percurso que aquela pessoa fez em
    determinado período de dias e horas"), desenhado no servidor NO MAPA INTEIRO (o recorte do mapa dos técnicos): a
    pessoa aproxima pelo navegador ("pode mostrar o mapa inteiro primeiro, e aí a pessoa pode ir dando zoom e mostrando
    as cidades e municípios de forma leve e fluída"). `trilha` = os pontos do período em ordem (`Servico.percurso`, com
    lat/lon só na memória); `municipios` = [(nome, polígonos, caixa)] da malha do IBGE já no disco
    (`municipios.na_caixa`).

    Devolve {"viewbox", "ufs", "usinas", "linha" (a polilinha na ordem), "marcas": [{"n", "x", "y", "hora", "mov", "np",
    "nr", "ox", "oy", "ancora"}], "municipios": [{"d", "nome", "x", "y", "n", "rota"}], "cidades", "foco", "km", "min",
    "niveis"}:
    - `hora` é a de Brasília ("16:52", ou "09/11 16:52" quando o percurso passa de um dia);
    - `np` e `nr`: o nível de zoom em que o ponto e a hora escrita aparecem (`_niveis`; 0 = sempre; o ponto que nunca se
      separa aparece só no último nível, e a hora dele não é escrita: fica na lista do painel e no título do ponto);
    - `ox`, `oy`, `ancora`: onde a hora fica em relação ao ponto, em "em" do texto (que não cresce com o zoom), num lado
      do trecho; o nome do município do percurso vai ao lado oposto;
    - `municipios`: o contorno aparece no nível `nb` (NIVEL_CIDADES) e o nome no `n` (os do percurso a partir do
      NIVEL_CIDADES, sem se amontoar; os vizinhos um nível depois);
    - `cidades`: os municípios do percurso na ordem da 1ª passagem; `foco`: a caixa do percurso ("x0 y0 x1 y1"); `km`: km
      por unidade do desenho; `min`: a menor largura da vista; `niveis`: as larguras em km de cada nível.
    Sem ponto, `viewbox` None. Nenhuma coordenada sai daqui: só o x/y do desenho."""
    vazio = {"viewbox": None, "ufs": [], "municipios": [], "cidades": [], "usinas": [], "linha": "", "marcas": [],
             "foco": "", "km": 0.0, "min": 0.0, "niveis": ""}
    if not trilha:
        return vazio
    v = vista_do_mapa(usinas, [(p["lat"], p["lon"]) for p in trilha])
    km_un = KM_POR_GRAU / v.escala
    pts = [v.ponto(p["lat"], p["lon"]) for p in trilha]
    pts = [(round(x, 3), round(y, 3)) for x, y in pts]

    def normal(i0, i1):
        """A perpendicular (unitária) do trecho de pts[i0] a pts[i1], o lado da hora; parado, para cima."""
        dx, dy = pts[i1][0] - pts[i0][0], pts[i1][1] - pts[i0][1]
        tam = math.hypot(dx, dy)
        return (0.0, -1.0) if tam == 0 else (dy / tam, -dx / tam)

    def ancora(nx):
        return "start" if nx > 0.3 else "end" if nx < -0.3 else "middle"

    marcas_u = []
    for uid, (lat, lon, *_resto) in usinas.items():
        x, y = v.ponto(lat, lon)
        marcas_u.append({"usina_id": uid, "x": _fino(x), "y": _fino(y)})
    fundo, primeira = [], {}
    for nome, poligonos, caixa in municipios:
        if not v.cruza(caixa):
            continue
        d = _caminho_fino([anel for pol in poligonos for anel in pol], v)
        if not d:
            continue
        dentro = [i for i, p in enumerate(trilha) if perto_da_caixa(p["lon"], p["lat"], caixa, 0)
                  and any(no_poligono(p["lon"], p["lat"], pol) for pol in poligonos)]
        if dentro:
            primeira.setdefault(nome, dentro[0])
            # o nome no meio dos pontos dele, do lado oposto ao da hora (a perpendicular do trecho que passa por ele)
            x = sum(pts[i][0] for i in dentro) / len(dentro)
            y = sum(pts[i][1] for i in dentro) / len(dentro)
            nx, ny = normal(dentro[0], dentro[-1]) if dentro[0] != dentro[-1] else normal(
                max(dentro[0] - 1, 0), min(dentro[0] + 1, len(pts) - 1))
            ox, oy, anc = -ROTULO_AFASTA_EM * nx, -ROTULO_AFASTA_EM * ny, ancora(-nx)
        else:
            x, y = v.ponto((caixa[1] + caixa[3]) / 2, (caixa[0] + caixa[2]) / 2)      # o meio da caixa do município
            ox, oy, anc = 0.0, 0.0, "middle"
        fundo.append({"d": d, "nome": nome, "x": _fino(x), "y": _fino(y), "ox": round(ox, 2), "oy": round(oy + 0.35, 2),
                      "ancora": anc, "rota": bool(dentro), "nb": NIVEL_CIDADES, "n": NIVEL_CIDADES + 1,
                      "_xy": (x, y)})
    # o nome dos municípios do percurso aparece com o contorno, sem se amontoar: na ordem da passagem, cada um no nível em
    # que fica longe o bastante dos vizinhos já escritos; os que nunca cabem, e os vizinhos do percurso, um nível depois
    da_rota = sorted((m for m in fundo if m["rota"]), key=lambda m: primeira[m["nome"]])
    if da_rota:
        for m, nv in zip(da_rota, _niveis([m["_xy"] for m in da_rota], km_un, NOME_FRACAO)):
            m["n"] = max(NIVEL_CIDADES, nv) if nv is not None else len(NIVEIS_KM)
    for m in fundo:
        del m["_xy"]
    instantes = [_instante(p["instante"]) for p in trilha]
    dias = {i.astimezone(_BRT).date() for i in instantes if i is not None}
    formato = "%d/%m %H:%M" if len(dias) > 1 else "%H:%M"
    np_, nr_ = _niveis(pts, km_un, PONTO_FRACAO), _niveis(pts, km_un, ROTULO_FRACAO)
    marcas = []
    for n, (p, inst) in enumerate(zip(trilha, instantes), start=1):
        nx, ny = normal(max(n - 2, 0), min(n, len(pts) - 1))
        marcas.append({"n": n, "x": _fino(pts[n - 1][0]), "y": _fino(pts[n - 1][1]),
                       "hora": inst.astimezone(_BRT).strftime(formato) if inst else "", "mov": bool(p.get("mov")),
                       "np": len(NIVEIS_KM) if np_[n - 1] is None else np_[n - 1], "nr": nr_[n - 1],
                       "ox": round(ROTULO_AFASTA_EM * nx, 2), "oy": round(ROTULO_AFASTA_EM * ny + 0.35, 2),
                       "ancora": ancora(nx)})
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    return {"viewbox": v.viewbox, "municipios": fundo, "cidades": sorted(primeira, key=primeira.get), "usinas": marcas_u,
            "linha": " ".join(f"{m['x']},{m['y']}" for m in marcas), "marcas": marcas,
            "foco": " ".join(_fino(c) for c in (min(xs), min(ys), max(xs), max(ys))),
            "km": round(km_un, 6), "min": VISTA_MIN_KM / km_un, "niveis": ",".join(str(int(n)) for n in NIVEIS_KM),
            "ufs": [{"d": f.d, "sigla": f.sigla, "x": f.x, "y": f.y} for f in M.ufs_da_vista(v)]}
