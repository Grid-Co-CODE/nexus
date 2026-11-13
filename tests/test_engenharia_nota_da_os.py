"""A nota da OS no Fracttal tem DOIS campos, e o Nexus regravava a junção dos dois (prova no Fracttal de verdade,
05/11/2026, OS 18591 de TESTE - PA).

O card (`api.get_os_detalhes`) mostra a `note` e a `task_note` de cada tarefa juntas (`notas`), e o `editar_nota_os` grava
só a `note`. A ponte da Engenharia (o comentário na nota, o editar e o apagar) partia da junção: no 1º comentário a `note`
virava a nota de entrada + a linha; no 2º, a junção já era `note` + `task_note`, e a nota de entrada entrava de novo. Na
prova, depois de um comentário e uma edição, a nota da OS tinha a nota de entrada três vezes. O Fracttal falso dos testes
antigos tinha um campo só, e nada disso aparecia. Aqui o falso tem os dois campos, e o card é o de verdade."""
import sys

import pytest

from nexus.torres.oscreator import ponte as P

if P.RAIZ_CLONE not in sys.path:
    sys.path.append(P.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
from os_web import os_acoes_web as regra  # noqa: E402
from test_oscreator_card_tarefas import WID, Fracttal, _tarefa  # noqa: E402

ENTRADA = ("[ENGENHARIA] Análise de recorrência de falhas\nAssumida em 05/11/2026 às 08:33 por Pessoa Teste.\n"
           "Falhas do ativo até agora: 3 falhas em 30 dias (2 em 7 dias).")
L1 = "[05/11/2026 09:25] Pessoa Teste (Engenharia): medir o isolamento"
L2 = "[05/11/2026 09:40] Pessoa Teste (Engenharia): trocar o cabo"


@pytest.fixture(params=["so_task_note", "os_dois"])
def os_(request, monkeypatch):
    """A OS de análise como o Fracttal a cria: a nota de entrada na `task_note` (e, no 2º caso, na `note` também)."""
    t = _tarefa(1)
    t.update(task_note=ENTRADA, note=ENTRADA if request.param == "os_dois" else "")
    f = Fracttal([t], [])
    monkeypatch.setattr(api, "_rpc_call", f.rpc)
    monkeypatch.setattr(api, "status_da_os", lambda wid: 1)

    def editar(wid, nota):                      # o editar_nota_os de verdade grava a `note` da tarefa, só ela
        t["note"] = nota
        return {"ok": True}
    monkeypatch.setattr(api, "editar_nota_os", editar)
    return t


def _comentar(linha):
    return P._acrescentar_na_nota(api, regra, {"wid": WID, "status": None, "nota": ""}, [linha])


def test_o_card_mostra_a_nota_de_entrada_uma_vez_so(os_):
    assert _comentar(L1) == "sim"
    d = api.get_os_detalhes(WID)
    assert d["notas"].count("[ENGENHARIA]") == 1 and d["notas"].endswith(L1)
    assert d["nota_gravada"] == os_["note"] and d["nota_da_tarefa"] == ENTRADA


def test_dois_comentarios_nao_repetem_a_nota_de_entrada(os_):
    assert _comentar(L1) == "sim" and _comentar(L2) == "sim"
    assert os_["note"] == ENTRADA + "\n" + L1 + "\n" + L2


def test_editar_e_apagar_mudam_so_a_linha(os_):
    _comentar(L1)
    _comentar(L2)
    assert P._mudar_linha_na_nota(api, regra, WID, [L1], L1 + " CC (editado)") == "sim"
    assert os_["note"] == ENTRADA + "\n" + L1 + " CC (editado)\n" + L2
    assert P._mudar_linha_na_nota(api, regra, WID, [L2], None) == "sim"
    assert os_["note"] == ENTRADA + "\n" + L1 + " CC (editado)"
    assert api.get_os_detalhes(WID)["notas"].count("[ENGENHARIA]") == 1


def test_a_pagina_da_os_mostra_a_note_e_a_task_note_sem_repetir():
    """Levi, 13/11/2026 (pelo chat de Chamados): "Na nota da OS" da página mostrava a nota velha nas OS em que o
    `work_orders_update` gravou a nota nova (a 19378 e mais cinco administrativas): a `note` trazia o cabeçalho e as
    respostas da Inspeção, e a `task_note` só o cabeçalho de 3 linhas. A regra agora é a do card do OS Creator
    (`os_detalhe.juntar_notas`): as duas, sem repetir a que já está dentro da outra."""
    from nexus.engenharia import os_equipe as E
    cab = "Chamado 812\nCliente X\nUsina Alfa"
    nova = cab + "\nInspeção: string 3 sem corrente"
    assert E._nota_da_os([{"task_note": cab, "note": nova}]) == nova
    assert E._nota_da_os([{"task_note": cab, "note": ""}]) == cab
    assert E._nota_da_os([{"task_note": None, "note": nova}]) == nova
    assert E._nota_da_os([{"task_note": "Entrada", "note": "Outra"}]) == "Outra\nEntrada"
    assert E._nota_da_os([{"task_note": cab, "note": nova}, {"task_note": cab, "note": nova}]) == nova
    assert E._nota_da_os([{"task_note": "None", "note": None}]) == ""
