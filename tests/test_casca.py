def test_saude_publica_e_enxuta(cliente):
    resp = cliente.get("/saude")
    assert resp.status_code == 200
    assert set(resp.get_json()) == {"ok", "commit"}


def test_a_cadeira_saiu(logado):
    """12/10/2026, Levi: "Exclua a parte de cadeiras já que os setores irão substituir!" (Base → Acessos)."""
    assert logado.post("/cadeira", data={"cadeira": "pcm"}).status_code == 404
    html = logado.get("/").get_data(as_text=True)
    assert 'class="cadeira"' not in html and "Cadeira" not in html and "data-sua" not in html
    # a senha de administrador não tem setor: o menu da conta não traz a linha do setor
    assert 'class="conta-setor"' not in html and "Setor:" not in html


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
    # Sem JavaScript, o nome da torre fica no title do ícone do trilho recolhido.
    assert 'title="COS"' in html
    # Com ele, passar o mouse no ícone abre ao lado as telas da torre (05/11/2026, Levi: "ao passar o mouse aparecesse
    # as opções daquela área"): a caixa nasce no base.html e o estilo mora no nexus.css
    assert 'voo.className = "menu-voo"' in html and 'torre.addEventListener("mouseenter"' in html


def test_a_caixa_do_menu_recolhido_tem_estilo_so_por_token():
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "nexus.css").read_text(encoding="utf-8")
    bloco = css[css.index(".menu-voo{"):css.index(".menu-voo li a[aria-current")]
    assert "position:fixed" in bloco and "#" not in bloco and "rgba(" not in bloco
