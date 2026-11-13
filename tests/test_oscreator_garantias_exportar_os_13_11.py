"""O nº da OS de campo e o da inspeção na exportação de Garantias (13/11/2026, pedido da área de chamados: "a inspeção
vinculada aparece nos cartões do quadro, mas não vem na exportação"; o Levi: na planilha e no PDF). A planilha (Exportar
tabela) ganha as duas colunas logo depois da OS; o relatório ao cliente (Exportar relatório, PDF) ganha a linha "OS de
campo · OS de inspeção" em cada chamado. A cadeia é a que o cartão já lê da nota da OS.

Fracttal e banco FALSOS (os do teste de 28/10). Nomes e números de mentira: o repositório é público."""
import io

from openpyxl import load_workbook
from test_oscreator_garantias_28_10 import LINHAS, _linha, tela  # noqa: F401 — a fixture é usada pelo nome

import api  # noqa: E402 — o api.py do clone (o sys.path vem do módulo acima)
from os_web import acomp_web as aw  # noqa: E402

NOTA = ("[CHAMADO] Acompanhamento — Huawei · Inversor\nOS de campo: 9001 · Inspeção: 9002 · Ativo: TST-1\n"
        "Data da falha: 26/10/2026 09:55 · Menos de 7 dias: Não")


def _com_a_cadeia(monkeypatch):
    linhas = [dict(l, note=NOTA) if l["folio"] == "9101" else dict(l) for l in LINHAS]
    monkeypatch.setattr(api, "list_chamados", lambda **k: [dict(l) for l in linhas])


def test_a_planilha_tem_a_os_de_campo_e_a_de_inspecao(tela, monkeypatch):
    c, _, _ = tela
    _com_a_cadeia(monkeypatch)
    r = c.post("/os/chamados/acompanhamento/tabela", json={"folios": ["9101", "9103"]})
    assert r.status_code == 200
    ws = load_workbook(io.BytesIO(r.data)).active
    cab = [x.value for x in ws[1]]
    assert cab[:4] == ["OS", "Nº da OS de campo", "Nº da OS de inspeção", "Ativo"]
    assert [ws.cell(row=2, column=i).value for i in (1, 2, 3)] == [9101, 9001, 9002]    # números, não texto
    assert [ws.cell(row=3, column=i).value for i in (1, 2, 3)] == [9103, None, None]    # sem a cadeia na nota: vazio
    assert ws.max_column == 15 and cab[-1] == "Responsável"


def test_o_pdf_traz_a_os_de_campo_e_a_de_inspecao(monkeypatch):
    from os_web import relatorio_chamados as rc
    hoje = aw.agora_brt()
    com = aw.cartao(dict(_linha(1, 9101), note=NOTA), "SR 1", "", hoje, status="Aguardando retorno do Cliente")
    sem = aw.cartao(_linha(2, 9102), "", "", hoje, status="Aguardando retorno do Fabricante")
    m = rc.modelo([com, sem], "Cliente A", hoje, {})
    itens = {x["ref"]: x for s in m["secoes"] for x in s["itens"]}
    assert (itens["Ticket SR 1"]["os_campo"], itens["Ticket SR 1"]["inspecao"]) == ("9001", "9002")
    assert (itens["OS 9102"]["os_campo"], itens["OS 9102"]["inspecao"]) == ("", "")
    # no PDF, a linha sai no chamado que tem a cadeia (o texto do PDF lido de volta)
    pdf = rc.gerar(m)
    try:
        import fitz
    except ImportError:
        return
    texto = " ".join(p.get_text() for p in fitz.open(stream=pdf, filetype="pdf"))
    assert "OS de campo 9001 · OS de inspeção 9002" in " ".join(texto.split())
