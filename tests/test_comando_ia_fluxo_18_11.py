"""A resposta da Nexus IA aparecendo enquanto é escrita (Levi, 18/11/2026). A resposta do Haiku levou 17,1 s numa
pergunta simples ("demorou muito para uma questão simples"), com a tela parada até chegar inteira; à pergunta "Quer que
o texto apareça enquanto a IA escreve?", ele respondeu "Sim".

Como funciona: com UM modelo da Anthropic marcado, a rota `ia/perguntar/fluxo` responde em pedaços (`text/event-stream`):
`texto` a cada trecho que o modelo escreve, e `fim` com a MESMA resposta da rota de sempre (o texto conferido, as ações,
os números, o custo). O bloco `<acoes>` nunca aparece no texto ao vivo. Se o Haiku falha, a pergunta vai às grátis como
antes, e o `fim` traz a resposta delas com o motivo. Com outro provedor, ou comparando modelos, não há texto ao vivo: só
o `fim`. Nenhum teste vai à rede: o SDK da Anthropic é um dublê."""
import json
import sys
import time
import types
from pathlib import Path

import pytest
from test_campo_responsaveis import tela  # noqa: F401  (tela é fixture)
from test_campo_visao import banco  # noqa: F401  (banco é fixture)
from test_comando_ia import DOSSIE

from nexus.comando import ia as IA

HAIKU = next(m for m in IA.MODELOS_PADRAO if m.id == "haiku")
TRECHOS = ["A usina caiu pela rede ", "da concessionária (§3).\n", "- PR: 78,4%\n", "<ac", 'oes>[{"setor": "Engenharia", "acao": "Analisar", ',
           '"os": null}]</acoes>']


def _ev(tipo, **k):
    return types.SimpleNamespace(type=tipo, **k)


def _eventos(trechos):
    yield _ev("content_block_start", content_block=types.SimpleNamespace(type="thinking"))
    yield _ev("content_block_delta", delta=types.SimpleNamespace(type="thinking_delta", thinking=""))
    yield _ev("content_block_start", content_block=types.SimpleNamespace(type="text"))
    for t in trechos:
        yield _ev("content_block_delta", delta=types.SimpleNamespace(type="text_delta", text=t))
        yield _ev("text", text=t)                    # o evento derivado do SDK: não pode contar em dobro


@pytest.fixture
def sdk(monkeypatch):
    """O SDK da Anthropic de mentira: `messages.stream(**pedido)` devolve os eventos de `sdk.trechos` e a mensagem
    final; `sdk.erro` (o nome de uma exceção do SDK) faz a abertura do fluxo falhar, `sdk.no_meio` faz cair depois do
    primeiro trecho, e `sdk.espera` (segundos) atrasa o primeiro evento. `messages.create(**pedido)` é a chamada sem
    fluxo, com as mesmas falhas. `sdk.recusa_o_sem_pensamento` faz a API responder 400 ao pedido com `thinking`."""
    estado = types.SimpleNamespace(pedidos=[], trechos=TRECHOS, erro="", no_meio="", espera=0, recusa_o_sem_pensamento=False)

    def _abrir(k):
        if estado.recusa_o_sem_pensamento and "thinking" in k:
            ex = falso.APIStatusError("thinking: disabled is not supported for this model")
            ex.status_code = 400
            raise ex
        if estado.erro:
            raise getattr(falso, estado.erro)("falhou")

    class _Uso:
        input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens = 16, 2231, 0, 18263

    class _Fluxo:
        def __init__(self, k=None):
            self.k = k or {}

        def __enter__(self):
            _abrir(self.k)
            return self

        def __exit__(self, *a):
            return False

        def __iter__(self):
            time.sleep(estado.espera)
            for n, e in enumerate(_eventos(estado.trechos)):
                if estado.no_meio and n == 5:
                    raise getattr(falso, estado.no_meio)("caiu no meio")
                yield e

        def get_final_message(self):
            return types.SimpleNamespace(stop_reason="end_turn", model="claude-haiku-5-5", usage=_Uso(),
                                         content=[types.SimpleNamespace(type="text", text="".join(estado.trechos))])

    def _criar(**k):
        estado.pedidos.append(k)
        _abrir(k)
        return _Fluxo(k).get_final_message()

    class _Cli:
        def __init__(self, **kw):
            self.messages = types.SimpleNamespace(stream=lambda **k: estado.pedidos.append(k) or _Fluxo(k), create=_criar)

    falso = types.ModuleType("anthropic")
    falso.Anthropic = _Cli
    for nome in ("NotFoundError", "AuthenticationError", "RateLimitError", "APIStatusError", "APIConnectionError"):
        setattr(falso, nome, type(nome, (Exception,), {}))
    monkeypatch.setitem(sys.modules, "anthropic", falso)
    return estado


def _rodar(cfg, ids=("haiku",), **k):
    eventos = list(IA.perguntar_em_fluxo(cfg, list(ids), DOSSIE, "Por que caiu?", setores=["Engenharia", "COS"], **k))
    assert eventos[-1][0] == "fim" and [t for t, _d in eventos].count("fim") == 1
    return eventos, eventos[-1][1]


# ── o gerador ────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_texto_sai_em_pedacos_e_o_fim_e_a_resposta_de_sempre(sdk, tmp_path):
    eventos, fim = _rodar({"NEXUS_DADOS": str(tmp_path), "ANTHROPIC_API_KEY": "k"})
    ao_vivo = "".join(d for t, d in eventos if t == "texto")
    # o que aparece na tela enquanto escreve: o texto, sem o bloco das ações (nem um pedaço dele)
    assert ao_vivo == "A usina caiu pela rede da concessionária (§3).\n- PR: 78,4%\n"
    assert "acoes" not in ao_vivo and "<" not in ao_vivo
    assert ("pensando", "") in eventos and eventos.index(("pensando", "")) < next(i for i, e in enumerate(eventos) if e[0] == "texto")
    # o fim: a mesma resposta da rota sem fluxo (o texto tratado, a ação, os números conferidos, os tokens, o custo)
    r = fim[0]
    assert r["ok"] and r["id"] == "haiku" and "<acoes>" not in r["texto"] and r["texto"].startswith("A usina caiu pela rede")
    assert r["acoes"] == [{"setor": "Engenharia", "acao": "Analisar", "os": None}]
    assert (r["entrada"], r["saida"], r["cache_gravado"]) == (16, 2231, 18263) and r["custo_usd"] > 0 and r["ms"] >= 0
    assert r["numeros"]["no_dossie"] == 1 and r["servido_por"] == "claude-haiku-5-5"
    # o pedido é o mesmo do sem fluxo: o esforço do modelo, o dossiê com cache, a pergunta no fim
    k = sdk.pedidos[0]
    assert k["model"] == "claude-haiku-5-5" and k["output_config"] == {"effort": IA.ESFORCO["claude-haiku-5-5"]}
    assert k["system"][1]["cache_control"] == {"type": "ephemeral"} and "<dossie>" in k["system"][1]["text"]
    assert k["messages"][-1] == {"role": "user", "content": "Por que caiu?"}


def test_o_haiku_que_falha_vai_as_gratis_e_o_fim_diz_por_que(sdk, tmp_path, monkeypatch):
    monkeypatch.setattr(IA, "_chamar", lambda m, *a: {"texto": "Resposta da grátis.", "entrada": 5, "saida": 3})
    cfg = {"NEXUS_DADOS": str(tmp_path), "ANTHROPIC_API_KEY": "k", "OPENROUTER_API_KEY": "o"}
    sdk.erro = "RateLimitError"
    eventos, fim = _rodar(cfg)
    assert [t for t, _d in eventos if t == "texto"] == []                      # nada ao vivo: o Haiku nem começou
    assert fim[0]["ok"] and fim[0]["texto"] == "Resposta da grátis." and "Claude Haiku 5.5 não respondeu" in fim[0]["troca"]
    # caiu no meio do texto: o que apareceu é trocado pela resposta da grátis, com o motivo
    sdk.erro, sdk.no_meio = "", "APIConnectionError"
    eventos, fim = _rodar(cfg)
    assert [t for t, _d in eventos if t == "texto"] and fim[0]["texto"] == "Resposta da grátis." and fim[0]["troca"]


def test_sem_texto_ao_vivo_com_outro_provedor_comparando_ou_com_o_teto(sdk, tmp_path, monkeypatch):
    monkeypatch.setattr(IA, "_chamar", lambda m, *a: {"texto": f"{m.id} respondeu.", "entrada": 5, "saida": 3})
    cfg = {"NEXUS_DADOS": str(tmp_path), "ANTHROPIC_API_KEY": "k", "OPENROUTER_API_KEY": "o"}
    eventos, fim = _rodar(cfg, ids=("nemotron",))
    assert [t for t, _d in eventos] == ["fim"] and fim[0]["texto"] == "nemotron respondeu." and sdk.pedidos == []
    # o teto do mês atingido: o Haiku não é chamado, a grátis responde (a regra do `perguntar`)
    IA.registrar(cfg, 1, "?", [{"id": "haiku", "ok": True, "texto": "x", "custo_usd": 10.5}], "abc", 100)
    eventos, fim = _rodar(cfg)
    assert [t for t, _d in eventos] == ["fim"] and "teto do mês" in fim[0]["troca"] and sdk.pedidos == []


def test_o_haiku_que_nao_escreve_dentro_do_teto_do_tempo_vai_as_gratis(sdk, tmp_path, monkeypatch):
    # o teto vale para o PRIMEIRO texto (e depois, para o intervalo entre um trecho e o próximo): a chamada que não
    # escreve nada dentro dele é abandonada, e a pergunta segue para as grátis como no `perguntar`
    monkeypatch.setattr(IA, "TEMPO_TOTAL_S", 0.3)
    monkeypatch.setattr(IA, "_chamar", lambda m, *a: {"texto": "Resposta da grátis.", "entrada": 5, "saida": 3})
    sdk.espera = 1.2
    eventos, fim = _rodar({"NEXUS_DADOS": str(tmp_path), "ANTHROPIC_API_KEY": "k", "OPENROUTER_API_KEY": "o"})
    assert [t for t, _d in eventos] == ["fim"] and fim[0]["texto"] == "Resposta da grátis."
    assert "Demorou mais de 0.3 s" in fim[0]["troca"]


def test_o_menor_que_nao_e_o_bloco_das_acoes_aparece(sdk, tmp_path):
    sdk.trechos = ["PR < 70% no dia 3 e ", "meta <b>abaixo</b>.", "\n<acoes>[]</acoes>"]
    eventos, fim = _rodar({"NEXUS_DADOS": str(tmp_path), "ANTHROPIC_API_KEY": "k"})
    assert "".join(d for t, d in eventos if t == "texto").rstrip() == "PR < 70% no dia 3 e meta <b>abaixo</b>."


# ── a rota e a tela ──────────────────────────────────────────────────────────────────────────────────────────────────
def _lidos(resp):
    corpo = resp.get_data(as_text=True)
    return [json.loads(l[6:]) for l in corpo.split("\n") if l.startswith("data: ")]


def test_a_rota_responde_em_pedacos_e_registra(tela, logado, sdk, tmp_path):
    logado.application.config.update(NEXUS_DADOS=str(tmp_path), ANTHROPIC_API_KEY="k")
    r = logado.post("/t/campo/usinas/1/ia/perguntar/fluxo", json={"pergunta": "Por que caiu?", "modelos": ["haiku"]})
    assert r.status_code == 200 and r.mimetype == "text/event-stream" and r.headers["Cache-Control"] == "no-store"
    ev = _lidos(r)
    assert [e["t"] for e in ev][0] == "inicio" and ev[-1]["t"] == "fim"
    assert "".join(e["d"] for e in ev if e["t"] == "texto").startswith("A usina caiu pela rede")
    fim = ev[-1]
    assert fim["ok"] and fim["respostas"][0]["texto"].startswith("A usina caiu pela rede") and "gasto" in fim and "teto" in fim
    assert fim["dossie_tokens"] > 0 and isinstance(fim["relatorios"], list)
    assert "<dossie>\n# Dossiê da usina Altair" in sdk.pedidos[0]["system"][1]["text"]
    linhas = [json.loads(l) for l in next((tmp_path / "ia").glob("perguntas-*.jsonl")).read_text(encoding="utf-8").splitlines()]
    assert len(linhas) == 1 and linhas[0]["modelo"] == "haiku" and linhas[0]["usina_id"] == 1


def test_a_tela_fechada_no_meio_ainda_registra_o_gasto(tela, logado, sdk, tmp_path):
    # a Anthropic cobra pela resposta mesmo com a tela fechada: a resposta termina por trás e entra no registro do mês
    # (é dele que sai o gasto que para o pago no teto)
    logado.application.config.update(NEXUS_DADOS=str(tmp_path), ANTHROPIC_API_KEY="k")
    r = logado.post("/t/campo/usinas/1/ia/perguntar/fluxo", json={"pergunta": "Por que caiu?", "modelos": ["haiku"]})
    pedacos = iter(r.response)
    assert b'"inicio"' in next(pedacos)
    assert not list((tmp_path / "ia").glob("perguntas-*.jsonl")) if (tmp_path / "ia").exists() else True
    r.close()                                                                  # a pessoa saiu da página
    linhas = [json.loads(l) for l in next((tmp_path / "ia").glob("perguntas-*.jsonl")).read_text(encoding="utf-8").splitlines()]
    assert len(linhas) == 1 and linhas[0]["modelo"] == "haiku" and linhas[0]["ok"] and linhas[0]["saida"] == 2231


def test_a_rota_recusa_como_a_de_sempre_e_baixa_o_relatorio_sem_ia(tela, logado, sdk):
    base = "/t/campo/usinas/1/ia/perguntar/fluxo"
    assert logado.post(base, json={"pergunta": " ", "modelos": ["haiku"]}).status_code == 400
    assert logado.post(base, json={"pergunta": "?", "modelos": []}).status_code == 400
    assert logado.post(base, json={"pergunta": "?", "modelos": ["haiku"]}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    r = logado.post(base, json={"pergunta": "me manda o relatório só de chamados", "modelos": ["haiku"]})
    assert r.mimetype == "application/json" and r.get_json()["relatorio"]["temas"] == ["Chamados de garantia"] and sdk.pedidos == []
    assert logado.post("/t/campo/usinas/999/ia/perguntar/fluxo", json={"pergunta": "?", "modelos": ["haiku"]}).status_code == 404


def test_a_caixa_do_prontuario_leva_o_endereco_do_fluxo_e_a_da_carteira_nao(tela, logado):
    h = logado.get("/t/campo/usinas/1/ia?parcial=1").get_data(as_text=True)
    assert 'data-ia-fluxo-url="/t/campo/usinas/1/ia/perguntar/fluxo"' in h
    c = logado.get("/t/campo/usinas/ia?parcial=1").get_data(as_text=True)
    assert "data-ia-url=" in c and "data-ia-fluxo-url" not in c
    js = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "comando" / "ia.js").read_text(encoding="utf-8")
    # a tela lê o corpo em pedaços e desenha o texto ao vivo pelo mesmo `texto()` do cartão definitivo (que escapa tudo
    # antes de virar parágrafo e lista); sem o fluxo, cai na rota de sempre
    for trecho in ("data-ia-fluxo-url", "getReader()", "TextDecoder", "data-ia-vivo", "vivo.innerHTML = texto(escrito", "setTimeout(function () {\n        pintar = 0;"):
        assert trecho in js, trecho
