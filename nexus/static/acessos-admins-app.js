/* Base → Acessos, aba Administradores do App de Campo (05/11/2026): a busca da lista de pessoas é da própria página (não
   recarrega) e o Tirar pergunta antes. Sem JavaScript, a lista inteira aparece, a escolha é obrigatória pelo próprio
   formulário (o `required` do rádio) e o Tirar vai direto.
   Com JavaScript, quem confere a escolha é o envio (revisão de 05/11/2026, achado 7): com o `required` num rádio que a
   busca escondeu, o navegador barrava o envio calado (o aviso dele não aparece num campo que não se vê). O aviso vai à
   linha `aria-live` da contagem, e o foco volta à busca. */
(function () {
  function sem(s) {
    return String(s || "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().replace(/\s+/g, " ").trim();
  }
  var form = document.getElementById("aa-por");
  var busca = document.querySelector("[data-aa-busca]");
  var itens = Array.prototype.slice.call(document.querySelectorAll("[data-aa-texto]"));
  var nada = document.querySelector("[data-aa-nada]");
  var conta = document.querySelector("[data-aa-conta]");
  function radio(l) { return l.querySelector("input"); }
  itens.forEach(function (l) { var r = radio(l); if (r) r.removeAttribute("required"); });
  if (busca) {
    busca.addEventListener("input", function () {
      var q = sem(busca.value), n = 0;
      itens.forEach(function (l) {
        // a pessoa marcada fica à vista mesmo fora da busca: escondida, o formulário mandaria quem ninguém vê
        var mostra = !q || l.getAttribute("data-aa-texto").indexOf(q) >= 0 || radio(l).checked;
        l.hidden = !mostra;
        if (mostra) n++;
      });
      if (nada) nada.hidden = n > 0 || !itens.length;
      if (conta) conta.textContent = n + (n === 1 ? " ficha" : " fichas");
    });
  }
  document.addEventListener("submit", function (ev) {
    var f = ev.target;
    if (form && f === form && !itens.some(function (l) { var r = radio(l); return r && r.checked; })) {
      ev.preventDefault();
      if (conta) conta.textContent = "Escolha a pessoa na lista antes de pôr (a busca pode estar escondendo quem você procura).";
      if (busca) busca.focus();
      return;
    }
    var txt = f && f.getAttribute && f.getAttribute("data-confirmar");
    if (txt && !window.confirm(txt)) ev.preventDefault();
  });
})();
