/* A ponte da zeladoria (nexus/static/zeladoria/ponte.js) no node, com um fetch de mentira que anota cada pedido.

   Prova que o clone do Radar recebe do `window.supabase.createClient()` o que recebia do supabase-js v2: o construtor
   que se encadeia e se resolve com {data, error, count, status, statusText} (como o PostgrestBuilder), a gravação
   recusada enquanto a torre é só leitura, o login vindo do Nexus e a função das fotos. Nunca lança: o supabase-js
   devolve o erro no `error`, e o Radar confia nisso.

   Uso: node tests/zeladoria_ponte_node.js nexus/static/zeladoria/ponte.js  (sai com 1 e a mensagem se algo falhar) */
"use strict";
const fs = require("fs");
const vm = require("vm");
const assert = require("assert");
// o objeto criado dentro do vm tem outro protótipo: a comparação é pelo JSON
const igual = (a, b) => assert.deepStrictEqual(JSON.parse(JSON.stringify(a)), JSON.parse(JSON.stringify(b)));

const codigo = fs.readFileSync(process.argv[2], "utf8");

function montar(respostas, extra) {
  const pedidos = [];
  const avisos = [];
  const window = {
    ZELADORIA: Object.assign({ api: "/raiz/t/zeladoria/api", somenteLeitura: true, sair: "/raiz/sair" }, extra || {}),
    showToast: (t) => avisos.push(t),
    top: { location: { href: "", recarregou: 0, reload() { this.recarregou += 1; } } },
    fetch: (url, opcoes) => {
      pedidos.push({ url: decodeURIComponent(url), opcoes: opcoes || {} });
      const r = respostas(url, opcoes || {});
      if (r instanceof Error) return Promise.reject(r);
      return Promise.resolve({ ok: r.status < 400, status: r.status, statusText: r.statusText || "",
                               redirected: !!r.redirecionou,
                               headers: { get: (h) => (h.toLowerCase() === "content-type" ? (r.tipo || "application/json") : null) },
                               json: () => (r.tipo && r.tipo !== "application/json" ? Promise.reject(new Error("não é JSON"))
                                                                                    : Promise.resolve(r.corpo)) });
    },
  };
  vm.runInNewContext(codigo, { window, Promise, JSON, encodeURIComponent, setTimeout, console });
  return { sb: window.supabase.createClient(), pedidos, window, avisos };
}

const testes = {
  async "select com eq e order vira um pedido só e resolve como o supabase-js"() {
    const { sb, pedidos } = montar(() => ({ status: 200, corpo: [{ folio: 1 }] }));
    const r = await sb.from("rf_fracttal_rondas").select("folio,data").eq("usina_chave", "X")
      .order("data", { ascending: false });
    igual(r, { data: [{ folio: 1 }], error: null, count: null, status: 200, statusText: "" });
    assert.strictEqual(pedidos.length, 1);
    assert.strictEqual(pedidos[0].url, '/raiz/t/zeladoria/api/rf/rf_fracttal_rondas?eq=usina_chave:"X"&order=data:desc');
  },
  async "neq e o construtor dentro de Promise.resolve"() {
    const { sb, pedidos } = montar(() => ({ status: 200, corpo: [] }));
    const r = await Promise.resolve(sb.from("rf_log").select("*").neq("id", -1).order("id", { ascending: true }));
    igual(r.data, []);
    assert.strictEqual(pedidos[0].url, "/raiz/t/zeladoria/api/rf/rf_log?neq=id:-1&order=id:asc");
  },
  async "gravar é recusado enquanto a torre é só leitura, sem ir ao servidor"() {
    const { sb, pedidos } = montar(() => ({ status: 500, corpo: {} }));
    for (const q of [sb.from("rf_cotacoes").upsert([{ id: "C1" }], { onConflict: "id" }),
                     sb.from("rf_cotacoes").insert({ id: "C2" }),
                     sb.from("rf_fin_cenario").update({ nome: "x" }).eq("id", "F1"),
                     sb.from("rf_historico_valor").delete().neq("id", -1),
                     sb.rpc("fin_promover", { p_cenario_id: "F1" })]) {
      const r = await q;
      assert.strictEqual(r.data, null);
      assert.strictEqual(r.error.code, "SOMENTE_LEITURA");
      assert.match(r.error.message, /edite no Radar/);
    }
    assert.strictEqual(pedidos.length, 0);
  },
  async "o retrato do cronograma (derivado) é aceito em silêncio"() {
    const { sb, pedidos } = montar(() => ({ status: 500, corpo: {} }));
    const r = await sb.from("rf_cronograma_publico").upsert({ id: "cronograma" }, { onConflict: "id" });
    igual([r.data, r.error], [null, null]);
    assert.strictEqual(pedidos.length, 0);
  },
  async "o login vem do Nexus"() {
    const { sb, pedidos, window } = montar(() => ({ status: 200, corpo: { user: { id: "u1", email: "fulano@exemplo.com" } } }));
    const evento = await new Promise((ok) => {
      const s = sb.auth.onAuthStateChange((ev, sessao) => ok([ev, sessao]));
      assert.strictEqual(typeof s.data.subscription.unsubscribe, "function");
    });
    igual(evento, ["INITIAL_SESSION", { user: { id: "u1", email: "fulano@exemplo.com" } }]);
    assert.strictEqual(pedidos[0].url, "/raiz/t/zeladoria/api/eu");
    const senha = await sb.auth.signInWithPassword({ email: "a", password: "b" });
    assert.match(senha.error.message, /login é o do Nexus/);
    await sb.auth.signOut();
    assert.strictEqual(window.top.location.href, "/raiz/sair");
  },
  async "as fotos da ronda vão à função da torre"() {
    const { sb, pedidos } = montar(() => ({ status: 200, corpo: { folio: "123", fotos: [], checklist: [] } }));
    const r = await sb.functions.invoke("fracttal-fotos", { body: { folio: "123" } });
    igual(r, { data: { folio: "123", fotos: [], checklist: [] }, error: null });
    assert.strictEqual(pedidos[0].url, "/raiz/t/zeladoria/api/funcao/fracttal-fotos");
    assert.strictEqual(pedidos[0].opcoes.method, "POST");
    igual(JSON.parse(pedidos[0].opcoes.body), { folio: "123" });
  },
  async "o PDF do contrato vem do Nexus; as fotos das rondas, do Fracttal"() {
    const { sb, pedidos } = montar((url) => (url.includes("/contrato-pdf")
      ? { status: 200, corpo: { signedUrl: "/raiz/t/zeladoria/contrato/cliente/a.pdf" } } : { status: 500, corpo: {} }));
    const r = await sb.storage.from("contratos-zeladoria").createSignedUrl("cliente/a.pdf", 600);
    igual(r, { data: { signedUrl: "/raiz/t/zeladoria/contrato/cliente/a.pdf" }, error: null });
    assert.strictEqual(pedidos[0].url, "/raiz/t/zeladoria/api/contrato-pdf?caminho=cliente/a.pdf");
    // o arquivo das fotos das rondas volta vazio, sem ir ao servidor: o Radar oferece buscar no Fracttal
    const f = await sb.storage.from("rondas-fotos").createSignedUrls(["x.jpg"], 3600);
    igual(f, { data: [], error: null });
    assert.strictEqual(pedidos.length, 1);
  },
  async "o PDF que ainda não veio diz isso"() {
    const { sb } = montar(() => ({ status: 404, corpo: { erro: "O PDF deste contrato ainda não foi trazido do Supabase para o Nexus." } }));
    const r = await sb.storage.from("contratos-zeladoria").createSignedUrl("cliente/b.pdf", 600);
    igual([r.data, r.error.message], [null, "O PDF deste contrato ainda não foi trazido do Supabase para o Nexus."]);
  },
  async "rede fora do ar vira erro, nunca exceção"() {
    const { sb } = montar(() => new Error("rede"));
    const r = await sb.from("rf_usinas").select("*");
    assert.strictEqual(r.data, null);
    assert.ok(r.error && r.error.message);
    const f = await sb.functions.invoke("fracttal-fotos", { body: {} });
    assert.ok(f.error && f.error.message);
  },
  async "sessão do Nexus que acabou vira erro SESSAO, nunca um Radar vazio"() {
    // o portão do Nexus manda o pedido sem sessão para o login: o fetch segue e recebe a página HTML com 200
    const { sb } = montar(() => ({ status: 200, redirecionou: true, tipo: "text/html", corpo: null }));
    const r = await sb.from("rf_usinas").select("*");
    assert.strictEqual(r.data, null);
    assert.strictEqual(r.error.code, "SESSAO");
  },
  async "o /eu sem sessão recarrega a página do Nexus, que leva ao login"() {
    const { sb, window } = montar(() => ({ status: 200, redirecionou: true, tipo: "text/html", corpo: null }));
    let chamou = false;
    sb.auth.onAuthStateChange(() => { chamou = true; });
    await new Promise((ok) => setTimeout(ok, 20));
    assert.strictEqual(window.top.location.recarregou, 1);
    assert.strictEqual(chamou, false);           // a tela de senha do Radar nunca aparece
  },
  async "o erro do servidor chega no error com a mensagem dele"() {
    const { sb } = montar(() => ({ status: 403, statusText: "FORBIDDEN", corpo: { erro: "Sem permissão." } }));
    const r = await sb.from("rf_usinas").select("*");
    igual([r.data, r.error.message, r.status], [null, "Sem permissão.", 403]);
  },

  // ── o modo de gravação (etapa 4: o servidor com NEXUS_ZELADORIA_GRAVA=1) ──
  async "gravando, o upsert do estado inteiro manda só as colunas que mudaram"() {
    const { sb, pedidos } = montar((url, o) => (o.method === "POST"
      ? { status: 200, corpo: { versao: 4, outros_salvaram: false, sobrepostas: [], ids: [[]], situacao: { erro: null } } }
      : { status: 200, corpo: [{ id: "C1", valor: 100, obs: "a" }, { id: "C2", valor: 200, obs: "b" }] }),
      { somenteLeitura: false });
    await sb.from("rf_cotacoes").select("*");
    // o syncTudo do Radar manda tudo; só a C2 mudou, e só o valor
    const r = await sb.from("rf_cotacoes").upsert([{ id: "C1", valor: "100", obs: "a" }, { id: "C2", valor: 250, obs: "b" }],
                                                  { onConflict: "id" });
    igual([r.data, r.error, r.status], [null, null, 201]);
    igual(JSON.parse(pedidos[1].opcoes.body), { ops: [{ op: "upsert", view: "rf_cotacoes", linhas: [{ valor: 250, id: "C2" }] }], versao: 0 });
    assert.strictEqual(pedidos[1].url, "/raiz/t/zeladoria/api/gravar");
    // de novo, igual: nada vai ao servidor
    await sb.from("rf_cotacoes").upsert([{ id: "C1", valor: 100, obs: "a" }, { id: "C2", valor: 250, obs: "b" }]);
    assert.strictEqual(pedidos.length, 2);
  },
  async "gravando, a mudança DENTRO do JSON que o Radar muda no lugar não se perde"() {
    // o Radar guarda a referência das pendências do dano e dá push nelas (revisão de 03/11/2026)
    const { sb, pedidos } = montar((url, o) => (o.method === "POST" ? { status: 200, corpo: { versao: 1, ids: [[]] } }
      : { status: 200, corpo: [{ id: "D1", pendencias: [{ p: "a", feito: false }], atualizado_em: "t0" }] }),
      { somenteLeitura: false });
    const r = await sb.from("rf_danos_modulos").select("*");
    const dano = r.data[0];
    dano.pendencias.push({ p: "b", feito: false });
    dano.pendencias[0].feito = true;
    await sb.from("rf_danos_modulos").upsert([{ id: "D1", pendencias: dano.pendencias, atualizado_em: "t1" }]);
    igual(JSON.parse(pedidos[1].opcoes.body).ops[0].linhas,
          [{ pendencias: [{ p: "a", feito: true }, { p: "b", feito: false }], atualizado_em: "t1", id: "D1" }]);
    // e depois de salvar, a próxima mudança no lugar também é vista
    dano.pendencias.push({ p: "c", feito: false });
    await sb.from("rf_danos_modulos").upsert([{ id: "D1", pendencias: dano.pendencias, atualizado_em: "t1" }]);
    assert.strictEqual(JSON.parse(pedidos[2].opcoes.body).ops[0].linhas[0].pendencias.length, 3);
  },
  async "gravando, a versão da página vai junto e o aviso de outra pessoa aparece no Radar"() {
    const { sb, pedidos, avisos } = montar((url, o) => {
      if (url.endsWith("/eu")) return { status: 200, corpo: { user: { id: "u1", email: "f@exemplo.com" }, grava: true, versao: 7 } };
      if (o.method === "POST") return { status: 200, corpo: { versao: 9, outros_salvaram: true, sobrepostas: ["cotacoes:C9"], ids: [[]] } };
      return { status: 200, corpo: [] };
    }, { somenteLeitura: false });
    await new Promise((ok) => sb.auth.onAuthStateChange(ok));
    await sb.from("rf_cotacoes").upsert([{ id: "C9", valor: 1 }]);
    assert.strictEqual(JSON.parse(pedidos[1].opcoes.body).versao, 7);
    assert.match(avisos[0], /mudaram o mesmo registro \(cotacoes:C9\)/);
  },
  async "gravando, o histórico apagado e regravado vira a diferença das linhas"() {
    let n = 0;
    const { sb, pedidos } = montar((url, o) => (o.method === "POST"
      ? { status: 200, corpo: { versao: ++n, ids: [[], [], [31]] } }
      : { status: 200, corpo: [{ id: 1, cotacao_id: "C1", valor: 10 }, { id: 2, cotacao_id: "C1", valor: 20 },
                               { id: 3, cotacao_id: "C2", valor: 30 }] }), { somenteLeitura: false });
    await sb.from("rf_historico_valor").select("*");
    // como o syncTudo: apaga tudo e, no passo seguinte, regrava
    await Promise.resolve(sb.from("rf_historico_valor").delete().neq("id", -1)).then(() =>
      sb.from("rf_historico_valor").insert([{ cotacao_id: "C1", valor: 10 }, { cotacao_id: "C2", valor: 30 },
                                            { cotacao_id: "C2", valor: 35 }]));
    assert.strictEqual(pedidos.length, 2);                                   // um salvamento só
    igual(JSON.parse(pedidos[1].opcoes.body).ops, [
      { op: "delete", view: "rf_historico_valor", filtros: [["eq", "id", 2]] },
      { op: "insert", view: "rf_historico_valor", linhas: [{ cotacao_id: "C2", valor: 35 }] }]);
    // a linha nova ganhou o id 31: a próxima regravação igual não manda nada
    await Promise.resolve(sb.from("rf_historico_valor").delete().neq("id", -1)).then(() =>
      sb.from("rf_historico_valor").insert([{ cotacao_id: "C1", valor: 10 }, { cotacao_id: "C2", valor: 30 },
                                            { cotacao_id: "C2", valor: 35 }]));
    await new Promise((ok) => setTimeout(ok, 10));
    assert.strictEqual(pedidos.length, 2);
  },
  async "gravando, o apagar tudo sem regravação apaga o que tinha"() {
    const { sb, pedidos } = montar((url, o) => (o.method === "POST" ? { status: 200, corpo: { versao: 1, ids: [] } }
      : { status: 200, corpo: [{ id: 5, cotacao_id: "C1", valor: 10 }] }), { somenteLeitura: false });
    await sb.from("rf_historico_valor").select("*");
    await sb.from("rf_historico_valor").delete().neq("id", -1);
    await new Promise((ok) => setTimeout(ok, 10));
    igual(JSON.parse(pedidos[1].opcoes.body).ops, [{ op: "delete", view: "rf_historico_valor", filtros: [["eq", "id", 5]] }]);
  },
  async "gravando, update, delete, insert e rpc vão ao servidor, e a recusa chega no error"() {
    const { sb, pedidos } = montar((url, o) => {
      if (url.includes("/funcao/fin_promover")) return { status: 200, corpo: { versao: 3, dados: { promovidos: ["IT-1"] } } };
      if (url.endsWith("/gravar") && JSON.parse(o.body).ops[0].view === "rf_perfis")
        return { status: 403, corpo: { erro: "só o HEAD mexe nos usuários do Radar" } };
      return { status: 200, corpo: { versao: 2, ids: [[8]] } };
    }, { somenteLeitura: false, chaves: { rf_perfis: "user_id" } });
    const u = await sb.from("rf_fin_cenario").update({ nome: "x" }).eq("id", "F1");
    igual([u.error, JSON.parse(pedidos[0].opcoes.body).ops[0]],
          [null, { op: "update", view: "rf_fin_cenario", patch: { nome: "x" }, filtros: [["eq", "id", "F1"]] }]);
    const d = await sb.from("rf_cotacoes").delete().eq("id", "C2");
    igual([d.error, JSON.parse(pedidos[1].opcoes.body).ops[0]], [null, { op: "delete", view: "rf_cotacoes", filtros: [["eq", "id", "C2"]] }]);
    const i = await sb.from("rf_log").insert([{ acao: "editar" }]);
    igual([i.error, i.status], [null, 201]);
    const p = await sb.rpc("fin_promover", { p_cenario_id: "CEN-1" });
    igual([p.data, p.error], [{ promovidos: ["IT-1"] }, null]);
    igual(JSON.parse(pedidos[3].opcoes.body), { args: { p_cenario_id: "CEN-1" }, versao: 0 });
    const f = await sb.from("rf_perfis").update({ papel: "HEAD" }).eq("user_id", "u1");
    igual([f.data, f.error.message, f.status], [null, "só o HEAD mexe nos usuários do Radar", 403]);
  },
};

(async () => {
  for (const [nome, t] of Object.entries(testes)) {
    try { await t(); } catch (e) { console.error("FALHOU: " + nome + "\n" + (e && e.stack || e)); process.exit(1); }
  }
  console.log("ok: " + Object.keys(testes).length + " casos");
})();
