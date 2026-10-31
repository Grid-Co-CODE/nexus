"""O porteiro do Fracttal (31/10/2026, etapa 5 do canto central do OS Creator). A cota do Fracttal é de 200 pedidos por
minuto para a EMPRESA toda, dividida com o App de Campo e os robôs, e estourá-la derruba o App de Campo (o desenho do canto
central chama isso de fracasso, mesmo com tudo funcionando). O porteiro mora no mesmo gancho do contador da etapa 0
(`casca/fracttal_conta.py`, o `Session.send`) e põe todo pedido do Nexus ao Fracttal numa conta deslizante de 60 s: no
máximo 150 por minuto (sobram 50 para o App de Campo e os robôs), e o fundo (origem `fundo:`, os laços) no máximo 90 deles.
Quem clica nunca é recusado: com o minuto cheio espera até 2 s e segue. O fundo espera a vez sem limite, sem segurar a
trava, e cede a vez ao clique que espera.

Provas, sem rede (a `requests.Session` de verdade com um Fracttal de mentira) e com o relógio na mão: a espera do porteiro
anda o relógio em vez de dormir, então um minuto de espera leva um instante. Os dois testes com threads usam a espera de
verdade (a Condition) com o relógio de parede parado: a janela só anda quando o teste manda."""
import contextvars
import logging
import threading
import time
from datetime import datetime

import pytest
import requests

from nexus.casca import fracttal_conta as C
from nexus.dados import fato_uso_os as F
from sessao_real_sem_rede import AdaptadorFalso

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
