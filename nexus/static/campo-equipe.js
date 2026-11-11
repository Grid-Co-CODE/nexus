/* A dica do ponto no Mapa de equipe (10/11/2026; a usina e o percurso em 11/11/2026).
   Levi: "Quero que ao clicar na pessoa no mapa já apareça o percurso e ao passar o mouse o nome da pessoa e a equipe!".
   O clique é o link do próprio ponto (o servidor monta o endereço do percurso do dia). Aqui, só a dica: o nome, a equipe
   e a situação do técnico, ou o nome da usina (e, com o clima, o nível e o motivo do alerta dela), lidos dos data-eq-*
   do ponto; aparece com o mouse e com o foco do teclado, e não leva coordenada nenhuma. */
(function () {
  "use strict";
  var dica = document.querySelector(".eq-palco .eq-dica"), palco = dica && dica.parentNode;
  if (!dica || palco.getAttribute("data-eq-dica")) return;
  palco.setAttribute("data-eq-dica", "1");
  function linha(tag, texto) {
    if (!texto) return;                                          // a usina sem o clima não tem a 3ª linha
    var e = document.createElement(tag);
    e.textContent = texto;
    dica.appendChild(e);
  }
  function mostrar(a, x, y) {
    dica.textContent = "";
    linha("b", a.getAttribute("data-eq-nome"));
    linha("span", a.getAttribute("data-eq-equipe"));
    linha("small", a.getAttribute("data-eq-sit"));
    dica.hidden = false;
    var q = palco.getBoundingClientRect(), largura = dica.offsetWidth, altura = dica.offsetHeight;
    var esq = x - q.left + 14, topo = y - q.top + 14;
    if (esq + largura > q.width - 6) esq = x - q.left - largura - 10;       // perto da borda direita, a dica vai à esquerda
    if (topo + altura > q.height - 6) topo = y - q.top - altura - 10;
    dica.style.left = Math.max(6, esq) + "px";
    dica.style.top = Math.max(6, topo) + "px";
  }
  function alvo(e) { return e.target.closest && e.target.closest("[data-eq-nome]"); }
  palco.addEventListener("pointermove", function (e) {
    var a = e.buttons ? null : alvo(e);                          // arrastando o mapa, a dica some
    if (a) mostrar(a, e.clientX, e.clientY); else dica.hidden = true;
  });
  palco.addEventListener("pointerleave", function () { dica.hidden = true; });
  palco.addEventListener("focusin", function (e) {
    var a = alvo(e);
    if (!a) return;
    var r = a.getBoundingClientRect();
    mostrar(a, r.right, r.bottom);
  });
  palco.addEventListener("focusout", function () { dica.hidden = true; });
})();
