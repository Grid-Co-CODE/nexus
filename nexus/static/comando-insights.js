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
  document.querySelectorAll("[data-ins-pedaco]").forEach(function (lugar) {
    fetch(lugar.getAttribute("data-ins-pedaco"), {credentials: "same-origin", headers: {"Accept": "text/html"}})
      .then(function (r) { return r.ok ? r.text() : ""; })
      .then(function (h) { lugar.innerHTML = h || ""; })
      .catch(function () { lugar.innerHTML = ""; });
  });

  function escolher(botao) {
    var alvo = botao.getAttribute("data-inf-cli");
    document.querySelectorAll("[data-inf-cli]").forEach(function (b) {
      b.setAttribute("aria-pressed", b === botao ? "true" : "false");
    });
    document.querySelectorAll(".inf-painel").forEach(function (p) { p.hidden = p.id !== alvo; });
    var painel = document.getElementById(alvo);
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
    caixa.scrollIntoView({block: "start"});
    if (enviar && !enviar.disabled && form) {
      if (form.requestSubmit) form.requestSubmit(); else enviar.click();
    } else {
      campo.focus();
    }
  }

  document.addEventListener("click", function (ev) {
    var cli = ev.target.closest && ev.target.closest("[data-inf-cli]");
    if (cli) { escolher(cli); return; }
    var p = ev.target.closest && ev.target.closest("[data-inf-perguntar]");
    if (p) { ev.preventDefault(); perguntar(p.getAttribute("data-inf-perguntar")); }
  });
})();
