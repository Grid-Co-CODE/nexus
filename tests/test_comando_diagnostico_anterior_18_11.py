"""O Nexus IA Insights abre na hora com o último diagnóstico enquanto o de hoje é feito (Levi, 18/11/2026: "demora 40
segundos para uma resposta após eu abrir a usina"; à proposta "mostrar o de ontem enquanto o de hoje fica pronto":
"faz o A").

O diagnóstico é um por usina por dia, feito na primeira abertura do prontuário, com pensamento: quem abre primeiro
esperava a IA olhando o parecer de sempre. Agora a rota, enquanto responde "preparando", manda junto o último
diagnóstico que deu certo (o de ontem; o de sexta, na segunda), e a tela o mostra com a data dele até o de hoje chegar.
Diagnóstico com mais de 7 dias não serve: a usina já é outra."""
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from test_campo_responsaveis import tela  # noqa: F401  (tela é fixture)
from test_campo_visao import banco  # noqa: F401  (banco é fixture)

from nexus.comando import diagnostico as DG
from nexus.comando import ia as IA

DIAG = {"situacao": "Usina com 3 pontos críticos.", "tem_que_fazer": [{"texto": "Programar a recarga do extintor", "os": ""}],
        "pode_fazer": [], "pendente": []}


def _guarda(tmp_path, usina_id, dia, ok=True, diag=DIAG, hora="10:57:00"):
    pasta = tmp_path / "ia" / "diagnosticos" / dia
    pasta.mkdir(parents=True, exist_ok=True)
    d = {"usina_id": usina_id, "dia": dia, "ts": time.time(), "gerado_em": f"{dia}T{hora}-03:00", "ok": ok,
         "rotulo": "Claude Haiku 5.5", "erro": "" if ok else "limite de uso", "versao": DG.VERSAO}
    if ok:
        d["diag"] = diag
    (pasta / f"{usina_id}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def test_o_anterior_e_o_ultimo_que_deu_certo_de_ate_7_dias(tmp_path):
    cfg = {"NEXUS_DADOS": str(tmp_path)}
    assert DG.anterior(cfg, 1, "2026-11-18") is None                       # nunca foi feito
    _guarda(tmp_path, 1, "2026-11-10")                                     # 8 dias: velho demais
    assert DG.anterior(cfg, 1, "2026-11-18") is None
    _guarda(tmp_path, 1, "2026-11-13")                                     # sexta
    _guarda(tmp_path, 1, "2026-11-16", ok=False)                           # o que falhou não serve
    _guarda(tmp_path, 2, "2026-11-17")                                     # o de outra usina não serve
    _guarda(tmp_path, 1, "2026-11-18")                                     # o do próprio dia não é "anterior"
    d = DG.anterior(cfg, 1, "2026-11-18")
    assert d["dia"] == "2026-11-13" and d["diag"]["situacao"] == "Usina com 3 pontos críticos."
    _guarda(tmp_path, 1, "2026-11-17", diag=dict(DIAG, situacao="Ontem."))
    assert DG.anterior(cfg, 1, "2026-11-18")["diag"]["situacao"] == "Ontem."      # o mais recente vence
    # a pasta que não é dia e o arquivo estragado não derrubam
    (tmp_path / "ia" / "diagnosticos" / "lixo").mkdir()
    (tmp_path / "ia" / "diagnosticos" / "2026-11-17" / "1.json").write_text("{", encoding="utf-8")
    assert DG.anterior(cfg, 1, "2026-11-18")["dia"] == "2026-11-13"
    assert DG.anterior({}, 1, "2026-11-18") is None                        # sem a pasta de dados


def test_a_rota_manda_o_anterior_enquanto_prepara_o_de_hoje(tela, logado, monkeypatch, tmp_path):
    logado.application.config.update(NEXUS_DADOS=str(tmp_path), OPENROUTER_API_KEY="k")
    cfg = logado.application.config
    monkeypatch.setattr(IA, "perguntar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("chamou a IA")))
    hoje = DG.hoje()
    ontem = f"{datetime.fromisoformat(hoje) - timedelta(days=1):%Y-%m-%d}"
    assert DG.travar(cfg, 1, hoje)                                         # outro pedido já está fazendo o de hoje
    # sem diagnóstico anterior: só o "preparando", como antes
    assert logado.get("/t/campo/usinas/1/ia/diagnostico").get_json() == {"estado": "preparando"}
    _guarda(tmp_path, 1, ontem)
    j = logado.get("/t/campo/usinas/1/ia/diagnostico").get_json()
    assert j["estado"] == "preparando"
    ant = j["anterior"]
    assert ant["estado"] == "pronto" and ant["diag"]["situacao"] == "Usina com 3 pontos críticos."
    assert ant["dia"] == ontem and ant["data"] == f"{ontem[8:10]}/{ontem[5:7]}" and ant["hora"] == "10:57"
    # o de hoje ficou pronto: volta só ele, sem o anterior
    DG.soltar(cfg, 1, hoje)
    _guarda(tmp_path, 1, hoje, diag=dict(DIAG, situacao="Hoje."))
    j = logado.get("/t/campo/usinas/1/ia/diagnostico").get_json()
    assert j["estado"] == "pronto" and j["diag"]["situacao"] == "Hoje." and "anterior" not in j


def test_a_tela_mostra_o_anterior_com_a_data_dele_ate_o_de_hoje_chegar():
    js = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "comando" / "prontuario.js").read_text(encoding="utf-8")
    for trecho in ("j.anterior", "desenharDiag(el, j.anterior)", "O de hoje está sendo feito"):
        assert trecho in js, trecho
