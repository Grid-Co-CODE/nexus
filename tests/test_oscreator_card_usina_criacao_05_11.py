"""O card da OS diz a usina, a data de criação e quanto já foi feito (Levi, 05/11/2026: "No card da OS quando clicamos nela,
no campo de ativos poderia ter um espaço para falar qual a usina, as vezes clico na OS sem contexto e não sei que usina é.
adicione também data de criação da OS"; "Usina sempre acima dos ativos! pois a usina é mais importante"; e a barra "tipo
barra de bateria do celular" no card da duração). A usina é a da coluna Usina do Histórico (o catálogo central, pelo código
de cada ativo da OS); a data de criação, a do cabeçalho da OS; a bateria, as subtarefas concluídas. O Fracttal é de mentira
(o dos testes do card); nomes, códigos e usinas inventados."""
import re
from types import SimpleNamespace

from test_oscreator_card_tarefas import JWT, WID, Fracttal, _card, _item, _tarefa, api, criar_app  # noqa: F401

LOCAL = {"TST-INV1.1": ("Cliente Teste", "Usina Alfa", "Inversor"), "TST-INV1.2": ("Cliente Teste", "Usina Alfa", "Inversor"),
         "TST-INV1.3": ("Cliente Teste", "Usina Beta", "Inversor")}


class _ComCriacao(Fracttal):
    """O cabeçalho da OS com a data de criação (UTC, como o Fracttal devolve)."""

    def rpc(self, metodo, params, timeout=45):
        if metodo == api.RPC_WO_DETAILS:
            return {"data": [{"id": WID, "labels": [], "created_by": "Pessoa Teste", "creation_date": "2026-10-29T20:40:00"}]}
        return super().rpc(metodo, params, timeout)


def _catalogo(monkeypatch, local=LOCAL):
    cat = SimpleNamespace(local_por_codigo=local) if local is not None else None
    monkeypatch.setattr(api.ativos_central, "atual", lambda: cat)


def _banner(html):
    return html[html.index('class="det-card det-banner"'):html.index('class="det-cols"')]


def test_o_card_diz_a_usina_e_a_data_de_criacao(monkeypatch):
    _catalogo(monkeypatch)
    monkeypatch.setattr(api, "_rpc_call", _ComCriacao([_tarefa(1)], [_item(1, 1)]).rpc)
    html = _card()
    b = _banner(html)
    assert "Usina</span>" in b and '<b class="det-banner-t">Usina Alfa</b>' in b
    assert b.index("Usina Alfa") < b.index("Inversor 1.1")                       # a usina em cima do ativo
    assert '<span class="det-banner-ativo">Inversor 1.1</span>' in b and 'class="det-banner-code">TST-INV1.1<' in b
    linha = html[html.index("data-criada"):][:400]
    assert "Data de criação" in linha and "29/10/2026 17:40" in linha              # 20:40 UTC = 17:40 em Brasília


def test_a_os_de_varios_ativos_diz_cada_usina_uma_vez(monkeypatch):
    _catalogo(monkeypatch)
    monkeypatch.setattr(api, "_rpc_call", _ComCriacao([_tarefa(k) for k in (1, 2, 3)], [_item(k, 1) for k in (1, 2, 3)]).rpc)
    b = _banner(_card())
    assert "Usinas</span>" in b and '<b class="det-banner-t">Usina Alfa · Usina Beta</b>' in b
    assert b.index("Usina Beta") < b.index("3 ativos") and "det-banner-code" not in b   # sem o código: são vários ativos


def test_sem_o_catalogo_o_card_fica_como_antes(monkeypatch):
    """O catálogo de ativos ainda não carregou (o servidor acabou de subir): o card não espera a carga e fica como era, com o
    código à direita; a linha da data de criação fica, com o traço quando o cabeçalho não a traz."""
    _catalogo(monkeypatch, local=None)
    monkeypatch.setattr(api, "_rpc_call", Fracttal([_tarefa(1)], [_item(1, 1)]).rpc)
    html = _card()
    b = _banner(html)
    assert "det-banner-usina" not in b and '<span class="det-banner-t">Inversor 1.1</span>' in b
    assert 'class="det-banner-code">TST-INV1.1<' in b
    linha = html[html.index("data-criada"):][:400]
    assert "Data de criação" in linha and "—" in linha


def test_a_primeira_pintura_tambem_diz(monkeypatch):
    """A 1ª pintura do card (a linha da lista central, antes da leitura ao vivo) já mostra as duas, para o card não pular."""
    from os_web import lista_central
    linha = {"folio": 15900, "tipo_tarefa": "Corretiva", "status": "Em Processo", "ativo": "Inversor 1.1", "code": "TST-INV1.1",
             "usina": "Usina Alfa", "event_date": "2026-10-30T09:00:00", "data_fim": None, "atribuido_a": "",
             "criado_por": "Pessoa Teste", "data": "2026-10-29T20:40:00", "descricao": "Teste"}
    monkeypatch.setattr(lista_central, "previa", lambda wid: dict(linha))
    c = criar_app(segredo="teste", testing=True).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": ""}
    r = c.get("/os/api/os/%d/previa" % WID)
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert '<b class="det-banner-t">Usina Alfa</b>' in html and "Data de criação" in html and "29/10/2026 17:40" in html
    assert html.index("Usina Alfa") < html.index("Inversor 1.1")
    linha["usina"] = "—"                                                           # a lista sem o catálogo: como antes
    html = c.get("/os/api/os/%d/previa" % WID).get_data(as_text=True)
    assert "det-banner-usina" not in html and '<span class="det-banner-t">Inversor 1.1</span>' in html


def _bateria(html):
    caixa = html[html.index("data-bateria="):]
    caixa = caixa[:caixa.index('<div class="det-etq-l">')]
    estado = re.match(r'data-bateria="([a-z]+)"', caixa).group(1)
    recheio = re.search(r'class="det-prog-f( parcial)?" style="width:(\d+)%"', caixa)
    return estado, recheio and (recheio.group(2), bool(recheio.group(1))), re.sub(r"<[^>]+>|\s+", " ", caixa)


def test_a_bateria_diz_quanto_da_os_foi_feito(monkeypatch):
    """A bateria à direita da duração: cheia e verde com tudo feito, laranja no meio, vazia sem nada feito e tracejada na OS
    sem subtarefas (Levi, 05/11/2026: "tipo barra de bateria do celular")."""
    _catalogo(monkeypatch)
    casos = [([_item(1, 1, feito=True), _item(1, 2, feito=True)], "cheia", ("100", False), "2 de 2 subtarefas"),
             ([_item(1, 1, feito=True), _item(1, 2)], "parcial", ("50", True), "1 de 2 subtarefas"),
             ([_item(1, 1), _item(1, 2)], "zerada", ("0", True), "0 de 2 subtarefas"),
             ([], "vazia", None, "OS sem subtarefas")]
    for itens, estado, recheio, texto in casos:
        monkeypatch.setattr(api, "_rpc_call", _ComCriacao([_tarefa(1)], itens).rpc)
        e, r, txt = _bateria(_card())
        assert (e, r) == (estado, recheio), estado
        assert texto in txt and (("%s%%" % recheio[0]) in txt if recheio else " — " in txt), estado
