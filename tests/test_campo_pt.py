"""Permissões de trabalho nativas do Nexus (Levi, 04/10/2026: "pode passar para o Nexus").

As PT moram, no App, na tabela dos tokens do Fracttal (fracttaltokens, partição "pt"). Aqui a tabela é falsa, no mesmo
formato; o Nexus só lê as partições liberadas e nunca a dos tokens.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from test_campo_atencao import TabelaFalsa

from nexus.campo import atencao, pessoas, pt, tabelas


def _iso(minutos_atras=0, dias_atras=0):
    t = datetime.now(timezone.utc) - timedelta(minutes=minutos_atras, days=dias_atras)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _pt(rk, status, criado, **mais):
    """Uma PT como o App grava: atividades críticas com as respostas da APR (SIM/NAO/NA)."""
    e = {"PartitionKey": "pt", "RowKey": rk, "status": status, "criado_em": criado, "os": "15150",
         "tarefa": "Troca de fusível", "usina": "Usina A", "cluster": "SP 01", "nome": "Técnico 5",
         "email": "tecnico5@exemplo.test", "atividades": json.dumps([{"id": "altura", "r": ["SIM", "NAO", "SIM"]}])}
    e.update(mais)
    return e


@pytest.fixture
def campo():
    dados = {"fracttaltokens": [
        _pt("pt1", "aguardando", _iso(minutos_atras=47)),
        _pt("pt2", "aguardando", _iso(minutos_atras=6)),
        _pt("pt3", "de_acordo", _iso(dias_atras=1), decidido_em=_iso(dias_atras=1), decidido_nome="Supervisor SP"),
        _pt("pt4", "negada", _iso(dias_atras=2), decidido_em=_iso(dias_atras=2), motivo="Sem bloqueio na APR"),
        _pt("pt5", "de_acordo", _iso(dias_atras=12), decidido_em=_iso(dias_atras=12)),     # validade de 7 dias: vencida
        {"PartitionKey": "tok", "RowKey": "alguem@exemplo.test", "token": "SEGREDO"},
    ]}
    tabelas.usar_fornecedor(lambda nome: TabelaFalsa(dados.setdefault(nome, [])))
    atencao.limpar_cache()
    yield dados
    tabelas.usar_fornecedor(None)
    atencao.limpar_cache()


def test_esperando_a_mais_antiga_primeiro_e_o_destaque_de_30_min(campo):
    d = pt.painel().dados
    assert [p["id"] for p in d["esperando"]] == ["pt1", "pt2"]
    assert d["destaque_min"] == 30
    assert [p["id"] for p in d["esperando"] if p["atrasada"]] == ["pt1"]


def test_historico_com_a_situacao_do_painel(campo):
    d = pt.painel().dados
    sit = {p["id"]: p["situacao"] for p in d["historico"]}
    assert sit == {"pt1": "aguardando", "pt2": "aguardando", "pt3": "de_acordo", "pt4": "negada", "pt5": "vencida"}
    assert d["contagem"] == {"aguardando": 2, "de_acordo": 1, "negada": 1, "vencida": 1}


def test_nexus_nao_le_a_particao_dos_tokens(campo):
    tok = pessoas.tabela_dos_tokens()
    with pytest.raises(PermissionError):
        tok.get_entity("tok", "alguem@exemplo.test")
    with pytest.raises(PermissionError):
        tok.query_entities("PartitionKey eq 'tok'")
    with pytest.raises(PermissionError):
        tok.query_entities("RowKey eq 'x'")          # sem partição fixa também não
    # e a tela não carrega assinatura nem as respostas da APR (o modo "completo" do App)
    for p in pt.painel().dados["historico"]:
        assert "ass_tec" not in p and "ass_aprov" not in p and "apr" not in p


def test_sem_chave_a_tela_continua_no_painel_do_app(logado):
    html = logado.get("/t/campo/pt").get_data(as_text=True)
    assert '<iframe class="campo-moldura"' in html


def test_tela_do_nexus(logado, campo):
    html = logado.get("/t/campo/pt").get_data(as_text=True)
    assert "<iframe" not in html and 'class="campo-nativa"' in html
    assert "Esperando decisão" in html and "Histórico" in html
    assert "Sem bloqueio na APR" in html and "Vencida" in html and "Não autorizada" in html
    assert "SEGREDO" not in html
    html = logado.get("/t/campo/pt?sit=negada").get_data(as_text=True)
    assert "Sem bloqueio na APR" in html
