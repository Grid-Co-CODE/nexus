"""Engenharia > Confiabilidade enxuta (Levi, 05/11/2026: "Para ver o que realmente importa preciso fazer uma rolagem
completa de tela, está muito ruim então precisamos enxugar o excesso"). A explicação e as metas vão para o "!" ao lado
do título (o da Segurança > Extintores), a leitura do Fracttal fica à direita do título, os números vêm antes dos
filtros, a linha das contas e o "Esconder serviço" saíram, e a lista de Ativos com sinal mostra 20 e rola."""
from test_engenharia_acompanhamento import _como, banco, tela  # noqa: F401
from test_engenharia_acompanhamento import ANA

URL = "/t/engenharia/confiabilidade"


def _pagina(cliente):
    return _como(cliente, ANA).get(URL).get_data(as_text=True)


def test_a_explicacao_e_as_metas_ficam_no_ponto_de_exclamacao(tela, cliente):
    html = _pagina(cliente)
    cab = html.split('class="cn-cab eg-cab"', 1)[1].split("</header>", 1)[0]
    assert 'class="gc-explica-bt"' in cab and "Confiabilidade dos ativos" in cab
    caixa = cab.split('class="gc-explica-caixa"', 1)[1]
    assert "Para que serve" in caixa and "classe mundial" in caixa and "MTBF ÷ (MTBF + MTTR)" in caixa
    # a leitura do Fracttal no mesmo cabeçalho, à direita do título
    assert "contas às" in cab
    # fora do "!" não sobra o texto de abertura, o "Entenda esta tela" nem o rodapé das metas
    resto = html.replace(caixa, "")
    assert "Entenda esta tela" not in html and 'class="cn-pergunta"' not in html
    assert "eg-kpi-rodape" not in resto and "classe mundial" not in resto
    # o "Como ler" da tabela e o "De onde vem" também (05/11/2026, o padrão do Nexus)
    assert "medianas dos ativos" in caixa and "As OS de falha" in caixa and 'class="cn-nota"' not in html


def test_os_numeros_vem_antes_dos_filtros_e_as_abas_depois(tela, cliente):
    html = _pagina(cliente)
    assert html.index('class="eg-painel eg-kpis"') < html.index('class="eg-filtros"') < html.index('class="eg-abas"')


def test_a_linha_das_contas_e_o_esconder_servico_sairam(tela, cliente):
    html = _pagina(cliente)
    assert "ativos com sinal, de" not in html and "em acompanhamento</" not in html
    assert "Esconder serviço" not in html and "Mostrar serviço" not in html and "servico=" not in html
    assert 'class="eg-conta"' not in html and "eg-alterna" not in html


def test_ativos_com_sinal_mostra_20_e_rola_com_as_etiquetas_so_na_cor(tela, cliente):
    html = _pagina(cliente)
    lista = html.split('class="eg-itens eg-sinais"', 1)[1].split("</section>", 1)[0]
    assert lista.startswith(' data-eg-max="20"')
    etiquetas = [t for t in lista.split('class="eg-tag ')[1:]]
    assert etiquetas and all(t.startswith("eg-tag--sem ") for t in etiquetas)
    # o nível (CRÍTICO, ATENÇÃO) também só na cor da letra, sem a pílula
    niveis = lista.split('class="eg-pill ')[1:]
    assert niveis and all(t.startswith("eg-pill--sem ") for t in niveis)
