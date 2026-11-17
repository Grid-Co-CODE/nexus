/* Comando > Contestações (16/11/2026, o redesenho; Levi: "deixe mais utilizável"). Sem JavaScript, tudo funciona por link
   e formulário (a lista leva a ?c=, o formulário volta com o aviso). Com ele:
   - o clique na lista troca o card da direita sem reler a página (o pedaço vem da rota do card) e o endereço guarda a
     escolhida; no celular, o card vem logo abaixo da lista e a página desce até ele;
   - escrever, resolver e reabrir gravam sem perder o texto quando o banco recusa (a frase aparece no próprio
     formulário); gravado, a página relê na contestação, com os números, a lista e o aviso do topo em dia.
   Os endereços saem do HTML (data-ct-card, data-rota) pelo nexusRota: nada a partir da raiz aqui. */
(function () {
  var fila = document.querySelector(".ct-fila");
  if (!fila) return;
  var rota = typeof nexusRota === "function" ? nexusRota : function (c) { return c; };
  var estreito = window.matchMedia ? window.matchMedia("(max-width: 899px)") : { matches: false };

  function ver() {
    return new URLSearchParams(location.search).get("ver") === "resolvidas" ? "resolvidas" : "abertas";
  }

  function marcar(id) {
    fila.querySelectorAll(".ct-item[data-ct-id]").forEach(function (a) {
      if (a.getAttribute("data-ct-id") === id) a.setAttribute("aria-current", "true");
      else a.removeAttribute("aria-current");
    });
  }

  function trocar(item) {
    var atual = document.getElementById("ct-detalhe");
    var id = item.getAttribute("data-ct-id");
    marcar(id);
    fila.classList.remove("ct-fila--auto");               // a escolhida agora é da pessoa (no celular, o card aparece)
    try { history.replaceState(null, "", item.getAttribute("href").split("#")[0]); } catch (e) {}
    if (atual) atual.setAttribute("aria-busy", "true");
    fetch(rota(item.getAttribute("data-ct-card")) + "?ver=" + ver(), { credentials: "same-origin" }).then(function (r) {
      if (r.redirected && /\/entrar/.test(r.url)) { location.reload(); return null; }     // a sessão do Nexus caiu
      if (!r.ok) throw new Error("O Nexus respondeu " + r.status);
      return r.text();
    }).then(function (html) {
      if (html === null) return;
      var caixa = document.createElement("div");
      caixa.innerHTML = html.trim();
      var novo = caixa.querySelector("#ct-detalhe");
      var velho = document.getElementById("ct-detalhe");
      if (!novo || !velho) { location.assign(item.href); return; }
      velho.replaceWith(novo);
      if (estreito.matches) novo.scrollIntoView({ block: "start" });
    }).catch(function () { location.assign(item.href); });   // sem o pedaço, o link de sempre
  }

  fila.addEventListener("click", function (ev) {
    var item = ev.target.closest(".ct-item[data-ct-card]");
    if (!item || ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button) return;   // abrir em outra aba segue o link
    ev.preventDefault();
    trocar(item);
  });

  fila.addEventListener("submit", function (ev) {
    var f = ev.target.closest("form[data-ct-acao]");
    if (!f || typeof window.nexusPedir !== "function") return;    // sem o pedido do Nexus, o formulário de sempre
    ev.preventDefault();
    var bt = f.querySelector("button[type=submit]");
    var rotulo = bt ? bt.textContent : "";
    if (bt) { bt.disabled = true; bt.textContent = "Salvando…"; }
    var falha = f.querySelector(".ct-falha");
    if (falha) falha.remove();
    window.nexusPedir(f.getAttribute("data-rota"), {
      method: "POST", body: new FormData(f),
      headers: { "Accept": "application/json", "X-Nexus-Parte": "1" }
    }).then(function () {
      var card = f.closest("#ct-detalhe");
      var u = new URL(location.href);
      if (card) u.searchParams.set("c", card.getAttribute("data-ct-id"));
      u.hash = "ct-detalhe";
      location.assign(u.toString());
      if (u.pathname + u.search === location.pathname + location.search) location.reload();
    }).catch(function (e) {
      if (bt) { bt.disabled = false; bt.textContent = rotulo; }
      var p = document.createElement("p");
      p.className = "ct-falha cn-t-critico";
      p.setAttribute("role", "alert");
      p.textContent = (e && e.message ? e.message : "Não consegui gravar agora.") + " Nada foi gravado; o texto continua aqui.";
      f.appendChild(p);
    });
  });
})();
