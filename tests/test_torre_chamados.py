"""Torre Chamados (Levi, 08/10/2026): o Controle de fornecedores do OS Creator Web abre em Chamados > Fabricantes e o
Acompanhamento de chamados em Chamados > Garantias, sem sair do OS Creator (o mesmo endereço /os/...)."""
from nexus.torres.oscreator.ponte import ATALHOS


def test_fabricantes_abre_o_controle_de_fornecedores_com_o_menu_de_chamados(logado):
    r = logado.get("/t/chamados/fabricantes")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'class="os-moldura" src="/os/chamados/fornecedores"' in html
    assert '"/t/chamados/garantias": {"nome": "Garantias", "url": "/os/chamados/acompanhamento"}' in html \
        or '"/t/chamados/garantias"' in html


def test_garantias_abre_o_acompanhamento_de_chamados(logado):
    r = logado.get("/t/chamados/garantias")
    assert r.status_code == 200
    assert 'class="os-moldura" src="/os/chamados/acompanhamento"' in r.get_data(as_text=True)


def test_as_telas_continuam_no_os_creator(logado):
    # "não que vão sair da visão do OS Creator Web": a torre OS Creator segue com a tela Chamados (o setor dele)
    r = logado.get("/t/os/chamados")
    assert r.status_code == 200 and 'src="/os/chamados"' in r.get_data(as_text=True)
    assert ATALHOS["chamados"] == {"fabricantes": "/os/chamados/fornecedores",
                                   "garantias": "/os/chamados/acompanhamento"}


def test_abrir_outra_tela_do_os_creator_so_aceita_endereco_dele(logado):
    r = logado.get("/t/chamados/garantias?abrir=/os/chamados/acompanhamento/15000")
    assert 'src="/os/chamados/acompanhamento/15000"' in r.get_data(as_text=True)
    r = logado.get("/t/chamados/garantias?abrir=https://outro.site/")
    assert 'src="/os/chamados/acompanhamento"' in r.get_data(as_text=True)


def test_sem_login_vai_para_a_entrada(cliente):
    assert cliente.get("/t/chamados/fabricantes").status_code == 302
