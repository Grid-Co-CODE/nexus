"""PCM → Almoxarifado → Usinas e almoxarifados (12/11/2026): o PCM marca, por usina, "sem almoxarifado", "compartilha" (usa o
almoxarifado da usina dona) ou "próprio", e o App de Campo (v343) lê o livro `nexus_almoxarifado_usinas`.

O PCM: "Algumas usinas não tem almoxarifado ou compartilham os almoxarifados [...] poderia ter uma aba desse tipo no Nexus
pra gente ter essa noção"; o Levi: "Passa para o cadastro do nexus". O contrato com o App (as colunas, na ordem) está
fechado: o primeiro teste o prende. O banco é o falso (tests/pg_falso.py); o livro, um arquivo, como na cópia de prova. Dado
de mentira: clientes, usinas e locais inventados, sem nome de gente."""
import json
import re

import pytest
from pg_falso import ApiPGFalsa
from test_campo_visao import _aba, banco  # noqa: F401  (banco é fixture)
from test_pcm_publicar import _no_setor, _pessoa

from nexus.cadastro import setor_ids as SID
from nexus.campo import visao
from nexus.dados import almox_usinas as AU
from nexus.dados import catalogo, explica, radar
from nexus.pcm import almox_usinas as P

TELA, MARCAR = "/t/pcm/pecas/usinas", "/t/pcm/pecas/usinas/marcar"
CLIENTES = [{"cliente_id": 1, "nome": "Cliente Alfa"}, {"cliente_id": 2, "nome": "Cliente Beta"}]
USINAS = [{"usina_id": 1, "nome": "Usina Um", "codigo": "ALF-UM100", "cliente_id": 1, "status": "OPERAÇÃO"},
          {"usina_id": 2, "nome": "Usina Dois", "codigo": "ALF-DOS100", "cliente_id": 1, "status": "OPERAÇÃO"},
          {"usina_id": 3, "nome": "Usina Tres", "codigo": "BET-TRS100", "cliente_id": 2, "status": "OPERAÇÃO"},
          # sem o cliente no cadastro: o mesmo cliente se confere pelo 1º nó do local no Fracttal
          {"usina_id": 4, "nome": "Usina Quatro", "codigo": "ALF-QTR100", "status": "OPERAÇÃO"},
          # sem o local no Fracttal: fora da lista
          {"usina_id": 5, "nome": "Usina Cinco", "codigo": "ALF-CNC100", "cliente_id": 1, "status": "OPERAÇÃO"},
          {"usina_id": 6, "nome": "Usina Seis", "codigo": "ALF-SEI100", "cliente_id": 1, "status": "OPERAÇÃO", "excluido": "sim"}]
# o cabeçalho da aba de mentira sai da 1ª linha (`_aba`): todas com as mesmas colunas
USINAS = [{"cliente_id": None, "excluido": "não", **u} for u in USINAS]
FR = "Fracttal · Classificação 1"
DE_PARA = [{"usina_id": 1, "sistema": FR, "chave_externa": "Cliente Alfa - Usina Um - SP"},
           {"usina_id": 2, "sistema": FR, "chave_externa": "Cliente Alfa - Usina Dois - SP"},
           {"usina_id": 3, "sistema": FR, "chave_externa": "Cliente Beta - Usina Tres - PI"},
           {"usina_id": 4, "sistema": FR, "chave_externa": "Cliente Alfa - Usina Quatro - PI"},
           {"usina_id": 5, "sistema": "BD_Thopen · aba", "chave_externa": "Usina Cinco"},
           {"usina_id": 6, "sistema": FR, "chave_externa": "Cliente Alfa - Usina Seis - SP"}]


@pytest.fixture
def au(app, banco, tmp_path, monkeypatch):  # noqa: F811
    """O cadastro de mentira (clientes, usinas e o de-para), o livro num arquivo e os almoxarifados do Fracttal dublados."""
    for aba, linhas in (("clientes", CLIENTES), ("usinas", USINAS), ("de_para", DE_PARA)):
        _aba(banco, "cadastro_nexus", aba, linhas)
    app.config.update(NEXUS_ALMOX_USINAS_ARQUIVO=str(tmp_path / "almox_usinas.json"), TESTING=True)
    monkeypatch.setattr(P, "almoxarifados_por_usina", lambda b: ({1: ["Almox Um"], 3: ["Almox Tres A", "Almox Tres B"]}, True))
    visao.limpar()
    AU.limpar()
    yield app
    AU.limpar()


def _pcm(app, monkeypatch):
    _no_setor(monkeypatch, SID.PCM)
    return _pessoa(app)


def _marcar(c, usina, situacao, dona="", **mais):
    return c.post(MARCAR, data={"usina": usina, "situacao": situacao, "dona": dona, **mais})


def _livro(app):
    return json.loads(open(app.config["NEXUS_ALMOX_USINAS_ARQUIVO"], encoding="utf-8").read())


def _aviso(c):
    return c.get(TELA).get_data(as_text=True)


# ── o contrato e o catálogo ────────────────────────────────────────────────────────────────────────────────────────────

def test_o_livro_e_o_contrato_com_o_app():
    """As colunas e a ordem da dimensão são o contrato com o App (v343): coluna nova só no fim."""
    assert (AU.LIVRO, AU.ABA) == ("nexus_almoxarifado_usinas", "dim_almoxarifado_usina")
    assert AU.CAB == ("usina_id", "usina", "situacao", "usina_dona_id", "usina_dona", "atualizado_em", "pessoa_hmac")
    assert AU.SITUACOES == ("sem_almoxarifado", "compartilha", "proprio")
    assert AU.CAB_DECISAO == ("decidida_em", "data_id", "usina_id", "situacao", "usina_dona_id", "cliente_por",
                              "pessoa_hmac")


def test_o_catalogo_conhece_o_livro():
    """PRIORIDADE 0: o livro entra no catálogo antes da 1ª gravação, e o radar da Governança o reconhece."""
    lv = catalogo.LIVRO_POR_NOME[AU.LIVRO]
    assert lv.abas == (AU.ABA, AU.ABA_DECISAO) and lv.so_cresce == (AU.ABA_DECISAO,) and not lv.no_banco
    assert all(catalogo.aba_segue_a_regra(a) for a in lv.abas)
    abas = {(AU.LIVRO, a): {"id": 900 + i, "row_count": 1, "visibility": "visible"} for i, a in enumerate(lv.abas)}
    c = radar.classificar(abas)
    assert sorted(t["aba"] for t in c["fato"]) == sorted(lv.abas) and not c["nova"]
    f = catalogo.POR_ID["decisao_almox_usina"]
    assert f.livro == f"{AU.LIVRO} · {AU.ABA_DECISAO}" and f.grao.startswith("1 linha") and f.tipo == "sem_medida"
    assert all(c in AU.CAB_DECISAO for c in f.chave) and f.dims["usina"][0] == "id" and f.dims["data"][0] == "id"
    assert explica.RESUMO.get("decisao_almox_usina") and explica.PARA_QUE.get("decisao_almox_usina")


# ── marcar e desmarcar ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_compartilha_grava_o_contrato_e_desmarcar_tira_a_linha(au, monkeypatch):
    c = _pcm(au, monkeypatch)
    r = _marcar(c, 2, "compartilha", 1)
    assert r.status_code == 303 and r.headers["Location"].endswith(f"{TELA}#u-2")
    html = _aviso(c)
    assert "Usina Dois marcada: usa o almoxarifado de Usina Um (o mesmo cliente, conferido pelo cadastro do Nexus)" in html
    (linha,) = _livro(au)[AU.ABA]
    assert list(linha) == list(AU.CAB)
    assert (linha["usina_id"], linha["usina"], linha["situacao"], linha["usina_dona_id"], linha["usina_dona"]) == (
        2, "Cliente Alfa - Usina Dois - SP", "compartilha", 1, "Cliente Alfa - Usina Um - SP")
    assert linha["atualizado_em"].endswith("Z") and re.fullmatch(r"[0-9a-f]{24}", linha["pessoa_hmac"])
    assert _marcar(c, 3, "sem_almoxarifado").status_code == 303
    assert _marcar(c, 1, "proprio").status_code == 303
    dim = {l["usina_id"]: l for l in _livro(au)[AU.ABA]}
    assert dim[3]["usina_dona_id"] is None and dim[3]["usina_dona"] is None and dim[1]["situacao"] == "proprio"
    # desmarcar tira a linha; o histórico guarda as quatro decisões
    assert _marcar(c, 2, "sem_marcacao").status_code == 303
    assert "Usina Dois ficou sem marcação" in _aviso(c)
    livro = _livro(au)
    assert sorted(l["usina_id"] for l in livro[AU.ABA]) == [1, 3]
    dec = livro[AU.ABA_DECISAO]
    assert [(d["usina_id"], d["situacao"]) for d in dec] == [(2, "compartilha"), (3, "sem_almoxarifado"), (1, "proprio"),
                                                             (2, "desmarcada")]
    assert dec[0]["cliente_por"] == "cadastro do Nexus" and dec[0]["usina_dona_id"] == 1
    assert list(dec[0]) == list(AU.CAB_DECISAO) and len(str(dec[0]["data_id"])) == 8
    assert "@" not in json.dumps(livro) and "Pessoa Teste" not in json.dumps(livro)


@pytest.mark.parametrize("usina,dona,texto", [
    (2, 3, "é de outro cliente (conferido pelo cadastro do Nexus)"),
    (2, 2, "não compartilha o próprio almoxarifado"),
    (2, None, "Compartilha pede a usina dona"),
    (2, 5, "A usina dona não está na lista"),
    (5, 1, "Essa usina não está na lista"),
])
def test_a_dona_que_nao_vale_e_recusada(au, monkeypatch, usina, dona, texto):
    c = _pcm(au, monkeypatch)
    r = _marcar(c, usina, "compartilha", dona or "")
    assert r.status_code == 303 and texto in _aviso(c)
    assert not __import__("os").path.exists(au.config["NEXUS_ALMOX_USINAS_ARQUIVO"])


def test_sem_cadeia(au, monkeypatch):
    """A dona não usa o almoxarifado de outra, nem está sem almoxarifado; e a dona de uma não passa a compartilhar nem a ficar
    sem almoxarifado."""
    c = _pcm(au, monkeypatch)
    _marcar(c, 2, "compartilha", 1)
    _marcar(c, 4, "compartilha", 2)
    assert "Usina Dois já usa o almoxarifado de outra usina: sem cadeia" in _aviso(c)
    _marcar(c, 1, "compartilha", 4)
    assert "Usina Um é a dona do almoxarifado de Usina Dois: ela não pode compartilhar o de outra" in _aviso(c)
    _marcar(c, 1, "sem_almoxarifado")
    assert "ela não pode ficar sem almoxarifado" in _aviso(c)
    _marcar(c, 4, "sem_almoxarifado")
    _marcar(c, 2, "compartilha", 4)                        # a 2 ainda é compartilha da 1: mudar de dona para uma sem almox
    assert "Usina Quatro está marcada sem almoxarifado: não pode ser a dona" in _aviso(c)
    dim = {l["usina_id"]: l["situacao"] for l in _livro(au)[AU.ABA]}
    assert dim == {2: "compartilha", 4: "sem_almoxarifado"}
    # a dona marcada como Próprio continua dona
    _marcar(c, 1, "proprio")
    assert {l["usina_id"]: l["situacao"] for l in _livro(au)[AU.ABA]}[1] == "proprio"


def test_o_mesmo_cliente_pelo_local_do_fracttal(au, monkeypatch):
    """A Usina Quatro não tem o cliente no cadastro: vale o 1º nó do local no Fracttal, e a mensagem diz qual valeu."""
    c = _pcm(au, monkeypatch)
    _marcar(c, 4, "compartilha", 1)
    assert "conferido pelo local do Fracttal" in _aviso(c)
    assert _livro(au)[AU.ABA_DECISAO][0]["cliente_por"] == "local do Fracttal"
    _marcar(c, 3, "compartilha", 4)
    assert "Usina Quatro já usa o almoxarifado de outra usina" in _aviso(c)


def test_a_dona_so_em_compartilha(au, monkeypatch):
    """A tela manda a dona só com Compartilha; a regra recusa a dona em outra situação (o pedido feito à mão)."""
    with pytest.raises(AU.Recusada, match="A usina dona só vale em Compartilha"):
        P.conferir(P.usinas_com_fracttal(_base(au)), {}, 2, "proprio", 1)
    c = _pcm(au, monkeypatch)
    _marcar(c, 2, "proprio", 1)                            # a rota tira a dona fora de Compartilha
    assert _livro(au)[AU.ABA][0]["usina_dona_id"] is None


def _base(app):
    return visao._Base()


# ── quem pode e de onde ────────────────────────────────────────────────────────────────────────────────────────────────

def test_quem_so_olha_ve_a_lista_e_recebe_403_no_post(au, monkeypatch):
    from nexus.pcm import telas
    c = _pcm(au, monkeypatch)
    monkeypatch.setattr(telas, "pode_programar", lambda: False)
    html = c.get(TELA).get_data(as_text=True)
    assert "Usina Dois" in html and 'action="/t/pcm/pecas/usinas/marcar"' not in html
    assert _marcar(c, 2, "proprio").status_code == 403
    assert not __import__("os").path.exists(au.config["NEXUS_ALMOX_USINAS_ARQUIVO"])


def test_o_post_de_outro_site_e_recusado(au, monkeypatch):
    c = _pcm(au, monkeypatch)
    r = c.post(MARCAR, data={"usina": 2, "situacao": "proprio"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    r = c.post(MARCAR, data={"usina": 2, "situacao": "proprio"}, headers={"Origin": "https://outro.exemplo.test"})
    assert r.status_code == 403
    assert not __import__("os").path.exists(au.config["NEXUS_ALMOX_USINAS_ARQUIVO"])
    assert au.test_client().post(MARCAR, data={"usina": 2, "situacao": "proprio"}).status_code in (302, 303, 401)


# ── a tela ─────────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_tela(au, monkeypatch):
    c = _pcm(au, monkeypatch)
    _marcar(c, 2, "compartilha", 1)
    html = c.get(TELA).get_data(as_text=True)
    cartoes = re.findall(r'<article class="rq-card au-usina" id="u-(\d+)"', html)
    assert cartoes == ["2", "4", "1", "3"]                 # do cadastro com o Fracttal, por cliente e nome; sem a 5 e a 6
    um = html.split('id="u-1"')[1].split("</article>")[0]
    assert "No Fracttal: Almox Um" in um and "É a dona do almoxarifado de Usina Dois" in um and "Sem marcação" in um
    dois = html.split('id="u-2"')[1].split("</article>")[0]
    assert "Usa o almoxarifado de <b>Usina Um</b>" in dois and "nenhum almoxarifado ligado a ela" in dois
    assert re.search(r'<option value="1" selected>Usina Um</option>', dois)
    assert ">Usina Tres<" not in dois                       # a dona é do mesmo cliente
    # o "!" diz o que cada situação faz no App e que o par antigo da App Setting vale para a não marcada
    explica_ = html.split("gc-explica-caixa")[1].split("</section>")[0]
    assert "o técnico vê e conta o almoxarifado da usina dona" in explica_ and "deixa de ser cobrado" in explica_
    assert "o par antigo dela segue" in explica_ and "anula o par" in explica_
    # a aba marcada na fila do Almoxarifado
    nav = html.split('class="alm-abas"')[1].split("</nav>")[0]
    assert re.search(r'aria-selected="true"[^>]*href="/t/pcm/pecas/usinas"', nav)
    # os filtros de cliente e de situação
    so_beta = c.get(f"{TELA}?cliente=Cliente+Beta").get_data(as_text=True)
    assert re.findall(r'id="u-(\d+)"', so_beta) == ["3"]
    so_comp = c.get(f"{TELA}?situacao=compartilha").get_data(as_text=True)
    assert re.findall(r'id="u-(\d+)"', so_comp) == ["2"]
    sem = c.get(f"{TELA}?situacao=sem_marcacao").get_data(as_text=True)
    assert re.findall(r'id="u-(\d+)"', sem) == ["4", "1", "3"]
    # a marcação feita com o filtro volta ao filtro
    r = _marcar(c, 3, "proprio", cliente="Cliente Beta")
    assert r.headers["Location"].endswith(f"{TELA}?cliente=Cliente+Beta#u-3")


def test_o_livro_que_nao_se_le_nao_deixa_marcar(au, monkeypatch):
    def caiu(cfg):
        raise ConnectionError("banco fora (de mentira)")
    monkeypatch.setattr(AU, "_ler_cru", caiu)
    c = _pcm(au, monkeypatch)
    html = c.get(TELA).get_data(as_text=True)
    assert "Não consegui ler o livro das usinas" in html and 'action="/t/pcm/pecas/usinas/marcar"' not in html
    _marcar(c, 2, "proprio")
    assert "nada foi gravado, para não apagar o que já está lá" in _aviso(c)


def test_no_banco_as_duas_abas_trocam_e_conferem(app):
    """No banco (falso, devolvendo tudo como texto): a marcação grava as duas abas; desmarcar encolhe a dimensão sem a trava
    do livro que só cresce (que vale só para o histórico), e o histórico cresce."""
    api = ApiPGFalsa(como_texto=True)
    app.extensions["nexus_dados_sessao"] = api
    cfg = {"GRIDCO_DB_API": "http://pg.falso", "GRIDCO_SQL_TOKEN": "tk"}
    usinas = {1: {"id": 1, "nome": "Usina Um", "cliente_id": 1, "local": "Cliente Alfa - Usina Um - SP"},
              2: {"id": 2, "nome": "Usina Dois", "cliente_id": 1, "local": "Cliente Alfa - Usina Dois - SP"}}
    AU.limpar()
    try:
        with app.app_context():
            P.marcar(cfg, usinas, 2, "compartilha", 1, "a1b2c3d4e5f60718293a4b5c")
            P.marcar(cfg, usinas, 1, "proprio", None, "")
            AU.limpar()
            assert sorted(AU.ler(cfg)["marcadas"]) == [1, 2]
            P.marcar(cfg, usinas, 2, "", None, "")
            assert [l["usina_id"] for l in api.linhas(AU.LIVRO, AU.ABA)] == ["1"]
            assert [l["situacao"] for l in api.linhas(AU.LIVRO, AU.ABA_DECISAO)] == ["compartilha", "proprio", "desmarcada"]
            assert list(api.linhas(AU.LIVRO, AU.ABA)[0]) == list(AU.CAB)
    finally:
        app.extensions.pop("nexus_dados_sessao", None)
        AU.limpar()


def test_a_linha_fora_da_forma_e_erro_de_quem_chama():
    with pytest.raises(ValueError, match="situacao"):
        AU.linha(1, "Cliente Alfa - Usina Um - SP", "outra")
    with pytest.raises(ValueError, match="compartilha pede"):
        AU.linha(1, "Cliente Alfa - Usina Um - SP", "compartilha")
    with pytest.raises(ValueError, match="só vai em compartilha"):
        AU.linha(1, "Cliente Alfa - Usina Um - SP", "proprio", 2, "Cliente Alfa - Usina Dois - SP")
    with pytest.raises(ValueError, match="e-mail"):
        AU.linha(1, "alguem@exemplo.test", "proprio")
    with pytest.raises(ValueError, match="pessoa_hmac"):
        AU.linha(1, "Cliente Alfa - Usina Um - SP", "proprio", pessoa_hmac="Pessoa Teste")
