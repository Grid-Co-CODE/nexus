"""A OS pai do chamado não é da própria cadeia do chamado, e o ativo com chamado em aberto não ganha outro (25/11/2026, Levi:
"Está tendo casos de OS de inspeção gerando outras OS de inspeção na parte de chamados"; à tarde, só no OS Creator, a
preventiva e os outros tipos abrem: "No OS Creator pode ser um pouquinho mais flexível"). O "Abrir chamado" do card (10/11/2026) aparecia em
toda OS e a Inspeção virava pai de outra Inspeção; a web não olhava se o ativo já tinha chamado. As duas regras são as do
App (`chamado_garantia.TIPOS_ORIGEM` e a v361). O Fracttal e o banco são de mentira."""
import pytest

from test_oscreator_card_tarefas import WID, Fracttal, _card, _item, _tarefa  # noqa: F401
from test_oscreator_solic_pcm import api  # noqa: F401

from os_web import chamado_aberto, criar_app  # noqa: E402
from os_web import insp_web as iw  # noqa: E402
from os_web import rotas  # noqa: E402

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
ATIVO = {"id": 501, "code": "TST-INV1.7", "tipo": "Inversor", "description": "Inversor 1.7 Huawei",
         "usina": "Usina Teste", "cliente": "Cliente Teste"}


def _cliente():
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": ""}
    return c


def _card_do_tipo(monkeypatch, tipo):
    t = _tarefa(1)
    t["tasks_types_main_description"] = tipo
    monkeypatch.setattr(api, "_rpc_call", Fracttal([t], [_item(1, 1)]).rpc)
    return _card()


# à tarde do mesmo dia (Levi: "muitas vezes dados levantados de OS de preventiva ou de outro tipo, às vezes é visto que vai
# precisar abrir chamado [...] No OS Creator pode ser um pouquinho mais flexível"): na web vale qualquer OS menos a
# Inspeção e a Administrativa do chamado; o App segue com o TIPOS_ORIGEM
@pytest.mark.parametrize("tipo, pode", [("Corretiva", True), ("Corretiva Emergencial", True), ("Religamento", True),
                                        ("Religamento Remoto", True), ("Preventiva", True), ("Preditiva", True),
                                        ("Inspeção", False), ("Administrativa", False), ("inspeção", False),
                                        ("Inspeção / Administrativa", False), ("Inspeção / Corretiva", True),
                                        ("Inspeção / Preventiva", True), ("", True), (None, True)])
def test_na_web_a_os_pai_e_qualquer_uma_menos_a_cadeia_do_chamado(tipo, pode):
    assert iw.pai_de_origem(tipo) is pode


def test_o_app_segue_so_com_a_corretiva_e_o_religamento():
    from chamado_garantia.regras import TIPOS_ORIGEM
    assert TIPOS_ORIGEM == ("Corretiva", "Corretiva Emergencial", "Religamento", "Religamento Remoto")


def test_o_abrir_chamado_aparece_menos_na_cadeia_do_chamado(monkeypatch):
    assert "Abrir chamado</a>" in _card_do_tipo(monkeypatch, "Corretiva Emergencial")
    assert "Abrir chamado</a>" in _card_do_tipo(monkeypatch, "Preventiva")
    # a Inspeção não abre chamado: era assim que nascia a inspeção da inspeção
    assert "Abrir chamado</a>" not in _card_do_tipo(monkeypatch, "Inspeção")
    assert "Abrir chamado</a>" not in _card_do_tipo(monkeypatch, "Administrativa")


def test_a_inspecao_como_os_pai_e_recusada_ao_escolher(monkeypatch):
    monkeypatch.setattr(api, "get_os_detalhes_por_folio",
                        lambda f: {"folio": f, "tipo": "Inspeção", "code": ATIVO["code"], "id_work_order": 77})
    r = _cliente().get("/os/api/insp/pai?folio=19398")
    assert r.status_code == 400
    assert r.get_json()["erro"].startswith("A OS 19398 é Inspeção, que já é do chamado.")


@pytest.mark.parametrize("tipo", ["Corretiva Emergencial", "Preventiva"])
def test_a_corretiva_e_a_preventiva_como_os_pai_seguem(monkeypatch, tipo):
    monkeypatch.setattr(api, "get_os_detalhes_por_folio",
                        lambda f: {"folio": f, "tipo": tipo, "code": ATIVO["code"],
                                   "id_work_order": 77, "event_date": "2026-11-25T08:18:00", "responsavel": ""})
    monkeypatch.setattr(rotas, "responsaveis_fracttal", lambda: [])
    monkeypatch.setattr(api, "load_assets_cached", lambda: [ATIVO])
    r = _cliente().get("/os/api/insp/pai?folio=20421")
    assert r.status_code == 200 and r.get_json()["folio"] == "20421"


@pytest.fixture
def criar(monkeypatch):
    """A criação com o ativo de teste; devolve a lista do que o Fracttal criaria."""
    feitas = []
    monkeypatch.setattr(api, "load_assets_cached", lambda: [ATIVO])
    monkeypatch.setattr(api, "create_inspecao_chamado",
                        lambda **kw: feitas.append(kw) or {"wo_folio": "30001", "n_subtarefas": 3})
    monkeypatch.setattr(chamado_aberto, "_ler", lambda: {})
    chamado_aberto.esquecer()
    yield feitas
    chamado_aberto.esquecer()


def _corpo(pai_id=None):
    marca = iw.ci.marcas_para("Inversor")[0]
    return {"ativo": ATIVO["id"], "marca": marca, "resp_id": 9, "resp_nome": "Pessoa Teste", "pai_id": pai_id}


def test_a_inspecao_como_os_pai_e_recusada_ao_criar(monkeypatch, criar):
    monkeypatch.setattr(api, "_meta_tarefa_por_os", lambda ids: {77: {"tipo_tarefa": "Inspeção"}})
    r = _cliente().post("/os/api/insp/criar", json=_corpo(pai_id=77))
    assert r.status_code == 400 and "A OS pai escolhida é Inspeção" in r.get_json()["erro"]
    assert criar == []


def test_a_preventiva_como_os_pai_cria(monkeypatch, criar):
    monkeypatch.setattr(api, "_meta_tarefa_por_os", lambda ids: {77: {"tipo_tarefa": "Preventiva"}})
    r = _cliente().post("/os/api/insp/criar", json=_corpo(pai_id=77))
    assert r.status_code == 200 and len(criar) == 1 and criar[0]["id_parent"] == 77


def test_o_ativo_com_chamado_aberto_nao_ganha_outro(monkeypatch, criar):
    monkeypatch.setattr(api, "_meta_tarefa_por_os", lambda ids: {77: {"tipo_tarefa": "Corretiva"}})
    monkeypatch.setattr(chamado_aberto, "_ler",
                        lambda: {"TST-INV1.7": {"inspecao": "20475", "adm": "20482", "coluna": "chegaram"}})
    r = _cliente().post("/os/api/insp/criar", json=_corpo(pai_id=77))
    assert r.status_code == 409
    assert "inspeção 20475 e administrativa 20482" in r.get_json()["erro"]
    assert criar == []


def test_a_corretiva_sem_chamado_aberto_cria(monkeypatch, criar):
    monkeypatch.setattr(api, "_meta_tarefa_por_os", lambda ids: {77: {"tipo_tarefa": "Corretiva Emergencial"}})
    r = _cliente().post("/os/api/insp/criar", json=_corpo(pai_id=77))
    assert r.status_code == 200 and r.get_json()["folio"] == "30001"
    assert len(criar) == 1 and criar[0]["id_parent"] == 77


def test_sem_os_pai_e_sem_a_foto_cria_como_antes(monkeypatch, criar):
    def falha():
        raise RuntimeError("banco fora")
    monkeypatch.setattr(chamado_aberto, "_ler", falha)
    r = _cliente().post("/os/api/insp/criar", json=_corpo())
    assert r.status_code == 200 and len(criar) == 1


def test_o_codigo_casa_como_o_do_app(monkeypatch):
    lidas = []
    monkeypatch.setattr(chamado_aberto, "_ler",
                        lambda: lidas.append(1) or {"GYT100-INVR1.7": {"inspecao": "1", "adm": "", "coluna": "x"}})
    chamado_aberto.esquecer()
    assert chamado_aberto.do_ativo(" gyt100-invr1.7 ")["inspecao"] == "1"
    assert chamado_aberto.do_ativo("GYT100-INVR1.8") is None and chamado_aberto.do_ativo("") is None
    assert lidas == [1]                     # a foto fica 1 min na memória
    chamado_aberto.esquecer()
