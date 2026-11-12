/* O Mapa de equipe com o mapa de verdade (11/11/2026).
   Levi, com o guia e a prévia do Willian: "Quero que utilize essa referência para completar nosso mapa", com três
   condições: "Pode tirar a opção 3D, não deve ter pois é muito pesada e sem necessidade", "Quero que apareça só Brasil"
   e "Quero em estilo Nexus".
   - O mapa: MapLibre GL 4.7.1 (static/vendor) sobre o mapa base do Brasil, um PMTiles servido pelo próprio Nexus
     (Base > Mapa base; o esquema do Protomaps, dados do OpenStreetMap). Nenhum bloco, fonte ou rota sai para terceiro.
   - Só o Brasil: a câmera não sai do Brasil (maxBounds), e o que é de outro país fica coberto pela máscara (o contorno
     do IBGE como buraco num retângulo do mundo).
   - Sem 3D: sem inclinação, sem giro, sem terreno e sem prédio em pé (maxPitch: 0, dragRotate: false).
   - Estilo Nexus: o estilo é montado aqui a partir dos tokens do nexus.css (os dois temas), sem cor escrita no script;
     a troca de tema refaz o estilo.
   - As divisas do Brasil pulsam de leve em verde Grid (o pedido do Levi de 11/11/2026, mantido com os efeitos de animação
     do Windows desligados); a usina com ocorrência crítica pulsa (parada, com os efeitos desligados).
   O servidor manda tudo pronto no JSON #eq-dados (equipe_tela._dados_do_mapa), depois do registro da LGPD e só com a
   coordenada de quem o mapa mostra. A regra (situação, eventos, percurso, clima) é toda do servidor. */
(function () {
  "use strict";

  // ── as contas puras (testadas no node) ──────────────────────────────────────────────────────────────────────────
  function rgb(cor) {
    var c = String(cor || "").trim();
    var m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(c);
    if (m) {
      var h = m[1].length === 3 ? m[1].replace(/./g, function (x) { return x + x; }) : m[1];
      return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)];
    }
    m = /^rgba?\(([^)]+)\)$/i.exec(c);
    if (m) return m[1].split(",").slice(0, 3).map(function (x) { return Math.round(parseFloat(x)); });
    return [128, 128, 128];
  }
  function mistura(a, b, t) {
    // a cor `a` com a fração `t` da cor `b` (o color-mix do CSS, que o MapLibre não lê)
    var x = rgb(a), y = rgb(b);
    var r = x.map(function (v, i) { return Math.round(v + (y[i] - v) * t); });
    return "rgb(" + r.join(", ") + ")";
  }
  function comAlfa(cor, alfa) {
    return "rgba(" + rgb(cor).join(", ") + ", " + alfa + ")";
  }
  function mascara(brasil) {
    // um retângulo do mundo com o Brasil (cada pedaço do contorno do IBGE) como buraco: cobre o que é de outro país
    var buracos = [];
    (brasil.features || [brasil]).forEach(function (f) {
      var g = f.geometry || f;
      var pols = g.type === "MultiPolygon" ? g.coordinates : [g.coordinates];
      pols.forEach(function (p) { buracos.push(p[0]); });
    });
    var mundo = [[-180, -85], [180, -85], [180, 85], [-180, 85], [-180, -85]];
    return { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [mundo].concat(buracos) } };
  }
  if (typeof module !== "undefined" && module.exports) {
    module.exports = { mistura: mistura, mascara: mascara, rgb: rgb };
    return;
  }

  var dadosEl = document.getElementById("eq-dados"), caixaMapa = document.getElementById("eq-mapa");
  if (!dadosEl || !caixaMapa) return;
  var D = JSON.parse(dadosEl.textContent);
  var palco = caixaMapa.parentNode, quadro = palco.closest(".eq-quadro") || palco.parentNode;
  var dica = palco.querySelector(".eq-dica"), aviso = palco.querySelector(".eq-ml-aviso");
  var raiz = document.documentElement;
  var REDUZIDO = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  var BRASIL = [[-74.1, -33.9], [-34.7, 5.4]];
  var FONTE = ["Noto Sans Regular"], FONTE_M = ["Noto Sans Medium"], FONTE_I = ["Noto Sans Italic"];

  function avisar(texto) { aviso.textContent = texto; aviso.hidden = false; }
  function temWebGL() {
    try { var c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); }
    catch (e) { return false; }
  }
  if (!window.maplibregl || !window.pmtiles || !temWebGL()) {
    avisar("Este navegador não abre o mapa (sem WebGL). Use o desenho dos estados: acrescente ?mapa=desenho ao endereço.");
    return;
  }

  // ── as cores: os tokens do nexus.css, lidos na hora (os dois temas) ─────────────────────────────────────────────
  var TOKENS = ["--superficie", "--superficie-2", "--fundo", "--linha", "--linha-forte", "--tinta", "--tinta-2", "--mudo",
                "--verde", "--info-cheio", "--ok-cheio", "--alerta-cheio", "--critico", "--severo", "--papel", "--papel-tinta"];
  function paleta() {
    var cs = getComputedStyle(raiz), t = {};
    TOKENS.forEach(function (n) { t[n] = cs.getPropertyValue(n).trim(); });
    var claro = raiz.getAttribute("data-tema") === "claro";
    var terra = mistura(t["--superficie"], t["--verde"], claro ? 0.04 : 0.025);
    return {
      t: t, claro: claro, terra: terra,
      agua: mistura(t["--fundo"], t["--info-cheio"], claro ? 0.22 : 0.16),
      mata: mistura(terra, t["--verde"], claro ? 0.13 : 0.07),
      urbano: mistura(terra, t["--tinta"], claro ? 0.07 : 0.06),
      predio: mistura(terra, t["--tinta"], claro ? 0.14 : 0.12),
      casco: mistura(t["--fundo"], t["--tinta"], claro ? 0.12 : 0.0),
      viaRodovia: mistura(t["--tinta-2"], t["--verde"], claro ? 0.35 : 0.42),
      viaMaior: mistura(terra, t["--tinta-2"], claro ? 0.6 : 0.5),
      viaMedia: mistura(terra, t["--tinta-2"], claro ? 0.45 : 0.34),
      viaMenor: mistura(terra, t["--tinta-2"], claro ? 0.3 : 0.2),
      limiteUf: mistura(t["--linha-forte"], t["--verde"], claro ? 0.45 : 0.4),
      verde: t["--verde"], rotulo: t["--tinta-2"], forte: t["--tinta"], fraco: t["--mudo"],
      halo: claro ? t["--superficie"] : t["--fundo"],
      // só o Brasil (Levi, 12/11/2026: "tem como mostrar só Brasil?"): a máscara de fora é o fundo, cheio; com 90% o
      // satélite do mundo e os vizinhos do recorte apareciam apagados por baixo
      fora: t["--fundo"],
      rotuloAgua: mistura(t["--info-cheio"], t["--tinta-2"], 0.35)
    };
  }
  var P = paleta();
  var TOM = function () {
    return { info: P.t["--info-cheio"], ok: P.t["--ok-cheio"], alerta: P.t["--alerta-cheio"], critico: P.t["--critico"],
             neutro: P.t["--mudo"] };
  };
  var NIVEL = function () {
    return { agir: P.t["--critico"], atencao: P.t["--alerta-cheio"], regiao: P.t["--info-cheio"], sem: P.t["--ok-cheio"],
             nx: P.t["--mudo"] };
  };
  var nome = ["coalesce", ["get", "name:pt"], ["get", "name"]];
  var z = function (pares) { return ["interpolate", ["exponential", 1.5], ["zoom"]].concat([].concat.apply([], pares)); };

  // ── o estilo do mapa base (o esquema do Protomaps v4) ───────────────────────────────────────────────────────────
  function estilo() {
    var via = function (id, filtro, cor, larg, min, casco) {
      var f = ["all", ["==", ["geometry-type"], "LineString"], filtro, ["!=", ["get", "is_tunnel"], true]];
      var out = [];
      if (casco) out.push({ id: "casco-" + id, type: "line", source: "base", "source-layer": "roads", minzoom: Math.max(min, 9),
        filter: f, layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": P.casco, "line-width": z(larg.map(function (p) { return [p[0], p[1] + (p[0] >= 12 ? 2.4 : 1.2)]; })) } });
      out.push({ id: "via-" + id, type: "line", source: "base", "source-layer": "roads", minzoom: min, filter: f,
        layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": cor, "line-width": z(larg) } });
      return out;
    };
    var k = function (v) { return ["==", ["get", "kind"], v]; };
    var vias = [].concat(
      via("menor", ["in", ["get", "kind"], ["literal", ["minor_road", "other"]]], P.viaMenor, [[12, 0.4], [14, 1.6], [17, 7]], 12, true),
      via("media", k("medium_road"), P.viaMedia, [[9, 0.4], [12, 1.1], [15, 3.4], [18, 12]], 9, true),
      via("maior", k("major_road"), P.viaMaior, [[6.5, 0.5], [10, 1.3], [14, 4.2], [18, 16]], 6, true),
      via("rodovia", k("highway"), P.viaRodovia, [[4.5, 0.6], [9, 1.6], [13, 4.4], [18, 20]], 4, true));
    return {
      version: 8,
      glyphs: new URL(D.fontes.replace("{fontstack}", "FONTSTACK").replace("{range}", "RANGE"), location.href).href
        .replace("FONTSTACK", "{fontstack}").replace("RANGE", "{range}"),
      sources: Object.assign({
        base: { type: "vector", url: "pmtiles://" + new URL(D.blocos, location.href).href,
                attribution: "© OpenStreetMap · Protomaps" }
      }, D.satelite ? { satelite: { type: "raster", tiles: [D.satelite.url], tileSize: 256, maxzoom: 19,
                                    attribution: D.satelite.credito } } : {}),
      layers: [
        { id: "fundo", type: "background", paint: { "background-color": P.agua } }
      ].concat(D.satelite ? [{ id: "satelite", type: "raster", source: "satelite", layout: { visibility: "none" },
                               paint: { "raster-fade-duration": 150 } }] : [], [
        { id: "terra", type: "fill", source: "base", "source-layer": "earth", paint: { "fill-color": P.terra } },
        { id: "mata-baixa", type: "fill", source: "base", "source-layer": "landcover", filter: ["in", ["get", "kind"], ["literal", ["forest", "scrub", "grassland"]]],
          paint: { "fill-color": P.mata, "fill-opacity": 0.6 } },
        { id: "uso-verde", type: "fill", source: "base", "source-layer": "landuse",
          filter: ["in", ["get", "kind"], ["literal", ["park", "national_park", "nature_reserve", "protected_area", "forest", "wood", "grass", "meadow", "scrub", "garden"]]],
          paint: { "fill-color": P.mata, "fill-opacity": ["interpolate", ["linear"], ["zoom"], 6, 0.5, 12, 0.9] } },
        { id: "uso-urbano", type: "fill", source: "base", "source-layer": "landuse",
          filter: ["in", ["get", "kind"], ["literal", ["residential", "commercial", "industrial", "retail", "neighbourhood", "urban_area", "railway"]]],
          paint: { "fill-color": P.urbano } },
        { id: "agua", type: "fill", source: "base", "source-layer": "water", filter: ["==", ["geometry-type"], "Polygon"],
          paint: { "fill-color": P.agua } },
        { id: "rio", type: "line", source: "base", "source-layer": "water", minzoom: 7,
          filter: ["all", ["==", ["geometry-type"], "LineString"], ["in", ["get", "kind"], ["literal", ["river", "canal", "stream"]]]],
          layout: { "line-cap": "round" },
          paint: { "line-color": P.agua, "line-width": ["interpolate", ["exponential", 1.5], ["zoom"], 8, ["match", ["get", "kind"], "river", 0.8, 0.2], 14, ["match", ["get", "kind"], "river", 4, 1.2], 18, ["match", ["get", "kind"], "river", 14, 4]] } },
        { id: "predio", type: "fill", source: "base", "source-layer": "buildings", minzoom: 13.5,
          paint: { "fill-color": P.predio, "fill-opacity": ["interpolate", ["linear"], ["zoom"], 13.5, 0, 14.5, 1] } },
        { id: "limite-uf", type: "line", source: "base", "source-layer": "boundaries", filter: k("region"),
          paint: { "line-color": P.limiteUf, "line-width": ["interpolate", ["linear"], ["zoom"], 3, 0.7, 10, 1.5], "line-dasharray": [3, 2] } }
      ], vias, [
        { id: "trilho", type: "line", source: "base", "source-layer": "roads", minzoom: 10, filter: k("rail"),
          paint: { "line-color": P.viaMenor, "line-width": ["interpolate", ["linear"], ["zoom"], 10, 0.6, 16, 2], "line-dasharray": [3, 3] } },
        { id: "nome-rio", type: "symbol", source: "base", "source-layer": "water", minzoom: 11,
          filter: ["all", ["==", ["geometry-type"], "LineString"], k("river")],
          layout: { "symbol-placement": "line", "text-field": nome, "text-font": FONTE_I, "text-size": 11, "symbol-spacing": 400 },
          paint: { "text-color": P.rotuloAgua, "text-halo-color": P.halo, "text-halo-width": 1.4 } },
        { id: "nome-rua", type: "symbol", source: "base", "source-layer": "roads", minzoom: 13.5,
          filter: ["in", ["get", "kind"], ["literal", ["major_road", "medium_road", "minor_road"]]],
          layout: { "symbol-placement": "line", "text-field": nome, "text-font": FONTE, "text-size": ["interpolate", ["linear"], ["zoom"], 14, 10.5, 18, 13], "symbol-spacing": 300, "text-max-angle": 30 },
          paint: { "text-color": P.rotulo, "text-halo-color": P.halo, "text-halo-width": 1.5 } },
        { id: "numero-via", type: "symbol", source: "base", "source-layer": "roads", minzoom: 7,
          filter: ["all", ["in", ["get", "kind"], ["literal", ["highway", "major_road"]]], ["has", "ref"]],
          layout: { "symbol-placement": "line", "symbol-spacing": ["interpolate", ["linear"], ["zoom"], 7, 300, 14, 500],
                    "text-field": ["get", "ref"], "text-font": FONTE_M, "text-size": 10, "text-rotation-alignment": "viewport" },
          paint: { "text-color": P.forte, "text-halo-color": P.casco, "text-halo-width": 2 } },
        { id: "nome-bairro", type: "symbol", source: "base", "source-layer": "places", minzoom: 12.5,
          filter: ["in", ["get", "kind"], ["literal", ["neighbourhood", "macrohood"]]],
          layout: { "text-field": nome, "text-font": FONTE, "text-size": 11, "text-letter-spacing": 0.04 },
          paint: { "text-color": P.fraco, "text-halo-color": P.halo, "text-halo-width": 1.4 } },
        { id: "nome-cidade", type: "symbol", source: "base", "source-layer": "places", minzoom: 5,
          filter: k("locality"),
          layout: { "text-field": nome, "text-font": FONTE_M,
                    "text-size": ["interpolate", ["linear"], ["zoom"], 5, 10.5, 10, 13, 14, 15],
                    "symbol-sort-key": ["coalesce", ["get", "min_zoom"], 20] },
          paint: { "text-color": P.rotulo, "text-halo-color": P.halo, "text-halo-width": 1.6 } },
        { id: "nome-uf", type: "symbol", source: "base", "source-layer": "places", minzoom: 3.5, maxzoom: 7, filter: k("region"),
          layout: { "text-field": nome, "text-font": FONTE_M, "text-size": 11, "text-transform": "uppercase", "text-letter-spacing": 0.14 },
          paint: { "text-color": mistura(P.fraco, P.verde, 0.35), "text-halo-color": P.halo, "text-halo-width": 1.2 } }
      ])
    };
  }

  // ── os ícones: a usina é um losango (o técnico é o círculo), na cor do dado ─────────────────────────────────────
  function losango(fundo, borda, selo) {
    var px = 2, L = 26, cv = document.createElement("canvas");
    cv.width = cv.height = L * px;
    var g = cv.getContext("2d");
    g.scale(px, px);
    g.beginPath(); g.moveTo(13, 2.5); g.lineTo(23.5, 13); g.lineTo(13, 23.5); g.lineTo(2.5, 13); g.closePath();
    g.fillStyle = fundo; g.fill(); g.lineWidth = 2; g.strokeStyle = borda; g.stroke();
    if (selo) {
      g.beginPath(); g.arc(20, 6, 5, 0, Math.PI * 2); g.fillStyle = selo; g.fill();
      g.lineWidth = 1.4; g.strokeStyle = P.t["--fundo"]; g.stroke();
      g.strokeStyle = P.t["--fundo"]; g.lineWidth = 1.6; g.lineCap = "round";
      g.beginPath(); g.moveTo(20, 3.6); g.lineTo(20, 6.6); g.moveTo(20, 8.4); g.lineTo(20, 8.5); g.stroke();
    }
    return g.getImageData(0, 0, cv.width, cv.height);
  }
  // a cor da usina (12/11/2026, Levi: "Quero as cores das usinas de acordo com o tempo real, OS Abertas do setor COS, as
  // regras estão em 'Comando > Usinas' pode pegar as cores de lá!"): o Agora de Comando > Usinas, no tom de lá (normal
  // verde, atenção amarelo, crítico vermelho, sem comunicação cinza; sem leitura do COS só o contorno). Com o clima
  // ligado, a cor é o nível do alerta de clima, e o selo "!" diz que o COS tem crítico ou atenção
  function corDaUsina(u) {
    if (u.nivel) return u.nivel;
    if (u.agora) return u.agora.estado === "sem_leitura" ? "sem_leitura" : "a_" + u.agora.tom;
    return D.modo === "usinas" ? "dest" : "neutra";
  }
  function icones(mapa) {
    var cores = NIVEL();
    var fill = { neutra: P.terra, dest: P.verde, sem_leitura: P.terra, a_ok: P.t["--ok-cheio"],
                 a_alerta: P.t["--alerta-cheio"], a_critico: P.t["--critico"], a_neutro: P.t["--mudo"] };
    Object.keys(cores).forEach(function (k) { fill[k] = cores[k]; });
    Object.keys(fill).forEach(function (k) {
      var borda = k === "neutra" ? P.verde : k === "sem_leitura" ? P.t["--mudo"] : P.t["--fundo"];
      [false, true].forEach(function (comSelo) {
        var id = "u-" + k + (comSelo ? "-!" : "");
        if (mapa.hasImage(id)) mapa.removeImage(id);
        mapa.addImage(id, losango(fill[k], borda, comSelo ? P.t["--critico"] : null), { pixelRatio: 2 });
      });
    });
    // a seta do sentido do percurso
    var px = 2, cv = document.createElement("canvas");
    cv.width = cv.height = 12 * px;
    var g = cv.getContext("2d");
    g.scale(px, px); g.strokeStyle = P.t["--fundo"]; g.lineWidth = 2.2; g.lineCap = "round"; g.lineJoin = "round";
    g.beginPath(); g.moveTo(3.5, 2.5); g.lineTo(8, 6); g.lineTo(3.5, 9.5); g.stroke();
    if (mapa.hasImage("seta")) mapa.removeImage("seta");
    mapa.addImage("seta", g.getImageData(0, 0, cv.width, cv.height), { pixelRatio: 2 });
  }

  // ── os dados nossos em GeoJSON ──────────────────────────────────────────────────────────────────────────────────
  function fc(feats) { return { type: "FeatureCollection", features: feats }; }
  function ponto(c, props) { return { type: "Feature", geometry: { type: "Point", coordinates: c }, properties: props || {} }; }
  function linhaGeo(coords) {
    return fc(coords.length > 1 ? [{ type: "Feature", geometry: { type: "LineString", coordinates: coords }, properties: {} }] : []);
  }
  function usinasGeo() {
    var ORD = { agir: 9, a_critico: 8, atencao: 7, a_alerta: 6, regiao: 4, sem: 3, nx: 2, a_neutro: 2, a_ok: 1, dest: 1,
                sem_leitura: 0, neutra: 0 };
    return fc(D.usinas.map(function (u) {
      var cor = corDaUsina(u);
      var selo = !!(u.nivel && u.agora && (u.agora.tom === "critico" || u.agora.tom === "alerta"));
      return ponto(u.c, { id: u.id, nome: u.nome, icone: "u-" + cor + (selo ? "-!" : ""), ordem: ORD[cor] || 0,
                          pulso: cor === "agir" || cor === "a_critico" });
    }));
  }
  function tecnicosGeo() {
    var tom = TOM();
    return fc(D.tecnicos.map(function (t) {
      return ponto(t.c, { pid: t.pid, ini: t.ini, cor: tom[t.tom] || tom.neutro, velho: t.velho, sel: t.sel,
                          ordem: t.sel ? 3 : t.velho ? 0 : 1 });
    }));
  }
  // o trecho atual do percurso (onde as "formigas" andam): do último ponto parado ao fim
  function trechoAtual() {
    var p = D.percurso.pontos, k = 0;
    for (var i = 0; i < p.length - 1; i++) if (!p[i].mov) k = i;
    return p.slice(k).map(function (q) { return q.c; });
  }
  function percursoGeo() {
    var p = D.percurso;
    if (!p) return { linha: fc([]), pontos: fc([]), marcos: fc([]), atual: fc([]) };
    var tom = TOM(), n = p.pontos.length;
    return {
      linha: linhaGeo(p.linha),
      pontos: fc(p.pontos.map(function (q, i) {
        return ponto(q.c, { cor: q.mov ? tom.info : tom.neutro, ponta: i === 0 || i === n - 1, hora: q.hora });
      })),
      marcos: fc(p.marcos.map(function (m) { return ponto(m.c, { texto: m.hora + " · " + m.texto, tipo: m.tipo }); })),
      atual: linhaGeo(trechoAtual())
    };
  }

  // ── o mapa ──────────────────────────────────────────────────────────────────────────────────────────────────────
  var protocolo = new pmtiles.Protocol();
  maplibregl.addProtocol("pmtiles", protocolo.tile);
  var mapa;
  try {
    mapa = new maplibregl.Map({
      container: caixaMapa, style: estilo(), bounds: BRASIL, fitBoundsOptions: { padding: 24 },
      maxBounds: [[-100, -48], [-12, 18]], minZoom: 2.5, maxZoom: 18,
      maxPitch: 0, dragRotate: false, pitchWithRotate: false, touchPitch: false,
      attributionControl: { compact: true }, fadeDuration: REDUZIDO ? 0 : 180, locale: {
        "NavigationControl.ZoomIn": "Aproximar", "NavigationControl.ZoomOut": "Afastar",
        "AttributionControl.ToggleAttribution": "Créditos do mapa", "ScaleControl.Meters": "m", "ScaleControl.Kilometers": "km" }
    });
  } catch (e) {
    avisar("O mapa não abriu neste navegador (" + e.message + "). Use o desenho dos estados: acrescente ?mapa=desenho ao endereço.");
    return;
  }
  caixaMapa.mapa = mapa;          // para a conferência no navegador (a bancada e o teste de produção)
  mapa.touchZoomRotate.disableRotation();
  mapa.keyboard.disableRotation();
  // o zoom mais rápido (Levi, 12/11/2026: "Quero o zoom um pouco mais rápido, pelo menos o dobro"): a roda do mouse 2,25x
  // (o padrão é 1/450), o trackpad 2,2x (1/100) e os botões de 2 em 2 níveis
  mapa.scrollZoom.setWheelZoomRate(1 / 200);
  mapa.scrollZoom.setZoomRate(1 / 45);
  mapa.addControl(new maplibregl.ScaleControl({ unit: "metric", maxWidth: 110 }), "bottom-left");
  mapa.on("error", function (ev) {
    var msg = ev && ev.error && ev.error.message || "";
    if (window.console) console.warn("Mapa de equipe:", msg);
    if (/404|pmtiles|Failed to fetch/i.test(msg) && !/arcgis/i.test(msg)) avisar("O mapa base não respondeu agora (" + msg.slice(0, 80) + "). Recarregue a página.");
  });

  function guardado(chave, padrao) {
    try { return localStorage.getItem(chave) || padrao; } catch (e) { return padrao; }
  }
  function guardar(chave, v) { try { localStorage.setItem(chave, v); } catch (e) { /* sem armazenamento */ } }
  var foco = D.modo === "tecnicos" ? guardado("nexus.equipe.foco", "tecnico") : "usina";
  var fundoBase = D.satelite ? guardado("nexus.equipe.base", "mapa") : "mapa";

  var brasilGeo = null;
  function nossas() {
    icones(mapa);
    var vazio = fc([]), pg = percursoGeo();
    var add = function (id, data, extra) {
      if (!mapa.getSource(id)) mapa.addSource(id, Object.assign({ type: "geojson", data: data }, extra || {}));
    };
    add("fora", brasilGeo ? fc([mascara(brasilGeo)]) : vazio);
    add("brasil", brasilGeo || vazio);
    add("avisos", D.clima ? D.clima.avisos : vazio);
    add("focos", fc(D.clima ? D.clima.focos.map(function (c) { return ponto(c); }) : []));
    add("aneis", fc(D.clima ? D.clima.aneis.map(function (c) { return ponto(c); }) : []));
    add("usinas", usinasGeo());
    add("tecnicos", tecnicosGeo());
    add("perc-linha", pg.linha, { lineMetrics: true });
    add("perc-atual", pg.atual);
    add("perc-pontos", pg.pontos);
    add("perc-marcos", pg.marcos);
    add("perc-agora", vazio);
    var nv = { 1: P.t["--alerta-cheio"], 2: P.t["--severo"], 3: P.t["--critico"] };
    var corAviso = ["match", ["get", "nivel"], 1, nv[1], 2, nv[2], nv[3]];
    var L = [
      // só o Brasil: o resto do mundo coberto, e o contorno do país em verde Grid (pulsa de leve)
      { id: "fora", type: "fill", source: "fora", paint: { "fill-color": P.fora } },
      { id: "brasil-borda", type: "line", source: "brasil", layout: { "line-join": "round" },
        paint: { "line-color": P.verde, "line-width": ["interpolate", ["linear"], ["zoom"], 3, 1.2, 10, 2.4], "line-opacity": 0.85,
                 "line-opacity-transition": { duration: 1300, delay: 0 } } },
      // o clima: a área do aviso (o que ainda vai começar, só o contorno tracejado), os focos e o anel perto de usina
      { id: "avisos", type: "fill", source: "avisos", filter: ["!", ["get", "futuro"]], paint: { "fill-color": corAviso, "fill-opacity": 0.24 } },
      { id: "avisos-futuro", type: "line", source: "avisos", filter: ["get", "futuro"], paint: { "line-color": corAviso, "line-width": 1.5, "line-dasharray": [3, 2] } },
      { id: "focos", type: "circle", source: "focos", paint: { "circle-color": P.t["--severo"], "circle-opacity": 0.8, "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 1.6, 10, 3.2] } },
      { id: "aneis", type: "circle", source: "aneis", paint: { "circle-color": comAlfa(P.t["--critico"], 0.12), "circle-stroke-color": P.t["--critico"], "circle-stroke-width": 2, "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 6, 12, 14] } },
      // o percurso (a animação da prévia, Levi, 12/11/2026): a linha que esquenta do início (apagada) ao fim (verde Grid),
      // com halo, as setas do sentido, o trecho atual andando (as "formigas"), os pontos de perto, os marcos e o "agora"
      { id: "perc-halo", type: "line", source: "perc-linha", layout: { "line-cap": "round", "line-join": "round" }, paint: { "line-color": P.verde, "line-opacity": 0.2, "line-width": z([[5, 6], [12, 12], [16, 18]]) } },
      { id: "perc-linha", type: "line", source: "perc-linha", layout: { "line-cap": "round", "line-join": "round" }, paint: {
        "line-gradient": ["interpolate", ["linear"], ["line-progress"], 0, mistura(P.fraco, P.verde, 0.35), 1, P.verde],
        "line-width": z([[5, 2.6], [12, 4.2], [16, 6.5]]) } },
      { id: "perc-formigas", type: "line", source: "perc-atual", layout: { "line-cap": "butt", "line-join": "round" }, paint: { "line-color": P.t["--papel"], "line-opacity": 0.85, "line-width": z([[5, 1.2], [12, 1.8], [16, 2.6]]), "line-dasharray": [0, 4, 3] } },
      { id: "perc-setas", type: "symbol", source: "perc-linha", minzoom: 7, layout: { "symbol-placement": "line", "symbol-spacing": 90, "icon-image": "seta", "icon-size": ["interpolate", ["linear"], ["zoom"], 8, 0.75, 15, 1.05], "icon-allow-overlap": true, "icon-ignore-placement": true, "icon-rotation-alignment": "map" } },
      { id: "perc-pontos", type: "circle", source: "perc-pontos", minzoom: 9, filter: ["!", ["get", "ponta"]], paint: { "circle-color": ["get", "cor"], "circle-radius": 3.6, "circle-stroke-color": P.t["--superficie"], "circle-stroke-width": 1.2 } },
      { id: "perc-pontas", type: "circle", source: "perc-pontos", filter: ["get", "ponta"], paint: { "circle-color": ["get", "cor"], "circle-radius": 7, "circle-stroke-color": P.forte, "circle-stroke-width": 2.4 } },
      // a usina: o losango que cresce com o zoom (Levi, 11/11/2026), uma a uma (nunca agrupada); a crítica pulsa
      { id: "usinas-pulso", type: "circle", source: "usinas", filter: ["get", "pulso"], paint: { "circle-color": comAlfa(P.t["--critico"], 0), "circle-stroke-color": P.t["--critico"], "circle-stroke-width": 2, "circle-radius": 12, "circle-stroke-opacity": 0.75,
        "circle-radius-transition": { duration: REDUZIDO ? 0 : 1100 }, "circle-stroke-opacity-transition": { duration: REDUZIDO ? 0 : 1100 } } },
      { id: "usinas", type: "symbol", source: "usinas", layout: { "icon-image": ["get", "icone"], "icon-size": tamanhoUsina(1),
        "icon-allow-overlap": true, "icon-ignore-placement": true, "symbol-sort-key": ["get", "ordem"] } },
      { id: "usinas-nome", type: "symbol", source: "usinas", minzoom: 8.5, layout: { "text-field": ["get", "nome"], "text-font": FONTE_M, "text-size": ["interpolate", ["linear"], ["zoom"], 8.5, 10.5, 13, 12.5],
        "text-variable-anchor": ["left", "right", "top", "bottom"], "text-radial-offset": 1.1, "text-optional": true }, paint: { "text-color": P.forte, "text-halo-color": P.halo, "text-halo-width": 1.6 } },
      { id: "perc-marcos", type: "symbol", source: "perc-marcos", layout: { "text-field": ["get", "texto"], "text-font": FONTE_M, "text-size": 11.5, "text-max-width": 16,
        "text-variable-anchor": ["left", "right", "top", "bottom"], "text-radial-offset": 1.2, "text-justify": "auto" }, paint: { "text-color": P.forte, "text-halo-color": P.halo, "text-halo-width": 1.8 } },
      { id: "perc-agora", type: "circle", source: "perc-agora", paint: { "circle-color": P.verde, "circle-radius": 8, "circle-stroke-color": P.t["--fundo"], "circle-stroke-width": 3 } },
      { id: "perc-agora-hora", type: "symbol", source: "perc-agora", layout: { "text-field": ["get", "hora"], "text-font": FONTE_M, "text-size": 12, "text-offset": [0, -1.6], "text-allow-overlap": true },
        paint: { "text-color": P.forte, "text-halo-color": P.halo, "text-halo-width": 2 } },
      // o técnico (Levi, 12/11/2026: "aumente um pouco o tamanho do circulo dos técnicos"): o círculo na cor da situação
      // com as iniciais (de outro dia, só o contorno); o escolhido com o anel branco e o halo escuro
      { id: "tecnicos-halo", type: "circle", source: "tecnicos", filter: ["get", "sel"], paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 14, 10, 18], "circle-color": P.t["--papel-tinta"] } },
      { id: "tecnicos", type: "circle", source: "tecnicos", layout: { "circle-sort-key": ["get", "ordem"] }, paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 10, 10, 14],
        "circle-color": ["case", ["get", "velho"], P.t["--superficie"], ["get", "cor"]],
        "circle-stroke-color": ["case", ["get", "sel"], P.t["--papel"], ["get", "velho"], P.t["--mudo"], P.t["--superficie"]],
        "circle-stroke-width": ["case", ["get", "sel"], 3.2, ["get", "velho"], 2.6, 1.8] } },
      { id: "tecnicos-ini", type: "symbol", source: "tecnicos", layout: { "text-field": ["get", "ini"], "text-font": FONTE_M, "text-size": 11, "text-allow-overlap": true, "text-ignore-placement": true },
        paint: { "text-color": ["case", ["get", "velho"], P.fraco, P.t["--fundo"]] } }
    ];
    L.forEach(function (l) { if (!mapa.getLayer(l.id)) mapa.addLayer(l); });
    aplicarFoco();
    aplicarBase();
  }
  function tamanhoUsina(f) {
    return ["interpolate", ["linear"], ["zoom"], 3, 0.5 * f, 6, 0.65 * f, 9, 0.85 * f, 12, 1.1 * f, 15, 1.4 * f];
  }

  // os dois focos (Levi, 12/11/2026: "Quero ter dois focos, foco técnico e focos usina, dessa forma dá para focar
  // melhor"): no foco técnico o técnico manda (a usina menor e mais apagada, o nome só de perto); no foco usina a usina
  // manda (maior, com o nome mais cedo) e o técnico vira um ponto pequeno, sem as iniciais. A escolha fica no navegador
  function aplicarFoco() {
    if (!mapa.getLayer("usinas")) return;
    var u = foco === "usina";
    mapa.setLayoutProperty("usinas", "icon-size", tamanhoUsina(u ? 1.25 : (D.modo === "tecnicos" ? 0.8 : 1)));
    mapa.setPaintProperty("usinas", "icon-opacity", u || D.modo !== "tecnicos" ? 1 : 0.75);
    mapa.setLayerZoomRange("usinas-nome", u ? 6.5 : 9.5, 24);
    if (mapa.getLayer("tecnicos")) {
      mapa.setPaintProperty("tecnicos", "circle-radius", u ? ["interpolate", ["linear"], ["zoom"], 3, 5, 10, 7]
                                                           : ["interpolate", ["linear"], ["zoom"], 3, 10, 10, 14]);
      mapa.setPaintProperty("tecnicos", "circle-opacity", u ? 0.55 : 1);
      mapa.setPaintProperty("tecnicos", "circle-stroke-opacity", u ? 0.55 : 1);
      mapa.setLayoutProperty("tecnicos-ini", "visibility", u ? "none" : "visible");
      mapa.setPaintProperty("tecnicos-halo", "circle-opacity", u ? 0.4 : 1);
    }
    quadro.querySelectorAll("[data-eq-foco]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-eq-foco") === foco));
    });
  }
  // o Mapa | Satélite (Levi, 12/11/2026: "Quero a visão de mapa e satélite"; a Esri, com a chave de Base > Chaves): no
  // satélite a imagem manda, e as ruas ficam finas e translúcidas por cima
  var SO_MAPA = ["terra", "mata-baixa", "uso-verde", "uso-urbano", "agua", "predio"];
  function aplicarBase() {
    if (!D.satelite || !mapa.getLayer("satelite")) return;
    var sat = fundoBase === "satelite";
    mapa.setLayoutProperty("satelite", "visibility", sat ? "visible" : "none");
    SO_MAPA.forEach(function (id) { if (mapa.getLayer(id)) mapa.setLayoutProperty(id, "visibility", sat ? "none" : "visible"); });
    ["menor", "media", "maior", "rodovia"].forEach(function (v) {
      if (mapa.getLayer("via-" + v)) mapa.setPaintProperty("via-" + v, "line-opacity", sat ? (v === "menor" ? 0 : 0.55) : 1);
      if (mapa.getLayer("casco-" + v)) mapa.setPaintProperty("casco-" + v, "line-opacity", sat ? 0 : 1);
    });
    quadro.querySelectorAll("[data-eq-base]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-eq-base") === fundoBase));
    });
  }

  // o pulso: as divisas do Brasil (sempre, pedido do Levi) e a usina crítica (parada com os efeitos desligados)
  var fase = false;
  setInterval(function () {
    if (!mapa.getLayer("brasil-borda")) return;
    fase = !fase;
    mapa.setPaintProperty("brasil-borda", "line-opacity", fase ? 0.35 : 0.95);
    if (!REDUZIDO && mapa.getLayer("usinas-pulso")) {
      mapa.setPaintProperty("usinas-pulso", "circle-radius", fase ? 20 : 12);
      mapa.setPaintProperty("usinas-pulso", "circle-stroke-opacity", fase ? 0.05 : 0.75);
    }
  }, 1300);
  // as formigas do trecho atual do percurso (a prévia; pedida pelo Levi, roda também com os efeitos desligados)
  var FORMIGAS = [[0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5], [2, 4, 1], [2.5, 4, 0.5], [3, 4, 0], [0, 0.5, 3, 3.5],
                  [0, 1, 3, 3], [0, 1.5, 3, 2.5], [0, 2, 3, 2], [0, 2.5, 3, 1.5], [0, 3, 3, 1], [0, 3.5, 3, 0.5]];
  var passoFormiga = 0;
  if (D.percurso) setInterval(function () {
    if (!mapa.getLayer("perc-formigas")) return;
    passoFormiga = (passoFormiga + 1) % FORMIGAS.length;
    mapa.setPaintProperty("perc-formigas", "line-dasharray", FORMIGAS[passoFormiga]);
  }, 60);

  // ── a reprodução do percurso: o traço se desenha do início ao fim, com o "agora" andando e a hora ──────────────────
  // a barra mora na gaveta, que vem DEPOIS deste script na página: é procurada quando o mapa carrega
  var rp = null, R = null;
  function horaDe(t) {
    return new Date(t * 1000).toLocaleTimeString("pt-BR", { timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit" });
  }
  function desenharAte(t) {
    var p = D.percurso.pontos, coords = [], c = p[0].c;
    for (var i = 0; i < p.length; i++) {
      if (p[i].t <= t) { coords.push(p[i].c); c = p[i].c; continue; }
      var a = p[i - 1] || p[i], f = a.t === p[i].t ? 1 : (t - a.t) / (p[i].t - a.t);
      c = [a.c[0] + (p[i].c[0] - a.c[0]) * f, a.c[1] + (p[i].c[1] - a.c[1]) * f];
      coords.push(c);
      break;
    }
    var fim = t >= R.t1;
    mapa.getSource("perc-linha").setData(linhaGeo(fim ? D.percurso.linha : coords));
    mapa.getSource("perc-agora").setData(fim ? fc([]) : fc([ponto(c, { hora: horaDe(t) })]));
    if (rp) {
      rp.querySelector("[data-eq-replay-tempo]").value = String(Math.round((t - R.t0) / Math.max(1, R.t1 - R.t0) * 1000));
      rp.querySelector("[data-eq-replay-hora]").textContent = horaDe(t);
      var bt = rp.querySelector("[data-eq-replay-tocar] i");
      if (bt) bt.className = "ph ph-" + (R.tocando ? "pause" : "play");
    }
  }
  var ultimoQuadro = 0;
  function quadroReplay(ms) {
    if (!R || !R.tocando) return;
    var dt = ultimoQuadro ? (ms - ultimoQuadro) / 1000 : 0;
    ultimoQuadro = ms;
    R.t = Math.min(R.t1, R.t + dt * R.vel);
    if (R.t >= R.t1) R.tocando = false;
    desenharAte(R.t);
    if (R.tocando) requestAnimationFrame(quadroReplay);
  }
  function tocar(vel) {
    if (R.t >= R.t1) R.t = R.t0;
    R.vel = vel; R.tocando = true; ultimoQuadro = 0;
    requestAnimationFrame(quadroReplay);
  }
  function prepararReplay() {
    var p = D.percurso.pontos;
    if (p.length < 2) return;
    R = { t0: p[0].t, t1: p[p.length - 1].t, t: p[p.length - 1].t, tocando: false, vel: 480 };
    rp = document.querySelector("[data-eq-replay]");
    if (!rp) return;
    rp.hidden = false;
    var vel = rp.querySelector("[data-eq-replay-vel]");
    rp.querySelector("[data-eq-replay-hora]").textContent = horaDe(R.t1);
    rp.querySelector("[data-eq-replay-tocar]").addEventListener("click", function () {
      if (R.tocando) { R.tocando = false; desenharAte(R.t); } else tocar(+vel.value);
    });
    rp.querySelector("[data-eq-replay-tempo]").addEventListener("input", function (e) {
      R.tocando = false;
      R.t = R.t0 + (R.t1 - R.t0) * (+e.target.value) / 1000;
      desenharAte(R.t);
    });
    vel.addEventListener("change", function () { if (R.tocando) R.vel = +vel.value; });
  }

  mapa.on("load", function () {
    fetch(new URL(D.brasil, location.href).href, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (g) { brasilGeo = g; }).catch(function () { brasilGeo = null; })
      .then(function () {
        nossas();
        if (D.percurso && D.percurso.pontos.length > 1) {
          // a câmera vai ao percurso e o traço se desenha sozinho uma vez (~8 s), como na prévia
          prepararReplay();
          var cx = D.percurso.caixa;
          mapa.fitBounds([[cx[0], cx[1]], [cx[2], cx[3]]], { padding: 90, maxZoom: 15, duration: 1800 });
          mapa.once("moveend", function () { R.t = R.t0; tocar(Math.max(1, (R.t1 - R.t0) / 8)); });
        }
      });
  });
  // a troca de tema refaz o estilo com as cores do tema novo; só depois do 1º carregamento e só quando o tema MUDA (o
  // base.html regrava o mesmo data-tema ao abrir a página, e refazer o estilo no meio do carregamento o deixava vazio)
  var temaAtual = raiz.getAttribute("data-tema"), carregado = false;
  function trocarTema() {
    var t = raiz.getAttribute("data-tema");
    if (!carregado || t === temaAtual) return;
    temaAtual = t;
    P = paleta();
    mapa.setStyle(estilo(), { diff: false });
    mapa.once("style.load", nossas);
  }
  // a troca no meio do carregamento fica para o fim dele
  mapa.once("load", function () { carregado = true; trocarTema(); });
  new MutationObserver(trocarTema).observe(raiz, { attributes: true, attributeFilter: ["data-tema"] });

  // ── a dica, o clique e os botões ────────────────────────────────────────────────────────────────────────────────
  var porPid = {}, porUsina = {};
  D.tecnicos.forEach(function (t) { porPid[t.pid] = t; });
  D.usinas.forEach(function (u) { porUsina[u.id] = u; });
  function linha(tag, texto) {
    if (!texto) return;
    var e = document.createElement(tag); e.textContent = texto; dica.appendChild(e);
  }
  function mostrar(linhas, x, y) {
    dica.textContent = "";
    linha("b", linhas[0]); linha("span", linhas[1]); linha("small", linhas[2]); linha("small", linhas[3]);
    dica.hidden = false;
    var q = palco.getBoundingClientRect(), w = dica.offsetWidth, h = dica.offsetHeight;
    var esq = x + 14, topo = y + 14;
    if (esq + w > q.width - 6) esq = x - w - 10;
    if (topo + h > q.height - 6) topo = y - h - 10;
    dica.style.left = Math.max(6, esq) + "px";
    dica.style.top = Math.max(6, topo) + "px";
  }
  function esconder() { dica.hidden = true; }
  mapa.on("mousemove", "tecnicos", function (e) {
    var t = porPid[e.features[0].properties.pid];
    if (!t) return;
    mapa.getCanvas().style.cursor = "pointer";
    mostrar([t.nome, t.equipe || "sem equipe", t.rotulo + (t.velho ? " · última posição " + t.hora : ""),
             "Clique para ver o percurso do dia"], e.point.x, e.point.y);
  });
  mapa.on("mousemove", "usinas", function (e) {
    var u = porUsina[e.features[0].properties.id];
    if (!u) return;
    mapa.getCanvas().style.cursor = "pointer";
    var cos = u.agora ? "Agora (COS): " + u.agora.rotulo + (u.agora.motivo ? " · " + u.agora.motivo : "") : "";
    mostrar([u.nome, u.onde, cos, u.rotulo ? "Clima: " + u.rotulo + (u.motivo ? ": " + u.motivo : "") : ""], e.point.x, e.point.y);
  });
  ["tecnicos", "usinas"].forEach(function (id) {
    mapa.on("mouseleave", id, function () { mapa.getCanvas().style.cursor = ""; esconder(); });
  });
  mapa.on("dragstart", esconder);
  mapa.on("click", "tecnicos", function (e) {
    var t = porPid[e.features[0].properties.pid];
    if (t && t.url) location.href = t.url;
  });
  mapa.on("click", "usinas", function (e) {
    var c = e.features[0].geometry.coordinates;
    mapa.flyTo({ center: c, zoom: Math.max(mapa.getZoom(), 13), duration: REDUZIDO ? 300 : 900, essential: true });
  });
  quadro.addEventListener("click", function (e) {
    var f = e.target.closest("[data-eq-foco]");
    if (f) { foco = f.getAttribute("data-eq-foco"); guardar("nexus.equipe.foco", foco); aplicarFoco(); return; }
    var bb = e.target.closest("[data-eq-base]");
    if (bb) { fundoBase = bb.getAttribute("data-eq-base"); guardar("nexus.equipe.base", fundoBase); aplicarBase(); return; }
    var b = e.target.closest("[data-eq-zoom]");
    if (!b) return;
    var q = b.getAttribute("data-eq-zoom"), dur = REDUZIDO ? 200 : 450;
    if (q === "mais") mapa.zoomTo(mapa.getZoom() + 2, { duration: dur });
    else if (q === "menos") mapa.zoomTo(mapa.getZoom() - 2, { duration: dur });
    else if (q === "inteiro") mapa.fitBounds(BRASIL, { padding: 24, duration: dur });
    else if (q === "percurso" && D.percurso) {
      var cx = D.percurso.caixa;
      mapa.fitBounds([[cx[0], cx[1]], [cx[2], cx[3]]], { padding: 90, maxZoom: 15, duration: 900 });
    }
  });
})();
