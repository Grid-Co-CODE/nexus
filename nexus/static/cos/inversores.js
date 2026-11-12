/* static/cos/inversores.js — o Monitoramento do COS EM TEMPO REAL, como o da Ronda COS (protótipo de 12/11/2026).
   Serve à tela normal (os cartões .cos-mon-u e a lista da atenção) e ao videowall (.cos-tv-u): o que tem data-gid.

   O ritmo é o da Ronda COS (apps/web/src/app/monitoramento/page.tsx e components/curva-scada.tsx):
   - GET /scada/monitoramento?entradas=separadas 3 s DEPOIS de cada resposta, parado com a aba escondida: o kW, o estado
     da usina e de CADA inversor andam sozinhos.
   - A curva gravada é de 5 em 5 min e é relida a cada 5 min; o que anda é a PONTA, montada com as leituras de 3 s (só
     quando o valor muda) e podada quando a gravação alcança — a curva nunca tem duas verdades. A ponta é do DIA: na
     virada, a de ontem some (revisão de 12/11: uma tela aberta de noite ganhava às 6h a cauda da tarde anterior).

   Na grade: o kW de cada cartão, a marca dos inversores (vermelho = desligado ou em falha; âmbar = sem comunicação, que
   pode estar gerando) e a ponta da curva. Ao clicar: a curva da usina e a de cada inversor, na mesma escala, com a cruz
   que acompanha o mouse em todos ao mesmo tempo.

   Custo da volta de 3 s (revisão de 12/11): o minuto do dia é conta (São Paulo é UTC−3 fixo desde 2019), não `Intl`;
   o cartão do SCADA é achado por mapa; só se escreve o que mudou; cartão escondido (as páginas do videowall) não é
   redesenhado; e o gráfico da janela só é refeito quando a série dele muda.

   Lê a API da Ronda COS com o login, direto do navegador (o desenho final): `window.NexusCos.api` (NEXUS_COS_API_URL).
   O id do inversor no cartão é "<logger>:<modbus>" (scada.parser.ts); a série da curva traz os dois. */
(function () {
  "use strict";
  var CFG = window.NexusCos || {};
  var API = CFG.api || "";                               // vazio: sem o ao vivo (a tela fica com o que o servidor manda)
  var DE = 5 * 60, ATE = 19 * 60;
  var VIVO_MS = 3000, CURVA_MS = 5 * 60000, CURVAS_GUARDADAS = 10;
  var fusoMin = -180, fusoEm = 0;                        // America/Sao_Paulo (UTC−3 hoje), conferido de hora em hora
  function fuso(ms) {
    if (ms - fusoEm > 3600000 || ms < fusoEm) {
      try {
        var p = {}; new Intl.DateTimeFormat("en-US", { timeZone: "America/Sao_Paulo", hourCycle: "h23", year: "numeric", month: "2-digit",
          day: "2-digit", hour: "2-digit", minute: "2-digit" }).formatToParts(new Date(ms)).forEach(function (x) { p[x.type] = +x.value; });
        fusoMin = Math.round((Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute) - Math.floor(ms / 60000) * 60000) / 60000);
      } catch (e) { fusoMin = -180; }
      fusoEm = ms;
    }
    return fusoMin;
  }
  var ESTADO = {
    GERANDO: { rotulo: "Gerando", tom: "ok" },
    STANDBY: { rotulo: "Standby", tom: "neutro" },
    DESLIGADO: { rotulo: "Desligado", tom: "critico", grupo: "fora" },
    FALHA: { rotulo: "Em falha", tom: "critico", grupo: "fora" },
    SEM_COMUNICACAO: { rotulo: "Sem comunicação", tom: "alerta", grupo: "semcom" },
    DESCONHECIDO: { rotulo: "Sem estado", tom: "neutro" }
  };
  var ORDEM = { DESLIGADO: 0, FALHA: 1, SEM_COMUNICACAO: 2, DESCONHECIDO: 3, STANDBY: 4, GERANDO: 5 };
  var NS = "http://www.w3.org/2000/svg";
  var SELETOR = ".cos-mon-u[data-gid], .cos-tv-u[data-gid], .cos-mon-at-i[data-gid]";

  // ── a API: o login (no final, o passe do Nexus em CFG.sessao; no protótipo, o da Ronda COS deste navegador) ───────
  function sessao() {
    if (typeof CFG.sessao === "function") { return CFG.sessao() || {}; }
    try { return (JSON.parse(localStorage.getItem("ronda-cos-auth") || "{}").state) || {}; } catch (e) { return {}; }
  }
  var renovando = null;                                  // um refresh só, por mais 401 que cheguem juntos
  function renovar(s) {
    if (typeof CFG.renovar === "function") { return Promise.resolve(CFG.renovar()); }
    if (!s.refreshToken) { return Promise.reject({ login: true }); }
    if (!renovando) {
      renovando = fetch(API + "/auth/refresh", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: s.refreshToken }) }).then(function (r) {
        if (!r.ok) { throw { login: true }; }
        return r.json();
      }).then(function (d) {
        try { var o = JSON.parse(localStorage.getItem("ronda-cos-auth")); o.state.accessToken = d.access_token; localStorage.setItem("ronda-cos-auth", JSON.stringify(o)); } catch (e) {}
      }).then(function () { renovando = null; }, function (e) { renovando = null; throw e; });
    }
    return renovando;
  }
  function pedir(caminho, deNovo) {
    if (!API) { return Promise.reject({ fora: true }); }
    // CFG.pelaPorta (12/11/2026, o Nexus): quem lê a Ronda COS é o servidor do Nexus, pela chave do Andamento
    // (`/t/cos/monitoramento/ronda-api/...`, a sessão do Nexus na mesma origem); sem login da Ronda COS
    if (CFG.pelaPorta) { return pedirPelaPorta(caminho); }
    var s = sessao();
    // CFG.semLogin (só o protótipo): o outro PC pede sem o próprio login, e o repassador do notebook completa
    if (!s.accessToken && !CFG.semLogin) { return Promise.reject({ login: true }); }
    var cab = s.accessToken ? { Authorization: "Bearer " + s.accessToken } : {};
    var ctl = window.AbortController ? new AbortController() : null, prazo = ctl ? setTimeout(function () { ctl.abort(); }, 15000) : 0;
    return fetch(API + caminho, { headers: cab, signal: ctl ? ctl.signal : undefined }).then(function (r) {
      clearTimeout(prazo);
      if (r.status === 401 && !deNovo && s.accessToken) { return renovar(s).then(function () { return pedir(caminho, true); }); }
      if (r.status === 401) { throw { login: true }; }
      if (!r.ok) { throw { erro: "a Ronda COS respondeu " + r.status }; }
      return r.json();
    }, function (e) { clearTimeout(prazo); throw { erro: e && e.name === "AbortError" ? "a Ronda COS não respondeu em 15 s" : "sem rede" }; });
  }

  function pedirPelaPorta(caminho) {
    var ctl = window.AbortController ? new AbortController() : null, prazo = ctl ? setTimeout(function () { ctl.abort(); }, 15000) : 0;
    return fetch(API + caminho, { credentials: "same-origin", headers: { Accept: "application/json" },
      signal: ctl ? ctl.signal : undefined }).then(function (r) {
      clearTimeout(prazo);
      // a sessão do Nexus que venceu volta como a página de entrar (HTML), e não JSON
      var tipo = r.headers.get("content-type") || "";
      if (r.status === 401 || r.status === 403 || (r.ok && tipo.indexOf("json") < 0)) { throw { login: true }; }
      if (!r.ok) {
        return r.json().catch(function () { return {}; }).then(function (d) { throw { erro: d.error || ("o Nexus respondeu " + r.status) }; });
      }
      return r.json();
    }, function (e) { clearTimeout(prazo); throw { erro: e && e.name === "AbortError" ? "a leitura não respondeu em 15 s" : "sem rede" }; });
  }

  // ── tempo e números (conta, não Intl, no que roda a cada 3 s) ────────────────────────────────────────────────────
  function minutoSP(t) {
    var ms = typeof t === "number" ? t : Date.parse(t);
    var m = (ms / 60000 + fuso(ms)) % 1440;
    return m < 0 ? m + 1440 : m;
  }
  function diaSP(ms) { return Math.floor((ms / 60000 + fuso(ms)) / 1440); }
  function dois(n) { return (n < 10 ? "0" : "") + n; }
  function hhmm(min) { return dois(Math.floor(min / 60)) + ":" + dois(Math.floor(min % 60)); }
  function hhmmss(ms) { var m = minutoSP(ms), s = Math.floor(ms / 1000) % 60; return hhmm(m) + ":" + dois(s); }
  var fmtMW = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 }), fmtKW = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
  function kw(v) {
    if (v == null || isNaN(v)) { return "—"; }
    return v >= 1000 ? fmtMW.format(v / 1000) + " MW" : fmtKW.format(v) + " kW";
  }
  function passoBonito(x) {
    var e = Math.pow(10, Math.floor(Math.log10(Math.max(x, 1e-9)))), f = x / e;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * e;
  }
  function tetoBonito(max, partes) { var p = passoBonito(Math.max(max, 1) / partes); return Math.max(1, p * Math.ceil(Math.max(max, 1) / p)); }
  function maximo(pts) { var m = 0; for (var i = 0; i < pts.length; i++) { if (pts[i][1] != null && pts[i][1] > m) { m = pts[i][1]; } } return m; }
  var series = new WeakMap();                            // a série gravada já convertida, por resposta da curva
  function serie(pontos) {
    if (!pontos) { return []; }
    if (series.has(pontos)) { return series.get(pontos); }
    var s = pontos.map(function (p) { return [minutoSP(p.em), p.pac_kw == null ? null : +p.pac_kw]; })
      .filter(function (p) { return p[0] >= DE && p[0] <= ATE; }).sort(function (a, b) { return a[0] - b[0]; });
    series.set(pontos, s);
    return s;
  }
  function valorEm(pts, min) {
    var melhor = null, d = 1e9;
    for (var i = 0; i < pts.length; i++) { var dd = Math.abs(pts[i][0] - min); if (dd < d) { d = dd; melhor = pts[i]; } }
    return melhor && d <= 7.5 ? melhor : null;
  }

  // ── a PONTA ao vivo: as leituras de 3 s depois do último ponto gravado, só do dia de hoje ─────────────────────────
  var pontas = {};
  function anotarPonta(chave, valor, ms) {
    var l = pontas[chave] || (pontas[chave] = []);
    if (l.length && l[l.length - 1].kw === valor && l[l.length - 1].dia === diaSP(ms)) { return; }
    l.push({ dia: diaSP(ms), min: minutoSP(ms), kw: valor });
    if (l.length > 400) { l.shift(); }
  }
  function comPonta(base, chave) {
    var ult = -1, hoje = diaSP(Date.now()), l = pontas[chave];
    for (var i = base.length - 1; i >= 0; i--) { if (base[i][1] != null) { ult = base[i][0]; break; } }
    if (!l || !l.length) { return base; }
    while (l.length && l[0].dia !== hoje) { l.shift(); }   // podada só a de ontem: o resto é de quem desenha
    var ponta = [];
    for (var k = 0; k < l.length; k++) { var p = l[k]; if (p.min > ult && p.min >= DE && p.min <= ATE && p.kw != null) { ponta.push([p.min, p.kw]); } }
    return ponta.length ? base.concat(ponta) : base;
  }

  // ── o gráfico (na largura real do bloco: nada esticado) ───────────────────────────────────────────────────────────
  function el(tag, attrs, pai) {
    var n = document.createElementNS(NS, tag);
    for (var k in attrs) { if (Object.prototype.hasOwnProperty.call(attrs, k)) { n.setAttribute(k, attrs[k]); } }
    if (pai) { pai.appendChild(n); }
    return n;
  }
  function caminhos(pts, x, y) {
    var dL = "", dA = "", aberto = false, ultX = 0;
    for (var i = 0; i < pts.length; i++) {
      var p = pts[i];
      if (p[1] == null) { if (aberto) { dA += "L" + ultX.toFixed(1) + " " + y(0).toFixed(1) + "Z"; } aberto = false; continue; }
      var px = x(p[0]).toFixed(1), py = y(p[1]).toFixed(1);
      if (!aberto) { dL += "M" + px + " " + py; dA += "M" + px + " " + y(0).toFixed(1) + "L" + px + " " + py; aberto = true; }
      else { dL += "L" + px + " " + py; dA += "L" + px + " " + py; }
      ultX = +px;
    }
    if (aberto) { dA += "L" + ultX.toFixed(1) + " " + y(0).toFixed(1) + "Z"; }
    return [dL, dA];
  }
  var graficos = [], cruzEm = null;
  // um gráfico por bloco; refeito só quando a série, o teto ou a largura mudam (a volta de 3 s não mexe no resto)
  function grafico(host, pts, o, largura) {
    var w = Math.max(160, largura || host.clientWidth || 600), h = o.h, max = o.max || 1;
    var fim = null;
    for (var i = pts.length - 1; i >= 0; i--) { if (pts[i][1] != null) { fim = pts[i]; break; } }
    var assinatura = [w, max, o.grupo || "", pts.length, fim ? fim[0].toFixed(2) + "/" + fim[1] : "-", Math.floor(minutoSP(Date.now()))].join("|");
    var velho = host._g;
    if (velho && velho.assinatura === assinatura) { velho.aoMarcar = o.aoMarcar; graficos.push(velho); return velho; }
    var ml = o.eixoY ? 52 : 6, mr = o.rotuloFim ? 72 : 10, mt = 10, mb = o.eixoX ? 22 : 6;
    var iw = w - ml - mr, ih = h - mt - mb;
    function x(m) { return ml + (m - DE) / (ATE - DE) * iw; }
    function y(v) { return mt + ih - Math.max(0, Math.min(1, v / max)) * ih; }
    var foco = velho && document.activeElement === velho.alvo;
    if (foco) { velho.trocando = true; }                 // o blur da troca não apaga a cruz
    host.textContent = "";
    var svg = el("svg", { viewBox: "0 0 " + w + " " + h, width: w, height: h, class: "pg" + (o.grupo ? " pg--" + o.grupo : ""),
      role: "img", "aria-label": o.rotulo || "" }, host);
    var grade = el("g", { class: "pg-grade" }, svg), eixo = el("g", { class: "pg-eixo" }, svg);
    var passo = passoBonito(max / (o.eixoY ? 4 : 2));
    for (var v = passo; v <= max + 1e-6; v += passo) {
      el("line", { x1: ml, x2: ml + iw, y1: Math.round(y(v)) + 0.5, y2: Math.round(y(v)) + 0.5 }, grade);
      if (o.eixoY) { el("text", { x: ml - 8, y: y(v) + 4, "text-anchor": "end" }, eixo).textContent = kw(v); }
    }
    el("line", { class: "pg-base", x1: ml, x2: ml + iw, y1: Math.round(y(0)) + 0.5, y2: Math.round(y(0)) + 0.5 }, svg);
    if (o.eixoY) { el("text", { x: ml - 8, y: y(0) + 4, "text-anchor": "end" }, eixo).textContent = "0"; }
    if (o.eixoX) {
      [6, 9, 12, 15, 18].forEach(function (hh) { el("text", { x: x(hh * 60), y: h - 6, "text-anchor": "middle" }, eixo).textContent = dois(hh) + "h"; });
    }
    var agora = minutoSP(Date.now());
    if (agora > DE && agora < ATE) { el("line", { class: "pg-agora", x1: x(agora), x2: x(agora), y1: mt, y2: mt + ih }, svg); }
    var d = caminhos(pts, x, y);
    if (d[1]) { el("path", { class: "pg-area", d: d[1] }, svg); }
    if (d[0]) { el("path", { class: "pg-linha", d: d[0] }, svg); }
    if (fim) {
      if (o.vivo) { el("circle", { class: "pg-halo", cx: x(fim[0]), cy: y(fim[1]), r: 8 }, svg); }
      el("circle", { class: "pg-fim", cx: x(fim[0]), cy: y(fim[1]), r: 4 }, svg);
      if (o.rotuloFim) { el("text", { class: "pg-fim-rot", x: x(fim[0]) + 10, y: y(fim[1]) + 4 }, svg).textContent = kw(fim[1]); }
    }
    var cruz = el("line", { class: "pg-cruz", x1: 0, x2: 0, y1: mt, y2: mt + ih, visibility: "hidden" }, svg);
    var ponto = el("circle", { class: "pg-cruz-ponto", r: 4, cx: 0, cy: 0, visibility: "hidden" }, svg);
    var alvo = el("rect", { class: "pg-alvo", x: ml, y: 0, width: iw, height: h, tabindex: "0", "aria-label": (o.nome || "") + ": use as setas para ler a curva" }, svg);
    var g = { host: host, pts: pts, x: x, y: y, cruz: cruz, ponto: ponto, nome: o.nome, aoMarcar: o.aoMarcar, fim: fim, alvo: alvo, assinatura: assinatura };
    host._g = g;
    graficos.push(g);
    function minutoDoEvento(ev) { var r = svg.getBoundingClientRect(); return DE + ((ev.clientX - r.left) * (w / r.width) - ml) / iw * (ATE - DE); }
    alvo.addEventListener("pointermove", function (ev) { marcarTodos(minutoDoEvento(ev), g, ev.clientX, ev.clientY); });
    alvo.addEventListener("pointerleave", limparTodos);
    alvo.addEventListener("blur", function () { if (!g.trocando) { limparTodos(); } });
    alvo.addEventListener("keydown", function (ev) {
      if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") { return; }
      ev.preventDefault();
      var base = cruzEm != null ? cruzEm : (g.fim ? g.fim[0] : minutoSP(Date.now()));
      var m = Math.max(DE, Math.min(ATE, base + (ev.key === "ArrowLeft" ? -5 : 5)));
      var r = svg.getBoundingClientRect();
      marcarTodos(m, g, r.left + x(m) * (r.width / w), r.top + 20);
    });
    if (foco) { alvo.focus({ preventScroll: true }); }    // o foco do teclado fica no gráfico novo
    return g;
  }
  var dica = document.getElementById("cos-inv-dica"), dicaQuadro = 0;
  function marcarTodos(min, origem, cx, cy) {
    var p0 = origem ? valorEm(origem.pts, min) : null;
    var alvoMin = p0 ? p0[0] : min;
    cruzEm = alvoMin;
    graficos.forEach(function (g) {
      if (!g.host.isConnected) { return; }
      var p = valorEm(g.pts, alvoMin);
      g.cruz.setAttribute("x1", g.x(alvoMin)); g.cruz.setAttribute("x2", g.x(alvoMin)); g.cruz.setAttribute("visibility", "visible");
      if (p && p[1] != null) { g.ponto.setAttribute("cx", g.x(p[0])); g.ponto.setAttribute("cy", g.y(p[1])); g.ponto.setAttribute("visibility", "visible"); }
      else { g.ponto.setAttribute("visibility", "hidden"); }
      if (g.aoMarcar) { g.aoMarcar(p, alvoMin); }
    });
    if (dica && cx != null) {
      dica.textContent = "";
      var b = document.createElement("b"); b.textContent = p0 && p0[1] != null ? kw(p0[1]) : "sem amostra";
      var s = document.createElement("span"); s.textContent = hhmm(alvoMin) + (origem && origem.nome ? " · " + origem.nome : "");
      dica.appendChild(b); dica.appendChild(s); dica.hidden = false;
      cancelAnimationFrame(dicaQuadro);
      dicaQuadro = requestAnimationFrame(function () {          // a posição lida e escrita num quadro só
        dica.style.left = Math.min(window.innerWidth - dica.offsetWidth - 8, cx + 14) + "px";
        dica.style.top = Math.max(8, cy - 40) + "px";
      });
    }
  }
  function limparTodos() {
    cruzEm = null;
    graficos.forEach(function (g) { g.cruz.setAttribute("visibility", "hidden"); g.ponto.setAttribute("visibility", "hidden"); if (g.aoMarcar) { g.aoMarcar(null, null); } });
    if (dica) { dica.hidden = true; }
  }

  // ── 1. a GRADE em tempo real ────────────────────────────────────────────────────────────────────────────────────
  function mapaDosCartoes(m) { var o = {}; (m && m.cartoes || []).forEach(function (c) { o[c.pid] = c; }); return o; }
  function contar(c) {
    var n = { fora: 0, semcom: 0, total: (c.inversores || []).length };
    (c.inversores || []).forEach(function (i) { var e = ESTADO[i.veredito]; if (e && e.grupo) { n[e.grupo]++; } });
    return n;
  }
  function curvaDoCartao(svg) {                          // a série de 15 min que o servidor desenhou (no próprio SVG)
    if (svg._curva) { return svg._curva; }
    var de = String(svg.getAttribute("data-de") || "").split(":"), passo = +svg.getAttribute("data-passo") || 15;
    var m0 = de.length === 2 ? (+de[0]) * 60 + (+de[1]) : NaN;
    svg._curva = isNaN(m0) ? [] : String(svg.getAttribute("data-kw") || "").split("|").map(function (v, k) { return [m0 + k * passo, v === "" ? null : +v]; })
      .filter(function (p) { return p[0] >= DE && p[0] <= ATE; });
    return svg._curva;
  }
  function escrever(no, prop, valor) { if (no && no[prop] !== valor) { no[prop] = valor; } }
  function redesenharCartao(art, gid) {
    var svg = art.querySelector("svg.cos-curva, svg.cos-tv-cv");
    if (!svg) { return; }
    var base = curvaDoCartao(svg);
    if (!base.length) { return; }
    var vb = svg.viewBox && svg.viewBox.baseVal, W = vb && vb.width || 160, H = vb && vb.height || 36;
    var pts = comPonta(base, "u:" + gid), max = Math.max(maximo(pts), 1);
    var sig = pts.length + "|" + max + "|" + (pts.length ? pts[pts.length - 1][1] : "");
    if (svg._sig === sig) { return; }
    svg._sig = sig;
    var d = caminhos(pts, function (m) { return (m - DE) / (ATE - DE) * W; }, function (v) { return H - Math.max(0, Math.min(1, v / max)) * (H - 2) - 1; });
    var area = svg.querySelector(".cos-curva-area"), linha = svg.querySelector(".cos-curva-linha");
    if (area) { area.setAttribute("d", d[1]); }
    if (linha) { linha.setAttribute("d", d[0]); }
  }
  function aplicarNaGrade(m, agoraMs) {
    var mapa = mapaDosCartoes(m), fora = 0, semcom = 0, vistos = {};
    Object.keys(mapa).forEach(function (pid) { anotarPonta("u:" + pid, mapa[pid].pac_total_kw, agoraMs); });
    document.querySelectorAll(SELETOR).forEach(function (art) {
      var gid = art.getAttribute("data-gid"), c = mapa[gid];
      if (!c) { return; }
      var gerando = c.situacao && c.situacao.chave === "GERANDO", n = contar(c);
      if (gerando && !vistos[gid]) { vistos[gid] = 1; fora += n.fora; semcom += n.semcom; }
      if (art.hidden || art.closest("[hidden]")) { return; }   // a página do videowall que não está na tela
      var k = art.querySelector(".kw");
      if (k && c.pac_total_kw != null) { escrever(k, "textContent", kw(c.pac_total_kw)); }
      redesenharCartao(art, gid);
      var alerta = /--(parada|semcom|velha)\b/.test(art.className), st = art.querySelector(".st");
      var marca = !alerta && gerando && n.total ? (n.fora ? "fora" : n.semcom ? "semcom" : "") : "";
      art.classList.toggle("cos-inv--fora", marca === "fora");
      art.classList.toggle("cos-inv--semcom", marca === "semcom");
      if (alerta || !gerando || !n.total) { return; }
      if (!st && k) { st = document.createElement("span"); k.insertAdjacentElement("beforebegin", st); }
      if (!st) { return; }
      var partes = [];
      if (n.fora) { partes.push(n.fora + (n.fora === 1 ? " desligado" : " desligados")); }
      if (n.semcom) { partes.push(n.semcom + " sem comunicação"); }
      escrever(st, "className", marca === "fora" ? "st st--inv" : marca === "semcom" ? "st st--semresp" : "st st--normal");
      escrever(st, "textContent", partes.length ? partes.join(" · ") + " · " + (n.total - n.fora - n.semcom) + "/" + n.total : n.total + "/" + n.total + " inversores");
      escrever(st, "title", "Estado de cada inversor no SCADA, ao vivo");
    });
    var num = document.getElementById("cos-mon-inv");      // o número da faixa da tela normal
    if (num) {
      num.hidden = false;
      var v = num.querySelector('[data-inv="fora"]'), s2 = num.querySelector('[data-inv="semcom"]');
      if (v) { escrever(v, "textContent", String(fora)); v.classList.toggle("ruim", fora > 0); }
      if (s2) { escrever(s2, "textContent", String(semcom)); }
    }
  }

  // ── o laço de 3 s (o mesmo ritmo do Monitoramento da Ronda COS); um só, mesmo com a aba indo e voltando ──────────
  var vivo = null, mapaVivo = {}, vivoEm = 0, laco = null, falhas = 0, voando = false, aberta = null;
  function rotuloLido() {                                // "SCADA ao vivo · hh:mm:ss": no frescor da tela, ou no canto do videowall
    var r = document.getElementById("cos-inv-vivo");
    if (r) { return r; }
    r = document.createElement("span"); r.id = "cos-inv-vivo";
    var lido = document.getElementById("cos-mon-lido");
    if (lido && lido.parentNode) { r.className = "cos-inv-vivo"; lido.parentNode.appendChild(document.createElement("br")); lido.parentNode.appendChild(r); }
    else { r.className = "cos-inv-vivo cos-inv-vivo--canto"; document.body.appendChild(r); }
    return r;
  }
  function proximo(ms) { clearTimeout(laco); laco = setTimeout(lerVivo, ms); }
  function lerVivo() {
    if (voando) { return; }
    if (document.hidden) { proximo(VIVO_MS); return; }
    voando = true;
    pedir("/scada/monitoramento?entradas=separadas").then(function (m) {
      voando = false; falhas = 0;
      proximo(VIVO_MS);                                 // o próximo já marcado: um erro de desenho não para o laço
      vivo = m; mapaVivo = mapaDosCartoes(m); vivoEm = Date.now();
      try { aplicarNaGrade(m, vivoEm); } catch (e) { console.error("inversores: a grade", e); }
      try { if (aberta) { aoVivoNaJanela(); } } catch (e) { console.error("inversores: a janela", e); }
      escrever(rotuloLido(), "textContent", "SCADA ao vivo · " + hhmmss(vivoEm));
      var nota = document.getElementById("cos-inv-nota"); if (nota) { nota.remove(); }
    }, function (e) {
      voando = false; falhas++;
      if (e && (e.login || e.fora)) { notaDeLogin(e); proximo(15000); return; }
      proximo(Math.min(30000, VIVO_MS * Math.pow(2, falhas)));
    });
  }
  function notaDeLogin(e) {
    if (document.getElementById("cos-inv-nota")) { return; }
    var n = document.createElement("div"); n.id = "cos-inv-nota"; n.className = "cos-inv-nota";
    if (e && e.fora) { n.textContent = "O ao vivo dos inversores está desligado: falta o endereço da API da Ronda COS (NEXUS_COS_API_URL)."; }
    else if (CFG.pelaPorta) { n.textContent = "A sessão do Nexus venceu: recarregue a página para entrar de novo e voltar ao tempo real."; }
    else {
      n.appendChild(document.createTextNode(CFG.semLogin
        ? "Para o tempo real, alguém precisa entrar uma vez no Console no notebook do protótipo (ou aqui, no "
        : "Para o tempo real (de 3 em 3 s, como na Ronda COS), entre uma vez no "));
      var a = document.createElement("a"); a.href = CFG.console || "#"; a.target = "_top"; a.textContent = "Console"; n.appendChild(a);
      n.appendChild(document.createTextNode(CFG.semLogin ? ")." : "."));
    }
    document.body.appendChild(n);
  }
  document.addEventListener("visibilitychange", function () { if (!document.hidden) { proximo(0); } });
  var corpoGrade = document.getElementById("cos-tv-corpo") || document.getElementById("cos-mon-corpo");
  if (corpoGrade && window.MutationObserver) {
    // a grade inteira é trocada pelo servidor a cada 30 s: a leitura ao vivo volta por cima na hora
    new MutationObserver(function () { if (vivo) { try { aplicarNaGrade(vivo, vivoEm); } catch (e) { console.error(e); } } })
      .observe(corpoGrade, { childList: true });
  }

  // ── 2. a JANELA da usina, em tempo real ─────────────────────────────────────────────────────────────────────────
  var dlg = document.getElementById("cos-inv-dlg");
  var corpo = dlg && dlg.querySelector(".cos-inv-corpo"), lido = dlg && dlg.querySelector(".cos-inv-lido");
  if (dlg && dica && dica.parentNode !== dlg) { dlg.appendChild(dica); }   // a dica dentro da janela (a camada de cima)
  var curva = null, curvaEm = 0, assinatura = "", partes = null;
  var curvas = {}, ordemCurvas = [], pedidosCurva = {}, falhouEm = {};
  var SEM_CURVA = { usina: [], inversores: [] };

  function pilula(tom, texto) { var s = document.createElement("span"); s.className = "cn-pill cn-" + tom; s.textContent = texto; return s; }
  function bloco(titulo, detalhe) {
    var d = document.createElement("section"); d.className = "cos-inv-bloco";
    var cab = document.createElement("div"); cab.className = "cos-inv-bloco-cab";
    var h = document.createElement("h3"); h.textContent = titulo; cab.appendChild(h);
    var s = document.createElement("span"); s.className = "d"; s.textContent = detalhe || ""; cab.appendChild(s);
    d.appendChild(cab); d._detalhe = s; return d;
  }
  function cosDaUsina(codigo) {
    var l = (CFG.inversoresAbertos || {})[codigo] || [];
    if (!l.length) { return null; }
    var p = document.createElement("p"); p.className = "cos-inv-cos";
    var b = document.createElement("b"); b.textContent = "Aberto no COS (a usina inteira): "; p.appendChild(b);
    p.appendChild(document.createTextNode(l.map(function (x) {
      return String(x[0]) + " — " + String(x[1] || "").toLowerCase() + (x[3] ? " desde " + String(x[3]).slice(8, 10) + "/" + String(x[3]).slice(5, 7) : "") + (x[2] ? " · OS " + x[2] : "");
    }).join("; ")));
    return p;
  }
  function ordenados(c) {
    return (c.inversores || []).slice().sort(function (a, b) { return (ORDEM[a.veredito] || 9) - (ORDEM[b.veredito] || 9) || a.modbus_id - b.modbus_id; });
  }

  // monta a estrutura uma vez; a cada 3 s só os números, os estados e os gráficos que mudaram
  function montar(c) {
    partes = { invs: {} };
    var frag = document.createDocumentFragment();
    var res = document.createElement("div"); res.className = "cos-inv-resumo";
    partes.kw = document.createElement("span"); partes.kw.className = "kw"; res.appendChild(partes.kw);
    partes.resumo = document.createElement("span"); partes.resumo.className = "d"; res.appendChild(partes.resumo);
    partes.estados = document.createElement("span"); partes.estados.className = "cos-inv-estados"; res.appendChild(partes.estados);
    frag.appendChild(res);
    var cos = cosDaUsina(aberta.getAttribute("data-codigo")); if (cos) { frag.appendChild(cos); }
    var bu = bloco("A usina hoje", "a curva gravada de 5 em 5 min e a ponta ao vivo, de 3 em 3 s · passe o mouse (ou use as setas) para ler a hora");
    partes.gu = document.createElement("div"); partes.gu.className = "cos-inv-graf"; bu.appendChild(partes.gu); frag.appendChild(bu);
    var bi = bloco("Cada inversor", ""); partes.escala = bi._detalhe;
    var grade = document.createElement("div"); grade.className = "cos-inv-grade"; bi.appendChild(grade); frag.appendChild(bi);
    ordenados(c).forEach(function (i) {
      var p = {};
      p.art = document.createElement("article");
      var cab = document.createElement("div"); cab.className = "cos-inv-i-cab";
      var nb = document.createElement("b"); nb.textContent = i.nome || ("Inversor " + i.modbus_id); cab.appendChild(nb);
      p.kv = document.createElement("span"); p.kv.className = "cos-inv-i-kw"; cab.appendChild(p.kv);
      p.art.appendChild(cab);
      p.estado = document.createElement("div"); p.estado.className = "cos-inv-estado"; p.art.appendChild(p.estado);
      p.graf = document.createElement("div"); p.graf.className = "cos-inv-graf"; p.art.appendChild(p.graf);
      grade.appendChild(p.art);
      partes.invs[i.id] = p;
    });
    var tab = document.createElement("details"); tab.className = "cos-inv-tabela";
    var su = document.createElement("summary"); su.className = "cn-link"; su.textContent = "Ver os inversores em tabela"; tab.appendChild(su);
    var t = document.createElement("table");
    t.innerHTML = "<thead><tr><th>Inversor</th><th>Estado</th><th class='n'>Agora</th><th class='n'>Máximo hoje</th><th class='n'>Energia hoje</th></tr></thead>";
    partes.tbody = document.createElement("tbody"); t.appendChild(partes.tbody); tab.appendChild(t); frag.appendChild(tab);
    corpo.textContent = ""; corpo.appendChild(frag);
  }

  function atualizar(c, cv) {
    cv = cv || SEM_CURVA;
    var gerando = c.situacao && c.situacao.chave === "GERANDO";
    var sig = ordenados(c).map(function (i) { return i.id + "=" + i.veredito; }).join(",");
    if (!partes || sig !== assinatura) { assinatura = sig; montar(c); }
    graficos = [];
    escrever(partes.kw, "textContent", kw(c.pac_total_kw));
    escrever(partes.resumo, "textContent", c.inversores_online + " de " + c.inversores_total + " inversores respondendo · " + (c.situacao ? c.situacao.texto : ""));
    var conta = {}, chips = [];
    (c.inversores || []).forEach(function (i) { conta[i.veredito] = (conta[i.veredito] || 0) + 1; });
    Object.keys(conta).sort(function (a, b) { return (ORDEM[a] || 9) - (ORDEM[b] || 9); }).forEach(function (v) { chips.push(v + conta[v]); });
    if (partes.estados._sig !== chips.join()) {
      partes.estados._sig = chips.join(); partes.estados.textContent = "";
      Object.keys(conta).sort(function (a, b) { return (ORDEM[a] || 9) - (ORDEM[b] || 9); }).forEach(function (v) {
        var e = ESTADO[v] || { rotulo: v, tom: "neutro" };
        partes.estados.appendChild(pilula(gerando || !e.grupo ? e.tom : "neutro", conta[v] + " " + e.rotulo.toLowerCase()));
      });
    }
    var porId = {};
    (cv.inversores || []).forEach(function (s) { var id = s.usina_id + ":" + s.modbus_id; porId[id] = comPonta(serie(s.pontos), "i:" + id); });
    var invs = ordenados(c), maxInv = 0;
    invs.forEach(function (i) { maxInv = Math.max(maxInv, maximo(porId[i.id] || []), i.pac || 0); });
    var tetoInv = tetoBonito(maxInv, 2);
    escrever(partes.escala, "textContent", cv === SEM_CURVA ? "lendo a curva gravada do dia… os pontos ao vivo já aparecem"
      : "todos na mesma escala (0 a " + kw(tetoInv) + "): quem gera menos fica visivelmente mais baixo");
    // as larguras lidas antes de desenhar (um layout só, e não um por gráfico)
    var larguraUsina = partes.gu.clientWidth, larguras = {};
    invs.forEach(function (i) { var p = partes.invs[i.id]; if (p) { larguras[i.id] = p.graf.clientWidth; } });
    var pu = comPonta(serie(cv.usina), "u:" + aberta.getAttribute("data-gid"));
    grafico(partes.gu, pu, { h: 230, max: tetoBonito(maximo(pu), 4), eixoX: true, eixoY: true, rotuloFim: true, vivo: true, nome: "usina", rotulo: "Curva de hoje da usina" }, larguraUsina);
    var linhas = [];
    invs.forEach(function (i) {
      var p = partes.invs[i.id]; if (!p) { return; }
      var e = ESTADO[i.veredito] || { rotulo: i.veredito || "—", tom: "neutro" };
      var grupo = gerando && e.grupo ? e.grupo : "";
      escrever(p.art, "className", "cos-inv-i" + (grupo === "fora" ? " cos-inv-i--fora" : grupo === "semcom" ? " cos-inv-i--semcom" : ""));
      var kwAgora = function () { p.kv.textContent = kw(i.pac); var sm = document.createElement("small"); sm.textContent = "agora"; p.kv.appendChild(sm); };
      if (cruzEm == null) { kwAgora(); }
      var motivo = i.veredito === "FALHA" ? (i.descricao_falha || i.estado) : (e.grupo === "semcom" ? "não responde ao SCADA: pode estar gerando" : (e.grupo ? i.estado : ""));
      var sigEstado = e.rotulo + "|" + grupo + "|" + (motivo || "");
      if (p.estado._sig !== sigEstado) {
        p.estado._sig = sigEstado; p.estado.textContent = "";
        p.estado.appendChild(pilula(grupo ? e.tom : (e.grupo ? "neutro" : e.tom), e.rotulo));
        if (motivo) { var mo = document.createElement("span"); mo.className = "cos-inv-motivo"; mo.textContent = motivo; p.estado.appendChild(mo); }
      }
      grafico(p.graf, porId[i.id] || [], { h: 78, max: tetoInv, grupo: grupo, vivo: true, nome: i.nome || ("Inversor " + i.modbus_id),
        rotulo: "Curva de hoje de " + (i.nome || i.modbus_id),
        aoMarcar: function (pt, min) {
          if (min == null) { kwAgora(); return; }
          p.kv.textContent = pt && pt[1] != null ? kw(pt[1]) : "—";
          var sm = document.createElement("small"); sm.textContent = "às " + hhmm(min); p.kv.appendChild(sm);
        } }, larguras[i.id]);
      var mx = null;
      (porId[i.id] || []).forEach(function (q) { if (q[1] != null && (!mx || q[1] > mx[1])) { mx = q; } });
      linhas.push([i.nome || ("Inversor " + i.modbus_id), e.rotulo, kw(i.pac), mx ? kw(mx[1]) + " às " + hhmm(mx[0]) : "—",
        i.geracao_dia != null ? fmtKW.format(i.geracao_dia) + " kWh" : "—"]);
    });
    var sigTab = JSON.stringify(linhas);
    if (partes.tbody._sig !== sigTab) {
      partes.tbody._sig = sigTab; partes.tbody.textContent = "";
      linhas.forEach(function (l) {
        var tr = document.createElement("tr");
        l.forEach(function (v, k) { var td = document.createElement("td"); if (k >= 2) { td.className = "n"; } td.textContent = v; tr.appendChild(td); });
        partes.tbody.appendChild(tr);
      });
    }
    if (cruzEm != null) { marcarTodos(cruzEm, null, null, null); }      // a cruz fica onde estava
  }

  function aoVivoNaJanela() {
    if (!aberta || !vivo || aberta._sunop) { return; }
    var gid = aberta.getAttribute("data-gid"), c = mapaVivo[gid];
    if (!c) {
      aviso("Esta usina não veio no monitoramento do SCADA agora. A janela tenta de novo a cada 3 segundos.");
      return;
    }
    var guardada = curvas[gid];
    if (guardada) { curva = guardada.cv; curvaEm = guardada.em; }
    (c.inversores || []).forEach(function (i) { anotarPonta("i:" + i.id, i.pac, vivoEm); });
    atualizar(c, curva);
    escrever(lido, "textContent", "ao vivo · " + hhmmss(vivoEm) + (curva ? " · curva gravada lida às " + hhmmss(curvaEm) : " · lendo a curva do dia…"));
    if (!curva || Date.now() - curvaEm > CURVA_MS) {
      lerCurva(gid).then(function () { if (aberta && aberta.getAttribute("data-gid") === gid) { aoVivoNaJanela(); } }, function () {});
    }
  }
  function guardarCurva(gid, cv) {                       // as últimas CURVAS_GUARDADAS usinas (a pré-busca não enche a memória)
    curvas[gid] = { cv: cv, em: Date.now() };
    ordemCurvas = ordemCurvas.filter(function (g) { return g !== gid; }).concat([gid]);
    while (ordemCurvas.length > CURVAS_GUARDADAS) { delete curvas[ordemCurvas.shift()]; }
  }
  function lerCurva(gid) {
    if (pedidosCurva[gid]) { return pedidosCurva[gid]; }
    if (falhouEm[gid] && Date.now() - falhouEm[gid] < 30000) { return Promise.reject({ erro: "a curva falhou há pouco; tenta de novo em 30 s" }); }
    var guardada = curvas[gid];
    if (guardada && Date.now() - guardada.em < CURVA_MS) { return Promise.resolve(guardada.cv); }
    var c = mapaVivo[gid];
    if (!c) { return Promise.reject({ erro: "o cartão desta usina não veio no monitoramento do SCADA agora" }); }
    pedidosCurva[gid] = pedir("/scada/curva/" + encodeURIComponent((c.usina_ids && c.usina_ids.length ? c.usina_ids : [c.usina_id]).join(",")))
      .then(function (cv) { cv = cv || SEM_CURVA; guardarCurva(gid, cv); delete pedidosCurva[gid]; return cv; },
            function (e) { delete pedidosCurva[gid]; falhouEm[gid] = Date.now(); throw e; });
    return pedidosCurva[gid];
  }
  function aviso(texto) {
    var p = document.createElement("p"); p.className = "cos-inv-aviso"; p.textContent = texto;
    corpo.textContent = ""; corpo.appendChild(p); partes = null; assinatura = "";
  }
  function abrir(art) {
    aberta = art; curva = null; partes = null; assinatura = "";
    var gid = art.getAttribute("data-gid");
    var n = art.querySelector(".n");
    dlg.querySelector(".cos-inv-titulo").textContent = n ? n.textContent : "";
    dlg.querySelector(".cos-inv-sub").textContent = [art.getAttribute("data-cliente"), art.getAttribute("data-fonte")].filter(Boolean).join(" · ");
    lido.textContent = "";
    corpo.textContent = "";
    var lendo = document.createElement("p"); lendo.className = "mudo"; lendo.textContent = "Lendo os inversores na Ronda COS…"; corpo.appendChild(lendo);
    if (typeof dlg.showModal === "function") { if (!dlg.open) { dlg.showModal(); } } else { dlg.setAttribute("open", ""); }
    art._sunop = art.getAttribute("data-fonte") === "SunOP" || String(gid).indexOf("sunop-") === 0;
    if (art._sunop) {
      aviso("Usina do SunOP: a curva por inversor depende do portal do SunOP, que está recusando a conta da plataforma desde 09/11 (o token oficial está pendente).");
      return;
    }
    if (vivo && mapaVivo[gid]) { aoVivoNaJanela(); return; }
    var pedidoEm = Date.now();
    pedir("/scada/monitoramento?entradas=separadas").then(function (m) {
      if (!aberta || aberta.getAttribute("data-gid") !== gid) { return; }      // a janela já mudou de usina
      if (pedidoEm > vivoEm) { vivo = m; mapaVivo = mapaDosCartoes(m); vivoEm = Date.now(); }
      aoVivoNaJanela();
    }).catch(function (e) {
      if (!aberta || aberta.getAttribute("data-gid") !== gid) { return; }
      if (e && e.fora) { aviso("Os inversores ao vivo precisam do endereço da API da Ronda COS (NEXUS_COS_API_URL), que este Nexus ainda não tem."); }
      else if (e && e.login && CFG.pelaPorta) { aviso("A sessão do Nexus venceu: recarregue a página e clique na usina de novo."); }
      else if (e && e.login) { aviso("Falta o login da Ronda COS neste navegador: entre uma vez no Console (no desenho final o login vem do Nexus) e clique na usina de novo."); }
      else { aviso("Não deu para ler os inversores: " + ((e && e.erro) || e) + "."); }
    });
  }
  function fechar() { aberta = null; curva = null; partes = null; assinatura = ""; limparTodos(); graficos = []; if (dlg.open) { dlg.close(); } }

  if (dlg) {
    var antes = null;
    var preCarregar = function (ev) {
      var art = ev.target.closest && ev.target.closest(SELETOR);
      clearTimeout(antes);
      if (!art || !vivo) { return; }
      antes = setTimeout(function () { lerCurva(art.getAttribute("data-gid")).catch(function () {}); }, 150);
    };
    document.addEventListener("pointerover", preCarregar);
    document.addEventListener("focusin", preCarregar);
    document.addEventListener("click", function (ev) {
      if (ev.target.closest && ev.target.closest("a")) { return; }            // o link da ficha leva à ficha
      var art = ev.target.closest && ev.target.closest(SELETOR);
      if (art && !dlg.contains(art)) { abrir(art); }
    });
    document.addEventListener("keydown", function (ev) {
      var art = ev.target.closest && ev.target.closest(SELETOR);
      if (!art || ev.target !== art) { return; }                              // Enter no link da ficha é da ficha
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); abrir(art); }
    });
    dlg.querySelector(".cos-inv-fechar").addEventListener("click", fechar);
    dlg.addEventListener("close", fechar);
    dlg.addEventListener("click", function (ev) { if (ev.target === dlg) { fechar(); } });
    var redim = null;
    window.addEventListener("resize", function () { clearTimeout(redim); redim = setTimeout(function () { if (aberta && vivo) { partes = null; assinatura = ""; aoVivoNaJanela(); } }, 150); });
  }
  lerVivo();
})();
