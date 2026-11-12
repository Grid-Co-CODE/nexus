"""A prévia da visão do contrato (12/11/2026, Contratos e clientes › Prévia): o mockup para a avaliação de Contratos e
dos setores, numa moldura, de todos e com o aviso de dados fictícios."""
from nexus.torres.contratos import TORRE

MOCKUP = "/static/previa/visao-do-contrato.html"


def test_a_previa_abre_na_moldura_com_o_aviso(logado):
    html = logado.get("/t/contratos/previa").get_data(as_text=True)
    assert "Prévia: visão do contrato" in html and "fictícios" in html
    assert '<iframe class="previa-moldura"' in html and MOCKUP in html
    assert TORRE.tela("previa").de_todos


def test_o_cabecalho_da_previa_e_uma_linha_so(logado):
    """Levi, 12/11/2026: "É quase a tela inteira, só de nada com nada": o título com o aviso na mesma linha; a pergunta
    da tela e a faixa de aviso saíram de cima da moldura."""
    html = logado.get("/t/contratos/previa").get_data(as_text=True)
    cab = html.split('class="campo-nativa"', 1)[1].split("<iframe", 1)[0]
    assert "cn-pergunta" not in cab and "cn-aviso" not in cab and "Abrir em tela cheia" in cab


def test_o_mockup_esta_no_static_e_se_esconde_dentro_do_nexus(cliente):
    r = cliente.get(MOCKUP)
    pagina = r.get_data(as_text=True)
    assert r.status_code == 200 and "Visão do contrato" in pagina
    # dentro da moldura do Nexus o topo do mockup some (o do Nexus já está na tela)
    assert 'classList.add("embutido")' in pagina and "html.embutido .topo{display:none}" in pagina
    r.close()


def test_o_mockup_e_so_o_contrato_e_abre_nas_regras(cliente):
    """Levi, 12/11/2026: "pode tirar o prontuário [...] Não tem nada a ver" e "A gente está vendo o quê? Regras do
    contrato. Então, tem que mostrar regras do contrato. Aí tem um filtro para isso, um filtro para aquilo. Aí uma
    porrada de KPI. Aí tem outro filtro lá em cima de contrato. Aí tem um botão de nova regra. Se decida, enxugue"."""
    r = cliente.get(MOCKUP)
    pagina = r.get_data(as_text=True)
    r.close()
    for fora in ("vProntuario", "PRONT", "#/prontuario", "Prontuário da usina</a>", "EQUIP"):     # o prontuário saiu inteiro
        assert fora not in pagina
    assert cliente.get("/static/previa/contratos-e-prontuario.html").status_code == 404
    # as seis partes do contrato, abrindo nas Regras
    assert ('var ABAS = [["regras", "Regras"], ["calendario", "Calendário"], ["atendimento", "Atendimento"], '
            '["entregaveis", "Entregáveis"], ["metas", "Metas"], ["financeiro", "Financeiro"]]') in pagina
    assert '(location.hash || "#/regras")' in pagina
    # um controle só nas Regras (Todas | Acordadas): saíram os filtros por categoria, a ficha de seis caixas e o
    # seletor de contrato separado (o nome do cliente é a troca); a regra nova é a última linha da tabela
    assert pagina.count("data-cat") == 0 and 'class="chip' not in pagina
    assert pagina.count('seg("Quais regras"') == 1 and "data-ficha" in pagina
    assert pagina.index('class="tab"') < pagina.index("data-nova-regra><i")
    assert "btn--prim\" data-nova" not in pagina
