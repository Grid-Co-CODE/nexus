"""O porteiro do Fracttal (31/10/2026, etapa 5 do canto central do OS Creator). A cota do Fracttal é de 200 pedidos por
minuto para a EMPRESA toda, dividida com o App de Campo e os robôs, e estourá-la derruba o App de Campo (o desenho do canto
central chama isso de fracasso, mesmo com tudo funcionando). O porteiro mora no mesmo gancho do contador da etapa 0
(`casca/fracttal_conta.py`, o `Session.send`) e põe todo pedido do Nexus ao Fracttal numa conta deslizante de 60 s: no
máximo 150 por minuto (sobram 50 para o App de Campo e os robôs), e o fundo no máximo 90 deles. Fundo é só a origem
DECLARADA `fundo:` (o laço do servidor que se declara); a thread sem declaração (o pool, a releitura por trás de uma tela)
é tratada como clique. Quem clica nunca é recusado: com o minuto cheio espera até 2 s e segue. O fundo espera a vez sem
limite, sem segurar a trava nem uma das 4 vagas do `campo/fracttal.py`, e cede a vez ao clique que espera.

Provas, sem rede (a `requests.Session` de verdade com um Fracttal de mentira) e com o relógio na mão: a espera do porteiro
anda o relógio em vez de dormir, então um minuto de espera leva um instante. Os testes com threads usam a espera de verdade
(a Condition) com o relógio de parede parado: a janela só anda quando o teste manda."""
import contextvars
import inspect
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pytest
import requests

from nexus.casca import fracttal_conta as C
from nexus.dados import fato_uso_os as F
from sessao_real_sem_rede import AdaptadorFalso

AQUI = Path(__file__).resolve().parent.parent
_API = "https://app.fracttal.com/api/work_orders?limit=100"
_RPC = "https://app.fracttal.com/rpc/proxy"
_HORA_10 = "2026103010"                 # 13:00Z de 30/10/2026 = 10:00 em Brasília (UTC-3)


def _epoca(utc: str) -> float:
    return datetime.fromisoformat(utc).timestamp()


class _Relogio:
    """O relógio na mão: a parede (a janela do porteiro e a hora da conta) e o cronômetro (o prazo de 2 s do clique) andam
    juntos, e a espera do porteiro anda os dois em vez de dormir, anotando quanto pediu."""

    def __init__(self, utc="2026-10-30T13:00:00+00:00"):
        self.t = _epoca(utc)
        self.mono = 5000.0
        self.esperas = []

    def agora(self) -> float:
        return self.t

    def cronometro(self) -> float:
        return self.mono

    def passa(self, segundos: float) -> None:
        self.t += segundos
        self.mono += segundos

    def em(self, utc: str) -> "_Relogio":
        self.t = _epoca(utc)
        return self

    def esperar(self, cond, segundos: float) -> None:
        self.esperas.append(segundos)
        self.passa(segundos)


class _Fracttal(AdaptadorFalso):
    """O Fracttal de mentira que anota, de cada pedido que chegou a ele, a hora (do relógio falso) e se era do fundo."""

    def __init__(self, relogio, n=500):
        super().__init__(*[(200, None)] * n)
        self.relogio, self.chegadas = relogio, []

    def send(self, request, **kwargs):
        self.chegadas.append((self.relogio.t, "quem=fundo" in request.url))
        return super().send(request, **kwargs)


def _sessao(adaptador) -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    s.mount("https://", adaptador)
    return s


def _pedir(s, origem: str, n: int = 1) -> None:
    """`n` pedidos ao REST do Fracttal com a origem dada; o endereço diz ao Fracttal de mentira se é do fundo."""
    quem = "fundo" if origem.startswith(C.FUNDO) else "clique"
    with C.origem(origem):
        for _ in range(n):
            assert s.get(f"{_API}&quem={quem}").status_code == 200


def _linha(origem, metodo="work_orders", hora=_HORA_10) -> dict:
    achadas = [lin for lin in C.instantaneo() if (lin["hora_id"], lin["origem"], lin["metodo"]) == (hora, origem, metodo)]
    assert len(achadas) == 1, f"{(hora, origem, metodo)} em {C.instantaneo()}"
    return achadas[0]


def _max_em_60s(tempos) -> int:
    """O maior número de pedidos que saíram em qualquer janela de 60 s (a do porteiro: os que saíram há menos de 60 s)."""
    tempos, maior, i = sorted(tempos), 0, 0
    for j, t in enumerate(tempos):
        while tempos[i] <= t - 60:
            i += 1
        maior = max(maior, j - i + 1)
    return maior


def _ate(condicao, prazo_s: float = 5.0) -> bool:
    fim = time.monotonic() + prazo_s
    while time.monotonic() < fim:
        if condicao():
            return True
        time.sleep(0.005)
    return condicao()


@pytest.fixture
def relogio(monkeypatch):
    """O gancho ligado e zerado, com o relógio na mão (10:00 de Brasília); o `Session.send` volta ao que era no fim."""
    monkeypatch.setattr(requests.sessions.Session, "send", requests.sessions.Session.send)
    C.limpar()
    r = _Relogio()
    monkeypatch.setattr(C, "_agora", r.agora)
    monkeypatch.setattr(C, "_cronometro", r.cronometro, raising=False)
    monkeypatch.setattr(C, "_esperar", r.esperar, raising=False)
    C.ligar()
    yield r
    C.limpar()


@pytest.fixture
def parado(monkeypatch):
    """O relógio de parede parado na mão (a janela só anda quando o teste manda) e a espera de verdade: quem espera a vez
    dorme na Condition do porteiro, sem a trava. No fim, o `limpar` solta quem tiver ficado esperando."""
    monkeypatch.setattr(requests.sessions.Session, "send", requests.sessions.Session.send)
    C.limpar()
    parede = [_epoca("2026-10-30T13:00:00+00:00")]
    monkeypatch.setattr(C, "_agora", lambda: parede[0])
    C.ligar()
    yield parede
    C.limpar()
    # o teste que falhou no meio não deixa ninguém esperando a vez para o seguinte (o fundo que cede a vaga ao clique
    # esperaria um clique que não é dele)
    assert _ate(lambda: C.estado()["esperando"] == {"clique": 0, "fundo": 0})


# ── os números ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_os_numeros_do_porteiro():
    # 150 dos 200 para o Nexus (sobram 50 para o App de Campo e os robôs), 90 deles para o fundo (os outros 60 são de quem
    # clica), 2 s de espera no máximo para o clique e a conta deslizante de 1 minuto, como a cota do Fracttal
    assert (C.COTA_POR_MINUTO, C.TETO_POR_MINUTO, C.TETO_FUNDO_POR_MINUTO) == (200, 150, 90)
    assert C.ESPERA_CLIQUE_MAX_S == 2 and C.JANELA_S == 60


# ── o fundo ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_fundo_espera_acima_de_90(relogio):
    f = _Fracttal(relogio)
    s = _sessao(f)
    t0 = relogio.t
    _pedir(s, "fundo:nexus-os-leitor:noite", 60)                # 60 de fundo agora
    relogio.passa(20)
    _pedir(s, "fundo:nexus-tarefas-os-banco", 30)               # mais 30: 90 de fundo no minuto, o teto do fundo
    assert relogio.esperas == []                                # até o 90º, ninguém esperou
    _pedir(s, "/os/historico", 5)                               # o clique não espera o fundo: o total (95) está longe dos 150
    assert relogio.esperas == [] and relogio.t == t0 + 20
    _pedir(s, "fundo:nexus-os-leitor:noite")                    # o 91º de fundo espera a vez...
    assert relogio.t - t0 == pytest.approx(60)                  # ... até os 60 de t0 saírem da janela, nem um segundo a mais
    assert len(f.chegadas) == 96 and f.chegadas[-1][1] is True and f.chegadas[-1][0] - t0 == pytest.approx(60)
    assert _linha("fundo:nexus-os-leitor:noite")["esperas_qtd"] == 1
    assert _linha("fundo:nexus-tarefas-os-banco")["esperas_qtd"] == 0 and _linha("/os/historico")["esperas_qtd"] == 0
    # o fundo que segue pedindo anda no ritmo do teto dele: nunca mais de 90 de fundo em 60 s
    _pedir(s, "fundo:nexus-tarefas-os-banco", 100)
    assert len(f.chegadas) == 196
    assert _max_em_60s([t for t, fundo in f.chegadas if fundo]) == C.TETO_FUNDO_POR_MINUTO
    assert relogio.t - t0 == pytest.approx(120)                 # 59 entraram aos 60 s, 30 aos 80 s e os 11 últimos aos 120 s
    # a janela guarda só o último minuto (os 30 dos 80 s e os 11 dos 120 s): a memória não cresce com as horas de fundo
    assert C.estado()["ultimo_minuto"] == {"todos": 41, "fundo": 41}


# ── o clique ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_clique_nunca_recusado(relogio):
    f = _Fracttal(relogio)
    s = _sessao(f)
    _pedir(s, "fundo:laco", 90)
    _pedir(s, "/os/historico", 60)                              # 150 no minuto: o teto do Nexus
    assert relogio.esperas == []
    # com o minuto cheio, cada clique espera os seus 2 s e sai: nenhum é recusado e nenhum espera mais do que isso. A tela
    # que se renova sozinha (a sessão de 5 em 5 min, com o `X-Nexus-Auto`) também é clique: é uma rota, não `fundo:`
    for rota in ("/os/os/<n>", "/os/os/<n>", "/os/_nexus/sessao", "/t/campo/aprovacao"):
        antes = relogio.t
        with C.origem(rota):
            assert s.get(_API).status_code == 200
        assert relogio.t - antes == pytest.approx(C.ESPERA_CLIQUE_MAX_S)
    assert len(f.chegadas) == 154                               # todos chegaram ao Fracttal
    assert max(relogio.esperas) <= C.ESPERA_CLIQUE_MAX_S
    assert _linha("/os/os/<n>")["esperas_qtd"] == 2 and _linha("/os/_nexus/sessao")["esperas_qtd"] == 1
    assert _linha("/t/campo/aprovacao")["esperas_qtd"] == 1 and _linha("/os/historico")["esperas_qtd"] == 0


# ── o teto do Nexus ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_teto_de_150(relogio):
    f = _Fracttal(relogio)
    s = _sessao(f)
    t0 = relogio.t
    _pedir(s, "/os/historico", 120)                             # uma rajada de 120 cliques num instante
    _pedir(s, "fundo:laco", 30)                                 # e o fundo, longe dos 90, completa os 150
    assert relogio.esperas == []
    _pedir(s, "fundo:laco")                                     # o 31º de fundo: vaga no fundo (30 de 90), nenhuma no Nexus
    assert relogio.t - t0 == pytest.approx(60)                  # espera os 150 de t0 saírem da janela
    _pedir(s, "fundo:laco", 200)                                # o fundo que segue pedindo, sozinho, anda a 90 por minuto
    assert len(f.chegadas) == 351
    assert _max_em_60s([t for t, _fundo in f.chegadas]) == C.TETO_POR_MINUTO      # o Nexus nunca passou de 150 em 60 s
    assert _max_em_60s([t for t, fundo in f.chegadas if fundo]) == C.TETO_FUNDO_POR_MINUTO


# ── as esperas ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_esperas_contadas(relogio):
    s = _sessao(_Fracttal(relogio))
    relogio.em("2026-10-30T13:59:30+00:00")                     # 10:59:30 de Brasília
    _pedir(s, "fundo:laco-a", 90)
    _pedir(s, "/os/historico", 60)                              # 150 na janela
    _pedir(s, "/os/os/<n>", 2)                                  # dois cliques esperam 2 s cada e saem (10:59:34)
    with C.origem("fundo:laco-b"):                              # o fundo espera os 150 saírem: às 11:00:30
        assert s.post(_RPC, json=[{"id": "1", "jsonrpc": "2.0", "method": "tasks.x", "params": {}}]).status_code == 200
    # quem esperou conta na linha dele (hora × quem × método), na hora em que SAIU, junto com o pedido
    assert (_linha("/os/os/<n>")["pedidos_qtd"], _linha("/os/os/<n>")["esperas_qtd"]) == (2, 2)
    fundo_b = _linha("fundo:laco-b", "tasks.x", "2026103011")
    assert (fundo_b["pedidos_qtd"], fundo_b["esperas_qtd"]) == (1, 1)
    assert _linha("fundo:laco-a")["esperas_qtd"] == 0 and _linha("/os/historico")["esperas_qtd"] == 0
    # a linha do total de cada hora soma as esperas de todas as origens
    assert _linha("*", "*")["esperas_qtd"] == 2 and _linha("*", "*", "2026103011")["esperas_qtd"] == 1
    assert _linha("*", "*")["pedidos_qtd"] == 152 and _linha("*", "*")["pico_minuto_qtd"] == 152
    # o estado: as esperas de cada hora, de clique e de fundo
    e = C.estado()
    assert e["esperas_por_hora"] == [{"hora_id": "2026103010", "clique": 2, "fundo": 0},
                                     {"hora_id": "2026103011", "clique": 0, "fundo": 1}]
    assert e["esperando"] == {"clique": 0, "fundo": 0}
    # o que vai ao banco: o drenar entrega a coluna, com a forma do fato, e o total da hora a leva à aba dele
    fechadas = C.drenar("2026103011")
    assert fechadas and all(F.valida(lin, F.ABA_FRACTTAL) for lin in fechadas)
    assert {lin["origem"]: lin["esperas_qtd"] for lin in fechadas} == {"*": 2, "/os/os/<n>": 2, "/os/historico": 0,
                                                                        "fundo:laco-a": 0}
    assert F.separar_total(fechadas)[1][0]["esperas_qtd"] == 2
    assert C.estado()["esperas_por_hora"] == [{"hora_id": "2026103011", "clique": 0, "fundo": 1}]


# ── as threads: ninguém dorme segurando a trava ──────────────────────────────────────────────────────────────────────
def test_fundo_esperando_nao_segura_o_clique(parado):
    s = _sessao(AdaptadorFalso(*[(200, None)] * 100))
    _pedir(s, "fundo:laco", 90)                                 # o fundo cheio: 90 no minuto
    saiu = threading.Event()

    def leitor():
        with C.origem("fundo:nexus-os-leitor:noite"):
            assert _sessao(AdaptadorFalso((200, None))).get(_API).status_code == 200
        saiu.set()

    t = threading.Thread(target=lambda: contextvars.Context().run(leitor), name="nexus-os-leitor", daemon=True)
    t.start()
    assert _ate(lambda: C.estado()["esperando"]["fundo"] == 1)  # o leitor esperando a vez, dormindo na Condition
    comeco = time.monotonic()
    with C.origem("/os/historico"):
        assert s.get(_API).status_code == 200                   # o clique passa na hora: o total (90) está longe dos 150
    assert time.monotonic() - comeco < 0.5                      # nem a trava nem a vez do fundo o seguraram
    assert not saiu.is_set() and C.estado()["esperando"] == {"clique": 0, "fundo": 1}
    parado[0] += 60                                             # o minuto andou: os 90 de fundo saem da janela
    assert saiu.wait(5)                                         # quem espera confere de novo a cada segundo, no máximo
    t.join(5)
    assert _linha("fundo:nexus-os-leitor:noite")["esperas_qtd"] == 1 and _linha("/os/historico")["esperas_qtd"] == 0


def test_clique_esperando_tem_a_vez_antes_do_fundo(parado, monkeypatch):
    s = _sessao(AdaptadorFalso(*[(200, None)] * 200))
    t0 = parado[0]
    parado[0] = t0 - 30
    _pedir(s, "/os/historico")                                  # 1 clique há 30 s
    parado[0] = t0
    _pedir(s, "/os/historico", 149)                             # e 149 agora: os 150 do teto
    # o fundo confere a vez de 5 em 5 ms; o clique, de 300 em 300: sem a regra, o fundo pegaria a vaga primeiro
    def esperar(cond, segundos):
        cond.wait(min(segundos, 0.005 if threading.current_thread().name == "fundo-teste" else 0.3))
    monkeypatch.setattr(C, "_esperar", esperar)
    fundo_saiu, clique_saiu = threading.Event(), threading.Event()

    def pedir(origem, saiu):
        with C.origem(origem):
            _sessao(AdaptadorFalso((200, None))).get(_API)
        saiu.set()

    tf = threading.Thread(target=lambda: contextvars.Context().run(pedir, "fundo:laco", fundo_saiu), name="fundo-teste",
                          daemon=True)
    tk = threading.Thread(target=lambda: contextvars.Context().run(pedir, "/os/os/<n>", clique_saiu), name="clique-teste",
                          daemon=True)
    tf.start()
    assert _ate(lambda: C.estado()["esperando"]["fundo"] == 1)
    tk.start()
    assert _ate(lambda: C.estado()["esperando"]["clique"] == 1)
    parado[0] = t0 + 31                                         # o clique de há 30 s sai da janela: UMA vaga
    assert clique_saiu.wait(1.5)                                # o clique a pegou, antes do prazo de 2 s dele
    assert not fundo_saiu.is_set()                              # o fundo cedeu a vez e segue esperando (de novo 150)
    assert C.estado()["ultimo_minuto"]["todos"] == C.TETO_POR_MINUTO
    parado[0] = t0 + 61                                         # os 149 de t0 saem: o fundo passa
    assert fundo_saiu.wait(5)
    tf.join(5)
    tk.join(5)
    assert _linha("/os/os/<n>")["esperas_qtd"] == 1 and _linha("fundo:laco")["esperas_qtd"] == 1


# ── só o Fracttal passa pelo porteiro ────────────────────────────────────────────────────────────────────────────────
def test_outro_dominio_nao_passa_pelo_porteiro(relogio):
    ad = AdaptadorFalso(*[(200, None)] * 200)
    s = _sessao(ad)
    _pedir(s, "fundo:laco", 90)
    _pedir(s, "/os/historico", 60)                              # o Fracttal no teto: 150 no minuto, 90 de fundo
    t, n = relogio.t, len(ad.pedidos)
    fora = ("https://example.com/api/work_orders", "https://notfracttal.com/api/work_orders",
            "https://app.fracttal.com.example.org/api/work_orders",
            "https://bucket.s3.amazonaws.com/fracttal.com/foto.png?x=app.fracttal.com",
            "https://api.banco.exemplo.invalid/api/sheets")
    for origem in ("fundo:laco", "/os/historico"):
        with C.origem(origem):
            for url in fora:
                assert s.get(url).status_code == 200
    assert len(ad.pedidos) == n + 2 * len(fora)
    assert relogio.t == t and relogio.esperas == []             # ninguém esperou: o relógio nem andou
    assert C.estado()["ultimo_minuto"] == {"todos": 150, "fundo": 90}      # e a janela não os contou


# ── o porteiro nunca derruba o pedido ────────────────────────────────────────────────────────────────────────────────
def test_porteiro_quebrado_nao_segura_o_pedido(relogio, monkeypatch, caplog):
    f = _Fracttal(relogio)
    s = _sessao(f)
    _pedir(s, "fundo:laco", 90)

    def quebra(cond, segundos):
        raise RuntimeError("a espera quebrou")

    monkeypatch.setattr(C, "_esperar", quebra)
    caplog.set_level(logging.DEBUG, logger=C.log.name)
    with C.origem("fundo:laco"):
        assert s.get(_API).status_code == 200                   # o pedido sai como sairia sem o porteiro
    assert len(f.chegadas) == 91
    assert _linha("fundo:laco")["pedidos_qtd"] == 90            # sem a conta (só o debug sabe), como no contador
    assert C.estado()["esperando"] == {"clique": 0, "fundo": 0}  # quem saiu pela exceção não ficou "esperando"
    assert [r.levelno for r in caplog.records if r.name == C.log.name] == [logging.DEBUG]


# ── só a origem DECLARADA é fundo (rodada de correção da 5.2) ─────────────────────────────────────────────────────────
# A tarefa de um pool comum e a thread aberta à mão começam sem a marca de quem as abriu: o contador lhes dá o nome da thread
# (`fundo:ThreadPoolExecutor`, `fundo:os-web-preparo`), e a 1ª versão do porteiro (antes de ir ao ar) as tratava como fundo,
# que espera a vez sem limite: o clique da Aprovação esperaria as páginas do pool, e o card do OS Creator, o detalhe lido
# por trás. Agora só é fundo quem se declara (`origem` ou `de_fundo`); o nome que vai ao fato não muda.
def test_thread_sem_declaracao_e_clique_no_porteiro(relogio):
    s = _sessao(_Fracttal(relogio))
    _pedir(s, "fundo:laco", 90)                                 # o fundo cheio

    def pedir(_):
        return _sessao(AdaptadorFalso((200, None))).get(_API).status_code       # sem origem: a marca é inferida
    with ThreadPoolExecutor(max_workers=2) as ex:
        assert list(ex.map(pedir, range(4))) == [200] * 4
    assert relogio.esperas == []                                # com o fundo em 90, o pool passou na hora: é clique
    lin = _linha("fundo:ThreadPoolExecutor")                    # e o nome no fato é o de sempre
    assert (lin["pedidos_qtd"], lin["esperas_qtd"]) == (4, 0)
    # com o minuto cheio (150), espera como o clique espera: no máximo 2 s, e segue
    _pedir(s, "/os/historico", 56)
    antes = relogio.t
    with ThreadPoolExecutor(max_workers=1) as ex:
        assert ex.submit(pedir, 0).result() == 200
    assert relogio.t - antes == pytest.approx(C.ESPERA_CLIQUE_MAX_S)
    assert _linha("fundo:ThreadPoolExecutor")["esperas_qtd"] == 1
    assert C.estado()["esperas_por_hora"] == [{"hora_id": _HORA_10, "clique": 1, "fundo": 0}]   # o estado diz clique


def test_de_fundo_declara_a_origem_e_nao_vaza(relogio):
    s = _sessao(_Fracttal(relogio))
    _pedir(s, "fundo:laco", 90)
    t0 = relogio.t

    def ler():
        assert s.get(_API).status_code == 200
        return C.pedidos_desta_thread()
    assert C.de_fundo("fundo:nexus-teste-laco", ler)() == 1     # o alvo da thread do laço, declarado: é fundo
    assert relogio.t - t0 == pytest.approx(60)                  # e esperou a vez do fundo (os 90 saírem da janela)
    lin = _linha("fundo:nexus-teste-laco")
    assert (lin["pedidos_qtd"], lin["esperas_qtd"]) == (1, 1)
    # fora do embrulho a declaração não ficou na thread: o pedido sem origem volta a ser inferido (clique)
    _pedir(s, "fundo:laco", 89)                                 # o fundo cheio de novo (89 + o do laço)
    t1 = relogio.t
    assert s.get(_API).status_code == 200
    assert relogio.t == t1
    with pytest.raises(ValueError):
        C.de_fundo("/os/historico", ler)                        # só se declara fundo com um nome de fundo


# Os laços do servidor que pedem ao Fracttal e até aqui só caíam na marca inferida: declaram o fundo no alvo da thread deles
# (não dentro da função, que um clique também chama na hora, como o `pedir_releitura(esperar=True)` da Engenharia), com o
# nome que o fato já mostrava (o da thread, sem contador). (arquivo, thread, quantas vezes a thread é aberta ali)
LACOS = [
    ("nexus/campo/tarefas_os.py", "nexus-tarefas-os-banco", 1),
    ("nexus/campo/chamados_acompanhamento.py", "nexus-chamados-banco", 1),
    ("nexus/campo/aprovacao.py", "nexus-fila-fracttal", 2),
    ("nexus/campo/ronda_checklist.py", "nexus-ronda-checklist", 1),
    ("nexus/engenharia/os_falhas.py", "nexus-os-falhas", 1),
    ("nexus/engenharia/os_equipe.py", "nexus-os-equipe", 1),
    ("nexus/engenharia/etm.py", "nexus-etm", 1),
    ("nexus/torres/oscreator/os_creator/ativos_leitor.py", "nexus-ativos-leitor", 1),
]


@pytest.mark.parametrize("arquivo, thread, vezes", LACOS)
def test_lacos_do_servidor_declaram_o_fundo(arquivo, thread, vezes):
    texto = (AQUI / arquivo).read_text(encoding="utf-8")
    assert texto.count(f'de_fundo("fundo:{thread}", ') == vezes, arquivo
    assert C._nome_de_fundo(thread) == thread                   # o mesmo nome que o fato já mostrava


def test_quem_um_clique_chama_na_hora_nao_se_declara_fundo():
    # a releitura da Engenharia roda na thread do clique com `esperar=True`, e os `em_segundo_plano` do Campo também abrem
    # as fotos da ronda (que a pessoa espera): declarar ali faria o clique esperar como fundo
    from nexus.campo import aprovacao, ronda_checklist
    from nexus.engenharia import etm, os_equipe, os_falhas
    for f in (os_equipe._reler, etm._reler, os_falhas._reler, aprovacao.em_segundo_plano, ronda_checklist.em_segundo_plano):
        fonte = inspect.getsource(f)
        assert "de_fundo" not in fonte and "origem(" not in fonte, f.__qualname__


# ── as 4 vagas do campo/fracttal.py: o fundo espera a vez ANTES de pegar uma ─────────────────────────────────────────
@pytest.fixture
def campo_fracttal(monkeypatch):
    """O `campo/fracttal.py` de verdade com o Fracttal de mentira no adaptador do requests (ele chama `requests.get`), o
    token já na mão, vagas novas e sem o ritmo de 4 por segundo (não é ele que se prova aqui)."""
    from nexus.campo import fracttal as FX

    def adaptador(self, request, **kwargs):
        r = requests.Response()
        r.status_code, r.url, r.request, r._content = 200, request.url, request, b"{}"
        r.headers["Content-Type"] = "application/json"
        return r
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", adaptador)
    monkeypatch.setattr(FX, "_FORNECEDOR", None)
    monkeypatch.setattr(FX, "_TOKEN", {"v": "token-de-teste", "exp": time.time() + 3600})
    monkeypatch.setattr(FX, "_VAGAS", threading.BoundedSemaphore(FX.SIMULTANEOS))
    monkeypatch.setattr(FX, "_ULTIMO", [0.0])
    monkeypatch.setattr(FX, "INTERVALO_S", 0.0)
    return FX


def test_fundo_parado_no_porteiro_nao_segura_as_vagas_do_campo(parado, campo_fracttal):
    FX = campo_fracttal
    s = _sessao(AdaptadorFalso(*[(200, None)] * 100))
    _pedir(s, "fundo:laco", 90)                                 # o fundo cheio
    saidas, threads = [], []

    def pedir(origem, saiu):
        with C.origem(origem):
            FX.ler("work_orders?limit=1")
        saiu.set()

    def abrir(origem, nome):
        saiu = threading.Event()
        t = threading.Thread(target=lambda: contextvars.Context().run(pedir, origem, saiu), name=nome, daemon=True)
        t.start()
        saidas.append(saiu)
        threads.append(t)
        return saiu
    try:
        for i in range(FX.SIMULTANEOS):                         # 4 leitores de fundo parados no porteiro
            abrir(f"fundo:laco-{i}", f"fundo-{i}")
        assert _ate(lambda: C.estado()["esperando"]["fundo"] == FX.SIMULTANEOS)
        comeco = time.monotonic()
        clique = abrir("/t/campo/aprovacao", "clique")          # o clique pelo campo/fracttal.py: as vagas estão livres
        assert clique.wait(C.ESPERA_CLIQUE_MAX_S)
        assert time.monotonic() - comeco < C.ESPERA_CLIQUE_MAX_S
        assert not any(e.is_set() for e in saidas[:FX.SIMULTANEOS])      # e os 4 seguem esperando a vez deles
        parado[0] += 61                                         # o minuto andou: os 4 passam
        assert all(e.wait(5) for e in saidas)
        # a reserva já contou cada um na janela: o envio dentro dela não conta de novo (4, não 8)
        assert C.estado()["ultimo_minuto"] == {"todos": 4, "fundo": 4}
    finally:
        if not all(e.is_set() for e in saidas):
            parado[0] += 61                                     # o teste que falhou no meio solta quem ficou esperando
        for t in threads:
            t.join(5)
    for i in range(FX.SIMULTANEOS):
        lin = _linha(f"fundo:laco-{i}", "work_orders")
        assert (lin["pedidos_qtd"], lin["esperas_qtd"]) == (1, 1)            # contado uma vez, com a espera
    assert _linha("/t/campo/aprovacao", "work_orders")["esperas_qtd"] == 0


def test_reserva_so_vale_para_o_fundo_declarado_com_o_gancho(relogio, monkeypatch):
    s = _sessao(_Fracttal(relogio))
    # o clique e a thread sem declaração não reservam nada: passam direto (o clique espera no máximo 2 s lá dentro)
    for origem in ("/t/campo/aprovacao", ""):
        with C.origem(origem), C.reservar_vez():
            pass
    assert C.estado()["ultimo_minuto"] == {"todos": 0, "fundo": 0} and relogio.esperas == []
    # o fundo declarado reserva: conta na janela já na reserva, e o 1º pedido dentro dela não conta de novo
    with C.origem("fundo:laco"), C.reservar_vez():
        assert C.estado()["ultimo_minuto"] == {"todos": 1, "fundo": 1}
        assert s.get(_API).status_code == 200
        assert C.estado()["ultimo_minuto"] == {"todos": 1, "fundo": 1}
        assert s.get(_API).status_code == 200                   # o 2º pedido do bloco já não tem reserva: conta
    assert C.estado()["ultimo_minuto"] == {"todos": 2, "fundo": 2}
    assert _linha("fundo:laco")["pedidos_qtd"] == 2
    # a reserva que sobrou (o pedido nem saiu) morre no fim do bloco: o pedido seguinte espera e conta como sempre
    with C.origem("fundo:laco"):
        with C.reservar_vez():
            pass
        assert s.get(_API).status_code == 200
    assert C.estado()["ultimo_minuto"] == {"todos": 4, "fundo": 4}
    # sem o gancho (o PC, os testes): a reserva não espera nem conta, nem com o fundo cheio
    _pedir(s, "fundo:laco", 86)                                 # 90 de fundo
    monkeypatch.setattr(requests.sessions.Session, "send", requests.sessions.Session.send.__wrapped__)
    with C.origem("fundo:laco"), C.reservar_vez():
        pass
    assert relogio.esperas == [] and C.estado()["ultimo_minuto"] == {"todos": 90, "fundo": 90}
