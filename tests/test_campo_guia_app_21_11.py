"""O Guia do App de Campo na Usinas 360° (21/11/2026). Levi, pelo chat do App de Campo: "guia do app de campo. E pode
ficar no Usina 360 com nova sessão mesmo [...] perguntas que eu recebo recorrentemente [...] vai aparecer as telas e vai
aparecer todas as regras ali embaixo"; "se o tema do Nexus estiver claro, vai aparecer o tema claro do celular; se
estiver escuro, o tema escuro do celular". E, em 22/11, a busca no alto, a separação por tema e o texto curto ("para quem
tem pouco tempo, porém busca entender").

O que estes testes seguram: a tela é a última da Usinas 360°; a busca, os chips de tema (Todos primeiro, na ordem em
que os temas aparecem) e a lista por tema; cada pergunta com o resumo, as telas num iframe que já nasce no tema do Nexus,
"Todas as regras (N)" fechado com a fonte separada e os casos; o "incerto" só para o administrador e o PCM; a pergunta
sem tela diz que elas vêm depois; sem o guia, a página abre e diz. Guia de mentira; nada de nome real."""
import json

import pytest

from nexus.campo import guia_app as G
from nexus.torres.campo import TORRE

URL = "/t/campo/guia-app"
GUIA = {
    "versao": 1, "atualizado_em": "2026-11-22", "app": "v366 no ar",
    "perguntas": [
        {"id": "pontos", "titulo": "Como os pontos são calculados?", "tema": "Pontos", "publico": ["técnico"],
         "resumo": ["Tarefa vale a nota menos 60.", "Só as 70 melhores do ciclo somam."],
         "regras": ["Ciclo: do dia 20 ao dia 19. [fa:10-12; v362]", "Nota de 0 a 100 pela programação."],
         "casos": ["Tarefa pausada não tem ponto."], "incerto": ["As configurações PLACAR_* podem mudar os valores."],
         "telas": [{"arquivo": "telas/pontos-1.html", "legenda": "O ciclo e a posição"}]},
        {"id": "justificar", "titulo": "Como o técnico justifica não ter feito uma tarefa?", "tema": "PCM e programação",
         "publico": ["técnico", "supervisor"], "resumo": ["A justificativa vai ao PCM na hora."],
         "regras": ["O motivo é escolhido numa lista. [ch:200]"], "casos": [], "incerto": [], "telas": []},
        {"id": "ronda", "titulo": "Ronda: curta ou longa?", "tema": "Pontos", "publico": ["técnico"],
         "resumo": ["A longa vale mais."], "regras": [], "casos": [], "incerto": [], "telas": []},
    ],
}


@pytest.fixture
def guia(tmp_path, monkeypatch):
    pasta = tmp_path / "guia-app"
    (pasta / "telas").mkdir(parents=True)
    (pasta / "guia.json").write_text(json.dumps(GUIA, ensure_ascii=False), encoding="utf-8")
    (pasta / "telas" / "pontos-1.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(G, "PASTA", pasta)
    G.limpar()
    yield pasta
    G.limpar()


def _cliente(app, admin=False, setor=None, tema=None):
    c = app.test_client()
    with c.session_transaction() as s:
        s["logado"] = True
        s["admin"] = admin
    if tema:
        c.set_cookie("nexus_tema", tema)
    return c


def test_a_tela_mora_na_usinas_360_por_ultimo():
    assert TORRE.telas[-1].id == "guia-app"
    assert TORRE.telas[-1].nome == "Guia do App de Campo"


def test_a_pagina_tem_a_busca_os_temas_e_a_lista_por_tema(app, guia):
    html = _cliente(app, admin=True).get(URL).get_data(as_text=True)
    assert 'data-guia-busca' in html and 'type="search"' in html
    chips = html.split('class="gu-chips"', 1)[1].split("</div>", 1)[0]
    assert chips.index(">Todos<") < chips.index(">Pontos<") < chips.index(">PCM e programação<")
    nav = html.split('class="gu-nav"', 1)[1].split("</nav>", 1)[0]
    assert nav.index("Pontos") < nav.index("Como os pontos") < nav.index("Ronda: curta") < nav.index("PCM e programação")
    assert 'href="#p-pontos"' in nav
    assert html.count('class="gu-pergunta"') == 3
    assert "data-guia-conta>3</b> perguntas" in html


def test_cada_pergunta_tem_o_resumo_as_telas_e_as_regras_fechadas(app, guia):
    html = _cliente(app, admin=True).get(URL).get_data(as_text=True)
    p = html.split('id="p-pontos"', 1)[1].split('id="p-', 1)[0]
    assert "Tarefa vale a nota menos 60." in p and "Só as 70 melhores do ciclo somam." in p
    assert '<iframe' in p and 'guia-app/telas/pontos-1.html?tema=escuro' in p and 'loading="lazy"' in p
    assert "O ciclo e a posição" in p
    assert "<summary>Todas as regras (2)</summary>" in p and "<details class=\"gu-regras\" open" not in p
    assert 'Ciclo: do dia 20 ao dia 19. <span class="gu-fonte">fa:10-12; v362</span>' in p
    assert "Nota de 0 a 100 pela programação." in p
    assert "Tarefa pausada não tem ponto." in p


def test_o_iframe_nasce_no_tema_do_nexus(app, guia):
    html = _cliente(app, admin=True, tema="claro").get(URL).get_data(as_text=True)
    assert "pontos-1.html?tema=claro" in html
    assert "guia-app.js" in html


def test_a_pergunta_sem_tela_diz_que_elas_vem_depois(app, guia):
    html = _cliente(app, admin=True).get(URL).get_data(as_text=True)
    p = html.split('id="p-justificar"', 1)[1].split('id="p-', 1)[0]
    assert "As telas desta pergunta chegam na próxima leva." in p and "<iframe" not in p


def test_a_busca_e_sem_acento(app, guia):
    html = _cliente(app, admin=True).get(URL).get_data(as_text=True)
    p = html.split('id="p-justificar"', 1)[0].rsplit("<article", 1)[1]
    busca = html.split('id="p-justificar"', 1)[1].split(">", 1)[0]
    assert "data-busca=" in busca and "nao ter feito" in busca and "justificativa" in busca and "não" not in busca
    assert p  # a pergunta anterior existe


def test_o_incerto_so_para_o_administrador_e_o_pcm(app, guia, monkeypatch):
    html = _cliente(app, admin=True).get(URL).get_data(as_text=True)
    assert "As configurações PLACAR_* podem mudar os valores." in html and 'class="gu-regras gu-incerto"' in html
    from nexus.torres.campo import guia_tela
    monkeypatch.setattr(guia_tela, "_ve_o_incerto", lambda: False)
    html = _cliente(app, admin=True).get(URL).get_data(as_text=True)
    assert "PLACAR_*" not in html and "gu-incerto" not in html


def test_sem_o_guia_a_pagina_abre_e_diz(app, tmp_path, monkeypatch):
    monkeypatch.setattr(G, "PASTA", tmp_path / "nada")
    G.limpar()
    resp = _cliente(app, admin=True).get(URL)
    assert resp.status_code == 200
    assert "O guia ainda não chegou a este Nexus" in resp.get_data(as_text=True)
    G.limpar()


def test_o_guia_de_verdade_no_repositorio_abre_e_nao_tem_tela_faltando():
    G.limpar()
    g = G.carregar()
    if g["erro"]:
        pytest.skip("o pacote do App ainda não foi importado")
    for p in g["perguntas"]:
        for t in p["telas"]:
            assert (G.PASTA / t["arquivo"]).is_file(), t["arquivo"]


def test_os_temas_seguem_a_ordem_que_o_pacote_manda(tmp_path, monkeypatch):
    """O pacote de 22/11 traz `temas` (a ordem dos chips); tema que aparece numa pergunta e falta na lista vai ao fim."""
    pasta = tmp_path / "guia-app"
    pasta.mkdir()
    guia = dict(GUIA, temas=["PCM e programação", "Pontos"])
    guia["perguntas"] = GUIA["perguntas"] + [dict(GUIA["perguntas"][2], id="extra", tema="Chamados")]
    (pasta / "guia.json").write_text(json.dumps(guia, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(G, "PASTA", pasta)
    G.limpar()
    assert [nome for nome, _ in G.carregar()["temas"]] == ["PCM e programação", "Pontos", "Chamados"]
    G.limpar()


def test_acima_da_pergunta_so_o_nome_do_setor(app, guia):
    """21/11/2026, Levi, vendo a tela no ar: "só quero o nome do setor em verde grid" (sem o público ao lado)."""
    html = _cliente(app, admin=True).get(URL).get_data(as_text=True)
    assert '<p class="gu-tema">Pontos</p>' in html
    assert "· técnico" not in html
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "guia-app.css").read_text(encoding="utf-8")
    assert ".gu-nav-tema{" in css and "color:var(--verde-texto)" in css.split(".gu-nav-tema{", 1)[1].split("}", 1)[0]
