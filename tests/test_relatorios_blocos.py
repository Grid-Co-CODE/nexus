"""A estrutura única da Central de emissão (14/10/2026, Levi: "Use a mesma estrutura do print 1 para todos os
relatórios de todos os setores e aí vai ficar filtrado por setor" e, para o PCM, "um bloco lateral ... com o título
'Relatórios Padrão PCM' e abaixo terá um bloco 'Relatório Gerencial PCM' onde terá os três tipos de relatório"): os
blocos à esquerda em todas as telas da Central, cada setor vendo os seus, o aberto aceso, e os da plataforma na coluna
da direita. Pessoas e setores de mentira, no banco falso do test_campo_visao."""
import re

from test_campo_visao import banco  # noqa: F401  (fixture)
from test_relatorios_dono_setor import DANI, _sem_copias, com_pcm  # noqa: F401  (fixtures)
from test_setor_telas import ANA, _como, setores  # noqa: F401  (fixtures)

from nexus.torres.relatorios import BLOCOS, TORRE

CENTRAL = "/t/relatorios/central"
TITULOS = ["Relatórios Padrão PCM", "Relatório Gerencial PCM", "Relatórios Performance"]


def _blocos(html: str) -> list[str]:
    return re.findall(r'<h2 id="rp-b-[^"]+">([^<]+)</h2>', html)


def _acesos(html: str) -> list[str]:
    return re.findall(r'class="rp-tipo on" data-relatorio="[^"]+" href="([^"]+)"', html)


def test_todo_relatorio_da_central_esta_num_bloco_uma_vez_so():
    itens = [(it["tela"], it.get("sub", "")) for b in BLOCOS for it in b["itens"]]
    assert len(itens) == len(set(itens))
    assert {t for t, _ in itens} == {t.id for t in TORRE.telas if t.dentro_de == "central"}
    assert [b["titulo"] for b in BLOCOS] == TITULOS
    assert [it["sub"] for it in BLOCOS[1]["itens"]] == ["interno", "cliente", "semana"]


def test_o_administrador_ve_os_tres_blocos_na_ordem_em_toda_tela_da_central(logado):
    for url in (CENTRAL, "/t/relatorios/pcm-diario", "/t/relatorios/pcm-executivo?tipo=semana",
                "/t/relatorios/relatorio-semanal"):
        assert _blocos(logado.get(url).get_data(as_text=True)) == TITULOS, url
    assert "Escolha o relatório na coluna ao lado" in logado.get(CENTRAL).get_data(as_text=True)


def test_cada_setor_ve_so_os_blocos_dele(app, com_pcm, setores):   # noqa: F811
    dani, ana = _como(app, DANI), _como(app, ANA)
    assert _blocos(dani.get(CENTRAL).get_data(as_text=True)) == TITULOS[:2]
    assert _blocos(dani.get("/t/relatorios/pcm-executivo?tipo=cliente").get_data(as_text=True)) == TITULOS[:2]
    assert _blocos(ana.get(CENTRAL).get_data(as_text=True)) == TITULOS[2:]
    assert ana.get("/t/relatorios/pcm-executivo?tipo=cliente").status_code == 403


def test_o_relatorio_aberto_acende_o_item_dele(logado):
    assert _acesos(logado.get("/t/relatorios/pcm-tarde").get_data(as_text=True)) == ["/t/relatorios/pcm-tarde"]
    assert _acesos(logado.get("/t/relatorios/pcm-executivo?tipo=cliente").get_data(as_text=True)) == \
        ["/t/relatorios/pcm-executivo?tipo=cliente"]
    assert _acesos(logado.get("/t/relatorios/pcm-executivo").get_data(as_text=True)) == \
        ["/t/relatorios/pcm-executivo?tipo=interno"]                            # sem tipo: o Interno Grid, como no painel
    assert _acesos(logado.get(CENTRAL).get_data(as_text=True)) == []


def test_o_relatorio_da_plataforma_vem_na_coluna_da_direita(logado):
    html = logado.get("/t/relatorios/potencia-ativa").get_data(as_text=True)
    assert _acesos(html) == ["/t/relatorios/potencia-ativa"]
    assert 'class="rp-dir rp-dir--moldura"' in html and 'id="porta"' in html
    # sem título do Nexus em cima da tela da plataforma (o 2º cabeçalho saiu em 13/10/2026)
    assert 'class="titulo-pagina"' not in html and "gc-eyebrow" not in html.split('class="conteudo', 1)[1]
    # as telas da plataforma nas outras torres seguem na moldura de sempre, sem os blocos
    html = logado.get("/t/performance/noc").get_data(as_text=True)
    assert 'id="porta"' in html and "rp-tela" not in html
