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
    assert "## 2. Usinas" in t and "## 3. Totais contados pelo Nexus" in t
    assert "## 4. Chamados de garantia abertos" in t and "## 5. O que ficou de fora" in t
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


def test_os_totais_sao_contados_pelo_nexus():
    """Perguntado duas vezes "quais fabricantes têm mais chamados abertos?", o Nemotron contou a Sungrow com 23 e depois
    com 28 (eram 39) e a STI com 52 (eram 102): a conta vem pronta no dossiê."""
    f = _fontes()
    f["chamados"][2] = [{"os": "18000", "situacao": "aberto", "fabricante": "SolarEdge", "data_id_abertura": "20261101"},
                        {"os": "18001", "situacao": "verificacao", "fabricante": "STI", "data_id_abertura": "20261110"}]
    t = CI.montar([_linha(1, "Colíder 1"), _linha(2, "Colíder 2", cliente="Thopen")], f, AGORA)["texto"]
    assert "| SolarEdge | 2 | 2 | 98 dias |" in t and "| STI | 1 | 1 | 6 dias |" in t
    assert "| Renogrid | 1 | 2,5 | 1 | 1 | 0 | 1 |" in t and "| Thopen | 1 | 2,5 | 1 | 2 | 1 | 1 |" in t
    assert "Nunca conte linha por linha" in CI.INSTRUCOES
    # o cruzamento pronto: só as usinas com chamado aberto, da pior disponibilidade para a melhor
    assert "Usinas com chamado de garantia aberto (2), da pior disponibilidade do mês para a melhor:" in t
    i = t.index("Usinas com chamado de garantia aberto (2)")
    assert t.index("| Colíder 1 | Renogrid | 0,0% |", i) < t.index("| Colíder 2 | Thopen | 70,2% |", i)


def test_a_resposta_vazia_ou_demorada_passa_a_reserva(monkeypatch):
    """No servidor só há as chaves do OpenRouter: a reserva é o Nemotron 3.5 Super, no mesmo OpenRouter."""
    import time
    cfg = {"OPENROUTER_API_KEY": "k"}
    vistos = []

    def chamar(m, *a):
        vistos.append(m.id)
        return {"texto": ""} if m.id == "nemotron" else {"texto": "Certo."}
    monkeypatch.setattr(IA, "_chamar", chamar)
    r = IA.perguntar(cfg, ["nemotron"], "D", "?")
    assert vistos == ["nemotron", "nemotron-super"] and r[0]["ok"] and "voltou sem resposta" in r[0]["troca"]
    # o teto do tempo inteiro: a demorada também passa
    monkeypatch.setattr(IA, "TEMPO_TOTAL_S", 0.2)
    vistos.clear()

    def lento(m, *a):
        vistos.append(m.id)
        if m.id == "nemotron":
            time.sleep(1)
        return {"texto": "Certo."}
    monkeypatch.setattr(IA, "_chamar", lento)
    r = IA.perguntar(cfg, ["nemotron"], "D", "?")
    assert vistos[:2] == ["nemotron", "nemotron-super"] and r[0]["ok"] and r[0]["id"] == "nemotron-super"


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


def test_executar_os_nunca_vira_pedido_a_outro_setor():
    """16/11/2026, na Marabá 200: com a regra nas instruções, o Nemotron ainda mandou estas duas à Manutenção."""
    _t, acoes = IA.separar_acoes(
        'Ok.\n<acoes>[{"setor": "Manutenção", "acao": "Executar as corretivas atrasadas OS 18364 (Tracker 9.101)", "os": 18364},'
        '{"setor": "Manutenção", "acao": "Atender as OS de parada abertas OS 19089 (Cabine 5)", "os": 19089},'
        '{"setor": "Engenharia", "acao": "Avaliar e apoiar a configuração do sensor de temperatura", "os": null},'
        '{"setor": "Engenharia", "acao": "Realizar a análise de recorrência do inversor 1.5", "os": null},'
        '{"setor": "Chamados", "acao": "Cobrar da STI os 4 chamados abertos", "os": null}]</acoes>',
        ["Manutenção", "Engenharia", "Chamados"])
    assert [a["acao"][:20] for a in acoes] == ["Avaliar e apoiar a c", "Realizar a análise d", "Cobrar da STI os 4 c"]


def test_a_caixa_esta_na_tela_para_todos(tela, logado):
    """Sem janela e sem o botão do alto: o lugar da caixa no prontuário e na lista; o pedaço abre para quem não é
    administrador, e a pergunta também (a de antes respondia 403)."""
    with logado.session_transaction() as s:
        s["admin"] = False
    p = logado.get("/t/campo/usinas/1").get_data(as_text=True)
    assert 'data-pu-ia="/t/campo/usinas/1/ia?parcial=1"' in p and "/static/comando/ia.js" in p
    assert 'data-pu-jan="/t/campo/usinas/1/ia?parcial=1"' not in p
    h = logado.get("/t/campo/usinas/1/ia?parcial=1")
    assert h.status_code == 200 and 'class="ia ia--embutida"' in h.get_data(as_text=True)
    assert logado.post("/t/campo/usinas/1/ia/perguntar", json={"pergunta": "?", "modelos": []}).status_code == 400
    lista = logado.get("/t/campo/usinas").get_data(as_text=True)
    assert 'data-cmu-ia="/t/campo/usinas/ia"' in lista and "/static/comando/ia.js" in lista
    c = logado.get("/t/campo/usinas/ia").get_data(as_text=True)
    assert 'data-ia-url="/t/campo/usinas/ia/perguntar"' in c and "sobre a carteira inteira" in c
    assert "Chamados abertos × disponibilidade e performance" in c
    # o texto do dossiê da carteira, só para o administrador
    assert logado.get("/t/campo/usinas/dossie-da-carteira.md").status_code == 403


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
    r = logado.post("/t/campo/usinas/ia/perguntar", json={"pergunta": "Chamados × disponibilidade", "modelos": ["nemotron"]})
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] and visto["instrucoes"] == CI.INSTRUCOES
    assert visto["dossie"].startswith("# Dossiê da carteira de usinas")
    resp = j["respostas"][0]
    (nome, url), = resp["usinas"].items()
    assert url.startswith("/t/campo/usinas/") and resp["acoes"][0]["usinas_ids"] == [int(url.rsplit("/", 1)[1])]
    assert logado.post("/t/campo/usinas/ia/perguntar", json={"pergunta": "?", "modelos": ["x"]},
                       headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403


def test_a_demanda_da_carteira_vai_com_as_usinas_da_lista(tela, logado, monkeypatch):
    from nexus.comando import demandas as DM
    visto = {}
    monkeypatch.setattr(DM, "abrir", lambda form, anexos, usuario: visto.update(form=form) or {"demanda_id": "d1"})
    lista = logado.get("/t/campo/usinas").get_data(as_text=True)
    ids = re.findall(r"/t/campo/usinas/(\d+)\"", lista)
    r = logado.post("/t/campo/usinas/ia/demanda", json={"para_hmac": "h", "para_setor_id": "2:Chamados", "tema_id": "t",
                                                         "titulo": "Cobrar", "descricao": "x", "usinas": f"{ids[0]},99999"})
    assert r.status_code == 200 and visto["form"]["usinas"] == [ids[0]]          # a usina fora da lista não vai


def test_as_perguntas_sugeridas_saem_prontas_e_certas_sem_ia(tela, logado, monkeypatch):
    """16/11/2026, Levi: "e a demora pai". A IA grátis levou de 54 a 150 s nessas perguntas e errou a conta (a STI com
    52 chamados, eram 102): as cinco sugeridas são contas que o Nexus tem, respondidas na hora."""
    f = _fontes()
    f["chamados"][2] = [{"os": "18000", "situacao": "aberto", "fabricante": "STI", "data_id_abertura": "20261110"}]
    dz = CI.montar([_linha(1, "Colíder 1"), _linha(2, "Colíder 2", atingimento=98.0, os_atrasadas=0)], f, AGORA)
    cruz = CI.resposta_pronta("Chamados abertos × disponibilidade e performance", dz)
    assert cruz.startswith("**2 usinas têm chamado de garantia aberto (2 chamados).**")
    assert cruz.index("| Colíder 1 |") < cruz.index("| Colíder 2 |")              # a pior disponibilidade primeiro
    meta = CI.resposta_pronta("quais usinas estão abaixo da meta no mês", dz)          # sem acento, sem "?", minúscula
    assert "**2 de 2 usinas estão abaixo da meta de novembro**" in meta and meta.index("| Colíder 1 |") < meta.index("| Colíder 2 |")
    assert "**1 desligamentos em novembro, em 1 usinas**" in CI.resposta_pronta(CI.SUGESTOES[2], dz)
    fab = CI.resposta_pronta(CI.SUGESTOES[3], dz)
    assert "| SolarEdge | 1 | 1 | 98 dias |" in fab and "| STI | 1 | 1 | 6 dias |" in fab
    os_ = CI.resposta_pronta(CI.SUGESTOES[4], dz)
    assert os_.startswith("**1 usinas têm OS urgente não iniciada ou atrasada:** 1 urgentes") and "| Colíder 1 |" in os_
    assert CI.resposta_pronta("Por que a Colíder 1 está com 0%?", dz) is None
    # pela rota: a sugerida não chama a IA
    monkeypatch.setattr(IA, "perguntar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("chamou a IA")))
    j = logado.post("/t/campo/usinas/ia/perguntar", json={"pergunta": CI.SUGESTOES[3], "modelos": ["nemotron"]}).get_json()
    r = j["respostas"][0]
    assert j["ok"] and r["sem_ia"] and r["rotulo"] == "Contado pelo Nexus"
