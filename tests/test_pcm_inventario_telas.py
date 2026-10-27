"""A aba Inventário do PCM (26/10/2026, Levi): a lista das contagens que o técnico enviou pelo App, a contagem aberta com o
Sistema (o saldo do Fracttal lido na hora) × Contado × Δ × Situação, os seis grupos da confirmação e a revisão (tirar uma peça
do lote, corrigir o número, pedir a recontagem), que só o setor PCM faz. Desenho:
docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md (seção 4.2). O banco é o falso do Campo, o livro do
inventário é um arquivo local e o Fracttal é o `EstoqueFalso`: nada vai à rede. Dado de mentira, sem nome de gente."""
import re
import time
from pathlib import Path

import pytest
from estoque_falso import EstoqueFalso
from test_campo_visao import CHAVE, _aba, banco  # noqa: F401  (banco é fixture)
from test_pcm_almoxarifado import _semear as _semear_almox
from test_pcm_inventario_leitura import _gravar, _iso, _linha, _publicar, inv  # noqa: F401  (inv é fixture)
from test_pcm_publicar import _no_setor
from test_setor_telas import ANA, _como, setores  # noqa: F401  (setores é fixture)

from nexus.campo import visao
from nexus.campo.ligacao_cadastro import codigo_da_pessoa
from nexus.dados import almoxarifado as A
from nexus.dados import fato_inventario as F
from nexus.pcm.inventario import estoque as E
from nexus.pcm.inventario import leitura as L

LISTA = "/t/pcm/pecas/inventario"
RAIZ = Path(__file__).resolve().parent.parent
EMAIL = "supervisora@exemplo.test"            # a ficha 92 do cadastro do `banco`: o pessoa_id sai do e-mail pelo HMAC


def _cenario(api):
    """Uma contagem (C-1) no almoxarifado 10 (a Altair), com uma peça de cada situação:
    501 sobe (10 → 12), 502 desce (5 → 3), 503 zera (4 → 0), 504 igual (7), 505 em branco, 506 com contado negativo,
    507 genérico por identificar, um achado fora do catálogo, 508 nunca ligada ao almoxarifado (→ 3) e 509 ligada com o
    saldo vazio no Fracttal (→ 2)."""
    _publicar(api,
              _linha("C-1", "L1", "501", "12"), _linha("C-1", "L2", "502", "3"), _linha("C-1", "L3", "503", "0"),
              _linha("C-1", "L4", "504", "7"), _linha("C-1", "L5", "505", ""), _linha("C-1", "L6", "506", "-2"),
              _linha("C-1", "L7", "507", "4", tipo="identificar", **{"Identificado como": "501"}),
              _linha("C-1", "L8", "", "2", tipo="fora_do_catalogo", Descrição="peça sem etiqueta, caixa azul"),
              _linha("C-1", "L9", "508", "3"), _linha("C-1", "L10", "509", "2"))
    itens = [{"ID do item": str(i), "Código": f"SP-{i}", "Nome": nome, "Unidade": un, "Família": "Teste", "Avariado": "Não",
              "Ferramenta": "Não", "Início do ciclo": "x", "Lido": "Sim"}
             for i, nome, un in ((501, "Fusível 10A", "UNIDADE"), (502, "Cabo 6 mm", "METRO"), (503, "Relé", "UNIDADE"),
                                 (504, "Disjuntor", "UNIDADE"), (505, "Terminal", "UNIDADE"), (506, "Conector", "UNIDADE"),
                                 (507, "Genérico de proteção", "UNIDADE"), (508, "Chave seccionadora", "UNIDADE"),
                                 (509, "Sensor", "UNIDADE"))]
    _aba(api, A.LIVRO_ITENS, A.ABA_ITENS, itens)
    _aba(api, A.LIVRO_SALDO, A.ABA_SALDO, [{"ID do item": "501", "Código": "SP-501", "ID do almoxarifado": "10",
                                            "Almoxarifado": "Almoxarifado Altair", "Início do ciclo": "x",
                                            "Local do almoxarifado": "// Thopen/ Thopen - Altair 1 - SP/", "Saldo": "10",
                                            "Mínimo": "2"}])
    visao.limpar()


def _estoque(**mais):
    return EstoqueFalso({"10": {"501": {"saldo": 10, "codigo": "SP-501"}, "502": 5, "503": 4, "504": 7, "505": 9, "506": 3,
                                 "507": 20, "509": {"saldo": None}}}, **mais)


@pytest.fixture
def falso(monkeypatch):
    """O `EstoqueFalso` no lugar do `estoque_da_sessao` (que, de verdade, abre o login do Fracttal de quem está no pedido)."""
    f = _estoque()
    monkeypatch.setattr(E, "estoque_da_sessao", lambda app: f)
    return f


def _via(c, via="microsoft"):
    """De onde nasceu a sessão do Nexus. A que nasceu do login do Fracttal (`via="fracttal"`) acaba junto com o dele: nos pedidos
    de /os o portão confere o cookie `os_sessao` e, sem o JWT, encerra a sessão (`nexus.auth._fim_do_fracttal`). Os testes da
    ponte sem o cookie usam a da Microsoft, que não cai com a do Fracttal e é a que de fato chega ao "entre pelo Fracttal"."""
    with c.session_transaction() as s:
        s["via"] = via
        if via == "microsoft":
            s["ms_ate"] = time.time() + 3600
    return c


def _pcm(app, monkeypatch, email=EMAIL, setor="PCM", via="microsoft"):
    """Uma pessoa do setor `setor`, entrando com o e-mail de uma ficha do cadastro (o pessoa_id sai dela)."""
    _no_setor(monkeypatch, setor)
    return _via(_como(app, email), via)


def _grupos(html):
    """{grupo: n} dos seis grupos da confirmação, pelo que a página diz de cada um."""
    return {g: int(n) for g, n in re.findall(r'data-grupo="(\w+)" data-n="(\d+)"', html)}


def _eventos(app):
    return F.ler(app.config, forcar=True)[F.ABA_EVENTO]


def _revisar(c, corpo, contagem="C-1"):
    return c.post(f"{LISTA}/{contagem}/revisar", json=corpo)


LOTE = "/os/_nexus/inventario/{}/lote"


def _lote(c, contagem="C-1"):
    """O pedaço da contagem que depende do Fracttal, pela ponte (o único lugar onde o login do Fracttal chega)."""
    return c.get(LOTE.format(contagem))


# ── a lista e a contagem ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_lista_e_contagem(app, inv, falso, monkeypatch):
    """A lista mostra a contagem com o almoxarifado, a usina e as contas. A PÁGINA da contagem mostra o contado e NÃO lê o
    Fracttal (o login dele só chega nas rotas de /os); o Sistema vem pela ponte, lido na hora (uma leitura só), e as dez peças
    caem nos seis grupos com os números certos."""
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    html = c.get(LISTA).get_data(as_text=True)
    assert "Almoxarifado Altair" in html and "Altair" in html and f"{LISTA}/C-1" in html
    assert ">Nova<" in html and "Contagens recebidas (1)" in html
    # a página: o contado, e o lugar onde a ponte põe o resto
    r = c.get(f"{LISTA}/C-1")
    pagina = r.get_data(as_text=True)
    assert r.status_code == 200 and falso.chamadas == []
    assert 'data-url="/os/_nexus/inventario/C-1/lote"' in pagina and "lendo o saldo do Fracttal…" in pagina
    assert "data-grupo" not in pagina and ">Sistema</th>" not in pagina and "Gravar" not in pagina
    assert "Fusível 10A" in pagina and re.search(r'data-item="501".*?>12<', pagina, re.S)
    # o pedaço que depende do Fracttal, pela ponte
    r = _lote(c)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and falso.chamadas == ["ler"] and "<html" not in html
    assert r.headers["Cache-Control"] == "no-store"
    assert _grupos(html) == {"para_cima": 3, "para_baixo": 1, "zerar": 1, "sem_alteracao": 1, "nao_tocada": 2, "curadoria": 2}
    assert "Gravar 5 alterações" in html
    # o zerar abre já aberto e destacado; os outros começam fechados
    assert re.search(r'<details[^>]*data-grupo="zerar"[^>]*\bopen\b', html)
    assert not re.search(r'<details[^>]*data-grupo="para_cima"[^>]*\bopen\b', html)
    assert "inv-grupo--zerar" in html
    # Sistema × Contado × Δ × Situação, com o código e o nome da peça
    for cabeca in ("Sistema", "Contado", "Δ", "Situação"):
        assert f">{cabeca}</th>" in html
    linha = {m.group(1): m.group(0) for m in re.finditer(r'<tr[^>]*data-item="(\d+)".*?</tr>', html, re.S)}
    assert set(linha) == {"501", "502", "503", "504", "505", "506", "507", "508", "509"}
    assert "Fusível 10A" in linha["501"] and "+2" in linha["501"] and "10" in linha["501"] and "12" in linha["501"]
    assert "-2" in linha["502"] and "-4" in linha["503"]
    assert "contado inválido" in linha["506"] and "em branco" in linha["505"]
    # o saldo que o Fracttal não disse: o Δ não inventa um "+2" contra um 0 que ninguém viu (a nota diz que vale 0 na conta)
    assert "saldo não informado" in linha["509"] and "não informado</span>" in linha["509"]
    assert re.search(r'data-r="Δ"[^>]*><span class="alm-v">—<', linha["509"]) and "inv-delta--mais" not in linha["509"]
    # a peça nunca ligada ao almoxarifado: o Sistema diz que não está ligada, em vez de um "0" pelado
    assert "não ligada (0)" in linha["508"] and "não ligada ao almoxarifado" in linha["508"]
    assert "entre pelo Fracttal" not in html
    # o botão grava (Task 7): ligado, pela ponte do Fracttal (/os/_nexus), com o N que a tela mostrou
    assert re.search(r'<button[^>]*\bdata-gravar="/os/_nexus/inventario/C-1/gravar"[^>]*>\s*Gravar 5 alterações', html)


def test_a_curadoria_aberta_avisa_e_nao_bloqueia(app, inv, falso, monkeypatch):
    """O achado por decidir e o genérico por identificar avisam, dizendo que decidir depois soma ao contado da peça escolhida;
    a aprovação (o "Gravar N") não é barrada (o desenho 4.2 põe a curadoria como um dos seis grupos, que não mexe)."""
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    html = c.get(f"{LISTA}/C-1").get_data(as_text=True)
    assert "1 achado por decidir na curadoria; decidir depois soma ao contado da peça escolhida" in html
    assert "genérico SP-507" in html and "decidir depois soma ao contado da peça escolhida" in html
    assert "peça sem etiqueta, caixa azul" in _lote(c).get_data(as_text=True)
    assert "Gravar 5 alterações" in _lote(c).get_data(as_text=True)


def test_a_curadoria_ja_decidida_nao_avisa_mais(app, inv, falso, monkeypatch):
    _cenario(inv)
    F.acrescentar(app.config, F.ABA_CURADORIA, [
        {"contagem_id": "C-1", "chave_linha": "L8", "decisao": "e_a_peca", "id_item": "501"},
        {"contagem_id": "C-1", "chave_linha": "L7", "decisao": "confirmar", "id_item": "501"}])
    c = _pcm(app, monkeypatch)
    assert "por decidir na curadoria" not in c.get(f"{LISTA}/C-1").get_data(as_text=True)
    html = _lote(c).get_data(as_text=True)
    # as 2 achadas e as 4 do genérico confirmado entram no contado de 501 (12 + 2 + 4 = 18); o genérico fica com 0 contra o
    # saldo 20 do Fracttal, e o zerar passa a ter a peça dele (o que o PCM confere aberto e destacado)
    g = _grupos(html)
    assert g["curadoria"] == 0 and g["zerar"] == 2 and g["para_cima"] == 3
    assert ">18<" in re.search(r'data-item="501".*?</tr>', html, re.S).group(0)


def test_contagem_que_nao_se_aprova_nao_le_o_fracttal(app, inv, falso, monkeypatch):
    """A de 91 dias, a substituída e a recontagem pedida só mostram o contado e o porquê: não gastam a cota do Fracttal, nem
    a página (que nem pede o lote) nem a ponte (que responde 409)."""
    _publicar(inv, _linha("C-VELHA", "L1", "501", "3", contada=_iso(dias_atras=91)))
    c = _pcm(app, monkeypatch)
    html = c.get(f"{LISTA}/C-VELHA").get_data(as_text=True)
    assert falso.chamadas == [] and "mais de 90 dias" in html and "data-grupo" not in html and "data-lote" not in html
    assert 'data-item="501"' in html and "Gravar" not in html
    r = _lote(c, "C-VELHA")
    assert r.status_code == 409 and "mais de 90 dias" in r.get_json()["erro"] and falso.chamadas == []


def test_contagem_do_app_fora_do_contrato_nao_mostra_comparacao(app, inv, falso, monkeypatch):
    """"ID da linha" vazio: as contas juntariam as linhas e perderiam unidades. A tela diz o que o App mandou de errado e não
    mostra número pela metade (nem a ponte devolve o lote)."""
    _publicar(inv, _linha("C-1", "", "501", "3"), _linha("C-1", "None", "502", "4"))
    c = _pcm(app, monkeypatch)
    html = c.get(f"{LISTA}/C-1").get_data(as_text=True)
    assert "o App mandou linha sem ID da linha" in html and "data-grupo" not in html and falso.chamadas == []
    assert 'data-rev="' not in html and "data-lote" not in html
    assert _lote(c).status_code == 409 and falso.chamadas == []


def test_contagem_que_nao_existe(app, inv, falso, monkeypatch):
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    assert c.get(f"{LISTA}/C-9").status_code == 404
    assert _lote(c, "C-9").status_code == 404


def test_a_lista_sem_o_livro_do_app(app, inv, monkeypatch):
    visao.limpar()
    html = _pcm(app, monkeypatch).get(LISTA).get_data(as_text=True)
    assert "O App ainda não publica as contagens do inventário" in html and "Contagens recebidas" not in html


def test_o_livro_que_nao_le_nao_derruba_a_tela(app, inv, falso, monkeypatch, tmp_path):
    """O livro do inventário que não deu para ler: a tela diz (200), nunca 500 nem "nenhuma contagem"; a ponte diz 502."""
    _cenario(inv)
    (tmp_path / "inventario.json").write_text("{não é json", encoding="utf-8")
    F.limpar()
    c = _pcm(app, monkeypatch)
    for rota in (LISTA, f"{LISTA}/C-1"):
        r = c.get(rota)
        assert r.status_code == 200 and "Não consegui ler o livro do inventário" in r.get_data(as_text=True)
    r = _lote(c)
    assert r.status_code == 502 and "Não consegui ler o livro do inventário" in r.get_json()["erro"]


def test_a_hora_sem_fuso_e_utc_na_tela(app, inv, falso, monkeypatch):
    """Um "Contada em" sem fuso é UTC (o App grava assim), na janela de aprovação e na tela: 12:00 vira 09:00 em Brasília. A
    tela lia como Brasília (`visao._dt`) e mostrava 12:00 onde a janela contava 09:00."""
    _publicar(inv, _linha("C-1", "L1", "501", "3", contada="2026-10-26T12:00:00", enviada="2026-10-26T13:30:00"))
    c = _pcm(app, monkeypatch)
    html = c.get(f"{LISTA}/C-1").get_data(as_text=True)
    assert "contada em 26/10/2026 às 09:00 (Brasília), enviada em 26/10/2026 às 10:30 (Brasília)" in html
    assert "26/10/2026 09:00" in c.get(LISTA).get_data(as_text=True)


# ── sem o login do Fracttal ──────────────────────────────────────────────────────────────────────────────────────────────
def test_sem_login_do_fracttal_nao_grava_nem_le(app, inv, monkeypatch):
    """Quem entrou pela senha de administrador (ou cuja sessão do Fracttal acabou) vê o que o técnico contou, sem Sistema
    nem Δ, e a tela diz como ter o saldo (a ponte responde 401 com o link para entrar pelo Fracttal); nada é lido do Fracttal e
    nada se grava (nem a revisão: sem login não se sabe quem revisa)."""
    from nexus.pcm.inventario.estoque import SemLogin
    _cenario(inv)
    chamadas = []

    def sem_login(app_):
        chamadas.append(1)
        raise SemLogin("sem o login do Fracttal nesta sessão")
    monkeypatch.setattr(E, "estoque_da_sessao", sem_login)
    c = _pcm(app, monkeypatch)
    r = c.get(f"{LISTA}/C-1")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "entre pelo Fracttal para ver o saldo do sistema e gravar" in html and not chamadas
    assert "data-grupo" not in html and ">Sistema</th>" not in html and ">Δ</th>" not in html
    assert "Fusível 10A" in html and re.search(r'data-item="501".*?>12<', html, re.S)   # o contado do técnico segue na tela
    assert "Gravar" not in html
    # a ponte: 401 com o link do login do Fracttal, que volta para esta página
    r = _lote(c)
    j = r.get_json()
    assert r.status_code == 401 and "entre pelo Fracttal" in j["erro"] and len(chamadas) == 1
    assert j["login"].startswith("/os/login?next=") and "%2Ft%2Fpcm%2Fpecas%2Finventario%2FC-1" in j["login"]
    # a senha de administrador: não é uma pessoa, e a revisão fica no nome de quem a faz
    admin = app.test_client()
    with admin.session_transaction() as s:
        s["logado"], s["admin"] = True, True
    r = _revisar(admin, {"acao": "recontagem", "motivo": "teste"})
    assert r.status_code == 409 and "entre com o seu login do Fracttal" in r.get_json()["erro"]
    assert _eventos(app) == []


def test_o_fracttal_pediu_pausa_ou_caiu(app, inv, monkeypatch):
    """429 e queda de rede são mensagens na tela (a ponte diz o que houve em JSON, e a página a põe no lugar do lote), nunca
    500; a página em si segue de pé, com o contado."""
    from nexus.pcm.inventario.estoque import ErroFracttal, Limite
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    for erro, status, texto in ((Limite("RPC HTTP 429"), 429, "o Fracttal pediu uma pausa; tente de novo em 1 minuto"),
                                (ErroFracttal("ASSET_ERRADO", "inventories.warehouses_items_stock"), 502,
                                 "O Fracttal recusou a leitura do saldo"),
                                (ConnectionError("rede"), 502, "Não consegui ler o saldo do Fracttal agora")):
        def cair(app_, erro=erro):
            raise erro
        monkeypatch.setattr(E, "estoque_da_sessao", cair)
        r = _lote(c)
        assert r.status_code == status and texto in r.get_json()["erro"]
        pagina = c.get(f"{LISTA}/C-1")
        assert pagina.status_code == 200 and "Fusível 10A" in pagina.get_data(as_text=True)


# ── a ponte: o login do Fracttal só chega em /os ─────────────────────────────────────────────────────────────────────────
def test_a_ponte_ve_o_login_do_fracttal_e_a_rota_do_pcm_nao(app, inv, monkeypatch):
    """O defeito da revisão das Tasks 5 e 6: o cookie `os_sessao` (o login do Fracttal) é gravado com `Path=/os`, e o navegador
    não o manda para `/t/pcm/...`: o `estoque_da_sessao` numa rota do PCM dava `SemLogin` SEMPRE, e o Sistema nunca aparecia em
    produção (os outros testes trocam o `estoque_da_sessao`). Aqui o `estoque_da_sessao` é o DE VERDADE e o cookie vai com o
    `Path=/os` que o Nexus grava; só o `requests.post` do `api` do clone é de mentira (nada vai ao Fracttal)."""
    from flask import jsonify
    from test_pcm_inventario_estoque import _jwt, _result, linha_de_saldo

    from nexus.torres.oscreator import ponte

    @app.route("/t/pcm/__sonda")                 # uma rota do PCM que pede o login do Fracttal, como a página pedia
    def sonda():
        try:
            E.estoque_da_sessao(app)
            return jsonify(login=True)
        except E.SemLogin:
            return jsonify(login=False)

    _cenario(inv)
    clone = ponte.clone(app)
    import api as os_api
    jwt, pedidos = _jwt(), []

    def post(url, headers=None, json=None, timeout=None):
        pedidos.append((headers["Authorization"], json[0]["method"], json[0]["params"].get("id_warehouse")))
        linhas = [linha_de_saldo(f"90{i}", i, f"SP-{i}", saldo, 0, 0) for i, saldo in
                  ((501, 10), (502, 5), (503, 4), (504, 7), (505, 9), (506, 3), (507, 20), (509, None))]
        return _result({"success": True, "data": linhas, "total": len(linhas)})
    monkeypatch.setattr(os_api.requests, "post", post)
    valor = clone.session_interface.get_signing_serializer(clone).dumps({"jwt": jwt, "conta": {"email": EMAIL}})
    c = _pcm(app, monkeypatch, via="fracttal")             # a sessão que nasceu do login do Fracttal, a que traz o cookie
    c.set_cookie("os_sessao", valor, path="/os")           # o que o Nexus grava no login (nexus.auth.os_cookie_path)
    assert c.get("/t/pcm/__sonda").get_json() == {"login": False}                  # a rota do PCM NÃO vê o login
    assert c.get(f"{LISTA}/C-1").status_code == 200 and pedidos == []             # e a página nem tenta ler o Fracttal
    r = _lote(c)                                                                    # a ponte vê o login e lê o Sistema
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and pedidos == [(f"Bearer {jwt}", "inventories.warehouses_items_stock", 10)]
    assert _grupos(html)["para_cima"] == 3 and re.search(r'data-item="501".*?>10<', html, re.S)
    # sem o cookie, a ponte pede o login: quem entrou pela Microsoft não tem o do Fracttal (e a sessão que nasceu do Fracttal,
    # sem o JWT, o portão do Nexus já encerrou: o fetch recebe o 401 de sessão encerrada, com o link do Entrar do Nexus)
    outro = _pcm(app, monkeypatch)
    r = _lote(outro)
    assert r.status_code == 401 and r.get_json()["login"].startswith("/os/login?next=") and len(pedidos) == 1
    caida = _pcm(app, monkeypatch, via="fracttal")
    r = caida.get(LOTE.format("C-1"), headers={"Sec-Fetch-Dest": "empty"})
    j = r.get_json()
    assert r.status_code == 401 and j["sessao_encerrada"] is True and j["entrar"].startswith("/entrar") and len(pedidos) == 1
    # o cookie de um navegador que o mandou para a raiz (Path=/) chegaria à rota do PCM: a premissa do teste vale
    controle = _pcm(app, monkeypatch, via="fracttal")
    controle.set_cookie("os_sessao", valor, path="/")
    assert controle.get("/t/pcm/__sonda").get_json() == {"login": True}


def test_a_ponte_e_so_do_setor_pcm_e_de_dentro_do_site(app, inv, falso, monkeypatch):
    """O portão por setor só olha `/t/...`: a ponte confere sozinha quem pode (o saldo da empresa não vai a qualquer pessoa
    logada) e que o pedido veio de uma página deste endereço (um site de fora não gasta a cota do Fracttal)."""
    _cenario(inv)
    for setor in ("Performance", "Responsáveis UFV"):
        r = _lote(_pcm(app, monkeypatch, setor=setor))
        assert r.status_code == 403 and "setor PCM" in r.get_json()["erro"]
    assert falso.chamadas == []
    c = _pcm(app, monkeypatch, setor="pcm")
    r = c.get(LOTE.format("C-1"), headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and falso.chamadas == []
    assert c.get(LOTE.format("C-1"), headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200
    # quem não entrou no Nexus nem chega à ponte
    assert app.test_client().get(LOTE.format("C-1")).status_code in (302, 303, 401)
    assert falso.chamadas == ["ler"]


# ── a revisão ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_revisar_tirar_corrigir_recontagem(app, inv, falso, monkeypatch):
    """Cada ação grava o evento no livro do inventário no nome de quem a fez, com o motivo SÓ cifrado, e a tela passa a mostrar
    a contagem revisada; a revisão nunca fala com o Fracttal."""
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    cfg = app.config
    # 1. tirar a peça 502 do lote
    r = _revisar(c, {"acao": "tirar", "id_item": "502", "motivo": "peça contada no almoxarifado errado"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    ev = _eventos(app)
    assert [e["tipo"] for e in ev] == ["peca_tirada"]
    e = ev[0]
    assert (e["contagem_id"], e["id_almoxarifado"], e["id_item"], e["codigo"]) == ("C-1", "10", "502", "SP-502")
    assert float(e["contado_qtd"]) == 3 and str(e["usina_id"]) in ("1", "1.0") and e["usina_ligada_por"] == "de-para do Fracttal"
    assert e["pessoa_hmac"] == codigo_da_pessoa(CHAVE, EMAIL) and str(e["pessoa_id"]) in ("92", "92.0")
    assert F.decifrar(cfg, F.ABA_EVENTO, e) == {"motivo": "peça contada no almoxarifado errado"}
    # 2. corrigir o número da 501 (vírgula ou ponto, os dois valem)
    r = _revisar(c, {"acao": "corrigir", "id_item": "501", "valor": "11,5", "motivo": "o técnico errou o dedo"})
    assert r.status_code == 200
    e = _eventos(app)[1]
    assert e["tipo"] == "numero_corrigido" and e["id_item"] == "501"
    assert (float(e["de_qtd"]), float(e["para_qtd"]), float(e["contado_qtd"])) == (12, 11.5, 12)
    assert F.decifrar(cfg, F.ABA_EVENTO, e) == {"motivo": "o técnico errou o dedo"}
    # a tela: 502 saiu do lote (Gravar 4), 501 vale 11,5 (Δ +1,5), e a contagem está revisada
    assert ">Revisada<" in c.get(f"{LISTA}/C-1").get_data(as_text=True)
    html = _lote(c).get_data(as_text=True)
    assert "Gravar 4 alterações" in html
    g = _grupos(html)
    assert g["para_baixo"] == 0 and g["nao_tocada"] == 3                       # a tirada vai a "não será tocada"
    l501 = re.search(r'data-item="501".*?</tr>', html, re.S).group(0)
    assert "11,5" in l501 and "+1,5" in l501 and "o técnico contou 12" in l501
    assert "tirada do lote" in re.search(r'data-item="502".*?</tr>', html, re.S).group(0)
    # 3. pedir a recontagem recusa a contagem inteira
    r = _revisar(c, {"acao": "recontagem", "motivo": "as fotos estão ilegíveis"})
    assert r.status_code == 200
    e = _eventos(app)[2]
    assert e["tipo"] == "recontagem_pedida" and not e["id_item"] and e["contagem_id"] == "C-1"
    assert F.decifrar(cfg, F.ABA_EVENTO, e) == {"motivo": "as fotos estão ilegíveis"}
    assert L.contagens(cfg)[0]["estado"] == "recontagem_pedida"
    html = c.get(f"{LISTA}/C-1").get_data(as_text=True)
    assert "recontagem pedida" in html.lower() and 'data-rev="' not in html and "data-lote" not in html
    assert _lote(c).status_code == 409
    # só o lote da contagem revisada leu o saldo (a recontagem pedida não se aprova: nem lê); revisar não chamou o Fracttal
    assert falso.chamadas == ["ler"]


def test_o_motivo_so_existe_cifrado(app, inv, falso, monkeypatch, tmp_path):
    """O motivo é texto livre e a API do banco tem leitura aberta: nem o arquivo do livro, nem uma coluna em claro o guarda."""
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    _revisar(c, {"acao": "tirar", "id_item": "502", "motivo": "texto livre do PCM que ninguém pode ler"})
    cru = (tmp_path / "inventario.json").read_text("utf-8")
    assert "texto livre do PCM" not in cru and "dados_cifrados" in cru
    assert "@" not in cru and "supervisora" not in cru           # nem o e-mail de quem revisou: só o HMAC


@pytest.mark.parametrize("valor", ["-1", "", "   ", "abc", "1,2,3", "1e3", None, True, "nan", "inf",
                                   -1, -0.5, float("nan"), float("inf")])         # o número no JSON vale como o texto
def test_corrigir_so_aceita_numero_nao_negativo(app, inv, falso, monkeypatch, valor):
    _cenario(inv)
    r = _revisar(_pcm(app, monkeypatch), {"acao": "corrigir", "id_item": "501", "valor": valor, "motivo": "teste"})
    assert r.status_code == 400 and r.get_json()["ok"] is False and r.get_json()["erro"]
    assert _eventos(app) == []


def test_corrigir_para_zero_vale(app, inv, falso, monkeypatch):
    """O 0 é número: o PCM pode dizer que a peça acabou. Só o vazio e o negativo não valem."""
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    assert _revisar(c, {"acao": "corrigir", "id_item": "501", "valor": "0", "motivo": "acabou"}).status_code == 200
    assert _grupos(_lote(c).get_data(as_text=True))["zerar"] == 2


def test_corrigir_resolve_o_contado_invalido(app, inv, falso, monkeypatch):
    """A peça com contado negativo (a 506) não mexe; o PCM diz o número certo e ela entra no lote."""
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    assert _revisar(c, {"acao": "corrigir", "id_item": "506", "valor": "4", "motivo": "era 4, saiu -2"}).status_code == 200
    html = _lote(c).get_data(as_text=True)
    assert "Gravar 6 alterações" in html
    g = _grupos(html)
    assert g["nao_tocada"] == 1 and g["para_cima"] == 4
    # a nota de "não será gravada" sai (a peça entrou no lote); fica a que diz o que houve, sem repetir um "contou —"
    l506 = re.search(r'data-item="506".*?</tr>', html, re.S).group(0)
    assert "contado inválido (negativo)" not in l506 and "não será gravada" not in l506
    assert "o técnico contou um valor inválido; o PCM corrigiu para 4 (era 4, saiu -2)" in l506
    na_lista = html.split('data-grupo="para_cima"')[1].split("</details>")[0]
    assert "não será gravada" not in na_lista and "corrigiu para 4" in na_lista
    # a peça em branco que o PCM preenche: o técnico não contou, e a nota diz isso
    assert _revisar(c, {"acao": "corrigir", "id_item": "505", "valor": "6", "motivo": "contei na prateleira"}).status_code == 200
    l505 = re.search(r'data-item="505".*?</tr>', _lote(c).get_data(as_text=True), re.S).group(0)
    assert "o técnico deixou em branco; o PCM informou 6 (contei na prateleira)" in l505
    assert "em branco: o técnico não contou" not in l505


@pytest.mark.parametrize("corpo, status", [
    ({"acao": "tirar", "id_item": "502", "motivo": ""}, 400),                        # o motivo é obrigatório
    ({"acao": "tirar", "id_item": "502", "motivo": "   "}, 400),
    ({"acao": "tirar", "id_item": "502"}, 400),
    ({"acao": "recontagem", "motivo": ""}, 400),
    ({"acao": "corrigir", "id_item": "501", "valor": "5"}, 400),
    ({"acao": "tirar", "id_item": "999", "motivo": "x"}, 400),                       # peça que não está na contagem
    ({"acao": "tirar", "id_item": "", "motivo": "x"}, 400),
    ({"acao": "tirar", "id_item": "50 1", "motivo": "x"}, 400),
    ({"acao": "corrigir", "id_item": "507", "valor": "5", "motivo": "x"}, 409),      # genérico por identificar: decide a curadoria
    ({"acao": "apagar", "id_item": "502", "motivo": "x"}, 400),
    ({"acao": "tirar", "id_item": "502", "motivo": "x" * 1001}, 400),
    ({}, 400),
])
def test_revisar_recusa_o_que_nao_vale(app, inv, falso, monkeypatch, corpo, status):
    _cenario(inv)
    r = _revisar(_pcm(app, monkeypatch), corpo)
    assert r.status_code == status and r.get_json()["ok"] is False
    assert _eventos(app) == []


def test_revisar_sem_json_e_contagem_que_nao_existe(app, inv, falso, monkeypatch):
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    assert c.post(f"{LISTA}/C-1/revisar", data="acao=tirar").status_code == 400
    assert _revisar(c, {"acao": "recontagem", "motivo": "x"}, contagem="C-9").status_code == 404
    assert _eventos(app) == []


def test_tirar_duas_vezes_a_mesma_peca(app, inv, falso, monkeypatch):
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    assert _revisar(c, {"acao": "tirar", "id_item": "502", "motivo": "x"}).status_code == 200
    r = _revisar(c, {"acao": "tirar", "id_item": "502", "motivo": "x"})
    assert r.status_code == 409 and len(_eventos(app)) == 1


def test_contagem_que_nao_se_aprova_nao_se_revisa(app, inv, falso, monkeypatch):
    """Recontagem já pedida, substituída, gravada ou velha: 409 com o porquê, e nada é gravado."""
    _publicar(inv,
              _linha("C-1", "L1", "501", "3", almox="10"),
              _linha("C-2", "L1", "501", "3", almox="11", contada=_iso(dias_atras=91)),
              _linha("C-3", "L1", "501", "3", almox="12"))
    _gravar(app, {"tipo": "recontagem_pedida", "contagem_id": "C-1", "id_almoxarifado": "10"},
            {"tipo": "aprovada", "contagem_id": "C-3", "id_almoxarifado": "12", "id_item": "501"})
    c = _pcm(app, monkeypatch)
    antes = len(_eventos(app))
    for cid, motivo in (("C-1", "recontagem pedida"), ("C-2", "mais de 90 dias"), ("C-3", "já gravada")):
        r = _revisar(c, {"acao": "tirar", "id_item": "501", "motivo": "x"}, contagem=cid)
        assert r.status_code == 409 and motivo in r.get_json()["erro"], (cid, r.get_json())
    assert len(_eventos(app)) == antes


def test_a_revisao_depois_do_controle_da_gravacao_e_recusada(app, inv, falso, monkeypatch, tmp_path):
    """O `iniciar` cria o controle da gravação ANTES de registrar a aprovação no livro: se o registro falhou no meio, os
    eventos ainda dizem "nova", mas o lote já foi congelado. Revisar ali seria gravar um evento que a gravação ignora: 409
    "a contagem já foi para a gravação", e nada é gravado (a re-revisão de 27/10/2026). O controle ilegível também recusa."""
    from nexus.pcm.inventario import gravacao as G
    _cenario(inv)
    app.config["NEXUS_DADOS"] = str(tmp_path / "dados")
    c = _pcm(app, monkeypatch)
    assert L.contagens(app.config)[0]["estado"] == "nova"
    G._gravar_json(G._caminho(app.config, "C-1"), {"contagem_id": "C-1", "id_almox": "10", "estado": "parada",
                                                     "lotes": [], "itens": {}})
    for corpo in ({"acao": "tirar", "id_item": "502", "motivo": "x"}, {"acao": "recontagem", "motivo": "x"},
                  {"acao": "corrigir", "id_item": "501", "valor": "11", "motivo": "x"}):
        r = _revisar(c, corpo)
        assert r.status_code == 409 and "já foi para a gravação" in r.get_json()["erro"], corpo
    G._caminho(app.config, "C-1").write_text("{não é json", encoding="utf-8")
    assert _revisar(c, {"acao": "recontagem", "motivo": "x"}).status_code == 409
    assert _eventos(app) == [] and falso.chamadas == []


def test_so_o_setor_pcm_revisa(app, inv, falso, monkeypatch):
    """Como o `test_pcm_publicar`: administrador e setor PCM revisam e leem o saldo do sistema; os outros setores (o
    Responsáveis UFV inclusive) veem o que o técnico contou, sem os botões nem o lote, e levam 403 ao tentar revisar ou ler o
    saldo pela ponte."""
    _cenario(inv)
    corpo = {"acao": "tirar", "id_item": "502", "motivo": "x"}
    for setor in ("Performance", "Responsáveis UFV"):
        c = _pcm(app, monkeypatch, setor=setor)
        assert _revisar(c, corpo).status_code == 403
        assert _lote(c).status_code == 403
        html = c.get(f"{LISTA}/C-1").get_data(as_text=True)
        assert 'data-rev="' not in html and "revisa o lote" in html and "Pedir recontagem" not in html
        assert "data-lote" not in html and "Fusível 10A" in html
    assert _eventos(app) == [] and falso.chamadas == []
    c = _pcm(app, monkeypatch, setor="pcm")
    pagina = c.get(f"{LISTA}/C-1").get_data(as_text=True)
    assert 'data-rev="recontagem"' in pagina and "data-lote" in pagina
    lote = _lote(c).get_data(as_text=True)
    assert 'data-rev="tirar"' in lote and 'data-rev="corrigir"' in lote
    assert _revisar(c, corpo).status_code == 200
    # o administrador pela lista de administradores também (a sessão do Fracttal, com e-mail e administrador)
    adm = app.test_client()
    with adm.session_transaction() as s:
        s["logado"], s["admin"] = True, True
        s["usuario"] = {"email": EMAIL, "nome": "Pessoa Teste"}
    assert _revisar(adm, {"acao": "recontagem", "motivo": "x"}).status_code == 200


def test_o_motivo_do_pcm_so_aparece_para_quem_revisa(app, inv, falso, monkeypatch):
    """O motivo é texto livre (pode citar gente): o PCM o lê na tela; os outros setores leem só "tirada do lote" e "corrigida
    pelo PCM"."""
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    _revisar(c, {"acao": "tirar", "id_item": "502", "motivo": "peça contada no almoxarifado errado"})
    _revisar(c, {"acao": "corrigir", "id_item": "501", "valor": "11", "motivo": "o técnico errou o dedo"})
    pagina = c.get(f"{LISTA}/C-1").get_data(as_text=True)
    lote = _lote(c).get_data(as_text=True)
    for html in (pagina, lote):
        assert "tirada do lote: peça contada no almoxarifado errado" in html
        assert "o técnico contou 12; o PCM corrigiu para 11 (o técnico errou o dedo)" in html
    for setor in ("Performance", "Responsáveis UFV"):
        html = _pcm(app, monkeypatch, setor=setor).get(f"{LISTA}/C-1").get_data(as_text=True)
        assert "tirada do lote" in html and "corrigida pelo PCM" in html
        assert "almoxarifado errado" not in html and "errou o dedo" not in html and "o técnico contou 12" not in html


@pytest.mark.parametrize("extra, status", [
    ({"valor": "900"}, 200),                                  # até 1000 passa sempre (o contado é 12)
    ({"valor": "1000"}, 200),                                 # o limite é "mais de"
    ({"valor": "1001"}, 400),
    ({"valor": "5000"}, 400),
    ({"valor": "5000", "confirmo": True}, 200),               # "confirmo": true aceita
    ({"valor": "5000", "confirmo": "sim"}, 400),              # só o true de verdade
    ({"valor": "4500", "sistema": "500"}, 200),               # o saldo que a página mostrou sobe o limite a 10 x 500
    ({"valor": "6000", "sistema": "500"}, 400),
    ({"valor": "6000", "sistema": "texto"}, 400),             # saldo ilegível não vale: fica o contado
])
def test_corrigir_exagerado_pede_confirmacao(app, inv, falso, monkeypatch, extra, status):
    """Um número mais de 10 vezes o maior entre o contado (12) e o saldo do sistema, e acima de 1000, é quase sempre um zero a
    mais, e iria ao estoque da empresa: 400 pedindo a confirmação (`"confirmo": true`)."""
    _cenario(inv)
    r = _revisar(_pcm(app, monkeypatch), {"acao": "corrigir", "id_item": "501", "motivo": "teste", **extra})
    assert r.status_code == status, r.get_json()
    if status == 400:
        j = r.get_json()
        assert j["confirmar"] is True and "confirme" in j["erro"] and _eventos(app) == []
    else:
        assert len(_eventos(app)) == 1


def test_o_servidor_sem_a_chave_da_pessoa_diz_isso(app, inv, falso, monkeypatch):
    """Sem a NEXUS_PESSOA_HMAC no servidor ninguém tem o código para a auditoria: a mensagem não manda a pessoa "entrar pelo
    Fracttal" (ela já entrou), manda avisar a T.I."""
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    app.config["NEXUS_PESSOA_HMAC"] = ""
    r = _revisar(c, {"acao": "recontagem", "motivo": "x"})
    erro = r.get_json()["erro"]
    assert r.status_code == 409 and "não está configurado" in erro and "T.I." in erro and "login do Fracttal" not in erro
    assert _eventos(app) == []


def test_pedido_de_outro_site_nao_revisa(app, inv, falso, monkeypatch):
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    r = c.post(f"{LISTA}/C-1/revisar", json={"acao": "recontagem", "motivo": "x"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403 and _eventos(app) == []


def test_a_tela_e_do_setor_pcm(app, inv, falso, setores):  # noqa: F811
    """A lista e a contagem são sub-rotas da tela Almoxarifado, que é do setor PCM (outros, pela marca em Base → Acessos)."""
    _cenario(inv)
    assert _como(app, ANA).get(LISTA).status_code == 403                       # a Ana é da Performance
    assert _como(app, ANA).get(f"{LISTA}/C-1").status_code == 403
    assert _como(app, ANA).get(f"{LISTA}/auditoria").status_code == 403
    assert _como(app, ANA).post(f"{LISTA}/C-1/revisar", json={"acao": "recontagem", "motivo": "x"}).status_code == 403
    # o portão por setor só olha /t/...: a ponte (/os/_nexus) confere o setor sozinha
    assert _lote(_via(_como(app, ANA))).status_code == 403


def test_sem_login_a_tela_manda_entrar(app, inv, falso):
    c = app.test_client()
    assert c.get(LISTA).status_code in (302, 303, 401) and c.get(f"{LISTA}/C-1").status_code in (302, 303, 401)
    assert c.post(f"{LISTA}/C-1/revisar", json={}).status_code in (302, 303, 401)


# ── a aba no Almoxarifado ────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_aba_inventario_ao_lado_das_cinco(app, inv, falso, monkeypatch):
    """A aba Inventário fica depois das cinco que já existem, com quantas contagens esperam o PCM; da tela do inventário
    cada uma das cinco volta à aba dela."""
    _semear_almox(inv)
    _publicar(inv, _linha("C-1", "L1", "501", "3"))
    c = _pcm(app, monkeypatch)
    html = c.get("/t/pcm/pecas").get_data(as_text=True)
    abas = re.findall(r'<(?:button|a)[^>]*class="alm-aba"[^>]*>(.*?)</(?:button|a)>', html, re.S)
    assert [re.sub(r"\s+", " ", a).split(" (")[0].strip() for a in abas] == ABAS
    assert re.search(r'<a[^>]*href="/t/pcm/pecas/inventario"[^>]*>\s*Inventário \(1\)', html)
    pagina = c.get(LISTA).get_data(as_text=True)
    for aba in ("reposicao", "almoxarifados", "catalogo", "consumo", "cadastro"):
        assert f'href="/t/pcm/pecas?aba={aba}"' in pagina
    assert re.search(r'aria-selected="true"[^>]*href="/t/pcm/pecas/inventario"|href="/t/pcm/pecas/inventario"[^>]*aria-selected="true"', pagina)


ABAS = ["Reposição", "Por almoxarifado", "Catálogo e saldo", "Consumo nas OS", "Cadastro a corrigir", "Inventário",
        "Mínimo e máximo", "Curadoria", "Auditoria"]


def test_as_abas_do_inventario_ficam_juntas(app, inv, falso, monkeypatch):
    """As quatro partes do inventário (Inventário, Mínimo e máximo, Curadoria, Auditoria) ficam juntas na fila das abas do
    Almoxarifado, em toda página delas, com a de agora marcada; o menu próprio da régua e da curadoria saiu."""
    _semear_almox(inv)
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    for caminho, marcada in ((LISTA, "inventario"), (f"{LISTA}/C-1", "inventario"), (f"{LISTA}/regua", "regua"),
                             (f"{LISTA}/curadoria", "curadoria"), (f"{LISTA}/auditoria", "auditoria")):
        html = c.get(caminho).get_data(as_text=True)
        nav = re.search(r'<nav class="alm-abas".*?</nav>', html, re.S).group(0)
        abas = re.findall(r'<a[^>]*class="alm-aba"[^>]*>(.*?)</a>', nav, re.S)
        assert [re.sub(r"\s+", " ", a).split(" (")[0].strip() for a in abas] == ABAS, caminho
        sel = re.findall(r'<a[^>]*aria-selected="true"[^>]*href="([^"]+)"', nav)
        destino = LISTA if marcada == "inventario" else f"{LISTA}/{marcada}"
        assert sel == [destino], caminho
        assert "rg-nav" not in html, caminho


def test_a_aba_nao_quebra_se_o_inventario_nao_le(app, inv, falso, monkeypatch, tmp_path):
    _semear_almox(inv)
    (tmp_path / "inventario.json").write_text("{não é json", encoding="utf-8")
    F.limpar()
    visao.limpar()
    r = _pcm(app, monkeypatch).get("/t/pcm/pecas")
    assert r.status_code == 200 and 'href="/t/pcm/pecas/inventario"' in r.get_data(as_text=True)


# ── a auditoria ──────────────────────────────────────────────────────────────────────────────────────────────────────────
AUDITORIA = f"{LISTA}/auditoria"


def _historia(app):
    """Uma história no almoxarifado 10 (a Altair), do mais velho ao mais novo: a peça tirada (com motivo), a aprovação, a
    peça gravada (com o movimento do Fracttal), um conflito (com motivo) e a régua gravada. E um evento no almoxarifado de
    teste (99), que fica fora das telas."""
    quem = {"pessoa_hmac": codigo_da_pessoa(CHAVE, EMAIL), "pessoa_id": 92, "id_almoxarifado": "10"}
    F.acrescentar(app.config, F.ABA_EVENTO, [
        dict(quem, tipo="peca_tirada", contagem_id="C-1", id_item="506", codigo="SP-506", quando="2026-10-26T12:00:00Z",
             dados={"motivo": "motivo secreto da peça tirada"}),
        dict(quem, tipo="aprovada", contagem_id="C-1", id_item="501", codigo="SP-501", de_qtd=10, para_qtd=12,
             situacao="para_cima", quando="2026-10-26T12:10:00Z"),
        dict(quem, tipo="peca_gravada", contagem_id="C-1", id_item="501", codigo="SP-501", de_qtd=10, para_qtd=12,
             movimento_fracttal="4321", lote=1, quando="2026-10-26T12:20:00Z"),
        dict(quem, tipo="conflito", contagem_id="C-1", id_item="502", codigo="SP-502", de_qtd=5, para_qtd=3,
             quando="2026-10-26T12:21:00Z", dados={"motivo": "a peça se moveu no Fracttal depois da contagem"}),
        dict(quem, tipo="regua_gravada", id_item="501", codigo="SP-501", de_qtd=2, para_qtd=3, quando="2026-10-26T13:00:00Z"),
        dict(quem, tipo="peca_gravada", contagem_id="T-1", id_almoxarifado="99", id_item="777", codigo="SP-TST-001",
             de_qtd=5, para_qtd=3, movimento_fracttal="9999", quando="2026-10-26T14:00:00Z"),
    ])


def _linhas_da_auditoria(html):
    return re.findall(r'<tr[^>]*\bdata-fl-linha\b[^>]*>.*?</tr>', html, re.S)


def _visiveis(html):
    return [l for l in _linhas_da_auditoria(html) if not re.match(r'<tr[^>]*\bhidden\b', l)]


def test_auditoria_lista_e_filtra(app, inv, falso, monkeypatch):
    """A aba Auditoria (desenho 4.6): os eventos do livro do inventário, do mais novo ao mais velho, com o tipo (cor E palavra),
    o almoxarifado, a peça, a contagem e os números (de → para, o movimento do Fracttal). O filtro por tipo e a busca são da
    própria página (filtro-local.js: cada linha leva o data-f-tipo e o data-f-busca sem acento nem caixa), e o endereço com
    ?tipo= e ?busca= já chega filtrado. O motivo nunca aparece (é cifrado; a contagem aberta o mostra a quem revisa), o
    almoxarifado de teste fica de fora, e o nome de quem fez só vai a quem pode revisar (o PCM)."""
    from nexus.pcm.inventario import revisao as R
    assert set(R.ROTULO_EVENTO) == set(F.TIPOS_EVENTO)                       # todo tipo do livro tem nome na tela
    _cenario(inv)
    app.config["NEXUS_ALMOX_TESTE_IDS"] = "99"
    _historia(app)
    c = _pcm(app, monkeypatch)
    r = c.get(AUDITORIA)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and falso.chamadas == []                     # a auditoria não fala com o Fracttal
    linhas = _linhas_da_auditoria(html)
    assert [re.search(r'data-f-tipo="(\w+)"', l).group(1) for l in linhas] == [
        "regua_gravada", "conflito", "peca_gravada", "aprovada", "peca_tirada"]
    assert "SP-TST-001" not in html and "9999" not in html                   # o almoxarifado de teste fica de fora
    gravada = linhas[2]
    assert "Peça gravada" in gravada and "SP-501" in gravada and "Fusível 10A" in gravada and "Almoxarifado Altair" in gravada
    assert re.search(r"10\s*para\s*12", gravada) and "4321" in gravada and 'href="/t/pcm/pecas/inventario/C-1"' in gravada
    assert "26/10/2026 09:20" in gravada                                     # a hora de Brasília
    assert "Supervisora Campo" in gravada                                    # quem: o nome da ficha, para o PCM
    assert "fusivel 10a" in re.search(r'data-f-busca="([^"]*)"', gravada).group(1)
    assert "Conflito" in linhas[1] and "alm-aviso" in linhas[1]
    assert "Régua gravada" in linhas[0] and re.search(r"2\s*para\s*3", linhas[0]) and "C-1" not in linhas[0]
    # o motivo nunca (é cifrado no livro); a tela só diz que ele existe
    assert "motivo secreto" not in html and "se moveu no Fracttal" not in html
    assert "motivo cifrado" in linhas[4] and "motivo cifrado" not in linhas[2]
    # o filtro na própria página
    assert re.search(r'<select[^>]*name="tipo"[^>]*data-fl\b', html) and 'data-fl-texto="contem"' in html
    assert "filtro-local.js" in html and re.search(r'<option value="conflito"[^>]*>Conflito \(1\)', html)
    filtrada = c.get(f"{AUDITORIA}?tipo=conflito").get_data(as_text=True)
    assert [re.search(r'data-f-tipo="(\w+)"', l).group(1) for l in _visiveis(filtrada)] == ["conflito"]
    assert re.search(r'<option value="conflito"[^>]*\bselected\b', filtrada)
    buscada = c.get(f"{AUDITORIA}?busca=FUSÍVEL").get_data(as_text=True)
    assert len(_visiveis(buscada)) == 3 and 'value="FUSÍVEL"' in buscada      # as três da peça 501 (a régua também)
    # quem só olha (outro setor com a tela marcada): os eventos, sem o nome de quem fez
    from nexus.pcm import telas
    monkeypatch.setattr(telas, "pode_programar", lambda: False)
    olha = c.get(AUDITORIA).get_data(as_text=True)
    assert "Peça gravada" in olha and "Supervisora Campo" not in olha
    assert "ficha 92" not in olha and ">Quem</th>" not in olha               # nem o número da ficha, nem na busca


def test_auditoria_sem_livro_diz_e_nao_quebra(app, inv, falso, monkeypatch, tmp_path):
    """O livro do inventário que não se lê: a tela diz, e não mostra "nenhum evento" (seria mentira)."""
    _cenario(inv)
    (tmp_path / "inventario.json").write_text("{não é json", encoding="utf-8")
    F.limpar()
    r = _pcm(app, monkeypatch).get(AUDITORIA)
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and "Auditoria do inventário" in html
    assert re.search(r'class="cn-erro" role="alert">[^<]*livro do inventário', html) and "Nenhum evento" not in html


# ── o visual ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_sem_cor_fora_de_token():
    """Cor só por token do nexus.css (nos dois temas): nada de #hex nem rgba() nos templates novos, nem no CSS do inventário."""
    base = RAIZ / "nexus" / "templates" / "pcm"
    for nome in ("inventario.html", "inventario_contagem.html", "_inventario_lote.html", "_almox_abas.html",
                 "inventario_auditoria.html"):
        t = (base / nome).read_text("utf-8")
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", t) and "rgba(" not in t and "rgb(" not in t, nome
    css = (RAIZ / "nexus" / "static" / "pcm.css").read_text("utf-8")
    bloco = css[css.index("Inventário do almoxarifado (26/10/2026"):]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", bloco) and "rgba(" not in bloco and "rgb(" not in bloco


def test_o_css_do_pcm_fecha_toda_chave():
    """Toda chave aberta no pcm.css se fecha (fora dos comentários). Caso real (26/10/2026): a junção das Tasks 8/9 com a 5/6
    perdeu o `}` do `@media (max-width:640px)` do fim do inventário, e o CSS da régua e da curadoria, que vinha depois, passou a
    valer só abaixo de 640 px: na tela larga a lista dos almoxarifados e os cartões da curadoria saíam sem estilo."""
    css = re.sub(r"/\*.*?\*/", "", (RAIZ / "nexus" / "static" / "pcm.css").read_text("utf-8"), flags=re.S)
    nivel = 0
    for ch in css:
        nivel += {"{": 1, "}": -1}.get(ch, 0)
        assert nivel >= 0
    assert nivel == 0


def test_o_401_da_sessao_encerrada_nao_vira_endereco():
    """O 401 do portão do Nexus nos pedidos de /os (a sessão que nasceu do Fracttal e perdeu o cookie dele) traz `login: true`
    e o endereço em `entrar`. Caso da revisão de 27/10/2026: o gravar, o continuar e o encerrar faziam `location.href =
    r.j.login`, e a página ia para "/true"; a régua e a curadoria punham "true" no link. Toda tela da ponte trata o
    `sessao_encerrada` à parte e só usa o `login` quando ele é texto."""
    contagem = (RAIZ / "nexus" / "templates" / "pcm" / "inventario_contagem.html").read_text("utf-8")
    ponte = (RAIZ / "nexus" / "static" / "pcm-ponte-inventario.js").read_text("utf-8")
    assert "location.href = r.j.login" not in contagem and contagem.count("entrarDeNovo(r.j)") == 3
    assert "j.sessao_encerrada && window.nexusEntrarDeNovo" in contagem and "typeof j.login === 'string'" in contagem
    assert "x.d.sessao_encerrada" in ponte and 'typeof login === "string"' in ponte


def test_a_sessao_que_caiu_recarrega_e_nao_injeta_a_pagina_de_login():
    """O pedaço do lote vem por `fetch` da ponte; com a sessão do Nexus caída, o portão manda ao /entrar, o `fetch` segue o
    redirecionamento e recebe 200 com a página de login, que ia parar DENTRO da contagem (estacionado da revisão das Tasks 5 e
    6, corrigido na revisão final de 27/10/2026). O `r.redirected` recarrega a página: o portão leva ao login com a volta."""
    contagem = (RAIZ / "nexus" / "templates" / "pcm" / "inventario_contagem.html").read_text("utf-8")
    i = contagem.index("fetch((window.nexusRota || String)(cx.dataset.url)")
    trecho = contagem[i:contagem.index("cx.innerHTML = html", i)]
    assert "if (r.redirected) { window.location.reload(); return; }" in trecho


def test_os_enderecos_nao_partem_da_raiz():
    """Endereço do Nexus nunca a partir da raiz (ele pode rodar debaixo de um prefixo): `{{ raiz }}` nos links e formulários."""
    base = RAIZ / "nexus" / "templates" / "pcm"
    for nome in ("inventario.html", "inventario_contagem.html", "_inventario_lote.html", "_almox_abas.html",
                 "inventario_auditoria.html"):
        t = (base / nome).read_text("utf-8")
        assert not re.search(r'(?:href|action|src)="/(?!/)', t), nome
        assert not re.search(r"(?:fetch|location\.href\s*=)\s*\(?\s*['\"]/", t), nome
