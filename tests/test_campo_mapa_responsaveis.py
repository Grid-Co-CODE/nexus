"""O mapa das usinas na Visão geral (18/10/2026, Levi: "Para o mapa podemos usar o IBGE como a performance faz";
decisões dele: Lista | Mapa na Visão geral, a cor do ponto pelo bloco clicado, o clique abre o resumo da usina ao lado,
só as usinas). A coordenada é campo sensível do cadastro e nunca vira texto: o servidor desenha. Coordenadas inventadas."""
import re

import pytest
from test_campo_responsaveis import _com_manut, manut, tela  # noqa: F401  (manut e tela são fixtures)
from test_campo_visao import banco  # noqa: F401  (fixture)

from nexus.campo import mapa_responsaveis as MR

# coordenadas com casas incomuns: se alguma aparecer no texto da tela, o teste acha
COORD = {"1": (-21.123457, -47.987653, "SP"), "2": (-25.432187, -49.276541, "PR")}


def _u(uid, nome, nivel="ok", manut_nivel="ok"):
    return {"usina_id": uid, "usina": nome, "nivel": nivel, "perf": {"nivel": nivel}, "manut": {"nivel": manut_nivel},
            "acomp": {"nivel": "ok"}}


def test_o_desenho_tem_os_pontos_e_nenhuma_coordenada_em_texto():
    d = MR.desenho([_u(1, "A", "critico"), _u(2, "B"), _u(3, "C")], COORD)
    assert [p["usina"] for p in d["pontos"]] == ["B", "A"]            # o crítico por último, desenhado por cima
    assert d["sem_coordenada"] == ["C"] and d["viewbox"].startswith("0 0 1000 ")
    assert {f["sigla"] for f in d["ufs"]} >= {"SP", "PR"}
    texto = repr(d)
    for n in ("123457", "987653", "432187", "276541"):
        assert n not in texto


def test_a_cor_do_ponto_e_a_do_bloco_destacado():
    us = [_u(1, "A", "atencao", manut_nivel="critico")]
    assert MR.desenho(us, COORD, "manut")["pontos"][0]["nivel"] == "critico"
    assert MR.desenho(us, COORD)["pontos"][0]["nivel"] == "atencao"


def test_sem_coordenada_nenhuma_nao_desenha():
    d = MR.desenho([_u(3, "C")], COORD)
    assert d["viewbox"] is None and d["pontos"] == [] and d["sem_coordenada"] == ["C"]


@pytest.fixture
def com_mapa(manut, monkeypatch):  # noqa: F811
    from nexus.performance.clima import usinas as CU
    cad = CU.Cadastro(usinas=[CU.Usina("1", "Altair", "Thopen", "SP", lat=-21.123457, lon=-47.987653),
                              CU.Usina("2", "Brodowski 1", "Thopen", "SP", lat=-20.987651, lon=-47.661237)],
                      sem_coordenada=[CU.Usina("3", "Coração 1", "Thopen", "SC")], fora_do_brasil=[], em_operacao=3)
    monkeypatch.setattr(CU, "do_app", lambda: cad)
    MR.limpar()
    yield manut
    MR.limpar()


def test_lista_ou_mapa_na_visao_geral(com_mapa, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&ver=mapa").get_data(as_text=True)
    assert 'aria-current="page">Mapa</a>' in html and html.count('class="cr-mapa-p ') == 2
    assert "Coração 1" in html.split("Sem coordenada no cadastro")[1][:300]
    for n in ("123457", "987653", "987651", "661237"):
        assert n not in html                                                # a coordenada nunca vira texto
    assert 'class="cr-gr-lin' not in html                                   # o mapa no lugar da lista
    lista = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert 'aria-current="page">Lista</a>' in lista and 'id="u-2"' in lista


def test_o_clique_no_ponto_abre_o_resumo(com_mapa, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&ver=mapa&usina=2").get_data(as_text=True)
    lado = html[html.index('class="cr-mapa-lado"'):]
    assert "Brodowski 1" in lado and "tarefa atrasada" in lado and "#u-2" in lado
    assert "cr-mapa-p--sel" in html


def test_o_ponto_na_cor_do_bloco_clicado(com_mapa, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&ver=mapa&bloco=manut").get_data(as_text=True)
    nivel = {"critico": "critico", "atencao": "alerta", "ok": "ok"}[_com_manut()["Brodowski 1"]["manut"]["nivel"]]
    assert re.search(rf'cr-mapa-p cr-mapa-p--{nivel}[^"]*"[^>]*><title>Brodowski 1</title>', html)


def test_sem_o_cadastro_o_mapa_avisa(manut, logado):  # noqa: F811
    MR.limpar()
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&ver=mapa").get_data(as_text=True)
    assert "O mapa precisa do cadastro" in html and "<svg" not in html.split('class="cr-mapa"')[1][:400]
