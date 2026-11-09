"""Quadro da equipe da Performance (04/11/2026, Levi: "clone o quadro de equipe da engenharia para o time de
performance com as pessoas da performance"; "tira do BASE > ACESSOS > PESSOAS E SETORES"): a equipe é o setor
Performance do livro nexus_setores, pelo id do Fracttal; o clique abre o card da OS do OS Creator. Nomes fictícios (o
repositório é público)."""
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

from nexus.engenharia import os_equipe as OE
from nexus.performance import quadro_equipe as Q

AGORA = datetime(2026, 11, 4, 15, 0, tzinfo=timezone.utc)
SETORES = {"setores": [{"setor_id": 1, "nome": "Engenharia", "excluido": False},
                       {"setor_id": 2, "nome": "Performance", "excluido": False}],
           "decisoes": [{"fracttal_id": 10, "setor_id": 2, "decidida_em": "2026-10-01T10:00:00"},
                        {"fracttal_id": 11, "setor_id": 2, "decidida_em": "2026-10-01T10:00:00"},
                        {"fracttal_id": 11, "setor_id": 1, "decidida_em": "2026-10-20T10:00:00"},   # mudou de setor
                        {"fracttal_id": 12, "setor_id": 1, "decidida_em": "2026-10-01T10:00:00"},
                        {"fracttal_id": 13, "setor_id": 2, "decidida_em": "2026-10-02T10:00:00"}],  # fora do Fracttal
           "erro": ""}
PESSOAS = [{"id_personnel": 10, "name": "Paula  Teste", "full_name": "Paula Teste"},
           {"id_personnel": 11, "name": "Otavio Exemplo", "full_name": "Otavio Exemplo"},
           {"id_personnel": 14, "name": "Paula Teste", "full_name": "Paula Teste"}]                  # homônima


def _w(folio, status, pid=10, prog_dias=3, **kw):
    prog = AGORA + timedelta(days=prog_dias)
    d = {"wo_folio": folio, "id_work_order": 9000 + int(folio), "id_personnel": pid, "id_status_work_order": status,
         "task_status": "NO_STARTED", "description": f"Strings {folio}", "items_log_description": "Inversor 1.1 {X-INV1.1}",
         "code": "X-INV1.1", "groups_1_description": "Thopen - Altair 1 - SP", "tasks_log_task_type_main": "Corretiva",
         "date_maintenance": prog.isoformat(), "creation_date": (AGORA - timedelta(days=2)).isoformat(),
         "final_date": None, "wo_final_date": None, "initial_date": None, "labels": [],
         "personnel_description": "Paula  Teste"}
    d.update(kw)
    return d


def test_a_equipe_e_o_setor_performance_de_hoje():
    # a última decisão de cada pessoa vale: quem mudou para a Engenharia sai
    assert sorted(Q.ids_do_setor(SETORES)) == ["10", "13"]
    assert Q.ids_do_setor({"setores": [dict(SETORES["setores"][1], excluido=True)], "decisoes": SETORES["decisoes"]}) == []


def test_le_as_os_de_quem_e_do_setor_pelo_id_do_fracttal(app, monkeypatch):
    linhas = [_w("1", 1, prog_dias=-2), _w("2", 2), _w("3", 1, pid=14)]          # a 3 é da homônima: fora

    def rest(path):
        if path.startswith("personnel?"):
            return {"data": PESSOAS}
        trecho = unquote(path.split("personnel_description=", 1)[1].split("&", 1)[0])
        return {"data": [w for w in linhas if trecho in w["personnel_description"]]}
    monkeypatch.setattr(OE, "_ler_fracttal", rest)
    monkeypatch.setattr(Q.time, "sleep", lambda s: None)
    monkeypatch.setattr(Q, "_setores", lambda: SETORES)
    Q.limpar()
    Q._reler(app)
    d = Q.dados()
    assert sorted(o["os"] for o in d["os"]) == ["1", "2"] and not d["erro"]
    assert [p["nome"] for p in d["equipe"]] == ["Paula Teste"]                     # o nome como o Fracttal escreve
    assert d["faltam"] == ["id 13"]
    Q.limpar()


def test_setores_fora_guarda_a_leitura_anterior(app, monkeypatch):
    Q.limpar()
    Q._EST.update(os=[{"os": "1"}], ts=1.0)
    monkeypatch.setattr(Q, "_setores", lambda: {"setores": [], "decisoes": [], "erro": "ConnectionError: fora"})
    Q._reler(app)
    assert Q.dados()["os"] == [{"os": "1"}] and "setores não lidos" in Q.dados()["erro"]
    Q.limpar()


def test_o_estado_e_separado_do_quadro_da_engenharia():
    Q.limpar()
    OE.limpar()
    Q._EST.update(os=[{"os": "1"}], ts=5.0)
    assert OE.dados()["os"] == [] and OE.dados()["lido"] == 0.0
    Q.limpar()


class _RelogioParado(datetime):
    """O relógio da tela parado em AGORA. A rota calcula o pulso ("parada", sem atualização há mais de 7 dias) com
    `datetime.now`, e as OS do teste nascem de AGORA: com o relógio real, a OS "nova" (criada em AGORA - 2 dias, 02/11)
    passou dos 7 dias em 09/11/2026 e o teste quebrou sem nada mudar na tela. Só o `now` para; o resto é o datetime."""

    @classmethod
    def now(cls, tz=None):
        return AGORA.astimezone(tz) if tz else AGORA.astimezone().replace(tzinfo=None)


def _tela(logado, monkeypatch, oss, faltam=()):
    monkeypatch.setattr("nexus.torres.performance.datetime", _RelogioParado)
    monkeypatch.setattr(Q, "pedir_releitura", lambda app=None, esperar=False, forcar=False: None)
    monkeypatch.setattr(Q, "dados", lambda: {"os": oss, "equipe": [{"id": 10, "nome": "Paula Teste",
                                                                    "nome_fracttal": "Paula Teste"}],
                                             "faltam": list(faltam), "lido": 1.0, "lendo": False, "erro": ""})
    r = logado.get("/t/performance/equipe")
    return r.status_code, r.get_data(as_text=True)


def test_a_tela_e_o_quadro_da_engenharia_com_o_card_do_os_creator(logado, monkeypatch):
    oss = OE.montar([_w("1", 1, prog_dias=-2), _w("2", 2)], {"id": 10, "nome": "Paula Teste"}, AGORA)
    st, html = _tela(logado, monkeypatch, oss, faltam=["id 13"])
    assert st == 200
    assert "Quem está com o quê" in html and 'class="kb-super"' in html and 'class="kb-kpis"' in html
    assert "As OS de quem é da performance" in html and "Base → Acessos → Pessoas e setores" in html
    assert "window.NexusOsCard" in html and "NexusOsCard.abrir(o.wid, op)" in html
    dados = html.split('id="kb-dados">', 1)[1].split("</script>", 1)[0]
    assert '"card": true' in dados and '"wid": 9001' in dados and '"status": "Em Processo"' in dados


def test_o_pulso_conta_so_o_fracttal(logado, monkeypatch):
    # a Performance não tem livro de OS: a OS aberta sem mexida nas tarefas nem criação há mais de 7 dias pulsa
    velha = _w("1", 1, creation_date=(AGORA - timedelta(days=20)).isoformat())
    nova = _w("2", 1)
    oss = OE.montar([velha, nova], {"id": 10, "nome": "Paula Teste"}, AGORA)
    _st, html = _tela(logado, monkeypatch, oss)
    dados = html.split('id="kb-dados">', 1)[1].split("</script>", 1)[0]
    import json
    por = {o["os"]: o for o in json.loads(dados)["oss"]}
    assert por["1"]["parada"] is True and por["2"]["parada"] is False
    assert "OSs sem atualização" in html and "sem ler o registro da engenharia" not in html


def test_quem_mudou_a_os_pelo_card_volta_com_o_quadro_relido(logado, monkeypatch):
    pedidos = []
    monkeypatch.setattr(Q, "pedir_releitura", lambda app=None, esperar=False, forcar=False: pedidos.append((esperar, forcar)))
    monkeypatch.setattr(Q, "dados", lambda: {"os": [], "equipe": [], "faltam": [], "lido": 1.0, "lendo": False, "erro": ""})
    logado.get("/t/performance/equipe")
    logado.get("/t/performance/equipe?atualizar=1")
    assert pedidos == [(False, False), (True, True)]


def test_o_quadro_da_engenharia_segue_igual(logado, monkeypatch):
    oss = OE.montar([_w("1", 1)], {"id": 10, "nome": "Ana"}, AGORA)
    monkeypatch.setattr(OE, "pedir_releitura", lambda app=None, esperar=False, forcar=False: None)
    monkeypatch.setattr(OE, "dados", lambda: {"os": oss, "equipe": [], "faltam": [], "lido": 1.0, "lendo": False,
                                              "erro": ""})
    html = logado.get("/t/engenharia/equipe").get_data(as_text=True)
    assert "As OS de quem é da engenharia" in html and "window.NexusOsCard" not in html
    assert '"card": false' in html.split('id="kb-dados">', 1)[1]


def test_tique_so_rele_com_alguem_usando(monkeypatch):
    pedidos = []
    monkeypatch.setattr(Q, "pedir_releitura", lambda app=None, esperar=False, forcar=False: pedidos.append(forcar))
    Q.limpar()
    assert Q._tique(None, agora=1000.0) is False                                   # ninguém abriu
    Q.marcar_uso()
    assert Q._tique(None) is True and pedidos == [True]
    Q.limpar()
