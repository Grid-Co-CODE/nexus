/* O filtro suspenso das telas da Usinas 360° (10/11/2026).
   Levi: "Quero que o visual dos filtros de todas as seções do usinas 360° tenha a estrutura de filtros usando como
   referência os filtros de histórico de OS, um filtro suspenso e simples". É o modelo do Histórico do OS Creator Web que
   as Rondas já usam desde 03/11/2026 (as mesmas classes rd-*): na barra ficam a visão, a busca e o botão Filtros (com
   quantos estão aplicados); as listas vão para o painel suspenso, que só vale no Aplicar (fechar sem aplicar descarta);
   embaixo, uma etiqueta por filtro aplicado, e o × tira só aquele.
   Como entra: o formulário da tela leva data-fs e este script o monta com as <select> que já estão nele (o rótulo é o da
   própria tela). Sem o script, a tela segue como era (cada lista filtra ao trocar). A lista com data-fs-fora fica na
   barra (o mês do Ranking). A lista sem `name` filtra na própria página (o cliente da Aprovação): vale na hora. */
(function () {
  "use strict";
  var n = 0;

  function rotuloDe(f, s) {
    var l = (s.id && f.querySelector('label[for="' + s.id + '"]')) || s.closest("label");
    var texto = "";
    if (l) {
      var r = l.querySelector(".gc-rotulo") || l;
      texto = Array.prototype.map.call(r.childNodes, function (c) { return c.nodeType === 3 ? c.textContent : (c.tagName === "SELECT" ? "" : c.textContent); }).join(" ");
    }
    texto = (texto || s.getAttribute("aria-label") || s.name || "Filtro").replace(/\s+/g, " ").trim();
    return { texto: texto, label: l };
  }
  function padraoDe(s) { return s.hasAttribute("data-padrao") ? s.getAttribute("data-padrao") : (s.options[0] ? s.options[0].value : ""); }
  function el(tag, classe, texto) {
    var e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto) e.textContent = texto;
    return e;
  }

  document.querySelectorAll("form[data-fs]:not([data-fs-ok])").forEach(function (f) {
    f.setAttribute("data-fs-ok", "1");
    var listas = Array.prototype.filter.call(f.querySelectorAll("select"), function (s) { return !s.hasAttribute("data-fs-fora"); });
    if (!listas.length) return;
    var id = "fs-painel-" + (++n);
    f.classList.add("fs-barra");

    // o botão Filtros no lugar da 1ª lista
    var abrir = el("button", "rd-btn");
    abrir.type = "button";
    abrir.setAttribute("aria-haspopup", "dialog");
    abrir.setAttribute("aria-expanded", "false");
    abrir.setAttribute("aria-controls", id);
    abrir.innerHTML = '<i class="ph ph-sliders-horizontal" aria-hidden="true"></i>Filtros';
    var badge = el("span", "rd-badge");
    badge.hidden = true;
    abrir.appendChild(badge);
    var primeiro = rotuloDe(f, listas[0]).label;
    var ancora = primeiro && !primeiro.contains(listas[0]) ? primeiro : (listas[0].closest("label") || listas[0]);
    ancora.parentNode.insertBefore(abrir, ancora);
    // a busca da barra no campo do modelo (Levi, 10/11/2026: "o campo buscar e as cores também tem que estar no mesmo
    // padrão"): a lupa, a mesma borda e o mesmo fundo do botão Filtros, e ANTES dele, como no Histórico de OS
    Array.prototype.forEach.call(f.querySelectorAll('input[type="search"]'), function (busca) {
      var rot = busca.id && f.querySelector('label[for="' + busca.id + '"]'), casca = busca.parentNode;
      var campo = el("label", "rd-campo rd-busca"), lupa = el("i", "ph ph-magnifying-glass");
      lupa.setAttribute("aria-hidden", "true");
      if (!busca.getAttribute("aria-label")) busca.setAttribute("aria-label", rot ? rot.textContent.trim() : "Buscar");
      if (rot && rot.parentNode) rot.parentNode.removeChild(rot);
      busca.classList.remove("gc-campo");
      abrir.parentNode.insertBefore(campo, abrir);
      campo.appendChild(lupa);
      campo.appendChild(busca);
      if (casca !== f && casca !== abrir.parentNode && casca.parentNode && !casca.children.length && !casca.textContent.trim()) casca.parentNode.removeChild(casca);
    });

    // o painel, com cada lista e o rótulo dela
    var veu = el("div", "rd-veu"), painel = el("div", "rd-painel");
    veu.hidden = painel.hidden = true;
    painel.id = id;
    painel.setAttribute("role", "dialog");
    painel.setAttribute("aria-label", "Filtros");
    var topo = el("div", "rd-painel-topo"), fechar = el("button", "rd-fechar", "×");
    topo.appendChild(el("h2", "", "Filtros"));
    fechar.type = "button";
    fechar.setAttribute("aria-label", "Fechar sem aplicar");
    fechar.title = "Fechar sem aplicar";
    topo.appendChild(fechar);
    var grade = el("div", "rd-grade"), campos = [];
    listas.forEach(function (s) {
      var r = rotuloDe(f, s), cel = el("label", "rd-cel");
      cel.appendChild(el("span", "gc-rotulo", r.texto));
      s.removeAttribute("onchange");
      s.onchange = null;
      var pai = s.parentNode;
      cel.appendChild(s);                                         // a lista sai da barra e entra no painel
      if (r.label && r.label.parentNode) r.label.parentNode.removeChild(r.label);
      // a casca que só tinha o rótulo e a lista (o par da Aprovação) não fica vazia na barra
      if (pai !== f && pai.parentNode && !pai.children.length && !pai.textContent.trim()) pai.parentNode.removeChild(pai);
      grade.appendChild(cel);
      campos.push({ s: s, rotulo: r.texto, padrao: padraoDe(s), aplicado: s.value, local: !s.name });
    });
    var rodape = el("div", "rd-rodape"), limpar = el("button", "gc-btn gc-btn--ui gc-btn--fantasma", "Limpar");
    var aplicar = el("button", "gc-btn gc-btn--primario", "Aplicar");
    limpar.type = aplicar.type = "button";
    rodape.appendChild(limpar);
    rodape.appendChild(aplicar);
    painel.appendChild(topo);
    painel.appendChild(grade);
    painel.appendChild(rodape);
    f.appendChild(veu);
    f.appendChild(painel);
    var etiquetas = el("div", "rd-etiquetas");
    etiquetas.setAttribute("role", "group");
    etiquetas.setAttribute("aria-label", "Filtros aplicados");
    f.parentNode.insertBefore(etiquetas, f.nextSibling);

    function enviar() { if (f.requestSubmit) f.requestSubmit(); else f.submit(); }
    function mudou(s) { s.dispatchEvent(new Event("change", { bubbles: true })); }
    function desenhar() {
      // o que está aplicado: o valor com que a página veio (a lista da própria página vale na hora)
      var ativos = campos.filter(function (c) { return (c.local ? c.s.value : c.aplicado) !== c.padrao; });
      badge.hidden = !ativos.length;
      badge.textContent = ativos.length;
      etiquetas.textContent = "";
      etiquetas.hidden = !ativos.length;
      ativos.forEach(function (c) {
        var bt = el("button", "rd-etiqueta");
        bt.type = "button";
        bt.title = "Tirar este filtro";
        var op = Array.prototype.filter.call(c.s.options, function (o) { return o.value === (c.local ? c.s.value : c.aplicado); })[0];
        bt.appendChild(document.createTextNode(c.rotulo + ": "));
        bt.appendChild(el("b", "", op ? op.textContent.trim() : ""));
        var x = el("span", "rd-x", "×");
        x.setAttribute("aria-hidden", "true");
        bt.appendChild(x);
        bt.addEventListener("click", function () {
          c.s.value = c.padrao;
          if (c.local) { mudou(c.s); desenhar(); } else enviar();
        });
        etiquetas.appendChild(bt);
      });
    }
    function fecha(descartar) {
      if (painel.hidden) return;
      if (descartar) campos.forEach(function (c) { if (!c.local) c.s.value = c.aplicado; });
      painel.hidden = veu.hidden = true;
      abrir.setAttribute("aria-expanded", "false");
    }
    abrir.addEventListener("click", function () {
      if (!painel.hidden) { fecha(true); return; }
      painel.hidden = veu.hidden = false;
      abrir.setAttribute("aria-expanded", "true");
      campos[0].s.focus();
    });
    fechar.addEventListener("click", function () { fecha(true); abrir.focus(); });
    veu.addEventListener("click", function () { fecha(true); });
    limpar.addEventListener("click", function () {
      campos.forEach(function (c) { if (c.s.value !== c.padrao) { c.s.value = c.padrao; if (c.local) mudou(c.s); } });
      desenhar();
    });
    aplicar.addEventListener("click", function () {
      if (campos.some(function (c) { return !c.local && c.s.value !== c.aplicado; })) { enviar(); return; }
      fecha(false);
      desenhar();
      abrir.focus();
    });
    campos.forEach(function (c) { if (c.local) c.s.addEventListener("change", desenhar); });
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape" && !painel.hidden) { fecha(true); abrir.focus(); } });
    document.addEventListener("click", function (ev) {
      if (!painel.hidden && !painel.contains(ev.target) && !abrir.contains(ev.target)) fecha(true);
    });
    desenhar();
  });
})();
