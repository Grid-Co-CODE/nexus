"""A prévia da visão do contrato e do prontuário da usina (12/11/2026, Contratos e clientes › Prévia): o mockup para a
avaliação de Contratos e dos setores, numa moldura, de todos e com o aviso de dados fictícios."""
from nexus.torres.contratos import TORRE


def test_a_previa_abre_na_moldura_com_o_aviso(logado):
    html = logado.get("/t/contratos/previa").get_data(as_text=True)
    assert "Prévia: contrato e prontuário" in html and "fictícios" in html
    assert '<iframe class="previa-moldura"' in html and "/static/previa/contratos-e-prontuario.html" in html
    assert TORRE.tela("previa").de_todos


def test_o_mockup_esta_no_static_e_se_esconde_dentro_do_nexus(cliente):
    r = cliente.get("/static/previa/contratos-e-prontuario.html")
    pagina = r.get_data(as_text=True)
    assert r.status_code == 200 and "Visão do contrato" in pagina and "Prontuário da usina" in pagina
    # dentro da moldura do Nexus o topo e o menu do mockup somem (os do Nexus já estão na tela)
    assert 'classList.add("embutido")' in pagina and "html.embutido .topo,html.embutido .menu{display:none}" in pagina
    r.close()
