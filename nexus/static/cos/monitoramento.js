// O Monitoramento do COS (09/11/2026, nexus/torres/cos/templates/cos/monitoramento.html).
// 1) O corpo da tela se atualiza a cada 30 s: o mesmo endereço com ?parcial=1, pelo nexusPedir (a sessão vencida leva ao
//    login), troca só o corpo, sem recarregar a página nem perder a rolagem. Com a aba escondida ou um campo em uso, espera.
// 2) A dica da curva: passar o mouse mostra o kW daquele horário, com a mira vertical na curva.
(function (raiz) {
  "use strict";
  // ── A BUSCA AO DIGITAR (13/11/2026, o dono: "Preciso digita o nome da usina e dar enter pra aparecer a que eu quero.
  // Isso fica incomodando"). A tela filtra os cartões que já estão nela a cada tecla, sem recarregar; o endereço guarda o
  // `q` (a volta de 30 s e o recarregar mantêm o filtro), e ao sair do campo a tela pede o corpo de novo para as somas e
  // as contagens do servidor. A regra é a do servidor (`painel`, nexus/cos/monitoramento.py): toda palavra no nome, no
  // código ou no cliente — e sem acento dos dois lados ("ribeirao" acha a Ribeirão).
  function dobrar(s) {
    return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }
  function palavrasDa(busca) { return dobrar(busca).split(/\s+/).filter(Boolean).slice(0, 12); }
  function combina(texto, palavras) {
    var t = dobrar(texto);
    for (var i = 0; i < palavras.length; i++) { if (t.indexOf(palavras[i]) < 0) { return false; } }
    return true;
  }
  raiz.NexusCosBusca = { dobrar: dobrar, palavrasDa: palavrasDa, combina: combina };
  if (typeof document === "undefined") { return; }       // no node (os testes) só as contas acima

  var corpo = document.getElementById("cos-mon-corpo");
  var dica = document.getElementById("cos-dica");
  var lido = document.getElementById("cos-mon-lido");
  if (!corpo) { return; }
  var INTERVALO_MS = 30000;

  function emUso() {
    var a = document.activeElement;
    // o painel dos Filtros aberto também segura a troca do corpo (12/11/2026, static/filtros-os.js): a lista não some
    // no meio da escolha
    if (corpo.querySelector(".fo-painel:not([hidden])")) { return true; }
    return !!(a && corpo.contains(a) && /^(INPUT|SELECT|TEXTAREA)$/.test(a.tagName));
  }

  var noAr = false, pedido = 0;                 // revisão de 12/11: um pedido de cada vez; a resposta velha não vence a nova
  // `digitando` (a busca ao digitar, 13/11/2026): pede mesmo com o campo em uso, e troca o corpo EM VOLTA do formulário
  // dos filtros — o campo fica onde está, com o foco e o cursor, e o resto (cartões, somas, contagens) vem do servidor.
  function trocarEmVoltaDoFormulario(html) {
    var atual = corpo.querySelector(":scope > form.cn-filtros");
    var tmp = document.createElement("div"); tmp.innerHTML = html;
    var novo = tmp.querySelector(":scope > form.cn-filtros");
    if (!atual || !novo) { return false; }
    var antes = true, depoisDe = atual;
    Array.prototype.slice.call(corpo.childNodes).forEach(function (n) { if (n !== atual) { corpo.removeChild(n); } });
    Array.prototype.slice.call(tmp.childNodes).forEach(function (n) {
      if (n === novo) { antes = false; return; }
      if (antes) { corpo.insertBefore(n, atual); } else { depoisDe.parentNode.insertBefore(n, depoisDe.nextSibling); depoisDe = n; }
    });
    return true;
  }
  function atualizar(digitando) {
    if (typeof window.nexusPedir !== "function" || document.hidden) { return; }
    if (!digitando && (noAr || emUso())) { return; }
    noAr = true;
    var este = ++pedido;
    setTimeout(function () { if (este === pedido) { noAr = false; } }, 25000);   // um pedido travado não para a tela
    var q = new URLSearchParams(location.search);
    q.set("parcial", "1");
    window.nexusPedir(nexusRota("/t/cos/monitoramento") + "?" + q.toString()).then(function (d) {
      if (este !== pedido) { return; }
      noAr = false;
      if (d && typeof d.html === "string") {
        esconder();
        var campo = document.activeElement, emBusca = campo && campo.matches && campo.matches('form.cn-filtros input[name="q"]');
        if (!(emBusca && trocarEmVoltaDoFormulario(d.html))) {
          if (emBusca) { return; }                 // sem como trocar em volta do campo: espera a pessoa sair dele
          corpo.innerHTML = d.html;
        }
        var campoBusca = corpo.querySelector('form.cn-filtros input[name="q"]');
        if (campoBusca && campoBusca.value) { filtrar(campoBusca.value); }   // a digitação que veio depois do pedido também vale
        if (lido) {
          lido.textContent = "";
          if (d.lido) { lido.appendChild(document.createTextNode("lido às ")); var b = document.createElement("b"); b.textContent = d.lido; lido.appendChild(b); }
        }
      }
    }).catch(function () { noAr = false; /* fica a última leitura: a próxima volta tenta de novo */ });
  }
  setInterval(function () { atualizar(); }, INTERVALO_MS);
  // protótipo de 12/11/2026: a página aberta de uma cópia (o voltar do navegador, uma aba esquecida) com a leitura de mais
  // de 2 minutos se atualiza na hora, em vez de esperar os 30 s com os números velhos na tela
  (function () {
    var b = lido && lido.querySelector("b"), m = b ? /^(\d{2}):(\d{2})$/.exec(b.textContent.trim()) : null;
    if (!m) { return; }
    var agora = new Date(new Date().toLocaleString("en-US", { timeZone: "America/Sao_Paulo" }));
    var dif = agora.getHours() * 60 + agora.getMinutes() - (+m[1] * 60 + +m[2]);
    if (dif > 2 || dif < 0) { atualizar(); }
  })();
  document.addEventListener("visibilitychange", function () { if (!document.hidden) { atualizar(); } });

  // ── a dica da curva ──
  function minutos(hhmm) {
    var p = String(hhmm || "").split(":");
    return p.length === 2 ? parseInt(p[0], 10) * 60 + parseInt(p[1], 10) : NaN;
  }
  function hora(m) {
    var h = Math.floor(m / 60), mm = m % 60;
    return (h < 10 ? "0" : "") + h + ":" + (mm < 10 ? "0" : "") + mm;
  }
  function kw(v) {   // a mesma conta do kw_txt (nexus/cos/monitoramento.py)
    if (v >= 1000) { return (v / 1000).toFixed(1).replace(".", ",") + " MW"; }
    return Math.round(v) + " kW";
  }
  var mira = null;
  function esconder() {
    if (dica) { dica.hidden = true; }
    if (mira) { mira.setAttribute("hidden", ""); mira = null; }
  }

  corpo.addEventListener("mousemove", function (e) {
    var svg = e.target && e.target.closest ? e.target.closest("svg.cos-curva") : null;
    if (!svg || !dica) { esconder(); return; }
    var valores = (svg.getAttribute("data-kw") || "").split("|");
    var de = minutos(svg.getAttribute("data-de")), passo = parseInt(svg.getAttribute("data-passo"), 10) || 15;
    var janela = (svg.getAttribute("data-janela") || "").split("-").map(Number);
    if (isNaN(de) || janela.length !== 2) { esconder(); return; }
    var r = svg.getBoundingClientRect();
    var frac = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    var i = Math.round((janela[0] + frac * (janela[1] - janela[0]) - de) / passo);
    var t = de + i * passo;
    var v = i >= 0 && i < valores.length && valores[i] !== "" ? Number(valores[i]) : null;
    dica.textContent = hora(t) + " · " + (v === null ? "sem amostra" : kw(v));
    dica.hidden = false;
    dica.style.left = Math.min(e.clientX + 12, window.innerWidth - dica.offsetWidth - 8) + "px";
    dica.style.top = (e.clientY - 34) + "px";
    var linha = svg.querySelector(".cos-curva-mira");
    if (linha) {
      var largura = svg.viewBox.baseVal.width || 160;
      var x = Math.max(0, Math.min(largura, (t - janela[0]) / (janela[1] - janela[0]) * largura));
      linha.setAttribute("x1", x);
      linha.setAttribute("x2", x);
      linha.removeAttribute("hidden");
      if (mira && mira !== linha) { mira.setAttribute("hidden", ""); }
      mira = linha;
    }
  });
  corpo.addEventListener("mouseleave", esconder);

  // ── a busca ao digitar (o campo mora no corpo, que a volta de 30 s troca: tudo por delegação) ──
  var SELETOR_BUSCA = 'form.cn-filtros input[name="q"]';
  var esperaBusca = null, esperaServidor = null, buscaAplicada = new URLSearchParams(location.search).get("q") || "";
  function textoDe(el) {
    var n = el.querySelector(".n");
    return [(n && n.textContent) || "", el.getAttribute("data-codigo") || "", el.getAttribute("data-cliente") || ""].join(" ");
  }
  function filtrar(valor) {
    var palavras = palavrasDa(valor), visiveis = 0;
    corpo.querySelectorAll(".cos-mon-u[data-gid], .cos-mon-at-i[data-gid]").forEach(function (el) {
      var mostra = !palavras.length || combina(textoDe(el), palavras);
      el.hidden = !mostra;
      if (mostra && el.classList.contains("cos-mon-u")) { visiveis++; }
    });
    // a seção (o cliente, a "Atenção agora") sem nenhum cartão à mostra some junto
    corpo.querySelectorAll(".cos-mon-cliente, .cos-mon-atencao").forEach(function (s) {
      s.hidden = !s.querySelector(".cos-mon-u[data-gid]:not([hidden]), .cos-mon-at-i[data-gid]:not([hidden])");
    });
    var vazio = corpo.querySelector(".cn-vazio-busca");
    if (!visiveis && palavras.length && corpo.querySelector(".cos-mon-u[data-gid]")) {
      if (!vazio) {
        vazio = document.createElement("p"); vazio.className = "cn-vazio cn-vazio-busca";
        var form = corpo.querySelector("form.cn-filtros");
        (form && form.parentNode ? form.parentNode : corpo).appendChild(vazio);
      }
      vazio.textContent = "Nenhuma usina com “" + valor.trim() + "”.";
    } else if (vazio) { vazio.remove(); }
  }
  function guardarNoEndereco(valor) {
    var q = new URLSearchParams(location.search);
    if (valor.trim()) { q.set("q", valor.trim()); } else { q.delete("q"); }
    var s = q.toString();
    try { history.replaceState(history.state, "", location.pathname + (s ? "?" + s : "") + location.hash); } catch (e) { /* sem history: filtra igual */ }
  }
  corpo.addEventListener("input", function (e) {
    if (!e.target.matches || !e.target.matches(SELETOR_BUSCA)) { return; }
    var campo = e.target;
    clearTimeout(esperaBusca);
    esperaBusca = setTimeout(function () { filtrar(campo.value); guardarNoEndereco(campo.value); }, 120);
    // e o servidor, logo depois que a pessoa para de digitar: as usinas que a busca anterior tinha tirado, as somas e as
    // contagens do filtro (o campo fica onde está: `trocarEmVoltaDoFormulario`)
    clearTimeout(esperaServidor);
    esperaServidor = setTimeout(function () {
      var v = campo.value.trim();
      if (v !== buscaAplicada) { buscaAplicada = v; atualizar(true); }
    }, 450);
  });
  corpo.addEventListener("keydown", function (e) {
    if (!e.target.matches || !e.target.matches(SELETOR_BUSCA)) { return; }
    if (e.key === "Enter") { e.preventDefault(); clearTimeout(esperaBusca); filtrar(e.target.value); guardarNoEndereco(e.target.value); }
    if (e.key === "Escape" && e.target.value) { e.preventDefault(); e.target.value = ""; filtrar(""); guardarNoEndereco(""); }
  });
  // ao sair do campo com a busca mudada, o corpo vem de novo do servidor: as somas e as contagens do filtro
  corpo.addEventListener("focusout", function (e) {
    if (!e.target.matches || !e.target.matches(SELETOR_BUSCA)) { return; }
    var v = e.target.value.trim();
    if (v !== buscaAplicada) { buscaAplicada = v; setTimeout(atualizar, 0); }
  });
})(typeof window !== "undefined" ? window : globalThis);
