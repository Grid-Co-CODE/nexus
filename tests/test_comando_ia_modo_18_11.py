"""Busca ou Pensamento na pergunta da Nexus IA (Levi, 18/11/2026). A resposta do Haiku levou 17,1 s numa pergunta
simples, e cerca de 1.800 dos 2.231 tokens de saída eram o rascunho que ele faz antes de responder (o pensamento). O
pedido: "pode ter a opção Busca/Pensamento. O botão fica no busca mas se a pessoa quiser que pense ela ativa o
pensamento".

Como funciona: a caixa da pergunta tem os dois modos, com Busca marcado. Em Busca, o Claude responde direto pelo dossiê
(`thinking: disabled` no pedido, `max_tokens` menor); em Pensamento, o pedido vai como antes. O modo vai no JSON da
pergunta (`modo`), e sem ele vale Busca. O diagnóstico do dia também vai em Busca (no mesmo dia, Levi: "diagnóstico em
busca, rode alguns diagnósticos e bata os dados para ver se a informação está confiável"). Se a Anthropic
recusar o `thinking: disabled`, o pedido é refeito sem ele, e a resposta diz que foi com pensamento. Nenhum teste vai
à rede: o SDK é um dublê."""
import inspect
import json
from pathlib import Path

from test_campo_responsaveis import tela  # noqa: F401  (tela é fixture)
from test_campo_visao import banco  # noqa: F401  (banco é fixture)
from test_comando_ia import DOSSIE
from test_comando_ia_fluxo_18_11 import sdk  # noqa: F401  (sdk é fixture: o SDK da Anthropic de mentira)

from nexus.comando import ia as IA

HAIKU = next(m for m in IA.MODELOS_PADRAO if m.id == "haiku")
MSGS = [{"role": "user", "content": "?"}]


def _cfg(tmp_path):
    return {"NEXUS_DADOS": str(tmp_path), "ANTHROPIC_API_KEY": "k"}


# ── o pedido ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_em_busca_o_pedido_vai_sem_pensamento_e_em_pensamento_como_antes():
    pensa = IA._pedido_anthropic(HAIKU, DOSSIE, MSGS)
    assert "thinking" not in pensa and pensa["max_tokens"] == IA.MAX_SAIDA_ANTHROPIC
    busca = IA._pedido_anthropic(HAIKU, DOSSIE, MSGS, pensar=False)
    assert busca["thinking"] == {"type": "disabled"} and busca["max_tokens"] == IA.MAX_SAIDA
    # o resto do pedido é o mesmo: o esforço do modelo, o dossiê com cache (o cache do dossiê vale nos dois modos)
    assert busca["output_config"] == pensa["output_config"] == {"effort": IA.ESFORCO["claude-haiku-5-5"]}
    assert busca["system"] == pensa["system"] and busca["messages"] == pensa["messages"]


def test_o_diagnostico_do_dia_vai_em_busca(tmp_path, monkeypatch):
    # a 1ª abertura do dia levava 40 s com pensamento (Levi, 18/11/2026); em Busca o Claude escreve só o diagnóstico
    from nexus.comando import diagnostico as DG
    visto = {}

    def perguntar(cfg, ids, dossie, pergunta, *a, **k):
        visto.update(k)
        return [{"id": "haiku", "rotulo": "Claude Haiku 5.5", "ok": True, "texto": '<diagnostico>{"situacao": "Ok."}</diagnostico>'}]
    monkeypatch.setattr(IA, "perguntar", perguntar)
    assert DG.PENSAR is False
    assert DG.gerar({"NEXUS_DADOS": str(tmp_path), "ANTHROPIC_API_KEY": "k"}, 1, DOSSIE, 100, "2026-11-18")["ok"]
    assert visto["pensar"] is False


def test_quem_nao_diz_o_modo_pensa_como_antes():
    # o padrão das funções segue "pensar": quem quer Busca diz (a caixa da pergunta e o diagnóstico do dia dizem)
    for f in (IA.perguntar, IA.responder, IA.perguntar_em_fluxo, IA.responder_em_fluxo):
        assert inspect.signature(f).parameters["pensar"].default is True, f.__name__


def test_a_resposta_diz_o_modo_com_e_sem_fluxo(sdk, tmp_path):
    cfg = _cfg(tmp_path)
    r = IA.perguntar(cfg, ["haiku"], DOSSIE, "Por que caiu?", setores=["Engenharia"], pensar=False)[0]
    assert r["ok"] and r["modo"] == "busca" and sdk.pedidos[-1]["thinking"] == {"type": "disabled"}
    r = IA.perguntar(cfg, ["haiku"], DOSSIE, "Por que caiu?", setores=["Engenharia"])[0]
    assert r["ok"] and r["modo"] == "pensamento" and "thinking" not in sdk.pedidos[-1]
    fim = list(IA.perguntar_em_fluxo(cfg, ["haiku"], DOSSIE, "Por que caiu?", setores=["Engenharia"], pensar=False))[-1][1]
    assert fim[0]["ok"] and fim[0]["modo"] == "busca" and sdk.pedidos[-1]["thinking"] == {"type": "disabled"}
    fim = list(IA.perguntar_em_fluxo(cfg, ["haiku"], DOSSIE, "Por que caiu?", setores=["Engenharia"]))[-1][1]
    assert fim[0]["modo"] == "pensamento" and "thinking" not in sdk.pedidos[-1]
    # o registro do mês guarda o modo (para comparar o tempo dos dois depois)
    IA.registrar(cfg, 1, "Por que caiu?", fim, "abc", 100)
    linha = json.loads(next((tmp_path / "ia").glob("perguntas-*.jsonl")).read_text(encoding="utf-8").splitlines()[-1])
    assert linha["modo"] == "pensamento"


def test_a_anthropic_que_recusa_o_sem_pensamento_responde_pensando(sdk, tmp_path):
    # não deu para provar o `thinking: disabled` contra a API de verdade (a chave só existe no servidor): se ela recusar
    # o parâmetro, a pergunta não cai nas grátis; o pedido é refeito sem ele, e a resposta diz que foi com pensamento
    cfg = _cfg(tmp_path)
    sdk.recusa_o_sem_pensamento = True
    r = IA.perguntar(cfg, ["haiku"], DOSSIE, "Por que caiu?", setores=["Engenharia"], pensar=False)[0]
    assert r["ok"] and r["modo"] == "pensamento" and r["id"] == "haiku" and "troca" not in r
    assert [("thinking" in p) for p in sdk.pedidos] == [True, False]
    assert sdk.pedidos[-1]["max_tokens"] == IA.MAX_SAIDA_ANTHROPIC
    sdk.pedidos.clear()
    eventos = list(IA.perguntar_em_fluxo(cfg, ["haiku"], DOSSIE, "Por que caiu?", setores=["Engenharia"], pensar=False))
    assert eventos[-1][1][0]["ok"] and eventos[-1][1][0]["modo"] == "pensamento" and "troca" not in eventos[-1][1][0]
    assert [("thinking" in p) for p in sdk.pedidos] == [True, False] and any(t == "texto" for t, _d in eventos)
    # outro 400 (que não fala do pensamento) não é refeito: segue como falha do Haiku
    sdk.pedidos.clear()
    sdk.recusa_o_sem_pensamento, sdk.erro = False, "APIStatusError"
    r = IA.perguntar(cfg, ["haiku"], DOSSIE, "Por que caiu?", setores=["Engenharia"], pensar=False)[0]
    assert not r["ok"] and len(sdk.pedidos) == 1


# ── as rotas e a tela ────────────────────────────────────────────────────────────────────────────────────────────────
def _lidos(resp):
    return [json.loads(l[6:]) for l in resp.get_data(as_text=True).split("\n") if l.startswith("data: ")]


def test_as_rotas_da_usina_levam_o_modo_e_sem_ele_vale_busca(tela, logado, sdk, tmp_path):
    logado.application.config.update(NEXUS_DADOS=str(tmp_path), ANTHROPIC_API_KEY="k")
    corpo = {"pergunta": "Por que caiu?", "modelos": ["haiku"]}
    for rota in ("/t/campo/usinas/1/ia/perguntar/fluxo", "/t/campo/usinas/1/ia/perguntar"):
        sdk.pedidos.clear()
        r = logado.post(rota, json=corpo)
        fim = _lidos(r)[-1] if r.mimetype == "text/event-stream" else r.get_json()
        assert fim["respostas"][0]["modo"] == "busca" and sdk.pedidos[-1]["thinking"] == {"type": "disabled"}, rota
        r = logado.post(rota, json=dict(corpo, modo="pensamento"))
        fim = _lidos(r)[-1] if r.mimetype == "text/event-stream" else r.get_json()
        assert fim["respostas"][0]["modo"] == "pensamento" and "thinking" not in sdk.pedidos[-1], rota
        # o modo que não existe vale Busca (não é erro: a tela antiga, sem o botão, segue respondendo)
        logado.post(rota, json=dict(corpo, modo="turbo")).get_data()        # lê o corpo: o fluxo só chama a IA ao ser lido
        assert sdk.pedidos[-1]["thinking"] == {"type": "disabled"}, rota


def test_a_rota_da_carteira_leva_o_modo(tela, logado, monkeypatch):
    visto = []

    def perguntar(cfg, ids, dossie, pergunta, historico=None, **k):
        visto.append(k.get("pensar"))
        return [{"id": "haiku", "rotulo": "Claude Haiku 5.5", "ok": True, "texto": "Resposta.", "acoes": []}]
    monkeypatch.setattr(IA, "perguntar", perguntar)
    corpo = {"pergunta": "quais usinas preocupam mais e por quê, olhando tudo?", "modelos": ["haiku"]}
    assert logado.post("/t/campo/usinas/ia/perguntar", json=corpo).status_code == 200
    assert logado.post("/t/campo/usinas/ia/perguntar", json=dict(corpo, modo="pensamento")).status_code == 200
    assert visto == [False, True]


def test_a_caixa_tem_busca_marcado_e_pensamento_so_com_a_chave_da_anthropic(tela, logado, tmp_path):
    logado.application.config.update(NEXUS_DADOS=str(tmp_path), ANTHROPIC_API_KEY="")
    sem = logado.get("/t/campo/usinas/1/ia?parcial=1").get_data(as_text=True)
    assert "data-ia-modo" not in sem               # sem o Claude, o botão não faria nada: não aparece
    logado.application.config.update(ANTHROPIC_API_KEY="k")
    for rota in ("/t/campo/usinas/1/ia?parcial=1", "/t/campo/usinas/ia?parcial=1"):
        h = logado.get(rota).get_data(as_text=True)
        assert 'role="radiogroup"' in h and h.count("data-ia-modo") == 2, rota
        busca = h.split('value="busca"', 1)[1].split(">", 1)[0]
        pensa = h.split('value="pensamento"', 1)[1].split(">", 1)[0]
        assert "checked" in busca and "checked" not in pensa, rota
        assert "> Busca<" in h.replace("</i>", ">") or "Busca</span>" in h, rota
        assert "Pensamento</span>" in h, rota
    js = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "comando" / "ia.js").read_text(encoding="utf-8")
    # a tela manda o modo marcado e diz no pé do cartão quando a resposta foi com pensamento
    for trecho in ("[data-ia-modo]:checked", "modo: modo", "r.modo === 'pensamento'"):
        assert trecho in js, trecho
