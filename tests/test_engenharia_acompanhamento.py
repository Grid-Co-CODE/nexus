"""Engenharia > Confiabilidade: o acompanhamento dos ativos com sinal (Levi, 18/10/2026: "os membros de engenharia ou
administradores pegar aqueles ativos com sinal para acompanhar ou alguém da engenharia poder encaminhar para a pessoa
ver!"). Desenho em docs/superpowers/specs/2026-10-18-engenharia-acompanhamento-design.md. Banco falso
(tests/pg_falso.py); os nomes são fictícios."""
import json
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import gerar_chave
from nexus.dados import catalogo, explica
from nexus.dados.equipamento import canon, equipamento_id
from nexus.engenharia import acompanhamento as A

BRT = timezone(timedelta(hours=-3))
ANA = {"email": "ana.lima@gridco.com.br", "nome": "Ana Lima"}
BETO = {"email": "beto.souza@gridco.com.br", "nome": "Beto Souza"}
ATIVO = {"cod": "IBI200-INVR1.3", "usina_id": 1, "usina_ligada_por": "de-para do Fracttal", "nivel": "critico",
         "nFalha": 5, "n7": 3}


def _no_banco(app, api):
    app.config.update(GRIDCO_DB_API="http://pg.falso", NEXUS_CHAVE_CADASTRO=gerar_chave(),
                      NEXUS_PESSOA_HMAC="hmac-teste", GRIDCO_SQL_TOKEN="tk")
    app.extensions["nexus_dados_sessao"] = api
    A.limpar()
    with app.app_context():
        yield api
    A.limpar()
    app.extensions.pop("nexus_dados_sessao", None)


@pytest.fixture
def banco(app):
    yield from _no_banco(app, ApiPGFalsa())


@pytest.fixture
def banco_texto(app):
    yield from _no_banco(app, ApiPGFalsa(como_texto=True))


def _como(cli, usuario, admin=False):
    with cli.session_transaction() as s:
        s["logado"], s["admin"], s["usuario"] = True, admin, usuario
    return cli


def _a():
    (a,) = A.estado(A.ler(forcar=True)["eventos"]).values()
    return a


def _aid():
    return _a()["id"]


def _aid_de(cod):
    return next((a["id"] for a in A.estado(A.ler(forcar=True)["eventos"]).values()
                 if a["aberto"] and canon(a["cod"]) == canon(cod)), None)


def _lista(html):
    """A lista da aba (os cartões), sem a gaveta nem os filtros."""
    return html.split('<div class="eg-itens">', 1)[1].split("</section>", 1)[0] if 'class="eg-itens"' in html else ""


def _dec(fracttal_id, setor_id, hmac, quando):
    return {"decidida_em": quando, "data_id": int(quando[:10].replace("-", "")), "fracttal_id": fracttal_id,
            "pessoa_id": None, "pessoa_ligada_por": "", "pessoa_hmac": hmac, "setor_id": setor_id,
            "decidida_por_hmac": "", "origem": "tela"}


# ── Task 1: o livro, a leitura, o estado e o Pegar ───────────────────────────────────────────────────────────────────
def test_catalogo_registra_o_livro_e_o_fato():
    l = catalogo.LIVRO_POR_NOME[A.LIVRO]
    assert l.abas == (A.ABA_DIAG, A.ABA_EVENTO) and all(catalogo.aba_segue_a_regra(x) for x in l.abas)
    f = catalogo.POR_ID["acompanhamento_ativo"]
    assert f.area == "engenharia" and f.tipo == "transacao" and f.chave == ("id",)
    assert f.fontes == (f"{A.LIVRO} · {A.ABA_EVENTO}",)
    assert {m.coluna for m in f.medidas} == {"falhas_30d_qtd", "falhas_7d_qtd"}
    assert "acompanhamento_ativo" in explica.RESUMO and "acompanhamento_ativo" in explica.PARA_QUE


def test_pegar_comeca_com_a_pessoa_e_o_inicio_hoje(banco):
    A.pegar(ATIVO, ANA, pode=True)
    (a,) = A.estado(A.ler(forcar=True)["eventos"]).values()
    assert a["aberto"] and a["responsavel"]["nome"] == "Ana Lima" and a["cod"] == "IBI200-INVR1.3"
    assert a["inicio"] == datetime.now(BRT).date() and a["fim"] is None and a["nivel_entrada"] == "critico"
    assert a["falhas30_entrada"] == 5 and a["falhas7_entrada"] == 3
    assert a["equipamento_id"] == equipamento_id("IBI200-INVR1.3") and a["usina_id"] == 1
    assert [d["nome"] for d in A.diagnosticos(banco.linhas(A.LIVRO, A.ABA_DIAG))] == ["Comunicação", "Disjuntor"]
    ev = banco.linhas(A.LIVRO, A.ABA_EVENTO)
    assert len(ev) == 1 and list(ev[0]) == list(A.CAB_EVENTO)
    assert ev[0]["evento"] == "pegou" and ev[0]["pessoa_hmac"] == ev[0]["responsavel_hmac"] == A.codigo(ANA)
    # a API do banco tem leitura aberta: nem o nome nem o e-mail em claro
    claro = json.dumps(ev, ensure_ascii=False, default=str).lower()
    assert "ana lima" not in claro and ANA["email"] not in claro


def test_pegar_recusa_sem_poder_sem_login_e_ativo_ja_acompanhado(banco):
    with pytest.raises(A.Recusada, match="Engenharia"):
        A.pegar(ATIVO, ANA, pode=False)
    with pytest.raises(A.Recusada, match="login"):
        A.pegar(ATIVO, None, pode=True)
    A.pegar(ATIVO, ANA, pode=True)
    # o mesmo ativo escrito de outro jeito (caixa, espaço) é o mesmo ativo
    with pytest.raises(A.Recusada, match="já está com Ana Lima"):
        A.pegar(dict(ATIVO, cod=" ibi200-invr1.3"), BETO, pode=True)
    assert len(banco.linhas(A.LIVRO, A.ABA_EVENTO)) == 1


def test_leitura_como_texto_da_o_mesmo_estado(banco_texto):
    # Review Focus 1: a API devolveu tudo como texto ("5", "20261018", "1")
    A.pegar(ATIVO, ANA, pode=True)
    assert isinstance(banco_texto.linhas(A.LIVRO, A.ABA_EVENTO)[0]["falhas_30d_qtd"], str)
    a = _a()
    assert a["falhas30_entrada"] == 5 and a["falhas7_entrada"] == 3 and a["usina_id"] == 1
    assert a["inicio"] == datetime.now(BRT).date() and a["aberto"]
    assert a["equipamento_id"] == equipamento_id("IBI200-INVR1.3")
    assert [d["id"] for d in A.diagnosticos(banco_texto.linhas(A.LIVRO, A.ABA_DIAG))] == [1, 2]


def test_banco_fora_nao_grava_e_a_leitura_diz(banco, monkeypatch):
    # Review Focus 4: "não consegui ler" não é "nenhum", e sem ler o livro nada se grava (gravaria por cima)
    monkeypatch.setattr(banco, "get", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("fora")))
    lido = A.ler(forcar=True)
    assert lido["erro"] and lido["eventos"] == [] and lido["lido_em"] is None
    with pytest.raises(requests.ConnectionError):
        A.pegar(ATIVO, ANA, pode=True)
    assert banco.syncs == 0
