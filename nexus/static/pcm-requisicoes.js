/* As requisições de material (12/11/2026, item 6 da 2ª rodada). A lista e o que grava moram na ponte do login do Fracttal
   (/os/_nexus/inventario/requisicoes: o cookie dele só chega em /os); os endereços vêm dos data-* da página e do pedaço, postos
   pela raiz, e passam pelo nexusRota. Ao chegar a lista, a página pede o automático das de Rank B e C (data-rq-auto-pode e
   data-rq-auto-n do pedaço; na sessão de quem abriu) e acompanha o andamento pelo automatico.json, a cada 3 s; no fim, relê a
   lista. "Aceitar" e "Recusar" pedem a confirmação e mandam o comentário (o do Recusar é obrigatório); o ok recarrega a página,
   que mostra o aviso, e o erro aparece na própria requisição, com o link do login quando falta. */
(function () {
  var lista = document.querySelector("[data-rq-lista]");
  if (!lista) return;
  var caixaAuto = document.querySelector("[data-rq-auto-estado]");
  var olhando = null;

  function json(r) {
    return r.json().then(function (d) { return {r: r, d: d || {}}; }, function () { return {r: r, d: {}}; });
  }

  function escrever(alvo, texto, login) {
    while (alvo.firstChild) alvo.removeChild(alvo.firstChild);
    alvo.appendChild(document.createTextNode(texto));
    if (typeof login === "string" && login) {      // o `login` do portão é um true, não um endereço
      alvo.appendChild(document.createTextNode(" "));
      var a = document.createElement("a");
      a.href = login;
      a.textContent = "Entrar pelo Fracttal";
      alvo.appendChild(a);
    }
    alvo.hidden = false;
  }

  function erroNaLista(texto, login) {
    var div = document.createElement("div");
    div.className = "cn-erro";
    div.setAttribute("role", "alert");
    var b = document.createElement("b");
    div.appendChild(b);
    escrever(b, texto, login);
    while (lista.firstChild) lista.removeChild(lista.firstChild);
    lista.appendChild(div);
  }

  function carregar(pedirAutomatico) {
    fetch(window.nexusRota(lista.getAttribute("data-rq-fonte")), {credentials: "same-origin", headers: {"Accept": "text/html"}})
      .then(function (r) {
        if (r.ok) return r.text().then(function (html) { lista.innerHTML = html; ligar(); if (pedirAutomatico) automatico(false); });
        return json(r).then(function (x) {
          erroNaLista(x.d.erro || ("Não consegui ler as requisições agora (HTTP " + x.r.status + "): tente de novo."),
                      x.d.sessao_encerrada ? x.d.entrar : x.d.login);
        });
      })
      .catch(function () { erroNaLista("Não consegui falar com o Nexus agora: tente de novo em instantes."); });
  }

  function mostrarAuto(texto) {
    if (!caixaAuto) return;
    var span = caixaAuto.querySelector("span") || caixaAuto;
    span.textContent = texto;
    caixaAuto.hidden = !texto;
  }

  function acompanhar() {
    if (olhando || !caixaAuto) return;
    olhando = window.setInterval(function () {
      fetch(window.nexusRota(caixaAuto.getAttribute("data-rq-auto-estado")), {credentials: "same-origin"})
        .then(json)
        .then(function (x) {
          if (!x.r.ok) return;
          mostrarAuto(x.d.texto || "");
          if (!x.d.andando) {
            window.clearInterval(olhando);
            olhando = null;
            carregar(false);
          }
        })
        .catch(function () {});
    }, 3000);
  }

  function automatico(clicado) {
    var raiz = lista.querySelector("[data-rq-raiz]");
    if (!raiz) return;
    if (!clicado && (raiz.getAttribute("data-rq-auto-pode") !== "1" || raiz.getAttribute("data-rq-auto-n") === "0")) return;
    fetch(window.nexusRota(lista.getAttribute("data-rq-automatico")), {
      method: "POST", credentials: "same-origin", headers: {"Accept": "application/json", "Content-Type": "application/json"},
      body: "{}"
    }).then(json).then(function (x) {
      if (x.r.ok && x.d.ok) { mostrarAuto(x.d.mensagem || ""); acompanhar(); return; }
      if (clicado) erroNaLista(x.d.erro || ("O automático não começou (HTTP " + x.r.status + ")."), x.d.login);
    }).catch(function () {});
  }

  function enviar(form, pergunta) {
    var campo = form.querySelector('[name="comentario"]');
    var erro = form.querySelector("[data-rq-erro]");
    if (form.hasAttribute("data-rq-recusar") && campo && !campo.value.trim()) {
      if (erro) escrever(erro, "Recusar pede o comentário.");
      campo.focus();
      return;
    }
    if (!window.confirm(pergunta)) return;
    var botao = form.querySelector('button[type="submit"]');
    if (botao) botao.disabled = true;
    fetch(window.nexusRota(form.getAttribute("data-rq-url")), {
      method: "POST", credentials: "same-origin", headers: {"Accept": "application/json", "Content-Type": "application/json"},
      body: JSON.stringify({comentario: campo ? campo.value : ""})
    }).then(json).then(function (x) {
      if (x.r.ok && x.d.ok) { window.location.assign(window.nexusRota(x.d.volta || window.location.pathname)); return; }
      if (erro) escrever(erro, x.d.erro || ("O Nexus não respondeu como esperado (HTTP " + x.r.status + "): pode ter gravado. " +
                                            "Recarregue a página e confira antes de tentar de novo."),
                         x.d.sessao_encerrada ? x.d.entrar : x.d.login);
      if (botao) botao.disabled = false;
    }).catch(function () {
      if (erro) escrever(erro, "Não consegui falar com o Nexus agora, e o pedido pode ter chegado: recarregue a página e confira " +
                               "antes de tentar de novo.");
      if (botao) botao.disabled = false;
    });
  }

  function ligar() {
    Array.prototype.forEach.call(lista.querySelectorAll("form[data-rq-aceitar]"), function (f) {
      f.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var os = f.getAttribute("data-rq-os");
        enviar(f, "Aceitar a requisição" + (os ? " da OS " + os : "") + "? O Nexus aprova, faz a saída ligada à OS e ela vai " +
                  "para Entrega total, no Fracttal, com o seu login.");
      });
    });
    Array.prototype.forEach.call(lista.querySelectorAll("form[data-rq-recusar]"), function (f) {
      f.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var os = f.getAttribute("data-rq-os");
        enviar(f, "Recusar a requisição" + (os ? " da OS " + os : "") + "? O técnico já usou a peça: a recusa só registra no " +
                  "Fracttal.");
      });
    });
    var agora = lista.querySelector("[data-rq-auto-agora]");
    if (agora) agora.addEventListener("click", function () { agora.disabled = true; automatico(true); });
  }

  carregar(true);
  if (caixaAuto && !caixaAuto.hidden) acompanhar();
})();
