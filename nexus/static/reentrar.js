/* nexus/static/reentrar.js — o pop-up de login (24/11/2026).

   Levi, 24/11/2026: os supervisores preenchiam a OS, a solicitação ou a OS avulsa no OS Creator e, ao finalizar,
   "aparece lá o login, para eles fazerem o login, eles perdem tudo"; "tem que sempre aparecer um pop-up em cima, ó, faça
   o login. E aí ele loga, e ele não perde o que ele fez". A sessão do Fracttal cai sozinha (o token vence) ou por fora (o
   Fracttal aceita UMA sessão por conta: entrar no site ou no celular derruba a do Nexus), e até aqui a janela inteira ia ao
   Entrar (`nexusEntrarDeNovo`), levando junto o que estava preenchido na moldura do OS Creator.

   `window.nexusReentrar({tipo, email})` abre o pop-up por cima da tela e devolve uma Promise: true quando a pessoa entrou,
   false quando ela disse "Agora não". Um pop-up só por vez (a 2ª chamada recebe a mesma Promise). A tela debaixo não é
   tocada: nada navega, nada recarrega.
   - tipo "nexus" (o padrão): a sessão do Nexus acabou junto com a do Fracttal (quem entrou pelo Fracttal). O pop-up entra
     pelo Entrar de sempre (`/entrar`, em JSON: as mesmas travas e os mesmos cookies, inclusive a sessão do OS Creator).
   - tipo "os": só a sessão do Fracttal do OS Creator caiu (quem entrou pela senha de administrador ou pela Microsoft). O
     pop-up entra pelo `/os/login` do OS Creator, também em JSON.
   Com a Microsoft ligada, a porta do Nexus não aceita a senha do Fracttal: o pop-up oferece o Entrar numa aba nova e o
   "Já entrei", que confere a sessão antes de fechar.

   A casca (base.html) põe `window.NEXUS_REENTRAR` = {raiz, email, ms} antes de carregar este arquivo; aberto fora dela
   (o OS Creator sozinho, `os_web/static/relogin.js`), a raiz sai do endereço. As cores são as do tema (nexus.css, e o
   os.css para o OS Creator sozinho): aqui só classes. */
(function () {
  "use strict";
  if (window.nexusReentrar) return;
  var pendente = null;

  function cfg() { return window.NEXUS_REENTRAR || {}; }
  function raiz() {
    var c = cfg();
    if (typeof c.raiz === "string") return c.raiz;
    var i = location.pathname.indexOf("/" + "os/");
    return i > 0 ? location.pathname.slice(0, i) : "";
  }
  // todo caminho do Nexus com a raiz em que ele roda (o prefixo, quando há: tests/test_prefixo.py)
  function rota(c) { return raiz() + c; }
  // o fetch de antes do embrulho do OS Creator (relogin.js): o pop-up nunca chama o pop-up
  function buscar(url, opcoes) { return (window.__nexusFetch || window.fetch).call(window, url, opcoes); }

  function conferir(tipo) {
    var url = tipo === "os" ? rota("/os/api/sessao") : rota("/os/_nexus/sessao");
    return buscar(url, {credentials: "same-origin", cache: "no-store", redirect: "manual"}).then(function (r) {
      if (r.type === "opaqueredirect" || r.status !== 200) return false;
      return r.json().then(function (j) { return !!(j && j.ok); }, function () { return false; });
    }, function () { return false; });
  }

  function entrar(tipo, email, senha) {
    var fd = new FormData();
    fd.append("email", email);
    fd.append("senha", senha);
    return buscar(tipo === "os" ? rota("/os/login") : rota("/entrar"),
                  {method: "POST", body: fd, credentials: "same-origin", headers: {"Accept": "application/json"}})
      .then(function (r) {
        return r.json().then(function (j) { return j || {}; }, function () { return {}; }).then(function (j) {
          if (r.ok && j.ok) return {ok: true};
          return {ok: false, erro: j.erro || ("Não deu para entrar agora (" + r.status + "). Tente de novo.")};
        });
      }, function () { return {ok: false, erro: "Sem conexão com o servidor. Confira a rede e tente de novo."}; });
  }

  var MARCA = (
    '<div class="nx-reentrar-caixa" role="dialog" aria-modal="true" aria-labelledby="nxr_t" aria-describedby="nxr_d">' +
    '<h2 class="nx-reentrar-t" id="nxr_t"><i class="ph ph-lock-key" aria-hidden="true"></i> Sua sessão do Fracttal caiu</h2>' +
    '<p class="nx-reentrar-d" id="nxr_d">Entre de novo aqui mesmo. <b>Nada do que você preencheu se perde</b>: a tela ' +
    'continua como estava.</p>' +
    '<form class="nx-reentrar-form" data-form novalidate>' +
    '<label class="nx-reentrar-l"><span class="gc-rotulo">E-mail do Fracttal</span>' +
    '<input class="gc-campo" type="email" name="email" autocomplete="username" required></label>' +
    '<label class="nx-reentrar-l"><span class="gc-rotulo">Senha</span>' +
    '<input class="gc-campo" type="password" name="senha" autocomplete="current-password" required></label>' +
    '<p class="nx-reentrar-erro os-erro" data-erro role="alert" hidden></p>' +
    '<div class="nx-reentrar-bts"><button type="submit" class="gc-btn gc-btn--primario" data-entrar>Entrar</button>' +
    '<button type="button" class="gc-btn gc-btn--contorno" data-nao>Agora não</button></div>' +
    '</form>' +
    '<div class="nx-reentrar-ms" data-ms hidden><a class="gc-btn gc-btn--primario" data-ms-link target="_blank" ' +
    'rel="noopener">Entrar com a conta Microsoft</a><button type="button" class="gc-btn gc-btn--contorno" data-nao>' +
    'Agora não</button></div>' +
    '<p class="nx-reentrar-pe">Entrou por outro caminho? <a data-aba target="_blank" rel="noopener">Abrir o Entrar numa ' +
    'aba nova</a> e depois <button type="button" class="nx-reentrar-link" data-ja>já entrei</button>.</p>' +
    '<p class="nx-reentrar-nota">O Fracttal aceita uma sessão por conta: entrar no Fracttal em outro lugar (o site, o ' +
    'celular) derruba esta.</p>' +
    '</div>');

  function montar(tipo, opcoes, fim) {
    var c = cfg();
    var antes = document.activeElement;
    var fundo = document.createElement("div");
    fundo.className = "nx-reentrar";
    fundo.innerHTML = MARCA;
    var caixa = fundo.firstChild;
    var form = caixa.querySelector("[data-form]"), erro = caixa.querySelector("[data-erro]");
    var campoEmail = form.elements.email, campoSenha = form.elements.senha, botao = caixa.querySelector("[data-entrar]");
    campoEmail.value = opcoes.email || c.email || "";
    caixa.querySelector("[data-aba]").href = c.ms && tipo === "nexus" ? rota("/entrar?ms=1") : rota("/entrar");
    if (c.ms && tipo === "nexus") {
      // a porta é a Microsoft: a senha do Fracttal não entra no Nexus; a conta Microsoft entra numa aba nova
      form.hidden = true;
      var ms = caixa.querySelector("[data-ms]");
      ms.hidden = false;
      ms.querySelector("[data-ms-link]").href = rota("/entrar?ms=1");
    }
    document.body.appendChild(fundo);

    function dizer(texto) { erro.textContent = texto || ""; erro.hidden = !texto; }
    function fechar(ok) {
      document.removeEventListener("keydown", teclas, true);
      fundo.remove();
      try { if (antes && antes.focus) antes.focus(); } catch (e) { /* o foco de antes já saiu da tela */ }
      fim(ok);
    }
    function teclas(e) {
      if (e.key === "Escape") { e.preventDefault(); fechar(false); return; }
      if (e.key !== "Tab") return;
      // o foco fica dentro do pop-up (aria-modal): do último volta ao primeiro, e vice-versa
      var focos = Array.prototype.filter.call(caixa.querySelectorAll("a[href], button, input"), function (x) {
        return !x.disabled && x.offsetParent !== null;
      });
      if (!focos.length) return;
      var i = focos.indexOf(document.activeElement);
      if (e.shiftKey && i <= 0) { e.preventDefault(); focos[focos.length - 1].focus(); }
      else if (!e.shiftKey && i === focos.length - 1) { e.preventDefault(); focos[0].focus(); }
    }
    document.addEventListener("keydown", teclas, true);

    Array.prototype.forEach.call(caixa.querySelectorAll("[data-nao]"), function (b) {
      b.addEventListener("click", function () { fechar(false); });
    });
    caixa.querySelector("[data-ja]").addEventListener("click", function () {
      dizer("");
      conferir(tipo).then(function (ok) {
        if (ok) fechar(true);
        else dizer("Ainda não achei a sessão aberta. Entre na outra aba e clique de novo em “já entrei”.");
      });
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var email = campoEmail.value.trim(), senha = campoSenha.value;
      if (!email || !senha) { dizer("Informe o e-mail e a senha do Fracttal."); (email ? campoSenha : campoEmail).focus(); return; }
      botao.disabled = true;
      botao.textContent = "Entrando…";
      dizer("");
      entrar(tipo, email, senha).then(function (r) {
        botao.disabled = false;
        botao.textContent = "Entrar";
        if (r.ok) { fechar(true); return; }
        campoSenha.value = "";
        dizer(r.erro);
        campoSenha.focus();
      });
    });
    var primeiro = form.hidden ? caixa.querySelector("[data-ms-link]") : (campoEmail.value ? campoSenha : campoEmail);
    primeiro.focus();
  }

  window.nexusReentrar = function (opcoes) {
    if (pendente) return pendente;
    var o = opcoes || {};
    var tipo = o.tipo === "os" ? "os" : "nexus";
    pendente = new Promise(function (resolver) {
      montar(tipo, o, function (ok) { pendente = null; resolver(ok); });
    });
    return pendente;
  };
})();
