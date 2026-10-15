/* PCM → Acompanhamento (14/10/2026): o painel de acompanhamento do PCM O&M no Nexus.
   Levi: "O design quero alá Nexus, não quero que copie o design, mas as estruturas quero sim que mantenha!". As
   estruturas são as do painel do PCM (scripts/modelo/dash_template.html do pacote de integração): as cinco abas, os
   filtros laterais que se cruzam, os cartões, os destaques, os gráficos e as tabelas que filtram com um clique, o mapa
   de carga e mobilização e o One Page. O desenho é o do Nexus (tokens do tema, ícones Phosphor) e os dados vêm do
   servidor (nexus/pcm/acompanhamento): o mapa chega desenhado e a distância chega medida, porque a coordenada da usina
   não sai do servidor. Regras e porquês: nexus/pcm/acompanhamento/CLAUDE.md. */
(function () {
  "use strict";
  var raiz = document.getElementById("pa");
  if (!raiz) return;
  var $ = function (s) { return document.querySelector(s); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]; }); };
  var D, X, COLAB, TODAY, AV;
  var fmt = function (s) { if (!s) return "—"; var p = s.split("-"); return p[2] + "/" + p[1] + (p[0] !== D.hoje.slice(0, 4) ? "/" + p[0].slice(2) : ""); };
  var dd = function (s) { return Math.round((new Date(s + "T00:00:00") - TODAY) / 86400000); };
  var nf = function (n) { return Number(n || 0).toLocaleString("pt-BR"); };

  /* os ícones dos filtros (Phosphor, os do Nexus) */
  var IC = {flag: "flag", building: "buildings", pin: "map-pin", shield: "shield-check", wrench: "wrench", users: "users-three",
            lock: "lock-simple", clock: "clock", sheet: "table", tag: "tag", hourglass: "hourglass-medium", sun: "solar-panel"};
  var ico = function (k) { return '<i class="ph ph-' + IC[k] + '" aria-hidden="true"></i>'; };

  /* rótulos (os do painel) */
  var SIT = {1: "Pendente Engenharia", 2: "Auxílio da Manutenção", 3: "Atrasadas e com mais pendências", 0: "Fora do ranking"};
  var CAUSE_LBL = {"Equipamento": "Falta de equipamento", "Desligamento ou noturna": "Desligamento ou atividade noturna", "Equipe": "Falta de equipe",
    "Lançar na OS": "Feito em campo, falta lançar na OS", "Chuva": "Chuva", "Correção da engenharia": "Correção pedida pela engenharia",
    "Sem bloqueio registrado": "Sem bloqueio registrado", "Laudo de óleo": "Aguarda laudo de óleo", "Revisão da engenharia": "Aguarda revisão da engenharia",
    "Cliente": "Alinhamento com o cliente", "Outros": "Outros"};
  var FIELD_CAUSES = ["Equipamento", "Desligamento ou noturna", "Equipe", "Lançar na OS", "Chuva", "Correção da engenharia", "Cliente", "Laudo de óleo", "Revisão da engenharia", "Outros", "Sem bloqueio registrado"];
  var atrasoFx = function (a) { return a == null ? null : a <= 30 ? "Até 30 dias" : a <= 90 ? "31 a 90 dias" : "Mais de 90 dias"; };
  var idadeFx = function (a) { return a <= 45 ? "25 a 45 dias" : a <= 60 ? "46 a 60 dias" : a <= 90 ? "61 a 90 dias" : "Mais de 90 dias"; };
  var cargaFx = function (n) { return !n ? "Sem OS aberta" : n <= 10 ? "1 a 10 tarefas" : n <= 30 ? "11 a 30 tarefas" : n <= 60 ? "31 a 60 tarefas" : "Mais de 60 tarefas"; };
  var MANUT = function (r) { return r.manut || "A definir"; };
  var TITULOS = {mpa: "Fechamento das MPAs", mps: "Fechamento das MPSs", bkl: "Radar de Backlog", map: "Mapa de carga e mobilização", op: "One Page semanal"};
  var TABS, STATE, MAPROWS, CLUSTERS, TEAM, BKL, PR, WCUR, WK, WKEYS;

  function preparar() {
    TODAY = new Date(D.hoje + "T00:00:00");
    PR = X.painel || {};
    WCUR = (X.w42 && X.w42.num) || "";
    /* o status da planilha e o atraso pela regra da Fila da Gestão PCM, em cada MPA/MPS */
    var porLinha = {};
    D.esp.forEach(function (e) { porLinha[e.linha] = e; });
    D.mpa.concat(D.mps).forEach(function (r) {
      var e = porLinha[r.linha]; r.status = e ? e.status : "Fora da planilha";
      var p = PR[r.linha]; if (!p || r.g === 1) return;
      r.refLim = p.ref_lim; r.atraso = p.atrasada ? (p.dias || 0) : 0;
    });
    BKL = D.backlog.filter(function (r) { return r.st === 1; });
    MAPROWS = X.usinas.filter(function (u) { return u.usina && !/teste/i.test(u.usina); }).map(function (u) {
      return Object.assign({}, u, {u: u.usina.replace(/^[^-]+-\s*/, "").replace(/\s*-\s*[A-Z]{2}$/, ""), cluster: u.cluster || "Sem cluster"});
    });
    TEAM = {};
    (COLAB || []).forEach(function (p) { var k = (p.cluster || "").toUpperCase().trim(); (TEAM[k] = TEAM[k] || []).push(p); });
    var ord = {"Técnico": 0, "Eletricista": 1, "Mantenedor": 2};
    Object.keys(TEAM).forEach(function (k) { TEAM[k].sort(function (x, y) { return ((ord[x.cargo] != null ? ord[x.cargo] : 9) - (ord[y.cargo] != null ? ord[y.cargo] : 9)) || x.nome.localeCompare(y.nome, "pt"); }); });
    CLUSTERS = Array.from(new Set(MAPROWS.map(function (r) { return r.cluster; }).filter(function (c) { return c !== "Sem cluster"; }))).sort(function (a, b) { return a.localeCompare(b, "pt", {numeric: true}); });
    WK = X.weeks || {};
    WKEYS = Object.keys(WK).sort(function (a, b) { return +a - +b; });
    var PM_FILTERS = [
      {k: "g", l: "Situação", i: "flag", get: function (r) { return r.g == null ? [] : [SIT[r.g]]; }, order: [SIT[1], SIT[2], SIT[3], SIT[0]]},
      {k: "cli", l: "Cliente", i: "building", get: function (r) { return [r.cli || "Sem cliente"]; }},
      {k: "cluster", l: "Cluster", i: "pin", get: function (r) { return [r.cluster || "Sem cluster"]; }},
      {k: "usina", l: "Usina", i: "sun", get: function (r) { return [r.u || "—"]; }},
      {k: "sup", l: "Supervisor", i: "shield", get: function (r) { return [r.sup || "Sem supervisor"]; }},
      {k: "resp", l: "Responsável da OS", i: "wrench", get: function (r) { return r.resp == null ? [] : [r.resp]; }},
      {k: "manut", l: "Resp. da Manutenção", i: "users", get: function (r) { return r.g == null ? [] : [MANUT(r)]; }},
      {k: "bl", l: "Bloqueio", i: "lock", get: function (r) { return (r.bl || []).map(function (b) { return CAUSE_LBL[b] || b; }); }},
      {k: "at", l: "Atraso", i: "clock", get: function (r) { return r.atraso == null || r.g === 1 ? [] : [atrasoFx(r.atraso)]; }, order: ["Até 30 dias", "31 a 90 dias", "Mais de 90 dias"]},
      {k: "status", l: "Status na planilha", i: "sheet", get: function (r) { return [r.status || "—"]; }}
    ];
    TABS = {
      mpa: {rows: function () { return D.mpa; }, esp: function () { return D.esp.filter(function (e) { return e.tipo === "MPA"; }); }, filters: PM_FILTERS, kind: "MPA"},
      mps: {rows: function () { return D.mps; }, esp: function () { return D.esp.filter(function (e) { return e.tipo === "MPS"; }); }, filters: PM_FILTERS, kind: "MPS"},
      bkl: {rows: function () { return BKL; }, filters: [
        {k: "tipo", l: "Tipo de OS", i: "tag", get: function (r) { return [r.tipo]; }, order: ["Corretiva", "Corretiva Emergencial", "Religamento", "Religamento Remoto", "Inspeção", "Administrativa", "Preventiva (MPA)", "Preventiva (MPS)", "Preventiva", "Handover", "Zeladoria"]},
        {k: "cli", l: "Cliente", i: "building", get: function (r) { return [r.cli]; }},
        {k: "cluster", l: "Cluster", i: "pin", get: function (r) { return [r.cluster]; }},
        {k: "usina", l: "Usina", i: "sun", get: function (r) { return [r.u || "—"]; }},
        {k: "resp", l: "Responsável da OS", i: "wrench", get: function (r) { return [r.resp || "Sem responsável"]; }},
        {k: "idade", l: "Idade da OS", i: "hourglass", get: function (r) { return [idadeFx(r.idade)]; }, order: ["25 a 45 dias", "46 a 60 dias", "61 a 90 dias", "Mais de 90 dias"]}
      ]},
      map: {rows: function () { return MAPROWS; }, filters: [
        {k: "cli", l: "Cliente", i: "building", get: function (r) { return [r.cli]; }},
        {k: "cluster", l: "Cluster", i: "pin", get: function (r) { return [r.cluster || "Sem cluster"]; }},
        {k: "usina", l: "Usina", i: "sun", get: function (r) { return [r.u || "—"]; }},
        {k: "sup", l: "Supervisor", i: "shield", get: function (r) { return [r.sup || "Sem supervisor"]; }},
        {k: "tipo", l: "Tipo de OS na carga", i: "tag", get: function (r) { return Object.keys(r.tipos); }, order: ["Preventiva", "Corretiva", "Corretiva Emergencial", "Inspeção", "Administrativa", "Religamento", "Religamento Remoto", "Handover", "Zeladoria"]},
        {k: "carga", l: "Faixa de carga", i: "hourglass", get: function (r) { return [cargaFx(r.tarefas)]; }, order: ["Sem OS aberta", "1 a 10 tarefas", "11 a 30 tarefas", "31 a 60 tarefas", "Mais de 60 tarefas"]}
      ]},
      op: {rows: function () { return []; }, filters: []}
    };
    var dIso = function (s) { return new Date(s + "T00:00:00"); };
    var aba = raiz.dataset.aba;
    STATE = {tab: TABS[aba] ? aba : "mpa", f: {mpa: {}, mps: {}, bkl: {}, map: {}, op: {}}, q: {mpa: "", mps: "", bkl: "", map: "", op: ""},
      sort: {}, limit: {}, map: {mode: "carga", group: "cluster", size: "tarefas", origin: null, dest: null, factor: 1.3, speed: 70, vb: null, rota: null},
      opWeek: WKEYS.filter(function (k) { return dIso(WK[k].fim) < TODAY; }).pop() || WKEYS[WKEYS.length - 1]};
  }
  var teamOf = function (c) { return TEAM[(c || "").toUpperCase().trim()] || []; };
  var teamTip = function (c) { var t = teamOf(c); return t.length ? "<br><b>Equipe (" + t.length + "):</b> " + t.map(function (p) { return esc(p.nome) + ' <span class="pa-tip-mudo">(' + esc(p.cargo) + ")</span>"; }).join(", ") : "<br>Equipe: sem colaborador ativo no cadastro"; };

  /* ── o motor dos filtros (o do painel: os filtros se cruzam; a busca ignora acento e caixa) ── */
  var fold = function (s) { return String(s == null ? "" : s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); };
  var HAY = new WeakMap();
  function hay(r, tab) {
    var h = HAY.get(r); if (h && h.tab === tab) return h.s;
    var parts = [r.os, r.u, r.usina, r.cli, r.cluster, r.sup, r.resp, r.tipo, r.obs, r.falta, r.desc, r.status, r.strel, MANUT(r)]
      .concat(r.tit || [], r.bloq || [], (r.bl || []).map(function (b) { return CAUSE_LBL[b] || b; }));
    TABS[tab].filters.forEach(function (def) { try { parts.push.apply(parts, def.get(r)); } catch (e) { /* campo ausente */ } });
    if (tab === "map") parts.push.apply(parts, teamOf(r.cluster).map(function (p) { return p.nome + " " + p.cargo; }));
    var s = fold(parts.filter(Boolean).join(" | ")); HAY.set(r, {tab: tab, s: s}); return s;
  }
  function passes(r, tab, skipKey) {
    var F = STATE.f[tab];
    for (var i = 0; i < TABS[tab].filters.length; i++) {
      var def = TABS[tab].filters[i];
      if (def.k === skipKey) continue;
      var sel = F[def.k]; if (!sel || !sel.size) continue;
      if (!def.get(r).some(function (v) { return sel.has(v); })) return false;
    }
    var q = fold(STATE.q[tab] || "").trim();
    if (q) { var h = hay(r, tab); if (!q.split(/\s+/).every(function (w) { return h.indexOf(w) >= 0; })) return false; }
    return true;
  }
  function toggle(tab, k, v, only) {
    var F = STATE.f[tab]; F[k] = F[k] || new Set();
    if (only) { if (F[k].size === 1 && F[k].has(v)) F[k].clear(); else { F[k].clear(); F[k].add(v); } }
    else if (F[k].has(v)) F[k].delete(v); else F[k].add(v);
    render();
  }

  /* ── o filtro de seleção múltipla ── */
  var openPanel = null;
  function closePanel() { if (openPanel) { openPanel.hidden = true; openPanel.previousElementSibling.setAttribute("aria-expanded", "false"); openPanel = null; } }
  function renderFilters() {
    var tab = STATE.tab, box = $("#pa-filtros"); box.innerHTML = "";
    var all = TABS[tab].rows().concat(TABS[tab].esp ? TABS[tab].esp() : []);
    TABS[tab].filters.forEach(function (def) {
      var sel = STATE.f[tab][def.k] || new Set(), counts = new Map();
      TABS[tab].rows().filter(function (r) { return passes(r, tab, def.k); }).forEach(function (r) { def.get(r).forEach(function (v) { counts.set(v, (counts.get(v) || 0) + 1); }); });
      var opts = Array.from(new Set([].concat.apply([], all.map(def.get))));
      opts.sort(def.order ? function (a, b) { return def.order.indexOf(a) - def.order.indexOf(b); } : function (a, b) { return String(a).localeCompare(String(b), "pt", {numeric: true}); });
      if (!opts.length) return;
      var wrap = document.createElement("div"); wrap.className = "pa-ms" + (sel.size ? " on" : "");
      var val = sel.size === 0 ? "Todos" : sel.size === 1 ? Array.from(sel)[0] : sel.size + " selecionados";
      var id = "pa-ms-" + def.k;
      wrap.innerHTML = '<span class="gc-rotulo" id="' + id + '-l">' + esc(def.l) + "</span>"
        + '<button type="button" class="pa-ms-bt" aria-haspopup="listbox" aria-expanded="false" aria-labelledby="' + id + '-l" title="' + esc(sel.size ? Array.from(sel).join(", ") : "Todos") + '">' + ico(def.i) + '<span class="val">' + esc(val) + '</span><i class="ph ph-caret-down" aria-hidden="true"></i></button>'
        + '<div class="pa-ms-painel" hidden>'
        + (opts.length > 8 ? '<input class="gc-campo pa-ms-busca" type="search" placeholder="Buscar ' + esc(def.l.toLowerCase()) + '" aria-label="Buscar ' + esc(def.l) + '">' : "")
        + '<div class="pa-ms-rapido"><button type="button" class="pa-lnk" data-q="all">Selecionar todos</button><button type="button" class="pa-lnk" data-q="none">Limpar</button></div>'
        + '<div class="pa-ms-lista" role="listbox" aria-multiselectable="true">' + opts.map(function (o) { var c = counts.get(o) || 0; return '<label class="pa-ms-op' + (c ? "" : " zero") + '"><input type="checkbox" value="' + esc(o) + '"' + (sel.has(o) ? " checked" : "") + "><span>" + esc(o) + "</span><em>" + c + "</em></label>"; }).join("") + "</div>"
        + '<div class="pa-ms-acoes"><button type="button" class="gc-btn gc-btn--contorno" data-a="cancel">Cancelar</button><button type="button" class="gc-btn gc-btn--primario" data-a="apply">Aplicar</button></div></div>';
      var btn = wrap.querySelector(".pa-ms-bt"), panel = wrap.querySelector(".pa-ms-painel");
      btn.addEventListener("click", function (e) { e.stopPropagation(); var was = !panel.hidden; closePanel(); if (!was) { panel.hidden = false; btn.setAttribute("aria-expanded", "true"); openPanel = panel; var s = panel.querySelector(".pa-ms-busca"); (s || panel.querySelector("input")).focus(); } });
      panel.addEventListener("click", function (e) { e.stopPropagation(); });
      var busca = panel.querySelector(".pa-ms-busca");
      if (busca) busca.addEventListener("input", function () { var q = fold(busca.value); panel.querySelectorAll(".pa-ms-op").forEach(function (o) { o.hidden = fold(o.textContent).indexOf(q) < 0; }); });
      panel.querySelector('[data-q="all"]').onclick = function () { panel.querySelectorAll(".pa-ms-op:not([hidden]) input").forEach(function (i) { i.checked = true; }); };
      panel.querySelector('[data-q="none"]').onclick = function () { panel.querySelectorAll("input[type=checkbox]").forEach(function (i) { i.checked = false; }); };
      panel.querySelector('[data-a="cancel"]').onclick = function () { closePanel(); btn.focus(); };
      panel.querySelector('[data-a="apply"]').onclick = function () {
        var s = new Set(Array.from(panel.querySelectorAll("input[type=checkbox]:checked")).map(function (i) { return i.value; }));
        STATE.f[tab][def.k] = s.size === opts.length ? new Set() : s; closePanel(); render();
      };
      panel.addEventListener("keydown", function (e) { if (e.key === "Escape") { closePanel(); btn.focus(); } if (e.key === "Enter" && e.target.type !== "checkbox" && e.target.tagName !== "BUTTON") panel.querySelector('[data-a="apply"]').click(); });
      box.appendChild(wrap);
    });
  }
  document.addEventListener("click", closePanel);

  /* ── a dica (tooltip) ── */
  var tip = $("#pa-tip");
  document.addEventListener("mouseover", function (e) { var t = e.target.closest && e.target.closest("#pa [data-tip]"); if (!t) { tip.hidden = true; return; } tip.innerHTML = t.dataset.tip; tip.hidden = false; });
  document.addEventListener("mousemove", function (e) { if (tip.hidden) return; var w = tip.offsetWidth, h = tip.offsetHeight, x = e.clientX + 14, y = e.clientY + 16; if (x + w > innerWidth - 8) x = e.clientX - w - 14; if (y + h > innerHeight - 8) y = e.clientY - h - 14; tip.style.left = x + "px"; tip.style.top = y + "px"; });
  document.addEventListener("focusin", function (e) { var t = e.target.closest && e.target.closest("#pa [data-tip]"); if (!t) return; tip.innerHTML = t.dataset.tip; tip.hidden = false; var r = t.getBoundingClientRect(); tip.style.left = Math.min(r.left, innerWidth - 330) + "px"; tip.style.top = (r.bottom + 6) + "px"; });
  document.addEventListener("focusout", function () { tip.hidden = true; });
  var tipAttr = function (html) { return 'data-tip="' + esc(html) + '"'; };

  /* ── peças reutilizáveis ── */
  var xf = function (k, v, label) { return '<span class="pa-xf" data-xf="' + k + '" data-v="' + esc(v) + '" role="button" tabindex="0">' + esc(label != null ? label : v) + "</span>"; };
  var usinaCell = function (r, ast) { return '<span class="pa-usina">' + esc(r.u) + (ast ? '<sup class="pa-ast">*</sup>' : "") + '</span><span class="pa-cli">' + xf("cli", r.cli || "Sem cliente") + " · " + xf("cluster", r.cluster || "Sem cluster") + "</span>"; };
  var chips = function (r) { return (r.bl || []).map(function (b) { var l = CAUSE_LBL[b] || b; return '<span class="pa-chip" data-xf="bl" data-v="' + esc(l) + '" role="button" tabindex="0">' + esc(l) + "</span>"; }).join(""); };
  var pendMeter = function (r, c) {
    if (r.tot == null) return '<div class="pa-med pa-med--' + c + '"><span><b>' + r.pend + "</b> pendência" + (r.pend > 1 ? "s" : "") + ' em campo</span><span class="pa-flag">OS 100% no Fracttal</span></div>';
    var done = r.tot - r.pend, p = Math.round(100 * done / r.tot);
    return '<div class="pa-med pa-med--' + c + '"><span><b>' + p + "%</b> concluído · faltam <b>" + r.pend + "</b> de " + r.tot + '</span><div class="pa-med-barra"><i style="width:' + Math.max(p, 2) + '%"></i></div></div>';
  };
  var progMeter = function (p, c) { return '<div class="pa-med pa-med--' + (c || "ok") + '"><span><b>' + p + '%</b> concluído</span><div class="pa-med-barra"><i style="width:' + Math.max(p, 2) + '%"></i></div></div>'; };
  var manutCell = function (r) { return r.manut ? xf("manut", r.manut) : '<span class="pa-tbd pa-xf" data-xf="manut" data-v="A definir" role="button" tabindex="0">A definir</span>'; };
  var respCell = function (r) { return r.resp && r.resp !== "—" ? xf("resp", r.resp) : "—"; };
  var oil = function (r) { return (r.bl || []).indexOf("Laudo de óleo") >= 0 && !r.sem_oleo; };
  var bulls = function (a) { return a.length ? '<ul class="pa-bul">' + a.join("") + "</ul>" : ""; };
  var blkCell = function (r, withChips) {
    var b = r.bloq || [], c = withChips === false ? "" : chips(r);
    return b.length ? c + bulls(b.map(function (x) { return "<li>" + esc(x) + "</li>"; })) : (c ? c + (r.obs ? '<div class="pa-bloco">' + esc(r.obs) + "</div>" : "") : '<span class="pa-bloco">—</span>');
  };
  function prazoCell(r) {
    if (!r.prazo) return '<span class="pa-sem-prazo">Sem prazo</span>';
    var n = dd(r.prazo);
    return '<span class="pa-prazo' + (n < 0 ? " vencido" : n <= 7 ? " perto" : "") + '"><b>' + fmt(r.prazo) + "</b> · " + (n > 0 ? "em " + n + " d" : n === 0 ? "hoje" : "vencido há " + (-n) + " d") + "</span>" + (r.sem_oleo ? '<br><span class="pa-bloco">sem análise de óleo</span>' : "");
  }

  /* ── a tabela ordenável e paginada ── */
  function cmp(a, b, k) { var x = a[k], y = b[k]; if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1; if (typeof x === "number" && typeof y === "number") return x - y; return String(x).localeCompare(String(y), "pt", {numeric: true}); }
  function table(id, cols, rows, defSort, opts) {
    opts = opts || {};
    var key = STATE.tab + ":" + id, s = STATE.sort[key] || defSort;
    rows = rows.slice().sort(function (a, b) { var v = cmp(a, b, s.k) * s.dir; if (!v && s.then) v = cmp(a, b, s.then.k) * s.then.dir; return v; });
    var lim = opts.page ? (STATE.limit[key] || opts.page) : Infinity, shown = rows.slice(0, lim);
    var head = "<thead><tr>" + cols.map(function (c) { var at = s.k === c.k; return '<th class="' + (c.cls || "") + (at ? " ativo" : "") + '" aria-sort="' + (at ? (s.dir > 0 ? "ascending" : "descending") : "none") + '"><button type="button" data-sort="' + c.k + '" data-key="' + key + '">' + c.h + '<i class="ph ' + (at ? (s.dir > 0 ? "ph-caret-up" : "ph-caret-down") : "ph-arrows-down-up") + '" aria-hidden="true"></i></button></th>'; }).join("") + "</tr></thead>";
    var body = "<tbody>" + shown.map(function (r) { return '<tr data-os="' + esc(r.os) + '"' + (opts.rowCls ? ' class="' + opts.rowCls(r) + '"' : "") + (opts.tip ? " " + tipAttr(opts.tip(r)) : "") + ">" + cols.map(function (c) { return '<td class="' + (c.cls || "") + '">' + c.c(r) + "</td>"; }).join("") + "</tr>"; }).join("") + "</tbody>";
    var more = rows.length > lim ? '<button class="gc-btn gc-btn--contorno pa-mais" data-more="' + key + '" data-step="' + opts.page + '" type="button">Mostrar mais ' + Math.min(opts.page, rows.length - lim) + " de " + (rows.length - lim) + " restantes</button>" : "";
    return '<div class="pa-rolo"><table class="pa-tbl">' + head + body + "</table></div>" + more;
  }
  function section(id, g, title, count, inner, foot) {
    var tag = g === "A" ? '<i class="ph ph-list-bullets" aria-hidden="true"></i>' : g === 0 || g === "0" ? "–" : g;
    return '<section class="pa-sec pa-sec--g' + g + '" id="pa-' + id + '"><h2><span class="pa-tag">' + tag + "</span>" + title + ' <span class="pa-conta">' + count + "</span></h2>" + inner + (foot || "") + "</section>";
  }
  var nota = function (itens) { return '<div class="pa-nota"><b>Como ler</b><ul>' + itens.map(function (x) { return "<li>" + x + "</li>"; }).join("") + "</ul></div>"; };
  var card = function (cls, n, t, s, attrs, pressed, tipHtml) { return '<button class="pa-card pa-card--' + cls + '" type="button" ' + (attrs || "") + ' aria-pressed="' + (pressed ? "true" : "false") + '" ' + tipAttr(tipHtml) + '><span class="n gc-num">' + n + '</span><span class="t">' + t + '</span><span class="s">' + s + "</span></button>"; };

  /* ── o gráfico de dispersão (MPA/MPS em campo) ── */
  function scatter(rows) {
    var W = 640, H = 340, m = {l: 46, r: 24, t: 14, b: 42};
    var maxX = Math.max.apply(null, [50].concat(rows.map(function (r) { return r.pend || 0; }))), maxY = Math.max.apply(null, [200].concat(rows.map(function (r) { return r.atraso || 0; })));
    maxY = Math.ceil(maxY / 50) * 50;                               /* a escala fecha numa linha da grade */
    var xs = function (v) { return m.l + (v / maxX) * (W - m.l - m.r); }, ys = function (v) { return H - m.b - (v / maxY) * (H - m.t - m.b); };
    var s = '<rect x="' + xs(0) + '" y="' + m.t + '" width="' + (xs(10.5) - xs(0)) + '" height="' + (H - m.b - m.t) + '" class="pa-zona"/><text x="' + (xs(10.5) + 6) + '" y="' + (m.t + 13) + '" class="pa-zona-rot">≤ 10 pendências: Manutenção</text><g class="pa-eixo">';
    for (var v = 0; v <= maxY; v += 50) s += '<line x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + ys(v) + '" y2="' + ys(v) + '"/><text x="' + (m.l - 8) + '" y="' + (ys(v) + 4) + '" text-anchor="end">' + v + "</text>";
    for (var u = 0; u <= maxX; u += 10) s += '<text x="' + xs(u) + '" y="' + (H - m.b + 17) + '" text-anchor="middle">' + u + "</text>";
    s += '</g><line x1="' + m.l + '" x2="' + (W - m.r) + '" y1="' + ys(0) + '" y2="' + ys(0) + '" class="pa-base"/><text x="' + ((m.l + W - m.r) / 2) + '" y="' + (H - 5) + '" text-anchor="middle" class="pa-eixo-tit">PENDÊNCIAS NA OS</text><text x="12" y="' + ((m.t + H - m.b) / 2) + '" text-anchor="middle" class="pa-eixo-tit" transform="rotate(-90 12 ' + ((m.t + H - m.b) / 2) + ')">DIAS DE ATRASO</text>';
    var top = rows.slice().sort(function (a, b) { return (b.atraso + b.pend * 2) - (a.atraso + a.pend * 2); }).slice(0, 6);
    /* Rótulo dos 6 piores sem cobrir ponto nem outro rótulo: tenta direita, esquerda, acima e abaixo, nessa ordem. Em
       15/10 o da Nova Xavantina 2 (47 pendências) ia para a esquerda e passava por cima do ponto das 40. */
    var ocup = rows.map(function (r) { var x = xs(r.pend || 0), y = ys(r.atraso); return [x - 7, y - 7, x + 7, y + 7]; });
    ocup.push([xs(10.5) + 6, m.t + 3, xs(10.5) + 6 + 26 * 6.6, m.t + 16]);   /* o rótulo da zona da Manutenção */
    var livre = function (b) { return b[0] >= 0 && b[2] <= W && b[1] >= 0 && b[3] <= H - m.b && !ocup.some(function (o) { return b[0] < o[2] && b[2] > o[0] && b[1] < o[3] && b[3] > o[1]; }); };
    var rotulos = top.map(function (r) {
      var x = xs(r.pend || 0), y = ys(r.atraso), w = String(r.u).length * 6.6;
      var op = [[x + 10, y + 4, "start", [x + 10, y - 7, x + 10 + w, y + 5]], [x - 10, y + 4, "end", [x - 10 - w, y - 7, x - 10, y + 5]],
        [x, y - 12, "middle", [x - w / 2, y - 21, x + w / 2, y - 9]], [x, y + 21, "middle", [x - w / 2, y + 10, x + w / 2, y + 22]]];
      var e = op.filter(function (o) { return livre(o[3]); })[0] || op[x < W - 150 ? 0 : 1];
      ocup.push(e[3]);
      return '<text x="' + e[0] + '" y="' + e[1] + '" text-anchor="' + e[2] + '" class="pa-pt-rot">' + esc(r.u) + "</text>";
    });
    rows.forEach(function (r) {
      var cx = xs(r.pend || 0), cy = ys(r.atraso);
      var t = "<b>" + esc(r.u) + "</b> · OS " + esc(r.os) + "<br>" + r.pend + " pendência" + (r.pend > 1 ? "s" : "") + " · " + r.atraso + " dias de atraso<br>" + esc(r.cli) + " · " + esc(r.cluster) + '<br><span class="pa-tip-mudo">Clique para ir à linha da tabela</span>';
      s += '<g class="pa-pt" tabindex="0" data-goto="' + esc(r.os) + '" ' + tipAttr(t) + ' aria-label="' + esc(r.u) + ": " + r.pend + " pendências, " + r.atraso + ' dias"><circle cx="' + cx + '" cy="' + cy + '" r="13" class="pa-alvo"/>'
        + (r.g === 2 ? '<circle cx="' + cx + '" cy="' + cy + '" r="6" class="pa-pt--g2"/>' : '<rect x="' + (cx - 6) + '" y="' + (cy - 6) + '" width="12" height="12" rx="2" class="pa-pt--g3"/>') + "</g>";
    });
    s += rotulos.join("");
    if (!rows.length) s += '<text x="' + (W / 2) + '" y="' + (H / 2) + '" text-anchor="middle" class="pa-eixo-tit">NENHUMA OS EM CAMPO NOS FILTROS</text>';
    return '<svg class="pa-graf" viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="Pendências por dias de atraso">' + s + "</svg>";
  }
  /* ── barras horizontais que filtram ── */
  function bars(items, fkey) {
    if (!items.length) return '<p class="pa-vazio">Nada nos filtros escolhidos.</p>';
    var max = Math.max.apply(null, items.map(function (x) { return x.v; })), sel = STATE.f[STATE.tab][fkey] || new Set();
    return '<div class="pa-barras">' + items.map(function (x) {
      var t = "<b>" + esc(x.label) + "</b><br>" + x.v + " " + (x.unit || "") + '<br><span class="pa-tip-mudo">Clique para filtrar</span>';
      return '<button type="button" class="pa-barra" data-xf="' + fkey + '" data-v="' + esc(x.label) + '" aria-pressed="' + sel.has(x.label) + '" ' + tipAttr(t) + '><span class="nome">' + esc(x.label) + '</span><span class="trilho"><i style="width:' + (x.v / max * 100) + '%"></i></span><span class="v gc-num">' + x.v + "</span></button>";
    }).join("") + "</div>";
  }

  /* ── abas MPA e MPS ── */
  function renderPM() {
    var tab = STATE.tab, T = TABS[tab], K = T.kind, rowsAll = T.rows();
    var base = rowsAll.filter(function (r) { return passes(r, tab, "g"); }), rows = rowsAll.filter(function (r) { return passes(r, tab); });
    var G = function (g) { return rows.filter(function (r) { return r.g === g; }); };
    var selG = STATE.f[tab].g || new Set();
    var b1 = base.filter(function (r) { return r.g === 1; }), o = b1.filter(oil).length;
    var pend = function (g) { return base.filter(function (r) { return r.g === g; }).reduce(function (a, r) { return a + (r.pend || 0); }, 0); };
    var cardG = function (g, t, s) { var n = base.filter(function (r) { return r.g === g; }).length; return card("g" + g, n, t, s, 'data-card="' + SIT[g] + '"', selG.has(SIT[g]), "<b>" + SIT[g] + "</b><br>" + s + '<br><span class="pa-tip-mudo">Clique para filtrar</span>'); };
    var cards = '<div class="pa-cards">' + cardG(1, "Pendente Engenharia", b1.length ? (b1.length - o) + " com a Engenharia" + (o ? " · " + o + " aguardam laudo de óleo*" : "") : "Nenhuma nos filtros")
      + cardG(2, "Auxílio da Manutenção", pend(2) + " pendências em aberto") + cardG(3, "Atrasadas e com mais pendências", pend(3) + " pendências em aberto")
      + cardG(0, "Fora do ranking", "OS recém-abertas, no prazo ou adiantadas") + "</div>";
    var field = rows.filter(function (r) { return r.g === 2 || r.g === 3; });
    /* no gráfico só entra quem tem atraso medido: sem a Gerencial e sem data programada no Fracttal, o ponto não tem
       onde ficar (15/10/2026: com o atraso vazio, os pontos iam para fora da escala, grudados no topo) */
    var comData = field.filter(function (r) { return typeof r.atraso === "number" && isFinite(r.atraso); });
    var semData = field.length - comData.length;
    var engOnly = G(1).filter(function (r) { return !oil(r) && r.parado != null; }).sort(function (a, b) { return b.parado - a.parado; });
    var withPrazo = G(1).filter(function (r) { return r.prazo; }).sort(function (a, b) { return a.prazo.localeCompare(b.prazo); });
    var oldest = comData.slice().sort(function (a, b) { return b.atraso - a.atraso; })[0];
    var eq = field.filter(function (r) { return (r.bl || []).indexOf("Equipamento") >= 0; }).length;
    var hl = [], nextP = withPrazo.filter(function (r) { return dd(r.prazo) >= 0; }), late = withPrazo.filter(function (r) { return dd(r.prazo) < 0; });
    if (late.length) hl.push([late.length + " vencido" + (late.length > 1 ? "s" : ""), "Relatórios da Engenharia com prazo vencido: " + late.map(function (r) { return esc(r.u); }).join(", ") + ".", "crit"]);
    if (nextP.length) { var p = nextP[0].prazo, n = nextP.filter(function (r) { return r.prazo === p; }), so = n.filter(function (r) { return r.sem_oleo; }).length;
      hl.push([fmt(p) + " · " + (dd(p) === 0 ? "hoje" : "em " + dd(p) + " dias"), "Próximo prazo da Engenharia: " + n.length + " relatório" + (n.length > 1 ? "s" : "") + " (" + n.map(function (r) { return esc(r.u); }).join(", ") + ")" + (so ? "; " + so + " saem sem a análise de óleo" : "") + ".", "info"]); }
    if (engOnly.length) hl.push([engOnly[0].parado + " dias", "Mais antiga parada com a Engenharia: " + esc(engOnly[0].u) + " (OS " + esc(engOnly[0].os) + ").", "alerta"]);
    if (oldest && oldest.atraso) hl.push([oldest.atraso + " dias", "Maior atraso em campo: " + esc(oldest.u) + ", com " + oldest.pend + " pendência" + (oldest.pend > 1 ? "s" : "") + ".", "crit"]);
    if (field.length) hl.push([eq + " de " + field.length, K + "s em campo travadas por falta de equipamento.", "alerta"]);
    var hlHtml = hl.length ? '<div class="pa-destaques" aria-label="Destaques">' + hl.map(function (h) { return '<div class="pa-hl pa-hl--' + h[2] + '"><b>' + h[0] + "</b><span>" + h[1] + "</span></div>"; }).join("") + "</div>" : "";
    var causeItems = FIELD_CAUSES.map(function (c) { var v = field.filter(function (r) { return (r.bl || []).indexOf(c) >= 0; }).length; return {label: CAUSE_LBL[c], v: v, unit: K + (v > 1 ? "s" : "")}; }).filter(function (x) { return x.v; }).sort(function (a, b) { return b.v - a.v; });
    var fonteAtraso = comData.some(function (r) { return r.atraso_fonte === "Fracttal"; }) ? (comData.every(function (r) { return r.atraso_fonte === "Fracttal"; }) ? " Atraso pela Data Programada no Fracttal (sem a Gerencial)." : " Atraso pela Gerencial e, sem ela, pela Data Programada no Fracttal.") : "";
    var charts = field.length ? '<div class="pa-graficos"><div class="pa-painel"><h3>Pendências × dias de atraso</h3><p class="pa-pequeno">' + K + "s ainda em campo. Passe o mouse para o resumo; clique para ir à linha." + fonteAtraso + (semData ? " " + semData + " sem data de atraso ficam fora do gráfico." : "") + "</p>"
      + '<div class="pa-legenda"><span><i class="pa-sw pa-sw--g2"></i>Auxílio da Manutenção</span><span><i class="pa-sw pa-sw--g3"></i>Atrasadas e com mais pendências</span></div>' + scatter(comData) + "</div>"
      + '<div class="pa-painel"><h3>O que trava as ' + K + 's em campo</h3><p class="pa-pequeno">Usinas por motivo; uma pode ter mais de um. Clique para filtrar.</p>' + bars(causeItems, "bl") + "</div></div>" : "";
    var osCell = function (r) { return '<span class="pa-os gc-num">' + esc(r.os) + "</span>"; };
    var c1 = [{k: "os", h: "OS", c: osCell}, {k: "u", h: "Usina", c: function (r) { return usinaCell(r, oil(r)); }}, {k: "resp", h: "Responsável da OS", c: respCell},
      {k: "fim", h: "Última execução", cls: "num", c: function (r) { return fmt(r.fim); }},
      {k: "parado", h: "Dias parado", cls: "num", c: function (r) { return r.parado == null ? "—" : '<span class="pa-idade' + (r.parado > 30 ? " alta" : r.parado > 14 ? " media" : "") + '">' + r.parado + " d</span>"; }},
      {k: "prazo", h: "Prazo do relatório", c: prazoCell}, {k: "bloq", h: "Bloqueios", c: function (r) { return blkCell(r); }}];
    var cField = function (withFalta) { return [{k: "os", h: "OS", c: osCell}, {k: "u", h: "Usina", c: function (r) { return usinaCell(r); }}, {k: "prog", h: "Progresso", c: function (r) { return pendMeter(r, "ok"); }}]
      .concat(withFalta ? [{k: "falta", h: "O que falta", c: function (r) { return esc(r.falta || "—"); }}] : [])
      .concat([{k: "bloq", h: "Bloqueios", c: function (r) { return blkCell(r); }}, {k: "resp", h: "Responsável da OS", c: respCell}, {k: "manut", h: "Resp. da Manutenção", c: manutCell},
        {k: "atraso", h: "Atraso", cls: "num", c: function (r) { return r.atraso == null ? "—" : '<span class="pa-atraso">' + r.atraso + " d</span>"; }}]); };
    var c0 = [{k: "os", h: "OS", c: osCell}, {k: "u", h: "Usina", c: function (r) { return usinaCell(r); }}, {k: "prog", h: "Progresso", c: function (r) { return progMeter(r.prog || 0, "info"); }},
      {k: "resp", h: "Responsável da OS", c: respCell}, {k: "manut", h: "Resp. da Manutenção", c: manutCell}, {k: "prev", h: "Prevista", cls: "num", c: function (r) { return fmt(r.prev); }},
      {k: "bloq", h: "Bloqueios", c: function (r) { return blkCell(r); }}];
    var tip1 = function (r) { return "<b>" + esc(r.u) + "</b> · OS " + esc(r.os) + "<br>Execução terminou em " + fmt(r.fim) + (r.parado != null ? " (" + r.parado + " dias parada)" : "") + "<br>" + (r.prazo ? "Prazo do relatório: " + fmt(r.prazo) + (r.sem_oleo ? " (sem análise de óleo)" : "") : "Sem prazo combinado") + (oil(r) ? "<br>* Aguarda laudo de óleo, não a Engenharia" : ""); };
    var tipF = function (r) { return "<b>" + esc(r.u) + "</b> · OS " + esc(r.os) + "<br>" + (r.tot ? r.pend + " de " + r.tot + " tarefas pendentes (" + Math.round(100 * r.pend / r.tot) + "%)" : (r.pend || 0) + " pendências em campo") + "<br>Atraso: " + (r.atraso == null ? "sem data" : r.atraso + " dias" + (r.atraso_fonte === "Fracttal" ? " (pela Data Programada no Fracttal)" : "")) + " · Prevista " + fmt(r.prev) + "<br>Bloqueio: " + (r.bl || []).map(function (b) { return CAUSE_LBL[b] || b; }).join(", "); };
    var html = '<div class="pa-fchips" id="pa-fchips"></div><p class="pa-meta">' + (K === "MPA" ? "Manutenções preventivas anuais" : "Manutenções preventivas semestrais") + " acompanhadas pela reunião de PCM (a curadoria), com a linha da Gerencial e as pendências da OS no Fracttal (pela Gestão PCM).</p>" + cards + hlHtml + charts;
    var g1 = G(1), g2 = G(2), g3 = G(3), g0 = G(0), pl = function (n) { return n + " " + K + (n > 1 ? "s" : ""); };
    if (g1.length) html += section("t1", 1, "Pendente revisão ou relatório por parte da Engenharia", pl(g1.length), table("t1", c1, g1, {k: "prazo", dir: 1, then: {k: "fim", dir: 1}}, {tip: tip1}), g1.some(oil) ? '<p class="pa-pe"><sup class="pa-ast">*</sup> Não é pendência da Engenharia: o relatório depende do laudo de análise de óleo do transformador, emitido por laboratório externo.</p>' : "");
    if (g2.length) html += section("t2", 2, "Poucas pendências, para auxílio da Manutenção", pl(g2.length), table("t2", cField(true), g2, {k: "pend", dir: 1, then: {k: "atraso", dir: -1}}, {tip: tipF}));
    if (g3.length) html += section("t3", 3, "Atrasadas e com mais pendências", pl(g3.length), table("t3", cField(false), g3, {k: "atraso", dir: -1}, {tip: tipF}));
    if (g0.length) html += section("t0", 0, "Fora do ranking", pl(g0.length), table("t0", c0, g0, {k: "prev", dir: 1}));
    if (!rowsAll.length) html += '<p class="pa-vazio pa-vazio--grande">' + (AV.curadoria ? "A curadoria do PCM não abriu: " + esc(AV.curadoria) + "." : "Nenhuma " + K + " na curadoria do PCM.") + "</p>";
    var esp = T.esp().filter(function (r) { return passes(r, tab); });
    var stCls = function (s) { return s === "Finalizado" ? "ok" : s === "Pendente Envio Relatório" ? "info" : s === "Em Execução" || s === "Refazer Pendências" ? "alerta" : ""; };
    var ce = [{k: "os", h: "OS", c: function (r) { return '<span class="pa-os gc-num">' + (esc(r.os) || "—") + "</span>"; }}, {k: "u", h: "Usina", c: function (r) { return usinaCell(r); }},
      {k: "ciclo", h: "Ciclo", cls: "num", c: function (r) { return esc(r.ciclo) || "—"; }}, {k: "prev", h: "Prevista", cls: "num", c: function (r) { return fmt(r.prev); }},
      {k: "status", h: "Status", c: function (r) { return '<span class="pa-st pa-st--' + (stCls(r.status) || "neutro") + ' pa-xf" data-xf="status" data-v="' + esc(r.status) + '" role="button" tabindex="0">' + (esc(r.status) || "—") + "</span>"; }},
      {k: "strel", h: "Status relatório", c: function (r) { return '<span class="pa-bloco">' + (esc(r.strel) || "—") + "</span>"; }}, {k: "sup", h: "Supervisor", c: function (r) { return r.sup ? xf("sup", r.sup) : "—"; }},
      {k: "g", h: "No painel", c: function (r) { return r.g == null ? '<span class="pa-bloco">—</span>' : '<span class="pa-st pa-st--' + ["neutro", "info", "alerta", "crit"][r.g] + '">' + SIT[r.g] + "</span>"; }},
      {k: "diasAtraso", h: "Atraso", cls: "num", c: function (r) { return r.atrasada ? '<span class="pa-atraso">' + r.diasAtraso + " d</span>" : "—"; }}];
    var soon = function (r) { if (!r.prev || r.status === "Finalizado") return false; var n = dd(r.prev); return n >= 0 && n <= 30; };
    if (D.esp.length) html += section("te", "A", "Todas as " + K + "s · espelho da Gerencial", esp.length + " linha" + (esp.length !== 1 ? "s" : ""), table("te", ce, esp, {k: "prev", dir: 1}, {page: 40, rowCls: function (r) { return soon(r) ? "pa-logo" : ""; }, tip: function (r) { return "<b>" + esc(r.u) + "</b> (" + esc(r.cli) + ")<br>Ciclo " + (esc(r.ciclo) || "—") + " · Prevista " + fmt(r.prev) + "<br>Status: " + (esc(r.status) || "—") + (soon(r) ? "<br>Prevista para os próximos 30 dias" : ""); }}), '<p class="pa-pe">A barra azul na lateral marca as ' + K + "s previstas para os próximos 30 dias que ainda não foram finalizadas.</p>");
    else html += '<div class="pa-aviso-inline"><i class="ph ph-lock-simple" aria-hidden="true"></i><span>O espelho da Gerencial (todas as ' + K + "s da aba MPAS) aparece quando o Nexus abrir a planilha da Gerencial: " + esc(AV.gerencial === "sem_chave" ? "falta a senha dela no servidor (NEXUS_PCM_MPAS_SENHA)" : AV.gerencial) + ".</span></div>";
    html += nota(["<b>Dias parado</b> conta da última execução registrada na OS até hoje. <b>Atraso</b> é o da Fila da Gestão PCM: da Data Prevista da Gerencial até hoje, para a MPA/MPS não concluída; sem a Gerencial, da Data Programada mais antiga das tarefas da OS no Fracttal.",
      "<b>Progresso</b> é a parcela de tarefas já feitas na OS (ou na cadeia de OS) no Fracttal, recalculada a cada leitura; o grupo, o prazo e o que falta são da reunião de PCM.",
      "<b>Resp. da Manutenção</b> segue a regra da curadoria (um responsável para o Norte e Nordeste, outro para o resto); fica \"A definir\" sem ela."]);
    return html;
  }

  /* ── Radar de Backlog ── */
  function titCell(t) { t = t || []; if (!t.length) return "—"; return '<div class="pa-tits">' + t.slice(0, 2).map(function (s) { return '<span class="pa-tit" title="' + esc(s) + '">' + esc(s) + "</span>"; }).join("") + (t.length > 2 ? '<span class="pa-cli">+' + (t.length - 2) + " outra" + (t.length - 2 > 1 ? "s" : "") + "</span>" : "") + "</div>"; }
  function renderBKL() {
    var tab = "bkl", all = BKL, rows = all.filter(function (r) { return passes(r, tab); });
    var baseId = all.filter(function (r) { return passes(r, tab, "idade"); }), baseTp = all.filter(function (r) { return passes(r, tab, "tipo"); });
    var selId = STATE.f.bkl.idade || new Set(), selTp = STATE.f.bkl.tipo || new Set();
    var n90 = baseId.filter(function (r) { return r.idade > 90; }).length, n6190 = baseId.filter(function (r) { return r.idade > 60 && r.idade <= 90; }).length, nCorr = baseTp.filter(function (r) { return r.tipo === "Corretiva"; }).length;
    var cards = '<div class="pa-cards">' + card("gA", rows.length, "OS em processo no backlog", "Total com os filtros atuais", 'data-reset-tab="1"', false, "<b>OS em processo no backlog</b><br>Total com os filtros atuais<br><span class='pa-tip-mudo'>Clique para limpar os filtros desta aba</span>")
      + card("g2", nCorr, "Corretivas", "Corretivas no backlog", 'data-xf="tipo" data-v="Corretiva" data-only="1"', selTp.size === 1 && selTp.has("Corretiva"), "<b>Corretivas</b><br>Clique para filtrar")
      + card("g3", n6190, "61 a 90 dias", "Abertas entre 2 e 3 meses", 'data-xf="idade" data-v="61 a 90 dias" data-only="1"', selId.has("61 a 90 dias"), "<b>61 a 90 dias</b><br>Clique para filtrar")
      + card("g0", n90, "Mais de 90 dias", "OS mais envelhecidas do backlog", 'data-xf="idade" data-v="Mais de 90 dias" data-only="1"', selId.has("Mais de 90 dias"), "<b>Mais de 90 dias</b><br>Clique para filtrar") + "</div>";
    var agrupa = function (campo) { var g = {}; rows.forEach(function (r) { var x = g[r[campo]] = g[r[campo]] || {label: r[campo], v: 0, unit: "OS"}; x.v++; }); return Object.keys(g).map(function (k) { return g[k]; }).sort(function (a, b) { return b.v - a.v; }); };
    var byI = {}; ["25 a 45 dias", "46 a 60 dias", "61 a 90 dias", "Mais de 90 dias"].forEach(function (k) { byI[k] = {label: k, v: 0, unit: "OS"}; }); rows.forEach(function (r) { byI[idadeFx(r.idade)].v++; });
    var charts = '<div class="pa-graficos"><div class="pa-painel"><h3>Backlog por cluster</h3><p class="pa-pequeno">Os 15 clusters com mais OS antigas. Clique para filtrar.</p>' + bars(agrupa("cluster").slice(0, 15), "cluster") + "</div>"
      + '<div class="pa-painel pa-painel--duplo"><div><h3>Por tipo de OS</h3>' + bars(agrupa("tipo"), "tipo") + "</div><div><h3>Por idade</h3>" + bars(Object.keys(byI).map(function (k) { return byI[k]; }).filter(function (x) { return x.v; }), "idade") + "</div></div></div>";
    var cols = [{k: "os", h: "OS", c: function (r) { return '<span class="pa-os gc-num">' + esc(r.os) + "</span>"; }}, {k: "tipo", h: "Tipo", c: function (r) { return xf("tipo", r.tipo); }},
      {k: "tit", h: "Tarefas em aberto", c: function (r) { return titCell(r.tit); }},
      {k: "u", h: "Usina", c: function (r) { return '<span class="pa-usina">' + esc(r.u) + '</span><span class="pa-cli">' + xf("cli", r.cli) + " · " + xf("cluster", r.cluster) + "</span>"; }},
      {k: "resp", h: "Responsável da OS", c: function (r) { return r.resp ? xf("resp", r.resp) : "—"; }}, {k: "cri", h: "Aberta em", cls: "num", c: function (r) { return fmt(r.cri); }},
      {k: "idade", h: "Idade", cls: "num", c: function (r) { return '<span class="pa-idade' + (r.idade > 90 ? " alta" : r.idade > 60 ? " media" : "") + '">' + r.idade + " d</span>"; }},
      {k: "pct", h: "Progresso", c: function (r) { return progMeter(r.pct, "ok"); }}];
    var tbl = section("tb", "A", "OS do backlog em processo", rows.length + " OS", table("tb", cols, rows, {k: "idade", dir: -1}, {page: 50, tip: function (r) { return "<b>OS " + esc(r.os) + "</b> · " + esc(r.tipo) + "<br>" + esc(r.u) + " (" + esc(r.cli) + ")<br>Aberta há " + r.idade + " dias · " + r.pct + "% concluído" + ((r.tit || []).length ? "<br><b>Tarefas em aberto:</b><br>" + r.tit.map(esc).join("<br>") : ""); }}));
    return '<div class="pa-fchips" id="pa-fchips"></div><p class="pa-meta">Todas as OS abertas há mais de 25 dias e ainda em processo no Fracttal (execução não concluída em campo), incluindo as preventivas MPA e MPS. Use o filtro "Tipo de OS" ao lado para recortar.</p>'
      + cards + charts + tbl + nota(["Entram OS de todos os tipos abertas há mais de 25 dias e com status <b>em processo</b> no Fracttal, ou seja, com execução ainda pendente em campo. As preventivas aparecem separadas em MPA e MPS pelo título das tarefas.",
        "A coluna <b>Tarefas em aberto</b> traz o título das tarefas ainda não concluídas na OS; as iguais aparecem agrupadas com \"(×N)\". Passe o mouse para ver a lista completa.",
        "OS em revisão (o técnico já concluiu, aguardando o fechamento) ficam fora desta análise."]);
  }

  /* ── o mapa de carga e mobilização (o desenho vem do servidor) ── */
  var fmtH = function (h) { var m = Math.round(h * 60); if (m < 60) return m + " min"; var hh = Math.floor(m / 60), mm = m % 60; return hh + " h" + (mm ? " " + String(mm).padStart(2, "0") + " min" : ""); };
  function mapLoad(r) { var sel = STATE.f.map.tipo; if (!sel || !sel.size) return {t: r.tarefas, o: r.os}; var t = 0; Object.keys(r.tipos).forEach(function (k) { if (sel.has(k)) t += r.tipos[k]; }); return {t: t, o: t ? r.os : 0}; }
  function renderMAP() {
    var S = STATE.map, rows = MAPROWS.filter(function (r) { return passes(r, "map"); });
    var noXY = rows.filter(function (r) { return !r.pt && r.tarefas; });
    var tot = rows.reduce(function (a, r) { var l = mapLoad(r); a.t += l.t; a.o += l.o; a.w += r.w42 || 0; if (l.t) a.u++; return a; }, {t: 0, o: 0, w: 0, u: 0});
    var cards = '<div class="pa-cards">' + card("gA", tot.u, "Usinas com carga", "de " + rows.length + " usinas no recorte", "", false, "<b>Usinas com OS em andamento</b><br>No recorte atual")
      + card("g2", tot.o, "OS em andamento", "com ao menos uma tarefa aberta", "", false, "<b>OS em andamento</b><br>Em processo no Fracttal, com tarefa aberta")
      + card("g3", nf(tot.t), "Tarefas abertas", "carga atual dos times", "", false, "<b>Tarefas abertas</b><br>Soma das tarefas não concluídas")
      + card("g0", nf(tot.w), "Programadas na Semana " + WCUR, "semana atual, no recorte", "", false, "<b>Programação da Semana " + WCUR + "</b><br>Tarefas planejadas na semana atual") + "</div>";
    var seg = function (name, val, opts) { return '<div class="pa-seg" role="group">' + opts.map(function (o) { return '<button type="button" data-' + name + '="' + o[0] + '" aria-pressed="' + (val === o[0]) + '">' + o[1] + "</button>"; }).join("") + "</div>"; };
    var tools = S.mode === "carga"
      ? seg("mode", S.mode, [["carga", "Carga dos times"], ["mob", "Mobilização"]]) + seg("group", S.group, [["cluster", "Por cluster"], ["usina", "Por usina"]]) + seg("size", S.size, [["tarefas", "Tarefas abertas"], ["os", "OS abertas"], ["w42", "Programadas S" + WCUR]])
      : seg("mode", S.mode, [["carga", "Carga dos times"], ["mob", "Mobilização"]]) + '<label class="pa-num-in">Fator de rota <input class="gc-campo" id="pa-fator" type="number" min="1" max="2" step="0.05" value="' + S.factor + '"></label><label class="pa-num-in">Velocidade (km/h) <input class="gc-campo" id="pa-vel" type="number" min="30" max="110" step="5" value="' + S.speed + '"></label><button type="button" class="gc-btn gc-btn--contorno" id="pa-limpar-rota">Limpar rota</button>';
    var cl = {};
    rows.forEach(function (r) { var l = mapLoad(r), c = cl[r.cluster] = cl[r.cluster] || {c: r.cluster, sup: r.sup, u: 0, o: 0, t: 0, w: 0, old: 0}; c.u++; c.o += l.o; c.t += l.t; c.w += r.w42 || 0; if (l.t) c.old = Math.max(c.old, r.maisantiga || 0); if (!c.sup && r.sup) c.sup = r.sup; });
    var atrCl = {}; D.esp.forEach(function (e) { if (e.atrasada) { var k = (e.cluster || "").toUpperCase(); atrCl[k] = (atrCl[k] || 0) + 1; } });
    var clRows = Object.keys(cl).map(function (k) { return cl[k]; }).filter(function (c) { return c.c !== "Sem cluster" || c.t; }).map(function (c) { return Object.assign({}, c, {mp: atrCl[c.c.toUpperCase()] || 0, eq: teamOf(c.c).length}); });
    var ranking = table("tm", [
      {k: "c", h: "Cluster", c: function (r) { return '<span class="pa-xf pa-usina" data-xf="cluster" data-v="' + esc(r.c) + '" role="button" tabindex="0">' + esc(r.c) + '</span><span class="pa-cli">' + esc(r.sup || "Sem supervisor") + "</span>"; }},
      {k: "t", h: "Tarefas", cls: "num", c: function (r) { return "<b>" + r.t + "</b>"; }}, {k: "o", h: "OS", cls: "num", c: function (r) { return r.o; }},
      {k: "w", h: "S" + WCUR, cls: "num", c: function (r) { return r.w; }},
      {k: "eq", h: "Equipe", c: function (r) { var t = teamOf(r.c); return t.length ? '<span class="pa-time">' + t.map(function (p) { return '<span><b>' + esc(p.nome) + '</b> <span class="pa-cli">' + esc(p.cargo) + "</span></span>"; }).join("") + "</span>" : '<span class="pa-tbd">Sem colaborador ativo</span>'; }},
      {k: "mp", h: "MPA/MPS atras.", cls: "num", c: function (r) { return r.mp ? '<span class="pa-atraso">' + r.mp + "</span>" : "—"; }},
      {k: "old", h: "Mais antiga", cls: "num", c: function (r) { return r.old ? '<span class="pa-idade' + (r.old > 60 ? " alta" : r.old > 35 ? " media" : "") + '">' + r.old + " d</span>" : "—"; }}],
      clRows, {k: "t", dir: -1}, {page: 15, tip: function (r) { return "<b>" + esc(r.c) + "</b> · " + esc(r.sup || "sem supervisor") + "<br>" + r.u + " usinas · " + r.o + " OS · " + r.t + " tarefas abertas<br>Semana " + WCUR + ": " + r.w + " tarefas programadas<br>MPA/MPS atrasadas: " + r.mp + teamTip(r.c); }});
    var legend = S.mode === "mob" ? '<p class="pa-pequeno">Cada ponto é uma usina. Clique numa para a origem e noutra para o destino, ou escolha pelo nome.</p>'
      : '<p class="pa-pequeno">O tamanho da bolha é ' + (S.size === "tarefas" ? "o número de tarefas abertas" : S.size === "os" ? "o número de OS em andamento" : "o número de tarefas programadas na Semana " + WCUR) + (S.group === "cluster" ? " do time (cluster), no centro das usinas dele" : " da usina") + ". Clique numa bolha para filtrar o cluster.</p>";
    var route = "", routeStats = "";
    if (S.mode === "mob") {
      var o = S.origin && MAPROWS.find(function (r) { return r.usina === S.origin; }), d = S.dest && MAPROWS.find(function (r) { return r.usina === S.dest; });
      var km = S.rota && S.rota.km != null && d ? S.rota.km : null, road = km != null ? km * S.factor : null, h = road != null ? road / S.speed : null;
      var stat = function (lbl, val, sub, big) { return '<div class="pa-rstat' + (big ? " grande" : "") + '"><span class="gc-rotulo">' + lbl + "</span><b>" + val + "</b><span>" + sub + "</span></div>"; };
      var lab = function (r) { return r ? r.u + " (" + r.cli + ")" : ""; };
      var equipe = function (r) { return teamOf(r.cluster).map(function (p) { return esc(p.nome) + " (" + esc(p.cargo) + ")"; }).join(", ") || "sem colaborador ativo"; };
      routeStats = '<div class="pa-rota"><div class="pa-rota-campos"><label><span class="gc-rotulo">Usina de origem</span><input class="gc-campo" id="pa-orig" list="pa-us" placeholder="Digite o nome da usina" value="' + esc(lab(o)) + '" autocomplete="off"></label>'
        + '<button type="button" class="gc-btn gc-btn--contorno pa-troca" id="pa-trocar" title="Inverter origem e destino" aria-label="Inverter origem e destino"><i class="ph ph-arrows-left-right" aria-hidden="true"></i></button>'
        + '<label><span class="gc-rotulo">Usina de destino</span><input class="gc-campo" id="pa-dest" list="pa-us" placeholder="Digite o nome da usina" value="' + esc(lab(d)) + '" autocomplete="off"></label><span class="pa-rmsg" id="pa-rmsg" role="status"></span>'
        + '<datalist id="pa-us">' + MAPROWS.filter(function (r) { return r.pt; }).sort(function (a, b) { return a.u.localeCompare(b.u, "pt", {numeric: true}); }).map(function (r) { return '<option value="' + esc(lab(r)) + '">' + esc(r.cluster) + "</option>"; }).join("") + "</datalist></div>"
        + '<div class="pa-rota-pontas" aria-live="polite"><span class="pa-rpt o">A</span><div><span class="gc-rotulo">Origem</span><b>' + (o ? esc(o.u) : "Clique numa usina no mapa") + "</b>" + (o ? "<span>" + esc(o.cluster) + " · " + esc(o.sup || "—") + "</span><span>Equipe: " + equipe(o) + "</span>" : "") + "</div>"
        + '<i class="ph ph-arrow-right pa-rseta" aria-hidden="true"></i><span class="pa-rpt d">B</span><div><span class="gc-rotulo">Destino</span><b>' + (d ? esc(d.u) : o ? "Clique no destino ou escolha acima" : "—") + "</b>" + (d ? "<span>" + esc(d.cluster) + " · " + esc(d.sup || "—") + "</span><span>Equipe: " + equipe(d) + "</span>" : "") + "</div></div>"
        + '<div class="pa-rstats">' + stat("Distância por estrada", road != null ? "~" + nf(Math.round(road)) + " km" : "—", "linha reta × fator " + String(S.factor).replace(".", ","), true)
        + stat("Tempo estimado", h != null ? "~" + fmtH(h) : "—", "a " + S.speed + " km/h de média", true) + stat("Linha reta", km != null ? nf(Math.round(km)) + " km" : "—", "distância geográfica", false) + "</div></div>";
      if (o && S.rota && S.rota.perto) {
        route = '<div class="pa-perto"><b>Mais próximas de ' + esc(o.u) + "</b>" + S.rota.perto.map(function (x) { var r = MAPROWS.find(function (m) { return m.usina === x.usina; }); if (!r) return ""; var rd = x.km * S.factor; return '<button type="button" class="pa-perto-lin" data-dest="' + esc(r.usina) + '"><span>' + esc(r.u) + '<span class="pa-cli">' + esc(r.cluster) + " · " + esc(r.sup || "—") + " · " + teamOf(r.cluster).length + " colaborador" + (teamOf(r.cluster).length === 1 ? "" : "es") + '</span></span><span class="num"><b>~' + Math.round(rd) + ' km</b><span class="pa-cli">~' + fmtH(rd / S.speed) + "</span></span></button>"; }).join("") + "</div>";
      }
    }
    var semMapa = !X.mapa ? '<div class="pa-aviso-inline"><i class="ph ph-map-trifold" aria-hidden="true"></i><span>O mapa precisa do cadastro de usinas do Nexus: ' + esc(AV.mapa || "ele não abriu nesta máquina") + ". A carga por cluster segue ao lado.</span></div>" : "";
    return '<div class="pa-fchips" id="pa-fchips"></div><p class="pa-meta">Carga atual dos times a partir das OS em andamento no Fracttal (tarefas não concluídas) e da programação da Semana ' + WCUR + ". Usinas no lugar do cadastro do Nexus; a coordenada não sai do servidor.</p>"
      + cards + '<div class="pa-mapa-grade"><div class="pa-painel"><div class="pa-mapa-ferr">' + tools + "</div>" + routeStats + legend + semMapa
      + (X.mapa ? '<div class="pa-mapa" id="pa-mapa"><svg id="pa-svg" class="pa-graf" role="img" aria-label="Mapa do Brasil com as usinas"></svg><div class="pa-zoom"><button type="button" data-zoom="1.5" aria-label="Aproximar"><i class="ph ph-plus" aria-hidden="true"></i></button><button type="button" data-zoom="0.667" aria-label="Afastar"><i class="ph ph-minus" aria-hidden="true"></i></button><button type="button" data-zoom="0" aria-label="Enquadrar"><i class="ph ph-corners-out" aria-hidden="true"></i></button></div><div class="pa-cl-leg" id="pa-cl-leg" aria-label="Clusters"></div></div>' : "")
      + route + (noXY.length ? '<p class="pa-pe">Sem coordenada no cadastro (fora do mapa, mas nos números): ' + noXY.map(function (r) { return esc(r.u); }).join(", ") + ".</p>" : "")
      + '</div><div class="pa-painel"><h3>Carga por time (cluster)</h3><p class="pa-pequeno">Clique no cluster para filtrar o mapa.</p>' + ranking + "</div></div>";
  }
  function pedirRota() {
    var S = STATE.map;
    if (!S.origin) { S.rota = null; return; }
    var q = new URLSearchParams({o: S.origin}); if (S.dest) q.set("d", S.dest);
    fetch((raiz.dataset.rota || "acompanhamento/rota") + "?" + q.toString(), {credentials: "same-origin"})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (j) { if (j && S.origin === q.get("o")) { S.rota = j; render(); } })
      .catch(function () { /* sem a distância, a rota fica com traço */ });
  }
  function mountMap() {
    var S = STATE.map, svg = $("#pa-svg"); if (!svg || !X.mapa) return;
    var vb0 = X.mapa.viewbox.split(" ").map(Number), W0 = vb0[2];
    var rows = MAPROWS.filter(function (r) { return passes(r, "map") && r.pt; });
    var s = '<rect x="-5000" y="-5000" width="10000" height="10000" class="pa-mar"/>';
    s += X.mapa.ufs.map(function (u) { return '<path d="' + u.d + '" class="pa-uf"/>'; }).join("");
    s += X.mapa.ufs.filter(function (u) { return u.x != null; }).map(function (u) { return '<text x="' + u.x + '" y="' + u.y + '" class="pa-uf-rot" text-anchor="middle">' + u.sigla + "</text>"; }).join("");
    var raioMax = 26;
    if (S.mode === "carga") {
      var pts;
      if (S.group === "cluster") {
        var g = {};
        rows.filter(function (r) { return r.cluster !== "Sem cluster"; }).forEach(function (r) { var l = mapLoad(r), c = g[r.cluster] = g[r.cluster] || {name: r.cluster, sup: r.sup, xs: 0, ys: 0, n: 0, t: 0, o: 0, w: 0, us: []}; c.xs += r.pt[0]; c.ys += r.pt[1]; c.n++; c.t += l.t; c.o += l.o; c.w += r.w42 || 0; c.us.push(r.u); });
        pts = Object.keys(g).map(function (k) { var c = g[k]; return {name: c.name, x: c.xs / c.n, y: c.ys / c.n, v: S.size === "tarefas" ? c.t : S.size === "os" ? c.o : c.w, tip: "<b>" + esc(c.name) + "</b> · " + esc(c.sup || "sem supervisor") + "<br>" + c.n + " usinas · " + c.o + " OS · " + c.t + " tarefas abertas<br>Semana " + WCUR + ": " + c.w + ' programadas<br><span class="pa-tip-mudo">' + esc(c.us.slice(0, 6).join(", ")) + (c.us.length > 6 ? "…" : "") + "</span>", cl: c.name}; });
      } else {
        pts = rows.map(function (r) { var l = mapLoad(r); return {name: r.u, x: r.pt[0], y: r.pt[1], v: S.size === "tarefas" ? l.t : S.size === "os" ? l.o : (r.w42 || 0), tip: "<b>" + esc(r.u) + "</b> (" + esc(r.cli) + ")<br>" + esc(r.cluster) + " · " + esc(r.sup || "—") + "<br>" + l.o + " OS · " + l.t + " tarefas abertas · mais antiga " + (r.maisantiga || 0) + " d<br>Semana " + WCUR + ": " + (r.w42 || 0) + " programadas", cl: r.cluster}; });
      }
      pts.forEach(function (p) { p.tip += teamTip(p.cl); });
      var max = Math.max.apply(null, [1].concat(pts.map(function (p) { return p.v; })));
      pts.sort(function (a, b) { return b.v - a.v; });
      var top = new Set(pts.slice(0, 8).map(function (p) { return p.name; })), selCl = STATE.f.map.cluster || new Set();
      s += pts.filter(function (p) { return p.v > 0; }).reverse().map(function (p) { var r = 4 + raioMax * Math.sqrt(p.v / max); return '<g class="pa-bolha' + (selCl.has(p.cl) ? " on" : "") + '" data-xf="cluster" data-v="' + esc(p.cl) + '" ' + tipAttr(p.tip + '<br><span class="pa-tip-mudo">Clique para filtrar o cluster</span>') + ' tabindex="0" role="button"><circle cx="' + p.x.toFixed(1) + '" cy="' + p.y.toFixed(1) + '" r="' + r.toFixed(1) + '"/>' + (top.has(p.name) ? '<text x="' + p.x.toFixed(1) + '" y="' + (p.y - r - 4).toFixed(1) + '" class="pa-bolha-rot" text-anchor="middle">' + esc(p.name) + " · " + p.v + "</text>" : "") + "</g>"; }).join("");
    } else {
      var o = S.origin && MAPROWS.find(function (r) { return r.usina === S.origin; }), d = S.dest && MAPROWS.find(function (r) { return r.usina === S.dest; });
      if (o && d && o.pt && d.pt) s += '<line x1="' + o.pt[0] + '" y1="' + o.pt[1] + '" x2="' + d.pt[0] + '" y2="' + d.pt[1] + '" class="pa-linha-rota"/>';
      s += rows.map(function (r) { var isO = o && o.usina === r.usina, isD = d && d.usina === r.usina; return '<g class="pa-ponto' + (isO ? " origem" : isD ? " destino" : "") + '" data-pick="' + esc(r.usina) + '" ' + tipAttr("<b>" + esc(r.u) + "</b> (" + esc(r.cli) + ")<br>" + esc(r.cluster) + " · " + esc(r.sup || "—") + "<br>" + r.os + " OS · " + r.tarefas + " tarefas abertas" + teamTip(r.cluster) + '<br><span class="pa-tip-mudo">Clique para definir ' + (o && !d ? "o destino" : "a origem") + "</span>") + ' tabindex="0" role="button"><circle cx="' + r.pt[0] + '" cy="' + r.pt[1] + '" r="' + (isO || isD ? 9 : 6) + '"/></g>'; }).join("");
    }
    svg.innerHTML = s;
    var lg = $("#pa-cl-leg");
    if (lg) { var cnt = {}; rows.forEach(function (r) { cnt[r.cluster] = (cnt[r.cluster] || 0) + 1; }); var sel = STATE.f.map.cluster || new Set();
      lg.innerHTML = "<b>Clusters (" + Object.keys(cnt).filter(function (c) { return c !== "Sem cluster"; }).length + ")</b>" + Object.keys(cnt).sort(function (a, b) { return a.localeCompare(b, "pt", {numeric: true}); }).map(function (c) { return '<button type="button" data-xf="cluster" data-v="' + esc(c) + '" aria-pressed="' + sel.has(c) + '">' + esc(c) + "<em>" + cnt[c] + "</em></button>"; }).join(""); }
    if (!S.vb) S.vb = vb0.slice();
    var marcas = function () { var z = S.vb[2] / W0, f = Math.pow(z, 0.9);
      svg.querySelectorAll(".pa-bolha circle,.pa-ponto circle").forEach(function (c) { if (!c.dataset.r0) c.dataset.r0 = c.getAttribute("r"); c.setAttribute("r", (+c.dataset.r0 * f).toFixed(2)); });
      svg.querySelectorAll(".pa-bolha").forEach(function (g) { var c = g.querySelector("circle"), t = g.querySelector("text"); if (!t) return; t.style.fontSize = (13 * f) + "px"; t.setAttribute("y", (+c.getAttribute("cy") - (+c.getAttribute("r")) - 4 * f).toFixed(2)); });
      svg.querySelectorAll(".pa-uf-rot").forEach(function (t) { t.style.fontSize = (14 * Math.pow(z, 0.6)) + "px"; });
      svg.querySelectorAll(".pa-linha-rota").forEach(function (l) { l.style.strokeWidth = (3 * f) + "px"; }); };
    var aplica = function () { svg.setAttribute("viewBox", S.vb.map(function (v) { return v.toFixed(2); }).join(" ")); marcas(); };
    aplica();
    var zoomAt = function (f, cx, cy) { var x = S.vb[0], y = S.vb[1], w = S.vb[2], h = S.vb[3], nw = Math.min(Math.max(w / f, W0 / 20), W0 * 1.2), nh = nw * h / w; S.vb = [cx - (cx - x) * nw / w, cy - (cy - y) * nh / h, nw, nh]; aplica(); };
    svg.onwheel = function (e) { e.preventDefault(); var r = svg.getBoundingClientRect(); zoomAt(e.deltaY < 0 ? 1.25 : 0.8, S.vb[0] + (e.clientX - r.left) / r.width * S.vb[2], S.vb[1] + (e.clientY - r.top) / r.height * S.vb[3]); };
    var drag = null;
    svg.onpointerdown = function (e) { if (e.target.closest(".pa-bolha,.pa-ponto")) return; e.preventDefault(); drag = {x: e.clientX, y: e.clientY, vb: S.vb.slice()}; svg.setPointerCapture(e.pointerId); svg.classList.add("arrastando"); };
    svg.onpointermove = function (e) { if (!drag) return; var r = svg.getBoundingClientRect(); S.vb = [drag.vb[0] - (e.clientX - drag.x) / r.width * drag.vb[2], drag.vb[1] - (e.clientY - drag.y) / r.height * drag.vb[3], drag.vb[2], drag.vb[3]]; aplica(); };
    svg.onpointerup = function () { drag = null; svg.classList.remove("arrastando"); };
    document.querySelectorAll("#pa [data-zoom]").forEach(function (b) { b.onclick = function () { var f = +b.dataset.zoom; if (!f) { S.vb = null; mountMap(); return; } zoomAt(f, S.vb[0] + S.vb[2] / 2, S.vb[1] + S.vb[3] / 2); }; });
    var fac = $("#pa-fator"), spd = $("#pa-vel");
    if (fac) fac.onchange = function () { S.factor = Math.min(2, Math.max(1, +fac.value || 1.3)); render(); };
    if (spd) spd.onchange = function () { S.speed = Math.min(110, Math.max(30, +spd.value || 70)); render(); };
    var clr = $("#pa-limpar-rota"); if (clr) clr.onclick = function () { S.origin = S.dest = null; S.rota = null; render(); };
    var findUs = function (txt) { var q = fold(txt).trim(); if (!q) return {u: null}; var com = MAPROWS.filter(function (r) { return r.pt; });
      var exato = com.find(function (r) { return fold(r.u + " (" + r.cli + ")") === q || fold(r.u) === q || fold(r.usina) === q; }); if (exato) return {u: exato};
      var parte = com.filter(function (r) { return fold(r.u + " (" + r.cli + ")").indexOf(q) >= 0; }); return parte.length === 1 ? {u: parte[0]} : {u: null, n: parte.length}; };
    var bindPick = function (id, key) { var el = $(id); if (!el) return; el.onchange = function () { var f = findUs(el.value), msg = $("#pa-rmsg");
        if (!el.value.trim()) { S[key] = null; if (key === "origin") S.rota = null; pedirRota(); render(); return; }
        if (f.u) { S[key] = f.u.usina; pedirRota(); render(); setTimeout(function () { var nx = key === "origin" ? $("#pa-dest") : null; if (nx && !S.dest) nx.focus(); }, 0); }
        else if (msg) msg.textContent = f.n ? f.n + " usinas combinam com “" + el.value + "”. Escolha uma da lista." : "Nenhuma usina com lugar no mapa para “" + el.value + "”."; };
      el.onkeydown = function (e) { if (e.key === "Enter") { e.preventDefault(); el.onchange(); } }; };
    bindPick("#pa-orig", "origin"); bindPick("#pa-dest", "dest");
    var sw = $("#pa-trocar"); if (sw) sw.onclick = function () { var t = S.origin; S.origin = S.dest; S.dest = t; pedirRota(); render(); };
  }

  /* ── One Page · o fechamento da semana ── */
  var CAT_ORDER = ["Preventivas (MPM e inspeções)", "Corretivas", "Religamentos", "Administrativas", "MPA", "Handover", "Zeladoria", "MPS"];
  var DOW = ["Seg", "Ter", "Qua", "Qui", "Sex"];
  function opData() {
    var O = X.open.filter(function (o) { return o.usina && !/teste/i.test(o.usina); }), clsup = function (c) { return X.clsup[(c || "").toUpperCase()] || "—"; };
    var short = function (u) { return u.replace(/^\s*[^-]+-\s*/, "").replace(/\s*-\s*[A-Z]{2}\s*$/, "").trim(); };
    var cliOf = function (u) { var c = (u.split(" - ")[0] || "").trim(); return /greenyellow/i.test(c) ? "GreenYellow" : /utragaz/i.test(c) ? "Ultragaz" : /renogrid/i.test(c) ? "RenoGrid" : c; };
    var byUs = {}; O.forEach(function (o) { var u = byUs[o.usina] = byUs[o.usina] || {u: o.usina, open: 0, corr: 0, old: 0}; u.open += o.open; if (/^Corretiva/.test(o.tipo)) u.corr++; u.old = Math.max(u.old, o.dias || 0); });
    var usRank = Object.keys(byUs).map(function (k) { return byUs[k]; }).sort(function (a, b) { return b.open - a.open; });
    var late35 = O.filter(function (o) { return (o.dias || 0) > 35; }), corrOS = O.filter(function (o) { return /^Corretiva/.test(o.tipo); });
    var rel = O.filter(function (o) { return /^Religamento/.test(o.tipo); }).sort(function (a, b) { return b.dias - a.dias; });
    var ho = O.filter(function (o) { return o.tipo === "Handover"; }).sort(function (a, b) { return b.dias - a.dias; });
    var rolTop = O.filter(function (o) { return X.rol[o.os]; }).map(function (o) { return Object.assign({}, o, {rol: X.rol[o.os]}); }).sort(function (a, b) { return b.rol - a.rol || b.dias - a.dias; }).slice(0, 10);
    var openBy = {}; O.forEach(function (o) { openBy[o.os] = o; });
    var mp = {}; D.esp.forEach(function (e) { if (!e.atrasada) return;
      var chain = ((PR[e.linha] || {}).cadeia || String(e.os || "").match(/\d{3,5}/g) || []).map(String);
      var live = chain.filter(function (n) { return openBy[n]; }), tasks = live.reduce(function (a, n) { return a + openBy[n].open; }, 0);
      if (!tasks) return;
      var old = Math.max.apply(null, live.map(function (n) { return openBy[n].dias || 0; })), key = e.u + "|" + e.tipo, cur = mp[key];
      if (!cur || old > cur.old) mp[key] = {u: e.u, cli: e.cli, tipo: e.tipo, os: live, tasks: tasks, old: old}; });
    var mpRows = Object.keys(mp).map(function (k) { return mp[k]; }).sort(function (a, b) { return b.old - a.old; });
    var W = WK[STATE.opWeek] || {tasks: [], ini: D.hoje, fim: D.hoje, fechado: ""}, T = W.tasks;
    var parcial = new Date(W.fim + "T00:00:00") >= TODAY, exec = T.reduce(function (a, t) { return a + t[6]; }, 0);
    var cats = {}; T.forEach(function (t) { var c = cats[t[5]] = cats[t[5]] || {n: 0, e: 0}; c.n++; c.e += t[6]; });
    var catRows = Object.keys(cats).map(function (k) { return {k: k, n: cats[k].n, e: cats[k].e}; }).sort(function (a, b) { var ia = CAT_ORDER.indexOf(a.k), ib = CAT_ORDER.indexOf(b.k); return ((ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib)) || b.n - a.n; });
    var supOf = function (t) { return (t[4] && t[4] !== "TBD") ? t[4] : (X.clsup[String(t[0]).toUpperCase()] || "Sem supervisor definido"); };
    var sups = {}; T.forEach(function (t) { var k = supOf(t), s = sups[k] = sups[k] || {s: k, d: [0, 0, 0, 0, 0], n: 0, e: 0}; if (t[1] != null && t[1] < 5) s.d[t[1]]++; s.n++; s.e += t[6]; });
    var supRows = Object.keys(sups).map(function (k) { return sups[k]; }).sort(function (a, b) { return b.n - a.n; });
    var ufOf = function (o) { var c = (o.cluster || "").slice(0, 2).toUpperCase(); if (/^[A-Z]{2}$/.test(c) && c !== "TE") return c; var m = o.usina.match(/-\s*([A-Z]{2})\s*$/); return m ? m[1] : "—"; };
    var reg = {}; O.filter(function (o) { return (o.dias || 0) > 0; }).forEach(function (o) { var uf = ufOf(o), R = reg[uf] = reg[uf] || {uf: uf, n: 0, cl: {}}, ck = o.cluster || "Sem cluster", C = R.cl[ck] = R.cl[ck] || {c: ck, n: 0, old: 0, us: {}};
      var U = C.us[o.usina] = C.us[o.usina] || {u: o.usina, n: 0, old: 0, os: []}; R.n += o.open; C.n += o.open; U.n += o.open; C.old = Math.max(C.old, o.dias); U.old = Math.max(U.old, o.dias); U.os.push(o); });
    var vals = function (o) { return Object.keys(o).map(function (k) { return o[k]; }); };
    var regions = vals(reg).map(function (R) { return Object.assign({}, R, {cls: vals(R.cl).map(function (C) { return Object.assign({}, C, {uss: vals(C.us).map(function (U) { return Object.assign({}, U, {os: U.os.sort(function (a, b) { return b.dias - a.dias; })}); }).sort(function (a, b) { return b.n - a.n; })}); }).sort(function (a, b) { return b.n - a.n; })}); }).sort(function (a, b) { return b.n - a.n; });
    return {usRank: usRank, late35: late35, corrOS: corrOS, rel: rel, ho: ho, rolTop: rolTop, mpRows: mpRows, short: short, cliOf: cliOf, clsup: clsup, W: W, T: T, parcial: parcial, exec: exec, catRows: catRows, supRows: supRows, regions: regions};
  }
  function renderOP() {
    if (!WKEYS.length) return '<p class="pa-vazio pa-vazio--grande">Sem a programação semanal agora: ' + esc(AV.bd || "o banco_dados.json não abriu") + ".</p>";
    var d = opData(), S = d.short, W = d.W, sem = STATE.opWeek;
    var dcls = function (n) { return n >= 60 ? "r" : n >= 35 ? "a" : ""; }, pct = function (e, n) { return n ? Math.round(100 * e / n) : 0; };
    var lateOS = d.late35.slice().sort(function (a, b) { return b.dias - a.dias; }), lateTasks = d.late35.reduce(function (a, o) { return a + o.open; }, 0);
    var mpTasks = d.mpRows.reduce(function (a, r) { return a + r.tasks; }, 0), rel35 = d.rel.filter(function (o) { return o.dias > 35; }).length;
    var hoTasks = d.ho.reduce(function (a, o) { return a + o.open; }, 0), hoUs = new Set(d.ho.map(function (o) { return o.usina; })).size;
    var restOpen = d.usRank.slice(10).reduce(function (a, u) { return a + u.open; }, 0), totExec = pct(d.exec, d.T.length), ini = fmt(W.ini), fim = fmt(W.fim);
    var corte = d.parcial ? "Parcial até " + fmt(D.hoje) : "Corte de sexta " + fim;
    var head = function (t, sub, pg) { return '<div class="pa-op-cab"><div><div class="pa-op-kicker">GRID CO. · OPERAÇÃO DE ATIVOS · PCM' + (pg > 1 ? " · FECHAMENTO DA SEMANA " + sem + " · CONTINUAÇÃO" : "") + "</div><h1" + (pg > 1 ? ' class="menor"' : "") + ">" + t + "</h1>" + (sub ? '<p class="pa-op-sub">' + sub + "</p>" : "") + "</div>"
      + (pg === 1 ? '<div class="pa-op-meta"><div class="pa-op-pilulas"><span class="pil escura">Semana ' + sem + " · " + ini + " a " + fim + '</span><span class="pil verde">' + corte + '</span><span class="pil">Gerado em ' + fmt(D.hoje) + '</span></div><span class="pa-op-fonte">Fontes: Fracttal (pela Gestão PCM, ' + fmt(D.hoje) + ") · Programação Semana " + sem + (W.fechado ? " (plano gerado em " + esc(W.fechado) + ")" : "") + " · Gerencial PCM 2026</span></div>" : '<span class="pa-op-fonte">foto de ' + fmt(D.hoje) + "</span>") + "</div>"; };
    var foot = function (n, txt) { return '<div class="pa-op-pe"><span>Grid Co. · PCM · Fechamento da Semana ' + sem + " · página " + n + "</span><span>" + (txt || "") + "</span></div>"; };
    var bar = function (p) { return '<span class="pa-op-barra"><i style="width:' + Math.max(p, 1) + '%"></i></span>'; };
    var pages = [];
    pages.push('<div class="pa-op-pag">' + head("Fechamento da Semana " + sem + ": o que rodou e o que ficou", "Gerado a partir do Acompanhamento do PCM no Nexus. Informativo para o time; prioridades e decisões com a coordenação.", 1)
      + '<div class="pa-op-kpis"><div><b class="' + (totExec >= 70 ? "g" : totExec >= 50 ? "" : "r") + '">' + totExec + "%</b><span>execução da semana (" + nf(d.exec) + " de " + nf(d.T.length) + " tarefas programadas)</span></div>"
      + '<div><b class="r">' + d.corrOS.length + "</b><span>corretivas abertas (OS vivas, emergenciais incluídas)</span></div>"
      + '<div><b class="r">' + lateTasks + "</b><span>tarefas atrasadas há mais de 35 dias, em " + d.late35.length + " OS</span></div>"
      + '<div><b class="r">' + mpTasks + "</b><span>tarefas de MPA/MPS atrasadas, em " + d.mpRows.length + " usinas</span></div>"
      + '<div><b class="' + (rel35 ? "a" : "g") + '">' + d.rel.length + "</b><span>religamentos em aberto; " + (rel35 ? rel35 + " acima de 35 dias" : "nenhum acima de 35 dias") + "</span></div></div>"
      + '<div class="pa-op-lin"><section class="pa-op-caixa"><div class="pa-op-k">1 · PLANEJADO × EXECUTADO</div><h2>Por tipo de tarefa (' + (d.parcial ? "até hoje" : "até o corte") + ")</h2>"
      + '<table><thead><tr><th>Tipo</th><th class="n">Planejadas</th><th class="n">Executadas</th><th style="width:150px">%</th></tr></thead><tbody>'
      + d.catRows.map(function (c) { var p = pct(c.e, c.n); return "<tr><td><b>" + esc(c.k) + '</b></td><td class="n">' + c.n + '</td><td class="n">' + c.e + '</td><td><span class="pa-op-pct ' + (p >= 70 ? "g" : p >= 40 ? "a" : "r") + '">' + p + "%</span>" + bar(p) + "</td></tr>"; }).join("")
      + '<tr class="tot"><td><b>Total</b></td><td class="n"><b>' + d.T.length + '</b></td><td class="n"><b>' + d.exec + "</b></td><td><b>" + totExec + "%</b></td></tr></tbody></table>"
      + '<p class="pa-op-nota">Executada = tarefa da Programação Semana ' + sem + " finalizada (a régua do Fechamento da semana do Nexus: status Finalizados na linha do plano). As linhas fora do plano ficam de fora.</p></section>"
      + '<section class="pa-op-caixa"><div class="pa-op-k">2 · QUEM FAZ O QUÊ</div><h2>Tarefas por supervisor e dia · total e executadas</h2><table><thead><tr><th>Supervisor</th>' + DOW.map(function (x) { return '<th class="n">' + x + "</th>"; }).join("") + '<th class="n">Total</th><th class="n">Exec.</th><th class="n">%</th></tr></thead><tbody>'
      + d.supRows.map(function (s) { var p = pct(s.e, s.n); return "<tr><td><b>" + esc(s.s) + "</b></td>" + s.d.map(function (v) { return '<td class="n">' + v + "</td>"; }).join("") + '<td class="n"><b>' + s.n + '</b></td><td class="n">' + s.e + '</td><td class="n ' + (p >= 70 ? "g" : p >= 40 ? "a" : "r") + '"><b>' + p + "%</b></td></tr>"; }).join("")
      + '</tbody></table><p class="pa-op-nota">Supervisor = responsável da equipe na Programação Semanal; quando ela não informa, o supervisor do cluster.</p></section></div>'
      + '<div class="pa-op-lin"><section class="pa-op-caixa"><div class="pa-op-k">3 · USINAS QUE PEDEM ATENÇÃO</div><h2>Ordenado por tarefas em aberto (OS vivas)</h2><table><thead><tr><th style="width:22px">#</th><th>Usina</th><th class="n">Em aberto</th><th class="n">Corr.+Emerg.</th><th class="n">Mais antiga</th></tr></thead><tbody>'
      + d.usRank.slice(0, 10).map(function (u, i) { return "<tr><td>" + (i + 1) + "</td><td><b>" + esc(S(u.u)) + " (" + esc(d.cliOf(u.u)) + ')</b></td><td class="n">' + u.open + '</td><td class="n">' + (u.corr || "—") + '</td><td class="n ' + dcls(u.old) + '">' + u.old + " d</td></tr>"; }).join("")
      + '</tbody></table><p class="pa-op-nota">As demais ' + Math.max(d.usRank.length - 10, 0) + " usinas somam " + nf(restOpen) + " tarefas em aberto.</p></section>"
      + '<section class="pa-op-caixa"><div class="pa-op-k">4 · TOP 10 · TAREFAS QUE MAIS ROLARAM</div><h2>Nº de semanas em que a OS entrou na programação</h2><table><thead><tr><th>OS</th><th>Usina</th><th>Tarefa</th><th>Tipo</th><th class="n">Semanas</th></tr></thead><tbody>'
      + d.rolTop.map(function (o) { return "<tr><td><b>" + esc(o.os) + "</b></td><td>" + esc(S(o.usina)) + "</td><td>" + esc(o.desc) + "</td><td>" + esc(o.tipo) + '</td><td class="n ' + (o.rol >= 10 ? "r" : o.rol >= 7 ? "a" : "") + '"><b>' + o.rol + "×</b></td></tr>"; }).join("")
      + '</tbody></table><p class="pa-op-nota">Rolagem = a OS voltou para a programação em outra semana sem ser concluída (o "Nº vezes programada" do PCM).</p></section></div>'
      + foot(1, "continua: atrasadas, religamentos, MPAS, handovers e backlog por região") + "</div>");
    pages.push('<div class="pa-op-pag">' + head("Atrasadas há mais de 35 dias e religamentos em aberto", "", 2)
      + '<section class="pa-op-caixa"><div class="pa-op-k">5 · ATRASADAS HÁ MAIS DE 35 DIAS · AGRUPADAS POR OS</div><h2>As 12 OS mais antigas (de ' + d.late35.length + ")</h2><table><thead><tr><th class=\"n\">Dias</th><th>OS</th><th>Cliente · usina</th><th>Tarefa(s) em aberto</th><th class=\"n\">Faltam</th><th>Responsável</th><th>Supervisor</th></tr></thead><tbody>"
      + lateOS.slice(0, 12).map(function (o) { return '<tr><td class="n ' + dcls(o.dias) + '"><b>' + o.dias + " d</b></td><td><b>" + esc(o.os) + "</b></td><td>" + esc(d.cliOf(o.usina)) + " · " + esc(S(o.usina)) + "</td><td>" + esc(o.tipo) + ": " + esc(o.desc) + '</td><td class="n"><b>' + o.open + "/" + o.tot + "</b></td><td>" + esc(o.resp) + "</td><td>" + esc(d.clsup(o.cluster)) + "</td></tr>"; }).join("")
      + '</tbody></table><p class="pa-op-nota">Dias = desde a data programada mais antiga das tarefas abertas. Faltam = tarefas abertas ÷ total da OS. Só OS vivas.</p></section>'
      + '<section class="pa-op-caixa"><div class="pa-op-k">6 · RELIGAMENTOS EM ABERTO</div><h2>' + d.rel.length + " OS vivas, " + (rel35 ? rel35 + " acima de 35 dias" : "nenhuma acima de 35 dias") + '</h2><table><thead><tr><th class="n">Dias</th><th>OS</th><th>Usina</th><th>Tipo</th><th>Responsável</th><th>Supervisor</th></tr></thead><tbody>'
      + d.rel.slice(0, 12).map(function (o) { return '<tr><td class="n ' + (o.dias > 35 ? "r" : o.dias >= 21 ? "a" : "") + '"><b>' + o.dias + " d</b></td><td><b>" + esc(o.os) + "</b></td><td>" + esc(S(o.usina)) + " (" + esc(d.cliOf(o.usina)) + ")</td><td>" + esc(o.tipo) + "</td><td><b>" + esc(o.resp) + "</b></td><td>" + esc(d.clsup(o.cluster)) + "</td></tr>"; }).join("")
      + '</tbody></table><p class="pa-op-nota">Só religamentos com OS em andamento no Fracttal.</p></section>' + foot(2) + "</div>");
    pages.push('<div class="pa-op-pag">' + head("MPAS atrasadas e handovers em andamento", "", 3)
      + '<section class="pa-op-caixa"><div class="pa-op-k">7 · MPAS ATRASADAS · UMA LINHA POR USINA</div><h2>Anuais e semestrais atrasadas: ' + Math.min(12, d.mpRows.length) + " usinas mais antigas (de " + d.mpRows.length + ')</h2><table><thead><tr><th>Usina</th><th>Tipo</th><th>OS</th><th class="n">Tarefas abertas</th><th class="n">Mais antiga</th><th>Resp. da Manutenção</th></tr></thead><tbody>'
      + d.mpRows.slice(0, 12).map(function (r) { var rec = D.mpa.concat(D.mps).find(function (x) { return x.u === r.u && x.tipo === r.tipo; }); return "<tr><td><b>" + esc(r.u) + " (" + esc(r.cli) + ")</b></td><td>" + r.tipo + "</td><td>" + esc(r.os.join(", ")) + '</td><td class="n">' + r.tasks + '</td><td class="n ' + dcls(r.old) + '"><b>' + r.old + " d</b></td><td>" + esc((rec && rec.manut) || "—") + "</td></tr>"; }).join("")
      + '</tbody></table><p class="pa-op-nota">' + (D.esp.length ? "Carteira toda: " + mpTasks + " tarefas de MPA/MPS atrasadas em " + d.mpRows.length + " usinas. Atraso pela Fila da Gestão PCM (Data Prevista da Gerencial); só usinas com tarefa aberta em campo." : "Sem a planilha da Gerencial no Nexus agora: esta seção fica vazia até ela abrir.") + "</p></section>"
      + '<section class="pa-op-caixa"><div class="pa-op-k">8 · HANDOVERS EM ANDAMENTO</div><h2>Entrada de usinas: ' + hoTasks + " tarefas vivas em " + hoUs + ' usinas</h2><table><thead><tr><th>Usina</th><th>OS</th><th class="n">Tarefas</th><th class="n">Mais antiga</th><th>Responsável</th><th>Supervisor</th></tr></thead><tbody>'
      + d.ho.slice(0, 14).map(function (o) { return "<tr><td><b>" + esc(S(o.usina)) + " (" + esc(d.cliOf(o.usina)) + ")</b></td><td><b>OS " + esc(o.os) + '</b></td><td class="n">' + o.open + '</td><td class="n ' + dcls(o.dias) + '"><b>' + o.dias + " d</b></td><td><b>" + esc(o.resp) + "</b></td><td>" + esc(d.clsup(o.cluster)) + "</td></tr>"; }).join("")
      + '</tbody></table><p class="pa-op-nota">Só OS vivas.' + (d.ho.length > 14 ? " Mais " + (d.ho.length - 14) + " OS de handover não listadas." : "") + "</p></section>" + foot(3) + "</div>");
    var COLH = 618, H = {reg: 30, cl: 24, us: 21, os: 16, more: 15, gap: 6}, blocks = [];
    d.regions.forEach(function (R) {
      blocks.push({h: H.reg, html: '<div class="pa-bk-reg">' + esc(R.uf) + " · " + R.n + " tarefas atrasadas · " + R.cls.length + " cluster(s)</div>"});
      R.cls.forEach(function (C) {
        blocks.push({h: H.cl, html: '<div class="pa-bk-cl"><b>' + esc(C.c) + "</b><span>" + C.n + ' atrasadas · mais antiga <b class="' + dcls(C.old) + '">' + C.old + "d</b></span></div>"});
        C.uss.forEach(function (U) { var shown = U.os.slice(0, 4), extra = U.os.length - shown.length;
          blocks.push({h: H.us + shown.length * H.os + (extra ? H.more : 0) + H.gap, html: '<div class="pa-bk-us"><div class="pa-bk-ush"><b>' + esc(S(U.u)) + '</b> <span class="cli">(' + esc(d.cliOf(U.u)) + ")</span><span>" + U.n + ' atrasadas · mais antiga <b class="' + dcls(U.old) + '">' + U.old + "d</b></span></div>"
            + shown.map(function (o) { return '<div class="pa-bk-os"><span class="n ' + dcls(o.dias) + '"><b>' + o.dias + "d</b></span><span><b>OS " + esc(o.os) + '</b></span><span class="t">' + esc(o.tipo) + '</span><span class="d">' + esc(o.desc) + (o.open > 1 ? " · <b>" + o.open + " tarefas</b>" : "") + '</span><span class="r">' + esc(o.resp) + "</span></div>"; }).join("")
            + (extra ? '<div class="pa-bk-mais">+ ' + extra + " OS atrasadas nesta usina</div>" : "") + "</div>"}); });
      });
    });
    var cols = [], cur = [], used = 0;
    blocks.forEach(function (b) { if (used + b.h > COLH && cur.length) { cols.push(cur); cur = []; used = 0; } cur.push(b.html); used += b.h; });
    if (cur.length) cols.push(cur);
    for (var i = 0; i < cols.length; i += 2) {
      var pg = pages.length + 1;
      pages.push('<div class="pa-op-pag">' + head(i === 0 ? "9 · Backlog atrasado por região, cluster e usina" : "9 · Backlog atrasado por região (continuação)", "", pg)
        + '<p class="pa-op-nota">Só tarefas atrasadas (data programada já passou) de OS vivas · até 4 OS por usina · coluna final: responsável da OS</p>'
        + '<div class="pa-bk-cols"><div>' + cols[i].join("") + "</div><div>" + (cols[i + 1] || []).join("") + "</div></div>" + foot(pg, i + 2 >= cols.length ? "fim do relatório" : "continua") + "</div>");
    }
    var opts = WKEYS.map(function (k) { return '<option value="' + k + '"' + (k === sem ? " selected" : "") + ">Semana " + k + " · " + fmt(WK[k].ini) + " a " + fmt(WK[k].fim) + (new Date(WK[k].fim + "T00:00:00") >= TODAY ? " (parcial)" : "") + "</option>"; }).join("");
    return '<div class="pa-op-barra-topo"><div><h2>Fechamento da Semana ' + sem + '</h2><p class="pa-pequeno">' + pages.length + ' páginas no modelo do Fechamento semanal do PCM, com os dados de agora. "Imprimir / PDF" imprime só as páginas; para guardar, escolha "Salvar como PDF".</p></div>'
      + '<div class="pa-op-acoes"><label class="pa-num-in">Semana <select class="gc-campo" id="pa-op-semana">' + opts + '</select></label><button class="gc-btn gc-btn--primario" id="pa-op-imprimir" type="button"><i class="ph ph-printer" aria-hidden="true"></i>Imprimir / PDF</button></div></div>'
      + '<div class="pa-op-folhas" id="pa-op-folhas">' + pages.join("") + "</div>";
  }
  function mountOP() {
    var ws = $("#pa-op-semana"); if (ws) ws.onchange = function () { STATE.opWeek = ws.value; render(); };
    var bt = $("#pa-op-imprimir"); if (bt) bt.onclick = function () { document.documentElement.classList.add("pa-imprime-op"); window.print(); };
  }
  window.addEventListener("afterprint", function () { document.documentElement.classList.remove("pa-imprime-op"); });

  /* ── o desenho geral ── */
  function renderChips() {
    var tab = STATE.tab, box = $("#pa-fchips"); if (!box) return;
    var parts = [];
    if ((STATE.q[tab] || "").trim()) parts.push('<span class="pa-fchip">Pesquisa: “' + esc(STATE.q[tab].trim()) + '”<button type="button" data-rmq="1" aria-label="Limpar pesquisa"><i class="ph ph-x" aria-hidden="true"></i></button></span>');
    TABS[tab].filters.forEach(function (def) { var s = STATE.f[tab][def.k]; if (s && s.size) Array.from(s).forEach(function (v) { parts.push('<span class="pa-fchip">' + esc(def.l) + ": " + esc(v) + '<button type="button" data-rm="' + def.k + '" data-v="' + esc(v) + '" aria-label="Remover filtro ' + esc(def.l) + " " + esc(v) + '"><i class="ph ph-x" aria-hidden="true"></i></button></span>'); }); });
    box.innerHTML = parts.join("");
  }
  function render() {
    var tab = STATE.tab;
    document.querySelectorAll("#pa .pa-aba").forEach(function (t) { var on = t.dataset.tab === tab; t.setAttribute("aria-selected", String(on)); t.tabIndex = on ? 0 : -1; });
    $("#pa-titulo").textContent = TITULOS[tab];
    $("#pa-main").innerHTML = tab === "bkl" ? renderBKL() : tab === "map" ? renderMAP() : tab === "op" ? renderOP() : renderPM();
    if (tab === "map") mountMap();
    if (tab === "op") mountOP();
    renderFilters(); renderChips();
    raiz.classList.toggle("pa--op", tab === "op");
    var n = TABS[tab].rows().filter(function (r) { return passes(r, tab); }).length, tot = TABS[tab].rows().length;
    $("#pa-mostrando").textContent = tab === "op" ? "" : "Mostrando " + n + " de " + tot + " " + (tab === "bkl" ? "OS" : tab === "map" ? "usinas" : TABS[tab].kind + "s");
    try { var u = new URL(location.href); u.searchParams.set("aba", tab); history.replaceState(null, "", u); } catch (e) { /* endereço sem a aba */ }
  }

  /* ── os cliques (delegados, como no painel) ── */
  var main = $("#pa-main");
  main.addEventListener("click", function (e) {
    if (e.target.closest("[data-rmq]")) { STATE.q[STATE.tab] = ""; syncSearch(); render(); return; }
    var rm = e.target.closest("[data-rm]"); if (rm) { STATE.f[STATE.tab][rm.dataset.rm].delete(rm.dataset.v); render(); return; }
    var cardEl = e.target.closest("[data-card]"); if (cardEl) { toggle(STATE.tab, "g", cardEl.dataset.card, true); return; }
    if (e.target.closest("[data-reset-tab]")) { STATE.f[STATE.tab] = {}; render(); return; }
    var x = e.target.closest("[data-xf]"); if (x) { toggle(STATE.tab, x.dataset.xf, x.dataset.v, !!x.dataset.only); return; }
    var th = e.target.closest("[data-sort]"); if (th) { var k = th.dataset.sort, key = th.dataset.key, cur = STATE.sort[key]; STATE.sort[key] = cur && cur.k === k ? {k: k, dir: -cur.dir} : {k: k, dir: 1}; render(); return; }
    var more = e.target.closest("[data-more]"); if (more) { var mk = more.dataset.more; STATE.limit[mk] = (STATE.limit[mk] || +more.dataset.step) + (+more.dataset.step); render(); return; }
    var segb = e.target.closest("[data-mode],[data-group],[data-size]"); if (segb) { var S = STATE.map; if (segb.dataset.mode) S.mode = segb.dataset.mode; if (segb.dataset.group) S.group = segb.dataset.group; if (segb.dataset.size) S.size = segb.dataset.size; render(); return; }
    var pick = e.target.closest("[data-pick]"); if (pick) { var M = STATE.map, us = pick.dataset.pick; if (!M.origin || M.dest) { M.origin = us; M.dest = null; } else if (us !== M.origin) M.dest = us; pedirRota(); render(); return; }
    var nd = e.target.closest("[data-dest]"); if (nd) { STATE.map.dest = nd.dataset.dest; pedirRota(); render(); return; }
    var pt = e.target.closest("[data-goto]"); if (pt) { var tr = document.querySelector('#pa tr[data-os="' + pt.dataset.goto + '"]'); if (tr) { tr.scrollIntoView({block: "center"}); tr.classList.remove("pa-pisca"); void tr.offsetWidth; tr.classList.add("pa-pisca"); } }
  });
  main.addEventListener("keydown", function (e) { if ((e.key === "Enter" || e.key === " ") && e.target.matches("[data-xf],[data-goto],[data-pick]")) { e.preventDefault(); e.target.dispatchEvent(new MouseEvent("click", {bubbles: true})); } });
  var gq = $("#pa-busca"), gqx = $("#pa-busca-x"), gqT = null;
  function syncSearch() { gq.value = STATE.q[STATE.tab] || ""; gqx.hidden = !gq.value; }
  gq.addEventListener("input", function () { STATE.q[STATE.tab] = gq.value; gqx.hidden = !gq.value; clearTimeout(gqT); gqT = setTimeout(function () { STATE.limit = {}; render(); }, 180); });
  gq.addEventListener("keydown", function (e) { if (e.key === "Escape") { STATE.q[STATE.tab] = ""; syncSearch(); render(); } });
  gqx.addEventListener("click", function () { STATE.q[STATE.tab] = ""; syncSearch(); render(); gq.focus(); });
  var abas = Array.from(document.querySelectorAll("#pa .pa-aba"));
  abas.forEach(function (t, i) {
    t.addEventListener("click", function () { if (!STATE) return; STATE.tab = t.dataset.tab; closePanel(); syncSearch(); render(); window.scrollTo({top: 0}); });
    t.addEventListener("keydown", function (e) { var j = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null; if (j == null) return; e.preventDefault(); var n = abas[(j + abas.length) % abas.length]; n.focus(); n.click(); });
  });
  $("#pa-limpar").addEventListener("click", function () { if (!STATE) return; STATE.f[STATE.tab] = {}; STATE.q[STATE.tab] = ""; syncSearch(); render(); });

  /* ── os dados: uma leitura, do servidor ── */
  function avisos() {
    var box = $("#pa-avisos"), itens = [];
    if (AV.gestao) itens.push(["critico", "warning-circle", "<strong>Não consegui ler o Fracttal pela Gestão PCM agora</strong> (" + esc(AV.gestao) + "). MPA, MPS, o Radar e o mapa ficam sem as OS até ela voltar."]);
    if (AV.curadoria) itens.push(["alerta", "notebook", "<strong>A curadoria do PCM não abriu</strong> (" + esc(AV.curadoria) + "): as abas MPA e MPS ficam vazias até ela voltar."]);
    if (AV.curadoria_ilegiveis) itens.push(["alerta", "lock-simple", AV.curadoria_ilegiveis + " item(ns) da curadoria não abriram com a chave deste Nexus e ficaram de fora."]);
    if (AV.gerencial && AV.gerencial !== "sem_chave") itens.push(["alerta", "lock-simple", "<strong>Sem a planilha da Gerencial agora</strong> (" + esc(AV.gerencial) + ")."]);
    box.innerHTML = itens.map(function (x) { return '<div class="pcm-aviso pcm-aviso--' + x[0] + '"><i class="ph ph-' + x[1] + '" aria-hidden="true"></i><div>' + x[2] + "</div></div>"; }).join("");
    var F = window.__PA_FONTES || {};
    var partes = [];
    if (F.gestao) partes.push("Fracttal de " + String(F.gestao).slice(0, 16).replace("T", " ") + " (pela Gestão PCM)");
    if (F.bd) partes.push("programação de " + String(F.bd).slice(0, 16).replace("T", " "));
    partes.push(F.gerencial ? "Gerencial de " + String(F.gerencial).slice(0, 10) : "sem a Gerencial");
    partes.push(F.curadoria === "arquivo" ? "curadoria do arquivo de prova" : "curadoria do banco");
    $("#pa-fonte").textContent = "Lê " + partes.join(" · ") + ".";
  }
  fetch(raiz.dataset.dados || "acompanhamento/dados.json", {credentials: "same-origin"})
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (j) {
      D = j.DATA; X = j.EXTRA; COLAB = j.COLAB || []; AV = j.AVISOS || {}; window.__PA_FONTES = j.FONTES || {};
      preparar(); avisos(); syncSearch(); render();
    })
    .catch(function (e) { $("#pa-main").innerHTML = '<div class="pcm-aviso pcm-aviso--critico"><i class="ph ph-warning-circle" aria-hidden="true"></i><div><strong>Não consegui montar o acompanhamento agora</strong> (' + esc(e.message) + "). Recarregue em instantes.</div></div>"; });
})();
