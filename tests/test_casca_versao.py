"""A versão no ar no Início (13/10/2026, Levi: "Quero que no início do Nexus diga quando foi o último commit para eu
acompanhar se está realmente subindo automático para o server"). Nada vai ao GitHub: a conferência é dublada."""
import subprocess
from datetime import datetime

import pytest

from nexus import casca
from nexus.casca import versao

SHA = "648c1007e956e9faf6c465c1bd6402b1960beed0"


class _NaHora:
    """A thread da conferência roda na hora (o teste não espera nada por trás)."""
    def __init__(self, target, args=(), **k):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


@pytest.fixture
def estado(monkeypatch):
    def zera():
        versao._ESTADO.update(conferido_em=0.0, resultado=None, atras_desde=0.0, trabalhando=False)
    zera()
    monkeypatch.setattr(versao, "local", lambda: {"sha": SHA, "em": datetime(2026, 10, 13, 14, 45, tzinfo=versao._BRT),
                                                  "assunto": "fix(casca): a pré-carga ao subir espera 5 min"})
    monkeypatch.setattr(casca, "_commit", lambda: "648c100")
    monkeypatch.setattr(versao.threading, "Thread", _NaHora)
    yield
    zera()


def _main(sha="abc1234def", hora=15):
    return {"sha": sha, "em": datetime(2026, 10, 13, hora, 20, tzinfo=versao._BRT), "assunto": "feat: o commit novo"}


def test_inicio_mostra_a_hora_do_commit_e_desde_quando_esta_no_ar(app, logado, estado):
    html = logado.get("/").get_data(as_text=True)
    assert "Versão no ar" in html and "13/10 14:45" in html and "<code>648c100</code>" in html
    assert "no ar desde" in html and "fix(casca): a pré-carga ao subir espera 5 min" in html
    # nos testes a conferência com o GitHub fica desligada: nada sai para a rede
    assert 'data-versao="desligada"' in html and versao._ESTADO["resultado"] is None


def test_em_dia_com_o_github_fica_verde(app, logado, estado, monkeypatch):
    pedidos = []
    monkeypatch.setattr(versao, "_github", lambda sha, repo: pedidos.append((sha, repo)) or
                        {"situacao": "em_dia", "a_frente": 0, "atras": 0, "main": _main(SHA)})
    app.config["NEXUS_VERSAO_GITHUB"] = "1"
    html = logado.get("/").get_data(as_text=True)
    assert 'gc-status gc-status--ok' in html and "Em dia com o GitHub" in html and 'title="conferido às' in html
    assert pedidos == [(SHA, "Grid-Co-CODE/nexus")]
    logado.get("/")
    assert len(pedidos) == 1                    # vale 5 min: a página seguinte não vai ao GitHub de novo


def test_atras_atualiza_por_5_min_e_depois_fica_vermelho(app, logado, estado, monkeypatch):
    """O deploy automático roda a cada 2 min: atrás nos 5 primeiros minutos é "atualizando"; depois, "atrasado"."""
    monkeypatch.setattr(versao, "_github", lambda sha, repo: {"situacao": "atras", "a_frente": 0, "atras": 3,
                                                              "main": _main()})
    app.config["NEXUS_VERSAO_GITHUB"] = "1"
    html = logado.get("/").get_data(as_text=True)
    assert "gc-status--alerta" in html and "Atualizando" in html
    assert "O GitHub tem o abc1234, de 15:20 (3 commits à frente); o deploy automático leva até 3 min." in html
    versao._ESTADO["atras_desde"] -= 7 * 60
    html = logado.get("/").get_data(as_text=True)
    assert "gc-status--critico" in html and "Atrasado há 7 min" in html and "o deploy automático não pegou" in html


def test_o_relogio_do_atras_so_zera_em_dia(estado, monkeypatch):
    """Commit novo no GitHub com o servidor parado não volta a "atualizando"; GitHub fora do ar não zera o relógio."""
    respostas = iter([{"situacao": "atras", "atras": 1, "a_frente": 0, "main": _main("aaa")},
                      {"situacao": "atras", "atras": 2, "a_frente": 0, "main": _main("bbb")}])
    monkeypatch.setattr(versao, "_github", lambda sha, repo: next(respostas))
    versao._conferir("x/y")
    versao._ESTADO["atras_desde"] -= 600
    desde = versao._ESTADO["atras_desde"]
    versao._conferir("x/y")
    assert versao._ESTADO["atras_desde"] == desde

    def fora(sha, repo):
        raise RuntimeError("sem rede")
    monkeypatch.setattr(versao, "_github", fora)
    versao._conferir("x/y")
    assert versao._ESTADO["atras_desde"] == desde and versao._ESTADO["resultado"]["situacao"] == "sem_github"
    monkeypatch.setattr(versao, "_github", lambda sha, repo: {"situacao": "em_dia", "atras": 0, "a_frente": 0, "main": {}})
    versao._conferir("x/y")
    assert versao._ESTADO["atras_desde"] == 0.0 and versao._ESTADO["trabalhando"] is False


@pytest.mark.parametrize("r, rotulo, classe, detalhe", [
    ({"situacao": "a_frente", "a_frente": 2, "atras": 0}, "À frente do GitHub", "neutro", "2 commits só nesta máquina."),
    ({"situacao": "diferente", "a_frente": 1, "atras": 3}, "Diferente do GitHub", "critico",
     "1 commit só aqui e 3 commits só no GitHub."),
    ({"situacao": "fora"}, "Fora do GitHub", "neutro", "Este commit não está no GitHub (só nesta máquina)."),
    ({"situacao": "sem_github", "erro": "ConnectionError: x"}, "GitHub sem resposta", "neutro",
     "Não consegui conferir agora (ConnectionError: x)."),
])
def test_as_outras_situacoes(app, estado, r, rotulo, classe, detalhe):
    versao._ESTADO.update(resultado=dict(r, main={}), conferido_em=versao.time.time())
    app.config["NEXUS_VERSAO_GITHUB"] = "1"
    c = versao.cartao(app)
    assert (c["rotulo"], c["classe"], c["detalhe"]) == (rotulo, classe, detalhe)


def test_a_api_do_github_compare(monkeypatch):
    import requests

    class Resp:
        def __init__(self, codigo, j=None):
            self.status_code, self._j = codigo, j

        def json(self):
            return self._j

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(str(self.status_code))
    pedidos = []

    def get(url, **k):
        pedidos.append(url)
        if url.endswith("...fora"):
            return Resp(404)
        status = url.rsplit("...", 1)[1]
        return Resp(200, {"status": status, "ahead_by": 1, "behind_by": 2, "base_commit": {
            "sha": "abc", "commit": {"committer": {"date": "2026-10-13T18:20:00Z"}, "message": "feat: novo\n\ncorpo"}}})
    monkeypatch.setattr(requests, "get", get)
    r = versao._pela_api("behind", "Grid-Co-CODE/nexus")
    assert pedidos[0] == "https://api.github.com/repos/Grid-Co-CODE/nexus/compare/main...behind"
    assert r["situacao"] == "atras" and (r["atras"], r["a_frente"]) == (2, 1)
    assert r["main"]["em"].strftime("%d/%m %H:%M") == "13/10 15:20" and r["main"]["assunto"] == "feat: novo"
    assert [versao._pela_api(s, "r")["situacao"] for s in ("identical", "ahead", "diverged", "fora")] == \
        ["em_dia", "a_frente", "diferente", "fora"]


def test_sem_a_api_vai_pelo_git(monkeypatch):
    def api_fora(sha, repo):
        raise ConnectionError("api.github.com bloqueado")
    monkeypatch.setattr(versao, "_pela_api", api_fora)
    saidas = {"ls-remote": "bbb\trefs/heads/main", "log": "2026-10-13T15:20:00-03:00\x1ffeat: novo", "rev-list": "3\t0"}
    monkeypatch.setattr(versao, "_git", lambda *a, **k: saidas[a[0]])
    r = versao._github("aaa", "Grid-Co-CODE/nexus")
    assert r["situacao"] == "atras" and r["atras"] == 3 and r["main"]["sha"] == "bbb"
    saidas["rev-list"] = "0\t2"
    assert versao._github("aaa", "r")["situacao"] == "a_frente"
    saidas["ls-remote"] = "aaa\trefs/heads/main"
    monkeypatch.setattr(versao, "local", lambda: {"sha": "aaa", "em": None, "assunto": ""})
    assert versao._github("aaa", "r")["situacao"] == "em_dia"

    def sem_objeto(*a, **k):
        if a[0] == "ls-remote":
            return "ccc\trefs/heads/main"
        raise RuntimeError("fatal: bad object ccc")
    monkeypatch.setattr(versao, "_git", sem_objeto)
    assert versao._github("aaa", "r")["situacao"] == "atras"      # sem o objeto aqui: outro commit no GitHub = atrás

    def git_fora(*a, **k):
        raise subprocess.TimeoutExpired("git", 10)
    monkeypatch.setattr(versao, "_git", git_fora)
    with pytest.raises(RuntimeError, match="API: ConnectionError.*git: TimeoutExpired"):
        versao._github("aaa", "r")


def test_o_commit_local_pelo_git(monkeypatch):
    monkeypatch.setattr(versao, "_git", lambda *a, **k: f"{SHA}\x1f2026-10-13T17:45:37Z\x1ffix: assunto")
    lo = versao.local.__wrapped__()
    assert lo["sha"] == SHA and lo["em"].strftime("%d/%m %H:%M") == "13/10 14:45" and lo["assunto"] == "fix: assunto"

    def sem_git(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(versao, "_git", sem_git)
    assert versao.local.__wrapped__() == {"sha": "", "em": None, "assunto": ""}


def test_nos_testes_nada_sai_para_o_github(app, monkeypatch):
    def nao(*a, **k):
        raise AssertionError("a conferência não pode sair nos testes")
    monkeypatch.setattr(versao.threading, "Thread", nao)
    versao.conferir(app)                          # TESTING: desligada
    app.config["NEXUS_VERSAO_GITHUB"] = "0"
    app.config["TESTING"] = False
    versao.conferir(app)                          # a chave em 0 desliga também fora dos testes
