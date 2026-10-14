/* O que o relatorio_exec.js do painel do PCM espera encontrar no navegador, para rodar dentro do Nexus (14/10/2026).
   Carrega ANTES dele. As funções do painel vêm copiadas como estão (js/app.js e js/preventivas.js do repositório do
   PCM); o resto é a costura com o Nexus. Regras e porquês: nexus/pcm/relatorio_exec/CLAUDE.md. */

// ── o login do painel: no Nexus todo mundo é da organização (Levi, 14/10/2026: "O nexus não está disponível para o
// cliente, é só para a organização mesmo!"), então sempre a visão de administrador do painel, com os três tipos ──
var S = { isAdmin: true, user: '' };

// ── js/app.js do PCM (linhas 206 e 2965-2971), sem mudar nada ──
const _cliEq=(a,b)=>(a||'').toLowerCase()===(b||'').toLowerCase();
function gpScopedTarefas(){
  const all=(GESTAO_DB&&GESTAO_DB.tarefas)||[];
  // esconde tarefas sem Classificação 1 (ativos "TESTE"/não classificados)
  let arr=all.filter(t=>t.usina && t.usina!=='(sem usina)' && t.cliente && t.cliente!=='(sem cliente)' && (t.cliente||'').toLowerCase()!=='usina teste');
  if(S.isAdmin||!S.user)return arr;
  return arr.filter(t=>_cliEq(t.cliente,S.user));
}

// ── js/preventivas.js do PCM (linha 149): a sigla da preventiva na tarefa ──
const GPV_RX = /\b(MP[MSAT])\b/;

// ── a Gestão PCM: o mesmo gestao_pcm.json do painel, servido pelo Nexus (cópia de 5 min no servidor) ──
var GESTAO_DB = null;

(function () {
  const estado = document.getElementById('rx-estado');
  const botao = document.getElementById('rx-gerar');
  fetch('gestao_pcm.json', { cache: 'no-store' })
    .then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(d => {
      GESTAO_DB = d;
      const quando = String(d.geradoEm || '').slice(0, 16).replace('T', ' ');
      estado.textContent = (d.tarefas || []).length.toLocaleString('pt-BR') + ' tarefas da Gestão PCM'
        + (quando ? ' · dados de ' + quando : '') + '.';
      botao.disabled = false;
    })
    .catch(e => {
      estado.textContent = 'Não consegui ler a Gestão PCM agora (' + e.message + '). Recarregue a página em instantes.';
      estado.classList.add('rx-erro');
    });
  botao.addEventListener('click', () => rexAbrirModal());
})();
