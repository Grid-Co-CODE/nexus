# CLAUDE.md — torre Campo · App

A visão do Nexus sobre o trabalho de campo. **Nenhuma tela abre o painel do App nem aponta para o Azure** (Levi,
05/10/2026: "quero parar de referenciar o Azure e ter uma visão nossa!"): todas leem o banco do Nexus (API db_performace).
Leia também o `CLAUDE.md` da raiz e, antes de pôr dado novo no banco, o `nexus/dados/CLAUDE.md` (PRIORIDADE 0).

## Regra: tudo em paralelo (Levi, 04/10/2026)

"Por hora todas as decisões para o Nexus são paralelas, não deve afetar o funcionamento atual." Nada aqui escreve no
App nem no Fracttal. Aprovar, devolver, encaminhar e decidir PT continuam no App: o Nexus mostra. Sem link para o painel
do App e sem "Abrir no App"; a OS aparece como `#número` (o Fracttal não tem endereço direto de uma OS).

## As telas

| Tela | De onde vem | Quem calcula |
|---|---|---|
| Central de atenção | rondas, PT e decisões do App + cadastro do Nexus | `visao.atencao` (conta nossa) |
| Aprovação de OS | fila de verificação do Fracttal ao vivo (só GET) + nota do livro do App | regras copiadas do App |
| Permissões de trabalho | `pt_app_campo` | `visao.pts` (conta nossa) |
| Ordens de serviço | `fechamentos_app_campo` | regras copiadas do App |
| Rondas | `rondas_app_campo` + usinas em operação do cadastro | `visao.rondas` (conta nossa) |
| Zeladoria | `zeladoria_app_campo` | `visao.zeladoria` (conta nossa) |
| Ranking | `fechamentos_app_campo` + cobertura de ronda | `visao.ranking` (conta nossa) |
| Triagem de qualidade | `fechamentos_app_campo` + rondas | regras copiadas do App |
| Imagens da ronda | placeholder: a foto ainda não chega ao banco | — |
| Rotas do dia | placeholder: programação do PCM + localização das usinas | — |

Fora daqui: a "APR e PT" da torre HSEQ responde outra pergunta (OS de risco sem APR ou PT assinada).

## De onde vem o dado

**Os livros que o próprio App grava no banco** (Levi, 05/10: "operador faz ronda > após ronda input é dado na API do PG
> Nexus lê"). O timer `nexus_workbooks_sync` do App (v226, aos :25 de cada hora) sobe `fechamentos_app_campo` (90 dias:
nota do painel, observação, GPS no início e no fim, pontualidade), `pt_app_campo`, `zeladoria_app_campo` e
`decisoes_app_campo`; o v210 já subia `rondas_app_campo`. 1ª carga (05/10 13:40): 2.488 fechamentos, 120 PT, 122
decisões, 766 rondas, zeladoria vazia.

- **Pessoa só como HMAC do e-mail.** O Nexus calcula o mesmo código para cada e-mail do cadastro do App
  (`identidades.json`, `NEXUS_CAMPO_IDENTIDADES`) e troca pelo nome na hora (`livros_app.pessoas_por_codigo`). Precisa
  de `NEXUS_PESSOA_HMAC` no `.env` daqui, a mesma do App Setting. Sem ela, o App não manda nada e a fonte das regras
  copiadas volta ao livro do coletor.
- **Usina e equipe ligam ao cadastro pelo `Ligador`** da camada de dados (`nexus/dados/fatos.py`): de-para "Fracttal ·
  Classificação 1" (a parte depois de " · "), de reserva o código da usina dentro do código do ativo (só se for
  único). A base da cobertura e do ranking são as usinas com status `OPERAÇÃO` e a equipe de cada uma. Região que o App
  escreve e o cadastro não tem (medido em 05/10: "MT Sul 02", 15 fechamentos; "Grid Co.", 1) vai para "fora do
  cadastro", não some. Conserto é no cadastro.
- **O que o livro ainda não traz:** a situação da OS no Fracttal, as durações do Fracttal, a aprovação e a avaliação (o
  App guarda de madrugada, `_enriquecer_qlog`, e não manda). Ficam desconhecidas, não aproximadas: "Em verificação" e
  "Tempo real" saem "—" (`ordens._ajuste_da_fonte`; com a duração do celular dava 5.726%, com a situação pela revisão
  do painel, 402 de 447 "em verificação"). Para ter: o App mandar essas colunas (mudança no App).
- **Zeladoria vazia é real:** em 90 dias o App não registrou nenhuma etapa de zeladoria. A tela diz isso.

## As contas nossas (`nexus/campo/visao.py`)

As constantes ficam no topo do arquivo; cada função diz a regra no docstring.
- **Rondas:** cobertura = dias desde a última ronda de cada usina em operação (nunca = 999, aparece "nunca"), da mais
  esquecida para a mais recente; janela de 7, 14 ou 30 dias. Conta também ronda sem OS no Fracttal e ronda que não
  ligou ao cadastro.
- **PT:** fila "aguardando" da mais antiga para a mais nova; espera = da criação à decisão. Medido em 05/10: 31
  esperando, 28 há mais de 2 h, mediana de 85 min.
- **Ranking por região:** 60% nota média dos fechamentos + 40% cobertura de ronda (usinas da equipe com ronda nos
  últimos 14 dias), a régua do painel do App. **Só pontua quem tem as duas partes:** região sem fechamento no período
  ganhava 100 só pela cobertura (erro meu, corrigido em 05/10). Colaboradores: nota, fechamentos, pontualidade e
  devolvidas.
- **Central de atenção:** usina em operação sem ronda há 7 dias ou mais (crítico); PT esperando há mais de 2 h; ronda
  cuja OS o Fracttal não criou; ronda longa pendente, **uma vez por usina** (o App repete o aviso em toda ronda curta:
  sem isso a lista enchia de repetidos); ronda com evidência incompleta. **Nota baixa de fechamento não entra:** é a
  fila da Aprovação, e o fechamento aprovado direto no Fracttal nunca tem decisão no painel, o que dava ponto falso.
  Os tratamentos da Central do App (`decisoes_app_campo`, origem "Central de atenção") aparecem ao lado.
- Cópia de 5 min por tela; banco fora do ar = a tela avisa "Não consegui ler o banco do Nexus" e não some. Nos testes,
  sem `app.extensions["nexus_dados_sessao"]`, nunca vai à rede.

## As contas copiadas do App (`nexus/campo/regras_app.py`)

Aprovação, Ordens e Triagem usam a lógica do App copiada, não refeita, para o número bater com o painel dele.
- `ferramentas/extrair_regras_campo.py` copia do `function_app.py` do App o fecho das funções das rotas
  `gestao/supervisao/fila`, `gestao/os` e `gestao/prioridades` e as duas réguas da nota. **Atenção e PT saíram da
  cópia em 05/10** (717 linhas a menos): agora são contas nossas. A cópia leva só a lógica (`ast.unparse`, sem
  comentários: o repositório é público e os comentários do App citam colegas pelo nome).
- `tests/test_campo_regras_app.py` compara cada função com o App pela árvore do código. Falhou = o App mudou: rode o
  extrator e confira a tela. Em 05/10 o v230 mudou `_qualidade_v2` (GPS do início vale como prova); recopiado, código
  `68d4d468251f7d6a`.
- Trocados pelo Nexus no fim do arquivo gerado: `_tabela` e `tabela_qlog` (leem pela fonte do Nexus, `tabelas.py`),
  `tabela` (a dos tokens do Fracttal: só a partição `cadastro`; `tok` e `pt` recusadas), `fx` (Fracttal só GET,
  `fracttal.py`) e `ident` (`pessoas.ident`).
- O código do App que vale é o da pasta `App_Campo\middleware` do SharePoint.
- O cartão "Tempo vs. previsto" do App mostra "+66%", mas a conta é real ÷ previsto: no Nexus sai "66% do previsto".

## Sem Azure, sem coletor

- Nenhum módulo importa o SDK do Azure (`tests/test_campo_regras_app.py` trava). A leitura do Storage do App por SAS foi
  feita e removida em 04/10. Chave do Storage no ambiente não liga nada.
- **O coletor do Fracttal está APOSENTADO** (05/10): gastava a cota de 200/min da empresa inteira para chegar a uma
  nota que batia com a do painel do App em só 14% das tarefas (11,8 pontos de diferença média). Fica DESLIGADO (sem
  `NEXUS_CAMPO_COLETOR`). O código (`coletor.py`, `banco_campo.py`, livro `campo_nexus`) é reserva para máquina sem a
  chave HMAC e sai quando a troca estiver conferida com o painel do App. Se um dia religar: nunca no horário de campo
  (seg a sex, 6h às 18h, `deve_rodar`), uma máquina só, e nunca o nome do técnico nem o endereço da usina em claro (o
  `items_log_description` do Fracttal traz o endereço).
- A Aprovação de OS ainda lê a fila do Fracttal ao vivo: 0,5 s entre pedidos, para no primeiro 406/429, a fila crua
  fica 10 min em cópia. Não abra essa tela em teste no horário de campo.

## Peças em `nexus/campo/`

- `visao.py`: as contas nossas (acima).
- `livros_app.py`, `fonte_pg.py`, `tabelas.py`: os livros do App no formato que as regras copiadas consultam
  (`query_entities`, `get_entity`); erro de leitura fica anotado e vira aviso.
- `aprovacao.py`, `ordens.py`, `triagem.py`: as telas pelas regras copiadas. `leitura.py`: cópia de 5 min e
  `limpar_cache()` (que também recarrega a cópia das regras).
- `pessoas.py`: `identidades.json` e a tabela dos tokens só na partição `cadastro`.
- `nota_fracttal.py`, `coletor.py`, `banco_campo.py`: o caminho do coletor aposentado.

Telas: `templates/campo/*.html` + `static/campo.css`; filtros pela URL.

Prova: `tests/test_torre_campo.py` (nenhuma tela com Azure, moldura ou "Abrir no App"), `test_campo_visao.py` (as
contas nossas com banco falso), `test_campo_regras_app.py`, `test_campo_aprovacao.py`, `test_campo_ordens.py`,
`test_campo_telas_pg.py`, `test_campo_livros_app.py`, `test_campo_fonte_pg.py`, `test_campo_nota_fracttal.py`,
`test_campo_coletor.py` (`tests/pg_falso.py`).
