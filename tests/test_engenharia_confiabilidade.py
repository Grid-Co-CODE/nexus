"""Engenharia > Confiabilidade, nossa (06/10/2026): as regras do robô do PCM sobre a nossa leitura das OS de falha do
Fracttal, com o ativo pelo código (com a usina) e o lugar pelo cadastro do Nexus."""
from datetime import datetime, timedelta, timezone

from nexus.engenharia import confiabilidade as C
from nexus.engenharia import os_falhas

AGORA = datetime(2026, 10, 6, 15, 0, tzinfo=timezone.utc)


def _os(cod, dias_atras, tipo="Corretiva", tarefa="Inversor desligado", usina="Thopen - Ibaté 2 - SP",
        horas_reparo=5.0, **kw):
    cr = AGORA - timedelta(days=dias_atras)
    d = {"wo_folio": f"{cod}-{dias_atras}", "id_work_order": 100 + dias_atras,
         "id_work_orders_tasks": f"{cod}|{dias_atras}|{tarefa}", "code": cod,
         "items_log_description": "Equipamento {" + cod + "}", "groups_1_description": usina,
         "tasks_log_task_type_main": tipo, "description": tarefa, "task_note": "", "creation_date": cr.isoformat(),
         "event_date": cr.isoformat(), "initial_date": (cr + timedelta(hours=1)).isoformat(),
         "final_date": (cr + timedelta(hours=horas_reparo)).isoformat(), "task_status": "DONE"}
    d.update(kw)
    return d


def _onde(texto, cod):
    return {"usina_id": 1, "usina": texto.split(" - ")[1], "cliente": texto.split(" - ")[0], "cluster": "SP Norte",
            "uf": "SP", "equipe": "SP Norte 01", "mobilizacao": None, "ligada_por": "de-para do Fracttal"}


def test_nivel_pelas_regras_do_pcm_e_servico_fora():
    linhas = ([_os("IBI200-INVR1.3", d) for d in (1, 2, 3, 10)]                    # 4 falhas, 3 em 7 dias: crítico
              + [_os("IBI200-TRK07", d) for d in (5, 20)]                          # tracker (C), 2 falhas: monitorar
              + [_os("IBI200-QGBT1", d) for d in (5, 20)]                          # QGBT (A), 2 falhas: sobe a atenção
              + [_os("IBI200-CAB1", d, tarefa="Limpeza da cabine") for d in (4, 9)]   # só serviço: monitorar
              + [_os("IBI200-INVR2.1", 40)]                                        # fora da janela
              + [_os("TESTE100-NCU1", d) for d in (1, 2, 3)])                      # ativo de teste: fora
    d = C.calcular(linhas, _onde, AGORA)
    s = {a["cod"]: a for a in d["sinais"]}
    assert set(s) == {"IBI200-INVR1.3", "IBI200-TRK07", "IBI200-QGBT1", "IBI200-CAB1"}
    assert (s["IBI200-INVR1.3"]["nivel"], s["IBI200-INVR1.3"]["nFalha"], s["IBI200-INVR1.3"]["n7"]) == ("critico", 4, 3)
    assert (s["IBI200-TRK07"]["nivel"], s["IBI200-TRK07"]["crit"]) == ("monitorar", "C")
    assert (s["IBI200-QGBT1"]["nivel"], s["IBI200-QGBT1"]["crit"]) == ("atencao", "A")
    assert s["IBI200-CAB1"]["soServico"] and s["IBI200-CAB1"]["nFalha"] == 0 and s["IBI200-CAB1"]["nivel"] == "monitorar"
    assert d["sinais"][0]["cod"] == "IBI200-INVR1.3"                                # crítico primeiro
    assert s["IBI200-INVR1.3"]["os"][0]["url"] == "https://one.fracttal.com/tasks/wo/101"   # a OS abre no Fracttal
    assert d["kpi"]["ativosCorretiva"] == 4 and d["kpi"]["criticos"] == 1


def test_mtbf_mttr_e_disponibilidade_pelo_metodo_do_power_bi():
    """MTBF = (horas desde a mobilização efetiva - paradas) / falhas; MTTR com 12 h por dia acima de 1 dia."""
    mob = datetime(2025, 10, 20, tzinfo=timezone(timedelta(hours=-3)))
    falhas = [_os("X-INV1", 30, horas_reparo=5.0), _os("X-INV1", 60, horas_reparo=48.0)]
    m = C.metodo(falhas, mob, AGORA)
    horas = (AGORA - mob).total_seconds() / 3600
    assert m["n"] == 2 and abs(m["mtbf"] - (horas - 4 - 47) / 2) < 1e-6           # paradas: do início ao fim
    assert abs(m["mttr"] - (5 + 2 * 12) / 2) < 1e-6                               # incidente -> fim: 5 h e 2 dias
    assert abs(m["disp"] - m["mtbf"] / (m["mtbf"] + m["mttr"])) < 1e-9


def test_ativo_e_o_codigo_e_nao_o_nome():
    """No PCM o MTBF era casado pelo nome: o Inversor 1.3 de Ibirapuã 2 levava o de Cipó Guaçu. Aqui cada código é um
    ativo, com a sua usina."""
    linhas = [_os("IBI200-INVR1.3", d, usina="Ultragaz - Ibirapuã 2 - BA") for d in (2, 3, 4)] + \
             [_os("CPG100-INVR1.3", 200, usina="Thopen - Cipó Guaçu - SP")]
    d = C.calcular(linhas, _onde, AGORA)
    a = {x["cod"]: x for x in d["ativos"]}
    assert a["IBI200-INVR1.3"]["usina"] == "Ibirapuã 2" and a["CPG100-INVR1.3"]["usina"] == "Cipó Guaçu"
    assert a["IBI200-INVR1.3"]["mtbf"] != a["CPG100-INVR1.3"]["mtbf"]


def test_indicadores_pela_mediana_dos_ativos():
    linhas = [_os("A-INV1", 2), _os("A-INV1", 3), _os("B-INV1", 2, usina="Athon - Matões 2 - MA")]
    d = C.calcular(linhas, _onde, AGORA)
    ind = {r["nome"]: r for r in C.indicadores(d["ativos"], d["sinais"], "cliente")}
    assert set(ind) == {"Thopen", "Athon"} and ind["Thopen"]["ativos"] == 1


def test_leitura_das_concluidas_guarda_e_continua(app, tmp_path, monkeypatch):
    """As concluídas vão para o arquivo; um 429 no meio não perde o que veio; depois, a leitura completa."""
    recusou = []

    def ler(path):
        if "id_status_work_order=3" not in path or "main=Corretiva&" not in path:
            return {"data": []}                                             # nenhuma viva; os outros tipos vazios
        ini = int(path.split("start=")[1])
        if ini == 100 and not recusou:
            recusou.append(1)
            raise RuntimeError("o Fracttal recusou por excesso de pedidos (HTTP 429)")
        n = 100 if ini < 200 else 20
        return {"data": [{"id_work_orders_tasks": f"t{ini + i}", "final_date": "2026-10-05T10:00:00",
                          "code": "X-INV1", "tasks_log_task_type_main": "Corretiva"} for i in range(n)]}
    monkeypatch.setattr(os_falhas, "_ler_fracttal", ler)
    monkeypatch.setattr(os_falhas, "PAUSA_S", 0)
    app.config.update(NEXUS_DADOS=str(tmp_path))
    os_falhas.limpar()
    try:
        with app.app_context():
            os_falhas._reler()
            e = os_falhas.estado()
            assert e["erro"] and not e["completa"] and e["n"] == 100
            os_falhas.limpar()
            assert len(os_falhas.linhas()) == 100                            # volta do arquivo, sem pedir nada
            os_falhas._reler()
            e = os_falhas.estado()
            assert not e["erro"] and e["completa"] and e["n"] == 220
    finally:
        os_falhas.limpar()


def test_tela_de_confiabilidade(app, logado, monkeypatch):
    linhas = [_os("IBI200-INVR1.3", d) for d in (1, 2, 3, 10)] + [_os("IBI200-TRK07", d) for d in (5, 20)]
    monkeypatch.setattr(os_falhas, "pedir_releitura", lambda app=None: None)
    monkeypatch.setattr(os_falhas, "linhas", lambda: linhas)
    monkeypatch.setattr(os_falhas, "estado", lambda: {"lendo": False, "erro": "", "completa": True, "n": 6, "vivas_em": 1})
    from nexus.torres import engenharia as torre
    monkeypatch.setattr(torre, "_onde_do_cadastro", lambda: _onde)
    torre._CACHE.clear()
    try:
        html = logado.get("/t/engenharia/confiabilidade").get_data(as_text=True)
        assert "Ativos com sinal" in html and "IBI200-INVR1.3" in html and "Crítico" in html
        assert 'class="eg-gaveta"' in html and "Onde está o problema" in html and "Por que acendeu" in html
        assert "A · 4 falhas em 30d" in html and "B · 3 em 7d" in html
        assert "IBI200-TRK07" in html                                       # monitorar aparece
        assert "IBI200-TRK07" not in logado.get("/t/engenharia/confiabilidade?nivel=critico").get_data(as_text=True)
        ind = logado.get("/t/engenharia/confiabilidade?aba=indicadores").get_data(as_text=True)
        assert "Estatísticas" in ind and "Thopen" in ind and "Eventos (hist.)" in ind and 'class="eg-disp"' in ind
    finally:
        torre._CACHE.clear()
