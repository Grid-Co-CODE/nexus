/* Performance › Limitações de potência (19/11/2026): a conta da potência retida enquanto se preenche, e o "Todos os
   inversores" que apaga a escolha um a um. A regra que vale é a do servidor (nexus/campo/limitacoes.py); aqui é só a prévia
   (inversores × potência nominal × (100% − limite)). Sem JavaScript, o formulário funciona igual, sem a prévia. */
(function () {
  "use strict";
  var form = document.querySelector("[data-lp-form]");
  if (!form) return;
  var calc = form.querySelector("[data-lp-calc]"), todos = form.querySelector("[data-lp-todos]"),
      nom = form.querySelector("[data-lp-nominal]"), pct = form.querySelector("[data-lp-pct]"), inv = form.querySelector(".lp-inv");
  function num(el) { var s = String(el && el.value || "").trim().replace(/\s/g, ""); if (s.indexOf(",") >= 0) s = s.replace(/\./g, "").replace(",", "."); var n = parseFloat(s); return isNaN(n) ? null : n; }
  function br(n) { return n.toLocaleString("pt-BR", {maximumFractionDigits: 1}); }
  function quantos() { return todos && todos.checked ? +(todos.getAttribute("data-qtd") || 0) : form.querySelectorAll('input[name="inversores"]:checked').length; }
  function conta() {
    if (inv) { if (todos && todos.checked) inv.setAttribute("data-todos", ""); else inv.removeAttribute("data-todos"); }
    if (!calc) return;
    var q = quantos(), n = num(nom), p = num(pct);
    if (!q) { calc.textContent = "Marque os inversores (ou Todos) e diga a potência e o limite: a potência retida aparece aqui."; return; }
    if (p === null || p <= 0 || p >= 100) { calc.textContent = q + (q === 1 ? " inversor marcado." : " inversores marcados.") + " Diga o limite (o percentual liberado, entre 0 e 100)."; return; }
    if (n === null || n <= 0) { calc.innerHTML = q + (q === 1 ? " inversor" : " inversores") + " a " + br(p) + "%. <b>Sem a potência nominal, esta limitação não entra no expurgo.</b>"; return; }
    var kw = q * n * (100 - p) / 100;
    calc.innerHTML = "Potência retida: " + q + (q === 1 ? " inversor" : " inversores") + " × " + br(n) + " kW × " + br(100 - p) + "% = <b>" + br(kw) + " kW</b>";
  }
  form.addEventListener("input", conta);
  form.addEventListener("change", conta);
  conta();
})();
