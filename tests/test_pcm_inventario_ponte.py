"""A ponte do inventário (`/os/_nexus/inventario`) e a tabela de erros das telas da régua e da curadoria (27/10/2026, a revisão das
Tasks 8 e 9). O login do Fracttal só chega às rotas debaixo de /os; as páginas ficam em /t/pcm e chamam a ponte por `fetch`. Aqui:

- `registrar` é idempotente (a torre e outro módulo podem chamá-lo: registrar duas vezes não levanta nem duplica a rota);
- as duas rotas da ponte e os endereços que a página monta funcionam debaixo do `NEXUS_PREFIXO` do servidor (`/nexus/os/_nexus/...`),
  sem dobrar o prefixo nem sair da raiz;
- o erro de rede e o de arquivo local não se confundem, e o texto do cadastro não diz "é o mesmo número" (a régua é idempotente; o
  cadastro tem outro jeito de não duplicar).
O banco é o falso do Campo, o livro do inventário um arquivo e o Fracttal o `EstoqueFalso`. Dado de mentira, sem nome de gente."""
from datetime import datetime

import pytest
import requests
from estoque_falso import EstoqueFalso
from flask import Blueprint, Flask
from test_campo_visao import BRT, _aba, banco  # noqa: F401  (banco é fixture)
from test_pcm_almoxarifado import _semear
from test_pcm_inventario_curadoria import CABO, CONECTOR, GENERICO, PECA_DA_LISTA

from nexus import create_app
from nexus.campo import visao
from nexus.dados import almoxarifado as A
from nexus.dados import fato_inventario as F
from nexus.pcm.inventario import erros, ponte_os
from nexus.pcm.inventario import estoque as E

SENHA = "senha-de-teste"
PREFIXO = "/nexus"
GRAVAR = {"almox": "10", "item": "1", "aco_min": "2", "aco_max": "9"}
REGUA = f"{PREFIXO}/t/pcm/pecas/inventario/regua"
CURADORIA = f"{PREFIXO}/t/pcm/pecas/inventario/curadoria"


@pytest.fixture
def app():
    """O Nexus como no servidor: debaixo do `/nexus` (o `Prefixo` tira o prefixo do caminho e põe o `SCRIPT_NAME`)."""
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA, "NEXUS_PREFIXO": PREFIXO})
    app.config["TESTING"] = True
    app.config["SESSION_COOKIE_SECURE"] = False
    return app


@pytest.fixture
def inv(app, banco, tmp_path, monkeypatch):  # noqa: F811
    monkeypatch.setattr(visao, "_agora", lambda: datetime(2026, 10, 25, 10, 0, tzinfo=BRT))
    _semear(banco)
    _aba(banco, A.LIVRO_CONTAGENS, A.ABA_CONTAGENS, [PECA_DA_LISTA, CABO, CONECTOR, GENERICO])
    app.config.update(NEXUS_ALMOX_INVENTARIO_ARQUIVO=str(tmp_path / "inventario.json"), TESTING=True,
                      NEXUS_DADOS=str(tmp_path / "dados"))
    visao.limpar()
    F.limpar()
    return app


def _administrador(app):
    """Quem entrou pela senha de administrador, debaixo do prefixo (`/nexus/entrar`)."""
    c = app.test_client()
    assert c.post(f"{PREFIXO}/entrar", data={"senha": SENHA}).status_code == 302
    return c


def test_registrar_duas_vezes_registra_a_ponte_uma_vez_so():
    """A torre registra a ponte e outro módulo (a gravação, a Task 7) pode registrá-la de novo: o mesmo blueprint duas vezes no
    mesmo app levantaria `ValueError`. O registro é idempotente, também com duas torres."""
    app = Flask("prova")
    torre_a, torre_b = Blueprint("torre_a", "prova"), Blueprint("torre_b", "prova")
    for torre in (torre_a, torre_a, torre_b):
        ponte_os.registrar(torre)
    app.register_blueprint(torre_a)
    app.register_blueprint(torre_b)
    assert list(app.blueprints).count(ponte_os.bp.name) == 1
    regras = [r.rule for r in app.url_map.iter_rules()]
    assert regras.count("/os/_nexus/inventario/regua/gravar") == 1 and regras.count("/os/_nexus/inventario/curadoria/cadastrar") == 1


def test_a_ponte_da_regua_debaixo_do_prefixo(inv, monkeypatch):
    """No servidor o Nexus mora em /nexus: a página monta o endereço da ponte com `{{ raiz }}`, o JSON devolve a volta com o prefixo,
    e a ponte responde no caminho que o navegador pede (`/nexus/os/_nexus/...`), sem dobrar o prefixo."""
    falso = EstoqueFalso({"10": {"1": {"saldo": 1, "minimo": 3, "maximo": 3, "codigo": "SP-1"}}})
    monkeypatch.setattr(E, "estoque_da_sessao", lambda app: falso)
    c = _administrador(inv)
    r = c.post(f"{REGUA}/decidir", data={"almox": "10", "item": "1", "aco_min": "2", "aco_max": "9"})
    assert r.status_code == 303 and r.headers["Location"].endswith(f"{REGUA}?almox=10")
    html = c.get(f"{REGUA}?almox=10").get_data(as_text=True)
    assert f'action="{PREFIXO}/os/_nexus/inventario/regua/gravar"' in html and "/nexus/nexus" not in html
    assert f'{PREFIXO}/static/pcm-ponte-inventario.js' in html
    r = c.post(f"{PREFIXO}/os/_nexus/inventario/regua/gravar", data=GRAVAR)
    assert r.status_code == 200 and r.get_json()["volta"] == f"{REGUA}?almox=10"
    assert (falso.ler("10")["1"]["minimo"], falso.ler("10")["1"]["maximo"]) == (2.0, 9.0)
    assert "gravada no fracttal" in c.get(r.get_json()["volta"]).get_data(as_text=True).lower()


def test_a_ponte_da_curadoria_debaixo_do_prefixo(inv, monkeypatch):
    falso = EstoqueFalso({"10": {"5": {"saldo": 1, "codigo": "SP-CAB-001"}}})
    monkeypatch.setattr(E, "estoque_da_sessao", lambda app: falso)
    c = _administrador(inv)
    html = c.get(CURADORIA).get_data(as_text=True)
    assert f'action="{PREFIXO}/os/_nexus/inventario/curadoria/cadastrar"' in html and "/nexus/nexus" not in html
    r = c.post(f"{PREFIXO}/os/_nexus/inventario/curadoria/cadastrar",
               data={"contagem": "C-1", "linha": "L-2", "sigla": "CAB", "nome": "Cabo azul 6 mm", "unidade": "METRO"})
    assert r.status_code == 200 and r.get_json()["volta"] == CURADORIA and "SP-CAB-002" in r.get_json()["mensagem"]
    assert "SP-CAB-002" in c.get(CURADORIA).get_data(as_text=True)


def test_sem_o_login_do_fracttal_o_link_do_login_sai_com_o_prefixo(inv):
    """Quem entrou pela senha de administrador não tem o cookie do Fracttal: 401 e o link do `/os/login` do OS Creator, debaixo do
    prefixo, nas duas rotas da ponte."""
    c = _administrador(inv)
    c.post(f"{REGUA}/decidir", data={"almox": "10", "item": "1", "aco_min": "2", "aco_max": "9"})
    for rota, corpo in (("regua/gravar", GRAVAR), ("curadoria/cadastrar", {"contagem": "C-1", "linha": "L-2", "sigla": "CAB",
                                                                        "nome": "Cabo"})):
        r = c.post(f"{PREFIXO}/os/_nexus/inventario/{rota}", data=corpo)
        assert r.status_code == 401 and r.get_json()["login"].startswith(f"{PREFIXO}/os/login?next=")


# ── a tabela de erros ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_erro_de_arquivo_do_nexus_nao_se_confunde_com_o_de_rede():
    """O controle do código reservado e a pasta de dados são arquivos locais: o erro deles (o disco, a permissão) não é do Fracttal e
    o texto não manda "gravar de novo, é o mesmo número"."""
    for ex in (FileNotFoundError("x"), PermissionError("x"), OSError(28, "disco cheio")):
        for ao in (None, "regua", "cadastro"):
            status, texto = erros.resposta(ex, ao=ao)
            assert status == 500 and "arquivo do Nexus" in texto and "Fracttal" not in texto and "mesmo número" not in texto


def test_erro_de_rede_tem_um_texto_para_cada_operacao():
    """A conexão que cai (a do Python e as do `requests`): na régua, gravar de novo é seguro e é o mesmo número; no cadastro, o
    código ficou reservado e repetir com os mesmos dados não cria outra peça; fora disso, só "tente de novo"."""
    redes = (ConnectionError("x"), TimeoutError("x"), requests.ConnectionError("x"), requests.Timeout("x"))
    for ex in redes:
        status, texto = erros.resposta(ex, ao="regua")
        assert status == 502 and "mesmo número" in texto
        status, texto = erros.resposta(ex, ao="cadastro")
        assert status == 502 and "reservado" in texto and "mesmo número" not in texto
        status, texto = erros.resposta(ex)
        assert status == 502 and "mesmo número" not in texto and "reservado" not in texto and "tente de novo" in texto


def test_o_resto_dos_erros_continua_com_o_status_de_antes():
    assert erros.resposta(E.Limite("x"))[0] == 429 and erros.resposta(E.SemLogin("x"))[0] == 401
    assert erros.resposta(E.ErroFracttal("ASSET_X", "m"))[0] == 502 and erros.resposta(erros.Conflito("x"))[0] == 409
    assert erros.resposta(erros.NaoConfere("x"))[0] == 502 and erros.resposta(F.Recusada("x"))[0] == 503
    assert erros.resposta(ValueError("x"))[0] == 400
    with pytest.raises(KeyError):
        erros.resposta(KeyError("bug nosso"))                    # o que não é de nenhum tipo sobe: a tela não o disfarça
