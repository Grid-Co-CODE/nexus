"""O "Abrir chamado" volta ao card da OS (Levi, 10/11/2026: "Quero que no card da OS do histórico de OS do OS Creator tenha
um botão de 'Abri Chamado' no extremo esquerdo lá em baixo onde a pessoa será levada para a parte de Inspeção de OS da
parte de chamados, a parte de OS pai já vai preenchida com a OS que ela estava e faz todo o carregamento"). Tinha saído em
29/10/2026. O Fracttal é de mentira."""
from test_oscreator_card_tarefas import WID, Fracttal, _card, _item, _tarefa  # noqa: F401
from test_oscreator_solic_pcm import WEB, api  # noqa: F401


def test_o_abrir_chamado_no_canto_esquerdo_do_rodape(monkeypatch):
    monkeypatch.setattr(api, "_rpc_call", Fracttal([_tarefa(1)], [_item(1, 1)]).rpc)
    h = _card()
    rodape = h[h.index('<footer class="det-foot">'):h.index("</footer>")]
    link = '<a class="det-b ambar det-chamado" href="/os/chamados/inspecao?pai=15900"'
    assert link in rodape and ">Abrir chamado</a>" in rodape
    # o 1º do rodapé: antes da contagem das subtarefas e de todos os botões
    assert rodape.index(link) < rodape.index('class="det-ajuda"') < rodape.index('data-acao="fluxo"')


def test_a_inspecao_abre_com_a_os_pai_do_endereco():
    """A tela da Inspeção recebe o nº pelo `?pai=` e o insp.js carrega a OS pai (o ativo, a data e o responsável)."""
    js = (WEB / "static" / "insp.js").read_text(encoding="utf-8")
    assert "/os/api/insp/pai?folio=" in js
    html = (WEB / "templates" / "insp.html").read_text(encoding="utf-8")
    assert "pai" in html
