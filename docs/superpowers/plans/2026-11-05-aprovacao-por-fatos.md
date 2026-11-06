# Aprovação de OS por fatos — plano de construção

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a Aprovação de OS do Campo · App vira um quadro Pronta / Em dúvida / Não OK pelas regras de fatos, com o
Aprovar no cartão e em lote.

**Architecture:** regras puras em `nexus/campo/prefiltro.py`; a leitura dos anexos (um GET por OS no Fracttal, as fotos
no S3) num laço de fundo em `nexus/campo/prefiltro_fundo.py`, com cópia em memória e em disco, disparado depois de cada
releitura da fila (`aprovacao._reler`) e no boot; a rota `/t/campo/aprovacao` monta o quadro sobre a conta pronta da
fila; o Aprovar é a rota do OS Creator que o Painel já usa (`POST /os/api/os/<id>/concluir`).

**Tech Stack:** Flask, Jinja, JS sem biblioteca, Pillow, pytest.

**Spec:** `docs/superpowers/specs/2026-11-05-aprovacao-por-fatos-design.md`

## Global Constraints

- pt-BR em tudo, comentário explica o porquê; sem emoji; cor só por token do `nexus.css` (nada de `#hex`/`rgba()`).
- Endereço: `url_for` no template, `nexusRota()` no JS.
- Nenhum nome de colega em arquivo versionado (testes com nomes fictícios).
- Fracttal só GET pelo `fracttal.ler`, laço de fundo declarado com `fracttal_conta.de_fundo("fundo:nexus-prefiltro", fn)`;
  a visita nunca lê o Fracttal nem o S3.
- Parâmetros (config, com padrão): `NEXUS_PREFILTRO_HORAS_TARDE`=24, `NEXUS_PREFILTRO_DIF`=12,
  `NEXUS_PREFILTRO_DIF_PRINT`=4, `NEXUS_PREFILTRO_POR_VOLTA`=150, `NEXUS_PREFILTRO_PAUSA_S`=2, `NEXUS_PREFILTRO=0` desliga
  o laço.
- Fora do pré-filtro: religamento (tipo ou tarefa), etiquetas PERFORMANCE, CHAMADOS, ENGENHARIA, criada pelo COS.

## Review Focus

1. OS com dezenas de fotos (75 numa só): o laço pagina os anexos (100 por página) e não guarda os bytes.
2. Fracttal recusando (429) no meio da volta: a volta para, o que já foi lido fica, a próxima volta continua.
3. OS que sai da fila: os fatos e as miniaturas dela saem do disco.
4. Captura de tela parecida (prints de geração do mês): não vira "repetida" com a diferença de foto de câmera.
5. Lote com OS sem sessão do Fracttal: para no 1º 401 e diz como entrar; nada aprovado por engano.

---

### Task 1: As regras puras

**Files:** Create `nexus/campo/prefiltro.py`; Test `tests/test_campo_prefiltro.py`

**Produces:**
- `parametros(config) -> dict` com `horas_tarde`, `dif`, `dif_print`, `por_volta`, `pausa_s`.
- `dhash(img: PIL.Image.Image) -> int` — 256 bits (16×16) da parte de cima (75%) em cinza.
- `pares_repetidos(anexos: list[dict], dif: int, dif_print: int) -> list[list[str]]` — anexo = `{"id", "hash", "print"}`;
  par `[id_anterior, id]`, um por foto repetida; com `print` em qualquer das duas, vale `dif_print`.
- `fora_do_escopo(cruas: list[dict], cos: dict | None) -> str` — "Religamento", "PERFORMANCE", "CHAMADOS", "ENGENHARIA",
  "Criada pelo COS" ou "" (reusa `verificacao.etiqueta_fora` e `criada_pelo_cos`).
- `classificar(o: dict, fatos: dict | None, fechado_app: str, p: dict) -> dict` — `o` é a OS de `_por_os` (com
  `tarefas`); devolve `{"coluna": "nao_ok"|"duvida"|"pronta"|"conferindo", "avisos": [{"nivel": "critico"|"alerta"|
  "neutro", "texto": str, "fotos": [id, ...]}], "tarde": int, "repetidas": int}`.

- [ ] Testes: `test_mesma_foto_com_carimbo_diferente_e_repetida` (imagem sintética + faixa de carimbo diferente no pé →
  par), `test_fotos_diferentes_nao_sao_repetidas`, `test_print_parecido_nao_e_repetido_mas_foto_de_camera_e`,
  `test_anexada_mais_de_24h_depois_e_nao_ok` (anexada 25 h depois de `fechado_app` → `nao_ok`, aviso com a contagem e
  "1 dia depois"), `test_23h_depois_nao_dispara`, `test_fora_do_app_e_em_duvida`, `test_repetida_e_em_duvida`,
  `test_sem_fatos_e_conferindo`, `test_fato_com_fotos_por_ler_vai_para_a_coluna_pior` (fora do App + fatos ausentes →
  `duvida` com aviso "faltam fotos por ler"), `test_escopo` (cada motivo), `test_avisos_da_regra_do_app_nao_mudam_a_coluna`
  (nota 60 em OS sem fato → `pronta` com aviso de nota).
- [ ] Implementar até passar; commit `feat(campo): regras do pré-filtro por fatos (prefiltro.py)`.

### Task 2: A leitura de fundo dos anexos

**Files:** Create `nexus/campo/prefiltro_fundo.py`; Modify `nexus/campo/aprovacao.py` (`_reler`: depois da fila boa,
`prefiltro_fundo.pedir_conferencia(app)`; `limpar`), `nexus/campo/__init__.py` (boot: `prefiltro_fundo.carregar_do_disco`);
Test `tests/test_campo_prefiltro_fundo.py`

**Consumes:** Task 1 (`dhash`, `pares_repetidos`, `parametros`).
**Produces:**
- `fatos(id_wo) -> dict | None` = `{"chave", "lido_em", "anexos": [{"id", "tarefa", "desc", "anexada", "print"}],
  "pares": [[id, id]], "erro"}`; `estado() -> {"conferidas", "lendo", "erro"}`.
- `conferir(app, linhas: list[dict]) -> int` (a volta, síncrona; quantas OS leu) e `pedir_conferencia(app)` (thread
  `nexus-prefiltro`, uma por vez).
- `baixar(url) -> tuple[bytes, str]` (bytes, `Last-Modified` em ISO UTC) — trocável nos testes.
- `miniatura(id_anexo) -> Path | None`; `carregar_do_disco(app)`.
- Disco: `pasta_dados/campo/prefiltro.json.gz` e `pasta_dados/campo/prefiltro_fotos/<id>.jpg` (240 px, só das fotos
  em pares).

- [ ] Testes com Fracttal falso (`fracttal.usar_fornecedor`) e `baixar` falso: `test_le_os_nova_uma_vez`,
  `test_chave_mudou_rele`, `test_teto_por_volta_e_a_mais_nova_primeiro`, `test_recusa_para_a_volta_e_guarda_o_lido`,
  `test_pagina_os_com_mais_de_100_anexos`, `test_os_que_saiu_da_fila_some_do_disco`, `test_ida_e_volta_do_disco`,
  `test_so_imagens`, `test_miniatura_so_das_repetidas`, `test_fora_do_escopo_nao_e_lido` (religamento, PERFORMANCE).
- [ ] Implementar; commit `feat(campo): leitura de fundo dos anexos do pré-filtro`.

### Task 3: O fechamento no App na conta pronta

**Files:** Modify `nexus/campo/aprovacao.py` (`fila_toda.calcular`: cada linha ganha `fechado_app` = a maior hora do
celular — `dev_ts`, senão `server_ts` — das linhas do registro do App daquela OS); Test em `tests/test_campo_prefiltro.py`
(`test_fechado_app_e_o_ultimo_fechamento_da_os`).

- [ ] Teste, implementação, commit `feat(campo): a hora do último fechamento no App na fila da Aprovação`.

### Task 4: O quadro

**Files:** Modify `nexus/torres/campo/__init__.py` (rota `/aprovacao`: colunas, fora do pré-filtro, ainda conferindo,
CSV; rota nova `/aprovacao/foto/<id_anexo>` com login e 404 sem arquivo); Rewrite
`nexus/torres/campo/templates/campo/aprovacao.html`; Modify `nexus/static/campo.css` (classes `apq-*`); Rewrite
`tests/test_campo_aprovacao_responsavel.py`; ajustar `tests/test_campo_aprovacao_supervisor.py`,
`tests/test_campo_aprovacao.py`, `tests/test_campo_fila_rapida.py`.

**Consumes:** Tasks 1–3.
**Marcação que os testes leem:** `section.apq-coluna[data-coluna=pronta|duvida|nao_ok]` com o número no cabeçalho;
`article.apq-cartao[data-wo][data-folio][data-coluna]`; dentro, nesta ordem, `.apq-score`, `ul.apq-avisos`,
`button[data-apq-aprovar]`; `input[data-apq-marcar]` só em Pronta e Em dúvida; `button[data-apq-lote]`; `#apq-fora` e
`#apq-conferindo`; filtros `select[name=responsavel]` (servidor), `select[data-apq-cliente]` e `input[data-apq-busca]`
(na página).

- [ ] Testes: colunas e números por responsável; cartão na ordem score → avisos → Aprovar; a foto repetida mostra as
  duas miniaturas (`/t/campo/aprovacao/foto/<id>`); marcar só em Pronta e Em dúvida; fora do pré-filtro com o motivo;
  ainda conferindo; o JS chama `nexusRota('/os/api/os/')` + `/concluir` e a conferência; 401 para o lote; CSV com
  "Coluna" e "Motivos"; `node --check` do script; a rota da foto pede login e dá 404 sem arquivo; a visita não lê o
  Fracttal.
- [ ] Implementar; commit `feat(campo): Aprovação de OS em quadro por fatos, com o Aprovar e o lote`.

### Task 5: Documentação e prova

**Files:** Modify `nexus/torres/campo/CLAUDE.md` (a seção da Aprovação de OS reescrita, a tabela das telas).

- [ ] Suíte inteira com o vigia de memória; navegador na cópia de prova (5170) com uma fila real guardada, computador e
  375 px; prova no Fracttal de verdade em TESTE - PA se der (senão, a entrega diz que não foi conferida).
- [ ] Commit `docs(campo): a Aprovação de OS por fatos`.

### Task 6 (por último): O veredito no banco

**Files:** `nexus/dados/catalogo.py` (fato `prefiltro_os` e livro `nexus_prefiltro`), gravação pela volta de fundo;
testes do catálogo e da gravação. Ler `nexus/dados/CLAUDE.md` antes. Se o tempo apertar, vira a próxima entrega.
