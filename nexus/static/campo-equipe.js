/* A dica do ponto no Mapa de equipe (10/11/2026).
   Levi: "Quero que ao clicar na pessoa no mapa já apareça o percurso e ao passar o mouse o nome da pessoa e a equipe!".
   O clique é o link do próprio ponto (o servidor monta o endereço do percurso do dia). Aqui, só a dica: o nome, a equipe
   e a situação, lidos dos data-eq-* do link; aparece com o mouse e com o foco do teclado, e não leva coordenada nenhuma. */
(function () {
  "use strict";
  var quadro = document.querySelector(".eq-quadro"), dica = quadro && quadro.querySelector(".eq-dica");
  if (!dica) return;
  function linha(tag, texto) { var e = document.createElement(tag); e.textContent = texto; return e; }
  function mostrar(a, x, y) {
    dica.textContent = "";
    dica.appendChild(linha("b", a.getAttribute("data-eq-nome")));
    dica.appendChild(linha("span", a.getAttribute("data-eq-equipe")));
    dica.appendChild(linha("small", a.getAttribute("data-eq-sit")));
    dica.hidden = false;
    var q = quadro.getBoundingClientRect(), largura = dica.offsetWidth, altura = dica.offsetHeight;
    var esq = x - q.left + 14, topo = y - q.top + 14;
    if (esq + largura > q.width - 6) esq = x - q.left - largura - 10;       // perto da borda direita, a dica vai à esquerda
    if (topo + altura > q.height - 6) topo = y - q.top - altura - 10;
    dica.style.left = Math.max(6, esq) + "px";
    dica.style.top = Math.max(6, topo) + "px";
  }
  function alvo(e) { return e.target.closest && e.target.closest("a[data-eq-nome]"); }
  quadro.addEventListener("pointermove", function (e) {
    var a = alvo(e);
    if (a) mostrar(a, e.clientX, e.clientY); else dica.hidden = true;
  });
  quadro.addEventListener("pointerleave", function () { dica.hidden = true; });
  quadro.addEventListener("focusin", function (e) {
    var a = alvo(e);
    if (!a) return;
    var r = a.getBoundingClientRect();
    mostrar(a, r.right, r.bottom);
  });
  quadro.addEventListener("focusout", function () { dica.hidden = true; });
})();
