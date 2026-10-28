"""O card da OS de vários ativos mostra as subtarefas POR ATIVO (Levi, 28/10/2026: "No OS creator, quando a OS tem mais de
um ativo e eu abro o card da OS não diferencia. Tem que dar para ver as subtarefas por ativo").

O caso: a OS de "Verificação de Tracker Parado" em dois trackers. As duas tarefas têm o mesmo título; o card de 08/10
mostrava o título em destaque e o ativo pequeno embaixo, com as subtarefas fechadas, e o banner do topo com um ativo só.
Agora, com mais de um ativo, cada tarefa abre pelo nome do ATIVO (o título vai embaixo), o banner diz quantos e quais,
e com até 4 ativos as subtarefas de cada um já vêm abertas. Com um ativo só (várias tarefas no mesmo ativo), fica como
era. O Fracttal é de mentira (o dos testes do card de 08/10); nomes e códigos inventados."""
import re

from test_oscreator_card_tarefas import WID, Fracttal, _blocos, _card, _item, _tarefa, api  # noqa: F401

WEB = __import__("pathlib").Path(api.__file__).parent / "os_web"


def _os(monkeypatch, tarefas, itens):
    monkeypatch.setattr(api, "_rpc_call", Fracttal(tarefas, itens).rpc)
    return _card()


def test_dois_ativos_com_o_mesmo_titulo_abrem_pelo_ativo(monkeypatch):
    t = "Verificação de Tracker Parado"
    html = _os(monkeypatch, [_tarefa(1, titulo=t, fim="2026-10-27T10:00:00", inicio="2026-10-27T09:00:00"), _tarefa(2, titulo=t)],
               [_item(k, n, feito=(k == 1)) for k in (1, 2) for n in (1, 2)])
    assert "SUBTAREFAS POR ATIVO (2)" in html and "clique no ativo" in html
    blocos = _blocos(html)
    assert len(blocos) == 2
    for k, (_tid, b) in enumerate(blocos, 1):
        topo = b[:b.index("</summary>")]
        assert re.search(r"<b>Inversor 1\.%d[^<]*</b><small>%s</small>" % (k, t), topo), topo      # o ativo em destaque
        assert re.match(r'<details class="det-tarefa[^"]*" data-tarefa="[^"]*" open>', b)          # já aberta
        assert b.count('<details class="det-sub') == 2
    banner = html[html.index('class="det-card det-banner"'):]
    banner = banner[:banner.index("</div>")]
    assert "2 ativos" in banner and "Inversor 1.1" in banner and "Inversor 1.2" in banner


def test_muitos_ativos_seguem_pelo_ativo_mas_fechados(monkeypatch):
    html = _os(monkeypatch, [_tarefa(k) for k in range(1, 7)], [_item(k, n) for k in range(1, 7) for n in (1, 2)])
    assert "SUBTAREFAS POR ATIVO (6)" in html
    blocos = _blocos(html)
    assert all(re.match(r'<details class="det-tarefa[^"]*" data-tarefa="[^"]*">', b) for _t, b in blocos)   # fechadas
    assert re.search(r"<b>Inversor 1\.3[^<]*</b>", blocos[2][1])


def test_varias_tarefas_no_mesmo_ativo_ficam_como_eram(monkeypatch):
    t1, t2 = _tarefa(1, titulo="Limpeza do inversor"), _tarefa(2, titulo="Medição de isolação")
    t2.update(items_description=t1["items_description"], code_item=t1["code_item"])
    html = _os(monkeypatch, [t1, t2], [_item(k, n) for k in (1, 2) for n in (1, 2)])
    assert "TAREFAS (2)" in html and "SUBTAREFAS POR ATIVO" not in html
    assert "<b>Limpeza do inversor</b>" in html and "<b>Medição de isolação</b>" in html
    assert " ativos" not in html[html.index('class="det-card det-banner"'):][:400]


def test_a_clonagem_de_planos_tem_a_noite_17h():
    """Levi, 28/10/2026: "Em OS Creator > PCM > Clonagem de Planos > Em 'Plano de tarefas' quero a opção Noite 17:00"."""
    html = (WEB / "templates" / "pcm.html").read_text(encoding="utf-8")
    js = (WEB / "static" / "pcm.js").read_text(encoding="utf-8")
    assert html.index('id="b_tarde"') < html.index('id="b_noite"') < html.index('id="b_mes"')
    assert "Noite (17:00)" in html
    assert "$('b_noite').onclick = () => editores((v) => v.slice(0, 10) + 'T17:00');" in js
