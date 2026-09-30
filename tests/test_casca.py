def test_saude_publica_e_enxuta(cliente):
    resp = cliente.get("/saude")
    assert resp.status_code == 200
    assert set(resp.get_json()) == {"ok", "commit"}


def test_cadeira_inexistente_recusada(logado):
    assert logado.post("/cadeira", data={"cadeira": "rei"}).status_code == 400


def test_trocar_cadeira_muda_o_menu(logado):
    resp = logado.post("/cadeira", data={"cadeira": "pcm", "voltar": "/"})
    assert resp.status_code == 302
    html = logado.get("/").get_data(as_text=True)
    assert "Coordenador de PCM" in html
    # A torre da cadeira vem marcada como "sua" no menu.
    assert 'data-torre="pcm" data-sua="1"' in html


def test_inicio_logado(logado):
    html = logado.get("/").get_data(as_text=True)
    assert "Nexus" in html
    assert "Sair" in html


def test_inicio_e_botao_direto(logado):
    """Início é um link só no topo do menu, marcado na página inicial, sem grupo de sub-telas."""
    html = logado.get("/").get_data(as_text=True)
    assert 'class="item-inicio" href="/" aria-current="page"' in html
    assert 'data-torre="inicio"' not in html


def test_botao_de_recolher_menu(logado):
    html = logado.get("/t/cos/mesa").get_data(as_text=True)
    assert 'id="recolhe-menu"' in html
    # No trilho recolhido o nome da torre aparece no title do ícone.
    assert 'title="COS"' in html
