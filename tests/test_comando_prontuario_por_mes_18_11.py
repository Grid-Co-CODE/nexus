"""O prontuário e o Nexus IA Insights por mês (Levi, 18/11/2026, com o Insights dizendo "Outubro teve 7 desligamentos;
novembro está em 91% da meta"): "O insights e todo o prontuário deve funcionar por mês! Começando por outubro mas quando
eu abrir o prontuário quero sempre no mês vigente, o que fica pendente do último mês ou dia ainda aparece porém em
relação a meta, PR, geração tem que ser do mês atual, o que foi feito no ativo".

1ª parte (este arquivo começa por ela): o diagnóstico do dia fala do MÊS CORRENTE. O dossiê traz o mês a mês desde
outubro, e a IA misturava os dois na situação. O que vem de mês anterior só entra se ainda está em aberto, como
pendência, sem os números de performance daquele mês."""
from nexus.comando import diagnostico as DG


def test_o_diagnostico_do_dia_e_do_mes_corrente_e_o_mes_anterior_so_entra_como_pendencia():
    p = DG.PEDIDO
    regra = next(l for l in p.splitlines() if l.startswith("- O diagnóstico é do MÊS CORRENTE"))
    # os números de performance e o que foi feito são os deste mês
    for trecho in ("meta", "PR", "geração", "disponibilidade", "desligamentos", "o que foi feito"):
        assert trecho in regra, trecho
    # o mês anterior não entra na situação; o que ficou aberto dele entra como pendência, sem a performance de lá
    assert "mês anterior" in regra and "pendência" in regra and "ainda está em aberto" in regra
    # a regra vem antes das listas, junto da situação (é ela que a IA escreve primeiro)
    assert p.index("- O diagnóstico é do MÊS CORRENTE") < p.index("- tem_que_fazer:")


# ── 2ª parte: o mês fechado (outubro em diante), com o Insights do mês e o relatório ─────────────────────────────────
# Levi, 18/11/2026, à pergunta "no mês fechado, o Insights é um diagnóstico do mês feito pela IA ou só os números?":
# "Sim! Com direito a relatório e tudo". O prontuário ganha o seletor de mês (a partir de outubro de 2026, o 1º mês do
# banco); o mês fechado abre a página do fechamento: o Insights do mês (um por usina por mês, guardado), os números do
# mês, o que foi feito no ativo, as paradas e o que segue pendente HOJE, com o PDF do mês. Os dados são os do relatório
# em PDF (`relatorio_usina.dados`), que já recortava o mês.
import json
import re
from datetime import date, datetime

from test_campo_responsaveis import tela  # noqa: E402,F401  (tela é fixture)
from test_campo_visao import banco  # noqa: E402,F401  (banco é fixture)

from nexus.comando import diagnostico_mes as DM
from nexus.comando import ia as IA


def _d():
    """O fechamento de um mês no formato do `relatorio_usina.dados` (só o que o dossiê do mês lê)."""
    return {"uid": 1, "usina": "Exemplo Um", "cliente": "Cliente X", "mes": "2026-10", "mes_txt": "outubro de 2026",
            "ini": date(2026, 10, 1), "fim": date(2026, 10, 31), "corrente": False, "hoje": date(2026, 11, 18), "erros": {},
            "perf": {"meta": {"prod_kwh": 850000.0, "meta_kwh": 1000000.0, "atingimento": 85.0, "pr": 78.4, "pr_meta": 80.0,
                              "dias_cob": 31, "dias_mes": 31},
                     "disp": {"disp": 96.4, "h_perdidas": 13.5, "dias": 31},
                     "oss": {"oss": [{"inicio": "12/10 08:00", "fim": "12/10 15:30", "tipo": "religamento", "escopo": "Usina",
                                      "sol_min": 450, "perda_kwh": 5200.0}]}},
            "religamentos": [
                {"ini": datetime(2026, 10, 12, 8, 0), "tipo": "Usina desligada", "fora": "7 h 30 min", "parou": True,
                 "os": "17540", "protecoes": "27", "relato": "Usina desligada por oscilação na rede da concessionária."},
                {"ini": datetime(2026, 10, 20, 9, 0), "tipo": "Falha de comunicação", "fora": "2 h", "parou": False,
                 "os": "", "protecoes": "", "relato": "Perda de comunicação, sem impacto na geração."},
                {"ini": datetime(2026, 10, 25, 6, 30), "tipo": "Cabine desligada", "fora": "40 min", "parou": True,
                 "os": "17810", "protecoes": "59", "relato": "Cabine 2 desligada por sobretensão."}],
            "rondas": [{"data": "2026-10-07", "tipo": "curta", "sujidade": 3, "vegetacao": 4, "vala": "parcial"},
                       {"data": "2026-10-21", "tipo": "longa", "sujidade": 2, "vegetacao": 4, "vala": "livre"}],
            "manut": {"feitas": [{"tipo": "Preventiva", "tarefas": 12, "os": 2}, {"tipo": "Corretiva", "tarefas": 3, "os": 3}],
                      "abertas": [{"tipo": "Corretiva", "os": 4}], "zeladoria": [date(2026, 10, 15)]},
            "chamados": {"mes": [{"os": 16034, "ini": date(2026, 10, 3), "fim": None, "situacao": "aberto", "dias": 46,
                                  "equip": "Tracker 1 STI", "fabricante": "STI", "componente": "Motor"},
                                 {"os": 15000, "ini": date(2026, 9, 2), "fim": date(2026, 10, 9), "situacao": "concluido",
                                  "dias": 37, "equip": "Inversor 1.2", "fabricante": "Huawei", "componente": "Placa"}],
                         "em_aberto": 3}}


def test_os_meses_vao_do_vigente_ate_outubro_de_2026_e_so_o_fechado_tem_pagina_propria():
    assert DM.meses(date(2026, 11, 18)) == [("2026-11", "Novembro de 2026", True), ("2026-10", "Outubro de 2026", False)]
    assert [m for m, _r, _c in DM.meses(date(2027, 1, 5))] == ["2027-01", "2026-12", "2026-11", "2026-10"]
    assert DM.meses(date(2026, 10, 9)) == [("2026-10", "Outubro de 2026", True)]
    hoje = date(2026, 11, 18)
    assert DM.mes_fechado("2026-10", hoje) == "2026-10"
    for fora in ("2026-11", "2026-09", "2026-13", "outubro", "", None):       # o vigente, o de antes do banco, o lixo
        assert DM.mes_fechado(fora, hoje) is None, fora


def test_o_dossie_do_mes_traz_os_numeros_do_mes_o_que_foi_feito_e_o_que_segue_pendente_hoje():
    t = DM.dossie(_d())
    assert t.startswith("# Fechamento de outubro de 2026 da usina Exemplo Um")
    for linha in ("- Geração: 850,0 MWh, 85% da meta de 1.000,0 MWh (31 de 31 dias medidos)",
                  "- PR do mês: 78,4% (previsto: 80,0%)",
                  "- Disponibilidade do mês: 96,4%; 13,5 h paradas",
                  "- Desligamentos (a geração parou): 2",
                  "- Registros sem a geração parar (não é desligamento): 1",
                  "- Rondas feitas no mês: 2",
                  "- Tarefas de manutenção executadas no mês, pelo registro do App de campo: 15 (Preventiva: 12 em 2 OS; Corretiva: 3 em 3 OS)",
                  "- Zeladoria feita em: 15/10",
                  "- Chamados de garantia finalizados no mês: 1",
                  "- Chamados de garantia em aberto hoje: 3",
                  "- OS em aberto hoje: 4 (Corretiva: 4)"):
        assert linha in t, linha
    assert "12/10 08:00 · Usina desligada · 7 h 30 min · desligamento (a geração parou) · OS 17540 · proteções: 27" in t
    assert "## 4. O que segue pendente hoje (18/11/2026)" in t
    # o tema que não abriu é dito, e o número que falta é "sem dado", nunca zero
    d = _d()
    d["erros"] = {"rondas": "SemBanco"}
    d.pop("rondas")
    d["perf"]["meta"]["pr"] = None
    t = DM.dossie(d)
    assert "- Rondas: sem leitura" in t and "- PR do mês: sem dado" in t and "Rondas feitas no mês: 0" not in t


RESPOSTA_MES = ('<diagnostico>{"situacao": "Outubro fechou em 85% da meta, com 2 desligamentos pela rede.", '
                '"pesou": [{"texto": "Desligamento de 12/10 (7 h 30 min) pela proteção 27", "os": 17540}, "PR de 78,4% contra 80,0%"], '
                '"feito": [{"texto": "2 rondas e 15 tarefas de manutenção", "os": null}], '
                '"pendente": [{"texto": "Chamado da OS 16034 (STI) segue aberto", "os": 16034}, {"texto": "OS inventada", "os": 99999}]}'
                '</diagnostico>')


def test_o_diagnostico_do_mes_e_lido_conferido_e_guardado_um_por_usina_por_mes(tmp_path, monkeypatch):
    d = _d()
    diag = DM.ler(RESPOSTA_MES, d)
    assert diag["situacao"].startswith("Outubro fechou em 85%") and [x["texto"] for x in diag["pesou"]][1] == "PR de 78,4% contra 80,0%"
    assert diag["pesou"][0]["os"] == "17540" and diag["pesou"][0]["os_tipo"] == "religamento"
    assert diag["pendente"][0]["os_tipo"] == "chamado" and diag["pendente"][1]["os"] == ""      # a OS fora do mês não vira link
    assert DM.conferir(diag, d) == []
    errado = DM.ler(RESPOSTA_MES.replace("com 2 desligamentos", "com 16 desligamentos"), d)
    assert "16 desligamentos" in DM.conferir(errado, d)[0] and "2" in DM.conferir(errado, d)[0]
    # gerar: Busca primeiro; o número que não bate refaz pensando; guardado por mês
    cfg = {"NEXUS_DADOS": str(tmp_path), "ANTHROPIC_API_KEY": "k"}
    chamadas = []

    def perguntar(c, ids, dossie, pergunta, *a, **k):
        assert k.get("instrucoes") == DM.INSTRUCOES          # as instruções do mês, não as do chat da usina
        chamadas.append((k.get("pensar"), dossie.startswith("# Fechamento de outubro de 2026"), pergunta == DM.PEDIDO))
        txt = RESPOSTA_MES if k.get("pensar") else RESPOSTA_MES.replace("com 2 desligamentos", "com 16 desligamentos")
        return [{"id": "haiku", "rotulo": "Claude Haiku 5.5", "ok": True, "texto": txt, "custo_usd": 0.001, "ms": 7000}]
    monkeypatch.setattr(IA, "perguntar", perguntar)
    g = DM.gerar(cfg, 1, d)
    assert chamadas == [(False, True, True), (True, True, True)] and g["ok"] and g["refeito"] and not g.get("conferir")
    arq = tmp_path / "ia" / "diagnosticos" / "mes" / "2026-10" / "1.json"
    assert json.loads(arq.read_text(encoding="utf-8"))["mes"] == "2026-10"
    tela_ = DM.para_tela(DM.guardado(cfg, 1, "2026-10"))
    assert tela_["estado"] == "pronto" and tela_["mes"] == "2026-10" and tela_["diag"]["feito"][0]["texto"].startswith("2 rondas")
    assert DM.guardado(cfg, 1, "2026-09") is None and DM.guardado(cfg, 2, "2026-10") is None
    # a recusa não é diagnóstico (no teste em produção, a Castelo do Piauí voltou com "Só respondo sobre a usina deste
    # prontuário", e isso ficou guardado como o Insights de outubro): sem o bloco, refaz pensando; se insistir, é erro,
    # que vale 20 minutos, e a próxima abertura tenta de novo. O guardado sem diagnóstico também é refeito
    chamadas.clear()
    monkeypatch.setattr(IA, "perguntar", lambda c, ids, dossie, pergunta, *a, **k: chamadas.append(k.get("pensar")) or [
        {"id": "haiku", "rotulo": "Claude Haiku 5.5", "ok": True, "texto": "Só respondo sobre a usina deste prontuário, com o dossiê dela."}])
    g = DM.gerar(cfg, 5, d)
    assert chamadas == [False, True] and not g["ok"] and "formato" in g["erro"]
    assert DM.para_tela(DM.guardado(cfg, 5, "2026-10"))["estado"] == "erro"
    arq5 = tmp_path / "ia" / "diagnosticos" / "mes" / "2026-10" / "5.json"
    arq5.write_text(json.dumps({"ok": True, "mes": "2026-10", "texto": "Só respondo sobre a usina.", "diag": None,
                                "versao": DG.VERSAO, "ts": 1}), encoding="utf-8")
    assert DM.guardado(cfg, 5, "2026-10") is None
    assert "sem o nome" not in DM.INSTRUCOES and "DADO" in DM.INSTRUCOES and "fechamento" in DM.INSTRUCOES.lower()
    # o pedido do mês não traz número de exemplo (a lição do "16 desligamentos" do diagnóstico do dia)
    assert not re.search(r"\d{2,}", DM.PEDIDO.split("</diagnostico>", 1)[1])


def test_a_rota_do_diagnostico_com_mes_fechado_faz_uma_vez_e_guarda(tela, logado, monkeypatch, tmp_path):
    logado.application.config.update(NEXUS_DADOS=str(tmp_path), OPENROUTER_API_KEY="k")
    chamadas = []

    def perguntar(c, ids, dossie, pergunta, *a, **k):
        chamadas.append(dossie.splitlines()[0])
        return [{"id": "nemotron", "rotulo": "Nemotron", "ok": True, "texto": '<diagnostico>{"situacao": "Outubro fechou bem."}</diagnostico>'}]
    monkeypatch.setattr(IA, "perguntar", perguntar)
    j = logado.get("/t/campo/usinas/1/ia/diagnostico?mes=2026-10").get_json()
    assert j["estado"] == "pronto" and j["mes"] == "2026-10" and j["diag"]["situacao"] == "Outubro fechou bem."
    assert chamadas[-1] == "# Fechamento de outubro de 2026 da usina Altair" and len(chamadas) == 1
    assert logado.get("/t/campo/usinas/1/ia/diagnostico?mes=2026-10").get_json()["estado"] == "pronto" and len(chamadas) == 1
    assert logado.get("/t/campo/usinas/987654/ia/diagnostico?mes=2026-10").status_code == 404
    # o mês que não é fechado (o vigente, o de antes do banco) cai no diagnóstico do dia, como sempre
    j = logado.get("/t/campo/usinas/1/ia/diagnostico?mes=2026-09").get_json()
    assert "mes" not in j and chamadas[-1].startswith("# Dossiê da usina Altair")


def test_o_prontuario_tem_o_seletor_de_mes_e_o_mes_fechado_abre_o_fechamento(tela, logado):
    h = logado.get("/t/campo/usinas/1").get_data(as_text=True)
    assert 'aria-label="Mês do prontuário"' in h and 'href="/t/campo/usinas/1?mes=2026-10"' in h and 'aria-current="page"' in h
    r = logado.get("/t/campo/usinas/1?mes=2026-10")
    m = r.get_data(as_text=True)
    assert r.status_code == 200 and "Outubro de 2026" in m and "mês fechado" in m
    assert 'data-pm-diag="/t/campo/usinas/1/ia/diagnostico?mes=2026-10"' in m
    assert 'href="/t/campo/usinas/1/relatorio.pdf?mes=2026-10"' in m            # o relatório do mês, em PDF
    assert 'href="/t/campo/usinas/1"' in m                                      # a volta para o mês vigente
    for titulo in ("O mês em números", "O que foi feito no ativo", "Paradas do mês", "Segue pendente hoje"):
        assert titulo in m, titulo
    # o fechamento em texto, o mesmo que a IA lê (para conferir o diagnóstico do mês contra ele)
    r = logado.get("/t/campo/usinas/1/dossie-do-mes.md?mes=2026-10")
    assert r.status_code == 200 and r.mimetype == "text/markdown"
    assert r.get_data(as_text=True).startswith("# Fechamento de outubro de 2026 da usina Altair")
    assert logado.get("/t/campo/usinas/1/dossie-do-mes.md?mes=2026-09").status_code == 404      # só mês fechado
    # o mês que não existe (ou o vigente) abre o prontuário de sempre; a usina que não existe, 404
    assert "Prontuário da usina" in logado.get("/t/campo/usinas/1?mes=2026-09").get_data(as_text=True)
    assert logado.get("/t/campo/usinas/987654?mes=2026-10").status_code == 404
