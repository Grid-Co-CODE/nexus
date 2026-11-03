// A @menção na conversa (Fase 2 dos setores conversando, 03/11/2026). Digitar @ abre a lista de pessoas (com setor) e
// de áreas; escolher põe "@Nome" no texto e a menção no formulário (a pessoa vai pelo código, nunca pelo nome). A lista
// só é pedida ao servidor no primeiro @ (o pessoal do Fracttal fica 1 h na memória de lá), nunca ao abrir a página.
// Menção cujo "@Nome" saiu do texto não vai. Sem JavaScript, as áreas se marcam na caixa "Mencionar áreas".
(function () {
  "use strict";
  var lista = null, pedindo = null;

  function semAcento(s) { return (s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); }

  function carregar(url) {
    if (lista) return Promise.resolve(lista);
    if (pedindo) return pedindo;
    pedindo = fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } })
      .then(function (r) { return r.ok ? r.json() : { pessoas: [], areas: [] }; })
      .then(function (d) {
        lista = (d.areas || []).map(function (a) { return { tipo: "area", id: a.id, nome: a.nome, sub: "Área: todo o setor que a vê" }; })
          .concat((d.pessoas || []).map(function (p) { return { tipo: "pessoa", id: p.hmac, nome: p.nome, sub: p.setor }; }));
        return lista;
      })
      .catch(function () { pedindo = null; return []; });
    return pedindo;
  }

  function montar(form) {
    if (form.hasAttribute("data-montado")) return;
    form.setAttribute("data-montado", "");
    var tx = form.querySelector("textarea[name=texto]");
    var caixa = form.querySelector(".conv-sugestoes");
    var escolhidas = form.querySelector(".conv-escolhidas");
    var marcadas = {};            // "tipo:id" -> {tipo, id, nome}
    var ativo = -1, achados = [];

    function termo() {
      var ate = tx.value.slice(0, tx.selectionStart);
      var m = ate.match(/(^|\s)@([^\s@]{0,30}(?: [^\s@]{0,30})?)$/);
      return m ? { texto: m[2], inicio: ate.length - m[2].length - 1 } : null;
    }

    function fechar() { caixa.hidden = true; caixa.innerHTML = ""; ativo = -1; achados = []; }

    function desenharEscolhidas() {
      escolhidas.innerHTML = "";
      Object.keys(marcadas).forEach(function (k) {
        var x = marcadas[k];
        var s = document.createElement("span");
        s.className = "conv-mencao" + (x.tipo === "area" ? " conv-mencao--area" : "");
        s.textContent = "@" + x.nome;
        escolhidas.appendChild(s);
      });
    }

    function escolher(x) {
      var t = termo();
      if (!t) return fechar();
      var antes = tx.value.slice(0, t.inicio), depois = tx.value.slice(tx.selectionStart);
      tx.value = antes + "@" + x.nome + " " + depois;
      var pos = (antes + "@" + x.nome + " ").length;
      tx.setSelectionRange(pos, pos);
      marcadas[x.tipo + ":" + x.id] = x;
      desenharEscolhidas();
      fechar();
      tx.focus();
    }

    function desenhar() {
      caixa.innerHTML = "";
      achados.forEach(function (x, i) {
        var li = document.createElement("li");
        li.setAttribute("role", "option");
        li.className = "conv-sug" + (i === ativo ? " conv-sug--ativa" : "");
        var b = document.createElement("b"); b.textContent = x.nome;
        var s = document.createElement("span"); s.textContent = x.sub || "";
        li.appendChild(b); li.appendChild(s);
        li.addEventListener("mousedown", function (ev) { ev.preventDefault(); escolher(x); });
        caixa.appendChild(li);
      });
      caixa.hidden = !achados.length;
    }

    tx.addEventListener("input", function () {
      var t = termo();
      if (!t) return fechar();
      carregar(form.getAttribute("data-conversa")).then(function (l) {
        var q = semAcento(t.texto);
        achados = l.filter(function (x) { return !q || semAcento(x.nome).indexOf(q) !== -1; }).slice(0, 8);
        ativo = achados.length ? 0 : -1;
        desenhar();
      });
    });
    tx.addEventListener("keydown", function (ev) {
      if (caixa.hidden) return;
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        ativo = (ativo + (ev.key === "ArrowDown" ? 1 : -1) + achados.length) % achados.length;
        desenhar();
      } else if (ev.key === "Enter" || ev.key === "Tab") {
        if (ativo >= 0) { ev.preventDefault(); escolher(achados[ativo]); }
      } else if (ev.key === "Escape") { fechar(); }
    });
    tx.addEventListener("blur", function () { setTimeout(fechar, 150); });

    form.addEventListener("submit", function () {
      Array.prototype.forEach.call(form.querySelectorAll("input[data-mencao]"), function (i) { i.remove(); });
      Object.keys(marcadas).forEach(function (k) {
        var x = marcadas[k];
        if (tx.value.indexOf("@" + x.nome) === -1) return;   // o @Nome saiu do texto: a menção não vai
        if (x.tipo === "area") {
          var chk = form.querySelector("input[name=area][value='" + x.id + "']");
          if (chk) { chk.checked = true; return; }
        }
        var h = document.createElement("input");
        h.type = "hidden"; h.name = x.tipo === "area" ? "area" : "pessoa"; h.value = x.id; h.setAttribute("data-mencao", "");
        form.appendChild(h);
      });
    });
  }

  // a conversa que chega depois, no miolo do insight aberto (comando/insights.js), monta por aqui
  window.nexusConversa = function (raiz) {
    Array.prototype.forEach.call((raiz || document).querySelectorAll("form[data-conversa]"), montar);
  };
  window.nexusConversa(document);
})();
