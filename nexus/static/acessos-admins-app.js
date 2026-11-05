/* Base → Acessos, aba Administradores do App de Campo (05/11/2026): a busca da lista de pessoas é da própria página (não
   recarrega) e o Tirar pergunta antes. Sem JavaScript, a lista inteira aparece, a escolha é obrigatória pelo próprio
   formulário e o Tirar vai direto. */
(function () {
  function sem(s) {
    return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
  }
  var busca = document.querySelector("[data-aa-busca]");
  if (busca) {
    var itens = Array.prototype.slice.call(document.querySelectorAll("[data-aa-texto]"));
    var nada = document.querySelector("[data-aa-nada]");
    var conta = document.querySelector("[data-aa-conta]");
    busca.addEventListener("input", function () {
      var q = sem(busca.value), n = 0;
      itens.forEach(function (l) {
        // a pessoa marcada fica à vista mesmo fora da busca: escondida, o formulário mandaria quem ninguém vê
        var mostra = !q || l.getAttribute("data-aa-texto").indexOf(q) >= 0 || l.querySelector("input").checked;
        l.hidden = !mostra;
        if (mostra) n++;
      });
      if (nada) nada.hidden = n > 0 || !itens.length;
      if (conta) conta.textContent = n + (n === 1 ? " ficha" : " fichas");
    });
  }
  document.addEventListener("submit", function (ev) {
    var f = ev.target, txt = f && f.getAttribute && f.getAttribute("data-confirmar");
    if (txt && !window.confirm(txt)) ev.preventDefault();
  });
})();
