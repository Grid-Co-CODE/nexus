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


def test_o_pdf_embute_a_foto_como_veio_sem_decodificar_de_novo():
    """Raio-X das 09:56 de 20/10/2026: o PDF de uma OS ~2 min no servidor, em `gerar`. O reportlab decodificava cada
    foto já reduzida em RGB só para dar nome a ela (1000 x 750 = 2,25 MB por foto, guardados até o fim): no PC, com 200
    fotos, +1 GB de memória e 64% do `gerar`. O JPEG do `reduzir` vai ao PDF como veio, sem passar pelo RGB."""
    import tracemalloc
    pypdf = pytest.importorskip("pypdf")
    m = os_pdf.modelo(DET, recursos=RECURSOS, anexos_sub=SUBS, anexos_os=OSS)
    os_pdf.gerar(m)                                                        # o reportlab e as fontes já carregados
    jpegs = [_jpeg(cor=(20 * i, 120, 200 - 10 * i), tam=(1000, 750)) for i in range(12)]
    m["fotos"] = [{"legenda": "foto %d" % i, "de": "Foto da placa", "item": {}} for i in range(13)]
    fotos = [os_pdf.reduzir(j) for j in jpegs + jpegs[:1]]                # a 13ª repete a 1ª (2 subtarefas)
    assert [f[0] for f in fotos] == jpegs + jpegs[:1]                      # já cabem: passam como vieram
    tracemalloc.start()
    try:
        pdf = os_pdf.gerar(m, fotos=fotos)
        pico = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert pico < 12 * 2**20, "%.0f MB: as fotos decodificadas (2,25 MB cada) na memória" % (pico / 2**20)
    # o MESMO PDF: cada foto dentro dele é o JPEG que o `reduzir` entregou, byte a byte (DCTDecode, sem recodificar),
    # e a repetida vai uma vez só, como quando o reportlab as comparava pelo RGB
    ler = pypdf.PdfReader(io.BytesIO(pdf))
    refs = {x.idnum: x.get_object() for p in ler.pages for x in p["/Resources"].get("/XObject", {}).values()}
    assert all(x["/Filter"] in ("/DCTDecode", ["/DCTDecode"]) for x in refs.values())
    assert sorted(x.get_data() for x in refs.values()) == sorted(jpegs)


def test_texto_que_a_helvetica_nao_tem_nao_vira_quadrado():
    assert os_pdf._texto("Painel ok \U0001F600 <b>") == "Painel ok  &lt;b&gt;"
    assert os_pdf._seguro("Usina São João – CO₂") == "Usina São João – CO2"


# ── a cópia reduzida guardada: a mesma foto noutro PDF não é reduzida de novo (20/10/2026) ───────────────────────────
def _contar_reducoes(monkeypatch) -> list:
    """Cada `reduzir` de verdade que acontecer, contado (a foto continua sendo reduzida)."""
    feitas, reduzir = [], os_pdf.reduzir

    def contando(dados, *a, **k):
        feitas.append(len(dados))
        return reduzir(dados, *a, **k)
    monkeypatch.setattr(os_pdf, "reduzir", contando)
    return feitas


def test_a_foto_reduzida_fica_guardada_pelo_conteudo_da_original(monkeypatch, tmp_path):
    """Levi, 20/10/2026, sobre guardar a cópia de cada foto: "se a saída for óbvia, faça". A chave é o conteúdo da foto
    original, e não o caminho no S3: no Fracttal, outro arquivo com o mesmo nome na mesma OS apaga o primeiro (README do
    OS Creator), e o caminho guardado voltaria com a foto errada num PDF de garantia."""
    feitas, pasta = _contar_reducoes(monkeypatch), str(tmp_path)
    a, b = _jpeg(cor=(200, 30, 30)), _jpeg(cor=(30, 200, 30))
    ra = os_pdf.reduzir_guardada(a, pasta)
    assert ra[1] == (1000, 750) and len(feitas) == 1 and len(list(tmp_path.iterdir())) == 1
    assert os_pdf.reduzir_guardada(a, pasta) == ra and len(feitas) == 1          # a mesma foto: da cópia
    rb = os_pdf.reduzir_guardada(b, pasta)
    assert len(feitas) == 2 and rb[0] != ra[0] and len(list(tmp_path.iterdir())) == 2    # outra foto: outra cópia
    assert os_pdf.reduzir_guardada(a, pasta, px=500)[1] == (500, 375)            # outro tamanho: outra cópia
    pequena = _jpeg(tam=(800, 600))                                              # já cabe: passa como veio, e não há
    assert os_pdf.reduzir_guardada(pequena, pasta) == (pequena, (800, 600))      # o que poupar guardando
    assert len(list(tmp_path.iterdir())) == 3


class _Morreu(BaseException):
    """O processo morto no meio da gravação (o reinício do deploy): nenhum `except` roda."""


def test_a_copia_so_aparece_no_lugar_inteira(monkeypatch, tmp_path):
    """O servidor reinicia a cada push: uma gravação cortada no meio com o nome da cópia faria todo PDF com aquela foto
    sair com o JPEG pela metade. Grava num nome provisório e troca de uma vez."""
    import os
    feitas, troca = _contar_reducoes(monkeypatch), os.replace

    def disco_cheio(*a, **k):
        raise OSError("disco cheio")
    monkeypatch.setattr(os, "replace", disco_cheio)                    # sem conseguir gravar: a foto sai, nada fica
    assert os_pdf.reduzir_guardada(_jpeg(), str(tmp_path))[1] == (1000, 750) and list(tmp_path.iterdir()) == []

    def morre(*a, **k):
        raise _Morreu()
    monkeypatch.setattr(os, "replace", morre)                          # morto antes da troca: só o provisório fica
    with pytest.raises(_Morreu):
        os_pdf.reduzir_guardada(_jpeg(), str(tmp_path))
    assert [p.name for p in tmp_path.iterdir() if not p.name.endswith(".parcial")] == []
    monkeypatch.setattr(os, "replace", troca)
    assert os_pdf.reduzir_guardada(_jpeg(), str(tmp_path))[1] == (1000, 750) and len(feitas) == 3   # reduz de novo


def test_a_varrida_tira_as_copias_sem_uso_e_segura_o_teto(monkeypatch, tmp_path):
    """Cópia sem uso há GUARDADAS_DIAS sai (usar de novo conta como uso); passando de GUARDADAS_TETO, saem as mais
    antigas primeiro."""
    import os
    import time
    pasta, agora = str(tmp_path), time.time()
    fotos = {k: _jpeg(cor=c) for k, c in (("a", (250, 0, 0)), ("b", (0, 250, 0)), ("c", (0, 0, 250)))}
    reduzidas = {k: os_pdf.reduzir_guardada(f, pasta)[0] for k, f in fotos.items()}

    def copia_de(k):
        return next(p for p in tmp_path.iterdir() if p.read_bytes() == reduzidas[k])
    velho = agora - (os_pdf.GUARDADAS_DIAS + 1) * 86400
    for i, k in enumerate("abc"):
        os.utime(copia_de(k), (velho + i, velho + i))                    # as três sem uso há 31 dias
    os_pdf.reduzir_guardada(fotos["b"], pasta)                          # a b é usada hoje
    os.utime(copia_de("c"), (agora - 60, agora - 60))                   # a c foi feita há 1 minuto
    os_pdf.varrer_guardadas(pasta, agora)
    assert {p.read_bytes() for p in tmp_path.iterdir()} == {reduzidas["b"], reduzidas["c"]}
    monkeypatch.setattr(os_pdf, "GUARDADAS_TETO", len(reduzidas["b"]) + len(reduzidas["c"]) - 1)
    os_pdf.varrer_guardadas(pasta, agora)                               # passou do teto: sai a mais antiga (a c)
    assert {p.read_bytes() for p in tmp_path.iterdir()} == {reduzidas["b"]}


# ── a rota e a tela ──────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def cli(monkeypatch, tmp_path):
    with rotas._MEMO_LOCK:
        rotas._MEMO.clear()
    monkeypatch.setattr(api, "_data_dir", lambda: str(tmp_path))      # as cópias das fotos do PDF, fora do %APPDATA%
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


def test_o_segundo_pdf_da_mesma_os_nao_reduz_as_fotos_de_novo(cli, monkeypatch, tmp_path):
    """A rota guarda a cópia reduzida de cada foto (na pasta de dados do clone) e varre as sem uso a cada PDF."""
    import os
    import time
    pedidos = _fracttal_da_os(monkeypatch, foto=_jpeg())
    feitas = _contar_reducoes(monkeypatch)
    antiga = tmp_path / "os_pdf_fotos" / "antiga.jpg"                   # uma cópia sem uso há 40 dias
    antiga.parent.mkdir()
    antiga.write_bytes(b"x")
    os.utime(antiga, (time.time() - 40 * 86400,) * 2)
    j1 = cli.post("/os/api/os/pdf", json={"folio": "9102", "wid": "9202"}).get_json()
    n1 = len(feitas)
    j2 = cli.post("/os/api/os/pdf", json={"folio": "9102", "wid": "9202"}).get_json()
    assert (j1["fotos"], j2["fotos"]) == (2, 2) and n1 >= 1 and len(feitas) == n1     # a 2ª vez, só da cópia
    assert pedidos["fotos"] == 4 and not antiga.exists()               # as fotos ainda vêm do Fracttal


def test_os_que_nao_existe(cli, monkeypatch):
    _fracttal_da_os(monkeypatch, foto=_jpeg())
    r = cli.post("/os/api/os/pdf", json={"folio": "777"})
    assert r.status_code == 404 and r.get_json()["erro"] == "Não achei a OS 777 no Fracttal."
    assert cli.post("/os/api/os/pdf", json={}).status_code == 400
