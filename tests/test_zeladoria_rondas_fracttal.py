"""As rondas da zeladoria lidas do Fracttal pelo Nexus (etapa 5, 06/11/2026): a regra da função `fracttal-sync` do Radar,
gravada pelo gravador da Zeladoria. Fracttal falso; nomes fictícios."""
from datetime import datetime, timezone

import pytest

from nexus.cadastro.cifra import Cofre, gerar_chave
from nexus.zeladoria import gravacao
from nexus.zeladoria import rondas_fracttal as RF

AGORA = datetime(2026, 11, 6, 15, 0, tzinfo=timezone.utc)


def _os(folio, usina="Cliente A - Usina 1 - SP", tipo="Curta", nota="Sujidade dos módulos: 3\nVegetação: 2\nQualidade 90%",
        status="3", criada="2026-11-06T10:00:00+00:00"):
    return {"wo_folio": folio, "id_work_order": 100 + int(folio), "description": f"Ronda {tipo} — {usina} — X",
            "groups_1_description": usina, "code": "CA-U1", "task_note": nota, "personnel_description": "Fulano de Tal",
            "id_status_work_order": status, "creation_date": criada, "initial_date": criada}


def _estado(rondas=(), sync=None):
    tipos_r = {c: "text" for c in ("folio", "data", "data_hora", "tipo", "usina_texto", "usina_chave", "codigo_ativo",
                                   "tecnico", "descricao", "resumo", "atualizado_em", "fotos_salvas_em", "fotos_erro")}
    tipos_r.update({c: "integer" for c in ("sujidade", "vegetacao", "qualidade", "status", "fotos_qtd", "fotos_tentativas")})
    tipos_r["id_work_order"] = "bigint"
    tipos_u = {c: "text" for c in ("usina_chave", "usina_texto", "folio", "data", "tipo", "tecnico", "codigo_ativo",
                                   "folio_nota", "data_nota", "fotos_salvas_em")}
    tipos_u.update({c: "integer" for c in ("qualidade", "sujidade", "vegetacao", "total_rondas", "fotos_qtd", "fotos_tentativas")})
    tipos_s = {c: "text" for c in ("id", "recente_ate", "ultima_sync_recente", "backfill_ate", "backfill_concluido_em",
                                   "em_execucao_desde", "ultima_execucao", "ultimo_erro")}
    tipos_s.update({c: "integer" for c in ("backfill_start", "backfill_vazios", "paginas_lidas", "rondas_gravadas")})
    tipos_s["backfill_concluido"] = "boolean"
    abas = {"fracttal_rondas": list(rondas), "fracttal_ultimas": RF.ultimas(rondas), "fracttal_sync": [sync or {
        "id": "principal", "recente_ate": "2026-11-06T11:00:00+00:00", "ultima_sync_recente": "2026-11-06T11:00:00+00:00",
        "paginas_lidas": 10, "rondas_gravadas": 5}], "log": []}
    return {"abas": abas, "tipos": {"fracttal_rondas": tipos_r, "fracttal_ultimas": tipos_u, "fracttal_sync": tipos_s,
                                    "log": {"id": "bigint", "acao": "text"}},
            "chaves": {"fracttal_rondas": "folio", "fracttal_ultimas": "usina_chave", "fracttal_sync": "id", "log": "id"},
            "versao": 0, "versoes": {}}


@pytest.fixture
def g(tmp_path):
    g = gravacao.Gravador(base="http://pg.falso", token="t", sessao=None, cofre=Cofre(gerar_chave()),
                          diario=tmp_path / "diario.jsonl")
    g.carregar(_estado([RF.para_linha(_os("10", criada="2026-11-01T10:00:00+00:00"), "2026-11-01T12:00:00+00:00")]))
    return g


def _fracttal(paginas):
    pedidos = []

    def ler(path):
        pedidos.append(path)
        return {"data": paginas[len(pedidos) - 1] if len(pedidos) <= len(paginas) else []}
    return ler, pedidos


def test_a_linha_da_ronda_e_a_do_radar():
    l = RF.para_linha(_os("11", usina="Usina Ânima - Cidade - PE"), "agora")
    assert (l["usina_chave"], l["tipo"], l["sujidade"], l["vegetacao"], l["qualidade"], l["status"]) == \
           ("usina anima - cidade - pe", "Curta", 3, 2, 90, 3)
    assert l["data"] == "2026-11-06" and RF.eh_ronda(_os("1")) and not RF.eh_ronda({"description": "Roçagem — UFV"})
    assert RF.eh_ronda({"description": "Inspeção de ronda", "tasks_log_types_2_description": "Zeladoria"})
    assert RF.para_linha({"wo_folio": 2, "description": "Ronda Curta"}, "agora") is None        # sem usina


def test_a_volta_grava_so_o_que_mudou_e_a_ultima_de_cada_usina(g):
    # a página traz a OS 10 igual (não muda), a 12 nova e uma OS que não é ronda
    ler, pedidos = _fracttal([[_os("10", criada="2026-11-01T10:00:00+00:00"), _os("12"),
                               {"wo_folio": 99, "description": "Corretiva — inversor"}]])
    r = RF.sincronizar(g, ler=ler, agora=AGORA, forcar=True)
    assert r["ok"] and r["gravadas"] == 1 and r["paginas"] == 1
    assert "since=2026-11-05T11:00:00-00" in pedidos[0] and "type_date=creation_date" in pedidos[0]   # o corte − 1 dia
    ult = g.estado["abas"]["fracttal_ultimas"]
    assert len(ult) == 1 and ult[0]["folio"] == "12" and ult[0]["total_rondas"] == 2
    st = g.estado["abas"]["fracttal_sync"][0]
    assert st["ultima_sync_recente"] == "2026-11-06T15:00:00+00:00" and st["rondas_gravadas"] == 6
    assert not [l for l in g.estado["abas"]["log"] if l.get("acao") == "excluir-definitivo"]          # dado do sistema


def test_a_cada_2_horas_e_o_botao_forca(g):
    ler, pedidos = _fracttal([[_os("12")]])
    assert RF.sincronizar(g, ler=ler, agora=AGORA.replace(hour=12))["pulou"] is True      # 1 h depois do último corte
    assert pedidos == []
    assert RF.sincronizar(g, ler=ler, agora=AGORA.replace(hour=12), forcar=True)["gravadas"] == 1


def test_a_cancelada_sai_da_ultima_e_a_nota_e_da_ultima_com_nivel(g):
    ler, _p = _fracttal([[_os("12", status="4"), _os("13", nota="sem nível", criada="2026-11-06T12:00:00+00:00")]])
    RF.sincronizar(g, ler=ler, agora=AGORA, forcar=True)
    u = g.estado["abas"]["fracttal_ultimas"][0]
    assert u["folio"] == "13" and u["folio_nota"] == "10" and u["sujidade"] == 3 and u["total_rondas"] == 2


def test_o_limite_da_cota_fica_registrado_e_nada_se_perde(g):
    from nexus.campo import fracttal

    def ler(path):
        raise fracttal.Recusado("o Fracttal recusou por excesso de pedidos (HTTP 429); a fila não foi lida")
    r = RF.sincronizar(g, ler=ler, agora=AGORA, forcar=True)
    assert r["ok"] is False and "Limite de consultas" in r["erro"]
    st = g.estado["abas"]["fracttal_sync"][0]
    assert st["ultimo_erro"].startswith("Limite") and st["recente_ate"] == "2026-11-06T11:00:00+00:00"   # o corte fica

