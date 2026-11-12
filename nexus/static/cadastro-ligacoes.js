/* Ligações entre bases: o botão que liga as sugestões de 100% pergunta antes (o formulário traz a pergunta em
   data-confirmar). Sem a pergunta aceita, o pedido não sai. */
document.addEventListener('submit', function (e) {
  var f = e.target;
  var pergunta = f && f.classList && f.classList.contains('lig-lote') && f.getAttribute('data-confirmar');
  if (pergunta && !window.confirm(pergunta)) { e.preventDefault(); }
});
