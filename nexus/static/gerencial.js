/* Comando › Visão gerencial (teste), 19/11/2026: o portfólio que afunila em três níveis, cada um com a sua capa.

   Levi, 18 e 19/11/2026: "Quero uma visão do portfólio inteiro puxando mensal por contratos da parte de COMANDO > CONTRATOS.
   Portfólio Grid Co, clientes, usinas, MWp e valor mensal, depois vai afunilando, clientes e depois usinas"; para o
   portfólio, "algo bem performático focando no MWp e o símbolo da Grid, alguma animação" e "Símbolo da grid em verde 3D";
   para o cliente, "algo diferenciado" (o parque em blocos) com "um score de contratos" em cima dos blocos, "a cor do bloco
   segue a nota do contrato" e "quando eu clicar na UFV tem que explicar esse número"; "é bom estar filtrado por mês sempre
   mostrando o mês atual"; na usina, "um botão que leva para o prontuário da usina".

   Os dados vêm do dados.json da tela (`torres/comando/gerencial_tela.py`); a nota e os textos que a explicam chegam
   prontos do servidor (`nexus/comando/gerencial.py`): aqui só se desenha. Nada de contrato mora neste arquivo.
   O nível e o mês ficam no endereço (?cliente=&usina=&mes=), para o Voltar do navegador subir um nível.
   As cores do canvas são as dos tokens do tema (lidas a cada desenho): a tela vale no escuro e no claro.
   A animação roda sempre, de propósito (o Windows do Levi manda "movimento reduzido": ele nunca veria).
   Para fotografar a animação parada num instante: &t=8 começa a 8 s do início e &foco=1 deixa o 2º item em foco. */
(function () {
  "use strict";
  var raiz = document.getElementById("vg"), tela = document.getElementById("vg-tela");
  if (!raiz || !tela) return;
  var D = null, E = {cliente: "", usina: "", mes: ""}, ANIMA = {id: 0}, COR = {}, RGB = {}, nivelAntes = "";
  var TAU = Math.PI * 2;

  /* ── utilidades ───────────────────────────────────────────────────────────────────────────────────────────────── */
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]; }); }
  function n(v, casas) { return v == null ? "—" : Number(v).toLocaleString("pt-BR", {minimumFractionDigits: casas || 0, maximumFractionDigits: casas || 0}); }
  function brl(v) { if (v == null) return "sem valor"; if (v >= 1e6) return "R$ " + n(v / 1e6, 2) + " mi"; if (v >= 1e3) return "R$ " + n(v / 1e3, 1) + " mil"; return "R$ " + n(v, 0); }
  function brlCheio(v) { return v == null ? "sem valor" : "R$ " + n(v, 0); }
  function tom(p) { return p == null ? "neutro" : p >= D.regua.em_dia ? "ok" : p >= D.regua.atencao ? "alerta" : "critico"; }
  function dBR(s) { return s ? s.slice(8, 10) + "/" + s.slice(5, 7) + "/" + s.slice(0, 4) : ""; }
  function oMes(id) { return D.meses.filter(function (m) { return m.id === id; })[0] || D.meses[0]; }
  function cli(nome) { return D.clientes.filter(function (c) { return c.cliente === nome; })[0]; }
  function usinas(k) { return k + (k === 1 ? " usina" : " usinas"); }
  function minuscula(t) { return t.charAt(0).toLowerCase() + t.slice(1); }
  /* a usina sem meta e sem PR publicados fica cinza na saúde, mesmo tendo pontos (como o cliente sem performance) */
  function tomSaude(u) { var m = u.meses[D.mes_atual] || {}; return m.meta == null && m.pr == null ? "neutro" : tom(u.pontos); }

  /* as cores do tema de agora, para o canvas */
  function cores() {
    var s = getComputedStyle(document.documentElement), t = function (k) { return s.getPropertyValue(k).trim(); };
    COR = {ok: t("--ok-cheio"), alerta: t("--alerta-cheio"), critico: t("--critico-cheio"), neutro: t("--fraco"), verde: t("--verde"),
      claro: t("--lima-cheio"), verdeEsc: t("--verde-hover"), tinta: t("--tinta"), fundo: t("--fundo"), escuro: t("--sobre-cheio"), branco: t("--sobre-barra")};
    RGB = {};
  }
  function rgb(cor) {
    if (RGB[cor]) return RGB[cor];
    var c = document.createElement("canvas"); c.width = c.height = 1;
    var x = c.getContext("2d"); x.fillStyle = cor; x.fillRect(0, 0, 1, 1);
    var d = x.getImageData(0, 0, 1, 1).data;
    return (RGB[cor] = [d[0], d[1], d[2]]);
  }
  function rgba(cor, a) { return "rgba(" + rgb(cor).join(",") + "," + a + ")"; }
  function mistura(a, b, f) { var x = rgb(a), y = rgb(b); return "rgb(" + x.map(function (v, i) { return Math.round(v + (y[i] - v) * f); }).join(",") + ")"; }

  /* ── o endereço: o nível e o mês ──────────────────────────────────────────────────────────────────────────────── */
  function ler() { var q = new URLSearchParams(location.search); E.cliente = q.get("cliente") || ""; E.usina = q.get("usina") || ""; E.mes = q.get("mes") || ""; }
  function urlDe(o) {
    var q = new URLSearchParams();
    if (o.cliente) q.set("cliente", o.cliente);
    if (o.cliente && o.usina) q.set("usina", o.usina);
    if (o.mes && o.mes !== D.mes_atual) q.set("mes", o.mes);
    var s = q.toString();
    return location.pathname + (s ? "?" + s : "");
  }
  function ir(o) { history.pushState(null, "", urlDe(o)); ler(); desenhar(); }
  function lk(o, texto) { return '<a href="' + esc(urlDe({cliente: o.cliente, usina: o.usina, mes: E.mes})) + '" data-vg-ir data-vg-cliente="' + esc(o.cliente || "") + '" data-vg-usina="' + esc(o.usina || "") + '">' + esc(texto) + "</a>"; }
  function alvo(o) { return ' data-vg-ir data-vg-cliente="' + esc(o.cliente || "") + '" data-vg-usina="' + esc(o.usina || "") + '"'; }

  /* ── pedaços comuns ───────────────────────────────────────────────────────────────────────────────────────────── */
  function seletorMes() {
    return '<div class="vg-meses" role="group" aria-label="Mês">' + D.meses.slice().reverse().map(function (m) {
      return '<button type="button" data-vg-mes="' + m.id + '" aria-pressed="' + (E.mes === m.id) + '">' + m.curto + (m.atual ? " (atual)" : "") + "</button>"; }).join("") + "</div>";
  }
  function contrato(c) {
    if (!c.tem_contrato) return '<span class="vg-chip">sem ficha de contrato</span>';
    if (c.dias_fim == null) return '<span class="vg-chip">sem data de fim</span>';
    if (c.dias_fim < 0) return '<span class="vg-chip vg-chip--critico">vencido há ' + (-c.dias_fim) + " dias</span>";
    if (c.dias_fim < 365) return '<span class="vg-chip vg-chip--alerta">vence em ' + c.dias_fim + " dias</span>";
    return '<span class="mudo">até ' + dBR(c.fim) + "</span>";
  }
  function obrigacoes(c) { var k = c.obrigacoes_atrasadas; return k ? ' <span class="vg-chip vg-chip--alerta">' + (k === 1 ? "1 obrigação atrasada" : k + " obrigações atrasadas") + "</span>" : ""; }
  function nota(v) { return v == null ? '<span class="mudo">fora</span>' : '<span class="vg-pt vg-t-' + tom(v) + '">' + v + "</span>"; }
  function avisos() { return D.avisos.length ? '<p class="vg-aviso">Ficou de fora agora: ' + D.avisos.map(esc).join("; ") + ".</p>" : ""; }
  function rodape() {
    return '<p class="vg-nota" style="margin-top:26px">Dado de ' + esc(D.gerado) + ". Os valores e as datas vêm do Comando › Contratos; a saúde e a nota de cada usina, do que o Nexus já mede. " +
      "A nota de cumprimento do contrato está em teste: os pesos ainda esperam aprovação.</p>";
  }
  function barras() { requestAnimationFrame(function () { [].forEach.call(tela.querySelectorAll(".vg-lin .vg-trilho i"), function (b) { b.style.width = b.getAttribute("data-w"); }); }); }

  /* ── o portfólio: o símbolo em verde 3D, o anel dos MWp por cliente e as usinas em volta ──────────────────────── */
  function capaPortfolio() {
    var T = D.totais, mx = D.clientes.length ? D.clientes[0].mwp || 1 : 1;
    return avisos() + '<section class="vg-pot"><canvas id="vg-cv" role="img" aria-label="Anel com a potência de cada cliente em volta do símbolo da Grid; a lista abaixo traz os mesmos números"></canvas>' +
      '<div class="vg-sim" id="vg-sim" aria-hidden="true"><div class="vg-brilho"></div><div class="vg-3d" id="vg-3d"></div></div>' +
      '<div class="vg-txt"><p class="vg-sobre">Portfólio Grid Co.</p><div class="vg-num"><span id="vg-n">' + n(T.mwp, 1) + "</span><small>MWp</small></div>" +
      '<p class="vg-leg">sob gestão, em ' + usinas(T.usinas) + " de " + T.clientes + " clientes" + (T.valor ? ", por " + brl(T.valor) + " ao mês" : "") + '.</p><div class="vg-foco" id="vg-foco"></div></div></section>' +
      '<p class="vg-nota">O anel reparte os ' + n(T.mwp, 1) + " MWp por cliente, do maior para o menor, com um fio na cor da saúde das usinas dele. Cada ponto é uma usina: o tamanho é a potência e a cor, a saúde (verde em dia, amarelo em atenção, vermelho em risco, cinza sem performance publicada).</p>" +
      '<h2>Potência por cliente</h2><div class="vg-rola"><table class="vg-tab"><thead><tr><th>Cliente</th><th>Potência</th><th class="vg-n">Do portfólio</th><th class="vg-n">Usinas</th><th class="vg-n">Valor mensal</th><th>Saúde</th><th>Usinas</th><th>Contrato</th></tr></thead><tbody>' +
      D.clientes.map(function (c) {
        var k = {critico: 0, alerta: 0, ok: 0}, tot = Math.max(1, c.usinas_n);
        c.usinas.forEach(function (u) { var t = tomSaude(u); if (k[t] != null) k[t]++; });
        return '<tr class="vg-lin"' + alvo({cliente: c.cliente}) + '><td class="vg-nm">' + lk({cliente: c.cliente}, c.cliente) + '</td><td><span class="vg-trilho" style="width:240px"><i data-w="' + (100 * c.mwp / mx) + '%"></i></span> <span class="vg-forte">' + n(c.mwp, 1) + " MWp</span></td>" +
          '<td class="vg-n">' + n(100 * c.mwp / (T.mwp || 1), 1) + '%</td><td class="vg-n">' + c.usinas_n + '</td><td class="vg-n">' + (c.valor ? brlCheio(c.valor) : '<span class="mudo">sem valor</span>') + (c.minuta ? ' <span class="vg-chip">minuta</span>' : "") + "</td>" +
          "<td>" + (c.media == null ? '<span class="vg-chip">sem performance</span>' : '<span class="vg-pt vg-t-' + tom(c.media) + '">' + c.media + "</span>") + "</td>" +
          '<td><span class="vg-seg" style="width:90px">' + ["critico", "alerta", "ok"].map(function (t) { return '<i class="vg-b-' + t + '" style="width:' + (100 * k[t] / tot) + '%"></i>'; }).join("") + "</span></td><td>" + contrato(c) + "</td></tr>"; }).join("") +
      "</tbody></table></div>" + rodape();
  }
  function iniciarPotencia() {
    var cv = document.getElementById("vg-cv");
    if (!cv || !cv.getContext) return;
    var ctx = cv.getContext("2d"), numEl = document.getElementById("vg-n"), focoEl = document.getElementById("vg-foco"), linhas = [].slice.call(tela.querySelectorAll(".vg-lin"));
    var T = D.totais, GAP = 0.016, livre = TAU - GAP * D.clientes.length, a = -Math.PI / 2, q0 = new URLSearchParams(location.search);
    var segs = D.clientes.map(function (c, i) { var da = c.mwp / (T.mwp || 1) * livre, s = {c: c, i: i, a0: a + GAP / 2, a1: a + GAP / 2 + da, cor: COR[tom(c.media)]}; a += da + GAP; return s; });
    function rnd(k) { var x = Math.sin(k * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); }
    var dots = [], k = 0, acum = [], somaM = 0;
    segs.forEach(function (s) { var us = s.c.usinas, m = us.length; us.forEach(function (u, j) { k++; var mw = u.mwp || 0.3;
      dots.push({s: s, ang: s.a0 + (j + 0.5) / m * (s.a1 - s.a0), rr: rnd(k), f1: rnd(k + 500) * TAU, f2: rnd(k + 900) * TAU, vel: 0.5 + rnd(k + 77), tam: 1.6 + Math.sqrt(mw) * 1.25, cor: COR[tomSaude(u)], mwp: mw}); }); });
    dots.forEach(function (d) { somaM += d.mwp; acum.push(somaM); });
    function sorteia() { var r = Math.random() * somaM, lo = 0, hi = acum.length - 1; while (lo < hi) { var mid = (lo + hi) >> 1; if (acum[mid] < r) lo = mid + 1; else hi = mid; } return dots[lo]; }
    var PULA = +(q0.get("t") || 0), parts = [], flashes = [], hover = q0.get("foco") == null ? -1 : +q0.get("foco"), t0 = null, ultimo = 0, cred = 0, G = {};
    /* O símbolo em verde 3D: o PNG da marca é a máscara de N camadas empilhadas na profundidade (a espessura); a da frente
       leva o verde claro com o brilho, a 2ª é o filete do chanfro e as de trás escurecem até o fundo. Só balança (nunca dá
       a volta: de costas a marca apareceria espelhada). */
    var sim = document.getElementById("vg-sim"), tres = document.getElementById("vg-3d"), brilho = sim.querySelector(".vg-brilho");
    var N = 26, PASSO = 1.5, frente = null, rot = {x: -9, y: 0}, rato = {x: 0, y: 0}, simGeo = "", mascara = 'url("' + raiz.getAttribute("data-simbolo") + '")';
    for (var z = N - 1; z >= 0; z--) { var cam = document.createElement("i"); cam.style.transform = "translateZ(" + ((N / 2 - z) * PASSO) + "px)";
      cam.style.webkitMaskImage = mascara; cam.style.maskImage = mascara;
      if (z === 0) { cam.className = "vg-frente"; frente = cam; } else cam.style.background = z === 1 ? COR.claro : mistura(COR.verdeEsc, COR.escuro, 0.12 + 0.76 * (z - 2) / (N - 3));
      tres.appendChild(cam); }
    function geo() { var w = cv.clientWidth, h = cv.clientHeight, dpr = window.devicePixelRatio || 1;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
      var estreito = w < 860, R = Math.max(70, Math.min(168, h / 2 - 150, (estreito ? w / 2 : w * 0.31) - 140));
      G = {w: w, h: h, dpr: dpr, cx: estreito ? w / 2 : w * 0.69, cy: h / 2, R: R, banda: Math.min(100, R * 0.62)}; }
    function pos(d, t) { var ang = d.ang + 0.014 * Math.sin(t * 0.33 * d.vel + d.f1), r = G.R + 30 + d.rr * G.banda + 3.5 * Math.sin(t * 0.5 * d.vel + d.f2);
      return {x: G.cx + Math.cos(ang) * r, y: G.cy + Math.sin(ang) * r, ang: ang, r: r}; }
    function quadro(agora) {
      if (!document.body.contains(cv)) return;                                   // a tela trocou: a animação para sozinha
      if (t0 === null) { t0 = agora - PULA * 1000; if (PULA) { rot.y = 24 * Math.sin(PULA * 0.55); for (var w0 = 0; w0 < 22; w0++) parts.push({d: sorteia(), t: Math.random() * 0.8, dur: 0.9 + Math.random() * 0.7}); } }
      var t = (agora - t0) / 1000, dt = Math.max(0, Math.min(0.05, t - ultimo)); ultimo = t;
      geo(); var c = ctx, R = G.R, m, e = 1 - Math.pow(1 - Math.min(1, t / 1.9), 3), fim = -Math.PI / 2 + e * TAU;
      c.setTransform(G.dpr, 0, 0, G.dpr, 0, 0); c.clearRect(0, 0, G.w, G.h); c.shadowBlur = 0; c.globalAlpha = 1;
      numEl.textContent = n(T.mwp * e, 1);
      c.lineWidth = 1; [0, 0.5, 1].forEach(function (f) { c.strokeStyle = rgba(COR.tinta, f === 1 ? 0.075 : 0.045); c.beginPath(); c.arc(G.cx, G.cy, R + 30 + G.banda * f, 0, TAU); c.stroke(); });
      segs.forEach(function (s) { if (s.a0 >= fim) return; var a1 = Math.min(s.a1, fim), on = hover === s.i, apag = hover >= 0 && !on;
        c.lineCap = "butt"; c.lineWidth = on ? 20 : 14; c.strokeStyle = rgba(COR.verde, apag ? 0.2 : on ? 1 : 0.8); c.beginPath(); c.arc(G.cx, G.cy, R, s.a0, a1); c.stroke();
        c.lineWidth = 3; c.globalAlpha = apag ? 0.3 : 0.95; c.strokeStyle = s.cor; c.beginPath(); c.arc(G.cx, G.cy, R + (on ? 16 : 13), s.a0, a1); c.stroke(); c.globalAlpha = 1; });
      for (var q = 0; q < 3; q++) { var pa = -Math.PI / 2 + ((t * 0.11 + q / 3) % 1) * TAU; if (pa > fim) continue;
        c.lineCap = "butt"; c.lineWidth = 14;
        for (m = 0; m < 9; m++) { c.strokeStyle = rgba(COR.claro, 0.34 * (1 - m / 9)); c.beginPath(); c.arc(G.cx, G.cy, R, pa - 0.05 - (m + 1) * 0.045, pa - 0.05 - m * 0.045); c.stroke(); }
        c.lineCap = "round"; c.shadowColor = COR.claro; c.shadowBlur = 20; c.strokeStyle = mistura(COR.claro, COR.branco, 0.7); c.beginPath(); c.arc(G.cx, G.cy, R, pa - 0.05, pa); c.stroke(); c.shadowBlur = 0; }
      var apar = Math.max(0, Math.min(1, (t - 0.45) / 1.5));
      dots.forEach(function (d) { var vis = Math.max(0, Math.min(1, apar * 1.7 - d.rr * 0.7)); if (!vis) return; var o = pos(d, t), on = hover === d.s.i, apag = hover >= 0 && !on;
        c.globalAlpha = vis * (apag ? 0.14 : on ? 1 : 0.62 + 0.3 * Math.sin(t * (0.7 + d.vel) + d.f1)); c.fillStyle = d.cor; c.beginPath(); c.arc(o.x, o.y, d.tam * (on ? 1.25 : 1), 0, TAU); c.fill(); });
      c.globalAlpha = 1;
      if (t > 1.5 && dots.length) { cred += dt * 16; while (cred >= 1) { cred--; parts.push({d: sorteia(), t: 0, dur: 0.9 + Math.random() * 0.7}); } }
      c.lineWidth = 1.5; c.lineCap = "round";
      for (m = parts.length - 1; m >= 0; m--) { var pt = parts[m]; pt.t += dt; var f = pt.t / pt.dur;
        if (f >= 1) { flashes.push({ang: pt.d.ang, t: 0}); parts.splice(m, 1); continue; }
        var o = pos(pt.d, t), r1 = o.r + (R + 9 - o.r) * f * f, r2 = Math.min(o.r, r1 + 8 + 18 * f), apag = hover >= 0 && hover !== pt.d.s.i;
        c.strokeStyle = rgba(COR.claro, apag ? 0.07 : 0.14 + 0.62 * f); c.beginPath(); c.moveTo(G.cx + Math.cos(o.ang) * r2, G.cy + Math.sin(o.ang) * r2); c.lineTo(G.cx + Math.cos(o.ang) * r1, G.cy + Math.sin(o.ang) * r1); c.stroke(); }
      c.lineCap = "butt"; c.lineWidth = 14;
      for (m = flashes.length - 1; m >= 0; m--) { var fl = flashes[m]; fl.t += dt; if (fl.t > 0.45) { flashes.splice(m, 1); continue; }
        c.strokeStyle = rgba(mistura(COR.claro, COR.branco, 0.7), 0.7 * (1 - fl.t / 0.45)); c.beginPath(); c.arc(G.cx, G.cy, R, fl.ang - 0.013, fl.ang + 0.013); c.stroke(); }
      /* o símbolo 3D: balança sozinho, vira para o mouse e entra de perfil; o brilho da face anda com o giro */
      var lado = (R - 50) * 2, chave = G.cx + "|" + G.cy + "|" + lado;
      if (chave !== simGeo) { simGeo = chave; sim.style.left = (G.cx - lado / 2) + "px"; sim.style.top = (G.cy - lado / 2) + "px"; sim.style.width = lado + "px"; sim.style.height = lado + "px"; }
      rot.y += (24 * Math.sin(t * 0.55) + rato.x * 24 - rot.y) * 0.08; rot.x += (-9 + 5 * Math.sin(t * 0.4) - rato.y * 15 - rot.x) * 0.08;
      var ry = rot.y * e - 84 * (1 - e);
      tres.style.transform = "rotateX(" + rot.x.toFixed(2) + "deg) rotateY(" + ry.toFixed(2) + "deg) scale(" + (0.8 + 0.2 * e).toFixed(3) + ")";
      frente.style.backgroundPosition = (50 + ry * 0.9).toFixed(1) + "% 0, 0 0";
      brilho.style.opacity = (e * (0.75 + 0.25 * Math.sin(t * 1.4))).toFixed(3);
      sim.style.opacity = Math.min(1, t / 0.4).toFixed(2);
      ANIMA.id = requestAnimationFrame(quadro);
    }
    function foco() { var s = segs[hover], c = s && s.c;
      focoEl.innerHTML = c ? "<b>" + esc(c.cliente) + '</b><span><strong>' + n(c.mwp, 1) + " MWp</strong>, " + n(100 * c.mwp / (T.mwp || 1), 1) + "% do portfólio</span><span>" + usinas(c.usinas_n) + (c.valor ? ", " + brl(c.valor) + " por mês" : ", sem valor no contrato lido") + "</span><span>" + (c.media == null ? "Sem performance publicada" : "Saúde média " + c.media + " de 100") + "</span>"
        : '<span class="mudo">Passe o mouse no anel ou na lista para ver um cliente. Clique para abrir.</span>';
      linhas.forEach(function (l, i) { l.classList.toggle("vg-ativo", i === hover); }); }
    function quem(ev) { var b = cv.getBoundingClientRect(), dx = ev.clientX - b.left - G.cx, dy = ev.clientY - b.top - G.cy, dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < G.R - 16 || dist > G.R + 42 + G.banda) return -1;
      var ang = Math.atan2(dy, dx); if (ang < -Math.PI / 2) ang += TAU;
      for (var i = 0; i < segs.length; i++) if (ang >= segs[i].a0 - GAP / 2 && ang < segs[i].a1 + GAP / 2) return i;
      return -1; }
    cv.addEventListener("mousemove", function (ev) { var b = cv.getBoundingClientRect(), h = quem(ev);
      rato.x = Math.max(-1, Math.min(1, (ev.clientX - b.left - G.cx) / (G.w * 0.4))); rato.y = Math.max(-1, Math.min(1, (ev.clientY - b.top - G.cy) / (G.h * 0.5)));
      cv.style.cursor = h >= 0 ? "pointer" : "default"; if (h !== hover) { hover = h; foco(); } });
    cv.addEventListener("mouseleave", function () { rato.x = 0; rato.y = 0; if (hover !== -1) { hover = -1; foco(); } });
    cv.addEventListener("click", function (ev) { var h = quem(ev); if (h >= 0) ir({cliente: segs[h].c.cliente, usina: "", mes: E.mes}); });
    linhas.forEach(function (l, i) { l.addEventListener("mouseenter", function () { hover = i; foco(); }); l.addEventListener("mouseleave", function () { hover = -1; foco(); }); });
    geo(); foco(); barras();
    cancelAnimationFrame(ANIMA.id); ANIMA.id = requestAnimationFrame(quadro);
  }

  /* ── o cliente: o parque em blocos ────────────────────────────────────────────────────────────────────────────────
     Cada usina é um bloco em perspectiva. A ALTURA é a potência, na mesma régua para todos os clientes (a maior usina do
     portfólio dá a altura máxima); a COR e o NÚMERO da tampa são a nota de cumprimento do contrato no mês do filtro. As
     mais altas ficam no fundo, para nenhuma esconder outra. Os riscos que sobem são a energia (quem tem mais MWp solta
     mais) e a faixa clara que atravessa é só luz. */
  function capaCliente(c) {
    var sm = c.score[E.mes] || {}, m = oMes(E.mes), mx = mwpMax();
    return avisos() + '<section class="vg-pot"><canvas id="vg-cv" role="img" aria-label="O parque do cliente em blocos: a altura de cada bloco é a potência da usina; a cor e o número são a nota de cumprimento do contrato; a lista abaixo traz os mesmos números"></canvas>' +
      '<div class="vg-txt"><div class="vg-topo"><p class="vg-trilha">' + lk({}, "Portfólio Grid Co.") + " / cliente</p>" + seletorMes() + '</div><p class="vg-nome">' + esc(c.cliente) + "</p>" +
      '<div class="vg-num vg-num--cli"><span id="vg-n">' + n(c.mwp, 1) + "</span><small>MWp</small></div>" +
      '<p class="vg-leg">em ' + usinas(c.usinas_n) + (c.valor ? ", por " + brl(c.valor) + " ao mês" + (c.minuta ? " (com minuta)" : "") + "." : D.contratos_ok ? ", sem valor no contrato lido." : ".") + "</p>" +
      '<p class="vg-ctr">Contrato: ' + contrato(c) + obrigacoes(c) + "</p>" +
      '<p class="vg-ctr">Cumprimento do contrato: ' + (sm.nota == null ? '<span class="mudo">sem item medido</span>' : '<strong class="vg-t-' + tom(sm.nota) + '">' + sm.nota + "</strong> de 100 em " + m.curto + ", na média de " + usinas(sm.usinas)) + '</p><div class="vg-foco" id="vg-foco"></div></div></section>' +
      '<p class="vg-nota">Cada bloco é uma usina: a altura é a potência, na mesma régua para todos os clientes. A cor e o número na tampa são o cumprimento do contrato da usina em ' + m.nome + (m.atual ? ", até ontem" : ", mês fechado") +
      ", de 0 a 100 (verde " + D.regua.em_dia + " ou mais, amarelo de " + D.regua.atencao + " a " + (D.regua.em_dia - 1) + ", vermelho abaixo de " + D.regua.atencao + ", cinza sem nota): a média de disponibilidade, geração e PR, rotinas e prazos de OS, cada item comparando o que o contrato pede com o que o Nexus mediu. Clique no bloco para ver a conta.</p>" +
      '<h2>Potência por usina</h2><div class="vg-rola"><table class="vg-tab"><thead><tr><th>Usina</th><th>Potência</th><th>Contrato</th><th>Disponibilidade</th><th>Geração e PR</th><th>Rotinas</th><th>Prazos de OS</th><th class="vg-n">Valor mensal</th></tr></thead><tbody>' +
      c.usinas.map(function (u) { var sc = u.score[E.mes];
        return '<tr class="vg-lin"' + alvo({cliente: c.cliente, usina: u.usina}) + '><td class="vg-nm">' + lk({cliente: c.cliente, usina: u.usina}, u.usina) + '</td><td><span class="vg-trilho" style="width:200px"><i data-w="' + (100 * (u.mwp || 0) / mx) + '%"></i></span> <span class="vg-forte">' + n(u.mwp, 1) + " MWp</span></td>" +
          '<td style="font-size:15px">' + nota(sc.nota) + "</td>" + sc.itens.map(function (it) { return "<td>" + nota(it.nota) + "</td>"; }).join("") +
          '<td class="vg-n">' + (u.valor == null ? '<span class="mudo">—</span>' : brlCheio(u.valor)) + "</td></tr>"; }).join("") + "</tbody></table></div>" + rodape();
  }
  function mwpMax() { var mx = 0; D.clientes.forEach(function (c) { c.usinas.forEach(function (u) { if ((u.mwp || 0) > mx) mx = u.mwp; }); }); return mx || 1; }
  function iniciarParque(c) {
    var cv = document.getElementById("vg-cv");
    if (!cv || !cv.getContext) return;
    var ctx = cv.getContext("2d"), numEl = document.getElementById("vg-n"), focoEl = document.getElementById("vg-foco"), linhas = [].slice.call(tela.querySelectorAll(".vg-lin"));
    var us = c.usinas, n0 = us.length, cols = Math.max(1, Math.ceil(Math.sqrt(n0 * 1.25))), rows = Math.max(1, Math.ceil(n0 / cols)), celulas = [], MX = mwpMax(), q0 = new URLSearchParams(location.search);
    for (var r = 0; r < rows; r++) for (var q = 0; q < cols; q++) celulas.push({c: q, r: r});
    celulas.sort(function (a, b) { return (a.c + a.r) - (b.c + b.r) || a.r - b.r; });
    var LADO = 0.78, acum = [], somaM = 0;
    /* a tampa leva a cor da nota inteira; as paredes são a mesma cor quase apagada no escuro, mais clara em cima e mais
       escura no pé (81 blocos de cor cheia viravam enfeite: a cor tem de ser lida na tampa) */
    var blocos = us.map(function (u, k) { var ce = celulas[k], sc = u.score[E.mes], cor = COR[tom(sc.nota)], mx = function (f) { return mistura(cor, COR.escuro, f); };
      return {u: u, k: k, sc: sc, x: ce.c - (cols - 1) / 2, y: ce.r - (rows - 1) / 2, h: 0.14 + 2.5 * (u.mwp || 0) / MX, atraso: 0.9 * (ce.c + ce.r) / Math.max(1, cols + rows - 2),
        topo: cor, dir: [mx(0.5), mx(0.84)], esq: [mx(0.7), mx(0.92)], topoA: mx(0.7), dirA: [mx(0.84), mx(0.93)], esqA: [mx(0.9), mx(0.96)], pol: null, hh: 0, sobe: 0}; });
    blocos.forEach(function (b) { somaM += (b.u.mwp || 0.3); acum.push(somaM); });
    function sorteia() { var x = Math.random() * somaM, lo = 0, hi = acum.length - 1; while (lo < hi) { var mid = (lo + hi) >> 1; if (acum[mid] < x) lo = mid + 1; else hi = mid; } return blocos[lo]; }
    var hAlto = Math.max.apply(null, blocos.map(function (b) { return b.h; }).concat([0.14])), EL0 = 0.6, cam = {fi: Math.PI / 4, el: EL0}, rato = {x: 0, y: 0, px: 0, py: 0, dentro: false};
    var PULA = +(q0.get("t") || 0), hover = -1, hoverLinha = q0.get("foco") == null ? -1 : +q0.get("foco"), ultimoHover = -2, t0 = null, ultimo = 0, cred = 0, parts = [], G = {};
    function geo() { var w = cv.clientWidth, h = cv.clientHeight, dpr = window.devicePixelRatio || 1;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) { cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr); }
      var estreito = w < 860, x0 = estreito ? 0 : w * 0.4, larg = w - x0 - 10, diag = (cols + rows) * 0.7071;
      var S = Math.min(84, larg / (diag + 0.6), (h - 70) / (diag * Math.sin(EL0) + hAlto * Math.cos(EL0)));
      G = {w: w, h: h, dpr: dpr, S: S, cx: x0 + larg / 2, cy: h / 2 + hAlto * Math.cos(EL0) * S / 2}; }
    function proj(x, y, z) { var co = Math.cos(cam.fi), si = Math.sin(cam.fi), xr = x * co - y * si, yr = x * si + y * co;
      return [G.cx + xr * G.S, G.cy + yr * G.S * Math.sin(cam.el) - z * G.S * Math.cos(cam.el), yr]; }
    function face(c2, p, cor) { c2.fillStyle = cor; c2.beginPath(); c2.moveTo(p[0][0], p[0][1]); for (var i = 1; i < p.length; i++) c2.lineTo(p[i][0], p[i][1]); c2.closePath(); c2.fill(); }
    function dentro(p, x, y) { var ok = false; for (var i = 0, j = p.length - 1; i < p.length; j = i++) if ((p[i][1] > y) !== (p[j][1] > y) && x < (p[j][0] - p[i][0]) * (y - p[i][1]) / (p[j][1] - p[i][1]) + p[i][0]) ok = !ok; return ok; }
    function foco() { var b = blocos[hover], u = b && b.u;
      focoEl.innerHTML = u ? "<b>" + esc(u.usina) + "</b><span><strong>" + n(u.mwp, 1) + " MWp</strong>" + (c.mwp ? ", " + n(100 * (u.mwp || 0) / c.mwp, 1) + "% do cliente" : "") + "</span><span>" +
        (b.sc.nota == null ? "Contrato sem nota: menos de dois itens medidos" : "<strong>Contrato " + b.sc.nota + " de 100</strong>: " + b.sc.itens.map(function (it) { return minuscula(it.nome) + " " + (it.nota == null ? "fora" : it.nota); }).join(", ")) +
        "</span><span>" + (u.valor == null ? "Sem ligação com o valor do contrato" : brlCheio(u.valor) + " por mês no contrato") + "</span>"
        : '<span class="mudo">Passe o mouse num bloco ou na lista para ver uma usina. Clique para abrir a conta da nota.</span>';
      linhas.forEach(function (l, i) { l.classList.toggle("vg-ativo", i === hover); }); }
    function quadro(agora) {
      if (!document.body.contains(cv)) return;
      if (t0 === null) { t0 = agora - PULA * 1000; if (PULA && blocos.length) for (var w0 = 0; w0 < 14; w0++) parts.push({b: sorteia(), t: Math.random() * 0.9, dur: 1 + Math.random() * 0.6, ox: Math.random() - 0.5, oy: Math.random() - 0.5}); }
      var t = (agora - t0) / 1000, dt = Math.max(0, Math.min(0.05, t - ultimo)); ultimo = t;
      geo(); var c2 = ctx, S = G.S, i, b, e = 1 - Math.pow(1 - Math.min(1, t / 1.8), 3);
      c2.setTransform(G.dpr, 0, 0, G.dpr, 0, 0); c2.clearRect(0, 0, G.w, G.h); c2.globalAlpha = 1;
      numEl.textContent = n(c.mwp * e, 1);
      cam.fi += (Math.PI / 4 + 0.1 * Math.sin(t * 0.32) + rato.x * 0.2 - cam.fi) * 0.07; cam.el += (EL0 - rato.y * 0.09 - cam.el) * 0.07;
      /* o chão: o brilho (uma elipse que APAGA antes da borda do canvas) e a malha do terreno */
      var ch = proj(0, 0, 0), rg = Math.max(40, Math.min((cols + rows) * 0.5 * S + 110, G.w - ch[0] - 4, ch[0] - 4, (G.h - ch[1] - 4) / 0.6, (ch[1] - 4) / 0.6));
      c2.save(); c2.translate(ch[0], ch[1]); c2.scale(1, 0.6); var gl = c2.createRadialGradient(0, 0, 0, 0, 0, rg);
      gl.addColorStop(0, rgba(COR.verde, 0.13)); gl.addColorStop(0.6, rgba(COR.verde, 0.05)); gl.addColorStop(1, rgba(COR.verde, 0)); c2.fillStyle = gl; c2.beginPath(); c2.arc(0, 0, rg, 0, TAU); c2.fill(); c2.restore();
      c2.lineWidth = 1; c2.strokeStyle = rgba(COR.tinta, 0.055); c2.beginPath();
      var mx = cols / 2 + 1, my = rows / 2 + 1, a1, a2;
      for (i = -mx; i <= mx + 0.01; i++) { a1 = proj(i, -my, 0); a2 = proj(i, my, 0); c2.moveTo(a1[0], a1[1]); c2.lineTo(a2[0], a2[1]); }
      for (i = -my; i <= my + 0.01; i++) { a1 = proj(-mx, i, 0); a2 = proj(mx, i, 0); c2.moveTo(a1[0], a1[1]); c2.lineTo(a2[0], a2[1]); }
      c2.stroke();
      /* os blocos, do fundo para a frente */
      var ordem = blocos.slice().sort(function (p1, p2) { return (p1.x - p2.x) * Math.sin(cam.fi) + (p1.y - p2.y) * Math.cos(cam.fi); });
      var faixa = ((t * 0.16) % 1) * ((cols + rows) * 0.7071 + 6) - (cols + rows) * 0.35 - 3;
      ordem.forEach(function (b) { var x = Math.max(0, Math.min(1, (t - 0.2 - b.atraso) / 0.85)), sobe = x <= 0 ? 0 : 1 + 2.2 * Math.pow(x - 1, 3) + 1.2 * Math.pow(x - 1, 2);
        var on = hover === b.k, apag = hover >= 0 && !on; b.sobe += ((on ? 0.16 : 0) - b.sobe) * 0.2;
        var hh = b.h * sobe, z0 = b.sobe, m = LADO / 2, x0 = b.x - m, x1 = b.x + m, y0 = b.y - m, y1 = b.y + m; b.hh = hh + z0;
        var A = proj(x0, y0, hh + z0), B = proj(x1, y0, hh + z0), Dd = proj(x1, y1, hh + z0), Ee = proj(x0, y1, hh + z0), B0 = proj(x1, y0, z0), D0 = proj(x1, y1, z0), E0 = proj(x0, y1, z0);
        b.pol = [[A, B, Dd, Ee], [B, Dd, D0, B0], [Ee, Dd, D0, E0]];
        if (sobe <= 0) return;
        var pe = Math.max(B0[1], D0[1], E0[1]), alto = Math.min(B[1], Dd[1], Ee[1]);
        [[2, apag ? b.esqA : b.esq], [1, apag ? b.dirA : b.dir]].forEach(function (pr) { var gr = c2.createLinearGradient(0, alto, 0, Math.max(alto + 1, pe)); gr.addColorStop(0, pr[1][0]); gr.addColorStop(1, pr[1][1]); face(c2, b.pol[pr[0]], gr); });
        face(c2, b.pol[0], apag ? b.topoA : b.topo);
        if (!apag) { var d = (b.x - b.y) * 0.7071 - faixa, luz = Math.exp(-d * d / 0.9); if (luz > 0.02) face(c2, b.pol[0], rgba(COR.branco, (0.5 * luz).toFixed(3)));
          c2.strokeStyle = rgba(COR.branco, on ? 0.9 : 0.28); c2.lineWidth = on ? 1.6 : 1; c2.beginPath(); c2.moveTo(A[0], A[1]); c2.lineTo(B[0], B[1]); c2.lineTo(Dd[0], Dd[1]); c2.lineTo(Ee[0], Ee[1]); c2.closePath(); c2.stroke(); }
        /* o número na tampa: a nota de cumprimento do contrato da usina no mês; sem nota, sem número */
        if (b.sc.nota != null && sobe > 0.85) { var fs = Math.max(10, Math.min(17, S * 0.27));
          c2.font = "700 " + fs.toFixed(1) + 'px Poppins, "Segoe UI", sans-serif'; c2.textAlign = "center"; c2.textBaseline = "middle"; c2.fillStyle = rgba(COR.escuro, apag ? 0.45 : 0.92);
          c2.fillText(String(b.sc.nota), (A[0] + Dd[0]) / 2, (A[1] + Dd[1]) / 2 + 0.5); c2.textAlign = "left"; } });
      /* a energia subindo */
      if (t > 1.4 && blocos.length) { cred += dt * (3 + Math.min(14, n0 * 0.5)); while (cred >= 1) { cred--; parts.push({b: sorteia(), t: 0, dur: 1 + Math.random() * 0.6, ox: Math.random() - 0.5, oy: Math.random() - 0.5}); } }
      c2.lineWidth = 2; c2.lineCap = "round";
      for (i = parts.length - 1; i >= 0; i--) { var pt = parts[i]; pt.t += dt; var f = pt.t / pt.dur; if (f >= 1) { parts.splice(i, 1); continue; }
        b = pt.b; var z = b.hh + 0.12 + 1.3 * f, p1 = proj(b.x + pt.ox * LADO * 0.8, b.y + pt.oy * LADO * 0.8, z), p2 = proj(b.x + pt.ox * LADO * 0.8, b.y + pt.oy * LADO * 0.8, z - 0.24 - 0.12 * f);
        c2.strokeStyle = rgba(COR.claro, ((hover >= 0 && hover !== b.k ? 0.12 : 0.85) * Math.sin(Math.PI * f)).toFixed(3)); c2.beginPath(); c2.moveTo(p1[0], p1[1]); c2.lineTo(p2[0], p2[1]); c2.stroke(); }
      /* quem está sob o mouse: testa da frente para o fundo */
      var novo = hoverLinha;
      if (rato.dentro) { novo = -1; for (i = ordem.length - 1; i >= 0 && novo < 0; i--) { b = ordem[i]; if (b.pol && (dentro(b.pol[0], rato.px, rato.py) || dentro(b.pol[1], rato.px, rato.py) || dentro(b.pol[2], rato.px, rato.py))) novo = b.k; } }
      if (novo >= blocos.length) novo = -1;
      hover = novo; if (hover !== ultimoHover) { ultimoHover = hover; cv.style.cursor = hover >= 0 && rato.dentro ? "pointer" : "default"; foco(); }
      /* a etiqueta do bloco em foco */
      if (hover >= 0 && blocos[hover].pol) { b = blocos[hover]; var tp = b.pol[0], tx = (tp[0][0] + tp[2][0]) / 2, ty = Math.min(tp[0][1], tp[1][1], tp[2][1], tp[3][1]), txt = b.u.usina + "   " + n(b.u.mwp, 1) + " MWp" + (b.sc.nota == null ? "" : "   contrato " + b.sc.nota);
        c2.font = '600 12.5px Poppins, "Segoe UI", sans-serif'; var lw = c2.measureText(txt).width + 20, lx = Math.max(4, Math.min(G.w - lw - 4, tx - lw / 2)), ly = Math.max(4, ty - 44);
        c2.strokeStyle = rgba(COR.tinta, 0.55); c2.lineWidth = 1; c2.beginPath(); c2.moveTo(tx, ty - 4); c2.lineTo(tx, ly + 26); c2.stroke();
        c2.fillStyle = rgba(COR.fundo, 0.92); c2.strokeStyle = rgba(COR.tinta, 0.28); c2.beginPath(); c2.rect(lx, ly, lw, 26); c2.fill(); c2.stroke();
        c2.fillStyle = COR.tinta; c2.textBaseline = "middle"; c2.fillText(txt, lx + 10, ly + 13.5); }
      ANIMA.id = requestAnimationFrame(quadro);
    }
    cv.addEventListener("mousemove", function (ev) { var bb = cv.getBoundingClientRect(); rato.px = ev.clientX - bb.left; rato.py = ev.clientY - bb.top; rato.dentro = true;
      rato.x = Math.max(-1, Math.min(1, (rato.px - G.cx) / (G.w * 0.4))); rato.y = Math.max(-1, Math.min(1, (rato.py - G.h / 2) / (G.h * 0.5))); });
    cv.addEventListener("mouseleave", function () { rato.dentro = false; rato.x = 0; rato.y = 0; });
    cv.addEventListener("click", function () { if (hover >= 0) ir({cliente: c.cliente, usina: blocos[hover].u.usina, mes: E.mes}); });
    linhas.forEach(function (l, i) { l.addEventListener("mouseenter", function () { hoverLinha = i; }); l.addEventListener("mouseleave", function () { hoverLinha = -1; }); });
    geo(); foco(); barras();
    cancelAnimationFrame(ANIMA.id); ANIMA.id = requestAnimationFrame(quadro);
  }

  /* ── a usina: a tela que EXPLICA a nota (Levi: "quando eu clicar na UFV tem que explicar esse número") ───────────
     A nota à esquerda e, à direita, cada item com o que o contrato pede, o que o Nexus mediu e a conta que deu a nota. */
  function capaUsina(c, u) {
    var sc = u.score[E.mes], m = oMes(E.mes), fora = sc.itens.filter(function (i) { return i.nota == null; }), med = sc.itens.filter(function (i) { return i.nota != null; });
    var prontuario = raiz.getAttribute("data-prontuario") + encodeURIComponent(u.uid) + (m.atual ? "" : "?mes=" + encodeURIComponent(m.id));
    return avisos() + '<p class="vg-trilha" style="margin-bottom:8px">' + lk({}, "Portfólio Grid Co.") + " / " + lk({cliente: c.cliente}, c.cliente) + " / usina</p>" +
      '<div class="vg-topo"><p class="vg-usina">' + esc(u.usina) + '</p><span class="vg-acoes">' + seletorMes() + (u.uid == null ? "" : '<a class="vg-botao" href="' + esc(prontuario) + '">Abrir o prontuário</a>') + "</span></div>" +
      '<p class="vg-lead">' + n(u.mwp, 1) + " MWp" + (u.valor != null ? ", " + brlCheio(u.valor) + " por mês no contrato" : D.contratos_ok ? ", sem ligação com o valor do contrato" : "") + ".</p>" +
      '<div class="vg-exp"><div><div class="vg-score vg-t-' + tom(sc.nota) + '">' + (sc.nota == null ? "—" : sc.nota) + '</div><p class="vg-score-rot">Cumprimento do contrato</p>' +
      '<p class="mudo" style="margin-top:4px">em ' + m.nome + (m.atual ? ", até ontem" : ", mês fechado") + ", de 0 a 100.</p>" +
      '<p style="margin-top:18px">' + (sc.nota == null ? (med.length ? "Só um dos quatro itens pôde ser medido nesta usina: com um item só não há nota." : "Nenhum dos quatro itens pôde ser medido nesta usina.")
        : "É a média dos " + med.length + " itens medidos: " + med.map(function (i) { return i.nota; }).join(" + ") + ", dividido por " + med.length + ".") + "</p>" +
      (fora.length ? '<p class="mudo">Fora da conta: ' + fora.map(function (i) { return minuscula(i.nome); }).join(", ") + ".</p>" : "") +
      '<ul class="vg-fatos"><li><span>Pontuação da usina no Nexus</span><b>' + (u.pontos == null ? "—" : u.pontos) + "</b></li><li><span>Fim do contrato</span><b>" +
      (!c.tem_contrato ? "sem ficha" : c.dias_fim == null ? "sem data" : c.dias_fim < 0 ? "venceu há " + (-c.dias_fim) + " dias" : "em " + c.dias_fim + " dias") + "</b></li></ul></div>" +
      "<div>" + sc.itens.map(function (it) { return '<section class="vg-item"><header><h3>' + esc(it.nome) + '</h3><span class="vg-trilho"><i class="vg-b-' + tom(it.nota) + '" style="width:' + (it.nota || 0) + '%"></i></span><span class="vg-v vg-t-' + tom(it.nota) + '">' + (it.nota == null ? "fora" : it.nota) + "</span></header>" +
        "<dl><dt>O contrato pede</dt><dd>" + esc(it.pede) + "</dd><dt>O Nexus mediu</dt><dd>" + esc(it.mediu) + "</dd><dt>A conta</dt><dd>" + esc(it.conta) + "</dd></dl></section>"; }).join("") + "</div></div>" +
      '<p class="vg-nota" style="margin-top:26px">A nota é uma proposta em teste: os quatro itens têm o mesmo peso, item sem garantia no contrato ou sem dado fica fora, e usina com menos de dois itens medidos fica sem nota. Os números da conta ainda esperam aprovação.</p>' + rodape();
  }

  /* ── o desenho ────────────────────────────────────────────────────────────────────────────────────────────────── */
  function desenhar() {
    if (!D) return;
    cancelAnimationFrame(ANIMA.id);
    cores();
    if (!D.meses.some(function (m) { return m.id === E.mes; })) E.mes = D.mes_atual;
    var c = E.cliente ? cli(E.cliente) : null, u = c && E.usina ? c.usinas.filter(function (x) { return x.usina === E.usina; })[0] : null;
    if (!c) { E.cliente = ""; E.usina = ""; } else if (!u) E.usina = "";
    var nivel = u ? "u" : c ? "c" : "p";
    tela.innerHTML = nivel === "u" ? capaUsina(c, u) : nivel === "c" ? capaCliente(c) : capaPortfolio();
    if (nivel !== nivelAntes) { window.scrollTo(0, 0); nivelAntes = nivel; }
    if (nivel === "p") iniciarPotencia(); else if (nivel === "c") iniciarParque(c);
  }
  tela.addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-vg-mes]");
    if (b) { ir({cliente: E.cliente, usina: E.usina, mes: b.getAttribute("data-vg-mes")}); return; }
    var a = ev.target.closest("[data-vg-ir]");
    if (!a || ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button) return;
    ev.preventDefault();
    ir({cliente: a.getAttribute("data-vg-cliente"), usina: a.getAttribute("data-vg-usina"), mes: E.mes});
  });
  window.addEventListener("popstate", function () { ler(); desenhar(); });

  function pedir(caminho) {
    if (typeof window.nexusPedir === "function") return window.nexusPedir(caminho);
    return fetch(caminho, {credentials: "same-origin"}).then(function (r) { return r.json(); });
  }
  pedir(raiz.getAttribute("data-dados")).then(function (d) {
    if (!d || !d.ok) throw new Error("sem dados");
    D = d; ler(); desenhar();
  }).catch(function (e) {
    tela.innerHTML = '<p class="vg-aviso" style="padding:18px 0">Não consegui ler o portfólio agora' + (e && e.message && e.message !== "sem dados" ? " (" + esc(e.message) + ")" : "") + ". Recarregue a página em instantes.</p>";
  });
})();
