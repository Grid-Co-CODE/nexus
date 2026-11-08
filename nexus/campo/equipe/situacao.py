"""Mapa de equipe: a situação de cada técnico a partir do último ponto dele, e o desenho do mapa (08/11/2026).

As decisões do Levi (08/11/2026, no plano `docs/superpowers/plans/2026-11-08-mapa-de-equipe.md`):
- "na usina" = parado a até RAIO_USINA_KM (1 km) da coordenada de uma usina do cadastro;
- "sem sinal" = o último ponto tem SEM_SINAL_MIN (30 min) ou mais;
- as cores: em deslocamento = info, na usina = ok, parado fora de usina = neutro, sem sinal = alerta, sem permissão de
  localização = crítico; "sem posição hoje" só na lista do painel, fora do mapa;
- "parado fora de usina" (a casa, o hotel) NUNCA vai ao mapa e não tem o Abrir rota: o painel diz a cidade e o estado
  (a malha do IBGE, `municipios.py`) e a distância até a usina mais perto. O ponto que ficou velho não muda de
  natureza: o "sem sinal"
  e o "sem permissão" cujo último ponto era parado fora de usina também ficam fora do mapa (senão a casa apareceria
  meia hora depois, no âmbar);
- o Abrir rota sai do último ponto conhecido em deslocamento, na usina e no "sem sinal" de um desses; nunca no "sem
  permissão" (quem negou a localização não tem a posição mandada ao Google) nem sem posição.

"Hoje" é o dia de Brasília: a coleta para às 22h e volta na 1ª abertura do App, e o ponto de ontem não diz onde o
técnico está agora (é "sem posição hoje"; a hora dele ainda aparece). Ponto com mais de 7 dias nunca é usado, nem a
hora dele, mesmo que chegue aqui (o serviço já o corta; aqui vale de novo, a regra é da LGPD).

Nada daqui devolve coordenada: a situação leva a usina mais perto e a distância; o desenho, só o x/y do SVG. A latitude
e a longitude ficam na memória do processo e só saem no clique do Abrir rota, para o Google (`url_da_rota`).
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

CHAVES = ("deslocamento", "na_usina", "fora_usina", "sem_sinal", "sem_permissao", "sem_posicao")
TOM = {"deslocamento": "info", "na_usina": "ok", "fora_usina": "neutro", "sem_sinal": "alerta",
       "sem_permissao": "critico", "sem_posicao": "neutro"}
ROTULO = {"deslocamento": "Em deslocamento", "na_usina": "Na usina", "fora_usina": "Parado fora de usina",
          "sem_sinal": "Sem sinal", "sem_permissao": "Sem permissão de localização", "sem_posicao": "Sem posição hoje"}
# o que pede ação é desenhado por último, por cima dos outros
ORDEM_TOM = {"neutro": 0, "info": 1, "ok": 2, "alerta": 3, "critico": 4}
_DE_MAPA = ("deslocamento", "na_usina")          # o ponto que pode ir ao mapa e dar rota


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
    usina_perto: (usina_id, km) | None, uf, cidade, base, no_mapa, rota, ultima, desde}, sem coordenada nenhuma:
    - `base`: o que o último ponto de hoje era (deslocamento, na_usina ou fora_usina), também quando ele envelheceu;
    - `no_mapa`: o ponto pode ser desenhado; `rota`: o Abrir rota vale;
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
    no_mapa = base in _DE_MAPA
    rota = no_mapa and chave in ("deslocamento", "na_usina", "sem_sinal")
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
            "usina_perto": perto, "uf": uf, "cidade": nome_cidade, "base": base, "no_mapa": no_mapa, "rota": rota,
            "ultima": inst, "desde": estado.get("desde")}


# ── o texto ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def km_texto(km: float, inteiro: bool = False) -> str:
    """"0,8 km" (uma casa, com vírgula) até 10 km; daí em diante o km inteiro ("23 km"). `inteiro` = sempre o km
    inteiro (o parado fora de usina)."""
    r = round(float(km), 1)
    return f"{r:.1f}".replace(".", ",") + " km" if r < 10 and not inteiro else f"{round(km)} km"


def texto_perto(km: float, nome: str, inteiro: bool = False) -> str:
    """A distância até a usina, como o desenho pede: "a 2,3 km da UFV X". Para o parado fora de usina, `inteiro`: o km
    inteiro ("a 5 km"), porque a casa decimal da distância a duas usinas já cercaria a casa ou o hotel que o mapa não
    mostra (revisão final de 08/11/2026)."""
    return f"a {km_texto(km, inteiro)} da {nome}"


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
def desenho(usinas: dict, pontos: list) -> dict:
    """O mapa no padrão da Visão geral (`mapa_responsaveis.desenho`): o contorno dos estados do IBGE, as usinas como
    marca discreta e cada técnico como um ponto já projetado. `usinas` = {usina_id: (lat, lon, uf)}; `pontos` =
    [(pessoa_id, lat, lon, tom)] só de quem VAI ao mapa (o parado fora de usina nem chega aqui). O recorte cobre os
    estados com usina e todo ponto desenhado. Devolve {"viewbox", "ufs": [{"d", "sigla", "x", "y"}], "usinas":
    [{"usina_id", "x", "y"}], "pontos": [{"pessoa_id", "x", "y", "tom"}]}, só com o x/y do SVG; sem nada a desenhar,
    `viewbox` None."""
    vazio = {"viewbox": None, "ufs": [], "usinas": [], "pontos": []}
    if not usinas and not pontos:
        return vazio
    ufs = {c[2] for c in usinas.values() if len(c) > 2 and c[2]}
    caixas = [e.caixa for e in M.estados() if e.sigla in ufs]
    caixas += [(c[1], c[0], c[1], c[0]) for c in usinas.values()]
    caixas += [(lon, lat, lon, lat) for _pid, lat, lon, _tom in pontos]
    lon0, lat0 = min(x[0] for x in caixas), min(x[1] for x in caixas)
    lon1, lat1 = max(x[2] for x in caixas), max(x[3] for x in caixas)
    if lon1 - lon0 < MIN_GRAUS:
        meio = (lon0 + lon1) / 2
        lon0, lon1 = meio - MIN_GRAUS / 2, meio + MIN_GRAUS / 2
    if lat1 - lat0 < MIN_GRAUS:
        meio = (lat0 + lat1) / 2
        lat0, lat1 = meio - MIN_GRAUS / 2, meio + MIN_GRAUS / 2
    v = M.vista_de_caixa("equipe", "Mapa de equipe", lon0, lat0, lon1, lat1, margem=0.06)

    def xy(lat, lon):
        x, y = v.ponto(lat, lon)
        return M._n(round(x, 1)), M._n(round(y, 1))

    marcas = []
    for uid, (lat, lon, *_resto) in usinas.items():
        x, y = xy(lat, lon)
        marcas.append({"usina_id": uid, "x": x, "y": y})
    tecnicos = []
    for pid, lat, lon, tom in sorted(pontos, key=lambda p: ORDEM_TOM.get(p[3], 0)):
        x, y = xy(lat, lon)
        tecnicos.append({"pessoa_id": pid, "x": x, "y": y, "tom": tom})
    return {"viewbox": v.viewbox, "usinas": marcas, "pontos": tecnicos,
            "ufs": [{"d": f.d, "sigla": f.sigla, "x": f.x, "y": f.y} for f in M.ufs_da_vista(v)]}
