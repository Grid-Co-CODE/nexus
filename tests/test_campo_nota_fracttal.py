"""Nota do fechamento calculada com o que o Fracttal guarda (Levi, 04/10/2026: "tá óbvio que vem do Fracttal com
métricas bem estabelecidas, é só copiar a regra").

As réguas são as do App, copiadas sem mudar linha: a do PAINEL (`_qualidade_os`, a que o App grava no registro e as
telas mostram) e a do PLACAR (`_qualidade_v2`). O que se testa aqui é o TRADUTOR: as linhas do REST do Fracttal
(work_orders_subtasks e work_orders_attachments, nos campos medidos em 04/10) viram o mesmo fechamento que o App
montaria. A assinatura entra como dada: o App não deixa concluir sem ela.
"""
import re

import pytest

from nexus.campo import fracttal, nota_fracttal as nf

TAREFA = 59786252
GPS = " · GPS -5.123456,-42.654321 · 2026-10-02T14:33:12.000Z"


def _sub(i, desc, tipo, valor, obrigatoria=True, tarefa=TAREFA):
    """Uma subtarefa como o REST devolve em work_orders_subtasks/?folio=."""
    return {"id_work_orders_tasks_form_items": 900 + i, "id_work_order_task": tarefa, "description": desc,
            "id_task_form_item_type": tipo, "value": valor, "is_required": obrigatoria, "order_number": i,
            "wo_folio": "15377"}


def _foto(texto, tarefa=TAREFA):
    """Um anexo como o REST devolve em work_orders_attachments?folio=: o App grava desc · GPS · hora."""
    return {"id_work_order_task": tarefa, "description": texto, "type": 1, "value": "https://s3/x.jpg",
            "wo_folio": "15377"}


def _checklist_ok():
    return [_sub(1, "Inspeção visual do inversor", 4, "1"), _sub(2, "Teste funcional", 4, "1"),
            _sub(3, "Limpeza executada", 2, "true"), _sub(4, "Observações gerais", 1, "Tudo certo na visita")]


def _item(n, rot):
    return next(i for i in n["itens"] if i["rot"] == rot)


def test_tipos_sao_os_do_app():
    # campo.html, formItemsParaChecklist: const TP={1:'texto',2:'check',3:'num',4:'verif',5:'num',6:'texto',...}
    assert nf.TIPO_DO_FRACTTAL == {1: "texto", 2: "check", 3: "num", 4: "verif", 5: "num", 6: "texto",
                                   7: "dropdown", 8: "date", 9: "check"}


@pytest.mark.parametrize("valor,tipo,esperado", [
    ("true", "check", True), ("1", "check", True), ("false", "check", False),
    ("2", "verif", 2), ("7", "verif", None), ("", "texto", None), (None, "num", None), (" abc ", "texto", "abc")])
def test_valor_como_o_app_le(valor, tipo, esperado):
    assert nf.valor_do_app(valor, tipo) == esperado


@pytest.mark.parametrize("valor,esperado", [
    ("Não se aplica", (None, True)), ("1 · foto: não se aplica", ("1", True)), ("Aprovado", ("Aprovado", False)),
    (None, (None, False))])
def test_nao_se_aplica_sai_do_valor(valor, esperado):
    # o App grava o "não se aplica" dentro do próprio campo (_valor_por_tipo / submeter_subtarefas)
    assert nf.separar_nao_se_aplica(valor) == esperado


def test_descricao_e_gps_da_foto():
    assert nf.descricao_da_foto("Inversor 3 — fusível queimado" + GPS) == (
        "Inversor 3 — fusível queimado", (-5.123456, -42.654321))
    assert nf.descricao_da_foto("GPS -5.1,-42.6 · 2026-10-02T14:33:12Z") == ("", (-5.1, -42.6))
    assert nf.descricao_da_foto("foto da string 4") == ("foto da string 4", None)


def test_nota_do_painel_e_do_placar():
    n = nf.nota(_checklist_ok(), [_foto("String 4 limpa" + GPS), _foto("Painel após limpeza" + GPS)])
    # painel: subtarefas 25 + fotos 20×2/3 + descrição 10 + assinatura 10 + observação 15 + GPS 20 = 93,3
    assert n["q"] == 93
    assert [(i["rot"], i["pts"]) for i in n["itens"]] == [
        ("Subtarefas obrigatórias", 25), ("Fotos", 13.3), ("Fotos com descrição", 10), ("Assinatura", 10),
        ("Observações", 15), ("GPS no fechamento", 20)]
    # placar (01/09): sem falha não entra a observação; 2 fotos sem nenhuma exigida contam inteiras
    assert n["placar"]["q"] == 100 and n["placar"]["pontos"] == 40
    assert n["n_fotos"] == 2 and n["n_desc"] == 2 and n["geo_ok"] and n["sub_ok"] and n["todas"] and n["obs_ok"]


def test_tres_fotos_dao_o_total_de_foto():
    fotos = [_foto(f"Foto {i}" + GPS) for i in range(3)]
    assert nf.nota(_checklist_ok(), fotos)["q"] == 100


def test_foto_sem_descricao_perde_a_descricao():
    fotos = [_foto("GPS -5.1,-42.6 · 2026-10-02T14:33:12Z") for _ in range(3)]
    n = nf.nota(_checklist_ok(), fotos)
    assert n["q"] == 90 and _item(n, "Fotos com descrição")["pts"] == 0


def test_a_assinatura_entra_como_dada():
    # o App não deixa concluir sem assinar (campo.html, travasSheet); a leitura do Fracttal é que não a devolve
    assert _item(nf.nota(_checklist_ok(), []), "Assinatura")["pts"] == 10


def test_nao_se_aplica_nao_conta_como_resposta():
    subs = _checklist_ok()
    subs[1]["value"] = "Não se aplica"
    n = nf.nota(subs, [_foto("x" + GPS)])
    assert _item(n, "Subtarefas obrigatórias")["det"] == "3 de 4 respondidas"
    assert next(i for i in n["placar"]["itens"] if i["rot"] == "sub")["det"] == "3 de 4 respondidas, 1 NA"


def test_falha_sem_descrever_perde_a_observacao():
    subs = _checklist_ok()
    subs[0]["value"] = "3"                       # Falha
    subs[3]["value"] = "ok"                      # menos de 20 caracteres
    n = nf.nota(subs, [_foto("x" + GPS)])
    assert _item(n, "Observações")["pts"] == 1.5 and not n["obs_ok"]
    obs = next(i for i in n["placar"]["itens"] if i["rot"] == "obs")
    assert obs["pts"] == 0 and "NAO descreveu" in obs["det"]


def test_observacao_do_checklist_conta_quando_ha_falha():
    subs = _checklist_ok()
    subs[0]["value"] = "2"                       # Alerta
    subs[3]["value"] = "Conector MC4 derretido na string 4, trocado"
    n = nf.nota(subs, [_foto("x" + GPS)])
    assert next(i for i in n["placar"]["itens"] if i["rot"] == "obs")["pts"] == 20 and n["obs_ok"]


def test_foto_de_subtarefa_so_tem_descricao_quando_o_tecnico_escreveu():
    # a foto de campo nasce com o nome do campo; "campo — nota" é que é descrição do técnico (_contar_fotos do App)
    fotos = [_foto("Inspeção visual do inversor" + GPS), _foto("Inspeção visual do inversor — tampa trincada" + GPS)]
    n = nf.nota(_checklist_ok(), fotos)
    assert (n["n_fotos"], n["n_desc"]) == (2, 1)


def test_foto_de_outra_tarefa_nao_entra():
    n = nf.nota(_checklist_ok(), [_foto("String 4" + GPS), _foto("Outra" + GPS, tarefa=1)], tarefa=TAREFA)
    assert n["n_fotos"] == 1


def test_sem_gps_nas_fotos_perde_o_gps_e_nao_pontua():
    n = nf.nota(_checklist_ok(), [_foto("String 4 limpa · 2026-10-02T14:33:12Z")])
    assert not n["geo_ok"] and _item(n, "GPS no fechamento")["pts"] == 0
    assert n["q"] == 67 and n["placar"]["pontos"] == 0


def test_o_que_o_fracttal_nao_tem_fica_dito():
    assert any("caixa do App" in f for f in nf.nota(_checklist_ok(), [])["fora"])


class FracttalDaOS:
    """REST do Fracttal para uma OS: tarefas, subtarefas e anexos, em páginas de `limit` pelo start=."""

    def __init__(self, subtarefas, anexos, limite=100):
        self.subs, self.anexos, self.limite, self.pedidos = subtarefas, anexos, limite, []

    def __call__(self, path):
        self.pedidos.append(path)
        ini = int((re.search(r"start=(\d+)", path) or [0, 0])[1])
        if path.startswith("work_orders?wo_folio="):
            return {"total": 1, "data": [{"id_work_orders_tasks": TAREFA, "wo_folio": "15377"}]}
        fonte = self.subs if path.startswith("work_orders_subtasks/") else self.anexos
        return {"total": len(fonte), "data": fonte[ini:ini + self.limite]}


def test_le_a_os_inteira_pagina_por_pagina():
    subs = [_sub(i, f"Item {i}", 1, "x") for i in range(150)]
    fx = FracttalDaOS(subs, [_foto("x" + GPS)])
    fracttal.usar_fornecedor(fx)
    try:
        os_ = nf.ler_os("15377")
    finally:
        fracttal.usar_fornecedor(None)
    assert len(os_["subtarefas"]) == 150 and len(os_["anexos"]) == 1
    assert [p for p in fx.pedidos if p.startswith("work_orders_subtasks/")] == [
        "work_orders_subtasks/?folio=15377&limit=100&start=0", "work_orders_subtasks/?folio=15377&limit=100&start=100"]


def test_notas_da_os_uma_por_tarefa():
    fx = FracttalDaOS(_checklist_ok(), [_foto(f"Foto {i}" + GPS) for i in range(3)])
    fracttal.usar_fornecedor(fx)
    try:
        notas = nf.notas_da_os("15377")
    finally:
        fracttal.usar_fornecedor(None)
    assert list(notas) == [TAREFA] and notas[TAREFA]["q"] == 100
