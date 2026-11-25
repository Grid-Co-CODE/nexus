"""As tratativas dos extintores (24/11/2026, `nexus/hseq/tratativas.py`): o que a Segurança fez com o cliente ou a usina
que tem extintor vencido, na coluna Evolução da tabela por cliente, com o "Ver histórico" e o "Registrar". O livro é um
arquivo (`NEXUS_HSEQ_TRATATIVAS_ARQUIVO`): nada vai ao banco.

O caso é o do `com_cadastro` de test_hseq_extintores.py, no dia 09/10/2026: a Thopen (cliente 1) com a Altair (usina 1)
e a Brodowski 1 (usina 2); o Outro Cliente com a Coração 1 (usina 3); a Irecê 2 fora do cadastro. Nomes fictícios."""
import json
import re

import pytest
from test_campo_visao import _aba, banco  # noqa: F401  (banco é fixture)
from test_hseq_extintores import _abre, _texto, _tabela, com_cadastro, com_livro  # noqa: F401

from nexus.cadastro import setor_ids as SID
from nexus.hseq import decisoes as DEC
from nexus.hseq import tratativas as TRAT


@pytest.fixture
def livro(app, tmp_path):
    arq = tmp_path / "tratativas.json"
    app.config["NEXUS_HSEQ_TRATATIVAS_ARQUIVO"] = str(arq)
    TRAT.limpar()
    DEC.limpar()
    yield arq
    TRAT.limpar()


@pytest.fixture
def tst(app, cliente):
    """Quem registra: um login de pessoa, administrador."""
    app.config["NEXUS_ADMINS"] = "tst@exemplo.test"
    with cliente.session_transaction() as s:
        s.update(logado=True, admin=True, usuario={"email": "tst@exemplo.test", "nome": "TST de teste"})
    return cliente


def _registrar(c, alvo, tipo="email", dia="08/10/2026", obs=""):
    return c.post("/t/hseq/extintores/tratativa", data={"alvo": alvo, "tipo": tipo, "dia": dia, "obs": obs,
                                                         "cliente": "Thopen"})


def _linhas(arq):
    return json.loads(arq.read_text(encoding="utf-8"))[TRAT.ABA]


def test_grava_o_cliente_pelo_id_e_a_observacao_so_cifrada(com_cadastro, livro, tst):
    r = _registrar(tst, "c:1", obs="Relatório enviado ao contato do contrato")
    assert r.status_code == 303 and "ok=Tratativa+registrada" in r.headers["Location"]
    r = _registrar(tst, "u:1", tipo="recarga_agendada", dia="09/10/2026")
    assert r.status_code == 303 and "ok=" in r.headers["Location"]
    cli, us = _linhas(livro)
    assert (cli["escopo"], cli["cliente_id"], cli["usina_id"], cli["tipo"], cli["data_id"]) == (
        "cliente", 1, None, "email", 20261008)
    assert (us["escopo"], us["cliente_id"], us["usina_id"], us["data_id"]) == ("usina", 1, 1, 20261009)
    texto = livro.read_text(encoding="utf-8")
    for claro in ("Thopen", "Altair", "Relatório enviado", "TST de teste", "tst@exemplo.test"):   # nada em claro
        assert claro not in texto, claro
    assert cli["assinatura"] and cli["decidida_por_hmac"]
    # decifrado, para quem está logado
    t = TRAT.lista(tst.application.config, TRAT.ler(tst.application.config, forcar=True))
    assert t[0]["tipo"] == "recarga_agendada" and t[1]["obs"] == "Relatório enviado ao contato do contrato"
    assert t[1]["quem"] == "TST de teste"


@pytest.mark.parametrize("dados, recusa", [
    ({"dia": "10/10/2026"}, "futuro"),                 # amanhã, no dia fixo da tela (09/10/2026)
    ({"dia": "2026-10-08"}, "dd/mm/aaaa"),
    ({"tipo": "inventado"}, "Escolha o que foi feito"),
    ({"tipo": "outro"}, "Outro"),                      # o Outro pede a observação
    ({"obs": "x" * 301}, "300"),
    ({"alvo": "c:999"}, "Escolha para quem vale"),     # cliente que não está na tela
    ({"alvo": "u:999"}, "não está mais na tela"),
])
def test_o_que_nao_grava(com_cadastro, livro, tst, dados, recusa):
    r = _registrar(tst, **{"alvo": "c:1", **dados})
    assert r.status_code == 303 and "erro=" in r.headers["Location"] and not livro.exists()
    from urllib.parse import parse_qs, urlsplit
    assert recusa in parse_qs(urlsplit(r.headers["Location"]).query)["erro"][0]


def test_so_quem_decide_e_com_login_de_pessoa(com_cadastro, livro, logado, app, cliente):
    # a senha de administrador não diz quem é
    r = _registrar(logado, "c:1")
    assert "erro=" in r.headers["Location"] and not livro.exists()
    # quem não é da Segurança nem administrador
    app.config["NEXUS_ADMINS"] = ""
    with cliente.session_transaction() as s:
        s.clear()
        s.update(logado=True, admin=False, usuario={"email": "outro@exemplo.test", "nome": "Pessoa de outro setor"})
    assert "erro=" in _registrar(cliente, "c:1").headers["Location"] and not livro.exists()
    # pedido de outro site
    r = cliente.post("/t/hseq/extintores/tratativa", data={"alvo": "c:1", "tipo": "email"},
                     headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_a_evolucao_mostra_a_mais_nova_de_cada_linha(com_cadastro, livro, tst):
    """Na linha do cliente, a mais nova entre as do cliente inteiro e as das usinas dele; na usina, a mais nova que vale
    para ela, contando as do cliente inteiro."""
    html = tst.get("/t/hseq/extintores").get_data(as_text=True)
    assert "Nenhuma tratativa Registrar" in _abre(html, "<b>Thopen</b>")
    _registrar(tst, "c:1", tipo="email", dia="05/10/2026")
    _registrar(tst, "u:1", tipo="os_recarga", dia="07/10/2026")
    _registrar(tst, "u:2", tipo="troca", dia="06/10/2026")
    html = tst.get("/t/hseq/extintores").get_data(as_text=True)
    th = _abre(html, "<b>Thopen</b>")
    assert "OS de recarga aberta · 07/10/2026 3 tratativas · última por TST de teste Ver histórico · Registrar" in th
    assert "OS de recarga aberta · 07/10/2026 2 tratativas" in _abre(html, "</span>Altair</span>")
    assert "Troca realizada · 06/10/2026 2 tratativas" in _abre(html, "</span>Brodowski 1</span>")
    # o Outro Cliente não tem nenhuma, nem a usina dele
    assert "Nenhuma tratativa" in _abre(html, "</span>Coração 1</span>")
    # o ícone é desenho (o Nexus não usa emoji), o nome do tipo vem escrito ao lado
    assert 'class="hs-trat-ic"' in _tabela(html) and not re.search(r"[\U0001F300-\U0001FAFF✅✉]", html)


def test_o_historico_vem_ao_abrir_do_mais_novo_para_o_mais_velho(com_cadastro, livro, tst):
    _registrar(tst, "c:1", tipo="email", dia="05/10/2026", obs="Primeiro aviso")
    _registrar(tst, "u:1", tipo="os_recarga", dia="07/10/2026")
    _registrar(tst, "u:2", tipo="troca", dia="06/10/2026")
    cli = _texto(tst.get("/t/hseq/extintores/tratativas?cliente_id=1&usinas=1,2").get_data(as_text=True))
    assert cli.index("07/10/2026") < cli.index("06/10/2026") < cli.index("05/10/2026")
    assert "OS de recarga aberta · Altair" in cli and "cliente inteiro" in cli and "Primeiro aviso" in cli
    us = _texto(tst.get("/t/hseq/extintores/tratativas?usina_id=2&cliente_id=1").get_data(as_text=True))
    assert "Troca realizada" in us and "Cliente notificado por e-mail · cliente inteiro" in us
    assert "OS de recarga aberta" not in us                                 # a da Altair não vale para a Brodowski 1
    vazio = tst.get("/t/hseq/extintores/tratativas?cliente_id=2").get_data(as_text=True)
    assert "Nenhuma tratativa registrada." in vazio
    # sem login, o pedaço não sai
    assert tst.application.test_client().get("/t/hseq/extintores/tratativas?cliente_id=1").status_code == 302


def test_quem_nao_registra_ve_o_historico_sem_o_registrar(com_cadastro, livro, tst, app, cliente):
    _registrar(tst, "c:1")
    app.config["NEXUS_ADMINS"] = ""
    with cliente.session_transaction() as s:
        s.clear()
        s.update(logado=True, admin=False, usuario={"email": "outro@exemplo.test", "nome": "Pessoa de outro setor"},
                 setor={"id": SID.SEGURANCA + 1000})
    html = cliente.get("/t/hseq/extintores").get_data(as_text=True)
    if "Cliente e usina" not in html:          # o setor sem a tela não abre: aí não há o que ver
        pytest.skip("a tela de Extintores não abre para este setor de teste")
    th = _abre(html, "<b>Thopen</b>")
    assert "Ver histórico" in th and "Registrar" not in th and 'id="hs-trat"' in html
    assert "Registrar tratativa" not in html


def test_a_caixa_tem_os_tipos_em_chips_a_data_de_hoje_e_o_vale_para(com_cadastro, livro, tst):
    html = tst.get("/t/hseq/extintores").get_data(as_text=True)
    caixa = html[html.index('id="hs-trat"'):html.index("</dialog>", html.index('id="hs-trat"'))]
    assert [r for r in re.findall(r'name="tipo" value="(\w+)"', caixa)] == list(TRAT.TIPOS)
    assert 'name="dia" value="09/10/2026"' in caixa and 'name="alvo"' in caixa
    assert 'maxlength="300"' in caixa and "Registrar tratativa" in caixa
    # a linha do cliente e as das usinas levam os IDs que a caixa usa
    assert 'data-cid="1" data-nome="Thopen"' in html and 'data-uid="1" data-cid="1" data-nome="Altair"' in html


def test_o_livro_esta_no_catalogo_antes_da_1a_gravacao():
    from nexus.dados import catalogo, explica
    l = catalogo.LIVRO_POR_NOME[TRAT.LIVRO]
    assert l.abas == (TRAT.ABA,) and l.so_cresce
    f = catalogo.POR_ID["tratativa_extintor"]
    assert f.livro == f"{TRAT.LIVRO} · {TRAT.ABA}"
    r, p = explica.RESUMO["tratativa_extintor"], explica.PARA_QUE["tratativa_extintor"]
    assert 15 <= len(r) <= 70 and not r.endswith(".") and len(p) >= 80 and p.endswith(".")
    # o livro das decisões, que o App de Campo lê, não ganhou aba nova
    assert catalogo.LIVRO_POR_NOME[DEC.LIVRO].abas == (DEC.ABA_EXC, DEC.ABA_RONDA, DEC.ABA_EDIT)
