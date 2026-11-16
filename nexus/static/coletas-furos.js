/* static/coletas-furos.js — a aba "Furos de coleta" da tela Coletas (16/11/2026).

   É a tela do relatório R01 da analista de Performance (`Gerador_Furos_Coleta\template2.html`), com a conta dela portada função a função
   (itens, "UFV toda", natureza Geração/ETM, validação por dia, vigência, sugestões, CSV) e três diferenças de propósito:
   - o dado vem do Nexus (`/coletas/furos/r01`: o banco e o COS), não de um HTML gerado à mão;
   - a validação é de TODOS: o que era o localStorage de cada navegador vai ao servidor a cada mudança (só o que mudou, com
     o `t` que esta tela viu; se outra pessoa mexeu na mesma chave antes, o servidor recusa e a tela recarrega);
   - o desenho é o do Nexus (DESIGN.md): os números na frente, a lista começando pela usina e a situação, o detalhe fechado
     até o clique, os filtros no padrão do Histórico de OS (static/filtros-os.js) e nenhum emoji.
   A regra mora em nexus/performance/coletas/ (CLAUDE.md de lá). */
(function () {
  "use strict";
  var CFG = JSON.parse(document.getElementById("fr-config").textContent);
  var $ = function (id) { return document.getElementById(id); };
  var DB = null, CONF = {}, SERVIDOR = {}, REV = 0, MONTH = "", MKEYS = [], VISAO = "res";
  var ORD = { res: { k: "pend", d: -1 }, det: { k: "pend", d: -1 } };
  var ABERTAS = new Set(), TODOS = new Set(), DIAS = new Set(), PARADAS = new Set(), SEL = {};
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
  function setVig(p, n, mode) {
    var ref = entryRef(p, n); if (!ref) return;
    if (mode === "*") toGlobal(p, n); else if (mode === "m") { CONF[ref].v = MONTH; touch(CONF[ref]); }
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
    return { kinds: kinds, cmt: items.filter(function (t) { return t.ent && t.ent.o; }).length, ufv: ufv, items: items, pend: pend, done: done,
      cp: cp, cellT: cellT, comp: comp, empty: empty, sit: sit, sev: sev, ex: ex,
      noos: (p.os || []).filter(function (o) { return o[6] === "A"; }).length, ipF: ipP ? ipP.pi.length : 0, ghF: ghP ? ghP.pi.length : 0,
      invF: invP.length, nInv: p.eqs.filter(isGen).length, pendN: pend.length, confN: done.length, inop: inop, inopN: inop.length };
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
  // "O que falta" numa linha só (Levi, 12/11/2026: o parecer na frente, o detalhe fechado): os dias de cada um ficam no
  // `title` e no detalhe da usina
  function falhaTxt(p, m) {
    var seg = [], um = function (tipo) { return m.pend.filter(function (t) { return t.tipo === tipo; })[0]; };
    if (m.empty && m.pendN === m.items.length && m.pendN) seg.push('<b class="fr-crit">Sem nenhuma coleta no mês</b>');
    var uf = um("UFV"), ip = um("IPOA"), gh = um("GHI"), iv = m.pend.filter(function (t) { return t.tipo === "Inversor"; });
    if (uf) seg.push('<span title="Dias ' + ranges(uf.pi, p.days) + '"><b class="fr-crit">Usina toda:</b> ' + uf.pi.length + (uf.pi.length === 1 ? " dia" : " dias") + "</span>");
    if (ip) seg.push('<span title="Dias ' + ranges(ip.pi, p.days) + '"><b>IPOA:</b> ' + ip.pi.length + (ip.pi.length === 1 ? " dia" : " dias") + "</span>");
    if (gh) seg.push('<span title="Dias ' + ranges(gh.pi, p.days) + '"><b>GHI:</b> ' + gh.pi.length + (gh.pi.length === 1 ? " dia" : " dias") + "</span>");
    if (iv.length) seg.push('<span title="' + esc(iv.map(function (t) { return curto(t.nome); }).join(", ")) + '"><b>Geração:</b> ' + iv.length + " de " + m.nInv + (m.nInv === 1 ? " equipamento" : " equipamentos") + "</span>");
    var an = m.pend.reduce(function (a, t) { return a + t.pi.filter(function (k) { return t.e.st[k] === "a"; }).length; }, 0);
    if (an) seg.push('<span class="fr-anom" title="Valor muito acima do padrão: coleta equivocada">' + an + (an === 1 ? " valor anômalo" : " valores anômalos") + "</span>");
    var pv = m.pend.filter(function (t) { return t.nv > 0; }).length;
    if (pv) seg.push('<span class="mudo">' + pv + (pv === 1 ? " item validado em parte" : " itens validados em parte") + "</span>");
    return seg.join('<span class="fr-sep" aria-hidden="true">·</span>');
  }

  // ── os filtros (static/filtros-os.js monta a barra, o painel e as etiquetas a partir destas <select>) ──────────────
  var SITS = [["falha", "Furo pendente"], ["conf", "Validado"], ["ok", "Sem falha"], ["os", "Com ausência explicada por parada"],
    ["noos", "Com parada sem OS"], ["ipoa", "IPOA pendente"], ["ghi", "GHI pendente"], ["inv", "Equipamento de geração com furo"],
    ["inop", "Com equipamento inoperante"]];
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
      if (e.target.name === "mes") { MONTH = e.target.value; ABERTAS.clear(); TODOS.clear(); SEL = {}; montarFiltros(); render(); return; }
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
          s === "os" ? m.ex : s === "noos" ? m.noos : s === "inv" ? m.invF : false;
      })) return false;
      return true;
    });
  }

  // ── o desenho ────────────────────────────────────────────────────────────────────────────────────────────────
  var rid = function (p) { return p.src + "|" + p.usina; };
  function situacao(m) {
    if (m.sit === "falha") return m.sev === "cr" ? '<span class="gc-status gc-status--critico">Falha crítica</span>' : '<span class="gc-status gc-status--alerta">Falha</span>';
    return m.sit === "conf" ? '<span class="gc-status gc-status--ok">Validado</span>' : '<span class="gc-status gc-status--neutro">Sem falha</span>';
  }
  function selos(m) {
    var h = "";
    if (m.inopN) h += '<span class="fr-selo fr-selo--inop" title="' + esc(m.inop.join(", ")) + '">' + m.inopN + " inoperante(s)</span>";
    if (m.noos) h += '<span class="fr-selo fr-selo--alerta" title="Parada registrada no COS sem número de OS: conta para o furo, mas é ponto de atenção">' + m.noos + " parada(s) sem OS</span>";
    if (m.cmt) h += '<span class="fr-selo" title="Itens com comentário">' + m.cmt + " comentário(s)</span>";
    return h;
  }
  function tipos(m) {
    return m.kinds ? m.kinds.split(" + ").map(function (k) { return '<span class="fr-tipo fr-tipo--' + (k === "ETM" ? "etm" : "ger") + '">' + k + "</span>"; }).join(" ") : '<span class="mudo">—</span>';
  }
  function numero(r, v, d, tom) { return '<div><div class="r">' + r + '</div><div class="v gc-num' + (tom ? " fr-v--" + tom : "") + '">' + v + '</div><div class="d">' + d + "</div></div>"; }
  function desenharNumeros(rows) {
    var n = function (k) { return rows.filter(function (r) { return r.m.sit === k; }).length; };
    var soma = function (k) { return rows.reduce(function (a, r) { return a + r.m[k]; }, 0); }, com = function (k) { return rows.filter(function (r) { return r.m[k]; }).length; };
    var cT = soma("cellT"), cP = soma("cp"), falha = n("falha"), crit = rows.filter(function (r) { return r.m.sit === "falha" && r.m.sev === "cr"; }).length;
    var ger = rows.filter(function (r) { return /Geração/.test(r.m.kinds); }).length, etm = rows.filter(function (r) { return /ETM/.test(r.m.kinds); }).length;
    $("fr-numeros").innerHTML =
      numero("Usinas com furo pendente", falha + ' <small>de ' + rows.length + "</small>", crit ? crit + " em falha crítica" : "nenhuma em falha crítica", falha ? (crit ? "critico" : "alerta") : "ok") +
      numero("Furo de geração", ger, "inversor, medidor ou a usina toda") +
      numero("Furo de ETM", etm, "IPOA ou GHI da estação") +
      numero("Completude", cT ? ((1 - cP / cT) * 100).toFixed(1).replace(".", ",") + "%" : "—", "das células esperadas até " + fmtD(M().end)) +
      numero("Paradas sem OS", soma("noos"), com("noos") ? "em " + com("noos") + " usina(s): ponto de atenção" : "nenhuma no mês");
    var par = function (r, v) { return '<div><span class="gc-rotulo">' + r + '</span><b class="gc-num">' + v + "</b></div>"; };
    $("fr-mais-grade").innerHTML =
      par("Usinas validadas", n("conf")) + par("Usinas sem falha", n("ok")) + par("Com IPOA pendente", com("ipF")) + par("Com GHI pendente", com("ghF")) +
      par("Células explicadas por parada", soma("ex") + " em " + com("ex") + " usina(s)") + par("Equipamentos inoperantes", soma("inopN") + " em " + com("inopN") + " usina(s)") +
      par("Equipamentos de geração com furo", soma("invF") + " de " + soma("nInv"));
  }
  function desenharFontes() {
    var f = DB.fontes || {}, s = DB.stats || {}, bd = f.bd || {}, partes = [];
    partes.push("Verificação de 01/" + MONTH.split("-")[1] + " a " + fmtD(M().end) + "/" + MONTH.split("-")[0] + ", " + P().length + " usinas");
    partes.push("banco: " + ["BD_Performance", "BD_Thopen"].map(function (k) { return k + " de " + (bd[k] ? bd[k].slice(0, 5) + " " + bd[k].slice(11) : "sem hora"); }).join(", "));
    if (f.cos && f.cos.ligado) partes.push("COS: " + (s.cos_registros || 0) + " paradas com geração parada");
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
  function desenharClientes(todas) {
    var cs = {}, sel = varios("cliente");
    todas.forEach(function (x) { var c = cs[x.p.cliente] = cs[x.p.cliente] || { n: 0, f: 0 }; c.n++; if (x.m.sit === "falha") c.f++; });
    var chip = function (nome, v, f, n, on) { return '<button type="button" class="gc-chip" data-cli="' + esc(v) + '" aria-pressed="' + (on ? "true" : "false") + '">' + esc(nome) + ' <b class="gc-num' + (f ? " fr-pend" : "") + '">' + f + '</b><span class="mudo gc-num">/' + n + "</span></button>"; };
    $("fr-clientes").innerHTML = chip("Todos", "", todas.filter(function (x) { return x.m.sit === "falha"; }).length, todas.length, !sel.length) +
      Object.keys(cs).sort(function (a, b) { return a.localeCompare(b, "pt-BR"); }).map(function (k) { return chip(k, k, cs[k].f, cs[k].n, sel.length === 1 && sel[0] === k); }).join("");
  }
  var COLS = {
    res: [["usina", "Usina"], ["sit", "Situação"], ["kinds", "Tipo de furo"], ["falha", "O que falta (dias sem dado)", 0, 1], ["pendN", "Pendentes", 1], ["confN", "Validados", 1], ["ex", "Com parada", 1]],
    det: [["usina", "Usina"], ["sit", "Situação"], ["kinds", "Tipo de furo"], ["ipF", "Dias sem IPOA", 1], ["ghF", "Dias sem GHI", 1], ["invF", "Geração com furo", 1], ["cp", "Células com furo", 1], ["comp", "Completude", 1], ["inopN", "Inoperantes", 1]]
  };
  function ordenar(rows) {
    var o = ORD[VISAO], sv = { falha: 2, conf: 1, ok: 0 };
    var val = function (x) {
      var p = x.p, m = x.m, k = o.k;
      return k === "sit" ? sv[m.sit] * 10 + (m.sev === "cr" ? 1 : 0) : k === "pend" ? (m.sit === "falha" ? 1e6 : m.sit === "conf" ? 5e5 : m.inopN ? 1e5 : 0) + (m.sev === "cr" ? 2e5 : 0) + m.cp : (k in m ? m[k] : (p[k] || ""));
    };
    rows.sort(function (a, b) { var x = val(a), y = val(b); return (x > y ? 1 : x < y ? -1 : 0) * o.d || (b.m.cp - a.m.cp) || a.p.usina.localeCompare(b.p.usina, "pt-BR"); });
  }
  function motOpts(ap, sel, ph) {
    return '<option value="">' + (ph || "Pendente: escolha o motivo") + "</option>" + MOT.filter(function (x) { return x.ap === "both" || x.ap === ap; }).map(function (x) {
      return '<option value="' + x.k + '"' + (sel === x.k ? " selected" : "") + ">" + x.l + "</option>";
    }).join("");
  }
  function quando(ent) {
    if (!ent || !ent.t) return "";
    var d = new Date(ent.t);
    if (isNaN(d)) return "";
    return (ent.q ? esc(ent.q) + " · " : "") + pad(d.getDate()) + "/" + pad(d.getMonth() + 1) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
  }
  function paradas(p, id) {
    if (!p.os || !p.os.length) return "";
    var cnt = p.os.map(function () { return 0; });
    p.eqs.forEach(function (e) { if (e.cv) Object.keys(e.cv).forEach(function (k) { e.cv[k].forEach(function (j) { cnt[j]++; }); }); });
    var fonte = { T: "Ticket", F: "Fracttal", C: "COS", "F+T": "Fracttal e ticket" };
    return '<details class="fr-dobra"' + (PARADAS.has(id) ? " open" : "") + ' data-paradas="' + esc(id) + '"><summary>Paradas registradas nesta usina <b class="gc-num">' + p.os.length +
      '</b><span class="mudo">cobre o dia a parada com 6 h ou mais entre 6h e 18h</span></summary><div class="fr-rola"><table class="fr-sub"><thead><tr><th>Fonte</th><th>OS</th><th>Equipamento</th><th>Classificação</th><th>Início</th><th>Fim</th><th class="n">Células cobertas</th></tr></thead><tbody>' +
      p.os.map(function (o, j) {
        return "<tr><td>" + (fonte[o[0]] || esc(o[0])) + "</td><td>" + (o[6] === "A" ? '<span class="fr-selo fr-selo--alerta">sem OS</span>' : esc(o[1])) + "</td><td>" + esc(o[2]) + "</td><td>" + esc(o[3]) +
          '</td><td class="gc-num">' + esc(o[4]) + '</td><td class="gc-num">' + esc(o[5]) + '</td><td class="n gc-num">' + cnt[j] + "</td></tr>";
      }).join("") + "</tbody></table></div></details>";
  }
  function mapa(p, m, id) {
    var sa = TODOS.has(id), z = opt("zero") !== "0", days = p.days, byN = {}, Dset = {};
    m.items.forEach(function (t) { byN[t.nome] = t; });
    (m.ufv ? m.ufv.idx : []).forEach(function (k) { Dset[k] = 1; });
    var eqs = p.eqs.filter(function (e) { return sa || byN[e.nome] || e.st.indexOf("e") >= 0 || (m.ufv && isGen(e)); });
    var h = '<div class="fr-mapa-topo"><h3 class="fr-h3">Mapa do mês</h3><div class="fr-chave">' +
      [["o", "Coletado"], ["v", "Vazio"], ["x", "Linha ausente"], ["z", "Zerado"], ["d", "IPOA só estimado"], ["a", "Valor anômalo"], ["e", "Explicado por parada"], ["c", "Validado"], ["i", "Inoperante"], ["p", "Usina sem geração"]]
        .map(function (x) { return '<span><i class="fr-c fr-c-' + x[0] + '"></i>' + x[1] + "</span>"; }).join("") +
      '</div><button type="button" class="gc-btn gc-btn--fantasma fr-mini" data-a="all" data-id="' + esc(id) + '">' + (sa ? "Mostrar só os equipamentos com falha" : "Mostrar todos os equipamentos (" + p.eqs.length + ")") + "</button></div>";
    if (!eqs.length) return h + '<p class="mudo">Nenhum equipamento com furo ou parada neste mês.</p>';
    h += '<div class="fr-rola"><table class="fr-heat"><thead><tr><th></th>' + days.map(function (d) { return '<th class="gc-num">' + d + "</th>"; }).join("") + "</tr></thead><tbody>";
    if (m.ufv) {
      h += '<tr><th>Usina toda' + (m.ufv.ok ? ' <small class="fr-okt">validado</small>' : "") + "</th>" + days.map(function (d, i) {
        var c = Dset[i] ? (m.ufv.vr[i] ? (m.ufv.vr[i] === "fora_op" ? "i" : "c") : "v") : "n";
        return '<td class="fr-c fr-c-' + c + '" title="' + (Dset[i] ? "Usina toda sem dado" + (m.ufv.vr[i] ? " (validado: " + esc(MOTL[m.ufv.vr[i]] || m.ufv.vr[i]) + ")" : "") : "sem furo da usina toda") + " · " + fmtD(d) + '"></td>';
      }).join("") + "</tr>";
    }
    eqs.forEach(function (e) {
      var t = byN[e.nome], bs = furoDe(e, z);
      h += "<tr><th>" + esc(e.nome) + (t && t.ok ? ' <small class="fr-okt">validado</small>' : (t && t.nv ? ' <small class="mudo">parcial</small>' : "")) + "</th>" + e.st.split("").map(function (c, i) {
        var u = (m.ufv && Dset[i] && isGen(e)) ? m.ufv : null, rr = u ? u.vr[i] : ((t && bs.indexOf(c) >= 0) ? t.vr[i] : ""), cc = rr ? (rr === "fora_op" ? "i" : "c") : c;
        return '<td class="fr-c fr-c-' + cc + '" title="' + esc(e.nome) + " · " + fmtD(days[i]) + " · " + (c === "e" ? "ausência esperada: " + esc(paradaTxt(p, e, i)) : ESTADO[c]) +
          (rr ? " (validado: " + esc(MOTL[rr] || rr) + ")" : "") + (u ? " · usina toda sem dado" : "") + '"></td>';
      }).join("") + "</tr>";
    });
    return h + "</tbody></table></div>";
  }
  function painel(p, m) {
    var id = rid(p), att0 = 'data-id="' + esc(id) + '"';
    var h = '<div class="fr-painel"><div class="fr-painel-topo"><div><b>' + esc(p.usina) + '</b> <span class="mudo">' + esc(p.cliente) + (p.carteira && p.carteira !== "—" && p.carteira !== p.cliente ? " · " + esc(p.carteira) : "") + " · " + esc(p.src) +
      (p.supervisor ? " · supervisor " + esc(p.supervisor) : "") + (p.status ? " · " + esc(p.status) : "") + "</span></div></div>";
    if (!m.items.length) return h + '<p class="mudo">Nenhum furo nesta usina com os critérios de agora.</p>' + paradas(p, id) + mapa(p, m, id) + "</div>";
    h += '<div class="fr-lote"><h3 class="fr-h3">Validar os furos</h3><span class="fr-lote-acoes"><button type="button" class="gc-btn gc-btn--contorno fr-mini" data-a="sug" ' + att0 + ' title="Aplica a sugestão do Nexus a cada item pendente que tem uma">Aceitar as sugestões</button>' +
      '<select class="gc-campo fr-sel" data-a="bulkmot" ' + att0 + ' aria-label="Motivo para todos os pendentes">' + motOpts("both", "", "Motivo para todos os pendentes") + "</select>" +
      '<select class="gc-campo fr-sel fr-sel--curto" data-a="bulkvig" ' + att0 + ' aria-label="Vale para"><option value="m">só este mês</option><option value="*">todos os meses</option></select>' +
      '<button type="button" class="gc-btn gc-btn--primario fr-mini" data-a="bulk" ' + att0 + ">Aplicar aos pendentes</button>" +
      '<button type="button" class="gc-btn gc-btn--fantasma fr-mini" data-a="clear" ' + att0 + ">Limpar as validações</button></span></div>";
    h += '<div class="fr-rola"><table class="fr-sub fr-itens"><thead><tr><th>Item</th><th>Dias com furo</th><th>Motivo do item inteiro</th><th>Vale para</th><th>Só alguns dias</th><th>Comentário</th></tr></thead><tbody>';
    m.items.forEach(function (t) {
      var s = suggest(p, t), ent = t.ent, ap = apOf(t.tipo), key = id + "|" + t.nome, sel = SEL[key] || (SEL[key] = {});
      var rs = {}; Object.keys(t.vr).forEach(function (k) { rs[t.vr[k]] = 1; });
      var rl = Object.keys(rs), selR = (t.nv === t.idx.length && rl.length === 1) ? rl[0] : "";
      var vsel = ent && ent.v === "*" ? "*" : (ent && String(ent.v).indexOf(",") >= 0 ? "keep" : "m");
      var att = att0 + ' data-n="' + esc(t.nome) + '"', nsel = Object.keys(sel).length;
      var chips = t.idx.map(function (k) {
        var d = p.days[k], r = t.vr[k];
        return '<button type="button" class="fr-dia' + (r ? " fr-dia--v" : "") + '" data-a="chip" ' + att + ' data-day="' + d + '" aria-pressed="' + (sel[d] ? "true" : "false") + '" title="' + fmtD(d) + ": " + (r ? "validado, " + esc(MOTL[r] || r) : "pendente") + '">' + pad(d) + "</button>";
      }).join("");
      var estado = t.ok ? '<span class="fr-okt">validado</span>' : (t.nv ? '<span class="fr-parc">' + t.nv + " de " + t.idx.length + " dias validados</span>" : '<span class="fr-pend">pendente</span>');
      h += "<tr><td><b>" + esc(t.tipo === "UFV" ? "Usina toda sem dado" : t.nome) + '</b> <span class="fr-tipo fr-tipo--' + (kindLbl(t.tipo) === "ETM" ? "etm" : "ger") + '">' + kindLbl(t.tipo) + "</span>" + '<span class="fr-item-estado">' + estado + "</span>" +
        (t.tipo === "UFV" ? '<small class="mudo fr-item-nota">os ' + t.w + " equipamentos de geração no mesmo dia</small>" : "") +
        (s && !t.ok ? '<small class="fr-item-nota fr-sug" title="' + esc(s[1]) + '">Sugestão: ' + esc(MOTL[s[0]]) + "</small>" : "") + "</td>" +
        '<td><b class="gc-num">' + t.idx.length + '</b><small class="mudo fr-item-nota">' + ranges(t.idx, p.days) + "</small></td>" +
        '<td><select class="gc-campo fr-sel" data-a="mot" ' + att + ' aria-label="Motivo de ' + esc(t.nome) + '">' + motOpts(ap, selR, t.nv && !selR ? "Validação parcial, por dia" : "") + "</select>" +
        (ent && (ent.r || ent.dm) && quando(ent) ? '<small class="mudo fr-quem">' + quando(ent) + "</small>" : "") + "</td>" +
        '<td><select class="gc-campo fr-sel fr-sel--curto" data-a="vig" ' + att + (t.nv ? "" : " disabled") + ' aria-label="Vale para"><option value="m"' + (vsel === "m" ? " selected" : "") + '>só este mês</option><option value="*"' + (vsel === "*" ? " selected" : "") + ">todos os meses</option>" +
        (vsel === "keep" ? '<option value="keep" selected>meses ' + esc(String(ent.v).replace(/,/g, ", ")) + "</option>" : "") + "</select></td>" +
        '<td><details class="fr-dias"' + ((DIAS.has(key) || nsel) ? " open" : "") + '><summary data-dk="' + esc(key) + '">' + (nsel ? nsel + " marcado(s)" : "Escolher os dias") + '</summary><div class="fr-dias-lista">' + chips + "</div>" +
        '<div class="fr-dias-acoes"><select class="gc-campo fr-sel" data-a="dmot" ' + att + ' aria-label="Motivo dos dias marcados">' + motOpts(ap, "", "Motivo dos dias marcados") + "</select>" +
        '<button type="button" class="gc-btn gc-btn--primario fr-mini" data-a="valdays" ' + att + ">Validar os marcados</button>" +
        '<button type="button" class="gc-btn gc-btn--contorno fr-mini" data-a="unval" ' + att + ">Tirar a validação</button>" +
        '<button type="button" class="gc-btn gc-btn--fantasma fr-mini" data-a="selpend" ' + att + ">Marcar os pendentes</button>" +
        '<button type="button" class="gc-btn gc-btn--fantasma fr-mini" data-a="selall" ' + att + ">Marcar todos</button>" +
        '<button type="button" class="gc-btn gc-btn--fantasma fr-mini" data-a="selnone" ' + att + ">Desmarcar</button></div></details></td>" +
        '<td><input type="text" class="gc-campo fr-obs" data-a="obs" ' + att + ' value="' + esc(ent && ent.o ? ent.o : "") + '" placeholder="Não muda a situação" aria-label="Comentário de ' + esc(t.nome) + '" maxlength="2000"></td></tr>';
    });
    return h + "</tbody></table></div>" + paradas(p, id) + mapa(p, m, id) + "</div>";
  }
  function celula(k, p, m) {
    switch (k) {
      case "usina": return '<td class="fr-usina"><i class="ph ph-caret-right fr-seta" aria-hidden="true"></i><span><b>' + esc(p.usina) + '</b><small class="mudo">' + esc(p.cliente) + (p.carteira && p.carteira !== "—" && p.carteira !== p.cliente ? " · " + esc(p.carteira) : "") + "</small></span></td>";
      case "sit": return '<td class="fr-sit">' + situacao(m) + selos(m) + "</td>";
      case "kinds": return "<td>" + tipos(m) + "</td>";
      case "falha": return '<td class="fr-falha">' + (falhaTxt(p, m) || '<span class="mudo">' + (m.sit === "conf" ? "Todo furo tem motivo registrado" : "Nada faltando no mês") + (m.ex ? ", " + m.ex + " célula(s) explicada(s) por parada" : "") + "</span>") + "</td>";
      case "comp": return '<td class="n"><span class="fr-barra-comp" aria-hidden="true"><i style="width:' + (m.comp * 100).toFixed(0) + '%"></i></span><span class="gc-num">' + (m.comp * 100).toFixed(0) + "%</span></td>";
      case "invF": return '<td class="n gc-num">' + m.invF + ' <small class="mudo">de ' + m.nInv + "</small></td>";
      default: return '<td class="n gc-num">' + (m[k] || (k === "pendN" || k === "cp" ? 0 : "")) + "</td>";
    }
  }
  function desenharTabela(rows) {
    var cols = COLS[VISAO], o = ORD[VISAO], tb = $("fr-tabela");
    tb.tHead.innerHTML = "<tr>" + cols.map(function (c) {
      return '<th scope="col" class="' + (c[2] ? "n" : "") + '" data-k="' + c[0] + '"' + (o.k === c[0] ? ' aria-sort="' + (o.d > 0 ? "ascending" : "descending") + '"' : "") + '><button type="button">' + c[1] +
        (o.k === c[0] ? '<i class="ph ph-caret-' + (o.d > 0 ? "up" : "down") + '" aria-hidden="true"></i>' : "") + "</button></th>";
    }).join("") + "</tr>";
    ordenar(rows);
    var h = "";
    rows.forEach(function (x) {
      var p = x.p, m = x.m, id = rid(p), ab = ABERTAS.has(id);
      h += '<tr class="fr-linha fr-linha--' + (m.sit === "falha" ? m.sev : m.sit) + (ab ? " fr-aberta" : "") + '" data-id="' + esc(id) + '" tabindex="0" aria-expanded="' + (ab ? "true" : "false") + '">' +
        cols.map(function (c) { return celula(c[0], p, m); }).join("") + "</tr>";
      if (ab) h += '<tr class="fr-detalhe"><td colspan="' + cols.length + '">' + painel(p, m) + "</td></tr>";
    });
    tb.tBodies[0].innerHTML = h || '<tr><td colspan="' + cols.length + '" class="fr-vazio">Nenhuma usina com estes filtros.</td></tr>';
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
  function aoClicar(e) {
    var th = e.target.closest("th[data-k]");
    if (th) {
      var o = ORD[VISAO], k = th.getAttribute("data-k");
      if (k === "falha") return;
      if (o.k === k) o.d *= -1; else { o.k = k; o.d = k === "usina" ? 1 : -1; }
      render(); return;
    }
    var b = e.target.closest("button[data-a]");
    if (b) {
      var p = porId(b.getAttribute("data-id")), a = b.getAttribute("data-a");
      if (!p) return;
      var m = calc(p), nome = b.getAttribute("data-n"), kS = b.getAttribute("data-id") + "|" + (nome || "");
      var tI = nome ? m.items.filter(function (x) { return x.nome === nome; })[0] : null, S = SEL[kS] || (SEL[kS] = {});
      var marcar = function (ks) { var n = {}; ks.forEach(function (k) { n[p.days[k]] = 1; }); SEL[kS] = n; };
      if (a === "chip") { var d = +b.getAttribute("data-day"); if (S[d]) delete S[d]; else S[d] = 1; render(); }
      else if (a === "selpend" && tI) { marcar(tI.pi); render(); }
      else if (a === "selall" && tI) { marcar(tI.idx); render(); }
      else if (a === "selnone") { SEL[kS] = {}; render(); }
      else if ((a === "valdays" || a === "unval") && tI) {
        var dias = Object.keys(S).map(Number), mot = "";
        if (!dias.length) { recado("Marque os dias antes.", true); return; }
        if (a === "valdays") {
          var sl = b.closest(".fr-dias-acoes").querySelector("[data-a=dmot]");
          mot = sl.value;
          if (!mot) { sl.focus(); recado("Escolha o motivo dos dias marcados.", true); return; }
        }
        SEL[kS] = {};
        mudar(function () { setDays(p, tI.nome, tI.idx.map(function (k) { return p.days[k]; }), dias, mot); });
      }
      else if (a === "all") { var id = b.getAttribute("data-id"); if (TODOS.has(id)) TODOS.delete(id); else TODOS.add(id); render(); }
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
      else if (a === "clear") {
        if (!m.items.some(function (t) { return t.nv; })) { recado("Esta usina não tem validação neste mês."); return; }
        mudar(function () { m.items.forEach(function (t) { setConf(p, t.nome, ""); }); });
      }
      else if (a === "bulk") {
        var cx = b.closest(".fr-lote"), bm = cx.querySelector("[data-a=bulkmot]").value, bv = cx.querySelector("[data-a=bulkvig]").value;
        if (!bm) { cx.querySelector("[data-a=bulkmot]").focus(); recado("Escolha o motivo para aplicar aos pendentes.", true); return; }
        var mo = MOT.filter(function (x) { return x.k === bm; })[0];
        mudar(function () {
          m.pend.forEach(function (t) {
            if (mo.ap !== "both" && mo.ap !== apOf(t.tipo)) return;
            if (t.nv) setDays(p, t.nome, t.idx.map(function (k) { return p.days[k]; }), t.pi.map(function (k) { return p.days[k]; }), bm);
            else setConf(p, t.nome, bm, bv);
          });
        });
      }
      return;
    }
    var sm = e.target.closest("summary[data-dk]");
    if (sm) { e.preventDefault(); var dk = sm.getAttribute("data-dk"); if (DIAS.has(dk)) DIAS.delete(dk); else DIAS.add(dk); render(); return; }
    var sp = e.target.closest("details[data-paradas] > summary");
    if (sp) { var pid = sp.parentNode.getAttribute("data-paradas"); if (PARADAS.has(pid)) PARADAS.delete(pid); else PARADAS.add(pid); return; }
    if (e.target.closest("select,input,button,details,.fr-detalhe")) return;
    var tr = e.target.closest("tr.fr-linha");
    if (tr) { var rid_ = tr.getAttribute("data-id"); if (ABERTAS.has(rid_)) ABERTAS.delete(rid_); else ABERTAS.add(rid_); render(); }
  }
  function aoMudar(e) {
    var t = e.target, a = t.getAttribute("data-a");
    if (!a || a.indexOf("bulk") === 0 || a === "dmot") return;
    var p = porId(t.getAttribute("data-id")), n = t.getAttribute("data-n");
    if (!p) return;
    if (a === "mot") mudar(function () { setConf(p, n, t.value, getEntry(p, n) ? "keep" : "m"); });
    else if (a === "vig") mudar(function () { setVig(p, n, t.value); });
    else if (a === "obs") mudar(function () { setObs(p, n, t.value.trim()); });
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
  $("fr-tabela").addEventListener("keydown", function (e) {
    if ((e.key === "Enter" || e.key === " ") && e.target.classList && e.target.classList.contains("fr-linha")) { e.preventDefault(); e.target.click(); }
  });
  $("fr-clientes").addEventListener("click", function (e) { var b = e.target.closest("[data-cli]"); if (b) porValores("cliente", b.getAttribute("data-cli") ? [b.getAttribute("data-cli")] : []); });
  [].forEach.call(document.querySelectorAll("[data-visao]"), function (b) {
    b.addEventListener("click", function () {
      VISAO = b.getAttribute("data-visao");
      [].forEach.call(document.querySelectorAll("[data-visao]"), function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); });
      render();
    });
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
