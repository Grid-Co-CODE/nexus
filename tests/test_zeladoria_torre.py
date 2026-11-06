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
    assert c.get("/t/zeladoria/api/eu").get_json() == {"user": {"id": "u-1", "email": "Fulano@Exemplo.com"},
                                                         "grava": False}
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
    r = logado.post("/t/zeladoria/api/funcao/fracttal-fotos", json={"folio": "2"}).get_json()
    assert r["folio"] == "2" and [f["descricao"] for f in r["fotos"]] == ["Sujidade dos módulos — 4",
                                                                           "Altura da vegetação — 5"]
    assert all(f["url"].endswith(f"/t/zeladoria/foto/2/{i}") for i, f in enumerate(r["fotos"]))
    assert "https://" not in json.dumps(r)
    assert r["checklist"] == [{"item": "Sujidade dos módulos", "valor": "4"}]
    assert logado.post("/t/zeladoria/api/funcao/fracttal-fotos", json={"folio": "12a"}).status_code == 400


def test_funcao_que_nao_existe_e_recusada_e_o_sincronizar_diz_que_vem_da_copia(logado, copiado):
    r = logado.post("/t/zeladoria/api/funcao/outra-funcao", json={})
    assert r.status_code == 405 and r.get_json() == {"erro": "Cópia só leitura até a troca."}
    # até a troca, o "Sincronizar com Fracttal" do Radar mostra o porquê no aviso dele (o `d.erro`), em vez de "Não foi
    # possível sincronizar agora"
    r = logado.post("/t/zeladoria/api/funcao/fracttal-sync", json={"forcar": True}).get_json()
    assert r["ok"] is False and "cópia do Radar" in r["erro"]


def test_so_o_head_ve_todos_os_perfis(cliente, copiado):
    c = _entrar_como(cliente, "fulano@exemplo.com")             # aprovado, papel Analista
    assert [p["user_id"] for p in c.get("/t/zeladoria/api/rf/rf_perfis").get_json()] == ["u-1"]


def test_foto_so_de_ronda_da_copia_e_so_para_aprovado(cliente, logado, copiado, monkeypatch):
    from nexus.campo import ronda_fotos
    monkeypatch.setattr(ronda_fotos, "tela", lambda folio, i, ler=None: (b"jpg", "image/jpeg"))
    assert logado.get("/t/zeladoria/foto/2/0").status_code == 200          # a OS 2 é ronda da cópia
    assert logado.get("/t/zeladoria/foto/999/0").status_code == 404        # OS que não é ronda da zeladoria
    assert logado.post("/t/zeladoria/api/funcao/fracttal-fotos", json={"folio": "999"}).status_code == 404
    pendente = _entrar_como(cliente, "beltrano@exemplo.com")
    assert pendente.get("/t/zeladoria/foto/2/0").status_code == 403


def test_o_clone_nasce_no_tema_do_nexus(logado, copiado):
    """O escuro é o padrão do Nexus; o claro vem do cookie do botão do topo. O clone muda junto, ao vivo, pelo aviso que
    o botão grava no navegador (`nexus.tema`)."""
    html = logado.get("/t/zeladoria/app").get_data(as_text=True)
    assert '<html lang="pt-BR" data-theme="dark">' in html and 'window.ZELADORIA_TEMA = "dark"' in html
    assert "nexus.tema" in html
    logado.set_cookie("nexus_tema", "claro")
    html = logado.get("/t/zeladoria/app").get_data(as_text=True)
    assert '<html lang="pt-BR" data-theme="light" data-tema="claro">' in html and 'window.ZELADORIA_TEMA = "light"' in html


def test_o_clone_usa_os_tokens_do_nexus(logado, copiado):
    """Levi, 03/11/2026: "bote aquele azul nexus para ficar no padrão nexus de planilha e cards". A torre põe os tokens
    do próprio nexus.css antes da paleta da Zeladoria, com o atributo do clone para vencer o CSS dele."""
    html = logado.get("/t/zeladoria/app").get_data(as_text=True)
    tokens = html[html.index('<style id="nexus-tokens">'):html.index('<style id="zeladoria-paleta">')]
    assert ":root[data-theme]{" in tokens and ':root[data-theme][data-tema="claro"]{' in tokens
    assert "--superficie:#161d30" in tokens and "--fundo:#090d18" in tokens and "--info:" in tokens
    assert ".topo" not in tokens and "box-sizing" not in tokens


def test_banco_fora_do_ar_avisa_sem_erro_500(logado, banco, monkeypatch):
    """Em 03/11/2026 a API do banco deu 502 em dois de cada três pedidos, e a tela caía em erro 500."""
    import requests
    from nexus.dados import livros

    def fora(*a, **k):
        raise requests.HTTPError("502 Server Error: Bad Gateway")
    monkeypatch.setattr(livros, "abas", fora)
    r = logado.get("/t/zeladoria/visao-geral")
    assert r.status_code == 200 and "O banco do Nexus não respondeu agora" in r.get_data(as_text=True)
    assert logado.get("/t/zeladoria/api/rf/rf_usinas").status_code == 503
