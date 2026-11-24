/* Base › E-mails automáticos (24/11/2026): a lista de destinatários da regra e as travas do formulário.

   A pessoa entra pelo nome (a lista de sugestões traz "Nome · e-mail", do cadastro e do Fracttal) ou pelo e-mail de uma
   caixa, como a do COS. Cada um vira uma linha com um campo escondido `dest`; o servidor confere tudo de novo
   (`emails_controle.conferir_destinatarios`). O que o navegador segura antes, para a pessoa não perder o motivo
   digitado: o teste sem lista (no App, teste sem lista manda para todos) e o desligar dos e-mails críticos sem a
   confirmação. `emailDoTexto` é pura, para o teste no node. */
(function (raiz) {
  "use strict";

  var EMAIL = /^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/;

  function emailDoTexto(txt) {
    var s = String(txt || "").trim().toLowerCase();
    var i = s.lastIndexOf(" · ");
    if (i >= 0) s = s.slice(i + 3).trim();
    return EMAIL.test(s) ? s : "";
  }
  raiz.BaseEmails = { emailDoTexto: emailDoTexto };
  if (typeof document === "undefined") return;

  var form = document.querySelector("[data-em-form]");
  if (!form) return;
  var lista = form.querySelector("[data-em-dest]");
  var novo = form.querySelector("[data-em-novo]");
  var erroDest = form.querySelector("[data-em-erro-dest]");
  var critico = form.querySelector("[data-em-critico]");
  var nomes = {};
  try {
    JSON.parse((document.getElementById("em-pessoas") || {}).textContent || "[]").forEach(function (o) {
      var e = emailDoTexto(o);
      if (e) nomes[e] = String(o).slice(0, String(o).lastIndexOf(" · "));
    });
  } catch (e) { /* sem a lista, entra só o e-mail */ }

  function emails() {
    return Array.prototype.map.call(lista.querySelectorAll("input[name=dest]"), function (i) { return i.value; });
  }
  function avisar(txt) {
    erroDest.textContent = txt || "";
    erroDest.hidden = !txt;
  }
  function incluir() {
    var e = emailDoTexto(novo.value);
    if (!e) { avisar("Escolha uma pessoa da lista ou digite um e-mail inteiro."); return; }
    if (emails().indexOf(e) >= 0) { avisar("Já está na lista."); return; }
    var li = document.createElement("li");
    var campo = document.createElement("input");
    campo.type = "hidden"; campo.name = "dest"; campo.value = e;
    var rot = document.createElement("span");
    rot.textContent = nomes[e] || e;
    if (nomes[e]) { var sm = document.createElement("small"); sm.textContent = e; rot.appendChild(sm); }
    var b = document.createElement("button");
    b.type = "button"; b.className = "gc-btn gc-btn--fantasma"; b.setAttribute("data-em-tirar", "");
    b.setAttribute("aria-label", "Tirar " + (nomes[e] || e)); b.textContent = "Tirar";
    li.appendChild(campo); li.appendChild(rot); li.appendChild(b);
    lista.appendChild(li);
    novo.value = ""; avisar(""); atualizar();
  }
  function valor(nome) {
    var m = form.querySelector("input[name=" + nome + "]:checked");
    return m ? m.value : "";
  }
  function atualizar() {
    if (critico) critico.hidden = valor("ligado") !== "nao";
  }

  form.querySelector("[data-em-incluir]").addEventListener("click", incluir);
  novo.addEventListener("keydown", function (ev) {
    // o Enter da lista de sugestões escolhe a opção; com a lista fechada, inclui (e não envia o formulário)
    if (ev.key === "Enter") { ev.preventDefault(); if (!document.querySelector(".ls-menu:not([hidden])")) incluir(); }
  });
  lista.addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-em-tirar]");
    if (b) { b.closest("li").remove(); atualizar(); }
  });
  form.addEventListener("change", atualizar);
  form.addEventListener("submit", function (ev) {
    var padrao = ev.submitter && ev.submitter.hasAttribute("data-em-padrao");
    if (padrao) return;
    if (valor("ligado") === "sim" && valor("modo") === "teste" && !emails().length) {
      ev.preventDefault();
      avisar("O modo teste precisa de ao menos um destinatário: sem lista o App manda para todos.");
      novo.focus();
      return;
    }
    if (critico && valor("ligado") === "nao" && !critico.querySelector("input").checked) {
      ev.preventDefault();
      critico.hidden = false;
      critico.querySelector("input").focus();
    }
  });
  atualizar();
})(typeof window !== "undefined" ? window : globalThis);
