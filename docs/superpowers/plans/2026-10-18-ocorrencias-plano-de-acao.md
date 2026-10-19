# As ocorrências com plano de ação — plano de construção

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** a tela Ocorrências do Campo · App (lista e quadro; criar e editar a ocorrência, o plano de ação e o
andamento), gravada no banco pelo Nexus, e a etiqueta de ocorrências abertas na Visão geral.

**Architecture:** um livro `nexus_ocorrencias` com uma aba de eventos (`fato_evento_ocorrencia`: criou, dados, acao,
andamento), só acrescenta; o estado sai dos eventos (`estado`), como o acompanhamento da Engenharia. O texto livre vai
cifrado (o Cofre); em claro, IDs, códigos e datas. Rotas no `bp` da torre Campo, guardadas pela régua de outro site.

**Tech Stack:** Python 3.14, Flask/Jinja, a API do banco (`livros`), o Cofre do cadastro, pytest com o banco falso.

**Spec:** `docs/superpowers/specs/2026-10-18-ocorrencias-plano-de-acao-design.md`

## Global Constraints

- Regra 10 da camada de dados: o livro entra no catálogo (Fato + Livro, `so_cresce=True`) antes da 1ª gravação.
- Regra 8: nada de texto livre nem nome em claro no banco; o Cofre com contexto por evento.
- Só o responsável O&M (login do Fracttal) e o administrador gravam; os outros só veem.
- Cor só por token, sem emoji, pt-BR, `url_for`/`url(...)`; nome de colega fictício nos testes.
- Antes de pronto: a suíte inteira e a tela a 1440 e 375 px, nos dois temas. Publicar: o Levi autorizou ("siga!").

## Review Focus

1. A gravação que falha ao reler o livro não grava (gravaria por cima do que há).
2. Quem não pode editar não grava nem vê os botões; o pedido de outro site é 403.
3. Texto vazio, comprido demais, data inválida, criticidade ou status fora da lista: recusado com o porquê, sem 500.
4. Ocorrência finalizada some das abertas da Visão geral; a etiqueta tem a cor da criticidade mais alta das abertas.
5. Sem a chave do cadastro, a tela diz que não grava e continua mostrando o que há.

---

### Task 1: o fato e a conta (puro) e o catálogo

**Files:** `nexus/campo/ocorrencias.py` (novo), `nexus/dados/catalogo.py`, `nexus/dados/explica.py`, testes
`tests/test_campo_ocorrencias.py` (novo) e `tests/test_dados_camada.py`.

- Produces: `CAB`, `EVENTOS`, `CRITICIDADES`, `STATUS`, `SITUACOES`; `estado(eventos) -> dict[str, dict]` (por
  `ocorrencia_id`: os campos da última decisão, `acoes` por `acao_id` com a última decisão, `andamentos` na ordem,
  `proximo_prazo`); `abertas_por_usina(estado) -> dict[int, dict]` ({"n", "pior"}); `ordenar(lista)` (prazo da próxima
  ação em aberto; sem prazo no fim).
- Testes: a última decisão vale; a ação editada fica com a última situação; o andamento na ordem; a finalizada sai das
  abertas; a pior criticidade das abertas; a ordem pelo prazo.

### Task 2: gravar e ler no banco

**Files:** `nexus/campo/ocorrencias.py`, `tests/test_campo_ocorrencias.py`.

- Produces: `ler() -> dict` (os eventos decifrados, cópia de 60 s; `limpar()`), `pode_editar(admin, responsavel)`,
  `criar(dados, usuario, admin) -> str`, `editar(oid, dados, ...)`, `acao(oid, dados, ...)`, `andamento(oid, texto,
  ...)`, `Recusada`.
- Testes (banco falso): criar e ler de volta; o texto não aparece em claro no banco; editar; ação nova e editada;
  andamento; recusas (sem permissão, texto vazio ou comprido, data inválida, código fora da lista, sem a chave); a
  releitura que falha não grava.

### Task 3: as telas

**Files:** `nexus/torres/campo/__init__.py` (a Tela "ocorrencias" e as rotas), `nexus/torres/campo/templates/campo/
ocorrencias.html` e `ocorrencia.html` (novos), `nexus/static/campo.css`, `tests/test_campo_ocorrencias.py`.

- Rotas: `/t/campo/ocorrencias` (lista e `?ver=quadro`, filtros usina, responsável, status, criticidade),
  `/t/campo/ocorrencias/nova` (GET e POST), `/t/campo/ocorrencias/<oid>` (o detalhe), POST `.../<oid>/dados`,
  `.../<oid>/acao`, `.../<oid>/andamento`.
- Testes: a lista e o quadro; criar pela tela (admin); quem não pode não vê o botão e o POST é recusado; o detalhe com o
  plano e o andamento; os filtros; outro site é 403.

### Task 4: a Visão geral, a documentação, a prova e a entrega

- A etiqueta "N ocorrências" no nome da usina na Visão geral (cor da pior criticidade aberta, link para a tela
  filtrada); `nexus/torres/campo/CLAUDE.md` e `nexus/dados/CLAUDE.md`; a prova na tela; a suíte inteira; publicar.
