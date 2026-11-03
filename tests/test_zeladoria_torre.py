"""A torre Zeladoria só leitura: as 18 abas do Radar no menu do Nexus, o clone num iframe e as rotas que a ponte usa.

O banco falso recebe a cópia de verdade (`copia.copiar` sobre uma exportação mínima), e a torre lê, decifra e entrega.
Nomes e e-mails fictícios.
"""
import json

import pytest

from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.zeladoria import copia, leitura
from nexus.zeladoria import tabelas as T
from tests.pg_falso import ApiPGFalsa
from tests.test_zeladoria_copia import AGORA, DE_PARA, _exportacao

CHAVE = gerar_chave()


def _exp():
    exp = _exportacao()
    exp["tipos"]["perfis"] = [["user_id", "uuid"], ["email", "text"], ["papel", "text"], ["status", "text"]]
    exp["chaves"]["perfis"] = "user_id"
    exp["tabelas"]["perfis"] = [
        {"user_id": "u-1", "email": "Fulano@Exemplo.com", "papel": "Analista", "status": "aprovado"},
        {"user_id": "u-2", "email": "beltrano@exemplo.com", "papel": "Outro", "status": "pendente"}]
    exp["tipos"]["fracttal_rondas"] = [["folio", "bigint"], ["usina_chave", "text"], ["data", "date"], ["tecnico", "text"]]
    exp["chaves"]["fracttal_rondas"] = "folio"
    exp["tabelas"]["fracttal_rondas"] = [
        {"folio": 1, "usina_chave": "X", "data": "2026-10-01", "tecnico": "Fulano de Tal"},
        {"folio": 2, "usina_chave": "X", "data": "2026-10-20", "tecnico": "Fulano de Tal"},
        {"folio": 3, "usina_chave": "Y", "data": "2026-10-10", "tecnico": "Beltrano"}]
    return exp


@pytest.fixture
def banco(app):
    api = ApiPGFalsa()
    app.config.update(GRIDCO_DB_API="http://pg.falso", GRIDCO_SQL_TOKEN="t", NEXUS_CHAVE_CADASTRO=CHAVE)
    app.extensions["nexus_dados_sessao"] = api
    leitura.limpar()
    yield api
    leitura.limpar()


@pytest.fixture
def copiado(banco):
    copia.copiar(_exp(), de_para=DE_PARA, cofre=Cofre(CHAVE), base="http://pg.falso", token="t", sessao=banco,
                 gravar=True, agora=AGORA)
    return banco


def _entrar_como(cliente, email):
    with cliente.session_transaction() as s:
        s["logado"] = True
        s["admin"] = False
        s["usuario"] = {"email": email, "nome": "Pessoa de Teste", "perfil": ""}
    return cliente


def test_cada_tela_abre_o_clone(logado, copiado):
    from nexus.torres.zeladoria import ABAS, TORRE
    assert len(TORRE.telas) == 18 and set(ABAS) == {t.id for t in TORRE.telas}
    for tela in TORRE.telas:
        html = logado.get(f"/t/zeladoria/{tela.id}").get_data(as_text=True)
        assert f'/t/zeladoria/app?aba={ABAS[tela.id]}"' in html and "<iframe" in html, tela.id
    assert ABAS["visao-geral"] == "overview" and ABAS["farol-contratual"] == "analiseServicos"


def test_app_injeta_config_e_ponte(logado, copiado):
    html = logado.get("/t/zeladoria/app?aba=cotacoes").get_data(as_text=True)
    assert "window.ZELADORIA = " in html and '"somenteLeitura": true' in html
    assert 'window.ZELADORIA_ABA = "cotacoes"' in html
    assert "/static/zeladoria/ponte.js" in html and "iniciarRadarApp()" in html
    assert "<!--ZELADORIA:" not in html


def test_aba_pedida_que_nao_existe_abre_a_visao_geral(logado, copiado):
    html = logado.get('/t/zeladoria/app?aba=</script><script>alert(1)').get_data(as_text=True)
    assert 'window.ZELADORIA_ABA = "overview"' in html


def test_filtros(logado, copiado):
    r = logado.get('/t/zeladoria/api/rf/rf_fracttal_rondas?eq=usina_chave:"X"&order=data:desc').get_json()
    assert [x["folio"] for x in r] == [2, 1] and r[0]["tecnico"] == "Fulano de Tal"
    r = logado.get('/t/zeladoria/api/rf/rf_fracttal_rondas?neq=usina_chave:"X"').get_json()
    assert [x["folio"] for x in r] == [3]
    assert logado.get("/t/zeladoria/api/rf/rf_nao_existe").status_code == 404


def test_pendente_so_ve_a_propria_linha(cliente, copiado):
    c = _entrar_como(cliente, "beltrano@exemplo.com")
    assert c.get("/t/zeladoria/api/rf/rf_fornecedores").get_json() == []
    assert [p["user_id"] for p in c.get("/t/zeladoria/api/rf/rf_perfis").get_json()] == ["u-2"]
    novo = _entrar_como(cliente, "ninguem@exemplo.com")
    assert novo.get("/t/zeladoria/api/rf/rf_perfis").get_json() == []
    eu = novo.get("/t/zeladoria/api/eu").get_json()
    assert eu["user"]["email"] == "ninguem@exemplo.com" and eu["user"]["id"].startswith("nexus:")


def test_aprovado_casa_pelo_email_e_ve_decifrado(cliente, copiado):
    c = _entrar_como(cliente, " fulano@exemplo.com ")
    assert c.get("/t/zeladoria/api/eu").get_json() == {"user": {"id": "u-1", "email": "Fulano@Exemplo.com"}}
    forn = c.get("/t/zeladoria/api/rf/rf_fornecedores").get_json()
    assert forn[0]["empresa"] == "Fulano de Tal MEI" and forn[0]["valor_mes"] == 900


def test_admin_e_head(logado, copiado):
    eu = logado.get("/t/zeladoria/api/eu").get_json()["user"]
    assert eu["id"] == "nexus-admin"
    perfil = logado.get('/t/zeladoria/api/rf/rf_perfis?eq=user_id:"nexus-admin"').get_json()
    assert perfil == [{"user_id": "nexus-admin", "email": eu["email"], "papel": "HEAD", "status": "aprovado"}]


def test_copia_ausente(logado, banco):
    html = logado.get("/t/zeladoria/visao-geral").get_data(as_text=True)
    assert "A cópia do Radar ainda não foi feita" in html and "<iframe" not in html
    r = logado.get("/t/zeladoria/api/rf/rf_usinas")
    assert r.status_code == 503 and "cópia" in r.get_json()["erro"]


def test_cifra_quebrada_nao_derruba(logado, copiado, app):
    app.config["NEXUS_CHAVE_CADASTRO"] = gerar_chave()          # a chave trocou depois da cópia
    leitura.limpar()
    r = logado.get("/t/zeladoria/api/rf/rf_fornecedores")
    assert r.status_code == 200 and r.get_json()[0]["empresa"] == "(não abre)"


def test_fotos(logado, copiado, monkeypatch):
    from nexus.campo import nota_fracttal, ronda_fotos
    monkeypatch.setattr(ronda_fotos, "anexos", lambda folio, ler=None: [
        {"i": 0, "desc": "Sujidade dos módulos — 4", "valor": "https://x/a.jpg", "mime": "image/jpeg"},
        {"i": 1, "desc": "Altura da vegetação — 5", "valor": "https://x/b.jpg", "mime": "image/jpeg"}])
    monkeypatch.setattr(nota_fracttal, "subtarefas_da_os", lambda folio, ler=None: [
        {"description": "Sujidade dos módulos", "value": "4"}])
    r = logado.post("/t/zeladoria/api/funcao/fracttal-fotos", json={"folio": "123"}).get_json()
    assert r["folio"] == "123" and [f["descricao"] for f in r["fotos"]] == ["Sujidade dos módulos — 4",
                                                                           "Altura da vegetação — 5"]
    assert all(f["url"].endswith(f"/t/zeladoria/foto/123/{i}") for i, f in enumerate(r["fotos"]))
    assert "https://" not in json.dumps(r)
    assert r["checklist"] == [{"item": "Sujidade dos módulos", "valor": "4"}]
    assert logado.post("/t/zeladoria/api/funcao/fracttal-fotos", json={"folio": "12a"}).status_code == 400


def test_funcao_que_grava_e_recusada(logado, copiado):
    r = logado.post("/t/zeladoria/api/funcao/fracttal-sync", json={})
    assert r.status_code == 405 and r.get_json() == {"erro": "Cópia só leitura até a troca."}
