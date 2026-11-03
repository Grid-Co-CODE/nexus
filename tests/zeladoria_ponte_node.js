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

function montar(respostas) {
  const pedidos = [];
  const window = {
    ZELADORIA: { api: "/raiz/t/zeladoria/api", somenteLeitura: true, sair: "/raiz/sair" },
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
  return { sb: window.supabase.createClient(), pedidos, window };
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
    assert.strictEqual(sb.storage, undefined);       // sem storage, o clone cai sozinho no fracttal-fotos
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
};

(async () => {
  for (const [nome, t] of Object.entries(testes)) {
    try { await t(); } catch (e) { console.error("FALHOU: " + nome + "\n" + (e && e.stack || e)); process.exit(1); }
  }
  console.log("ok: " + Object.keys(testes).length + " casos");
})();
