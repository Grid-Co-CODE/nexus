"""Modo TV do Painel NOC (11/10/2026), o lado do servidor.

Levi: "onde eu quiser que tenha TV já deixe um botão de TV, no caso só mapa e NOC mesmo! não precisa de conta fixa". O
Mapa de risco já tinha o modo TV (`?tv=1`, mapa_tv.html); o Painel NOC ganha o dele: o botão "Modo TV" na faixa da
moldura (no canto direito dela, a mesma classe e o mesmo texto do Mapa) leva a `/t/performance/noc?tv=1`, que
sai SEM a casca do Nexus (sem menu e sem topo), com a moldura na tela inteira e o mesmo porta.js: o passe, a renovação de
11 h e o "nexus:sessao-vencida" continuam valendo para a sessão da PLATAFORMA. A TV fica de pé enquanto valer a sessão do
NEXUS de quem a abriu, sem conta fixa: pelo Fracttal, ~12 h a partir do LOGIN (o `fracttal_exp`), e nada que a TV faz a
estica (revisão de 11/10/2026: login às 07:00 e TV às 18:30 = 30 minutos de TV). Aqui se prova:
- o botão só no Painel NOC (e o do Mapa continua lá), levando o caminho aberto;
- o `?tv=1` sem a casca, com a moldura, o formulário do passe, a rota de renovação, o "Sair do modo TV" e a "Tela cheia";
- o `?tv=1` numa tela sem TV é a tela de sempre (nada muda nas outras telas);
- o "Sair do modo TV" volta à tela normal;
- sem login, o Entrar volta para a TV; sem a chave, a TV avisa e não recarrega sozinha (nada de laço);
- o prazo da sessão de quem abriu a TV à vista (nos controles e no aviso do canto), e o token vencido levando a TV, o
  passe novo e a conferência de 5 min ao login, que volta à TV;
- tudo na raiz e debaixo do /nexus (o prefixo do servidor).
O que o porta.js faz no modo TV (o endereço, os controles que aparecem ao mexer o mouse) está em `tests/test_porta_js.py`.
"""
import html as _html
import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from nexus.performance import porta
from test_porta_moldura import PREFIXO, _app, _cliente, _dados, _form, _fracttal, _ler

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
    # sem a casca: nem topo, nem menu, nem o setor e a troca de tema da casca
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


# ── o prazo da sessão de quem abriu a TV (revisão de 11/10/2026) ─────────────────────────────────────────────────────
# A TV fica de pé enquanto valer a sessão do Nexus de quem a abriu. Pelo Fracttal, o portão confere o `fracttal_exp` (o
# `exp` do JWT, ~12 h depois do LOGIN) em todo pedido, e nem a conferência de 5 min nem o passe de 11 h renovam o token.
BRT = timezone(timedelta(hours=-3))


def _fracttal_com_prazo(monkeypatch, exp, prefixo=""):
    """O login pelo Fracttal (como o `_fracttal` de test_porta_moldura) com o `exp` do JWT dado."""
    from nexus.auth import fracttal
    monkeypatch.setattr(fracttal, "entrar", lambda app, e, s: {"email": e, "nome": "Pessoa Teste", "perfil": "", "exp": exp,
                                                                "cookie": ("os_sessao", "valor", 3600)})
    cli = _cliente(prefixo, logar=False)
    assert cli.post(prefixo + "/entrar", data={"email": "pessoa@exemplo.test", "senha": "x"}).status_code == 302
    return cli


def test_o_prazo_sai_no_relogio_de_brasilia_com_o_dia_quando_nao_e_hoje():
    from flask import session

    from nexus.torres import moldura
    vence = datetime(2026, 10, 11, 22, 0, tzinfo=timezone.utc).timestamp()          # 19:00 em Brasília
    with _app("").test_request_context():
        session["usuario"] = {"email": "pessoa@exemplo.test", "nome": "Pessoa Teste", "perfil": ""}
        session["fracttal_exp"] = vence
        assert moldura._prazo_da_tv(datetime(2026, 10, 11, 8, 0, tzinfo=BRT)) == {
            "nome": "Pessoa Teste", "ate": "19:00", "quando": "às 19:00", "vence": int(vence)}
        # login às 20:00: o token vence às 08:00 do dia seguinte, e o dia vai na frente
        session["fracttal_exp"] = vence + 13 * 3600
        p = moldura._prazo_da_tv(datetime(2026, 10, 11, 20, 0, tzinfo=BRT))
        assert (p["ate"], p["quando"]) == ("12/10 às 08:00", "em 12/10 às 08:00")
        # sem nome no Fracttal, não sai o e-mail (a TV fica numa sala com gente passando)
        session["usuario"] = {"email": "pessoa@exemplo.test", "nome": "", "perfil": ""}
        assert moldura._prazo_da_tv()["nome"] == "quem entrou"
        # o login põe o e-mail no nome quando o Fracttal não devolve o nome: também não sai (prova de 11/10/2026)
        session["usuario"] = {"email": "pessoa@exemplo.test", "nome": "pessoa@exemplo.test", "perfil": ""}
        assert moldura._prazo_da_tv()["nome"] == "quem entrou"
        # a sessão de antes do fracttal_exp e a senha de administrador: sem prazo conhecido
        session.pop("fracttal_exp")
        assert moldura._prazo_da_tv() is None
        session["fracttal_exp"] = vence
        session.pop("usuario")
        assert moldura._prazo_da_tv() is None


@pytest.mark.parametrize("prefixo", ["", PREFIXO])
def test_a_tv_mostra_ate_quando_vale_a_sessao_de_quem_a_abriu(monkeypatch, prefixo):
    exp = time.time() + 2 * 3600
    cli = _fracttal_com_prazo(monkeypatch, exp, prefixo)
    h = cli.get(prefixo + NOC, query_string={"tv": "1"}).get_data(as_text=True)
    d = datetime.fromtimestamp(exp, BRT)
    hoje = d.date() == datetime.now(BRT).date()
    ate = d.strftime("%H:%M") if hoje else d.strftime("%d/%m às %H:%M")
    quando = ("às " if hoje else "em ") + ate
    # nos controles (aparecem ao abrir e ao mexer o mouse) e, na última meia hora, no aviso fixo do canto (o porta.js o
    # mostra pelo sessao_vence: tests/test_porta_js.py)
    assert (f'<p class="porta-tv-prazo" id="porta-tv-prazo">Sessão de Pessoa Teste até {ate}; depois, a TV pede '
            "login</p>") in h
    assert (f'<p class="porta-tv-vence" id="porta-tv-vence" role="status" hidden>A sessão de Pessoa Teste vence {quando}: '
            "depois disso, a TV vai pedir login.</p>") in h
    assert _dados(h)["sessao_vence"] == int(exp)
    assert "pessoa@exemplo.test" not in h                      # o nome, não o e-mail
    # fora da TV, a tela de sempre não ganha nada disso
    h = cli.get(prefixo + NOC).get_data(as_text=True)
    assert "porta-tv-prazo" not in h and "porta-tv-vence" not in h and _dados(h)["sessao_vence"] == 0


def test_a_tv_da_senha_de_administrador_nao_tem_prazo():
    """A senha de administrador não depende do Fracttal (só o Sair a encerra): nada de prazo nem de aviso."""
    h = _cliente().get(NOC, query_string={"tv": "1"}).get_data(as_text=True)
    assert "porta-tv-prazo" not in h and "porta-tv-vence" not in h and _dados(h)["sessao_vence"] == 0


@pytest.mark.parametrize("prefixo", ["", PREFIXO])
def test_com_o_token_do_fracttal_vencido_a_tv_vai_ao_login_e_volta_para_ela(monkeypatch, prefixo):
    """O fim da TV: com o fracttal_exp vencido, o F5 da TV vai ao Entrar dizendo que a sessão venceu, e o login volta à
    TV. É o que a TV aberta faz sozinha: o passe novo (sessão da plataforma vencida, renovação de 11 h) e a conferência de
    5 min recebem o 401 com o endereço do Entrar, e o porta.js e o _confere_sessao_js.html levam a janela até ele."""
    r = _fracttal_com_prazo(monkeypatch, time.time() - 60, prefixo).get(prefixo + NOC, query_string={"tv": "1"})
    assert r.status_code == 302
    loc = r.headers["Location"]
    assert loc.startswith(f"{prefixo}/entrar?") and "motivo=venceu" in loc and "tv%3D1" in loc, loc
    dados = {"Sec-Fetch-Dest": "empty", "Sec-Fetch-Site": "same-origin"}       # o fetch do navegador
    for pedido in (lambda c: c.post(prefixo + NOC + "/passe", data={"p": "/painel"}, headers=dados),
                   lambda c: c.get(prefixo + "/os/_nexus/sessao", headers=dados)):
        r = pedido(_fracttal_com_prazo(monkeypatch, time.time() - 60, prefixo))
        j = r.get_json()
        assert r.status_code == 401 and j["sessao_encerrada"] is True, (r.status_code, j)
        assert j["entrar"].startswith(f"{prefixo}/entrar?") and "motivo=venceu" in j["entrar"]


# o Mapa de risco precisa do mundo de mentira dele (cadastro e leituras prontas, sem rede)
from test_torre_performance_mapa import pagina  # noqa: E402
from test_torre_performance_mapa_tv import leituras, mundo  # noqa: E402,F401
