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
