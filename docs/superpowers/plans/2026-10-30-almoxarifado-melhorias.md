# Almoxarifado: as nove melhorias — plano de execução

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a tela PCM → Almoxarifado e o inventário com as nove melhorias do Levi de 30/10/2026, prontos antes do App.

**Architecture:** tudo no Nexus (Flask + Jinja + JS sem dependência), tolerante aos livros do App sem as colunas novas.
As contas puras ficam em `nexus/dados/almoxarifado.py` e `nexus/pcm/inventario/contas.py`; as telas leem pela mesma
cópia de 5 min de hoje; o que grava no Fracttal continua só na ponte `/os/_nexus/inventario`.

**Tech Stack:** Python 3, Flask, Jinja, pytest, JS puro (`filtro-local.js`, `nexusRota`), Pillow (fotos).

**Spec:** `docs/superpowers/specs/2026-10-30-almoxarifado-melhorias-design.md` (leia antes; ele decide o que este plano não
repete). As áreas: seções "Almoxarifado" e "Inventário do almoxarifado" do `nexus/pcm/CLAUDE.md`; `nexus/dados/CLAUDE.md`.

## Global Constraints

- pt-BR em tudo, comentários inclusive; comentário explica o porquê, com o caso real (Levi, 30/10/2026).
- Sem emoji na interface; severidade por cor e palavra. Cor só por token do `nexus/static/nexus.css` (nada de `#hex`/`rgba()`
  em CSS ou template), nos dois temas.
- Endereço nunca a partir da raiz: `{{ raiz }}`, `url_for`, `na_raiz()`, `nexusRota()` (`tests/test_prefixo.py`).
- Repositório público: nenhum nome de colega, e-mail, dado de cliente ou segredo; fixture com nome fictício.
- Coluna nova de livro só no FIM, nos dois lados; o livro sem a coluna nova continua lido (mostra "–" ou nada).
- Número pela metade não vai à tela; dado que o Fracttal não deu nunca vira 0 nem "C".
- Motivo e texto livre só cifrados (`dados={"motivo": ...}`); pessoa como `pessoa_hmac`/`pessoa_id`; usina por ID.
- A tela funciona em 375 px (tabela vira cartão com `data-r`); acessível (foco visível, `aria-*`).
- Cada tarefa atualiza a seção do `nexus/pcm/CLAUDE.md` (ou do `nexus/dados/CLAUDE.md`) que muda, corrigindo a linha velha.
- Testes por tarefa: só os arquivos citados + `tests/test_prefixo.py`; a suíte inteira só no fim. O teste de nomes precisa
  do `.env` na worktree (já está lá).
- Commit por tarefa no ramo `inventario-almox` da worktree `C:/GridcoAuto/wt/nexus-inventario`; nada de push.

## Review Focus

- Livro do App da versão de hoje (sem Criticidade, Curva ABC, Custo, Fabricante...): nenhuma tela quebra e nenhuma diz
  "sem curva"/"sem custo" para tudo (a coluna ausente não é a coluna vazia). Testes em T2, T4 e T8.
- Recontagem que chega com a original ainda pendente, depois uma contagem inteira nova: a ordem da substituição (T5).
- Avariado contado pela aba e o -AV contado direto na mesma contagem; -AV criado hoje que o catálogo diário ainda não tem (T6).
- A rota pública das fotos: chave com `../`, reenvio fora da janela, arquivo de 50 MB, GET (T7).
- Trocar de aba com um filtro escolhido: as contas da lista são as da aba à vista; aba sem tabela esconde o filtro (T2,
  prova no navegador).

---

### Task 1: o contrato e o histórico com as colunas novas

**Files:**
- Modify: `nexus/dados/almoxarifado.py` (colunas, tipos e três ajudantes)
- Modify: `nexus/dados/fato_almoxarifado.py` (`CAB_DIM_ITEM`, `CAB_SALDO`, `dim_itens`, `saldo_do_ciclo`)
- Modify: `nexus/dados/catalogo.py` (o texto do fato `saldo_almox` e da dimensão do item), `nexus/dados/CLAUDE.md`
- Test: `tests/test_dados_almoxarifado.py`, `tests/test_pcm_inventario_contrato.py`

**Interfaces:**
- Produces: `A.COLUNAS_ITENS[-2:] == ("Criticidade", "Curva ABC")`; `A.COLUNAS_SALDO[-1] == "Custo unitário"`;
  `A.COLUNAS_CONTAGENS[14:] == ("Fabricante", "Modelo", "Número de série", "Fotos dos dados", "Recontagem de")`;
  `A.TIPOS_CONTAGEM == ("item", "identificar", "fora_do_catalogo", "avariado")`; `A.NA = "n/a"`;
  `A.curva_abc(v) -> str` ("A" | "B" | "C" | ""); `A.custo(v) -> float | None`;
  `A.fotos_dos_dados(v) -> dict[str, str]` (rótulos `fabricante`, `modelo`, `serie`).
  Histórico: `CAB_DIM_ITEM` termina em `["criticidade", "curva_abc"]`; `CAB_SALDO` termina em `["custo_unitario_brl"]`.

- [ ] **Step 1: testes que falham**

```python
def test_colunas_novas_no_fim():
    assert A.COLUNAS_ITENS[-2:] == ("Criticidade", "Curva ABC")
    assert A.COLUNAS_SALDO[-1] == "Custo unitário"
    assert A.COLUNAS_CONTAGENS[13] == "ID da linha"
    assert A.COLUNAS_CONTAGENS[14:] == ("Fabricante", "Modelo", "Número de série", "Fotos dos dados", "Recontagem de")
    assert A.TIPOS_CONTAGEM[-1] == "avariado"

def test_curva_abc_normaliza():
    assert [A.curva_abc(v) for v in ("A", "b", " Curva C ", "c - baixo giro")] == ["A", "B", "C", "C"]
    assert [A.curva_abc(v) for v in ("", None, "X", "AB", "1")] == ["", "", "", "", ""]

def test_custo_so_positivo():
    assert A.custo("12,5") == 12.5 and A.custo(3) == 3.0
    assert [A.custo(v) for v in ("0", "-3", "", None, "nan", "abc")] == [None] * 6

def test_fotos_dos_dados():
    assert A.fotos_dos_dados("fabricante:k1|modelo:k2|serie:k3") == {"fabricante": "k1", "modelo": "k2", "serie": "k3"}
    assert A.fotos_dos_dados("modelo:k2|outro:k9|serie:") == {"modelo": "k2"}
    assert A.fotos_dos_dados("") == {} and A.fotos_dos_dados(None) == {}
```

Mais dois no histórico: `test_historico_leva_criticidade_e_curva` (`dim_itens` de um item com "Criticidade" "1.Crítico" e
"Curva ABC" "a" grava `"1.Crítico"` e `"A"`; o item sem as colunas grava `""` nas duas) e `test_saldo_do_ciclo_leva_custo`
(`"Custo unitário"` "15,5" → 15.5; ausente ou "0" → `""`). Atualize as asserções que fixam o contrato antigo
(`test_dados_almoxarifado.py` fixa a última coluna do Saldo; `test_pcm_inventario_contrato.py` fixa as 14 colunas).

- [ ] **Step 2:** `python -m pytest tests/test_dados_almoxarifado.py tests/test_pcm_inventario_contrato.py -q` → falham.
- [ ] **Step 3: implementar.** `curva_abc`: a primeira letra A/B/C isolada depois de tirar "curva" e espaços (regex
  `^(?:curva\s*)?([abc])(?:\b|\s|-|$)`, sem caixa); `custo`: `A.numero(v)` finito e > 0, senão None; `fotos_dos_dados`:
  divide por `|` e por `:` na primeira ocorrência, só os três rótulos, chave vazia fica de fora. No histórico, a coluna
  nova no fim de cada linha (o livro é republicado inteiro pelo `livros.publicar`; confira no teste com o `pg_falso` que a
  linha velha sem a coluna e a nova convivem). Catálogo e `nexus/dados/CLAUDE.md`: a dimensão do item ganha criticidade e
  curva (as do cadastro do Fracttal), o saldo ganha o custo; o grão não muda.
- [ ] **Step 4:** os mesmos testes passam, mais os `tests/test_dados_*.py` que conferem o catálogo (`grep -l catalogo tests/test_dados_*.py`).
- [ ] **Step 5:** commit `feat(dados): o contrato do almoxarifado com criticidade, Curva ABC e custo, e as colunas novas da contagem`.

### Task 2: filtro por aba, saldo unitário e a ordem da Reposição (itens 7 e 8)

**Files:**
- Modify: `nexus/pcm/almoxarifado.py` (`_do_app`, `_do_nexus`, `_partes`)
- Modify: `nexus/templates/pcm/almoxarifado.html` (Reposição, o número do alto, Cadastro a corrigir, o script das abas)
- Test: `tests/test_pcm_almoxarifado.py`

**Interfaces:**
- Consumes: T1 (`A.curva_abc`, `A.custo`, as colunas).
- Produces: em cada linha de `d["linhas"]`: `criticidade` (texto do Fracttal), `crit_n` (int ou None, pelo
  `revisao._criticidade`), `curva` ("A"/"B"/"C"/""), `custo` (float ou None); situação nova `"saldo_unitario"`;
  `d["saldo_unitario"]` (lista); `d["kpis"]["saldo_unitario"]`; `fonte["tem_criticidade"]`, `fonte["tem_curva"]`,
  `fonte["tem_custo"]` (a coluna existe no livro); cada cartão de `d["por_almoxarifado"]` com `saldo_unitario`.

- [ ] **Step 1: testes que falham**
  - `test_saldo_unitario_sai_do_limite`: saldo 1 e mínimo 1 → situação `saldo_unitario`, fora de `d["reposicao"]`, em
    `d["saldo_unitario"]`, `kpis["no_limite"]` sem ela, `kpis["saldo_unitario"] == 1`; saldo 2 e mínimo 2 continua `no_limite`.
  - `test_reposicao_ordena_dentro_do_grupo`: abaixo comum (falta 5), abaixo "1.Crítico" (falta 1) e no limite "1.Crítico"
    → ordem: o abaixo crítico, o abaixo comum, o no limite crítico. Curva desempata dentro da criticidade (A antes de B,
    "" por último), a falta depois.
  - `test_livro_de_hoje_sem_colunas_novas`: os livros sem Criticidade/Curva/Custo → as linhas com `criticidade == ""`,
    `curva == ""`, `custo is None`, `tem_curva` falso, a ordem de hoje, e o Cadastro a corrigir SEM a linha "sem Curva ABC".
  - `test_cadastro_sem_curva_e_sem_criticidade`: com as colunas e duas peças com saldo sem curva → a linha "2 peças com
    saldo sem Curva ABC no Fracttal" (e a da criticidade).
  - `test_a_troca_de_aba_refaz_o_filtro`: o HTML da tela tem `FiltroLocal['alm-f'].aplicar` no script das abas e o
    formulário ganha `data-alm-filtro`.
- [ ] **Step 2:** `python -m pytest tests/test_pcm_almoxarifado.py -q` → falham.
- [ ] **Step 3: implementar.** `_situacao(saldo, minimo) -> str` em `almoxarifado.py` embrulha `A.situacao` (não mude
  `A.situacao`: o histórico usa). `_ordem(x) -> tuple` = `(crit_n or 99, {"A": 0, "B": 1, "C": 2}.get(curva, 3), ...)` e,
  depois, a chave de hoje do grupo (abaixo: `-falta`; no limite e saldo unitário: `(almox, codigo)`). Template: colunas Crit.
  (o quadradinho `.crit c1..c4` que a Aprovação do inventário já usa; sem criticidade "–") e Curva; o saldo unitário num
  `<details>` fechado logo abaixo da tabela, com a frase do desenho e a mesma tabela (no mesmo `data-fl-grupo`); o número do
  alto "N no limite (+M de saldo unitário)"; a ajuda da Reposição diz a ordem. Script das abas: depois de mostrar o painel,
  `form.hidden = !painel.querySelector('[data-fl-grupo="alm-f"]')` e, se `window.FiltroLocal && FiltroLocal['alm-f']`,
  `.aplicar()` (o `dispatchEvent('input')` no formulário de hoje não chega a ninguém: sai).
- [ ] **Step 4:** os testes passam, mais `tests/test_prefixo.py`.
- [ ] **Step 5:** commit `feat(pcm): Almoxarifado - o filtro conta a aba à vista, o saldo unitário sai do "no limite" e a Reposição por criticidade e curva`.

### Task 3: a aba Avariadas, parada há quanto tempo (item 6)

**Files:**
- Modify: `nexus/pcm/almoxarifado.py`, `nexus/templates/pcm/almoxarifado.html`
- Test: `tests/test_pcm_almoxarifado.py`

**Interfaces:**
- Consumes: T2 (linhas com `custo`), `regua.avariada(codigo, marca=False) -> bool` (`nexus/pcm/inventario/regua.py:56`), os
  ciclos aplicados e as fotos do Saldo do histórico (`F.ABA_CICLO`, `F.livro_do_mes`, `F.ABA_SALDO`).
- Produces: `_paradas(chaves: set[tuple[str, str]], hoje) -> dict[tuple[str, str], dict]` com `{"desde": "dd/mm/aaaa",
  "dias": int, "pelo_menos": bool, "inicio": "dd/mm/aaaa"}` por (id_item, id_almox); `d["avariadas"]` (lista, a mais parada
  primeiro: `codigo`, `nome`, `almox`, `usina`, `saldo`, `dias`, `desde`, `pelo_menos`, `valor` ou None);
  `kpis["avariadas"]` = `len(d["avariadas"])`.

- [ ] **Step 1: testes que falham**
  - `test_avariada_parada_ha_n_dias`: três ciclos aplicados (01/10, 15/10, 29/10), a avariada com saldo 0, 2, 2 → `desde`
    15/10, `dias` = hoje − 15/10, `pelo_menos` falso.
  - `test_avariada_desde_o_inicio_diz_pelo_menos`: saldo > 0 nos três → `pelo_menos` verdadeiro e `inicio` 01/10.
  - `test_ciclo_anulado_nao_conta`: o ciclo anulado do meio não interrompe nem conta.
  - `test_avariada_pela_marca_e_pelo_av`: "SP-3-AV" sem marca e "SP-9" com a marca "Avariado" entram; "SP-AVR-001" não.
  - `test_avariada_sai_do_cadastro_a_corrigir` e `test_kpi_avariadas_conta_com_saldo` (catálogo com 3 avariadas, 1 com
    saldo → 1, e a nota "com saldo").
  - `test_sem_historico_avariada_sem_dias`: sem ciclo aplicado no Nexus → `dias` None e a tela diz "sem histórico ainda".
- [ ] **Step 2:** `python -m pytest tests/test_pcm_almoxarifado.py -q` → falham.
- [ ] **Step 3: implementar.** `_paradas` lê os ciclos bons (aplicado, não anulado) em ordem, abre só os livros dos meses
  deles e filtra as chaves pedidas; anda do ciclo mais novo para trás enquanto o saldo > 0. Roda dentro do `calcular()` (a
  cópia de 5 min). Aba Avariadas (tabela filtrável: peça, almoxarifado, saldo, parada, valor quando `tem_custo`); o cartão
  do alto vira botão `data-aba="avariadas"`; as linhas de avariada saem do Cadastro a corrigir.
- [ ] **Step 4:** os testes passam.
- [ ] **Step 5:** commit `feat(pcm): Almoxarifado - a aba Avariadas com há quanto tempo cada uma está parada sem destino`.

### Task 4: Por almoxarifado — as peças no clique, a última contagem e o valor por curva (itens 1 e 9)

**Files:**
- Modify: `nexus/pcm/almoxarifado.py` (rota nova e o cartão), `nexus/templates/pcm/almoxarifado.html`
- Create: `nexus/templates/pcm/_almox_pecas.html`
- Test: `tests/test_pcm_almoxarifado.py`

**Interfaces:**
- Consumes: T2/T3 (linhas com `situacao`, `crit_n`, `curva`, `custo`), `leitura.contagens(cfg)` (estado, `id_almox`,
  `contada_em`).
- Produces: rota `GET /t/pcm/pecas/almox/<id_almox>` (endpoint `pecas_almox`) → o pedaço HTML; no cartão:
  `ultima_contagem` ("dd/mm/aaaa", "" = nunca, None = não leu), `valor` (`{"total", "A", "B", "C", "sem_curva"}` ou None),
  `sem_custo` (int).

- [ ] **Step 1: testes que falham**
  - `test_ver_pecas_do_almoxarifado`: a rota devolve só as peças daquele almoxarifado, na ordem abaixo → no limite → saldo
    unitário → sem mínimo → ok, e dentro por criticidade e curva; `test_ver_pecas_almox_desconhecido_404`; a rota usa a
    mesma conta guardada (`montar` chamado, nenhuma leitura nova dos livros).
  - `test_cartao_ultima_contagem_gravada`: duas contagens gravadas do almoxarifado (05/10 e 20/10) e uma nova de 25/10 →
    "20/10/2026"; `test_cartao_nunca_contado` → "nunca contado pelo inventário"; `test_cartao_inventario_nao_leu` (a leitura
    levanta `Recusada`) → a linha não aparece.
  - `test_valor_por_curva`: A saldo 2 × 10, sem curva 1 × 5 e uma peça com saldo sem custo → total 25, A 20, sem curva 5,
    "1 peça sem custo no Fracttal"; `test_sem_coluna_custo_nao_mostra_valor`.
- [ ] **Step 2:** `python -m pytest tests/test_pcm_almoxarifado.py -q` → falham.
- [ ] **Step 3: implementar.** A rota filtra `montar().dados["linhas"]` por `id_almox`, com o mesmo controle de acesso da
  tela; a última contagem e o valor se montam na `tela()`, fora da cópia de 5 min (como o `inventario_a_revisar`). O botão
  "Ver peças" (`aria-expanded`, `aria-controls`) busca com `fetch(nexusRota(...))` só na 1ª abertura e mostra "lendo…";
  erro: "não consegui abrir as peças agora". O pedaço é a tabela `.alm-t` (Código · Peça · Crit. · Curva · Saldo · Mínimo ·
  Situação), cartão em 375 px.
- [ ] **Step 4:** os testes passam, mais `tests/test_prefixo.py`.
- [ ] **Step 5:** commit `feat(pcm): Almoxarifado - abrir um almoxarifado mostra as peças, a última contagem gravada e o valor por curva`.

### Task 5: pedir recontagem só das peças marcadas (item 4)

**Files:**
- Modify: `nexus/dados/fato_inventario.py` (`TIPOS_EVENTO` + `"recontagem_item_pedida"`)
- Modify: `nexus/pcm/inventario/leitura.py` (`recontagem_de` na contagem; `revisao_da` com `recontar`; `estado_dos_eventos`)
- Modify: `nexus/pcm/inventario/contas.py` (`substituidas`; `itens_do_lote` com `recontar`)
- Modify: `nexus/pcm/inventario/revisao.py` (ação `recontagem_itens`; a nota; o rótulo da lista)
- Modify: `nexus/templates/pcm/_inventario_lote.html`, `nexus/templates/pcm/inventario_contagem.html`, o JS da revisão
- Test: `tests/test_pcm_inventario_contas.py`, `tests/test_pcm_inventario_leitura.py`, `tests/test_pcm_inventario_telas.py`

**Interfaces:**
- Consumes: T1 (`"Recontagem de"`).
- Produces: contagem com `recontagem_de: str` ("" quando não é); `revisao_da(...)["recontar"]: {id_item: motivo}`; entrada do
  lote com `recontar: bool` (e `tirada` verdadeiro junto: fora do lote pelos caminhos de hoje); `POST .../revisar` com
  `{"acao": "recontagem_itens", "itens": [id_item, ...], "motivo": str}` → `{"ok": true, "n": int}`.

- [ ] **Step 1: testes que falham**
  - Contas: `test_recontagem_nao_substitui_a_original` (original 10:00 pendente, recontagem dela 12:00 → nenhuma
    substituída); `test_original_mais_velha_nao_substitui_a_recontagem`; `test_inteira_nova_substitui_a_recontagem`
    (inteira 14:00 → a original e a recontagem não gravadas substituídas); `test_recontagem_gravada_fica`;
    `test_recontar_tira_do_lote` (`itens_do_lote` com `revisao={"recontar": {"9": "m"}}` → a 9 com `recontar` e `tirada`).
  - Leitura: `test_evento_recontagem_item_deixa_revisada` (estado `revisada`, aprovável); `test_revisao_da_recontar`.
  - Telas/revisar: `test_recontagem_parcial_um_evento_por_peca` (dois itens → dois eventos `recontagem_item_pedida`, motivo
    só cifrado, `usina_id`, `pessoa_hmac`); `test_recontagem_parcial_sai_do_gravar` (o N do "Gravar N alterações" sem elas e
    a nota "recontagem pedida em dd/mm" em "não será tocada"); recusas: lista vazia 400, sem motivo 400, peça fora da contagem
    400, achado sem `id_item` 400, peça já pedida 409, peça tirada 409, `corrigir` peça em recontagem 409, contagem já na
    gravação 409, outro setor 403; `test_recontagem_inteira_continua` (a ação `recontagem` de hoje mata a contagem);
    `test_a_aprovacao_tem_as_caixas` (uma caixa por peça marcável, "marcar todas", o botão com o N, o botão "Recontar a
    contagem inteira"); `test_a_lista_diz_recontagem_de`.
- [ ] **Step 2:** `python -m pytest tests/test_pcm_inventario_contas.py tests/test_pcm_inventario_leitura.py tests/test_pcm_inventario_telas.py -q` → falham.
- [ ] **Step 3: implementar.** `substituidas`: a chave de ordem de hoje `(contada, enviada, cid)`; as inteiras (sem
  `recontagem_de`) competem como hoje; a recontagem não gravada fica velha só se uma INTEIRA do mesmo almoxarifado tiver
  chave maior. Quem chama passa `recontagem_de` em cada contagem. A ação valida tudo antes de gravar e grava todos os
  eventos de uma vez (`F.acrescentar` com a lista). Front: caixas na tabela da Aprovação (só nas peças com ação; `marcar
  todas` marca as marcáveis), o botão abre a mesma caixa de motivo das outras ações; o fetch vai à rota `revisar` de hoje.
- [ ] **Step 4:** os testes passam, mais `tests/test_pcm_inventario_gravacao.py` (o lote congelado sem as peças a recontar).
- [ ] **Step 5:** commit `feat(pcm): inventário - pedir recontagem só das peças marcadas; o resto da contagem segue`.

### Task 6: avariados na contagem (item 5)

**Files:**
- Create: `nexus/pcm/inventario/avariados.py`
- Modify: `nexus/pcm/inventario/leitura.py` (aplica o `resolver` em `ler`), `contas.py` (`dobro`), `curadoria.py` (tipo
  `avariado`, o cadastrar com o código -AV), `estoque.py` (`criar_peca(..., descricao="")`, real e falso), `revisao.py`/`_inventario_lote.html` (a nota)
- Test: `tests/test_pcm_inventario_avariados.py` (novo), `tests/test_pcm_inventario_curadoria.py`, `tests/test_pcm_inventario_contas.py`

**Interfaces:**
- Consumes: T1 (`"avariado"`), `leitura.ler(cfg)["itens"]` (`{id_item: {codigo, nome, unidade}}`), `regua.avariada`.
- Produces: `avariados.codigo_av(codigo: str) -> str`; `avariados.resolver(linhas: list[dict], itens: dict[str, dict])
  -> list[dict]` (cópias; a linha resolvida vira `Tipo` "item" com o ID e o Código do -AV e a marca `"_avariado_de": id_bom`;
  a não resolvida fica `avariado`); `curadoria.DECISOES_DO_TIPO["avariado"] == ("cadastrar", "e_a_peca", "descartar")`;
  entrada do lote com `dobro: bool` (com `invalido` verdadeiro junto: o caminho de hoje do contado inválido).

- [ ] **Step 1: testes que falham**
  - `test_codigo_av`: `codigo_av(" sp-3 ") == "SP-3-AV"`.
  - `test_resolver_acha_o_av` (catálogo com "SP-3" e "SP-3-AV" → a linha avariada de SP-3 vira item do -AV com
    `_avariado_de`); `test_resolver_sem_av_fica_avariado`; `test_resolver_nao_mexe_nas_outras`; `test_resolver_sem_caixa`.
  - Contas: `test_avariado_entra_no_lote_como_peca_av`; `test_avariado_nao_resolvido_vai_a_curadoria`;
    `test_avariado_em_dobro_fora_do_lote` (a mesma contagem com o -AV direto e pela aba → `dobro`, fora do N);
    `test_dobro_corrigido_entra`; `test_avariado_em_branco_nao_zera`.
  - Curadoria: `test_avariada_sem_cadastro_na_lista` (o rótulo "avariada sem cadastro" e o -AV que falta);
    `test_cadastrar_avariado_usa_o_codigo_av` (`EstoqueFalso`: cria com o código `SP-3-AV`, o nome no padrão dos -AV do
    catálogo e a unidade do bom, nunca um `SP-<sigla>-NNN`); `test_cadastrar_avariado_que_ja_existe_no_fracttal_liga`
    (`achar_peca` acha → decisão `e_a_peca` com aquele id, sem criar).
- [ ] **Step 2:** `python -m pytest tests/test_pcm_inventario_avariados.py tests/test_pcm_inventario_curadoria.py tests/test_pcm_inventario_contas.py -q` → falham.
- [ ] **Step 3: implementar.** O `resolver` roda UMA vez, em `leitura.ler`, sobre as linhas de cada contagem: tudo o que vem
  depois (lote, curadoria, contas da lista) vê as linhas resolvidas. Em `contas._ler`, o `avariado` não resolvido segue o
  caminho do `fora_do_catalogo` (achado que a decisão da curadoria leva a uma peça); a linha com `_avariado_de` cuja peça
  também veio direta marca `dobro`. O padrão do nome do -AV: leia os -AV do livro Itens do App no banco (sem gravar nada) e
  escreva o padrão achado no docstring do módulo; sem nenhum -AV no catálogo, `"<nome do bom> [AVARIADO]"` (o que a régua
  de 14/10 cita). `criar_peca` ganha `descricao=""` (vai no `description` do `item_insert`, passo 0) para a T8 usar.
- [ ] **Step 4:** os testes passam, mais `tests/test_pcm_inventario_estoque.py` e `tests/test_pcm_inventario_telas.py`.
- [ ] **Step 5:** commit `feat(pcm): inventário - os avariados na contagem pelo código -AV, com a curadoria quando o -AV não existe`.

### Task 7: a rota das fotos do inventário (item 3, o transporte)

**Files:**
- Create: `nexus/pcm/inventario/fotos_app.py`
- Modify: `nexus/pcm/inventario/curadoria.py` (a rota de receber; a de servir ganha `?mini=1`), `nexus/auth/__init__.py`
  (`ROTAS_PUBLICAS` + o comentário)
- Test: `tests/test_pcm_inventario_fotos.py` (novo)

**Interfaces:**
- Consumes: `curadoria.nome_da_foto(chave)`, `curadoria._pasta_fotos(cfg)`, `hseq.fotos.reduzir` (a cópia reduzida).
- Produces: `fotos_app.ROTULO_CHAVE = b"nexus:pcm:fotos-inventario"`; `fotos_app.chave(cfg) -> bytes | None`;
  `fotos_app.assinatura(k: bytes, chave_foto: str, ts, dados: bytes) -> str` (HMAC-SHA256 de
  `f"{chave_foto}|{int(ts)}|{sha256(dados).hexdigest()}"`); `fotos_app.receber(cfg, chave_foto, ts, assinatura, dados,
  agora=None) -> tuple[int, str]`; rota `POST /t/pcm/pecas/inventario/foto` (endpoint `torre_pcm.inventario_foto_receber`,
  campos `chave`, `ts`, `assinatura`, arquivo `foto`).

- [ ] **Step 1: testes que falham:** `test_recebe_e_guarda` (a foto e a miniatura de 160 px no nome da chave);
  `test_mesma_chave_substitui`; `test_assinatura_errada_401`; `test_fora_da_janela_401` (15 min); `test_nao_imagem_400`;
  `test_maior_que_8mb_400`; `test_chave_vazia_ou_longa_400` (mais de 200 caracteres ou caractere de controle);
  `test_chave_com_barras_nao_vira_caminho` (`../x` grava só `<sha1>.jpg` dentro da pasta); `test_sem_hmac_503`;
  `test_rota_publica_so_post` (GET não serve); `test_mini_so_para_quem_pode_programar`; e o
  `test_toda_rota_nao_publica_exige_login` de hoje continua passando.
- [ ] **Step 2:** `python -m pytest tests/test_pcm_inventario_fotos.py tests/test_auth*.py -q` → falham.
- [ ] **Step 3: implementar** no molde do `nexus/hseq/fotos.receber`, sem o código em maiúsculas nem o `dia`; a rota segue
  o precedente `torre_pcm.motivo_do_app` (o que ele faz com a origem e o CSRF, esta faz igual).
- [ ] **Step 4:** os testes passam.
- [ ] **Step 5:** commit `feat(pcm): inventário - a rota assinada que recebe as fotos do App`.

### Task 8: a curadoria com fabricante, modelo, série e as fotos ampliadas (itens 2 e 3)

**Files:**
- Modify: `nexus/pcm/inventario/curadoria.py` (`pendencias`; o cadastrar leva a descrição)
- Modify: `nexus/templates/pcm/inventario_curadoria.html` (os dados, as miniaturas, a caixa da foto), `nexus/static/pcm.css`
- Create: `nexus/static/pcm-fotos.js`
- Test: `tests/test_pcm_inventario_curadoria.py`

**Interfaces:**
- Consumes: T1 (`A.fotos_dos_dados`, `A.NA`), T6 (`criar_peca(..., descricao=)`), T7 (as fotos no disco; `?mini=1`).
- Produces: cada pendência com `fabricante`, `modelo`, `serie` (texto; `A.NA` vira "não tem"; ausente "") e `fotos`: lista de
  `{"rotulo": "Peça" | "Fabricante" | "Modelo" | "Número de série", "foto_id": str, "tem": bool}`.

- [ ] **Step 1: testes que falham:** `test_curadoria_mostra_fabricante_modelo_serie`; `test_curadoria_na_vira_nao_tem`;
  `test_curadoria_fotos_com_rotulo` (a "Foto" e as três dos dados, na ordem Peça, Fabricante, Modelo, Número de série);
  `test_curadoria_foto_que_nao_chegou` ("foto ainda não chegou"); `test_curadoria_livro_de_hoje` (sem as colunas novas:
  a tela de hoje); `test_a_caixa_da_foto` (um `<dialog>` com a imagem, a legenda, "Anterior", "Próxima" e "Fechar" com
  `aria-label`, e as miniaturas como `<button>`); `test_cadastrar_leva_fabricante_modelo_serie` (`EstoqueFalso` recebe a
  descrição "Fabricante: X · Modelo: Y · Série: Z", sem as partes "n/a"); cores por token.
- [ ] **Step 2:** `python -m pytest tests/test_pcm_inventario_curadoria.py -q` → falham.
- [ ] **Step 3: implementar.** A caixa: `<dialog>` com `showModal()`; Esc fecha (nativo); setas ← → passam entre as fotos do
  mesmo achado; ao fechar o foco volta à miniatura que abriu; a imagem grande é a rota de hoje sem `mini`, carregada só ao
  abrir. A miniatura usa `?mini=1` com `loading="lazy"`.
- [ ] **Step 4:** os testes passam, mais `tests/test_prefixo.py`.
- [ ] **Step 5:** commit `feat(pcm): inventário - a curadoria com fabricante, modelo, número de série e as fotos ampliadas`.

### Task 9: o contrato do App e a prova (controlador)

- [ ] Atualizar `C:\GridcoBuild\app-campo-docs\_propostas\inventario-contagens\CONTRATO.md` (as 5 colunas novas, o tipo
  `avariado`, a aba Avariados, fabricante/modelo/série com "n/a" e as fotos obrigatórias, a rota das fotos com a assinatura,
  os eventos `recontagem_item_pedida` e a coluna "Recontagem de", o "atendida") e a proposta da varredura em
  `_propostas/almoxarifado-nexus` (Criticidade e Curva ABC no Itens, Custo unitário no Saldo).
- [ ] Suíte inteira: `python -m pytest -q`.
- [ ] Prova no navegador na cópia de prova com o `EstoqueFalso` (porta 5180–5189): desktop e 375 px, escuro e claro, os
  pontos da seção Prova do desenho; fotos para o Levi.
