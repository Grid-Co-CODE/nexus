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


def test_tickets_de_performance_saiu_com_a_tela_do_os_creator(app, logado):
    """Levi, 12/10/2026: "Chamados > Tickets de Performance -> pode excluir essa seção e o código dela!". Sai o item da
    torre e a tela de Tickets do OS Creator Web (as rotas, o painel, o card na Performance e o atalho do Início dele).
    A linha de ticket que nasce junto da OS da Performance (a caixa "Gerar ticket") é da criação de OS e fica."""
    html = logado.get("/t/chamados/fabricantes").get_data(as_text=True)
    assert "/t/chamados/tickets" not in html and "Tickets de performance" not in html
    assert logado.get("/t/chamados/tickets").status_code == 404
    assert "2 de 3 prontas" in logado.get("/").get_data(as_text=True)
    # no clone a rota não existe mais (o registro automático das telas não acha o rotas_tickets)
    from nexus.torres.oscreator import ponte
    clone = ponte.clone(app)
    # (o /os/api/acomp/<folio>/ticket é o nº do chamado no fabricante, do Acompanhamento de chamados: fica)
    assert not [r.rule for r in clone.url_map.iter_rules() if "/tickets" in r.rule]
    import sys
    if ponte.RAIZ_CLONE not in sys.path:
        sys.path.append(ponte.RAIZ_CLONE)
    from os_web import lancador
    assert "tickets" not in lancador.ICONE_SECAO and all(s != "tickets" for _p, s in lancador.ABAS_SECOES)
