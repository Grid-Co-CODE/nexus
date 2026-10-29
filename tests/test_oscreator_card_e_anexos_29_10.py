"""O card da OS, a Zeladoria na Fila e os anexos da Nova solicitação (Levi, 29/10/2026).

- o card: "Ordem de serviço" sem a borda (a classe era a da caixa de subtarefa), sem "Abrir chamado" ("ele não servirá
  mais") e sem "Clonar esta OS", e com a seta de baixar o PDF da OS ao lado esquerdo da Solicitação;
- a Fila do PCM: "Não consegui aprovar a solicitação 4126. Falha ao criar as tarefas: ?: Tipo de tarefa desconhecido:
  Zeladoria" — o tipo vinha pelo NOME e só a lista fixa do código era lida; agora o catálogo vivo do Fracttal também;
- a Nova solicitação: "quero que seja possível adicionar anexos como PDFS e fotos. E quando o PCM gere uma OS pela fila
  de PCM com aquela solicitação o anexo vá junto!" — guardados no servidor até a aprovação (escolha do Levi), e na
  aprovação sobem na tarefa da OS pelo caminho dos anexos da Engenharia.

O Fracttal é de mentira e a rede está proibida. Nomes de mentira."""
import io
import json

import pytest

from test_oscreator_card_tarefas import WID, Fracttal, _card, _item, _tarefa  # noqa: F401
from test_oscreator_solic_pcm import LINHAS, WEB, api, cli, sw  # noqa: F401

from os_web import solic_anexos  # noqa: E402

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF"
JPG = b"\xff\xd8\xff\xe0" + b"0" * 64


# ── o card ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_card_sem_abrir_chamado_e_clonar_e_com_o_pdf(monkeypatch):
    monkeypatch.setattr(api, "_rpc_call", Fracttal([_tarefa(1)], [_item(1, 1), _item(1, 2)]).rpc)
    h = _card()
    assert '<div class="det-num-sub">Ordem de serviço</div>' in h and 'class="det-sub">Ordem de serviço' not in h
    assert "Abrir chamado" not in h and "Clonar esta OS" not in h
    topo = h[h.index('class="det-top"'):h.index("</header>")]
    assert topo.index('data-os-pdf="15900"') < topo.index("Solicitação")
    assert 'data-wid="%d"' % WID in topo and "data-pdf-caixa" in h and "data-pdf-msg" in h
    css = (WEB / "static" / "os.css").read_text(encoding="utf-8")
    assert ".det-num-sub{" in css and ".det-pdf{" in css


# ── a Zeladoria ─────────────────────────────────────────────────────────────────────────────────────────────────────
class _Pedido(Exception):
    pass


def test_o_tipo_que_a_lista_fixa_nao_tem_vem_do_catalogo_vivo(monkeypatch):
    monkeypatch.setattr(api, "_CLASSIF_CACHE", {})
    monkeypatch.setattr(api, "get_tipos_classif", lambda: {"tipos": [{"id": 77001, "description": "Zeladoria"}], "c1": [], "c2": []})
    assert api.tipo_main_ao_vivo("Zeladoria") == 77001 and api.tipo_main_ao_vivo("zeladoria ") == 77001
    assert api.tipo_main_ao_vivo("Não existe") is None
    enviado = []

    def post(url, headers=None, json=None, timeout=None):
        enviado.append(json)
        raise _Pedido()
    monkeypatch.setattr(api.requests, "post", post)
    monkeypatch.setattr(api, "_rpc_headers", lambda: {})          # o login de mentira
    with pytest.raises(_Pedido):
        api.create_os_rpc({"id": 5, "code": "TST-INV1", "description": "Inversor 1.1"}, "T", "Zeladoria", [])
    assert enviado[0][0]["params"]["id_task_type_main"] == 77001


def test_tipo_que_nao_existe_em_lugar_nenhum_segue_recusado(monkeypatch):
    monkeypatch.setattr(api, "_rpc_headers", lambda: {})
    monkeypatch.setattr(api, "_CLASSIF_CACHE", {})
    monkeypatch.setattr(api, "get_tipos_classif", lambda: {"tipos": [], "c1": [], "c2": []})
    with pytest.raises(api.FracttalError, match="Tipo de tarefa desconhecido"):
        api.create_os_rpc({"id": 5, "code": "TST-INV1"}, "T", "Inventado", [])


# ── os anexos da Nova solicitação ───────────────────────────────────────────────────────────────────────────────────
def test_guardar_listar_ler_e_apagar(tmp_path):
    solic_anexos.guardar(4126, [{"nome": "laudo.pdf", "bytes": PDF, "tamanho": len(PDF)}], raiz=tmp_path)
    assert solic_anexos.listar(4126, raiz=tmp_path) == [{"nome": "laudo.pdf", "tamanho": len(PDF)}]
    assert solic_anexos.ler(4126, "laudo.pdf", raiz=tmp_path) == PDF
    assert solic_anexos.ler(4126, "../../segredo", raiz=tmp_path) is None and solic_anexos.listar("x", raiz=tmp_path) == []
    solic_anexos.apagar(4126, ["laudo.pdf"], raiz=tmp_path)
    assert solic_anexos.listar(4126, raiz=tmp_path) == []


@pytest.fixture
def pasta(monkeypatch, tmp_path):
    monkeypatch.setattr(solic_anexos, "RAIZ", str(tmp_path))
    return tmp_path


def _criar(cli, monkeypatch, arquivos):
    monkeypatch.setattr(api, "_read_asset_cache", lambda: [])
    monkeypatch.setattr(api, "create_solicitacoes_bulk", lambda assets, desc, c1, **k: [
        {"code": a["code"], "ok": True, "id_code": 4126} for a in assets])
    dados = {"payload": json.dumps({"ativos": ["TST-INV11"], "descricao": "Troca", "classif1": 7})}
    dados["anexos"] = [(io.BytesIO(b), n) for n, b in arquivos]
    return cli.post("/os/api/solic/criar", data=dados, content_type="multipart/form-data")


def test_a_solicitacao_guarda_os_anexos_com_o_numero(cli, monkeypatch, pasta):
    r = _criar(cli, monkeypatch, [("laudo.pdf", PDF), ("foto.jpg", JPG)])
    assert r.status_code == 200, r.get_json()
    assert [a["nome"] for a in solic_anexos.listar(4126)] == ["foto.jpg", "laudo.pdf"]
    assert "2 anexo(s)" in r.get_json()["mensagem"]


def test_anexo_torto_nao_cria_a_solicitacao(cli, monkeypatch, pasta):
    r = _criar(cli, monkeypatch, [("virus.pdf", b"MZ\x90\x00 nada de pdf")])
    assert r.status_code == 400 and "Nenhuma solicitação foi criada" in r.get_json()["erro"]
    assert solic_anexos.listar(4126) == []


def test_ao_aprovar_os_anexos_vao_para_a_tarefa_da_os(cli, monkeypatch, pasta):
    solic_anexos.guardar(5001, [{"nome": "laudo.pdf", "bytes": PDF, "tamanho": len(PDF)}])
    subidos = []
    monkeypatch.setattr(api, "_ids_tarefas_da_os", lambda wid: [321])
    monkeypatch.setattr(api, "attach_imagem_os", lambda wid, tid, b, nome: subidos.append((wid, tid, b, nome)))
    d = cli.get("/os/solicitacao/fila").get_data(as_text=True)
    assert "laudo.pdf" in d                                                      # a ficha mostra o que vai junto
    r = cli.post("/os/api/solic/5001/aprovar", json={"id_responsible": 1, "responsavel": "Ana Teste Silva"})
    assert r.status_code == 200 and subidos == [(99, 321, PDF, "laudo.pdf")]
    assert "laudo.pdf" in r.get_json()["mensagem"] and solic_anexos.listar(5001) == []   # subiu: sai do servidor


def test_anexo_que_falha_na_aprovacao_fica_guardado(cli, monkeypatch, pasta):
    solic_anexos.guardar(5001, [{"nome": "laudo.pdf", "bytes": PDF, "tamanho": len(PDF)}])
    monkeypatch.setattr(api, "_ids_tarefas_da_os", lambda wid: [321])

    def falha(*a):
        raise api.FracttalError("S3 fora")
    monkeypatch.setattr(api, "attach_imagem_os", falha)
    r = cli.post("/os/api/solic/5001/aprovar", json={"id_responsible": 1, "responsavel": "Ana Teste Silva"})
    assert r.status_code == 200 and "NÃO subiu" in r.get_json()["mensagem"]
    assert [a["nome"] for a in solic_anexos.listar(5001)] == ["laudo.pdf"]


def test_o_historico_lista_os_anexos_guardados_e_baixa(cli, pasta):
    solic_anexos.guardar(5001, [{"nome": "laudo.pdf", "bytes": PDF, "tamanho": len(PDF)}])
    api_lista = cli.get("/os/api/solic/5001/anexos").get_json()["anexos"]
    guardado = [a for a in api_lista if a.get("guardado")][0]               # o fixture tem outro laudo.pdf, do Fracttal
    assert guardado["nome"] == "laudo.pdf"
    assert guardado["url"].startswith("/os/api/solic/5001/anexo-guardado?nome=")
    r = cli.get(guardado["url"])
    assert r.status_code == 200 and r.data == PDF
    assert cli.get("/os/api/solic/5001/anexo-guardado?nome=..%2F..%2Fx").status_code == 404


def test_a_tela_da_nova_solicitacao_tem_os_anexos():
    h = (WEB / "templates" / "solic.html").read_text(encoding="utf-8")
    assert 'id="anexo_in"' in h and "FormData" in h and "anexos" in h
