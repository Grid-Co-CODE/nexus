"""Tela Base → Ligações (nexus/cadastro/ligacoes.py + telas_ligacoes.py): buraco à vista e corrigido na própria tela."""
import json
from urllib.parse import parse_qs, urlparse

import pytest

from nexus import create_app
from nexus.cadastro import ligacoes as L
from nexus.cadastro.cifra import gerar_chave
from nexus.cadastro.servico import Carga

from conftest import SENHA_TESTE

FR = "Fracttal · Classificação 1"
FONTES = {FR: [{"chave": "Thopen - Brodowski 1 - SP", "codigo": "BWK100", "nome": "Thopen - Brodowski 1 - SP"},
               {"chave": "Athon - Matões 1 - MA", "codigo": "MTS100", "nome": "Athon - Matões 1 - MA", "tarefas": 843}]}


@pytest.fixture
def app_lig(tmp_path):
    app = create_app({"NEXUS_SECRET_KEY": "chave-de-teste", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_CHAVE_CADASTRO": gerar_chave(), "NEXUS_ARMAZEM_LOCAL": str(tmp_path / "cadastro.json"),
                      "NEXUS_DADOS": str(tmp_path / "dados")})
    app.config.update({"TESTING": True, "SESSION_COOKIE_SECURE": False, "NEXUS_LIGACOES_FONTES_TESTE": FONTES})
    from nexus.cadastro.telas import servico
    with app.app_context():
        servico().aplicar_carga(Carga(
            entidades={
                "clientes": [{"id": "1", "ordem": 1, "valores": {"nome": "Thopen"}},
                             {"id": "2", "ordem": 2, "valores": {"nome": "Faro Energy"}},
                             {"id": "3", "ordem": 3, "valores": {"nome": "Athon"}}],
                "usinas": [
                    {"id": "1", "ordem": 1, "valores": {"nome": "Brodowski", "codigo": "THPN-BWK100", "cliente": "1",
                                                         "status": "OPERAÇÃO", "cidade": "Brodowski", "uf": "SP"}},
                    {"id": "2", "ordem": 2, "valores": {"nome": "Matões 100", "codigo": "CÓDIGO", "cliente": "3",
                                                         "status": "OPERAÇÃO", "cidade": "Matões", "uf": "MA"}},
                    {"id": "3", "ordem": 3, "valores": {"nome": "Pedra do Sal 1", "cliente": "2", "status": "OPERAÇÃO"}},
                ]},
            listas={"status_usina": ["OPERAÇÃO"], "uf": ["SP", "MA"]}))
        L.calcular(app.config, servico())
    return app


@pytest.fixture
def cli(app_lig):
    c = app_lig.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return c


def _linhas(app):
    return [tuple(l) for l in L.ler(app.config)["linhas"] if l[1] == FR]


def _decidir(cli, **form):
    r = cli.post("/t/base/ligacoes/decidir", data={"alvo_sistema": FR, **form})
    assert r.status_code == 303
    return parse_qs(urlparse(r.headers["Location"]).query)


def test_tela_exige_login(app_lig):
    assert app_lig.test_client().get("/t/base/ligacoes").status_code == 302


def test_buraco_aparece_com_a_sugestao_certa(cli):
    html = cli.get("/t/base/ligacoes").get_data(as_text=True)
    assert "Athon - Matões 1 - MA" in html and "843 tarefas" in html
    assert "Athon - Matões 100" in html                       # a sugestão (código "CÓDIGO" no cadastro: só o nome)
    assert "Thopen - Brodowski 1 - SP" not in html.split("lig-tabela")[1].split("</table>")[0]   # ligado: não é buraco


def test_ligar_na_tela_vale_na_hora_e_fica_gravado_com_quem(app_lig, cli):
    q = _decidir(cli, acao="ligar", chave="Athon - Matões 1 - MA", usina="2 · Athon - Matões 100")
    assert "ok" in q
    linha = next(l for l in _linhas(app_lig) if l[2] == "Athon - Matões 1 - MA")
    assert linha[0] == 2 and linha[3].startswith("manual (admin,")
    regras = json.loads(L.caminho_regras(app_lig.config).read_text(encoding="utf-8"))
    assert regras["ligar"][0]["quem"] == "admin" and regras["ligar"][0]["usina_id"] == 2


def test_desligar_e_desfazer(app_lig, cli):
    _decidir(cli, acao="desligar", chave="Thopen - Brodowski 1 - SP", usina="1")
    assert (None, FR, "Thopen - Brodowski 1 - SP", "desligado à mão") in _linhas(app_lig)
    _decidir(cli, acao="desfazer", motivo="desligar", chave="Thopen - Brodowski 1 - SP")
    assert (1, FR, "Thopen - Brodowski 1 - SP", "código") in _linhas(app_lig)


def test_ignorar_pede_motivo(app_lig, cli):
    assert "erro" in _decidir(cli, acao="ignorar", chave="Athon - Matões 1 - MA", motivo=" ")
    _decidir(cli, acao="ignorar", chave="Athon - Matões 1 - MA", motivo="usina vendida")
    assert (None, FR, "Athon - Matões 1 - MA", "ignorado: usina vendida") in _linhas(app_lig)


def test_ausencia_esperada_por_cliente_some_da_aba_fora(app_lig, cli):
    """Faro Energy inteira fora do Fracttal (04/10: 36 usinas): marcada uma vez para o cliente, sai da lista."""
    antes = cli.get("/t/base/ligacoes?aba=fora").get_data(as_text=True)
    assert 'href="/t/base/usina/3"' in antes                  # Pedra do Sal 1 (Faro) na tabela de fora
    _decidir(cli, acao="ausencia", cliente_id="2", motivo="operada fora do Fracttal")
    depois = cli.get("/t/base/ligacoes?aba=fora").get_data(as_text=True)
    assert 'href="/t/base/usina/3"' not in depois and 'href="/t/base/usina/2"' in depois   # Matões continua


def test_teste_sem_pasta_propria_nao_grava_na_pasta_real():
    with pytest.raises(RuntimeError):
        L.caminho_regras({"TESTING": True})


def test_publicar_sem_token_avisa_e_nao_envia(cli):
    r = cli.post("/t/base/ligacoes/publicar", data={})
    assert "GRIDCO_SQL_TOKEN" in parse_qs(urlparse(r.headers["Location"]).query)["erro"][0]


def test_sugestao_pelo_codigo_parecido():
    usinas = [{"id": 2, "nome": "Matões 100", "cliente": "Athon", "codigo": "", "cidade": "Matões", "titulo": "Athon - Matões 100"},
              {"id": 9, "nome": "Marabá 100", "cliente": "Athon", "codigo": "ATHN-MAB100", "cidade": "Marabá", "titulo": "Athon - Marabá 100"}]
    s = L.sugestoes({"chave": "Athon - Matões 1 - MA", "codigo": "MTS100", "nome": "Athon - Matões 1 - MA"}, usinas)
    assert [x["id"] for x in s][0] == 2


def test_sugestao_nunca_cruza_cliente():
    """Achado na tela real (04/10): para "Andradina" da Thopen o Nexus sugeria "E1 - Andradina 1"."""
    usinas = [{"id": 5, "nome": "Andradina 1", "cliente": "E1", "codigo": "", "cidade": "Andradina", "titulo": "E1 - Andradina 1"}]
    assert L.sugestoes({"chave": "Andradina", "nome": "Andradina", "cliente": "Thopen"}, usinas) == []
    assert L.sugestoes({"chave": "Andradina", "nome": "Andradina", "cliente": "E1"}, usinas)[0]["id"] == 5


def test_sugestao_nao_e_coincidencia_de_letra():
    """Na tela real: "Andradina" sugeria "Canarana" e "Anápolis" sugeria "Fernandópolis", a 53%."""
    usinas = [{"id": 46, "nome": "Canarana 1", "cliente": "Thopen", "codigo": "CNN100", "cidade": "Canarana", "titulo": "Thopen - Canarana 1"},
              {"id": 82, "nome": "Fernandópolis", "cliente": "Thopen", "codigo": "THPN-FRN100", "cidade": "Fernandópolis", "titulo": "Thopen - Fernandópolis"},
              {"id": 55, "nome": "Caxambu 1", "cliente": "Thopen", "codigo": "THPN-CXB100", "cidade": "Jundiaí", "titulo": "Thopen - Caxambu 1"}]
    assert L.sugestoes({"chave": "Andradina", "nome": "Andradina", "cliente": "Thopen"}, usinas) == []
    assert L.sugestoes({"chave": "Anápolis", "nome": "Anápolis", "cliente": "Thopen"}, usinas) == []
    assert [x["id"] for x in L.sugestoes({"chave": "Caxambu", "nome": "Caxambu", "cliente": "Thopen"}, usinas)] == [55]


def test_numero_diferente_e_outra_usina():
    """Na tela real: "Thopen - Marajoara 2 - SP" (MRJ200) sugeria "Marajoara 1" a 100%."""
    usinas = [{"id": 98, "nome": "Marajoara 1", "cliente": "Thopen", "codigo": "THPN-MRJ100", "cidade": "Caçapava", "titulo": "Thopen - Marajoara 1"},
              {"id": 92, "nome": "Ipixuna 1 e 2", "cliente": "Thopen", "codigo": "THPN-IPX100", "cidade": "Ipixuna", "titulo": "Thopen - Ipixuna 1 e 2"}]
    assert L.sugestoes({"chave": "Thopen - Marajoara 2 - SP", "codigo": "MRJ200", "nome": "Thopen - Marajoara 2 - SP"}, usinas) == []
    assert [x["id"] for x in L.sugestoes({"chave": "Ipixuna 2", "nome": "Ipixuna 2", "cliente": "Thopen"}, usinas)] == [92]
    assert L.sugestoes({"chave": "Marajoara 2 1", "nome": "Marajoara 2 1", "cliente": "Thopen"}, usinas) == []


def test_sugestao_respeita_cidade_e_potencia():
    usinas = [{"id": 105, "nome": "Ouro Branco", "cliente": "Thopen", "codigo": "THPN-ORB100", "cidade": "Ouro Branco", "mwp": 2.0, "titulo": "Thopen - Ouro Branco"},
              {"id": 11, "nome": "Aparecida do Taboado 1 e 2", "cliente": "Thopen", "codigo": "THPN-ADT100", "cidade": "Aparecida do Taboado", "mwp": 2.58, "titulo": "x"}]
    assert L.sugestoes({"chave": "Ouro Branco I", "nome": "Ouro Branco I", "cliente": "Thopen", "cidade": "Bandeirantes"}, usinas) == []
    assert L.sugestoes({"chave": "AP. do Taboado", "nome": "AP. do Taboado", "cliente": "Thopen",
                        "cidade": "Aparecida do Taboado", "mwp": 0.413}, usinas) == []
