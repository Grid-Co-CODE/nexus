"""O Início honesto (auditoria A3 da porta única, 10/10/2026).

O Início é a primeira página de todos, e na segunda-feira em que o Nexus vira a porta principal ele dizia "Esta é a fase
0" e "Com dado real: 0", com 40 telas prontas no ar. E cada cartão abria a 1ª tela da torre, que em Comando, COS,
Contratos e Relatórios é "Em construção". Agora o número é o das telas prontas, pela mesma conta do verde do menu
(`telas_com_conteudo`), o cartão leva à 1ª tela PRONTA da torre e a torre sem nenhuma diz "Em construção", sem link.
"""
import re

import pytest

from nexus import create_app
from nexus.torres import telas_com_conteudo

from conftest import SENHA_TESTE


def _cliente(**extra):
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE, **extra})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    cli = app.test_client()
    assert cli.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return app, cli


def _cartoes(html: str) -> dict:
    """{torre: (tag do cartão, href ou None, texto do cartão)} pelos cartões do Início."""
    saida = {}
    for m in re.finditer(r'<(a|div) class="card-torre[^"]*" data-torre="([^"]+)"([^>]*)>(.*?)</\1>', html, re.S):
        href = re.search(r'href="([^"]*)"', m.group(3))
        saida[m.group(2)] = (m.group(1), href.group(1) if href else None, m.group(4))
    return saida


@pytest.mark.parametrize("extra", [{}, {"NEXUS_SSO_CHAVE": "c" * 40}], ids=["sem-porta", "com-porta"])
def test_o_inicio_conta_as_telas_prontas_e_nao_fala_em_fase_0(extra):
    app, cli = _cliente(**extra)
    html = cli.get("/").get_data(as_text=True)
    assert "fase 0" not in html.lower() and "Com dado real" not in html
    prontas = telas_com_conteudo(app)
    total = sum(len(t.telas) for t in app.extensions["nexus_torres"])
    m = re.search(r'<div class="r">Telas prontas</div><div class="v gc-num">(\d+)</div>', html)
    assert m and int(m.group(1)) == len(prontas) > 0
    assert re.search(rf'<div class="r">Telas previstas</div><div class="v gc-num">{total}</div>', html)


@pytest.mark.parametrize("extra", [{}, {"NEXUS_SSO_CHAVE": "c" * 40}], ids=["sem-porta", "com-porta"])
def test_cada_cartao_leva_a_primeira_tela_pronta_ou_diz_em_construcao(extra):
    app, cli = _cliente(**extra)
    cartoes = _cartoes(cli.get("/").get_data(as_text=True))
    prontas = telas_com_conteudo(app)
    torres = app.extensions["nexus_torres"]
    assert set(cartoes) == {t.id for t in torres}
    for t in torres:
        tag, href, texto = cartoes[t.id]
        primeira = next((f"/t/{t.id}/{s.id}" for s in t.telas if f"/t/{t.id}/{s.id}" in prontas), None)
        if primeira:
            assert (tag, href) == ("a", primeira), t.id
            assert cli.get(href).status_code == 200 and "Em construção" not in cli.get(href).get_data(as_text=True)
        else:
            # sem link enganoso: o cartão não é link e diz por quê
            assert tag == "div" and href is None and "Em construção" in texto, t.id


def test_o_cos_com_a_porta_leva_ao_acompanhamento_e_nao_a_mesa_em_construcao():
    """O caso que criou a regra: o 1º item do COS (Mesa) é "Em construção"; o Acompanhamento COS (a moldura da
    Performance) é o que está pronto com a porta ligada. Comando, Contratos e Relatórios não têm nenhuma pronta."""
    _app, cli = _cliente(NEXUS_SSO_CHAVE="c" * 40)
    cartoes = _cartoes(cli.get("/").get_data(as_text=True))
    assert cartoes["cos"][1] == "/t/cos/acompanhamento"
    for vazia in ("comando", "contratos", "relatorios"):
        assert cartoes[vazia][0] == "div" and "Em construção" in cartoes[vazia][2]


def test_debaixo_do_prefixo_o_cartao_sai_com_ele():
    from werkzeug.test import Client
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE, "NEXUS_PREFIXO": "/nexus"})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    cli = Client(app)
    assert cli.post("/nexus/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    cartoes = _cartoes(cli.get("/nexus/").get_data(as_text=True))
    assert cartoes["pcm"][1] == "/nexus/t/pcm/semana"
