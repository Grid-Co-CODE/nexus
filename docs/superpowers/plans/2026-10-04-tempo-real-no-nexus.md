# Tempo real no Nexus — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a aba Performance → Tempo real do Nexus mostra a Entrada e o Monitoramento inteiros da Plataforma de
Performance, só leitura, com o visual do Nexus, por uma ponte viva.

**Architecture:** o Nexus ganha uma ponte (`/t/performance/plataforma/<caminho>`) que leva cada pedido à plataforma
com uma chave só de leitura e o cabeçalho `X-Forwarded-Prefix`; a plataforma, que já sabe rodar debaixo de um caminho,
serve as páginas com o prefixo e recusa toda gravação feita com a chave. A ponte injeta no HTML o visual do Nexus e um
guarda que segura no navegador todo POST que grava.

**Tech Stack:** Python 3.14, Flask, requests (Nexus), pytest, node (testes de lógica JS da plataforma).

**Spec:** `docs/superpowers/specs/2026-10-04-tempo-real-no-nexus-design.md` (neste repositório, o Nexus).

## Global Constraints

- Dois repositórios: **PLATAFORMA** = `C:\Users\Levi Maia\OneDrive - GRID CO\Área de Trabalho\temp\Projeto API PV`
  (GitHub `Levi-6242/PerformancePainel`); **NEXUS** = `C:\Users\Levi Maia\OneDrive - GRID CO\Área de Trabalho\temp\Nexus`
  (GitHub `Grid-Co-CODE/nexus`). Cada tarefa diz em qual roda.
- Os dois repositórios são **públicos**: chave, senha, print ou dado real nunca entram em commit, teste ou log.
- **Em paralelo:** nada pode mudar o funcionamento atual da plataforma. Toda mudança nela é inofensiva sem a chave
  (`NEXUS_LEITURA_TOKEN` vazia) e sem prefixo (que é como ela roda hoje).
- Nomes fixos: na plataforma, variável `NEXUS_LEITURA_TOKEN` e cabeçalho `X-Nexus-Leitura`; no Nexus, opcionais
  `NEXUS_PLATAFORMA_URL` e `NEXUS_PLATAFORMA_TOKEN`; prefixo da ponte `/t/performance/plataforma`.
- POSTs de consulta (os únicos POSTs que passam): `/api/os-performance/counts`, `/api/os-creator/fractall-usinas`,
  `/api/etm/os`.
- Tempo-limite da ponte: **150 s**. A ponte tira o parâmetro `force` de todo pedido.
- Sempre pt-BR, inclusive comentário; comentário explica o porquê; sem emoji na interface; tema navy.
- **Commit:** só com o OK do Levi. Nos dois repositórios há trabalho de outras sessões sem commit: `git add` só dos
  arquivos e trechos desta tarefa (no `app.py` da plataforma, patch só dos próprios trechos — ver o `CLAUDE.md` raiz da
  plataforma). **Push na `main` da plataforma = deploy automático** (~4 min); só com o OK do Levi.
- Testes: PLATAFORMA `python -m pytest -q` na raiz; NEXUS `python -m pytest -q` na raiz.

---

## Mapa de arquivos

| Repositório | Arquivo | Responsabilidade |
|---|---|---|
| PLATAFORMA | `plataforma/leitura_nexus.py` (novo) | Lista fechada do que a chave de leitura alcança; `permitido(metodo, caminho)` |
| PLATAFORMA | `plataforma/app.py` | `NEXUS_LEITURA_TOKEN`; portão; `_SHIM_PREFIXO`; `_injeta_prefixo` |
| PLATAFORMA | `docs/redesign/Entrada.html` | Caminho sem prefixo; moldura do Monitoramento pelo calço |
| PLATAFORMA | `tests/test_leitura_nexus.py` (novo) | Lista, portão, cobertura das rotas das páginas |
| PLATAFORMA | `tests/test_prefixo_subcaminho.py` (novo) | Atributos com prefixo, calço, caminho da Entrada (node) |
| PLATAFORMA | `plataforma/CLAUDE.md`, `docs/tempo-real.md` | O porquê e o como provar |
| NEXUS | `nexus/config.py`, `.env.example` | Opcionais da ponte |
| NEXUS | `nexus/performance/__init__.py`, `nexus/performance/ponte.py` (novos) | Regra da ponte, sem Flask |
| NEXUS | `nexus/performance/CLAUDE.md` (novo) | O porquê, a lista, como provar |
| NEXUS | `nexus/torres/performance/__init__.py` | Rotas `/tempo-real` e `/plataforma/<caminho>` |
| NEXUS | `nexus/torres/performance/templates/performance/tempo_real.html` (novo) | Casca + faixa + moldura |
| NEXUS | `nexus/torres/performance/CLAUDE.md` (novo) | Tela por tela da torre |
| NEXUS | `nexus/static/nexus.css` | Classes `.ponte-*` da faixa e da moldura |
| NEXUS | `tests/test_performance_ponte.py`, `tests/test_torre_performance.py` (novos) | Regra e rotas |
| NEXUS | `CLAUDE.md`, `nexus/torres/CLAUDE.md`, `DEPLOY.md` | Tabelas de área e variáveis |

---

### Task 1 (PLATAFORMA): lista do que a chave de leitura alcança

**Files:**
- Create: `plataforma/leitura_nexus.py`
- Test: `tests/test_leitura_nexus.py`

**Interfaces:**
- Produces: `leitura_nexus.permitido(metodo: str, caminho: str) -> bool`; constantes `POSTS_DE_CONSULTA: frozenset[str]`,
  `GRAVACOES: tuple[str, ...]`, `FONTES_API: tuple[str, ...]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_leitura_nexus.py
# -*- coding: utf-8 -*-
"""A chave de leitura do Nexus (04/10/2026): o Nexus mostra a Entrada e o Monitoramento da plataforma por uma ponte, só
leitura. Esta lista diz o que a chave alcança; todo o resto, com ela, é 403."""
import leitura_nexus as ln


def test_paginas_do_tempo_real_passam():
    for c in ("/tempo-real", "/tempo-real/athon", "/monitor"):
        assert ln.permitido("GET", c), c
    assert not ln.permitido("GET", "/")              # a Entrada nível 1 leva a Painel, OS, Gerencial: fora deste passo
    assert not ln.permitido("GET", "/painel")


def test_leitura_das_fontes_passa():
    for f in ln.FONTES_API:
        assert ln.permitido("GET", f"/api/{f}/trackers/parados"), f
    for c in ("/api/state", "/api/entrada/tempo-real", "/api/spv/usina/123", "/api/etm/chart", "/api/notificacoes",
              "/api/strings/tickets/12/os", "/api/plant/MAB100", "/api/os-performance", "/api/data"):
        assert ln.permitido("GET", c), c
    assert ln.permitido("HEAD", "/api/state")


def test_so_os_tres_posts_de_consulta_passam():
    for c in ("/api/os-performance/counts", "/api/os-creator/fractall-usinas", "/api/etm/os"):
        assert ln.permitido("POST", c), c
    for c in ln.GRAVACOES:
        assert not ln.permitido("POST", c.rstrip("/") + ("/1/salvar" if c.endswith("/") else "")), c


def test_o_que_nao_e_do_tempo_real_fica_fora():
    for c in ("/api/tokens", "/api/ronda/whats/preview", "/api/tracker-watch/update", "/login", "/api/macro"):
        assert not ln.permitido("GET", c), c
    assert not ln.permitido("DELETE", "/api/state")
    assert not ln.permitido("PUT", "/api/state")
    assert not ln.permitido("GET", "/api/datax")      # prefixo sem barra não vaza para rota vizinha
```

- [ ] **Step 2: Run test to verify it fails**

Run (PLATAFORMA): `python -m pytest -q tests/test_leitura_nexus.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'leitura_nexus'`

- [ ] **Step 3: Write minimal implementation**

```python
# plataforma/leitura_nexus.py
# -*- coding: utf-8 -*-
"""O que a chave de leitura do Nexus alcança (04/10/2026).

O Nexus mostra a Entrada e o Monitoramento desta plataforma por uma ponte, só leitura (Levi: "tudo da plataforma, só
leitura", "em paralelo por enquanto"). A ponte manda `X-Nexus-Leitura: <NEXUS_LEITURA_TOKEN>`; com ela, o `_auth_gate`
deixa passar só o que `permitido` aceita e devolve 403 para o resto. A lista é FECHADA de propósito: a chave não
alcança `/api/tokens`, a ronda, a coleta nem nada que dispare trabalho pesado. O teste
`test_a_lista_cobre_as_rotas_das_paginas` confere esta lista contra as rotas citadas nas duas páginas: rota nova numa
página quebra o teste, em vez de a aba do Nexus ficar em branco calada.
"""

# as fontes do Monitoramento (o `/api/'+f+'/...` dinâmico das páginas)
FONTES_API = ("pv", "pg", "sunop", "axis", "solaredge", "owen", "2capi", "semp", "alveslima")

# páginas: o nível 2 e 3 da Entrada e o Monitoramento embutido
_PAGINAS = ("/tempo-real", "/monitor")

# leituras que as páginas fazem (GET/HEAD); "x" casa "x" e "x/..."
_GET = tuple(f"/api/{f}" for f in FONTES_API) + (
    "/api/state", "/api/entrada/tempo-real", "/api/notificacoes", "/api/data", "/api/plant", "/api/spv", "/api/etm",
    "/api/perdas", "/api/trackers", "/api/strings", "/api/fracttal/ultima-os", "/api/os-abertas", "/api/os-performance",
)

# POSTs que só consultam (corpo com a lista de usinas): contagem de OS, de-para do Fracttal, OS da ETM
POSTS_DE_CONSULTA = frozenset({"/api/os-performance/counts", "/api/os-creator/fractall-usinas", "/api/etm/os"})

# o que as páginas gravam (documentação e teste): com a chave, tudo isto é 403
GRAVACOES = (
    "/api/state/string-trancada", "/api/state/comment/add", "/api/state/comment/del", "/api/state/os-atribuir",
    "/api/state/os-desatribuir", "/api/state/usina-desligada", "/api/state/usina-religada", "/api/state/tracking",
    "/api/strings/tickets/", "/api/entrada/tempo-real/atualizar", "/api/notificacoes/ler-agora",
)


def _casa(caminho: str, base: str) -> bool:
    return caminho == base or caminho.startswith(base + "/")


def permitido(metodo: str, caminho: str) -> bool:
    m = (metodo or "").upper()
    c = (caminho or "").split("?", 1)[0].rstrip("/") or "/"
    if m == "POST":
        return c in POSTS_DE_CONSULTA
    if m not in ("GET", "HEAD"):
        return False
    return any(_casa(c, b) for b in _PAGINAS + _GET)
```

- [ ] **Step 4: Run test to verify it passes**

Run (PLATAFORMA): `python -m pytest -q tests/test_leitura_nexus.py`
Expected: PASS (4 testes). `/api/sunop/uso` passa por estar debaixo de `/api/sunop` — leitura barata, aceito.

- [ ] **Step 5: Commit** (com o OK do Levi)

```bash
git add plataforma/leitura_nexus.py tests/test_leitura_nexus.py
git commit -m "feat(nexus): lista fechada do que a chave de leitura do Nexus alcanca"
```

---

### Task 2 (PLATAFORMA): o portão aceita a chave de leitura

**Files:**
- Modify: `plataforma/app.py` — junto de `DASH_PASSWORD = os.environ.get(...)` e no começo de `_auth_gate`
- Test: `tests/test_leitura_nexus.py` (acrescentar)

**Interfaces:**
- Consumes: `leitura_nexus.permitido` (Task 1).
- Produces: variável de módulo `app.NEXUS_LEITURA_TOKEN: str` (vazia = desligada).

- [ ] **Step 1: Write the failing test**

```python
# acrescentar em tests/test_leitura_nexus.py
import pytest

import app

CHAVE = "chave-de-teste-nexus"


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(app, "DASH_PASSWORD", "senha-qualquer")
    monkeypatch.setattr(app, "NEXUS_LEITURA_TOKEN", CHAVE)
    return app.app.test_client()


def test_chave_certa_le(cli):
    r = cli.get("/api/state", headers={"X-Nexus-Leitura": CHAVE})
    assert r.status_code == 200


def test_chave_certa_nao_grava(cli):
    r = cli.post("/api/state/tracking", json={"key": "pv:1", "value": 3}, headers={"X-Nexus-Leitura": CHAVE})
    assert r.status_code == 403 and r.get_json()["error"] == "somente leitura (Nexus)"


def test_chave_certa_nao_sai_da_lista(cli):
    assert cli.get("/api/tokens", headers={"X-Nexus-Leitura": CHAVE}).status_code == 403


def test_chave_errada_e_recusada(cli):
    r = cli.get("/api/state", headers={"X-Nexus-Leitura": "outra"})
    assert r.status_code == 401 and "chave" in r.get_json()["error"]


def test_sem_chave_configurada_o_cabecalho_nao_abre_nada(cli, monkeypatch):
    monkeypatch.setattr(app, "NEXUS_LEITURA_TOKEN", "")
    assert cli.get("/api/state", headers={"X-Nexus-Leitura": ""}).status_code == 401   # sem sessão: como hoje


def test_plataforma_aberta_tambem_recusa_gravacao_pela_chave(cli, monkeypatch):
    # DASH_PASSWORD vazia = plataforma aberta (uso local); mesmo assim, quem chega pela chave do Nexus só lê
    monkeypatch.setattr(app, "DASH_PASSWORD", "")
    r = cli.post("/api/state/tracking", json={}, headers={"X-Nexus-Leitura": CHAVE})
    assert r.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run (PLATAFORMA): `python -m pytest -q tests/test_leitura_nexus.py`
Expected: FAIL — `AttributeError: module 'app' has no attribute 'NEXUS_LEITURA_TOKEN'` (o monkeypatch exige o nome).

- [ ] **Step 3: Write minimal implementation**

Logo abaixo da linha `DASH_PASSWORD = os.environ.get("DASH_PASSWORD", "").strip()`:

```python
# Chave só de leitura do Nexus (04/10/2026). O Nexus mostra a Entrada e o Monitoramento por uma ponte que manda
# `X-Nexus-Leitura`; com a chave certa passa só o que `leitura_nexus.permitido` aceita, e gravação é 403. Vazia =
# desligada (o cabeçalho é ignorado). Mora no .env/tokens.txt, nunca no git — os dois repositórios são públicos.
NEXUS_LEITURA_TOKEN = os.environ.get("NEXUS_LEITURA_TOKEN", "").strip()
```

No começo de `_auth_gate`, ANTES de `if not DASH_PASSWORD:` (a plataforma aberta também precisa recusar gravação
pela chave):

```python
    chave_nexus = flask_request.headers.get("X-Nexus-Leitura")
    if chave_nexus is not None and NEXUS_LEITURA_TOKEN:
        import leitura_nexus
        if not secrets.compare_digest(chave_nexus.encode(), NEXUS_LEITURA_TOKEN.encode()):
            return jsonify({"error": "chave de leitura recusada"}), 401
        if leitura_nexus.permitido(flask_request.method, flask_request.path):
            return
        return jsonify({"error": "somente leitura (Nexus)"}), 403
```

(`secrets` já é importado no bloco do `DASH_PASSWORD`: `import hashlib, secrets, base64`. O `_auth_gate` é definido
depois desse bloco.)

- [ ] **Step 4: Run test to verify it passes**

Run (PLATAFORMA): `python -m pytest -q tests/test_leitura_nexus.py tests/test_auth*.py`
Expected: PASS. Se não houver `tests/test_auth*.py`, rode só o primeiro arquivo.

- [ ] **Step 5: Commit** (com o OK do Levi; patch só destes trechos do `app.py`)

```bash
git add tests/test_leitura_nexus.py
# app.py: só os dois trechos desta tarefa (ver "Sessões paralelas" no CLAUDE.md raiz)
git commit -m "feat(nexus): o portao aceita a chave so de leitura do Nexus e recusa gravacao com 403"
```

---

### Task 3 (PLATAFORMA): a lista cobre as rotas das páginas

**Files:**
- Test: `tests/test_leitura_nexus.py` (acrescentar)

**Interfaces:**
- Consumes: `leitura_nexus.permitido`, `POSTS_DE_CONSULTA`, `GRAVACOES`, `FONTES_API`.

- [ ] **Step 1: Write the test**

```python
# acrescentar em tests/test_leitura_nexus.py
import pathlib
import re

RAIZ = pathlib.Path(app.__file__).resolve().parents[1]
PAGINAS = [RAIZ / "docs" / "redesign" / "Entrada.html", RAIZ / "docs" / "redesign" / "Monitoramento (novo design).html",
           RAIZ / "plataforma" / "static" / "notif.js"]


def test_a_lista_cobre_as_rotas_das_paginas():
    """Rota nova numa página do tempo real precisa ser classificada aqui: leitura (entra na lista), consulta por POST
    ou gravação. Sem isso, a aba do Nexus quebra calada."""
    soltas = set()
    for p in PAGINAS:
        for rota in re.findall(r"/api/[A-Za-z0-9_\-/]+", p.read_text(encoding="utf-8")):
            rota = rota.rstrip("/")
            if rota == "/api":
                continue                                     # '/api/'+f+... : coberto pelas FONTES_API
            if ln.permitido("GET", rota) or ln.permitido("POST", rota):
                continue
            if any(rota == g.rstrip("/") or rota.startswith(g) for g in ln.GRAVACOES):
                continue
            soltas.add(rota)
    assert not soltas, f"rotas das páginas fora da lista do Nexus: {sorted(soltas)}"
```

- [ ] **Step 2: Run test**

Run (PLATAFORMA): `python -m pytest -q tests/test_leitura_nexus.py::test_a_lista_cobre_as_rotas_das_paginas`
Expected: PASS. Se falhar, a mensagem lista as rotas soltas: classifique cada uma no `leitura_nexus.py` (leitura em
`_GET`, consulta em `POSTS_DE_CONSULTA`, gravação em `GRAVACOES`), lendo a rota no `app.py` para saber o método e se
grava. Não afrouxe o teste.

- [ ] **Step 3: Commit** (com o OK do Levi)

```bash
git add tests/test_leitura_nexus.py plataforma/leitura_nexus.py
git commit -m "test(nexus): a lista de leitura do Nexus cobre todas as rotas da Entrada e do Monitoramento"
```

---

### Task 4 (PLATAFORMA): o modo sub-caminho cobre atributos, links criados depois e window.open

**Files:**
- Modify: `plataforma/app.py` — `_SHIM_PREFIXO` e `_injeta_prefixo`
- Test: `tests/test_prefixo_subcaminho.py` (novo)

**Interfaces:**
- Produces: HTML servido com `X-Forwarded-Prefix: <p>` tem `src|href|action="<p>/..."` nos absolutos; `window.__pfx`
  segue existindo; o calço corrige `<a>` no clique e o `window.open`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_prefixo_subcaminho.py
# -*- coding: utf-8 -*-
"""A plataforma debaixo de um caminho (X-Forwarded-Prefix): a ponte do Nexus (04/10/2026) e o sub-caminho da T.I.

Até aqui o calço (`_SHIM_PREFIXO`) corrigia fetch, XHR e os <a> presentes na carga. Ficavam de fora o
<script src="/static/notif.js">, o logo e os links escritos no HTML (a raiz do domínio, debaixo do Nexus, é o
Nexus), o link que o JavaScript cria depois da carga e o window.open."""
import pytest

import app

P = "/t/performance/plataforma"


@pytest.fixture
def cli(monkeypatch):
    monkeypatch.setattr(app, "DASH_PASSWORD", "")
    return app.app.test_client()


def test_atributos_absolutos_ganham_o_prefixo(cli):
    html = cli.get("/tempo-real", headers={"X-Forwarded-Prefix": P}).get_data(as_text=True)
    assert f'src="{P}/static/notif.js"' in html
    assert 'src="/static/' not in html and 'href="/tempo-real"' not in html
    assert f'{P}{P}/' not in html                           # nada em dobro


def test_sem_prefixo_o_html_sai_como_hoje(cli):
    html = cli.get("/tempo-real").get_data(as_text=True)
    assert 'src="/static/notif.js"' in html and "window.__pfx" not in html


def test_calco_corrige_link_no_clique_e_window_open(cli):
    html = cli.get("/tempo-real", headers={"X-Forwarded-Prefix": P}).get_data(as_text=True)
    assert "addEventListener('click'" in html and "window.open=function" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run (PLATAFORMA): `python -m pytest -q tests/test_prefixo_subcaminho.py`
Expected: FAIL em `test_atributos_absolutos_ganham_o_prefixo` e `test_calco_corrige_link_no_clique_e_window_open`.

- [ ] **Step 3: Write minimal implementation**

No `_SHIM_PREFIXO`, troque a última parte (do `document.addEventListener('DOMContentLoaded'` até o fim) por:

```python
document.addEventListener('DOMContentLoaded',function(){
document.querySelectorAll('a[href^="/"],form[action^="/"]').forEach(function(el){
var a=el.tagName==='A'?'href':'action';el.setAttribute(a,fix(el.getAttribute(a)));});});
function noClique(e){var a=e.target&&e.target.closest?e.target.closest('a[href^="/"]'):null;
if(a)a.setAttribute('href',fix(a.getAttribute('href')));}
document.addEventListener('click',noClique,true);document.addEventListener('auxclick',noClique,true);
var _wo=window.open;window.open=function(u){arguments[0]=fix(u);return _wo.apply(window,arguments);};
})();</script>"""
```

No `_injeta_prefixo`, depois de `html = resp.get_data(as_text=True)`:

```python
        # Atributos absolutos escritos no HTML (04/10/2026): o <script src="/static/notif.js">, o logo e os links da
        # Entrada pediam a raiz do domínio. Debaixo da ponte do Nexus a raiz é o Nexus, e o sino nem carregava. O
        # calço só pega o que roda depois; isto pega o que já vem escrito. `(?!/)` deixa o "//host" em paz e o
        # lookahead do prefixo impede a dobra.
        ja = re.escape(pref.lstrip("/")) + "/"
        html = re.sub(r'(\s(?:src|href|action)=)(["\'])/(?!/|' + ja + ")", r"\1\2" + pref + "/", html)
```

- [ ] **Step 4: Run test to verify it passes**

Run (PLATAFORMA): `python -m pytest -q tests/test_prefixo_subcaminho.py tests/test_gemeo_proxy.py tests/test_os_web_proxy.py`
Expected: PASS.

- [ ] **Step 5: Commit** (com o OK do Levi; patch só destes trechos)

```bash
git add tests/test_prefixo_subcaminho.py
git commit -m "fix(prefixo): atributos absolutos, link criado depois da carga e window.open debaixo de sub-caminho"
```

---

### Task 5 (PLATAFORMA): a Entrada abre o nível 2 e 3 debaixo de prefixo

**Files:**
- Modify: `docs/redesign/Entrada.html` — o bloco "niveis 2 e 3" (hoje `var partes = location.pathname...`) e os
  dois `fr.src = "/monitor?..."`
- Test: `tests/test_prefixo_subcaminho.py` (acrescentar, node)

**Interfaces:**
- Produces: função JS `_partesDoCaminho(caminho, pfx)` → array de segmentos sem o prefixo, delimitada por
  `/* fim _partesDoCaminho */`.

- [ ] **Step 1: Write the failing test**

```python
# acrescentar em tests/test_prefixo_subcaminho.py
import json
import pathlib
import shutil
import subprocess

ENTRADA = (pathlib.Path(app.__file__).resolve().parents[1] / "docs" / "redesign" / "Entrada.html").read_text(
    encoding="utf-8")


def _roda_js(expr):
    node = shutil.which("node")
    if not node:
        pytest.skip("node não instalado")
    i = ENTRADA.index("function _partesDoCaminho(")
    fim = "/* fim _partesDoCaminho */"
    js = ENTRADA[i:ENTRADA.index(fim, i) + len(fim)] + "\nprocess.stdout.write(JSON.stringify(" + expr + "));"
    r = subprocess.run([node, "-e", js], capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def test_entrada_le_o_nivel_sem_o_prefixo():
    assert _roda_js(f"_partesDoCaminho('{P}/tempo-real/athon/', '{P}')") == ["tempo-real", "athon"]
    assert _roda_js("_partesDoCaminho('/tempo-real', '')") == ["tempo-real"]
    assert _roda_js(f"_partesDoCaminho('/tempo-real', '{P}')") == ["tempo-real"]     # sem o prefixo no caminho


def test_moldura_do_monitoramento_passa_pelo_calco():
    assert ENTRADA.count('fr.src = "/monitor?') == 0
    assert ENTRADA.count('_pfxUrl("/monitor?') == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run (PLATAFORMA): `python -m pytest -q tests/test_prefixo_subcaminho.py -k "entrada or moldura"`
Expected: FAIL — `ValueError: substring not found` e a contagem de `fr.src`.

- [ ] **Step 3: Write minimal implementation**

No `Entrada.html`, logo ANTES do comentário `// ── niveis 2 e 3: /tempo-real e /tempo-real/<fonte>`, dentro do mesmo
`<script>`:

```js
  // Os segmentos do caminho SEM o prefixo de sub-caminho (04/10/2026): debaixo da ponte do Nexus (e do sub-caminho da
  // T.I.) o caminho é "/t/performance/plataforma/tempo-real/athon", e o nível 2 e o 3 não abriam porque o 1º segmento
  // era "t". window.APP_PREFIX vem do calço da plataforma (vazio na raiz).
  function _partesDoCaminho(caminho, pfx) {
    var c = String(caminho || "/");
    if (pfx && c.indexOf(pfx + "/") === 0) c = c.slice(pfx.length);
    return c.replace(/\/+$/, "").split("/").filter(Boolean);
  }
  /* fim _partesDoCaminho */
  var _pfxUrl = window.__pfx || function (u) { return u; };
```

E troque:
- `var partes = location.pathname.replace(/\/+$/, "").split("/").filter(Boolean);` →
  `var partes = _partesDoCaminho(location.pathname, window.APP_PREFIX || "");`
- `fr.src = "/monitor?fonte=" + encodeURIComponent(fonteSel) + "&embed=1&view=" + viewSel + fundo;` →
  `fr.src = _pfxUrl("/monitor?fonte=" + encodeURIComponent(fonteSel) + "&embed=1&view=" + viewSel + fundo);`
- `else fr.src = "/monitor?fonte=" + encodeURIComponent(fonteSel) + "&embed=1&view=" + id;` →
  `else fr.src = _pfxUrl("/monitor?fonte=" + encodeURIComponent(fonteSel) + "&embed=1&view=" + id);`

- [ ] **Step 4: Run test to verify it passes**

Run (PLATAFORMA): `python -m pytest -q tests/test_prefixo_subcaminho.py` e depois a suíte inteira, `python -m pytest -q`
Expected: PASS em tudo. (O HTML é relido sem restart; conferir também `http://127.0.0.1:5050/tempo-real/athon` como hoje.)

- [ ] **Step 5: Commit** (com o OK do Levi)

```bash
git add docs/redesign/Entrada.html tests/test_prefixo_subcaminho.py
git commit -m "fix(entrada): nivel 2 e 3 e a moldura do Monitoramento debaixo de sub-caminho"
```

---

### Task 6 (PLATAFORMA): documentação

**Files:**
- Modify: `plataforma/CLAUDE.md` (nova seção curta "Ponte do Nexus: chave só de leitura e sub-caminho"),
  `docs/tempo-real.md` (linha na tabela "Onde fica": `plataforma/leitura_nexus.py`)

- [ ] **Step 1:** Em `plataforma/CLAUDE.md`, depois da seção "Arquitetura de cache", acrescente:

```markdown
## Ponte do Nexus: chave só de leitura e sub-caminho (04/10/2026)

O Nexus (`Grid-Co-CODE/nexus`, torre Performance → Tempo real) mostra a Entrada e o Monitoramento desta plataforma por
uma ponte, só leitura (Levi: "tudo da plataforma, só leitura", "em paralelo por enquanto"; a meta é a plataforma morar
100% no Nexus). A ponte manda `X-Nexus-Leitura` (= `NEXUS_LEITURA_TOKEN`, no `.env`/tokens.txt, nunca no git) e
`X-Forwarded-Prefix: /t/performance/plataforma`. Com a chave, o `_auth_gate` deixa passar só o que
`leitura_nexus.permitido` aceita (páginas do tempo real, leituras das fontes e 3 POSTs de consulta); gravação é 403,
mesmo com a plataforma aberta. **Rota nova numa página do tempo real precisa entrar na lista** —
`test_a_lista_cobre_as_rotas_das_paginas` quebra se não entrar. O modo sub-caminho passou a pôr o prefixo nos
atributos `src`/`href`/`action` do HTML, nos links criados depois da carga e no `window.open`; a Entrada lê o nível
pelo caminho sem o prefixo (`_partesDoCaminho`). Sem chave e sem prefixo, nada muda. Testes:
`tests/test_leitura_nexus.py`, `tests/test_prefixo_subcaminho.py`.
```

- [ ] **Step 2:** Em `docs/tempo-real.md`, na tabela da seção 2, acrescente a linha:

```markdown
| Chave de leitura do Nexus | `plataforma/leitura_nexus.py` | O que a ponte do Nexus pode ler; gravação com a chave é 403 (ver `plataforma/CLAUDE.md`). |
```

- [ ] **Step 3: Commit** (com o OK do Levi)

```bash
git add plataforma/CLAUDE.md docs/tempo-real.md
git commit -m "docs(nexus): ponte do Nexus, chave so de leitura e sub-caminho"
```

---

### Task 7 (NEXUS): configuração da ponte

**Files:**
- Modify: `nexus/config.py` (tupla `OPCIONAIS`), `.env.example`
- Test: `tests/test_config.py` (acrescentar)

**Interfaces:**
- Produces: `app.config["NEXUS_PLATAFORMA_URL"]` e `app.config["NEXUS_PLATAFORMA_TOKEN"]` quando presentes.

- [ ] **Step 1: Write the failing test**

```python
# acrescentar em tests/test_config.py
from nexus.config import OPCIONAIS


def test_a_ponte_da_plataforma_e_opcional():
    assert "NEXUS_PLATAFORMA_URL" in OPCIONAIS and "NEXUS_PLATAFORMA_TOKEN" in OPCIONAIS
```

- [ ] **Step 2: Run test to verify it fails**

Run (NEXUS): `python -m pytest -q tests/test_config.py`
Expected: FAIL no assert.

- [ ] **Step 3: Write minimal implementation**

Em `nexus/config.py`, no fim da tupla `OPCIONAIS`:

```python
             # aba Tempo real (04/10/2026): onde está a plataforma de Performance e a chave só de leitura dela
             "NEXUS_PLATAFORMA_URL", "NEXUS_PLATAFORMA_TOKEN")
```

(Troque o `)` final de `"GRIDCO_SQL_TOKEN", "GRIDCO_DB_API")` por `,` e acrescente as duas linhas acima.)

No `.env.example`, no fim:

```
# Aba Performance -> Tempo real: a plataforma de Performance e a chave so de leitura (a mesma NEXUS_LEITURA_TOKEN
# do .env/tokens.txt da plataforma). Local: http://127.0.0.1:5050 ; servidor: https://app.gridco.com.br
NEXUS_PLATAFORMA_URL=
NEXUS_PLATAFORMA_TOKEN=
```

- [ ] **Step 4: Run test to verify it passes**

Run (NEXUS): `python -m pytest -q tests/test_config.py`
Expected: PASS.

- [ ] **Step 5: Commit** (com o OK do Levi)

```bash
git add nexus/config.py .env.example tests/test_config.py
git commit -m "feat(performance): configuracao da ponte da plataforma (opcional)"
```

---

### Task 8 (NEXUS): a regra da ponte

**Files:**
- Create: `nexus/performance/__init__.py` (vazio, só a docstring), `nexus/performance/ponte.py`
- Test: `tests/test_performance_ponte.py`

**Interfaces:**
- Produces (em `nexus.performance.ponte`):
  - `PREFIXO = "/t/performance/plataforma"`; `TEMPO_LIMITE_S = 150`; `POSTS_DE_CONSULTA: frozenset[str]`
  - `pode_passar(metodo: str, caminho: str) -> bool` — `caminho` sem o prefixo, começando em `/`
  - `montar_pedido(base_url: str, token: str, metodo: str, caminho: str, query: list[tuple[str, str]], corpo: bytes | None, tipo: str | None) -> dict` — kwargs de `requests.request`
  - `ajustar_resposta(status: int, cabecalhos: dict, corpo: bytes) -> tuple[int, dict, bytes]`
  - `injetar(html: str) -> str`
  - `enviar(**pedido) -> requests.Response` — o único ponto que fala com a rede (os testes trocam)
  - `class ForaDoAr(Exception)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_performance_ponte.py
"""Ponte do Nexus para a plataforma de Performance (04/10/2026): só leitura, com o visual do Nexus."""
from nexus.performance import ponte as pt


def test_so_leitura_e_os_tres_posts_de_consulta_passam():
    assert pt.pode_passar("GET", "/api/sunop/data")
    assert pt.pode_passar("HEAD", "/tempo-real")
    for c in ("/api/os-performance/counts", "/api/os-creator/fractall-usinas", "/api/etm/os"):
        assert pt.pode_passar("POST", c), c
    assert not pt.pode_passar("POST", "/api/state/tracking")
    assert not pt.pode_passar("DELETE", "/api/state")


def test_pedido_leva_a_chave_o_prefixo_e_tira_o_force():
    p = pt.montar_pedido("http://plat:5050/", "k", "GET", "/api/pv/trackers/parados",
                         [("force", "1"), ("data", "2026-10-04")], None, None)
    assert p["url"] == "http://plat:5050/api/pv/trackers/parados"
    assert p["params"] == [("data", "2026-10-04")]
    assert p["headers"]["X-Nexus-Leitura"] == "k"
    assert p["headers"]["X-Forwarded-Prefix"] == pt.PREFIXO
    assert "Cookie" not in p["headers"]
    assert p["timeout"] == pt.TEMPO_LIMITE_S and p["allow_redirects"] is True


def test_post_de_consulta_leva_o_corpo_e_o_tipo():
    p = pt.montar_pedido("http://plat", "k", "POST", "/api/etm/os", [], b'{"usinas":["A"]}', "application/json")
    assert p["data"] == b'{"usinas":["A"]}' and p["headers"]["Content-Type"] == "application/json"


def test_resposta_sem_cookie_e_sem_cabecalho_de_salto():
    st, cab, corpo = pt.ajustar_resposta(200, {"Content-Type": "application/json", "Set-Cookie": "s=1",
                                               "Content-Length": "9", "Content-Encoding": "gzip",
                                               "Transfer-Encoding": "chunked", "Connection": "keep-alive",
                                               "Content-Disposition": "attachment; filename=x.csv"}, b"{}")
    assert st == 200 and corpo == b"{}"
    assert set(cab) == {"Content-Type", "Content-Disposition"}


def test_html_ganha_o_visual_e_o_guarda_de_leitura():
    st, cab, corpo = pt.ajustar_resposta(200, {"Content-Type": "text/html; charset=utf-8"},
                                         "<html><head><title>x</title></head><body></body></html>".encode())
    html = corpo.decode("utf-8")
    assert html.index('id="nexus-visual"') < html.index("</head>")
    assert 'id="nexus-leitura"' in html and "Somente leitura no Nexus" in html
    assert "/api/etm/os" in html                         # a lista de consulta vai ao guarda do navegador


def test_html_sem_head_tambem_recebe():
    assert 'id="nexus-leitura"' in pt.injetar("<body>x</body>")
```

- [ ] **Step 2: Run test to verify it fails**

Run (NEXUS): `python -m pytest -q tests/test_performance_ponte.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'nexus.performance'`

- [ ] **Step 3: Write minimal implementation**

```python
# nexus/performance/__init__.py
"""Regra da torre Performance, sem Flask (padrão de nexus/cadastro e nexus/pcm). Ver CLAUDE.md desta pasta."""
```

```python
# nexus/performance/ponte.py
"""Ponte do Nexus para a Plataforma de Performance (04/10/2026).

Levi: "tudo da plataforma, só leitura", "em paralelo por enquanto", e a meta de a plataforma morar 100% no Nexus. A
aba Performance → Tempo real mostra a Entrada e o Monitoramento da própria plataforma: o navegador fala só com o Nexus,
e esta ponte leva cada pedido à plataforma com a chave só de leitura (`X-Nexus-Leitura`) e o prefixo
(`X-Forwarded-Prefix`). A plataforma já sabe rodar debaixo de um caminho e devolve as páginas com o prefixo, então as
chamadas delas voltam para cá sem reescrever HTML. Aqui só se acrescenta o visual do Nexus e o guarda de leitura.

Só leitura em três camadas: o portão da plataforma (403 para gravação com a chave), `pode_passar` aqui, e o guarda no
navegador. Sem Flask: a rota está em nexus/torres/performance.
"""
import json

import requests

PREFIXO = "/t/performance/plataforma"
# O drill da API PV leva até 120 s na plataforma (24/09/2026, API PV lenta); 150 s cobre sem prender para sempre.
TEMPO_LIMITE_S = 150
# os únicos POSTs que passam: consultas com a lista de usinas no corpo (a mesma lista do leitura_nexus da plataforma)
POSTS_DE_CONSULTA = frozenset({"/api/os-performance/counts", "/api/os-creator/fractall-usinas", "/api/etm/os"})
# cabeçalhos que a plataforma devolve e o navegador pode ver; o resto (Set-Cookie, salto, tamanho) fica aqui
_CABECALHOS_QUE_PASSAM = ("Content-Type", "Content-Disposition", "Cache-Control", "Last-Modified", "ETag")


class ForaDoAr(Exception):
    """A plataforma não respondeu (rede, tempo-limite)."""


def pode_passar(metodo: str, caminho: str) -> bool:
    m = (metodo or "").upper()
    if m in ("GET", "HEAD"):
        return True
    return m == "POST" and (caminho or "").split("?", 1)[0].rstrip("/") in POSTS_DE_CONSULTA


def montar_pedido(base_url, token, metodo, caminho, query, corpo, tipo) -> dict:
    # `force=1` refaz na hora o que o motor monta sozinho (no "Atualizar" dos trackers, curvas novas na SunOp): pelo
    # Nexus, ler é ler o que já está pronto
    params = [(k, v) for k, v in (query or []) if k != "force"]
    cab = {"X-Nexus-Leitura": token, "X-Forwarded-Prefix": PREFIXO, "Accept": "*/*", "User-Agent": "nexus-ponte"}
    pedido = {"method": metodo.upper(), "url": base_url.rstrip("/") + caminho, "params": params, "headers": cab,
              "timeout": TEMPO_LIMITE_S, "allow_redirects": True}
    if corpo is not None and pedido["method"] == "POST":
        pedido["data"] = corpo
        if tipo:
            cab["Content-Type"] = tipo
    return pedido


def ajustar_resposta(status, cabecalhos, corpo):
    cab = {k: v for k, v in (cabecalhos or {}).items() if k in _CABECALHOS_QUE_PASSAM}
    if str(cab.get("Content-Type", "")).startswith("text/html"):
        corpo = injetar(corpo.decode("utf-8", "replace")).encode("utf-8")
    return status, cab, corpo


# O visual do Nexus por cima (mesmo Design System; muda a fonte, o fundo e some com o topo próprio da plataforma —
# o topo do Nexus já está na casca). O "‹ Entrada" leva ao nível 1 (Painel, OS, Gerencial), fora deste passo.
_VISUAL = """<link href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700&display=swap" rel="stylesheet">
<style id="nexus-visual">
body,button,input,select,textarea{font-family:"Poppins",system-ui,-apple-system,"Segoe UI",sans-serif!important}
body{background-image:none!important}
.topo,.pe,a.volta[href$="/plataforma/"],button.atualiza,[data-atualizar]{display:none!important}
[onclick*="trancarString"],[onclick*="excluirComent"],[onclick*="gcDesatribuirOS"],[onclick*="gcUsinaReligada"],
[onchange*="setTracking"],[oninput*="setTracking"]{display:none!important}
#nexus-leitura-aviso{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:99999;background:#161d30;
  color:#e9eef6;border:1px solid rgba(255,216,61,.5);border-radius:10px;padding:10px 16px;font:500 13px/1.4 "Poppins",sans-serif;
  box-shadow:0 10px 30px rgba(0,0,0,.45)}
</style>"""

# O guarda do navegador: todo POST que grava não sai e vira um 403 com aviso. Roda depois do calço da plataforma (que
# fica no topo do <head>), então recebe o caminho já com o prefixo e o tira para comparar.
_GUARDA = """<script id="nexus-leitura">(function(){var CONSULTA=%s,P=%s,_f=window.fetch;
function aviso(){var d=document.getElementById('nexus-leitura-aviso');if(!d){d=document.createElement('div');
d.id='nexus-leitura-aviso';document.body.appendChild(d);}d.textContent='Somente leitura no Nexus: faça isto na plataforma.';
clearTimeout(d._t);d.style.display='block';d._t=setTimeout(function(){d.style.display='none';},4000);}
if(_f)window.fetch=function(u,o){var m=((o&&o.method)||'GET').toUpperCase();
if(m!=='GET'&&m!=='HEAD'){var c=String(typeof u==='string'?u:(u&&u.url)||'').split('?')[0];
if(c.indexOf(P)===0)c=c.slice(P.length);c=c.replace(/\\/+$/,'');
if(CONSULTA.indexOf(c)<0){aviso();return Promise.resolve(new Response(JSON.stringify({ok:false,error:'somente leitura (Nexus)'}),
{status:403,headers:{'Content-Type':'application/json'}}));}}return _f.apply(this,arguments);};})();</script>"""


def injetar(html: str) -> str:
    extra = _VISUAL + _GUARDA % (json.dumps(sorted(POSTS_DE_CONSULTA)), json.dumps(PREFIXO))
    i = html.lower().find("</head>")
    return html[:i] + extra + html[i:] if i >= 0 else extra + html


def enviar(**pedido):
    """O único ponto que fala com a rede. Os testes trocam esta função."""
    try:
        return requests.request(**pedido)
    except requests.RequestException as e:
        raise ForaDoAr(type(e).__name__) from e
```

- [ ] **Step 4: Run test to verify it passes**

Run (NEXUS): `python -m pytest -q tests/test_performance_ponte.py`
Expected: PASS (6 testes).

- [ ] **Step 5: Commit** (com o OK do Levi)

```bash
git add nexus/performance/__init__.py nexus/performance/ponte.py tests/test_performance_ponte.py
git commit -m "feat(performance): ponte so de leitura para a plataforma de Performance"
```

---

### Task 9 (NEXUS): a aba Tempo real e a rota da ponte

**Files:**
- Modify: `nexus/torres/performance/__init__.py`
- Create: `nexus/torres/performance/templates/performance/tempo_real.html`
- Modify: `nexus/static/nexus.css` (classes `.ponte-*`, junto das `.campo-*`)
- Test: `tests/test_torre_performance.py`

**Interfaces:**
- Consumes: `ponte.PREFIXO`, `pode_passar`, `montar_pedido`, `ajustar_resposta`, `enviar`, `ForaDoAr`,
  `TEMPO_LIMITE_S` (Task 8); `app.config["NEXUS_PLATAFORMA_URL" | "NEXUS_PLATAFORMA_TOKEN"]` (Task 7).
- Produces: endpoints `torre_performance.tempo_real` (`/t/performance/tempo-real`) e `torre_performance.plataforma`
  (`/t/performance/plataforma/<path:caminho>`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_torre_performance.py
"""Torre Performance → Tempo real: a plataforma inteira, só leitura, pela ponte (04/10/2026)."""
import pytest

from nexus import create_app
from nexus.performance import ponte

from conftest import SENHA_TESTE


class _Resp:
    def __init__(self, status=200, corpo=b"{}", tipo="application/json", extra=None):
        self.status_code, self.content = status, corpo
        self.headers = {"Content-Type": tipo, **(extra or {})}


@pytest.fixture
def app_ponte():
    app = create_app({"NEXUS_SECRET_KEY": "k", "NEXUS_SENHA_ADMIN": SENHA_TESTE,
                      "NEXUS_PLATAFORMA_URL": "http://plat:5050", "NEXUS_PLATAFORMA_TOKEN": "segredo-xyz"})
    app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
    return app


@pytest.fixture
def logado_ponte(app_ponte):
    c = app_ponte.test_client()
    assert c.post("/entrar", data={"senha": SENHA_TESTE}).status_code == 302
    return c


def test_aba_mostra_a_plataforma_na_moldura(logado_ponte):
    html = logado_ponte.get("/t/performance/tempo-real").get_data(as_text=True)
    assert f'src="{ponte.PREFIXO}/tempo-real"' in html and "somente leitura" in html.lower()
    assert 'class="menu"' in html and "Em construção" not in html


def test_ponte_exige_login(app_ponte):
    r = app_ponte.test_client().get(ponte.PREFIXO + "/api/state")
    assert r.status_code == 302


def test_ponte_leva_o_pedido_e_devolve_sem_cookie(logado_ponte, monkeypatch):
    visto = {}

    def falso(**p):
        visto.update(p)
        return _Resp(extra={"Set-Cookie": "s=1"})
    monkeypatch.setattr(ponte, "enviar", falso)
    r = logado_ponte.get(ponte.PREFIXO + "/api/pv/trackers/parados?force=1&data=x")
    assert r.status_code == 200 and "Set-Cookie" not in r.headers
    assert visto["url"] == "http://plat:5050/api/pv/trackers/parados" and visto["params"] == [("data", "x")]
    assert visto["headers"]["X-Nexus-Leitura"] == "segredo-xyz"


def test_gravacao_nao_sai_do_nexus(logado_ponte, monkeypatch):
    monkeypatch.setattr(ponte, "enviar", lambda **p: pytest.fail("gravação saiu do Nexus"))
    r = logado_ponte.post(ponte.PREFIXO + "/api/state/tracking", json={"key": "x"})
    assert r.status_code == 403 and r.get_json()["error"] == "somente leitura (Nexus)"


def test_post_de_consulta_passa(logado_ponte, monkeypatch):
    monkeypatch.setattr(ponte, "enviar", lambda **p: _Resp(corpo=b'{"A":1}'))
    r = logado_ponte.post(ponte.PREFIXO + "/api/os-performance/counts", json={"usinas": ["A"]})
    assert r.status_code == 200 and r.get_json() == {"A": 1}


def test_plataforma_fora_mostra_a_hora_e_tentar_de_novo(logado_ponte, monkeypatch):
    def cai(**p):
        raise ponte.ForaDoAr("ReadTimeout")
    monkeypatch.setattr(ponte, "enviar", cai)
    r = logado_ponte.get(ponte.PREFIXO + "/tempo-real")
    assert r.status_code == 502
    corpo = r.get_data(as_text=True)
    assert "Plataforma de Performance sem resposta" in corpo and "Tentar de novo" in corpo


def test_chave_recusada_diz_sem_mostrar_a_chave(logado_ponte, monkeypatch):
    monkeypatch.setattr(ponte, "enviar", lambda **p: _Resp(401, b'{"error":"chave de leitura recusada"}'))
    r = logado_ponte.get(ponte.PREFIXO + "/tempo-real")
    corpo = r.get_data(as_text=True)
    assert r.status_code == 502 and "recusou a chave" in corpo and "segredo-xyz" not in corpo


def test_sem_configuracao_a_aba_diz_o_que_falta(logado):
    html = logado.get("/t/performance/tempo-real").get_data(as_text=True)
    assert "NEXUS_PLATAFORMA_URL" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run (NEXUS): `python -m pytest -q tests/test_torre_performance.py`
Expected: FAIL — a aba ainda cai no placeholder ("Em construção") e a ponte dá 404.

- [ ] **Step 3: Write minimal implementation**

No fim de `nexus/torres/performance/__init__.py` (depois de `bp = TORRE.criar_blueprint(__name__)`), e troque o
`from ..modelo import Tela, Torre` do topo por:

```python
from datetime import datetime

from flask import Response, current_app, jsonify, render_template, request

from ...performance import ponte
from ..modelo import Tela, Torre
```

```python
# Tempo real (04/10/2026): a Entrada e o Monitoramento da própria plataforma, só leitura, pela ponte. Levi: "tudo da
# plataforma, só leitura", "em paralelo por enquanto". A plataforma segue sendo o motor; o Nexus não pede nada a mais
# às fontes. A regra mora em nexus/performance/ponte.py.
def _config_ponte():
    url = current_app.config.get("NEXUS_PLATAFORMA_URL")
    token = current_app.config.get("NEXUS_PLATAFORMA_TOKEN")
    falta = [n for n, v in (("NEXUS_PLATAFORMA_URL", url), ("NEXUS_PLATAFORMA_TOKEN", token)) if not v]
    return url, token, falta


@bp.route("/tempo-real")
def tempo_real():
    url, _token, falta = _config_ponte()
    return render_template("performance/tempo_real.html", torre=TORRE, tela=TORRE.tela("tempo-real"),
                           prefixo=ponte.PREFIXO, plataforma=url, falta=falta)


def _erro(texto: str) -> Response:
    hora = datetime.now().strftime("%H:%M")
    html = render_template("performance/ponte_erro.html", texto=texto, hora=hora)
    return Response(html, status=502, mimetype="text/html")


@bp.route("/plataforma/<path:caminho>", methods=["GET", "HEAD", "POST"])
def plataforma(caminho: str):
    url, token, falta = _config_ponte()
    if falta:
        return _erro("A ponte não está configurada: falta " + " e ".join(falta) + " no .env do Nexus.")
    c = "/" + caminho
    if not ponte.pode_passar(request.method, c):
        return jsonify({"ok": False, "error": "somente leitura (Nexus)"}), 403
    pedido = ponte.montar_pedido(url, token, request.method, c, list(request.args.items(multi=True)),
                                 request.get_data() if request.method == "POST" else None, request.content_type)
    try:
        r = ponte.enviar(**pedido)
    except ponte.ForaDoAr:
        return _erro(f"Plataforma de Performance sem resposta em {ponte.TEMPO_LIMITE_S} s.")
    if r.status_code == 401:
        return _erro("A plataforma recusou a chave de leitura do Nexus. Confira NEXUS_PLATAFORMA_TOKEN no .env do "
                     "Nexus e NEXUS_LEITURA_TOKEN na plataforma.")
    status, cab, corpo = ponte.ajustar_resposta(r.status_code, dict(r.headers), r.content)
    return Response(corpo, status=status, headers=cab)
```

Crie `nexus/torres/performance/templates/performance/tempo_real.html`:

```html
{% extends "base.html" %}
{% block titulo %}{{ tela.nome }}{% endblock %}
{% block classe_conteudo %}conteudo--moldura{% endblock %}
{% block conteudo %}
{# A Entrada e o Monitoramento da Plataforma de Performance, só leitura, pela ponte (04/10/2026). As ações que gravam
   (cadeado, ticket, OS) seguem na plataforma: "Abrir na plataforma" leva até lá. #}
<div class="ponte-recorte">
  <div class="ponte-faixa">
    <span class="ponte-origem">Plataforma de Performance · somente leitura</span>
    {% if plataforma %}<a class="ponte-fora" href="{{ plataforma }}/tempo-real" target="_blank" rel="noopener">Abrir na plataforma</a>{% endif %}
  </div>
  {% if falta %}
  <p class="ponte-falta">A aba ainda não está ligada à plataforma: falta {{ falta|join(" e ") }} no .env do Nexus.</p>
  {% else %}
  <iframe class="ponte-moldura" src="{{ prefixo }}/tempo-real" title="Tempo real da Plataforma de Performance"></iframe>
  {% endif %}
</div>
{% endblock %}
```

Crie `nexus/torres/performance/templates/performance/ponte_erro.html` (página solta: abre DENTRO da moldura):

```html
<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Plataforma sem resposta</title>
<link rel="stylesheet" href="{{ url_for('static', filename='nexus.css') }}"></head>
<body class="ponte-erro">
  <h1>Plataforma de Performance sem resposta</h1>
  <p>{{ texto }}</p>
  <p class="mudo">Às {{ hora }}.</p>
  <button class="gc-btn gc-btn--primario" type="button" onclick="location.reload()">Tentar de novo</button>
</body></html>
```

Atenção ao teste `test_plataforma_fora_mostra_a_hora_e_tentar_de_novo`: a mensagem do `_erro` do `ForaDoAr` é
"Plataforma de Performance sem resposta em 150 s." e o `<h1>` repete o título — os dois contêm o texto procurado.

No `nexus/static/nexus.css`, logo depois da linha `.campo-fora:hover{text-decoration:underline}`:

```css
/* Tempo real pela ponte (04/10/2026): mesma faixa + moldura do Campo, sem recorte do menu da plataforma */
.ponte-recorte{flex:1;min-width:0;height:calc(100vh - var(--topo));display:flex;flex-direction:column}
.ponte-faixa{display:flex;align-items:center;gap:16px;padding:0 16px;min-height:40px;border-bottom:1px solid var(--linha);
  font:500 13px/1.4 var(--font-sans)}
.ponte-origem{color:var(--mudo)}
.ponte-fora{margin-left:auto;color:var(--verde-texto);font-weight:600;text-decoration:none}
.ponte-fora:hover{text-decoration:underline}
.ponte-moldura{flex:1;min-height:0;width:100%;border:0;display:block;background:var(--fundo)}
.ponte-falta{margin:24px 16px;color:var(--alerta)}
.ponte-erro{padding:32px 24px;max-width:640px}
.ponte-erro h1{font:600 20px/1.3 var(--font-display);margin:0 0 12px}
```

- [ ] **Step 4: Run test to verify it passes**

Run (NEXUS): `python -m pytest -q tests/test_torre_performance.py` e depois `python -m pytest -q`
Expected: PASS em tudo (inclusive `test_toda_rota_nao_publica_exige_login` e o exportador estático, que só usa o
placeholder).

- [ ] **Step 5: Commit** (com o OK do Levi)

```bash
git add nexus/torres/performance/__init__.py nexus/torres/performance/templates nexus/static/nexus.css tests/test_torre_performance.py
git commit -m "feat(performance): aba Tempo real com a plataforma inteira, so leitura, pela ponte"
```

---

### Task 10 (NEXUS): documentação da área

**Files:**
- Create: `nexus/performance/CLAUDE.md`, `nexus/torres/performance/CLAUDE.md`
- Modify: `CLAUDE.md` (tabela de áreas), `nexus/torres/CLAUDE.md` (tabela de torres), `DEPLOY.md` (variáveis)

- [ ] **Step 1:** `nexus/performance/CLAUDE.md`:

```markdown
# CLAUDE.md — Performance (regra da torre, sem Flask)

## Ponte para a Plataforma de Performance (04/10/2026)

A aba Performance → Tempo real mostra a Entrada e o Monitoramento da própria plataforma (Levi: "tudo da plataforma,
só leitura", "em paralelo por enquanto"). Fase 1 de cinco para a plataforma morar 100% no Nexus: ver o spec
`docs/superpowers/specs/2026-10-04-tempo-real-no-nexus-design.md`, seção 10.

- O navegador fala só com o Nexus. `ponte.py` leva o pedido à plataforma com `X-Nexus-Leitura`
  (`NEXUS_PLATAFORMA_TOKEN` = `NEXUS_LEITURA_TOKEN` da plataforma) e `X-Forwarded-Prefix: /t/performance/plataforma`.
  A plataforma devolve as páginas com o prefixo (`_SHIM_PREFIXO` + atributos): a ponte não reescreve HTML, só injeta
  o visual (`#nexus-visual`) e o guarda (`#nexus-leitura`).
- **Só leitura em três camadas:** portão da plataforma (403 com a chave), `pode_passar` aqui, guarda no navegador.
  Os únicos POSTs: `POSTS_DE_CONSULTA` (a mesma lista do `leitura_nexus.py` da plataforma — mudou lá, muda aqui).
- **`force` sai de todo pedido:** o "Atualizar" dos trackers refaria curvas na SunOp (cota). Pelo Nexus, lê-se o pronto.
- Não passa `Set-Cookie` nem o cookie do Nexus; tempo-limite 150 s (o drill da API PV leva até 120 s).
- Controle de gravação que aparecer na tela (seletor novo na plataforma): acrescentar em `_VISUAL`. Mesmo sem isso,
  o guarda não deixa gravar.

Como provar: `tests/test_performance_ponte.py`, `tests/test_torre_performance.py` e, na tela, o Nexus local contra a
plataforma local — mesmo número do card nos dois no mesmo minuto.
```

- [ ] **Step 2:** `nexus/torres/performance/CLAUDE.md`:

```markdown
# CLAUDE.md — torre Performance

| Tela | Estado | De onde vem |
|---|---|---|
| Tempo real | plataforma inteira, só leitura, pela ponte (04/10/2026) | `nexus/performance/ponte.py` — leia `nexus/performance/CLAUDE.md` |
| Painel NOC, Diagnóstico, Strings e trackers, Visão gerencial, Criador de relatório, Gêmeo digital | placeholder | fase 2: cada uma entra na lista de leitura da plataforma e ganha a sua moldura pela mesma ponte |

A regra mora em `nexus/performance/`; aqui ficam as rotas e os templates.
```

- [ ] **Step 3:** No `CLAUDE.md` raiz, na tabela de áreas, acrescente a linha
`| Performance (Tempo real pela ponte) | nexus/performance/CLAUDE.md e nexus/torres/performance/CLAUDE.md |`; no
`nexus/torres/CLAUDE.md`, na tabela de torres, a linha
`| performance/ | Tempo real = plataforma pela ponte, só leitura; as outras telas placeholder | nexus/performance/CLAUDE.md |`;
no `DEPLOY.md`, na lista de variáveis do `.env`, `NEXUS_PLATAFORMA_URL` (no servidor, `https://app.gridco.com.br`) e
`NEXUS_PLATAFORMA_TOKEN` (a mesma `NEXUS_LEITURA_TOKEN` do `.env` da plataforma no servidor).

- [ ] **Step 4: Commit** (com o OK do Levi)

```bash
git add nexus/performance/CLAUDE.md nexus/torres/performance/CLAUDE.md CLAUDE.md nexus/torres/CLAUDE.md DEPLOY.md
git commit -m "docs(performance): ponte do Tempo real e a torre Performance"
```

---

### Task 11 (os dois): prova na tela, de ponta a ponta

**Files:** nenhum de código (só configuração local, fora do git).

- [ ] **Step 1: Gerar a chave e configurar as duas pontas (sem imprimir a chave)**

A chave vai para os dois arquivos por script, sem aparecer no terminal (nunca colar no chat nem em log). O script
recusa se a variável já existir num deles, para não deixar duas.

```bash
python - <<'EOF'
import pathlib, secrets
RAIZ = pathlib.Path(r"C:\Users\Levi Maia\OneDrive - GRID CO\Área de Trabalho\temp")
alvos = {RAIZ / "Projeto API PV" / "tokens.txt": ["NEXUS_LEITURA_TOKEN"],
         RAIZ / "Nexus" / ".env": ["NEXUS_PLATAFORMA_URL", "NEXUS_PLATAFORMA_TOKEN"]}
for arq, nomes in alvos.items():
    texto = arq.read_text(encoding="utf-8")
    ja = [n for n in nomes if any(l.split("=", 1)[0].strip() == n for l in texto.splitlines())]
    assert not ja, f"{arq.name} já tem {ja}: confira à mão antes"
k = secrets.token_urlsafe(32)
valores = {"NEXUS_LEITURA_TOKEN": k, "NEXUS_PLATAFORMA_TOKEN": k, "NEXUS_PLATAFORMA_URL": "http://127.0.0.1:5050"}
for arq, nomes in alvos.items():
    texto = arq.read_text(encoding="utf-8").rstrip("\n")
    arq.write_text(texto + "\n" + "\n".join(f"{n}={valores[n]}" for n in nomes) + "\n", encoding="utf-8")
pathlib.Path(r"C:\GridcoAuto\nexus\chave_leitura.txt").write_text(k, encoding="utf-8")
print("chave gravada nos dois lados (não exibida)")
EOF
```

Reinicie a plataforma local (ritual do `plataforma/CLAUDE.md`: compilar, matar só `app.py`/`worker.py` desta pasta, o
guardião sobe) e o Nexus (`python app.py`).

- [ ] **Step 2: Ponte responde, com a chave, e recusa gravação**

```bash
python -c "import pathlib,requests;k=pathlib.Path(r'C:\GridcoAuto\nexus\chave_leitura.txt').read_text().strip();H={'X-Nexus-Leitura':k,'X-Forwarded-Prefix':'/t/performance/plataforma'};print(requests.get('http://127.0.0.1:5050/api/entrada/tempo-real',headers=H,timeout=60).status_code, requests.post('http://127.0.0.1:5050/api/state/tracking',json={},headers=H,timeout=60).status_code)"
```

Expected: `200 403`.

- [ ] **Step 3: Na tela (Browser pane, login do Nexus por sessão lendo o `.env`, sem exibir a senha)**

Abra `http://localhost:5070/t/performance/tempo-real`. Confira:
1. os cards por cliente e fonte aparecem, com o menu lateral do Nexus à vista e sem o topo da plataforma;
2. o clique no card da Athon abre o Monitoramento da Athon (nível 3) dentro da moldura;
3. expandir uma usina e um inversor abre o drill (strings e curva);
4. `read_console_messages` sem erro de 404 de `/static/` ou `/api/`; `read_network_requests` com tudo debaixo de
   `/t/performance/plataforma/`;
5. em 375 px (`resize_window` mobile) não há rolagem lateral na casca.

- [ ] **Step 4: Só leitura de verdade**

Copie `plataforma/ufv_state.json` para o scratchpad. Na tela do Nexus, procure algum controle de gravação que ainda
apareça. Rode no console da moldura:

```js
[...document.querySelectorAll('[onclick],[onchange],[oninput]')].map(e=>(e.getAttribute('onclick')||e.getAttribute('onchange')||e.getAttribute('oninput')).slice(0,60)).filter((v,i,a)=>a.indexOf(v)===i)
```

Para cada um que chame função que grava (`string-trancada`, `comment`, `os-atribuir`, `usina-desligada`, `tickets`,
`tracking`), clique: tem de aparecer "Somente leitura no Nexus" e nada mudar. Acrescente o seletor em `_VISUAL`
(`ponte.py`) se o controle estiver à vista, e rode `python -m pytest -q tests/test_performance_ponte.py`. Depois,
`fc` do `ufv_state.json` contra a cópia: **idêntico**.

- [ ] **Step 5: Mesmo número dos dois lados**

No mesmo minuto, abra `http://127.0.0.1:5050/tempo-real` e a aba do Nexus: os números de um card (strings faltando,
sem comunicação, trackers parados) e o "atualizado às" têm de ser iguais. Screenshot dos dois lado a lado para o Levi.

- [ ] **Step 6: Fechamento**

Mostrar ao Levi (feito / motivo / resolvido?), com o screenshot. Commits e o push da plataforma (deploy) só com o OK
dele. No servidor: a mesma chave no `.env` da plataforma e no do Nexus; o `NEXUS_PLATAFORMA_URL` do servidor é
`https://app.gridco.com.br`.
