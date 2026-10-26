# ETMs na Engenharia (1ª parte) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a tela ETMs na torre Engenharia (o Planner do app de ETM), a OS da ETM na página da OS da Engenharia com o
painel das marcações, o livro das marcações e a importação única do histórico do app.

**Architecture:** leitura das OS de ETM no Fracttal pelo leitor do Nexus (15 pedidos, cópia de 5 min relida por trás,
como o `os_equipe`); as marcações num livro novo do banco (`nexus_engenharia_etm`, catálogo antes da 1ª gravação); os
comentários no livro e na nota da OS que a Engenharia já usa; a importação na ponte do OS Creator (as duas sessões).

**Tech Stack:** Flask/Jinja, o leitor `nexus.campo.fracttal`, `nexus.dados.livros`, o Cofre, JS puro.

**Spec:** `docs/superpowers/specs/2026-10-26-engenharia-etm-design.md`

## Global Constraints

- pt-BR em tudo, sem emoji; cor só por token (`nexus.css`, os dois temas); endereços pela raiz (`url_for`, `|na_raiz`,
  `nexusRota`).
- Nenhum nome de pessoa no código, nos testes nem nos `.md` (repositório público): a equipe vem de
  `NEXUS_ENGENHARIA_RESPONSAVEIS`; o repositório e o token do GitHub de `NEXUS_ETM_GITHUB_REPO` e `NEXUS_ETM_GITHUB_TOKEN`.
- Dado novo no banco só com o livro no catálogo (`Fato` + `Livro`, `so_cresce`) e o `explica` (RESUMO 15 a 70 letras,
  PARA_QUE de 80 ou mais terminando em ponto); quem fez e texto só cifrados; a pessoa pelo `pessoa_hmac`.
- O Nexus não escreve no Fracttal pelo leitor REST; a nota da OS só pela ponte do OS Creator, na sessão da pessoa.
- Nada de rede nos testes (Fracttal, banco e GitHub falsos).

## Review Focus

- A leitura do Fracttal pela metade (429 numa página): a tela mostra a última leitura boa e diz, nunca um quadro parcial.
- OS de várias tarefas e OS com tarefa de ativo que não é ETM: uma OS só, e só se o código for de ETM.
- O livro relido vazio com o livro existente: leitura incompleta, não "sem marcação" (a mesma trava do `os_acompanhamento`).
- Importar duas vezes: nada se repete (a chave é o id do comentário e da issue no GitHub).
- A nota da OS na importação: só nas OS abertas, numa escrita por OS, com as travas do comentário da Engenharia.

---

### Task 1: A leitura das OS de ETM

**Files:**
- Create: `nexus/engenharia/etm.py`
- Test: `tests/test_engenharia_etm.py`

**Interfaces:**
- Consumes: `os_equipe._cartao(folio, ts, pessoa, hoje)`, `os_equipe.coluna`, `os_equipe.nomes(config)`, `os_equipe._norm`.
- Produces: `ETM = "Estação Meteorológica"`; `cliente_de(usina) -> str`; `coluna_etm(coluna) -> str` ("nao_iniciada",
  "em_andamento", "finalizada", "cancelada"); `montar(linhas, codigos_etm: set, equipe: list[str], hoje) -> list[dict]`
  (o cartão do `os_equipe` mais `coluna_etm`, `trabalho` "analise"|"campo", `cliente`, `responsavel`, `criado_por`);
  `dados() -> {"os", "lido", "lendo", "erro"}`; `pedir_releitura(app=None, esperar=False, forcar=False)`;
  `marcar_uso()`; `manter_quente(app)`; `limpar()`; `eh_etm(codigo) -> bool | None` (None sem leitura).

- [ ] Testes: quem entra (Corretiva e Administrativa de ETM; Preventiva só com responsável ou solicitante da equipe;
  código fora das ETMs nunca), Análise × Campo, a coluna, uma OS por nº, `cliente_de`, os dois caminhos lidos
  (`items?field_1=` e `work_orders?items_log_description=`) e a leitura que falha guardando a anterior.
- [ ] Rodar e ver falhar; implementar; rodar e ver passar; commit.

### Task 2: O livro das marcações

**Files:**
- Create: `nexus/engenharia/etm_marcas.py`
- Modify: `nexus/dados/catalogo.py` (Fato `marcacao_etm`, Livro `nexus_engenharia_etm`), `nexus/dados/explica.py`
- Test: `tests/test_engenharia_etm.py`

**Interfaces:**
- Produces: `LIVRO = "nexus_engenharia_etm"`; `ABA = "fato_marcacao_etm"`; `DIAGNOSTICOS`, `STATUS_POS`, `ETIQUETAS`
  (tuplas (id, nome), ids nunca reaproveitados); `EVENTOS = ("diagnostico", "status_pos", "etiqueta", "acompanhamento",
  "finalizado")`; `ler(forcar=False) -> {"eventos", "lido_em", "erro"}`; `estado(eventos) -> {wid: {"diagnostico_id",
  "status_pos_id", "etiquetas": set, "acompanhamento": bool, "finalizado": bool, "ultima": datetime|None}}`;
  `marcar(os_, evento, valor, usuario, pode) -> dict` (diagnóstico e status pós: id, 0 limpa; etiqueta: (id, ligado);
  acompanhamento e finalizado: bool); `Recusada`.
- CAB: id, registrado_em, data_id, evento, os_id, os_folio, codigo_ativo, equipamento_id, usina_id, usina_ligada_por,
  pessoa_hmac, valor_id, ligado, origem, origem_id, dados_cifrados.

- [ ] Testes: o catálogo e o explica; uma marcação vira um evento com quem cifrado; o estado (o último vale, etiqueta
  liga e desliga, 0 limpa); recusas (fora da Engenharia, valor fora da lista, OS sem id do Fracttal); o livro existente
  relido sem a aba é leitura incompleta.
- [ ] Rodar e ver falhar; implementar; rodar e ver passar; commit.

### Task 3: A tela ETMs (o Planner)

**Files:**
- Modify: `nexus/torres/engenharia/__init__.py` (a `Tela("etm", "ETMs", ...)`, a rota `/etm`)
- Create: `nexus/torres/engenharia/templates/engenharia/etm.html`
- Modify: `nexus/static/engenharia.css` (classes `etm-*`, só tokens)
- Test: `tests/test_engenharia_etm.py`

**Interfaces:**
- Consumes: `etm.dados()`, `etm.pedir_releitura`, `etm.marcar_uso`, `etm_marcas.ler/estado`.
- Produces: a página `/t/engenharia/etm` com o JSON `#etm-dados` ({"oss", "hoje"}); cada OS com `diagnostico`,
  `status_pos`, `etiquetas_eng`, `acompanhamento`, `finalizado`; o clique abre `/t/engenharia/etm/os/<nº>`.

- [ ] Testes: a tela na torre; as colunas Não iniciadas, Em andamento, Finalizadas (Canceladas pelo filtro); os filtros
  do app (cliente, usina, criado por, solicitante, responsável, Análise/Campo, período, canceladas); a faixa de números;
  sem o livro, a tela diz e não chuta marcação; `?atualizar=1` relê.
- [ ] Rodar e ver falhar; implementar; rodar e ver passar; commit.

### Task 4: A OS da ETM

**Files:**
- Modify: `nexus/torres/engenharia/__init__.py` (rotas `/etm/os/<int:folio>` e `/etm/os/<int:folio>/marcar`)
- Modify: `nexus/torres/engenharia/templates/engenharia/os_quadro.html` (o painel da ETM no lugar de Status e
  prioridade; o bloco "Checklist da OS"; a volta para ETMs)
- Test: `tests/test_engenharia_etm.py`

**Interfaces:**
- Consumes: `os_equipe.ler_os`, `os_equipe._paginas_ate("work_orders_subtasks/?folio=")`, `etm_marcas.marcar`, o
  `comentar_url` da ponte (o mesmo da OS do Quadro).
- Produces: a página com `etm` no contexto (as listas, o estado, o checklist); o POST grava e volta com `?ok=`/`?erro=`.

- [ ] Testes: o painel (diagnóstico, status pós-OS, etiquetas, acompanhamento, finalizado) só para a Engenharia; gravar
  cada marcação; o checklist com as respostas; os comentários e a nota da OS iguais aos do Quadro; a volta para ETMs; a
  OS que não é de ETM abre a página comum.
- [ ] Rodar e ver falhar; implementar; rodar e ver passar; commit.

### Task 5: O histórico do app (uma vez)

**Files:**
- Create: `nexus/engenharia/etm_historico.py`
- Modify: `nexus/torres/oscreator/ponte.py` (rota `/os/_nexus/engenharia/etm/historico`, GET prévia e POST importar,
  só administrador), `nexus/engenharia/os_acompanhamento.py` (comentário importado: `origem`, `origem_id`, o autor e a
  data originais), `nexus/torres/engenharia/templates/engenharia/etm.html` (o painel do administrador)
- Test: `tests/test_engenharia_etm_historico.py`

**Interfaces:**
- Produces: `ler_github(token, repo, get) -> {folio: {"comentarios": [{"id", "autor", "texto", "data"}], "labels": set,
  "datas_labels": {label: data}}}`; `previa(gh, abertas: set) -> {"comentarios", "oss", "abertas_com_nota"}`;
  `importar(gh, ...)`.

- [ ] Testes: o corpo `**Autor:**\ntexto` vira autor e texto; a prévia; importar grava comentários e marcações; de novo
  não repete; a nota só nas abertas, uma escrita por OS, do mais antigo ao mais novo; sem o token, o painel diz o que falta.
- [ ] Rodar e ver falhar; implementar; rodar e ver passar; commit.

### Task 6: Documentação, prova e revisão

- [ ] `nexus/torres/engenharia/CLAUDE.md` (a tela ETMs, o livro, a importação), `nexus/dados/CLAUDE.md` se a regra pedir,
  a tabela do `CLAUDE.md` da raiz.
- [ ] Prova na cópia de prova (desktop e 375 px, escuro e claro); suíte inteira; revisão do ramo inteiro.
