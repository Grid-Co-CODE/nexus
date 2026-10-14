"""Raio-X do Nexus (14/10/2026, Levi: "O nexus está muito lento, carregando bem devagar"): o que o processo faz agora,
para o administrador, sem a T.I. Provas: só administrador; mostra os pedidos em andamento com onde cada um está (pelo
registro dos pedidos presos), as tarefas de fundo e o processador; sem o registro ligado (os testes), diz isso."""
import threading
import time

from nexus.casca import presos as P
from nexus.casca import raio_x as R


def test_so_administrador(app, cliente):
    assert cliente.get("/t/base/raio-x").status_code == 302                     # sem login: vai ao Entrar
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"], s["admin"] = True, False
        s["usuario"] = {"email": "pessoa@exemplo.test", "nome": "Pessoa", "perfil": ""}
    assert c.get("/t/base/raio-x").status_code == 403


def test_sem_o_registro_diz_e_mostra_o_processador(app, logado, monkeypatch):
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 37, "nucleos": 4, "carga": [0.5, 0.4, 0.3]})
    h = logado.get("/t/base/raio-x").get_data(as_text=True)
    assert "Raio-X do Nexus" in h and "37%" in h and "0.5 · 0.4 · 0.3" in h
    assert "O registro dos pedidos só liga no servidor" in h


def test_mostra_o_pedido_preso_e_a_tarefa_de_fundo_com_onde_cada_um_esta(app, logado, monkeypatch):
    monkeypatch.setattr(R, "_processador", lambda janela_s=1.0: {"pct": 100, "nucleos": 2, "carga": None})
    estado = P._Estado(16, None)
    app.extensions[P.CHAVE] = estado
    solta = threading.Event()

    def pedido_lento():
        seq = estado.entrar({"REQUEST_METHOD": "GET", "PATH_INFO": "/os/api/performance/contagens"})
        estado.em_curso[seq]["inicio"] -= 95                                   # há 1 min 35 s
        solta.wait(5)
        estado.sair(seq)

    def tarefa_de_fundo():
        solta.wait(5)
    t1 = threading.Thread(target=pedido_lento, name="waitress-3")
    t2 = threading.Thread(target=tarefa_de_fundo, name="nexus-pre-carga")
    t1.start(), t2.start()
    try:
        for _ in range(50):
            if estado.em_curso:
                break
            time.sleep(0.01)
        h = logado.get("/t/base/raio-x").get_data(as_text=True)
    finally:
        solta.set()
        t1.join(), t2.join()
    assert "GET /os/api/performance/contagens" in h and "1 min 35 s" in h and "1 de 16" in h
    assert "nexus-pre-carga" in h and "esperando outra thread" in h and "waitress-3" not in h
    assert "100%" in h
