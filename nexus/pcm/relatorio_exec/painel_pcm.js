/* Trechos do painel do PCM (repositório fillipefigueiro-source/gridco-pcm-data, main e6cdab4) que o
   relatorio_exec.js usa, copiados LINHA A LINHA, sem editar, pelo ferramentas/copiar_painel_pcm.py (as faixas
   de linha de cada trecho estão no comentário dele). NÃO EDITE: o teste confere o hash (COPIAS no
   __init__.py). Para atualizar, veja o CLAUDE.md desta pasta. */

// ── js/app.js, linhas 206-206: o cliente igual sem caixa (usado pelo gpScopedTarefas) ──
const _cliEq=(a,b)=>(a||'').toLowerCase()===(b||'').toLowerCase();

// ── js/app.js, linhas 2965-2971: as tarefas do escopo do login (no Nexus, sempre a visão de administrador) ──
function gpScopedTarefas(){
  const all=(GESTAO_DB&&GESTAO_DB.tarefas)||[];
  // esconde tarefas sem Classificação 1 (ativos "TESTE"/não classificados)
  let arr=all.filter(t=>t.usina && t.usina!=='(sem usina)' && t.cliente && t.cliente!=='(sem cliente)' && (t.cliente||'').toLowerCase()!=='usina teste');
  if(S.isAdmin||!S.user)return arr;
  return arr.filter(t=>_cliEq(t.cliente,S.user));
}

// ── js/app.js, linhas 582-582: a Gerencial aberta (MP); o pacote cifrado não vem ao navegador no Nexus ──
let MP_PACK=null, MP=null;                       // pacote cifrado / dados abertos

// ── js/app.js, linhas 638-650: a situação de cada MPA/MPS (mesma regra do site MPAS) ──
const mpBd=r=>{const o=String(r.os||'').trim();return (o&&MP&&MP.bd&&MP.bd[o])?MP.bd[o]:null;};
function mpSit(r){
  const b=mpBd(r), hoje=new Date().toISOString().slice(0,10);
  let k=null;
  if(b&&b.sit) k=b.sit;
  else{
    const st=(r.status||'').toLowerCase();
    k = st.startsWith('finaliz')?'Concluída' : st.startsWith('em execu')?'Em andamento':'Não iniciada';
  }
  if(k!=='Concluída'&&r.prevista&&r.prevista<hoje) k='Atrasada';
  const cls={'Concluída':'green','Em andamento':'blue','Não iniciada':'amber','Atrasada':'red'}[k]||'gray';
  return {k,cls};
}

// ── js/preventivas.js, linhas 41-41: o estado da Gerencial (no Nexus: 'ok' quando o servidor a abriu) ──
let GPV_MP = { estado: 'nao', mapa: null, err: '' };   // nao|carregando|ok|erro|sem-chave

// ── js/preventivas.js, linhas 47-67: o nome da usina normalizado e a última observação datada ──
function gpvMpNorm(s) {
  return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[–—]/g, '-').toLowerCase()
    .replace(/\s*-\s*[a-z]{2}\s*$/, '')      // corta o " - UF" do Fracttal
    .replace(/(\d)00\b/g, '$1')              // Gerencial "Marabá 200" ~ Fracttal "Marabá 2"
    .replace(/\butragaz\b/g, 'ultragaz')     // typo histórico do Fracttal (mesmo alias do Python)
    .replace(/[^a-z0-9]+/g, ' ').trim();
}
const GPV_MP_DATA = /(\d{2})\/(\d{2})\/(\d{4})/;
function gpvMpUltObs(txt) {
  const t = String(txt || '').trim();
  if (!t) return '';
  const pedacos = t.split(/\n|(?=•)/).map(x => x.trim()).filter(Boolean);
  let melhor = '', melhorK = '';
  pedacos.forEach(p => {
    const m = GPV_MP_DATA.exec(p);
    const k = m ? m[3] + m[2] + m[1] : '';
    if (!melhor || k >= melhorK) { melhorK = k; melhor = p; }
  });
  return melhor.replace(/^•\s*/, '');
}

// ── js/preventivas.js, linhas 118-126: a criticidade em três baldes ──
function gpvMpCls(c) {
  // sem acento: "Crítico" tem í; "Muito Crítico" começa com M — 'crit' em
  // QUALQUER posição vem antes do balde "Média" (âmbar).
  const s = String(c || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  if (!s) return '';
  if (s.indexOf('crit') >= 0 || s.startsWith('alt')) return 'crit';
  if (s.startsWith('m')) return 'and';
  return 'ok';
}

// ── js/preventivas.js, linhas 149-149: a sigla da preventiva na tarefa ──
const GPV_RX = /\b(MP[MSAT])\b/;

// ── js/preventivas.js, linhas 177-181: dias desde uma data e o hoje ──
function gpvDias(iso) {
  if (!iso) return null;
  return Math.floor((Date.now() - new Date(iso + 'T12:00:00').getTime()) / 86400000);
}
const gpvHoje = () => new Date().toISOString().slice(0, 10);

// ── js/preventivas.js, linhas 334-373: a Fila das MPA/MPS: Gerencial + Fracttal (o 'MPA/MPS atrasadas' do relatório) ──
function gpvFilaLinhas() {
  const hoje = gpvHoje();
  const out = [];
  ((MP && MP.manut) || []).forEach(m => {
    const tipo = String(m.tipo || '').toUpperCase().indexOf('MPS') >= 0 ? 'MPS' : 'MPA';
    // a célula OS da Gerencial pode trazer VÁRIAS OSs ("123/456") — todas
    // contam: a Programada é a mais cedo entre elas e as tarefas se somam
    const partes = String(m.os || '').split(/[\/,;]/).map(x => x.trim()).filter(Boolean);
    const bds = partes.map(p => (MP.bd && MP.bd[p]) || null).filter(Boolean);
    const os = partes.join(' / ');
    let prog = null, bdFin = null, bdTot = null;
    bds.forEach(b => {
      if (b.tasks) b.tasks.forEach(t => { if (t.prog && (!prog || t.prog < prog)) prog = t.prog; });
      bdFin = (bdFin || 0) + (b.fin || 0); bdTot = (bdTot || 0) + (b.total || 0);
    });
    const bd = bds.length ? { fin: bdFin, total: bdTot } : null;
    const sit = mpSit(m);
    const conclu = sit.k === 'Concluída';
    const atraso = (!conclu && m.prevista && m.prevista < hoje) ? gpvDias(m.prevista) : null;
    const obs = gpvMpUltObs(m.obs);
    const od = GPV_MP_DATA.exec(obs);
    const obsIso = od ? od[3] + '-' + od[2] + '-' + od[1] : null;
    const critCls = gpvMpCls(m.criticidade);
    out.push({
      nome: (m.cliente ? m.cliente + ' – ' : '') + (m.usina_curta || m.usina || '—'),
      usinaFull: m.usina || '', cli: m.cliente || '', clu: m.cluster || '',
      tipo, crit: m.criticidade || '', critCls,
      prev: m.prevista || null, prog, atraso,
      os, semOS: !os, osSemPar: !!os && !bd, semData: !!bd && !prog,
      // "crítica sem data futura": criticidade alta/crítica, não concluída e
      // sem programação à frente — o KPI de GESTÃO (mede funil, não sorte)
      critSemData: !conclu && critCls === 'crit' && (!prog || prog < hoje),
      sit, conclu, obs, obsIso, obsVelha: obsIso ? (gpvDias(obsIso) > 60) : false,
      equipe: m.equipe || '', apoio: m.apoio || '', statusPlan: m.status || '',
      bdFin: bd ? bd.fin : null, bdTot: bd ? bd.total : null,
      diverge: !!(m.prevista && prog && Math.abs(gpvDias(m.prevista) - gpvDias(prog)) > 30),
    });
  });
  return out;
}
