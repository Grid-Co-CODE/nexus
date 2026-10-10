"""Porta única: o passo 0 (cookie próprio) e o Nexus debaixo de um prefixo (09/10/2026).

Levi: "a partir de segunda quero o Nexus como link principal; o Nexus será o centro de tudo". No servidor o Nexus mora em
app.gridco.com.br/nexus, ao lado da plataforma de Performance na raiz; o menu, o Início, o Sair e os `fetch` saíam da raiz
e caíam na plataforma, e o cookie `session` dos dois se apagava (spec 2026-10-09, seção 5.1). Aqui se prova:
- o cookie `nexus_sessao` no caminho do prefixo (e o do OS Creator embutido em prefixo + /os), nos dois modos;
- o `NEXUS_PREFIXO` com o Caddy cortando o /nexus (o servidor de hoje), sem cortar, e um SCRIPT_NAME dado por outro meio;
- o rastreador: todas as páginas a partir do Início, logado como admin, com o OS Creator embutido, e nenhum endereço
  interno fora do prefixo (e, na raiz, nenhum com ele);
- a convivência com a camada da T.I. que hoje reescreve a resposta no servidor (nada sai com /nexus/nexus);
- o varredor estático: nenhum template, .js ou redirecionamento escrito a partir da raiz.
"""
import importlib.util
import os
import re
import socket
from pathlib import Path

import pytest
from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.test import Client

from nexus import create_app
from nexus.prefixo import Prefixo, PrefixoInvalido, na_raiz, normalizar, sem_raiz

from conftest import SENHA_TESTE
from rastreador_de_links import Rastreio, caminhos_do_html, caminhos_do_js

RAIZ = Path(__file__).resolve().parent.parent
PREFIXO = "/nexus"
JWT_DE_MENTIRA = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"


# ── as peças ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_normalizar():
    assert normalizar(None) == "" and normalizar("") == "" and normalizar("/") == "" and normalizar("  ") == ""
    assert normalizar("/nexus") == "/nexus" and normalizar("nexus/") == "/nexus" and normalizar("/a/b/") == "/a/b"
    for ruim in ("/ne xus", "/../x", "/a//b", "/x?y=1", "/x#y", "/./x"):
        with pytest.raises(PrefixoInvalido):
            normalizar(ruim)


def test_prefixo_invalido_nao_deixa_subir():
    with pytest.raises(PrefixoInvalido):
        create_app({"NEXUS_SECRET_KEY": "k", "NEXUS_SENHA_ADMIN": "s", "NEXUS_PREFIXO": "/a b"})


def _eco(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [f"{environ.get('SCRIPT_NAME')}|{environ.get('PATH_INFO')}".encode()]


@pytest.mark.parametrize("pedido, esperado", [
    ("/t/cos/mesa", "/nexus|/t/cos/mesa"),          # o Caddy cortou (handle_path, o servidor de hoje)
    ("/nexus/t/cos/mesa", "/nexus|/t/cos/mesa"),    # o Caddy não cortou
    ("/nexus", "/nexus|/"),
    ("/nexus/", "/nexus|/"),
    ("/nexusx", "/nexus|/nexusx"),                  # outro caminho que só começa igual não perde nada
])
def test_o_middleware_poe_o_prefixo_venha_ele_no_caminho_ou_nao(pedido, esperado):
    assert Client(Prefixo(_eco, "/nexus")).get(pedido).get_data(as_text=True) == esperado


def test_o_prefixo_vindo_de_fora_nao_vale():
    """O Caddy repassa cabeçalho do cliente: quem mandasse X-Forwarded-Prefix escolheria para onde links e cookie vão."""
    r = Client(_app(None)).get("/t/cos/mesa", headers={"X-Forwarded-Prefix": "/mal", "X-Script-Name": "/mal"})
    assert r.headers["Location"].startswith("/entrar?next=") and "/mal" not in r.headers["Location"]
    r = Client(_app()).get("/nexus/t/cos/mesa", headers={"X-Forwarded-Prefix": "/mal"})
    assert r.headers["Location"].startswith("/nexus/entrar?next=") and "/mal" not in r.headers["Location"]


def test_na_raiz_e_sem_raiz_sao_idempotentes():
    app = Flask(__name__)
    with app.test_request_context("/t/x", base_url="http://localhost/nexus/"):
        assert na_raiz("/t/pcm/gerar?x=1") == "/nexus/t/pcm/gerar?x=1"
        assert na_raiz("/nexus/t/x") == "/nexus/t/x"           # a camada da T.I. pode ter posto
        assert na_raiz("/") == "/nexus/"
        for igual in ("https://x.test/a", "//x.test/a", "?a=1", "#x", "", None):
            assert na_raiz(igual) == igual
        assert sem_raiz("/nexus/t/x") == "/t/x" and sem_raiz("/nexus") == "/" and sem_raiz("/nexus?a=1") == "/?a=1"
        assert sem_raiz("/t/x") == "/t/x" and sem_raiz("/nexusx/a") == "/nexusx/a"
    with app.test_request_context("/t/x"):
        assert na_raiz("/t/x") == "/t/x" and sem_raiz("/nexus/t/x") == "/nexus/t/x"


# ── o passo 0: cada sistema com o seu cookie ─────────────────────────────────────────────────────────────────────────
def _app(prefixo: str | None = PREFIXO, **extra):
    cfg = {"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE, **extra}
    if prefixo:
        cfg["NEXUS_PREFIXO"] = prefixo
    app = create_app(cfg)
    app.config["TESTING"] = True
    app.config["SESSION_COOKIE_SECURE"] = False
    return app


def _caddy_corta(app):
    """O Caddy do servidor de hoje: /nexus/* vai ao Nexus SEM o /nexus (handle_path); o resto é da plataforma."""
    def wsgi(environ, start_response):
        caminho = environ.get("PATH_INFO") or "/"
        if caminho == PREFIXO or caminho.startswith(PREFIXO + "/"):
            environ["PATH_INFO"] = caminho[len(PREFIXO):] or "/"
            return app(environ, start_response)
        start_response("599 PLATAFORMA", [("Content-Type", "text/plain")])
        return [b"isto seria a plataforma"]
    return wsgi


def _biscoitos(resp, nome):
    return [c for c in resp.headers.getlist("Set-Cookie") if c.startswith(nome + "=")]


@pytest.mark.parametrize("prefixo, caminho", [(PREFIXO, "/nexus"), (None, "/")])
def test_a_sessao_do_nexus_tem_nome_proprio_no_caminho_em_que_ele_roda(prefixo, caminho):
    app = _app(prefixo)
    cli = Client(_caddy_corta(app) if prefixo else app)
    r = cli.post((prefixo or "") + "/entrar", data={"senha": SENHA_TESTE})
    assert r.status_code == 302 and r.headers["Location"] == (prefixo or "") + "/"
    assert not _biscoitos(r, "session")                     # o nome da plataforma: os dois se apagavam
    (biscoito,) = _biscoitos(r, "nexus_sessao")
    assert f"Path={caminho};" in biscoito and "HttpOnly" in biscoito
    assert cli.get((prefixo or "") + "/").status_code == 200


def test_a_sessao_da_plataforma_nao_derruba_a_do_nexus():
    """O defeito de antes: entrar na plataforma (cookie `session` em /) apagava a sessão do Nexus."""
    app = _app()
    cli = Client(_caddy_corta(app))
    cli.post("/nexus/entrar", data={"senha": SENHA_TESTE})
    cli.set_cookie("session", "o-da-plataforma", path="/")
    assert cli.get("/nexus/t/cos/mesa").status_code == 200


def _sessoes_apagadas(resp, nome="nexus_sessao"):
    return sorted(c.split("Path=")[1].split(";")[0] for c in _biscoitos(resp, nome)
                  if c.startswith(nome + "=;") or "Max-Age=0" in c or "1970" in c)


def test_depois_de_por_o_prefixo_o_sair_apaga_tambem_a_sessao_velha_da_raiz():
    """Revisão de 10/10/2026. O DEPLOY 5a sobe o código antes e põe a NEXUS_PREFIXO depois. Entre os dois, quem entra
    recebe nexus_sessao em Path=/ (atrás do Caddy que corta o /nexus, a raiz é ''); depois, o Nexus grava em Path=/nexus,
    mas o cookie velho continua indo a /nexus/* e continua válido (mesma NEXUS_SECRET_KEY, 12 h). O Sair apagava só o de
    /nexus: a pessoa seguia logada, talvez como admin, e num PC de campo o próximo entrava com a sessão do anterior."""
    cli = Client(_caddy_corta(_app(None)))                  # passo 1: o código novo, ainda sem NEXUS_PREFIXO
    r = cli.post("/nexus/entrar", data={"senha": SENHA_TESTE})
    assert r.status_code == 302 and "Path=/;" in _biscoitos(r, "nexus_sessao")[0] + ";"
    cli.application = _caddy_corta(_app(PREFIXO))           # passo 2: NEXUS_PREFIXO=/nexus e reinício
    assert cli.post("/nexus/cadeira", data={"cadeira": "", "voltar": "/"}).status_code == 302
    r = cli.get("/nexus/sair")
    assert _sessoes_apagadas(r) == ["/", "/nexus"]
    r = cli.get("/nexus/t/cos/mesa")
    assert r.status_code == 302 and r.headers["Location"].startswith("/nexus/entrar")


def test_entrar_debaixo_do_prefixo_apaga_a_sessao_velha_da_raiz():
    """O mesmo cookie velho de Path=/ sai também quando a pessoa entra (senão ele volta a valer quando o novo sai)."""
    cli = Client(_caddy_corta(_app(None)))
    cli.post("/nexus/entrar", data={"senha": SENHA_TESTE})
    cli.application = _caddy_corta(_app(PREFIXO))
    r = cli.post("/nexus/entrar", data={"senha": SENHA_TESTE})
    assert r.status_code == 302 and _sessoes_apagadas(r) == ["/"]
    # na raiz (o PC, a fase 4) o cookie da raiz é o da sessão: nada é apagado ao entrar
    raiz = Client(_app(None))
    r = raiz.post("/entrar", data={"senha": SENHA_TESTE})
    assert _sessoes_apagadas(r) == []


@pytest.mark.parametrize("prefixo", [PREFIXO, None])
def test_o_login_do_fracttal_abre_o_os_creator_no_os_do_nexus(prefixo, monkeypatch):
    from nexus.auth import fracttal
    monkeypatch.setattr(fracttal, "entrar", lambda app, e, s: {"email": e, "nome": "Pessoa Teste", "perfil": "",
                                                                  "cookie": ("os_sessao", "valor-assinado", 3600)})
    app = _app(prefixo)
    cli = Client(_caddy_corta(app) if prefixo else app)
    p = prefixo or ""
    r = cli.post(p + "/entrar?next=" + p + "/os/", data={"email": "pessoa@exemplo.test", "senha": "x"})
    assert r.headers["Location"] == p + "/os/"
    (os_sessao,) = _biscoitos(r, "os_sessao")
    assert f"Path={p}/os;" in os_sessao
    sair = cli.get(p + "/sair")
    assert sair.headers["Location"] == p + "/entrar"
    assert any(f"Path={p}/os" in c for c in _biscoitos(sair, "os_sessao"))      # apaga no mesmo caminho
    assert any(f"Path={p or '/'};" in c for c in _biscoitos(sair, "nexus_sessao"))


def test_o_portao_e_o_entrar_voltam_para_a_tela_debaixo_do_prefixo():
    app = _app()
    cli = Client(_caddy_corta(app))
    r = cli.get("/nexus/t/cos/mesa?x=1")
    assert r.headers["Location"] == "/nexus/entrar?next=/nexus/t/cos/mesa?x%3D1"
    html = cli.get(r.headers["Location"]).get_data(as_text=True)
    assert 'action="/nexus/entrar?next=/nexus/t/cos/mesa%3Fx%3D1"' in html
    assert 'href="/nexus/entrar?admin=1&amp;next=' in html or 'href="/nexus/entrar?admin=1&next=' in html
    r = cli.post("/nexus/entrar?next=%2Fnexus%2Ft%2Fcos%2Fmesa%3Fx%3D1", data={"senha": SENHA_TESTE})
    assert r.headers["Location"] == "/nexus/t/cos/mesa?x=1"
    # o next que a camada da T.I. não reescreveu (sem o prefixo) também volta ao lugar certo, e o de fora não sai
    for nxt, destino in (("/t/cos/mesa", "/nexus/t/cos/mesa"), ("https://mal.exemplo/", "/nexus/"),
                         ("//mal.exemplo/", "/nexus/")):
        cli.get("/nexus/sair")
        assert cli.post("/nexus/entrar", query_string={"next": nxt}, data={"senha": SENHA_TESTE}).headers["Location"] \
            == destino


def test_cadeira_e_tema_voltam_para_a_tela_debaixo_do_prefixo():
    app = _app()
    cli = Client(_caddy_corta(app))
    cli.post("/nexus/entrar", data={"senha": SENHA_TESTE})
    assert cli.post("/nexus/cadeira", data={"cadeira": "pcm", "voltar": "/t/pcm/semana"}).headers["Location"] \
        == "/nexus/t/pcm/semana"
    assert cli.post("/nexus/tema", data={"tema": "claro", "voltar": "/t/pcm/semana?x=1"}).headers["Location"] \
        == "/nexus/t/pcm/semana?x=1"


def test_o_javascript_recebe_o_prefixo():
    app = _app()
    cli = Client(_caddy_corta(app))
    cli.post("/nexus/entrar", data={"senha": SENHA_TESTE})
    html = cli.get("/nexus/").get_data(as_text=True)
    assert 'window.NEXUS_RAIZ = "/nexus";' in html and "window.nexusRota = function" in html
    raiz = Client(_app(None))
    raiz.post("/entrar", data={"senha": SENHA_TESTE})
    assert 'window.NEXUS_RAIZ = "";' in raiz.get("/").get_data(as_text=True)


def test_nexus_rota_no_navegador_e_idempotente():
    """A função do _raiz_js.html no node: com a camada da T.I. ainda reescrevendo "/t/..." para "/nexus/t/...", o caminho
    não ganha outro prefixo."""
    import json
    import shutil
    import subprocess
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    js = (RAIZ / "nexus/templates/_raiz_js.html").read_text(encoding="utf-8")
    js = re.sub(r"\{#.*?#\}", "", js, flags=re.S).replace("{{ (raiz or '')|tojson }}", "process.argv[1]")
    script = "var window = {};" + js + """
var r = window.nexusRota; window.nexusRota = r;
console.log(JSON.stringify([r('/t/x'), r('/nexus/t/x'), r('/nexus'), r('/nexus?a=1'), r('https://a.test/x'), r('//a/x'),
                            r('?a=1'), r('/nexusx/a')]));"""
    com = json.loads(subprocess.run(["node", "-e", script, "/nexus"], capture_output=True, text=True, timeout=30).stdout)
    assert com == ["/nexus/t/x", "/nexus/t/x", "/nexus", "/nexus?a=1", "https://a.test/x", "//a/x", "?a=1",
                   "/nexus/nexusx/a"]
    sem = json.loads(subprocess.run(["node", "-e", script, ""], capture_output=True, text=True, timeout=30).stdout)
    assert sem == ["/t/x", "/nexus/t/x", "/nexus", "/nexus?a=1", "https://a.test/x", "//a/x", "?a=1", "/nexusx/a"]


# ── o rastreador: todas as páginas, nos três modos ────────────────────────────────────────────────────────────────────
@pytest.fixture
def sem_rede(monkeypatch):
    """Nada sai da máquina: Fracttal, banco, INMET/INPE e NASA respondem "fora" e as telas mostram o aviso delas."""
    def recusa(*_a, **_k):
        raise OSError("rede bloqueada no teste do prefixo")
    monkeypatch.setattr(socket.socket, "connect", recusa)
    monkeypatch.setattr(socket.socket, "connect_ex", recusa)
    monkeypatch.setattr(socket, "create_connection", recusa)


def _app_com_dados(tmp_path, prefixo, **extra):
    """O app com um cadastro de mentira (as telas da Base com linhas e fichas, e os links delas) e a pasta de dados
    num diretório temporário."""
    from nexus.cadastro.cifra import gerar_chave
    from nexus.cadastro.servico import Carga
    from nexus.cadastro.telas import servico
    app = _app(prefixo, NEXUS_CHAVE_CADASTRO=gerar_chave(), NEXUS_ARMAZEM_LOCAL=str(tmp_path / "cadastro.json"),
               NEXUS_DADOS=str(tmp_path), **extra)
    with app.app_context():
        servico().aplicar_carga(Carga(
            entidades={
                "equipes": [{"id": "E-001", "ordem": 1, "valores": {"nome": "Equipe Teste 01"}}],
                "pessoas": [{"id": "P-0001", "ordem": 1, "valores": {
                    "nome": "Pessoa Teste", "cargo": "Técnico O&M", "equipe": "E-001", "status": "Ativo",
                    "vinculo": "Colaborador de campo"}}],
                "clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Cliente Teste"}}],
                "usinas": [{"id": "1", "ordem": 1, "valores": {
                    "nome": "Usina Teste", "status": "OPERAÇÃO", "equipe": "E-001", "cidade": "Cidade Teste",
                    "uf": "SP", "pais": "Brasil", "cliente": "1", "id_bd": "UFV-001"}}],
            },
            listas={"status_usina": ["OPERAÇÃO"], "uf": ["SP"], "cargos": ["Técnico O&M"],
                    "status_contratacao": ["Ativo"], "vinculo": ["Colaborador de campo"]},
        ))
    return app


def _logar(cli, app, p):
    """Admin pela senha, e o cookie do OS Creator como o login do Fracttal o deixa (JWT de mentira): o OS Creator
    embutido abre as telas dele em vez do login."""
    assert cli.post(p + "/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    from nexus.torres.oscreator import ponte
    clone = ponte.clone(app)
    valor = clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": JWT_DE_MENTIRA, "conta": {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid"}})
    cli.set_cookie("os_sessao", valor, path=p + "/os")


def _rastrear(cli, p):
    rs = Rastreio(cli, p).percorrer(p + "/")
    erros = {u: s for u, s in rs.visitados.items() if s >= 500}
    assert not erros, erros
    # a cobertura não pode cair em silêncio: as 13 torres, o cadastro com fichas e o OS Creator embutido
    assert len(rs.visitados) >= 120, len(rs.visitados)
    for preciso in ("/t/base/usina/1", "/t/pessoas/colaborador/P-0001", "/t/os/inicio", "/os/", "/os/historico",
                    "/os/static/abas.js", "/t/performance/clima/mapa", "/t/campo/rondas/avulsa"):
        assert p + preciso in rs.visitados, preciso
    return rs


def test_debaixo_do_prefixo_com_o_caddy_cortando_todo_endereco_sai_com_ele(tmp_path, sem_rede):
    app = _app_com_dados(tmp_path, PREFIXO)
    cli = Client(_caddy_corta(app))
    _logar(cli, app, PREFIXO)
    rs = _rastrear(cli, PREFIXO)
    assert rs.ruins == [], sorted(set(rs.ruins))[:30]


def test_debaixo_do_prefixo_sem_o_caddy_cortar_e_igual(tmp_path, sem_rede):
    app = _app_com_dados(tmp_path, PREFIXO)
    cli = Client(app)
    _logar(cli, app, PREFIXO)
    rs = _rastrear(cli, PREFIXO)
    assert rs.ruins == [], sorted(set(rs.ruins))[:30]


def test_com_o_script_name_dado_por_outro_meio_tambem(tmp_path, sem_rede):
    """Sem NEXUS_PREFIXO, montado num DispatcherMiddleware (SCRIPT_NAME=/nexus): links e cookies seguem o pedido."""
    app = _app_com_dados(tmp_path, None)
    cli = Client(DispatcherMiddleware(_eco, {PREFIXO: app}))
    r = cli.post(PREFIXO + "/entrar", data={"senha": SENHA_TESTE})
    assert r.headers["Location"] == "/nexus/" and "Path=/nexus;" in _biscoitos(r, "nexus_sessao")[0]
    _logar(cli, app, PREFIXO)
    rs = _rastrear(cli, PREFIXO)
    assert rs.ruins == [], sorted(set(rs.ruins))[:30]


def test_na_raiz_nada_ganha_o_prefixo(tmp_path, sem_rede):
    app = _app_com_dados(tmp_path, None)
    cli = Client(app)
    _logar(cli, app, "")
    rs = _rastrear(cli, "")
    assert rs.ruins == [], sorted(set(rs.ruins))[:30]


@pytest.mark.parametrize("prefixo", [PREFIXO, None])
def test_com_a_porta_da_performance_ligada_tambem(tmp_path, sem_rede, prefixo):
    """Porta única (09/10/2026): com a NEXUS_SSO_CHAVE as telas da Performance viram molduras, e elas escrevem endereços
    da PLATAFORMA (o formulário do passe, "Abrir em outra aba") na raiz de propósito: no servidor a plataforma mora na
    raiz. O rastreador separa esses (da_plataforma) e continua sem achar endereço do Nexus fora do prefixo."""
    from nexus.performance import porta
    app = _app_com_dados(tmp_path, prefixo, NEXUS_SSO_CHAVE="c" * 40)
    cli = Client(_caddy_corta(app) if prefixo else app)
    p = prefixo or ""
    _logar(cli, app, p)
    rs = _rastrear(cli, p)
    assert rs.ruins == [], sorted(set(rs.ruins))[:30]
    # o rastreador não segue ".../relatorio" (é o nome dos downloads): essas telas passam por ele uma a uma
    from rastreador_de_links import Rastreio
    da_plataforma = list(rs.da_plataforma)
    for t in porta.MAPA:
        url = f"{p}/t/{t.torre}/{t.tela}"
        if url not in rs.visitados:
            um = Rastreio(cli, p, limite=1).percorrer(url)
            assert um.visitados == {url: 200} and um.ruins == [], (t, um.ruins)
            da_plataforma += um.da_plataforma
        else:
            assert rs.visitados[url] == 200, t
    vistos = {(onde, c) for _, onde, c in da_plataforma}
    assert ("action", "/painel/nexus/entrar") in vistos and ("href", "/tempo-real") in vistos
    assert not any(c.startswith("/nexus") for _, c in vistos)


def test_o_rastreador_pega_o_endereco_esquecido():
    """O rastreador não pode passar tudo: um href, um action, um data-url, um fetch e um Location da raiz aparecem."""
    pagina = ('<a href="/t/x">a</a><form action="/sair"></form><div data-url="/os/x"></div><a href="/nexus/t/ok"></a>'
              '<a href="https://fora.test/x"></a><a href="?a=1"></a><script>fetch("/t/pcm/x"); fetch(nexusRota("/t/ok"));'
              "var v = '/os/_nexus/voltar?para=';</script>")
    achados = list(caminhos_do_html(pagina))
    assert ("href", "/t/x") in achados and ("action", "/sair") in achados and ("data-url", "/os/x") in achados
    assert ("js", "/t/pcm/x") in achados and not any(c == "/t/ok" for _, c in achados)
    assert not any("fora.test" in c or c.startswith("?") for _, c in achados)
    assert list(caminhos_do_js("location.href = '/entrar';")) == [("js", "/entrar")]

    def falso(environ, start_response):
        if environ["PATH_INFO"] == "/nexus/":
            start_response("200 OK", [("Content-Type", "text/html")])
            return [b'<a href="/nexus/t/y">ok</a><a href="/t/z">ruim</a>']
        start_response("302 Found", [("Location", "/t/w")])
        return [b""]
    rs = Rastreio(Client(falso), PREFIXO).percorrer("/nexus/")
    assert ("/nexus/", "href", "/t/z") in rs.ruins and ("/nexus/t/y", "Location", "/t/w") in rs.ruins


# ── o OS Creator embutido debaixo do prefixo (a ponte reescreve; o clone fica igual ao do oem) ─────────────────────────
def _clone_js():
    from nexus.torres.oscreator import ponte
    return sorted(p.name for p in (Path(ponte.RAIZ_CLONE) / "os_web" / "static").glob("*.js"))


@pytest.mark.parametrize("prefixo", [PREFIXO, None])
def test_todo_js_do_clone_sai_com_o_prefixo_e_na_raiz_sai_igual(prefixo, sem_rede):
    from nexus.torres.oscreator import ponte
    app = _app(prefixo)
    cli = Client(_caddy_corta(app) if prefixo else app)
    p = prefixo or ""
    _logar(cli, app, p)
    nomes = _clone_js()
    assert "abas.js" in nomes and len(nomes) >= 15
    for nome in nomes:
        r = cli.get(f"{p}/os/static/{nome}")
        assert r.status_code == 200, nome
        corpo = r.get_data()
        original = (Path(ponte.RAIZ_CLONE) / "os_web" / "static" / nome).read_bytes()
        if prefixo:
            assert not re.search(rb"""[\"'`(]/os(?=[/\"'`?#)])""", corpo), nome
            # nem nas expressões regulares (revisão de 10/10/2026: /^\/os\/.../ do abas.js e do carga.js ficavam sem o
            # prefixo, e debaixo do /nexus as abas do OS Creator embutido paravam de funcionar)
            assert rb"^\/os" not in corpo, nome
            assert corpo.count(b"/nexus/os") >= original.count(b"'/os") + original.count(b'"/os'), nome
            # a pergunta "mudou?" é sobre a versão reescrita: com a marca dela, 304; com a do original, o arquivo novo
            marca = r.headers["ETag"]
            assert cli.get(f"{p}/os/static/{nome}", headers={"If-None-Match": marca}).status_code == 304
        elif nome != "abas.js":
            assert corpo == original, nome                   # na raiz, byte a byte o de sempre


def _regras_das_abas(js: str, p: str) -> dict:
    """As regras puras do abas.js (como a ponte o serve) rodadas no node, com os caminhos debaixo de `p`."""
    import json
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(js)
    base = "http://h.test" + p + "/os/"
    script = """
var window = {}; require(process.argv[1]);
var P = window.OsAbas.puro, p = process.argv[2], base = process.argv[3];
var tabela = [[p + "/os/historico", "hist"], [p + "/os/ativos", "ativos"]];
var em = {pathname: p + "/os/historico", search: ""};
process.stdout.write(JSON.stringify({
  ehTela: [P.ehTela(p + "/os/historico"), P.ehTela(p + "/os/api/x"), P.ehTela(p + "/os/login"), P.ehTela(p + "/os/")],
  normalizar: P.normalizar(p + "/os/historico?x=1&solo=1", base),
  abaDoEndereco: P.abaDoEndereco("?aba=" + encodeURIComponent(p + "/os/historico"), base),
  secao: [P.secaoDe(p + "/os/historico", tabela), P.secaoDe(p + "/os/clonar", []), P.secaoDe(p + "/os/", [])],
  destino: [P.destino({href: p + "/os/ativos", target: "", botao: 0}, em, tabela, base),
            P.destino({href: p + "/os/login", target: "", botao: 0}, em, tabela, base),
            P.destino({href: p + "/os/", target: "", botao: 0}, em, tabela, base),
            P.destino({href: p + "/os/historico?y=2", target: "", botao: 0}, em, tabela, base),
            P.destino({href: "/tempo-real", target: "", botao: 0}, em, tabela, base)],
}));
"""
    try:
        r = subprocess.run(["node", "-e", script, f.name, p, base], capture_output=True, text=True, encoding="utf-8",
                           timeout=60)
    finally:
        os.unlink(f.name)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_as_abas_do_os_creator_funcionam_debaixo_do_prefixo(sem_rede):
    r"""Revisão de 10/10/2026: a ponte punha o prefixo em "/os, '/os, `/os e (/os, mas não nas expressões regulares do
    clone (/^\/os\/[^/]/ e afins). Debaixo do /nexus o location.pathname é /nexus/os/...: ehTela dava false, normalizar e
    abaDoEndereco null e destino() 'seguir' onde devia 'abrir' ou 'topo'. Todo item da torre OS Creator abria o Início, os
    cartões não abriam aba e o "Clonar esta OS" caía no Início. Na raiz, nada muda."""
    respostas = {}
    for prefixo in (PREFIXO, None):
        app = _app(prefixo)
        cli = Client(_caddy_corta(app) if prefixo else app)
        p = prefixo or ""
        _logar(cli, app, p)
        respostas[p] = _regras_das_abas(cli.get(f"{p}/os/static/abas.js").get_data(as_text=True), p)
    raiz = respostas[""]
    assert raiz["ehTela"] == [True, False, False, False] and raiz["destino"] == ["abrir", "topo", "inicio", "seguir", "topo"]
    assert raiz["normalizar"] == "/os/historico?x=1" and raiz["abaDoEndereco"] == "/os/historico"
    no_prefixo = respostas[PREFIXO]
    assert no_prefixo["ehTela"] == raiz["ehTela"] and no_prefixo["destino"] == raiz["destino"]
    assert no_prefixo["secao"] == raiz["secao"] == ["hist", "outra:clonar", "inicio"]
    assert no_prefixo["normalizar"] == PREFIXO + raiz["normalizar"]
    assert no_prefixo["abaDoEndereco"] == PREFIXO + raiz["abaDoEndereco"]


def test_o_login_do_clone_volta_para_a_tela_sem_o_prefixo_no_next(sem_rede):
    """O clone só devolve para /os/...: o `next` que chega com o prefixo sai dele antes, e o do formulário fica sem."""
    app = _app()
    cli = Client(_caddy_corta(app))
    cli.post("/nexus/entrar", data={"senha": SENHA_TESTE})
    r = cli.get("/nexus/os/historico")
    assert r.headers["Location"] == "/nexus/os/login?next=%2Fos%2Fhistorico"
    for nxt in ("/nexus/os/historico", "/os/historico"):
        html = cli.get("/nexus/os/login", query_string={"next": nxt}).get_data(as_text=True)
        assert 'name="next" value="/os/historico"' in html, nxt
        assert 'action="/nexus/os/login' in html or "/nexus/os/login" in html


def test_o_card_da_os_debaixo_do_prefixo(sem_rede):
    app = _app()
    cli = Client(_caddy_corta(app))
    _logar(cli, app, PREFIXO)
    h = cli.get("/nexus/os/_nexus/card/9001?status=Em%20Processo&de=/nexus/t/engenharia/equipe").get_data(as_text=True)
    assert 'data-fragmento="/nexus/os/os/9001?parcial=1&amp;status=Em+Processo"' in h
    assert 'data-pagina="/nexus/os/os/9001?status=Em+Processo"' in h
    for peca in ('<script src="/nexus/os/static/os_acoes.js">', 'href="/nexus/os/static/os.css"'):
        assert peca in h, peca
    # o "Clonar esta OS" do card: o endereço do clone chega com o prefixo e a torre OS Creator o abre numa aba
    r = cli.get("/nexus/os/_nexus/ir", query_string={"url": "/nexus/os/clonar?folio=15000"})
    assert r.headers["Location"] == "/nexus/t/os/clonagem?abrir=%2Fos%2Fclonar%3Ffolio%3D15000"
    h = cli.get(r.headers["Location"]).get_data(as_text=True)
    assert 'src="/nexus/os/clonar?folio=15000"' in h
    # o menu da torre (abre a tela como aba na casca já aberta): chave e endereço com o prefixo
    assert '"/nexus/t/os/clonagem": {' in h and '"url": "/nexus/os/clonar"' in h


def test_a_assinatura_da_pt_volta_para_a_tela_debaixo_do_prefixo():
    app = _app()
    cli = Client(_caddy_corta(app))
    cli.post("/nexus/entrar", data={"senha": SENHA_TESTE})
    r = cli.get("/nexus/os/_nexus/voltar", query_string={"para": "/nexus/t/campo/aprovacao?x=1"})
    assert r.headers["Location"] == "/nexus/t/campo/aprovacao?x=1"
    assert cli.get("/nexus/os/_nexus/voltar", query_string={"para": "/nexus/t/base/x"}).headers["Location"] \
        == "/nexus/t/campo/aprovacao"
    j = cli.get("/nexus/os/_nexus/pt/PT-1/assinatura-tecnico").get_json()
    assert j["entrar"] == "/nexus/os/login?next=%2Fos%2F_nexus%2Fpt%2FPT-1%2Fvoltar"


def test_a_ponte_do_tempo_real_leva_o_prefixo_a_plataforma(monkeypatch):
    """A ponte de 04/10 (até a Operação em tempo real entrar): a plataforma escreve os links com o X-Forwarded-Prefix, e o
    guarda de leitura compara com o mesmo caminho; debaixo do /nexus os dois levam o prefixo."""
    from nexus.performance import ponte

    class _Resp:
        status_code, content = 200, b"<html><head></head><body></body></html>"
        headers = {"Content-Type": "text/html; charset=utf-8", "X-Nexus-Leitura-Ok": "1"}
    visto = {}
    monkeypatch.setattr(ponte, "enviar", lambda **p: visto.update(p) or _Resp())
    app = _app(NEXUS_PLATAFORMA_URL="https://plat.test", NEXUS_PLATAFORMA_TOKEN="chave-de-teste")
    cli = Client(_caddy_corta(app))
    cli.post("/nexus/entrar", data={"senha": SENHA_TESTE})
    assert 'src="/nexus/t/performance/plataforma/tempo-real"' in cli.get("/nexus/t/performance/tempo-real").get_data(
        as_text=True)
    corpo = cli.get("/nexus/t/performance/plataforma/tempo-real").get_data(as_text=True)
    assert visto["headers"]["X-Forwarded-Prefix"] == "/nexus/t/performance/plataforma"
    assert ',P="/nexus/t/performance/plataforma"' in corpo          # o guarda de leitura (ponte._GUARDA)


# ── a convivência com a camada da T.I. (ela reescreve a resposta no servidor de hoje) ─────────────────────────────────
def _porta_local():
    spec = importlib.util.spec_from_file_location("porta_local", RAIZ / "ferramentas" / "porta_local.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_com_a_reescrita_do_servidor_ligada_nada_sai_com_o_prefixo_dobrado(tmp_path, sem_rede):
    """A ordem do deploy: o código sobe, a T.I. põe NEXUS_PREFIXO=/nexus e só depois desliga a reescrita dela. No meio,
    as duas valem juntas: nada pode sair /nexus/nexus (o JavaScript passa pelo nexusRota, que também não dobra)."""
    pl = _porta_local()
    app = _app_com_dados(tmp_path, PREFIXO)
    corta = _caddy_corta(app)

    def com_a_camada(environ, start_response):
        guardado = {}

        def pega(status, cabecalhos, exc=None):
            guardado["s"], guardado["h"] = status, cabecalhos
        corpo = b"".join(corta(environ, pega))
        tipo = dict(guardado["h"]).get("Content-Type", "")
        if "text/html" in tipo or "javascript" in tipo:
            corpo = pl.reescreve_corpo(corpo.decode("utf-8"), "text/html" in tipo).encode("utf-8")
        cab = [(k, pl.reescreve_location(v) if k.lower() == "location" else v) for k, v in guardado["h"]
               if k.lower() != "content-length"] + [("Content-Length", str(len(corpo)))]
        start_response(guardado["s"], cab)
        return [corpo]

    cli = Client(com_a_camada)
    _logar(cli, app, PREFIXO)
    rs = Rastreio(cli, PREFIXO).percorrer(PREFIXO + "/")
    assert len(rs.visitados) >= 120
    dobrados = [u for u in rs.visitados if "/nexus/nexus" in u] + [d for _, d in rs.redirecionamentos if "/nexus/nexus" in d]
    assert dobrados == []
    for url in ("/nexus/", "/nexus/t/os/inicio", "/nexus/os/", "/nexus/t/base/usina/1"):
        assert b"/nexus/nexus" not in cli.get(url).get_data(), url


# ── o varredor estático: o que o rastreador não alcança (telas que só desenham o link com dado do banco) ─────────────
_PASTAS = [RAIZ / "nexus"]
_FORA = ("os_creator",)                                # o clone do oem: a ponte reescreve (testes acima)


def _arquivos(sufixo):
    for pasta in _PASTAS:
        for arq in pasta.rglob("*" + sufixo):
            if not any(p in arq.parts for p in _FORA):
                yield arq


def _sem_comentarios_jinja(texto):
    return re.sub(r"\{#.*?#\}", "", re.sub(r"<!--.*?-->", "", texto, flags=re.S), flags=re.S)


def test_nenhum_template_escreve_endereco_a_partir_da_raiz():
    """Todo href/src/action/data-* absoluto começa por {{ raiz }}, sai do url_for ou passa pelo |na_raiz."""
    ruins = []
    atributo = re.compile(r'\s(href|src|action|formaction|poster|data-[\w-]+)="(/[^/"][^"]*|\{\{[^}]*\}\}[^"]*)"')
    for arq in _arquivos(".html"):
        texto = _sem_comentarios_jinja(arq.read_text(encoding="utf-8"))
        for m in atributo.finditer(texto):
            valor = m.group(2)
            if valor.startswith("/"):
                ruins.append(f"{arq.relative_to(RAIZ)}: {m.group(0).strip()}")
            elif not re.match(r"\{\{\s*(raiz\b|url_for\(|url\(|\(?[^}]*\|\s*na_raiz)", valor) \
                    and m.group(1) in ("href", "src", "action", "formaction") \
                    and "plataforma" not in valor:            # o "Abrir na plataforma": URL completa, de outro sistema
                ruins.append(f"{arq.relative_to(RAIZ)}: {m.group(0).strip()}")
    assert ruins == []


def test_nenhum_javascript_escreve_caminho_do_nexus_sem_o_nexus_rota():
    ruins = []
    for arq in list(_arquivos(".html")) + list(_arquivos(".js")):
        texto = _sem_comentarios_jinja(arq.read_text(encoding="utf-8"))
        partes = [m.group(2) for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", texto, re.S)] \
            if arq.suffix == ".html" else [texto]
        for js in partes:
            sem_comentario = re.sub(r"(?<![:'\"])//[^\n]*|/\*.*?\*/", "", js, flags=re.S)
            ruins += [f"{arq.relative_to(RAIZ)}: {c}" for _, c in caminhos_do_js(sem_comentario)]
    assert ruins == []


def test_nenhum_redirecionamento_do_python_sai_da_raiz():
    """redirect("/t/...") cru levava à plataforma debaixo do /nexus: passa pelo na_raiz (ou url_for/destino_seguro)."""
    ruins = []
    for arq in _arquivos(".py"):
        for i, linha in enumerate(arq.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"""redirect\(\s*f?["']/""", linha):
                ruins.append(f"{arq.relative_to(RAIZ)}:{i}: {linha.strip()}")
    assert ruins == []
