/* A ponte do inventário (26/10/2026): o que fala com o Fracttal (gravar a régua acordada, cadastrar a peça nova) não roda em
   /t/pcm, porque o login do Fracttal (o cookie os_sessao) só chega aos endereços debaixo de /os. O formulário com
   data-ponte vai por fetch para a rota da ponte (o action dele, /os/_nexus/inventario/...), que responde JSON:
   {ok, volta} recarrega a página (que mostra o aviso), {erro, login?} aparece no alto da página, com o link para entrar pelo
   Fracttal quando é isso que falta. Quem não tem JavaScript não grava no Fracttal: de propósito, a resposta é JSON.
   O formulário com data-ponte-espera (11/11/2026: todos os acordados de um almoxarifado, um pedido por segundo) diz o texto
   dele no alto enquanto a ponte trabalha: o pedido pode levar minutos, e o botão parado sem palavra parecia travado. */
(function () {
  function aviso() {
    var caixa = document.querySelector("[data-ponte-aviso]");
    if (!caixa) return null;
    while (caixa.firstChild) caixa.removeChild(caixa.firstChild);
    return caixa;
  }
  function mostrar(texto, login, rotulo) {
    var caixa = aviso();
    if (!caixa) return;
    var div = document.createElement("div");
    div.className = "cn-erro";
    div.setAttribute("role", "alert");
    var b = document.createElement("b");
    b.textContent = texto;
    div.appendChild(b);
    if (typeof login === "string" && login) {      // o `login` do portão é um true, não um endereço (ver abaixo)
      div.appendChild(document.createTextNode(" "));
      var a = document.createElement("a");
      a.href = login;
      a.textContent = rotulo || "Entrar pelo Fracttal";
      div.appendChild(a);
    }
    caixa.appendChild(div);
    if (caixa.scrollIntoView) caixa.scrollIntoView({block: "nearest"});
  }
  function esperar(texto) {
    var caixa = aviso();
    if (!caixa) return;
    var div = document.createElement("div");
    div.className = "cn-erro cn-aviso";
    div.setAttribute("role", "status");
    div.textContent = texto;
    caixa.appendChild(div);
  }
  document.addEventListener("submit", function (ev) {
    var f = ev.target;
    if (!f || !f.hasAttribute || !f.hasAttribute("data-ponte")) return;
    ev.preventDefault();
    var botao = f.querySelector('button[type="submit"]');
    if (botao) botao.disabled = true;
    if (f.hasAttribute("data-ponte-espera")) esperar(f.getAttribute("data-ponte-espera"));
    fetch(window.nexusRota(f.getAttribute("action")), {
      method: "POST", body: new FormData(f), credentials: "same-origin", headers: {"Accept": "application/json"}
    }).then(function (r) {
      return r.json().then(function (d) { return {r: r, d: d || {}}; }, function () { return {r: r, d: {}}; });
    }).then(function (x) {
      if (x.r.ok && x.d.ok) { window.location.assign(window.nexusRota(x.d.volta || window.location.pathname)); return; }
      // o 401 do portão do Nexus (a sessão que nasceu do Fracttal e perdeu o cookie dele foi encerrada junto): o `login` é um
      // true e o endereço de entrar de novo é o `entrar`; o 401 da ponte traz o `login` com o /os/login do Fracttal
      if (x.d.sessao_encerrada) mostrar(x.d.erro || "A sessão acabou: entre de novo.", x.d.entrar, "Entrar de novo");
      // o 502 e o 504 do proxy (ou o pedido que caiu no meio) não dizem o que o Nexus fez: pode ter gravado, e a frase de antes
      // garantia que nada tinha sido anotado (a revisão de 11/11/2026)
      else mostrar(x.d.erro || "O Nexus não respondeu como esperado (HTTP " + x.r.status + "): pode ter gravado. Por isso, " +
                   "recarregue a página e confira antes de tentar de novo.", x.d.login);
      if (botao) botao.disabled = false;
    }).catch(function () {
      mostrar("Não consegui falar com o Nexus agora, e o pedido pode ter chegado: recarregue a página e confira antes de " +
              "tentar de novo.");
      if (botao) botao.disabled = false;
    });
  });
})();
