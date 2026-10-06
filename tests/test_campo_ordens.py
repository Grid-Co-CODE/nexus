"""Ordens de serviço nativas do Nexus (Levi, 04/10/2026: "passa para o Nexus logo")."""
from datetime import datetime, timedelta

import pytest
from test_campo_regras_app import TabelaFalsa

from nexus.campo import leitura, ordens, regras_app, tabelas


def _ts(dias_atras):
    return (datetime.utcnow() - timedelta(days=dias_atras)).strftime("%Y-%m-%dT%H:%M:%S")


def _registro(rk, atras, os_, q, devolvida=False, pontual=True, prev=60, real=60, status=3):
    """O registro de fechamento que o App grava (tabela qualidadelog)."""
    return {"PartitionKey": "q", "RowKey": rk, "server_ts": _ts(atras), "email": f"{rk}@exemplo.test",
            "nome": f"Técnico {rk}", "os": os_, "tarefa": f"Tarefa {os_}", "usina": "Usina A", "cluster": "SP 01",
            "fx_tipo": "Corretiva", "qualidade": q, "foi_devolvida": devolvida, "pontual": pontual,
            "fx_dur_prev_min": prev, "fx_dur_real_min": real, "fx_status": status}


@pytest.fixture
def campo():
    dados = {"qualidadelog": [
        _registro("a", 1, "15140", 96, prev=60, real=70, status=regras_app.STATUS_IN_REVIEW),
        _registro("b", 2, "15131", 58, devolvida=True, pontual=False, prev=90, real=14),
        _registro("c", 3, "15118", 80),
        _registro("d", 10, "15002", 40),          # janela anterior (7 dias antes)
    ]}
    tabelas.usar_fornecedor(lambda nome: TabelaFalsa(dados.setdefault(nome, [])))
    leitura.limpar_cache()
    yield dados
    tabelas.usar_fornecedor(None)
    leitura.limpar_cache()


def test_numeros_do_periodo_e_da_janela_anterior(campo):
    d = ordens.painel(7).dados
    r = d["atual"]["resumo"]
    assert (r["os"], r["devolvidas"], r["retrabalho_pct"], r["em_verificacao"]) == (3, 1, 33, 1)
    assert r["qualidade_media"] == round((96 + 58 + 80) / 3)
    assert d["anterior"]["os"] == 1 and d["anterior"]["qualidade_media"] == 40


def test_periodo_estranho_vira_7_dias(campo):
    assert ordens.painel(13).dados["dias"] == 7


def test_tela_do_nexus(logado, campo):
    html = logado.get("/t/campo/os").get_data(as_text=True)
    assert "<iframe" not in html and 'class="campo-nativa"' in html
    assert ">15140<" in html and ">15131<" in html and "Devolvida" in html
    assert "do previsto" in html                       # o número do App, com o rótulo certo
    html = logado.get("/t/campo/os?faixa=dev").get_data(as_text=True)
    assert ">15131<" in html and ">15140<" not in html
    html = logado.get("/t/campo/os?faixa=ok").get_data(as_text=True)
    assert ">15140<" in html and ">15131<" not in html and ">15118<" not in html
