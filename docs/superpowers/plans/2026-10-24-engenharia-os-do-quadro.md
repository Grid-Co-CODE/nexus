# A OS do Quadro da equipe — plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (inline) to implement this plan task-by-task.

**Goal:** o clique numa OS do Quadro da equipe abre a página da OS da engenharia (status, prioridade, comentários na nota
do Fracttal, OS filhas com a resposta do técnico, Solicitar OS com a OS pai) e o quadro pulsa as OS paradas há 7 dias.

**Architecture:** página Nexus na torre Engenharia, livro novo no banco (`nexus_engenharia_os`) no molde do
`acompanhamento.py`, o comentário pela ponte do OS Creator (sessão do Fracttal da pessoa), a Nova solicitação do clone
aceitando a sugestão por endereço.

**Tech Stack:** Flask, Jinja, JS sem framework, o banco falso `tests/pg_falso.py`, o Fracttal falso por monkeypatch.

**Spec:** `docs/superpowers/specs/2026-10-24-engenharia-os-do-quadro-design.md`

## Global Constraints

- pt-BR em tudo; sem emoji; cor só por token nos dois temas (`test_tema`); endereço nunca da raiz (`url_for`,
  `nexusRota`); nome de colega nunca em arquivo versionado (fixtures fictícias); `.env` na worktree para o
  `test_sem_nomes`.
- Livro registrado no catálogo antes de existir (regra 10), `so_cresce=True`; pessoa só como HMAC, texto e nome cifrados.
- Nada escreve no Fracttal além da nota pelo `api.editar_nota_os` do clone, na sessão da pessoa.
- O clone não importa `nexus`: o que é só do Nexus vai na `ponte.py`.
- Commit/push e a ida ao oem só com o OK do Levi.

## Review Focus

- Comentário com a nota mudada por outra pessoa entre a leitura e a escrita: a escrita relê a nota na hora e acrescenta.
- OS de várias tarefas, concluída ou cancelada: o comentário não vai à nota e a tela diz por quê; nada some.
- Sessão do Fracttal vencida no meio: a resposta pede o login, nada gravado no Nexus.
- O quadro com o livro fora: os cartões aparecem sem status e sem pulso (nunca um "parada" chutado).
- A Nova solicitação aberta sem sugestão segue igual (o oem usa a mesma página).

---

### Task 1: o livro e as regras (`nexus/engenharia/os_acompanhamento.py`)

**Files:** Create `nexus/engenharia/os_acompanhamento.py`; Modify `nexus/dados/catalogo.py`, `nexus/dados/explica.py`;
Test `tests/test_engenharia_os_quadro.py`.

**Interfaces — Produces:**
- `LIVRO = "nexus_engenharia_os"`, `ABA = "fato_acompanhamento_os"`, `ABA_STATUS = "dim_status_os"`,
  `ABA_PRIORIDADE = "dim_prioridade_os"`; `STATUS: tuple[(id, nome)]` (os 8, ids 1..8 na ordem do anexo);
  `PRIORIDADES = ((1, "Média"), (2, "Alta"), (3, "Urgente"))`; `DIAS_PARADA = 7`.
- `ler(forcar=False) -> {"eventos", "lido_em", "erro", "velha"?}` (cópia de 60 s, a última boa quando o banco cai).
- `estado(eventos) -> {os_id(str): {"status_id", "prioridade_id", "ultimo"(datetime), "eventos":[...] (o mais novo
  primeiro: {"evento","quando","quando_txt","nome","texto","status_id","prioridade_id","nota"}) }}`.
- `classificar(os: dict, status_id, prioridade_id, usuario, pode) -> dict` (status e/ou prioridade; "Nada mudou").
- `registrar_comentario(os: dict, texto, usuario, pode, nota: str) -> dict` (`nota` = "sim" | o motivo de não ter ido).
- `linha_da_nota(texto, nome, quando: datetime) -> str` = `"[24/10/2026 14:32] Nome (Engenharia): texto"`.
- `ultima_atualizacao(os_id, atividade_iso, est) -> datetime | None` e `parada(coluna, ultima, agora) -> bool`.
- `Recusada(Exception)`; quem pode = `acompanhamento.pode_agir` (setor Engenharia ou admin com login de pessoa).
- `os` = `{"wid", "folio", "codigo", "usina"}` (do quadro).

Testes (escreva antes, veja falhar):
- `test_catalogo_registra_o_livro_da_os` (o Livro com as 3 abas, `so_cresce`, o Fato com grão e IDs; explica com
  RESUMO e PARA_QUE).
- `test_status_e_prioridade_vao_ao_livro_e_o_estado_le_o_ultimo` (dois eventos; o estado traz os ids do último).
- `test_nada_mudou_e_quem_nao_e_da_engenharia_nao_classifica`.
- `test_comentario_cifrado_com_o_nome_e_a_linha_da_nota` (a linha com data e hora de Brasília; texto e nome não aparecem
  em claro nas linhas do banco falso).
- `test_ultima_atualizacao_e_parada` (evento, criação e atividade: vale o mais novo; aberta com 8 dias pulsa, 6 não,
  concluída nunca).

### Task 2: a página da OS (`/t/engenharia/equipe/os/<int:folio>`) e o classificar

**Files:** Modify `nexus/torres/engenharia/__init__.py`; Create `templates/engenharia/os_quadro.html`; Modify
`nexus/static/engenharia.css`; Modify `nexus/engenharia/os_equipe.py` (`atividade_iso` em `montar`; `ler_os(folio)`,
`filhas(wid)`, `resposta_da_atividade(folio)` pelo REST só leitura); Test `tests/test_engenharia_os_quadro.py`.

**Interfaces:** `os_equipe.ler_os(folio) -> dict | None` (o dict do `montar`, sem filtro de pessoa, com `nota` inteira e
`wid`); `os_equipe.filhas(wid) -> list[dict]` (`work_orders?id_parent_wo=`); `os_equipe.resposta_da_atividade(folio) ->
str | None` (`work_orders_subtasks/?folio=`, descrição normalizada "descreva a atividade realizada"). Rota
`POST /t/engenharia/equipe/os/<folio>/classificar` (origem conferida; volta à página com o aviso).

Testes:
- `test_pagina_da_os_tem_os_quatro_numeros_e_os_blocos` (Status, Prioridade, Programada, Última atualização; Status e
  prioridade, Dados, OS filhas, Na nota da OS, Demais respostas do técnico, Comentários; o botão Solicitar OS com
  `ativo`, `os_pai` e `os_pai_folio`; sem "Abrir a OS").
- `test_demais_respostas_vem_da_os_filha` (duas filhas, uma com a resposta, outra sem).
- `test_classificar_grava_e_volta_com_o_aviso` e `test_quem_nao_e_da_engenharia_le_sem_formularios`.
- `test_os_que_nao_existe_diz_que_nao_achou` (404 com a mensagem).

### Task 3: o comentário na nota da OS (ponte `/os/_nexus/engenharia/os/<int:wid>/comentar`)

**Files:** Modify `nexus/torres/oscreator/ponte.py`; Test `tests/test_engenharia_os_quadro.py`.

Regra: Nexus logado e quem pode; sem JWT do Fracttal → 401 `{"login": url}` e nada gravado; `os_api.get_os_detalhes(wid)`
na sessão (`os_sessao.contexto`); `regra.nota_pode_editar` recusa → grava só no Nexus com o motivo; senão
`editar_nota_os(wid, nota_atual + "\n" + linha)` e grava no Nexus com `nota="sim"`; erro do Fracttal → 502, nada gravado.

Testes: `test_comentario_vai_para_a_nota_com_data_e_hora`, `test_sem_login_do_fracttal_pede_o_login_e_nao_grava`,
`test_os_de_varias_tarefas_fica_so_no_nexus_com_o_motivo`, `test_erro_do_fracttal_nao_grava_nada`,
`test_comentario_de_outro_site_e_recusado`.

### Task 4: o quadro (o clique, as etiquetas e o pulso)

**Files:** Modify `templates/engenharia/equipe.html`, `nexus/torres/engenharia/__init__.py` (`equipe()` junta
`eng_status`, `eng_prioridade`, `ultima_iso`, `parada`), `nexus/static/nexus.css` (token `--pulso` em H S L nos dois temas),
`nexus/static/engenharia.css` (`.kb-card--parada` com a sombra do Levi numa camada `::after`, opacidade 0,5 ↔ 1,
`prefers-reduced-motion`). Test `tests/test_engenharia_equipe.py`.

Testes: `test_quadro_leva_status_prioridade_e_parada_de_cada_os`, `test_clique_abre_a_pagina_da_os` (o JS monta o
endereço da página, sem `NexusOsCard`), `test_pulso_usa_a_sombra_em_camadas_por_token` (CSS).

### Task 5: a Nova solicitação com a sugestão (clone)

**Files:** Modify `os_creator/os_web/rotas_solic.py` (`sugestao` = cliente, usina, ativo e a OS pai, resolvidos no
catálogo pelo código), `os_creator/os_web/templates/solic.html` (a cascata em funções que devolvem promessa; a sugestão
marca o ativo e escolhe a OS pai); README da torre. Test `tests/test_oscreator_solic_pcm.py`.

Testes: `test_solicitacao_com_sugestao_traz_o_ativo_e_a_os_pai`, `test_solicitacao_sem_sugestao_segue_igual`.

### Task 6: os `.md`, a prova no navegador e a revisão

`nexus/torres/engenharia/CLAUDE.md` (Quadro da equipe: o clique, o pulso; a seção nova da OS), `nexus/dados/CLAUDE.md`
(o livro na tabela e na regra 9), raiz (linha da Engenharia), README do OS Creator (a sugestão). Suíte inteira com o
`.env`; a página e o quadro na cópia de prova a 1440 e a 375 px, escuro e claro; revisor novo no ramo inteiro.
