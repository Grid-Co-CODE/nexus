"""A vista em tabela das Garantias no navegador (27/10/2026): os filtros do quadro valem nas linhas da tabela, a troca
quadro/tabela fica guardada neste navegador, e o clique na linha abre o chamado. Roda o `static/acomp.js` de verdade no
node, com um DOM de mentira."""
import json
import shutil
import subprocess

import pytest

from nexus.torres.oscreator import ponte

JS = ponte.RAIZ_CLONE + "/os_web/static/acomp.js"

RODAR = r"""
const fs = require("fs");
const [guardado, acao] = [JSON.parse(process.argv[1]), process.argv[2]];
const local = Object.assign({}, guardado);
global.localStorage = {getItem: (k) => (k in local ? local[k] : null), setItem: (k, v) => { local[k] = String(v); }};
global.sessionStorage = {getItem: () => null, setItem: () => {}};
function classes() {
  const s = new Set();
  return {add: (c) => s.add(c), remove: (c) => s.delete(c), contains: (c) => s.has(c),
          toggle: (c, f) => { if (f === undefined ? !s.has(c) : f) s.add(c); else s.delete(c); }};
}
function el(extra) {
  return Object.assign({dataset: {}, classList: classes(), style: {setProperty() {}}, scrollTop: 0, value: "", _ev: {},
    addEventListener(t, f) { this._ev[t] = f; }, querySelector: () => null, querySelectorAll: () => [],
    getBoundingClientRect: () => ({top: 0, bottom: 0}), getAttribute: () => "/os/chamados/acompanhamento/1",
    setAttribute(k, v) { this["_" + k] = v; }}, extra);
}
const linhas = [["Huawei", "9103", "Cliente", "Supervisor Um"], ["Sungrow", "9104", "Fabricante", ""],
                ["Huawei", "9105", "", "Supervisor Um"]].map(([m, f, g, u]) =>
  el({dataset: {marca: m, busca: "os " + f, href: "/os/chamados/acompanhamento/" + f, geral: g, ufv: u}, tagName: "TR"}));
const vazioTabela = el();
const marca = el({tagName: "SELECT", dataset: {f: "marca"}, options: [{value: ""}, {value: "Huawei"}, {value: "Sungrow"}]});
const geral = el({tagName: "SELECT", dataset: {f: "geral"}, options: [{value: ""}, {value: "Cliente"}, {value: "_sem"}]});
const ufv = el({tagName: "SELECT", dataset: {f: "ufv"}, options: [{value: ""}, {value: "Supervisor Um"}, {value: "_sem"}]});
const bQuadro = el({dataset: {vista: "quadro"}}), bTabela = el({dataset: {vista: "tabela"}});
let navegou = null;
const quadro = el({
  dataset: {vista: "quadro"},
  querySelectorAll: (s) => ({"[data-f]": [marca, geral, ufv], "tr[data-linha]": linhas, ".vistas [data-vista]": [bQuadro, bTabela]}[s] || []),
  querySelector: (s) => (s === "[data-vazio-tabela]" ? vazioTabela : null),
});
global.document = {querySelector: () => null, querySelectorAll: () => [], getElementById: (id) => (id === "acomp" ? quadro : null),
                   addEventListener: () => {}, fonts: null};
global.window = global;
global.addEventListener = () => {};
global.scrollTo = () => {};
global.requestAnimationFrame = (f) => { f(); return 1; };
global.getComputedStyle = () => ({paddingBottom: "0"});
global.location = {pathname: "/", search: "", reload() {}, set href(v) { navegou = v; }, get href() { return ""; }};
global.OsCarga = {buscar: async () => ({})};
eval(fs.readFileSync(process.argv[3], "utf8"));
if (acao === "filtrar") { marca.value = "Sungrow"; marca._ev.change(); }
if (acao === "nada") { marca.value = "Ninguem"; marca._ev.change(); }
if (acao === "geral") { geral.value = "Cliente"; geral._ev.change(); }
if (acao === "sem_geral") { geral.value = "_sem"; geral._ev.change(); }
if (acao === "ufv") { ufv.value = "Supervisor Um"; ufv._ev.change(); }
if (acao === "sem_ufv") { ufv.value = "_sem"; ufv._ev.change(); }
if (acao === "tabela") { bTabela._ev.click(); }
if (acao === "clique") { linhas[1]._ev.click({target: {closest: () => null}}); }
console.log(JSON.stringify({vista: quadro.dataset.vista, guardada: local["acomp.vista"] || null, navegou,
  visiveis: linhas.filter((l) => !l.classList.contains("oculto")).map((l) => l.dataset.busca),
  vazio: !vazioTabela.classList.contains("oculto")}));
"""


def _rodar(guardado=None, acao="") -> dict:
    if not shutil.which("node"):
        pytest.skip("sem node nesta máquina")
    r = subprocess.run(["node", "-e", RODAR, json.dumps(guardado or {}), acao, JS],
                       capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_o_filtro_vale_nas_linhas_da_tabela():
    r = _rodar(acao="filtrar")
    assert r["visiveis"] == ["os 9104"] and r["vazio"] is False


def test_filtro_sem_nenhuma_linha_diz_que_nao_ha():
    r = _rodar(acao="nada")
    assert r["visiveis"] == [] and r["vazio"] is True


def test_a_troca_para_tabela_fica_guardada():
    r = _rodar(acao="tabela")
    assert (r["vista"], r["guardada"]) == ("tabela", "tabela")


def test_o_clique_na_linha_abre_o_chamado():
    assert _rodar(acao="clique")["navegou"] == "/os/chamados/acompanhamento/9104"


@pytest.mark.parametrize("acao,ficam", [("geral", ["os 9103"]), ("sem_geral", ["os 9105"]),
                                        ("ufv", ["os 9103", "os 9105"]), ("sem_ufv", ["os 9104"])])
def test_os_filtros_status_geral_e_responsavel_ufv(acao, ficam):
    """28/10/2026: o Status geral e o Responsável UFV no lugar do Responsável; "_sem" acha o que não tem."""
    assert _rodar(acao=acao)["visiveis"] == ficam
