/* os_creator/os_web/static/relogin.js — a sessão que cai no meio da tela abre o pop-up de login, e nada se perde
   (24/11/2026).

   Levi, 24/11/2026: os supervisores preenchiam a OS, a solicitação ou a OS avulsa e, ao finalizar, "aparece lá o login,
   para eles fazerem o login, eles perdem tudo"; "tem que sempre aparecer um pop-up em cima, ó, faça o login. E aí ele
   loga, e ele não perde o que ele fez". Todo envio do OS Creator é `fetch` (o único formulário que posta a página é o
   próprio login), então o embrulho fica aqui, num lugar só, carregado antes das telas (base.html, sem defer).

   A sessão caiu quando o pedido a uma rota do OS Creator volta com o 401 `{"login": true}` (o clone sem o JWT, o Fracttal
   que recusou o token, ou o Nexus que encerrou junto: `sessao_encerrada`) ou foi desviado ao Entrar do Nexus ou ao
   /os/login. Aí o pop-up abre (nexus/static/reentrar.js; o da casca do Nexus, a janela de cima, que cobre a tela toda;
   sem ela, o OS Creator aberto sozinho, o desta página) e o pedido espera:
   - entrou e o pedido é leitura (GET): ele é feito de novo, e a tela recebe a resposta certa, sem saber de nada;
   - entrou e o pedido é envio (criar, gravar): NÃO é refeito sozinho (a mesma regra do carga.js: formulário e gravação
     nunca, para não criar duas OS). A tela recebe a mensagem "Você entrou de novo. Clique outra vez para enviar: o que
     você preencheu continua na tela.", no lugar onde ela mostra os erros;
   - "Agora não": a tela recebe a resposta de antes, como sempre foi. */
(function () {
  "use strict";
  if (window.__nexusFetch || typeof window.fetch !== "function") return;
  var original = window.fetch.bind(window);
  window.__nexusFetch = original;                 // o pop-up busca por aqui: ele nunca chama o pop-up
  // "/" + "os/", e não a palavra inteira entre aspas: debaixo do prefixo a ponte reescreve todo caminho do OS Creator nos .js
  // dele (ponte._no_prefixo), e a raiz sairia vazia
  var OS = "/" + "os/";
  var i = location.pathname.indexOf(OS);
  var RAIZ = i > 0 ? location.pathname.slice(0, i) : "";
  var DE_NOVO = "Você entrou de novo. Clique outra vez para enviar: o que você preencheu continua na tela.";

  function doOs(url) {
    try {
      var u = new URL(url, location.href);
      return u.origin === location.origin && u.pathname.indexOf(RAIZ + OS) === 0;
    } catch (e) { return false; }
  }

  function tipoDaQueda(r) {
    if (r.redirected) {
      var p = "";
      try { p = new URL(r.url).pathname; } catch (e) { /* sem endereço: segue para o status */ }
      if (p === RAIZ + "/entrar") return Promise.resolve("nexus");
      if (p === RAIZ + OS + "login") return Promise.resolve("os");
    }
    if (r.status !== 401) return Promise.resolve(null);
    return r.clone().json().then(function (j) {
      if (!j || !j.login) return null;
      return j.sessao_encerrada ? "nexus" : "os";
    }, function () { return null; });
  }

  function emailDaPagina() {
    var m = document.querySelector('meta[name="os-conta-email"]');
    return m ? m.content : "";
  }

  // o pop-up da janela mais alta que o tem (a casca do Nexus); sem nenhuma, o desta página, carregado na hora
  function abridor() {
    var achado = null, w = window;
    try {
      while (w.parent && w.parent !== w) {
        w = w.parent;
        if (typeof w.nexusReentrar === "function") achado = w;
      }
    } catch (e) { /* uma janela de outra origem acima: fica a última da mesma origem */ }
    if (achado) return Promise.resolve(achado.nexusReentrar.bind(achado));
    if (typeof window.nexusReentrar === "function") return Promise.resolve(window.nexusReentrar);
    return new Promise(function (ok) {
      var s = document.createElement("script");
      s.src = RAIZ + "/static/reentrar.js";
      s.onload = function () { ok(typeof window.nexusReentrar === "function" ? window.nexusReentrar : null); };
      s.onerror = function () { ok(null); };
      document.head.appendChild(s);
    });
  }

  function pedirLogin(tipo) {
    return abridor().then(function (abrir) {
      return abrir ? abrir({tipo: tipo, email: emailDaPagina()}) : false;
    }, function () { return false; });
  }

  window.fetch = function (input, init) {
    var url = typeof input === "string" ? input : (input && input.url) || String(input || "");
    var metodo = String((init && init.method) || (input && input.method) || "GET").toUpperCase();
    var copia = (typeof Request !== "undefined" && input instanceof Request) ? input.clone() : null;
    return original(input, init).then(function (r) {
      if (!doOs(url)) return r;
      return tipoDaQueda(r).then(function (tipo) {
        if (!tipo) return r;
        return pedirLogin(tipo).then(function (entrou) {
          if (!entrou) return r;
          if (metodo === "GET" || metodo === "HEAD") return original(copia || input, init);
          return new Response(JSON.stringify({erro: DE_NOVO, relogou: true}),
                              {status: 409, headers: {"Content-Type": "application/json"}});
        });
      });
    });
  };
})();
