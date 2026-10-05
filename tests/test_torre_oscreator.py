"""A torre OS Creator ligada ao clone do OS Creator Web (nexus/torres/oscreator/os_creator).

O clone roda DENTRO do Nexus, sem segundo serviço: o Nexus atende /os/* depois do portão de login e entrega a
requisição ao app Flask do clone (ponte.py). Estes testes sobem o clone de verdade, mas só em telas que não
falam com o Fracttal (login, arquivos, redirecionamentos) — nenhum teste aqui faz rede.
"""
import hashlib
import hmac

import pytest

from nexus.torres import descobrir_torres

# o clone importa o steps/ui.py do OS Creator (PyQt6) ao montar a tela de Engenharia
pytest.importorskip("PyQt6")

DESTINOS = {"inicio": "/os/", "historico": "/os/historico", "ativos": "/os/ativos", "performance": "/os/performance",
            "cos": "/os/cos", "pcm": "/os/setor/pcm", "chamados": "/os/chamados", "engenharia": "/os/engenharia",
            "solicitacao": "/os/solicitacao", "clonagem": "/os/clonar"}


def _torre_os():
    return next(t for t in descobrir_torres() if t.id == "os")


def test_cada_tela_da_torre_abre_o_os_creator_na_secao_dela(logado):
    torre = _torre_os()
    assert {t.id for t in torre.telas} == set(DESTINOS)
    for tela in torre.telas:
        resp = logado.get(f"/t/os/{tela.id}")
        assert resp.status_code == 200, tela.id
        html = resp.get_data(as_text=True)
        assert tela.nome in html
        # Dentro do Nexus, com o menu lateral (Levi, 30/09: "quero que continue no espaço do Nexus"), e não em
        # tela cheia: a seção abre numa moldura da página da torre.
        assert f'<iframe class="os-moldura" src="{DESTINOS[tela.id]}"' in html, tela.id
        assert 'class="menu"' in html, tela.id
        assert "location.replace" not in html, tela.id
        assert "Em construção" not in html, tela.id


def test_os_creator_trata_a_moldura_do_nexus_como_a_janela(logado):
    """Os scripts do clone usam window.top para saber se são a casca. Na moldura do Nexus, window.top é o Nexus:
    as abas não ligariam e o login fugiria da moldura. A ponte troca window.top pela janela do próprio OS Creator."""
    html = logado.get("/os/login").get_data(as_text=True)
    assert "window.__osTopo = function" in html
    assert "window.top" not in html.replace("window.__osTopo", "")
    abas = logado.get("/os/static/abas.js").get_data(as_text=True)
    assert "if (window.__osTopo() === window) casca();" in abas
    assert "if (window.parent === window) casca();" not in abas


def test_abas_js_ajustado_nao_fica_preso_no_cache_do_original(logado):
    """30/09: o abas.js ajustado saía com a ETag do original. O navegador que já tinha o original perguntava "mudou?",
    levava 304 e seguia com o antigo: a casca não ligava as abas e todo botão voltava ao Início do OS Creator."""
    r = logado.get("/os/static/abas.js")
    assert r.status_code == 200 and "__osTopo" in r.get_data(as_text=True)
    etag = r.headers.get("ETag", "")
    assert "nexus" in etag
    # quem tem o ORIGINAL em cache (ETag e data do arquivo) recebe o ajustado, e não um 304
    original = etag.split("-nexus")[0] + '"' if etag.endswith('"') else etag.split("-nexus")[0]
    r2 = logado.get("/os/static/abas.js", headers={"If-None-Match": original,
                                                   "If-Modified-Since": r.headers.get("Last-Modified", "")})
    assert r2.status_code == 200 and "__osTopo" in r2.get_data(as_text=True)


def test_topo_do_os_creator_no_nexus_sem_voltar_e_sem_marca(logado):
    """Levi, 04/10: sem o botão de voltar (o menu lateral já leva a qualquer lugar) e sem o símbolo e o "Grid Co."
    (o topo do Nexus já tem); só o "Sistema de Ordens de Serviço"."""
    html = logado.get("/os/login").get_data(as_text=True)
    assert "os-topo-voltar" not in html and "Plataforma" not in html and "&larr; Nexus" not in html
    assert 'class="os-n1"' not in html and 'class="os-simbolo"' not in html
    assert 'class="os-n2 os-n2--nexus">Sistema de Ordens de Serviço<' in html
    assert ".os-n2--nexus{" in html


def test_menu_lateral_abre_aba_nova_na_casca(logado):
    """Levi, 04/10: "os botões laterais devem contribuir em adicionar novas abas também na tela acima". A página da
    torre leva o mapa menu → tela, e o abas.js ganha (pela ponte) uma porta que só ouve o Nexus."""
    html = logado.get("/t/os/historico").get_data(as_text=True)
    assert '"/t/os/pcm": {"nome": "PCM", "url": "/os/setor/pcm"}' in html
    assert "nexusOs: 1" in html
    abas = logado.get("/os/static/abas.js").get_data(as_text=True)
    assert abas.count("d.nexusOs !== 1") == 1 and "e.source !== window.parent" in abas
    assert abas.index("d.nexusOs !== 1") < abas.index("if (d.tipo === 'pagina')")     # dentro da casca, antes da original


def test_fila_do_pcm_usa_o_id_que_a_lista_de_pessoas_tem():
    """04/10: clicar em PCM dava 500. A Fila pedia p.id_account, campo que a lista de responsáveis não tem; o oem já
    tinha corrigido em 02/10 (id_personnel) e o clone era de 30/09."""
    from pathlib import Path
    from nexus.torres.oscreator import ponte
    fila = Path(ponte.RAIZ_CLONE, "os_web", "templates", "solic_fila.html").read_text(encoding="utf-8")
    assert "p.id_account" not in fila.split("{#")[0] + fila.split("#}")[-1] and "p.id_personnel" in fila


def test_os_sem_login_do_nexus_para_no_portao(cliente):
    for url in ("/os/", "/os/login", "/os/static/os.css", "/os/historico"):
        resp = cliente.get(url)
        assert resp.status_code == 302, url
        assert "/entrar" in resp.headers["Location"], url


def test_login_do_os_creator_passa_pela_ponte(logado):
    resp = logado.get("/os/login")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Sistema de Ordens de Serviço" in html     # é a tela do OS Creator, não uma página do Nexus
    assert 'name="senha"' in html


def test_post_chega_ao_os_creator(logado):
    # token colado que não é token: o OS Creator recusa na hora, sem ir ao Fracttal
    resp = logado.post("/os/login", data={"token": "isto não é um token"})
    assert resp.status_code == 401
    assert "Sistema de Ordens de Serviço" in resp.get_data(as_text=True)


def test_sem_fracttal_o_os_creator_manda_para_o_login_dele(logado):
    resp = logado.get("/os/")
    assert resp.status_code == 302
    assert "/os/login" in resp.headers["Location"]


def test_arquivos_do_os_creator_passam(logado):
    css = logado.get("/os/static/os.css")
    assert css.status_code == 200 and css.mimetype == "text/css"
    png = logado.get("/os/assets/grid-logo.png")
    assert png.status_code == 200 and png.mimetype == "image/png"


def test_sessao_do_fracttal_fica_no_cookie_do_os_creator(app):
    """A chave do clone sai da do Nexus (HMAC), então não é a do supervisório nem a própria chave do Nexus."""
    from nexus.torres.oscreator import ponte
    clone = ponte.clone(app)
    esperado = hmac.new(app.config["SECRET_KEY"].encode(), b"nexus/os_web", hashlib.sha256).hexdigest()
    assert clone.config["SECRET_KEY"] == esperado != app.config["SECRET_KEY"]
    assert clone.config["SESSION_COOKIE_NAME"] == "os_sessao"
    assert clone.config["SESSION_COOKIE_PATH"] == "/os"
    assert ponte.clone(app) is clone                     # sobe uma vez só por app


def test_clone_que_nao_sobe_vira_aviso_e_o_nexus_segue(logado, monkeypatch):
    from nexus.torres.oscreator import ponte

    def quebra(_app):
        raise ImportError("No module named 'PyQt6'")

    monkeypatch.setattr(ponte, "_criar_clone", quebra)
    resp = logado.get("/os/")
    assert resp.status_code == 503
    html = resp.get_data(as_text=True)
    assert "OS Creator" in html and "PyQt6" in html
    assert logado.get("/").status_code == 200
