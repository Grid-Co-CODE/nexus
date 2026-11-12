"""As rotas da transferência na ponte do login do Fracttal (`/os/_nexus/inventario/transferir`; 12/11/2026): a lista dos
almoxarifados lida no Fracttal, as peças com saldo na origem, o Conferir e o Transferir, com as guardas das requisições (o setor, a
origem do pedido, a pessoa, o login do Fracttal e o `so_no_servidor`). O Fracttal é o `EstoqueFalso`. Dado de mentira."""
import pytest
from test_campo_visao import banco  # noqa: F401  (banco é fixture)
from test_pcm_inventario_curadoria import _pessoa_ms
from test_pcm_inventario_estoque import com_o_fracttal
from test_pcm_inventario_transferencia_regra import PESSOA, _eventos, _falso, tr  # noqa: F401  (tr é fixture)
from test_pcm_publicar import _no_setor

from nexus.cadastro import setor_ids as SID
from nexus.pcm.inventario import estoque as E

BASE = "/os/_nexus/inventario/transferir"
PEDIDO = {"origem": "30", "destino": "31", "item": "1", "qtd": "2", "referencia": "OS 4521"}


def _pcm(app_, monkeypatch, falso, email=None):
    monkeypatch.setattr(E, "estoque_da_sessao", lambda app: falso)
    _no_setor(monkeypatch, SID.PCM)
    return com_o_fracttal(app_, _pessoa_ms(app_), email or PESSOA["email"])


def test_a_lista_dos_almoxarifados_vem_do_fracttal(tr, monkeypatch):
    c = _pcm(tr, monkeypatch, _falso(inativos={"40"}))
    r = c.get(f"{BASE}/almoxarifados")
    j = r.get_json()
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store" and j["ok"] is True
    assert {a["id"]: a["cliente"] for a in j["almoxarifados"]} == {"31": "Cliente Alfa", "60": "CLIENTE ÁLFA",
                                                                   "30": "Cliente Alfa", "50": ""}
    assert j["almoxarifados"][0] == {"id": "31", "nome": "Almoxarifado Usina Dois", "cliente": "Cliente Alfa", "teste": False}


def test_as_pecas_com_saldo_na_origem(tr, monkeypatch):
    c = _pcm(tr, monkeypatch, _falso())
    j = c.get(f"{BASE}/pecas", query_string={"origem": "30"}).get_json()
    assert [(p["id"], p["codigo"], p["saldo"], p["decimal"]) for p in j["pecas"]] == [("1", "SP-1", 5, False),
                                                                                     ("2", "SP-2", 2.5, True)]
    assert j["pecas"][0]["nome"]                                       # o nome pelo catálogo do App
    assert c.get(f"{BASE}/pecas", query_string={"origem": "x"}).status_code == 400


def test_conferir_e_transferir(tr, monkeypatch):
    falso = _falso()
    c = _pcm(tr, monkeypatch, falso)
    r = c.post(f"{BASE}/conferir", json=PEDIDO)
    p = r.get_json()["plano"]
    assert r.status_code == 200 and (p["origem"]["depois"], p["destino"]["depois"], p["vincular"]) == (3, 3, False)
    assert falso.transferencias == []
    r = c.post(f"{BASE}/conferir", json=dict(PEDIDO, destino="40"))
    assert r.status_code == 409 and "outro cliente" in r.get_json()["erro"]
    assert c.post(f"{BASE}/conferir", json=dict(PEDIDO, destino="30")).status_code == 400
    r = c.post(BASE, json=PEDIDO)
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] and j["confirmada"] and j["volta"] == "/t/pcm/pecas/transferir"
    assert len(falso.transferencias) == 1 and falso.transferencias[0]["id_responsible"] == 501
    assert [e["tipo"] for e in _eventos(tr)] == ["transferencia_saida", "transferencia_entrada"]
    assert falso.transferencias[0]["description"].startswith("OS 4521 · Transferência pelo Nexus NX-TR-")


def test_o_nao_do_fracttal_vem_com_o_status(tr, monkeypatch):
    from test_pcm_inventario_transferencia_regra import _TransferenciaRecusada
    c = _pcm(tr, monkeypatch, _falso(classe=_TransferenciaRecusada))
    r = c.post(BASE, json=PEDIDO)
    assert r.status_code == 409 and r.get_json()["ok"] is False and "Nada foi transferido" in r.get_json()["erro"]


def test_transferir_so_no_servidor(tr, monkeypatch):
    falso = _falso()
    c = _pcm(tr, monkeypatch, falso)
    monkeypatch.delitem(tr.config, "NEXUS_INVENTARIO_GRAVAR")
    r = c.post(BASE, json=PEDIDO)
    assert r.status_code == 409 and "só roda no servidor" in r.get_json()["erro"]
    assert falso.chamadas == [] and falso.transferencias == []
    assert c.post(f"{BASE}/conferir", json=PEDIDO).status_code == 200           # o Conferir só lê: abre em qualquer um


@pytest.mark.parametrize("rota, metodo", [(f"{BASE}/almoxarifados", "get"), (f"{BASE}/pecas?origem=30", "get"),
                                          (f"{BASE}/conferir", "post"), (BASE, "post")])
def test_as_recusas_da_ponte(tr, monkeypatch, logado, rota, metodo):
    falso = _falso()
    monkeypatch.setattr(E, "estoque_da_sessao", lambda app: falso)
    com_o_fracttal(tr, logado, "outra.pessoa@exemplo.test")
    r = getattr(logado, metodo)(rota, json=PEDIDO)
    assert r.status_code == 409 and "senha de administrador" in r.get_json()["erro"]
    _no_setor(monkeypatch, SID.PCM)
    r = getattr(_pessoa_ms(tr), metodo)(rota, json=PEDIDO)
    assert r.status_code == 401 and "/os/login?next=" in r.get_json()["login"]
    r = getattr(com_o_fracttal(tr, _pessoa_ms(tr), "outra.pessoa@exemplo.test"), metodo)(rota, json=PEDIDO)
    assert r.status_code == 409 and "outra conta" in r.get_json()["erro"]
    _no_setor(monkeypatch, SID.PERFORMANCE)
    assert getattr(com_o_fracttal(tr, _pessoa_ms(tr)), metodo)(rota, json=PEDIDO).status_code == 403
    _no_setor(monkeypatch, SID.PCM)
    r = getattr(com_o_fracttal(tr, _pessoa_ms(tr)), metodo)(rota, json=PEDIDO, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert falso.transferencias == []
