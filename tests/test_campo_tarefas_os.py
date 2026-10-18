"""As tarefas das OS do Fracttal no banco (18/10/2026, Levi: "pegando tudo do Fracttal ou Nexus, sem fontes
externas!"): o laço que lê o REST (dublado aqui) e grava `nexus_os · fato_tarefa_os` no banco falso. O fato é puro
(`nexus/dados/fato_tarefa_os.py`). Leitura incompleta não grava: "número pela metade não vai para a tela"."""
import json
from datetime import date, datetime, timedelta, timezone
from urllib.parse import unquote

import pytest
from pg_falso import ApiPGFalsa

from nexus.campo import fracttal
from nexus.campo import tarefas_os as P
from nexus.dados import fato_tarefa_os as F

USINAS = [{"usina_id": 1, "nome": "Altair", "codigo": "THPN-ALT100"}]
DE_PARA = [{"usina_id": 1, "sistema": "Fracttal · Classificação 1", "chave_externa": "Thopen - Altair 1 - SP"}]
HOJE = date(2026, 10, 18)
AGORA = datetime(2026, 10, 18, 20, 0, tzinfo=timezone(timedelta(hours=-3)))


def _w(tarefa, folio, st, tipo="Corretiva", estado="NO_STARTED", fim=None):
    return {"id_work_orders_tasks": tarefa, "wo_folio": str(folio), "id_work_order": 50000 + folio,
            "id_status_work_order": str(st), "task_status": estado, "tasks_log_task_type_main": tipo,
            "date_maintenance": "2026-10-01T10:00:00+00:00", "creation_date": "2026-09-20T12:00:00+00:00",
            "final_date": fim, "wo_final_date": fim, "code": "THPN-ALT100-INVR1",
            "groups_1_description": "Thopen - Altair 1 - SP", "description": "Troca de fusível",
            "tasks_duration": 3600, "user_assigned": "Fulana Responsável", "personnel_description": "Ciclano"}


class _Fracttal:
    """O REST dublado: as linhas por (status, tipo), a página pelo `start`, e as páginas que recusam (429)."""

    def __init__(self, por_chave, recusar=()):
        self.por_chave, self.recusar, self.pedidos = por_chave, set(recusar), []

    def __call__(self, path):
        self.pedidos.append(path)
        st = int(path.split("id_status_work_order=")[1].split("&")[0])
        tipo = (unquote(path.split("tasks_log_task_type_main=")[1].split("&")[0])
                if "tasks_log_task_type_main=" in path else "")
        ini = int(path.split("start=")[1].split("&")[0])
        if (st, ini) in self.recusar:
            raise fracttal.Recusado("HTTP 429")
        return {"data": self.por_chave.get((st, tipo), [])[ini:ini + 100]}


@pytest.fixture
def rapido(monkeypatch):
    monkeypatch.setattr(P, "PAUSA_S", 0)
    monkeypatch.setattr(P, "ESPERA_RECUSA_S", 0)
    monkeypatch.setattr(P, "_backoffice_hmac", lambda config: set())


@pytest.fixture
def banco(app, rapido):
    api = ApiPGFalsa()
    api.workbooks["cadastro_nexus"] = {}
    for aba, linhas in (("usinas", USINAS), ("de_para", DE_PARA)):
        cab = list(linhas[0])
        api._id("cadastro_nexus", aba)["linhas"] = [{"headers": cab, "values": [l.get(c) for c in cab]} for l in linhas]
    api.workbooks["nexus_equipamentos"] = {}
    api._id("nexus_equipamentos", "dim_equipamento")["linhas"] = [
        {"headers": ["equipamento_id", "codigo", "na_foto"], "values": [900, "THPN-ALT100-INVR1", 1]}]
    app.config.update(GRIDCO_DB_API="http://pg.falso", GRIDCO_SQL_TOKEN="token-de-teste")
    return api


def _tres():
    return _Fracttal({(1, ""): [_w(1, 100, 1)], (2, ""): [_w(2, 200, 2)],
                      (3, "Zeladoria"): [_w(3, 300, 3, tipo="Zeladoria", estado="DONE",
                                           fim="2026-10-10T12:00:00+00:00")]})


def test_le_os_status_1_e_2_inteiros_e_a_zeladoria_feita(rapido):
    ler = _tres()
    rows = P.ler_fracttal(ler, HOJE)
    assert sorted(r["id_work_orders_tasks"] for r in rows) == [1, 2, 3]
    assert {p.split("id_status_work_order=")[1][0] for p in ler.pedidos} == {"1", "2", "3"}
    # os abertos de todo tipo; das finalizadas, só a zeladoria (o tipo vai na URL)
    assert all(("tasks_log_task_type_main=" in p) == ("id_status_work_order=3" in p) for p in ler.pedidos)
    assert any("tasks_log_task_type_main=Zeladoria" in p for p in ler.pedidos)


def test_a_zeladoria_para_quando_a_pagina_inteira_passou_dos_90_dias(rapido):
    nova, velha = "2026-10-01T12:00:00+00:00", "2026-06-01T12:00:00+00:00"       # o piso é 20/07/2026
    zel = ([_w(1000 + i, 1000 + i, 3, tipo="Zeladoria", estado="DONE", fim=nova) for i in range(99)]
           + [_w(1099, 1099, 3, tipo="Zeladoria", estado="DONE", fim=velha)]      # uma velha numa página nova
           + [_w(2000 + i, 2000 + i, 3, tipo="Zeladoria", estado="DONE", fim=velha) for i in range(200)])
    ler = _Fracttal({(3, "Zeladoria"): zel})
    rows = P.ler_fracttal(ler, HOJE)
    # a 1ª página (com uma velha) não para; a 2ª, toda velha, para; a 3ª nunca é pedida
    assert sum("id_status_work_order=3" in p for p in ler.pedidos) == 2
    # e o que passou do piso fica fora da janela de 90 dias
    assert len(rows) == 99 and all(r["final_date"] == nova for r in rows)


def test_leitura_incompleta_nao_grava(app, banco):
    ler = _Fracttal({(1, ""): [_w(1, 100, 1)]}, recusar={(2, 0)})                 # a página do status 2 sempre recusa
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=ler, agora=AGORA)
    assert "LeituraIncompleta" in rel["erro"] and banco.syncs == 0
    assert sum("id_status_work_order=2" in p for p in ler.pedidos) == P.TENTATIVAS


def test_teto_de_paginas_nao_corta_calado(app, banco, monkeypatch):
    monkeypatch.setattr(P, "PAGINAS_MAX", 2)
    ler = _Fracttal({(1, ""): [_w(i, 100 + i, 1) for i in range(1, 301)]})          # 3 páginas cheias
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=ler, agora=AGORA)
    assert "LeituraIncompleta" in rel["erro"] and banco.syncs == 0


def test_publica_o_fato_e_a_qualidade_e_confere(app, banco):
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=_tres(), agora=AGORA)
    assert rel["gravado"] == {F.ABA: 3, "qualidade": 1}
    assert (rel["lidas"], rel["linhas"], rel["abertas"], rel["sem_usina"], rel["paginas"]) == (3, 3, 2, 0, 3)
    linhas = banco.linhas(F.LIVRO, F.ABA)
    assert [(r["fracttal_tarefa_id"], r["status_os"], r["usina_id"], r["equipamento_id"]) for r in linhas] == [
        (1, "em_processo", 1, 900), (2, "em_verificacao", 1, 900), (3, "finalizada", 1, 900)]
    q = banco.linhas(F.LIVRO, "qualidade")[0]
    assert (q["fato"], q["linhas"], q["pct_usina"], q["pct_equipamento"], q["usina_por_de_para"]) == (
        "tarefa_os", 3, 100.0, 100.0, 3)
    assert json.loads(q["extra"])["paginas"] == 3


def test_sem_a_lista_do_backoffice_grava_e_diz(app, banco, monkeypatch):
    monkeypatch.setattr(P, "_backoffice_hmac", lambda config: None)               # o livro dos motivos não abriu
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=_tres(), agora=AGORA)
    assert rel["gravado"][F.ABA] == 3
    assert json.loads(banco.linhas(F.LIVRO, "qualidade")[0]["extra"])["backoffice"] is None


def test_o_banco_que_falha_nao_gasta_o_fracttal(app, banco, monkeypatch):
    """O ensaio de 18/10/2026 leu 89 páginas do Fracttal (2 min da cota da empresa) e caiu depois, lendo o cadastro do
    banco (tempo esgotado): o banco vai antes, e o Fracttal só é lido quando o resto da volta pode terminar."""
    from nexus.dados import livros
    ler = _tres()

    def banco_fora(*a, **k):
        raise ConnectionError("o banco não respondeu")
    monkeypatch.setattr(livros, "ler", banco_fora)
    with app.app_context(), pytest.raises(ConnectionError):
        P.publicar(app.config, banco, ler=ler, agora=AGORA)
    assert ler.pedidos == [] and banco.syncs == 0


def test_outra_maquina_gravou_ha_menos_de_50_min_pula(app, banco, monkeypatch):
    monkeypatch.setattr(P, "_ultima", lambda base, s: AGORA - timedelta(minutes=20))
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=_tres(), agora=AGORA)
    assert "pulou" in rel and banco.syncs == 0


def test_fracttal_vazio_nao_apaga_o_livro_e_sem_token_nao_grava(app, banco):
    banco.workbooks[F.LIVRO] = {}
    banco._id(F.LIVRO, F.ABA)["linhas"] = [{"headers": F.CAB_TAREFA_OS, "values": [1] + [None] * 17}]
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=_Fracttal({}), agora=AGORA)
        assert "recusou" in rel and banco.syncs == 0 and len(banco.linhas(F.LIVRO, F.ABA)) == 1
        app.config["GRIDCO_SQL_TOKEN"] = ""
        assert "erro" in P.publicar(app.config, banco, ler=_Fracttal({}), agora=AGORA)


def test_o_laco_desliga_com_a_chave(app):
    app.config["NEXUS_OS_PUBLICAR"] = "0"
    P.ligar(app)
    assert P._LACO["thread"] is None
