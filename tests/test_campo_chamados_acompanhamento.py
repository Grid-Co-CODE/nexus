"""Os chamados de garantia no banco (12/10/2026, Levi: "O nexus é um ambiente centralizado e precisamos ter os dados se
conversando!"): as OS de acompanhamento de chamado do Fracttal em `nexus_chamados · fato_chamado`. O fato é puro
(`nexus/dados/fato_chamado.py`); o publicador lê o REST (dublado aqui) e grava no banco falso."""
from datetime import date, datetime, timedelta, timezone

import pytest
from pg_falso import ApiPGFalsa

from nexus.campo import chamados_acompanhamento as P
from nexus.dados import fato_chamado as F
from nexus.dados import fatos as D

USINAS = [{"usina_id": 1, "nome": "Altair", "codigo": "THPN-ALT100"},
          {"usina_id": 3, "nome": "Coração 1", "codigo": "THPN-COR100"}]
DE_PARA = [{"usina_id": 1, "sistema": "Fracttal · Classificação 1", "chave_externa": "Thopen - Altair 1 - SP"}]
HOJE = date(2026, 10, 12)


def _w(folio, st, criada, fim=None, nota="[CHAMADO] Acompanhamento — STI · Estrutura Trackers\nOS de campo: 1",
       site="Thopen - Altair 1 - SP", code="THPN-ALT100-ETKR1", desc="[Tracker 1] - Acompanhamento de chamado STI",
       tipo="Administrativa", **kw):
    d = {"wo_folio": str(folio), "id_status_work_order": str(st), "creation_date": criada, "final_date": fim,
         "wo_final_date": fim, "task_note": nota, "groups_1_description": site, "code": code, "description": desc,
         "tasks_log_task_type_main": tipo, "created_by": "Fulana da Silva", "personnel_description": "Ciclano"}
    d.update(kw)
    return d


def _lig():
    return D.Ligador(USINAS, DE_PARA, [], {})


def test_so_a_os_de_acompanhamento_entra_com_os_ids_e_sem_pessoa():
    rows = [
        _w(16034, 1, "2026-10-10T02:30:00+00:00"),                         # 02:30Z = dia 09 em Brasília
        _w(16034, 1, "2026-10-10T05:00:00+00:00"),                         # a mesma OS em outra linha: vale a mais antiga
        _w(16040, 2, "2026-10-01T12:00:00+00:00", fim="2026-10-03T12:00:00+00:00", site="Coração", code="THPN-COR100-CABN1",
           nota="[CHAMADO] Acompanhamento — Convert · Cabine"),
        _w(15000, 3, "2026-09-01T12:00:00+00:00", fim="2026-09-02T12:30:00+00:00"),       # concluída há 40 dias: entra
        _w(14000, 3, "2026-06-01T12:00:00+00:00", fim="2026-06-02T12:00:00+00:00"),       # há mais de 90 dias: sai
        _w(16100, 4, "2026-10-05T12:00:00+00:00"),                                        # cancelada: sai, como no quadro
        _w(16200, 1, "2026-10-05T12:00:00+00:00", nota="", desc="Relatório mensal"),       # Administrativa qualquer: sai
        _w(16300, 1, "2026-10-06T12:00:00+00:00", nota="", site="Usina Nova - XX", code="ZZZ999"),  # pelo título; sem usina
    ]
    out = F.linhas(rows, _lig(), {"THPN-ALT100-ETKR1": 900}, HOJE)
    d = {r[0]: dict(zip(F.CAB_CHAMADO, r)) for r in out}
    assert list(d) == [15000, 16034, 16040, 16300]
    assert d[16034] == {"os": 16034, "data_id_abertura": 20261009, "data_id_fim": None, "usina_id": 1,
                        "usina_ligada_por": "de-para do Fracttal", "site_fracttal": "Thopen - Altair 1 - SP",
                        "equipamento_id": 900, "equipamento_ligado_por": "código do ativo",
                        "codigo_ativo": "THPN-ALT100-ETKR1", "situacao": "aberto", "fabricante": "STI",
                        "componente": "Estrutura Trackers", "duracao_min": None, "abertura_por": "os",
                        "status": None, "status_por": None}
    assert (d[16040]["usina_id"], d[16040]["usina_ligada_por"], d[16040]["situacao"]) == (3, "código do ativo", "verificacao")
    assert (d[16040]["fabricante"], d[16040]["componente"], d[16040]["duracao_min"]) == ("Convert", "Cabine", 2880)
    assert d[15000]["situacao"] == "concluido" and d[15000]["duracao_min"] == 1470
    assert d[16300]["usina_id"] is None and d[16300]["fabricante"] is None and d[16300]["site_fracttal"] == "Usina Nova - XX"
    # nada de pessoa nem da nota (a API do banco tem leitura aberta)
    assert "Fulana" not in str(out) and "Ciclano" not in str(out) and "OS de campo" not in str(out)


def test_marca_e_reconhecimento():
    assert F.marca("[CHAMADO] Acompanhamento — Sungrow · Inversor\nresto") == ("Sungrow", "Inversor")
    assert F.marca("nota sem marca") == ("", "")
    assert F.eh_os3({"task_note": "[CHAMADO] Acompanhamento — X · Y"})
    assert F.eh_os3({"description": "[Inv 1] - Acompanhamento de chamado X", "tasks_log_task_type_main": "Administrativa"})
    assert not F.eh_os3({"description": "[Inv 1] - Acompanhamento de chamado X", "tasks_log_task_type_main": "Corretiva"})


class _Fracttal:
    """O REST dublado: devolve as linhas por status e anota os caminhos pedidos."""

    def __init__(self, por_status):
        self.por_status, self.pedidos = por_status, []

    def __call__(self, path):
        self.pedidos.append(path)
        st = int(path.split("id_status_work_order=")[1].split("&")[0])
        ini = int(path.split("start=")[1])
        return {"data": self.por_status.get(st, [])[ini:ini + 100]}


@pytest.fixture
def banco(app):
    api = ApiPGFalsa()
    for aba, linhas in (("usinas", USINAS), ("de_para", DE_PARA), ("equipes", [])):
        api.workbooks["cadastro_nexus"] = {}
        cab = list(linhas[0]) if linhas else ["vazio"]
        api._id("cadastro_nexus", aba)["linhas"] = [{"headers": cab, "values": [l.get(c) for c in cab]} for l in linhas]
    api.workbooks["nexus_equipamentos"] = {}
    api._id("nexus_equipamentos", "dim_equipamento")["linhas"] = [
        {"headers": ["equipamento_id", "codigo", "descricao"], "values": [900, "THPN-ALT100-ETKR1", "Tracker 1 STI"]}]
    app.config.update(GRIDCO_DB_API="http://pg.falso", GRIDCO_SQL_TOKEN="token-de-teste")
    return api


AGORA = datetime(2026, 10, 12, 20, 0, tzinfo=timezone(timedelta(hours=-3)))


def test_publica_e_confere(app, banco):
    ler = _Fracttal({1: [_w(16034, 1, "2026-10-10T13:00:00+00:00")],
                     2: [_w(16040, 2, "2026-10-01T12:00:00+00:00", fim="2026-10-03T12:00:00+00:00")]})
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=ler, agora=AGORA)
    assert rel["gravado"] == {F.ABA: 2} and (rel["linhas"], rel["abertas"], rel["sem_usina"]) == (2, 1, 0)
    linhas = banco.linhas(F.LIVRO, F.ABA)
    assert [(r["os"], r["situacao"], r["equipamento_id"]) for r in linhas] == [(16034, "aberto", 900), (16040, "verificacao", 900)]
    # só GET no Fracttal, a tarefa Administrativa, os três status
    assert all("tasks_log_task_type_main=Administrativa" in p for p in ler.pedidos)
    assert {p.split("id_status_work_order=")[1][0] for p in ler.pedidos} == {"1", "2", "3"}


def test_outra_maquina_gravou_ha_menos_de_50_min_pula(app, banco, monkeypatch):
    monkeypatch.setattr(P, "_ultima", lambda base, s: AGORA - timedelta(minutes=20))
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=_Fracttal({}), agora=AGORA)
    assert "pulou" in rel and banco.syncs == 0


def test_fracttal_vazio_nao_apaga_o_livro_e_sem_token_nao_grava(app, banco):
    banco.workbooks[F.LIVRO] = {}
    banco._id(F.LIVRO, F.ABA)["linhas"] = [{"headers": F.CAB_CHAMADO, "values": [16034] + [None] * 12}]
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=_Fracttal({}), agora=AGORA)
        assert "recusou" in rel and banco.syncs == 0 and len(banco.linhas(F.LIVRO, F.ABA)) == 1
        app.config["GRIDCO_SQL_TOKEN"] = ""
        assert "erro" in P.publicar(app.config, banco, ler=_Fracttal({}), agora=AGORA)


def test_as_concluidas_param_na_primeira_pagina_mais_velha_que_90_dias(monkeypatch):
    monkeypatch.setattr(P, "PAUSA_S", 0)
    velhas = [_w(10000 + i, 3, "2026-05-01T12:00:00+00:00", fim="2026-05-02T12:00:00+00:00") for i in range(100)]
    ler = _Fracttal({3: velhas * 3})
    P.ler_fracttal(ler, HOJE)
    assert sum("id_status_work_order=3" in p for p in ler.pedidos) == 1


def test_o_laco_desliga_com_a_chave(app):
    app.config["NEXUS_CHAMADOS_PUBLICAR"] = "0"
    P.ligar(app)
    assert P._LACO["thread"] is None
