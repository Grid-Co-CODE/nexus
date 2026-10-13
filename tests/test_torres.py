import re

from nexus.torres import descobrir_torres, montar_menu, telas_com_conteudo


def test_treze_torres_descobertas():
    ids = [t.id for t in descobrir_torres()]
    assert len(ids) == 13
    assert ids[0] == "comando"
    assert len(set(ids)) == 13
    # OS Creator entra logo abaixo da Base (pedido do Levi, 29/09).
    assert ids[-2:] == ["base", "os"]
    # Início é um botão da casca, não uma torre com sub-telas (pedido do Levi, 29/09).
    assert "inicio" not in ids


def test_toda_tela_responde_logado(logado):
    for torre in descobrir_torres():
        assert torre.telas, torre.id
        for tela in torre.telas:
            resp = logado.get(f"/t/{torre.id}/{tela.id}")
            assert resp.status_code == 200, (torre.id, tela.id)
            assert tela.nome in resp.get_data(as_text=True)


def test_tela_inexistente_404(logado):
    assert logado.get("/t/cos/nao-existe").status_code == 404


def test_menu_segue_o_catalogo():
    torres = descobrir_torres()
    menu = montar_menu(torres, None)
    assert [m["id"] for m in menu] == [t.id for t in torres]
    assert not any(m["aberta"] for m in menu)
    assert not any("sua" in m for m in menu)          # a cadeira saiu em 12/10/2026: os setores a substituíram


def test_menu_abre_a_torre_atual():
    menu = montar_menu(descobrir_torres(), "pcm")
    assert [m["id"] for m in menu if m["aberta"]] == ["pcm"]


def test_menu_so_com_as_telas_do_setor():
    """Base → Acessos (12/10/2026): só as telas liberadas; torre sem nenhuma some; None = tudo (o administrador)."""
    torres = descobrir_torres()
    menu = montar_menu(torres, None, liberadas={"pcm/quadro", "cos/mesa", "performance/clima/mapa"})
    assert [m["id"] for m in menu] == ["cos", "pcm", "performance"]
    assert [[s["id"] for s in m["telas"]] for m in menu] == [["mesa"], ["quadro"], ["clima/mapa"]]
    assert montar_menu(torres, None, liberadas=set()) == []
    assert len(montar_menu(torres, None, liberadas=None)) == len(torres)


def test_tela_com_view_propria_conta_como_conteudo(app):
    """O verde do menu sai do mapa de rotas: view própria conta, placeholder não (Levi, 04/10/2026)."""
    prontas = telas_com_conteudo(app)
    assert "/t/base/governanca" in prontas        # view própria
    assert "/t/pcm/quadro" in prontas
    assert "/t/cos/mesa" not in prontas           # ainda placeholder
    assert all(not u.startswith("/t/comando/") for u in prontas)


def test_menu_pinta_de_verde_so_o_que_tem_conteudo(logado):
    html = logado.get("/").get_data(as_text=True)
    classe = {torre: extra for extra, torre in re.findall(r'<details class="torre( com-conteudo)?" data-torre="([^"]+)"', html)}
    assert len(classe) == 13
    assert classe["base"] and classe["os"]
    assert not classe["comando"]
    assert '<a href="/t/base/governanca" class="com-conteudo"' in html
    assert 'href="/t/cos/mesa" class="com-conteudo"' not in html


def test_aviso_aponta_a_pasta_certa(app):
    """A torre "os" mora em oscreator/; o aviso da tela tem de mandar o dev para a pasta que existe.

    Desde 30/09 as telas da torre "os" abrem o clone do OS Creator em vez do aviso, então o aviso é conferido
    no próprio template — é ele que a vitrine estática e toda tela sem view usam."""
    from flask import render_template

    torre = next(t for t in descobrir_torres() if t.id == "os")
    with app.test_request_context("/t/os/inicio"):
        html = render_template("tela.html", torre=torre, tela=torre.telas[0])
    assert "nexus/torres/oscreator/" in html
