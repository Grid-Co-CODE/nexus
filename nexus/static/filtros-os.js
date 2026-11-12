/* static/filtros-os.js — os filtros do Nexus no padrão do Histórico de OS do OS Creator Web (12/11/2026).

   Levi: "em todas as partes do nexo, eu quero que os filtros sejam no padrão de nexos, OS Creator, histórico de OS [...]
   Com o mesmo estilo, as mesmas funcionalidades [...] Não é só um cartão suspenso". O modelo é o "A" do Histórico
   (03/11/2026): uma barra de uma linha (a busca e o botão Filtros com quantos estão aplicados), um painel suspenso preso
   à barra com uma lista por filtro, TODAS digitáveis (a caixa no topo filtra sem acento e sem caixa; as setas andam; o
   Enter escolhe), o ponto no campo que mudou, o Aplicar que só acende com mudança ("2 alterações"), o Limpar, fechar
   (×, Esc, clique fora) que descarta, e embaixo uma etiqueta por filtro APLICADO: o × tira aquele filtro e aplica na
   hora, e o "Limpar tudo" tira todos.

   Como entra: o formulário da tela leva `data-fo` e este script monta tudo com as <select> que já estão nele (o rótulo é
   o da própria tela). As <select> continuam no formulário, escondidas, guardando o valor: é o que o servidor, os testes e
   o script da tela leem. Nada vai para elas antes do Aplicar.
   - <select>           → lista de UM valor (escolher fecha a lista), como o Criado por e a Etiqueta do Histórico;
   - <select multiple>  → lista de marcar, como o Cliente e a Usina do Histórico (vai ao servidor como a=1&a=2);
   - data-fo="local"    → a tela filtra na própria página: o Aplicar grava as <select> e dispara o `change` de cada uma
                          que mudou (na ordem do formulário), e não envia. Sem isso, o Aplicar envia o formulário;
   - data-fo-fora       → a <select> que fica na barra, fora do painel;
   - data-padrao        → o valor "sem filtro" da <select> (o padrão é o da 1ª opção);
   - data-fo-some       → o que o padrão substitui (o "Filtrar", o "Limpar os filtros" antigo), dentro do formulário ou
                          logo depois dele: some pelo CSS (o botão escondido ainda envia o formulário no Enter).
   O corpo trocado depois (o Monitoramento do COS, a cada 30 s) é montado de novo sozinho. Sem este script, a tela segue
   com as <select> à vista. O estilo é o `fo-*` do nexus.css. */
(function () {
  "use strict";
  if (window.FiltrosOS) return;
  var seq = 0;

  function el(tag, classe, texto) {
    var e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texto) e.textContent = texto;
    return e;
  }
  function icone(nome) {
    var i = el("i", "ph ph-" + nome);
    i.setAttribute("aria-hidden", "true");
    return i;
  }
  function sem(s) {
    return String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " ").trim();
  }
  // "Thopen (12)" → "Thopen": a contagem fica na lista; o campo e a etiqueta dizem só o valor
  function semConta(t) { return String(t || "").replace(/\s*\(\d+\)\s*$/, "").replace(/\s+/g, " ").trim(); }
  function igual(a, b) { return a.length === b.length && a.every(function (v) { return b.indexOf(v) >= 0; }); }
  function opcoes(s) {
    return Array.prototype.filter.call(s.options, function (o) { return !o.hidden && !o.disabled; });
  }
  function lerValor(s) {
    if (s.multiple) return opcoes(s).filter(function (o) { return o.selected; }).map(function (o) { return o.value; });
    return [s.value];
  }
  function padraoDe(s) {
    if (s.multiple) return [];
    return [s.hasAttribute("data-padrao") ? s.getAttribute("data-padrao") : (s.options[0] ? s.options[0].value : "")];
  }
  function porValor(s, v) {
    if (s.multiple) {
      Array.prototype.forEach.call(s.options, function (o) { o.selected = v.indexOf(o.value) >= 0; });
      return;
    }
    s.value = v[0];
    if (s.value !== v[0]) s.value = padraoDe(s)[0];         // a opção sumiu (a cascata da tela): volta ao "sem filtro"
  }
  function rotuloDe(form, s) {
    var l = (s.id && form.querySelector('label[for="' + s.id + '"]')) || s.closest("label");
    var texto = "";
    if (l) {
      var r = l.querySelector(".gc-rotulo");
      texto = r ? r.textContent : Array.prototype.map.call(l.childNodes, function (c) {
        return c.nodeType === 3 ? c.textContent : "";
      }).join(" ");
    }
    texto = (texto || s.getAttribute("aria-label") || s.name || "Filtro").replace(/\s+/g, " ").trim();
    return { texto: texto, label: l };
  }

  function montar(form) {
    if (form.hasAttribute("data-fo-ok")) return;
    var listas = Array.prototype.filter.call(form.querySelectorAll("select"), function (s) {
      return !s.hasAttribute("data-fo-fora");
    });
    if (!listas.length) return;
    form.setAttribute("data-fo-ok", "1");
    var local = form.getAttribute("data-fo") === "local";
    var id = "fo-painel-" + (++seq);
    form.classList.add("fo-barra");

    // o botão Filtros no lugar da 1ª lista
    var abrir = el("button", "fo-btn");
    abrir.type = "button";
    abrir.setAttribute("aria-haspopup", "dialog");
    abrir.setAttribute("aria-expanded", "false");
    abrir.setAttribute("aria-controls", id);
    abrir.appendChild(icone("funnel-simple"));
    abrir.appendChild(document.createTextNode("Filtros"));
    var badge = el("span", "fo-badge");
    badge.hidden = true;
    abrir.appendChild(badge);
    var primeiro = rotuloDe(form, listas[0]).label;
    var ancora = primeiro && !primeiro.contains(listas[0]) ? primeiro : (listas[0].closest("label") || listas[0]);
    ancora.parentNode.insertBefore(abrir, ancora);

    // a busca da barra no campo do modelo (a lupa, a mesma borda), antes do botão Filtros
    var buscas = Array.prototype.slice.call(form.querySelectorAll('input[type="search"]'));
    buscas.forEach(function (b) {
      var rot = b.id && form.querySelector('label[for="' + b.id + '"]');
      var campo = el("label", "fo-campo fo-busca");
      if (!b.getAttribute("aria-label")) b.setAttribute("aria-label", rot ? rot.textContent.trim() : "Buscar");
      if (rot && rot.parentNode && !rot.contains(b)) rot.parentNode.removeChild(rot);
      var casca = b.closest("label");
      b.classList.remove("gc-campo");
      abrir.parentNode.insertBefore(campo, abrir);
      campo.appendChild(icone("magnifying-glass"));
      campo.appendChild(b);
      if (casca && casca !== campo && casca.parentNode && !casca.querySelector("input, select, button")) casca.parentNode.removeChild(casca);
    });

    // o painel
    var painel = el("div", "fo-painel");
    painel.id = id;
    painel.hidden = true;
    painel.setAttribute("role", "dialog");
    painel.setAttribute("aria-label", "Filtros");
    var topo = el("div", "fo-topo"), fechar = el("button", "fo-fechar", "×");
    topo.appendChild(el("h4", "", "Filtros"));
    fechar.type = "button";
    fechar.setAttribute("aria-label", "Fechar sem aplicar");
    fechar.title = "Fechar sem aplicar";
    topo.appendChild(fechar);
    var grade = el("div", "fo-grade");
    var guarda = el("div", "fo-guarda");            // as <select> de verdade: escondidas, guardando o valor
    guarda.hidden = true;
    var campos = [];
    listas.forEach(function (s, i) {
      var r = rotuloDe(form, s), pai = s.parentNode;
      s.removeAttribute("onchange");
      s.onchange = null;
      guarda.appendChild(s);
      if (r.label && r.label.parentNode) r.label.parentNode.removeChild(r.label);
      if (pai !== form && pai.parentNode && !pai.children.length && !pai.textContent.trim()) pai.parentNode.removeChild(pai);
      var cel = el("div", "fo-cel"), rot = el("span", "fo-rot", r.texto), det = el("details", "fo-multi" + (s.multiple ? "" : " fo-uni"));
      rot.id = id + "-r" + i;
      var sum = el("summary"), txt = el("span", "fo-txt");
      txt.id = id + "-v" + i;
      sum.setAttribute("aria-labelledby", rot.id + " " + txt.id);
      sum.appendChild(txt);
      sum.appendChild(icone("caret-down"));
      var lista = el("div", "fo-lista");
      det.appendChild(sum);
      det.appendChild(lista);
      cel.appendChild(rot);
      cel.appendChild(det);
      grade.appendChild(cel);
      var v = lerValor(s);
      campos.push({ s: s, rotulo: r.texto, padrao: padraoDe(s), aplicado: v, pend: v.slice(), cel: cel, det: det, txt: txt, lista: lista });
    });
    var rodape = el("div", "fo-rodape"), limpar = el("button", "fo-btn fo-fantasma", "Limpar");
    var dir = el("div", "fo-dir"), nalt = el("span", "", "Sem alterações"), aplicar = el("button", "fo-btn fo-aplicar", "Aplicar");
    limpar.type = aplicar.type = "button";
    aplicar.disabled = true;
    nalt.setAttribute("aria-live", "polite");
    dir.appendChild(nalt);
    dir.appendChild(aplicar);
    rodape.appendChild(limpar);
    rodape.appendChild(dir);
    painel.appendChild(topo);
    painel.appendChild(grade);
    painel.appendChild(rodape);
    form.appendChild(guarda);
    form.appendChild(painel);
    var etiquetas = el("div", "fo-etiquetas");
    etiquetas.hidden = true;
    etiquetas.setAttribute("role", "group");
    etiquetas.setAttribute("aria-label", "Filtros aplicados");
    form.parentNode.insertBefore(etiquetas, form.nextSibling);

    function textoDe(c, valores) {
      var ops = opcoes(c.s);
      if (!c.s.multiple) {
        var o = ops.filter(function (x) { return x.value === valores[0]; })[0] || c.s.options[0];
        return o ? semConta(o.textContent) : "";
      }
      var nomes = ops.filter(function (x) { return valores.indexOf(x.value) >= 0; }).map(function (x) { return semConta(x.textContent); });
      return nomes.join(", ");
    }
    function resumoDe(c) {
      if (!c.s.multiple) return textoDe(c, c.pend);
      if (!c.pend.length) return c.s.getAttribute("data-todos") || "Todos";
      return c.pend.length === 1 ? textoDe(c, c.pend) : c.pend.length + " selecionados";
    }
    function conferir() {
      var n = 0;
      campos.forEach(function (c) {
        var mudou = !igual(c.pend, c.aplicado);
        c.cel.classList.toggle("mudou", mudou);
        c.det.classList.toggle("fo-tem", !igual(c.pend, c.padrao));
        c.txt.textContent = resumoDe(c);
        if (mudou) n++;
      });
      aplicar.disabled = !n;
      nalt.textContent = n ? (n === 1 ? "1 alteração" : n + " alterações") : "Sem alterações";
    }
    // a lista de um filtro, refeita a cada abertura (a tela pode ter trocado as opções e as contagens)
    function encher(c) {
      var lista = c.lista;
      lista.textContent = "";
      var procura = el("input", "fo-procura");
      procura.type = "search";
      procura.placeholder = "Digite para filtrar";
      procura.autocomplete = "off";
      procura.setAttribute("aria-label", "Filtrar " + c.rotulo.toLowerCase());
      lista.appendChild(procura);
      opcoes(c.s).forEach(function (o) {
        var item;
        if (c.s.multiple) {
          item = el("label", "fo-op");
          var cx = el("input");
          cx.type = "checkbox";
          cx.checked = c.pend.indexOf(o.value) >= 0;
          cx.addEventListener("change", function () {
            c.pend = c.pend.filter(function (v) { return v !== o.value; });
            if (cx.checked) c.pend.push(o.value);
            item.classList.toggle("sel", cx.checked);
            conferir();
          });
          item.appendChild(cx);
          item.appendChild(el("span", "", o.textContent.trim()));
        } else {
          item = el("button", "fo-op", o.textContent.trim());
          item.type = "button";
          item.addEventListener("click", function () {
            c.pend = [o.value];
            c.det.open = false;
            c.det.querySelector("summary").focus();
            conferir();
          });
        }
        if (c.pend.indexOf(o.value) >= 0) item.classList.add("sel");
        item.setAttribute("data-fo-texto", sem(o.textContent));
        lista.appendChild(item);
      });
      var vazio = el("p", "fo-vazio", "Nada com esse texto.");
      vazio.hidden = true;
      lista.appendChild(vazio);
      function visiveis() {
        return Array.prototype.filter.call(lista.querySelectorAll(".fo-op"), function (x) { return !x.hidden; });
      }
      procura.addEventListener("input", function () {
        var q = sem(procura.value), n = 0;
        Array.prototype.forEach.call(lista.querySelectorAll(".fo-op"), function (x) {
          x.hidden = !!q && x.getAttribute("data-fo-texto").indexOf(q) < 0;
          if (!x.hidden) n++;
        });
        vazio.hidden = n > 0;
      });
      // as setas andam pela lista; o Enter na caixa escolhe quando só sobrou uma (e nunca envia o formulário)
      lista.addEventListener("keydown", function (e) {
        var vs = visiveis(), alvo = function (x) { return x.tagName === "LABEL" ? x.querySelector("input") : x; };
        var onde = vs.map(alvo).indexOf(document.activeElement);
        if (e.key === "ArrowDown") { e.preventDefault(); if (vs[onde + 1]) alvo(vs[onde + 1]).focus(); }
        else if (e.key === "ArrowUp") { e.preventDefault(); if (onde > 0) alvo(vs[onde - 1]).focus(); else procura.focus(); }
        else if (e.key === "Enter" && e.target === procura) { e.preventDefault(); if (vs.length === 1) alvo(vs[0]).click(); }
      });
      setTimeout(function () { procura.focus(); }, 0);
    }
    campos.forEach(function (c) {
      c.det.addEventListener("toggle", function () {
        if (!c.det.open) return;
        campos.forEach(function (o) { if (o !== c) o.det.open = false; });       // uma lista aberta por vez
        encher(c);
      });
    });
    // o que acontece dentro do painel não chega ao formulário (o script da tela ouve o `change` e o `input` dele)
    ["change", "input"].forEach(function (ev) { painel.addEventListener(ev, function (e) { e.stopPropagation(); }); });

    function desenhar() {
      var ativos = campos.filter(function (c) { return !igual(c.aplicado, c.padrao); });
      badge.hidden = !ativos.length;
      badge.textContent = ativos.length;
      etiquetas.textContent = "";
      etiquetas.hidden = !ativos.length;
      ativos.forEach(function (c) {
        var chip = el("span", "fo-chip"), valor = textoDe(c, c.aplicado), x = el("button", "fo-chip-x", "×");
        var v = el("span", "fo-chip-v", valor);
        v.title = valor;
        x.type = "button";
        x.setAttribute("aria-label", "Tirar o filtro " + c.rotulo);
        x.title = "Tirar este filtro";
        x.addEventListener("click", function () {
          campos.forEach(function (o) { o.pend = (o === c ? o.padrao : o.aplicado).slice(); });
          aplicarAgora(false);
        });
        chip.appendChild(el("i", "", c.rotulo + ":"));
        chip.appendChild(v);
        chip.appendChild(x);
        etiquetas.appendChild(chip);
      });
      if (ativos.length) {
        var tudo = el("button", "fo-link", "Limpar tudo");
        tudo.type = "button";
        tudo.addEventListener("click", function () {
          campos.forEach(function (o) { o.pend = o.padrao.slice(); });
          aplicarAgora(true);
        });
        etiquetas.appendChild(tudo);
      }
    }
    // o valor de agora das <select> vira o aplicado (depois do Aplicar, e quando o script da tela mexe nelas)
    function sincronizar() {
      campos.forEach(function (c) { c.aplicado = lerValor(c.s); c.pend = c.aplicado.slice(); });
      desenhar();
      conferir();
    }
    function fecha(descartar) {
      if (painel.hidden) return;
      if (descartar) campos.forEach(function (c) { c.pend = c.aplicado.slice(); });
      campos.forEach(function (c) { c.det.open = false; });
      painel.hidden = true;
      abrir.setAttribute("aria-expanded", "false");
      conferir();
    }
    function aplicarAgora(comBusca) {
      if (comBusca) buscas.forEach(function (b) { b.value = ""; });
      if (!local) {
        campos.forEach(function (c) { porValor(c.s, c.pend); });
        if (form.requestSubmit) form.requestSubmit(); else form.submit();
        return;
      }
      // na própria página: uma <select> de cada vez, na ordem do formulário (a cascata da tela refaz as seguintes)
      var pedidos = campos.map(function (c) { return c.pend.slice(); });
      campos.forEach(function (c, i) {
        if (igual(pedidos[i], lerValor(c.s))) return;
        porValor(c.s, pedidos[i]);
        c.s.dispatchEvent(new Event("change", { bubbles: true }));
      });
      if (comBusca) buscas.forEach(function (b) { b.dispatchEvent(new Event("input", { bubbles: true })); });
      fecha(false);
      sincronizar();
    }
    abrir.addEventListener("click", function () {
      if (!painel.hidden) { fecha(true); return; }
      painel.hidden = false;
      abrir.setAttribute("aria-expanded", "true");
      conferir();
    });
    fechar.addEventListener("click", function () { fecha(true); abrir.focus(); });
    limpar.addEventListener("click", function () {
      campos.forEach(function (c) { c.pend = c.padrao.slice(); c.det.open = false; });
      conferir();
    });
    aplicar.addEventListener("click", function () { aplicarAgora(false); });
    // a <select> mexida por fora (o script da tela) aparece nas etiquetas
    form.addEventListener("change", function (e) {
      if (listas.indexOf(e.target) >= 0) setTimeout(sincronizar, 0);
    });
    painel._foFecha = function () { fecha(true); };
    painel._foAbrir = abrir;
    sincronizar();
  }

  function montarTodos(raiz) {
    Array.prototype.forEach.call((raiz || document).querySelectorAll("form[data-fo]:not([data-fo-ok])"), montar);
  }
  // um só ouvinte para todos os painéis (o corpo trocado de 30 em 30 s não deixa ouvinte velho para trás)
  function abertos() { return Array.prototype.slice.call(document.querySelectorAll(".fo-painel:not([hidden])")); }
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    abertos().forEach(function (p) { p._foFecha(); if (p._foAbrir) p._foAbrir.focus(); });
  });
  document.addEventListener("click", function (e) {
    abertos().forEach(function (p) {
      if (!p.contains(e.target) && !(p._foAbrir && p._foAbrir.contains(e.target))) p._foFecha();
    });
  });
  window.FiltrosOS = { montar: montarTodos };
  montarTodos(document);
  if (window.MutationObserver) {
    new MutationObserver(function (ms) {
      for (var i = 0; i < ms.length; i++) {
        if (ms[i].addedNodes && ms[i].addedNodes.length) { montarTodos(document); return; }
      }
    }).observe(document.documentElement, { childList: true, subtree: true });
  }
})();
