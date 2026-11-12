/* Base > Mapa base (11/11/2026): manda o PMTiles do Brasil em partes (nexus/torres/base/mapa_base_tela.py).
   Cada parte vai com o SHA-256 dela (o servidor confere); a parte que falha vai de novo (até 5 vezes); o servidor diz
   quanto já tem (a subida retoma de onde parou, também depois de recarregar a página e escolher o mesmo arquivo). No
   fim, o servidor confere o arquivo inteiro antes de trocar o que estava no ar. */
(function () {
  "use strict";
  var f = document.querySelector("form[data-mb-form]");
  if (!f) return;
  var campo = f.querySelector("#mb-arquivo"), sha = f.querySelector("#mb-sha");
  var caixa = f.querySelector(".mb-progresso"), barra = caixa.querySelector(".mb-barra span"), msg = caixa.querySelector("p");
  var parar = f.querySelector("[data-mb-parar]"), enviar = f.querySelector('button[type="submit"]');
  var PARTE = parseInt(f.getAttribute("data-parte-max"), 10), parado = false;

  function dizer(t) { msg.textContent = t; }
  function gb(n) { return (n / 1073741824).toFixed(2).replace(".", ",") + " GB"; }
  function hex(buf) {
    return Array.prototype.map.call(new Uint8Array(buf), function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
  }
  function pedir(url, opcoes) {
    return fetch(url, Object.assign({ credentials: "same-origin" }, opcoes)).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) { return { ok: r.ok, status: r.status, j: j }; });
    });
  }
  function esperar(ms) { return new Promise(function (ok) { setTimeout(ok, ms); }); }

  function mandarParte(arq, ini, tentativa) {
    if (parado) return Promise.reject(new Error("parado"));
    var pedaco = arq.slice(ini, Math.min(ini + PARTE, arq.size));
    return pedaco.arrayBuffer().then(function (buf) {
      return crypto.subtle.digest("SHA-256", buf).then(function (h) {
        return pedir(f.getAttribute("data-parte") + "?offset=" + ini, {
          method: "POST", body: buf, headers: { "Content-Type": "application/octet-stream", "X-Sha256": hex(h) } });
      });
    }).then(function (r) {
      if (r.ok) return r.j.recebido;
      if (r.status === 409 && typeof r.j.recebido === "number") return r.j.recebido;      // o servidor diz onde está
      throw new Error(r.j.erro || ("HTTP " + r.status));
    }).catch(function (e) {
      if (parado || tentativa >= 5) throw e;
      dizer("A parte em " + gb(ini) + " falhou (" + e.message + "): tentando de novo.");
      return esperar(2000 * (tentativa + 1)).then(function () { return mandarParte(arq, ini, tentativa + 1); });
    });
  }

  function seguir(arq, recebido, t0, ini0) {
    var pct = arq.size ? recebido / arq.size : 1;
    barra.style.width = (pct * 100).toFixed(1) + "%";
    var seg = (Date.now() - t0) / 1000, mbs = (recebido - ini0) / 1048576 / Math.max(seg, 1);
    dizer(gb(recebido) + " de " + gb(arq.size) + " (" + (pct * 100).toFixed(1).replace(".", ",") + "%)" +
          (seg > 3 ? " · " + mbs.toFixed(1).replace(".", ",") + " MB/s" : ""));
    if (recebido >= arq.size) return Promise.resolve();
    return mandarParte(arq, recebido, 0).then(function (novo) { return seguir(arq, novo, t0, ini0); });
  }

  f.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var arq = campo.files && campo.files[0];
    if (!arq) return;
    parado = false;
    caixa.hidden = false;
    parar.hidden = false;
    enviar.disabled = true;
    dizer("Abrindo a subida…");
    pedir(f.getAttribute("data-iniciar"), {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tamanho: arq.size, sha256: (sha.value || "").trim() }) })
      .then(function (r) {
        if (!r.ok) throw new Error(r.j.erro || ("HTTP " + r.status));
        var ja = (r.j.parcial && r.j.parcial.recebido) || 0;
        return seguir(arq, ja, Date.now(), ja);
      })
      .then(function () {
        dizer("Arquivo inteiro no servidor: conferindo (leva cerca de um minuto)…");
        return pedir(f.getAttribute("data-concluir"), { method: "POST" });
      })
      .then(function (r) {
        if (!r.ok) throw new Error(r.j.erro || ("HTTP " + r.status));
        dizer("Pronto: o mapa base está no ar. SHA-256 " + r.j.pronto.sha256 + ".");
        setTimeout(function () { location.reload(); }, 2500);
      })
      .catch(function (e) {
        dizer(e.message === "parado" ? "Parado. Escolha o mesmo arquivo para continuar de onde parou." : "Não subiu: " + e.message);
      })
      .then(function () { enviar.disabled = false; parar.hidden = true; });
  });
  parar.addEventListener("click", function () { parado = true; });
})();
