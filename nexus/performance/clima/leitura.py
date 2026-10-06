"""Cache de cada fonte do Clima e risco (06/10/2026), no padrão do `publicacao.py` da operação em tempo real.

- TTL por fonte: avisos do INMET 30 min, focos do INPE 10 min, risco de fogo 6 h (o INPE publica uma vez por dia, ~06:30).
- Depois de uma falha, 60 s sem insistir: a fonte caída não leva um pedido por visita à tela.
- Uma busca por vez: quem chega enquanto outra thread busca recebe a última leitura boa como está (ou "lendo a fonte"),
  sem esperar a rede. Uma busca de risco de fogo leva alguns segundos; sem isto, a fila de visitas esgotaria as threads.
- A última leitura boa é servida com o erro e a hora dela (`velha=True`), nunca como fresca: a tela diz "INMET fora agora;
  última leitura boa às HH:MM".
- Nos testes (`TESTING`), sem sessão injetada não vai à rede.

Nada aqui grava em disco nem no banco: a fase 1 é só leitura, e histórico seria fato novo da governança de dados.
"""
import threading
import time
from dataclasses import dataclass
from typing import Any

from . import fontes

TTL_AVISOS_S = 30 * 60
TTL_FOCOS_S = 10 * 60
TTL_RISCO_S = 6 * 3600
FALHA_TTL_S = 60
LENDO = "lendo a fonte"
SEM_FONTE_NOS_TESTES = "sem fonte nos testes"


@dataclass
class Leitura:
    """O que a tela recebe de uma fonte.

    dados     o resultado da fonte (ver `fontes.py`), ou None se nunca houve leitura boa
    lido_em   quando a leitura boa mostrada foi feita (epoch, segundos); None se não há leitura boa
    erro      por que a última tentativa falhou, ou None
    velha     True = a falha é recente e `dados` é a última leitura boa, de `lido_em`
    """
    dados: Any | None
    lido_em: float | None = None
    erro: str | None = None
    velha: bool = False


_relogio_global = [time.time]
_sessao_teste = [None]


def usar_relogio(relogio) -> None:
    """Troca o relógio de todos os caches (os testes avançam o tempo sem dormir). None volta ao `time.time`."""
    _relogio_global[0] = relogio or time.time


def usar_sessao(sessao) -> None:
    """Injeta a sessão (a falsa dos testes). None devolve ao `requests`."""
    _sessao_teste[0] = sessao


class Cache:
    def __init__(self, ttl_s, falha_ttl_s=FALHA_TTL_S, relogio=None):
        self.ttl_s, self.falha_ttl_s = ttl_s, falha_ttl_s
        self._relogio_proprio = relogio
        self._trava = threading.Lock()
        self.limpar()

    def _agora(self) -> float:
        return (self._relogio_proprio or _relogio_global[0])()

    def limpar(self) -> None:
        with self._trava:
            self._bom, self._chave, self._t = None, None, 0.0
            self._erro, self._falha_t, self._buscando = None, 0.0, False

    def ler(self, buscar, chave=None) -> Leitura:
        """`buscar()` devolve os dados ou levanta. `chave` separa leituras que não valem uma para a outra (o risco de fogo
        depende do conjunto de usinas)."""
        agora = self._agora()
        with self._trava:
            bom = self._bom if self._bom is not None and self._chave == chave else None
            if bom is not None and agora - self._t < self.ttl_s:
                return bom
            if self._erro is not None and agora - self._falha_t < self.falha_ttl_s:
                if bom is not None:
                    return Leitura(bom.dados, bom.lido_em, erro=self._erro, velha=True)
                return Leitura(None, None, erro=self._erro)
            if self._buscando:
                return bom if bom is not None else Leitura(None, None, erro=LENDO)
            self._buscando = True
        dados, erro = None, None
        try:
            dados = buscar()
        except Exception as e:                          # noqa: BLE001 — a tela diz o erro; nada vai para o log com dado
            erro = fontes.resumo_do_erro(e)
        with self._trava:
            self._buscando = False
            fim = self._agora()
            if erro is None:
                self._bom, self._chave, self._t, self._erro, self._falha_t = Leitura(dados, fim), chave, fim, None, 0.0
                return self._bom
            if self._chave != chave:
                self._bom, self._chave = None, chave    # a leitura velha era de outro conjunto: não vale para este
            self._erro, self._falha_t = erro, fim
            if self._bom is not None:
                return Leitura(self._bom.dados, self._bom.lido_em, erro=erro, velha=True)
            return Leitura(None, None, erro=erro)


_AVISOS = Cache(TTL_AVISOS_S)
_FOCOS = Cache(TTL_FOCOS_S)
_RISCO = Cache(TTL_RISCO_S)


def limpar_cache() -> None:
    for c in (_AVISOS, _FOCOS, _RISCO):
        c.limpar()


def _ler(cache, config, sessao, fabricar, chave=None) -> Leitura:
    s = sessao or _sessao_teste[0]
    if s is None:
        if (config or {}).get("TESTING"):
            return Leitura(None, None, erro=SEM_FONTE_NOS_TESTES)
        s = fontes.sessao_padrao()
    return cache.ler(lambda: fabricar(s), chave)


def avisos(config, sessao=None) -> Leitura:
    return _ler(_AVISOS, config, sessao, lambda s: fontes.inmet_avisos(s, fontes.enderecos(config)["inmet"]))


def focos(config, sessao=None) -> Leitura:
    return _ler(_FOCOS, config, sessao, lambda s: fontes.inpe_focos(s, fontes.enderecos(config)["focos"]))


def risco(config, pontos, sessao=None) -> Leitura:
    """`pontos`: [(chave, lat, lon)]. A leitura vale para ESTE conjunto de pontos (a ordem não conta): entrou ou saiu uma usina
    do cadastro, lê de novo."""
    pontos = list(pontos)
    chave = frozenset((c, lat, lon) for c, lat, lon in pontos)
    return _ler(_RISCO, config, sessao,
                lambda s: fontes.inpe_risco_fogo(pontos, s, fontes.enderecos(config)["risco"]), chave)
