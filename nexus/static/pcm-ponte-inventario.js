/* A ponte do inventário (26/10/2026): o que fala com o Fracttal (gravar a régua acordada, cadastrar a peça nova) não roda em
   /t/pcm, porque o login do Fracttal (o cookie os_sessao) só chega aos endereços debaixo de /os. O formulário com
   data-ponte vai por fetch para a rota da ponte (o action dele, /os/_nexus/inventario/...), que responde JSON:
   {ok, volta} recarrega a página (que mostra o aviso), {erro, login?} aparece no alto da página, com o link para entrar pelo
   Fracttal quando é isso que falta. Quem não tem JavaScript não grava no Fracttal: de propósito, a resposta é JSON. */
(function () {
  function aviso() {
    var caixa = document.querySelector("[data-ponte-aviso]");
    if (!caixa) return null;
    while (caixa.firstChild) caixa.removeChild(caixa.firstChild);
    return caixa;
  }
  function mostrar(texto, login) {
    var caixa = aviso();
    if (!caixa) return;
    var div = document.createElement("div");
    div.className = "cn-erro";
    div.setAttribute("role", "alert");
    var b = document.createElement("b");
    b.textContent = texto;
    div.appendChild(b);
    if (login) {
      div.appendChild(document.createTextNode(" "));
      var a = document.createElement("a");
      a.href = login;
      a.textContent = "Entrar pelo Fracttal";
      div.appendChild(a);
    }
    caixa.appendChild(div);
    if (caixa.scrollIntoView) caixa.scrollIntoView({block: "nearest"});
  }
  document.addEventListener("submit", function (ev) {
    var f = ev.target;
    if (!f || !f.hasAttribute || !f.hasAttribute("data-ponte")) return;
    ev.preventDefault();
    var botao = f.querySelector('button[type="submit"]');
    if (botao) botao.disabled = true;
    fetch(window.nexusRota(f.getAttribute("action")), {
      method: "POST", body: new FormData(f), credentials: "same-origin", headers: {"Accept": "application/json"}
    }).then(function (r) {
      return r.json().then(function (d) { return {r: r, d: d || {}}; }, function () { return {r: r, d: {}}; });
    }).then(function (x) {
      if (x.r.ok && x.d.ok) { window.location.assign(window.nexusRota(x.d.volta || window.location.pathname)); return; }
      mostrar(x.d.erro || "O Nexus não respondeu como esperado (HTTP " + x.r.status + "). Nada foi anotado.", x.d.login);
      if (botao) botao.disabled = false;
    }).catch(function () {
      mostrar("Não consegui falar com o Nexus agora. Nada foi anotado; confira a página antes de tentar de novo.");
      if (botao) botao.disabled = false;
    });
  });
})();
