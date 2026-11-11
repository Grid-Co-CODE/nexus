"""A leitura de TESTE da API da FAMA (11/11/2026, nexus/cadastro/fama_teste.py): só o administrador, só GET, com a chave no
cabeçalho, e nada de pessoa nem de texto livre na resposta. A FAMA é de mentira (uma sessão que responde pelo caminho);
nenhum teste vai à rede."""
import json

import pytest

from nexus.cadastro import fama_teste as F

CHAVE = "chave-fama-de-teste-0123456789"


class _Resp:
    def __init__(self, corpo, status=200):
        self.corpo, self.status_code = corpo, status

    def json(self):
        return self.corpo


class _FamaFalsa:
    """Responde como as rotas da prestadora da FAMA e guarda o que foi pedido (método, caminho e a chave do cabeçalho)."""

    def __init__(self):
        self.pedidos = []
        self.os = [{"id": 10 + i, "title": "Troca do inversor", "description": "texto livre do cliente",
                    "status_id": 1, "status": {"id": 1, "service_status": "Aberta" if i % 2 else "Em execução"},
                    "type": {"id": 2, "service_type": "Corretiva"}, "severity": {"id": 1, "service_severity": "Alta"},
                    "project": {"id": 7 if i % 3 else 8, "name": "Usina Fictícia 1" if i % 3 else "Usina Fictícia 2"},
                    "creation_date": f"202{5 + i % 2}-0{1 + i % 9}-10T10:00:00", "expected_execution_date": None,
                    "contract_id": 3} for i in range(7)]

    def get(self, url, params=None, timeout=None, headers=None):
        caminho = url.replace(F.BASE, "")
        self.pedidos.append(("GET", caminho, (headers or {}).get("X-Contractor-Key")))
        if caminho == "/v2/contractor/service-orders/":
            return _Resp(self.os)
        if caminho.startswith("/v2/contractor/service-orders/"):
            return _Resp({"id": 1, "title": "Troca do inversor", "description": "texto livre do cliente",
                          "creator": {"id": 5, "full_name": "Pessoa Fictícia", "email": "pessoa@exemplo.invalid"},
                          "logs": [{"title": "o técnico fulano", "description": "esteve lá"}], "assets": []})
        return _Resp({"detail": "Could not validate credentials"}, 401)


@pytest.fixture(autouse=True)
def _sem_pausa_e_sem_copia(monkeypatch):
    monkeypatch.setattr(F, "PAUSA_S", 0)
    F._CACHE.clear()
    yield
    F._CACHE.clear()


def test_a_leitura_so_faz_get_com_a_chave_no_cabecalho_e_nao_devolve_pessoa_nem_texto():
    fama = _FamaFalsa()
    out = F.ler(CHAVE, sessao=fama)
    assert {m for m, _c, _k in fama.pedidos} == {"GET"}
    assert {k for _m, _c, k in fama.pedidos} == {CHAVE}
    assert [c for _m, c, _k in fama.pedidos] == ["/v2/contractor/service-orders/", "/v2/contractor/service-orders/15"]
    texto = json.dumps(out, ensure_ascii=False)
    assert CHAVE not in texto and "@" not in texto
    for proibido in ("texto livre", "fulano", "Troca do inversor", "Pessoa Fictícia", "esteve lá"):
        assert proibido not in texto
    lst = out["lista"]
    assert lst["total"] == 7 and lst["status"] == 200 and lst["erro_da_fama"] is None
    assert lst["por_status"] == {"Aberta": 3, "Em execução": 4}
    assert dict(lst["por_usina"]) == {"Usina Fictícia 1": 4, "Usina Fictícia 2": 3}
    assert lst["criacao"] == {"mais_antiga": "2025-01-10", "mais_nova": "2026-06-10"}
    assert lst["preenchido_pct"]["expected_execution_date"] == 0 and lst["previstas"]["com_data"] == 0
    det = out["detalhe_da_mais_nova"]
    assert det["listas"]["logs"] == {"itens": 1, "campos": ["description", "title"]}
    assert det["objetos"]["creator"] == ["email", "full_name", "id"]


def test_a_chave_recusada_diz_a_frase_da_fama():
    class Recusa(_FamaFalsa):
        def get(self, url, params=None, timeout=None, headers=None):
            self.pedidos.append(("GET", url, None))
            return _Resp({"detail": "Could not validate credentials"}, 401)
    out = F.ler(CHAVE, sessao=Recusa())
    assert out["lista"]["status"] == 401 and out["lista"]["erro_da_fama"] == "Could not validate credentials"
    assert "detalhe_da_mais_nova" not in out


def test_o_teto_de_chamadas_segura_a_leitura(monkeypatch):
    monkeypatch.setattr(F, "TETO_CHAMADAS", 1)
    fama = _FamaFalsa()
    out = F.ler(CHAVE, sessao=fama)
    assert len(fama.pedidos) == 1 and out["chamadas"] == 1
    assert out["detalhe_da_mais_nova"]["erro"] == "teto da leitura"


def test_so_o_administrador_e_sem_a_chave_diz_o_que_falta(app, cliente, logado):
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"], s["admin"] = True, False
        s["usuario"] = {"email": "pessoa@exemplo.invalid", "nome": "Pessoa", "perfil": ""}
    assert c.get("/t/base/fama-teste").status_code == 403
    app.config.pop("NEXUS_FAMA_CHAVE", None)
    r = logado.get("/t/base/fama-teste")
    assert r.status_code == 409 and "NEXUS_FAMA_CHAVE" in r.get_json()["erro"]


def test_com_a_chave_a_pagina_le_uma_vez_e_guarda(app, logado, monkeypatch):
    app.config["NEXUS_FAMA_CHAVE"] = CHAVE
    vezes = []
    monkeypatch.setattr(F, "ler", lambda chave: vezes.append(chave) or {"os": {"total": 1}})
    assert logado.get("/t/base/fama-teste").get_json() == {"os": {"total": 1}}
    logado.get("/t/base/fama-teste")
    assert vezes == [CHAVE]
    logado.get("/t/base/fama-teste?novo=1")
    assert len(vezes) == 2
