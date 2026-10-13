def test_saude_publica_e_enxuta(cliente):
    resp = cliente.get("/saude")
    assert resp.status_code == 200
    assert set(resp.get_json()) == {"ok", "commit"}


def test_a_cadeira_saiu(logado):
    """12/10/2026, Levi: "Exclua a parte de cadeiras já que os setores irão substituir!" (Base → Acessos)."""
    assert logado.post("/cadeira", data={"cadeira": "pcm"}).status_code == 404
    html = logado.get("/").get_data(as_text=True)
    assert 'class="cadeira"' not in html and "Cadeira" not in html and "data-sua" not in html
    # a senha de administrador não tem setor: o espaço do setor no topo fica vazio
    assert '<span class="setor-topo"></span>' in html


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
