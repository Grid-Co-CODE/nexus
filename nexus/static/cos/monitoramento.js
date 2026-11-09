// O Monitoramento do COS (09/11/2026, nexus/torres/cos/templates/cos/monitoramento.html).
// 1) O corpo da tela se atualiza a cada 30 s: o mesmo endereço com ?parcial=1, pelo nexusPedir (a sessão vencida leva ao
//    login), troca só o corpo, sem recarregar a página nem perder a rolagem. Com a aba escondida ou um campo em uso, espera.
// 2) A dica da curva: passar o mouse mostra o kW daquele horário, com a mira vertical na curva.
(function () {
  "use strict";
  var corpo = document.getElementById("cos-mon-corpo");
  var dica = document.getElementById("cos-dica");
  var lido = document.getElementById("cos-mon-lido");
  if (!corpo) { return; }
  var INTERVALO_MS = 30000;

  function emUso() {
    var a = document.activeElement;
    return !!(a && corpo.contains(a) && /^(INPUT|SELECT|TEXTAREA)$/.test(a.tagName));
  }

  function atualizar() {
    if (document.hidden || emUso() || typeof window.nexusPedir !== "function") { return; }
    var q = new URLSearchParams(location.search);
    q.set("parcial", "1");
    window.nexusPedir(nexusRota("/t/cos/monitoramento") + "?" + q.toString()).then(function (d) {
      if (d && typeof d.html === "string") {
        esconder();
        corpo.innerHTML = d.html;
        if (lido) { lido.innerHTML = d.lido ? "lido às <b>" + d.lido + "</b>" : ""; }
      }
    }).catch(function () { /* fica a última leitura: a próxima volta tenta de novo */ });
  }
  setInterval(atualizar, INTERVALO_MS);
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
})();
