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
