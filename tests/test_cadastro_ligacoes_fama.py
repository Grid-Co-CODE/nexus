"""Os projetos da FAMA em Base → Ligações entre bases (11/11/2026): o sistema `FAMA · Projetos`, lido da
`nexus_os_fama · dim_projeto_fama`, com a proposta pelo nome (o normalizador próprio da FAMA: romano vira arábico e o
"<Cliente> - <Usina N> - UF" do cadastro e do Fracttal casa com "Usina N") e a ligação SÓ pela decisão da tela.
Clientes, usinas e projetos inventados."""
from urllib.parse import parse_qs, urlparse

import pytest

from nexus import create_app
from nexus.cadastro import banco as B
from nexus.cadastro import ligacao_campo
from nexus.cadastro import ligacao_fama as LF
from nexus.cadastro import ligacoes as L
from nexus.cadastro.cifra import gerar_chave
from nexus.cadastro.servico import Carga
from nexus.dados import fato_os_fama as F

from conftest import SENHA_TESTE

FR = "Fracttal · Classificação 1"
DIM = [{"fama_projeto_id": 10, "nome": "Lagoa Fictícia II", "os_qtd": 113},
       {"fama_projeto_id": "11.0", "nome": "Morro Inventado IV", "os_qtd": 5},
       {"fama_projeto_id": 12, "nome": "Vale Repetido I", "os_qtd": 2},
       {"fama_projeto_id": 13, "nome": "Serra Exemplo III", "os_qtd": 1},
       {"fama_projeto_id": 14, "nome": "Projeto Sem Par", "os_qtd": 1}]
# a usina 5 se chama "Serra Exemplo" no cadastro; o Fracttal a chama de "Cliente Alfa - Serra Exemplo 3 - SC" (liga pelo
# código): é por ele que a proposta da FAMA a acha
FONTES = {FR: [{"chave": "Cliente Alfa - Serra Exemplo 3 - SC", "codigo": "SEX300",
                "nome": "Cliente Alfa - Serra Exemplo 3 - SC"}],
          F.SISTEMA: LF.itens(DIM)}


@pytest.fixture
def app_fama(tmp_path):
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "cadastro.json"),
                      "NEXUS_DADOS": str(tmp_path / "dados")})
    app.config.update({"TESTING": True, "SESSION_COOKIE_SECURE": False, "NEXUS_LIGACOES_FONTES_TESTE": FONTES})
    from nexus.cadastro.telas import servico

    def usina(i, nome, cliente, codigo=None):
        v = {"nome": nome, "cliente": cliente, "status": "OPERAÇÃO"}
        return {"id": str(i), "ordem": i, "valores": dict(v, codigo=codigo) if codigo else v}
    with app.app_context():
        servico().aplicar_carga(Carga(
            entidades={"clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Cliente Alfa"}},
                                    {"id": "2", "ordem": 2, "valores": {"nome": "Cliente Beta"}}],
                       "usinas": [usina(1, "Lagoa Fictícia 2", "1"), usina(2, "Morro Inventado 4", "2"),
                                  usina(3, "Vale Repetido 1", "1"), usina(4, "Vale Repetido 1", "2"),
                                  usina(5, "Serra Exemplo", "1", "SEX300"), usina(6, "Outra Usina 1", "2")]},
            listas={"status_usina": ["OPERAÇÃO"]}))
        L.calcular(app.config, servico())
    return app


@pytest.fixture
def cli(app_fama):
    c = app_fama.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return c


def _linhas_fama(app):
    return [tuple(l) for l in L.ler(app.config)["linhas"] if l[1] == F.SISTEMA]


def _secao(cli, **q):
    html = cli.get("/t/base/governanca", query_string=q).get_data(as_text=True)
    return html.split('<section id="ligacoes"')[1]


# ── o normalizador da FAMA ────────────────────────────────────────────────────────────────────────────────────────
def test_o_normalizador_da_fama_poe_o_romano_em_arabico_e_tira_cliente_e_estado():
    assert LF.nome_fama("Lagoa Fictícia II") == "lagoa ficticia 2"
    assert LF.nome_fama("Morro Inventado IV") == LF.nome_fama("morro inventado 4") == "morro inventado 4"
    assert LF.nome_fama("UFV Vale Repetido 01") == "vale repetido 1"
    assert LF.nome_fama("Serra do Exemplo XII") == "serra exemplo 12"
    # o padrão do cadastro e do Fracttal, "<Cliente> - <Usina N> - UF", casa com "Usina N" (o hífen grudado também)
    for k in ("Cliente Alfa - Lagoa Fictícia 2 - RN", "Cliente Alfa - Lagoa Fictícia 2- RN", "Cliente Alfa - Lagoa Fictícia 2"):
        assert LF.nome_fama(k, tirar_cliente=True) == "lagoa ficticia 2", k
    # sem tirar o cliente, ele fica (o nome da FAMA não traz cliente); "II" no fim não é estado, e só a palavra inteira
    # que é romano vira número
    assert LF.nome_fama("Cliente Alfa - Lagoa Fictícia 2") == "cliente alfa lagoa ficticia 2"
    assert LF.nome_fama("Vila Civil - II") == "vila civil 2"
    assert LF.nome_fama("Ilha Vivi") == "ilha vivi" and LF.nome_fama("") == ""


def test_o_normalizador_compartilhado_nao_mudou():
    """O `banco.norm` (o de-para inteiro) e o `ligacao_campo._norm` (os fatos do Campo e das OS) seguem como eram: o
    romano da FAMA mora só no normalizador dela."""
    assert B.norm("Lagoa Fictícia II") == "lagoa ficticia ii"
    assert B.norm("Cliente Alfa - Lagoa Fictícia 2 - RN") == "cliente alfa lagoa ficticia 2"
    assert ligacao_campo._norm("Cliente Alfa - Lagoa Fictícia II - RN") == "cliente alfa-lagoa ficticia ii-rn"


def test_cada_projeto_da_dimensao_vira_uma_chave_pelo_id_com_o_nome_no_rotulo():
    itens = LF.itens(DIM + [{"fama_projeto_id": None, "nome": "sem id"}, {"fama_projeto_id": "10", "nome": "Lagoa"}])
    assert [i["chave"] for i in itens] == ["10", "11", "12", "13", "14"]       # "11.0" do banco é o 11; o id não repete
    assert itens[0] == {"chave": "10", "nome": "Lagoa Fictícia II", "rotulo": "Lagoa Fictícia II", "os": 113,
                        "so_decisao": True, "propor": "fama"}


# ── a ligação: proposta pelo nome, decisão na tela ───────────────────────────────────────────────────────────────
def test_o_projeto_da_fama_nunca_liga_sozinho(app_fama):
    linhas = _linhas_fama(app_fama)
    assert sorted(linhas) == sorted((None, F.SISTEMA, k, B.A_DECIDIR) for k in ("10", "11", "12", "13", "14"))
    # nem quando o nome bateria pela regra das outras bases: a FAMA só liga pela decisão
    from nexus.cadastro.telas import servico
    fontes = {F.SISTEMA: [dict(LF.itens(DIM)[0], nome="Cliente Alfa - Lagoa Fictícia 2")]}
    with app_fama.app_context():
        assert B.de_para(servico(), fontes)[-1][2:] == ["10", B.A_DECIDIR]


def test_a_proposta_pelo_nome_aparece_como_sugestao_de_um_clique(cli):
    secao = _secao(cli, sistema=F.SISTEMA)
    tabela = secao.split("lig-tabela")[1].split("</table>")[0]
    linhas = {l.split('class="lig-chave">')[1].split("<")[0]: l for l in tabela.split("<tr>")[2:]}
    assert set(linhas) == {"Lagoa Fictícia II", "Morro Inventado IV", "Vale Repetido I", "Serra Exemplo III",
                           "Projeto Sem Par"}
    assert "113 OS" in linhas["Lagoa Fictícia II"] and "id 10" in linhas["Lagoa Fictícia II"]
    assert "Cliente Alfa - Lagoa Fictícia 2" in linhas["Lagoa Fictícia II"] and "100%" in linhas["Lagoa Fictícia II"]
    assert "Cliente Beta - Morro Inventado 4" in linhas["Morro Inventado IV"]
    # o mesmo nome em dois clientes: as duas, nenhuma com certeza (quem escolhe é a pessoa)
    assert ("Cliente Alfa - Vale Repetido 1" in linhas["Vale Repetido I"]
            and "Cliente Beta - Vale Repetido 1" in linhas["Vale Repetido I"] and "50%" in linhas["Vale Repetido I"])
    # o nome do cadastro é outro ("Serra Exemplo"), e o Fracttal ligado a ela diz "Serra Exemplo 3": a proposta acha
    assert "Cliente Alfa - Serra Exemplo" in linhas["Serra Exemplo III"]
    assert "nenhuma parecida" in linhas["Projeto Sem Par"]
    assert B.A_DECIDIR in linhas["Lagoa Fictícia II"]
    # o cartão da FAMA, sem as usinas fora: a FAMA só cobre os clientes que a usam
    cartao = secao.split(f'<span class="nome">{F.SISTEMA}</span>')[1].split("</a>")[0]
    assert "0/5 ligadas" in cartao and "usinas fora" not in cartao


def test_ligar_pela_tela_vale_para_o_fato(app_fama, cli):
    r = cli.post("/t/base/ligacoes/decidir", data={"acao": "ligar", "alvo_sistema": F.SISTEMA, "chave": "10",
                                                    "usina": "1"})
    assert r.status_code == 303 and "ok" in parse_qs(urlparse(r.headers["Location"]).query)
    linha = next(l for l in _linhas_fama(app_fama) if l[2] == "10")
    assert linha[0] == 1 and linha[3].startswith("manual (")
    # o de-para que vai ao banco é o que o fato lê: só a ligação decidida dá usina à OS
    de_para = [dict(zip(B.CAB_DE_PARA, l)) for l in L.ler(app_fama.config)["linhas"]]
    assert F.ligacao_decidida(de_para)[0] == {10: 1}
    # a aba Decisões mostra o nome do projeto, não só o id
    dec = _secao(cli, aba="decisoes").split("lig-tabela")[1]
    assert "Lagoa Fictícia II" in dec


def test_ler_as_bases_traz_os_projetos_da_fama_do_banco(monkeypatch, tmp_path):
    """O "Ler as bases de novo" (fora do teste) lê a `dim_projeto_fama` do banco; sem o livro, a FAMA não aparece."""
    import requests

    abas = [("bd_performance", "Base UFV"), ("tickets_performance", "Base de dados - Usinas"),
            ("bd_thopen", "Dados Gerais Usinas")]

    def listagem(com_fama):
        out = [{"id": 100 + i, "workbook_key": w, "sheet_name": a} for i, (w, a) in enumerate(abas)]
        return out + ([{"id": 900, "workbook_key": F.LIVRO, "sheet_name": F.ABA_DIM}] if com_fama else [])

    class R:
        def __init__(self, corpo):
            self.corpo = corpo

        def json(self):
            return self.corpo

        def raise_for_status(self):
            return None

    estado = {"com_fama": True}

    def get(url, params=None, timeout=None):
        if url.endswith("/api/sheets"):
            return R(listagem(estado["com_fama"]))
        if url.endswith("/api/sheets/900/rows"):
            cab = list(DIM[0])
            return R([{"headers": cab, "values": [d.get(c) for c in cab]} for d in DIM])
        return R([])
    monkeypatch.setattr(requests, "get", get)
    monkeypatch.setattr(L, "fracttal", lambda config: [])
    cfg = {"NEXUS_DADOS": str(tmp_path)}
    fs = L.fontes(cfg)
    assert [i["chave"] for i in fs[F.SISTEMA]] == ["10", "11", "12", "13", "14"]
    estado["com_fama"] = False
    assert F.SISTEMA not in L.fontes(cfg)
