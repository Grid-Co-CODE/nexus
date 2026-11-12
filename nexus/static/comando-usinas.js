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

  // ── a dica dos quadradinhos da faixa (12/11/2026, Levi: "ao passar o mouse nos pontos colorido diga a usina e o motivo
  // da cor"): na hora, sem a espera do title do navegador; o teclado (Tab) também mostra
  var dica = document.querySelector("[data-cmu-dica]");
  var faixa = document.querySelector("[data-cmu-faixa]");
  if (dica && faixa) {
    var mostra = function (seg) {
      dica.querySelector("b").textContent = seg.getAttribute("data-dica-usina");
      dica.querySelector("span").textContent = seg.getAttribute("data-dica-motivo");
      dica.hidden = false;
      var r = seg.getBoundingClientRect(), q = faixa.parentNode.getBoundingClientRect(), w = dica.offsetWidth;
      var x = Math.max(0, Math.min(r.left - q.left + r.width / 2 - w / 2, q.width - w));
      dica.style.left = x + "px";
      dica.style.top = (r.bottom - q.top + 8) + "px";
    };
    var esconde = function () { dica.hidden = true; };
    faixa.addEventListener("mouseover", function (e) { var s = e.target.closest(".cmu-seg"); if (s) mostra(s); });
    faixa.addEventListener("focusin", function (e) { var s = e.target.closest(".cmu-seg"); if (s) mostra(s); });
    faixa.addEventListener("mouseleave", esconde);
    faixa.addEventListener("focusout", esconde);
  }

  // ── os filtros no modelo do Histórico de OS (12/11/2026, Levi: "que nos filtros o cliente seja digitável tal qual é em
  // histórico de OS [...] no mesmo estilo e mesmas funções"): o botão Filtros abre o painel; cada lista é de marcar, com a
  // caixa de digitar no topo (sem acento e sem caixa); o campo que mudou ganha o ponto; o Aplicar só acende com mudança e
  // recarrega a página com os filtros; fechar (×, Esc, clique fora) descarta; Limpar desmarca tudo (ainda pede o
  // Aplicar). Embaixo, uma etiqueta por filtro aplicado: o × tira aquele filtro e aplica na hora; "Limpar tudo" tira todos
  var fl = document.querySelector("[data-cmu-fl]");
  if (!fl) return;
  var painel = fl.querySelector(".cmu-fl-painel"), abrir = fl.querySelector("[data-cmu-fl-abrir]");
  var aplicarB = fl.querySelector("[data-cmu-fl-aplicar]"), nalt = fl.querySelector("[data-cmu-fl-nalt]");
  var badge = fl.querySelector("[data-cmu-fl-badge]"), etiquetas = fl.querySelector("[data-cmu-fl-etiquetas]");
  var listas = Array.prototype.slice.call(fl.querySelectorAll(".cmu-fl-multi"));
  var aplicado = {};
  function caixas(d) { return Array.prototype.slice.call(d.querySelectorAll('input[type="checkbox"]')); }
  function marcados(d) { return caixas(d).filter(function (c) { return c.checked; }); }
  function rotuloDe(c) { return c.parentNode.textContent.trim(); }
  listas.forEach(function (d) { aplicado[d.dataset.nome] = marcados(d).map(function (c) { return c.value; }); });
  function igual(a, b) { return a.length === b.length && a.every(function (v) { return b.indexOf(v) >= 0; }); }
  function resumo(d) {
    var m = marcados(d), t = d.querySelector(".cmu-fl-txt");
    t.textContent = !m.length ? d.dataset.todos : (m.length === 1 ? rotuloDe(m[0]) : m.length + " selecionados");
    d.classList.toggle("cmu-fl-tem", m.length > 0);
    caixas(d).forEach(function (c) { c.parentNode.classList.toggle("on", c.checked); });
  }
  function conferir() {
    var n = 0;
    listas.forEach(function (d) {
      var mudou = !igual(marcados(d).map(function (c) { return c.value; }), aplicado[d.dataset.nome]);
      d.parentNode.classList.toggle("mudou", mudou);
      if (mudou) n++;
      resumo(d);
    });
    aplicarB.disabled = !n;
    nalt.textContent = n ? (n === 1 ? "1 alteração" : n + " alterações") : "Sem alterações";
  }
  function ir(valores) {
    var u = new URL(location.href);
    listas.forEach(function (d) { u.searchParams.delete(d.dataset.nome); });
    Object.keys(valores).forEach(function (k) { valores[k].forEach(function (v) { u.searchParams.append(k, v); }); });
    if (busca) { if (busca.value.trim()) u.searchParams.set("q", busca.value.trim()); else u.searchParams.delete("q"); }
    location.href = u.pathname + u.search;
  }
  function escolhidos() {
    var o = {};
    listas.forEach(function (d) { o[d.dataset.nome] = marcados(d).map(function (c) { return c.value; }); });
    return o;
  }
  function fechar(descartar) {
    if (painel.hidden) return;
    if (descartar) listas.forEach(function (d) {
      caixas(d).forEach(function (c) { c.checked = aplicado[d.dataset.nome].indexOf(c.value) >= 0; });
    });
    listas.forEach(function (d) { d.open = false; });
    painel.hidden = true;
    abrir.setAttribute("aria-expanded", "false");
    conferir();
  }
  abrir.addEventListener("click", function () {
    if (!painel.hidden) { fechar(true); return; }
    painel.hidden = false;
    abrir.setAttribute("aria-expanded", "true");
    conferir();
  });
  fl.querySelector("[data-cmu-fl-fechar]").addEventListener("click", function () { fechar(true); abrir.focus(); });
  fl.querySelector("[data-cmu-fl-limpar]").addEventListener("click", function () {
    listas.forEach(function (d) { caixas(d).forEach(function (c) { c.checked = false; }); });
    conferir();
  });
  aplicarB.addEventListener("click", function () { ir(escolhidos()); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !painel.hidden) { fechar(true); abrir.focus(); } });
  document.addEventListener("click", function (e) {
    if (!painel.hidden && !painel.contains(e.target) && !abrir.contains(e.target)) fechar(true);
  });
  listas.forEach(function (d) {
    // uma lista aberta por vez; a caixa de digitar ganha o foco ao abrir
    d.addEventListener("toggle", function () {
      if (!d.open) return;
      listas.forEach(function (o) { if (o !== d) o.open = false; });
      var p = d.querySelector(".cmu-fl-procura");
      if (p) { p.value = ""; procurar(d, ""); setTimeout(function () { p.focus(); }, 0); }
    });
    d.addEventListener("change", conferir);
    var p = d.querySelector(".cmu-fl-procura");
    if (p) p.addEventListener("input", function () { procurar(d, p.value); });
  });
  function procurar(d, txt) {
    var q = sem(txt), n = 0;
    caixas(d).forEach(function (c) {
      var ok = !q || sem(rotuloDe(c)).indexOf(q) >= 0;
      c.parentNode.hidden = !ok;
      if (ok) n++;
    });
    d.querySelector(".cmu-fl-vazio").hidden = n > 0;
  }
  // as etiquetas e o número do botão: o que está APLICADO (o que veio no endereço)
  var ativos = listas.filter(function (d) { return aplicado[d.dataset.nome].length; });
  badge.hidden = !ativos.length;
  badge.textContent = ativos.length;
  etiquetas.hidden = !ativos.length;
  ativos.forEach(function (d) {
    var nomes = caixas(d).filter(function (c) { return aplicado[d.dataset.nome].indexOf(c.value) >= 0; }).map(rotuloDe);
    var chip = document.createElement("span");
    chip.className = "cmu-fl-chip";
    var rot = document.createElement("i");
    rot.textContent = d.dataset.rotulo + ":";
    var val = document.createElement("span");
    val.className = "cmu-fl-chip-v";
    val.textContent = nomes.join(", ");
    val.title = nomes.join(", ");
    var x = document.createElement("button");
    x.type = "button";
    x.className = "cmu-fl-chip-x";
    x.setAttribute("aria-label", "Tirar o filtro " + d.dataset.rotulo);
    x.title = "Tirar este filtro";
    x.textContent = "×";
    x.addEventListener("click", function () {
      var v = {};
      listas.forEach(function (o) { v[o.dataset.nome] = o === d ? [] : aplicado[o.dataset.nome]; });
      ir(v);
    });
    chip.appendChild(rot);
    chip.appendChild(val);
    chip.appendChild(x);
    etiquetas.appendChild(chip);
  });
  if (ativos.length) {
    var tudo = document.createElement("button");
    tudo.type = "button";
    tudo.className = "cmu-fl-link";
    tudo.textContent = "Limpar tudo";
    tudo.addEventListener("click", function () { ir({}); });
    etiquetas.appendChild(tudo);
  }
  conferir();
})();
