# Visão geral na Visão do responsável — plano de construção

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a 4ª aba "Visão geral" da Visão do responsável: os três blocos de KPI em cima e todas as usinas numa lista só,
filtrada pelo clique num bloco, num nível ou num número; e o cabeçalho e as colunas centralizados (menos Usina) nas
tabelas da tela.

**Architecture:** nada de dado novo: a aba usa as mesmas usinas da tela (`com_manutencao`, filtro de responsável,
cliente, busca e equipe), o mesmo resumo (`soma`) e as mesmas células (`u[b].valores`, `u[b].det`). O filtro é uma chave
no endereço (`filtro=manut.atrasadas`), validada contra `FILTROS_GERAL` em `nexus/campo/responsaveis.py`, onde cada
chave tem a mesma condição que conta o número no `soma`.

**Tech Stack:** Python 3.14, Flask/Jinja, CSS por token (`nexus/static/campo.css`), pytest.

**Spec:** `docs/superpowers/specs/2026-10-18-visao-responsavel-visao-geral-design.md`

## Global Constraints

- Construir DEPOIS que o Ranking das equipes estiver na `origin/main` (mexe no mesmo template, rota e CSS).
- Nenhuma régua nova: cada filtro usa a condição do número que ele representa no `soma`.
- Cor só por token nos dois temas; sem emoji; pt-BR; endereço nunca a partir da raiz (`url(...)`, `url_for`).
- Nome de colega não entra em arquivo versionado: fixture com nome fictício.
- Antes de dar por pronto: suíte inteira uma vez e a tela conferida a 1440 e 375 px, nos dois temas.
- Subir para a `main` só com o OK do Levi.

## Review Focus

1. `filtro` que não existe, vazio ou com lixo no endereço: a aba abre sem filtro, sem erro.
2. Quem entrou pelo Fracttal (responsável logado) vê na Visão geral só as usinas dele, como em Onde focar.
3. O número do bloco na Visão geral é o mesmo de Onde focar com os mesmos filtros (o mesmo `soma`).
4. Número zero não é link; filtro sem nenhuma usina mostra "Nenhuma usina com esse filtro" e o × que limpa.
5. O centro das colunas não quebra as tabelas dos blocos onde colunas se escondem (até 1180 e até 760 px).

---

### Task 1: os filtros da Visão geral, puros

**Files:**
- Modify: `nexus/campo/responsaveis.py` (perto de `soma`)
- Test: `tests/test_campo_responsaveis.py`

**Interfaces:**
- Produces: `FILTROS_GERAL: dict[str, tuple[str, str, Callable[[dict], bool]]]` = chave → (bloco, rótulo, predicado);
  chaves: `perf`, `acomp`, `manut` (nível diferente de ok), `perf.critico`, `perf.atencao` (e o mesmo para `acomp` e
  `manut`), `perf.abaixo_meta`, `perf.pr_abaixo`, `perf.disp`, `acomp.rondas`, `acomp.pts`, `acomp.chamados`,
  `acomp.ext`, `manut.atrasadas`, `manut.paradas`, `manut.semana`.
- Produces: `filtro_geral(valor) -> str | None` (a chave válida ou None) e
  `filtrar_geral(usinas: list[dict], chave: str | None) -> list[dict]` (sem chave, a lista inteira).

- [ ] **Step 1: Write the failing tests**

```python
def test_os_filtros_da_visao_geral_contam_como_o_resumo(tela):
    """Cada filtro da Visão geral usa a condição que conta o número no resumo (`soma`): nenhuma régua nova."""
    us = _com_manut()                                  # as usinas da tela, com a Manutenção no limite de 30
    lista = list(us.values())
    s = R.soma("Todos", lista)
    n = lambda k: len(R.filtrar_geral(lista, k))
    assert n("perf.abaixo_meta") == s["abaixo_meta"] and n("perf.pr_abaixo") == s["pr_abaixo"]
    assert n("acomp.rondas") == s["rondas"]
    assert n("acomp.pts") == sum(1 for u in lista if u["pt"]["aguardando"])
    assert n("manut.atrasadas") == sum(1 for u in lista if (u.get("manutencao") or {}).get("atrasadas"))
    for b in ("perf", "acomp", "manut"):
        assert n(b) == s[b]["critico"] + s[b]["atencao"]
        assert n(f"{b}.critico") == s[b]["critico"] and n(f"{b}.atencao") == s[b]["atencao"]


def test_filtro_da_visao_geral_com_lixo_e_ignorado():
    assert [R.filtro_geral(v) for v in ("manut.atrasadas", "", None, "manut.", "x" * 500, "perf.critico")] == [
        "manut.atrasadas", None, None, None, None, "perf.critico"]
    assert R.filtrar_geral([{"usina": "A"}], None) == [{"usina": "A"}]
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest -q tests/test_campo_responsaveis.py -k "visao_geral"`
Expected: FAIL (`AttributeError: ... filtrar_geral`)

- [ ] **Step 3: Implement `FILTROS_GERAL`, `filtro_geral` and `filtrar_geral`**

Cada predicado copia a condição do `soma` (abaixo da meta: `atingimento < META_NA_META`; PR: `pr < pr_meta`; rondas:
`tipo in ("nunca", "sem_ronda", "longa_pendente")`; PT: `aguardando > 0`; chamados: `abertos > 0`; extintores:
`vencidos > 0`; atrasadas e paradas da `manutencao` > 0; semana: `passada_pct < META_SEMANA`; disponibilidade:
`disp < DISP_OK`). Os de bloco olham `u[b]["nivel"]`.

- [ ] **Step 4: Run them to see them pass**

Run: `python -m pytest -q tests/test_campo_responsaveis.py -k "visao_geral"`
Expected: PASS

- [ ] **Step 5: Commit** — `feat(campo): os filtros da Visão geral, com a condição de cada número do resumo`

### Task 2: a aba na tela, a lista única e o centro das colunas

**Files:**
- Modify: `nexus/torres/campo/__init__.py` (rota `responsaveis`: `modo == "geral"`, `filtro`, a lista)
- Modify: `nexus/torres/campo/templates/campo/responsaveis.html` (o link da aba; a seção `geral`; o detalhe de cada bloco
  num macro usado pelos blocos e pela Visão geral)
- Modify: `nexus/static/campo.css` (`.cr-gr-*`; o centro: as colunas `cr-col-*` do cabeçalho e das linhas)
- Test: `tests/test_campo_responsaveis.py`

**Interfaces:**
- Consumes: `FILTROS_GERAL`, `filtro_geral`, `filtrar_geral` (Task 1); `soma`, `bloco`, `com_manutencao`.
- Produces: no template, `filtro` (a chave ou None), `filtros_geral` e `lista_geral` (as usinas filtradas).

- [ ] **Step 1: Write the failing tests**

```python
def test_a_visao_geral_mostra_os_tres_blocos_e_a_lista_unica(manut, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral").get_data(as_text=True)
    assert 'aria-current="page">Visão geral' in html
    geral = html[html.index('class="cr-gr"'):]
    for b in ("Performance", "Acompanhamento", "Manutenção"):
        assert b in geral
    assert geral.count('class="cr-gr-lin') == len(_com_manut())          # todas as usinas, uma linha cada
    assert "filtro=manut.atrasadas" in geral                              # o número vira link


def test_o_clique_no_numero_filtra_a_lista(manut, logado):
    total = len(_com_manut())
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&filtro=manut.atrasadas").get_data(as_text=True)
    geral = html[html.index('class="cr-gr"'):]
    assert geral.count('class="cr-gr-lin') == 2                          # as duas usinas com tarefa atrasada
    estado = geral[geral.index('class="cr-gr-estado"'):][:600]
    assert f"2 de {total} usinas" in estado and "Tarefas atrasadas" in estado
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&filtro=nada").get_data(as_text=True)
    assert html.count('class="cr-gr-lin') == total                       # filtro que não existe: sem filtro


def test_filtro_sem_usina_diz_e_deixa_limpar(manut, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=geral&filtro=acomp.ext").get_data(as_text=True)
    assert "Nenhuma usina com esse filtro" in html and 'class="cr-gr-limpar"' in html
    assert 'filtro=acomp.ext"' not in html.split('class="cr-gr-blocos"')[1].split('class="cr-gr-estado"')[0]   # zero não é link


def test_quem_entra_pelo_fracttal_ve_so_as_usinas_dele_na_visao_geral(manut, cliente):
    """Como em Onde focar: o responsável que entrou pelo Fracttal vê as usinas dele."""
    _responsavel(cliente)
    html = cliente.get("/t/campo/responsaveis?modo=geral").get_data(as_text=True)
    dele = [u for u in _com_manut().values() if u.get("responsavel") == "Beltrano Supervisor"]
    assert html.count('class="cr-gr-lin') == len(dele) > 0


def test_o_cabecalho_e_as_colunas_ficam_no_centro():
    css = (Path(__file__).resolve().parent.parent / "nexus/static/campo.css").read_text(encoding="utf-8")
    assert re.search(r"\.cr-g > \[class\*=\"cr-col-\"\]\{[^}]*justify-self:center", css)
```

- [ ] **Step 2: Run them to see them fail**

Run: `python -m pytest -q tests/test_campo_responsaveis.py -k "visao_geral or clique_no_numero or centro or sem_usina"`
Expected: FAIL

- [ ] **Step 3: Implement the route, the template section and the CSS**

A seção segue o protótipo aprovado: os três cartões (`cr-gr-bloco`) com o cabeçalho que filtra o bloco, os quatro números
do resumo (link quando a contagem do filtro é maior que zero), a barra e os botões focar/acompanhar; a linha de estado
("N de M usinas" e o filtro com ×); a lista (`cr-gr-lin`, `details` como as linhas dos blocos) com Meta, Disp., Ronda,
Limpeza, PT, Atrasadas, Paradas e Semana, e o detalhe dos três blocos ao abrir; até 760 px, cartões com as etiquetas
P, A e M.

- [ ] **Step 4: Run them to see them pass**, then the area: `python -m pytest -q tests/test_campo_responsaveis.py`
Expected: PASS

- [ ] **Step 5: Commit** — `feat(campo): a Visão geral na Visão do responsável e as colunas no centro`

### Task 3: prova na tela, documentação e entrega

- [ ] **Step 1:** a tela com o dado real (cópia de prova, só leitura) a 1440 e 375 px, nos dois temas: os três blocos,
  um clique em cada tipo de filtro e o × que limpa.
- [ ] **Step 2:** `nexus/torres/campo/CLAUDE.md`: a Visão geral (o que é, os filtros e a condição de cada um, o centro
  das colunas).
- [ ] **Step 3:** a suíte inteira uma vez: `python -m pytest -q` — Expected: nenhuma falha.
- [ ] **Step 4: Commit** — `docs(campo): a Visão geral na Visão do responsável`; subir para a `main` só com o OK do Levi.
