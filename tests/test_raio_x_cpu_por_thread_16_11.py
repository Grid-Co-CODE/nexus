"""O Raio-X diz QUEM usa o processador (16/11/2026, Levi: "qual o motivo do processador estar estourando assim?").

O caso: em 16/11/2026 o Raio-X mostrou o processador do Nexus em 231%, 167% e 242%, e a página só dizia o total. As
threads "trabalhando" não respondem: o rótulo é da linha em que a thread está, e ela pode estar ali esperando a vez de
rodar (o Nexus só roda uma conta Python por vez), e o que passa de 100% é trabalho fora do Python (compactar, imagem, a
rede cifrada), que nem aparece como "trabalhando". Foi preciso amostrar a página 30 vezes de fora para montar o quadro.
Agora, na mesma janela de 1 s do "Processador do Nexus", o Raio-X lê do /proc do Linux o processador de CADA thread do
processo e mostra as que mais usaram, com o nome da tarefa de fundo ou o pedido que a thread atende. Fora do Linux (o
PC), nada aparece. Só nomes de thread e caminhos sem a consulta: nenhum dado de pessoa."""
import threading
import types

import pytest

from nexus.casca import raio_x as R


def _tarefa(pasta, tid, comm, utime, stime):
    d = pasta / str(tid)
    d.mkdir(parents=True)
    # o formato do /proc/<pid>/task/<tid>/stat: o nome entre parênteses pode ter espaço e parêntese
    campos = ["S", "1", "1", "1", "0", "-1", "4194304", "10", "0", "0", "0", str(utime), str(stime)] + ["0"] * 20
    (d / "stat").write_text("%d (%s) %s\n" % (tid, comm, " ".join(campos)), encoding="ascii")


def test_os_tiques_de_cada_thread_saem_do_proc(tmp_path):
    _tarefa(tmp_path, 101, "python", 250, 50)
    _tarefa(tmp_path, 102, "nexus-pre (carga) x", 7, 3)       # o nome com espaço e parênteses não desloca os campos
    (tmp_path / "103").mkdir()                                # a thread que morreu no meio: sem o arquivo, fica de fora
    (tmp_path / "lixo").mkdir()
    assert R._tiques_das_threads(str(tmp_path)) == {101: 300, 102: 10}


def test_fora_do_linux_nao_ha_tiques(tmp_path):
    assert R._tiques_das_threads(str(tmp_path / "nao-existe")) is None
    assert R._quem_gasta(None, None, 1.0) is None


def test_quem_gasta_ordena_soma_e_da_nome():
    antes = {1: 1000, 2: 500, 3: 40, 4: 10, 5: 0}
    depois = {1: 1096, 2: 541, 3: 40, 4: 13, 5: 1, 6: 30, 9: 25}     # a 6 e a 9 nasceram na janela
    nomes = {1: ("nexus-prefiltro", 11), 2: ("waitress-3", 22), 4: ("nexus-campo-quente", 44), 5: ("nexus-presos", 55),
             6: ("ThreadPoolExecutor-60_1", 66)}
    pedidos = {22: "GET /os/historico"}
    quem = R._quem_gasta(antes, depois, 1.0, tiques_por_s=100, nomes=nomes, pedidos=pedidos)
    assert quem == [
        {"nome": "nexus-prefiltro", "pct": 96, "pedido": ""},
        {"nome": "waitress-3", "pct": 41, "pedido": "GET /os/historico"},
        {"nome": "ThreadPoolExecutor-60_1", "pct": 30, "pedido": ""},
        {"nome": "thread sem nome no Python", "pct": 25, "pedido": ""},     # a 9: biblioteca nativa, fora do threading
        {"nome": "nexus-campo-quente", "pct": 3, "pedido": ""},
        {"nome": "nexus-presos", "pct": 1, "pedido": ""},
    ]
    # a janela de 2 s divide; quem não usou não aparece; no máximo MAX_QUEM_GASTA
    dois = R._quem_gasta(antes, depois, 2.0, tiques_por_s=100, nomes=nomes, pedidos=pedidos)
    assert dois[0]["pct"] == 48 and all(l["nome"] != "nexus-presos" for l in dois)     # 0,5% não entra
    muitas = {i: 0 for i in range(1, 40)}
    com_nome = {i: ("tarefa-%d" % i, i) for i in muitas}
    lista = R._quem_gasta(muitas, {i: 5 + i for i in muitas}, 1.0, tiques_por_s=100, nomes=com_nome, pedidos={})
    assert len(lista) == R.MAX_QUEM_GASTA and lista[0] == {"nome": "tarefa-39", "pct": 44, "pedido": ""}


def test_as_threads_sem_nome_somam_numa_linha_so():
    quem = R._quem_gasta({}, {7: 20, 8: 30, 1: 10}, 1.0, tiques_por_s=100, nomes={1: ("nexus-memoria", 5)}, pedidos={})
    assert quem == [{"nome": "thread sem nome no Python", "pct": 50, "pedido": ""},
                    {"nome": "nexus-memoria", "pct": 10, "pedido": ""}]


def test_o_processador_traz_quem_gastou_na_mesma_janela(monkeypatch):
    fotos = iter([{1: 100, 2: 100}, {1: 190, 2: 100}])
    monkeypatch.setattr(R, "_tiques_das_threads", lambda base=None: next(fotos))
    monkeypatch.setattr(R, "_nomes_das_threads", lambda: {1: ("nexus-prefiltro", 11)})
    monkeypatch.setattr(R, "_pedidos_por_thread", lambda: {})
    monkeypatch.setattr(R, "_tiques_por_segundo", lambda: 100)
    monkeypatch.setattr(R.time, "sleep", lambda s: None)
    relogio = iter([10.0, 11.0, 11.0, 11.0])
    monkeypatch.setattr(R.time, "monotonic", lambda: next(relogio))
    cpu = R._processador()
    assert cpu["quem"] == [{"nome": "nexus-prefiltro", "pct": 90, "pedido": ""}]


def test_os_nomes_e_os_pedidos_vem_das_threads_de_verdade(app):
    pronto, soltar = threading.Event(), threading.Event()
    t = threading.Thread(target=lambda: (pronto.set(), soltar.wait(10)), name="nexus-de-teste")
    t.start()
    try:
        assert pronto.wait(10)
        nomes = R._nomes_das_threads()
        assert nomes[t.native_id] == ("nexus-de-teste", t.ident)
        estado = types.SimpleNamespace(trava=threading.Lock(), em_curso={
            1: {"thread": t.ident, "metodo": "GET", "caminho": "/t/campo/rondas", "inicio": 0.0}})
        app.extensions[R.P.CHAVE] = estado
        with app.app_context():
            assert R._pedidos_por_thread() == {t.ident: "GET /t/campo/rondas"}
    finally:
        soltar.set()
        t.join(10)
        app.extensions.pop(R.P.CHAVE, None)


@pytest.fixture
def com_quem(monkeypatch):
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {
        "pct": 167, "nucleos": 8, "carga": None, "maquina": None,
        "quem": [{"nome": "nexus-prefiltro", "pct": 96, "pedido": ""},
                 {"nome": "waitress-3", "pct": 41, "pedido": "GET /os/historico"}]})


def test_a_pagina_mostra_quem_usou_o_processador(logado, com_quem):
    html = logado.get("/t/base/raio-x").get_data(as_text=True)
    assert "Quem usou o processador neste segundo" in html
    trecho = html.split("Quem usou o processador neste segundo", 1)[1].split("</section>", 1)[0]
    assert "nexus-prefiltro" in trecho and "96%" in trecho
    assert "GET /os/historico" in trecho and "41%" in trecho and "waitress-3" not in trecho    # o pedido diz mais que a thread
    # e o cartão do processador resume a que mais usou
    cartao = html.split("Processador do Nexus", 1)[1].split("</article>", 1)[0]
    assert "nexus-prefiltro" in cartao and "96%" in cartao


def test_sem_a_medida_a_pagina_fica_como_antes(logado, monkeypatch):
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 10, "nucleos": 4, "carga": None, "maquina": None})
    html = logado.get("/t/base/raio-x").get_data(as_text=True)
    assert "Quem usou o processador neste segundo" not in html and "Processador do Nexus" in html
