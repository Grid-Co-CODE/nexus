/* A prévia da folha nas telas da Central de emissão (14/10/2026): os quatro relatórios do PCM e o Relatório executivo.
   A folha é um documento à parte, na moldura (#rp-folha); "Imprimir / PDF" imprime só ela. Os do PCM ficam prontos ao
   carregar; o executivo se monta no navegador depois de ler os dados e avisa quando acabou (data-espera="aviso").
   A coluna da esquerda do executivo (o período e o escopo) também mora aqui. */
(function () {
  "use strict";
  var folha = document.getElementById("rp-folha"), escala = document.getElementById("rp-escala"),
      imprimir = document.getElementById("rp-imprimir"), montando = document.getElementById("rp-montando");

  // A folha é A4 de largura fixa, como no papel: numa tela estreita ela é reduzida inteira para caber (a prévia de
  // impressão), em vez de cortar a direita; a impressão sai sempre no tamanho certo (é a folha, não a prévia). Tabela
  // que não quebra linha (a dos religamentos com +30 linhas, 13/10/2026) passa da largura do A4: o Chrome encolhe a
  // página para caber ao imprimir, e a prévia faz o mesmo, alargando a folha até o conteúdo e reduzindo o todo.
  // A margem da direita (Levi, 14/10/2026: "a pré visualização ... deixa o texto comendo um pouco a margem da página
  // ... quando eu transformo em PDF fica normal!"): o scrollWidth vai só até o fim do conteúdo, sem a margem do papel,
  // e a folha alargada encostava o texto na borda, com uma barra de rolagem por cima. Agora ela ganha a mesma margem dos
  // dois lados, como no PDF, e não rola por dentro (a moldura tem o tamanho dela).
  function ajustar() {
    try {
      var d = folha.contentDocument, raiz = d.documentElement;
      raiz.style.overflow = "hidden";
      folha.style.width = "";
      // o papel é o elemento com a margem da folha: o body nos do PCM, a .rex-a4 no executivo (que já é mais larga que o
      // A4 na tela, 210 mm mais o recuo dela, como no painel). Só o conteúdo que passa do papel ganha a margem a mais.
      var papel = d.querySelector(folha.dataset.margem || "body") || d.body;
      var margem = parseFloat(getComputedStyle(papel).paddingRight) || 0;
      for (var i = 0; i < 3 && raiz.scrollWidth > folha.offsetWidth; i++) {
        var passa = papel.scrollWidth > papel.clientWidth + 1;
        folha.style.width = (raiz.scrollWidth + (passa ? margem : 0)) + "px";
      }
      var alt = Math.max(raiz.scrollHeight, d.body ? d.body.scrollHeight : 0);
      folha.style.height = alt + "px";
      var cabe = escala.parentNode.clientWidth - 2 * parseFloat(getComputedStyle(escala.parentNode).paddingLeft || 0);
      var s = Math.min(1, cabe / folha.offsetWidth);
      folha.style.transform = s < 1 ? "scale(" + s + ")" : "";
      escala.style.width = (folha.offsetWidth * s) + "px";
      escala.style.height = (alt * s) + "px";
    } catch (e) { /* folha de outra origem: fica o tamanho do CSS */ }
  }
  function pronta() {
    if (montando) montando.hidden = true;
    escala.classList.remove("rp-escala--montando");
    ajustar();
    imprimir.disabled = false;
  }
  function falhou(texto) {
    if (montando) {
      montando.hidden = false;
      montando.textContent = texto;
      montando.classList.add("rp-erro");
    }
    escala.hidden = true;
  }
  if (folha) {
    if (folha.dataset.espera === "aviso") {
      window.addEventListener("message", function (e) {
        if (e.source !== folha.contentWindow || e.origin !== location.origin || !e.data || !e.data.rx) return;
        if (e.data.pronto) pronta();
        else if (e.data.erro) falhou(e.data.erro);
      });
    } else {
      folha.addEventListener("load", pronta);
    }
    window.addEventListener("resize", ajustar);
    imprimir.addEventListener("click", function () {
      try { folha.contentWindow.focus(); folha.contentWindow.print(); }
      catch (e) { window.open(folha.src, "_blank", "noopener"); }
    });
  }

  // os do PCM: o recorte em cascata (trocar o cliente ou o cluster recarrega as listas, sem gerar a folha)
  document.querySelectorAll("[data-rp-cascata]").forEach(function (s) {
    s.addEventListener("change", function () { s.form.submit(); });
  });

  // ── o Relatório executivo: o período e o escopo do modal do painel do PCM, aqui na coluna ──
  var form = document.getElementById("rx-form");
  if (!form) return;
  var de = document.getElementById("rx-de"), ate = document.getElementById("rx-ate");
  var iso = function (d) { return d.toISOString().slice(0, 10); };
  var hoje = function () { return iso(new Date()); };
  // os presets são os do painel (rexPreset, js/relatorio_exec.js), conta por conta: a semana começa na segunda
  var PRESETS = ["sem", "semp", "mes", "mesp", "30d"];
  function faixa(p) {
    var hj = new Date(); hj.setHours(12);
    var d = new Date(hj), f;
    if (p === "sem") { d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return [iso(d), hoje()]; }
    if (p === "semp") { d.setDate(d.getDate() - ((d.getDay() + 6) % 7) - 7); f = new Date(d); f.setDate(f.getDate() + 6); return [iso(d), iso(f)]; }
    if (p === "mes") return [iso(new Date(d.getFullYear(), d.getMonth(), 1, 12)), hoje()];
    if (p === "mesp") return [iso(new Date(d.getFullYear(), d.getMonth() - 1, 1, 12)), iso(new Date(d.getFullYear(), d.getMonth(), 0, 12))];
    d.setDate(d.getDate() - 29);
    return [iso(d), hoje()];
  }
  // o chip aceso é o preset que dá exatamente o período escolhido (datas mexidas à mão: nenhum)
  function marcar() {
    var atual = PRESETS.filter(function (p) { var x = faixa(p); return x[0] === de.value && x[1] === ate.value; })[0];
    form.querySelectorAll("[data-p]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.p === atual)); });
  }
  form.querySelectorAll("[data-p]").forEach(function (b) {
    b.addEventListener("click", function () { var x = faixa(b.dataset.p); de.value = x[0]; ate.value = x[1]; marcar(); });
  });
  if (de && ate) {
    if (!de.value || !ate.value) { var x = faixa("mes"); de.value = x[0]; ate.value = x[1]; }   // o padrão do painel
    marcar();
    de.addEventListener("change", marcar);
    ate.addEventListener("change", marcar);
  }
  // a cascata do painel (rexEscopoMuda): escolher o cliente filtra a lista de usinas pelo começo do nome e, como lá,
  // começa a escolha das usinas de novo. O servidor manda todas; ao abrir, vale o cliente já escolhido.
  var cli = document.getElementById("rx-cli"), usi = document.getElementById("rx-usi");
  if (cli && usi) {
    var todas = Array.prototype.map.call(usi.options, function (o) { return [o.value, o.selected]; });
    var filtrar = function (manter) {
      var c = cli.value;
      usi.innerHTML = "";
      todas.forEach(function (x) {
        if (c && x[0].indexOf(c) !== 0) return;
        var o = document.createElement("option");
        o.value = x[0]; o.textContent = x[0]; o.selected = manter && x[1];
        usi.appendChild(o);
      });
    };
    filtrar(true);
    cli.addEventListener("change", function () { filtrar(false); });
  }
  form.addEventListener("submit", function (e) {
    if (de && ate && (!de.value || !ate.value || de.value > ate.value)) {
      e.preventDefault();
      var aviso = document.getElementById("rx-aviso");
      if (aviso) { aviso.hidden = false; aviso.textContent = "Confira o período: o início vem antes do fim."; }
    }
  });
})();
