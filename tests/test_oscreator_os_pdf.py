"""O PDF da OS (OS Creator Web), com o que o Fracttal junta para imprimir o dele. Levi, 19/10/2026, em Nexus > Chamados >
Garantias: "Gostaria de incluir a opção de baixar o mesmo PDF que o fractall gera" e "inclua a opção de baixar na cadeia
de chamado, uma seta de download!".

Fracttal FALSO (nada vai à rede; as fotos são geradas aqui). Nomes e números de mentira: o repositório é público."""
import io
import sys
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
pytest.importorskip("reportlab")
Image = pytest.importorskip("PIL.Image")
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import chamados_obs_store as obs_store  # noqa: E402
from os_web import criar_app, os_pdf, rotas  # noqa: E402

WEB = Path(ponte.RAIZ_CLONE) / "os_web"
JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
WID, FOLIO = 9201, 9103
NOTA = """[CHAMADO] Acompanhamento — STI · Estrutura Trackers
OS de campo: 9101 · Inspeção: 9102 · Ativo: TST100-ETKR1.100
Data da falha: 10/09/2026 13:28 · Menos de 7 dias: Sim"""


def _jpeg(cor=(30, 120, 200), tam=(1600, 1200)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", tam, cor).save(b, "JPEG", quality=80)
    return b.getvalue()


DET = {"folio": 9102, "descricao": "[Inversor 1.1] - Inspeção de chamado", "tipo": "Corretiva",
       "classif": "Inspeção / Garantia", "criticidade": "Alto", "event_date": "2026-10-01T12:00:00",
       "data_fim": "2026-10-01T15:30:00", "responsavel": "Técnico Teste", "criado_por": "Pessoa Teste",
       "solicitacao": "", "os_pai": "9101", "notas": "Inversor desligado.\nFoto da placa enviada.", "status_id": 3,
       "etiquetas": [{"id": 1, "nome": "CHAMADOS", "cor": "#fff"}], "code": "TST100-INVR1.1", "ativo": "Inversor 1.1",
       "cancel_motivo": "", "cancel_nota": "",
       "tarefas": [{"id": 11, "titulo": "Inspeção do inversor", "ativo": "Inversor 1.1", "tipo": "Corretiva",
                    "programada": "2026-10-01T11:00:00", "inicio": "2026-10-01T12:00:00", "fim": "2026-10-01T15:30:00",
                    "nota": "Levar a câmera térmica"},
                   {"id": 12, "titulo": "Registro do chamado", "ativo": "Inversor 1.1", "tipo": "Administrativa",
                    "programada": None, "inicio": None, "fim": None, "nota": ""}],
       "subtarefas": [{"descricao": "Foto da placa", "feito": True, "tipo": "Texto", "resposta": "ok", "id_tarefa": 11},
                      {"descricao": "Código do erro", "feito": True, "tipo": "Texto", "resposta": "E-021",
                       "id_tarefa": 11},
                      {"descricao": "Nº do ticket", "feito": False, "tipo": "Texto", "resposta": "", "id_tarefa": 12}]}
SUBS = [{"url": "https://s3.exemplo.invalid/a.jpg", "value": ".ot/a.jpg", "nome": "a.jpg", "descricao": "placa",
         "subtarefa": "Foto da placa", "is_image": True, "is_text": False},
        {"url": "https://s3.exemplo.invalid/b.jpg", "value": ".ot/b.jpg", "nome": "b.jpg", "descricao": "",
         "subtarefa": "Foto da placa", "is_image": True, "is_text": False},
        {"url": "", "value": "", "nome": "nota", "descricao": "Erro some depois de religar", "subtarefa": "Código do erro",
         "is_image": False, "is_text": True}]
OSS = [{"value": ".ot/laudo.pdf", "nome": "laudo.pdf", "user": "Pessoa Teste", "url": "https://s3.exemplo.invalid/l.pdf",
        "is_image": False, "is_text": False, "desc": ""},
       {"value": ".ot/a.jpg", "nome": "a.jpg", "user": "Pessoa Teste", "url": "https://s3.exemplo.invalid/a.jpg",
        "is_image": True, "is_text": False, "desc": ""}]                  # a mesma foto da subtarefa: não repete
RECURSOS = [{"tipo": "Peça / inventário", "descricao": "Fusível 15 A { FUS-15 }", "qtd": 2.5, "usado": 0,
             "unidade": "un", "origem": "Almoxarifado Teste", "custo_unit": 0, "custo_total": "0.00",
             "nota": "Lançado pelo App de Campo", "id_tarefa": 11}]


# ── os recursos do Fracttal ─────────────────────────────────────────────────────────────────────────────────────
def test_os_recursos_vem_do_pedido_do_print_do_fracttal(monkeypatch):
    pedidos = []

    def rpc(metodo, params, timeout=45):
        pedidos.append((metodo, params))
        return {"data": [{"type": 1, "type_description": "INVENTORY", "description": "Fusível 15 A { FUS-15 }",
                          "qty": 2.5, "real_qty_used": 0, "units_description": "un",
                          "source_description": "Almoxarifado Teste", "unit_cost": 0, "total_cost": "0.00",
                          "note": "Lançado pelo App de Campo", "id_work_orders_tasks": 11},
                         {"type_description": "HUMAN_RESOURCES", "description": "Técnico Teste", "qty": 3},
                         {"type_description": "", "description": ""}]}           # vazio: fora
    monkeypatch.setattr(api, "_rpc_call", rpc)
    r = api.get_os_recursos(WID)
    assert pedidos == [("tasks.work_orders_resources_all_list", {"id_work_order": WID})]   # o pedido do print da web
    assert [(x["tipo"], x["descricao"], x["qtd"], x["unidade"], x["origem"]) for x in r] == [
        ("Peça / inventário", "Fusível 15 A { FUS-15 }", 2.5, "un", "Almoxarifado Teste"),
        ("Mão de obra", "Técnico Teste", 3, "", "")]


# ── o conteúdo do PDF ───────────────────────────────────────────────────────────────────────────────────────────
def test_o_modelo_tem_o_que_o_fracttal_junta():
    m = os_pdf.modelo(DET, recursos=RECURSOS, anexos_sub=SUBS, anexos_os=OSS,
                      local=("Cliente Teste", "Usina Teste 1", "Inversor"))
    assert (m["folio"], m["status"], m["tom_status"]) == ("9102", "Concluída", "ok")
    dados = dict(m["dados"])
    assert dados["Ativo"] == "Inversor 1.1" and dados["Cliente"] == "Cliente Teste" and dados["Usina"] == "Usina Teste 1"
    assert dados["Responsável"] == "Técnico Teste" and dados["Data do evento"] == "01/10/2026 09:00"   # Brasília
    assert dados["Data fim"] == "01/10/2026 12:30" and dados["Duração total"] == "3h 30m"
    assert dados["OS pai"] == "9101" and dados["Etiquetas"] == "CHAMADOS"
    assert "Solicitação" not in dados and "Motivo do cancelamento" not in dados        # vazio não ocupa linha
    # as tarefas na ordem do card, cada uma com as subtarefas dela
    t1, t2 = m["tarefas"]
    assert (t1["n"], t1["titulo"], t1["situacao"], t1["duracao"], t1["nota"]) == (
        1, "Inspeção do inversor", "Finalizada", "3h 30m", "Levar a câmera térmica")
    assert [(s["descricao"], s["resposta"], s["feito"]) for s in t1["subtarefas"]] == [
        ("Foto da placa", "ok", True), ("Código do erro", "E-021", True)]
    assert (t2["titulo"], t2["situacao"], [s["resposta"] for s in t2["subtarefas"]]) == (
        "Registro do chamado", "Não iniciada", ["—"])
    # as fotos: as das subtarefas, com a subtarefa; a da OS que já é de subtarefa não repete
    assert [(f["de"], f["legenda"]) for f in m["fotos"]] == [("Foto da placa", "placa"), ("Foto da placa", "b.jpg")]
    assert m["documentos"] == [{"nome": "laudo.pdf", "de": "Pessoa Teste"}]
    assert m["notas_anexo"] == [{"texto": "Erro some depois de religar", "de": "Código do erro"}]
    assert m["observacoes"] == "Inversor desligado.\nFoto da placa enviada."
    assert m["recursos"][0]["descricao"] == "Fusível 15 A { FUS-15 }"


def test_os_de_uma_tarefa_so_e_recurso_que_nao_veio():
    d = dict(DET, tarefas=DET["tarefas"][:1], subtarefas=DET["subtarefas"][:2], status_id=1)
    m = os_pdf.modelo(d, recursos=None)
    assert [t["titulo"] for t in m["tarefas"]] == ["Inspeção do inversor"] and len(m["tarefas"][0]["subtarefas"]) == 2
    assert m["recursos"] is None and m["status"] == "Em Processo" and m["fotos"] == []
    assert [os_pdf.numero(x) for x in (3, 2.5, "1,25", "", "abc")] == ["3", "2,5", "1,25", "—", "abc"]
    assert [os_pdf.dinheiro(x) for x in (0, "0.00", 1234.5, None)] == ["", "", "R$ 1.234,50", ""]


def test_o_pdf_sai_com_as_fotos_dentro():
    pypdf = pytest.importorskip("pypdf")
    m = os_pdf.modelo(DET, recursos=RECURSOS, anexos_sub=SUBS, anexos_os=OSS)
    fotos = [os_pdf.reduzir(_jpeg()), None]                                # a 2ª não veio do Fracttal
    assert fotos[0][1] == (1000, 750)                                      # reduzida a FOTO_PX no lado maior
    pdf = os_pdf.gerar(m, fotos=fotos, gerado_em="19/10/2026 14:00", quem="Analista Teste",
                       logo=str(Path(ponte.RAIZ_CLONE) / "assets" / "grid-logo.png"))
    assert pdf.startswith(b"%PDF")
    ler = pypdf.PdfReader(io.BytesIO(pdf))
    texto = " ".join(" ".join(p.extract_text().split()) for p in ler.pages)
    for trecho in ("OS 9102", "Concluída", "Ordem de serviço 9102", "Responsável",
                   "Tarefa 1 · Inspeção do inversor", "Tarefa 2 · Registro do chamado", "Código do erro", "E-021",
                   "Fusível 15 A", "Almoxarifado Teste", "2,5", "Inversor desligado.", "Fotos 1 de 2",
                   "A foto não veio do Fracttal", "laudo.pdf", "Erro some depois de religar",
                   "gerado em 19/10/2026 14:00 por Analista Teste", "Página 1"):
        assert trecho in texto, trecho
    fotos_no_pdf = sum(len(p.images) for p in ler.pages)
    assert fotos_no_pdf == len(ler.pages) + 1                              # o logo em cada página + a foto que veio


def test_texto_que_a_helvetica_nao_tem_nao_vira_quadrado():
    assert os_pdf._texto("Painel ok \U0001F600 <b>") == "Painel ok  &lt;b&gt;"
    assert os_pdf._seguro("Usina São João – CO₂") == "Usina São João – CO2"


# ── a rota e a tela ──────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def cli(monkeypatch):
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    monkeypatch.setattr(api, "_code_to_loc", lambda: {})
    monkeypatch.setattr(api, "list_chamados", lambda **k: [
        {"id": WID, "folio": str(FOLIO), "cliente": "Cliente Teste", "usina": "Usina Teste", "ativo": "Tracker 1.100",
         "tipo": "Estrutura Trackers", "tipo_tarefa": "Administrativa", "note": NOTA,
         "descricao": "[Tracker 1.100] - Acompanhamento de chamado STI", "status_id": 1,
         "status": api.WO_STATUS.get(1), "data": "2026-10-01T12:00:00", "data_fim": "",
         "atribuido_a": "Técnico Teste", "id_atribuido": 900002}])
    monkeypatch.setattr(api, "tickets_os3_em_massa", lambda ids: {i: "" for i in ids})
    monkeypatch.setattr(obs_store, "do_os", lambda folio: [])
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Analista Teste", "email": "teste@exemplo.invalid", "perfil": ""}
    yield c
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()


def test_a_cadeia_do_chamado_tem_a_seta_de_cada_os(cli, monkeypatch):
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: {"folio": FOLIO, "subtarefas": [], "notas": NOTA})
    h = cli.get("/os/chamados/acompanhamento/%d" % FOLIO).get_data(as_text=True)
    cadeia = h.split("data-pdf-caixa", 1)[1].split("</section>", 1)[0]
    assert 'data-os-pdf="9101" title="Baixar o PDF da OS 9101"' in cadeia                       # OS de campo
    assert 'data-os-pdf="9102" title="Baixar o PDF da OS 9102"' in cadeia                       # inspeção
    assert 'data-os-pdf="%d" data-wid="%d"' % (FOLIO, WID) in cadeia                            # este chamado
    assert '<div class="msg" data-pdf-msg hidden></div>' in cadeia
    js = (WEB / "static" / "os_acoes.js").read_text(encoding="utf-8")
    assert "closest('[data-os-pdf]')" in js and "'/os/api/os/pdf'" in js and "Montando o PDF da OS" in js
    css = (WEB / "static" / "chamados.css").read_text(encoding="utf-8")
    assert "grid-template-columns:24px 1fr auto 26px" in css and ".cad-pdf{" in css


def _fracttal_da_os(monkeypatch, foto=None):
    """O Fracttal falso do PDF: a OS 9102 pelo nº, o detalhe, os anexos, os recursos e as fotos."""
    pedidos = {"folio": [], "fotos": 0}

    def por_folio(folio):
        pedidos["folio"].append(str(folio))
        return 9202 if str(folio) == "9102" else None
    monkeypatch.setattr(api, "_wo_id_por_folio", por_folio)
    monkeypatch.setattr(api, "get_os_detalhes", lambda wid: dict(DET) if wid == 9202 else {})
    monkeypatch.setattr(api, "get_os_subtarefa_anexos", lambda wid: [dict(a) for a in SUBS])
    monkeypatch.setattr(api, "get_os_anexos", lambda wid: [dict(a) for a in OSS])
    monkeypatch.setattr(api, "get_os_recursos", lambda wid: list(RECURSOS))

    def baixar(url):
        pedidos["fotos"] += 1
        if foto is None:
            raise api.FracttalError("link vencido")
        return foto
    monkeypatch.setattr(api, "baixar_imagem", baixar)
    monkeypatch.setattr(api, "s3_get_url", lambda name: None)
    return pedidos


def test_a_rota_monta_o_pdf_pelo_numero_e_entrega_so_para_quem_pediu(cli, monkeypatch):
    pedidos = _fracttal_da_os(monkeypatch, foto=_jpeg())
    r = cli.post("/os/api/os/pdf", json={"folio": "9102"})
    j = r.get_json()
    assert r.status_code == 200 and j["ok"] and j["nome"] == "OS 9102.pdf" and (j["fotos"], j["falhas"]) == (2, 0)
    assert pedidos["folio"] == ["9102"] and pedidos["fotos"] == 2
    b = cli.get(j["url"])
    assert b.status_code == 200 and b.mimetype == "application/pdf" and b.data.startswith(b"%PDF")
    assert 'attachment; filename="OS 9102.pdf"' in b.headers["Content-Disposition"]
    # outra pessoa (outra sessão do Fracttal) com o link não baixa; e o link do .zip não entrega o PDF
    import base64
    outra = base64.urlsafe_b64encode(b'{"email":"outra@exemplo.invalid","exp":9999999999}').decode().rstrip("=")
    with cli.session_transaction() as s:
        s["jwt"] = "aaa.%s.sig" % outra
        s["conta"] = {"nome": "Outra Pessoa", "email": "outra@exemplo.invalid", "perfil": ""}
    r = cli.get(j["url"])
    assert r.status_code == 404 and "venceu" in r.get_json()["erro"]
    with cli.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Analista Teste", "email": "teste@exemplo.invalid", "perfil": ""}
    token = j["url"].rsplit("/", 1)[1]
    assert cli.get("/os/api/os/9202/anexos-zip/%s" % token).status_code == 404


def test_com_o_id_nao_busca_pelo_numero_e_foto_que_nao_vem_nao_derruba(cli, monkeypatch):
    pedidos = _fracttal_da_os(monkeypatch, foto=None)                     # o S3 recusa as duas fotos
    j = cli.post("/os/api/os/pdf", json={"folio": "9102", "wid": "9202"}).get_json()
    assert j["ok"] and (j["fotos"], j["falhas"]) == (0, 2) and pedidos["folio"] == []
    assert cli.get(j["url"]).data.startswith(b"%PDF")


def test_os_que_nao_existe(cli, monkeypatch):
    _fracttal_da_os(monkeypatch, foto=_jpeg())
    r = cli.post("/os/api/os/pdf", json={"folio": "777"})
    assert r.status_code == 404 and r.get_json()["erro"] == "Não achei a OS 777 no Fracttal."
    assert cli.post("/os/api/os/pdf", json={}).status_code == 400
