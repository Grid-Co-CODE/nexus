"""O link do cronograma da zeladoria servido pelo Nexus (etapa 5, 06/11/2026): a mesma resposta da função
`cronograma-api` do Radar, a chave no `x-api-key`, e o retrato que o gravador só regrava quando o cronograma muda.
Usinas e clientes fictícios."""
from datetime import datetime, timezone

import pytest

from nexus.auth import ROTAS_PUBLICAS
from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.zeladoria import cronograma_api as CA
from nexus.zeladoria import gravacao, leitura

CHAVE = "k" * 40
AGORA = datetime(2026, 11, 6, 2, 0, tzinfo=timezone.utc)        # 23:00 de 05/11 em Brasília


def _snap():
    return {"versao": 1, "usinas": [
        {"id": 1, "usina": "Usina Águia", "cliente": "Cliente Á", "uf": "SP", "cidade": "Cidade A", "ultimo": {},
         "historico": [{"servico": "Roçagem", "servico_codigo": "rocagem", "data": "2026-10-01"},
                       {"servico": "Roçagem", "servico_codigo": "rocagem", "data": "2026-06-01"}],
         "proximos": [{"id": "p1", "servico": "Roçagem", "inicio": "2026-11-01", "fim": "2026-11-05", "confirmado": True,
                       "iniciado": False, "remarcacoes": []},
                      {"id": "p2", "servico": "Poda química", "inicio": "2026-12-01", "fim": "2026-12-03",
                       "confirmado": False, "iniciado": True, "remarcacoes": []}]},
        {"id": 2, "usina": "Usina Beta", "cliente": "Cliente B", "uf": "MG", "historico": [], "proximos": []}]}


def _est(snap=None):
    linhas = [] if snap is None else [{"id": "cronograma", "dados": snap, "atualizado_em": "2026-11-05T12:00:00+00:00"}]
    return {"abas": {"cronograma_publico": linhas}}


def test_a_resposta_e_a_do_radar():
    status, r = CA.responder(_est(_snap()), {}, agora=AGORA)
    assert status == 200 and r["total_usinas"] == 2 and r["servicos"] == ["Roçagem", "Limpeza de módulos", "Poda química"]
    assert r["atualizado_em"] == "2026-11-05T12:00:00+00:00" and r["fonte"].startswith("Radar de Fornecedores")
    p1, p2 = r["usinas"][0]["proximos"]
    assert (p1["situacao"], p1["atrasado"], p2["situacao"], p2["atrasado"]) == ("confirmado", False, "em_execucao", False)
    assert "iniciado" not in p1 and "confirmado" not in p1
    # o "hoje" é o de Brasília: às 02:00 UTC de 06/11 ainda é 05/11, e o fim em 05/11 não está atrasado
    _s, r2 = CA.responder(_est(_snap()), {}, agora=AGORA.replace(hour=4))
    assert r2["usinas"][0]["proximos"][0]["atrasado"] is True


def test_os_filtros_sem_acento_e_o_historico_desde():
    _s, r = CA.responder(_est(_snap()), {"usina": "aguia", "cliente": "cliente a", "uf": "sp",
                                         "historico_desde": "2026-09-01"}, agora=AGORA)
    assert [u["id"] for u in r["usinas"]] == [1] and len(r["usinas"][0]["historico"]) == 1
    _s, r = CA.responder(_est(_snap()), {"cliente": "cliente", "historico_desde": "ontem"}, agora=AGORA)
    assert r["total_usinas"] == 0                                    # cliente é igual, não "contém"
    assert CA.responder(_est(None), {}, agora=AGORA)[0] == 503       # sem retrato publicado


@pytest.fixture
def com_dados(app, tmp_path, monkeypatch):
    app.config["NEXUS_DADOS"] = str(tmp_path / "dados")
    monkeypatch.setattr(leitura, "estado", lambda cfg: _est(_snap()))
    return app


def test_o_link_sem_chave_no_nexus_diz_que_nao_esta_configurado(cliente, com_dados):
    assert "torre_zeladoria.cronograma_api" in ROTAS_PUBLICAS
    r = cliente.get("/t/zeladoria/api/cronograma", headers={"x-api-key": CHAVE})
    assert r.status_code == 503 and "não configurada" in r.get_json()["erro"]


def test_o_link_pede_a_chave_certa_e_nao_pede_login(cliente, com_dados):
    com_dados.config[CA.CHAVE] = CHAVE
    assert cliente.get("/t/zeladoria/api/cronograma").status_code == 401
    assert cliente.get("/t/zeladoria/api/cronograma", headers={"x-api-key": "k" * 39}).status_code == 401
    r = cliente.get("/t/zeladoria/api/cronograma?uf=MG", headers={"x-api-key": CHAVE})
    assert r.status_code == 200 and r.get_json()["total_usinas"] == 1
    assert r.headers["Access-Control-Allow-Origin"] == "*" and r.headers["Cache-Control"] == "no-store"
    assert cliente.options("/t/zeladoria/api/cronograma").status_code == 200


def test_a_chave_curta_nao_entra_pela_tela():
    from nexus.auth import chaves
    with pytest.raises(chaves.Recusada):
        chaves.CHAVES[CA.CHAVE]["conferir"]("curta demais")
    assert "40 caracteres" in chaves.CHAVES[CA.CHAVE]["conferir"](CHAVE)


def test_o_retrato_so_regrava_quando_o_cronograma_muda(tmp_path):
    g = gravacao.Gravador(base="http://pg.falso", token="t", sessao=None, cofre=Cofre(gerar_chave()),
                          diario=tmp_path / "diario.jsonl")
    tipos = {"id": "text", "dados": "jsonb", "atualizado_em": "timestamp with time zone", "atualizado_por": "text"}
    est = _est(_snap())
    g.carregar({"abas": est["abas"], "tipos": {"cronograma_publico": tipos}, "chaves": {"cronograma_publico": "id"},
                "versao": 0, "versoes": {}})
    quem = {"status": "aprovado", "papel": "HEAD", "email": "pessoa@exemplo.com"}

    def publicar(dados):
        return g.aplicar([{"op": "upsert", "view": "rf_cronograma_publico", "linhas": [
            {"id": "cronograma", "dados": dados, "atualizado_em": "2026-11-06T10:00:00Z",
             "atualizado_por": "pessoa@exemplo.com"}]}], quem, g.estado["versao"])["versao"]
    assert publicar(_snap()) == 0                                    # a página abriu: só a hora mudou
    novo = _snap()
    novo["usinas"][1]["proximos"].append({"id": "p3", "servico": "Roçagem", "inicio": "2027-01-01"})
    assert publicar(novo) == 1
    assert g.estado["abas"]["cronograma_publico"][0]["dados"]["usinas"][1]["proximos"][0]["id"] == "p3"
