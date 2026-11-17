// A recoleta pelas fontes na tela 1 do Conversor (Nexus, 17/11/2026). Arquivo DO NEXUS (não é gerado do .exe).
//
// Levi: "quero formas de coletar os dados novamente pelas nossas fontes de dados e gerar uma planilha para colar nos
// BDs... insere no NEXUS > PERFORMANCE > COLETAS". O .exe 1.0.14 tem o painel "Recoletar pela API PV" (uma fonte só);
// aqui o mesmo painel ganha o seletor de Fonte (banco da Thopen, SCADA Grid Co., API PV nas duas contas, SolarEdge,
// SunOp e chuva) e a chave Chuva, mostra o custo ANTES de buscar e manda o resultado para a tela 2 de sempre.
// Só carrega para quem pode recoletar (o setor Performance; coletas_tela._pode_recoletar). A regra de cada fonte e os
// tetos moram na plataforma; a conta do lado do Nexus, em nexus/performance/coletas/recoleta_fontes.py.
(function () {
  "use strict";
  const q = s => document.querySelector(s);
  const box = q("#rc"), abrir = q("#rcAbrir");
  if (!box || !abrir || typeof nxPost !== "function") return;
  const E = {fontes: [], fonte: "", us: [], info: null, relogio: null, vez: 0, ocupado: false};
  const texto = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

  abrir.textContent = "Recoletar pela fonte";
  box.querySelector("h4").innerHTML = 'Recoletar pela fonte <span>a plataforma busca direto na fonte da usina; o resultado ' +
    'abre como uma conversão: amarelo = valor novo, o resto já bate com o BD</span>';
  box.querySelector(".rc-campos").insertAdjacentHTML("afterbegin",
    '<label class="fz-l rc-f">Fonte<select id="rcFonte" class="fz-ctl" aria-label="Fonte da recoleta"></select></label>');
  q("#rcEtm").closest("label").insertAdjacentHTML("afterend",
    '<label class="fz-sw"><input type="checkbox" id="rcChuva"><span></span>Chuva</label>');

  const st = (t, erro) => { q("#rcSt").textContent = t || ""; q("#rcSt").classList.toggle("er", !!erro); };
  const iso = d => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  const ddmm = s => s.slice(8, 10) + "/" + s.slice(5, 7);
  const usina = () => E.us.find(x => x.usina === q("#rcUsina").value);
  const dias = () => { const a = q("#rcIni").value, b = q("#rcFim").value; return a && b && b >= a ? Math.round((new Date(b) - new Date(a)) / 864e5) + 1 : 0; };
  const oQue = () => [q("#rcGer").checked, q("#rcEtm").checked, q("#rcChuva").checked];
  const nomeDaFonte = () => (E.fontes.find(f => f.id === E.fonte) || {}).nome || E.fonte;
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
    st(u.destino + " · " + u.plantas + " planta(s) · " + dias() + " dia(s) · " + custo);
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
    if (!n || !(g || e || c)) { st(u.destino + " · " + u.plantas + " planta(s): escolha o período e o que recoletar"); return; }
    st(u.destino + " · " + u.plantas + " planta(s) · " + n + " dia(s) · conferindo o custo…");
    const vez = E.vez; E.relogio = setTimeout(() => simular(vez), 450);
  }

  async function trocarFonte() {
    E.fonte = q("#rcFonte").value; E.us = []; E.info = null;
    q("#rcLista").innerHTML = ""; q("#rcUsina").value = ""; q("#rcUsina").placeholder = "carregando…";
    const soChuva = E.fonte === "chuva";                         // a fonte "chuva" é só a chuva (a mesma consulta meteo)
    q("#rcGer").disabled = q("#rcEtm").disabled = soChuva;
    if (soChuva) { q("#rcGer").checked = q("#rcEtm").checked = false; q("#rcChuva").checked = true; }
    st("Buscando as usinas de " + nomeDaFonte() + "…"); validar();
    const pedida = E.fonte, r = await chama("fontes_plantas", [pedida]);
    if (pedida !== E.fonte) return;
    if (!r || r.erro) { st((r && r.erro) || "sem resposta", true); q("#rcUsina").placeholder = "indisponível"; return; }
    E.info = r; E.us = r.usinas || [];
    q("#rcLista").innerHTML = E.us.map(x => '<option value="' + texto(x.usina) + '">' + texto(x.destino.replace("BD_", "")) +
      " · " + x.plantas + " planta(s)</option>").join("");
    q("#rcUsina").placeholder = E.us.length ? "digite para buscar a usina" : "nenhuma usina com aba no BD";
    validar();
  }

  async function abrirPainel() {
    box.hidden = !box.hidden; if (box.hidden) return;
    const ontem = new Date(); ontem.setDate(ontem.getDate() - 1);
    ["#rcIni", "#rcFim"].forEach(i => { q(i).max = iso(ontem); if (!q(i).value) q(i).value = iso(ontem); });
    if (E.fontes.length) { validar(); return; }
    st("Buscando as fontes…");
    const r = await chama("fontes_lista", []);
    if (!r || r.erro || !r.length) { st((r && r.erro) || "sem resposta", true); return; }
    E.fontes = r;
    q("#rcFonte").innerHTML = r.map(f => '<option value="' + texto(f.id) + '">' + texto(f.nome) + "</option>").join("");
    trocarFonte();
  }

  async function ir() {
    const u = usina(); if (!u || E.ocupado) return;
    const [g, e, c] = oQue();
    E.ocupado = true; clearTimeout(E.relogio); E.vez++; q("#rcIr").disabled = true;
    const fim = (t, erro) => { E.ocupado = false; if (t) st(t, erro); else validar(); q("#rcIr").disabled = !usina(); };
    const pl = await chama("fontes_plano", [E.fonte, u.usina, q("#rcIni").value, q("#rcFim").value, g, e, c]);
    if (!pl || pl.erro) return fim((pl && pl.erro) || "sem resposta", true);
    const ps = pl.pedidos || [];
    for (let i = 0; i < ps.length; i++) {
      st("Recoletando " + u.usina + ": " + ddmm(ps[i][0]) + " a " + ddmm(ps[i][1]) + (ps.length > 1 ? " (" + (i + 1) + " de " + ps.length + ")" : "") + "…");
      const r = await chama("fontes_parte", [i]);
      if (!r || r.erro) return fim((r && r.erro) || "sem resposta", true);
      if (E.info && r.cota_restante != null) E.info.cota_restante = r.cota_restante;
    }
    st("Comparando com o BD…");
    const res = await chama("fontes_montar", []);
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
  q("#rcIr").onclick = ir;
  q("#rcFonte").onchange = trocarFonte;
  ["#rcUsina", "#rcIni", "#rcFim", "#rcGer", "#rcEtm", "#rcChuva"].forEach(i => { q(i).oninput = validar; q(i).onchange = validar; });
})();
