/* Comando > Usinas (11/11/2026): a tabela ordena pelo cabeçalho (o clique alterna crescente e decrescente; "Agora" volta
   à ordem do servidor, a do estado mais grave), a busca da barra filtra as linhas na própria página enquanto se digita
   e as linhas visíveis alternam a cor (12/11/2026, Levi: "uma cor alterando entre as linhas"): a alternância é refeita
   a cada busca e a cada ordem, para a linha escondida não quebrar o zebrado. O cliente e o estado vão pelo painel de
   Filtros (campo-filtros.js, o modelo do Histórico de OS), que só vale no Aplicar. Vazio vai sempre para o fim. */
(function () {
  "use strict";
  var tabela = document.querySelector("[data-cmu-tabela]");
  if (!tabela) return;
  var corpo = tabela.tBodies[0];
  var vazio = corpo.querySelector("[data-cmu-vazio]");
  var conta = document.querySelector("[data-cmu-conta]");
  var busca = document.querySelector("[data-cmu-busca]");

  function linhas() { return Array.prototype.slice.call(corpo.querySelectorAll("tr[data-cmu-uid]")); }
  function sem(s) {
    return String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
  }
  function zebrar() {
    var n = 0;
    linhas().forEach(function (tr) {
      tr.classList.toggle("cmu-par", !tr.hidden && (n++ % 2 === 1));
    });
    if (conta) conta.textContent = n;
    if (vazio) vazio.hidden = n > 0;
  }
  function filtrar() {
    var q = busca ? sem(busca.value) : "";
    linhas().forEach(function (tr) { tr.hidden = !!q && (tr.getAttribute("data-busca") || "").indexOf(q) < 0; });
    zebrar();
  }
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
      var ls = linhas();
      ls.sort(function (a, c) {
        var x = valor(a, chave, num), y = valor(c, chave, num);
        if (x === y) return 0;
        if (x === null || x === "") return 1;
        if (y === null || y === "") return -1;
        var r = num ? x - y : x.localeCompare(y, "pt-BR");
        return sobe ? r : -r;
      });
      ls.forEach(function (tr) { corpo.insertBefore(tr, vazio); });
      zebrar();
    });
  });

  // a linha inteira abre o prontuário, como no mockup (11/11/2026, Levi: "quando clico na usina não acontece nada!": só
  // o nome era link). O clique em outro link ou botão da linha segue o dele; Ctrl, Shift ou o botão do meio abrem em outra
  // aba, como no link; quem seleciona texto não sai da página
  corpo.addEventListener("click", function (ev) {
    var tr = ev.target.closest("tr[data-cmu-uid]");
    if (!tr || ev.target.closest("a, button") || String(window.getSelection() || "")) return;
    var a = tr.querySelector("a.cmu-usina");
    if (!a) return;
    if (ev.ctrlKey || ev.metaKey || ev.shiftKey) window.open(a.href, "_blank");
    else location.href = a.href;
  });
  corpo.addEventListener("auxclick", function (ev) {
    var tr = ev.target.closest("tr[data-cmu-uid]");
    if (ev.button !== 1 || !tr || ev.target.closest("a, button")) return;
    var a = tr.querySelector("a.cmu-usina");
    if (a) window.open(a.href, "_blank");
  });

  if (busca) {
    var espera;
    busca.addEventListener("input", function () { clearTimeout(espera); espera = setTimeout(filtrar, 120); });
  }
  filtrar();
})();
