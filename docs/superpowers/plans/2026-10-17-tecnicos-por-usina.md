# Técnicos por usina — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** uma tela no PCM onde o PCM põe e tira técnicos de cada usina, gravada no banco do Nexus por ID, com o contrato e o pacote para o App de Campo passar a ler dali.

**Architecture:** um livro novo (`nexus_pcm_atribuicoes`, só acrescenta decisões, vale a última) no molde do `nexus/pcm/motivos.py`; um módulo de visão (`tecnicos_usina.py`) que junta o cadastro do banco, a evidência (rondas, fechamentos, programação) e a foto do App; rotas na torre PCM. O App é outro projeto: daqui sai o pacote `LEIA.md` (A1 a A3).

**Tech Stack:** Python 3 / Flask / Jinja, pytest (+ `tests/pg_falso.py`), a API `db_performace` (`nexus.dados.livros`), o Cofre (`nexus.cadastro.cifra`).

**Spec:** `docs/superpowers/specs/2026-10-17-tecnicos-por-usina-design.md`

## Global Constraints

- Ler antes: `nexus/dados/CLAUDE.md` (regras 1 a 13), `nexus/pcm/CLAUDE.md`, `nexus/casca/CLAUDE.md` (prefixo, tema).
- Repositório PÚBLICO: nenhum nome de colega em código, teste, doc ou commit; fixture com nome fictício ("Pessoa Teste").
- Banco: pessoa só como `pessoa_id` e `pessoa_hmac`; texto livre só cifrado (Cofre, `NEXUS_CHAVE_CADASTRO`); livro registrado em `catalogo.LIVROS` antes de existir; o radar com 0 tabelas novas.
- A tela lê só o banco (regra 12), nunca o armazém local do cadastro.
- Endereços com `{{ raiz }}`/`url_for`/`na_raiz` (`tests/test_prefixo.py`); cor só por token nos dois temas (`nexus/static/nexus.css`); pt-BR; sem emoji.
- Quem vê: setores "PCM" e "Responsáveis UFV" (`do_setor`). Quem edita: `telas.pode_programar()`. Carga inicial: só `session["admin"]`.
- Datas pelo dia de Brasília (`data_id` AAAAMMDD); `decidida_em` em UTC ISO `%Y-%m-%dT%H:%M:%SZ` (o mesmo `_iso` dos motivos).
- Nada muda no campo nesta entrega: o App só lê quando o Levi ligar o `NEXUS_ATRIBUICOES` dele.
- Trabalhar no worktree `C:/GridcoAuto/wt/nexus-pcm-rondas` (origin/main). Commit no worktree a cada tarefa; **push para a `main` só depois de o Levi ver a tela** (push = produção em ~2 min).

## Review Focus

1. **A virada do dia:** apoio com `ate_data_id` = hoje ainda vale; `de_data_id` = hoje já vale; decisão às 23:30 de Brasília (02:30Z) cai no dia de Brasília. Teste na Task 1.
2. **Banco fora na hora de gravar:** leitura que falha não grava nem apaga (Recusada com o motivo). Teste na Task 1.
3. **Pessoa sem e-mail ou Nexus sem `NEXUS_CHAVE_CADASTRO`:** a tela abre e avisa; a decisão grava com `pessoa_hmac` vazio e o aviso "o App não reconhece". Teste na Task 2.
4. **A mesma decisão duas vezes** (duas abas, clique duplo): não grava de novo ("Nada mudou"); tirar quem já não está = Recusada. Teste na Task 1.
5. **A usina mudou de nome no Fracttal** (o `de_para` mudou): a linha avisa e "Reenviar ao App" regrava as vigentes com o nome novo (origem `reemissao`). Teste na Task 2.

---

### Task 1: O livro e as regras (`nexus/pcm/atribuicoes.py`) e o catálogo

**Files:**
- Create: `nexus/pcm/atribuicoes.py`
- Modify: `nexus/dados/catalogo.py` (um `Fato`, um `Livro`, uma `Conhecida`), `nexus/dados/explica.py` (`RESUMO`, `PARA_QUE`)
- Test: `tests/test_pcm_atribuicoes.py`

**Interfaces:**
- Produces:
  - `LIVRO = "nexus_pcm_atribuicoes"`, `NOME_LIVRO = "Nexus · técnicos por usina (PCM)"`, `ABA = "fato_decisao_atribuicao"`
  - `CAB = ("decidida_em", "data_id", "usina_id", "usina_fracttal", "pessoa_id", "pessoa_hmac", "papel", "na_usina", "de_data_id", "ate_data_id", "origem", "decidida_por_hmac", "dados_cifrados", "assinatura")`
  - `PAPEIS = ("executa",)` (fase 3 acrescenta `"responsavel"`), `ORIGENS = ("tela", "carga_inicial", "reemissao")`, `OBS_MAX = 300`, `TTL_S = 60`, `ROTULO_CHAVE = b"nexus:pcm:atribuicoes"`
  - `class Recusada(ValueError)`
  - `ler(cfg, forcar: bool = False) -> dict` → `{"decisoes": [dict], "erro": str, "lido_em": float|None, "velha"?: bool}` (cache 60 s, igual ao `motivos.ler`)
  - `limpar() -> None`
  - `hoje_id() -> int` (dia de Brasília agora; usa `_agora()`, que os testes trocam)
  - `atuais(est: dict, hoje: int) -> dict[tuple[int, int, str], dict]` → chave `(usina_id, pessoa_id, papel)`; valor = a última decisão da chave com `status` `"vale"` ou `"agendado"` (de no futuro); tiradas e vencidas não entram
  - `assinatura(linha: dict, chave_base: str) -> str`
  - `decidir(cfg, *, usina_id: int, usina_fracttal: str, pessoa_id: int, pessoa_hmac: str, na_usina: bool, usuario: dict|None, de: str = "", ate: str = "", obs: str = "", origem: str = "tela", papel: str = "executa") -> dict` → `{"gravou": bool, "texto": str}`; `de`/`ate` em `AAAA-MM-DD` ou vazio
  - `decidir_varias(cfg, pedidos: list[dict], usuario, origem: str) -> int` (uma gravação só; cada pedido tem as chaves de `decidir`) — usado pela carga inicial e pela reemissão
  - `historico(cfg, est: dict, usina_id: int) -> list[dict]` → `{"quando", "pessoa_id", "acao" ("pôs" | "tirou"), "de", "ate", "origem", "quem_hmac", "obs"}`, do mais novo ao mais antigo, `obs` decifrada (vazia sem a chave)
- Consumes: `nexus.dados.livros` (`abas`, `_linhas`, `publicar`), `nexus.dados.fatos as D` (`_txt`, `_id`), `nexus.cadastro.cifra.Cofre`, `nexus.pcm.motivos._quem` e `motivos._banco` (reuso, não copiar).

- [ ] **Step 1: Escrever os testes que falham** em `tests/test_pcm_atribuicoes.py`, com a fixture `cfg` como a dos motivos (`TESTING`, `NEXUS_PCM_ATRIBUICOES_ARQUIVO` em `tmp_path`, `NEXUS_CHAVE_CADASTRO=gerar_chave()`, `NEXUS_PESSOA_HMAC="chave-hmac-de-teste"`) e um `Relogio` que troca `atribuicoes._agora`:
  - `test_vale_a_ultima_decisao_de_cada_usina_pessoa_papel`: pôr (1, 10), pôr (1, 11), tirar (1, 10) → `atuais(...)` tem só `(1, 11, "executa")`.
  - `test_apoio_vale_ate_o_ultimo_dia_e_agenda_o_futuro`: `ate="2026-10-17"` com hoje 20261017 → `status == "vale"`; com hoje 20261018 → fora; `de="2026-10-20"` com hoje 20261017 → `status == "agendado"`; `de` igual a hoje → `"vale"`.
  - `test_decisao_as_23h30_de_brasilia_e_do_dia_de_brasilia`: `_agora` = 2026-10-18T02:30Z → `data_id == 20261017`.
  - `test_mesma_decisao_nao_grava_de_novo`: pôr (1, 10) duas vezes → a 2ª devolve `gravou False` e o livro tem 1 linha; tirar (1, 11), que não está → `Recusada`.
  - `test_ate_antes_de_de_e_data_ruim_sao_recusadas`: `de="2026-10-20", ate="2026-10-19"` e `ate="20/10/2026"` → `Recusada`.
  - `test_leitura_que_falha_nao_grava`: `_ler_cru` levanta → `decidir` levanta `Recusada` e o arquivo não muda.
  - `test_nada_em_claro_no_livro`: com `obs="apoio nas férias do titular"` e usuário `{"email": "pessoa.teste@exemplo.com", "nome": "Pessoa Teste"}`, o JSON do livro não contém "férias", "Pessoa Teste" nem "@"; `historico` devolve a obs decifrada.
  - `test_assinatura_igual_a_do_contrato_com_o_app`: `assinatura({"usina_fracttal": "Cliente A - Usina 1 - SP", "pessoa_hmac": "0123456789abcdef01234567", "papel": "executa", "na_usina": "sim", "de_data_id": "", "ate_data_id": 20261031, "decidida_em": "2026-10-17T17:05:00Z"}, "chave-hmac-de-teste") == "e00727b720f3fbba3bfed36b8d90ac1e721cefe87908dd016e4f74df9b2ff750"`; sem chave → `""`.
  - `test_decidir_varias_grava_uma_vez`: 3 pedidos → 1 escrita do arquivo (conte as chamadas de `_gravar_cru` com monkeypatch) e 3 linhas.

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest -q tests/test_pcm_atribuicoes.py`
Expected: FAIL (`ModuleNotFoundError: nexus.pcm.atribuicoes`).

- [ ] **Step 3: Implementar `nexus/pcm/atribuicoes.py`** no molde do `motivos.py`: `_arquivo_local(cfg)` pela `NEXUS_PCM_ATRIBUICOES_ARQUIVO`; `_ler_cru`/`_gravar_cru` (uma aba; com `TESTING` e sem arquivo, vazio e nunca a rede; gravar no banco exige `GRIDCO_SQL_TOKEN` e usa `livros.publicar`); `_gravar(cfg, mudar)` com `_TRAVA`, relendo antes (leitura que falha = `Recusada`). A assinatura, exatamente:

```python
def assinatura(linha: dict, chave_base: str) -> str:
    base = (chave_base or "").strip()
    if not base:
        return ""
    chave = hmac.new(base.encode("utf-8"), ROTULO_CHAVE, hashlib.sha256).digest()
    txt = "|".join(("atribuicao", D._txt(linha.get("usina_fracttal")), D._txt(linha.get("pessoa_hmac")),
                    D._txt(linha.get("papel")), D._txt(linha.get("na_usina")), D._txt(linha.get("de_data_id")),
                    D._txt(linha.get("ate_data_id")), D._txt(linha.get("decidida_em"))))
    return hmac.new(chave, txt.encode("utf-8"), hashlib.sha256).hexdigest()
```

  A `obs` vai cifrada em `dados_cifrados` com o contexto `f"pcm/atribuicoes/{usina_id}/{pessoa_id}/{decidida_em}"` (JSON `{"obs": ...}`); sem `obs`, `dados_cifrados` vazio. "Mesma decisão" = mesma `na_usina`, `de_data_id` e `ate_data_id` da última decisão da chave (a obs sozinha não conta como mudança).

- [ ] **Step 4: Registrar no catálogo** (`nexus/dados/catalogo.py`), ao lado dos motivos:
  - `Fato("decisao_atribuicao_pcm", "Técnicos por usina", "pcm", "nexus_pcm_atribuicoes · fato_decisao_atribuicao", "1 linha = 1 decisão de pôr ou tirar 1 pessoa de 1 usina num papel (executa); vale a última decisão de cada usina, pessoa e papel", _d(data=("id", "data_id (o dia de Brasília da decisão)"), usina=("id", "usina_id (+ usina_fracttal, o nome do Fracttal que o App usa)"), pessoa=("id", "pessoa_id + pessoa_hmac (o código do e-mail, que o App usa) e decidida_por_hmac")), tipo="sem_medida", chave=("decidida_em", "usina_id", "pessoa_id", "papel"), fontes=("nexus_pcm_atribuicoes · fato_decisao_atribuicao",), janela_origem="o Nexus é a fonte (só acrescenta)", observacao=...)` — a observação diz: o App lê este livro e aplica o `executa` vigente (com o interruptor dele), cada linha assinada; `de_data_id`/`ate_data_id` fazem o apoio; a obs só cifrada.
  - `Livro("nexus_pcm_atribuicoes", ("fato_decisao_atribuicao",), "a cada decisão na tela Técnicos por usina", "nexus/pcm/atribuicoes.py, pela tela Técnicos por usina do PCM", False, "registrado em 17/10/2026 antes de existir: nasce com a 1ª decisão ou com a carga inicial")`.
  - `Conhecida("organizacao_app_campo", ("Atribuicoes",), "apoio", "a foto das atribuições do App de Campo (usina × pessoa em HMAC × papel), publicada pelo App para o PCM comparar antes de o App passar a ler o nexus_pcm_atribuicoes; sai quando a troca estiver feita")`.
  - Em `explica.py`: `RESUMO["decisao_atribuicao_pcm"] = "Quem cobre cada usina: os técnicos que o PCM põe e tira, fixos ou de apoio"` e o `PARA_QUE` em 2 a 3 frases (o que guarda, de onde vem, quem lê: o App de Campo, para a aba Ronda).

- [ ] **Step 5: Rodar os testes do livro e do catálogo**

Run: `python -m pytest -q tests/test_pcm_atribuicoes.py tests/test_dados_camada.py tests/test_dados_organograma.py`
Expected: PASS.

- [ ] **Step 6: Mutação** — estragar, um de cada vez, e ver o teste falhar: `>=` do `ate` virar `>`; o rótulo da chave; o `_BRT` do `data_id`; a comparação de "mesma decisão". Desfazer.

- [ ] **Step 7: Commit**

```bash
git add nexus/pcm/atribuicoes.py nexus/dados/catalogo.py nexus/dados/explica.py tests/test_pcm_atribuicoes.py
git commit -m "feat(pcm): o livro dos tecnicos por usina (nexus_pcm_atribuicoes) - decisoes que so acrescentam, apoio com datas, assinatura para o App"
```

### Task 2: A visão da tela (`nexus/pcm/tecnicos_usina.py`)

**Files:**
- Create: `nexus/pcm/tecnicos_usina.py`
- Test: `tests/test_pcm_tecnicos_usina.py`

**Interfaces:**
- Consumes: Task 1 (`ler`, `atuais`, `hoje_id`, `decidir_varias`); `nexus.campo.visao._Base` (usinas, equipes, de_para, pessoas, regiao, regiao_da_equipe, nomes) e `visao._livro` (cache de 2 min), `visao.CAMPO`; `nexus.campo.ligacao_cadastro.codigo_da_pessoa` e `_norm`; `nexus.cadastro.cifra.Cofre`.
- Produces:
  - `FILTROS = ("equipe", "regiao", "responsavel", "situacao", "q")`; `SITUACOES = (("sem_tecnico", "Sem técnico"), ("com_aviso", "Com aviso"))`
  - `EVIDENCIA_DIAS = 30`
  - `montar(cfg, args, hoje: int | None = None) -> dict` → o contexto da tela: `{"ver": "usina"|"tecnico", "linhas": [...], "tecnicos": [...], "pedido": {...}, "opcoes": {...}, "pessoas_json": [...], "app": {"existe": bool, "so_no_app": [...], "so_no_nexus": [...], "pendencias": [...]}, "livro_vazio": bool, "erro": str, "avisos_gerais": [...]}`
  - Linha por usina: `{"usina_id", "nome", "equipe", "regiao", "responsavel", "fracttal": str ("" = sem de_para), "fracttal_mudou": bool, "tecnicos": [{"pessoa_id", "nome", "status" ("vale"|"agendado"), "de", "ate", "sem_email": bool}], "evidencia": [{"pessoa_id", "nome", "rondas", "fechamentos", "na_programacao": bool, "do_cadastro": bool}], "avisos": [str]}`
  - `pessoas_de_campo(base, cfg) -> dict[int, dict]` → `{pessoa_id: {"nome", "equipe_id", "cargo", "hmac"}}` (vínculo `visao.CAMPO`, não desligado, não excluído; nome e e-mail decifrados uma vez; `hmac` vazio sem e-mail ou sem chave)
  - `pedidos_da_carga_inicial(base, pessoas) -> list[dict]` (a regra da equipe: cada pessoa de campo × cada usina não excluída com o mesmo `equipe_id`)
  - `pedidos_da_reemissao(base, pessoas, est, usina_id, hoje) -> list[dict]` (as vigentes da usina com o `usina_fracttal` atual)
  - `historico_da_usina(cfg, base, pessoas, usina_id) -> list[dict]` (o `atribuicoes.historico` com o nome de quem e de quem decidiu, pelo HMAC)

- [ ] **Step 1: Escrever os testes que falham** em `tests/test_pcm_tecnicos_usina.py`, com `ApiPGFalsa` em `app.extensions["nexus_dados_sessao"]` (o molde do `test_campo_visao.py`, função `_aba`), cadastro fictício (3 usinas: duas da equipe 10, uma da 20; pessoas de campo 10, 11 na equipe 10, 12 na 20, 13 sem e-mail; `de_para` "Fracttal · Classificação 1" para as usinas 1 e 2), `fato_ronda` com a pessoa 12 rondando a usina 1 há 5 dias e `fato_programacao` com a pessoa 10 na semana em curso:
  - `test_carga_inicial_e_a_regra_da_equipe`: `pedidos_da_carga_inicial` dá (1,10), (1,11), (2,10), (2,11), (3,12) e nenhum par de equipe diferente.
  - `test_linha_mostra_tecnicos_evidencia_e_avisos`: com (1,10) e (1,13) gravados, a linha da usina 1 tem os dois técnicos, a 13 com `sem_email`, a evidência da 12 (1 ronda) com o aviso "rondou aqui e não está na lista", e a usina 3 com os avisos "sem técnico" e "sem nome do Fracttal".
  - `test_filtros_em_cascata`: com `equipe=10`, a opção de `regiao` só lista a região da equipe 10; a equipe escolhida continua na lista mesmo sem resultado; `situacao=sem_tecnico` só traz usina sem vigente; `q` busca no nome da usina e do técnico, sem acento.
  - `test_visao_por_tecnico`: `ver=tecnico` dá uma linha por pessoa de campo com as usinas vigentes e a contagem.
  - `test_sem_chave_do_cadastro_a_tela_abre_e_avisa`: sem `NEXUS_CHAVE_CADASTRO`, `montar` não quebra, os nomes viram "Pessoa <id>" e `avisos_gerais` diz que falta a chave.
  - `test_usina_que_mudou_de_nome_no_fracttal`: gravada com `usina_fracttal` "Nome Antigo", o `de_para` atual diz outro → `fracttal_mudou` e `pedidos_da_reemissao` refaz com o nome novo.
  - `test_comparacao_com_a_foto_do_app`: sem o livro `organizacao_app_campo`, `app["existe"] is False`; com ele (colunas `Usina`, `Pessoa (HMAC)`, `Papel`, `De`, `Ate`, `Origem`), um par só no App, um só no Nexus, uma pessoa cujo HMAC não casa com ficha nenhuma e uma usina sem `de_para` → caem em `so_no_app`, `so_no_nexus` e `pendencias` (2), e o papel `responsavel` do App é ignorado.

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest -q tests/test_pcm_tecnicos_usina.py`
Expected: FAIL (módulo não existe).

- [ ] **Step 3: Implementar `nexus/pcm/tecnicos_usina.py`**. Usinas da lista = as não excluídas do cadastro; o filtro `situacao` não restringe a si mesmo e a cascata segue o `_filtrar` do Fora da programação (`telas.FILTROS_FORA`): cada filtro lista o que existe com os OUTROS aplicados. A evidência: `fato_ronda` e `fato_fechamento` (`nexus_fatos`) com `data_id >= hoje - 30 dias`, contados por (`usina_id`, `pessoa_id`); `fato_programacao` (`nexus_programacao`) com `data_id_semana` = a segunda da semana de hoje, pela `pessoa_id_tecnico`; o "do cadastro" = `tecnico_om_id` da usina. A região = `base.regiao[base.regiao_da_equipe[equipe_id]]["nome"]`; o responsável = o nome do `responsavel_om_id`. O nome do Fracttal = a `chave_externa` do `de_para` com sistema `ligacao_cadastro.SISTEMA_FRACTTAL` (se houver mais de uma para a usina, a primeira em ordem alfabética e o aviso "duas grafias no Fracttal"). A foto do App casa a usina pelo `_norm` do nome com o `de_para` e a pessoa pelo `pessoa_hmac`. `pessoas_json` leva só `{id, nome, equipe_id}` (o e-mail nunca vai à página).

- [ ] **Step 4: Rodar os testes**

Run: `python -m pytest -q tests/test_pcm_tecnicos_usina.py tests/test_pcm_atribuicoes.py`
Expected: PASS.

- [ ] **Step 5: Mutação** — a regra da equipe com a equipe errada; a janela de 30 dias; o filtro que restringe a si mesmo; o HMAC que casa por e-mail em vez de código. Ver falhar e desfazer.

- [ ] **Step 6: Commit**

```bash
git add nexus/pcm/tecnicos_usina.py tests/test_pcm_tecnicos_usina.py
git commit -m "feat(pcm): a visao dos tecnicos por usina - cadastro do banco, evidencia de rondas, fechamentos e programacao, avisos, filtros em cascata e a comparacao com a foto do App"
```

### Task 3: A tela, as rotas e o menu

**Files:**
- Modify: `nexus/pcm/telas.py` (rotas dentro de `registrar_pcm`), `nexus/torres/pcm/__init__.py` (a `Tela`), `nexus/static/pcm.css`
- Create: `nexus/templates/pcm/tecnicos.html`, `nexus/templates/pcm/_tecnicos_historico.html`, `nexus/static/pcm-tecnicos.js`
- Test: `tests/test_pcm_tecnicos_tela.py`

**Interfaces:**
- Consumes: Task 1 (`decidir`, `decidir_varias`, `ler`, `Recusada`), Task 2 (`montar`, `pessoas_de_campo`, `pedidos_da_carga_inicial`, `pedidos_da_reemissao`, `historico_da_usina`, `FILTROS`), `telas.pode_programar`, `telas._de_outro_site`, `telas._usuario`, `na_raiz`.
- Produces (rotas):
  - `GET /t/pcm/tecnicos-por-usina` (`?ver=usina|tecnico` + filtros) → `pcm/tecnicos.html`
  - `POST /t/pcm/tecnicos-por-usina/decidir` (form: `usina_id`, `pessoa_id`, `acao` = `por` | `tirar` | `reemitir`, `de`, `ate`, `obs`, `v_<filtro>`) → 303 de volta, filtrada; aviso em `session["pcm_tecnicos_aviso"]`
  - `POST /t/pcm/tecnicos-por-usina/carga-inicial` → só `session["admin"]` e só com o livro vazio
  - `GET /t/pcm/tecnicos-por-usina/historico?usina=<id>` → o parcial `_tecnicos_historico.html` (fetch)
  - Menu: `Tela("tecnicos-por-usina", "Técnicos por usina", "Quem cobre cada usina, e quem pode rondar ali no App?", "O cadastro do Nexus, as rondas e a programação; as decisões do PCM nesta tela", do_setor=("PCM", "Responsáveis UFV"))`, depois do "Fora da programação".

- [ ] **Step 1: Escrever os testes que falham** em `tests/test_pcm_tecnicos_tela.py` (o banco falso da Task 2, as fixtures `app` e `logado` da casa, `_no_setor`/`_pessoa` de `test_pcm_publicar`):
  - `test_quem_ve_e_quem_edita`: setor Responsáveis UFV → GET 200 e POST `decidir` 403; setor PCM → POST 303 e grava; outro setor → GET não abre (o mesmo que a casa faz com o Quadro para outro setor: conferir no `tests/test_pcm_motivos.py::test_quem_marca_e_quem_mexe_no_cadastro`); carga inicial com setor PCM sem admin → 403.
  - `test_por_e_tirar_volta_filtrado`: POST `acao=por` com `v_equipe=10` → `Location` termina em `/t/pcm/tecnicos-por-usina?equipe=10` (com `na_raiz`) e o livro tem a decisão; `acao=tirar` tira.
  - `test_carga_inicial_so_com_livro_vazio`: admin → grava a regra da equipe (origem `carga_inicial`); 2ª vez → aviso "o livro já tem decisões" e nada grava.
  - `test_reemitir_regrava_com_o_nome_novo`: o caso da Task 2 pela rota.
  - `test_pagina_sem_email_nem_nome_de_colega`: o HTML não tem "@" nem o nome decifrado de quem decidiu fora do que a tela mostra de propósito; `pessoas_json` só com `id`, `nome`, `equipe_id`.
  - `test_historico_da_usina`: GET `historico?usina=1` devolve as decisões do mais novo ao mais antigo, com a observação.
  - Acrescentar a rota nova à lista do `tests/test_prefixo.py` se ele listar as rotas do PCM à mão.

- [ ] **Step 2: Rodar e ver falhar**

Run: `python -m pytest -q tests/test_pcm_tecnicos_tela.py`
Expected: FAIL (404 nas rotas).

- [ ] **Step 3: Implementar as rotas e o template.** A página é a do Fora da programação no desenho (cabeçalho, filtros em cascata no alto, tabela), com a alternância "Por usina | Por técnico". Na linha da usina: os técnicos como selos (o apoio com "até dd/mm", o agendado com "a partir de dd/mm", × para tirar quando `pode_programar`), a evidência em texto discreto, os avisos em âmbar (palavra e cor, sem ícone de emoji), "Histórico" que abre o parcial por fetch e "Reenviar ao App" quando `fracttal_mudou`. "Pôr técnico" abre UMA janela compartilhada (`<dialog>`) preenchida pelo `pcm-tecnicos.js` com a lista do `pessoas_json`: no alto as da evidência daquela usina (com a conta), depois as da mesma equipe, depois as outras, com busca; os campos de/até (`type=date`) e a observação. O bloco "Comparação com o App" só aparece quando `app.existe`: só no App, só no Nexus, pendências para a troca. Sem `pode_programar`, nada de botão de edição. O botão "Carga inicial pela equipe" só para admin com o livro vazio, com confirmação que diz quantas ligações vão nascer.

- [ ] **Step 4: Rodar os testes da tela e o recorte do PCM**

Run: `python -m pytest -q tests/test_pcm_tecnicos_tela.py tests/test_prefixo.py tests/test_sem_nomes_no_repositorio.py -k "tecnicos or prefixo or nomes"` e depois `python -m pytest -q -k "pcm or relatorios_central or chaves or dados"`
Expected: PASS.

- [ ] **Step 5: Ver a tela.** Renderizar com o banco falso dos testes para um HTML, servir a pasta com o `static/` ao lado (`.claude/launch.json`) e conferir no navegador do app a 1366 px e a 375 px, nos temas escuro e claro: a tabela cabe sem rolagem horizontal a 1366, a janela de pôr técnico abre e filtra, os avisos legíveis nos dois temas.

- [ ] **Step 6: Commit**

```bash
git add nexus/pcm/telas.py nexus/torres/pcm/__init__.py nexus/static/pcm.css nexus/static/pcm-tecnicos.js nexus/templates/pcm/tecnicos.html nexus/templates/pcm/_tecnicos_historico.html tests/test_pcm_tecnicos_tela.py
git commit -m "feat(pcm): a tela Tecnicos por usina - o PCM poe e tira tecnicos (fixo ou apoio com datas), com a evidencia de campo, os avisos, o historico e a carga inicial pela equipe"
```

### Task 4: O pacote do App (A1 a A3)

**Files:**
- Create: `C:\GridcoBuild\app-campo-docs\_propostas\atribuicoes-nexus\LEIA.md` (fora do repositório; no formato do `ranking-pontos-nexus\LEIA.md`)

**Interfaces:**
- Consumes: o contrato da Task 1 (`CAB`, `assinatura`, o vetor de teste).

- [ ] **Step 1: Ler o pacote anterior** (`C:\GridcoBuild\app-campo-docs\_propostas\ranking-pontos-nexus\LEIA.md`) e o bloco do `nexus_pt_decisoes` no `function_app.py` da v282 (l. ~31760–32100), para escrever no idioma do App.
- [ ] **Step 2: Escrever o `LEIA.md`** com: o porquê (seção 1 do desenho, sem nomes); **A1** — o livro `organizacao_app_campo`, aba `Atribuicoes`, colunas `Usina` (nome do catálogo), `Pessoa (HMAC)` (`_pessoa_hmac` do e-mail), `Papel`, `De`, `Ate`, `Origem`, as linhas vigentes da tabela `atribuicoes` (`ate` vazio), publicado com os outros livros no timer aos :25; **A2** — o timer que lê `nexus_pcm_atribuicoes · fato_decisao_atribuicao` como o `_nexus_pt_ler` (lista de livros pelo `updated_at`, releitura de 10 min), confere a assinatura (a função em Python igual à da Task 1, com o vetor `e00727b7...f750` como teste), calcula o vigente (última por usina × pessoa × papel, `na_usina = sim`, de/até no dia de Brasília), reverte o HMAC pelos e-mails conhecidos (como o `_nexus_pt_nome`), casa a usina pelo `_casar_usina` e SUBSTITUI o `executa` (grava com origem `nexus`, encerra com `ate` o que o Nexus não tem); interruptor `NEXUS_ATRIBUICOES` (ausente = desligado) e o `/health` com a última passada (só números); **A3** — com o interruptor ligado, `gestao/organizacao` recusa `executa_add`/`executa_del` com "editado no Nexus (PCM → Técnicos por usina)" e o `espelhar_bd_operacoes.py` não toca no `executa`; a ordem de ligar (A1 no ar → o PCM zera as pendências na tela do Nexus → A2 e A3 com o interruptor desligado → o Levi liga).
- [ ] **Step 3: Conferir** que o `LEIA.md` não tem nome de pessoa nem e-mail (busca por "@" e pelos nomes do cadastro, como o `test_sem_nomes_no_repositorio` faz).

### Task 5: Documentação e fechamento

**Files:**
- Modify: `nexus/pcm/CLAUDE.md` (módulos `atribuicoes.py` e `tecnicos_usina.py`; seção nova "Técnicos por usina (17/10/2026)"; o menu), `nexus/dados/CLAUDE.md` (linha "Técnicos por usina" em "O que existe" e o total de `LIVROS`), `CLAUDE.md` da raiz (a linha do PCM na tabela de áreas cita a tela)

- [ ] **Step 1: Escrever a seção do `nexus/pcm/CLAUDE.md`**: para que serve (as frases do Levi de 17/10), o que `executa` quer dizer no App, a regra da equipe da carga inicial, quem vê e quem edita, o apoio com datas, o contrato com o App (assinatura, colunas, o interruptor) e as fases; como provar (os três arquivos de teste e a tela). Regra que já existe e mudou se corrige, não se empilha.
- [ ] **Step 2: Rodar a suíte inteira**

Run: `python -m pytest -q`
Expected: PASS (mais de 3.300 testes).

- [ ] **Step 3: Commit**

```bash
git add nexus/pcm/CLAUDE.md nexus/dados/CLAUDE.md CLAUDE.md docs/superpowers/specs/2026-10-17-tecnicos-por-usina-design.md docs/superpowers/plans/2026-10-17-tecnicos-por-usina.md
git commit -m "docs(pcm): os tecnicos por usina - a tela, o livro, o contrato com o App e as fases"
```

- [ ] **Step 4: Mostrar ao Levi** a tela (prints a 1366 e 375 px) e o pacote do App, e só então perguntar se sobe (push na `main` = produção).
