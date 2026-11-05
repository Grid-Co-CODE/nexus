"""A Central da usina (Levi, 04/11/2026: "Como temos uma visão para os supervisores em Central do Responsável podemos ter
como pesquisar a usina e ter uma central de informações daquela usina, performance, disponibilidade, sujidade,
pendências, chamados, PTs etc"; "inclua junto da central dos responsáveis, como aba alternativa"). Decisões dele: a aba
na Visão do responsável, o mês corrente, as quatro pendências (rondas, OS atrasadas e pausadas, ocorrências abertas,
Segurança) e todas as usinas na busca. Banco falso do test_campo_responsaveis (a Altair, a Brodowski 1 e a Coração 1)."""
import re
from datetime import timedelta
from pathlib import Path

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
    # o responsável, o cliente e a busca da lista não valem na Central
    assert 'id="cr-responsavel"' not in html and 'id="cr-cliente"' not in html


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
    assert 'data-folio="16034"' in html
    # PT: as duas que esperam o De acordo (na janela do número da PT)
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


# ── 3ª rodada (05/11/2026), os nove pedidos do Levi sobre a Central da usina ─────────────────────────────────────────
CSS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "campo.css"
BUSCA = Path(__file__).resolve().parents[1] / "nexus" / "torres" / "campo" / "templates" / "campo" / "_busca_usina.html"


def _quadro(html, ident):
    return html.split(f'id="{ident}"', 1)[1].split("</section>", 1)[0]


def test_os_numeros_em_linhas_alinhadas_o_nome_em_cima_e_o_valor_embaixo_no_meio(tela, logado):
    """"Nesses KPIS quero campos separados por linhas invisíveis separando cabeçalho e valor / quero que centralize
    horizontal e verticalmente": cada número ocupa três linhas da faixa (o nome, o valor, o complemento), as MESMAS
    linhas em todos (a subgrade), e cada pedaço fica no meio da casa dele."""
    css = CSS.read_text(encoding="utf-8")
    regra = re.search(r"\.cn-numeros\.cu-numeros > \*\{([^}]*)\}", css).group(1)
    assert "grid-row:span 3" in regra and "grid-template-rows:subgrid" in regra
    assert "place-items:center" in regra and "text-align:center" in regra
    faixa = _central(logado, "&usina=1").split('<div class="cn-numeros cu-numeros">', 1)[1].split("</div>", 1)[0]
    for rot in ("Meta do mês", "PR", "Disponibilidade", "Limpeza", "Ronda", "Chamados", "PT", "OS atrasadas"):
        assert f'<span class="d">{rot}</span><b class="v' in faixa, rot


def test_a_exclamacao_amarela_ao_lado_do_titulo_leva_a_leitura_e_as_reguas(tela, logado):
    """"Os avisos do anexo 2 não precisam aparecer, pode ficar nos disclaimers" (a caixa "Gerencial, Confiabilidade (...)
    lido às" do canto) e "A exclamação tem que ficar ao lado do título e tem que ter o destaque em amarelo conforme
    segurança > extintores": o cabeçalho de todas as abas da Visão fica só com o título e o "!" do padrão do Nexus
    (`_explica.html`, o mesmo dia), que leva também a hora da leitura."""
    for args in ("modo=usina", "modo=usina&usina=1", "responsavel=*&modo=geral", "responsavel=*&modo=cartoes",
                 "modo=ranking", "modo=painel&responsavel=*"):
        html = logado.get("/t/campo/responsaveis?" + args).get_data(as_text=True)
        assert 'class="cn-frescor"' not in html and '<details class="cr-info">' not in html, args
        cab = html.split('<div class="gc-titulo-explica"><h1 class="cn-titulo">', 1)[1].split("</details>", 1)[0]
        assert ('<details class="gc-explica"><summary class="gc-explica-bt" '
                'title="De onde vem cada número e a régua de cada alerta"') in cab, args
        assert "<b>Lido às " in cab and "pelo banco do Nexus" in cab, args
        for _b, _a, regua, texto in R.REGUAS:
            assert f"<dt>{regua}</dt>" in cab and texto[:30] in cab, (args, regua)


def test_sem_usina_escolhida_so_o_campo_de_busca(tela, logado):
    """"Quando não tem nenhum usina não precisa amontoar um monte de card de usinas, deixa só a parte de pesquisar
    mesmo!": a lista abre no foco, por cima, como nas Rondas (a lista aberta em grade da 2ª rodada saiu)."""
    html = _central(logado)
    assert 'id="rd-us-1"' in html                                 # as usinas seguem na busca, para filtrar
    assert 'role="listbox" aria-label="Usinas" hidden>' in html
    assert "rd-usinas--aberta" not in html and "data-rd-aberta" not in html
    assert "busca_aberta" not in BUSCA.read_text(encoding="utf-8")


def test_a_busca_fica_a_direita_na_linha_das_abas(tela, logado):
    """"Quero o 'Buscar usinas' do lado direito paralelizando com os botões a visão dos responsáveis!"."""
    for args in ("", "&usina=1"):
        html = _central(logado, args)
        topo = html.split('<div class="cu-topo">', 1)[1]
        assert topo.index('class="cn-seg"') < topo.index("data-rd-usina"), args
        assert html.index('<div class="cu-topo">') < html.index('class="cn-seg"'), args
        if args:
            assert topo.index("data-rd-usina") < topo.index('class="cu-cab"'), args
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r"\.cu-topo\{[^}]*display:flex[^}]*justify-content:space-between", css)
    # nas outras abas, a busca da usina não aparece
    assert "data-rd-usina" not in logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)


def test_o_relatorio_pergunta_o_mes_primeiro(tela, logado):
    """"Quando clicar em baixar relatórios: escolher qual o mês!": a janela abre com os meses em botões (o anterior
    marcado), antes dos temas."""
    from nexus.campo import relatorio_usina as RU
    html = _central(logado, "&usina=1")
    jan = html.split('<template id="cu-rel-temas">', 1)[1].split("</template>", 1)[0]
    assert '<fieldset class="cu-rel-meses">' in jan and "<legend" in jan and "Qual mês?" in jan
    for m, _rot in RU.meses(HOJE):
        marcado = " checked" if m == RU.mes_padrao(HOJE) else ""
        assert f'<input type="radio" name="mes" value="{m}"{marcado}>' in jan, m
    assert jan.index("cu-rel-meses") < jan.index("pn-rel-temas")
    assert "<select" not in jan


def test_a_performance_traz_o_grafico_da_geracao(tela, logado):
    """"Quero que o gráfico de geração também apareça na visão do responsável > central da usina": o mesmo gráfico da
    janela do PR (a geração do dia que o Gerencial conta, a meta e o POA), dentro do quadro da Performance."""
    perf = _quadro(_central(logado, "&usina=1"), "cu-perf")
    assert "Geração diária (MWh) e POA (kWh/m²)" in perf and 'class="cr-svg"' in perf
    assert perf.count('class="cr-barra cr-barra--') == 2              # os dois dias com geração (o 3º só tem PR)
    # a janela do PR desenha o mesmo gráfico, da mesma macro
    jan = logado.get("/t/campo/responsaveis/usina/1/pr").get_data(as_text=True)
    assert jan.count('class="cr-barra cr-barra--') == 2
    assert "{% macro geracao(g) %}" in (BUSCA.parent / "_graficos.html").read_text(encoding="utf-8")
    # sem a série do dia a dia no banco, o quadro fica sem o gráfico (a Brodowski 1)
    assert 'class="cr-svg"' not in _quadro(_central(logado, "&usina=2"), "cu-perf")


def test_os_chamados_so_mostram_a_linha_que_tem_chamado(tela, banco, logado):
    """"SE NÃO TIVER VERIFICAÇÃO OU CONCLUSÃO NÃO PRECISA APARECER NA TELA": a linha sem chamado sai (a dos abertos
    também, pela mesma regra); sem nenhum, uma frase só."""
    ch = _quadro(_central(logado, "&usina=1"), "cu-ch")
    assert "Abertos" in ch and "Em verificação" not in ch and "Finalizados no mês" not in ch
    d = HOJE.replace(day=1)
    _aba(banco, "nexus_chamados", "fato_chamado", [
        dict(_chamado(17001, 1, "concluido", 30), data_id_fim=d.year * 10000 + d.month * 100 + d.day),
        _chamado(17005, 1, "verificacao", 3), _chamado(16050, 3, "aberto", 2)])
    visao.limpar()
    ch = _quadro(_central(logado, "&usina=1"), "cu-ch")
    assert "Abertos" not in ch and "Em verificação" in ch and "Finalizados no mês" in ch
    assert "Abertos" in _quadro(_central(logado, "&usina=3"), "cu-ch")
    ch = _quadro(_central(logado, "&usina=2"), "cu-ch")
    assert "Nenhum chamado aberto, em verificação ou finalizado no mês." in ch and "<dt" not in ch


def test_o_numero_da_pt_abre_a_lista_do_painel_e_o_quadro_da_pt_sai(tela, logado):
    """"o KPI de PT já tem a informação, ao clicar no KPI aparece o mesmo card que aparece em visão do responsável >
    painel": o número da PT abre na janela a lista do Painel (as PT esperando o De acordo, a parada de hoje primeiro),
    cada uma abrindo a decisão; o quadro PT da página saiu."""
    html = _central(logado, "&usina=1")
    assert 'id="cu-pt"' not in html and "Pedidas no mês" not in html
    faixa = html.split('<div class="cn-numeros cu-numeros">', 1)[1].split("</div>", 1)[0]
    assert re.search(r'<button type="button" data-cu-pts aria-haspopup="dialog"[^>]*><span class="d">PT</span>', faixa)
    lista = html.split('<template id="cu-pts-lista">', 1)[1].split("</template>", 1)[0]
    assert '<ol class="pn-lista pn-lista--jan"' in lista and "PTs pendentes" in lista and "<h2>Altair</h2>" in lista
    assert lista.count('class="pn-it cr-abre" data-cr-painel="/t/campo/responsaveis/pt/') == 2
    # o mesmo desenho da lista do Painel (a mesma macro)
    painel = logado.get("/t/campo/responsaveis?modo=painel&responsavel=*").get_data(as_text=True)
    pl = painel.split('<template id="pn-pts-lista">', 1)[1].split("</template>", 1)[0]
    assert '<ol class="pn-lista pn-lista--jan"' in pl and pl.count('class="pn-it cr-abre"') >= 2
    assert "querySelector('[data-cu-pts]')" in html and "getElementById('cu-pts-lista')" in html
    # sem PT esperando, a lista diz que não há (a Coração 1)
    assert "Nenhuma PT esperando o De acordo." in _central(logado, "&usina=3").split('<template id="cu-pts-lista">', 1)[1]


def test_o_eixo_com_passo_quebrado_mostra_a_casa_decimal():
    """O eixo do POA de passo 2,5 (achado na 3ª rodada, no gráfico da Altair): as marcas 2,5 e 7,5 saíam "2" e "8" (o
    arredondamento de 0 casa); agora o eixo com alguma marca quebrada leva uma casa em todas."""
    from nexus.campo import responsaveis_graficos as G
    g = G.geracao([{"dia": 1, "geracao_kwh": 37000, "meta_kwh": 40000, "ipoa": 9.5, "ipoa_meta": 7.7}], 30)
    assert [m["rotulo"] for m in g["grades_dir"]] == ["0,0", "2,5", "5,0", "7,5", "10,0", "12,5"]
    assert [m["rotulo"] for m in g["grades"]] == ["0", "10", "20", "30", "40", "50"]      # o passo inteiro fica sem casa
