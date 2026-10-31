"""O uso das telas do OS Creator por hora (31/10/2026, etapa 0 do canto central do OS Creator): quantas vezes cada tela é
aberta, por quantas pessoas, em quanto tempo e quantos pedidos ela faz ao Fracttal, separando o clique da pessoa do que a
tela pede sozinha. Sem esse número o "antes e depois" de cada etapa seguinte seria chute.

Provas, com um Flask de mentira (rotas `/os/...` falsas, sessão com e-mail fictício, o Fracttal de mentira do
`requests` e o relógio na mão; nada vai à rede nem ao banco): a rota normalizada; o clique e o automático; as pessoas
distintas sem guardar quem; a mediana e o p95; o erro e o 503 do teto; os pedidos ao Fracttal atribuídos à rota que os
fez; o que fica de fora (estático, pré-carga, sem login); o parcial que sobrevive ao reinício; e o corte por setor, que
mora só no disco do servidor, por 30 dias."""
import contextvars
import json
import re
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pytest
import requests
from flask import Flask, jsonify, request, session

from nexus.casca import fracttal_conta as C
from nexus.casca import teto_os
from nexus.casca import uso_os as U
from sessao_real_sem_rede import sessao_real

AQUI = Path(__file__).resolve().parent.parent
_HORA_10 = "2026103010"                 # 13:00Z de 30/10/2026 = 10:00 em Brasília (UTC-3, sem horário de verão)
_HORA_11 = "2026103011"
_CHAVE_PESSOA = "chave-de-pessoa-de-teste"
_UM, _DOIS, _TRES = "pessoa.um@exemplo.invalid", "pessoa.dois@exemplo.invalid", "pessoa.tres@exemplo.invalid"
_COLUNAS = {"hora_id", "rota", "automatico", "pedidos_qtd", "pessoas_qtd", "duracao_p50_ms", "duracao_p95_ms",
            "erros_qtd", "ocupado_qtd", "fracttal_qtd"}
AUTO = {"X-Nexus-Auto": "1"}


class _Relogio:
    """O relógio na mão: a hora de Brasília e a duração do pedido (o cronômetro) andam só quando o teste manda."""

    def __init__(self, utc="2026-10-30T13:00:00+00:00"):
        self.t = datetime.fromisoformat(utc).timestamp()
        self.mono = 5000.0

    def agora(self) -> float:
        return self.t

    def cronometro(self) -> float:
        return self.mono

    def passa(self, segundos: float) -> None:
        self.t += segundos
        self.mono += segundos

    def em(self, utc: str) -> "_Relogio":
        self.t = datetime.fromisoformat(utc).timestamp()
        return self


@pytest.fixture
def relogio(monkeypatch):
    """Os dois contadores zerados, o relógio na mão (10:00 de Brasília) e o gancho do Fracttal ligado; o `Session.send`
    volta ao que era no fim (o monkeypatch guarda o de antes do `ligar`)."""
    monkeypatch.setattr(requests.sessions.Session, "send", requests.sessions.Session.send)
    r = _Relogio()
    monkeypatch.setattr(U, "_agora", r.agora)
    monkeypatch.setattr(U, "_cronometro", r.cronometro)
    monkeypatch.setattr(C, "_agora", r.agora)
    C.limpar()
    U.limpar()
    C.ligar()
    yield r
    C.limpar()
    U.limpar()


@pytest.fixture
def setores(monkeypatch):
    """O setor de cada pessoa sem ir ao banco: `{e-mail: nome do setor}` (quem não está no mapa não tem setor)."""
    from nexus.auth import setor_telas
    mapa: dict = {}

    def acesso():
        nome = mapa.get(((session.get("usuario") or {}).get("email")))
        return {"tudo": True, "telas": set(), "setor": {"id": 1, "nome": nome} if nome else None, "erro": ""}
    monkeypatch.setattr(setor_telas, "acesso", acesso)
    return mapa


def _app(tmp_path, relogio, **extra):
    """Um Flask de mentira: as rotas do OS Creator que os testes usam, uma tela de fora dele e o Fracttal sem rede."""
    app = Flask(__name__)
    app.config.update(SECRET_KEY="chave-de-teste", TESTING=True, PROPAGATE_EXCEPTIONS=False, NEXUS_DADOS=str(tmp_path),
                      NEXUS_PESSOA_HMAC=_CHAVE_PESSOA)
    app.config.update(extra)
    app.extensions["solta"] = threading.Event()
    fracttal, _ = sessao_real(*[(200, None)] * 400)

    def pede(recurso="work_orders"):
        fracttal.get(f"https://app.fracttal.com/api/{recurso}")

    def leva(ms):
        relogio.passa(float(ms) / 1000)

    @app.route("/os/historico")
    def historico():
        leva(request.args.get("ms", 0))
        return "ok"

    @app.route("/os/os/<int:wid>")
    def card(wid):
        leva(request.args.get("ms", 0))
        return "card"

    @app.route("/os/api/quebra")
    def quebra():
        return jsonify(erro="x"), 500

    @app.route("/os/api/explode")
    def explode():
        raise RuntimeError("caiu no meio")

    @app.route("/os/api/selo")
    def selo():
        return jsonify(ok=True)

    @app.route("/os/api/lenta")
    def lenta():
        app.extensions["solta"].wait(5)
        return "ok"

    @app.route("/os/_nexus/sessao")
    def sessao_viva():
        return jsonify(ok=True)

    @app.route("/os/chamados/acompanhamento/estado")
    def estado():
        return jsonify(renovando=False)

    @app.route("/os/static/<path:arquivo>")
    def estatico(arquivo):
        return "css"

    @app.route("/t/os/clonagem")
    def clonagem():
        return "clonagem"

    @app.route("/os/api/fracttal")
    def tres_pedidos():
        for _ in range(3):
            pede()
        return "ok"

    @app.route("/os/api/leque")
    def leque():
        # como o `api._ExecutorComContexto`: cada tarefa leva uma cópia do contexto do pedido
        with ThreadPoolExecutor(max_workers=3) as ex:
            for f in [ex.submit(contextvars.copy_context().run, pede) for _ in range(4)]:
                f.result()
        return "ok"

    @app.route("/t/campo/ronda/<int:n>")
    def ronda(n):
        pede("items")
        return "ronda"

    return app


def _cliente(app, email=_UM, **sessao):
    """Um navegador logado como `email` (sem e-mail: a senha de administrador, que não traz pessoa)."""
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"] = True
        if email:
            s["usuario"] = {"email": email}
        s.update(sessao)
    return c


def _codigo(email):
    from nexus.campo.ligacao_cadastro import codigo_da_pessoa
    return codigo_da_pessoa(_CHAVE_PESSOA, email)


def _linhas(hora=_HORA_10):
    return {(lin["rota"], lin["automatico"]): lin for lin in U.instantaneo()["linhas"] if lin["hora_id"] == hora}


def _linha(rota, automatico=0, hora=_HORA_10):
    achadas = _linhas(hora)
    assert (rota, automatico) in achadas, f"{(rota, automatico)} em {sorted(achadas)}"
    return achadas[(rota, automatico)]


# ── a rota normalizada ───────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("entra, sai", [
    ("/os/os/16995", "/os/os/<n>"),                                      # o exemplo do desenho
    ("/os/os/16995?parcial=1&x=2", "/os/os/<n>"),                        # a query sai
    ("/os/os/16995#topo", "/os/os/<n>"),
    ("/os/api/os/16995/tarefa/42/checklist", "/os/api/os/<n>/tarefa/<n>/checklist"),
    ("/os/api/solic/5001/aprovar", "/os/api/solic/<n>/aprovar"),
    ("/os/chamados/acompanhamento/20001/preparar", "/os/chamados/acompanhamento/<n>/preparar"),
    ("/os/_nexus/engenharia/acompanhamento/3f9c2a7b1d4e/salvar", "/os/_nexus/engenharia/acompanhamento/<id>/salvar"),
    ("/os/_nexus/engenharia/acompanhamento/3F9C2A7B1D4E/salvar", "/os/_nexus/engenharia/acompanhamento/<id>/salvar"),
    ("/x/123e4567-e89b-12d3-a456-426614174000/y", "/x/<id>/y"),          # uuid
    ("/os/api/os/12/anexos-zip/Zk3_aB9-xQ2mP7vL1nR8sT4u", "/os/api/os/<n>/anexos-zip/<id>"),   # token_urlsafe(18)
    ("/t/campo/ocorrencias/oc0123456789a", "/t/campo/ocorrencias/<id>"),     # prefixo + uuid.hex[:11]
    ("/t/x/ev-0123456789abcdef", "/t/x/<id>"),
    ("/os/historico", "/os/historico"),                                  # palavra não vira id
    ("/os/", "/os/"),
    ("/os", "/os"),
    ("/t/os/clonagem", "/t/os/clonagem"),
    ("/os/chamados/acompanhamento/estado", "/os/chamados/acompanhamento/estado"),
    ("/os/api/os/12/cancel-motivos", "/os/api/os/<n>/cancel-motivos"),
    ("/t/engenharia/acompanhamento-de-chamados-garantia", "/t/engenharia/acompanhamento-de-chamados-garantia"),
    ("/t/pcm/relatorio-8h", "/t/pcm/relatorio-8h"),                      # dígito dentro de palavra curta: segue
    ("/t/pcm/v2/abc123", "/t/pcm/v2/abc123"),                            # curto demais para ser id
    ("", ""),
    (None, ""),
])
def test_normalizar_rota(entra, sai):
    assert U.normalizar_rota(entra) == sai


def test_normalizar_rota_tem_tamanho_maximo():
    longa = "/os/" + "palavra/" * 100
    assert len(U.normalizar_rota(longa)) <= U.MAX_CARACTERES_DA_ROTA


def test_nenhuma_palavra_de_rota_vira_id():
    """O esquecimento de verdade: palavra de rota que a normalização tomasse por número ou id juntaria telas diferentes
    na mesma linha. Confere todo trecho fixo das rotas do Nexus e do clone do OS Creator."""
    from nexus import create_app
    trechos = set()
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": "senha-de-teste"})
    for regra in app.url_map.iter_rules():
        trechos.update(s for s in regra.rule.split("/") if s and "<" not in s)
    fontes = list((AQUI / "nexus/torres/oscreator/os_creator/os_web").glob("*.py")) + [
        AQUI / "nexus/torres/oscreator/ponte.py"]
    for fonte in fontes:
        for rota in re.findall(r"route\(\s*[\"']([^\"']+)[\"']", fonte.read_text(encoding="utf-8")):
            trechos.update(s for s in rota.split("/") if s and "<" not in s)
    assert len(trechos) > 100
    trocados = sorted(t for t in trechos if U.normalizar_rota("/" + t) != "/" + t)
    assert trocados == []


# ── o clique e o automático ──────────────────────────────────────────────────────────────────────────────────────────
def test_conta_clique_e_automatico(tmp_path, relogio):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=False)
    c = _cliente(app)
    c.get("/os/historico")                                               # clique
    c.get("/os/historico?modo=cos")                                      # clique: a query não muda a rota
    c.get("/os/historico", headers=AUTO)                                 # a atualização de 10 min pede pelo cabeçalho...
    c.get("/os/historico?nx_auto=1&modo=criadas")                        # ...ou pelo endereço (o formulário não manda cabeçalho)
    c.get("/os/historico", headers={"X-Nexus-Auto": "0"})                # só o valor 1 marca
    c.get("/os/_nexus/sessao")                                           # as rotas da lista fixa são automáticas...
    c.get("/os/chamados/acompanhamento/estado")                          # ...mesmo sem o cabeçalho (aba com o JS de antes)
    c.get("/os/historico/progresso?p=abc123")                            # o círculo de carga, de 350 em 350 ms
    c.get("/os/os/16995")
    c.get("/os/os/20001?ms=0")                                           # as duas OS são a mesma rota
    c.get("/t/os/clonagem")                                              # as telas do OS Creator no Nexus também contam
    linhas = _linhas()
    assert linhas[("/os/historico", 0)]["pedidos_qtd"] == 3
    assert linhas[("/os/historico", 1)]["pedidos_qtd"] == 2
    assert linhas[("/os/_nexus/sessao", 1)]["pedidos_qtd"] == 1 and ("/os/_nexus/sessao", 0) not in linhas
    assert linhas[("/os/chamados/acompanhamento/estado", 1)]["pedidos_qtd"] == 1
    assert linhas[("/os/historico/progresso", 1)]["pedidos_qtd"] == 1 and ("/os/historico/progresso", 0) not in linhas
    assert linhas[("/os/os/<n>", 0)]["pedidos_qtd"] == 2
    assert linhas[("/t/os/clonagem", 0)]["pedidos_qtd"] == 1
    assert len(linhas) == 7
    assert all(set(lin) == _COLUNAS for lin in linhas.values())
    assert all(lin["automatico"] in (0, 1) and isinstance(lin["automatico"], int) for lin in linhas.values())


def test_so_o_valor_um_marca_o_automatico_no_endereco(tmp_path, relogio):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=False)
    c = _cliente(app)
    c.get("/os/historico?nx_auto=0")
    c.get("/os/historico?nx_auto=")
    c.get("/os/historico?outra=nx_auto%3D1")
    assert set(_linhas()) == {("/os/historico", 0)} and _linha("/os/historico")["pedidos_qtd"] == 3


def test_a_hora_e_a_de_brasilia(tmp_path, relogio):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=False)
    relogio.em("2026-10-31T02:30:00+00:00")                              # 23:30 de 30/10 em Brasília, já 31/10 em UTC
    _cliente(app).get("/os/historico")
    relogio.em("2026-10-31T03:00:00+00:00")                              # a virada do dia de Brasília
    _cliente(app).get("/os/historico")
    assert sorted(lin["hora_id"] for lin in U.instantaneo()["linhas"]) == ["2026103023", "2026103100"]


# ── as pessoas ───────────────────────────────────────────────────────────────────────────────────────────────────────
def test_pessoas_distintas_sem_guardar_quem(tmp_path, relogio, setores):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=True)
    setores.update({_UM: "Setor Alfa"})
    um, dois, adm = _cliente(app, _UM), _cliente(app, _DOIS), _cliente(app, None)
    for c in (um, um, um, dois, adm):                                    # a senha de administrador não traz pessoa
        c.get("/os/historico")
    lin = _linha("/os/historico")
    assert lin["pedidos_qtd"] == 5 and lin["pessoas_qtd"] == 2
    # na memória, só o código do e-mail (o HMAC), nunca o e-mail
    balde = U._horas[_HORA_10].baldes[("/os/historico", 0)]
    assert balde.pessoas == {_codigo(_UM), _codigo(_DOIS)}
    # no disco, contagens: nem o e-mail, nem o código, nem a chave
    U.salvar()
    for nome in ("uso_os_parcial.json", "uso_os_setor.json"):
        texto = (tmp_path / "casca" / nome).read_text(encoding="utf-8")
        for proibido in (_UM, _DOIS, "exemplo.invalid", _codigo(_UM), _codigo(_DOIS), _CHAVE_PESSOA):
            assert proibido not in texto, (nome, proibido)
    # na linha que vai ao banco, nenhuma coluna diz quem
    assert set(lin) == _COLUNAS
    assert all(_codigo(e) not in json.dumps(lin) for e in (_UM, _DOIS))


def test_sem_a_chave_das_pessoas_conta_pela_chave_do_app(tmp_path, relogio):
    """O PC pode não ter a NEXUS_PESSOA_HMAC: as pessoas se contam do mesmo jeito (o código só vive na memória)."""
    app = _app(tmp_path, relogio, NEXUS_PESSOA_HMAC=None)
    U.ligar(app, gravar=False)
    for e in (_UM, _DOIS, _UM):
        _cliente(app, e).get("/os/historico")
    assert _linha("/os/historico")["pessoas_qtd"] == 2


# ── a duração ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_p50_p95(tmp_path, relogio):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=False)
    c = _cliente(app)
    for ms in range(1, 101):
        c.get(f"/os/historico?ms={ms}")                                  # o pedido leva `ms` milissegundos
    lin = _linha("/os/historico")
    assert lin["pedidos_qtd"] == 100
    assert 48 <= lin["duracao_p50_ms"] <= 52 and 93 <= lin["duracao_p95_ms"] <= 97
    assert isinstance(lin["duracao_p50_ms"], int)
    c.get("/os/os/1?ms=2000")                                            # um pedido só: a mediana e o p95 são o tempo dele
    lin = _linha("/os/os/<n>")
    assert 1940 <= lin["duracao_p50_ms"] <= 2060 and lin["duracao_p50_ms"] == lin["duracao_p95_ms"]
    c.get("/os/api/selo")                                                # instantâneo: 1 ms é o piso
    assert _linha("/os/api/selo")["duracao_p50_ms"] == 1


def test_p95_pega_a_cauda(tmp_path, relogio):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=False)
    c = _cliente(app)
    for _ in range(94):
        c.get("/os/historico?ms=100")
    for _ in range(6):
        c.get("/os/historico?ms=9000")                                   # 6% de pedidos lentos
    lin = _linha("/os/historico")
    assert 95 <= lin["duracao_p50_ms"] <= 105 and 8700 <= lin["duracao_p95_ms"] <= 9300


# ── erro e ocupado ───────────────────────────────────────────────────────────────────────────────────────────────────
def test_erro_e_ocupado(tmp_path, relogio):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=False)
    c = _cliente(app)
    assert c.get("/os/api/quebra").status_code == 500                    # a tela respondeu 500
    assert c.get("/os/api/explode").status_code == 500                   # exceção sem tratamento: o Flask devolve 500
    assert c.get("/os/api/nao-existe").status_code == 404                # 404 não é erro do servidor
    c.get("/os/api/selo")
    assert _linha("/os/api/quebra")["erros_qtd"] == 1
    assert _linha("/os/api/explode")["erros_qtd"] == 1 and _linha("/os/api/explode")["pedidos_qtd"] == 1
    assert _linha("/os/api/nao-existe")["erros_qtd"] == 0 and _linha("/os/api/nao-existe")["pedidos_qtd"] == 1
    assert _linha("/os/api/selo")["erros_qtd"] == 0
    assert all(lin["ocupado_qtd"] == 0 for lin in U.instantaneo()["linhas"])


def test_o_teto_cheio_conta_ocupado(tmp_path, relogio):
    """O 503 do teto (casca/teto_os.py) nasce antes do Flask: o teto avisa o uso. O pedido recusado conta (a pessoa
    clicou), não é erro do servidor e não entra na duração (esperou a vaga, não foi atendido)."""
    app = _app(tmp_path, relogio)
    teto_os.ligar(app, teto=1, espera=0.05)
    U.ligar(app, gravar=False)                                           # depois do teto: é ele que avisa
    preso = threading.Thread(target=lambda: _cliente(app, _UM).get("/os/api/lenta"))
    preso.start()
    for _ in range(300):
        if app.extensions[teto_os.CHAVE].estado()["em_uso"] == 1:
            break
        time.sleep(0.01)
    try:
        assert _cliente(app, _DOIS).get("/os/api/selo").status_code == 503
        assert _cliente(app, _DOIS).get("/os/historico?nx_auto=1").status_code == 503
    finally:
        app.extensions["solta"].set()
        preso.join(5)
    selo = _linha("/os/api/selo")
    assert (selo["pedidos_qtd"], selo["ocupado_qtd"], selo["erros_qtd"], selo["pessoas_qtd"]) == (1, 1, 0, 0)
    assert selo["duracao_p50_ms"] is None and selo["duracao_p95_ms"] is None          # nenhum pedido atendido
    assert _linha("/os/historico", 1)["ocupado_qtd"] == 1                # o automático recusado também
    lenta = _linha("/os/api/lenta")
    assert (lenta["pedidos_qtd"], lenta["ocupado_qtd"], lenta["pessoas_qtd"]) == (1, 0, 1)


def test_sem_o_uso_ligado_o_teto_segue_igual(tmp_path, relogio):
    app = _app(tmp_path, relogio)
    teto_os.ligar(app, teto=1, espera=0.05)
    assert app.extensions[teto_os.CHAVE].ao_recusar is None
    assert _cliente(app).get("/os/api/selo").status_code == 200
    assert U.instantaneo()["linhas"] == []


# ── os pedidos ao Fracttal ───────────────────────────────────────────────────────────────────────────────────────────
def test_fracttal_atribuido_ao_pedido(tmp_path, relogio):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=False)
    c = _cliente(app)
    c.get("/os/api/fracttal")
    c.get("/os/api/fracttal")
    c.get("/os/api/leque")                                               # as tarefas do fan-out são da rota que as chamou
    c.get("/os/historico")                                               # sem pedido ao Fracttal
    assert _linha("/os/api/fracttal")["fracttal_qtd"] == 6
    assert _linha("/os/api/leque")["fracttal_qtd"] == 4
    assert _linha("/os/historico")["fracttal_qtd"] == 0
    # o contador do Fracttal atribui os mesmos pedidos à mesma rota: dá para juntar o uso com o consumo
    origens = {(lin["origem"], lin["metodo"]): lin["pedidos_qtd"] for lin in C.instantaneo()}
    assert origens[("/os/api/fracttal", "work_orders")] == 6 and origens[("/os/api/leque", "work_orders")] == 4


def test_toda_rota_do_flask_marca_a_origem_do_fracttal(tmp_path, relogio):
    """Os pedidos das telas do Campo, da Engenharia e do PCM caem na rota deles, e não em `fundo:waitress`; mas o uso das
    telas só conta o OS Creator."""
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=False)
    c = _cliente(app)
    c.get("/t/campo/ronda/77")
    c.get("/t/campo/ronda/78")
    origens = {(lin["origem"], lin["metodo"]): lin["pedidos_qtd"] for lin in C.instantaneo() if lin["origem"] != "*"}
    assert origens == {("/t/campo/ronda/<n>", "items"): 2}                # a rota normalizada, não o número da ronda
    assert U.instantaneo()["linhas"] == []
    app.test_client().get("/t/campo/ronda/79")                           # até o pedido sem login marca a origem
    assert C.instantaneo()[1]["pedidos_qtd"] == 3


def test_a_marca_sai_com_o_pedido_mesmo_quando_ele_quebra(tmp_path, relogio):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=False)
    c = _cliente(app)
    s, _ = sessao_real(*[(200, None)] * 5)
    c.get("/os/api/fracttal")
    c.get("/os/api/explode")                                             # a exceção não deixa a marca presa na thread
    c.get("/os/api/nao-existe")
    assert C.pedidos_desta_thread() == 0
    s.get("https://app.fracttal.com/api/items")                          # o que esta thread pedir agora é dela, do fundo
    origens = {lin["origem"] for lin in C.instantaneo() if lin["origem"] != "*"}
    assert origens == {"/os/api/fracttal", f"fundo:{C._nome_de_fundo(threading.current_thread().name)}"}


# ── o que não é uso das telas ────────────────────────────────────────────────────────────────────────────────────────
def test_static_fora(tmp_path, relogio):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=False)
    c = _cliente(app)
    c.get("/os/static/inicio.css")                                       # os estáticos do OS Creator
    c.get("/t/campo/ronda/1")                                            # outra torre
    c.get("/os/historico", headers={"X-Nexus-Pre-Carga": "1"})           # a pré-carga abre as telas por dentro
    _cliente(app, None, logado=False).get("/os/historico")               # sem login: o portão responde, não é uso
    app.test_client().get("/os/historico")                               # sem sessão nenhuma
    assert U.instantaneo()["linhas"] == []
    c.get("/os/historico")                                               # e o clique de verdade conta
    assert [lin["rota"] for lin in U.instantaneo()["linhas"]] == ["/os/historico"]


def test_ligar_duas_vezes_nao_conta_em_dobro(tmp_path, relogio):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=False)
    U.ligar(app, gravar=False)
    _cliente(app).get("/os/historico")
    assert _linha("/os/historico")["pedidos_qtd"] == 1


# ── a hora aberta, o teto de memória ─────────────────────────────────────────────────────────────────────────────────
def test_drenar_tira_so_as_horas_fechadas(tmp_path, relogio):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=False)
    c = _cliente(app)
    c.get("/os/historico")
    c.get("/os/os/1", headers=AUTO)
    relogio.passa(3600)                                                  # 11:00
    c.get("/os/historico")
    assert U.drenar(_HORA_10) == []                                      # a hora aberta (a de agora) fica; ate_hora_id é exclusivo
    saiu = U.drenar(_HORA_11)                                            # a 10h fechou: sai, e só ela
    assert [(lin["hora_id"], lin["rota"], lin["automatico"]) for lin in saiu] == [
        (_HORA_10, "/os/historico", 0), (_HORA_10, "/os/os/<n>", 1)]
    assert all(set(lin) == _COLUNAS for lin in saiu)
    assert [lin["hora_id"] for lin in U.instantaneo()["linhas"]] == [_HORA_11]
    assert U.drenar(_HORA_11) == []                                      # a hora drenada não sai duas vezes
    assert len(U.drenar("2026103012")) == 1


# A hora do pedido é lida DENTRO da trava, como no `fracttal_conta._registrar`. Lida antes, o laço da gravação podia drenar a
# hora no meio da conta; o pedido a recriava com 1 pedido, o próximo `drenar` devolvia a MESMA chave (hora, rota, automático)
# com o número errado, e a gravação por chave (Task 0.3) trocaria a linha certa pela dele.
def test_hora_drenada_enquanto_o_setor_e_achado_nao_renasce(tmp_path, relogio, monkeypatch):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=True)
    c = _cliente(app, _UM)
    c.get("/os/historico")                                               # 10h: um pedido, que vai ser gravado
    drenado = []

    def setor_que_demora():
        relogio.passa(3600)                                              # a hora vira no meio da conta deste pedido...
        drenado.extend(U.drenar(C.hora_id_de()))                         # ...e o laço da gravação drena a 10h, que fechou
        return U.SEM_SETOR
    monkeypatch.setattr(U, "_setor_da_pessoa", setor_que_demora)
    c.get("/os/historico")                                               # começou às 10h, a conta fecha às 11h
    assert [(lin["hora_id"], lin["pedidos_qtd"]) for lin in drenado] == [(_HORA_10, 1)]      # a 10h saiu como estava
    assert [(lin["hora_id"], lin["pedidos_qtd"]) for lin in U.instantaneo()["linhas"]] == [(_HORA_11, 1)]   # e ele é da 11h
    proximo = U.drenar("2026103012")
    assert [lin["hora_id"] for lin in drenado + proximo] == [_HORA_10, _HORA_11]       # nenhuma chave sai duas vezes


class _TravaQueDrena:
    """A trava do módulo, mas na 1ª vez que alguém vai tomá-la a hora vira e o laço da gravação drena a que fechou: põe a
    drenagem EXATAMENTE entre o que a conta fez antes da trava e a trava (a janela que o relógio lido dentro dela fecha)."""

    def __init__(self, relogio, drenado):
        self.real, self.relogio, self.drenado, self.feito = threading.Lock(), relogio, drenado, False

    def __enter__(self):
        if not self.feito:
            self.feito = True
            self.relogio.passa(3600)
            self.drenado.extend(U.drenar(C.hora_id_de()))                # (o `drenar` toma a trava já pelo caminho normal)
        self.real.acquire()
        return self

    def __exit__(self, *exc):
        self.real.release()


@pytest.mark.parametrize("quem", ["atendido", "recusado"])
def test_hora_drenada_antes_da_trava_nao_renasce(tmp_path, relogio, monkeypatch, quem):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=True)
    c = _cliente(app, _UM)
    c.get("/os/historico")                                               # 10h: um pedido, que vai ser gravado
    drenado = []
    monkeypatch.setattr(U, "_trava", _TravaQueDrena(relogio, drenado))
    if quem == "atendido":
        c.get("/os/historico")                                           # a conta do pedido que a tela fez às 10h
    else:
        U.recusado({"PATH_INFO": "/os/historico", "QUERY_STRING": ""})   # o 503 do teto, que não passa pelo Flask
    assert [(lin["hora_id"], lin["pedidos_qtd"]) for lin in drenado] == [(_HORA_10, 1)]
    assert [(lin["hora_id"], lin["pedidos_qtd"]) for lin in U.instantaneo()["linhas"]] == [(_HORA_11, 1)]


def test_horas_guardadas_tem_teto(tmp_path, relogio, monkeypatch):
    """Sem o laço da gravação (o PC, ou o banco fora por dias) as horas não podem crescer sem fim: as pessoas de cada
    uma ficam na memória."""
    monkeypatch.setattr(U, "MAX_HORAS", 3)
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=False)
    c = _cliente(app)
    for _ in range(6):
        c.get("/os/historico")
        relogio.passa(3600)
    horas = sorted({lin["hora_id"] for lin in U.instantaneo()["linhas"]})
    assert horas == ["2026103013", "2026103014", "2026103015"]           # ficam as mais novas


def test_rotas_distintas_por_hora_tem_teto(tmp_path, relogio, monkeypatch):
    monkeypatch.setattr(U, "MAX_ROTAS", 3)
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=False)
    c = _cliente(app)
    for caminho in ("/os/a1", "/os/a2", "/os/a3", "/os/a4", "/os/a5", "/os/a1"):
        c.get(caminho)                                                   # 404 conta como pedido da rota (o que veio)
    c.get("/os/a2", headers=AUTO)                                        # automático da rota que já tinha vaga: entra
    linhas = _linhas()
    assert {r for r, _a in linhas} == {"/os/a1", "/os/a2", "/os/a3", U.OUTRAS}
    assert linhas[("/os/a1", 0)]["pedidos_qtd"] == 2 and linhas[(U.OUTRAS, 0)]["pedidos_qtd"] == 2
    assert ("/os/a2", 1) in linhas
    relogio.passa(3600)                                                  # a hora seguinte recomeça a conta
    c.get("/os/a5")
    assert ("/os/a5", 0) in _linhas(_HORA_11)


# ── o parcial: o reinício não perde a hora ───────────────────────────────────────────────────────────────────────────
def test_parcial_volta_no_boot(tmp_path, relogio):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=True)
    um, dois = _cliente(app, _UM), _cliente(app, _DOIS)
    um.get("/os/historico?ms=40")
    dois.get("/os/historico?ms=60")
    um.get("/os/historico", headers=AUTO)
    um.get("/os/api/fracttal")
    um.get("/os/api/quebra")
    relogio.passa(3600)
    um.get("/os/os/16995?ms=300")
    antes = U.instantaneo()["linhas"]
    assert {lin["hora_id"] for lin in antes} == {_HORA_10, _HORA_11}
    U.salvar()                                                           # o laço de 5 em 5 minutos faz isto
    # o processo reinicia: a memória some, o boot lê o arquivo
    U.limpar()
    assert U.instantaneo()["linhas"] == []
    novo = _app(tmp_path, relogio)
    U.ligar(novo, gravar=True)
    assert U.instantaneo()["linhas"] == antes                            # nenhuma linha se perdeu, nenhum número mudou
    # pessoas depois do reinício: a soma dos dois lados, no máximo os pedidos (quem já tinha vindo pode contar de novo)
    _cliente(novo, _UM).get("/os/os/16995?ms=300")
    lin = _linha("/os/os/<n>", hora=_HORA_11)
    assert lin["pedidos_qtd"] == 2 and 1 <= lin["pessoas_qtd"] <= lin["pedidos_qtd"]
    assert 280 <= lin["duracao_p50_ms"] <= 320                           # a duração soma as duas metades
    # e a hora seguinte do mesmo processo segue gravando por cima do arquivo
    U.salvar()
    assert json.loads((tmp_path / "casca" / "uso_os_parcial.json").read_text(encoding="utf-8"))["horas"][_HORA_11]


def test_parcial_so_tem_contagens(tmp_path, relogio, setores):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=True)
    setores[_UM] = "Setor Alfa"
    _cliente(app, _UM).get("/os/historico?ms=40")
    U.salvar()
    arq = tmp_path / "casca" / "uso_os_parcial.json"
    dados = json.loads(arq.read_text(encoding="utf-8"))
    assert set(dados) == {"versao", "gravado_em", "horas"}
    assert list(dados["horas"]) == [_HORA_10]
    for balde in dados["horas"][_HORA_10]:
        assert set(balde) == {"rota", "automatico", "pedidos", "pessoas", "histo", "erros", "ocupado", "fracttal"}
        assert isinstance(balde["pessoas"], int)                         # quantas, nunca quem
    assert not list((tmp_path / "casca").glob("*.tmp"))                  # a gravação atômica não deixa resto


@pytest.mark.parametrize("conteudo", [
    "{ isto não é json",
    "",
    "[]",
    '"texto"',
    "null",
    pytest.param("[" * 300000, id="aninhado"),                # o json levanta RecursionError, e não ValueError
    '{"horas": []}',
    '{"horas": {"2026103010": "x"}}',
    '{"horas": {"não-é-hora": [{"rota": "/os/x", "automatico": 0, "pedidos": 1, "pessoas": 1, "histo": {}, '
    '"erros": 0, "ocupado": 0, "fracttal": 0}]}}',
])
def test_parcial_corrompido_ignorado(tmp_path, relogio, conteudo):
    (tmp_path / "casca").mkdir()
    (tmp_path / "casca" / "uso_os_parcial.json").write_text(conteudo, encoding="utf-8")
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=True)                                            # não levanta: o Nexus sobe do mesmo jeito
    assert U.instantaneo()["linhas"] == []
    _cliente(app).get("/os/historico")                                   # e o uso segue contando
    U.salvar()                                                           # e a gravação seguinte conserta o arquivo
    dados = json.loads((tmp_path / "casca" / "uso_os_parcial.json").read_text(encoding="utf-8"))
    assert list(dados["horas"]) == [_HORA_10]


def test_parcial_com_um_balde_ruim_aproveita_os_bons(tmp_path, relogio):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=True)
    _cliente(app).get("/os/historico?ms=50")
    U.salvar()
    arq = tmp_path / "casca" / "uso_os_parcial.json"
    dados = json.loads(arq.read_text(encoding="utf-8"))
    ruins = [{"rota": "/os/ruim1", "automatico": 0, "pedidos": "muitos", "pessoas": 0, "histo": {}, "erros": 0,
              "ocupado": 0, "fracttal": 0},
             {"rota": "/os/ruim2", "automatico": 0, "pedidos": -4, "pessoas": 0, "histo": {}, "erros": 0, "ocupado": 0,
              "fracttal": 0},
             {"rota": "/os/ruim3", "automatico": 0, "pedidos": 2, "pessoas": 9, "histo": {}, "erros": 0, "ocupado": 0,
              "fracttal": 0},                                            # mais pessoas que pedidos
             {"rota": "/os/ruim4", "automatico": 0, "pedidos": 2, "pessoas": 1, "histo": {"x": 1}, "erros": 0,
              "ocupado": 0, "fracttal": 0},
             {"rota": 7, "automatico": 0, "pedidos": 2}, "não é um balde"]
    dados["horas"][_HORA_10] += ruins
    arq.write_text(json.dumps(dados), encoding="utf-8")
    U.limpar()
    U.ligar(_app(tmp_path, relogio), gravar=True)
    assert [(lin["rota"], lin["pedidos_qtd"]) for lin in U.instantaneo()["linhas"]] == [("/os/historico", 1)]


def test_o_laco_de_cinco_minutos_so_liga_fora_dos_testes(tmp_path, relogio, monkeypatch):
    rodou = threading.Event()
    monkeypatch.setattr(U, "_laco", rodou.set)
    # o laço da gravação de hora em hora também sai de cena: de verdade ele dormiria até o :05 e, acordando no meio de outro
    # teste, tiraria as horas dos contadores dele (a prova dele é a de tests/test_dados_fato_uso_os.py)
    monkeypatch.setattr(U, "_laco_gravacao", lambda: None)
    U.ligar(_app(tmp_path, relogio), gravar=True)                        # TESTING: sem thread
    assert not rodou.wait(0.3)
    U.limpar()
    U.ligar(_app(tmp_path, relogio, TESTING=False), gravar=True)         # o servidor: com o laço
    assert rodou.wait(3)
    assert U.PASSO_S == 300


def test_sem_pasta_de_dados_o_uso_conta_e_nao_grava(tmp_path, relogio):
    app = _app(tmp_path, relogio, NEXUS_DADOS=None)                      # teste sem NEXUS_DADOS: a pasta de dados se recusa
    U.ligar(app, gravar=False)
    _cliente(app).get("/os/historico")
    U.salvar()                                                           # não levanta, não grava em lugar nenhum
    assert _linha("/os/historico")["pedidos_qtd"] == 1
    assert not (tmp_path / "casca").exists()


def test_falha_ao_gravar_nao_derruba_e_nao_estraga_o_arquivo(tmp_path, relogio, monkeypatch, caplog):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=True)
    _cliente(app).get("/os/historico")
    U.salvar()
    arq = tmp_path / "casca" / "uso_os_parcial.json"
    bom = arq.read_text(encoding="utf-8")
    _cliente(app).get("/os/historico")

    def nao_troca(*a, **k):
        raise OSError("disco cheio")
    monkeypatch.setattr(U.os, "replace", nao_troca)
    with caplog.at_level("WARNING"):
        U.salvar()                                                       # a gravação atômica falhou: o laço segue
    assert arq.read_text(encoding="utf-8") == bom                        # o arquivo de antes continua inteiro
    assert not list(arq.parent.glob("*.tmp"))                            # e o rascunho não fica para trás
    assert "disco cheio" in caplog.text


# ── o corte por setor: só no disco do servidor, 30 dias ──────────────────────────────────────────────────────────────
def test_setor_so_no_disco_30_dias(tmp_path, relogio, setores):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=True)
    setores.update({_UM: "Setor Alfa", _DOIS: "Setor Beta"})
    um, dois, tres = _cliente(app, _UM), _cliente(app, _DOIS), _cliente(app, _TRES)   # a 3ª pessoa não tem setor
    um.get("/os/historico")
    um.get("/os/historico", headers=AUTO)
    dois.get("/os/historico")
    tres.get("/os/historico")
    _cliente(app, None).get("/os/historico")                             # a senha de administrador: sem pessoa, sem setor
    # o corte está na memória (para o Raio-X)...
    esperado = {"20261030": {
        "Setor Alfa": {"/os/historico": {"cliques": 1, "automaticos": 1}},
        "Setor Beta": {"/os/historico": {"cliques": 1, "automaticos": 0}},
        U.SEM_SETOR: {"/os/historico": {"cliques": 2, "automaticos": 0}}}}
    assert U.instantaneo()["setor"] == esperado
    # ...e no disco do servidor
    U.salvar()
    arq = tmp_path / "casca" / "uso_os_setor.json"
    assert json.loads(arq.read_text(encoding="utf-8"))["dias"] == esperado
    # NUNCA no que vai ao banco, nem no parcial: as linhas por hora não têm setor
    linhas = U.drenar(_HORA_11)
    assert linhas and all(set(lin) == _COLUNAS for lin in linhas)
    assert "Setor" not in json.dumps(linhas)
    assert "Setor" not in (tmp_path / "casca" / "uso_os_parcial.json").read_text(encoding="utf-8")
    # 30 dias: o dia que completa 30 dias sai, o de 29 dias atrás ainda fica
    relogio.passa(29 * 86400)
    um.get("/os/historico")
    U.salvar()
    assert sorted(json.loads(arq.read_text(encoding="utf-8"))["dias"]) == ["20261030", "20261128"]
    relogio.passa(86400)
    um.get("/os/historico")
    U.salvar()
    assert sorted(json.loads(arq.read_text(encoding="utf-8"))["dias"]) == ["20261128", "20261129"]
    assert sorted(U.instantaneo()["setor"]) == ["20261128", "20261129"]


def test_setor_volta_no_boot_e_ignora_arquivo_corrompido(tmp_path, relogio, setores):
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=True)
    setores[_UM] = "Setor Alfa"
    _cliente(app, _UM).get("/os/historico")
    U.salvar()
    antes = U.instantaneo()["setor"]
    U.limpar()
    U.ligar(_app(tmp_path, relogio), gravar=True)
    assert U.instantaneo()["setor"] == antes                             # o dia de hoje não recomeça do zero no reinício
    # arquivo corrompido: ignora e segue
    U.limpar()
    (tmp_path / "casca" / "uso_os_setor.json").write_text("{ quebrado", encoding="utf-8")
    U.ligar(_app(tmp_path, relogio), gravar=True)
    assert U.instantaneo()["setor"] == {}
    # só aproveita o que tem a forma certa
    U.limpar()
    (tmp_path / "casca" / "uso_os_setor.json").write_text(json.dumps({"dias": {
        "20261030": {"Setor Alfa": {"/os/x": {"cliques": 2, "automaticos": 1}, "/os/ruim": {"cliques": "dois"},
                                    "/os/ruim2": [1, 2]}, "Setor Ruim": "x"},
        "não-é-dia": {"Setor Alfa": {"/os/x": {"cliques": 1, "automaticos": 0}}}}}), encoding="utf-8")
    U.ligar(_app(tmp_path, relogio), gravar=True)
    assert U.instantaneo()["setor"] == {"20261030": {"Setor Alfa": {"/os/x": {"cliques": 2, "automaticos": 1}}}}


def test_setor_nao_conta_o_que_o_teto_recusou(tmp_path, relogio, setores):
    """O pedido recusado pelo teto não chegou ao Flask (sem sessão, sem setor): fica fora do corte por setor."""
    setores[_UM] = "Setor Alfa"
    app = _app(tmp_path, relogio)
    teto_os.ligar(app, teto=1, espera=0.05)
    U.ligar(app, gravar=False)
    preso = threading.Thread(target=lambda: _cliente(app, _UM).get("/os/api/lenta"))
    preso.start()
    for _ in range(300):
        if app.extensions[teto_os.CHAVE].estado()["em_uso"] == 1:
            break
        time.sleep(0.01)
    try:
        assert _cliente(app, _UM).get("/os/api/selo").status_code == 503
    finally:
        app.extensions["solta"].set()
        preso.join(5)
    assert U.instantaneo()["setor"] == {"20261030": {"Setor Alfa": {"/os/api/lenta": {"cliques": 1, "automaticos": 0}}}}


def test_setor_que_nao_se_acha_conta_sem_setor_e_o_pedido_segue(tmp_path, relogio, monkeypatch):
    from nexus.auth import setor_telas

    def quebra():
        raise RuntimeError("banco fora")
    monkeypatch.setattr(setor_telas, "acesso", quebra)
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=False)
    assert _cliente(app).get("/os/historico").status_code == 200
    assert U.instantaneo()["setor"] == {"20261030": {U.SEM_SETOR: {"/os/historico": {"cliques": 1, "automaticos": 0}}}}


def test_setores_e_rotas_do_corte_tem_teto(tmp_path, relogio, setores, monkeypatch):
    monkeypatch.setattr(U, "MAX_ROTAS", 2)
    monkeypatch.setattr(U, "MAX_SETORES", 2)
    app = _app(tmp_path, relogio)
    U.ligar(app, gravar=False)
    setores.update({_UM: "S1", _DOIS: "S2", _TRES: "S3"})
    for e in (_UM, _DOIS, _TRES):
        _cliente(app, e).get("/os/historico")
    for r in ("/os/a", "/os/b", "/os/c"):
        _cliente(app, _UM).get(r)
    corte = U.instantaneo()["setor"]["20261030"]
    assert set(corte) == {"S1", "S2", U.OUTRAS}                          # o 3º setor cai no balaio
    assert set(corte["S1"]) == {"/os/historico", "/os/a", U.OUTRAS}      # e a 3ª rota do setor também


# ── o servidor liga, o PC e os testes não ────────────────────────────────────────────────────────────────────────────
def test_o_servidor_liga_o_contador_e_o_uso():
    texto = (AQUI / "servir.py").read_text(encoding="utf-8")
    assert "fracttal_conta.ligar()" in texto and "uso_os.ligar(app, gravar=True)" in texto
    # o contador cedo, para pegar os laços que o instalar_* já abre; o uso depois do teto (é o teto que avisa o 503) e
    # antes dos presos (que ficam por fora de tudo)
    assert texto.index("fracttal_conta.ligar()") < texto.index("instalar_campo(app)")
    assert texto.index("teto_os.ligar(app") < texto.index("uso_os.ligar(") < texto.index("presos.ligar(app, THREADS)")


def test_o_pc_e_o_create_app_seguem_sem_o_uso():
    for arquivo in ("app.py", "nexus/__init__.py"):
        assert "uso_os" not in (AQUI / arquivo).read_text(encoding="utf-8"), arquivo


# ── as telas que se renovam sozinhas avisam que são automáticas ──────────────────────────────────────────────────────
WEB = AQUI / "nexus/torres/oscreator/os_creator/os_web"

_RODAR_ACOMP = r"""
const fs = require("fs");
let visto = null, timers = [];
const fonte = {getAttribute: (k) => (k === "data-quando" ? "22/10/2026 18:10:00" : null)};
global.document = {
  querySelector: (sel) => (sel === ".ac-fonte[data-renovando]" ? fonte : null),
  querySelectorAll: () => [], getElementById: () => null, addEventListener: () => {},
};
global.location = {reload: () => {}, pathname: "/", search: ""};
global.window = global;
global.OsCarga = {buscar: async () => ({})};
global.setInterval = (fn) => { timers.push(fn); return timers.length; };
global.clearInterval = () => {};
global.fetch = async (url, init) => {
  visto = {url, headers: (init && init.headers) || {}};
  return {ok: true, json: async () => ({quando: "22/10/2026 18:10:00", renovando: false})};
};
eval(fs.readFileSync(process.argv[1], "utf8"));
(async () => { await timers[0](); console.log(JSON.stringify(visto)); })();
"""

_RODAR_PEDIR = r"""
const fs = require("fs");
const visto = [];
global.window = global;
global.document = {};
global.OsCarga = {buscar: (url, op, texto) => {
  visto.push({url, auto: (op.headers || {})["X-Nexus-Auto"] || null});
  return Promise.resolve({ok: true, status: 200, json: async () => ({})});
}};
eval(fs.readFileSync(process.argv[1], "utf8"));
(async () => {
  const P = window.SolicPcm.pedir;
  await P("/os/api/solic/historico", undefined, "x", true);                    // a atualização de 15 min
  await P("/os/api/solic/historico", undefined, "x");                          // o ↻
  await P("/os/api/solic/historico", undefined, "x", {type: "click"});        // o evento do clique não vale
  await P("/os/api/solic/5001/status", {codigo: "X"}, "x");                    // uma gravação
  console.log(JSON.stringify(visto));
})();
"""


def _node(script, js):
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    r = subprocess.run(["node", "-e", script, str(js)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_acomp_pergunta_o_estado_como_automatico():
    visto = _node(_RODAR_ACOMP, WEB / "static" / "acomp.js")
    assert visto["url"] == "/os/chamados/acompanhamento/estado" and visto["headers"]["X-Nexus-Auto"] == "1"
    assert visto["headers"]["X-Requested-With"] == "fetch"               # o que já mandava segue


def test_solic_pcm_pedir_so_marca_quando_a_tela_pede_sozinha():
    visto = _node(_RODAR_PEDIR, WEB / "static" / "solic_pcm.js")
    assert [(v["url"], v["auto"]) for v in visto] == [
        ("/os/api/solic/historico", "1"), ("/os/api/solic/historico", None), ("/os/api/solic/historico", None),
        ("/os/api/solic/5001/status", None)]


def test_historico_de_solicitacoes_marca_so_os_15_minutos():
    js = (WEB / "static" / "solic_hist.js").read_text(encoding="utf-8")
    assert "function recarregar(auto)" in js
    assert "'Buscando as solicitações no Fracttal…', auto === true)" in js
    assert "addEventListener('click', function () { recarregar(false); })" in js          # o ↻ é clique
    assert "recarregar(true); }, 15 * 60 * 1000)" in js                                   # os 15 min são da tela
    # e a página chama os dois arquivos com a versão no endereço: sem ela o navegador seguia com o JavaScript de antes
    html = (WEB / "templates" / "solic_hist.html").read_text(encoding="utf-8")
    assert "{{ estatico('solic_pcm.js') }}" in html and "{{ estatico('solic_hist.js') }}" in html


def test_historico_de_os_marca_so_os_10_minutos():
    html = (WEB / "templates" / "historico.html").read_text(encoding="utf-8")
    assert "function enviar(forcar, auto)" in html
    assert "enviar(false, true);\n  }, 10 * 60 * 1000)" in html                           # os 10 min são da tela
    # um formulário não manda cabeçalho: a marca vai no endereço, só nesse envio, e sai do endereço depois de carregar
    assert 'name = "nx_auto"' in html and 'qa.delete("nx_auto")' in html and "history.replaceState" in html
    # todo outro envio (clique, F5, filtro) tira a marca antes de mandar, e só a atualização de 10 min a põe
    assert "else if (a) a.remove();" in html and html.count("enviar(false, true)") == 1


_RODAR_ENVIAR = r"""
// O DOM mínimo do formulário do Histórico: só os <input> escondidos que o `enviar` cria e tira.
const [fonteEnviar, fonteMarca] = JSON.parse(process.argv[1]);
const campos = [], enviados = [];
const novo = () => { const el = {name: "", value: "", type: ""}; el.remove = () => { const i = campos.indexOf(el); if (i >= 0) campos.splice(i, 1); }; return el; };
const form = {
  querySelector: (sel) => { const m = /name=(\w+)/.exec(sel); return campos.find((c) => c.name === m[1]) || null; },
  appendChild: (el) => { campos.push(el); },
  submit: () => { enviados.push(Object.fromEntries(campos.map((c) => [c.name, c.value]))); },
};
const document = {getElementById: () => ({value: ""}), createElement: novo};
const window = {OsCarga: {token: () => "tok", mostrar: () => {}}};
eval(fonteEnviar);                                   // a função `enviar` de verdade, tirada do template
enviar(false, true);                                 // a atualização de 10 min
enviar(false);                                       // um clique depois: a marca sai
enviar(true);                                        // o F5
enviar(false, true);                                 // e a de 10 min de novo: volta
const enderecos = [];
for (const [busca, hash] of [["?modo=criadas&nx_auto=1&p=abc", "#x"], ["?nx_auto=1", ""], ["?modo=cos", ""]]) {
  const location = {search: busca, pathname: "/os/historico", hash};
  const history = {replaceState: (a, b, url) => { enderecos.push(url); }};
  eval(fonteMarca);                                  // o começo da página, tirado do template
}
console.log(JSON.stringify({enviados, enderecos}));
"""


def test_historico_de_os_poe_a_marca_so_na_atualizacao_e_a_tira_do_endereco():
    """Roda o `enviar` e o começo da página do template de verdade (no node, com o formulário de mentira)."""
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    html = (WEB / "templates" / "historico.html").read_text(encoding="utf-8")
    enviar = html[html.index("function enviar(forcar, auto)"):html.index('  form.addEventListener("submit"')]
    marca = re.search(r"try \{\n    var qa .*?catch \(e\) \{[^\n]*\}\n", html, re.S).group(0)
    r = subprocess.run(["node", "-e", _RODAR_ENVIAR, json.dumps([enviar, marca])], capture_output=True, text=True,
                       encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    saida = json.loads(r.stdout.strip().splitlines()[-1])
    assert saida["enviados"] == [{"p": "tok", "nx_auto": "1"}, {"p": "tok"}, {"p": "tok"}, {"p": "tok", "nx_auto": "1"}]
    assert saida["enderecos"] == ["/os/historico?modo=criadas&p=abc#x", "/os/historico"]   # sem a marca, nada a trocar


def test_o_circulo_de_carga_avisa_que_e_automatico():
    js = (WEB / "static" / "carga.js").read_text(encoding="utf-8")
    pergunta = next(linha for linha in js.splitlines() if "/os/historico/progresso?p=" in linha)
    assert "'X-Nexus-Auto': '1'" in pergunta


def test_conferencia_da_sessao_avisa_que_e_automatica():
    html = (AQUI / "nexus/templates/_confere_sessao_js.html").read_text(encoding="utf-8")
    assert 'headers: {"X-Nexus-Auto": "1"}' in html
