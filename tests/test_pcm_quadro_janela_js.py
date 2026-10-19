"""A janela da OS do Quadro da semana (pcm-quadro.js), aberta no node com uma página de mentira.

Levi, 18/10/2026: o título do motivo é a pergunta "Técnico não consegue fazer?", sem o "Sem motivo."; o botão é
"Salvar motivo"; no Quando, o dia da semana leva a data entre parênteses ("Terça (13/10)"); Onde e Quem lado a lado e o
Quando embaixo; nos cartões do topo, a criticidade da OS, na ordem Tipo, Situação, Criticidade, Semanas na fila e
Reprogramada, e sai a seção "Situação da OS" de baixo."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "pcm-quadro.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")

PAGINA = r"""
function el() {
  const ls = {};
  return {innerHTML: "", hidden: false, open: false, attrs: {},
    getAttribute(k) { return this.attrs[k]; }, setAttribute(k, v) { this.attrs[k] = v; },
    addEventListener(t, f) { (ls[t] = ls[t] || []).push(f); }, disparar(t, ev) { (ls[t] || []).forEach(f => f(ev || {})); },
    querySelector() { return null; }, querySelectorAll() { return []; }, focus() {}, showModal() { this.open = true; },
    classList: {toggle() {}}};
}
const D = JSON.parse(process.argv[2]);
const corpo = el(), fechar = el(), dlg = el(), cartao = el();
dlg.querySelector = sel => sel === "[data-det-corpo]" ? corpo : (sel === "[data-det-fechar]" ? fechar : null);
cartao.attrs["data-cartao"] = "0";
globalThis.localStorage = {getItem() { return null; }, setItem() {}};
globalThis.document = {
  getElementById(id) { return id === "q-dados" ? {textContent: JSON.stringify(D)} : (id === "q-det" ? dlg : null); },
  querySelectorAll(sel) { return sel === "[data-cartao]" ? [cartao] : []; },
  contains() { return false; },
};
require(process.argv[1]);
cartao.disparar("click");
process.stdout.write(JSON.stringify(corpo.innerHTML));
"""

ITEM = {"os": "16186", "t": "[Thopen - Sarandi 1 - PR] - Religamento", "tp": "Religamento", "tc": "religa",
        "st": "Finalizada", "rol": 1, "rep": False, "cri": "Alta", "uc": "Thopen - Sarandi 1 - PR", "cli": "Thopen",
        "cl": "PR Norte 01", "cod": "SAR1", "dcri": "13/10/2026", "d": "Terça", "data": "13/10", "dprog": "13/10/2026",
        "ini": "06:00", "fim": "11:20", "h": "5,3 h", "dfim": "13/10/2026", "resp": "Responsável Um", "ros": "Gestora Um",
        "sp": "Em processo", "par": "não", "termo": "sim", "nova": "Programada", "etq": "Religamento"}


def janela(item, **d):
    dados = {"semana": "2026-W42", "itens": [item], "oss": {}, "motivos": [[1, "Aguardando cliente", True]],
             "pode_marcar": True}
    dados.update(d)
    r = subprocess.run(["node", "-e", PAGINA, str(JS), json.dumps(dados)], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_o_motivo_e_a_pergunta_sem_o_sem_motivo_e_o_botao_salvar():
    h = janela(ITEM)
    assert "<h3>Técnico não consegue fazer?</h3>" in h and "<h3>Motivo</h3>" not in h
    assert "Sem motivo." not in h and "Marcar o motivo" not in h and "Salvar motivo" in h


def test_no_quando_o_dia_da_semana_leva_a_data_entre_parenteses():
    h = janela(ITEM)
    assert "<dd>Terça (13/10)</dd>" in h and "Terça 13/10" not in h


def test_onde_e_quem_lado_a_lado_e_o_quando_embaixo():
    h = janela(ITEM)
    lado = h.split('<div class="q-lado">', 1)
    assert len(lado) == 2
    par = lado[1].split("<h3>Quando</h3>", 1)[0]
    assert par.index("<h3>Onde</h3>") < par.index("<h3>Quem</h3>")
    assert h.index("<h3>Quando</h3>") > h.index("<h3>Quem</h3>")


def test_os_cartoes_do_topo_com_a_criticidade_e_sem_a_situacao_da_os_embaixo():
    h = janela(ITEM)
    fatos = h.split('<div class="q-fatos">', 1)[1].split("</div></div>", 1)[0] + "</div>"
    rotulos = re.findall(r"<div><span>([^<]+)</span>", fatos)
    assert rotulos == ["Tipo", "Situação", "Criticidade", "Semanas na fila", "Reprogramada"]
    assert ">Alta</b>" in fatos
    assert "Situação da OS" not in h and "Status da OS" not in h
    sem = janela(dict(ITEM, cri=""))
    assert ">—</b>" in sem.split('<div class="q-fatos">', 1)[1].split("<h3>", 1)[0]


def test_a_lista_de_motivos_como_no_fora_da_programacao():
    """Levi, 18/10/2026 (2ª rodada): os motivos da janela "tem que estar de acordo com os motivos de fora da
    programação": só o nome, sem o "(tira da programação)" do lado; a cor do campo diz se o escolhido tira (vermelho)
    ou não (laranja), e uma linha embaixo diz quando tira."""
    h = janela(ITEM, motivos=[[1, "Engenharia", False], [4, "Aguardando cliente", True]])
    sel = h.split("data-mp-sel", 1)[1].split("</select>", 1)[0]
    assert "(tira da programação)" not in sel
    assert '<option value="1" data-tira="0">Engenharia</option>' in sel
    assert '<option value="4" data-tira="1">Aguardando cliente</option>' in sel
    assert "data-mp-tira" in h and "Tira a tarefa da programação" in h
    css = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "pcm.css").read_text(encoding="utf-8")
    assert ".q-mp-sel--tira{color:var(--critico)}" in css and ".q-mp-sel--nao{color:var(--laranja)}" in css


def test_os_rotulos_dos_cartoes_cabem():
    """Levi, 18/10/2026: "reprogramada está ultrapassando linha do card". As cinco colunas seguem o conteúdo (auto), com
    menos respiro, para o rótulo mais longo de uma palavra (REPROGRAMADA) caber na janela de 580 px."""
    css = (Path(__file__).resolve().parents[1] / "nexus" / "static" / "pcm.css").read_text(encoding="utf-8")
    regra = css.split("\n.q-fatos{", 1)[1].split("}", 1)[0]
    assert "grid-template-columns:repeat(5,auto)" in regra



# ── a subtarefa no "O que" (19/10/2026) ──────────────────────────────────────────────────────────────────────
# O programador do PCM tirou da semana UM inversor da OS 16739 e a confirmação disse que saíam os 15. O "O que" oferece
# a subtarefa (a tarefa naquele ativo), a tarefa em todos os ativos e a OS inteira; o padrão é a do cartão.
INV = "[GreenYellow] - MPT - Inversor"
IRMAS = [{"t": INV, "tp": "Preventiva", "pend": False, "n": 3,
          "cods": [["MCB100-INVR1", 1], ["MCB100-INVR2", 1], ["MCB100-INVR3", 1]]},
         {"t": "[GreenYellow] - MPT - QGBT", "tp": "Preventiva", "pend": False, "n": 2, "cods": [["MCB100-QGBT1", 2]]}]


def _node(expr, *args):
    script = "require(process.argv[1]); const L = globalThis.QuadroLinha; const A = JSON.parse(process.argv[2]);"              "process.stdout.write(JSON.stringify(" + expr + "));"
    r = subprocess.run(["node", "-e", script, str(JS), json.dumps(args)], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_o_que_oferece_a_subtarefa_do_cartao():
    ops = _node("L.opcoesAlvo(A[0], A[1])", IRMAS, {"t": INV, "cod": "MCB100-INVR2"})
    assert [o["v"] for o in ops] == [["", ""], [INV, ""], [INV, "MCB100-INVR1"], [INV, "MCB100-INVR2"],
                                     [INV, "MCB100-INVR3"], ["[GreenYellow] - MPT - QGBT", "MCB100-QGBT1"]]
    assert [o["v"] for o in ops if o.get("sel")] == [[INV, "MCB100-INVR2"]]
    assert ops[0]["rotulo"] == "a OS inteira (4 tarefas)" and ops[1]["rotulo"].startswith("Em todos os 3 ativos · ")
    assert ops[3]["rotulo"].startswith("MCB100-INVR2 · ")          # o ativo na frente: no celular o fim some
    # na janela, o valor de cada opção é [tarefa, código]
    item = dict(ITEM, os="16739", t=INV, cod="MCB100-INVR2", tp="Preventiva")
    h = janela(item, oss={"16739": IRMAS}, destino="atual", dias=[["seg", "Segunda"]], turnos=["manhã"])
    sel = re.search(r'<option value="([^"]*)" selected>', h)
    assert sel and json.loads(sel.group(1).replace("&quot;", '"')) == [INV, "MCB100-INVR2"]


def test_tirar_a_subtarefa_diz_que_sai_so_ela():
    txt = _node("L.textoTirar(A[0], '16739', A[1], A[2])", IRMAS, INV, "MCB100-INVR2")
    assert "no ativo MCB100-INVR2" in txt and "As outras 3 tarefas da OS continuam na semana." in txt
    assert "saem todas" not in txt and "15" not in txt
    txt = _node("L.textoTirar(A[0], '16739', A[1], A[2])", IRMAS, "[GreenYellow] - MPT - QGBT", "MCB100-QGBT1")
    assert "2 blocos da semana: saem todos" in txt
    # a tarefa em todos os ativos: sai pelo nome, nos 3
    txt = _node("L.textoTirar(A[0], '16739', A[1], A[2])", IRMAS, INV, "")
    assert "em todos os 3 ativos" in txt and "A outra tarefa da OS continua na semana." in txt
