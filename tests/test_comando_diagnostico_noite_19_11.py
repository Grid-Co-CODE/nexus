"""O Insights de madrugada, em lote (Levi, 19/11/2026).

As decisões dele: "Insights de madrugada: gerar de noite, fora do período solar, para todas as usinas. Se o dossiê de uma
usina estiver idêntico ao do dia anterior, reaproveite o insight em vez de chamar o Haiku"; e, com a conta na mão (132
chamadas por noite, US$ 12 a 16 por mês direto ou a metade em lote): "Madrugada em lote, com teto de US$ 12. O lote só
garante a resposta em até 24 h, então comece logo depois da meia-noite e, se às 6h ainda faltar alguma usina, gere essas
direto. Registre quantas caíram nessa rede de segurança".

Nenhum teste vai à rede: o cliente da Anthropic é um dublê do `client.messages.batches`."""
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from nexus.comando import diagnostico as DG
from nexus.comando import diagnostico_noite as NT
from nexus.comando import ia as IA

DIA, ONTEM = "2026-11-20", "2026-11-19"
SETORES = [{"setor_id": 1, "nome": "Engenharia", "temas": []}]


def _dossie(uid, corpo="tudo em dia", hora="00:12"):
    return (f"# Dossiê da usina U{uid}\n\n- Documento: dossiê (formato 7)\n- Gerado em: 20/11/2026 às {hora}, horário de Brasília\n\n"
            f"## 3. Performance\n\n- Meta do mês: {corpo}\n")


def _msg(situacao="Usina em dia."):
    texto = "<diagnostico>" + json.dumps({"situacao": situacao, "tem_que_fazer": [], "pode_fazer": [], "pendente": []},
                                         ensure_ascii=False) + "</diagnostico>"
    return SimpleNamespace(stop_reason="end_turn", model="claude-haiku-5-5", content=[SimpleNamespace(type="text", text=texto)],
                           usage=SimpleNamespace(input_tokens=9000, output_tokens=1000, cache_read_input_tokens=0,
                                                 cache_creation_input_tokens=0))


class Lotes:
    """O `client.messages.batches` de mentira: guarda o que foi criado e devolve o que o teste mandar."""
    def __init__(self):
        self.criados, self.status, self.resultados, self.cancelados = [], {}, {}, []
        self.messages = SimpleNamespace(batches=self)

    def create(self, requests):
        lid = f"lote{len(self.criados) + 1}"
        self.criados.append((lid, list(requests)))
        self.status[lid] = "in_progress"
        return SimpleNamespace(id=lid, processing_status="in_progress")

    def retrieve(self, lid):
        return SimpleNamespace(id=lid, processing_status=self.status[lid])

    def results(self, lid):
        return iter(self.resultados.get(lid, []))

    def cancel(self, lid):
        self.cancelados.append(lid)

    def acabar(self, lid, **por_usina):
        self.status[lid] = "ended"
        self.resultados[lid] = [SimpleNamespace(custom_id=cid, result=(SimpleNamespace(type="succeeded", message=v) if v is not None
                                                                         else SimpleNamespace(type="errored", error=SimpleNamespace(type="api_error"))))
                                for cid, v in por_usina.items()]


@pytest.fixture
def cfg(tmp_path):
    return {"NEXUS_DADOS": str(tmp_path), "ANTHROPIC_API_KEY": "k", "NEXUS_IA_DIAGNOSTICO_MODELO": "haiku"}


def _guardar(cfg, uid, dia, sha, situacao="De ontem.", **k):
    d = {"usina_id": uid, "dia": dia, "ts": 1, "gerado_em": f"{dia}T00:40:00-03:00", "ok": True, "modelo": "haiku",
         "rotulo": "Claude Haiku 5.5", "versao": DG.VERSAO, "dossie_sha": sha,
         "diag": {"situacao": situacao, "tem_que_fazer": [], "pode_fazer": [], "pendente": []}, **k}
    p = DG._pasta(cfg, dia)
    p.mkdir(parents=True, exist_ok=True)
    (p / f"{uid}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def _ids(req):
    return [r["custom_id"] for r in req]


# ── o dossiê idêntico ────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_assinatura_ignora_so_a_hora_em_que_o_dossie_foi_gerado():
    a, b = _dossie(1, hora="00:12"), _dossie(1, hora="23:59").replace("20/11/2026", "19/11/2026")
    assert NT.assinatura(a) == NT.assinatura(b) and len(NT.assinatura(a)) == 64
    assert NT.assinatura(a) != NT.assinatura(_dossie(1, corpo="68%"))


def test_o_diagnostico_feito_na_hora_guarda_a_assinatura_do_dossie(cfg, monkeypatch):
    # sem ela, o insight feito de dia (pela abertura da usina) nunca seria reaproveitado na noite seguinte
    monkeypatch.setattr(IA, "perguntar", lambda *a, **k: [{"id": "haiku", "rotulo": "Claude Haiku 5.5", "ok": True,
                                                           "texto": '<diagnostico>{"situacao": "Ok."}</diagnostico>'}])
    monkeypatch.setattr(IA, "registrar", lambda *a, **k: None)
    d = DG.gerar(cfg, 1, _dossie(1), 100, DIA)
    assert d["dossie_sha"] == NT.assinatura(_dossie(1)) == DG.guardado(cfg, 1, DIA)["dossie_sha"]


def test_o_dossie_identico_ao_de_ontem_reaproveita_o_insight_sem_chamar_o_haiku(cfg):
    cli = Lotes()
    _guardar(cfg, 1, ONTEM, NT.assinatura(_dossie(1)))                   # igual ao de hoje
    _guardar(cfg, 2, ONTEM, NT.assinatura(_dossie(2, corpo="antes")))    # mudou
    e = NT.preparar(cfg, DIA, [1, 2, 3], lambda uid: (_dossie(uid), 100), SETORES, cli)
    assert e["usinas"] == {"1": "reaproveitado", "2": "lote_a", "3": "lote_a"} and e["fase"] == "lote_a"
    assert len(cli.criados) == 1 and _ids(cli.criados[0][1]) == ["u2", "u3"]
    hoje = DG.guardado(cfg, 1, DIA)
    assert hoje["diag"]["situacao"] == "De ontem." and hoje["reaproveitado_de"] == ONTEM and hoje["dia"] == DIA
    assert DG.para_tela(hoje)["sem_mudanca_desde"] == "19/11"            # a tela diz de quando é
    assert DG.guardado(cfg, 2, DIA) is None


def test_o_reaproveitado_de_varios_dias_guarda_o_dia_em_que_foi_feito(cfg):
    _guardar(cfg, 1, ONTEM, NT.assinatura(_dossie(1)), reaproveitado_de="2026-11-17")
    NT.preparar(cfg, DIA, [1], lambda uid: (_dossie(uid), 100), SETORES, Lotes())
    assert DG.guardado(cfg, 1, DIA)["reaproveitado_de"] == "2026-11-17"


def test_o_pedido_do_lote_e_o_mesmo_da_chamada_direta_em_busca(cfg):
    cli = Lotes()
    NT.preparar(cfg, DIA, [5], lambda uid: (_dossie(uid), 100), SETORES, cli)
    p = cli.criados[0][1][0]["params"]
    haiku = next(m for m in IA.MODELOS_PADRAO if m.id == "haiku")
    direto = IA._pedido_anthropic(haiku, IA.para_o_modelo(_dossie(5)), IA._mensagens(None, DG.PEDIDO + DG.lista_de_temas(SETORES)),
                                  IA._contexto(["Engenharia"], ""), "", False)
    assert p == direto and p["thinking"] == {"type": "disabled"} and "stream" not in p and "fallbacks" not in p


def test_quem_ja_tem_o_insight_de_hoje_e_quem_nao_tem_dossie_ficam_fora_do_lote(cfg):
    cli = Lotes()
    _guardar(cfg, 1, DIA, "x", situacao="Feito à 00:05 por quem abriu a usina.")
    e = NT.preparar(cfg, DIA, [1, 2], lambda uid: None if uid == 2 else (_dossie(uid), 100), SETORES, cli)
    assert e["usinas"] == {"1": "ja_tinha", "2": "sem_dossie"} and e["fase"] == "colhido" and not cli.criados


def test_com_o_teto_do_mes_atingido_a_noite_nao_manda_o_lote(cfg, monkeypatch):
    monkeypatch.setattr(IA, "gasto_do_mes", lambda cfg, agora=None: 12.01)
    cli = Lotes()
    e = NT.preparar(cfg, DIA, [1], lambda uid: (_dossie(uid), 100), SETORES, cli)
    assert e["fase"] == "teto" and not cli.criados
    assert IA.TETO_PADRAO_USD == 12.0                                      # o teto que o Levi definiu em 19/11/2026


def test_sem_o_haiku_com_chave_nao_ha_lote(tmp_path):
    e = NT.preparar({"NEXUS_DADOS": str(tmp_path), "NEXUS_IA_DIAGNOSTICO_MODELO": "haiku"}, DIA, [1],
                    lambda uid: (_dossie(uid), 100), SETORES, Lotes())
    assert e["fase"] == "sem_ia"


# ── colher o lote ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_lote_que_nao_acabou_espera_e_o_que_acabou_vira_o_insight_do_dia(cfg):
    cli = Lotes()
    NT.preparar(cfg, DIA, [1, 2], lambda uid: (_dossie(uid), 100), SETORES, cli)
    assert NT.colher(cfg, DIA, SETORES, cli)["fase"] == "lote_a" and DG.guardado(cfg, 1, DIA) is None
    cli.acabar("lote1", u1=_msg("Usina 1 em dia."), u2=None)             # a 2 voltou com erro
    e = NT.colher(cfg, DIA, SETORES, cli)
    assert e["fase"] == "colhido" and e["usinas"] == {"1": "pronto", "2": "falhou"}
    d = DG.guardado(cfg, 1, DIA)
    assert d["ok"] and d["diag"]["situacao"] == "Usina 1 em dia." and d["lote"] is True and d["versao"] == DG.VERSAO
    assert d["dossie_sha"] == NT.assinatura(_dossie(1)) and DG.para_tela(d)["estado"] == "pronto"
    assert DG.guardado(cfg, 2, DIA) is None                               # fica para a rede de segurança


def test_a_resposta_do_lote_e_registrada_pela_metade_do_preco(cfg):
    cli = Lotes()
    NT.preparar(cfg, DIA, [1], lambda uid: (_dossie(uid), 100), SETORES, cli)
    cli.acabar("lote1", u1=_msg())
    NT.colher(cfg, DIA, SETORES, cli)
    linhas = [json.loads(l) for l in IA._arquivo_do_mes(cfg).read_text(encoding="utf-8").splitlines()]
    assert len(linhas) == 1 and linhas[0]["quem"] == "diagnostico-da-noite" and linhas[0]["pergunta"].startswith("[diagnóstico do dia]")
    haiku = next(m for m in IA.MODELOS_PADRAO if m.id == "haiku")
    assert linhas[0]["custo_usd"] == pytest.approx(IA.custo(haiku, 9000, 1000) * 0.5)


def test_o_que_nao_confere_e_refeito_num_segundo_lote_pensando(cfg):
    # a tabela do dossiê diz 2 desligamentos em novembro; o diagnóstico em Busca disse 9
    tabela = ("\n## 4. COS\n\n| Mês | Desligamentos (a geração parou) | Sem a geração parar (não é desligamento) | Normalizações no total |\n"
              "| --- | --- | --- | --- |\n| novembro | 2 | 0 | 2 |\n")
    cli = Lotes()
    NT.preparar(cfg, DIA, [1], lambda uid: (_dossie(uid) + tabela, 100), SETORES, cli)
    cli.acabar("lote1", u1=_msg("Usina com 9 desligamentos em novembro."))
    e = NT.colher(cfg, DIA, SETORES, cli)
    assert e["fase"] == "lote_b" and e["usinas"] == {"1": "lote_b"} and _ids(cli.criados[1][1]) == ["u1"]
    assert "thinking" not in cli.criados[1][1][0]["params"]              # o 2º lote pensa
    assert DG.guardado(cfg, 1, DIA)["conferir"]                           # enquanto isso, vale o 1º, marcado "A conferir"
    cli.acabar("lote2", u1=_msg("Usina com 2 desligamentos em novembro."))
    e = NT.colher(cfg, DIA, SETORES, cli)
    d = DG.guardado(cfg, 1, DIA)
    assert e["fase"] == "colhido" and e["usinas"] == {"1": "pronto"} and d["refeito"] is True and "conferir" not in d
    assert d["diag"]["situacao"].startswith("Usina com 2")


# ── a rede de segurança das 6h ───────────────────────────────────────────────────────────────────────────────────────
def test_as_6h_o_que_faltar_e_gerado_direto_e_a_conta_fica_registrada(cfg, monkeypatch):
    cli, diretos = Lotes(), []

    def gerar(cfg_, uid, dossie, tokens=0, dia=None, setores=None):
        diretos.append(uid)
        _guardar(cfg_, uid, dia, NT.assinatura(dossie), situacao="Direto.")
        return DG.guardado(cfg_, uid, dia)
    monkeypatch.setattr(DG, "gerar", gerar)
    _guardar(cfg, 4, ONTEM, NT.assinatura(_dossie(4)))
    NT.preparar(cfg, DIA, [1, 2, 3, 4], lambda uid: (_dossie(uid), 100), SETORES, cli)
    cli.acabar("lote1", u1=_msg(), u2=None)                               # a 3 nem voltou
    NT.colher(cfg, DIA, SETORES, cli)
    e = NT.rede(cfg, DIA, [1, 2, 3, 4], lambda uid: (_dossie(uid), 100), SETORES, cli)
    assert diretos == [2, 3] and e["fase"] == "fim"
    assert e["contas"] == {"usinas": 4, "reaproveitados": 1, "ja_tinham": 0, "pelo_lote": 1, "refeitos": 0, "rede": 2,
                           "sem_insight": 0}
    assert NT.resumo(cfg)[0] == {"dia": DIA, "fase": "fim", **e["contas"]}


def test_as_6h_o_lote_que_ainda_roda_e_cancelado_e_tudo_que_falta_vai_direto(cfg, monkeypatch):
    cli, diretos = Lotes(), []
    monkeypatch.setattr(DG, "gerar", lambda c, uid, *a, **k: diretos.append(uid) or {"ok": False, "erro": "limite"})
    NT.preparar(cfg, DIA, [1, 2], lambda uid: (_dossie(uid), 100), SETORES, cli)
    e = NT.rede(cfg, DIA, [1, 2], lambda uid: (_dossie(uid), 100), SETORES, cli)
    assert cli.cancelados == ["lote1"] and diretos == [1, 2]
    assert e["contas"]["rede"] == 2 and e["contas"]["sem_insight"] == 2   # tentou direto e não saiu: fica dito


# ── o relógio ────────────────────────────────────────────────────────────────────────────────────────────────────────
def _passo(cfg, hora, cli, usinas=(1,)):
    agora = datetime.fromisoformat(f"{DIA}T{hora}:00-03:00")
    return NT.passo(cfg, agora, lambda: list(usinas), lambda uid: (_dossie(uid), 100), lambda: SETORES, lambda: cli)


def test_o_relogio_da_noite(cfg, monkeypatch):
    cli = Lotes()
    monkeypatch.setattr(DG, "gerar", lambda c, uid, dossie, tokens=0, dia=None, setores=None: _guardar(c, uid, dia, "s") or {"ok": True})
    assert _passo(cfg, "00:05", cli) == "fora da janela" and NT.estado(cfg, DIA) is None       # antes das 00:10
    assert _passo(cfg, "00:10", cli) == "preparou" and NT.estado(cfg, DIA)["fase"] == "lote_a"
    assert _passo(cfg, "00:15", cli) == "esperando o lote"
    cli.acabar("lote1", u1=_msg())
    assert _passo(cfg, "01:00", cli) == "colheu" and NT.estado(cfg, DIA)["fase"] == "colhido"
    assert _passo(cfg, "03:00", cli) == "esperando as 6h"
    assert _passo(cfg, "06:00", cli) == "rede de segurança" and NT.estado(cfg, DIA)["fase"] == "fim"
    assert _passo(cfg, "06:05", cli) == "noite fechada"


def test_a_noite_que_nao_rodou_ainda_tem_a_rede_das_6h(cfg, monkeypatch):
    # o servidor fora do ar de madrugada: às 6h não há lote, e as usinas são geradas direto
    cli, diretos = Lotes(), []
    monkeypatch.setattr(DG, "gerar", lambda c, uid, *a, **k: diretos.append(uid) or {"ok": True})
    assert _passo(cfg, "05:40", cli, usinas=(1, 2)) == "fora da janela"                         # tarde demais para o lote
    assert _passo(cfg, "06:10", cli, usinas=(1, 2)) == "rede de segurança" and diretos == [1, 2] and not cli.criados
    assert _passo(cfg, "09:00", cli, usinas=(1, 2)) == "noite fechada"
    assert NT.estado(cfg, DIA)["contas"]["rede"] == 2


def test_depois_das_7h_sem_noite_nada_roda_e_o_dia_segue_sob_demanda(cfg):
    cli = Lotes()
    assert _passo(cfg, "07:30", cli) == "fora da janela" and NT.estado(cfg, DIA) is None and not cli.criados


# ── o laço, a tela e o painel ────────────────────────────────────────────────────────────────────────────────────────
def test_o_laco_nao_liga_no_pc_nem_com_a_noite_desligada(app):
    nada = (lambda: [], lambda uid: None, lambda: [])
    for chave in ("NEXUS_CAMPO_AQUECER", "NEXUS_IA_NOITE"):
        NT._LACO["thread"] = None
        app.config.update(NEXUS_CAMPO_AQUECER="1", NEXUS_IA_NOITE="1")
        app.config[chave] = "0"
        NT.ligar(app, *nada)
        assert NT._LACO["thread"] is None, chave


def test_quem_liga_a_noite_e_o_instalar_e_nunca_o_create_app():
    import inspect

    import nexus
    from nexus import campo
    assert "noite_laco.ligar(app)" in inspect.getsource(campo.instalar)
    assert "noite_laco" not in inspect.getsource(nexus.create_app)


def test_o_painel_de_uso_mostra_as_noites_com_a_rede_de_seguranca(logado, app, monkeypatch):
    monkeypatch.setattr(NT, "resumo", lambda cfg, noites=7: [{"dia": "2026-11-20", "fase": "fim", "usinas": 144, "reaproveitados": 12,
                                                             "ja_tinham": 1, "pelo_lote": 124, "refeitos": 9, "rede": 7, "sem_insight": 0}])
    html = logado.get("/t/campo/usinas/ia/uso").get_data(as_text=True)
    assert "Insights de madrugada" in html and "Rede de segurança" in html and ">20/11<" in html
    assert ">124<" in html and ">7<" in html and "fechada" in html


def test_a_tela_diz_desde_quando_o_dossie_nao_muda():
    js = (Path(__file__).resolve().parent.parent / "nexus" / "static" / "comando" / "prontuario.js").read_text(encoding="utf-8")
    assert "j.sem_mudanca_desde" in js and "não mudou desde" in js
