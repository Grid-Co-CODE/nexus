"""O contador de pedidos ao Fracttal e o porteiro do Nexus (31/10/2026, etapas 0 e 5 do canto central do OS Creator).

A cota do Fracttal é de 200 pedidos por minuto para a empresa toda, dividida entre o OS Creator, o App de Campo e os robôs
do Nexus, e até a etapa 0 ninguém sabia quanto o Nexus gasta dela, a que hora nem quem pede: o Raio-X mostrava o momento e
o journal só o erro. Daqui saem as linhas por hora que o laço do `uso_os` guarda no disco e leva ao banco (`drenar`; a
linha `*` do total vai para a aba própria do total, `fato_uso_os.separar_total`) e que o Raio-X mostra (`instantaneo`).

O gancho é UM só, no `requests.sessions.Session.send`: todo pedido do processo ao Fracttal passa por ele, seja o RPC do OS
Creator (`/rpc/proxy`), o REST do `campo/fracttal.py` (`/api/<recurso>`) ou o token OAuth, e quem pede não muda uma linha.
Conta só o host `fracttal.com` (e os `*.fracttal.com`): o S3 pré-assinado e o resto da internet passam sem contar e sem
porteiro. O porteiro (abaixo) vive no mesmo embrulho, por isso o embrulho mora aqui e em mais nenhum.

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
- **O contador nunca derruba o pedido:** qualquer falha dele (e do porteiro) vai ao log em debug, e a resposta (ou a
  exceção) do pedido volta como veio.

**O porteiro (etapa 5).** Estourar a cota derruba o App de Campo, que vive dela: o desenho do canto central chama isso de
fracasso, mesmo com tudo funcionando. Todo pedido do processo ao Fracttal entra numa conta deslizante de 60 s (`JANELA_S`),
contado na hora em que sai, dentro deste embrulho:
- **Teto do Nexus: 150 por minuto** (`TETO_POR_MINUTO`): sobram 50 dos 200 para o App de Campo e os robôs. **O fundo, até
  90** (`TETO_FUNDO_POR_MINUTO`); os outros 60 são de quem clica.
- **Fundo é só a origem `fundo:` DECLARADA** (`origem(...)` ou, no alvo da thread do laço, `de_fundo(...)`). A marca que o
  contador infere do nome da thread (o pool comum, a thread aberta à mão por uma tela) leva ao fato o nome de sempre,
  `fundo:<thread>`, e o porteiro a trata como clique: o card do OS Creator espera o detalhe lido por trás (`os-web-preparo`)
  e a Aprovação espera as páginas do pool, e como fundo a pessoa esperaria a vez dele, sem limite.
- **Quem clica nunca é recusado:** clique é toda origem que não é fundo declarado (a rota do pedido, inclusive o que a tela
  pede sozinha, com o `X-Nexus-Auto`). Com o minuto cheio ele espera até 2 s (`ESPERA_CLIQUE_MAX_S`) e segue: nenhuma
  thread do waitress fica presa aqui.
- **O fundo espera a vez, sem limite:** passa com menos de 90 de fundo E menos de 150 no total nos últimos 60 s, e cede a
  vaga ao clique que estiver esperando. A leitura dele continua em curso enquanto espera: para quem lê, é só um pedido mais
  lento (o `timeout` do requests nem começa a contar: a espera é antes do adaptador). Quem segura um recurso enquanto pede
  (as 4 vagas do `campo/fracttal.py`) tira a vez ANTES (`reservar_vez`), o fundo e o clique: ninguém espera a vez com uma
  vaga na mão.
- **Ninguém dorme segurando a trava:** a espera é na `threading.Condition` da trava (`_esperar`), com tempo, no máximo
  `PASSO_DA_ESPERA_S` por vez e conferindo de novo; um fundo esperando nunca atrasa um clique.
- **A conta é deste processo:** o PC (que não liga o gancho) e o App de Campo ficam fora dela; os 50 de folga são deles.
- O pedido que esperou conta na linha dele (`esperas_qtd`, na hora em que SAIU), e `estado()` diz as esperas de cada hora,
  de clique e de fundo, o que saiu no último minuto e quem espera agora.

`ligar()` é chamado só pelo servidor (`servir.py`, junto do `teto_os`), nunca pelo `create_app`: o PC e os testes seguem
sem o gancho.
"""
import collections
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
COTA_POR_MINUTO = 200                   # a cota do Fracttal: 200 pedidos por minuto para a empresa toda (página "Limites de Requests")
TETO_POR_MINUTO = 150                   # o Nexus inteiro: sobram 50 da cota para o App de Campo e os robôs
TETO_FUNDO_POR_MINUTO = 90              # o fundo (origem `fundo:`): os outros 60 do teto são de quem clica
ESPERA_CLIQUE_MAX_S = 2.0               # o clique nunca é recusado: com o minuto cheio espera até isto e segue
JANELA_S = 60.0                         # a conta deslizante: a cota do Fracttal é por minuto
PASSO_DA_ESPERA_S = 1.0                 # quem espera a vez confere de novo ao menos a cada segundo (o relógio que pulou)
RECUSAS = (406, 429)                    # o Fracttal pedindo calma (a cota por minuto)
FUNDO = "fundo:"                        # o começo da origem de quem pede por conta própria (laço, thread), não por rota
MAX_ORIGENS_DE_FUNDO = 50               # origens de fundo distintas por hora; a 51ª e as seguintes vão para OUTROS
OUTROS = FUNDO + "outros"
_BRT = timezone(timedelta(hours=-3))
# o contador de instância no fim do nome da thread (ou antes do " (alvo)" que o Python põe): `-137_0`, `-12`, `3`
_CONTADOR = re.compile(r"(?:[-_ ]?\d+)+(?=$| \()")
_EMBRULHO = "_nexus_fracttal_conta"     # no `send` embrulhado: ligar de novo não embrulha o embrulho
_PEDIDOS, _RECUSADOS, _ERROS, _PICO, _ESPERAS = range(5)    # as posições da lista de cada linha

_trava = threading.Lock()               # a única: o gancho roda em todas as threads e a conta é de dicionário pequeno
# quem espera a vez no porteiro dorme aqui, SEM a trava: a `Condition.wait` a solta enquanto dorme e a pega de volta
_vez = threading.Condition(_trava)
_horas: dict = {}                       # hora_id -> _Hora
_minuto = {"id": None, "total": 0, "chaves": {}}    # o minuto corrente e o que já se pediu nele (o resto virou pico)
# a janela do porteiro: quando saiu cada pedido dos últimos 60 s, em ordem (todos, e só os do fundo). Do tamanho do que de
# fato saiu no minuto: o fundo não passa de 90 e o clique que passa sem vaga já esperou os 2 s dele
_janela: collections.deque = collections.deque()
_janela_fundo: collections.deque = collections.deque()
_esperando = {"clique": 0, "fundo": 0}  # quantos esperam a vez agora (o fundo cede a vaga ao clique que espera)


class _Marca:
    """Quem está pedindo: o nome da origem, se ela foi DECLARADA (por `origem`/`de_fundo`; a que o contador infere do nome
    da thread não foi: para o porteiro, só a `fundo:` declarada é fundo) e quantos pedidos ao Fracttal ela já fez (a conta
    do pedido em curso)."""
    __slots__ = ("nome", "pedidos", "declarada")

    def __init__(self, nome: str, declarada: bool = False):
        self.nome, self.pedidos, self.declarada = nome, 0, declarada


class _Reserva:
    """A vez que o fundo declarado tirou antes do pedido (`reservar_vez`): de quem é, se esperou e se o pedido já a usou."""
    __slots__ = ("marca", "esperou", "usada")

    def __init__(self, marca: _Marca, esperou: bool):
        self.marca, self.esperou, self.usada = marca, esperou, False


# O objeto é COMPARTILHADO entre os contextos copiados (a cópia leva a referência): as tarefas do fan-out somam na
# mesma conta. Sem marca no contexto, o 1º pedido cria a do fundo, com o nome da thread.
_marca_atual: contextvars.ContextVar = contextvars.ContextVar("nexus_fracttal_marca", default=None)
_reserva: contextvars.ContextVar = contextvars.ContextVar("nexus_fracttal_reserva", default=None)


class _Hora:
    """Uma hora de Brasília: uma linha [pedidos, recusas, erros, pico, esperas] por (origem, método), as origens de fundo
    que ela já tem (no máximo MAX_ORIGENS_DE_FUNDO; a rota não entra aqui), o pico do total e as esperas da hora como o
    porteiro as tratou, de clique e de fundo (o nome `fundo:<thread>` no fato não diz: a thread sem declaração é clique)."""
    __slots__ = ("linhas", "fundos", "pico", "esperas_clique", "esperas_fundo")

    def __init__(self):
        self.linhas: dict = {}
        self.fundos: set = set()
        self.pico = 0
        self.esperas_clique = self.esperas_fundo = 0


def _nome_de_fundo(nome: str) -> str:
    """O nome da thread sem o contador de instância: `ThreadPoolExecutor-137_0` vira `ThreadPoolExecutor`, `waitress-12`
    vira `waitress` e `Thread-5 (alvo)` vira `Thread (alvo)`. O `campo/regras_app._fx_wo_paralelo` abre um executor NOVO
    a cada chamada; com o nome cru, cada rodada criaria origens novas na tabela da hora, sem fim."""
    return _CONTADOR.sub("", nome) or nome


def _origem_de_fundo() -> str:
    return FUNDO + _nome_de_fundo(threading.current_thread().name)


def _agora() -> float:
    """O relógio (os testes o trocam: a hora de Brasília perto da meia-noite UTC não se espera acontecer). É ele que conta a
    hora, o minuto do pico e a janela do porteiro."""
    return time.time()


def _cronometro() -> float:
    """O relógio do prazo de 2 s do clique: monotônico, para o relógio de parede que o NTP acerta não esticar a espera de
    quem clica (os testes o trocam)."""
    return time.monotonic()


def _esperar(cond: threading.Condition, segundos: float) -> None:
    """Dorme até `segundos`, ou até um aviso, SOLTANDO a trava (`Condition.wait`). Os testes trocam: o relógio falso anda,
    e um minuto de espera leva um instante."""
    cond.wait(segundos)


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


# ── o porteiro ───────────────────────────────────────────────────────────────────────────────────────────────────────
def _e_fundo(marca: _Marca) -> bool:
    """Para o porteiro, fundo é só a origem `fundo:` DECLARADA (o laço que se declara: `origem`, `de_fundo`). A marca que o
    contador infere do nome da thread (o pool comum, a thread aberta à mão) é clique. A revisão da 1ª versão do porteiro
    (31/10/2026, antes de ir ao ar) achou o card do OS Creator, que espera até 45 s o detalhe lido por trás
    (`os-web-preparo`), e a Aprovação, que espera as páginas do pool: como fundo, a pessoa esperaria a vez do fundo, sem
    limite. O nome que vai ao fato não muda."""
    return marca.declarada and marca.nome.startswith(FUNDO)


def _ligado() -> bool:
    """O gancho está no `Session.send` deste processo (só o servidor liga): sem ele não há porteiro."""
    return bool(getattr(requests.sessions.Session.send, _EMBRULHO, False))


def _podar(agora: float) -> None:
    """Com a trava na mão: tira da janela o que saiu há 60 s ou mais. Se o relógio de parede voltou (o NTP acertou para
    trás), o que ficou "no futuro" passa a ser de agora: segue contando, e a janela não fica presa num minuto que não acaba."""
    corte = agora - JANELA_S
    for fila in (_janela, _janela_fundo):
        while fila and fila[0] <= corte:
            fila.popleft()
        futuros = 0
        while fila and fila[-1] > agora:
            fila.pop()
            futuros += 1
        fila.extend([agora] * futuros)


def _falta(fila, teto: int, agora: float) -> float:
    """Segundos até a `fila` ter menos de `teto` pedidos nos últimos 60 s (0: já tem). Quem precisa sair da janela para
    abrir a vaga é o pedido de posição `len - teto`, contando do mais velho."""
    excesso = len(fila) - teto
    return 0.0 if excesso < 0 else max(fila[excesso] + JANELA_S - agora, 0.0)


def _vez_de(fundo: bool) -> tuple:
    """Com a trava na mão: espera a vez do pedido que vai sair e devolve `(esperou, agora)`, com `agora` o instante em que
    ele sai. O clique passa com menos de 150 no último minuto e, sem vaga, espera até 2 s e passa assim mesmo: nunca é
    recusado. O fundo passa com menos de 150 no total, menos de 90 de fundo e nenhum clique esperando a vez; senão espera,
    sem limite. A espera solta a trava (`_esperar`, a Condition): os outros pedidos, a conta e o Raio-X andam enquanto isso."""
    tipo = "fundo" if fundo else "clique"
    prazo = None if fundo else _cronometro() + ESPERA_CLIQUE_MAX_S
    esperou = False
    try:
        while True:
            agora = _agora()
            _podar(agora)
            falta = _falta(_janela, TETO_POR_MINUTO, agora)
            if fundo:
                falta = max(falta, _falta(_janela_fundo, TETO_FUNDO_POR_MINUTO, agora))
                if not falta and _esperando["clique"]:
                    falta = PASSO_DA_ESPERA_S           # a vaga é do clique que espera: ele avisa quando passar
            if not falta:
                return esperou, agora
            if prazo is not None:
                resta = prazo - _cronometro()
                if resta <= 0:
                    return esperou, agora               # os 2 s acabaram: o clique segue sem vaga, nunca é recusado
                falta = min(falta, resta)
            if not esperou:
                esperou = True
                _esperando[tipo] += 1
            _esperar(_vez, min(falta, PASSO_DA_ESPERA_S))
    finally:
        if esperou:
            _esperando[tipo] -= 1
            if not fundo:
                _vez.notify_all()                       # o fundo que cedeu a vaga a este clique confere de novo


# ── a conta ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def _registrar(marca: _Marca, metodo: str) -> tuple:
    """Espera a vez no porteiro e soma o pedido na hora e no minuto em que ele sai; devolve onde somou, para a resposta
    fechar a conta. O pedido com a vez já reservada (`reservar_vez`) não espera nem entra na janela de novo."""
    with _trava:
        fundo = _e_fundo(marca)
        reserva = _reserva.get()
        if reserva is not None and reserva.marca is marca and not reserva.usada:
            reserva.usada = True                        # a vez foi tirada antes da vaga do `campo/fracttal.py`, e já contou
            esperou, agora = reserva.esperou, _agora()
        else:
            # pode soltar a trava enquanto espera (a Condition) e volta com ela na mão; dali até somar, ninguém mais entra
            esperou, agora = _vez_de(fundo)
            _janela.append(agora)                       # no mesmo passo da vez: duas threads nunca pegam a mesma vaga
            if fundo:
                _janela_fundo.append(agora)
        hora_id = hora_id_de(agora)                     # dentro da trava: a ordem das horas é a ordem dos pedidos
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
        linha = hora.linhas.setdefault(chave, [0, 0, 0, 0, 0])
        linha[_PEDIDOS] += 1
        if esperou:
            linha[_ESPERAS] += 1                        # na hora em que saiu, junto com o pedido
            if fundo:
                hora.esperas_fundo += 1
            else:
                hora.esperas_clique += 1
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
    """Passa o pedido que vai sair pelo porteiro e o conta, se for do Fracttal (o resto da internet nem para aqui). Nunca
    levanta: com o porteiro ou a conta quebrados, o pedido sai do mesmo jeito, sem esperar e sem contar."""
    try:
        metodo = _metodo(request)
        if metodo is None:
            return None
        marca = _marca_atual.get()
        if marca is None:                               # sem `origem`: o nome da thread, inferido (o porteiro: clique)
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
    """Marca esta thread: o que ela pedir ao Fracttal dentro do bloco é de `nome` (a rota do pedido, ou `fundo:<nome>`), e a
    marca é DECLARADA: a `fundo:` declarada é o fundo do porteiro. Sem marca (ou com o nome vazio), a origem é inferida,
    `fundo:<nome da thread sem o contador de instância>`, e o porteiro a trata como clique. A marca vai no contexto: as
    tarefas que copiam o contexto (o `api._ExecutorComContexto`) herdam; a thread aberta à mão e a tarefa do
    `ThreadPoolExecutor` comum começam sem contexto e não (ponha o `origem` dentro da tarefa, ou o `de_fundo` no alvo da
    thread). Ao sair, volta a de antes."""
    antes = _marca_atual.get()
    _marca_atual.set(_Marca(nome or _origem_de_fundo(), declarada=bool(nome)))
    try:
        yield
    finally:
        _marca_atual.set(antes)


def de_fundo(nome: str, fn):
    """`fn` rodando com a origem de fundo DECLARADA `nome`, para o ALVO da thread de um laço do servidor ou de uma releitura
    por trás: `threading.Thread(target=fracttal_conta.de_fundo("fundo:nexus-tarefas-os-banco", laco), ...)`, numa linha. A
    declaração vale só dentro de `fn` (sai junto com ela) e mantém o nome que o fato já mostrava, o da thread. Nunca na
    função que um clique também roda na hora (a releitura da Engenharia com `esperar=True` roda na thread do pedido): ali o
    clique passaria a esperar a vez do fundo."""
    if not str(nome).startswith(FUNDO):
        raise ValueError(f"a origem de fundo começa com {FUNDO!r}: {nome!r}")

    @functools.wraps(fn)
    def declarado(*args, **kwargs):
        with origem(nome):
            return fn(*args, **kwargs)
    return declarado


@contextmanager
def reservar_vez():
    """A vez no porteiro tirada ANTES do pedido, para quem segura um recurso enquanto pede ao Fracttal: as 4 vagas do
    `campo/fracttal.py` (`with fracttal_conta.reservar_vez(), _VAGAS:`), para ninguém esperar a vez com uma vaga na mão.
    Nas versões de antes (31/10/2026, antes de ir ao ar), quem esperava a vez segurava a vaga: 4 leitores de fundo parados
    no porteiro prendiam, sem limite, o clique que lê pelo mesmo arquivo, e, com o minuto cheio, o 12º clique da fila
    somava 6 s. Cada um espera a sua vez aqui, sem a vaga, como espera no envio: o fundo declarado sem limite, o resto (o
    clique, a thread sem declaração) no máximo 2 s. A reserva já entra na
    janela; o 1º pedido dentro do bloco a honra (não espera nem conta de novo na janela; a hora e a espera vão à linha dele,
    como sempre). Sem o gancho (o PC, os testes) não faz nada. A reserva que sobrou (o pedido que nem saiu) morre no fim do
    bloco. Nunca levanta: com o porteiro quebrado, o pedido segue sem reserva."""
    reserva = None
    try:
        if _ligado():
            marca = _marca_atual.get()
            if marca is None:                           # como o 1º pedido faria (`_abrir`): o nome da thread, inferido
                marca = _Marca(_origem_de_fundo())
                _marca_atual.set(marca)
            fundo = _e_fundo(marca)
            with _trava:
                esperou, agora = _vez_de(fundo)
                _janela.append(agora)
                if fundo:
                    _janela_fundo.append(agora)
            reserva = _Reserva(marca, esperou)
    except Exception:                                   # noqa: BLE001 - o porteiro não derruba o pedido de ninguém
        log.debug("porteiro do Fracttal: não consegui reservar a vez", exc_info=True)
    token = _reserva.set(reserva)
    try:
        yield
    finally:
        _reserva.reset(token)


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
            "recusas_qtd": v[_RECUSADOS], "erros_qtd": v[_ERROS], "pico_minuto_qtd": v[_PICO],
            "esperas_qtd": v[_ESPERAS]}


def _linhas_da_hora(hora_id: str, hora: _Hora) -> list:
    """As linhas de uma hora: a do total (`*`, com o pico de tudo junto) primeiro, depois uma por (origem, método)."""
    total = [sum(v[i] for v in hora.linhas.values()) for i in range(_ESPERAS + 1)]
    total[_PICO] = hora.pico                            # o pico do total não é a soma dos picos: é o de tudo junto
    return [_linha(hora_id, "*", "*", total)] + [
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


def estado() -> dict:
    """O porteiro agora, só contagens: se o gancho está ligado neste processo (só o servidor liga), os tetos, quantos
    pedidos saíram nos últimos 60 s (`ultimo_minuto`: todos e os do fundo), quantos esperam a vez neste instante
    (`esperando`: clique e fundo) e as esperas de cada hora que o contador ainda guarda (`esperas_por_hora`, da mais antiga
    à mais nova: a aberta e a que o laço do :05 ainda não tirou), de clique e de fundo como o porteiro as tratou (a thread
    sem declaração é clique, mesmo com o nome `fundo:<thread>` no fato). Somadas por hora, são as mesmas que vão ao banco
    por linha, como `esperas_qtd`."""
    with _trava:
        _podar(_agora())
        horas = [{"hora_id": h, "clique": _horas[h].esperas_clique, "fundo": _horas[h].esperas_fundo}
                 for h in sorted(_horas)]
        return {"ligado": _ligado(),
                "teto_por_minuto": TETO_POR_MINUTO, "teto_fundo_por_minuto": TETO_FUNDO_POR_MINUTO,
                "espera_clique_max_s": ESPERA_CLIQUE_MAX_S,
                "ultimo_minuto": {"todos": len(_janela), "fundo": len(_janela_fundo)},
                "esperando": dict(_esperando), "esperas_por_hora": horas}


def limpar() -> None:
    """Esquece tudo o que contou, e a janela do porteiro (os testes; nada no servidor chama). Quem esperava a vez confere
    de novo: a janela vazia o deixa passar."""
    with _trava:
        _horas.clear()
        _minuto.update(id=None, total=0, chaves={})
        _janela.clear()
        _janela_fundo.clear()
        _vez.notify_all()
    zerar_desta_thread()
