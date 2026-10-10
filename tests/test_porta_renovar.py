"""A moldura renova a sessão da plataforma (auditoria A5 da porta única, 10/10/2026), o lado Nexus.

O caso: a sessão que o passe abre na plataforma vale 12 h fixas (`SESSAO_DO_PASSE_S`), sem renovação. Depois disso o
`/api/macro` do Painel NOC dava 401, e o painel, que relê a cada 60 s, desenhava o erro como "Energia perdida 0,0 MWh":
número falso numa tela de NOC ou de TV. O protocolo combinado entre os dois lados:
- a página da plataforma em modo Nexus, ao receber 401 numa chamada de dado, avisa a moldura:
  `postMessage({tipo: "nexus:sessao-vencida", caminho: location.pathname + location.search}, <origem do Nexus>)`;
- a moldura (porta.js) confere a fonte e a origem como no "nexus:rota", pede um passe NOVO ao Nexus
  (`POST <tela>/passe`, aqui) e reabre a mesma tela, no máximo 1 vez a cada 60 s (sem laço);
- e renova sozinha antes de vencer: a cada 11 h com a aba aberta, um passe novo abre outra sessão de 12 h, sem recarregar
  a tela.
Aqui, a rota que emite o passe novo; o porta.js, em `tests/test_porta_js.py`.
"""
import pytest

from nexus.performance import porta
from test_porta_moldura import PREFIXO, _cliente, _dados, _fracttal, _ler


def _renovar(cli, url, p, **cab):
    return cli.post(url, data={"p": p} if p is not None else {}, headers=cab)


@pytest.mark.parametrize("prefixo", ["", PREFIXO])
def test_a_pagina_diz_onde_pedir_o_passe_novo(prefixo):
    cli = _cliente(prefixo)
    for t in porta.MAPA:
        dados = _dados(cli.get(f"{prefixo}/t/{t.torre}/{t.tela}").get_data(as_text=True))
        assert dados["renovar"] == f"{prefixo}/t/{t.torre}/{t.tela}/passe", t


@pytest.mark.parametrize("prefixo", ["", PREFIXO])
def test_o_passe_novo_e_do_caminho_pedido_e_de_quem_esta_logado(prefixo, monkeypatch):
    cli = _fracttal(monkeypatch, prefixo=prefixo)
    r = _renovar(cli, f"{prefixo}/t/performance/noc/passe", "/painel")
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    j = r.get_json()
    p = _ler(j["passe"])
    assert (j["destino"], p["destino"], p["email"], p["admin"]) == ("/painel", "/painel", "pessoa@exemplo.test", False)
    # a moldura pode ter ido a outra tela do mapa (do Painel NOC ao diagnóstico de uma usina): o passe é do caminho dela
    destino = "/painel/usina/297410?fonte=pv&nome=Usina%20Teste"
    assert _ler(_renovar(cli, f"{prefixo}/t/performance/noc/passe", destino).get_json()["passe"])["destino"] == destino
    # cada pedido, um passe novo (60 s, uso único)
    a, b = (_ler(_renovar(cli, f"{prefixo}/t/performance/noc/passe", "/painel").get_json()["passe"]) for _ in range(2))
    assert a["numero"] != b["numero"]


@pytest.mark.parametrize("ruim", [None, "", "//evil.example/x", "https://evil.example/painel", "/login", "/os/",
                                  "/painel/nexus/entrar", "/api/macro", "/gemeo/%2e%2e/tokens", "/painel x"])
def test_caminho_fora_do_mapa_nao_ganha_passe(ruim):
    r = _renovar(_cliente(), "/t/performance/noc/passe", ruim)
    assert r.status_code == 400 and "passe" not in r.get_json()


def test_chaves_das_fontes_so_para_admin(monkeypatch):
    cli = _fracttal(monkeypatch)
    assert _renovar(cli, "/t/base/chaves-fontes/passe", "/tokens").status_code == 403
    # nem pela rota de outra tela
    r = _renovar(cli, "/t/performance/noc/passe", "/tokens")
    assert r.status_code == 403 and "passe" not in r.get_json()
    adm = _fracttal(monkeypatch, admins="pessoa@exemplo.test")
    assert _ler(_renovar(adm, "/t/base/chaves-fontes/passe", "/tokens").get_json()["passe"])["admin"] is True


@pytest.mark.parametrize("prefixo", ["", PREFIXO])
def test_sem_login_nao_ha_passe(prefixo):
    r = _renovar(_cliente(prefixo, logar=False), f"{prefixo}/t/performance/noc/passe", "/painel")
    # o fetch da moldura vê o redirecionamento ao Entrar (opaqueredirect) e leva a janela ao login
    assert r.status_code == 302 and r.headers["Location"].startswith(f"{prefixo}/entrar")


def test_com_o_fracttal_vencido_o_nexus_responde_401_e_diz_onde_entrar(monkeypatch):
    """A sessão do Nexus acabou junto com a do Fracttal: o porta.js leva a janela ao login (`nexusEntrarDeNovo`)."""
    from nexus.auth import fracttal
    monkeypatch.setattr(fracttal, "entrar", lambda app, e, s: {"email": e, "nome": "Pessoa Teste", "perfil": "",
                                                                  "exp": 1.0, "cookie": ("os_sessao", "valor", 3600)})
    cli = _cliente(logar=False)
    assert cli.post("/entrar", data={"email": "pessoa@exemplo.test", "senha": "x"}).status_code == 302
    r = cli.post("/t/performance/noc/passe", data={"p": "/painel"}, headers={"Sec-Fetch-Dest": "empty"})
    assert r.status_code == 401
    j = r.get_json()
    assert j["sessao_encerrada"] is True and j["entrar"].startswith("/entrar") and "passe" not in j


def test_sem_a_chave_nao_ha_passe():
    r = _renovar(_cliente(NEXUS_SSO_CHAVE=None), "/t/performance/noc/passe", "/painel")
    assert r.status_code == 404 and "passe" not in r.get_json()


def test_pedido_de_outro_site_nao_ganha_passe():
    cli = _cliente()
    for cab in ({"Sec-Fetch-Site": "cross-site"}, {"Sec-Fetch-Site": "same-site"},
                {"Origin": "https://mal.exemplo.test"}, {"Origin": "null"}):
        r = _renovar(cli, "/t/performance/noc/passe", "/painel", **cab)
        assert r.status_code == 403 and "passe" not in r.get_json(), cab
    # da própria página (o fetch do porta.js): passa
    assert _renovar(cli, "/t/performance/noc/passe", "/painel", **{"Sec-Fetch-Site": "same-origin"}).status_code == 200
    assert _renovar(cli, "/t/performance/noc/passe", "/painel", Origin="http://localhost").status_code == 200


def test_so_por_post():
    assert _cliente().get("/t/performance/noc/passe?p=/painel").status_code == 405
