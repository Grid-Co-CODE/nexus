/* static/coletas-furos.js — a aba "Furos de coleta" da tela Coletas (16/11/2026; redesenhada em 19/11/2026).

   É a tela do relatório R01 da analista de Performance (`Gerador_Furos_Coleta\template2.html`), com a conta dela portada função a função
   (itens, "UFV toda", natureza Geração/ETM, validação por dia, vigência, sugestões, CSV), e:
   - o dado vem do Nexus (`/coletas/furos/r01`: o banco e o COS), não de um HTML gerado à mão;
   - a validação é de TODOS: vai ao servidor a cada mudança (só o que mudou, com o `t` que esta tela viu; se outra pessoa
     mexeu na mesma chave antes, o servidor recusa e a tela recarrega);
   - o desenho de 19/11/2026 (Levi: "ao clicar, tá aparecendo uma linha grossa por campo que tá faltando [...] linka com
     as ocorrências [...] do COS para responder [...] se naquele dia teve desligamento, foi de que horas até que horas [...]
     mais visual também, por cliente [...] por tamanho do furo [...] diminua as informações"): quatro números, o tamanho do
     furo por cliente em barras, uma tira do mês por usina (um quadrado por dia, com o ponto do COS), e no clique o que o
     COS registrou (com as horas) e o mapa do mês, onde se marca o dia e se valida numa barra só. Os inversores com o mesmo
     furo nos mesmos dias viram UMA linha do mapa (Crateús: 40 linhas de validação viraram 2).
   A regra mora em nexus/performance/coletas/ (CLAUDE.md de lá). Nenhum emoji; cor só por token. */
(function () {
  "use strict";
  var CFG = JSON.parse(document.getElementById("fr-config").textContent);
  var $ = function (id) { return document.getElementById(id); };
  var DB = null, CONF = {}, SERVIDOR = {}, REV = 0, MONTH = "", MKEYS = [];
  var ORD = { k: "tam", d: -1 };
  var ABERTAS = new Set(), TODOS = new Set(), OCTODAS = new Set(), SEL = {}, BARRA = {}, MAPA = {};
  var fila = Promise.resolve(), enviando = 0;

  var MN = ["", "janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
  var mlabel = function (k) { return MN[+k.split("-")[1]] + " de " + k.split("-")[0]; };
  var MOT = [
    { k: "sem_ipoa", l: "Usina sem sensor de IPOA (esperado)", ap: "ipoa" },
    { k: "sem_ghi", l: "Usina sem sensor de GHI (esperado)", ap: "ghi" },
    { k: "coleta_alt", l: "O dado vem de outra fonte (esperado)", ap: "both" },
    { k: "fora_op", l: "Equipamento inoperante, fora de operação (fica sinalizado)", ap: "inv" },
    { k: "nao_mob", l: "Usina não mobilizada, fora de operação", ap: "both" },
    { k: "os", l: "Parada com OS ou manutenção programada", ap: "both" },
    { k: "zero_real", l: "Zero real (geração confirmada, não é furo)", ap: "inv" },
    { k: "corrigido", l: "Dado já corrigido, não é falha", ap: "both" },
    { k: "outro", l: "Outro (descreva no comentário)", ap: "both" }];
  var MOTL = {}; MOT.forEach(function (m) { MOTL[m.k] = m.l; });
  var UFVN = "Furo de coleta da UFV toda";
  var isGen = function (e) { return e.nome !== "IPOA" && e.nome !== "GHI"; };
  var kindLbl = function (t) { return (t === "IPOA" || t === "GHI") ? "ETM" : "Geração"; };
  var tipoOf = function (n) { return n === UFVN ? "UFV" : n === "IPOA" ? "IPOA" : n === "GHI" ? "GHI" : "Inversor"; };
  var apOf = function (t) { return t === "IPOA" ? "ipoa" : t === "GHI" ? "ghi" : "inv"; };
  var norm = function (s) { return String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]/g, ""); };
  // as usinas que as notas da Thopen de 07/10 dão como sem IPOA/GHI (§8.3 do documento da analista)
  var SEM_IPOA = { ceuazul: 1, guatambu: 1, indaiatuba: 1, ipixuna1: 1, ipixuna2: 1, brodowski: 1, vargemgrande1: 1 };
  var ESTADO = { o: "coletado", v: "vazio", x: "linha do dia ausente", z: "zerado com os outros gerando", p: "usina sem geração no dia",
    a: "valor anômalo (muito acima do padrão: coleta equivocada)", d: "IPOA só no valor estimado (DEF)", w: "pendente de carga", e: "ausência esperada" };
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function pad(n) { return String(n).padStart(2, "0"); }

  // ── as validações (o modelo do confirmacoes_furos.json, §8.4): as funções são as da tela da analista ──────────────────
  var ckey = function (p, n) { return p.src + "|" + p.usina + "|" + n; };
  var vlist = function (v) { return String(v).split(","); };
  function entryRef(p, n) {
    var k = ckey(p, n), km = k + "@" + MONTH;
    if (CONF[km]) return km;
    var c = CONF[k];
    return c && (c.v === "*" || vlist(c.v).indexOf(MONTH) >= 0) ? k : null;
  }
  function getEntry(p, n) { var r = entryRef(p, n); return r ? CONF[r] : null; }
  function reasonDay(c, day) { if (!c) return ""; var m = c.dm && c.dm[MONTH]; return m ? (m[day] || "") : (c.r || ""); }
  function hasReason(c, r) {
    return !!c && (c.dm && c.dm[MONTH] ? Object.keys(c.dm[MONTH]).some(function (d) { return c.dm[MONTH][d] === r; }) : c.r === r);
  }
  function touch(c) { c.t = new Date().toISOString(); }
  function prune(ref) {
    var c = CONF[ref]; if (!c) return;
    if (c.dm && c.dm[MONTH] && !Object.keys(c.dm[MONTH]).length && !c.r) delete c.dm[MONTH];
    if (c.dm && !Object.keys(c.dm).length) delete c.dm;
    if (!c.r && !c.o && !c.dm) delete CONF[ref];
  }
  function explode(k) {
    var c = CONF[k]; if (!c || c.v === "*") return;
    vlist(c.v).forEach(function (m) { var cp = JSON.parse(JSON.stringify(c)); cp.v = m; CONF[k + "@" + m] = cp; });
    delete CONF[k];
  }
  function toGlobal(p, n) {
    var ref = entryRef(p, n); if (!ref) return;
    var k = ckey(p, n), c = CONF[ref];
    if (c.v === "*") return;
    if (ref === k) { c.v = "*"; touch(c); return; }
    delete CONF[ref]; explode(k);
    var cp = JSON.parse(JSON.stringify(c)); cp.v = "*"; CONF[k] = cp;
  }
  function ensure(p, n, glob) {
    var ref = entryRef(p, n);
    if (ref) { if (glob && CONF[ref].v !== "*") toGlobal(p, n); return CONF[entryRef(p, n)]; }
    var k = ckey(p, n);
    if (glob) { explode(k); CONF[k] = { r: "", v: "*", o: "", t: "" }; return CONF[k]; }
    var key = CONF[k] ? k + "@" + MONTH : k;      // a chave "@mês" não sobrescreve a validação de outro mês do mesmo item
    CONF[key] = { r: "", v: MONTH, o: "", t: "" };
    return CONF[key];
  }
  // o item inteiro; "*" amplia para todos os meses; mexer no motivo nunca reduz a vigência que já existe
  function setConf(p, n, r, vig, obs) {
    var ref0 = entryRef(p, n), c;
    if (!r) {
      if (!ref0) return;
      c = CONF[ref0]; c.r = ""; if (c.dm) delete c.dm[MONTH];
      touch(c); prune(ref0); return;
    }
    c = ensure(p, n, vig === "*"); c.r = r;
    if (c.dm) delete c.dm[MONTH];
    if (c.dm && !Object.keys(c.dm).length) delete c.dm;
    if (obs !== undefined) c.o = obs;
    touch(c);
  }
  function setObs(p, n, txt) {
    var ref = entryRef(p, n); if (!ref && !txt) return;
    var c = ref ? CONF[ref] : ensure(p, n, false);
    c.o = txt; touch(c); prune(entryRef(p, n) || ref);
  }
  // só alguns dias: motivo '' retira a validação dos dias marcados
  function setDays(p, n, gapDays, sel, reason) {
    var c = ensure(p, n, false);
    if (!c.dm || !c.dm[MONTH]) { c.dm = c.dm || {}; var b = {}; if (c.r) gapDays.forEach(function (d) { b[d] = c.r; }); c.dm[MONTH] = b; }
    sel.forEach(function (d) { if (reason) c.dm[MONTH][d] = reason; else delete c.dm[MONTH][d]; });
    touch(c); prune(entryRef(p, n));
  }

  // ── o que vai ao servidor: só as chaves que diferem do que ele tem (sem contar o `t` e o `q`, que são dele) ──────
  function canon(e) {
    if (!e) return "";
    var dm = e.dm || {}, ms = Object.keys(dm).sort();
    return JSON.stringify([e.r || "", e.v || "", e.o || "", ms.map(function (m) {
      return [m, Object.keys(dm[m]).sort(function (a, b) { return a - b; }).map(function (d) { return [d, dm[m][d]]; })];
    })]);
  }
  function diferencas(base, atual) {
    var ops = [], ks = {};
    Object.keys(base).forEach(function (k) { ks[k] = 1; });
    Object.keys(atual).forEach(function (k) { ks[k] = 1; });
    Object.keys(ks).forEach(function (k) {
      if (canon(base[k]) === canon(atual[k])) return;
      var v = atual[k] ? { r: atual[k].r || "", v: atual[k].v, o: atual[k].o || "" } : null;
      if (v && atual[k].dm) v.dm = atual[k].dm;
      ops.push({ k: k, v: v, base: (base[k] || {}).t || "" });
    });
    return ops;
  }
  function sincronizar() {
    fila = fila.then(function () {
      var ops = diferencas(SERVIDOR, CONF);
      if (!ops.length) return null;
      var enviado = JSON.parse(JSON.stringify(CONF));
      enviando++;
      return nexusPedir(CFG.conf, { method: "POST", headers: { "Content-Type": "application/json", "Accept": "application/json" },
        body: JSON.stringify({ ops: ops }) }).then(function (r) {
        enviando--;
        var depois = diferencas(enviado, CONF);          // o que a pessoa mexeu enquanto o pedido ia
        SERVIDOR = r.conf; REV = r.conf_rev;
        CONF = JSON.parse(JSON.stringify(r.conf));
        depois.forEach(function (o) { if (o.v) CONF[o.k] = o.v; else delete CONF[o.k]; });
        render();
      }, function (e) {
        enviando--;
        recado(e.message || "Não consegui gravar a validação.", true);
        return nexusPedir(CFG.conf).then(function (r) { SERVIDOR = r.conf; REV = r.conf_rev; CONF = JSON.parse(JSON.stringify(r.conf)); render(); },
          function () { CONF = JSON.parse(JSON.stringify(SERVIDOR)); render(); });
      });
    });
  }
  function mudar(fn) { fn(); sincronizar(); render(); }

  // ── as horas (as ocorrências do COS chegam em ISO sem fuso, a hora de Brasília: o Date lê como hora local) ───────
  var ANO = function () { return +MONTH.split("-")[0]; }, MES = function () { return +MONTH.split("-")[1]; };
  var iniDia = function (d) { return new Date(ANO(), MES() - 1, d).getTime(); };
  function hm(t) { var d = new Date(t); return pad(d.getHours()) + ":" + pad(d.getMinutes()); }
  function dh(t) { var d = new Date(t); return pad(d.getDate()) + "/" + pad(d.getMonth() + 1) + " " + hm(t); }
  function dur(ms) {
    var mi = Math.max(0, Math.round(ms / 6e4)), h = Math.floor(mi / 60), r = mi % 60;
    return h >= 48 ? Math.round(h / 24) + " dias" : h ? h + "h" + (r ? pad(r) : "") : r + " min";
  }
  function tempos(p) {
    if (!p._t) p._t = (p.oc || []).map(function (o) { return [Date.parse(o[0]), Date.parse(o[1])]; });
    return p._t;
  }
  // o pedaço da ocorrência dentro do dia: "08:10 às 15:30", "o dia todo"
  function noDia(p, j, d) {
    var t = tempos(p)[j], a = iniDia(d), b = a + 864e5, s = Math.max(t[0], a), e = Math.min(t[1], b);
    if (s <= a && e >= b) return "o dia todo";
    return (s <= a ? "00:00" : hm(s)) + " às " + (e >= b ? "24:00" : hm(e));
  }
  var ocCurto = function (p, j, d) { return p.oc[j][2] + " " + noDia(p, j, d); };

  // ── a conta de cada usina (calc da tela da analista) ─────────────────────────────────────────────────────────────
  var M = function () { return DB.months[MONTH]; }, P = function () { return M().plants; };
  var fmtD = function (d) { return pad(d) + "/" + MONTH.split("-")[1]; };
  function nat(n) { return n.split(/[^0-9]+/).filter(Boolean).map(Number); }
  function cmpN(a, b) {
    var x = nat(a.nome), y = nat(b.nome);
    for (var i = 0; i < Math.max(x.length, y.length); i++) { var d = (x[i] || 0) - (y[i] || 0); if (d) return d; }
    return 0;
  }
  function ranges(idx, days) {
    var o = [], a = null, b = null;
    idx.forEach(function (i) { var d = days[i]; if (a === null) { a = b = d; } else if (d === b + 1) { b = d; } else { o.push([a, b]); a = b = d; } });
    if (a !== null) o.push([a, b]);
    return o.map(function (r) { return r[0] === r[1] ? pad(r[0]) : pad(r[0]) + " a " + pad(r[1]); }).join(", ");
  }
  var opt = function (nome) { var f = $("fr-filtros"), s = f && f.elements[nome]; return s ? s.value : ""; };
  function varios(nome) {
    var f = $("fr-filtros"), s = f && f.elements[nome];
    return s ? [].filter.call(s.options, function (o) { return o.selected && o.value !== ""; }).map(function (o) { return o.value; }) : [];
  }
  function suggest(p, it) {
    if (it.tipo === "UFV") return null;
    var emp = p.eqs.filter(isGen).every(function (e) { return e.st.split("").every(function (c) { return "vxwe".indexOf(c) >= 0; }); });
    var n = p.eqs[it.i].st.replace(/w/g, "").length, pc = n ? Math.round(100 * it.idx.length / n) : 0;
    if (p.status && p.status !== "OPERAÇÃO") return ["nao_mob", "Status da usina: " + p.status];
    if (it.tipo === "IPOA") {
      if (SEM_IPOA[norm(p.usina)]) return ["sem_ipoa", "Consta nas notas da Thopen (07/10) como usina sem IPOA/GHI"];
      if (n >= 5 && pc >= 90) return ["sem_ipoa", "IPOA ausente em " + pc + "% dos dias: provável usina sem sensor"];
    } else if (it.tipo === "GHI") {
      if (n >= 5 && pc >= 90) return ["sem_ghi", "GHI ausente em " + pc + "% dos dias: provável usina sem sensor"];
    } else if (!emp && n >= 5 && pc >= 90) return ["fora_op", "Sem geração ou coleta em " + pc + "% dos dias: provável equipamento fora de operação"];
    return null;
  }
  function furoDe(e, z) { return e.nome === "IPOA" ? (z ? "vxdza" : "vxda") : (z ? "vxza" : "vxa"); }
  function calc(p) {
    var z = opt("zero") !== "0", useC = opt("validados") !== "0", items = [], cellT = 0, tmp = [];
    p.eqs.forEach(function (e, i) {
      var s = e.st, bs = furoDe(e, z), idx = [], zi = [];
      for (var k = 0; k < s.length; k++) { if (bs.indexOf(s[k]) >= 0) idx.push(k); if (s[k] === "z") zi.push(k); if (s[k] !== "w" && s[k] !== "p") cellT++; }
      tmp.push({ e: e, i: i, idx: idx, zi: zi });
    });
    function fin(t) {
      t.nv = Object.keys(t.vr).length;
      t.pi = t.idx.filter(function (k) { return !(k in t.vr); });
      t.ok = t.idx.length > 0 && t.nv === t.idx.length;
      return t;
    }
    function mkIt(e, i, nome, tipo, idx, zi, w) {
      var ent = getEntry(p, nome), vr = {};
      if (useC) idx.forEach(function (k) { var r = reasonDay(ent, p.days[k]); if (r) vr[k] = r; });
      return fin({ e: e, i: i, nome: nome, tipo: tipo, idx: idx, zi: zi, ent: ent, vr: vr, w: w });
    }
    // os dias em que TODOS os equipamentos de geração estão em furo viram um item só, "UFV toda" (a analista, 11/11/2026)
    var G = tmp.filter(function (x) { return isGen(x.e); }), ufv = null;
    if (G.length >= 2) {
      var D = G[0].idx.filter(function (k) { return G.every(function (x) { return x.idx.indexOf(k) >= 0; }); });
      if (D.length) {
        var Ds = {}; D.forEach(function (k) { Ds[k] = 1; });
        G.forEach(function (x) { x.idx = x.idx.filter(function (k) { return !Ds[k]; }); x.zi = x.zi.filter(function (k) { return !Ds[k]; }); });
        ufv = mkIt({ nome: UFVN, st: G[0].e.st }, -1, UFVN, "UFV", D, [], G.length);
        if (useC) {
          // o dia da UFV toda também vale como validado se TODOS os inversores têm validação nele
          var eg = G.map(function (x) { return getEntry(p, x.e.nome); });
          D.forEach(function (k) {
            if (k in ufv.vr) return;
            var rs = eg.map(function (c) { return reasonDay(c, p.days[k]); });
            if (rs.every(Boolean)) ufv.vr[k] = rs[0];
          });
          fin(ufv);
        }
      }
    }
    if (ufv) items.push(ufv);
    tmp.forEach(function (x) { if (x.idx.length) items.push(mkIt(x.e, x.i, x.e.nome, tipoOf(x.e.nome), x.idx, x.zi)); });
    var pend = items.filter(function (t) { return !t.ok; }), done = items.filter(function (t) { return t.ok; });
    var inop = p.eqs.filter(function (e) { return isGen(e) && /[vxzp]/.test(e.st) && hasReason(getEntry(p, e.nome), "fora_op"); }).map(function (e) { return e.nome; });
    var cp = items.reduce(function (a, t) { return a + t.pi.length * (t.w || 1); }, 0);
    var empty = p.eqs.every(function (e) { return e.st.split("").every(function (c) { return "vxdwe".indexOf(c) >= 0; }); });
    var ex = p.eqs.reduce(function (a, e) { return a + (e.st.split("e").length - 1); }, 0);
    var comp = cellT ? 1 - cp / cellT : 1;
    var sit = pend.length ? "falha" : (items.length ? "conf" : "ok"), sev = "ok";
    if (pend.length) sev = (empty && pend.length === items.length) || comp < 0.5 ? "cr" : "at";
    var ipP = pend.filter(function (t) { return t.tipo === "IPOA"; })[0], ghP = pend.filter(function (t) { return t.tipo === "GHI"; })[0];
    var invP = pend.filter(function (t) { return t.tipo === "Inversor"; }), ks = {};
    pend.forEach(function (t) { ks[kindLbl(t.tipo)] = 1; });
    var kl = Object.keys(ks), kinds = kl.length === 2 ? "Geração + ETM" : (kl.length ? kl[0] : "");
    // o dia da usina, para a tira do mês (Levi, 19/11/2026: "algo mais visual [...] por tamanho do furo"): o pior estado
    // do dia. u = a usina toda sem dado; f = falta a geração de parte dos equipamentos; t = só o IPOA ou o GHI (a estação
    // sem dado com a geração toda lá pesa menos: era o que fazia 17 de 17 dias em quase toda usina); todos pendentes.
    // c = o furo do dia está validado; e = uma parada explicou o dia; n = usina sem geração no dia; o = completo
    var t0 = tempos(p), dia = [], ocd = [], dd = 0, du = 0, dg = 0, cosF = 0, ocF = {};
    p.days.forEach(function (d, k) {
      var s = "o", tem = false, pu = false, pg = false, pe = false;
      items.forEach(function (t) {
        if (t.idx.indexOf(k) < 0) return;
        tem = true;
        if (k in t.vr) return;
        if (t.tipo === "UFV") pu = true; else if (t.tipo === "Inversor") pg = true; else pe = true;
      });
      s = pu ? "u" : pg ? "f" : pe ? "t" : tem ? "c" : p.eqs.some(function (e) { return e.st[k] === "e"; }) ? "e" :
        p.eqs.length && p.eqs.filter(isGen).every(function (e) { return e.st[k] === "p"; }) ? "n" : "o";
      var a = iniDia(d), b = a + 864e5, js = [];
      t0.forEach(function (t, j) { if (t[0] < b && t[1] > a) js.push(j); });
      if (pu || pg || pe) { dd++; if (pu) du++; else if (pg) dg++; if (js.length) { cosF++; js.forEach(function (j) { ocF[j] = 1; }); } }
      dia.push(s); ocd.push(js);
    });
    return { kinds: kinds, cmt: items.filter(function (t) { return t.ent && t.ent.o; }).length, ufv: ufv, items: items, pend: pend, done: done,
      cp: cp, cellT: cellT, comp: comp, empty: empty, sit: sit, sev: sev, ex: ex,
      noos: (p.os || []).filter(function (o) { return o[6] === "A"; }).length, ipF: ipP ? ipP.pi.length : 0, ghF: ghP ? ghP.pi.length : 0,
      invF: invP.length, nInv: p.eqs.filter(isGen).length, pendN: pend.length, confN: done.length, inop: inop, inopN: inop.length,
      dia: dia, ocd: ocd, dd: dd, du: du, dg: dg, dt: dd - du - dg, cosF: cosF, ocF: ocF, ocN: (p.oc || []).length, ocFN: Object.keys(ocF).length };
  }
  // a parada que cobre o dia troca o estado por "e" (ausência esperada); "o" e "a" nunca mudam (§6.4)
  function applyOS() {
    var on = opt("paradas") !== "0";
    Object.keys(DB.months).forEach(function (m) {
      DB.months[m].plants.forEach(function (p) {
        p.eqs.forEach(function (e) {
          if (e.st0 === undefined) e.st0 = e.st;
          if (!e.cv || !on) { e.st = e.st0; return; }
          var a = e.st0.split("");
          Object.keys(e.cv).forEach(function (k) { if ("vxzpd".indexOf(a[k]) >= 0) a[k] = "e"; });
          e.st = a.join("");
        });
      });
    });
  }
  var curto = function (n) { return n.replace(/^Inversor\s*/i, ""); };
  function paradaTxt(p, e, i) {
    var r = e.cv && e.cv[i];
    return r ? r.map(function (j) { var o = p.os[j]; return (o[6] === "A" ? "parada do COS sem OS" : (o[0] === "T" ? "ticket " : "OS ") + o[1]) + " (" + o[2] + ")"; }).join("; ") : "";
  }
  // o que falta, curto, para a lista (os dias de cada um ficam no mapa da usina)
  function oQueFalta(m) {
    var seg = [];
    if (m.empty && m.pendN === m.items.length && m.pendN) seg.push("nenhuma coleta no mês");
    else if (m.ufv && !m.ufv.ok) seg.push("usina toda em " + m.ufv.pi.length + (m.ufv.pi.length === 1 ? " dia" : " dias"));
    if (m.ipF) seg.push("IPOA");
    if (m.ghF) seg.push("GHI");
    if (m.invF) seg.push(m.invF + " de " + m.nInv + (m.nInv === 1 ? " equipamento" : " equipamentos"));
    var an = m.pend.reduce(function (a, t) { return a + t.pi.filter(function (k) { return t.e.st[k] === "a"; }).length; }, 0);
    if (an) seg.push(an + (an === 1 ? " valor anômalo" : " valores anômalos"));
    return seg.join(" · ");
  }

  // ── os filtros (static/filtros-os.js monta a barra, o painel e as etiquetas a partir destas <select>) ──────────────
  var SITS = [["falha", "Furo pendente"], ["conf", "Validado"], ["ok", "Sem falha"], ["cos", "Com ocorrência do COS no dia do furo"],
    ["os", "Com ausência explicada por parada"], ["noos", "Com parada sem OS"], ["ipoa", "IPOA pendente"], ["ghi", "GHI pendente"],
    ["inv", "Equipamento de geração com furo"], ["inop", "Com equipamento inoperante"]];
  function lerFiltros() {
    var f = $("fr-filtros"), o = {};
    if (!f || !f.elements.cliente) return null;
    ["cliente", "carteira", "fonte", "status", "sit"].forEach(function (n) { o[n] = varios(n); });
    ["tipo", "zero", "paradas", "validados"].forEach(function (n) { o[n] = opt(n); });
    o.q = f.elements.q ? f.elements.q.value : "";
    return o;
  }
  function montarFiltros() {
    var antes = lerFiltros() || { cliente: [], carteira: [], fonte: [], status: [], sit: [], tipo: "", zero: "1", paradas: "1", validados: "1", q: "" };
    var ps = P();
    function unicos(fn) { var s = {}; ps.forEach(function (p) { var v = fn(p); if (v !== null) s[v] = 1; }); return Object.keys(s).sort(function (a, b) { return a.localeCompare(b, "pt-BR"); }); }
    function lista(nome, rotulo, ops, marcados) {
      return '<label><span class="gc-rotulo">' + rotulo + '</span><select name="' + nome + '" multiple>' + ops.map(function (o) {
        var v = o.pop ? o[0] : o, t = o.pop ? o[1] : o;
        return '<option value="' + esc(v) + '"' + (marcados.indexOf(v) >= 0 ? " selected" : "") + ">" + esc(t) + "</option>";
      }).join("") + "</select></label>";
    }
    function chave(nome, rotulo, sim, nao, v) {
      return '<label><span class="gc-rotulo">' + rotulo + '</span><select name="' + nome + '" data-padrao="1"><option value="1"' + (v !== "0" ? " selected" : "") + ">" + sim +
        '</option><option value="0"' + (v === "0" ? " selected" : "") + ">" + nao + "</option></select></label>";
    }
    var f = document.createElement("form");
    f.id = "fr-filtros"; f.className = "fr-filtros"; f.setAttribute("data-fo", "local");
    f.addEventListener("submit", function (e) { e.preventDefault(); });
    f.innerHTML =
      '<label class="fr-mes"><span class="gc-rotulo">Mês</span><select name="mes" class="gc-campo" data-fo-fora>' + MKEYS.slice().reverse().map(function (k) {
        return '<option value="' + k + '"' + (k === MONTH ? " selected" : "") + ">" + mlabel(k) + "</option>";
      }).join("") + "</select></label>" +
      '<input type="search" name="q" placeholder="Buscar usina" aria-label="Buscar usina" value="' + esc(antes.q) + '">' +
      lista("sit", "Situação", SITS, antes.sit) +
      '<label><span class="gc-rotulo">Tipo de furo</span><select name="tipo"><option value="">Todos</option>' +
      [["ger", "Geração (com ou sem ETM)"], ["etm", "ETM (com ou sem Geração)"], ["ambos", "Geração e ETM juntos"]].map(function (o) {
        return '<option value="' + o[0] + '"' + (antes.tipo === o[0] ? " selected" : "") + ">" + o[1] + "</option>";
      }).join("") + "</select></label>" +
      lista("cliente", "Cliente", unicos(function (p) { return p.cliente; }), antes.cliente) +
      lista("carteira", "Carteira (Thopen)", unicos(function (p) { return p.cliente === "Thopen" ? p.carteira : null; }), antes.carteira) +
      lista("fonte", "Fonte", [["BD_Performance", "BD_Performance"], ["BD_Thopen", "BD_Thopen"]], antes.fonte) +
      lista("status", "Status da usina", unicos(function (p) { return p.status || "Sem status"; }), antes.status) +
      chave("zero", "Zerado com os outros gerando", "Conta como furo", "Não conta como furo", antes.zero) +
      chave("paradas", "Parada do COS, OS ou ticket", "Explica a ausência", "Não considerar", antes.paradas) +
      chave("validados", "Itens validados", "Contam como resolvidos", "Mostrar como pendentes", antes.validados);
    var caixa = $("fr-filtros").parentNode;
    [].slice.call(caixa.querySelectorAll(".fo-etiquetas")).forEach(function (x) { x.remove(); });
    caixa.replaceChild(f, $("fr-filtros"));
    f.addEventListener("change", function (e) {
      if (e.target.name === "mes") { MONTH = e.target.value; ABERTAS.clear(); TODOS.clear(); OCTODAS.clear(); SEL = {}; montarFiltros(); render(); return; }
      if (e.target.name === "paradas") applyOS();
      render();
    });
    f.addEventListener("input", function (e) { if (e.target.name === "q") render(); });
    if (window.FiltrosOS) window.FiltrosOS.montar(document);
  }
  function porValores(nome, valores) {
    var s = $("fr-filtros").elements[nome];
    [].forEach.call(s.options, function (o) { o.selected = valores.indexOf(o.value) >= 0; });
    s.dispatchEvent(new Event("change", { bubbles: true }));
  }
  function linhas() { return P().map(function (p) { return { p: p, m: calc(p) }; }); }
  function filtrar(todas) {
    var f = lerFiltros(), q = norm(f.q);
    return todas.filter(function (x) {
      var p = x.p, m = x.m;
      if (f.cliente.length && f.cliente.indexOf(p.cliente) < 0) return false;
      if (f.carteira.length && f.carteira.indexOf(p.carteira) < 0) return false;
      if (f.fonte.length && f.fonte.indexOf(p.src) < 0) return false;
      if (f.status.length && f.status.indexOf(p.status || "Sem status") < 0) return false;
      if (q && norm(p.usina).indexOf(q) < 0) return false;
      // o filtro de tipo da analista (16/11/2026): Geração e ETM incluem a usina que tem os dois; "juntos" só ela
      if (f.tipo === "ger" && m.kinds !== "Geração" && m.kinds !== "Geração + ETM") return false;
      if (f.tipo === "etm" && m.kinds !== "ETM" && m.kinds !== "Geração + ETM") return false;
      if (f.tipo === "ambos" && m.kinds !== "Geração + ETM") return false;
      if (f.sit.length && !f.sit.some(function (s) {
        return s === "falha" || s === "conf" || s === "ok" ? m.sit === s : s === "ipoa" ? m.ipF : s === "ghi" ? m.ghF : s === "inop" ? m.inopN :
          s === "os" ? m.ex : s === "noos" ? m.noos : s === "inv" ? m.invF : s === "cos" ? m.cosF : false;
      })) return false;
      return true;
    });
  }

  // ── o desenho ────────────────────────────────────────────────────────────────────────────────────────────────
  var rid = function (p) { return p.src + "|" + p.usina; };
  function numero(r, v, d, tom) { return '<div><div class="r">' + r + '</div><div class="v gc-num' + (tom ? " fr-v--" + tom : "") + '">' + v + '</div><div class="d">' + d + "</div></div>"; }
  function desenharNumeros(rows) {
    var soma = function (k) { return rows.reduce(function (a, r) { return a + r.m[k]; }, 0); };
    var falha = rows.filter(function (r) { return r.m.sit === "falha"; }).length, crit = rows.filter(function (r) { return r.m.sit === "falha" && r.m.sev === "cr"; }).length;
    var cT = soma("cellT"), cP = soma("cp"), dd = soma("dd"), du = soma("du"), dt = soma("dt"), cf = soma("cosF");
    $("fr-numeros").innerHTML =
      numero("Usinas com furo pendente", falha + ' <small>de ' + rows.length + "</small>", crit ? crit + " sem coleta ou com menos da metade do dado" : "nenhuma em falha crítica", falha ? (crit ? "critico" : "alerta") : "ok") +
      numero("Dias com furo", dd, dd ? "somando as usinas: " + du + " com a usina toda sem dado, " + dt + " só de IPOA ou GHI" : "nenhum dia pendente", dd ? "alerta" : "ok") +
      numero("Completude", cT ? ((1 - cP / cT) * 100).toFixed(1).replace(".", ",") + "%" : "—", "das células esperadas até " + fmtD(M().end)) +
      numero("Com ocorrência no COS", cf + (dd ? ' <small>de ' + dd + "</small>" : ""), "dias com furo em que o COS registrou algo na usina");
  }
  function desenharFontes() {
    var f = DB.fontes || {}, s = DB.stats || {}, bd = f.bd || {}, partes = [];
    partes.push("Verificação de 01/" + MONTH.split("-")[1] + " a " + fmtD(M().end) + "/" + MONTH.split("-")[0] + ", " + P().length + " usinas");
    partes.push("banco: " + ["BD_Performance", "BD_Thopen"].map(function (k) { return k + " de " + (bd[k] ? bd[k].slice(0, 5) + " " + bd[k].slice(11) : "sem hora"); }).join(", "));
    if (f.cos && f.cos.ligado) partes.push("COS: " + (s.cos_ocorrencias != null ? s.cos_ocorrencias + " ocorrências nas usinas" : (s.cos_registros || 0) + " paradas com geração parada"));
    partes.push("conta de " + (DB.gen || "").slice(0, 5) + " " + (DB.gen || "").slice(11));
    $("fr-fontes").textContent = partes.join(" · ") + ".";
    var av = [];
    if ((f.bd_atrasado || []).length) av.push("O banco ainda está com a subida de " + f.bd_atrasado.map(function (k) { return (bd[k] || "sem hora") + " (" + k + ")"; }).join(" e ") +
      ". O que entrou no Excel depois disso aparece aqui como furo até a próxima subida da coleta.");
    if (f.cos && !f.cos.ligado) av.push("O COS não respondeu neste servidor" + (f.cos.aviso ? " (" + f.cos.aviso + ")" : "") + ": as paradas de novembro em diante não entraram, e o que elas explicariam aparece como furo.");
    else if (f.cos && f.cos.aviso && !/^bancada/.test(f.cos.aviso)) av.push("COS: " + f.cos.aviso + ".");
    if (MONTH < "2026-11" && !(f.congelado || {})[MONTH]) av.push("As paradas de " + mlabel(MONTH) + " ainda não foram importadas do relatório R01: o que a OS ou o ticket explicava aparece como furo. " +
      "Em Validações, escolha Importar e aponte o Furos_Coleta_Performance_GridCo_R01.html.");
    if (DB.erro_conta) av.push("A última tentativa de refazer a conta falhou (" + DB.erro_conta + "). O que está na tela é a conta de " + (DB.gen || "antes") + ".");
    $("fr-avisos").innerHTML = av.map(function (t) { return '<p class="aviso">' + esc(t) + "</p>"; }).join("");
  }
  // o tamanho do furo por cliente (Levi, 19/11/2026: "mais visual também, por cliente, sabe, por tamanho do furo"): a barra
  // é a soma dos dias com furo das usinas dele, em vermelho a parte em que faltou a usina toda; o clique filtra
  function desenharClientes(todas) {
    var cs = {}, sel = varios("cliente");
    todas.forEach(function (x) {
      var c = cs[x.p.cliente] = cs[x.p.cliente] || { n: 0, f: 0, dd: 0, du: 0, dg: 0, dt: 0 };
      c.n++; c.dd += x.m.dd; c.du += x.m.du; c.dg += x.m.dg; c.dt += x.m.dt; if (x.m.sit === "falha") c.f++;
    });
    var nomes = Object.keys(cs).sort(function (a, b) { return a.localeCompare(b, "pt-BR"); });
    var com = nomes.filter(function (k) { return cs[k].dd; }).sort(function (a, b) { return cs[b].dd - cs[a].dd; }), sem = nomes.filter(function (k) { return !cs[k].dd; });
    var max = com.length ? cs[com[0]].dd : 1;
    $("fr-clientes").innerHTML = com.map(function (k) {
      var c = cs[k], on = sel.length === 1 && sel[0] === k;
      return '<button type="button" class="fr-cli' + (sel.length && !on ? " fr-cli--fora" : "") + '" data-cli="' + esc(k) + '" aria-pressed="' + on + '">' +
        '<span class="fr-cli-nome">' + esc(k) + "</span>" +
        '<span class="fr-cli-barra" title="' + c.du + " dia(s) com a usina toda sem dado, " + c.dg + " com parte da geração faltando, " + c.dt + ' só de IPOA ou GHI">' +
        ["u", "dg", "dt"].map(function (s) { var v = s === "u" ? c.du : c[s]; return '<i class="fr-cli-' + s + '" style="width:' + (100 * v / max).toFixed(2) + '%"></i>'; }).join("") + "</span>" +
        '<span class="fr-cli-num"><b class="gc-num">' + c.dd + "</b> " + (c.dd === 1 ? "dia" : "dias") + ' <span class="mudo">· ' + c.f + " de " + c.n + (c.n === 1 ? " usina" : " usinas") + "</span></span></button>";
    }).join("") + (sem.length ? '<p class="fr-cli-sem mudo">Sem furo pendente: ' + sem.map(function (k) {
      return '<button type="button" class="fr-cli-link" data-cli="' + esc(k) + '">' + esc(k) + "</button>";
    }).join(", ") + "</p>" : "") + (com.length ? "" : '<p class="mudo">Nenhum cliente com furo pendente neste mês.</p>');
  }
  var DIA_T = { u: "a usina toda sem dado", f: "falta a geração de parte dos equipamentos", t: "falta só o IPOA ou o GHI", c: "furo validado", e: "explicado por parada", n: "usina sem geração no dia", o: "completo" };
  function tira(p, m) {
    return '<span class="fr-tira">' + m.dia.map(function (s, k) {
      var js = m.ocd[k], d = p.days[k];
      return '<i class="fr-q fr-q--' + s + (js.length ? " fr-q--cos" : "") + '" title="' + fmtD(d) + ": " + DIA_T[s] +
        (js.length ? " · COS: " + esc(js.map(function (j) { return ocCurto(p, j, d); }).join("; ")) : "") + '"></i>';
    }).join("") + "</span>";
  }
  var COLS = [["usina", "Usina"], ["dia", "O mês, dia a dia"], ["tam", "Furo pendente", 1], ["oc", "COS no mês", 1]];
  function ordenar(rows) {
    var o = ORD;
    var val = function (x) {
      var m = x.m;
      // o tamanho: os dias com furo; no empate, o da usina toda e o de geração vêm antes do só de IPOA ou GHI
      return o.k === "usina" ? x.p.usina : o.k === "oc" ? m.ocFN * 1e4 + m.ocN : m.dd * 1e6 + m.du * 1e4 + m.dg * 1e2 + (m.sit === "conf" ? 1 : 0) + m.cp / 1e7;
    };
    rows.sort(function (a, b) {
      var x = val(a), y = val(b);
      return (typeof x === "string" ? x.localeCompare(y, "pt-BR") : (x > y ? 1 : x < y ? -1 : 0)) * o.d || a.p.usina.localeCompare(b.p.usina, "pt-BR");
    });
  }
  function celula(k, p, m) {
    switch (k) {
      case "usina": return '<td class="fr-usina"><i class="ph ph-caret-right fr-seta" aria-hidden="true"></i><span><b>' + esc(p.usina) + '</b><small class="mudo">' + esc(p.cliente) + (p.carteira && p.carteira !== "—" && p.carteira !== p.cliente ? " · " + esc(p.carteira) : "") + "</small></span></td>";
      case "dia": return '<td class="fr-td-tira">' + tira(p, m) + "</td>";
      case "tam":
        if (m.dd) return '<td class="n fr-tam"><b class="gc-num fr-tam-n fr-tam-n--' + m.sev + '">' + m.dd + '</b> <span class="mudo">' + (m.dd === 1 ? "dia" : "dias") + '</span><small>' + esc(oQueFalta(m)) + "</small></td>";
        return '<td class="n fr-tam">' + (m.sit === "conf" ? '<span class="fr-okt">validado</span>' : '<span class="mudo">completo</span>') + (m.ex ? '<small>' + m.ex + " célula(s) explicada(s) por parada</small>" : "") + "</td>";
      case "oc":
        if (!m.ocN) return '<td class="n"><span class="mudo">nenhuma</span></td>';
        return '<td class="n"><b class="gc-num">' + m.ocN + '</b>' + (m.ocFN ? '<small class="fr-oc-furo">' + m.ocFN + (m.ocFN === 1 ? " no dia do furo" : " nos dias do furo") + "</small>" : "") + "</td>";
    }
    return "<td></td>";
  }
  function desenharTabela(rows) {
    var tb = $("fr-tabela");
    tb.tHead.innerHTML = "<tr>" + COLS.map(function (c) {
      if (c[0] === "dia") return '<th scope="col" class="fr-th-tira"><span>' + c[1] + ' <span class="fr-th-nota">' + fmtD(1) + " a " + fmtD(M().end) + "</span></span></th>";
      return '<th scope="col" class="' + (c[2] ? "n" : "") + '" data-k="' + c[0] + '"' + (ORD.k === c[0] ? ' aria-sort="' + (ORD.d > 0 ? "ascending" : "descending") + '"' : "") + '><button type="button">' + c[1] +
        (ORD.k === c[0] ? '<i class="ph ph-caret-' + (ORD.d > 0 ? "up" : "down") + '" aria-hidden="true"></i>' : "") + "</button></th>";
    }).join("") + "</tr>";
    ordenar(rows);
    var h = "";
    rows.forEach(function (x) {
      var p = x.p, m = x.m, id = rid(p), ab = ABERTAS.has(id);
      h += '<tr class="fr-linha fr-linha--' + (m.sit === "falha" ? m.sev : m.sit) + (ab ? " fr-aberta" : "") + '" data-id="' + esc(id) + '" tabindex="0" aria-expanded="' + (ab ? "true" : "false") + '">' +
        COLS.map(function (c) { return celula(c[0], p, m); }).join("") + "</tr>";
      if (ab) h += '<tr class="fr-detalhe"><td colspan="' + COLS.length + '">' + painel(p, m) + "</td></tr>";
    });
    tb.tBodies[0].innerHTML = h || '<tr><td colspan="' + COLS.length + '" class="fr-vazio">Nenhuma usina com estes filtros.</td></tr>';
    // a barra de validação lembra o motivo, a vigência e o comentário escolhidos antes de marcar os dias
    [].forEach.call(tb.querySelectorAll(".fr-acao[data-id]"), function (bx) {
      var b = BARRA[bx.getAttribute("data-id")];
      if (!b) return;
      ["amot", "avig", "aobs"].forEach(function (a) { var el = bx.querySelector("[data-a=" + a + "]"); if (el && b[a] != null && !el.disabled) el.value = b[a]; });
    });
  }

  // ── o detalhe da usina: o que o COS registrou, e o mapa do mês com a validação ─────────────────────────────────
  function ocorrencias(p, m, id) {
    var oc = p.oc || [], cong = (p.os || []).filter(function (o) { return o[0] !== "C"; }), t = tempos(p);
    var todas = OCTODAS.has(id), mostrar = oc.map(function (_o, j) { return j; }).filter(function (j) { return todas || m.ocF[j] || oc[j][7]; });
    var h = '<section class="fr-oc"><div class="fr-oc-topo"><h3 class="fr-h3">O que o COS registrou</h3><span class="mudo">' +
      (oc.length ? oc.length + (oc.length === 1 ? " ocorrência" : " ocorrências") + " em " + MN[MES()] + "; " + m.ocFN + " nos dias com furo" : "nenhuma ocorrência em " + MN[MES()]) + "</span>" +
      (oc.length && mostrar.length < oc.length ? '<button type="button" class="gc-btn gc-btn--fantasma fr-mini" data-a="octodas" data-id="' + esc(id) + '">Ver as ' + oc.length + "</button>" : "") +
      (todas && oc.length > m.ocFN ? '<button type="button" class="gc-btn gc-btn--fantasma fr-mini" data-a="octodas" data-id="' + esc(id) + '">Só as dos dias com furo</button>' : "") + "</div>";
    if (oc.length && !mostrar.length) h += '<p class="mudo fr-oc-nada">Nenhuma ocorrência do COS nos dias com furo: o furo não tem explicação registrada.</p>';
    if (mostrar.length || cong.length) {
      h += '<div class="fr-rola"><table class="fr-sub fr-oc-tab"><thead><tr><th>Quando</th><th>Ocorrência</th><th>OS</th><th>Geração</th><th></th></tr></thead><tbody>' +
        mostrar.map(function (j) {
          var o = oc[j];
          return '<tr class="' + (m.ocF[j] ? "fr-oc-nofuro" : "") + '"><td class="gc-num fr-oc-quando">' + dh(t[j][0]) + " → " + (o[6] ? '<b class="fr-pend">em aberto</b>' : dh(t[j][1])) +
            ' <span class="mudo">(' + dur(t[j][1] - t[j][0]) + ")</span></td><td><b>" + esc(o[2]) + "</b>" + (o[3] ? ' <span class="mudo">' + esc(o[3]) + "</span>" : "") + "</td>" +
            '<td class="gc-num">' + (o[4] ? esc(o[4]) : '<span class="fr-selo fr-selo--alerta">sem OS</span>') + "</td>" +
            "<td>" + (o[5] === "s" ? "parou" : o[5] === "n" ? "seguiu" : '<span class="mudo">não informado</span>') + "</td>" +
            "<td>" + (o[7] ? '<span class="fr-tag fr-tag--e" title="Parada de 6 h ou mais entre 6h e 18h, com geração parada: pela regra do R01 o dia não é furo">explica o dia</span>' :
              m.ocF[j] ? '<span class="fr-tag fr-tag--f">no dia do furo</span>' : "") + "</td></tr>";
        }).join("") +
        cong.map(function (o) {
          return "<tr><td class=\"gc-num fr-oc-quando\">" + esc(o[4]) + " → " + esc(o[5]) + "</td><td><b>" + esc(o[3]) + '</b> <span class="mudo">' + esc(o[2]) + "</span></td><td class=\"gc-num\">" +
            ({ T: "ticket ", F: "OS ", "F+T": "OS " }[o[0]] || "") + esc(o[1]) + '</td><td><span class="mudo">' + ({ T: "ticket", F: "Fracttal", "F+T": "Fracttal e ticket" }[o[0]] || esc(o[0])) +
            '</span></td><td><span class="fr-tag fr-tag--e">explica o dia</span></td></tr>';
        }).join("") + "</tbody></table></div>";
    }
    return h + "</section>";
  }
  // as linhas do mapa: a do COS, a da usina toda, o IPOA e o GHI, e os equipamentos de geração; os que têm o MESMO furo
  // nos mesmos dias (mesmas cores, mesma validação, mesma marcação) viram uma linha só
  function linhasDoMapa(p, m, id) {
    var sa = TODOS.has(id), z = opt("zero") !== "0", byN = {}, Dset = {}, ls = [];
    m.items.forEach(function (t) { byN[t.nome] = t; });
    (m.ufv ? m.ufv.idx : []).forEach(function (k) { Dset[k] = 1; });
    function cores(e, t) {
      var bs = furoDe(e, z);
      return e.st.split("").map(function (c, i) {
        var u = (m.ufv && Dset[i] && isGen(e)) ? m.ufv : null, rr = u ? u.vr[i] : ((t && bs.indexOf(c) >= 0) ? t.vr[i] : "");
        return rr ? (rr === "fora_op" ? "i" : "c") : c;
      });
    }
    if (m.ufv) ls.push({ nome: "Usina toda sem dado", itens: [m.ufv], cel: p.days.map(function (_d, i) { return Dset[i] ? (m.ufv.vr[i] ? (m.ufv.vr[i] === "fora_op" ? "i" : "c") : "v") : "n"; }) });
    p.eqs.forEach(function (e) {
      var t = byN[e.nome];
      if (!sa && !t && e.st.indexOf("e") < 0) return;
      var cel = cores(e, t), selT = t ? Object.keys(SEL[id + "|" + t.nome] || {}).sort().join(",") : "";
      var assin = isGen(e) ? cel.join("") + "|" + (t ? t.idx.join(",") + "|" + JSON.stringify(t.vr) + "|" + selT + "|" + (t.ent && t.ent.o ? t.ent.o : "") : "-") : null;
      var ult = ls[ls.length - 1];
      if (assin && ult && ult.assin === assin) { ult.eqs.push(e); if (t) ult.itens.push(t); return; }
      ls.push({ nome: e.nome, eqs: [e], itens: t ? [t] : [], cel: cel, assin: assin });
    });
    return ls;
  }
  function rotulo(l) {
    if (!l.eqs || l.eqs.length === 1) return esc(l.nome);
    var ns = l.eqs.map(function (e) { return curto(e.nome); });
    return l.eqs.length <= 3 ? "Inversores " + esc(ns.join(", ")) : esc(l.eqs.length + " inversores") + ' <span class="mudo">(' + esc(ns[0]) + " a " + esc(ns[ns.length - 1]) + ")</span>";
  }
  function estadoDe(p, l) {
    var t = l.itens[0];
    if (!t) return '<span class="mudo">sem furo</span>';
    var s = suggest(p, t), ms = {};
    Object.keys(t.vr).forEach(function (k) { ms[MOTL[t.vr[k]] || t.vr[k]] = 1; });
    if (t.ok) return '<span class="fr-okt" title="' + esc(Object.keys(ms).join(" / ")) + '">validado</span>';
    if (t.nv) return '<span class="fr-parc">' + t.nv + " de " + t.idx.length + " dias validados</span>";
    return '<span class="fr-pend">pendente</span>' + (s ? ' <span class="fr-sug" title="' + esc(s[1]) + '">sugestão: ' + esc(MOTL[s[0]].replace(/ \(.*\)$/, "")) + "</span>" : "");
  }
  function mapa(p, m, id) {
    var ls = linhasDoMapa(p, m, id), days = p.days, dsel = {}, isel = 0;
    MAPA[id] = ls.map(function (l) { return l.itens.map(function (t) { return t.nome; }); });
    m.items.forEach(function (t) { var ks = Object.keys(SEL[id + "|" + t.nome] || {}); if (ks.length) { isel++; ks.forEach(function (d) { dsel[d] = 1; }); } });
    var nsel = Object.keys(dsel).length;
    var sugN = m.pend.filter(function (t) { return suggest(p, t); }).length;
    var h = '<section class="fr-mapa"><div class="fr-mapa-topo"><h3 class="fr-h3">Mapa do mês</h3><div class="fr-chave">' +
      [["v", "Sem dado"], ["z", "Zerado"], ["d", "IPOA só estimado"], ["a", "Valor anômalo"], ["e", "Explicado por parada"], ["c", "Validado"], ["i", "Inoperante"], ["o", "Coletado"]]
        .map(function (x) { return '<span><i class="fr-c fr-c-' + x[0] + '"></i>' + x[1] + "</span>"; }).join("") +
      '<span><i class="fr-c fr-c-cos"></i>Ocorrência no COS</span></div>' +
      (sugN ? '<button type="button" class="gc-btn gc-btn--contorno fr-mini" data-a="sug" data-id="' + esc(id) + '" title="Aplica a sugestão do Nexus a cada item pendente que tem uma">Aceitar as sugestões (' + sugN + ")</button>" : "") +
      '<button type="button" class="gc-btn gc-btn--fantasma fr-mini" data-a="all" data-id="' + esc(id) + '">' + (TODOS.has(id) ? "Só os equipamentos com furo" : "Todos os equipamentos (" + p.eqs.length + ")") + "</button></div>";
    if (!ls.length && !(p.oc || []).length) return h + '<p class="mudo">Nenhum equipamento com furo ou parada neste mês.</p></section>';
    h += '<div class="fr-rola"><table class="fr-heat"><thead><tr><th></th>' + days.map(function (d) { return '<th class="gc-num">' + d + "</th>"; }).join("") + "</tr></thead><tbody>";
    if ((p.oc || []).length) {
      h += '<tr class="fr-heat-cos"><th>COS</th>' + days.map(function (d, i) {
        var js = m.ocd[i];
        return '<td class="fr-c ' + (js.length ? (js.some(function (j) { return p.oc[j][7]; }) ? "fr-c-cose" : "fr-c-cos") : "fr-c-nada") + '"' +
          (js.length ? ' title="' + fmtD(d) + " · " + esc(js.map(function (j) { var o = p.oc[j]; return o[2] + " " + noDia(p, j, d) + (o[4] ? " (OS " + o[4] + ")" : "") + (o[5] === "s" ? ", geração parou" : o[5] === "n" ? ", geração seguiu" : ""); }).join("; ")) + '"' : "") + "></td>";
      }).join("") + "</tr>";
    }
    ls.forEach(function (l, r) {
      var furo = {}, sel = {}, todos = l.itens.length && l.itens.every(function (t) { return !t.pi.length || t.pi.every(function (k) { return (SEL[id + "|" + t.nome] || {})[p.days[k]]; }); });
      l.itens.forEach(function (t) { t.idx.forEach(function (k) { furo[k] = 1; }); Object.keys(SEL[id + "|" + t.nome] || {}).forEach(function (d) { sel[d] = 1; }); });
      var t0 = l.itens[0], cmt = l.itens.filter(function (t) { return t.ent && t.ent.o; })[0];
      var nomes = l.eqs && l.eqs.length > 1 ? l.eqs.map(function (e) { return e.nome; }).join(", ") : "";
      h += '<tr><th class="fr-rot' + (l.itens.length ? " fr-rot--clic" : "") + '"' + (l.itens.length ? ' data-a="linha" data-id="' + esc(id) + '" data-r="' + r + '" aria-pressed="' + (todos && l.itens.some(function (t) { return t.pi.length; }) ? "true" : "false") + '"' : "") +
        ' title="' + esc((nomes ? nomes + ". " : "") + (l.itens.length ? "Clique para marcar os dias pendentes" : "") + (cmt ? ". Comentário: " + cmt.ent.o : "") + (t0 && t0.ent && t0.nv && quando(t0.ent) ? ". Validado por " + quando(t0.ent) : "")) + '">' +
        '<span class="fr-rot-nome">' + rotulo(l) + "</span>" + (cmt ? '<i class="ph ph-chat-text fr-rot-cmt" aria-label="tem comentário"></i>' : "") + ' <span class="fr-rot-est">' + estadoDe(p, l) + "</span></th>" +
        l.cel.map(function (c, i) {
          var d = days[i], clic = !!furo[i] && l.itens.length;
          return '<td class="fr-c fr-c-' + c + (clic ? " fr-clic" : "") + (sel[d] ? " fr-on" : "") + '"' + (clic ? ' data-a="cel" data-id="' + esc(id) + '" data-r="' + r + '" data-day="' + d + '"' : "") +
            ' title="' + esc(l.nome) + " · " + fmtD(d) + " · " + (c === "e" && l.eqs ? "ausência esperada: " + esc(paradaTxt(p, l.eqs[0], i)) : c === "c" ? "validado" : c === "i" ? "inoperante" : (ESTADO[c] || "")) +
            (m.ocd[i].length ? " · COS: " + esc(m.ocd[i].map(function (j) { return ocCurto(p, j, d); }).join("; ")) : "") + (clic ? (sel[d] ? " · marcado" : " · clique para marcar") : "") + '"></td>';
        }).join("") + "</tr>";
    });
    h += "</tbody></table></div>";
    // a barra única de validação: no lugar de uma linha por item com cinco campos (o desenho até 18/11/2026)
    var um = isel === 1 ? m.items.filter(function (t) { return Object.keys(SEL[id + "|" + t.nome] || {}).length; })[0] : null;
    var att = 'data-id="' + esc(id) + '"', des = nsel ? "" : " disabled";
    h += '<div class="fr-acao" ' + att + '><span class="fr-acao-n">' + (nsel ? "<b>" + nsel + "</b> " + (nsel === 1 ? "dia marcado" : "dias marcados") + (isel > 1 ? " em " + isel + " itens" : um ? " em " + esc(um.tipo === "UFV" ? "usina toda" : um.nome) : "") :
      '<span class="mudo">Clique nos dias com furo do mapa, ou no nome da linha, para marcar.</span>') + "</span>" +
      '<select class="gc-campo fr-sel" data-a="amot" ' + att + des + ' aria-label="Motivo"><option value="">Motivo</option>' + MOT.map(function (x) { return '<option value="' + x.k + '">' + x.l + "</option>"; }).join("") + "</select>" +
      '<select class="gc-campo fr-sel fr-sel--curto" data-a="avig" ' + att + des + ' aria-label="Vale para"><option value="m">só este mês</option><option value="*">todos os meses</option></select>' +
      '<input type="text" class="gc-campo fr-obs" data-a="aobs" ' + att + des + ' maxlength="2000" placeholder="Comentário (opcional)" aria-label="Comentário" value="' + esc(um && um.ent && um.ent.o ? um.ent.o : "") + '">' +
      '<button type="button" class="gc-btn gc-btn--primario fr-mini" data-a="aval" ' + att + des + ">Validar</button>" +
      '<button type="button" class="gc-btn gc-btn--contorno fr-mini" data-a="atirar" ' + att + des + ">Tirar a validação</button>" +
      '<button type="button" class="gc-btn gc-btn--fantasma fr-mini" data-a="apend" ' + att + (m.pend.length ? "" : " disabled") + ">Marcar todos os pendentes</button>" +
      (nsel ? '<button type="button" class="gc-btn gc-btn--fantasma fr-mini" data-a="anada" ' + att + ">Desmarcar</button>" : "") + "</div>";
    return h + "</section>";
  }
  function quando(ent) {
    if (!ent || !ent.t) return "";
    var d = new Date(ent.t);
    if (isNaN(d)) return "";
    return (ent.q ? ent.q + " em " : "") + pad(d.getDate()) + "/" + pad(d.getMonth() + 1) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }
  function painel(p, m) {
    return '<div class="fr-painel"><div class="fr-painel-topo"><b>' + esc(p.usina) + '</b> <span class="mudo">' + esc(p.cliente) + (p.carteira && p.carteira !== "—" && p.carteira !== p.cliente ? " · " + esc(p.carteira) : "") + " · " + esc(p.src) +
      (p.supervisor ? " · supervisor " + esc(p.supervisor) : "") + (p.status ? " · " + esc(p.status) : "") + "</span></div>" +
      ocorrencias(p, m, rid(p)) + mapa(p, m, rid(p)) + "</div>";
  }
  function render() {
    if (!DB || !MONTH) return;
    var todas = linhas(), rows = filtrar(todas);
    desenharNumeros(rows);
    desenharFontes();
    desenharClientes(todas);
    $("fr-titulo-lista").textContent = "Usinas (" + rows.length + (rows.length !== todas.length ? " de " + todas.length : "") + ")";
    desenharTabela(rows);
    var n = Object.keys(CONF).length;
    $("fr-conf-n").textContent = n + " validação(ões) guardada(s) no Nexus" + (enviando ? " · gravando…" : "");
  }
  var recadoT = null;
  function recado(texto, erro) {
    var r = $("fr-recado");
    r.textContent = texto; r.hidden = false;
    r.className = "fr-recado" + (erro ? " fr-recado--erro" : "");
    clearTimeout(recadoT);
    recadoT = setTimeout(function () { r.hidden = true; }, erro ? 9000 : 5000);
  }

  // ── os cliques ───────────────────────────────────────────────────────────────────────────────────────────────
  var porId = function (id) { return P().filter(function (p) { return rid(p) === id; })[0]; };
  // validar o que está marcado: o item com TODOS os dias de furo marcados recebe o motivo do item inteiro (e a vigência
  // escolhida); o marcado em parte, só os dias (neste mês), como o "Só alguns dias" da tela da analista
  function validarMarcados(p, m, id, mot, vig, obs, tirar) {
    var feitos = 0, recusados = 0, mo = MOT.filter(function (x) { return x.k === mot; })[0];
    mudar(function () {
      m.items.forEach(function (t) {
        var s = SEL[id + "|" + t.nome] || {}, dias = Object.keys(s).map(Number);
        if (!dias.length) return;
        if (!tirar && mot && mo.ap !== "both" && mo.ap !== apOf(t.tipo)) { recusados++; return; }
        var gap = t.idx.map(function (k) { return p.days[k]; }), todos = gap.every(function (d) { return s[d]; });
        if (tirar) { if (todos) setConf(p, t.nome, ""); else setDays(p, t.nome, gap, dias, ""); }
        else if (mot) { if (todos) setConf(p, t.nome, mot, vig); else setDays(p, t.nome, gap, dias, mot); }
        if (!tirar && obs !== null && obs !== ((t.ent && t.ent.o) || "")) setObs(p, t.nome, obs);
        feitos++;
        delete SEL[id + "|" + t.nome];
      });
    });
    delete BARRA[id];
    if (recusados) recado(recusados + (recusados === 1 ? " item não aceita" : " itens não aceitam") + " esse motivo e " + (recusados === 1 ? "ficou marcado" : "ficaram marcados") + ": " + MOTL[mot] + ".", true);
    else if (!tirar && !mot) recado("Comentário gravado em " + feitos + (feitos === 1 ? " item" : " itens") + ". A situação não muda.");
  }
  function aoClicar(e) {
    var th = e.target.closest("th[data-k]");
    if (th) {
      var k = th.getAttribute("data-k");
      if (ORD.k === k) ORD.d *= -1; else { ORD.k = k; ORD.d = k === "usina" ? 1 : -1; }
      render(); return;
    }
    var b = e.target.closest("[data-a]");
    if (b && b.tagName !== "SELECT" && b.tagName !== "INPUT") {
      var id = b.getAttribute("data-id"), p = porId(id), a = b.getAttribute("data-a");
      if (!p || b.disabled) return;
      var m = calc(p), linha = (MAPA[id] || [])[+b.getAttribute("data-r")] || [];
      var itensDa = function (ns) { return m.items.filter(function (t) { return ns.indexOf(t.nome) >= 0; }); };
      if (a === "cel") {
        var d = +b.getAttribute("data-day"), its = itensDa(linha).filter(function (t) { return t.idx.some(function (k) { return p.days[k] === d; }); });
        var liga = !its.every(function (t) { return (SEL[id + "|" + t.nome] || {})[d]; });
        its.forEach(function (t) { var s = SEL[id + "|" + t.nome] = SEL[id + "|" + t.nome] || {}; if (liga) s[d] = 1; else delete s[d]; });
        render();
      } else if (a === "linha") {
        var it = itensDa(linha), on = b.getAttribute("aria-pressed") === "true";
        it.forEach(function (t) { var s = {}; if (!on) (t.pi.length ? t.pi : t.idx).forEach(function (k) { s[p.days[k]] = 1; }); SEL[id + "|" + t.nome] = s; });
        render();
      } else if (a === "apend") {
        m.items.forEach(function (t) { var s = {}; t.pi.forEach(function (k) { s[p.days[k]] = 1; }); SEL[id + "|" + t.nome] = s; });
        render();
      } else if (a === "anada") {
        m.items.forEach(function (t) { delete SEL[id + "|" + t.nome]; });
        render();
      } else if (a === "aval" || a === "atirar") {
        var bx = b.closest(".fr-acao"), mot = bx.querySelector("[data-a=amot]").value, obsEl = bx.querySelector("[data-a=aobs]");
        var obs = obsEl.value.trim();
        if (a === "aval" && !mot && !obs) { bx.querySelector("[data-a=amot]").focus(); recado("Escolha o motivo dos dias marcados.", true); return; }
        validarMarcados(p, m, id, mot, bx.querySelector("[data-a=avig]").value, obs === "" && !obsEl.defaultValue ? null : obs, a === "atirar");
      } else if (a === "all") { if (TODOS.has(id)) TODOS.delete(id); else TODOS.add(id); render(); }
      else if (a === "octodas") { if (OCTODAS.has(id)) OCTODAS.delete(id); else OCTODAS.add(id); render(); }
      else if (a === "sug") {
        var feitas = 0;
        mudar(function () {
          m.pend.forEach(function (t) {
            var s = suggest(p, t); if (!s) return;
            feitas++;
            // no item parcial, só os dias pendentes; a sugestão não cobre o comentário que já existe (a analista, 16/11/2026)
            if (t.nv) setDays(p, t.nome, t.idx.map(function (k) { return p.days[k]; }), t.pi.map(function (k) { return p.days[k]; }), s[0]);
            else setConf(p, t.nome, s[0], (s[0] === "sem_ipoa" || s[0] === "sem_ghi") ? "*" : "m", t.ent && t.ent.o ? undefined : s[1]);
          });
        });
        recado(feitas ? feitas + " sugestão(ões) aplicada(s)." : "Nenhum item pendente desta usina tem sugestão.");
      }
      return;
    }
    if (e.target.closest("select,input,button,.fr-detalhe")) return;
    var tr = e.target.closest("tr.fr-linha");
    if (tr) { var rid_ = tr.getAttribute("data-id"); if (ABERTAS.has(rid_)) ABERTAS.delete(rid_); else ABERTAS.add(rid_); render(); }
  }
  function aoMudar(e) {
    var t = e.target, a = t.getAttribute("data-a"), id = t.getAttribute("data-id");
    if (!id || ["amot", "avig", "aobs"].indexOf(a) < 0) return;
    (BARRA[id] = BARRA[id] || {})[a] = t.value;
  }

  // ── exportar e importar ──────────────────────────────────────────────────────────────────────────────────────
  function baixar(nome, texto, tipo) {
    var a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([texto], { type: tipo })); a.download = nome;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
  }
  function csv() {
    var L = [["Mês", "Cliente", "Carteira", "Usina", "Fonte", "Status usina", "Item", "Tipo", "Natureza", "Dias com furo", "Datas com furo", "Dias validados", "Datas validadas",
      "Dias pendentes", "Datas pendentes", "Situação", "Motivo(s) da validação", "Vigência", "Comentário", "Validado por", "Validado em"]];
    filtrar(linhas()).forEach(function (x) {
      var p = x.p;
      x.m.items.forEach(function (t) {
        var c = t.ent, vd = t.idx.filter(function (k) { return k in t.vr; }), ms = {};
        Object.keys(t.vr).forEach(function (k) { ms[MOTL[t.vr[k]] || t.vr[k]] = 1; });
        L.push([MONTH, p.cliente, p.carteira, p.usina, p.src, p.status || "", t.nome, t.tipo, kindLbl(t.tipo), t.idx.length, ranges(t.idx, p.days), vd.length, ranges(vd, p.days),
          t.pi.length, ranges(t.pi, p.days), t.ok ? "Validado" : (t.nv ? "Validação parcial" : "Pendente"), Object.keys(ms).join(" / "),
          t.nv && c ? (c.v === "*" ? "todos os meses" : (String(c.v).indexOf(",") >= 0 ? "meses " + c.v : "só " + c.v)) : "", c ? (c.o || "") : "", c && t.nv ? (c.q || "") : "", c && t.nv ? (c.t || "") : ""]);
      });
    });
    baixar("furos_coleta_" + MONTH + ".csv", "﻿" + L.map(function (r) { return r.map(function (v) { return '"' + String(v).replace(/"/g, '""') + '"'; }).join(";"); }).join("\r\n"), "text/csv;charset=utf-8");
  }
  function importar(arquivo) {
    var fd = new FormData();
    fd.append("arquivo", arquivo, arquivo.name);
    recado("Importando " + arquivo.name + "…");
    nexusPedir(CFG.importar, { method: "POST", body: fd }).then(function (r) {
      var v = r.resumo.validacoes || {}, pr = r.resumo.paradas;
      SERVIDOR = r.conf; REV = r.conf_rev; CONF = JSON.parse(JSON.stringify(r.conf));
      recado("Importado: " + (v.novas || 0) + " nova(s), " + (v.atualizadas || 0) + " atualizada(s), " + ((v.iguais || 0) + (v.mais_novas_no_nexus || 0)) + " que o Nexus já tinha igual ou mais nova; total " + (v.total || 0) + "." +
        (pr && pr.congelados && pr.congelados.length ? " Paradas guardadas de " + pr.congelados.join(", ") + ": a conta está sendo refeita." : ""));
      render();
      if (pr && pr.congelados && pr.congelados.length) setTimeout(carregar, 2500);
    }, function (e) { recado(e.message || "Não consegui importar.", true); });
  }

  // ── a carga ──────────────────────────────────────────────────────────────────────────────────────────────────
  function mexendo() { var a = document.activeElement; return !!(a && a.closest && a.closest("#fr-tabela") && /^(INPUT|SELECT)$/.test(a.tagName)); }
  function aplicar(d) {
    var novo = !DB || DB.gen !== d.gen;
    if (novo) {
      Object.keys(d.months).forEach(function (k) {
        d.months[k].plants.forEach(function (p) { p.eqs = p.eqs.filter(function (e) { return !isGen(e); }).concat(p.eqs.filter(isGen).sort(cmpN)); });
      });
    }
    var meses = Object.keys(d.months).sort(), mudouMeses = meses.join() !== MKEYS.join();
    if (novo) { DB = d; MKEYS = meses; } else { DB.fontes = d.fontes; DB.erro_conta = d.erro_conta; }
    if (!MONTH || MKEYS.indexOf(MONTH) < 0) MONTH = MKEYS[MKEYS.length - 1];
    if (!enviando && !diferencas(SERVIDOR, CONF).length) { SERVIDOR = d.conf; REV = d.conf_rev; CONF = JSON.parse(JSON.stringify(d.conf)); }
    $("fr-carregando").hidden = true; $("fr-corpo").hidden = false;
    if (novo && (mudouMeses || !$("fr-filtros").elements.cliente)) montarFiltros();
    if (novo) applyOS();
    render();
  }
  function carregar() {
    nexusPedir(CFG.dados).then(function (d) {
      if (d && d.pronto && d.months && Object.keys(d.months).length) {
        if (mexendo()) { setTimeout(carregar, 5000); return; }
        d.erro_conta = d.erro_conta || "";
        aplicar(d);
      } else {
        $("fr-carregando").textContent = d && d.erro_conta ? "Não consegui calcular os furos: " + d.erro_conta + ". Tentando de novo em instantes." :
          "Calculando os furos a partir do banco e do COS. Na primeira vez leva cerca de um minuto.";
      }
      if (!d || !d.pronto || d.calculando) setTimeout(carregar, 4000);
    }, function (e) {
      $("fr-carregando").textContent = e.message || "Não consegui ler os furos.";
      setTimeout(carregar, 15000);
    });
  }
  // o que os outros validaram chega sem recarregar: a cada minuto, só se a revisão mudou e ninguém está digitando
  setInterval(function () {
    if (!DB || enviando || mexendo() || document.hidden || diferencas(SERVIDOR, CONF).length) return;
    nexusPedir(CFG.conf + "?rev=" + REV).then(function (r) {
      if (!r || r.igual || enviando || mexendo()) return;
      SERVIDOR = r.conf; REV = r.conf_rev; CONF = JSON.parse(JSON.stringify(r.conf)); render();
    }, function () {});
  }, 60000);
  // a conta é refeita no servidor a cada 10 min: a tela busca a nova de 5 em 5
  setInterval(function () { if (DB && !document.hidden) carregar(); }, 300000);

  $("fr-tabela").addEventListener("click", aoClicar);
  $("fr-tabela").addEventListener("change", aoMudar);
  $("fr-tabela").addEventListener("input", aoMudar);
  $("fr-tabela").addEventListener("keydown", function (e) {
    if ((e.key === "Enter" || e.key === " ") && e.target.classList && e.target.classList.contains("fr-linha")) { e.preventDefault(); e.target.click(); }
  });
  $("fr-clientes").addEventListener("click", function (e) {
    var b = e.target.closest("[data-cli]"); if (!b) return;
    var k = b.getAttribute("data-cli"), sel = varios("cliente");
    porValores("cliente", sel.length === 1 && sel[0] === k ? [] : [k]);
  });
  $("fr-csv").addEventListener("click", csv);
  $("fr-exportar").addEventListener("click", function () {
    $("fr-menu").open = false;
    baixar("confirmacoes_furos.json", JSON.stringify({ versao: 1, exportado: new Date().toISOString(), conf: CONF }, null, 1), "application/json");
  });
  $("fr-importar").addEventListener("click", function () { $("fr-menu").open = false; $("fr-arquivo").click(); });
  $("fr-arquivo").addEventListener("change", function () { var f = $("fr-arquivo").files[0]; $("fr-arquivo").value = ""; if (f) importar(f); });
  document.addEventListener("click", function (e) { var m = $("fr-menu"); if (m.open && !m.contains(e.target)) m.open = false; });
  carregar();
})();
