# Visão do responsável: bloco Manutenção, coluna Limpeza e faixa "Parada agora" — plano de construção

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pôr na Visão do responsável (`/t/campo/responsaveis`) a manutenção de cada usina (OS abertas e atrasadas, tarefas paradas por motivo, a semana, a zeladoria), a limpeza da última ronda e as paradas abertas, com as OS lidas do Fracttal pelo próprio Nexus.

**Architecture:** Um fato novo no banco, `nexus_os · fato_tarefa_os`, montado por um módulo puro (`nexus/dados/fato_tarefa_os.py`) e publicado de hora em hora por um laço do Campo que lê o REST do Fracttal (`nexus/campo/tarefas_os.py`, no molde do `chamados_acompanhamento.py`). A conta do bloco é pura (`nexus/campo/manutencao.py`) e junta o fato novo, os motivos do PCM, os chamados e a programação; a Visão (`nexus/campo/responsaveis.py`) lê tudo dentro da cópia de 5 min que já tem e aplica, no pedido, o limite de dias que o supervisor guarda num cookie.

**Tech Stack:** Python 3.14, Flask/Jinja, pytest; a API do banco `db_performace` (livros xlsx, `nexus/dados/livros.py`); o REST do Fracttal, só GET (`nexus/campo/fracttal.py`).

**Spec:** `docs/superpowers/specs/2026-10-18-visao-responsavel-manutencao-design.md`

## Global Constraints

- Tudo em pt-BR, inclusive comentários; comentário diz o porquê, com o caso real (decisões do Levi de 18/10/2026).
- Sem emoji na interface; severidade por cor e palavra. Cor só por token do `nexus/static/nexus.css`, nos dois temas: nada de `#hex` ou `rgba()` em regra de CSS nem em template.
- Endereço nunca a partir da raiz: `{{ raiz }}`, `url_for`, `|na_raiz` no template; `na_raiz()` no Python; `nexusRota()` no JavaScript.
- Banco tem leitura aberta: no fato, nada de nome de pessoa, e-mail ou texto livre (o `user_assigned` e o `personnel_description` do Fracttal só servem na memória). Nome de colega também não entra em arquivo versionado: fixture com nome fictício.
- Fracttal: só GET, limite de 200 pedidos por minuto para a empresa inteira; leitura sequencial com pausa entre páginas; leitura incompleta **não grava** ("número pela metade não vai para a tela").
- Fonte: só Fracttal ou banco do Nexus. A única dependência externa é a programação (cópia de hora em hora do `banco_dados.json` do PCM), e a tela diz isso.
- Regras do `nexus/dados/CLAUDE.md`: livro registrado em `catalogo.LIVROS` antes de existir; grão escrito; IDs no fato; não liga = vazio, nunca chutar; dia de Brasília; uma gravação por hora, uma máquina por vez (mais de 50 min desde a última).
- Fonte que falha na Visão fica de fora e a tela diz qual (`_ler_fonte`); o resto vale.
- Testes: `"$PY" -m pytest -q <arquivo>::<teste>` na raiz da worktree, com `PY="/c/Users/Levi Maia/AppData/Local/Python/pythoncore-3.14-64/python.exe"`. Só os testes afetados durante o trabalho; a suíte inteira UMA vez, no fim (o PC já travou por RAM).
- Segredo nunca é impresso. As worktrees não têm o `.env`: copiar da pasta principal antes do ensaio e da suíte inteira, sem mostrar o conteúdo.
- Não reiniciar 5050, 5070, 5080 nem 5090; prova na cópia da 5170 (`ferramentas/subir_copia_de_prova.py`).
- Commits na branch `setor-campo-hseq` desta worktree. A 1ª gravação do fato no banco e o push para a `main` (produção em ~2 min) só com o OK do Levi.
- Cada mudança atualiza no mesmo trabalho o `CLAUDE.md` da área.

## Review Focus

- **Leitura do Fracttal que falha no meio** (429 repetido, página que não volta, teto de páginas atingido): nada se grava, a Visão continua com a última foto e diz de quando ela é e que a última leitura falhou. Teste na Task 2 (`test_leitura_incompleta_nao_grava`) e na Task 6 (`test_a_tela_diz_que_a_leitura_falhou`).
- **Tarefa sem Data Programada, com data futura, ou criada perto da meia-noite em UTC:** sem data nunca é atrasada nem "vence até amanhã"; o atraso conta pelo dia de Brasília. Teste na Task 4 (`test_sem_data_programada_nao_atrasa_nem_vence`) e na Task 1 (`test_dia_de_brasilia`).
- **Marca de motivo com código vazio (vale para todos os ativos da OS) e o nome da tarefa com acento ou caixa diferente:** a tarefa sai das atrasadas do mesmo jeito. Teste na Task 4 (`test_marca_sem_codigo_tira_todos_os_ativos_e_casa_sem_acento`).
- **Cookie do limite com lixo** (texto, 0, negativo, 9999, vazio): vale 30, ou o mais perto entre 10 e 365 quando é número; nunca 500. Teste na Task 6 (`test_limite_do_cookie_com_lixo`).
- **Semana passada sem linha da usina** (usina nova, programação não publicada): "sem programação", neutro, nunca 0% em Acompanhar. Teste na Task 4 (`test_usina_sem_programacao_fica_neutra`).

---

### Task 1: O fato puro `fato_tarefa_os` e o registro no catálogo

**Files:**
- Create: `nexus/dados/fato_tarefa_os.py`
- Modify: `nexus/dados/catalogo.py` (um `Fato` novo e um `Livro` novo em `LIVROS`), `nexus/dados/explica.py` (`RESUMO` e `PARA_QUE`), `nexus/dados/telas.py:49-51` (ler a `qualidade` do livro novo)
- Test: `tests/test_dados_tarefa_os.py` (novo); `tests/test_dados_camada.py:74-76` e `:110-111` (o `CABS` e a tupla de `LIVRO` ganham o fato novo)

**Interfaces:**
- Produces:
  - `LIVRO, ABA = "nexus_os", "fato_tarefa_os"`; `NOME_LIVRO = "Nexus · tarefas das OS do Fracttal (em processo, em verificação e zeladoria feita)"`.
  - `CAB_TAREFA_OS = ["fracttal_tarefa_id", "os", "fracttal_os_id", "tarefa_chave", "codigo_ativo", "equipamento_id", "equipamento_ligado_por", "usina_id", "usina_ligada_por", "site_fracttal", "data_id_criacao", "data_id_programada", "data_id_fim", "tipo_tarefa", "status_os", "estado_tarefa", "do_backoffice", "duracao_min"]`.
  - `TIPO = "snapshot_periodico"` (se o catálogo grafar a foto periódica de outro jeito, vale a grafia dele), `GRAO = "1 linha = 1 tarefa de OS do Fracttal (em processo ou em verificação, e a zeladoria finalizada nos últimos 90 dias)"`, `CHAVE = ("fracttal_tarefa_id",)`, `MEDIDAS = (("duracao_min", "min", "aditiva"),)`, `FONTES = (("Fracttal (API REST)", "work_orders: status 1 e 2 inteiros; status 3 do tipo Zeladoria"),)`, `JANELA_ORIGEM = "o que está aberto agora (status 1 e 2); a zeladoria finalizada, 90 dias pelo fim da tarefa"`.
  - `STATUS_OS = {1: "em_processo", 2: "em_verificacao", 3: "finalizada"}` (4 fica fora); `ESTADO_TAREFA` = `NO_STARTED`/`NOT_STARTED` → `nao_iniciada`, `STARTED`/`IN_PROGRESS` → `em_progresso`, `PAUSED` → `pausada`, `DONE`/`FINISHED`/`COMPLETED` → `finalizada` (os mesmos valores do `fato_programacao`); `TIPOS_TAREFA` = texto normalizado → `preventiva`, `corretiva`, `corretiva_emergencial`, `religamento`, `religamento_remoto`, `inspecao`, `preditiva`, `administrativa`, `zeladoria`, `handover`, `teste` (fora da lista = vazio e conta).
  - `linhas(rows: list[dict], lig: fatos.Ligador, equip_idx: dict, backoffice_hmac: set[str], chave_hmac: str | None) -> tuple[list[list], dict]`: as linhas na ordem do `CAB_TAREFA_OS`, ordenadas pela chave, e um relatório `{"lidas", "repetidas", "fora_do_dominio": {coluna: n}, "sem_usina", "sem_equipamento", "backoffice"}`.
  - `conferir_grao(linhas: list[list]) -> None`: `fato_ronda.conferir_grao(linhas, CAB_TAREFA_OS, "fracttal_tarefa_id")`.

- [ ] **Step 1: Escrever os testes que falham** em `tests/test_dados_tarefa_os.py`, com o dublê de linha do REST no molde do `_w` de `tests/test_campo_chamados_acompanhamento.py` (chaves `id_work_orders_tasks`, `wo_folio`, `id_work_order`, `id_status_work_order`, `task_status`, `tasks_log_task_type_main`, `date_maintenance`, `creation_date`, `final_date`, `code`, `groups_1_description`, `description`, `tasks_duration`, `user_assigned`, `personnel_description`), o `Ligador` e o de-para do mesmo arquivo:
  - `test_uma_linha_por_tarefa_com_os_ids_e_sem_pessoa`: a mesma tarefa em duas páginas vira uma linha (`relatorio["repetidas"] == 1`); `status_os`, `estado_tarefa` e `tipo_tarefa` nos domínios; `tarefa_chave == fatos.tarefa_chave(description)`; `duracao_min == 90` para `tasks_duration = 5400`; nenhum `user_assigned`, `personnel_description` nem `description` em `str(linhas)`; status 4 fica fora.
  - `test_dia_de_brasilia`: `creation_date = "2026-10-10T02:30:00+00:00"` → `data_id_criacao == 20261009`; `date_maintenance` vazio → `data_id_programada is None`.
  - `test_a_ligacao_nao_chuta`: site do de-para → `usina_ligada_por == "de-para do Fracttal"`; site desconhecido com código de uma usina só → `"código do ativo"`; nenhum dos dois → `usina_id is None` e conta em `sem_usina`; código fora da dimensão → `equipamento_id is None`.
  - `test_do_backoffice_pelo_hmac`: `user_assigned` cujo `motivos.nome_hmac(chave, nome)` está em `backoffice_hmac` → `do_backoffice == 1`; o resto 0; sem a chave HMAC (`chave_hmac=None`) → todas 0 e `relatorio["backoffice"] is None`.
  - `test_conferir_grao_pega_chave_repetida_ou_vazia`: `pytest.raises(GraoDuplicado)`.
  - Em `tests/test_dados_camada.py`, o `CABS` (:74-76) ganha `"tarefa_os": fato_tarefa_os.CAB_TAREFA_OS` e a tupla de `LIVRO` (:110-111) ganha `fato_tarefa_os.LIVRO`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `"$PY" -m pytest -q tests/test_dados_tarefa_os.py tests/test_dados_camada.py`
Expected: FAIL (`ModuleNotFoundError: nexus.dados.fato_tarefa_os`).

- [ ] **Step 3: Implementar `nexus/dados/fato_tarefa_os.py`** com as interfaces acima: dedupe por `id_work_orders_tasks`; dia de Brasília como o `fato_chamado._dia`; usina por `lig.usina(groups_1_description, code)`; equipamento por `equipamento.indice`/`equipamento.ligar` (o `canon`, como a carga, e não o código cru do chamado); `do_backoffice` comparando `motivos.nome_hmac(chave_hmac, user_assigned)` com o conjunto (import de `nexus.pcm.motivos` dentro da função). Registrar o `Fato("tarefa_os", "Tarefa de OS do Fracttal", "pcm", ...)` com `_d(data=..., usina=..., equipamento=..., os=("cod", "os"))`, estado `origem`, e o `Livro("nexus_os", ("fato_tarefa_os", "qualidade"), "de hora em hora (:10), uma máquina por vez", "nexus/campo/tarefas_os.py (laço do Campo; NEXUS_OS_PUBLICAR=0 desliga numa máquina)", True)`. `RESUMO` de 15 a 70 caracteres sem ponto final; `PARA_QUE` com 80 ou mais terminando em ".". Em `dados/telas.py:49-51`, o livro `nexus_os` entra na leitura da `qualidade`.

- [ ] **Step 4: Rodar e ver passar**

Run: `"$PY" -m pytest -q tests/test_dados_tarefa_os.py tests/test_dados_camada.py tests/test_dados_organograma.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nexus/dados/fato_tarefa_os.py nexus/dados/catalogo.py nexus/dados/explica.py nexus/dados/telas.py tests/test_dados_tarefa_os.py tests/test_dados_camada.py
git commit -m "feat(dados): o fato das tarefas das OS do Fracttal (nexus_os · fato_tarefa_os), puro e registrado no catálogo antes de existir"
```

### Task 2: A leitura do Fracttal e a publicação de hora em hora

**Files:**
- Create: `nexus/campo/tarefas_os.py`
- Modify: `nexus/campo/__init__.py:31-34` (ligar o laço), `nexus/config.py:40-41` (`NEXUS_OS_PUBLICAR` em `OPCIONAIS`), `DEPLOY.md:402-404` (o interruptor), `ferramentas/subir_copia_de_prova.py:88-91` (`NEXUS_OS_PUBLICAR=0` e, ponta solta, `NEXUS_CHAMADOS_PUBLICAR=0`: a cópia gastava a cota lendo os chamados)
- Test: `tests/test_campo_tarefas_os.py` (novo), `tests/test_campo_instalar.py:31, 55-65`

**Interfaces:**
- Consumes: Task 1 (`fato_tarefa_os.linhas`, `conferir_grao`, `LIVRO`, `ABA`, `NOME_LIVRO`, `CAB_TAREFA_OS`); `livros.publicar(livro, nome, tabelas, *, base, token, sessao) -> dict`; `livros.atualizado_em(base, sessao, livro)`; `livros.ler(base, s, livro, aba)`; `fatos.Ligador`; `equipamento.indice(dim)`; `fatos.qualidade(fato, livro, linhas, cab, origem, origem_em, agora, *, extra=None)`; o backoffice vigente pela regra do próprio PCM, `{b["nome_hmac"] for b in motivos.backoffice(cfg, motivos.ler(cfg))}` (sem o Cofre a lista vem vazia e ninguém é do backoffice: o relatório diz isso), e a chave `config["NEXUS_PESSOA_HMAC"]`.
- Produces:
  - `class LeituraIncompleta(RuntimeError)`.
  - `ler_fracttal(ler, hoje: date) -> list[dict]`: status 1 e 2 inteiros (`work_orders?id_status_work_order={st}&sort=creation_date:desc&limit=100&start={n}`), e o status 3 do tipo Zeladoria (`&tasks_log_task_type_main={quote(TIPO_ZELADORIA_REST)}&sort=final_date:desc`) até uma página INTEIRA ter o `final_date` mais novo antes de `hoje - 90 dias` (não para no 1º velho: a ordem do REST é aproximada). `PAUSA_S = 1.0` entre páginas; `fracttal.Recusado` numa página → espera `ESPERA_RECUSA_S = 60` e tenta a mesma página até 3 vezes, depois `LeituraIncompleta`; `PAGINAS_MAX = 150` atingido → `LeituraIncompleta` (nunca corta calado).
  - `publicar(config, sessao=None, *, ler=None, agora=None, forcar=False) -> dict`, na ordem do `chamados_acompanhamento.publicar`: regra 11 (`_ultima`), sem `GRIDCO_SQL_TOKEN` → `{"erro"}`, ler o Fracttal, ler cadastro, dimensão de equipamento e backoffice, montar e conferir o grão, recusar livro cheio com leitura vazia (`{"recusou"}`), gravar `{ABA: (CAB, linhas), "qualidade": (fatos.CAB_QUALIDADE, [linha])}`. Devolve `{"lidas", "linhas", "abertas", "sem_usina", "paginas", "gravado"}` ou `{"pulou"}`, `{"recusou"}`, `{"erro"}`.
  - `estado() -> dict`: `{"ultimo": dict | None, "quando": str | None}` (o resultado da última volta, para a Visão dizer quando a leitura falhou). Escolha do Claude, diferente da letra do desenho: na falha nada se grava, nem a `qualidade`; a falha fica neste estado (a Visão mostra) e no log, e a Governança vê a idade do livro. Regravar o fato igual só para marcar a falha (o `carga._fato_ou_anterior`) relia o livro inteiro a cada hora sem ganho para a tela.
  - `ligar(app) -> None`, `_LACO`, `MINUTO_DA_HORA = 10`, `PRIMEIRA_S = 120`; não liga com `NEXUS_OS_PUBLICAR = "0"`.

- [ ] **Step 1: Escrever os testes que falham** em `tests/test_campo_tarefas_os.py`, com um dublê `_Fracttal` que lê `id_status_work_order=`, `tasks_log_task_type_main=` e `start=` da URL (o do teste dos chamados) e o fixture `banco(app)` daquele arquivo:
  - `test_le_os_status_1_e_2_inteiros_e_a_zeladoria_feita`: os caminhos pedidos têm os dois status sem filtro de tipo e o status 3 com o tipo Zeladoria; só GET.
  - `test_a_zeladoria_para_quando_a_pagina_inteira_passou_dos_90_dias`: uma página com uma linha velha e outras novas continua; a página toda velha para.
  - `test_leitura_incompleta_nao_grava`: o dublê levanta `fracttal.Recusado` sempre numa página (com `ESPERA_RECUSA_S` e `PAUSA_S` em 0 por monkeypatch) → `publicar` devolve `{"erro": ...}` com "LeituraIncompleta" e `banco.syncs == 0`; o mesmo com mais de `PAGINAS_MAX` páginas.
  - `test_publica_o_fato_e_a_qualidade_e_confere`: `rel["gravado"] == {ABA: n, "qualidade": 1}` e as linhas no banco falso.
  - `test_outra_maquina_gravou_ha_menos_de_50_min_pula` e `test_fracttal_vazio_nao_apaga_o_livro_e_sem_token_nao_grava` (os do chamado, para este livro).
  - `test_o_laco_desliga_com_a_chave`: `NEXUS_OS_PUBLICAR = "0"` → `_LACO["thread"] is None`.
  - Em `tests/test_campo_instalar.py`, o marcador do laço novo e as duas listas esperadas.

- [ ] **Step 2: Rodar e ver falhar**

Run: `"$PY" -m pytest -q tests/test_campo_tarefas_os.py tests/test_campo_instalar.py`
Expected: FAIL (`ModuleNotFoundError: nexus.campo.tarefas_os`).

- [ ] **Step 3: Implementar `nexus/campo/tarefas_os.py`** com as interfaces acima (o `ler` padrão é `fracttal.ler`, importado tarde como no chamado). `TIPO_ZELADORIA_REST = "Zeladoria"` fica numa constante: a Task 3 confere a grafia exata no Fracttal. Ligar no `campo.instalar`, depois do laço dos chamados. Pôr `NEXUS_OS_PUBLICAR` em `OPCIONAIS` e no `DEPLOY.md`; na cópia de prova, as duas chaves em "0".

- [ ] **Step 4: Rodar e ver passar**

Run: `"$PY" -m pytest -q tests/test_campo_tarefas_os.py tests/test_campo_instalar.py tests/test_campo_chamados_acompanhamento.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nexus/campo/tarefas_os.py nexus/campo/__init__.py nexus/config.py DEPLOY.md ferramentas/subir_copia_de_prova.py tests/test_campo_tarefas_os.py tests/test_campo_instalar.py
git commit -m "feat(campo): o laço que lê as tarefas das OS do Fracttal e grava o nexus_os de hora em hora (leitura incompleta não grava; NEXUS_OS_PUBLICAR=0 desliga)"
```

### Task 3: O ensaio com o Fracttal de verdade (sem gravar)

**Files:**
- Create: `ferramentas/ensaio_tarefas_os.py`
- Modify: `nexus/campo/tarefas_os.py` (só a constante `TIPO_ZELADORIA_REST`, se o ensaio mostrar outra grafia), `nexus/dados/CLAUDE.md` (o fato novo em "O que existe" e a 1ª medida)

**Interfaces:**
- Consumes: Task 2 (`ler_fracttal`, `publicar(..., forcar=True)`), Task 1 (`linhas`, `conferir_grao`); `nexus.pcm.fonte.ler_gestao(cfg)` (o `gestao_pcm.json`, só para comparar).
- Produces: `python ferramentas/ensaio_tarefas_os.py` (mede e compara, não grava) e `--gravar` (a 1ª gravação, só com o OK do Levi, pelo `publicar(..., forcar=True)`).

- [ ] **Step 1: Escrever a ferramenta.** Imprime só contagens: páginas e tempo por status, linhas lidas, repetidas, chave repetida depois do dedupe (tem de ser 0), % de usina e de equipamento ligados, os valores de `tasks_log_task_type_main` com a contagem (para fixar a grafia de Zeladoria e Teste), quantas do backoffice. E a comparação por usina com o `gestao_pcm.json`, sem nenhuma exclusão nos dois lados (o arquivo do PCM não traz o responsável da OS, então o backoffice não se aplica a ele): tarefas abertas de OS em processo ou verificação e tarefas atrasadas (mais de 10 dias), lado a lado, listando só as usinas com diferença. Depois, à parte, quantas tarefas cada exclusão tira (backoffice, motivo, chamado, zeladoria, teste).
- [ ] **Step 2: Copiar o `.env` da pasta principal para a worktree (sem mostrar) e rodar.**

Run: `"$PY" ferramentas/ensaio_tarefas_os.py`
Expected: chave repetida 0; usina ligada em 98% ou mais (abaixo disso, achar o porquê e consertar no cadastro antes de seguir); a diferença com o `gestao_pcm.json` só de horário (a do robô é de até 30 min antes). Diferença que não seja de horário: parar e explicar ao Levi.

- [ ] **Step 3: Ajustar `TIPO_ZELADORIA_REST`** se a grafia for outra e rodar `"$PY" -m pytest -q tests/test_campo_tarefas_os.py`. Expected: PASS.
- [ ] **Step 4: Escrever a 1ª medida no `nexus/dados/CLAUDE.md`** (páginas, linhas, % ligado, a comparação), sem nome de pessoa.
- [ ] **Step 5: Commit**

```bash
git add ferramentas/ensaio_tarefas_os.py nexus/campo/tarefas_os.py nexus/dados/CLAUDE.md
git commit -m "feat(dados): o ensaio do nexus_os com o Fracttal de verdade - mede, compara com a Gestão PCM e não grava"
```

### Task 4: A conta pura do bloco Manutenção

**Files:**
- Create: `nexus/campo/manutencao.py`
- Test: `tests/test_campo_manutencao.py` (novo)

**Interfaces:**
- Consumes: as linhas do fato (dicts do `visao._livro`, valores podem vir como texto: ler com `fatos._id`/`_int`), as marcas de `motivos.vigentes`, as OS do `fato_chamado`, as linhas do `fato_programacao`.
- Produces:
  - `DIAS_ATRASO = 10` (a régua do PCM: `DIAS_ALERTA` do `gerar_gestao_pcm_json.py`), `META_SEMANA = 85.0` (`relatorios.regras.META`), `LIMITE_PADRAO, LIMITE_MIN, LIMITE_MAX = 30, 10, 365`.
  - `marcas_paradas(vigentes: dict, usina_de) -> list[dict]`: o recorte do Fora da programação (`m["tira"] or m["origem_motivo"] == "app"`), cada uma `{"usina_id", "os", "codigo", "chave", "motivo", "desde": date, "quem"}`, com `chave = fatos.tarefa_chave(m["tarefa"])`, `codigo = equipamento.canon(m["codigo"])` ("" = todos os ativos da OS) e `usina_id = usina_de(m)`.
  - `tarefas_por_usina(tarefas: list[dict] | None, marcas: list[dict], os_de_chamado: set[int], hoje: date) -> dict[int, dict]` com `{"os_abertas", "em_verificacao", "atrasadas", "atrasadas_os", "maior_atraso", "lista_atrasadas": [{"os", "wid", "dias", "tipo"}], "vencem", "paradas", "motivo_comum", "lista_paradas": [{"os", "wid", "motivo", "desde", "quem"}], "zeladoria_proxima", "zeladoria_vencida", "zeladoria_ultima"}`. Viva = `estado_tarefa != "finalizada"` e `status_os` em processo ou verificação. Fora das OS abertas, atrasadas e vencem: `do_backoffice == 1`, `tipo_tarefa` `zeladoria` ou `teste`, OS em `os_de_chamado`, e a tarefa com marca. Atrasada = viva com `(hoje - programada).days > DIAS_ATRASO`. Vencem = viva com programada hoje ou amanhã. Parada = marca cuja tarefa ainda está viva no fato (com `tarefas is None`, toda marca conta). Zeladoria: próxima = a menor programada de hoje em diante entre as vivas; vencida = a menor programada antes de hoje entre as vivas; última = o maior `data_id_fim` entre as finalizadas.
  - `semana_por_usina(prog: list[dict], hoje: date, agora_hhmm: str) -> dict[int, dict]` com `{"passada", "passada_prog", "passada_feitas", "passada_pct", "hoje_devidas", "hoje_feitas"}`. Passada = as linhas com `data_id_semana` igual à segunda da semana anterior (conta do Fechamento: linhas, feita = `status_execucao == "finalizada"`); hoje = as linhas de `data_id_programada == hoje` com `hora_inicio <= agora_hhmm`.

- [ ] **Step 1: Escrever os testes que falham** em `tests/test_campo_manutencao.py`, num dia fixo (`HOJE = date(2026, 10, 21)`, uma quarta):
  - `test_atrasada_e_a_regua_do_pcm`: programada há 10 dias não é atrasada, há 11 é; `maior_atraso == 11`; `atrasadas` conta tarefas e `atrasadas_os` conta OS.
  - `test_as_exclusoes`: backoffice, zeladoria, teste, OS de chamado e tarefa com marca ficam fora das OS abertas e das atrasadas, cada uma num caso.
  - `test_marca_sem_codigo_tira_todos_os_ativos_e_casa_sem_acento`: marca com código "" e tarefa "Inspeção  Visual" casa com as tarefas "inspecao visual" de dois ativos da mesma OS.
  - `test_sem_data_programada_nao_atrasa_nem_vence`.
  - `test_vencem_hoje_e_amanha`.
  - `test_paradas_so_com_a_tarefa_viva_e_o_motivo_mais_comum`: marca de tarefa finalizada não conta; sem o fato (`None`), conta.
  - `test_zeladoria_proxima_vencida_e_ultima`.
  - `test_semana_passada_pela_conta_do_fechamento`: 17 de 20 linhas → `passada_pct == 85.0`; hoje, só as de `hora_inicio` até agora.
  - `test_usina_sem_programacao_fica_neutra`: sem linha da usina na semana passada → `passada_pct is None`.

- [ ] **Step 2: Rodar e ver falhar**

Run: `"$PY" -m pytest -q tests/test_campo_manutencao.py`
Expected: FAIL (`ModuleNotFoundError: nexus.campo.manutencao`).

- [ ] **Step 3: Implementar `nexus/campo/manutencao.py`** com as interfaces acima (módulo puro: nada de rede, banco nem Flask).

- [ ] **Step 4: Rodar e ver passar**

Run: `"$PY" -m pytest -q tests/test_campo_manutencao.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nexus/campo/manutencao.py tests/test_campo_manutencao.py
git commit -m "feat(campo): a conta do bloco Manutenção da Visão do responsável - atrasada pela régua do PCM, as exclusões, as paradas por motivo, a semana fechada e a zeladoria"
```

### Task 5: A Limpeza no Acompanhamento e as paradas abertas

**Files:**
- Modify: `nexus/campo/responsaveis.py` (leitores `limpeza()` e `paradas_abertas(nomes, mes)`; `alertas_acompanhamento` e `linha_acompanhamento` com a Limpeza; `montar` com as duas fontes novas por `fontes.get(...)`; `REGUAS` com a área `limpeza`)
- Test: `tests/test_campo_responsaveis.py`

**Interfaces:**
- Consumes: `visao.rondas().dados` (`todas`, `cobertura`, `validacoes`, `hoje`), `ronda_checklist.respostas()`, `visao.sujidade_vegetacao(todas, cobertura, respostas, 90, hoje_iso, validacoes)` (só a última leitura de cada usina; sem pedir releitura ao Fracttal); `visao._livro(LIVRO_DISP, ABA_DISP_OS)` e a ligação por nome do `disponibilidade()` (:214-220).
- Produces:
  - `limpeza() -> tuple[dict[int, dict], dict]`: por usina a linha do `sujidade_vegetacao` (`data`, `sujidade`, `vegetacao`, `vala`, `sensores_sujos`, `status`).
  - `paradas_abertas(nomes, mes: str) -> tuple[dict[int, list[dict]], dict]`: por usina as OS do mês com `aberta` = sim, cada uma `{"os", "tipo", "escopo", "codigo", "inicio" ("DD/MM HH:MM"), "_ini"}`, a mais antiga primeiro.
  - `u["limpeza"]` e `u["paradas_abertas"]` (lista, vazia quando não há) no `montar`.
  - Na linha do Acompanhamento, `valores["limpeza"]` (`_v("S4 V2", cls)`: crítico se algum item do `status` é crítico, alerta se algum é alerta; sem leitura, `_v("—", "neutro")`) e o item `{"rot": "Limpeza", ...}` no detalhe, só quando há leitura. Os alertas: item crítico do `status` → nível `critico`; alerta → `atencao`.

- [ ] **Step 1: Escrever os testes que falham** em `tests/test_campo_responsaveis.py`, reaproveitando os fixtures `banco` e `tela`:
  - `test_limpeza_na_regua_das_rondas`: com uma ronda de vegetação 5 na Altair, a Limpeza dela é crítica e o nível do Acompanhamento vai a crítico; com sujidade 4, atenção; sem leitura, "—" e sem item no detalhe (a lista do teste da linha 160 não muda).
  - `test_paradas_abertas_de_todas_as_usinas`: a OS 13002 aberta do fixture aparece em `u["paradas_abertas"]` da Altair com o início em "DD/MM HH:MM"; OS fechada não.
  - Atualizar o `vazias` do teste das linhas 199-200 só se ele quebrar (as fontes novas entram por `fontes.get`).

- [ ] **Step 2: Rodar e ver falhar**

Run: `"$PY" -m pytest -q tests/test_campo_responsaveis.py`
Expected: FAIL nos dois testes novos.

- [ ] **Step 3: Implementar** os dois leitores, as duas fontes no `visao_responsaveis()` por `_ler_fonte` (com `info["limpeza"]` e `info["paradas"]`) e a Limpeza nos alertas e na linha do Acompanhamento.

- [ ] **Step 4: Rodar e ver passar**

Run: `"$PY" -m pytest -q tests/test_campo_responsaveis.py tests/test_campo_visao.py`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add nexus/campo/responsaveis.py tests/test_campo_responsaveis.py
git commit -m "feat(campo): a Limpeza da última ronda no Acompanhamento da Visão do responsável e as paradas abertas por usina"
```

### Task 6: O bloco na tela, o limite do supervisor e a faixa

**Files:**
- Modify: `nexus/campo/responsaveis.py` (as fontes do bloco no `visao_responsaveis()`; `BLOCOS`, `REGUAS`, `bloco`, `soma`, `por_responsavel`; as funções novas abaixo)
- Modify: `nexus/torres/campo/__init__.py:325-329` (`TELA_DONA` e `LINKS_DO_BLOCO`) e `:353-396` (a rota com o limite)
- Modify: `nexus/torres/campo/templates/campo/responsaveis.html` (colunas :13-14; ícone :99; resumo :100-112; faixa; limite; nota das réguas :152; cartões :62-80; o card da OS)
- Modify: `nexus/static/campo.css:637-707`
- Test: `tests/test_campo_responsaveis.py`

**Interfaces:**
- Consumes: Task 4 (`marcas_paradas`, `tarefas_por_usina`, `semana_por_usina`, as constantes), Task 5 (`u["paradas_abertas"]`), Task 2 (`tarefas_os.estado()`); `motivos.ler(cfg)`, `motivos.vigentes(cfg, est)` (tirar `_ilegiveis`), a usina da marca por `visao._Base().lig.usina(m["usina"], m["codigo"])`; `visao._livro("nexus_os", "fato_tarefa_os")`, `visao._livro("nexus_programacao", "fato_programacao")`, as OS de `visao._livro(LIVRO_CHAMADOS, ABA_CHAMADOS)`; `livros.atualizado_em(base, s, "nexus_os")`.
- Produces:
  - `u["manutencao"] = {**tarefas.get(uid, {}), **semana.get(uid, {})}` no `montar` (o dado cru, sem nível: o nível depende do limite de quem olha). As fontes leem a configuração por `current_app.config`, como as outras fontes da Visão dentro do `calcular`.
  - `alertas_manutencao(u: dict, limite: int) -> tuple[list[dict], list[str]]`: parada aberta → `critico`; `maior_atraso > limite` → `critico`; atrasada → `atencao`; tarefa parada → `atencao`; `passada_pct < META_SEMANA` → `atencao`; zeladoria vencida → `atencao`.
  - `linha_manutencao(u: dict, limite: int) -> dict` (`valores`: `os`, `atrasadas`, `vencem`, `paradas`, `semana`, `zeladoria`; `det` com OS atrasadas, paradas, semana, zeladoria e as em verificação). **Item de OS no detalhe usa a chave `os_card` (`{"wid", "folio"}`), nunca `numero`**: `numero` vira botão de PT no template.
  - `ordem_da_manutencao(u) -> tuple`: nível, parada primeiro, mais atrasadas, mais paradas, a semana mais baixa, o nome.
  - `com_manutencao(usinas: list[dict], limite: int) -> list[dict]`: cópias rasas com `u["manut"] = {"alertas", "bem", "nivel", "peso", **linha_manutencao(u, limite)}` e `u["nivel"]`/`u["foco"]` refeitos com os três blocos (nunca muda o dicionário da cópia guardada).
  - `limite_do_pedido(valor: str | None) -> int`: número fora de 10 a 365 vai ao mais perto; texto ou vazio vale 30.
  - `BLOCOS` ganha `("manut", "Manutenção", "OS, tarefas paradas, semana e zeladoria")`; `bloco(usinas, "manut")` ordena por `ordem_da_manutencao`; `soma` e `por_responsavel` contam os três blocos.
  - Rota: `?limite=` válido grava o cookie `nexus_resp_limite` (1 ano, `SameSite=Lax`, no caminho do cookie de sessão, respeitando o prefixo); sem o parâmetro, vale o cookie; sem os dois, 30. A rota passa `limite` e usa `com_manutencao(...)` antes de filtrar.
  - `TELA_DONA` ganha `gestao` → `torre_pcm.gestao`, `fora` → `torre_pcm.fora`, `quadro` → `torre_pcm.quadro`, `aprovacao` → `torre_campo.aprovacao`; `LINKS_DO_BLOCO["manut"]` com os quatro.

- [ ] **Step 1: Escrever os testes que falham** em `tests/test_campo_responsaveis.py` (livros `nexus_os` e `nexus_programacao` injetados pelo `_aba`; as marcas de motivo gravadas no banco falso pelas funções do próprio `motivos.py`, como em `tests/test_pcm_motivos.py`, porque os campos vão cifrados; dia fixo por `monkeypatch.setattr(visao, "_agora", ...)`):
  - `test_o_bloco_manutencao_na_tela`: a `section` `id="cr-manut"` vem depois do Acompanhamento, com as seis colunas, e a usina com atrasada de 31 dias está em Focar.
  - `test_o_limite_muda_o_nivel_e_fica_no_cookie`: `?limite=45` deixa a de 31 dias em Acompanhar e responde com `Set-Cookie: nexus_resp_limite=45`; o pedido seguinte, sem o parâmetro, segue com 45.
  - `test_limite_do_cookie_com_lixo`: `limite_do_pedido` com `"abc"`, `""`, `None` → 30; `"0"`, `"-5"` → 10; `"9999"` → 365; a página com o cookie `nexus_resp_limite=abc` responde 200.
  - `test_parada_aberta_poe_em_focar_e_na_faixa_respeitando_o_filtro`: a OS 13002 aberta da Altair aparece na faixa "Parada agora" e a linha da Altair no bloco Manutenção fica crítica; com o filtro de outro responsável, a faixa não mostra a Altair.
  - `test_sem_o_fato_a_tela_avisa_e_nao_cobra`: sem o livro `nexus_os`, o aviso "As OS do Fracttal ainda não chegaram ao banco" e nenhuma usina em Focar por OS.
  - `test_a_tela_diz_que_a_leitura_falhou`: com `tarefas_os.estado()` dublado com erro, a nota diz que a última leitura falhou e de quando são as OS.
  - `test_os_do_detalhe_abre_o_card_e_nao_a_pt`: o botão da OS atrasada tem `data-wid` e não aponta para `/t/campo/responsaveis/pt/`.
  - `test_cartoes_com_os_tres_blocos`: no modo cartões, cada responsável mostra a triagem da Manutenção.

- [ ] **Step 2: Rodar e ver falhar**

Run: `"$PY" -m pytest -q tests/test_campo_responsaveis.py`
Expected: FAIL nos testes novos.

- [ ] **Step 3: Implementar a conta e a rota** (as funções e a rota acima; as fontes novas por `_ler_fonte`, com `info["manut"] = {"publicado", "atualizado_em", "erro_leitura", "semana_passada"}`).

- [ ] **Step 4: Implementar o template e o CSS.** As colunas `manut` e a `limpeza` do `acomp` no dicionário de colunas; o ícone por dicionário (`ph-wrench` para `manut`); o resumo do `manut` (OS abertas, Atrasadas, Paradas, Semana passada) num `elif`; a nota "A semana vem do arquivo do PCM, copiado para o banco de hora em hora" no cabeçalho do bloco; o campo do limite (form GET com os filtros em `hidden`, `type="number" min="10" max="365"`); a faixa "Parada agora" depois dos filtros, com as usinas já filtradas (as 6 mais antigas e "e mais N"); a nota das réguas por `BLOCOS`; o 3º `cr-card-bloco` nos cartões; o `include "oscreator/card_os_abrir.html"` e o clique em `[data-wid]` (`NexusOsCard.abrir(wid, {folio})`, sem `wid` `abrirFolio(folio)`), como em `templates/pcm/gestao.html:216-227`. No CSS: `.cr-bloco--manut{grid-column:1/-1}`, a grade das colunas dele, a coluna nova do `acomp` e as regras de 700 px (no celular a Limpeza some da linha e fica no detalhe), só com tokens.

- [ ] **Step 5: Rodar e ver passar**

Run: `"$PY" -m pytest -q tests/test_campo_responsaveis.py tests/test_campo_visao.py tests/test_nexus_servidor_13_10.py`
Expected: PASS. (O teste que recorta o Acompanhamento até `class="cn-nota"`, linha 235, passa a pegar o bloco novo: recortar até `id="cr-manut"`.)

- [ ] **Step 6: Commit**

```bash
git add nexus/campo/responsaveis.py nexus/torres/campo/__init__.py nexus/torres/campo/templates/campo/responsaveis.html nexus/static/campo.css tests/test_campo_responsaveis.py
git commit -m "feat(campo): o bloco Manutenção na Visão do responsável - faixa Parada agora, limite das atrasadas do supervisor no cookie, o card da OS e os cartões com os três blocos"
```

### Task 7: A prova, a documentação e a entrega

**Files:**
- Modify: `nexus/torres/campo/CLAUDE.md` (Visão do responsável: o bloco, a Limpeza, a faixa, o limite, as fontes, as exclusões e as réguas; a tabela das telas; "Peças em nexus/campo/"), `nexus/dados/CLAUDE.md` (o `nexus_os` em "O que existe")

- [ ] **Step 1: Atualizar os dois `CLAUDE.md`** (corrigir a linha velha, não empilhar).
- [ ] **Step 2: A suíte inteira, uma vez** (com o `.env` copiado, sem mostrar).

Run: `"$PY" -m pytest -q`
Expected: tudo passa; falha que não for desta mudança se diz, com a saída.

- [ ] **Step 3: A tela na cópia de prova** (`python ferramentas/subir_copia_de_prova.py --porta 5170`, entrando pela senha de administrador): escuro e claro, a 1920 px, 1366 px e 375 px. Antes da 1ª gravação, o bloco mostra o aviso de que as OS ainda não chegaram; a Limpeza, a faixa e a semana já vêm do banco real.
- [ ] **Step 4: Parar e pedir ao Levi o OK para a 1ª gravação do `nexus_os`** (`"$PY" ferramentas/ensaio_tarefas_os.py --gravar`) e conferir depois de gravar (a contagem relida e a tela da 5170 com o bloco cheio, nas três larguras).
- [ ] **Step 5: Commit**

```bash
git add nexus/torres/campo/CLAUDE.md nexus/dados/CLAUDE.md
git commit -m "docs(campo): a Visão do responsável com o bloco Manutenção, a Limpeza e a faixa; o nexus_os na camada de dados"
```

- [ ] **Step 6: Levar à `main` só com o OK do Levi** (o caminho do `C:/GridcoAuto/setores/CLAUDE.md`, "Subir"): `git fetch origin` → `git checkout --detach origin/main` → `git merge --no-ff setor-campo-hseq` → a suíte inteira → `git push origin HEAD:main` → `git checkout setor-campo-hseq` → `git merge --ff-only origin/main`. Depois, `curl -s https://app.gridco.com.br/saude` dá o commit no ar.
