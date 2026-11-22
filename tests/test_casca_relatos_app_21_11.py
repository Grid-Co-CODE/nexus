"""Os relatos do App de Campo nas Sugestões do Início (21/11/2026). Levi, pelo chat do App: "os relatos do pessoal de
campo, que é muito importante. Podia até ficar ali no início do Nexus"; no chat do Nexus escolheu o caminho A (o App
continua a fonte; o Nexus lê e responde pelo servidor do App), "Administradores" respondem e, por fim, "pode ir para
sugestões no início com uma tag de App de campo!".

O que estes testes seguram: sem a chave o Nexus nem chama o App e o administrador lê o porquê; com ela, o relato entra
nas Sugestões recebidas com a etiqueta "App de campo", o tipo no título, o status do App e as mensagens; quem não é
administrador não vê relato nem faz o App ser chamado; a resposta vai ao App (com a chave, a pessoa e o id que segura o
2º envio) e só com login; o App que recusa ou não responde vira aviso, nunca erro 500; a chave nunca vai ao HTML; o
contador do Início soma os relatos que esperam a Grid. App falso; nomes fictícios."""
import io
import json
import urllib.error

import pytest
from test_campo_visao import banco  # noqa: F401  (fixture)

from nexus.auth import chaves as CH
from nexus.casca import relatos_app as R
from nexus.casca import sugestoes as S

URL = "/?aba=sugestoes"
CHAVE = "k" * 40
ADMIN = {"email": "admin.teste@exemplo.test", "nome": "Admin de Teste", "perfil": ""}
PESSOA = {"email": "fulana@exemplo.test", "nome": "Fulana de Teste", "perfil": ""}


def _relato(**kw):
    r = {"id": "fb-0001", "tipo": "problema", "texto": "A tela de OS trava ao anexar a foto.\nAconteceu duas vezes hoje.",
         "tela": "OS", "status": "aberto", "criado_em": "2026-11-21T13:05:00Z", "atualizado_em": "2026-11-21T13:05:00Z",
         "autor": {"nome": "Tecnico de Teste", "email": "tecnico.teste@exemplo.test", "papel": "Tecnico",
                   "funcao": "Eletricista"},
         "versao_app": "v365", "aparelho": "Android 14 · Moto de teste", "mensagens": []}
    r.update(kw)
    return r


class _AppFalso:
    """O servidor do App de mentira: guarda os pedidos e responde o que o teste mandar."""
    def __init__(self, relatos=None, status_get=200, status_post=200, corpo_post=None, fora=False, versao=1):
        self.relatos = relatos if relatos is not None else [_relato()]
        self.status_get, self.status_post, self.corpo_post = status_get, status_post, corpo_post
        self.fora, self.versao = fora, versao
        self.pedidos = []

    def __call__(self, req, timeout=None):
        corpo = req.data.decode("utf-8") if req.data else ""
        self.pedidos.append({"metodo": req.get_method(), "url": req.full_url,
                             "chave": req.get_header("X-nexus-chave"), "corpo": json.loads(corpo) if corpo else None})
        if self.fora:
            raise urllib.error.URLError("sem rede")
        if req.get_method() == "GET":
            cod, dados = self.status_get, {"versao": self.versao, "relatos": self.relatos}
        else:
            cod = self.status_post
            dados = self.corpo_post if self.corpo_post is not None else {"relato": _relato(status="respondido")}
        if cod != 200:
            raise urllib.error.HTTPError(req.full_url, cod, "erro", {}, io.BytesIO(json.dumps(dados).encode()))
        return io.BytesIO(json.dumps(dados).encode("utf-8"))


@pytest.fixture
def app_falso(app, banco, monkeypatch, tmp_path):
    app.config["NEXUS_DADOS"] = str(tmp_path / "dados")
    app.config["NEXUS_APP_RELATOS_CHAVE"] = CHAVE
    app.config["NEXUS_ADMINS"] = ADMIN["email"]    # o portão segue a lista a cada pedido
    S.limpar()
    R.limpar()
    falso = _AppFalso()
    monkeypatch.setattr(R, "_abrir", falso)
    yield falso
    R.limpar()
    S.limpar()


def _cliente(app, admin=False, usuario=ADMIN):
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"] = True
        s["admin"] = admin
        if usuario:
            s["usuario"] = dict(usuario)
    return c


def _codigo(html: str) -> str:
    return html.split('name="codigo" value="', 1)[1].split('"', 1)[0]


# ── a lista ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_sem_a_chave_o_nexus_nao_chama_o_app_e_o_administrador_le_o_porque(app, banco, monkeypatch, tmp_path):
    app.config["NEXUS_DADOS"] = str(tmp_path / "dados")
    app.config.pop("NEXUS_APP_RELATOS_CHAVE", None)
    app.config["NEXUS_ADMINS"] = ADMIN["email"]
    R.limpar()
    falso = _AppFalso()
    monkeypatch.setattr(R, "_abrir", falso)
    html = _cliente(app, admin=True).get(URL).get_data(as_text=True)
    assert falso.pedidos == []
    assert "Os relatos do App de Campo ainda não chegam aqui" in html
    assert "Chaves do Nexus" in html


def test_o_relato_entra_nas_recebidas_com_a_etiqueta_app_de_campo(app, app_falso):
    html = _cliente(app, admin=True).get(URL).get_data(as_text=True)
    assert app_falso.pedidos[0]["metodo"] == "GET"
    assert app_falso.pedidos[0]["url"].endswith("/api/app/nexus/relatos")
    assert app_falso.pedidos[0]["chave"] == CHAVE
    assert 'id="sug-app-fb-0001"' in html
    assert 'class="atu-area sug-tag-app"' in html and ">App de campo<" in html
    assert 'data-sug-area="_app"' in html
    assert "Tecnico de Teste" in html
    assert "Problema: A tela de OS trava ao anexar a foto." in html
    assert "Aconteceu duas vezes hoje." in html
    assert "gc-status--info\">Aberto<" in html
    assert "Eletricista" in html and "v365" in html and "Tela: OS" in html
    # o filtro e o contador por setor ganham o App de campo como um setor
    assert ">App de campo (1)</option>" in html
    # o status do relato é do App: aqui não se troca, e o aviso diz quem encerra
    trecho = html.split('id="sug-app-fb-0001"', 1)[1].split("</li>", 1)[0]
    assert 'name="status"' not in trecho
    assert "Só quem relatou encerra, pelo App" in trecho
    assert CHAVE not in html


def test_as_mensagens_do_relato_aparecem_na_ordem_com_quem_escreveu(app, app_falso):
    app_falso.relatos = [_relato(status="reaberto", mensagens=[
        {"id": "m1", "texto": "Já atualizamos o App, tente de novo.", "lado": "grid",
         "por": {"nome": "Admin de Teste"}, "em": "2026-11-21T14:00:00Z"},
        {"id": "m2", "texto": "Continua travando.", "lado": "campo",
         "por": {"nome": "Tecnico de Teste"}, "em": "2026-11-21T15:00:00Z"}])]
    html = _cliente(app, admin=True).get(URL).get_data(as_text=True)
    trecho = html.split('id="sug-app-fb-0001"', 1)[1].split("</li>", 1)[0]
    assert trecho.index("Já atualizamos o App") < trecho.index("Continua travando.")
    assert "Resposta de Admin de Teste" in trecho
    assert "Tecnico de Teste (no App)" in trecho
    assert "gc-status--alerta\">Reaberto<" in trecho
    assert 'class="sug-n-resp"' in trecho          # 1 resposta da Grid


def test_quem_nao_e_administrador_nao_ve_relato_nem_chama_o_app(app, app_falso):
    html = _cliente(app, admin=False, usuario=PESSOA).get(URL).get_data(as_text=True)
    assert app_falso.pedidos == []
    assert "sug-app-" not in html and "Tecnico de Teste" not in html


def test_o_resolvido_vai_para_o_fim_como_a_concluida(app, app_falso):
    app_falso.relatos = [_relato(id="fb-velho", status="resolvido", criado_em="2026-11-21T16:00:00Z"),
                         _relato(id="fb-novo", status="aberto", criado_em="2026-11-20T10:00:00Z")]
    html = _cliente(app, admin=True).get(URL).get_data(as_text=True)
    assert html.index('id="sug-app-fb-novo"') < html.index('id="sug-app-fb-velho"')
    assert "gc-status--ok\">Resolvido<" in html


def test_o_contrato_errado_ou_o_relato_incompleto_nao_derrubam_a_pagina(app, app_falso):
    app_falso.versao = 2
    resp = _cliente(app, admin=True).get(URL)
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert "Não li os relatos do App agora" in html and "versão 2 do contrato" in html
    R.limpar()
    app_falso.versao = 1
    app_falso.relatos = [_relato(id="../fora"), {"id": "fb-2"}, _relato(id="fb-3")]
    html = _cliente(app, admin=True).get(URL).get_data(as_text=True)
    assert 'id="sug-app-fb-3"' in html
    assert "sug-app-fb-2" not in html and "fora" not in html.split("sug-recebidas", 1)[1].split("sug-setores", 1)[0]


def test_o_app_fora_mostra_a_ultima_lista_boa_com_o_aviso(app, app_falso):
    c = _cliente(app, admin=True)
    c.get(URL)
    app_falso.fora = True
    R.envelhecer()
    html = c.get(URL).get_data(as_text=True)
    assert 'id="sug-app-fb-0001"' in html
    assert "Não li os relatos do App agora (o App não respondeu" in html


# ── a resposta ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _responder(c, texto="Obrigado, vamos olhar hoje.", **kw):
    html = c.get(URL).get_data(as_text=True)
    trecho = html.split('id="sug-app-fb-0001"', 1)[1].split("</li>", 1)[0]
    novo = trecho.split('name="novo_id" value="', 1)[1].split('"', 1)[0]
    form = {"codigo": _codigo(html), "relato": "fb-0001", "resposta": texto, "novo_id": novo}
    form.update(kw)
    return c.post(URL + "&acao=responder_app", data=form, headers={"Origin": "http://localhost"}), novo


def test_a_resposta_vai_ao_app_com_a_chave_a_pessoa_e_o_id(app, app_falso):
    c = _cliente(app, admin=True)
    resp, novo = _responder(c)
    assert resp.status_code == 302 and resp.headers["Location"].endswith("#sug-app-fb-0001")
    post = [p for p in app_falso.pedidos if p["metodo"] == "POST"]
    assert len(post) == 1
    assert post[0]["url"].endswith("/api/app/nexus/relatos/fb-0001/responder")
    assert post[0]["chave"] == CHAVE
    assert post[0]["corpo"] == {"resposta_id": novo, "texto": "Obrigado, vamos olhar hoje.",
                                "por": {"nome": "Admin de Teste", "email": "admin.teste@exemplo.test"}}
    html = c.get(URL).get_data(as_text=True)
    assert "Resposta enviada ao App: o técnico lê em Meus relatos." in html
    # a lista foi relida depois da resposta (a cópia velha não fica)
    assert sum(1 for p in app_falso.pedidos if p["metodo"] == "GET") >= 2


def test_sem_login_o_administrador_pela_senha_nao_responde(app, app_falso):
    c = _cliente(app, admin=True, usuario=None)
    html = c.get(URL).get_data(as_text=True)
    trecho = html.split('id="sug-app-fb-0001"', 1)[1].split("</li>", 1)[0]
    assert "Entre com o seu login" in trecho and 'acao=responder_app' not in trecho
    with c.session_transaction() as s:              # sem login não há formulário na página: o código vem da sessão
        s["sugestoes_codigo"] = "abc"
    resp = c.post(URL + "&acao=responder_app", data={"codigo": "abc", "relato": "fb-0001", "resposta": "x",
                                                     "novo_id": "r0123456789a"}, headers={"Origin": "http://localhost"})
    assert resp.status_code == 302
    assert not [p for p in app_falso.pedidos if p["metodo"] == "POST"]
    assert "a resposta vai ao técnico com o seu nome" in c.get(URL).get_data(as_text=True)


def test_quem_nao_e_administrador_nao_responde(app, app_falso):
    c = _cliente(app, admin=False, usuario=PESSOA)
    resp = c.post(URL + "&acao=responder_app", data={"relato": "fb-0001", "resposta": "x"},
                  headers={"Origin": "http://localhost"})
    assert resp.status_code == 403
    assert app_falso.pedidos == []


def test_outro_site_ou_formulario_vencido_nao_respondem(app, app_falso):
    c = _cliente(app, admin=True)
    _responder(c, codigo="vencido")
    _responder(c, )                                        # o certo, para comparar
    post = [p for p in app_falso.pedidos if p["metodo"] == "POST"]
    assert len(post) == 1
    resp = c.post(URL + "&acao=responder_app", data={"relato": "fb-0001", "resposta": "x"},
                  headers={"Origin": "https://outro.exemplo.test"})
    assert resp.status_code == 302
    assert len([p for p in app_falso.pedidos if p["metodo"] == "POST"]) == 1


@pytest.mark.parametrize("cod,corpo,trecho", [
    (404, {"erro": "relato não existe"}, "relato não existe"),
    (409, {"erro": "o relato já foi resolvido pelo técnico"}, "o relato já foi resolvido pelo técnico"),
    (401, {}, "o App recusou a chave do Nexus"),
    (500, {}, "o App respondeu 500"),
])
def test_o_app_que_recusa_a_resposta_vira_aviso(app, app_falso, cod, corpo, trecho):
    app_falso.status_post, app_falso.corpo_post = cod, corpo
    c = _cliente(app, admin=True)
    resp, _ = _responder(c)
    assert resp.status_code == 302
    html = c.get(URL).get_data(as_text=True)
    assert trecho in html and "A resposta não foi enviada" in html


def test_o_app_fora_na_resposta_vira_aviso(app, app_falso):
    c = _cliente(app, admin=True)
    c.get(URL)
    app_falso.fora = True
    resp, _ = _responder(c)
    assert resp.status_code == 302
    assert "o App não respondeu" in c.get(URL).get_data(as_text=True)


def test_resposta_vazia_ou_longa_demais_nao_vai(app, app_falso):
    c = _cliente(app, admin=True)
    _responder(c, texto="   ")
    _responder(c, texto="x" * (S.RESPOSTA_MAX + 1))
    assert not [p for p in app_falso.pedidos if p["metodo"] == "POST"]


# ── o contador e as chaves ──────────────────────────────────────────────────────────────────────────────────────────
def test_o_contador_do_administrador_soma_os_relatos_que_esperam_a_grid(app, app_falso):
    app_falso.relatos = [_relato(id="a1", status="aberto"), _relato(id="a2", status="reaberto"),
                         _relato(id="a3", status="respondido"), _relato(id="a4", status="resolvido")]
    with app.test_request_context("/"):
        assert R.esperando() == 2
    html = _cliente(app, admin=True).get("/").get_data(as_text=True)
    # nenhuma sugestão no banco falso: o número da aba são os 2 relatos que esperam a Grid
    num = html.split('class="sug-contador"', 1)[1].split(">", 1)[1].split("<", 1)[0]
    assert num.strip() == "2"
    # quem não é administrador não conta relato (nem faz o App ser chamado)
    R.limpar()
    antes = len(app_falso.pedidos)
    html = _cliente(app, admin=False, usuario=PESSOA).get("/").get_data(as_text=True)
    assert len(app_falso.pedidos) == antes


def test_as_duas_chaves_moram_na_tela_de_chaves_e_a_curta_e_recusada():
    assert "NEXUS_APP_RELATOS_CHAVE" in CH.CHAVES and "NEXUS_APP_RELATOS_URL" in CH.CHAVES
    with pytest.raises(CH.Recusada):
        CH.CHAVES["NEXUS_APP_RELATOS_CHAVE"]["conferir"]("curta")
    with pytest.raises(CH.Recusada):
        CH.CHAVES["NEXUS_APP_RELATOS_URL"]["conferir"]("http://sem-tls.exemplo.test/api")
    assert "caracteres" in CH.CHAVES["NEXUS_APP_RELATOS_CHAVE"]["conferir"]("z" * 40)


# ── o filtro Tipo de demanda (21/11/2026, Levi: "nas sugestões deve dar para filtrar o Tipo de demanda Nexus/App de
# campo!") ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_filtro_tipo_de_demanda_separa_nexus_e_app_de_campo(app, app_falso):
    app_falso.relatos = [_relato(id="fb-1"), _relato(id="fb-2", status="resolvido")]
    html = _cliente(app, admin=True).get(URL).get_data(as_text=True)
    filtro = html.split('data-sug-filtro="origem"', 1)[1].split("</select>", 1)[0]
    assert ">App de campo (2)</option>" in filtro
    assert ">Nexus (0)</option>" not in filtro          # sem sugestão no banco falso, a opção Nexus não aparece
    assert "Tipo de demanda" in html.split('data-sug-filtro="origem"', 1)[0][-300:]
    assert html.count('data-sug-origem="app"') == 2
    # o script da página lê a origem junto com o setor e quem solicitou
    script = next(s for s in html.split("<script>")[1:] if "sug-lista > li[data-sug-area]" in s)
    assert 'data-sug-filtro="origem"' in script and "data-sug-origem" in script


# ── o App de verdade (v367, 21/11/2026): resposta curta e o App sem a chave ─────────────────────────────────────────
def test_resposta_com_menos_de_5_caracteres_e_recusada_aqui(app, app_falso):
    c = _cliente(app, admin=True)
    _responder(c, texto="ok")
    assert not [p for p in app_falso.pedidos if p["metodo"] == "POST"]
    assert "A resposta precisa de 5 caracteres ou mais" in c.get(URL).get_data(as_text=True)


def test_o_app_sem_a_chave_dele_vira_o_aviso_com_o_texto_do_app(app, app_falso):
    app_falso.status_get = 503
    app_falso.relatos = None
    falso_get = app_falso.__call__

    def com_503(req, timeout=None):
        if req.get_method() == "GET":
            app_falso.pedidos.append({"metodo": "GET", "url": req.full_url, "chave": None, "corpo": None})
            raise urllib.error.HTTPError(req.full_url, 503, "erro", {}, io.BytesIO(json.dumps(
                {"erro": "a chave do Nexus para os relatos não está configurada no App"}).encode()))
        return falso_get(req, timeout)
    R._abrir = com_503
    html = _cliente(app, admin=True).get(URL).get_data(as_text=True)
    assert "a chave do Nexus para os relatos não está configurada no App" in html
