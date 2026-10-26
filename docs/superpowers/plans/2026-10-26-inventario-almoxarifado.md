# Inventário do almoxarifado no PCM — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** o PCM recebe no Nexus a contagem cega que a turma faz no App, revisa, aprova e grava o saldo no Fracttal com o
próprio login, com régua de mínimo e máximo, curadoria e auditoria.

**Architecture:** o App publica as contagens num livro do banco (contrato em `nexus/dados/almoxarifado.py`). O Nexus lê,
calcula as situações (`nexus/pcm/inventario/contas.py`, puro), mostra as abas no PCM → Almoxarifado e grava no Fracttal
por um adaptador único (`nexus/pcm/inventario/estoque.py`) dentro da sessão do Fracttal de quem aprovou, num trabalho em
segundo plano que retoma sem duplicar. Cada evento vai ao livro `nexus_almoxarifado_inventario`, que só cresce.

**Tech Stack:** Python 3 / Flask / Jinja; a API JSON-RPC do Fracttal pelo `api.py` do OS Creator (`_rpc_call`,
`os_sessao.contexto`); a API de planilhas `db_performace` (`livros.py`, `visao.py`); pytest com `tests/pg_falso.py`.

**Spec:** `docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md` (aprovado pelo Levi em 26/10/2026).

## Global Constraints

- pt-BR em tudo; comentário diz o porquê, com o caso real. Repositório PÚBLICO: nenhum nome de colega (os documentos do
  Spare Parts citam pessoas: aqui, só o papel), e-mail, segredo nem login do Fracttal em arquivo.
- Cor só por token do `nexus.css`; endereço nunca a partir da raiz (`{{ raiz }}`, `url_for`, `nexusRota()`); sem emoji.
- Só quem `pcm.telas.pode_programar()` (administrador ou setor PCM) revisa, grava, decide curadoria e régua.
- Toda gravação no Fracttal vai **na sessão do Fracttal de quem aprovou** (`ponte.sessao_do_os`), nunca numa conta de
  serviço; quem entrou pela senha de administrador não grava. O login fica só na memória.
- Ritmo no Fracttal: ~1 pedido por segundo (o limite de 200/min é da empresa); 429 → espera 62 s e tenta uma vez; de
  novo, a gravação para e fica para "Continuar".
- O contado **substitui** o saldo (nunca soma ao do Fracttal); **em branco nunca é zero**; o movimento é **ajuste de
  inventário**, nunca consumo nem devolução, com a referência `INVENTARIO-<contagem>`.
- Mostrar antes de gravar, reler depois, registrar: a peça só fica "gravada" quando a releitura confirma o saldo.
- Texto livre do PCM (motivo) só cifrado (`dados_cifrados`, o `Cofre` do cadastro), como nas atribuições.
- Gravação de prova no Fracttal **só no almoxarifado de teste** (Task 0), e cada uma com o OK do Levi.
- Commit no ramo `inventario-almox` a cada tarefa; push na `main` e deploy do App só com o OK do Levi.

## Review Focus

1. **Duas pessoas do PCM gravam a mesma contagem (ou o mesmo almoxarifado) ao mesmo tempo:** a 2ª é recusada com "já
   tem uma gravação em andamento neste almoxarifado" (Task 7).
2. **A peça contada nunca foi ligada ao almoxarifado no Fracttal** (não vem na leitura do saldo): saldo do sistema 0,
   ligada antes do ajuste (Task 3 e 7).
3. **O livro do App devolve tudo como texto** ("3", "3,0", "", "None"): "" e "None" são "não contei"; "3,0" é 3 (Task 3).
4. **O login do Fracttal expira no meio da gravação** (`SessionExpired`): a gravação para como `parada: o login do
   Fracttal expirou`, e quem aprovou continua depois de entrar de novo (Task 7).
5. **A leitura do almoxarifado traz a peça com saldo vazio**: saldo do sistema 0 para a conta, mas a peça aparece como
   "saldo não informado" na revisão, e o zerar não vale para ela (Task 3).

---

## Arquivos

| Arquivo | O que faz |
|---|---|
| `docs/superpowers/specs/2026-10-26-inventario-almoxarifado-passo0.md` (novo) | O resultado do passo 0: métodos, parâmetros e respostas reais |
| `nexus/dados/almoxarifado.py` | + o contrato do livro das contagens e os almoxarifados de teste |
| `nexus/dados/fato_inventario.py` (novo) | Os cabeçalhos e a gravação do livro `nexus_almoxarifado_inventario` |
| `nexus/dados/catalogo.py`, `nexus/dados/explica.py` | A fonte, o livro e os fatos novos |
| `nexus/pcm/inventario/__init__.py` (novo) | `registrar(bp)` das abas |
| `nexus/pcm/inventario/estoque.py` (novo) | O adaptador do Fracttal (a única porta de leitura e gravação de estoque) |
| `nexus/pcm/inventario/contas.py` (novo) | Situações, contado efetivo, substituição, conflitos (puro) |
| `nexus/pcm/inventario/leitura.py` (novo) | As contagens do App com o estado de cada uma |
| `nexus/pcm/inventario/gravacao.py` (novo) | O trabalho de gravação em segundo plano |
| `nexus/pcm/inventario/regua.py` (novo) | A sugestão da régua e as decisões |
| `nexus/pcm/inventario/curadoria.py` (novo) | As pendências e as decisões |
| `nexus/templates/pcm/inventario*.html` (novos), `nexus/static/pcm.css` | As abas |
| `nexus/pcm/almoxarifado.py`, `nexus/templates/pcm/almoxarifado.html`, `nexus/torres/pcm/__init__.py` | A ligação das abas novas e o filtro do almoxarifado de teste |
| `tests/estoque_falso.py` (novo) | O Fracttal de mentira do estoque |
| `tests/test_pcm_inventario_*.py` (novos) | Provas |

---

### Task 0: Passo 0 — a API do Fracttal confirmada e o almoxarifado de teste

Sem código de produto. Precisa do Levi: ele entra no Fracttal com o login dele, no navegador do app, e dá o OK de cada
gravação de prova.

**Files:** Create `docs/superpowers/specs/2026-10-26-inventario-almoxarifado-passo0.md`.

- [ ] **Step 1:** Pedir ao Levi o OK, numa mensagem só, para as gravações de prova, todas debaixo do cliente de teste do
  Fracttal ("teste - pa"): criar o almoxarifado `TESTE-INVENTARIO`; criar a peça `SP-TST-001` ("Peça de teste do
  inventário", UNIDADE); ligar a peça ao almoxarifado com mínimo 1 e máximo 4; uma entrada de ajuste de 3; uma saída de
  ajuste de 1; se existir, um ajuste de saldo absoluto para 5; no fim, desativar a peça. Sem o OK, parar aqui.
- [ ] **Step 2:** Com o Levi logado em app.fracttal.com no navegador do app, abrir Almoxarifados → um almoxarifado de
  usina → Estoque, e ler as requisições de rede (`read_network_requests`, filtro `rpc`): o método e os parâmetros da
  lista dos almoxarifados, do estoque de um almoxarifado (saldo, mínimo, máximo) e, se a tela tiver, dos movimentos do
  almoxarifado por data (o kardex). Só leitura.
- [ ] **Step 3:** No almoxarifado de teste, fazer cada gravação do Step 1 pela tela do Fracttal e ler a requisição de
  cada uma: o método, o corpo mínimo, a resposta (o id do movimento), o tipo de movimento que a tela usa para "ajuste".
- [ ] **Step 4:** Escrever o `...-passo0.md`: para cada operação do adaptador (Task 2), o método RPC, os parâmetros
  obrigatórios, os campos da resposta usados e um exemplo de resposta **sem nome de pessoa** (trocar por "PESSOA");
  se há ajuste absoluto (sim/não); se há leitura de movimentos por data (sim/não); o id do almoxarifado de teste e o da
  peça de teste. **Se não houver como gravar estoque pela RPC, parar e avisar o Levi** (o desenho depende disso).
- [ ] **Step 5:** Commit `docs(almox): o resultado do passo 0 do inventário (a API do estoque do Fracttal)`.

### Task 1: O contrato das contagens e o almoxarifado de teste

**Files:** Modify `nexus/dados/almoxarifado.py`, `nexus/dados/catalogo.py`, `nexus/dados/explica.py`,
`nexus/pcm/almoxarifado.py`, `nexus/dados/carga.py`; Test `tests/test_pcm_inventario_contrato.py`.

**Interfaces — Produces:**
- `almoxarifado.LIVRO_CONTAGENS = "almoxarifado_contagens_app_campo"`, `ABA_CONTAGENS = "Contagens"`,
  `COLUNAS_CONTAGENS = ("ID da contagem", "Enviada em", "Contada em", "ID do almoxarifado", "Usina", "Tipo",
  "ID do item", "Código", "Contado", "Identificado como", "Descrição", "Foto", "Contou (HMAC)")`,
  `TIPOS_CONTAGEM = ("item", "identificar", "fora_do_catalogo")`.
- `almoxarifado.contado(v) -> float | None` ("" e "None" → None; "3,0" → 3.0; nunca 0 para vazio).
- `almoxarifado.ids_de_teste(config) -> set[str]` (da `NEXUS_ALMOX_TESTE_IDS`, ids separados por vírgula).
- Fato `contagem_inventario` (estado `origem`, área `pcm`, fonte o livro acima, `janela_origem` "90 dias (App)").

- [ ] **Step 1: Tests:** `test_contrato_das_contagens` (a tupla exata acima; "Contou (HMAC)" e nenhuma coluna com
  "e-mail"); `test_contado_vazio_nao_e_zero` (`contado("") is None`, `contado("None") is None`, `contado("0") == 0.0`,
  `contado("3,0") == 3.0`); `test_almoxarifado_de_teste_fora_das_telas` (com `NEXUS_ALMOX_TESTE_IDS="999"`, a linha do
  almoxarifado 999 do livro Saldo não entra no `pcm.almoxarifado.montar()` nem na foto da `carga.gerar_almoxarifado`);
  `test_contagem_no_catalogo` (o fato existe, com `RESUMO`/`PARA_QUE`).
- [ ] **Step 2:** Rodar → FAIL.
- [ ] **Step 3:** Implementar; `NEXUS_ALMOX_TESTE_IDS` em `config.OPCIONAIS` e no `.env.example`.
- [ ] **Step 4:** `python -m pytest -q tests/test_pcm_inventario_contrato.py tests/test_dados_almoxarifado.py tests/test_pcm_almoxarifado.py` → PASS.
- [ ] **Step 5:** Commit; e mandar o contrato (a tupla, os tipos, a regra "em branco não é zero" e "uma linha por
  específico no genérico") à sessão "App de campo", sem pedir deploy.

### Task 2: O adaptador do estoque e o Fracttal de mentira

**Files:** Create `nexus/pcm/inventario/__init__.py`, `nexus/pcm/inventario/estoque.py`, `tests/estoque_falso.py`;
Test `tests/test_pcm_inventario_estoque.py`.

**Interfaces — Produces** (em `estoque.py`; os métodos RPC e os campos vêm do `...-passo0.md`):
- `class Limite(Exception)` (429), `class SemLogin(Exception)` (login recusado ou expirado).
- `class Estoque` (o contrato que a `EstoqueFracttal` e a `EstoqueFalso` cumprem):
  - `ler(id_almox: str) -> dict[str, dict]` — `{id_item: {"saldo": float | None, "minimo": float | None,
    "maximo": float | None}}` das peças ligadas ao almoxarifado;
  - `ligar(id_almox: str, id_item: str) -> None`;
  - `ajustar(id_almox: str, id_item: str, de: float, para: float, referencia: str) -> str` (o id do movimento; pelo
    ajuste absoluto se o passo 0 achou, senão entrada ou saída de ajuste pelo Δ);
  - `achar_movimento(id_almox: str, referencia: str) -> str | None`;
  - `mexidas_desde(id_almox: str, desde_iso: str) -> set[str] | None` (None = o Fracttal não diz);
  - `definir_regua(id_almox: str, id_item: str, minimo: float | None, maximo: float | None) -> None`;
  - `criar_peca(codigo: str, nome: str, unidade: str) -> str` (o id do item);
  - `codigos(sigla: str) -> list[str]` (os códigos `SP-<sigla>-NNN` que existem).
- `estoque_da_sessao(app) -> EstoqueFracttal` (a sessão do Fracttal do pedido, `ponte.sessao_do_os`; sem login →
  `SemLogin`). A `EstoqueFracttal` guarda o JWT e o e-mail só na memória e roda cada chamada dentro de
  `os_sessao.contexto(jwt, email)`, no ritmo de ~1 pedido/s.
- `tests/estoque_falso.py`: `EstoqueFalso(saldos: dict, *, perder_resposta: set = (), limite_em: int | None = None,
  expirar_em: int | None = None)` — em memória; `perder_resposta`: a gravação acontece e a chamada levanta (a resposta
  "se perdeu"); `limite_em`/`expirar_em`: a N-ésima chamada levanta `Limite`/`SemLogin`; guarda `.movimentos`.

- [ ] **Step 1: Tests** (a `EstoqueFracttal` com o `_rpc_call` trocado por um gravador que devolve as respostas do
  passo 0): `test_ler_monta_saldo_minimo_maximo`; `test_ajustar_usa_o_movimento_de_ajuste_com_a_referencia` (o método e
  o tipo do passo 0, a referência `INVENTARIO-c1`); `test_429_vira_limite`; `test_login_recusado_vira_sem_login`;
  `test_ritmo_de_um_pedido_por_segundo` (o relógio de mentira: 3 chamadas ≥ 2 s); e o falso:
  `test_falso_perde_a_resposta_mas_grava`.
- [ ] **Step 2:** Rodar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** Rodar → PASS.
- [ ] **Step 5:** Commit.

### Task 3: As contas (situações, contado efetivo, substituição, conflitos)

**Files:** Create `nexus/pcm/inventario/contas.py`; Test `tests/test_pcm_inventario_contas.py`.

**Interfaces — Produces:**
- `SITUACOES = ("para_cima", "para_baixo", "zerar", "sem_alteracao", "nao_tocada", "curadoria")`; `MEXEM =
  ("para_cima", "para_baixo", "zerar")`.
- `situacao(sistema: float | None, contado: float | None) -> str`.
- `contado_efetivo(linhas: list[dict], curadoria: dict[str, dict]) -> dict[str, float | None]` — `linhas`: as da
  contagem (o livro do App); `curadoria`: `{chave_da_linha: {"decisao": "e_a_peca"|"cadastrar"|"descartar"|"confirmar",
  "id_item": str}}`. Regras: o item vale o "Contado" da linha dele; "é a peça X" e o "cadastrar" somam as unidades
  achadas ao contado de X (X em branco vira só as achadas); o genérico identificado e confirmado tira as unidades do
  genérico e soma ao específico.
- `itens_do_lote(contagem: list[dict], sistema: dict[str, dict], curadoria: dict, revisao: dict) -> list[dict]` — uma
  entrada por peça: `id_item`, `codigo`, `sistema`, `contado`, `contado_campo`, `situacao`, `ligada` (bool),
  `corrigido` (bool), `tirada` (bool); `revisao`: `{"tiradas": {id_item: motivo}, "corrigidos": {id_item: valor}}`.
- `substituidas(contagens: list[dict], gravadas: set[str]) -> set[str]` (por almoxarifado, vale a mais nova pelo
  "Contada em"; as mais velhas não gravadas são substituídas).
- `aprovavel(contada_em: str, agora: datetime, dias: int = 7) -> bool`.

- [ ] **Step 1: Tests** (valores exatos): `test_situacao` — (4, 6) para_cima; (4, 2) para_baixo; (4, 0) zerar;
  (0, 0) sem_alteracao; (4, None) nao_tocada; (None, 3) para_cima com `sistema` None tratado como 0;
  `test_e_a_peca_x_soma_na_mesma_contagem` — X contada 3 + 2 achadas = 5; X em branco + 2 achadas = 2;
  `test_generico_identificado_sai_do_generico` — genérico 4, as 4 identificadas como Y: Y +4 e o genérico 0 (zerar);
  `test_texto_da_api` — "3,0", "" e "None" (o foco 3); `test_peca_nao_ligada` — a peça fora da leitura entra com
  `sistema` 0 e `ligada` False (o foco 2); `test_saldo_vazio_nao_zera` — sistema None e contado 0: situação
  `sem_alteracao`, não `zerar` (o foco 5); `test_corrigido_e_tirada`; `test_a_mais_nova_substitui`;
  `test_aprovavel_ate_7_dias`.
- [ ] **Step 2:** Rodar → FAIL.
- [ ] **Step 3:** Implementar (puro: nada de rede).
- [ ] **Step 4:** Rodar → PASS.
- [ ] **Step 5:** Commit.

### Task 4: O livro do inventário no Nexus

**Files:** Create `nexus/dados/fato_inventario.py`; Modify `nexus/dados/catalogo.py`, `nexus/dados/explica.py`,
`nexus/config.py`, `.env.example`; Test `tests/test_pcm_inventario_livro.py`.

**Interfaces — Produces:**
- `LIVRO = "nexus_almoxarifado_inventario"`; abas `fato_evento_inventario`, `fato_regua_minimo`,
  `fato_curadoria_inventario`, `qualidade`, `atualizacao`; `so_cresce=True` nas três de fato.
- `CAB_EVENTO = ["evento_id", "quando", "data_id", "contagem_id", "tipo", "id_almoxarifado", "usina_id", "id_item",
  "codigo", "de_qtd", "para_qtd", "contado_qtd", "movimento_fracttal", "situacao", "lote", "pessoa_id",
  "pessoa_hmac", "dados_cifrados"]`; `TIPOS_EVENTO = ("contagem_recebida", "aprovada", "peca_gravada", "conflito",
  "erro", "peca_tirada", "recontagem_pedida", "numero_corrigido", "substituida", "curadoria", "regua_gravada")`.
- `CAB_REGUA = ["decidida_em", "data_id", "id_almoxarifado", "usina_id", "id_item", "codigo", "sugestao_min_qtd",
  "sugestao_max_qtd", "recomendado_min_qtd", "recomendado_max_qtd", "acordado_min_qtd", "acordado_max_qtd",
  "gravado_fracttal", "pessoa_id", "pessoa_hmac"]`.
- `CAB_CURADORIA = ["decidida_em", "contagem_id", "chave_linha", "decisao", "id_item", "codigo_criado", "pessoa_id",
  "pessoa_hmac", "dados_cifrados"]`.
- `acrescentar(cfg, aba: str, linhas: list[dict]) -> None` — relê o livro inteiro, acrescenta, grava todas as abas
  (`livros.publicar`); `NEXUS_ALMOX_INVENTARIO_ARQUIVO` troca o banco por um arquivo (a cópia de prova e os testes,
  como o `atribuicoes._ler_cru`/`_gravar_cru`); leitura que falha → `Recusada` (a exceção deste módulo, que as
  Tasks 6 a 9 também usam), nada gravado.
- `ler(cfg) -> dict[str, list[dict]]` (as três abas, cópia de 2 min).
- Os três fatos no catálogo (estado `conformado`: o Nexus é a fonte), com `RESUMO`/`PARA_QUE`; o livro em `LIVROS`; a
  qualidade dele no `dados.telas._ultima_qualidade`.

- [ ] **Step 1: Tests:** `test_acrescentar_guarda_o_que_havia` (com o `pg_falso` e `como_texto=True`);
  `test_leitura_que_falha_nao_grava`; `test_arquivo_local`; `test_nada_de_nome_no_livro` (os CABs não têm "nome",
  "email", "motivo"; o motivo só no `dados_cifrados`); `test_inventario_no_catalogo` (o `test_dados_camada` também passa
  com os CABs registrados).
- [ ] **Step 2:** Rodar → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** `python -m pytest -q tests/test_pcm_inventario_livro.py tests/test_dados_camada.py tests/test_dados_organograma.py` → PASS.
- [ ] **Step 5:** Commit.

### Task 5: As contagens e o estado de cada uma

**Files:** Create `nexus/pcm/inventario/leitura.py`; Test `tests/test_pcm_inventario_leitura.py`.

**Interfaces — Consumes:** Task 1 (o contrato, `ids_de_teste`), Task 3 (`substituidas`, `aprovavel`), Task 4 (`ler`).
**Produces:** `contagens(cfg) -> list[dict]` — uma por contagem: `contagem_id`, `id_almox`, `usina`, `usina_id`,
`contada_em`, `enviada_em`, `linhas` (as do livro do App), `n_contadas`, `n_em_branco`, `n_curadoria`, `estado` em
`ESTADOS = ("nova", "revisada", "recontagem_pedida", "substituida", "gravando", "gravada", "gravada_com_conflitos")`,
`aprovavel` (bool); ordenadas da mais nova para a mais velha; sem o almoxarifado de teste; pela cópia de 5 min do
`visao._ler`.

- [ ] **Step 1: Tests:** `test_estados_pelos_eventos` (sem evento: nova; `recontagem_pedida`; com `peca_gravada` de
  todas: gravada; com `conflito`: gravada_com_conflitos); `test_a_mais_nova_substitui_a_velha_nao_gravada`;
  `test_livro_do_app_que_nao_existe` (lista vazia e `livro_existe` falso); `test_contagem_de_8_dias_nao_aprova`.
- [ ] **Step 2:** Rodar → FAIL. **Step 3:** Implementar. **Step 4:** Rodar → PASS. **Step 5:** Commit.

### Task 6: A aba Inventário (lista, revisão e aprovação)

**Files:** Create `nexus/templates/pcm/inventario.html`,
`nexus/templates/pcm/inventario_contagem.html`; Modify `nexus/pcm/inventario/__init__.py` (`registrar`), `nexus/pcm/almoxarifado.py`, `nexus/templates/pcm/almoxarifado.html`,
`nexus/static/pcm.css`, `nexus/torres/pcm/__init__.py`; Test `tests/test_pcm_inventario_telas.py`.

**Interfaces — Consumes:** Tasks 2–5. **Produces** (rotas no `bp` da torre PCM, todas debaixo de `/pecas/inventario`):
- `GET /pecas/inventario` — a lista (Task 5).
- `GET /pecas/inventario/<contagem_id>` — Sistema × Contado × Δ × Situação; o "Sistema" lido na hora pelo
  `estoque_da_sessao(app).ler(id_almox)`; sem login do Fracttal, a tela mostra o contado e diz "entre pelo Fracttal para
  ver o saldo do sistema e gravar"; os seis grupos da confirmação (o zerar aberto e destacado).
- `POST /pecas/inventario/<contagem_id>/revisar` — JSON `{"acao": "tirar"|"corrigir"|"recontagem", "id_item"?,
  "valor"?, "motivo"}`; só `pode_programar()`; grava o evento (Task 4) com o motivo cifrado; 403 para quem não pode.
- A aba "Inventário" no `almoxarifado.html`, ao lado das 5 que já existem.

- [ ] **Step 1: Tests:** `test_lista_e_contagem` (com o `banco` do Campo, o livro de contagens e um `EstoqueFalso` posto
  no lugar do `estoque_da_sessao`: os seis grupos com os números certos); `test_sem_login_do_fracttal_nao_grava_nem_le`;
  `test_revisar_tirar_corrigir_recontagem` (os eventos, o motivo só cifrado); `test_so_o_setor_pcm_revisa` (403 para
  outro setor, como o `test_pcm_publicar`); `test_sem_cor_fora_de_token`.
- [ ] **Step 2:** Rodar → FAIL. **Step 3:** Implementar. **Step 4:** Rodar → PASS. **Step 5:** Commit.

### Task 7: A gravação em segundo plano

**Files:** Create `nexus/pcm/inventario/gravacao.py`; Modify `nexus/pcm/inventario/__init__.py`,
`nexus/templates/pcm/inventario_contagem.html`; Test `tests/test_pcm_inventario_gravacao.py`.

**Interfaces — Consumes:** Task 2 (`Estoque`, `Limite`, `SemLogin`), Task 3 (`itens_do_lote`, `MEXEM`), Task 4
(`acrescentar`). **Produces:**
- `iniciar(cfg, contagem: dict, itens: list[dict], estoque: Estoque, aprovador: dict) -> dict` — recusa
  (`fato_inventario.Recusada`) se já houver gravação em andamento no mesmo almoxarifado; grava o evento `aprovada`; roda numa thread.
- `continuar(cfg, contagem_id: str, estoque: Estoque, pessoa: dict) -> dict` — só se `pessoa["email"]` for o do
  aprovador; senão `Recusada("só quem aprovou continua")`.
- `estado(cfg, contagem_id: str) -> dict` — `{"estado": "gravando"|"parada"|"concluida", "motivo", "feitas",
  "total", "conflitos", "erros", "lote"}`, de `<NEXUS_DADOS>/almox_inventario/<contagem_id>.json` (o controle: o ponto
  de retomada e a peça "sem resposta"; nunca o login).
- Rotas: `POST /pecas/inventario/<id>/gravar`, `POST /pecas/inventario/<id>/continuar`,
  `GET /pecas/inventario/<id>/estado.json`; a tela acompanha o progresso a cada 3 s.
- O algoritmo, por lote de 50 (só os itens com situação em `MEXEM`, não tirados):

```
saldos = estoque.ler(id_almox)                               # 1 leitura por lote
mexidas = estoque.mexidas_desde(id_almox, contada_em)        # None: usa as peças lançadas pelo App depois da contagem
para cada item:
    se a peça é a "sem resposta" do controle:                 # a gravação parou no meio desta peça
        mov = estoque.achar_movimento(id_almox, ref)          # achou: já gravou, só confirma; não achou: grava
    se saldos[item].saldo != item.sistema ou item em mexidas: evento conflito; segue
    se não item.ligada: estoque.ligar(id_almox, item)
    controle.sem_resposta = item; salvar controle
    mov = estoque.ajustar(id_almox, item, de=item.sistema, para=item.contado, referencia=f"INVENTARIO-{contagem_id}")
    controle.feitas += item; controle.sem_resposta = None; salvar controle
no fim: estoque.ler(id_almox) de novo; saldo == contado → evento peca_gravada (com o mov); senão evento erro
Limite: espera 62 s e tenta 1 vez; de novo → parada ("limite do Fracttal"). SemLogin → parada ("o login do Fracttal expirou").
```

- [ ] **Step 1: Tests** (com o `EstoqueFalso` e um relógio de mentira, sem esperar de verdade):
  `test_grava_e_confirma` (os movimentos e os eventos `peca_gravada`); `test_saldo_mudou_vira_conflito`;
  `test_mexida_depois_da_contagem_vira_conflito`; `test_resposta_perdida_nao_duplica` (`perder_resposta`, a parada e o
  `continuar`: um movimento só); `test_so_quem_aprovou_continua`; `test_login_expirado_para_e_continua` (o foco 4);
  `test_duas_gravacoes_no_mesmo_almoxarifado` (o foco 1); `test_limite_espera_e_para`; `test_nunca_guarda_o_login`
  (o JSON de controle não tem "jwt" nem "token").
- [ ] **Step 2:** Rodar → FAIL. **Step 3:** Implementar. **Step 4:** Rodar → PASS. **Step 5:** Commit.

### Task 8: A régua de mínimo e máximo

**Files:** Create `nexus/pcm/inventario/regua.py`, `nexus/templates/pcm/inventario_regua.html`; Modify
`nexus/pcm/inventario/__init__.py`; Test `tests/test_pcm_inventario_regua.py`.

**Interfaces — Produces:**
- `sugestao(saldo: float | None, avariada: bool, decimal: bool) -> tuple[float | None, float | None]` — a régua de 14/10:
  mínimo = 20% do saldo, máximo = 2× o saldo; avariada: sem mínimo (None) e máximo 3×; unidade inteira: o mínimo
  arredonda para cima (decisão do construtor: com saldo 3, mínimo 1, não 0); unidade decimal (METRO, MASSA): duas casas.
  Saldo None ou 0: (0, 0).
- `quadro(cfg, id_almox: str) -> list[dict]` — por peça: saldo, sugestão, o recomendado e o acordado vigentes (a última
  decisão do `fato_regua_minimo`).
- `decidir(cfg, id_almox, id_item, *, recomendado=(min, max) | None, acordado=(min, max) | None, pessoa) -> None`.
- `gravar_acordado(cfg, id_almox, id_item, estoque: Estoque, pessoa) -> str` — só o acordado vai ao Fracttal
  (`estoque.definir_regua`), relê e grava o evento `regua_gravada`.
- Rotas: `GET /pecas/inventario/regua?almox=`, `POST .../regua/decidir`, `POST .../regua/gravar` (só `pode_programar`).

- [ ] **Step 1: Tests:** `test_sugestao` — (10, False, False) → (2, 20); (3, False, False) → (1, 6); (0, …) → (0, 0);
  (4, True, False) → (None, 12); (12.5, False, True) → (2.5, 25.0); `test_so_o_acordado_vai_ao_fracttal` (decidir o
  recomendado não chama o `EstoqueFalso`; gravar o acordado chama `definir_regua` com o mínimo e o máximo acordados);
  `test_sem_acordado_nao_grava`.
- [ ] **Step 2:** Rodar → FAIL. **Step 3:** Implementar. **Step 4:** Rodar → PASS. **Step 5:** Commit.

### Task 9: A curadoria

**Files:** Create `nexus/pcm/inventario/curadoria.py`, `nexus/templates/pcm/inventario_curadoria.html`; Modify
`nexus/pcm/inventario/__init__.py`; Test `tests/test_pcm_inventario_curadoria.py`.

**Interfaces — Consumes:** Task 3 (`contado_efetivo` lê as decisões), Task 4. **Produces:**
- `SIGLAS = ("PEL", "PME", "CAB", "SEN", "CTR", "COM", "INS", "ARM", "EAX", "HSE", "CSM", "GER")` (+ `TST` só no
  almoxarifado de teste).
- `pendencias(cfg) -> list[dict]` — as linhas `fora_do_catalogo` e `identificar` das contagens não gravadas, com a foto
  (pela rota de fotos do App, como `nexus/hseq/fotos.py`).
- `proximo_codigo(codigos: list[str], sigla: str) -> str` — `SP-<sigla>-NNN`, o próximo número livre (três dígitos).
- `decidir(cfg, contagem_id, chave_linha, decisao, *, id_item=None, sigla=None, nome=None, unidade=None, motivo=None,
  estoque: Estoque | None = None, pessoa) -> dict` — `cadastrar` cria a peça (`estoque.criar_peca`) e grava a decisão
  com o código criado; `e_a_peca` e `confirmar` gravam a decisão; `descartar` grava com o motivo cifrado. A quantidade
  entra no lote pela `contado_efetivo` (a peça nova é ligada e ajustada na gravação da contagem).
- Rotas: `GET /pecas/inventario/curadoria`, `POST .../curadoria/decidir` (só `pode_programar`); a tela lembra que grupo,
  criticidade e Curva ABC se completam na tela do Fracttal.

- [ ] **Step 1: Tests:** `test_proximo_codigo` (["SP-CAB-001", "SP-CAB-012"] → "SP-CAB-013"; nenhum → "SP-CAB-001");
  `test_cadastrar_cria_e_registra`; `test_e_a_peca_entra_no_lote` (a contagem com 2 achadas que são X: o lote de X
  com 5, a Task 3); `test_descartar_motivo_cifrado`; `test_so_o_setor_pcm_decide`.
- [ ] **Step 2:** Rodar → FAIL. **Step 3:** Implementar. **Step 4:** Rodar → PASS. **Step 5:** Commit.

### Task 10: Auditoria, documentação, prova no navegador e revisão

**Files:** Create `nexus/templates/pcm/inventario_auditoria.html`; Modify `nexus/pcm/inventario/__init__.py`,
`nexus/pcm/CLAUDE.md`, `nexus/dados/CLAUDE.md`, `nexus/torres/CLAUDE.md`, `CLAUDE.md`; Test
`tests/test_pcm_inventario_telas.py`.

- [ ] **Step 1:** A aba Auditoria (`GET /pecas/inventario/auditoria`): os eventos do `fato_evento_inventario`, filtro por
  tipo e busca (o `filtro-local.js`), sem o motivo (é cifrado). Test `test_auditoria_lista_e_filtra` → FAIL, implementar,
  PASS.
- [ ] **Step 2:** Os `.md`: a seção "Inventário" no `nexus/pcm/CLAUDE.md` (o fluxo, as regras, a chave de teste, como
  provar), a linha do livro no `nexus/dados/CLAUDE.md`, a linha da torre e a do PCM no `CLAUDE.md` da raiz.
- [ ] **Step 3:** A prova no navegador numa cópia de prova com o `EstoqueFalso` (script fora do repositório): lista,
  contagem, revisão, gravação com um conflito e uma retomada, régua, curadoria e auditoria; desktop e 375 px, escuro e
  claro.
- [ ] **Step 4:** A prova no Fracttal de verdade, **só no almoxarifado de teste** e com o OK do Levi: uma contagem de
  mentira da peça `SP-TST-001`, gravada pelo Nexus com o login dele, relida no Fracttal; a régua acordada gravada.
- [ ] **Step 5:** A suíte inteira (com o `.env` copiado à worktree) → 0 falhas; a revisão final do ramo pelo revisor
  mais capaz; cada achado Crítico ou Importante com teste antes; commit; pedir ao Levi o OK para subir.

---

## Fora deste plano

- A tela da contagem no App (a sessão do App constrói pelo contrato da Task 1; o deploy é com o OK do Levi).
- O piloto num almoxarifado de usina que o PCM escolher (depois do deploy dos dois lados).
- Tornar a varredura do App mais barata com a leitura do estoque por almoxarifado (12 chamadas no lugar de 574): é do
  App, depois do passo 0.
