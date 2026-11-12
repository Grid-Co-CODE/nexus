"""As sugestões dos buracos das Ligações entre bases (12/11/2026, Levi: "tem muita coisa que dá para vir sugerido do Nexus
e não está vindo"): a contenção de palavras (o nome do cadastro com palavras a mais ou a menos), o número que tem de
bater, as travas de antes e o "por quê" que diz o que fazer. Clientes, usinas e chaves inventados, no formato das bases
de verdade ("Cliente - Usina N - UF" do Fracttal, o romano dos projetos da FAMA)."""
from difflib import SequenceMatcher
from urllib.parse import parse_qs, urlparse

import pytest

from nexus import create_app
from nexus.cadastro import casamento as K
from nexus.cadastro import ligacao_fama as LF
from nexus.cadastro import ligacoes as L
from nexus.cadastro.cifra import gerar_chave
from nexus.cadastro.servico import Carga

from conftest import SENHA_TESTE

FR = "Fracttal · Classificação 1"


def _u(i, nome, cliente="Aurora Energia", cidade=None, mwp=None, codigo=""):
    return {"id": i, "nome": nome, "cliente": cliente, "titulo": f"{cliente} - {nome}", "codigo": codigo,
            "cidade": cidade, "mwp": mwp}


USINAS = [
    _u(1, "São Brás do Pinhal 1", cidade="São Brás do Pinhal", mwp=2.5),
    _u(2, "Nova Quimera 1"),
    _u(3, "Cachoeira Dourada 1"), _u(4, "Dourada do Sul 1"),
    _u(5, "Ventania 3"),
    _u(6, "Serra Clara do Leste 2"),
    _u(7, "Lagoa Bonita 1", cliente="Boreal"),
    _u(8, "Usina Solar 1", cliente="Boreal"),
]


def _ids(item, usinas=USINAS):
    return [(s["id"], s["nota"]) for s in L.sugestoes(item, usinas)]


def _fr(chave, **k):
    return {"chave": chave, "nome": chave, **k}


# ── a contenção de palavras ──────────────────────────────────────────────────────────────────────────────────────
def test_o_nome_do_cadastro_com_palavras_a_mais_vem_sugerido_a_100():
    """O caso real, com nomes inventados: a chave "Cliente - Pinhal 1 - UF" é a "São Brás do Pinhal 1" do cadastro, e a
    parecença de letras (o corte de 0,78) não a achava. O cliente do Fracttal é o começo do nome do cadastro ("Aurora" e
    "Aurora Energia"): é o mesmo cliente."""
    assert SequenceMatcher(None, "pinhal 1", "sao bras pinhal 1").ratio() < 0.78       # por isso não vinha
    assert _ids(_fr("Aurora - Pinhal 1 - BA")) == [(1, 100)]


def test_o_nome_do_cadastro_com_palavras_a_menos_tambem():
    assert _ids(_fr("Aurora - Ventania do Norte 3 - CE")) == [(5, 100)]


def test_o_romano_vira_arabico_na_contencao():
    assert _ids(_fr("Aurora - Clara do Leste II - MG")) == [(6, 100)]


def test_o_numero_que_nao_existe_no_cadastro_nao_sugere_e_o_porque_diz_o_que_falta():
    item = _fr("Aurora - Nova Quimera 2 - PA")
    assert L.sugestoes(item, USINAS) == []
    assert L.porque_sem_sugestao(item, USINAS) == "o cadastro tem a Nova Quimera 1, não a 2: crie no Registro mestre"
    item = _fr("Aurora - Pinhal 2 - BA")
    assert L.sugestoes(item, USINAS) == []
    assert L.porque_sem_sugestao(item, USINAS) == ("o cadastro tem a São Brás do Pinhal 1, não a 2: crie no Registro "
                                                   "mestre")


def test_duas_candidatas_do_cliente_nenhuma_chega_a_100():
    s = _ids(_fr("Aurora - Dourada 1 - GO"))
    assert sorted(i for i, _ in s) == [3, 4] and all(n < 100 for _, n in s)
    buraco = {"sistema": FR, "chave": "Aurora - Dourada 1 - GO", "sugestoes": L.sugestoes(_fr("Aurora - Dourada 1 - GO"),
                                                                                          USINAS)}
    assert L.sugestoes_de_100([buraco], FR) == {"ligar": [], "pulos": {"varias": 1, "abaixo": 0, "sem": 0, "repetida": 0}}


def test_sem_o_cliente_na_chave_a_unica_fica_abaixo_de_100():
    """Sem o cliente, a trava do cliente não se confere (o mesmo nome em dois clientes é usina diferente): a pessoa
    confirma, o lote não liga."""
    assert _ids({"chave": "Pinhal 1", "nome": "Pinhal 1"}) == [(1, 90)]


# ── as travas de antes continuam ─────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("item", [
    _fr("Boreal - Pinhal 1 - BA"),                                         # outro cliente
    _fr("Aurorax - Pinhal 1 - BA"),                                        # nem começo do nome do cliente
    {"chave": "Pinhal 1", "nome": "Pinhal 1", "cliente": "Aurora Energia", "cidade": "Cidade Distante"},
    {"chave": "Pinhal 1", "nome": "Pinhal 1", "cliente": "Aurora Energia", "mwp": 0.4},
    _fr("Aurora - Pinhal 3 - BA"),                                         # outro número
    _fr("Aurora - Pinhal - BA"),                                           # a chave sem número, o cadastro com
], ids=["cliente", "cliente_parecido", "cidade", "potencia", "numero", "sem_numero"])
def test_as_travas_de_antes_continuam(item):
    assert 1 not in [i for i, _ in _ids(item)]


@pytest.mark.parametrize("chave", ["Aurora - UFV Pinhal 1 - BA", "Aurora - Usina Pinhal 1 - BA",
                                   "Aurora - Pinhal Solar 1 - BA", "Aurora - Cliente Pinhal 1 - BA",
                                   "Aurora - Pinhal da Serra 1 - BA"])
def test_as_palavras_genericas_nao_contam(chave):
    """usina, ufv, solar, cliente e as preposições não fazem uma usina ser outra (a lista curta, `GENERICAS_SUGESTAO`);
    "Serra" conta, e "Pinhal da Serra" não está no nome do cadastro."""
    esperado = [] if "Serra" in chave else [(1, 100)]
    assert [x for x in _ids(_fr(chave)) if x[0] == 1 and x[1] == 100] == esperado


def test_a_lista_curta_das_genericas():
    assert {"usina", "ufv", "solar", "cliente", "de", "do", "da"} <= K.GENERICAS_SUGESTAO
    assert len(K.GENERICAS_SUGESTAO) <= 12
    # só as genéricas de um lado não contêm nada: "Usina 1" não é a "Usina Solar 1" pela contenção
    assert K.contencao(K.termos("Usina 1"), "Usina Solar 1") is None
    # nem a palavra fraca sozinha ("Nova" está em toda parte)
    assert K.contencao(K.termos("Nova 1"), "Nova Quimera 1") is None
    assert K.contencao(K.termos("Quimera 1"), "Nova Quimera 1") == K.MESMO
    assert K.contencao(K.termos("Quimera 2"), "Nova Quimera 1") == K.OUTRO_NUMERO
    # "1 e 2" do cadastro responde pelo 2
    assert K.contencao(K.termos("Pinhal 2"), "São Brás do Pinhal 1 e 2") == K.MESMO


def test_o_porque_sem_usina_parecida_e_sem_o_cliente():
    assert L.porque_sem_sugestao(_fr("Boreal - Pinhal 1 - BA"), USINAS) == (
        "o cadastro não tem usina parecida deste cliente: crie no Registro mestre")
    assert L.porque_sem_sugestao(_fr("Cometa - Pinhal 1 - BA"), USINAS) == (
        "o cadastro não tem o cliente Cometa: confira o nome do cliente ou crie no Registro mestre")
    assert L.porque_sem_sugestao({"chave": "Rio Inexistente 4", "nome": "Rio Inexistente 4"}, USINAS) == (
        "o cadastro não tem usina parecida: crie no Registro mestre")


def test_o_porque_da_usina_de_nome_contido_que_a_trava_tirou():
    """Achado no dado real (12/11/2026): a usina de nome certo vetada pela cidade (a base erra a cidade) fazia o "por
    quê" dizer "o cadastro tem a X 2, não a 1" com a X 1 lá. A vetada vem primeiro, com a trava que a tirou."""
    base = {"chave": "Pinhal 1", "nome": "Pinhal 1", "cliente": "Aurora Energia"}
    assert L.porque_sem_sugestao(dict(base, cidade="Cidade Distante"), USINAS) == (
        "o cadastro tem a São Brás do Pinhal 1, mas a cidade da base não bate com a do cadastro: confira antes de ligar "
        "à mão")
    assert L.porque_sem_sugestao(dict(base, mwp=0.4), USINAS) == (
        "o cadastro tem a São Brás do Pinhal 1, mas a potência da base não bate com a do cadastro: confira antes de "
        "ligar à mão")


def test_o_porque_quando_um_lado_nao_tem_numero():
    usinas = USINAS + [_u(9, "Ribeira Alta")]
    item = _fr("Aurora - Ribeira 1, 2, 3 e 4 - CE")
    assert L.sugestoes(item, usinas) == []
    assert L.porque_sem_sugestao(item, usinas) == ("o cadastro tem a Ribeira Alta, sem número: confira se é a mesma "
                                                   "usina antes de ligar à mão")
    assert L.porque_sem_sugestao(_fr("Aurora - Pinhal - BA"), USINAS) == (
        "o cadastro tem a São Brás do Pinhal 1, com número, e a chave não diz qual: confira ou crie no Registro mestre")


def test_o_cliente_pelo_comeco_do_nome():
    assert L.mesmo_cliente("Aurora", "Aurora Energia") and L.mesmo_cliente("aurora energia", "AURORA")
    assert L.mesmo_cliente("Boreal", "Boreal")
    assert not L.mesmo_cliente("Aurorax", "Aurora Energia") and not L.mesmo_cliente("Energia", "Aurora Energia")
    assert not L.mesmo_cliente("", "Aurora")


# ── os projetos da FAMA ──────────────────────────────────────────────────────────────────────────────────────────
def test_a_fama_tambem_acha_pela_contencao_abaixo_de_100():
    """O projeto da FAMA não diz o cliente: o nome contido vem a 90 (a pessoa confirma). Depois que a chave do Fracttal
    dela é ligada, o índice da FAMA a acha pelo nome igual, a 100."""
    por_id = {u["id"]: u for u in USINAS}
    idx = LF.indice(USINAS)
    assert [(s["id"], s["nota"]) for s in LF.sugestoes({"nome": "Pinhal I"}, idx, por_id)] == [(1, 90)]
    assert all(s["nota"] < 100 for s in LF.sugestoes({"nome": "Dourada I"}, idx, por_id))
    assert LF.sugestoes({"nome": "Pinhal II"}, idx, por_id) == []
    idx = LF.indice(USINAS, {1: ["Aurora - Pinhal 1 - BA"]})
    assert [(s["id"], s["nota"]) for s in LF.sugestoes({"nome": "Pinhal I"}, idx, por_id)] == [(1, 100)]


# ── a seção: o "por quê" na tela ─────────────────────────────────────────────────────────────────────────────────
FONTES = {FR: [_fr("Boreal - Lagoa Bonita 1 - SP"),                       # liga pelo nome
               _fr("Boreal - Lagoa Bonita do Alto 1 - SP"),               # contém a mesma usina: já ligada a outra chave
               _fr("Aurora - Nova Quimera 2 - PA"),                       # o cadastro só tem a 1
               _fr("Aurora - Pinhal 1 - BA")]}                            # contém: 100


@pytest.fixture
def cli(tmp_path):
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "cadastro.json"),
                      "NEXUS_DADOS": str(tmp_path / "dados")})
    app.config.update({"TESTING": True, "SESSION_COOKIE_SECURE": False, "NEXUS_LIGACOES_FONTES_TESTE": FONTES})
    from nexus.cadastro.telas import servico
    with app.app_context():
        servico().aplicar_carga(Carga(
            entidades={"clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Aurora Energia"}},
                                    {"id": "2", "ordem": 2, "valores": {"nome": "Boreal"}}],
                       "usinas": [{"id": "1", "ordem": 1, "valores": {"nome": "São Brás do Pinhal 1", "cliente": "1",
                                                                       "status": "OPERAÇÃO"}},
                                  {"id": "2", "ordem": 2, "valores": {"nome": "Nova Quimera 1", "cliente": "1",
                                                                       "status": "OPERAÇÃO"}},
                                  {"id": "7", "ordem": 3, "valores": {"nome": "Lagoa Bonita 1", "cliente": "2",
                                                                       "status": "OPERAÇÃO"}}]},
            listas={"status_usina": ["OPERAÇÃO"]}))
        L.calcular(app.config, servico())
    c = app.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    c.app = app
    return c


def _linhas_da_tabela(cli):
    html = cli.get("/t/base/governanca?aba=buracos").get_data(as_text=True).split('<section id="ligacoes"')[1]
    tabela = html.split("lig-tabela")[1].split("</table>")[0]
    return {l.split('class="lig-chave">')[1].split("<")[0]: l for l in tabela.split("<tr>")[2:]}


def test_o_porque_util_aparece_no_lugar_do_sem_par(cli):
    linhas = _linhas_da_tabela(cli)
    assert set(linhas) == {"Boreal - Lagoa Bonita do Alto 1 - SP", "Aurora - Nova Quimera 2 - PA",
                           "Aurora - Pinhal 1 - BA"}
    q = linhas["Aurora - Nova Quimera 2 - PA"]
    assert "o cadastro tem a Nova Quimera 1, não a 2: crie no Registro mestre" in q and "sem par no cadastro" not in q
    p = linhas["Aurora - Pinhal 1 - BA"]
    assert "Aurora Energia - São Brás do Pinhal 1" in p and "100%" in p


def test_a_usina_ja_ligada_por_nome_a_outra_chave_da_base_fica_abaixo_de_100_e_diz(cli):
    linha = _linhas_da_tabela(cli)["Boreal - Lagoa Bonita do Alto 1 - SP"]
    assert "Boreal - Lagoa Bonita 1" in linha and "100%" not in linha
    assert ("a Boreal - Lagoa Bonita 1 já está ligada por nome a outra chave desta base (Boreal - Lagoa Bonita 1 - SP): "
            "confira antes de ligar") in linha
    from nexus.cadastro.telas import servico
    with cli.app.test_request_context("/"):
        p = L.panorama(servico(), L.ler(cli.app.config), L.carregar_regras(cli.app.config))
    assert [c for c, _ in L.sugestoes_de_100(p["buracos"], FR)["ligar"]] == ["Aurora - Pinhal 1 - BA"]


def test_ligar_a_sugestao_nova_pela_tela(cli):
    r = cli.post("/t/base/ligacoes/decidir", data={"acao": "ligar", "alvo_sistema": FR, "chave": "Aurora - Pinhal 1 - BA",
                                                    "usina": "1"})
    assert r.status_code == 303 and "ok" in parse_qs(urlparse(r.headers["Location"]).query)
    assert "Aurora - Pinhal 1 - BA" not in _linhas_da_tabela(cli)
