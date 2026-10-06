from nexus.auth import ROTAS_PUBLICAS, next_seguro

from conftest import SENHA_TESTE


def test_toda_rota_nao_publica_exige_login(app, cliente):
    """Percorre o url_map inteiro: uma rota nova esquecida fora do portão aparece aqui."""
    verificadas = 0
    for regra in app.url_map.iter_rules():
        if regra.endpoint in ROTAS_PUBLICAS or "GET" not in regra.methods:
            continue
        # rota com <int:...> (o histórico de rondas da usina) só monta com número
        valores = {arg: 1 if type(regra._converters.get(arg)).__name__ == "IntegerConverter" else "x"
                   for arg in regra.arguments}
        url = regra.build(valores, append_unknown=False)[1]
        resp = cliente.get(url)
        assert resp.status_code == 302, url
        assert "/entrar" in resp.headers["Location"], url
        verificadas += 1
    assert verificadas >= 3


def test_post_de_cadeira_sem_login_tambem_barra(cliente):
    resp = cliente.post("/cadeira", data={"cadeira": "cos"})
    assert resp.status_code == 302
    assert "/entrar" in resp.headers["Location"]


def test_senha_errada_nao_loga(cliente):
    resp = cliente.post("/entrar", data={"senha": "errada"})
    assert resp.status_code == 401
    assert cliente.get("/").status_code == 302


def test_sexta_tentativa_errada_bloqueia(cliente):
    for _ in range(5):
        assert cliente.post("/entrar", data={"senha": "errada"}).status_code == 401
    # Bloqueado: nem a senha certa entra até a janela passar.
    assert cliente.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 429


def test_senha_certa_respeita_next_interno(cliente):
    resp = cliente.post("/entrar?next=/t/cos/mesa", data={"senha": SENHA_TESTE})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/t/cos/mesa")


def test_next_externo_cai_no_inicio(cliente):
    resp = cliente.post("/entrar?next=https://mal.exemplo.com/", data={"senha": SENHA_TESTE})
    assert resp.headers["Location"].endswith("/")
    assert "mal.exemplo" not in resp.headers["Location"]


def test_next_seguro():
    assert next_seguro("/t/pcm/semana") == "/t/pcm/semana"
    assert next_seguro("//mal.com") == "/"
    assert next_seguro("https://mal.com") == "/"
    assert next_seguro("/\\mal.com") == "/"
    assert next_seguro(None) == "/"


def test_sair_encerra_sessao(logado):
    assert logado.get("/").status_code == 200
    logado.get("/sair")
    assert logado.get("/").status_code == 302


def test_entrar_com_o_fracttal_abre_o_nexus_e_o_os_creator(cliente, monkeypatch):
    """06/10: a pessoa entra com o login do Fracttal; a sessão do OS Creator (o JWT) nasce junto, no cookie de /os."""
    from nexus.auth import fracttal
    monkeypatch.setattr(fracttal, "entrar", lambda app, e, s: {"email": e, "nome": "Pessoa Teste", "perfil": "",
                                                                  "cookie": ("os_sessao", "valor-assinado", 3600)})
    r = cliente.post("/entrar?next=/os/", data={"email": "pessoa@exemplo.test", "senha": "x"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/os/")
    biscoito = [h for h in r.headers.getlist("Set-Cookie") if h.startswith("os_sessao=")][0]
    assert "Path=/os" in biscoito and "HttpOnly" in biscoito
    assert cliente.get("/").status_code == 200
    sair = cliente.get("/sair")
    assert any(h.startswith("os_sessao=;") for h in sair.headers.getlist("Set-Cookie"))


def test_fracttal_que_recusa_mostra_o_motivo(cliente, monkeypatch):
    from nexus.auth import fracttal

    def recusa(app, e, s):
        raise fracttal.LoginRecusado("E-mail ou senha incorretos.")
    monkeypatch.setattr(fracttal, "entrar", recusa)
    r = cliente.post("/entrar", data={"email": "pessoa@exemplo.test", "senha": "errada"})
    assert r.status_code == 401 and "E-mail ou senha incorretos." in r.get_data(as_text=True)
    assert cliente.get("/").status_code == 302


def test_tela_de_entrada_pede_o_fracttal_e_guarda_a_senha_de_admin(cliente):
    html = cliente.get("/entrar").get_data(as_text=True)
    assert "E-mail do Fracttal" in html and "Entrar com a senha de administrador" in html
    assert "Senha de administrador" in cliente.get("/entrar?admin=1").get_data(as_text=True)
