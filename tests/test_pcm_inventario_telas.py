"""A aba Inventário do PCM (26/10/2026, Levi): a lista das contagens que o técnico enviou pelo App, a contagem aberta com o
Sistema (o saldo do Fracttal lido na hora) × Contado × Δ × Situação, os seis grupos da confirmação e a revisão (tirar uma peça
do lote, corrigir o número, pedir a recontagem), que só o setor PCM faz. Desenho:
docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md (seção 4.2). O banco é o falso do Campo, o livro do
inventário é um arquivo local e o Fracttal é o `EstoqueFalso`: nada vai à rede. Dado de mentira, sem nome de gente."""
import re
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


def _pcm(app, monkeypatch, email=EMAIL, setor="PCM"):
    """Uma pessoa do setor `setor`, entrando com o e-mail de uma ficha do cadastro (o pessoa_id sai dela)."""
    _no_setor(monkeypatch, setor)
    return _como(app, email)


def _grupos(html):
    """{grupo: n} dos seis grupos da confirmação, pelo que a página diz de cada um."""
    return {g: int(n) for g, n in re.findall(r'data-grupo="(\w+)" data-n="(\d+)"', html)}


def _eventos(app):
    return F.ler(app.config, forcar=True)[F.ABA_EVENTO]


def _revisar(c, corpo, contagem="C-1"):
    return c.post(f"{LISTA}/{contagem}/revisar", json=corpo)


# ── a lista e a contagem ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_lista_e_contagem(app, inv, falso, monkeypatch):
    """A lista mostra a contagem com o almoxarifado, a usina e as contas; aberta, o Sistema vem LIDO NA HORA do Fracttal
    (uma leitura só) e as dez peças caem nos seis grupos com os números certos."""
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    html = c.get(LISTA).get_data(as_text=True)
    assert "Almoxarifado Altair" in html and "Altair" in html and f"{LISTA}/C-1" in html
    assert ">Nova<" in html and "Contagens recebidas (1)" in html
    r = c.get(f"{LISTA}/C-1")
    html = r.get_data(as_text=True)
    assert r.status_code == 200 and falso.chamadas == ["ler"]
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
    assert "saldo não informado" in linha["509"] and "não ligada" in linha["508"]
    assert "entre pelo Fracttal" not in html
    # a gravação é da próxima entrega: o botão aparece desligado, com a dica
    assert re.search(r'<button[^>]*\bdisabled\b[^>]*>\s*Gravar 5 alterações', html)
    assert "a gravação chega na próxima entrega" in html


def test_a_curadoria_aberta_avisa_e_nao_bloqueia(app, inv, falso, monkeypatch):
    """O achado por decidir e o genérico por identificar avisam, dizendo que decidir depois soma ao contado da peça escolhida;
    a aprovação (o "Gravar N") não é barrada (o desenho 4.2 põe a curadoria como um dos seis grupos, que não mexe)."""
    _cenario(inv)
    html = _pcm(app, monkeypatch).get(f"{LISTA}/C-1").get_data(as_text=True)
    assert "1 achado por decidir na curadoria; decidir depois soma ao contado da peça escolhida" in html
    assert "genérico SP-507" in html and "decidir depois soma ao contado da peça escolhida" in html
    assert "Peça sem etiqueta, caixa azul" in html or "peça sem etiqueta, caixa azul" in html
    assert "Gravar 5 alterações" in html


def test_a_curadoria_ja_decidida_nao_avisa_mais(app, inv, falso, monkeypatch):
    _cenario(inv)
    F.acrescentar(app.config, F.ABA_CURADORIA, [
        {"contagem_id": "C-1", "chave_linha": "L8", "decisao": "e_a_peca", "id_item": "501"},
        {"contagem_id": "C-1", "chave_linha": "L7", "decisao": "confirmar", "id_item": "501"}])
    html = _pcm(app, monkeypatch).get(f"{LISTA}/C-1").get_data(as_text=True)
    assert "por decidir na curadoria" not in html
    # as 2 achadas e as 4 do genérico confirmado entram no contado de 501 (12 + 2 + 4 = 18); o genérico fica com 0 contra o
    # saldo 20 do Fracttal, e o zerar passa a ter a peça dele (o que o PCM confere aberto e destacado)
    g = _grupos(html)
    assert g["curadoria"] == 0 and g["zerar"] == 2 and g["para_cima"] == 3
    assert ">18<" in re.search(r'data-item="501".*?</tr>', html, re.S).group(0)


def test_contagem_que_nao_se_aprova_nao_le_o_fracttal(app, inv, falso, monkeypatch):
    """A de 91 dias, a substituída e a recontagem pedida só mostram o contado e o porquê: não gastam a cota do Fracttal."""
    _publicar(inv, _linha("C-VELHA", "L1", "501", "3", contada=_iso(dias_atras=91)))
    html = _pcm(app, monkeypatch).get(f"{LISTA}/C-VELHA").get_data(as_text=True)
    assert falso.chamadas == [] and "mais de 90 dias" in html and "data-grupo" not in html
    assert 'data-item="501"' in html and "Gravar" not in html


def test_contagem_do_app_fora_do_contrato_nao_mostra_comparacao(app, inv, falso, monkeypatch):
    """"ID da linha" vazio: as contas juntariam as linhas e perderiam unidades. A tela diz o que o App mandou de errado e não
    mostra número pela metade."""
    _publicar(inv, _linha("C-1", "", "501", "3"), _linha("C-1", "None", "502", "4"))
    html = _pcm(app, monkeypatch).get(f"{LISTA}/C-1").get_data(as_text=True)
    assert "o App mandou linha sem ID da linha" in html and "data-grupo" not in html and falso.chamadas == []
    assert 'data-rev="' not in html


def test_contagem_que_nao_existe(app, inv, falso, monkeypatch):
    _cenario(inv)
    assert _pcm(app, monkeypatch).get(f"{LISTA}/C-9").status_code == 404


def test_a_lista_sem_o_livro_do_app(app, inv, monkeypatch):
    visao.limpar()
    html = _pcm(app, monkeypatch).get(LISTA).get_data(as_text=True)
    assert "O App ainda não publica as contagens do inventário" in html and "Contagens recebidas" not in html


def test_o_livro_que_nao_le_nao_derruba_a_tela(app, inv, falso, monkeypatch, tmp_path):
    """O livro do inventário que não deu para ler: a tela diz (200), nunca 500 nem "nenhuma contagem"."""
    _cenario(inv)
    (tmp_path / "inventario.json").write_text("{não é json", encoding="utf-8")
    F.limpar()
    c = _pcm(app, monkeypatch)
    for rota in (LISTA, f"{LISTA}/C-1"):
        r = c.get(rota)
        assert r.status_code == 200 and "Não consegui ler o livro do inventário" in r.get_data(as_text=True)


# ── sem o login do Fracttal ──────────────────────────────────────────────────────────────────────────────────────────────
def test_sem_login_do_fracttal_nao_grava_nem_le(app, inv, monkeypatch):
    """Quem entrou pela senha de administrador (ou cuja sessão do Fracttal acabou) vê o que o técnico contou, sem Sistema
    nem Δ, e a tela diz como ter o saldo; nada é lido do Fracttal e nada se grava (nem a revisão: sem login não se sabe quem
    revisa)."""
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
    assert r.status_code == 200 and "entre pelo Fracttal para ver o saldo do sistema e gravar" in html
    assert "data-grupo" not in html and ">Sistema</th>" not in html and ">Δ</th>" not in html
    assert "Fusível 10A" in html and re.search(r'data-item="501".*?>12<', html, re.S)   # o contado do técnico segue na tela
    assert "Gravar" not in html or re.search(r'<button[^>]*\bdisabled\b[^>]*>\s*Gravar', html)
    # a senha de administrador: não é uma pessoa, e a revisão fica no nome de quem a faz
    admin = app.test_client()
    with admin.session_transaction() as s:
        s["logado"], s["admin"] = True, True
    r = _revisar(admin, {"acao": "recontagem", "motivo": "teste"})
    assert r.status_code == 409 and "entre com o seu login do Fracttal" in r.get_json()["erro"]
    assert _eventos(app) == []


def test_o_fracttal_pediu_pausa_ou_caiu(app, inv, monkeypatch):
    """429 e queda de rede são mensagens na tela, nunca 500."""
    from nexus.pcm.inventario.estoque import ErroFracttal, Limite
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    for erro, texto in ((Limite("RPC HTTP 429"), "o Fracttal pediu uma pausa; tente de novo em 1 minuto"),
                        (ErroFracttal("ASSET_ERRADO", "inventories.warehouses_items_stock"), "O Fracttal recusou a leitura do saldo"),
                        (ConnectionError("rede"), "Não consegui ler o saldo do Fracttal agora")):
        def cair(app_, erro=erro):
            raise erro
        monkeypatch.setattr(E, "estoque_da_sessao", cair)
        r = c.get(f"{LISTA}/C-1")
        html = r.get_data(as_text=True)
        assert r.status_code == 200 and texto in html and "data-grupo" not in html and "Fusível 10A" in html


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
    html = c.get(f"{LISTA}/C-1").get_data(as_text=True)
    assert "Gravar 4 alterações" in html and ">Revisada<" in html
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
    assert "recontagem pedida" in html.lower() and 'data-rev="' not in html
    # só a abertura da tela revisada leu o saldo (a recontagem pedida não se aprova: nem lê); revisar não chamou o Fracttal
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
    assert _grupos(c.get(f"{LISTA}/C-1").get_data(as_text=True))["zerar"] == 2


def test_corrigir_resolve_o_contado_invalido(app, inv, falso, monkeypatch):
    """A peça com contado negativo (a 506) não mexe; o PCM diz o número certo e ela entra no lote."""
    _cenario(inv)
    c = _pcm(app, monkeypatch)
    assert _revisar(c, {"acao": "corrigir", "id_item": "506", "valor": "4", "motivo": "era 4, saiu -2"}).status_code == 200
    html = c.get(f"{LISTA}/C-1").get_data(as_text=True)
    assert "Gravar 6 alterações" in html
    g = _grupos(html)
    assert g["nao_tocada"] == 1 and g["para_cima"] == 4


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


def test_so_o_setor_pcm_revisa(app, inv, falso, monkeypatch):
    """Como o `test_pcm_publicar`: administrador e setor PCM revisam; os outros setores (o Responsáveis UFV inclusive) veem a
    contagem, sem os botões, e levam 403 ao tentar revisar."""
    _cenario(inv)
    corpo = {"acao": "tirar", "id_item": "502", "motivo": "x"}
    for setor in ("Performance", "Responsáveis UFV"):
        c = _pcm(app, monkeypatch, setor=setor)
        assert _revisar(c, corpo).status_code == 403
        html = c.get(f"{LISTA}/C-1").get_data(as_text=True)
        assert 'data-rev="' not in html and "revisa o lote" in html and "Pedir recontagem" not in html
    assert _eventos(app) == []
    c = _pcm(app, monkeypatch, setor="pcm")
    html = c.get(f"{LISTA}/C-1").get_data(as_text=True)
    assert 'data-rev="tirar"' in html and 'data-rev="corrigir"' in html and 'data-rev="recontagem"' in html
    assert _revisar(c, corpo).status_code == 200
    # o administrador pela lista de administradores também (a sessão do Fracttal, com e-mail e administrador)
    adm = app.test_client()
    with adm.session_transaction() as s:
        s["logado"], s["admin"] = True, True
        s["usuario"] = {"email": EMAIL, "nome": "Pessoa Teste"}
    assert _revisar(adm, {"acao": "recontagem", "motivo": "x"}).status_code == 200


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
    assert _como(app, ANA).post(f"{LISTA}/C-1/revisar", json={"acao": "recontagem", "motivo": "x"}).status_code == 403


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
    assert [re.sub(r"\s+", " ", a).split(" (")[0].strip() for a in abas] == [
        "Reposição", "Por almoxarifado", "Catálogo e saldo", "Consumo nas OS", "Cadastro a corrigir", "Inventário"]
    assert re.search(r'<a[^>]*href="/t/pcm/pecas/inventario"[^>]*>\s*Inventário \(1\)', html)
    pagina = c.get(LISTA).get_data(as_text=True)
    for aba in ("reposicao", "almoxarifados", "catalogo", "consumo", "cadastro"):
        assert f'href="/t/pcm/pecas?aba={aba}"' in pagina
    assert re.search(r'aria-selected="true"[^>]*href="/t/pcm/pecas/inventario"|href="/t/pcm/pecas/inventario"[^>]*aria-selected="true"', pagina)


def test_a_aba_nao_quebra_se_o_inventario_nao_le(app, inv, falso, monkeypatch, tmp_path):
    _semear_almox(inv)
    (tmp_path / "inventario.json").write_text("{não é json", encoding="utf-8")
    F.limpar()
    visao.limpar()
    r = _pcm(app, monkeypatch).get("/t/pcm/pecas")
    assert r.status_code == 200 and 'href="/t/pcm/pecas/inventario"' in r.get_data(as_text=True)


# ── o visual ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_sem_cor_fora_de_token():
    """Cor só por token do nexus.css (nos dois temas): nada de #hex nem rgba() nos templates novos, nem no CSS do inventário."""
    base = RAIZ / "nexus" / "templates" / "pcm"
    for nome in ("inventario.html", "inventario_contagem.html", "_almox_abas.html"):
        t = (base / nome).read_text("utf-8")
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", t) and "rgba(" not in t and "rgb(" not in t, nome
    css = (RAIZ / "nexus" / "static" / "pcm.css").read_text("utf-8")
    bloco = css[css.index("Inventário do almoxarifado (26/10/2026"):]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", bloco) and "rgba(" not in bloco and "rgb(" not in bloco


def test_os_enderecos_nao_partem_da_raiz():
    """Endereço do Nexus nunca a partir da raiz (ele pode rodar debaixo de um prefixo): `{{ raiz }}` nos links e formulários."""
    base = RAIZ / "nexus" / "templates" / "pcm"
    for nome in ("inventario.html", "inventario_contagem.html", "_almox_abas.html"):
        t = (base / nome).read_text("utf-8")
        assert not re.search(r'(?:href|action|src)="/(?!/)', t), nome
        assert not re.search(r"(?:fetch|location\.href\s*=)\s*\(?\s*['\"]/", t), nome
