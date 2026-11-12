// O SSO da zeladoria guarda e lê os dados pelo Nexus (12/11/2026), no lugar do Supabase, que parou em 11/11/2026.
//
// Este arquivo substitui o shared/supabase-client.js do site (o resto do site não muda): ele é o `window.supabase` que
// o app já usa, com o mesmo jeito de chamar (`from(...).select().eq().order()`, `insert`, `update`, `delete`,
// `storage.from(...).upload`, `auth`, `rpc`), e fala com a API do Nexus (nexus/sso/api.py no repositório do Nexus).
// As duas funções e os arquivos ficam no mesmo caminho de antes, debaixo do endereço do Nexus (IV_SUPABASE_URL), e o
// app monta esses endereços sozinho.
//
// A Gestão entra pelo login do Nexus: sem passe, a página da Gestão vai ao Nexus (/t/sso/voltar), que pede o login e
// volta com o passe no fim do endereço (#nexus_sso=...). O passe vale 8 h; vencido, a página busca outro sozinha.
// Os formulários do fornecedor não têm login: só enviam.
(function () {
  "use strict";

  // o endereço do Nexus. Para a prova numa cópia local, troque só esta linha
  var NEXUS = "https://app.gridco.com.br";
  var BASE = NEXUS + "/t/sso";
  var CHAVE = "nexus_sso_passe";

  window.IV_SUPABASE_URL = BASE;
  window.IV_SUPABASE_ANON_KEY = "nexus";

  // ── o passe da Gestão ──────────────────────────────────────────────────────────────────────────────────────────
  (function lerDoEndereco() {
    var m = /(?:^|[#&])nexus_sso=([^&]+)/.exec(location.hash || "");
    if (!m) return;
    try { localStorage.setItem(CHAVE, decodeURIComponent(m[1])); } catch (e) { /* sem armazenamento: vale só nesta página */ }
    window.__nexusSsoPasse = decodeURIComponent(m[1]);
    history.replaceState(null, "", location.pathname + location.search);
  })();

  function passe() {
    if (window.__nexusSsoPasse) return window.__nexusSsoPasse;
    try { return localStorage.getItem(CHAVE); } catch (e) { return null; }
  }

  function esquecerPasse() {
    window.__nexusSsoPasse = null;
    try { localStorage.removeItem(CHAVE); } catch (e) { /* nada */ }
  }

  function naGestao() { return /\/gestao(\/|$)/.test(location.pathname); }

  function irAoLogin() {
    var aqui = location.href.split("#")[0];
    location.href = BASE + "/voltar?para=" + encodeURIComponent(aqui);
  }

  // ── o pedido ao Nexus ──────────────────────────────────────────────────────────────────────────────────────────
  function pedir(metodo, caminho, corpo, ehFormulario) {
    var cab = {};
    var p = passe();
    if (p) cab.Authorization = "Bearer " + p;
    var opcoes = { method: metodo, headers: cab, credentials: "omit" };
    if (corpo !== undefined) {
      if (ehFormulario) opcoes.body = corpo;
      else { cab["Content-Type"] = "application/json"; opcoes.body = JSON.stringify(corpo); }
    }
    return fetch(BASE + caminho, opcoes).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (r.status === 401 && p) { esquecerPasse(); if (naGestao()) irAoLogin(); }
        if (!r.ok) return { data: null, error: { message: (j && (j.message || j.error)) || ("HTTP " + r.status), status: r.status } };
        return { data: j, error: null };
      });
    }, function () {
      return { data: null, error: { message: "Sem conexão com o servidor. Confira a internet e tente de novo." } };
    });
  }

  // ── from(view): a consulta ─────────────────────────────────────────────────────────────────────────────────────
  function Consulta(view) {
    this.view = view; this.acao = "select"; this.colunas = "*"; this.filtros = []; this.ordens = []; this.lim = null;
    this.um = null; this.linhas = null; this.patch = null; this.devolve = false; this._p = null;
  }
  Consulta.prototype.select = function (colunas) {
    if (this.acao === "select") this.colunas = colunas || "*"; else this.devolve = true;
    return this;
  };
  Consulta.prototype.eq = function (c, v) { this.filtros.push(["eq", c, v]); return this; };
  Consulta.prototype.neq = function (c, v) { this.filtros.push(["neq", c, v]); return this; };
  Consulta.prototype.order = function (c, o) { this.ordens.push([c, !(o && o.ascending === false) ? "asc" : "desc"]); return this; };
  Consulta.prototype.limit = function (n) { this.lim = n; return this; };
  Consulta.prototype.single = function () { this.um = "single"; return this; };
  Consulta.prototype.maybeSingle = function () { this.um = "maybe"; return this; };
  Consulta.prototype.insert = function (linhas) { this.acao = "insert"; this.linhas = [].concat(linhas); return this; };
  Consulta.prototype.upsert = function (linhas) { this.acao = "upsert"; this.linhas = [].concat(linhas); return this; };
  Consulta.prototype.update = function (patch) { this.acao = "update"; this.patch = patch || {}; return this; };
  Consulta.prototype["delete"] = function () { this.acao = "delete"; return this; };

  function umSo(res, modo) {
    if (res.error || !modo) return res;
    var d = res.data || [];
    if (d.length > 1) return { data: null, error: { message: "JSON object requested, multiple (or no) rows returned", code: "PGRST116" } };
    if (!d.length) return modo === "maybe" ? { data: null, error: null }
      : { data: null, error: { message: "JSON object requested, multiple (or no) rows returned", code: "PGRST116" } };
    return { data: d[0], error: null };
  }

  Consulta.prototype._rodar = function () {
    var self = this;
    if (this.acao === "select") {
      var q = [];
      this.filtros.forEach(function (f) { q.push(f[0] + "=" + encodeURIComponent(f[1] + ":" + JSON.stringify(f[2]))); });
      this.ordens.forEach(function (o) { q.push("order=" + encodeURIComponent(o[0] + ":" + o[1])); });
      if (this.lim != null) q.push("limit=" + encodeURIComponent(this.lim));
      if (this.colunas && this.colunas !== "*") q.push("select=" + encodeURIComponent(this.colunas.replace(/\s+/g, "")));
      return pedir("GET", "/api/v/" + encodeURIComponent(this.view) + (q.length ? "?" + q.join("&") : ""))
        .then(function (r) { return umSo(r, self.um); });
    }
    var op = { op: this.acao, view: this.view, filtros: this.filtros };
    if (this.linhas) op.linhas = this.linhas;
    if (this.patch) op.patch = this.patch;
    return pedir("POST", "/api/gravar", { ops: [op] }).then(function (r) {
      if (r.error) return r;
      var linhas = (r.data.resultado || [[]])[0] || [];
      if (!self.devolve) return { data: null, error: null };
      return umSo({ data: linhas, error: null }, self.um);
    });
  };
  Consulta.prototype.then = function (ok, falha) {
    if (!this._p) this._p = this._rodar();
    return this._p.then(ok, falha);
  };
  Consulta.prototype["catch"] = function (falha) { return this.then(null, falha); };

  // ── storage ────────────────────────────────────────────────────────────────────────────────────────────────────
  var assinadas = {};      // o endereço com a assinatura que a Gestão recebe ao enviar (para mostrar logo depois)
  function Bucket(nome) { this.nome = nome; }
  Bucket.prototype.upload = function (caminho, arquivo, opcoes) {
    var nome = this.nome, fd = new FormData();
    fd.append("bucket", nome);
    fd.append("caminho", caminho);
    fd.append("upsert", opcoes && opcoes.upsert ? "true" : "false");
    fd.append("arquivo", arquivo, String(caminho).split("/").pop());
    return pedir("POST", "/api/arquivo", fd, true).then(function (r) {
      if (r.error) return r;
      if (r.data.url && r.data.url.indexOf("?a=") > 0) assinadas[nome + "/" + caminho] = r.data.url;
      return { data: { path: caminho, fullPath: nome + "/" + caminho, id: nome + "/" + caminho }, error: null };
    });
  };
  Bucket.prototype.getPublicUrl = function (caminho) {
    return { data: { publicUrl: assinadas[this.nome + "/" + caminho] || (BASE + "/storage/v1/object/public/" + this.nome + "/" + caminho) } };
  };

  // ── auth: a sessão é a do Nexus ────────────────────────────────────────────────────────────────────────────────
  var sessaoLida = null;
  function lerSessao() {
    if (sessaoLida) return sessaoLida;
    sessaoLida = (function () {
      if (!passe()) return Promise.resolve(null);
      return pedir("GET", "/api/eu").then(function (r) {
        if (r.error || !r.data || !r.data.user) return null;
        return { access_token: passe(), token_type: "bearer", user: r.data.user };
      });
    })();
    return sessaoLida;
  }
  var auth = {
    getSession: function () {
      return lerSessao().then(function (s) { return { data: { session: s }, error: null }; });
    },
    getUser: function () {
      return lerSessao().then(function (s) { return { data: { user: s ? s.user : null }, error: null }; });
    },
    onAuthStateChange: function (cb) {
      lerSessao().then(function (s) {
        if (!s && naGestao()) { irAoLogin(); return; }
        cb(s ? "SIGNED_IN" : "SIGNED_OUT", s);
      });
      return { data: { subscription: { unsubscribe: function () {} } } };
    },
    signInWithPassword: function () { irAoLogin(); return Promise.resolve({ data: {}, error: null }); },
    signUp: function () { irAoLogin(); return Promise.resolve({ data: {}, error: null }); },
    signOut: function () {
      esquecerPasse();
      location.href = NEXUS + "/sair";
      return Promise.resolve({ error: null });
    }
  };

  var cliente = {
    from: function (view) { return new Consulta(view); },
    storage: { from: function (nome) { return new Bucket(nome); } },
    auth: auth,
    rpc: function (nome, args) {
      return pedir("POST", "/api/rpc/" + encodeURIComponent(nome), args || {});
    }
  };

  window.supabase = { createClient: function () { return cliente; } };
  window.getSupabaseClient = function () { return cliente; };
})();
