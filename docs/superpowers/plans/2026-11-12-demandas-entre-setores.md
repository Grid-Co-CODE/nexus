# Demandas entre setores — plano de construção

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** um setor demanda outro dentro do Nexus (pessoa + setor + tema com prazo em dias úteis, usinas, OS da usina,
anexos), com o vai e volta, a Caixa de entrada do Comando e um sininho próprio.

**Architecture:** a regra pura (prazo, situação, avisos) num módulo sem Flask; a gravação e a leitura do livro
`nexus_demandas` num módulo ao lado, no molde das Sugestões (`nexus/casca/sugestoes.py`: Cofre, `livros.publicar`, trava,
cópia de 60 s); as rotas debaixo de `/t/comando/caixa-de-entrada/demandas/...` (herdam a permissão da Caixa, que é de
todos); o bloco das demandas entra no alto da Caixa; o sininho, no topo do `base.html`.

**Tech Stack:** Python 3, Flask, Jinja, CSS por tokens (`comando.css`), JS sem handler inline; testes com pytest e o
banco falso de `tests/test_campo_visao.py`.

**Spec:** `docs/superpowers/specs/2026-11-12-demandas-entre-setores-design.md`

## Global Constraints

- Tudo em pt-BR (código, comentário, tela). Sem emoji na interface; tema navy; status pela cor (cn-ok/alerta/critico/info).
- Banco com leitura aberta: no banco, pessoa só por `pessoa_hmac` (HMAC do e-mail, `cadastro.ligacao_campo.codigo_da_pessoa`)
  e `pessoa_id`; título, descrição, nomes, textos e nomes de anexo só em `dados_cifrados` (Cofre com `NEXUS_CHAVE_CADASTRO`).
- Livro `nexus_demandas`, abas `dim_tema`, `fato_demanda`, `fato_demanda_usina`, `fato_evento_demanda`, registrado em
  `nexus/dados/catalogo.py` (`Fato` de cada aba + `Livro(..., so_cresce=True)`), `explica.RESUMO`/`PARA_QUE` de cada fato e
  a linha em `nexus/dados/CLAUDE.md` ANTES da 1ª gravação (o teste do catálogo cobra).
- Prazo em dias úteis: sem sábado, domingo e `nexus.dados.calendario.nacionais_calculados(ano)` (dict `{date: nome}`).
- Pedir informação **pausa** o prazo; Finalizada sem ok nem devolução em **3 dias úteis** = Concluída sozinha (calculada na
  leitura, não gravada); vencida avisa **quem recebeu + todo o setor dele**.
- Anexos: a regra das Sugestões (`sugestoes.anexos()` valida; até 5 arquivos, 5 MB cada, 15 MB juntos), no disco em
  `<pasta de dados>/demandas/<demanda_id>/`, nome neutro.
- OS: só uma OS do retrato `nexus_os · fato_tarefa_os` (`visao._livro(FT.LIVRO, FT.ABA)`) com `usina_id` entre as usinas
  escolhidas; o número abre o card do OS Creator (`oscreator/card_os_abrir.html`, `NexusOsCard.abrirFolio(folio, op)`).
- A linha da Caixa mostra só: o selo do prazo, quem pediu, o setor dele, o título e as primeiras 6 palavras; à direita, a
  situação e o tema. O tema aparece UMA vez no detalhe (acima do título).
- Endereços nos templates com `{{ raiz }}`/`url_for`/`|na_raiz` (o `test_prefixo` cobra); POST com o código da sessão e
  `de_outro_site()` (como as Sugestões).
- Larguras de quebra só as do DESIGN.md (480, 640, 820, 900, 1100, 1180).

## Review Focus

1. **Demanda para quem não tem setor ou para setor excluído:** recusada com texto claro ("Essa pessoa não tem setor no
   Nexus"), nada gravado — teste no Task 3.
2. **Prazo que cai num feriado ou fim de semana, e pausa que atravessa fim de semana:** o "Resposta até" pula os dois —
   teste no Task 2.
3. **Duplo clique no Enviar / no botão de evento:** o `novo_id` do formulário torna o 2º envio inofensivo — teste no Task 3.
4. **Ação fora do papel ou fora da vez** (quem recebeu tenta concluir; quem pediu tenta responder; devolver sem
  justificativa; responder demanda concluída): recusada, nada gravado — teste no Task 3.
5. **Sem a chave do cadastro ou sem login de pessoa (senha de administrador):** a tela abre e diz o que falta; o formulário
  não aparece; nada é gravado — teste no Task 5.

---

### Task 1: O livro, o catálogo e os temas do setor

**Files:**
- Create: `nexus/comando/demandas.py`
- Modify: `nexus/dados/catalogo.py` (4 `Fato` + 1 `Livro`), `nexus/dados/explica.py` (RESUMO e PARA_QUE dos 4),
  `nexus/dados/CLAUDE.md` (uma linha por fato na tabela "O que existe")
- Test: `tests/test_comando_demandas.py`

**Interfaces:**
- Produces (em `nexus/comando/demandas.py`):
  - `LIVRO = "nexus_demandas"`, `ABA_TEMA = "dim_tema"`, `ABA_DEMANDA = "fato_demanda"`, `ABA_USINA = "fato_demanda_usina"`,
    `ABA_EVENTO = "fato_evento_demanda"`; `CAB_TEMA`, `CAB_DEMANDA`, `CAB_USINA`, `CAB_EVENTO` (as colunas do spec, nessa
    ordem; `dados_cifrados` por último onde houver)
  - `class Recusada(ValueError)`; `limpar() -> None`
  - `ID_DEMANDA = re.compile(r"d[0-9a-f]{11}")`, `ID_EVENTO = re.compile(r"e[0-9a-f]{11}")`, `ID_TEMA = re.compile(r"m[0-9a-f]{11}")`
  - `ler(forcar: bool = False) -> dict` → `{"temas", "demandas", "usinas", "eventos", "lido_em", "erro"}` (cópia de 60 s;
    a falha devolve a última boa com o erro)
  - `temas(setor_id: int | None = None, so_ativos: bool = True) -> list[dict]` → `[{tema_id, setor_id, nome,
    prazo_dias_uteis, ativo}]` (a última versão de cada `tema_id`, nome decifrado, ordem por nome)
  - `salvar_tema(setor_id: int, nome: str, prazo_dias_uteis: int, usuario: dict, tema_id: str | None = None,
    ativo: bool = True) -> dict` (nova versão; nome 1–60 caracteres; prazo 1–30)
  - `_publicar(temas, demandas, usinas, eventos) -> None` (as 4 abas juntas; aba vazia só vai depois da 1ª linha dela)

- [ ] **Step 1: testes que falham** — `test_o_livro_esta_no_catalogo_antes_da_1a_gravacao` (as 4 abas em
  `catalogo.LIVRO_POR_NOME["nexus_demandas"].abas` e `so_cresce`; cada `catalogo.POR_ID[...]` com `chave == ("id",)` ou
  a chave do spec; `explica.RESUMO` e `PARA_QUE` com os 4 ids) e `test_o_tema_do_setor_vai_cifrado_e_vale_a_ultima_versao`
  (salva "Dado que não bate" com prazo 2, edita para 3, desativa; `temas(setor)` devolve só a última; `temas(so_ativos=False)`
  inclui o desativado; o nome não aparece em claro em `banco.linhas(LIVRO, ABA_TEMA)`; prazo 0 ou 31 levanta `Recusada`).
- [ ] **Step 2:** `python -m pytest -q -p no:cacheprovider tests/test_comando_demandas.py` → FAIL (módulo não existe).
- [ ] **Step 3:** implementar o módulo (o molde do `nexus/casca/sugestoes.py`: `_cofre`, `_quem`, `_banco`, `_TRAVA`,
  `_CACHE`, `_ctx_*` por aba) e as entradas do catálogo, do explica e do CLAUDE.md dos dados.
- [ ] **Step 4:** rodar os dois testes + `tests/test_dados_camada.py` → PASS.
- [ ] **Step 5:** commit `feat(demandas): o livro nexus_demandas no catalogo e os temas de cada setor`.

### Task 2: A regra pura — prazo, situação, avisos

**Files:**
- Create: `nexus/comando/demandas_regras.py` (sem Flask, sem banco)
- Test: `tests/test_comando_demandas.py`

**Interfaces:**
- Produces:
  - `SITUACOES = {"nova": ("Nova", "info"), "em_analise": ("Em análise", "alerta"), "aguardando": ("Aguardando quem pediu",
    "neutro"), "finalizada": ("Finalizada", "ok"), "concluida": ("Concluída", "ok"), "devolvida": ("Devolvida", "critico")}`
  - `EVENTOS = ("em_analise", "pediu_informacao", "informou", "respondeu", "devolveu", "concluiu")`
  - `somar_dias_uteis(inicio: date, n: int) -> date` e `dias_uteis_entre(a: date, b: date) -> int` (dias úteis em (a, b])
  - `estado(demanda: dict, eventos: list[dict], prazo_dias: int, hoje: date) -> dict` → `{situacao, rotulo, tom,
    prazo: date | None, dias_restantes: int | None, vencida: bool, pausada: bool, sozinha: bool, aberta: bool}`; `demanda`
    tem `registrado_em` (ISO UTC); cada evento tem `evento` e `registrado_em`, em ordem de gravação
  - `selo_do_prazo(e: dict) -> tuple[str, str, str]` → (linha 1, linha 2, tom): "Vence"/"hoje"/critico, "Falta"/"1 dia"/alerta,
    "Faltam"/"N dias"/ok, "Vencida"/"há N dias"/critico, "Pausado"/"aguarda"/neutro, "Respondida"/"dd/mm"/neutro, "Concluída"/"dd/mm"/neutro
  - `avisos(lista: list[dict], meu_hmac: str, meu_setor: int | None, hoje: date) -> list[dict]` → `[{demanda_id, tipo,
    titulo_curto, tom}]`, `tipo` em `nova`, `prazo`, `vence_hoje`, `vencida`, `devolvida`, `respondida`, `informacao`
    (as regras do spec: vencida também para quem é do setor de quem recebeu); a lista já vem com `estado` em cada item

- [ ] **Step 1: testes que falham** —
  `test_prazo_pula_fim_de_semana_e_feriado` (`somar_dias_uteis(date(2026,11,13), 1) == date(2026,11,16)`;
  `somar_dias_uteis(date(2026,11,19), 1) == date(2026,11,23)` por causa de 20/11; `dias_uteis_entre(date(2026,11,13),
  date(2026,11,16)) == 1`);
  `test_situacoes_pelo_ultimo_evento` (sem evento = nova; em_analise; pediu_informacao = aguardando e `pausada`; informou =
  em_analise; respondeu = finalizada; devolveu = devolvida com prazo recontado da devolução; concluiu = concluida);
  `test_a_pausa_empurra_o_prazo` (aberta qua 11/11 com 2 dias: prazo sex 13/11; pediu informação qui 12/11 e informou seg
  16/11: prazo vira qua 18/11);
  `test_vencida_e_conclusao_sozinha` (prazo 13/11 e hoje 16/11 em análise: vencida, `dias_restantes` negativo; respondida
  em 10/11 e hoje 13/11: `concluida` com `sozinha=True`; hoje 12/11: ainda finalizada);
  `test_avisos_de_quem_pediu_de_quem_recebe_e_do_setor` (nova e "falta 1 dia" para quem recebe; vencida também para outro
  do mesmo setor e não para pessoa de outro setor; respondida e informacao para quem pediu).
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3:** implementar. A data de cada evento é o dia de Brasília do `registrado_em` (UTC-3).
- [ ] **Step 4:** rodar → PASS.
- [ ] **Step 5:** commit `feat(demandas): a regra do prazo em dias uteis, das situacoes e dos avisos`.

### Task 3: Abrir a demanda e registrar cada passo

**Files:**
- Modify: `nexus/comando/demandas.py`
- Test: `tests/test_comando_demandas.py`

**Interfaces:**
- Consumes: Task 1 (`_publicar`, `temas`, `_cofre`), Task 2 (`estado`), `nexus.casca.sugestoes.anexos(arquivos)` (valida;
  levanta `sugestoes.Recusada`)
- Produces:
  - `pessoas_com_setor() -> list[dict]` → `[{hmac, nome, setor_id, setor_nome}]`: as decisões de setor vigentes
    (`setor_telas.setor_de_cada_codigo` sobre o livro dos setores) cruzadas com o pessoal do Fracttal
    (`cadastro.fracttal_pessoal.ler_pessoal()`, e-mail → `codigo_da_pessoa`); só setor ativo; ordem por nome
  - `os_das_usinas(usina_ids: set[int]) -> list[dict]` → `[{os: int, usina_id, tipo, status}]`, uma por OS, do retrato
  - `abrir(form: dict, arquivos, usuario: dict) -> dict` — `form` com `para_hmac`, `para_setor_id`, `tema_id`, `titulo`
    (1–120), `descricao` (1–4000), `usinas` (lista de ids), `os` (opcional), `novo_id` (`d` + 11 hex; o 2º envio devolve a
    mesma); recusa: sem pessoa no login, pessoa sem esse setor, tema de outro setor ou desativado, OS fora das usinas
  - `registrar(demanda_id: str, evento: str, texto: str, usuario: dict, novo_id: str | None = None) -> dict` — o papel e a
    vez: `em_analise`, `pediu_informacao` (texto obrigatório), `respondeu` (texto obrigatório) só de quem recebeu, com a
    demanda aberta; `informou` (texto obrigatório) só de quem pediu, com ela aguardando; `concluiu` e `devolveu`
    (justificativa obrigatória) só de quem pediu, com ela finalizada; o resto levanta `Recusada`
  - `arquivo(demanda_id: str, n: int) -> tuple[Path, dict] | None` (anexo para baixar)

- [ ] **Step 1: testes que falham** — com o banco falso do `test_campo_visao` (usinas 1, 2, 3; pessoas com setor via o
  livro de setores como em `tests/test_base_fracttal.py`; `ler_pessoal` trocado por monkeypatch):
  `test_abrir_grava_cifrado_e_o_segundo_envio_nao_duplica` (título, descrição e nomes fora do claro; `fato_demanda_usina`
  com as duas usinas; o mesmo `novo_id` = 1 linha);
  `test_a_os_tem_de_ser_da_usina_escolhida` (OS de outra usina → `Recusada`, nada gravado);
  `test_destinatario_sem_setor_ou_tema_de_outro_setor_recusa`;
  `test_o_papel_e_a_vez_de_cada_passo` (quem pediu não responde; quem recebeu não conclui; devolver sem justificativa
  recusa; responder concluída recusa; a sequência válida grava os eventos na ordem);
  `test_anexo_fora_do_limite_recusa_a_demanda_inteira` (6 arquivos → `Recusada`, nada no disco).
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3:** implementar (anexos: `sugestoes.anexos()` para validar e uma `_gravar_anexos` própria na pasta
  `demandas/<id>`, apagando a pasta se o banco recusar).
- [ ] **Step 4:** rodar → PASS.
- [ ] **Step 5:** commit `feat(demandas): abrir a demanda (pessoa, setor, tema, usinas, OS da usina, anexos) e o vai e volta`.

### Task 4: A lista para a Caixa (decifrada, com estado) e os filtros

**Files:**
- Modify: `nexus/comando/demandas.py`
- Test: `tests/test_comando_demandas.py`

**Interfaces:**
- Produces:
  - `lista(hoje: date | None = None) -> list[dict]` → cada demanda com `demanda_id, de_hmac, de_nome, de_setor_id,
    de_setor_nome, para_hmac, para_nome, para_setor_id, para_setor_nome, tema_id, tema_nome, titulo, descricao, inicio
    (primeiras 6 palavras + "…"), usinas [(id, nome)], os, anexos, eventos [{evento, quando_txt, nome, texto}],
    estado (o de `demandas_regras.estado`), selo (o de `selo_do_prazo`)`; ordem: abertas pelo prazo mais perto, depois as
    fechadas da mais nova para a mais velha
  - `da_aba(lista: list[dict], aba: str, meu_hmac: str, meu_setor: int | None) -> list[dict]` — `para` (para_hmac == meu),
    `pedi` (de_hmac == meu), `setor` (para_setor_id == meu setor)
  - `filtrar(lista, filtro: str, pessoa: str = "", tema: str = "") -> list[dict]` — `abertas` (padrão), `vencem`
    (dias_restantes ≤ 1 e aberta), `vencidas`, `finalizadas`, `concluidas`

- [ ] **Step 1: testes que falham** — `test_a_lista_decifra_e_ordena_pelo_prazo`, `test_as_tres_abas_e_os_filtros`
  (para mim / que eu pedi / do meu setor; "vencem até amanhã"; filtro por pessoa e por tema no setor).
- [ ] **Step 2:** rodar → FAIL. **Step 3:** implementar. **Step 4:** rodar → PASS.
- [ ] **Step 5:** commit `feat(demandas): a lista decifrada com o estado e os filtros das tres abas`.

### Task 5: As telas — o bloco da Caixa, a Nova demanda e os Temas do setor

**Files:**
- Create: `nexus/torres/comando/demandas_tela.py` (rotas; importado no fim de `nexus/torres/comando/__init__.py`, como o
  `campo/cliente_tela.py`), `nexus/torres/comando/templates/comando/_demandas.html`,
  `nexus/torres/comando/templates/comando/temas_setor.html`, `nexus/static/comando-demandas.js`
- Modify: `nexus/torres/comando/__init__.py` (a `Tela("temas-do-setor", "Temas do setor", ..., de_todos=True)`; o contexto
  da Caixa com `dem`), `nexus/torres/comando/templates/comando/caixa.html` (inclui `_demandas.html` no alto e o
  `oscreator/card_os_abrir.html`), `nexus/static/comando.css`
- Test: `tests/test_comando_demandas.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces (rotas):
  - `GET /t/comando/caixa-de-entrada?dem=para|pedi|setor&f=<filtro>&d=<demanda_id>&p=<hmac>&t=<tema_id>` — o bloco
  - `POST /t/comando/caixa-de-entrada/demandas/nova` (multipart; volta para `?dem=pedi&d=<id>` com o aviso)
  - `POST /t/comando/caixa-de-entrada/demandas/<demanda_id>/passo` (`acao`, `texto`, `novo_id`)
  - `GET /t/comando/caixa-de-entrada/demandas/<demanda_id>/anexo/<n>` (só quem pediu, quem recebeu, o setor dele e
    administrador; senão 404)
  - `GET /t/comando/caixa-de-entrada/demandas/os?usinas=1,2` → JSON `[{os, rotulo}]` para o campo da OS
  - `GET /t/comando/temas-do-setor` e `POST /t/comando/temas-do-setor/salvar` (o setor da pessoa; o administrador escolhe
    o setor por `?setor=`)

- [ ] **Step 1: testes que falham** —
  `test_quem_recebe_ve_em_para_mim_e_o_setor_em_do_meu_setor` (logado como cada um; a linha tem o nome de quem pediu, o
  setor, o título e o início; não tem o tema repetido no detalhe);
  `test_o_fluxo_inteiro_pela_tela` (abrir, em análise, pedir informação, informar, responder, devolver, responder,
  concluir; o aviso de cada passo; outro site e formulário vencido não gravam);
  `test_o_card_da_os_e_o_anexo` (o número da OS sai com `data-os-folio`; o anexo baixa para quem pode e dá 404 para outro);
  `test_temas_do_setor` (a pessoa edita os do seu setor; outro setor → 403; o administrador escolhe o setor);
  `test_sem_chave_ou_sem_pessoa_a_tela_diz_e_nao_grava` (Review Focus 5).
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3:** implementar, no desenho da prévia v2 (`Projeto API PV/docs/mockups/demandas-entre-setores/index.html`):
  as abas, a faixa de filtros, a lista e o detalhe ao lado; o diálogo da Nova demanda (`<dialog>` aberto pelo JS); o campo
  da OS que pede a lista à rota `os` quando as usinas mudam; "Resposta até <dia>" calculado no servidor por tema
  (`data-ate` em cada `<option>`); os botões do papel; tudo por tokens no `comando.css` (prefixo `dm-`).
- [ ] **Step 4:** rodar + `tests/test_tema.py tests/test_prefixo.py tests/test_larguras_de_quebra.py
  tests/test_comando_insights.py` → PASS (a falha das larguras em 560 px do `engenharia.css`/`os_acoes.css` é de outra
  sessão e já estava na main).
- [ ] **Step 5:** commit `feat(demandas): a Caixa de entrada com as demandas, a Nova demanda e os Temas do setor`.

### Task 6: O sininho das demandas no topo

**Files:**
- Modify: `nexus/casca/__init__.py` (`_sino_demandas()` e o contexto `sino_dem`), `nexus/templates/base.html` (o botão à
  esquerda do `sino-topo`), `nexus/static/nexus.css`
- Test: `tests/test_comando_demandas.py`

**Interfaces:**
- Consumes: `demandas.lista()`, `demandas_regras.avisos()`, o `_meu_hmac()` da torre Comando e `setor_telas.acesso()["setor"]`.
- Produces: `_sino_demandas() -> dict | None` → `{"n": int, "itens": [{titulo, sub, tom, link}]}` (até 8; link para
  `/t/comando/caixa-de-entrada?dem=...&d=<id>`); None para cliente, Modo cliente e sem login; nunca derruba a página.

- [ ] **Step 1: teste que falha** — `test_o_sininho_conta_o_que_pede_a_minha_acao` (quem recebe vê "Nova demanda de
  <nome>" e o número; quem pediu vê "Respondida" depois do responder; o cliente não vê o botão).
- [ ] **Step 2:** rodar → FAIL. **Step 3:** implementar (ícone `ph-tray`, número no verde da Grid; lista em `<details>`
  como o `sino-topo`). **Step 4:** rodar → PASS.
- [ ] **Step 5:** commit `feat(demandas): o sininho das demandas no topo`.

### Task 7: O .md da área, a suíte e a prévia

**Files:**
- Modify: `nexus/comando/CLAUDE.md` (seção "Demandas entre setores (12/11/2026)": para que serve, as regras do Levi, o
  livro, as rotas, como provar)

- [ ] **Step 1:** escrever a seção.
- [ ] **Step 2:** `python -m pytest -q -p no:cacheprovider -rf --maxfail=30` → só as falhas que já estavam na main.
- [ ] **Step 3:** prévia local com o banco falso (porta 5223): abrir, receber, pedir informação, informar, responder,
  devolver, concluir; o sininho; o card da OS; o celular (375 px) sem rolagem de lado.
- [ ] **Step 4:** commit `docs(demandas): a secao das demandas no CLAUDE.md do Comando`.
