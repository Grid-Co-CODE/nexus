/* Comando › Nexus Insights (19/11/2026): a caixa da Nexus IA e o portfólio vêm por trás, depois da página, para a lista
   dos insights abrir na hora mesmo com a conta do portfólio fria (a 1ª visita depois de um deploy leva perto de 40 s).
   Cada [data-ins-pedaco] pede o seu endereço e se troca pelo que volta; a caixa da IA é a do comando/ia.js, que escuta
   os cliques da página inteira e serve ao pedaço que chega depois.

   O funil do portfólio (Levi: "cliente tal, tá ruim por causa disso. Usina tal. Aí vai ter a opção abrir prontuário"):
   - o clique num cliente [data-inf-cli] mostra o painel dele e esconde os outros;
   - o "Perguntar à Nexus IA" [data-inf-perguntar] escreve a pergunta pronta na caixa do alto e manda, e a página sobe até
     a caixa para a pessoa ver a resposta chegar. Sem chave de IA o botão de enviar fica desligado: aí só escreve. */
(function () {
  "use strict";
  // o pedaço que volta "montando" ([data-ins-repetir], a conta fria logo depois de um deploy) é pedido de novo sozinho,
  // até 30 vezes; o que falha (a rede, o túnel) também, com o aviso no lugar em vez de sumir
  var TENTATIVAS = 30;
  function pedir(lugar, n) {
    fetch(lugar.getAttribute("data-ins-pedaco"), {credentials: "same-origin", headers: {"Accept": "text/html"}})
      .then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.text(); })
      .then(function (h) {
        lugar.innerHTML = h || "";
        var rep = lugar.querySelector("[data-ins-repetir]");
        if (rep && n < TENTATIVAS) setTimeout(function () { pedir(lugar, n + 1); }, 1000 * (+rep.getAttribute("data-ins-repetir") || 5));
      })
      .catch(function () {
        if (n >= TENTATIVAS) { lugar.innerHTML = ""; return; }
        if (lugar.querySelector(".ins-lendo")) lugar.querySelector(".ins-lendo").textContent = "Não consegui ler agora; tentando de novo…";
        setTimeout(function () { pedir(lugar, n + 1); }, 10000);
      });
  }
  document.querySelectorAll("[data-ins-pedaco]").forEach(function (lugar) { pedir(lugar, 0); });

  function escolher(botao) {
    var alvo = botao.getAttribute("data-inf-cli");
    document.querySelectorAll("[data-inf-cli]").forEach(function (b) {
      b.setAttribute("aria-pressed", b === botao ? "true" : "false");
    });
    document.querySelectorAll(".inf-painel").forEach(function (p) { p.hidden = p.id !== alvo; });
    var painel = document.getElementById(alvo);
    // o painel fica no alto da grade: escolhido um cliente lá de baixo, a página sobe até ele, logo abaixo do chat preso
    if (painel) {
      var falta = painel.getBoundingClientRect().top - (topo() + chatAltura() + 12);
      if (falta < 0) window.scrollBy(0, falta);
    }
    // na tela estreita o painel fica embaixo da lista: leva a pessoa até ele
    if (painel && window.matchMedia("(max-width: 900px)").matches) painel.scrollIntoView({block: "start"});
  }

  function perguntar(texto) {
    var caixa = document.querySelector("[data-ia]");
    if (!caixa) return;
    var campo = caixa.querySelector("[data-ia-pergunta]"), enviar = caixa.querySelector("[data-ia-enviar]");
    var form = caixa.querySelector("[data-ia-form]");
    if (!campo) return;
    campo.value = texto;
    // a caixa fica presa no alto: só sobe a página se ela não estiver à vista
    if (caixa.getBoundingClientRect().bottom < 0) caixa.scrollIntoView({block: "start"});
    if (enviar && !enviar.disabled && form) {
      if (form.requestSubmit) form.requestSubmit(); else enviar.click();
    } else {
      campo.focus();
    }
  }

  function topo() {
    return parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--topo")) || 60;
  }
  function chatAltura() {
    var c = document.querySelector(".inf-ia");
    return c ? c.getBoundingClientRect().height : 0;
  }

  // o chat preso no alto: o marco logo acima dele passou do topo → a caixa prendeu (recolhe as sugestões). Conferido a
  // cada rolagem (uma conta de posição só; com o IntersectionObserver, na volta ao alto a caixa às vezes ficava presa)
  var marco = document.querySelector("[data-inf-ia-marco]"), chat = document.querySelector(".inf-ia");
  function conferePresa() {
    if (marco && chat) chat.classList.toggle("inf-ia--presa", marco.getBoundingClientRect().top < topo());
  }
  window.addEventListener("scroll", conferePresa, {passive: true});
  conferePresa();

  // a usina aberta faz o painel crescer o que ela ocupa, para o texto caber sem rolar (Levi: "quando eu expandir a
  // usina, o tamanho expande junto"); fechada, o painel volta ao teto de 10 clientes
  document.addEventListener("toggle", function (ev) {
    var det = ev.target;
    if (!det.classList || !det.classList.contains("inf-us")) return;
    var painel = det.closest(".inf-painel");
    if (!painel) return;
    painel.style.maxHeight = "";
    var extra = 0;
    painel.querySelectorAll(".inf-us[open] .inf-us-corpo").forEach(function (c) { extra += c.getBoundingClientRect().height; });
    if (extra) painel.style.maxHeight = (parseFloat(getComputedStyle(painel).maxHeight) + extra) + "px";
    if (det.open) det.scrollIntoView({block: "nearest"});
  }, true);

  document.addEventListener("click", function (ev) {
    var cli = ev.target.closest && ev.target.closest("[data-inf-cli]");
    if (cli) { escolher(cli); return; }
    var p = ev.target.closest && ev.target.closest("[data-inf-perguntar]");
    if (p) { ev.preventDefault(); perguntar(p.getAttribute("data-inf-perguntar")); }
  });
})();
