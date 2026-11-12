/* Lista de sugestões do Nexus para um campo de texto (12/11/2026): no lugar do <datalist> do navegador.

   Levi, 12/11/2026, no campo "usina do cadastro" das Ligações: "Esses dados suspensos tá escroto demais, tem que estar
   alinhado com o campo!". É o mesmo comportamento do pcm-etiqueta.js (19/10/2026), em componente genérico: o campo traz
   data-lista="<id>" e a página traz um <script type="application/json" id="<id>"> com as opções (texto). A lista abre
   colada embaixo do campo, com a largura dele (ou mais, até o limite da tela), filtra sem acento e sem caixa, as que
   COMEÇAM com o texto primeiro, anda com as setas, escolhe com Enter ou clique, fecha com Esc ou clicando fora.
   É position:fixed e se reposiciona pelo campo ao abrir, ao rolar (qualquer rolagem, a da tabela .cad-rolagem inclusive:
   o overflow da tabela cortaria uma lista absoluta) e ao redimensionar. Vale qualquer texto digitado.
   `filtrar` é pura, para o teste no node. */
(function (raiz) {
  "use strict";

  function sem(s) {
    return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
  }
  function filtrar(lista, q) {
    var alvo = sem(q);
    if (!alvo) return lista.slice();
    var comeca = [], contem = [];
    lista.forEach(function (e) {
      var n = sem(e);
      if (n.indexOf(alvo) === 0) comeca.push(e); else if (n.indexOf(alvo) >= 0) contem.push(e);
    });
    return comeca.concat(contem);
  }
  raiz.ListaSugestoes = { filtrar: filtrar, sem: sem };
  if (typeof document === "undefined") return;

  var MENU_ID = "ls-menu";
  var menu = document.createElement("div");
  menu.className = "ls-menu";
  menu.id = MENU_ID;
  menu.setAttribute("role", "listbox");
  menu.hidden = true;
  document.body.appendChild(menu);
  var campo = null, itens = [], ativo = -1, cache = {};

  function opcoes(id) {
    if (!(id in cache)) {
      var no = document.getElementById(id), l = [];
      try { l = JSON.parse(no ? no.textContent : "[]") || []; } catch (e) { l = []; }
      cache[id] = l;
    }
    return cache[id];
  }
  function fechar() {
    menu.hidden = true;
    if (campo) { campo.setAttribute("aria-expanded", "false"); campo.removeAttribute("aria-activedescendant"); }
    campo = null; itens = []; ativo = -1;
  }
  function posicionar() {
    if (!campo) return;
    var r = campo.getBoundingClientRect(), vw = document.documentElement.clientWidth || window.innerWidth;
    var larg = Math.min(Math.max(r.width, 280), vw - 16);
    menu.style.width = larg + "px";
    menu.style.left = Math.max(8, Math.min(r.left, vw - larg - 8)) + "px";
    var embaixo = window.innerHeight - r.bottom, alto = Math.min(menu.scrollHeight, 280);
    menu.style.top = (embaixo >= alto + 12 || embaixo >= r.top ? r.bottom + 4 : r.top - alto - 4) + "px";
  }
  function marcar(i) {
    ativo = i;
    itens.forEach(function (b, j) { b.setAttribute("aria-selected", j === i ? "true" : "false"); });
    if (campo) {
      if (itens[i]) campo.setAttribute("aria-activedescendant", itens[i].id); else campo.removeAttribute("aria-activedescendant");
    }
    if (itens[i]) itens[i].scrollIntoView({ block: "nearest" });
  }
  function escolher(valor) {
    if (!campo) return;
    var c = campo;
    c.value = valor;
    fechar();
    c.dispatchEvent(new Event("input", { bubbles: true }));
    c.focus();
  }
  function desenhar() {
    var todas = opcoes(campo.getAttribute("data-lista")), achadas = filtrar(todas, campo.value).slice(0, 60);
    menu.innerHTML = "";
    itens = [];
    achadas.forEach(function (e, i) {
      var b = document.createElement("button");
      b.type = "button";
      b.id = MENU_ID + "-" + i;
      b.className = "ls-op";
      b.setAttribute("role", "option");
      b.textContent = e;
      b.addEventListener("mousedown", function (ev) { ev.preventDefault(); escolher(e); });
      menu.appendChild(b);
      itens.push(b);
    });
    if (!achadas.length) {
      var p = document.createElement("p");
      p.className = "ls-vazio";
      p.textContent = todas.length ? "Nada com esse nome na lista: vale o que você digitou." : "Digite o que procura.";
      menu.appendChild(p);
    }
    menu.hidden = false;
    campo.setAttribute("aria-expanded", "true");
    marcar(-1);
    posicionar();
  }
  function abrir(c) { campo = c; desenhar(); }

  document.querySelectorAll("input[data-lista]").forEach(function (c) {
    c.setAttribute("role", "combobox");
    c.setAttribute("aria-autocomplete", "list");
    c.setAttribute("aria-controls", MENU_ID);
    c.setAttribute("aria-expanded", "false");
    c.setAttribute("autocomplete", "off");
    c.addEventListener("focus", function () { abrir(c); });
    c.addEventListener("click", function () { if (campo !== c) abrir(c); });
    c.addEventListener("input", function () { if (campo === c) desenhar(); });
    c.addEventListener("blur", function () { setTimeout(function () { if (campo === c && document.activeElement !== c) fechar(); }, 120); });
    c.addEventListener("keydown", function (ev) {
      if (campo !== c) { if (ev.key === "ArrowDown") { abrir(c); ev.preventDefault(); } return; }
      if (ev.key === "ArrowDown") { ev.preventDefault(); marcar(Math.min(ativo + 1, itens.length - 1)); }
      else if (ev.key === "ArrowUp") { ev.preventDefault(); marcar(Math.max(ativo - 1, 0)); }
      else if (ev.key === "Enter" && ativo >= 0) { ev.preventDefault(); itens[ativo].dispatchEvent(new MouseEvent("mousedown")); }
      else if (ev.key === "Escape") { ev.preventDefault(); fechar(); }
    });
  });
  window.addEventListener("resize", posicionar);
  document.addEventListener("scroll", function () { if (campo) posicionar(); }, true);
})(typeof window !== "undefined" ? window : globalThis);
