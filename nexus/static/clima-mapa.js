/* Mapa de risco (nexus/performance/clima/mapa.py, templates/performance/mapa.html e mapa_tv.html), 09/10/2026.

   Levi: "Quero o mapa mais interativo" (zoom e arraste, dica, clique na usina destaca a tabela e vice-versa, clique no estado
   aproxima, busca, teclado) e "visão de tela cheia para colocar no video wall" (Tela cheia e o modo TV, ?tv=1).
   Este arquivo só ENFEITA o que o servidor desenhou: sem ele, o mapa é o SVG do servidor, os controles são links e a página se
   recarrega sozinha. Com ele:
   - o zoom troca só o viewBox (nada anima: o Windows do Levi usa movimento reduzido);
   - a página relê o mapa no ritmo dos caches das fontes (data-proxima-s, que o servidor calcula), nunca antes, e troca só os
     pedaços marcados com data-parte, sem perder o zoom; se a sessão cai ou o Nexus não responde, a tela DIZ isso e esmaece o
     mapa com um véu, em vez de deixar dado velho parecendo novo;
   - texto que veio de fora (nome de usina, evento do INMET) entra por textContent, nunca como HTML.
   As contas (zoom, limites, espera, falha, linhas que cabem, busca) ficam em MapaRisco e o teste as roda no node. */
(function (raiz) {
  "use strict";

  var ZOOM_MAX = 24;                 // até 24 vezes o recorte do servidor (o contorno do IBGE é o "mínimo": mais que isso só pixela)
  var PASSO_ZOOM = 1.6;              // um clique em + ou -, ou uma tecla
  var EXPOENTE_PONTO = 0.8;          // o ponto da usina cresce devagar com o zoom: 8x de zoom, 1,5x de ponto
  var MIN_S = 10, MAX_S = 1800, FALHA_S = 60;

  function limitar(vb, base) {
    // o recorte nunca passa do recorte do servidor (zoom >= 1) nem de ZOOM_MAX, guarda a proporção do mapa e fica dentro dele;
    // o centro pedido é mantido enquanto cabe
    var w = Math.min(base[2], Math.max(base[2] / ZOOM_MAX, vb[2]));
    var h = w * base[3] / base[2];
    var cx = vb[0] + vb[2] / 2, cy = vb[1] + (vb[3] > 0 ? vb[3] : h) / 2;
    var x = Math.min(base[0] + base[2] - w, Math.max(base[0], cx - w / 2));
    var y = Math.min(base[1] + base[3] - h, Math.max(base[1], cy - h / 2));
    return [x, y, w, h];
  }

  function zoomEm(vb, base, px, py, fator) {
    // aproxima (fator > 1) ou afasta em volta do ponto (px, py) do desenho, que fica parado sob o mouse
    var w = vb[2] / fator, h = vb[3] / fator;
    var w2 = Math.min(base[2], Math.max(base[2] / ZOOM_MAX, w));
    var k = w2 / vb[2];
    var novo = [px - (px - vb[0]) * k, py - (py - vb[1]) * k, w2, w2 * base[3] / base[2]];
    return limitar(novo, base);
  }

  function enquadrar(caixa, base, folga) {
    // o recorte que mostra a caixa [x0, y0, x1, y1] inteira, com folga, na proporção do mapa
    folga = folga === undefined ? 0.12 : folga;
    var w = (caixa[2] - caixa[0]) * (1 + 2 * folga), h = (caixa[3] - caixa[1]) * (1 + 2 * folga);
    var prop = base[2] / base[3];
    if (w / h > prop) h = w / prop; else w = h * prop;
    var cx = (caixa[0] + caixa[2]) / 2, cy = (caixa[1] + caixa[3]) / 2;
    return limitar([cx - w / 2, cy - h / 2, w, h], base);
  }

  function proximaEspera(proximaS, falhou) {
    // quanto esperar para reler: o que o servidor disse (o vencimento do primeiro cache), entre 10 s e 30 min; 60 s depois de falha
    if (falhou) return FALHA_S;
    var s = parseInt(proximaS, 10);
    if (!isFinite(s)) s = 60;
    return Math.min(MAX_S, Math.max(MIN_S, s));
  }

  function motivoDaFalha(r) {
    // r: {tipo, status, temMapa}. "sessao": o portão mandou para o Entrar (redirecionamento, ou a página de entrar no lugar do
    // mapa); "http": o Nexus respondeu com erro; null: deu certo
    if (r.tipo === "opaqueredirect" || r.status === 401 || r.status === 403) return "sessao";
    if (!(r.status >= 200 && r.status < 300)) return "http";
    if (!r.temMapa) return "sessao";
    return null;
  }

  function quantasCabem(alturas, disponivel, alturaDoMais) {
    // quantas linhas da tabela cabem em `disponivel` (o modo TV não rola): se não cabem todas, sobra lugar para "e mais N"
    var soma = 0, i;
    for (i = 0; i < alturas.length; i++) soma += alturas[i];
    if (soma <= disponivel) return alturas.length;
    soma = 0;
    for (i = 0; i < alturas.length; i++) {
      if (soma + alturas[i] > disponivel - (alturaDoMais || 0)) return i;
      soma += alturas[i];
    }
    return alturas.length;
  }

  function normalizar(s) {
    return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
  }

  function acharUsina(usinas, texto) {
    // pelo nome: o igual, depois o que começa com o texto, depois o que o contém (sem acento e sem caixa)
    var alvo = normalizar(texto);
    if (!alvo) return null;
    var ids = Object.keys(usinas || {}), i, nome;
    for (i = 0; i < ids.length; i++) if (normalizar(usinas[ids[i]].n) === alvo) return ids[i];
    for (i = 0; i < ids.length; i++) { nome = normalizar(usinas[ids[i]].n); if (nome.indexOf(alvo) === 0) return ids[i]; }
    for (i = 0; i < ids.length; i++) { nome = normalizar(usinas[ids[i]].n); if (nome.indexOf(alvo) >= 0) return ids[i]; }
    return null;
  }

  function hhmm(d) {
    return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
  }

  raiz.MapaRisco = { limitar: limitar, zoomEm: zoomEm, enquadrar: enquadrar, proximaEspera: proximaEspera,
                     motivoDaFalha: motivoDaFalha, quantasCabem: quantasCabem, acharUsina: acharUsina, normalizar: normalizar,
                     ZOOM_MAX: ZOOM_MAX, MIN_S: MIN_S, MAX_S: MAX_S, FALHA_S: FALHA_S };
  if (typeof document === "undefined") return;          // no node (o teste), só as contas

  var mapa = document.querySelector("[data-mapa]");
  if (!mapa) return;
  var TV = mapa.hasAttribute("data-tv");
  var base = null, vb = null, historico = [], selecionada = null, dados = {}, ultimoOk = new Date();
  var timer = null, carregando = null, arrasto = null, arrastou = false, ultimoTipo = "mouse", rodaAte = 0, quadro = 0;
  var giroTimer = null, giroFalta = 0, controlesTimer = null, falhaAtual = null;

  function svg() { return mapa.querySelector(".mp-svg"); }
  function figura() { return mapa.querySelector(".mp-mapa"); }
  function dica() { return mapa.querySelector(".mp-dica"); }
  function lerVB(el) { return el.getAttribute("viewBox").split(/[\s,]+/).map(Number); }

  function lerDados() {
    var el = document.getElementById("mp-dados");
    try { dados = el ? JSON.parse(el.textContent) : {}; } catch (e) { dados = {}; }
  }

  // ── o desenho: o viewBox e o tamanho dos pontos ───────────────────────────────────────────────────────────────────────
  function aplicar(novo, guardar) {
    var s = svg();
    if (!s || !base) return;
    if (guardar && vb) {
      historico.push(vb.slice());
      if (historico.length > 50) historico.shift();
    }
    vb = limitar(novo, base);
    s.setAttribute("viewBox", vb.map(function (n) { return Math.round(n * 10) / 10; }).join(" "));
    var z = base[2] / vb[2];
    // o texto e os pontos não crescem com o zoom (o CSS lê estes dois): a sigla fica do tamanho de sempre, o ponto cresce devagar
    s.style.setProperty("--mp-zt", (1 / z).toFixed(4));
    s.style.setProperty("--mp-zp", Math.pow(1 / z, EXPOENTE_PONTO).toFixed(4));
    // No computador, o mapa entre a legenda e a tabela pode ter só ~390 px (a 1440 px de tela), e o ponto da usina, que é medido no
    // desenho de 1000 unidades, ficava com 2 px: cresce até 1,8x quando o mapa é estreito. Celular e modo TV seguem o CSS deles.
    if (!TV && window.innerWidth > 820) {
      var largura = s.getBoundingClientRect().width || 700;
      s.style.setProperty("--mp-k", Math.min(1.8, Math.max(1, 640 / largura)).toFixed(3));
    }
    var voltar = mapa.querySelector('[data-zoom="voltar"]');
    if (voltar) voltar.disabled = historico.length === 0;
    desenharSelecao();
  }

  function pontoDoDesenho(clientX, clientY) {
    var s = svg(), m = s && s.getScreenCTM();
    if (!m) return null;
    var p = new DOMPoint(clientX, clientY).matrixTransform(m.inverse());
    return [p.x, p.y];
  }

  function zoomBotao(fator) {
    if (!vb) return;
    aplicar(zoomEm(vb, base, vb[0] + vb[2] / 2, vb[1] + vb[3] / 2, fator), true);
  }

  function voltar() {
    if (!historico.length) return;
    vb = historico.pop();
    aplicar(vb, false);
  }

  function iniciarDesenho(preservar) {
    var s = svg();
    if (!s) return;
    var novoBase = lerVB(s);
    var mesmo = base && novoBase.join(" ") === base.join(" ");
    base = novoBase;
    if (preservar && mesmo && vb) {
      aplicar(vb, false);
    } else {
      historico = [];
      vb = base.slice();
      aplicar(vb, false);
    }
    prepararTitulos(s);
  }

  function prepararTitulos(s) {
    // o <title> do SVG é o balão do navegador (e a dica sem JavaScript); com a dica daqui, ele viraria um segundo balão por cima.
    // O texto vai para o aria-label (o leitor de tela continua lendo) e para data-dica (a dica do aviso).
    s.querySelectorAll(".mp-usinas a").forEach(function (a) {
      var t = a.querySelector("title");
      if (t) { a.setAttribute("aria-label", t.textContent.replace(/\n/g, ". ")); t.remove(); }
    });
    s.querySelectorAll(".mp-avisos path").forEach(function (p) {
      var t = p.querySelector("title");
      if (t) { p.setAttribute("data-dica", t.textContent); t.remove(); }
    });
  }

  // ── a usina escolhida: o aro no mapa e a linha da tabela ──────────────────────────────────────────────────────────────
  function idDoHref(href) {
    var partes = String(href || "").split("/usina/");
    return partes.length > 1 ? decodeURIComponent(partes[1].split(/[?#]/)[0]) : null;
  }

  function linkDaUsina(id) {
    var achado = null;
    mapa.querySelectorAll(".mp-usinas a").forEach(function (a) { if (idDoHref(a.getAttribute("href")) === id) achado = a; });
    return achado;
  }

  function linhaDaUsina(id) {
    var achada = null;
    mapa.querySelectorAll(".mp-tab-lin").forEach(function (tr) {
      var a = tr.querySelector("a.cl-link");
      if (a && idDoHref(a.getAttribute("href")) === id) achada = tr;
    });
    return achada;
  }

  function desenharSelecao() {
    var s = svg(), g = s && s.querySelector(".mp-selecao");
    if (!g) return;
    while (g.firstChild) g.removeChild(g.firstChild);
    if (!selecionada) return;
    var a = linkDaUsina(selecionada), ponto = a && a.querySelector(".mp-ponto");
    if (!ponto) return;
    var c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("class", "mp-sel mp-anel-sel");
    c.setAttribute("cx", ponto.getAttribute("cx"));
    c.setAttribute("cy", ponto.getAttribute("cy"));
    c.setAttribute("r", String(parseFloat(ponto.getAttribute("r")) * 2));
    g.appendChild(c);
  }

  function rolarTabelaAte(tr) {
    var caixa = tr && tr.closest(".mp-tab-rolagem");
    if (!caixa) return;
    var topo = tr.offsetTop, fim = topo + tr.offsetHeight;
    var cab = caixa.querySelector("thead");
    var h = cab ? cab.offsetHeight : 0;
    if (topo - h < caixa.scrollTop) caixa.scrollTop = topo - h - 4;
    else if (fim > caixa.scrollTop + caixa.clientHeight) caixa.scrollTop = fim - caixa.clientHeight + 4;
  }

  function selecionar(id, opcoes) {
    opcoes = opcoes || {};
    selecionada = id;
    mapa.querySelectorAll(".mp-tab--sel").forEach(function (tr) { tr.classList.remove("mp-tab--sel"); });
    var tr = id && linhaDaUsina(id);
    if (tr) { tr.classList.add("mp-tab--sel"); rolarTabelaAte(tr); }
    desenharSelecao();
    var a = id && linkDaUsina(id);
    if (a && (opcoes.centralizar || opcoes.zoom)) {
      var p = a.querySelector(".mp-ponto");
      var x = parseFloat(p.getAttribute("cx")), y = parseFloat(p.getAttribute("cy"));
      var dentro = x > vb[0] && x < vb[0] + vb[2] && y > vb[1] && y < vb[1] + vb[3];
      if (opcoes.zoom) {
        var w = Math.min(vb[2], base[2] / 6);
        aplicar([x - w / 2, y - w * base[3] / base[2] / 2, w, w * base[3] / base[2]], true);
      } else if (!dentro) {
        aplicar([x - vb[2] / 2, y - vb[3] / 2, vb[2], vb[3]], true);
      }
    }
    // a dica não fica presa em cima do mapa (a 1440 px o mapa tem ~390 px e ela cobria metade dele): a marca é o aro no mapa e a linha
    // da tabela; o nome na linha abre a página da usina, e o segundo clique no ponto também
    esconderDica(true);
  }

  // ── a dica ────────────────────────────────────────────────────────────────────────────────────────────────────────────
  function el(tag, classe, texto) {
    var e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto !== undefined && texto !== null) e.textContent = texto;
    return e;
  }

  function posicionar(d, x, y) {
    var f = figura(), r = f.getBoundingClientRect();
    d.hidden = false;
    var w = d.offsetWidth, h = d.offsetHeight;
    var esq = x - r.left + 16, cima = y - r.top + 16;
    if (esq + w > r.width - 6) esq = Math.max(6, x - r.left - w - 16);
    if (cima + h > r.height - 6) cima = Math.max(6, y - r.top - h - 16);
    d.style.left = esq + "px";
    d.style.top = cima + "px";
  }

  function mostrarDicaDaUsina(a, evento, fixa) {
    var d = dica();
    if (!d) return;
    var id = idDoHref(a.getAttribute("href")), u = (dados.usinas || {})[id];
    if (!u) return;
    d.textContent = "";
    d.appendChild(el("strong", "mp-dica-nome", u.n));
    d.appendChild(el("span", "mp-dica-onde", u.o));
    var nivel = el("span", "mp-dica-nivel");
    nivel.appendChild(el("span", "mp-chave mp-n-" + u.v));
    nivel.appendChild(document.createTextNode(u.r));
    d.appendChild(nivel);
    d.appendChild(el("span", "mp-dica-motivo", u.m));
    if (u.f && u.f.length) {
      d.appendChild(el("span", "mp-dica-h", "O que pesou"));
      var ul = el("ul");
      u.f.forEach(function (par) {
        var li = el("li");
        if (par[0]) { li.appendChild(el("span", "mp-dica-fonte", par[0])); li.appendChild(document.createTextNode(": ")); }
        li.appendChild(document.createTextNode(par[1]));
        ul.appendChild(li);
      });
      d.appendChild(ul);
    }
    if (fixa) {
      var abrir = el("a", null, "Abrir a página da usina");
      abrir.href = a.getAttribute("href");
      var p = el("span", "mp-dica-acao");
      p.appendChild(abrir);
      d.appendChild(p);
    } else if (!TV) {
      d.appendChild(el("span", "mp-dica-acao", "Clique para marcar na tabela; outro clique abre a página da usina."));
    }
    d.classList.toggle("mp-dica--fixa", !!fixa);
    var box = a.querySelector(".mp-ponto").getBoundingClientRect();
    posicionar(d, evento ? evento.clientX : box.right, evento ? evento.clientY : box.bottom);
  }

  function ufNoPonto(x, y) {
    var pilha = document.elementsFromPoint ? document.elementsFromPoint(x, y) : [];
    for (var i = 0; i < pilha.length; i++) {
      if (pilha[i].classList && pilha[i].classList.contains("mp-uf")) return pilha[i].getAttribute("data-uf");
    }
    return null;
  }

  function nomeDaUf(uf) {
    var info = (dados.ufs || {})[uf];
    return info ? info.nome + " (" + uf + ")" : uf;
  }

  function mostrarDicaSimples(linhas, x, y) {
    var d = dica();
    if (!d || d.classList.contains("mp-dica--fixa")) return;
    d.textContent = "";
    linhas.forEach(function (l, i) { d.appendChild(el(i === 0 ? "strong" : "span", i === 0 ? "mp-dica-nome" : "mp-dica-uf", l)); });
    posicionar(d, x, y);
  }

  function esconderDica(tambemFixa) {
    var d = dica();
    if (!d) return;
    if (d.classList.contains("mp-dica--fixa") && !tambemFixa) return;
    d.hidden = true;
    d.classList.remove("mp-dica--fixa");
  }

  function dicaNoPonto(e) {
    var alvo = e.target, s = svg();
    if (!s || arrasto) return;
    var a = alvo.closest && alvo.closest(".mp-usinas a");
    if (a) { if (!dica().classList.contains("mp-dica--fixa")) mostrarDicaDaUsina(a, e, false); return; }
    var uf = ufNoPonto(e.clientX, e.clientY);
    var rodape = uf ? nomeDaUf(uf) + (TV ? "" : " · clique para aproximar") : "";
    var nomes = dados.nomes || {};
    if (alvo.matches && alvo.matches(".mp-avisos path")) {
      mostrarDicaSimples(["Aviso do " + (nomes.inmet || "INMET"), alvo.getAttribute("data-dica") || "", rodape].filter(Boolean),
                         e.clientX, e.clientY);
      return;
    }
    if (alvo.matches && alvo.matches(".mp-cr, .mp-cd")) {
      var camada = alvo.classList.contains("mp-cr") ? "risco" : "densidade";
      var info = (dados.calor || {})[camada] || {};
      var titulo = camada === "risco" ? "Risco de fogo do " + (nomes.inpe || "INPE")
                                      : "Densidade de focos de queimada (" + (nomes.inpe || "INPE") + ")";
      var classe = (info.classes || {})[alvo.getAttribute("data-classe")] || "";
      mostrarDicaSimples([titulo, classe, info.lado_km ? "quadrado de cerca de " + info.lado_km + " km" : "", rodape]
                         .filter(Boolean), e.clientX, e.clientY);
      return;
    }
    if (alvo.matches && alvo.matches(".mp-focos")) {
      mostrarDicaSimples(["Foco de queimada", "detectado na última hora (" + (nomes.inpe || "INPE") + ")", rodape].filter(Boolean),
                         e.clientX, e.clientY);
      return;
    }
    if (uf) { mostrarDicaSimples([rodape], e.clientX, e.clientY); return; }
    esconderDica();
  }

  // ── os eventos do mapa ────────────────────────────────────────────────────────────────────────────────────────────────
  mapa.addEventListener("pointerdown", function (e) {
    ultimoTipo = e.pointerType || "mouse";
    var s = svg();
    if (!s || !s.contains(e.target) || e.button !== 0 || ultimoTipo === "touch") return;
    arrasto = { x: e.clientX, y: e.clientY, vb: vb.slice(), id: e.pointerId, ativo: false, escala: s.getScreenCTM().a };
    arrastou = false;
  });

  mapa.addEventListener("pointermove", function (e) {
    var s = svg();
    if (arrasto && e.pointerId === arrasto.id) {
      var dx = e.clientX - arrasto.x, dy = e.clientY - arrasto.y;
      if (!arrasto.ativo && Math.abs(dx) + Math.abs(dy) > 5) {
        arrasto.ativo = true;
        historico.push(arrasto.vb.slice());
        s.setPointerCapture(e.pointerId);
        s.classList.add("mp-arrastando");
        esconderDica(true);
      }
      if (arrasto.ativo) {
        aplicar([arrasto.vb[0] - dx / arrasto.escala, arrasto.vb[1] - dy / arrasto.escala, arrasto.vb[2], arrasto.vb[3]], false);
        return;
      }
    }
    if (e.pointerType === "touch") return;
    if (!s || !s.contains(e.target)) { esconderDica(); return; }      // fora do desenho, a dica some (não fica a de antes)
    if (quadro) return;
    quadro = requestAnimationFrame(function () { quadro = 0; dicaNoPonto(e); });
  });

  function soltar(e) {
    if (!arrasto) return;
    var s = svg();
    if (arrasto.ativo) {
      arrastou = true;
      if (s && s.hasPointerCapture && s.hasPointerCapture(e.pointerId)) s.releasePointerCapture(e.pointerId);
      if (s) s.classList.remove("mp-arrastando");
      var voltarBt = mapa.querySelector('[data-zoom="voltar"]');
      if (voltarBt) voltarBt.disabled = historico.length === 0;
    }
    arrasto = null;
  }
  mapa.addEventListener("pointerup", soltar);
  mapa.addEventListener("pointercancel", soltar);

  mapa.addEventListener("pointerleave", function (e) {
    if (e.target === mapa) esconderDica();
  });
  mapa.addEventListener("mouseout", function (e) {
    var s = svg();
    if (s && s.contains(e.target) && !s.contains(e.relatedTarget)) esconderDica();
  });

  mapa.addEventListener("wheel", function (e) {
    var s = svg();
    if (!s || !s.contains(e.target) || !vb) return;
    e.preventDefault();
    var p = pontoDoDesenho(e.clientX, e.clientY);
    if (!p) return;
    var unidade = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 400 : 1;
    var fator = Math.exp(-e.deltaY * unidade * 0.0018);
    // a rodada inteira (uma girada da roda) volta com um "Voltar" só
    var agora = Date.now();
    aplicar(zoomEm(vb, base, p[0], p[1], fator), agora > rodaAte);
    rodaAte = agora + 500;
  }, { passive: false });

  mapa.addEventListener("click", function (e) {
    var s = svg();
    if (s && s.contains(e.target)) {
      if (arrastou) { arrastou = false; e.preventDefault(); return; }
      var a = e.target.closest(".mp-usinas a");
      if (a) {
        // ctrl/cmd/shift abrem em outra aba, como o navegador sempre fez; no celular o toque abre a página, como antes
        if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || ultimoTipo === "touch") return;
        var id = idDoHref(a.getAttribute("href"));
        if (id === selecionada) return;                    // o segundo clique segue o link: abre a página da usina
        e.preventDefault();
        selecionar(id, {});
        return;
      }
      var uf = ufNoPonto(e.clientX, e.clientY);
      var info = uf && (dados.ufs || {})[uf];
      if (info && ultimoTipo !== "touch") { aplicar(enquadrar(info.caixa, base), true); return; }
      if (selecionada) selecionar(null);
      return;
    }
    var bt = e.target.closest("[data-zoom]");
    if (bt) {
      var z = bt.getAttribute("data-zoom");
      if (z === "mais") zoomBotao(PASSO_ZOOM);
      else if (z === "menos") zoomBotao(1 / PASSO_ZOOM);
      else if (z === "tudo") aplicar(base, true);
      else if (z === "voltar") voltar();
      return;
    }
    var tr = e.target.closest(".mp-tab-lin");
    if (tr && !e.target.closest("a")) {
      var link = tr.querySelector("a.cl-link");
      selecionar(link && idDoHref(link.getAttribute("href")), { centralizar: true });
      return;
    }
    var acao = e.target.closest("[data-acao]");
    if (!acao) return;
    var tipo = acao.getAttribute("data-acao");
    if (tipo === "estado" || tipo === "regiao") {
      if (e.ctrlKey || e.metaKey || e.shiftKey) return;
      e.preventDefault();
      mudarEstado(acao, tipo === "regiao");
    } else if (tipo === "tela-cheia") {
      alternarTelaCheia();
    } else if (tipo === "tema") {
      alternarTema(acao);
    }
  });

  mapa.addEventListener("keydown", function (e) {
    var acao = e.target.closest && e.target.closest('[role="button"][data-acao]');
    if (acao && e.key === " ") { e.preventDefault(); acao.click(); return; }
    var f = figura();
    if (!f || !f.contains(e.target) || e.altKey || e.ctrlKey || e.metaKey || !vb) return;
    var passo = 0.12, feito = true;
    if (e.key === "ArrowLeft") aplicar([vb[0] - vb[2] * passo, vb[1], vb[2], vb[3]], true);
    else if (e.key === "ArrowRight") aplicar([vb[0] + vb[2] * passo, vb[1], vb[2], vb[3]], true);
    else if (e.key === "ArrowUp") aplicar([vb[0], vb[1] - vb[3] * passo, vb[2], vb[3]], true);
    else if (e.key === "ArrowDown") aplicar([vb[0], vb[1] + vb[3] * passo, vb[2], vb[3]], true);
    else if (e.key === "+" || e.key === "=") zoomBotao(PASSO_ZOOM);
    else if (e.key === "-" || e.key === "_") zoomBotao(1 / PASSO_ZOOM);
    else if (e.key === "0") aplicar(base, true);
    else if (e.key === "Backspace") voltar();
    else if (e.key === "Escape") { selecionar(null); esconderDica(true); }
    else feito = false;
    if (feito) e.preventDefault();
  });

  // o foco do teclado mostra o mesmo que o mouse: a usina com foco no mapa ganha a dica; a linha da tabela com foco marca a usina
  mapa.addEventListener("focusin", function (e) {
    var a = e.target.closest && e.target.closest(".mp-usinas a");
    if (a) {
      a.setAttribute("aria-describedby", "mp-dica");
      mostrarDicaDaUsina(a, null, false);
      var tr = linhaDaUsina(idDoHref(a.getAttribute("href")));
      mapa.querySelectorAll(".mp-tab--foco").forEach(function (x) { x.classList.remove("mp-tab--foco"); });
      if (tr) { tr.classList.add("mp-tab--foco"); rolarTabelaAte(tr); }
      return;
    }
    var link = e.target.closest && e.target.closest(".mp-tab-lin a.cl-link");
    if (link) {
      var id = idDoHref(link.getAttribute("href")), u = linkDaUsina(id);
      if (u && vb) {
        var p = u.querySelector(".mp-ponto"), x = parseFloat(p.getAttribute("cx")), y = parseFloat(p.getAttribute("cy"));
        if (!(x > vb[0] && x < vb[0] + vb[2] && y > vb[1] && y < vb[1] + vb[3])) aplicar([x - vb[2] / 2, y - vb[3] / 2, vb[2], vb[3]], true);
        mostrarDicaDaUsina(u, null, false);
      }
    }
  });
  mapa.addEventListener("focusout", function (e) {
    if (e.target.closest && (e.target.closest(".mp-usinas a") || e.target.closest(".mp-tab-lin a.cl-link"))) esconderDica();
  });

  // ── o estado da tela no endereço: camada, filtros, região ─────────────────────────────────────────────────────────────
  function mudarEstado(link, empurrar) {
    // na hora, o que dá para mostrar sem o servidor; depois, a página relida com o endereço novo traz o resto (e os links novos)
    var fundo = link.getAttribute("data-fundo"), sobre = link.getAttribute("data-sobre");
    var nivel = link.getAttribute("data-nivel"), ev = link.getAttribute("data-ev");
    if (fundo) {
      mapa.setAttribute("data-fundo", fundo);
      link.parentNode.querySelectorAll("[data-fundo]").forEach(function (x) { x.setAttribute("aria-pressed", String(x === link)); });
    } else if (sobre) {
      var some = mapa.classList.toggle("mp-sem-" + sobre);
      link.setAttribute("aria-pressed", String(!some));
    } else if (nivel) {
      var oculto = mapa.classList.toggle("mp-oculta-" + nivel);
      link.setAttribute("aria-pressed", String(!oculto));
    } else if (ev) {
      var esconder = link.getAttribute("aria-pressed") !== "false";
      link.setAttribute("aria-pressed", String(!esconder));
      mapa.querySelectorAll('.mp-avisos path[data-ev="' + ev + '"]').forEach(function (p) {
        p.classList.toggle("mp-av-oculto", esconder);
      });
    }
    var destino = link.getAttribute("href");
    if (empurrar) history.pushState(null, "", destino); else history.replaceState(null, "", destino);
    if (empurrar) { selecionada = null; }
    atualizar();
  }

  mapa.addEventListener("change", function (e) {
    if (!e.target.matches || !e.target.matches('[data-acao="cliente"]')) return;
    var url = new URL(location.href);
    if (e.target.value) url.searchParams.set("cliente", e.target.value); else url.searchParams.delete("cliente");
    history.replaceState(null, "", url.pathname + url.search);
    selecionada = null;
    atualizar();
  });

  window.addEventListener("popstate", function () { selecionada = null; atualizar(); });

  // ── a busca ───────────────────────────────────────────────────────────────────────────────────────────────────────────
  var busca = document.getElementById("mp-busca");
  function buscar() {
    var msg = mapa.querySelector(".mp-busca-msg");
    var id = acharUsina(dados.usinas, busca.value);
    if (!busca.value.trim()) { if (msg) msg.textContent = ""; return; }
    if (!id) {
      if (msg) msg.textContent = "Nenhuma usina com esse nome neste recorte" + (dados.regiao && dados.regiao !== "brasil" ? "; escolha o Brasil para procurar em todas." : ".");
      return;
    }
    if (mapa.classList.contains("mp-sem-usinas")) mapa.classList.remove("mp-sem-usinas");
    selecionar(id, { zoom: true });
    if (msg) msg.textContent = "No mapa: " + dados.usinas[id].n + ".";
  }
  if (busca) {
    busca.closest(".mp-busca").hidden = false;
    busca.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); buscar(); } });
    busca.addEventListener("change", buscar);
  }

  // ── a releitura no ritmo dos caches ───────────────────────────────────────────────────────────────────────────────────
  function agendar(segundos) {
    clearTimeout(timer);
    timer = setTimeout(function () { atualizar(); }, segundos * 1000);
    var prox = mapa.querySelector(".mp-tv-proxima");
    if (prox) prox.textContent = "próxima leitura às " + hhmm(new Date(Date.now() + segundos * 1000));
  }

  function trocar(doc, nova) {
    var foco = document.activeElement && document.activeElement.id;
    esconderDica(true);                      // a dica era de um desenho que vai sair
    mapa.className = nova.className;
    ["data-fundo", "data-proxima-s", "data-girar"].forEach(function (a) {
      if (nova.hasAttribute(a)) mapa.setAttribute(a, nova.getAttribute(a));
    });
    mapa.querySelectorAll("[data-parte]").forEach(function (atual) {
      var nome = atual.getAttribute("data-parte");
      var veio = nova.querySelector('[data-parte="' + nome + '"]');
      if (veio) atual.replaceWith(document.importNode(veio, true));
    });
    lerDados();
    iniciarDesenho(true);
    if (selecionada && !linkDaUsina(selecionada)) selecionada = null;
    if (selecionada) {
      var tr = linhaDaUsina(selecionada);
      if (tr) tr.classList.add("mp-tab--sel");
      desenharSelecao();
    }
    if (foco) { var f = document.getElementById(foco); if (f) f.focus({ preventScroll: true }); }
    if (TV) { caberTabela(); iniciarGiro(); }
  }

  function mostrarFalha(motivo, detalhe) {
    falhaAtual = motivo;
    mapa.classList.add("mp-desatualizado");
    var quando = hhmm(ultimoOk), agora = hhmm(new Date());
    var texto = motivo === "sessao"
      ? "A sessão do Nexus neste navegador terminou (às " + agora + "). O mapa abaixo é de " + quando +
        " e não está mais sendo atualizado: entre de novo no Nexus neste navegador."
      : "O Nexus não respondeu (" + (detalhe || "sem conexão") + ", às " + agora + "). O mapa abaixo é de " + quando +
        " e não está sendo atualizado; a tela tenta de novo a cada minuto.";
    var faixa = mapa.querySelector(TV ? ".mp-tv-estado" : ".mp-faixa-estado");
    if (!faixa) return;
    faixa.textContent = texto;
    if (motivo === "sessao" && !TV) {
      var entrar = el("a", null, " Entrar de novo");
      entrar.href = "/entrar?next=" + encodeURIComponent(location.pathname + location.search);
      faixa.appendChild(entrar);
    }
    faixa.classList.toggle("mp-faixa-estado--fora", motivo === "sessao");
    faixa.classList.toggle("mp-tv-estado--atencao", motivo !== "sessao");
    faixa.hidden = false;
    if (TV) caberTabela();                   // a faixa toma altura: a tabela refaz o que cabe
  }

  function limparFalha() {
    falhaAtual = null;
    mapa.classList.remove("mp-desatualizado");
    var faixa = mapa.querySelector(TV ? ".mp-tv-estado" : ".mp-faixa-estado");
    if (faixa && !faixa.hidden) { faixa.hidden = true; faixa.textContent = ""; if (TV) caberTabela(); }
  }

  function atualizar() {
    clearTimeout(timer);
    if (carregando) carregando.abort();
    var controle = new AbortController();
    carregando = controle;
    mapa.classList.add("mp-atualizando");
    fetch(location.pathname + location.search, { credentials: "same-origin", redirect: "manual", cache: "no-store",
                                                  signal: controle.signal, headers: { "Accept": "text/html" } })
      .then(function (r) {
        var motivo = motivoDaFalha({ tipo: r.type, status: r.status, temMapa: true });
        if (motivo) throw { motivo: motivo, detalhe: "HTTP " + r.status };
        return r.text();
      })
      .then(function (html) {
        var doc = new DOMParser().parseFromString(html, "text/html");
        var nova = doc.querySelector("[data-mapa]");
        if (motivoDaFalha({ tipo: "basic", status: 200, temMapa: !!nova })) throw { motivo: "sessao" };
        trocar(doc, nova);
        ultimoOk = new Date();
        limparFalha();
        agendar(proximaEspera(nova.getAttribute("data-proxima-s"), false));
      })
      .catch(function (erro) {
        if (erro && erro.name === "AbortError") return;
        mostrarFalha(erro && erro.motivo ? erro.motivo : "rede", erro && erro.detalhe);
        agendar(proximaEspera(null, true));
      })
      .then(function () {
        if (carregando === controle) { carregando = null; mapa.classList.remove("mp-atualizando"); }
      });
  }

  document.addEventListener("visibilitychange", function () {
    // a aba que volta a aparecer (o navegador segura os relógios das abas escondidas) relê se a hora já passou
    if (document.visibilityState === "visible" && Date.now() - ultimoOk.getTime() > proximaEspera(mapa.getAttribute("data-proxima-s"), false) * 1000) {
      atualizar();
    }
  });

  // ── tela cheia e tema ─────────────────────────────────────────────────────────────────────────────────────────────────
  function alvoDaTelaCheia() { return TV ? document.documentElement : document.getElementById("mp-palco"); }
  function alternarTelaCheia() {
    if (document.fullscreenElement) { document.exitFullscreen(); return; }
    var alvo = alvoDaTelaCheia();
    if (alvo && alvo.requestFullscreen) alvo.requestFullscreen().catch(function () {});
  }
  function marcarTelaCheia() {
    var cheia = !!document.fullscreenElement;
    mapa.querySelectorAll('[data-acao="tela-cheia"]').forEach(function (b) {
      b.setAttribute("aria-pressed", String(cheia));
      b.textContent = cheia ? "Sair da tela cheia" : "Tela cheia";
    });
    if (vb) aplicar(vb, false);
    if (TV) caberTabela();
  }
  document.addEventListener("fullscreenchange", marcarTelaCheia);
  if (document.fullscreenEnabled) {
    mapa.querySelectorAll('[data-acao="tela-cheia"]').forEach(function (b) { b.hidden = false; });
  }

  function alternarTema(botao) {
    var novo = document.documentElement.getAttribute("data-tema") === "claro" ? "escuro" : "claro";
    if (window.NexusTema) window.NexusTema.gravar(novo);
    document.documentElement.setAttribute("data-tema", novo);
    botao.textContent = "Tema: " + (novo === "claro" ? "Claro" : "Escuro");
  }

  // ── o modo TV: relógio, giro das camadas, controles que somem e a tabela que não rola ────────────────────────────────
  function relogio() {
    var agora = new Date();
    var h = mapa.querySelector(".mp-tv-hora"), d = mapa.querySelector(".mp-tv-data");
    if (h) h.textContent = hhmm(agora);
    if (d) d.textContent = agora.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });
  }

  function caberTabela() {
    // o modo TV não rola: a tabela mostra as linhas que cabem (da mais grave para a menos) e diz quantas ficaram de fora
    var caixa = mapa.querySelector(".mp-tv .mp-tab-rolagem"), mais = mapa.querySelector(".mp-tv .mp-tab-mais");
    if (!caixa) return;
    var linhas = Array.prototype.slice.call(caixa.querySelectorAll("tbody tr"));
    linhas.forEach(function (tr) { tr.style.display = ""; });
    var visiveis = linhas.filter(function (tr) { return getComputedStyle(tr).display !== "none"; });
    if (mais) { mais.hidden = false; mais.textContent = "e mais 0 usinas"; }       // reserva a linha do "e mais" antes de medir
    var cab = caixa.querySelector("thead");
    var alturas = visiveis.map(function (tr) { return tr.getBoundingClientRect().height; });
    var n = quantasCabem(alturas, caixa.clientHeight - (cab ? cab.getBoundingClientRect().height : 0), 0);
    visiveis.forEach(function (tr, i) { if (i >= n) tr.style.display = "none"; });
    if (mais) {
      var resto = visiveis.length - n;
      mais.hidden = resto <= 0;
      mais.textContent = resto > 0 ? "e mais " + resto + (resto === 1 ? " usina" : " usinas") + " (a lista inteira está no Clima e risco)" : "";
    }
  }

  function iniciarGiro() {
    clearInterval(giroTimer);
    var s = parseInt(mapa.getAttribute("data-girar"), 10) || 0;
    var giro = (dados.giro || []);
    var aviso = mapa.querySelector(".mp-tv-giro");
    if (!TV || s < MIN_S || giro.length < 2) { if (aviso) aviso.hidden = true; return; }
    giroFalta = s;
    if (aviso) aviso.hidden = false;
    giroTimer = setInterval(function () {
      giroFalta -= 1;
      if (giroFalta <= 0) {
        var atual = giro.indexOf(mapa.getAttribute("data-fundo"));
        mapa.setAttribute("data-fundo", giro[(atual + 1) % giro.length]);
        giroFalta = s;
        caberTabela();
      }
      var n = mapa.querySelector(".mp-tv-giro-s");
      if (n) n.textContent = String(giroFalta);
    }, 1000);
  }

  function mostrarControles() {
    var c = mapa.querySelector(".mp-tv-controles");
    if (!c) return;
    c.hidden = false;
    document.documentElement.classList.remove("mp-tv-ocioso");
    clearTimeout(controlesTimer);
    controlesTimer = setTimeout(function () {
      if (c.contains(document.activeElement)) return;
      c.hidden = true;
      document.documentElement.classList.add("mp-tv-ocioso");
    }, 6000);
  }

  // ── começo ────────────────────────────────────────────────────────────────────────────────────────────────────────────
  lerDados();
  iniciarDesenho(false);
  var ferramentas = mapa.querySelector(".mp-ferramentas");
  if (ferramentas) ferramentas.hidden = false;
  window.addEventListener("resize", function () { if (vb) aplicar(vb, false); if (TV) caberTabela(); });
  if (TV) {
    relogio();
    setInterval(relogio, 10000);
    caberTabela();
    iniciarGiro();
    ["mousemove", "keydown", "pointerdown"].forEach(function (t) { document.addEventListener(t, mostrarControles); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") { var c = mapa.querySelector(".mp-tv-controles"); if (c) c.hidden = true; }
    });
  }
  agendar(proximaEspera(mapa.getAttribute("data-proxima-s"), false));
})(typeof window !== "undefined" ? window : globalThis);
