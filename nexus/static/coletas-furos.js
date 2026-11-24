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
  // o BD da tela (Levi, 24/11/2026: "tem que começar a separar BD performance e BD operações. Para isso é bem direcionado";
  // escolha dele: a troca no alto vale para a tela toda, cada equipe vê o seu). O navegador lembra a escolha
  var BDS = ["BD_Performance", "BD_Thopen"], BD = BDS[0];
  (function () { var k = "nexus.furos.bd"; try { var v = localStorage.getItem(k); if (BDS.indexOf(v) >= 0) BD = v; } catch (e) {} })();
  var ORD = { k: "tam", d: -1 };
  var VISAO = "tabela", ABERTAS = new Set(), TODOS = new Set(), OCTODAS = new Set(), SEL = {}, BARRA = {}, MAPA = {};
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
  // o motivo curto, para a linha do mapa (o longo fica no `title` e na lista de escolha)
  var MOTC = { sem_ipoa: "sem sensor de IPOA", sem_ghi: "sem sensor de GHI", coleta_alt: "outra fonte", fora_op: "inoperante",
    nao_mob: "não mobilizada", os: "parada com OS", zero_real: "zero real", corrigido: "já corrigido", outro: "outro" };
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
  // com o equipamento que o COS citou (24/11/2026: "Falha de comunicação (Inversor 2.4)" diz que não é a usina)
  var ocCurto = function (p, j, d) { var e = String(p.oc[j][3] || ""); return p.oc[j][2] + (e && e.length <= 40 ? " (" + e + ")" : "") + " " + noDia(p, j, d); };
  // falha de comunicação: o tipo de falha do COS (139 em novembro); com a usina gerando, é o furo que a equipe resolve
  var ehCom = function (o) { return /comunica/i.test(o[2]); };
  // o ALCANCE da falha de comunicação (Levi, 24/11/2026, na Nova Xavantina 1: "é só o inversor com falha de comunicação, o
  // resto está verde [...] tem que ter uma cor só para inversor"; a falha do Inversor 2.4, em aberto desde 22/06, pintava de
  // roxo todo dia com furo, até o do IPOA). A ocorrência que cita inversores no campo Equipamentos ("Inversor 2.4", "UG 1")
  // vale só para eles: devolve {nome do equipamento: 1}. Sem inversor citado (vazio, cabine, relé, SKID, estação) ou com
  // nome que não casa com nenhum equipamento da aba, vale para a usina toda, como antes: devolve null
  function alvoCom(p, j) {
    var c = p._alvo = p._alvo || {};
    if (j in c) return c[j];
    var txt = String(p.oc[j][3] || ""), r = /(Inversor|UG)\s*(\d+(?:\.\d+)?)/gi, a, s = {}, n = 0;
    while ((a = r.exec(txt))) {
      var q = nat(a[2]), ug = /^ug/i.test(a[1]);
      p.eqs.forEach(function (e) {
        if (!isGen(e) || s[e.nome]) return;
        var en = nat(e.nome);
        if (ug ? en[0] === q[0] : en.length === q.length && en.every(function (x, i) { return x === q[i]; })) { s[e.nome] = 1; n++; }
      });
    }
    return (c[j] = n ? s : null);
  }
  // "Inversor 2.1, 2.2 e 2.3" ou "15 equipamentos (Inversor 2.1 a 3.5)"
  function listaEq(ns) {
    if (ns.length <= 3) return ns.join(", ");
    return ns.length + " equipamentos (" + ns[0] + " a " + curto(ns[ns.length - 1]) + ")";
  }
  // as horas da ocorrência dentro da janela solar (06-18 h) do dia: a régua das 6 h do R01
  function solNoDia(p, j, d) {
    var t = tempos(p)[j], a = iniDia(d) + 6 * 36e5, b = iniDia(d) + 18 * 36e5;
    return Math.max(0, Math.min(t[1], b) - Math.max(t[0], a)) / 36e5;
  }

  // ── a conta de cada usina (calc da tela da analista) ─────────────────────────────────────────────────────────────
  var M = function () { return DB.months[MONTH]; }, PC = { ps: null, bd: "", v: null };
  // as usinas do mês no BD escolhido
  var P = function () {
    var ps = M().plants;
    if (PC.ps !== ps || PC.bd !== BD) { PC.ps = ps; PC.bd = BD; PC.v = ps.filter(function (p) { return p.src === BD; }); }
    return PC.v;
  };
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
    // o dia da usina, para a tira do mês, pela CAUSA (Levi, 19/11/2026: "é justificado se foi queda. Agora, se foi falha de
    // comunicação, a gente tem que resolver isso [...] uma cor para o que foi justificado em questão de geração, uma cor que
    // tem furo e foi falha de comunicação [...] e conseguir filtrar esses pontos"). Com furo pendente no dia:
    //   m = o COS registrou falha de comunicação no dia (o furo a resolver: a usina gerava e o dado não veio);
    //   s = furo sem justificativa no COS; com `q`, o COS tem uma queda curta no dia, que pela regra do R01 não justifica
    //       (o Levi manteve as 6 h de sol, 19/11/2026: uma queda de 20 min não explica o dia inteiro sem dado);
    //   `t` = falta só o IPOA ou o GHI (o quadrado vazado).
    // Sem furo pendente: c = validado pela equipe; e = justificado por queda (a parada de 6 h ou mais que a regra aceitou);
    // n = usina sem geração no dia; o = completo.
    //   k = o furo da geração está só nos inversores que o COS registrou com falha de comunicação (24/11/2026).
    // Sem furo pendente, a queda que pegou só parte da usina, com o resto da geração com dado, é dia completo (`jp`).
    var t0 = tempos(p), oc = p.oc || [], dia = [], ocd = [], com = [], comI = [], dd = 0, du = 0, dCom = 0, dComI = 0, dSem = 0, dSemT = 0, dSemP = 0, dEtm = 0,
      dQ = 0, dJ = 0, dJp = 0, dV = 0, cosF = 0, ocF = {}, nGen = p.eqs.filter(isGen).length;
    p.days.forEach(function (d, k) {
      var tem = false, pu = false, pg = 0, pe = false, pgN = [];
      items.forEach(function (t) {
        if (t.idx.indexOf(k) < 0) return;
        tem = true;
        if (k in t.vr) return;
        if (t.tipo === "UFV") pu = true; else if (t.tipo === "Inversor") { pg++; pgN.push(t.nome); } else pe = true;
      });
      // a usina toda: o item "UFV toda" do dia, ou todos os equipamentos de geração sem dado (a usina de um inversor só)
      var total = pu || (nGen > 0 && pg >= nGen);
      var a = iniDia(d), b = a + 864e5, js = [];
      t0.forEach(function (t, j) { if (t[0] < b && t[1] > a) js.push(j); });
      // a falha de comunicação da usina (cm) e a dos inversores citados (ci); com todos os inversores pendentes do dia
      // citados, o dia é `k`; se eles são a geração inteira (a usina de um inversor só), é a usina: `m`
      var cm = false, ci = {};
      js.forEach(function (j) { if (!ehCom(oc[j])) return; var al = alvoCom(p, j); if (!al) cm = true; else Object.keys(al).forEach(function (n) { ci[n] = 1; }); });
      var ki = !cm && !pu && pg > 0 && pgN.every(function (n) { return ci[n]; });
      if (ki && total) { cm = true; ki = false; }
      var q = !cm && !ki && js.some(function (j) { return oc[j][5] === "s" && !ehCom(oc[j]) && solNoDia(p, j, d) < 6; });
      var pend = pu || pg || pe, x = { s: "o", t: pend && !pu && !pg, q: pend && q };
      if (pend) {
        x.s = cm ? "m" : ki ? "k" : (total || !pg) ? "s" : "p";
        if (ki) x.ki = pgN;
        dd++; if (total) du++;
        if (cm) dCom++; else if (ki) dComI++; else { dSem++; if (x.t) dEtm++; else if (total) dSemT++; else dSemP++; if (q) dQ++; }
        if (js.length) { cosF++; js.forEach(function (j) { ocF[j] = 1; }); }
      }
      else if (tem) { x.s = "c"; dV++; }
      else if (p.eqs.some(function (e) { return e.st[k] === "e"; })) {
        // a queda que pegou só parte da usina (Levi, 24/11/2026: "a queda foi parcial"; na Nova Xavantina 1, de 01 a 05/11,
        // 10 dos 25 inversores com dado e o "Desligamento de usina" justificando os outros 15 saía azul, como se a usina
        // toda tivesse caído): com algum equipamento de geração com dado no dia, é completo; quem caiu fica no `title` e
        // no mapa do mês. O azul fica para a queda da usina toda
        if (p.eqs.some(function (e) { return isGen(e) && "oa".indexOf(e.st[k]) >= 0; })) {
          x.jp = p.eqs.filter(function (e) { return e.st[k] === "e"; }).map(function (e) { return e.nome; }); dJp++;
        } else { x.s = "e"; dJ++; }
      }
      else if (p.eqs.length && p.eqs.filter(isGen).every(function (e) { return e.st[k] === "p"; })) x.s = "n";
      dia.push(x); ocd.push(js); com.push(cm); comI.push(ci);
    });
    return { kinds: kinds, cmt: items.filter(function (t) { return t.ent && t.ent.o; }).length, ufv: ufv, items: items, pend: pend, done: done,
      cp: cp, cellT: cellT, comp: comp, empty: empty, sit: sit, sev: sev, ex: ex,
      noos: (p.os || []).filter(function (o) { return o[6] === "A"; }).length, ipF: ipP ? ipP.pi.length : 0, ghF: ghP ? ghP.pi.length : 0,
      invF: invP.length, nInv: p.eqs.filter(isGen).length, pendN: pend.length, confN: done.length, inop: inop, inopN: inop.length,
      dia: dia, ocd: ocd, com: com, comI: comI, dd: dd, du: du, dCom: dCom, dComI: dComI, dJp: dJp, dSem: dSem, dSemT: dSemT, dSemP: dSemP, dEtm: dEtm, dQ: dQ, dJ: dJ, dV: dV, cosF: cosF, ocF: ocF,
      ocN: (p.oc || []).length, ocFN: Object.keys(ocF).length };
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
  // as causas do furo pelo COS viraram filtro (Levi, 19/11/2026: "eu quero esses pontos e eu quero conseguir filtrar esses
  // pontos"); a lista abre só no "Furo pendente": o justificado sai dela ("tirasse dessa lista [...] o que está justificado")
  var SITS = [["falha", "Furo pendente"], ["com", "Furo com falha de comunicação da usina no COS"], ["comi", "Furo com falha de comunicação no inversor"], ["semj", "Furo sem justificativa no COS"], ["semt", "Sem justificativa: a usina toda sem dado"],
    ["semp", "Sem justificativa: parte dos inversores"], ["etmo", "Falta só o IPOA ou o GHI"],
    ["qc", "Furo com queda curta no COS (menos de 6 h)"], ["os", "Com dia justificado por queda"], ["val", "Com dia validado pela equipe"],
    ["conf", "Tudo validado"], ["ok", "Sem falha"], ["noos", "Com parada sem OS"], ["ipoa", "IPOA pendente"], ["ghi", "GHI pendente"],
    ["inv", "Equipamento de geração com furo"], ["inop", "Com equipamento inoperante"]];
  var SIT_PADRAO = ["falha"];
  function lerFiltros() {
    var f = $("fr-filtros"), o = {};
    if (!f || !f.elements.cliente) return null;
    ["cliente", "carteira", "fonte", "status", "sit"].forEach(function (n) { o[n] = varios(n); });
    ["tipo", "zero", "paradas", "validados"].forEach(function (n) { o[n] = opt(n); });
    o.q = f.elements.q ? f.elements.q.value : "";
    return o;
  }
  function montarFiltros(trocouBD) {
    var antes = lerFiltros() || { cliente: [], carteira: [], fonte: [], status: [], sit: SIT_PADRAO.slice(), tipo: "", zero: "1", paradas: "1", validados: "1", q: "" };
    var ps = P();
    if (trocouBD) { antes.cliente = []; antes.carteira = []; }          // o cliente de um BD não existe no outro
    function unicos(fn) { var s = {}; ps.forEach(function (p) { var v = fn(p); if (v !== null) s[v] = 1; }); return Object.keys(s).sort(function (a, b) { return a.localeCompare(b, "pt-BR"); }); }
    function lista(nome, rotulo, ops, marcados) {
      if (!ops.length) return "";
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
      // o mês na mesma linha e na mesma altura da busca e do Filtros (Levi, 19/11/2026: "esse mês aí tá desalinhado com o
      // buscador e os filtros, tá feião"): sem o rótulo em cima, que o descia; o nome fica para o leitor de tela
      '<label class="fr-mes"><select name="mes" class="fr-mes-sel" aria-label="Mês" data-fo-fora>' + MKEYS.slice().reverse().map(function (k) {
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
  function filtrar(todas, semSituacao) {
    var f = lerFiltros(), q = norm(f.q);
    if (semSituacao) f.sit = [];
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
          s === "os" ? m.dJ || m.ex : s === "noos" ? m.noos : s === "inv" ? m.invF : s === "com" ? m.dCom : s === "comi" ? m.dComI : s === "semj" ? m.dSem :
          s === "qc" ? m.dQ : s === "val" ? m.dV : s === "semt" ? m.dSemT : s === "semp" ? m.dSemP : s === "etmo" ? m.dEtm : false;
      })) return false;
      return true;
    });
  }

  // ── o desenho ────────────────────────────────────────────────────────────────────────────────────────────────
  var rid = function (p) { return p.src + "|" + p.usina; };
  // a legenda é fixa no alto da lista, conta e filtra (Levi, 19/11/2026: "quando eu estiver scrollando, a parte que mostra
  // a quantidade de usinas e o que cada cor significa precisa ficar fixa [...] Esses KPIs aí não servem de nada, sendo que
  // tem a mesma coisa sendo dita embaixo"; e a ordem: "os vermelhos juntos [...] à direita. O resto pode ficar à esquerda").
  // Conta os dias com os outros filtros de agora, sem o de Situação, que é o que o clique troca; o 2º clique volta ao padrão
  var LEG = [
    [null, "o", "completo/validado", null, "o dia com todo o dado (validado automático), com o furo validado pela equipe, ou com parte da usina parada por uma queda que justifica e o resto com dado"],
    ["os", "e", "justificado por queda", "dJ", "a usina toda parada pela queda do COS, de 6 h ou mais entre 6h e 18h"],
    ["com", "m", "falha de comunicação da usina", "dCom", "furo num dia em que o COS registrou falha de comunicação da usina: resolver"],
    ["comi", "k", "falha de comunicação no inversor", "dComI", "furo só nos inversores que o COS registrou com falha de comunicação; o resto da geração tem dado: resolver"],
    "|",
    ["semt", "s", "usina toda sem dado", "dSemT", "sem justificativa: a usina inteira sem dado no dia"],
    ["semp", "p", "parcial", "dSemP", "sem justificativa: um inversor ou alguns sem dado"],
    ["qc", "s fr-q--qc", "com queda curta", "dQ", "sem justificativa, com uma queda de menos de 6 h no COS (não justifica)"],
    ["etmo", "s fr-q--t", "só IPOA ou GHI", "dEtm", "sem justificativa: a geração está lá, falta a estação"]];
  function desenharLegenda(base) {
    var sel = varios("sit"), cT = 0, cP = 0;
    base.forEach(function (r) { cT += r.m.cellT; cP += r.m.cp; });
    // dois grupos: o resto à esquerda e os vermelhos juntos à direita; na tela estreita o grupo inteiro desce
    $("fr-legenda").innerHTML = '<span class="fr-leg-grupo">' + LEG.map(function (c) {
      if (c === "|") return '</span><span class="fr-leg-grupo">';
      var sw = '<i class="fr-q fr-q--' + c[1] + '" aria-hidden="true"></i>';
      if (!c[0]) return '<span class="fr-leg fr-leg--fixa" title="' + c[4] + '">' + sw + c[2] + "</span>";
      var dias = 0, us = 0, on = sel.length === 1 && sel[0] === c[0];
      base.forEach(function (r) { var v = r.m[c[3]]; dias += v; if (v) us++; });
      return '<button type="button" class="fr-leg" data-sit="' + c[0] + '" aria-pressed="' + on + '" title="' + c[4] + ": " + dias +
        (dias === 1 ? " dia" : " dias") + " em " + us + (us === 1 ? " usina" : " usinas") + (on ? ". Clique de novo para voltar." : ". Clique para filtrar.") + '">' +
        sw + c[2] + ' <b class="gc-num">' + dias + "</b></button>";
    }).join("") + "</span>";
    $("fr-completude").textContent = cT ? "Completude de " + ((1 - cP / cT) * 100).toFixed(1).replace(".", ",") + "% das células esperadas até " + fmtD(M().end) + ". " : "";
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
  // é a soma dos dias com furo pendente das usinas dele, pela causa: roxo, falha de comunicação no COS; vermelho, sem
  // justificativa. O clique filtra
  // O PESO (Levi, 24/11/2026: "ele mostra por quantidade e não tá adiantando muito não [...] Apollo só tem 3 usinas, as 3
  // estão com furo [...] Tem que mostrar esse peso"; escolha dele: a % dos dias das usinas). A barra é dias com furo
  // pendente ÷ (usinas × dias verificados): a Thopen, com 98 usinas, não esmaga quem tem 3. No BD_Thopen o cliente é um
  // só, e a barra sai por carteira
  var campoCli = function () { return BD === "BD_Thopen" ? "carteira" : "cliente"; };
  var nomeCli = function (k) { return k === "—" || !k ? "Sem carteira" : k; };
  function desenharClientes(todas) {
    var cs = {}, campo = campoCli(), sel = varios(campo);
    todas.forEach(function (x) {
      var g = x.p[campo] || "—", c = cs[g] = cs[g] || { n: 0, f: 0, dd: 0, cap: 0, com: 0, comi: 0, semt: 0, semp: 0, etm: 0 };
      c.n++; c.dd += x.m.dd; c.cap += x.p.days.length; c.com += x.m.dCom; c.comi += x.m.dComI; c.semt += x.m.dSemT; c.semp += x.m.dSemP; c.etm += x.m.dEtm;
      if (x.m.sit === "falha") c.f++;
    });
    var peso = function (c) { return c.cap ? c.dd / c.cap : 0; }, pct = function (v) { return Math.round(100 * v) + "%"; };
    var nomes = Object.keys(cs).sort(function (a, b) { return a.localeCompare(b, "pt-BR"); });
    var com = nomes.filter(function (k) { return cs[k].dd; }).sort(function (a, b) { return peso(cs[b]) - peso(cs[a]) || cs[b].dd - cs[a].dd; }), sem = nomes.filter(function (k) { return !cs[k].dd; });
    $("fr-cli-titulo").textContent = campo === "carteira" ? "Peso do furo por carteira" : "Peso do furo por cliente";
    $("fr-clientes").setAttribute("aria-label", campo === "carteira" ? "Filtrar por carteira" : "Filtrar por cliente");
    $("fr-clientes").innerHTML = com.map(function (k) {
      var c = cs[k], on = sel.length === 1 && sel[0] === k;
      return '<button type="button" class="fr-cli' + (sel.length && !on ? " fr-cli--fora" : "") + '" data-cli="' + esc(k) + '" aria-pressed="' + on + '">' +
        '<span class="fr-cli-nome">' + esc(nomeCli(k)) + "</span>" +
        '<span class="fr-cli-barra" title="' + pct(peso(c)) + " dos dias das usinas: " + c.dd + " de " + c.cap + ". Falha de comunicação: " + c.com + " da usina, " + c.comi +
        " no inversor; sem justificativa: " + c.semt + " com a usina toda, " + c.semp + " parciais, " + c.etm + ' só de IPOA ou GHI">' +
        [["com", c.com], ["comi", c.comi], ["semt", c.semt], ["semp", c.semp], ["etm", c.etm]].map(function (s) {
          return '<i class="fr-cli-' + s[0] + '" style="width:' + (c.cap ? 100 * s[1] / c.cap : 0).toFixed(2) + '%"></i>';
        }).join("") + "</span>" +
        '<span class="fr-cli-num"><b class="gc-num">' + pct(peso(c)) + '</b> <span class="mudo">· ' + c.dd + " de " + c.cap + " dias</span>" +
        (c.com + c.comi ? ' <span class="fr-txt-com">· ' + (c.com + c.comi) + " de comunicação</span>" : "") +
        ' <span class="mudo">· ' + c.f + " de " + c.n + (c.n === 1 ? " usina" : " usinas") + "</span></span></button>";
    }).join("") + (sem.length ? '<p class="fr-cli-sem-furo mudo">Sem furo pendente: ' + sem.map(function (k) {
      return '<button type="button" class="fr-cli-link" data-cli="' + esc(k) + '">' + esc(nomeCli(k)) + "</button>";
    }).join(", ") + "</p>" : "") + (com.length ? "" : '<p class="mudo">Nenhum' + (campoCli() === "carteira" ? "a carteira" : " cliente") + ' com furo pendente neste mês.</p>');
  }
  var DIA_T = { m: "furo com falha de comunicação da usina no COS", k: "furo com falha de comunicação no inversor, no COS (o resto da geração tem dado)", s: "furo sem justificativa no COS: a usina toda sem dado",
    p: "furo sem justificativa no COS: parte dos inversores sem dado", c: "furo validado pela equipe",
    e: "justificado por queda da usina toda (parada do COS de 6 h ou mais)", n: "usina sem geração no dia", o: "completo: todo o dado no dia (validado automático)" };
  function classeDia(x) { return "fr-q fr-q--" + x.s + (x.t ? " fr-q--t" : "") + (x.q ? " fr-q--qc" : ""); }
  function tira(p, m) {
    return '<span class="fr-tira">' + m.dia.map(function (x, k) {
      var js = m.ocd[k], d = p.days[k];
      return '<i class="' + classeDia(x) + '" title="' + fmtD(d) + ": " + (x.t ? (x.s === "m" ? "furo com falha de comunicação da usina no COS: falta só o IPOA ou o GHI" : "furo sem justificativa no COS: falta só o IPOA ou o GHI") : DIA_T[x.s]) +
        (x.ki ? ": " + esc(listaEq(x.ki)) : "") + (x.jp ? "; justificado por queda: " + esc(listaEq(x.jp)) : "") +
        (x.q ? " (o COS tem uma queda curta, que não justifica o dia)" : "") +
        (js.length ? " · COS: " + esc(js.map(function (j) { return ocCurto(p, j, d); }).join("; ")) : "") + '"></i>';
    }).join("") + "</span>";
  }
  var COLS = [["usina", "Usina"], ["dia", "O mês, dia a dia"], ["tam", "Furo pendente", 1], ["com", "Falha de comunicação", 1]];
  function ordenar(rows) {
    var o = ORD;
    var val = function (x) {
      var m = x.m;
      // o tamanho: os dias com furo pendente; no empate, os de falha de comunicação e os da usina toda primeiro
      return o.k === "usina" ? x.p.usina : o.k === "com" ? (m.dCom + m.dComI) * 1e4 + m.dd : m.dd * 1e6 + m.dCom * 1e3 + m.du * 10 + (m.sit === "conf" ? 1 : 0) + m.cp / 1e7;
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
        if (m.dd) return '<td class="n fr-tam"><b class="gc-num fr-tam-n">' + m.dd + '</b> <span class="mudo">' + (m.dd === 1 ? "dia" : "dias") + '</span><small>' + esc(oQueFalta(m)) + "</small></td>";
        return '<td class="n fr-tam">' + (m.sit === "conf" ? '<span class="fr-okt">validado</span>' : '<span class="mudo">completo</span>') + (m.dJ ? '<small>' + m.dJ + (m.dJ === 1 ? " dia justificado" : " dias justificados") + " por queda</small>" : "") + "</td>";
      case "com":
        var nc = m.dCom + m.dComI;
        return '<td class="n">' + (nc ? '<b class="gc-num fr-txt-com">' + nc + '</b> <span class="mudo">' + (nc === 1 ? "dia" : "dias") + "</span>" +
          (m.dComI ? '<small>' + (m.dComI === nc ? "no inversor" : m.dComI + " no inversor") + "</small>" : "") : '<span class="mudo">—</span>') + "</td>";
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
    // por padrão, as seis que mais dizem sobre o furo (a que explica o dia, a em aberto, a mais longa), em ordem de data;
    // "Ver as N" mostra todas (a Crateús tinha 20, quase todas desligamentos de minutos à noite)
    var todas = OCTODAS.has(id), rel = oc.map(function (_o, j) { return j; }).filter(function (j) { return m.ocF[j] || oc[j][7]; });
    var mostrar = todas ? oc.map(function (_o, j) { return j; }) : rel.slice().sort(function (a, b) {
      return (oc[b][7] - oc[a][7]) || (oc[b][6] - oc[a][6]) || ((t[b][1] - t[b][0]) - (t[a][1] - t[a][0]));
    }).slice(0, 6).sort(function (a, b) { return a - b; });
    var h = '<section class="fr-oc"><div class="fr-oc-topo"><h3 class="fr-h3">O que o COS registrou</h3><span class="mudo">' +
      (oc.length ? oc.length + (oc.length === 1 ? " ocorrência" : " ocorrências") + " em " + MN[MES()] + "; " + m.ocFN + " nos dias com furo" : "nenhuma ocorrência em " + MN[MES()]) + "</span>" +
      (oc.length && mostrar.length < oc.length ? '<button type="button" class="gc-btn gc-btn--fantasma fr-mini" data-a="octodas" data-id="' + esc(id) + '">Ver as ' + oc.length + "</button>" : "") +
      (todas && oc.length > 6 ? '<button type="button" class="gc-btn gc-btn--fantasma fr-mini" data-a="octodas" data-id="' + esc(id) + '">Só as principais</button>' : "") + "</div>";
    if (oc.length && !mostrar.length) h += '<p class="mudo fr-oc-nada">Nenhuma ocorrência do COS nos dias com furo: o furo não tem explicação registrada.</p>';
    if (mostrar.length || cong.length) {
      h += '<div class="fr-rola"><table class="fr-sub fr-oc-tab"><thead><tr><th>Quando</th><th>Ocorrência</th><th>OS</th><th>Geração</th><th></th></tr></thead><tbody>' +
        mostrar.map(function (j) {
          var o = oc[j];
          return '<tr class="' + (ehCom(o) ? "fr-oc-com" : o[7] ? "fr-oc-just" : m.ocF[j] ? "fr-oc-nofuro" : "") + '"><td class="gc-num fr-oc-quando">' + dh(t[j][0]) + " → " + (o[6] ? '<b class="fr-pend">em aberto</b>' : dh(t[j][1])) +
            ' <span class="mudo">(' + dur(t[j][1] - t[j][0]) + ")</span></td><td><b>" + esc(o[2]) + "</b>" + (o[3] ? ' <span class="mudo">' + esc(o[3]) + "</span>" : "") + "</td>" +
            '<td class="gc-num">' + (o[4] ? esc(o[4]) : '<span class="fr-selo fr-selo--alerta">sem OS</span>') + "</td>" +
            "<td>" + (o[5] === "s" ? "parou" : o[5] === "n" ? "seguiu" : '<span class="mudo">não informado</span>') + "</td>" +
            "<td>" + (o[7] ? '<span class="fr-tag fr-tag--e" title="Parada de 6 h ou mais entre 6h e 18h, com geração parada: pela regra do R01 o dia não é furo">explica o dia</span>' :
              m.ocF[j] ? "" : '<span class="mudo">fora dos dias com furo</span>') + "</td></tr>";
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
        // o furo pendente num dia com falha de comunicação no COS sai em roxo: é o que a equipe tem de resolver
        // a da usina pinta todo furo do dia; a do inversor, só o dele (24/11/2026: o IPOA da Nova Xavantina 1 saía roxo)
        return rr ? (rr === "fora_op" ? "i" : "c") : (bs.indexOf(c) >= 0 && (m.com[i] || m.comI[i][e.nome]) ? "m" : c);
      });
    }
    if (m.ufv) ls.push({ nome: "Usina toda sem dado", itens: [m.ufv], cel: p.days.map(function (_d, i) { return Dset[i] ? (m.ufv.vr[i] ? (m.ufv.vr[i] === "fora_op" ? "i" : "c") : (m.com[i] ? "m" : "v")) : "n"; }) });
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
    Object.keys(t.vr).forEach(function (k) { ms[MOTC[t.vr[k]] || t.vr[k]] = 1; });
    if (t.ok) return '<span class="fr-okt">validado · ' + esc(Object.keys(ms).join(", ")) + "</span>";
    if (t.nv) return '<span class="fr-parc">' + t.nv + " de " + t.idx.length + " dias validados</span>";
    return '<span class="fr-pend">pendente</span>' + (s ? ' <span class="fr-sug" title="Sugestão do Nexus: ' + esc(MOTL[s[0]] + ". " + s[1]) + '">· sugestão: ' + esc(MOTC[s[0]]) + "</span>" : "");
  }
  function mapa(p, m, id) {
    var ls = linhasDoMapa(p, m, id), days = p.days, dsel = {}, isel = 0;
    MAPA[id] = ls.map(function (l) { return l.itens.map(function (t) { return t.nome; }); });
    m.items.forEach(function (t) { var ks = Object.keys(SEL[id + "|" + t.nome] || {}); if (ks.length) { isel++; ks.forEach(function (d) { dsel[d] = 1; }); } });
    var nsel = Object.keys(dsel).length;
    var sugN = m.pend.filter(function (t) { return suggest(p, t); }).length;
    var h = '<section class="fr-mapa"><div class="fr-mapa-topo"><h3 class="fr-h3">Mapa do mês</h3><div class="fr-chave">' +
      [["m", "Sem dado, com falha de comunicação no COS (da usina ou do próprio equipamento)"], ["v", "Sem dado"], ["z", "Zerado"], ["d", "IPOA só estimado"], ["a", "Valor anômalo"],
        ["e", "Justificado por queda"], ["o", "Coletado ou validado"], ["i", "Inoperante"]]
        .map(function (x) { return '<span><i class="fr-c fr-c-' + x[0] + '"></i>' + x[1] + "</span>"; }).join("") +
      '<span><i class="fr-c fr-c-qc"></i>Queda curta no COS (não justifica)</span><span><i class="fr-c fr-c-cos"></i>Outra ocorrência no COS</span></div>' +
      (sugN ? '<button type="button" class="gc-btn gc-btn--contorno fr-mini" data-a="sug" data-id="' + esc(id) + '" title="Aplica a sugestão do Nexus a cada item pendente que tem uma">Aceitar as sugestões (' + sugN + ")</button>" : "") +
      '<button type="button" class="gc-btn gc-btn--fantasma fr-mini" data-a="all" data-id="' + esc(id) + '">' + (TODOS.has(id) ? "Só os equipamentos com furo" : "Todos os equipamentos (" + p.eqs.length + ")") + "</button></div>";
    if (!ls.length && !(p.oc || []).length) return h + '<p class="mudo">Nenhum equipamento com furo ou parada neste mês.</p></section>';
    h += '<div class="fr-rola"><table class="fr-heat"><thead><tr><th></th>' + days.map(function (d) { return '<th class="gc-num">' + d + "</th>"; }).join("") + "</tr></thead><tbody>";
    if ((p.oc || []).length) {
      h += '<tr class="fr-heat-cos"><th>COS</th>' + days.map(function (d, i) {
        // a linha do COS pela causa: roxo, falha de comunicação; azul, queda que justifica (6 h ou mais de sol); contorno
        // azul, queda curta; cinza, outra ocorrência (string, tracker)
        var js = m.ocd[i], oc = p.oc, cls = !js.length ? "fr-c-nada" : js.some(function (j) { return ehCom(oc[j]); }) ? "fr-c-m" :
          js.some(function (j) { return oc[j][5] === "s" && solNoDia(p, j, d) >= 6; }) ? "fr-c-e" :
          js.some(function (j) { return oc[j][5] === "s"; }) ? "fr-c-qc" : "fr-c-cos";
        return '<td class="fr-c ' + cls + '"' +
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
  var KAN = [["com", "m", "Comunicação da usina", "dCom", "resolver com o COS e coletar"],
    ["comi", "k", "Comunicação no inversor", "dComI", "resolver com o COS e coletar o inversor"],
    ["semt", "s", "Usina toda sem dado", "dSemT", "sem justificativa no COS"],
    ["semp", "p", "Parcial", "dSemP", "um inversor ou alguns, sem justificativa"],
    ["etmo", "s fr-q--t", "Só IPOA ou GHI", "dEtm", "a geração está lá, falta a estação"],
    ["ok", "o", "Sem furo pendente", null, "completo, justificado ou validado"]];
  function colunaDe(m) {
    if (!m.dd) return "ok";
    var melhor = "com", n = -1;
    KAN.forEach(function (c) { if (c[3] && m[c[3]] > n) { n = m[c[3]]; melhor = c[0]; } });
    return melhor;
  }
  function desenharKanban(rows) {
    ordenar(rows);
    var por = {};
    rows.forEach(function (x) { (por[colunaDe(x.m)] = por[colunaDe(x.m)] || []).push(x); });
    $("fr-kanban").innerHTML = KAN.filter(function (c) { return c[0] !== "ok" || (por.ok || []).length; }).map(function (c) {
      var cs = por[c[0]] || [], dias = c[3] ? cs.reduce(function (a, x) { return a + x.m[c[3]]; }, 0) : 0;
      return '<section class="fr-kan-col"><header><i class="fr-q fr-q--' + c[1] + '" aria-hidden="true"></i><b>' + c[2] + '</b><span class="gc-num">' + cs.length + "</span>" +
        '<small class="mudo">' + c[4] + (dias ? " · " + dias + " dias" : "") + "</small></header>" +
        (cs.length ? cs.map(function (x) {
          var p = x.p, m = x.m;
          return '<button type="button" class="fr-kan-card" data-abrir="' + esc(rid(p)) + '"><span class="fr-kan-topo"><b>' + esc(p.usina) + '</b><span class="gc-num">' +
            (m.dd ? m.dd + (m.dd === 1 ? " dia" : " dias") : "ok") + '</span></span><small class="mudo">' + esc(p.cliente) + "</small>" + tira(p, m) +
            (m.dd ? '<small class="fr-kan-oque">' + esc(oQueFalta(m)) + "</small>" : "") + "</button>";
        }).join("") : '<p class="mudo fr-kan-vazio">Nenhuma usina.</p>') + "</section>";
    }).join("");
  }
  function desenharBDs() {
    var n = {};
    M().plants.forEach(function (p) { n[p.src] = (n[p.src] || 0) + 1; });
    $("fr-bds").innerHTML = BDS.map(function (b) {
      return '<button type="button" class="gc-chip" data-bd="' + b + '" aria-pressed="' + (b === BD) + '">' + b + ' <span class="mudo">' + (n[b] || 0) + " usinas</span></button>";
    }).join("");
  }
  function render() {
    if (!DB || !MONTH) return;
    desenharBDs();
    var todas = linhas(), rows = filtrar(todas);
    desenharLegenda(filtrar(todas, true));
    desenharFontes();
    desenharClientes(todas);
    $("fr-titulo-lista").textContent = "Usinas (" + rows.length + (rows.length !== todas.length ? " de " + todas.length : "") + ")";
    $("fr-caixa").hidden = VISAO !== "tabela"; $("fr-kanban").hidden = VISAO !== "kanban";
    [].forEach.call(document.querySelectorAll("[data-visao]"), function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-visao") === VISAO); });
    if (VISAO === "kanban") desenharKanban(rows); else desenharTabela(rows);
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
    var k = b.getAttribute("data-cli"), campo = campoCli(), sel = varios(campo);
    porValores(campo, sel.length === 1 && sel[0] === k ? [] : [k]);
  });
  $("fr-bds").addEventListener("click", function (e) {
    var b = e.target.closest("[data-bd]"); if (!b || b.getAttribute("data-bd") === BD) return;
    BD = b.getAttribute("data-bd");
    var k = "nexus.furos.bd"; try { localStorage.setItem(k, BD); } catch (x) {}
    ABERTAS.clear(); TODOS.clear(); OCTODAS.clear(); SEL = {};
    montarFiltros(true); render();
  });
  // o contador filtra pelo ponto dele; clicar de novo volta ao padrão (só o furo pendente)
  $("fr-legenda").addEventListener("click", function (e) {
    var b = e.target.closest("[data-sit]"); if (!b) return;
    var k = b.getAttribute("data-sit"), sel = varios("sit");
    porValores("sit", sel.length === 1 && sel[0] === k ? SIT_PADRAO : [k]);
  });
  [].forEach.call(document.querySelectorAll("[data-visao]"), function (b) {
    b.addEventListener("click", function () { VISAO = b.getAttribute("data-visao"); render(); });
  });
  // o cartão do Kanban abre a usina na tabela, no lugar dela
  $("fr-kanban").addEventListener("click", function (e) {
    var b = e.target.closest("[data-abrir]"); if (!b) return;
    var id = b.getAttribute("data-abrir");
    VISAO = "tabela"; ABERTAS.add(id); render();
    var tr = [].filter.call(document.querySelectorAll("tr.fr-linha"), function (x) { return x.getAttribute("data-id") === id; })[0];
    if (tr) tr.scrollIntoView({ block: "start" });
  });
  // a altura do cabeçalho fixo da lista vai para o CSS: o cabeçalho da tabela e o das colunas do Kanban prendem logo abaixo
  (function () {
    var cab = document.querySelector(".fr-cab-lista");
    function medir() { document.documentElement.style.setProperty("--fr-cab-h", (cab ? cab.offsetHeight : 0) + "px"); }
    if (cab && window.ResizeObserver) new ResizeObserver(medir).observe(cab);
    medir();
  })();
  // o bloco do tamanho por cliente lembra se a pessoa o recolheu
  (function () {
    var d = $("fr-dobra-cli"), k = "nexus.furos.clientes.aberto";
    try { if (localStorage.getItem(k) === "0") d.open = false; } catch (e) {}
    d.addEventListener("toggle", function () { try { localStorage.setItem(k, d.open ? "1" : "0"); } catch (e) {} });
  })();
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
