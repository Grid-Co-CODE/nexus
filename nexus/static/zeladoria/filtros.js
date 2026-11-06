/* Os filtros da Zeladoria num painel suspenso, como os do Histórico de OS do OS Creator (Levi, 06/11/2026: "quero que todos
   os filtros sejam suspensos alá histórico de OS do OS Creator!"). O modelo é o A do Histórico
   (nexus/torres/oscreator/README.md, "Os filtros do Histórico só valem no Aplicar"): a busca por texto fica na barra e filtra
   enquanto se digita; o botão Filtros, com a contagem dos aplicados, abre o painel; cada campo é uma lista digitável; nada
   filtra antes do Aplicar; as etiquetas azuis dos aplicados ficam abaixo da barra, e o × tira aquele filtro na hora.

   Por que de fora, sem mexer no Radar: o clone (clone/radar.html) é o Radar como está no ar, refeito pela ferramenta a cada
   versão nova, e o estado dele (`ui`, `render`) mora dentro de uma função, fora de alcance. Então esta peça só mexe no
   DOM: esconde os campos `flt-*` do Radar (e as listas de vários valores dele, `.msf`), monta o painel com cópias, e no
   Aplicar escreve nos campos escondidos e dispara o mesmo `change` que a pessoa dispararia. O Radar refaz a tela a cada
   `change` (o #app inteiro troca), e a peça remonta a barra quando isso acontece (MutationObserver). Um filtro novo que o
   Radar ganhar com id `flt-*` entra no painel sozinho.

   Fica fora do painel: o texto (a busca, que filtra enquanto se digita, como no Histórico) e os campos que ESCOLHEM o que a
   tela mostra em vez de filtrar (`FORA`). */
(function (w, d) {
  "use strict";
  if (w.__zeladoriaFiltros) return;
  w.__zeladoriaFiltros = true;

  // o usuário cujas permissões se vê, o previsto que o Financeiro adota e o mês da simulação de repasse
  var FORA = { "flt-perm-outro-usuario": 1, "flt-fin-geral-prev": 1, "flt-gj-mes": 1 };
  // o nome do campo pelo fim do id, quando a 1ª opção não diz ("Região (todas)" já diz "Região")
  var ROTULOS = {
    cliente: "Cliente", alerta: "Alerta", estado: "Estado", usina: "Usina", mes: "Mês", cidade: "Cidade", uf: "Estado",
    responsavel: "Responsável", resp: "Responsável", periodo: "Período", indicador: "Indicador", ordenar: "Ordenar por",
    ordem: "Ordem", semana: "Semana", semanas: "Janela", forma: "Forma", tipo: "Tipo", equipe: "Equipe", servico: "Serviço",
    serv: "Serviço", regiao: "Região", farol: "Farol", supervisor: "Supervisor", tecnico: "Técnico", status: "Status",
    crit: "Criticidade", nivel: "Criticidade", situacao: "Situação", cluster: "Cluster", minimo: "Situação",
    cobertura: "Cobertura", fin: "Finalização"
  };
  var SVG = {
    filtro: '<svg class="zf-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h18M6 12h12M10 19h4"/></svg>',
    seta: '<svg class="zf-ico zf-seta" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>',
    x: '<svg class="zf-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>'
  };

  var vistos = {};          // o 1º valor de cada campo sem "todos" (ordenar, período): é o padrão dele nesta página
  var aberto = null;        // {chave do grupo, pend: {campo: valor}} do painel aberto, que sobrevive a um render do Radar
  var aplicando = false;

  function sem(s) {
    return String(s == null ? "" : s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  }
  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  function igual(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  function el(html) { var t = d.createElement("template"); t.innerHTML = html.trim(); return t.content.firstChild; }

  // ── os campos de um grupo, lidos do DOM do Radar ─────────────────────────────────────────────────────────────────
  function ehTodos(op) {
    return !!op && (/^(todos|todas|all)?$/i.test(op.value) || /\(tod[oa]s?\)|^tod[oa]s?\b/i.test(op.textContent));
  }
  function rotuloDe(id, primeira) {
    if (primeira && ehTodos(primeira)) {
      var t = primeira.textContent.replace(/\s*\(.*\)\s*$/, "").trim();
      if (t && !/^tod[oa]s?\b/i.test(t)) return t;
    }
    var fim = id.split("-").pop();
    return ROTULOS[fim] || (fim.charAt(0).toUpperCase() + fim.slice(1));
  }
  function textoDaMarca(c) {
    var l = c.closest("label");
    var t = l ? l.textContent : (c.nextSibling && c.nextSibling.textContent) || "";
    return t.replace(/\s+/g, " ").trim() || rotuloDe(c.id);
  }

  function lerCampo(c) {
    if (c.tagName === "SELECT") {
      var ops = [].map.call(c.options, function (o) { return { v: o.value, t: o.textContent.trim() }; });
      var primeira = c.options[0];
      if (!(c.id in vistos)) vistos[c.id] = c.value;
      return { chave: c.id, tipo: "lista", rotulo: rotuloDe(c.id, primeira), opcoes: ops, atual: c.value,
               padrao: ehTodos(primeira) ? primeira.value : vistos[c.id] };
    }
    if (c.type === "checkbox") {
      if (!(c.id in vistos)) vistos[c.id] = c.checked;
      return { chave: c.id, tipo: "marca", rotulo: textoDaMarca(c), atual: c.checked, padrao: vistos[c.id] };
    }
    if (!(c.id in vistos)) vistos[c.id] = c.value;
    return { chave: c.id, tipo: "campo", tipoInput: c.type, rotulo: rotuloDe(c.id), atual: c.value, padrao: vistos[c.id] };
  }

  // a lista de vários valores do Radar (multiSelectFiltro): o botão "Cliente: todos ▾" e as marcas de cada valor
  function lerVarios(m) {
    var k = m.getAttribute("data-msf");
    var botao = m.querySelector("[data-msf-toggle]");
    var marcas = [].slice.call(m.querySelectorAll(".msf-check"));
    var ops = marcas.map(function (x) {
      return { v: x.getAttribute("data-msf-idx"), t: (x.closest("label") || x.parentNode).textContent.trim() };
    });
    return { chave: "msf:" + k, msf: k, tipo: "varios", rotulo: (botao ? botao.textContent : k).split(":")[0].trim(),
             opcoes: ops, atual: marcas.filter(function (x) { return x.checked; }).map(function (x) { return x.getAttribute("data-msf-idx"); }),
             padrao: ops.map(function (o) { return o.v; }) };
  }

  function ehBusca(c) { return c.tagName === "INPUT" && (c.type === "text" || c.type === "search" || !c.type); }

  // a marca (e às vezes a lista) vem dentro de um <label> com o texto dela: some o rótulo inteiro, não só a caixinha
  function embrulho(x) {
    var l = x.closest("label");
    return l && l !== x && l.closest("#app") ? l : x;
  }

  // os grupos: os campos de filtro de cada barra do Radar (a `.chiprow`, a barra da tabela, ou o pai do campo)
  function grupos() {
    var porBarra = [];
    function barraDe(x) { return x.closest(".chiprow, .table-toolbar") || embrulho(x).parentNode; }
    function grupo(b) {
      for (var i = 0; i < porBarra.length; i++) if (porBarra[i].barra === b) return porBarra[i];
      var g = { barra: b, campos: [], busca: null, limpar: null };
      porBarra.push(g);
      return g;
    }
    var app = d.getElementById("app");
    if (!app) return [];
    [].forEach.call(app.querySelectorAll('[id^="flt-"]'), function (c) {
      if (FORA[c.id] || c.closest(".zf-painel")) return;
      if (!/^(SELECT|INPUT)$/.test(c.tagName)) return;
      var g = grupo(barraDe(c));
      if (ehBusca(c)) { if (!g.busca) g.busca = c; return; }
      g.campos.push({ dom: c, campo: lerCampo(c) });
    });
    [].forEach.call(app.querySelectorAll(".msf[data-msf]"), function (m) {
      if (m.closest(".zf-painel")) return;
      grupo(barraDe(m)).campos.push({ dom: m, campo: lerVarios(m) });
    });
    return porBarra.filter(function (g) {
      if (!g.campos.length) return false;
      // no painel, na ordem em que estavam na barra do Radar
      g.campos.sort(function (a, b) { return a.dom.compareDocumentPosition(b.dom) & 4 ? -1 : 1; });
      g.chave = g.campos[0].campo.chave;
      // o "Limpar filtros" (ou "Limpar cidade/estado") do próprio Radar vira o "Limpar tudo" das etiquetas
      g.limpar = [].filter.call(g.barra.querySelectorAll("button"), function (b) {
        return /^limpar/i.test(b.textContent.trim()) && /limpar/i.test(b.id || "");
      })[0] || null;
      return true;
    });
  }

  // ── a barra: o botão Filtros e as etiquetas ──────────────────────────────────────────────────────────────────
  function aplicados(g) {
    return g.campos.map(function (x) { return x.campo; }).filter(function (c) { return !igual(c.atual, c.padrao); });
  }
  function resumo(c, v) {
    if (c.tipo === "marca") return v ? "sim" : "não";
    if (c.tipo === "varios") {
      if (v.length === c.opcoes.length) return "todos";
      if (!v.length) return "nenhum";
      if (v.length === 1) return (c.opcoes.filter(function (o) { return o.v === v[0]; })[0] || {}).t || "1";
      return v.length + " selecionados";
    }
    if (c.tipo === "lista") return (c.opcoes.filter(function (o) { return o.v === v; })[0] || { t: v }).t;
    return v;
  }

  function montarGrupo(g) {
    if (g.barra.getAttribute("data-zf")) return;
    g.barra.setAttribute("data-zf", "1");
    g.barra.classList.add("zf-barra");
    g.campos.forEach(function (x) { embrulho(x.dom).classList.add("zf-oculto"); });
    if (g.limpar) g.limpar.classList.add("zf-oculto");
    var lista = aplicados(g);
    var ancora = el('<span class="zf-ancora"><button type="button" class="zf-btn" aria-expanded="false" aria-haspopup="dialog">' +
      SVG.filtro + "Filtros" + (lista.length ? ' <span class="zf-badge">' + lista.length + "</span>" : "") + "</button></span>");
    // depois da busca; sem busca, no lugar do 1º filtro (no Financeiro, Cidade e Estado ficam no fim da linha da meta)
    if (g.busca) g.busca.insertAdjacentElement("afterend", ancora);
    else embrulho(g.campos[0].dom).insertAdjacentElement("beforebegin", ancora);
    ancora.firstChild.addEventListener("click", function () {
      if (aberto && aberto.chave === g.chave) fechar(); else abrir(g, ancora, null);
    });
    if (lista.length) {
      var et = el('<div class="zf-etiquetas"></div>');
      lista.forEach(function (c) {
        var chip = el('<span class="zf-chip"><i>' + esc(c.rotulo) + '</i> <span class="zf-chip-v">' + esc(resumo(c, c.atual)) +
          '</span><button type="button" class="zf-chip-x" title="Tirar este filtro" aria-label="Tirar o filtro ' + esc(c.rotulo) +
          '">' + SVG.x + "</button></span>");
        chip.querySelector("button").addEventListener("click", function () {
          var p = {}; p[c.chave] = c.padrao; aplicar(p);
        });
        et.appendChild(chip);
      });
      var tudo = el('<button type="button" class="zf-link">Limpar tudo</button>');
      tudo.addEventListener("click", function () { limparTudo(g); });
      et.appendChild(tudo);
      g.barra.insertAdjacentElement("afterend", et);
    }
  }

  function limparTudo(g) {
    // o "Limpar filtros" do próprio Radar, quando a barra tem um (limpa também a busca, como o Limpar tudo do Histórico)
    if (g.limpar && d.body.contains(g.limpar)) { g.limpar.click(); return; }
    var p = {};
    g.campos.forEach(function (x) { p[x.campo.chave] = x.campo.padrao; });
    aplicar(p);
  }

  // ── o painel ─────────────────────────────────────────────────────────────────────────────────────────────────
  function abrir(g, ancora, pend) {
    fechar();
    var campos = g.campos.map(function (x) { return x.campo; });
    var valores = {};
    campos.forEach(function (c) { valores[c.chave] = pend && c.chave in pend ? pend[c.chave] : c.atual; });
    aberto = { chave: g.chave, pend: valores };
    var painel = el('<div class="zf-painel" role="dialog" aria-label="Filtros" tabindex="-1">' +
      '<div class="zf-painel-topo"><h4>Filtros</h4><button type="button" class="zf-fechar" aria-label="Fechar">' + SVG.x +
      '</button></div><div class="zf-painel-corpo"><div class="zf-grade"></div></div>' +
      '<div class="zf-rodape"><button type="button" class="zf-btn zf-fantasma" data-zf-limpar>Limpar</button>' +
      '<div class="zf-dir"><span data-zf-n></span><button type="button" class="zf-btn zf-lima" data-zf-aplicar>Aplicar</button>' +
      "</div></div></div>");
    var grade = painel.querySelector(".zf-grade");
    campos.forEach(function (c) { grade.appendChild(celula(c)); });
    var veu = el('<div class="zf-veu"></div>');
    veu.addEventListener("click", fechar);
    ancora.appendChild(painel);
    d.body.appendChild(veu);
    ancora.firstChild.setAttribute("aria-expanded", "true");
    painel.querySelector(".zf-fechar").addEventListener("click", fechar);
    painel.querySelector("[data-zf-limpar]").addEventListener("click", function () {
      campos.forEach(function (c) { aberto.pend[c.chave] = c.padrao; });
      redesenhar();
    });
    painel.querySelector("[data-zf-aplicar]").addEventListener("click", function () {
      var p = {};
      campos.forEach(function (c) { if (!igual(aberto.pend[c.chave], c.atual)) p[c.chave] = aberto.pend[c.chave]; });
      fechar();
      aplicar(p);
    });
    // o painel largo perto da borda direita abre para a esquerda
    var r = painel.getBoundingClientRect();
    if (r.right > d.documentElement.clientWidth - 8) painel.classList.add("zf-direita");
    painel.focus();

    function redesenhar() {
      [].forEach.call(grade.children, function (cel, i) { pintar(cel, campos[i]); });
      var n = campos.filter(function (c) { return !igual(aberto.pend[c.chave], c.atual); }).length;
      painel.querySelector("[data-zf-n]").textContent = n ? n + (n === 1 ? " alteração" : " alterações") : "";
      painel.querySelector("[data-zf-aplicar]").disabled = !n;
    }
    painel.__redesenhar = redesenhar;
    redesenhar();
  }

  function fechar() {
    var p = d.querySelector(".zf-painel"), v = d.querySelector(".zf-veu");
    if (p) {
      var b = p.parentNode && p.parentNode.firstChild;
      if (b && b.setAttribute) b.setAttribute("aria-expanded", "false");
      p.remove();
    }
    if (v) v.remove();
    aberto = null;
  }

  // uma célula: o rótulo e o campo; o campo que mudou em relação ao aplicado ganha o ponto
  function celula(c) {
    var cel = el('<div class="zf-cel"><span class="zf-rot">' + esc(c.rotulo) + "</span></div>");
    if (c.tipo === "marca") {
      var m = el('<label class="zf-marca"><input type="checkbox"> <span>' + esc(c.rotulo) + "</span></label>");
      cel.firstChild.remove();
      m.querySelector("input").addEventListener("change", function (e) { aberto.pend[c.chave] = e.target.checked; atualizar(cel); });
      cel.appendChild(m);
    } else if (c.tipo === "campo") {
      var i = el('<input class="zf-entrada">');
      i.type = c.tipoInput || "text";
      i.addEventListener("input", function () { aberto.pend[c.chave] = i.value; atualizar(cel, true); });
      cel.appendChild(i);
    } else {
      cel.appendChild(lista(c, cel));
    }
    return cel;
  }
  function atualizar(cel, semPintar) {
    var p = cel.closest(".zf-painel");
    if (p && p.__redesenhar && !semPintar) p.__redesenhar();
    else if (p && p.__redesenhar) {
      // o texto digitado não se repinta (perderia o cursor): só a contagem e o ponto
      var foco = d.activeElement; p.__redesenhar(); if (foco && foco.focus) foco.focus();
    }
  }
  function pintar(cel, c) {
    var v = aberto.pend[c.chave];
    cel.classList.toggle("zf-mudou", !igual(v, c.atual));
    if (c.tipo === "marca") cel.querySelector("input").checked = !!v;
    else if (c.tipo === "campo") { var i = cel.querySelector("input"); if (i !== d.activeElement) i.value = v; }
    else {
      var cab = cel.querySelector(".zf-lista-cab span");
      cab.textContent = resumo(c, v);
      cel.querySelector(".zf-lista").classList.toggle("zf-tem", !igual(v, c.padrao));
      [].forEach.call(cel.querySelectorAll(".zf-op"), function (o) {
        var marcado = c.tipo === "varios" ? v.indexOf(o.getAttribute("data-v")) !== -1 : o.getAttribute("data-v") === v;
        o.classList.toggle("zf-sel", marcado);
        o.setAttribute("aria-selected", marcado ? "true" : "false");
      });
    }
  }

  // a lista digitável: o cabeçalho mostra o escolhido; aberta, a caixa de busca no topo filtra sem acento nem caixa, as
  // setas andam, Enter escolhe (a de um valor fecha; a de vários marca e fica aberta) e o Esc fecha só a lista
  function lista(c, cel) {
    var varios = c.tipo === "varios";
    var caixa = el('<div class="zf-lista"><button type="button" class="zf-lista-cab" aria-expanded="false"><span></span>' +
      SVG.seta + '</button><div class="zf-lista-corpo" hidden><input type="text" class="zf-lista-busca" placeholder="Digite para ' +
      'filtrar" aria-label="Filtrar ' + esc(c.rotulo) + '">' +
      (varios ? '<div class="zf-lista-acoes"><button type="button" class="zf-link" data-todos>Marcar todos</button>' +
        '<button type="button" class="zf-link" data-nenhum>Desmarcar todos</button></div>' : "") +
      '<div class="zf-ops" role="listbox"' + (varios ? ' aria-multiselectable="true"' : "") + "></div>" +
      '<p class="zf-vazio" hidden>Nada com esse texto.</p></div></div>');
    var cab = caixa.firstChild, corpo = caixa.querySelector(".zf-lista-corpo"), busca = caixa.querySelector(".zf-lista-busca");
    var ops = caixa.querySelector(".zf-ops"), vazio = caixa.querySelector(".zf-vazio"), foco = -1;
    c.opcoes.forEach(function (o) {
      var b = el('<button type="button" class="zf-op" role="option"></button>');
      b.setAttribute("data-v", o.v);
      b.textContent = o.t;
      b.addEventListener("click", function () { escolher(o.v); });
      ops.appendChild(b);
    });
    function visiveis() { return [].filter.call(ops.children, function (b) { return !b.hidden; }); }
    function escolher(v) {
      if (varios) {
        var atual = aberto.pend[c.chave].slice(), i = atual.indexOf(v);
        if (i === -1) atual.push(v); else atual.splice(i, 1);
        aberto.pend[c.chave] = c.padrao.filter(function (x) { return atual.indexOf(x) !== -1; });
        atualizar(cel);
      } else {
        aberto.pend[c.chave] = v;
        fecharLista();
        atualizar(cel);
        cab.focus();
      }
    }
    function abrirLista() {
      [].forEach.call(d.querySelectorAll(".zf-lista-corpo"), function (x) { if (x !== corpo) { x.hidden = true; x.previousSibling.setAttribute("aria-expanded", "false"); } });
      corpo.hidden = false;
      cab.setAttribute("aria-expanded", "true");
      busca.value = "";
      filtrar();
      // no celular o teclado cobriria metade da lista: o cursor só vai à busca no computador
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
        var vs = visiveis();
        var alvo = vs[foco >= 0 ? foco : 0];
        if (alvo && (foco >= 0 || vs.length === 1 || busca.value)) escolher(alvo.getAttribute("data-v"));
      } else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); fecharLista(); cab.focus(); }
    });
    if (varios) {
      caixa.querySelector("[data-todos]").addEventListener("click", function () { aberto.pend[c.chave] = c.padrao.slice(); atualizar(cel); });
      caixa.querySelector("[data-nenhum]").addEventListener("click", function () { aberto.pend[c.chave] = []; atualizar(cel); });
    }
    return caixa;
  }

  // ── aplicar: escreve no campo escondido do Radar e dispara o change dele, um campo por vez ─────────────────────
  function disparar(alvo, tipo) { alvo.dispatchEvent(new Event(tipo, { bubbles: true })); }
  function aplicar(pend) {
    aplicando = true;
    try {
      Object.keys(pend).forEach(function (chave) {
        var v = pend[chave];
        if (chave.indexOf("msf:") === 0) { aplicarVarios(chave.slice(4), v); return; }
        // o render do Radar troca o #app inteiro: o campo se acha de novo pelo id a cada passo
        var c = d.getElementById(chave);
        if (!c) return;
        if (c.type === "checkbox") { if (c.checked === !!v) return; c.checked = !!v; disparar(c, "change"); }
        else { if (c.value === v) return; c.value = v; disparar(c, "input"); if (d.getElementById(chave) === c) disparar(c, "change"); }
      });
    } finally {
      aplicando = false;
    }
    montar();
  }
  // a lista de vários do Radar só muda pelas marcas dela (cada uma refaz a tela): pelo caminho mais curto, a partir de
  // "Marcar todos" (e desmarcar o que não vale) ou de "Desmarcar todos" (e marcar o que vale)
  function aplicarVarios(k, quer) {
    function m() { return d.querySelector('.msf[data-msf="' + k + '"]'); }
    if (!m()) return;
    var todos = [].map.call(m().querySelectorAll(".msf-check"), function (x) { return x.getAttribute("data-msf-idx"); });
    var poucos = quer.length <= todos.length / 2;
    var b = m().querySelector(poucos ? "[data-msf-none]" : "[data-msf-all]");
    if (b) b.click();
    var mudar = poucos ? quer : todos.filter(function (i) { return quer.indexOf(i) === -1; });
    mudar.forEach(function (i) {
      var x = m() && m().querySelector('.msf-check[data-msf-idx="' + i + '"]');
      if (!x) return;
      x.checked = poucos;
      disparar(x, "change");
    });
  }

  // ── remontar quando o Radar refaz a tela ─────────────────────────────────────────────────────────────────────
  var agendado = false;
  function montar() {
    agendado = false;
    if (aplicando) return;
    var gs = grupos();
    gs.forEach(montarGrupo);
    if (aberto && !d.querySelector(".zf-painel")) {
      var g = gs.filter(function (x) { return x.chave === aberto.chave; })[0];
      var pend = aberto.pend;
      aberto = null;
      if (g) abrir(g, g.barra.querySelector(".zf-ancora"), pend);
    }
  }
  new MutationObserver(function () {
    if (agendado || aplicando) return;
    agendado = true;
    (w.queueMicrotask || function (f) { Promise.resolve().then(f); })(montar);
  }).observe(d.body, { childList: true, subtree: true });

  // fechar sem aplicar descarta: Esc (com a lista fechada) e o clique fora, na captura, antes do resto da página
  d.addEventListener("keydown", function (e) {
    if (e.key !== "Escape" || !aberto) return;
    // com uma lista aberta, o Esc fecha só ela (no celular o cursor não vai à busca, e o Esc chega aqui)
    var lista = d.querySelector(".zf-lista-corpo:not([hidden])");
    if (lista) { lista.hidden = true; lista.previousSibling.setAttribute("aria-expanded", "false"); return; }
    fechar();
  });
  d.addEventListener("mousedown", function (e) {
    if (!aberto) return;
    if (e.target.closest && (e.target.closest(".zf-painel") || e.target.closest(".zf-ancora"))) return;
    fechar();
  }, true);

  if (d.readyState === "loading") d.addEventListener("DOMContentLoaded", montar); else montar();
})(window, document);
