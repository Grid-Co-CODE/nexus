# Canto central do OS Creator — plano de execução (etapas 0 a 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** o OS Creator lê ativos, histórico de OS e catálogos de um canto central (memória + disco + banco), atualizado
fora do pico pela credencial da empresa, medido antes e depois, com um caminho só para juntar tarefas em OS e um
porteiro da cota do Fracttal.

**Architecture:** um gancho único no `requests` conta (etapa 0) e depois dosa (etapa 5) todo pedido ao Fracttal; um
registro por hora conta o uso das telas. Ativos, OS e catálogos ganham, cada um, um módulo-dono com uma cópia
imutável em memória por versão, recarregada no boot sem Fracttal; as telas leem dele. A leitura ao vivo pela sessão da
pessoa fica como reserva (visão restrita, PC, canto ainda vazio).

**Tech Stack:** Python 3 / Flask / waitress (um processo, 32 threads), `requests`, a API do banco (`nexus/dados/livros.py`),
pytest com `tests/pg_falso.py` e Fracttal falso.

**Spec:** `docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md` (leia junto: as decisões vêm de lá).

**Worktree e ramo:** `C:\GridcoAuto\wt\nexus-canto-central`, ramo `oscreator/canto-central` (de `origin/main` ac4039f).
Commits locais a cada tarefa; **nada vai ao GitHub sem o OK do Levi** (push na `main` = produção em ~2 min).

## Global Constraints

- pt-BR em tudo, inclusive comentários (comentário explica o porquê, com o caso real); sem emoji na interface.
- Repositório público: nada de nome de colega, e-mail, CPF, segredo nem dado de cliente em arquivo versionado; fixture
  com nome fictício. Nunca imprimir valores do `.env`.
- Cor só por token, nos dois temas do `nexus.css` / `os.css` (`:where(html[data-tema="claro"])`); nada de `#hex` ou
  `rgba()` em regra nova de CSS, template ou JS.
- Endereço nunca a partir da raiz: `{{ raiz }}`, `url_for`, `na_raiz()`, `nexusRota()`.
- Dado novo no banco segue o `nexus/dados/CLAUDE.md`: registrar no `catalogo.py` (Fato, `LIVROS`/`FAMILIAS`,
  `so_cresce`) e em `explica.py` ANTES de gravar; nada pessoal em claro (regra 8); conferir antes e depois
  (`livros.publicar`); uma máquina grava (regra 11).
- Leitura do Fracttal em segundo plano: 1 pedido por segundo; 406/429 espera e tenta de novo; leitura incompleta não
  troca o que existe; nunca gravar numa OS real para testar; teste nunca vai à rede.
- Os leitores do canto central e a gravação do uso só ligam pelo `servir.py` (o servidor). O `app.py` (o PC do Levi) e os
  testes seguem sem eles, como o `teto_os`.
- Cada tarefa termina com os testes dela passando; cada etapa termina com a suíte inteira passando (com o `.env`
  copiado, para o teste de nomes rodar) e o `CLAUDE.md`/README da área corrigido no mesmo trabalho.

## Review Focus

1. **O Fracttal fora do ar ou recusando (429) no meio de uma leitura central** → nada é trocado pela metade; a tela
   segue com a versão anterior e diz de quando ela é ("ativos de HH:MM", "lista das HH:MM"). Teste em cada leitor.
2. **Reinício no meio da gravação da cópia em disco** → gravação atômica (`.parcial` + `os.replace`); cópia corrompida
   ou de formato velho é ignorada no boot, sem derrubar a tela. Teste em cada módulo com cópia em disco.
3. **Pessoa de visão restrita no Fracttal** → nunca recebe a lista central; segue com a dela ao vivo. Teste na etapa 3.
4. **Quem chama alterando o registro compartilhado** (o catálogo e a lista são uma cópia só para todos) → a cópia é
   imutável por versão; quem precisa mudar um registro recebe uma cópia dele. Teste na etapa 2 e na 3.
5. **Hora e dia de Brasília** → os baldes de hora e o `data_id` saem do relógio de Brasília (UTC-3), também perto da
   meia-noite UTC. Teste na etapa 0.

## Decisões de execução (tomadas pelo Claude; vão ao relatório)

- **A sonda dos campos do REST foi barrada** (regra de segurança da sessão sobre credencial). A paridade REST × RPC é
  conferida **em tempo de execução pelo próprio leitor**, contra a `foto_ativos` do banco (que veio do RPC): passando,
  vale o REST; não passando, o leitor diz o motivo no estado e o canto cai no RPC central (uma leitura por dia, para
  todos, pela 1ª sessão), sem a tela piorar.
- **O PC não roda os leitores do canto**: ativos vêm da `foto_ativos` do banco (renovada pelo servidor); o histórico
  no PC segue ao vivo pela sessão (o mesmo caminho da visão restrita). Corrige a escolha 7 do desenho (cota e regra 12).
- **"Um caminho só"** (etapa 5) = as fases 2 a 4 (juntar as tarefas numa OS com a soma do tempo, etiquetas, anexos) num
  módulo único; a fase 1 (criar as tarefas) segue por caminho, porque difere de verdade (planejada × avulsa × clonada).
- **O `api.py`** perde o que as etapas tocam; os nomes que a ponte e os testes usam (`api.X`) ficam como fachada.

---

## Etapa 0 — Medir o uso

### Task 0.1: O contador de pedidos ao Fracttal

**Files:**
- Create: `nexus/casca/fracttal_conta.py`
- Test: `tests/test_casca_fracttal_conta.py`

**Interfaces:**
- Produces:
  - `ligar() -> None` — embrulha `requests.sessions.Session.send` uma vez (idempotente); conta só quando o host termina
    em `fracttal.com`.
  - `origem(nome: str)` — gerenciador de contexto que marca a thread (rota do pedido ou `fundo:<nome>`); sem ele, a
    origem é `fundo:<nome da thread>`.
  - `pedidos_desta_thread() -> int` e `zerar_desta_thread() -> None` — o que o pedido em curso já pediu ao Fracttal.
  - `drenar(ate_hora_id: str) -> list[dict]` — devolve e tira as linhas das horas fechadas: `hora_id` (`AAAAMMDDHH` de
    Brasília), `origem`, `metodo`, `pedidos_qtd`, `recusas_qtd` (406/429), `erros_qtd` (exceção ou ≥ 500),
    `pico_minuto_qtd`; mais uma linha `origem="*"`, `metodo="*"` por hora com o total e o pico por minuto de tudo.
  - `instantaneo() -> list[dict]` — as mesmas linhas, sem tirar (o Raio-X).
- `metodo`: no RPC (`/rpc/proxy`), o `method` do corpo JSON (lista ou objeto; corpo que não é JSON → `rpc`); no REST, o
  1º segmento depois de `/api/` (`work_orders`); o token OAuth → `token`.

- [ ] **Step 1: testes que falham** — `test_conta_so_o_fracttal`, `test_origem_da_thread_e_do_fundo`,
  `test_metodo_do_rpc_e_do_rest`, `test_recusa_e_erro`, `test_pico_por_minuto`, `test_drenar_tira_so_as_horas_fechadas`,
  `test_hora_de_brasilia_perto_da_meia_noite_utc` (02:30Z de 31/10 → `hora_id` `2026103023`), `test_ligar_duas_vezes`.
  O envio falso: um adaptador montado numa `requests.Session` que devolve `Response` com o status pedido.
- [ ] **Step 2:** `python -m pytest tests/test_casca_fracttal_conta.py -q` → falham.
- [ ] **Step 3:** implementar (uma trava; os minutos só da hora corrente).
- [ ] **Step 4:** os testes passam.
- [ ] **Step 5:** commit `feat(casca): o contador de pedidos ao Fracttal (etapa 0 do canto central)`.

### Task 0.2: O uso das telas por hora

**Files:**
- Create: `nexus/casca/uso_os.py`
- Modify: `servir.py` (liga `fracttal_conta.ligar()` e `uso_os.ligar(app)` junto do `teto_os`)
- Modify: os JS do OS Creator que se renovam sozinhos (`os_creator/os_web/static/*.js` e templates): o cabeçalho
  `X-Nexus-Auto: 1` nas chamadas automáticas (Histórico 10 min, Solicitação 15 min, `acompanhamento/estado`, sessão 5 min)
- Test: `tests/test_casca_uso_os.py`

**Interfaces:**
- Consumes: `fracttal_conta.origem`, `pedidos_desta_thread`, `zerar_desta_thread`.
- Produces:
  - `normalizar_rota(caminho: str) -> str` — sem query; segmento só de dígitos → `<n>`; hex/uuid longo → `<id>`
    (`/os/os/16995` → `/os/os/<n>`).
  - `ligar(app, *, gravar: bool) -> None` — `before_request`/`teardown_request` só para `/os/` e `/t/os/` (fora
    `/os/static/`); marca a origem do contador com a rota normalizada.
  - `drenar(ate_hora_id: str) -> list[dict]` — linhas `hora_id`, `rota`, `automatico` (1/0), `pedidos_qtd`,
    `pessoas_qtd`, `duracao_p50_ms`, `duracao_p95_ms`, `erros_qtd` (≥ 500), `ocupado_qtd` (o 503 do teto),
    `fracttal_qtd`.
  - `instantaneo() -> dict` — o mesmo, sem tirar, e o corte por setor.
- Pessoa: o HMAC do e-mail da sessão (`campo/ligacao_cadastro.codigo_da_pessoa`) num conjunto **só na memória**, por
  balde; nunca vai a disco nem ao banco. Automático = cabeçalho `X-Nexus-Auto: 1` ou rota da lista fixa
  (`/os/_nexus/sessao`, `.../acompanhamento/estado`).
- **Corte por setor** (o setor da pessoa, como a casca já o acha para o menu): só no disco do servidor,
  `<pasta de dados>/casca/uso_os_setor.json`, 30 dias, gravação atômica. Nunca no banco.
- **O reinício não perde a hora:** a cada 5 min os baldes (só contagens) vão a `<pasta de dados>/casca/uso_os_parcial.json`
  (atômico) e voltam no boot; `pessoas_qtd` depois de um reinício é aproximado (soma dos dois lados, no máximo
  `pedidos_qtd`). Dito no `CLAUDE.md` da casca.

- [ ] **Step 1: testes que falham** — `test_normalizar_rota`, `test_conta_clique_e_automatico`,
  `test_pessoas_distintas_sem_guardar_quem` (o JSON parcial não tem e-mail nem HMAC),
  `test_p50_p95`, `test_erro_e_ocupado`, `test_fracttal_atribuido_ao_pedido`, `test_static_fora`,
  `test_parcial_volta_no_boot`, `test_parcial_corrompido_ignorado`, `test_setor_so_no_disco_30_dias`.
  App Flask de teste com rotas `/os/...` falsas e sessão com e-mail fictício.
- [ ] **Step 2–4:** falham → implementar → passam.
- [ ] **Step 5:** commit `feat(casca): o uso das telas do OS Creator por hora (etapa 0)`.

### Task 0.3: A gravação de hora em hora no banco

**Files:**
- Create: `nexus/dados/fato_uso_os.py`
- Modify: `nexus/dados/catalogo.py` (2 fatos, o livro da família em `LIVROS`/`FAMILIAS` com `so_cresce`),
  `nexus/dados/explica.py` (`RESUMO`, `PARA_QUE`), `nexus/casca/uso_os.py` (o laço de gravação)
- Test: `tests/test_dados_fato_uso_os.py`

**Interfaces:**
- Livro: `nexus_oscreator_uso_AAAA_MM` (um por mês do `hora_id`), abas `fato_uso_hora` e `fato_fracttal_hora`.
  Grão: 1 linha = 1 rota × automático × hora (uso); 1 linha = 1 origem × método × hora (Fracttal). Tipo: foto periódica.
  Chaves: (`hora_id`, `rota`, `automatico`) e (`hora_id`, `origem`, `metodo`). Mais `data_id` (o dia de Brasília) e
  `hora` (0–23). Medidas: `_qtd` aditivas; `_ms` não somam.
- `gravar(linhas_uso: list[dict], linhas_fracttal: list[dict], *, base, token, sessao) -> dict` — agrupa por mês, relê o
  livro do mês, troca as linhas da mesma chave (regravar a mesma hora não duplica), publica pelo `livros.publicar`.
- O laço (em `uso_os`, só com `gravar=True`): no minuto :05 de cada hora drena as horas fechadas dos dois contadores e
  grava; falhou, guarda as linhas e tenta na hora seguinte (no máximo 48 h guardadas).

- [ ] **Step 1: testes que falham** — `test_grao_e_chave` (`conferir_grao`), `test_mesma_hora_regravada_nao_duplica`,
  `test_virada_do_mes_vai_a_dois_livros`, `test_nada_pessoal_nas_colunas`, `test_catalogo_registra_o_livro_e_os_fatos`
  (o teste da camada já cobra `explica`), `test_falha_guarda_para_a_proxima_hora`; com `tests/pg_falso.py`
  (inclusive `como_texto=True`).
- [ ] **Step 2–4:** falham → implementar → passam; `python -m pytest tests/test_dados_camada.py -q` passa.
- [ ] **Step 5:** commit `feat(dados): o uso do OS Creator no banco, por hora (etapa 0)`.

### Task 0.4: A seção do Raio-X

**Files:**
- Modify: `nexus/casca/raio_x.py` e o template que ele renderiza
- Test: `tests/test_casca_raio_x_uso_os.py`

**Interfaces:**
- Consumes: `fato_uso_os` (leitura dos livros dos últimos 7 dias, guardada 10 min), `uso_os.instantaneo()`,
  `fracttal_conta.instantaneo()`, o arquivo do corte por setor.
- Mostra: as 15 rotas mais pedidas em 7 dias (cliques e automáticos separados, mediana e p95); os cliques por hora do
  dia; os pedidos ao Fracttal por hora (total e o pico por minuto, com a cota de 200 ao lado); o corte por setor. Sem
  dado (PC, banco fora): "sem medição ainda", sem quebrar a página.

- [ ] **Step 1–4:** testes (`test_secao_com_dado`, `test_secao_sem_dado`, `test_sem_cor_fixa`) → implementar → passam.
- [ ] **Step 5:** `nexus/casca/CLAUDE.md` (o uso e o contador), `DESEMPENHO.md` (como ler a seção), linha nova em
  "O que existe" do `nexus/dados/CLAUDE.md`; suíte inteira; commit `feat(casca): a seção Uso do OS Creator no Raio-X`.

---

## Etapa 1 — O Nexus como casa única

### Task 1.1: Sem a sincronia com o oem

**Files:**
- Delete: `ferramentas/sincronizar_oscreator.py`, `nexus/torres/oscreator/sincronia.json` e os testes só deles
- Modify: `nexus/torres/oscreator/README.md` (o topo: o Nexus é a casa; o oem congelado), `CLAUDE.md` da raiz (a linha
  "o clone fica idêntico ao do oem de propósito"), e todo `.md` que mande sincronizar (`grep -rn "sincroniz"`)

- [ ] **Step 1:** `grep -rn "sincronia\|sincronizar_oscreator\|idêntico ao do oem\|identico ao oem" --include=*.py --include=*.md .`
  lista tudo; nada fica apontando para o que sai.
- [ ] **Step 2:** apagar e corrigir; a suíte do OS Creator (`-k oscreator`) passa.
- [ ] **Step 3:** commit `refactor(oscreator): o Nexus é a casa do OS Creator web; o oem fica congelado (etapa 1)`.

### Task 1.2: O caminho web sem PyQt

**Files:**
- Modify/Delete: o que em `nexus/torres/oscreator/os_creator/` importa `PyQt6` no caminho da ponte e do `os_web`
  (o que for só do app de mesa sai da cópia do Nexus)
- Modify: os testes com `pytest.importorskip("PyQt6")`
- Test: `tests/test_oscreator_sem_pyqt.py`

- [ ] **Step 1: teste que falha** — `test_ponte_e_os_web_importam_sem_pyqt`: num subprocesso com `sys.modules["PyQt6"] = None`
  (e os submódulos), importar `nexus.torres.oscreator.ponte`, `api` e todos os `os_web.*`.
- [ ] **Step 2–4:** falha → cortar a dependência (arquivo só do app de mesa sai; import tardio onde for o caso) → passa.
- [ ] **Step 5:** tirar o `importorskip("PyQt6")` dos testes; suíte inteira; commit
  `refactor(oscreator): o caminho web do OS Creator sem PyQt (etapa 1)`.

---

## Etapa 2 — Os ativos centrais

### Task 2.1: O catálogo central em memória

**Files:**
- Create: `nexus/torres/oscreator/os_creator/ativos_central.py`
- Modify: `api.py` (`load_assets_cached`, `_asset_by_code`, `_code_loc`/`_code_to_loc`, `ativos_do_cliente` se morar lá),
  `os_web/rotas_solic.py` (`_indice_ativos` e o renovador dele saem)
- Test: `tests/test_oscreator_ativos_central.py`

**Interfaces:**
- Produces:
  - `class Catalogo` (imutável): `lista: tuple[dict]` (registros no formato de hoje: `id`, `code`, `description`,
    `id_parent`, `id_type_item`, `id_group_task`, `parent_description`, `cliente`, `usina`, `tipo_code`, `tipo`,
    `label`), `por_id`, `por_codigo`, `por_cliente_usina`, `versao` (sha das linhas ordenadas), `lido_em`, `fonte`
    (`banco`, `rest`, `rpc`, `disco`).
  - `atual() -> Catalogo | None`; `trocar(registros: list[dict], fonte: str) -> bool` (troca inteira; recusa lista
    vazia ou que encolhe mais de 5% contra a atual); `registro(codigo) -> dict | None` (uma CÓPIA).
  - `estado() -> dict` (fonte, lido_em, versão, motivo da última recusa, paridade do REST).
- Boot: carrega a cópia em disco (`<dados>/oscreator/ativos.json.gz`, atômica) e, por trás, a `foto_ativos` do banco;
  nenhum pedido ao Fracttal. O `assets_cache.json` deixa de ser fonte (lido uma última vez, se for a única cópia).
- `load_assets_cached()` devolve `atual().lista` sem copiar a lista; auditar quem muda registro e trocar por
  `registro()`/cópia.

- [ ] **Step 1: testes que falham** — `test_telas_leem_sem_pedir_ao_fracttal` (Fracttal falso que conta: 0 pedidos em
  `load_assets_cached`, `_asset_by_code`, `ativos_do_cliente`, índice da Solicitação), `test_boot_pelo_disco_e_pelo_banco`,
  `test_registro_e_copia` (mudar o devolvido não muda o catálogo), `test_troca_recusa_vazia_e_encolhida`,
  `test_disco_corrompido_ignorado`, `test_busca_por_codigo_sem_varrer` (índice).
- [ ] **Step 2–4:** falham → implementar → passam; os testes de catálogo de hoje
  (`test_oscreator_catalogo_por_tras_24_10.py` e afins) ajustados ao novo dono, sem perder o que eles provam.
- [ ] **Step 5:** commit `feat(oscreator): o catálogo de ativos central, um para todas as telas (etapa 2)`.

### Task 2.2: O leitor da madrugada e dos novos, com a paridade conferida

**Files:**
- Create: `nexus/torres/oscreator/os_creator/ativos_leitor.py`
- Modify: `nexus/dados/` — a renovação da `foto_ativos` (mover a montagem de `ferramentas/carregar_ativos_fracttal.py`
  para um módulo que a ferramenta e o leitor usam), `catalogo.py` (a coluna nova no fim)
- Test: `tests/test_oscreator_ativos_leitor.py`

**Interfaces:**
- Consumes: `nexus.campo.fracttal.ler(path)` (REST, credencial do Nexus), `ativos_central.trocar`, `api._build_records`.
- Produces:
  - `ler_todos_rest() -> list[dict]` (100 por página, 1 por segundo, para pelo total informado; incompleta → exceção);
  - `ler_novos_rest(maior_id: int) -> list[dict]` (`sort=id:desc`, para quando uma página inteira já é conhecida);
  - `para_registro(itens_rest: list[dict]) -> list[dict]` — o formato cru do RPC: `parent_description` do próprio item
    se vier; senão montado pela cadeia de `id_parent` (descrições dos ancestrais, sem a raiz da organização);
    `id_group_task` do item se vier; senão o da foto para o mesmo `id`; senão `None` (resolvido ao vivo quando usado);
  - `conferir_paridade(registros, foto_por_codigo) -> tuple[bool, str, float]` — vale se ≥ 99% dos códigos em comum
    dão o mesmo cliente e usina e os campos obrigatórios estão presentes;
  - `ligar(app) -> None` (só pelo `servir.py`): completo às 02:15 de Brasília; novos a cada 30 min das 06:00 às 22:00.
    Paridade falhou → estado diz o motivo e o completo do dia vai pelo RPC na 1ª sessão (o renovador de hoje, uma vez
    por dia, para todos).
- `foto_ativos`: troca só quando o sha muda; código que sumiu do Fracttal **fica**, com `fora_do_fracttal_desde`
  (`data_id`, coluna nova no FIM); a leitura incompleta ou que encolhe mais de 5% não grava; uma máquina por vez.

- [ ] **Step 1: testes que falham** — `test_completo_pagina_e_para_no_total`, `test_incompleto_nao_troca`,
  `test_429_espera_e_tenta`, `test_novos_param_na_pagina_conhecida`, `test_caminho_montado_pelos_pais`,
  `test_paridade_passa_e_falha` (falha → cai no RPC uma vez por dia), `test_foto_guarda_o_codigo_que_saiu`,
  `test_foto_so_grava_quando_muda`.
- [ ] **Step 2–4:** falham → implementar → passam.
- [ ] **Step 5:** commit `feat(oscreator, dados): os ativos lidos de madrugada pela credencial da empresa (etapa 2)`.

### Task 2.3: Os botões "Atualizar ativos" e a tela

**Files:**
- Modify: `os_web/rotas_ativos.py`, `os_web/rotas_tradicional.py`, `os_web/rotas_solic.py` (as três rotas de atualizar),
  os templates/JS que mostram a data dos ativos
- Test: `tests/test_oscreator_ativos_botao.py`

- [ ] **Step 1–4:** testes (`test_botao_pede_os_novos_por_tras`, `test_tela_diz_ativos_de_hhmm`,
  `test_pc_usa_a_sessao_da_pessoa`) → implementar: no servidor, o botão pede os novos por trás e responde na hora com
  "ativos de HH:MM"; no PC (sem o leitor), o RPC com a sessão da pessoa, como hoje, para dentro do catálogo central.
- [ ] **Step 5:** README do OS Creator (seção nova, linhas velhas do catálogo corrigidas), `nexus/dados/CLAUDE.md` (a
  `foto_ativos` deixa de ser carga única); suíte inteira; commit `feat(oscreator): atualizar ativos sem esperar o Fracttal`.

---

## Etapa 3 — O histórico de OS central

### Task 3.1: A lista central de OS

**Files:**
- Create: `nexus/torres/oscreator/os_creator/os_central.py`
- Test: `tests/test_oscreator_os_central.py`

**Interfaces:**
- Produces:
  - registro enxuto por OS com os campos que o Histórico, o Garantias e o card mostram (o construtor lista a partir do
    `_historico_linhas.html` e do `list_minhas_os`), montado das linhas do REST `work_orders` (uma por tarefa, agrupadas
    por `id_work_order`) ou do RPC (a ação do OS Creator);
  - `Lista` imutável por versão: `por_id`, `por_folio`, `por_codigo_ativo`, `lido_em`, `janela` (de, até);
  - `receber(linhas_rest: list[dict], faixa: str) -> None` (troca as OS daquela leitura; a faixa diz o que a leitura
    cobre, para a OS que mudou de status sair da faixa antiga), `atualizar_os(id_work_order: int, registro: dict | None
    = None) -> None` (a ação do OS Creator entra na hora; sem `registro`, lê a OS ao vivo pela sessão do pedido em curso,
    1 a 3 pedidos, o que o card já lê; fora de um pedido, marca a OS para a próxima faixa),
    `filtrar(visao, pessoa, de, ate) -> list`, `folio_para_id(folio) -> int | None`,
    `estado() -> dict`;
  - cópia em disco atômica `<dados>/oscreator/os_central.json.gz`, carregada no boot.
- Mapeamento REST → registro: os campos que o Nexus já lê do REST (`wo_folio`, `id_work_order`, `description`, `code`,
  `items_log_description`, `id_status_work_order`, `id_personnel`, `personnel_description`, `created_by`,
  `creation_date`, `date_maintenance`, `initial_date`, `final_date`, `wo_final_date`, `tasks_log_task_type_main`,
  `parent_description`, `labels`, `id_parent_wo`, `tasks_duration`, `id_task`, `id_work_orders_tasks`). Campo que a tela
  usa e o REST não tem: anotado no README e vazio na lista central, preenchido pela leitura ao vivo do card.

- [ ] **Step 1–4:** testes (`test_agrupa_tarefas_por_os`, `test_faixa_troca_so_o_que_cobre`,
  `test_acao_entra_na_hora`, `test_folio_para_id_sem_pedido`, `test_filtros_das_visoes`, `test_disco_atomico_e_corrompido`,
  `test_lista_e_copia_para_quem_muda`) → implementar → passam.
- [ ] **Step 5:** commit `feat(oscreator): a lista central de OS (etapa 3)`.

### Task 3.2: O leitor em faixas

**Files:**
- Create: `nexus/torres/oscreator/os_creator/os_leitor.py`
- Modify: `nexus/campo/tarefas_os.py` (entrega a leitura das abertas, já feita de hora em hora, ao `os_central`, sem mudar
  o fato nem o custo dela)
- Test: `tests/test_oscreator_os_leitor.py`

**Interfaces:**
- `ligar(app)` (só `servir.py`). Faixas, pela credencial do Nexus, 1 pedido por segundo, longe dos minutos ocupados:
  - **novas:** `work_orders?sort=creation_date:desc` até uma página inteira conhecida; a cada 3 min das 06:00 às 20:00
    de seg a sex e a cada 15 min fora disso;
  - **7 dias:** as criadas nos últimos 7 dias, relidas inteiras a cada 10 min (06:00–20:00);
  - **abertas:** recebidas do `tarefas_os` (status 1 e 2), de hora em hora;
  - **finalizadas:** status 3, `sort=final_date:desc`, desde a data de fim mais nova conhecida menos 2 dias, parando
    quando uma página INTEIRA passa do piso (a técnica da zeladoria), de hora em hora. É a leitura do desenho do PCM de
    27/10: o fato `fato_tarefa_finalizada` não é publicado aqui;
  - **madrugada (03:20):** a janela de 90 dias inteira, para as mudanças sem data de alteração.
- Leitura que falha no meio não chama `receber`.

- [ ] **Step 1–4:** testes (`test_novas_param_na_pagina_conhecida`, `test_sete_dias_inteiros`,
  `test_abertas_vem_do_tarefas_os_sem_pedido_a_mais`, `test_finalizadas_param_no_piso`,
  `test_falha_no_meio_nao_troca`, `test_horarios_das_faixas`, `test_tarefas_os_segue_igual` (o fato e o número de
  pedidos de antes)) → implementar → passam.
- [ ] **Step 5:** commit `feat(oscreator): o histórico de OS lido em faixas fora do pico (etapa 3)`.

### Task 3.3: As telas leem da lista central

**Files:**
- Modify: `os_web/historico_store.py` e `os_web/rotas.py` (Histórico e as visões), `os_web/rotas_acomp.py` (Garantias),
  a marcação verde dos Ativos (`api.codigos_os_recentes`), `os_web/rotas_investigar.py`, `api.os_por_folio`, o card
  (1ª pintura), as ações que criam ou mudam OS (criar, clonar, aprovar, cancelar, finalizar, responsável, nota) chamando
  `os_central.atualizar_os`, e o `historico.html` (sem o `atualizar=1` forçado ao fechar o card)
- Test: `tests/test_oscreator_historico_central.py`

- [ ] **Step 1–4:** testes (`test_historico_sem_pedido_ao_fracttal`, `test_visao_restrita_segue_com_a_dela`,
  `test_criadas_por_mim_pela_lista_central` (quem não casa sem ambiguidade segue ao vivo),
  `test_garantias_e_ativos_e_investigar_da_mesma_lista`, `test_card_alterado_aparece_sem_releitura`,
  `test_pc_segue_ao_vivo`, `test_virada_do_dia_nao_rele_tudo`) → implementar → passam; os testes de 19/10
  (`test_oscreator_historico_compartilhado_19_10.py`) ajustados sem perder o que provam.
- [ ] **Step 5:** README (o Histórico central; a seção de 19/10 corrigida), suíte inteira, medir a memória (o cartão do
  Raio-X numa cópia de prova com a lista cheia de um arquivo de ensaio); commit
  `feat(oscreator): Histórico, Garantias, Ativos e card da lista central (etapa 3)`.

---

## Etapa 4 — Os catálogos pequenos num lugar só

### Task 4.1: Um dono por catálogo

**Files:**
- Create: `nexus/torres/oscreator/os_creator/catalogos.py`
- Modify: os 7 caminhos de pessoas (`rotas.py` ~568 e ~739, `rotas_solic.py` ~133, `api.py` ~1383 e ~2081,
  `rotas_cos.py` ~120, `rotas_solic_eng.py` ~104), os 4 de etiquetas, os 3 de tipos e classificações, as falhas do COS
- Test: `tests/test_oscreator_catalogos.py`

**Interfaces:**
- `pessoas()`, `etiquetas()`, `tipos_classif()`, `falhas()`, `status()` → listas no formato que as telas usam hoje;
  `plano(id_item, id_group_task)` e `detalhe_do_plano(id_task, id_item)` → o de hoje.
- Cada um: prazo próprio (pessoas e etiquetas 6 h; tipos, falhas e status 24 h; planos 24 h), cópia em disco atômica
  em `<dados>/oscreator/catalogos/`, aquecido no boot por trás (sem pedido quando o disco está em dia), renovado fora do
  pico quando há leitor; sem leitor da empresa para o assunto, a 1ª sessão do dia renova, uma vez para todos.
- Pessoas: pelo REST do cadastro (`nexus/cadastro/fracttal_pessoal.py`) se trouxer os campos da tela; senão RPC.
- Planos da Performance: guardados por ativo (e por grupo, se o construtor provar que o plano é o mesmo por
  `id_group_task`): a 2ª escolha da mesma usina não pede nada.

- [ ] **Step 1–4:** testes (`test_um_pedido_para_todas_as_telas` por catálogo, `test_reinicio_sem_pedido`,
  `test_disco_corrompido`, `test_performance_segunda_vez_sem_pedido`, `test_prazo_vencido_renova_por_tras`) →
  implementar → passam; os testes de hoje das telas que usam os catálogos seguem passando.
- [ ] **Step 5:** README, suíte inteira, commit `feat(oscreator): pessoas, etiquetas, tipos e planos num lugar só (etapa 4)`.

---

## Etapa 5 — Um caminho só para juntar em OS e o porteiro

### Task 5.1: O caminho único das fases 2 a 4

**Files:**
- Create: `nexus/torres/oscreator/os_creator/os_juntar.py`
- Modify: `api.py` — `create_planned_os_multi`, `create_planned_os_one_wo`, `create_work_orders_agrupada`,
  `create_performance_os_agrupada`, `clonar_os`, a retomada de `aprovar_solicitacao`, `create_work_orders_bulk` e
  `create_work_orders_datas` (estes, uma OS por tarefa)
- Test: `tests/test_oscreator_os_juntar.py`

**Interfaces:**
- `juntar_em_os(id_tasks: list, duracoes: dict, id_responsible, responsible_name: str = "", *, id_parent=None,
  note: str = "", etiqueta_ids: list | None = None, imagens: dict | None = None) -> dict` — kanban (`_kanban_records`)
  → `_work_order_insert` com `duration=_tempo_da_os(...)` → etiquetas → imagens → devolve
  `{"id_work_order", "wo_folio", "id_tasks", "aviso"?}` com os avisos de hoje (kanban fora, tarefa não achada, etiqueta
  que falhou) e chama `os_central.atualizar_os(id_work_order)` (etapa 3).
- Os payloads enviados ao Fracttal não mudam (os testes de hoje que conferem payload seguem passando sem ajuste).

- [ ] **Step 1–4:** testes (`test_todos_os_caminhos_passam_pelo_juntar`, `test_tempo_e_a_soma_em_todos`,
  `test_avisos_de_hoje`, `test_payload_igual_ao_de_antes` com um registro do payload de cada caminho gravado antes da
  troca) → implementar → passam.
- [ ] **Step 5:** commit `refactor(oscreator): um caminho só para juntar as tarefas numa OS (etapa 5)`.

### Task 5.2: O porteiro do Fracttal

**Files:**
- Modify: `nexus/casca/fracttal_conta.py` (o mesmo gancho da etapa 0)
- Test: `tests/test_casca_porteiro.py`

**Interfaces:**
- Conta deslizante de 60 s de todos os pedidos do Nexus ao Fracttal. **Teto do Nexus: 150 por minuto** (sobram 50 da
  cota de 200 para o App de Campo e os robôs); **o fundo até 90 por minuto**. O pedido de quem está clicando (thread de
  pedido HTTP) nunca é recusado: com o minuto cheio, espera até 2 s e segue. O de fundo espera a vez (sem limite de
  espera, mas a leitura em curso continua contando como em andamento). `estado()` diz quantas esperas houve por hora
  (vai ao `fato_fracttal_hora` como `esperas_qtd`, coluna no fim).

- [ ] **Step 1–4:** testes (`test_fundo_espera_acima_de_90`, `test_clique_nunca_recusado`, `test_teto_de_150`,
  `test_esperas_contadas`, com relógio falso) → implementar → passam.
- [ ] **Step 5:** commit `feat(casca): o porteiro do Fracttal para o Nexus inteiro (etapa 5)`.

### Task 5.3: O que sobra do `api.py`

**Files:**
- Modify: `api.py` (o que as etapas tocaram vai para os módulos novos; `api.X` fica como fachada para a ponte e os testes)
- Test: a suíte inteira

- [ ] **Step 1:** `wc -l api.py` antes e depois (vai ao relatório).
- [ ] **Step 2:** mover; a suíte inteira passa; README do OS Creator com o mapa dos módulos.
- [ ] **Step 3:** commit `refactor(oscreator): o api.py dividido pelos donos de cada assunto (etapa 5)`.

---

## Fecho

- [ ] A suíte inteira passa na worktree; as telas tocadas conferidas no Chrome sem janela (1280 e 375 px, escuro e
  claro), pelo molde das páginas renderizadas por teste.
- [ ] O desenho corrigido onde a execução decidiu diferente (a escolha 7).
- [ ] O relatório ao Levi: o que foi feito por etapa, as decisões e por quê, o que ficou para ligar no servidor e o
  pedido de OK para subir (etapa por etapa).
