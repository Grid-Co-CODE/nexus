/* O Raio-X em abas (16/11/2026, Levi: "como a gente separa por categoria, deixou várias abinhas ali dentro da página [...]
   bem cara de televisão"). A página já vem com todas as partes (a leitura do processo é uma só); as abas só mostram uma e
   escondem as outras, sem ir ao servidor, e o endereço guarda a aba (?aba=), para o "Ler de novo", o favorito e a TV.
   "Atualizar sozinho" lê a página de novo a cada 30 s, na mesma aba (a escolha fica no navegador); "Tela cheia" põe só o
   Raio-X na tela, sem o menu. Sem JavaScript, as abas são links comuns. */
(function () {
  var raiz = document.querySelector("[data-rx]");
  if (!raiz) return;
  var abas = [].slice.call(raiz.querySelectorAll("[data-rx-aba]"));
  var paineis = [].slice.call(raiz.querySelectorAll("[data-rx-painel]"));
  var ler = raiz.querySelector("[data-rx-ler]");
  var CHAVE = "nexus.raiox.sozinho", ESPERA_MS = 30000;

  function endereco(aba) {
    var u = new URL(location.href);
    u.searchParams.set("aba", aba);
    u.hash = "";
    return u;
  }

  function abrir(aba) {
    abas.forEach(function (a) {
      if (a.getAttribute("data-rx-aba") === aba) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    paineis.forEach(function (p) { p.hidden = p.getAttribute("data-rx-painel") !== aba; });
    var u = endereco(aba);
    try { history.replaceState(null, "", u.pathname + u.search); } catch (e) {}
    if (ler) ler.setAttribute("href", u.pathname + u.search);
  }

  abas.forEach(function (a) {
    a.addEventListener("click", function (ev) {
      if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button) return;     // abrir em outra aba segue o link
      ev.preventDefault();
      abrir(a.getAttribute("data-rx-aba"));
    });
  });

  // "Atualizar sozinho": a mesma aba, a cada 30 s; a marca fica neste navegador (localStorage pode faltar: aí vale só aqui)
  var caixa = raiz.querySelector("[data-rx-sozinho]"), relogio = 0;
  function agendar() {
    clearTimeout(relogio);
    if (!caixa || !caixa.checked) return;
    relogio = setTimeout(function () {
      var atual = raiz.querySelector("[data-rx-aba][aria-current]");
      location.replace(endereco(atual ? atual.getAttribute("data-rx-aba") : "agora").href);
    }, ESPERA_MS);
  }
  if (caixa) {
    try { caixa.checked = localStorage.getItem(CHAVE) === "1"; } catch (e) {}
    caixa.addEventListener("change", function () {
      try { localStorage.setItem(CHAVE, caixa.checked ? "1" : "0"); } catch (e) {}
      agendar();
    });
    agendar();
  }

  // "Tela cheia": só o Raio-X (a TV); o Esc do navegador sai
  var cheia = raiz.querySelector("[data-rx-cheia]");
  if (cheia) {
    if (!raiz.requestFullscreen) cheia.hidden = true;
    cheia.addEventListener("click", function () {
      if (document.fullscreenElement) document.exitFullscreen();
      else raiz.requestFullscreen().catch(function () {});
    });
    document.addEventListener("fullscreenchange", function () {
      cheia.lastChild.textContent = document.fullscreenElement ? " Sair da tela cheia" : " Tela cheia";
    });
  }
})();
