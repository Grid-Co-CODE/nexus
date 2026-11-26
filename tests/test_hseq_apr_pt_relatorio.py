"""O relatório de APR e PT em PDF, do Histórico (26/11/2026). Levi: "tem que ter um botão de extrair relatório, e aí a pessoa
vai selecionar um mês e o cliente [...] só PT, só APR, os dois"; "um formato em PDF [...] parecido com o dos extintores".

O que estes testes seguram: o Histórico tem o "Extrair relatório" com o mês, o cliente e o que entra; o PDF sai como
anexo com o nome do tipo, do cliente e do mês; entram as PTs nascidas no mês e as APRs feitas nele, do cliente da usina;
o "só PT" e o "só APR" tiram a outra seção; outro cliente sai vazio dizendo isso; mês inválido volta ao Histórico. Banco
falso e nomes de mentira."""
import io
from datetime import timedelta

from pypdf import PdfReader

from nexus.campo import visao
from nexus.hseq import relatorio_apr_pt as RAP
from test_campo_visao import _aba, banco  # noqa: F401 (fixture)
from test_hseq_sem_apr import _apr

URL = "/t/hseq/apr-pt/relatorio.pdf"


def _texto(pdf: bytes) -> str:
    # as linhas quebradas da célula viram espaço: a frase é conferida inteira
    return " ".join(" ".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages).split())


def _mes_e_dia(app):
    """O mês e o dia da PT-1 do banco falso (nasce horas antes de agora): no dia 1, "hoje" e a PT cairiam em meses
    diferentes, e o teste não pode depender do relógio (regra do CLAUDE.md da raiz)."""
    with app.test_request_context("/"):
        dia = visao.pt("PT-1")["criada"].date()
    return f"{dia:%Y-%m}", dia


def test_o_historico_tem_o_extrair_relatorio(banco, logado):
    html = logado.get("/t/hseq/apr-pt?aba=historico").get_data(as_text=True)
    assert "Extrair relatório" in html and 'action="/t/hseq/apr-pt/relatorio.pdf"' in html
    assert 'name="mes"' in html and 'name="cliente"' in html and '<option value="pt">Só PT</option>' in html
    assert '<option value="Thopen">Thopen</option>' in html


def test_o_pdf_do_mes_e_do_cliente(app, banco, logado):
    mes, hoje = _mes_e_dia(app)
    _aba(banco, "apr_app_campo", "APR", [_apr("700", hoje.isoformat(), pt="PT-1"),
                                         _apr("701", hoje.isoformat(), precisa="sim", pt=""),
                                         _apr("702", (hoje.replace(day=1) - timedelta(days=1)).isoformat())])
    visao.limpar()
    r = logado.get(f"{URL}?mes={mes}&cliente=Thopen&tipo=ambos")
    assert r.status_code == 200 and r.mimetype == "application/pdf"
    assert r.headers["Content-Disposition"] == f'attachment; filename="apr-e-pt-thopen-{mes}.pdf"'
    t = _texto(r.data)
    assert "Relatório de APR e PT" in t and "Thopen" in t
    assert "Permissões de trabalho (PT)" in t and "PT-1" in t
    assert "Análises Preliminares de Risco (APR)" in t and "700" in t and "701" in t and "702" not in t   # 702: mês antes
    assert "pedia PT e ficou sem" in t


def test_so_pt_e_so_apr_tiram_a_outra_secao(app, banco, logado):
    mes, hoje = _mes_e_dia(app)
    _aba(banco, "apr_app_campo", "APR", [_apr("700", hoje.isoformat(), pt="PT-1")])
    visao.limpar()
    so_pt = _texto(logado.get(f"{URL}?mes={mes}&cliente=Thopen&tipo=pt").data)
    assert "Relatório de PT" in so_pt and "Análises Preliminares de Risco" not in so_pt
    so_apr = _texto(logado.get(f"{URL}?mes={mes}&cliente=Thopen&tipo=apr").data)
    assert "Relatório de APR" in so_apr and "Permissões de trabalho (PT)" not in so_apr


def test_outro_cliente_sai_vazio_e_mes_invalido_volta(app, banco, logado):
    mes, _hoje = _mes_e_dia(app)
    t = _texto(logado.get(f"{URL}?mes={mes}&cliente=Outro+Cliente&tipo=ambos").data)
    assert "Nenhuma PT neste mês para este cliente." in t
    r = logado.get(f"{URL}?mes=nada&tipo=ambos")
    assert r.status_code == 302 and r.headers["Location"].endswith("/t/hseq/apr-pt?aba=historico")


def test_o_mes_por_extenso_e_do_texto():
    from datetime import date
    assert RAP.mes_do_texto("2026-11") == date(2026, 11, 1) and RAP.mes_do_texto("x") is None
    assert RAP.mes_por_extenso(date(2026, 3, 1)) == "março de 2026"
