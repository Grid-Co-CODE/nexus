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


def test_troca_vale_com_crlf():
    """Clone do Windows (core.autocrlf) sai em CRLF: a porta do menu e o topo têm de entrar do mesmo jeito (05/10/2026,
    ensaio da T.I. num clone limpo: o abas.js saía sem a porta, sem erro)."""
    from nexus.torres.oscreator import ponte
    for de, para in ponte._TROCAS_ABAS + [(ponte._MARCA_DE, ponte._MARCA_PARA)]:
        lf = b"antes\n" + de + b"depois\n"
        crlf = lf.replace(b"\n", b"\r\n")
        assert ponte._trocar(lf, de, para) == b"antes\n" + para + b"depois\n"
        assert ponte._trocar(crlf, de, para) == (b"antes\n" + para + b"depois\n").replace(b"\n", b"\r\n")


# ── sincronia com o oem: o Nexus é a referência (Levi, 06/10/2026) ──────────────────────────────────────────────────
def _arvore(raiz, arquivos):
    for rel, texto in arquivos.items():
        p = raiz / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(texto, encoding="utf-8")


def test_sincronia_leva_o_que_mudou_no_nexus_e_nao_atropela_o_oem(tmp_path):
    from nexus.torres.oscreator import sincronia as S
    nexus, oem, backup = tmp_path / "nexus", tmp_path / "oem", tmp_path / "backup"
    comum = {"os_creator/a.py": "a = 1\n", "os_creator/b.py": "b = 1\n", "os_creator/c.py": "c = 1\n",
             "os_creator/d.py": "d = 1\n"}
    _arvore(nexus, comum)
    _arvore(oem, comum)
    base = {rel: S._hash(nexus / rel) for rel in comum}
    _arvore(nexus, {"os_creator/b.py": "b = 2\n", "os_creator/d.py": "d = 2\n", "os_creator/os_web/e.html": "novo"})
    _arvore(oem, {"os_creator/c.py": "c = 9\n", "os_creator/d.py": "d = 9\n"})
    lista = sorted(list(comum) + ["os_creator/os_web/e.html"])
    st = S.estado(nexus, oem, lista, base)
    assert (st["igual"], st["levar"], st["trazer"], st["conflito"]) == (
        ["os_creator/a.py"], ["os_creator/b.py", "os_creator/os_web/e.html"], ["os_creator/c.py"], ["os_creator/d.py"])
    feitos, nova = S.aplicar(nexus, oem, lista, base, backup)
    assert feitos == ["os_creator/b.py", "os_creator/os_web/e.html"]
    assert (oem / "os_creator/b.py").read_text(encoding="utf-8") == "b = 2\n"
    assert (backup / "os_creator/b.py").read_text(encoding="utf-8") == "b = 1\n"                 # o do oem guardado
    assert (oem / "os_creator/c.py").read_text(encoding="utf-8") == "c = 9\n"                    # não atropela o oem
    assert (oem / "os_creator/d.py").read_text(encoding="utf-8") == "d = 9\n"                    # conflito fica
    st = S.estado(nexus, oem, lista, nova)
    assert (st["levar"], st["trazer"], st["conflito"]) == ([], ["os_creator/c.py"], ["os_creator/d.py"])
    feitos, nova = S.trazer(nexus, oem, lista, nova, backup)
    assert feitos == ["os_creator/c.py"] and (nexus / "os_creator/c.py").read_text(encoding="utf-8") == "c = 9\n"
    assert S.estado(nexus, oem, lista, nova)["conflito"] == ["os_creator/d.py"]


def test_sincronia_recusa_copia_que_importa_o_nexus(tmp_path):
    from nexus.torres.oscreator import sincronia as S
    _arvore(tmp_path / "n", {"os_creator/x.py": "from nexus.config import algo\n"})
    with pytest.raises(RuntimeError, match="importa o pacote nexus"):
        S.aplicar(tmp_path / "n", tmp_path / "o", ["os_creator/x.py"], {}, tmp_path / "b")


def test_copia_do_os_creator_vai_sem_o_env_e_sem_importar_o_nexus():
    """O .env da cópia tem a credencial do Fracttal: nunca entra na lista. E a cópia não importa o nexus."""
    from nexus.torres.oscreator import sincronia as S
    lista = S.arquivos()
    assert len(lista) > 100 and not any(rel.endswith(".env") for rel in lista)
    assert S.importa_o_nexus(S.AQUI, lista) == []


@pytest.mark.skipif(not (__import__("nexus.torres.oscreator.sincronia", fromlist=["x"]).OEM_PADRAO / "os_creator").is_dir(),
                    reason="o oem não está nesta máquina")
def test_copia_do_os_creator_igual_ao_oem():
    """O Nexus é a referência: mudou aqui, rode `python ferramentas/sincronizar_oscreator.py --aplicar` para levar ao
    oem (o 5090 do supervisório). Mudou só no oem, ou nos dois: a ferramenta lista, e nada é atropelado."""
    from nexus.torres.oscreator import sincronia as S
    st = S.estado(S.AQUI, S.OEM_PADRAO, S.arquivos(), S.ler_manifesto())
    assert not (st["levar"] or st["trazer"] or st["conflito"]), {k: st[k][:10] for k in ("levar", "trazer", "conflito")}


def test_sincronia_nao_conta_o_fim_de_linha(tmp_path):
    """Clone do Windows (CRLF) contra o oem (LF): o mesmo conteúdo é igual, e nada é copiado."""
    from nexus.torres.oscreator import sincronia as S
    (tmp_path / "n/os_creator").mkdir(parents=True)
    (tmp_path / "o/os_creator").mkdir(parents=True)
    (tmp_path / "n/os_creator/a.py").write_bytes(b"x = 1\r\ny = 2\r\n")
    (tmp_path / "o/os_creator/a.py").write_bytes(b"x = 1\ny = 2\n")
    assert S.estado(tmp_path / "n", tmp_path / "o", ["os_creator/a.py"], {})["igual"] == ["os_creator/a.py"]
