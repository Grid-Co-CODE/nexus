/* O zoom do percurso no Mapa de equipe (10/11/2026).
   Levi: "No deslocamento pode mostrar o mapa inteiro primeiro, e aí a pessoa pode ir dando zoom e mostrando as cidades e
   municípios de forma leve e fluída, pode estudar como os setores fazem". O modelo é o do Mapa de risco da Performance
   (clima-mapa.js): o zoom troca só o viewBox do SVG; o texto e os pontos não crescem com ele (o CSS lê o --eq-zt = 1 /
   zoom); os botões levam a vista andando (curto no Windows com os efeitos de animação desligados: encurta, não some); a
   roda, o arrasto e os dois dedos seguem na hora.
   O que aparece em cada zoom vem do servidor (situacao.desenho_percurso): cada ponto, hora e município tem no data-n o
   nível dele, e o nível da vista sai da largura dela em km (data-km = km por unidade; data-niveis = as larguras). Nada
   aqui conhece coordenada: só o x/y do desenho. */
(function () {
  "use strict";
  var PASSO = 1.6, FOLGA = 0.18;

  function limitar(vb, base, minimo) {
    // a vista nunca passa do mapa inteiro nem fica menor que o mínimo, guarda a proporção do mapa e fica dentro dele
    var w = Math.min(base[2], Math.max(minimo, vb[2]));
    var h = w * base[3] / base[2];
    var cx = vb[0] + vb[2] / 2, cy = vb[1] + (vb[3] > 0 ? vb[3] : h) / 2;
    var x = Math.min(base[0] + base[2] - w, Math.max(base[0], cx - w / 2));
    var y = Math.min(base[1] + base[3] - h, Math.max(base[1], cy - h / 2));
    return [x, y, w, h];
  }
  function zoomEm(vb, base, minimo, px, py, fator) {
    // aproxima (fator > 1) ou afasta em volta do ponto (px, py) do desenho, que fica parado sob o mouse
    var w = Math.min(base[2], Math.max(minimo, vb[2] / fator)), k = w / vb[2];
    return limitar([px - (px - vb[0]) * k, py - (py - vb[1]) * k, w, w * base[3] / base[2]], base, minimo);
  }
  function enquadrar(caixa, base, minimo) {
    // a vista que mostra a caixa [x0, y0, x1, y1] inteira, com folga, na proporção do mapa
    var w = Math.max(minimo, (caixa[2] - caixa[0]) * (1 + 2 * FOLGA)), h = (caixa[3] - caixa[1]) * (1 + 2 * FOLGA);
    var prop = base[2] / base[3];
    if (w / h > prop) h = w / prop; else w = h * prop;
    return limitar([(caixa[0] + caixa[2]) / 2 - w / 2, (caixa[1] + caixa[3]) / 2 - h / 2, w, h], base, minimo);
  }
  function nivelDa(larguraKm, niveis) {
    // 0 = o mapa inteiro; o nível i vale quando a vista tem até niveis[i-1] km de largura
    var n = 0;
    for (var i = 0; i < niveis.length; i++) if (larguraKm <= niveis[i]) n = i + 1;
    return n;
  }
  if (typeof module !== "undefined" && module.exports) {      // as contas, para o teste no node
    module.exports = { limitar: limitar, zoomEm: zoomEm, enquadrar: enquadrar, nivelDa: nivelDa };
    return;
  }

  var REDUZIDO = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var DURACAO_MS = REDUZIDO ? 140 : 320;

  document.querySelectorAll("svg[data-eq-perc]:not([data-eq-ok])").forEach(function (s) {
    s.setAttribute("data-eq-ok", "1");
    var num = function (t) { return t.split(/[\s,]+/).map(Number); };
    var base = num(s.getAttribute("viewBox")), vb = base.slice();
    var foco = num(s.getAttribute("data-foco")), km = parseFloat(s.getAttribute("data-km")) || 1;
    var niveis = num(s.getAttribute("data-niveis")), minimo = Math.min(base[2], parseFloat(s.getAttribute("data-min")) || base[2] / 24);
    var porNivel = Array.prototype.slice.call(s.querySelectorAll("[data-n]")).map(function (el) {
      return [el, parseInt(el.getAttribute("data-n"), 10)];
    });
    var quadro = s.closest(".eq-quadro") || s.parentNode, nivel = -1, animacao = 0;
    var bt = function (z) { return quadro.querySelector('[data-eq-zoom="' + z + '"]'); };

    function aplicar(novo) {
      vb = limitar(novo, base, minimo);
      s.setAttribute("viewBox", vb.map(function (n) { return Math.round(n * 1000) / 1000; }).join(" "));
      s.style.setProperty("--eq-zt", (vb[2] / base[2]).toFixed(5));
      // o mapa estreito na tela (o painel ao lado, o celular): o texto e os pontos crescem até 2x para seguirem legíveis
      var largura = s.getBoundingClientRect().width || 900;
      s.style.setProperty("--eq-k", Math.min(2, Math.max(1, 900 / largura)).toFixed(3));
      var n = nivelDa(vb[2] * km, niveis);
      if (n !== nivel) {
        nivel = n;
        porNivel.forEach(function (p) { p[0].style.display = p[1] <= n ? "inline" : "none"; });
      }
      var inteiro = vb[2] >= base[2] - 1e-6;
      if (bt("menos")) bt("menos").disabled = inteiro;
      if (bt("inteiro")) bt("inteiro").disabled = inteiro;
      if (bt("mais")) bt("mais").disabled = vb[2] <= minimo + 1e-6;
    }
    function parar() { if (animacao) { cancelAnimationFrame(animacao); animacao = 0; } }
    function irPara(novo) {
      parar();
      var alvo = limitar(novo, base, minimo), de = vb.slice(), t0 = null;
      function passo(t) {
        if (t0 === null) t0 = t;
        var k = Math.min(1, (t - t0) / DURACAO_MS), e = 1 - Math.pow(1 - k, 3);          // sai rápido e assenta
        // a largura anda em proporção (o zoom é multiplicativo): de 4.000 km a 20 km em passos iguais para o olho
        var w = de[2] * Math.pow(alvo[2] / de[2], e), f = de[2] === alvo[2] ? e : (w - de[2]) / (alvo[2] - de[2]);
        aplicar([de[0] + (alvo[0] - de[0]) * f, de[1] + (alvo[1] - de[1]) * f, w, w * base[3] / base[2]]);
        animacao = k < 1 ? requestAnimationFrame(passo) : 0;
      }
      animacao = requestAnimationFrame(passo);
    }
    function noDesenho(clientX, clientY) {
      var m = s.getScreenCTM();
      if (!m) return [vb[0] + vb[2] / 2, vb[1] + vb[3] / 2];
      var p = new DOMPoint(clientX, clientY).matrixTransform(m.inverse());
      return [p.x, p.y];
    }
    function meio() { return [vb[0] + vb[2] / 2, vb[1] + vb[3] / 2]; }

    quadro.addEventListener("click", function (e) {
      var b = e.target.closest("[data-eq-zoom]");
      if (!b) return;
      var z = b.getAttribute("data-eq-zoom"), c = meio();
      if (z === "mais") irPara(zoomEm(vb, base, minimo, c[0], c[1], PASSO));
      else if (z === "menos") irPara(zoomEm(vb, base, minimo, c[0], c[1], 1 / PASSO));
      else if (z === "percurso") irPara(enquadrar(foco, base, minimo));
      else if (z === "inteiro") irPara(base);
    });
    s.addEventListener("wheel", function (e) {
      e.preventDefault();
      parar();
      var p = noDesenho(e.clientX, e.clientY), unidade = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1;
      aplicar(zoomEm(vb, base, minimo, p[0], p[1], Math.exp(-e.deltaY * unidade * 0.0018)));
    }, { passive: false });
    // o arrasto (um dedo ou o mouse) anda; dois dedos aproximam em volta do meio deles
    var dedos = {}, arrasto = null, pinca = null;
    function distancia(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }
    s.addEventListener("pointerdown", function (e) {
      dedos[e.pointerId] = { x: e.clientX, y: e.clientY };
      parar();
      var ids = Object.keys(dedos), m = s.getScreenCTM();
      if (ids.length === 1) arrasto = { x: e.clientX, y: e.clientY, vb: vb.slice(), escala: m ? m.a : 1 };
      else if (ids.length === 2) { arrasto = null; pinca = { d: distancia(dedos[ids[0]], dedos[ids[1]]), vb: vb.slice() }; }
      try { s.setPointerCapture(e.pointerId); } catch (x) { /* o navegador sem captura: o arrasto para na borda */ }
    });
    s.addEventListener("pointermove", function (e) {
      if (!dedos[e.pointerId]) return;
      dedos[e.pointerId] = { x: e.clientX, y: e.clientY };
      var ids = Object.keys(dedos);
      if (pinca && ids.length >= 2) {
        var a = dedos[ids[0]], b = dedos[ids[1]], d = distancia(a, b);
        if (d > 0 && pinca.d > 0) {
          var c = noDesenho((a.x + b.x) / 2, (a.y + b.y) / 2);
          aplicar(zoomEm(pinca.vb, base, minimo, c[0], c[1], d / pinca.d));
        }
      } else if (arrasto) {
        var dx = e.clientX - arrasto.x, dy = e.clientY - arrasto.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) s.classList.add("eq-arrastando");
        aplicar([arrasto.vb[0] - dx / arrasto.escala, arrasto.vb[1] - dy / arrasto.escala, arrasto.vb[2], arrasto.vb[3]]);
      }
    });
    function soltar(e) {
      delete dedos[e.pointerId];
      pinca = null;
      var ids = Object.keys(dedos), m = s.getScreenCTM();
      arrasto = ids.length === 1 ? { x: dedos[ids[0]].x, y: dedos[ids[0]].y, vb: vb.slice(), escala: m ? m.a : 1 } : null;
      if (!ids.length) s.classList.remove("eq-arrastando");
    }
    s.addEventListener("pointerup", soltar);
    s.addEventListener("pointercancel", soltar);
    s.setAttribute("tabindex", "0");
    s.addEventListener("keydown", function (e) {
      var c = meio(), passo = vb[2] * 0.15;
      if (e.key === "+" || e.key === "=") irPara(zoomEm(vb, base, minimo, c[0], c[1], PASSO));
      else if (e.key === "-" || e.key === "_") irPara(zoomEm(vb, base, minimo, c[0], c[1], 1 / PASSO));
      else if (e.key === "ArrowLeft") aplicar([vb[0] - passo, vb[1], vb[2], vb[3]]);
      else if (e.key === "ArrowRight") aplicar([vb[0] + passo, vb[1], vb[2], vb[3]]);
      else if (e.key === "ArrowUp") aplicar([vb[0], vb[1] - passo, vb[2], vb[3]]);
      else if (e.key === "ArrowDown") aplicar([vb[0], vb[1] + passo, vb[2], vb[3]]);
      else return;
      e.preventDefault();
    });
    aplicar(base);                                              // o mapa inteiro primeiro
  });
})();
