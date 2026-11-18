"""O diagnóstico do dia conferido contra o dossiê (Levi, 18/11/2026: "diagnóstico em busca, rode alguns diagnósticos e
bata os dados para ver se a informação está confiável").

A prova, em produção, com o diagnóstico em Busca em 4 usinas de clientes diferentes: os 52 números citados estavam no
dossiê, mas dois diagnósticos erraram a conta dos desligamentos. A Colíder 1 saiu com "16 desligamentos em novembro"
(o dossiê: 11) e a Castelo do Piauí com "16 desligamentos em 30 dias" (o dossiê: 3 em novembro e 2 em outubro). O 16
era o do exemplo que o próprio pedido trazia ("com 17 normalizações e 16 com a geração parada, são 16 desligamentos").
Na Poconé, o dossiê dizia "Última ronda: há 999 dias" (o 999 é a marca interna de "nunca"), e a IA repetiu.

O que muda: o pedido não traz mais número de exemplo; o Nexus confere o número de desligamentos do diagnóstico com a
tabela por mês do dossiê; o que não bate é refeito uma vez com pensamento e, se ainda não bater, a tela avisa; os
diagnósticos feitos com o pedido antigo são refeitos na próxima abertura; e o dossiê diz "nunca rondada" sem o 999."""
import json
import re
from pathlib import Path

from test_campo_responsaveis import tela  # noqa: F401  (tela é fixture)
from test_campo_visao import banco  # noqa: F401  (banco é fixture)
from test_comando_dossie import AGORA, _ctx

from nexus.comando import diagnostico as DG
from nexus.comando import dossie as DS
from nexus.comando import ia as IA

DOSSIE = """# Dossiê da usina Exemplo

## 4. COS

- Normalizações registradas: 20. Desligamento é só a normalização em que a geração parou.

| Mês | Desligamentos (a geração parou) | Sem a geração parar (não é desligamento) | Normalizações no total |
| --- | --- | --- | --- |
| novembro | 11 | 0 | 11 |
| outubro | 6 | 3 | 9 |

- [crítico] 17 religamentos em 30 dias em Usina inteira
"""


def _resp(situacao, **k):
    return '<diagnostico>' + json.dumps(dict({"situacao": situacao, "tem_que_fazer": [], "pode_fazer": [], "pendente": []}, **k),
                                        ensure_ascii=False) + '</diagnostico>'


def test_o_pedido_nao_traz_numero_de_exemplo():
    # o "16" do exemplo virou o número de desligamentos de duas usinas: regra se escreve sem número
    regra = next(l for l in DG.PEDIDO.splitlines() if "Desligamento é só a parada em que a geração parou" in l)
    assert not re.search(r"\d", regra), regra
    assert "tabela por mês" in regra and "mês corrente" in regra
    assert "16 desligamentos" not in DG.PEDIDO and "17 normalizações" not in DG.PEDIDO


def test_o_pedido_tem_as_regras_dos_outros_erros_da_prova():
    # Castelo do Piauí: "Programar a ronda: a zeladoria está vencida desde 04/11 e a última ronda foi hoje"
    ronda = next(l for l in DG.PEDIDO.splitlines() if l.startswith("- Ronda:"))
    assert "atrasada ou sem cobertura" in ronda and "Zeladoria vencida não é ronda" in ronda
    # Colíder 1: o dossiê dizia "Extintores: sem dado", e o diagnóstico pediu "Extintores sem conferência"
    sem = next(l for l in DG.PEDIDO.splitlines() if l.startswith('- O que o dossiê marca como "sem dado"'))
    assert "não vira item" in sem


def test_a_conferencia_le_a_tabela_por_mes_e_aponta_o_numero_que_nao_bate():
    assert DG.desligamentos_do_dossie(DOSSIE) == {"novembro": 11, "outubro": 6}
    assert DG.desligamentos_do_dossie("# Dossiê sem COS") == {}
    certo = DG.ler(_resp("Meta em 82%, com 11 desligamentos em novembro e 17 religamentos em 30 dias."), DOSSIE)
    assert DG.conferir(certo, DOSSIE) == []
    errado = DG.ler(_resp("Meta em 82%, com 16 desligamentos da geração em novembro.",
                          pendente=[{"item": "Análise dos 16 desligamentos em 30 dias", "os": None}]), DOSSIE)
    falhas = DG.conferir(errado, DOSSIE)
    assert len(falhas) == 1 and "16 desligamentos" in falhas[0] and "novembro: 11" in falhas[0] and "outubro: 6" in falhas[0]
    # "1 desligamento" no singular também é conferido; sem a tabela no dossiê, não há o que conferir
    assert DG.conferir(DG.ler(_resp("Teve 1 desligamento no mês."), DOSSIE), DOSSIE)
    assert DG.conferir(errado, "# Dossiê sem COS") == []
    assert DG.conferir(None, DOSSIE) == []


def _ia_de_mentira(monkeypatch, respostas):
    chamadas = []

    def perguntar(cfg, ids, dossie, pergunta, *a, **k):
        chamadas.append(k.get("pensar"))
        return [{"id": "haiku", "rotulo": "Claude Haiku 5.5", "ok": True, "texto": respostas[min(len(chamadas), len(respostas)) - 1],
                 "custo_usd": 0.001, "ms": 7000}]
    monkeypatch.setattr(IA, "perguntar", perguntar)
    return chamadas


def test_o_numero_que_nao_bate_e_refeito_pensando_e_se_insistir_a_tela_avisa(tmp_path, monkeypatch):
    cfg = {"NEXUS_DADOS": str(tmp_path), "ANTHROPIC_API_KEY": "k"}
    # a 1ª (Busca) erra, a 2ª (pensando) acerta: vale a 2ª, sem aviso
    chamadas = _ia_de_mentira(monkeypatch, [_resp("Com 16 desligamentos em novembro."), _resp("Com 11 desligamentos em novembro.")])
    d = DG.gerar(cfg, 1, DOSSIE, 100, "2026-11-18")
    assert chamadas == [False, True] and d["diag"]["situacao"] == "Com 11 desligamentos em novembro." and not d.get("conferir")
    assert d["refeito"] is True and d["versao"] == DG.VERSAO
    linhas = next((tmp_path / "ia").glob("perguntas-*.jsonl")).read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 2                                    # as duas chamadas entram no registro (e no teto)
    # as duas erram: fica a última, e a tela recebe o aviso do que não bateu
    chamadas = _ia_de_mentira(monkeypatch, [_resp("Com 16 desligamentos em novembro.")])
    d = DG.gerar(cfg, 2, DOSSIE, 100, "2026-11-18")
    assert chamadas == [False, True] and "16 desligamentos" in d["conferir"][0]
    assert "16 desligamentos" in DG.para_tela(DG.guardado(cfg, 2, "2026-11-18"))["conferir"][0]
    # a que acerta de primeira não é refeita
    chamadas = _ia_de_mentira(monkeypatch, [_resp("Com 11 desligamentos em novembro.")])
    d = DG.gerar(cfg, 3, DOSSIE, 100, "2026-11-18")
    assert chamadas == [False] and not d.get("refeito") and "conferir" not in DG.para_tela(d)


def test_o_diagnostico_do_pedido_antigo_e_refeito_e_ainda_serve_de_anterior(tmp_path, monkeypatch):
    cfg = {"NEXUS_DADOS": str(tmp_path), "ANTHROPIC_API_KEY": "k"}
    _ia_de_mentira(monkeypatch, [_resp("Com 11 desligamentos em novembro.")])
    DG.gerar(cfg, 1, DOSSIE, 100, "2026-11-18")
    arq = tmp_path / "ia" / "diagnosticos" / "2026-11-18" / "1.json"
    assert DG.guardado(cfg, 1, "2026-11-18")["versao"] == DG.VERSAO
    velho = json.loads(arq.read_text(encoding="utf-8"))
    velho.pop("versao")                                        # o guardado de antes desta mudança não tinha a versão
    arq.write_text(json.dumps(velho), encoding="utf-8")
    assert DG.guardado(cfg, 1, "2026-11-18") is None           # é refeito na próxima abertura
    assert DG.anterior(cfg, 1, "2026-11-19")["dia"] == "2026-11-18"      # mas serve de "anterior" enquanto o novo é feito


def test_a_usina_nunca_rondada_nao_sai_com_999_dias(tela, logado):
    ctx = _ctx(logado)
    ctx["cu"]["u"]["ronda"] = {"dias": 999, "ultima": None, "tipo": None, "obs": "nunca rondada"}
    linha = next(l for l in DS.montar(ctx, AGORA)["texto"].splitlines() if l.startswith("- Última ronda:"))
    assert linha == "- Última ronda: nunca rondada" and "999" not in linha


def test_a_tela_mostra_o_aviso_da_conferencia():
    js = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "comando" / "prontuario.js").read_text(encoding="utf-8")
    assert "j.conferir" in js and "A conferir:" in js
