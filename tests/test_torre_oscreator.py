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


def test_dentro_do_nexus_sem_a_faixa_de_abas_e_as_telas_seguem_vivas(logado):
    """Levi, 12/10/2026: "quero que mantenha esse carregamento mas tire a visão de abas da parte de cima pois como já
    temos as abas laterais, fica redundante ... quero passar a impressão de unidade!". A ponte esconde as duas faixas
    (.os-tabs: a da casca e a da tela aberta sozinha) só no Nexus; a casca continua guardando cada tela aberta, e sem o X
    de fechar ela guarda no máximo _ABAS_MAX (a acesa há mais tempo sai, nunca a ativa). O arquivo do clone não muda: o
    ajuste é da ponte, na resposta."""
    from nexus.torres.oscreator import ponte
    html = logado.get("/os/login").get_data(as_text=True)
    assert ".os-tabs{display:none!important}" in html
    abas = logado.get("/os/static/abas.js").get_data(as_text=True)
    assert abas.count("uso[id] = ++relogio;") == 1 and abas.count(f"if (abas.length >= {ponte._ABAS_MAX})") == 1
    # o teto entra antes de a aba nova nascer (no abrir) e a ativa nunca é a que sai
    assert abas.index(f"if (abas.length >= {ponte._ABAS_MAX})") < abas.index("seq += 1;")
    assert "return b.id !== ativa;" in abas
    # o arquivo do clone segue sem nada disso: é tudo da ponte, na resposta
    from pathlib import Path
    original = (Path(ponte.RAIZ_CLONE) / "os_web" / "static" / "abas.js").read_text(encoding="utf-8")
    assert "relogio" not in original and "os-tabs{display:none" not in original


def test_fila_do_pcm_usa_o_id_que_a_lista_de_pessoas_tem():
    """04/10: clicar em PCM dava 500. A Fila pedia p.id_account, campo que a lista de responsáveis não tem; o oem já
    tinha corrigido em 02/10 (id_personnel) e o clone era de 30/09."""
    from pathlib import Path
    from nexus.torres.oscreator import ponte
    # desde 13/10/2026 a Fila é a do app (lista e ficha) e a lista de pessoas sai pronta da rota (`rotas_solic.fila`)
    rota = Path(ponte.RAIZ_CLONE, "os_web", "rotas_solic.py").read_text(encoding="utf-8")
    fila = rota.split("def fila():", 1)[1].split("\n@bp.route", 1)[0]
    assert "id_account" not in fila and '"id": p.get("id_personnel")' in fila


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


# ── o card da OS em outra torre (Levi, 08/10/2026: "precisamos fazer os setores se conversarem") ────────────────────
def _login_do_fracttal(app, cliente):
    """O cookie do OS Creator como o login do Nexus pelo Fracttal o deixa (JWT de mentira; nada vai ao Fracttal)."""
    from nexus.torres.oscreator import ponte
    clone = ponte.clone(app)
    jwt = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"
    valor = clone.session_interface.get_signing_serializer(clone).dumps(
        {"jwt": jwt, "conta": {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid"}})
    cliente.set_cookie("os_sessao", valor, path="/os")


def test_o_card_da_os_e_o_do_historico_numa_moldura(app, logado):
    """A moldura carrega o MESMO card do Histórico: o fragmento /os/os/<id>?parcial=1 (com o status, como a linha do
    Histórico manda), as ações do os_acoes.js e o CSS do OS Creator, dentro da mesma .os-modal."""
    _login_do_fracttal(app, logado)
    r = logado.get("/os/_nexus/card/9001?status=Em%20Processo&de=/t/engenharia/equipe")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    assert 'data-fragmento="/os/os/9001?parcial=1&amp;status=Em+Processo"' in h and "carregar();" in h
    for peca in ('<script src="/os/static/os_acoes.js">', 'href="/os/static/os.css"', 'href="/os/static/os_acoes.css"',
                 '<script src="/os/static/os_busca.js"', '<script src="/os/static/carga.js">', 'class="os-modal"',
                 'class="os-modal-card os-form"', 'class="os-modal-x" data-fechar'):
        assert peca in h, peca
    assert 'data-pagina="/os/os/9001?status=Em+Processo"' in h      # aberta sozinha, vira a página da OS
    assert "window.__osTopo" not in h                               # é página do Nexus, não passa pelas trocas da ponte


def test_sem_o_login_do_fracttal_o_card_diz_para_entrar(logado):
    """Quem entrou pela senha de admin (ou pela conta Microsoft) não tem o JWT do Fracttal: a moldura não busca a OS e
    manda ao login do Fracttal do PRÓPRIO OS Creator (/os/login), que volta, pelo /os/_nexus/card/voltar, à tela de onde a
    pessoa saiu. Levi, 18/10/2026: o botão ia ao /entrar do Nexus, que com a Microsoft ligada é a porta dela ("redireciona
    para logar pela microsoft, não loga pelo fractal")."""
    h = logado.get("/os/_nexus/card/9001?status=Em%20Processo&de=/t/engenharia/equipe").get_data(as_text=True)
    assert "Para abrir a OS, entre pelo Fracttal" in h and "carregar();" not in h
    assert 'href="/os/login?next=%2Fos%2F_nexus%2Fcard%2Fvoltar%3Fde%3D%2Ft%2Fengenharia%2Fequipe" target="_top"' in h
    assert 'href="/entrar' not in h
    # de fora do Nexus não vira destino
    h = logado.get("/os/_nexus/card/9001?de=//exemplo.invalid/x").get_data(as_text=True)
    assert 'href="/os/login?next=%2Fos%2F_nexus%2Fcard%2Fvoltar%3Fde%3D%2F"' in h


def test_a_volta_do_login_do_fracttal_cai_na_tela_de_origem(app, logado):
    """O /os/_nexus/card/voltar leva à tela do Nexus (`de`), e só a uma do próprio site. O login do clone o aceita como
    destino (começa com /os), então quem entra pelo Fracttal no card volta à tela de onde clicou na OS."""
    r = logado.get("/os/_nexus/card/voltar?de=/t/pcm/gestao%3Fmodo%3Dplano")
    assert r.status_code == 302 and r.headers["Location"] == "/t/pcm/gestao?modo=plano"
    assert logado.get("/os/_nexus/card/voltar?de=//exemplo.invalid/x").headers["Location"] == "/"
    from nexus.torres.oscreator import ponte
    from nexus.torres.oscreator.os_creator.os_web import rotas
    with ponte.clone(app).test_request_context():
        assert rotas._destino_local("/os/_nexus/card/voltar?de=/t/pcm/gestao") == "/os/_nexus/card/voltar?de=/t/pcm/gestao"


def test_o_card_da_os_pelo_numero(app, logado):
    """16/10/2026: a tela sem o id do Fracttal (o nº citado na observação do Fora da programação do PCM) abre o MESMO
    card pelo número: o fragmento do "Buscar OS pelo nº" do clone (/os/os/folio/<nº>?parcial=1)."""
    h = logado.get("/os/_nexus/card/folio/16290?de=/t/pcm/fora-da-programacao").get_data(as_text=True)
    assert "Para abrir a OS, entre pelo Fracttal" in h
    assert 'href="/os/login?next=%2Fos%2F_nexus%2Fcard%2Fvoltar%3Fde%3D%2Ft%2Fpcm%2Ffora-da-programacao"' in h
    _login_do_fracttal(app, logado)
    r = logado.get("/os/_nexus/card/folio/16290?status=Em%20Processo&de=/t/pcm/fora-da-programacao")
    h = r.get_data(as_text=True)
    assert r.status_code == 200 and "carregar();" in h
    assert 'data-fragmento="/os/os/folio/16290?parcial=1&amp;status=Em+Processo"' in h
    assert 'data-pagina="/os/os/folio/16290?status=Em+Processo"' in h
    assert logado.get("/os/_nexus/card/folio/abc").status_code == 404           # só número


def test_link_do_card_abre_a_torre_os_creator_com_a_tela_numa_aba(logado):
    from nexus.torres.oscreator import ponte
    assert ponte.tela_do_endereco("/os/clonar?folio=15101") == "clonagem"
    assert ponte.tela_do_endereco("/os/chamados/inspecao?pai=15101") == "chamados"
    assert ponte.tela_do_endereco("/os/os/9001") == "inicio"
    r = logado.get("/os/_nexus/ir?url=/os/clonar?folio=15101")
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/os/clonagem?abrir=%2Fos%2Fclonar%3Ffolio%3D15101")
    h = logado.get("/t/os/clonagem?abrir=/os/clonar?folio=15101").get_data(as_text=True)
    assert '<iframe class="os-moldura" src="/os/clonar?folio=15101"' in h
    # só endereço do próprio OS Creator: o resto cai no Início, e a moldura não sai do /os
    assert logado.get("/os/_nexus/ir?url=https://exemplo.invalid").headers["Location"].endswith("/t/os/inicio?abrir=%2Fos%2F")
    h = logado.get("/t/os/inicio?abrir=//exemplo.invalid").get_data(as_text=True)
    assert '<iframe class="os-moldura" src="/os/"' in h
