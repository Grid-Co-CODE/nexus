# Ranking das equipes na Visão do responsável: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** uma aba "Ranking das equipes" na Visão do responsável (`/t/campo/responsaveis?modo=ranking`): um cartão por
equipe, da pior para a melhor, com a posição e a nota da régua do Ranking por região do App de Campo (60% qualidade + 40%
cobertura, 30 dias), a seta contra os 30 dias anteriores e, ao lado, em quê cobrar.

**Architecture:** a régua mora num módulo novo e puro, `nexus/campo/ranking_equipes.py`. O agregado por usina (as notas e a
ronda nos dois períodos) entra na cópia de 5 min da Visão (`responsaveis.visao_responsaveis`), como mais uma fonte isolada
(`_ler_fonte`). O agrupamento por equipe sai no pedido, porque os filtros e o limite das atrasadas são de quem olha. A rota
`responsaveis()` ganha o `modo=ranking` e o filtro `equipe=`. Nada novo vai ao banco.

**Tech Stack:** Python 3, Flask, Jinja2, CSS por token (`nexus/static/nexus.css`, `campo.css`), pytest com o banco falso
(`tests/test_campo_visao.py`, fixture `banco`; `tests/test_campo_responsaveis.py`, fixture `tela`).

**Spec:** `docs/superpowers/specs/2026-10-18-visao-responsavel-ranking-equipes-design.md` (aprovado pelo Levi em 18/10/2026).

## Global Constraints

- Tudo em pt-BR, inclusive comentários; comentário diz o porquê, de preferência com o caso real.
- Sem emoji na interface; severidade por cor e palavra.
- Cor só por token: nada de `#hex` ou `rgba()` em regra de CSS nem em template; os dois temas (escuro e claro).
- Repositório público: nenhum nome de colega em arquivo versionado; teste com nome fictício (os do banco falso: "Beltrano
  Supervisor", "Ciclano Chefe"); nenhum nome de equipe real ao lado do desempenho dela.
- Endereço nunca a partir da raiz: na tela, o `url(...)` da torre (`_url`); em Python, `url_for`/`na_raiz`.
- Só banco do Nexus e Fracttal como fonte; nada novo no banco (nenhum livro, fato ou entrada de catálogo).
- Janela `JANELA_DIAS = 30`: atual = hoje − 29 a hoje; anterior = hoje − 59 a hoje − 30; o dia é o `data_id` (Brasília).
- Pesos `visao.PESO_QUALIDADE = 0.6`, `visao.PESO_COBERTURA = 0.4`; arredondamento como o App: `int(round(x))`.
- Cor da nota (escala do painel do App): 85 ou mais `ok`, 70 ou mais `alerta`, abaixo `critico`, sem nota `neutro`.
- Base pequena: menos de `visao.BASE_PEQUENA` (3) usinas.
- Trabalho no worktree `C:/GridcoAuto/setores/campo-hseq/nexus`, ramo `setor-campo-hseq`. Commit no ramo; push para a
  `main` só com o OK do Levi (push na `main` = produção em ~2 min).
- Testes: `python -m pytest <arquivo> -q` na raiz do worktree.

## Review Focus

1. **A API devolve número como texto** (`"90"`, `"20261018"`, `"1"`): nota, dia e usina passam por `D._int`/`D._id`; com
   texto, a conta é a mesma (teste na Task 1).
2. **A fonte das notas fora do ar** (o fato de fechamento ou as rondas falham): a aba diz "Não consegui ler as notas do App"
   e não mostra cartões sem nota por engano; Onde focar continua (testes nas Tasks 2 e 4).
3. **A equipe recortada pelos filtros** (cliente, busca, ou uma equipe com usinas de dois responsáveis): a nota é refeita
   só sobre as usinas que passam (teste na Task 3).
4. **O filtro `equipe=` é exato e o link leva o nome com espaço:** `equipe=SP+Norte` não pega a "SP Norte 01"; o cartão
   leva `equipe=SP+Norte+01` (teste na Task 4).
5. **O responsável logado pedindo `modo=cartoes` ou `modo=ranking`:** nunca vê os cartões dos outros responsáveis; no
   ranking, só as equipes dele (teste na Task 4).

---

### Task 1: A régua do App, pura

**Files:**
- Create: `nexus/campo/ranking_equipes.py`
- Test: `tests/test_campo_ranking_equipes.py`

**Interfaces:**
- Consumes: `visao.PESO_QUALIDADE`, `visao.PESO_COBERTURA`, `visao.BASE_PEQUENA`, `visao.SEM_EQUIPE`; `nexus.dados.fatos`
  como `D` (`D._id`, `D._int`).
- Produces:
  - `JANELA_DIAS = 30`, `COR_VERDE = 85`, `COR_AMBAR = 70`
  - `periodos(hoje: date) -> dict[str, tuple[date, date]]`: `{"atual": (ini, fim), "anterior": (ini, fim)}`
  - `agregar(fechamentos: list[dict], rondas: list[dict], mobilizadas, hoje: date) -> dict[int, dict]`:
    `{usina_id: {"atual": AGG, "anterior": AGG}}` para TODA usina mobilizada (zeros quando não há nada), com
    `AGG = {"q_soma": int, "q_n": int, "n_os": int, "n_ronda": int, "rondada": bool}`. `fechamentos` são linhas do
    `fato_fechamento` (`data_id`, `usina_id`, `nota_pts`, podendo vir como texto); `rondas` são as de
    `visao._rondas_ligadas` (`data` "AAAA-MM-DD", `usina_id`, `nota`, `avulsa` só na avulsa).
  - `nota_da_equipe(aggs: list[dict]) -> dict`: `{"qualidade": int|None, "cobertura": int|None, "nota": int|None,
    "n_notas": int, "n_os": int, "n_ronda": int, "rondadas": int, "usinas": int}`; `usinas = len(aggs)`.
  - `cor(nota: int | None) -> str`: `"neutro" | "ok" | "alerta" | "critico"`
  - `posicoes(notas: dict[str, dict]) -> dict[str, int]`: só as equipes com `nota` não vazia, 1 = a melhor.
  - `seta(atual: int | None, antes: int | None) -> dict`: `{"tipo": "sobe"|"desce"|"igual"|"sem", "n": int}`

- [ ] **Step 1: Commit do desenho e deste plano**

```bash
git add docs/superpowers/specs/2026-10-18-visao-responsavel-ranking-equipes-design.md docs/superpowers/plans/2026-10-18-visao-responsavel-ranking-equipes.md
git commit -m "docs(campo): o desenho e o plano do Ranking das equipes na Visão do responsável"
```

- [ ] **Step 2: Escrever os testes que falham** (`tests/test_campo_ranking_equipes.py`, dia fixo `HOJE = date(2026, 10, 18)`)

```python
def test_periodos_de_30_dias():
    p = RE.periodos(HOJE)
    assert p["atual"] == (date(2026, 9, 19), date(2026, 10, 18))
    assert p["anterior"] == (date(2026, 8, 20), date(2026, 9, 18))

def test_agrega_tarefas_e_rondas_por_usina_e_periodo():
    fech = [{"data_id": 20261018, "usina_id": 1, "nota_pts": 90},
            {"data_id": "20260919", "usina_id": "1", "nota_pts": "70"},     # texto da API: a mesma conta
            {"data_id": 20260918, "usina_id": 1, "nota_pts": 100},          # hoje − 30: o período anterior
            {"data_id": 20261010, "usina_id": 1, "nota_pts": None},         # sem nota: fora de tudo
            {"data_id": 20261010, "usina_id": 9, "nota_pts": 50},           # usina não mobilizada: fora
            {"data_id": 20260801, "usina_id": 1, "nota_pts": 10}]           # antes dos dois períodos: fora
    rondas = [{"data": "2026-10-01", "usina_id": 1, "nota": 80},
              {"data": "2026-10-02", "usina_id": 2, "nota": None},           # ronda do App sem nota: ronda, sem nota
              {"data": "2026-10-03", "usina_id": 3, "nota": None, "avulsa": True}]   # avulsa: só a cobertura
    a = RE.agregar(fech, rondas, {1, 2, 3, 4}, HOJE)
    assert a[1]["atual"] == {"q_soma": 240, "q_n": 3, "n_os": 2, "n_ronda": 1, "rondada": True}
    assert a[1]["anterior"] == {"q_soma": 100, "q_n": 1, "n_os": 1, "n_ronda": 0, "rondada": False}
    assert a[2]["atual"] == {"q_soma": 0, "q_n": 0, "n_os": 0, "n_ronda": 1, "rondada": True}
    assert a[3]["atual"] == {"q_soma": 0, "q_n": 0, "n_os": 0, "n_ronda": 0, "rondada": True}
    assert a[4]["atual"]["rondada"] is False and 9 not in a

def test_nota_da_equipe_a_conta_do_app():
    aggs = [{"q_soma": 158, "q_n": 2, "n_os": 1, "n_ronda": 1, "rondada": True},
            {"q_soma": 0, "q_n": 0, "n_os": 0, "n_ronda": 0, "rondada": False}]
    assert RE.nota_da_equipe(aggs) == {"qualidade": 79, "cobertura": 50, "nota": 67, "n_notas": 2, "n_os": 1,
                                       "n_ronda": 1, "rondadas": 1, "usinas": 2}     # 0,6 × 79 + 0,4 × 50 = 67,4

def test_equipe_sem_nenhuma_nota_fica_sem_nota():
    n = RE.nota_da_equipe([{"q_soma": 0, "q_n": 0, "n_os": 0, "n_ronda": 0, "rondada": True}])
    assert (n["qualidade"], n["nota"], n["cobertura"]) == (None, None, 100)

def test_igual_ao_ranking_por_regiao_do_app():
    # a aritmética de `_ranking_regioes` (function_app.py, v283), copiada como referência
    def app(notas, rondadas, total):
        qual = int(round(sum(notas) / float(len(notas))))
        cob = int(round(100.0 * rondadas / total)) if total else None
        return int(round(0.6 * qual + 0.4 * (cob if cob is not None else 0)))
    for notas, rondadas, total in (([95, 88, 100, 61], 3, 4), ([70], 0, 2), ([100] * 5, 1, 1), ([84, 85], 2, 3)):
        aggs = [{"q_soma": sum(notas), "q_n": len(notas), "n_os": len(notas), "n_ronda": 0, "rondada": rondadas > 0}]
        aggs += [{"q_soma": 0, "q_n": 0, "n_os": 0, "n_ronda": 0, "rondada": i < rondadas - 1} for i in range(total - 1)]
        assert RE.nota_da_equipe(aggs)["nota"] == app(notas, rondadas, total)

def test_cor_na_escala_do_painel_do_app():
    assert [RE.cor(n) for n in (85, 84, 70, 69, None)] == ["ok", "alerta", "alerta", "critico", "neutro"]

def test_posicoes_e_o_desempate():
    n = lambda nota, q, c, k: {"nota": nota, "qualidade": q, "cobertura": c, "n_notas": k}
    notas = {"B": n(90, 85, 100, 5), "A": n(90, 85, 100, 5), "C": n(90, 88, 95, 3), "D": n(92, 80, 100, 9),
             "X": n(90, 85, 100, 7), "E": n(None, None, 100, 0)}
    assert RE.posicoes(notas) == {"D": 1, "C": 2, "X": 3, "A": 4, "B": 5}   # nota, qualidade, cobertura, volume, nome

def test_seta():
    assert RE.seta(3, 5) == {"tipo": "sobe", "n": 2} and RE.seta(4, 2) == {"tipo": "desce", "n": 2}
    assert RE.seta(2, 2) == {"tipo": "igual", "n": 0}
    assert RE.seta(2, None) == RE.seta(None, 1) == {"tipo": "sem", "n": 0}
```

- [ ] **Step 3: Rodar e ver falhar**

Run: `python -m pytest tests/test_campo_ranking_equipes.py -q`
Expected: FAIL (`ModuleNotFoundError: nexus.campo.ranking_equipes`)

- [ ] **Step 4: Implementar o módulo** com as assinaturas acima. Docstring do módulo com o porquê (Levi, 18/10/2026: "de
  acordo com as regras do ranking do app de campo"; a régua `_ranking_regioes` do App; as quatro diferenças contra o
  painel do App do desenho). A ronda sem `nota` conta em `n_ronda` e `rondada`; a avulsa só em `rondada`; o fechamento
  sem nota não conta em nada. `posicoes` ordena por `(-nota, -qualidade, -cobertura, -n_notas, nome)`.

- [ ] **Step 5: Rodar e ver passar**

Run: `python -m pytest tests/test_campo_ranking_equipes.py -q`
Expected: PASS (8)

- [ ] **Step 6: Commit**

```bash
git add nexus/campo/ranking_equipes.py tests/test_campo_ranking_equipes.py
git commit -m "feat(campo): a régua do ranking por região do App, pura (Ranking das equipes)"
```

### Task 2: As notas na cópia de 5 min da Visão

**Files:**
- Modify: `nexus/campo/responsaveis.py` (função nova perto de `limpeza()`; `visao_responsaveis()`, linhas ~1249-1286)
- Test: `tests/test_campo_ranking_equipes.py`

**Interfaces:**
- Consumes: `ranking_equipes.agregar`, `ranking_equipes.periodos`; `visao._fato("fechamento", b)`, `visao._rondas_ligadas(b)`,
  `b.mobilizadas`, `b.times()`.
- Produces:
  - `responsaveis.ranking_fonte(b, hoje: date) -> tuple[dict, dict]`: `(agregar(...), {"de": ..., "aviso": ...,
    "atual": ("AAAA-MM-DD", "AAAA-MM-DD"), "anterior": (...)})`
  - nas chaves de `visao_responsaveis().dados`: `"ranking_por_usina"` (o dict de `agregar`), `"tecnicos_por_equipe"`
    (`{nome da equipe: técnicos}`, de `b.times()`), `info["ranking"]`; erro da fonte em `erros["ranking"]`.

- [ ] **Step 1: Escrever os testes que falham** (no mesmo arquivo; importam a fixture `tela` de `test_campo_responsaveis`)

```python
def test_as_notas_do_app_chegam_a_usina_do_cadastro(tela):
    d = R.visao_responsaveis().dados
    a = d["ranking_por_usina"]
    # Altair: 2 rondas (90) + 3 tarefas fechadas pelo App (90, 70, 100); Brodowski 1: 1 ronda (90); Coração 1: nada
    assert a[1]["atual"] == {"q_soma": 440, "q_n": 5, "n_os": 3, "n_ronda": 2, "rondada": True}
    assert a[2]["atual"] == {"q_soma": 90, "q_n": 1, "n_os": 0, "n_ronda": 1, "rondada": True}
    assert a[3]["atual"]["rondada"] is False and a[3]["atual"]["q_n"] == 0
    assert d["tecnicos_por_equipe"]["SP Norte 01"] == 2 and d["tecnicos_por_equipe"]["SC Oeste 01"] == 1

def test_a_fonte_das_notas_que_falha_nao_derruba_a_visao(tela, monkeypatch):
    monkeypatch.setattr(R, "ranking_fonte", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("fato fora")))
    visao.limpar()
    d = R.visao_responsaveis().dados
    assert "fato fora" in d["erros"]["ranking"] and len(d["usinas"]) == 3 and d["ranking_por_usina"] == {}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_campo_ranking_equipes.py -q -k "chegam or derruba"`
Expected: FAIL (`KeyError: 'ranking_por_usina'`)

- [ ] **Step 3: Implementar** `ranking_fonte(b, hoje)` e, em `visao_responsaveis().calcular()`,
  `rk, rk_i = _ler_fonte("ranking", lambda: ranking_fonte(b, hoje), erros)` e as três chaves novas no retorno. As duas
  leituras já estão na cópia do ciclo quando a Visão é feita (medido no banco real em 18/10/2026: `_rondas_ligadas` 0,03 s e
  o fato de fechamento 0,00 s depois da conta da Visão): comentário com essa medida.

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_campo_ranking_equipes.py tests/test_campo_responsaveis.py -q`
Expected: PASS (os dois arquivos inteiros)

- [ ] **Step 5: Commit**

```bash
git add nexus/campo/responsaveis.py tests/test_campo_ranking_equipes.py
git commit -m "feat(campo): as notas do App por usina na cópia da Visão do responsável"
```

### Task 3: Os cartões e o que cobrar

**Files:**
- Modify: `nexus/campo/ranking_equipes.py`
- Test: `tests/test_campo_ranking_equipes.py`

**Interfaces:**
- Consumes: `responsaveis.soma(nome, usinas)` (import dentro da função: `responsaveis` importa este módulo); as usinas já
  com o bloco Manutenção (`responsaveis.com_manutencao`); `ranking_por_usina` e `tecnicos_por_equipe` da Task 2.
- Produces:
  - `etiquetas(s: dict, usinas: list[dict], limite: int) -> list[dict]`: `[{"cls": "critico"|"alerta", "txt": str}]`, o
    crítico primeiro e, dentro do nível, a ordem fixa abaixo; `[]` quando não há nada.
  - `cartoes(usinas: list[dict], por_usina: dict, tecnicos: dict, limite: int) -> dict`: `{"cartoes": [CARTAO], "total":
    int, "kpis": {"equipes": int, "tecnicos": int, "melhor": {"nota", "equipe"}|None, "menor": {...}|None,
    "amplitude": int|None}}`, com `CARTAO = {"equipe", "sem_equipe": bool, "usinas", "tecnicos", "regiao_campo",
    "base_pequena": bool, "posicao": int|None, "nota", "qualidade", "cobertura", "n_os", "n_ronda", "cor",
    "antes": {"nota", "posicao"}, "seta", "tri": {"perf", "acomp", "manut"}, "etiquetas": [até 4], "mais": int}`.
  - A ordem dos cartões: os sem nota (pelo nome), os ranqueados da última posição para a 1ª, e "Sem equipe" no fim, sem
    posição. A posição de antes é a da MESMA lista de equipes no período anterior. `kpis` contam as equipes de verdade
    (sem a "Sem equipe").

As etiquetas, na ordem fixa (nível; texto):

| # | Quando | Nível | Texto |
|---|---|---|---|
| 1 | `s["paradas_abertas"]` | crítico | "1 OS de parada aberta" / "2 OS de parada abertas" |
| 2 | `s["atrasadas"]` | crítico se a maior `manutencao.maior_atraso` das usinas > `limite`, senão alerta | "17 tarefas atrasadas, a mais antiga há 132 d" (1: "1 tarefa atrasada, há 12 d") |
| 3 | `s["paradas"]` (PT) | crítico | "2 PT paradas" / "1 PT parada" |
| 4 | usinas com `ronda.tipo` em nunca, sem_ronda, longa_pendente | crítico se alguma nunca ou sem_ronda, senão alerta | "2 usinas pedem ronda" / "1 usina pede ronda" |
| 5 | usinas com `acomp.valores.limpeza.cls` crítico (senão alerta) | o mesmo | "limpeza crítica em 1 usina" / "limpeza em atenção em 2 usinas" |
| 6 | `s["ext_vencidos"]` | crítico | "14 extintores vencidos" / "1 extintor vencido" |
| 7 | usinas com `meta.atingimento` < 97 | crítico se alguma < 90, senão alerta | "1 usina abaixo da meta" / "3 usinas abaixo da meta" |
| 8 | `s["disp"]` < 99 | crítico se < 80, senão alerta | "disp. 95,1%" |
| 9 | usinas com `manutencao.zeladoria_vencida` | alerta | "zeladoria vencida em 1 usina" |
| 10 | `s["semana_pct"]` < 85 | alerta | "semana passada 48%" |
| 11 | `s["chamados"]` | alerta | "1 chamado com o fabricante" / "2 chamados com o fabricante" |
| 12 | `s["tarefas_paradas"]` | alerta | "3 tarefas fora da programação" / "1 tarefa fora da programação" |

- [ ] **Step 1: Escrever os testes que falham**

```python
def _u(**kw):
    """Uma usina mínima para as etiquetas (só o que `etiquetas` lê)."""
    base = {"ronda": {}, "acomp": {"valores": {"limpeza": {"cls": "neutro"}}}, "meta": {}, "manutencao": {}}
    return {**base, **kw}

def test_etiquetas_na_regua_de_cada_tela():
    s = {"paradas_abertas": 1, "atrasadas": 17, "paradas": 2, "ext_vencidos": 14, "disp": 95.1, "semana_pct": 48.1,
         "chamados": 1, "tarefas_paradas": 3}
    us = [_u(ronda={"tipo": "sem_ronda"}, acomp={"valores": {"limpeza": {"cls": "critico"}}}, meta={"atingimento": 88.0},
             manutencao={"maior_atraso": 132, "zeladoria_vencida": "2026-10-01"}),
          _u(ronda={"tipo": "longa_pendente"}, meta={"atingimento": 99.0}, manutencao={"maior_atraso": 20})]
    assert [(e["cls"], e["txt"]) for e in RE.etiquetas(s, us, 30)] == [
        ("critico", "1 OS de parada aberta"), ("critico", "17 tarefas atrasadas, a mais antiga há 132 d"),
        ("critico", "2 PT paradas"), ("critico", "2 usinas pedem ronda"), ("critico", "limpeza crítica em 1 usina"),
        ("critico", "14 extintores vencidos"), ("critico", "1 usina abaixo da meta"), ("alerta", "disp. 95,1%"),
        ("alerta", "zeladoria vencida em 1 usina"), ("alerta", "semana passada 48%"),
        ("alerta", "1 chamado com o fabricante"), ("alerta", "3 tarefas fora da programação")]
    # o limite de quem olha: a mais antiga há 132 d com o limite 200 é atenção, e vai para depois dos críticos
    assert ("alerta", "17 tarefas atrasadas, a mais antiga há 132 d") in [(e["cls"], e["txt"]) for e in RE.etiquetas(s, us, 200)]

def test_sem_nada_a_cobrar_nao_ha_etiqueta():
    assert RE.etiquetas({"disp": 99.5, "semana_pct": 90}, [_u(meta={"atingimento": 98})], 30) == []

def test_cartoes_da_pior_para_a_melhor(tela):
    d = R.visao_responsaveis().dados
    r = RE.cartoes(R.com_manutencao(d["usinas"], 30), d["ranking_por_usina"], d["tecnicos_por_equipe"], 30)
    assert [c["equipe"] for c in r["cartoes"]] == ["SC Oeste 01", "SP Norte 01"]     # sem nota antes das ranqueadas
    sc, sp = r["cartoes"]
    assert (sc["posicao"], sc["nota"], sc["cor"]) == (None, None, "neutro")
    # SP Norte 01: (440 + 90) ÷ 6 = 88,3 -> 88; 2 de 2 usinas com ronda; 0,6 × 88 + 0,4 × 100 = 92,8 -> 93
    assert (sp["posicao"], sp["qualidade"], sp["cobertura"], sp["nota"], sp["cor"]) == (1, 88, 100, 93, "ok")
    assert (sp["n_os"], sp["n_ronda"], sp["tecnicos"], sp["usinas"], sp["base_pequena"]) == (3, 3, 2, 2, True)
    assert sp["seta"] == {"tipo": "sem", "n": 0} and r["total"] == 1
    assert r["kpis"] == {"equipes": 2, "tecnicos": 3, "melhor": {"nota": 93, "equipe": "SP Norte 01"},
                         "menor": {"nota": 93, "equipe": "SP Norte 01"}, "amplitude": 0}

def test_a_nota_e_refeita_sobre_as_usinas_do_filtro(tela):
    d = R.visao_responsaveis().dados
    so_brodowski = [u for u in R.com_manutencao(d["usinas"], 30) if u["usina"] == "Brodowski 1"]
    c = RE.cartoes(so_brodowski, d["ranking_por_usina"], d["tecnicos_por_equipe"], 30)["cartoes"][0]
    assert (c["usinas"], c["qualidade"], c["cobertura"], c["nota"]) == (1, 90, 100, 94)

def test_sem_equipe_vai_para_o_fim_sem_posicao(tela):
    d = R.visao_responsaveis().dados
    us = [dict(u, equipe=visao.SEM_EQUIPE) if u["usina"] == "Coração 1" else u for u in R.com_manutencao(d["usinas"], 30)]
    r = RE.cartoes(us, d["ranking_por_usina"], d["tecnicos_por_equipe"], 30)
    assert r["cartoes"][-1]["equipe"] == visao.SEM_EQUIPE and r["cartoes"][-1]["sem_equipe"]
    assert r["cartoes"][-1]["posicao"] is None and r["kpis"]["equipes"] == 1

def test_a_seta_contra_o_periodo_anterior(tela):
    d = R.visao_responsaveis().dados
    agg = lambda s, n: {"q_soma": s, "q_n": n, "n_os": n, "n_ronda": 0, "rondada": True}
    por = {1: {"atual": agg(450, 5), "anterior": agg(350, 5)}, 2: {"atual": agg(90, 1), "anterior": agg(70, 1)},
           3: {"atual": agg(80, 1), "anterior": agg(100, 1)}}
    r = {c["equipe"]: c for c in RE.cartoes(R.com_manutencao(d["usinas"], 30), por, d["tecnicos_por_equipe"], 30)["cartoes"]}
    assert (r["SP Norte 01"]["posicao"], r["SP Norte 01"]["antes"]["posicao"]) == (1, 2)
    assert r["SP Norte 01"]["seta"] == {"tipo": "sobe", "n": 1} and r["SC Oeste 01"]["seta"] == {"tipo": "desce", "n": 1}
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_campo_ranking_equipes.py -q`
Expected: FAIL (`AttributeError: ... 'etiquetas'`)

- [ ] **Step 3: Implementar** `etiquetas` e `cartoes` com as assinaturas e a tabela acima. O número vai com vírgula
  decimal como no resto da Visão (`responsaveis._virgula`); o porcentual da semana sem casa (`48%`), o da disponibilidade
  com uma (`95,1%`). Até 4 etiquetas no cartão e `mais` = o resto.

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_campo_ranking_equipes.py -q`
Expected: PASS (16)

- [ ] **Step 5: Commit**

```bash
git add nexus/campo/ranking_equipes.py tests/test_campo_ranking_equipes.py
git commit -m "feat(campo): os cartões do Ranking das equipes, da pior para a melhor, com a seta e o que cobrar"
```

### Task 4: A aba na tela, o filtro `equipe=` e o "×"

**Files:**
- Modify: `nexus/torres/campo/__init__.py` (`responsaveis()`, linhas ~362-419)
- Modify: `nexus/torres/campo/templates/campo/responsaveis.html` (barra das abas, linhas ~57-73; o bloco novo entre os
  cartões e o "Onde focar", linhas ~85-130; o mapa `fonte_nome`, linha 11)
- Modify: `nexus/static/campo.css` (classes novas `cr-rk-*` e `cr-tag--ok`, por token)
- Modify: `nexus/torres/campo/CLAUDE.md` (a linha da Visão em "As telas" e a seção nova abaixo de "O bloco Manutenção")
- Test: `tests/test_campo_responsaveis.py`

**Interfaces:**
- Consumes: `ranking_equipes.cartoes` (Task 3); as chaves da Task 2.
- Produces: `GET /t/campo/responsaveis?modo=ranking` (todas as equipes do filtro) e `?modo=foco&equipe=<nome exato>`.

Na rota: `modo` aceita `"ranking"`; o responsável logado fica em `"ranking"` se pediu, senão `"foco"` (nunca `"cartoes"`);
`equipe = request.args.get("equipe", "")` entra no `passa(u)` por igualdade (`u.get("equipe") == equipe`); o template recebe
`equipe` e `ranking` (`cartoes(...)` só quando `modo == "ranking"`). Na tela: a barra mostra "Por responsável" (só para quem
não é responsável), "Onde focar" e "Ranking das equipes" (`url(modo='ranking', equipe=None)`), agora também para o
responsável logado; o campo escondido `equipe` no formulário; o "×" do filtro de equipe na faixa de Onde focar
(`url(equipe=None)`); o bloco do ranking como no cartão v2 do protótipo aprovado: os quatro números de cima, a régua numa
frase (a do desenho, seção "Na tela", com as quatro diferenças contra o painel do App) e um `<a>` por cartão na grade
`cn-equipes cr-rk`, com `cn-equipe cn-equipe--{{ c.cor }}` (sem o modificador no `neutro`), indo a
`url(modo='foco', equipe=c.equipe, responsavel=responsavel or '*')`. O cartão leva o selo "base pequena"
(`cr-tag cr-tag--neutro`), a composição (ou "sem nota do App: nenhuma OS nem ronda pelo App em 30 dias"; na "Sem equipe",
"usinas sem equipe no cadastro: o conserto é no cadastro"), o semáforo dos três blocos com as macros `triagem` e
`triagem_leg` do próprio template, as etiquetas (`cr-tag cr-tag--{{ e.cls }}`) e "Ver as usinas da equipe em Onde focar".
Com `'ranking' in erros`, só o aviso "Não consegui ler as notas do App" e nenhum cartão. A 640 px os números de cima ficam
em 2 × 2.

- [ ] **Step 1: Escrever os testes que falham** (em `tests/test_campo_responsaveis.py`)

```python
def test_a_aba_ranking_das_equipes(tela, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=ranking").get_data(as_text=True)
    assert 'aria-current="page">Ranking das equipes</a>' in html and 'class="cn-equipes cr-rk"' in html
    assert html.index("SC Oeste 01") < html.index("SP Norte 01")             # sem nota antes da ranqueada
    assert "1º" in html and "de 1" in html and ">93<" in html and "sem nota do App" in html
    assert "60% qualidade" in html and "equipe=SP+Norte+01" in html and "modo=foco" in html

def test_o_responsavel_logado_ve_o_ranking_das_equipes_dele(tela, cliente):
    html = _responsavel(cliente).get("/t/campo/responsaveis?modo=ranking").get_data(as_text=True)
    assert ">Ranking das equipes</a>" in html and ">Por responsável</a>" not in html
    assert "SC Oeste 01" in html and "SP Norte 01" not in html                # Beltrano é o responsável da Coração 1
    html = cliente.get("/t/campo/responsaveis?modo=cartoes").get_data(as_text=True)
    assert 'id="cr-perf"' in html and 'class="cn-equipes"' not in html       # nunca os cartões dos outros

def test_o_filtro_de_equipe_em_onde_focar(tela, logado):
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=foco&equipe=SP+Norte+01").get_data(as_text=True)
    assert "Altair" in html and "Brodowski 1" in html and "Coração 1" not in html
    assert "Equipe SP Norte 01" in html and 'href="?responsavel=%2A&amp;modo=foco"' in html   # o "×" tira só a equipe
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=foco&equipe=SP+Norte").get_data(as_text=True)
    assert "Altair" not in html                                               # o nome exato, nunca um pedaço

def test_sem_as_notas_do_app_o_ranking_avisa(tela, logado, monkeypatch):
    monkeypatch.setattr(R, "ranking_fonte", lambda *a, **k: (_ for _ in ()).throw(ConnectionError("fato fora")))
    visao.limpar()
    html = logado.get("/t/campo/responsaveis?responsavel=*&modo=ranking").get_data(as_text=True)
    assert "Não consegui ler as notas do App" in html and 'class="cn-equipes cr-rk"' not in html
    assert 'id="cr-perf"' in logado.get("/t/campo/responsaveis?responsavel=*&modo=foco").get_data(as_text=True)
```

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_campo_responsaveis.py -q -k "ranking or filtro_de_equipe"`
Expected: FAIL (a aba não existe)

- [ ] **Step 3: Implementar** a rota, o template e o CSS como descrito acima (cor só por token; sem emoji; a seta em
  palavras: "sobe 3", "desce 2", "mesma posição", "sem nota antes").

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_campo_responsaveis.py tests/test_campo_ranking_equipes.py -q`
Expected: PASS (os dois arquivos inteiros, inclusive os testes antigos da Visão)

- [ ] **Step 5: Atualizar o `nexus/torres/campo/CLAUDE.md`**: na tabela "As telas", a linha da Visão cita a aba Ranking das
  equipes; seção nova "### O Ranking das equipes (18/10/2026)" depois de "O bloco Manutenção": para que serve (qual equipe
  cobrar), a régua (a do App, os 30 dias, a cor do painel do App), as quatro diferenças contra o painel do App, de onde vem
  cada número, onde mora a conta (`campo/ranking_equipes.py`, `responsaveis.ranking_fonte`), o filtro `equipe=` e a prova.
  Curto: o detalhe fica no desenho.

- [ ] **Step 6: Commit**

```bash
git add nexus/torres/campo/__init__.py nexus/torres/campo/templates/campo/responsaveis.html nexus/static/campo.css nexus/torres/campo/CLAUDE.md tests/test_campo_responsaveis.py
git commit -m "feat(campo): a aba Ranking das equipes na Visão do responsável e o filtro de equipe em Onde focar"
```

### Task 5: O Índice das rondas (Rondas › Painel)

**Files:**
- Modify: `nexus/torres/campo/templates/campo/rondas.html` (a nota da tela, linhas ~38-40; o subtítulo, linha ~192; o
  "sem índice no período", linha ~199; o cabeçalho da coluna, linha ~208)
- Modify: `nexus/campo/visao.py` (o comentário de `PESO_QUALIDADE`, linha 49; a docstring de `comparativos`, linhas ~1090-1096)
- Modify: `nexus/torres/campo/CLAUDE.md` (o item "Painel" de Rondas, linhas ~195-202)
- Test: `tests/test_campo_rondas_pedido_0810.py` (o teste dos destaques, linha ~250)

Só o texto: a chave `indice` e a conta não mudam. O texto novo diz que é "Índice das rondas = 60% da nota média das rondas +
40% cobertura", a fórmula do ranking por região do App só com as rondas, e que o Ranking das equipes da Visão do responsável
usa também as tarefas fechadas pelo App.

- [ ] **Step 1: Escrever o teste que falha** (no teste dos destaques, sobre a mesma página do Painel)

```python
    assert 'aria-sort="descending">Índice das rondas</th>' in html
    assert "Índice das rondas = 60% da nota média das rondas + 40% cobertura" in html
    assert "(a régua do ranking do App)" not in html
```

E troque, no mesmo teste, `"sem índice no período"` por `"sem índice das rondas no período"`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest tests/test_campo_rondas_pedido_0810.py -q`
Expected: FAIL (o cabeçalho ainda diz "Índice")

- [ ] **Step 3: Trocar os textos** nos três arquivos.

- [ ] **Step 4: Rodar e ver passar**

Run: `python -m pytest tests/test_campo_rondas_pedido_0810.py tests/test_campo_visao.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add nexus/torres/campo/templates/campo/rondas.html nexus/campo/visao.py nexus/torres/campo/CLAUDE.md tests/test_campo_rondas_pedido_0810.py
git commit -m "fix(campo): o Índice do Painel das Rondas vira Índice das rondas (o Ranking das equipes usa também as OS)"
```

### Task 6: A prova: a suíte inteira, a tela no navegador e o registro

**Files:**
- Modify: `nexus/torres/campo/CLAUDE.md` (a linha de prova da seção nova, com as medidas)

- [ ] **Step 1: A suíte inteira, uma vez** (em segundo plano: passa de 2 min)

Run: `python -m pytest -q`
Expected: tudo passa (anote o total; falha antiga sem relação com este trabalho é relatada, não consertada aqui)

- [ ] **Step 2: A tela com o banco real, sem senha no navegador.** Um script de rascunho FORA do repositório (o HTML tem nome
  de pessoa): as variáveis da cópia de prova (`NEXUS_CARGA_DADOS=0`, `NEXUS_CAMPO_AQUECER=0`, `NEXUS_CHAMADOS_PUBLICAR=0`,
  `NEXUS_OS_PUBLICAR=0`, `NEXUS_PCM_RELATORIOS_AUTO=0`, `NEXUS_CAMPO_COLETOR=""`), a trava
  `ferramentas/subir_copia_de_prova.instalar_trava()` (só GET sai), `create_app()`, `os_falhas.pedir_releitura` desligado,
  o `test_client` com `session_transaction` (`logado` e `admin`), e o HTML de: ranking de todos; ranking de um responsável
  com 11 ou 12 equipes; Onde focar com `equipe=`; e as mesmas no tema claro (a escolha de tema da sessão). O `static` ao
  lado, servido por `python -m http.server`.
- [ ] **Step 3: No navegador do app**, a 1440 × 900 e a 375 × 812, escuro e claro: sem rolagem lateral
  (`document.documentElement.scrollWidth <= innerWidth`), os cartões legíveis, a seta e as etiquetas nas cores. Screenshot
  de prova.
- [ ] **Step 4: O custo**: a conta fria da Visão antes (21,7 s, medida em 18/10/2026) e depois; o agrupamento no pedido.
- [ ] **Step 5: Registrar** no `nexus/torres/campo/CLAUDE.md` a prova e as medidas (equipes, notas, o tempo) e fazer o commit

```bash
git add nexus/torres/campo/CLAUDE.md
git commit -m "docs(campo): a prova do Ranking das equipes com o banco real"
```

- [ ] **Step 6: Não subir para a `main`.** Relatar ao Levi: o ramo, os commits, a suíte, as telas, e pedir o OK do push.
