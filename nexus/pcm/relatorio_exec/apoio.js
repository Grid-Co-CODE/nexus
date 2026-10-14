/* A costura do Nexus para o relatorio_exec.js do painel do PCM (14/10/2026). Carrega DEPOIS do painel_pcm.js (os
   trechos do painel copiados como estão) e ANTES do relatorio_exec.js. Regras e porquês:
   nexus/pcm/relatorio_exec/CLAUDE.md. */

// ── o login do painel: no Nexus todo mundo é da organização (Levi, 14/10/2026: "O nexus não está disponível para o
// cliente, é só para a organização mesmo!"), então sempre a visão de administrador do painel, com os três tipos ──
var S = { isAdmin: true, user: '' };

// ── a Gestão PCM: o mesmo gestao_pcm.json do painel, servido pelo Nexus (cópia de 5 min no servidor) ──
var GESTAO_DB = null;

// ── a partida pela Central de emissão: a escolha (tipo, período, escopo) foi feita na coluna da esquerda e vem no
// endereço; aqui ela vai para os campos que o rexGerar lê (os mesmos ids do modal do painel), escondidos ──
async function rxPartir(q) {
  const tipo = ['interno', 'cliente', 'semana'].indexOf(q.get('tipo')) >= 0 ? q.get('tipo') : 'interno';
  const caixa = document.createElement('div');
  caixa.hidden = true;
  caixa.innerHTML = '<input id="rex-de"><input id="rex-ate"><input id="rex-cli"><input id="rex-clu">'
    + '<select id="rex-usi" multiple></select><input type="checkbox" id="rex-semprev">';
  document.body.appendChild(caixa);
  document.getElementById('rex-de').value = q.get('de') || '';
  document.getElementById('rex-ate').value = q.get('ate') || '';
  document.getElementById('rex-cli').value = q.get('cli') || '';
  document.getElementById('rex-clu').value = q.get('clu') || '';
  const usi = document.getElementById('rex-usi');
  q.getAll('usi').forEach(u => { const o = document.createElement('option'); o.value = u; o.selected = true; usi.appendChild(o); });
  document.getElementById('rex-semprev').checked = q.get('semprev') === '1';
  rexTipo(tipo);
  await rexGerar();
  caixa.remove();
}

(function () {
  const estado = document.getElementById('rx-estado');
  const botao = document.getElementById('rx-gerar');
  const q = new URLSearchParams(location.search);
  const gerar = q.get('gerar') === '1';
  let avisou = false;
  // a Central espera o aviso de que a folha ficou pronta (ou do que deu errado) para medir e liberar o Imprimir
  const avisar = o => {
    avisou = avisou || !!o.erro;
    try { if (window.parent !== window) window.parent.postMessage(Object.assign({ rx: 1 }, o), location.origin); } catch (e) {}
  };
  // na folha da Central, o aviso do painel (alert) vira o recado da coluna da direita, no lugar da janela do navegador
  if (document.body.classList.contains('rx-previa')) window.alert = texto => avisar({ erro: String(texto) });
  const ler = nome => fetch(nome, { cache: 'no-store' }).then(r => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });

  // a Gerencial (Levi, 14/10/2026: "traz a Gerencial cifrada para aparecer o MPA/MPS"): o servidor a abre com a senha
  // do .env, como o painel abre com a do login de administrador; sem ela, o relatório sai como no painel sem a senha
  const gerencial = ler('gerencial.json')
    .then(d => { MP = d; GPV_MP.estado = 'ok'; })
    .catch(() => { GPV_MP.estado = 'sem-chave'; });

  ler('gestao_pcm.json')
    .then(d => {
      GESTAO_DB = d;
      const quando = String(d.geradoEm || '').slice(0, 16).replace('T', ' ');
      estado.textContent = (d.tarefas || []).length.toLocaleString('pt-BR') + ' tarefas da Gestão PCM'
        + (quando ? ' · dados de ' + quando : '') + '.';
      return gerencial;
    }, e => {
      estado.textContent = 'Não consegui ler a Gestão PCM agora (' + e.message + '). Recarregue a página em instantes.';
      estado.classList.add('rx-erro');
      avisar({ erro: estado.textContent });
      throw e;
    })
    .then(async () => {
      botao.disabled = false;
      if (!gerar) return;
      try { await rxPartir(q); }
      catch (e) { avisar({ erro: 'O relatório não foi montado (' + ((e && e.message) || e) + ').' }); return; }
      if (avisou) return;
      if (document.getElementById('rex-view')) avisar({ pronto: true });
      else avisar({ erro: 'O relatório não foi montado. Confira a escolha e gere de novo.' });
    })
    .catch(() => {});
  botao.addEventListener('click', () => rexAbrirModal());
})();
