# Zeladoria no Nexus, etapas 1 e 2: plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Copiar as 39 tabelas do Radar (Supabase) para três livros do banco do Nexus, por comando, e abrir as 18 abas
do Radar dentro do Nexus como uma torre só leitura, com o dado real.

**Architecture:**
- Um comando lê o Supabase com um papel só de leitura (`pg8000`) e grava os livros pelo `livros.publicar`, com o dado
  pessoal cifrado pelo `Cofre` do cadastro.
- A torre `zeladoria` serve o `index.html` do Radar já limpo de nomes, dentro de um iframe da casca. No lugar do
  supabase-js, ele recebe uma ponte (`ponte.js`) que lê pelas rotas da torre.
- Nada é gravado pela torre nestas etapas.

**Tech Stack:** Python 3.14, Flask, `pg8000==1.31.6`, openpyxl (já no Nexus), JS puro (ponte), node só nos testes.

**Spec:** `docs/superpowers/specs/2026-11-03-zeladoria-no-nexus-design.md` (leia antes).

**Referências (fora do repositório, só leitura):**
- o pacote do Radar: `C:\Users\Levi Maia\Downloads\Deploy\radar_2026-10-28\radar` (`public/index.html`, `tests/`,
  `supabase/functions/`);
- o mapa das tabelas: o `radar_modelo_de_dados.md` do scratchpad desta sessão (cópia em
  `Downloads\Deploy\radar_2026-10-28\` quando o Levi pedir);
- o cliente oficial do Supabase v2.118: `Downloads\Deploy\referencias_supabase\` (`postgrest-js/src/PostgrestBuilder.ts`
  diz a forma da resposta).

## Antes de começar

- Trabalhar sobre o `origin/main` (esta worktree está atrás). O `sync_with_base_branch` só funciona depois que o Levi
  confirmar a origem em Help → Troubleshooting → Review Pinned Git Origins; até lá, abrir uma worktree nova a partir do
  `origin/main`.
- **Copiar o `.env` para a worktree antes da suíte:** sem ele, o `test_sem_nomes_no_repositorio.py` pula.
- **A etapa 0 é do Levi e precede a Task 3 de verdade:**
  - o `retrato_do_banco.csv` salvo em `Downloads\Deploy\radar_2026-10-28\`;
  - o papel só de leitura criado no Supabase;
  - a conexão dele colada em Base → Chaves das fontes → aba Nexus.

  As Tasks 1, 2, 4 e 5 não dependem disso.

## Global Constraints

- **Repositório público:** nenhum nome de colega, e-mail real, dado de usina, de fornecedor ou de valor, nem chave,
  nem o id ou a URL do projeto Supabase, em arquivo versionado. Fixture de teste com nome fictício. Os nomes das
  tabelas do Supabase que contêm o nome do supervisor nunca aparecem literais: casam por padrão (Task 1).
- **Regra 10 do `nexus/dados/CLAUDE.md`:** livro registrado em `catalogo.LIVROS` antes da primeira gravação, com
  `no_banco=False`.
- **Livros e abas:**
  - `nexus_zeladoria_app` (31 abas + `atualizacao`);
  - `nexus_zeladoria_fracttal` (`fracttal_rondas`, `fracttal_fotos`, `fracttal_sync`, `fracttal_ultimas` +
    `atualizacao`);
  - `nexus_zeladoria_historico` (`log`, `financeiro_historico`, `fin_provisao_historico`, `cronograma_alteracoes` +
    `atualizacao`), com `so_cresce` nas quatro abas de dado.
- **Cifra:** `Cofre(cfg["NEXUS_CHAVE_CADASTRO"])` de `nexus/cadastro/cifra.py`, com o contexto
  `zeladoria/<aba>/<valor da chave da linha>/<coluna>`.
- **Célula do xlsx:** no máximo 32.767 caracteres. O valor maior que `PARTE = 32000` vai partido em colunas
  `<coluna>__p2`, `<coluna>__p3`…, e o número de linhas nunca muda.
- **Até a troca:** a torre não grava no banco, e só pede ao Fracttal as fotos de uma ronda, no clique.
- **Endereço:** `{{ raiz }}`, `url_for`, `na_raiz()` no Python, `nexusRota()` no JS da casca. A ponte recebe as bases
  prontas do servidor em `window.ZELADORIA`.
- **Login:** toda rota nova exige login (nenhuma em `ROTAS_PUBLICAS`).
- **Código novo:** pt-BR, comentário com o porquê, sem emoji. O clone mantém os emojis até a etapa 3.
- **Commit e push:** commit só com o OK do Levi; push na `main` vai para produção em ~2 min.

## Review Focus

1. **Tabela nova no Supabase que o mapa não conhece:** a cópia para, diz qual é a tabela e não grava nenhum livro
   (teste na Task 3).
2. **Conexão colada com permissão de escrita:** a Chave do Nexus recusa e diz por quê (teste na Task 3).
3. **Pessoa logada no Nexus sem linha em `perfis`, ou pendente:** vê a tela de "aguardando aprovação" do Radar e nenhum
   dado além da própria linha (teste na Task 6).
4. **Livro da zeladoria ainda não gravado ou lido vazio:** a tela diz "a cópia do Radar ainda não foi feita" e não
   mostra o Radar vazio como se não houvesse dado (teste na Task 6).
5. **Cifra que não abre (chave trocada):** a coluna vem como `"(não abre)"`, o log diz qual aba e coluna, e a tela não
   cai (testes nas Tasks 2 e 6).

---

### Task 1: O mapa das tabelas e o registro no catálogo

**Files:**
- Create: `nexus/zeladoria/__init__.py` (vazio, com a docstring do pacote), `nexus/zeladoria/tabelas.py`
- Modify: `nexus/dados/catalogo.py` (três `Livro` em `LIVROS`; as abas em `ABAS_FORA_DA_REGRA`)
- Test: `tests/test_zeladoria_tabelas.py`

**Interfaces:**
- Produces, em `nexus/zeladoria/tabelas.py`:
  - `LIVRO_APP = "nexus_zeladoria_app"`, `LIVRO_FRACTTAL = "nexus_zeladoria_fracttal"`,
    `LIVRO_HISTORICO = "nexus_zeladoria_historico"`;
  - `TABELAS: dict[str, str]`: aba → livro, com as 40 abas (39 tabelas + `fracttal_ultimas`);
  - `class TabelaDesconhecida(ValueError)`;
  - `nome_no_nexus(nome_supabase: str) -> str`;
  - `aba_da_view(view: str) -> str`;
  - `coluna_cifrada(aba: str, coluna: str) -> bool`.

- [ ] **Step 1: Write the failing tests**
  - `test_as_40_abas_em_um_livro_so`:
    - `len(TABELAS) == 40`;
    - os valores ⊆ dos três livros;
    - `TABELAS["fracttal_ultimas"] == LIVRO_FRACTTAL`;
    - `TABELAS["log"] == LIVRO_HISTORICO`;
    - `TABELAS["cotacoes"] == LIVRO_APP`.
  - `test_equipe_primarizada_casa_por_padrao`:
    - `nome_no_nexus("gastos_fulano") == "gastos_equipe"`;
    - `nome_no_nexus("orcamento_fulano_semanal") == "orcamento_equipe_semanal"`;
    - `nome_no_nexus("tipos_gasto_fulano") == "tipos_gasto_equipe"`;
    - `nome_no_nexus("simulacao_repasse_fulano") == "simulacao_repasse_equipe"`;
    - `nome_no_nexus("rota_fulano") == "rota_equipe"`;
    - `nome_no_nexus("cotacoes") == "cotacoes"`.
  - `test_tabela_desconhecida_para`: `pytest.raises(TabelaDesconhecida)` para `nome_no_nexus("tabela_nova")`.
  - `test_view_vira_aba`:
    - `aba_da_view("rf_cotacoes") == "cotacoes"`;
    - `aba_da_view("rf_rota_fulano") == "rota_equipe"`;
    - `aba_da_view("rf_fracttal_ultimas") == "fracttal_ultimas"`.
  - `test_colunas_cifradas`:
    - verdadeiro para `("fornecedores","empresa")`, `("fornecedores","pix")`, `("usinas","contato_email")`,
      `("usinas","responsavel_om")`, `("cotacoes","obs")`, `("perfis","email")`, `("log","quem")`,
      `("fin_cenario","criado_por")`, `("fracttal_rondas","tecnico")`, `("colaboradores","nome")`,
      `("config","valor")` e `("cronograma_publico","dados")`;
    - falso para `("cotacoes","valor")`, `("colaboradores","id")`, `("colaboradores","fornecedor_id")` e
      `("usinas","potencia")`.
  - `test_livros_no_catalogo`:
    - os três em `catalogo.LIVRO_POR_NOME` com `no_banco is False`;
    - `so_cresce` do histórico == as quatro abas de dado;
    - `all(catalogo.aba_segue_a_regra(a) for a in TABELAS)`.

- [ ] **Step 2: Run** `python -m pytest tests/test_zeladoria_tabelas.py -q`. Expected: FAIL (módulo não existe).

- [ ] **Step 3: Implement `tabelas.py`**
  - **A equipe primarizada casa por um regex só,** sem o nome literal:
    `^(tipos_gasto|gastos|orcamento|simulacao_repasse|rota)_[a-z]+(_semanal)?$` → `\1_equipe\2`.
  - **`coluna_cifrada` segue regras, não lista fechada:**
    - `colaboradores` cifra tudo, menos `id` e `*_id`;
    - nomes `{empresa, contato, telefone, pix, email, email_contrato, responsavel_om, tecnico_om, eletricista_om,
      mantenedor_om, tecnico, avaliacao_colaboradores, equipe, pendencias, quem, fornecedor, fornecedor_nome, alias}`;
    - o prefixo `contato_` e o sufixo `_por`;
    - o texto livre `{obs, observacao, motivo, resumo, descricao, comentario, nota}`;
    - os pares `("config","valor")` e `("cronograma_publico","dados")`.
  - **No `catalogo.py`:** cada `Livro` com cadência "sob comando (ferramentas/copiar_zeladoria.py) até a troca" e
    `quem_grava="nexus/zeladoria/copia.py"`. Em `ABAS_FORA_DA_REGRA`, uma entrada por aba, com o motivo "cópia fiel da
    tabela do Radar de Fornecedores (zeladoria); os fatos vêm depois, a partir dela".

- [ ] **Step 4: Run** `python -m pytest tests/test_zeladoria_tabelas.py tests/test_dados_camada.py -q`. Expected: PASS.

- [ ] **Step 5: Ajustar à realidade.** Com o `retrato_do_banco.csv` (quando houver), conferir que toda tabela do esquema
  `radar_fornecedores` passa por `nome_no_nexus`. Listar as colunas que as regras cifram e as que deixam em claro; o
  Levi confere a lista uma vez. Corrigir as regras se preciso.

- [ ] **Step 6: Commit** `feat(zeladoria): o mapa das tabelas do Radar e os três livros no catálogo` (só com o OK).

### Task 2: Da linha do Supabase para a aba do livro, e de volta

**Files:**
- Create: `nexus/zeladoria/guardar.py`
- Test: `tests/test_zeladoria_guardar.py`

**Interfaces:**
- Consumes: `coluna_cifrada` (Task 1); `Cofre`, `CifraErro` (`nexus/cadastro/cifra.py`).
- Produces:
  - `PARTE = 32000`;
  - `para_aba(aba: str, colunas: list[tuple[str, str]], linhas: list[dict], cofre, chave: str) -> tuple[list[str], list[list]]`;
  - `de_aba(aba: str, tipos: dict[str, str], linhas: list[dict], cofre, chave: str) -> list[dict]`;
  - `colunas` e `tipos` usam o tipo do Postgres (`text`, `integer`, `bigint`, `numeric`, `boolean`, `date`,
    `timestamp with time zone`, `json`, `jsonb`, `ARRAY`…).

- [ ] **Step 1: Write the failing tests**
  - `test_ida_e_volta_de_todos_os_tipos`: cada tipo Postgres volta igual, com `None` como `None`, `dict`/`list` para
    `json`/`jsonb`, `bool`, `int` e `float`.
  - `test_coluna_pessoal_vai_cifrada`:
    - na aba, `fornecedores.empresa` começa com `"cf1:"`;
    - `de_aba` devolve o texto original.
  - `test_cifra_presa_a_linha`: a cifra da linha `id="A"`, posta na linha `id="B"`, volta `"(não abre)"`.
  - `test_valor_grande_partido`:
    - um `config.valor` de 70.000 caracteres gera `valor`, `valor__p2` e `valor__p3`, cada um com até `PARTE`;
    - o número de linhas é igual ao da entrada;
    - `de_aba` remonta igual.
  - `test_cifra_que_nao_abre_nao_derruba` (Review Focus 5): com um `Cofre` de outra chave, a coluna vem
    `"(não abre)"`, e `caplog` tem a aba e a coluna, sem o valor.

- [ ] **Step 2: Run** `python -m pytest tests/test_zeladoria_guardar.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement.**
  - **Na ida:** JSON com `json.dumps(ensure_ascii=False, sort_keys=True)`; data e hora em ISO; o resto como texto do
    próprio valor. Cifrar depois de serializar e partir depois de cifrar.
  - **Na volta:** juntar as partes, decifrar e converter pelo `tipos`.

- [ ] **Step 4: Run** de novo. Expected: PASS.

- [ ] **Step 5: Commit** `feat(zeladoria): linha do Radar para a aba do livro, com a cifra e o valor partido`.

### Task 3: A cópia sob comando e a chave do Supabase

**Files:**
- Create: `nexus/zeladoria/copia.py`, `ferramentas/copiar_zeladoria.py`
- Modify:
  - `nexus/auth/chaves.py`: a entrada `NEXUS_ZELADORIA_SUPABASE_PG` em `CHAVES`, com `_conferir_supabase_leitura`;
  - `requirements.txt`: `pg8000==1.31.6`, com o comentário do porquê.
- Test: `tests/test_zeladoria_copia.py`

**Interfaces:**
- Consumes: Tasks 1 e 2; `livros.publicar` e `livros.ler` (`nexus/dados/livros.py`); `chaves.valor(nome, config)`.
- Produces:
  - `ler_supabase(conexao) -> dict[str, dict]`: aba → `{"colunas": [(nome, tipo)], "chave": str, "linhas": [dict]}`.
    Lê o esquema `radar_fornecedores` pelo `information_schema` e pelo `pg_constraint` (a chave primária), mais a view
    `public.rf_fracttal_ultimas`;
  - `copiar(conexao, *, cofre, base: str, token: str, sessao, gravar: bool, agora: datetime) -> dict`: o relatório
    `{"abas": {aba: {"supabase": n, "nexus": n}}, "maior_celula": n, "gravou": bool}`;
  - a aba `atualizacao` de cada livro: 1 linha por aba de dado, com `aba, coluna, tipo_pg, chave, linhas_supabase,
    copiado_em` (e 1 linha por coluna). É de onde a Task 6 tira os `tipos`.

- [ ] **Step 1: Write the failing tests.** Uma conexão falsa, com um cursor que responde ao `information_schema`, às
  chaves e ao `SELECT *` de cada tabela, mais a `ApiPGFalsa` de `tests/pg_falso.py`.
  - `test_copia_os_tres_livros_e_confere`: com `gravar=True`, os três livros gravados, contagem Supabase = Nexus em
    todas as abas, `atualizacao` presente.
  - `test_ensaio_nao_grava`: com `gravar=False`, nada no banco falso e o relatório completo.
  - `test_tabela_desconhecida_nao_grava_nada` (Review Focus 1): uma tabela `tabela_nova` no esquema leva a
    `TabelaDesconhecida` com o nome, e o banco falso fica vazio.
  - `test_chave_com_escrita_e_recusada` (Review Focus 2): `_conferir_supabase_leitura` com uma conexão falsa em que
    `has_table_privilege(..., 'INSERT')` é verdadeiro levanta `chaves.Recusada`, com "só leitura" na mensagem.
  - `test_pessoal_nao_sai_em_claro`: nenhuma célula do banco falso contém o e-mail ou o nome fictício da fixture.

- [ ] **Step 1b (revisão final de 03/11): os valores com nome de gente nos dados.**
  - O clone renomeou valores que estão gravados nos dados: o tipo/escopo das simulações, as chaves do `config`
    (`previsto_decidido_*`, `simulacao_gastos_*`, `simulacao_cenarios_*`) e a origem `planilha_<nome>`.
  - A cópia aplica o MESMO de-para da ferramenta do clone. Ele fica fora do repositório: o caminho do JSON vai na
    variável `NEXUS_ZELADORIA_DE_PARA` do `.env`, e sem ela a cópia para.
  - Vale só em texto com cara de identificador (`^[a-z0-9_:-]*<nome>[a-z0-9_:-]*$`), inclusive DENTRO do JSON (chaves
    e valores), antes de cifrar. Nunca em nome de gente nem e-mail.
  - O relatório conta quantas trocas fez por aba.
  - Teste `test_valores_com_nome_renomeados`: uma linha do `config` com chave `previsto_decidido_fulano` e um JSON com
    `{"escopo": "fulano"}` chegam como `previsto_decidido_equipe` e `{"escopo": "equipe"}`. Um e-mail
    `fulano@exemplo.com` fica igual.
  - Use `tabelas.mapa_de_tabelas(nomes)` (não o `nome_no_nexus` sozinho) para a lista do esquema.
- [ ] **Step 2: Run** `python -m pytest tests/test_zeladoria_copia.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement.**
  - A conexão sai de `pg8000.dbapi.connect`, montada da URL da chave (o pooler do Supabase, em modo sessão).
  - A ferramenta:
    - lê a chave, a base e o token como o resto do Nexus (o padrão de `nexus/campo/decisao_pt.py`, perto da linha 273);
    - aceita `--ensaio` (padrão) e `--gravar`;
    - só grava com `NEXUS_ZELADORIA_COPIA=1` nesta máquina, porque uma máquina grava;
    - imprime a tabela de contagens e a maior célula, nunca linhas.

- [ ] **Step 4: Run** `python -m pytest -q`. Expected: PASS, com a suíte inteira.

- [ ] **Step 5: Medir com o dado real** (depois da etapa 0). Rodar `python ferramentas/copiar_zeladoria.py --ensaio`
  no PC e anotar as contagens, a maior célula e o tempo. Rodar `--gravar` uma vez e anotar quanto tempo cada
  `livros.publicar` leva: é a medida do "Salvo" do desenho.

- [ ] **Step 6: Commit** `feat(zeladoria): cópia do Radar sob comando, só leitura, com a chave conferida`.

### Task 4: O clone limpo no repositório

**Files:**
- Create:
  - `ferramentas/zeladoria_limpar_clone.py`;
  - `nexus/torres/zeladoria/clone/radar.html` (saída do script, versionada);
  - `nexus/torres/zeladoria/clone/ORIGEM.md` (a versão `f0b4cac`, o que o script trocou e como rodar de novo).
- Test: `tests/test_zeladoria_clone.py`

**Interfaces:**
- Produces: `radar.html` que carrega a ponte em vez do supabase-js e tem os marcadores
  `<!--ZELADORIA:CONFIG-->` (no `<head>`, antes de qualquer script) e `<!--ZELADORIA:PONTE-->` (onde estava o
  carregador das CDNs), que a Task 6 substitui ao servir.

- [ ] **Step 1: Write the failing tests** (sobre o arquivo versionado):
  - `test_sem_supabase`: o arquivo não contém `supabase.co`, `sb_publishable`, `cdn.jsdelivr.net/npm/@supabase` nem
    `unpkg.com/@supabase`.
  - `test_marcadores`: cada marcador aparece exatamente uma vez.
  - `test_sem_email`: nenhum `@gridco.com.br` e nenhum e-mail.
  - `test_js_valido`: com `node` presente, todo `<script>` inline passa no `node --check`, como em
    `tests/test_campo_responsaveis.py:1482`.
  - O `tests/test_sem_nomes_no_repositorio.py` existente cobre os nomes.

- [ ] **Step 2: Run** `python -m pytest tests/test_zeladoria_clone.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement o script:**
  `python -I ferramentas/zeladoria_limpar_clone.py --origem <index.html do pacote> --nomes <json fora do repositório> --saida nexus/torres/zeladoria/clone/radar.html`.
  - O json de nomes (`{"Nome": "Papel", "nome": "papel", ...}`) fica em `Downloads\Deploy\radar_2026-10-28\`, nunca no
    repositório. O Levi confere os papéis: aprovador = "Head", segunda alçada = "Analista", supervisor da equipe
    primarizada = "Equipe".
  - Troca por palavra inteira, em identificadores, rótulos e comentários.
  - Tira as duas linhas `SUPABASE_URL`/`SUPABASE_ANON_KEY` e passa a usar `window.supabase.createClient()` sem
    argumentos.
  - Põe os dois marcadores.
  - Os seis nomes `rf_<tabela>_<nome>` viram `rf_<tabela>_equipe` pelo mesmo regex da Task 1.
  - No fim, procura por e-mails e pelos nomes do json; sobrando algum, sai com erro e lista as linhas.

- [ ] **Step 4: Run** o script, depois `python -m pytest tests/test_zeladoria_clone.py tests/test_sem_nomes_no_repositorio.py -q`
  (com o `.env`). Expected: PASS. Conferir à mão as primeiras 30 trocas.

- [ ] **Step 5: Commit** `feat(zeladoria): o clone do Radar (f0b4cac), sem nomes e sem o Supabase`.

### Task 5: A ponte (o `sb` do Nexus)

**Files:**
- Create: `nexus/static/zeladoria/ponte.js`, `tests/zeladoria_ponte_node.js`
- Test: `tests/test_zeladoria_ponte.py` (roda o node; pula sem node)

**Interfaces:**
- Consumes: `window.ZELADORIA = {api: "<raiz>/t/zeladoria/api", somenteLeitura: true, sair: "<raiz da saída>"}`.
- Produces: `window.supabase.createClient()`, que devolve:
  - `from(view)`: `select`, `eq`, `neq`, `order`, `insert`, `update`, `upsert`, `delete`, thenable. O `then` resolve
    `{data, error, count: null, status, statusText}` como o `PostgrestBuilder` da v2.118;
  - `rpc(nome, args)`;
  - `auth`: `onAuthStateChange(cb)` devolve `{data: {subscription: {unsubscribe}}}`; `signOut()` leva ao `sair`;
    `signInWithPassword`, `signUp`, `resetPasswordForEmail` e `updateUser` resolvem `{data: null, error: {message}}`
    ("o login é o do Nexus");
  - `functions.invoke(nome, {body})`;
  - **sem** `storage`: o clone cai sozinho no `fracttal-fotos`.
- **Chamadas HTTP:**
  - `GET {api}/rf/<view>?eq=<col>:<json>&neq=<col>:<json>&order=<col>:asc|desc`, com os filtros repetíveis;
  - `GET {api}/eu`;
  - `POST {api}/funcao/<nome>` com o `body`.
- **Somente leitura:** `insert`, `update`, `upsert`, `delete` e `rpc` resolvem `{data: null, error: {message: "Cópia
  só leitura até a troca: edite no Radar.", code: "SOMENTE_LEITURA"}}`. A exceção é o `upsert` em
  `rf_cronograma_publico`, derivado, que resolve `{data: null, error: null}` sem chamar o servidor.

- [ ] **Step 1: Write the failing node test**, com um `fetch` falso que anota as chamadas:
  - `select('*').eq('usina_chave','X').order('data',{ascending:false})` chama
    `/rf/rf_fracttal_rondas?eq=usina_chave:"X"&order=data:desc` e resolve `data` como array;
  - `Promise.resolve(builder)` funciona;
  - `upsert` em `rf_cotacoes` dá o erro `SOMENTE_LEITURA`;
  - `upsert` em `rf_cronograma_publico` resolve sem `fetch`;
  - `onAuthStateChange` chama `cb('INITIAL_SESSION', {user})` com o que `/eu` devolveu;
  - `fetch` que falha resolve `{data: null, error: {message}}`, sem `throw`, como o supabase-js.

  O teste Python roda `node tests/zeladoria_ponte_node.js nexus/static/zeladoria/ponte.js` e confere o código de saída.
- [ ] **Step 2: Run** `python -m pytest tests/test_zeladoria_ponte.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement `ponte.js`.** Até ~150 linhas, sem dependência.
- [ ] **Step 4: Run** de novo. Expected: PASS.
- [ ] **Step 5: Commit** `feat(zeladoria): a ponte que faz o Radar falar com o Nexus (só leitura)`.

### Task 6: A torre só leitura

**Files:**
- Create:
  - `nexus/zeladoria/leitura.py`;
  - `nexus/torres/zeladoria/__init__.py`;
  - `nexus/torres/zeladoria/templates/zeladoria/tela.html` (estende o layout da casca; só o iframe e o aviso);
  - `nexus/torres/zeladoria/CLAUDE.md`.
- Modify: `CLAUDE.md` (uma linha na tabela de áreas), `nexus/torres/CLAUDE.md` (a torre na tabela).
- Test: `tests/test_zeladoria_torre.py`

**Interfaces:**
- Consumes:
  - Tasks 1, 2, 4 e 5;
  - `livros.ler`;
  - `ronda_fotos.grupos/anexos/tela/miniatura` (`nexus/campo/ronda_fotos.py`);
  - `nota_fracttal.subtarefas_da_os(folio)` (`nexus/campo/nota_fracttal.py`);
  - `session["usuario"]["email"]`, `session["admin"]`.
- Produces, em `leitura.py`:
  - `estado(config) -> dict[str, list[dict]] | None`: as 40 abas decifradas, com cache de 300 s; `None` quando um livro
    não existe ou volta vazio;
  - `linhas(view: str, filtros: list[tuple[str, str, object]], ordem: tuple[str, bool] | None, quem: dict) -> list[dict]`;
  - **o contrato do `/api/eu` é `{"user": {"id", "email"}}`** (o que a ponte e o teste node esperam; revisão final de
    03/11). O papel e o status, o clone lê de `rf_perfis?eq=user_id:...`, então o servidor monta a linha de `perfis`
    do administrador sem linha (HEAD, aprovado) também nessa leitura;
  - `quem_sou(config, usuario: dict | None, admin: bool) -> dict`:
    - devolve `{"id", "email", "papel", "status"}`;
    - casa o e-mail normalizado com `perfis.email`;
    - o administrador sem linha recebe `{"id": "nexus-admin", "papel": "HEAD", "status": "aprovado"}`;
    - sem linha, recebe `{"id": "nexus:" + sha1(email)[:12], "status": "pendente"}`.
- **A torre:**
  - `TORRE = Torre(id="zeladoria", nome="Zeladoria", ordem=<depois de Contratos>, icone="plant", ...)`;
  - 18 `Tela`, uma por aba do `TABS` do Radar, e o de-para `ABAS: dict[str, str]` (id da tela → id da aba do Radar):
    `visao-geral`→`overview`, `farol-contratual`→`analiseServicos`, e as demais com o mesmo id (`usinas`,
    `fornecedores`, `criticidade`, `prioridades`, `rodadas`, `aprovacao`, `andamento`, `cotacoes`, `historico`,
    `planejamento`, `contratos`, `documentacao`, `financeiro`, `danos`, `lixeira`, `usuarios`);
  - rotas: `/<tela>`, `/app`, `/api/rf/<view>`, `/api/eu`, `/api/funcao/<nome>`, `/foto/<folio>/<int:i>`.

- [ ] **Step 1: Write the failing tests:**
  - `test_cada_tela_abre_o_clone`: as 18 rotas dão 200 com um `<iframe` cujo `src` termina em `/t/zeladoria/app?aba=<id do Radar>`.
  - `test_app_injeta_config_e_ponte`: `/app` responde 200 e:
    - contém `window.ZELADORIA` com `somenteLeitura: true`;
    - contém o `<script src=` da ponte (`url_for('static', filename='zeladoria/ponte.js')`);
    - não contém nenhum marcador `<!--ZELADORIA:`.
  - `test_filtros`: `/api/rf/rf_fracttal_rondas?eq=usina_chave:"X"&order=data:desc` devolve só as da usina X, em ordem
    decrescente; `neq` funciona.
  - `test_pendente_so_ve_a_propria_linha` (Review Focus 3): um e-mail fora do `perfis` recebe
    `/api/rf/rf_fornecedores` = `[]` e `/api/rf/rf_perfis` = só a linha dele (vazia).
  - `test_admin_e_head`: com `session["admin"]` sem linha, `/api/eu` devolve papel HEAD aprovado.
  - `test_copia_ausente` (Review Focus 4): com o banco falso vazio, `/t/zeladoria/visao-geral` mostra "A cópia do Radar
    ainda não foi feita" e nenhum iframe.
  - `test_pessoal_decifrado_para_aprovado`: o aprovado vê `empresa` em claro.
  - `test_cifra_quebrada_nao_derruba` (Review Focus 5): a resposta é 200 e o valor vem `"(não abre)"`.
  - `test_fotos`: `/api/funcao/fracttal-fotos` com `{"folio": "123"}` devolve
    `{"folio": "123", "fotos": [{"descricao", "url"}], "checklist": [{"item", "valor"}]}`. As `url` apontam para
    `/t/zeladoria/foto/123/<i>`, e nenhuma tem `https://`. `ronda_fotos` e `nota_fracttal` são falsos por monkeypatch.
  - `test_funcao_desconhecida`: `/api/funcao/fracttal-sync` dá `{"erro": "Cópia só leitura até a troca."}`.

- [ ] **Step 2: Run** `python -m pytest tests/test_zeladoria_torre.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement.**
  - **O `/app`:** lê `radar.html` uma vez por processo e troca os marcadores:
    - o de CONFIG vira o `<script>` com `window.ZELADORIA` e `window.ZELADORIA_ABA` (a aba pedida);
    - o de PONTE vira o `<script src>` da ponte seguido de `iniciarRadarApp()`.

    O clone abre na aba pedida com `ui.tab = window.ZELADORIA_ABA`; essa linha é feita pela Task 4, no ponto em que o
    `ui` nasce.
  - **A barra lateral própria do clone some** por uma classe no `<body>`, posta pelo `/app`. O menu é o do Nexus.
  - **O aviso** "Cópia do Radar: edite no Radar até a troca. Copiado em <data>", com a data da `atualizacao`, fica no
    template da tela, fora do iframe.

- [ ] **Step 4: Run** `python -m pytest -q` (com o `.env`). Expected: PASS, inclusive `test_prefixo.py` e
  `test_toda_rota_nao_publica_exige_login`.

- [ ] **Step 5: Escrever o `nexus/torres/zeladoria/CLAUDE.md`** em até 60 linhas:
  - de onde veio (o pacote e a versão);
  - o congelamento ao fim da etapa 2;
  - os três livros;
  - a ponte e as rotas;
  - o que é só leitura até a troca;
  - como rodar a cópia;
  - como provar.

  Mais a linha na tabela do `CLAUDE.md` da raiz.

- [ ] **Step 6: Commit** `feat(zeladoria): a torre Zeladoria, só leitura, com as 18 abas do Radar`.

### Task 7: Prova na cópia de prova

**Files:** nenhum novo (só correções que a prova achar).

- [ ] **Step 1:** Com a cópia gravada (Task 3, Step 5), subir
  `python ferramentas/subir_copia_de_prova.py --porta 5170 --plataforma ""` e entrar pela senha de administrador.
- [ ] **Step 2:** Abrir as 18 telas no navegador do app, em desktop e em 375 px.
  - Conferir que cada uma carrega sem erro no console.
  - Comparar com o Radar no ar, no mesmo dia: os totais da Visão Geral, o Mês a mês do Financeiro e o Farol
    Contratual.
  - Abrir as fotos de uma ronda.
- [ ] **Step 3:** Anotar no `CLAUDE.md` da torre a primeira medida: contagens, tempo da cópia e tempo de abertura da
  Visão Geral. Mostrar ao Levi, só na conversa e nunca em arquivo, quem está aprovado no `perfis`, para ele conferir
  antes da troca quem ainda não entra no Nexus.
- [ ] **Step 4:** Mostrar ao Levi. Com o OK dele, combinar com o dono do Radar o congelamento. Depois disso, a etapa 3
  começa.
