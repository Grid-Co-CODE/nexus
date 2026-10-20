"""O Histórico do OS Creator sem repetir o Fracttal (19/10/2026; Levi: "o que causa essa busca de 2.000, todas as buscas
são necessárias?" e "tem como atualizar só o dia somando com o que já carregou ou tem que carregar tudo de novo?").
Cada carga da Visão COS eram ~26 pedidos (10 páginas de 200 OS e 16 lotes das tarefas), repetidos por pessoa, a cada
atualização automática de 10 min de cada aba e a cada ↻; e as 2.000 linhas montadas a cada pedido (43 s no servidor).
Aqui se conta quantas vezes cada cenário vai ao Fracttal. Nada sai da máquina."""
import sys
import threading
import time

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import criar_app, rotas  # noqa: E402
from os_web import historico_store as HS  # noqa: E402

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira


def _os(i, data, status_id=1):
    return {"id": i, "folio": str(10000 + i), "cliente": "Cliente X", "usina": "Usina Teste", "tipo": "Inversor",
            "ativo": "Inversor 1.1", "descricao": "OS de teste", "status_id": status_id,
            "status": api.WO_STATUS[status_id], "data": data, "tipo_tarefa": "Corretiva", "event_date": "",
            "data_fim": "", "note": "", "inicio": "", "gatilho": "", "etiquetas": [], "criado_por": "Alguém",
            "programada": "", "equipe": ""}


class _Fracttal:
    """O Fracttal de mentira do Histórico: guarda cada busca (inteira ou das novas) e cada conferência de total."""

    def __init__(self, linhas, total=None):
        self.linhas, self.total = list(linhas), total
        self.buscas, self.totais, self.trava = [], [], threading.Lock()
        self.espera = 0.0
        self.erro = None

    def list_minhas_os(self, **kw):
        with self.trava:
            self.buscas.append(kw)
        if self.espera:
            time.sleep(self.espera)
        if self.erro:
            raise self.erro
        de = kw.get("de") or ""
        linhas = [dict(x) for x in self.linhas if x["data"] >= de] if "T" in de else [dict(x) for x in self.linhas]
        if isinstance(kw.get("info"), dict):
            kw["info"].update({"total": self.total or len(self.linhas), "cap": api.HISTORICO_CAP})
        return linhas

    def pagina(self, *a, **k):
        with self.trava:
            self.totais.append(a)
        return {"total": self.total or len(self.linhas), "linhas": [], "tem_mais": False}

    def inteiras(self):
        return [b for b in self.buscas if "T" not in str(b.get("de") or "")]

    def novas(self):
        return [b for b in self.buscas if "T" in str(b.get("de") or "")]


@pytest.fixture
def fr(monkeypatch):
    import requests

    def sem_rede(*a, **k):                    # a cota do Fracttal é da empresa: aqui nada sai da máquina
        raise AssertionError("o teste tentou ir à rede")
    monkeypatch.setattr(requests.Session, "request", sem_rede)
    f = _Fracttal([_os(i, f"2026-10-19T{8 + i // 60:02d}:{i % 60:02d}:00") for i in range(1, 6)])
    monkeypatch.setattr(api, "list_minhas_os", f.list_minhas_os)
    monkeypatch.setattr(api, "list_minhas_os_pagina", f.pagina)
    monkeypatch.setattr(api, "get_labels", lambda *a, **k: [])
    monkeypatch.setattr(api, "get_pessoas_contas", lambda *a, **k: {"pessoas": [], "eu": None})
    monkeypatch.setattr(api, "_code_to_loc", lambda *a, **k: {})
    monkeypatch.setattr(api, "_read_asset_cache", lambda *a, **k: [])
    monkeypatch.setattr(rotas, "_em_segundo_plano", lambda fn: fn())        # a renovação por trás, na hora
    relogio = {"t": 1000.0}
    monkeypatch.setattr(HS, "_relogio", lambda: relogio["t"])
    f.relogio = relogio
    yield f
    HS.limpar()


def _cliente(email="pessoa1@exemplo.invalid"):
    c = criar_app(segredo="teste", testing=False).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": email, "perfil": "ADMINISTRATOR"}
    return c


def _hist(c, q="modo=cos"):
    r = c.get("/os/historico?" + q)
    assert r.status_code == 200
    return r.get_data(as_text=True)


def test_a_lista_de_todos_e_uma_so_para_quem_ve_o_mesmo(fr):
    a, b = _cliente("a@exemplo.invalid"), _cliente("b@exemplo.invalid")
    assert "10005" in _hist(a) and "10005" in _hist(b)
    # uma busca inteira para as duas pessoas; a 2ª só confere o total na sessão dela (1 pedido de 1 linha)
    assert len(fr.inteiras()) == 1 and len(fr.totais) == 1
    assert len(fr.buscas[0]) and fr.buscas[0]["id_account"] == "TODOS"


def test_quem_ve_outro_total_no_fracttal_fica_com_a_dele(fr):
    a, b = _cliente("a@exemplo.invalid"), _cliente("b@exemplo.invalid")
    _hist(a)
    fr.total = 2                                   # a visão da 2ª pessoa no Fracttal é restrita
    _hist(b)
    assert len(fr.inteiras()) == 2                 # ela não vê a lista de quem vê mais


def test_a_lista_vencida_volta_na_hora_e_se_renova_so_com_as_novas(fr):
    c = _cliente()
    _hist(c)
    fr.linhas.append(_os(99, "2026-10-19T15:00:00"))             # alguém criou uma OS depois da carga
    fr.relogio["t"] += HS.TTL_S + 1
    html = _hist(c)                                # volta a lista guardada; a renovação (no teste, na hora) vem depois
    assert "10099" not in html
    assert len(fr.inteiras()) == 1 and len(fr.novas()) == 1
    assert fr.novas()[0]["de"] == "2026-10-19T07:55:00"         # a mais nova guardada (08:05) menos 10 min
    assert "10099" in _hist(c)                     # somada ao que já estava, sem buscar tudo de novo
    assert len(fr.inteiras()) == 1


def test_a_cada_10_min_a_lista_inteira_e_as_fechadas_nao_relem_as_tarefas(fr):
    fr.linhas[0]["status_id"], fr.linhas[0]["status"] = 3, "Concluída"
    fr.linhas[1]["status_id"], fr.linhas[1]["status"] = 4, "Cancelada"
    c = _cliente()
    _hist(c)
    fr.relogio["t"] += HS.INTEIRA_S + 1
    _hist(c)
    assert len(fr.inteiras()) == 2
    ja = fr.inteiras()[1]["meta_ja"]
    assert set(ja) == {1, 2} and ja[1]["status_id"] == 3          # só as fechadas levam o que já se sabia


def test_o_refresco_logo_depois_da_carga_so_busca_as_novas(fr):
    c = _cliente()
    _hist(c)
    _hist(c, "modo=cos&atualizar=1")
    assert len(fr.inteiras()) == 1 and len(fr.novas()) == 1
    fr.relogio["t"] += HS.REFRESCO_MIN_S + 1
    _hist(c, "modo=cos&atualizar=1")               # passado 1 min, o ↻ busca tudo (o status das antigas)
    assert len(fr.inteiras()) == 2


def test_varias_pessoas_juntas_fazem_uma_busca_so(fr):
    fr.espera = 0.3
    saidas = []
    ts = [threading.Thread(target=lambda e=e: saidas.append(_hist(_cliente(e))))
          for e in ("a@exemplo.invalid", "b@exemplo.invalid", "c@exemplo.invalid")]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert len(saidas) == 3 and all("10005" in h for h in saidas)
    assert len(fr.inteiras()) == 1


def test_o_fracttal_fora_por_tras_mantem_a_lista(fr):
    c = _cliente()
    _hist(c)
    fr.erro = api.FracttalError("HTTP 429")
    fr.relogio["t"] += HS.TTL_S + 1
    assert "10005" in _hist(c)                     # a renovação falhou por trás; a lista guardada segue
    assert "10005" in _hist(c)


def test_as_linhas_sao_montadas_uma_vez_por_versao(fr, monkeypatch):
    montadas = []
    original = HS.html_das_linhas

    def contar(lista, chave, montar):
        return original(lista, chave, lambda: montadas.append(chave) or montar())
    monkeypatch.setattr(HS, "html_das_linhas", contar)
    for e in ("a@exemplo.invalid", "b@exemplo.invalid", "a@exemplo.invalid"):
        _hist(_cliente(e))
    assert montadas == [("cos", "")]


def test_a_atualizacao_automatica_usa_a_lista_guardada(fr):
    html = _hist(_cliente())
    js = html[html.index("setInterval(function () {\n    if (document.hidden"):]
    assert js.split("}, 10 * 60 * 1000")[0].strip().endswith("enviar(false);")
    assert "Lista das " in html


def test_juntar_e_desde():
    g = [_os(1, "2026-10-19T08:00:00"), _os(2, "2026-10-19T09:00:00")]
    n = [_os(2, "2026-10-19T09:00:00", 3), _os(3, "2026-10-19T10:00:00")]
    j = HS.juntar(g, n, cap=2)
    assert [d["id"] for d in j] == [3, 2] and j[1]["status_id"] == 3        # a linha nova vale; o teto corta a mais velha
    assert HS.desde(g) == "2026-10-19T08:50:00" and HS.desde([]) is None


def test_list_minhas_os_reaproveita_as_tarefas_das_fechadas(monkeypatch):
    linhas = [{"id": 1, "wo_folio": "1", "id_status_work_order": 3, "creation_date": "2026-10-19T08:00:00"},
              {"id": 2, "wo_folio": "2", "id_status_work_order": 1, "creation_date": "2026-10-19T09:00:00"},
              {"id": 3, "wo_folio": "3", "id_status_work_order": 1, "creation_date": "2026-10-19T10:00:00"}]
    monkeypatch.setattr(api, "_rpc_call", lambda *a, **k: {"total": 3, "data": [dict(x) for x in linhas]})
    monkeypatch.setattr(api, "_code_to_loc", lambda *a, **k: {})
    pedidos = []

    def meta(ids, passo=None):
        pedidos.append(list(ids))
        return {i: {"tipo_tarefa": "Nova"} for i in ids}
    monkeypatch.setattr(api, "_meta_tarefa_por_os", meta)
    ja = {1: {"status_id": 3, "tipo_tarefa": "Antiga"}, 2: {"status_id": 3, "tipo_tarefa": "Reaberta"}}
    out = {d["id"]: d for d in api.list_minhas_os(id_account="TODOS", meta_ja=ja)}
    assert pedidos == [[3, 2]]                     # a fechada que seguiu fechada não vai; a reaberta (2) e a nova vão
    assert out[1]["tipo_tarefa"] == "Antiga" and out[2]["tipo_tarefa"] == "Nova"


def test_o_circulo_de_carga_nao_muda_o_total_no_meio(monkeypatch):
    """O círculo do Histórico (Levi, 27/09) conta os pedidos ao Fracttal: o total sai depois da 1ª página e não muda no
    meio da carga, e o último aviso fecha em 100% (o oem cobra o mesmo). Os lotes das tarefas que não vão ao Fracttal
    (as fechadas já sabidas, ou menos OS do que o total do servidor) contam como feitos logo depois das páginas."""
    monkeypatch.setattr(api, "_current_user_ids", lambda: (10, 77))
    monkeypatch.setattr(api, "_rpc_call", lambda metodo, params: {"total": 450, "data": [{"id": params.get("start", 0) + 1}]}
                        if metodo == api.RPC_WO_LIST else {"data": []})
    monkeypatch.setattr(api, "_shape_wo_row", lambda w: {"id": w["id"], "data": "2026-09-11T12:00:00"})
    vistos = []
    api.list_minhas_os(progresso=lambda f, t: vistos.append((f, t)))
    # 3 páginas (200 + 200 + 50) + 4 lotes estimados (450 / 130) = 7; chegaram 3 OS: 1 lote só, os outros 3 contam já
    assert vistos[0] == (1, 7) and vistos[-1] == (7, 7) and all(t == 7 for _, t in vistos)
    assert [f for f, _ in vistos] == sorted(f for f, _ in vistos)
