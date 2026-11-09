"""A Visão do cliente, fase 1 (05/11/2026; a sugestão "Visão do cliente: Comando com a síntese das usinas dele" e o "Sim,
fase 1" do Levi): a síntese POR CLIENTE no servidor, com o que o cliente pode ver, e a tela da Usinas 360°. Banco falso
do test_campo_responsaveis (Thopen: Altair e Brodowski 1; Outro Cliente: Coração 1)."""
from datetime import date, datetime, timedelta

import pytest
from test_campo_responsaveis import HOJE, _did, _tarefa, manut, tela  # noqa: F401  (fixtures)
from test_campo_visao import _aba, banco  # noqa: F401

from nexus.campo import manutencao as M
from nexus.campo import visao
from nexus.campo import visao_cliente as VC


def _u(uid, nome, prod=None, meta=None, ating=None):
    return {"usina_id": uid, "usina": nome, "cidade": nome, "uf": "SP", "equipe": "",
            "meta": {"prod_kwh": prod, "meta_kwh": meta, "atingimento": ating}}


def _tr(nome, status, causa="Normal", lida="2026-11-05 14:20:00"):
    return {"usina": nome, "status": status, "causa": causa, "ultima_leitura": lida}


# ── a conta ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_status_para_quem_le():
    assert VC.status_da_usina(None)["rotulo"] == "Sem leitura"                     # nunca parada
    assert VC.status_da_usina(_tr("x", "ok", "Sem sol na usina (fora da janela solar)"))["rotulo"] == "Sem sol"
    assert VC.status_da_usina(_tr("x", "ok"))["rotulo"] == "Gerando"
    assert VC.status_da_usina(_tr("x", "desligada", "Usina desligada · OS 1 de religamento aberta"))["rotulo"] == "Parada"
    assert VC.status_da_usina(_tr("x", "sem_producao"))["tom"] == "critico"
    assert VC.status_da_usina(_tr("x", "atencao"))["rotulo"] == "Gerando com perda"
    assert VC.status_da_usina(_tr("x", "sem_comm"))["rotulo"] == "Sem comunicação"
    assert VC.status_da_usina(_tr("x", "critico"))["lido"] == "14:20"
    # a última leitura de outro dia leva a data (na bancada: "última leitura 22:43" era de ontem)
    assert VC.status_da_usina(_tr("x", "sem_comm", lida="2026-11-04 22:43:00"), date(2026, 11, 5))["lido"] == "04/11 22:43"
    assert VC.status_da_usina(_tr("x", "sem_comm", lida="2026-11-05 17:52:00"), date(2026, 11, 5))["lido"] == "17:52"


def test_o_tipo_para_quem_le():
    assert VC._tipo("corretiva_emergencial") == "corretiva emergencial" and VC._tipo("Inspeção") == "inspeção"
    assert VC._tipo("MPA") == "preventiva (MPA)" and VC._tipo("mps") == "preventiva (MPS)"   # plano do PCM
    assert VC._tipo("Limpeza de módulos") == "Limpeza de módulos"                   # o resto como o PCM escreve


def test_a_sintese_soma_o_cliente_e_poe_quem_pede_atencao_primeiro():
    hoje = date(2026, 11, 5)
    # metas diferentes de propósito: a do cliente é a SOMA das gerações sobre a soma das metas, não a média dos %
    usinas = [_u(1, "Alfa", 1010, 1000, 101.0), _u(2, "Bravo", 1624, 2000, 81.2), _u(3, "Charlie", 927, 1000, 92.7),
              _u(4, "Delta", 990, 1000, 99.0)]
    tr = {1: _tr("Alfa", "ok"), 2: _tr("Bravo", "sem_producao"), 3: _tr("Charlie", "atencao"), 4: _tr("Delta", "ok")}
    criado = datetime(2026, 11, 1, 7, 40)
    ch = {2: [{"concessionaria": "CPFL", "uc": "1", "situacao": "com protocolo", "tom": "ok", "criado": criado,
               "protocolo": "2026-118734", "protocolo_quando": criado, "os": "4812"}]}
    os_ = {1: [{"os": 4790, "wid": 1, "tipo": "preventiva", "situacao": "programada para 12/11", "tom": "neutro",
                "ordem": 1, "criada": None, "programada": date(2026, 11, 12), "execucao": False, "verificacao": False}],
           2: [{"os": 4812, "wid": 2, "tipo": "corretiva", "situacao": "em execução", "tom": "info", "ordem": 0,
                "criada": hoje, "programada": hoje, "execucao": True, "verificacao": False}]}
    vis = {1: {"dia": date(2026, 11, 12), "hora": "08:00", "tipo": "preventiva"},
           2: {"dia": hoje, "hora": "14:20", "tipo": "corretiva"}}
    s = VC.montar(usinas, tr, ch, os_, vis, hoje)
    assert [x["usina"] for x in s["linhas"]] == ["Bravo", "Charlie", "Alfa"]        # a parada, a com perda, a com OS
    assert [x["usina"] for x in s["normais"]] == ["Delta"]                          # sem pendência, agrupada
    k = s["kpis"]
    assert (k["status"]["valor"], k["status"]["de"], k["status"]["rotulo"]) == (2, 4, "gerando")
    assert (1, "parada", "critico") in k["status"]["selos"] and (1, "com perda", "alerta") in k["status"]["selos"]
    assert k["perf"]["pct"] == round(100 * 4551 / 5000, 1) == 91.0 and k["perf"]["tom"] == "alerta"   # a soma
    assert (k["chamados"]["n"], k["chamados"]["protocolo"], k["chamados"]["mais_antigo"]) == (1, 1, 4)
    assert (k["os"]["n"], k["os"]["execucao"], k["os"]["programadas"]) == (2, 1, 1)
    assert k["visita"] == {"quando": "Hoje 14:20", "usina": "Bravo", "tipo": "corretiva"}



def test_as_abertas_sao_as_por_fazer_e_a_conferencia_fica_a_parte():
    """Na Athon (05/11/2026) eram 422 "abertas" e 382 delas concluídas esperando a conferência da Grid: o número do
    cliente é o que ainda vai ser feito; a conferência aparece à parte."""
    hoje = date(2026, 11, 5)
    os_ = {1: [{"os": 1, "wid": 1, "tipo": "corretiva", "situacao": "em execução", "tom": "info", "ordem": 0,
                "criada": None, "programada": None, "execucao": True, "verificacao": False},
               {"os": 2, "wid": 2, "tipo": "preventiva", "situacao": "concluída, em conferência", "tom": "ok",
                "ordem": 2, "criada": None, "programada": None, "execucao": False, "verificacao": True}],
           2: [{"os": 3, "wid": 3, "tipo": "preventiva", "situacao": "concluída, em conferência", "tom": "ok",
                "ordem": 2, "criada": None, "programada": None, "execucao": False, "verificacao": True}]}
    s = VC.montar([_u(1, "Alfa"), _u(2, "Bravo")], {1: _tr("Alfa", "ok"), 2: _tr("Bravo", "ok")}, {}, os_, {}, hoje)
    assert (s["kpis"]["os"]["n"], s["kpis"]["os"]["verificacao"]) == (1, 2)
    assert {x["usina"]: x["os_abertas"] for x in s["linhas"] + s["normais"]} == {"Alfa": 1, "Bravo": 0}
    assert [x["usina"] for x in s["normais"]] == ["Bravo"]                 # só conferência: sem pendência


def test_fonte_que_nao_respondeu_e_sem_leitura_nunca_zero():
    s = VC.montar([_u(1, "Alfa", 10, 10, 100.0)], None, None, None, None, date(2026, 11, 5))
    k = s["kpis"]
    assert k["status"] is None and k["chamados"] is None and k["os"] is None and k["visita"] is None
    x = s["linhas"][0]                                       # sem leitura é pendência: não some no "sem pendência"
    assert x["status"]["rotulo"] == "Sem leitura" and x["chamados"] is None and x["os"] is None
    assert x["visita_lida"] is False


def test_o_nome_da_equipe_nao_sai():
    """O PCM avisou (05/11/2026): o nome da equipe pode ser o de uma pessoa. Fica só a cidade."""
    u = _u(1, "Alfa", 10, 10, 100.0)
    u["equipe"] = "Equipe Fulano"
    s = VC.montar([u], {1: _tr("Alfa", "ok")}, {}, {}, {}, date(2026, 11, 5))
    assert "Fulano" not in repr(s) and s["normais"][0]["onde"] == "Alfa/SP"


def test_a_noite_nao_vira_gerando():
    s = VC.montar([_u(1, "Alfa"), _u(2, "Bravo")], {1: _tr("Alfa", "ok", "Sem sol na usina"), 2: _tr("Bravo", "ok")},
                  {}, {}, {}, date(2026, 11, 5))
    st = s["kpis"]["status"]
    assert (st["valor"], st["rotulo"]) == (2, "sem alerta") and (1, "sem sol", "neutro") in st["selos"]


def test_as_os_seguem_a_regua_do_quadro_os_e_manutencao():
    hoje = HOJE
    tarefas = [_tarefa(1, 901, 1, -3), _tarefa(2, 902, 1, 5, estado="em_progresso"),
               _tarefa(3, 903, 1, 2, status="em_verificacao", estado="finalizada"),
               _tarefa(4, 904, 1, 1, tipo="zeladoria"), _tarefa(5, 905, 1, 1, tipo="teste"),
               dict(_tarefa(6, 906, 1, 1), do_backoffice=1), _tarefa(7, 16034, 1, 1)]
    por = VC.os_por_usina(tarefas, {16034}, hoje)[1]
    assert [o["os"] for o in por] == [902, 901, 903]                       # em execução, a fazer, em conferência
    assert [o["situacao"] for o in por] == ["em execução", f"programada para {hoje + timedelta(days=3):%d/%m}",
                                            "concluída, em conferência"]
    conta = M.tarefas_por_usina(tarefas, [], {16034}, hoje)[1]              # o mesmo número do quadro da Visão
    assert len(por) == conta["os_abertas"]
    assert sum(o["execucao"] for o in por) == conta["em_execucao"]
    assert sum(o["verificacao"] for o in por) == conta["em_verificacao"]


def test_a_proxima_visita_e_o_proximo_bloco_ainda_nao_feito():
    hoje = date(2026, 11, 5)
    prog = [{"usina_id": 1, "data_id_programada": 20261104, "hora_inicio": "08:00", "tipo_tarefa": "preventiva"},
            {"usina_id": 1, "data_id_programada": 20261105, "hora_inicio": "10:00", "tipo_tarefa": "corretiva",
             "status_execucao": "finalizada"},
            {"usina_id": 1, "data_id_programada": 20261107, "hora_inicio": "13:00", "tipo_tarefa": "preventiva"},
            {"usina_id": 1, "data_id_programada": 20261107, "hora_inicio": "08:30", "tipo_tarefa": "inspecao"}]
    assert VC.visitas_por_usina(prog, hoje)[1] == {"dia": date(2026, 11, 7), "hora": "08:30", "tipo": "inspeção"}
    # de hoje, só o que ainda vai começar: o bloco das 09:00 visto às 18:00 já foi (achado na bancada com a Athon)
    hoje_cedo = [{"usina_id": 2, "data_id_programada": 20261105, "hora_inicio": "09:00", "tipo_tarefa": "Corretiva"},
                 {"usina_id": 2, "data_id_programada": 20261106, "hora_inicio": "07:30", "tipo_tarefa": "Corretiva Emergencial"}]
    assert VC.visitas_por_usina(hoje_cedo, hoje, "18:00")[2] == {"dia": date(2026, 11, 6), "hora": "07:30",
                                                                "tipo": "corretiva emergencial"}
    assert VC.visitas_por_usina(hoje_cedo, hoje, "08:00")[2]["hora"] == "09:00"


def test_os_chamados_da_distribuidora_so_com_o_que_o_cliente_pode_ver():
    class _Lig:
        def usina(self, nome, codigo):
            return ({"THPN-ALT100": 1}.get(codigo), "código")

    class _B:
        lig = _Lig()

    class _L:
        dados = {"usinas": [{"nome": "Altair", "codigo": "THPN-ALT100"}],
                 "chamados": [{"usina_codigo": "THPN-ALT100", "estado": "PROTOCOLO", "protocolo": "123",
                               "criado_em": "2026-11-05T07:40:00-03:00", "protocolo_em": "2026-11-05T08:00:00-03:00",
                               "concessionaria": "CPFL", "uc": "9", "os": "4812", "aberto_por": "sistema",
                               "protocolo_por": "pessoa", "telefone": "999"},
                              {"usina_codigo": "THPN-ALT100", "estado": "DISPENSADO", "criado_em": "2026-11-04T07:40:00"}]}
    ch = VC.chamados_por_usina(_B(), [_L()])
    assert len(ch[1]) == 1 and ch[1][0]["protocolo"] == "123" and ch[1][0]["situacao"] == "com protocolo"
    assert set(ch[1][0]) == {"concessionaria", "uc", "situacao", "tom", "criado", "enviado", "protocolo",
                             "protocolo_quando", "os"}                       # nada de quem abriu nem telefone


def test_chamado_sem_hora_nao_derruba_a_lista():
    """O Andamento entrega o instante com fuso: um chamado sem `criado_em` não pode quebrar a ordem (com o `datetime.min`
    sem fuso, a comparação dava TypeError e a tela inteira dizia "sem leitura" nos chamados)."""
    class _Lig:
        def usina(self, nome, codigo):
            return (1, "código")

    class _B:
        lig = _Lig()

    class _L:
        dados = {"usinas": [{"nome": "Altair", "codigo": "X"}],
                 "chamados": [{"usina_codigo": "X", "estado": "PENDENTE"},
                              {"usina_codigo": "X", "estado": "ENVIADO", "criado_em": "2026-11-05T07:40:00-03:00"}]}
    ch = VC.chamados_por_usina(_B(), [_L()])[1]
    assert [c["situacao"] for c in ch] == ["enviado, aguardando resposta", "pendente"]   # o sem hora no fim


# ── o detalhe da usina (entrega 2) ──────────────────────────────────────────────────────────────────────────────────
def _quando(txt):
    from nexus.cos import andamento as AND
    return AND.instante(txt)


def test_a_agenda_de_hoje_junta_as_tarefas_do_bloco():
    hoje = date(2026, 11, 5)
    prog = [{"usina_id": 1, "data_id_programada": 20261105, "hora_inicio": "14:00", "tipo_tarefa": "MPA",
             "status_execucao": "nao_iniciada", "pessoa_id_tecnico": 7},
            {"usina_id": 1, "data_id_programada": 20261105, "hora_inicio": "14:00", "tipo_tarefa": "MPA",
             "status_execucao": "finalizada"},
            {"usina_id": 1, "data_id_programada": 20261105, "hora_inicio": "07:30", "tipo_tarefa": "Corretiva",
             "status_execucao": "finalizada"},
            {"usina_id": 1, "data_id_programada": 20261105, "hora_inicio": "10:00", "tipo_tarefa": "Inspeção",
             "status_execucao": "em_progresso"},
            {"usina_id": 1, "data_id_programada": 20261105, "hora_inicio": "11:00", "tipo_tarefa": "Corretiva",
             "status_execucao": "pausada"},
            {"usina_id": 1, "data_id_programada": 20261106, "hora_inicio": "08:00", "tipo_tarefa": "MPA"},
            {"usina_id": 2, "data_id_programada": 20261105, "hora_inicio": "09:00", "tipo_tarefa": "MPA"}]
    ag = VC.agenda_de_hoje(prog, hoje)
    assert [(b["hora"], b["tipo"], b["situacao"]) for b in ag[1]] == [
        ("07:30", "corretiva", "feita"), ("10:00", "inspeção", "em execução"), ("11:00", "corretiva", "pausada"),
        ("14:00", "preventiva (MPA)", "programada")]                       # a de amanhã não entra
    assert ag[1][3]["tarefas"] == 2 and ag[2][0]["situacao"] == "programada"
    assert set(ag[1][0]) == {"hora", "tipo", "situacao", "tom", "tarefas"}    # sem quem vai


def test_o_bloco_de_hoje_que_passou_sem_comecar_e_nao_iniciada():
    """Na bancada (Athon, 18:50 de 05/11/2026): "Visita programada: corretiva" às 09:00, de um bloco que nunca começou.
    O status do Quadro é "nao_iniciada": com a hora passada, a linha diz isso; o bloco que ainda vem segue "programada"."""
    hoje = date(2026, 11, 5)
    prog = [{"usina_id": 1, "data_id_programada": 20261105, "hora_inicio": "09:00", "tipo_tarefa": "Corretiva",
             "status_execucao": "nao_iniciada"},
            {"usina_id": 1, "data_id_programada": 20261105, "hora_inicio": "16:00", "tipo_tarefa": "Corretiva",
             "status_execucao": "nao_iniciada"}]
    ag = VC.agenda_de_hoje(prog, hoje, "12:00")[1]
    assert [(b["hora"], b["situacao"], b["tom"]) for b in ag] == [("09:00", "não iniciada", "alerta"),
                                                                  ("16:00", "programada", "neutro")]


def test_a_os_aberta_hoje_e_ja_concluida_diz_isso():
    """Na bancada (Athon): duas OS de religamento abertas hoje já estavam em conferência; "aberta" sozinho enganava."""
    hoje = date(2026, 11, 5)
    os_ = [{"os": 18604, "tipo": "religamento", "criada": hoje, "verificacao": True}]
    assert VC.linha_do_dia(None, None, os_, None, hoje) == [
        {"hora": "hoje", "texto": "OS 18604 aberta e concluída: religamento", "tom": "ok"}]


def test_a_linha_do_dia_so_com_o_que_aconteceu_hoje():
    hoje = date(2026, 11, 5)
    paradas = [{"os": "4812", "tipo": "Religamento", "escopo": "Usina inteira", "inicio": "05/11 07:15",
                "_ini": "2026-11-05T07:15:00", "codigo": "UFV"},
               {"os": "4700", "tipo": "desligamento de inversor", "escopo": "Inversor 1.3", "inicio": "24/10 10:45",
                "_ini": "2026-10-24T10:45:00", "codigo": "INV-13"}]
    chamados = [{"concessionaria": "CPFL", "protocolo": "2026-118734", "criado": _quando("2026-11-05T07:38:00-03:00"),
                 "enviado": _quando("2026-11-05T07:40:00-03:00"),
                 "protocolo_quando": _quando("2026-11-05T08:00:00-03:00"), "situacao": "com protocolo", "tom": "ok"},
                {"concessionaria": "CPFL", "protocolo": "", "criado": _quando("2026-11-04T09:00:00-03:00"),
                 "enviado": None, "protocolo_quando": None, "situacao": "pendente", "tom": "alerta"},
                # aberto e com protocolo ontem: nada hoje
                {"concessionaria": "CPFL", "protocolo": "2026-1", "criado": _quando("2026-11-04T09:00:00-03:00"),
                 "enviado": _quando("2026-11-04T09:05:00-03:00"),
                 "protocolo_quando": _quando("2026-11-04T10:00:00-03:00"), "situacao": "com protocolo", "tom": "ok"},
                # aberto ontem, protocolo hoje: só o protocolo
                {"concessionaria": "CPFL", "protocolo": "2026-2", "criado": _quando("2026-11-04T15:00:00-03:00"),
                 "enviado": _quando("2026-11-04T15:05:00-03:00"),
                 "protocolo_quando": _quando("2026-11-05T09:30:00-03:00"), "situacao": "com protocolo", "tom": "ok"}]
    os_ = [{"os": 4813, "tipo": "corretiva", "criada": hoje, "verificacao": False},
           {"os": 4790, "tipo": "preventiva", "criada": date(2026, 11, 1), "verificacao": False}]
    agenda = [{"hora": "14:00", "tipo": "corretiva", "situacao": "programada", "tom": "neutro", "tarefas": 1}]
    dia = VC.linha_do_dia(paradas, chamados, os_, agenda, hoje)
    assert [(e["hora"], e["texto"]) for e in dia] == [
        ("07:15", "Parada registrada: Usina inteira · OS 4812"),
        ("07:40", "Chamado aberto na CPFL"),
        ("08:00", "Protocolo 2026-118734 da CPFL"),
        ("09:30", "Protocolo 2026-2 da CPFL"),
        ("14:00", "Visita programada: corretiva"),
        ("hoje", "OS 4813 aberta: corretiva")]                              # o fato da OS só guarda o dia
    assert all(set(e) == {"hora", "texto", "tom"} for e in dia)
    assert VC.linha_do_dia(None, None, None, None, hoje) == []             # sem fonte: nada inventado


def _ch_uc(uc, protocolo="20266296905597", criado="2026-11-04T20:31:00-03:00", prot_em="2026-11-05T07:29:00-03:00"):
    return {"concessionaria": "COPEL", "uc": uc, "protocolo": protocolo, "criado": _quando(criado),
            "enviado": _quando(criado), "protocolo_quando": _quando(prot_em), "situacao": "com protocolo", "tom": "ok",
            "os": ""}


def test_um_protocolo_de_varias_ucs_e_uma_linha_so():
    """Produção, 05/11/2026 (Mandaguaçu): a COPEL deu UM protocolo para as 4 UCs da usina, e a linha do dia repetia
    "07:29 Protocolo ... da COPEL" quatro vezes; a lista dos chamados também. Fica uma linha, com as UCs."""
    hoje = date(2026, 11, 5)
    chamados = [_ch_uc(uc) for uc in ("1", "2", "3", "4")]
    dia = VC.linha_do_dia(None, chamados, None, None, hoje)
    assert [(e["hora"], e["texto"]) for e in dia] == [("07:29", "Protocolo 20266296905597 da COPEL · 4 UCs")]
    grupos = VC.chamados_agrupados(chamados + [_ch_uc("9", protocolo="777", criado="2026-11-01T10:00:00-03:00",
                                                     prot_em="2026-11-01T11:00:00-03:00")])
    assert [(g["protocolo"], g["ucs"]) for g in grupos] == [("20266296905597", ["1", "2", "3", "4"]), ("777", ["9"])]
    # sem protocolo não junta: cada chamado é um
    sem = [_ch_uc("1", protocolo=""), _ch_uc("2", protocolo="")]
    assert len(VC.chamados_agrupados(sem)) == 2


def test_o_detalhe_vai_na_linha_sem_nada_interno():
    hoje = date(2026, 11, 5)
    u = _u(1, "Alfa", 10, 10, 100.0)
    u["paradas_abertas"] = [{"os": "4812", "tipo": "Religamento Remoto", "escopo": "Usina inteira",
                             "inicio": "05/11 07:15", "_ini": "2026-11-05T07:15:00", "codigo": "UFV-1"}]
    agenda = {1: [{"hora": "14:00", "tipo": "corretiva", "situacao": "programada", "tom": "neutro", "tarefas": 1}]}
    s = VC.montar([u], {1: _tr("Alfa", "desligada")}, {}, {}, {}, hoje, agenda=agenda)
    x = s["linhas"][0]
    assert x["paradas"] == [{"os": "4812", "tipo": "religamento remoto", "escopo": "Usina inteira",
                             "desde": "05/11 07:15"}]                       # sem o código do ativo
    assert [e["hora"] for e in x["dia"]] == ["07:15", "14:00"]
    assert "codigo" not in _chaves(s, set()) and "_ini" not in _chaves(s, set())


def _chaves(x, out):
    if isinstance(x, dict):
        for k, v in x.items():
            out.add(str(k))
            _chaves(v, out)
    elif isinstance(x, (list, tuple, set)):
        for v in x:
            _chaves(v, out)
    return out


def test_a_sintese_nao_leva_nada_interno():
    """A fase 2 (o login do cliente) reaproveita a conta: desde já sem nome de técnico, custo, horas nem causa."""
    hoje = date(2026, 11, 5)
    tarefas = [_tarefa(1, 901, 1, -3)]
    s = VC.montar([_u(1, "Alfa", 10, 10, 100.0)], {1: _tr("Alfa", "desligada", "Usina desligada · OS 1")}, {},
                  VC.os_por_usina(tarefas, set(), hoje), {}, hoje)
    chaves = _chaves(s, set())
    for proibida in ("duracao_min", "quem", "tecnico", "pessoa", "telefone", "custo", "causa", "motivo",
                     "responsavel", "solicitante"):
        assert not any(proibida in c for c in chaves), proibida


# ── a leitura do tempo real pela ponte só de leitura ────────────────────────────────────────────────────────────────
class _Resp:
    def __init__(self, status, corpo, ok=True):
        self.status_code, self._corpo = status, corpo
        self.headers = {"X-Nexus-Leitura-Ok": "1"} if ok else {}

    def json(self):
        return self._corpo


def test_o_tempo_real_vem_pela_ponte_e_sem_ela_e_sem_leitura(monkeypatch):
    from nexus.performance import ponte
    VC.limpar()
    assert VC.ler_tempo_real({})["erro"]                                 # sem a ponte configurada: sem leitura
    pedidos = []
    corpo = {"cache_ts": "17:49:39", "idade_s": 10,
             "grupos": [{"usinas": [_tr("Altair", "ok")]}, {"usinas": [_tr("Coração 1", "sem_comm")]}]}
    monkeypatch.setattr(ponte, "enviar", lambda **p: pedidos.append(p) or _Resp(200, corpo))
    VC.limpar()
    cfg = {"NEXUS_PLATAFORMA_URL": "https://plataforma.exemplo", "NEXUS_PLATAFORMA_TOKEN": "x"}
    d = VC.ler_tempo_real(cfg)
    assert [u["usina"] for u in d["usinas"]] == ["Altair", "Coração 1"] and d["cache_ts"] == "17:49:39"
    assert pedidos[0]["url"].endswith("/api/entrada/tempo-real") and pedidos[0]["method"] == "GET"
    assert pedidos[0]["headers"]["X-Nexus-Leitura"] == "x" and not pedidos[0]["params"]     # nada de force
    VC.ler_tempo_real(cfg)
    assert len(pedidos) == 1                                              # guardado 2 min
    monkeypatch.setattr(ponte, "enviar", lambda **p: _Resp(200, corpo, ok=False))
    VC.limpar()
    assert VC.ler_tempo_real(cfg)["erro"]                                 # a plataforma que não confirma a chave
    VC.limpar()


# ── a tela ──────────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def cliente_tela(manut, monkeypatch):
    from nexus.campo import responsaveis as R
    VC.limpar()
    monkeypatch.setattr(VC, "ler_tempo_real", lambda cfg: {
        "usinas": [_tr("Altair", "sem_producao"), _tr("Brodowski 1", "ok"), _tr("Coração 1", "ok")],
        "cache_ts": "14:20:00", "idade_s": 30, "erro": ""})
    amanha = HOJE + timedelta(days=1)
    monkeypatch.setattr(R, "_programacao_recente", lambda segundas, listagem=None: [
        {"usina_id": 2, "data_id_programada": _did(amanha), "hora_inicio": "08:00", "tipo_tarefa": "preventiva"}])
    return manut


@pytest.fixture
def modo_cliente(app, tmp_path, logado):
    """O administrador no Modo cliente da Thopen (cliente 1), com a Visão do cliente marcada para o setor Clientes: desde
    09/11/2026 é só por aqui (ou como o próprio cliente) que a tela abre (`Tela.so_do_cliente`)."""
    from nexus.auth import setor_telas as ST
    from nexus.cadastro import setor_ids as SID
    app.config["NEXUS_DADOS"] = str(tmp_path / "dados")
    ST.limpar()
    with app.test_request_context():
        ST.gravar(SID.CLIENTES, ["campo/cliente"], ST.telas_do_cliente_possiveis(), app.config, "http://pg.falso",
                  app.extensions["nexus_dados_sessao"], "admin@exemplo.test")
    ST.limpar()
    with logado.session_transaction() as s:
        s["modo_cliente"] = {"id": 1, "nome": "Thopen"}
    yield logado
    ST.limpar()


def test_a_grid_nao_ve_mais_a_tela_fora_do_modo_cliente(cliente_tela, logado):
    """Levi, 09/11/2026 (pelo Scrum master): "O 'visão do cliente' pode tirar pois já temos no modo cliente do nosso
    menu". Quem é da Grid vai à Visão do responsável (o endereço guardado, com ou sem cliente) e o item sai do menu."""
    for url in ("/t/campo/cliente", "/t/campo/cliente?cliente=1", "/t/campo/cliente?cliente=999"):
        r = logado.get(url)
        assert r.status_code == 302 and r.headers["Location"].endswith("/t/campo/responsaveis"), url
    menu = logado.get("/t/campo/responsaveis").get_data(as_text=True).split('<nav class="menu"', 1)[1].split("</nav>", 1)[0]
    assert "/t/campo/cliente" not in menu and "/t/campo/responsaveis" in menu


def test_no_modo_cliente_a_tela_mostra_a_sintese(cliente_tela, modo_cliente):
    html = modo_cliente.get("/t/campo/cliente").get_data(as_text=True)
    # no Modo cliente o nome vai no cumprimento do alto (o mockup do cliente), não no título da escolha
    assert ", Thopen</h1>" in html and "Coração 1" not in html.split('class="vc-numeros"', 1)[1]
    numeros = html.split('class="vc-numeros"', 1)[1].split('<section class="vc-q"', 1)[0]
    assert "<b>1</b> de 2 gerando" in numeros and "1 parada" in numeros
    assert "92,5%</b> do esperado" in numeros                            # (850 + 1000) ÷ (1000 + 1000), a soma
    assert "sem leitura" in numeros                                       # o Andamento não está ligado nos testes
    assert "<b>1</b> aberta" in numeros                                   # a OS 901 da Brodowski 1
    assert "Amanhã 08:00" in numeros and "Brodowski 1 · preventiva" in numeros
    tabela = html.split('<section class="vc-q"', 1)[1]
    assert tabela.index("Altair") < tabela.index("Brodowski 1")           # a parada primeiro
    assert "Não consegui ler os chamados na distribuidora" in html
    assert "De onde vem cada número" not in html                         # a explicação interna é da Grid


def test_sem_cadastro_a_tela_abre_com_o_aviso(cliente_tela, modo_cliente, monkeypatch):
    """Sem o banco (o cadastro não responde), a tela abre com o aviso, como as outras do Campo; nunca o erro 500."""
    def _sem(*a, **k):
        raise visao.SemBanco("sem banco")
    monkeypatch.setattr(visao, "_Base", _sem)
    r = modo_cliente.get("/t/campo/cliente")
    # para o cliente, o aviso sem o nome do erro interno
    assert r.status_code == 200 and "Parte das informações não carregou agora" in r.get_data(as_text=True)


def test_fica_logo_depois_das_ocorrencias_no_menu():
    from nexus.torres.campo import TORRE
    ids = [t.id for t in TORRE.telas]
    assert ids.index("cliente") == ids.index("ocorrencias") + 1         # a Visão do responsável e as Ocorrências juntas


def test_a_tela_abre_o_detalhe_da_usina_escolhida(cliente_tela, modo_cliente):
    logado = modo_cliente
    html = logado.get("/t/campo/cliente?cliente=1").get_data(as_text=True)
    det = html.split('<aside class="vc-det"', 1)[1]
    # sem escolha: o detalhe da primeira que pede atenção (a Altair, parada); as outras escondidas
    assert det.index('id="vc-det-1"') < det.index('id="vc-det-2"')
    assert 'id="vc-det-1" class="vc-det-u">' in det and 'id="vc-det-2" class="vc-det-u" hidden>' in det
    assert 'data-vc="1"' in html and 'class="vc-linha vc-sel"' in html
    html = logado.get("/t/campo/cliente?cliente=1&usina=2").get_data(as_text=True)
    det = html.split('<aside class="vc-det"', 1)[1]
    assert 'id="vc-det-2" class="vc-det-u">' in det and 'id="vc-det-1" class="vc-det-u" hidden>' in det
    bro = det.split('id="vc-det-2"', 1)[1]
    assert "Amanhã 08:00" in bro and "OS 901" in bro                     # a próxima visita e a OS da Brodowski 1
    # a usina de outro cliente no endereço não abre: volta para a primeira deste
    html = logado.get("/t/campo/cliente?cliente=1&usina=3").get_data(as_text=True)
    assert 'id="vc-det-3"' not in html and 'id="vc-det-1" class="vc-det-u">' in html


def test_o_painel_lista_o_protocolo_de_varias_ucs_uma_vez(cliente_tela, modo_cliente, monkeypatch):
    logado = modo_cliente
    from nexus.torres.campo import cliente_tela as CT
    original = CT._fontes

    def _com_chamados(b, uids, hoje):
        f, e = original(b, uids, hoje)
        f["chamados"] = {1: [_ch_uc(uc) for uc in ("11", "12")]}
        e.pop("chamados", None)
        return f, e
    monkeypatch.setattr(CT, "_fontes", _com_chamados)
    html = logado.get("/t/campo/cliente?cliente=1&usina=1").get_data(as_text=True)
    det = html.split('id="vc-det-1"', 1)[1].split("</section>", 1)[0]
    assert det.count("Protocolo 20266296905597</b>") == 1 and "2 UCs (11, 12)" in det

