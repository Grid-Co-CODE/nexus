/* A caixa da foto da Curadoria do inventário (PCM → Almoxarifado → Curadoria; 30/10/2026, itens 2 e 3 das melhorias do
   Almoxarifado). Cada achado tem a foto da peça e as do fabricante, do modelo e do número de série, em miniatura (a cópia de
   160 px, `?mini=1`); a placa ou a etiqueta só se lê ampliada. O clique (ou Enter/Espaço: a miniatura é um <button>) abre o
   <dialog> da página com a foto INTEIRA, pedida só agora (o <img> da caixa nasce sem src: abrir a tela não baixa as fotos
   grandes de todos os achados). Esc fecha (o próprio <dialog>); as setas ← → e os botões Anterior e Próxima passam entre as
   fotos do MESMO achado (o [data-cu-grupo], o cartão); o foco fica preso na caixa (showModal deixa o resto da página inerte)
   e volta à miniatura que a abriu. O clique no véu, fora da foto e dos botões, também fecha.
   Os endereços vêm prontos do template (com o {{ raiz }}): aqui nenhum caminho é escrito. */
(function () {
  'use strict';
  var caixa = document.getElementById('cu-caixa');
  if (!caixa) return;
  var img = document.getElementById('cu-caixa-img');
  var legenda = document.getElementById('cu-caixa-legenda');
  var conta = document.getElementById('cu-caixa-conta');
  var dentro = caixa.querySelector('.cu-caixa-in');
  var grupo = [], atual = 0, origem = null;

  function mostrar(i) {
    if (!grupo.length) return;
    atual = (i + grupo.length) % grupo.length;          // dá a volta: o botão em foco nunca some debaixo do dedo
    var b = grupo[atual];
    var texto = b.getAttribute('data-cu-legenda') || '';
    legenda.textContent = texto;
    img.alt = texto;
    img.src = b.getAttribute('data-cu-foto');
    conta.textContent = grupo.length > 1 ? (atual + 1) + ' de ' + grupo.length : '';
  }

  img.addEventListener('error', function () {
    if (img.getAttribute('src')) legenda.textContent = 'Não consegui abrir a foto agora. Tente de novo em instantes.';
  });

  document.addEventListener('click', function (ev) {
    var b = ev.target.closest ? ev.target.closest('[data-cu-foto]') : null;
    if (!b) return;
    var cartao = b.closest('[data-cu-grupo]');
    grupo = Array.prototype.slice.call((cartao || document).querySelectorAll('[data-cu-foto]'));
    origem = b;
    if (typeof caixa.showModal !== 'function') {         // navegador sem <dialog>: a foto inteira noutra aba
      window.open(b.getAttribute('data-cu-foto'), '_blank', 'noopener');
      return;
    }
    caixa.classList.toggle('cu-caixa--uma', grupo.length < 2);
    mostrar(grupo.indexOf(b));
    caixa.showModal();
  });

  caixa.querySelector('[data-cu-anterior]').addEventListener('click', function () { mostrar(atual - 1); });
  caixa.querySelector('[data-cu-proxima]').addEventListener('click', function () { mostrar(atual + 1); });
  caixa.querySelector('[data-cu-fechar]').addEventListener('click', function () { caixa.close(); });

  caixa.addEventListener('keydown', function (ev) {
    if (grupo.length < 2) return;
    if (ev.key === 'ArrowLeft') { ev.preventDefault(); mostrar(atual - 1); }
    else if (ev.key === 'ArrowRight') { ev.preventDefault(); mostrar(atual + 1); }
  });

  // o véu: o clique que cai na própria caixa ou no miolo vazio (fora da foto, da legenda e dos botões)
  caixa.addEventListener('click', function (ev) {
    if (ev.target === caixa || ev.target === dentro) caixa.close();
  });

  caixa.addEventListener('close', function () {
    img.removeAttribute('src');                         // a próxima abertura não mostra a foto anterior por um instante
    legenda.textContent = '';
    if (origem && document.contains(origem)) origem.focus();
    origem = null;
  });
})();
