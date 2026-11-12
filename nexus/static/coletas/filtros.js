/* Os filtros dos Furos de coleta (Performance > Coletas) no modelo A do Histórico de OS (Levi, 12/11/2026: "arrume esses
   filtros para ficar no padrão exatamente dos filtros de Histórico de OS com o mesmo estilo e funcionalidades!"). O modelo
   (nexus/torres/oscreator/README.md, "Os filtros do Histórico só valem no Aplicar"): a busca por texto fica na barra e filtra
   enquanto se digita; o botão Filtros, com a contagem em verde dos aplicados (a busca não conta), abre o painel suspenso; cada
   campo é uma lista digitável de MARCAR VÁRIOS (nenhum marcado = todos); nada filtra antes do Aplicar; o campo que mudou ganha
   o ponto; as etiquetas azuis dos aplicados ficam abaixo da barra, o × tira aquele filtro na hora e o "Limpar tudo" tira o
   resto e a busca; fechar sem aplicar (Esc, clique fora, o botão de novo) descarta. O CSS é o mesmo da Zeladoria
   (static/zeladoria/filtros.css, as classes zf-*), que copiou o do Histórico.

   Por que de fora: a tela dos Furos é GERADA do furos.js do Conversor (ferramentas/portar_tela_conversor.py), e o estado dela
   mora dentro de uma função. Então esta peça só mexe no DOM: esconde os campos do .exe (os <select> viram `multiple`), monta a
   barra e o painel, e no Aplicar marca as opções nos campos escondidos e dispara o mesmo `change` que a pessoa dispararia. O
   furos.js (com a troca da geração) lê os vários valores e chama `coletasFiltros.atualizar()` ao fim de cada desenho. */
(function (w, d) {
  "use strict";
  // os campos do painel, na ordem da tela do .exe; o rótulo é o do .exe
  var LISTAS = [["fzCli", "Cliente"], ["fzCart", "Carteira (Thopen)"], ["fzSrc", "Fonte"], ["fzSt", "Status da usina"],
                ["fzSit", "Situação"]];
  // as três chaves do .exe mudam a CONTA (não escolhem linhas): no painel, como marcas, e etiqueta só quando desligadas
  var MARCAS = [["fzZero", "Contar zerado como furo"], ["fzOS", "OS/ticket de desligamento = ausência esperada"],
                ["fzConf", "Confirmados contam como OK"]];
  var SVG = {
    busca: '<svg class="zf-ico" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>',
    filtro: '<svg class="zf-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4"/></svg>',
    seta: '<svg class="zf-ico zf-seta" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>',
    x: '<svg class="zf-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>'
  };
  var $ = function (id) { return d.getElementById(id); };
  var aberto = null;             // {pend: {campo: valor}} do painel aberto
  var barra, ancora, botao, etiquetas;

  function sem(s) { return String(s == null ? "" : s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim(); }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function el(html) { var t = d.createElement("template"); t.innerHTML = html.trim(); return t.content.firstChild; }
  function igual(a, b) { return JSON.stringify(a) === JSON.stringify(b); }

  // ── o estado de agora, lido dos campos escondidos do .exe ─────────────────────────────────────────────────────
  function opcoes(id) {
    return [].filter.call($(id).options, function (o) { return o.value !== ""; })
      .map(function (o) { return { v: o.value, t: o.textContent.trim() }; });
  }
  function campos() {
    return LISTAS.map(function (x) {
      return { chave: x[0], rotulo: x[1], tipo: "varios", opcoes: opcoes(x[0]), padrao: [],
               atual: [].filter.call($(x[0]).options, function (o) { return o.selected && o.value !== ""; }).map(function (o) { return o.value; }) };
    }).concat(MARCAS.map(function (x) {
      return { chave: x[0], rotulo: x[1], tipo: "marca", padrao: true, atual: $(x[0]).checked };
    }));
  }
  function aplicados() { return campos().filter(function (c) { return !igual(c.atual, c.padrao); }); }
  function resumo(c, v) {
    if (c.tipo === "marca") return v ? "sim" : "não";
    if (!v.length) return "Todos";
    if (v.length === 1) return (c.opcoes.filter(function (o) { return o.v === v[0]; })[0] || { t: v[0] }).t;
    return v.length + " selecionados";
  }

  // ── a barra: a busca, o botão Filtros e, à direita, a contagem; embaixo, as etiquetas ───────────────────────────
  function montar() {
    var corpo = $("fzCorpo"), caixa = corpo && corpo.querySelector(".box");
    if (!caixa || barra) return;
    LISTAS.forEach(function (x) { $(x[0]).multiple = true; [].forEach.call($(x[0]).options, function (o) { o.selected = false; }); });
    barra = el('<div class="zf-barra cf-barra"></div>');
    var busca = el('<label class="cf-busca" title="Filtra as usinas pelo nome">' + SVG.busca + "</label>");
    var q = $("fzQ");
    q.placeholder = "Buscar usina…";
    q.setAttribute("aria-label", "Buscar usina");
    busca.appendChild(q);
    ancora = el('<span class="zf-ancora"><button type="button" class="zf-btn" aria-expanded="false" aria-haspopup="dialog">' +
      SVG.filtro + 'Filtros <span class="zf-badge" hidden></span></button></span>');
    botao = ancora.firstChild;
    botao.addEventListener("click", function () { if (aberto) fechar(); else abrir(); });
    var dir = el('<span class="cf-dir"></span>');
    dir.appendChild($("fzContagem"));
    barra.appendChild(busca);
    barra.appendChild(ancora);
    barra.appendChild(dir);
    etiquetas = el('<div class="zf-etiquetas cf-etiquetas" role="group" aria-label="Filtros aplicados" hidden></div>');
    caixa.classList.add("cf-oculto");
    caixa.insertAdjacentElement("beforebegin", barra);
    barra.insertAdjacentElement("afterend", etiquetas);
    atualizar();
  }

  function atualizar() {
    if (!barra) return;
    var lista = aplicados();
    var badge = botao.querySelector(".zf-badge");
    badge.hidden = !lista.length;
    badge.textContent = lista.length;
    etiquetas.innerHTML = "";
    var busca = $("fzQ").value.trim(), colunas = d.querySelectorAll("#fzTb [data-cf]");
    var temColuna = [].some.call(colunas, function (x) { return x.value !== ""; });
    lista.forEach(function (c) {
      var chip = el('<span class="zf-chip"><i>' + esc(c.rotulo) + '</i> <span class="zf-chip-v">' + esc(resumo(c, c.atual)) +
        '</span><button type="button" class="zf-chip-x" title="Tirar este filtro" aria-label="Tirar o filtro ' + esc(c.rotulo) +
        '">' + SVG.x + "</button></span>");
      chip.querySelector("button").addEventListener("click", function () { var p = {}; p[c.chave] = c.padrao; aplicar(p); });
      etiquetas.appendChild(chip);
    });
    // o Limpar tudo só aparece quando há o que limpar (como no Histórico): os filtros, a busca e os da coluna da tabela
    if (lista.length || busca || temColuna) {
      var tudo = el('<button type="button" class="zf-link">Limpar tudo</button>');
      tudo.addEventListener("click", limparTudo);
      etiquetas.appendChild(tudo);
    }
    etiquetas.hidden = !etiquetas.children.length;
  }

  function limparTudo() {
    var p = {};
    campos().forEach(function (c) { p[c.chave] = c.padrao; });
    aplicar(p, true);
    $("fzLimpar").click();              // o Limpar filtros do .exe: a busca e os filtros da coluna da tabela
  }

  // ── o painel ─────────────────────────────────────────────────────────────────────────────────────────────────
  function abrir() {
    fechar();
    var cs = campos(), pend = {};
    cs.forEach(function (c) { pend[c.chave] = c.atual; });
    aberto = { pend: pend, campos: cs };
    var painel = el('<div class="zf-painel" role="dialog" aria-label="Filtros" tabindex="-1">' +
      '<div class="zf-painel-topo"><h4>Filtros</h4><button type="button" class="zf-fechar" aria-label="Fechar sem aplicar" ' +
      'title="Fechar sem aplicar">' + SVG.x + '</button></div><div class="zf-painel-corpo"><div class="zf-grade"></div></div>' +
      '<div class="zf-rodape"><button type="button" class="zf-btn zf-fantasma" data-zf-limpar>Limpar</button>' +
      '<div class="zf-dir"><span data-zf-n aria-live="polite"></span><button type="button" class="zf-btn zf-lima" data-zf-aplicar>' +
      "Aplicar</button></div></div></div>");
    var grade = painel.querySelector(".zf-grade");
    cs.forEach(function (c) { grade.appendChild(celula(c)); });
    var veu = el('<div class="zf-veu"></div>');
    veu.addEventListener("click", fechar);
    ancora.appendChild(painel);
    d.body.appendChild(veu);
    botao.setAttribute("aria-expanded", "true");
    painel.querySelector(".zf-fechar").addEventListener("click", fechar);
    painel.querySelector("[data-zf-limpar]").addEventListener("click", function () {
      cs.forEach(function (c) { aberto.pend[c.chave] = c.padrao; });
      redesenhar();
    });
    painel.querySelector("[data-zf-aplicar]").addEventListener("click", function () {
      var p = {};
      cs.forEach(function (c) { if (!igual(aberto.pend[c.chave], c.atual)) p[c.chave] = aberto.pend[c.chave]; });
      fechar();
      aplicar(p);
    });
    var r = painel.getBoundingClientRect();
    if (r.right > d.documentElement.clientWidth - 8) painel.classList.add("zf-direita");
    painel.focus();
    function redesenhar() {
      [].forEach.call(grade.children, function (cel, i) { pintar(cel, cs[i]); });
      var n = cs.filter(function (c) { return !igual(aberto.pend[c.chave], c.atual); }).length;
      painel.querySelector("[data-zf-n]").textContent = n ? n + (n === 1 ? " alteração" : " alterações") : "Sem alterações";
      painel.querySelector("[data-zf-aplicar]").disabled = !n;
    }
    painel.__redesenhar = redesenhar;
    redesenhar();
  }

  function fechar() {
    var p = d.querySelector(".zf-painel"), v = d.querySelector(".zf-veu");
    if (p) p.remove();
    if (v) v.remove();
    if (botao) botao.setAttribute("aria-expanded", "false");
    aberto = null;
  }

  function celula(c) {
    var cel = el('<div class="zf-cel"><span class="zf-rot">' + esc(c.rotulo) + "</span></div>");
    if (c.tipo === "marca") {
      var m = el('<label class="zf-marca"><input type="checkbox"> <span>' + esc(c.rotulo) + "</span></label>");
      cel.firstChild.remove();
      m.querySelector("input").addEventListener("change", function (e) { aberto.pend[c.chave] = e.target.checked; repintar(cel); });
      cel.appendChild(m);
    } else {
      cel.appendChild(lista(c, cel));
    }
    return cel;
  }
  function repintar(cel) { var p = cel.closest(".zf-painel"); if (p && p.__redesenhar) p.__redesenhar(); }
  function pintar(cel, c) {
    var v = aberto.pend[c.chave];
    cel.classList.toggle("zf-mudou", !igual(v, c.atual));
    if (c.tipo === "marca") { cel.querySelector("input").checked = !!v; return; }
    cel.querySelector(".zf-lista-cab span").textContent = resumo(c, v);
    cel.querySelector(".zf-lista").classList.toggle("zf-tem", v.length > 0);
    [].forEach.call(cel.querySelectorAll(".zf-op"), function (o) {
      var marcado = v.indexOf(o.getAttribute("data-v")) !== -1;
      o.classList.toggle("zf-sel", marcado);
      o.setAttribute("aria-selected", marcado ? "true" : "false");
    });
  }

  // a lista digitável de marcar: a busca no topo filtra sem acento nem caixa, as setas andam, Enter marca e a lista fica
  // aberta; o Esc fecha só a lista
  function lista(c, cel) {
    var caixa = el('<div class="zf-lista"><button type="button" class="zf-lista-cab" aria-expanded="false"><span></span>' +
      SVG.seta + '</button><div class="zf-lista-corpo" hidden><input type="text" class="zf-lista-busca" placeholder="Digite para ' +
      'filtrar" aria-label="Filtrar ' + esc(c.rotulo) + '"><div class="zf-lista-acoes"><button type="button" class="zf-link" ' +
      'data-nenhum>Desmarcar todos</button></div><div class="zf-ops" role="listbox" aria-multiselectable="true"></div>' +
      '<p class="zf-vazio" hidden>Nada com esse texto.</p></div></div>');
    var cab = caixa.firstChild, corpo = caixa.querySelector(".zf-lista-corpo"), busca = caixa.querySelector(".zf-lista-busca");
    var ops = caixa.querySelector(".zf-ops"), vazio = caixa.querySelector(".zf-vazio"), foco = -1;
    c.opcoes.forEach(function (o) {
      var b = el('<button type="button" class="zf-op" role="option"></button>');
      b.setAttribute("data-v", o.v);
      b.textContent = o.t;
      b.addEventListener("click", function () { marcar(o.v); });
      ops.appendChild(b);
    });
    if (!c.opcoes.length) vazio.textContent = "Nenhuma opção neste mês.";
    function visiveis() { return [].filter.call(ops.children, function (b) { return !b.hidden; }); }
    function marcar(v) {
      var atual = aberto.pend[c.chave].slice(), i = atual.indexOf(v);
      if (i === -1) atual.push(v); else atual.splice(i, 1);
      var ordem = c.opcoes.map(function (o) { return o.v; });
      aberto.pend[c.chave] = ordem.filter(function (x) { return atual.indexOf(x) !== -1; });
      repintar(cel);
    }
    function abrirLista() {
      [].forEach.call(d.querySelectorAll(".zf-lista-corpo"), function (x) {
        if (x !== corpo) { x.hidden = true; x.previousSibling.setAttribute("aria-expanded", "false"); }
      });
      corpo.hidden = false;
      cab.setAttribute("aria-expanded", "true");
      busca.value = "";
      filtrar();
      if (!w.matchMedia("(max-width: 639px)").matches) busca.focus();
    }
    function fecharLista() { corpo.hidden = true; cab.setAttribute("aria-expanded", "false"); foco = -1; }
    function filtrar() {
      var q = sem(busca.value);
      [].forEach.call(ops.children, function (b) { b.hidden = q && sem(b.textContent).indexOf(q) === -1; b.classList.remove("zf-foco"); });
      foco = -1;
      vazio.hidden = visiveis().length > 0;
    }
    function andar(passo) {
      var vs = visiveis();
      if (!vs.length) return;
      foco = Math.max(0, Math.min(vs.length - 1, foco + passo));
      vs.forEach(function (b, i) { b.classList.toggle("zf-foco", i === foco); });
      vs[foco].scrollIntoView({ block: "nearest" });
    }
    cab.addEventListener("click", function () { if (corpo.hidden) abrirLista(); else fecharLista(); });
    busca.addEventListener("input", filtrar);
    busca.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown") { e.preventDefault(); andar(1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); andar(-1); }
      else if (e.key === "Enter") {
        e.preventDefault();
        var vs = visiveis(), alvo = vs[foco >= 0 ? foco : 0];
        if (alvo && (foco >= 0 || vs.length === 1 || busca.value)) marcar(alvo.getAttribute("data-v"));
      } else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); fecharLista(); cab.focus(); }
    });
    caixa.querySelector("[data-nenhum]").addEventListener("click", function () { aberto.pend[c.chave] = []; repintar(cel); });
    return caixa;
  }

  // ── aplicar: marca as opções no campo escondido do .exe e dispara o change dele ─────────────────────────────────
  function aplicar(pend, semAtualizar) {
    Object.keys(pend).forEach(function (chave) {
      var x = $(chave), v = pend[chave];
      if (!x) return;
      if (x.type === "checkbox") {
        if (x.checked === !!v) return;
        x.checked = !!v;
      } else {
        [].forEach.call(x.options, function (o) { o.selected = o.value !== "" && v.indexOf(o.value) !== -1; });
      }
      x.dispatchEvent(new Event("change", { bubbles: true }));
    });
    if (!semAtualizar) atualizar();
  }

  // fechar sem aplicar descarta: Esc (com a lista fechada) e o clique fora, na captura
  d.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || !aberto) return;
    var l = d.querySelector(".zf-lista-corpo:not([hidden])");
    if (l) { l.hidden = true; l.previousSibling.setAttribute("aria-expanded", "false"); return; }
    fechar();
  });
  d.addEventListener("mousedown", function (e) {
    if (!aberto) return;
    if (e.target.closest && (e.target.closest(".zf-painel") || e.target.closest(".zf-ancora"))) return;
    fechar();
  }, true);
  // a busca (e o filtro da coluna) mudam as etiquetas: o Limpar tudo aparece e some com eles
  d.addEventListener("input", function (e) { if (e.target && (e.target.id === "fzQ" || e.target.closest("#fzTb"))) atualizar(); });

  w.coletasFiltros = { atualizar: atualizar };
  if (d.readyState === "loading") d.addEventListener("DOMContentLoaded", montar); else montar();
})(window, document);
