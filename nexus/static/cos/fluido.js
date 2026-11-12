/* static/cos/fluido.js — as telas do COS abrem quase na hora (checkup do COS, 12/11/2026).

   Pré-busca no passar do mouse: quando a pessoa para o mouse num link para outra tela do COS (65 ms, "moderate"), o
   navegador já pede a página; no clique ela vem pronta. Com as cópias do Andamento servidas na hora (nexus/cos/
   andamento.py, `_com_copia`), pedir a página não custa leitura nova à Ronda COS.

   - Chrome/Edge: Speculation Rules (o navegador decide, respeita economia de dados e memória).
   - Os outros: um <link rel="prefetch"> no passar do mouse.
   - Nunca o que baixa arquivo ou grava: fora o `formato=` (Excel/CSV), o `parcial=`, o que tem `download` e o que não é GET
     (formulários não entram). Os endereços que valem vêm de `window.NexusCosFluido.endereco` (o padrão é /t/cos/). */
(function () {
  "use strict";
  var CFG = window.NexusCosFluido || {};
  var raiz = typeof window.nexusRota === "function" ? window.nexusRota("/t/cos/") : "/t/cos/";
  var padrao = CFG.endereco || (raiz + "*");
  var fora = ["*formato=*", "*parcial=*", "*tv=1*"];

  if (window.HTMLScriptElement && HTMLScriptElement.supports && HTMLScriptElement.supports("speculationrules")) {
    var s = document.createElement("script");
    s.type = "speculationrules";
    s.textContent = JSON.stringify({
      prefetch: [{
        source: "document",
        where: { and: [{ href_matches: padrao }].concat(fora.map(function (f) { return { not: { href_matches: f } }; }),
          [{ not: { selector_matches: "[download], [target=_blank]" } }]) },
        eagerness: "moderate"
      }]
    });
    document.head.appendChild(s);
    return;
  }

  var feitos = {}, relogio = null;
  function vale(a) {
    if (!a || !a.href || a.hasAttribute("download") || a.target === "_blank") { return false; }
    var u;
    try { u = new URL(a.href, location.href); } catch (e) { return false; }
    if (u.origin !== location.origin || u.href === location.href) { return false; }
    var alvo = padrao.replace(/\*$/, "");
    return u.pathname.indexOf(alvo.replace(location.origin, "")) === 0 && !/[?&](formato|parcial)=|[?&]tv=1/.test(u.search);
  }
  document.addEventListener("pointerover", function (ev) {
    var a = ev.target.closest && ev.target.closest("a[href]");
    clearTimeout(relogio);
    if (!vale(a) || feitos[a.href]) { return; }
    relogio = setTimeout(function () {
      feitos[a.href] = 1;
      var l = document.createElement("link"); l.rel = "prefetch"; l.href = a.href; document.head.appendChild(l);
    }, 65);
  });
})();
