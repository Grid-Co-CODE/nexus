// nexus/static/pcm-quadro-filtros.js — os filtros do Quadro da semana no modelo A do Histórico de OS (16/11/2026, Levi:
// "Quadro da semana quero os filtros no mesmo padrão de qualidade e funcionalidades do filtro de Histórico de OS > OS
// Creator!"). O HTML está no templates/pcm/quadro.html; as linhas da cascata, no `quadro.painel_filtros` (#qf_dados).
//  - O botão Filtros abre o painel. Nada vai ao servidor antes do Aplicar; fechar sem aplicar (Esc, clique fora, o botão
//    de novo, o × da folha do celular) devolve o que está aplicado. O × de uma etiqueta é um link (o endereço de agora
//    sem aquele filtro): o clique fora descarta antes, e o que estava escolhido no painel não vai junto.
//  - A cascata é recontada a cada marca: cada opção conta as tarefas que passam pelos OUTROS campos (o filtro não conta a
//    si mesmo, como o `quadro.opcoes`), e as OS da FAMA à parte ("+N FAMA"). Sem tarefa e sem FAMA, a opção some; a
//    marcada nunca some (a tela não esconde o filtro que vale).
//  - Cada lista tem a caixa de busca no topo: sem acento e sem caixa, palavra por palavra, setas, Enter marca, Esc fecha a
//    lista. É o contrato do os_busca.js do OS Creator, que não é carregado aqui: ele transformaria em campo de busca todo
//    <select> comprido da página (a janela de reprogramar). A busca da lista esconde por classe (qf-fora); o [hidden] é
//    da cascata, como no Histórico.
//  - O Enter na busca de texto manda o formulário com o que está aplicado.
(function () {
  "use strict";
  var form = document.querySelector("[data-q-barra]"), painel = document.getElementById("qf_painel");
  if (!form || !painel) return;
  var dadosEl = document.getElementById("qf_dados");
  var D = {};
  try { D = JSON.parse((dadosEl && dadosEl.textContent) || "{}"); } catch (e) { D = {}; }
  var CAMPOS = D.campos || [], VALORES = D.valores || {};
  var botao = document.getElementById("qf_botao"), veu = document.getElementById("qf_veu"), barra = document.getElementById("qf_barra");
  var bAplicar = document.getElementById("qf_aplicar"), nAlt = document.getElementById("qf_nalt"), busca = document.getElementById("q");
  var aberto = false;
  var cada = function (lista, f) { Array.prototype.forEach.call(lista, f); };
  var todos = function (raiz, sel) { return Array.prototype.slice.call(raiz.querySelectorAll(sel)); };

  // sem acento, sem caixa e com os espaços colapsados; cada palavra digitada tem de aparecer no texto, em qualquer ordem
  function norm(s) { return String(s == null ? "" : s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim(); }
  function casa(texto, filtro) { var t = norm(texto); return norm(filtro).split(" ").every(function (p) { return t.indexOf(p) >= 0; }); }

  function lista(campo) { return form.querySelector('details[data-nome="' + campo + '"]'); }
  function caixas(campo) { var d = lista(campo); return d ? todos(d, "input[type=checkbox]") : []; }
  function marcados(campo) { return caixas(campo).filter(function (c) { return c.checked; }).map(function (c) { return c.value; }); }
  function escolhido() { var o = {}; CAMPOS.forEach(function (c) { o[c] = marcados(c).sort(); }); return o; }
  var aplicado = escolhido();                                      // o que a página trouxe marcado é o que o servidor aplicou

  // ── a cascata ──
  function reconta() {
    var quer = CAMPOS.map(function (c) {                           // os índices marcados de cada campo (null = sem filtro)
      var m = marcados(c), vals = VALORES[c] || [];
      if (!m.length) return null;
      var idx = {};
      m.forEach(function (v) { var i = vals.indexOf(v); if (i >= 0) idx[i] = true; });
      return idx;
    });
    // a linha que passa por todos os campos conta em todos; a que falha num só conta só nele (o campo não filtra a si mesmo)
    function contar(linhas) {
      var contas = CAMPOS.map(function () { return {}; });
      (linhas || []).forEach(function (l) {
        var falhas = 0, onde = -1;
        for (var k = 0; k < CAMPOS.length && falhas < 2; k++) if (quer[k] && !quer[k][l[k]]) { falhas++; onde = k; }
        if (falhas === 0) for (var j = 0; j < CAMPOS.length; j++) contas[j][l[j]] = (contas[j][l[j]] || 0) + 1;
        else if (falhas === 1) contas[onde][l[onde]] = (contas[onde][l[onde]] || 0) + 1;
      });
      return contas;
    }
    var tarefas = contar(D.linhas), fama = contar(D.fora);
    CAMPOS.forEach(function (c, k) {
      var d = lista(c), vals = VALORES[c] || [];
      if (!d) return;
      todos(d, ".qf-op").forEach(function (l) {
        var cx = l.querySelector("input"), i = vals.indexOf(cx.value);
        var n = i >= 0 ? (tarefas[k][i] || 0) : 0, f = i >= 0 ? (fama[k][i] || 0) : 0;
        l.querySelector(".gc-num").textContent = String(n);
        var fe = l.querySelector(".q-ms-fama");
        if (fe) { fe.textContent = f ? "+" + f + " FAMA" : ""; fe.hidden = !f; }
        l.hidden = !(n || f || cx.checked);
      });
      vazio(d);
    });
  }
  function vazio(d) {                                              // a lista sem nada para mostrar diz por quê
    var p = d.querySelector(".qf-vazio"), b = d.querySelector(".qf-lista-busca");
    if (!p) return;
    var algum = todos(d, ".qf-op").some(function (l) { return !l.hidden && !l.classList.contains("qf-fora"); });
    var f = b ? b.value : "";
    p.hidden = algum;
    p.textContent = norm(f) ? "Nenhuma opção tem “" + f.trim() + "”." : "Nada para escolher com os outros filtros.";
  }

  // ── o texto de cada campo, o ponto do que mudou e o Aplicar ──
  function resumo(campo) {
    var d = lista(campo); if (!d) return;
    var txt = d.querySelector(".qf-multi-txt"), m = marcados(campo);
    txt.textContent = !m.length ? txt.getAttribute("data-todos") : (m.length === 1 ? m[0] : m.length + " " + txt.getAttribute("data-plural"));
    d.title = m.join("\n");
    d.classList.toggle("qf-tem", m.length > 0);
  }
  function acende() {
    var agora = escolhido(), n = 0;
    CAMPOS.forEach(function (c) {
      var mudou = JSON.stringify(agora[c]) !== JSON.stringify(aplicado[c]);
      var cel = form.querySelector('.qf-cel[data-filtro="' + c + '"]');
      if (cel) cel.classList.toggle("mudou", mudou);
      if (mudou) n++;
    });
    bAplicar.disabled = n === 0;
    nAlt.textContent = n === 0 ? "Sem alterações" : n + (n === 1 ? " alteração" : " alterações");
  }
  function tudo() { reconta(); CAMPOS.forEach(resumo); acende(); }
  function poe(valores) {                                          // as caixas no estado `valores` ({campo: [valor]})
    CAMPOS.forEach(function (c) { caixas(c).forEach(function (cx) { cx.checked = (valores[c] || []).indexOf(cx.value) >= 0; }); });
  }

  // ── as listas digitáveis ──
  CAMPOS.forEach(function (c) {
    var d = lista(c); if (!d) return;
    var b = d.querySelector(".qf-lista-busca"), marcado = -1;
    var linhas = function () { return todos(d, ".qf-op"); };
    var visiveis = function () { return linhas().filter(function (l) { return !l.hidden && !l.classList.contains("qf-fora"); }); };
    function marcar(k) {
      var vis = visiveis();
      marcado = vis.length && k >= 0 ? Math.min(vis.length - 1, k) : -1;
      linhas().forEach(function (l) { l.classList.remove("on"); });
      if (marcado < 0) return;
      var l = vis[marcado], caixa = d.querySelector(".qf-lista"), topo = (b ? b.offsetHeight : 0) + 8;
      l.classList.add("on");
      if (!caixa) return;                                           // rola só a lista (scrollIntoView rolaria a página)
      if (l.offsetTop - topo < caixa.scrollTop) caixa.scrollTop = Math.max(0, l.offsetTop - topo);
      else if (l.offsetTop + l.offsetHeight > caixa.scrollTop + caixa.clientHeight) caixa.scrollTop = l.offsetTop + l.offsetHeight - caixa.clientHeight;
    }
    function filtra() {
      var f = b ? b.value : "";
      linhas().forEach(function (l) { var s = l.querySelector("span"); l.classList.toggle("qf-fora", !casa(s ? s.textContent : "", f)); });
      vazio(d);
      marcar(norm(f) ? 0 : -1);
    }
    caixas(c).forEach(function (cx) { cx.addEventListener("change", tudo); });
    if (b) {
      b.addEventListener("input", filtra);
      b.addEventListener("keydown", function (e) {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          marcar(marcado < 0 ? 0 : Math.max(0, marcado + (e.key === "ArrowDown" ? 1 : -1)));
        } else if (e.key === "Enter") {
          e.preventDefault();                                       // o Enter marca e desmarca; nunca manda o formulário
          var l = visiveis()[marcado], cx = l && l.querySelector("input[type=checkbox]");
          if (cx) cx.click();
        } else if (e.key === "Escape") {
          e.preventDefault(); e.stopPropagation();                  // só a lista fecha; o Esc seguinte fecha o painel
          d.open = false;
          var s = d.querySelector("summary"); if (s) s.focus();
        }
      });
    }
    d.addEventListener("toggle", function () {
      if (d.open) {
        CAMPOS.forEach(function (o) { var x = lista(o); if (x && x !== d && x.open) x.open = false; });
        filtra();
        // no computador a busca já abre com o foco; no celular não (o teclado cobriria metade da lista)
        if (b && window.matchMedia && window.matchMedia("(pointer: fine)").matches) b.focus({preventScroll: true});
      } else if (b && b.value) { b.value = ""; filtra(); }
    });
  });
  // o clique fora de uma lista aberta a fecha (dentro do painel também: a lista do lado)
  document.addEventListener("click", function (e) {
    todos(form, "details.qf-multi[open]").forEach(function (d) { if (!d.contains(e.target)) d.open = false; });
  });

  // ── o painel ──
  function celular() { return !!(window.matchMedia && window.matchMedia("(max-width: 639px)").matches); }
  function posiciona() {                                           // PC: a borda esquerda do painel na do botão, sem sair da barra
    if (celular()) { painel.style.left = ""; return; }              // celular: o CSS faz dele uma folha de baixo
    var c = barra.getBoundingClientRect(), r = botao.getBoundingClientRect(), w = painel.offsetWidth;
    painel.style.left = Math.max(0, Math.min(Math.round(r.left - c.left), Math.round(c.width - w))) + "px";
  }
  function abre() {
    painel.hidden = false; veu.hidden = false; aberto = true;
    botao.setAttribute("aria-expanded", "true");
    posiciona();
    painel.focus();
  }
  function descarta() {
    poe(aplicado);
    todos(form, ".qf-lista-busca").forEach(function (b) { b.value = ""; });
    todos(form, ".qf-op.qf-fora").forEach(function (l) { l.classList.remove("qf-fora"); });
    tudo();
  }
  function fecha(descartar) {
    if (!aberto) return;
    if (descartar) descarta();
    todos(painel, "details[open]").forEach(function (d) { d.open = false; });
    painel.hidden = true; veu.hidden = true; aberto = false;
    botao.setAttribute("aria-expanded", "false");
  }
  botao.addEventListener("click", function () { if (aberto) fecha(true); else abre(); });
  document.getElementById("qf_fechar").addEventListener("click", function () { fecha(true); botao.focus(); });
  // o clique fora descarta ANTES de qualquer outro clique da página agir (captura): o × de uma etiqueta, uma semana, um cartão
  document.addEventListener("click", function (e) {
    if (aberto && !painel.contains(e.target) && !botao.contains(e.target)) fecha(true);
  }, true);
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || !aberto) return;
    var l = painel.querySelector("details[open]");                  // o Esc fecha só a lista; com ela fechada, o painel
    if (l) { l.open = false; var s = l.querySelector("summary"); if (s) s.focus(); return; }
    fecha(true); botao.focus();
  });
  document.getElementById("qf_limpar").addEventListener("click", function () {   // zera o painel e espera o Aplicar
    poe({}); tudo();
  });
  bAplicar.addEventListener("click", function () {
    fecha(false);
    form.submit();
  });
  // o Enter na busca manda o que está aplicado: o que o painel tinha escolhido sem Aplicar volta antes
  if (busca) busca.addEventListener("keydown", function (e) {
    if (e.key !== "Enter") return;
    e.preventDefault();
    fecha(true);
    form.submit();
  });

  tudo();
})();
