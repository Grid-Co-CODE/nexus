// A recoleta pelas fontes na tela 1 do Conversor (Nexus, 17/11/2026). Arquivo DO NEXUS (não é gerado do .exe).
//
// Levi: "quero formas de coletar os dados novamente pelas nossas fontes de dados e gerar uma planilha para colar nos
// BDs... insere no NEXUS > PERFORMANCE > COLETAS". O .exe 1.0.14 tem o painel "Recoletar pela API PV" (uma fonte só);
// aqui o mesmo painel ganha a Fonte (banco da Thopen, SCADA Grid Co., API PV nas duas contas, SolarEdge, SunOp e chuva)
// e a chave Chuva, mostra o custo ANTES de buscar e manda o resultado para a tela 2 de sempre.
// A Fonte e a Usina são a LISTA DIGITÁVEL do Nexus (as zf-* do Histórico de OS, static/zeladoria/filtros.css; Levi,
// 18/11/2026, sobre a caixa nativa do navegador: "essa lista de usinas também tá escrota, quero ao estilo nexus!").
// Só carrega para quem pode recoletar (o setor Performance; coletas_tela._pode_recoletar). A regra de cada fonte e os
// tetos moram na plataforma; a conta do lado do Nexus, em nexus/performance/coletas/recoleta_fontes.py.
(function () {
  "use strict";
  const q = s => document.querySelector(s);
  const box = q("#rc"), abrir = q("#rcAbrir");
  if (!box || !abrir || typeof nxPost !== "function") return;
  const E = {fontes: [], fonte: "", us: [], usina: "", info: null, relogio: null, vez: 0, ocupado: false};
  const texto = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const SETA = '<svg class="zf-ico zf-seta" viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg>';
  const semAcento = s => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  // ── a lista digitável do Nexus, de UMA escolha: o botão com o escolhido, a busca e as opções ─────────────────────
  function lista(rotulo, vazio, aoEscolher) {
    const el = document.createElement("div");
    el.className = "fz-l rc-lista";
    el.innerHTML = texto(rotulo) + '<div class="zf-lista"><button type="button" class="zf-lista-cab" aria-haspopup="listbox" ' +
      'aria-expanded="false"><span></span>' + SETA + '</button><div class="zf-lista-corpo" hidden>' +
      '<input type="text" class="zf-lista-busca" placeholder="Digite para filtrar" aria-label="Filtrar ' + texto(rotulo) + '">' +
      '<div class="zf-ops" role="listbox" aria-label="' + texto(rotulo) + '"></div><p class="zf-vazio" hidden>Nada com esse texto.</p></div></div>';
    const caixa = el.querySelector(".zf-lista"), cab = el.querySelector(".zf-lista-cab"), corpo = el.querySelector(".zf-lista-corpo");
    const busca = el.querySelector(".zf-lista-busca"), ops = el.querySelector(".zf-ops"), nada = el.querySelector(".zf-vazio");
    let itens = [], valor = "", aviso = vazio, foco = -1;
    const visiveis = () => [].filter.call(ops.children, o => !o.hidden);
    const pintar = () => {
      const it = itens.find(x => x.v === valor);
      cab.querySelector("span").textContent = it ? it.t : aviso;
      caixa.classList.toggle("zf-tem", !!it);
      [].forEach.call(ops.children, o => { const s = o.dataset.v === valor; o.classList.toggle("zf-sel", s); o.setAttribute("aria-selected", s); });
    };
    const focar = i => { const v = visiveis(); foco = v.length ? (i + v.length) % v.length : -1;
      [].forEach.call(ops.children, o => o.classList.remove("zf-foco")); if (foco >= 0) { v[foco].classList.add("zf-foco"); v[foco].scrollIntoView({block: "nearest"}); } };
    const filtrar = () => { const b = semAcento(busca.value); let n = 0;
      [].forEach.call(ops.children, o => { o.hidden = !!b && semAcento(o.dataset.b).indexOf(b) < 0; if (!o.hidden) n++; });
      nada.hidden = n > 0 || !itens.length; focar(0); };
    const fechar = () => { corpo.hidden = true; cab.setAttribute("aria-expanded", "false"); };
    const abrirLista = () => { document.querySelectorAll(".rc-lista .zf-lista-corpo").forEach(c => { if (c !== corpo) { c.hidden = true; c.previousElementSibling.setAttribute("aria-expanded", "false"); } });
      corpo.hidden = false; cab.setAttribute("aria-expanded", "true"); busca.value = ""; filtrar(); busca.focus(); };
    const escolher = (v, avisar) => { valor = v; pintar(); fechar(); if (avisar !== false) { cab.focus(); aoEscolher(v); } };
    cab.onclick = () => { if (cab.disabled) return; corpo.hidden ? abrirLista() : fechar(); };
    busca.oninput = filtrar;
    corpo.onkeydown = e => {
      if (e.key === "ArrowDown") { e.preventDefault(); focar(foco + 1); }
      else if (e.key === "ArrowUp") { e.preventDefault(); focar(foco - 1); }
      else if (e.key === "Enter") { e.preventDefault(); const v = visiveis(); if (foco >= 0 && v[foco]) escolher(v[foco].dataset.v); }
      else if (e.key === "Escape") { e.preventDefault(); fechar(); cab.focus(); }
    };
    ops.onclick = e => { const o = e.target.closest(".zf-op"); if (o) escolher(o.dataset.v); };
    document.addEventListener("mousedown", e => { if (!corpo.hidden && !el.contains(e.target)) fechar(); });
    pintar();
    return {el, valor: () => valor, escolher,
      desligar(d) { cab.disabled = !!d; },
      // opcoes: [{v, t, sub}]; `aviso` é o que o botão diz enquanto nada foi escolhido
      definir(opcoes, novoAviso) {
        itens = opcoes || []; aviso = novoAviso || vazio; if (!itens.some(x => x.v === valor)) valor = "";
        ops.innerHTML = itens.map(x => '<button type="button" class="zf-op" role="option" data-v="' + texto(x.v) + '" data-b="' +
          texto(x.t + " " + (x.sub || "")) + '">' + (x.sub ? '<span class="rc-sub">' + texto(x.sub) + "</span>" : "") + texto(x.t) + "</button>").join("");
        pintar();
      }};
  }

  abrir.textContent = "Recoletar pela fonte";
  box.querySelector("h4").innerHTML = 'Recoletar pela fonte <span>a plataforma busca direto na fonte da usina; o resultado ' +
    'abre como uma conversão: amarelo = valor novo, o resto já bate com o BD</span>';
  const campos = box.querySelector(".rc-campos");
  const LF = lista("Fonte", "escolha a fonte", trocarFonte), LU = lista("Usina", "carregando…", () => { E.usina = LU.valor(); validar(); });
  LU.el.classList.add("rc-u");
  q("#rcUsina").closest("label").hidden = true;                  // a caixa nativa do .exe sai: vale a lista do Nexus
  campos.insertBefore(LU.el, campos.firstChild); campos.insertBefore(LF.el, LU.el);
  q("#rcEtm").closest("label").insertAdjacentHTML("afterend",
    '<label class="fz-sw"><input type="checkbox" id="rcChuva"><span></span>Chuva</label>');

  const st = (t, erro) => { q("#rcSt").textContent = t || ""; q("#rcSt").classList.toggle("er", !!erro); };
  const iso = d => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  const ddmm = s => s.slice(8, 10) + "/" + s.slice(5, 7);
  const usina = () => E.us.find(x => x.usina === E.usina);
  const dias = () => { const a = q("#rcIni").value, b = q("#rcFim").value; return a && b && b >= a ? Math.round((new Date(b) - new Date(a)) / 864e5) + 1 : 0; };
  const oQue = () => [q("#rcGer").checked, q("#rcEtm").checked, q("#rcChuva").checked];
  const nomeDaFonte = () => (E.fontes.find(f => f.id === E.fonte) || {}).nome || E.fonte;
  const plantas = n => n + (n === 1 ? " planta" : " plantas");
  const cota = i => !i || !i.paga ? "sem custo de cota" :
    (i.cota_restante != null ? "restam " + i.cota_restante + (i.teto ? " de " + i.teto : "") + " consultas hoje" : "fonte com cota");

  async function chama(metodo, args) {
    try { return await nxPost(metodo, args); } catch (e) { return {erro: (e && e.message) || "sem resposta do Nexus"}; }
  }

  async function simular(vez) {
    const u = usina(), [g, e, c] = oQue();
    if (!u || !dias() || E.ocupado) return;
    const r = await chama("fontes_simular", [E.fonte, u.usina, q("#rcIni").value, q("#rcFim").value, g, e, c]);
    if (vez !== E.vez || E.ocupado) return;                      // a pessoa mudou algo enquanto a conta vinha
    if (!r || r.erro) { st((r && r.erro) || "sem resposta", true); return; }
    const custo = r.consultas ? "custa " + r.consultas + " consulta(s)" + (r.cota_restante != null ? " (restam " + r.cota_restante +
      (r.teto ? " de " + r.teto : "") + " hoje)" : "") : "sem custo de cota";
    st(u.destino + " · " + plantas(u.plantas) + " · " + dias() + " dia(s) · " + custo);
  }

  function validar() {
    const u = usina(), n = dias(), [g, e, c] = oQue();
    q("#rcIr").disabled = E.ocupado || !(u && n && (g || e || c));
    clearTimeout(E.relogio); E.vez++;
    if (!E.info || E.ocupado) return;
    if (!u) {
      let t = E.us.length + " usina(s) em " + nomeDaFonte() + " · " + cota(E.info);
      if ((E.info.sem_bd || []).length) t += " · " + E.info.sem_bd.join(" e ") + " não foi lido: as usinas dele ficaram de fora";
      else if ((E.info.sem_aba || []).length) t += " · " + E.info.sem_aba.length + " sem aba no BD ficaram de fora";
      st(t); return;
    }
    if (!n || !(g || e || c)) { st(u.destino + " · " + plantas(u.plantas) + ": escolha o período e o que recoletar"); return; }
    st(u.destino + " · " + plantas(u.plantas) + " · " + n + " dia(s) · conferindo o custo…");
    const vez = E.vez; E.relogio = setTimeout(() => simular(vez), 450);
  }

  async function trocarFonte() {
    E.fonte = LF.valor(); E.us = []; E.usina = ""; E.info = null;
    LU.definir([], "carregando…"); LU.desligar(true);
    const soChuva = E.fonte === "chuva";                         // a fonte "chuva" é só a chuva (a mesma consulta meteo)
    q("#rcGer").disabled = q("#rcEtm").disabled = soChuva;
    if (soChuva) { q("#rcGer").checked = q("#rcEtm").checked = false; q("#rcChuva").checked = true; }
    st("Buscando as usinas de " + nomeDaFonte() + "…"); validar();
    const pedida = E.fonte, r = await chama("fontes_plantas", [pedida]);
    if (pedida !== E.fonte) return;
    if (!r || r.erro) { st((r && r.erro) || "sem resposta", true); LU.definir([], "indisponível"); return; }
    E.info = r; E.us = r.usinas || [];
    LU.definir(E.us.map(x => ({v: x.usina, t: x.usina, sub: x.destino.replace("BD_", "") + " · " + plantas(x.plantas)})),
      E.us.length ? "escolha a usina" : "nenhuma usina com aba no BD");
    LU.desligar(!E.us.length);
    validar();
  }

  async function abrirPainel() {
    box.hidden = !box.hidden; if (box.hidden) return;
    const ontem = new Date(); ontem.setDate(ontem.getDate() - 1);
    ["#rcIni", "#rcFim"].forEach(i => { q(i).max = iso(ontem); if (!q(i).value) q(i).value = iso(ontem); });
    if (E.fontes.length) { validar(); return; }
    st("Buscando as fontes…"); LU.desligar(true);
    const r = await chama("fontes_lista", []);
    if (!r || r.erro || !r.length) { st((r && r.erro) || "sem resposta", true); return; }
    E.fontes = r;
    LF.definir(r.map(f => ({v: f.id, t: f.nome})));
    LF.escolher(r[0].id);                                        // a 1ª é a que não gasta cota (banco da Thopen)
  }

  // O Nexus reinicia a cada publicação e a busca em andamento mora na memória dele: se uma parte volta com `refazer`,
  // a busca recomeça sozinha, UMA vez (18/11/2026, Levi: "a lista fica vencendo ainda, resolva!")
  async function ir(denovo) {
    const u = usina(); if (!u || (E.ocupado && denovo !== true)) return;
    const [g, e, c] = oQue();
    E.ocupado = true; clearTimeout(E.relogio); E.vez++; q("#rcIr").disabled = true;
    const fim = (t, erro) => { E.ocupado = false; if (t) st(t, erro); else validar(); q("#rcIr").disabled = !usina(); };
    const pl = await chama("fontes_plano", [E.fonte, u.usina, q("#rcIni").value, q("#rcFim").value, g, e, c]);
    if (!pl || pl.erro) return fim((pl && pl.erro) || "sem resposta", true);
    const ps = pl.pedidos || [];
    for (let i = 0; i < ps.length; i++) {
      st("Recoletando " + u.usina + ": " + ddmm(ps[i][0]) + " a " + ddmm(ps[i][1]) + (ps.length > 1 ? " (" + (i + 1) + " de " + ps.length + ")" : "") + "…");
      const r = await chama("fontes_parte", [i]);
      if (r && r.refazer && denovo !== true) { st("O Nexus reiniciou: recomeçando a busca…"); return ir(true); }
      if (!r || r.erro) return fim((r && r.erro) || "sem resposta", true);
      if (E.info && r.cota_restante != null) E.info.cota_restante = r.cota_restante;
    }
    st("Comparando com o BD…");
    const res = await chama("fontes_montar", []);
    if (res && res.refazer && denovo !== true) { st("O Nexus reiniciou: recomeçando a busca…"); return ir(true); }
    if (!res || res.erro) return fim((res && res.erro) || "sem resposta", true);
    app.res = res;
    $("#status").textContent = "Recoleta de " + u.usina + " (" + nomeDaFonte() + ") pronta às " + res.hora;
    $("#pasta-saida").textContent = res.pasta || "";
    $("#aba2").disabled = false;
    app.resultado(); app.tela(2);
    // a tela 2 do .exe diz "valores vindos da API PV" (lá só há essa fonte): aqui vale a fonte que a pessoa escolheu
    const andar = document.createTreeWalker(q("#kpis") || box, NodeFilter.SHOW_TEXT);
    for (let n = andar.nextNode(); n; n = andar.nextNode()) {
      if (n.nodeValue.indexOf("vindos da API PV") >= 0) n.nodeValue = n.nodeValue.replace("vindos da API PV", "vindos de " + nomeDaFonte());
    }
    fim();
  }

  abrir.onclick = abrirPainel;
  q("#rcIr").onclick = () => ir();
  ["#rcIni", "#rcFim", "#rcGer", "#rcEtm", "#rcChuva"].forEach(i => { q(i).oninput = validar; q(i).onchange = validar; });
})();
