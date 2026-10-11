"""Modo TV do Painel NOC (11/10/2026), o lado do servidor.

Levi: "onde eu quiser que tenha TV já deixe um botão de TV, no caso só mapa e NOC mesmo! não precisa de conta fixa". O
Mapa de risco já tinha o modo TV (`?tv=1`, mapa_tv.html); o Painel NOC ganha o dele: o botão "Modo TV" na faixa da
moldura (no canto direito dela, a mesma classe e o mesmo texto do Mapa) leva a `/t/performance/noc?tv=1`, que
sai SEM a casca do Nexus (sem menu e sem topo), com a moldura na tela inteira e o mesmo porta.js: o passe, a renovação de
11 h e o "nexus:sessao-vencida" continuam valendo, e é isso que deixa a TV ligada o dia todo sem uma conta fixa. Aqui se
prova:
- o botão só no Painel NOC (e o do Mapa continua lá), levando o caminho aberto;
- o `?tv=1` sem a casca, com a moldura, o formulário do passe, a rota de renovação, o "Sair do modo TV" e a "Tela cheia";
- o `?tv=1` numa tela sem TV é a tela de sempre (nada muda nas outras telas);
- o "Sair do modo TV" volta à tela normal;
- sem login, o Entrar volta para a TV; sem a chave, a TV avisa e não recarrega sozinha (nada de laço);
- tudo na raiz e debaixo do /nexus (o prefixo do servidor).
O que o porta.js faz no modo TV (o endereço, os controles que aparecem ao mexer o mouse) está em `tests/test_porta_js.py`.
"""
import html as _html
import json
import re
from pathlib import Path

import pytest

from nexus.performance import porta
from test_porta_moldura import PREFIXO, _cliente, _dados, _form, _fracttal, _ler

NOC = "/t/performance/noc"
CSS = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "nexus.css").read_text(encoding="utf-8")
TELAS_SEM_TV = [t for t in porta.MAPA if (t.torre, t.tela) != ("performance", "noc")]


def _botao_tv(h: str) -> str | None:
    """O href do botão "Modo TV" da faixa da moldura, ou None."""
    m = re.search(r'<a class="gc-btn gc-btn--contorno" id="porta-tv" href="([^"]*)">Modo TV</a>', h)
    return _html.unescape(m.group(1)) if m else None


def _sair_tv(h: str) -> str | None:
    m = re.search(r'<a class="gc-btn gc-btn--contorno" id="porta-sair-tv" href="([^"]*)">Sair do modo TV</a>', h)
    return _html.unescape(m.group(1)) if m else None


# ── o botão ──────────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("prefixo", ["", PREFIXO])
def test_o_botao_modo_tv_so_no_painel_noc(prefixo):
    cli = _cliente(prefixo)
    h = cli.get(prefixo + NOC).get_data(as_text=True)
    assert _botao_tv(h) == f"{prefixo}{NOC}?tv=1"
    # o último item da faixa, sem o "Abrir em outra aba" (saiu em 11/10/2026: "é só Nexus e já era!"), e no canto
    # direito dela como o do Mapa: quem o empurrava para lá era o margin-left:auto do .porta-fora, que saiu junto; sem a
    # regra própria do botão (nexus.css), ele colava em "Painel NOC · Plataforma de Performance"
    faixa = h.split('<div class="porta-faixa">', 1)[1].split("</div>", 1)[0]
    assert "Abrir em outra aba" not in faixa and "porta-fora" not in faixa
    assert faixa.rstrip().endswith('id="porta-tv" href="' + f"{prefixo}{NOC}?tv=1" + '">Modo TV</a>')
    assert ".porta-faixa #porta-tv{margin-left:auto}" in CSS
    # o porta.js sabe que tela tem TV (o botão some quando a moldura sai do Painel NOC e volta quando ela volta)
    assert [x["url"] for x in _dados(h)["telas"] if x.get("tv")] == [f"{prefixo}{NOC}"]
    assert _dados(h).get("tv") is False
    for t in TELAS_SEM_TV:
        h = cli.get(f"{prefixo}/t/{t.torre}/{t.tela}").get_data(as_text=True)
        assert "Modo TV" not in h and 'id="porta-tv"' not in h, t


def test_o_botao_leva_o_caminho_que_a_moldura_abriu():
    """O favorito ?p= do Painel NOC (um filtro, por exemplo) vai junto para a TV, como o Mapa leva o estado dele."""
    h = _cliente().get(NOC, query_string={"p": "/painel?cliente=X"}).get_data(as_text=True)
    assert _botao_tv(h) == f"{NOC}?tv=1&p=%2Fpainel%3Fcliente%3DX"


def test_sem_a_chave_nao_ha_botao():
    h = _cliente(NEXUS_SSO_CHAVE=None).get(NOC).get_data(as_text=True)
    assert "Performance ainda não ligada neste servidor" in h and _botao_tv(h) is None


def test_o_mapa_de_risco_continua_com_o_modo_tv_dele(mundo):
    """O Mapa já tinha o botão (mapa.html, `data-acao="tv"`): nada muda nele."""
    h = pagina(mundo)
    assert re.search(r'<a class="gc-btn gc-btn--contorno" data-acao="tv" href="/t/performance/clima/mapa\?[^"]*tv=1[^"]*">'
                     r'Modo TV</a>', h)


# ── o ?tv=1 ──────────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("prefixo", ["", PREFIXO])
def test_o_modo_tv_sai_sem_a_casca_e_com_a_moldura(prefixo):
    r = _cliente(prefixo).get(prefixo + NOC, query_string={"tv": "1"})
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    h = r.get_data(as_text=True)
    # sem a casca: nem topo, nem menu, nem a troca de cadeira e tema da casca
    assert '<header class="topo">' not in h and 'class="menu"' not in h and 'name="voltar"' not in h
    assert re.search(r'<html lang="pt-BR" class="porta-tv-html" data-nexus data-tema="escuro">', h)
    assert "window.top !== window.self" in h                     # o Nexus nunca fica dentro de moldura
    # a moldura e o mesmo formulário do passe (POST, alvo na moldura), com o destino padrão do Painel NOC
    assert '<iframe class="porta-moldura" id="porta-moldura" name="porta-moldura"' in h
    form = _form(h)
    assert (form["action"], form["target"], form["method"]) == ("/painel/nexus/entrar", "porta-moldura", "post")
    assert _ler(form["passe"])["destino"] == "/painel"
    # o mesmo porta.js, com a rota do passe novo (renovação de 11 h e sessão vencida) e a marca de TV
    dados = _dados(h)
    assert dados["tv"] is True and dados["renovar"] == f"{prefixo}{NOC}/passe" and dados["url"] == f"{prefixo}{NOC}"
    assert f'src="{prefixo}/static/porta.js"' in h and "window.nexusEntrarDeNovo = function" in h
    assert f"window.NEXUS_RAIZ = {json.dumps(prefixo)};" in h
    # os controles: Tela cheia (o porta.js a mostra quando o navegador permite) e Sair do modo TV
    assert '<button type="button" class="gc-btn gc-btn--contorno" data-acao="tela-cheia" aria-pressed="false" hidden>' \
           'Tela cheia</button>' in h
    assert _sair_tv(h) == f"{prefixo}{NOC}"
    assert 'id="porta-tv-controles"' in h and _botao_tv(h) is None
    # a TV não se recarrega sozinha: quem reabre é o porta.js, no máximo 1 vez a cada 60 s
    assert 'http-equiv="refresh"' not in h


def test_o_modo_tv_leva_o_caminho_pedido_e_o_sair_volta_a_ele():
    cli = _cliente()
    h = cli.get(NOC, query_string={"tv": "1", "p": "/painel?cliente=X"}).get_data(as_text=True)
    assert _ler(_form(h)["passe"])["destino"] == "/painel?cliente=X"
    assert _sair_tv(h) == f"{NOC}?p=%2Fpainel%3Fcliente%3DX"


@pytest.mark.parametrize("prefixo", ["", PREFIXO])
def test_o_sair_do_modo_tv_volta_a_tela_normal(prefixo):
    cli = _cliente(prefixo)
    sair = _sair_tv(cli.get(prefixo + NOC, query_string={"tv": "1"}).get_data(as_text=True))
    h = cli.get(sair).get_data(as_text=True)
    assert '<header class="topo">' in h and 'class="menu"' in h
    assert f'href="{prefixo}{NOC}" class="com-conteudo" aria-current="page"' in h
    assert _botao_tv(h) == f"{prefixo}{NOC}?tv=1" and _sair_tv(h) is None


@pytest.mark.parametrize("t", TELAS_SEM_TV, ids=lambda t: f"{t.torre}-{t.tela}")
def test_tv_numa_tela_sem_tv_e_a_tela_de_sempre(t):
    """Só o Painel NOC tem TV: nas outras, o ?tv=1 é ignorado (nada muda no comportamento delas)."""
    cli = _cliente()
    com = cli.get(f"/t/{t.torre}/{t.tela}", query_string={"tv": "1"})
    assert com.status_code == 200
    h = com.get_data(as_text=True)
    assert '<header class="topo">' in h and "porta-tv-html" not in h and _sair_tv(h) is None
    assert _dados(h).get("tv") is False


@pytest.mark.parametrize("prefixo", ["", PREFIXO])
def test_o_modo_tv_sem_login_vai_ao_entrar_e_volta_para_a_tv(prefixo):
    r = _cliente(prefixo, logar=False).get(prefixo + NOC, query_string={"tv": "1"})
    assert r.status_code == 302 and r.headers["Location"].startswith(f"{prefixo}/entrar?next=")
    assert "tv%3D1" in r.headers["Location"]


def test_o_modo_tv_confere_a_sessao_do_fracttal_como_a_casca(monkeypatch):
    """Sair do Fracttal = sair do Nexus (10/10/2026): a TV aberta por quem entrou pelo Fracttal pergunta a cada 5 minutos,
    como toda página da casca, e vai ao login quando a sessão acabou (a TV não fica mostrando o NOC de quem saiu)."""
    h = _fracttal(monkeypatch).get(NOC, query_string={"tv": "1"}).get_data(as_text=True)
    assert "porta-tv-html" in h and 'nexusRota("/os/_nexus/sessao")' in h
    # depois do nexusRota e do nexusEntrarDeNovo, que ela usa
    assert h.index("window.nexusRota = function") < h.index("function confereSessao")
    assert h.index("window.nexusEntrarDeNovo = function") < h.index("function confereSessao")
    # a senha de administrador não tem Fracttal para conferir (o mesmo da casca)
    assert "/os/_nexus/sessao" not in _cliente().get(NOC, query_string={"tv": "1"}).get_data(as_text=True)


def test_o_modo_tv_sem_a_chave_avisa_e_nao_recarrega():
    h = _cliente(NEXUS_SSO_CHAVE=None).get(NOC, query_string={"tv": "1"}).get_data(as_text=True)
    assert "porta-tv-html" in h and "Performance ainda não ligada neste servidor" in h
    assert _form(h) is None and "porta-dados" not in h and 'http-equiv="refresh"' not in h
    assert _sair_tv(h) == NOC


def test_o_modo_tv_segue_o_tema():
    cli = _cliente()
    cli.set_cookie("nexus_tema", "claro")
    assert 'class="porta-tv-html" data-nexus data-tema="claro"' in cli.get(NOC, query_string={"tv": "1"}).get_data(
        as_text=True)


def test_o_p_de_outro_item_sai_da_tv_para_o_item_dono():
    """O Diagnóstico de uma usina não tem TV: o favorito vai ao item dono, na tela de sempre."""
    r = _cliente().get(NOC, query_string={"tv": "1", "p": "/painel/falhas"})
    assert r.status_code == 302 and r.headers["Location"] == "/t/performance/strings-trackers?p=%2Fpainel%2Ffalhas"


# o Mapa de risco precisa do mundo de mentira dele (cadastro e leituras prontas, sem rede)
from test_torre_performance_mapa import pagina  # noqa: E402
from test_torre_performance_mapa_tv import leituras, mundo  # noqa: E402,F401
