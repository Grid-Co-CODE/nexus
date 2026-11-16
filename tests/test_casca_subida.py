"""A fila de subida: as tarefas de aquecimento do boot, uma depois da outra (16/11/2026, Levi: "pode seguir com a fila
de subida").

O caso: com o processador por thread no Raio-X (o reinício das 17:47 de 16/11/2026), a leitura dos primeiros minutos não
achou um culpado: eram umas dez tarefas de subida juntas, cada uma com 10 a 40% de um núcleo (a releitura da fila da
Aprovação 37 a 39%, a conta dela 23%, a pré-carga até 21%, os chamados 17%, o pré-filtro 14% mais quatro threads). O
Nexus roda uma conta Python por vez: com N tarefas disputando, o clique da pessoa fica com 1/(N+1) do processador, e o
Raio-X, que abre em 1 s, levava de 8 a 42 s depois de cada deploy.

Aqui: a fila em si (`nexus/casca/subida.py`), com threads de verdade e esperas curtas, e os pontos em que as tarefas de
subida entram nela."""
import inspect
import threading
import time

import pytest

from nexus.casca import subida as S


@pytest.fixture(autouse=True)
def limpa():
    S.desligar()
    yield
    S.desligar()


class Tarefa:
    """Uma tarefa de subida de mentira: entra na vez, avisa, e fica até mandarem sair."""

    def __init__(self, nome, registro, erro=None):
        self.nome, self.registro, self.erro = nome, registro, erro
        self.dentro, self.sair = threading.Event(), threading.Event()
        self.fio = threading.Thread(target=self._rodar, daemon=True)

    def _rodar(self):
        try:
            with S.vez(self.nome):
                self.registro.append(self.nome)
                self.dentro.set()
                assert self.sair.wait(20)
                if self.erro:
                    raise self.erro
        except RuntimeError:
            pass

    def comecar(self):
        self.fio.start()
        return self

    def acabar(self):
        self.sair.set()
        self.fio.join(10)


def _na_fila(n, prazo=5.0):
    """Espera `n` tarefas estarem esperando a vez."""
    fim = time.monotonic() + prazo
    while time.monotonic() < fim:
        if len(S.estado()["fila"]) == n:
            return True
        time.sleep(0.01)
    return False


def test_sem_ligar_ninguem_espera():
    """O `create_app` e os testes não ligam a fila: as tarefas rodam juntas, como sempre."""
    ordem = []
    a, b = Tarefa("a", ordem).comecar(), Tarefa("b", ordem).comecar()
    assert a.dentro.wait(5) and b.dentro.wait(5)            # as duas dentro ao mesmo tempo
    assert S.estado() == {"ligada": False, "ativa": False, "ha_s": None, "dono": None, "fila": [], "feitas": []}
    assert S.esperar_calma(5) is False
    a.acabar(), b.acabar()


def test_uma_por_vez_na_ordem_de_chegada():
    S.ligar()
    ordem = []
    a = Tarefa("campo", ordem).comecar()
    assert a.dentro.wait(5)
    b = Tarefa("fila", ordem).comecar()
    assert _na_fila(1)
    c = Tarefa("sso", ordem).comecar()
    assert _na_fila(2)
    e = S.estado()
    assert e["ativa"] and e["dono"]["nome"] == "campo" and e["fila"] == ["fila", "sso"]
    assert not b.dentro.is_set() and not c.dentro.is_set()   # só a primeira roda
    a.acabar()
    assert b.dentro.wait(5) and not c.dentro.wait(0.3)       # a segunda entra; a terceira ainda não
    assert S.estado()["dono"]["nome"] == "fila"
    b.acabar()
    assert c.dentro.wait(5)
    c.acabar()
    assert ordem == ["campo", "fila", "sso"]
    feitas = S.estado()["feitas"]
    assert [f["nome"] for f in feitas] == ["campo", "fila", "sso"] and S.estado()["dono"] is None
    assert all(set(f) == {"nome", "esperou_s", "levou_s"} for f in feitas)


def test_a_tarefa_lenta_nao_segura_as_outras_para_sempre(monkeypatch):
    """A que passa do prazo com a vez (esperando a rede) deixa a seguinte entrar, e termina por fora."""
    monkeypatch.setattr(S, "PRAZO_S", 0.3)
    monkeypatch.setattr(S, "PASSO_S", 0.05)
    S.ligar()
    ordem = []
    lenta = Tarefa("releitura", ordem).comecar()
    assert lenta.dentro.wait(5)
    b = Tarefa("conta", ordem).comecar()
    c = Tarefa("sso", ordem).comecar()
    assert not b.dentro.wait(0.1)                            # dentro do prazo, espera
    assert b.dentro.wait(5)                                  # passou do prazo: entra, com a lenta ainda rodando
    assert not lenta.sair.is_set() and S.estado()["dono"]["nome"] == "conta"
    # a lenta termina: a vez segue com quem a tem agora, e a terceira continua esperando por ESSA
    monkeypatch.setattr(S, "PRAZO_S", 60)
    lenta.acabar()
    assert S.estado()["dono"]["nome"] == "conta" and not c.dentro.wait(0.3)
    b.acabar()
    assert c.dentro.wait(5)
    c.acabar()
    assert ordem == ["releitura", "conta", "sso"]


def test_a_tarefa_que_quebra_passa_a_vez():
    S.ligar()
    ordem = []
    a = Tarefa("quebra", ordem, erro=RuntimeError("de mentira")).comecar()
    assert a.dentro.wait(5)
    b = Tarefa("seguinte", ordem).comecar()
    assert _na_fila(1)
    a.acabar()
    assert b.dentro.wait(5)
    b.acabar()
    assert S.estado()["dono"] is None and [f["nome"] for f in S.estado()["feitas"]] == ["quebra", "seguinte"]


def test_quem_ja_tem_a_vez_nao_espera_de_novo():
    S.ligar()
    passos = []
    with S.vez("de fora"):
        with S.vez("de dentro"):                             # a tarefa que chama outra que também pede a vez
            passos.append("dentro")
        assert S.esperar_calma(5) is False                   # e quem tem a vez não espera a calma dela mesma
        passos.append("fora")
    assert passos == ["dentro", "fora"] and [f["nome"] for f in S.estado()["feitas"]] == ["de fora"]


def test_depois_da_janela_a_fila_nao_vale(monkeypatch):
    agora = [1000.0]
    monkeypatch.setattr(S, "_RELOGIO", lambda: agora[0])
    S.ligar()
    assert S.ativa()
    agora[0] += S.JANELA_S - 1
    assert S.ativa()
    agora[0] += 1
    assert not S.ativa()
    ordem = []
    a, b = Tarefa("a", ordem).comecar(), Tarefa("b", ordem).comecar()
    assert a.dentro.wait(5) and b.dentro.wait(5)             # juntas, como antes
    assert S.esperar_calma(5) is False
    a.acabar(), b.acabar()


def test_quem_esperava_quando_a_janela_acabou_segue(monkeypatch):
    monkeypatch.setattr(S, "PASSO_S", 0.05)
    monkeypatch.setattr(S, "PRAZO_S", 10 ** 6)               # só o fim da janela pode soltar quem espera
    agora = [1000.0]
    monkeypatch.setattr(S, "_RELOGIO", lambda: agora[0])
    S.ligar()
    ordem = []
    a = Tarefa("a", ordem).comecar()
    assert a.dentro.wait(5)
    b = Tarefa("b", ordem).comecar()
    assert _na_fila(1) and not b.dentro.wait(0.2)
    agora[0] += S.JANELA_S                                   # a janela acabou com a primeira ainda rodando
    assert b.dentro.wait(5)                                  # a que esperava segue, sem tirar a vez de ninguém
    assert S.estado()["fila"] == [] and S.estado()["dono"]["nome"] == "a"
    a.acabar(), b.acabar()


def test_esperar_calma_espera_o_sossego_e_a_fila_esvaziar(monkeypatch):
    monkeypatch.setattr(S, "PASSO_S", 0.05)
    agora = [1000.0]
    monkeypatch.setattr(S, "_RELOGIO", lambda: agora[0])
    S.ligar()
    saiu = threading.Event()
    fio = threading.Thread(target=lambda: (S.esperar_calma(), saiu.set()), daemon=True)
    fio.start()
    assert not saiu.wait(0.3)                                # o boot acabou de acontecer: nem com a fila vazia
    agora[0] += S.SOSSEGO_S - 10
    assert not saiu.wait(0.3)                                # ainda dentro do sossego
    ordem = []
    a = Tarefa("campo", ordem).comecar()
    assert a.dentro.wait(5)
    agora[0] += 20                                           # passou o sossego, mas há tarefa com a vez (há 20 s)
    assert not saiu.wait(0.3)
    a.acabar()
    assert saiu.wait(5)                                      # fila vazia e sossego passado: segue
    fio.join(5)
    assert S.esperar_calma(5) is False                       # já está calma: não espera


def test_esperar_calma_tem_teto(monkeypatch):
    monkeypatch.setattr(S, "PASSO_S", 0.05)
    monkeypatch.setattr(S, "JANELA_S", 4)
    S.ligar()
    with S.vez("uma tarefa"):                                # quem saiu da vez volta a esperar como os outros
        pass
    t0 = time.monotonic()
    assert S.esperar_calma(0.3) is True                      # esperou, e saiu no teto (o sossego é de 5 min)
    assert 0.25 <= time.monotonic() - t0 < 3


def test_a_tarefa_lenta_fora_do_prazo_nao_segura_a_calma(monkeypatch):
    monkeypatch.setattr(S, "PASSO_S", 0.05)
    agora = [1000.0]
    monkeypatch.setattr(S, "_RELOGIO", lambda: agora[0])
    S.ligar()
    ordem = []
    lenta = Tarefa("releitura", ordem).comecar()
    assert lenta.dentro.wait(5)
    agora[0] += S.SOSSEGO_S + S.PRAZO_S                      # a releitura do Fracttal leva minutos: não segura a pré-carga
    saiu = threading.Event()
    fio = threading.Thread(target=lambda: (S.esperar_calma(), saiu.set()), daemon=True)
    fio.start()
    assert saiu.wait(5)
    fio.join(5)
    lenta.acabar()


def test_uma_por_vez_embrulha_o_alvo_da_thread():
    S.ligar()
    vistos = []

    def alvo(x, y=0):
        vistos.append(S.estado()["dono"]["nome"])
        return x + y
    assert S.uma_por_vez("nexus-fila-conta", alvo)(2, y=3) == 5
    assert vistos == ["nexus-fila-conta"] and S.estado()["dono"] is None


def test_ligar_duas_vezes_nao_recomeca_a_janela(monkeypatch):
    agora = [1000.0]
    monkeypatch.setattr(S, "_RELOGIO", lambda: agora[0])
    S.ligar()
    agora[0] += 600
    S.ligar()                                                # o app.py e o servir.py chamam uma vez; a 2ª não estica
    assert S.estado()["ha_s"] == 600


# ── quem entra na fila ───────────────────────────────────────────────────────────────────
def _fonte(obj) -> str:
    return inspect.getsource(obj)


def test_o_servidor_e_o_pc_ligam_a_fila_antes_das_tarefas():
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1]
    for arq in ("servir.py", "app.py"):
        texto = (raiz / arq).read_text(encoding="utf-8")
        assert "subida.ligar()" in texto, arq
        assert texto.index("subida.ligar()") < texto.index("instalar_campo(app)"), arq


def test_as_contas_do_campo_entram_na_fila():
    from nexus.campo import visao
    fonte = _fonte(visao.manter_quente)
    assert 'with subida.vez("nexus-campo-quente"):' in fonte
    trecho = fonte.split('with subida.vez("nexus-campo-quente"):', 1)[1]
    assert trecho.lstrip().startswith("aquecer()")


def test_a_fila_da_aprovacao_entra_na_fila():
    from nexus.campo import aprovacao
    fonte = _fonte(aprovacao.aquecer)
    assert fonte.count('subida.uma_por_vez("nexus-fila-conta"') == 2          # nos dois caminhos do aquecer
    assert 'subida.uma_por_vez("nexus-fila-fracttal"' in fonte


def test_os_livros_do_sso_entram_na_fila():
    from nexus.sso import api
    fonte = _fonte(api.aquecer_ao_subir)
    assert 'with subida.vez("nexus-sso-aquecer"):' in fonte


def test_a_pre_carga_espera_a_subida_assentar(app, monkeypatch):
    """A pré-carga abre ~85 telas frias: nos primeiros minutos ela disputava com as tarefas da subida (no reinício das
    17:47 de 16/11/2026 começou aos 17 s, chamada pelo 1º pedido de quem tem setor). Agora espera a calma antes de CADA
    tela, e a fila dela segue guardada até lá."""
    from nexus.auth import pre_carga
    chamadas = []
    monkeypatch.setattr(pre_carga.subida, "esperar_calma", lambda *a, **k: chamadas.append(1) or False)
    e = pre_carga._estado(app)
    with e["trava"]:
        e["fila"].extend(["base/governanca", "base/registro-mestre"])
        e["na_fila"].update(["base/governanca", "base/registro-mestre"])
        e["trabalhando"] = True
    monkeypatch.setattr(pre_carga, "PAUSA_S", 0)
    monkeypatch.setattr(pre_carga.time, "sleep", lambda s: None)
    pre_carga._trabalhar(app)
    assert len(chamadas) == 2 and not e["fila"]              # uma espera por tela, antes de abri-la


def test_o_pre_filtro_espera_a_subida_assentar():
    from nexus.campo import prefiltro_fundo
    for nome in ("_volta", "_volta_meta"):
        fonte = _fonte(getattr(prefiltro_fundo, nome))
        corpo = fonte.split('"""', 2)[2] if '"""' in fonte else fonte.split(":\n", 1)[1]
        assert corpo.lstrip().startswith("subida.esperar_calma()"), nome


# ── a fila no Raio-X ─────────────────────────────────────────────────────────────────────
@pytest.fixture
def raio_x_leve(monkeypatch):
    from nexus.casca import raio_x as R
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 10, "nucleos": 4, "carga": None, "maquina": None})
    return R


def _com_estado(R, monkeypatch, **campos):
    e = {"ligada": True, "ativa": True, "ha_s": 95, "dono": {"nome": "nexus-fila-fracttal", "ha_s": 31},
         "fila": ["nexus-sso-aquecer"],
         "feitas": [{"nome": "nexus-campo-quente", "esperou_s": 0.0, "levou_s": 44.6},
                    {"nome": "nexus-fila-conta", "esperou_s": 12.4, "levou_s": 20.0}]}
    e.update(campos)
    monkeypatch.setattr(R.subida, "estado", lambda: e)


def test_o_raio_x_mostra_a_fila_de_subida(logado, raio_x_leve, monkeypatch):
    """O Levi não tem acesso ao servidor: se a fila funcionou depois de um deploy, é o Raio-X que diz."""
    _com_estado(raio_x_leve, monkeypatch)
    html = logado.get("/t/base/raio-x").get_data(as_text=True)
    trecho = html.split("Fila de subida", 1)[1].split("</section>", 1)[0]
    assert "nexus-fila-fracttal" in trecho and "com a vez há 31 s" in trecho
    assert "nexus-sso-aquecer" in trecho and "esperando a vez" in trecho
    assert "nexus-campo-quente" in trecho and "levou 45 s" in trecho
    assert "nexus-fila-conta" in trecho and "levou 20 s; esperou 12 s pela vez" in trecho
    assert trecho.count("pela vez") == 1                     # quem não esperou não leva o "esperou 0 s"
    assert "subiu há 1 min 35 s" in trecho


@pytest.mark.parametrize("campos", [{"ligada": False, "ativa": False, "ha_s": None}, {"ativa": False, "ha_s": 3700}])
def test_sem_a_fila_ou_uma_hora_depois_o_raio_x_fica_como_antes(logado, raio_x_leve, monkeypatch, campos):
    _com_estado(raio_x_leve, monkeypatch, **campos)
    assert "Fila de subida" not in logado.get("/t/base/raio-x").get_data(as_text=True)


def test_a_fila_que_quebra_nao_derruba_o_raio_x(logado, raio_x_leve, monkeypatch):
    monkeypatch.setattr(raio_x_leve.subida, "estado", lambda: 1 / 0)
    r = logado.get("/t/base/raio-x")
    assert r.status_code == 200 and "Fila de subida" not in r.get_data(as_text=True)
