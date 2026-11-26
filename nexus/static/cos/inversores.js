/* static/cos/inversores.js — o Monitoramento do COS EM TEMPO REAL, como o da Ronda COS (protótipo de 12/11/2026).
   Serve à tela normal (os cartões .cos-mon-u e a lista da atenção) e ao videowall (.cos-tv-u): o que tem data-gid.

   O ritmo é o da Ronda COS (apps/web/src/app/monitoramento/page.tsx e components/curva-scada.tsx):
   - GET /scada/monitoramento?entradas=separadas 3 s DEPOIS de cada resposta, parado com a aba escondida: o kW, o estado
     da usina e de CADA inversor andam sozinhos.
   - A curva gravada é de 5 em 5 min e é relida a cada 5 min; o que anda é a PONTA, montada com as leituras de 3 s (só
     quando o valor muda) e podada quando a gravação alcança — a curva nunca tem duas verdades. A ponta é do DIA: na
     virada, a de ontem some (revisão de 12/11: uma tela aberta de noite ganhava às 6h a cauda da tarde anterior).

   Na grade: o kW de cada cartão, a marca dos inversores (vermelho = desligado ou em falha; âmbar = sem comunicação, que
   pode estar gerando) e a ponta da curva. Ao clicar: a curva da usina e a de cada inversor, na mesma escala, com a cruz
   que acompanha o mouse em todos ao mesmo tempo.

   O DETALHE DE UM INVERSOR (13/11/2026; o dono: "clicar num inversor e ver o gráfico individual desse inversor, junto com
   o gráfico das strings dele, individual ou em grupo, por exemplo por MPPT"): o inversor da janela vira botão e abre, na
   mesma janela, a curva dele (a gravada e a ponta), as entradas de agora (a corrente de cada string sob o MPPT que o
   coletor declarou, com a tensão, a corrente e a potência do MPPT) e as entradas DO DIA. O Esc volta à usina antes de
   fechar a janela.

   O DIA E O HISTÓRICO (13/11/2026; o dono: "como faço pra ver os gráficos de ontem ? precisamos armazenar por pelo menos
   40 dias"): a janela escolhe o dia (Hoje, Ontem ou até 40 dias atrás), para a curva da usina, a de cada inversor e as
   entradas. As entradas vêm do histórico gravado na Ronda COS (a scada_entradas, de 5 em 5 min, 45 dias), um pedido por
   inversor e dia (`/scada/entradas/<logger>/<modbus>?dia=`). Em hoje, a ponta é o registro feito aqui com as leituras de
   3 s que já chegam (um ponto a cada 20 s, só da usina aberta, some ao fechar), como a ponta da curva. Num dia que
   passou, não há ponta, e a releitura de 3 s só mexe no estado e nas entradas de agora.

   Custo da volta de 3 s (revisão de 12/11): o minuto do dia é conta (São Paulo é UTC−3 fixo desde 2019), não `Intl`;
   o cartão do SCADA é achado por mapa; só se escreve o que mudou; cartão escondido (as páginas do videowall) não é
   redesenhado; e o gráfico da janela só é refeito quando a série dele muda.

   Lê a API da Ronda COS com o login, direto do navegador (o desenho final): `window.NexusCos.api` (NEXUS_COS_API_URL).
   O id do inversor no cartão é "<logger>:<modbus>" (scada.parser.ts); a série da curva traz os dois.
   As contas sem tela (as entradas, o registro, as marcas do eixo) ficam em `NexusCosInversores`, para o teste no node. */
(function (raiz) {
  "use strict";
  var CFG = raiz.NexusCos || {};
  var API = CFG.api || "";                               // vazio: sem o ao vivo (a tela fica com o que o servidor manda)
  var DE = 5 * 60, ATE = 19 * 60;
  var VIVO_MS = 3000, CURVA_MS = 5 * 60000, CURVAS_GUARDADAS = 20;      // por usina e dia (13/11/2026: o dia escolhido)
  // as cores das strings (13/11/2026): 24 tons em ordem fixa por índice (`--cos-str-1..24`, no inversores.css)
  var N_CORES = 24;
  var fusoMin = -180, fusoEm = 0;                        // America/Sao_Paulo (UTC−3 hoje), conferido de hora em hora
  function fuso(ms) {
    if (ms - fusoEm > 3600000 || ms < fusoEm) {
      try {
        var p = {}; new Intl.DateTimeFormat("en-US", { timeZone: "America/Sao_Paulo", hourCycle: "h23", year: "numeric", month: "2-digit",
          day: "2-digit", hour: "2-digit", minute: "2-digit" }).formatToParts(new Date(ms)).forEach(function (x) { p[x.type] = +x.value; });
        fusoMin = Math.round((Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute) - Math.floor(ms / 60000) * 60000) / 60000);
      } catch (e) { fusoMin = -180; }
      fusoEm = ms;
    }
    return fusoMin;
  }
  var ESTADO = {
    GERANDO: { rotulo: "Gerando", tom: "ok" },
    STANDBY: { rotulo: "Standby", tom: "neutro" },
    DESLIGADO: { rotulo: "Desligado", tom: "critico", grupo: "fora" },
    FALHA: { rotulo: "Em falha", tom: "critico", grupo: "fora" },
    SEM_COMUNICACAO: { rotulo: "Sem comunicação", tom: "alerta", grupo: "semcom" },
    DESCONHECIDO: { rotulo: "Sem estado", tom: "neutro" }
  };
  var ORDEM = { DESLIGADO: 0, FALHA: 1, SEM_COMUNICACAO: 2, DESCONHECIDO: 3, STANDBY: 4, GERANDO: 5 };
  var NS = "http://www.w3.org/2000/svg";
  var SELETOR = ".cos-mon-u[data-gid], .cos-tv-u[data-gid], .cos-mon-at-i[data-gid]";

  // ── tempo e números (conta, não Intl, no que roda a cada 3 s) ────────────────────────────────────────────────────
  function minutoSP(t) {
    var ms = typeof t === "number" ? t : Date.parse(t);
    var m = (ms / 60000 + fuso(ms)) % 1440;
    return m < 0 ? m + 1440 : m;
  }
  function diaSP(ms) { return Math.floor((ms / 60000 + fuso(ms)) / 1440); }
  function dois(n) { return (n < 10 ? "0" : "") + n; }
  function hhmm(min) { return dois(Math.floor(min / 60)) + ":" + dois(Math.floor(min % 60)); }
  function hhmmss(ms) { var m = minutoSP(ms), s = Math.floor(ms / 1000) % 60; return hhmm(m) + ":" + dois(s); }
  function hhmmssDoMin(min) { var s = Math.round(min * 60); return dois(Math.floor(s / 3600) % 24) + ":" + dois(Math.floor(s / 60) % 60) + ":" + dois(s % 60); }
  var fmtMW = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 }), fmtKW = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
  var fmt1 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  var fmt2 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  var fmtAte1 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
  function kw(v) {
    if (v == null || isNaN(v)) { return "—"; }
    return v >= 1000 ? fmtMW.format(v / 1000) + " MW" : fmtKW.format(v) + " kW";
  }
  // a corrente com duas casas e a tensão com uma: as do painel da Ronda COS, na vírgula do pt-BR
  function amp(v) { return v == null || isNaN(v) ? "—" : fmt2.format(v) + " A"; }
  function volt(v) { return v == null || isNaN(v) ? "—" : fmt1.format(v) + " V"; }
  function valorNa(v, un) { return un === "A" ? amp(v) : un === "V" ? volt(v) : kw(v); }
  function rotuloDoEixo(v, un) { return un === "A" || un === "V" ? fmtAte1.format(v) + " " + un : kw(v); }
  function num(v) { return typeof v === "number" && isFinite(v) ? v : null; }
  function passoBonito(x) {
    var e = Math.pow(10, Math.floor(Math.log10(Math.max(x, 1e-9)))), f = x / e;
    return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * e;
  }
  function tetoBonito(max, partes) { var p = passoBonito(Math.max(max, 1) / partes); return Math.max(1, p * Math.ceil(Math.max(max, 1) / p)); }
  function maximo(pts) { var m = 0; for (var i = 0; i < pts.length; i++) { if (pts[i][1] != null && pts[i][1] > m) { m = pts[i][1]; } } return m; }
  function ultimo(pts) { for (var i = pts.length - 1; i >= 0; i--) { if (pts[i][1] != null) { return pts[i]; } } return null; }
  var convertidas = new WeakMap();                       // a série gravada já convertida, por resposta da curva
  function serie(pontos) {
    if (!pontos) { return []; }
    if (convertidas.has(pontos)) { return convertidas.get(pontos); }
    var s = comBuracos(pontos.map(function (p) { return [minutoSP(p.em), p.pac_kw == null ? null : +p.pac_kw]; })
      .filter(function (p) { return p[0] >= DE && p[0] <= ATE; }).sort(function (a, b) { return a[0] - b[0]; }));
    convertidas.set(pontos, s);
    return s;
  }
  // o ponto mais perto do minuto, até `tol` minutos (7,5: meio balde de 15 min da curva gravada; o registro de 20 s usa menos)
  function valorEm(pts, min, tol) {
    var melhor = null, d = 1e9, lim = tol == null ? 7.5 : tol;
    for (var i = 0; i < pts.length; i++) { var dd = Math.abs(pts[i][0] - min); if (dd < d) { d = dd; melhor = pts[i]; } }
    return melhor && d <= lim ? melhor : null;
  }

  // ── a PONTA ao vivo: as leituras de 3 s depois do último ponto gravado, só do dia de hoje ─────────────────────────
  var pontas = {};
  // ⚠ A HORA DA PONTA É A DA LEITURA (`recebido_em` do cartão), nunca a do pedido (13/11/2026, o dono: "Ipixuna 2c, a
  // ultima leitura foi 15:49, mas no grafico está como 16:04"). Com o coletor calado, a resposta de 3 s repete a leitura
  // velha; carimbada com a hora do pedido, ela esticava a curva até agora. Sem `recebido_em` (ou com ele adiante do
  // relógio daqui), fica a hora do pedido — nunca uma hora futura.
  function horaDaLeitura(c, pedidoMs) {
    var t = c && c.recebido_em ? Date.parse(c.recebido_em) : NaN;
    return isFinite(t) ? Math.min(t, pedidoMs) : pedidoMs;
  }
  function anotarPonta(chave, valor, ms) {
    var l = pontas[chave] || (pontas[chave] = []);
    if (l.length && l[l.length - 1].kw === valor && l[l.length - 1].dia === diaSP(ms)) { return; }
    l.push({ dia: diaSP(ms), min: minutoSP(ms), kw: valor });
    if (l.length > 400) { l.shift(); }
  }
  function comPonta(base, chave) {
    var ult = -1, hoje = diaSP(Date.now()), l = pontas[chave];
    for (var i = base.length - 1; i >= 0; i--) { if (base[i][1] != null) { ult = base[i][0]; break; } }
    if (!l || !l.length) { return base; }
    while (l.length && l[0].dia !== hoje) { l.shift(); }   // podada só a de ontem: o resto é de quem desenha
    var ponta = [];
    for (var k = 0; k < l.length; k++) { var p = l[k]; if (p.min > ult && p.min >= DE && p.min <= ATE && p.kw != null) { ponta.push([p.min, p.kw]); } }
    if (!ponta.length) { return base; }
    // a ponta que começa longe do último ponto gravado (o coletor calou e voltou): buraco, nunca uma reta por cima
    var junta = base.slice();
    if (ult >= 0 && ponta[0][0] - ult > limiarDeBuraco(base)) { junta.push([(ult + ponta[0][0]) / 2, null]); }
    return junta.concat(ponta);
  }
  // ⚠ O BURACO NA CURVA (13/11/2026, o dono: "em alguns casos ela fica sem dados de amostra e só completa com uma linha
  // reta, não acho isso ideal"). Entre dois pontos mais distantes que 1,5 passo da série (5 min na gravada, 15 na do
  // cartão), ninguém mediu: o desenho interrompe a linha (um null no meio), como já fazia o gráfico das strings.
  function limiarDeBuraco(pts) {
    var menor = Infinity, ant = null;
    for (var i = 0; i < pts.length; i++) {
      if (pts[i][1] == null) { ant = null; continue; }
      if (ant != null && pts[i][0] - ant > 0) { menor = Math.min(menor, pts[i][0] - ant); }
      ant = pts[i][0];
    }
    return Math.max(7.5, (isFinite(menor) ? menor : 5) * 1.5);
  }
  function comBuracos(pts) {
    var lim = limiarDeBuraco(pts), out = [], ant = null;
    for (var i = 0; i < pts.length; i++) {
      var p = pts[i];
      if (p[1] != null && ant != null && p[0] - ant > lim) { out.push([(ant + p[0]) / 2, null]); }
      out.push(p);
      ant = p[1] == null ? null : p[0];
    }
    return out;
  }

  // ── AS ENTRADAS DO INVERSOR: a regra da Ronda COS (apps/web/src/lib/entradas-do-inversor.ts), portada ─────────────
  // A tela só afirma o MPPT que o coletor DECLAROU. Os formatos que chegam (medidos pela Ronda COS em 27/09/2026): só
  // strings, sem MPPT (todo Huawei, pelo SmartLogger; o Sungrow 250 kW sem o mapa string→MPPT); só MPPT (o SG125HV dos
  // coletores antigos, um MPPT agregado); nenhum dos dois (os SG125HV do pacote 2026.09.23); MPPT com strings (SG75CX,
  // SG50CX-P2, 320 kW). A string tem só a CORRENTE: a tensão do payload é cópia da do MPPT pai, e aparece uma vez, no MPPT.
  function nomeDaString(s) {                             // o do coletor quando ele veio; "String<índice>" quando não
    var n = s && s.nome != null ? String(s.nome).trim() : "";
    return n || ("String" + s.indice);
  }
  function plural(n, um, varios) { return n + " " + (n === 1 ? um : varios); }
  function vistaDasEntradas(i) {
    var mppts = i.mppts || [], soltas = i.strings_sem_mppt || [];
    var nasMppts = mppts.reduce(function (n, m) { return n + (m.strings || []).length; }, 0);
    var total = nasMppts + soltas.length, temStrings = total > 0;
    var titulo = mppts.length > 0 && temStrings ? "MPPT e strings (" + mppts.length + " MPPT · " + plural(total, "string", "strings") + ")"
      : mppts.length > 0 ? "MPPT (" + mppts.length + ")"
      : temStrings ? "Strings (" + total + ")" : "MPPT e strings";
    // o nome do grupo das soltas tem de valer para cada uma delas: "sem MPPT declarado" só quando nenhuma declara MPPT
    var nenhumaDeclara = soltas.every(function (s) { return s.mppt == null; });
    var grupoSoltas = nenhumaDeclara ? "sem MPPT declarado" : "fora dos MPPT listados";
    var semListaDeMppt = nenhumaDeclara ? "não informa MPPT" : "não lista MPPT";
    var doSunop = i.strings_origem === "sunop";            // o SunOP não é "o coletor": as frases mudam
    var tensaoSunop = i.tensao_strings != null ? fmtAte1.format(i.tensao_strings) + " V" : "sem leitura";
    var semUso = i.entradas_sem_uso || [];
    var rotuloSoltas = soltas.length === 0 ? null
      : doSunop ? "O SunOP não informa MPPT: cada string aparece com a corrente medida. Tensão de string deste inversor: " + tensaoSunop + "."
      : mppts.length === 0 ? "O coletor " + semListaDeMppt + " neste inversor: cada string aparece com a corrente medida, sem tensão de entrada."
      : "Strings " + grupoSoltas + " (" + soltas.length + ")";
    var notaTensao = !temStrings ? null
      : doSunop ? "A corrente é o único valor medido por string. Uma string em 0 A só fica em amarelo quando a mesma entrada conduz na maioria dos outros inversores desta usina — o portal não diz quais entradas têm cabo." +
          (semUso.length > 0 ? " " + (semUso.length === 1 ? "A entrada" : "As entradas") + " " + semUso.join(", ") + " não " + (semUso.length === 1 ? "conduz" : "conduzem") +
            " em nenhum inversor da usina agora e não " + (semUso.length === 1 ? "aparece" : "aparecem") + "." : "")
      : mppts.length === 0 ? (nenhumaDeclara
          ? "A corrente é o único valor medido por string, e este inversor não informa MPPT — por isso não há tensão na lista."
          : "A corrente é o único valor medido por string, e o coletor não lista MPPT neste inversor — por isso não há tensão na lista.")
      : soltas.length === 0 ? "A corrente é o único valor medido por string — a tensão mostrada é a do MPPT a que ela pertence."
      : nasMppts === 0 ? "A corrente é o único valor medido por string — as strings " + grupoSoltas + " aparecem sem tensão."
      : "A corrente é o único valor medido por string — a tensão mostrada é a do MPPT a que ela pertence; as strings " + grupoSoltas + " aparecem sem tensão.";
    var correntes = [1];                                   // o teto das barras é a maior corrente DESTE inversor
    mppts.forEach(function (m) { (m.strings || []).forEach(function (s) { correntes.push(s.corrente || 0); }); });
    soltas.forEach(function (s) { correntes.push(s.corrente || 0); });
    return { titulo: titulo, mppts: mppts, soltas: soltas, rotuloSoltas: rotuloSoltas, grupoSoltas: grupoSoltas,
      notaTensao: notaTensao, temStrings: temStrings, doSunop: doSunop, teto: Math.max.apply(null, correntes),
      vazio: mppts.length === 0 && soltas.length === 0 };
  }
  // As séries do gráfico das entradas, na ordem da tela: cada string, sob o MPPT que o coletor declarou (ou no grupo das
  // soltas); sem string nenhuma, cada MPPT (a corrente dele); sem os dois, nada. NUNCA um MPPT inventado: o grupo das
  // soltas se diz como tal, e o "Por MPPT" só existe quando há MPPT declarado com string (`porMppt`).
  function entradasDoInversor(i) {
    var v = vistaDasEntradas(i), lista = [], grupos = [], vistas = {};
    function chaveUnica(base) { var c = base, k = 2; while (vistas[c]) { c = base + "~" + (k++); } vistas[c] = 1; return c; }
    if (v.temStrings) {
      v.mppts.forEach(function (m) {
        if (!(m.strings || []).length) { return; }
        var g = { chave: "m" + m.indice, nome: m.nome || ("MPPT" + m.indice), mppt: true, itens: [] };
        m.strings.forEach(function (s) {
          var e = { chave: chaveUnica("s" + s.indice), nome: nomeDaString(s), grupo: g.chave, valor: num(s.corrente) };
          g.itens.push(e); lista.push(e);
        });
        grupos.push(g);
      });
      if (v.soltas.length) {
        var gs = { chave: "soltas", nome: "Strings " + v.grupoSoltas, mppt: false, itens: [] };
        v.soltas.forEach(function (s) {
          var e = { chave: chaveUnica("s" + s.indice), nome: nomeDaString(s), grupo: null, valor: num(s.corrente) };
          gs.itens.push(e); lista.push(e);
        });
        grupos.push(gs);
      }
      return { tipo: "strings", lista: lista, grupos: grupos, porMppt: grupos.some(function (g) { return g.mppt; }) };
    }
    if (v.mppts.length) {
      v.mppts.forEach(function (m) { lista.push({ chave: chaveUnica("m" + m.indice), nome: m.nome || ("MPPT" + m.indice), grupo: null, valor: num(m.corrente) }); });
      return { tipo: "mppts", lista: lista, grupos: [], porMppt: false };
    }
    return { tipo: "nada", lista: [], grupos: [], porMppt: false };
  }

  // ── A PONTA DAS ENTRADAS da usina aberta (13/11/2026) ───────────────────────────────────────────────────────────
  // O dono, no ar: "as strings não mostram o gráfico do dia, apenas somente depois de 50 segundos praticamente. Eu preciso
  // do gráfico do dia em tempo real". A 1ª versão anotava um ponto a cada 20 s; agora é a ponta de 3 s, como a da curva:
  // cada leitura da usina aberta anota a corrente de cada entrada (chave "<inversor>|<entrada>"). Valor que repete não
  // empilha ponto: o último anda até a leitura de agora (a linha chega ao "agora" mesmo parada). Só o dia de hoje; no
  // máximo PONTA_MAX pontos por entrada (o histórico gravado cobre o resto do dia).
  var PONTA_MAX = 400, pontasEnt = {}, versaoPontaEnt = 0;
  function limparPontaEnt() { pontasEnt = {}; versaoPontaEnt++; }
  function anotarPontaEnt(chave, valor, ms) {
    var l = pontasEnt[chave] || (pontasEnt[chave] = []), dia = diaSP(ms), min = minutoSP(ms), n = l.length;
    while (l.length && l[0].dia !== dia) { l.shift(); }  // virou o dia: a de ontem sai
    n = l.length;
    if (n && l[n - 1].ms === ms) { return; }              // a mesma leitura de novo (um clique redesenha a janela)
    if (n >= 2 && l[n - 1].kw === valor && l[n - 2].kw === valor) { l[n - 1].min = min; l[n - 1].ms = ms; }
    else { l.push({ dia: dia, min: min, kw: valor, ms: ms }); if (l.length > PONTA_MAX) { l.shift(); } }
    versaoPontaEnt++;
  }
  function pontaEnt(chave) {
    var l = pontasEnt[chave] || [], hoje = diaSP(Date.now()), out = [];
    for (var k = 0; k < l.length; k++) { if (l[k].dia === hoje) { out.push([l[k].min, l[k].kw]); } }
    return out;
  }
  // a cor de uma entrada pelo índice dela ("s7" e "m7" = 7; a 25 volta à cor da 1), e o estilo que a leva ao SVG
  function corDaEntrada(chave) {
    var n = parseInt(String(chave).replace(/^[a-z]+/, ""), 10);
    return n > 0 ? ((n - 1) % N_CORES) + 1 : 1;
  }
  function estiloDaCor(k) { return "--cor:var(--cos-str-" + k + ")"; }
  // as marcas do eixo de um trecho que não é o dia inteiro: o menor passo redondo que dá até 5 marcas
  var PASSOS_DO_EIXO = [1, 2, 5, 10, 15, 30, 60, 120, 180, 240];
  function marcasDoEixo(de, ate) {
    var vao = Math.max(ate - de, 1), passo = PASSOS_DO_EIXO[PASSOS_DO_EIXO.length - 1];
    for (var k = 0; k < PASSOS_DO_EIXO.length; k++) { if (vao / PASSOS_DO_EIXO[k] <= 5) { passo = PASSOS_DO_EIXO[k]; break; } }
    var l = [];
    for (var m = Math.ceil(de / passo) * passo; m <= ate + 1e-9; m += passo) { l.push(m); }
    return l;
  }

  // ── O DIA (13/11/2026): hoje, ontem ou um dia até DIAS_ATRAS para trás (o dono: "como faço pra ver os gráficos de
  // ontem ?"). A curva do dia vem da scada_amostra (90 dias); as entradas, da scada_entradas (45 dias). ─────────────
  var DIAS_ATRAS = 40;
  function diaTexto(ms) { return new Date(Math.floor(ms / 60000 + fuso(ms)) * 60000).toISOString().slice(0, 10); }
  function diaMenos(dia, n) { var p = String(dia).split("-"); return new Date(Date.UTC(+p[0], +p[1] - 1, +p[2] - n)).toISOString().slice(0, 10); }
  function diaCurto(dia) { var p = String(dia || "").split("-"); return p.length === 3 ? p[2] + "/" + p[1] : ""; }

  // O HISTÓRICO DAS ENTRADAS de um dia (o contrato EntradasDoDia da Ronda COS, scada.entradas.ts) nas séries do gráfico.
  // A forma (as strings e o MPPT que cada uma declara) vira um "inversor" e passa pela MESMA regra das entradas de agora
  // (entradasDoInversor): as chaves ("s" + índice; "m" + índice no só MPPT) são as do registro ao vivo, e a ponta de
  // hoje encaixa na série gravada. As correntes chegam em centésimos de A. Dois baldes com mais de 1,5 passo entre si:
  // buraco (um null no meio), nunca uma reta por cima do que ninguém mediu.
  function entradasDoHistorico(r) {
    var strings = (r && r.strings) || [], mppts = (r && r.mppts) || [], pontos = (r && r.pontos) || [];
    var passo = (r && r.passo_min) || 5, porIndice = {};
    var formaMppts = mppts.map(function (m) { var x = { indice: m.indice, nome: "MPPT" + m.indice, strings: [] }; porIndice[m.indice] = x; return x; });
    var soltas = [];
    strings.forEach(function (s) {
      var x = { indice: s.indice, mppt: s.mppt == null ? null : s.mppt, corrente: null, sem_corrente: false };
      if (s.mppt != null && porIndice[s.mppt]) { porIndice[s.mppt].strings.push(x); } else { soltas.push(x); }
    });
    var ent = entradasDoInversor({ mppts: formaMppts, strings_sem_mppt: soltas });
    var colunas = [];
    if (ent.tipo === "strings") { strings.forEach(function (s, k) { colunas.push(["s" + s.indice, "s", k]); }); }
    else if (ent.tipo === "mppts") { mppts.forEach(function (m, k) { colunas.push(["m" + m.indice, "ma", k]); }); }
    var series = {}, ultimo = null;
    colunas.forEach(function (c) { series[c[0]] = []; });
    pontos.forEach(function (p) {
      var min = minutoSP(p.em);
      if (min < DE || min > ATE) { return; }
      var buraco = ultimo != null && min - ultimo > passo * 1.5;
      colunas.forEach(function (c) {
        var l = series[c[0]], v = p[c[1]] ? p[c[1]][c[2]] : null;
        if (buraco) { l.push([(ultimo + min) / 2, null]); }
        l.push([min, v == null ? null : v / 100]);
      });
      ultimo = min;
    });
    return { ent: ent, series: series, pontos: pontos.length, dia: (r && r.dia) || "", primeiroDia: (r && r.primeiro_dia) || null,
      desde: (r && r.gravacao_desde) || null };
  }
  // a série gravada com a ponta ao vivo (as leituras de 3 s) depois do último balde, só no trecho do gráfico
  function comPontaAoVivo(base, ponta) {
    var ult = -1, extra = [];
    for (var i = base.length - 1; i >= 0; i--) { if (base[i][1] != null) { ult = base[i][0]; break; } }
    for (var k = 0; k < ponta.length; k++) { if (ponta[k][0] > ult && ponta[k][0] >= DE && ponta[k][0] <= ATE) { extra.push(ponta[k]); } }
    if (!extra.length) { return base; }
    var junta = base.slice();
    if (ult >= 0 && extra[0][0] - ult > 7.5) { junta.push([(ult + extra[0][0]) / 2, null]); }   // a janela abriu depois: buraco
    return junta.concat(extra);
  }
  // o que a tela diz sobre o histórico do dia: lendo, falhou, ou por que não há ponto ("o histórico das strings começou em
  // DD/MM", e não um gráfico vazio sem explicação); vazio quando há ponto
  function avisoDoHistorico(hist, hoje, dia, falhou, temPonta) {
    var aoVivo = hoje && temPonta ? " Aparece a leitura ao vivo desde a abertura da janela." : "";
    if (!hist) { return falhou ? "Não deu para ler o histórico das strings agora; a janela tenta de novo em 30 s." + aoVivo : "Lendo o histórico das strings do dia…"; }
    if (hist.pontos > 0) { return ""; }
    var d = hist.dia || dia, inicio = hist.primeiroDia || hist.desde;
    if (!inicio) { return "O histórico das strings ainda não começou a ser gravado." + aoVivo; }
    if (d && d < inicio) { return "O histórico das strings começou em " + diaCurto(inicio) + "." + aoVivo; }
    if (!hist.primeiroDia) { return "O coletor deste inversor não mandou string nem MPPT desde " + diaCurto(hist.desde) + ", quando o histórico começou." + aoVivo; }
    return (hoje ? "Ainda não há leitura de string gravada hoje (a gravação é das 05:00 às 19:00, de 5 em 5 min)."
      : "Nenhuma leitura de string gravada neste dia: o inversor não respondeu, ou o coletor não mandou string nem MPPT.") + aoVivo;
  }

  // ── O ZOOM NO HORÁRIO (13/11/2026; o dono: "quero poder dar zoom nos graficos, da usina, dos inversores, das
  // strings..") ─────────────────────────────────────────────────────────────────────────────────────────────────────
  // UM trecho para a janela inteira ({de, ate}, em minutos do dia, dentro de 5h às 19h): a usina, os inversores e as
  // strings aproximam juntos, como a cruz anda junto. `null` é o dia inteiro. O mínimo é ZOOM_MIN: abaixo disso não há
  // ponto a ver (o gravado é de 5 em 5 min; a ponta, de 3 s).
  var ZOOM_MIN = 10;
  function limitarTrecho(de, ate) {
    var a = Math.min(de, ate), b = Math.max(de, ate);
    if (!(b - a >= ZOOM_MIN)) { var meio = (a + b) / 2; a = meio - ZOOM_MIN / 2; b = meio + ZOOM_MIN / 2; }
    if (b - a >= ATE - DE) { return null; }               // o dia inteiro (ou mais) é o sem zoom
    if (a < DE) { b += DE - a; a = DE; }
    if (b > ATE) { a -= b - ATE; b = ATE; }
    return { de: a, ate: b };
  }
  // fator < 1 aproxima, > 1 afasta; o minuto `centro` fica onde está (o ponteiro, a pinça); sem ele, o meio do trecho
  function aproximar(t, fator, centro) {
    var de = t ? t.de : DE, ate = t ? t.ate : ATE;
    if (centro == null || !(centro >= de && centro <= ate)) { centro = (de + ate) / 2; }
    return limitarTrecho(centro - (centro - de) * fator, centro + (ate - centro) * fator);
  }
  // desliza o trecho `delta` minutos, sem sair do dia e sem mudar a largura
  function deslizar(t, delta) {
    if (!t) { return null; }
    var w = t.ate - t.de, de = Math.max(DE, Math.min(ATE - w, t.de + delta));
    return { de: de, ate: de + w };
  }
  // O trecho que contém AGORA (em hoje) acompanha a ponta ao vivo: guarda a folga entre agora e o fim, e anda com ela.
  // `agora` é o minuto de agora em hoje, ou null num dia que passou (lá nada anda).
  function novoTrecho(t, agora) {
    if (!t) { return null; }
    var segue = agora != null && agora >= t.de - 0.5 && agora <= t.ate + 0.5;
    return { de: t.de, ate: t.ate, segue: segue, folga: segue ? Math.max(0, t.ate - agora) : 0 };
  }
  function seguirPonta(t, agora) {
    if (!t || !t.segue || agora == null) { return t; }
    var w = t.ate - t.de, ate = Math.min(ATE, agora + t.folga), de = Math.max(DE, ate - w);
    return { de: de, ate: de + w, segue: true, folga: t.folga };
  }
  // a série no trecho: os pontos dele e o vizinho de cada lado (a linha entra e sai pela borda, sem um vão na ponta)
  function recortar(pts, de, ate) {
    if (de <= DE && ate >= ATE) { return pts; }
    var out = [], antes = null, depois = null;
    for (var i = 0; i < pts.length; i++) {
      var p = pts[i];
      if (p[0] < de) { antes = p; } else if (p[0] > ate) { if (!depois) { depois = p; } } else { out.push(p); }
    }
    if (antes) { out.unshift(antes); }
    if (depois) { out.push(depois); }
    return out;
  }
  // o eixo Y do trecho: o maior valor do que se vê nele (com os vizinhos da borda, que a linha também desenha)
  function maximoNoTrecho(pts, de, ate) { return maximo(recortar(pts, de, ate)); }
  function textoDoTrecho(t) { return hhmm(t ? t.de : DE) + "–" + hhmm(t ? t.ate : ATE); }

  // ── SEPARAR AS LINHAS (13/11/2026; o dono: "tipo o das strings, todas, ficam todas juntas e não consigo separar
  // qual é qual, por isso o zoom") ─────────────────────────────────────────────────────────────────────────────────
  // As strings andam todas em 4 a 5 A e viram um feixe: o zoom só no horário não as separa. Com zoom, o eixo Y vai do
  // menor ao maior do que se vê (não de 0), e a caixa do arraste escolhe também a faixa de valor.
  // a faixa dos valores vistos no trecho (as séries recortadas nele), ou null sem valor nenhum
  function faixaDoTrecho(series, de, ate) {
    var lo = Infinity, hi = -Infinity;
    series.forEach(function (pts) {
      recortar(pts || [], de, ate).forEach(function (p) { if (p[1] != null) { lo = Math.min(lo, p[1]); hi = Math.max(hi, p[1]); } });
    });
    return lo === Infinity ? null : { min: lo, max: hi };
  }
  // o Y JUSTO: a faixa vista com uma folga de 8% (no mínimo 2% do topo, ou 0,05 da unidade), nas marcas redondas do eixo;
  // não desce abaixo de 0 quando nada é negativo. Sem valor: 0 a 1
  function escalaJusta(f, partes) {
    if (!f) { return { min: 0, max: 1 }; }
    var folga = Math.max((f.max - f.min) * 0.08, Math.abs(f.max) * 0.02, 0.05);
    var lo = f.min - folga, hi = f.max + folga, passo = passoBonito((hi - lo) / (partes || 4));
    lo = Math.floor(lo / passo + 1e-9) * passo; hi = Math.ceil(hi / passo - 1e-9) * passo;
    if (f.min >= 0 && lo < 0) { lo = 0; }
    return { min: +lo.toFixed(6), max: +hi.toFixed(6) };
  }
  // a faixa de valor da caixa (de baixo para cima, qualquer ordem), com uma altura mínima para não virar uma linha
  function limitarFaixa(v0, v1) {
    var lo = Math.min(v0, v1), hi = Math.max(v0, v1), minimo = Math.max(0.05, Math.abs(hi) * 0.01);
    if (hi - lo < minimo) { var meio = (lo + hi) / 2; lo = meio - minimo / 2; hi = meio + minimo / 2; }
    return { min: lo, max: hi };
  }
  // A CAIXA DO ARRASTE: um arraste quase só na horizontal (menos de LIMIAR_Y_PX de altura) é zoom só de horário, como
  // antes; quase só na vertical (menos de LIMIAR_X_PX de largura), só de valor; os dois, a caixa. `trecho` undefined =
  // o horário fica como está; `faixa` null = o valor fica como está.
  var LIMIAR_Y_PX = 18, LIMIAR_X_PX = 8;
  function caixaDoArraste(m0, m1, v0, v1, dxPx, dyPx) {
    var r = {};
    if (Math.abs(dxPx) >= LIMIAR_X_PX) { r.trecho = limitarTrecho(m0, m1); }
    r.faixa = Math.abs(dyPx) >= LIMIAR_Y_PX ? limitarFaixa(v0, v1) : null;
    return r;
  }
  // a linha MAIS PRÓXIMA do ponteiro naquele horário: o índice da série cujo valor perto de `min` está mais perto de
  // `valor` (as séries dividem a escala, então a distância em valor é a mesma que na tela), ou -1 sem nenhuma
  function maisPerto(lista, min, valor, tol) {
    var melhor = -1, d = Infinity;
    lista.forEach(function (s, k) {
      var p = valorEm(s.pts || [], min, tol);
      if (!p || p[1] == null) { return; }
      var dd = Math.abs(p[1] - valor);
      if (dd < d) { d = dd; melhor = k; }
    });
    return melhor;
  }
  // "Só esta": com uma string isolada, só ela fica no gráfico (sem nenhuma, todas)
  function visiveis(lista, isolada) {
    if (!isolada) { return lista; }
    var so = lista.filter(function (e) { return e.chave === isolada; });
    return so.length ? so : lista;
  }

  // ── O SUNOP NA JANELA (25/11/2026) ───────────────────────────────────────────────────────────────────────────────
  // O print do dono da aba Athon: a janela de uma usina do SunOP não mostrava gráfico nenhum. A Ronda COS grava a série
  // do SunOP desde 13/11 com o id `SUNOP-<código>` (o inversor é `SUNOP-<código>:<n>`), e desde 25/11 manda os inversores
  // de agora (`/sunop/monitoramento`, lidos do portal uma vez por minuto). O que muda para ele: o ritmo (20 s, não 3 s), as
  // frases (o portal não é "o coletor") e o detalhe (o SunOP não guarda o histórico das strings).
  function ehDoSunop(x) {
    if (!x) { return false; }
    return x.fonte === "SUNOP" || /^sunop-/i.test(String(x.pid || "")) || /^SUNOP-/i.test(String(x.usina_id || x.id || ""));
  }

  // ── AS BARRAS POR INVERSOR (25/11/2026) ─────────────────────────────────────────────────────────────────────────
  // O cliente pediu poder ver as usinas em barras para comparar os inversores: uma barra por inversor, o kW de agora, na
  // ordem da usina, e a linha tracejada da MEDIANA dos que estão gerando — quem fica bem abaixo dela gera menos que os
  // vizinhos. Quando todo inversor com medida tem a potência nominal, a barra é a fração da nominal (inversores de
  // tamanhos diferentes na mesma usina); sem ela, o kW. A cor é a do estado que a Ronda COS manda (desligado ou em falha,
  // sem comunicação); sem medida, a barra fica só no contorno. Nenhum limiar inventado aqui: a régua é a mediana à vista.
  function medianaDe(vals) {
    var v = vals.slice().sort(function (a, b) { return a - b; }), n = v.length;
    if (!n) { return null; }
    return n % 2 ? v[(n - 1) / 2] : (v[n / 2 - 1] + v[n / 2]) / 2;
  }
  // `o.valores` (25/11/2026, as barras da JANELA da usina): no lugar do kW de agora, um valor por inversor (id -> número),
  // hoje a ENERGIA do trecho pela curva gravada (`energiaDaSerie`), e `o.semEstado` tira a cor do estado de agora (num dia
  // que passou ela não vale). Com a nominal de todos, a energia vira kWh por kW de nominal, como o kW vira a fração dela.
  function barrasDaUsina(c, o) {
    o = o || {};
    var invs = (c && c.inversores) || [], energia = !!o.valores;
    var base = function (i) { return energia ? num(o.valores[i.id]) : num(i.pac); };
    var comMedida = invs.filter(function (i) { return base(i) != null; });
    var porNominal = comMedida.length > 0 && comMedida.every(function (i) { return num(i.capacidade) != null && i.capacidade > 0; });
    var vals = invs.map(function (i) { var p = base(i); return p == null ? null : (porNominal ? p / i.capacidade : p); });
    var topo = 0;
    vals.forEach(function (v) { if (v != null && v > topo) { topo = v; } });
    var gerando = [];
    invs.forEach(function (i, k) {
      if (vals[k] != null && (energia || !i.veredito ? vals[k] > 0 : i.veredito === "GERANDO")) { gerando.push(vals[k]); }
    });
    var med = medianaDe(gerando), menor = -1;
    var barras = invs.map(function (i, k) {
      var e = ESTADO[i.veredito], grupo = e && e.grupo, v = vals[k];
      if (v != null && (menor < 0 || v < vals[menor])) { menor = k; }
      return {
        id: i.id, nome: nomeDoInversor(i), serial: serialDoInversor(i), kw: num(i.pac), valor: base(i), rotulo: e && !o.semEstado ? e.rotulo : null,
        fracao: v == null || topo <= 0 ? 0 : Math.max(0, Math.min(1, v / topo)),
        pct: porNominal && v != null && !energia ? Math.round(v * 100) : null,
        porKw: porNominal && v != null && energia ? v : null,
        tom: v == null ? "sem" : o.semEstado ? "ok" : grupo === "fora" ? "fora" : grupo === "semcom" ? "semcom" : "ok"
      };
    });
    return {
      barras: barras, porNominal: porNominal, energia: energia, topo: topo,
      mediana: med == null || topo <= 0 ? null : Math.max(0, Math.min(1, med / topo)), medianaBruta: med,
      medianaKw: med != null && !porNominal && !energia ? med : null, medianaPct: med != null && porNominal && !energia ? Math.round(med * 100) : null,
      menor: menor >= 0 && gerando.length ? barras[menor] : null, gerando: gerando.length
    };
  }
  // a energia em kWh (MWh a partir de mil), e o kWh por kW de nominal com uma casa
  function kwh(v) {
    if (v == null || isNaN(v)) { return "—"; }
    return v >= 1000 ? fmtMW.format(v / 1000) + " MWh" : fmtKW.format(v) + " kWh";
  }
  // o valor de uma barra como a tela o escreve (o kW, a % da nominal, o kWh ou o kWh por kW)
  function valorDaBarra(b, x) {
    if (x.valor == null) { return "sem medida"; }
    if (b.energia) { return b.porNominal ? fmtAte1.format(x.porKw) + " kWh/kW (" + kwh(x.valor) + ")" : kwh(x.valor); }
    return b.porNominal ? x.pct + "% (" + kw(x.kw) + ")" : kw(x.kw);
  }
  // a mediana como a tela a escreve, na mesma régua das barras
  function textoDaMediana(b) {
    if (b.medianaBruta == null) { return ""; }
    if (b.energia) { return b.porNominal ? fmtAte1.format(b.medianaBruta) + " kWh/kW" : kwh(b.medianaBruta); }
    return b.porNominal ? b.medianaPct + "% da nominal" : kw(b.medianaKw);
  }
  // O texto de baixo das barras: a régua e quem ficou mais baixo (só com a usina gerando: de noite, todo mundo é zero)
  function resumoDasBarras(b, gerandoUsina) {
    if (!b.barras.length) { return "sem a leitura dos inversores agora"; }
    if (b.energia) {
      if (!b.gerando) { return b.barras.length + " inversores · nenhuma energia gravada neste trecho"; }
    } else if (!gerandoUsina || !b.gerando) { return b.barras.length + " inversores · nenhum gerando agora"; }
    var m = b.menor;
    var deM = !m ? "" : b.energia ? (b.porNominal ? fmtAte1.format(m.porKw) + " kWh/kW" : kwh(m.valor)) : (b.porNominal ? m.pct + "%" : kw(m.kw));
    return "mediana " + textoDaMediana(b) + (m ? " · menor: " + m.nome + ", " + deM : "");
  }
  // A energia de um inversor num trecho do dia, pela curva GRAVADA (de 5 em 5 min: cada ponto vale 5 min daquele kW).
  // Só a gravada: a ponta ao vivo, de 3 em 3 s, contaria o mesmo trecho várias vezes. `null` = nenhum ponto no trecho.
  function energiaDaSerie(pts, de, ate) {
    var e = null;
    (pts || []).forEach(function (p) {
      if (p[1] != null && p[0] >= de && p[0] < ate) { e = (e || 0) + p[1] * 5 / 60; }
    });
    return e;
  }
  // A escolha da pessoa (curva ou barras), lembrada neste navegador; quem nunca escolheu fica na curva
  var CHAVE_DA_VISTA = "nexus.cos.monitoramento.vista";
  function vistaGuardada(armazem) {
    try { var v = armazem && armazem.getItem(CHAVE_DA_VISTA); return v === "barras" ? "barras" : "curva"; } catch (e) { return "curva"; }
  }
  function guardarVista(armazem, v) {
    try { if (armazem) { armazem.setItem(CHAVE_DA_VISTA, v === "barras" ? "barras" : "curva"); } } catch (e) { /* sem armazenamento: vale até recarregar */ }
  }

  raiz.NexusCosInversores = { comBuracos: comBuracos, limiarDeBuraco: limiarDeBuraco, horaDaLeitura: horaDaLeitura, usinaDoLink: usinaDoLink, nomeDaString: nomeDaString, vistaDasEntradas: vistaDasEntradas, entradasDoInversor: entradasDoInversor,
    anotarPontaEnt: anotarPontaEnt, pontaEnt: pontaEnt, limparPontaEnt: limparPontaEnt, corDaEntrada: corDaEntrada,
    estiloDaCor: estiloDaCor, N_CORES: N_CORES, PONTA_MAX: PONTA_MAX, marcasDoEixo: marcasDoEixo, DIAS_ATRAS: DIAS_ATRAS, diaTexto: diaTexto, diaMenos: diaMenos, diaCurto: diaCurto,
    entradasDoHistorico: entradasDoHistorico, comPontaAoVivo: comPontaAoVivo, avisoDoHistorico: avisoDoHistorico,
    ZOOM_MIN: ZOOM_MIN, DE: DE, ATE: ATE, limitarTrecho: limitarTrecho, aproximar: aproximar, deslizar: deslizar,
    novoTrecho: novoTrecho, seguirPonta: seguirPonta, recortar: recortar, maximoNoTrecho: maximoNoTrecho, textoDoTrecho: textoDoTrecho,
    faixaDoTrecho: faixaDoTrecho, escalaJusta: escalaJusta, limitarFaixa: limitarFaixa, caixaDoArraste: caixaDoArraste,
    LIMIAR_Y_PX: LIMIAR_Y_PX, LIMIAR_X_PX: LIMIAR_X_PX, maisPerto: maisPerto, visiveis: visiveis,
    releSemMedicao: releSemMedicao, releDesequilibrio: releDesequilibrio, releFaseDoCodigo: releFaseDoCodigo, releDisjuntor: releDisjuntor,
    ehDoSunop: ehDoSunop, barrasDaUsina: barrasDaUsina, resumoDasBarras: resumoDasBarras, medianaDe: medianaDe,
    energiaDaSerie: energiaDaSerie, valorDaBarra: valorDaBarra, textoDaMediana: textoDaMediana, kwh: kwh,
    serialDoInversor: serialDoInversor, textoDoSerial: textoDoSerial,
    vistaGuardada: vistaGuardada, guardarVista: guardarVista, CHAVE_DA_VISTA: CHAVE_DA_VISTA };
  if (typeof document === "undefined") { return; }       // no node (o teste), só as contas

  // ── a API: o login (no final, o passe do Nexus em CFG.sessao; no protótipo, o da Ronda COS deste navegador) ───────
  function sessao() {
    if (typeof CFG.sessao === "function") { return CFG.sessao() || {}; }
    try { return (JSON.parse(localStorage.getItem("ronda-cos-auth") || "{}").state) || {}; } catch (e) { return {}; }
  }
  var renovando = null;                                  // um refresh só, por mais 401 que cheguem juntos
  function renovar(s) {
    if (typeof CFG.renovar === "function") { return Promise.resolve(CFG.renovar()); }
    if (!s.refreshToken) { return Promise.reject({ login: true }); }
    if (!renovando) {
      renovando = fetch(API + "/auth/refresh", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: s.refreshToken }) }).then(function (r) {
        if (!r.ok) { throw { login: true }; }
        return r.json();
      }).then(function (d) {
        try { var o = JSON.parse(localStorage.getItem("ronda-cos-auth")); o.state.accessToken = d.access_token; localStorage.setItem("ronda-cos-auth", JSON.stringify(o)); } catch (e) {}
      }).then(function () { renovando = null; }, function (e) { renovando = null; throw e; });
    }
    return renovando;
  }
  function pedir(caminho, deNovo) {
    if (!API) { return Promise.reject({ fora: true }); }
    // CFG.pelaPorta (12/11/2026, o Nexus): quem lê a Ronda COS é o servidor do Nexus, pela chave do Andamento
    // (`/t/cos/monitoramento/ronda-api/...`, a sessão do Nexus na mesma origem); sem login da Ronda COS
    if (CFG.pelaPorta) { return pedirPelaPorta(caminho); }
    var s = sessao();
    // CFG.semLogin (só o protótipo): o outro PC pede sem o próprio login, e o repassador do notebook completa
    if (!s.accessToken && !CFG.semLogin) { return Promise.reject({ login: true }); }
    var cab = s.accessToken ? { Authorization: "Bearer " + s.accessToken } : {};
    var ctl = window.AbortController ? new AbortController() : null, prazo = ctl ? setTimeout(function () { ctl.abort(); }, 15000) : 0;
    return fetch(API + caminho, { headers: cab, signal: ctl ? ctl.signal : undefined }).then(function (r) {
      clearTimeout(prazo);
      if (r.status === 401 && !deNovo && s.accessToken) { return renovar(s).then(function () { return pedir(caminho, true); }); }
      if (r.status === 401) { throw { login: true }; }
      if (!r.ok) { throw { erro: "a Ronda COS respondeu " + r.status }; }
      return r.json();
    }, function (e) { clearTimeout(prazo); throw { erro: e && e.name === "AbortError" ? "a Ronda COS não respondeu em 15 s" : "sem rede" }; });
  }

  function pedirPelaPorta(caminho) {
    var ctl = window.AbortController ? new AbortController() : null, prazo = ctl ? setTimeout(function () { ctl.abort(); }, 15000) : 0;
    return fetch(API + caminho, { credentials: "same-origin", headers: { Accept: "application/json" },
      signal: ctl ? ctl.signal : undefined }).then(function (r) {
      clearTimeout(prazo);
      // a sessão do Nexus que venceu volta como a página de entrar (HTML), e não JSON
      var tipo = r.headers.get("content-type") || "";
      if (r.status === 401 || r.status === 403 || (r.ok && tipo.indexOf("json") < 0)) { throw { login: true }; }
      if (!r.ok) {
        return r.json().catch(function () { return {}; }).then(function (d) { throw { erro: d.error || ("o Nexus respondeu " + r.status) }; });
      }
      return r.json();
    }, function (e) { clearTimeout(prazo); throw { erro: e && e.name === "AbortError" ? "a leitura não respondeu em 15 s" : "sem rede" }; });
  }

  // ── o gráfico (na largura real do bloco: nada esticado) ───────────────────────────────────────────────────────────
  function el(tag, attrs, pai) {
    var n = document.createElementNS(NS, tag);
    for (var k in attrs) { if (Object.prototype.hasOwnProperty.call(attrs, k)) { n.setAttribute(k, attrs[k]); } }
    if (pai) { pai.appendChild(n); }
    return n;
  }
  function caminhos(pts, x, y) {
    var dL = "", dA = "", aberto = false, ultX = 0;
    for (var i = 0; i < pts.length; i++) {
      var p = pts[i];
      if (p[1] == null) { if (aberto) { dA += "L" + ultX.toFixed(1) + " " + y(0).toFixed(1) + "Z"; } aberto = false; continue; }
      var px = x(p[0]).toFixed(1), py = y(p[1]).toFixed(1);
      if (!aberto) { dL += "M" + px + " " + py; dA += "M" + px + " " + y(0).toFixed(1) + "L" + px + " " + py; aberto = true; }
      else { dL += "L" + px + " " + py; dA += "L" + px + " " + py; }
      ultX = +px;
    }
    if (aberto) { dA += "L" + ultX.toFixed(1) + " " + y(0).toFixed(1) + "Z"; }
    return [dL, dA];
  }
  var graficos = [], cruzEm = null;
  // Um gráfico por bloco; refeito só quando as séries, o teto, o trecho ou a largura mudam (a volta de 3 s não mexe no
  // resto). `lista`: [{pts, nome, cor, forte, fraca}]. UMA série é o desenho de sempre (a área, a linha e o ponto do fim):
  // verde sem `cor`, ou na cor da string com ela (o modo Individual). Com várias, cada uma é uma linha na cor dela: `cor` é
  // o número da paleta das strings (1 a 24, `--cos-str-N` no inversores.css, pela ordem do índice da string); `forte` é a
  // destacada (mais grossa, por cima) e `fraca` a esmaecida (13/11/2026: o destaque no lugar do teto de 4 cores).
  // `o`: h, max, un ("kW", "A", "V"), de/ate (o trecho, em minutos do dia; o padrão é 5h às 19h), eixoX, eixoY, rotuloFim,
  // vivo (o halo), grupo (fora/semcom), semAgora, tol e passo (minutos), seg (a hora com segundos), nome, rotulo, aoMarcar, dica.
  function grafico(host, lista, o, largura) {
    var w = Math.max(160, largura || host.clientWidth || 600), h = o.h, un = o.un || "kW";
    // a faixa de valor: a da CAIXA do arraste feita neste gráfico (ou nos irmãos da mesma `escala`), senão a de quem
    // chama (0 a teto sem zoom; o Y justo com zoom). `lo` acima de 0 = o eixo não começa em 0, e a tela diz isso
    var fy = o.escala && faixasY[o.escala], lo = fy ? fy.min : (o.min || 0), max = fy ? fy.max : (o.max || 1);
    if (!(max > lo)) { max = lo + 1; }
    // o trecho é o do zoom da janela (13/11/2026): todo gráfico dela aproxima junto; sem zoom, 5h às 19h
    var tr = trechoAtual(), de = o.de != null ? o.de : tr.de, ate = o.ate != null ? o.ate : tr.ate;
    var unica = lista.length === 1;
    var fins = lista.map(function (s) { return ultimo(s.pts); }), fim = null;
    fins.forEach(function (f) { if (f && (!fim || f[0] > fim[0])) { fim = f; } });
    var assinatura = [w, h, lo, max, de.toFixed(3), ate.toFixed(3), o.grupo || "", o.semAgora ? "-" : Math.floor(minutoSP(Date.now()))].concat(
      lista.map(function (s, k) {
        var f = fins[k];
        return (s.cor == null ? "u" : s.cor) + (s.forte ? "F" : s.fraca ? "f" : "") + ":" + s.pts.length + ":" + (f ? f[0].toFixed(3) + "/" + f[1] : "-");
      })).join("|");
    var velho = host._g;
    if (velho && velho.assinatura === assinatura) { velho.aoMarcar = o.aoMarcar; graficos.push(velho); return velho; }
    var ml = o.eixoY ? 52 : 6, mr = o.rotuloFim ? 72 : 10, mt = 10, mb = o.eixoX ? 22 : 6;
    var iw = w - ml - mr, ih = h - mt - mb, vao = Math.max(ate - de, 1e-6);
    function x(m) { return ml + (m - de) / vao * iw; }
    function y(v) { return mt + ih - Math.max(0, Math.min(1, (v - lo) / (max - lo))) * ih; }
    var foco = velho && document.activeElement === velho.alvo;
    if (foco) { velho.trocando = true; }                 // o blur da troca não apaga a cruz
    var colorida = unica && lista[0].cor != null;          // o gráfico de uma string só, na cor dela (o modo Individual)
    var svg = el("svg", { viewBox: "0 0 " + w + " " + h, width: w, height: h, class: "pg" + (o.grupo ? " pg--" + o.grupo : "") + (colorida ? " pg-colorida" : ""),
      role: "img", "aria-label": o.rotulo || "" });
    // troca SÓ o SVG: a faixa do arraste (o zoom) mora no mesmo bloco e sobrevive ao redesenho de 3 s
    if (velho && velho.svg && velho.svg.parentNode === host) { host.replaceChild(svg, velho.svg); }
    else { host.textContent = ""; host.appendChild(svg); }
    if (colorida) { svg.setAttribute("style", estiloDaCor(lista[0].cor)); }
    var grade = el("g", { class: "pg-grade" }, svg), eixo = el("g", { class: "pg-eixo" }, svg);
    var passo = passoBonito((max - lo) / (o.eixoY ? 4 : 2));
    for (var k = 1; lo + k * passo <= max + 1e-6; k++) {
      var v = lo + k * passo;
      el("line", { x1: ml, x2: ml + iw, y1: Math.round(y(v)) + 0.5, y2: Math.round(y(v)) + 0.5 }, grade);
      if (o.eixoY) { el("text", { x: ml - 8, y: y(v) + 4, "text-anchor": "end" }, eixo).textContent = rotuloDoEixo(v, un); }
    }
    // a base: em 0, a de sempre; acima de 0, tracejada e com o valor dela, e o aviso no canto (o feixe aberto engana
    // menos quando se lê que o eixo foi cortado)
    var yb = Math.round(y(lo)) + 0.5;
    el("line", { class: "pg-base" + (lo > 0 ? " pg-base--corte" : ""), x1: ml, x2: ml + iw, y1: yb, y2: yb }, svg);
    if (o.eixoY) { el("text", { x: ml - 8, y: y(lo) + 4, "text-anchor": "end", class: lo > 0 ? "pg-eixo-corte" : "" }, eixo).textContent = lo > 0 ? rotuloDoEixo(lo, un) : "0"; }
    if (lo > 0) { el("text", { class: "pg-corte", x: ml + 4, y: mt + 9 }, svg).textContent = "o eixo começa em " + rotuloDoEixo(lo, un); }
    if (o.eixoX) {
      if (de === DE && ate === ATE) {
        [6, 9, 12, 15, 18].forEach(function (hh) { el("text", { x: x(hh * 60), y: h - 6, "text-anchor": "middle" }, eixo).textContent = dois(hh) + "h"; });
      } else {
        marcasDoEixo(de, ate).forEach(function (m) { el("text", { x: x(m), y: h - 6, "text-anchor": "middle" }, eixo).textContent = hhmm(m); });
      }
    }
    var agora = minutoSP(Date.now());
    if (!o.semAgora && agora > de && agora < ate) { el("line", { class: "pg-agora", x1: x(agora), x2: x(agora), y1: mt, y2: mt + ih }, svg); }
    // as séries recortadas no trecho e presas à área do gráfico (com zoom, o vizinho da borda não invade o eixo)
    var idCorte = "pg-corte-" + (++nCortes), corte = el("clipPath", { id: idCorte }, el("defs", {}, svg));
    el("rect", { x: ml, y: 0, width: iw, height: h }, corte);
    var dentro = el("g", { "clip-path": "url(#" + idCorte + ")" }, svg);
    var visivel = function (f) { return f && f[0] >= de - 1e-6 && f[0] <= ate + 1e-6; };
    var linhasEl = [];
    if (unica) {
      var d = caminhos(recortar(lista[0].pts, de, ate), x, y);
      if (d[1]) { el("path", { class: "pg-area", d: d[1] }, dentro); }
      if (d[0]) { el("path", { class: "pg-linha", d: d[0] }, dentro); }
      if (visivel(fim)) {
        if (o.vivo) { el("circle", { class: "pg-halo", cx: x(fim[0]), cy: y(fim[1]), r: 8 }, dentro); }
        el("circle", { class: "pg-fim", cx: x(fim[0]), cy: y(fim[1]), r: 4 }, dentro);
        if (o.rotuloFim) { el("text", { class: "pg-fim-rot", x: x(fim[0]) + 10, y: y(fim[1]) + 4 }, svg).textContent = valorNa(fim[1], un); }
      }
    } else {
      // cada série na cor dela (`cor`, o número da paleta das strings); as esmaecidas embaixo, as destacadas por cima; o
      // fim de cada uma com o anel da superfície (a sobreposição se lê) quando são poucas ou destacadas
      var camada = function (s) { return s.forte ? 2 : s.fraca ? 0 : 1; };
      lista.map(function (s, k) { return [s, k]; }).sort(function (a, b) { return camada(a[0]) - camada(b[0]); }).forEach(function (par) {
        var s = par[0], dl = caminhos(recortar(s.pts, de, ate), x, y)[0];
        if (!dl) { return; }
        var a = { class: "pg-s" + (s.forte ? " pg-s--forte" : s.fraca ? " pg-s--fraca" : ""), d: dl };
        if (s.cor != null) { a.style = estiloDaCor(s.cor); }
        linhasEl[par[1]] = el("path", a, dentro);           // guardada pelo índice: a linha mais próxima se destaca sem redesenhar
      });
      lista.forEach(function (s, k) {
        if (!visivel(fins[k]) || s.fraca || !(s.forte || lista.length <= 4)) { return; }
        var a = { class: "pg-sfim", cx: x(fins[k][0]), cy: y(fins[k][1]), r: 3.5 };
        if (s.cor != null) { a.style = estiloDaCor(s.cor); }
        el("circle", a, dentro);
      });
    }
    var cruz = el("line", { class: "pg-cruz", x1: 0, x2: 0, y1: mt, y2: mt + ih, visibility: "hidden" }, svg);
    var pontos = [];
    lista.forEach(function (s) {
      if (!unica && s.fraca) { return; }                   // a esmaecida não ganha ponto na cruz (a dica ainda a lê)
      var a = { class: "pg-cruz-ponto" + (unica ? "" : " pg-cp"), r: unica ? 4 : 3, cx: 0, cy: 0, visibility: "hidden" };
      if (!unica && s.cor != null) { a.style = estiloDaCor(s.cor); }
      pontos.push({ s: s, c: el("circle", a, svg) });
    });
    var alvo = el("rect", { class: "pg-alvo", x: ml, y: 0, width: iw, height: h, tabindex: "0", "aria-label": (o.nome || "") + ": use as setas para ler a curva" }, svg);
    var principal = unica ? lista[0] : (lista.filter(function (s) { return s.forte; })[0] || lista[0]);
    var g = { host: host, lista: lista, pts: principal ? principal.pts : [], x: x, y: y, de: de, ate: ate, un: un,
      tol: o.tol == null ? 7.5 : o.tol, seg: !!o.seg, cruz: cruz, pontos: pontos, nome: o.nome,
      // a seta anda 5 min no dia inteiro e menos com zoom (um sexagésimo do trecho, no mínimo 15 s)
      passo: o.passo || Math.min(5, Math.max(0.25, (ate - de) / 60)),
      aoMarcar: o.aoMarcar, dica: o.dica || null, contar: o.contar || ["série", "séries"], fim: fim, alvo: alvo, assinatura: assinatura,
      svg: svg, w: w, ml: ml, iw: iw, h: h, mt: mt, ih: ih, min: lo, max: max, escala: o.escala || "", linhasEl: linhasEl, perto: -1 };
    host._g = g;
    ligarZoom(host);
    graficos.push(g);
    function minutoDoEvento(ev) { var r = svg.getBoundingClientRect(); return de + ((ev.clientX - r.left) * (w / r.width) - ml) / iw * vao; }
    alvo.addEventListener("pointermove", function (ev) { marcarTodos(minutoDoEvento(ev), g, ev.clientX, ev.clientY); });
    // no toque, tocar escolhe a hora e a linha mais próxima, e a escolha fica até o próximo toque
    alvo.addEventListener("pointerdown", function (ev) { if (ev.pointerType === "touch") { marcarTodos(minutoDoEvento(ev), g, ev.clientX, ev.clientY); } });
    alvo.addEventListener("pointerleave", function (ev) { if (ev.pointerType !== "touch") { limparTodos(); } });
    alvo.addEventListener("blur", function () { if (!g.trocando) { limparTodos(); } });
    alvo.addEventListener("keydown", function (ev) {
      if (ev.key !== "ArrowLeft" && ev.key !== "ArrowRight") { return; }
      ev.preventDefault();
      var base = cruzEm != null ? cruzEm : (g.fim ? g.fim[0] : minutoSP(Date.now()));
      var m = Math.max(de, Math.min(ate, base + (ev.key === "ArrowLeft" ? -g.passo : g.passo)));
      var r = svg.getBoundingClientRect();
      marcarTodos(m, g, r.left + x(m) * (r.width / w), r.top + 20);
    });
    if (foco) { alvo.focus({ preventScroll: true }); }    // o foco do teclado fica no gráfico novo
    return g;
  }
  // OS GESTOS DO ZOOM (13/11/2026), presos ao BLOCO do gráfico, e não ao SVG: o SVG é refeito a cada mudança de trecho,
  // e o arraste com o ponteiro capturado se perderia no meio. Leem a geometria do desenho de agora (`host._g`), nunca o
  // `det` (a lição do PR #25).
  // - arrastar seleciona um trecho, e soltar aplica; Shift + arrastar (com zoom) desliza;
  // - Ctrl (ou Cmd) + roda aproxima e afasta em torno do ponteiro. A roda SOZINHA continua rolando a janela, que é longa e
  //   cheia de gráficos (no modo Individual, quase todo ponto da tela é um gráfico): tomar a roda prenderia a rolagem.
  //   A pinça do trackpad chega como roda com Ctrl, e também funciona;
  // - no toque, a pinça aproxima e um dedo na horizontal desliza (com zoom); na vertical, a página rola (`touch-action`);
  // - duplo clique volta ao dia inteiro.
  var nCortes = 0;
  function ligarZoom(host) {
    if (host._zoomLigado) { return; }
    host._zoomLigado = true;
    var toques = {}, gesto = null, faixa = null;
    function minutoEm(clientX) {
      var g = host._g;
      if (!g || !g.svg.isConnected) { return null; }
      var r = g.svg.getBoundingClientRect();
      return g.de + ((clientX - r.left) * (g.w / r.width) - g.ml) / g.iw * (g.ate - g.de);
    }
    function pxPorMinuto() { var g = host._g, r = g.svg.getBoundingClientRect(); return (g.iw * (r.width / g.w)) / (g.ate - g.de); }
    // o valor (eixo Y) na altura do ponteiro, pela escala do desenho de agora
    function valorNaAltura(clientY) {
      var g = host._g;
      if (!g || !g.svg.isConnected) { return null; }
      var r = g.svg.getBoundingClientRect(), py = (clientY - r.top) * (g.h / r.height);
      return g.min + (g.mt + g.ih - py) / g.ih * (g.max - g.min);
    }
    // a faixa do arraste: só o horário (a altura toda) quando a altura é pequena, a CAIXA (horário e valor) quando não
    function mostrarFaixa(gst, cx, cy) {
      var g = host._g, m1 = minutoEm(cx);
      if (!g || m1 == null) { return; }
      if (!faixa) { faixa = document.createElement("div"); faixa.className = "cos-inv-faixa"; faixa.setAttribute("aria-hidden", "true"); host.appendChild(faixa); }
      var r = g.svg.getBoundingClientRect(), h = host.getBoundingClientRect(), k = r.width / g.w, ky = r.height / g.h;
      var soValor = Math.abs(cx - gst.x0) < LIMIAR_X_PX, comValor = Math.abs(cy - gst.y0) >= LIMIAR_Y_PX;
      var a = soValor ? g.de : Math.max(g.de, Math.min(gst.m0, m1)), b = soValor ? g.ate : Math.min(g.ate, Math.max(gst.m0, m1));
      faixa.style.left = (r.left - h.left + g.x(a) * k).toFixed(1) + "px";
      faixa.style.width = Math.max(1, (g.x(b) - g.x(a)) * k).toFixed(1) + "px";
      var topo = r.top - h.top + g.mt * ky, alto = g.ih * ky;
      if (comValor) {
        var y0 = Math.max(r.top + g.mt * ky, Math.min(gst.y0, cy)), y1 = Math.min(r.top + (g.mt + g.ih) * ky, Math.max(gst.y0, cy));
        topo = y0 - h.top; alto = Math.max(1, y1 - y0);
      }
      faixa.style.top = topo.toFixed(1) + "px";
      faixa.style.height = alto.toFixed(1) + "px";
      faixa.classList.toggle("cos-inv-faixa--caixa", comValor);
    }
    function esconderFaixa() { if (faixa) { faixa.remove(); faixa = null; } }
    host.addEventListener("pointerdown", function (ev) {
      if (!host._g) { return; }
      if (ev.pointerType === "touch") {
        toques[ev.pointerId] = ev.clientX;
        var xs = Object.keys(toques).map(function (k) { return toques[k]; });
        if (xs.length === 2) {
          gesto = { pinca: true, d0: Math.max(10, Math.abs(xs[0] - xs[1])), centro: minutoEm((xs[0] + xs[1]) / 2), tr0: zoom, moveu: false };
        } else if (xs.length === 1 && zoom) {
          gesto = { pan: true, x0: ev.clientX, tr0: zoom, moveu: false };
        }
        return;
      }
      if (ev.button !== 0) { return; }
      var m = minutoEm(ev.clientX);
      if (m == null) { return; }
      gesto = ev.shiftKey && zoom ? { pan: true, x0: ev.clientX, tr0: zoom, moveu: false }
        : { m0: m, x0: ev.clientX, y0: ev.clientY, v0: valorNaAltura(ev.clientY), moveu: false };
      try { host.setPointerCapture(ev.pointerId); } catch (e) {}
    });
    host.addEventListener("pointermove", function (ev) {
      if (ev.pointerType === "touch" && toques[ev.pointerId] != null) { toques[ev.pointerId] = ev.clientX; }
      if (!gesto) { return; }
      if (gesto.pinca) {
        var xs = Object.keys(toques).map(function (k) { return toques[k]; });
        if (xs.length < 2) { return; }
        gesto.moveu = true;
        definirZoom(aproximar(gesto.tr0, gesto.d0 / Math.max(10, Math.abs(xs[0] - xs[1])), gesto.centro));
        return;
      }
      var dx = ev.clientX - gesto.x0, dy = gesto.y0 == null ? 0 : ev.clientY - gesto.y0;
      if (Math.abs(dx) > 4 || Math.abs(dy) > 4) { gesto.moveu = true; }
      if (!gesto.moveu) { return; }
      if (gesto.pan) { definirZoom(deslizar(gesto.tr0, -dx / pxPorMinuto())); }
      else { mostrarFaixa(gesto, ev.clientX, ev.clientY); }
    });
    function terminar(ev) {
      if (ev.pointerType === "touch") { delete toques[ev.pointerId]; }
      if (!gesto) { return; }
      var gst = gesto;
      if (gst.pinca && Object.keys(toques).length) { gesto = null; return; }   // um dedo saiu da pinça: ela acaba aqui
      gesto = null;
      esconderFaixa();
      if (gst.moveu) { host._arrastou = Date.now(); }
      if (ev.type === "pointerup" && gst.moveu && gst.m0 != null) {
        // a CAIXA: o horário vale para a janela inteira; a faixa de valor, só para este gráfico (e os irmãos da escala)
        var m1 = minutoEm(ev.clientX), v1 = valorNaAltura(ev.clientY), g = host._g;
        if (m1 == null) { return; }
        var cx = caixaDoArraste(gst.m0, m1, gst.v0, v1, ev.clientX - gst.x0, ev.clientY - gst.y0);
        if (cx.faixa && g && g.escala && gst.v0 != null && v1 != null) { faixasY[g.escala] = cx.faixa; }
        definirZoom(cx.trecho !== undefined ? cx.trecho : zoom);
      }
    }
    host.addEventListener("pointerup", terminar);
    host.addEventListener("pointercancel", terminar);
    // o clique que fecha um arraste não abre o inversor do cartão (o cartão inteiro é botão)
    host.addEventListener("click", function (ev) {
      if (host._arrastou && Date.now() - host._arrastou < 500) { ev.stopPropagation(); ev.preventDefault(); host._arrastou = 0; }
    }, true);
    host.addEventListener("dblclick", function (ev) { ev.preventDefault(); zerarZoom(); });
    host.addEventListener("wheel", function (ev) {
      if (!(ev.ctrlKey || ev.metaKey) || !host._g) { return; }
      ev.preventDefault();
      definirZoom(aproximar(zoom, Math.min(2, Math.max(0.5, Math.exp(ev.deltaY / 300))), minutoEm(ev.clientX)));
    }, { passive: false });
  }
  var dica = document.getElementById("cos-inv-dica"), dicaQuadro = 0;
  function esconderCruz(g) { g.cruz.setAttribute("visibility", "hidden"); g.pontos.forEach(function (q) { q.c.setAttribute("visibility", "hidden"); }); }
  // A LINHA EM REALCE (13/11/2026, o dono: "não consigo separar qual é qual"): a mais próxima do ponteiro, ou a do chip
  // sob o mouse, fica grossa e as outras esmaecem, sem redesenhar; com o minuto, ela ganha o nome ao lado do ponteiro
  function realcar(g, k, min) {
    var tem = k != null && k >= 0 && !!g.linhasEl[k];
    g.svg.classList.toggle("pg-com-perto", tem);
    g.linhasEl.forEach(function (linha, j) { if (linha) { linha.classList.toggle("pg-s--perto", j === k); } });
    var p = tem && min != null ? valorEm(g.lista[k].pts, min, g.tol) : null;
    if (!p || p[1] == null) { if (g.rotPerto) { g.rotPerto.setAttribute("visibility", "hidden"); } return; }
    if (!g.rotPerto) { g.rotPerto = el("text", { class: "pg-perto-rot" }, g.svg); }
    var xs = g.x(p[0]), aDireita = xs < g.ml + g.iw - 90;
    g.rotPerto.setAttribute("x", (aDireita ? xs + 9 : xs - 9).toFixed(1));
    g.rotPerto.setAttribute("y", (g.y(p[1]) - 8).toFixed(1));
    g.rotPerto.setAttribute("text-anchor", aDireita ? "start" : "end");
    g.rotPerto.textContent = g.lista[k].nome || "";
    g.rotPerto.setAttribute("visibility", "visible");
  }
  function marcarTodos(min, origem, cx, cy) {
    var p0 = origem ? valorEm(origem.pts, min, origem.tol) : null;
    var alvoMin = p0 ? p0[0] : min;
    cruzEm = alvoMin;
    // no gráfico de várias linhas em que o ponteiro está, a linha MAIS PRÓXIMA dele na vertical, naquele horário; a
    // escolha fica guardada pelo BLOCO, para o redesenho de 3 s (que refaz o gráfico e repõe a cruz) não a apagar
    if (origem) {
      origem.perto = -1;
      if (origem.lista.length > 1 && cy != null && origem.svg.isConnected) {
        var r0 = origem.svg.getBoundingClientRect(), py = (cy - r0.top) * (origem.h / r0.height);
        origem.perto = maisPerto(origem.lista, alvoMin, origem.min + (origem.mt + origem.ih - py) / origem.ih * (origem.max - origem.min), origem.tol);
      }
      pertoGuardado = { host: origem.host, k: origem.perto };
    }
    graficos.forEach(function (g) {
      if (!g.host.isConnected) { return; }
      // o minuto fora do trecho deste gráfico (a curva do dia e as strings desde a abertura): a cruz some só nele
      if (alvoMin < g.de - 1e-6 || alvoMin > g.ate + 1e-6) { esconderCruz(g); realcar(g, -1); if (g.aoMarcar) { g.aoMarcar(null, null); } return; }
      realcar(g, g === origem ? g.perto : (!origem && pertoGuardado && pertoGuardado.host === g.host ? pertoGuardado.k : -1), alvoMin);
      g.cruz.setAttribute("x1", g.x(alvoMin)); g.cruz.setAttribute("x2", g.x(alvoMin)); g.cruz.setAttribute("visibility", "visible");
      g.pontos.forEach(function (q) {
        var p = valorEm(q.s.pts, alvoMin, g.tol);
        if (p && p[1] != null) { q.c.setAttribute("cx", g.x(p[0])); q.c.setAttribute("cy", g.y(p[1])); q.c.setAttribute("visibility", "visible"); }
        else { q.c.setAttribute("visibility", "hidden"); }
      });
      if (g.aoMarcar) { g.aoMarcar(valorEm(g.pts, alvoMin, g.tol), alvoMin); }
    });
    if (dica && cx != null && origem) {
      var linhas = origem.dica ? origem.dica(origem, alvoMin)
        : [{ v: p0 && p0[1] != null ? valorNa(p0[1], origem.un) : "sem amostra", t: (origem.seg ? hhmmssDoMin(alvoMin) : hhmm(alvoMin)) + (origem.nome ? " · " + origem.nome : "") }];
      dica.textContent = "";
      linhas.forEach(function (l) {
        var r = document.createElement("div"); r.className = "cos-inv-dica-l" + (l.forte ? " forte" : "") + (l.perto ? " perto" : "");
        if (l.cor != null) { var c = document.createElement("i"); c.className = "cos-inv-cor"; c.setAttribute("style", estiloDaCor(l.cor)); c.setAttribute("aria-hidden", "true"); r.appendChild(c); }
        var b = document.createElement("b"); b.textContent = l.v; r.appendChild(b);
        if (l.t) { var s = document.createElement("span"); s.textContent = l.t; r.appendChild(s); }
        dica.appendChild(r);
      });
      dica.hidden = false;
      cancelAnimationFrame(dicaQuadro);
      dicaQuadro = requestAnimationFrame(function () {          // a posição lida e escrita num quadro só
        dica.style.left = Math.min(window.innerWidth - dica.offsetWidth - 8, cx + 14) + "px";
        dica.style.top = Math.max(8, Math.min(window.innerHeight - dica.offsetHeight - 8, cy - 40)) + "px";   // a de 24 linhas cabe na tela
      });
    }
  }
  var pertoGuardado = null;
  function limparTodos() {
    cruzEm = null; pertoGuardado = null;
    graficos.forEach(function (g) { esconderCruz(g); if (g.svg && g.svg.isConnected) { realcar(g, -1); } if (g.aoMarcar) { g.aoMarcar(null, null); } });
    if (dica) { dica.hidden = true; }
  }

  // ── 1. a GRADE em tempo real ────────────────────────────────────────────────────────────────────────────────────
  function mapaDosCartoes(m) { var o = {}; (m && m.cartoes || []).forEach(function (c) { o[c.pid] = c; }); return o; }
  function contar(c) {
    var n = { fora: 0, semcom: 0, total: (c.inversores || []).length };
    (c.inversores || []).forEach(function (i) { var e = ESTADO[i.veredito]; if (e && e.grupo) { n[e.grupo]++; } });
    return n;
  }
  function curvaDoCartao(svg) {                          // a série de 15 min que o servidor desenhou (no próprio SVG)
    if (svg._curva) { return svg._curva; }
    var de = String(svg.getAttribute("data-de") || "").split(":"), passo = +svg.getAttribute("data-passo") || 15;
    var m0 = de.length === 2 ? (+de[0]) * 60 + (+de[1]) : NaN;
    svg._curva = isNaN(m0) ? [] : String(svg.getAttribute("data-kw") || "").split("|").map(function (v, k) { return [m0 + k * passo, v === "" ? null : +v]; })
      .filter(function (p) { return p[0] >= DE && p[0] <= ATE; });
    return svg._curva;
  }
  function escrever(no, prop, valor) { if (no && no[prop] !== valor) { no[prop] = valor; } }
  function redesenharCartao(art, gid) {
    var svg = art.querySelector("svg.cos-curva, svg.cos-tv-cv");
    if (!svg) { return; }
    var base = curvaDoCartao(svg);
    if (!base.length) { return; }
    var vb = svg.viewBox && svg.viewBox.baseVal, W = vb && vb.width || 160, H = vb && vb.height || 36;
    var pts = comPonta(base, "u:" + gid), max = Math.max(maximo(pts), 1);
    var sig = pts.length + "|" + max + "|" + (pts.length ? pts[pts.length - 1][1] : "");
    if (svg._sig === sig) { return; }
    svg._sig = sig;
    var d = caminhos(pts, function (m) { return (m - DE) / (ATE - DE) * W; }, function (v) { return H - Math.max(0, Math.min(1, v / max)) * (H - 2) - 1; });
    var area = svg.querySelector(".cos-curva-area"), linha = svg.querySelector(".cos-curva-linha");
    if (area) { area.setAttribute("d", d[1]); }
    if (linha) { linha.setAttribute("d", d[0]); }
  }
  function aplicarNaGrade(m, agoraMs) {
    var mapa = mapaDosCartoes(m), fora = 0, semcom = 0, vistos = {};
    Object.keys(mapa).forEach(function (pid) { anotarPonta("u:" + pid, mapa[pid].pac_total_kw, horaDaLeitura(mapa[pid], agoraMs)); });
    document.querySelectorAll(SELETOR).forEach(function (art) {
      var gid = art.getAttribute("data-gid"), c = mapa[gid];
      if (!c) { return; }
      var gerando = c.situacao && c.situacao.chave === "GERANDO", n = contar(c);
      if (gerando && !vistos[gid]) { vistos[gid] = 1; fora += n.fora; semcom += n.semcom; }
      if (art.hidden || art.closest("[hidden]")) { return; }   // a página do videowall que não está na tela
      var k = art.querySelector(".kw");
      if (k && c.pac_total_kw != null) { escrever(k, "textContent", kw(c.pac_total_kw)); }
      redesenharCartao(art, gid);
      var alerta = /--(parada|semcom|velha)\b/.test(art.className), st = art.querySelector(".st");
      var marca = !alerta && gerando && n.total ? (n.fora ? "fora" : n.semcom ? "semcom" : "") : "";
      art.classList.toggle("cos-inv--fora", marca === "fora");
      art.classList.toggle("cos-inv--semcom", marca === "semcom");
      if (alerta || !gerando || !n.total) { return; }
      if (!st && k) { st = document.createElement("span"); k.insertAdjacentElement("beforebegin", st); }
      if (!st) { return; }
      var partes = [];
      if (n.fora) { partes.push(n.fora + (n.fora === 1 ? " desligado" : " desligados")); }
      if (n.semcom) { partes.push(n.semcom + " sem comunicação"); }
      escrever(st, "className", marca === "fora" ? "st st--inv" : marca === "semcom" ? "st st--semresp" : "st st--normal");
      escrever(st, "textContent", partes.length ? partes.join(" · ") + " · " + (n.total - n.fora - n.semcom) + "/" + n.total : n.total + "/" + n.total + " inversores");
      escrever(st, "title", ehDoSunop(c) ? "Estado de cada inversor no SunOP (o portal é lido a cada minuto)" : "Estado de cada inversor no SCADA, ao vivo");
    });
    var num = document.getElementById("cos-mon-inv");      // o número da faixa da tela normal
    if (num) {
      num.hidden = false;
      var v = num.querySelector('[data-inv="fora"]'), s2 = num.querySelector('[data-inv="semcom"]');
      if (v) { escrever(v, "textContent", String(fora)); v.classList.toggle("ruim", fora > 0); }
      if (s2) { escrever(s2, "textContent", String(semcom)); }
    }
    desenharTodasAsBarras(mapa);
  }

  // ── AS BARRAS NA GRADE (25/11/2026): o seletor "Curva de hoje | Barras por inversor" e o desenho ──────────────────
  // A escolha mora no <html data-cos-vista> (o CSS esconde a curva ou as barras) e no localStorage, por pessoa. O seletor
  // só existe na tela normal (`[data-cos-vista-sel]`, cos/monitoramento.html): o videowall continua na curva.
  var seletorDaVista = document.querySelector("[data-cos-vista-sel]");
  var vista = seletorDaVista ? vistaGuardada(raiz.localStorage) : "curva";
  function aplicarVista(v) {
    vista = v === "barras" ? "barras" : "curva";
    if (seletorDaVista) {
      document.documentElement.setAttribute("data-cos-vista", vista);
      seletorDaVista.querySelectorAll("[data-vista]").forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-vista") === vista)); });
    }
  }
  function desenharTodasAsBarras(mapa) {
    if (vista !== "barras") { return; }
    document.querySelectorAll(".cos-mon-u[data-gid]").forEach(function (art) {
      if (art.hidden || art.closest("[hidden]")) { return; }
      desenharBarras(art, mapa[art.getAttribute("data-gid")]);
    });
  }
  function desenharBarras(art, c) {
    var bloco = art.querySelector(".cos-barras-bloco");
    if (!bloco) {
      bloco = document.createElement("div"); bloco.className = "cos-barras-bloco";
      var pe = art.querySelector(".cos-mon-u-pe");
      if (pe) { art.insertBefore(bloco, pe); } else { art.appendChild(bloco); }
    }
    var b = barrasDaUsina(c), gerando = !!(c && c.situacao && c.situacao.chave === "GERANDO");
    var sig = JSON.stringify([b.barras, b.mediana, gerando]);
    if (bloco._sig === sig) { return; }
    bloco._sig = sig; bloco.textContent = "";
    var det = document.createElement("span"); det.className = "det cos-barras-det";
    if (!b.barras.length) {
      det.className = "det cos-barras-vazio";
      det.textContent = c ? "sem a leitura dos inversores agora" : (vivo ? "esta usina não veio na leitura dos inversores agora" : "lendo os inversores…");
      bloco.appendChild(det); return;
    }
    var n = b.barras.length, W = n * 10, H = 100;
    var svg = el("svg", { class: "cos-barras", viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none", role: "img",
      "aria-label": "Inversores agora de " + ((art.querySelector(".n") || {}).textContent || "esta usina") + ": " + n + " barras; " + resumoDasBarras(b, gerando) }, null);
    el("line", { class: "cos-curva-base", x1: 0, y1: H, x2: W, y2: H }, svg);
    b.barras.forEach(function (x, k) {
      var h = x.tom === "sem" ? 4 : Math.max(1.5, x.fracao * (H - 2));
      var r = el("rect", { class: "cos-barra cos-barra--" + x.tom, x: k * 10 + 1, y: H - h, width: 8, height: h }, svg);
      var t = el("title", {}, r);
      t.textContent = x.nome + (x.serial ? " (S/N " + x.serial + ")" : "") + " · " + (x.kw == null ? "sem medida" : kw(x.kw)) + (x.pct != null ? " (" + x.pct + "% da nominal)" : "") + (x.rotulo ? " · " + x.rotulo : "");
    });
    if (b.mediana != null && gerando) {
      var y = H - b.mediana * (H - 2);
      el("line", { class: "cos-barras-mediana", x1: 0, y1: y, x2: W, y2: y }, svg);
    }
    bloco.appendChild(svg);
    det.textContent = resumoDasBarras(b, gerando);
    bloco.appendChild(det);
  }
  if (seletorDaVista) {
    aplicarVista(vista);
    seletorDaVista.hidden = false;
    seletorDaVista.addEventListener("click", function (ev) {
      var bt = ev.target.closest && ev.target.closest("[data-vista]");
      if (!bt) { return; }
      aplicarVista(bt.getAttribute("data-vista"));
      guardarVista(raiz.localStorage, vista);
      desenharTodasAsBarras(mapaVivo);
    });
  }

  // ── o laço de 3 s (o mesmo ritmo do Monitoramento da Ronda COS); um só, mesmo com a aba indo e voltando ──────────
  // `vivo` é a frota JUNTA (25/11/2026): os cartões do SCADA (`vivoScada`, de 3 em 3 s) e os do SunOP (`vivoSunop`, de 20
  // em 20 s, só com cartão do SunOP na tela). Quem lê `vivo`/`mapaVivo` acha as duas fontes do mesmo jeito.
  var vivo = null, mapaVivo = {}, vivoEm = 0, laco = null, falhas = 0, voando = false, aberta = null;
  var vivoScada = null, vivoSunop = null, sunopEm = 0, lacoSunop = null, falhasSunop = 0, voandoSunop = false, SUNOP_MS = 20000;
  function juntarVivo() {
    vivo = vivoScada || vivoSunop ? { cartoes: [].concat((vivoScada && vivoScada.cartoes) || [], (vivoSunop && vivoSunop.cartoes) || []) } : null;
    mapaVivo = mapaDosCartoes(vivo);
  }
  function temSunopNaTela() { return !!document.querySelector('[data-gid^="sunop-"]'); }
  function proximoSunop(ms) { clearTimeout(lacoSunop); lacoSunop = setTimeout(lerSunop, ms); }
  function lerSunop() {
    if (voandoSunop) { return; }
    if (document.hidden || !temSunopNaTela()) { proximoSunop(SUNOP_MS); return; }
    voandoSunop = true;
    pedir("/sunop/monitoramento").then(function (m) {
      voandoSunop = false; falhasSunop = 0;
      proximoSunop(SUNOP_MS);
      vivoSunop = m && Array.isArray(m.cartoes) ? m : { cartoes: [] }; sunopEm = Date.now();
      juntarVivo();
      try { aplicarNaGrade(vivo, sunopEm); } catch (e) { console.error("inversores: a grade (SunOP)", e); }
      try { if (aberta && ehDoSunop(mapaVivo[aberta.getAttribute("data-gid")])) { aoVivoNaJanela(); } } catch (e) { console.error("inversores: a janela (SunOP)", e); }
    }, function (e) {
      voandoSunop = false; falhasSunop++;
      // a rota ainda não existe (Nexus antes do Andamento) ou o login venceu: tenta de novo devagar, sem nota própria
      proximoSunop(Math.min(5 * 60000, SUNOP_MS * Math.pow(2, falhasSunop)));
    });
  }
  function rotuloLido() {                                // "SCADA ao vivo · hh:mm:ss": no frescor da tela, ou no canto do videowall
    var r = document.getElementById("cos-inv-vivo");
    if (r) { return r; }
    r = document.createElement("span"); r.id = "cos-inv-vivo";
    var lido = document.getElementById("cos-mon-lido");
    if (lido && lido.parentNode) { r.className = "cos-inv-vivo"; lido.parentNode.appendChild(document.createElement("br")); lido.parentNode.appendChild(r); }
    else { r.className = "cos-inv-vivo cos-inv-vivo--canto"; document.body.appendChild(r); }
    return r;
  }
  function proximo(ms) { clearTimeout(laco); laco = setTimeout(lerVivo, ms); }
  function lerVivo() {
    if (voando) { return; }
    if (document.hidden) { proximo(VIVO_MS); return; }
    voando = true;
    pedir("/scada/monitoramento?entradas=separadas").then(function (m) {
      voando = false; falhas = 0;
      proximo(VIVO_MS);                                 // o próximo já marcado: um erro de desenho não para o laço
      vivoScada = m; vivoEm = Date.now(); juntarVivo();
      try { aplicarNaGrade(vivo, vivoEm); } catch (e) { console.error("inversores: a grade", e); }
      try { if (aberta) { aoVivoNaJanela(); } } catch (e) { console.error("inversores: a janela", e); }
      escrever(rotuloLido(), "textContent", "SCADA ao vivo · " + hhmmss(vivoEm));
      var nota = document.getElementById("cos-inv-nota"); if (nota) { nota.remove(); }
    }, function (e) {
      voando = false; falhas++;
      if (e && (e.login || e.fora)) { notaDeLogin(e); proximo(15000); return; }
      proximo(Math.min(30000, VIVO_MS * Math.pow(2, falhas)));
    });
  }
  function notaDeLogin(e) {
    if (document.getElementById("cos-inv-nota")) { return; }
    var n = document.createElement("div"); n.id = "cos-inv-nota"; n.className = "cos-inv-nota";
    if (e && e.fora) { n.textContent = "O ao vivo dos inversores está desligado: falta o endereço da API da Ronda COS (NEXUS_COS_API_URL)."; }
    else if (CFG.pelaPorta) { n.textContent = "A sessão do Nexus venceu: recarregue a página para entrar de novo e voltar ao tempo real."; }
    else {
      n.appendChild(document.createTextNode(CFG.semLogin
        ? "Para o tempo real, alguém precisa entrar uma vez no Console no notebook do protótipo (ou aqui, no "
        : "Para o tempo real (de 3 em 3 s, como na Ronda COS), entre uma vez no "));
      var a = document.createElement("a"); a.href = CFG.console || "#"; a.target = "_top"; a.textContent = "Console"; n.appendChild(a);
      n.appendChild(document.createTextNode(CFG.semLogin ? ")." : "."));
    }
    document.body.appendChild(n);
  }
  document.addEventListener("visibilitychange", function () { if (!document.hidden) { proximo(0); proximoSunop(0); } });
  var corpoGrade = document.getElementById("cos-tv-corpo") || document.getElementById("cos-mon-corpo");
  if (corpoGrade && window.MutationObserver) {
    // a grade inteira é trocada pelo servidor a cada 30 s: a leitura ao vivo volta por cima na hora
    new MutationObserver(function () {
      try { if (vivo) { aplicarNaGrade(vivo, vivoEm); } else { desenharTodasAsBarras({}); } } catch (e) { console.error(e); }
    })
      .observe(corpoGrade, { childList: true });
  }

  // ── 2. a JANELA da usina, em tempo real ─────────────────────────────────────────────────────────────────────────
  var dlg = document.getElementById("cos-inv-dlg");
  var corpo = dlg && dlg.querySelector(".cos-inv-corpo"), lido = dlg && dlg.querySelector(".cos-inv-lido");
  if (dlg && dica && dica.parentNode !== dlg) { dlg.appendChild(dica); }   // a dica dentro da janela (a camada de cima)
  var curva = null, curvaEm = 0, assinatura = "", partes = null;
  var curvas = {}, ordemCurvas = [], pedidosCurva = {}, falhouEm = {};
  var SEM_CURVA = { usina: [], inversores: [] };
  // o detalhe de um inversor (cos/_inversores.html, .cos-inv-det): sem ele no template, o inversor não vira botão
  var detEl = dlg && dlg.querySelector(".cos-inv-det");
  var detCorpo = detEl && detEl.querySelector(".cos-inv-det-corpo"), detTitulo = detEl && detEl.querySelector(".cos-inv-det-titulo");
  var detSub = detEl && detEl.querySelector(".cos-inv-det-sub");
  var invAberto = null, det = null, modo = "", destaques = {}, pontasDe = null;    // pontasDe: a usina da ponta das entradas
  // as barras da janela (25/11/2026): o que se compara, o kW de agora ou a energia do trecho; vale até recarregar
  var metricaBarras = "agora";
  // o dia escolhido na janela (13/11/2026): "" é hoje (com a ponta ao vivo); um dia que passou não tem ponta, e a
  // releitura de 3 s não mexe nos gráficos dele (o estado de agora e as barras de agora continuam ao vivo)
  var diaEscolhido = "";
  var diasEl = dlg && dlg.querySelector(".cos-inv-dias"), diaData = diasEl && diasEl.querySelector(".cos-inv-dia-data");
  function hojeSP() { return diaTexto(Date.now()); }
  function ehHoje() { return !diaEscolhido || diaEscolhido >= hojeSP(); }
  // O ZOOM DA JANELA (13/11/2026): um trecho só para todo gráfico dela (as contas puras estão acima: limitarTrecho,
  // aproximar, deslizar, seguirPonta). Trocar o dia volta ao dia inteiro; abrir outro inversor mantém o trecho dentro da
  // mesma usina; outra usina e fechar a janela zeram.
  var zoom = null, zoomQuadro = 0;
  var zoomEl = dlg && dlg.querySelector(".cos-inv-zoom"), zoomTexto = zoomEl && zoomEl.querySelector(".cos-inv-zoom-trecho");
  function trechoAtual() { return zoom || { de: DE, ate: ATE }; }
  function minutoDeAgora() { return ehHoje() ? minutoSP(Date.now()) : null; }
  function agoraVisivel() { var a = minutoDeAgora(), tr = trechoAtual(); return a != null && a >= tr.de && a <= tr.ate; }
  function mostrarZoom() {
    if (!zoomEl) { return; }
    escrever(zoomTexto, "textContent", textoDoTrecho(zoom) + (!zoom ? " · o dia inteiro" : zoom.segue ? " · acompanhando agora" : ""));
    zoomEl.classList.toggle("cos-inv-zoom--ativo", !!zoom);
  }
  // aplica o trecho (null = o dia inteiro) e redesenha a janela num quadro só (a roda e o arraste mandam muitos)
  function definirZoom(tr) {
    zoom = novoTrecho(tr, minutoDeAgora());
    mostrarZoom();
    cancelAnimationFrame(zoomQuadro);
    zoomQuadro = requestAnimationFrame(function () { if (aberta && vivo) { limparTodos(); aoVivoNaJanela(); } });
  }
  // a FAIXA DE VALOR de cada escala (a caixa do arraste): vale só para o gráfico onde a caixa foi feita, ou para os
  // irmãos que dividem a escala (os cartões do Individual, a grade dos inversores). "Dia inteiro" e o duplo clique zeram.
  var faixasY = {};
  function zerarZoom() { faixasY = {}; definirZoom(null); }
  // a escala de um gráfico (ou de irmãos): sem zoom, como sempre, de 0 ao teto; com zoom, o Y JUSTO do que se vê
  // (não começa em 0, e o feixe das strings abre). `extras`: os valores de agora, quando agora está à vista
  function escalaDe(series, partes, extras) {
    var tr = trechoAtual(), f = faixaDoTrecho(series, tr.de, tr.ate);
    (extras || []).forEach(function (v) { if (v != null) { f = f ? { min: Math.min(f.min, v), max: Math.max(f.max, v) } : { min: v, max: v }; } });
    if (!zoom) { return { min: 0, max: tetoBonito(f ? Math.max(f.max, 0) : 0, partes) }; }
    return escalaJusta(f, 4);
  }
  function rotuloDaEscala(e, un) { return (e.min > 0 ? rotuloDoEixo(e.min, un) : "0") + " a " + rotuloDoEixo(e.max, un); }
  // AMPLIAR: o gráfico (a curva do inversor, o Todas, um do Por MPPT) ocupa ~70% da altura da tela; o mesmo botão volta
  var ampliado = "";
  function alturaDe(chave, h) { return ampliado && ampliado === chave ? Math.max(h, Math.round(window.innerHeight * 0.7)) : h; }
  function botaoAmpliar(chave, alvo) {                  // `alvo`: o bloco do gráfico, preso aqui (nunca lido do `det`)
    var b = document.createElement("button"); b.type = "button"; b.className = "gc-chip cos-inv-ampliar";
    b.setAttribute("data-amplia-botao", chave);
    b.addEventListener("click", function () {
      ampliado = ampliado === chave ? "" : chave;
      if (aberta && vivo) { aoVivoNaJanela(); }
      var a = typeof alvo === "function" ? alvo() : alvo;
      if (ampliado && a && a.scrollIntoView) { requestAnimationFrame(function () { a.scrollIntoView({ block: "nearest" }); }); }
    });
    return b;
  }
  function mostrarAmpliar(b, chave) {
    var sim = ampliado === chave;
    escrever(b, "textContent", sim ? "Voltar ao tamanho" : "Ampliar");
    b.setAttribute("aria-pressed", String(sim));
    escrever(b, "title", sim ? "Volta o gráfico à altura de antes" : "O gráfico ocupa quase a janela inteira em altura");
  }
  // "SÓ ESTA": uma string isolada por inversor no modo Todas (duplo clique ou Shift+Enter no chip); "Mostrar todas" volta
  var isoladas = {};
  function isolarString(chave) {
    if (isoladas[invAberto] === chave) { delete isoladas[invAberto]; } else { isoladas[invAberto] = chave; }
    if (aberta && vivo) { aoVivoNaJanela(); }
  }
  // o "+" aproxima em torno de agora quando ele está à vista (em hoje, o zoom já nasce acompanhando a ponta)
  function aproximarPeloBotao(fator) { definirZoom(aproximar(zoom, fator, agoraVisivel() ? minutoDeAgora() : null)); }

  function pilula(tom, texto) { var s = document.createElement("span"); s.className = "cn-pill cn-" + tom; s.textContent = texto; return s; }
  function bloco(titulo, detalhe) {
    var d = document.createElement("section"); d.className = "cos-inv-bloco";
    var cab = document.createElement("div"); cab.className = "cos-inv-bloco-cab";
    var h = document.createElement("h3"); h.textContent = titulo; cab.appendChild(h);
    var s = document.createElement("span"); s.className = "d"; s.textContent = detalhe || ""; cab.appendChild(s);
    d.appendChild(cab); d._titulo = h; d._detalhe = s; return d;
  }
  function cosDaUsina(codigo) {
    var l = (CFG.inversoresAbertos || {})[codigo] || [];
    if (!l.length) { return null; }
    var p = document.createElement("p"); p.className = "cos-inv-cos";
    var b = document.createElement("b"); b.textContent = "Aberto no COS (a usina inteira): "; p.appendChild(b);
    p.appendChild(document.createTextNode(l.map(function (x) {
      return String(x[0]) + " — " + String(x[1] || "").toLowerCase() + (x[3] ? " desde " + String(x[3]).slice(8, 10) + "/" + String(x[3]).slice(5, 7) : "") + (x[2] ? " · OS " + x[2] : "");
    }).join("; ")));
    return p;
  }
  function ordenados(c) {
    return (c.inversores || []).slice().sort(function (a, b) { return (ORDEM[a.veredito] || 9) - (ORDEM[b.veredito] || 9) || a.modbus_id - b.modbus_id; });
  }
  function nomeDoInversor(i) { return i.nome || ("Inversor " + i.modbus_id); }
  // O NÚMERO DE SÉRIE (26/11/2026, pedido do dono): o coletor 2026.11.26.1 lê o serial do próprio equipamento, e a Ronda
  // COS o manda em `numero_serie` em cada inversor de `/geracao/scada` (a chave nem vem quando não há). A tela escreve
  // "S/N <serial>" ao lado do nome, apagado e menor, só quando há; sem serial, nada muda.
  function serialDoInversor(i) {
    var s = i && i.numero_serie != null ? String(i.numero_serie).trim() : "";
    return s || null;
  }
  function textoDoSerial(i) { var s = serialDoInversor(i); return s ? "S/N " + s : ""; }
  function motivoDoEstado(i, e) {
    if (e.grupo === "semcom") { return ehDoSunop(i) ? "o portal SunOP acusa falha de comunicação: pode estar gerando" : "não responde ao SCADA: pode estar gerando"; }
    return i.veredito === "FALHA" ? (i.descricao_falha || i.estado) : (e.grupo ? i.estado : "");
  }

  // o relé de proteção na ficha: ver `montarCardRele` (refeita 18/11/2026). Só aparece se a usina tem relé.
  function braw(v) { return v == null || isNaN(v) ? "—" : fmtKW.format(v); }
  // tensao do rele em kV: o coletor ja manda V REAL (escala do perfil do modelo): 13883 -> "13,88".
  function releKv(v) { return v == null || isNaN(v) ? "—" : fmt2.format(v / 1000); }
  // corrente (A) / cosphi — 2 casas; o coletor ja manda o valor real.
  function releNum(v) { return v == null || isNaN(v) ? "—" : fmt2.format(v); }
  // Proteções do URP6000 (códigos ANSI) -> nome amigável, para os cartões de trip e as etiquetas.
  var RELE_FAMILIAS = [
    ["27", "Subtensão"], ["59", "Sobretensão"],
    ["50", "Sobrecorrente instantânea"], ["51", "Sobrecorrente temporizada"],
    ["67", "Direcional"], ["81", "Frequência"],
    ["32", "Potência direcional"], ["37", "Subpotência"],
    ["78", "Salto de vetor"], ["47", "Sequência de fase"], ["86", "Bloqueio"]
  ];
  function releFamilia(code) { var m = String(code).match(/^\d+/); return m ? m[0] : String(code); }
  function releNomeFamilia(fam) { for (var i = 0; i < RELE_FAMILIAS.length; i++) { if (RELE_FAMILIAS[i][0] === fam) { return RELE_FAMILIAS[i][1]; } } return "Proteção " + fam; }
  // o resto do código depois da família: "67B" -> "fase B", "59N" -> "neutro", "81" -> "".
  function releFaseDoCodigo(code) {
    var suf = String(code).slice(releFamilia(code).length).replace(/^-/, "");
    return { A: "fase A", B: "fase B", C: "fase C", N: "neutro", "0": "sequência zero" }[suf] || suf;
  }
  // disjuntor: o servidor manda 1 (fechado) / 0 (aberto) / null (desconhecido) — já interpretado do perfil.
  function releDisjuntor(d) { return d === 1 ? "Fechado" : d === 0 ? "Aberto" : "Sem leitura"; }
  // ⚠ FASE SEM MEDIÇÃO (18/11/2026, Céu Azul 1): corrente EXATAMENTE 0 com outra fase em carga (> 1 A) não é
  // "zero medido" — é o TC ou a entrada do relé que não traz a corrente. Medido no próprio relé: a máxima da
  // fase A nunca passou de 2 A enquanto B e C chegavam a 33 e 24 A. Mostrar 0 ali seria afirmar o que ninguém mediu.
  function releSemMedicao(vals) {
    return vals.map(function (x, i) {
      return x === 0 && vals.some(function (y, j) { return j !== i && y != null && y > 1; });
    });
  }
  // desequilíbrio entre fases: o maior desvio da média, em % da média; null sem as três fases medidas.
  function releDesequilibrio(vals, sem) {
    var m = vals.filter(function (x, i) { return x != null && !isNaN(x) && !(sem && sem[i]); });
    if (m.length !== 3) { return null; }
    var media = (m[0] + m[1] + m[2]) / 3;
    if (!media) { return null; }
    return Math.max(Math.abs(m[0] - media), Math.abs(m[1] - media), Math.abs(m[2] - media)) / media * 100;
  }
  var fmt1 = new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  var RELE_SVG = "http://www.w3.org/2000/svg";
  // o desenho do disjuntor: fechado = a lâmina liga os dois bornes; aberto = a lâmina levantada; sem leitura = tracejada
  function releIconeDj(estado) {
    var s = document.createElementNS(RELE_SVG, "svg");
    var at = { width: "40", height: "40", viewBox: "0 0 40 40", fill: "none", stroke: "currentColor", "stroke-width": "2.5", "stroke-linecap": "round", "aria-hidden": "true" };
    Object.keys(at).forEach(function (k) { s.setAttribute(k, at[k]); });
    function el(tag, a) { var e = document.createElementNS(RELE_SVG, tag); Object.keys(a).forEach(function (k) { e.setAttribute(k, a[k]); }); s.appendChild(e); }
    el("line", { x1: 2, y1: 21, x2: 8, y2: 21 }); el("line", { x1: 32, y1: 21, x2: 38, y2: 21 });
    if (estado === 0) { el("line", { x1: 9, y1: 21, x2: 28, y2: 9 }); }
    else { el("line", estado === 1 ? { x1: 9, y1: 21, x2: 31, y2: 21 } : { x1: 9, y1: 21, x2: 31, y2: 21, "stroke-dasharray": "3 4" }); }
    el("circle", { cx: 8, cy: 21, r: 2.6, fill: "currentColor" }); el("circle", { cx: 32, cy: 21, r: 2.6, fill: "currentColor" });
    return s;
  }
  function releDiv(cls, texto) { var d = document.createElement("div"); d.className = cls; if (texto != null) { d.textContent = texto; } return d; }
  // um cartão de corrente ou de tensão por fase, no estilo dos cartões de inversor: média no canto, barra por fase
  function releCartaoFase(titulo, unidade) {
    var c = { unidade: unidade, linhas: [] };
    c.el = releDiv("cos-rele-cartao cos-rele-fase");
    var cab = releDiv("cos-rele-fase-cab");
    var b = document.createElement("b"); b.textContent = titulo; cab.appendChild(b);
    c.media = document.createElement("span"); c.media.className = "cos-rele-val"; cab.appendChild(c.media);
    c.el.appendChild(cab);
    ["A", "B", "C"].forEach(function (f) {
      var l = releDiv("cos-rele-linha"); l.tabIndex = 0;
      var letra = document.createElement("span"); letra.className = "cos-rele-letra"; letra.textContent = f; letra.setAttribute("aria-hidden", "true"); l.appendChild(letra);
      var tr = releDiv("cos-rele-trilho"); l.appendChild(tr);
      var barra = releDiv("cos-rele-barra"); tr.appendChild(barra);
      var num = releDiv("cos-rele-num"); tr.appendChild(num);
      var sem = releDiv("cos-rele-semmed", "⚠︎ sem medição: verificar TC"); sem.hidden = true; tr.appendChild(sem);
      c.el.appendChild(l); c.linhas.push({ f: f, el: l, barra: barra, num: num, sem: sem });
    });
    c.pe = releDiv("cos-rele-pe"); c.el.appendChild(c.pe);
    return c;
  }
  function releAtualizarFase(c, vals, ehCorrente) {
    var sem = ehCorrente ? releSemMedicao(vals) : [false, false, false];
    var ok = vals.map(function (x, i) { return x != null && !isNaN(x) && !sem[i]; });
    var medidos = vals.filter(function (x, i) { return ok[i]; });
    var teto = Math.max.apply(null, medidos.concat([0])) * 1.22 || 1;   // folga para o número na ponta da barra
    c.linhas.forEach(function (l, i) {
      var x = vals[i], p = ok[i] ? x / teto * 100 : 0;
      l.sem.hidden = !sem[i]; l.barra.hidden = !ok[i]; l.num.hidden = sem[i];
      escrever(l.barra.style, "width", p + "%"); escrever(l.num.style, "left", p + "%");
      escrever(l.num, "textContent", ok[i] ? fmt2.format(x) : "—");
      var txt = sem[i] ? "sem medição, verificar TC" : (ok[i] ? fmt2.format(x) + " " + c.unidade : "sem leitura");
      escrever(l.el, "title", "Fase " + l.f + " · " + txt);
      l.el.setAttribute("aria-label", "Fase " + l.f + ": " + txt);
    });
    c.el.classList.toggle("cos-rele-fase--semmed", sem.some(Boolean));
    var faltam = ["A", "B", "C"].filter(function (_, i) { return sem[i]; });
    var sig = medidos.join(",") + "|" + faltam.join("");
    if (c.media._sig !== sig) {
      c.media._sig = sig; c.media.textContent = "";
      if (medidos.length) {
        c.media.appendChild(document.createTextNode(fmt2.format(medidos.reduce(function (a, b) { return a + b; }, 0) / medidos.length) + " " + c.unidade));
        var sm = document.createElement("small");
        sm.textContent = faltam.length ? "média de " + ["A", "B", "C"].filter(function (_, i) { return ok[i]; }).join(" e ") : "média";
        c.media.appendChild(sm);
      }
    }
    var d = releDesequilibrio(vals, sem);
    escrever(c.pe, "textContent",
      ehCorrente && vals.every(function (x) { return x === 0; }) ? "Sem corrente nas três fases"
      : d !== null ? "Desequilíbrio entre fases " + fmt1.format(d) + " %"
      : sem.some(Boolean) ? "Desequilíbrio: sem cálculo (fase sem medição)" : "Desequilíbrio: sem leitura das três fases");
  }
  // ⚠ A SEÇÃO DO RELÉ NA FICHA (refeita 18/11/2026, pedido do dono: "precisa deixar o status do disjuntor em
  // evidência, melhorar os gráficos pra ficar no tema da tela, os trips e etc"). Faixa de cima: o DISJUNTOR em
  // destaque, a proteção, a frequência e a temperatura; depois corrente e tensão por fase em cartões iguais aos dos
  // inversores; as proteções que atuaram em cartão próprio; e as etiquetas das monitoradas, que só acendem ao atuar.
  // Potência e fator de potência SAÍRAM até a leitura deles ser corrigida (hoje: ~2x a soma dos inversores, e o FP
  // em escala errada — mostrar seria afirmar números que não batem).
  function montarCardRele(rl, idx) {
    var br = bloco("Relé — " + (rl.cabine || ("Cabine " + (idx + 1))), "");
    br.classList.add("cos-rele");
    var card = { secao: br, det: br._detalhe, badges: {} };
    var faixa = releDiv("cos-rele-faixa");
    card.dj = releDiv("cos-rele-cartao cos-rele-dj"); card.dj.setAttribute("role", "status");
    card.djIcone = document.createElement("span"); card.dj.appendChild(card.djIcone);
    var djTxt = document.createElement("div");
    djTxt.appendChild(releDiv("cos-rele-rot", "Disjuntor"));
    card.djEstado = releDiv("cos-rele-dj-estado"); djTxt.appendChild(card.djEstado);
    card.djSub = releDiv("cos-rele-dj-sub"); djTxt.appendChild(card.djSub);
    card.dj.appendChild(djTxt); faixa.appendChild(card.dj);
    card.prot = releDiv("cos-rele-cartao");
    card.protRot = releDiv("cos-rele-rot", "Proteção"); card.prot.appendChild(card.protRot);
    card.status = releDiv("cos-rele-status"); card.prot.appendChild(card.status); faixa.appendChild(card.prot);
    var fq = releDiv("cos-rele-cartao"); fq.appendChild(releDiv("cos-rele-rot", "Frequência"));
    card.freq = releDiv("cos-rele-val"); fq.appendChild(card.freq); faixa.appendChild(fq);
    var tp = releDiv("cos-rele-cartao"); tp.appendChild(releDiv("cos-rele-rot", "Temperatura do relé"));
    card.temp = releDiv("cos-rele-val"); tp.appendChild(card.temp); faixa.appendChild(tp);
    br.appendChild(faixa);
    var fases = releDiv("cos-rele-fases");
    card.ci = releCartaoFase("Corrente por fase", "A"); fases.appendChild(card.ci.el);
    card.cv = releCartaoFase("Tensão por fase", "kV"); fases.appendChild(card.cv.el);
    br.appendChild(fases); card.fasesEl = fases; card.fq = fq; card.tp = tp;
    card.faltas = releDiv("cos-rele-faltas"); br.appendChild(card.faltas);
    br.appendChild(releDiv("cos-rele-rot", "Proteções monitoradas"));
    card.chips = releDiv("cos-rele-chips");
    RELE_FAMILIAS.forEach(function (fn) {
      var ch = document.createElement("span"); ch.className = "cos-rele-chip"; ch.title = fn[0] + " — " + fn[1];
      var b = document.createElement("b"); b.textContent = fn[0]; ch.appendChild(b);
      ch.appendChild(document.createTextNode(fn[1]));
      var fase = document.createElement("span"); ch.appendChild(fase);
      card.chips.appendChild(ch); card.badges[fn[0]] = { el: ch, fase: fase };
    });
    br.appendChild(card.chips);
    return card;
  }
  function atualizarUmRele(card, r) {
    var trips = r.trips || [];
    var atuou = !!r.responde && trips.length > 0;
    escrever(card.det, "textContent", !r.responde ? "sem comunicação" : (r.mins_atras != null ? "lido há " + r.mins_atras + " min" : "ao vivo"));
    // disjuntor — sem comunicação, não se afirma o estado velho
    var dj = r.responde ? r.disjuntor : null;
    var sigD = dj + "|" + (r.responde ? 1 : 0);
    if (card.dj._sig !== sigD) {
      card.dj._sig = sigD;
      card.dj.classList.toggle("cos-rele-dj--fechado", dj === 1);
      card.dj.classList.toggle("cos-rele-dj--aberto", dj === 0);
      card.dj.classList.toggle("cos-rele-dj--nada", dj !== 0 && dj !== 1);
      card.djIcone.textContent = ""; card.djIcone.appendChild(releIconeDj(dj));
      card.djEstado.textContent = releDisjuntor(dj);
      card.djSub.textContent = dj === 1 ? "usina conectada à rede" : dj === 0 ? "usina desconectada da rede"
        : (r.responde ? "o relé não informou o disjuntor" : "relé sem comunicação");
    }
    // proteção: o selo e, quando atuou, cada proteção num cartão; as etiquetas acendem junto
    var sigT = trips.join(",") + "|" + (r.responde ? 1 : 0);
    if (card.status._sig !== sigT) {
      card.status._sig = sigT; card.status.textContent = "";
      card.prot.classList.toggle("cos-rele-prot--atuou", atuou);
      card.protRot.textContent = "Proteção" + (atuou && trips.length > 1 ? " · " + trips.length + " atuadas" : "");
      if (!r.responde) { card.status.appendChild(pilula("neutro", "Sem comunicação")); }
      else if (trips.length) {
        card.status.appendChild(pilula("critico", "Atuou"));
        var g = releDiv("cos-rele-trips");
        trips.forEach(function (t) {
          var k = releDiv("cos-rele-trip"); k.title = t + " — " + releNomeFamilia(releFamilia(t));
          var b = document.createElement("b"); b.textContent = t; k.appendChild(b);
          var sm = document.createElement("small"); sm.textContent = releNomeFamilia(releFamilia(t)); k.appendChild(sm);
          var fs = releFaseDoCodigo(t); if (fs) { var s2 = document.createElement("small"); s2.textContent = fs; k.appendChild(s2); }
          g.appendChild(k);
        });
        card.status.appendChild(g);
      } else { card.status.appendChild(pilula("ok", "Sem atuação")); }
      var fam = {}; trips.forEach(function (t) { var f = releFamilia(t); (fam[f] = fam[f] || []).push(releFaseDoCodigo(t)); });
      Object.keys(card.badges).forEach(function (k) {
        var on = atuou && !!fam[k], fases = on ? fam[k].filter(Boolean) : [];
        card.badges[k].el.classList.toggle("ativa", on);
        card.badges[k].fase.textContent = fases.length ? " · " + fases.join(", ") : "";
      });
      // sem comunicação: os números são os da última leitura — apagados, para a tela não os afirmar como de agora
      [card.chips, card.fasesEl, card.fq, card.tp].forEach(function (el) { el.classList.toggle("muda", !r.responde); });
    }
    var m = r.medidas || {};
    escrever(card.freq, "textContent", m.freq == null || isNaN(m.freq) ? "—" : fmt2.format(m.freq) + " Hz");
    escrever(card.temp, "textContent", m.temp == null || isNaN(m.temp) ? "—" : fmt1.format(m.temp) + " °C");
    releAtualizarFase(card.ci, [m.iA, m.iB, m.iC], true);
    releAtualizarFase(card.cv, [m.vA, m.vB, m.vC].map(function (v) { return v == null || isNaN(v) ? null : v / 1000; }), false);
    // o que o relé registrou na atuação (só depois de um trip)
    var ff = r.faltas || {};
    var chavesF = ["ifA", "ifB", "ifC", "ifN", "vfA", "vfB", "vfC"];
    var temDadoFalta = chavesF.some(function (k) { return ff[k] != null; });
    var temFalta = temDadoFalta && (trips.length > 0 || chavesF.some(function (k) { return ff[k]; }));
    var sigF = (temFalta ? 1 : 0) + "|" + chavesF.map(function (k) { return ff[k]; }).join(",");
    if (card.faltas._sig !== sigF) {
      card.faltas._sig = sigF; card.faltas.textContent = "";
      if (temFalta) {
        card.faltas.appendChild(releDiv("cos-rele-rot", "Registrado pelo relé no trip"));
        var gf = releDiv("cos-rele-falta-grade");
        [["Corrente A", ff.ifA, "A"], ["Corrente B", ff.ifB, "A"], ["Corrente C", ff.ifC, "A"], ["Neutro", ff.ifN, "A"],
         ["Tensão A", ff.vfA, "kV"], ["Tensão B", ff.vfB, "kV"], ["Tensão C", ff.vfC, "kV"]].forEach(function (x) {
          if (x[1] == null) { return; }
          var cf = releDiv("cos-rele-cartao"); cf.appendChild(releDiv("cos-rele-rot", x[0]));
          cf.appendChild(releDiv("cos-rele-val", x[2] === "A" ? braw(x[1]) + " A" : releKv(x[1]) + " kV"));
          gf.appendChild(cf);
        });
        card.faltas.appendChild(gf);
      }
    }
  }

  // monta a estrutura uma vez; a cada 3 s só os números, os estados e os gráficos que mudaram
  function montar(c) {
    partes = { invs: {} };
    var frag = document.createDocumentFragment();
    var res = document.createElement("div"); res.className = "cos-inv-resumo";
    partes.kw = document.createElement("span"); partes.kw.className = "kw"; res.appendChild(partes.kw);
    partes.resumo = document.createElement("span"); partes.resumo.className = "d"; res.appendChild(partes.resumo);
    partes.estados = document.createElement("span"); partes.estados.className = "cos-inv-estados"; res.appendChild(partes.estados);
    frag.appendChild(res);
    var cos = cosDaUsina(aberta.getAttribute("data-codigo")); if (cos) { frag.appendChild(cos); }
    var bu = bloco("A usina hoje", ""); partes.tituloU = bu._titulo; partes.detU = bu._detalhe;
    partes.gu = document.createElement("div"); partes.gu.className = "cos-inv-graf"; bu.appendChild(partes.gu); frag.appendChild(bu);
    var bi = bloco("Cada inversor", ""); partes.escala = bi._detalhe;
    // CURVAS OU BARRAS NA JANELA (25/11/2026, o dono com a janela da Altair 5 aberta: "aqui tinha que ter a visualização em
    // barra também"): a MESMA escolha do seletor do alto da tela (um localStorage só) e, nas barras, o que se compara: o kW
    // de agora ou a energia do trecho do gráfico (o dia inteiro, ou o do zoom), pela curva gravada
    var sel = document.createElement("div"); sel.className = "cos-inv-vista";
    sel.setAttribute("role", "group"); sel.setAttribute("aria-label", "Como ver os inversores");
    partes.btVista = {}; partes.btMetrica = {};
    [["curva", "Curvas"], ["barras", "Barras"]].forEach(function (par) {
      var b = document.createElement("button"); b.type = "button"; b.className = "gc-chip"; b.textContent = par[1];
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", function () { trocarVista(par[0]); });
      partes.btVista[par[0]] = b; sel.appendChild(b);
    });
    partes.selMetrica = document.createElement("span"); partes.selMetrica.className = "cos-inv-vista-metrica";
    partes.selMetrica.setAttribute("role", "group"); partes.selMetrica.setAttribute("aria-label", "O que as barras comparam");
    [["agora", "Agora (kW)"], ["energia", "Energia do trecho"]].forEach(function (par) {
      var b = document.createElement("button"); b.type = "button"; b.className = "gc-chip"; b.textContent = par[1];
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", function () { metricaBarras = par[0]; if (aberta && vivo) { aoVivoNaJanela(); } });
      partes.btMetrica[par[0]] = b; partes.selMetrica.appendChild(b);
    });
    sel.appendChild(partes.selMetrica);
    bi.appendChild(sel);
    partes.barras = document.createElement("div"); partes.barras.className = "cos-inv-barras"; partes.barras.hidden = true; bi.appendChild(partes.barras);
    var grade = document.createElement("div"); grade.className = "cos-inv-grade"; bi.appendChild(grade); frag.appendChild(bi);
    partes.grade = grade;
    ordenados(c).forEach(function (i) {
      var p = {}, id = i.id, nome = nomeDoInversor(i);
      p.art = document.createElement("article");
      var cab = document.createElement("div"); cab.className = "cos-inv-i-cab";
      if (detEl) {
        // 13/11/2026: o inversor abre o detalhe dele. O botão é o nome (o teclado chega nele); o mouse abre pelo cartão todo
        p.abrir = document.createElement("button"); p.abrir.type = "button"; p.abrir.className = "cos-inv-i-abrir";
        p.abrir.setAttribute("aria-label", "Abrir o detalhe do " + nome + ": a curva e as entradas");
        var nb = document.createElement("b"); nb.textContent = nome; p.abrir.appendChild(nb);
        if (textoDoSerial(i)) { var snb = document.createElement("small"); snb.className = "cos-inv-sn"; snb.textContent = textoDoSerial(i); p.abrir.appendChild(snb); }
        var seta = document.createElement("span"); seta.setAttribute("aria-hidden", "true"); seta.textContent = "›"; p.abrir.appendChild(seta);
        cab.appendChild(p.abrir);
        p.art.title = "Abrir o detalhe do " + nome;
        p.art.addEventListener("click", function (ev) { if (ev.target.closest && ev.target.closest("a")) { return; } abrirInversor(id); });
        // o histórico do dia pedido ao passar o mouse (ou o foco) no inversor, como a curva da usina no cartão: quando o
        // detalhe abre, o gráfico das strings já vem com o gravado (o dono: "eu preciso do gráfico do dia em tempo real")
        var antesHist = null;
        var preCarregarHist = function () {
          if (ehDoSunop(i)) { return; }                    // o SunOP não tem histórico de strings (25/11/2026)
          clearTimeout(antesHist);
          antesHist = setTimeout(function () { lerHistorico(id, diaEscolhido).catch(function () {}); }, 150);
        };
        p.art.addEventListener("pointerenter", preCarregarHist);
        p.art.addEventListener("focusin", preCarregarHist);
      } else {
        var b = document.createElement("b"); b.textContent = nome;
        var nomeEl = document.createElement("span"); nomeEl.className = "cos-inv-i-nome"; nomeEl.appendChild(b); cab.appendChild(nomeEl);
        if (textoDoSerial(i)) { var sn = document.createElement("small"); sn.className = "cos-inv-sn"; sn.textContent = textoDoSerial(i); nomeEl.appendChild(sn); }
      }
      p.kv = document.createElement("span"); p.kv.className = "cos-inv-i-kw"; cab.appendChild(p.kv);
      p.art.appendChild(cab);
      p.estado = document.createElement("div"); p.estado.className = "cos-inv-estado"; p.art.appendChild(p.estado);
      p.graf = document.createElement("div"); p.graf.className = "cos-inv-graf"; p.art.appendChild(p.graf);
      grade.appendChild(p.art);
      partes.invs[i.id] = p;
    });
    if (c.reles && c.reles.length) {
      partes.reles = [];
      c.reles.forEach(function (rl, idx) { var card = montarCardRele(rl, idx); partes.reles.push(card); frag.appendChild(card.secao); });
    }
    var tab = document.createElement("details"); tab.className = "cos-inv-tabela";
    var su = document.createElement("summary"); su.className = "cn-link"; su.textContent = "Ver os inversores em tabela"; tab.appendChild(su);
    var t = document.createElement("table");
    t.innerHTML = "<thead><tr><th>Inversor</th><th>Estado</th><th class='n'>Agora</th><th class='n' data-th='max'>Máximo hoje</th><th class='n' data-th='energia'>Energia hoje</th></tr></thead>";
    partes.thMax = t.querySelector("[data-th=max]"); partes.thEnergia = t.querySelector("[data-th=energia]");
    partes.tbody = document.createElement("tbody"); t.appendChild(partes.tbody); tab.appendChild(t); frag.appendChild(tab);
    corpo.textContent = ""; corpo.appendChild(frag);
  }

  function atualizar(c, cv) {
    cv = cv || SEM_CURVA;
    var gerando = c.situacao && c.situacao.chave === "GERANDO";
    var sig = ordenados(c).map(function (i) { return i.id + "=" + i.veredito + "#" + (serialDoInversor(i) || ""); }).join(",") + (c.reles && c.reles.length ? "|reles:" + c.reles.map(function (r) { return r.cabine || ""; }).join(",") : "");
    if (!partes || sig !== assinatura) { assinatura = sig; montar(c); }
    graficos = [];
    var porId = {};
    // num dia que passou não há ponta: a curva é só a gravada daquele dia
    var hoje = ehHoje(), quando = hoje ? "hoje" : "em " + diaCurto(diaEscolhido);
    (cv.inversores || []).forEach(function (s) { var id = s.usina_id + ":" + s.modbus_id; porId[id] = hoje ? comPonta(serie(s.pontos), "i:" + id) : serie(s.pontos); });
    if (invAberto) { detalhe(c, porId); return; }           // a usina fica montada por baixo, sem redesenhar
    escrever(partes.kw, "textContent", kw(c.pac_total_kw));
    escrever(partes.resumo, "textContent", (c.inversores_online != null ? c.inversores_online : "—") + " de " + c.inversores_total + " inversores respondendo · " + (c.situacao ? c.situacao.texto : ""));
    var conta = {}, chips = [];
    (c.inversores || []).forEach(function (i) { conta[i.veredito] = (conta[i.veredito] || 0) + 1; });
    Object.keys(conta).sort(function (a, b) { return (ORDEM[a] || 9) - (ORDEM[b] || 9); }).forEach(function (v) { chips.push(v + conta[v]); });
    if (partes.estados._sig !== chips.join()) {
      partes.estados._sig = chips.join(); partes.estados.textContent = "";
      Object.keys(conta).sort(function (a, b) { return (ORDEM[a] || 9) - (ORDEM[b] || 9); }).forEach(function (v) {
        var e = ESTADO[v] || { rotulo: v, tom: "neutro" };
        partes.estados.appendChild(pilula(gerando || !e.grupo ? e.tom : "neutro", conta[v] + " " + e.rotulo.toLowerCase()));
      });
    }
    var invs = ordenados(c);
    // a escala comum dos inversores, pelo que se vê no trecho do zoom (o de agora entra só se agora está à vista)
    var eInv = escalaDe(invs.map(function (i) { return porId[i.id] || []; }), 2, hoje && agoraVisivel() ? invs.map(function (i) { return i.pac; }) : []);
    escrever(partes.tituloU, "textContent", "A usina " + quando);
    escrever(partes.detU, "textContent", (hoje ? "a curva gravada de 5 em 5 min e a ponta ao vivo, " + (ehDoSunop(c) ? "a cada leitura do portal (1 min)" : "de 3 em 3 s") : "a curva gravada de 5 em 5 min") +
      " · passe o mouse (ou use as setas) para ler a hora; arraste para aproximar (uma caixa aproxima também o valor; duplo clique volta)");
    escrever(partes.thMax, "textContent", "Máximo " + quando);
    escrever(partes.thEnergia, "textContent", "Energia " + quando);
    var emBarras = vista === "barras", metrica = hoje ? metricaBarras : "energia";
    escrever(partes.grade, "hidden", emBarras); escrever(partes.barras, "hidden", !emBarras); escrever(partes.selMetrica, "hidden", !emBarras);
    Object.keys(partes.btVista).forEach(function (k) {
      var v = String(k === (emBarras ? "barras" : "curva"));
      if (partes.btVista[k].getAttribute("aria-pressed") !== v) { partes.btVista[k].setAttribute("aria-pressed", v); }
    });
    Object.keys(partes.btMetrica).forEach(function (k) {
      var v = String(k === metrica);
      if (partes.btMetrica[k].getAttribute("aria-pressed") !== v) { partes.btMetrica[k].setAttribute("aria-pressed", v); }
    });
    escrever(partes.btMetrica.agora, "disabled", !hoje);                // num dia que passou não há "agora"
    escrever(partes.btMetrica.agora, "title", hoje ? "O kW de cada inversor agora, ao vivo" : "Num dia que passou não há leitura de agora: só a energia");
    escrever(partes.escala, "textContent", emBarras
      ? (metrica === "energia" ? "a energia de cada inversor em " + textoDoTrecho(zoom) + (hoje ? " (até agora)" : "") + ", pela curva gravada de 5 em 5 min" : "o kW de cada inversor agora") +
        " · a linha tracejada é a mediana dos que geraram: quem fica abaixo dela gera menos que os vizinhos" + (detEl ? " · clique numa barra para abrir o inversor" : "")
      : cv === SEM_CURVA ? "lendo a curva gravada do dia… os pontos ao vivo já aparecem"
      : "todos na mesma escala (" + rotuloDaEscala(faixasY.inversores || eInv, "kW") + "): quem gera menos fica visivelmente mais baixo" + (detEl ? " · clique num inversor para ver a curva dele e as strings" : ""));
    // as larguras lidas antes de desenhar (um layout só, e não um por gráfico)
    var larguraUsina = partes.gu.clientWidth, larguras = {};
    invs.forEach(function (i) { var p = partes.invs[i.id]; if (p) { larguras[i.id] = p.graf.clientWidth; } });
    var pu = hoje ? comPonta(serie(cv.usina), "u:" + aberta.getAttribute("data-gid")) : serie(cv.usina), eU = escalaDe([pu], 4);
    grafico(partes.gu, [{ pts: pu }], { h: 230, min: eU.min, max: eU.max, escala: "usina", eixoX: true, eixoY: true, rotuloFim: true, vivo: hoje, semAgora: !hoje,
      nome: "usina", rotulo: "Curva " + quando + " da usina" }, larguraUsina);
    var linhas = [];
    invs.forEach(function (i) {
      var p = partes.invs[i.id]; if (!p) { return; }
      var e = ESTADO[i.veredito] || { rotulo: i.veredito || "—", tom: "neutro" };
      var grupo = gerando && e.grupo ? e.grupo : "";
      escrever(p.art, "className", "cos-inv-i" + (detEl ? " cos-inv-i--abre" : "") + (grupo === "fora" ? " cos-inv-i--fora" : grupo === "semcom" ? " cos-inv-i--semcom" : ""));
      var kwAgora = function () { p.kv.textContent = kw(i.pac); var sm = document.createElement("small"); sm.textContent = "agora"; p.kv.appendChild(sm); };
      if (cruzEm == null) { kwAgora(); }
      var motivo = motivoDoEstado(i, e);
      var sigEstado = e.rotulo + "|" + grupo + "|" + (motivo || "");
      if (p.estado._sig !== sigEstado) {
        p.estado._sig = sigEstado; p.estado.textContent = "";
        p.estado.appendChild(pilula(grupo ? e.tom : (e.grupo ? "neutro" : e.tom), e.rotulo));
        if (motivo) { var mo = document.createElement("span"); mo.className = "cos-inv-motivo"; mo.textContent = motivo; p.estado.appendChild(mo); }
      }
      // a cor do estado (desligado, sem comunicação) é de AGORA: num dia que passou, a linha fica na cor de sempre. Nas
      // barras a grade está escondida: o gráfico de cada inversor não é desenhado (largura zero, e ninguém o vê)
      if (!emBarras) grafico(p.graf, [{ pts: porId[i.id] || [] }], { h: 78, min: eInv.min, max: eInv.max, escala: "inversores", grupo: hoje ? grupo : "", vivo: hoje, semAgora: !hoje, nome: nomeDoInversor(i),
        rotulo: "Curva " + quando + " de " + (i.nome || i.modbus_id),
        aoMarcar: function (pt, min) {
          if (min == null) { kwAgora(); return; }
          p.kv.textContent = pt && pt[1] != null ? kw(pt[1]) : "—";
          var sm = document.createElement("small"); sm.textContent = "às " + hhmm(min); p.kv.appendChild(sm);
        } }, larguras[i.id]);
      var mx = null;
      (porId[i.id] || []).forEach(function (q) { if (q[1] != null && (!mx || q[1] > mx[1])) { mx = q; } });
      linhas.push([nomeDoInversor(i) + (textoDoSerial(i) ? " · " + textoDoSerial(i) : ""), e.rotulo, kw(i.pac), mx ? kw(mx[1]) + " às " + hhmm(mx[0]) : "—",
        hoje && i.geracao_dia != null ? fmtKW.format(i.geracao_dia) + " kWh" : "—"]);
    });
    if (emBarras) {
      var b = null;
      if (metrica === "energia") {
        var tr = trechoAtual(), valores = {};
        (cv.inversores || []).forEach(function (s) { valores[s.usina_id + ":" + s.modbus_id] = energiaDaSerie(serie(s.pontos), tr.de, tr.ate); });
        if (cv !== SEM_CURVA) { b = barrasDaUsina(c, { valores: valores, semEstado: !hoje }); }
      } else { b = barrasDaUsina(c); }
      graficoDeBarras(partes.barras, b, { gerando: gerando, carregando: metrica === "energia" && cv === SEM_CURVA,
        nome: (aberta.querySelector(".n") || {}).textContent || "esta usina" });
    }
    var sigTab = JSON.stringify(linhas);
    if (partes.tbody._sig !== sigTab) {
      partes.tbody._sig = sigTab; partes.tbody.textContent = "";
      linhas.forEach(function (l) {
        var tr = document.createElement("tr");
        l.forEach(function (v, k) { var td = document.createElement("td"); if (k >= 2) { td.className = "n"; } td.textContent = v; tr.appendChild(td); });
        partes.tbody.appendChild(tr);
      });
    }
    if (partes.reles && c.reles) { partes.reles.forEach(function (card, idx) { if (c.reles[idx]) { atualizarUmRele(card, c.reles[idx]); } }); }
    if (cruzEm != null) { marcarTodos(cruzEm, null, null, null); }      // a cruz fica onde estava
  }

  // A janela troca a vista da tela inteira (a mesma escolha do seletor do alto, um localStorage só)
  function trocarVista(v) {
    aplicarVista(v); guardarVista(raiz.localStorage, vista);
    desenharTodasAsBarras(mapaVivo);
    if (aberta && vivo) { aoVivoNaJanela(); }
  }
  // AS BARRAS DA JANELA (25/11/2026): uma coluna por inversor, na ordem da usina, com o eixo na unidade do que se compara
  // (kW, % da nominal, kWh ou kWh por kW), o nome embaixo, o valor em cima quando cabe e a mediana tracejada. A coluna
  // inteira é o alvo do clique, que abre o inversor (o teclado abre pela tabela ou pela vista de curvas).
  function rotuloDoEixoDasBarras(b, v) {
    if (b.energia) { return b.porNominal ? fmtAte1.format(v) + " kWh/kW" : kwh(v); }
    return b.porNominal ? Math.round(v * 100) + "%" : kw(v);
  }
  function graficoDeBarras(host, b, o) {
    var w = Math.max(240, host.clientWidth || 600);
    var sig = JSON.stringify([w, b && b.barras, b && b.mediana, o.gerando, o.carregando]);
    if (host._sig === sig) { return; }
    host._sig = sig; host.textContent = "";
    if (!b || !b.barras.length) {
      var vazio = document.createElement("p"); vazio.className = "mudo";
      vazio.textContent = o.carregando ? "lendo a curva gravada do dia…" : "sem a leitura dos inversores agora";
      host.appendChild(vazio); return;
    }
    var n = b.barras.length, maxNome = 0, maxSerial = 0;
    b.barras.forEach(function (x) {
      maxNome = Math.max(maxNome, String(x.nome).length);
      if (x.serial) { maxSerial = Math.max(maxSerial, ("S/N " + x.serial).length); }
    });
    var ml = 60, mr = 10, mt = 20, iw = w - ml - mr, passo = iw / n;
    // o nome (ou o S/N, menor) que não cabe na largura da coluna vai inclinado; sem serial, a conta de antes
    var gira = maxNome * 6.2 > passo - 4 || maxSerial * 5.6 > passo - 4;
    var mb = !gira ? (maxSerial ? 40 : 28)
      : maxSerial ? Math.min(150, 18 + 0.82 * (maxNome * 6.2 + 18 + maxSerial * 5.6)) : Math.min(96, 14 + maxNome * 5.2);
    var h = 200 + mb, ih = h - mt - mb;
    var teto = tetoBonito(b.topo > 0 ? b.topo : 1, 4), bw = Math.max(2, Math.min(44, passo * 0.68));
    var y = function (v) { return mt + ih - Math.max(0, Math.min(1, v / teto)) * ih; };
    var svg = el("svg", { viewBox: "0 0 " + w + " " + h, width: w, height: h, class: "pg cos-inv-barras-svg", role: "img",
      "aria-label": "Barras dos inversores de " + o.nome + ": " + resumoDasBarras(b, o.gerando) }, null);
    var grade = el("g", { class: "pg-grade" }, svg), eixo = el("g", { class: "pg-eixo" }, svg);
    for (var k = 0; k <= 4; k++) {
      var v = teto * k / 4, yy = Math.round(y(v)) + 0.5;
      el("line", { x1: ml, y1: yy, x2: w - mr, y2: yy }, grade);
      el("text", { x: ml - 6, y: yy + 4, "text-anchor": "end" }, eixo).textContent = rotuloDoEixoDasBarras(b, v);
    }
    b.barras.forEach(function (x, k) {
      var x0 = ml + k * passo, cx = x0 + passo / 2, g = el("g", { class: "cos-inv-barra-g" }, svg);
      var sem = x.tom === "sem", alt = sem ? 4 : Math.max(1.5, mt + ih - y(x.fracao * b.topo));
      el("rect", { class: "cos-inv-barra cos-inv-barra--" + x.tom, x: cx - bw / 2, y: mt + ih - alt, width: bw, height: alt }, g);
      if (bw >= 26 && x.valor != null) {
        el("text", { class: "cos-inv-barras-val", x: cx, y: mt + ih - alt - 4, "text-anchor": "middle" }, g).textContent =
          b.energia ? (b.porNominal ? fmtAte1.format(x.porKw) : fmtKW.format(x.valor)) : (b.porNominal ? x.pct + "%" : fmtKW.format(x.kw));
      }
      var tn = el("text", { class: "cos-inv-barras-rot", x: cx, y: mt + ih + 14, "text-anchor": gira ? "end" : "middle" }, g);
      if (gira) { tn.setAttribute("transform", "rotate(-55 " + cx + " " + (mt + ih + 10) + ")"); }
      tn.textContent = x.nome;
      if (x.serial) {
        var ts = el("tspan", { class: "cos-inv-barras-sn" }, tn);
        if (gira) { ts.textContent = " · S/N " + x.serial; }
        else { ts.setAttribute("x", cx); ts.setAttribute("dy", 12); ts.textContent = "S/N " + x.serial; }
      }
      var alvo = el("rect", { class: "cos-inv-barra-alvo", x: x0, y: mt, width: passo, height: ih + mb }, g);
      el("title", {}, alvo).textContent = x.nome + (x.serial ? " (S/N " + x.serial + ")" : "") + " · " + valorDaBarra(b, x) + (x.rotulo ? " · " + x.rotulo : "");
      if (detEl) { alvo.addEventListener("click", function () { abrirInversor(x.id); }); }
    });
    el("line", { class: "pg-base", x1: ml, y1: mt + ih + 0.5, x2: w - mr, y2: mt + ih + 0.5 }, svg);
    if (b.mediana != null && (b.energia || o.gerando)) {
      var ym = y(b.medianaBruta), lm = el("g", {}, svg);
      el("line", { class: "cos-inv-barras-mediana", x1: ml, y1: ym, x2: w - mr, y2: ym }, lm);
      el("text", { class: "cos-inv-barras-val", x: w - mr, y: ym - 4, "text-anchor": "end" }, lm).textContent = "mediana " + textoDaMediana(b);
    }
    host.appendChild(svg);
    var d = document.createElement("p"); d.className = "d"; d.textContent = resumoDasBarras(b, o.gerando); host.appendChild(d);
  }

  // ── 3. o DETALHE de um inversor (13/11/2026) ────────────────────────────────────────────────────────────────────
  // A curva dele no dia escolhido, as entradas de agora (ao vivo) e as entradas DO DIA: o histórico gravado de 5 em 5 min
  // (a scada_entradas da Ronda COS, 45 dias) e, em hoje, a ponta ao vivo do registro desde a abertura, como a curva faz.
  // Monta uma vez por inversor; a cada 3 s, só os números, as barras que mudaram e os gráficos cuja série mudou.
  // ⚠ NENHUM callback guardado (aoMarcar, dica, clique, a volta de um pedido) lê o `det` global: o fechar() o zera antes
  // de a limpeza chamar os callbacks, e lendo `det.f` a janela não fechava (PR #25, 13/11/2026). O que eles precisam fica
  // preso numa variável local na hora de desenhar.
  function com(a, b) { var o = {}, k; for (k in a) { o[k] = a[k]; } for (k in b) { o[k] = b[k]; } return o; }
  function lembrarFoco() {                               // o foco num botão que vai ser refeito volta para o novo
    var a = document.activeElement;
    return a && detCorpo && detCorpo.contains(a) ? a.getAttribute("data-foco") : null;
  }
  function devolverFoco(chave) {
    if (!chave) { return; }
    var n = detCorpo.querySelector('[data-foco="' + chave + '"]');
    if (n) { n.focus({ preventScroll: true }); } else { detTitulo.focus({ preventScroll: true }); }
  }
  function modoDe(ent) {                                  // a escolha da pessoa segue para os outros inversores, até recarregar
    var m = modo || (ent.porMppt ? "mppt" : "individual");
    return m === "mppt" && !ent.porMppt ? "individual" : m;
  }
  function abrirInversor(id) {
    if (!detEl || !aberta || !vivo) { return; }
    // outro inversor: o trecho do horário fica (a mesma usina), e a faixa de valor das caixas do detalhe sai (era de outro)
    Object.keys(faixasY).forEach(function (k) { if (k !== "usina" && k !== "inversores") { delete faixasY[k]; } });
    invAberto = id; det = null; limparTodos();
    corpo.hidden = true; detEl.hidden = false;
    aoVivoNaJanela();                                     // desenha já, com a leitura de agora
    dlg.scrollTop = 0;
    detTitulo.focus({ preventScroll: true });             // o leitor de tela anuncia o inversor; o Tab segue para o voltar
  }
  function sairDoDetalhe() {
    invAberto = null; det = null; ampliado = "";
    if (detEl) { detEl.hidden = true; detCorpo.textContent = ""; }
    if (corpo) { corpo.hidden = false; }
  }
  function voltarAUsina() {
    var id = invAberto;
    limparTodos(); sairDoDetalhe(); graficos = [];
    if (aberta && vivo) { aoVivoNaJanela(); }
    var p = partes && partes.invs[id];
    if (p && p.abrir && p.abrir.isConnected) { p.abrir.focus(); }   // o foco volta ao inversor de onde se saiu
    else { var f = dlg.querySelector(".cos-inv-fechar"); if (f) { f.focus(); } }
  }
  function alternarDestaque(chave) {                     // destaca e desfaz; quantas quiser (13/11/2026: sem o teto de 4)
    var d = destaques[invAberto] || (destaques[invAberto] = {});
    if (d[chave]) { delete d[chave]; } else { d[chave] = true; }
    aoVivoNaJanela();
  }

  // O HISTÓRICO DAS ENTRADAS de um inversor num dia: um pedido por inversor e dia (`/scada/entradas/<logger>/<modbus>`);
  // o de hoje é relido de 5 em 5 min (a gravação é de 5 em 5), o de um dia que passou fica guardado. Os últimos
  // HIST_GUARDADOS, como as curvas.
  var historicos = {}, ordemHist = [], pedidosHist = {}, falhouHist = {}, HIST_GUARDADOS = 20;
  function chaveHist(id, dia) { return id + "|" + (dia || "hoje"); }
  function lerHistorico(id, dia) {
    var k = chaveHist(id, dia), g = historicos[k];
    if (pedidosHist[k]) { return pedidosHist[k]; }
    if (g && (dia || Date.now() - g.em < CURVA_MS)) { return Promise.resolve(g.h); }
    if (falhouHist[k] && Date.now() - falhouHist[k] < 30000) { return Promise.reject({ erro: "o histórico falhou há pouco; tenta de novo em 30 s" }); }
    var p = String(id).split(":");                        // o id do inversor é "<logger>:<modbus>" (scada.parser.ts)
    if (p.length !== 2) { return Promise.reject({ erro: "o inversor não diz de qual logger é" }); }
    pedidosHist[k] = pedir("/scada/entradas/" + encodeURIComponent(p[0]) + "/" + encodeURIComponent(p[1]) + (dia ? "?dia=" + dia : ""))
      .then(function (r) {
        historicos[k] = { h: entradasDoHistorico(r), em: Date.now() };
        ordemHist = ordemHist.filter(function (x) { return x !== k; }).concat([k]);
        while (ordemHist.length > HIST_GUARDADOS) { delete historicos[ordemHist.shift()]; }
        delete pedidosHist[k]; delete falhouHist[k];
        return historicos[k].h;
      }, function (e) { delete pedidosHist[k]; falhouHist[k] = Date.now(); throw e; });
    return pedidosHist[k];
  }

  function montarDetalhe(i) {
    det = { id: i.id, cache: {}, cacheChave: "", montado: "", entSig: "" };
    var frag = document.createDocumentFragment();
    det.estado = document.createElement("div"); det.estado.className = "cos-inv-estado cos-inv-det-estado"; frag.appendChild(det.estado);
    var fatos = document.createElement("dl"); fatos.className = "cos-inv-fatos";
    det.f = {}; det.rot = {};
    [["agora", "Agora"], ["max", "Máximo hoje"], ["energia", "Energia hoje"], ["temp", "Temperatura"], ["nominal", "Potência nominal"]].forEach(function (par) {
      var d = document.createElement("div"), dt = document.createElement("dt"), dd = document.createElement("dd");
      dt.textContent = par[1]; dd.className = "gc-num"; d.appendChild(dt); d.appendChild(dd); fatos.appendChild(d);
      det.f[par[0]] = dd; det.rot[par[0]] = dt;
    });
    frag.appendChild(fatos);
    var bc = bloco("Curva de hoje", ""); det.tituloCurva = bc._titulo; det.detCurva = bc._detalhe;
    var hostCurva = document.createElement("div"); hostCurva.className = "cos-inv-graf"; det.gc = hostCurva;
    det.btAmpliarCurva = botaoAmpliar("inversor", hostCurva); bc.firstChild.appendChild(det.btAmpliarCurva);
    bc.appendChild(hostCurva); frag.appendChild(bc);
    var be = bloco("", "agora, de 3 em 3 s (ao vivo)"); det.entTit = be._titulo;
    det.ent = document.createElement("div"); det.ent.className = "cos-inv-ent"; be.appendChild(det.ent);
    det.nota = document.createElement("p"); det.nota.className = "cos-inv-ent-nota"; be.appendChild(det.nota);
    frag.appendChild(be);
    var bs = bloco("", ""); det.stTit = bs._titulo; det.stDet = bs._detalhe;
    det.stAviso = document.createElement("p"); det.stAviso.className = "cos-inv-hist-aviso"; det.stAviso.setAttribute("role", "status");
    bs.appendChild(det.stAviso);
    det.modos = document.createElement("div"); det.modos.className = "cos-inv-modos";
    det.modos.setAttribute("role", "group"); det.modos.setAttribute("aria-label", "Como ver as entradas");
    det.botoes = {};
    [["individual", "Individual"], ["mppt", "Por MPPT"], ["todas", "Todas"]].forEach(function (par) {
      var b = document.createElement("button"); b.type = "button"; b.className = "gc-chip"; b.textContent = par[1];
      b.setAttribute("data-foco", "modo:" + par[0]); b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", function () { modo = par[0]; aoVivoNaJanela(); });
      det.botoes[par[0]] = b; det.modos.appendChild(b);
    });
    det.btAmpliarTodas = botaoAmpliar("todas", function () { return detCorpo.querySelector('[data-amplia="todas"]'); });
    det.modos.appendChild(det.btAmpliarTodas);
    bs.appendChild(det.modos);
    det.chips = document.createElement("div"); det.chips.className = "cos-inv-chips"; det.chips.hidden = true;
    det.chips.setAttribute("role", "group");
    det.chips.setAttribute("aria-label", "Destacar strings no gráfico: clique destaca, de novo desfaz; duplo clique (ou Shift+Enter) mostra só esta");
    bs.appendChild(det.chips);
    det.sg = document.createElement("div"); det.sg.className = "cos-inv-sg"; bs.appendChild(det.sg);
    frag.appendChild(bs);
    detCorpo.textContent = ""; detCorpo.appendChild(frag);
  }

  function detalhe(c, porId) {
    var i = null;
    (c.inversores || []).forEach(function (x) { if (x.id === invAberto) { i = x; } });
    if (!i) {
      if (!det || !det.falta) {
        var foco = detCorpo.contains(document.activeElement);
        detCorpo.textContent = "";
        var av = document.createElement("p"); av.className = "cos-inv-aviso";
        av.textContent = ehDoSunop(c) ? "Este inversor não veio na leitura do SunOP agora. A janela tenta de novo a cada 20 segundos."
          : "Este inversor não veio na leitura do SCADA agora. A janela tenta de novo a cada 3 segundos.";
        detCorpo.appendChild(av); det = { falta: true };
        if (foco) { detTitulo.focus({ preventScroll: true }); }
      }
      return;
    }
    var nome = nomeDoInversor(i), hoje = ehHoje(), dia = diaEscolhido, quando = hoje ? "hoje" : "em " + diaCurto(dia);
    escrever(detTitulo, "textContent", nome);
    escrever(detSub, "textContent", [i.parte, i.modelo, textoDoSerial(i)].filter(Boolean).join(" · "));
    if (!det || det.falta || det.id !== i.id) { var lembrado = lembrarFoco(); montarDetalhe(i); devolverFoco(lembrado); }
    var gerando = c.situacao && c.situacao.chave === "GERANDO";
    var e = ESTADO[i.veredito] || { rotulo: i.veredito || "—", tom: "neutro" };
    var grupo = gerando && e.grupo ? e.grupo : "", motivo = motivoDoEstado(i, e);
    var sigEstado = e.rotulo + "|" + grupo + "|" + (motivo || "");
    if (det.estado._sig !== sigEstado) {
      det.estado._sig = sigEstado; det.estado.textContent = "";
      det.estado.appendChild(pilula(grupo ? e.tom : (e.grupo ? "neutro" : e.tom), e.rotulo));
      if (motivo) { var mo = document.createElement("span"); mo.className = "cos-inv-motivo"; mo.textContent = motivo; det.estado.appendChild(mo); }
    }
    var pts = porId[i.id] || [], mx = null;
    pts.forEach(function (q) { if (q[1] != null && (!mx || q[1] > mx[1])) { mx = q; } });
    // ⚠ Os campos ficam presos AQUI (`campos`), e não lidos de `det` na hora (PR #25: o fechar() zera o `det` antes)
    var campos = det.f;
    var agoraTxt = function () { campos.agora.textContent = kw(i.pac); var sm = document.createElement("small"); sm.textContent = "agora"; campos.agora.appendChild(sm); };
    if (cruzEm == null) { agoraTxt(); }
    escrever(det.rot.max, "textContent", "Máximo " + quando);
    escrever(campos.max, "textContent", mx ? kw(mx[1]) + " às " + hhmm(mx[0]) : "—");
    // a energia do dia vem do contador do equipamento, só ao vivo: de um dia que passou, não há número a afirmar
    escrever(det.rot.energia, "textContent", "Energia " + quando);
    escrever(campos.energia, "textContent", hoje && i.geracao_dia != null ? fmtKW.format(i.geracao_dia) + " kWh" : "—");
    escrever(campos.temp, "textContent", i.temperatura != null ? fmt1.format(i.temperatura) + " °C" : "—");
    // a nominal derivada do nome do modelo se diz como tal (o número medido e o derivado não têm o mesmo peso)
    escrever(campos.nominal, "textContent", i.capacidade != null ? kw(i.capacidade) + (i.capacidade_origem === "modelo" ? " (pelo modelo)" : "") : "—");
    escrever(det.tituloCurva, "textContent", "Curva " + (hoje ? "de hoje" : "de " + diaCurto(dia)));
    escrever(det.detCurva, "textContent", hoje ? "a curva gravada de 5 em 5 min e a ponta ao vivo, de 3 em 3 s" : "a curva gravada de 5 em 5 min");
    var eC = escalaDe([pts], 4, hoje && agoraVisivel() ? [i.pac] : []);
    mostrarAmpliar(det.btAmpliarCurva, "inversor");
    grafico(det.gc, [{ pts: pts }], { h: alturaDe("inversor", 230), min: eC.min, max: eC.max, escala: "inversor", eixoX: true, eixoY: true,
      rotuloFim: true, vivo: hoje, semAgora: !hoje, grupo: hoje ? grupo : "", nome: nome, rotulo: "Curva " + quando + " de " + nome,
      aoMarcar: function (pt, min) {
        if (min == null) { agoraTxt(); return; }
        campos.agora.textContent = pt && pt[1] != null ? kw(pt[1]) : "—";
        var sm = document.createElement("small"); sm.textContent = "às " + hhmm(min); campos.agora.appendChild(sm);
      } }, det.gc.clientWidth);
    desenharEntradas(i);
    desenharEntradasDoDia(i, hoje, dia);
    if (cruzEm != null) { marcarTodos(cruzEm, null, null, null); }      // a cruz fica onde estava
  }

  // as entradas de AGORA: a corrente de cada string sob o MPPT dela, e a tensão, a corrente e a potência de cada MPPT
  function celula(s, teto, mppt) {
    var nome = nomeDaString(s), corrente = s.corrente != null ? amp(s.corrente) : "sem leitura";
    var d = document.createElement("div"); d.className = "cos-inv-cel";
    // a tensão só no title e só com MPPT: a string não tem tensão própria (a do payload é cópia da do MPPT pai)
    d.title = mppt ? nome + " · " + corrente + " · tensão " + volt(mppt.tensao) + " (do " + (mppt.nome || "MPPT") + ")"
      : nome + " · " + corrente + (s.mppt != null ? " · declara o MPPT " + s.mppt + ", que o coletor não listou" : "");
    var l = document.createElement("div"); l.className = "cos-inv-cel-l";
    var n = document.createElement("span"); n.textContent = nome; l.appendChild(n);
    var v = document.createElement("span");
    // "sem corrente" em cinza, nunca em amarelo: a plataforma não sabe quais entradas têm cabo (o coletor não manda)
    if (s.corrente == null) { v.className = "sem"; v.textContent = "sem leitura"; }
    else if (s.sem_corrente) { v.className = "sem"; v.textContent = "sem corrente"; }
    else { v.textContent = amp(s.corrente); }
    l.appendChild(v); d.appendChild(l);
    d.appendChild(barra(s.corrente, teto, s.sem_corrente || s.corrente == null));
    return d;
  }
  function barra(valor, teto, apagada) {
    var b = document.createElement("span"); b.className = "cos-inv-barra"; b.setAttribute("aria-hidden", "true");
    var i = document.createElement("i");
    if (apagada) { i.className = "apagada"; }
    i.style.width = Math.max(0, Math.min(100, ((valor || 0) / (teto || 1)) * 100)).toFixed(1) + "%";
    b.appendChild(i); return b;
  }
  function desenharEntradas(i) {
    var v = vistaDasEntradas(i);
    escrever(det.entTit, "textContent", v.titulo);
    var sig = JSON.stringify([v.mppts, v.soltas]);
    if (det.entSig === sig) { return; }
    det.entSig = sig; det.ent.textContent = "";
    if (v.vazio) {
      // nem MPPT nem string nesta leitura: o Sungrow do pacote 2026.09.23, que não lê os dois (e não é a noite), ou o
      // inversor que não responde agora
      var p = document.createElement("p"); p.className = "cos-inv-ent-vazio";
      p.textContent = ehDoSunop(i) ? "O SunOP não manda MPPT nem string deste inversor nesta leitura: fica a curva dele, acima."
        : "O coletor não lê MPPT nem string deste inversor agora: fica a curva dele, acima.";
      det.ent.appendChild(p); escrever(det.nota, "textContent", ""); return;
    }
    var tetoMppt = Math.max.apply(null, [1].concat(v.mppts.map(function (m) { return m.corrente || 0; })));
    var grade = document.createElement("div"); grade.className = "cos-inv-mppts";
    v.mppts.forEach(function (m) {
      var card = document.createElement("div"); card.className = "cos-inv-mppt";
      var cab = document.createElement("div"); cab.className = "cos-inv-mppt-cab";
      var b = document.createElement("b"); b.textContent = m.nome || ("MPPT" + m.indice); cab.appendChild(b);
      var med = document.createElement("span"); med.className = "gc-num";
      // o MPPT que diz 0 A com as strings dele conduzindo: o zero não vai para a tela (diria que o MPPT morreu); vai a soma
      if (m.discorda_das_strings) {
        med.textContent = "sem leitura própria" + (m.corrente_strings != null ? " · " + amp(m.corrente_strings) + " nas strings" : "");
        card.title = "O MPPT reporta 0 A enquanto as strings dele conduzem: o que foi medido é a soma das strings.";
      } else {
        med.textContent = volt(m.tensao) + " · " + amp(m.corrente) + (m.potencia != null ? " · " + fmt2.format(m.potencia) + " kW" : "");
      }
      cab.appendChild(med); card.appendChild(cab);
      var strs = m.strings || [];
      if (strs.length) {
        var cels = document.createElement("div"); cels.className = "cos-inv-cels";
        strs.forEach(function (s) { cels.appendChild(celula(s, v.teto, m)); });
        card.appendChild(cels);
      } else if (v.temStrings) {
        var sl = document.createElement("p"); sl.className = "cos-inv-ent-vazio"; sl.textContent = "Sem leitura por string neste MPPT"; card.appendChild(sl);
      } else {
        card.appendChild(barra(m.corrente, tetoMppt, m.corrente == null || m.corrente <= 0.05));   // só o MPPT: a barra é a corrente dele
      }
      grade.appendChild(card);
    });
    if (v.soltas.length) {
      // as strings sem MPPT não ganham um MPPT de mentira: lista própria, com nome e corrente, sem linha de tensão
      var sol = document.createElement("div"); sol.className = "cos-inv-mppt" + (v.mppts.length ? " cos-inv-mppt--soltas" : " cos-inv-mppt--so-strings");
      if (v.rotuloSoltas) { var r = document.createElement("p"); r.className = v.mppts.length ? "cos-inv-mppt-cab" : "cos-inv-ent-rot"; r.textContent = v.rotuloSoltas; sol.appendChild(r); }
      var cs = document.createElement("div"); cs.className = "cos-inv-cels";
      v.soltas.forEach(function (s) { cs.appendChild(celula(s, v.teto, null)); });
      sol.appendChild(cs); grade.appendChild(sol);
    }
    det.ent.appendChild(grade);
    escrever(det.nota, "textContent", v.notaTensao ? v.notaTensao + (v.doSunop ? ""
      : " A plataforma ainda não sabe quais entradas estão sem cabo, então “sem corrente” não quer dizer defeito.") : "");
  }

  // as entradas DO DIA: Individual (um gráfico por entrada, todos na mesma escala), Por MPPT (um por MPPT, as strings dele
  // em cor, até 4) e Todas (um só, todas em linha de fundo e até 4 em destaque, escolhidas nos botões). O eixo é o do dia
  // (5h às 19h), o mesmo da curva: a cruz anda junto nos dois.
  function dicaMulti(g, min) {
    var linhas = [];
    g.lista.forEach(function (s, k) {
      var p = valorEm(s.pts, min, g.tol), v = p && p[1] != null ? p[1] : null;
      if (v == null && !s.forte && k !== g.perto) { return; }
      linhas.push({ cor: s.cor, forte: !!s.forte, perto: k === g.perto, v: v == null ? "sem leitura" : valorNa(v, g.un), t: s.nome, n: v == null ? -1 : v });
    });
    // em ordem de valor, da maior corrente para a menor (a que destoa para baixo fica no pé); a mais próxima do ponteiro
    // vem marcada, e é ela que leva o nome ao lado do ponteiro no gráfico
    linhas.sort(function (a, b) { return b.n - a.n; });
    linhas.unshift({ v: hhmm(min), t: g.nome || "" });
    if (linhas.length === 1) { linhas.push({ v: "sem amostra", t: "" }); }
    return linhas;
  }
  var SEM_ENTRADAS = { tipo: "nada", lista: [], grupos: [], porMppt: false };
  function formaDe(ent) {
    return ent.tipo + "|" + ent.lista.map(function (e) { return e.chave + "@" + (e.grupo || "-"); }).join(",");
  }
  function desenharEntradasDoDia(i, hoje, dia) {
    if (ehDoSunop(i)) {
      // 25/11/2026: a Ronda COS não grava as strings do SunOP (a `scada_entradas` é só do coletor): nada a pedir
      escrever(det.stTit, "textContent", "As strings " + (hoje ? "hoje" : "em " + diaCurto(dia)));
      escrever(det.stAviso, "textContent", "O SunOP não guarda o histórico das strings: fica a curva do inversor, acima.");
      escrever(det.stDet, "textContent", "");
      det.modos.hidden = true; det.chips.hidden = true; det.sg.textContent = ""; det.montado = "";
      return;
    }
    var id = i.id, k = chaveHist(id, dia), g = historicos[k], hist = g ? g.h : null;
    var falhou = !!(falhouHist[k] && Date.now() - falhouHist[k] < 30000);
    if ((!g || (hoje && Date.now() - g.em > CURVA_MS)) && !pedidosHist[k] && !falhou) {
      // a volta do pedido redesenha só se a pessoa ainda está no mesmo inversor e no mesmo dia (sem ler o `det`)
      var redesenhar = function () { if (invAberto === id && diaEscolhido === dia && aberta && vivo) { aoVivoNaJanela(); } };
      lerHistorico(id, dia).then(redesenhar, redesenhar);
    }
    var entVivo = entradasDoInversor(i), vivoPor = {};
    entVivo.lista.forEach(function (e) { vivoPor[e.chave] = e.valor; });
    // a forma vem do histórico do dia quando ele tem entrada (o inversor que agora não responde ainda tem as do dia);
    // sem ele, em hoje, a de agora, com a ponta desde a abertura
    var ent = hist && hist.ent.tipo !== "nada" ? hist.ent : (hoje ? entVivo : SEM_ENTRADAS);
    var quais = ent.tipo === "mppts" ? "Os MPPT" : "As strings";
    escrever(det.stTit, "textContent", quais + " " + (hoje ? "hoje" : "em " + diaCurto(dia)));
    escrever(det.stAviso, "textContent", avisoDoHistorico(hist, hoje, dia, falhou, !!(hoje && aberta && pontasDe === aberta.getAttribute("data-gid"))));
    var nada = ent.tipo === "nada";
    det.modos.hidden = nada;
    if (nada) {
      det.chips.hidden = true; det.sg.textContent = ""; det.montado = "";
      escrever(det.stDet, "textContent", "");
      return;
    }
    var chaveCache = (hoje ? versaoPontaEnt : -1) + "|" + (g ? g.em : 0) + "|" + dia;     // a ponta anda a cada leitura de 3 s
    if (det.cacheChave !== chaveCache) { det.cacheChave = chaveCache; det.cache = {}; }
    var cache = det.cache;
    var serieDe = function (chave) {
      if (cache[chave]) { return cache[chave]; }
      var base = hist && hist.series[chave] || [];
      cache[chave] = hoje ? comPontaAoVivo(base, pontaEnt(id + "|" + chave)) : base;
      return cache[chave];
    };
    var m = modoDe(ent);
    var bMppt = det.botoes.mppt;
    escrever(bMppt, "disabled", !ent.porMppt);
    // nunca um MPPT inventado: sem MPPT declarado com string (todo Huawei), não há o que agrupar
    escrever(bMppt, "title", ent.porMppt ? "" : ent.tipo === "mppts" ? "Cada série já é um MPPT" : "O coletor não informa MPPT neste inversor: não há como agrupar as strings");
    escrever(det.botoes.todas, "textContent", ent.tipo === "mppts" ? "Todos" : "Todas");
    Object.keys(det.botoes).forEach(function (b) { det.botoes[b].setAttribute("aria-pressed", String(b === m)); });
    var contar = ent.tipo === "mppts" ? ["MPPT", "MPPT"] : ["string", "strings"];
    // as que aparecem: no Todas, com uma string isolada ("Só esta"), só ela; nos outros modos, todas
    var isolada = m === "todas" ? isoladas[id] : null, vis = visiveis(ent.lista, isolada);
    // a escala comum das entradas (os cartões do Individual seguem iguais entre si), pelo que se vê no trecho do zoom:
    // sem zoom, de 0 ao teto; com zoom, o Y justo do feixe (não começa em 0)
    var eS = escalaDe(vis.map(function (e) { return serieDe(e.chave); }), 2, hoje && agoraVisivel() ? vis.map(function (e) { return vivoPor[e.chave]; }) : []);
    escrever(det.stDet, "textContent", "a corrente, gravada de 5 em 5 min (45 dias)" + (hoje ? " e a ponta ao vivo, de 3 em 3 s" : "") +
      " · " + (m === "todas" ? "" : "todos na mesma escala, ") + rotuloDaEscala(eS, "A") + " · arraste uma caixa para aproximar o horário e o valor");
    var comum = { un: "A", min: eS.min, max: eS.max, vivo: false, semAgora: !hoje, contar: contar };
    var forma = m + "|" + formaDe(ent);
    if (det.montado !== forma) {
      det.montado = forma; det.sg.textContent = ""; det.hosts = []; det.chips.textContent = ""; det.chipsPor = {};
      if (m === "individual") {
        var gi = document.createElement("div"); gi.className = "cos-inv-sg-grade";
        ent.lista.forEach(function (e) {
          var a = document.createElement("article"); a.className = "cos-inv-sgi";
          var cab = document.createElement("div"); cab.className = "cos-inv-i-cab";
          var b = document.createElement("b"); b.className = "cos-inv-sgi-nome";
          var ci = document.createElement("i"); ci.className = "cos-inv-cor"; ci.setAttribute("style", estiloDaCor(corDaEntrada(e.chave))); ci.setAttribute("aria-hidden", "true");
          b.appendChild(ci); b.appendChild(document.createTextNode(e.nome)); cab.appendChild(b);
          var vv = document.createElement("span"); vv.className = "cos-inv-i-kw"; cab.appendChild(vv);
          a.appendChild(cab);
          var host = document.createElement("div"); host.className = "cos-inv-graf"; a.appendChild(host);
          gi.appendChild(a); det.hosts.push({ host: host, e: e, valor: vv });
        });
        det.sg.appendChild(gi);
      } else if (m === "mppt") {
        var gm = document.createElement("div"); gm.className = "cos-inv-sg-mppts";
        ent.grupos.forEach(function (gr) {
          var a = document.createElement("article"); a.className = "cos-inv-sgm" + (gr.mppt ? "" : " cos-inv-sgm--soltas");
          var cab = document.createElement("div"); cab.className = "cos-inv-i-cab";
          var b = document.createElement("b"); b.textContent = gr.nome; cab.appendChild(b);
          var qt = document.createElement("span"); qt.className = "d"; qt.textContent = plural(gr.itens.length, "string", "strings"); cab.appendChild(qt);
          var hostM = document.createElement("div"); hostM.className = "cos-inv-graf";
          var btM = botaoAmpliar("mppt:" + gr.chave, hostM); cab.appendChild(btM);
          a.appendChild(cab);
          var leg = document.createElement("ul"); leg.className = "cos-inv-leg"; var valores = {};
          gr.itens.forEach(function (e) {
            var li = document.createElement("li");
            var cor = document.createElement("i"); cor.className = "cos-inv-cor"; cor.setAttribute("style", estiloDaCor(corDaEntrada(e.chave))); cor.setAttribute("aria-hidden", "true"); li.appendChild(cor);
            li.appendChild(document.createTextNode(e.nome + " "));
            var vv = document.createElement("span"); vv.className = "gc-num"; li.appendChild(vv); valores[e.chave] = vv;
            leg.appendChild(li);
          });
          a.appendChild(leg);
          a.appendChild(hostM);
          gm.appendChild(a); det.hosts.push({ host: hostM, grupo: gr, valores: valores, btAmpliar: btM });
        });
        det.sg.appendChild(gm);
      } else {
        var hostT = document.createElement("div"); hostT.className = "cos-inv-graf"; hostT.setAttribute("data-amplia", "todas");
        var todas = document.createElement("button"); todas.type = "button"; todas.className = "gc-chip cos-inv-mostrar-todas";
        todas.textContent = "Mostrar todas"; todas.hidden = true; todas.setAttribute("data-foco", "mostrar-todas");
        todas.addEventListener("click", function () { delete isoladas[invAberto]; if (aberta && vivo) { aoVivoNaJanela(); } });
        det.chips.appendChild(todas); det.btMostrarTodas = todas;
        ent.lista.forEach(function (e) {
          var b = document.createElement("button"); b.type = "button"; b.className = "gc-chip cos-inv-chip";
          b.setAttribute("data-foco", "chip:" + e.chave); b.setAttribute("aria-pressed", "false");
          var cor = document.createElement("i"); cor.className = "cos-inv-cor"; cor.setAttribute("style", estiloDaCor(corDaEntrada(e.chave))); cor.setAttribute("aria-hidden", "true"); b.appendChild(cor);
          b.appendChild(document.createTextNode(e.nome));
          b.addEventListener("click", function () { alternarDestaque(e.chave); });
          // duplo clique: "Só esta" (os dois cliques dele destacam e desfazem, e o destaque fica como estava)
          b.addEventListener("dblclick", function (ev) { ev.preventDefault(); isolarString(e.chave); });
          b.addEventListener("keydown", function (ev) { if (ev.key === "Enter" && ev.shiftKey) { ev.preventDefault(); isolarString(e.chave); } });
          // o mouse no chip realça a linha dele no gráfico (lida no desenho de agora do bloco, nunca no `det`)
          b.addEventListener("pointerenter", function () {
            var g = hostT._g;
            if (g && g.svg.isConnected && cruzEm == null) { realcar(g, g.lista.map(function (s) { return s.chave; }).indexOf(e.chave), null); }
          });
          b.addEventListener("pointerleave", function () { var g = hostT._g; if (g && g.svg.isConnected && cruzEm == null) { realcar(g, -1); } });
          det.chips.appendChild(b); det.chipsPor[e.chave] = { b: b, cor: cor };
        });
        det.sg.appendChild(hostT);
        det.hosts.push({ host: hostT, todas: true });
      }
    }
    det.chips.hidden = m !== "todas";
    det.btAmpliarTodas.hidden = m !== "todas";
    mostrarAmpliar(det.btAmpliarTodas, "todas");
    if (det.btMostrarTodas) { det.btMostrarTodas.hidden = !isolada; }
    var larguras = det.hosts.map(function (x) { return x.host.clientWidth; });  // as larguras antes de desenhar
    var sel = destaques[id] || {}, nSel = Object.keys(sel).length, chipsPor = det.chipsPor;     // os destacados (sem teto)
    // o valor ao lado do nome: o de agora em hoje; o máximo do dia num dia que passou
    var rotuloDoValor = function (no, e) {
      if (hoje) { no.textContent = vivoPor[e.chave] == null ? "sem leitura" : amp(vivoPor[e.chave]); }
      else { var mx = maximo(serieDe(e.chave)); no.textContent = mx > 0 ? amp(mx) : "—"; }
      var sm = document.createElement("small"); sm.textContent = hoje ? "agora" : "máx."; no.appendChild(sm);
    };
    det.hosts.forEach(function (x, n) {
      if (x.e) {
        var e = x.e;
        if (cruzEm == null) { rotuloDoValor(x.valor, e); }
        grafico(x.host, [{ pts: serieDe(e.chave), cor: corDaEntrada(e.chave) }], com(comum, { h: 64, escala: "individual", nome: e.nome, rotulo: "A corrente de " + e.nome + " " + (hoje ? "hoje" : "em " + diaCurto(dia)),
          aoMarcar: function (pt, min) {
            if (min == null) { rotuloDoValor(x.valor, e); return; }
            x.valor.textContent = pt && pt[1] != null ? amp(pt[1]) : "—";
            var sm = document.createElement("small"); sm.textContent = "às " + hhmm(min); x.valor.appendChild(sm);
          } }), larguras[n]);
      } else if (x.grupo) {
        x.grupo.itens.forEach(function (e) {
          escrever(x.valores[e.chave], "textContent", hoje ? (vivoPor[e.chave] == null ? "sem leitura" : amp(vivoPor[e.chave])) : "");
        });
        mostrarAmpliar(x.btAmpliar, "mppt:" + x.grupo.chave);
        grafico(x.host, x.grupo.itens.map(function (e) { return { pts: serieDe(e.chave), nome: e.nome, chave: e.chave, cor: corDaEntrada(e.chave) }; }),
          com(comum, { h: alturaDe("mppt:" + x.grupo.chave, 150), escala: "mppt:" + x.grupo.chave, eixoX: true, eixoY: true, nome: x.grupo.nome, rotulo: "As strings do " + x.grupo.nome + " " + (hoje ? "hoje" : "em " + diaCurto(dia)), dica: dicaMulti }), larguras[n]);
      } else {
        ent.lista.forEach(function (e) {
          var ch = chipsPor[e.chave], marcado = !!sel[e.chave];
          if (!ch) { return; }
          ch.b.setAttribute("aria-pressed", String(marcado));
          ch.b.classList.toggle("cos-inv-chip--oculta", !!isolada && isolada !== e.chave);     // fora do "Só esta"
          escrever(ch.b, "title", hoje ? (vivoPor[e.chave] == null ? e.nome + ": sem leitura agora" : e.nome + ": " + amp(vivoPor[e.chave]) + " agora") : e.nome);
        });
        // toda string na cor dela; com alguma destacada, ela engrossa e as outras esmaecem (sem nenhuma, todas por inteiro)
        grafico(x.host, vis.map(function (e) {
          return { pts: serieDe(e.chave), nome: e.nome, chave: e.chave, cor: corDaEntrada(e.chave), forte: !!sel[e.chave], fraca: nSel > 0 && !sel[e.chave] };
        }),
          com(comum, { h: alturaDe("todas", 240), escala: "todas", eixoX: true, eixoY: true, nome: ent.tipo === "mppts" ? "todos os MPPT" : "todas as strings",
            rotulo: quais + " " + (hoje ? "hoje" : "em " + diaCurto(dia)), dica: dicaMulti }), larguras[n]);
      }
    });
  }

  function aoVivoNaJanela() {
    if (!aberta || !vivo) { return; }
    var gid = aberta.getAttribute("data-gid"), c = mapaVivo[gid];
    if (!c) {
      aviso(aberta._sunop ? "Esta usina não veio na leitura do SunOP agora. A janela tenta de novo a cada 20 segundos."
        : "Esta usina não veio no monitoramento do SCADA agora. A janela tenta de novo a cada 3 segundos.");
      return;
    }
    // a curva DO DIA ESCOLHIDO (13/11/2026): guardada por usina e dia; trocar o dia não deixa a de outro dia na tela
    var dia = diaEscolhido, hoje = ehHoje(), guardada = curvas[chaveDaCurva(gid, dia)];
    curva = guardada ? guardada.cv : null; curvaEm = guardada ? guardada.em : 0;
    var lidoEm = horaDaLeitura(c, ehDoSunop(c) ? sunopEm : vivoEm);   // a hora da leitura, não a do pedido
    (c.inversores || []).forEach(function (i) { anotarPonta("i:" + i.id, i.pac, lidoEm); });
    // a ponta das entradas de hoje: cada leitura de 3 s, só desta usina (outra usina limpa); leitura velha não entra
    if (pontasDe !== gid) { limparPontaEnt(); pontasDe = gid; }
    if (c.fresca !== false) {
      (c.inversores || []).forEach(function (i) {
        entradasDoInversor(i).lista.forEach(function (e) { anotarPontaEnt(i.id + "|" + e.chave, e.valor, lidoEm); });
      });
    }
    // o zoom que contém agora acompanha a ponta ao vivo (em hoje); o de um trecho do passado fica parado
    if (zoom && zoom.segue) { zoom = seguirPonta(zoom, minutoDeAgora()); mostrarZoom(); }
    atualizar(c, curva);
    escrever(lido, "textContent", (ehDoSunop(c) ? "SunOP · lido às " + hhmmss(lidoEm) : "ao vivo · " + hhmmss(vivoEm)) + (!curva ? " · lendo a curva do dia…"
      : hoje ? " · curva gravada lida às " + hhmmss(curvaEm) : " · curva gravada de " + diaCurto(dia)));
    // a de hoje é relida de 5 em 5 min; a de um dia que passou não muda, e fica com a primeira leitura
    if (!curva || (hoje && Date.now() - curvaEm > CURVA_MS)) {
      lerCurva(gid, dia).then(function () { if (aberta && aberta.getAttribute("data-gid") === gid && diaEscolhido === dia) { aoVivoNaJanela(); } }, function () {});
    }
  }
  function chaveDaCurva(gid, dia) { return gid + "|" + (dia || "hoje"); }
  function guardarCurva(k, cv) {                         // as últimas CURVAS_GUARDADAS (usina e dia; a pré-busca não enche a memória)
    curvas[k] = { cv: cv, em: Date.now() };
    ordemCurvas = ordemCurvas.filter(function (g) { return g !== k; }).concat([k]);
    while (ordemCurvas.length > CURVAS_GUARDADAS) { delete curvas[ordemCurvas.shift()]; }
  }
  // a curva de uma usina num dia ("" = hoje, relida de 5 em 5 min; um dia que passou, lida uma vez)
  function lerCurva(gid, dia) {
    dia = dia || "";
    var k = chaveDaCurva(gid, dia);
    if (pedidosCurva[k]) { return pedidosCurva[k]; }
    if (falhouEm[k] && Date.now() - falhouEm[k] < 30000) { return Promise.reject({ erro: "a curva falhou há pouco; tenta de novo em 30 s" }); }
    var guardada = curvas[k];
    if (guardada && (dia || Date.now() - guardada.em < CURVA_MS)) { return Promise.resolve(guardada.cv); }
    var c = mapaVivo[gid];
    if (!c) { return Promise.reject({ erro: "o cartão desta usina não veio no monitoramento do SCADA agora" }); }
    pedidosCurva[k] = pedir("/scada/curva/" + encodeURIComponent((c.usina_ids && c.usina_ids.length ? c.usina_ids : [c.usina_id]).join(",")) + (dia ? "?dia=" + dia : ""))
      .then(function (cv) { cv = cv || SEM_CURVA; guardarCurva(k, cv); delete pedidosCurva[k]; return cv; },
            function (e) { delete pedidosCurva[k]; falhouEm[k] = Date.now(); throw e; });
    return pedidosCurva[k];
  }
  // O SELETOR DO DIA (13/11/2026, cos/_inversores.html): Hoje, Ontem e uma data até DIAS_ATRAS para trás. Vale para a
  // curva da usina, a de cada inversor e as entradas do detalhe
  function mostrarDia() {
    if (!diasEl) { return; }
    var hoje = hojeSP(), ontem = diaMenos(hoje, 1), d = diaEscolhido || hoje;
    diasEl.querySelectorAll("[data-dia]").forEach(function (b) {
      b.setAttribute("aria-pressed", String((b.getAttribute("data-dia") === "ontem" ? ontem : hoje) === d));
    });
    if (diaData) {
      diaData.min = diaMenos(hoje, DIAS_ATRAS); diaData.max = hoje;
      if (diaData.value !== d) { diaData.value = d; }
    }
  }
  function escolherDia(d) {
    var hoje = hojeSP(), limite = diaMenos(hoje, DIAS_ATRAS);
    if (!d || !/^\d{4}-\d{2}-\d{2}$/.test(d) || d >= hoje) { d = ""; }
    else if (d < limite) { d = limite; }
    if (d !== diaEscolhido) {
      diaEscolhido = d; curva = null; zoom = null; faixasY = {}; mostrarZoom();     // outro dia: o dia inteiro, o Y de sempre
      limparTodos(); graficos = [];
      if (aberta && vivo) { aoVivoNaJanela(); }
    }
    mostrarDia();
  }
  function aviso(texto) {
    if (invAberto) {                                      // a usina sumiu da leitura: o detalhe fecha e o aviso aparece
      var tinhaFoco = detEl.contains(document.activeElement);
      sairDoDetalhe();
      if (tinhaFoco) { var f = dlg.querySelector(".cos-inv-fechar"); if (f) { f.focus(); } }
    }
    var p = document.createElement("p"); p.className = "cos-inv-aviso"; p.textContent = texto;
    corpo.textContent = ""; corpo.appendChild(p); partes = null; assinatura = "";
  }
  function abrir(art) {
    sairDoDetalhe(); limparPontaEnt(); pontasDe = null; destaques = {};   // outra usina: a ponta e os destaques são dela
    diaEscolhido = ""; zoom = null; faixasY = {}; ampliado = ""; isoladas = {};   // e a janela abre em hoje, no dia inteiro
    aberta = art; curva = null; partes = null; assinatura = "";
    var gid = art.getAttribute("data-gid");
    var n = art.querySelector(".n");
    dlg.querySelector(".cos-inv-titulo").textContent = n ? n.textContent : "";
    dlg.querySelector(".cos-inv-sub").textContent = [art.getAttribute("data-cliente"), art.getAttribute("data-fonte")].filter(Boolean).join(" · ");
    lido.textContent = "";
    corpo.textContent = "";
    var lendo = document.createElement("p"); lendo.className = "mudo"; lendo.textContent = "Lendo os inversores na Ronda COS…"; corpo.appendChild(lendo);
    if (typeof dlg.showModal === "function") { if (!dlg.open) { dlg.showModal(); } } else { dlg.setAttribute("open", ""); }
    art._sunop = art.getAttribute("data-fonte") === "SunOP" || String(gid).indexOf("sunop-") === 0;
    // 25/11/2026: o SunOP tem a série gravada desde 13/11 (`SUNOP-<código>`), então o dia e o zoom valem para ele também
    if (diasEl) { diasEl.hidden = false; mostrarDia(); }
    if (zoomEl) { zoomEl.hidden = false; mostrarZoom(); }
    if (vivo && mapaVivo[gid]) { aoVivoNaJanela(); return; }
    var pedidoEm = Date.now();
    // o SunOP pelo caminho dele (`/sunop/monitoramento`, 25/11/2026); o SCADA pelo de sempre
    pedir(art._sunop ? "/sunop/monitoramento" : "/scada/monitoramento?entradas=separadas").then(function (m) {
      if (!aberta || aberta.getAttribute("data-gid") !== gid) { return; }      // a janela já mudou de usina
      if (art._sunop) { if (pedidoEm > sunopEm) { vivoSunop = m; sunopEm = Date.now(); juntarVivo(); } }
      else if (pedidoEm > vivoEm) { vivoScada = m; vivoEm = Date.now(); juntarVivo(); }
      aoVivoNaJanela();
    }).catch(function (e) {
      if (!aberta || aberta.getAttribute("data-gid") !== gid) { return; }
      if (e && e.fora) { aviso("Os inversores ao vivo precisam do endereço da API da Ronda COS (NEXUS_COS_API_URL), que este Nexus ainda não tem."); }
      else if (e && e.login && CFG.pelaPorta) { aviso("A sessão do Nexus venceu: recarregue a página e clique na usina de novo."); }
      else if (e && e.login) { aviso("Falta o login da Ronda COS neste navegador: entre uma vez no Console (no desenho final o login vem do Nexus) e clique na usina de novo."); }
      else { aviso("Não deu para ler os inversores: " + ((e && e.erro) || e) + "."); }
    });
  }
  function fechar() {
    // ⚠ A janela fecha SEMPRE (`finally`): um erro na limpeza dos gráficos não pode prender a pessoa na janela. E a
    // limpeza vem ANTES de sair do detalhe, enquanto os gráficos ainda acham o que escrever (13/11/2026).
    try {
      limparTodos();
    } finally {
      aberta = null; curva = null; partes = null; assinatura = "";
      sairDoDetalhe(); limparPontaEnt(); pontasDe = null; destaques = {};   // a ponta das entradas é da janela aberta: some ao fechar
      diaEscolhido = ""; zoom = null; faixasY = {}; ampliado = ""; isoladas = {};
      graficos = []; if (dlg.open) { dlg.close(); }
    }
  }

  if (dlg) {
    var antes = null;
    var preCarregar = function (ev) {
      var art = ev.target.closest && ev.target.closest(SELETOR);
      clearTimeout(antes);
      if (!art || !vivo) { return; }
      antes = setTimeout(function () { lerCurva(art.getAttribute("data-gid")).catch(function () {}); }, 150);
    };
    document.addEventListener("pointerover", preCarregar);
    document.addEventListener("focusin", preCarregar);
    document.addEventListener("click", function (ev) {
      if (ev.target.closest && ev.target.closest("a")) { return; }            // o link da ficha leva à ficha
      var art = ev.target.closest && ev.target.closest(SELETOR);
      if (art && !dlg.contains(art)) { abrir(art); }
    });
    document.addEventListener("keydown", function (ev) {
      var art = ev.target.closest && ev.target.closest(SELETOR);
      if (!art || ev.target !== art) { return; }                              // Enter no link da ficha é da ficha
      if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); abrir(art); }
    });
    dlg.querySelector(".cos-inv-fechar").addEventListener("click", fechar);
    dlg.addEventListener("close", fechar);
    dlg.addEventListener("click", function (ev) { if (ev.target === dlg) { fechar(); } });
    if (detEl) {
      detEl.querySelector(".cos-inv-voltar").addEventListener("click", voltarAUsina);
    }
    if (zoomEl) {
      // os controles do zoom: "−", "+", "Dia inteiro" e o trecho; no teclado, as setas deslizam (um quarto do trecho),
      // Home e End vão ao começo e ao fim do dia, "+" e "-" aproximam e afastam
      zoomEl.querySelector(".cos-inv-zoom-mais").addEventListener("click", function () { aproximarPeloBotao(0.5); });
      zoomEl.querySelector(".cos-inv-zoom-menos").addEventListener("click", function () { aproximarPeloBotao(2); });
      zoomEl.querySelector(".cos-inv-zoom-dia").addEventListener("click", function () { zerarZoom(); });
      zoomEl.addEventListener("keydown", function (ev) {
        var k = ev.key;
        if (k === "+" || k === "=") { ev.preventDefault(); aproximarPeloBotao(0.5); return; }
        if (k === "-" || k === "_") { ev.preventDefault(); aproximarPeloBotao(2); return; }
        if (!zoom || ["ArrowLeft", "ArrowRight", "Home", "End"].indexOf(k) < 0) { return; }
        ev.preventDefault();
        var w = zoom.ate - zoom.de;
        definirZoom(k === "Home" ? deslizar(zoom, DE - zoom.de) : k === "End" ? deslizar(zoom, ATE - zoom.ate)
          : deslizar(zoom, (k === "ArrowLeft" ? -1 : 1) * w / 4));
      });
    }
    if (diasEl) {
      diasEl.querySelectorAll("[data-dia]").forEach(function (b) {
        b.addEventListener("click", function () { escolherDia(b.getAttribute("data-dia") === "ontem" ? diaMenos(hojeSP(), 1) : ""); });
      });
      if (diaData) { diaData.addEventListener("change", function () { escolherDia(diaData.value); }); }
    }
    if (detEl) {
      // O Esc no detalhe volta à usina; o segundo Esc fecha a janela. Pelo `cancel` do <dialog> (o pedido de fechar), e
      // não pelo keydown: a 1ª versão cancelava o keydown e guardava uma marca desligada por setTimeout 0, e na prova no
      // Edge (13/11/2026) o segundo Esc, logo depois do primeiro, chegou antes do temporizador (o navegador põe a tecla na
      // frente) e a janela não fechou mais. O Chromium só deixa cancelar o fechamento com um clique ou uma tecla desde a
      // última vez, e o detalhe sempre abre por um dos dois.
      dlg.addEventListener("cancel", function (ev) {
        if (!invAberto) { return; }
        ev.preventDefault();
        voltarAUsina();
      });
    }
    var redim = null;
    window.addEventListener("resize", function () { clearTimeout(redim); redim = setTimeout(function () { if (aberta && vivo) { partes = null; assinatura = ""; aoVivoNaJanela(); } }, 150); });
    abrirPeloLink();
  }
  lerVivo();
  lerSunop();

  // ── O LINK QUE ABRE UMA USINA (13/11/2026) ──────────────────────────────────────────────────────────────────────
  // O "Ver" do aviso de falha do Console embutido traz `?usina=<id do cartão>` (o mesmo `data-gid`): a janela daquela
  // usina abre sozinha. O parâmetro sai do endereço logo depois, para recarregar a página não reabrir a janela.
  function usinaDoLink(busca) {
    var m = /(?:^|[?&])usina=([^&#]*)/.exec(busca || "");
    var id = m ? decodeURIComponent(m[1].replace(/\+/g, " ")) : "";
    return /^(scada|sunop)-[A-Za-z0-9_-]{1,80}$/.test(id) ? id : null;
  }
  function abrirPeloLink() {
    var id = usinaDoLink(raiz.location && raiz.location.search);
    if (!id) { return; }
    try {
      var url = new URL(raiz.location.href); url.searchParams.delete("usina");
      raiz.history.replaceState(raiz.history.state, "", url.pathname + url.search + url.hash);
    } catch (e) { /* sem history: a janela abre do mesmo jeito */ }
    var arts = document.querySelectorAll(SELETOR), art = null;
    for (var k = 0; k < arts.length; k++) { if (arts[k].getAttribute("data-gid") === id && !dlg.contains(arts[k])) { art = arts[k]; break; } }
    if (!art) { return; }                                   // a usina não está nesta tela (outro filtro ou fonte)
    if (art.scrollIntoView) { art.scrollIntoView({ block: "center" }); }
    abrir(art);
  }
})(typeof window !== "undefined" ? window : globalThis);
