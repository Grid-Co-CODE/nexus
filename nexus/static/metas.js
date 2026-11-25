/* static/metas.js — Base › Metas das usinas (protótipo de 25/11/2026). A meta de 12 meses da usina do Registro mestre:
   a de agora (a salva no Nexus; sem ela, a da Info Mensal) em valores limpos; o Editar abre as células (digitar ou colar
   do Excel: o que se cola se espalha para a direita e para baixo); o PVsyst anexado entra já para editar. O que muda
   contra a meta de agora fica com borda até salvar. A usina e o ano se digitam (Levi, 25/11/2026: "Sempre que for fazer
   [...] um filtro, ele tem que ser digitável"). A regra: nexus/performance/metas_pvsyst.py. */
(function () {
  "use strict";
  var CFG = JSON.parse(document.getElementById("mt-config").textContent);
  var $ = function (id) { return document.getElementById(id); };
  var MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
  // as colunas: o campo, o título, as casas, o fator de exibição (o PR se mostra em %)
  var COLS = [["p50_mwh", "P50 (MWh)", 1, 1], ["p90_mwh", "P90 (MWh)", 1, 1], ["p75_mwh", "P75 (MWh)", 1, 1],
    ["pr", "PR (%)", 1, 100], ["ipoa_kwh_m2", "IPOA (kWh/m²)", 1, 1], ["ghi_kwh_m2", "GHI (kWh/m²)", 1, 1]];
  var U = null, PV = null, META = null, BASE = null, EDITAR = false;

  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function br(v, casas) { return v == null || isNaN(v) ? "" : Number(v).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }); }
  function sem(s) { return String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim(); }
  // "1.234,5" / "1234.5" / "73,6%" -> número; vazio -> null; texto -> NaN
  function num(t) {
    t = String(t == null ? "" : t).trim().replace(/%$/, "").replace(/\s/g, "");
    if (!t) return null;
    if (t.indexOf(",") >= 0 && t.indexOf(".") >= 0) t = t.lastIndexOf(",") > t.lastIndexOf(".") ? t.replace(/\./g, "").replace(",", ".") : t.replace(/,/g, "");
    else if (t.indexOf(",") >= 0) t = t.replace(",", ".");
    var v = Number(t);
    return isNaN(v) ? NaN : v;
  }
  function vazia() { var m = []; for (var i = 1; i <= 12; i++) { var x = { mes: i }; COLS.forEach(function (c) { x[c[0]] = null; }); m.push(x); } return m; }
  function copia(m) { return JSON.parse(JSON.stringify(m)); }
  function igual(a, b) { return (a == null && b == null) || (a != null && b != null && Math.abs(a - b) < 1e-6); }
  function estado(t, erro) { var e = $("mt-estado"); e.textContent = t || ""; e.className = "mt-estado" + (erro ? " mt-erro" : " mudo"); }
  function pedir(url, corpo) {
    var op = corpo instanceof FormData ? { method: "POST", body: corpo } :
      { method: "POST", headers: { "Content-Type": "application/json", "Accept": "application/json" }, body: JSON.stringify(corpo) };
    op.credentials = "same-origin";
    return fetch(url, op).then(function (r) { return r.json().catch(function () { return { ok: false, erro: "Resposta inesperada (" + r.status + ")." }; }); });
  }
  function mudados() {
    var n = 0;
    META.forEach(function (m, i) { COLS.forEach(function (c) { if (!igual(m[c[0]], (BASE[i] || {})[c[0]])) n++; }); });
    return n;
  }

  // ── a usina digitada: o rótulo inteiro, ou o único que tem todas as palavras ──────────────────────────────────────
  function resolver(texto) {
    var t = sem(texto);
    if (!t) return { id: "" };
    for (var i = 0; i < CFG.rotulos.length; i++) if (sem(CFG.rotulos[i]) === t) return { id: CFG.ids[i] };
    var p = t.split(" "), achou = [];
    CFG.rotulos.forEach(function (r, i) { var s = " " + sem(r) + " "; if (p.every(function (w) { return s.indexOf(w) >= 0; })) achou.push(i); });
    if (achou.length === 1) return { id: CFG.ids[achou[0]] };
    return { id: "", n: achou.length };
  }
  function rotuloDe(id) { var i = CFG.ids.indexOf(id); return i >= 0 ? CFG.rotulos[i] : ""; }

  // ── desenhar ─────────────────────────────────────────────────────────────────────────────────────────────────────
  function cabecalho() {
    var partes = [];
    if (U) {
      partes.push("<b>" + esc(U.usina) + "</b>");
      if (U.cliente) partes.push(esc(U.cliente));
      var s = U.salva;
      if (U.de_onde === "nexus") partes.push("meta " + U.ano + " salva no Nexus (" + esc(s.origem) + ", " + esc(s.salvo_em) + " · " + s.edicoes + " ediç" + (s.edicoes === 1 ? "ão" : "ões") + ")");
      else if (U.de_onde === "info_mensal") partes.push("meta " + U.ano + " da Info Mensal" + (sem(U.linha_info) !== sem(U.nome) ? " (linha “" + esc(U.linha_info) + "”)" : ""));
      else partes.push("sem meta " + U.ano + " no Nexus nem na Info Mensal");
    } else partes.push("<b>Escolha a usina</b> desta meta");
    if (EDITAR) { var n = mudados(); if (n) partes.push('<span class="mt-conta">' + n + " valor" + (n === 1 ? "" : "es") + " a salvar</span>"); }
    $("mt-sub").innerHTML = partes.join(" · ");
    var L = PV && PV.lido, itens = [];
    if (L) {
      itens.push('<li class="mt-pv"><i class="ph ph-file-pdf" aria-hidden="true"></i>PVsyst: ' + esc(L.projeto || PV.arquivo) + " · " + esc(L.versao || "?") +
        (L.simulado_em ? " de " + esc(L.simulado_em) : "") + (L.kwp ? " · " + br(L.kwp, 0) + " kWp" + (U && U.kwp ? " (Registro mestre: " + br(U.kwp, 0) + " kWp)" : "") : "") + "</li>");
      (L.conferencias || []).forEach(function (c) {
        itens.push('<li class="' + (c.ok ? "mt-ok" : "mt-falha") + '"><i class="ph ph-' + (c.ok ? "check-circle" : "warning-circle") + '" aria-hidden="true"></i>' + esc(c.texto) + "</li>");
      });
    }
    if (U && U.erro_meta) itens.push('<li class="mt-falha"><i class="ph ph-warning-circle" aria-hidden="true"></i>A Info Mensal não abriu (' + esc(U.erro_meta) + ").</li>");
    $("mt-confere").innerHTML = itens.join("");
  }
  function desenhar() {
    $("mt-leitura").hidden = false;
    cabecalho();
    var h = "<thead><tr><th>Mês" + (U ? " de " + U.ano : "") + "</th>" + COLS.map(function (c) { return "<th>" + c[1] + "</th>"; }).join("") + "</tr></thead><tbody>";
    META.forEach(function (m, i) {
      h += "<tr><th>" + MESES[m.mes] + "</th>" + COLS.map(function (c, j) {
        var v = m[c[0]], antes = (BASE[i] || {})[c[0]], mudou = !igual(v, antes);
        var txt = br(v == null ? null : v * c[3], c[2]);
        var dica = mudou ? ' title="Antes: ' + (antes == null ? "vazio" : br(antes * c[3], c[2])) + '"' : "";
        if (EDITAR) return '<td class="' + (mudou ? "mt-mudou" : "") + '"' + dica + '><input class="mt-cel" data-i="' + i + '" data-j="' + j + '" inputmode="decimal" value="' + txt + '" aria-label="' + c[1] + " de " + MESES[m.mes] + '"></td>';
        return '<td class="' + (mudou ? "mt-mudou" : "") + '"' + dica + ">" + (txt || '<span class="mudo">—</span>') + "</td>";
      }).join("") + "</tr>";
    });
    var tot = function (k) { var s = 0, ok = true; META.forEach(function (m) { if (m[k] == null) ok = false; else s += m[k]; }); return ok ? br(s, 1) : "—"; };
    h += "</tbody><tfoot><tr><th>Ano</th><td>" + tot("p50_mwh") + "</td><td>" + tot("p90_mwh") + "</td><td>" + tot("p75_mwh") + "</td><td></td><td></td><td></td></tr></tfoot>";
    $("mt-tabela").innerHTML = h;
    $("mt-tabela").classList.toggle("mt-editando", EDITAR);
    $("mt-editar").hidden = EDITAR || !U;
    $("mt-cancelar").hidden = !EDITAR;
    $("mt-salvar").hidden = !EDITAR;
    $("mt-salvar").disabled = !U;
  }

  // ── abrir a usina (e o ano) ──────────────────────────────────────────────────────────────────────────────────────
  function poeAnos(r) {
    $("mt-lista-anos").innerHTML = (r.anos || []).map(function (a) { return '<option value="' + a + '">'; }).join("");
    $("mt-ano").value = r.ano;
  }
  function abrir(id, ano) {
    var guardaPv = !!PV;              // o PDF anexado é do arquivo: trocar a usina (ou o ano) mantém os valores dele
    if (!guardaPv && EDITAR && META && mudados() && !window.confirm("Descartar o que mudou nesta meta?")) { if (U) { $("mt-usina").value = U.usina; $("mt-ano").value = U.ano; } return; }
    estado("Abrindo " + rotuloDe(id) + "…");
    pedir(CFG.abrir, { usina_id: id, ano: ano || null }).then(function (r) {
      if (!r.ok) { estado(r.erro || "Não consegui abrir.", true); return; }
      U = r; BASE = r.atual; $("mt-usina").value = r.usina; poeAnos(r);
      if (!guardaPv) { META = copia(BASE); EDITAR = false; }
      estado(""); desenhar();
    }, function () { estado("Sem conexão: nada foi aberto.", true); });
  }
  function escolherUsina() {
    var t = $("mt-usina").value, r = resolver(t);
    if (r.id) { if (!U || U.usina_id !== r.id) abrir(r.id, $("mt-ano").value); else $("mt-usina").value = U.usina; return; }
    if (!sem(t)) return;
    estado(r.n ? r.n + " usinas têm “" + t + "”: continue digitando ou escolha na lista." : "Nenhuma usina do Registro mestre com “" + t + "”.", true);
  }
  $("mt-usina").addEventListener("change", escolherUsina);
  $("mt-usina").addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); escolherUsina(); } });
  function escolherAno() {
    var a = parseInt($("mt-ano").value, 10);
    if (!U) return;
    if (!(a >= 2000 && a <= 2100)) { estado("Ano inválido: “" + $("mt-ano").value + "”.", true); $("mt-ano").value = U.ano; return; }
    if (a !== U.ano) abrir(U.usina_id, a);
  }
  $("mt-ano").addEventListener("change", escolherAno);
  $("mt-ano").addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); escolherAno(); } });

  // ── editar, colar do Excel, cancelar ─────────────────────────────────────────────────────────────────────────────
  $("mt-editar").addEventListener("click", function () {
    EDITAR = true; desenhar();
    var c = $("mt-tabela").querySelector(".mt-cel"); if (c) { c.focus(); c.select(); }
  });
  $("mt-cancelar").addEventListener("click", function () {
    PV = null; META = copia(BASE || vazia()); EDITAR = false; estado(""); desenhar();
    if (!U) $("mt-leitura").hidden = true;
  });
  // uma célula: grava o valor no estado (o PR digitado em % volta para fração)
  function poe(i, j, texto) {
    var c = COLS[j], v = num(texto);
    if (v !== null && isNaN(v)) return false;
    META[i][c[0]] = v === null ? null : Math.round(v / c[3] * 10000) / 10000;
    return true;
  }
  function focar(i, j) { var p = $("mt-tabela").querySelector('.mt-cel[data-i="' + i + '"][data-j="' + j + '"]'); if (p) { p.focus(); p.select(); } }
  $("mt-tabela").addEventListener("change", function (e) {
    var t = e.target; if (!t.classList.contains("mt-cel")) return;
    if (!poe(+t.dataset.i, +t.dataset.j, t.value)) { estado("Valor inválido: “" + t.value + "”.", true); t.focus(); return; }
    estado("");
    var a = document.activeElement, ai = a && a.dataset ? a.dataset.i : null, aj = a && a.dataset ? a.dataset.j : null;
    desenhar(); if (ai != null) focar(ai, aj);
  });
  $("mt-tabela").addEventListener("paste", function (e) {
    var t = e.target; if (!t.classList.contains("mt-cel")) return;
    var txt = (e.clipboardData || window.clipboardData).getData("text");
    if (!/[\t\n]/.test(txt.trim())) return;          // um valor só: o colar normal do campo
    e.preventDefault();
    var i0 = +t.dataset.i, j0 = +t.dataset.j, ruins = 0, n = 0;
    txt.replace(/\r/g, "").replace(/\n$/, "").split("\n").forEach(function (linha, di) {
      linha.split("\t").forEach(function (cel, dj) {
        var i = i0 + di, j = j0 + dj;
        if (i > 11 || j >= COLS.length) return;
        if (poe(i, j, cel)) n++; else ruins++;
      });
    });
    desenhar(); focar(i0, j0);
    estado(n + " célula" + (n === 1 ? "" : "s") + " colada" + (n === 1 ? "" : "s") + (ruins ? "; " + ruins + " com texto que não é número ficaram como estavam" : "") + ".", !!ruins);
  });
  $("mt-tabela").addEventListener("keydown", function (e) {
    var t = e.target; if (!t.classList.contains("mt-cel") || ["Enter", "ArrowDown", "ArrowUp"].indexOf(e.key) < 0) return;
    e.preventDefault();
    var i = +t.dataset.i + (e.key === "ArrowUp" ? -1 : 1), j = t.dataset.j;
    if (!poe(+t.dataset.i, +j, t.value)) { estado("Valor inválido: “" + t.value + "”.", true); return; }
    desenhar(); focar(Math.max(0, Math.min(11, i)), j);
  });

  // ── o PVsyst ─────────────────────────────────────────────────────────────────────────────────────────────────────
  $("mt-anexar").addEventListener("click", function () { $("mt-arquivo").click(); });
  $("mt-arquivo").addEventListener("change", function () {
    var f = this.files[0]; this.value = ""; if (!f) return;
    var fd = new FormData(); fd.append("arquivo", f, f.name);
    if (U) { fd.append("usina_id", U.usina_id); fd.append("ano", U.ano); }
    estado("Lendo " + f.name + "…");
    pedir(CFG.ler, fd).then(function (r) {
      if (!r.ok) { estado(r.erro || "Não consegui ler.", true); return; }
      var antes = U && U.usina_id;
      PV = r.pvsyst; META = copia(PV.meta); EDITAR = true;
      if (r.usina_id) {
        U = r; BASE = r.atual; $("mt-usina").value = r.usina; poeAnos(r);
        estado(antes && antes !== r.usina_id ? "O projeto do PDF é de " + r.usina + ": a meta abriu nela." : "");
      }
      else { U = null; BASE = vazia(); estado("O projeto do PDF não bateu com nenhuma usina: digite a usina.", true); $("mt-usina").focus(); }
      desenhar();
    }, function () { estado("Sem conexão: nada foi lido.", true); });
  });

  // ── salvar ───────────────────────────────────────────────────────────────────────────────────────────────────────
  $("mt-salvar").addEventListener("click", function () {
    if (!U) { estado("Escolha a usina antes de salvar.", true); $("mt-usina").focus(); return; }
    var k = PV && PV.lido ? PV.lido.kwp : null, kr = U.kwp;
    if (k && kr && Math.abs(k - kr) / kr > 0.05 && !window.confirm("O kWp do PVsyst (" + br(k, 0) + ") difere mais de 5% do Registro mestre de " +
        U.usina + " (" + br(kr, 0) + "). Confira se é o PDF desta usina. Salvar mesmo assim?")) return;
    var b = this; b.disabled = true;
    var sha = PV ? PV.sha : ((U.salva || {}).sha || ""), arq = PV ? PV.arquivo : ((U.salva || {}).arquivo || "");
    pedir(CFG.salvar, { usina_id: U.usina_id, ano: U.ano, meta: META, sha: sha, arquivo: arq }).then(function (r) {
      b.disabled = false;
      estado(r.ok ? r.aviso : (r.erro || "Não salvou."), !r.ok);
      if (r.ok) setTimeout(function () { location.href = location.pathname + "?usina=" + encodeURIComponent(U.usina_id) + "&ano=" + U.ano; }, 1800);
    }, function () { b.disabled = false; estado("Sem conexão: nada foi salvo.", true); });
  });

  [].forEach.call(document.querySelectorAll("[data-abrir]"), function (b) {
    b.addEventListener("click", function () { PV = null; abrir(b.getAttribute("data-abrir"), b.getAttribute("data-ano")); window.scrollTo(0, 0); });
  });
  // depois do Salvar (e num link): a usina e o ano voltam abertos
  var q = new URLSearchParams(location.search);
  if (q.get("usina") && CFG.ids.indexOf(q.get("usina")) >= 0) abrir(q.get("usina"), q.get("ano"));
})();
