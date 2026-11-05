"""A Paleta Nexus (04/11/2026; Levi: "ao clicar no nome da pessoa aparecer 'paleta nexus' só para os administradores"):
o escuro ao lado do claro, lidos do nexus.css; o item no menu da conta e a página, só para administradores."""
from nexus.casca import paleta_tokens as PA


def test_o_administrador_ve_a_paleta_lida_do_css(app, logado):
    html = logado.get("/").get_data(as_text=True)
    conta = html.split('class="conta-caixa"', 1)[1].split("</details>", 1)[0]
    assert 'href="/paleta"' in conta and "Paleta Nexus" in conta
    r = logado.get("/paleta")
    pag = r.get_data(as_text=True)
    assert r.status_code == 200 and "Início · escuro" in pag and "Início · claro" in pag
    with app.app_context():
        esc, cla = PA.tokens()
    assert esc["fundo"] == "#090d18" and cla["fundo"] == "#ffffff"           # o escuro de sempre e o claro de agora
    assert f'<code style="color:{esc["tinta-2"]}">{esc["superficie"]}</code>' in pag
    assert pag.count("<tr><th><code>--") == len(esc)                          # todo token, nenhum a mais


def test_quem_nao_e_administrador_nao_ve(app):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=False, usuario={"email": "pessoa@exemplo.test", "nome": "Pessoa de Teste"})
    assert c.get("/paleta").status_code == 403
    assert 'href="/paleta"' not in c.get("/").get_data(as_text=True)


def test_o_contraste_do_texto():
    assert PA.contraste("#ffffff", "#000000") == 21.0
    assert PA.contraste("rgba(0,0,0,.5)", "#ffffff") < PA.contraste("#000000", "#ffffff")
    assert PA.contraste("var(--x)", "#ffffff") is None
