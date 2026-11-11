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
    """Responde como a FAMA pelo caminho e guarda o que foi pedido (método, caminho e cabeçalho da chave)."""

    def __init__(self):
        self.pedidos = []
        self.os = [{"id": i, "project_id": 7 if i % 2 else 8, "status_id": 1, "type_id": 2, "title": "Troca do inversor",
                    "description": "texto livre do cliente", "creation_date": f"2026-0{1 + i % 9}-10T10:00:00",
                    "assets": [{"id": 1}], "tasks": [{"id": 1}, {"id": 2}], "responsible_id": 99,
                    "logs": [{"description": "o técnico fulano esteve lá"}]} for i in range(7)]

    def get(self, url, params=None, timeout=None, headers=None):
        self.pedidos.append(("GET", url.replace(F.BASE, ""), (headers or {}).get("X-Contractor-Key")))
        caminho = url.replace(F.BASE, "")
        if caminho == "/mcp/whoami/":
            return _Resp({"user": "alguem@exemplo.invalid", "tenant": 3})
        if caminho == "/service-orders/status/":
            return _Resp([{"id": 1, "name": "Aberta"}, {"id": 2, "name": "Em execução"}])
        if caminho == "/service-orders/types/":
            return _Resp([{"id": 2, "name": "Corretiva"}])
        if caminho.startswith("/service-orders/"):
            return _Resp([])
        if caminho == "/mcp/projects/":
            return _Resp({"total": 2, "returned": 2, "projects": [{"id": 7, "name": "Usina Fictícia 1"},
                                                                  {"id": 8, "name": "Usina Fictícia 2"}]})
        if caminho == "/users/":
            return _Resp([{"id": 1, "name": "Pessoa Fictícia", "email": "pessoa@exemplo.invalid"}])
        if caminho == "/assets/":
            return _Resp([{"id": 1, "name": "Inversor 1", "serial_number": "X"}])
        if caminho == "/v2/service-orders/":
            p = params or {}
            linhas = [x for x in self.os if all(x.get(k) == v for k, v in p.items() if k in ("status_id", "type_id"))]
            ini, lim = int(p.get("offset", 0)), int(p.get("limit", 100))
            return _Resp({"total": len(linhas), "rows": linhas[ini:ini + lim]})
        return _Resp({"detail": "Not Found"}, 404)


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
    texto = json.dumps(out, ensure_ascii=False)
    assert CHAVE not in texto and "@" not in texto
    assert "texto livre" not in texto and "fulano" not in texto and "Troca do inversor" not in texto
    assert "Pessoa Fictícia" not in texto
    assert out["usuarios"]["quantos"] == 1
    assert out["os"]["total"] == 7 and out["os"]["amostra"] == 7
    assert out["os"]["preenchido_pct"]["assets"] == 100 and out["os"]["preenchido_pct"]["tasks"] == 100
    assert out["os"]["por_status"] == {"1 Aberta": 7, "2 Em execução": 0}
    assert [u["nome"] for u in out["usinas"]["lista"]] == ["Usina Fictícia 1", "Usina Fictícia 2"]
    assert out["chamadas"] <= F.TETO_CHAMADAS


def test_o_teto_de_chamadas_segura_a_leitura(monkeypatch):
    monkeypatch.setattr(F, "TETO_CHAMADAS", 3)
    fama = _FamaFalsa()
    out = F.ler(CHAVE, sessao=fama)
    assert len(fama.pedidos) == 3 and out["chamadas"] == 3


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
