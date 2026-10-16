"""Relatórios → Central de emissão (13/10/2026). Levi: "Criador de relatório e relatório semanal vai para a central de
emissão no Nexus > Relatórios. Ficará filtrado no setor da pessoa, caso a pessoa seja administradora aparece todos os
relatórios. Aí a pessoa escolhe que tipo de relatório ela quer! Sai da parte de Performance!" E, no mesmo pedido, o
relatório novo "Potência Ativa dos Inversores".

Provas: os relatórios estão no mapa na torre Relatórios e saíram da Performance (menu e endereço antigo, que leva ao
novo); o menu de Relatórios tem só a Central, que acende com o relatório aberto (no servidor e no porta.js); o
administrador vê todos os cartões; os três são DO setor Performance (Levi: "Potência ativa faz parte da performance!",
"Esses dois são do setor performance"), que os vê sem marcar; outro setor vê os marcados e a Central sem marcá-la; a
marca de antes (da Performance) vale para o relatório daqui. Nos testes, a Ana é da Performance e a Bia de um setor
chamado "Administrador" (um setor como os outros). O banco é o falso do test_campo_visao; nada vai à rede."""
import pytest
from test_campo_visao import banco  # noqa: F401  (fixture)
from test_porta_moldura import _cliente, _dados
from test_setor_telas import ANA, BIA, URL, _como, _linhas, _salvar, _sem_copias, setores  # noqa: F401  (fixtures)

from nexus.auth import setor_telas as ST
from nexus.performance import porta

RELATORIOS = ("relatorio", "relatorio-semanal", "potencia-ativa")
NOMES = ("Criador de relatório", "Relatório semanal", "Potência Ativa dos Inversores")


def _menu(html: str) -> str:
    return html.split('class="menu"', 1)[1].split("</nav>", 1)[0]


def _torre(menu: str, torre: str) -> str:
    return menu.split(f'data-torre="{torre}"', 1)[1].split("</details>", 1)[0]


def test_os_relatorios_estao_no_mapa_na_torre_relatorios_e_nao_na_performance():
    assert [t.tela for t in porta.da_torre("relatorios")] == list(RELATORIOS)
    assert [t.nome for t in porta.da_torre("relatorios")] == list(NOMES)
    assert not any(t.tela in RELATORIOS for t in porta.da_torre("performance"))
    assert porta.tela_do_caminho("/relatorio/potencia-ativa").tela == "potencia-ativa"


def test_o_administrador_ve_todos_os_relatorios_na_central(logado):
    r = logado.get("/t/relatorios/central")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    for tela, nome in zip(RELATORIOS, NOMES):
        assert f'href="/t/relatorios/{tela}"' in h and nome in h
    assert "Como administrador, você vê todos." in h and "Performance" in h


def test_o_menu_de_relatorios_tem_so_a_central_e_a_performance_perdeu_os_relatorios(logado):
    menu = _menu(logado.get("/t/relatorios/central").get_data(as_text=True))
    rel = _torre(menu, "relatorios")
    assert 'href="/t/relatorios/central" class="com-conteudo" aria-current="page">Central de emissão</a>' in rel
    for nome in NOMES:
        assert nome not in menu
    assert "/t/performance/relatorio" not in _torre(menu, "performance")


def test_o_endereco_antigo_leva_ao_novo_com_o_caminho(logado):
    r = logado.get("/t/performance/relatorio?p=%2Frelatorio")
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/relatorios/relatorio?p=%2Frelatorio")
    r = logado.get("/t/performance/relatorio-semanal")
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/relatorios/relatorio-semanal")


@pytest.mark.parametrize("tela", RELATORIOS)
def test_o_relatorio_aberto_acende_a_central_no_menu_e_no_porta_js(tela):
    h = _cliente().get(f"/t/relatorios/{tela}").get_data(as_text=True)
    assert 'href="/t/relatorios/central" class="com-conteudo" aria-current="page"' in h
    dados = _dados(h)
    por_url = {x["url"]: x for x in dados["telas"]}
    for t in RELATORIOS:
        assert por_url[f"/t/relatorios/{t}"]["menu"] == "/t/relatorios/central"
    assert "menu" not in por_url["/t/performance/noc"]          # as outras acendem o próprio item


def test_o_porta_js_acende_o_item_do_menu_da_tela():
    js = open("nexus/static/porta.js", encoding="utf-8").read()
    assert "var alvo = tela.menu || tela.url;" in js and 'a.getAttribute("href") !== alvo' in js


# ── o setor ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_performance_ve_os_tres_relatorios_sem_marcar_nada(app, setores):
    c = _como(app, ANA)
    r = c.get("/t/relatorios/central")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    for tela in RELATORIOS:
        assert f'href="/t/relatorios/{tela}"' in h
    assert "Aparecem os do setor Performance e os liberados para ele." in h
    assert ">Central de emissão</a>" in _menu(c.get("/").get_data(as_text=True))
    assert c.get("/t/relatorios/potencia-ativa").status_code == 200
    with app.app_context():
        assert ST.das_do_setor("performance") == ST.das_do_setor("Performance") == {f"relatorios/{t}" for t in RELATORIOS}
        # os do PCM (14/10/2026) são do setor PCM: os relatórios (nexus/pcm/relatorios, tests/test_relatorios_pcm.py) e o
        # Acompanhamento (nexus/pcm/acompanhamento, tests/test_pcm_acompanhamento.py)
        # e, desde 16/10/2026, o Gerar a semana e o Quadro da semana (Levi: "administradores e pessoas do setor de PCM
        # conseguir gerar uma programação semanal!", tests/test_pcm_publicar.py)
        assert ST.das_do_setor("PCM") == ({f"relatorios/pcm-{t}" for t in ("diario", "tarde", "semanal", "alerta", "executivo")}
                                          | {"pcm/acompanhamento", "pcm/gerar", "pcm/quadro"})
        # o Gerar e o Quadro têm dois donos: o PCM e os supervisores (Levi, 16/10/2026: "tanto PCM quanto supervisores!
        # Vou criar um setor de Responsáveis UFV"), pelo nome, sem acento nem caixa
        assert ST.das_do_setor("Responsáveis UFV") == ST.das_do_setor("responsaveis ufv") == {"pcm/gerar", "pcm/quadro"}
        assert ST.das_do_setor("") == set()


def test_na_matriz_os_relatorios_da_performance_ficam_marcados_e_o_salvar_nao_grava_decisao_para_eles(app, setores,
                                                                                                         logado):
    h = logado.get(URL + "?setor=1").get_data(as_text=True)
    for tela in RELATORIOS:
        i = h.index(f"{dict(zip(RELATORIOS, NOMES))[tela]}</label>")
        assert "data-do-setor checked disabled" in h[i - 160:i] and "do setor" in h[i:i + 200], tela
    assert _salvar(logado, 1, ["cos/mesa"]).status_code == 303
    assert {x["tela"] for x in _linhas(setores) if x["setor_id"] in (1, "1")} == {"cos/mesa"}
    # mesmo que a caixa presa venha no formulário, não vira decisão nem erro
    assert _salvar(logado, 1, ["cos/mesa", "relatorios/potencia-ativa"]).status_code == 303
    assert not any(x["tela"].startswith("relatorios/") for x in _linhas(setores))


def test_o_setor_ve_so_os_relatorios_marcados_e_a_central_sem_marcar(app, setores, logado):
    assert _salvar(logado, 2, ["relatorios/relatorio-semanal"]).status_code == 303
    c = _como(app, BIA)
    r = c.get("/t/relatorios/central")
    assert r.status_code == 200
    h = r.get_data(as_text=True)
    assert 'href="/t/relatorios/relatorio-semanal"' in h
    assert 'href="/t/relatorios/relatorio"' not in h and 'href="/t/relatorios/potencia-ativa"' not in h
    assert "Aparecem os do setor Administrador e os liberados para ele." in h
    assert ">Central de emissão</a>" in _menu(c.get("/").get_data(as_text=True))
    assert c.get("/t/relatorios/relatorio-semanal").status_code == 200
    assert c.get("/t/relatorios/potencia-ativa").status_code == 403


def test_setor_sem_relatorio_nao_ve_a_central(app, setores, logado):
    assert _salvar(logado, 2, ["cos/mesa"]).status_code == 303
    c = _como(app, BIA)
    assert 'data-torre="relatorios"' not in _menu(c.get("/").get_data(as_text=True))
    assert c.get("/t/relatorios/central").status_code == 403


def test_a_marca_de_antes_da_performance_vale_para_o_relatorio_daqui():
    d = [{"decidida_em": "2026-10-12T10:00:00Z", "setor_id": 1, "tela": "performance/relatorio", "liberada": True},
         {"decidida_em": "2026-10-12T10:00:00Z", "setor_id": 1, "tela": "performance/relatorio-semanal",
          "liberada": True},
         # a decisão mais nova, já com o nome novo, ganha
         {"decidida_em": "2026-10-13T10:00:00Z", "setor_id": 1, "tela": "relatorios/relatorio-semanal",
          "liberada": False}]
    assert ST.vigentes(d) == {1: {"relatorios/relatorio"}}


def test_quem_tinha_o_relatorio_na_performance_continua_vendo(app, setores, monkeypatch):
    lido = ST._ler_banco

    def com_a_marca_antiga(base, sessao):
        return lido(base, sessao) + [{"decidida_em": "2026-10-12T10:00:00Z", "data_id": 20261012, "setor_id": 2,
                                      "tela": "performance/relatorio", "liberada": True, "decidida_por_hmac": "",
                                      "origem": "tela"}]
    monkeypatch.setattr(ST, "_ler_banco", com_a_marca_antiga)
    ST.limpar()
    c = _como(app, BIA)
    h = c.get("/t/relatorios/central").get_data(as_text=True)
    assert 'href="/t/relatorios/relatorio"' in h and 'href="/t/relatorios/relatorio-semanal"' not in h


def test_a_central_entra_com_qualquer_relatorio(app):
    with app.app_context():
        assert ST.com_as_de_fora({"relatorios/potencia-ativa", "cos/mesa"}) == {
            "relatorios/potencia-ativa", "relatorios/central", "cos/mesa"}
        assert ST.com_as_de_fora({"cos/mesa"}) == {"cos/mesa"}
