/* Mínimo e máximo do almoxarifado (26/10/2026): "usar como recomendado" copia a sugestão da peça para os dois campos do
   recomendado (o PCM ajusta antes de Registrar). Só preenche os campos: quem grava é o botão Registrar, nunca este
   script. Os campos de cada peça apontam para o formulário dela pelo atributo form (data-rg-form). */
(function () {
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest ? ev.target.closest("[data-rg-sugestao]") : null;
    if (!b) return;
    var f = b.getAttribute("data-rg-form");
    ["min", "max"].forEach(function (k) {
      var campo = document.querySelector('input[form="' + f + '"][name="rec_' + k + '"]');
      if (campo) campo.value = b.getAttribute("data-" + k) || "";
    });
  });
})();
/* O lote dos acordados em segundo plano (a revisão de 11/11/2026): enquanto ele anda, a página pergunta o andamento a cada 3 s
   (o lote.json, que só lê o controle dele, sem o Fracttal) e recarrega quando ele termina ou para, para mostrar o resultado e o
   que o Fracttal tem agora. A falha de uma pergunta não para as outras; a sessão que venceu para (a re-revisão de 11/11/2026: o
   401 do portão, ou o pedido levado à tela de entrar, voltava a cada 3 s sem dizer nada), e a caixa diz o que fazer. */
(function () {
  var caixa = document.querySelector('[data-rg-lote="gravando"]');
  if (!caixa) return;
  var n = caixa.querySelector("[data-rg-lote-n]");
  var VENCEU = "A sua sessão do Fracttal venceu.";
  function sessao(texto) {
    caixa.setAttribute("role", "alert");
    caixa.textContent = (texto || VENCEU) + " O lote segue no Nexus: recarregue a página e entre de novo para ver o resultado.";
  }
  var vez = setInterval(function () {
    fetch(window.nexusRota(caixa.getAttribute("data-url")), {credentials: "same-origin"}).then(function (r) {
      if (r.status === 401 || r.redirected) {
        clearInterval(vez);
        return r.json().catch(function () { return null; }).then(function (e) {
          sessao(e && e.erro);
          return null;
        });
      }
      return r.ok ? r.json() : null;
    }).then(function (e) {
      if (!e) return;
      if (e.estado !== "gravando") { clearInterval(vez); window.location.reload(); return; }
      if (n) n.textContent = (e.feitas || 0) + " de " + (e.a_mandar || 0);
    }).catch(function () {});
  }, 3000);
})();
