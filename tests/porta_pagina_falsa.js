/* Roda no node a parte da PÁGINA do porta.js (e o script do sair.html), com um DOM de mentira, e diz o que ela fez:
   quantas vezes enviou o formulário do passe (e com que passe), que pedidos fez (fetch) e se avisou. Revisão de
   10/10/2026 da porta única: o porta.js enviava o passe mesmo com a plataforma configurada em OUTRA origem (só avisava),
   e o base_da_plataforma aceita http em loopback: com a NEXUS_PLATAFORMA_URL interna do servidor, cada visitante mandava
   um passe válido, com o e-mail dele, para a porta local da própria máquina. O que se confere aqui é que nada sai para
   outra origem. Auditoria A5 (10/10/2026): também a renovação da sessão da plataforma, pelos `passos` (mensagens da
   moldura e o relógio andando). Modo TV do Painel NOC (11/10/2026): o endereço que a TV mantém, o botão "Modo TV" e o
   "Sair do modo TV" que acompanham a moldura, e os controles que aparecem ao mexer o mouse (`elementos`, `evento`,
   `carregar`).

   Uso: node porta_pagina_falsa.js <arquivo.js> '<config JSON>'
   config: {pagina: "https://app.exemplo.test/nexus/t/...", modo: "porta" | "sair", dados, moldura, seletor, acao, id,
            script, elementos: {"<id>": {hidden, href}} (outros elementos da página, devolvidos no fim),
            respostas: {"<url completa>": {status, tipo ("basic" | "opaqueredirect"), json}} (o resto: 401),
            passos: [{mensagem: {...}, origem: "<origem>" (padrão: a da página), de: "moldura" | "outra"}
                     | {avancar: <ms no relógio>} | {intervalo: true} (roda os setInterval) | {visivel: true}
                     | {evento: "mousemove" | "keydown" ..., em: "documento" | "moldura" (o documento da página dentro
                        dela), tecla} | {carregar: true} (a moldura terminou de carregar uma página)]} */
"use strict";
const fs = require("fs");
const vm = require("vm");

const [arquivo, textoCfg] = process.argv.slice(2);
const cfg = JSON.parse(textoCfg);
const feito = {envios: 0, passes: [], pedidos: [], corpos: [], alerta: null, foiPara: null, entrarDeNovo: null,
               enderecos: []};

const ouvintes = {janela: {}, documento: {}, moldura: {}};
function ouvir(onde) {
  return function (tipo, f) { (ouvintes[onde][tipo] = ouvintes[onde][tipo] || []).push(f); };
}

function elemento(id, extra) {
  const seus = {};                           // os ouvintes do elemento (o "load" da moldura, o "click" de um botão)
  return Object.assign({id: id, hidden: true, textContent: "", innerHTML: "", options: [], disabled: false, _ouvintes: seus,
                        addEventListener: function (t, f) { (seus[t] = seus[t] || []).push(f); },
                        setAttribute: function () {}, removeAttribute: function () {},
                        appendChild: function () {}, getAttribute: function () { return null; },
                        contains: function () { return false; },
                        querySelector: function () { return null; }}, extra || {});
}

const els = {};
const campoPasse = {name: "passe", value: "passe-da-pagina"};
if (cfg.modo === "sair") {
  // o formulário do Sair (sair.html) ou o do Entrar (entrar.html: a sessão do passe de quem estava antes)
  els[cfg.id || "sair-plataforma"] = elemento(cfg.id || "sair-plataforma", {getAttribute: function (n) {
    return n === "action" ? cfg.acao : n === "data-entrar" ? "/nexus/entrar" : null;
  }});
} else {
  els["porta"] = elemento("porta");
  els["porta-dados"] = elemento("porta-dados", {textContent: JSON.stringify(cfg.dados || {})});
  els["porta-alerta"] = elemento("porta-alerta");
  if (cfg.moldura) {
    els["porta-moldura"] = elemento("porta-moldura", {contentWindow: {document: {addEventListener: ouvir("moldura")}}});
    els["porta-passe"] = elemento("porta-passe", {
      submit: function () { feito.envios++; feito.passes.push(campoPasse.value); },
      querySelector: function (sel) { return sel.indexOf("passe") >= 0 ? campoPasse : null; }});
  }
  if (cfg.seletor) {
    els["porta-usina"] = elemento("porta-usina");
    els["porta-usina-nota"] = elemento("porta-usina-nota");
  }
  Object.keys(cfg.elementos || {}).forEach(function (id) { els[id] = elemento(id, cfg.elementos[id]); });
}

// o relógio da página (Date.now) anda só pelos passos `avancar`
let agora = 1760000000000;
class DataFalsa extends Date {
  static now() { return agora; }
}

const intervalos = [];

const pagina = new URL(cfg.pagina);
const local = {href: pagina.href, origin: pagina.origin, pathname: pagina.pathname, search: pagina.search,
               assign: function (u) { feito.foiPara = String(u); }, replace: function (u) { feito.foiPara = String(u); },
               reload: function () { feito.foiPara = "recarregar"; }};
const caixa = {
  document: {getElementById: function (id) { return els[id] || null; }, querySelectorAll: function () { return []; },
             querySelector: function () { return null; }, visibilityState: "visible",
             addEventListener: ouvir("documento"),
             createElement: function () { return elemento("criado"); }},
  window: {addEventListener: ouvir("janela"),
           nexusEntrarDeNovo: function (u) { feito.entrarDeNovo = u == null ? "" : String(u); }},
  location: local,
  history: {state: null, replaceState: function (_s, _t, u) { feito.enderecos.push(String(u)); }},
  fetch: function (url, opcoes) {
    feito.pedidos.push({url: String(url), metodo: (opcoes && opcoes.method) || "GET"});
    // o corpo de cada pedido, na mesma ordem (à parte: os testes de antes comparam os pedidos inteiros)
    feito.corpos.push(opcoes && opcoes.body != null ? String(opcoes.body) : null);
    const r = (cfg.respostas || {})[String(url)];
    if (r) {
      return Promise.resolve({type: r.tipo || "basic", status: r.status, ok: r.status >= 200 && r.status < 300,
                              json: function () { return Promise.resolve(r.json || {}); }});
    }
    // a plataforma sem sessão: 401 (o Diagnóstico tenta abrir a sessão com o passe da lista)
    return Promise.resolve({type: "basic", status: 401, ok: false, json: function () { return Promise.resolve({}); }});
  },
  FormData: function (f) { this.f = f; },
  URL: URL, URLSearchParams: URLSearchParams, Promise: Promise, JSON: JSON, AbortController: AbortController,
  Date: DataFalsa,
  setTimeout: function (f, ms) { return ms > 1000 ? 0 : setTimeout(f, 0); }, clearTimeout: clearTimeout,
  setInterval: function (f, ms) { intervalos.push(f); return intervalos.length; }, clearInterval: function () {},
};
let codigo = fs.readFileSync(arquivo, "utf-8");
if (cfg.modo === "sair") codigo = cfg.script;
vm.runInNewContext(codigo, caixa);

function esperar() { return new Promise(function (ok) { setTimeout(ok, 20); }); }

(async function () {
  await esperar();
  for (const passo of cfg.passos || []) {
    if (passo.mensagem) {
      const fonte = passo.de === "outra" ? {} : (els["porta-moldura"] || {}).contentWindow;
      const ev = {source: fonte, origin: passo.origem || pagina.origin, data: passo.mensagem};
      (ouvintes.janela.message || []).forEach(function (f) { f(ev); });
    }
    if (passo.avancar) agora += passo.avancar;
    if (passo.intervalo) intervalos.forEach(function (f) { f(); });
    if (passo.visivel) (ouvintes.documento.visibilitychange || []).forEach(function (f) { f(); });
    if (passo.carregar) ((els["porta-moldura"] || {_ouvintes: {}})._ouvintes.load || []).forEach(function (f) { f(); });
    if (passo.evento) {
      const ev = {type: passo.evento, key: passo.tecla || ""};
      (ouvintes[passo.em || "documento"][passo.evento] || []).forEach(function (f) { f(ev); });
    }
    await esperar();
  }
  await new Promise(function (ok) { setTimeout(ok, 50); });
  const alerta = els["porta-alerta"];
  feito.alerta = alerta && !alerta.hidden ? alerta.textContent : null;
  feito.intervalos = intervalos.length;
  feito.elementos = {};
  Object.keys(cfg.elementos || {}).forEach(function (id) {
    feito.elementos[id] = {hidden: els[id].hidden, href: els[id].href == null ? null : String(els[id].href)};
  });
  process.stdout.write(JSON.stringify(feito));
})();
