# Almoxarifado no PCM — desenho (25/10/2026)

Levi, 25/10/2026: "No fractall temos almoxarifado, gostaria de uma visão para a gestão desse almoxarifado na parte de
PCM". A prévia (dados reais da varredura de 25/10, fora do Nexus) foi aprovada: "Aprovado o desenho da prévia do
almoxarifado. Pode escrever o projeto, com o App publicando a varredura no banco." Revisado em 25/10 contra as regras
da camada de dados e o código do App v299 (23 achados; os que mudaram o desenho estão incorporados abaixo).

## 1. Para que serve

A pergunta da tela: **que peça está abaixo do mínimo ou no limite, em que almoxarifado, e o que saiu nas OS?**
O PCM confere a reposição antes de programar a semana e vê o que o cadastro do Fracttal deixa em aberto (peça sem
mínimo, peça avariada no saldo).

Entra no lugar reservado que a torre PCM já tem: a tela `pecas` ("Peças e sobressalentes", hoje placeholder). O
endereço fica o mesmo (`/t/pcm/pecas`), para não mexer nos acessos salvos por setor; o título vira **Almoxarifado**, a
fonte "Fracttal (inventário), pela varredura diária do App de Campo", e o setor dono, `do_setor="PCM"` (outros
setores pela marca em Base → Acessos).

## 2. De onde vem o dado

```
Fracttal (inventário)                         o Nexus não chama o Fracttal: zero da cota de 200/min
   │  RPC inventories.items_list + associate_warehouses_list, item a item, com o token de serviço do App
   ▼
App de Campo: a varredura diária (já existe)  a partir de 00:00 de Brasília, em passadas de 10 min; ~30 min
   │  tabela Azure `pecas`: almoxitem, recurso, almoxscan
   ▼
App publica no banco (NOVO, pacote para a sessão do App)
   │  4 livros na API de planilhas (db_performace), pelo mesmo caminho dos que já sobem (sync-xlsx, replace)
   ▼
Nexus
   ├─ tela PCM → Almoxarifado: o ciclo mais novo e coerente dos livros do App
   └─ carga própria (no laço de hora em hora, com portão próprio): guarda o histórico em `nexus_almoxarifado` e na
      família `nexus_almoxarifado_saldo_AAAA_MM` (o livro do App é trocado a cada ciclo; sem o Nexus guardar, o saldo
      de ontem se perde)
```

Por que pelo App: o saldo só sai item a item (574 chamadas por leitura); o App já paga essa conta uma vez por dia, de
madrugada, com folga na cota. Ler de novo no Nexus dobraria o custo e brigaria pela cota da empresa.

## 3. Os livros que o App publica (o contrato)

Um grão por livro (o `sync-xlsx` com `replace` troca o livro inteiro). As colunas são o contrato, na ordem; coluna
nova só no fim, dos dois lados, com teste dos dois lados comparando a lista (como o `test_v257_extintores_nexus.py`).
O Nexus lê pelo NOME da coluna. IDs do Fracttal e número de OS vão como TEXTO; saldo, mínimo e quantidade como
número já normalizado pelo App (o Fracttal pode mandar "10.00" em texto).

**O ciclo** é identificado pelo seu **início** (ISO UTC, o `inicio` do `almoxscan`), não pela data: o "Atualizar" do
Admin reinicia o ciclo com a mesma data, e o pedido entre 21:00 e 23:59 de Brasília cai na data UTC do dia seguinte.

### 3.1 `almoxarifado_ciclo_app_campo` · `Ciclo` — 1 linha = o último ciclo completo publicado

Início do ciclo · Fim do ciclo · Itens na lista do Fracttal · Itens lidos · Erros · Origem (`automático` ou `pedido
do Admin`). É por ele que o Nexus sabe se o ciclo está inteiro (seção 4.3).

### 3.2 `almoxarifado_itens_app_campo` · `Itens` — 1 linha = 1 item que estava na lista do Fracttal no ciclo

ID do item · Código · Nome · Unidade · Família · Avariado (Sim/Não) · Ferramenta (Sim/Não) · Início do ciclo · Lido
(Sim/Não: Não = o saldo falhou neste ciclo e o item vai sem linha no Saldo).

Muda no App: cada item ganha a marca do ciclo em que estava na lista (`na_lista`), mesmo quando o saldo falha; só esses
são publicados. Hoje a partição `almoxitem` nunca apaga, e o item desativado no Fracttal fica para sempre igual ao item
que falhou na leitura.

### 3.3 `almoxarifado_saldo_app_campo` · `Saldo` — 1 linha = 1 item × 1 almoxarifado, lido no ciclo

ID do item · Código · ID do almoxarifado · Almoxarifado · Local do almoxarifado · Saldo · Mínimo · Início do ciclo.

O **Local** vai inteiro (o caminho do Fracttal, `parent_description`); o Nexus tira dele o pedaço "Cliente - Usina - UF",
como o `ligacoes.usina_do_caminho` (hoje o App guarda só o último pedaço, e um almoxarifado debaixo de uma
sublocalização perderia a usina). Mínimo 0 = sem mínimo cadastrado.

### 3.4 `almoxarifado_pecas_app_campo` · `Peças` — 1 linha = 1 peça lançada (ou recusada) pelo App

ID do lançamento · Recebido em (ISO UTC, a hora do servidor) · Usada em (o `ts` do evento no celular; a fila offline
atrasa o recebimento) · OS · Tarefa · Código do ativo · ID do item · Código · ID do almoxarifado · Quantidade ·
Unidade · Situação (`lançada`/`recusada`) · Motivo da recusa · Lançado por (HMAC).

- **Tarefa e Código do ativo** ligam a peça à tarefa do fechamento (o `fato_fechamento` não tem o ID da tarefa do
  Fracttal); o Nexus troca a tarefa pela `tarefa_chave`, como nos outros livros, e o texto não entra no fato.
- **Motivo da recusa:** um domínio curto tirado das recusas reais (as 13 de 21–22/10 foram a chave recusada pelo
  Fracttal, o erro corrigido no App v294), em `dominios.py`: `chave recusada pelo Fracttal`, `sem permissão`, `outro`.
  NUNCA o texto do erro (pode trazer nome). O App não grava hoje a "tarefa fora da OS" (409 antes de gravar) nem o
  limite do Fracttal (volta para a fila): ficam de fora desta etapa.
- **Lançado por:** HMAC-SHA256 do e-mail com a `NEXUS_PESSOA_HMAC`, como nos outros livros; nunca o e-mail.
- Janela: a dos outros livros (`NEXUS_WB_DIAS`, 90 dias); o Nexus guarda o resto.

### 3.5 Quando o App publica

- **Ciclo, Itens e Saldo: uma vez por ciclo completo** (`almoxscan|estado.fim`), nunca no meio (no meio a tabela mistura
  o saldo de hoje com o de ontem). O App marca o ciclo publicado só depois dos três OK; o que falhar, tenta de novo na
  passada seguinte. Os três entram no `NEXUS_WB_SEM_VAZIO` (não sobem vazios).
- **Peças: de hora em hora, aos :25**, com os outros livros.
- Atrás do mesmo interruptor dos outros (`NEXUS_PESSOA_HMAC`); sem `GRIDCO_SQL_TOKEN`, nada sai.

O que muda no App vai num pacote em `C:\GridcoBuild\app-campo-docs\_propostas\almoxarifado-nexus\` (LEIA, diff,
`aplicar.py`, o teste do contrato), no formato dos pacotes anteriores. Quem aplica e publica é a sessão do App, com o
OK do Levi.

## 4. A base no Nexus (Kimball)

### 4.1 Os livros

| Livro · aba | Grão | Tipo |
|---|---|---|
| `nexus_almoxarifado_saldo_AAAA_MM` · `fato_saldo_almox` (família por mês, como a `nexus_geracao_inversor_AAAA_MM`) | 1 linha = 1 item × 1 almoxarifado × 1 ciclo completo aplicado | `snapshot_periodico` |
| `nexus_almoxarifado` · `fato_ciclo_varredura` | 1 linha = 1 ciclo da varredura que o Nexus viu (aplicado ou recusado, com o porquê; e a marca de anulado) | `snapshot_acumulado` |
| `nexus_almoxarifado` · `fato_peca_lancada` | 1 linha = 1 peça lançada (ou recusada) pelo App; vale a última linha do App para o mesmo ID (o reenvio de uma recusada vira lançada) | `snapshot_acumulado` |
| `nexus_almoxarifado` · `dim_item_almox` | 1 linha = 1 item já visto (ID, código, nome, unidade, família, avariado, ferramenta) | dimensão |
| `nexus_almoxarifado` · `dim_almoxarifado` | 1 linha = 1 almoxarifado já visto (ID, nome, local, `usina_id`, `usina_ligada_por`) | dimensão |
| `nexus_almoxarifado` · `qualidade`, `atualizacao` | as de todo livro do Nexus (a qualidade no formato `CAB_QUALIDADE`, com linha própria) | |

**Foto por ciclo, e não intervalos:** ~270 linhas por ciclo, ~8 mil por mês num livro do mês, só acrescentando. Sem
lógica de fechar período, sem fechar por ausência (regra 6), e o dia sem ciclo fica sem foto: "não medido" não vira
"não mudou". O saldo do dia D é o do último ciclo aplicado que começou em D; dia sem ciclo, sem resposta.

**Medidas** (regra 3): `saldo_qtd`, `minimo_qtd`, `quantidade_qtd`, com a unidade "a do item"
(`dim_item_almox.unidade`: UNIDADE, METRO, MASSA) e soma `semi` (soma entre almoxarifados do MESMO item; nunca no tempo
nem entre itens). `lancada` (1/0) na peça.

**Dimensões no catálogo:** o item segue o precedente do extintor: no lugar de `equipamento`, estado `prop` ("ID do item
do inventário, cadastro próprio: `dim_item_almox`"). Promover "item" a dimensão conformada (`DIMENSOES`) fica para
quando vierem compras e consumo, porque mexe em todos os fatos. O almoxarifado é hierarquia da usina (como a
`estrutura_usina`).

**Ligações (regra 4: não liga = vazio, nunca chutar):**
- **Usina:** o local "Cliente - Usina - UF" é a mesma chave da Classificação 1 do Fracttal e liga pelo
  `cadastro_nexus · de_para` do banco (o que a carga usa). Os locais de almoxarifado entram na lista do sistema
  `Fracttal · Classificação 1` da tela Base → Ligações, lidos do livro Saldo do App no banco (igual nas duas máquinas),
  sem repetir chave, para o local que não está lá (a Nobres) ligar à mão. Medido na de-para desta máquina: 11 de 12; a
  medida de verdade é contra a do banco, no passo 1. `usina_id` e `usina_ligada_por` vão também NO FATO (a Governança
  mede a usina por fato); o livro do mês corrente é religado a cada gravação, os meses fechados ficam como foram gravados.
- **Pessoa:** `pessoa_id` pelo HMAC.
- **OS e tarefa:** `os`, `codigo_ativo` e `tarefa_chave` no fato da peça: é por eles que a peça encontra o fechamento.
- **Datas** (regra 7, papéis): no saldo, `data_id` = o dia de Brasília do início do ciclo; na peça, `data_id` = o dia de
  Brasília do "Usada em" e `data_id_recebida` = o do "Recebido em".

### 4.2 Quem grava

Uma função própria no laço de hora em hora, como o `gerar_geracao`, com portão próprio (a carga dos fatos só grava os
4 livros dela e recusa outro; e o portão dela é o horário do `nexus_fatos`: se o PC ganhar a hora, o servidor pula).
O portão do almoxarifado: **um ciclo novo (pelo início) ainda não visto, ou mudou o sha das peças**. Idempotente, com as
linhas ordenadas (as duas máquinas dão o mesmo resultado, regra 11), isolada em `try` (regra 13: a falha dela não para
a carga dos fatos).

### 4.3 As travas (confiabilidade antes de tela)

- **Completude do próprio ciclo:** aplica só com `lidos ÷ itens na lista ≥ 90%`. Abaixo disso, o ciclo entra no
  `fato_ciclo_varredura` como recusado, com o porquê, e a tela fica no último ciclo bom, com o aviso. A queda de itens
  contra o ciclo anterior é só aviso na qualidade (o PCM pode limpar o catálogo).
- **Coerência entre os livros:** aplica e mostra só quando Ciclo, Itens e Saldo têm o mesmo início de ciclo; senão, a
  tela mostra o último ciclo aplicado, do histórico do Nexus, com o aviso.
- **Livro do Nexus que só cresce** (`so_cresce`, regra 9), com as travas do `_programacao`: livro que existe e leitura
  que falha ou vem vazia não grava. A regra 9 e o `nexus/dados/CLAUDE.md` passam a dizer que esta carga tem trava.
- **Anular um ciclo aplicado errado:** uma ferramenta à mão marca o ciclo como anulado no `fato_ciclo_varredura` (não
  apaga linha: o livro só cresce); as contas ignoram os ciclos anulados.

## 5. A tela (a da prévia aprovada)

**Topo, 6 números** (a faixa `kb-kpis` da casa): almoxarifados · peças com saldo · abaixo do mínimo + no limite · sem
mínimo cadastrado · avariadas · lançadas pelo App (com quantas recusadas). E a linha do ciclo: "saldo do Fracttal de
25/10, 00:29 (574 itens lidos)".

**5 abas:**
1. **Reposição:** abaixo do mínimo primeiro, depois no limite. Almoxarifado, peça (código e nome), família, saldo com
   a barra, mínimo, falta (ou "no limite").
2. **Por almoxarifado:** um cartão por almoxarifado, com a usina do cadastro: peças, abaixo · no limite, sem mínimo,
   zeradas, a barra (cor por token).
3. **Catálogo e saldo:** busca no catálogo inteiro; onde a peça tem saldo (e "sem saldo em nenhum almoxarifado").
4. **Consumo nas OS:** lê o fato do Nexus (não para nos 90 dias do App): quando, OS, peça, quantidade, almoxarifado,
   lançada ou recusada (e o motivo). **Tudo desde o início, sem corte** (Levi, 25/10/2026), na aba e no número do
   topo, inclusive as 13 recusadas de 21–22/10.
5. **Cadastro a corrigir:** peças sem mínimo por almoxarifado, peças avariadas com saldo e peças recusadas ("corrigir no
   Fracttal": a recusada nunca saiu do saldo).

Filtros: almoxarifado, família e busca (endereço relativo ou `nexusRota`, nunca a partir da raiz). Abaixo de 640 px,
as tabelas viram cartões. Cor só por token; severidade por cor e palavra; sem emoji.

**As contas** ficam num módulo puro só (a tela e a carga usam o mesmo, regra "uma regra só"):
- **Abaixo do mínimo:** mínimo > 0 e saldo < mínimo. **No limite:** mínimo > 0 e saldo = mínimo (25/10: 0 abaixo,
  54 no limite: o Fracttal costuma ter o mínimo igual ao saldo).
- **Sem mínimo:** mínimo = 0 (25/10: 22 linhas). **Zerada:** saldo = 0 com a peça associada ao almoxarifado.
- **Avariada:** a marca do item (25/10: 5 itens).
- **Ciclo velho:** o último ciclo aplicado com mais de 36 h: a tela mostra o saldo com a data dele e o aviso, sem
  esconder nem misturar. Livro do App que ainda não existe: "o App ainda não publica o almoxarifado", sem número.

Números de 25/10 (prévia): 574 itens no catálogo, 222 com saldo, 12 almoxarifados (todos de usina), 267 linhas item ×
almoxarifado, 11 famílias, 16 peças lançadas pelo App (13 recusadas, todas do erro de 21–22/10).

## 6. Governança (PRIORIDADE 0)

- **Catálogo primeiro** (`nexus/dados/catalogo.py`): os fatos `saldo_almox`, `ciclo_varredura` e `peca_lancada`; o
  livro `nexus_almoxarifado` e o molde da família em `LIVROS`/`FAMILIAS`; os quatro livros do App como fontes (ou em
  `CONHECIDAS`, o de itens com o papel dimensão); `RESUMO`/`PARA_QUE` em `explica.py`. Assim nenhum livro aparece
  como "novo" no radar.
- **Qualidade visível:** `nexus_almoxarifado · qualidade` entra no `_ultima_qualidade` da Governança de dados (hoje
  ela lê uma lista fixa de livros).
- **Nada pessoal** (regra 8): a pessoa só pelo HMAC; o texto do erro não vai; nome em lugar nenhum.
- **Medir antes de gravar** (`carregar_dados.py --ensaio`): com o 1º ciclo real, e a usina ≥ 98% (a Nobres ligada
  antes).
- **Prova sem dado real no repositório:** a cópia de 25/10 da tabela do App fica em `dados/` (fora do git) e passa
  pela transformação do contrato (HMAC, motivo) antes de virar o banco de mentira da prova; as fixtures têm nomes
  fictícios; o `.env` vai copiado à worktree antes da suíte (o teste de nomes só roda com ele).
- **Um `.md` por área, no mesmo trabalho:** `nexus/dados/CLAUDE.md` (o que existe; regras 2 e 9), `nexus/pcm/CLAUDE.md`,
  `nexus/torres/CLAUDE.md` e a linha do PCM no `CLAUDE.md` da raiz.

## 7. Ordem da entrega

O Nexus sobe ANTES do App, em ensaio (Levi, 25/10/2026): assim nenhum dia de histórico se perde entre o App começar a
publicar e a 1ª gravação, e a gravação só liga depois do ensaio com o dado real, sem novo push.

1. **Nexus:** o catálogo, o módulo das contas, a tela (com os estados "o App ainda não publica" e "ciclo velho"), a
   carga do almoxarifado com o portão e as travas, a ligação da usina pelos locais do App, a qualidade na Governança,
   os testes (fixtures no formato do contrato; carga com o `pg_falso`, inclusive `como_texto=True`). A carga do
   almoxarifado nasce em ensaio: monta, mede e escreve no log, mas só grava com `NEXUS_ALMOX_GRAVAR=1` no `.env`.
2. **O pacote do App** (`_propostas/almoxarifado-nexus`).
3. **Com o App publicando:** ensaio com o 1º ciclo real (linhas, chave repetida, % de usina), a Nobres ligada, a chave
   `NEXUS_ALMOX_GRAVAR=1` no `.env` do servidor, a 1ª gravação conferida, a tela conferida no navegador (desktop e
   375 px).

Push na `main` e deploy do App, cada um só com o OK do Levi.

## 8. O que fica de fora (e por quê)

- **Entradas, transferências, solicitações de compra e custo/valor do estoque:** o App não lê; ler pediria chamadas
  novas ao Fracttal (a cota é da empresa). 2ª etapa, se o PCM pedir.
- **Baixa feita direto no Fracttal (fora do App):** não aparece em Consumo nas OS. O histórico por ciclo permite, numa
  etapa seguinte, apontar "saldo caiu sem lançamento no App".
- **A recusa "tarefa fora da OS" e o limite do Fracttal:** o App não grava a linha hoje; contar essas pede mudar o App.
- **Almoxarifado compartilhado** (a App Setting `ALMOX_COMPARTILHADOS`): cada almoxarifado aparece na usina dele.
- **Gravar no Fracttal** (mínimo, ajuste de saldo): o Nexus só lê; quem corrige é o PCM no Fracttal.
- **Tendência de consumo e previsão de reposição:** o histórico começa no dia 1 para isso; a tela vem depois.
