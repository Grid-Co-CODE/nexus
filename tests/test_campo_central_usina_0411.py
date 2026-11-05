"""A Central da usina (Levi, 04/11/2026: "Como temos uma visão para os supervisores em Central do Responsável podemos ter
como pesquisar a usina e ter uma central de informações daquela usina, performance, disponibilidade, sujidade,
pendências, chamados, PTs etc"; "inclua junto da central dos responsáveis, como aba alternativa"). Decisões dele: a aba
na Visão do responsável, o mês corrente, as quatro pendências (rondas, OS atrasadas e pausadas, ocorrências abertas,
Segurança) e todas as usinas na busca. Banco falso do test_campo_responsaveis (a Altair, a Brodowski 1 e a Coração 1)."""
from datetime import timedelta

from test_campo_responsaveis import HOJE, _chamado, _por_usina, tela  # noqa: F401  (tela é fixture)
from test_campo_visao import _aba, banco  # noqa: F401  (banco é fixture)

from nexus.campo import central_usina as CU
from nexus.campo import responsaveis as R
from nexus.campo import visao
from nexus.dados import fato_chamado as F


def _central(logado, args=""):
    return logado.get("/t/campo/responsaveis?modo=usina" + args).get_data(as_text=True)


def test_a_aba_fica_ao_lado_das_outras_e_busca_todas_as_usinas(tela, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert ">Central da usina</a>" in html and "modo=usina" in html
    html = _central(logado, "&responsavel=Ciclano+Chefe")
    # a busca traz TODAS as usinas da Visão, sem o filtro do responsável (decisão do Levi: as 131, para quem abre a tela)
    for uid in (1, 2, 3):
        assert f'id="rd-us-{uid}"' in html
    assert 'name="modo" value="usina"' in html
    # sem usina escolhida, a lista já aberta, em grade (2ª rodada: "Deixar a lista de 'buscar usina' já no estilo nexus")
    assert 'class="rd-usinas rd-usinas--aberta"' in html and "data-rd-aberta" in html and ">3 usinas<" in html
    # o responsável, o cliente e a busca da lista não valem na Central
    assert 'id="cr-responsavel"' not in html and 'id="cr-cliente"' not in html
    # com a usina escolhida, a lista volta a abrir só no foco (por cima)
    assert "rd-usinas--aberta" not in _central(logado, "&usina=1")


def test_a_usina_escolhida_traz_os_numeros_da_linha_dela_na_visao(tela, logado):
    html = _central(logado, "&usina=1")
    a = _por_usina()["Altair"]
    assert '<h2 class="cu-nome">Altair</h2>' in html
    # os números são os da linha da Altair na Visão (o mesmo do Painel e da Visão geral), e a meta abre o dia a dia
    for txt in (a["perf"]["valores"]["meta"]["txt"], a["perf"]["valores"]["disp"]["txt"]):
        assert txt in html
    assert "/t/campo/responsaveis/usina/1/meta" in html and "Performance do mês" in html
    # as pendências: a ronda longa pendente, e a seção de cada uma
    assert "Ronda longa pendente" in html and "Ocorrências" in html and "Segurança" in html
    # chamados: o aberto (16034) com o card da OS; o concluído sem fim no mês não entra nos finalizados
    assert 'data-folio="16034"' in html and "Finalizados no mês" in html
    # PT: as duas que esperam o De acordo
    assert html.count("/t/campo/responsaveis/pt/") >= 2


def test_sem_o_script_a_busca_acha_pelo_nome(tela, logado):
    assert '<h2 class="cu-nome">Coração 1</h2>' in _central(logado, "&nome=coracao")
    html = _central(logado, "&nome=nao+existe")
    assert 'Nenhuma usina com o nome "nao existe"' in html and "cu-nome" not in html


def test_os_chamados_finalizados_no_mes(tela, banco):
    d = HOJE.replace(day=1)
    fim = d.year * 10000 + d.month * 100 + d.day
    velho = HOJE.replace(day=1) - timedelta(days=1)
    _aba(banco, "nexus_chamados", "fato_chamado", [
        dict(_chamado(17001, 1, "concluido", 30), data_id_fim=fim),
        dict(_chamado(17002, 1, "concluido", 40), data_id_fim=velho.year * 10000 + velho.month * 100 + velho.day),
        dict(_chamado(17003, 2, "concluido", 10), data_id_fim=fim), _chamado(17004, 1, "aberto", 3)])
    visao.limpar()
    fin = R.chamados_finalizados(1, HOJE)
    assert [c["os"] for c in fin] == [17001]                      # o de outro mês e o de outra usina ficam de fora
    assert fin[0]["fim"] == d and fin[0]["dias"] == 30 - (HOJE - d).days
    assert set(F.CAB_CHAMADO) >= {"data_id_fim", "situacao"}


def test_as_pendencias_da_seguranca_sao_as_da_mesa_so_da_usina():
    listas = {"vencidos": [{"usina_id": 1, "ext": "EXT01", "vence": "2026-10-01", "vence_qual": "recarga",
                            "local": "Cabine", "posicao": ""}, {"usina_id": 2, "ext": "EXT09"}],
              "pts": [{"usina_id": 1, "os": "18000", "numero": "PT-1", "codigo": "C1", "tarefa": "Troca de string"}],
              "sem_luvas": [{"usina_id": 1, "desde": "2026-10-28"}]}
    s = CU.seguranca(1, listas)
    assert [g["rot"] for g in s] == ["PT parada", "Extintor vencido", "Sem luvas"]   # a ordem da Mesa
    assert s[1]["itens"] == [{"forte": "Extintor EXT01", "txt": "(Cabine) recarga venceu em 01/10"}]
    assert s[0]["itens"][0]["pt"]["numero"] == "PT-1" and s[2]["itens"][0]["txt"] == "desde 28/10"
    assert CU.seguranca(3, listas) == []


def test_a_visao_conta_os_extintores_como_a_seguranca(tela, monkeypatch):
    """O extintor que a Segurança excluiu ou corrigiu (`decisoes.separar`) sai da conta da Visão também: antes, a Visão
    contava o livro do App cru e a Mesa, o HSEQ e o Comando, sem ele (achado da Central da usina, 04/11/2026)."""
    from nexus.hseq import decisoes as DEC

    def separar(ext, nr, est):
        return ([x for x in ext if x["codigo"] != "ALT100-EXT01"], nr,
                [x for x in ext if x["codigo"] == "ALT100-EXT01"])
    monkeypatch.setattr(DEC, "separar", separar)
    visao.limpar()
    a = _por_usina()["Altair"]
    assert (a["extintores"]["total"], a["extintores"]["vencidos"]) == (1, 0)


def test_as_pt_do_mes_sao_as_pedidas_no_mes_em_brasilia():
    from datetime import datetime, timezone
    hoje = HOJE
    no_mes = datetime(hoje.year, hoje.month, 1, 12, tzinfo=timezone.utc)
    # 1º do mês às 01:30 UTC é o último dia do mês anterior em Brasília
    virada = datetime(hoje.year, hoje.month, 1, 1, 30, tzinfo=timezone.utc)
    hist = [{"usina_id": 1, "numero": "A", "criada": no_mes}, {"usina_id": 1, "numero": "B", "criada": virada},
            {"usina_id": 2, "numero": "C", "criada": no_mes}]
    out = CU.pts_do_mes(1, hist, hoje)
    assert [p["numero"] for p in out] == ["A"] and out[0]["dia_txt"] == f"01/{hoje.month:02d}"


# ── o relatório da usina para o cliente (2ª rodada, 04/11/2026: "é interessante que dê para baixar um relatório da usina
# também! Algo bem profissional para o cliente!"; o mês escolhido, o anterior de início; os temas como no Painel) ──────
def test_os_meses_do_relatorio_e_o_padrao_o_anterior():
    from datetime import date

    from nexus.campo import relatorio_usina as RU
    hoje = date(2026, 1, 15)
    assert RU.meses(hoje) == [("2026-01", "Janeiro de 2026"), ("2025-12", "Dezembro de 2025"),
                              ("2025-11", "Novembro de 2025")]
    assert RU.mes_padrao(hoje) == "2025-12"                       # o mês fechado anterior
    assert RU.mes_do_pedido("2025-11", hoje) == "2025-11" and RU.mes_do_pedido("2025-10", hoje) == "2025-12"
    assert RU.temas_do_pedido(["rondas", "x"]) == ("rondas",) and RU.temas_do_pedido([]) == RU.CHAVES_TEMAS


def test_a_central_tem_o_botao_e_a_janela_do_relatorio(tela, logado):
    html = _central(logado, "&usina=1")
    assert "data-cu-rel" in html and 'id="cu-rel-temas"' in html
    assert "/t/campo/responsaveis/usina/1/relatorio.pdf" in html
    from nexus.campo import relatorio_usina as RU
    for k, rot in RU.TEMAS:                                       # os quatro temas, todos marcados
        assert f'value="{k}" checked> {rot}' in html
    # PT, Segurança e técnicos ficam de fora do relatório do cliente (são internos)
    assert "PT, Segurança e nomes de técnicos não entram" in html


def test_o_relatorio_sai_em_pdf_com_os_temas_escolhidos(tela, logado):
    r = logado.get(f"/t/campo/responsaveis/usina/1/relatorio.pdf?mes={HOJE.strftime('%Y-%m')}")
    assert r.status_code == 200 and r.mimetype == "application/pdf" and r.data[:5] == b"%PDF-"
    assert "Altair" in r.headers["Content-Disposition"].replace("%20", " ")
    assert logado.get("/t/campo/responsaveis/usina/999/relatorio.pdf").status_code == 404
    import pytest
    fitz = pytest.importorskip("fitz")
    texto = "".join(p.get_text() for p in fitz.open(stream=r.data, filetype="pdf"))
    for t in ("Altair", "Performance e disponibilidade", "Rondas e limpeza", "Manutenção", "Chamados de garantia",
              "Resumo do mês", "85%"):
        assert t in texto, t
    # só os temas marcados
    r = logado.get(f"/t/campo/responsaveis/usina/1/relatorio.pdf?mes={HOJE.strftime('%Y-%m')}&tema=chamados")
    texto = "".join(p.get_text() for p in fitz.open(stream=r.data, filetype="pdf"))
    assert "Chamados de garantia" in texto and "Performance e disponibilidade" not in texto and "Rondas e limpeza" not in texto
    # o chamado aberto da Altair no mês (16034, aberto há 26 dias, conta no mês se abriu nele)
    assert "Em aberto em" in texto


def test_os_dados_do_relatorio_sao_os_das_telas_donas(tela):
    from nexus.campo import relatorio_usina as RU
    d = RU.dados(1, HOJE.strftime("%Y-%m"), HOJE)
    a = _por_usina()["Altair"]
    # a meta e a disponibilidade do mês são as da linha da Altair na Visão (o mesmo leitor)
    assert d["perf"]["meta"]["atingimento"] == a["meta"]["atingimento"] == 85.0
    assert d["perf"]["disp"]["disp"] == a["disp"]["disp"]
    assert d["chamados"]["em_aberto"] == a["chamados"]["abertos"] + a["chamados"]["verificacao"]
    assert not d["erros"]
