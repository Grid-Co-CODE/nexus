"""As regras de alerta por usina (06/10/2026), no mesmo corte do `gridco_meteo/alertas.py` e do `config.ALERTA` do pacote
de referência: aviso do INMET cujo polígono contém a usina, foco de queimada a até 5 km, classe do risco de fogo do INPE.
Os três níveis da usina (Agir agora, Atenção, Sem alerta) são de 07/10/2026.

Funções puras: recebem coordenada e dado já lido, devolvem o que a tela mostra. Quem cruza com o cadastro e ordena por
gravidade é o `visao.py`.
"""
import math
from collections import defaultdict
from datetime import datetime, timezone

from ...cadastro.servico import chave_texto
from . import geometria

FOCO_KM = 5.0              # foco de queimada a até 5 km da usina é alerta
RISCO_ALTO = 0.7           # escala de 0 a 1 do INPE: alto >= 0,7 ...
RISCO_CRITICO = 0.95       # ... e crítico > 0,95 (o 0,95 ainda é alto)

# ── os três níveis da usina (07/10/2026, Levi) ───────────────────────────────────────────────────────────────────────
# O caso que os criou: em 06/10, no meio da seca, 145 das 154 usinas apareciam "com alerta" (aviso de baixa umidade e risco de
# fogo alto cobrindo quase o Nordeste e o Centro-Oeste inteiros) e só 3 pediam alguma ação. Quando quase tudo é alerta, a lista
# não deixa ver o que importa. Por isso a tela separa quem precisa de ação AGORA de quem só merece o olho:
#   Agir agora  foco de queimada a até 5 km (é um evento, não uma previsão); OU aviso do INMET "Grande Perigo" de qualquer
#               evento; OU aviso "Perigo" de um evento que estraga usina (EVENTOS_QUE_ESTRAGAM_USINA)
#   Atenção     qualquer outro aviso do INMET, em vigor ou futuro (Perigo Potencial; Perigo de evento fora da lista, que
#               nunca some, só não manda agir); OU risco de fogo alto ou crítico em algum dos quatro dias (hoje a D+3)
#   Sem alerta  nada disso, e só quando as três fontes foram lidas (a regra do "não dá para dizer" mora no visao.py)
AGIR, ATENCAO, SEM_ALERTA = "agir", "atencao", "sem"
ROTULO_NIVEL = {AGIR: "Agir agora", ATENCAO: "Atenção", SEM_ALERTA: "Sem alerta"}
NIVEL_PERIGO, NIVEL_GRANDE_PERIGO = 2, 3        # os níveis do INMET: Perigo Potencial (1, amarelo), Perigo (2, laranja), Grande Perigo (3, vermelho)
# Os eventos que estragam usina quando o INMET os põe em "Perigo". Comparados sem acento, sem caixa e sem espaço sobrando
# (`chave_texto`), e por igualdade com o nome inteiro: evento que não está aqui, mesmo em Perigo, vai para Atenção em vez de
# mandar agir (um nome novo do INMET nunca acende "Agir agora" sozinho, nem some da tela).
EVENTOS_QUE_ESTRAGAM_USINA = frozenset({"tempestade", "chuvas intensas", "acumulado de chuva", "vendaval",
                                        "ventos costeiros", "granizo"})

_KM_POR_GRAU_MINIMO = 110.0   # um grau de latitude vale de 110,6 a 111,7 km: o menor, para a busca nunca ficar curta
_SEM_INICIO = datetime.min.replace(tzinfo=timezone.utc)


# ── risco de fogo ────────────────────────────────────────────────────────────────────────────────────────────────────

def classe_risco_fogo(v) -> str:
    """As faixas do INPE: mínimo < 0,15 <= baixo < 0,4 <= médio < 0,7 <= alto <= 0,95 < crítico. O valor vem de um double
    gravado em passos de 0,01, e o 0,70 pode chegar como 0,6999999999999: arredonda (9 casas, bem acima do ruído de 1e-16 e
    bem abaixo de qualquer passo real) antes de comparar com a divisa."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "sem dado"
    v = round(v, 9)
    return ("mínimo" if v < 0.15 else "baixo" if v < 0.4 else "médio" if v < RISCO_ALTO
            else "alto" if v <= RISCO_CRITICO else "crítico")


def nivel_do_risco(classe: str) -> int:
    """Gravidade para a ordem da tela: 0 não é alerta, 2 alto, 3 crítico."""
    return {"alto": 2, "crítico": 3}.get(classe, 0)


# ── aviso do INMET ───────────────────────────────────────────────────────────────────────────────────────────────────

def em_vigor(aviso, agora) -> bool:
    """O aviso já começou? (O INMET manda em `futuro` o que ainda vai começar.)"""
    return aviso.inicio is None or aviso.inicio <= agora


def avisos_que_contem(lat, lon, avisos, agora) -> list:
    """Os avisos não vencidos cujo polígono contém o ponto, do mais grave para o menos (e, no empate, o que começa antes).
    A caixa do polígono descarta a maioria sem percorrer um vértice. Um aviso que ainda vai começar entra: a tela diz
    quando começa."""
    achados = []
    for a in avisos:
        if a.fim is not None and a.fim < agora:
            continue
        x0, y0, x1, y1 = a.caixa
        if x0 <= lon <= x1 and y0 <= lat <= y1 and geometria.contem(a.geometria, lon, lat):
            achados.append(a)
    achados.sort(key=lambda a: (-a.nivel, a.inicio or _SEM_INICIO))
    return achados


def evento_estraga_usina(evento) -> bool:
    return chave_texto(evento) in EVENTOS_QUE_ESTRAGAM_USINA


def aviso_manda_agir(aviso) -> bool:
    """Grande Perigo, de qualquer evento, ou Perigo de um evento que estraga usina. Perigo Potencial nunca manda agir."""
    if aviso.nivel == NIVEL_GRANDE_PERIGO:
        return True
    return aviso.nivel == NIVEL_PERIGO and evento_estraga_usina(aviso.evento)


def nivel_da_usina(avisos, tem_foco: bool, risco_alto: bool) -> str:
    """"agir", "atencao" ou "sem", pelos alertas que a usina TEM (os avisos já são os que a contêm, em vigor ou futuros). Se uma
    fonte não foi lida, "sem" não quer dizer "sem alerta": quem monta a tela é quem sabe disso (`visao.montar`)."""
    if tem_foco or any(aviso_manda_agir(a) for a in avisos):
        return AGIR
    if avisos or risco_alto:
        return ATENCAO
    return SEM_ALERTA


# ── focos de queimada ────────────────────────────────────────────────────────────────────────────────────────────────

class IndiceFocos:
    """Os focos numa grade de células de `celula` graus (~11 km): cada usina olha só as células em volta. Na hora do pico
    da estação seca são milhares de focos por hora no continente, e a conta de cada usina contra todos eles seria
    centenas de milhares de haversines por visita à tela."""

    def __init__(self, focos, celula=0.1):
        self.celula = celula
        self._celulas = defaultdict(list)
        for f in focos:
            self._celulas[(math.floor(f.lat / celula), math.floor(f.lon / celula))].append(f)

    def no_raio(self, lat, lon, raio_km=FOCO_KM):
        """Os focos a até `raio_km` da coordenada, cada um com a distância: [(km, Foco)], sem ordem; [] se não há. É o que o mapa
        usa para pôr o anel no foco (e não na usina) e o `perto` resume."""
        graus_lat = raio_km / _KM_POR_GRAU_MINIMO
        graus_lon = raio_km / (_KM_POR_GRAU_MINIMO * max(math.cos(math.radians(lat)), 0.05))
        dl, dc = math.ceil(graus_lat / self.celula), math.ceil(graus_lon / self.celula)
        c0, c1 = math.floor(lat / self.celula), math.floor(lon / self.celula)
        achados = []
        for i in range(c0 - dl, c0 + dl + 1):
            for j in range(c1 - dc, c1 + dc + 1):
                for f in self._celulas.get((i, j), ()):
                    d = geometria.distancia_km(lat, lon, f.lat, f.lon)
                    if d <= raio_km:
                        achados.append((d, f))
        return achados

    def perto(self, lat, lon, raio_km=FOCO_KM):
        """None se não há foco no raio. Senão: quantos (`n`), a distância do mais perto (`km`) com o satélite e a hora (UTC)
        dele, e a detecção mais recente entre todos os do raio (`ultima`)."""
        achados = self.no_raio(lat, lon, raio_km)
        if not achados:
            return None
        d, f = min(achados, key=lambda par: par[0])           # no empate fica o primeiro achado, como antes
        return {"n": len(achados), "km": d, "satelite": f.satelite, "hora": f.data,
                "ultima": max(g.data for _, g in achados)}
