"""A Central da usina (Levi, 04/11/2026: "Como temos uma visão para os supervisores em Central do Responsável podemos ter
como pesquisar a usina e ter uma central de informações daquela usina, performance, disponibilidade, sujidade,
pendências, chamados, PTs etc"; "inclua junto da central dos responsáveis, como aba alternativa"). Decisões dele: a aba
na Visão do responsável, o mês corrente, as quatro pendências (rondas, OS atrasadas e pausadas, ocorrências abertas,
Segurança) e todas as usinas na busca. Banco falso do test_campo_responsaveis (a Altair, a Brodowski 1 e a Coração 1).

Desde 12/11/2026 a aba mostra o PRONTUÁRIO da usina, a página do Comando > Usinas (Levi: "essa visão irá substituir a
central da usina"; tests/test_comando_prontuario.py): a conta da Central (`_central_da_usina`, `central_usina.py`) segue
e alimenta o prontuário, e estes testes seguram o que é da aba (a busca, o relatório do cliente, a janela desta tela) e
o que a Central conta."""
import re
from datetime import timedelta
from pathlib import Path

from test_campo_responsaveis import HOJE, _chamado, _por_usina, tela  # noqa: F401  (tela é fixture)
from test_campo_visao import _aba, banco  # noqa: F401  (banco é fixture)

from nexus.campo import central_usina as CU
from nexus.campo import relatorio_usina as RU
from nexus.campo import responsaveis as R
from nexus.campo import visao
from nexus.dados import fato_chamado as F


def _central(logado, args=""):
    """O prontuário da usina: desde 16/11/2026 só no Comando > Usinas (Levi: "Tire a opção de prontuário da Visão do
    Responsável"; a aba saiu e o endereço dela leva para lá, tests/test_campo_prontuario_sai_da_visao_16_11.py)."""
    return logado.get("/t/comando/usinas/" + re.search(r"usina=(\d+)", args).group(1)).get_data(as_text=True)




def test_a_usina_escolhida_traz_os_numeros_da_linha_dela_na_visao(tela, logado):
    html = _central(logado, "&usina=1")
    a = _por_usina()["Altair"]
    assert '<h1 class="cu-nome cmu-nome">Altair ' in html                      # (no Comando > Usinas desde 16/11/2026)
    # os números são os da linha da Altair na Visão (o mesmo do Painel e da Visão geral), no painel do alto
    painel = html.split('class="pu-painel"', 1)[1].split('class="pu-faixa"', 1)[0]
    for txt in (a["perf"]["valores"]["meta"]["txt"], a["perf"]["valores"]["disp"]["txt"]):
        assert txt in painel
    assert "Performance do mês" in painel
    # as pendências: a ronda longa pendente, e o cartão de cada assunto
    assert "Ronda longa pendente" in html and "Segurança do trabalho" in html and "Chamados e garantias" in html
    # chamados: o aberto (16034) com o card da OS
    assert 'data-pu-os="16034"' in html
    # PT: as duas que esperam o De acordo abrem a página da PT (a janela era da aba, que saiu em 16/11/2026)
    assert html.count('href="/t/campo/pt/') >= 2




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
    assert "data-pu-rel" in html and 'id="pu-rel"' in html
    assert "/t/comando/usinas/1/relatorio.pdf" in html                          # o do Comando > Usinas
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


def test_os_campos_do_relatorio_e_o_pedido():
    """12/11/2026, Levi: "eu quero o relatório de forma profissional, que dê para editar os campos que eu quero que
    apareça": cada bloco do PDF é um campo; sem `campo` no pedido valem todos os dos temas (o endereço de antes)."""
    from nexus.campo import relatorio_usina as RU
    assert RU.campos_do_pedido([]) == RU.CHAVES_CAMPOS
    assert RU.campos_do_pedido([], ("perf",)) == ("resumo", "perf_numeros", "perf_grafico", "perf_dias", "perf_eventos")
    assert RU.campos_do_pedido(["rondas_lista", "perf_grafico", "lixo"]) == ("perf_grafico", "rondas_lista")   # na ordem do PDF
    # o campo de um tema que não foi pedido não esvazia o relatório: valem os campos do tema pedido
    assert RU.campos_do_pedido(["rondas_lista"], ("perf",)) == RU.campos_do_pedido([], ("perf",))
    grupos = RU.campos_por_tema()
    assert [t for t, _n, _c in grupos] == ["", "perf", "religamentos", "rondas", "manut", "chamados"]
    assert [k for _t, _n, cs in grupos for k, _r in cs] == list(RU.CHAVES_CAMPOS)
    assert {t for _k, t, _r in RU.CAMPOS} == {""} | set(RU.CHAVES_TEMAS)
    # o resumo só fala dos temas que têm campo ligado; só com o resumo, de todos
    assert RU.temas_dos_campos(RU.CHAVES_TEMAS, ("resumo", "perf_grafico", "chamados_abertos")) == ("perf", "chamados")
    assert RU.temas_dos_campos(RU.CHAVES_TEMAS, ("resumo",)) == RU.CHAVES_TEMAS


def test_o_relatorio_so_desenha_os_campos_escolhidos(tela, logado):
    import pytest
    fitz = pytest.importorskip("fitz")
    mes = HOJE.strftime("%Y-%m")

    def texto(q=""):
        r = logado.get(f"/t/campo/responsaveis/usina/1/relatorio.pdf?mes={mes}{q}")
        assert r.status_code == 200 and r.data[:5] == b"%PDF-"
        return "".join(p.get_text() for p in fitz.open(stream=r.data, filetype="pdf"))
    tudo = texto()
    for t in ("Resumo do mês", "Atingimento da meta", "Geração diária e meta", "Dia a dia",
              "Eventos que afetaram a disponibilidade", "Tarefas executadas no mês", "Ordens de serviço em aberto"):
        assert t in tudo, t
    # só o gráfico e os chamados em aberto: o resto não se desenha, e o tema sem campo ligado não abre seção
    so = texto("&campo=perf_grafico&campo=chamados_abertos")
    assert "Geração diária e meta" in so and "Em aberto em" in so
    for t in ("Resumo do mês", "Atingimento da meta", "Dia a dia", "Eventos que afetaram", "Tarefas executadas",
              "Rondas e limpeza", "Manutenção"):
        assert t not in so, t
    # o resumo ligado só fala dos temas com campo ligado: sem campo das Rondas, sem a frase das rondas
    res = texto("&campo=resumo&campo=perf_numeros")
    assert "Resumo do mês" in res and "A usina gerou" in res and "ronda" not in res.split("Fontes:", 1)[0].lower()
    # os números sozinhos ficam no alto e não abrem a seção da Performance
    num = texto("&campo=perf_numeros")
    assert "Atingimento da meta" in num and "Performance e disponibilidade" not in num and "Resumo do mês" not in num
    # pelo endereço do Comando, o mesmo PDF
    r = logado.get(f"/t/comando/usinas/1/relatorio.pdf?mes={mes}&campo=perf_numeros")
    assert "Performance e disponibilidade" not in "".join(p.get_text() for p in fitz.open(stream=r.data, filetype="pdf"))


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
    """O miolo de um cartão do prontuário (`pu-perf`, `pu-chamados`, `pu-seg`...)."""
    return html.split(f'id="{ident}"', 1)[1].split("</details>", 1)[0]


def test_os_numeros_viraram_o_painel_do_prontuario(tela, logado):
    """A faixa dos oito números da Central (05/11/2026) saiu com ela em 12/11/2026: os números da usina estão no painel
    do prontuário (a Performance em medidores com barra, as OS por estado, as pendências) e na faixa do resto."""
    css = CSS.read_text(encoding="utf-8")
    assert "cu-numeros" not in css
    html = _central(logado, "&usina=1")
    assert 'class="cn-numeros cu-numeros"' not in html
    painel = html.split('class="pu-painel"', 1)[1].split('class="pu-faixa"', 1)[0]
    for rot in ("Meta do mês", "PR", "Disponibilidade"):
        assert f'<span class="pu-med-r">{rot}</span>' in painel, rot
    faixa = html.split('class="pu-faixa"', 1)[1].split("</div>", 1)[0]
    for rot in ("Última ronda", "Chamados abertos", "Segurança"):
        assert f"<small>{rot}</small>" in faixa, rot


def test_a_exclamacao_amarela_ao_lado_do_titulo_leva_a_leitura_e_as_reguas(tela, logado):
    """"Os avisos do anexo 2 não precisam aparecer, pode ficar nos disclaimers" (a caixa "Gerencial, Confiabilidade (...)
    lido às" do canto) e "A exclamação tem que ficar ao lado do título e tem que ter o destaque em amarelo conforme
    segurança > extintores": o cabeçalho de todas as abas da Visão fica só com o título e o "!" do padrão do Nexus
    (`_explica.html`, o mesmo dia), que leva também a hora da leitura."""
    for args in ("responsavel=*&modo=geral", "responsavel=*&modo=cartoes",
                 "modo=ranking", "modo=painel&responsavel=*"):
        html = logado.get("/t/campo/responsaveis?" + args).get_data(as_text=True)
        assert 'class="cn-frescor"' not in html and '<details class="cr-info">' not in html, args
        cab = html.split('<div class="gc-titulo-explica"><h1 class="cn-titulo">', 1)[1].split("</details>", 1)[0]
        assert ('<details class="gc-explica"><summary class="gc-explica-bt" '
                'title="De onde vem cada número e a régua de cada alerta"') in cab, args
        assert "<b>Lido às " in cab and "pelo banco do Nexus" in cab, args
        for _b, _a, regua, texto in R.REGUAS:
            assert f"<dt>{regua}</dt>" in cab and texto[:30] in cab, (args, regua)






def test_o_relatorio_pergunta_o_mes_primeiro(tela, logado):
    """"Quando clicar em baixar relatórios: escolher qual o mês!": a janela abre com os meses em botões (o anterior
    marcado), antes dos temas."""
    from nexus.campo import relatorio_usina as RU
    html = _central(logado, "&usina=1")
    jan = html.split('id="pu-rel"', 1)[1].split("</dialog>", 1)[0]
    assert '<fieldset class="cu-rel-meses">' in jan and "<legend" in jan and "Qual mês?" in jan
    for m, _rot in RU.meses(HOJE):
        marcado = " checked" if m == RU.mes_padrao(HOJE) else ""
        assert f'<input type="radio" name="mes" value="{m}"{marcado}>' in jan, m
    assert jan.index("cu-rel-meses") < jan.index("pu-rel-campos")
    assert "<select" not in jan


def test_a_performance_traz_o_grafico_da_geracao(tela, logado):
    """"Quero que o gráfico de geração também apareça na visão do responsável > central da usina": o mesmo gráfico da
    janela do PR (a geração do dia que o Gerencial conta, a meta e o POA), dentro do cartão da Performance; no painel do
    alto, as mesmas barras numa faixa baixa."""
    html = _central(logado, "&usina=1")
    perf = _quadro(html, "pu-perf")
    assert "Geração diária (MWh) e POA (kWh/m²)" in perf and 'class="cr-svg"' in perf
    assert perf.count('class="cr-barra cr-barra--') == 2              # os dois dias com geração (o 3º só tem PR)
    assert html.split('class="pu-spark"', 1)[1].split("</a>", 1)[0].count('class="cr-barra cr-barra--') == 2
    # a janela do PR desenha o mesmo gráfico, da mesma macro
    jan = logado.get("/t/campo/responsaveis/usina/1/pr").get_data(as_text=True)
    assert jan.count('class="cr-barra cr-barra--') == 2
    assert "{% macro geracao(g) %}" in (BUSCA.parent / "_graficos.html").read_text(encoding="utf-8")
    # sem a série do dia a dia no banco, o cartão e o painel ficam sem o gráfico (a Brodowski 1)
    sem = _central(logado, "&usina=2")
    assert 'class="cr-svg"' not in _quadro(sem, "pu-perf") and 'class="pu-spark"' not in sem


def test_os_chamados_so_mostram_a_linha_que_tem_chamado(tela, banco, logado):
    """"SE NÃO TIVER VERIFICAÇÃO OU CONCLUSÃO NÃO PRECISA APARECER NA TELA": o cartão só mostra o que há (os abertos e
    em verificação numa lista, os concluídos no mês em outra); sem nenhum, uma frase só."""
    ch = _quadro(_central(logado, "&usina=1"), "pu-chamados")
    assert 'data-pu-os="16034"' in ch and "em verificação</em>" not in ch and "Concluídos neste mês" not in ch
    d = HOJE.replace(day=1)
    _aba(banco, "nexus_chamados", "fato_chamado", [
        dict(_chamado(17001, 1, "concluido", 30), data_id_fim=d.year * 10000 + d.month * 100 + d.day),
        _chamado(17005, 1, "verificacao", 3), _chamado(16050, 3, "aberto", 2)])
    visao.limpar()
    ch = _quadro(_central(logado, "&usina=1"), "pu-chamados")
    assert "em verificação</em>" in ch and "Concluídos neste mês" in ch and 'data-pu-os="17001"' in ch
    assert 'data-pu-os="16050"' in _quadro(_central(logado, "&usina=3"), "pu-chamados")
    ch = _quadro(_central(logado, "&usina=2"), "pu-chamados")
    assert "Nenhum chamado de garantia aberto." in ch and "pu-lista" not in ch




def test_o_eixo_com_passo_quebrado_mostra_a_casa_decimal():
    """O eixo do POA de passo 2,5 (achado na 3ª rodada, no gráfico da Altair): as marcas 2,5 e 7,5 saíam "2" e "8" (o
    arredondamento de 0 casa); agora o eixo com alguma marca quebrada leva uma casa em todas."""
    from nexus.campo import responsaveis_graficos as G
    g = G.geracao([{"dia": 1, "geracao_kwh": 37000, "meta_kwh": 40000, "ipoa": 9.5, "ipoa_meta": 7.7}], 30)
    assert [m["rotulo"] for m in g["grades_dir"]] == ["0,0", "2,5", "5,0", "7,5", "10,0", "12,5"]
    assert [m["rotulo"] for m in g["grades"]] == ["0", "10", "20", "30", "40", "50"]      # o passo inteiro fica sem casa



def test_o_pdf_leva_as_paradas_do_mes_com_o_que_aconteceu():
    """14/11/2026, Levi: "Na parte de relatório, eu não vi a opção de religamentos [...] Tem que ter religamentos"."""
    from datetime import date, datetime, timezone
    from nexus.campo import relatorio_usina as RU
    br = timezone(timedelta(hours=-3))
    d = {"uid": 1, "usina": "Altair", "cliente": "Thopen", "cidade": "", "uf": "SP", "potencia_mwp": None,
         "mes": "2026-11", "mes_id": 202611, "mes_txt": "novembro de 2026", "ini": date(2026, 11, 1),
         "fim": date(2026, 11, 13), "corrente": True, "hoje": date(2026, 11, 14), "erros": {},
         "religamentos": [{"ini": datetime(2026, 11, 12, 9, 41, tzinfo=br), "tipo": "Usina desligada", "fora": "54 min",
                           "fim": datetime(2026, 11, 12, 10, 35, tzinfo=br),
                           "parou": True, "os": "19375", "protecoes": "27;59",
                           "relato": "Causa: oscilação na rede da concessionária."},
                          {"ini": datetime(2026, 11, 10, 15, 55, tzinfo=br), "tipo": "Usina desligada", "fora": "4 min",
                           "parou": True, "os": "19150", "protecoes": "27", "relato": ""}]}
    # o resumo não repete o número do alto da seção (14/11/2026, Levi: "é a mesma coisa que se repete no KPI")
    assert RU._resumo(d, ("religamentos",)) == []
    corpo = RU._religamentos(d, RU._estilos(), RU.CHAVES_CAMPOS)
    # a explicação do religamento, os quatro números, o gráfico das proteções (logo depois dos números) e a tabela
    assert "a volta é o religamento" in corpo[0].text and len(corpo) == 8
    assert corpo[4].text == "Proteções que mais atuaram"
    # a Parada na frente e o período em pílulas: a parada no fundo vermelho-pastel, a volta no verde-pastel
    tabela = corpo[-1]
    assert [c.text for c in tabela._cellvalues[0]] == ["Parada", "Período", "Tempo indisponível (solar)", "Proteções", "OS",
                                                       "O que aconteceu"]
    # 12/11 09:41 a 10:35, toda no período solar: 54 min
    assert tabela._cellvalues[1][2].text == "54 min"
    saiu, _esp, voltou = tabela._cellvalues[1][1]
    assert "12/11 09:41" in saiu._cellvalues[0][0].text and saiu._bkgrndcmds[0][3] == RU.PILULA_PARADA[0]
    assert "12/11 10:35" in voltou._cellvalues[0][0].text and voltou._bkgrndcmds[0][3] == RU.PILULA_VOLTA[0]
    pdf = RU.gerar(d, ("religamentos",), gerado_em="14/11/2026 às 15:00", campos=("religamentos_lista",))
    assert pdf[:4] == b"%PDF" and len(pdf) > 1000


def test_o_que_aconteceu_so_completa_a_linha():
    """14/11/2026, Levi: "no usina desligada de dia tal a tal hora [...] já diz o período [...] Não precisa repetir
    quando voltou [...] no que aconteceu só complementa". As frases-modelo da Ronda COS, como estão no banco."""
    p = RU.relato_partes("Usina desligada de 02/11 às 21:40 a 03/11 às 08:51 (11 h 11 min). Causa: atuação da proteção "
                         "de sobretensão (59) no relé da usina. A usina voltou a gerar em 03/11 às 08:51, após o reset do "
                         "relé e o religamento no local. Foi aberto um chamado com a concessionária (nº 4471).")
    assert p == {"rotulo": "Usina desligada", "causa": "Atuação da proteção de sobretensão (59) no relé da usina",
                 "volta": "Voltou a funcionar após o reset do relé e o religamento no local.", "jeito": "local",
                 "extras": ["Foi aberto um chamado com a concessionária (nº 4471)."]}
    p = RU.relato_partes("Perda de comunicação com a usina de 05/11 às 09:35 a 05/11 às 15:30 (5 h 55 min), sem impacto "
                         "na geração. Causa: falha no equipamento de comunicação local da usina. Em 05/11 às 15:30, a "
                         "comunicação foi restabelecida. Normalizada em 05/11 às 15:40.")
    assert (p["rotulo"], p["volta"], p["extras"], p["jeito"]) == (
        "Perda de comunicação", "A comunicação foi restabelecida.", ["Sem impacto na geração."], None)
    p = RU.relato_partes("Usina desligada de 09/11 às 15:05 a 09/11 às 15:09 (4 min). A usina voltou a gerar em 09/11 às "
                         "15:09, religada remotamente pelo COS.")
    assert (p["volta"], p["jeito"], p["causa"]) == ("Voltou a funcionar pelo religamento remoto, feito pelo COS.", "remoto", "")
    # a volta sem o "como" sai inteira (a hora já está no Período); a continuação traz a causa no fim
    p = RU.relato_partes("Continuação: Cabine 1 e Cabine 2 desligadas de 04/11 às 00:00 a 04/11 às 10:15, por atuação da "
                         "proteção de subtensão (27). A Cabine 1 e a Cabine 2 voltaram a gerar em 04/11 às 10:15.")
    assert p == {"rotulo": "Cabines 1 e 2 desligadas", "causa": "Atuação da proteção de subtensão (27)", "volta": "",
                 "jeito": None, "extras": []}
    assert RU._rotulo_curto("Cabine 1, Cabine 2, Cabine 4, Cabine 5 e Cabine 6 desligadas") == "Cabines 1, 2, 4, 5 e 6 desligadas"
    assert RU.protecoes_do_texto("27ABC;59N, 27") == ["27", "59"] and RU.PROTECAO_NOME["78"] == "Salto de vetor"
    # nada de hora repetida no texto que vai para a célula
    texto = RU._o_que_aconteceu(RU.relato_partes("Usina desligada de 02/11 às 21:40 a 03/11 às 08:51 (11 h 11 min). "
                                                 "A usina voltou a gerar em 03/11 às 08:51, religada no local pela "
                                                 "equipe de campo."), RU._estilos()).text
    assert "às" not in texto and "Voltou a funcionar pelo religamento no local, feito pela equipe de campo." in texto



def test_o_grafico_destaca_os_desligamentos_sem_protecao():
    """14/11/2026, Levi: "destaque também as sem proteção [...] Sem proteção atuada. Quando for desligamento". A perda
    de comunicação (a geração não para) e a manutenção programada não entram. A parada com 27 e 59 tem a linha dela
    ("para esse caso aí de ser 2 ao mesmo tempo, incluir uma linha [...] bota 27 e 59"): cada parada numa linha só."""
    rel = [{"parou": True, "protecoes": "27;59"}, {"parou": True, "protecoes": "27ABC"},
           {"parou": True, "protecoes": ""}, {"parou": False, "protecoes": ""}, {"parou": True, "protecoes": ""}]
    partes = [{"rotulo": "Usina desligada"}, {"rotulo": "Usina desligada"}, {"rotulo": "Inversor 7.1 desligado"},
              {"rotulo": "Perda de comunicação"}, {"rotulo": "Manutenção programada"}]
    assert RU.sem_protecao(rel, partes) == 1 and RU._contagem_protecoes(rel) == [("27", 2), ("59", 1)]
    titulo, tabela, _esp = RU._grafico_protecoes(rel, partes, RU._estilos())
    linhas = tabela._cellvalues
    assert [(linhas[i][0].text, linhas[i][1].text, linhas[i][2].text) for i in (1, 2)] == [
        ("27", "Subtensão", "1"), ("27 e 59", "Subtensão e sobretensão", "1")]
    assert "Sem proteção atuada" in linhas[3][1].text
    assert RU._contagem_combinacoes([{"protecoes": "59;27"}, {"protecoes": "27"}, {"protecoes": "27, 59N"},
                                     {"protecoes": "59"}, {"protecoes": ""}]) == [(("27", "59"), 2), (("27",), 1), (("59",), 1)]
    assert RU._grafico_protecoes([], [], RU._estilos()) == []



def test_as_fontes_sao_so_as_dos_temas_do_pdf():
    """14/11/2026, Levi, no PDF só de religamentos: "a fonte está vindo do próprio COS mesmo, né? Não sei porque você
    botou meta, PR, gerencial". A linha das fontes era uma só para o relatório inteiro; agora é a dos temas que entraram."""
    import fitz
    from datetime import date
    d = {"uid": 1, "usina": "Altair", "cliente": "Thopen", "cidade": "", "uf": "SP", "potencia_mwp": None,
         "mes": "2026-10", "mes_id": 202610, "mes_txt": "outubro de 2026", "ini": date(2026, 10, 1),
         "fim": date(2026, 10, 31), "corrente": False, "hoje": date(2026, 11, 14), "erros": {}, "religamentos": []}
    texto = "".join(p.get_text() for p in fitz.open(stream=RU.gerar(d, ("religamentos",), gerado_em="14/11/2026"),
                                                    filetype="pdf")).replace("\n", " ")
    assert "Fonte: paradas e religamentos registrados pelo Centro de Operações (COS)" in texto and "Grid Co.." not in texto
    assert "Gerencial" not in texto and "Fracttal" not in texto and "Resumo do mês" not in texto



def test_o_tempo_indisponivel_conta_so_o_periodo_solar():
    """14/11/2026, Levi: "a parte de tempo fora, tem que ser calculado em período solar [...] De 6 da manhã às 6 da
    tarde". As paradas reais da Capitão Poço 100 em novembro."""
    from datetime import datetime, timedelta, timezone
    br = timezone(timedelta(hours=-3))

    def h(dia, hh, mm):
        return datetime(2026, 11, dia, hh, mm, tzinfo=br)
    assert RU.minutos_solares(h(2, 21, 40), h(3, 8, 51)) == 171          # só a manhã do dia 3: 06:00 a 08:51
    assert RU.minutos_solares(h(5, 9, 35), h(5, 15, 30)) == 355          # toda de dia
    assert RU.minutos_solares(h(9, 22, 45), h(9, 22, 51)) == 0           # toda de noite
    assert RU.minutos_solares(h(9, 17, 17), h(10, 9, 30)) == 43 + 210    # o fim da tarde e a manhã seguinte
    assert RU.minutos_solares(h(1, 5, 0), h(4, 7, 0)) == 3 * 720 + 60    # vários dias: em horas, não em dias
    assert RU._h_min(3 * 720 + 60) == "37 h" and RU._h_min(171) == "2 h 51 min" and RU._h_min(None) == "—"
    assert RU.minutos_solares(h(1, 5, 0), None) is None


def test_desligamento_e_so_quando_a_geracao_parou():
    """14/11/2026, Levi: "um deles foi falha de comunicação [...] você vai dizer 16 desligamentos, que é verdade [...] A
    pessoa pode ter até colocado o tipo da tarefa como religamento, mas na realidade não foi". A perda de comunicação fica
    na tabela, sem tempo indisponível, e fora do número do alto."""
    from datetime import date, datetime, timezone
    br = timezone(timedelta(hours=-3))
    para = {"ini": datetime(2026, 11, 12, 9, 41, tzinfo=br), "fim": datetime(2026, 11, 12, 10, 35, tzinfo=br),
            "tipo": "Usina desligada", "fora": "54 min", "parou": True, "os": "19375", "protecoes": "27",
            "relato": "Usina desligada de 12/11 às 09:41 a 12/11 às 10:35 (54 min). Causa: subtensão."}
    com = {"ini": datetime(2026, 11, 5, 9, 35, tzinfo=br), "fim": datetime(2026, 11, 5, 15, 30, tzinfo=br),
           "tipo": "Falha de comunicação", "fora": "5 h 55 min", "parou": False, "os": "18604", "protecoes": "",
           "relato": "Perda de comunicação com a usina de 05/11 às 09:35 a 05/11 às 15:30 (5 h 55 min), sem impacto na "
                     "geração. Causa: falha no equipamento de comunicação local da usina."}
    d = {"religamentos": [com, para], "ini": date(2026, 11, 1)}
    corpo = RU._religamentos(d, RU._estilos(), RU.CHAVES_CAMPOS)
    kpi = corpo[2]._cellvalues[0][0]
    assert [p.text for p in kpi] == ["Desligamentos no mês", '<font color="#c8102e">1</font>',
                                     "e 1 perda de comunicação, sem parar a geração"]
    linhas = corpo[-1]._cellvalues
    assert "a geração não parou" in linhas[1][2].text and linhas[2][2].text == "54 min"
