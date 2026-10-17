/* Técnicos por usina (17/10/2026): a janela de pôr técnico, o histórico da usina e as confirmações.
   A lista de pessoas vem uma vez na página (#tu-dados: id, nome e equipe; nunca o e-mail); a janela de pôr técnico é UMA
   só, montada a cada clique: no alto quem esteve na usina (a evidência da linha), depois a mesma equipe, depois as outras.
   O servidor confere tudo de novo ao gravar (a pessoa de campo, a usina, o nome no Fracttal e o código saem do cadastro). */
(function () {
  "use strict";
  var dados = JSON.parse(document.getElementById("tu-dados").textContent);
  var dlg = document.getElementById("tu-det");
  var corpo = dlg.querySelector("[data-det-corpo]");
  // o endereço vem da página já com o prefixo ({{ raiz }}); o nexusRota é idempotente
  var rota = window.nexusRota(dlg.dataset.rota);

  function sem(s) {
    return String(s || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }
  function abrir() { if (!dlg.open) dlg.showModal(); }
  function fechar() { if (dlg.open) dlg.close(); corpo.innerHTML = ""; }

  dlg.addEventListener("click", function (ev) {
    // o <dialog> não tem margem interna: o clique que cai nele mesmo (e não no corpo) foi no véu
    if (ev.target === dlg || ev.target.closest("[data-det-fechar]")) fechar();
  });

  document.addEventListener("submit", function (ev) {
    var f = ev.target;
    if (f.dataset && f.dataset.confirmar && !window.confirm(f.dataset.confirmar)) ev.preventDefault();
  });

  function grupo(titulo, pessoas, lista) {
    if (!pessoas.length) return;
    var h = document.createElement("div");
    h.className = "tu-grupo";
    h.textContent = titulo;
    lista.appendChild(h);
    pessoas.forEach(function (p) {
      var l = document.createElement("label");
      l.className = "tu-pessoa";
      l.dataset.nome = sem(p.nome);
      var r = document.createElement("input");
      r.type = "radio";
      r.name = "pessoa_id";
      r.value = p.id;
      l.appendChild(r);
      l.appendChild(document.createTextNode(" " + p.nome));
      lista.appendChild(l);
    });
  }

  function porTecnico(tr) {
    var tpl = document.getElementById("tu-por");
    if (!tpl) return;
    corpo.innerHTML = "";
    corpo.appendChild(tpl.content.cloneNode(true));
    corpo.querySelector("[data-por-usina]").textContent = tr.dataset.usinaNome;
    corpo.querySelector("input[name=usina_id]").value = tr.dataset.usina;
    var ja = {};
    tr.querySelectorAll(".tu-tec input[name=pessoa_id]").forEach(function (i) { ja[i.value] = true; });
    var evid = (tr.dataset.evid || "").split(",").filter(Boolean);
    var livres = dados.pessoas.filter(function (p) { return !ja[String(p.id)]; });
    var esteve = livres.filter(function (p) { return evid.indexOf(String(p.id)) >= 0; });
    var equipe = livres.filter(function (p) {
      return evid.indexOf(String(p.id)) < 0 && tr.dataset.equipe && String(p.equipe_id) === tr.dataset.equipe;
    });
    var outras = livres.filter(function (p) { return esteve.indexOf(p) < 0 && equipe.indexOf(p) < 0; });
    var lista = corpo.querySelector("[data-por-lista]");
    grupo("Esteve na usina", esteve, lista);
    grupo("Da mesma equipe", equipe, lista);
    grupo("Outras pessoas de campo", outras, lista);
    var enviar = corpo.querySelector("[data-por-enviar]");
    lista.addEventListener("change", function () { enviar.disabled = !lista.querySelector("input:checked"); });
    corpo.querySelector("[data-por-busca]").addEventListener("input", function (ev) {
      var q = sem(ev.target.value).trim();
      lista.querySelectorAll(".tu-pessoa").forEach(function (l) { l.hidden = q && l.dataset.nome.indexOf(q) < 0; });
    });
    abrir();
  }

  function historico(id) {
    corpo.innerHTML = '<p class="pcm-sub">Carregando o histórico…</p>';
    abrir();
    fetch(rota + "/historico?usina=" + encodeURIComponent(id), {credentials: "same-origin"})
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.text(); })
      .then(function (html) { corpo.innerHTML = html; })
      .catch(function (e) { corpo.innerHTML = '<p class="pcm-sub">Não consegui abrir o histórico (' + e.message + ").</p>"; });
  }

  document.addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-por]");
    if (b) { porTecnico(b.closest("tr")); return; }
    var h = ev.target.closest("[data-historico]");
    if (h) historico(h.dataset.historico);
  });
})();
