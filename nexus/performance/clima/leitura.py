"""Cache de cada fonte do Clima e risco (06/10/2026), no padrão do `publicacao.py` da operação em tempo real.

- TTL por fonte: avisos do INMET 30 min, focos do INPE 10 min, risco de fogo 6 h (o INPE publica uma vez por dia, ~06:30).
  O TTL do risco conta da leitura, e a leitura de antes da publicação é do arquivo de ontem: lido às 05:00, ficaria com ele até
  as 11:01. Por isso, enquanto o T0 não é comprovadamente o de hoje (pela data do arquivo), o TTL é de 15 min.
- A irradiação da NASA POWER (07/10/2026) é a única fonte com um cache POR USINA: 12 h cada, só quando alguém abre a página da
  usina (a tela principal nunca a chama). A NASA publica com uns 5 dias de atraso e a série não muda de hora em hora; 12 h
  deixa a página da usina leve sem esconder um dia novo por mais de meio dia. Uma busca por vez em cada usina: quem chega no
  meio recebe "lendo" (ou a última boa), e as outras usinas buscam à parte, sem esperar.
- Depois de uma falha, 60 s sem insistir: a fonte caída não leva um pedido por visita à tela.
- Uma busca por vez: quem chega enquanto outra thread busca recebe a última leitura boa como está (ou "lendo a fonte"),
  sem esperar a rede. Uma busca de risco de fogo leva alguns segundos; sem isto, a fila de visitas esgotaria as threads.
- A última leitura boa é servida com o erro e a hora dela (`velha=True`), nunca como fresca: a tela diz "INMET fora agora;
  última leitura boa às HH:MM".
- Nos testes (`TESTING`), sem sessão injetada não vai à rede.
- O mapa de calor do risco de fogo (09/10/2026, Mapa de risco) lê a ÁREA do Brasil no arquivo do INPE (~8 MB e alguns segundos
  de LZW por dia de previsão): um cache por dia, lido AO FUNDO (`ao_fundo=True`: a tela recebe "lendo" ou a leitura anterior na
  hora, e quem lê é uma thread), e só quando alguém liga a camada. Ao vencer, relê só o cabeçalho e, se o arquivo é o mesmo
  (Last-Modified), não baixa tile nenhuma.
- Cada leitura diz quando vence (`vence_em`): o Mapa de risco e o modo TV marcam a próxima atualização por ela, nunca antes.
- O fogo das últimas 24 h da NASA (FIRMS, 10/10/2026): 30 min. Os arquivos mudam a cada passagem de satélite (umas 4 vezes por dia
  cada um), e a releitura manda o ETag da leitura anterior: o que não mudou volta 304, sem download e sem reler o CSV.

Nada aqui grava em disco nem no banco: a fase 1 é só leitura, e histórico seria fato novo da governança de dados.
"""
import logging
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from . import fontes

log = logging.getLogger(__name__)
BRT = timezone(timedelta(hours=-3))

TTL_AVISOS_S = 30 * 60
TTL_FOCOS_S = 10 * 60
TTL_RISCO_S = 6 * 3600
TTL_RISCO_DESATUALIZADO_S = 15 * 60     # enquanto o arquivo T0 do INPE não é comprovadamente o de hoje
TTL_POWER_S = 12 * 3600                 # NASA POWER, por usina
TTL_FIRMS_S = 30 * 60                   # NASA FIRMS (o dado só muda depois de uma passagem de satélite)
JANELA_POWER_DIAS = 40                  # os 40 dias que terminam hoje: cobrem os 30 do gráfico e o mês inteiro, e dão folga de um dia
                                        # para o cache de até 12 h cuja janela já mudou
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
    vence_em  quando o cache desta fonte busca de novo (epoch): o fim do TTL da leitura boa, ou o fim da janela de 60 s depois de
              uma falha; None enquanto lê pela primeira vez (ou leitura montada à mão). É o ritmo do modo TV (09/10/2026)
    """
    dados: Any | None
    lido_em: float | None = None
    erro: str | None = None
    velha: bool = False
    vence_em: float | None = None


_relogio_global = [time.time]
_sessao_teste = [None]
# Quem roda a leitura ao fundo: uma thread por leitura (no máximo uma por cache, pela trava). Os testes trocam por um que roda na
# hora (`usar_executor(lambda f: f())`), para não depender de tempo.
_executor = [lambda tarefa: threading.Thread(target=tarefa, name="clima-ao-fundo", daemon=True).start()]


def usar_relogio(relogio) -> None:
    """Troca o relógio de todos os caches (os testes avançam o tempo sem dormir). None volta ao `time.time`."""
    _relogio_global[0] = relogio or time.time


def usar_sessao(sessao) -> None:
    """Injeta a sessão (a falsa dos testes). None devolve ao `requests`."""
    _sessao_teste[0] = sessao


def usar_executor(executor) -> None:
    """Troca quem roda a leitura ao fundo (os testes rodam na hora). None volta à thread."""
    _executor[0] = executor or (lambda tarefa: threading.Thread(target=tarefa, name="clima-ao-fundo", daemon=True).start())


def agora() -> float:
    """O relógio dos caches (epoch): o mesmo que decide o TTL; nos testes, o de mentira."""
    return _relogio_global[0]()


def _ttl_do_risco(dados, t) -> float:
    """O TTL de uma leitura do risco de fogo, lida em `t` (epoch): 6 h se o T0 é de hoje (em Brasília); senão 15 min. Sem a
    data do T0 (dia 0 sem leitura, ou servidor sem Last-Modified) não dá para confirmar, e na dúvida o TTL é o curto."""
    arquivo = ((dados or {}).get("arquivos") or {}).get(0)
    if arquivo is None:
        return TTL_RISCO_DESATUALIZADO_S
    hoje = datetime.fromtimestamp(t, BRT).date()
    return TTL_RISCO_S if arquivo.astimezone(BRT).date() == hoje else TTL_RISCO_DESATUALIZADO_S


class Cache:
    def __init__(self, ttl_s, falha_ttl_s=FALHA_TTL_S, relogio=None, nome="fonte", validade=None):
        """`validade(dados, t)`, se houver, diz por quantos segundos vale CADA leitura (no lugar do `ttl_s`)."""
        self.ttl_s, self.falha_ttl_s, self.nome, self.validade = ttl_s, falha_ttl_s, nome, validade
        self._relogio_proprio = relogio
        self._trava = threading.Lock()
        self.limpar()

    def _agora(self) -> float:
        return (self._relogio_proprio or _relogio_global[0])()

    def limpar(self) -> None:
        with self._trava:
            self._bom, self._chave, self._t, self._ttl_efetivo = None, None, 0.0, self.ttl_s
            self._erro, self._falha_t, self._buscando = None, 0.0, False

    def ultima_boa(self):
        """Os dados da última leitura boa (de qualquer idade), ou None: a releitura do mapa de calor compara o arquivo com ela."""
        with self._trava:
            return self._bom.dados if self._bom is not None else None

    def _pronta(self, agora, chave):
        """A resposta que não precisa de busca (dentro do TTL, dentro da janela de falha, ou outra thread já buscando), ou None
        se é hora de buscar. Chame com a trava."""
        bom = self._bom if self._bom is not None and self._chave == chave else None
        if bom is not None and agora - self._t < self._ttl_efetivo:
            return bom
        if self._erro is not None and agora - self._falha_t < self.falha_ttl_s:
            vence = self._falha_t + self.falha_ttl_s
            if bom is not None:
                return Leitura(bom.dados, bom.lido_em, erro=self._erro, velha=True, vence_em=vence)
            return Leitura(None, None, erro=self._erro, vence_em=vence)
        if self._buscando:
            return bom if bom is not None else Leitura(None, None, erro=LENDO)
        return None

    def ler(self, buscar, chave=None, ao_fundo=False) -> Leitura:
        """`buscar()` devolve os dados ou levanta. `chave` separa leituras que não valem uma para a outra (o risco de fogo
        depende do conjunto de usinas). `ao_fundo`: a busca roda numa thread e quem pediu recebe na hora o que há (a leitura
        anterior, mesmo vencida, ou "lendo"); é o mapa de calor, que leva segundos e não pode segurar a página."""
        with self._trava:
            pronta = self._pronta(self._agora(), chave)
            if pronta is not None:
                return pronta
            bom = self._bom if self._bom is not None and self._chave == chave else None
            self._buscando = True
        if not ao_fundo:
            return self._buscar(buscar, chave)
        _executor[0](lambda: self._buscar(buscar, chave))
        with self._trava:
            # o executor dos testes roda na hora: aí a resposta já está pronta; com a thread, é a anterior ou "lendo"
            pronta = self._pronta(self._agora(), chave)
            return pronta if pronta is not None else (bom if bom is not None else Leitura(None, None, erro=LENDO))

    def _buscar(self, buscar, chave) -> Leitura:
        dados, erro = None, None
        try:
            dados = buscar()
        except Exception as e:                          # noqa: BLE001 — a tela diz o erro, e o log guarda uma linha dele
            erro = fontes.resumo_do_erro(e)
        except BaseException:
            # Ctrl+C, SystemExit e afins atravessam, mas antes soltam a trava: sem isto, a fonte ficava em "lendo a fonte" para
            # sempre (toda visita via a trava presa, e nenhuma refazia a busca).
            with self._trava:
                self._buscando = False
            raise
        with self._trava:
            self._buscando = False
            fim = self._agora()
            if erro is None:
                self._ttl_efetivo = self.validade(dados, fim) if self.validade else self.ttl_s
                self._bom = Leitura(dados, fim, vence_em=fim + self._ttl_efetivo)
                self._chave, self._t, self._erro, self._falha_t = chave, fim, None, 0.0
                return self._bom
            if self._chave != chave:
                self._bom, self._chave = None, chave    # a leitura velha era de outro conjunto: não vale para este
            self._erro, self._falha_t = erro, fim
            vence = fim + self.falha_ttl_s
            resposta = (Leitura(self._bom.dados, self._bom.lido_em, erro=erro, velha=True, vence_em=vence)
                        if self._bom is not None else Leitura(None, None, erro=erro, vence_em=vence))
        # Uma linha por FALHA (a janela de 60 s não busca de novo, então não repete): o resumo curto, sem a mensagem crua da
        # rede, e nunca dado de usina.
        log.warning("clima: %s fora: %s", self.nome, erro)
        return resposta


def _ttl_da_grade(dados, t) -> float:
    """O TTL do mapa de calor do risco de um dia: 6 h se o arquivo é de hoje (em Brasília), senão 15 min, como o risco por
    usina. Ao vencer, a releitura confere o Last-Modified antes de baixar tile (`fontes.inpe_risco_grade`, `anterior`)."""
    modificado = (dados or {}).get("modificado")
    if modificado is None:
        return TTL_RISCO_DESATUALIZADO_S
    hoje = datetime.fromtimestamp(t, BRT).date()
    return TTL_RISCO_S if modificado.astimezone(BRT).date() == hoje else TTL_RISCO_DESATUALIZADO_S


_AVISOS = Cache(TTL_AVISOS_S, nome="INMET (avisos)")
_FOCOS = Cache(TTL_FOCOS_S, nome="INPE (focos)")
_RISCO = Cache(TTL_RISCO_S, nome="INPE (risco de fogo)", validade=_ttl_do_risco)
# o mapa de calor do risco de fogo, um cache por dia de previsão (0 a 3): cada dia é um arquivo do INPE, lido só se alguém o escolhe
_GRADES = {d: Cache(TTL_RISCO_S, nome=f"INPE (mapa de calor do risco de fogo, dia {d})", validade=_ttl_da_grade)
           for d in fontes.DIAS_DE_RISCO}
_FIRMS = Cache(TTL_FIRMS_S, nome="NASA FIRMS (fogo das últimas 24 h)")
_POWER: dict = {}                       # um Cache por usina; o id vem do cadastro (quem chama confere que a usina existe)
_POWER_TRAVA = threading.Lock()


def limpar_cache() -> None:
    for c in (_AVISOS, _FOCOS, _RISCO, _FIRMS, *_GRADES.values()):
        c.limpar()
    with _POWER_TRAVA:
        _POWER.clear()


def _cache_da_usina(usina_id) -> Cache:
    # O nome do cache vai ao log quando a fonte falha: nunca leva o id nem a coordenada da usina.
    with _POWER_TRAVA:
        c = _POWER.get(str(usina_id))
        if c is None:
            c = _POWER[str(usina_id)] = Cache(TTL_POWER_S, nome="NASA POWER (irradiação)")
        return c


def _ler(cache, config, sessao, fabricar, chave=None, ao_fundo=False) -> Leitura:
    s = sessao or _sessao_teste[0]
    if s is None:
        if (config or {}).get("TESTING"):
            return Leitura(None, None, erro=SEM_FONTE_NOS_TESTES)
        s = fontes.sessao_padrao()
    return cache.ler(lambda: fabricar(s), chave, ao_fundo=ao_fundo)


def avisos(config, sessao=None) -> Leitura:
    return _ler(_AVISOS, config, sessao, lambda s: fontes.inmet_avisos(s, fontes.enderecos(config)["inmet"]))


def focos(config, sessao=None) -> Leitura:
    return _ler(_FOCOS, config, sessao, lambda s: fontes.inpe_focos(s, fontes.enderecos(config)["focos"]))


def firms(config, sessao=None) -> Leitura:
    """O fogo das últimas 24 h dos satélites da NASA (ver `fontes.nasa_firms`): a releitura leva o ETag da leitura boa anterior."""
    anterior = _FIRMS.ultima_boa()
    return _ler(_FIRMS, config, sessao, lambda s: fontes.nasa_firms(s, fontes.enderecos(config)["firms"], anterior=anterior))


def risco(config, pontos, sessao=None) -> Leitura:
    """`pontos`: [(chave, lat, lon)]. A leitura vale para ESTE conjunto de pontos (a ordem não conta): entrou ou saiu uma usina
    do cadastro, lê de novo."""
    pontos = list(pontos)
    chave = frozenset((c, lat, lon) for c, lat, lon in pontos)
    return _ler(_RISCO, config, sessao,
                lambda s: fontes.inpe_risco_fogo(pontos, s, fontes.enderecos(config)["risco"]), chave)


def irradiacao(config, usina_id, lat, lon, hoje: date, sessao=None) -> Leitura:
    """O GHI diário da NASA POWER numa usina, dos 40 dias que terminam em `hoje` (data de Brasília): ver `fontes.nasa_power`.
    O cache é o da usina: outra usina busca à parte, e a falha de uma não derruba a outra."""
    inicio = hoje - timedelta(days=JANELA_POWER_DIAS - 1)
    return _ler(_cache_da_usina(usina_id), config, sessao,
                lambda s: fontes.nasa_power(lat, lon, inicio, hoje, s, fontes.enderecos(config)["power"]))


def risco_grade(config, dia: int, caixa, precisa=None, sessao=None) -> Leitura:
    """O mapa de calor do risco de fogo do dia `dia` (0 a 3, o T0..T3 do INPE) na `caixa` (o Brasil), lido AO FUNDO: a primeira
    visita recebe "lendo" e a tela se atualiza quando a leitura termina. `precisa(oeste, sul, leste, norte)` escolhe as tiles
    (só as que encostam no Brasil). Ver `fontes.inpe_risco_grade`."""
    cache = _GRADES[dia]
    url = fontes.enderecos(config)["risco"].format(d=dia)
    anterior = cache.ultima_boa()
    return _ler(cache, config, sessao,
                lambda s: fontes.inpe_risco_grade(s, url, caixa, precisa=precisa, anterior=anterior), chave=url, ao_fundo=True)
