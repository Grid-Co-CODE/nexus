"""Sem o 2º cabeçalho (13/10/2026, Levi: "Quero que essa visão de cabeçalho ao lado de sair vá para o cabeçalho do Nexus
e suma esse 2° cabeçalho tanto de OS Creator Web quanto de plataforma de performance! Dá a impressão que é uma tela
dentro de uma tela!").

- o topo do Nexus mostra quem entrou como o topo do OS Creator mostrava: o avatar com as iniciais, o nome e o perfil do
  Fracttal, ao lado do Sair;
- o OS Creator logo abaixo do Nexus some com o topo dele (a ponte marca a tela antes de pintar); aberto sozinho, fica;
- as telas da Plataforma de Performance perdem a faixa "<tela> · Plataforma de Performance": ela só nasce com controle
  (o seletor de usina do Diagnóstico), e o Modo TV do Painel NOC foi para o topo do Nexus.
"""
import pytest

from nexus import iniciais
from nexus.performance import porta
from nexus.torres.oscreator import ponte
from test_porta_moldura import PREFIXO, _cliente

CSS = (__import__("pathlib").Path(__file__).resolve().parent.parent / "nexus" / "static" / "nexus.css").read_text(
    encoding="utf-8")


def _topo(html: str) -> str:
    return html.split('<header class="topo">', 1)[1].split("</header>", 1)[0]


# ── quem entrou, no topo do Nexus ───────────────────────────────────────────────────────────────────────────────────
def test_iniciais_como_o_avatar_do_os_creator():
    assert iniciais("Ana Maria Souza") == "AS" and iniciais("fulano") == "F"
    assert iniciais("") == "?" and iniciais(None) == "?" and iniciais("  ") == "?"


def test_o_topo_mostra_quem_entrou_pelo_fracttal_ao_lado_do_sair(logado):
    with logado.session_transaction() as s:
        s["usuario"] = {"email": "pessoa@exemplo.test", "nome": "Pessoa Exemplo", "perfil": "ADMINISTRATOR"}
    topo = _topo(logado.get("/").get_data(as_text=True))
    assert '<span class="usuario-avatar" aria-hidden="true">PE</span>' in topo
    assert '<span class="usuario-nome">Pessoa Exemplo</span><span class="usuario-perfil">ADMINISTRATOR</span>' in topo
    assert 'class="usuario-topo" title="pessoa@exemplo.test"' in topo
    # entre o Tema e o Sair, como o bloco do OS Creator ficava ao lado do "sair" dele
    assert topo.index('class="troca-tema-form"') < topo.index("usuario-topo") < topo.index('aria-label="Sair"')
    # sem perfil no Fracttal, só o nome (sem linha vazia)
    with logado.session_transaction() as s:
        s["usuario"] = {"email": "pessoa@exemplo.test", "nome": "Pessoa Exemplo", "perfil": ""}
    topo = _topo(logado.get("/").get_data(as_text=True))
    assert "usuario-nome" in topo and "usuario-perfil" not in topo


def test_pela_senha_de_administrador_o_topo_nao_inventa_nome(logado):
    assert "usuario-topo" not in _topo(logado.get("/").get_data(as_text=True))


def test_no_celular_fica_so_o_avatar_entre_o_tema_e_o_sair():
    celular = CSS.split("@media (max-width:820px)", 1)[1]
    assert ".usuario-topo{grid-column:3;grid-row:2}" in celular
    assert ".sair{grid-column:4;grid-row:2;justify-self:end}" in celular
    assert "grid-template-columns:minmax(0,1fr) auto auto auto" in celular
    # o esconder do nome vem DEPOIS do .usuario-txt{display:flex}: antes dele, perdia (o nome seguia à vista a 375 px)
    esconde = "@media (max-width:820px){.usuario-txt,.topo-tv{display:none}}"
    assert esconde in CSS and CSS.index(".usuario-txt{display:flex") < CSS.index(esconde)


# ── o OS Creator dentro do Nexus, sem o topo dele ───────────────────────────────────────────────────────────────────
def test_o_os_creator_logo_abaixo_do_nexus_marca_a_tela_e_some_com_o_topo(logado):
    html = logado.get("/os/login").get_data(as_text=True)
    cabeca = html.split("<head>", 1)[1]
    marca = ponte._MARCA_NO_NEXUS.decode()
    # a marca vem antes de qualquer script da página e do <title>: o topo nem chega a piscar
    assert marca in cabeca and cabeca.index(marca) < cabeca.index("<title>")
    assert 'hasAttribute("data-nexus")' in marca and 'classList.add("os-no-nexus")' in marca
    assert "html.os-no-nexus .os-header,html.os-no-nexus .os-sep{display:none!important}" in html
    # o "topo sempre à mostra" de quem o tinha recolhido vale só fora do Nexus (o OS Creator aberto sozinho)
    assert "html:not(.os-embutido):not(.os-no-nexus) body.os-sem-topo .os-header{display:flex!important}" in html
    assert "html:not(.os-embutido) body.os-sem-topo" not in html
    # o topo segue no HTML: aberto sozinho no navegador, sem o Nexus em cima, é o único lugar com o nome e o sair
    assert 'class="os-header"' in html


# ── as telas da Plataforma de Performance, sem a faixa ─────────────────────────────────────────────────────────────
@pytest.mark.parametrize("prefixo", ["", PREFIXO])
def test_nenhuma_tela_da_plataforma_tem_a_faixa_com_o_nome(prefixo):
    cli = _cliente(prefixo)
    for t in porta.MAPA:
        h = cli.get(f"{prefixo}/t/{t.torre}/{t.tela}").get_data(as_text=True)
        assert "Plataforma de Performance</span>" not in h and "porta-origem" not in h, t
        corpo = h.split('<div class="porta" id="porta">', 1)[1]
        if t.tela == "diagnostico":
            # o seletor de usina é da página do Nexus: a faixa fica, só com ele
            faixa = corpo.split('<div class="porta-faixa" id="porta-faixa">', 1)[1].split('<p class="porta-alerta"', 1)[0]
            assert 'id="porta-usina"' in faixa and "Plataforma de Performance" not in faixa
        else:
            assert 'class="porta-faixa"' not in corpo, t
