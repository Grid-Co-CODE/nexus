/* A resposta das ações da gaveta do acompanhamento (Engenharia > Confiabilidade, 18/10/2026).

   Revisão final do mesmo dia: o fetch punha na gaveta o que viesse. Com a sessão vencida, o portão responde 302 e o
   fetch segue até a página de login, que entrava inteira na gaveta; com a sessão do Fracttal encerrada, o JSON 401
   aparecia cru; e nos dois o texto digitado se perdia. O molde é o card das Contestações: login = recarregar a página
   (o portão leva ao Entrar e volta para cá); HTTP de erro = falha, sem trocar a gaveta (o formulário e o texto ficam).
   Prova: tests/test_engenharia_gaveta_js.py (no node). */
(function (w) {
  w.egGaveta = {
    resposta: function (r) {
      if ((r.redirected && /\/entrar([/?#]|$)/.test(r.url || '')) || r.status === 401) {
        return Promise.resolve({acao: 'login'});
      }
      if (!r.ok) {
        return Promise.resolve({acao: 'falha', msg: 'O Nexus não gravou (HTTP ' + r.status + '). O que você digitou ' +
          'continua aqui: tente de novo.'});
      }
      return r.text().then(function (html) { return {acao: 'mostrar', html: html}; });
    },
    // A gaveta lateral e as ações dela, na Confiabilidade e na Mesa do engenheiro (18/10/2026): os cartões com
    // data-gaveta abrem o <template> do mesmo id; os formulários data-eg-form gravam por fetch e a resposta (a gaveta
    // de novo, com o aviso ou o erro) vira o conteúdo; ao fechar depois de gravar, a página recarrega.
    ligar: function () {
        // a gaveta do ativo: o clique no cartão copia o detalhe dele para a gaveta lateral (sem animação). Desde 18/10/2026
        // ela traz o acompanhamento: os formulários gravam sem sair dela (a resposta é a gaveta de novo) e, ao fechar
        // depois de gravar, a página recarrega (as listas e os números das abas mudaram)
        var gav = document.querySelector('.eg-gaveta'), veu = document.querySelector('.eg-veu');
        if (gav) {
          var corpo = gav.querySelector('.eg-gav-corpo'), ativo = null, mudou = false;
          function mostra() { gav.hidden = false; veu.hidden = false; gav.querySelector('.eg-gav-fechar').focus(); }
          function fecha() {
            if (mudou) { location.reload(); return; }
            gav.hidden = true; veu.hidden = true; if (ativo) { ativo.classList.remove('eg-item--on'); ativo.focus(); } ativo = null;
          }
          function marca(cartao) {
            if (ativo) ativo.classList.remove('eg-item--on');
            ativo = cartao; if (cartao) cartao.classList.add('eg-item--on');
          }
          function abre(id, cartao) {
            var t = document.getElementById(id);
            if (!t) return;
            corpo.replaceChildren(t.content.cloneNode(true));
            marca(cartao);
            mostra();
          }
          document.querySelectorAll('.eg-item').forEach(function (b) {
            b.addEventListener('click', function () { abre(b.dataset.gaveta, b); });
          });
          // o Encaminhar do cartão abre a gaveta já na escolha da pessoa
          document.querySelectorAll('[data-eg-abrir-encaminhar]').forEach(function (b) {
            b.addEventListener('click', function () {
              abre(b.dataset.gaveta, b.closest('.eg-cartao').querySelector('.eg-item'));
              var d = corpo.querySelector('[data-eg-encaminhar]');
              if (d) { d.open = true; var s = d.querySelector('select'); if (s) s.focus(); }
            });
          });
          // os formulários do acompanhamento (os da gaveta e o Pegar do cartão): POST por fetch; a resposta, com o aviso
          // ou o erro, vira o conteúdo da gaveta (aberta, se o clique foi no cartão)
          document.addEventListener('submit', function (ev) {
            var f = ev.target.closest('form[data-eg-form]');
            if (!f) return;
            ev.preventDefault();
            var b = f.querySelector('[type="submit"]'), cartao = f.closest('.eg-cartao');
            if (b) b.disabled = true;
            // a falha não troca a gaveta: o formulário, com o que foi digitado, continua (o molde das Contestações)
            function falha(msg) {
              if (b) b.disabled = false;
              var alvo = f;
              if (cartao) {
                if (gav.hidden) abre(cartao.querySelector('.eg-item').dataset.gaveta, cartao.querySelector('.eg-item'));
                alvo = null;
              }
              var p = (alvo && alvo.querySelector('.eg-acomp-msg--erro')) || document.createElement('p');
              p.className = 'eg-acomp-msg eg-acomp-msg--erro';
              p.setAttribute('role', 'alert');
              p.textContent = msg;
              if (alvo) alvo.appendChild(p); else corpo.prepend(p);
            }
            fetch(f.action, {method: 'POST', body: new FormData(f), credentials: 'same-origin'})
              .then(w.egGaveta.resposta)
              .then(function (x) {
                if (x.acao === 'login') { location.reload(); return; }
                if (x.acao === 'falha') { falha(x.msg); return; }
                corpo.innerHTML = x.html;
                mudou = true;
                if (cartao) marca(cartao.querySelector('.eg-item'));
                if (gav.hidden) mostra();
              })
              .catch(function () { falha('Não consegui falar com o Nexus agora. Nada mudou; tente de novo em instantes.'); });
          });
          // o fim da análise antes de uma falha faz o ativo voltar para Ativos com sinal (a regra do Levi): avisa na hora
          document.addEventListener('input', function (ev) {
            var f = ev.target.closest('form[data-eg-form="salvar"]');
            if (!f || ev.target.name !== 'fim') return;
            var fimDia = ev.target.value, dias = (f.dataset.falhas || '').split(',').filter(Boolean);
            var n = fimDia ? dias.filter(function (d) { return d > fimDia; }).length : 0;
            var aviso = f.querySelector('[data-eg-volta]');
            aviso.hidden = !n;
            aviso.textContent = n ? 'Há ' + n + (n === 1 ? ' falha' : ' falhas') + ' depois desta data de fim: o ativo volta para Ativos com sinal ao encerrar.' : '';
          });
          gav.querySelector('.eg-gav-fechar').addEventListener('click', fecha);
          veu.addEventListener('click', fecha);
          document.addEventListener('keydown', function (ev) { if (ev.key === 'Escape' && !gav.hidden) fecha(); });
        }
    }
  };
})(window);
