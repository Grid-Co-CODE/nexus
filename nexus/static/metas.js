/* static/metas.js — Performance › Metas das usinas (protótipo de 25/11/2026). A meta de 12 meses numa grade editável: vem
   do PVsyst (o servidor lê o PDF: nexus/performance/metas_pvsyst.py), da meta salva, ou em branco; digita-se ou cola-se do
   Excel (as células coladas se espalham para a direita e para baixo, como lá). Embaixo de cada célula, em cinza, a meta de
   hoje da Info Mensal. A célula editada ganha borda. O Salvar manda as 12 linhas, e o servidor registra o que mudou. */
(function () {
  "use strict";
  var CFG = JSON.parse(document.getElementById("mt-config").textContent);
  var $ = function (id) { return document.getElementById(id); };
  var MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
  // as colunas: o campo, o título, as casas, o fator de exibição (o PR se mostra em %)
  var COLS = [["p50_mwh", "P50 (MWh)", 1, 1], ["p90_mwh", "P90 (MWh)", 1, 1], ["p75_mwh", "P75 (MWh)", 1, 1],
    ["pr", "PR (%)", 1, 100], ["ipoa_kwh_m2", "IPOA (kWh/m²)", 1, 1], ["ghi_kwh_m2", "GHI (kWh/m²)", 1, 1]];
  var D = null, META = null, BASE = null;
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function br(v, casas) { return v == null || isNaN(v) ? "" : Number(v).toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas }); }
  // "1.234,5" / "1234.5" / "73,6%" -> número; vazio -> null; texto -> NaN
  function num(t) {
    t = String(t == null ? "" : t).trim().replace(/%$/, "").replace(/\s/g, "");
    if (!t) return null;
    if (t.indexOf(",") >= 0 && t.indexOf(".") >= 0) t = t.lastIndexOf(",") > t.lastIndexOf(".") ? t.replace(/\./g, "").replace(",", ".") : t.replace(/,/g, "");
    else if (t.indexOf(",") >= 0) t = t.replace(",", ".");
    var v = Number(t);
    return isNaN(v) ? NaN : v;
  }
  function estado(t, erro) { var e = $("mt-estado"); e.textContent = t || ""; e.className = "mt-estado" + (erro ? " mt-erro" : " mudo"); }
  function pedir(url, corpo) {
    var op = corpo instanceof FormData ? { method: "POST", body: corpo } :
      { method: "POST", headers: { "Content-Type": "application/json", "Accept": "application/json" }, body: JSON.stringify(corpo) };
    op.credentials = "same-origin";
    return fetch(url, op).then(function (r) { return r.json().catch(function () { return { ok: false, erro: "Resposta inesperada (" + r.status + ")." }; }); });
  }
  function anos(lista, ano) { $("mt-ano").innerHTML = lista.map(function (a) { return '<option value="' + a + '"' + (a === ano ? " selected" : "") + ">" + a + "</option>"; }).join(""); }
  function usina(u) {
    var s = $("mt-usina");
    if (u && ![].some.call(s.options, function (o) { return o.value === u; })) s.insertAdjacentHTML("beforeend", '<option value="' + esc(u) + '">' + esc(u) + "</option>");
    s.value = u || "";
  }
  function copia(m) { return JSON.parse(JSON.stringify(m)); }
  function igual(a, b) { return (a == null && b == null) || (a != null && b != null && Math.abs(a - b) < 1e-6); }

  function cabecalho() {
    var L = D.lido, partes = [];
    if (L) partes.push("<b>" + esc(L.projeto || D.arquivo) + "</b>", "PVsyst " + esc(L.versao || "?") + (L.simulado_em ? " de " + esc(L.simulado_em) : ""),
      L.kwp ? br(L.kwp, 0) + " kWp no PVsyst" + (D.kwp_hoje ? " · " + br(D.kwp_hoje, 0) + " kWp na Info Geral" : "") : "");
    else partes.push("<b>" + (D.origem === "manual" ? "Meta à mão" : "Meta salva") + "</b>", "digite ou cole do Excel");
    if (D.edicoes) partes.push(D.edicoes + " edição(ões) registrada(s)");
    $("mt-sub").innerHTML = partes.filter(Boolean).join(" · ");
    $("mt-confere").innerHTML = ((L && L.conferencias) || []).map(function (c) {
      return '<li class="' + (c.ok ? "mt-ok" : "mt-falha") + '"><i class="ph ph-' + (c.ok ? "check-circle" : "warning-circle") + '" aria-hidden="true"></i>' + esc(c.texto) + "</li>";
    }).join("") + (D.erro_meta ? '<li class="mt-falha"><i class="ph ph-warning-circle" aria-hidden="true"></i>A meta de hoje não foi lida (' + esc(D.erro_meta) + ").</li>" : "");
  }
  function hojeTxt(h, c) {
    var v = (h || {})[c[0]], m = META[h ? h.mes - 1 : 0];
    if (v == null) return '<small class="mudo">—</small>';
    var d = m && m[c[0]] != null && v ? (m[c[0]] - v) / v * 100 : null;
    return '<small class="mudo">' + br(v * c[3], c[2]) + (d != null && Math.abs(d) >= 2 ? ' <span class="mt-dif ' + (d > 0 ? "mt-dif--mais" : "mt-dif--menos") + '">' + (d > 0 ? "+" : "") + br(d, 1) + "%</span>" : "") + "</small>";
  }
  function desenhar() {
    $("mt-leitura").hidden = false;
    cabecalho();
    var h = '<thead><tr><th>Mês de ' + D.ano + "</th>" + COLS.map(function (c) { return "<th>" + c[1] + "</th>"; }).join("") + "</tr></thead><tbody>";
    META.forEach(function (m, i) {
      var hoje = (D.hoje || [])[i];
      h += "<tr><th>" + MESES[m.mes] + "</th>" + COLS.map(function (c, j) {
        var ed = !igual(m[c[0]], (BASE[i] || {})[c[0]]);
        return '<td><input class="mt-cel' + (ed ? " mt-editada" : "") + '" data-i="' + i + '" data-j="' + j + '" inputmode="decimal" value="' + br(m[c[0]] == null ? null : m[c[0]] * c[3], c[2]) + '"' +
          (ed ? ' title="Antes: ' + (BASE[i][c[0]] == null ? "vazio" : br(BASE[i][c[0]] * c[3], c[2])) + '"' : "") + ' aria-label="' + c[1] + " de " + MESES[m.mes] + '">' + hojeTxt(hoje, c) + "</td>";
      }).join("") + "</tr>";
    });
    var tot = function (k) { var s = 0, ok = true; META.forEach(function (m) { if (m[k] == null) ok = false; else s += m[k]; }); return ok ? s : null; };
    var th = 0, hok = (D.hoje || []).length === 12;
    (D.hoje || []).forEach(function (x) { if (x.p50_mwh == null) hok = false; else th += x.p50_mwh; });
    h += "</tbody><tfoot><tr><th>Ano</th><td><b>" + br(tot("p50_mwh"), 1) + "</b><small class=\"mudo\">" + (hok ? br(th, 1) : "—") + "</small></td><td><b>" + br(tot("p90_mwh"), 1) + "</b></td><td><b>" + br(tot("p75_mwh"), 1) + "</b></td><td colspan=\"3\"></td></tr></tfoot>";
    $("mt-tabela").innerHTML = h;
    $("mt-salvar").disabled = !$("mt-usina").value;
  }
  function carregar(r, manterMeta) {
    if (!r.ok) { estado(r.erro || "Não consegui.", true); return; }
    var editado = manterMeta && META ? META : null;
    D = r; usina(r.usina); anos(r.anos, r.ano);
    META = editado || copia(r.meta); BASE = editado ? BASE : copia(r.meta);
    estado(""); desenhar();
  }
  // uma célula: grava o valor no estado (o PR digitado em % volta para fração)
  function poe(i, j, texto) {
    var c = COLS[j], v = num(texto);
    if (v !== null && isNaN(v)) return false;
    META[i][c[0]] = v === null ? null : Math.round(v / c[3] * 10000) / 10000;
    return true;
  }
  $("mt-tabela").addEventListener("change", function (e) {
    var t = e.target; if (!t.classList.contains("mt-cel")) return;
    if (!poe(+t.dataset.i, +t.dataset.j, t.value)) { estado("Valor inválido: “" + t.value + "”.", true); t.focus(); return; }
    estado(""); desenhar();
    var prox = $("mt-tabela").querySelector('.mt-cel[data-i="' + t.dataset.i + '"][data-j="' + t.dataset.j + '"]'); if (prox) prox.blur();
  });
  // colar do Excel: linhas por quebra, células por tabulação, a partir da célula onde se colou
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
    desenhar();
    estado(n + " célula(s) colada(s)" + (ruins ? "; " + ruins + " com texto que não é número ficaram como estavam" : "") + ".", !!ruins);
  });
  $("mt-tabela").addEventListener("keydown", function (e) {
    var t = e.target; if (!t.classList.contains("mt-cel") || (e.key !== "Enter" && e.key !== "ArrowDown" && e.key !== "ArrowUp")) return;
    e.preventDefault();
    var i = +t.dataset.i + (e.key === "ArrowUp" ? -1 : 1), j = t.dataset.j;
    t.dispatchEvent(new Event("change", { bubbles: true }));
    var p = $("mt-tabela").querySelector('.mt-cel[data-i="' + i + '"][data-j="' + j + '"]'); if (p) { p.focus(); p.select(); }
  });

  $("mt-anexar").addEventListener("click", function () { $("mt-arquivo").click(); });
  $("mt-arquivo").addEventListener("change", function () {
    var f = this.files[0]; this.value = ""; if (!f) return;
    var fd = new FormData(); fd.append("arquivo", f, f.name);
    estado("Lendo " + f.name + "…");
    pedir(CFG.ler, fd).then(function (r) { carregar(r, false); if (r.ok && !r.usina) estado("O nome do projeto não bateu com nenhuma usina: escolha a usina.", true); },
      function () { estado("Sem conexão: nada foi lido.", true); });
  });
  function abrir(u) {
    if (!u) { estado("Escolha a usina.", true); return; }
    estado("Abrindo " + u + "…");
    pedir(CFG.abrir, { usina: u, ano: +$("mt-ano").value || null }).then(function (r) { carregar(r, false); });
  }
  $("mt-manual").addEventListener("click", function () { abrir($("mt-usina").value); });
  [].forEach.call(document.querySelectorAll("[data-abrir]"), function (b) {
    b.addEventListener("click", function () { usina(b.getAttribute("data-abrir")); abrir(b.getAttribute("data-abrir")); window.scrollTo(0, 0); });
  });
  // trocar a usina ou o ano com a grade aberta: só a meta de hoje muda, o que está na grade fica
  function trocar() {
    if (!D) { if ($("mt-usina").value) abrir($("mt-usina").value); return; }
    pedir(CFG.hoje, { usina: $("mt-usina").value, ano: +$("mt-ano").value || null }).then(function (r) {
      if (!r.ok) return;
      D.usina = r.usina; D.ano = r.ano; D.anos = r.anos; D.hoje = r.hoje; D.kwp_hoje = r.kwp_hoje; D.erro_meta = r.erro_meta;
      anos(r.anos, r.ano); desenhar();
    });
  }
  $("mt-usina").addEventListener("change", trocar);
  $("mt-ano").addEventListener("change", trocar);
  $("mt-salvar").addEventListener("click", function () {
    if (!D || !$("mt-usina").value) return;
    var k = (D.lido || {}).kwp, kh = D.kwp_hoje;
    if (k && kh && Math.abs(k - kh) / kh > 0.05 && !window.confirm("O kWp do PVsyst (" + br(k, 0) + ") difere mais de 5% do da Info Geral de " +
        $("mt-usina").value + " (" + br(kh, 0) + "). Confira se é o PDF desta usina. Salvar mesmo assim?")) return;
    var b = this; b.disabled = true;
    pedir(CFG.salvar, { usina: $("mt-usina").value, ano: +$("mt-ano").value, meta: META, sha: D.sha || "", arquivo: D.arquivo || "" }).then(function (r) {
      b.disabled = false;
      estado(r.ok ? r.aviso : (r.erro || "Não salvou."), !r.ok);
      if (r.ok) setTimeout(function () { location.reload(); }, 2200);
    }, function () { b.disabled = false; estado("Sem conexão: nada foi salvo.", true); });
  });
})();
