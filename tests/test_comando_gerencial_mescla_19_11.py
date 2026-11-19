"""Visão gerencial (teste): o cabeçalho do cliente que sobe e encolhe no scroll, e a usina com o Nexus Insights junto da nota
do contrato (19/11/2026).

Levi, 19/11/2026: "na telinha do cliente [...] quando desce um scroll, aparece a animação dessas informações do cliente indo
para cima e diminuindo. Então, ficaria Athon, tantos MWp pico, 10 usinas, tantos por mês, e os cardzinhos também iriam
subir" e "clicando na usina, eu queria que a informação fosse uma mescla do que a gente tem agora com o que a gente tem no
Nexus Insights". Usinas e insights inventados; nada lê o banco."""
from pathlib import Path

import pytest

from nexus.torres import comando as TC

from test_campo_responsaveis import tela  # noqa: F401  (tela é fixture)
from test_campo_visao import banco  # noqa: F401  (banco é fixture)

RAIZ = Path(__file__).resolve().parents[1]
JS = (RAIZ / "nexus" / "static" / "gerencial.js").read_text(encoding="utf-8")
CSS = (RAIZ / "nexus" / "static" / "gerencial.css").read_text(encoding="utf-8")
URL = "/t/comando/visao-gerencial/usina/{}/insights.json"


def _ins(id_, regra, sev, usina="Usina Um", **kw):
    return dict({"id": id_, "regra": regra, "sev": sev, "usina": usina, "titulo": f"{regra} em {usina}", "torre": "cos",
                 "evid": ["prova 1", "prova 2"], "acao": "Fazer a coisa certa", "link": "/t/cos/ronda"}, **kw)


@pytest.fixture
def vivos(monkeypatch):
    """O `_usinas_montadas` com os insights vivos de duas usinas (o que o motor do Nexus Insights apontou agora)."""
    viv = {7: [_ins("R11:7", "R11", "atencao", torre="campo"), _ins("R03:7:a", "R03", "critico"),
               _ins("R07:7", "R07", "info", torre="hseq")],
           8: [_ins("R05:8", "R05", "critico", usina="Usina Oito")]}
    monkeypatch.setattr(TC, "_usinas_montadas", lambda: {"linhas": [], "avisos": [], "vivos": viv,
                                                         "insights_calculando": False})
    monkeypatch.setattr(TC.ES, "atual", lambda: {"R11:7": {"evento": "assumiu", "por": "Pessoa Teste", "quando_txt": "19/11"}})
    monkeypatch.setattr(TC.PD, "atual", lambda: {})
    return viv


def test_a_usina_traz_os_insights_vivos_dela_do_mais_grave_para_o_menos(tela, logado, vivos):
    r = logado.get(URL.format(7))
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    d = r.get_json()
    assert d["ok"] and not d["calculando"] and d["janela"] == "agora"
    assert [i["regra"] for i in d["insights"]] == ["R03", "R11", "R07"]           # crítico, atenção, informativo
    assert d["contas"] == {"critico": 1, "atencao": 1, "info": 1}
    i = d["insights"][0]
    assert i["sev_rot"] == "Crítico" and i["sev_tom"] == "critico" and i["regra_nome"] and i["torre_nome"]
    assert i["evid"] == ["prova 1", "prova 2"] and i["acao"] == "Fazer a coisa certa"
    assert i["abrir"].endswith("/t/comando/insights?abrir=R03%3A7%3Aa#ins-R03-7-a") and i["link"].endswith("/t/cos/ronda")
    # com quem está: o assumido diz com quem; o novo, que ninguém foi avisado
    assert d["insights"][1]["com_quem"] == "Com Pessoa Teste" and i["com_quem"] == "Ninguém avisado"


def test_a_usina_sem_insight_vivo_e_a_conta_ainda_calculando(tela, logado, vivos, monkeypatch):
    d = logado.get(URL.format(99)).get_json()
    assert d["ok"] and d["insights"] == [] and d["contas"] == {"critico": 0, "atencao": 0, "info": 0}
    monkeypatch.setattr(TC, "_usinas_montadas", lambda: {"linhas": [], "avisos": [], "vivos": {},
                                                         "insights_calculando": True})
    assert logado.get(URL.format(7)).get_json()["calculando"] is True


def test_o_cliente_nao_le_os_insights_da_visao_gerencial(tela, logado, vivos):
    with logado.session_transaction() as s:
        s["via"] = "cliente"
    assert logado.get(URL.format(7)).status_code in (302, 403)


def test_a_tela_da_usina_pede_os_insights_e_mostra_os_dois_lados():
    assert "data-insights" in (RAIZ / "nexus/torres/comando/templates/comando/gerencial.html").read_text(encoding="utf-8")
    assert "function capaUsina" in JS and "Nexus Insights" in JS and "insights.json" not in JS    # o endereço vem da página
    assert "vg-ins" in CSS and "Abrir no Nexus Insights" in JS and "O que a regra viu" in JS and "O que fazer" in JS


def test_o_cabecalho_do_cliente_sobe_e_encolhe_no_scroll():
    assert "vg-barra" in CSS and "vg-cards" in CSS and "position:sticky" in CSS.replace(" ", "")
    assert "function encolher" in JS and "addEventListener(\"scroll\"" in JS
    # o que vai para a barra: o nome, os MWp, as usinas, o valor por mês e os cartões
    for marca in ("data-vg-voa=\"nome\"", "data-vg-voa=\"mwp\"", "data-vg-voa=\"leg\"", "data-vg-card"):
        assert marca in JS, marca


def test_o_titulo_do_insight_perde_o_nome_da_usina_que_ja_esta_no_alto(tela, logado, vivos):
    vivos[7][0]["titulo"] = "Usina Um: sem ronda há 22 dias"
    d = logado.get(URL.format(7)).get_json()
    assert next(i for i in d["insights"] if i["regra"] == "R11")["titulo"] == "sem ronda há 22 dias"
    assert next(i for i in d["insights"] if i["regra"] == "R03")["titulo"] == "R03 em Usina Um"   # sem o prefixo, fica


# ── a usina do insight pelo id, não só pelo nome (19/11/2026, conferindo a mescla com o dado real) ──────────────────────
def test_o_insight_leva_o_id_da_usina_quando_a_regra_sabe():
    """Conferindo a mescla contra a tela do Nexus Insights, 142 de 144 usinas batiam: os 3 insights da Macaíba 1 caíam em
    outra usina de mesmo nome no cadastro (a ligação era só pelo nome, e o último homônimo vencia). As regras que sabem o
    id da usina passam a gravá-lo."""
    from nexus.comando import regras as RG
    assert RG._insight("R11", "96", "atencao", "t", [], "a", "Usina Um", usina_id="96")["usina_id"] == 96
    assert RG._insight("R03", "x", "critico", "t", [], "a", "Usina Um")["usina_id"] is None
    assert RG._insight("R11", "x", "critico", "t", [], "a", "Usina Um", usina_id="lixo")["usina_id"] is None
    r11 = RG.r11_sem_ronda([{"usina": "Usina Um", "usina_id": 96, "dias": 16}])
    r13 = RG.r13_chamado_parado({43: {"lista": [{"situacao": "aberto", "status": RG.FABRICANTE, "dias": 30, "os": "17311"}]}},
                                lambda uid: "Usina Dois")
    assert r11[0]["usina_id"] == 96 and r13[0]["usina_id"] == 43


def test_a_ligacao_do_insight_prefere_o_id_e_so_cai_no_nome_sem_ele():
    from nexus.comando import usinas as CU
    nome_para_uid = {"usina um": 27}                         # o homônimo que vence no nome
    ins = [{"id": "R11:96", "usina": "Usina Um", "usina_id": 96}, {"id": "R03:a", "usina": "Usina Um"},
           {"id": "R13:1", "usina": "Usina Um", "usina_id": 555}]          # id fora do cadastro: cai no nome
    assert CU.uid_do_insight(ins[0], nome_para_uid, {27, 96}) == 96
    assert CU.uid_do_insight(ins[1], nome_para_uid, {27, 96}) == 27
    assert CU.uid_do_insight(ins[2], nome_para_uid, {27, 96}) == 27
    assert CU.insights_por_usina(ins, {}, nome_para_uid, {27, 96}) == {96: 1, 27: 2}


# ── o 2º retorno do Levi, no mesmo dia ───────────────────────────────────────────────────────────────────────────────────
def test_a_barra_do_cliente_e_uma_animacao_de_tempo_e_nao_um_quadro_preso_ao_scroll():
    """Levi, 19/11/2026, com a foto da barra parada no meio: "dá uma bugada, não está soando como animação!". O voo era
    preso à posição do scroll: parando no meio, os dois textos ficavam um em cima do outro. Agora a barra abre quando a
    página passa de ABRE px e fecha abaixo de FECHA px, e o voo é uma animação de tempo que sempre termina."""
    assert "ABRE = " in JS and "FECHA = " in JS and ".animate(" in JS
    assert "/ CURSO" not in JS                                   # nada mais calculado pela fração do scroll
    assert "vg-barra--aberta" in CSS and "vg-cli-aberta" in CSS  # o estado final é de classe; a animação só leva até ele


def test_as_explicacoes_de_cada_nivel_moram_no_ponto_de_exclamacao_ao_lado_do_nome():
    """Levi, 19/11/2026, com a foto do texto "Cada bloco é uma usina [...]": "essas informações poderiam estar em uma
    exclamação ao lado do nome". O "!" amarelo é o padrão do Nexus (`_explica.html`); vale para os três níveis."""
    assert JS.count("explica(") >= 4 and 'class="gc-explica' in JS and "gc-explica-bt" in JS
    assert "vg-nota" not in JS and "vg-nota" not in CSS
    for texto in ("Cada bloco é uma usina", "O anel reparte", "é uma proposta em teste", "Os insights</b> são os do Nexus Insights"):
        assert texto in JS, texto
