"""O que o Radar ganhou depois do clone (06/11/2026): os PDFs dos contratos no servidor do Nexus (no Supabase eram um
arquivo privado) e a consulta da OS pelo número no Fracttal (no Supabase, a função `fracttal-os`). Banco falso; nomes
fictícios."""
import pytest

from nexus.cadastro.cifra import Cofre
from nexus.zeladoria import contratos_pdf, copia, fracttal_os, leitura
from tests.test_zeladoria_copia import AGORA, DE_PARA
from tests.test_zeladoria_torre import CHAVE, _entrar_como, _exp, banco  # noqa: F401 — as fixtures

PDF = b"%PDF-1.4\n% contrato de teste\n"


@pytest.fixture
def com_contratos(app, banco, tmp_path):  # noqa: F811
    exp = _exp()
    exp["tipos"]["zeladoria_contratual_docs"] = [["id", "bigint"], ["cliente", "text"], ["titulo", "text"],
                                                 ["caminho_pdf", "text"], ["caminho_zeladoria", "text"]]
    exp["tabelas"]["zeladoria_contratual_docs"] = [
        {"id": 1, "cliente": "Cliente A", "titulo": "Contrato A", "caminho_pdf": "cliente-a/contrato.pdf",
         "caminho_zeladoria": "cliente-a/contrato_zeladoria.pdf"}]
    copia.copiar(exp, de_para=DE_PARA, cofre=Cofre(CHAVE), base="http://pg.falso", token="t", sessao=banco,
                 gravar=True, agora=AGORA)
    app.config["NEXUS_DADOS"] = str(tmp_path)
    leitura.limpar()
    return tmp_path


def test_o_caminho_fica_dentro_da_pasta(app, tmp_path):
    app.config.update(NEXUS_DADOS=str(tmp_path))
    for ruim in ("../fora.pdf", "/abs.pdf", "a\\b.pdf", "a/../../b.pdf", ""):
        with pytest.raises(contratos_pdf.Recusado):
            contratos_pdf.arquivo(app.config, ruim)
    with pytest.raises(contratos_pdf.Recusado, match="não é um PDF"):
        contratos_pdf.guardar(app.config, "a/b.pdf", b"<html>")
    assert contratos_pdf.guardar(app.config, "a/b.pdf", PDF) == len(PDF)
    assert (tmp_path / "zeladoria" / "contratos" / "a" / "b.pdf").read_bytes() == PDF


def test_o_admin_envia_e_o_aprovado_abre(cliente, logado, com_contratos):
    r = logado.get("/t/zeladoria/api/contrato-pdf?caminho=cliente-a/contrato.pdf")
    assert r.status_code == 404 and "ainda não foi trazido" in r.get_json()["erro"]
    pagina = logado.get("/t/zeladoria/contratos-pdf").get_data(as_text=True)
    assert "cliente-a/contrato.pdf" in pagina and "falta" in pagina
    import io
    r = logado.post("/t/zeladoria/api/contratos/enviar",
                    data={"caminho": "cliente-a/contrato.pdf", "arquivo": (io.BytesIO(PDF), "contrato.pdf")},
                    content_type="multipart/form-data")
    assert r.status_code == 200, r.get_json()
    link = logado.get("/t/zeladoria/api/contrato-pdf?caminho=cliente-a/contrato.pdf").get_json()["signedUrl"]
    assert link == "/t/zeladoria/contrato/cliente-a/contrato.pdf"
    pdf = logado.get(link)
    assert pdf.status_code == 200 and pdf.data == PDF and pdf.mimetype == "application/pdf"
    # caminho fora da cópia não abre, mesmo que o arquivo exista
    contratos_pdf.guardar(logado.application.config, "outro/x.pdf", PDF)
    assert logado.get("/t/zeladoria/contrato/outro/x.pdf").status_code == 404
    assert logado.post("/t/zeladoria/api/contratos/enviar", data={"caminho": "outro/x.pdf"}).status_code == 400


def test_so_o_admin_envia(cliente, com_contratos):
    c = _entrar_como(cliente, "fulano@exemplo.com")              # aprovado, mas não administrador do Nexus
    assert c.get("/t/zeladoria/contratos-pdf").status_code == 403
    assert c.post("/t/zeladoria/api/contratos/enviar", data={"caminho": "cliente-a/contrato.pdf"}).status_code == 403
    pendente = _entrar_como(cliente, "beltrano@exemplo.com")
    assert pendente.get("/t/zeladoria/api/contrato-pdf?caminho=cliente-a/contrato.pdf").status_code == 403


def test_a_os_do_fracttal_vira_o_que_o_app_espera():
    linhas = [{"wo_folio": "123", "id_status_work_order": "4", "personnel_description": "Fulano de Tal",
               "creation_date": "2026-11-01T10:00:00+00:00", "initial_date": "2026-11-03T02:30:00+00:00",
               "final_date": "2026-11-04T12:00:00+00:00", "description": "Roçagem — UFV A — lote 1",
               "groups_1_description": "", "tasks_log_types_2_description": "Zeladoria", "task_note": "cancelada"},
              {"wo_folio": "123", "tasks_log_types_2_description": "Elétrica"}]
    os_ = fracttal_os.da_os("123", linhas)
    assert os_["encontrada"] and os_["status"] == 4 and os_["tecnico"] == "Fulano de Tal"
    assert os_["data_marcada"] == "2026-11-02"                   # o dia de Brasília: 02:30Z é o dia anterior
    assert os_["usina_texto"] == "UFV A" and os_["area"] == ["Zeladoria", "Elétrica"] and os_["nota"] == "cancelada"
    assert fracttal_os.da_os("9", []) == {"folio": "9", "encontrada": False}


def test_a_rota_da_os_e_o_limite_da_cota(cliente, com_contratos, monkeypatch):
    from nexus.campo import nota_fracttal
    vistos = []

    def tarefas(folio, ler=None):
        vistos.append(folio)
        if folio == "3":
            raise RuntimeError("429")
        return [{"wo_folio": folio, "id_status_work_order": "1", "description": "Roçagem"}]
    monkeypatch.setattr(nota_fracttal, "tarefas_da_os", tarefas)
    c = _entrar_como(cliente, "fulano@exemplo.com")
    r = c.post("/t/zeladoria/api/funcao/fracttal-os", json={"folios": ["1", "2", "3", "4"]}).get_json()
    assert [o["folio"] for o in r["os"]] == ["1", "2"] and r["limite"] is True and vistos == ["1", "2", "3"]
    assert c.post("/t/zeladoria/api/funcao/fracttal-os", json={"folios": ["x"]}).status_code == 400
    assert c.post("/t/zeladoria/api/funcao/fracttal-os", json={"folios": [str(i) for i in range(11)]}).status_code == 400
    pendente = _entrar_como(cliente, "beltrano@exemplo.com")
    assert pendente.post("/t/zeladoria/api/funcao/fracttal-os", json={"folios": ["1"]}).status_code == 403
