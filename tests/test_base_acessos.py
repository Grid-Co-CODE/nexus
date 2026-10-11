"""Base → Acessos (11/10/2026): os administradores do Nexus pela tela, a auditoria e quem entrou em 30 dias.

Pedido: "Tem algum canto do Nexus onde eu posso administrar isso?". Até então os administradores eram só a NEXUS_ADMINS
do .env do servidor. Provas: só admin vê e grava; o do servidor não sai; dar acesso vale no login seguinte (e já no
próximo pedido); tirar vale no próximo pedido; a auditoria grava; a escrita é atômica e com trava; e-mail inválido é
recusado; o registro de logins tem teto; arquivo corrompido fecha e não é sobrescrito; e nada grava sem a pasta de dados.
"""
import json
import re
import threading
from datetime import timedelta

import pytest

from conftest import SENHA_TESTE
from nexus import create_app
from nexus.auth import acessos as A

SERVIDOR = "servidor@exemplo.com"
PESSOA = "pessoa@exemplo.com"
OUTRA = "outra@exemplo.com"
URL = "/t/base/acessos"


@pytest.fixture
def app(tmp_path):
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_ADMINS": SERVIDOR, "NEXUS_DADOS": str(tmp_path / "dados")})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    return app


@pytest.fixture
def fracttal_falso(monkeypatch):
    from nexus.auth import fracttal
    monkeypatch.setattr(fracttal, "entrar", lambda app, e, s: {"email": e.strip().lower(), "nome": "Pessoa Teste",
                                                                  "perfil": "", "cookie": ("os_sessao", "v", 3600)})


def _admin(app):
    c = app.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return c


def _pelo_fracttal(app, email):
    c = app.test_client()
    assert c.post("/entrar", data={"email": email, "senha": "x"}).status_code == 302
    return c


def _codigo(c) -> str:
    html = c.get(URL).get_data(as_text=True)
    return re.search(r'name="codigo" value="([^"]+)"', html).group(1)


def _post(c, acao, email, codigo=None, **extra):
    return c.post(URL, data={"codigo": codigo if codigo is not None else _codigo(c), "acao": acao, "email": email,
                             **extra})


def _arquivo(app):
    return A.pasta(app.config) / A.ARQUIVO


def _lido(app):
    return json.loads(_arquivo(app).read_text(encoding="utf-8"))


def _sessao(c):
    with c.session_transaction() as s:
        return dict(s)


# ── quem vê ──────────────────────────────────────────────────────────────────────────────────────────────────────


def test_admin_ve_os_do_servidor_e_grava_um_novo(app):
    c = _admin(app)
    r = c.get(URL)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert SERVIDOR in html and "do servidor" in html and "só pela T.I." in html
    r = _post(c, "adicionar", "  Pessoa@Exemplo.COM ")
    assert r.status_code == 303 and r.headers["Location"].endswith(URL)
    dado = _lido(app)
    assert [a["email"] for a in dado["admins"]] == [PESSOA]                # minúsculas, sem espaço
    assert dado["admins"][0]["por"] == "senha de administrador" and dado["admins"][0]["quando"].endswith("Z")
    html = c.get(URL).get_data(as_text=True)
    assert "agora é administrador do Nexus" in html and "pela tela" in html and PESSOA in html


def test_a_tela_fica_verde_no_menu(app):
    from nexus.torres import telas_com_conteudo
    assert URL in telas_com_conteudo(app)


def test_quem_nao_e_admin_e_barrado_e_nao_grava(app, fracttal_falso):
    c = _pelo_fracttal(app, PESSOA)
    r = c.get(URL)
    assert r.status_code == 403
    html = r.get_data(as_text=True)
    assert "A tela Acessos é só para administradores" in html and PESSOA in html and "Forbidden" not in html
    r = c.post(URL, data={"acao": "adicionar", "email": PESSOA, "codigo": "qualquer"})
    assert r.status_code == 403
    assert not _arquivo(app).exists()


# ── o que não pode ───────────────────────────────────────────────────────────────────────────────────────────────


def test_o_do_servidor_nao_sai_pela_tela(app, fracttal_falso):
    c = _admin(app)
    r = _post(c, "remover", SERVIDOR)
    assert r.status_code == 400
    assert "só sai pelo .env do servidor" in r.get_data(as_text=True)
    assert not _arquivo(app).exists()                                        # nada gravado
    # e quem é do servidor segue administrador
    s = _pelo_fracttal(app, SERVIDOR)
    assert _sessao(s)["admin"] is True and s.get(URL).status_code == 200
    # dar acesso pela tela a quem já é do servidor também não grava
    assert _post(c, "adicionar", SERVIDOR).status_code == 400


def test_quem_a_ti_pos_no_servidor_depois_de_dado_pela_tela_nao_sai_pela_tela(app):
    """Dado pela tela e, depois, posto na NEXUS_ADMINS pela T.I.: tirar da lista da tela não tiraria o acesso (o servidor
    dá), então a tela não oferece o botão e o pedido é recusado; ele segue administrador."""
    c = _admin(app)
    assert _post(c, "adicionar", PESSOA).status_code == 303
    app.config["NEXUS_ADMINS"] = f"{SERVIDOR},{PESSOA}"
    html = c.get(URL).get_data(as_text=True)
    assert "também do servidor" in html and f'name="email" value="{PESSOA}"' not in html
    r = _post(c, "remover", PESSOA)
    assert r.status_code == 400 and "só sai pelo .env do servidor" in r.get_data(as_text=True)
    assert A.admins_da_tela(app.config) == {PESSOA}


@pytest.mark.parametrize("email", ["", "   ", "sem-arroba", "nome@dominio", "@exemplo.com", "nome @exemplo.com",
                                   "nome@exem plo.com", "nome@@exemplo.com", "nome@exemplo..com", ".nome@exemplo.com",
                                   "nome.@exemplo.com", "nome@exemplo.com,outra@exemplo.com", "nomé@exemplo.com",
                                   "a" * 250 + "@exemplo.com", "nome@exemplo.com\nBcc:x@exemplo.com"])
def test_email_invalido_e_recusado(app, email):
    c = _admin(app)
    r = _post(c, "adicionar", email)
    assert r.status_code == 400
    assert "Nada mudou" in r.get_data(as_text=True)
    assert not _arquivo(app).exists()


def test_email_normal():
    assert A.email_normal("  Nome.Sobrenome+x@Empresa.COM.br ") == "nome.sobrenome+x@empresa.com.br"
    with pytest.raises(A.Recusado):
        A.email_normal("nome sobrenome@empresa.com")


def test_post_sem_o_codigo_da_tela_ou_de_outro_site_e_recusado(app):
    c = _admin(app)
    codigo = _codigo(c)
    assert _post(c, "adicionar", PESSOA, codigo="").status_code == 403
    assert _post(c, "adicionar", PESSOA, codigo="codigo-de-outra-sessao").status_code == 403
    r = c.post(URL, data={"codigo": codigo, "acao": "adicionar", "email": PESSOA},
               headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = c.post(URL, data={"codigo": codigo, "acao": "adicionar", "email": PESSOA},
               headers={"Origin": "https://outro.exemplo.com"})
    assert r.status_code == 403
    assert not _arquivo(app).exists()
    # da própria página passa
    r = c.post(URL, data={"codigo": codigo, "acao": "adicionar", "email": PESSOA},
               headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 303


def test_ninguem_se_tira_sozinho_por_engano(app, fracttal_falso):
    adm = _admin(app)
    assert _post(adm, "adicionar", PESSOA).status_code == 303
    eu = _pelo_fracttal(app, PESSOA)
    # o último da tela não tira o próprio acesso, nem confirmando (e a tela nem oferece o botão)
    assert "o último da tela não tira o próprio acesso" in eu.get(URL).get_data(as_text=True)
    r = _post(eu, "remover", PESSOA, confirmo="1")
    assert r.status_code == 400 and "último administrador dado pela tela" in r.get_data(as_text=True)
    assert _post(adm, "adicionar", OUTRA).status_code == 303
    assert 'name="confirmo"' in eu.get(URL).get_data(as_text=True)          # com outro na lista, o botão volta
    # com outro na lista, só confirmando
    r = _post(eu, "remover", PESSOA)
    assert r.status_code == 400 and "marque a confirmação" in r.get_data(as_text=True)
    assert PESSOA in A.admins_da_tela(app.config)
    r = _post(eu, "remover", PESSOA, confirmo="1")
    assert r.status_code == 303 and r.headers["Location"].endswith("/")      # vai ao Início: a tela já não abre
    assert A.admins_da_tela(app.config) == {OUTRA}
    assert eu.get(URL).status_code == 403


# ── vale de verdade ──────────────────────────────────────────────────────────────────────────────────────────────


def test_dar_acesso_faz_o_login_seguinte_virar_admin(app, fracttal_falso):
    antes = _pelo_fracttal(app, PESSOA)
    assert _sessao(antes)["admin"] is False
    assert _post(_admin(app), "adicionar", PESSOA).status_code == 303
    depois = _pelo_fracttal(app, PESSOA)
    assert _sessao(depois)["admin"] is True
    assert depois.get(URL).status_code == 200
    # e quem já estava logado vira admin no próximo pedido, sem sair e entrar
    assert antes.get(URL).status_code == 200


def test_tirar_o_acesso_vale_ja_no_proximo_pedido(app, fracttal_falso):
    adm = _admin(app)
    assert _post(adm, "adicionar", PESSOA).status_code == 303
    pessoa = _pelo_fracttal(app, PESSOA)
    assert pessoa.get(URL).status_code == 200
    assert _post(adm, "remover", PESSOA).status_code == 303
    assert pessoa.get(URL).status_code == 403                               # a sessão aberta perdeu o admin
    assert _sessao(pessoa)["admin"] is False
    assert _sessao(_pelo_fracttal(app, PESSOA))["admin"] is False            # e o login seguinte também não é


def test_a_senha_de_administrador_nao_depende_da_lista(app):
    adm = _admin(app)
    _arquivo(app).parent.mkdir(parents=True, exist_ok=True)
    _arquivo(app).write_text("{ quebrado", encoding="utf-8")
    assert adm.get(URL).status_code == 200


def test_a_aprovacao_de_os_enxerga_os_da_tela(app):
    from nexus.auth import _admins
    assert _post(_admin(app), "adicionar", PESSOA).status_code == 303
    with app.test_request_context("/"):
        assert _admins() == {SERVIDOR, PESSOA}


def test_auditoria_grava_quem_fez_o_que_e_quando(app, fracttal_falso):
    assert _post(_admin(app), "adicionar", PESSOA).status_code == 303
    srv = _pelo_fracttal(app, SERVIDOR)
    assert _post(srv, "remover", PESSOA).status_code == 303
    aud = _lido(app)["auditoria"]
    assert [(x["quem"], x["acao"], x["email"]) for x in aud] == [("senha de administrador", "adicionou", PESSOA),
                                                                  (SERVIDOR, "removeu", PESSOA)]
    assert all(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", x["quando"]) for x in aud)
    html = srv.get(URL).get_data(as_text=True)
    assert html.index("tirou acesso") < html.index("deu acesso")             # a mais recente primeiro


def test_auditoria_tem_teto(app, monkeypatch):
    monkeypatch.setattr(A, "MAX_AUDITORIA", 3)
    for i in range(4):
        A.adicionar(app.config, f"p{i}@exemplo.com", "teste", set())
    aud = _lido(app)["auditoria"]
    assert len(aud) == 3 and aud[0]["email"] == "p1@exemplo.com"


# ── o arquivo ────────────────────────────────────────────────────────────────────────────────────────────────────


def test_escrita_atomica_falha_na_troca_nao_mexe_no_arquivo(app, monkeypatch):
    c = _admin(app)
    assert _post(c, "adicionar", PESSOA).status_code == 303
    antes = _arquivo(app).read_bytes()

    def troca_que_falha(*a, **k):
        raise OSError("disco cheio")
    monkeypatch.setattr(A.os, "replace", troca_que_falha)
    r = _post(c, "adicionar", OUTRA)
    assert r.status_code == 500 and "nada mudou" in r.get_data(as_text=True)
    assert _arquivo(app).read_bytes() == antes
    assert not list(_arquivo(app).parent.glob("*.tmp"))                    # o temporário não ficou
    monkeypatch.undo()
    assert A.admins_da_tela(app.config) == {PESSOA}


def test_escrita_atomica_falha_no_meio_nao_deixa_arquivo_pela_metade(app, monkeypatch):
    A.adicionar(app.config, PESSOA, "teste", set())
    antes = _arquivo(app).read_bytes()
    original = A.json.dump

    def para_no_meio(dado, f, **k):
        f.write('{"versao": 1, "admins": [')
        raise OSError("caiu no meio")
    monkeypatch.setattr(A.json, "dump", para_no_meio)
    with pytest.raises(OSError):
        A.adicionar(app.config, OUTRA, "teste", set())
    monkeypatch.setattr(A.json, "dump", original)
    assert _arquivo(app).read_bytes() == antes
    assert not list(_arquivo(app).parent.glob("*.tmp"))


def test_trava_nenhuma_mudanca_se_perde_com_varias_threads(app):
    erros = []

    def dar(i):
        try:
            A.adicionar(app.config, f"pessoa{i}@exemplo.com", "teste", set())
        except Exception as e:      # noqa: BLE001
            erros.append(e)
    fios = [threading.Thread(target=dar, args=(i,)) for i in range(20)]
    for f in fios:
        f.start()
    for f in fios:
        f.join()
    assert not erros
    assert len(A.admins_da_tela(app.config)) == 20 and len(_lido(app)["auditoria"]) == 20


def test_arquivo_corrompido_fecha_e_nao_e_sobrescrito(app, fracttal_falso):
    A.adicionar(app.config, PESSOA, "teste", set())
    pessoa = _pelo_fracttal(app, PESSOA)
    assert _sessao(pessoa)["admin"] is True
    _arquivo(app).write_text('{"admins": [{"email": ', encoding="utf-8")
    assert A.admins_da_tela(app.config) == set()
    assert pessoa.get(URL).status_code == 403                               # fecha: só os do servidor valem
    adm = _admin(app)
    html = adm.get(URL).get_data(as_text=True)
    assert "A lista da tela não abriu" in html and 'name="acao" value="adicionar"' not in html
    r = adm.post(URL, data={"codigo": "outro", "acao": "adicionar", "email": OUTRA})
    assert r.status_code == 403                                             # sem o código da sessão
    with adm.session_transaction() as s:
        s["acessos_codigo"] = "codigo-certo"
    r = adm.post(URL, data={"codigo": "codigo-certo", "acao": "adicionar", "email": OUTRA})
    assert r.status_code == 409 and "Gravar agora apagaria" in r.get_data(as_text=True)
    assert _arquivo(app).read_text(encoding="utf-8") == '{"admins": [{"email": '


def test_sem_pasta_de_dados_em_teste_nada_e_lido_nem_gravado(tmp_path, monkeypatch):
    app = create_app({"NEXUS_SECRET_KEY": "k", "NEXUS_SENHA_ADMIN": SENHA_TESTE})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    assert A.pasta(app.config) is None
    c = _admin(app)
    html = c.get(URL).get_data(as_text=True)
    assert "Sem pasta de dados" in html
    with pytest.raises(A.Recusado):
        A.adicionar(app.config, PESSOA, "teste", set())


# ── quem entrou ──────────────────────────────────────────────────────────────────────────────────────────────────


def test_quem_entrou_nos_ultimos_30_dias(app, fracttal_falso):
    A.adicionar(app.config, PESSOA, "teste", set())
    for e in (PESSOA, OUTRA, SERVIDOR):
        _pelo_fracttal(app, e)
    html = _admin(app).get(URL).get_data(as_text=True)
    secao = html[html.index("Quem entrou nos últimos 30 dias"):]
    for e in (PESSOA, OUTRA, SERVIDOR):
        assert e in secao
    assert "senha de administrador" in secao
    gravado = json.loads((A.pasta(app.config) / A.ARQUIVO_LOGINS).read_text(encoding="utf-8"))
    assert set(gravado["logins"]) == {PESSOA, OUTRA, SERVIDOR, "senha de administrador"}
    assert all(set(v) <= set("0123456789-T:Z") for v in gravado["logins"].values())   # só a hora, nada mais


def test_registro_de_logins_tem_teto_e_janela(app, fracttal_falso, monkeypatch):
    monkeypatch.setattr(A, "MAX_LOGINS", 3)
    agora = A._agora()
    velho = A._iso(agora - timedelta(days=31))
    alvo = A.pasta(app.config) / A.ARQUIVO_LOGINS
    alvo.parent.mkdir(parents=True, exist_ok=True)
    alvo.write_text(json.dumps({"versao": 1, "logins": {"antigo@exemplo.com": velho}}), encoding="utf-8")
    for i in range(5):
        monkeypatch.setattr(A, "_agora", lambda i=i: agora + timedelta(minutes=i))
        _pelo_fracttal(app, f"p{i}@exemplo.com")
    logins = json.loads(alvo.read_text(encoding="utf-8"))["logins"]
    assert set(logins) == {"p2@exemplo.com", "p3@exemplo.com", "p4@exemplo.com"}   # os 3 mais recentes, sem o antigo


def test_registro_de_logins_que_falha_nao_impede_a_entrada(app, fracttal_falso, monkeypatch):
    def falha(*a, **k):
        raise OSError("disco")
    monkeypatch.setattr(A, "_gravar_atomico", falha)
    c = _pelo_fracttal(app, PESSOA)
    assert c.get("/").status_code == 200


# ── pasta de dados que não abre (revisão de 11/10/2026) ────────────────────────────────────────────────────────


def _stat_negado(monkeypatch, *nomes):
    """O `stat` do arquivo (e só dele) dá PermissionError: é o que acontece com a pasta de dados sem permissão de busca
    para o usuário do serviço; no Linux, a NEXUS_DADOS apontando para um arquivo dá NotADirectoryError no mesmo lugar."""
    from pathlib import Path
    original = Path.stat

    def stat(self, *a, **k):
        if self.name in nomes:
            raise PermissionError(13, "Permission denied", str(self))
        return original(self, *a, **k)
    monkeypatch.setattr(Path, "stat", stat)


def test_pasta_sem_permissao_nao_derruba_o_nexus_e_fecha(app, fracttal_falso, monkeypatch):
    # antes da correção, o stat que não era FileNotFoundError subia pelo portão: 500 em TODO pedido de toda sessão do
    # Fracttal (o Início incluído) e no próprio login; a senha de administrador não passa por _admin_em_dia, por isso
    # quem testava com ela não via
    A.adicionar(app.config, PESSOA, "teste", set())
    pessoa = _pelo_fracttal(app, PESSOA)
    assert _sessao(pessoa)["admin"] is True
    _stat_negado(monkeypatch, A.ARQUIVO, A.ARQUIVO_LOGINS)
    assert pessoa.get("/").status_code == 200                               # o Nexus segue de pé
    assert _sessao(pessoa)["admin"] is False                                # e fecha: só os do servidor valem
    assert A.admins_da_tela(app.config) == set()
    assert pessoa.get(URL).status_code == 403
    outra = _pelo_fracttal(app, OUTRA)                                      # o login também não cai
    assert outra.get("/").status_code == 200 and _sessao(outra)["admin"] is False
    assert _sessao(_pelo_fracttal(app, SERVIDOR))["admin"] is True          # o do servidor segue administrador
    adm = _admin(app)
    r = adm.get(URL)
    assert r.status_code == 200                                             # a tela abre, com o aviso
    html = r.get_data(as_text=True)
    assert "A lista da tela não abriu" in html and "PermissionError" in html
    assert 'name="acao" value="adicionar"' not in html
    with adm.session_transaction() as s:
        s["acessos_codigo"] = "codigo-certo"
    r = adm.post(URL, data={"codigo": "codigo-certo", "acao": "adicionar", "email": OUTRA})
    assert r.status_code == 409                                             # e não grava por cima do que não abriu
    monkeypatch.undo()
    assert A.admins_da_tela(app.config) == {PESSOA}                         # a permissão voltou: a lista volta


def test_erro_de_pasta_vai_ao_log_uma_vez_e_nao_a_cada_pedido(app, monkeypatch, caplog):
    # o portão consulta a lista a cada pedido: registrar a cada clique encheria o journal; uma linha por mudança basta
    monkeypatch.setattr(A, "_AVISADO", {})
    _stat_negado(monkeypatch, A.ARQUIVO)
    with caplog.at_level("WARNING", logger=A.__name__):
        for _ in range(5):
            assert A.admins_da_tela(app.config) == set()
    assert sum("não abriu agora" in r.getMessage() for r in caplog.records) == 1


def test_arquivo_que_nao_e_utf8_fecha_e_nao_derruba(app, fracttal_falso):
    # bytes que não são UTF-8 (disco, ou salvo à mão em outra codificação) davam UnicodeDecodeError, que não é OSError
    # nem passava pelo json: mesmo 500 em todo pedido do Fracttal
    A.adicionar(app.config, PESSOA, "teste", set())
    pessoa = _pelo_fracttal(app, PESSOA)
    _arquivo(app).write_bytes(b'{"admins": [{"email": "\xff\xfe"}]}')
    assert A.admins_da_tela(app.config) == set()
    assert pessoa.get("/").status_code == 200 and _sessao(pessoa)["admin"] is False
    assert "A lista da tela não abriu" in _admin(app).get(URL).get_data(as_text=True)


def test_arquivo_aninhado_demais_fecha_e_nao_derruba(app, fracttal_falso):
    # o json do Python estoura a recursão (RecursionError, não ValueError) num arquivo aninhado a fundo
    pessoa = _pelo_fracttal(app, PESSOA)
    _arquivo(app).parent.mkdir(parents=True, exist_ok=True)
    _arquivo(app).write_text("[" * 200000 + "]" * 200000, encoding="utf-8")
    assert A.admins_da_tela(app.config) == set()
    assert pessoa.get("/").status_code == 200
    assert "A lista da tela não abriu" in _admin(app).get(URL).get_data(as_text=True)


def test_admins_da_tela_nunca_levanta(app, monkeypatch, caplog):
    # a garantia do portão: qualquer erro inesperado na leitura fecha (nenhum da tela) e fica no journal
    def explode(*a, **k):
        raise KeyError("inesperado")
    monkeypatch.setattr(A, "_AVISADO", {})
    monkeypatch.setattr(A, "_ler", explode)
    with caplog.at_level("ERROR", logger=A.__name__):
        assert A.admins_da_tela(app.config) == set()
        assert A.admins_da_tela(app.config) == set()
    assert sum("KeyError" in r.getMessage() for r in caplog.records) == 1    # uma linha, não uma por pedido


def test_gravou_mas_o_stat_depois_falhou_nao_diz_que_nada_mudou(app, monkeypatch):
    # o arquivo já foi trocado: um erro do stat dali para a frente faria a tela dizer "nada mudou" com a mudança no disco
    original = A._trocar

    def trocar_e_negar(tmp, p):
        original(tmp, p)
        _stat_negado(monkeypatch, A.ARQUIVO)
    monkeypatch.setattr(A, "_trocar", trocar_e_negar)
    assert A.adicionar(app.config, PESSOA, "teste", set()) == PESSOA
    monkeypatch.undo()
    assert A.admins_da_tela(app.config) == {PESSOA}
    assert [a["email"] for a in _lido(app)["admins"]] == [PESSOA]
