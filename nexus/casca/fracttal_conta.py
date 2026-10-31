"""O contador de pedidos ao Fracttal (31/10/2026, etapa 0 do canto central do OS Creator).

A cota do Fracttal é de 200 pedidos por minuto para a empresa toda, dividida entre o OS Creator, o App de Campo e os robôs
do Nexus, e até aqui ninguém sabia quanto o Nexus gasta dela, a que hora nem quem pede: o Raio-X mostra o momento e o
journal só o erro. Sem esse número, o "antes e depois" de cada etapa e o limitador da etapa 5 seriam chute. Daqui saem as
linhas por hora que o laço de gravação leva ao banco (`drenar`) e que o Raio-X mostra (`instantaneo`).

O gancho é UM só, no `requests.sessions.Session.send`: todo pedido do processo ao Fracttal passa por ele, seja o RPC do OS
Creator (`/rpc/proxy`), o REST do `campo/fracttal.py` (`/api/<recurso>`) ou o token OAuth, e quem pede não muda uma linha.
Conta só o host `fracttal.com` (e os `*.fracttal.com`): o S3 pré-assinado e o resto da internet passam sem contar. O
limitador da etapa 5 vai no mesmo lugar, por isso o embrulho mora aqui e em mais nenhum.

- **Uma linha por hora × origem × método.** A origem é quem pediu: a rota do pedido do Nexus (`origem(...)`, marcada pela
  casca) ou, sem marca, `fundo:<nome da thread sem o contador de instância>` (`ThreadPoolExecutor-137_0` vira
  `ThreadPoolExecutor`, `waitress-12` vira `waitress`). O método é o `method` do corpo do RPC, o 1º segmento depois de
  `/api/` no REST (`work_orders`), `token` no OAuth e `outro` no que sobrar; corpo que não é JSON conta como `rpc`.
- **No máximo MAX_ORIGENS_DE_FUNDO (50) origens de fundo (`fundo:...`) distintas por hora:** a 51ª e as seguintes da hora
  entram em `fundo:outros`, e as 50 que já existem seguem contando nas suas. Sem o teto, o nome que ganha número novo a
  cada vez (o de thread) faria a tabela da hora, e o banco, crescerem sem fim. **A rota não tem teto:** quem a marca passa
  a rota normalizada, e ela é limitada pelo conjunto de rotas do app; também não gasta vaga do fundo.
- **A marca viaja pelo contexto (`contextvars`), não pela thread**, como o JWT do OS Creator: o `api._ExecutorComContexto`
  copia o contexto do pedido para as tarefas do fan-out (o catálogo de ativos pede ~110 vezes, 6 de uma vez), e esses
  pedidos são da rota que os chamou e somam na conta dela (`pedidos_desta_thread`). Com `threading.local` eles cairiam
  em `fundo:ThreadPoolExecutor`, e justo as rotas mais pesadas ficariam com a conta vazia. A marca só chega às tarefas de
  um executor que COPIA o contexto: no `ThreadPoolExecutor` comum e na thread aberta à mão a tarefa começa sem contexto
  (a marca de quem a abriu NÃO chega lá), e a origem tem de ser posta dentro da tarefa, senão ela é `fundo:<nome>`.
- **Recusa e erro à parte.** 406 e 429 são o Fracttal pedindo calma (`recusas_qtd`); exceção ou 5xx é `erros_qtd`.
- **O pico por minuto** (`pico_minuto_qtd`) é o maior número de pedidos num mesmo minuto, da linha e, na linha `*` de
  cada hora, de tudo junto: é o número que se compara com a cota. Só o minuto corrente é guardado (o pico da hora já
  guardou o resto), então a memória não cresce com o tempo.
- **A hora é a de Brasília** (UTC-3 fixo, sem horário de verão desde 2019): `hora_id` = `AAAAMMDDHH`. A virada do dia cai
  às 03:00 UTC, e é aí que um erro de fuso apareceria.
- **O contador nunca derruba o pedido:** qualquer falha dele vai ao log em debug, e a resposta (ou a exceção) do pedido
  volta como veio.

`ligar()` é chamado só pelo servidor (`servir.py`, junto do `teto_os`), nunca pelo `create_app`: o PC e os testes seguem
sem o gancho.
"""
import contextvars
import functools
import json
import logging
import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import requests

log = logging.getLogger(__name__)

DOMINIO = "fracttal.com"
RECUSAS = (406, 429)                    # o Fracttal pedindo calma (a cota por minuto)
FUNDO = "fundo:"                        # o começo da origem de quem pede por conta própria (laço, thread), não por rota
MAX_ORIGENS_DE_FUNDO = 50               # origens de fundo distintas por hora; a 51ª e as seguintes vão para OUTROS
OUTROS = FUNDO + "outros"
_BRT = timezone(timedelta(hours=-3))
# o contador de instância no fim do nome da thread (ou antes do " (alvo)" que o Python põe): `-137_0`, `-12`, `3`
_CONTADOR = re.compile(r"(?:[-_ ]?\d+)+(?=$| \()")
_EMBRULHO = "_nexus_fracttal_conta"     # no `send` embrulhado: ligar de novo não embrulha o embrulho
_PEDIDOS, _RECUSADOS, _ERROS, _PICO = range(4)      # as posições da lista de cada linha

_trava = threading.Lock()               # a única: o gancho roda em todas as threads e a conta é de dicionário pequeno
_horas: dict = {}                       # hora_id -> _Hora
_minuto = {"id": None, "total": 0, "chaves": {}}    # o minuto corrente e o que já se pediu nele (o resto virou pico)


class _Marca:
    """Quem está pedindo: o nome da origem e quantos pedidos ao Fracttal ela já fez (a conta do pedido em curso)."""
    __slots__ = ("nome", "pedidos")

    def __init__(self, nome: str):
        self.nome, self.pedidos = nome, 0


# O objeto é COMPARTILHADO entre os contextos copiados (a cópia leva a referência): as tarefas do fan-out somam na
# mesma conta. Sem marca no contexto, o 1º pedido cria a do fundo, com o nome da thread.
_marca_atual: contextvars.ContextVar = contextvars.ContextVar("nexus_fracttal_marca", default=None)


class _Hora:
    """Uma hora de Brasília: uma linha [pedidos, recusas, erros, pico] por (origem, método), as origens de fundo que ela
    já tem (no máximo MAX_ORIGENS_DE_FUNDO; a rota não entra aqui) e o pico do total."""
    __slots__ = ("linhas", "fundos", "pico")

    def __init__(self):
        self.linhas: dict = {}
        self.fundos: set = set()
        self.pico = 0


def _nome_de_fundo(nome: str) -> str:
    """O nome da thread sem o contador de instância: `ThreadPoolExecutor-137_0` vira `ThreadPoolExecutor`, `waitress-12`
    vira `waitress` e `Thread-5 (alvo)` vira `Thread (alvo)`. O `campo/regras_app._fx_wo_paralelo` abre um executor NOVO
    a cada chamada; com o nome cru, cada rodada criaria origens novas na tabela da hora, sem fim."""
    return _CONTADOR.sub("", nome) or nome


def _origem_de_fundo() -> str:
    return FUNDO + _nome_de_fundo(threading.current_thread().name)


def _agora() -> float:
    """O relógio (os testes o trocam: a hora de Brasília perto da meia-noite UTC não se espera acontecer)."""
    return time.time()


def hora_id_de(epoch: float | None = None) -> str:
    """`AAAAMMDDHH` da hora de Brasília de `epoch` (sem ele, a de agora)."""
    return datetime.fromtimestamp(_agora() if epoch is None else epoch, _BRT).strftime("%Y%m%d%H")


# ── o que o pedido pede ──────────────────────────────────────────────────────────────────────────────────────────────
def _metodo_rpc(corpo) -> str:
    """O `method` do JSON-RPC (corpo em lista: o do 1º pedido que traz um; em objeto: o dele). Sem ele, só `rpc`."""
    if not isinstance(corpo, (bytes, bytearray, str)):
        return "rpc"                                    # sem corpo ou em pedaços: não se lê para contar
    try:
        dados = json.loads(corpo)
    except (ValueError, RecursionError):
        return "rpc"
    for item in dados if isinstance(dados, list) else [dados]:
        metodo = item.get("method") if isinstance(item, dict) else None
        if isinstance(metodo, str) and metodo:
            return metodo
    return "rpc"


def _metodo(request) -> str | None:
    """O método da linha do pedido, ou None quando ele não é do Fracttal (e então não conta)."""
    partes = urlsplit(request.url)
    host = (partes.hostname or "").lower()
    if host != DOMINIO and not host.endswith("." + DOMINIO):
        return None                                     # `notfracttal.com` termina em fracttal.com e não é dele
    caminho = partes.path.rstrip("/")
    if caminho.endswith("/rpc/proxy"):
        return _metodo_rpc(request.body)
    if caminho.startswith("/api/"):
        return caminho[len("/api/"):].split("/", 1)[0] or "outro"
    if caminho.endswith("/token"):
        return "token"                                  # o OAuth (`/oauth/token`) e a renovação do JWT (`/rpc/token`)
    return "outro"


# ── a conta ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _registrar(marca: _Marca, metodo: str) -> tuple:
    """Soma o pedido que vai sair na hora e no minuto de agora; devolve onde somou, para a resposta fechar a conta."""
    with _trava:
        agora = _agora()                                # dentro da trava: a ordem das horas é a ordem dos pedidos
        hora_id = hora_id_de(agora)
        hora = _horas.get(hora_id)
        if hora is None:
            hora = _horas[hora_id] = _Hora()
        quem = marca.nome
        if quem.startswith(FUNDO) and quem not in hora.fundos:      # só o fundo tem teto; a rota é limitada pelo app
            if len(hora.fundos) >= MAX_ORIGENS_DE_FUNDO:
                quem = OUTROS                           # a hora já tem os de fundo que cabem: o novo entra no balaio
            else:
                hora.fundos.add(quem)
        chave = (quem, metodo)
        linha = hora.linhas.setdefault(chave, [0, 0, 0, 0])
        linha[_PEDIDOS] += 1
        minuto = int(agora // 60)                       # o fuso é de horas inteiras: o minuto nunca racha uma hora
        if _minuto["id"] != minuto:
            _minuto.update(id=minuto, total=0, chaves={})
        _minuto["total"] += 1
        n = _minuto["chaves"][chave] = _minuto["chaves"].get(chave, 0) + 1
        linha[_PICO] = max(linha[_PICO], n)
        hora.pico = max(hora.pico, _minuto["total"])
        marca.pedidos += 1
    return hora_id, chave


def _abrir(request) -> tuple | None:
    """Conta o pedido que vai sair, se for do Fracttal. Nunca levanta: sem conta, o pedido sai do mesmo jeito."""
    try:
        metodo = _metodo(request)
        if metodo is None:
            return None
        marca = _marca_atual.get()
        if marca is None:                               # sem `origem`: é o fundo, com o nome da thread
            marca = _Marca(_origem_de_fundo())
            _marca_atual.set(marca)
        return _registrar(marca, metodo)
    except Exception:                                   # noqa: BLE001 - o contador não derruba o pedido de ninguém
        log.debug("contador do Fracttal: não consegui contar o pedido", exc_info=True)
        return None


def _fechar(ref: tuple, resposta) -> None:
    """Lança na linha do pedido como ele terminou (`resposta` None = a exceção). Nunca levanta."""
    try:
        if resposta is None:
            coluna = _ERROS
        else:
            # Com redirecionamento o `requests` refaz o pedido pelo mesmo `send` (cada salto conta o seu) e a resposta
            # que volta ao 1º é a FINAL: a do 1º pedido é a primeira da história. Sem isso uma recusa contava duas vezes.
            propria = resposta.history[0] if resposta.history else resposta
            status = propria.status_code
            coluna = _RECUSADOS if status in RECUSAS else _ERROS if status >= 500 else None
        if coluna is None:
            return
        hora_id, chave = ref
        with _trava:
            hora = _horas.get(hora_id)
            linha = hora.linhas.get(chave) if hora else None
            if linha is not None:                       # a hora já drenada não renasce: a gravação trocaria a linha certa
                linha[coluna] += 1
    except Exception:                                   # noqa: BLE001
        log.debug("contador do Fracttal: não consegui fechar a conta do pedido", exc_info=True)


def _embrulhar(enviar):
    @functools.wraps(enviar)
    def contado(self, request, **kwargs):
        ref = _abrir(request)
        if ref is None:
            return enviar(self, request, **kwargs)
        try:
            resposta = enviar(self, request, **kwargs)
        except BaseException:
            _fechar(ref, None)
            raise
        _fechar(ref, resposta)
        return resposta

    setattr(contado, _EMBRULHO, True)
    return contado


def ligar() -> None:
    """Embrulha o `Session.send` do requests, uma vez só (ligar de novo não faz nada)."""
    with _trava:
        atual = requests.sessions.Session.send
        if not getattr(atual, _EMBRULHO, False):
            requests.sessions.Session.send = _embrulhar(atual)


# ── quem pediu ───────────────────────────────────────────────────────────────────────────────────────────────────────
@contextmanager
def origem(nome: str):
    """Marca esta thread: o que ela pedir ao Fracttal dentro do bloco é de `nome` (a rota do pedido, ou `fundo:<nome>`).
    Sem marca, a origem é `fundo:<nome da thread sem o contador de instância>`. A marca vai no contexto: as tarefas que
    copiam o contexto (o `api._ExecutorComContexto`) herdam; a thread aberta à mão e a tarefa do `ThreadPoolExecutor`
    comum começam sem contexto e não (ponha o `origem` dentro da tarefa). Ao sair, volta a de antes."""
    antes = _marca_atual.get()
    _marca_atual.set(_Marca(nome or _origem_de_fundo()))
    try:
        yield
    finally:
        _marca_atual.set(antes)


def pedidos_desta_thread() -> int:
    """Quantos pedidos ao Fracttal o pedido em curso já fez desde o último `zerar_desta_thread()`: os desta thread e os
    das tarefas que herdaram a marca dele. A conta é da marca em que a thread está (o `origem` de dentro tem a sua)."""
    marca = _marca_atual.get()
    return marca.pedidos if marca is not None else 0


def zerar_desta_thread() -> None:
    marca = _marca_atual.get()
    if marca is not None:
        marca.pedidos = 0


# ── o que saiu ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _linha(hora_id: str, quem: str, metodo: str, v: list) -> dict:
    return {"hora_id": hora_id, "origem": quem, "metodo": metodo, "pedidos_qtd": v[_PEDIDOS],
            "recusas_qtd": v[_RECUSADOS], "erros_qtd": v[_ERROS], "pico_minuto_qtd": v[_PICO]}


def _linhas_da_hora(hora_id: str, hora: _Hora) -> list:
    """As linhas de uma hora: a do total (`*`, com o pico de tudo junto) primeiro, depois uma por (origem, método)."""
    soma = [sum(v[i] for v in hora.linhas.values()) for i in (_PEDIDOS, _RECUSADOS, _ERROS)]
    return [_linha(hora_id, "*", "*", soma + [hora.pico])] + [
        _linha(hora_id, o, m, v) for (o, m), v in sorted(hora.linhas.items())]


def instantaneo() -> list:
    """As linhas de todas as horas guardadas, da mais antiga à mais nova, sem tirar nada (o Raio-X)."""
    with _trava:
        return [linha for h in sorted(_horas) for linha in _linhas_da_hora(h, _horas[h])]


def drenar(ate_hora_id: str) -> list:
    """Devolve e tira as linhas das horas FECHADAS: as anteriores a `ate_hora_id`, que é a hora aberta (a de agora,
    `hora_id_de()`) e fica onde está. Em cada hora, a linha `*` com o total e o pico por minuto de tudo."""
    limite = str(ate_hora_id)
    with _trava:
        fechadas = [(h, _horas.pop(h)) for h in sorted(h for h in _horas if h < limite)]
    return [linha for h, hora in fechadas for linha in _linhas_da_hora(h, hora)]


def limpar() -> None:
    """Esquece tudo o que contou (os testes; nada no servidor chama)."""
    with _trava:
        _horas.clear()
        _minuto.update(id=None, total=0, chaves={})
    zerar_desta_thread()
