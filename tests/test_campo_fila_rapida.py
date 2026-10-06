"""Aprovação de OS (05/10/2026): o gargalo da fila do Fracttal, os filtros de equipe e supervisor pelo cadastro, e a
sessão vencida do Fracttal no OS Creator voltando ao login (Levi: "por qual motivo demora tanto ... exponha e
resolva!", "tem que voltar a logar no Fracttal", "Adicione um filtro de supervisores e Equipes")."""
import pytest
from pg_falso import ApiPGFalsa
from test_campo_aprovacao import FracttalFalso, _nota, _os
from test_campo_regras_app import TabelaFalsa
from test_campo_visao import _aba

from nexus.campo import fracttal, leitura, tabelas, visao


class _Resp:
    def __init__(self, status, corpo=None):
        self.status_code, self._corpo = status, corpo or {}

    def json(self):
        return self._corpo

    def raise_for_status(self):
        pass


def test_recusa_em_segundo_plano_espera_e_tenta_de_novo(monkeypatch):
    import requests
    respostas = [_Resp(429), _Resp(200, {"data": [1]})]
    monkeypatch.setattr(requests, "get", lambda *a, **k: respostas.pop(0))
    monkeypatch.setattr(fracttal, "_token", lambda: "t")
    monkeypatch.setattr(fracttal, "ESPERAS_RECUSA_S", (0, 0))
    assert fracttal.ler("work_orders?x=1") == {"data": [1]} and respostas == []


def test_recusa_dentro_da_tela_sobe_na_hora(app, monkeypatch):
    import requests
    chamadas = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: chamadas.append(1) or _Resp(429))
    monkeypatch.setattr(fracttal, "_token", lambda: "t")
    with app.test_request_context():
        with pytest.raises(fracttal.Recusado):
            fracttal.ler("work_orders?x=1")
    assert len(chamadas) == 1


def test_no_maximo_4_pedidos_ao_mesmo_tempo(monkeypatch):
    import threading
    import time
    import requests
    agora, pico = [0], [0]
    trava = threading.Lock()

    def get(*a, **k):
        with trava:
            agora[0] += 1
            pico[0] = max(pico[0], agora[0])
        time.sleep(0.05)
        with trava:
            agora[0] -= 1
        return _Resp(200, {"data": []})
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(fracttal, "_token", lambda: "t")
    monkeypatch.setattr(fracttal, "INTERVALO_S", 0)
    ts = [threading.Thread(target=fracttal.ler, args=(f"p{i}",)) for i in range(12)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert 1 < pico[0] <= fracttal.SIMULTANEOS


@pytest.fixture
def fila_e_cadastro(app):
    """A fila do Fracttal (usina "SP 01" no Fracttal) e o cadastro ligando "SP 01" à usina 1 da equipe SP Norte 01."""
    api = ApiPGFalsa()
    _aba(api, "cadastro_nexus", "usinas", [
        {"usina_id": 1, "nome": "Usina A", "status": "OPERAÇÃO", "equipe_id": 10, "data_mobilizacao": "2025-01-01",
         "uf": "SP"},
        {"usina_id": 2, "nome": "Usina B", "status": "OPERAÇÃO", "equipe_id": 20, "data_mobilizacao": "2025-01-01",
         "uf": "SC"}])
    _aba(api, "cadastro_nexus", "equipes", [{"equipe_id": 10, "nome": "SP Norte 01"}, {"equipe_id": 20, "nome": "SC Oeste 01"}])
    _aba(api, "cadastro_nexus", "de_para", [
        {"usina_id": 1, "sistema": "Fracttal · Classificação 1", "chave_externa": "SP 01"},
        {"usina_id": 2, "sistema": "Fracttal · Classificação 1", "chave_externa": "SC 01"}])
    _aba(api, "cadastro_nexus", "pessoas", [
        {"pessoa_id": 1, "vinculo": "Colaborador de campo", "equipe_id": 10, "status": "Ativo", "supervisor_id": 90},
        {"pessoa_id": 2, "vinculo": "Colaborador de campo", "equipe_id": 20, "status": "Ativo", "supervisor_id": 91}])
    app.config.update(GRIDCO_DB_API="http://pg.falso")
    app.extensions["nexus_dados_sessao"] = api
    dados = {"qualidadelog": [_nota(15102, 96), _nota(15088, 71)]}
    fx = FracttalFalso([_os(15002, 33, "Técnico 7"), _os(15088, 8, "Técnico 4"), _os(15102, 4, "Técnico 5")])
    tabelas.usar_fornecedor(lambda nome: TabelaFalsa(dados.setdefault(nome, [])))
    fracttal.usar_fornecedor(fx)
    leitura.limpar_cache()
    visao.limpar()
    yield
    tabelas.usar_fornecedor(None)
    fracttal.usar_fornecedor(None)
    leitura.limpar_cache()
    visao.limpar()
    app.extensions.pop("nexus_dados_sessao", None)


def test_filtro_de_equipe_e_supervisor_pelo_cadastro(fila_e_cadastro, logado):
    html = logado.get("/t/campo/aprovacao?vista=fila&dias=60").get_data(as_text=True)
    assert 'name="equipe"' in html and 'name="supervisor"' in html and "SP Norte 01" in html
    assert ">15102<" in html and ">15002<" in html
    html = logado.get("/t/campo/aprovacao?vista=fila&dias=60&equipe=SP+Norte+01").get_data(as_text=True)
    assert ">15102<" in html and ">15088<" in html and ">15002<" in html          # as 3 são da usina "SP 01"
    html = logado.get("/t/campo/aprovacao?vista=fila&dias=60&equipe=SC+Oeste+01").get_data(as_text=True)
    assert ">15102<" not in html and "Nada na fila com esses filtros" in html
    html = logado.get("/t/campo/aprovacao?vista=fila&dias=60&supervisor=Supervisor+91").get_data(as_text=True)
    assert ">15102<" not in html                                                  # o supervisor 91 é da SC Oeste 01


# ── OS Creator: sessão do Fracttal vencida volta ao login ──────────────────────────────────────────────────────
def _clone_que_responde(corpo: bytes, tipo: str):
    def wsgi(environ, start_response):
        start_response("200 OK", [("Content-Type", tipo)])
        return [corpo]
    wsgi.config = {"SESSION_COOKIE_NAME": "os_sessao"}
    return wsgi


def test_jwt_vencido_no_os_creator_volta_ao_login(logado, monkeypatch):
    from nexus.torres.oscreator import ponte
    aviso = "⚠ O JWT do login do Fracttal expirou — cole um novo em fracttal_login.txt.".encode()
    monkeypatch.setattr(ponte, "clone", lambda app: _clone_que_responde(b"<html><head></head>" + aviso, "text/html"))
    r = logado.get("/os/historico?modo=criadas")
    assert r.status_code == 302 and r.headers["Location"] == "/os/login?next=%2Fos%2Fhistorico%3Fmodo%3Dcriadas"
    assert any("os_sessao=;" in c and "Path=/os" in c for c in r.headers.getlist("Set-Cookie"))
    monkeypatch.setattr(ponte, "clone", lambda app: _clone_que_responde(b'{"erro": "' + aviso + b'"}', "application/json"))
    r = logado.get("/os/historico/meta")
    assert r.status_code == 401 and r.get_json()["login"] is True


def test_aprovacao_para_insight(fila_e_cadastro, logado):
    """Levi, 05/10: "refaça essa parte de aprovação de OS para retirada de bons insights"."""
    html = logado.get("/t/campo/aprovacao?dias=60").get_data(as_text=True)
    # abre nos cartões por supervisor (do cadastro, pela usina do Fracttal "SP 01")
    assert 'class="cn-equipes"' in html and "Supervisor 90" in html and "tarefas esperando aprovação" in html
    assert "Prontas para aprovar" in html and "Precisam do seu olho" in html and "Uso do App" in html
    assert "Idade da fila" in html and "31 a 60 dias" in html                       # a OS 15002 espera 33 dias
    # os indicadores e a idade filtram a fila
    html = logado.get("/t/campo/aprovacao?dias=60&balde=completa").get_data(as_text=True)
    assert ">15102<" in html and ">15088<" not in html and "Fila de verificação" in html
    html = logado.get("/t/campo/aprovacao?dias=60&idade=31-60").get_data(as_text=True)
    assert ">15002<" in html and ">15102<" not in html and "Usina A" in html and "SP Norte 01" in html
    html = logado.get("/t/campo/aprovacao?dias=60&vista=tecnicos").get_data(as_text=True)
    assert "Técnico 7" in html and "<th>Uso do App</th>" in html
    r = logado.get("/t/campo/aprovacao?dias=60&csv=1")
    assert r.mimetype == "text/csv" and "15102" in r.get_data(as_text=True)


def test_linha_da_fila_diz_por_que_do_grupo_e_aprova_pelo_os_creator(fila_e_cadastro, logado):
    """Levi, 05/10: "expandir a linha para entender o motivo do grupo, pq precisa do meu olho?" e "ao expandir o
    supervisor deve conseguir aprovar a OS também, usando o mesmo caminho que o OS Creator Web"."""
    from nexus.campo import aprovacao, regras_app
    olho = {"pelo_app": True, "qualidade": 71, "foi_devolvida": True}
    assert [c for c, _ in aprovacao.motivos(olho)] == ["alerta", "alerta"]
    assert "abaixo de 80%" in aprovacao.motivos(olho)[0][1] and "devolvida" in aprovacao.motivos(olho)[1][1]
    assert aprovacao.motivos({"pelo_app": True, "qualidade": 96})[0][0] == "ok"
    assert "fora do App" in aprovacao.motivos({"pelo_app": False})[0][1]
    html = logado.get("/t/campo/aprovacao?dias=60&vista=fila").get_data(as_text=True)
    assert 'class="cn-detalhe" hidden' in html and "Por que está em" in html and "Nota do registro 71%" in html
    assert 'data-wo="15088"' in html and "Aprovar a OS 15088" in html and "/os/api/os/" in html
    # o Concluir do OS Creator sem login do Fracttal: 401 pedindo login (a tela leva ao login e volta)
    r = logado.post("/os/api/os/15088/concluir", json={"folio": "15088"})
    assert r.status_code == 401 and r.get_json()["login"] is True
    assert logado.get("/os/_nexus/voltar?para=/t/campo/aprovacao%3Fvista%3Dfila").headers["Location"].endswith("/t/campo/aprovacao?vista=fila")
    assert logado.get("/os/_nexus/voltar?para=https://fora.test/x").headers["Location"].endswith("/t/campo/aprovacao")
    # aprovada: sai da fila guardada na hora
    antes = len(regras_app._FILA_CACHE["linhas"])
    assert logado.post("/t/campo/aprovacao/15088/tirar").get_json()["tarefas"] == 1
    assert len(regras_app._FILA_CACHE["linhas"]) == antes - 1
    assert ">15088<" not in logado.get("/t/campo/aprovacao?dias=60&vista=fila").get_data(as_text=True)
