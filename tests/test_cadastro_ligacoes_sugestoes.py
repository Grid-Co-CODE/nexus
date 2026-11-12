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


def _u(i, nome, cliente="Aurora Energia", cidade=None, mwp=None, codigo="", uf=None):
    return {"id": i, "nome": nome, "cliente": cliente, "titulo": f"{cliente} - {nome}", "codigo": codigo,
            "cidade": cidade, "mwp": mwp, "uf": uf}


USINAS = [
    _u(1, "São Brás do Pinhal 1", cidade="São Brás do Pinhal", mwp=2.5, uf="BA"),
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


def test_a_chave_com_palavras_a_mais_vem_a_95_fora_do_lote():
    """O sentido contrário ao do pedido: o nome do cadastro cabe na chave, que tem palavras A MAIS. A palavra a mais pode
    ser a que separa duas usinas ("Nova Quimera 1" não é a "Quimera 1"; o caso da revisão de 12/11/2026, ao contrário do
    pedido): 95, no alto e a um clique, mas fora do lote (ligação errada é pior que nenhuma), e o "por quê" diz."""
    assert _ids(_fr("Aurora - Ventania do Norte 3 - CE")) == [(5, 95)]
    usinas = [_u(11, "Quimera 1", cliente="Boreal")]
    s = L.sugestoes(_fr("Boreal - Nova Quimera 1 - PA"), usinas)
    assert [(x["id"], x["nota"]) for x in s] == [(11, 95)]
    assert s[0]["ressalva"] == ("a chave tem palavras a mais que a Boreal - Quimera 1 (nova): pode ser outra usina, "
                                "confira antes de ligar")
    buraco = {"sistema": FR, "chave": "Boreal - Nova Quimera 1 - PA", "sugestoes": s}
    assert L.sugestoes_de_100([buraco], FR)["ligar"] == []


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


def test_a_letra_solta_e_a_usina():
    """O "a" e o "e" só caem entre dois números (o "1 a 4", o "1 e 2"); fora disso a letra é a usina: "Pinhal A" não é a
    "Pinhal B", nem a "Pinhal" sem letra (revisão de 12/11/2026: o "a" das genéricas apagava a letra, e vinha a 100%)."""
    usinas = [_u(21, "Pinhal B"), _u(22, "Pinhal"), _u(23, "Pinhal 1 a 4", cliente="Boreal")]
    assert _ids(_fr("Aurora - Pinhal A - BA"), usinas[:1]) == []
    # contra a "Pinhal" sem letra, a parecença de letras ainda sugere, abaixo de 100 (como "Caxambu" e "Caxambu 1")
    assert all(n < 100 for _, n in _ids(_fr("Aurora - Pinhal C - BA"), usinas))
    assert _ids(_fr("Aurora - Pinhal B - BA"), usinas)[0] == (21, 100)
    assert _ids(_fr("Boreal - Pinhal 3 - BA"), usinas) == [(23, 100)]          # a faixa responde pelo 3
    assert K.contencao(K.termos("Pinhal A"), "Pinhal B") == K.OUTRO_NUMERO
    assert K.contencao(K.termos("Pinhal 3"), "Pinhal 1 a 4") == K.MESMO
    assert K.contencao(K.termos("Pinhal 5"), "Pinhal 1 a 4") == K.OUTRO_NUMERO
    assert K.contencao(K.termos("Pinhal 1 e 2"), "Pinhal 1 e 2") == K.MESMO
    # a letra abreviada e o apóstrofo não são letra da usina
    assert K.termos("S. Pinhal 1") == K.termos("Pinhal 1")
    assert K.contencao(K.termos("Olho dAgua 1"), "Olho D'Água 1") == K.MESMO


def test_o_romano_acima_do_xii_tambem_e_numero():
    """As `palavras` param no XII; na contenção, "Pinhal XIII" é a 13, e não a "Pinhal" sem número."""
    usinas = [_u(31, "Pinhal")]
    assert all(n < 100 for _, n in _ids(_fr("Aurora - Pinhal XIII - BA"), usinas))
    assert K.contencao(K.termos("Pinhal XIII"), "Pinhal 13") == K.MESMO
    assert K.contencao(K.termos("Pinhal XXXIX"), "Pinhal") == K.OUTRO_NUMERO
    assert K.termos("Vivi Civil 1")[0] == {"vivi", "civil"}                     # palavra não é romano


def test_a_uf_diferente_segura_em_95_sem_vetar():
    """O município de mesmo nome em outro estado: a chave diz SP e a usina é da BA. Não veta (a base também erra a UF),
    mas sai do lote, e o "por quê" diz."""
    s = L.sugestoes(_fr("Aurora - Pinhal 1 - SP"), USINAS)
    assert [(x["id"], x["nota"]) for x in s] == [(1, 95)]
    assert s[0]["ressalva"] == "a Aurora Energia - São Brás do Pinhal 1 é de BA, e a chave diz SP: confira antes de ligar"
    assert _ids(_fr("Aurora - Pinhal 1 - BA")) == [(1, 100)]
    # a UF por extenso, do BD_Thopen
    assert _ids({"chave": "Pinhal 1", "nome": "Pinhal 1", "cliente": "Aurora Energia", "uf": "São Paulo"}) == [(1, 95)]


def test_o_cliente_exato_vale_primeiro():
    """Com "Aurora" e "Aurora Solar" no cadastro, a chave da Aurora fica na Aurora: o começo do nome só vale sem o exato,
    e só se apontar UM cliente (revisão de 12/11/2026: um cliente não é outro)."""
    usinas = [_u(41, "Pinhal Alto 1", cliente="Aurora"), _u(42, "São Brás do Pinhal 1", cliente="Aurora Solar")]
    assert _ids(_fr("Aurora - Pinhal 1 - BA"), usinas) == [(41, 100)]
    assert _ids(_fr("Aurora Solar - Pinhal 1 - BA"), usinas) == [(42, 100)]
    # sem o exato, dois clientes que começam como a chave: dúvida, nenhuma sugestão, e o "por quê" diz
    duas = [_u(43, "Pinhal Alto 1", cliente="Aurora Energia"), _u(44, "São Brás do Pinhal 1", cliente="Aurora Solar")]
    assert _ids(_fr("Aurora - Pinhal 1 - BA"), duas) == []
    assert L.porque_sem_sugestao(_fr("Aurora - Pinhal 1 - BA"), duas) == (
        "o cliente Aurora começa como Aurora Energia e Aurora Solar no cadastro: confira o nome do cliente antes de "
        "ligar à mão")
    # um só pelo começo vale (o caso real: o Fracttal escreve o cliente mais curto)
    assert _ids(_fr("Aurora - Pinhal 1 - BA"), duas[:1]) == [(43, 100)]


def test_o_cliente_da_chave_se_escolhe_uma_vez_e_nao_uma_por_usina(monkeypatch):
    """A seção das Ligações compara cada buraco com o cadastro inteiro a cada visita: escolher o cliente dentro do laço
    das usinas custava uma varredura do cadastro por usina (medido em 12/11/2026, com dados inventados: 60 chaves contra
    260 usinas levavam 4,7 s)."""
    vezes = []
    de_verdade = L._clientes_da_chave
    monkeypatch.setattr(L, "_clientes_da_chave", lambda c, us: vezes.append(c) or de_verdade(c, us))
    usinas = [_u(100 + i, f"Pinhal Alto {i}") for i in range(1, 31)]
    assert _ids(_fr("Aurora - Pinhal Alto 7 - BA"), usinas)[0] == (107, 100)
    assert len(vezes) == 1


def test_duas_contidas_uma_vetada_pela_cidade_a_outra_fica_abaixo_de_100():
    """A única do cliente conta ANTES das travas de cidade e de potência: a candidata que a cidade tirou ainda é dúvida."""
    usinas = [_u(51, "Pinhal do Norte 1", cidade="Cidade Norte"), _u(52, "Pinhal do Sul 1", cidade="Cidade Sul")]
    s = _ids({"chave": "Pinhal 1", "nome": "Pinhal 1", "cliente": "Aurora Energia", "cidade": "Cidade Sul"}, usinas)
    assert [i for i, _ in s] == [52] and s[0][1] < 100


def test_com_o_codigo_igual_e_outra_contida_nenhuma_chega_a_100():
    """O código igual e o nome igual levavam a 100 pelo caminho antigo; com outra contida do cliente, o teto é 95."""
    usinas = [_u(61, "Pinhal 1", codigo="AUR-PNH100"), _u(62, "Pinhal do Sul 1")]
    s = _ids({"chave": "Aurora - Pinhal 1 - BA", "nome": "Aurora - Pinhal 1 - BA", "codigo": "PNH100"}, usinas)
    assert sorted(i for i, _ in s) == [61, 62] and all(n < 100 for _, n in s)


def test_a_sigla_de_duas_letras_nao_e_palavra_forte():
    """ "GD 1" não diz usina nenhuma: a contenção pede uma palavra de três letras ou mais no lado menor."""
    assert K.contencao(K.termos("GD 1"), "Lagoa GD 1") is None
    assert _ids(_fr("Aurora - GD 1 - BA"), [_u(71, "Lagoa GD 1")]) == []


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
    assert len(K.GENERICAS_SUGESTAO) <= 12 and not {"a", "e"} & K.GENERICAS_SUGESTAO       # a letra é a usina
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
               _fr("Aurora - Pinhal 1 - BA"),                             # contém: 100
               _fr("Aurora - Nova Quimera do Norte 1 - PA")]}             # palavras a mais: 95, e o porquê diz


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
                           "Aurora - Pinhal 1 - BA", "Aurora - Nova Quimera do Norte 1 - PA"}
    a_mais = linhas["Aurora - Nova Quimera do Norte 1 - PA"]
    assert "95%" in a_mais and "sem par no cadastro" not in a_mais
    assert ("a chave tem palavras a mais que a Aurora Energia - Nova Quimera 1 (norte): pode ser outra usina, confira "
            "antes de ligar") in a_mais
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
