"""Uma leitura só por chave na memória do OS Creator (`os_web.rotas._memo`), mesmo com várias pessoas chegando juntas
(03/11/2026). O Raio-X do Nexus mostrou 828 pedidos ao Fracttal num minuto às 10h, contra a cota de 200 da empresa toda, e
o Acompanhamento de chamados com 1.851 pedidos em 49 cliques: o servidor reinicia a cada push na `main`, a memória volta
vazia, e cada pessoa que abria o quadro antes de a 1ª leitura terminar fazia a leitura inteira dela (o `_memo` só guardava
DEPOIS de ler). Agora quem chega com a leitura da mesma chave em curso espera por ela e leva o mesmo resultado; se ela
falha, ou não é guardada (`guardar`), lê por conta própria, como antes. Nenhum pedido vai à rede: as leituras são
funções de mentira."""
import sys
import threading
import time

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

from os_web import rotas  # noqa: E402

CHAVE = ("acomp", "TODOS")


@pytest.fixture(autouse=True)
def _memoria_limpa():
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
        rotas._EM_CURSO.clear()
    yield
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
        rotas._EM_CURSO.clear()


class _Leitor:
    """A leitura de mentira: conta as vezes, avisa que começou e só termina quando o teste solta."""

    def __init__(self, falha=False, valor="quadro"):
        self.vezes, self.falha, self.valor = 0, falha, valor
        self.comecou, self.solta = threading.Event(), threading.Event()

    def __call__(self):
        self.vezes += 1
        self.comecou.set()
        assert self.solta.wait(5)
        if self.falha:
            raise RuntimeError("o Fracttal caiu no meio")
        return {"valor": self.valor, "vez": self.vezes}


def _em_thread(f):
    caixa = {}

    def rodar():
        try:
            caixa["r"] = f()
        except Exception as e:                      # noqa: BLE001 — o teste confere a exceção
            caixa["erro"] = e
    t = threading.Thread(target=rodar)
    t.start()
    return t, caixa


def _esperando(n, chave=CHAVE):
    """Até `n` chamadas estarem paradas esperando a leitura em curso da chave (sem dormir às cegas)."""
    fim = time.monotonic() + 5
    while time.monotonic() < fim:
        with rotas._MEMO_LOCK:
            leitura = rotas._EM_CURSO.get(chave)
            if leitura is not None and leitura.esperando >= n:
                return
        time.sleep(0.01)
    raise AssertionError("ninguém ficou esperando a leitura em curso")


def test_quem_chega_com_a_leitura_em_curso_espera_e_leva_o_mesmo():
    leitor = _Leitor()
    t1, c1 = _em_thread(lambda: rotas._memo(CHAVE, 1800, leitor))
    assert leitor.comecou.wait(5)
    outros = [_em_thread(lambda: rotas._memo(CHAVE, 1800, leitor)) for _ in range(3)]
    _esperando(3)
    assert leitor.vezes == 1                        # ninguém mais foi ao Fracttal
    leitor.solta.set()
    for t, _c in [(t1, c1)] + outros:
        t.join(5)
        assert not t.is_alive()
    assert leitor.vezes == 1
    assert all(c["r"] is c1["r"] for _t, c in outros)
    assert rotas._memo(CHAVE, 1800, leitor) is c1["r"]   # e a memória guardou, como sempre
    assert not rotas._EM_CURSO


def test_a_leitura_que_falha_nao_serve_a_quem_esperou():
    """Quem esperou lê com a sessão dele: o erro de um (a sessão caída, o 429) não vira o erro de todos."""
    primeiro, segundo = _Leitor(falha=True), _Leitor(valor="do segundo")
    t1, c1 = _em_thread(lambda: rotas._memo(CHAVE, 1800, primeiro))
    assert primeiro.comecou.wait(5)
    t2, c2 = _em_thread(lambda: rotas._memo(CHAVE, 1800, segundo))
    _esperando(1)
    assert segundo.vezes == 0
    segundo.solta.set()
    primeiro.solta.set()
    t1.join(5)
    t2.join(5)
    assert isinstance(c1["erro"], RuntimeError)
    assert c2["r"]["valor"] == "do segundo" and segundo.vezes == 1
    assert not rotas._EM_CURSO


def test_a_leitura_que_nao_foi_guardada_nao_serve_a_quem_esperou():
    """O catálogo que veio vazio (a sessão de quem não tem a permissão no Fracttal) não é guardado (`guardar`, 20/10/2026),
    e também não vai para quem esperou: ele lê com a sessão dele."""
    vazio, cheio = _Leitor(valor=""), _Leitor(valor="cheio")
    guardar = lambda r: bool(r["valor"])            # noqa: E731
    t1, c1 = _em_thread(lambda: rotas._memo(CHAVE, 1800, vazio, guardar=guardar))
    assert vazio.comecou.wait(5)
    t2, c2 = _em_thread(lambda: rotas._memo(CHAVE, 1800, cheio, guardar=guardar))
    _esperando(1)
    cheio.solta.set()
    vazio.solta.set()
    t1.join(5)
    t2.join(5)
    assert c1["r"]["valor"] == "" and c2["r"]["valor"] == "cheio" and cheio.vezes == 1


def test_o_atualizar_le_mesmo_com_uma_leitura_em_curso():
    """O `forcar` (o Atualizar, a releitura por trás) lê na hora, como sempre."""
    leitor, forcado = _Leitor(), _Leitor(valor="forçado")
    forcado.solta.set()
    t1, _c1 = _em_thread(lambda: rotas._memo(CHAVE, 1800, leitor))
    assert leitor.comecou.wait(5)
    assert rotas._memo(CHAVE, 1800, forcado, forcar=True)["valor"] == "forçado"
    assert forcado.vezes == 1
    leitor.solta.set()
    t1.join(5)


def test_chaves_diferentes_nao_esperam_uma_pela_outra():
    a, b = _Leitor(valor="a"), _Leitor(valor="b")
    b.solta.set()
    t1, _c1 = _em_thread(lambda: rotas._memo(("acomp", "pessoa-a"), 1800, a))
    assert a.comecou.wait(5)
    assert rotas._memo(("acomp", "pessoa-b"), 1800, b)["valor"] == "b"
    a.solta.set()
    t1.join(5)
