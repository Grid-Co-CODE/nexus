"""As fotos citadas na Aprovação de OS carregam na barra lateral (Levi, 16/11/2026: "Aprovação de OS quando tiver algo que
cita Fotos tem que carregar as fotos!"). Até ali o fato dizia o nome da foto ("p03 é a mesma imagem de p01", "1 foto
anexada 2 dias depois") e o clique abria o card da OS. O cartão do quadro segue sem foto (Levi, 05/11/2026: "nem precisa
mostrar a foto de cara"); na barra lateral, cada foto citada aparece.

O Nexus não guarda a imagem nem o endereço dela (o id da foto é o caminho no S3; o resto do endereço pode mudar): a
barra lateral abre só da memória, como antes, e cada imagem vem da rota `aprovacao/<id_wo>/foto/<id>`, que lê a lista
de anexos da OS no Fracttal (1 pedido, guardado 10 min por OS) e leva ao arquivo. A fila e os fatos: os de
test_campo_aprovacao_responsavel.py (15088 com p03 = p01; 15102 com a foto anexada 2 dias depois)."""
import hashlib
import re

import pytest
from test_campo_aprovacao_responsavel import ID, fila_resp, quadro  # noqa: F401  (fixtures)
from test_campo_aprovacao_supervisor import fila  # noqa: F401  (fixture)

from nexus.campo import prefiltro_fundo


def _imgs(html):
    return re.findall(r'<img[^>]*src="([^"]+)"', html)


def test_a_barra_lateral_mostra_as_fotos_citadas(quadro, logado):
    rep = logado.get("/t/campo/aprovacao/15088/detalhe").get_data(as_text=True)
    assert _imgs(rep) == [f"/t/campo/aprovacao/15088/foto/{ID['p3']}", f"/t/campo/aprovacao/15088/foto/{ID['p1']}"]
    assert 'loading="lazy"' in rep and re.search(r'<img[^>]*alt="Foto p03', rep)
    tarde = logado.get("/t/campo/aprovacao/15102/detalhe").get_data(as_text=True)
    assert _imgs(tarde) == [f"/t/campo/aprovacao/15102/foto/{ID['tarde']}"]
    # o cartão do quadro segue sem foto (05/11/2026)
    quadro_html = logado.get("/t/campo/aprovacao?responsavel=*").get_data(as_text=True)
    assert "<img" not in quadro_html.split('<div class="apq-quadro"', 1)[1]


def _anexo(caminho, tarefa=""):
    return {"value": f"https://s3.exemplo.test{caminho}?X-Amz-Signature=abc", "id_work_order_task": tarefa}


def _id(caminho):
    return hashlib.sha1(caminho.encode("utf-8")).hexdigest()[:16]


def test_a_rota_leva_ao_arquivo_da_lista_de_anexos_e_guarda_a_lista(quadro, logado, monkeypatch):
    prefiltro_fundo.limpar_fotos_da_os()
    pedidos = []

    def listar(folio):
        pedidos.append(folio)
        return [_anexo("/fotos/a.jpg"), _anexo("/docs/manual.pdf"),
                {"value": "http://s3.exemplo.test/fotos/b.jpg", "id_work_order_task": ""}]
    monkeypatch.setattr(prefiltro_fundo, "_listar", listar)
    r = logado.get(f"/t/campo/aprovacao/15088/foto/{_id('/fotos/a.jpg')}")
    assert r.status_code == 302 and r.headers["Location"] == "https://s3.exemplo.test/fotos/a.jpg?X-Amz-Signature=abc"
    assert logado.get(f"/t/campo/aprovacao/15088/foto/{_id('/fotos/a.jpg')}").status_code == 302
    assert pedidos == ["15088"]                                     # a lista é lida uma vez e guardada
    # o que não é foto da OS, o endereço que não é https e o id torto: 404
    assert logado.get(f"/t/campo/aprovacao/15088/foto/{_id('/docs/manual.pdf')}").status_code == 404
    assert logado.get(f"/t/campo/aprovacao/15088/foto/{_id('/fotos/b.jpg')}").status_code == 404
    assert logado.get("/t/campo/aprovacao/15088/foto/xyz").status_code == 404
    # a OS que não está na fila não vai ao Fracttal
    assert logado.get(f"/t/campo/aprovacao/99999/foto/{_id('/fotos/a.jpg')}").status_code == 404
    assert pedidos == ["15088"]


def test_o_fracttal_fora_nao_derruba_a_rota(quadro, logado, monkeypatch):
    prefiltro_fundo.limpar_fotos_da_os()

    def fora(folio):
        raise ConnectionError("Fracttal fora")
    monkeypatch.setattr(prefiltro_fundo, "_listar", fora)
    assert logado.get(f"/t/campo/aprovacao/15088/foto/{ID['p1']}").status_code == 503


@pytest.fixture(autouse=True)
def _sem_lista_guardada():
    yield
    prefiltro_fundo.limpar_fotos_da_os()
