"""Os filtros do Quadro com mais de uma opção, o topo com a exclamação e os chips (Levi, 27/10/2026: "nos filtros também
quero poder escolher mais de uma opção"; "quero o mesmo [a exclamação dos Extintores] para ocultar esse texto enorme").

O que estes testes seguram: `quadro.varios` lê "A|B"; o `filtrar`, as pendentes e as opções aceitam vários valores; a tela
lê a URL repetida (`tipo=MPA&tipo=MPM`) e também o "A|B" que os links das semanas levam; o chip diz quantos foram
escolhidos e deixa as caixas marcadas; os textos longos estão na exclamação e não soltos na página."""
from datetime import date

from nexus.pcm import quadro as Q
from test_pcm_quadro import _banco, _semana_teste


def test_varios_le_o_separador_e_ignora_vazio():
    assert Q.varios("MPA| MPM |") == {"MPA", "MPM"}
    assert Q.varios("") == set() and Q.varios(None) == set()
    assert Q.varios("Corretiva") == {"Corretiva"}


def test_filtrar_com_varios_valores():
    rows = _semana_teste()["rows"]                      # 3 Corretiva, 1 MPA, 2 MPM; 5 da SP Leste 02, 1 da RN Sul 01
    assert len(Q.filtrar(rows, {"tipo": "MPA|MPM"})) == 3
    assert len(Q.filtrar(rows, {"tipo": "Corretiva|MPA"})) == 4
    assert len(Q.filtrar(rows, {"equipe": "SP Leste 02|RN Sul 01"})) == 6
    assert len(Q.filtrar(rows, {"tipo": "MPA|MPM", "equipe": "RN Sul 01"})) == 1      # os filtros somam
    assert Q.filtrar(rows, {"tipo": "Inexistente"}) == []


def test_pendentes_e_opcoes_com_varios_valores():
    sem = _semana_teste()
    assert len(Q.filtrar_pendentes(sem["pendentes"], {"tipo": "MPM|Corretiva"})) == 2
    assert [p["os_id"] for p in Q.filtrar_pendentes(sem["pendentes"], {"equipe": "RN Sul 01|Outra"})] == ["6"]
    # a opção escolhida fica na lista mesmo com 0 (a tela não esconde o filtro que vale), cada uma das escolhidas
    op = Q.opcoes(sem["rows"], {"tipo": "MPA|Inexistente"})["tipo"]
    assert ("Inexistente", 0) in op and ("MPA", 1) in op
    # o filtro não conta a si mesmo: com o tipo escolhido, as outras opções de tipo seguem na lista
    assert {v for v, _ in op} >= {"Corretiva", "MPA", "MPM"}


def test_tela_le_a_url_repetida_e_o_valor_dos_links(app, logado, tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "hoje", lambda: date(2026, 10, 7))
    app.config.update(NEXUS_PCM_FONTE=str(_banco(tmp_path)), NEXUS_PCM_TRABALHO=str(tmp_path / "trab"))
    html = logado.get("/t/pcm/quadro?semana=2026-W41&tipo=MPA&tipo=MPM").get_data(as_text=True)
    assert html.count("data-cartao=") == 3
    assert "2 escolhidos" in html and 'class="q-ms q-ms--ativo"' in html
    assert 'name="tipo" value="MPA" checked' in html and 'name="tipo" value="MPM" checked' in html
    # os links das semanas levam os filtros como "MPA|MPM", e a tela os lê do mesmo jeito
    assert "tipo=MPA%7CMPM" in html
    html = logado.get("/t/pcm/quadro?semana=2026-W41&tipo=MPA%7CMPM").get_data(as_text=True)
    assert html.count("data-cartao=") == 3


def test_tela_tem_a_exclamacao_e_a_busca_embaixo(app, logado, tmp_path, monkeypatch):
    monkeypatch.setattr(Q, "hoje", lambda: date(2026, 10, 7))
    app.config.update(NEXUS_PCM_FONTE=str(_banco(tmp_path)), NEXUS_PCM_TRABALHO=str(tmp_path / "trab"))
    html = logado.get("/t/pcm/quadro").get_data(as_text=True)
    topo = html.split('class="q-barra"', 1)[0]
    # os textos longos estão na exclamação (o details do aviso), não num parágrafo solto antes dos filtros
    assert 'class="hs-aviso"' in topo and "Como o Quadro lê e conta a semana" in topo
    assert "sábado 03/10 00:00" in topo and 'class="pcm-fonte"' not in topo
    # a busca vem depois dos chips, sozinha
    barra = html.split('class="q-barra"', 1)[1].split("</form>", 1)[0]
    assert barra.index('data-ms') < barra.index('name="q"')
