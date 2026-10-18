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
    }
  };
})(window);
