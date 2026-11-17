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

from nexus.dados.conexao import SemBanco
from nexus.performance.coletas import motor, pg, servico

from conversor import montagem  # noqa: E402 — depois do motor
from conversor.nucleo import BD, Celula, Contexto, formula  # noqa: E402

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
    livro bd_formulas como a coleta sobe (`src/mapa_formulas.py`): os trechos de células com fórmula seguidas na mesma
    coluna (o texto da 1ª célula, sem o "=") e a lista de abas do Excel."""

    def __init__(self, caminho, com_mapa=True, mapa_em=SUBIDA, abas_excel=("Teste",)):
        wb = openpyxl.load_workbook(caminho)
        self.sheets, self.rows, sid = {}, {}, 0
        celulas = {}                                   # (aba, coluna) -> {linha: fórmula}
        for ws in wb.worksheets:
            sid += 1
            cab = [c.value for c in ws[1]]
            linhas = []
            for r in range(2, ws.max_row + 1):
                vals = []
                for j in range(1, len(cab) + 1):
                    v = ws.cell(r, j).value
                    if isinstance(v, str) and v.startswith("="):
                        celulas.setdefault((ws.title, j, cab[j - 1]), {})[r] = v
                        v = None                       # valores-only: a fórmula sem cache sobe vazia
                    elif isinstance(v, dt.datetime):
                        v = v.strftime("%Y-%m-%d")
                    vals.append(v)
                linhas.append({"row_number": r, "headers": cab, "values": vals})
            self.sheets.setdefault("bd_performance", {})[ws.title] = {"id": sid, "sheet_name": ws.title, "header_row": 1}
            self.rows[sid] = linhas
        formulas = []
        for (aba, j, cab_j), por_linha in celulas.items():
            ls = sorted(por_linha)
            de = ls[0]
            for i, n in enumerate(ls):
                if i + 1 == len(ls) or ls[i + 1] != n + 1:
                    formulas.append({"aba": aba, "coluna": j, "linha_de": de, "linha_ate": n, "cabecalho": cab_j,
                                     "formula": por_linha[de][1:], "subida_em": mapa_em})
                    de = ls[i + 1] if i + 1 < len(ls) else None
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
    # o trecho 11-13/10 (linhas 12 a 14) volta inteiro como fórmula; o texto é o da 1ª célula (o Conversor só pergunta SE)
    assert all(formula(a.valor(dt.date(2026, 10, d), a.col("IPOA (kWh/m²)"))) for d in (11, 12, 13))
    assert a.valor(dt.date(2026, 10, 14), a.col("IPOA (kWh/m²)")) is None      # o dia seguinte é valor (vazio)
    assert all(formula(a.valor(D0 + dt.timedelta(days=k), a.col("Multimedidor"))) for k in range(25))
    assert bd.estilos("Teste", 1, 5, 0, 5) == {}


def test_a_aba_velha_do_banco_nao_conta(tmp_path):
    bd = pg.BDdoBanco("BD_Performance", BancoDeMentira(_bd_excel(tmp_path)))
    assert bd.abas() == ["Teste"] and bd.aba("Vitesse") is None and bd.velhas == ["Vitesse"]


def test_sem_o_mapa_o_banco_nao_e_usado(tmp_path):
    with pytest.raises(pg.SemMapa, match="mapa de fórmulas"):
        pg.BDdoBanco("BD_Performance", BancoDeMentira(_bd_excel(tmp_path), com_mapa=False))


def test_mapa_em_outro_formato_nao_vira_bd_sem_formula(tmp_path):
    """O leitor que não entende o mapa NUNCA lê o BD sem as fórmulas (16/11/2026: o mapa passou de uma linha por célula
    a trechos; o leitor velho leria o novo sem marcar fórmula nenhuma e o bloco colaria valor por cima da soma)."""
    b = BancoDeMentira(_bd_excel(tmp_path))
    sid = b.sheets[pg.LIVRO_FORMULAS]["formulas_bd_performance"]["id"]
    for x in b.rows[sid]:
        x["headers"] = ["aba", "linha", "coluna", "cabecalho", "formula", "subida_em", "x"]
    with pytest.raises(pg.SemMapa, match="nenhum trecho"):
        pg.BDdoBanco("BD_Performance", b)


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


def _sem_banco():
    raise SemBanco("teste sem banco")


def test_os_furos_sobem_e_todos_veem_o_mesmo(coletas, app, tmp_path):
    """Desde 16/11/2026 a tela 3 lê os furos calculados pelo Nexus (tests/test_coletas_furos_r01.py); o relatório que
    alguém subiu é a reserva de quando a conta não sai (aqui, o banco fora)."""
    app.config["NEXUS_DADOS"] = str(tmp_path / "dados")
    app.config["NEXUS_COLETAS_BANCO"] = _sem_banco
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


# ── os filtros dos Furos no modelo do Histórico de OS (12/11/2026) ─────────────────────────────────────────────────
def test_os_furos_usam_o_painel_do_historico_e_varios_valores(coletas):
    html = coletas.get("/t/performance/coletas/app").get_data(as_text=True)
    assert "/static/zeladoria/filtros.css" in html and "/static/coletas/filtros.js" in html and "/static/coletas/coletas.css" in html
    furos = open(os.path.join(RAIZ, "nexus", "static", "coletas", "furos.js"), encoding="utf-8").read()
    assert 'const vs = i => [...$f(i).options]' in furos                      # cada filtro lê vários valores
    assert 'if (sit.length && !sit.some(x => sitOk(x, m))) return false;' in furos
    assert 'p.cliente !== c' not in furos                                      # não sobrou o filtro de um valor só
    assert "window.coletasFiltros.atualizar()" in furos
    peca = open(os.path.join(RAIZ, "nexus", "static", "coletas", "filtros.js"), encoding="utf-8").read()
    for campo in ("fzCli", "fzCart", "fzSrc", "fzSt", "fzSit", "fzZero", "fzOS", "fzConf", "fzFInv", "fzFIpoa", "fzFGhi",
                  "fzColF"):
        assert '"%s"' % campo in peca                                          # todos os filtros do .exe no painel
    assert "Aplicar" in peca and "Limpar tudo" in peca and "zf-badge" in peca


def test_a_leitura_do_banco_em_fundo_nao_tira_o_excel_que_chegou_no_meio(tmp_path):
    """12/11/2026, o 1º uso do Levi ("usei o subir excel, não prestou nada!"): o BD_Thopen em Excel entrou enquanto o banco
    era lido em fundo, e a leitura do banco, terminando depois, o tirou ("BD_Thopen não foi lido" ao converter)."""
    import threading
    p = _bd_excel(tmp_path)
    pg._GUARDA.clear()
    solta = threading.Event()

    class BancoLento(BancoDeMentira):
        def livros(self):
            solta.wait(10)                         # o banco responde só depois de o Excel entrar
            return super().livros()

    s = servico.SessaoNexus(lambda: BancoLento(p, com_mapa=False), str(tmp_path / "sessao"), str(tmp_path / "novos"))
    try:
        s.iniciar()
        lote = s.novo_lote()
        with open(p, "rb") as f:
            s.receber(lote, "BD_Performance · meu.xlsx", io.BytesIO(f.read()))
        s.lote_pronto(lote, ["BD_Performance · meu.xlsx"])
        assert s.origem_bd["BD_Performance"] == "arquivo"
        solta.set()
        assert s.pronto.wait(10)
        b = {x["destino"]: x for x in s.estado_bds()}["BD_Performance"]
        assert b["lido"] and b["origem"] == "arquivo" and not b["erro"]   # o Excel ficou
        assert s.bds["BD_Performance"].aba("Teste") is not None
        s.limpar()                                                       # o Limpar volta ao banco
        assert s.origem_bd.get("BD_Performance") is None and "mapa de fórmulas" in s.erros_bd["BD_Performance"]
    finally:
        s.fechar()
        pg._GUARDA.clear()


def test_a_tela_aberta_antes_do_mapa_le_o_banco_quando_ele_chega(tmp_path):
    """16/11/2026, o dia em que o mapa de fórmulas passou a subir: a sessão aberta antes dele seguia pedindo o Excel (a
    leitura que falhou nunca era refeita). Agora o estado confere o banco no máximo a cada minuto e nunca no meio de uma
    conversão; o Excel solto não sai por aqui."""
    p = _bd_excel(tmp_path)
    pg._GUARDA.clear()
    banco = {"agora": BancoDeMentira(p, com_mapa=False)}
    s = servico.SessaoNexus(lambda: banco["agora"], str(tmp_path / "sessao"), str(tmp_path / "novos"))
    try:
        s.iniciar()
        assert s.pronto.wait(10)
        perf = lambda: {x["destino"]: x for x in s.estado()["bds"]}["BD_Performance"]   # noqa: E731
        assert not perf()["lido"] and "mapa de fórmulas" in perf()["erro"]
        banco["agora"] = BancoDeMentira(p)                       # o mapa chegou ao banco
        assert not perf()["lido"]                                # antes de um minuto, não confere de novo
        s._conferido -= servico.RELER_S
        s._convertendo.set()
        assert not perf()["lido"]                                # no meio de uma conversão, também não
        s._convertendo.clear()
        assert perf()["lido"] and perf()["origem"] == "banco" and not perf()["erro"]
        assert s.bds["BD_Performance"].aba("Teste") is not None
    finally:
        s.fechar()
        pg._GUARDA.clear()


# ── a aba "Para coletar" do Conversor 1.0.10 (13/11/2026): onde buscar no portal e a ronda ──────────────────────────
_CAB_EQ = ["", "Cliente", "Usina", "Usina Supervisório", "Usina Fractall", "Equipamento", "Equipamento Supervisório",
           "Equipamento Parente"]


def _com_equipamentos(banco):
    """A aba Equipamentos do BD_Performance como o banco devolve: cabeçalho na linha 3, dados a partir da 4."""
    linhas = [[None, "Thopen", "Ceilândia 2", "Ceilandia II - Pitangueira (94)", None, "UFV", None, None],
              [None, "Thopen", "Ceilândia 2", "Ceilandia II - Pitangueira (94)", None, "Inversor 2.1", "INVERSOR - 1", "UFV"],
              [None, "Thopen", "Ceilândia 2", "Ceilandia II - Pitangueira (94)", None, "Inversor 2.2", "INVERSOR - 2", "UFV"],
              [None, "Sunpower", "Cascavel (Sunpower)", "SunPower UFV 6 (12)", None, "Inversor 6,2", "INV 6.2", "UFV"],
              [None, "Thopen", "Sem planta", None, None, "Inversor 1.1", "X", "UFV"]]
    banco.sheets["bd_performance"]["Equipamentos"] = {"id": 900, "sheet_name": "Equipamentos", "header_row": 3}
    banco.rows[900] = [{"row_number": i + 4, "headers": _CAB_EQ, "values": v} for i, v in enumerate(linhas)]
    return banco


def test_onde_buscar_no_portal_sai_da_aba_equipamentos_do_banco(coletas, app, tmp_path):
    p = _bd_excel(tmp_path)
    app.config["NEXUS_COLETAS_BANCO"] = lambda: _com_equipamentos(BancoDeMentira(p))
    servico._PORTAL.clear()
    m = coletas.get("/t/performance/coletas/furos/portal").get_json()
    assert m["Ceilândia 2"] == {"plantas": ["Ceilandia II - Pitangueira"],
                                "inv": {"Inversor 2.1": ["Ceilandia II - Pitangueira", "INVERSOR - 1"],
                                        "Inversor 2.2": ["Ceilandia II - Pitangueira", "INVERSOR - 2"]}}
    assert m["Cascavel (Sunpower)"]["inv"] == {"Inversor 6.2": ["SunPower UFV 6", "INV 6.2"]}   # "6,2" = "6.2"
    assert "Sem planta" not in m                                                 # sem a planta do supervisório não entra
    servico._PORTAL.clear()


def test_a_leitura_do_portal_e_a_mesma_do_exe(tmp_path):
    """O Excel com a aba Equipamentos: o furos.portal do .exe e a leitura do banco dão o mesmo mapa."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Equipamentos"
    ws.append([])
    ws.append([])
    ws.append(_CAB_EQ)
    for v in _com_equipamentos(BancoDeMentira(_bd_excel(tmp_path))).rows[900]:
        ws.append(v["values"])
    x = tmp_path / "BD_Performance_eq.xlsx"
    wb.save(x)
    linhas = [_CAB_EQ] + [v["values"] for v in _com_equipamentos(BancoDeMentira(_bd_excel(tmp_path))).rows[900]]
    assert servico.portal_de_linhas(linhas) == servico._furos.portal(str(x))


def test_a_ronda_e_o_portal_passam_pelo_nexus(coletas):
    html = coletas.get("/t/performance/coletas/app").get_data(as_text=True)
    assert "furos_gravar_ronda(x)" in html and 'NX_BASE + "/furos/portal"' in html and "CHAVE_RONDA" in html
    furos = open(os.path.join(RAIZ, "nexus", "static", "coletas", "furos.js"), encoding="utf-8").read()
    assert 'data-t="col"' in html and "api().furos_portal()" in furos


# ── a aba "Baixa performance" do Conversor 1.0.11 (13/11/2026): o mural com os VALORES do banco ────────────────────
SEM_PARADAS = {"dia": {}, "abertas": {}, "erro": None, "lido": "13/11 10:00"}


@pytest.fixture(autouse=True)
def _paradas_sem_rede(monkeypatch):
    """As paradas do COS (1.0.13) vêm do db_performace pela rede: no teste, dubladas."""
    monkeypatch.setattr(servico._paradas, "carregar", lambda forcar=False: SEM_PARADAS)


def _bd_mural(tmp_path):
    """Uma usina com 4 inversores em novembro: o 1.4 gera metade dos outros nos dias 3 e 4; o 1.1 tem metade da potência."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Usina X"
    ws.append(["Data", "Inversor 1.1", "Inversor 1.2", "Inversor 1.3", "Inversor 1.4"])
    for d in range(1, 8):
        baixo = d in (3, 4)
        ws.append([dt.datetime(2026, 11, d), 50.0, 100.0, 100.0, 40.0 if baixo else 100.0])
    eq = wb.create_sheet("Equipamentos")
    eq.append(["Cliente", "Usina", "Usina Supervisório", "Equipamento", "Equipamento Supervisório", "Potência (kWp)"])
    for i, k in ((1, 50), (2, 100), (3, 100), (4, 100)):
        eq.append(["X", "Usina X", "Planta X (7)", "Inversor 1.%d" % i, "INV-%d" % i, k])
    p = tmp_path / "BD_Performance_mural.xlsx"
    wb.save(p)
    return p


def test_o_mural_do_banco_e_o_mesmo_do_exe(tmp_path):
    from conversor import mural
    p = _bd_mural(tmp_path)
    hoje = dt.date(2026, 11, 8)
    mural._CACHE.clear()
    exe = mural.mural({"BD_Performance": BD("BD_Performance", str(p))}, str(p), "2026-11", hoje=hoje,
                      paradas_dados=SEM_PARADAS)

    class S:
        origem_bd, bds, caminhos_bd = {}, {}, {}
    servico._MURAL.clear()
    servico._PORTAL.clear()
    banco = BancoDeMentira(p, com_mapa=False)
    nx = servico.furos_mural(S(), lambda: banco, "2026-11", hoje=hoje)
    assert nx == exe                                     # sem o mapa de fórmulas: ler não precisa dele
    assert [(x["inversor"], x["base"], [d[0] for d in x["dias"]]) for x in nx["linhas"]] == \
        [("Inversor 1.4", "kWh/kWp", ["2026-11-03", "2026-11-04"])]       # o 1.1 menor não é defeito (kWh/kWp)
    lidas = banco.pedidos
    assert servico.furos_mural(S(), lambda: banco, "2026-11", hoje=hoje) is nx   # guardado pela subida:
    assert banco.pedidos == lidas                                                # não lê as abas de novo
    assert "erro" in servico.furos_mural(S(), None, "11/2026")
    servico._MURAL.clear()
    servico._PORTAL.clear()


def test_o_mural_passa_pela_api_da_tela(coletas):
    servico._MURAL.clear()
    r = coletas.post("/t/performance/coletas/api/furos_mural", json={"args": ["2026-10"]}).get_json()
    assert "linhas" in r and r["ini"] == "2026-10-01"
    assert "erro" in coletas.post("/t/performance/coletas/api/furos_mural", json={"args": ["x"]}).get_json()
    furos = open(os.path.join(RAIZ, "nexus", "static", "coletas", "furos.js"), encoding="utf-8").read()
    assert 's = vs("fzSrc"), c = vs("fzCli"), ca = vs("fzCart")' in furos      # o mural lê os filtros de vários valores
    servico._MURAL.clear()


def test_a_parada_do_cos_explica_o_dia_baixo_no_mural(tmp_path, monkeypatch):
    """1.0.13: a OS aberta no inversor explica o dia baixo, pela regra do .exe (paradas.explicar)."""
    from conversor import mural
    p = _bd_mural(tmp_path)
    hoje = dt.date(2026, 11, 8)
    com_os = {"dia": {}, "abertas": {"Usina X": [{"os": "123", "tipo": "Corretiva", "escopo": "Inversor 1.4",
                                                   "inicio": "2026-11-02"}]}, "erro": None, "lido": "13/11 10:00"}
    monkeypatch.setattr(servico._paradas, "carregar", lambda forcar=False: com_os)

    class S:
        origem_bd, bds, caminhos_bd = {}, {}, {}
    servico._MURAL.clear()
    servico._PORTAL.clear()
    mural._CACHE.clear()
    nx = servico.furos_mural(S(), lambda: BancoDeMentira(p, com_mapa=False), "2026-11", hoje=hoje)
    exe = mural.mural({"BD_Performance": BD("BD_Performance", str(p))}, str(p), "2026-11", hoje=hoje,
                      paradas_dados=com_os)
    assert nx == exe and nx["paradas"] is True
    (x,) = nx["linhas"]
    assert x["n_expl"] == 2 and x["n_sem"] == 0                  # os dois dias baixos explicados pela OS aberta
    servico._MURAL.clear()
    servico._PORTAL.clear()
    mural._CACHE.clear()


def test_as_paradas_passam_pela_api_da_tela(coletas):
    r = coletas.post("/t/performance/coletas/api/furos_paradas", json={"args": []}).get_json()
    assert r == SEM_PARADAS


# ── a recoleta pela fonte (Conversor 1.0.14), ligada no Nexus em 17/11/2026 por permissão ─────────────────────────
def _plataforma_dublada(monkeypatch):
    """A rota da plataforma (/api/recoleta/apipv) dublada: nada sai para a rede. -> a lista dos pedidos feitos."""
    pedidos = []

    def pedir(rota, chave_, corpo=None, timeout=180):
        pedidos.append((rota, chave_, corpo))
        if rota.endswith("/plantas"):
            return {"plantas": [{"id": 7, "nome": "Planta Teste (7)", "cadastro": "Teste"}], "max_dias": 7,
                    "restam_hoje": 150, "teto_dia": 150}
        return {"plantas": {"7": {"dias": {"2026-10-14": {"ger": {"INV A": 1500.0, "INV B": 1400.0}, "ipoa": 6.1,
                                                          "ghi": 5.0}}}}, "chamadas": 2, "restam": 148}
    monkeypatch.setattr(servico._recoleta, "_pedir", pedir)
    return pedidos


def _banco_com_a_planta(p):
    """O banco de mentira com a aba Equipamentos dizendo onde a usina Teste está na fonte."""
    b = BancoDeMentira(p)
    linhas = [[None, "Cliente", "Teste", "Planta Teste (7)", None, "UFV", None, None],
              [None, "Cliente", "Teste", "Planta Teste (7)", None, "Inversor 1.1", "INV A", "UFV"],
              [None, "Cliente", "Teste", "Planta Teste (7)", None, "Inversor 1.2", "INV B", "UFV"]]
    b.sheets["bd_performance"]["Equipamentos"] = {"id": 900, "sheet_name": "Equipamentos", "header_row": 3}
    b.rows[900] = [{"row_number": i + 4, "headers": _CAB_EQ, "values": v} for i, v in enumerate(linhas)]
    return b


def _api(c, metodo, *args):
    return c.post("/t/performance/coletas/api/" + metodo, json={"args": list(args)})


def test_a_recoleta_busca_na_fonte_e_sai_pela_mesma_montagem(coletas, app, tmp_path, monkeypatch):
    """Levi (17/11/2026): "quero formas de coletar os dados novamente pelas nossas fontes de dados e gerar uma planilha
    para colar nos BDs". A usina sai da aba Equipamentos do banco, o dado da plataforma (dublada) e o resultado é a
    conversão de sempre: célula vazia recebe, a planilha baixa pelo índice, nada grava no BD."""
    p = _bd_excel(tmp_path)
    app.config.update(NEXUS_COLETAS_BANCO=lambda: _banco_com_a_planta(p), CONVERSOR_RECOLETA_CHAVE="chave-de-teste")
    servico._PORTAL.clear()
    pedidos = _plataforma_dublada(monkeypatch)
    assert '<button class="btn2" id="rcAbrir">Recoletar pela API</button>' in coletas.get("/t/performance/coletas/app").get_data(as_text=True)
    for _ in range(50):
        if _api(coletas, "estado").get_json()["bd_pronto"]:
            break
        time.sleep(0.1)
    op = _api(coletas, "recoleta_opcoes").get_json()
    assert op["usinas"] == [{"usina": "Teste", "destino": "BD_Performance", "plantas": ["Planta Teste"], "n_inv": 2}]
    assert op["restam_hoje"] == 150 and pedidos[0][:2] == ("/api/recoleta/apipv/plantas", "chave-de-teste")
    assert _api(coletas, "recoleta_fatias", "2026-10-14", "2026-10-14").get_json() == [["2026-10-14", "2026-10-14"]]
    parte = _api(coletas, "recoleta_parte", "Teste", "2026-10-14", "2026-10-14", True, True, True).get_json()
    assert parte == {"ok": True, "chamadas": 2, "restam": 148}
    assert pedidos[-1][2] == {"ids": [7], "ini": "2026-10-14", "fim": "2026-10-14", "geracao": True, "etm": True}
    res = _api(coletas, "recoleta_montar", "Teste", True, True).get_json()
    assert not res.get("erro") and res["origem"] == "recoleta" and res["recoleta"] == {"usina": "Teste", "celulas": 4}
    assert res["totais"]["novo"] >= 3 and res["pasta"] == ""
    assert res["saidas"] and res["saidas"][0]["indice"] == 0 and os.sep not in res["saidas"][0]["caminho"]
    assert any("veio do banco" in a["texto"] for a in res["avisos"])
    assert coletas.get("/t/performance/coletas/planilha/0").status_code == 200


def test_a_recoleta_so_abre_para_quem_tem_a_tela_dela(coletas, app, monkeypatch):
    """A recoleta gasta cota paga (a da API PV é dividida com a coleta da noite): ter a Coletas não basta. Sem a tela
    "Recoleta pelas fontes" o botão sai escondido, as rotas recusam e nada chega à plataforma."""
    from nexus.auth import setor_telas
    app.config["CONVERSOR_RECOLETA_CHAVE"] = "chave-de-teste"
    servico._PORTAL.clear()
    pedidos = _plataforma_dublada(monkeypatch)
    telas = {"performance/coletas"}
    monkeypatch.setattr(setor_telas, "acesso", lambda: {"tudo": False, "telas": telas, "setor": None, "erro": ""})
    assert '<button class="btn2" id="rcAbrir" hidden>' in coletas.get("/t/performance/coletas/app").get_data(as_text=True)
    for m in ("recoleta_opcoes", "recoleta_fatias", "recoleta_parte", "recoleta_montar"):
        r = _api(coletas, m, "Teste", "2026-10-14", "2026-10-14", True, True)
        assert r.status_code == 403 and "Base > Acessos" in r.get_json()["erro"]
    assert pedidos == []
    telas.add("performance/coletas/recoleta")
    assert '<button class="btn2" id="rcAbrir">' in coletas.get("/t/performance/coletas/app").get_data(as_text=True)
    assert _api(coletas, "recoleta_opcoes").status_code == 200 and pedidos


def test_a_tela_da_recoleta_mora_dentro_da_coletas(app):
    from nexus.torres.performance import TORRE
    t = TORRE.tela("coletas/recoleta")
    assert t.nome == "Recoleta pelas fontes" and t.dentro_de == "coletas"


def test_a_chave_da_recoleta_sai_do_ambiente_do_nexus_sem_nada_no_git():
    import hashlib
    import hmac
    sso = "s" * 40
    esperado = hmac.new(sso.encode(), servico.ROTULO_RECOLETA, hashlib.sha256).hexdigest()
    assert servico.chave_recoleta({"NEXUS_SSO_CHAVE": sso}) == esperado and len(esperado) == 64
    assert servico.chave_recoleta({"NEXUS_SSO_CHAVE": sso, "CONVERSOR_RECOLETA_CHAVE": " posta pela TI "}) == "posta pela TI"
    assert servico.chave_recoleta({}) == ""


def test_sem_chave_a_recoleta_diz_o_motivo_e_nao_pede_nada(coletas, app, monkeypatch):
    servico._PORTAL.clear()
    pedidos = _plataforma_dublada(monkeypatch)
    monkeypatch.delenv("CONVERSOR_RECOLETA_CHAVE", raising=False)
    app.config.pop("CONVERSOR_RECOLETA_CHAVE", None)
    app.config["NEXUS_SSO_CHAVE"] = ""
    assert "chave da recoleta" in _api(coletas, "recoleta_opcoes").get_json()["erro"] and pedidos == []


def test_a_sala_de_controle_le_o_abaixo_dos_demais_daqui(coletas, app):
    """A Sala de controle da Performance (a tela é da plataforma) lê o "abaixo dos demais" do dono da conta: a mesma do
    mural da Coletas, só com os BDs do banco. Abre para quem tem a tela dela, sem depender de ter a Coletas (16/11/2026)."""
    from nexus.auth import setor_telas
    servico._MURAL.clear()
    r = coletas.get("/t/performance/sala-de-controle/abaixo?mes=2026-10")
    assert r.status_code == 200
    d = r.get_json()
    assert "linhas" in d and d["ini"] == "2026-10-01" and d["limiar"] == servico._mural.LIMIAR
    assert coletas.get("/t/performance/sala-de-controle/abaixo?mes=x").status_code == 400
    with app.test_request_context():
        assert setor_telas.pode("/t/performance/sala-de-controle/abaixo", {"performance/sala-de-controle"})
        assert not setor_telas.pode("/t/performance/sala-de-controle/abaixo", {"performance/coletas"})
    servico._MURAL.clear()
