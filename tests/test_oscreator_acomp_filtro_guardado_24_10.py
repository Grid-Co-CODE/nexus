"""O filtro do Acompanhamento de chamados fica ao abrir um chamado e voltar (Levi, 24/10/2026: "Quando eu faço um filtro
em garantias > acompanhamento de chamados e clico na os, ao voltar para o acompanhamento o filtro se desfaz e carrega
novamente, quero que mantenha o filtro anterior!"). O `static/acomp.js` guarda o filtro e a rolagem nesta aba do
navegador (sessionStorage) e os põe de volta quando o quadro abre de novo (a volta, o Atualizar, a tela que troca
sozinha). Roda o script de verdade no node, com um DOM de mentira."""
import json
import shutil
import subprocess

import pytest

from nexus.torres.oscreator import ponte

JS = ponte.RAIZ_CLONE + "/os_web/static/acomp.js"

RODAR = r"""
const fs = require("fs");
const [guardado, acao] = [JSON.parse(process.argv[1]), process.argv[2]];
const armazem = Object.assign({}, guardado);
global.sessionStorage = {getItem: (k) => (k in armazem ? armazem[k] : null), setItem: (k, v) => { armazem[k] = String(v); }};
const ouvintes = {};
function classes() {
  const s = new Set();
  return {add: (c) => s.add(c), remove: (c) => s.delete(c), contains: (c) => s.has(c),
          toggle: (c, f) => { if (f === undefined ? !s.has(c) : f) s.add(c); else s.delete(c); }};
}
function el(extra) {
  const e = Object.assign({dataset: {}, classList: classes(), style: {setProperty() {}}, scrollTop: 0, value: "",
    _ev: {}, addEventListener(t, f) { this._ev[t] = f; }, querySelector: () => null, querySelectorAll: () => [],
    getBoundingClientRect: () => ({top: 0, bottom: 0}), getAttribute: () => "/os/chamados/acompanhamento/1"}, extra);
  return e;
}
const cards = [["Huawei", "1"], ["Sungrow", "2"], ["Huawei", "3"]].map(([m, n]) => el({dataset: {marca: m, busca: "os " + n}}));
const n = el(), vazio = el();
const caixa = el({querySelectorAll: (s) => (s === ".card" ? cards : [])});
const col = el({querySelectorAll: (s) => (s === ".card" ? cards : []), querySelector: (s) => (s === "[data-n]" ? n : s === "[data-vazio]" ? vazio : null)});
const marca = el({tagName: "SELECT", dataset: {f: "marca"}, options: [{value: ""}, {value: "Huawei"}, {value: "Sungrow"}]});
const busca = el({tagName: "INPUT", dataset: {f: "busca"}});
const limpar = el();
const quadro = el({
  querySelectorAll: (s) => ({"[data-f]": [marca, busca], ".col": [col], ".cards": [caixa], "a.card[href]": cards}[s] || []),
  querySelector: (s) => (s === "[data-limpar]" ? limpar : null),
});
let rolou = null;
global.document = {querySelector: () => null, querySelectorAll: () => [], getElementById: (id) => (id === "acomp" ? quadro : null),
                   addEventListener: () => {}, fonts: null};
global.window = global;
global.addEventListener = (t, f) => { ouvintes[t] = f; };
global.scrollY = 0;
global.scrollTo = (x, y) => { rolou = y; };
global.requestAnimationFrame = (f) => { f(); return 1; };
global.getComputedStyle = () => ({paddingBottom: "0"});
global.location = {pathname: "/", search: "", reload() {}};
global.OsCarga = {buscar: async () => ({})};
eval(fs.readFileSync(process.argv[3], "utf8"));
if (acao === "filtrar") { marca.value = "Huawei"; marca._ev.change(); busca.value = "OS 3"; busca._ev.input(); }
if (acao === "limpar") { limpar._ev.click(); }
if (acao === "sair") { caixa.scrollTop = 240; global.scrollY = 380; ouvintes.pagehide(); }
console.log(JSON.stringify({marca: marca.value, busca: busca.value, n: n.textContent,
  visiveis: cards.filter((c) => !c.classList.contains("oculto")).length, coluna: caixa.scrollTop, pagina: rolou,
  armazem}));
"""


def _rodar(guardado=None, acao="") -> dict:
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    r = subprocess.run(["node", "-e", RODAR, json.dumps(guardado or {}), acao, JS],
                       capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def _filtro(r) -> dict:
    return json.loads(r["armazem"]["acomp.filtros"])


def test_o_filtro_escolhido_fica_guardado():
    r = _rodar(acao="filtrar")
    assert _filtro(r) == {"marca": "Huawei", "busca": "OS 3"}
    assert r["visiveis"] == 1


def test_a_volta_ao_quadro_poe_o_filtro_de_volta():
    r = _rodar({"acomp.filtros": json.dumps({"marca": "Huawei", "busca": ""})})
    assert (r["marca"], r["visiveis"], r["n"]) == ("Huawei", 2, "2")


def test_o_que_saiu_da_lista_nao_vira_filtro():
    """A marca do filtro guardado não está mais no quadro (o último chamado dela fechou): o quadro abre inteiro."""
    r = _rodar({"acomp.filtros": json.dumps({"marca": "Marca Que Saiu"})})
    assert (r["marca"], r["visiveis"]) == ("", 3)


def test_a_rolagem_da_coluna_e_da_pagina_tambem_voltam():
    r = _rodar(acao="sair")
    assert json.loads(r["armazem"]["acomp.rolagem"]) == {"pagina": 380, "colunas": [240]}
    r = _rodar({"acomp.rolagem": json.dumps({"pagina": 380, "colunas": [240]})})
    assert (r["coluna"], r["pagina"]) == (240, 380)


def test_sem_nada_guardado_o_quadro_abre_como_sempre():
    r = _rodar()
    assert (r["marca"], r["visiveis"], r["pagina"]) == ("", 3, None) and "acomp.filtros" not in r["armazem"]
