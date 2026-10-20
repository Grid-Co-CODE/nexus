"""O portão não espera o disco (20/10/2026). Raio-X das 08:56 (Levi: "cliquei em campo app > visão do responsável e foi
um parto para abrir"): a Visão do responsável e a conferência de 5 min de outra aba estavam paradas havia 2 s na trava
da lista de acessos (`acessos._ler`, na linha do `with _TRAVA`), que o portão consulta a CADA pedido de toda sessão
(`auth._admin_em_dia`). A mesma trava era segurada pela gravação do registro de quem entrou (`registrar_login`, a cada
login, com `fsync`) e pela gravação da lista (dar ou tirar acesso): com o disco do servidor ocupado (o banco mora na
mesma máquina), um login gravando devagar segurava as telas de todo mundo, uma atrás da outra.

O disco aqui é de mentira e lento: o `fsync` espera o teste liberar. Nomes de mentira: o repositório é público."""
import threading

import pytest

from conftest import SENHA_TESTE
from nexus import create_app
from nexus.auth import acessos as A
from test_base_acessos import _pelo_fracttal, fracttal_falso  # noqa: F401 — a fixture é usada pelo nome

PESSOA = "pessoa@exemplo.com"
OUTRA = "outra@exemplo.com"


@pytest.fixture
def app(tmp_path):
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_ADMINS": "servidor@exemplo.com", "NEXUS_DADOS": str(tmp_path / "dados")})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    return app


def _disco_lento(monkeypatch):
    """Daqui em diante o `fsync` fica preso até o teste liberar: (entrou no fsync, libera)."""
    entrou, libera = threading.Event(), threading.Event()
    original = A.os.fsync

    def fsync(fd):
        entrou.set()
        libera.wait(10)
        return original(fd)
    monkeypatch.setattr(A.os, "fsync", fsync)
    return entrou, libera


def _em_ate(fn, segundos):
    """Roda `fn` numa thread: (terminou em até `segundos`?, o que devolveu)."""
    r = {}
    t = threading.Thread(target=lambda: r.setdefault("v", fn()), daemon=True)
    t.start()
    t.join(segundos)
    return not t.is_alive(), r.get("v")


def test_login_gravando_devagar_nao_segura_o_portao(app, monkeypatch):
    A.adicionar(app.config, PESSOA, "teste", set())
    assert A.admins_da_tela(app.config) == {PESSOA}
    entrou, libera = _disco_lento(monkeypatch)
    login = threading.Thread(target=A.registrar_login, args=(app.config, OUTRA), daemon=True)
    login.start()
    assert entrou.wait(5)                                         # o login está gravando, preso no disco
    try:
        assert _em_ate(lambda: A.admins_da_tela(app.config), 1.0) == (True, {PESSOA})
    finally:
        libera.set()
        login.join(5)
    assert [x["email"] for x in A.logins_recentes(app.config)] == [OUTRA]


def test_dar_acesso_gravando_devagar_nao_segura_o_portao(app, monkeypatch):
    """Enquanto a lista nova é gravada, o portão segue com a de antes; trocado o arquivo, vale a nova."""
    A.adicionar(app.config, PESSOA, "teste", set())
    assert A.admins_da_tela(app.config) == {PESSOA}
    entrou, libera = _disco_lento(monkeypatch)
    dar = threading.Thread(target=A.adicionar, args=(app.config, OUTRA, "teste", set()), daemon=True)
    dar.start()
    assert entrou.wait(5)
    try:
        assert _em_ate(lambda: A.admins_da_tela(app.config), 1.0) == (True, {PESSOA})
    finally:
        libera.set()
        dar.join(5)
    assert A.admins_da_tela(app.config) == {PESSOA, OUTRA}


def test_a_lista_que_mudou_e_relida_sem_esperar_o_login_de_outro(app, monkeypatch):
    """A lista mudou no disco (outra pessoa deu acesso): o portão relê com a trava DELA, e não com a do registro de
    logins, que está presa no fsync de um login."""
    import json
    A.adicionar(app.config, PESSOA, "teste", set())
    assert A.admins_da_tela(app.config) == {PESSOA}
    arq = A.pasta(app.config) / A.ARQUIVO
    dado = json.loads(arq.read_text(encoding="utf-8"))
    dado["admins"].append({"email": OUTRA, "por": "teste", "quando": ""})
    arq.write_text(json.dumps(dado), encoding="utf-8")
    entrou, libera = _disco_lento(monkeypatch)
    login = threading.Thread(target=A.registrar_login, args=(app.config, "terceira@exemplo.com"), daemon=True)
    login.start()
    assert entrou.wait(5)
    try:
        assert _em_ate(lambda: A.admins_da_tela(app.config), 1.0) == (True, {PESSOA, OUTRA})
    finally:
        libera.set()
        login.join(5)


def test_a_tela_de_quem_ja_entrou_nao_espera_o_login_de_outro(app, fracttal_falso, monkeypatch):  # noqa: F811
    c = _pelo_fracttal(app, PESSOA)
    entrou, libera = _disco_lento(monkeypatch)
    login = threading.Thread(target=A.registrar_login, args=(app.config, OUTRA), daemon=True)
    login.start()
    assert entrou.wait(5)
    try:
        terminou, status = _em_ate(lambda: c.get("/t/base/acessos").status_code, 2.0)
        assert terminou and status in (200, 302, 403)
    finally:
        libera.set()
        login.join(5)
