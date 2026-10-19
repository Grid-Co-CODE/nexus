/* A etiqueta do Fracttal no Cadastro de motivos (19/10/2026): a lista de sugestões no estilo do Nexus.

   O <datalist> do navegador abria a lista dele, fora do estilo e torta ("Esse campo de etiquetas tá bugadasso, mal
   formatado (não está no estilo Nexus) e tá todo torto", Levi, 19/10/2026). Aqui a lista é do Nexus: abre embaixo do
   campo, filtra sem acento e sem caixa enquanto se digita, anda com as setas, escolhe com Enter ou clique, fecha com
   Esc ou clicando fora. "Sem etiqueta" limpa o campo. Vale qualquer nome digitado (o App casa sem acento e sem caixa).
   As etiquetas vêm da página (#etq-lista: as que já estão nas OS). `filtrar` é pura, para o teste no node. */
(function (raiz) {
  "use strict";

  function sem(s) {
    return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
  }
  // as que contêm o que foi digitado, as que COMEÇAM com ele primeiro; sem texto, todas na ordem da página
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
  raiz.EtiquetaSugestao = { filtrar: filtrar, sem: sem };
  if (typeof document === "undefined") return;

  var dados = document.getElementById("etq-lista");
  var LISTA = [];
  try { LISTA = JSON.parse(dados ? dados.textContent : "[]") || []; } catch (e) { LISTA = []; }
  var menu = document.createElement("div");
  menu.className = "fp-etq-menu";
  menu.id = "fp-etq-menu";
  menu.setAttribute("role", "listbox");
  menu.hidden = true;
  document.body.appendChild(menu);
  var campo = null, itens = [], ativo = -1;

  function fechar() {
    menu.hidden = true;
    if (campo) campo.setAttribute("aria-expanded", "false");
    campo = null; itens = []; ativo = -1;
  }
  function posicionar() {
    if (!campo) return;
    var r = campo.getBoundingClientRect(), larg = Math.max(r.width, 240);
    larg = Math.min(larg, window.innerWidth - 32);
    menu.style.width = larg + "px";
    menu.style.left = Math.max(16, Math.min(r.left, window.innerWidth - larg - 16)) + "px";
    var embaixo = window.innerHeight - r.bottom, alto = Math.min(menu.scrollHeight, 280);
    menu.style.top = (embaixo >= alto + 12 || embaixo >= r.top ? r.bottom + 4 : r.top - alto - 4) + "px";
  }
  function marcar(i) {
    ativo = i;
    itens.forEach(function (b, j) { b.setAttribute("aria-selected", j === i ? "true" : "false"); });
    if (itens[i]) itens[i].scrollIntoView({ block: "nearest" });
  }
  function escolher(valor) {
    if (!campo) return;
    var c = campo;
    c.value = valor;
    fechar();
    c.dispatchEvent(new Event("input", { bubbles: true }));     // a linha mostra o Salvar
    c.focus();
  }
  function desenhar() {
    var achadas = filtrar(LISTA, campo.value).slice(0, 60);
    menu.innerHTML = "";
    itens = [];
    function op(rotulo, valor, cls) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "fp-etq-op" + (cls ? " " + cls : "");
      b.setAttribute("role", "option");
      b.textContent = rotulo;
      b.addEventListener("mousedown", function (ev) { ev.preventDefault(); escolher(valor); });
      menu.appendChild(b);
      itens.push(b);
    }
    if (campo.value.trim()) op("Sem etiqueta", "", "fp-etq-op--nenhuma");
    achadas.forEach(function (e) { op(e, e); });
    if (!achadas.length) {
      var p = document.createElement("p");
      p.className = "fp-etq-vazio";
      p.textContent = LISTA.length ? "Nenhuma etiqueta das OS com esse nome: vale o que você digitou."
                                   : "Digite o nome da etiqueta como está no Fracttal.";
      menu.appendChild(p);
    }
    menu.hidden = false;
    campo.setAttribute("aria-expanded", "true");
    marcar(-1);
    posicionar();
  }
  function abrir(c) {
    campo = c;
    desenhar();
  }

  document.querySelectorAll("input[data-etq]").forEach(function (c) {
    c.setAttribute("role", "combobox");
    c.setAttribute("aria-autocomplete", "list");
    c.setAttribute("aria-controls", "fp-etq-menu");
    c.setAttribute("aria-expanded", "false");
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
