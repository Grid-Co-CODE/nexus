/* Usinas 360° › Guia do App de Campo (21/11/2026): a busca sem acento, os temas e o tema dos telefones.
   - Busca: no título, no resumo, nas regras e nos casos (o `data-busca` de cada pergunta já vem sem acento do servidor,
     nexus/campo/guia_app.sem_acento; aqui a mesma conta para o que se digita).
   - Temas: o chip escolhe um tema (Todos = nenhum); a lista ao lado esconde o que não passa.
   - Tema dos telefones: cada iframe nasce com ?tema= do Nexus; quando o tema do Nexus troca (o data-tema do <html>, que
     muda sem recarregar), e quando um telefone termina de carregar (o carregamento é preguiçoso), manda
     postMessage({tipo: 'tema', tema}), o contrato das telas do App. */
(function () {
  "use strict";
  var raiz = document.documentElement;
  var fones = Array.prototype.slice.call(document.querySelectorAll("iframe[data-guia-fone]"));
  function tema() { return raiz.getAttribute("data-tema") === "claro" ? "claro" : "escuro"; }
  function avisar(f) { try { f.contentWindow && f.contentWindow.postMessage({ tipo: "tema", tema: tema() }, location.origin); } catch (e) { /* telefone ainda sem janela */ } }
  fones.forEach(function (f) { f.addEventListener("load", function () { avisar(f); }); });
  // os prints do App em PNG (27/11/2026): a imagem do tema da vez (data-escuro / data-claro)
  var prints = Array.prototype.slice.call(document.querySelectorAll("img[data-guia-print]"));
  function trocarPrints() { prints.forEach(function (im) { var s = im.getAttribute("data-" + tema()); if (s && im.getAttribute("src") !== s) im.setAttribute("src", s); }); }
  new MutationObserver(function () { fones.forEach(avisar); trocarPrints(); }).observe(raiz, { attributes: true, attributeFilter: ["data-tema"] });

  var campo = document.querySelector("[data-guia-busca]");
  if (!campo) return;
  var perguntas = Array.prototype.slice.call(document.querySelectorAll(".gu-pergunta[data-busca]"));
  var chips = Array.prototype.slice.call(document.querySelectorAll("[data-guia-tema]"));
  var conta = document.querySelector("[data-guia-conta]"), nada = document.querySelector("[data-guia-nada]");
  var escolhido = "";
  function semAcento(t) { return String(t || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim(); }
  function filtrar() {
    var termos = semAcento(campo.value).split(" ").filter(Boolean), n = 0, vistos = {};
    perguntas.forEach(function (p) {
      var texto = p.getAttribute("data-busca");
      var ok = (!escolhido || p.getAttribute("data-guia-de") === escolhido) &&
               termos.every(function (t) { return texto.indexOf(t) >= 0; });
      p.hidden = !ok;
      if (ok) { n++; vistos[p.id.slice(2)] = true; }
    });
    document.querySelectorAll("[data-guia-item]").forEach(function (li) { li.hidden = !vistos[li.getAttribute("data-guia-item")]; });
    document.querySelectorAll("[data-guia-grupo]").forEach(function (g) { g.hidden = !g.querySelector("[data-guia-item]:not([hidden])"); });
    if (conta) conta.textContent = n;
    if (nada) nada.hidden = n > 0;
    chips.forEach(function (c) { c.setAttribute("aria-pressed", c.getAttribute("data-guia-tema") === escolhido ? "true" : "false"); });
  }
  campo.addEventListener("input", filtrar);
  chips.forEach(function (c) { c.addEventListener("click", function () { escolhido = c.getAttribute("data-guia-tema"); filtrar(); }); });
})();
