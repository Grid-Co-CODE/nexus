/* O vídeo wall do Mapa de equipe (12/11/2026, Levi: "Prepare um modo vídeo wall que apareça informações como no anexo 1
   do lado esquerdo do mapa!"). O mapa é o do campo-mapa.js; aqui só o que é da TV:
   - o relógio (hora de Brasília);
   - a releitura da tela a cada 2 minutos (a escolha dele), NO LUGAR desde 27/11/2026: os dados trocam e o mapa fica (o
     satélite fixo e o radar não baixam de novo); a recarga inteira é uma por hora, depois de conferir que o Nexus
     responde. Com o servidor fora, a tela fica com o que tem e diz desde quando; a sessão que caiu leva ao Entrar;
   - a lista das ocorrências que não cabe rola sozinha, devagar, e volta ao topo ("Rolar sozinha devagar", a escolha
     dele): para 5 s em cima e embaixo. Roda também com os efeitos de animação do Windows desligados, porque sem ela a
     lista ficaria cortada (o mesmo caso das divisas pulsando);
   - os controles (sair, zoom, focos, fundo) aparecem ao mexer o mouse ou apertar uma tecla, e somem em 4 s. */
(function () {
  "use strict";
  var raiz = document.querySelector("[data-eq-tv]");
  if (!raiz) return;

  // ── o relógio ──────────────────────────────────────────────────────────────────────────────────────────────────
  var hora = raiz.querySelector(".eqtv-hora"), data = raiz.querySelector(".eqtv-data");
  function relogio() {
    var agora = new Date();
    try {
      hora.textContent = agora.toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
      data.textContent = agora.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo", weekday: "long", day: "2-digit", month: "2-digit" });
    } catch (e) { /* navegador sem fuso: fica a hora que o servidor escreveu */ }
  }
  relogio();
  setInterval(relogio, 15000);

  // ── a releitura a cada 2 minutos ───────────────────────────────────────────────────────────────────────────────
  var segundos = parseInt(raiz.getAttribute("data-recarrega-s"), 10) || 120;
  var saude = raiz.getAttribute("data-saude");
  var estado = raiz.querySelector(".eqtv-estado");
  function hhmm() {
    try { return new Date().toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" }); }
    catch (e) { return ""; }
  }
  var foraDesde = "";
  function fora() {
    foraDesde = foraDesde || hhmm();
    estado.textContent = "O Nexus não respondeu desde " + foraDesde + ". A tela fica com o que tem e tenta de novo em " +
      Math.round(segundos / 60) + " min.";
    estado.hidden = false;
    setTimeout(reler, segundos * 1000);
  }
  // a recarga inteira, uma por hora (27/11/2026): pega o JS e o CSS de uma subida e começa o mapa do zero; o satélite
  // fixo baixa de novo só aqui (a cota grátis da Esri: 2 milhões de imagens por mês)
  var RELEITURAS_ATE_RECARREGAR = Math.max(1, Math.round(3600 / segundos)), feitas = 0;
  function recarregar() {
    fetch(saude, { cache: "no-store", credentials: "same-origin" }).then(function (r) {
      if (!r.ok) throw new Error(String(r.status));
      location.reload();
    }).catch(fora);
  }
  function substituir(doc, sel) {
    var a = raiz.querySelector(sel), b = doc.querySelector(sel);
    if (a && b) a.replaceWith(document.adoptNode(b));
  }
  // a troca no lugar: a coluna do COS (os números, os cartões e o rodapé), a contagem e as equipes em deslocamento do
  // mapa, o prazo da sessão e as duas listas da direita (a visão escolhida e a rolagem da mão ficam); os dados do mapa
  // vão ao campo-mapa.js pelo evento "eqtv:dados"
  function trocar(html) {
    var doc = new DOMParser().parseFromString(html, "text/html");
    var nova = doc.querySelector("[data-eq-tv]");
    if (!nova) { location.reload(); return; }
    [".eqtv-cos", ".eqtv-conta", ".eqtv-desloc", ".eqtv-prazo"].forEach(function (s) { substituir(doc, s); });
    ["ocorrencias", "tecnicos"].forEach(function (v) {
      var sel = '.eqtv-visao[data-tv-visao-so="' + v + '"]', velho = raiz.querySelector(sel), novo = nova.querySelector(sel);
      if (!velho || !novo) return;
      var l0 = velho.querySelector(".eqtv-lista"), topo = l0 ? l0.scrollTop : 0;
      velho.innerHTML = novo.innerHTML;
      var l1 = velho.querySelector(".eqtv-lista");
      if (l1) l1.scrollTop = topo;
    });
    var dados = doc.getElementById("eq-dados");
    if (dados) {
      try { document.dispatchEvent(new CustomEvent("eqtv:dados", { detail: JSON.parse(dados.textContent) })); }
      catch (e) { /* o mapa fica com o que tem */ }
    }
    var c = raiz.querySelector("[data-eqtv-rola]");
    rolar(c, c && c.querySelector(".eqtv-trilho"));
  }
  function reler() {
    feitas += 1;
    if (feitas >= RELEITURAS_ATE_RECARREGAR) { recarregar(); return; }
    fetch(location.href, { cache: "no-store", credentials: "same-origin" }).then(function (r) {
      if (!r.ok) throw new Error(String(r.status));
      return r.text();
    }).then(function (html) {
      // a troca que quebra (uma página diferente da esperada) recarrega a página inteira, como antes
      try { trocar(html); } catch (e) { location.reload(); return; }
      foraDesde = ""; estado.hidden = true;
      setTimeout(reler, segundos * 1000);
    }).catch(fora);
  }
  setTimeout(reler, segundos * 1000);

  // ── a lista que rola sozinha ───────────────────────────────────────────────────────────────────────────────────
  // as duas colunas que rolam (26/11/2026): a das ocorrências e a da linha do tempo
  function rolar(caixa, trilho) {
    if (!caixa || !trilho) return;
    var PARADA_MS = 5000, pos = 0, fase = "topo", desde = performance.now(), antes = desde;
    var passo = function (t) {
      if (!caixa.isConnected) return;          // a coluna trocada na releitura: este laço para, o da nova segue
      var sobra = trilho.scrollHeight - caixa.clientHeight;
      var dt = Math.min(100, t - antes);
      antes = t;
      if (sobra <= 2) {                       // cabe: nada rola
        pos = 0; fase = "topo"; desde = t;
      } else if (fase === "topo" || fase === "fim") {
        if (t - desde > PARADA_MS) {
          if (fase === "fim") { pos = 0; fase = "topo"; } else { fase = "desce"; }
          desde = t;
        }
      } else {
        // uma altura da caixa a cada 25 s: devagar, para dar tempo de ler de longe
        pos = Math.min(sobra, pos + caixa.clientHeight / 25000 * dt);
        if (pos >= sobra) { fase = "fim"; desde = t; }
      }
      trilho.style.transform = "translateY(" + (-pos).toFixed(1) + "px)";
      requestAnimationFrame(passo);
    };
    requestAnimationFrame(passo);
  }
  // a linha do tempo da direita não rola sozinha (27/11/2026, Levi: "não precisa ficar rolando automático não"): rola na mão
  var c1 = raiz.querySelector("[data-eqtv-rola]");
  rolar(c1, c1 && c1.querySelector(".eqtv-trilho"));

  // ── as duas visões da coluna da direita (27/11/2026, Levi: "Visão técnico, visão ocorrências") ─────────────────
  var colTl = raiz.querySelector("[data-tv-visao]");
  function visao(v) {
    if (!colTl) return;
    colTl.setAttribute("data-tv-visao", v);
    colTl.querySelectorAll("[data-tv-visao-so]").forEach(function (el) { el.hidden = el.getAttribute("data-tv-visao-so") !== v; });
    colTl.querySelectorAll("[data-tv-visao-bt]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-tv-visao-bt") === v)); });
    try { localStorage.setItem("nexus.equipe.tv.visao", v); } catch (e) { /* sem armazenamento */ }
  }
  if (colTl) {
    var guardada = "ocorrencias";
    try { guardada = localStorage.getItem("nexus.equipe.tv.visao") || "ocorrencias"; } catch (e) { /* sem armazenamento */ }
    visao(guardada === "tecnicos" ? "tecnicos" : "ocorrencias");
    colTl.addEventListener("click", function (e) {
      var b = e.target.closest("[data-tv-visao-bt]");
      if (b) visao(b.getAttribute("data-tv-visao-bt"));
    });
  }

  // ── os controles só ao mexer ───────────────────────────────────────────────────────────────────────────────────
  var esconder = 0;
  function mexeu() {
    raiz.classList.add("eqtv--mexeu");
    clearTimeout(esconder);
    esconder = setTimeout(function () { raiz.classList.remove("eqtv--mexeu"); }, 4000);
  }
  ["mousemove", "keydown", "touchstart"].forEach(function (ev) { document.addEventListener(ev, mexeu, { passive: true }); });
})();
