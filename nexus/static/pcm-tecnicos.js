/* Técnicos por usina (17/10/2026): a linha que abre o detalhe (como a tela de PT), o histórico da usina buscado na
   1ª abertura, a janela de pôr técnico e as confirmações.
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

  function porTecnico(id) {
    var tpl = document.getElementById("tu-por");
    var tr = document.querySelector('tr.cn-linha[data-usina="' + id + '"]');
    if (!tpl || !tr) return;
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

  function historico(caixa) {
    if (!caixa || caixa.dataset.carregado) return;
    caixa.dataset.carregado = "1";
    fetch(rota + "/historico?usina=" + encodeURIComponent(caixa.dataset.historico), {credentials: "same-origin"})
      .then(function (r) {
        // a sessão vencida volta o login (redirecionado): não é o histórico
        if (!r.ok || r.redirected) throw new Error(r.redirected ? "a sessão venceu: atualize a página" : "HTTP " + r.status);
        return r.text();
      })
      .then(function (html) { caixa.innerHTML = html; })
      .catch(function (e) {
        delete caixa.dataset.carregado;
        caixa.textContent = "Não consegui abrir o histórico (" + e.message + ").";
      });
  }

  // clicar na linha abre o detalhe logo abaixo (como na tela de PT); os botões e o × dentro dela fazem só o deles
  document.querySelectorAll("table.cn-expande tr.cn-linha").forEach(function (tr) {
    function alterna(ev) {
      if (ev.target.closest("a, button, form, input, label")) return;
      var det = tr.nextElementSibling;
      if (!det || !det.classList.contains("cn-detalhe")) return;
      det.hidden = !det.hidden;
      tr.setAttribute("aria-expanded", String(!det.hidden));
      if (!det.hidden) historico(det.querySelector("[data-historico]"));
    }
    tr.addEventListener("click", alterna);
    tr.addEventListener("keydown", function (ev) {
      if (ev.target !== tr) return;
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); alterna(ev); }
    });
  });

  document.addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-por]");
    if (b) porTecnico(b.dataset.por);
  });

  // escolher as usinas que o técnico vê (24/11/2026, Levi: "clicar no técnico e escolher as usinas, que ele vai ver"): a
  // janela com as usinas em operação por cliente, as dele já marcadas (as dele fora de operação também, para poder tirar),
  // a busca e o Salvar, que grava de uma vez (o servidor confere tudo de novo, dentro da trava)
  function escolherUsinas(tr) {
    var tpl = document.getElementById("tu-usinas");
    if (!tpl) return;
    corpo.innerHTML = "";
    corpo.appendChild(tpl.content.cloneNode(true));
    corpo.querySelector("[data-us-nome]").textContent = tr.dataset.nome;
    corpo.querySelector("input[name=pessoa_id]").value = tr.dataset.escolherUsinas;
    var dele = {};
    (tr.dataset.usinasDele || "").split(",").filter(Boolean).forEach(function (i) { dele[i] = true; });
    var lista = corpo.querySelector("[data-us-lista]"), conta = corpo.querySelector("[data-us-conta]");
    var porCliente = {}, ordem = [];
    (dados.usinas || []).forEach(function (u) {
      if (!u.op && !dele[String(u.id)]) return;
      if (!porCliente[u.cliente]) { porCliente[u.cliente] = []; ordem.push(u.cliente); }
      porCliente[u.cliente].push(u);
    });
    // as que ele já tem vêm primeiro (o cliente delas no alto e, dentro dele, as marcadas): com 190 usinas na lista, a
    // pessoa abria a janela e não via as dele sem rolar (a prova de 24/11/2026)
    function antes(lista_, marca) {
      return lista_.map(function (x, i) { return [marca(x) ? 0 : 1, i, x]; })
        .sort(function (a, b) { return a[0] - b[0] || a[1] - b[1]; }).map(function (x) { return x[2]; });
    }
    function eDele(u) { return dele[String(u.id)]; }
    ordem = antes(ordem, function (cli) { return porCliente[cli].some(eDele); });
    ordem.forEach(function (cli) { porCliente[cli] = antes(porCliente[cli], eDele); });
    ordem.forEach(function (cli) {
      var g = document.createElement("fieldset");
      g.className = "tu-us-grupo";
      g.dataset.cliente = sem(cli);
      var lg = document.createElement("legend");
      lg.textContent = cli;
      g.appendChild(lg);
      porCliente[cli].forEach(function (u) {
        var l = document.createElement("label");
        l.className = "tu-us-item";
        l.dataset.nome = sem(u.nome + " " + cli);
        var c = document.createElement("input");
        c.type = "checkbox"; c.name = "usina"; c.value = u.id; c.checked = !!dele[String(u.id)];
        l.appendChild(c);
        l.appendChild(document.createTextNode(" " + u.nome + (u.op ? "" : " (fora de operação)")));
        g.appendChild(l);
      });
      lista.appendChild(g);
    });
    function contar() {
      var n = lista.querySelectorAll("input:checked").length;
      conta.textContent = n + (n === 1 ? " usina marcada" : " usinas marcadas");
    }
    lista.addEventListener("change", contar);
    contar();
    corpo.querySelector("[data-us-busca]").addEventListener("input", function (ev) {
      var q = sem(ev.target.value).trim();
      lista.querySelectorAll(".tu-us-grupo").forEach(function (g) {
        var algum = false;
        g.querySelectorAll(".tu-us-item").forEach(function (l) {
          l.hidden = q && l.dataset.nome.indexOf(q) < 0;
          algum = algum || !l.hidden;
        });
        g.hidden = !algum;
      });
    });
    abrir();
  }
  document.querySelectorAll("tr[data-escolher-usinas]").forEach(function (tr) {
    tr.addEventListener("click", function (ev) {
      if (ev.target.closest("a, button, form, input, label")) return;
      escolherUsinas(tr);
    });
    tr.addEventListener("keydown", function (ev) {
      if (ev.target === tr && (ev.key === "Enter" || ev.key === " ")) { ev.preventDefault(); escolherUsinas(tr); }
    });
  });

  // as abas Por usina e Por técnico trocam na própria página (17/10/2026: o filtro não recarrega, a aba também não)
  var abaAgora = (new URL(location.href)).searchParams.get("ver") === "tecnico" ? "tecnico" : "usina";
  document.querySelectorAll(".cn-abas a[data-aba]").forEach(function (a) {
    a.addEventListener("click", function (ev) {
      // a Comparação com o App é outra página, sem as duas seções: ali o link navega (18/10/2026, o Levi clicava em
      // Por usina na Comparação e a tela não voltava, porque o clique era cancelado e não havia seção para mostrar)
      var aba = a.getAttribute("data-aba");
      var tem = false;
      document.querySelectorAll("[data-aba-secao]").forEach(function (s) { tem = tem || s.getAttribute("data-aba-secao") === aba; });
      if (!tem) return;
      ev.preventDefault();
      abaAgora = aba;
      document.querySelectorAll(".cn-abas a[data-aba]").forEach(function (o) {
        if (o === a) o.setAttribute("aria-current", "page"); else o.removeAttribute("aria-current");
      });
      document.querySelectorAll("[data-aba-secao]").forEach(function (s) { s.hidden = s.getAttribute("data-aba-secao") !== abaAgora; });
      document.querySelectorAll("[data-so-aba]").forEach(function (e) { e.hidden = e.getAttribute("data-so-aba") !== abaAgora; });
      var u = new URL(location.href);
      if (abaAgora === "usina") u.searchParams.delete("ver"); else u.searchParams.set("ver", abaAgora);
      history.replaceState(history.state, "", u.pathname + u.search + u.hash);
      if (window.FiltroLocal && window.FiltroLocal["tu-f"]) window.FiltroLocal["tu-f"].aplicar();
    });
  });
  // gravar volta para a aba de agora
  document.addEventListener("submit", function (ev) {
    var f = ev.target;
    if (f.id === "tu-f" || f.method.toLowerCase() !== "post") return;
    f.querySelectorAll('input[name="v_ver"]').forEach(function (i) { i.remove(); });
    if (abaAgora !== "usina") {
      var i = document.createElement("input");
      i.type = "hidden"; i.name = "v_ver"; i.value = abaAgora;
      f.appendChild(i);
    }
  });
})();
