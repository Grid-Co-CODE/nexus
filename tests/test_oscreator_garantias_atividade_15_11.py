"""A atividade do chamado de Garantias no Fracttal (Levi, 15/11/2026: "quando tivesse o primeiro comentário, a data e hora
do primeiro comentário entraria como início da atividade do chamado, se tiver só um ativo"; no quiz: o fim na finalização,
também os abertos, e o cronômetro iniciado no 1º comentário).

- o 1º comentário escrito na tela do chamado inicia a atividade da tarefa, com a hora dele; o 2º não mexe;
- só na OS de UM ativo (uma tarefa), e só se a atividade ainda não começou;
- o Finalizar encerra a atividade antes de concluir; a de outra pessoa ele não encerra, e diz de quem é, sem concluir;
- o chamado que chega ao Finalizar sem atividade nenhuma (os abertos de antes da regra) ganha o registro inteiro: início no
  1º comentário, fim na finalização.

Fracttal e banco FALSOS (os do teste de 20/10): nenhum pedido vai à rede. Nomes e números de mentira."""
import datetime as dt

import pytest
from test_oscreator_acomp_30min_20_10 import URL, _cliente, _memoria_limpa, fila, fracttal  # noqa: F401

import api  # noqa: E402 — o api.py do clone (o sys.path vem do módulo acima)
import chamados_obs_store as obs_store  # noqa: E402
from os_web import rotas_acomp  # noqa: E402

BRT = dt.timezone(dt.timedelta(hours=-3))


@pytest.fixture
def cron(monkeypatch, fracttal):
    """O cronômetro de mentira da tarefa 21 (a única da OS 9104, wid 2): o estado, os registros e o que foi pedido."""
    c = {"estado": "parada", "registros": [], "pedidos": [], "tarefas": [21], "banco": [], "dono": "",
         "concluiu": 0, "finaliza_falha": False, "ignora_inicio": False}

    def iniciar(tid, inicio=None):
        c["pedidos"].append(("iniciar", tid, inicio))
        ini = dt.datetime.now(dt.timezone.utc) if c["ignora_inicio"] else inicio
        c["registros"].insert(0, {"id": 700 + len(c["registros"]), "initial_date": ini.astimezone(dt.timezone.utc)
                                  .strftime("%Y-%m-%dT%H:%M:%SZ"), "final_date": None})
        c["estado"] = "rodando"
        return {"ok": True}

    def finalizar(tid):
        c["pedidos"].append(("finalizar", tid))
        if not c["finaliza_falha"]:
            c["estado"] = "parada"
            c["registros"][0]["final_date"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {"ok": True}

    def retomar(tid):
        c["pedidos"].append(("retomar", tid))
        c["estado"] = "rodando"
        return {"ok": True}

    def editar(rid, ini, fim=None):
        c["pedidos"].append(("editar", rid, ini, fim))
        return {"ok": True}

    def excluir(rid):
        c["pedidos"].append(("excluir", rid))
        c["registros"] = [e for e in c["registros"] if e["id"] != rid]
        return {"ok": True}

    def concluir(wid):
        c["concluiu"] += 1
        return {"ok": True, "data_fim": {}}

    def adicionar(folio, texto, tipo, **k):
        reg = {"id": "n%d" % len(c["banco"]), "quando": dt.datetime.now(BRT).isoformat(), "os": str(folio), "tipo": tipo,
               "texto": texto, "quem": "Pessoa Teste", "email": "", "ativo": "", "extra": dict(k.get("extra") or {})}
        c["banco"].append(reg)
        return reg
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: {"folio": {1: 9103, 2: 9104}[wid], "notas": "", "code": "TST-1",
                                                             "subtarefas": [], "tarefas": [{"id": t} for t in c["tarefas"]]})
    monkeypatch.setattr(api, "execucao_atual", lambda tid: {"estado": c["estado"]})
    monkeypatch.setattr(api, "historico_execucao", lambda tid: list(c["registros"]))
    monkeypatch.setattr(api, "iniciar_execucao", iniciar)
    monkeypatch.setattr(api, "finalizar_execucao", finalizar)
    monkeypatch.setattr(api, "retomar_execucao", retomar)
    monkeypatch.setattr(api, "editar_execucao", editar)
    monkeypatch.setattr(api, "execucoes_abertas", lambda tid: [{"name": c["dono"]}] if c["dono"] else [])
    monkeypatch.setattr(api, "concluir_os_checado", concluir)
    monkeypatch.setattr(api, "excluir_execucao", excluir)
    monkeypatch.setattr(api, "_cabecalho_os", lambda wid: {"wo_folio": "9104", "id_status_work_order": 3})
    monkeypatch.setattr(obs_store, "adicionar", adicionar)
    monkeypatch.setattr(obs_store, "listar", lambda forcar=False: list(c["banco"]))
    monkeypatch.setattr(rotas_acomp.lista_central, "mudou", lambda wid: None)
    return c


def _comentar(cli, texto="Cobrado o fabricante."):
    return cli.post("/os/api/acomp/9104/obs", json={"texto": texto, "wid": 2}).get_json()


def test_o_primeiro_comentario_inicia_a_atividade_com_a_hora_dele(cron, fila):
    cli = _cliente()
    cli.get(URL)
    j = _comentar(cli)
    assert j["ok"] is True and j["atividade"]["ok"] is True and "o 1º comentário" in j["atividade"]["mensagem"]
    (acao, tid, inicio), = cron["pedidos"]
    assert (acao, tid) == ("iniciar", 21)
    assert inicio == dt.datetime.fromisoformat(cron["banco"][0]["quando"])      # a hora do comentário, não outra
    j2 = _comentar(cli, "Segundo comentário.")
    assert j2["atividade"] == {} and len(cron["pedidos"]) == 1                  # o 2º não mexe


def test_os_de_varios_ativos_ou_atividade_ja_iniciada_nao_mexe(cron, fila):
    cli = _cliente()
    cli.get(URL)
    cron["tarefas"] = [21, 22]
    assert _comentar(cli)["atividade"] == {} and not cron["pedidos"]
    cron["banco"].clear()
    cron["tarefas"], cron["estado"] = [21], "rodando"                          # alguém já iniciou pela página da OS
    assert _comentar(cli)["atividade"] == {} and not cron["pedidos"]


def test_quando_o_fracttal_nao_inicia_o_comentario_fica_e_a_tela_avisa(cron, fila, monkeypatch):
    monkeypatch.setattr(api, "iniciar_execucao", lambda tid, inicio=None: {"ok": False, "erro": "SEM_PERMISSAO"})
    cli = _cliente()
    cli.get(URL)
    j = _comentar(cli)
    assert j["ok"] is True and len(cron["banco"]) == 1
    assert "não iniciou a atividade" in j["atividade"]["aviso"] and "SEM PERMISSAO" in j["atividade"]["aviso"]


def test_o_finalizar_encerra_a_atividade_antes_de_concluir(cron, fila):
    cli = _cliente()
    cli.get(URL)
    _comentar(cli)
    cron["estado"] = "pausada"
    j = cli.post("/os/api/acomp/9104/finalizar", json={"wid": 2}).get_json()
    assert j["ok"] is True and "A atividade foi encerrada" in j["mensagem"] and j["aviso"] == ""
    assert [p[0] for p in cron["pedidos"]] == ["iniciar", "retomar", "finalizar"] and cron["concluiu"] == 1


def test_a_atividade_de_outra_pessoa_nao_deixa_concluir_e_diz_de_quem_e(cron, fila):
    cli = _cliente()
    cli.get(URL)
    cron["estado"], cron["finaliza_falha"], cron["dono"] = "rodando", True, "Analista Dois"
    cron["registros"].append({"id": 1, "initial_date": "2026-11-14T12:00:00Z", "final_date": None})
    r = cli.post("/os/api/acomp/9104/finalizar", json={"wid": 2})
    assert r.status_code == 400 and "no nome de Analista Dois" in r.get_json()["erro"]
    assert cron["concluiu"] == 0                                               # não tenta concluir: o Fracttal recusaria


def test_o_chamado_sem_atividade_ganha_o_registro_do_primeiro_comentario_ate_a_finalizacao(cron, fila):
    """Os abertos de antes da regra: a atividade nunca começou; o Finalizar lança o registro inteiro."""
    cli = _cliente()
    cli.get(URL)
    antes = dt.datetime(2026, 11, 10, 9, 30, tzinfo=BRT)
    cron["banco"].append({"id": "o1", "quando": antes.isoformat(), "os": "9104", "tipo": "obs", "texto": "Aberto.",
                          "quem": "", "email": "", "ativo": "", "extra": {}})
    j = cli.post("/os/api/acomp/9104/finalizar", json={"wid": 2}).get_json()
    assert j["ok"] is True and "10/11 às 09:30" in j["mensagem"] and cron["concluiu"] == 1
    assert cron["pedidos"][0] == ("iniciar", 21, antes) and cron["pedidos"][1] == ("finalizar", 21)
    assert len(cron["pedidos"]) == 2                                           # o Fracttal guardou o início pedido


def test_se_o_fracttal_trocar_o_inicio_o_registro_e_corrigido(cron, fila):
    cli = _cliente()
    cli.get(URL)
    cron["ignora_inicio"] = True
    antes = dt.datetime(2026, 11, 10, 9, 30, tzinfo=BRT)
    cron["banco"].append({"id": "o1", "quando": antes.isoformat(), "os": "9104", "tipo": "obs", "texto": "Aberto.",
                          "quem": "", "email": "", "ativo": "", "extra": {}})
    cli.post("/os/api/acomp/9104/finalizar", json={"wid": 2})
    assert cron["pedidos"][-1][0] == "editar" and cron["pedidos"][-1][2] == antes


def test_sem_comentario_e_sem_atividade_conclui_como_sempre(cron, fila):
    cli = _cliente()
    cli.get(URL)
    j = cli.post("/os/api/acomp/9104/finalizar", json={"wid": 2}).get_json()
    assert j["ok"] is True and not cron["pedidos"] and cron["concluiu"] == 1


# ── o comentário apagado (Levi, 15/11/2026: "pense também na possibilidade de quando o comentário for apagado") ─────────
def _excluir(cli, id_obs):
    return cli.post("/os/api/acomp/9104/obs/%s/excluir" % id_obs, json={"wid": 2}).get_json()


def test_o_unico_comentario_apagado_desfaz_a_atividade_que_ele_iniciou(cron, fila):
    cli = _cliente()
    cli.get(URL)
    _comentar(cli)
    j = _excluir(cli, cron["banco"][0]["id"])
    assert j["ok"] is True and "foi desfeita" in j["atividade"]["mensagem"]
    assert [p[0] for p in cron["pedidos"]] == ["iniciar", "finalizar", "excluir"] and cron["registros"] == []
    assert _comentar(cli, "Agora no chamado certo.")["atividade"]["ok"] is True      # o próximo inicia de novo


def test_apagado_com_outros_comentarios_o_inicio_passa_ao_primeiro_em_vigor_na_finalizacao(cron, fila):
    cli = _cliente()
    cli.get(URL)
    _comentar(cli, "Primeiro.")
    cron["banco"].append({"id": "o2", "quando": (dt.datetime.now(BRT) + dt.timedelta(hours=2)).isoformat(), "os": "9104",
                          "tipo": "obs", "texto": "Segundo.", "quem": "", "email": "", "ativo": "", "extra": {}})
    j = _excluir(cli, cron["banco"][0]["id"])
    assert j["atividade"] == {} and [p[0] for p in cron["pedidos"]] == ["iniciar"]    # na hora, nada
    cli.post("/os/api/acomp/9104/finalizar", json={"wid": 2})
    acao, rid, ini, fim = cron["pedidos"][-1]
    assert acao == "editar" and ini == dt.datetime.fromisoformat(cron["banco"][1]["quando"]) and fim is not None


def test_a_atividade_que_nao_nasceu_de_comentario_nao_e_desfeita(cron, fila):
    """Iniciada à mão pela página da OS (o início não bate com a hora de nenhum comentário): o Nexus não mexe."""
    cli = _cliente()
    cli.get(URL)
    cron["estado"] = "rodando"
    cron["registros"].append({"id": 1, "initial_date": "2026-11-01T12:00:00Z", "final_date": None})
    _comentar(cli)                                                             # já tinha atividade: não inicia
    j = _excluir(cli, cron["banco"][0]["id"])
    assert j["atividade"] == {} and not cron["pedidos"] and cron["estado"] == "rodando"


def test_apagar_o_primeiro_e_depois_o_segundo_desfaz_a_atividade(cron, fila):
    """A atividade nasceu do 1º (já apagado); apagado o último que restava, ela é desfeita."""
    cli = _cliente()
    cli.get(URL)
    _comentar(cli, "Primeiro.")
    _comentar(cli, "Segundo.")
    assert _excluir(cli, cron["banco"][0]["id"])["atividade"] == {}
    j = _excluir(cli, cron["banco"][1]["id"])
    assert "foi desfeita" in j["atividade"]["mensagem"] and cron["registros"] == []
