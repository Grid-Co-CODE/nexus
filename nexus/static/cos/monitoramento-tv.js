// O videowall do Monitoramento do COS (09/11/2026, templates/cos/monitoramento_tv.html).
// 1) Caber: acha o número de colunas que deixa o MAIOR cartão possível com todas as usinas na tela, sem rolagem. Se nem
//    assim o cartão fica legível (MIN_REM de largura), divide em páginas e gira a cada GIRO_MS.
// 2) Ao vivo: a cada 30 s pede o corpo de novo (?tv=1&parcial=1, pelo nexusPedir) e troca só ele.
// 3) O relógio em Brasília, a tela acesa (Wake Lock, quando o navegador deixa) e os controles só ao mexer o mouse.
(function () {
  "use strict";
  var corpo = document.getElementById("cos-tv-corpo");
  if (!corpo) { return; }
  var ASPECTO = 1.55;          // largura / altura do cartão que se lê bem: o nome, o kW e a curva
  var MIN_REM = 8.5;           // abaixo disso o nome some: melhor girar páginas
  var GIRO_MS = 15000;
  var VOLTA_MS = 30000;
  var pagina = 0, paginas = 1;

  function rem() { return parseFloat(getComputedStyle(document.documentElement).fontSize) || 16; }

  function caber() {
    var grade = document.getElementById("cos-tv-grade");
    if (!grade) { return; }
    var cartoes = Array.prototype.slice.call(grade.children);
    var n = cartoes.length;
    if (!n) { return; }
    var W = grade.clientWidth, H = grade.clientHeight, gap = parseFloat(getComputedStyle(grade).rowGap) || 8;
    var melhor = null;
    for (var c = 1; c <= n; c++) {
      var w = (W - (c - 1) * gap) / c;
      var linhas = Math.ceil(n / c);
      var h = Math.min((H - (linhas - 1) * gap) / linhas, w / ASPECTO * 1.25);
      var area = Math.min(w, h * ASPECTO) * h;
      if (h > 0 && (!melhor || area > melhor.area)) { melhor = {c: c, w: w, h: h, area: area}; }
    }
    var minimo = MIN_REM * rem();
    if (!melhor || melhor.w >= minimo) {
      paginas = 1;
    } else {
      // não cabe legível: o cartão mínimo, quantos couberem por página
      var cols = Math.max(1, Math.floor((W + gap) / (minimo + gap)));
      var hMin = minimo / ASPECTO;
      var linhasPorPagina = Math.max(1, Math.floor((H + gap) / (hMin + gap)));
      var porPagina = cols * linhasPorPagina;
      paginas = Math.ceil(n / porPagina);
      melhor = {c: cols, h: (H - (linhasPorPagina - 1) * gap) / linhasPorPagina};
      pagina = pagina % paginas;
      cartoes.forEach(function (el, i) { el.hidden = Math.floor(i / porPagina) !== pagina; });
    }
    if (paginas === 1) { cartoes.forEach(function (el) { el.hidden = false; }); }
    grade.style.setProperty("--cols", melhor.c);
    grade.style.setProperty("--linha", Math.floor(melhor.h) + "px");
    var rotulo = document.getElementById("cos-tv-pagina");
    if (rotulo) {
      rotulo.hidden = paginas === 1;
      rotulo.textContent = "página " + (pagina + 1) + " de " + paginas;
    }
  }

  function girar() {
    if (paginas > 1) { pagina = (pagina + 1) % paginas; caber(); }
  }

  function atualizar() {
    if (document.hidden || typeof window.nexusPedir !== "function") { return; }
    var q = new URLSearchParams(location.search);
    q.set("tv", "1");
    q.set("parcial", "1");
    window.nexusPedir(nexusRota("/t/cos/monitoramento") + "?" + q.toString()).then(function (d) {
      if (d && typeof d.html === "string") { corpo.innerHTML = d.html; caber(); }
    }).catch(function () { /* fica a última leitura na parede: a próxima volta tenta de novo */ });
  }

  var hora = document.getElementById("cos-tv-hora"), data = document.getElementById("cos-tv-data");
  function relogio() {
    var agora = new Date();
    try {
      if (hora) { hora.textContent = agora.toLocaleTimeString("pt-BR", {timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit"}); }
      if (data) { data.textContent = agora.toLocaleDateString("pt-BR", {timeZone: "America/Sao_Paulo", weekday: "short", day: "2-digit", month: "2-digit"}); }
    } catch (e) { /* navegador sem o fuso: fica a hora do servidor */ }
  }

  // a tela da parede não pode apagar sozinha
  var trava = null;
  function manterAcesa() {
    if (!navigator.wakeLock || document.hidden) { return; }
    navigator.wakeLock.request("screen").then(function (t) { trava = t; }).catch(function () { trava = null; });
  }

  // os controles aparecem ao mexer o mouse e somem 3 s depois
  var quieto = null;
  function mexeu() {
    document.body.classList.remove("cos-tv-quieto");
    clearTimeout(quieto);
    quieto = setTimeout(function () { document.body.classList.add("cos-tv-quieto"); }, 3000);
  }
  document.addEventListener("mousemove", mexeu);
  document.addEventListener("keydown", mexeu);
  var cheia = document.getElementById("cos-tv-cheia");
  if (cheia) {
    cheia.addEventListener("click", function () {
      if (document.fullscreenElement) { document.exitFullscreen(); }
      else if (document.documentElement.requestFullscreen) { document.documentElement.requestFullscreen(); }
    });
  }

  window.addEventListener("resize", caber);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) { atualizar(); manterAcesa(); }
  });
  caber();
  relogio();
  mexeu();
  manterAcesa();
  setInterval(relogio, 5000);
  setInterval(atualizar, VOLTA_MS);
  setInterval(girar, GIRO_MS);
})();
