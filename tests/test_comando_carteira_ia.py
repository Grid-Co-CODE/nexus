"""A Nexus IA da carteira e a caixa na tela (16/11/2026). Retornos do time: "Eu queria a IA fora do ambiente da usina.
Por exemplo... Agora eu quero ver todos os chamados em aberto e correlacionar com as usinas com baixa disponibilidade e
performance" e "Tem que ser a caixa de texto para a IA sem abrir uma janela". Levi: "libera para todos e só no Comando ›
Usinas, pode construir".

Nada vai à rede: as rotas usam o `IA.perguntar` dublado; o dossiê é montado com linhas inventadas."""
import re
from datetime import datetime

from test_campo_responsaveis import tela  # noqa: F401  (tela é fixture)
from test_campo_visao import banco  # noqa: F401  (banco é fixture)

from nexus.comando import carteira_ia as CI
from nexus.comando import ia as IA

AGORA = datetime(2026, 11, 16, 9, 30)


def _linha(uid, nome, **k):
    base = {"usina_id": uid, "usina": nome, "cliente": "Renogrid", "cluster": "MT", "tipologia": "Fixo", "mwp": 2.5,
            "atingimento": 84.9, "pr": 63.07, "pr_meta": 87.6, "os_abertas": 5, "os_atrasadas": 1,
            "conformidade": [["1 extintor vencido", "critico"]], "estado_rot": "Normal", "responsavel": "Fulano Responsável"}
    return dict(base, **k)


def _fontes():
    return {"disps": {"2026-11": {1: {"disp": 0.0, "h_perdidas": 180.0}, 2: {"disp": 70.19, "h_perdidas": 53.7}},
                      "2026-10": {1: {"disp": 97.5}}},
            "cos": {2: [{"inicio": "2026-11-10T08:00:00", "geracao_parou": "1"},
                        {"inicio": "2026-11-11T08:00:00", "geracao_parou": "0"},
                        {"inicio": "2026-10-01T08:00:00", "geracao_parou": "1"}]},
            "chamados": {1: [{"os": "17129", "situacao": "aberto", "fabricante": "SolarEdge", "componente": "Inversor",
                              "data_id_abertura": "20260810", "equipamento_id": "77", "status": "Aguardando retorno"},
                             {"os": "17000", "situacao": "finalizado", "fabricante": "SolarEdge"}]},
            "nomes_equip": {77: "Inversor 1.1"},
            "manutencao": {1: {"os_nao_iniciadas": [{"os": 1, "urgente": True}, {"os": 2, "urgente": False}]}},
            "vivos": {1: [{"sev": "critico"}, {"sev": "atencao"}]}, "avisos": ["o COS (a coluna Agora)"]}


def test_o_dossie_da_carteira_tem_uma_linha_por_usina_e_os_chamados_abertos():
    d = CI.montar([_linha(1, "Colíder 1"), _linha(2, "Colíder 2", atingimento=98.0)], _fontes(), AGORA)
    t = d["texto"]
    assert d["usinas"] == {"Colíder 1": 1, "Colíder 2": 2} and d["os_usina"] == {"17129": 1} and d["n_chamados"] == 1
    assert "## 2. Usinas" in t and "## 3. Chamados de garantia abertos" in t and "## 4. O que ficou de fora" in t
    linhas = [l for l in t.splitlines() if l.startswith("| ")]
    cab = [c.strip() for c in linhas[0].strip("|").split("|")]
    tab = {c[0]: dict(zip(cab, c)) for c in ([x.strip() for x in l.strip("|").split("|")] for l in linhas[2:4])}
    u1, u2 = tab["Colíder 1"], tab["Colíder 2"]
    # a pior disponibilidade em cima (16/11/2026: a IA pulava a usina na tabela em ordem alfabética)
    assert [l.split("|")[1].strip() for l in linhas[2:4]] == ["Colíder 1", "Colíder 2"]
    assert (u1["Disponibilidade de novembro"], u1["Horas paradas"], u1["Disponibilidade de outubro"]) == ("0,0%", "180,0 h", "97,5%")
    assert (u1["OS urgentes não iniciadas"], u1["Chamados abertos"], u1["Chamado mais antigo"]) == ("1", "1", "98 d")
    assert (u1["Fabricantes dos chamados"], u1["Insights abertos"]) == ("SolarEdge", "2 (1 críticos)")
    assert u2["Desligamentos no mês"] == "1" and u2["Chamados abertos"] == "0"   # novembro: 1 com a geração parada
    assert "Chamados de garantia abertos: 1, em 1 usinas" in t
    assert "| 17129 | Colíder 1 | Renogrid | Inversor 1.1 | SolarEdge | Inversor | aberto | 98 dias | Aguardando retorno |" in t
    assert "17000" not in t                                       # o chamado finalizado não entra
    assert "Fulano Responsável" not in t and "Pessoas: não constam" in t
    assert "- o COS (a coluna Agora)" in t


def test_a_usina_citada_pelo_nome_inteiro():
    us = {"Colíder 1": 1, "Colíder 10": 10, "Marabá 200": 60}
    assert CI.usinas_citadas("A Colíder 10 e a marabá 200 caíram.", us) == {"Colíder 10": 10, "Marabá 200": 60}
    # o nome de uma dentro do de outra (a carteira tem a Nova Xavantina e a Nova Xavantina 1)
    nx = {"Nova Xavantina": 219, "Nova Xavantina 1": 50}
    assert CI.usinas_citadas("A Nova Xavantina 1 caiu.", nx) == {"Nova Xavantina 1": 50}
    assert CI.usinas_citadas("A Nova Xavantina 1 e a Nova Xavantina.", nx) == nx


def test_a_acao_leva_as_usinas_e_as_instrucoes_mudam_por_escopo():
    _t, acoes = IA.separar_acoes('Ok.\n<acoes>[{"setor": "Chamados", "acao": "Cobrar a SolarEdge", "os": null, '
                                 '"usinas": ["Colíder 1", 7, " "]}]</acoes>', ["Chamados"])
    assert acoes == [{"setor": "Chamados", "acao": "Cobrar a SolarEdge", "os": None, "usinas": ["Colíder 1"]}]
    assert IA._sistema("D").startswith(IA.INSTRUCOES)
    assert IA._sistema("D", "", CI.INSTRUCOES).startswith(CI.INSTRUCOES) and "CARTEIRA" in CI.INSTRUCOES


def test_a_caixa_esta_na_tela_para_todos(tela, logado):
    """Sem janela e sem o botão do alto: o lugar da caixa no prontuário e na lista; o pedaço abre para quem não é
    administrador, e a pergunta também (a de antes respondia 403)."""
    with logado.session_transaction() as s:
        s["admin"] = False
    p = logado.get("/t/comando/usinas/1").get_data(as_text=True)
    assert 'data-pu-ia="/t/comando/usinas/1/ia?parcial=1"' in p and "/static/comando/ia.js" in p
    assert 'data-pu-jan="/t/comando/usinas/1/ia?parcial=1"' not in p
    h = logado.get("/t/comando/usinas/1/ia?parcial=1")
    assert h.status_code == 200 and 'class="ia ia--embutida"' in h.get_data(as_text=True)
    assert logado.post("/t/comando/usinas/1/ia/perguntar", json={"pergunta": "?", "modelos": []}).status_code == 400
    lista = logado.get("/t/comando/usinas").get_data(as_text=True)
    assert 'data-cmu-ia="/t/comando/usinas/ia"' in lista and "/static/comando/ia.js" in lista
    c = logado.get("/t/comando/usinas/ia").get_data(as_text=True)
    assert 'data-ia-url="/t/comando/usinas/ia/perguntar"' in c and "sobre a carteira inteira" in c
    assert "Chamados abertos × disponibilidade e performance" in c
    # o texto do dossiê da carteira, só para o administrador
    assert logado.get("/t/comando/usinas/dossie-da-carteira.md").status_code == 403


def test_a_pergunta_da_carteira_usa_o_dossie_e_as_instrucoes_dela(tela, logado, monkeypatch, tmp_path):
    logado.application.config.update(NEXUS_DADOS=str(tmp_path))
    visto = {}

    def perguntar(cfg, ids, dossie, pergunta, historico=None, setores=None, meu_setor="", instrucoes=""):
        visto.update(dossie=dossie, instrucoes=instrucoes)
        nome = next(l[2:-2].split(" | ")[0] for l in dossie.splitlines() if l.startswith("| ") and "---" not in l
                    and not l.startswith("| Usina |") and not l.startswith("| OS |"))
        return [{"id": "nemotron", "ok": True, "texto": f"A {nome} pesa mais.", "custo_usd": 0,
                 "acoes": [{"setor": "Chamados", "acao": "Cobrar", "os": None, "usinas": [nome.upper(), "Marte"]}]}]
    monkeypatch.setattr(IA, "perguntar", perguntar)
    r = logado.post("/t/comando/usinas/ia/perguntar", json={"pergunta": "Chamados × disponibilidade", "modelos": ["nemotron"]})
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] and visto["instrucoes"] == CI.INSTRUCOES
    assert visto["dossie"].startswith("# Dossiê da carteira de usinas")
    resp = j["respostas"][0]
    (nome, url), = resp["usinas"].items()
    assert url.startswith("/t/comando/usinas/") and resp["acoes"][0]["usinas_ids"] == [int(url.rsplit("/", 1)[1])]
    assert logado.post("/t/comando/usinas/ia/perguntar", json={"pergunta": "?", "modelos": ["x"]},
                       headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_a_demanda_da_carteira_vai_com_as_usinas_da_lista(tela, logado, monkeypatch):
    from nexus.comando import demandas as DM
    visto = {}
    monkeypatch.setattr(DM, "abrir", lambda form, anexos, usuario: visto.update(form=form) or {"demanda_id": "d1"})
    lista = logado.get("/t/comando/usinas").get_data(as_text=True)
    ids = re.findall(r"/t/comando/usinas/(\d+)\"", lista)
    r = logado.post("/t/comando/usinas/ia/demanda", json={"para_hmac": "h", "para_setor_id": "2:Chamados", "tema_id": "t",
                                                         "titulo": "Cobrar", "descricao": "x", "usinas": f"{ids[0]},99999"})
    assert r.status_code == 200 and visto["form"]["usinas"] == [ids[0]]          # a usina fora da lista não vai
