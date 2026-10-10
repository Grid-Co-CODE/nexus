"""O `next` do Entrar só leva a um caminho do próprio Nexus (revisão adversarial de 10/10/2026).

O caso: o `next_seguro` só recusava `//` e `/\\` no começo. Um `next` igual a `/` + TAB + `/outro.site/x` passava, e o
Werkzeug tira o TAB ao montar o Location (o `urlsplit` do Python remove TAB, LF e CR, como manda a regra de URL dos
navegadores): o cabeçalho saía `//outro.site/x`. Provado pelo fluxo inteiro: GET /entrar?next=..., o formulário leva o
next, o login do Fracttal acerta e a resposta é 302 para `//evil.example.com/entrar`. Debaixo do /nexus isso não
acontecia (o prefixo vai na frente: `/nexus//evil...`); na RAIZ, que entra na segunda-feira, a pessoa digitava a senha
do Fracttal no endereço da empresa e caía num site de fora. LF e CR davam 500 (o Werkzeug recusa quebra de linha no
cabeçalho). Agora o `next` com caractere de controle (0x00-0x20, 0x7f) ou barra invertida em QUALQUER posição volta ao
Início, como a régua do `nexus_sair` e do `_entrar_pelo_nexus_href` da plataforma.
"""
import pytest

from nexus import create_app
from nexus.auth import destino_seguro, fracttal, next_seguro

from conftest import SENHA_TESTE
from test_auth_sair_fracttal import _cookie_os, _jwt, _pelo_fracttal

FORA = "evil.example.com"
# cada um, depois do "/", vira "//evil..." no Location ou no navegador (que também tira TAB, LF e CR de URL)
NEXTS_RUINS = [
    "/\t/" + FORA + "/entrar",
    "/\n/" + FORA + "/x",
    "/\r/" + FORA + "/x",
    "/\x0b/" + FORA + "/x",
    "/\x0c/" + FORA + "/x",
    "/\x00/" + FORA + "/x",
    "/ /" + FORA + "/x",
    "/\x7f/" + FORA + "/x",
    "/\t\\" + FORA + "/x",
    "/t/pcm\\..\\x",                     # barra invertida em qualquer posição
    "\t//" + FORA + "/x",
    "/t/pcm/semana\t",                   # controle no fim também: o caminho do Nexus não tem
]


@pytest.mark.parametrize("valor", NEXTS_RUINS)
def test_next_com_caractere_de_controle_ou_barra_invertida_volta_ao_inicio(valor):
    assert next_seguro(valor) == "/"


@pytest.mark.parametrize("valor", [
    "/t/pcm/semana",
    "/t/performance/painel?p=%2Fpainel%2Ffalhas",     # o ?p= da moldura vem codificado: segue como está
    "/os/os/15089?parcial=1&status=ok",
    "/nexus/t/cos/mesa",                              # o next que já vem com o prefixo (a camada da T.I.)
    "/t/x%09y",                                       # %09 ainda CODIFICADO é caminho comum: o navegador não o decodifica
])
def test_next_interno_segue(valor):
    assert next_seguro(valor) == valor


def _app(prefixo):
    cfg = {"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE}
    if prefixo:
        cfg["NEXUS_PREFIXO"] = prefixo
    app = create_app(cfg)
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    return app


def _fracttal_aceita(monkeypatch):
    monkeypatch.setattr(fracttal, "entrar", lambda app, e, s: {"email": e, "nome": "Pessoa Teste", "perfil": "",
                                                                  "cookie": ("os_sessao", "v", 3600)})


def _ficou_em_casa(location: str, base: str):
    assert not location.startswith("//") and FORA not in location, location
    assert location == base + "/", location


@pytest.mark.parametrize("prefixo", [None, "/nexus"])
def test_o_fluxo_inteiro_do_entrar_com_tab_codificado_nao_sai_do_nexus(prefixo, monkeypatch):
    """Como o achado foi provado: o link com %09 (o navegador manda codificado, o Flask decodifica para TAB)."""
    _fracttal_aceita(monkeypatch)
    app, base = _app(prefixo), prefixo or ""
    cli = app.test_client()
    pagina = cli.get(base + "/entrar?next=/%09/" + FORA + "/entrar").get_data(as_text=True)
    assert FORA not in pagina                          # o formulário nem leva o next ruim adiante
    r = cli.post(base + "/entrar?next=/%09/" + FORA + "/entrar", data={"email": "pessoa@exemplo.com", "senha": "x"})
    assert r.status_code == 302
    _ficou_em_casa(r.headers["Location"], base)


@pytest.mark.parametrize("prefixo", [None, "/nexus"])
@pytest.mark.parametrize("valor", NEXTS_RUINS)
def test_fracttal_e_senha_de_admin_nao_redirecionam_para_fora(prefixo, valor, monkeypatch):
    _fracttal_aceita(monkeypatch)
    app, base = _app(prefixo), prefixo or ""
    r = app.test_client().post(base + "/entrar", query_string={"next": valor},
                               data={"email": "pessoa@exemplo.com", "senha": "x"})
    assert r.status_code == 302                        # e não 500 (LF e CR no Location)
    _ficou_em_casa(r.headers["Location"], base)
    r = app.test_client().post(base + "/entrar", query_string={"next": valor}, data={"senha": SENHA_TESTE})
    assert r.status_code == 302
    _ficou_em_casa(r.headers["Location"], base)


@pytest.mark.parametrize("valor", NEXTS_RUINS)
def test_o_login_do_os_creator_de_quem_ja_entrou_nao_redireciona_para_fora(app, cliente, valor):
    """O mesmo helper serve o /os/login?next= de quem já está logado pelo Fracttal (`_fim_do_fracttal`)."""
    _pelo_fracttal(cliente)
    _cookie_os(app, cliente, _jwt())
    r = cliente.get("/os/login", query_string={"next": valor})
    assert r.status_code == 302
    _ficou_em_casa(r.headers["Location"], "")


@pytest.mark.parametrize("rota, campo", [("/tema", {"tema": "escuro"}), ("/cadeira", {"cadeira": ""})])
def test_tema_e_cadeira_voltam_so_para_o_nexus(logado, rota, campo):
    for valor in NEXTS_RUINS:
        r = logado.post(rota, data=dict(campo, voltar=valor))
        assert r.status_code == 302
        _ficou_em_casa(r.headers["Location"], "")


def test_destino_seguro_debaixo_do_prefixo():
    app = _app("/nexus")
    with app.test_request_context("/entrar", base_url="http://localhost/nexus"):
        assert destino_seguro("/\t/" + FORA) == "/nexus/"
        assert destino_seguro("/t/cos/mesa") == "/nexus/t/cos/mesa"
