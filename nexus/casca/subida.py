"""A fila de subida: as tarefas de aquecimento do boot, uma depois da outra (16/11/2026, Levi: "pode seguir com a fila de
subida").

O caso: em 16/11/2026 o Raio-X mostrou o processador do Nexus em 231%, 167% e 242% depois de cada deploy. Com o
processador por thread no ar (o reinício das 17:47), a leitura dos primeiros minutos não achou um culpado: eram umas dez
tarefas de subida ao mesmo tempo, cada uma com 10 a 40% de um núcleo por meio a dois minutos (a releitura da fila da
Aprovação, a conta dela, a pré-carga, os chamados, o pré-filtro, as contas do Campo, os livros do SSO). O Nexus é um
processo Python só, e nele roda UMA conta por vez: com N tarefas disputando, o clique da pessoa fica com 1/(N+1) do
processador a cada troca, e o Raio-X, que abre em 1 s, levava de 8 a 42 s.

O que este módulo dá:
- `vez(nome)`: a tarefa de subida entra na fila e roda quando chega a vez dela, na ordem de chegada. Uma por vez. A que
  passa de PRAZO_S com a vez (está esperando a rede, quase sempre) não segura as outras: a seguinte entra, e ela termina
  por fora. Reentrante: quem já tem a vez não espera de novo.
- `esperar_calma()`: para o que só deve rodar DEPOIS da subida (a pré-carga das telas, o pré-filtro das fotos): espera
  o boot passar de SOSSEGO_S e a fila esvaziar.
- A fila só vale na JANELA_S depois do boot (`ligar`, chamado pelo servir.py e pelo app.py). Fora dela, e onde ninguém
  ligou (o `create_app`, os testes), `vez` e `esperar_calma` não esperam nada: tudo roda como antes.

O pedido de uma pessoa NUNCA entra na fila: quem espera a vez são só as tarefas de fundo da subida. O que a fila custa é
a tela fria por mais tempo (as cópias ficam prontas uma depois da outra, e a pré-carga só depois de 5 min, que já era o
prazo da volta do boot); o que ela dá é o Nexus respondendo enquanto isso. `estado()` vai ao Raio-X.
"""
import threading
import time
from collections import deque
from contextlib import contextmanager

JANELA_S = 15 * 60          # depois disto do boot a fila se desliga
PRAZO_S = 90                # quanto a tarefa da vez segura as outras; passou disso, a seguinte entra
SOSSEGO_S = 300             # antes disto do boot, o que roda "depois da subida" nem começa (os 5 min da pré-carga)
PASSO_S = 1.0               # de quanto em quanto quem espera confere o prazo do dono e a janela
GUARDAR = 40                # as últimas tarefas que passaram, para o Raio-X

_RELOGIO = time.monotonic
_COND = threading.Condition()
_FILA: deque = deque()      # (senha, nome) de quem espera a vez, na ordem de chegada
_E = {"inicio": None, "dono": None, "desde": 0.0, "senha": 0, "feitas": deque(maxlen=GUARDAR)}
_LOCAL = threading.local()


def ligar() -> None:
    """Marca o boot: a partir daqui, por JANELA_S, as tarefas de subida rodam uma por vez. Quem chama é o servir.py e o
    app.py, antes dos `instalar_*`; nunca o `create_app` (os testes não entram em fila nenhuma)."""
    with _COND:
        if _E["inicio"] is None:
            _E["inicio"] = _RELOGIO()


def desligar() -> None:
    """Volta ao estado de quem nunca ligou (os testes)."""
    with _COND:
        _E.update(inicio=None, dono=None, desde=0.0, senha=0, feitas=deque(maxlen=GUARDAR))
        _FILA.clear()
        _COND.notify_all()


def ativa() -> bool:
    inicio = _E["inicio"]
    return inicio is not None and _RELOGIO() - inicio < JANELA_S


def _livre(agora: float) -> bool:
    return _E["dono"] is None or agora - _E["desde"] >= PRAZO_S


@contextmanager
def vez(nome: str):
    """A vez de uma tarefa de subida: espera as que chegaram antes, roda, e passa a vez."""
    if getattr(_LOCAL, "dentro", 0) or not ativa():
        yield
        return
    chegou = _RELOGIO()
    com_a_vez = False
    with _COND:
        _E["senha"] += 1
        eu = (_E["senha"], nome)
        _FILA.append(eu)
        while ativa():
            if _FILA[0] is eu and _livre(_RELOGIO()):
                com_a_vez = True
                break
            _COND.wait(PASSO_S)
        _FILA.remove(eu)
        entrou = _RELOGIO()
        if com_a_vez:
            _E["dono"], _E["desde"] = eu, entrou
        _COND.notify_all()
    _LOCAL.dentro = 1
    try:
        yield
    finally:
        _LOCAL.dentro = 0
        with _COND:
            if _E["dono"] is eu:
                _E["dono"] = None
            _E["feitas"].append({"nome": nome, "esperou_s": round(entrou - chegou, 1),
                                 "levou_s": round(_RELOGIO() - entrou, 1)})
            _COND.notify_all()


def uma_por_vez(nome: str, funcao):
    """`funcao` embrulhada na vez: para o alvo de uma thread de subida."""
    def com_a_vez(*a, **k):
        with vez(nome):
            return funcao(*a, **k)
    return com_a_vez


def esperar_calma(max_s: float | None = None) -> bool:
    """Para o que roda DEPOIS da subida: espera o boot passar de SOSSEGO_S e a fila esvaziar (ninguém com a vez dentro
    do prazo, ninguém esperando), no máximo `max_s` (padrão: até a janela acabar). Devolve se esperou. Fora da janela,
    sem `ligar` ou para quem já tem a vez, não espera."""
    if getattr(_LOCAL, "dentro", 0) or not ativa():
        return False
    fim = None if max_s is None else _RELOGIO() + max_s
    esperou = False
    with _COND:
        while ativa():
            agora = _RELOGIO()
            calma = agora - _E["inicio"] >= SOSSEGO_S and not _FILA and _livre(agora)
            if calma or (fim is not None and agora >= fim):
                break
            esperou = True
            _COND.wait(PASSO_S)
    return esperou


def estado() -> dict:
    """Para o Raio-X: {"ligada", "ativa", "ha_s" (desde o boot), "dono" {"nome", "ha_s"} | None, "fila" [nomes],
    "feitas" [{"nome", "esperou_s", "levou_s"}] na ordem em que terminaram}. Só nomes de tarefa e segundos."""
    with _COND:
        agora = _RELOGIO()
        inicio, dono = _E["inicio"], _E["dono"]
        return {"ligada": inicio is not None, "ativa": inicio is not None and agora - inicio < JANELA_S,
                "ha_s": round(agora - inicio) if inicio is not None else None,
                "dono": {"nome": dono[1], "ha_s": round(agora - _E["desde"])} if dono else None,
                "fila": [n for _s, n in _FILA], "feitas": [dict(f) for f in _E["feitas"]]}
