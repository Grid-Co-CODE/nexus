/* O filtro na própria página (Levi, 17/10/2026: "sempre que vou puxar um filtro ele carrega o site de novo, deveria só
   filtrar os dados direto, parece que está atualizando a página novamente!"). As linhas já vêm todas na página, cada uma
   com o que cada filtro olha (data-f-<chave>, vários valores separados por "|"); escolher um filtro só mostra e esconde
   linhas, refaz as contas de cada lista (em cascata: cada lista conta com os OUTROS filtros, como o servidor faz) e
   troca o endereço (history.replaceState), sem ir ao servidor. O servidor continua entendendo o mesmo endereço: a página
   aberta já filtrada chega com as linhas certas escondidas.

   O formulário:   <form data-filtro-local id="X">: os <select data-fl> (o name é a chave), os <input data-fl-texto>
                   ("contem": a busca no data-f-busca; "numero": os dígitos iguais ao data-f-<name>) e o
                   [data-fl-limpar].
   As linhas:      [data-fl-grupo="X"] (uma tabela; a que está escondida não conta) com <tr data-fl-linha>; a linha de
                   detalhe logo abaixo (cn-detalhe, fp-hist) some junto. data-fl-fora="1": só aparece com "todas".
   Os chips:       [data-fl-chips="X"] com <a data-fl-chip="valor"> (data-fl-chave diz a chave; "" = todas).
   Todas:          [data-fl-seg="X"] com <a data-fl-todas="0|1">.
   As contas:      [data-fl-conta="grupo"] (as linhas visíveis do grupo); [data-fl-vazio="grupo"] (sem nenhuma).
   Os formulários de gravar da página levam os filtros de agora (v_<chave>), para a tela voltar filtrada.
   Depois de cada filtragem: o evento "filtro-local" no document, com {form, visiveis} (a página refaz o que for dela). */
(function () {
  "use strict";

  function sem(s) {
    return String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
  }

  function iniciar(form) {
    var id = form.id;
    var selects = Array.prototype.slice.call(form.querySelectorAll("select[data-fl]"));
    var textos = Array.prototype.slice.call(form.querySelectorAll("input[data-fl-texto]"));
    var chips = document.querySelector('[data-fl-chips="' + id + '"]');
    var chaveChip = chips ? chips.getAttribute("data-fl-chave") : null;
    var seg = document.querySelector('[data-fl-seg="' + id + '"]');
    var url = new URL(location.href);
    var estado = {};
    selects.forEach(function (s) { estado[s.name] = s.value; });
    textos.forEach(function (t) { estado[t.name] = t.value; });
    if (chaveChip) estado[chaveChip] = url.searchParams.get(chaveChip) || "";
    estado.todas = seg ? url.searchParams.get("todas") === "1" : true;

    function grupos() { return Array.prototype.slice.call(document.querySelectorAll('[data-fl-grupo="' + id + '"]')); }
    function ativo(g) { return !g.closest("[hidden]"); }
    function linhas(g) { return Array.prototype.slice.call(g.querySelectorAll("tr[data-fl-linha]")); }
    function vals(tr, k) {
      var v = tr.getAttribute("data-f-" + k);
      return v === null ? null : v.split("|");
    }
    function passa(tr, menos) {
      if (tr.getAttribute("data-fl-fora") === "1" && !estado.todas) return false;
      var ks = selects.map(function (s) { return s.name; });
      if (chaveChip) ks.push(chaveChip);
      for (var i = 0; i < ks.length; i++) {
        var k = ks[i];
        if (k === menos || !estado[k]) continue;
        var v = vals(tr, k);
        if (v !== null && v.indexOf(estado[k]) < 0) return false;
      }
      for (var j = 0; j < textos.length; j++) {
        var t = textos[j], q = estado[t.name];
        if (t.name === menos || !q) continue;
        if (t.getAttribute("data-fl-texto") === "numero") {
          var n = q.replace(/\D/g, ""), alvo = tr.getAttribute("data-f-" + t.name);
          if (n && alvo !== null && alvo !== n) return false;
        } else if ((tr.getAttribute("data-f-busca") || "").indexOf(sem(q)) < 0) {
          return false;
        }
      }
      return true;
    }
    function contar(ls, k) {
      var c = {};
      ls.forEach(function (tr) {
        if (!passa(tr, k)) return;
        (vals(tr, k) || []).forEach(function (v) { if (v) c[v] = (c[v] || 0) + 1; });
      });
      return c;
    }

    function aplicar() {
      var visiveis = 0, ativas = [];
      grupos().forEach(function (g) {
        var n = 0;
        linhas(g).forEach(function (tr) {
          var ok = passa(tr, null), det = tr.nextElementSibling;
          tr.hidden = !ok;
          if (det && det.matches(".cn-detalhe, .fp-hist") && !ok) {
            det.hidden = true;
            tr.setAttribute("aria-expanded", "false");
            var b = tr.querySelector("[aria-expanded]");
            if (b) b.setAttribute("aria-expanded", "false");
          }
          if (ok) n++;
          if (ativo(g)) ativas.push(tr);         // as contas das listas: só a tabela que está à vista
        });
        if (ativo(g)) visiveis += n;
        var gid = g.getAttribute("data-fl-nome");
        if (gid) {
          document.querySelectorAll('[data-fl-conta="' + gid + '"]').forEach(function (e) { e.textContent = n; });
          document.querySelectorAll('[data-fl-vazio="' + gid + '"]').forEach(function (e) { e.hidden = n > 0; });
        }
      });
      // as listas: cada uma conta com os OUTROS filtros; a escolhida fica mesmo sem nada
      selects.forEach(function (s) {
        var c = contar(ativas, s.name);
        Array.prototype.forEach.call(s.options, function (o) {
          if (!o.value) return;
          var n = c[o.value] || 0, rot = o.getAttribute("data-rotulo") || o.value;
          o.textContent = rot + " (" + n + ")";
          var some = !n && o.value !== estado[s.name];
          o.hidden = some;
          o.disabled = some;
        });
      });
      if (chips) {
        var cc = contar(ativas, chaveChip), todas = ativas.filter(function (tr) { return passa(tr, chaveChip); }).length;
        chips.querySelectorAll("a[data-fl-chip]").forEach(function (a) {
          var v = a.getAttribute("data-fl-chip"), b = a.querySelector("b");
          if (b) b.textContent = v ? (cc[v] || 0) : todas;
          if (v === (estado[chaveChip] || "")) a.setAttribute("aria-current", "page");
          else a.removeAttribute("aria-current");
        });
      }
      if (seg) {
        seg.querySelectorAll("a[data-fl-todas]").forEach(function (a) {
          if ((a.getAttribute("data-fl-todas") === "1") === estado.todas) a.setAttribute("aria-current", "page");
          else a.removeAttribute("aria-current");
        });
      }
      var limpar = form.querySelector("[data-fl-limpar]");
      if (limpar) {
        limpar.hidden = !Object.keys(estado).some(function (k) { return k !== "todas" && estado[k]; });
      }
      // o endereço acompanha (voltar, atualizar e mandar o link dão a mesma tela)
      var u = new URL(location.href);
      Object.keys(estado).forEach(function (k) {
        var v = k === "todas" ? (seg && estado.todas ? "1" : "") : estado[k];
        if (v) u.searchParams.set(k, v); else u.searchParams.delete(k);
      });
      history.replaceState(history.state, "", u.pathname + u.search + u.hash);
      document.dispatchEvent(new CustomEvent("filtro-local", {detail: {form: form, visiveis: visiveis}}));
    }

    selects.forEach(function (s) {
      s.addEventListener("change", function () { estado[s.name] = s.value; aplicar(); });
    });
    var espera;
    textos.forEach(function (t) {
      t.addEventListener("input", function () {
        clearTimeout(espera);
        espera = setTimeout(function () { estado[t.name] = t.value.trim(); aplicar(); }, 150);
      });
    });
    form.addEventListener("submit", function (ev) { ev.preventDefault(); });
    if (chips) {
      chips.addEventListener("click", function (ev) {
        var a = ev.target.closest("a[data-fl-chip]");
        if (!a) return;
        ev.preventDefault();
        estado[chaveChip] = a.getAttribute("data-fl-chip");
        aplicar();
      });
    }
    if (seg) {
      seg.addEventListener("click", function (ev) {
        var a = ev.target.closest("a[data-fl-todas]");
        if (!a) return;
        ev.preventDefault();
        estado.todas = a.getAttribute("data-fl-todas") === "1";
        aplicar();
      });
    }
    var limpar = form.querySelector("[data-fl-limpar]");
    if (limpar) {
      limpar.addEventListener("click", function (ev) {
        ev.preventDefault();
        selects.forEach(function (s) { s.value = ""; estado[s.name] = ""; });
        textos.forEach(function (t) { t.value = ""; estado[t.name] = ""; });
        if (chaveChip) estado[chaveChip] = "";
        aplicar();
      });
    }
    // gravar leva os filtros de agora: a tela volta como estava
    document.addEventListener("submit", function (ev) {
      var f = ev.target;
      if (f === form || ev.defaultPrevented || !f.querySelector('input[name^="v_"], input[name="item"], input[name="usina_id"]')) return;
      Array.prototype.forEach.call(f.querySelectorAll('input[name^="v_"]'), function (i) {
        if (i.name !== "v_ver") i.remove();
      });
      Object.keys(estado).forEach(function (k) {
        var v = k === "todas" ? (seg && estado.todas ? "1" : "") : estado[k];
        if (!v) return;
        var i = document.createElement("input");
        i.type = "hidden"; i.name = "v_" + k; i.value = v;
        f.appendChild(i);
      });
    });
    window.FiltroLocal = window.FiltroLocal || {};
    window.FiltroLocal[id] = {aplicar: aplicar, estado: estado};
    aplicar();
  }

  document.querySelectorAll("form[data-filtro-local]").forEach(iniciar);
})();
