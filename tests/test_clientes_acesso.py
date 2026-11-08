"""O acesso dos clientes ao Nexus (07/11/2026, Levi: "Quero um acesso extra chamado 'clientes' onde eu boto o e-mail do
cliente avulso"; com ele, no mesmo dia: a senha nasce por um link de convite de uso único, e o cliente vê SÓ as usinas
dele). Seguram: o convite (uma vez, 7 dias), a senha só embaralhada e fora do banco, o login com trava, o portão que só
abre as telas marcadas para o setor Clientes que recortam pelo cliente, o cliente que vem da sessão e nunca do
endereço, e o acesso removido que cai no próximo clique. Nomes e e-mails inventados."""
import re
import time

import pytest
from test_campo_responsaveis import manut, tela  # noqa: F401  (fixtures)
from test_campo_visao import banco  # noqa: F401
from test_campo_visao_cliente_0511 import cliente_tela  # noqa: F401

from nexus.auth import clientes as CL
from nexus.auth import setor_telas as ST
from nexus.cadastro import setor_ids as SID

EMAIL = "compras@cliente-exemplo.test"
URL = "/t/base/acessos"


@pytest.fixture
def dados(app, tmp_path):
    app.config["NEXUS_DADOS"] = str(tmp_path / "dados")
    ST.limpar()
    yield app.config
    ST.limpar()


def _codigo(c, url=URL + "?aba=clientes"):
    # o da tela (dentro do <main>), não o do card do Modo cliente da casca
    html = c.get(url).get_data(as_text=True)
    return re.search(r'name="codigo" value="([^"]+)"', html.split("<main", 1)[1]).group(1)


def _token(link: str) -> str:
    return link.split("convite=", 1)[1]


def test_o_convite_a_senha_e_a_conferencia(app, dados):
    with app.test_request_context():
        e, token = CL.adicionar(dados, EMAIL.upper(), 1, "Thopen", "admin@exemplo.test")
        assert e == EMAIL and CL.conta_do_convite(dados, token)["email"] == EMAIL
        assert CL.conferir(dados, EMAIL, "qualquer coisa") is None                  # sem senha ainda, não entra
        for a, b in (("curta", "curta"), ("senha-boa-123", "outra-senha-123")):
            with pytest.raises(CL.Recusado):
                CL.definir_senha(dados, token, a, b)
        assert CL.definir_senha(dados, token, "uma senha boa 2026", "uma senha boa 2026") == EMAIL
        assert CL.conta_do_convite(dados, token) is None                            # o link vale uma vez
        with pytest.raises(CL.Recusado):
            CL.definir_senha(dados, token, "outra senha boa 99", "outra senha boa 99")
        assert CL.conferir(dados, EMAIL, "uma senha boa 2026")["cliente_id"] == 1
        assert CL.conferir(dados, EMAIL, "senha errada 2026") is None
        assert CL.conferir(dados, "ninguem@exemplo.test", "uma senha boa 2026") is None
        bruto = (dados["NEXUS_DADOS"] + "/clientes.json")
        texto = open(bruto, encoding="utf-8").read()
        assert "uma senha boa" not in texto and token not in texto and "scrypt$" in texto   # só o resumo
        # o link novo troca o velho; remover tira a senha e o convite
        novo = CL.gerar_link(dados, EMAIL, "admin@exemplo.test")
        assert CL.conta_do_convite(dados, novo) and CL.conta_ativa(dados, EMAIL, 1)
        CL.remover(dados, EMAIL, "admin@exemplo.test")
        assert not CL.conta_ativa(dados, EMAIL, 1) and CL.conta_do_convite(dados, novo) is None
        assert CL.conferir(dados, EMAIL, "uma senha boa 2026") is None


def test_o_cliente_ve_so_as_usinas_dele(app, dados, cliente_tela, logado):
    # o administrador cria a conta na aba Clientes e marca a Visão do cliente para o setor Clientes
    html = logado.get(URL + "?aba=clientes").get_data(as_text=True)
    assert "Dar acesso a um cliente" in html and '<option value="1">Thopen</option>' in html
    r = logado.post(URL, data={"codigo": _codigo(logado), "acao": "cliente_adicionar", "email": EMAIL, "cliente_id": "1"})
    assert r.status_code == 303
    html = logado.get(URL + "?aba=clientes").get_data(as_text=True)
    link = re.search(r'id="cli-link" type="text" readonly value="([^"]+)"', html).group(1)
    assert "/entrar?convite=" in link and "esperando a senha" in html
    assert 'id="cli-link"' not in logado.get(URL + "?aba=clientes").get_data(as_text=True)   # o link aparece uma vez
    # o setor Clientes na matriz (08/11/2026): toda tela se marca; a que ainda não recorta pelo cliente leva "falta o
    # filtro" e não abre para ele (a Central de atenção, marcada, segue fechada para o cliente)
    mat = logado.get(URL + f"?setor={SID.CLIENTES}").get_data(as_text=True)
    assert "Clientes" in mat and 'value="campo/cliente"' in mat and 'value="campo/atencao"' in mat
    item = mat[mat.index('value="campo/atencao"'):].split("</li>", 1)[0]
    assert "falta o filtro" in item and "falta o filtro" not in mat[mat.index('value="campo/cliente"'):].split("</li>", 1)[0]
    r = logado.post(URL, data={"codigo": _codigo(logado, URL), "acao": "telas_setor", "setor": str(SID.CLIENTES),
                               "tela": ["campo/cliente", "campo/atencao"]})
    assert r.status_code == 303
    assert "1 marcada espera o filtro por cliente" in logado.get(r.headers["Location"]).get_data(as_text=True)
    ST.limpar()
    # o cliente cria a senha pelo link e entra
    c = app.test_client()
    pag = c.get("/entrar?convite=" + _token(link)).get_data(as_text=True)
    assert "Crie a senha do acesso de <b>" + EMAIL in pag
    c.post("/entrar", data={"convite": _token(link), "senha": "senha do cliente 1", "senha2": "senha do cliente 1"})
    assert "não vale mais" in c.get("/entrar?convite=" + _token(link)).get_data(as_text=True)
    assert c.post("/entrar", data={"cliente_email": EMAIL, "cliente_senha": "errada errada"}).status_code == 401
    r = c.post("/entrar", data={"cliente_email": EMAIL, "cliente_senha": "senha do cliente 1"})
    assert r.status_code == 302
    with c.session_transaction() as s:
        assert s["via"] == "cliente" and s["cliente_id"] == 1 and not s["admin"]
    # o Início leva à tela dele; nela, o cliente da sessão, sem escolha, e o ?cliente= de outro é ignorado
    assert c.get("/").headers["Location"].endswith("/t/campo/cliente")
    html = c.get("/t/campo/cliente?cliente=2&usina=3").get_data(as_text=True)
    # o cabeçalho e o menu do próprio cliente (08/11/2026, o mockup): "Bom dia, Thopen", "Comando", só leitura
    assert re.search(r"(Bom dia|Boa tarde|Boa noite), Thopen</h1>", html) and "2 usinas no contrato" in html
    menu_c = html.split('<nav class="menu"', 1)[1].split("</nav>", 1)[0]
    assert "Acesso de cliente · só leitura" in menu_c and ">Comando</span>" in menu_c and "Sair do modo" not in menu_c
    assert '<h2 class="vc-nome">' not in html and 'id="vc-cliente"' not in html and 'id="vc-det-3"' not in html
    assert 'class="sino-topo"' not in html and "_nexus/sessao" not in html
    menu = re.findall(r'href="(/t/[^"]+)"', html.split('<nav class="menu"', 1)[1].split("</nav>", 1)[0])
    assert set(menu) <= {"/t/campo/cliente"}
    # a OS só leitura (08/11/2026): a do cliente abre, do banco; a de outro cliente não
    assert 'href="/t/campo/cliente/os/901"' in html
    card = c.get("/t/campo/cliente/os/901")
    pag = card.get_data(as_text=True)
    assert card.status_code == 200 and "OS 901" in pag and "só leitura" in pag and "<form" not in pag.split("<main", 1)[1]
    assert c.get("/t/campo/cliente/os/902").status_code == 404           # a OS 902 é da Coração 1, de outro cliente
    # nada fora da tela dele: telas da Grid, dados, o OS Creator, a gravação
    for url in ("/t/campo/atencao", "/t/comando/caixa-de-entrada", "/t/base/acessos", "/t/campo/responsaveis",
                "/os/", "/t/comando/conversa/pessoas", "/t/base/paleta"):
        assert c.get(url).status_code == 403, url
    assert c.post("/t/campo/cliente").status_code in (403, 405)
    # removido, cai no próximo clique
    logado.post(URL, data={"codigo": _codigo(logado), "acao": "cliente_remover", "email": EMAIL})
    r = c.get("/t/campo/cliente")
    assert r.status_code == 302 and "motivo=cliente_fim" in r.headers["Location"]


def test_a_sessao_do_cliente_dura_12_horas(app, dados, cliente_tela):
    with app.test_request_context():
        _e, token = CL.adicionar(dados, EMAIL, 1, "Thopen", "admin@exemplo.test")
        CL.definir_senha(dados, token, "senha do cliente 1", "senha do cliente 1")
    c = app.test_client()
    c.post("/entrar", data={"cliente_email": EMAIL, "cliente_senha": "senha do cliente 1"})
    with c.session_transaction() as s:
        assert time.time() + 11 * 3600 < s["cliente_ate"] <= time.time() + 12 * 3600 + 5
        s["cliente_ate"] = time.time() - 1
    r = c.get("/t/campo/cliente")
    assert r.status_code == 302 and "motivo=cliente_fim" in r.headers["Location"]


def test_a_trava_das_tentativas_do_cliente(app, dados):
    with app.test_request_context():
        _e, token = CL.adicionar(dados, EMAIL, 1, "Thopen", "admin@exemplo.test")
        CL.definir_senha(dados, token, "senha do cliente 1", "senha do cliente 1")
    c = app.test_client()
    for _ in range(5):
        assert c.post("/entrar", data={"cliente_email": EMAIL, "cliente_senha": "errada errada"}).status_code == 401
    r = c.post("/entrar", data={"cliente_email": EMAIL, "cliente_senha": "senha do cliente 1"})
    assert r.status_code == 429                                         # nem a certa passa até a janela acabar


def test_a_tela_de_entrar_oferece_o_acesso_de_cliente(cliente):
    html = cliente.get("/entrar").get_data(as_text=True)
    assert 'href="/entrar?cliente=1"' in html and "Sou cliente" in html
    pag = cliente.get("/entrar?cliente=1").get_data(as_text=True)
    assert 'name="cliente_email"' in pag and 'name="cliente_senha"' in pag
    assert "não vale mais" in cliente.get("/entrar?convite=inventado").get_data(as_text=True)


def test_o_modo_cliente_do_administrador(app, dados, cliente_tela, logado):
    """07/11/2026, Levi: no menu do nome, "Modo Cliente" abre um card (fundo desfocado) para escolher o cliente; o
    administrador vê o Nexus como ele veria; no menu lateral, "Sair do modo cliente"."""
    with app.test_request_context():
        ST.gravar(SID.CLIENTES, ["campo/cliente"], ST.telas_do_cliente_possiveis(), dados, "http://pg.falso",
                  app.extensions["nexus_dados_sessao"], "admin@exemplo.test")
    ST.limpar()
    html = logado.get("/t/base/acessos").get_data(as_text=True)
    assert "data-abre-modo-cliente" in html and 'id="modo-cliente-card"' in html and "Sair do modo cliente" not in html
    lista = logado.get("/t/base/modo-cliente/clientes").get_json()
    assert {"id": 1, "nome": "Thopen", "usinas": 2} in lista["clientes"]
    codigo = re.search(r'data-codigo="([^"]+)"', html.split('id="modo-cliente-card"', 1)[1]).group(1)
    assert 'name="cliente_id"' not in html                              # o card só se monta ao abrir
    assert logado.post("/t/base/modo-cliente", data={"codigo": "errado", "cliente_id": "1"}).status_code == 403
    assert logado.post("/t/base/modo-cliente", data={"codigo": codigo, "cliente_id": "999"}).status_code == 400
    assert logado.post("/t/base/modo-cliente", data={"codigo": codigo, "cliente_id": "1"}).status_code == 303
    # agora ele vê como o cliente: o Início leva à tela dele, o cliente é o do modo, o resto fecha, sem sino
    assert logado.get("/").headers["Location"].endswith("/t/campo/cliente")
    pag = logado.get("/t/campo/cliente?cliente=2").get_data(as_text=True)
    assert ", Thopen</h1>" in pag and 'id="vc-cliente"' not in pag and 'class="sino-topo"' not in pag
    menu = pag.split('<nav class="menu"', 1)[1].split("</nav>", 1)[0]
    assert "<b>Thopen</b>Modo cliente · só leitura" in menu and "Sair do modo cliente" in menu
    assert ">Comando</span>" in menu and ">Início</span>" not in menu        # o menu do cliente (o mockup)
    assert 'id="modo-cliente-card"' not in pag
    assert logado.get("/t/base/acessos").status_code == 403 and logado.get("/t/comando/insights").status_code == 403
    # sai pelo menu lateral e volta ao Nexus inteiro
    assert logado.post("/t/base/modo-cliente/sair", data={"codigo": codigo}).status_code == 303
    assert logado.get("/t/base/acessos").status_code == 200


def test_quem_nao_e_administrador_nao_entra_no_modo(app, dados, cliente_tela):
    c = app.test_client()
    with c.session_transaction() as s:
        s.update(logado=True, admin=False, usuario={"email": "pessoa@exemplo.test", "nome": "Pessoa"}, casca_codigo="x")
    assert c.post("/t/base/modo-cliente", data={"codigo": "x", "cliente_id": "1"}).status_code == 403
    assert c.get("/t/base/modo-cliente/clientes").status_code == 403
    with c.session_transaction() as s:
        s["modo_cliente"] = {"id": 1, "nome": "Thopen"}               # forjado sem ser administrador: não vale
        assert "modo_cliente" in s
    assert "Sair do modo cliente" not in c.get("/").get_data(as_text=True)


def test_o_mes_escolhido_no_topo(app, dados, cliente_tela):
    """08/11/2026, Levi: "Gostaria que tivesse um filtro de mês!" (no topo, vale para todas as telas do cliente). Na Visão
    do cliente, o mês muda a performance (o Gerencial daquele mês); o resto é de agora, e a tela diz."""
    with app.test_request_context():
        ST.gravar(SID.CLIENTES, ["campo/cliente"], ST.telas_do_cliente_possiveis(), dados, "http://pg.falso",
                  app.extensions["nexus_dados_sessao"], "admin@exemplo.test")
        _e, token = CL.adicionar(dados, EMAIL, 1, "Thopen", "admin@exemplo.test")
        CL.definir_senha(dados, token, "senha do cliente 1", "senha do cliente 1")
    ST.limpar()
    c = app.test_client()
    c.post("/entrar", data={"cliente_email": EMAIL, "cliente_senha": "senha do cliente 1"})
    html = c.get("/t/campo/cliente").get_data(as_text=True)
    topo = html.split('class="cli-mes"', 1)[1].split("</form>", 1)[0]
    meses = re.findall(r'<option value="(\d{4}-\d\d)"', topo)
    assert len(meses) == 12 and "Performance do mês" in html and "Mês de <b>" not in html
    codigo = re.search(r'name="codigo" value="([^"]+)"', topo).group(1)
    r = c.post("/t/base/cliente-mes", data={"codigo": codigo, "mes": meses[1], "volta": "/t/campo/cliente"})
    assert r.status_code == 303 and r.headers["Location"].endswith("/t/campo/cliente")
    html = c.get("/t/campo/cliente").get_data(as_text=True)
    assert "Mês de <b>" in html and "Performance de " in html and f'value="{meses[1]}" selected' in html
    c.post("/t/base/cliente-mes", data={"codigo": codigo, "mes": "1999-01", "volta": "/t/campo/cliente"})
    assert f'value="{meses[1]}" selected' in c.get("/t/campo/cliente").get_data(as_text=True)   # fora da janela: não muda


def test_as_rondas_na_versao_do_cliente(app, dados, cliente_tela, monkeypatch):
    """As Rondas do cliente (08/11/2026): só as usinas dele, no mês do topo, sem técnico; as sub-rotas da tela da Grid
    (a página da usina, o CSV) não abrem para ele."""
    from nexus.campo import visao
    from nexus.campo import versao_cliente as VCL
    hoje = visao._agora().date()
    dados_r = {"todas": [
        {"usina_id": 1, "usina": "Altair", "data": hoje.isoformat(), "tipo": "Ronda", "os": 7001, "pendencia": "",
         "tecnico": "Técnico Secreto"},
        {"usina_id": 3, "usina": "Coração 1", "data": hoje.isoformat(), "tipo": "Ronda", "os": 7002, "pendencia": "",
         "tecnico": "Outro"}],
        "cobertura": [{"usina_id": 1, "usina": "Altair", "ultima": hoje.isoformat(), "dias": 0},
                      {"usina_id": 2, "usina": "Brodowski 1", "ultima": None, "dias": 999},
                      {"usina_id": 3, "usina": "Coração 1", "ultima": hoje.isoformat(), "dias": 0}]}
    r = VCL.rondas(dados_r, {1, 2}, hoje.replace(day=1))
    assert [x["usina"] for x in r["linhas"]] == ["Altair"] and "Técnico" not in str(r)
    assert [c["usina"] for c in r["cobertura"]] == ["Brodowski 1", "Altair"] and r["atrasadas"] == 1
    # pela tela, logado como cliente
    from nexus.campo import leitura as LE
    monkeypatch.setattr(visao, "rondas", lambda *a, **k: LE.Leitura(dados_r, 0))
    with app.test_request_context():
        ST.gravar(SID.CLIENTES, ["campo/cliente", "campo/rondas"], ST.telas_do_cliente_possiveis(), dados,
                  "http://pg.falso", app.extensions["nexus_dados_sessao"], "admin@exemplo.test")
        _e, token = CL.adicionar(dados, EMAIL, 1, "Thopen", "admin@exemplo.test")
        CL.definir_senha(dados, token, "senha do cliente 1", "senha do cliente 1")
    ST.limpar()
    c = app.test_client()
    c.post("/entrar", data={"cliente_email": EMAIL, "cliente_senha": "senha do cliente 1"})
    html = c.get("/t/campo/rondas?cliente=Outro%20Cliente").get_data(as_text=True)
    assert "Rondas nas suas usinas" in html and "Altair" in html and "Coração 1" not in html
    assert "Técnico Secreto" not in html and 'href="/t/campo/cliente/os/7001?volta=/t/campo/rondas"' in html
    menu = html.split('<nav class="menu"', 1)[1].split("</nav>", 1)[0]
    assert ">Rondas</span>" in menu
    assert c.get("/t/campo/rondas/usina/1").status_code == 403         # a página da usina é da Grid
