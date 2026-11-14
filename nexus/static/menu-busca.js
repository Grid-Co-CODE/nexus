/* A busca do menu lateral (14/11/2026, Levi: "seria interessante um campo de busca para a pessoa digitar palavras-chave e
   aí já aparece tudo. Tudo que tem relação, já aparece expandido"). Filtra na própria página, sem ir ao servidor:
   - acha pelo nome da área, pelo nome da tela e pela pergunta que a tela responde (data-pergunta, a `Tela.pergunta`), sem
     acento e sem caixa: "disponib" acha a Disponibilidade, "mtta" acha as telas do COS pela pergunta;
   - mais de uma palavra: a tela precisa ter todas, em qualquer um dos três ("pcm semana");
   - a área com resultado abre, a sem resultado some; o pedaço achado fica em destaque e, quando ele só está na pergunta,
     a pergunta aparece embaixo do nome, para a pessoa ver por que a tela veio;
   - as telas que abrem por dentro de outra (o Relatório semanal, na Central de emissão: li.menu-dentro) só aparecem na
     busca, debaixo da de fora;
   - "/" leva ao campo, Enter abre a primeira, as setas andam pelos resultados, Esc limpa. Campo vazio = o menu volta como
     estava: as mesmas áreas abertas e, se ele estava recolhido no trilho, recolhido de novo (a busca abre o menu só
     enquanto se busca, sem gravar a escolha da pessoa).
   A largura do menu fica presa na máxima enquanto se busca: ela segue o maior nome à vista, e encolher a cada letra
   sacudia a tela; presa na de antes, o "Criador de relatório" quebrava em duas linhas (visto no navegador). */
(function () {
  // ── as contas, sem a página (o node as roda em tests/test_menu_busca.py) ──
  function sem(s) { return String(s || "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase(); }
  function palavras(q) { return sem(q).split(/\s+/).filter(Boolean); }

  // a tela casa com a busca? 0 = não; 1 = pelos nomes (a área, a tela de fora e a tela); 2 = só com a pergunta
  function achar(ps, area, fora, nome, pergunta) {
    var nomes = sem(area + " " + (fora ? fora + " " : "") + nome), tudo = nomes + " " + sem(pergunta);
    if (!ps.length || !ps.every(function (p) { return tudo.indexOf(p) >= 0; })) return 0;
    return ps.every(function (p) { return nomes.indexOf(p) >= 0; }) ? 1 : 2;
  }

  // os pedaços achados, no texto original ([início, fim)), juntos quando se encostam: "inversor" acha o "Inversores",
  // "relatorio" o "Relatório" (o acento sai só na comparação)
  function faixas(texto, ps) {
    var mapa = [], n = "";
    for (var i = 0; i < texto.length; i++) {
      var c = sem(texto[i]);
      for (var k = 0; k < c.length; k++) mapa.push(i);
      n += c;
    }
    var todas = [];
    ps.forEach(function (p) {
      for (var j = n.indexOf(p); j >= 0; j = n.indexOf(p, j + p.length)) todas.push([mapa[j], mapa[j + p.length - 1] + 1]);
    });
    todas.sort(function (x, y) { return x[0] - y[0]; });
    var juntas = [];
    todas.forEach(function (f) {
      var u = juntas[juntas.length - 1];
      if (u && f[0] <= u[1]) u[1] = Math.max(u[1], f[1]); else juntas.push(f.slice());
    });
    return juntas;
  }

  // a pergunta longa vira um trecho em volta do 1º pedaço achado (no menu estreito, a pergunta inteira tomava 4 linhas)
  function trecho(texto, ps) {
    if (texto.length <= 72) return texto;
    var f = faixas(texto, ps), ini = f.length ? f[0][0] : 0;
    var de = Math.max(0, ini - 24);
    if (de > 0) { var b = texto.lastIndexOf(" ", de); de = b > 0 ? b + 1 : 0; }
    var ate = Math.min(texto.length, de + 72);
    if (ate < texto.length) { var e = texto.lastIndexOf(" ", ate); if (e > de + 30) ate = e; }
    return (de > 0 ? "… " : "") + texto.slice(de, ate).trim() + (ate < texto.length ? " …" : "");
  }

  if (typeof window !== "undefined") {
    window.NexusMenuBusca = {sem: sem, palavras: palavras, achar: achar, faixas: faixas, trecho: trecho};
  }

  // ── a página ──
  var campo = document.getElementById("menu-busca");
  if (!campo) return;
  var raiz = document.documentElement;
  var menu = campo.closest(".menu");
  var caixa = campo.closest(".menu-busca");
  var conta = document.getElementById("menu-busca-conta");
  var limpa = caixa.querySelector(".menu-busca-limpa");
  var nada = menu.querySelector(".menu-busca-nada");
  var inicio = menu.querySelector(".item-inicio");

  var torres = [].map.call(menu.querySelectorAll(".torre"), function (d) {
    var span = d.querySelector("summary span");
    var fora = null;
    var telas = [].map.call(d.querySelectorAll("ul > li"), function (li) {
      var a = li.querySelector("a");
      var t = {li: li, a: a, nome: a.textContent.trim(), pergunta: a.getAttribute("data-pergunta") || "",
               dentro: li.classList.contains("menu-dentro")};
      if (t.dentro) t.fora = fora; else fora = t;
      return t;
    });
    return {d: d, span: span, nome: span ? span.textContent.trim() : "", telas: telas};
  });

  // o texto com <mark> nos pedaços achados
  function realcar(el, texto, ps) {
    var frag = document.createDocumentFragment(), pos = 0;
    faixas(texto, ps).forEach(function (f) {
      if (f[0] > pos) frag.appendChild(document.createTextNode(texto.slice(pos, f[0])));
      var m = document.createElement("mark");
      m.className = "menu-achado";
      m.textContent = texto.slice(f[0], f[1]);
      frag.appendChild(m);
      pos = f[1];
    });
    if (pos < texto.length) frag.appendChild(document.createTextNode(texto.slice(pos)));
    el.replaceChildren(frag);
    return el;
  }

  var antes = null;        // como o menu estava antes da busca: as áreas abertas
  var doTrilho = false;    // a busca abriu o trilho recolhido: volta a recolher quando acabar

  function abrirDoTrilho() {
    if (raiz.classList.contains("menu-recolhido") && window.innerWidth > 820) {
      raiz.classList.remove("menu-recolhido");
      doTrilho = true;
    }
  }
  function voltarAoTrilho() {
    if (doTrilho && !campo.value.trim()) { raiz.classList.add("menu-recolhido"); doTrilho = false; }
  }

  function restaurar() {
    torres.forEach(function (t, i) {
      t.d.hidden = false;
      if (antes) t.d.open = antes[i];
      if (t.span) t.span.textContent = t.nome;
      t.telas.forEach(function (s) { s.li.hidden = s.dentro; s.a.textContent = s.nome; });
    });
    if (inicio) inicio.hidden = false;
    nada.hidden = true;
    conta.hidden = true;
    limpa.hidden = true;
    menu.classList.remove("menu-buscando");
    menu.style.width = "";
    antes = null;
  }

  function buscar() {
    var q = campo.value.trim();
    var ps = palavras(q);
    if (!ps.length) { restaurar(); return; }
    if (!antes) {
      antes = torres.map(function (t) { return t.d.open; });
      // a largura máxima do menu (224 px; 196 na tela média): a pergunta e a tela de dentro, um passo para dentro, cabem
      // sem quebrar o nome, e ela não muda mais até a busca acabar. No celular (até 820 px) o menu já é a largura da tela
      var max = parseFloat(getComputedStyle(menu).maxWidth);
      if (window.innerWidth > 820 && !isNaN(max)) menu.style.width = Math.max(menu.getBoundingClientRect().width, max) + "px";
      menu.classList.add("menu-buscando");
    }
    limpa.hidden = false;
    var nTelas = 0, nAreas = 0;
    torres.forEach(function (t) {
      var achou = t.telas.map(function (s) { return achar(ps, t.nome, s.fora && s.fora.nome, s.nome, s.pergunta); });
      // a de dentro achada traz a de fora junto, sem destaque, para se ver onde ela abre
      var mostra = achou.map(function (x) { return x > 0; });
      t.telas.forEach(function (s, i) { if (achou[i] && s.dentro) mostra[t.telas.indexOf(s.fora)] = true; });
      var alguma = mostra.some(Boolean);
      t.d.hidden = !alguma;
      if (!alguma) return;
      nAreas++;
      t.d.open = true;
      if (t.span) realcar(t.span, t.nome, ps);
      t.telas.forEach(function (s, i) {
        s.li.hidden = !mostra[i];
        if (!mostra[i]) return;
        if (achou[i]) nTelas++;
        if (!achou[i]) { s.a.textContent = s.nome; return; }
        realcar(s.a, s.nome, ps);
        if (achou[i] === 2) {
          var p = document.createElement("span");
          p.className = "menu-pergunta";
          s.a.appendChild(realcar(p, trecho(s.pergunta, ps), ps));
        }
      });
    });
    if (inicio) inicio.hidden = !ps.every(function (p) { return "inicio".indexOf(p) >= 0; });
    nada.hidden = nTelas > 0 || (inicio && !inicio.hidden);
    nada.textContent = "Nenhuma tela com “" + q + "”. Tente outra palavra ou só o começo dela.";
    conta.hidden = !nTelas;
    conta.textContent = nTelas + (nTelas === 1 ? " tela" : " telas") + " em " + nAreas + (nAreas === 1 ? " área" : " áreas");
  }

  function aVista() {
    return [].filter.call(menu.querySelectorAll(".item-inicio, .torre:not([hidden]) li:not([hidden]) a"),
                          function (a) { return !a.hidden && a.offsetParent !== null; });
  }

  campo.addEventListener("input", buscar);
  campo.addEventListener("focus", abrirDoTrilho);
  campo.addEventListener("blur", function () {
    setTimeout(function () { if (!menu.contains(document.activeElement)) voltarAoTrilho(); }, 0);
  });
  campo.addEventListener("keydown", function (ev) {
    var lista;
    if (ev.key === "Enter") {
      lista = aVista();
      if (campo.value.trim() && lista.length) { ev.preventDefault(); lista[0].click(); }
    } else if (ev.key === "ArrowDown") {
      lista = aVista();
      if (campo.value.trim() && lista.length) { ev.preventDefault(); lista[0].focus(); }
    } else if (ev.key === "Escape") {
      ev.preventDefault();
      if (campo.value) { campo.value = ""; buscar(); } else campo.blur();
    }
  });
  // as setas andam pelos resultados; para cima do primeiro, o campo; o Esc volta ao campo
  menu.addEventListener("keydown", function (ev) {
    if (!menu.classList.contains("menu-buscando") || ev.target === campo || ev.target.tagName !== "A") return;
    var lista = aVista(), i = lista.indexOf(ev.target);
    if (i < 0) return;
    if (ev.key === "ArrowDown" && i < lista.length - 1) { ev.preventDefault(); lista[i + 1].focus(); }
    else if (ev.key === "ArrowUp") { ev.preventDefault(); (i > 0 ? lista[i - 1] : campo).focus(); }
    else if (ev.key === "Escape") { ev.preventDefault(); campo.focus(); campo.select(); }
  });
  menu.addEventListener("focusout", function (ev) {
    if (!menu.contains(ev.relatedTarget)) voltarAoTrilho();
  });
  limpa.addEventListener("click", function () { campo.value = ""; buscar(); campo.focus(); });
  // o botão de recolher durante a busca: vale a escolha da pessoa, a busca não recolhe de novo por conta própria
  var botao = document.getElementById("recolhe-menu");
  if (botao) botao.addEventListener("click", function () { doTrilho = false; });
  // "/" fora de campo de texto leva à busca (o "[" recolhe o menu: o mesmo jeito de atalho)
  document.addEventListener("keydown", function (ev) {
    if (ev.key !== "/" || ev.ctrlKey || ev.metaKey || ev.altKey) return;
    var t = ev.target;
    if (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)) return;
    if (campo.offsetParent === null) return;   // o menu fechado atrás do botão Menu, no celular
    ev.preventDefault();
    campo.focus();
    campo.select();
  });
  // o navegador devolve o texto digitado ao voltar pela história: a busca reaparece filtrada, e não com o menu inteiro
  if (campo.value.trim()) buscar();
})();
