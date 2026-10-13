"""A pré-carga das telas de quem tem setor (Levi, 12/10/2026: "para esses que tem setores, exceto sem setores e
administradores - assim que entrar já pré carrega tudo o que está disponível para aquela pessoa, pode fazer por partes
mas é interessante que fique cada vez mais leve da pessoa abrir uma informação e analisar!").

Provas: abre por trás só as telas liberadas que podem ser abertas (sem as que leem o Fracttal, o OS Creator e as molduras
da plataforma), na ordem do menu; no máximo uma vez por minuto e só as que esfriaram (4 min); administrador e quem não
tem setor não disparam; a tela que lê o Fracttal na pré-carga sai dela; desligada, nada; e a seção de Acessos mostra a
última volta. Nos testes roda na hora (sem thread), com o banco falso; nada vai ao Fracttal."""
import re

import pytest
from test_setor_telas import ANA, CAIO, URL, _como, _salvar, _sem_copias, banco, setores  # noqa: F401  (fixtures)

from nexus.auth import pre_carga as PC
from nexus.campo import fracttal as F

TELAS = ["cos/mesa", "cos/ocorrencias", "pcm/quadro", "campo/aprovacao", "campo/rondas", "os/inicio",
         "performance/gerencial"]
QUENTES = {"cos/mesa", "cos/ocorrencias", "pcm/quadro", "campo/rondas"}


@pytest.fixture
def ligada(app, setores, logado):
    """O setor Performance (1) com telas de todo tipo, e a pré-carga ligada (na hora, sem thread)."""
    assert _salvar(logado, 1, TELAS).status_code == 303
    app.config["NEXUS_PRE_CARGA"] = "1"
    app.extensions.pop("nexus_pre_carga", None)
    return app


def _estado(app) -> dict:
    return app.extensions.get("nexus_pre_carga") or {}


def test_abre_so_o_que_pode_e_na_ordem_do_menu(app):
    a = PC.aqueciveis(app)
    assert {"cos/mesa", "pcm/quadro", "campo/responsaveis", "campo/rondas", "performance/clima", "base/governanca"} <= set(a)
    assert not set(a) & PC.FORA                                                   # as que leem o Fracttal ao abrir
    assert not [t for t in a if t.startswith("os/")]                              # o OS Creator
    assert "performance/gerencial" not in a and "performance/tempo-real" not in a  # as molduras da plataforma
    ordem = [f"{t.id}/{s.id}" for t in sorted(app.extensions["nexus_torres"], key=lambda t: t.ordem) for s in t.telas]
    assert a == [t for t in ordem if t in a]


def test_o_primeiro_clique_de_quem_tem_setor_aquece_as_telas_dele(ligada):
    assert _como(ligada, ANA).get("/").status_code == 200
    e = _estado(ligada)
    assert set(e["aquecida_em"]) == QUENTES
    assert all(status == 200 for status, _ in e["ultimo"].values())
    assert e["ultima_volta"]["telas"] == 4 and not e["ultima_volta"]["erros"] and not e["trabalhando"]
    # a 1ª tela de cada torre primeiro (onde o cartão do Início leva), depois o resto na ordem do menu
    assert list(e["ultimo"]) == ["cos/mesa", "pcm/quadro", "campo/rondas", "cos/ocorrencias"]


def test_uma_vez_por_minuto_e_so_o_que_esfriou(ligada):
    c = _como(ligada, ANA)
    c.get("/")
    e = _estado(ligada)
    primeira = dict(e["aquecida_em"])
    c.get("/t/cos/mesa")                                          # no mesmo minuto: nada
    assert e["aquecida_em"] == primeira
    for k in e["lembrado_em"]:
        e["lembrado_em"][k] -= 120                                # passou o minuto, mas tudo ainda está quente
    c.get("/t/cos/mesa")
    assert e["aquecida_em"] == primeira
    for k in e["lembrado_em"]:
        e["lembrado_em"][k] -= 120
    for k in e["aquecida_em"]:
        e["aquecida_em"][k] -= PC.REAQUECER_S                     # esfriaram: a volta se repete
    antes = dict(e["aquecida_em"])
    c.get("/t/cos/mesa")
    assert all(e["aquecida_em"][k] > antes[k] for k in antes)


def test_administrador_e_sem_setor_nao_disparam(ligada, logado):
    logado.get("/")                                               # a senha de administrador
    _como(ligada, CAIO).get("/")                                  # sem setor
    ligada.config["NEXUS_ADMINS"] = ANA                           # a Ana administradora: vê tudo, sem pré-carga
    _como(ligada, ANA).get("/")
    assert not _estado(ligada).get("aquecida_em")


def test_desligada_nao_abre_nada(ligada):
    ligada.config["NEXUS_PRE_CARGA"] = "0"
    _como(ligada, ANA).get("/")
    assert not _estado(ligada).get("aquecida_em")


def test_a_tela_que_le_o_fracttal_sai_da_pre_carga(ligada, monkeypatch):
    ep, _ = ligada.url_map.bind("localhost").match("/t/cos/mesa")
    original = ligada.view_functions[ep]

    def com_fracttal(*a, **k):
        if k.get("tela_id", "mesa") == "mesa":
            F.ler("tasks?status=2")
        return original(*a, **k)
    monkeypatch.setitem(ligada.view_functions, ep, com_fracttal)
    F.usar_fornecedor(lambda path: {"data": []})
    try:
        c = _como(ligada, ANA)
        c.get("/")
        e = _estado(ligada)
        assert e["fracttal"] == {"cos/mesa"}
        for k in e["lembrado_em"]:
            e["lembrado_em"][k] -= 120
        for k in e["aquecida_em"]:
            e["aquecida_em"][k] -= PC.REAQUECER_S
        e["aquecida_em"].pop("cos/mesa")
        c.get("/t/pcm/quadro")
        assert "cos/mesa" not in e["aquecida_em"]                 # não volta mais à pré-carga
    finally:
        F.usar_fornecedor(None)


def test_a_marca_do_fracttal_e_da_thread():
    F.usar_fornecedor(lambda path: {"data": []})
    try:
        assert F.marcar_pre_carga(True) is False
        F.ler("tasks")
        assert F.marcar_pre_carga(False) is True
        F.ler("tasks")                                            # sem a marca, não anota
        assert F.marcar_pre_carga(False) is False
    finally:
        F.usar_fornecedor(None)


def test_a_sessao_interna_nao_e_de_ninguem(app):
    from itsdangerous import URLSafeTimedSerializer  # noqa: F401  (o serializador do Flask)
    nome, valor = PC._biscoito(app).split("=", 1)
    assert nome == app.config["SESSION_COOKIE_NAME"]
    dado = app.session_interface.get_signing_serializer(app).loads(valor)
    assert dado == {"logado": True, "admin": True, "pre_carga": True}             # sem usuario: nada de Fracttal de ninguém


def test_acessos_mostra_a_ultima_volta(ligada, logado):
    html = logado.get(URL).get_data(as_text=True)
    assert "nenhuma volta desde que o Nexus subiu" in html
    _como(ligada, ANA).get("/")
    html = logado.get(URL).get_data(as_text=True)
    assert re.search(r"última volta em \d\d/\d\d \d\d:\d\d: 4 telas em [\d,]+ s", html)
