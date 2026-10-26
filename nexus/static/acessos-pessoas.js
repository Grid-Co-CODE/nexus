/* Base → Acessos, aba Pessoas e setores (25/10/2026; era a tela Integração Fracttal). O setor de UMA pessoa grava na
   hora, sem recarregar (a lista tem ~180 e recarregar perdia a rolagem); o resultado vai no aviso do canto e na borda do
   campo (um texto na linha mudava a largura da coluna). As marcadas vão pelo formulário da barra, que só aparece com
   alguém marcado. A busca e os filtros são do filtro-local.js (sem ir ao servidor).

   O campo Setor de cada linha chega só com o setor dela; a lista inteira (o <template id="fr-opcoes">) entra quando a
   pessoa toca nele: com a lista em cada linha a página passava de 300 KB. Depois de gravar, a linha passa a ser do setor
   novo também para os filtros (data-f-setor e a busca). */
(function () {
  "use strict";
  var lote = document.getElementById("fr-lote");
  var conta = document.getElementById("fr-lote-n");
  var todas = document.getElementById("fr-todas");
  var toast = document.getElementById("fr-toast"), relogio = null;
  var modelo = document.getElementById("fr-opcoes");
  if (!lote) return;

  function sem(s) {
    return String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
  }
  function avisar(texto, ok) {
    toast.textContent = texto;
    toast.className = "fr-toast fr-toast--" + (ok ? "ok" : "erro");
    toast.hidden = false;
    clearTimeout(relogio);
    relogio = setTimeout(function () { toast.hidden = true; }, ok ? 4000 : 9000);
  }
  // só as linhas à vista: marcar todas com um filtro marca as do filtro
  function caixas() {
    return Array.prototype.slice.call(document.querySelectorAll(".fr-marcar:not(:disabled)"))
      .filter(function (c) { return !c.closest("tr").hidden; });
  }
  function atualizar() {
    var cx = caixas(), n = cx.filter(function (c) { return c.checked; }).length;
    conta.textContent = n;
    lote.hidden = n === 0;
    if (todas) { todas.checked = n > 0 && n === cx.length; todas.indeterminate = n > 0 && n < cx.length; }
  }
  function encher(sel) {
    if (!modelo || sel.hasAttribute("data-cheio")) return;
    var atual = sel.value, rotulo = sel.selectedOptions[0] ? sel.selectedOptions[0].textContent : "";
    sel.innerHTML = "";
    sel.appendChild(modelo.content.cloneNode(true));
    if (atual && !Array.prototype.some.call(sel.options, function (o) { return o.value === atual; })) {
      var o = document.createElement("option");
      o.value = atual; o.textContent = rotulo;
      sel.appendChild(o);                       // o setor fora da lista fica, com o nome que tinha
    }
    sel.value = atual;
    sel.setAttribute("data-cheio", "1");
  }
  function linhaDoSetor(sel) {
    var tr = sel.closest("tr"), o = sel.selectedOptions[0];
    if (!tr) return;
    tr.setAttribute("data-f-setor", sel.value || "sem");
    tr.setAttribute("data-f-busca", sem((tr.getAttribute("data-busca-base") || "") + " " + (sel.value && o ? o.textContent : "")));
    if (window.FiltroLocal && window.FiltroLocal["fr-filtros"]) window.FiltroLocal["fr-filtros"].aplicar();
  }
  function salvar(sel) {
    var form = sel.form, antes = sel.getAttribute("data-antes") || "";
    var dados = new FormData(form);          /* antes de desabilitar: select desabilitado não vai no FormData */
    sel.disabled = true;
    sel.classList.remove("fr-sel--ok", "fr-sel--erro");
    function erro(texto) {
      sel.disabled = false; sel.value = antes;
      sel.classList.add("fr-sel--erro"); sel.title = texto;
      avisar(texto, false);
    }
    fetch(form.action, {method: "POST", body: dados, headers: {"Accept": "application/json"}, credentials: "same-origin"})
      .then(function (r) { return r.json().catch(function () { return {ok: false, erro: "Resposta inesperada (" + r.status + "): não gravou."}; }); })
      .then(function (j) {
        if (!j.ok) { erro(j.erro || "Não gravou."); return; }
        sel.disabled = false; sel.setAttribute("data-antes", sel.value);
        sel.classList.add("fr-sel--ok"); sel.removeAttribute("title");
        linhaDoSetor(sel);
        avisar(j.aviso || "Salvo.", true);
      })
      .catch(function () { erro("Sem conexão: não gravou."); });
  }
  document.querySelectorAll(".fr-setor-sel").forEach(function (s) { s.setAttribute("data-antes", s.value); });
  ["pointerdown", "mousedown", "focusin", "touchstart"].forEach(function (ev) {
    document.addEventListener(ev, function (e) {
      var s = e.target.closest && e.target.closest(".fr-setor-sel");
      if (s) encher(s);
    }, true);
  });
  document.addEventListener("change", function (e) {
    var t = e.target;
    if (t === todas) { caixas().forEach(function (c) { c.checked = todas.checked; }); atualizar(); return; }
    if (t.classList.contains("fr-marcar")) { atualizar(); return; }
    if (t.classList.contains("fr-setor-sel")) { salvar(t); }
  });
  // o filtro mudou: a marcada que sumiu da vista desmarca (aplicar às marcadas é sobre o que se vê)
  document.addEventListener("filtro-local", function () {
    document.querySelectorAll(".fr-marcar:checked").forEach(function (c) { if (c.closest("tr").hidden) c.checked = false; });
    atualizar();
  });
  // gravar pelo formulário (as marcadas, a lista de setores) volta com os filtros de agora, e não os da abertura
  document.addEventListener("submit", function (e) {
    var v = e.target.querySelector && e.target.querySelector('input[name="volta"]');
    if (v) v.value = location.search.replace(/^\?/, "");
  });
  document.getElementById("fr-lote-limpar").addEventListener("click", function () {
    caixas().forEach(function (c) { c.checked = false; }); atualizar();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && document.activeElement && document.activeElement.classList.contains("fr-dica-botao")) {
      document.activeElement.blur();
    }
  });
  atualizar();
})();
