"""O filtro Status do chamado no quadro de Garantias (Levi, 04/11/2026: "inclua uma filtros de status do chamado"): o
`static/acomp.js` esconde o cartão de outro status, e o "Sem status" deixa só o que não tem. Roda o script de verdade
no node, com um DOM de mentira (o mesmo de `test_oscreator_acomp_filtro_guardado_24_10.py`)."""
import json
import shutil
import subprocess

import pytest

from nexus.torres.oscreator import ponte

JS = ponte.RAIZ_CLONE + "/os_web/static/acomp.js"

RODAR = r"""
const fs = require("fs");
const escolha = process.argv[1];
const armazem = {};
global.sessionStorage = {getItem: (k) => (k in armazem ? armazem[k] : null), setItem: (k, v) => { armazem[k] = String(v); }};
function classes() {
  const s = new Set();
  return {add: (c) => s.add(c), remove: (c) => s.delete(c), contains: (c) => s.has(c),
          toggle: (c, f) => { if (f === undefined ? !s.has(c) : f) s.add(c); else s.delete(c); }};
}
function el(extra) {
  return Object.assign({dataset: {}, classList: classes(), style: {setProperty() {}}, scrollTop: 0, value: "",
    _ev: {}, addEventListener(t, f) { this._ev[t] = f; }, querySelector: () => null, querySelectorAll: () => [],
    getBoundingClientRect: () => ({top: 0, bottom: 0}), getAttribute: () => "/os/chamados/acompanhamento/1"}, extra);
}
const cards = [["Standby", "Standby"], ["Aguardando retorno do Cliente", "Cliente"], ["", ""], ["Standby", "Standby"]]
  .map(([st, g], i) => el({dataset: {st: st, geral: g, busca: "os " + i}}));
const n = el(), vazio = el();
const caixa = el({querySelectorAll: (s) => (s === ".card" ? cards : [])});
const col = el({querySelectorAll: (s) => (s === ".card" ? cards : []), querySelector: (s) => (s === "[data-n]" ? n : s === "[data-vazio]" ? vazio : null)});
const st = el({tagName: "SELECT", dataset: {f: "st"}, options: [{value: ""}, {value: "Standby"}, {value: "_sem"}]});
const quadro = el({querySelectorAll: (s) => ({"[data-f]": [st], ".col": [col], ".cards": [caixa], "a.card[href]": cards}[s] || [])});
global.document = {querySelector: () => null, querySelectorAll: () => [], getElementById: (id) => (id === "acomp" ? quadro : null),
                   addEventListener: () => {}, fonts: null};
global.window = global;
global.addEventListener = () => {};
global.scrollY = 0;
global.scrollTo = () => {};
global.requestAnimationFrame = (f) => { f(); return 1; };
global.getComputedStyle = () => ({paddingBottom: "0"});
global.location = {pathname: "/", search: "", reload() {}};
global.OsCarga = {buscar: async () => ({})};
eval(fs.readFileSync(process.argv[2], "utf8"));
st.value = escolha; st._ev.change();
console.log(JSON.stringify({visiveis: cards.map((c, i) => c.classList.contains("oculto") ? null : i).filter((i) => i !== null),
                            n: n.textContent, guardado: armazem["acomp.filtros"]}));
"""


def _rodar(escolha) -> dict:
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    r = subprocess.run(["node", "-e", RODAR, escolha, JS], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_o_status_escolhido_deixa_so_os_dele():
    r = _rodar("Standby")
    assert (r["visiveis"], r["n"]) == ([0, 3], "2")
    assert json.loads(r["guardado"]) == {"st": "Standby"}                 # fica na volta, como os outros filtros


def test_sem_status_deixa_so_o_que_nao_tem():
    assert _rodar("_sem")["visiveis"] == [2]


def test_todos_deixa_tudo():
    assert _rodar("")["visiveis"] == [0, 1, 2, 3]
