"""Comando > Contratos editável, com histórico (18/11/2026). Levi: "Tire essas opções de subir arquivos [...] Eu quero que
essas informações sejam editáveis [...] Só gestores de contrato ou administradores podem editar, e tudo com histórico.
Nesse histórico deve ter quem mudou, o que mudou, quando mudou, o motivo porque mudou, anexar alguma coisa [...]"; e
"deixar muita informação em cima [...] Arrume isso". Escolhas dele: o anexo é obrigatório (arquivo ou texto colado), o
administrador liga o gestor à pessoa, tudo é editável, e a tela se chama Contratos.

Banco falso (tests/pg_falso.py); a carga inicial é a planilha inventada de test_contratos_controle e uma ficha inventada
(o repositório é público: nada real aqui)."""
import io
import json

import pytest
from pg_falso import ApiPGFalsa

from nexus.cadastro.cifra import gerar_chave
from nexus.cadastro.ligacao_campo import codigo_da_pessoa
from nexus.contratos import controle as K
from nexus.contratos import edicao as E
from nexus.contratos import fichas as F
from nexus.torres.comando import contratos_tela as CT

from test_contratos_controle import _planilha

HMAC = "hmac-teste"
FICHA = {"cliente": "SOLAR ALFA", "documentos": [{"arquivo": "contrato.pdf", "tipo": "contrato", "assinado": True}],
         "contratos": [{"id": "ALFA-1", "vigencia": {"fim": "2027-02-24"}, "valor": {"mensal": 1000.0},
                        "regras": [{"categoria": "SLA", "nome": "Chegada", "vigente": "Até 4 h", "ref": {"pagina": 9}}]},
                       {"id": "ALFA-2", "vigencia": {"fim": "2027-05-01"}, "valor": {"mensal": 500.0},
                        "regras": [{"categoria": "SLA", "nome": "Chegada", "vigente": "Até 4 h", "ref": {"pagina": 9}}]}]}


@pytest.fixture
def carga(app, tmp_path, monkeypatch):
    """A carga inicial na pasta de dados (a planilha e as fichas, como o servidor tem desde 16 e 18/11), o banco falso e
    as chaves; as pessoas que podem ser gestoras: a "Pessoa Um" da planilha é a gestora@ (gestora da Beta GD)."""
    pasta = tmp_path / "contratos"
    pasta.mkdir()
    (pasta / K.ARQUIVO).write_text(json.dumps(dict(K.ler_planilha(_planilha()), importado_em="2026-11-16T23:12")), encoding="utf-8")
    (pasta / F.ARQUIVO).write_text(json.dumps({"importado_em": "2026-11-18T00:00", "fichas": [FICHA]}), encoding="utf-8")
    api = ApiPGFalsa()
    app.config.update(NEXUS_DADOS=str(tmp_path), GRIDCO_DB_API="http://pg.falso", NEXUS_CHAVE_CADASTRO=gerar_chave(),
                      NEXUS_PESSOA_HMAC=HMAC, GRIDCO_SQL_TOKEN="tk", NEXUS_ADMINS="admin@gridco.com.br")
    app.extensions["nexus_dados_sessao"] = api
    pessoas = [{"hmac": codigo_da_pessoa(HMAC, "gestora@gridco.com.br"), "nome": "Pessoa Um"},
               {"hmac": codigo_da_pessoa(HMAC, "outra@gridco.com.br"), "nome": "Pessoa Cinco"}]
    monkeypatch.setattr(CT, "_pessoas", lambda: pessoas)
    with app.app_context():
        yield api
    app.extensions.pop("nexus_dados_sessao", None)


def _como(cli, email, admin=False):
    with cli.session_transaction() as s:
        s["logado"], s["admin"], s["usuario"] = True, admin, {"email": email, "nome": email.split("@")[0].title()}
    return cli


def _editar(cli, **f):
    ids = f.pop("item_id", [])
    arquivos = f.pop("provas", [])
    dados = {k: (json.dumps(v) if k == "valores" else v) for k, v in f.items()}
    dados["item_id"] = ids if isinstance(ids, list) else [ids]
    if arquivos:
        dados["provas"] = arquivos
    r = cli.post("/t/comando/contratos/editar", data=dados, content_type="multipart/form-data",
                 headers={"X-Nexus-Parte": "1", "Accept": "application/json"})
    return r.status_code, r.get_json()


def test_a_tela_nao_tem_mais_importacao_e_o_endereco_antigo_leva_ao_novo(carga, logado):
    html = logado.get("/t/comando/contratos").get_data(as_text=True)
    assert 'id="ctr-main"' in html and "contratos.js" in html
    assert 'type="file"' not in html and "importar" not in html.lower()
    assert "previa-moldura" not in html and "Dados <b>reais</b>" not in html          # o cabeçalho dobrado saiu
    r = logado.get("/t/comando/visao-do-contrato?x=1")
    assert r.status_code == 308 and r.headers["Location"].endswith("/t/comando/contratos?x=1")
    assert logado.post("/t/comando/visao-do-contrato/importar").status_code in (308, 405)
    assert logado.get("/static/previa/visao-do-contrato.html").status_code == 404


def test_a_carga_tem_ids_fixos(carga):
    plan = K.ler_planilha(_planilha())
    a, b = E.carga(plan, {"fichas": [FICHA]}), E.carga(plan, {"fichas": [FICHA]})
    assert a["itens"].keys() == b["itens"].keys() and all(a["itens"][t].keys() == b["itens"][t].keys() for t in a["itens"])
    assert len(a["itens"]["regra"]) == 2 and len(a["itens"]["contrato"]) == 2 and len(a["itens"]["cliente"]) == 3


def test_o_administrador_edita_com_motivo_e_prova_e_fica_no_historico(carga, cliente):
    adm = _como(cliente, "admin@gridco.com.br", admin=True)
    d = adm.get("/t/comando/contratos/dados.json").get_json()
    beta = next(c for c in d["contratos"] if c["cliente"] == "Beta GD")
    assert d["admin"] and beta["pode_editar"]
    assert (beta["gestor"], beta["gestor_como"]) == ("Pessoa Um", "pelo nome")
    base = dict(item_tipo="cliente", item_id=beta["id"], evento="alteracao", cliente="Beta GD", valores={"aviso_dias": "60"})
    # sem motivo, sem prova, nada mudou: nada grava
    assert _editar(adm, **base, motivo="", prova_texto="o e-mail do cliente")[0] == 400
    st, r = _editar(adm, **base, motivo="Combinado com o cliente", prova_texto="")
    assert st == 400 and "prova" in r["erro"]
    st, r = _editar(adm, **base, motivo="Combinado com o cliente", prova_texto="De: cliente. Confirmamos 60 dias de aviso.")
    assert st == 200 and r["mudou"] == 1
    assert _editar(adm, **base, motivo="De novo igual", prova_texto="o mesmo texto de prova")[0] == 400
    d = adm.get("/t/comando/contratos/dados.json").get_json()
    beta = next(c for c in d["contratos"] if c["cliente"] == "Beta GD")
    # a renovação é refeita com o dado editado: fim 23/06/2027 menos 60 dias
    assert beta["aviso_dias"] == 60 and beta["avisar_ate"] == "2027-04-24" and "aviso_dias" in beta["_editado"]
    h = adm.get("/t/comando/contratos/historico.json", query_string={"cliente": "Beta GD"}).get_json()["historico"]
    assert [x["evento"] for x in h] == ["alteracao", "carga"]
    assert h[0]["quem"] == "Admin" and h[0]["motivo"] == "Combinado com o cliente" and "60 dias" in h[0]["prova_texto"]
    assert h[0]["campos"] == [{"campo": "Aviso prévio de renovação (dias)", "antes": None, "depois": 60}]
    # no banco, o conteúdo vai cifrado: nem o motivo nem o nome aparecem em claro
    bruto = json.dumps(carga.workbooks, default=str)
    assert "Combinado com o cliente" not in bruto and "admin@gridco" not in bruto and "Beta GD" not in bruto


def test_so_o_gestor_do_contrato_e_o_administrador_editam(carga, cliente):
    adm = _como(cliente, "admin@gridco.com.br", admin=True)
    d = adm.get("/t/comando/contratos/dados.json").get_json()
    por = {c["cliente"]: c for c in d["contratos"]}
    prova = dict(motivo="Ajuste combinado", prova_texto="Ata da reunião com o cliente.")
    gest = _como(cliente, "gestora@gridco.com.br")
    d = gest.get("/t/comando/contratos/dados.json").get_json()
    pode = {c["cliente"]: c["pode_editar"] for c in d["contratos"]}
    # a Pessoa Um é gestora da Beta GD (o supervisor único) e não da Solar Alfa (a linha geral é da Pessoa Três)
    assert pode["Beta GD"] and not pode["Solar Alfa"] and d["pessoas"] == []
    assert _editar(gest, item_tipo="cliente", item_id=por["Beta GD"]["id"], evento="alteracao", cliente="Beta GD",
                   valores={"sla": "Até 6 h"}, **prova)[0] == 200
    st, r = _editar(gest, item_tipo="cliente", item_id=por["Solar Alfa"]["id"], evento="alteracao", cliente="Solar Alfa",
                    valores={"sla": "Até 6 h"}, **prova)
    assert st == 400 and "gestor" in r["erro"]
    # trocar o gestor e mexer nas metas é só do administrador
    outra = codigo_da_pessoa(HMAC, "outra@gridco.com.br")
    st, r = _editar(gest, item_tipo="cliente", item_id=por["Beta GD"]["id"], evento="alteracao", cliente="Beta GD",
                    valores={"gestor_hmac": outra}, **prova)
    assert st == 400 and "administrador" in r["erro"]
    assert _editar(gest, item_tipo="parametros", item_id="p0", evento="alteracao", valores={"meta_entregaveis": "0.9"}, **prova)[0] == 400
    # quem não é gestor de nada não edita
    fora = _como(cliente, "outra@gridco.com.br")
    assert _editar(fora, item_tipo="cliente", item_id=por["Beta GD"]["id"], evento="alteracao", cliente="Beta GD",
                   valores={"sla": "x"}, **prova)[0] == 400
    # o administrador troca o gestor: a Pessoa Cinco passa a editar a Beta GD, e a Pessoa Um deixa de editar
    adm = _como(cliente, "admin@gridco.com.br", admin=True)
    assert _editar(adm, item_tipo="cliente", item_id=por["Beta GD"]["id"], evento="alteracao", cliente="Beta GD",
                   valores={"gestor_hmac": outra}, **prova)[0] == 200
    h = adm.get("/t/comando/contratos/historico.json", query_string={"cliente": "Beta GD"}).get_json()["historico"]
    assert h[0]["campos"] == [{"campo": "Gestor do contrato", "antes": "Pessoa Um", "depois": "Pessoa Cinco"}]
    assert next(c for c in _como(cliente, "outra@gridco.com.br").get("/t/comando/contratos/dados.json").get_json()["contratos"]
                if c["cliente"] == "Beta GD")["pode_editar"]


def test_a_regra_igual_em_varios_contratos_muda_de_uma_vez_com_o_anexo(carga, cliente):
    adm = _como(cliente, "admin@gridco.com.br", admin=True)
    d = adm.get("/t/comando/contratos/dados.json").get_json()
    ids = [r["_id"] for k in d["fichas"]["Solar Alfa"]["contratos"] for r in k["regras"]]
    assert len(ids) == 2
    pdf = (io.BytesIO(b"%PDF-1.4\n%prova\n"), "aditivo.pdf")
    st, r = _editar(adm, item_tipo="regra", item_id=ids, evento="alteracao", cliente="Solar Alfa",
                    valores={"vigente": "Até 6 h"}, motivo="O 1º aditivo amplia o prazo", prova_texto="", provas=[pdf])
    assert st == 200 and r["mudou"] == 2
    d = adm.get("/t/comando/contratos/dados.json").get_json()
    assert {r["vigente"] for k in d["fichas"]["Solar Alfa"]["contratos"] for r in k["regras"]} == {"Até 6 h"}
    h = adm.get("/t/comando/contratos/historico.json", query_string={"cliente": "Solar Alfa"}).get_json()["historico"]
    assert len(h[0]["itens"]) == 2 and h[0]["anexos"][0]["nome"] == "aditivo.pdf"      # uma entrada para a mudança
    r = adm.get(h[0]["anexos"][0]["url"])
    assert r.status_code == 200 and r.data.startswith(b"%PDF") and r.mimetype == "application/pdf"
    # o arquivo que não é o que diz não grava
    falso = (io.BytesIO(b"MZ isto nao e pdf"), "aditivo.pdf")
    st, r = _editar(adm, item_tipo="regra", item_id=ids[:1], evento="alteracao", cliente="Solar Alfa",
                    valores={"vigente": "Até 8 h"}, motivo="Outra mudança", prova_texto="", provas=[falso])
    assert st == 400 and "não bate" in r["erro"]


def test_incluir_e_retirar_ficam_no_historico(carga, cliente):
    adm = _como(cliente, "admin@gridco.com.br", admin=True)
    prova = dict(motivo="Pedido do cliente", prova_texto="E-mail do cliente com o pedido.")
    st, r = _editar(adm, item_tipo="obrigacao", evento="inclusao", cliente="Beta GD", **prova,
                    valores={"tipo": "Reajuste", "descricao": "Reajuste combinado", "status": "Não iniciado", "vencimento": "2026-12-01"})
    assert st == 200
    oid = r["item_ids"][0]
    d = adm.get("/t/comando/contratos/dados.json").get_json()
    assert any(o["_id"] == oid and o["tom"] == "neutro" for o in d["obrigacoes"])
    # incluir sem o obrigatório não grava
    st, r = _editar(adm, item_tipo="obrigacao", evento="inclusao", cliente="Beta GD", valores={"descricao": "x"}, **prova)
    assert st == 400 and "Preencha" in r["erro"]
    assert _editar(adm, item_tipo="obrigacao", item_id=oid, evento="retirada", cliente="Beta GD", valores={}, **prova)[0] == 200
    d = adm.get("/t/comando/contratos/dados.json").get_json()
    assert not any(o["_id"] == oid for o in d["obrigacoes"])
    h = adm.get("/t/comando/contratos/historico.json", query_string={"cliente": "Beta GD"}).get_json()["historico"]
    assert [x["evento"] for x in h] == ["retirada", "inclusao", "carga"]


def test_o_catalogo_registra_o_livro_antes_da_primeira_gravacao():
    from nexus.dados import catalogo
    assert catalogo.POR_ID["edicao_contrato"].fontes == (f"{E.LIVRO} · {E.ABA}",)
    livro = next(l for l in catalogo.LIVROS if l.nome == E.LIVRO)
    assert livro.so_cresce


def test_a_pagina_pede_motivo_e_prova_e_mostra_o_lapis_so_para_quem_edita(cliente):
    r = cliente.get("/static/contratos.js")
    js = r.get_data(as_text=True)
    r.close()
    assert "Motivo da mudança" in js and "(obrigatório: o arquivo ou o texto colado)" in js
    assert 'if (tipo === "parametros" ? !R.admin : !pode(c)) return "";' in js            # o lápis
    assert '["historico", "Histórico"]' in js and "Aplicar a" in js
    assert "nexusPedir" in js and "/t/comando/contratos/" in js
