"""O acessos-admins-app.js (Base → Acessos, aba Administradores do App de Campo), rodado no node com uma página de mentira.

Revisão de 05/11/2026 (achado 7): com o `required` nos rádios, o envio sem pessoa escolhida, com a 1ª ficha escondida
pela busca, era barrado calado pelo navegador (o aviso dele não aparece num campo que não se vê). Com o JavaScript, o
`required` sai dos rádios e o envio confere a escolha: sem pessoa, não envia, o aviso vai à linha `aria-live` da contagem
e o foco volta à busca. Com a pessoa escolhida, envia; e o Tirar pergunta antes."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

JS = Path(__file__).resolve().parents[1] / "nexus" / "static" / "acessos-admins-app.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="sem node nesta máquina")

PAGINA = r"""
const ouvintes = {};
function el(attrs) {
  const ls = {};
  return {attrs: Object.assign({}, attrs), hidden: false, textContent: "", value: "", checked: false, focado: false,
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    removeAttribute(k) { delete this.attrs[k]; },
    addEventListener(t, f) { (ls[t] = ls[t] || []).push(f); },
    disparar(t, ev) { (ls[t] || []).forEach(f => f(ev)); },
    focus() { this.focado = true; }};
}
const CENA = JSON.parse(process.argv[2]);
const radios = CENA.nomes.map(() => el({required: ""}));
const pessoas = CENA.nomes.map((n, i) => Object.assign(el({"data-aa-texto": n}), {querySelector() { return radios[i]; }}));
const busca = el({}), conta = el({}), nada = el({}), form = el({id: "aa-por"}), tirar = el({"data-confirmar": "Tirar?"});
nada.hidden = true;
globalThis.window = globalThis;
const perguntas = [];
window.confirm = m => { perguntas.push(m); return CENA.confirma; };
globalThis.document = {
  getElementById(id) { return id === "aa-por" ? form : null; },
  querySelector(sel) {
    return {"[data-aa-busca]": busca, "[data-aa-nada]": nada, "[data-aa-conta]": conta}[sel] || null;
  },
  querySelectorAll(sel) { return sel === "[data-aa-texto]" ? pessoas : []; },
  addEventListener(t, f) { (ouvintes[t] = ouvintes[t] || []).push(f); },
};
require(process.argv[1]);
const required = radios.map(r => "required" in r.attrs);
busca.value = CENA.busca;
busca.disparar("input", {});
if (CENA.marca !== null) radios[CENA.marca].checked = true;
let cancelou = false;
(ouvintes.submit || []).forEach(f => f({target: CENA.alvo === "tirar" ? tirar : form,
                                        preventDefault() { cancelou = true; }}));
process.stdout.write(JSON.stringify({cancelou, required, conta: conta.textContent, foco: busca.focado, perguntas,
  escondidas: pessoas.map(p => p.hidden)}));
"""


def enviar(**cena):
    cena = dict({"nomes": ["tecnico dez", "supervisora onze"], "busca": "", "marca": None, "alvo": "por",
                 "confirma": True}, **cena)
    r = subprocess.run(["node", "-e", PAGINA, str(JS), json.dumps(cena)], capture_output=True, text=True,
                       encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_o_required_sai_dos_radios_e_o_envio_sem_pessoa_avisa_na_linha_aria_live():
    r = enviar(busca="onze")                                   # a 1ª ficha escondida pela busca, ninguém escolhido
    assert r["required"] == [False, False]
    assert r["escondidas"] == [True, False]
    assert r["cancelou"] is True and r["foco"] is True
    assert r["conta"].startswith("Escolha a pessoa na lista antes de pôr")


def test_com_a_pessoa_escolhida_envia():
    r = enviar(busca="onze", marca=1)
    assert r["cancelou"] is False and r["conta"] == "1 ficha"


def test_a_busca_sem_acento_e_o_tirar_pergunta_antes():
    assert enviar(busca="Técnico", marca=0)["escondidas"] == [False, True]
    r = enviar(alvo="tirar", confirma=False)
    assert r["cancelou"] is True and r["perguntas"] == ["Tirar?"]
    assert enviar(alvo="tirar", confirma=True)["cancelou"] is False
