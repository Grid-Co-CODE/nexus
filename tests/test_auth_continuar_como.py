"""O "Continuar como" na tela de entrar (14/11/2026, Levi, depois do App de Campo, a v350: "quando o cara já conectou no
Microsoft, para ele não precisar ficar logando de novo no Microsoft, só tem um botão lá de continuar como pessoa tal
[...] Porque às vezes desconecta sozinho"). A escolha dele, entre três: "Sem senha no PC marcado".

O que estes testes seguram: a marca "Este computador é só meu" na entrada pela Microsoft grava o cookie assinado
`nexus_lembrar` (30 dias); com ele, o Entrar mostra "Continuar como" (primeiro e último nome, e o e-mail), que vai à
Microsoft sem tela (`prompt=none`, `login_hint` do cookie, nunca do endereço); a sessão da Microsoft caída leva à senha
com o e-mail preenchido, sem contar como recusa; sem tela, outra conta não entra e desmarca; a entrada sem a marca, o
Sair do Nexus e o do OS Creator desmarcam; a sessão do Nexus que vence (as 12 h) não. Sem a marca, nada muda: a senha
da Microsoft em toda entrada (o PC da sala do NOC). A Microsoft é a de mentira do test_auth_microsoft."""
import time
from urllib.parse import parse_qs, urlsplit

from itsdangerous import URLSafeTimedSerializer
from test_auth_microsoft import EMAIL, _b64, _claims, fake, ms  # noqa: F401  (fixtures)

from nexus.auth import COOKIE_LEMBRAR, LEMBRAR_S, TEXTO_OUTRA_CONTA

OUTRO = "outra.pessoa@gridco.com.br"


def _ida(cliente, query):
    r = cliente.get("/entrar?" + query)
    assert r.status_code == 302, r.status_code
    q = {k: v[0] for k, v in parse_qs(urlsplit(r.headers["Location"]).query).items()}
    with cliente.session_transaction() as s:
        pedido = dict(s["ms_pedidos"][q["state"]])
    return r, q, pedido


def _volta(cliente, fake, pedido, **mudar):
    fake.resposta = (200, {"id_token": f"{_b64({'alg': 'RS256'})}.{_b64(_claims(pedido['nonce'], **mudar))}.assin"})
    return cliente.get(f"/entrar?code=codigo-de-teste&state={pedido['state']}")


def _cookie(r) -> str:
    return next((h for h in r.headers.getlist("Set-Cookie") if h.startswith(COOKIE_LEMBRAR + "=")), "")


def _apagou(r) -> bool:
    c = _cookie(r)
    return c.startswith(COOKIE_LEMBRAR + "=;") and "Max-Age=0" in c


def _venceu(cliente):
    """A sessão do Nexus caiu (as 12 h, o cookie da sessão perdido): o navegador segue com a marca."""
    with cliente.session_transaction() as s:
        s.clear()


def _marcar(cliente, fake, **mudar):
    _r, q, pedido = _ida(cliente, "ms=1&lembrar=1")
    assert pedido["lembrar"] is True and q["prompt"] == "login" and "login_hint" not in q
    r = _volta(cliente, fake, pedido, **mudar)
    assert r.status_code == 302
    return r


def test_sem_a_marca_a_tela_de_sempre_com_a_caixa_de_marcar(ms, cliente):
    html = cliente.get("/entrar?next=/t/cos/mesa").get_data(as_text=True)
    assert "Continuar como" not in html and "Entrar com a Microsoft" in html
    assert 'name="lembrar"' in html and 'for="lembrar"' in html and "Este computador é só meu" in html
    assert '<input type="hidden" name="ms" value="1">' in html and 'name="next" value="/t/cos/mesa"' in html
    # sem a marca, a ida é a de sempre: a senha da Microsoft, sem e-mail preenchido
    _r, q, pedido = _ida(cliente, "ms=1")
    assert q["prompt"] == "login" and q["domain_hint"] == "gridco.com.br" and "login_hint" not in q
    assert "lembrar" not in pedido and "continuar" not in pedido


def test_a_marca_grava_o_cookie_e_o_entrar_mostra_continuar_como(ms, cliente, fake):
    r = _marcar(cliente, fake, name="Pessoa do Meio Teste")
    c = _cookie(r)
    assert f"Max-Age={LEMBRAR_S}" in c and "HttpOnly" in c and "SameSite=Lax" in c and "Path=/" in c
    _venceu(cliente)
    html = cliente.get("/entrar").get_data(as_text=True)
    assert "Continuar como Pessoa Teste<small>pessoa.teste@gridco.com.br</small>" in html   # o primeiro e o último
    assert 'href="/entrar?ms=1&continuar=1"' in html and "Entrar com outra conta" in html
    assert "Entrar com a senha de administrador" in html                                   # a reserva segue


def test_o_continuar_vai_sem_senha_com_o_email_do_cookie_e_entra(ms, cliente, fake):
    _marcar(cliente, fake)
    _venceu(cliente)
    r, q, pedido = _ida(cliente, "ms=1&continuar=1&next=/t/cos/mesa")
    assert q["prompt"] == "none" and q["login_hint"] == EMAIL and "domain_hint" not in q
    assert pedido["continuar"] == EMAIL and pedido["lembrar"] is True and r.headers["Cache-Control"] == "no-store"
    r = _volta(cliente, fake, pedido)
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/cos/mesa")
    assert f"Max-Age={LEMBRAR_S}" in _cookie(r)                          # a marca renova os 30 dias
    with cliente.session_transaction() as s:
        assert s["logado"] and s["via"] == "microsoft" and s["usuario"]["email"] == EMAIL


def test_sem_a_marca_o_continuar_do_endereco_e_a_entrada_de_sempre(ms, cliente, app):
    # sem cookie: o "continuar=1" do endereço não vira login_hint nem prompt=none
    _r, q, pedido = _ida(cliente, "ms=1&continuar=1")
    assert q["prompt"] == "login" and "login_hint" not in q and "continuar" not in pedido
    # cookie com outra chave, ou com e-mail de fora da Grid: ninguém no botão
    falso = URLSafeTimedSerializer("outra-chave", salt="nexus-lembrar").dumps({"email": EMAIL, "nome": "X"})
    cliente.set_cookie(COOKIE_LEMBRAR, falso)
    assert "Continuar como" not in cliente.get("/entrar").get_data(as_text=True)
    de_fora = URLSafeTimedSerializer(app.secret_key, salt="nexus-lembrar").dumps({"email": "a@fora.test", "nome": "A"})
    cliente.set_cookie(COOKIE_LEMBRAR, de_fora)
    assert "Continuar como" not in cliente.get("/entrar").get_data(as_text=True)
    assert _ida(cliente, "ms=1&continuar=1")[1]["prompt"] == "login"


def test_a_sessao_da_microsoft_caida_leva_a_senha_com_o_email_preenchido(ms, cliente, fake):
    _marcar(cliente, fake)
    _venceu(cliente)
    fake.pedidos.clear()
    _r, _q, pedido = _ida(cliente, "ms=1&continuar=1&next=/t/cos/mesa")
    r = cliente.get(f"/entrar?error=login_required&error_description=AADSTS50058&state={pedido['state']}")
    assert r.status_code == 302
    q = {k: v[0] for k, v in parse_qs(urlsplit(r.headers["Location"]).query).items()}
    assert q["prompt"] == "login" and q["login_hint"] == EMAIL and q["state"] != pedido["state"]
    assert not fake.pedidos                                              # nenhum código trocado
    assert ("ms", "127.0.0.1") not in cliente.application.extensions["nexus_erros_login"]   # não conta como recusa
    with cliente.session_transaction() as s:
        novo = dict(s["ms_pedidos"][q["state"]])
    assert novo["dica"] == EMAIL and novo["lembrar"] is True and novo["next"] == "/t/cos/mesa"
    r = _volta(cliente, fake, novo)
    assert r.status_code == 302 and f"Max-Age={LEMBRAR_S}" in _cookie(r)
    # a mesma volta de erro numa ida de sempre (sem o Continuar) é recusa, como antes
    _r, _q, comum = _ida(cliente, "ms=1")
    assert cliente.get(f"/entrar?error=login_required&state={comum['state']}").status_code == 403


def test_sem_tela_outra_conta_nao_entra_e_desmarca(ms, cliente, fake):
    _marcar(cliente, fake)
    _venceu(cliente)
    _r, _q, pedido = _ida(cliente, "ms=1&continuar=1")
    r = _volta(cliente, fake, pedido, email=OUTRO, preferred_username=OUTRO)
    assert r.status_code == 403 and TEXTO_OUTRA_CONTA in r.get_data(as_text=True) and _apagou(r)
    with cliente.session_transaction() as s:
        assert not s.get("logado")


def test_na_senha_com_o_email_preenchido_pode_trocar_de_conta_e_a_marca_sai(ms, cliente, fake):
    _marcar(cliente, fake)
    _venceu(cliente)
    _r, _q, pedido = _ida(cliente, "ms=1&continuar=1")
    r = cliente.get(f"/entrar?error=interaction_required&state={pedido['state']}")
    novo_state = parse_qs(urlsplit(r.headers["Location"]).query)["state"][0]
    with cliente.session_transaction() as s:
        novo = dict(s["ms_pedidos"][novo_state])
    r = _volta(cliente, fake, novo, email=OUTRO, preferred_username=OUTRO, name="Outra Pessoa")
    assert r.status_code == 302 and _apagou(r)                           # entrou com a senha dela; a marca do outro sai
    with cliente.session_transaction() as s:
        assert s["usuario"]["email"] == OUTRO


def test_a_entrada_sem_a_marca_desmarca(ms, cliente, fake):
    _marcar(cliente, fake)
    _venceu(cliente)
    _r, _q, pedido = _ida(cliente, "ms=1")
    assert _apagou(_volta(cliente, fake, pedido))
    _venceu(cliente)
    assert "Continuar como" not in cliente.get("/entrar").get_data(as_text=True)


def test_a_sessao_que_vence_mantem_a_marca_e_o_sair_desmarca(ms, cliente, fake):
    _marcar(cliente, fake)
    with cliente.session_transaction() as s:
        s["ms_ate"] = time.time() - 1                                    # as 12 h passaram
    r = cliente.get("/t/cos/mesa")
    assert r.status_code == 302 and "motivo=expirou" in r.headers["Location"] and not _cookie(r)
    assert "Continuar como Pessoa Teste" in cliente.get("/entrar").get_data(as_text=True)
    # entra pelo Continuar e sai pelo Sair do Nexus: o botão some
    _r, _q, pedido = _ida(cliente, "ms=1&continuar=1")
    _volta(cliente, fake, pedido)
    assert _apagou(cliente.get("/sair"))
    assert "Continuar como" not in cliente.get("/entrar").get_data(as_text=True)


def test_o_sair_do_os_creator_tambem_desmarca(ms, cliente, fake):
    _marcar(cliente, fake)
    r = cliente.get("/os/logout")
    assert r.status_code == 302 and "motivo=saiu" in r.headers["Location"] and _apagou(r)


def test_com_a_microsoft_desligada_o_cookie_nao_mostra_nada(app, cliente):
    cookie = URLSafeTimedSerializer(app.secret_key, salt="nexus-lembrar").dumps({"email": EMAIL, "nome": "Pessoa"})
    cliente.set_cookie(COOKIE_LEMBRAR, cookie)
    html = cliente.get("/entrar").get_data(as_text=True)
    assert "Continuar como" not in html and "E-mail do Fracttal" in html
