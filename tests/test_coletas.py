# -*- coding: utf-8 -*-
"""Coletas (Performance > Coletas, 11/11/2026): o Conversor Grid Co. dentro do Nexus, com o BD lido do banco.

A prova que importa: o BD montado pelo banco (valores + o mapa de fórmulas que a coleta sobe) dá a MESMA conversão que o
BD lido do Excel — a mesma tabela por aba, e o bloco colado muda as mesmas células. Sem o mapa, o banco não é usado (a
fórmula sem valor em cache chega vazia ao banco, e o Conversor escreveria por cima do IPOA da Vitesse = Hortina).
"""
import datetime as dt
import io
import os
import re
import time

import openpyxl
import pytest

from nexus.performance.coletas import motor, pg, servico

from conversor import montagem  # noqa: E402 — depois do motor
from conversor.nucleo import BD, Celula, Contexto  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D0 = dt.date(2026, 10, 1)
HOJE = dt.date(2026, 10, 20)
CAB = ["Usina", "Data", "Multimedidor", "Inversor 1.1", "Inversor 1.2", "IPOA (kWh/m²)", "GHI (kWh/m²)",
       "IPOA (kWh/m²) DEF", "Validação"]
SUBIDA = "2026-10-20T08:00:00-03:00"


def _bd_excel(tmp_path):
    """O BD de mentira do teste do Conversor: Multimedidor e IPOA DEF são fórmula; 11-13/10 o IPOA é fórmula de outra
    aba (estação quebrada, o caso da Salvales = Carosa de 21 a 25/10/2026)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Teste"
    ws.append(CAB)
    for k in range(25):
        r = k + 2
        d = D0 + dt.timedelta(days=k)
        ws.append(["Teste", dt.datetime(d.year, d.month, d.day), "=SUM(D%d:E%d)" % (r, r), None, None, None, None,
                   "=MAX(F%d,G%d)" % (r, r), "ok"])
    for k in range(10):
        ws.cell(k + 2, 4, 1500.0)
        ws.cell(k + 2, 5, 1400.0)
        ws.cell(k + 2, 6, 6.0)
    for k in range(10, 13):
        ws.cell(k + 2, 6, "='Outra aba'!F%d" % (k + 2))
    velha = wb.create_sheet("Vitesse")                # a aba renomeada que ficou velha no banco
    velha.append(CAB)
    p = tmp_path / "BD_Performance.xlsx"
    wb.save(p)
    return str(p)


class BancoDeMentira:
    """A API db_performace como ela devolve (row_number, headers, values; sem fórmula), montada a partir do Excel — e o
    livro bd_formulas como a coleta vai subir: as células que são fórmula e a lista de abas do Excel."""

    def __init__(self, caminho, com_mapa=True, mapa_em=SUBIDA, abas_excel=("Teste",)):
        wb = openpyxl.load_workbook(caminho)
        self.sheets, self.rows, sid = {}, {}, 0
        formulas = []
        for ws in wb.worksheets:
            sid += 1
            cab = [c.value for c in ws[1]]
            linhas = []
            for r in range(2, ws.max_row + 1):
                vals = []
                for j in range(1, len(cab) + 1):
                    v = ws.cell(r, j).value
                    if isinstance(v, str) and v.startswith("="):
                        formulas.append({"aba": ws.title, "linha": r, "coluna": j, "cabecalho": cab[j - 1],
                                         "formula": v, "subida_em": mapa_em})
                        v = None                       # valores-only: a fórmula sem cache sobe vazia
                    elif isinstance(v, dt.datetime):
                        v = v.strftime("%Y-%m-%d")
                    vals.append(v)
                linhas.append({"row_number": r, "headers": cab, "values": vals})
            self.sheets.setdefault("bd_performance", {})[ws.title] = {"id": sid, "sheet_name": ws.title, "header_row": 1}
            self.rows[sid] = linhas
        if com_mapa:
            for nome, linhas, cab in (("formulas_bd_performance", formulas, pg.CAB_FORMULAS),
                                      ("abas_bd_performance", [{"aba": a, "linhas": 0, "colunas": 0, "subida_em": mapa_em}
                                                               for a in abas_excel], pg.CAB_ABAS)):
                sid += 1
                self.sheets.setdefault(pg.LIVRO_FORMULAS, {})[nome] = {"id": sid, "sheet_name": nome}
                self.rows[sid] = [{"row_number": i + 2, "headers": list(cab), "values": [x.get(c) for c in cab]}
                                  for i, x in enumerate(linhas)]
        self.pedidos = 0

    def livros(self):
        return {"bd_performance": {"key": "bd_performance", "updated_at": SUBIDA},
                "bd_thopen": {"key": "bd_thopen", "updated_at": SUBIDA}}

    def abas(self):
        return self.sheets

    def linhas(self, sid):
        self.pedidos += 1
        return self.rows[sid]


def C(d, col, v):
    return Celula("BD_Performance", "Teste", d, col, v)


def _celulas():
    cel = []
    for k in range(8, 16):
        d = D0 + dt.timedelta(days=k)
        cel += [C(d, "Inversor 1.1", 1500.0), C(d, "Inversor 1.2", 1400.0), C(d, "IPOA", 6.1), C(d, "GHI", 5.0)]
    return cel


def _colar(bd_path, saida, aba="Teste"):
    """Cola cada bloco no BD (Ctrl+V na célula indicada): {(linha, coluna): (antes, depois)} do que muda."""
    ws = openpyxl.load_workbook(saida)[aba]
    bd = openpyxl.load_workbook(bd_path)[aba]
    mudou, r = {}, 1
    while r <= ws.max_row:
        m = re.match(r"Bloco \d+ de \d+ — colar na célula ([A-Z]+)(\d+)", str(ws.cell(r, 1).value or ""))
        if not m:
            r += 1
            continue
        col0, lin0 = openpyxl.utils.column_index_from_string(m.group(1)), int(m.group(2))
        ncol = 0
        while ws.cell(r + 1, 2 + ncol).value is not None:
            ncol += 1
        r += 2
        i = 0
        while r <= ws.max_row and ws.cell(r, 1).value is not None:
            for j in range(ncol):
                v, velho = ws.cell(r, 2 + j).value, bd.cell(lin0 + i, col0 + j).value
                if v != velho:
                    mudou[(lin0 + i, col0 + j)] = (velho, v)
            r += 1
            i += 1
    return mudou


def _montar(bd, pasta):
    ctx = Contexto({"BD_Performance": bd}, hoje=HOJE)
    return montagem.montar([(c, "Teste") for c in _celulas()], ctx, pasta, carimbo=dt.datetime(2026, 10, 20, 9, 0))


def _sem_hora(tabela):
    return [{k: v for k, v in t.items()} for t in tabela]


# ── o motor é a cópia idêntica da pasta da coleta ──────────────────────────────────────────────────────────────────
def test_o_motor_e_o_pacote_conversor_da_copia_do_nexus():
    import conversor
    assert os.path.dirname(conversor.__file__) == os.path.join(motor.PASTA, "conversor")
    assert motor.APP_VERSAO


def test_a_copia_e_a_tela_batem_com_a_pasta_da_coleta():
    import sys
    sys.path.insert(0, os.path.join(RAIZ, "ferramentas"))
    import sincronizar_conversor as S
    origem = os.environ.get("CONVERSOR_DIR") or S.ORIGEM_PADRAO
    if not os.path.isdir(origem):
        pytest.skip("a pasta do Conversor não existe nesta máquina (o servidor)")
    dif, sobra = S.diferencas(origem)
    assert (dif, sobra) == ([], []), "rode python ferramentas/sincronizar_conversor.py"
    assert S.tela_difere(origem) == [], "rode python ferramentas/sincronizar_conversor.py"


# ── o BD do banco ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_o_bd_do_banco_da_a_mesma_conversao_que_o_excel(tmp_path):
    p = _bd_excel(tmp_path)
    xl = BD("BD_Performance", p)
    try:
        r_xl = _montar(xl, str(tmp_path / "xl"))
    finally:
        xl.fechar()
    bd = pg.BDdoBanco("BD_Performance", BancoDeMentira(p))
    r_pg = _montar(bd, str(tmp_path / "pg"))
    assert _sem_hora(r_pg["tabela"]) == _sem_hora(r_xl["tabela"])
    mud_xl = _colar(p, r_xl["saidas"][0]["caminho"])
    mud_pg = _colar(p, r_pg["saidas"][0]["caminho"])
    assert mud_pg == mud_xl and mud_pg
    formula = {(k + 2, 6) for k in range(10, 13)}
    assert not formula & set(mud_pg)                      # a fórmula do IPOA (= outra aba) ficou intocada
    assert [a["texto"] for a in r_pg["avisos"]] == [a["texto"] for a in r_xl["avisos"]]


def test_a_data_vira_data_e_a_formula_volta_por_celula(tmp_path):
    bd = pg.BDdoBanco("BD_Performance", BancoDeMentira(_bd_excel(tmp_path)))
    a = bd.aba("Teste")
    assert a.datas[dt.date(2026, 10, 1)] == 2 and a.linha_cab == 1
    assert a.valor(dt.date(2026, 10, 11), a.col("IPOA (kWh/m²)")) == "='Outra aba'!F12"
    assert a.valor(dt.date(2026, 10, 14), a.col("IPOA (kWh/m²)")) is None      # o dia seguinte é valor (vazio)
    assert bd.estilos("Teste", 1, 5, 0, 5) == {}


def test_a_aba_velha_do_banco_nao_conta(tmp_path):
    bd = pg.BDdoBanco("BD_Performance", BancoDeMentira(_bd_excel(tmp_path)))
    assert bd.abas() == ["Teste"] and bd.aba("Vitesse") is None and bd.velhas == ["Vitesse"]


def test_sem_o_mapa_o_banco_nao_e_usado(tmp_path):
    with pytest.raises(pg.SemMapa, match="mapa de fórmulas"):
        pg.BDdoBanco("BD_Performance", BancoDeMentira(_bd_excel(tmp_path), com_mapa=False))


def test_mapa_de_outra_subida_nao_vale(tmp_path):
    with pytest.raises(pg.SemMapa, match="outra subida"):
        pg.BDdoBanco("BD_Performance", BancoDeMentira(_bd_excel(tmp_path), mapa_em="2026-10-19T08:00:00-03:00"))


def test_a_leitura_do_banco_e_uma_por_subida(tmp_path):
    pg._GUARDA.clear()
    b = BancoDeMentira(_bd_excel(tmp_path))
    bd1, e1 = pg.bd_do_banco("BD_Performance", b)
    bd2, e2 = pg.bd_do_banco("BD_Performance", b)
    assert bd1 is bd2 and e1 is e2 is None
    sem, erro = pg.bd_do_banco("BD_Thopen", b)
    assert sem is None and "bd_thopen" in erro.lower()
    pg._GUARDA.clear()


# ── a sessão de cada pessoa ────────────────────────────────────────────────────────────────────────────────────────
def test_nome_seguro_nao_sai_da_pasta():
    assert servico.nome_seguro("../../etc/x.csv") == os.path.join("etc", "x.csv")
    assert servico.nome_seguro("pasta/sub/a:b.csv") == os.path.join("pasta", "sub", "a_b.csv")


def test_o_bd_em_excel_solto_entra_no_lugar_do_banco_e_a_data_do_arquivo_vale(tmp_path):
    p = _bd_excel(tmp_path)
    s = servico.SessaoNexus(lambda: BancoDeMentira(p, com_mapa=False), str(tmp_path / "sessao"), str(tmp_path / "novos"))
    try:
        s.iniciar()
        assert s.pronto.wait(10)
        e = {b["destino"]: b for b in s.estado()["bds"]}
        assert not e["BD_Performance"]["lido"] and "mapa de fórmulas" in e["BD_Performance"]["erro"]
        lote = s.novo_lote()
        with open(p, "rb") as f:
            s.receber(lote, "BD_Performance · meu.xlsx", io.BytesIO(f.read()))
        csv = s.receber(lote, "relatorio.csv", io.BytesIO("a;b\n1;2\n".encode()), modificado_ms=1793000000000)
        assert abs(os.path.getmtime(csv) - 1793000000) < 2
        est = s.lote_pronto(lote, ["BD_Performance · meu.xlsx", "relatorio.csv"])
        bds = {b["destino"]: b for b in est["bds"]}
        assert bds["BD_Performance"]["lido"] and bds["BD_Performance"]["origem"] == "arquivo"
        assert [c["nome"] for c in est["itens"]] == ["relatorio.csv"]            # o BD não vira cartão
        for _ in range(50):
            if all(c["estado"] != "identificando" for c in s.estado()["itens"]):
                break
            time.sleep(0.1)
        assert s.estado()["itens"][0]["estado"] == "desconhecido"
        assert s.separar(s.itens[0]["id"], "Portal X")["estado"] == "separado"
        assert any("Portal X" in n for n in os.listdir(tmp_path / "novos"))
        s.limpar()
        assert s.itens == [] and s.origem_bd.get("BD_Performance") is None      # o Excel sai com os arquivos
    finally:
        s.fechar()


def test_a_conversao_avisa_que_o_banco_anda_atras_do_excel(tmp_path):
    p = _bd_excel(tmp_path)
    pg._GUARDA.clear()
    s = servico.SessaoNexus(lambda: BancoDeMentira(p), str(tmp_path / "sessao"), str(tmp_path / "novos"), hoje=HOJE)
    try:
        s.iniciar()
        assert s.pronto.wait(10) and s.estado_bds()[0]["origem"] == "banco"

        class Lt:                                    # um leitor que devolve as células do teste
            destino, fonte = "BD_Performance", "Teste"

            def ler(self, arq, ctx, rec, escolha=None):
                return _celulas(), []

        class Rec:
            leitor, fonte, recusa, usinas, candidatas, pergunta, periodo, detalhe = Lt(), "Teste", None, ["Teste"], [], None, None, ""

        arq = type("A", (), {"nome": "x.csv", "caminho": p})()
        s.itens = [{"id": 1, "nome": "x.csv", "caminho": p, "tamanho": 1, "estado": "ok", "arqs": [arq],
                    "recs": [(arq, Rec())], "escolha": None}]
        os.utime(p, (time.mktime((2026, 10, 20, 9, 0, 0, 0, 0, -1)),) * 2)
        r = s.converter(agora=dt.datetime(2026, 10, 20, 9, 0))
        assert r["saidas"] and r["saidas"][0]["caminho"].startswith("Para colar no BD_Performance")
        assert os.path.isfile(s.saidas[0]) and r["pasta"] == ""
        assert "veio do banco, da subida de 20/10 às 08:00" in r["avisos"][0]["texto"]
    finally:
        s.fechar()
        pg._GUARDA.clear()


# ── as rotas ───────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.fixture
def coletas(app, logado, tmp_path):
    p = _bd_excel(tmp_path)
    pg._GUARDA.clear()
    app.config["NEXUS_COLETAS_BANCO"] = lambda: BancoDeMentira(p)
    app.config["NEXUS_COLETAS_TMP"] = str(tmp_path)
    yield logado
    for k in list(servico._SESSOES):
        servico.esquecer(k)
    pg._GUARDA.clear()


def test_a_tela_e_a_pagina_do_conversor_abrem(coletas):
    r = coletas.get("/t/performance/coletas")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "gc-explica" in html and 'src="/t/performance/coletas/app"' in html
    app_html = coletas.get("/t/performance/coletas/app").get_data(as_text=True)
    assert "pywebview.api." not in app_html.replace("window.pywebview && window.pywebview.api && window.pywebview.api.copiar", "")
    assert '"/t/performance/coletas"' in app_html and "/static/coletas/furos.js" in app_html


def test_o_estado_le_o_bd_do_banco(coletas):
    for _ in range(50):
        e = coletas.post("/t/performance/coletas/api/estado", json={"args": []}).get_json()
        if e["bd_pronto"]:
            break
        time.sleep(0.1)
    bds = {b["destino"]: b for b in e["bds"]}
    assert bds["BD_Performance"]["lido"] and bds["BD_Performance"]["origem"] == "banco"
    assert bds["BD_Performance"]["lido_em"] == "20/10 08:00"
    assert not bds["BD_Thopen"]["lido"] and bds["BD_Thopen"]["erro"]


def test_metodo_fora_da_lista_nao_existe(coletas):
    assert coletas.post("/t/performance/coletas/api/fechar", json={}).status_code == 404


def test_o_envio_e_o_lote(coletas):
    lote = coletas.post("/t/performance/coletas/api/novo_lote", json={"args": []}).get_json()
    r = coletas.post("/t/performance/coletas/arquivo", data={"lote": str(lote), "rel": "a.csv", "modificado": "",
                                                             "arquivo": (io.BytesIO(b"x;y\n1;2\n"), "a.csv")})
    assert r.status_code == 200
    e = coletas.post("/t/performance/coletas/api/lote_pronto", json={"args": [lote, ["a.csv"]]}).get_json()
    assert [c["nome"] for c in e["itens"]] == ["a.csv"]
    assert coletas.post("/t/performance/coletas/api/lote_pronto", json={"args": [999, ["a.csv"]]}).status_code == 400


def test_planilha_que_nao_existe_e_404(coletas):
    assert coletas.get("/t/performance/coletas/planilha/0").status_code == 404


def test_os_furos_sobem_e_todos_veem_o_mesmo(coletas, app, tmp_path):
    app.config["NEXUS_DADOS"] = str(tmp_path / "dados")
    assert "erro" in coletas.get("/t/performance/coletas/furos").get_json()
    html = ('<script>\nconst DB={"gen":"11/11/2026","months":{"2026-11":{"plants":[]}}};\n'
            "let CONF=/*CONF0*/{}/*END0*/;\n</script>")
    r = coletas.post("/t/performance/coletas/furos", data={"arquivo": (io.BytesIO(html.encode()), "Furos_Coleta_Performance_1.html")})
    assert r.status_code == 200 and r.get_json()["db"]["gen"] == "11/11/2026"
    assert coletas.get("/t/performance/coletas/furos").get_json()["nome"] == "Furos_Coleta_Performance_1.html"
    ruim = coletas.post("/t/performance/coletas/furos", data={"arquivo": (io.BytesIO(b"<html></html>"), "x.html")})
    assert ruim.status_code == 400
    m = coletas.post("/t/performance/coletas/furos/html", json={"conf": {"a": {"r": "ok"}}})
    assert m.status_code == 200 and '/*CONF0*/{"a": {"r": "ok"}}/*END0*/' in m.get_data(as_text=True)
