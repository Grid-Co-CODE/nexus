"""O setor de cada relatório, escolhido na Central de emissão (14/10/2026, Levi: "adicione a opção de eu escolher de qual
setor é o relatório! Apenas administradores podem editar!"): só o administrador vê e grava; o setor dono vê o relatório
sem marcar em Base → Acessos e aparece no cartão; a escolha vale por cima do padrão do código e segue o setor renomeado.
Pessoas e setores de mentira, no banco falso do test_campo_visao."""
import re

import pytest

from nexus.auth import dono_relatorio as DR
from nexus.auth import setor_telas as ST
from nexus.cadastro import setores as S
from nexus.dados import catalogo
from test_campo_visao import banco  # noqa: F401  (fixture)
from test_setor_telas import ANA, BASE, _como, setores  # noqa: F401  (fixtures)

CENTRAL = "/t/relatorios/central"
DANI = "dani@exemplo.test"          # setor PCM


@pytest.fixture(autouse=True)
def _sem_copias():
    S._CACHE.clear()
    ST.limpar()
    DR.limpar()
    yield
    S._CACHE.clear()
    ST.limpar()
    DR.limpar()


@pytest.fixture
def com_pcm(app, setores):          # noqa: F811
    """Performance (1, a Ana), Administrador (2) e PCM (3, a Dani)."""
    novo = S.criar("PCM", app.config, BASE, setores)
    S.definir([{"id": 703, "email": DANI, "ficha": None, "por": ""}], novo["setor_id"], app.config, BASE, setores)
    return novo["setor_id"]


def _codigo(c) -> str:
    return re.search(r'name="codigo" value="([^"]+)"', c.get(CENTRAL).get_data(as_text=True)).group(1)


def _salvar(c, donos: dict, codigo=None):
    dados = {"codigo": codigo if codigo is not None else _codigo(c)}
    dados.update({f"dono:{t}": ("" if s is None else str(s)) for t, s in donos.items()})
    return c.post(CENTRAL, data=dados)


def _linhas(banco):                 # noqa: F811
    return banco.linhas(DR.LIVRO, DR.ABA)


def _cartoes(c) -> set[str]:
    return set(re.findall(r'data-relatorio="([^"]+)"', c.get(CENTRAL).get_data(as_text=True)))


def test_so_o_administrador_ve_a_escolha_e_grava(app, logado, com_pcm, setores):   # noqa: F811
    html = logado.get(CENTRAL).get_data(as_text=True)
    assert "Setor de cada relatório" in html and 'name="dono:pcm-diario"' in html and 'name="dono:relatorio"' in html
    # o padrão do código: os do PCM no setor PCM, os da plataforma na Performance
    assert re.search(r'name="dono:pcm-diario">.*?<option value="3" selected>PCM</option>', html, re.S)
    assert re.search(r'name="dono:relatorio">.*?<option value="1" selected>Performance</option>', html, re.S)
    ana = _como(app, ANA)
    assert "Setor de cada relatório" not in ana.get(CENTRAL).get_data(as_text=True)
    r = ana.post(CENTRAL, data={"codigo": "x", "dono:pcm-diario": "1"})
    assert r.status_code == 403 and _linhas(setores) == []


def test_mudar_o_dono_muda_quem_ve_sem_marcar(app, logado, com_pcm, setores):   # noqa: F811
    dani, ana = _como(app, DANI), _como(app, ANA)
    assert "pcm-diario" in _cartoes(dani) and "pcm-diario" not in _cartoes(ana)
    r = _salvar(logado, {"pcm-diario": 1})
    assert r.status_code == 303 and r.headers["Location"].endswith("#setor-dos-relatorios")
    assert [(x["tela"], str(x["setor_id"])) for x in _linhas(setores)] == [("relatorios/pcm-diario", "1")]
    assert "1 relatório mudou de setor" in logado.get(CENTRAL).get_data(as_text=True)
    # a Ana (Performance) passa a ver sem marca nenhuma; a Dani (PCM) deixa de ver
    assert "pcm-diario" in _cartoes(ana) and ana.get("/t/relatorios/pcm-diario").status_code == 200
    assert "pcm-diario" not in _cartoes(dani) and dani.get("/t/relatorios/pcm-diario").status_code == 403
    assert "pcm-tarde" in _cartoes(dani)                                     # o resto do PCM segue com ela
    # a Acessos mostra o relatório como DO setor Performance (a caixa presa)
    with app.test_request_context():
        assert "relatorios/pcm-diario" in ST.das_do_setor({"id": 1, "nome": "Performance"})
        assert "relatorios/pcm-diario" in ST.das_do_setor("Performance")     # pelo nome também
        assert "relatorios/pcm-diario" not in ST.das_do_setor({"id": com_pcm, "nome": "PCM"})


def test_salvar_sem_mexer_nao_grava_e_nenhum_setor_tira_de_todos(app, logado, com_pcm, setores):   # noqa: F811
    assert _salvar(logado, {"pcm-diario": com_pcm, "relatorio": 1}).status_code == 303
    assert _linhas(setores) == [] and "Nada mudou" in logado.get(CENTRAL).get_data(as_text=True)
    assert _salvar(logado, {"relatorio": None}).status_code == 303
    assert [(x["tela"], x["setor_id"]) for x in _linhas(setores)] == [("relatorios/relatorio", None)]
    ana = _como(app, ANA)
    assert "relatorio" not in _cartoes(ana) and "relatorio-semanal" in _cartoes(ana)
    html = logado.get(CENTRAL).get_data(as_text=True)                       # o administrador segue vendo
    assert 'data-relatorio="relatorio"' in html
    assert re.search(r'name="dono:relatorio">\s*<option value="" selected>Nenhum setor', html)


def test_codigo_vencido_ou_setor_desconhecido_nao_grava(app, logado, com_pcm, setores):   # noqa: F811
    _salvar(logado, {"pcm-diario": 1}, codigo="codigo-velho")
    assert _linhas(setores) == [] and "O formulário venceu" in logado.get(CENTRAL).get_data(as_text=True)
    _salvar(logado, {"pcm-diario": 999})
    assert _linhas(setores) == [] and "Setor desconhecido" in logado.get(CENTRAL).get_data(as_text=True)


def test_o_setor_renomeado_continua_dono(app, logado, com_pcm, setores):   # noqa: F811
    _salvar(logado, {"pcm-alerta": 1})
    S.renomear(1, "Performance e Dados", app.config, BASE, setores)
    S._CACHE.clear()
    ST.limpar()
    assert "pcm-alerta" in _cartoes(_como(app, ANA))
    html = logado.get(CENTRAL).get_data(as_text=True)
    assert re.search(r'data-relatorio="pcm-alerta".*?<span class="qtd">Performance e Dados</span>', html, re.S)


def test_o_dado_novo_esta_no_catalogo():
    f = next(x for x in catalogo.FATOS if x.id == "decisao_dono_relatorio")
    assert f.livro == "nexus_relatorio_setor · fato_decisao_dono_relatorio" and f.tipo == "sem_medida"
    livro = catalogo.LIVRO_POR_NOME["nexus_relatorio_setor"]
    assert livro.abas == ("fato_decisao_dono_relatorio",) and not livro.no_banco
    assert DR.LIVRO != ST.LIVRO                                              # gravar troca o livro inteiro
