"""O Raio X da OS, etapa 2 (Levi, 11/11/2026; no quiz, "uma página só"): o quadro de Garantias abre o Raio X da OS (a
página da OS do Nexus) na página inteira, com a volta para Garantias, e o Raio X da OS de chamado mostra o chamado: a tela
do chamado do OS Creator no modo "blocos", só com o que é do chamado (o estado, o Finalizar, os números do fornecedor, o
ticket, o status do chamado, como abrir, a cadeia do chamado, para abrir o ticket, as observações e os outros chamados).
O Fracttal e o banco são de mentira; nomes e números inventados."""
from test_engenharia_acompanhamento import ANA, _como
from test_engenharia_os_quadro import URL as URL_OS, banco, pagina  # noqa: F401  (fixtures)
from test_oscreator_acomp_tela_vencida_20_10 import URL, _cliente, _memoria_limpa, fila, fr  # noqa: F401
from test_oscreator_garantias_pagina_da_os_09_11 import NEXUS

from nexus.engenharia import cadeia_os as C
from nexus.torres import engenharia as torre


def _quadro(environ=None):
    return _cliente().get(URL, environ_overrides=environ or {}).get_data(as_text=True)


def _tela(qs="", environ=None):
    cli = _cliente()
    cli.get(URL)
    return cli.get(URL + "/9104" + qs, environ_overrides=environ or {}).get_data(as_text=True)


def test_no_nexus_o_cartao_e_a_linha_abrem_o_raio_x_da_os(fr, fila):
    html = _quadro({"os_web.pagina_da_os": NEXUS})
    assert 'href="/t/engenharia/equipe/os/9104?de=garantias" target="_top"' in html
    assert 'data-href="/t/engenharia/equipe/os/9104?de=garantias" data-topo' in html
    assert 'href="/os/chamados/acompanhamento/9104"' not in html


def test_sozinho_o_cartao_abre_a_tela_do_chamado_como_antes(fr, fila):
    html = _quadro()
    assert 'href="/os/chamados/acompanhamento/9104"' in html and "data-topo" not in html


def test_o_modo_blocos_so_tem_o_que_e_do_chamado(fr, fila):
    html = _tela("?blocos=1", {"os_web.pagina_da_os": NEXUS})
    for h in ("Ticket no fornecedor", "Status do chamado", "Como abrir", "A cadeia do chamado", "Para abrir o ticket",
              "Observações", "Outros chamados"):
        assert "<h2>%s</h2>" % h in html, h
    for h in ("Dados", "Ações da OS", "Na nota da OS", "Demais respostas do técnico"):
        assert "<h2>%s</h2>" % h not in html, h
    assert "Abrir a OS" not in html and "← Acompanhamento" not in html and "Chamado de garantia" in html
    assert "tipo: 'altura'" in html                                   # a altura vai para o Raio X ajustar a moldura
    inteira = _tela("", {"os_web.pagina_da_os": NEXUS})                  # sem o modo, a tela de sempre
    assert "<h2>Dados</h2>" in inteira and "tipo: 'altura'" not in inteira


def test_a_ponte_da_a_pagina_da_os_ao_quadro():
    fonte = open(__import__("nexus.torres.oscreator.ponte", fromlist=["x"]).__file__, encoding="utf-8").read()
    assert 'if resto == "chamados/acompanhamento":' in fonte


def test_o_raio_x_da_os_de_chamado_mostra_o_chamado(pagina, cliente, monkeypatch):
    C.limpar()
    cli = _como(cliente, ANA)
    html = cli.get(URL_OS + "?de=garantias").get_data(as_text=True)
    assert '<a class="eg-ac-volta" href="/t/chamados/garantias">← Garantias</a>' in html
    assert 'src="/os/chamados/acompanhamento/16502?blocos=1"' in html and "data-chamado" in html
    # sem o `de`, vale o livro dos chamados
    monkeypatch.setattr(torre, "_ler_chamados", lambda: [{"os": "16502.0", "situacao": "aberto"}])
    assert 'src="/os/chamados/acompanhamento/16502?blocos=1"' in cli.get(URL_OS).get_data(as_text=True)
    monkeypatch.setattr(torre, "_ler_chamados", lambda: [{"os": "99999", "situacao": "aberto"}])
    assert "data-chamado" not in cli.get(URL_OS).get_data(as_text=True)


def test_o_banco_dos_chamados_fora_nao_derruba_o_raio_x(pagina, cliente, monkeypatch):
    def fora():
        raise RuntimeError("banco fora")
    monkeypatch.setattr(torre, "_ler_chamados", fora)
    r = _como(cliente, ANA).get(URL_OS)
    assert r.status_code == 200 and "data-chamado" not in r.get_data(as_text=True)
