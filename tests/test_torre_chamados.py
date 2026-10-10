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
                                   "tickets": "/os/tickets",
                                   "garantias": "/os/chamados/acompanhamento"}


def test_abrir_outra_tela_do_os_creator_so_aceita_endereco_dele(logado):
    r = logado.get("/t/chamados/garantias?abrir=/os/chamados/acompanhamento/15000")
    assert 'src="/os/chamados/acompanhamento/15000"' in r.get_data(as_text=True)
    r = logado.get("/t/chamados/garantias?abrir=https://outro.site/")
    assert 'src="/os/chamados/acompanhamento"' in r.get_data(as_text=True)


def test_sem_login_vai_para_a_entrada(cliente):
    assert cliente.get("/t/chamados/fabricantes").status_code == 302


def test_tickets_de_performance_abre_os_tickets_do_os_creator_e_fica_verde(logado):
    """Auditoria B8 da porta única (10/10/2026): o item "Tickets de performance" aparecia "Em construção", mas a tela já
    existia no Nexus em /os/tickets (a do OS Creator Web). Agora é um atalho, como Fabricantes e Garantias."""
    r = logado.get("/t/chamados/tickets")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'class="os-moldura" src="/os/tickets"' in html and "Em construção" not in html
    # o item fica verde no menu (tela com conteúdo) e o Início conta a torre com 3 prontas
    assert 'href="/t/chamados/tickets" class="com-conteudo"' in html
    assert "3 de 4 prontas" in logado.get("/").get_data(as_text=True)
    # a rota existe de fato no clone (o atalho não leva a um 404); sem o login do Fracttal ela pede o login do OS Creator
    # antes de ler qualquer coisa (nada vai à rede aqui)
    r = logado.get("/os/tickets")
    assert r.status_code == 302 and r.headers["Location"].startswith("/os/login?next=%2Fos%2Ftickets")
