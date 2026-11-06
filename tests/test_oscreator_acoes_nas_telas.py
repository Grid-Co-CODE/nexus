"""As ações da OS nas telas que abrem a OS (Levi, 06/11/2026: o Incluir anexo, com os anexos para ver e baixar, e "Nessas
telas devem ter essas opção também: Enviar para verificação, concluir e cancelar!"): o card do OS Creator (o que o Quadro
da Performance abre), a moldura dele no Nexus abrindo já numa ação (a página da OS da Engenharia) e a tela do chamado de
Garantias, com os diálogos do card (_dlg_acoes_os.html). O Fracttal daqui é de mentira; nenhum teste vai à rede."""
import re

from test_oscreator_acomp_tela_vencida_20_10 import URL, _cliente, _memoria_limpa, fila, fr  # noqa: F401
from test_oscreator_card_tarefas import Fracttal, _card, _tarefa

import api  # noqa: E402 — o api.py do clone (o sys.path vem dos módulos acima)


def test_o_card_tem_o_incluir_anexo_e_os_dialogos_de_sempre(monkeypatch):
    monkeypatch.setattr(api, "_rpc_call", Fracttal([_tarefa(1)], []).rpc)
    html = _card()
    assert 'data-acao="anexo-incluir"' in html and 'accept=".pdf' in html
    # as regras na dica do botão, não à vista (06/11/2026: "tire o texto [...] e organize melhor a informação")
    assert re.search(r'data-acao="anexo-incluir"[^>]*title="[^"]*até 10 MB cada', html)
    assert '<span class="det-ajuda">PDF' not in html
    for dlg in ("concluir", "verificacao", "executar", "cancelar", "anexos", "fluxo"):
        assert html.count('<template data-dlg="%s">' % dlg) == 1, dlg
    assert 'data-acao="verificacao"' in html


def test_a_tela_do_chamado_tem_as_acoes_da_os(fr, fila):
    cli = _cliente()
    cli.get(URL)
    html = cli.get(URL + "/9104").get_data(as_text=True)
    caixa = html.split("<h2>Ações da OS</h2>", 1)[1].split("</section>", 1)[0]
    for a in ("anexos-os", "anexos-sub", "anexo-incluir", "verificacao", "cancelar"):
        assert 'data-acao="%s"' % a in caixa, a
    # sem o Concluir: o "Finalizar chamado" do topo já conclui a OS no Fracttal (dois finalizar confundiriam)
    assert 'data-acao="concluir"' not in caixa
    assert re.search(r'data-acao="anexo-incluir"[^>]*title="[^"]*até 10 MB cada', caixa)
    assert '<span class="det-ajuda">PDF' not in caixa
    for dlg in ("verificacao", "cancelar", "anexos"):
        assert '<template data-dlg="%s">' % dlg in caixa, dlg
    assert "data-no-lugar" in html.split("<h2>Ações da OS</h2>", 1)[0].rsplit("<section", 1)[1]


def test_a_moldura_do_card_abre_so_nas_acoes_do_card(cliente):
    from test_engenharia_acompanhamento import ANA
    from test_engenharia_os_analise import _pela_microsoft
    c = _pela_microsoft(cliente, ANA) or cliente
    assert 'data-acao="concluir"' in c.get("/os/_nexus/card/15088?acao=concluir").get_data(as_text=True)
    assert 'data-acao=""' in c.get("/os/_nexus/card/15088?acao=apagar-tudo").get_data(as_text=True)
