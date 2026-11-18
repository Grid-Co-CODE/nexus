"""O painel de uso da Nexus IA (18/11/2026). O gasto e o tempo de cada resposta só apareciam no rodapé do cartão, um a um:
não dava para saber quanto do teto de US$ 10 o diagnóstico diário consome, nem comparar Busca com Pensamento. O mapa da
Nexus IA pôs o painel entre o que faltava, e o Levi mandou fazer ("o resto faça!").

O painel lê o registro do mês que já existe (`<NEXUS_DADOS>/ia/perguntas-AAAA-MM.jsonl`, uma linha por resposta) e
mostra só contas: por dia, por origem (pergunta na usina, na carteira, diagnóstico do dia, diagnóstico do mês), por modo
e por modelo, com a projeção do mês contra o teto. Não mostra o texto das perguntas nem quem perguntou. Só o
administrador abre."""
import json
from datetime import datetime, timedelta, timezone

from test_campo_responsaveis import tela  # noqa: F401  (tela é fixture)
from test_campo_visao import banco  # noqa: F401  (banco é fixture)

from nexus.comando import ia as IA

BRT = timezone(timedelta(hours=-3))
AGORA = datetime(2026, 11, 18, 14, 0, tzinfo=BRT)


def _linha(em, pergunta, modelo="haiku", ok=True, ms=7000, custo=0.003, saida=400, modo="busca", erro="", quem="abc123"):
    return {"em": em, "usina_id": 1, "quem": quem, "pergunta": pergunta, "modelo": modelo, "ok": ok, "texto": "resposta secreta",
            "erro": erro, "ms": ms, "entrada": 16, "saida": saida, "cache_lido": 18000, "custo_usd": custo, "modo": modo}


def _registro(tmp_path):
    linhas = [
        _linha("2026-11-17T09:00:00-03:00", "Por que caiu?", modo="pensamento", ms=17100, custo=0.0034, saida=2231),
        _linha("2026-11-18T10:00:00-03:00", "Por que caiu?", ms=5000, custo=0.0025),
        _linha("2026-11-18T10:05:00-03:00", "E o PR?", ms=3000, custo=0.0005),
        _linha("2026-11-18T11:00:00-03:00", "[carteira] quais usinas preocupam?", ms=9000, custo=0.004),
        _linha("2026-11-18T11:48:00-03:00", "[diagnóstico do dia]", ms=7000, custo=0.004, quem="diagnostico-do-dia"),
        _linha("2026-11-18T11:49:00-03:00", "[diagnóstico do dia]", ms=49000, custo=0.009, modo="pensamento", quem="diagnostico-do-dia"),
        _linha("2026-11-18T12:31:00-03:00", "[diagnóstico do mês 2026-10]", ms=18000, custo=0.003, quem="diagnostico-do-mes"),
        _linha("2026-11-18T08:39:00-03:00", "[diagnóstico do dia]", ok=False, ms=60000, custo=0, modo="",
               erro="Demorou mais de 60 s para responder.", quem="diagnostico-do-dia"),
        _linha("2026-11-18T08:40:00-03:00", "[diagnóstico do dia]", modelo="nemotron", ms=40000, custo=0, modo="", quem="diagnostico-do-dia")]
    pasta = tmp_path / "ia"
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "perguntas-2026-11.jsonl").write_text("\n".join(json.dumps(l, ensure_ascii=False) for l in linhas) + "\nlixo\n",
                                                   encoding="utf-8")
    return {"NEXUS_DADOS": str(tmp_path)}


def test_o_uso_do_mes_por_dia_origem_modo_e_modelo(tmp_path):
    u = IA.uso(_registro(tmp_path), AGORA)
    assert u["respostas"] == 9 and u["mes"] == "novembro de 2026"
    assert u["gasto"] == round(0.0034 + 0.0025 + 0.0005 + 0.004 + 0.004 + 0.009 + 0.003, 4) and u["teto"] == IA.TETO_PADRAO_USD
    # a projeção do mês: o gasto até hoje (dia 18) levado aos 30 dias do mês
    assert u["projecao"] == round(u["gasto"] / 18 * 30, 2)
    dias = {d["nome"]: d for d in u["dias"]}
    assert list(dias) == ["18/11", "17/11"] and dias["18/11"]["n"] == 8 and dias["17/11"]["custo"] == 0.0034
    origens = {o["nome"]: o for o in u["origens"]}
    assert set(origens) == {"Pergunta na usina", "Pergunta na carteira", "Diagnóstico do dia", "Diagnóstico do mês"}
    assert origens["Pergunta na usina"]["n"] == 3 and origens["Diagnóstico do dia"]["n"] == 4
    assert origens["Diagnóstico do dia"]["falhas"] == 1 and origens["Diagnóstico do dia"]["custo"] == 0.013
    # o tempo médio é o das respostas que deram certo (a que estourou os 60 s não entra na média)
    assert origens["Diagnóstico do dia"]["s_medio"] == round((7 + 49 + 40) / 3, 1)
    modos = {m["nome"]: m for m in u["modos"]}
    assert modos["Busca"]["n"] == 5 and modos["Pensamento"]["n"] == 2 and modos["Pensamento"]["s_medio"] == round((17.1 + 49) / 2, 1)
    assert modos["Pensamento"]["saida_media"] == round((2231 + 400) / 2) and "Sem modo (IA grátis ou falha)" in modos
    modelos = {m["nome"]: m for m in u["modelos"]}
    assert modelos["haiku"]["n"] == 8 and modelos["haiku"]["falhas"] == 1 and modelos["nemotron"]["n"] == 1
    assert u["falhas"] == [("Demorou mais de 60 s para responder", 1)]
    # sem o registro (ou sem a pasta): tudo zerado, nunca erro
    assert IA.uso({"NEXUS_DADOS": str(tmp_path / "vazio")}, AGORA)["respostas"] == 0 and IA.uso({"TESTING": True}, AGORA)["respostas"] == 0


def test_o_painel_abre_so_para_o_administrador_e_nao_mostra_pergunta_nem_pessoa(tela, logado, tmp_path, monkeypatch):
    cfg = _registro(tmp_path)
    logado.application.config.update(NEXUS_DADOS=cfg["NEXUS_DADOS"])
    monkeypatch.setattr(IA, "_agora_brt", lambda: AGORA)
    h = logado.get("/t/campo/usinas/ia/uso").get_data(as_text=True)
    for trecho in ("Uso da Nexus IA", "novembro de 2026", "Diagnóstico do dia", "Pergunta na carteira", "Busca", "Pensamento",
                   "Demorou mais de 60 s para responder", "18/11"):
        assert trecho in h, trecho
    for proibido in ("Por que caiu?", "quais usinas preocupam", "abc123", "resposta secreta"):
        assert proibido not in h, proibido
    with logado.session_transaction() as s:
        s["admin"] = False
    assert logado.get("/t/campo/usinas/ia/uso").status_code == 403
