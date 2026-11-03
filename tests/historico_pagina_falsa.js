/* A página do Histórico de OS no node, com um DOM de mentira: lê o HTML que o servidor de verdade montou (o template
   renderizado, sem o Jinja), roda o script que está NELA e o `os_busca.js` do clone (a busca das listas), e deixa o teste
   mexer na página como a pessoa mexe: clicar, digitar, teclar, passar o tempo. Nada sai da máquina: o `fetch` e o
   `form.submit()` só anotam o que a página mandou.

   Por que existe (03/11/2026, filtros do Histórico no modelo A): o teste de antes recortava trechos do template pelo texto e
   rodava cada um com meia dúzia de elementos de mentira. Com o painel, as etiquetas e as listas digitáveis, o que importa é o
   conjunto (o clique fora descartar o que a troca acendeu; o × da etiqueta aplicar; o Enter da lista escolher), e o conjunto só
   se prova com o HTML de verdade e o script inteiro.

   Uso (de um teste Python): node -e "<RODAR>" historico_pagina_falsa.js os_busca.js '<opções JSON>' < pagina.html
   O `<RODAR>` faz `require(arquivo).abrir(html, opcoes)` e recebe a `pag`: ver `abrir` embaixo.
   opções: {pagina: "/os/historico?modo=criadas", hoje: "2026-11-03", celular: false, ponteiro_fino: false, busca_js: "<arquivo>",
            sessao: {chave: "valor"} (o sessionStorage de antes)} */
"use strict";
const fs = require("fs");
const vm = require("vm");

// ── o HTML vira árvore ─────────────────────────────────────────────────────────────────────────────────────────────────
const VAZIOS = new Set(["area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"]);
const TEXTO_CRU = new Set(["script", "style", "title", "textarea"]);
const ENTIDADES = {amp: "&", lt: "<", gt: ">", quot: "\"", apos: "'", nbsp: " "};

function decodifica(s) {
  return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e) => {
    if (e[0] === "#") return String.fromCodePoint(e[1].toLowerCase() === "x" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10));
    return Object.prototype.hasOwnProperty.call(ENTIDADES, e.toLowerCase()) ? ENTIDADES[e.toLowerCase()] : m;
  });
}

function lerHtml(html, doc) {
  const raiz = doc.criar("#fragmento");
  const pilha = [raiz];
  const topo = () => pilha[pilha.length - 1];
  const ATRIBUTO = /([^\s"'=<>\/]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?/g;
  const TAG_ABRE = /^<([a-zA-Z][\w:-]*)((?:\s+[^\s"'=<>\/]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s"'=<>`]+))?)*)\s*(\/?)>/;
  const TAG_FECHA = /^<\/([a-zA-Z][\w:-]*)\s*>/;
  let i = 0;
  const texto = (t) => { if (t) topo().appendChild(doc.criarTexto(decodifica(t))); };
  while (i < html.length) {
    const j = html.indexOf("<", i);
    if (j < 0) { texto(html.slice(i)); break; }
    texto(html.slice(i, j));
    const resto = html.slice(j);
    let m;
    if (resto.startsWith("<!--")) { const f = resto.indexOf("-->"); i = j + (f < 0 ? resto.length : f + 3); continue; }
    if (/^<!doctype/i.test(resto)) { i = j + resto.indexOf(">") + 1; continue; }
    if ((m = TAG_FECHA.exec(resto))) {
      const nome = m[1].toLowerCase();
      for (let k = pilha.length - 1; k > 0; k--) if (pilha[k].tagName.toLowerCase() === nome) { pilha.length = k; break; }
      i = j + m[0].length; continue;
    }
    if ((m = TAG_ABRE.exec(resto))) {
      const nome = m[1].toLowerCase(), no = doc.criar(nome);
      for (const a of m[2].matchAll(ATRIBUTO)) no.setAttribute(a[1].toLowerCase(), decodifica(a[2] ?? a[3] ?? a[4] ?? ""));
      topo().appendChild(no);
      i = j + m[0].length;
      if (TEXTO_CRU.has(nome)) {
        const f = html.toLowerCase().indexOf("</" + nome, i);
        const fim = f < 0 ? html.length : f;
        if (fim > i) no.appendChild(doc.criarTexto(html.slice(i, fim)));
        i = f < 0 ? html.length : html.indexOf(">", f) + 1;
      } else if (!VAZIOS.has(nome) && !m[3]) pilha.push(no);
      continue;
    }
    texto("<"); i = j + 1;
  }
  return raiz;
}

// ── os seletores (o que o script e o os_busca.js usam: tag, #id, .classe, [atributo], :checked, :not(), descendente, >, vírgula) ──
function partirFora(s, separadores) {
  const partes = []; let nivel = 0, atual = "";
  for (const ch of s) {
    if (ch === "[" || ch === "(") nivel++;
    if (ch === "]" || ch === ")") nivel--;
    if (nivel === 0 && separadores.includes(ch)) { partes.push(atual); atual = ""; } else atual += ch;
  }
  partes.push(atual);
  return partes;
}

function lerComposto(s) {
  const c = {tag: null, id: null, classes: [], attrs: [], nots: [], checked: false};
  let i = 0;
  const m = /^(?:[a-zA-Z][\w-]*|\*)/.exec(s);
  if (m) { c.tag = m[0] === "*" ? null : m[0].toUpperCase(); i = m[0].length; }
  while (i < s.length) {
    const ch = s[i];
    if (ch === "#" || ch === ".") {
      const n = /^[\w-]+/.exec(s.slice(i + 1))[0];
      if (ch === "#") c.id = n; else c.classes.push(n);
      i += n.length + 1;
    } else if (ch === "[") {
      const f = s.indexOf("]", i), corpo = s.slice(i + 1, f);
      const mm = /^([\w-]+)(?:=(?:"([^"]*)"|'([^']*)'|(.*)))?$/.exec(corpo);
      c.attrs.push({nome: mm[1], valor: mm[2] ?? mm[3] ?? mm[4]});
      i = f + 1;
    } else if (s.startsWith(":checked", i)) { c.checked = true; i += 8; }
    else if (s.startsWith(":not(", i)) {
      let nivel = 1, k = i + 5;
      while (k < s.length && nivel) { if (s[k] === "(") nivel++; if (s[k] === ")") nivel--; k++; }
      c.nots.push(lerComposto(s.slice(i + 5, k - 1)));
      i = k;
    } else throw new Error("seletor sem suporte no DOM de mentira: " + s);
  }
  return c;
}

function lerSeletor(s) {
  return partirFora(s, ",").map((alt) => {
    const passos = []; let comb = " ";
    // cada pedaço entre espaços; o ">" vira o combinador do pedaço seguinte
    const fichas = partirFora(alt.trim().replace(/\s*>\s*/g, " > "), " ").filter(Boolean);
    for (const f of fichas) { if (f === ">") { comb = ">"; continue; } passos.push({comb, comp: lerComposto(f)}); comb = " "; }
    return passos;
  });
}

function casaComposto(no, c) {
  if (no.nodeType !== 1) return false;
  if (c.tag && no.tagName !== c.tag) return false;
  if (c.id && no.id !== c.id) return false;
  for (const k of c.classes) if (!no.classList.contains(k)) return false;
  for (const a of c.attrs) {
    if (!no.hasAttribute(a.nome)) return false;
    if (a.valor !== undefined && no.getAttribute(a.nome) !== a.valor) return false;
  }
  if (c.checked && !no.checked) return false;
  for (const n of c.nots) if (casaComposto(no, n)) return false;
  return true;
}

function casaPassos(no, passos, k) {
  if (!casaComposto(no, passos[k].comp)) return false;
  if (k === 0) return true;
  if (passos[k].comb === ">") return !!no.parentNode && casaPassos(no.parentNode, passos, k - 1);
  for (let p = no.parentNode; p; p = p.parentNode) if (casaPassos(p, passos, k - 1)) return true;
  return false;
}

const casaSeletor = (no, alts) => alts.some((p) => casaPassos(no, p, p.length - 1));

// ── os elementos ───────────────────────────────────────────────────────────────────────────────────────────────────────
const doCamelo = (s) => s.replace(/[A-Z]/g, (m) => "-" + m.toLowerCase());

class No {
  constructor(tag, doc) {
    this.tagName = tag.toUpperCase(); this.nodeType = tag.startsWith("#") ? 11 : 1; this.doc = doc;
    this._attrs = new Map(); this._filhos = []; this.parentNode = null; this._ouv = {};
    this._valor = undefined; this._checked = undefined; this._ini = undefined;
    this.scrollTop = 0; this.offsetTop = 0; this.offsetHeight = 36; this.offsetWidth = 520; this.clientHeight = 260;
    const self = this;
    const estilos = {};                                                  // o style reflete no atributo, como no navegador
    this.style = new Proxy(estilos, {
      set: (o, k, v) => { if (v === "" || v == null) delete o[k]; else o[k] = v;
        const f = Object.entries(o).map(([a, b]) => doCamelo(a) + ": " + b).join("; ");
        if (f) self._attrs.set("style", f); else self._attrs.delete("style"); return true; },
      get: (o, k) => k === "setProperty" ? ((n, v) => { self.style[n] = v; }) : o[k],
    });
    this.dataset = new Proxy({}, {
      get: (_, k) => (typeof k === "string" && self._attrs.has("data-" + doCamelo(k))) ? self._attrs.get("data-" + doCamelo(k)) : undefined,
      set: (_, k, v) => { self._attrs.set("data-" + doCamelo(k), String(v)); return true; },
      has: (_, k) => self._attrs.has("data-" + doCamelo(k)),
      deleteProperty: (_, k) => { self._attrs.delete("data-" + doCamelo(k)); return true; },
    });
    this.classList = {
      _lista: () => (self._attrs.get("class") || "").split(/\s+/).filter(Boolean),
      contains: (c) => self.classList._lista().includes(c),
      add: (...cs) => { const l = self.classList._lista(); cs.forEach((c) => { if (!l.includes(c)) l.push(c); }); self._attrs.set("class", l.join(" ")); },
      remove: (...cs) => { self._attrs.set("class", self.classList._lista().filter((c) => !cs.includes(c)).join(" ")); },
      toggle: (c, forca) => { const tem = self.classList.contains(c), quer = forca === undefined ? !tem : !!forca;
        if (quer && !tem) self.classList.add(c); else if (!quer && tem) self.classList.remove(c); return quer; },
    };
  }
  // atributos
  getAttribute(n) { return this._attrs.has(n) ? this._attrs.get(n) : null; }
  // o <details> avisa (`toggle`) quando abre ou fecha, por código também, como no navegador
  setAttribute(n, v) { const era = this._attrs.has(n); this._attrs.set(n, String(v)); if (n === "open" && !era && this.tagName === "DETAILS") this.dispararToggle(); }
  removeAttribute(n) { const era = this._attrs.has(n); this._attrs.delete(n); if (n === "open" && era && this.tagName === "DETAILS") this.dispararToggle(); }
  hasAttribute(n) { return this._attrs.has(n); }
  get id() { return this.getAttribute("id") || ""; }
  set id(v) { this.setAttribute("id", v); }
  get className() { return this.getAttribute("class") || ""; }
  set className(v) { this.setAttribute("class", v); }
  get hidden() { return this.hasAttribute("hidden"); }
  set hidden(v) { if (v) this.setAttribute("hidden", ""); else this.removeAttribute("hidden"); }
  get disabled() { return this.hasAttribute("disabled"); }
  set disabled(v) { if (v) this.setAttribute("disabled", ""); else this.removeAttribute("disabled"); }
  get title() { return this.getAttribute("title") || ""; }
  set title(v) { this.setAttribute("title", v); }
  get type() { return (this.getAttribute("type") || (this.tagName === "BUTTON" ? "submit" : "text")).toLowerCase(); }
  set type(v) { this.setAttribute("type", v); }
  get name() { return this.getAttribute("name") || ""; }
  set name(v) { this.setAttribute("name", v); }
  get placeholder() { return this.getAttribute("placeholder") || ""; }
  set placeholder(v) { this.setAttribute("placeholder", v); }
  get open() { return this.hasAttribute("open"); }
  set open(v) { if (v) this.setAttribute("open", ""); else this.removeAttribute("open"); }
  dispararToggle() { this.dispatchEvent({type: "toggle", bubbles: false}); }
  // formulários
  get value() {
    if (this.tagName === "SELECT") { const o = this.options[this.selectedIndex]; return o ? o.value : ""; }
    if (this.tagName === "OPTION") return this.hasAttribute("value") ? this.getAttribute("value") : this.textContent;
    if (this._valor !== undefined) return this._valor;
    return this.getAttribute("value") || "";
  }
  set value(v) {
    if (this.tagName === "SELECT") { const i = this.options.findIndex((o) => o.value === String(v)); this._sel = i; return; }
    this._valor = String(v);
  }
  get checked() { return this._checked !== undefined ? this._checked : this.hasAttribute("checked"); }
  set checked(v) { this._checked = !!v; }
  get options() { return this.tagName === "SELECT" ? this.querySelectorAll("option") : []; }
  get selectedIndex() {
    if (this._sel !== undefined) return this._sel;
    const o = this.options, i = o.findIndex((x) => x.hasAttribute("selected"));
    return i >= 0 ? i : (o.length ? 0 : -1);
  }
  set selectedIndex(i) { this._sel = i; }
  get text() { return this.textContent; }
  get form() { return this.closest("form"); }
  get tabIndex() { return Number(this.getAttribute("tabindex") || 0); }
  set tabIndex(v) { this.setAttribute("tabindex", v); }
  // a árvore
  get children() { return this._filhos.filter((f) => f.nodeType === 1); }
  get childNodes() { return this._filhos.slice(); }
  get firstChild() { return this._filhos[0] || null; }
  get lastChild() { return this._filhos[this._filhos.length - 1] || null; }
  get firstElementChild() { return this.children[0] || null; }
  get parentElement() { return this.parentNode && this.parentNode.nodeType === 1 ? this.parentNode : null; }
  appendChild(n) { return this.insertBefore(n, null); }
  insertBefore(n, ref) {
    if (n.parentNode) n.parentNode.removeChild(n);
    const i = ref ? this._filhos.indexOf(ref) : -1;
    if (i < 0) this._filhos.push(n); else this._filhos.splice(i, 0, n);
    n.parentNode = this; return n;
  }
  removeChild(n) { const i = this._filhos.indexOf(n); if (i >= 0) { this._filhos.splice(i, 1); n.parentNode = null; } return n; }
  remove() { if (this.parentNode) this.parentNode.removeChild(this); }
  contains(n) { for (let p = n; p; p = p.parentNode) if (p === this) return true; return false; }
  get textContent() { return this._filhos.map((f) => f.nodeType === 3 ? f.nodeValue : f.textContent).join(""); }
  set textContent(t) { this._filhos.forEach((f) => { f.parentNode = null; }); this._filhos = []; if (t !== "" && t != null) this.appendChild(this.doc.criarTexto(String(t))); }
  set innerHTML(h) { this._filhos.forEach((f) => { f.parentNode = null; }); this._filhos = []; this._html = h; }
  get innerHTML() { return this._html || ""; }
  cloneNode(fundo) {
    const c = new No(this.tagName, this.doc);
    this._attrs.forEach((v, k) => c._attrs.set(k, v));
    if (fundo) this._filhos.forEach((f) => c.appendChild(f.nodeType === 3 ? this.doc.criarTexto(f.nodeValue) : f.cloneNode(true)));
    return c;
  }
  // buscas
  matches(s) { return casaSeletor(this, lerSeletor(s)); }
  closest(s) { const alts = lerSeletor(s); for (let p = this; p && p.nodeType === 1; p = p.parentNode) if (casaSeletor(p, alts)) return p; return null; }
  querySelectorAll(s) {
    const alts = lerSeletor(s), saida = [];
    const andar = (n) => { for (const f of n._filhos) if (f.nodeType === 1) { if (casaSeletor(f, alts)) saida.push(f); andar(f); } };
    andar(this); return saida;
  }
  querySelector(s) { return this.querySelectorAll(s)[0] || null; }
  getBoundingClientRect() { return {left: 100, right: 620, top: 40, bottom: 76, width: 520, height: 36}; }
  // eventos
  addEventListener(t, f, captura) { (this._ouv[t] = this._ouv[t] || []).push({f, captura: captura === true || (captura && captura.capture === true)}); }
  removeEventListener(t, f) { this._ouv[t] = (this._ouv[t] || []).filter((o) => o.f !== f); }
  _chamar(ev, fase) {
    for (const o of (this._ouv[ev.type] || []).slice()) {
      if (fase === "captura" && !o.captura) continue;
      if (fase === "bolha" && o.captura) continue;
      ev.currentTarget = this; o.f.call(this, ev);
      if (ev._imediato) return;
    }
  }
  dispatchEvent(ev) {
    ev.target = ev.target || this; ev.defaultPrevented = false; ev._parou = false;
    ev.preventDefault = () => { ev.defaultPrevented = true; };
    ev.stopPropagation = () => { ev._parou = true; };
    ev.stopImmediatePropagation = () => { ev._parou = true; ev._imediato = true; };
    const caminho = []; for (let n = this; n; n = n.parentNode) caminho.push(n);
    if (ev.bubbles !== false) {
      for (let k = caminho.length - 1; k > 0 && !ev._parou; k--) caminho[k]._chamar(ev, "captura");
      if (!ev._parou) this._chamar(ev, "alvo");
      for (let k = 1; k < caminho.length && !ev._parou; k++) caminho[k]._chamar(ev, "bolha");
    } else this._chamar(ev, "alvo");
    return !ev.defaultPrevented;
  }
  // o que o navegador faz sozinho
  click() {
    if (this.disabled) return;
    const ev = {type: "click", bubbles: true, target: this};
    const antes = this.checked;
    if (this.tagName === "INPUT" && this.type === "checkbox") this._checked = !antes;
    if (this.tagName === "INPUT" && this.type === "radio") this._checked = true;
    const livre = this.dispatchEvent(ev);
    if (!livre) { if (this.tagName === "INPUT" && this.type === "checkbox") this._checked = antes; return; }
    if (this.tagName === "INPUT" && (this.type === "checkbox" || (this.type === "radio" && !antes))) this.dispatchEvent({type: "change", bubbles: true, target: this});
    if (this.tagName === "SUMMARY" && this.parentNode && this.parentNode.tagName === "DETAILS") this.parentNode.open = !this.parentNode.open;
    if (this.tagName === "BUTTON" && this.type === "submit" && this.form) this.form._pedirEnvio();
    // a etiqueta passa o clique ao controle dela (só quando o alvo é a própria etiqueta, e não o controle dentro dela)
    if (this.tagName === "LABEL") {
      const alvo = this.hasAttribute("for") ? this.doc.getElementById(this.getAttribute("for")) : this.querySelector("input, select, textarea, button");
      if (alvo && alvo !== this) alvo.click();
    }
  }
  _pedirEnvio() {
    const ev = {type: "submit", bubbles: true, target: this};
    if (this.dispatchEvent(ev)) this.submit();
  }
  submit() {
    const campos = [];
    this.querySelectorAll("input, select, textarea").forEach((c) => {
      if (!c.name || c.disabled) return;
      if (c.tagName === "INPUT" && (c.type === "checkbox" || c.type === "radio") && !c.checked) return;
      campos.push([c.name, c.value]);
    });
    this.doc.envios.push(campos);
  }
  focus() { this.doc.ativo = this; this.dispatchEvent({type: "focus", bubbles: false}); }
  blur() { if (this.doc.ativo === this) this.doc.ativo = null; }
  select() {}
}

class Doc extends No {
  constructor() { super("#document", null); this.doc = this; this.nodeType = 9; this.envios = []; this.ativo = null; this.readyState = "interactive"; this.hidden = false; }
  criar(tag) { return new No(tag, this); }
  criarTexto(t) { return {nodeType: 3, nodeValue: t, parentNode: null, textContent: t}; }
  createElement(t) { return this.criar(t); }
  createElementNS(ns, t) { return this.criar(t); }
  createTextNode(t) { return this.criarTexto(t); }
  getElementById(id) { return this.querySelector("#" + id); }
  get activeElement() { return this.ativo; }
  get hidden() { return this._oculto === true; }
  set hidden(v) { this._oculto = !!v; }
  get documentElement() { return this.querySelector("html"); }
  get body() { return this.querySelector("body"); }
}

// ── a página ───────────────────────────────────────────────────────────────────────────────────────────────────────────
function abrir(html, opcoes) {
  opcoes = opcoes || {};
  const doc = new Doc();
  const arvore = lerHtml(html, doc);
  arvore._filhos.slice().forEach((f) => doc.appendChild(f));

  const pagina = new URL("http://localhost" + (opcoes.pagina || "/os/historico?modo=criadas"));
  const pag = {doc, envios: doc.envios, avisos: [], foiPara: [], enderecos: [], pedidos: [], agora: 0, erros: []};
  const guardado = Object.assign({}, opcoes.sessao || {});
  const FIXA = opcoes.hoje ? new Date(opcoes.hoje + "T12:00:00") : new Date();
  class DataFalsa extends Date {
    constructor(...a) { if (a.length === 0) super(FIXA.getTime()); else super(...a); }
    static now() { return FIXA.getTime(); }
  }
  const timers = []; let proximo = 1;
  const marcarTimer = (f, ms, repete) => { const t = {id: proximo++, quando: pag.agora + ms, f, repete: repete ? ms : 0}; timers.push(t); return t.id; };
  const local = {pathname: pagina.pathname, search: pagina.search, hash: "", origin: pagina.origin};
  Object.defineProperty(local, "href", {get: () => pagina.href, set: (v) => { pag.foiPara.push(String(v)); }});
  const sandbox = {
    document: doc, location: local, console, Date: DataFalsa, URLSearchParams, URL, Math, JSON, Promise, String, Number, Object, Array, RegExp,
    history: {replaceState: (a, b, url) => { pag.enderecos.push(url); }},
    sessionStorage: {getItem: (k) => (k in guardado ? guardado[k] : null), setItem: (k, v) => { guardado[k] = String(v); }, removeItem: (k) => { delete guardado[k]; }},
    localStorage: {getItem: () => null, setItem() {}, removeItem() {}},
    alert: (t) => { pag.avisos.push(String(t)); },
    fetch: (url) => { pag.pedidos.push(String(url)); return Promise.resolve({status: 204, ok: false, text: () => Promise.resolve(""), json: () => Promise.resolve({})}); },
    setTimeout: (f, ms) => marcarTimer(f, ms || 0, false), clearTimeout: (id) => { const i = timers.findIndex((t) => t.id === id); if (i >= 0) timers.splice(i, 1); },
    setInterval: (f, ms) => marcarTimer(f, ms, true), clearInterval: (id) => { const i = timers.findIndex((t) => t.id === id); if (i >= 0) timers.splice(i, 1); },
    requestAnimationFrame: (f) => { f(); return 0; },
    MutationObserver: class { observe() {} disconnect() {} },
    HTMLSelectElement: class {},
    Event: class { constructor(t, o) { this.type = t; Object.assign(this, o || {}); } },
    OsCarga: {token: () => "tok", mostrar() {}, esconder() {}, buscar: () => Promise.resolve({text: () => Promise.resolve("")})},
    Blob: class {}, navigator: {userAgent: "node"},
  };
  sandbox.window = sandbox;
  sandbox.matchMedia = (q) => ({matches: /max-width:\s*639px/.test(q) ? !!opcoes.celular : (/pointer:\s*fine/.test(q) ? !!opcoes.ponteiro_fino : false), media: q});
  sandbox.addEventListener = () => {};
  vm.createContext(sandbox);

  // o script da página (o único que tem o `enviar`) e depois o os_busca.js, que no navegador é `defer` (roda com a página pronta)
  const scripts = doc.querySelectorAll("script").filter((s) => !s.hasAttribute("src"));
  const doHistorico = scripts.find((s) => s.textContent.includes("function enviar(forcar, auto)"));
  if (!doHistorico) throw new Error("o script do Histórico não está na página");
  vm.runInContext(doHistorico.textContent, sandbox, {filename: "historico.html"});
  if (opcoes.busca_js) vm.runInContext(fs.readFileSync(opcoes.busca_js, "utf8"), sandbox, {filename: "os_busca.js"});

  // ── o que o teste faz na página ──
  pag.$ = (s) => doc.querySelector(s);
  pag.$$ = (s) => doc.querySelectorAll(s);
  pag.clicar = (no) => { if (typeof no === "string") no = pag.$(no); if (!no) throw new Error("sem elemento para clicar"); no.click(); };
  pag.digitar = (no, texto) => { no.value = texto; no.dispatchEvent({type: "input", bubbles: true}); };
  pag.tecla = (no, tecla, extra) => {
    if (typeof no === "string") no = pag.$(no);
    const ev = Object.assign({type: "keydown", bubbles: true, key: tecla, ctrlKey: false, metaKey: false}, extra || {});
    const livre = no.dispatchEvent(ev);
    // o que o navegador faz com o Enter num campo de formulário que ninguém tratou: manda o formulário pelo 1º botão de envio
    if (livre && tecla === "Enter" && no.tagName === "INPUT" && no.form) {
      const botao = no.form.querySelector("button[type=submit], input[type=submit]") || no.form.querySelector("button:not([type])");
      if (botao) botao.click();
    }
    return livre;
  };
  pag.avanca = (ms) => {
    const fim = pag.agora + ms;
    for (;;) {
      const prontos = timers.filter((t) => t.quando <= fim).sort((a, b) => a.quando - b.quando);
      if (!prontos.length) break;
      const t = prontos[0]; pag.agora = Math.max(pag.agora, t.quando);
      if (t.repete) t.quando += t.repete; else timers.splice(timers.indexOf(t), 1);
      t.f();
    }
    pag.agora = fim;
  };
  pag.visiveis = () => pag.$$("#tab_hist tbody tr[data-id]").filter((tr) => !tr.hidden).map((tr) => tr.dataset.id);
  pag.sessao = guardado;
  pag.texto = (no) => (typeof no === "string" ? pag.$(no) : no).textContent.replace(/\s+/g, " ").trim();
  pag.janela = sandbox;
  return pag;
}

module.exports = {abrir};
