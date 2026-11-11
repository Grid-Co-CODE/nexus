/* O zoom do Mapa de equipe (10/11/2026 no percurso; 11/11/2026 também no mapa dos técnicos e no das usinas).
   Levi: "No deslocamento pode mostrar o mapa inteiro primeiro, e aí a pessoa pode ir dando zoom e mostrando as cidades e
   municípios de forma leve e fluída, pode estudar como os setores fazem". O modelo é o do Mapa de risco da Performance
   (clima-mapa.js): o zoom troca só o viewBox do SVG; os botões levam a vista andando (curto no Windows com os efeitos
   de animação desligados: encurta, não some); a roda, o arrasto e os dois dedos seguem na hora.
   A vista tem a proporção do CARTÃO, não a do desenho (Levi, 11/11/2026: "mesmo eu dando um zoom os municípios ficam bem
   pequenos, tem que ser responsivo!"): o desenho é mais alto que largo e o cartão é largo, então a escala de verdade
   saía da altura e os 14 px do texto viravam 7 na tela. O script mede o palco e diz ao CSS, no --eq-un, quantas unidades
   do desenho valem um pixel da tela: o texto e os pontos têm o tamanho certo em qualquer zoom e em qualquer tela.
   O que aparece em cada zoom vem do servidor (situacao.desenho_percurso): cada ponto, hora e município tem no data-n o
   nível dele, e o nível da vista sai da largura dela em km (data-km = km por unidade; data-niveis = as larguras). Nada
   aqui conhece coordenada: só o x/y do desenho. */
(function () {
  "use strict";
  var PASSO = 1.6, FOLGA = 0.18;

  function larguraInteira(base, prop) {
    // a largura da vista que mostra o mapa inteiro num cartão de proporção `prop` (largura / altura)
    return Math.max(base[2], base[3] * prop);
  }
  function limitar(vb, base, minimo, prop) {
    // a vista nunca passa do mapa inteiro nem fica menor que o mínimo, tem a proporção do cartão (sem ela, a do mapa) e
    // fica dentro do mapa; no lado em que ela é maior que o mapa, o mapa fica no meio
    prop = prop || base[2] / base[3];
    var w = Math.min(larguraInteira(base, prop), Math.max(minimo, vb[2])), h = w / prop;
    var cx = vb[0] + vb[2] / 2, cy = vb[1] + (vb[3] > 0 ? vb[3] : h) / 2;
    var x = w >= base[2] ? base[0] + (base[2] - w) / 2 : Math.min(base[0] + base[2] - w, Math.max(base[0], cx - w / 2));
    var y = h >= base[3] ? base[1] + (base[3] - h) / 2 : Math.min(base[1] + base[3] - h, Math.max(base[1], cy - h / 2));
    return [x, y, w, h];
  }
  function zoomEm(vb, base, minimo, px, py, fator, prop) {
    // aproxima (fator > 1) ou afasta em volta do ponto (px, py) do desenho, que fica parado sob o mouse
    prop = prop || base[2] / base[3];
    var w = Math.min(larguraInteira(base, prop), Math.max(minimo, vb[2] / fator)), k = w / vb[2];
    return limitar([px - (px - vb[0]) * k, py - (py - vb[1]) * k, w, w / prop], base, minimo, prop);
  }
  function enquadrar(caixa, base, minimo, prop) {
    // a vista que mostra a caixa [x0, y0, x1, y1] inteira, com folga, na proporção do cartão
    prop = prop || base[2] / base[3];
    var w = Math.max(minimo, (caixa[2] - caixa[0]) * (1 + 2 * FOLGA)), h = (caixa[3] - caixa[1]) * (1 + 2 * FOLGA);
    if (w / h > prop) h = w / prop; else w = h * prop;
    return limitar([(caixa[0] + caixa[2]) / 2 - w / 2, (caixa[1] + caixa[3]) / 2 - h / 2, w, h], base, minimo, prop);
  }
  function nivelDa(larguraKm, niveis) {
    // 0 = o mapa inteiro; o nível i vale quando a vista tem até niveis[i-1] km de largura
    var n = 0;
    for (var i = 0; i < niveis.length; i++) if (larguraKm <= niveis[i]) n = i + 1;
    return n;
  }
  if (typeof module !== "undefined" && module.exports) {      // as contas, para o teste no node
    module.exports = { limitar: limitar, zoomEm: zoomEm, enquadrar: enquadrar, nivelDa: nivelDa,
                       larguraInteira: larguraInteira };
    return;
  }

  var REDUZIDO = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var DURACAO_MS = REDUZIDO ? 140 : 320;

  document.querySelectorAll("svg[data-eq-perc]:not([data-eq-ok]),svg[data-eq-mapa]:not([data-eq-ok])").forEach(function (s) {
    s.setAttribute("data-eq-ok", "1");
    var num = function (t) { return t.split(/[\s,]+/).map(Number); };
    var base = num(s.getAttribute("viewBox")), vb = base.slice();
    var focoTexto = s.getAttribute("data-foco"), foco = focoTexto ? num(focoTexto) : null;
    var km = parseFloat(s.getAttribute("data-km")) || 1;
    var niveisTexto = s.getAttribute("data-niveis"), niveis = niveisTexto ? num(niveisTexto) : [];
    var minimo = Math.min(base[2], parseFloat(s.getAttribute("data-min")) || base[2] / 24);
    var porNivel = Array.prototype.slice.call(s.querySelectorAll("[data-n]")).map(function (el) {
      return [el, parseInt(el.getAttribute("data-n"), 10)];
    });
    // os textos do desenho, do mais importante ao menos: a hora, o município do percurso, a sigla do estado e o
    // município vizinho. O que encosta num texto mais importante já escrito sai da frente (`arrumar`)
    var textos = [];
    [".eq-perc-horas text", ".eq-mun-nomes .eq-mun-rota", ".eq-siglas text", ".eq-mun-nomes text:not(.eq-mun-rota)"]
      .forEach(function (seletor) { Array.prototype.push.apply(textos, s.querySelectorAll(seletor)); });
    var arrumando = 0;
    var quadro = s.closest(".eq-quadro") || s.parentNode, palco = s.parentNode;
    var brilho = quadro.querySelector("svg.eq-brilho"), nivel = -1, animacao = 0;
    var largura = 900, prop = base[2] / base[3];
    var bt = function (z) { return quadro.querySelector('[data-eq-zoom="' + z + '"]'); };

    function medir() {
      // o tamanho do desenho NA TELA (o palco é um bloco comum: a medida vale em todo navegador)
      var w = palco.clientWidth, h = palco.clientHeight;
      if (w > 0 && h > 0) { largura = w; prop = w / h; }
    }
    function inteira() { return limitar([base[0], base[1], 1e9, 0], base, minimo, prop); }
    function noInteiro() { return vb[2] >= larguraInteira(base, prop) - 1e-6; }
    function aplicar(novo) {
      vb = limitar(novo, base, minimo, prop);
      var texto = vb.map(function (n) { return Math.round(n * 1000) / 1000; }).join(" ");
      s.setAttribute("viewBox", texto);
      if (brilho) brilho.setAttribute("viewBox", texto);
      // quantas unidades do desenho valem um pixel da tela: o texto e os pontos são escritos em pixels dela
      s.style.setProperty("--eq-un", (vb[2] / largura).toFixed(5));
      var n = nivelDa(vb[2] * km, niveis);
      if (n !== nivel) {
        nivel = n;
        porNivel.forEach(function (p) { p[0].style.display = p[1] <= n ? "inline" : "none"; });
      }
      if (textos.length > 1) { clearTimeout(arrumando); arrumando = setTimeout(arrumar, 90); }
      var todo = noInteiro();
      if (bt("menos")) bt("menos").disabled = todo;
      if (bt("inteiro")) bt("inteiro").disabled = todo;
      if (bt("mais")) bt("mais").disabled = vb[2] <= minimo + 1e-6;
    }
    function arrumar() {
      // com o texto em pixels da tela (11/11/2026), dois nomes vizinhos podem cair um em cima do outro: fica o mais
      // importante, e o outro some até a vista mudar. Roda quando a vista assenta, não a cada quadro do zoom
      arrumando = 0;
      var area = palco.getBoundingClientRect(), postos = [];
      textos.forEach(function (t) { t.style.visibility = ""; });
      textos.forEach(function (t) {
        if (t.style.display === "none") return;                  // fora do nível de zoom
        var r = t.getBoundingClientRect();
        if (!r.width || r.right < area.left || r.left > area.right || r.bottom < area.top || r.top > area.bottom) return;
        for (var i = 0; i < postos.length; i++) {
          var o = postos[i];
          if (r.left < o.right + 4 && r.right > o.left - 4 && r.top < o.bottom + 2 && r.bottom > o.top - 2) {
            t.style.visibility = "hidden";
            return;
          }
        }
        postos.push(r);
      });
    }
    function parar() { if (animacao) { cancelAnimationFrame(animacao); animacao = 0; } }
    function irPara(novo) {
      parar();
      var alvo = limitar(novo, base, minimo, prop), de = vb.slice(), t0 = null;
      function passo(t) {
        if (t0 === null) t0 = t;
        var k = Math.min(1, (t - t0) / DURACAO_MS), e = 1 - Math.pow(1 - k, 3);          // sai rápido e assenta
        // a largura anda em proporção (o zoom é multiplicativo): de 4.000 km a 20 km em passos iguais para o olho
        var w = de[2] * Math.pow(alvo[2] / de[2], e), f = de[2] === alvo[2] ? e : (w - de[2]) / (alvo[2] - de[2]);
        aplicar([de[0] + (alvo[0] - de[0]) * f, de[1] + (alvo[1] - de[1]) * f, w, w / prop]);
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
    function zoom(px, py, fator) { return zoomEm(vb, base, minimo, px, py, fator, prop); }

    quadro.addEventListener("click", function (e) {
      var b = e.target.closest("[data-eq-zoom]");
      if (!b) return;
      var z = b.getAttribute("data-eq-zoom"), c = meio();
      if (z === "mais") irPara(zoom(c[0], c[1], PASSO));
      else if (z === "menos") irPara(zoom(c[0], c[1], 1 / PASSO));
      else if (z === "percurso" && foco) irPara(enquadrar(foco, base, minimo, prop));
      else if (z === "inteiro") irPara(inteira());
    });
    s.addEventListener("wheel", function (e) {
      // no mapa inteiro, a roda para baixo não tem o que afastar: a página rola (o cartão ocupa quase a janela toda)
      if (e.deltaY > 0 && noInteiro()) return;
      e.preventDefault();
      parar();
      var p = noDesenho(e.clientX, e.clientY), unidade = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1;
      aplicar(zoom(p[0], p[1], Math.exp(-e.deltaY * unidade * 0.0018)));
    }, { passive: false });
    // o arrasto (um dedo ou o mouse) anda; dois dedos aproximam em volta do meio deles. O ponteiro só é preso depois de
    // andar 3 px: o clique simples no ponto do técnico (um link) continua sendo clique, e o que foi arrasto não abre nada
    var dedos = {}, arrasto = null, pinca = null, arrastou = false;
    function distancia(a, b) { return Math.hypot(a.x - b.x, a.y - b.y); }
    function novoArrasto(x, y) { return { x: x, y: y, vb: vb.slice(), escala: largura / vb[2], preso: false }; }
    s.addEventListener("pointerdown", function (e) {
      dedos[e.pointerId] = { x: e.clientX, y: e.clientY };
      parar();
      arrastou = false;
      var ids = Object.keys(dedos);
      if (ids.length === 1) arrasto = novoArrasto(e.clientX, e.clientY);
      else if (ids.length === 2) { arrasto = null; pinca = { d: distancia(dedos[ids[0]], dedos[ids[1]]), vb: vb.slice() }; }
    });
    s.addEventListener("pointermove", function (e) {
      if (!dedos[e.pointerId]) return;
      dedos[e.pointerId] = { x: e.clientX, y: e.clientY };
      var ids = Object.keys(dedos);
      if (pinca && ids.length >= 2) {
        var a = dedos[ids[0]], b = dedos[ids[1]], d = distancia(a, b);
        arrastou = true;
        if (d > 0 && pinca.d > 0) {
          var c = noDesenho((a.x + b.x) / 2, (a.y + b.y) / 2);
          aplicar(zoomEm(pinca.vb, base, minimo, c[0], c[1], d / pinca.d, prop));
        }
      } else if (arrasto) {
        var dx = e.clientX - arrasto.x, dy = e.clientY - arrasto.y;
        if (!arrasto.preso && Math.abs(dx) + Math.abs(dy) <= 3) return;
        if (!arrasto.preso) {
          arrasto.preso = arrastou = true;
          s.classList.add("eq-arrastando");
          try { s.setPointerCapture(e.pointerId); } catch (x) { /* o navegador sem captura: o arrasto para na borda */ }
        }
        aplicar([arrasto.vb[0] - dx / arrasto.escala, arrasto.vb[1] - dy / arrasto.escala, arrasto.vb[2], arrasto.vb[3]]);
      }
    });
    function soltar(e) {
      delete dedos[e.pointerId];
      pinca = null;
      var ids = Object.keys(dedos);
      arrasto = ids.length === 1 ? novoArrasto(dedos[ids[0]].x, dedos[ids[0]].y) : null;
      if (!ids.length) s.classList.remove("eq-arrastando");
    }
    s.addEventListener("pointerup", soltar);
    s.addEventListener("pointercancel", soltar);
    s.addEventListener("click", function (e) {
      if (!arrastou) return;
      arrastou = false;
      e.preventDefault();
      e.stopPropagation();
    }, true);
    s.setAttribute("tabindex", "0");
    s.addEventListener("keydown", function (e) {
      var c = meio(), passo = vb[2] * 0.15;
      if (e.key === "+" || e.key === "=") irPara(zoom(c[0], c[1], PASSO));
      else if (e.key === "-" || e.key === "_") irPara(zoom(c[0], c[1], 1 / PASSO));
      else if (e.key === "ArrowLeft") aplicar([vb[0] - passo, vb[1], vb[2], vb[3]]);
      else if (e.key === "ArrowRight") aplicar([vb[0] + passo, vb[1], vb[2], vb[3]]);
      else if (e.key === "ArrowUp") aplicar([vb[0], vb[1] - passo, vb[2], vb[3]]);
      else if (e.key === "ArrowDown") aplicar([vb[0], vb[1] + passo, vb[2], vb[3]]);
      else return;
      e.preventDefault();
    });
    medir();
    aplicar(inteira());                                         // o mapa inteiro primeiro
    // o cartão mudou de tamanho (a janela, o menu recolhido, o painel do clima): a vista segue a proporção nova
    if (window.ResizeObserver) {
      new ResizeObserver(function () {
        var todo = noInteiro(), c = meio(), w = vb[2];
        medir();
        aplicar(todo ? inteira() : [c[0] - w / 2, c[1] - w / prop / 2, w, w / prop]);
      }).observe(palco);
    }
  });
})();
