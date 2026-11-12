// O miolo de cada insight vem quando a pessoa abre a linha (03/11/2026). Com 327 insights, a página com todos os miolos
// dava 2 MB, 1.310 formulários e 12.544 campos, e o navegador travava (Levi: "cliquei em nexus insights e travou tudo").
// A linha fechada já vem na página; abrir pede /t/comando/insights/corpo uma vez e põe o miolo no lugar. O endereço com
// #ins-... (o sino, a volta de um Assumir ou de uma mensagem) abre o insight dele. Sem JavaScript, o link "Abrir este
// insight" recarrega a página com ele aberto.
(function () {
  "use strict";

  function carregar(caixa) {
    if (!caixa || caixa.hasAttribute("data-pedido")) return Promise.resolve();
    caixa.setAttribute("data-pedido", "");
    return fetch(caixa.getAttribute("data-corpo"), { credentials: "same-origin", headers: { Accept: "text/html" } })
      .then(function (r) { return r.text().then(function (t) { return { ok: r.ok, t: t }; }); })
      .then(function (r) {
        caixa.innerHTML = r.t;
        if (r.ok) { caixa.removeAttribute("data-corpo"); if (window.nexusConversa) window.nexusConversa(caixa); }
        else caixa.removeAttribute("data-pedido");
      })
      .catch(function () {
        caixa.removeAttribute("data-pedido");
        caixa.innerHTML = '<p class="mudo ins-nota">Não consegui abrir este insight agora (a rede caiu?). Feche e abra de novo.</p>';
      });
  }

  Array.prototype.forEach.call(document.querySelectorAll("details.ins-dobra"), function (d) {
    d.addEventListener("toggle", function () { if (d.open) carregar(d.querySelector(".ins-corpo[data-corpo]")); });
  });

  // o insight do endereço: #ins-R07-1, ou #conv-insight-R07-1 (a conversa dentro dele)
  var h = decodeURIComponent((location.hash || "").slice(1));
  var id = h.indexOf("conv-insight-") === 0 ? "ins-" + h.slice(13) : (h.indexOf("ins-") === 0 ? h : "");
  var li = id && document.getElementById(id);
  // o Sem dono vem recolhido (12/11/2026): o número do alto (#cx-sem-dono) e o endereço de um insight dele o abrem
  function abrirRecolhido(el) { var r = el && el.closest && el.closest("details.cx-recolhe"); if (r && !r.open) r.open = true; }
  if (h === "cx-sem-dono") abrirRecolhido(document.getElementById(h));
  window.addEventListener("hashchange", function () {
    if (location.hash === "#cx-sem-dono") abrirRecolhido(document.getElementById("cx-sem-dono"));
  });
  if (li) {
    abrirRecolhido(li);
    var d = li.querySelector("details.ins-dobra");
    if (d && !d.open) d.open = true;
    carregar(li.querySelector(".ins-corpo[data-corpo]")).then(function () {
      var alvo = document.getElementById(h) || li;
      alvo.scrollIntoView({ block: "start" });
    });
  }

  // a conta dos insights correndo (o Nexus acabou de subir): a página se atualiza sozinha
  var rec = document.querySelector("[data-recarregar]");
  if (rec) setTimeout(function () { location.reload(); }, 1000 * (parseInt(rec.getAttribute("data-recarregar"), 10) || 10));
})();
