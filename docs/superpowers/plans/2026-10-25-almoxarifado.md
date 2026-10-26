# Almoxarifado no PCM — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a tela PCM → Almoxarifado (reposição, por almoxarifado, catálogo, consumo nas OS, cadastro a corrigir), lendo
o que o App de Campo publica da varredura diária do inventário do Fracttal, e o histórico guardado no banco pelo Nexus.

**Architecture:** o App publica 4 livros (Ciclo, Itens, Saldo, Peças). Um módulo puro (`nexus/dados/almoxarifado.py`)
tem o contrato e as contas, usado pela tela e pela carga. O `fato_almoxarifado.py` monta os fatos. A
`carga.gerar_almoxarifado` roda no laço de hora em hora com portão próprio e grava `nexus_almoxarifado` e a família
`nexus_almoxarifado_saldo_AAAA_MM`, só com `NEXUS_ALMOX_GRAVAR=1` (antes disso, ensaio). A tela lê os livros do App
pelo `visao` do Campo e o Consumo pelo fato do Nexus.

**Tech Stack:** Python 3 / Flask / Jinja, API de planilhas `db_performace` (`livros.py`, `visao.py`), pytest com
`tests/pg_falso.py`; no App, Azure Functions (`function_app.py` v300).

**Spec:** `docs/superpowers/specs/2026-10-25-almoxarifado-design.md` (aprovado pelo Levi em 25/10/2026).

## Global Constraints

- pt-BR em tudo, inclusive comentários; comentário diz o porquê, com o caso real.
- Repositório PÚBLICO: nenhum nome de colega, e-mail, CPF ou segredo; fixtures com nomes fictícios. Copie o `.env` da
  pasta do Levi para a worktree antes da suíte (o `test_sem_nomes_no_repositorio.py` só roda com ele).
- Cor só por token do `nexus.css` (nada de `#hex`/`rgba()` em CSS nem template); sem emoji; severidade por cor e palavra.
- Endereço nunca a partir da raiz: `{{ raiz }}`, `url_for`, `|na_raiz`, `nexusRota()`, ou `?` relativo.
- O Nexus não chama o Fracttal nesta entrega. Nada grava no Fracttal.
- Pessoa só por HMAC (`NEXUS_PESSOA_HMAC`) → `pessoa_id`; o texto do erro do Fracttal nunca vai ao banco.
- Livro novo do Nexus registrado em `catalogo.LIVROS` antes de existir; nome `nexus_<assunto>`, abas `fato_*`, `dim_*`,
  `qualidade`, `atualizacao`.
- A carga do almoxarifado só grava com `NEXUS_ALMOX_GRAVAR=1` no `.env` (Levi, 25/10/2026: o Nexus sobe antes, em
  ensaio).
- Consumo nas OS: tudo desde o início, sem corte, no número do topo e na aba (Levi, 25/10/2026).
- Commit no ramo `almoxarifado` a cada tarefa; push na `main` e deploy do App só com o OK do Levi.

## Review Focus

1. **O mesmo ciclo chega duas vezes** (a carga roda de hora em hora; o Admin relê no mesmo dia): nenhuma linha
   repetida; um início novo no mesmo dia vira outra foto com o mesmo `data_id` (Task 3 e 4).
2. **A API devolve tudo como texto** ("10.00", "0", ""): o saldo vira número; mínimo "0" é sem mínimo; vazio é `None`,
   nunca 0 (Task 1 e 4, `como_texto=True`).
3. **Os livros do App são de ciclos diferentes** (Saldo de D-1 com Itens de D): não aplica, e a tela mostra o último
   ciclo aplicado com o aviso (Task 1, 4 e 6).
4. **O almoxarifado cujo local não está na de-para** (a Nobres hoje): `usina_id` vazio, contado na qualidade, a tela diz
   "usina não ligada"; nunca liga pelo código (Task 3, 5 e 6).
5. **Item da lista com `Lido = Não`**: não vira saldo zero; a tela o marca "não lido neste ciclo" e a qualidade conta
   (Task 1 e 6).

---

## Arquivos

| Arquivo | O que faz |
|---|---|
| `nexus/dados/almoxarifado.py` (novo) | Contrato dos 4 livros do App, números, local → chave da usina, contas (situação, completude, coerência) |
| `nexus/dados/fato_almoxarifado.py` (novo) | Monta dimensões, `fato_saldo_almox` por ciclo, `fato_ciclo_varredura`, `fato_peca_lancada`, qualidade e tabelas |
| `nexus/dados/dominios.py` | `RECUSA_PECA` |
| `nexus/dados/catalogo.py`, `nexus/dados/explica.py` | Fatos, livros, família, conhecidas, `RESUMO`/`PARA_QUE` |
| `nexus/dados/carga.py` | `gerar_almoxarifado` e a chamada no laço |
| `nexus/dados/telas.py` | `_ultima_qualidade` lê `nexus_almoxarifado · qualidade` |
| `nexus/cadastro/ligacoes.py` | os locais de almoxarifado entram no sistema Fracttal da tela Ligações |
| `nexus/config.py`, `.env.example` | `NEXUS_ALMOX_GRAVAR` |
| `nexus/pcm/almoxarifado.py` (novo) | Leitura da tela (livros do App + fato do Nexus) e `registrar(bp)` |
| `nexus/templates/pcm/almoxarifado.html` (novo), `nexus/static/pcm.css` | A tela |
| `nexus/torres/pcm/__init__.py` | A `Tela("pecas")` vira Almoxarifado, `do_setor="PCM"`, registra a rota |
| `ferramentas/anular_ciclo_almox.py` (novo) | Marca um ciclo como anulado (não apaga linha) |
| `tests/test_dados_almoxarifado.py`, `tests/test_pcm_almoxarifado.py` (novos) | Provas |
| `nexus/dados/CLAUDE.md`, `nexus/pcm/CLAUDE.md`, `nexus/torres/CLAUDE.md`, `CLAUDE.md` | Documentação da área |
| `C:\GridcoBuild\app-campo-docs\_propostas\almoxarifado-nexus\` (fora do repositório) | O pacote do App |

---

### Task 1: Contrato e contas

**Files:**
- Create: `nexus/dados/almoxarifado.py`
- Modify: `nexus/dados/dominios.py`
- Test: `tests/test_dados_almoxarifado.py`

**Interfaces:**
- Produces:
  - Constantes `LIVRO_CICLO = "almoxarifado_ciclo_app_campo"`, `ABA_CICLO = "Ciclo"`, `LIVRO_ITENS =
    "almoxarifado_itens_app_campo"`, `ABA_ITENS = "Itens"`, `LIVRO_SALDO = "almoxarifado_saldo_app_campo"`,
    `ABA_SALDO = "Saldo"`, `LIVRO_PECAS = "almoxarifado_pecas_app_campo"`, `ABA_PECAS = "Peças"`.
  - `COLUNAS_CICLO`, `COLUNAS_ITENS`, `COLUNAS_SALDO`, `COLUNAS_PECAS`: tuplas com os nomes da seção 3 do desenho, na
    ordem (`("Início do ciclo", "Fim do ciclo", "Itens na lista do Fracttal", "Itens lidos", "Erros", "Origem")`, etc.).
  - `COMPLETUDE_MIN = 0.9`, `CICLO_VELHO_H = 36`.
  - `numero(v) -> float | None`: `"10.00"` → 10.0, `"0"` → 0.0, `""`/`None`/texto → `None`.
  - `chave_do_local(caminho: str) -> str | None`: o pedaço "Cliente - Usina - UF" do caminho do Fracttal (o mesmo
    padrão do `ligacoes.usina_do_caminho`, devolvendo o pedaço inteiro, sem espaços nas pontas).
  - `situacao(saldo: float | None, minimo: float | None) -> str`: `"abaixo"` (mínimo > 0 e saldo < mínimo),
    `"no_limite"` (mínimo > 0 e saldo = mínimo), `"zerada"` (saldo = 0, sem mínimo), `"sem_minimo"` (mínimo 0 ou
    `None`), `"ok"`.
  - `completo(ciclo: dict) -> bool`: `Itens lidos ÷ Itens na lista do Fracttal ≥ COMPLETUDE_MIN` (lista 0 → False).
  - `ciclo_comum(ciclo: list[dict], itens: list[dict], saldo: list[dict]) -> str | None`: o "Início do ciclo" quando os
    três livros têm um só e o mesmo; senão `None`.
  - `dominios.RECUSA_PECA = ("chave recusada pelo Fracttal", "sem permissão", "outro")`.

- [ ] **Step 1: Write the failing tests** em `tests/test_dados_almoxarifado.py`:
  `test_numero_le_texto_da_api` (`numero("10.00") == 10.0`, `numero("0") == 0.0`, `numero("") is None`,
  `numero(None) is None`, `numero("abc") is None`); `test_chave_do_local`
  (`chave_do_local("// Greenyellow/ Greenyellow - Irecê 1 - BA/") == "Greenyellow - Irecê 1 - BA"`,
  `chave_do_local("// Thopen/ Thopen - Brodowski 1 - SP/ Cabine 1/") == "Thopen - Brodowski 1 - SP"`,
  `chave_do_local("Almoxarifado") is None`); `test_situacao` (`situacao(1, 2) == "abaixo"`,
  `situacao(2, 2) == "no_limite"`, `situacao(0, 0) == "zerada"`, `situacao(3, 0) == "sem_minimo"`,
  `situacao(3, None) == "sem_minimo"`, `situacao(5, 2) == "ok"`); `test_completo` (574 de 574 → True; 516 de 574 →
  True; 515 de 574 → False; lista 0 → False; valores em texto "574"); `test_ciclo_comum` (os três com
  `"2026-10-25T03:00:12Z"` → esse; Saldo com outro → `None`; Itens vazio → `None`).
- [ ] **Step 2:** `python -m pytest -q tests/test_dados_almoxarifado.py` → FAIL (módulo não existe).
- [ ] **Step 3:** Implementar `nexus/dados/almoxarifado.py` e `RECUSA_PECA` em `dominios.py`, com o docstring do módulo
  dizendo de onde vem o dado (a varredura do App, seção 2 do desenho) e o porquê da completude pelo próprio ciclo.
- [ ] **Step 4:** Rodar de novo → PASS.
- [ ] **Step 5:** Commit `feat(almox): o contrato dos livros do App e as contas do almoxarifado`.

### Task 2: Catálogo

**Files:**
- Modify: `nexus/dados/catalogo.py`, `nexus/dados/explica.py`
- Test: `tests/test_dados_camada.py` (já existe; não muda), `tests/test_dados_almoxarifado.py`

**Interfaces:**
- Consumes: as constantes de livro e aba da Task 1.
- Produces: `catalogo.POR_ID["saldo_almox"]`, `["ciclo_varredura"]`, `["peca_lancada"]`; `LIVROS` com
  `nexus_almoxarifado` (abas `fato_ciclo_varredura`, `fato_peca_lancada`, `dim_item_almox`, `dim_almoxarifado`,
  `qualidade`, `atualizacao`; `so_cresce=True`, `no_banco=False`) e o molde `nexus_almoxarifado_saldo_AAAA_MM` (aba
  `fato_saldo_almox`, `so_cresce=True`, `no_banco=False`); `FAMILIAS` com
  `re.compile(r"^nexus_almoxarifado_saldo_\d{4}_\d{2}$")`; `CONHECIDAS` com o livro de itens do App (papel
  `dimensao`).

- [ ] **Step 1: Write the failing test** `test_almoxarifado_no_catalogo`: os três fatos existem, com o tipo da seção 4.1
  (`snapshot_periodico`, `snapshot_acumulado`, `snapshot_acumulado`); `saldo_almox.dims["equipamento"][0] == "prop"`;
  `saldo_almox.dims["usina"][0] == "id"`; as medidas `saldo_qtd`, `minimo_qtd` com `soma == "semi"` e
  `medida_valida`; `catalogo.da_familia("nexus_almoxarifado_saldo_2026_10", "fato_saldo_almox")`; os fatos têm
  `RESUMO` e `PARA_QUE` em `explica`.
- [ ] **Step 2:** Rodar → FAIL.
- [ ] **Step 3:** Declarar os fatos (estado `montado`, `conformado_em` com o livro do Nexus, `fontes` com os livros do
  App, `janela_origem` "o último ciclo completo (App)" e "90 dias (App)"), os livros, a família e a conhecida;
  `RESUMO` e `PARA_QUE` em pt-BR simples.
- [ ] **Step 4:** `python -m pytest -q tests/test_dados_almoxarifado.py tests/test_dados_camada.py` → PASS.
- [ ] **Step 5:** Commit `feat(almox): os fatos e os livros do almoxarifado no catálogo`.

### Task 3: Os fatos

**Files:**
- Create: `nexus/dados/fato_almoxarifado.py`
- Test: `tests/test_dados_almoxarifado.py`

**Interfaces:**
- Consumes: Task 1; `fatos.Ligador` (`usina_do_fracttal(texto)`, `pessoa(codigo)`); `fatos.CAB_QUALIDADE`;
  `fatos.tarefa_chave(texto)`; `historico.dia_brt(iso) -> date` e `calendario.data_id(d) -> int` (ISO UTC → AAAAMMDD
  de Brasília).
- Produces:
  - `LIVRO = "nexus_almoxarifado"`, `NOME_LIVRO`, `LIVRO_SALDO_MOLDE = "nexus_almoxarifado_saldo_{:04d}_{:02d}"`,
    `livro_do_mes(data_id: int) -> str`.
  - `CAB_SALDO = ["saldo_id", "ciclo_inicio", "data_id", "id_item", "codigo", "id_almoxarifado", "usina_id",
    "usina_ligada_por", "saldo_qtd", "minimo_qtd"]` (`saldo_id` = sha1 de `ciclo_inicio|id_item|id_almoxarifado`).
  - `CAB_CICLO = ["ciclo_inicio", "data_id", "fim", "itens_lista", "itens_lidos", "erros", "origem", "situacao",
    "motivo", "anulado", "visto_em"]` (`situacao` em `aplicado`/`recusado`; `anulado` 1/0).
  - `CAB_PECA = ["lancamento_id", "data_id", "data_id_recebida", "os", "codigo_ativo", "tarefa_chave", "id_item",
    "codigo", "id_almoxarifado", "usina_id", "usina_ligada_por", "pessoa_id", "quantidade_qtd", "lancada",
    "motivo_recusa"]`.
  - `CAB_DIM_ITEM = ["id_item", "codigo", "nome", "unidade", "familia", "avariado", "ferramenta"]`,
    `CAB_DIM_ALMOX = ["id_almoxarifado", "nome", "local", "usina_id", "usina_ligada_por"]`.
  - `saldo_do_ciclo(saldo: list[dict], lig) -> list[list]` (ordenado por `id_item`, `id_almoxarifado`).
  - `mesclar_dim(no_banco: list[dict], novas: list[list], chave: str, cab: list) -> list[list]` (a linha do banco que
    não veio fica; a que veio troca; ordenada pela chave).
  - `mesclar_pecas(no_banco: list[dict], app: list[dict], lig) -> list[list]` (por `lancamento_id`, vale a do App; a do
    banco que saiu da janela de 90 dias do App fica).
  - `linha_ciclo(ciclo: dict, situacao: str, motivo: str, visto_em: str) -> list`.
  - `linha_qualidade(fato: str, linhas: list[list], cab: list, origem_em: str, agora: str) -> list` no `CAB_QUALIDADE`
    (preenche pelo nome, como a `programacao.linha_qualidade`).

- [ ] **Step 1: Write the failing tests:**
  - `test_saldo_liga_a_usina_pela_de_para_e_nao_chuta`: um `Ligador` com o de-para "Greenyellow - Irecê 1 - BA" → 7;
    a linha com o local da Irecê sai com `usina_id == 7`, `usina_ligada_por == "de-para do Fracttal"`; a da Nobres
    ("RenoGrid - Nobres 1 - MT", fora da de-para) sai com `usina_id is None` mesmo com um código de usina que casaria.
  - `test_saldo_numeros_em_texto`: Saldo "10.00" e Mínimo "0" (o `como_texto`) → `10.0` e `0.0`; Mínimo "" → `None`.
  - `test_mesma_foto_mesmo_saldo_id`: o mesmo ciclo montado duas vezes dá as mesmas linhas, na mesma ordem; outro
    início no mesmo dia dá outros `saldo_id` com o mesmo `data_id`.
  - `test_data_id_e_o_dia_de_brasilia`: início `"2026-10-26T02:30:00Z"` → `data_id == 20261025`.
  - `test_peca_reenviada_vale_a_ultima_e_a_antiga_fica`: no banco, o lançamento A recusado e o B fora da janela; o App
    manda A lançado → A com `lancada == 1`, B continua; o motivo fora do `RECUSA_PECA` vira `"outro"`; nenhuma coluna
    com e-mail nem nome (o `CAB_PECA` não tem texto livre).
  - `test_dim_nao_encolhe`: `mesclar_dim` mantém o item que não veio no ciclo.
  - `test_qualidade_no_cab_da_casa`: `len(linha_qualidade(...)) == len(fatos.CAB_QUALIDADE)`, com `pct_usina` 50.0
    para 1 de 2 ligadas.
- [ ] **Step 2:** Rodar → FAIL.
- [ ] **Step 3:** Implementar `nexus/dados/fato_almoxarifado.py` (puro: nada de rede).
- [ ] **Step 4:** Rodar → PASS.
- [ ] **Step 5:** Commit `feat(almox): os fatos do almoxarifado (saldo por ciclo, ciclos, peças) e a qualidade`.

### Task 4: A carga, com portão, travas e ensaio

**Files:**
- Modify: `nexus/dados/carga.py`, `nexus/config.py`, `.env.example`
- Create: `ferramentas/anular_ciclo_almox.py`
- Test: `tests/test_dados_almoxarifado.py`

**Interfaces:**
- Consumes: Tasks 1–3; `livros.ler`, `livros.abas`, `livros.publicar` (a trava `so_cresce` vem do catálogo);
  `carga._Leitor`, `carga.ligador`, `carga._pessoas_por_codigo`, `carga._base`.
- Produces: `gerar_almoxarifado(config, sessao=None, *, gravar=True, forcar=False, agora=None) -> dict` (só
  contagens; nunca levanta para o laço); `anular_ciclo_almox.py --ciclo <início> [--gravar]`.

O fluxo da `gerar_almoxarifado`, na ordem (cada "não grava" volta um relatório com o motivo):
1. Lê os 4 livros do App. Livro de Ciclo/Itens/Saldo ausente → `{"pulou": "o App ainda não publica o almoxarifado"}`.
2. `ciclo_comum` → `None`: não aplica ("livros do App de ciclos diferentes").
3. Portão: o início já está no `fato_ciclo_varredura` E o sha das linhas de Peças é o da última `atualizacao` →
   `{"pulou": ...}`.
4. Lê do banco `nexus_almoxarifado` (todas as abas) e, se o ciclo é novo, o livro do mês. Livro que existe e leitura que
   falha ou volta vazia → não grava ("o fato não encolhe", como o `_programacao`).
5. Ciclo novo e `completo` → as fotos do saldo entram no livro do mês e o ciclo como `aplicado`; incompleto → só a
   linha do ciclo como `recusado`, com "N de M itens lidos". A queda de itens contra o ciclo anterior vai só no
   `extra` da qualidade.
6. Sem `NEXUS_ALMOX_GRAVAR=1` no `config` (ou com `gravar=False`): `{"ensaio": ..., contagens}` e nada grava.
7. Grava o livro do mês primeiro e o `nexus_almoxarifado` depois (ele é a marca de ciclo aplicado; se o mês falhar, a
   próxima hora tenta de novo).

- [ ] **Step 1: Write the failing tests** (com `ApiPGFalsa`, o `_aba` do `test_campo_visao` e um `config` com
  `GRIDCO_SQL_TOKEN` de teste):
  - `test_sem_os_livros_do_app_pula`.
  - `test_sem_a_chave_e_ensaio`: com os livros e sem `NEXUS_ALMOX_GRAVAR`, `rel["ensaio"]` e `api.syncs == 0`.
  - `test_grava_o_mes_e_a_marca` e, rodada de novo na mesma hora, `pulou` sem gravar nada (`api.syncs` igual).
  - `test_releitura_no_mesmo_dia_vira_outra_foto`: 2º início no mesmo dia → o livro do mês com o dobro de linhas, dois
    ciclos `aplicado`.
  - `test_ciclo_incompleto_e_recusado`: 515 de 574 → nenhuma linha de saldo nova, o ciclo `recusado`.
  - `test_livros_de_ciclos_diferentes_nao_aplicam`.
  - `test_leitura_vazia_do_livro_existente_nao_grava` (o `ApiPGFalsa(perder=...)` ou o `omitir`).
  - `test_como_texto`: a mesma rodada com `ApiPGFalsa(como_texto=True)` dá as mesmas linhas.
  - `test_anular_marca_sem_apagar`: a ferramenta põe `anulado = 1` no ciclo e mantém a contagem de linhas.
- [ ] **Step 2:** Rodar → FAIL.
- [ ] **Step 3:** Implementar a `gerar_almoxarifado` em `carga.py` (a gravação passa pelo `livros.publicar`; a chamada
  no `ligar`, depois da `gerar_geracao`, no mesmo molde, em `try` próprio, com o log só das chaves `pulou`, `ensaio`,
  `gravado`, `erro`); `NEXUS_ALMOX_GRAVAR` em `config.OPCIONAIS` e no `.env.example` (comentado: "1 liga a gravação do
  histórico do almoxarifado; sem ela, a carga só mede"); a ferramenta.
- [ ] **Step 4:** Rodar → PASS.
- [ ] **Step 5:** Commit `feat(almox): a carga do histórico do almoxarifado, com portão próprio, travas e ensaio`.

### Task 5: A usina dos almoxarifados na Ligação e a qualidade na Governança

**Files:**
- Modify: `nexus/cadastro/ligacoes.py`, `nexus/dados/telas.py`
- Test: `tests/test_dados_almoxarifado.py`

**Interfaces:**
- Consumes: `almoxarifado.chave_do_local`, `LIVRO_SALDO`/`ABA_SALDO`, `fato_almoxarifado.LIVRO`.
- Produces: `ligacoes.locais_de_almoxarifado(linhas_saldo: list[dict], ja: set) -> list[dict]` (itens
  `{"chave", "nome", "origem": "local de almoxarifado"}`, sem repetir as chaves já presentes nem entre si), usada pela
  `fontes()` no sistema `FRACTTAL` quando o livro Saldo está no banco.

- [ ] **Step 1: Write the failing tests:** `test_local_de_almoxarifado_entra_na_ligacao` (dois almoxarifados no mesmo
  local e um local que já é chave da Classificação 1 → só uma chave nova, com a origem); `test_governanca_le_a_qualidade_do_almox`
  (a `_ultima_qualidade`, com o banco falso, traz a linha `saldo_almox` do `nexus_almoxarifado · qualidade`; livro
  ausente não quebra).
- [ ] **Step 2:** Rodar → FAIL.
- [ ] **Step 3:** Implementar. Na `_ultima_qualidade`, o livro que ainda não existe volta vazio (o `livros.ler` já faz).
- [ ] **Step 4:** `python -m pytest -q tests/test_dados_almoxarifado.py tests/test_cadastro_fonte_elis.py tests/test_dados_telas*.py` → PASS.
- [ ] **Step 5:** Commit `feat(almox): os locais de almoxarifado na Ligação e a qualidade na Governança`.

### Task 6: A tela

**Files:**
- Create: `nexus/pcm/almoxarifado.py`, `nexus/templates/pcm/almoxarifado.html`
- Modify: `nexus/torres/pcm/__init__.py`, `nexus/static/pcm.css`
- Test: `tests/test_pcm_almoxarifado.py`

**Interfaces:**
- Consumes: Task 1 (contas), Task 3 (`fato_almoxarifado.LIVRO`, `livro_do_mes`, `CAB_CICLO`, `CAB_PECA`),
  `visao._ciclo`, `visao._livro`, `visao._ler`, `visao._Base`, `visao._atualizados`, `visao._agora`.
- Produces: `montar() -> leitura.Leitura` (o `valor` é um dict com `estado` em `sem_livro` | `ok` | `ciclo_velho` |
  `incoerente`, `ciclo` {início, fim, lidos, total}, `kpis`, `reposicao`, `por_almoxarifado`, `catalogo`, `consumo`,
  `cadastro`); `registrar(bp)` com a rota `/pecas` (endpoint `pecas`).

Regras que o teste fixa:
- `estado == "sem_livro"`: a página diz "O App ainda não publica o almoxarifado" e não mostra número nenhum.
- Livros incoerentes ou ciclo recusado: mostra o último ciclo `aplicado` do `fato_ciclo_varredura` e o saldo do livro
  do mês dele, com o aviso "Os livros do App chegaram de ciclos diferentes: mostrando o saldo de DD/MM, HH:MM". Sem
  ciclo aplicado no Nexus (o ensaio, antes da `NEXUS_ALMOX_GRAVAR`): o aviso e nenhum número.
- Consumo: o `fato_peca_lancada` do Nexus; enquanto ele não existe (o ensaio), o livro Peças do App, com a nota "o
  histórico ainda não é gravado: mostrando os 90 dias do App".
- Ciclo com mais de `CICLO_VELHO_H` horas: aviso com a data, os números continuam.
- Os 6 números: almoxarifados, peças com saldo, abaixo + no limite, sem mínimo, avariadas, lançadas (com recusadas),
  tudo desde o início no consumo.
- Reposição ordenada: abaixo primeiro (pela falta, maior primeiro), depois no limite.
- Almoxarifado sem usina ligada: o cartão diz "usina não ligada".
- Item com `Lido = Não`: no Catálogo, "não lido neste ciclo" (nunca "sem saldo").
- Recusadas aparecem em Cadastro a corrigir como "corrigir no Fracttal".

- [ ] **Step 1: Write the failing tests** com o `banco` do `test_campo_visao` e os 4 livros do App em fixture (locais
  "Thopen - Altair 1 - SP" e "Thopen - Brodowski 1 - SP", que a `DE_PARA` da fixture liga, e "Nenhuma - Usina Z - MT",
  que não liga): `test_sem_o_livro_do_app`, `test_kpis_e_reposicao` (com os números da fixture),
  `test_livros_incoerentes_mostram_o_ultimo_aplicado`, `test_incoerente_sem_ciclo_no_nexus_nao_mostra_numero`,
  `test_consumo_sem_o_fato_le_o_livro_do_app`, `test_ciclo_velho_avisa`, `test_usina_nao_ligada`,
  `test_item_nao_lido`, `test_recusadas_em_cadastro_a_corrigir`, `test_tela_so_do_setor_pcm` (quem não é do setor e
  não tem a marca não abre, como os outros testes do PCM), `test_sem_cor_fora_de_token` (o template não tem `#` seguido
  de hex nem `rgba(`).
- [ ] **Step 2:** Rodar → FAIL.
- [ ] **Step 3:** Implementar a leitura (cópia de 5 min pelo `visao._ler`), a view, o template (a faixa de números no
  desenho `kb-kpis` da casa; as 5 abas; filtros por `?aba=&almox=&familia=&q=` relativos; abaixo de 640 px os cartões)
  e a `Tela("pecas", "Almoxarifado", "Que peça está abaixo do mínimo ou no limite, em que almoxarifado, e o que saiu
  nas OS?", "Fracttal (inventário), pela varredura diária do App de Campo", do_setor="PCM")`.
- [ ] **Step 4:** Rodar → PASS.
- [ ] **Step 5: Conferir no navegador**, numa cópia de prova (`ferramentas/subir_copia_de_prova.py --porta 5170`) com um
  banco de mentira montado por um script FORA do repositório (scratchpad), a partir da cópia de 25/10 da tabela do App
  guardada em `dados/` e passada pelo contrato (HMAC no lugar do e-mail, o motivo no domínio). Desktop e 375 px, temas
  escuro e claro; a prova é um print de cada.
- [ ] **Step 6:** Commit `feat(almox): a tela Almoxarifado do PCM`.

### Task 7: O pacote do App

**Files (fora do repositório):** `C:\GridcoBuild\app-campo-docs\_propostas\almoxarifado-nexus\` com `LEIA.md`,
`almoxarifado-nexus.diff` (contra a `C:\GridcoBuild\app-campo-v300`), `aplicar.py` (o molde do
`ranking-pontos-nexus/aplicar.py`) e `test_almoxarifado_nexus.py`.

**Interfaces:**
- Consumes: `nexus/dados/almoxarifado.py` (as quatro tuplas de colunas: o teste do App as copia e compara).
- Produces, no `function_app.py`:
  - `NEXUS_WB` com `almox_ciclo`, `almox_itens`, `almox_saldo`, `almox_pecas` e `NEXUS_COLUNAS` iguais às tuplas da
    Task 1; os quatro no `NEXUS_WB_SEM_VAZIO`.
  - Na `_almox_passada`: no início do ciclo, a lista de ids do Fracttal fica no estado (`est["lista"]`, JSON) e o cursor
    anda sobre ela (a lista não é relida no meio do ciclo); cada item lido guarda `ciclo_inicio`; o estado guarda
    `lidos`, `erros` e `origem` (`pedido do Admin` quando veio do `/almox/atualizar`).
  - `_almox_publicar_ciclo()`: depois do `fim`, se `est["publicado"] != est["inicio"]`, sobe Ciclo, Itens e Saldo
    (só os itens da `lista`; Lido = Sim quando `ciclo_inicio == inicio`), e só marca `publicado` com os três OK.
    Chamada no fim da `_almox_passada` e na passada de hora em hora (repete o que falhou).
  - `_nexus_linhas_almox_pecas()`: a partição `recurso`, na janela `NEXUS_WB_DIAS`, com `Usada em` (o `ts` do evento,
    gravado a partir de agora), `Tarefa` e `Código do ativo` (gravados a partir de agora; as linhas antigas vão vazias),
    o motivo classificado pelo texto do erro (`FOREIGN_KEY_VIOLATION`/chave → "chave recusada pelo Fracttal";
    permissão → "sem permissão"; resto → "outro"; vazio quando lançada) e o HMAC do `por`.
  - Saldo, Mínimo e Quantidade como número (`_num0` não serve: vazio fica vazio).

- [ ] **Step 1:** Copiar a v300 para o TEMP e escrever `test_almoxarifado_nexus.py` (colunas iguais às do Nexus, na
  ordem; nada publicado no meio do ciclo; os três ou nenhum marcado; item fora da lista não sai; o motivo nunca traz o
  texto do erro; o e-mail nunca aparece).
- [ ] **Step 2:** Rodar → FAIL.
- [ ] **Step 3:** Fazer a mudança na cópia; gerar o diff; escrever o `LEIA.md` (o que muda, o contrato, a ordem: o
  Nexus já está no ar em ensaio, a sessão do App aplica, o deploy só com o OK do Levi).
- [ ] **Step 4:** `python aplicar.py <cópia limpa da v300>` aplica e roda o teste novo e a suíte do App → PASS.
- [ ] **Step 5:** Avisar a sessão "App de campo" do pacote (o caminho do LEIA), sem pedir deploy.

### Task 8: Documentação, suíte e revisão

**Files:** `nexus/dados/CLAUDE.md` (o que existe: a linha do almoxarifado; a regra 9 passa a dizer que a carga do
almoxarifado tem trava; a regra 2 cita o `nexus_almoxarifado` como mestre do item e do almoxarifado), `nexus/pcm/CLAUDE.md`
(a seção Almoxarifado: para que serve, de onde vem, as contas, como provar, a chave `NEXUS_ALMOX_GRAVAR`),
`nexus/torres/CLAUDE.md` (a linha da tela), a linha do PCM no `CLAUDE.md` da raiz.

- [ ] **Step 1:** Escrever os quatro `.md` (corrigir as linhas velhas, não acrescentar ao lado).
- [ ] **Step 2:** Copiar o `.env` à worktree e rodar a suíte inteira em segundo plano: `python -m pytest -q` → 0 falhas.
- [ ] **Step 3:** Revisão final do ramo por um revisor novo (o modelo mais capaz), com o desenho e este plano; corrigir
  cada achado com teste antes (vermelho → verde).
- [ ] **Step 4:** Commit `docs(almox): a área do almoxarifado nos CLAUDE.md`.
- [ ] **Step 5:** Pedir ao Levi o OK para subir na `main` (o Nexus em ensaio). Depois do App publicar: `--ensaio` com o
  1º ciclo real, a Nobres ligada em Base → Ligações, `NEXUS_ALMOX_GRAVAR=1` no `.env` do servidor (com o OK dele), a 1ª
  gravação conferida por GET.
