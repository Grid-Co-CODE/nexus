# Visão do responsável: o Ranking das equipes — desenho

18/10/2026. Pedido e decisões do Levi nesta data; o que é escolha do Claude está marcado como tal.

## Por que

O objetivo (Levi, 18/10/2026) é os responsáveis O&M largarem os painéis próprios e usarem só o Nexus. Esta é a peça 2 de
quatro, na ordem combinada: (1) a manutenção na Visão (no ar desde 18/10; desenho em
`2026-10-18-visao-responsavel-manutencao-design.md`), (2) o ranking das equipes, aqui; (3) o mapa das usinas; (4) as
ocorrências com plano de ação.

**A pergunta que o ranking responde:** "qual equipe cobrar". O responsável abre o ranking e vê as equipes das usinas
dele da pior para a melhor e, em cada uma, em quê cobrar.

**De onde veio a régua.** O painel próprio de um supervisor (o export de 16/10/2026 que motivou estas peças) **não tem
ranking**: cita só uma seção "Eficiência O&M", desenhada por script, sem a conta. O Levi decidiu que a posição segue as
regras do ranking do App de Campo. O App tem duas réguas de ranking (`function_app.py`, v283):

- **Ranking por região** (`_ranking_regioes`, rota `gestao/ranking`; no painel do App, Desempenho > Regiões, "Ranking ·
  Regiões"): por cluster, nota composta = 60% qualidade + 40% cobertura. É um quadro de gestão (o técnico não o vê, não
  tem pontos nem prêmio) e é a **única conta por equipe que existe no App**. É a escolhida.
- **Placar do ciclo** (`_ciclo_v2`; no painel, Desempenho > Colaboradores): pontos por **técnico** e mês do calendário. É
  o ranking que o campo reconhece (o técnico vê a posição no App; tem prêmio para os três primeiros e a corrida do
  campeão), mas é só individual: o App não tem soma, média nem prêmio por equipe. Não serve hoje (abaixo, "O que não dá
  para fazer").

A sessão do App de Campo confirmou as duas leituras no código que está no ar (v283, em 18/10/2026) e que não há regra de
ranking por equipe no código, nos documentos nem na memória do App: para equipe, a regra é a que o Levi escolher.

## Objetivos

1. Uma aba nova na Visão do responsável, **Ranking das equipes**, ao lado de Onde focar.
2. Um cartão por equipe, **da pior para a melhor**, com a posição e a nota da régua do App.
3. No cartão, **em quê cobrar**: os números da Visão por equipe, na régua de cada tela dona. Eles **não mudam a
   posição**.
4. A **seta**: a nota e a posição contra os 30 dias anteriores.
5. Clicar no cartão leva a **Onde focar só com as usinas da equipe**.
6. Só banco do Nexus e Fracttal como fonte (a regra do Levi para estas peças). Nada novo no banco.
7. O Índice por equipe da tela Rondas › Painel passa a se chamar **Índice das rondas** (só o texto: rótulos, nota da tela,
   docstring e `CLAUDE.md`), para não haver dois números com o mesmo nome.

## Não objetivos

- O placar do ciclo por equipe (pontos dos técnicos): espera o App publicar o livro `ranking_app_campo`.
- Régua nova. A posição é a do App; o que a Visão sabe fica ao lado.
- Guardar o ranking no banco (histórico de posições). A seta sai dos fatos que já existem.
- Escrever no App ou no Fracttal.
- Ranking de técnicos (já existe a tela Ranking de pontos, que mostra o placar do App quando ele chegar).

## Anti-objetivos (falharia mesmo funcionando)

- Nota que não segue a régua do App sem dizer por quê. Toda diferença conhecida (abaixo, "Diferenças contra o painel do
  App") aparece na nota da tela.
- Posição decidida por número que a tela não mostra.
- Equipe sumindo da lista por não ter nota: ela aparece, sem posição, e a tela diz por quê.
- Nome de pessoa no repositório (público): teste com nome fictício; nenhum nome de técnico ou supervisor em arquivo
  versionado, nem nome de equipe ao lado do desempenho dela.

## As decisões do Levi (18/10/2026)

| Assunto | Decisão |
|---|---|
| Para quê | Qual equipe cobrar |
| Quem entra | O responsável vê as equipes das usinas dele; quem não é responsável (coordenador, administrador) vê todas. Segue o filtro de responsável que a Visão já tem |
| O que decide a posição | A régua do App, "de acordo com as regras do ranking do app de campo": o Ranking por região, 60% qualidade + 40% cobertura. Depois de ver o dado real (uma equipe em 1º com 37 tarefas atrasadas e a semana em 11%, porque as 12 equipes do responsável tinham 100% de cobertura): "Fica a régua do App" |
| Os outros números da Visão | Só aparecem ao lado ("em quê cobrar"); não mudam a posição |
| Forma | Cartões (o protótipo B), da pior para a melhor; o cartão v2 do protótipo foi aprovado ("Está bom") |
| Seta | Sim, contra o período anterior |
| Clique | Onde focar, só com as usinas da equipe |
| Janela de tempo | **30 dias**, de hoje − 29 a hoje (a sessão do App de Campo, perguntada a pedido do Levi, respondeu que não há janela oficial: a barra do painel começa em 30 dias, `PER='30'`, e o servidor usa 30 sem janela; o ciclo é por mês do calendário, o ranking por região por janela móvel) |
| O Índice do Painel das Rondas | **Renomear** para "Índice das rondas": a mesma fórmula 60/40, mas só com as rondas e no período da tela Rondas. Sem isso, a mesma equipe teria duas "notas do App" diferentes na mesma torre |

## A régua (a do App, sobre o dado do Nexus)

Para cada equipe, sobre as usinas **mobilizadas** dela que passam pelos filtros da tela, no período P:

- **Qualidade** = a média simples, arredondada, de todas as notas do período, cada uma com o mesmo peso: a "Nota do
  painel" de cada **tarefa** fechada pelo App (`fato_fechamento.nota_pts`: uma linha por tarefa, como o qlog do App) e a
  "Nota da ronda" de cada ronda do App (`fato_ronda.nota_pts`). Uma média só, sobre tarefas e rondas juntas, como o App
  faz (`q_soma / q_n`). Nota vazia não entra.
- **Cobertura** = usinas da equipe com ronda no período ÷ usinas da equipe, em %, arredondada.
- **Nota** = arredondamento de 0,6 × qualidade + 0,4 × cobertura.
- **Sem nota:** equipe sem nenhuma nota no período (nenhuma OS nem ronda do App). O App a deixa fora do ranking; o Nexus
  a mostra sem posição, com "sem nota do App: nenhuma OS nem ronda pelo App em 30 dias" (escolha do Claude: para quem
  cobra, é o pior caso, e sumir a esconderia). Esses cartões vêm **antes** dos ranqueados.
- **A cor da nota**: a escala de cor do painel do App (`qcor` no `gestao.html`: 85 ou mais verde, 70 ou mais âmbar,
  abaixo vermelho), a mesma que o painel usa na nota composta e em outros números. **Não é régua oficial da nota**
  (confirmado pela sessão do App: não há corte decidido para a composta); a tela diz "a cor do painel do App" e não
  "exemplar" ou "crítico" como julgamento.
- **A ordem** do App é só a nota, da maior para a menor. Empate (medido: 41 das 52 equipes com nota dividem 10 notas):
  maior qualidade, maior cobertura, mais notas no período (o ciclo do App desempata pelo volume, as tarefas contadas), o
  nome (escolha do Claude: o ranking por região do App não desempata, e a ordem dele no empate é a da leitura das
  tabelas). A posição 1 é a melhor, como no App; a tela mostra da última para a 1ª e diz o desempate.
- **Período P** (decisão do Levi): os últimos 30 dias, de hoje − 29 a hoje, pelo dia de Brasília do fato (`data_id`),
  como o "Últimos 30 dias" do painel do App. **Anterior**: de hoje − 59 a hoje − 30; a usina mobilizada depois do fim
  dele fica fora da conta dele (revisão do ramo: ela contava como "sem ronda" e a seta subia sozinha). A janela fica
  numa constante.
- **A ronda avulsa** (lançada à mão no Nexus) conta na cobertura (decisão do Levi de 07/10/2026 para a cobertura das
  Rondas) e não tem nota. A validação por foto não é ronda (fica fora, como em todo o Campo).

### Diferenças contra o painel do App (a tela diz)

1. **A equipe é a da usina nos dois**, mas por cadastros diferentes. O App põe a OS no cluster da tarefa na programação
   do PCM (sem ela, no cluster da usina no catálogo do App; só em último caso no 1º cluster da pessoa: "senão o apoio
   fora do cluster contaria para a região errada", regra do App de 31/07) e a ronda no cluster da usina no catálogo do
   App. O Nexus põe as duas na equipe da usina no cadastro do Nexus (`usinas.equipe_id`), a regra de todo o Campo. Se o
   catálogo do App e o cadastro do Nexus divergirem numa usina, a equipe diverge; o conserto é no cadastro.
2. **A base da cobertura** são as usinas mobilizadas do cadastro (status OPERAÇÃO e mobilização já passada), não o
   catálogo de usinas do App. (No App, a região sem usina no catálogo fica sem cobertura e entra com 0 na composta; no
   Nexus toda equipe da lista tem ao menos uma usina, então isso não acontece.)
3. **O dia** é o de Brasília do registro; o App corta pela hora do servidor. Muda só quem fechou perto da meia-noite no
   1º dia do período.
4. **A ronda avulsa** (lançada no Nexus) conta na cobertura; o App não a conhece.

## Na tela

**A aba.** Na barra da Visão: Por responsável | Onde focar | **Ranking das equipes** (`modo=ranking`). O responsável que
entrou pelo Fracttal (que hoje não vê a barra) passa a ver **Onde focar | Ranking das equipes**, e continua sem os cartões
dos outros. Os filtros da Visão valem (responsável, cliente, busca); a posição é entre as equipes que sobram.

**Em cima (os números do painel do App):** Equipes (e técnicos), Melhor nota (a equipe), Menor nota (a equipe) e
Amplitude (da 1ª à última). Estão no cartão v2 aprovado; no painel do App, uma revisão de 13/08 os julgou decoração (a
proposta de tirar não foi executada). E a régua numa frase: como a nota é feita, que a posição é só a nota, o que a
seta compara, que a cor é a do painel do App, e as diferenças contra o painel do App.

**O cartão** (o v2 aprovado):

- A **posição** ("12º de 12") e a **seta**: "sobe 3", "desce 2", "mesma posição" ou "sem nota antes"; a posição de antes é
  a da mesma lista de equipes no período anterior.
- A **nota** na cor do painel do App (85 ou mais verde, 70 ou mais âmbar, abaixo vermelho; ver "A régua").
- O nome da equipe e "base pequena" quando tem menos de 3 usinas (`visao.BASE_PEQUENA`, a mesma do Painel das Rondas);
  embaixo: usinas, técnicos (contagem, do cadastro) e a região de campo.
- A **composição**: qualidade, cobertura, quantas OS e rondas entraram, e a nota e a posição de antes.
- O **semáforo dos três blocos** (Performance, Acompanhamento, Manutenção): quantas usinas em Focar, Acompanhar e em dia,
  o mesmo `soma` dos cartões por responsável, com o limite das atrasadas de quem olha.
- **Em quê cobrar**: uma etiqueta por área com alerta nas usinas da equipe, tirada dos MESMOS alertas que fazem o
  semáforo do cartão (os três blocos, nas réguas das telas donas e no limite das atrasadas de quem olha), no nível do
  pior alerta da área; o crítico primeiro, até 4 e "e mais N"; "nada a cobrar nos três blocos" só com o semáforo todo em
  dia. Correção da revisão do ramo (18/10/2026): no 1º desenho eram 12 números à parte, e uma equipe só com um ativo em
  crítico mostrava "nada a cobrar". O texto usa o número do grupo quando a Visão tem (tarefas atrasadas e a mais antiga,
  PT paradas, extintores vencidos, chamados, tarefas paradas, a semana do grupo) e, senão, quantas usinas. Para a meta,
  conta **usinas abaixo de 97%** e não a meta somada do grupo (escolha do Claude: medido em 18/10, uma usina com produção
  de 10,7 GWh contra meta de 149 MWh põe a equipe em 2.207%); na disponibilidade, as usinas abaixo de 99% (ou de 80%), e
  não a média do grupo pela potência. Uma legenda diz o que são os três números do semáforo (cor e palavra).
- **Clicar** abre Onde focar só com as usinas da equipe: filtro novo `equipe=` na Visão (o nome exato da equipe do
  cadastro), com o "×" para tirar, como os outros filtros. A busca continua.

**A equipe "Sem equipe"** (usinas sem equipe no cadastro; medido: 2 usinas) aparece no fim, sem posição, com "conserto no
cadastro" (escolha do Claude, como o "Sem responsável O&M" dos cartões).

**375 px:** os números de cima em 2 × 2, um cartão por linha, sem rolagem lateral. **Temas:** escuro e claro, cor só por
token do `nexus.css`.

## De onde vem cada número

| Na tela | Fonte | Fracttal ou Nexus |
|---|---|---|
| Qualidade (OS) | `nexus_fatos · fato_fechamento.nota_pts` = a "Nota do painel" do livro `fechamentos_app_campo`, que o App publica de hora em hora (a mesma `qualidade` do qlog que o ranking do App usa) | Banco do Nexus (o App publica) |
| Qualidade (ronda) e cobertura | `nexus_fatos · fato_ronda` (`nota_pts` = a "Nota da ronda" do `rondas_app_campo`; a avulsa do Nexus conta só na cobertura) | Banco do Nexus |
| Equipe, usinas, técnicos, região de campo | `cadastro_nexus` (`usinas.equipe_id`, a equipe e os colaboradores de campo dela) | Banco do Nexus |
| Usinas mobilizadas | `cadastro_nexus` (status e data de mobilização) | Banco do Nexus |
| OS de parada aberta | `falhas_performance · disponibilidade_os` (a plataforma publica do Fracttal) | Banco do Nexus, vindo do Fracttal |
| Tarefas atrasadas, paradas, zeladoria | `nexus_os · fato_tarefa_os` (o Nexus lê o Fracttal de hora em hora) e os motivos do PCM | Banco do Nexus, vindo do Fracttal |
| Semana passada | `nexus_programacao · fato_programacao` (cópia do arquivo do PCM) | Banco do Nexus; a única fonte externa, como no bloco Manutenção |
| Rondas pendentes, limpeza | a Central de atenção e as Rondas (`fato_ronda`; a limpeza também pelo texto da OS de ronda no Fracttal) | Banco do Nexus e Fracttal |
| PT parada | `fato_pt` | Banco do Nexus |
| Extintores | `extintores_app_campo` | Banco do Nexus |
| Meta, disponibilidade | `nexus_performance · fato_meta_usina_mes`, `falhas_performance · disponibilidade_dia` | Banco do Nexus |
| Chamados | `nexus_chamados · fato_chamado` | Banco do Nexus, vindo do Fracttal |

Nada novo vai ao banco: a conta é feita na tela, sobre os fatos que já existem (nenhum livro, catálogo ou fato novo).

## O que não dá para fazer, por falta de dado

1. **O placar do ciclo por equipe** (os pontos dos técnicos somados ou na média): o App ainda não publica o placar no
   banco (o livro `ranking_app_campo` não existe; o pacote do lado do App, preparado em 13/10, não foi aplicado; na v283 o
   `NEXUS_COLUNAS` não tem "ranking"). Recalcular o placar no Nexus já deu errado (a nota do coletor batia com a do
   painel do App em 14% das tarefas, 05/10): quem calcula é o App.
2. **A usina no cluster pelo catálogo e pela programação do App**, igual ao painel do App: o catálogo do App não está no
   banco. O Nexus usa o cadastro do Nexus; onde os dois divergem, o número diverge (o conserto é no cadastro).
3. **OS fechada direto no Fracttal, sem o App:** não tem nota, então não entra na qualidade (no App também não).
4. **Seta além de 60 dias** (o mês a mês): o livro de fechamentos do App guarda 90 dias. Histórico mais longo pediria
   guardar o ranking num fato novo. Fora deste trabalho.
5. **Seta para o "em quê cobrar":** as atrasadas, a zeladoria e as paradas são uma foto de agora (`fato_tarefa_os` não
   guarda o passado). Só a nota do App tem seta.
6. **Horas e produtividade do técnico** (ponto, jornada): não existem no Nexus.
7. **Duração das OS no Fracttal** (tempo de execução): o livro do App não traz as durações do Fracttal.

## Medido em 18/10/2026 (banco real, só leitura)

131 usinas mobilizadas, 55 equipes com usina, 8 responsáveis; cada equipe tem um responsável só; os quatro maiores têm
11 ou 12 equipes. Usinas por equipe: 13 com 1, 22 com 2, 13 com 3, 7 com 4 a 6 (35 de base pequena). Nos 30 dias: 52
equipes com nota, de 41 a 98 (mediana 92,5); qualidade de 69 a 100 (mediana 88); cobertura de 0 a 100% (mediana 100%);
3 sem nota (uma é "Sem equipe"). Contra os 30 dias anteriores: a nota variou de −12 a +53 (mediana +1); 51 equipes
tinham nota antes. Nas 12 equipes de um responsável, todas com 100% de cobertura, a nota foi de 85 a 96, e a equipe em
1º tinha 37 tarefas atrasadas, a semana passada em 11% e nenhuma OS fechada pelo App em 30 dias (a nota dela veio de 5
rondas).

## Como provar que funciona

- **A régua, num módulo puro** (escolha do Claude: `nexus/campo/ranking_equipes.py`), com testes num dia fixo: a média
  única de OS e rondas; o arredondamento (0,6 × 79 + 0,4 × 50 = 67,4 → 67); a cobertura sobre as usinas da equipe que
  passam pelo filtro; a avulsa na cobertura e fora da qualidade; a nota vazia fora; os limites do período (hoje − 29
  dentro, hoje − 30 no anterior); a cor em 84/85 e 69/70; o desempate; a equipe sem nota (sem posição, antes das
  ranqueadas); a "Sem equipe" no fim; a seta (sobe, desce, mesma, sem nota antes). Com mutações que os testes pegam.
- **Contra o App:** a mesma conta sobre o mesmo conjunto de notas dá o mesmo número que o `_ranking_regioes` (um teste
  com a fórmula do App copiada como referência, num caso pequeno).
- **A tela** (`tests/test_campo_responsaveis.py`): a aba aparece para o administrador e para o responsável logado; o
  responsável vê só as equipes dele; o filtro de cliente muda a lista; o cartão leva a `modo=foco&equipe=`; o filtro
  `equipe=` em Onde focar e o "×".
- **No navegador**, com o dado real (cópia de prova, só GET): 1440 e 375 px, escuro e claro, sem rolagem lateral.
- **Desempenho:** a conta da tela não pode pesar. O agregado por usina (notas e ronda nos dois períodos) entra na cópia
  de 5 min da Visão (`visao_responsaveis`); o agrupamento por equipe sai no pedido (os filtros mudam). Medir a conta fria
  antes e depois (hoje ~24 s, em segundo plano).
- **O Índice das rondas:** a tela Rondas › Painel diz "Índice das rondas" no cabeçalho, no destaque e na nota (teste da
  tela), e nenhum texto dela chama esse índice de "a régua do ranking do App" sem dizer que é só com as rondas.
- Atualizar no mesmo trabalho: `nexus/torres/campo/CLAUDE.md` (Visão do responsável: a aba e a régua; Rondas › Painel:
  o nome novo do índice).

## Fica para o construtor

O nome das funções e das rotas internas; o desenho fino do cartão e da barra (sempre por token, nos dois temas); a ordem
fixa das etiquetas de mesma gravidade; o texto exato dos avisos.

## Pendente

- **Publicar o placar do ciclo no banco** (`ranking_app_campo`): depende do Levi; a sessão do App de Campo reaplica o
  pacote sobre a v283, roda a suíte e publica se ele pedir. Com o livro no banco, a tela Ranking de pontos passa a mostrar
  o placar, e o ranking por equipe pode ganhar os pontos ao lado.
- **Achado fora deste trabalho (Performance):** a meta do mês de uma usina no `fato_meta_usina_mes` está com produção de
  10,7 GWh contra meta de 149 MWh (7.209%), e duas usinas passam de 200%. Conserto na publicação do Gerencial.
