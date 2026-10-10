/* Roda no node a parte da PÁGINA do porta.js (e o script do sair.html), com um DOM de mentira, e diz o que ela fez:
   quantas vezes enviou o formulário do passe, que pedidos fez (fetch) e se avisou. Revisão de 10/10/2026 da porta única:
   o porta.js enviava o passe mesmo com a plataforma configurada em OUTRA origem (só avisava), e o base_da_plataforma
   aceita http em loopback: com a NEXUS_PLATAFORMA_URL interna do servidor, cada visitante mandava um passe válido, com
   o e-mail dele, para a porta local da própria máquina. O que se confere aqui é que nada sai para outra origem.

   Uso: node porta_pagina_falsa.js <arquivo.js> '<config JSON>'
   config: {pagina: "https://app.exemplo.test/nexus/t/...", modo: "porta" | "sair", dados, moldura, seletor, acao} */
"use strict";
const fs = require("fs");
const vm = require("vm");

const [arquivo, textoCfg] = process.argv.slice(2);
const cfg = JSON.parse(textoCfg);
const feito = {envios: 0, pedidos: [], alerta: null, foiPara: null};

function elemento(id, extra) {
  return Object.assign({id: id, hidden: true, textContent: "", innerHTML: "", options: [], disabled: false,
                        addEventListener: function () {}, setAttribute: function () {}, removeAttribute: function () {},
                        appendChild: function () {}, getAttribute: function () { return null; }}, extra || {});
}

const els = {};
if (cfg.modo === "sair") {
  els["sair-plataforma"] = elemento("sair-plataforma", {getAttribute: function (n) {
    return n === "action" ? cfg.acao : n === "data-entrar" ? "/nexus/entrar" : null;
  }});
} else {
  els["porta"] = elemento("porta");
  els["porta-dados"] = elemento("porta-dados", {textContent: JSON.stringify(cfg.dados || {})});
  els["porta-alerta"] = elemento("porta-alerta");
  if (cfg.moldura) {
    els["porta-moldura"] = elemento("porta-moldura", {contentWindow: {}});
    els["porta-passe"] = elemento("porta-passe", {submit: function () { feito.envios++; }});
  }
  if (cfg.seletor) {
    els["porta-usina"] = elemento("porta-usina");
    els["porta-usina-nota"] = elemento("porta-usina-nota");
  }
}

const pagina = new URL(cfg.pagina);
const local = {href: pagina.href, origin: pagina.origin, pathname: pagina.pathname, search: pagina.search,
               assign: function (u) { feito.foiPara = String(u); }, replace: function (u) { feito.foiPara = String(u); }};
const caixa = {
  document: {getElementById: function (id) { return els[id] || null; }, querySelectorAll: function () { return []; },
             querySelector: function () { return null; },
             createElement: function () { return elemento("criado"); }},
  window: {addEventListener: function () {}},
  location: local,
  history: {state: null, replaceState: function () {}},
  fetch: function (url, opcoes) {
    feito.pedidos.push({url: String(url), metodo: (opcoes && opcoes.method) || "GET"});
    // a plataforma sem sessão: 401 (o Diagnóstico tenta abrir a sessão com o passe da lista)
    return Promise.resolve({type: "basic", status: 401, ok: false, json: function () { return Promise.resolve({}); }});
  },
  FormData: function (f) { this.f = f; },
  URL: URL, URLSearchParams: URLSearchParams, Promise: Promise, JSON: JSON, AbortController: AbortController,
  setTimeout: function (f, ms) { return ms > 1000 ? 0 : setTimeout(f, 0); }, clearTimeout: clearTimeout,
};
let codigo = fs.readFileSync(arquivo, "utf-8");
if (cfg.modo === "sair") codigo = cfg.script;
vm.runInNewContext(codigo, caixa);
setTimeout(function () {
  const alerta = els["porta-alerta"];
  feito.alerta = alerta && !alerta.hidden ? alerta.textContent : null;
  process.stdout.write(JSON.stringify(feito));
}, 50);
