"""O card da OS com VÁRIAS tarefas (Levi, 08/10/2026: "Nas OSs que aparecem no OS Creator Web quando a OS tem mais que
uma tarefa está duplicando as subtarefas e não aparecendo as tarefas, tem que dividir por tarefa quando clicar!").

A causa, provada no REST do Fracttal (só leitura, 08/10/2026): o `order_number` das subtarefas RECOMEÇA em 1 em cada
tarefa, e o `api.get_os_detalhes` ordenava as subtarefas da OS inteira por ele. As tarefas se intercalavam: numa OS de 8
tarefas iguais (a mesma coleta em 8 inversores: 16 subtarefas, 16 ids diferentes, 2 por tarefa), a 1ª pergunta saía 8
vezes seguidas e depois a 2ª, mais 8, sem dizer de qual tarefa era cada uma. E o card não agrupava nada: as tarefas só
apareciam numa tabela solta, depois da lista. Não é regressão das duas levas paralelas (ced4a6b): os pedidos e a
resposta são os mesmos; a ordenação e o card são assim desde que o card nasceu na web.

O Fracttal daqui é de mentira, no formato que o REST mostrou (ids, `order_number` por tarefa, a mesma pergunta em todas
as tarefas). Nomes e códigos são inventados: o repositório é público. Nenhum teste vai à rede."""
import re
import sys

import pytest

from nexus.torres.oscreator import ponte

pytest.importorskip("PyQt6")          # o clone importa o steps/ui.py do OS Creator ao montar a tela de Engenharia
if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import criar_app  # noqa: E402
from os_web import os_acoes_web as regra  # noqa: E402

JWT = "aaa.eyJlbWFpbCI6InRlc3RlQGV4ZW1wbG8uaW52YWxpZCIsImV4cCI6OTk5OTk5OTk5OX0.sig"   # de mentira
WID, T0 = 9101, 70000
PERGUNTAS = ("Registre a geração diária do inversor", "A coleta do período ficou completa?")


def _tarefa(k, inicio=None, fim=None, titulo="Coleta de dados de geração"):
    """Uma linha do `work_orders_tasks_new_list`, com o que o card lê."""
    return {"id": T0 + k, "id_work_order_task": T0 + k, "wo_folio": 15900, "tasks_description": titulo,
            "tasks_types_main_description": "Administrativa", "items_description": "Inversor 1.%d { TST-INV1.%d }" % (k, k),
            "code_item": "TST-INV1.%d" % k, "personnel_description": "Pessoa Teste", "id_status_work_order": 1,
            "initial_date": inicio, "final_date": fim, "date_maintenance": "2026-10-09T08:00:00", "note": ""}


def _item(k, n, feito=False, fid=None, descricao=None):
    """Uma subtarefa (form item) da tarefa `k`, na posição `n` DELA: o `order_number` recomeça em cada tarefa."""
    return {"description": descricao or PERGUNTAS[n - 1], "done": "true" if feito else "false",
            "value": "1" if feito else None, "order_number": n, "id_work_order_task": T0 + k,
            "id_work_orders_tasks_form_items": fid or 800000 + 10 * k + n, "id_task_form_item_type": 4 if n == 2 else 1}


class Fracttal:
    """Responde ao que o card pede. As subtarefas vêm agrupadas por tarefa, como o REST as devolve."""

    def __init__(self, tarefas, itens):
        self.tarefas, self.itens = tarefas, itens

    def rpc(self, metodo, params, timeout=45):
        if metodo == api.RPC_WO_TASKS:
            return {"data": self.tarefas}
        if metodo == api.RPC_WO_FORMIT:
            return {"data": self.itens}
        if metodo == api.RPC_WO_DETAILS:
            return {"data": [{"id": WID, "labels": [], "created_by": "Pessoa Teste"}]}
        if metodo == api.RPC_REQ_LIST:
            return {"data": []}
        raise AssertionError("pedido que o card não faz: " + metodo)


def _oito_tarefas():
    """A OS de 8 tarefas iguais: a 1ª já começou, a 2ª terminou com as duas subtarefas feitas, as outras nem começaram."""
    tarefas = [_tarefa(1, inicio="2026-10-08T09:00:00")] + [_tarefa(2, inicio="2026-10-08T09:00:00",
                                                                     fim="2026-10-08T09:40:00")]
    tarefas += [_tarefa(k) for k in range(3, 9)]
    itens = [_item(k, n, feito=(k == 2)) for k in range(1, 9) for n in (1, 2)]
    return tarefas, itens


@pytest.fixture
def fracttal(monkeypatch):
    f = Fracttal(*_oito_tarefas())
    monkeypatch.setattr(api, "_rpc_call", f.rpc)
    return f


def _card(status="Em Processo", app=None):
    c = (app or criar_app(segredo="teste", testing=True)).test_client()
    with c.session_transaction() as s:
        s["jwt"] = JWT
        s["conta"] = {"nome": "Pessoa Teste", "email": "teste@exemplo.invalid", "perfil": ""}
    r = c.get("/os/os/%d?parcial=1&status=%s" % (WID, status))
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _blocos(html):
    """[(id da tarefa, HTML do bloco)] na ordem do card. O último bloco vai até os anexos."""
    marcas = [(m.start(), m.group(1)) for m in re.finditer(r'<details class="det-tarefa[^"]*" data-tarefa="([^"]*)"', html)]
    fim = html.index("ANEXOS DA OS")
    return [(tid, html[ini:(marcas[i + 1][0] if i + 1 < len(marcas) else fim)]) for i, (ini, tid) in enumerate(marcas)]


# ── a leitura: cada subtarefa uma vez, na tarefa dela ─────────────────────────────────────────────────────────────────
def test_as_subtarefas_vem_agrupadas_pela_tarefa_e_nao_intercaladas(fracttal):
    d = api.get_os_detalhes(WID)
    # antes: [70001, 70002, ..., 70008, 70001, ..., 70008] (ordenado só pelo order_number, que recomeça em cada tarefa)
    assert [s["id_tarefa"] for s in d["subtarefas"]] == [T0 + k for k in range(1, 9) for _ in (1, 2)]
    assert [s["descricao"] for s in d["subtarefas"][:4]] == [PERGUNTAS[0], PERGUNTAS[1], PERGUNTAS[0], PERGUNTAS[1]]
    assert len({s["id_form_item"] for s in d["subtarefas"]}) == 16 and len(d["tarefas"]) == 8


def test_a_ordem_vem_da_tarefa_mesmo_com_o_fracttal_embaralhado(fracttal):
    fracttal.itens = list(reversed(fracttal.itens))
    d = api.get_os_detalhes(WID)
    assert [(s["id_tarefa"], s["descricao"]) for s in d["subtarefas"][:2]] == [(T0 + 1, PERGUNTAS[0]), (T0 + 1, PERGUNTAS[1])]


def test_subtarefa_repetida_na_resposta_conta_uma_vez(monkeypatch):
    """Guarda, não a causa: o REST não repete subtarefa (16 ids em 16 linhas, 45 em 45 na OS de 13 tarefas), e o RPC do
    card não deu para ler. A mesma subtarefa (o mesmo id do form item) duas vezes na resposta vale uma vez só, na lista,
    na barra e no Concluir."""
    itens = [_item(1, 1, feito=True), _item(1, 2), _item(1, 1, feito=True)]
    monkeypatch.setattr(api, "_rpc_call", Fracttal([_tarefa(1)], itens).rpc)
    d = api.get_os_detalhes(WID)
    assert [s["id_form_item"] for s in d["subtarefas"]] == [800011, 800012]
    html = _card()
    assert html.count('<details class="det-sub') == 2 and "1 de 2 concluídas" in html and "1 de 2 subtarefas concluídas" in html
    assert "2 subtarefa(s)" in html


# ── o card ────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_card_de_varias_tarefas_mostra_as_tarefas_e_cada_uma_abre_as_suas_subtarefas(fracttal):
    html = _card()
    blocos = _blocos(html)
    assert [tid for tid, _ in blocos] == [str(T0 + k) for k in range(1, 9)]          # as 8 tarefas, na ordem da OS
    corpo = html[html.index('class="det-corpo"'):html.index("ANEXOS DA OS")]
    assert corpo.count('<details class="det-sub') == 16                                      # cada subtarefa uma vez só
    assert '<details class="det-sub' not in corpo[:corpo.index('class="det-tarefa')]          # nenhuma solta, fora da tarefa
    for k, (tid, b) in enumerate(blocos, 1):
        assert b.count('<details class="det-sub') == 2, tid                                   # só as DELA
        assert "Inversor 1.%d" % k in b and "Coleta de dados de geração" in b
        assert b.count(PERGUNTAS[0]) == 1 and b.count(PERGUNTAS[1]) == 1
        assert 'data-fid="%d"' % (800000 + 10 * k + 1) in b
        assert "<summary" in b                                                        # o clique e o teclado (Enter/Espaço)
    situacao = {tid: re.search(r'class="det-situ [a-z]+">([^<]+)<', b).group(1) for tid, b in blocos}
    assert situacao[str(T0 + 1)] == "Iniciada" and situacao[str(T0 + 2)] == "Finalizada"
    assert situacao[str(T0 + 3)] == "Não iniciada"
    contagem = {tid: re.search(r'class="det-tarefa-c[^"]*">([^<]+)<', b).group(1) for tid, b in blocos}
    assert contagem[str(T0 + 2)] == "2 de 2 concluídas" and contagem[str(T0 + 1)] == "0 de 2 concluídas"
    # a barra e o "X de Y" contam a OS inteira, cada subtarefa uma vez
    assert "2 de 16 subtarefas concluídas" in html and 'style="width:12%"' in html
    assert "16 subtarefa(s) em 8 tarefas" in html
    assert "<th>Programada</th>" not in html                                          # a tabela solta saiu: o que ela dizia está na tarefa


def test_card_de_varias_tarefas_ainda_mostra_tipo_programada_e_execucao_de_cada_uma(fracttal):
    b = dict(_blocos(_card()))[str(T0 + 2)]
    assert "Administrativa" in b and "09/10/2026" in b and "08/10/2026" in b


def test_concluir_diz_de_qual_tarefa_e_cada_pendencia(fracttal):
    """O diálogo do Concluir listava as pendentes pela descrição: numa OS de tarefas iguais, a mesma frase 6 vezes. E o
    "Fazer a tarefa" de cada uma tinha o mesmo título nas 8, como o aviso das tarefas sem data de fim. O rótulo leva o
    ativo quando o título se repete."""
    html = _card()
    dlg = html[html.index('data-dlg="concluir"'):html.index('data-dlg="executar"')]
    assert "2 de 16 subtarefas concluídas" in dlg and "14 subtarefas que ficam pendentes" in dlg
    pend = re.findall(r"<li>(.*?)</li>", dlg)
    assert len(pend) == 6 and "Inversor 1.1" in pend[0] and "Inversor 1.3" in pend[2]
    fazer = re.findall(r'data-fazer-titulo="([^"]+)"', dlg)
    assert len(fazer) == 3 and len(set(fazer)) == 3
    assert all(t.startswith("Coleta de dados de geração · Inversor 1.") for t in fazer)
    assert ("<b>7 tarefas</b> desta OS vão fechar <b>sem data de fim</b>" in dlg
            and "geração · Inversor 1.1; Coleta de dados de geração · Inversor 1.3; " in dlg)


def test_subtarefa_sem_tarefa_conhecida_aparece_num_grupo_proprio(fracttal):
    fracttal.itens = fracttal.itens + [dict(_item(1, 3, descricao="Pergunta de tarefa que não veio"),
                                            id_work_order_task=99999)]
    html = _card()
    blocos = _blocos(html)
    assert [tid for tid, _ in blocos][-1] == "sem-tarefa"
    assert "Pergunta de tarefa que não veio" in blocos[-1][1] and "Subtarefas sem tarefa identificada" in blocos[-1][1]
    assert "2 de 17 subtarefas concluídas" in html


def test_servico_antigo_com_o_template_novo_abre_o_card_com_a_lista_direta(fracttal):
    """A cópia chega ao 5090 (e ao 5070) sem reiniciar o serviço: o template que ainda não estava na memória sai do disco,
    novo, e o Python segue o antigo, sem as funções das tarefas. O card abre com a lista de antes, e não com erro."""
    app = criar_app(segredo="teste", testing=True)
    for nome in ("acoes_grupos_tarefas", "acoes_rotulos_tarefas"):
        app.jinja_env.globals.pop(nome)
    html = _card(app=app)
    assert "det-tarefa" not in html and html.count('<details class="det-sub') == 16 and "SUBTAREFAS" in html


def test_card_de_uma_tarefa_continua_com_a_lista_direta(monkeypatch):
    """A esmagadora maioria (corretiva de tracker, religamento): o card não muda."""
    monkeypatch.setattr(api, "_rpc_call", Fracttal([_tarefa(1)], [_item(1, 1, feito=True), _item(1, 2)]).rpc)
    html = _card()
    assert "det-tarefa" not in html and html.count('<details class="det-sub') == 2
    assert "SUBTAREFAS" in html and "1 de 2 concluídas" in html and "1 de 2 subtarefas concluídas" in html
    assert "2 subtarefa(s)<" in html and "em 1 tarefas" not in html


# ── as regras, puras ──────────────────────────────────────────────────────────────────────────────────────────────────
def test_situacao_da_tarefa_pelas_datas_de_execucao():
    assert regra.situacao_tarefa({"inicio": "", "fim": ""}) == ("Não iniciada", "nao")
    assert regra.situacao_tarefa({"inicio": "2026-10-08T09:00:00", "fim": None}) == ("Iniciada", "and")
    assert regra.situacao_tarefa({"inicio": "2026-10-08T09:00:00", "fim": "2026-10-08T10:00:00"}) == ("Finalizada", "ok")


def test_rotulo_da_tarefa_leva_o_ativo_so_quando_o_titulo_se_repete():
    r = regra.rotulos_tarefas([{"id": 1, "titulo": "Coleta", "ativo": "Inversor 1.1"},
                               {"id": 2, "titulo": "Coleta", "ativo": "Inversor 1.2"},
                               {"id": 3, "titulo": "Limpeza", "ativo": "Cabine 1"}, {"id": 4, "titulo": "", "ativo": ""}])
    assert r == {1: "Coleta · Inversor 1.1", 2: "Coleta · Inversor 1.2", 3: "Limpeza", 4: "Tarefa 4"}


def test_grupos_nao_repetem_subtarefa_nem_tarefa():
    d = {"tarefas": [{"id": 1, "titulo": "A"}, {"id": 2, "titulo": "B"}, {"id": 1, "titulo": "A"}],
         "subtarefas": [{"id_tarefa": 1, "feito": True, "descricao": "x"}, {"id_tarefa": 2, "feito": False, "descricao": "y"},
                        {"id_tarefa": None, "feito": False, "descricao": "z"}]}
    g = regra.subtarefas_por_tarefa(d)
    assert [(x["id"], x["total"], x["feitas"]) for x in g] == [(1, 1, 1), (2, 1, 0), (None, 1, 0)]
    assert sum(x["total"] for x in g) == len(d["subtarefas"])
