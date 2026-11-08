# Mapa de equipe (parte do Nexus) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Receber as posições dos técnicos de campo enviadas pelo Nexus Field (3 rotas do contrato), guardar no banco cifrado e mostrar o Mapa de equipe na torre Usinas 360°, com o Abrir rota pelo servidor.

**Architecture:** Um pacote `nexus/campo/equipe/` com peças puras e testáveis (o token Microsoft, as chaves dos aparelhos, os pontos, os deslocamentos, a situação de cada técnico) e um gravador em fundo que publica no banco em lote (o `livros.publicar` troca o livro inteiro: não há "acrescentar"). O que chega é guardado na hora num diário local cifrado (o desenho do `nexus/zeladoria/gravacao.py`) e publicado de 5 em 5 min; os pontos vão num livro por DIA e os deslocamentos num por MÊS (famílias), para cada gravação ser pequena e a T.I. apagar o velho livro a livro. As rotas ficam em `nexus/torres/campo/equipe_tela.py`.

**Tech Stack:** Flask, `cryptography` (já instalado: RS256 do token e o `Cofre` AES-GCM), `requests`, pytest com o `tests/pg_falso.py`/`ApiPGFalsa` e o fixture `freeze`/monkeypatch de hora.

**Spec:** `C:\GridcoAuto\app-campo-android\docs\superpowers\specs\2026-11-08-mapa-de-equipe-design.md` (seção 4.2, itens 2, 3 e 5 da seção 5, contrato da seção 8).

## Global Constraints

- Janela de coleta: das 6h às 22h na hora do técnico (o `fuso` do lote); fora dela o ponto é descartado.
- Ponto com mais de 7 dias é descartado na entrada e nunca usado nem mostrado; até 200 pontos por lote.
- Guarda: 7 dias os pontos, 1 ano os deslocamentos (a limpeza no banco é da T.I.; o Nexus para de ler antes).
- "Sem sinal" a partir de 30 minutos sem posição.
- CORS da rota do aparelho: só a origem `https://gridco-campo-mw.azurewebsites.net`, cabeçalhos `Authorization` e `Content-Type`.
- Chave do aparelho: 32 bytes aleatórios em base64url; o banco guarda só o hash (sha256); um par pessoa + aparelho tem uma chave só, e a nova troca a velha.
- Respostas do contrato: aparelho `200 {coleta: true, chave}` | `200 {coleta: false}` | `401`; posições `200 {aceitos, coleta}` | `401`; revogar `204`.
- A coordenada (do técnico ou da usina) nunca em texto na página nem no JSON; no banco só cifrada (`Cofre`, `NEXUS_CHAVE_CADASTRO`).
- Abrir rota: só Google Maps, montado no servidor por redirecionamento; não aparece para "parado fora de usina".
- Quem vê: setores PCM (9), COS (5), Performance (2), Supervisão Campo (6) e Responsáveis UFV (10), mais os administradores; conferido também dentro da rota (o portão de setor fica desligado em teste e sem `NEXUS_PESSOA_HMAC`).
- Quem é coletado: técnico de campo ativo do cadastro (`pcm.tecnicos_usina.pessoas_de_campo`) E, no piloto, só os escolhidos (padrão: ninguém).
- Repositório PÚBLICO: nenhum nome de pessoa em código, testes ou docs; tudo em pt-BR; comentário explica o porquê.
- Regra 10 do `nexus/dados/CLAUDE.md`: livro novo entra em `catalogo.LIVROS`/`FAMILIAS` e em `explica.py` ANTES de existir.

## Review Focus

1. **O fuso do lote.** `fuso` = minutos SOMADOS ao UTC para dar a hora local (Brasília = -180; o Mato Grosso = -240). Ponto às 21:59 locais entra, às 22:00 sai; o mesmo `t` num técnico do MT cai uma hora antes. Teste em `test_equipe_pontos.py`.
2. **O token que não é o ID token.** O `getTokenMW` devolve `idToken || accessToken`: um token do Graph (outro `aud`) tem de dar 401, não 500; Microsoft fora do ar (JWKS sem resposta) dá 503, para a casca tentar de novo, e não 401 (que apagaria a chave). Testes em `test_equipe_token.py` e `test_equipe_rotas.py`.
3. **Reinício do servidor.** O diário do dia é relido no boot: o mapa volta com as últimas posições, e o gravador nunca publica um dia vazio por cima de um livro que já tem pontos (máquina nova). Teste em `test_equipe_gravador.py`.
4. **Lote repetido ou fora de ordem.** Sem sinal, a casca reenvia: o mesmo (pessoa, t) entra uma vez (`ponto_id` = sha1 de pessoa|t). Teste em `test_equipe_pontos.py`.
5. **Duas contas no mesmo aparelho e a chave trocada.** A chave nova de pessoa+aparelho revoga a velha (401 nela); outra pessoa no mesmo aparelho tem a sua. Teste em `test_equipe_aparelhos.py`.

---

## Decisões do construtor (para o Levi conferir junto com o OK de subir)

- **Raio "na usina": 1 km** da coordenada da usina no cadastro — **confirmado pelo Levi em 08/11** ("Ok, vamo").
- **Cidade do "parado fora de usina": pela API do IBGE** (Levi, 08/11: "Faça puxar uma API do IBGE"). O servidor baixa a
  malha de municípios do ESTADO (`servicodados.ibge.gov.br/api/v3/malhas/estados/<UF>?intrarregiao=municipio&qualidade=minima&formato=application/vnd.geo+json`)
  e os nomes (`/api/v1/localidades/estados/<UF>/municipios`), guarda no disco por 30 dias e acha a cidade por ponto no
  polígono, no servidor. **A posição do técnico nunca vai ao IBGE** (baixa-se o estado inteiro; nada de geocodificação
  reversa por coordenada).
- **"Sem permissão" pede um campo novo no contrato:** `permissao: "sem"` (opcional) no lote de posições, com `pontos: []`. Sem ele o técnico sem permissão é igual a "sem posição hoje". **Avisar a sessão do Nexus Field.**
- **Cores:** em deslocamento = info (azul), parado na usina = ok (verde), parado fora de usina = neutro (cinza), sem sinal = alerta (âmbar), sem permissão = crítico (vermelho), sem posição hoje = só no painel, fora do mapa.
- **Registro da chave:** a casca pede chave só quando não tem (ou depois de um 401); cada pedido troca a chave. **Avisar a sessão do Nexus Field.**

---

### Task 1: O dado no catálogo (antes de existir)

**Files:**
- Modify: `nexus/dados/catalogo.py` (Fatos novos, `LIVROS`, `FAMILIAS`)
- Modify: `nexus/dados/explica.py` (`RESUMO`, `PARA_QUE`)
- Test: `tests/test_equipe_catalogo.py`

**Interfaces:**
- Produces (constantes usadas por todas as tasks, em `nexus/campo/equipe/__init__.py`):
  - `LIVRO_PONTOS_MOLDE = "nexus_equipe_pontos_AAAA_MM_DD"`, `ABA_PONTOS = "fato_ponto_equipe"`, `CAB_PONTOS = ("ponto_id", "data_id", "instante", "pessoa_id", "cifra")`
  - `LIVRO_DESLOC_MOLDE = "nexus_equipe_deslocamentos_AAAA_MM"`, `ABA_DESLOC = "fato_deslocamento_equipe"`, `CAB_DESLOC = ("deslocamento_id", "data_id", "pessoa_id", "usina_id_saida", "usina_id_chegada", "saida", "chegada", "duracao_min", "distancia_km")`
  - `LIVRO_APARELHOS, ABA_APARELHOS = "nexus_equipe_aparelhos", "fato_evento_aparelho"`, `CAB_APARELHOS = ("evento_id", "instante", "data_id", "pessoa_id", "aparelho", "evento", "chave_hash", "app")` (`evento` ∈ `emitida`, `revogada`)
  - `LIVRO_PILOTO, ABA_PILOTO = "nexus_equipe_piloto", "fato_decisao_piloto"`, `CAB_PILOTO = ("decisao_id", "instante", "data_id", "pessoa_id", "no_piloto", "decidida_por_hmac")`
  - `LIVRO_ACESSOS, ABA_ACESSOS = "nexus_equipe_acessos", "fato_acesso_mapa"`, `CAB_ACESSOS = ("acesso_id", "instante", "data_id", "pessoa_id", "pessoa_hmac", "acao", "alvo_pessoa_id", "usina_id")` (`acao` ∈ `abriu_mapa`, `abriu_rota`)
  - `livro_pontos(dia: date) -> str` e `livro_deslocamentos(dia: date) -> str`
  - As réguas do desenho, num lugar só: `JANELA_H = (6, 22)`, `GUARDA_PONTOS_DIAS = 7`, `GUARDA_DESLOC_DIAS = 365`,
    `MAX_PONTOS = 200`, `SEM_SINAL_MIN = 30`, `RAIO_USINA_KM = 1.0` (a confirmar com o Levi),
    `ORIGEM_APP = "https://gridco-campo-mw.azurewebsites.net"`

- [ ] **Step 1: Write the failing test** `test_os_livros_do_mapa_estao_no_catalogo_antes_da_1a_gravacao` (modelo: `tests/test_comando_insights.py:151`): os 5 Fatos com `area="campo"`, `grao` começando por "1 linha", `chave[0] == CAB[0]`, `tipo` (`transacao` para ponto, acesso, aparelho e piloto; `transacao` com medidas `duracao_min` (min, soma) e `distancia_km` (km, soma) para deslocamento); `LIVROS` com `nexus_equipe_aparelhos`, `nexus_equipe_piloto` e `nexus_equipe_acessos` (`so_cresce=True`, `no_banco=False`); `FAMILIAS` reconhece `nexus_equipe_pontos_2026_11_08` e `nexus_equipe_deslocamentos_2026_11`; `explica.RESUMO`/`PARA_QUE` com os 5; `livro_pontos(date(2026,11,8)) == "nexus_equipe_pontos_2026_11_08"`.
- [ ] **Step 2: Run** `python -m pytest -q -p no:cacheprovider tests/test_equipe_catalogo.py` — Expected: FAIL (`ModuleNotFoundError: nexus.campo.equipe`).
- [ ] **Step 3: Implement** as constantes e o catálogo. A observação do Fato do ponto diz: coordenada só cifrada (contexto `equipe/ponto/<ponto_id>`), 7 dias, o livro do dia some pela T.I.; o do deslocamento: 1 ano; o do acesso: LGPD (quem abriu o mapa ou a rota).
- [ ] **Step 4: Run** a task e `tests/test_dados_camada.py tests/test_dados_organograma.py tests/test_dados_livros_trava.py` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(equipe): o dado do Mapa de equipe no catálogo antes de existir`.

### Task 2: O ID token da Microsoft, com a assinatura conferida

**Files:**
- Create: `nexus/campo/equipe/token_ms.py`
- Modify: `nexus/auth/chaves.py` (`CHAVES`: `NEXUS_EQUIPE_MS_CLIENT_ID` e `NEXUS_EQUIPE_MS_TENANT_ID`, a mudar na tela Base → Chaves sem a T.I.)
- Test: `tests/test_equipe_token.py`

**Interfaces:**
- Produces: `class TokenRecusado(Exception)`, `class MicrosoftForaDoAr(Exception)`, `conferir(token: str, *, cliente: str, diretorio: str, chaves_jwks=None, agora: float | None = None) -> str` (devolve o e-mail em minúscula; `chaves_jwks` injeta as chaves no teste), `chaves_da_microsoft(diretorio: str) -> dict` (cache de 24 h; `kid` desconhecido força UMA releitura).

- [ ] **Step 1: Write the failing tests** com um par RSA gerado no teste (`cryptography`) e o JWKS montado dele: `test_o_id_token_do_app_passa_e_devolve_o_email` (iss `https://login.microsoftonline.com/<tid>/v2.0`, aud = cliente, tid, exp futuro → `"tecnico@gridco.com.br"` do `preferred_username`, em minúscula); `test_recusa` parametrizado: assinatura de outra chave, `alg` diferente de RS256 (inclusive `none`), aud do Graph (`00000003-0000-0000-c000-000000000000`), outro iss/tid, vencido há mais de 120 s, `nbf` no futuro além de 120 s, convidado (`#EXT#` no e-mail), domínio fora de `gridco.com.br` → `TokenRecusado`; `test_microsoft_fora_do_ar_nao_e_token_invalido` (JWKS que levanta `requests.ConnectionError` → `MicrosoftForaDoAr`).
- [ ] **Step 2: Run** `python -m pytest -q -p no:cacheprovider tests/test_equipe_token.py` — Expected: FAIL (módulo não existe).
- [ ] **Step 3: Implement** sem biblioteca nova: base64url do cabeçalho/corpo, `RSAPublicNumbers(e, n).public_key().verify(sig, f"{h}.{p}".encode(), PKCS1v15(), SHA256())`, JWKS de `https://login.microsoftonline.com/{diretorio}/discovery/v2.0/keys`; os domínios aceitos são os do `nexus.auth.microsoft.dominios(cfg)`. O docstring diz por que aqui a assinatura É conferida (o token vem do navegador; o login do Nexus não aceita token do navegador).
- [ ] **Step 4: Run** a task — Expected: PASS.
- [ ] **Step 5: Commit** `feat(equipe): o ID token do App conferido pela assinatura da Microsoft`.

### Task 3: As chaves dos aparelhos e quem é coletado

**Files:**
- Create: `nexus/campo/equipe/aparelhos.py`
- Test: `tests/test_equipe_aparelhos.py`

**Interfaces:**
- Consumes: as constantes da Task 1; `nexus.pcm.tecnicos_usina.pessoas_de_campo(base, cfg) -> {pessoa_id: {...}}`; `visao._Base().pessoa_do_login(email, nome)`.
- Produces: `class Chaveiro` com `emitir(pessoa_id: int, aparelho: str, app: str, agora: datetime) -> str` (a chave em claro, só nesta volta; revoga a anterior do mesmo par), `quem(chave: str) -> tuple[int, str] | None` (pessoa_id, aparelho), `revogar(chave: str, agora) -> bool`, `eventos_novos() -> list[list]` (linhas de `CAB_APARELHOS` a publicar) e `carregar(eventos: list[dict])` (reconstrói as ativas no boot); `coleta_vale(pessoa_id: int, tecnicos: dict, piloto: set[int]) -> bool`; `piloto_atual(decisoes: list[dict]) -> set[int]` (a última decisão de cada técnico).

- [ ] **Step 1: Write the failing tests:** `test_a_chave_tem_32_bytes_e_o_banco_so_ve_o_hash` (len(base64url-decode) == 32; o `chave_hash` do evento é o sha256 hex e a chave em claro não aparece em `eventos_novos()`); `test_a_chave_nova_do_mesmo_par_revoga_a_velha` (`quem(velha) is None`, evento `revogada`); `test_outra_pessoa_no_mesmo_aparelho_tem_a_sua`; `test_revogar_e_sem_efeito_para_chave_desconhecida`; `test_carregar_reconstroi_as_ativas`; `test_coleta_so_para_tecnico_ativo_e_no_piloto` (fora do cadastro, desligado, não técnico, técnico fora do piloto → False; padrão do piloto vazio → ninguém).
- [ ] **Step 2: Run** `python -m pytest -q -p no:cacheprovider tests/test_equipe_aparelhos.py` — Expected: FAIL.
- [ ] **Step 3: Implement** com `secrets.token_bytes(32)` → base64url sem `=`; um `threading.Lock`; `evento_id` = "A" + 11 hex (a regra das IDs com letra, `sugestoes.py:57-59`).
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(equipe): as chaves dos aparelhos (só o hash no banco) e quem é coletado`.

### Task 4: Os pontos: validação, janela, cifra e diário

**Files:**
- Create: `nexus/campo/equipe/pontos.py`
- Test: `tests/test_equipe_pontos.py`

**Interfaces:**
- Consumes: `nexus.cadastro.cifra.Cofre`; as constantes da Task 1.
- Produces: `aceitar(pessoa_id: int, lote: dict, agora_utc: datetime, cofre) -> list[dict]` (os pontos válidos como `{ponto_id, data_id, instante, pessoa_id, cifra, lat, lon, prec_m, vel_ms, mov}`; lat/lon só em memória), `class Diario(pasta: Path, cofre)` com `acrescentar(pontos)`, `do_dia(dia: date) -> list[dict]` (decifrados), `ultimos() -> dict[int, dict]` (o último ponto de cada pessoa, até 7 dias) e `apagar_velhos(hoje: date)` (arquivo local com mais de 7 dias sai: a guarda vale também no disco); `linha_do_banco(p: dict) -> list` (só `CAB_PONTOS`, sem lat/lon).

- [ ] **Step 1: Write the failing tests:** `test_a_janela_e_das_6h_as_22h_na_hora_do_tecnico` (`fuso=-180`: 05:59 sai, 06:00 entra, 21:59 entra, 22:00 sai; o mesmo `t` com `fuso=-240` muda de lado); `test_ponto_com_mais_de_7_dias_ou_no_futuro_sai` (futuro > 5 min); `test_ponto_invalido_sai_e_o_resto_entra` (lat fora de -90..90, lon fora de -180..180, prec negativa, `t` não numérico); `test_lote_com_mais_de_200_pontos_e_recusado` (`ValueError`); `test_o_mesmo_ponto_entra_uma_vez` (reenvio: mesmo `ponto_id`, `Diario` não duplica); `test_a_linha_do_banco_nao_tem_coordenada` (nenhum `lat`/`lon`/número com 4 casas em `linha_do_banco`; `Cofre.decifrar(cifra, f"equipe/ponto/{ponto_id}")` devolve o JSON com lat, lon, prec_m, vel_ms, mov); `test_o_diario_sobrevive_ao_reinicio` (novo `Diario` na mesma pasta devolve `ultimos()` iguais; o arquivo no disco não tem lat/lon em claro).
- [ ] **Step 2: Run** `python -m pytest -q -p no:cacheprovider tests/test_equipe_pontos.py` — Expected: FAIL.
- [ ] **Step 3: Implement**: `ponto_id` = "P" + sha1(f"{pessoa_id}|{t}")[:11]; `data_id` = o dia de Brasília do instante (regra 7); um arquivo `equipe/pontos_AAAAMMDD.jsonl` por dia na `pasta_dados`, uma linha cifrada por ponto (contexto `equipe/diario`), com `fsync` como o `zeladoria/gravacao.py:145-170`.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(equipe): os pontos do Nexus Field validados, cifrados e no diário do dia`.

### Task 5: As três rotas do contrato

**Files:**
- Create: `nexus/torres/campo/equipe_tela.py` (importado no fim de `nexus/torres/campo/__init__.py`, como o `cliente_tela`)
- Modify: `nexus/auth/__init__.py` (`ROTAS_PUBLICAS` += `torre_campo.equipe_aparelho`, `torre_campo.equipe_posicoes`, `torre_campo.equipe_revogar`)
- Create: `nexus/campo/equipe/servico.py` (o estado do processo: `Chaveiro`, `Diario`, último estado por pessoa, `permissao`; `do_app(app)` cria um por app em `app.extensions["nexus_equipe"]`)
- Test: `tests/test_equipe_rotas.py`

**Interfaces:**
- Consumes: Tasks 2 a 4.
- Produces: `POST /t/campo/equipe/aparelho` (CORS e `OPTIONS` só para a origem do App), `POST /t/campo/equipe/posicoes`, `POST /t/campo/equipe/aparelho/revogar`; `servico.do_app(app).estado_de(pessoa_id) -> dict` para a Task 7 (`{ultimo: dict | None, permissao: "ok" | "sem", desde: datetime}`).

- [ ] **Step 1: Write the failing tests** (token falso via monkeypatch de `token_ms.conferir`; `NEXUS_CHAVE_CADASTRO=gerar_chave()`; `NEXUS_DADOS` num `tmp_path`): `test_o_preflight_so_abre_para_a_origem_do_app` (OPTIONS com `Origin: https://gridco-campo-mw.azurewebsites.net` → 204 com `Access-Control-Allow-Origin` igual e `Allow-Headers` com Authorization e Content-Type; outra origem → sem o cabeçalho); `test_registro_do_tecnico_do_piloto_devolve_a_chave`; `test_registro_fora_do_piloto_devolve_coleta_false`; `test_token_invalido_e_401_e_microsoft_fora_e_503`; `test_posicoes_com_a_chave_gravam_e_respondem_aceitos` (`{aceitos: 2, coleta: true}`); `test_chave_revogada_ou_desconhecida_e_401`; `test_tecnico_que_saiu_do_piloto_recebe_coleta_false`; `test_lote_grande_ou_corpo_acima_de_64_kb_e_413`; `test_permissao_sem_fica_no_estado` (`{aparelho, fuso, pontos: [], permissao: "sem"}` → `estado_de(pid)["permissao"] == "sem"`); `test_revogar_e_204_sempre`; `test_as_rotas_publicas_nao_pedem_login_e_as_outras_sim` (entram em `ROTAS_PUBLICAS`; `tests/test_auth.py` segue verde).
- [ ] **Step 2: Run** `python -m pytest -q -p no:cacheprovider tests/test_equipe_rotas.py tests/test_auth.py` — Expected: FAIL.
- [ ] **Step 3: Implement**: sem `NEXUS_CHAVE_CADASTRO` ou sem `NEXUS_EQUIPE_MS_CLIENT_ID` as rotas respondem 503 com o texto do que falta (o servidor sem a chave não grava coordenada em claro); `request.max_content_length = 64 * 1024`; o e-mail do token vira pessoa por `pessoa_do_login`; a decisão do piloto vem do livro `nexus_equipe_piloto` (cache de 60 s).
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(equipe): as três rotas do contrato com o Nexus Field (registro, posições, revogação)`.

### Task 6: O gravador em lote e os deslocamentos

**Files:**
- Create: `nexus/campo/equipe/deslocamentos.py`, `nexus/campo/equipe/gravador.py`, `nexus/campo/equipe/acessos.py`
- Modify: `nexus/campo/__init__.py` (liga o gravador no boot onde `NEXUS_EQUIPE_GRAVA=1`, como a zeladoria)
- Test: `tests/test_equipe_deslocamentos.py`, `tests/test_equipe_gravador.py`

**Interfaces:**
- Consumes: Tasks 1, 3, 4; `campo.mapa_responsaveis.coordenadas() -> ({usina_id: (lat, lon, uf)}, erro)`.
- Produces: `deslocamentos(pontos: list[dict], usinas: dict, raio_km: float = RAIO_USINA_KM) -> list[list]` (linhas de `CAB_DESLOC`); `class Registro` em `acessos.py` com `acrescentar(acao: str, pessoa_id: int | None, pessoa_hmac: str, alvo_pessoa_id: int | None, usina_id: int | None, agora: datetime)` e `novos() -> list[list]` (linhas de `CAB_ACESSOS`); `class Gravador` com `rodada(agora)` (publica o livro do dia dos pontos, o do mês dos deslocamentos, os eventos de aparelho e os acessos; apaga o diário local velho).

- [ ] **Step 1: Write the failing tests:** `test_um_deslocamento_e_da_saida_de_uma_usina_a_chegada_na_outra` (pontos dentro de 1 km de A, depois no caminho, depois dentro de 1 km de B → 1 linha A→B com saída = último ponto em A, chegada = 1º em B, `duracao_min` e `distancia_km` pela soma dos trechos, haversine); `test_voltar_para_a_mesma_usina_nao_e_deslocamento`; `test_parado_fora_de_usina_nao_conta`; `test_o_gravador_publica_so_o_dia_que_mudou` (`ApiPGFalsa`: duas rodadas sem ponto novo = uma gravação); `test_o_gravador_nao_publica_dia_vazio_por_cima` (livro do dia com linhas no banco falso e diário vazio → nada gravado); `test_o_livro_do_dia_nao_tem_coordenada_em_claro`; `test_o_diario_local_com_mais_de_7_dias_some`.
- [ ] **Step 2: Run** `python -m pytest -q -p no:cacheprovider tests/test_equipe_deslocamentos.py tests/test_equipe_gravador.py` — Expected: FAIL.
- [ ] **Step 3: Implement**: rodada a cada 5 min numa thread com `fracttal_conta`-free (não lê o Fracttal); cada livro grava sozinho e o erro de um não para o outro (regra 13); o livro do dia relido antes de publicar só para a trava do "dia vazio".
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `feat(equipe): o gravador em lote (o livro do dia dos pontos e o do mês dos deslocamentos)`.

### Task 7: A tela Mapa de equipe e o Abrir rota

**Files:**
- Create: `nexus/campo/equipe/situacao.py`, `nexus/torres/campo/templates/campo/equipe.html`
- Modify: `nexus/torres/campo/equipe_tela.py` (rotas `GET /t/campo/equipe`, `GET /t/campo/equipe/rota`, `POST /t/campo/equipe/piloto`), `nexus/torres/campo/__init__.py` (`Tela("equipe", "Mapa de equipe", ..., do_setor=(SID.PCM, SID.COS, SID.PERFORMANCE, SID.SUPERVISAO_CAMPO, SID.RESPONSAVEL_UFV))` logo depois da Visão do cliente), `nexus/static/campo.css` (bloco `eq-*`)
- Test: `tests/test_equipe_situacao.py`, `tests/test_equipe_tela.py`

**Interfaces:**
- Consumes: `servico.do_app(app).estado_de`, `acessos.Registro.acrescentar`, `aparelhos.coleta_vale`, `mapa_responsaveis.coordenadas`, `performance.clima.mapa` (`vista_de_caixa`, `ufs_da_vista`, `estados`).
- Produces: `situacao(estado: dict, usinas: dict, agora_utc) -> dict` (`{chave, rotulo, tom, idade_min, usina_perto: (usina_id, km) | None, uf}`; chaves `deslocamento`, `na_usina`, `fora_usina`, `sem_sinal`, `sem_permissao`, `sem_posicao`), `url_da_rota(origem: tuple, destino: tuple) -> str` (`https://www.google.com/maps/dir/?api=1&origin=<lat>,<lon>&destination=<lat>,<lon>&travelmode=driving`).

- [ ] **Step 1: Write the failing tests:** situação: `test_a_situacao_de_cada_tecnico` (mov recente → deslocamento; parado a 0,8 km de uma usina → na_usina com "a 0,8 km da <usina>"; parado a 5 km → fora_usina com o estado e sem ponto; último ponto há 31 min → sem_sinal; `permissao: "sem"` → sem_permissao; ponto de 8 dias → sem_posicao); tela: `test_so_os_cinco_setores_e_o_admin_veem` (sessão de outro setor → 403 mesmo com o portão desligado); `test_a_pagina_e_o_json_nao_tem_coordenada` (nenhuma lat/lon do técnico nem da usina no HTML: procurar as strings das coordenadas de teste); `test_parado_fora_de_usina_sem_ponto_e_sem_rota` (não está no SVG; está no painel com o estado; sem link de rota); `test_abrir_rota_redireciona_para_o_google_e_registra_o_acesso` (302 para `https://www.google.com/maps/dir/?api=1&origin=...&destination=...`; para fora_usina → 404; `acessos` com `abriu_rota`); `test_abrir_o_mapa_registra_o_acesso`; `test_o_piloto_so_o_admin_muda` (POST de não admin → 403; admin marca um técnico → decisão no livro do piloto).
- [ ] **Step 2: Run** `python -m pytest -q -p no:cacheprovider tests/test_equipe_situacao.py tests/test_equipe_tela.py` — Expected: FAIL.
- [ ] **Step 3: Implement**: o SVG como o da Visão geral (`campo/responsaveis.html:511-544`): contorno dos estados, as usinas como marca discreta, o técnico como círculo `eq-p--<tom>` com o x/y já projetado no servidor; o painel ao lado com nome (decifrado do cadastro), equipe, hora da última posição (Brasília), usina perto e o botão Abrir rota (com a escolha da usina); a lista "sem posição hoje" e "parados fora de usina" no painel. O `!` com a explicação (`_explica.html`) diz o que é coletado, quem vê e a guarda.
- [ ] **Step 4: Run** a task e `tests/test_torre_campo.py tests/test_torres.py tests/test_prefixo.py` (a tela nova entra em `NOSSAS`) — Expected: PASS.
- [ ] **Step 5: Commit** `feat(campo): a tela Mapa de equipe na Usinas 360° com o Abrir rota pelo servidor`.

### Task 7b: A cidade pelo IBGE

**Files:**
- Create: `nexus/campo/equipe/municipios.py`
- Modify: `nexus/campo/equipe/situacao.py` (o `fora_usina` ganha `cidade`), `nexus/torres/campo/templates/campo/equipe.html` (o painel mostra "Cidade/UF")
- Test: `tests/test_equipe_municipios.py`

**Interfaces:**
- Consumes: `situacao(...)` da Task 7.
- Produces: `cidade(lat: float, lon: float, uf: str, *, pasta: Path | None, baixar=None) -> str | None` (o nome do município ou None; `baixar(url) -> dict` injeta a resposta no teste).

- [ ] **Step 1: Write the failing tests:** `test_acha_a_cidade_pelo_poligono` (malha falsa com dois municípios quadrados e os nomes → o ponto dentro do 2º devolve o nome dele); `test_fora_de_todos_devolve_none`; `test_a_malha_fica_no_disco_e_nao_baixa_de_novo` (2ª chamada não chama `baixar`; arquivo com mais de 30 dias baixa de novo); `test_ibge_fora_do_ar_nao_quebra_o_mapa` (`baixar` levanta → None e a situação segue com só o estado); `test_a_url_nunca_leva_a_coordenada` (as URLs pedidas não contêm a lat nem a lon do teste).
- [ ] **Step 2: Run** `python -m pytest -q -p no:cacheprovider tests/test_equipe_municipios.py` — Expected: FAIL.
- [ ] **Step 3: Implement** ponto no polígono (raio par-ímpar, com os buracos do GeoJSON), a malha por UF em `pasta_dados/equipe/ibge/<UF>.json`; o código do município da malha (`codarea`) casa com o `id` da lista de nomes.
- [ ] **Step 4: Run** a task e `tests/test_equipe_situacao.py tests/test_equipe_tela.py` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(equipe): a cidade do parado fora de usina pela API do IBGE, sem mandar a posição`.

### Task 8: A documentação, o pedido à T.I. e a prova

**Files:**
- Modify: `nexus/torres/campo/CLAUDE.md` (seção "Mapa de equipe"), `nexus/dados/CLAUDE.md` (os livros novos em "O que existe")
- Create: `docs/mapa-equipe-pedido-ti.md` (o texto para o Levi mandar à T.I.: apagar todo dia os livros `nexus_equipe_pontos_AAAA_MM_DD` com mais de 7 dias e todo mês os `nexus_equipe_deslocamentos_AAAA_MM` com mais de 12 meses, e garantir que cópia de segurança não guarde além disso)

- [ ] **Step 1:** Escrever as três peças (o que é, de onde vem o dado, as regras e o caso que as criou, como provar).
- [ ] **Step 2: Run** a suíte inteira `python -m pytest -q -p no:cacheprovider` — Expected: PASS (anotar o número).
- [ ] **Step 3:** Bancada só leitura com um técnico falso mandando um lote pelo `test_client` e o mapa a 1440 px e 375 px (sem rolagem de lado).
- [ ] **Step 4: Commit** `docs(equipe): o Mapa de equipe nos CLAUDE.md e o pedido de limpeza à T.I.`
