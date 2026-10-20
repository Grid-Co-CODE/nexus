"""O Acompanhamento de chamados só relê o Fracttal no Atualizar ou a cada 30 min (Levi, 20/10/2026: "o kanban carrega, eu
clico na OS e aparece a tela daquele chamado, quando tento voltar para acompanhamento dá uma travada, faz outra pesquisa
no fractal? poderíamos otimizar isso, só pesquisar caso a singrid clique em atualizar, fora isso fica mostrando o que já
carregou ou carrega a cada 30 min").

Até então a cópia do quadro valia 3 min, e cada gravação da tela do chamado (o ticket, o finalizar, o responsável)
apagava o quadro da memória: a volta ao quadro esperava a lista e os tickets do Fracttal na frente de quem voltou. Agora a
gravação ajusta o quadro guardado com o que ela mesma gravou, e a volta não vai ao Fracttal.

Fracttal FALSO: nenhum pedido vai à rede, cada leitura é contada, e a releitura por trás fica parada numa fila até o
teste mandar rodar. Nomes e números de mentira: o repositório é público."""
import sys
import threading

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import chamados_obs_store as obs_store  # noqa: E402
from os_web import criar_app, rotas, rotas_acomp  # noqa: E402

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
URL = "/os/chamados/acompanhamento"
PESSOA = ("Pessoa Teste", "teste@exemplo.invalid")


def _cliente():
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": PESSOA[0], "email": PESSOA[1], "perfil": ""}
    return c


def _linha(i, folio):
    return {"id": i, "folio": str(folio), "cliente": "Cliente Teste", "usina": "Usina Teste", "ativo": "Inversor 1.1",
            "tipo": "Inversor", "tipo_tarefa": "Administrativa", "note": "",
            "descricao": "[Inversor 1.1] - Acompanhamento de chamado Marca", "status_id": 1,
            "status": api.WO_STATUS.get(1), "data": "2026-10-01T12:00:00", "data_fim": "",
            "atribuido_a": "Técnico Teste", "id_atribuido": 900002}


@pytest.fixture(autouse=True)
def _memoria_limpa(monkeypatch):
    monkeypatch.setattr(obs_store, "_linhas", lambda: [])              # o banco da Gridco: nenhum teste vai
    monkeypatch.setattr(obs_store, "adicionar", lambda folio, texto, tipo, **k: {"quando": "", "texto": texto,
                                                                                 "tipo": tipo, "quem": PESSOA[0]})
    obs_store._estado.update(lista=None, lido=0.0)
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    rotas_acomp._RENOVANDO.clear()
    rotas_acomp._ESQUECIDO["em"] = 0.0
    del getattr(rotas_acomp, "_AJUSTES", [])[:]
    yield
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    rotas_acomp._RENOVANDO.clear()
    del getattr(rotas_acomp, "_AJUSTES", [])[:]


@pytest.fixture
def fila(monkeypatch):
    """As releituras por trás, paradas até o teste mandar rodar."""
    jobs = []
    monkeypatch.setattr(rotas_acomp, "_em_segundo_plano", jobs.append)
    return jobs


@pytest.fixture
def fracttal(monkeypatch):
    lido = {"listas": 0, "tickets": 0, "gravados": []}

    def listar(**k):
        lido["listas"] += 1
        if isinstance(k.get("info"), dict):
            k["info"]["total"] = 2
        return [_linha(1, 9103), _linha(2, 9104)]

    def tickets(ids):
        lido["tickets"] += 1
        return {i: "" for i in ids}                                       # as duas esperando ticket

    def detalhe(wid):
        return {"folio": {1: 9103, 2: 9104}[wid], "notas": "", "code": "TESTE-INVR1.1",
                "subtarefas": [{"descricao": "Nº do ticket no fornecedor", "resposta": "", "id_form_item": 11,
                                "id_tarefa": 21, "tipo_id": 1}]}
    monkeypatch.setattr(api, "list_chamados", listar)
    monkeypatch.setattr(api, "tickets_os3_em_massa", tickets)
    monkeypatch.setattr(api, "total_chamados", lambda de=None: 2)
    monkeypatch.setattr(api, "get_os_detalhes", detalhe)
    monkeypatch.setattr(api, "salvar_subtarefas", lambda wid, tarefa, itens: lido["gravados"].append((wid, itens)))
    return lido


def _envelhecer(segundos):
    with rotas._MEMO_LOCK:
        for k, (t, v) in list(rotas._MEMO.items()):
            rotas._MEMO[k] = (t - segundos, v)


def _coluna(h, titulo):
    """O HTML de uma coluna do quadro, pelo título ("Chegaram", "Ticket aberto", "Finalizados")."""
    return h.split("<h2>%s</h2>" % titulo, 1)[1].split('<section class="col', 1)[0]


def test_o_quadro_guardado_vale_30_min(fracttal, fila):
    assert rotas_acomp.TTL_QUADRO == 30 * 60
    cli = _cliente()
    cli.get(URL)
    _envelhecer(29 * 60)
    h = cli.get(URL).get_data(as_text=True)
    assert (fracttal["listas"], fracttal["tickets"]) == (1, 1) and not fila      # nada foi ao Fracttal, nem por trás
    assert "data-renovando" not in h


def test_depois_de_30_min_abre_na_hora_e_rele_por_tras(fracttal, fila):
    cli = _cliente()
    cli.get(URL)
    _envelhecer(31 * 60)
    h = cli.get(URL).get_data(as_text=True)
    assert fracttal["listas"] == 1 and "data-renovando" in h and len(fila) == 1


def test_o_atualizar_rele_na_hora(fracttal, fila):
    cli = _cliente()
    cli.get(URL)
    cli.get(URL + "?atualizar=1")
    assert (fracttal["listas"], fracttal["tickets"]) == (2, 2) and not fila


def test_gravar_o_ticket_ajusta_o_quadro_e_a_volta_nao_vai_ao_fracttal(fracttal, fila):
    cli = _cliente()
    cli.get(URL)
    r = cli.post("/os/api/acomp/9103/ticket", json={"ticket": "SR 90000001", "wid": 1})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    assert fracttal["gravados"] == [(1, [{"id_form_item": 11, "valor": "SR 90000001", "tipo": 1}])]
    h = cli.get(URL).get_data(as_text=True)                                   # a volta ao quadro
    assert (fracttal["listas"], fracttal["tickets"]) == (1, 1) and not fila
    assert "OS 9103" in _coluna(h, "Ticket aberto") and "SR 90000001" in _coluna(h, "Ticket aberto")
    assert "OS 9103" not in _coluna(h, "Chegaram") and "OS 9104" in _coluna(h, "Chegaram")


def test_finalizar_ajusta_o_quadro_pelo_status_que_o_fracttal_deu(fracttal, fila, monkeypatch):
    monkeypatch.setattr(api, "concluir_os_checado", lambda wid: {"ok": True, "data_fim": {}})
    monkeypatch.setattr(api, "_cabecalho_os", lambda wid: {"wo_folio": "9104", "id_status_work_order": 2})
    cli = _cliente()
    cli.get(URL)
    assert cli.post("/os/api/acomp/9104/finalizar", json={"wid": 2}).get_json()["ok"] is True
    h = cli.get(URL).get_data(as_text=True)
    assert (fracttal["listas"], fracttal["tickets"]) == (1, 1) and not fila
    assert "OS 9104" in _coluna(h, "Finalizados") and "em verificação" in _coluna(h, "Finalizados")
    assert "OS 9104" not in _coluna(h, "Chegaram")


def test_finalizar_sem_saber_o_status_tira_o_quadro_como_antes(fracttal, fila, monkeypatch):
    """Sem o status do Fracttal depois de concluir, o quadro não chuta: sai da memória e a volta relê, como até hoje."""
    monkeypatch.setattr(api, "concluir_os_checado", lambda wid: {"ok": True, "data_fim": {}})
    monkeypatch.setattr(api, "_cabecalho_os", lambda wid: {})
    cli = _cliente()
    cli.get(URL)
    cli.post("/os/api/acomp/9104/finalizar", json={"wid": 2})
    cli.get(URL)
    assert fracttal["listas"] == 2


def test_trocar_o_responsavel_ajusta_o_quadro(fracttal, fila, monkeypatch):
    monkeypatch.setattr(api, "mudar_responsavel", lambda wid, idp, nota=None: {"ok": True})
    cli = _cliente()
    cli.get(URL)
    r = cli.post("/os/api/os/1/responsavel", json={"id_personnel": 900003, "name": "Pessoa Nova", "folio": "9103"})
    assert r.get_json()["ok"] is True
    h = cli.get(URL).get_data(as_text=True)
    assert fracttal["listas"] == 1 and not fila
    cartao = h.split("OS 9103", 1)[1].split("</a>", 1)[0]
    assert "Pessoa Nova" in cartao and "Técnico Teste" not in cartao


def test_a_releitura_que_comecou_antes_da_gravacao_leva_a_gravacao(fracttal, fila, monkeypatch):
    """A releitura por trás que começou antes do ticket termina depois dele: o quadro que ela guarda já leva o ticket
    (antes, a cópia saía da memória e a volta relia na frente)."""
    cli = _cliente()
    cli.get(URL)
    _envelhecer(31 * 60)
    cli.get(URL)                                                              # agenda a releitura por trás
    job = fila.pop()
    lendo, seguir = threading.Event(), threading.Event()
    listar = api.list_chamados

    def devagar(**k):
        lendo.set()
        seguir.wait(10)                                                       # a lista que o Fracttal deu ANTES do ticket
        return listar(**k)
    monkeypatch.setattr(api, "list_chamados", devagar)
    t = threading.Thread(target=job)
    t.start()
    assert lendo.wait(10)
    cli.post("/os/api/acomp/9103/ticket", json={"ticket": "SR 90000002", "wid": 1})
    seguir.set()
    t.join(10)
    h = cli.get(URL).get_data(as_text=True)
    assert fracttal["listas"] == 2                                            # a da 1ª visita e a por trás: nenhuma na frente
    assert "SR 90000002" in _coluna(h, "Ticket aberto")


def test_o_teto_da_memoria_nao_tira_o_quadro(fracttal, fila):
    """A memória do OS Creator tem teto (300) e tirava o que foi guardado há mais tempo: com 30 min, seria o quadro."""
    cli = _cliente()
    cli.get(URL)
    for i in range(400):
        rotas._memo(("anexos", "teste@exemplo.invalid", i), 20, lambda: [])
    cli.get(URL)
    assert fracttal["listas"] == 1


def test_seis_cartoes_a_vista_em_cada_coluna():
    """A altura da coluna cabe 6 cartões (Levi, 20/10/2026: "aumente o tamanho ... para mostrar 6 ... nas colunas"): o
    acomp.js mede o 6º cartão visível e o CSS usa a medida; no celular a coluna não tem teto, como antes."""
    from pathlib import Path
    web = Path(ponte.RAIZ_CLONE) / "os_web" / "static"
    js = (web / "acomp.js").read_text(encoding="utf-8")
    css = (web / "chamados.css").read_text(encoding="utf-8")
    assert "CARTOES_A_VISTA = 6" in js and "--cards-max" in js
    assert "max-height:var(--cards-max,72vh)" in css
    assert "@media (max-width:1000px){.cards{max-height:none;overflow:visible}}" in css
