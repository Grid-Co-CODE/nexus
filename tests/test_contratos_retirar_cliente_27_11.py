"""Comando > Contratos, 27/11/2026: tirar um cliente dos contratos (Levi: "TIRA SAL ENERGIA DOS CONTRATOS!").

Só o administrador, com o motivo e a prova; o cliente, os contratos, as regras e as obrigações saem da tela e ficam no
histórico. Tudo inventado (o repositório é público)."""
from test_contratos_editavel_18_11 import _como, _editar, carga  # noqa: F401 — a fixture da carga inicial


def test_o_administrador_tira_o_cliente_com_motivo_e_prova(carga, cliente):  # noqa: F811
    adm = _como(cliente, "admin@gridco.com.br", admin=True)
    d = adm.get("/t/comando/contratos/dados.json").get_json()
    beta = next(c for c in d["contratos"] if c["cliente"] == "Beta GD")
    base = dict(item_tipo="cliente", item_id=beta["id"], evento="retirada", cliente="Beta GD", valores={})
    # quem não é administrador não tira, nem o gestor do contrato
    st, r = _editar(_como(cliente, "gestora@gridco.com.br"), **base, motivo="Não é mais cliente", prova_texto="E-mail da diretoria")
    assert st == 400 and "administrador" in r["erro"]
    adm = _como(cliente, "admin@gridco.com.br", admin=True)              # o mesmo cliente de teste: a sessão volta ao admin
    assert _editar(adm, **base, motivo="", prova_texto="")[0] == 400                    # sem motivo nem prova, nada grava
    st, r = _editar(adm, **base, motivo="Não é mais cliente", prova_texto="E-mail da diretoria de 27/11")
    assert st == 200 and r["ok"], r
    d = adm.get("/t/comando/contratos/dados.json").get_json()
    assert "Beta GD" not in [c["cliente"] for c in d["contratos"]] and "Beta GD" not in d["fichas"]
    assert not [o for o in d["obrigacoes"] if o["cliente"] == "Beta GD"]
    assert all("Beta GD" not in a["por_cliente"] for t in d["quem_cuida"]["temas"] for a in t["atividades"])
    # fica no histórico
    h = adm.get("/t/comando/contratos/historico.json", query_string={"cliente": "Beta GD"}).get_json()["historico"]
    assert any(x.get("evento") == "retirada" for x in h)
    assert adm.get("/t/comando/contratos/indicadores.json", query_string={"cliente": "Beta GD"}).status_code == 404


def test_a_tela_tem_o_botao_de_tirar_o_cliente(cliente):
    r = cliente.get("/static/contratos.js")
    js = r.get_data(as_text=True)
    r.close()
    assert '(tipo === "cliente" && R.admin)' in js and "Tirar o cliente dos contratos" in js
