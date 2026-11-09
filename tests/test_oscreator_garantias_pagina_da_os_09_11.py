"""A OS na tela do chamado de Garantias abre a página da OS da Engenharia (09/11/2026, Levi, pelo chat do scrum master:
"em chamados a parte de anexos está toda bugada", e o mesmo desenho da página da OS da Engenharia). No quiz ele escolheu
"Abrir a OS leva a ela": a tela do chamado continua (status, ticket, observações), e o "Abrir a OS" e os números da
cadeia levam à página da OS, que tem os anexos, as tarefas e as subtarefas, com a volta para o chamado dentro da moldura
de Garantias. O bloco de anexos sai da tela do chamado. Sozinho (sem o Nexus), a OS segue abrindo o card do OS Creator.

O Fracttal daqui é de mentira; nenhum teste vai à rede."""
from urllib.parse import parse_qs, urlsplit

from test_oscreator_acomp_tela_vencida_20_10 import URL, _cliente, _memoria_limpa, fila, fr  # noqa: F401

from nexus.torres.oscreator import ponte

NEXUS = {"os": "/t/engenharia/equipe/os/", "volta": "/t/chamados/garantias?abrir=/os/chamados/acompanhamento/"}


def _tela(environ=None):
    cli = _cliente()
    cli.get(URL)
    return cli.get(URL + "/9104", environ_overrides=environ or {}).get_data(as_text=True)


def _links(html, texto):
    """Os <a ...> cujo texto é `texto`."""
    out = []
    for parte in html.split("<a ")[1:]:
        tag, resto = parte.split(">", 1)
        if resto.split("</a>", 1)[0].strip() == texto:
            out.append(tag)
    return out


def test_no_nexus_o_abrir_a_os_e_a_cadeia_vao_a_pagina_da_os_com_a_volta_para_o_chamado(fr, fila):
    html = _tela({"os_web.pagina_da_os": NEXUS})
    for tag in _links(html, "Abrir a OS") + _links(html, "9104"):
        href = tag.split('href="', 1)[1].split('"', 1)[0].replace("&amp;", "&")
        u = urlsplit(href)
        assert u.path == "/t/engenharia/equipe/os/9104", href
        assert parse_qs(u.query)["de"] == ["/t/chamados/garantias?abrir=/os/chamados/acompanhamento/9104"]
        assert 'target="_top"' in tag                    # a página é do Nexus: sai da moldura do OS Creator
    assert len(_links(html, "Abrir a OS")) == 1 and len(_links(html, "9104")) >= 1
    assert "/os/os/" not in html.split('<ol class="cadeia">', 1)[1].split("</ol>", 1)[0]


def test_sozinho_a_os_abre_o_card_como_antes(fr, fila):
    html = _tela()
    tag = _links(html, "Abrir a OS")[0]
    assert 'href="/os/os/' in tag and "target" not in tag


def test_a_tela_do_chamado_nao_tem_mais_os_anexos(fr, fila):
    for environ in ({"os_web.pagina_da_os": NEXUS}, None):
        html = _tela(environ)
        for a in ("anexos-os", "anexos-sub", "anexo-incluir"):
            assert 'data-acao="%s"' % a not in html, a
        assert "data-anexos=" not in html


def test_a_ponte_da_o_endereco_da_pagina_com_o_prefixo(app):
    with app.test_request_context("/os/chamados/acompanhamento/9104"):
        assert ponte.pagina_da_os() == NEXUS
    with app.test_request_context("/os/chamados/acompanhamento/9104", base_url="http://localhost/nexus"):
        assert ponte.pagina_da_os()["os"] == "/nexus/t/engenharia/equipe/os/"
    # só a tela de um chamado leva a chave (o quadro não paga a leitura do setor)
    assert ponte._ROTA_OBS.fullmatch("chamados/acompanhamento/9104")
    assert not ponte._ROTA_OBS.fullmatch("chamados/acompanhamento")
