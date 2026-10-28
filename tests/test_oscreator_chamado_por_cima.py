"""A tela do chamado de Garantias por cima de uma tela do Nexus (Levi, 28/10/2026, no Painel do responsável: "Ao clicar
no chamado deve aparecer a tela que aparece quando clicamos na OS de chamados na parte de garantias. Não deve direcionar,
apenas sobrepor a tela como uma meio que janela dando um blur de fundo"): a moldura do meio (/os/_nexus/chamado/<nº>,
`ponte.chamado_os`) com a MESMA tela do clone dentro, ou o aviso de como entrar pelo Fracttal."""
from test_oscreator_tema_claro import _login_do_fracttal, precisa_do_clone


@precisa_do_clone
def test_sem_o_login_do_fracttal_a_moldura_diz_como_entrar_e_volta(logado):
    h = logado.get("/os/_nexus/chamado/17311?de=/t/campo/responsaveis").get_data(as_text=True)
    assert "Para abrir o chamado, entre pelo Fracttal" in h and 'id="nx_ch"' not in h
    # o login do OS Creator, voltando à tela do Nexus de onde a pessoa saiu (o mesmo /card/voltar do card da OS)
    assert 'href="/os/login?next=%2Fos%2F_nexus%2Fcard%2Fvoltar%3Fde%3D%2Ft%2Fcampo%2Fresponsaveis"' in h
    assert 'target="_top"' in h


@precisa_do_clone
def test_com_o_login_a_tela_do_chamado_vem_na_moldura_de_dentro(app, logado):
    _login_do_fracttal(app, logado)
    h = logado.get("/os/_nexus/chamado/17311?de=/t/campo/responsaveis").get_data(as_text=True)
    assert '<iframe class="nx-ch" id="nx_ch" src="/os/chamados/acompanhamento/17311"' in h
    # aberta sozinha (link copiado), vira a própria tela do chamado; o Esc avisa a janela do Nexus para fechar
    assert 'location.replace("/os/chamados/acompanhamento/17311")' in h
    assert "nexusChamado: 1, tipo: 'fechar'" in h


def test_o_destino_de_volta_so_e_do_proprio_site(logado):
    """O `de` passa pelo `next_seguro`: um endereço de fora não vira a volta do login."""
    h = logado.get("/os/_nexus/chamado/17311?de=https://exemplo.invalid/x").get_data(as_text=True)
    assert "exemplo.invalid" not in h
