/* O vídeo wall do Mapa de equipe (12/11/2026, Levi: "Prepare um modo vídeo wall que apareça informações como no anexo 1
   do lado esquerdo do mapa!"). O mapa é o do campo-mapa.js; aqui só o que é da TV:
   - o relógio (hora de Brasília);
   - a releitura da tela a cada 2 minutos (a escolha dele), só depois de conferir que o Nexus responde: com o servidor
     fora, a tela fica com o que tem e diz desde quando; a sessão que caiu leva ao Entrar (o _confere_sessao_js);
   - a lista das ocorrências que não cabe rola sozinha, devagar, e volta ao topo ("Rolar sozinha devagar", a escolha
     dele): para 5 s em cima e embaixo. Roda também com os efeitos de animação do Windows desligados, porque sem ela a
     lista ficaria cortada (o mesmo caso das divisas pulsando);
   - os controles (sair, zoom, focos, fundo) aparecem ao mexer o mouse ou apertar uma tecla, e somem em 4 s. */
(function () {
  "use strict";
  var raiz = document.querySelector("[data-eq-tv]");
  if (!raiz) return;

  // ── o relógio ──────────────────────────────────────────────────────────────────────────────────────────────────
  var hora = raiz.querySelector(".eqtv-hora"), data = raiz.querySelector(".eqtv-data");
  function relogio() {
    var agora = new Date();
    try {
      hora.textContent = agora.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
      data.textContent = agora.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo", weekday: "long", day: "2-digit", month: "2-digit" });
    } catch (e) { /* navegador sem fuso: fica a hora que o servidor escreveu */ }
  }
  relogio();
  setInterval(relogio, 15000);

  // ── a releitura a cada 2 minutos ───────────────────────────────────────────────────────────────────────────────
  var segundos = parseInt(raiz.getAttribute("data-recarrega-s"), 10) || 120;
  var saude = raiz.getAttribute("data-saude");
  var estado = raiz.querySelector(".eqtv-estado");
  function hhmm() {
    try { return new Date().toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" }); }
    catch (e) { return ""; }
  }
  var foraDesde = "";
  function reler() {
    fetch(saude, { cache: "no-store", credentials: "same-origin" }).then(function (r) {
      if (!r.ok) throw new Error(String(r.status));
      location.reload();
    }).catch(function () {
      foraDesde = foraDesde || hhmm();
      estado.textContent = "O Nexus não respondeu desde " + foraDesde + ". A tela fica com o que tem e tenta de novo em " +
        Math.round(segundos / 60) + " min.";
      estado.hidden = false;
      setTimeout(reler, segundos * 1000);
    });
  }
  setTimeout(reler, segundos * 1000);

  // ── a lista que rola sozinha ───────────────────────────────────────────────────────────────────────────────────
  var caixa = raiz.querySelector("[data-eqtv-rola]");
  var trilho = caixa && caixa.querySelector(".eqtv-trilho");
  if (caixa && trilho) {
    var PARADA_MS = 5000, pos = 0, fase = "topo", desde = performance.now(), antes = desde;
    var passo = function (t) {
      var sobra = trilho.scrollHeight - caixa.clientHeight;
      var dt = Math.min(100, t - antes);
      antes = t;
      if (sobra <= 2) {                       // cabe: nada rola
        pos = 0; fase = "topo"; desde = t;
      } else if (fase === "topo" || fase === "fim") {
        if (t - desde > PARADA_MS) {
          if (fase === "fim") { pos = 0; fase = "topo"; } else { fase = "desce"; }
          desde = t;
        }
      } else {
        // uma altura da caixa a cada 25 s: devagar, para dar tempo de ler de longe
        pos = Math.min(sobra, pos + caixa.clientHeight / 25000 * dt);
        if (pos >= sobra) { fase = "fim"; desde = t; }
      }
      trilho.style.transform = "translateY(" + (-pos).toFixed(1) + "px)";
      requestAnimationFrame(passo);
    };
    requestAnimationFrame(passo);
  }

  // ── os controles só ao mexer ───────────────────────────────────────────────────────────────────────────────────
  var esconder = 0;
  function mexeu() {
    raiz.classList.add("eqtv--mexeu");
    clearTimeout(esconder);
    esconder = setTimeout(function () { raiz.classList.remove("eqtv--mexeu"); }, 4000);
  }
  ["mousemove", "keydown", "touchstart"].forEach(function (ev) { document.addEventListener(ev, mexeu, { passive: true }); });
})();
