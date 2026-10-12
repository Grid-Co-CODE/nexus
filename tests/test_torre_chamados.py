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
    """Levi, 12/10/2026: "Chamados > Tickets de Performance -> pode excluir essa seção e o código dela!" e "Isso você não
    levará para o oem". Sai o item da torre e a tela de Tickets da cópia do OS Creator (as rotas e o painel; a sincronia
    só lista o apagado). Os links que o código do oem ainda desenha (o card da Performance e a pílula do setor no Início)
    saem na ponte, e a cópia segue igual à do oem. A linha de ticket que nasce junto da OS da Performance (a caixa "Gerar
    ticket") é da criação de OS e fica."""
    html = logado.get("/t/chamados/fabricantes").get_data(as_text=True)
    assert "/t/chamados/tickets" not in html and "Tickets de performance" not in html
    assert logado.get("/t/chamados/tickets").status_code == 404
    assert "2 de 3 prontas" in logado.get("/").get_data(as_text=True)
    # no clone a rota não existe mais (o registro automático das telas não acha o rotas_tickets)
    from nexus.torres.oscreator import ponte
    clone = ponte.clone(app)
    # (o /os/api/acomp/<folio>/ticket é o nº do chamado no fabricante, do Acompanhamento de chamados: fica)
    assert not [r.rule for r in clone.url_map.iter_rules() if "/tickets" in r.rule]
    # os links para a tela que saiu: o card da Performance (o template da cópia, igual ao do oem) e a pílula do Início
    from pathlib import Path
    perf = Path(ponte.RAIZ_CLONE, "os_web", "templates", "performance.html").read_bytes()
    assert b'href="/os/tickets"' in perf                                     # a cópia não mudou
    limpo = ponte._SEM_TICKETS.sub(b"", perf)
    assert b"/os/tickets" not in limpo and limpo.count(b'class="os-plano"') == perf.count(b'class="os-plano"') - 1
    pilulas = (b'<div class="portas"><a href="/os/performance/criar?frase=x">String</a><a href="/os/tickets">Tickets</a>'
               b'</div>')
    sem = b'<div class="portas"><a href="/os/performance/criar?frase=x">String</a></div>'
    assert ponte._SEM_TICKETS.sub(b"", pilulas) == sem


def test_paginas_do_os_creator_no_nexus_sem_link_para_os_tickets(app, logado, monkeypatch):
    """A Performance e o Início do OS Creator, servidos pela ponte com o login do Fracttal (de mentira, sem rede): nenhum
    link para a tela que saiu. O "/os/tickets" que sobra no Início é a tabela das abas (JSON), não um link."""
    import socket
    from test_torre_oscreator import _login_do_fracttal

    def sem_rede(*a, **k):
        raise OSError("teste sem rede")
    monkeypatch.setattr(socket.socket, "connect", sem_rede)
    _login_do_fracttal(app, logado)
    perf = logado.get("/os/performance")
    assert perf.status_code == 200
    h = perf.get_data(as_text=True)
    assert "/os/tickets" not in h and h.count('class="os-plano"') == 4       # os 4 planos; o card Tickets saiu
    inicio = logado.get("/os/").get_data(as_text=True)
    assert 'href="/os/tickets"' not in inicio and 'class="portas"' in inicio
