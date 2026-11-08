"""Mapa de equipe: a cidade do técnico "parado fora de usina", pela malha de municípios do IBGE, sem mandar a posição
(08/11/2026, Levi: "Faça puxar uma API do IBGE").

O mapa nunca mostra o ponto de quem está parado fora de usina (a casa, o hotel): o painel diz "Cidade/UF" e a distância
até a usina mais perto. A cidade sai daqui, com estas regras:
- A posição do técnico NUNCA vai ao IBGE (nada de geocodificação reversa por coordenada): baixa-se a malha do ESTADO
  inteiro, a mesma para qualquer ponto dele, e a lista dos nomes; o ponto no polígono roda no servidor (raio par-ímpar
  com os buracos do GeoJSON, `situacao.no_poligono`). O IBGE só vê a sigla da UF.
- O código do município da malha (`codarea`, em texto) casa com o `id` da lista de nomes (número). Conferido na API de
  verdade em 08/11/2026 com o DF: `codarea` "5300108" na malha, `id` 5300108 na lista. Minas Gerais inteira: 500 KB de
  malha e 380 KB de nomes, meio segundo cada.
- A malha fica no disco, em `pasta_dados/equipe/ibge/<UF>.json` (só código, nome e polígono de cada município), por
  30 dias (o IBGE publica uma malha por ano), e na memória do processo. Vencida, baixa de novo; o IBGE fora com a
  vencida no disco, vale a vencida.
- **O pedido da página NUNCA baixa** (revisão de 08/11/2026: a ida ao IBGE dentro do pedido eram dois GET seguidos de
  até 35 s cada, um por técnico parado, e o IBGE pendurado prendia o mapa por minutos). Sem a malha da UF (ou com ela
  vencida), `cidade` manda a ida ao IBGE para o fundo (`iniciar`: uma thread, uma por UF de cada vez) e responde já
  com o que há: None sem malha nenhuma (o painel mostra só a UF), a vencida quando há. A próxima abertura tem a
  cidade. O GET de verdade espera no máximo TIMEOUT (3 s a conexão, 8 s a resposta).
- O IBGE fora do ar não quebra o mapa: a ida em fundo falha calada (no log, o tipo), e a mesma UF só tenta de novo
  depois de ESPERA_FALHA_S.
- O ponto fora de todo município (o litoral simplificado da malha "mínima" põe a praia no mar) fica com o de borda mais
  perto até `situacao.FOLGA_UF_KM`, a mesma régua do estado; mais longe, None.
- Nos testes (TESTING) o IBGE de verdade nunca é chamado (`_baixador`, decidido no pedido, não na thread, que não tem
  o contexto do app): quem testa injeta o `baixar` e o `iniciar`.
"""
import json
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nexus.campo.equipe import situacao as SI
from nexus.performance.clima import mapa as M

log = logging.getLogger(__name__)

URL_MALHA = ("https://servicodados.ibge.gov.br/api/v3/malhas/estados/{uf}?formato=application/vnd.geo+json"
             "&intrarregiao=municipio&qualidade=minima")
URL_NOMES = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
VALIDADE = timedelta(days=30)
ESPERA_FALHA_S = 600            # o IBGE que falhou: a mesma UF só tenta de novo depois de 10 min
TIMEOUT = (3, 8)                # o GET de verdade: 3 s para conectar, 8 s para responder (e só em fundo)
VERSAO = 1                      # o formato do arquivo do disco; outro número é lido como "não há"
SIGLAS = frozenset(sigla for sigla, _nome, _regiao in M.UFS.values())
_FORMATO = "%Y-%m-%dT%H:%M:%SZ"

_TRAVA = threading.Lock()
_MEMORIA: dict = {}             # (pasta, uf) -> {"baixado_em": datetime, "lista": [(nome, polígonos, caixa)]}
_FALHOU: dict = {}              # (pasta, uf) -> time.monotonic() da última falha
_BAIXANDO: set = set()          # (pasta, uf) com a ida ao IBGE em curso, em fundo


def limpar() -> None:
    """Esquece a memória e as falhas (os testes; um reinício do processo faz o mesmo). O disco fica."""
    with _TRAVA:
        _MEMORIA.clear()
        _FALHOU.clear()
        _BAIXANDO.clear()


def _arquivo(pasta, uf: str) -> Path:
    return Path(pasta) / "equipe" / "ibge" / f"{uf}.json"


def _baixar_do_ibge(url: str):
    """O GET de verdade (só leitura, sem chave), sempre numa thread de fundo."""
    import requests
    r = requests.get(url, timeout=TIMEOUT, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()


def _baixador():
    """Quem vai ao IBGE quando ninguém injeta: o GET de verdade; nos testes (TESTING), ninguém. Decidido aqui, no
    pedido: a thread de fundo não tem o contexto do app para saber se é teste."""
    from flask import current_app, has_app_context
    if has_app_context() and current_app.config.get("TESTING"):
        return None
    return _baixar_do_ibge


def _em_fundo(alvo) -> None:
    """A ida ao IBGE numa thread à parte: o pedido da página segue sem esperar."""
    threading.Thread(target=alvo, name="nexus-equipe-ibge", daemon=True).start()


def _montar(malha, nomes) -> list[dict]:
    """A malha do estado e a lista dos nomes do IBGE -> [{"codigo", "nome", "geometria"}]. O município sem nome na lista
    fica de fora; resposta de outro formato, ou nenhum município casado, levanta ValueError (nada vai ao disco)."""
    try:
        nome_de = {str(n["id"]).strip(): str(n["nome"]).strip() for n in nomes}
        out = []
        for f in malha["features"]:
            codigo, g = str(f["properties"]["codarea"]).strip(), f["geometry"]
            nome = nome_de.get(codigo)
            if nome and g.get("type") in ("Polygon", "MultiPolygon"):
                out.append({"codigo": codigo, "nome": nome,
                            "geometria": {"type": g["type"], "coordinates": g["coordinates"]}})
    except (KeyError, TypeError, AttributeError) as e:
        raise ValueError(f"a resposta do IBGE não tem o formato esperado ({type(e).__name__})") from None
    if not out:
        raise ValueError("a malha e os nomes do IBGE não casaram nenhum município")
    return out


def _carregar(municipios: list[dict]) -> list:
    """[(nome, polígonos, caixa)] para o ponto no polígono; o polígono é uma tupla de anéis de (lon, lat)."""
    out = []
    for m in municipios:
        g = m["geometria"]
        brutos = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        poligonos = tuple(tuple(tuple((float(p[0]), float(p[1])) for p in anel) for anel in pol) for pol in brutos)
        pontos = [p for pol in poligonos for anel in pol for p in anel]
        if not pontos:
            continue
        caixa = (min(p[0] for p in pontos), min(p[1] for p in pontos), max(p[0] for p in pontos),
                 max(p[1] for p in pontos))
        out.append((m["nome"], poligonos, caixa))
    return out


def _ler_disco(arq: Path):
    """(baixado_em, lista) do arquivo, ou None: sem arquivo, de outra versão ou estragado (a queda no meio da gravação)
    é como não ter, e a próxima ida ao IBGE o refaz."""
    try:
        d = json.loads(arq.read_text(encoding="utf-8"))
        if d.get("versao") != VERSAO:
            return None
        baixado = datetime.strptime(d["baixado_em"], _FORMATO).replace(tzinfo=timezone.utc)
        return baixado, _carregar(d["municipios"])
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as e:
        log.warning("equipe: a malha do IBGE no disco (%s) não abriu (%s)", arq.name, type(e).__name__)
        return None


def _gravar_disco(arq: Path, uf: str, baixado_em: datetime, municipios: list[dict]) -> None:
    """Grava inteiro ou nada (o temporário troca o arquivo de uma vez)."""
    arq.parent.mkdir(parents=True, exist_ok=True)
    tmp = arq.with_suffix(".tmp")
    tmp.write_text(json.dumps({"versao": VERSAO, "uf": uf, "baixado_em": baixado_em.strftime(_FORMATO),
                               "fonte": [URL_MALHA.format(uf=uf), URL_NOMES.format(uf=uf)], "municipios": municipios},
                              ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, arq)


def _guardar_do_ibge(chave, uf: str, arq, baixar) -> None:
    """A ida ao IBGE (na thread de fundo): a malha e os nomes, no disco e na memória. A falha fica no log (o tipo) e
    segura a UF por ESPERA_FALHA_S; a malha que havia (vencida) segue valendo."""
    try:
        municipios = _montar(baixar(URL_MALHA.format(uf=uf)), baixar(URL_NOMES.format(uf=uf)))
        agora = datetime.now(timezone.utc)
        novo = {"baixado_em": agora, "lista": _carregar(municipios)}
        if arq is not None:
            try:
                _gravar_disco(arq, uf, agora, municipios)
            except OSError as e:        # sem disco, a memória vale até o processo reiniciar
                log.warning("equipe: não gravei a malha do IBGE de %s no disco (%s)", uf, type(e).__name__)
        with _TRAVA:
            _MEMORIA[chave] = novo
            _FALHOU.pop(chave, None)
    except Exception as e:      # noqa: BLE001 — o IBGE fora, a resposta torta: o mapa segue com o estado
        log.warning("equipe: a malha dos municípios de %s não veio do IBGE (%s)", uf, type(e).__name__)
        with _TRAVA:
            _FALHOU[chave] = time.monotonic()
    finally:
        with _TRAVA:
            _BAIXANDO.discard(chave)


def _malha(uf: str, pasta, baixar, iniciar, agora: datetime):
    """Os municípios da UF que já há, da memória ou do disco, ou None. Nunca vai ao IBGE no pedido: sem a malha, ou com
    ela vencida, manda a ida para o fundo (uma por UF de cada vez, e nenhuma por ESPERA_FALHA_S depois de uma falha)."""
    chave = (str(pasta) if pasta is not None else "", uf)
    arq = _arquivo(pasta, uf) if pasta is not None else None
    with _TRAVA:
        m = _MEMORIA.get(chave)
    if m is None and arq is not None:
        lido = _ler_disco(arq)
        if lido is not None:
            m = {"baixado_em": lido[0], "lista": lido[1]}
            with _TRAVA:
                _MEMORIA[chave] = m
    if m is not None and agora - m["baixado_em"] < VALIDADE:
        return m["lista"]
    if baixar is not None:
        with _TRAVA:
            falhou = _FALHOU.get(chave)
            vai = chave not in _BAIXANDO and (falhou is None or time.monotonic() - falhou >= ESPERA_FALHA_S)
            if vai:
                _BAIXANDO.add(chave)
        if vai:
            try:
                iniciar(lambda: _guardar_do_ibge(chave, uf, arq, baixar))
            except Exception as e:      # noqa: BLE001 — a thread que não sobe: a próxima abertura tenta de novo
                log.warning("equipe: a ida ao IBGE de %s não subiu (%s)", uf, type(e).__name__)
                with _TRAVA:
                    _BAIXANDO.discard(chave)
    return m["lista"] if m is not None else None


def cidade(lat: float, lon: float, uf: str, *, pasta: Path | None, baixar=None, iniciar=None) -> str | None:
    """O nome do município onde o ponto cai, na malha do IBGE da `uf`, ou None (fora de todos, a UF que não é UF, a
    malha ainda não baixada). Responde na hora: sem a malha, manda a ida ao IBGE para o fundo e devolve None (a próxima
    pergunta tem a cidade). `pasta` = a pasta de dados do Nexus (None: só a memória); `baixar(url) -> JSON` é o GET ao
    IBGE e `iniciar(alvo)` põe a ida numa thread (o teste injeta os dele). Só a sigla da UF entra no endereço pedido; a
    coordenada fica aqui."""
    uf = str(uf or "").strip().upper()
    if uf not in SIGLAS:
        return None
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return None
    lista = _malha(uf, pasta, baixar or _baixador(), iniciar or _em_fundo, datetime.now(timezone.utc))
    if not lista:
        return None
    for nome, poligonos, caixa in lista:
        if SI.perto_da_caixa(lon, lat, caixa, 0) and any(SI.no_poligono(lon, lat, p) for p in poligonos):
            return nome
    melhor, menor = None, SI.FOLGA_UF_KM
    for nome, poligonos, caixa in lista:
        if not SI.perto_da_caixa(lon, lat, caixa, SI.FOLGA_UF_KM):
            continue
        km = min(SI.km_da_borda(lon, lat, p) for p in poligonos)
        if km <= menor:
            melhor, menor = nome, km
    return melhor
