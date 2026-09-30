from nexus.cadeiras import CADEIRAS
from nexus.torres import descobrir_torres, montar_menu


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


def test_torre_inicial_de_toda_cadeira_existe():
    ids = {t.id for t in descobrir_torres()}
    for cadeira in CADEIRAS.values():
        assert cadeira.torre_inicial in ids, cadeira.id


def test_menu_poe_torre_da_cadeira_primeiro():
    menu = montar_menu(descobrir_torres(), "cos", None)
    assert menu[0]["id"] == "cos"
    assert menu[0]["sua"] and menu[0]["aberta"]
    assert not any(m["sua"] for m in menu[1:])
    assert not any(m["aberta"] for m in menu[1:])


def test_menu_sem_cadeira_segue_catalogo():
    torres = descobrir_torres()
    menu = montar_menu(torres, None, None)
    assert [m["id"] for m in menu] == [t.id for t in torres]
    assert not any(m["sua"] for m in menu)


def test_menu_abre_a_torre_atual():
    menu = montar_menu(descobrir_torres(), "cos", "pcm")
    pcm = next(m for m in menu if m["id"] == "pcm")
    assert pcm["aberta"] and not pcm["sua"]


def test_aviso_aponta_a_pasta_certa(app):
    """A torre "os" mora em oscreator/; o aviso da tela tem de mandar o dev para a pasta que existe.

    Desde 30/09 as telas da torre "os" abrem o clone do OS Creator em vez do aviso, então o aviso é conferido
    no próprio template — é ele que a vitrine estática e toda tela sem view usam."""
    from flask import render_template

    torre = next(t for t in descobrir_torres() if t.id == "os")
    with app.test_request_context("/t/os/inicio"):
        html = render_template("tela.html", torre=torre, tela=torre.telas[0])
    assert "nexus/torres/oscreator/" in html
