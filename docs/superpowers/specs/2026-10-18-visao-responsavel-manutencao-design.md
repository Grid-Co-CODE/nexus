# Visão do responsável: bloco Manutenção, coluna Limpeza e faixa "Parada agora" — desenho

18/10/2026. Pedido e decisões do Levi nesta data; o que é escolha do Claude está marcado como tal.

## Por que

Um supervisor montou um painel próprio (planilha, robô do Fracttal, WhatsApp, IA) porque a Visão do responsável
(`/t/campo/responsaveis`) não mostra a manutenção das usinas dele: OS em aberto, o que está atrasado, o que parou, o
que foi feito na semana. O Levi quer que os responsáveis larguem os painéis próprios e usem só o Nexus ("Sim, é isso").

Este documento é a 1ª de quatro peças, na ordem combinada: (1) as informações de manutenção na Visão, aqui; (2) o
ranking das equipes; (3) o mapa das usinas; (4) as ocorrências com plano de ação. As outras três ganham desenho próprio.

## Objetivos

1. **Faixa "Parada agora"** no topo da Visão: toda OS de parada aberta nas usinas do filtro.
2. **Coluna "Limpeza"** no bloco Acompanhamento: sujidade e vegetação da última ronda.
3. **Bloco "Manutenção"**, o terceiro, embaixo de Performance e Acompanhamento, na largura toda (modelo A, escolhido
   pelo Levi), com as colunas OS abertas, Atrasadas, Vencem até amanhã, Paradas (motivo), Semana e Zeladoria.
4. **Só Fracttal ou banco do Nexus** como fonte (regra do Levi, 18/10: "pegando tudo do Fracttal ou Nexus, sem fontes
   externas"). A exceção consciente é a Semana (abaixo).

## Não objetivos

- Ranking das equipes, mapa e ocorrências (peças 2 a 4).
- Filtro ou cartões por gestor de contrato: o Levi escolheu manter a Visão pelo Responsável O&M da usina.
- Fazer a Gestão PCM, o Fora da programação ou o Quadro lerem o fato novo. Fica como próximo passo natural (eles leem
  hoje o `gestao_pcm.json` do GitHub do PCM), mas não neste trabalho.
- Escrever no Fracttal ou no App de Campo.
- Separar a zeladoria por serviço (roçada, poda química, lavagem, pragas) ou mostrar o fornecedor: o dado não existe no
  Fracttal (só o tipo de tarefa Zeladoria) e separar pelo nome da tarefa já errou ("roça" casava com "troca").

## Anti-objetivos (falharia mesmo funcionando)

- Número que não bate com a tela dona dele sem explicação. A regra da Visão continua: nenhum indicador refeito com
  régua nova; cada número sai da mesma fonte e da mesma régua da tela dona (`nexus/torres/campo/CLAUDE.md`, "Visão do
  responsável").
- Leitura do Fracttal pela metade virando número na tela ("número pela metade não vai para a tela", CLAUDE.md da raiz).
- Rajada no Fracttal: o limite de 200 pedidos por minuto é da empresa inteira, e o App de Campo recebe o 429.
- Nome de pessoa ou texto livre no banco (a API tem leitura aberta).
- Dependência externa escondida: a única que fica (a Semana) aparece na tela.

## As decisões do Levi (18/10/2026)

| Assunto | Decisão |
|---|---|
| Onde entra | Modelo A: os dois blocos de hoje lado a lado e o bloco Manutenção embaixo, na largura toda |
| Fonte | Fracttal ou banco do Nexus. OS e zeladoria: o Nexus lê o Fracttal direto |
| Fonte da Semana | Usa a cópia que o banco já tem (`nexus_programacao`, refeita de hora em hora a partir do `banco_dados.json` do PCM), com uma nota na tela dizendo isso, até o PCM gravar a semana direto no banco |
| Atrasada | A régua do PCM, a mesma das telas e relatórios dele (Gestão PCM, diário, fechamento, executivo): tarefa aberta com a Data Programada há **mais de 10 dias**. Atrasada vai para Acompanhar; acima de um limite em dias, Focar. O limite é do supervisor: começa em 30 e ele muda na tela; fica guardado no navegador dele (cookie), não no banco |
| Backoffice | As OS da lista do backoffice do PCM ficam fora das OS abertas e das atrasadas (o supervisor não age sobre elas; já ficam fora da programação e do Fora da programação) |
| Parada | Qualquer OS de parada aberta (usina inteira ou equipamento) põe a usina em Focar e na faixa |
| Semana | Na coluna, a aderência da **semana passada, fechada**, pela régua do Fechamento da semana do PCM: 85% ou mais em dia, abaixo disso Acompanhar. No detalhe, o dia de hoje até agora, só informando (sem cor). Motivo: durante a semana a rolagem da noite tira da agenda o que não foi feito (vai às pendentes, fora do fato), e o robô só refaz a semana pelo plano publicado quando ela fecha; a semana corrente, contada "até hoje", sai inflada |
| Paradas (motivo) | Acompanhar |
| Zeladoria | Zeladoria com a data programada vencida e não feita vai para Acompanhar; usina sem zeladoria no Fracttal só informa |
| Ordem do bloco | Pelo nível; dentro dele, parada primeiro, depois mais tarefas atrasadas, depois mais tarefas paradas, depois a semana mais baixa |
| Limpeza | A régua das Rondas (`visao.criticidade`): nível 5 ou vala obstruída = Focar; nível 4, vala parcial ou sensor sujo = Acompanhar |

## De onde vem cada coisa

| Na tela | Fonte | Situação |
|---|---|---|
| Parada agora | `falhas_performance · disponibilidade_os`, linhas com `aberta` = sim no mês corrente (a plataforma de Performance publica a partir do Fracttal; a Visão já lê em `responsaveis.os_disponibilidade`) | Banco do Nexus |
| Limpeza | A leitura de sujidade e vegetação das Rondas (`visao.sujidade_vegetacao` e `visao.criticidade`: o checklist da ronda do App no banco, o texto da OS de ronda e a validação por foto) | Banco do Nexus e Fracttal |
| Paradas (motivo) | `nexus_pcm_motivos · fato_decisao_motivo` (`nexus/pcm/motivos.py`): a marca é por tarefa (OS + código + nome) e guarda a usina, o motivo, desde quando e quem marcou (HMAC). Vale o motivo que tira da programação e a justificativa do App, o mesmo recorte do painel Fora da programação | Banco do Nexus |
| Semana | `nexus_programacao · fato_programacao` (`status_execucao`, `data_id_semana`, `data_id_programada`, `hora_inicio`, `usina_id`, `os`, `codigo_ativo`, `tarefa_chave`) com a conta do Fechamento da semana do PCM (`nexus/pcm/relatorios/fechamento.py`: aderência = linhas do plano finalizadas ÷ linhas do plano, `regras.fin`, meta `regras.META` = 85%) | Banco do Nexus, copiado do arquivo do PCM |
| OS abertas, Atrasadas, Vencem até amanhã, Zeladoria | **Fato novo**, lido do Fracttal pelo próprio Nexus (abaixo) | Fracttal |

## O fato novo: as tarefas das OS do Fracttal

Antes de gravar, seguir o passo a passo de `nexus/dados/CLAUDE.md` ("Como entra um dado novo"): catálogo primeiro,
módulo puro do fato, testes, ensaio com o dado real, gravar e conferir.

- **Livro e aba:** `nexus_os · fato_tarefa_os` (nome sugerido; registrar em `catalogo.LIVROS` e o `Fato` em
  `catalogo.py`, estado `origem` até a 1ª gravação; o "para que serve" em `explica.py`).
- **Grão:** 1 linha = 1 tarefa de OS do Fracttal (OS × código do ativo × tarefa), como o REST devolve (uma linha por
  tarefa). Medir a chave na fonte antes: repetição é grão errado.
- **O que entra:** as tarefas das OS em processo e em verificação, e as tarefas do tipo Zeladoria finalizadas
  recentemente (para a "última zeladoria feita"). A janela das finalizadas é decisão do construtor depois de medir o
  custo em páginas (ponto de partida: OS criadas nos últimos 90 dias). Se ler as finalizadas custar caro demais, a
  coluna Zeladoria mostra só a próxima programada e a tela diz por quê.
- **Colunas (IDs, chaves e domínios; nada de nome ou texto):** `os` (dimensão degenerada), `tarefa_chave` (sha1 do
  nome normalizado, como no `fato_programacao`, para casar com a programação e com os motivos), `codigo_ativo`,
  `equipamento_id` e `equipamento_ligado_por`, `usina_id`, `usina_ligada_por` e o site do Fracttal (para consertar no
  cadastro o que não liga), `data_id_criacao`, `data_id_programada`, `data_id_fim`, `tipo_tarefa` (domínio, do tipo de
  tarefa do Fracttal: é ele que separa a Zeladoria), `status_os` e `estado_tarefa` (domínios) e `do_backoffice` (1/0:
  o responsável da OS no Fracttal está na lista do backoffice do PCM, `fato_decisao_backoffice`, comparado na hora da
  leitura como o motor compara). Pessoa fica de fora (a Visão não precisa); a marca do backoffice é decidida antes da
  1ª gravação porque o livro é para sempre (regra 10).
- **`tarefa_chave` igual à das outras fontes:** a mesma normalização do nome que os motivos (`motivos.item_id`: sem
  acento, sem caixa, espaço único) e a programação usam, para a tarefa casar entre os três.
- **Ligação:** a usina pelo de-para "Fracttal · Classificação 1" e, de reserva, o código da usina dentro do código do
  ativo, só se for único (o mesmo caminho do `fato_chamado`); o equipamento pela dimensão de equipamento. Não liga =
  vazio, com o site e o código para consertar no cadastro.
- **Datas:** dia de Brasília (o Fracttal manda em UTC).
- **Quem lê e grava:** um laço próprio, como o dos chamados (`nexus/campo/chamados_acompanhamento.py`), fora da carga
  de hora em hora (que não toca no Fracttal). Lê em segundo plano, sem rajada (como a Aprovação de OS: duas páginas por
  vez, pausa depois de um 429), uma vez por hora; grava a máquina que chegar primeiro (regra 11: a última gravação tem
  de ter mais de 50 min); um interruptor de ambiente desliga numa máquina. **Leitura incompleta não grava**: o livro
  fica como estava e a qualidade diz que a leitura falhou.
- **Medir antes de gravar (com o Fracttal de verdade, só GET):** páginas por leitura, linhas, chave repetida, % de
  usina e de equipamento ligados (abaixo de 98% em usina, achar o porquê antes). E comparar, na mesma hora, com o
  `gestao_pcm.json`: tarefas abertas e atrasadas (o campo `atrasado` do robô do PCM, `DIAS_ALERTA` = 10) por usina,
  sem exclusão nos dois lados (o arquivo do PCM não traz o responsável da OS, então o backoffice não se aplica a ele),
  e o efeito de cada exclusão à parte. Diferença que não seja de horário precisa de explicação antes de ir para a
  tela.

## Na tela

**Faixa "Parada agora"** (acima dos blocos): cada OS de parada aberta nas usinas do filtro, com a usina, o que parou
(o escopo e o código do ativo), a OS e desde quando; a mais antiga primeiro; as primeiras e "e mais N" quando forem
muitas. Sem parada, a faixa não aparece.

**Coluna Limpeza** (Acompanhamento, entre Ronda e PT): sujidade e vegetação da última leitura, no formato das Rondas
(número com a cor da régua); no detalhe, o dia da ronda, a vala e os sensores. Entra no nível da linha do
Acompanhamento; a ordem do bloco continua pela ronda.

**Bloco Manutenção** (embaixo, largura toda), com o mesmo desenho dos outros dois: cabeçalho com o resumo do grupo,
colunas, uma linha por usina com a cor do nível, e o detalhe ao abrir.
- Colunas: Usina | OS abertas | Atrasadas | Vencem até amanhã | Paradas (motivo) | Semana | Zeladoria.
- **O que conta em OS abertas, Atrasadas e Vencem até amanhã** (escolha do Claude, para nada contar duas vezes): as
  tarefas de OS não finalizadas, em processo e em verificação (a tarefa "viva" do PCM), MENOS as do backoffice (decisão
  do Levi), as que têm motivo ativo que tira da programação (já contam em Paradas), as OS que estão no `fato_chamado`
  (já contam em Chamados, no Acompanhamento), as tarefas do tipo Zeladoria (coluna e régua próprias) e as do tipo
  Teste (o PCM também tira).
- **OS abertas:** quantas OS; no detalhe, quantas delas estão em verificação, esperando aprovação.
- **Atrasada:** a régua do PCM, tarefa aberta com a Data Programada há mais de 10 dias, contada **por tarefa** como o
  PCM conta (escolha do Claude, para o número bater com o dele); o detalhe diz também em quantas OS. A célula mostra
  quantas e o maior atraso. Atrasada vai para Acompanhar; acima do limite do supervisor, Focar.
- **Vencem até amanhã:** tarefas programadas para hoje ou amanhã, ainda não finalizadas. Só informa.
- **Paradas:** quantas tarefas da usina estão no Fora da programação, e o motivo mais comum.
- **Semana:** a aderência da semana passada, fechada, pela conta do Fechamento da semana do PCM (linhas do plano
  finalizadas ÷ linhas do plano da usina), com a meta dele: 85% ou mais em dia, abaixo disso Acompanhar. No detalhe, o
  dia de hoje até agora: as tarefas de hoje cujo horário de início (`hora_inicio`) já passou, quantas estão
  finalizadas; só informa, porque o feito chega com até 1,5 h de atraso (o robô do PCM e a cópia aos :40). Nota na
  tela: a semana vem do arquivo do PCM, copiado para o banco de hora em hora.
- **Zeladoria:** a próxima programada (data) e, no detalhe, a última feita.
- **O limite das atrasadas:** um campo no cabeçalho do bloco ("Focar tarefa atrasada há mais de N dias"), começando em
  30 e aceitando de 10 a 365 (atrasada já é mais de 10). Muda o nível e a ordem na hora; fica num cookie do navegador,
  respeitando o prefixo do endereço (`na_raiz`).
- **Detalhe da linha:** as OS atrasadas (a mais atrasada primeiro, as primeiras e "e mais N"), a OS abrindo o card dela
  no Nexus como a Gestão PCM faz; as tarefas paradas com o motivo, desde quando e quem marcou; a semana; a zeladoria;
  e quantas OS esperam aprovação (em verificação), só para informar. Links: Gestão PCM, Fora da programação, Quadro da
  semana e Aprovação de OS.
- **Cartões por responsável** (o modo de quem não é responsável): ganham o terceiro mini-bloco, Manutenção, com a
  triagem e os números (Atrasadas, Paradas, Semana).
- **Nota das réguas** (a da Visão): ganha as réguas de Manutenção e de Limpeza.
- **Fonte que falha:** cada uma isolada (`_ler_fonte`): a que falha fica de fora e a tela diz qual; o resto vale. Sem o
  fato novo no banco: "As OS do Fracttal ainda não chegaram ao banco", e o bloco não cobra por elas.
- **Desempenho:** a tela não lê o Fracttal; lê o banco, com a cópia de 5 min que a Visão já usa.
- **375 px:** os blocos empilham, como hoje; a linha do bloco Manutenção segue o padrão das outras no celular.

## Como provar que funciona

- Testes de cada regra num dia fixo: atrasada (10 e 11 dias; 30 e 31 com o limite padrão; o limite mudado pelo
  cookie), as exclusões (backoffice, motivo que tira, OS de chamado, zeladoria, Teste), parada de usina e de
  equipamento, a semana fechada (84,9% e 85%) e o dia de hoje antes e depois do horário de início, zeladoria vencida e
  sem zeladoria, a ordem do bloco, a Limpeza na régua das Rondas. Com mutações que os testes pegam.
- A semana fechada por cliente igual à tabela "Por cliente" do Fechamento da semana do PCM, na mesma semana.
- Testes do fato: grão, a ligação que não chuta, nada de nome, domínios, a leitura incompleta que não grava, a pausa
  depois do 429 e a regra 11, com o `tests/pg_falso.py`.
- O ensaio com o Fracttal de verdade e a comparação com o `gestao_pcm.json` (acima), com os números escritos no
  `nexus/dados/CLAUDE.md`.
- A tela na cópia de prova (porta 5170), escuro e claro, a 1920 px, 1366 px e 375 px.
- Atualizar no mesmo trabalho: `nexus/torres/campo/CLAUDE.md` (Visão do responsável), `nexus/dados/CLAUDE.md` (o fato
  novo e a 1ª medida) e o catálogo.

## Fica para o construtor

O endpoint e os campos exatos do Fracttal e a paginação; as listas de domínio; o nome final do livro; quantos itens
cada lista do detalhe mostra; o desenho fino do campo do limite e do CSS (sempre por token, nos dois temas).

## Pendente fora deste trabalho

- **Do Levi:** o PCM gravar a semana direto no banco, para a Semana deixar de depender do arquivo do GitHub.
- **Próximas peças:** ranking das equipes, mapa das usinas, ocorrências com plano de ação.
