/* Comando > Usinas (11/11/2026): a tabela ordena pelo cabeçalho (o clique alterna crescente e decrescente; "Agora" volta
   à ordem do servidor, a do estado mais grave) e a faixa do alto acompanha os filtros da página (filtro-local.js): a
   barra da usina escondida some junto. Vazio vai sempre para o fim. */
(function () {
  "use strict";
  var tabela = document.querySelector("[data-cmu-tabela]");
  if (!tabela) return;
  var corpo = tabela.tBodies[0];
  var vazio = corpo.querySelector("[data-fl-vazio]");

  function valor(tr, chave, num) {
    var v = tr.getAttribute("data-o-" + chave) || "";
    if (!num) return v.toLowerCase();
    return v === "" ? null : parseFloat(v);
  }

  tabela.querySelectorAll("[data-cmu-ordem]").forEach(function (b) {
    b.addEventListener("click", function () {
      var chave = b.getAttribute("data-cmu-ordem"), num = b.hasAttribute("data-cmu-num");
      var sobe = b.getAttribute("aria-sort") !== "ascending";
      tabela.querySelectorAll("[data-cmu-ordem]").forEach(function (o) { o.removeAttribute("aria-sort"); });
      b.setAttribute("aria-sort", sobe ? "ascending" : "descending");
      var linhas = Array.prototype.slice.call(corpo.querySelectorAll("tr[data-fl-linha]"));
      linhas.sort(function (a, c) {
        var x = valor(a, chave, num), y = valor(c, chave, num);
        if (x === y) return 0;
        if (x === null || x === "") return 1;
        if (y === null || y === "") return -1;
        var r = num ? x - y : x.localeCompare(y, "pt-BR");
        return sobe ? r : -r;
      });
      linhas.forEach(function (tr) { corpo.insertBefore(tr, vazio); });
    });
  });

  // a linha inteira abre o prontuário, como no mockup (11/11/2026, Levi: "quando clico na usina não acontece nada!": só
  // o nome era link). O clique em outro link ou botão da linha segue o dele; Ctrl, Shift ou o botão do meio abrem em outra
  // aba, como no link; quem seleciona texto não sai da página
  corpo.addEventListener("click", function (ev) {
    var tr = ev.target.closest("tr[data-fl-linha]");
    if (!tr || ev.target.closest("a, button") || String(window.getSelection() || "")) return;
    var a = tr.querySelector("a.cmu-usina");
    if (!a) return;
    if (ev.ctrlKey || ev.metaKey || ev.shiftKey) window.open(a.href, "_blank");
    else location.href = a.href;
  });
  corpo.addEventListener("auxclick", function (ev) {
    var tr = ev.target.closest("tr[data-fl-linha]");
    if (ev.button !== 1 || !tr || ev.target.closest("a, button")) return;
    var a = tr.querySelector("a.cmu-usina");
    if (a) window.open(a.href, "_blank");
  });

  document.addEventListener("filtro-local", function () {
    corpo.querySelectorAll("tr[data-cmu-uid]").forEach(function (tr) {
      var s = document.querySelector('[data-cmu-seg="' + tr.getAttribute("data-cmu-uid") + '"]');
      if (s) s.hidden = tr.hidden;
    });
  });
})();
