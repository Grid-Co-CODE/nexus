"""Clima e risco: as usinas em operação e as coordenadas, lidas do cadastro do Nexus (cifrado, aberto só no processo).
Cadastro inventado, numa pasta temporária; nome e coordenada de usina de verdade nunca entram em teste."""
import pytest

from nexus import create_app
from nexus.cadastro.armazem import ArmazemLocal
from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.cadastro.servico import Carga, Servico
from nexus.cadastro.tipos import Legado
from nexus.performance.clima import usinas as U

from conftest import SENHA_TESTE


def u(id_, nome, status="OPERAÇÃO", cliente="1", lat=None, lon=None, uf="CE", cidade="Cidade Um"):
    v = {"nome": nome, "status": status, "cliente": cliente, "uf": uf, "cidade": cidade}
    if lat is not None:
        v["latitude"] = lat
    if lon is not None:
        v["longitude"] = lon
    return {"id": id_, "ordem": int(id_), "valores": v}


@pytest.fixture
def srv(tmp_path):
    s = Servico(ArmazemLocal(tmp_path / "cadastro.json"), Cofre(gerar_chave()))
    s.aplicar_carga(Carga(
        entidades={
            "clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Cliente Alfa"}},
                         {"id": "2", "ordem": 2, "valores": {"nome": "Cliente Beta"}}],
            "usinas": [
                u("1", "Usina Um", lat=-5.5, lon=-40.5),
                u("2", "Usina Dois", cliente="2", lat=-12.25, lon=-45.75, uf="BA", cidade="Cidade Dois"),
                u("3", "Usina Sem Coordenada"),
                u("4", "Usina Em Obra", status="A MOBILIZAR", lat=-9.0, lon=-40.0),
                u("5", "Usina Zero", lat=0.0, lon=0.0),
                u("6", "Usina Trocada", lat=-47.0, lon=-15.0),                      # lat e lon trocados
                u("7", "Usina Sem Cliente", cliente=None, lat=-8.0, lon=-38.0),
                u("8", "Usina So Latitude", lat=-8.0),
                u("9", "Usina Marcador", lat="N/A", lon="N/A"),
                u("10", "Usina Legado", lat=Legado("9 graus sul"), lon=Legado("40 graus oeste")),   # texto herdado do Excel
                u("11", "Usina Lat Positiva", lat=9.5, lon=-40.5),                       # só a latitude fora: sinal trocado
                u("12", "Usina Lon Positiva", lat=-9.5, lon=40.5),                       # só a longitude fora
            ],
        },
        listas={"status_usina": ["OPERAÇÃO", "A MOBILIZAR"], "uf": ["CE", "BA"]}))
    return s


def test_so_usina_em_operacao_com_coordenada_vai_para_o_mapa(srv):
    c = U.carregar(srv)
    assert [x.nome for x in c.usinas] == ["Usina Um", "Usina Dois", "Usina Sem Cliente"]
    assert c.em_operacao == 11                      # a "Em Obra" não conta


def test_usina_sem_coordenada_nunca_some(srv):
    c = U.carregar(srv)
    assert sorted(x.nome for x in c.sem_coordenada) == ["Usina Legado", "Usina Marcador", "Usina Sem Coordenada",
                                                        "Usina So Latitude"]


def test_coordenada_fora_do_brasil_fica_a_parte_e_nao_vai_para_o_mapa(srv):
    c = U.carregar(srv)
    assert sorted(x.nome for x in c.fora_do_brasil) == ["Usina Lat Positiva", "Usina Lon Positiva", "Usina Trocada", "Usina Zero"]
    assert not {x.nome for x in c.usinas} & {x.nome for x in c.fora_do_brasil}


def test_todas_as_em_operacao_estao_em_algum_grupo(srv):
    c = U.carregar(srv)
    assert len(c.usinas) + len(c.sem_coordenada) + len(c.fora_do_brasil) == c.em_operacao


def test_cliente_e_o_nome_e_vazio_vira_sem_cliente(srv):
    por_nome = {x.nome: x for x in U.carregar(srv).usinas}
    assert por_nome["Usina Um"].cliente == "Cliente Alfa" and por_nome["Usina Dois"].cliente == "Cliente Beta"
    assert por_nome["Usina Sem Cliente"].cliente == U.SEM_CLIENTE


def test_uf_e_cidade_vem_do_cadastro(srv):
    por_nome = {x.nome: x for x in U.carregar(srv).usinas}
    assert (por_nome["Usina Dois"].uf, por_nome["Usina Dois"].cidade) == ("BA", "Cidade Dois")


def test_pontos_para_as_fontes_sao_chave_lat_lon(srv):
    c = U.carregar(srv)
    assert c.pontos() == [(x.id, x.lat, x.lon) for x in c.usinas]
    assert c.pontos()[0] == ("1", -5.5, -40.5)


def test_clientes_para_o_filtro_sem_repetir_e_em_ordem(srv):
    assert U.carregar(srv).clientes() == ["Cliente Alfa", "Cliente Beta", U.SEM_CLIENTE]


def test_cliente_so_com_usina_sem_coordenada_tambem_esta_no_filtro():
    com = U.Usina("1", "U1", "Alfa", lat=-5.0, lon=-40.0)
    sem = U.Usina("2", "U2", "Beta")
    fora = U.Usina("3", "U3", "Gama", lat=0.0, lon=0.0)
    assert U.Cadastro([com], [sem], [fora], 3).clientes() == ["Alfa", "Beta", "Gama"]


def test_a_coordenada_nao_aparece_nem_no_repr(srv):
    c = U.carregar(srv)
    texto = repr(c.usinas) + str(c.usinas[0]) + repr(c)
    for numero in ("5.5", "40.5", "12.25", "45.75"):
        assert numero not in texto


def test_ficha_ilegivel_e_contada_e_nao_derruba(srv, tmp_path):
    outra_chave = Servico(ArmazemLocal(tmp_path / "cadastro.json"), Cofre(gerar_chave()))      # a chave não confere
    c = U.carregar(outra_chave)
    assert c.usinas == [] and c.ilegiveis > 0


def test_cadastro_vazio_diz_vazio(tmp_path):
    s = Servico(ArmazemLocal(tmp_path / "nada.json"), Cofre(gerar_chave()))
    c = U.carregar(s)
    assert c.usinas == [] and c.em_operacao == 0


# ── o serviço do app ─────────────────────────────────────────────────────────────────────────────────────────────────

def _app(**extra):
    app = create_app({"NEXUS_SECRET_KEY": "k", "NEXUS_SENHA_ADMIN": SENHA_TESTE, **extra})
    app.config["TESTING"] = True
    return app


def test_sem_a_chave_do_cadastro_diz_o_que_falta():
    with _app().app_context(), pytest.raises(U.SemCadastro) as e:
        U.do_app()
    assert "NEXUS_CHAVE_CADASTRO" in str(e.value)


def test_nos_testes_sem_armazem_proprio_nao_le_o_cadastro_de_verdade():
    app = _app(NEXUS_CHAVE_CADASTRO=gerar_chave())             # chave, mas nenhum NEXUS_ARMAZEM_LOCAL
    with app.app_context(), pytest.raises(U.SemCadastro) as e:
        U.do_app()
    assert "NEXUS_ARMAZEM_LOCAL" in str(e.value)


def test_arquivo_do_cadastro_que_nao_existe_diz_que_nao_esta_na_maquina(tmp_path):
    app = _app(NEXUS_CHAVE_CADASTRO=gerar_chave(), NEXUS_ARMAZEM_LOCAL=str(tmp_path / "nao-existe.json"))
    with app.app_context(), pytest.raises(U.SemCadastro) as e:
        U.do_app()
    assert "não está nesta máquina" in str(e.value)


def test_le_o_cadastro_do_app(srv, tmp_path):
    chave = gerar_chave()
    app = _app(NEXUS_CHAVE_CADASTRO=chave, NEXUS_ARMAZEM_LOCAL=str(tmp_path / "cadastro.json"))
    app.extensions["nexus_cadastro"] = srv                      # o mesmo gancho que o cadastro usa
    with app.app_context():
        c = U.do_app()
    assert [x.nome for x in c.usinas] == ["Usina Um", "Usina Dois", "Usina Sem Cliente"]
