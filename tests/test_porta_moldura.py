"""Porta única (09/10/2026): as telas da Plataforma de Performance numa moldura do Nexus (nexus/torres/moldura.py).

Levi: "a partir de segunda quero o Nexus como link principal; o Nexus será o centro de tudo, precisamos trazer o tempo
real de performance painel para o Nexus". Aqui se prova o lado Nexus da spec 2026-10-09 (seções 5.2, 5.5 a 5.7 e 7):
- cada tela do mapa abre a moldura com o formulário certo (POST do passe a /painel/nexus/entrar, alvo na moldura);
- o passe muda a cada abertura, vence em 60 s e diz quem é (e-mail, nome, admin), e nunca vai na URL;
- sem login vai ao Entrar; sem a chave (ou com a configuração errada) a tela avisa e nada quebra;
- o `?p=` do mapa abre a tela naquele caminho; de outro item, leva ao item dono; fora do mapa, a tela padrão;
- Chaves das fontes só para admin; o Tempo real sem a chave cai na ponte de 04/10 e, com ela, a ponte sai do menu;
- o Sair passa por /painel/nexus/sair quando a chave existe; sem ela, é o de sempre.
Tudo nos dois modos: na raiz (o PC e a fase 4) e debaixo do /nexus (o servidor, com o Caddy cortando o caminho).
"""
import base64
import hashlib
import hmac
import html as _html
import json
import re
import time

import pytest
from werkzeug.test import Client

from nexus import create_app
from nexus.performance import porta

from conftest import SENHA_TESTE

CHAVE = "c" * 40
PREFIXO = "/nexus"


def _app(prefixo="", **extra):
    cfg = {"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE, "NEXUS_SSO_CHAVE": CHAVE, **extra}
    if prefixo:
        cfg["NEXUS_PREFIXO"] = prefixo
    cfg = {k: v for k, v in cfg.items() if v is not None}
    app = create_app(cfg)
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    return app


def _caddy_corta(app):
    """O Caddy do servidor de hoje: /nexus/* vai ao Nexus sem o /nexus; o resto seria a plataforma."""
    def wsgi(environ, start_response):
        caminho = environ.get("PATH_INFO") or "/"
        if caminho == PREFIXO or caminho.startswith(PREFIXO + "/"):
            environ["PATH_INFO"] = caminho[len(PREFIXO):] or "/"
            return app(environ, start_response)
        start_response("599 PLATAFORMA", [("Content-Type", "text/plain")])
        return [b"isto seria a plataforma"]
    return wsgi


def _cliente(prefixo="", logar=True, **extra):
    app = _app(prefixo, **extra)
    cli = Client(_caddy_corta(app) if prefixo else app)
    if logar:
        assert cli.post(prefixo + "/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return cli


def _fracttal(monkeypatch, email="pessoa@exemplo.test", nome="Pessoa Teste", admins=None, prefixo=""):
    from nexus.auth import fracttal
    monkeypatch.setattr(fracttal, "entrar", lambda app, e, s: {"email": e, "nome": nome, "perfil": "",
                                                                  "cookie": ("os_sessao", "valor", 3600)})
    cli = _cliente(prefixo, logar=False, NEXUS_ADMINS=admins)
    assert cli.post(prefixo + "/entrar", data={"email": email, "senha": "x"}).status_code == 302
    return cli


def _form(html: str) -> dict | None:
    """O formulário do passe da página: action, target e o passe."""
    m = re.search(r'<form id="porta-passe"[^>]*>', html)
    if not m:
        return None
    tag = m.group(0)
    passe = re.search(r'<input type="hidden" name="passe" value="([^"]*)">', html).group(1)
    return {"action": re.search(r'action="([^"]*)"', tag).group(1), "target": re.search(r'target="([^"]*)"', tag).group(1),
            "method": re.search(r'method="([^"]*)"', tag).group(1), "passe": _html.unescape(passe)}


def _ler(passe: str) -> dict:
    corpo_b64, assin_b64 = passe.split(".")
    corpo = base64.urlsafe_b64decode(corpo_b64 + "=" * (-len(corpo_b64) % 4))
    assin = base64.urlsafe_b64decode(assin_b64 + "=" * (-len(assin_b64) % 4))
    assert hmac.compare_digest(assin, hmac.new(CHAVE.encode(), corpo, hashlib.sha256).digest())
    return json.loads(corpo)


def _dados(html: str) -> dict:
    m = re.search(r'<script type="application/json" id="porta-dados">(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else {}


def test_toda_tela_do_mapa_e_um_item_do_menu_com_a_moldura(app):
    """Cada tela do mapa está declarada na torre (é o que entra no menu) e o endereço dela cai na moldura, e não no
    placeholder. Os ids que já existiam (tempo-real, noc, diagnostico, strings-trackers, gerencial, relatorio, gemeo) não
    mudam: viraram endereço e favorito."""
    torres = {t.id: t for t in app.extensions["nexus_torres"]}
    rotas = app.url_map.bind("localhost")
    for t in porta.MAPA:
        assert torres[t.torre].tela(t.tela) is not None, t
        assert torres[t.torre].tela(t.tela).nome == t.nome, t
        endpoint, _ = rotas.match(f"/t/{t.torre}/{t.tela}", method="GET")
        assert endpoint == f"torre_{t.torre}.moldura_{t.tela.replace('-', '_')}", (t, endpoint)


# ── cada tela do mapa abre a moldura com o formulário certo ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("prefixo", ["", PREFIXO])
@pytest.mark.parametrize("t", porta.MAPA, ids=lambda t: f"{t.torre}-{t.tela}")
def test_cada_tela_do_mapa_abre_a_moldura_com_o_formulario_certo(prefixo, t):
    cli = _cliente(prefixo)
    r = cli.get(f"{prefixo}/t/{t.torre}/{t.tela}")
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "no-store"            # o passe não fica em cache (voltar gera outro)
    h = r.get_data(as_text=True)
    assert t.nome in h and 'class="menu"' in h and "Em construção" not in h
    assert f'href="{prefixo}/t/{t.torre}/{t.tela}" class="com-conteudo" aria-current="page"' in h
    dados = _dados(h)
    assert dados["url"] == f"{prefixo}/t/{t.torre}/{t.tela}" and dados["plataforma"] == ""
    assert all(x["url"].startswith(f"{prefixo}/t/") for x in dados["telas"]) and len(dados["telas"]) == 13
    assert f'src="{prefixo}/static/porta.js"' in h
    form = _form(h)
    if not porta.concreto(t):                                  # o Diagnóstico espera a usina do seletor
        assert form is None and 'id="porta-usina"' in h and "Escolha uma usina" in h
        assert _ler(dados["passe_lista"])["destino"] == "/painel"
        return
    assert form == {"action": "/painel/nexus/entrar", "target": "porta-moldura", "method": "post",
                    "passe": form["passe"]}
    assert 'name="porta-moldura"' in h and '<iframe class="porta-moldura"' in h
    p = _ler(form["passe"])
    assert p["destino"] == t.caminho and p["admin"] is True       # a senha de administrador
    assert p["email"] == porta.EMAIL_DA_SENHA_DE_ADMIN
    assert f'href="{t.caminho}"' in h                           # "Abrir em outra aba", na plataforma
    assert dados["passe_lista"] == "" and form["passe"] not in r.headers.get("Location", "")


def test_o_passe_muda_a_cada_abertura_e_vence_em_60_s():
    cli = _cliente()
    antes = time.time()
    passes = [_form(cli.get("/t/performance/noc").get_data(as_text=True))["passe"] for _ in range(3)]
    assert len(set(passes)) == 3
    lidos = [_ler(p) for p in passes]
    assert len({p["numero"] for p in lidos}) == 3
    assert all(antes + 59 <= p["vence"] <= time.time() + 60 for p in lidos)


def test_o_passe_diz_quem_entrou_pelo_fracttal(monkeypatch):
    cli = _fracttal(monkeypatch)
    p = _ler(_form(cli.get("/t/performance/gerencial").get_data(as_text=True))["passe"])
    assert (p["email"], p["nome"], p["admin"], p["destino"]) == ("pessoa@exemplo.test", "Pessoa Teste", False,
                                                                   "/gerencial")
    adm = _fracttal(monkeypatch, admins="pessoa@exemplo.test")
    assert _ler(_form(adm.get("/t/performance/gerencial").get_data(as_text=True))["passe"])["admin"] is True


def test_a_url_da_plataforma_configurada_vai_no_formulario():
    cli = _cliente(NEXUS_PLATAFORMA_URL="http://127.0.0.1:5150/")
    h = cli.get("/t/performance/tempo-real").get_data(as_text=True)
    assert _form(h)["action"] == "http://127.0.0.1:5150/painel/nexus/entrar"
    assert _dados(h)["plataforma"] == "http://127.0.0.1:5150"
    assert 'href="http://127.0.0.1:5150/tempo-real"' in h


# ── sem login, sem chave, sem configuração ───────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("prefixo", ["", PREFIXO])
def test_sem_login_vai_ao_entrar(prefixo):
    cli = _cliente(prefixo, logar=False)
    for t in porta.MAPA:
        r = cli.get(f"{prefixo}/t/{t.torre}/{t.tela}?p=/painel")
        assert r.status_code == 302 and r.headers["Location"].startswith(f"{prefixo}/entrar?next=")
        assert "passe" not in r.get_data(as_text=True)


@pytest.mark.parametrize("extra, motivo", [
    ({"NEXUS_SSO_CHAVE": None}, "falta a NEXUS_SSO_CHAVE"),
    ({"NEXUS_SSO_CHAVE": "curta-demais"}, "menos de 32 caracteres"),
    ({"NEXUS_PLATAFORMA_URL": "http://plataforma.exemplo.test"}, "https fora da máquina local"),
    ({"NEXUS_PLATAFORMA_URL": "https://x.test\\@127.0.0.1"}, "barra invertida"),
])
def test_sem_configuracao_a_tela_avisa_e_nada_quebra(extra, motivo):
    cli = _cliente(**extra)
    for t in porta.MAPA:
        r = cli.get(f"/t/{t.torre}/{t.tela}")
        h = r.get_data(as_text=True)
        assert r.status_code == 200, t
        assert "Performance ainda não ligada neste servidor" in h and motivo in h, t
        assert _form(h) is None and "porta-dados" not in h and "curta-demais" not in h
    assert cli.get("/t/performance/clima").status_code == 200       # o resto do Nexus segue
    assert cli.get("/").status_code == 200


# ── o ?p= (favorito, F5, o endereço que acompanhou a moldura) ────────────────────────────────────────────────────────
@pytest.mark.parametrize("prefixo", ["", PREFIXO])
def test_p_do_mapa_abre_a_moldura_naquele_caminho(prefixo):
    cli = _cliente(prefixo)
    h = cli.get(f"{prefixo}/t/performance/tempo-real", query_string={"p": "/monitor?fonte=pv&embed=1"}).get_data(
        as_text=True)
    assert _ler(_form(h)["passe"])["destino"] == "/monitor?fonte=pv&embed=1"
    h = cli.get(f"{prefixo}/t/performance/diagnostico",
                query_string={"p": "/painel/usina/297410?fonte=pv&nome=Usina%20Teste"}).get_data(as_text=True)
    assert _ler(_form(h)["passe"])["destino"] == "/painel/usina/297410?fonte=pv&nome=Usina%20Teste"
    assert _dados(h)["destino"] == "/painel/usina/297410?fonte=pv&nome=Usina%20Teste" and 'id="porta-usina"' in h


@pytest.mark.parametrize("prefixo", ["", PREFIXO])
def test_p_de_outro_item_leva_ao_item_dono(prefixo):
    cli = _cliente(prefixo)
    r = cli.get(f"{prefixo}/t/performance/noc", query_string={"p": "/painel/falhas"})
    assert r.status_code == 302
    assert r.headers["Location"] == f"{prefixo}/t/performance/strings-trackers?p=%2Fpainel%2Ffalhas"
    r = cli.get(f"{prefixo}/t/performance/noc", query_string={"p": "/cos"})
    assert r.headers["Location"] == f"{prefixo}/t/cos/acompanhamento?p=%2Fcos"


@pytest.mark.parametrize("ruim", ["//evil.example/x", "https://evil.example/painel", "/login", "/os/",
                                  "/painel/nexus/entrar", "/painel/usina/a'b", "javascript:alert(1)", "/api/macro",
                                  "/tempo-real#x", "/painel x"])
def test_p_fora_do_mapa_cai_na_tela_padrao(ruim):
    cli = _cliente()
    r = cli.get("/t/performance/noc", query_string={"p": ruim})
    assert r.status_code == 200
    assert _ler(_form(r.get_data(as_text=True))["passe"])["destino"] == "/painel"
    h = cli.get("/t/performance/diagnostico", query_string={"p": ruim}).get_data(as_text=True)
    assert _form(h) is None and "Escolha uma usina" in h


def test_p_com_ponto_ponto_codificado_cai_na_tela_padrao():
    """Revisão de 10/10/2026: ?p=/gemeo/%252e%252e/<caminho> virava o destino '/gemeo/%2e%2e/<caminho>' no passe e no
    "Abrir em outra aba", e o navegador o resolve como '..': a moldura ia a qualquer caminho da mesma origem."""
    cli = _cliente()
    for ruim in ("/gemeo/%2e%2e/%2e%2e/nexus/sair", "/gemeo/%2e%2e/tokens", "/gemeo/a%2fb"):
        h = cli.get("/t/performance/gemeo", query_string={"p": ruim}).get_data(as_text=True)
        assert _ler(_form(h)["passe"])["destino"] == "/gemeo/" and "%2e" not in h.lower(), ruim


# ── só admin, Tempo real, menu ───────────────────────────────────────────────────────────────────────────────────────
def test_chaves_das_fontes_so_para_admin(monkeypatch):
    cli = _fracttal(monkeypatch)
    r = cli.get("/t/base/chaves-fontes")
    h = r.get_data(as_text=True)
    assert r.status_code == 403 and "Só administradores do Nexus" in h and _form(h) is None and "porta-dados" not in h
    # o ?p= de outro item também não atravessa
    assert cli.get("/t/performance/noc", query_string={"p": "/tokens"}).headers["Location"] \
        == "/t/base/chaves-fontes?p=%2Ftokens"
    adm = _fracttal(monkeypatch, admins="pessoa@exemplo.test")
    h = adm.get("/t/base/chaves-fontes").get_data(as_text=True)
    p = _ler(_form(h)["passe"])
    assert p["destino"] == "/tokens" and p["admin"] is True


def test_tempo_real_sem_a_chave_cai_na_ponte_e_com_ela_a_ponte_sai():
    """A ponte de 04/10 segue no código (e é a reserva do Tempo real até a T.I. pôr a chave: nada afeta o que funciona
    hoje); com a chave, o item abre a moldura e a ponte não aparece."""
    ponte = {"NEXUS_PLATAFORMA_URL": "https://plat.exemplo.test", "NEXUS_PLATAFORMA_TOKEN": "segredo-xyz"}
    sem = _cliente(NEXUS_SSO_CHAVE=None, **ponte)
    h = sem.get("/t/performance/tempo-real").get_data(as_text=True)
    assert 'src="/t/performance/plataforma/tempo-real"' in h and "Performance ainda não ligada neste servidor" in h
    assert _form(h) is None and "segredo-xyz" not in h
    # as outras telas, sem a chave, avisam (a ponte nunca as mostrou)
    assert "Performance ainda não ligada" in sem.get("/t/performance/noc").get_data(as_text=True)
    com = _cliente(**ponte)
    h = com.get("/t/performance/tempo-real").get_data(as_text=True)
    assert "/t/performance/plataforma" not in h and _form(h)["action"] == "https://plat.exemplo.test/painel/nexus/entrar"
    # a rota da ponte continua no código (sai só do menu): o portão e a regra dela seguem valendo
    assert com.post("/t/performance/plataforma/api/state/x").status_code == 403


def test_a_alternancia_pelo_banco_fica_escondida():
    from nexus.torres import moldura
    assert [v["id"] for v in moldura.VISOES_DO_TEMPO_REAL] == ["ao-vivo", "banco"]
    h = _cliente().get("/t/performance/tempo-real").get_data(as_text=True)
    assert "Pelo banco" not in h and "porta-visoes" not in h


def test_o_menu_traz_as_telas_novas_e_acende_o_item():
    h = _cliente().get("/t/performance/disponibilidade").get_data(as_text=True)
    for t in porta.MAPA:
        assert f'href="/t/{t.torre}/{t.tela}"' in h, t
    assert re.search(r'<details class="torre com-conteudo" data-torre="performance"[^>]*open', h)
    assert h.count('aria-current="page"') == 1


# ── o Sair ───────────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("prefixo", ["", PREFIXO])
def test_o_sair_passa_pela_plataforma_quando_a_chave_existe(prefixo):
    cli = _cliente(prefixo)
    r = cli.get(prefixo + "/sair")
    h = r.get_data(as_text=True)
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    assert 'action="/painel/nexus/sair"' in h and f'name="volta" value="{prefixo}/entrar"' in h
    assert f'data-entrar="{prefixo}/entrar"' in h
    assert any(c.startswith("os_sessao=;") for c in r.headers.getlist("Set-Cookie"))
    # a sessão do Nexus acabou: a próxima tela vai ao Entrar
    assert cli.get(prefixo + "/t/performance/noc").status_code == 302


def test_o_sair_sem_a_chave_e_o_de_sempre():
    cli = _cliente(NEXUS_SSO_CHAVE=None)
    r = cli.get("/sair")
    assert r.status_code == 302 and r.headers["Location"] == "/entrar"


# ── a convivência com a camada da T.I. (que reescreve a resposta no servidor de hoje) ────────────────────────────────
def test_a_camada_do_servidor_nao_mexe_nos_enderecos_da_plataforma():
    """A camada fora do repositório põe /nexus nos caminhos DO NEXUS escritos no HTML; os da plataforma (o passe, o Sair
    e o "Abrir em outra aba") ficam como estão, e nada sai /nexus/nexus."""
    import importlib.util
    from pathlib import Path
    arq = Path(__file__).resolve().parent.parent / "ferramentas" / "porta_local.py"
    spec = importlib.util.spec_from_file_location("porta_local", arq)
    pl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pl)
    cli = _cliente(PREFIXO)
    for t in porta.MAPA:
        h = pl.reescreve_corpo(cli.get(f"{PREFIXO}/t/{t.torre}/{t.tela}").get_data(as_text=True), True)
        assert "/nexus/nexus" not in h, t
        if porta.concreto(t):
            assert _form(h)["action"] == "/painel/nexus/entrar" and f'href="{t.caminho}"' in h, t
        assert all(x["url"].startswith("/nexus/t/") for x in _dados(h)["telas"])
    h = pl.reescreve_corpo(cli.get(PREFIXO + "/sair").get_data(as_text=True), True)
    assert 'action="/painel/nexus/sair"' in h and "/nexus/nexus" not in h


# ── o passe não vai à máquina de quem visita (revisão de 10/10/2026) ─────────────────────────────────────────────────
def _script_do_sair(h: str) -> str:
    return re.findall(r"<script>(.*?)</script>", h, re.S)[-1]


def _rodar_sair(script: str, acao: str) -> dict:
    import shutil
    import subprocess
    from pathlib import Path
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    falsa = Path(__file__).resolve().parent / "porta_pagina_falsa.js"
    cfg = {"modo": "sair", "pagina": "https://app.exemplo.test/nexus/sair", "acao": acao, "script": script}
    r = subprocess.run(["node", str(falsa), str(falsa), json.dumps(cfg)], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_com_a_url_interna_e_o_nexus_aberto_por_fora_a_porta_fica_desligada():
    """NEXUS_PLATAFORMA_URL em loopback (o endereço interno do servidor, que a ponte de 04/10 pode usar) e o Nexus aberto
    por um endereço de fora: o formulário levaria o passe, com o e-mail, à porta local da máquina de quem visita. A tela
    diz que não está ligada e o Tempo real segue pela ponte (a reserva), como antes da chave."""
    cfg = {"NEXUS_PLATAFORMA_URL": "http://127.0.0.1:5050", "NEXUS_PLATAFORMA_TOKEN": "segredo-xyz"}
    app = _app(**cfg)
    fora = Client(app)
    assert fora.post("/entrar", data={"senha": SENHA_TESTE}, base_url="https://app.exemplo.test").status_code == 302
    h = fora.get("/t/performance/noc", base_url="https://app.exemplo.test").get_data(as_text=True)
    assert _form(h) is None and "porta-dados" not in h and "Performance ainda não ligada" in h
    assert "127.0.0.1:5050/painel" not in h
    h = fora.get("/t/performance/tempo-real", base_url="https://app.exemplo.test").get_data(as_text=True)
    assert 'src="/t/performance/plataforma/tempo-real"' in h and _form(h) is None
    r = fora.get("/sair", base_url="https://app.exemplo.test")
    assert r.status_code == 302                                   # sem POST à máquina de quem visita
    # no PC (o Nexus aberto em localhost), a mesma URL é a da cópia local: segue valendo
    local = _cliente(**cfg)
    assert _form(local.get("/t/performance/noc").get_data(as_text=True))["action"] \
        == "http://127.0.0.1:5050/painel/nexus/entrar"


def test_o_sair_nao_manda_post_a_outra_origem():
    cli = _cliente(NEXUS_PLATAFORMA_URL="https://outra.exemplo.test")
    h = cli.get("/sair").get_data(as_text=True)
    feito = _rodar_sair(_script_do_sair(h), "https://outra.exemplo.test/painel/nexus/sair")
    assert feito["pedidos"] == [] and feito["foiPara"] == "/nexus/entrar"
    feito = _rodar_sair(_script_do_sair(_cliente().get("/sair").get_data(as_text=True)), "/painel/nexus/sair")
    assert feito["pedidos"] == [{"url": "https://app.exemplo.test/painel/nexus/sair", "metodo": "POST"}]

