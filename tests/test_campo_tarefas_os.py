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
    """O REST dublado como o de verdade (sonda de 18/10/2026, 5 GETs): `limit=1` traz o `total` do filtro (o do tipo
    também); a página depois do fim vem com `data: None` e `success: true`. As linhas por (status, tipo), a página pelo
    `start`; as páginas que recusam (429), as que vêm sem dado, as que dizem `success: false`, o total que não vem, o
    total maior que as linhas (a OS que saiu do status no meio da leitura) e o REST que ignora o `start`."""

    def __init__(self, por_chave, recusar=(), sem_dado=(), falha=(), total=None, sem_total=False, ignora_start=False):
        self.por_chave, self.recusar, self.pedidos = por_chave, set(recusar), []
        self.sem_dado, self.falha, self.total = set(sem_dado), set(falha), total or {}
        self.sem_total, self.ignora_start = sem_total, ignora_start

    def __call__(self, path):
        self.pedidos.append(path)
        st = int(path.split("id_status_work_order=")[1].split("&")[0])
        tipo = (unquote(path.split("tasks_log_task_type_main=")[1].split("&")[0])
                if "tasks_log_task_type_main=" in path else "")
        limite = int(path.split("limit=")[1].split("&")[0])
        ini = int(path.split("start=")[1].split("&")[0]) if "start=" in path else 0
        if (st, ini) in self.recusar:
            raise fracttal.Recusado("HTTP 429")
        if (st, ini) in self.falha:
            return {"success": False, "message": "erro do servidor", "data": []}
        linhas = self.por_chave.get((st, tipo), [])
        r = {"success": True, "message": "", "total": self.total.get((st, tipo), len(linhas))}
        if limite == 1:
            if self.sem_total:
                del r["total"]
            return dict(r, data=linhas[:1])
        if self.ignora_start:
            ini = 0
        return dict(r, data=None if (st, ini) in self.sem_dado else (linhas[ini:ini + limite] or None))


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
    app.config.update(GRIDCO_DB_API="http://pg.falso", GRIDCO_SQL_TOKEN="token-de-teste",
                      NEXUS_PESSOA_HMAC="chave-de-teste")
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
    assert sum("id_status_work_order=3" in p and "limit=100" in p for p in ler.pedidos) == 2
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


def test_pagina_sem_dado_antes_do_total_nao_grava(app, banco):
    """Revisão de 18/10/2026: a página que vinha sem a lista antes do fim parava a leitura e gravava o que tinha como
    se fosse tudo (250 tarefas no Fracttal, 100 no banco): "número pela metade não vai para a tela"."""
    ler = _Fracttal({(1, ""): [_w(i, 100 + i, 1) for i in range(1, 251)]}, sem_dado={(1, 100)})
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=ler, agora=AGORA)
    assert "100 de 250" in (rel.get("erro") or "") and banco.syncs == 0


def test_pagina_com_success_false_nao_grava(app, banco):
    ler = _Fracttal({(1, ""): [_w(1, 100, 1)], (2, ""): [_w(2, 200, 2)]}, falha={(2, 0)})
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=ler, agora=AGORA)
    assert "LeituraIncompleta" in (rel.get("erro") or "") and banco.syncs == 0


def test_sem_o_total_nao_le_as_paginas(app, banco):
    ler = _Fracttal({(1, ""): [_w(1, 100, 1)]}, sem_total=True)
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=ler, agora=AGORA)
    assert "total" in (rel.get("erro") or "") and banco.syncs == 0
    assert not any("limit=100" in p for p in ler.pedidos)


def test_pagina_repetida_para_na_segunda(app, banco):
    """O REST que ignora o `start` devolve a mesma página cheia: antes lia até o teto (150 pedidos da cota)."""
    ler = _Fracttal({(1, ""): [_w(i, 100 + i, 1) for i in range(1, 301)]}, ignora_start=True)
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=ler, agora=AGORA)
    assert "repetiu" in (rel.get("erro") or "") and banco.syncs == 0
    assert sum("limit=100" in p for p in ler.pedidos) == 2


def test_o_fim_exato_vem_sem_dado_e_grava(app, banco):
    """Guarda (a sonda de 18/10/2026): com 200 tarefas, a 3ª página vem com `data: None` e é o fim, não um corte."""
    ler = _Fracttal({(1, ""): [_w(i, 100 + i, 1) for i in range(1, 201)]})
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=ler, agora=AGORA)
    assert rel["gravado"][F.ABA] == 200


def test_tarefa_que_muda_de_status_durante_a_leitura_passa_e_fica_medida(app, banco):
    """A OS que sai do status no meio da leitura (~1 min por status) pula as linhas dela numa borda de página: até 1%
    do total passa, e o que faltou fica na qualidade (a Governança mostra)."""
    ler = _Fracttal({(1, ""): [_w(i, 100 + i, 1) for i in range(1, 300)]}, total={(1, ""): 300})   # 299 de 300
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=ler, agora=AGORA)
    assert rel["gravado"][F.ABA] == 299
    assert json.loads(banco.linhas(F.LIVRO, "qualidade")[0]["extra"])["faltaram"] == 1


def test_publica_o_fato_e_a_qualidade_e_confere(app, banco):
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=_tres(), agora=AGORA)
    assert rel["gravado"] == {F.ABA: 3, "qualidade": 1}
    assert (rel["lidas"], rel["linhas"], rel["abertas"], rel["sem_usina"], rel["paginas"]) == (3, 3, 2, 0, 6)
    linhas = banco.linhas(F.LIVRO, F.ABA)
    assert [(r["fracttal_tarefa_id"], r["status_os"], r["usina_id"], r["equipamento_id"]) for r in linhas] == [
        (1, "em_processo", 1, 900), (2, "em_verificacao", 1, 900), (3, "finalizada", 1, 900)]
    q = banco.linhas(F.LIVRO, "qualidade")[0]
    assert (q["fato"], q["linhas"], q["pct_usina"], q["pct_equipamento"], q["usina_por_de_para"]) == (
        "tarefa_os", 3, 100.0, 100.0, 3)
    assert json.loads(q["extra"])["paginas"] == 6


def test_sem_a_lista_do_backoffice_nao_grava_nem_le_o_fracttal(app, banco, monkeypatch):
    """Revisão de 18/10/2026: sem a lista do backoffice (o livro dos motivos não abriu), toda tarefa ia ao banco com
    `do_backoffice` 0, chutado, e a Visão cobrava do supervisor as OS do backoffice. Não grava, e nem gasta o Fracttal."""
    monkeypatch.setattr(P, "_backoffice_hmac", lambda config: None)
    ler = _tres()
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=ler, agora=AGORA)
    assert "backoffice" in (rel.get("recusou") or "") and banco.syncs == 0 and ler.pedidos == []


def test_sem_a_chave_hmac_nao_grava(app, banco):
    app.config["NEXUS_PESSOA_HMAC"] = ""
    ler = _tres()
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=ler, agora=AGORA)
    assert "NEXUS_PESSOA_HMAC" in (rel.get("recusou") or "") and banco.syncs == 0 and ler.pedidos == []


def test_cadastro_vazio_nao_grava(app, banco):
    banco._id("cadastro_nexus", "de_para")["linhas"] = []
    ler = _tres()
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=ler, agora=AGORA)
    assert "de_para" in (rel.get("recusou") or "") and banco.syncs == 0 and ler.pedidos == []


def test_usina_que_liga_abaixo_do_piso_nao_grava(app, banco):
    """O 1º ensaio ligou 98,6% das tarefas a uma usina; abaixo de 90% o de-para ou o cadastro quebrou, e a tela ficaria
    sem as OS da maioria das usinas."""
    sem = {**_w(9, 900, 1), "groups_1_description": "Site que ninguém conhece", "code": "ATIVO SEM CODIGO"}
    ler = _Fracttal({(1, ""): [_w(1, 100, 1), sem, {**sem, "id_work_orders_tasks": 10}]})
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=ler, agora=AGORA)
    assert "33,3%" in (rel.get("recusou") or "") and banco.syncs == 0


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


def test_outra_maquina_gravou_durante_a_leitura_nao_grava_de_novo(app, banco, monkeypatch):
    """Revisão de 18/10/2026: o PC e o servidor acordavam no mesmo :10, os dois liam o Fracttal (~2 min) e os dois
    gravavam. Quem termina depois confere de novo antes de gravar (regra 11: uma gravação por hora)."""
    vezes = []

    def ultima(base, s):
        vezes.append(1)
        return None if len(vezes) == 1 else AGORA + timedelta(minutes=1)
    monkeypatch.setattr(P, "_ultima", ultima)
    with app.app_context():
        rel = P.publicar(app.config, banco, ler=_tres(), agora=AGORA)
    assert "pulou" in rel and banco.syncs == 0 and len(vezes) == 2


def test_cada_maquina_acorda_num_minuto_seu():
    brt = timezone(timedelta(hours=-3))
    assert P._espera_s(datetime(2026, 10, 18, 9, 0, tzinfo=brt), 300) == 15 * 60
    assert P._espera_s(datetime(2026, 10, 18, 9, 14, tzinfo=brt), 300) == 60
    assert P._espera_s(datetime(2026, 10, 18, 9, 16, tzinfo=brt), 300) == 59 * 60
    vistos = {P._desencontro_s() for _ in range(50)}
    assert len(vistos) > 1 and all(0 <= v <= P.DESENCONTRO_MAX_S for v in vistos)
    assert P.MINUTO_DA_HORA * 60 + P.DESENCONTRO_MAX_S < 25 * 60      # antes do sync do App (:25)


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
