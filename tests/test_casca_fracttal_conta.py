"""O contador de pedidos ao Fracttal (31/10/2026, etapa 0 do canto central do OS Creator): a cota de 200 pedidos por
minuto é da empresa toda, e até aqui ninguém sabia quanto o Nexus gasta dela, a que hora nem quem pede. O contador é UM
gancho no `Session.send` do requests, por onde passa todo pedido ao Fracttal. Provas, com a `requests.Session` de verdade
e um adaptador falso (nada vai à rede): só o host do Fracttal conta; a origem é a da thread; o método sai do corpo do RPC
ou do caminho do REST; recusa (406/429) e erro (exceção ou 5xx) à parte; o pico por minuto; a hora é a de Brasília; a
drenagem tira só as horas fechadas; ligar duas vezes não conta em dobro; e o contador nunca derruba o pedido."""
import contextvars
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
import requests
from requests.adapters import BaseAdapter

from nexus.casca import fracttal_conta as C
from sessao_real_sem_rede import AdaptadorFalso, sessao_real

_API = "https://app.fracttal.com/api/work_orders?limit=100"
_RPC = "https://app.fracttal.com/rpc/proxy"
_HORA_10 = "2026103010"                 # 13:00Z de 30/10/2026 = 10:00 em Brasília (UTC-3, sem horário de verão)
_COLUNAS = {"hora_id", "origem", "metodo", "pedidos_qtd", "recusas_qtd", "erros_qtd", "pico_minuto_qtd", "esperas_qtd"}


def _epoca(utc: str) -> float:
    return datetime.fromisoformat(utc).timestamp()


class _Relogio:
    """O relógio na mão: a hora de Brasília perto da meia-noite UTC não se espera acontecer. O porteiro mora no mesmo gancho
    (etapa 5): a espera dele anda este relógio (e o cronômetro do clique) em vez de dormir, como no test_casca_porteiro.py,
    então o teste que passa de 90 de fundo no mesmo minuto termina, em vez de esperar para sempre o relógio parado."""

    def __init__(self, utc="2026-10-30T13:00:00+00:00"):
        self.t = _epoca(utc)
        self.mono = 5000.0

    def __call__(self) -> float:
        return self.t

    def cronometro(self) -> float:
        return self.mono

    def esperar(self, cond, segundos: float) -> None:
        self.t += segundos
        self.mono += segundos

    def em(self, utc: str) -> "_Relogio":
        self.t = _epoca(utc)
        return self


class _Cai(BaseAdapter):
    """O Fracttal que não responde: levanta a exceção dada, como o adaptador de verdade faz com a rede fora do ar."""

    def __init__(self, erro):
        super().__init__()
        self.erro = erro

    def send(self, request, **kwargs):
        raise self.erro

    def close(self):
        pass


class _Drena(AdaptadorFalso):
    """O adaptador que, no meio do pedido, deixa a gravação da hora drenar o contador (o pedido ainda nem voltou)."""

    def __init__(self, *respostas, ate):
        super().__init__(*respostas)
        self.ate, self.drenado = ate, None

    def send(self, request, **kwargs):
        self.drenado = C.drenar(self.ate)
        return super().send(request, **kwargs)


def _em_thread_nova(nome, alvo):
    """Roda `alvo` numa thread de nome `nome`, com o contexto vazio (como a aberta à mão), e espera ela acabar."""
    t = threading.Thread(target=lambda: contextvars.Context().run(alvo), name=nome)
    t.start()
    t.join()


@pytest.fixture
def relogio(monkeypatch):
    """O contador ligado e zerado, com o relógio na mão (10:00 de Brasília); o `Session.send` volta ao que era no fim."""
    # (o monkeypatch guarda o `Session.send` de antes do ligar() e o devolve no fim do teste)
    monkeypatch.setattr(requests.sessions.Session, "send", requests.sessions.Session.send)
    C.limpar()
    r = _Relogio()
    monkeypatch.setattr(C, "_agora", r)
    monkeypatch.setattr(C, "_cronometro", r.cronometro)
    monkeypatch.setattr(C, "_esperar", r.esperar)
    C.ligar()
    yield r
    C.limpar()


def _linha(origem, metodo, hora=_HORA_10):
    achadas = [lin for lin in C.instantaneo() if (lin["hora_id"], lin["origem"], lin["metodo"]) == (hora, origem, metodo)]
    assert len(achadas) == 1, f"{(hora, origem, metodo)} em {C.instantaneo()}"
    return achadas[0]


def _contas(origem, metodo, hora=_HORA_10):
    lin = _linha(origem, metodo, hora)
    return lin["pedidos_qtd"], lin["recusas_qtd"], lin["erros_qtd"], lin["pico_minuto_qtd"]


# ── só o Fracttal conta ──────────────────────────────────────────────────────────────────────────────────────────────
def test_conta_so_o_fracttal(relogio):
    s, ad = sessao_real(*[(200, None)] * 8)
    with C.origem("teste"):
        s.get("https://app.fracttal.com/api/work_orders")               # conta
        s.post("https://one.fracttal.com/oauth/token")                  # outro host do Fracttal: conta
        s.get("https://fracttal.com/api/items")                         # o domínio puro: conta
        s.get("https://example.com/api/work_orders")                    # não conta
        s.get("https://notfracttal.com/api/work_orders")                # termina em fracttal.com, mas é de outro dono
        s.get("https://app.fracttal.com.example.org/api/work_orders")   # o Fracttal só no começo do nome
        s.get("https://bucket.s3.amazonaws.com/fracttal.com/foto.png?x=app.fracttal.com")   # no caminho ou na query
        s.get("https://example.com/redirect?para=https://app.fracttal.com/api/items")
        assert C.pedidos_desta_thread() == 3
    assert [(lin["origem"], lin["metodo"], lin["pedidos_qtd"]) for lin in C.instantaneo()] == [
        ("*", "*", 3), ("teste", "items", 1), ("teste", "token", 1), ("teste", "work_orders", 1)]
    assert len(ad.pedidos) == 8                                          # contar não segura nem tira nenhum pedido


# ── a origem ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_origem_da_thread_e_do_fundo(relogio):
    s, _ = sessao_real(*[(200, None)] * 5)
    nome = threading.current_thread().name
    s.get(_API)                                                          # sem marca: o trabalho de fundo desta thread
    with C.origem("/os/os/<n>"):
        s.get(_API)
        with C.origem("/os/api/ativos"):
            s.get(_API)
        s.get(_API)                                                      # saiu da de dentro: volta à de fora
    s.get(_API)                                                          # saiu das duas: de novo o fundo

    def outra_thread():
        s2, _ = sessao_real((200, None))
        s2.get(_API)

    # A thread aberta à mão começa com o contexto vazio (aqui explícito, para valer também onde a thread herda o do pai):
    # não herda a marca de quem a abriu e é trabalho de fundo, com o nome dela.
    t = threading.Thread(target=lambda: contextvars.Context().run(outra_thread), name="nexus-teste-fundo")
    with C.origem("/os/os/<n>"):
        t.start()
        t.join()
    assert {lin["origem"]: lin["pedidos_qtd"] for lin in C.instantaneo() if lin["origem"] != "*"} == {
        f"fundo:{nome}": 2, "/os/os/<n>": 2, "/os/api/ativos": 1, "fundo:nexus-teste-fundo": 1}


def test_pedidos_do_pedido_em_curso(relogio):
    s, _ = sessao_real(*[(200, None)] * 7)
    with C.origem("/os/os/<n>"):
        assert C.pedidos_desta_thread() == 0
        s.get(_API)
        s.get(_API)
        assert C.pedidos_desta_thread() == 2
        with C.origem("/os/api/ativos"):                                 # a conta é a da origem em que a thread está
            s.get(_API)
            assert C.pedidos_desta_thread() == 1
        assert C.pedidos_desta_thread() == 2                             # saiu da de dentro: a de fora seguiu onde estava
        C.zerar_desta_thread()                                           # o começo do pedido seguinte da mesma thread
        assert C.pedidos_desta_thread() == 0
        s.get(_API)
        assert C.pedidos_desta_thread() == 1
    C.zerar_desta_thread()                                               # sem origem a conta é a da própria thread
    s.get(_API)
    s.get(_API)
    assert C.pedidos_desta_thread() == 2


def test_tarefas_que_copiam_o_contexto_herdam_a_origem_e_a_conta(relogio):
    # O `api._ExecutorComContexto` do OS Creator copia o contexto do pedido para cada tarefa (o JWT de quem pediu viaja
    # assim): o catálogo de ativos pede ~110 vezes, 6 de uma vez, e esses pedidos são da rota que os chamou.
    class ComContexto(ThreadPoolExecutor):
        def submit(self, fn, /, *args, **kwargs):
            return super().submit(contextvars.copy_context().run, fn, *args, **kwargs)

    def pedir(_):
        sessao_real((200, None))[0].get(_API)

    with C.origem("/os/api/ativos"):
        with ComContexto(max_workers=4) as ex:
            list(ex.map(pedir, range(12)))
        assert C.pedidos_desta_thread() == 12                            # a conta do pedido tem os das tarefas
        with ThreadPoolExecutor(max_workers=2) as ex:                    # o executor comum começa sem contexto: fundo
            list(ex.map(pedir, range(2)))
        assert C.pedidos_desta_thread() == 12
    quem = {lin["origem"]: lin["pedidos_qtd"] for lin in C.instantaneo() if lin["origem"] != "*"}
    assert quem == {"/os/api/ativos": 12, "fundo:ThreadPoolExecutor": 2}      # sem o -N_M do executor


def test_origem_sem_nome_vale_como_sem_marca(relogio):
    s, _ = sessao_real((200, None))
    with C.origem(""):
        s.get(_API)
    assert _linha(f"fundo:{threading.current_thread().name}", "work_orders")["pedidos_qtd"] == 1

    def vazia():
        with C.origem(""):                                      # a thread de nome com contador: o mesmo `fundo:` sem ele
            s2, _ = sessao_real((200, None))
            s2.get(_API)

    _em_thread_nova("waitress-7", vazia)
    assert _linha("fundo:waitress", "work_orders")["pedidos_qtd"] == 1


# ── o fundo sem contador e o teto de origens ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("nome, esperado", [
    ("ThreadPoolExecutor-137_0", "ThreadPoolExecutor"),       # o do `regras_app._fx_wo_paralelo`: um executor por chamada
    ("ThreadPoolExecutor-0_12", "ThreadPoolExecutor"),
    ("waitress-12", "waitress"),
    ("waitress-0", "waitress"),
    ("Thread-5 (alvo)", "Thread (alvo)"),                     # o nome que o Python dá à thread aberta sem nome
    ("Thread-12", "Thread"),
    ("Dummy-3", "Dummy"),
    ("worker3", "worker"),                                    # contador colado no fim
    ("nexus-setor-2", "nexus-setor"),
    ("Thread-5 (rodar_2)", "Thread (rodar_2)"),               # o número do nome da função não é contador
    ("nexus-memoria", "nexus-memoria"),                       # o que não tem contador fica como está
    ("nexus-pre-carga-boot", "nexus-pre-carga-boot"),
    ("MainThread", "MainThread"),
    ("7", "7"),                                               # só número: não deixa a origem sem nome
])
def test_nome_da_thread_sem_o_contador(nome, esperado):
    assert C._nome_de_fundo(nome) == esperado


def test_thread_com_contador_no_nome_vira_uma_origem_de_fundo_so(relogio):
    s, _ = sessao_real(*[(200, None)] * 3)

    def pedir():
        s.get(_API)

    for nome in ("waitress-12", "waitress-13", "Thread-5 (alvo)"):
        _em_thread_nova(nome, pedir)
    assert {lin["origem"]: lin["pedidos_qtd"] for lin in C.instantaneo() if lin["origem"] != "*"} == {
        "fundo:waitress": 2, "fundo:Thread (alvo)": 1}


def test_executor_novo_a_cada_rodada_nao_cria_origem_nova(relogio):
    # O `campo/regras_app._fx_wo_paralelo` abre um ThreadPoolExecutor NOVO a cada chamada, e o nome das threads dele leva o
    # contador da instância (`ThreadPoolExecutor-137_0`): com o nome cru cada rodada criaria origens novas na tabela da hora.
    def pedir(_):
        sessao_real((200, None))[0].get(_API)

    for _ in range(5):
        with ThreadPoolExecutor(max_workers=2) as ex:
            list(ex.map(pedir, range(4)))
    assert {lin["origem"]: lin["pedidos_qtd"] for lin in C.instantaneo() if lin["origem"] != "*"} == {
        "fundo:ThreadPoolExecutor": 20}


def test_teto_de_origens_de_fundo_por_hora(relogio):
    assert C.MAX_ORIGENS_DE_FUNDO == 50
    n = C.MAX_ORIGENS_DE_FUNDO
    # As 50 primeiras origens de fundo da hora têm linha própria; a 51ª e as que vierem (aqui, a 51ª com uma recusa e a
    # 52ª) são contadas em `fundo:outros`; as 50 que já existem seguem contando nas suas.
    s, _ = sessao_real(*[(200, None)] * n, (429, None), (200, None), (200, None))
    for i in range(n):
        with C.origem(f"fundo:laco-{i}"):
            s.get(_API)
    with C.origem(f"fundo:laco-{n}"):
        s.get(_API)
        assert C.pedidos_desta_thread() == 1                    # a conta do pedido não depende de onde a hora o pôs
    with C.origem("fundo:laco-0"):
        s.get(_API)
    with C.origem(f"fundo:laco-{n + 1}"):
        s.get(_API)
    origens = {lin["origem"] for lin in C.instantaneo() if lin["origem"] != "*"}
    assert len(origens) == n + 1 and "fundo:outros" in origens and f"fundo:laco-{n}" not in origens
    assert _contas("fundo:outros", "work_orders")[:3] == (2, 1, 0)      # a recusa da 51ª foi para a linha em que ela contou
    assert _contas("fundo:laco-0", "work_orders")[0] == 2
    assert _contas("*", "*")[0] == n + 3
    # a hora seguinte recomeça a conta: o laço que não coube agora tem linha própria
    relogio.em("2026-10-30T14:00:00+00:00")
    with C.origem(f"fundo:laco-{n}"):
        sessao_real((200, None))[0].get(_API)
    assert _contas(f"fundo:laco-{n}", "work_orders", "2026103011")[0] == 1


def test_rota_nao_tem_teto_e_nao_gasta_a_vaga_do_fundo(relogio):
    # A rota (a origem que o gancho do pedido põe, sem `fundo:`) é limitada pelo conjunto de rotas do app: sem teto, e sem
    # tirar vaga do fundo. Só o nome que ganha número novo a cada vez (o de thread) precisava de freio.
    n = C.MAX_ORIGENS_DE_FUNDO
    s, _ = sessao_real(*[(200, None)] * (60 + n), (200, None))
    for i in range(60):
        with C.origem(f"/os/rota/{i}"):
            s.get(_API)
    for i in range(n):
        with C.origem(f"fundo:laco-{i}"):
            s.get(_API)
    with C.origem(f"fundo:laco-{n}"):                            # a 51ª de fundo: só ela vai para o balaio
        s.get(_API)
    origens = {lin["origem"] for lin in C.instantaneo() if lin["origem"] != "*"}
    assert all(_contas(f"/os/rota/{i}", "work_orders")[0] == 1 for i in range(60))      # as 60 rotas, cada uma na sua
    assert {f"fundo:laco-{i}" for i in range(n)} <= origens                              # e as 50 de fundo, inteiras
    assert _contas("fundo:outros", "work_orders")[0] == 1 and f"fundo:laco-{n}" not in origens
    assert len(origens) == 60 + n + 1


# ── o método ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _gerador():
    yield b"em pedacos"


@pytest.mark.parametrize("verbo, url, args, esperado", [
    ("POST", _RPC, {"json": [{"id": "1", "jsonrpc": "2.0", "method": "inventories.items_list", "params": {}}]},
     "inventories.items_list"),                                          # o corpo do OS Creator: uma lista de um pedido
    ("POST", _RPC, {"json": {"jsonrpc": "2.0", "method": "tasks.x", "params": {}}}, "tasks.x"),      # ou um objeto
    ("POST", _RPC, {"json": [{"id": "1"}, {"method": "segundo.metodo"}]}, "segundo.metodo"),         # o 1º que traz
    ("POST", _RPC + "/", {"json": [{"method": "com.barra"}]}, "com.barra"),
    ("POST", _RPC, {"data": "isto não é JSON"}, "rpc"),
    ("POST", _RPC, {"data": b"\xff\xfe\x00"}, "rpc"),                    # bytes que nem decodificam
    ("POST", _RPC, {}, "rpc"),                                           # sem corpo
    ("POST", _RPC, {"json": [1, 2]}, "rpc"),
    ("POST", _RPC, {"json": [{"method": 5}]}, "rpc"),
    ("POST", _RPC, {"data": _gerador()}, "rpc"),                         # corpo em pedaços: não se lê para contar
    ("GET", "https://app.fracttal.com/api/work_orders?limit=100&start=0", {}, "work_orders"),
    ("GET", "https://app.fracttal.com/api/work_orders/123/tasks", {}, "work_orders"),
    ("GET", "https://app.fracttal.com/api/", {}, "outro"),
    ("POST", "https://app.fracttal.com/oauth/token", {"data": {"grant_type": "client_credentials"}}, "token"),
    ("POST", "https://one.fracttal.com/rpc/token", {}, "token"),         # a renovação do JWT da sessão
    ("POST", "https://app.fracttal.com/rpc/login_new", {"json": {"usuario": "x"}}, "outro"),
    ("GET", "https://app.fracttal.com/", {}, "outro"),
])
def test_metodo_do_rpc_e_do_rest(relogio, verbo, url, args, esperado):
    s, _ = sessao_real((200, None))
    with C.origem("teste"):
        s.request(verbo, url, **args)
    assert [(lin["origem"], lin["metodo"], lin["pedidos_qtd"]) for lin in C.instantaneo()] == [
        ("*", "*", 1), ("teste", esperado, 1)]


# ── recusa e erro ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_recusa_e_erro(relogio):
    respostas = [(200, None), (429, None), (406, None), (500, None), (503, None), (404, None), (401, None)]
    s, _ = sessao_real(*respostas)
    with C.origem("teste"):
        assert [s.get(_API).status_code for _ in respostas] == [r[0] for r in respostas]   # a resposta passa como veio
    # recusa = 406 e 429 (o Fracttal pedindo calma); erro = 5xx; 401 e 404 não são nem uma coisa nem outra
    assert _contas("teste", "work_orders")[:3] == (7, 2, 2)

    erro = requests.exceptions.ConnectTimeout("sem resposta")           # a exceção conta como erro e sobe a mesma
    cai = requests.Session()
    cai.trust_env = False
    cai.mount("https://", _Cai(erro))
    with C.origem("teste"), pytest.raises(requests.exceptions.ConnectTimeout) as subiu:
        cai.get(_API)
    assert subiu.value is erro
    assert _contas("teste", "work_orders")[:3] == (8, 2, 3)
    assert _contas("*", "*")[:3] == (8, 2, 3)                           # o total da hora soma tudo


# ── o pico por minuto ────────────────────────────────────────────────────────────────────────────────────────────────
def test_pico_por_minuto(relogio):
    s, _ = sessao_real(*[(200, None)] * 14)

    def pedir(utc, origem, vezes=1):
        relogio.em(utc)
        with C.origem(origem):
            for _ in range(vezes):
                s.get(_API)

    pedir("2026-10-30T13:00:05+00:00", "a", 3)       # minuto 13:00: a=3, total=3
    pedir("2026-10-30T13:01:50+00:00", "b", 3)       # minuto 13:01: b=3, total=3
    pedir("2026-10-30T13:02:10+00:00", "a")          # minuto 13:02: a=1, b=1, total=2
    pedir("2026-10-30T13:02:40+00:00", "b")
    pedir("2026-10-30T13:03:00+00:00", "b")          # minuto 13:03: b=1, total=1
    pedir("2026-10-30T13:04:00+00:00", "a", 2)       # minuto 13:04: a=2, b=2, total=4
    pedir("2026-10-30T13:04:59+00:00", "b", 2)
    assert _contas("a", "work_orders") == (6, 0, 0, 3)
    assert _contas("b", "work_orders") == (7, 0, 0, 3)
    # o pico do total NÃO é a soma dos picos (3 + 3): é o maior número de pedidos de todos juntos num mesmo minuto
    assert _contas("*", "*") == (13, 0, 0, 4)

    # na hora seguinte o pico recomeça: os minutos guardados são só os da hora corrente
    pedir("2026-10-30T14:00:00+00:00", "a")
    assert _contas("a", "work_orders", "2026103011") == (1, 0, 0, 1)
    assert _contas("*", "*", "2026103011") == (1, 0, 0, 1)
    assert _contas("*", "*") == (13, 0, 0, 4)                            # a hora de antes ficou como estava


# ── drenar ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_drenar_tira_so_as_horas_fechadas(relogio):
    s, _ = sessao_real(*[(200, None)] * 4)
    with C.origem("a"):
        for utc in ("2026-10-30T13:10:00+00:00", "2026-10-30T13:20:00+00:00",    # 10h
                    "2026-10-30T14:10:00+00:00",                                 # 11h
                    "2026-10-30T15:10:00+00:00"):                                # 12h
            relogio.em(utc)
            s.get(_API)

    antes = C.instantaneo()
    assert C.instantaneo() == antes                                      # olhar não tira nada (o Raio-X)
    assert [lin["hora_id"] for lin in antes] == ["2026103010"] * 2 + ["2026103011"] * 2 + ["2026103012"] * 2
    assert all(set(lin) == _COLUNAS for lin in antes)

    # a hora de `ate_hora_id` está aberta (é a de agora): saem só as anteriores a ela
    fechadas = C.drenar("2026103011")
    assert {lin["hora_id"] for lin in fechadas} == {"2026103010"}
    assert [(lin["origem"], lin["metodo"], lin["pedidos_qtd"]) for lin in fechadas] == [
        ("*", "*", 2), ("a", "work_orders", 2)]
    assert {lin["hora_id"] for lin in C.instantaneo()} == {"2026103011", "2026103012"}   # as outras seguem lá
    assert C.drenar("2026103011") == []                                  # o que saiu não sai duas vezes

    assert {lin["hora_id"] for lin in C.drenar("2026103012")} == {"2026103011"}
    assert {lin["hora_id"] for lin in C.instantaneo()} == {"2026103012"}     # a de agora segue aberta
    assert {lin["hora_id"] for lin in C.drenar("2026103013")} == {"2026103012"}
    assert C.instantaneo() == []


def test_resposta_que_volta_depois_da_hora_drenada_nao_recria_a_linha(relogio):
    # A gravação REGRAVA a linha da mesma chave (hora, origem, método): uma linha de 0 pedidos e 1 recusa, nascida de uma
    # resposta tardia depois da drenagem, apagaria a linha certa da hora no banco.
    ad = _Drena((429, None), ate="2026103011")
    s = requests.Session()
    s.trust_env = False
    s.mount("https://", ad)
    with C.origem("a"):
        assert s.get(_API).status_code == 429
    # o pedido já estava contado quando a drenagem passou no meio dele
    assert [(lin["origem"], lin["pedidos_qtd"]) for lin in ad.drenado] == [("*", 1), ("a", 1)]
    assert C.instantaneo() == []


# ── a hora de Brasília ───────────────────────────────────────────────────────────────────────────────────────────────
def test_hora_de_brasilia_perto_da_meia_noite_utc(relogio):
    relogio.em("2026-10-31T02:30:00+00:00")                              # ainda é 30/10 em Brasília: 23:30
    sessao_real((200, None))[0].get(_API)
    assert [lin["hora_id"] for lin in C.instantaneo()] == ["2026103023", "2026103023"]
    assert C.hora_id_de() == "2026103023"                                # sem argumento, o relógio de agora
    assert C.hora_id_de(_epoca("2026-10-31T02:59:59+00:00")) == "2026103023"
    assert C.hora_id_de(_epoca("2026-10-31T03:00:00+00:00")) == "2026103100"     # a meia-noite de Brasília é 03:00Z
    assert C.hora_id_de(_epoca("2027-01-01T02:59:59+00:00")) == "2026123123"     # e a virada do ano também
    assert C.hora_id_de(_epoca("2026-01-15T02:30:00+00:00")) == "2026011423"     # verão: fixo em UTC-3 desde 2019


# ── ligar ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_ligar_duas_vezes(relogio):
    ligado = requests.sessions.Session.send
    C.ligar()
    C.ligar()
    assert requests.sessions.Session.send is ligado                      # não embrulhou o embrulho
    s, _ = sessao_real((200, None))
    s.get(_API)
    assert _contas("*", "*")[0] == 1                                     # um pedido, uma conta (não duas)
    assert C.pedidos_desta_thread() == 1


# ── nunca derruba o pedido ───────────────────────────────────────────────────────────────────────────────────────────
def test_o_contador_nunca_derruba_o_pedido(relogio, monkeypatch, caplog):
    def quebra():
        raise RuntimeError("o relógio quebrou")

    monkeypatch.setattr(C, "_agora", quebra)
    caplog.set_level(logging.DEBUG, logger=C.log.name)
    s, ad = sessao_real((200, None))
    assert s.get(_API).status_code == 200                                # o pedido sai e a resposta volta
    assert len(ad.pedidos) == 1
    assert C.pedidos_desta_thread() == 0                                 # sem contar, e sem acusar pedido que não contou
    assert C.instantaneo() == []
    assert [r.levelno for r in caplog.records if r.name == C.log.name] == [logging.DEBUG]   # só o debug sabe


# ── o caminho de verdade do Nexus, redirecionamento e várias threads ─────────────────────────────────────────────────
def test_requests_direto_tambem_conta(relogio, monkeypatch):
    # O Nexus quase não monta `Session`: o OS Creator chama `requests.post(...)` e o leitor do Campo `requests.get(...)`,
    # cada um com a sessão descartável que o próprio requests abre. O gancho está na classe, então esses contam igual.
    mandou = []

    def adaptador_de_mentira(self, request, **kwargs):
        mandou.append(request.url)
        r = requests.Response()
        r.status_code, r.url, r.request, r._content = 200, request.url, request, b"{}"
        return r

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", adaptador_de_mentira)
    with C.origem("teste"):
        requests.post(_RPC, timeout=5, json=[{"id": "1", "jsonrpc": "2.0", "method": "tasks.x", "params": {}}])
        requests.get(_API, timeout=5)
        requests.request("POST", "https://app.fracttal.com/oauth/token", data={"grant_type": "client_credentials"},
                         timeout=5)
        requests.get("https://example.com/api/work_orders", timeout=5)
    assert len(mandou) == 4
    assert [(lin["origem"], lin["metodo"], lin["pedidos_qtd"]) for lin in C.instantaneo()] == [
        ("*", "*", 3), ("teste", "tasks.x", 1), ("teste", "token", 1), ("teste", "work_orders", 1)]


def test_redirecionamento_conta_cada_salto_uma_vez(relogio):
    # O requests refaz o pedido pelo MESMO `Session.send` a cada salto: dois pedidos de verdade. A resposta final (429) é
    # do 2º; a do 1º é a 302, que não é recusa nem erro. Contar a final nos dois dobraria a recusa.
    s, ad = sessao_real((302, "https://app.fracttal.com/api/items"), (429, None))
    with C.origem("teste"):
        assert s.get("https://app.fracttal.com/api/work_orders").status_code == 429
    assert len(ad.pedidos) == 2
    assert _contas("teste", "work_orders")[:3] == (1, 0, 0)
    assert _contas("teste", "items")[:3] == (1, 1, 0)
    assert _contas("*", "*")[:3] == (2, 1, 0)


def test_threads_juntas_nao_perdem_pedido(relogio, monkeypatch):
    # 400 cliques no mesmo minuto (o relógio está parado): o porteiro seguraria cada um depois do 150º por 2 s DE VERDADE
    # (100 s de teste). Aqui a prova é a conta com threads juntas; a do porteiro mora em tests/test_casca_porteiro.py
    monkeypatch.setattr(C, "TETO_POR_MINUTO", 10_000)
    threads, por_thread = 8, 50
    largada = threading.Barrier(threads)
    contaram = []

    def pedir():
        s, _ = sessao_real(*[(200, None)] * por_thread)
        with C.origem("/os/api/ativos"):
            largada.wait()
            for _ in range(por_thread):
                s.get(_API)
            contaram.append(C.pedidos_desta_thread())

    ts = [threading.Thread(target=pedir) for _ in range(threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert contaram == [por_thread] * threads                            # cada thread viu só os dela
    assert _contas("/os/api/ativos", "work_orders") == (threads * por_thread, 0, 0, threads * por_thread)
    assert _contas("*", "*")[0] == threads * por_thread


# ── o relógio deste arquivo e o porteiro (etapa 5) ───────────────────────────────────────────────────────────────────
def test_fundo_acima_de_90_no_minuto_parado_nao_trava(relogio):
    # O porteiro mora no mesmo gancho: com o relógio parado e a espera de verdade, o 91º de fundo no mesmo minuto esperaria
    # uma janela que nunca anda, e a suíte travaria. A espera deste relógio anda o relógio (como a do test_casca_porteiro):
    # o teste termina, e o que passa de 90 espera a vez dele no relógio falso
    s, _ = sessao_real(*[(200, None)] * 91)
    with C.origem("fundo:laco"):
        for _ in range(91):
            s.get(_API)
    assert _contas("fundo:laco", "work_orders")[0] == 91
    assert _linha("fundo:laco", "work_orders")["esperas_qtd"] == 1
