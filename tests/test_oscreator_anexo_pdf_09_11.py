"""O anexo e o PDF da OS no card (09/11/2026, pedidos do Levi pela OS 8159):
- a observação escrita na aba Anexos da tarefa vinha com o TEXTO no lugar do caminho do arquivo e virava documento: o Abrir
  mostrava '{"erro":"Falha ao baixar a imagem (HTTP 404)."}' e o Baixar salvava esse JSON. Agora é nota de texto;
- o Abrir que falha mostra a página de aviso, e não o JSON; o Baixar pede o arquivo pela tela e só salva o arquivo;
- o PDF responde sempre em JSON (o erro sem JSON virava "a gravação pode ter sido feita" no card e "a sua sessão do Nexus
  acabou" na Aprovação de OS), as fotos têm prazo, e o POST que só lê tem o aviso de leitura.
O Fracttal é de mentira; números e textos inventados."""
import sys
from pathlib import Path

from test_oscreator_anexos_19_10 import TAREFA, WID, fr  # noqa: F401  (fixture)
from test_oscreator_os_pdf import _fracttal_da_os, _jpeg, cli  # noqa: F401  (fixture)

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402
from os_web import os_acoes_web as regra  # noqa: E402
from os_web import rotas_os_acoes  # noqa: E402

WEB = Path(ponte.RAIZ_CLONE) / "os_web"
TEXTO = "Não há cabine de medição 02 na UFV Teste"


def test_a_observacao_no_lugar_do_arquivo_e_nota_de_texto(fr):  # noqa: F811
    fr.arquivos[TAREFA] = [{"value": TEXTO, "description": ""},
                           {"value": "Outra observação", "description": "Campo", "type": 3},
                           {"value": ".ot/%d/laudo.pdf" % WID, "description": ""}]
    api.esquecer_os()
    anexos = api.get_os_anexos(WID)
    nota, outra, laudo = anexos
    assert (nota["is_text"], nota["value"], nota["desc"]) == (True, "", TEXTO)
    assert (outra["is_text"], outra["desc"]) == (True, "Campo: Outra observação")
    assert (laudo["is_text"], laudo["value"]) == (False, ".ot/%d/laudo.pdf" % WID)
    itens = regra.itens_os(anexos, WID)
    assert [(x["tipo"], x["texto"]) for x in itens if x["tipo"] == "nota"] == [("nota", TEXTO),
                                                                               ("nota", "Campo: Outra observação")]
    assert all(x["baixar"] is None for x in itens if x["tipo"] == "nota")           # a nota não tem Abrir nem Baixar
    assert [x["nome"] for x in itens if x["tipo"] == "documento"] == ["laudo.pdf"]


def test_o_abrir_que_falha_mostra_o_aviso_e_nao_o_json(cli, monkeypatch):  # noqa: F811
    monkeypatch.setattr(api, "s3_get_url", lambda name: "https://s3.exemplo.invalid/x")

    def sumiu(url):
        raise api.FracttalError("Falha ao baixar a imagem (HTTP 404).")
    monkeypatch.setattr(api, "baixar_imagem", sumiu)
    r = cli.get("/os/api/os/9202/anexo?value=.ot/9202/foto.jpg&nome=foto.jpg&abrir=1")
    h = r.get_data(as_text=True)
    assert r.status_code == 404 and r.mimetype == "text/html"
    assert "não está mais no Fracttal" in h and '{"erro"' not in h
    # o Baixar pede JSON: recebe o motivo para dizer no rodapé dos anexos, e nada para salvar
    r = cli.get("/os/api/os/9202/anexo?value=.ot/9202/foto.jpg&nome=foto.jpg", headers={"Accept": "application/json"})
    assert r.status_code == 404 and "não está mais no Fracttal" in r.get_json()["erro"]
    # o Fracttal fora: outro aviso, também sem o JSON na aba
    monkeypatch.setattr(api, "baixar_imagem", lambda url: (_ for _ in ()).throw(api.FracttalError("Erro ao baixar")))
    r = cli.get("/os/api/os/9202/anexo?value=.ot/9202/foto.jpg&nome=foto.jpg&abrir=1")
    assert r.status_code == 502 and "tente de novo" in r.get_data(as_text=True)


def test_o_pdf_que_quebra_responde_em_json_com_o_motivo(cli, monkeypatch):  # noqa: F811
    _fracttal_da_os(monkeypatch, foto=_jpeg())
    from os_web import os_pdf

    def quebra(*a, **k):
        raise RuntimeError("fonte sem o caractere")
    monkeypatch.setattr(os_pdf, "gerar", quebra)
    r = cli.post("/os/api/os/pdf", json={"folio": "9102"})
    assert r.status_code == 500 and r.is_json
    assert "Não consegui montar o PDF desta OS (RuntimeError)" in r.get_json()["erro"]


def test_as_fotos_do_pdf_tem_prazo(cli, monkeypatch):  # noqa: F811
    pedidos = _fracttal_da_os(monkeypatch, foto=_jpeg())
    monkeypatch.setattr(rotas_os_acoes, "PRAZO_FOTOS_S", -1)               # o prazo já passou: nenhuma foto é pedida
    j = cli.post("/os/api/os/pdf", json={"folio": "9102"}).get_json()
    assert j["ok"] and (j["fotos"], j["falhas"]) == (0, 2) and pedidos["fotos"] == 0
    assert cli.get(j["url"]).data.startswith(b"%PDF")


def test_o_post_que_so_le_tem_o_aviso_de_leitura_e_o_baixar_confere():
    js = (WEB / "static" / "carga.js").read_text(encoding="utf-8")
    assert "const SO_LEITURA = [/\\/api\\/os\\/pdf$/, /\\/anexos-zip$/];" in js
    assert "Nada foi gravado no Fracttal." in js and "conferida(fetch(url, opcoes), opcoes, url)" in js
    assert "semResposta(r.status, leitura)" in js
    card = (WEB / "static" / "os_acoes.js").read_text(encoding="utf-8")
    assert card.count("data-baixar-arq>Baixar</a>") == 2 and "async function baixarArquivo(e, dlg, a)" in card
    assert "if (a.origin !== location.origin) return;" in card            # a pré-assinada do S3 segue direto


LONGO = ("linha de texto comprida " * 12 + "\n") * 120


def test_texto_longo_nao_derruba_o_pdf():
    """A OS 8159 dava LayoutError: uma linha de tabela (a resposta longa de uma subtarefa) maior que uma página, que o
    reportlab não quebra sem o splitInRow; e a legenda longa da foto não cabia no quadro dela."""
    from os_web import os_pdf
    m = os_pdf.modelo({"folio": "1", "descricao": "Teste",
                       "subtarefas": [{"descricao": LONGO, "resposta": LONGO, "feito": True, "tipo": "Texto"}],
                       "tarefas": [{"id": 1, "titulo": "T", "nota": LONGO}]},
                      anexos_sub=[{"url": "u", "value": "a/b.jpg", "nome": "b.jpg", "is_image": True,
                                   "descricao": LONGO[:6000], "subtarefa": LONGO[:4000]}],
                      recursos=[{"tipo": "Peça", "descricao": LONGO, "qtd": 1}])
    assert os_pdf.gerar(m, fotos=[os_pdf.reduzir(_jpeg())]).startswith(b"%PDF")


def test_o_bloco_que_ainda_nao_cabe_sai_com_o_texto_cortado(monkeypatch):
    from reportlab.platypus.doctemplate import LayoutError
    from os_web import os_pdf
    vistos = []
    original = os_pdf._gerar

    def primeiro_falha(m, **k):
        vistos.append(m)
        if len(vistos) == 1:
            raise LayoutError("não coube")
        return original(m, **k)
    monkeypatch.setattr(os_pdf, "_gerar", primeiro_falha)
    m = os_pdf.modelo({"folio": "1", "descricao": "Teste", "notas": LONGO, "subtarefas": [], "tarefas": []})
    assert os_pdf.gerar(m).startswith(b"%PDF") and len(vistos) == 2
    assert "texto cortado no PDF" in str(vistos[1]) and len(str(vistos[1])) < len(str(vistos[0]))
