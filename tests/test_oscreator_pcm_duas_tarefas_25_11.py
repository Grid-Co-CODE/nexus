"""PCM → OS por plano de tarefas: o ativo com duas tarefas vira duas linhas (25/11/2026, Levi, pelo chat do PCM: "Em MPA
tem algumas tarefas que são 2 tarefas para o mesmo ativo [...] quando tiver mais de uma tarefa no mesmo ativo, ele duplica
aquele ativo e aí só muda a nomenclatura da tarefa. E pode mudar a cor também, pode deixar um laranja de fundo, só para
mostrar, um laranja bem claro mesmo").

O caso real (lido no ar em 25/11, só leitura): no [Grid Co.] da família MPA o inversor tem o plano (Diurno) e o (Noturno),
e a tela só criava o que estava no combo. As contas do grupo rodam no node (`OsPcmTarefas.grupoDoAtivo`); o motor e o
Fracttal são falsos. Planos e ativos inventados."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.torres.oscreator import ponte

if ponte.RAIZ_CLONE not in sys.path:
    sys.path.append(ponte.RAIZ_CLONE)

import api  # noqa: E402 — o api.py do clone
import os_criar  # noqa: E402
import os_juntar  # noqa: E402
from os_web import pcm_web as pcm  # noqa: E402

WEB = Path(ponte.RAIZ_CLONE, "os_web")
JS = WEB / "static" / "pcm.js"
GRID, AXIS = pcm.chave_tipo("Grid Co."), pcm.chave_tipo("Axis")


def _p(i, desc, family="MPA"):
    return {"id_task": i, "description": desc, "family": family, "tipo": pcm.chave_tipo(pcm.tipo_do_plano(desc)),
            "turno": pcm.turno_do_plano(desc)}


DIURNO = _p(1, "[Grid Co.] - MPA - Inversor (Diurno)")
NOTURNO = _p(2, "[Grid Co.] - MPA - Inversor (Noturno)")
AXIS_D = _p(3, "[Axis] - MPA - Inversor - Diurna")
AXIS_TERMO = _p(4, "[Axis] - MPA - Inversor - apenas termografia")
OUTRA_FAM = _p(5, "[Grid Co.] - MPS - Inversor", family="MPS")


@pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")
@pytest.mark.parametrize("planos, combo, grupo", [
    # o par Diurno + Noturno do [Grid Co.]: duas linhas, a 1ª no Diurno (o de saída); o [Axis] fica só no combo
    ([AXIS_D, NOTURNO, DIURNO, AXIS_TERMO], [4, 3, 1, 2], [1, 2]),
    # com o turno Diurna escolhido, o filtro já tirou o Noturno: uma linha só, como antes
    ([AXIS_D, DIURNO], [3, 1], [1]),
    # sem [Grid Co.]: o de saída é o 1º por nome, e o grupo são os do tipo dele (a termografia e a Diurna do [Axis])
    ([AXIS_D, AXIS_TERMO], [4, 3], [4, 3]),
    # a família "(todas)": o plano de outra família não vira uma 2ª tarefa
    ([DIURNO, OUTRA_FAM], [1, 5], [1]),
    ([], [], []),
])
def test_o_grupo_e_o_plano_de_saida_e_os_do_mesmo_tipo_e_familia(planos, combo, grupo):
    script = ("require(process.argv[1]); const g = globalThis.OsPcmTarefas.grupoDoAtivo(JSON.parse(process.argv[2]));"
              "process.stdout.write(JSON.stringify({ps: g.ps.map((p) => p.id_task), grupo: g.grupo.map((p) => p.id_task)}));")
    r = subprocess.run(["node", "-e", script, str(JS), json.dumps(planos)], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == {"ps": combo, "grupo": grupo}


def test_a_tela_duplica_a_linha_e_manda_uma_selecao_por_linha():
    js = JS.read_text(encoding="utf-8")
    # a linha da outra tarefa: o mesmo ativo, data-slot, a classe da cor, e a data e o tempo por linha
    for trecho in ("data-slot", "(slot || slotsExtras(a.id).length ? ' dupla' : '')", "tr.classList.toggle('dupla', slots.length > 0)",
                   "const chave = (aid, slot)", "dtByAsset[k]", "durByAsset[k]",
                   "extraOff", "linhasQueViramTarefa", "uma por linha marcada",
                   "O mesmo plano está em duas linhas do mesmo ativo"):
        assert trecho in js, trecho
    # o criar percorre as LINHAS (não mais os ativos) e cada seleção leva o plano, a data e o tempo da própria linha
    criar = js.split("function criar()", 1)[1].split("function criarSemPlano", 1)[0]
    assert "linhasQueViramTarefa().forEach" in criar and "dataDaTr(tr)" in criar and "durByAsset[k]" in criar
    css = (WEB / "static" / "pcm.css").read_text(encoding="utf-8")
    assert ".pcm-tbl tr.dupla td{background:var(--pcm-dupla)}" in css
    assert "#pcm{--pcm-dupla:" in css and ':where(html[data-tema="claro"]) #pcm{--pcm-dupla:' in css


def test_o_servidor_aceita_o_mesmo_ativo_duas_vezes_com_planos_diferentes():
    ativo = {"id": 11, "code": "TST-INV11", "description": "Inversor 1.1"}
    corpo = {"sem_plano": False, "responsavel": {"id_personnel": 7, "name": "Pessoa Teste"},
             "selecoes": [{"asset_id": 11, "id_task": 1, "event_date": "2026-12-01T08:00", "duracao": None},
                          {"asset_id": 11, "id_task": 2, "event_date": "2026-12-01T19:00", "duracao": 3600}]}
    modo, args, _kw, erro = pcm.montar_criacao(corpo, [ativo])
    assert erro == "" and modo == "multi"
    sel = args[0]
    assert [(s["asset"]["id"], s["id_task"]) for s in sel] == [(11, 1), (11, 2)]
    assert sel[1]["duracao"] == 3600 and sel[0]["event_date"] != sel[1]["event_date"]


def test_o_motor_cria_as_duas_tarefas_do_mesmo_ativo_numa_os(monkeypatch):
    criadas, juntadas = [], []
    monkeypatch.setattr(api, "get_plan_details", lambda idt, aid: {"id_task": idt, "subtasks": [{"description": "s"}]})

    def criar(asset, plan, **k):
        criadas.append((asset["id"], plan["id_task"], k.get("event_date")))
        return {"id_task": 900 + len(criadas), "duracao": 1800}
    monkeypatch.setattr(api, "create_planned_os", criar)
    monkeypatch.setattr(os_juntar, "juntar_em_os", lambda ids, dur, *a, **k: juntadas.append(list(ids)) or {"ok": True})
    monkeypatch.setattr(os_juntar, "da_os", lambda jun: {"id_work_order": 1, "wo_folio": 10})
    ativo = {"id": 11, "code": "TST-INV11"}
    r = os_criar.create_planned_os_multi([{"asset": ativo, "id_task": 1, "event_date": "d1"},
                                          {"asset": ativo, "id_task": 2, "event_date": "d2"}], 7, "Pessoa Teste")
    assert r["ok"] and r["n_criadas"] == 2
    assert criadas == [(11, 1, "d1"), (11, 2, "d2")] and juntadas == [[901, 902]]
