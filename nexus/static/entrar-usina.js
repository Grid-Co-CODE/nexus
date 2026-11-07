/* A usina sem fim atrás da tela de entrar (07/11/2026, Levi, depois de seis rodadas de prévia: "Ficou ótimo!!! sobe").

   Dois blocos espelhados de fileiras paralelas, cada fileira uma string de 2 módulos em retrato (2,28 m) por 34 módulos
   (1,13 m), inclinadas 20° para o sol a 0,8 m do chão, vistas do alto (a câmera do "ângulo alto"). São fileiras demais
   para caber na tela, de propósito: o campo passa da borda e as de longe somem no fundo, a sensação de infinito. As cores
   são só classes (o nexus.css, seção "Entrar"), então o desenho segue o tema escuro e o claro.

   O que as rodadas ensinaram:
   - a ordem do desenho é por MÓDULO, não por fileira: a fileira é longa e vista de lado, uma ponta perto e a outra longe,
     e ordenar a fileira pelo centro punha módulos de trás por cima dos da frente (e o mouse marcava o de trás);
   - o módulo é opaco ("tire essa transparência dos módulos"): a distância apaga por cima, com uma névoa da cor do fundo
     na forma do próprio módulo;
   - ao passar o mouse, o módulo ganha a borda verde escura, desenhada por cima de tudo (a vizinha não cobre metade dela);
   - uma luz verde passa uma vez pelos módulos ao abrir; quem pede menos movimento no sistema não a vê;
   - só entra o que aparece na tela, e o módulo pequeno na tela vai sem as células (a tela não pesa). */
(function () {
  var svg = document.querySelector("svg.entrar-usina");
  if (!svg) return;
  var parado = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var R = Math.PI / 180;
  var MOD_L = 1.13, MOD_A = 2.28, GAP = 0.03, INCL = 20 * R, ALT0 = 0.8, FILEIRAS = 22, N = 34, PASSO = 7.5, CORREDOR = 7;
  var CAM = {yaw: -30, pitch: 34, dist: 26, altura: 18, alvo: [0, 6], esc: 980, ox: 1130, oy: 560};
  var SOL = [-0.55, 0.45];                                        // a sombra cai para trás e para a esquerda

  var cy = Math.cos(CAM.yaw * R), sy = Math.sin(CAM.yaw * R), cp = Math.cos(CAM.pitch * R), sp = Math.sin(CAM.pitch * R);
  function proj(p) {                                              // (x, y, z) em metros -> [x, y] da tela e a profundidade
    var x = p[0] - CAM.alvo[0], y = p[1] - CAM.alvo[1];
    var xr = x * cy - y * sy, yr = x * sy + y * cy;
    var vy = yr + CAM.dist, vz = p[2] - CAM.altura;
    var prof = vy * cp - vz * sp, cima = vy * sp + vz * cp;
    return [CAM.ox + CAM.esc * xr / prof, CAM.oy - CAM.esc * cima / prof, prof];
  }
  function pts(ps) { return ps.map(function (p) { var q = proj(p); return q[0].toFixed(1) + "," + q[1].toFixed(1); }).join(" "); }
  function poli(ps, cls, extra) { return '<polygon class="' + cls + '" points="' + pts(ps) + '"' + (extra || "") + "/>"; }
  function lin(a, b, cls) {
    var p = proj(a), q = proj(b);
    return '<line class="' + cls + '" x1="' + p[0].toFixed(1) + '" y1="' + p[1].toFixed(1) + '" x2="' + q[0].toFixed(1) +
      '" y2="' + q[1].toFixed(1) + '"/>';
  }
  function canto(m, i, a) { return [m.x + i, m.y + a * Math.cos(INCL), ALT0 + a * Math.sin(INCL)]; }
  function naTela(ps) {
    return ps.some(function (p) { var q = proj(p); return q[2] > 0.5 && q[0] > -60 && q[0] < 1660 && q[1] > -60 && q[1] < 960; });
  }

  var mesas = [], comp = N * (MOD_L + GAP);
  for (var r = 0; r < FILEIRAS; r++) {
    mesas.push({x: -CORREDOR / 2 - comp, y: r * PASSO, n: N});   // o bloco da esquerda
    mesas.push({x: CORREDOR / 2, y: r * PASSO, n: N});           // o da direita, espelhado
  }
  var pecas = mesas.map(function (m) {
    var L = m.n * (MOD_L + GAP), A = 2 * (MOD_A + GAP);
    return {m: m, L: L, A: A, prof: proj([m.x + L / 2, m.y + 1, 1])[2]};
  }).filter(function (pc) { return pc.prof > 1; });
  var perto = Math.min.apply(null, pecas.map(function (p) { return p.prof; }));
  var longe = Math.max.apply(null, pecas.map(function (p) { return p.prof; }));
  function apagar(prof) {                                         // 1 perto, quase 0 longe
    var f = Math.min(1, Math.max(0, (prof - perto) / (longe - perto)));
    return Math.max(0.06, 1 - Math.pow(f, 0.8) * 0.95);
  }

  var sombras = [], fila = [];
  pecas.forEach(function (pc) {
    var m = pc.m, c4 = [canto(m, 0, 0), canto(m, pc.L, 0), canto(m, pc.L, pc.A), canto(m, 0, pc.A)];
    if (!naTela(c4)) return;
    sombras.push('<g opacity="' + apagar(pc.prof).toFixed(2) + '">' +
      poli(c4.map(function (p) { return [p[0] + p[2] * SOL[0], p[1] + p[2] * SOL[1], 0]; }), "eu-sombra") + "</g>");
    for (var k = 0; k <= m.n; k += 3) {                            // os pés, na frente e atrás, a cada 3 módulos
      var x = Math.min(k, m.n) * (MOD_L + GAP);
      [canto(m, x, 0.3), canto(m, x, pc.A - 0.3)].forEach(function (topo) {
        var pr = proj(topo)[2];
        fila.push({prof: pr + 0.05, svg: '<g opacity="' + apagar(pr).toFixed(2) + '">' + lin(topo, [topo[0], topo[1], 0], "eu-pe") + "</g>"});
      });
    }
    for (var i = 0; i < m.n; i++) for (var j = 0; j < 2; j++) {
      var x0 = i * (MOD_L + GAP), a0 = j * (MOD_A + GAP);
      var q = [canto(m, x0, a0), canto(m, x0 + MOD_L, a0), canto(m, x0 + MOD_L, a0 + MOD_A), canto(m, x0, a0 + MOD_A)];
      if (!naTela(q)) continue;
      var centro = proj([m.x + x0 + MOD_L / 2, m.y + (a0 + MOD_A / 2) * Math.cos(INCL), ALT0 + (a0 + MOD_A / 2) * Math.sin(INCL)])[2];
      var op = apagar(centro), g = [poli(q, "eu-modulo")];
      var p0 = proj(q[0]), p2 = proj(q[2]);
      if (Math.hypot(p2[0] - p0[0], p2[1] - p0[1]) > 26) {        // as células (6 por 10) só no módulo grande na tela
        for (var cc = 1; cc < 6; cc++) g.push(lin(canto(m, x0 + MOD_L * cc / 6, a0), canto(m, x0 + MOD_L * cc / 6, a0 + MOD_A), "eu-celula"));
        for (var rr = 1; rr < 10; rr++) g.push(lin(canto(m, x0, a0 + MOD_A * rr / 10), canto(m, x0 + MOD_L, a0 + MOD_A * rr / 10), "eu-celula"));
      }
      if (op > 0.25) g.push(poli(q, "eu-luz", ' fill="url(#entrar-brilho)"'));
      if (op < 0.99) g.push(poli(q, "eu-nevoa", ' fill-opacity="' + (1 - op).toFixed(2) + '"'));
      fila.push({prof: centro, svg: g.join("")});
    }
  });
  fila.sort(function (a, b) { return b.prof - a.prof; });          // os de trás primeiro

  var anima = parado ? "" :
    '<animate attributeName="x1" from="-900" to="2300" dur="2.8s" begin="0.5s" fill="freeze"/>' +
    '<animate attributeName="x2" from="-500" to="2700" dur="2.8s" begin="0.5s" fill="freeze"/>';
  svg.innerHTML = '<defs><linearGradient id="entrar-brilho" gradientUnits="userSpaceOnUse" x1="' + (parado ? 3000 : -900) +
    '" y1="0" x2="' + (parado ? 3400 : -500) + '" y2="320"><stop offset="0" class="eu-brilho" stop-opacity="0"/>' +
    '<stop offset=".5" class="eu-brilho" stop-opacity=".5"/><stop offset="1" class="eu-brilho" stop-opacity="0"/>' + anima +
    "</linearGradient></defs>" + sombras.join("") + fila.map(function (it) { return it.svg; }).join("") +
    '<polygon class="eu-realce" points="0,0" visibility="hidden"/>';

  var realce = svg.querySelector(".eu-realce");
  svg.addEventListener("mouseover", function (ev) {
    var m = ev.target.closest && ev.target.closest(".eu-modulo");
    if (!m) { realce.setAttribute("visibility", "hidden"); return; }
    realce.setAttribute("points", m.getAttribute("points"));
    realce.setAttribute("visibility", "visible");
  });
  svg.addEventListener("mouseleave", function () { realce.setAttribute("visibility", "hidden"); });
})();
