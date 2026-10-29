/* COS > Normalizações: o filtro na própria página (29/10/2026, Levi: "eu carrego a primeira vez e ele inventa de carregar
   sempre que clico"). Cada filtro recarregava a página inteira (1,1 MB com ~1.000 normalizações no mês). Agora as linhas
   do mês vêm todas, cada uma com o que cada filtro olha (data-f-<filtro>), e aqui só se mostra e esconde, refaz a faixa
   de números e troca o endereço (history.replaceState). O mês continua indo ao servidor (são outras linhas).

   As contas são as do servidor (nexus/cos/normalizacoes.py, `painel`), de propósito iguais:
   - a faixa conta a lista filtrada SEM o status (senão a fatia aberta seria sempre 100%), e a mediana só com a hora real;
   - as opções dos filtros contam o mês, ANTES dos filtros, e não mudam; as de usina, dentro do cliente escolhido;
   - a busca: o nº igual ao da OS (ou de uma relacionada), ou o texto dentro do de cada linha (data-f-busca);
   - o arredondamento do % é o do Python (o meio vai para o par) e a mediana de duas cai no meio, sem os segundos.
   Não usa o filtro-local.js porque lá as opções contam em cascata, e aqui a regra do COS é outra. */
(function () {
  "use strict";
  var form = document.getElementById("cos-norm-filtros");
  if (!form) return;
  var linhas = Array.prototype.slice.call(document.querySelectorAll("tr[data-norm-linha]"));
  var CHAVES = ["falha", "cliente", "usina", "criado_por", "tecnico"];
  var BUSCA_MAX = 80;
  var busca = form.elements.q;
  var relogio = null;

  function valor(nome) { return form.elements[nome] ? form.elements[nome].value : ""; }
  function texto() { return busca.value.split(/\s+/).filter(Boolean).join(" ").slice(0, BUSCA_MAX); }

  function casa(tr, q) {
    if (!q) return true;
    q = q.toLowerCase();
    if (/^\d+$/.test(q) && (tr.getAttribute("data-os") || "").split("|").indexOf(q) >= 0) return true;
    return (tr.getAttribute("data-f-busca") || "").indexOf(q) >= 0;
  }

  function paraOPar(x) {          // o round do Python: o meio vai para o número par
    var f = Math.floor(x);
    if (Math.abs(x - f - 0.5) < 1e-9) return f % 2 === 0 ? f : f + 1;
    return Math.round(x);
  }

  function duracao(m) {           // a duracao() do servidor: minutos e horas, nunca dias
    m = Math.max(0, Math.trunc(m));
    if (m < 60) return m + " min";
    var h = Math.floor(m / 60), r = m % 60;
    return r ? h + " h " + (r < 10 ? "0" : "") + r : h + " h";
  }

  function mediana(v) {
    if (!v.length) return "—";
    v.sort(function (a, b) { return a - b; });
    var meio = Math.floor(v.length / 2);
    return duracao(v.length % 2 ? v[meio] : (v[meio - 1] + v[meio]) / 2);
  }

  function por(nome, v) {
    var el = document.querySelector('[data-norm-r="' + nome + '"]');
    if (el) el.textContent = v;
    return el;
  }

  function endereco(extra) {
    var u = new URL(location.href);
    CHAVES.concat(["status"]).forEach(function (k) {
      if (valor(k)) u.searchParams.set(k, valor(k)); else u.searchParams.delete(k);
    });
    if (texto()) u.searchParams.set("q", texto()); else u.searchParams.delete("q");
    u.searchParams.delete("formato");
    Object.keys(extra || {}).forEach(function (k) { u.searchParams.set(k, extra[k]); });
    return u;
  }

  function aplicar() {
    var q = texto(), status = valor("status");
    var recorte = linhas.filter(function (tr) {
      for (var i = 0; i < CHAVES.length; i++) {
        var v = valor(CHAVES[i]);
        if (v && tr.getAttribute("data-f-" + CHAVES[i]) !== v) return false;
      }
      return casa(tr, q);
    });
    var lista = status ? recorte.filter(function (tr) { return tr.getAttribute("data-f-status") === status; }) : recorte;
    var na = new Set(lista);
    linhas.forEach(function (tr) {
      tr.hidden = !na.has(tr);
      // a linha dos Detalhes (logo abaixo, aberta pelo botão da OS) fecha junto com a linha que o filtro escondeu
      var det = tr.nextElementSibling;
      if (tr.hidden && det && det.classList.contains("cos-det-linha") && !det.hidden) {
        det.hidden = true;
        var bt = tr.querySelector(".cos-det-bt");
        if (bt) bt.setAttribute("aria-expanded", "false");
      }
    });

    var abertas = recorte.filter(function (tr) { return tr.getAttribute("data-aberta") === "1"; });
    var foras = recorte.filter(function (tr) {
      return tr.getAttribute("data-hr") === "1" && tr.getAttribute("data-fora") !== "";
    }).map(function (tr) { return Number(tr.getAttribute("data-fora")); });
    por("total", recorte.length);
    var ab = por("abertas", abertas.length);
    if (ab) ab.classList.toggle("ruim", abertas.length > 0);
    por("abertas_pct", recorte.length ? paraOPar(100 * abertas.length / recorte.length) : 0);
    por("abertas_7d", abertas.filter(function (tr) { return Number(tr.getAttribute("data-dias") || 0) >= 7; }).length);
    por("mediana", mediana(foras));
    por("sem_hora_real", recorte.filter(function (tr) { return tr.getAttribute("data-hr") === "0"; }).length);

    var vazio = document.querySelector("[data-norm-vazio]");
    if (vazio) vazio.hidden = lista.length > 0;
    var filtrado = !!(q || status || CHAVES.some(valor));
    var caixa = document.querySelector("[data-norm-limpar-caixa]");
    if (caixa) caixa.hidden = !filtrado;

    var u = endereco();
    history.replaceState(history.state, "", u.pathname + u.search + u.hash);
    var csv = document.querySelector("[data-norm-csv]");
    if (csv) { var c = endereco({formato: "csv"}); csv.setAttribute("href", c.pathname + c.search); }
    document.querySelectorAll("[data-norm-mes]").forEach(function (a) {
      var m = endereco({mes: a.getAttribute("data-norm-mes")});
      a.setAttribute("href", m.pathname + m.search);
    });
  }

  // as usinas do cliente escolhido, contadas sobre o mês (antes dos outros filtros), como o servidor faz
  function usinasDoCliente() {
    var cli = valor("cliente"), sel = form.elements.usina, conta = {};
    linhas.forEach(function (tr) {
      if (!cli || tr.getAttribute("data-f-cliente") === cli) {
        var u = tr.getAttribute("data-f-usina");
        conta[u] = (conta[u] || 0) + 1;
      }
    });
    sel.innerHTML = "";
    var todas = document.createElement("option");
    todas.value = ""; todas.textContent = "Todas";
    sel.appendChild(todas);
    Object.keys(conta).sort(function (a, b) { return a < b ? -1 : a > b ? 1 : 0; }).forEach(function (u) {
      var o = document.createElement("option");
      o.value = u; o.textContent = u + " (" + conta[u] + ")";
      sel.appendChild(o);
    });
    sel.value = "";
  }

  form.addEventListener("change", function (e) {
    if (e.target.name === "cliente") usinasDoCliente();
    aplicar();
  });
  busca.addEventListener("input", function () { clearTimeout(relogio); relogio = setTimeout(aplicar, 150); });
  form.addEventListener("submit", function (e) { e.preventDefault(); clearTimeout(relogio); aplicar(); });
  var limpar = document.querySelector("[data-norm-limpar]");
  if (limpar) limpar.addEventListener("click", function (e) {
    e.preventDefault();
    CHAVES.concat(["status"]).forEach(function (k) { if (form.elements[k]) form.elements[k].value = ""; });
    busca.value = "";
    usinasDoCliente();
    aplicar();
  });
})();
