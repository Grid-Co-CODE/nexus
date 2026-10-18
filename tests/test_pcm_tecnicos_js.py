"""As abas do pcm-tecnicos.js (Técnicos por usina), rodadas no node com uma página de mentira.

Levi, 18/10/2026: "Quando clico em comparação com o app e clico no botão de 'Por Usina' e 'Por Técnico' não carrega de
volta para essas abas". A Comparação com o App é outra página (o template não desenha as seções Por usina e Por técnico
nela), e o script cancelava o clique da aba para trocar na própria página, onde não havia o que mostrar: o endereço
mudava e a tela ficava na Comparação. A aba só troca na página quando a seção dela está ali; senão o link navega."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "pcm-tecnicos.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")

PAGINA = r"""
const ouvintes = {};
function el(attrs) {
  const ls = {};
  return {attrs: Object.assign({}, attrs), dataset: {}, hidden: false,
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    removeAttribute(k) { delete this.attrs[k]; },
    addEventListener(t, f) { (ls[t] = ls[t] || []).push(f); },
    disparar(t, ev) { (ls[t] || []).forEach(f => f(ev)); },
    querySelector() { return el({}); }, querySelectorAll() { return []; }, closest() { return null; }};
}
const VER = process.argv[2], SECOES = JSON.parse(process.argv[3]), ALVO = process.argv[4];
const abas = ["usina", "tecnico"].map(a => el({"data-aba": a}));
const secoes = SECOES.map(s => Object.assign(el({"data-aba-secao": s}), {hidden: s !== (VER || "usina")}));
const dlg = el({});
dlg.dataset.rota = "/t/pcm/tecnicos-por-usina";
globalThis.window = globalThis;
window.nexusRota = x => x;
globalThis.location = {href: "http://nexus.test/t/pcm/tecnicos-por-usina" + (VER ? "?ver=" + VER : "")};
const enderecos = [];
globalThis.history = {state: null, replaceState(s, t, u) { enderecos.push(u); }};
globalThis.document = {
  getElementById(id) { return id === "tu-dados" ? {textContent: '{"pessoas": []}'} : dlg; },
  querySelectorAll(sel) {
    if (sel === ".cn-abas a[data-aba]") return abas;
    if (sel === "[data-aba-secao]") return secoes;
    return [];
  },
  querySelector() { return null; },
  addEventListener(t, f) { (ouvintes[t] = ouvintes[t] || []).push(f); },
};
require(process.argv[1]);
let cancelou = false;
abas.find(a => a.getAttribute("data-aba") === ALVO).disparar("click", {preventDefault() { cancelou = true; }});
process.stdout.write(JSON.stringify({cancelou, enderecos,
  visivel: secoes.filter(s => !s.hidden).map(s => s.getAttribute("data-aba-secao"))}));
"""


def clicar(ver, secoes, alvo):
    r = subprocess.run(["node", "-e", PAGINA, str(JS), ver, json.dumps(secoes), alvo], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_na_comparacao_a_aba_navega_de_volta():
    """Na página da Comparação não há as seções: o clique segue o link (a página Por usina ou Por técnico abre)."""
    for alvo in ("usina", "tecnico"):
        r = clicar("app", [], alvo)
        assert r["cancelou"] is False and r["enderecos"] == [], (alvo, r)


def test_com_as_secoes_a_aba_troca_na_pagina():
    """Por usina e Por técnico seguem trocando na própria página, sem recarregar, e o endereço acompanha."""
    r = clicar("", ["usina", "tecnico"], "tecnico")
    assert r["cancelou"] is True and r["visivel"] == ["tecnico"]
    assert r["enderecos"] == ["/t/pcm/tecnicos-por-usina?ver=tecnico"]
    r = clicar("tecnico", ["usina", "tecnico"], "usina")
    assert r["cancelou"] is True and r["visivel"] == ["usina"] and r["enderecos"] == ["/t/pcm/tecnicos-por-usina"]
