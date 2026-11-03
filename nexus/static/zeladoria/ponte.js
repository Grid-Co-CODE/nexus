/* A ponte da zeladoria: o `window.supabase` que o clone do Radar (nexus/torres/zeladoria/clone/radar.html) usa, agora
   falando com as rotas da torre Zeladoria em vez do Supabase.

   O clone foi escrito para o supabase-js v2 e continua escrito assim (Levi, 03/11/2026: "a mesma lógica e caminhos do
   BD"). Esta ponte entrega só o que ele usa, com a mesma forma de resposta do PostgrestBuilder da v2.118:
   {data, error, count, status, statusText}. O construtor se encadeia (select, eq, neq, order), vale dentro de
   Promise.resolve e nunca lança: o erro, inclusive o de rede, vem no `error`, como no supabase-js.

   Até a troca (docs/superpowers/specs/2026-11-03-zeladoria-no-nexus-design.md) a torre é só leitura: gravar e as
   funções do financeiro (rpc) voltam o erro SOMENTE_LEITURA sem ir ao servidor. A exceção é o retrato do cronograma, que
   o clone regrava sozinho ao abrir: ele é derivado, e recusá-lo poria um aviso de erro em toda abertura.

   O login é o do Nexus: `onAuthStateChange` entrega a pessoa de /api/eu, e as telas de senha do Radar não servem mais.
   Sem `storage`: sem ele, o clone pede as fotos da ronda à função `fracttal-fotos`, que a torre atende.

   A configuração vem do servidor em `window.ZELADORIA` = {api, somenteLeitura, sair}, com os endereços já montados
   (o Nexus pode rodar debaixo de um prefixo). */
(function (w) {
  "use strict";
  var cfg = w.ZELADORIA || {};
  var SOMENTE_LEITURA = { message: "Cópia só leitura até a troca: edite no Radar.", code: "SOMENTE_LEITURA" };
  var DERIVADAS = { rf_cronograma_publico: true };

  function resposta(data, error, status, statusText) {
    return { data: data, error: error, count: null, status: status, statusText: statusText || "" };
  }

  // Sem sessão, o portão do Nexus manda o pedido para o login: o fetch segue o redirecionamento e recebe a página HTML
  // com 200. Sem esta conferência, o clone recebia "sem erro e sem dado" e montava o Radar vazio sem aviso (revisão
  // final de 03/11/2026).
  var SESSAO = { message: "Sua sessão do Nexus acabou: entre de novo.", code: "SESSAO" };

  function semSessao(r) {
    var tipo = (r.headers && r.headers.get && r.headers.get("content-type")) || "";
    return r.redirected || tipo.indexOf("json") < 0;
  }

  function pedir(url, opcoes) {
    return w.fetch(url, opcoes || { credentials: "same-origin" }).then(function (r) {
      if (semSessao(r)) return resposta(null, SESSAO, r.status, r.statusText);
      return r.json().then(function (corpo) { return corpo; }, function () { return null; }).then(function (corpo) {
        if (r.ok) return resposta(corpo, null, r.status, r.statusText);
        var msg = (corpo && (corpo.erro || corpo.message)) || ("O Nexus respondeu " + r.status + ".");
        return resposta(null, { message: msg, code: String(r.status) }, r.status, r.statusText);
      });
    }, function () {
      return resposta(null, { message: "Sem conexão com o Nexus agora. Tente de novo em instantes.", code: "REDE" }, 0, "");
    });
  }

  function construtor(view) {
    var filtros = [], ordem = null, gravando = null, promessa = null;
    var b = {
      select: function () { return b; },
      eq: function (col, val) { filtros.push(["eq", col, val]); return b; },
      neq: function (col, val) { filtros.push(["neq", col, val]); return b; },
      order: function (col, opcoes) {
        ordem = col + ":" + (opcoes && opcoes.ascending === false ? "desc" : "asc");
        return b;
      },
      insert: function () { gravando = "insert"; return b; },
      update: function () { gravando = "update"; return b; },
      upsert: function () { gravando = "upsert"; return b; },
      delete: function () { gravando = "delete"; return b; },
      then: function (ok, falha) {
        if (!promessa) promessa = executar();
        return promessa.then(ok, falha);
      },
    };
    function executar() {
      if (gravando) {
        if (gravando === "upsert" && DERIVADAS[view]) return Promise.resolve(resposta(null, null, 201, "Created"));
        return Promise.resolve(resposta(null, SOMENTE_LEITURA, 405, ""));
      }
      var partes = filtros.map(function (f) { return f[0] + "=" + encodeURIComponent(f[1] + ":" + JSON.stringify(f[2])); });
      if (ordem) partes.push("order=" + encodeURIComponent(ordem));
      return pedir(cfg.api + "/rf/" + encodeURIComponent(view) + (partes.length ? "?" + partes.join("&") : ""));
    }
    return b;
  }

  function login() {
    return Promise.resolve({ data: null, error: { message: "O login é o do Nexus: entre pelo Nexus." } });
  }

  function createClient() {
    return {
      from: construtor,
      rpc: function () { return Promise.resolve(resposta(null, SOMENTE_LEITURA, 405, "")); },
      auth: {
        onAuthStateChange: function (cb) {
          pedir(cfg.api + "/eu").then(function (r) {
            // sem sessão, a página inteira do Nexus recarrega e o portão leva ao login (a tela de senha do Radar não
            // serve mais)
            if (r.error && r.error.code === "SESSAO") { w.top.location.reload(); return; }
            var sessao = r.data && r.data.user ? { user: r.data.user } : null;
            setTimeout(function () { cb("INITIAL_SESSION", sessao); }, 0);
          });
          return { data: { subscription: { unsubscribe: function () {} } } };
        },
        signOut: function () {
          if (cfg.sair) w.top.location.href = cfg.sair;
          return Promise.resolve({ error: null });
        },
        signInWithPassword: login,
        signUp: login,
        resetPasswordForEmail: login,
        updateUser: login,
      },
      functions: {
        invoke: function (nome, opcoes) {
          return pedir(cfg.api + "/funcao/" + encodeURIComponent(nome), {
            method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
            body: JSON.stringify((opcoes && opcoes.body) || {}),
          }).then(function (r) { return { data: r.data, error: r.error }; });
        },
      },
    };
  }

  w.supabase = { createClient: createClient };
})(window);
