"""Nexus IA no prontuário da usina (13/11/2026). Levi: "Do prontuário, eu quero que tenha um chat. Onde a pessoa possa
fazer perguntas. Coisas do tipo, como foi a performance no mês? Por que a usina caiu? Qual a tendência? E aí já
responder [...] Teste com várias IAs. Tal como Sonnet, Opus, Gemini, Groq, Grok".

Nenhum teste vai à rede: o SDK da Anthropic e o `requests` são trocados por dublês que respondem como cada provedor
responde (o formato de cada um), e as rotas usam o `IA.perguntar` dublado."""
import json
import sys
import types

import pytest
from test_campo_responsaveis import tela  # noqa: F401  (tela é fixture)
from test_campo_visao import banco  # noqa: F401  (banco é fixture)

from nexus.comando import ia as IA

DOSSIE = """# Dossiê da usina Altair

## 3. Performance

- Atingimento da meta: 91,4% em outubro; mês anterior, 97,2%
- Geração: 1.234,5 MWh
- PR: 78,4%
- 3 inversores parados desde 02/11
"""


class _Resp:
    def __init__(self, status, corpo):
        self.status_code, self._corpo, self.text = status, corpo, json.dumps(corpo)

    def json(self):
        return self._corpo


# ── a lista de modelos, a chave e a conta ────────────────────────────────────────────────────────────────────────────
def test_sem_chave_o_modelo_aparece_e_nao_e_chamado(monkeypatch):
    chamados = []
    monkeypatch.setattr(IA, "_chamar", lambda *a: chamados.append(a) or {"texto": "x"})
    d = {m["id"]: m for m in IA.disponiveis({"GEMINI_API_KEY": "g"})}
    assert d["gemini-lite"]["tem_chave"] and not d["opus"]["tem_chave"] and not d["nemotron"]["tem_chave"]
    assert "ANTHROPIC_API_KEY" in d["opus"]["motivo"] and "console.anthropic.com" in d["opus"]["motivo"]
    r = IA.responder({}, IA.modelos({})[0], DOSSIE, "Como foi o mês?")
    assert not r["ok"] and "Falta a ANTHROPIC_API_KEY" in r["erro"] and chamados == []


def test_a_lista_troca_pelo_env_e_o_json_errado_nao_derruba():
    cfg = {"NEXUS_IA_MODELOS": json.dumps([{"id": "g3", "rotulo": "Gemini 3", "provedor": "gemini", "modelo": "gemini-3",
                                            "entrada": 2, "saida": 12}, {"id": "x", "rotulo": "?", "provedor": "nada",
                                                                         "modelo": "y"}])}
    assert [m.id for m in IA.modelos(cfg)] == ["g3"]
    assert [m.id for m in IA.modelos({"NEXUS_IA_MODELOS": "{quebrado"})] == [m.id for m in IA.MODELOS_PADRAO]


def test_o_custo_conta_o_cache_da_anthropic():
    opus = next(m for m in IA.MODELOS_PADRAO if m.id == "opus")
    # 1.000 de entrada a US$ 4, 10.000 lidos do cache a 10%, 300 de saída a US$ 20
    assert IA.custo(opus, 1000, 300, cache_lido=10000) == pytest.approx((4000 + 4000 + 6000) / 1e6)


# ── os números da resposta que estão no dossiê ───────────────────────────────────────────────────────────────────────
def test_os_numeros_que_nao_estao_no_dossie_aparecem():
    r = IA.numeros_conferidos("A meta ficou em 91,4% em outubro (§3), contra 97,2% em setembro: queda de 5,8 pontos. "
                              "Gerou 1234,5 MWh; 3 inversores parados desde 02/11; o PR foi 81,0% em 2026.", DOSSIE)
    assert r == {"n": 5, "no_dossie": 3, "fora": ["5,8", "81,0"]}


def test_o_historico_vai_curto_e_so_com_pares_completos():
    hist = [{"pergunta": f"p{i}", "resposta": f"r{i}"} for i in range(5)] + [{"pergunta": "sem resposta"}]
    msgs = IA._mensagens(hist, "e agora?")
    assert [m["content"] for m in msgs] == ["p3", "r3", "p4", "r4", "e agora?"]


# ── cada provedor, no formato dele ───────────────────────────────────────────────────────────────────────────────────
def test_anthropic_com_o_dossie_em_cache_esforco_baixo_e_reserva_no_opus(monkeypatch):
    pedidos = []

    class _Uso:
        input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens = 120, 80, 9000, 0

    class _Msg:
        stop_reason, model, usage = "end_turn", "claude-opus-5-5", _Uso()
        content = [types.SimpleNamespace(type="thinking", thinking=""), types.SimpleNamespace(type="text", text="Caiu.")]

    class _Cli:
        def __init__(self, **kw):
            pedidos.append(("cliente", kw))
            self.messages = types.SimpleNamespace(create=lambda **k: pedidos.append(("normal", k)) or _Msg())
            self.beta = types.SimpleNamespace(messages=types.SimpleNamespace(
                create=lambda **k: pedidos.append(("beta", k)) or _Msg()))

    falso = types.ModuleType("anthropic")
    falso.Anthropic = _Cli
    for nome in ("NotFoundError", "AuthenticationError", "RateLimitError", "APIStatusError", "APIConnectionError"):
        setattr(falso, nome, type(nome, (Exception,), {}))
    monkeypatch.setitem(sys.modules, "anthropic", falso)
    cfg = {"ANTHROPIC_API_KEY": "k"}
    r = IA.responder(cfg, next(m for m in IA.MODELOS_PADRAO if m.id == "opus"), DOSSIE, "Por que caiu?")
    assert r["ok"] and r["texto"] == "Caiu." and (r["entrada"], r["saida"], r["cache_lido"]) == (120, 80, 9000)
    tipo, k = pedidos[1]
    assert tipo == "beta" and k["fallbacks"] == "default" and k["betas"] == ["server-side-fallback-2026-07-01"]
    assert k["output_config"] == {"effort": "low"} and "thinking" not in k and "temperature" not in k
    assert k["system"][0]["text"] == IA.INSTRUCOES and k["system"][1]["cache_control"] == {"type": "ephemeral"}
    assert "<dossie>" in k["system"][1]["text"] and k["messages"][-1] == {"role": "user", "content": "Por que caiu?"}
    IA.responder(cfg, next(m for m in IA.MODELOS_PADRAO if m.id == "haiku"), DOSSIE, "?")
    assert pedidos[-1][0] == "normal" and "fallbacks" not in pedidos[-1][1]
    # a recusa vira erro escrito, nunca resposta vazia
    _Msg.stop_reason = "refusal"
    assert IA.responder(cfg, IA.MODELOS_PADRAO[0], DOSSIE, "?")["erro"] == "O modelo recusou responder a esta pergunta."


def test_gemini_tira_o_pensamento_e_soma_o_que_pensou_na_saida(monkeypatch):
    visto = {}

    def post(url, json=None, headers=None, timeout=None):
        visto.update(url=url, corpo=json, headers=headers)
        return _Resp(200, {"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"text": "pensando...", "thought": True}, {"text": "A meta foi 91,4% (§3)."}]}}],
            "usageMetadata": {"promptTokenCount": 5000, "candidatesTokenCount": 40, "thoughtsTokenCount": 300}})
    monkeypatch.setattr(IA.requests, "post", post)
    m = next(x for x in IA.MODELOS_PADRAO if x.id == "gemini-lite")
    r = IA.responder({"GEMINI_API_KEY": "g"}, m, DOSSIE, "Como foi o mês?", [{"pergunta": "oi", "resposta": "olá"}])
    assert r["ok"] and r["texto"] == "A meta foi 91,4% (§3)." and (r["entrada"], r["saida"]) == (5000, 340)
    assert visto["url"].endswith("/models/gemini-3.1-flash-lite:generateContent") and visto["headers"]["x-goog-api-key"] == "g"
    assert [c["role"] for c in visto["corpo"]["contents"]] == ["user", "model", "user"]
    assert "<dossie>" in visto["corpo"]["systemInstruction"]["parts"][0]["text"]
    assert r["numeros"] == {"n": 1, "no_dossie": 1, "fora": []}


def test_grok_groq_e_openrouter_pelo_chat_completions(monkeypatch):
    urls = []

    def post(url, json=None, headers=None, timeout=None):
        urls.append(url)
        assert headers["Authorization"] == "Bearer k" and json["messages"][0]["role"] == "system"
        return _Resp(200, {"choices": [{"finish_reason": "stop", "message": {"content": "<think>hmm</think>Subiu."}}],
                           "usage": {"prompt_tokens": 4000, "completion_tokens": 25}})
    monkeypatch.setattr(IA.requests, "post", post)
    # o Grok saiu da lista padrão (13/11/2026: pago) e volta pelo NEXUS_IA_MODELOS
    lista = [{"id": m.id, "rotulo": m.rotulo, "provedor": m.provedor, "modelo": m.modelo, "entrada": m.entrada,
              "saida": m.saida} for m in IA.MODELOS_PADRAO]
    lista.append({"id": "grok", "rotulo": "Grok", "provedor": "xai", "modelo": "grok-x", "entrada": 2, "saida": 6})
    cfg = {"XAI_API_KEY": "k", "GROQ_API_KEY": "k", "OPENROUTER_API_KEY": "k", "NEXUS_IA_MODELOS": json.dumps(lista)}
    assert "grok" not in [m.id for m in IA.MODELOS_PADRAO]
    rs = IA.perguntar(cfg, ["grok", "groq-oss", "nemotron", "opus"], DOSSIE, "Qual a tendência?")
    assert [r["id"] for r in rs] == ["grok", "groq-oss", "nemotron", "opus"]
    assert rs[2]["custo_usd"] == 0.0                                    # o ":free" do OpenRouter não custa
    assert [r["ok"] for r in rs] == [True, True, True, False] and rs[0]["texto"] == "Subiu."
    assert sorted(urls) == ["https://api.groq.com/openai/v1/chat/completions", "https://api.x.ai/v1/chat/completions",
                            "https://openrouter.ai/api/v1/chat/completions"]


def test_modelo_que_nao_existe_diz_quais_existem(monkeypatch):
    monkeypatch.setattr(IA.requests, "post", lambda *a, **k: _Resp(404, {"error": {"message": "The model x does not exist"}}))
    monkeypatch.setattr(IA.requests, "get", lambda *a, **k: _Resp(200, {"data": [{"id": "deepseek/a:free"}, {"id": "qwen/b:free"}]}))
    r = IA.responder({"OPENROUTER_API_KEY": "k"}, next(m for m in IA.MODELOS_PADRAO if m.id == "nemotron"), DOSSIE, "?")
    assert not r["ok"] and "404" in r["erro"] and "Os que existem para esta chave: deepseek/a:free, qwen/b:free" in r["erro"]


def test_um_provedor_que_quebra_nao_derruba_os_outros(monkeypatch):
    def chamar(m, *a):
        if m.provedor == "gemini":
            raise RuntimeError("boom")
        return {"texto": "ok", "entrada": 1, "saida": 1}
    monkeypatch.setattr(IA, "_chamar", chamar)
    rs = IA.perguntar({"GEMINI_API_KEY": "g", "GROQ_API_KEY": "k"}, ["gemini-lite", "groq-oss", "naoexiste"], DOSSIE, "?")
    assert [(r["id"], r["ok"]) for r in rs] == [("gemini-lite", False), ("groq-oss", True)]
    assert rs[0]["erro"] == "Falhou (RuntimeError)."


# ── o registro do mês e o teto ───────────────────────────────────────────────────────────────────────────────────────
def test_registro_do_mes_e_o_teto(tmp_path):
    cfg = {"NEXUS_DADOS": str(tmp_path), "NEXUS_IA_TETO_USD": "0.5"}
    IA.registrar(cfg, 1, "Como foi?", [{"id": "opus", "ok": True, "texto": "Bem.", "custo_usd": 0.3},
                                      {"id": "grok", "ok": False, "erro": "sem chave"}], "abc", 9000)
    linhas = [json.loads(x) for x in next((tmp_path / "ia").glob("perguntas-*.jsonl")).read_text(encoding="utf-8").splitlines()]
    assert [(x["modelo"], x["quem"], x["usina_id"]) for x in linhas] == [("opus", "abc", 1), ("grok", "abc", 1)]
    assert IA.gasto_do_mes(cfg) == 0.3 and IA.teto(cfg) == 0.5
    assert IA.gasto_do_mes({"TESTING": True}) == 0.0           # teste sem pasta própria não grava nem lê


# ── a tela ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_botao_e_a_janela_so_para_administrador(tela, logado):
    p = logado.get("/t/comando/usinas/1").get_data(as_text=True)
    assert 'data-pu-jan="/t/comando/usinas/1/ia?parcial=1" data-pu-jan-t="Nexus IA · Altair"' in p
    assert "/static/comando/ia.js" in p
    h = logado.get("/t/comando/usinas/1/ia?parcial=1").get_data(as_text=True)
    assert "<html" not in h.lower() and 'data-ia-url="/t/comando/usinas/1/ia/perguntar"' in h
    assert "Como foi a performance no mês?" in h and "Nenhuma IA ligada neste servidor" in h and "sem chave" in h
    assert "<html" in logado.get("/t/comando/usinas/1/ia").get_data(as_text=True).lower()     # a página inteira
    with logado.session_transaction() as s:
        s["admin"] = False
    assert "/ia?parcial=1" not in logado.get("/t/comando/usinas/1").get_data(as_text=True)
    assert logado.get("/t/comando/usinas/1/ia?parcial=1").status_code == 403
    assert logado.post("/t/comando/usinas/1/ia/perguntar", json={"pergunta": "?", "modelos": ["opus"]}).status_code == 403


def test_perguntar_monta_o_dossie_de_agora_e_registra(tela, logado, monkeypatch, tmp_path):
    logado.application.config.update(NEXUS_DADOS=str(tmp_path), GEMINI_API_KEY="g", NEXUS_IA_MODELOS=json.dumps([
        {"id": "gemini-flash", "rotulo": "Gemini", "provedor": "gemini", "modelo": "g", "entrada": 0.3, "saida": 2.5},
        {"id": "gemini-pro", "rotulo": "Gemini Pro", "provedor": "gemini", "modelo": "p", "entrada": 1.25, "saida": 10},
        {"id": "opus", "rotulo": "Opus", "provedor": "anthropic", "modelo": "claude-opus-5-5", "entrada": 4, "saida": 20}]))
    visto = {}

    def perguntar(cfg, ids, dossie, pergunta, historico=None):
        visto.update(ids=ids, dossie=dossie, pergunta=pergunta, historico=historico)
        return [{"id": "gemini-flash", "ok": True, "texto": "Bem.", "custo_usd": 0.01}]
    monkeypatch.setattr(IA, "perguntar", perguntar)
    h = logado.get("/t/comando/usinas/1/ia?parcial=1").get_data(as_text=True)
    # marcado de início: o 1º modelo com chave (a Anthropic sem chave fica de fora)
    assert 'value="gemini-flash" data-ia-modelo checked' in h and 'value="gemini-pro" data-ia-modelo>' in h
    assert 'value="opus" data-ia-modelo disabled' in h and "Nenhuma IA ligada" not in h and "US$ 0,00" in h
    r = logado.post("/t/comando/usinas/1/ia/perguntar", json={
        "pergunta": "  Por que   caiu? ", "modelos": ["gemini-flash"], "historico": [{"pergunta": "a", "resposta": "b"}]})
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] and j["respostas"][0]["texto"] == "Bem." and j["gasto"] == 0.01
    assert visto["pergunta"] == "Por que caiu?" and visto["dossie"].startswith("# Dossiê da usina Altair")
    assert "Ciclano Chefe" not in visto["dossie"]                       # as pessoas vão pelo papel
    assert len(list((tmp_path / "ia").glob("perguntas-*.jsonl"))) == 1
    # sem pergunta, sem modelo, de outro site, teto estourado
    assert logado.post("/t/comando/usinas/1/ia/perguntar", json={"pergunta": " ", "modelos": ["x"]}).status_code == 400
    assert logado.post("/t/comando/usinas/1/ia/perguntar", json={"pergunta": "?", "modelos": []}).status_code == 400
    assert logado.post("/t/comando/usinas/1/ia/perguntar", json={"pergunta": "?", "modelos": ["opus"]},
                       headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    logado.application.config["NEXUS_IA_TETO_USD"] = "0.01"
    r = logado.post("/t/comando/usinas/1/ia/perguntar", json={"pergunta": "?", "modelos": ["gemini-flash"]})
    assert r.status_code == 429 and "teto do mês" in r.get_json()["erro"]


# ── a rodada de comparação (ferramentas/ia_comparar.py) ──────────────────────────────────────────────────────────────
def test_a_rodada_compara_os_modelos_com_chave_e_respeita_o_teto(monkeypatch, tmp_path):
    from ferramentas import ia_comparar as CMP
    lista = json.dumps([{"id": "gemini-pro", "rotulo": "P", "provedor": "gemini", "modelo": "p", "entrada": 1.25, "saida": 10},
                        {"id": "gemini-flash", "rotulo": "F", "provedor": "gemini", "modelo": "f", "entrada": 0.3, "saida": 2.5},
                        {"id": "groq-oss", "rotulo": "G", "provedor": "groq", "modelo": "o", "entrada": 0.15, "saida": 0.6},
                        {"id": "opus", "rotulo": "O", "provedor": "anthropic", "modelo": "claude-opus-5-5", "entrada": 4, "saida": 20}])
    monkeypatch.setattr(CMP, "_dossies", lambda ids: ({1: ("Altair", DOSSIE)}, {"GEMINI_API_KEY": "g", "GROQ_API_KEY": "k",
                                                                               "NEXUS_IA_MODELOS": lista}))
    for p in IA.PROVEDORES.values():
        monkeypatch.delenv(p["chave"], raising=False)
    monkeypatch.setattr(IA, "_chamar", lambda m, *a: {"texto": f"{m.id}: a meta foi 91,4% e 55,5 inventado.",
                                                      "entrada": 1_000_000, "saida": 0})
    assert CMP.main(["--usinas", "1", "--perguntas", "Como foi?|Por que caiu?|Tendência?", "--saida", str(tmp_path),
                     "--teto", "1"]) == 0
    rodada = json.loads(next(tmp_path.glob("comparacao-*.json")).read_text(encoding="utf-8"))
    # cada pergunta custa US$ 1,25 + 0,30 + 0,15 (1 milhão de entrada em cada): passou do teto na 1ª, parou
    assert [x["pergunta"] for x in rodada] == ["Como foi?"]
    assert [r["id"] for r in rodada[0]["respostas"]] == ["gemini-pro", "gemini-flash", "groq-oss"]
    pagina = next(tmp_path.glob("comparacao-*.html")).read_text(encoding="utf-8")
    assert "Nexus IA · teste das IAs" in pagina and "sem chave: não foi chamado" in pagina
    assert "1 de 2 números no dossiê · fora: 55,5" in pagina and "<script" not in pagina
    monkeypatch.setattr(CMP, "_dossies", lambda ids: ({1: ("Altair", DOSSIE)}, {}))
    assert CMP.main(["--usinas", "1", "--saida", str(tmp_path)]) == 2          # nenhuma chave: não roda


def test_as_chaves_e_a_lista_chegam_ao_app_config_pelo_env():
    """14/11/2026: o .env só chega ao app.config pelas OPCIONAIS; sem elas, o chat dizia "sem chave" com a chave no .env."""
    from nexus import create_app
    from nexus.config import OPCIONAIS
    for p in IA.PROVEDORES.values():
        assert p["chave"] in OPCIONAIS
    assert "NEXUS_IA_MODELOS" in OPCIONAIS and "NEXUS_IA_TETO_USD" in OPCIONAIS
    app = create_app({"NEXUS_SECRET_KEY": "x", "NEXUS_SENHA_ADMIN": "y", "OPENROUTER_API_KEY": "k", "NEXUS_IA_TETO_USD": "5"})
    assert app.config["OPENROUTER_API_KEY"] == "k" and IA.teto(app.config) == 5.0
    assert {m["id"]: m["tem_chave"] for m in IA.disponiveis(app.config)}["nemotron"] is True
