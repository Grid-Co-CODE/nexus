# CLAUDE.md — torre Campo · App

A visão do Nexus sobre o trabalho de campo. **Nenhuma tela abre o painel do App nem aponta para o Azure** (Levi,
05/10/2026: "quero parar de referenciar o Azure e ter uma visão nossa!"): todas leem o banco do Nexus (API db_performace).
Leia também o `CLAUDE.md` da raiz e, antes de pôr dado novo no banco, o `nexus/dados/CLAUDE.md` (PRIORIDADE 0).

## Regra: tudo em paralelo (Levi, 04/10/2026)

"Por hora todas as decisões para o Nexus são paralelas, não deve afetar o funcionamento atual." Nada aqui escreve no
App nem no Fracttal. Devolver OS e encaminhar ponto continuam no App. Sem link para o painel do App e sem
"Abrir no App". **A OS aparece só com o número, sem "#"** (Levi, 05/10: "Em OS tira esse #").

**Exceções: a decisão da PT** (Levi, 05/10: "Técnico faz APR e PT -> Chega no PG -> Atualiza para os steakholders ->
Atualiza na aprovação de PT -> Supervisor faz -> Fica salvo!"; ver "Aprovação de PT no Nexus" abaixo) **e o Aprovar da
Aprovação de OS** (o Concluir do OS Creator no Fracttal, só para quem aprova a OS: o Supervisor de Campo da região da
usina, com a vaga aberta o Coordenador de Campo, ou um admin; ver "Aprovação de OS" e "Estrutura de O&M de 10/2026").

## As telas

| Tela | De onde vem | Quem calcula |
|---|---|---|
| Central de atenção | `fato_ronda` e `fato_pt` (passo 4, ver "De onde vem o dado") + cadastro do Nexus | `visao.atencao` (conta nossa) |
| Aprovação de OS | fila de verificação do Fracttal INTEIRA (só GET) + nota do livro do App; Aprovar pelo portão `/os/_nexus/aprovacao/<id>/aprovar` | regras copiadas do App |
| Permissões de trabalho → **em Segurança · HSEQ > APR e PT desde 09/10/2026** (`/t/hseq/apr-pt`; `/t/campo/pt` leva para lá). O código continua aqui (`pagina_pt`, a aprovação `/t/campo/pt/<número>`, os PDFs da PT e da APR); a regra de lá está em `nexus/torres/hseq/CLAUDE.md` | `fato_pt` (+ `pt_app_campo` para o texto) | `visao.pts` (conta nossa) |
| Rondas | `fato_ronda` (App, checklist da carga única, avulsa) + usinas mobilizadas do cadastro + `fato_fechamento` (última OS da usina) + a validação por foto (só sujidade e vegetação) | `visao.rondas` (conta nossa) |
| Ronda avulsa (`/t/campo/rondas/avulsa`) | lançada à mão no Nexus, com o login do Fracttal | `campo/ronda_avulsa.py` |
| Zeladoria | `zeladoria_app_campo` | `visao.zeladoria` (conta nossa) |
| Triagem de qualidade | `fechamentos_app_campo` + rondas | regras copiadas do App |
| Rotas do dia | placeholder: programação do PCM + localização das usinas | — |

**Saíram em 08/10/2026: Ordens de serviço, Imagens da ronda e Ranking** (Levi: "ordens de serviço e imagens da ronda e
ranking são redundantes"): a nota do fechamento está na Aprovação e na Triagem, a comparação por região, equipe e
supervisor no Painel das Rondas, as fotos no histórico da usina. Saíram do menu, com rota, template, `campo/ordens.py`,
`visao.ranking` e os testes delas; `/t/campo/os`, `/ranking` e `/imagens` levam à Central (`TELAS_QUE_SAIRAM`, para
quem guardou o endereço). O `_gestao_os` (a conta da antiga Ordens) saiu da cópia das regras do App na recópia de 09/10
(ver "As contas copiadas do App").

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
- **O técnico das rondas pelo código** (passo 2 do Kimball, lado do Nexus, 08/10/2026): o App vai trocar a coluna
  `Técnico` (nome em claro, na API de leitura aberta) do `rondas_app_campo` por `Técnico (HMAC)` (pacote
  `C:\GridcoBuild\app-campo-docs\_propostas\rondas-tecnico-hmac\LEIA.md`). O Nexus aceita as DUAS, inclusive misturadas
  no mesmo livro (uma leitura no meio do `sync-xlsx` pega linha com o cabeçalho velho e com o novo):
  `livros_app.nome_do_tecnico` traduz o código pelo `pessoas_por_codigo`, como nos outros livros, para a fonte das
  regras copiadas (`fonte_pg._do_app("rondas")`) e para a tela; o `fato_ronda` liga a pessoa pelo HMAC primeiro. Código
  sem dono fica sem nome, nunca o código na tela. Sem `NEXUS_PESSOA_HMAC` a tela não quebra e diz quantas rondas ficaram
  sem o nome do técnico. **Ordem:** este código no servidor ANTES do App publicar o pacote.
- **As telas leem o FATO** (passo 4 do Kimball, Levi, 08/10/2026; `visao._fato`): Rondas, Central de atenção e PT tiram
  a contagem e a ligação (`usina_id`, `pessoa_id`, `data_id`) do fato conformado (`nexus_fatos` · `fato_ronda`,
  `fato_pt`, `fato_fechamento`). Antes a tela refazia a ligação a cada conta com um `Ligador` dela e lia o checklist da
  carga única à parte: duas regras para a mesma conta. O que o fato não tem (veredito, pendências, observação, horários,
  o texto das falhas e da situação da OS, tarefa e motivo da PT, a região escrita pelo App) vem do livro cru, juntado
  pela chave do fato: a ronda do App pelo `Início` (`ronda_id = sha1("app|"+Início)`), a avulsa pelo `ronda_id` dela,
  a PT pelo `pt_linha_id` (Número + Código do ativo), o fechamento pelo `fechamento_id` (`fatos.chave_fechamento`).
  O fato do banco vale quando a `qualidade` dele diz que saiu da MESMA versão do livro do App que a API tem agora
  (`origem_atualizada_em` = `updated_at`; na ronda, também nenhum lançamento de avulsa depois da carga) e a carga não
  falhou nele. Senão a tela monta o fato NA HORA com a mesma função da carga (`carga.montar_ronda`, `montar_pt`,
  `montar_fechamento`, o mesmo `carga.ligador` e a mesma tradução da pessoa, `carga.mapas_das_linhas`; sem o
  `equipamento_id`, que a tela não usa) e diz no topo, discretamente: "fato_ronda calculado na hora; o banco ainda não
  tem" ou "o banco tem a carga das 15:40, de antes do livro do App das 15:50". Por que a versão: o App regrava as
  rondas aos :50 e a carga roda aos :40; o fato velho atrasaria "Rondas finalizadas hoje" em até ~50 min. Em 08/10 o
  banco só tem o `fato_fechamento` (do código antigo do servidor, usado das :40 às :25); ronda e PT saem na hora até o
  servidor rodar o código novo. Livro com a mesma ronda duas vezes (grão quebrado) não vira número em dobro: a tela
  mostra o fato anterior do banco com aviso ou, sem ele, diz o erro.
  **Prova (08/10, banco real só por GET, as MESMAS respostas para o código de antes e o de depois, hora congelada; 368
  páginas: as 6 abas de Rondas, os filtros e os 40 clusters em 7, 14 e 30 dias, o histórico das 128 usinas, a Central
  em 3 visões × 2 abas × 3 períodos, a PT nas 3 visões e no histórico de 7, 30 e 90 dias, as 47 PT esperando):** indicadores, Sem
  ronda, Quem ronda (cluster e pessoa), Painel, Central por equipe e por supervisor e PT iguais valor a valor, salvo três
  diferenças, todas da ligação do fato: (1) uma ronda de 876 tem a "Data" do App em 06/10 e o início em 07/10 às 09:09
  de Brasília: pela regra 7 do `nexus/dados` (o dia é o de Brasília do início) é de 07/10; muda a última ronda daquela
  usina (2 → 1 dia) e a observação da pendência dela na Central; (2) uma ronda de 05/10 estava sem OS na carga única
  do checklist (06/10) e ganhou OS depois: o fato casa a resposta pelo `Início`, e a tela antes só olhava a carga única
  para ronda SEM OS; sem o texto da OS lido do Fracttal, a Sujidade ganha a leitura dela (1 usina a mais com leitura em
  7 e 14 dias; em 30, a usina troca a leitura de 16/09 pela de 05/10); com a OS lida, vale o texto da OS, como antes;
  (3) o técnico ligado ao cadastro aparece pelo "Nome padrão" da ficha (192 das 874 rondas de usina mobilizada mudam de
  grafia; no livro, 79 grafias viram 54 pessoas) e Quem ronda agrupa por `pessoa_id`: os números de 7, 14 e 30 dias
  não mudaram. O fato do banco
  (`fato_fechamento` do servidor) e o montado na hora deram as mesmas 368 páginas. **Desempenho:** tela quente igual
  (10 telas somadas, mediana de 60 pedidos, 5 rodadas: 114 a 153 ms antes, 110 a 142 ms depois); a conta fria, que o
  `manter_quente` faz em segundo plano, gasta +20 a +40 ms de CPU (decifrar o cadastro para ligar a pessoa e montar o
  fato) e, com o fato no banco, lê também `/api/workbooks`, a `qualidade` e o fato.
- **Usina, pessoa e dia vêm do fato, que liga pelo `Ligador`** da camada de dados (`nexus/dados/fatos.py`): de-para "Fracttal ·
  Classificação 1" (a parte depois de " · "), de reserva o código da usina dentro do código do ativo (só se for
  único). A base da cobertura, do Painel das Rondas e da Central são as **usinas mobilizadas**: status `OPERAÇÃO` E data de
  mobilização já passada (Levi, 05/10: "tem usina que nem mobilizada está"; medido: das 177 em OPERAÇÃO, 49 sem data
  de mobilização e nenhuma delas com ronda pelo App; as 107 com ronda têm a data). A PT não passa por esse filtro: PT
  esperando decisão aparece sempre. Onde a tela mostra a usina, mostra **Equipe, Estado e Região do Brasil** do
  cadastro (e, da estrutura de O&M de 10/2026, a região de campo e o gestor de contrato: seção própria abaixo), nunca a
  "Região" que o App escreve (Levi: "uma hora é '-' outra é o nome da UFV, outra é o nome do
  cluster"). A **região do Brasil sai da UF** (`visao.REGIAO_DA_UF`), não da coluna `regiao` do cadastro: medido em
  05/10, ela diz "Sudeste" para Alto Paraná 1 e 2 (PR), "Nordeste" para Ponto Belo 1 (ES), está vazia em Aquiraz e
  Cascavel (CE) e mistura "Centro Oeste" com "Centro-Oeste". Conserto da coluna é no cadastro. Pessoa aparece pelo
  **"Nome padrão" da ficha** do cadastro, pelo `pessoa_id` do fato (desde 08/10); sem ficha, pelo nome resumido do que
  o livro traz (`visao.nome_curto`: primeiro e último nome). A equipe da tela é a da USINA no cadastro, não o
  `equipe_id` do fato (que é o papel "registro", a equipe que o App anotou). A Aprovação de OS liga a usina do Fracttal (Classificação 1) ao cadastro pelo de-para (`visao.usinas_do_fracttal`). Região que o App
  escreve e o cadastro não tem (medido em 05/10: "MT Sul 02", 15 fechamentos; "Grid Co.", 1) vai para "fora do
  cadastro", não some. Conserto é no cadastro.
- **O que o livro ainda não traz:** a situação da OS no Fracttal, as durações do Fracttal, a aprovação e a avaliação (o
  App guarda de madrugada, `_enriquecer_qlog`, e não manda). Ficam desconhecidas, não aproximadas (com a duração do
  celular o "tempo vs. previsto" dava 5.726%; com a situação pela revisão do painel, 402 de 447 "em verificação"); a
  Triagem não acusa demora nem divergência de supervisor por isso. Para ter: o App mandar essas colunas (mudança no App).
- **Zeladoria vazia é real:** em 90 dias o App não registrou nenhuma etapa de zeladoria. A tela diz isso.

## As contas nossas (`nexus/campo/visao.py`)

As constantes ficam no topo do arquivo; cada função diz a regra no docstring.
- **Rondas** (05/10, no estilo do painel de rondas que o Levi mostrou; refeita em 08/10 pelo pedido dele): sete
  indicadores do período (`painel_rondas`, depois dos filtros de região do Brasil, cliente, região de campo, gestor de
  contrato e equipe) e seis abas:
  Registros, Painel, Sujidade e vegetação, Sem ronda, Trackers e Quem ronda. **A aba Cobertura saiu** (08/10: "já não
  faz sentido tendo o histórico da usina"); o endereço antigo `aba=cobertura` cai na Sem ronda. Toda tabela da tela
  ordena pelo cabeçalho, no navegador (`_ordenar.html`, `table.cn-ordenavel`: clicar de novo inverte, a seta é o
  `aria-sort`, vazio no fim, a linha de fotos ou de detalhe anda junto). A seta já marca a ordem que vem do servidor
  (Registros e Trackers pela data; Sujidade pelo Status; Painel pelo Índice; Sem ronda pela Última ronda), senão o 1º
  clique não mudava nada; a pessoa ordena pelo nome (`data-ordem`, não pelas iniciais do avatar) e o Veredito pela
  gravidade (o pior primeiro), não pelo alfabeto.
  - **Registros** (a tabela "Rondas diárias"; 08/10: "tira as colunas região, início e fim", "bote a coluna duração ao
    lado de data"): Data, Duração, Técnico, Usina, Equipe, Tipo, Qualidade, Veredito, Pendências, Trackers, OS, Fotos.
    O mouse (ou o foco do teclado) na duração mostra "Iniciou às 07:00 · terminou às 08:00 (Brasília)" numa dica fixa
    na tela (a rolagem da tabela cortaria uma dica presa à célula). O CSV continua com início, fim, estado e região.
    Até 300 linhas com o aviso; filtro de duração e de pendência; Exportar CSV com BOM para o Excel.
  - Cobertura = usinas mobilizadas com ronda no período ÷ mobilizadas; a seta compara com o período anterior de
    mesmo tamanho. Duração = fim − início carimbados pelo aparelho (0 a 8 h; fora disso, sem duração; o livro não
    traz a pausa). **Veredito = o `_veredito_ronda` do App, na mesma ordem, com os limites dele** (`LIMIARES_PADRAO`:
    60/85/95 e 10 min); o GPS só aparece como a falha "sem GPS". "Ronda longa pendente" é pendência para o App
    (vira Atenção). Medido em 08/10, 30 dias: 527 rondas, cobertura 83% (106 de 128), qualidade 96%, duração média
    47 min; 7 dias: 149 rondas, 66% (84 de 128).
  - **Os sete indicadores filtram a tabela** (Levi, 05/10): Rondas finalizadas = as de hoje (`ind=hoje`); Cobertura =
    a aba Sem ronda (`aba=sem`); **Nunca tiveram ronda** = `aba=sem&cob=nunca`; Qualidade = abaixo do limite
    (`ind=qualidade`); Duração = da mais longa para a mais curta (`ind=duracao`); Abaixo de 10 min = `dur=curta`; Usina
    mais atrasada = as há 7 dias ou mais (`aba=sem&cob=atrasadas`). O cartão ativo fica marcado; clicar de novo, ou no
    × do filtro, tira.
  - **Nunca tiveram ronda** (08/10: "em KPIs coloque mais um, quantas usinas nunca tiveram ronda";
    `visao._registro_da_cobertura`): usina mobilizada sem nenhuma ronda em TODO o registro do Nexus, não só no período:
    o livro de rondas do App, as avulsas e a carga `nexus_rondas_checklist`. O `title` do cartão diz desde quando vai o
    registro (a data mais antiga das três). Medido em 08/10: registro desde 11/08/2026; 19 de 128 mobilizadas nunca
    tiveram ronda (igual à conta antiga "999 dias": a carga só tem rondas que o livro também tem).
  - **Sem ronda** (08/10: "troque por uma tabela chamada 'Sem ronda' que mostrará usina, equipe, técnicos, supervisor e
    última OS feita na usina (para conseguir rastrear a última vez que o técnico foi lá)"): as mobilizadas sem ronda no
    período (padrão), há 7 dias ou mais (`cob=atrasadas`) ou nunca (`cob=nunca`), a mais esquecida primeiro (mais dias
    sem ronda; no empate, a última OS mais antiga). Colunas: Usina (link ao histórico), Equipe, Técnicos (colaboradores
    de campo não desligados da equipe, nome curto decifrado; sem a chave do cadastro, só quantos são), Região de campo
    (com o Supervisor de Campo embaixo, ou a vaga), Gestor de contrato, **Última OS na usina** e Última ronda (há quantos dias, o dia e quem fez). A última OS é a última de QUALQUER tipo
    fechada pelo App na usina, do livro `fechamentos_app_campo` ligado pelo `Ligador` (`visao._ultima_os_por_usina`):
    número, dia, tipo e quem fez. **Limite:** só o que passou pelo App, e o livro guarda 90 dias; OS fechada direto no
    Fracttal não aparece ("nenhuma pelo App"). Medido em 08/10: 113 de 128 mobilizadas têm a última OS; sem ronda em
    30 dias, 22 (18 com a última OS); em 7 dias, 44 (36); das 19 que nunca tiveram ronda, há usina com OS do App de 2
    dias antes (o técnico foi lá e não fez ronda). 6 usinas em equipe sem técnico no cadastro. Ler o livro de
    fechamentos deixou a conta fria da tela ~3,6 s mais longa (2.907 linhas, medido do PC); ela é feita em segundo
    plano (`manter_quente`) e a tela quente responde em 0,01 a 0,2 s.
  - **Painel** (08/10: "uma visão a mais, dashboards que mostre de fato, regiões com melhores indicadores, melhores
    coberturas, quais equipes tem melhor qualidade e cobertura, qual cliente, qual supervisor!"; `visao.comparativos`):
    respeitando o período e os filtros, uma tabela por região do Brasil (UF), equipe, cliente, região de campo (com o
    Supervisor de Campo embaixo do nome) e gestor de contrato (do cadastro: a região pela equipe da usina, o gestor pela
    usina; a de "supervisor" saiu com a estrutura de O&M de 10/2026) com Índice, Cobertura (barra), Qualidade (barra), Rondas e Duração média, melhor índice primeiro; em
    cima, o melhor e o que pede atenção de cada uma (sem os de base pequena). Índice = 60% qualidade + 40% cobertura (a
    régua do ranking do App); grupo sem uma das duas fica sem índice. **Base pequena** = menos de 3 usinas
    (`BASE_PEQUENA`). Clicar no nome leva aos Registros filtrados (`regiao=`, `equipe=`, `cliente=`, `regiao_campo=`,
    `gestor=`; a
    equipe virou filtro da tela, com o ×). Barras em CSS feitas no servidor, sem biblioteca. As tabelas ficam lado a
    lado só quando cada uma cabe inteira (620 px); a 1280 px com o menu, duas colunas rolavam de lado. Com todos os
    grupos de base pequena, o destaque diz isso em vez de "sem índice". Medido em 08/10 (30 dias):
    5 regiões (índice 99 a 79; Sul com a menor cobertura, 58%), 53 equipes (47 com índice, 34 de base pequena), 12
    clientes, 7 supervisores (índice 99 a 71); as somas batem com o total (128 usinas, 527 rondas). Com a estrutura
    (conferência de 08/10, cadastro do ensaio da publicação): 9 grupos de região de campo (as 8 e "Sem região de
    campo"; índice 99 a 82) e 5 gestores de contrato (98 a 87).
  - **Ronda sem OS, o motivo em português** (`visao.motivo_sem_os`; Levi, 05/10: "não entendi essa observação, minha
    conta fracttal já está conectada"): o App cria a OS de ronda com a conta Fracttal do TÉCNICO; "Conecte sua conta
    Fracttal" é a mensagem do App para o técnico. Medido em 05/10: 114 de 771 rondas (90 dias) sem OS por isso (os
    cinco técnicos com mais somavam 74). O App tenta 5 vezes, uma por
    minuto, e desiste (`RONDA_OS_FILA_MAX`, `_MAX_H` 24 h): a ronda antiga não ganha OS quando o técnico conecta depois.
  - **Filtro por cliente** (Levi, 05/10: "a cobertura das rondas das UFVs do cliente. Essas usinas tem que bater com
    as mesmas do registro mestre!"): o cliente vem de `usinas.cliente_id` → `clientes.nome` do `cadastro_nexus`
    (`_Base.nome_cliente`), nunca do nome da usina no livro. Filtra as rondas E a base da cobertura; com cliente
    escolhido aparece a faixa "cobertura das rondas: N%, X de Y usinas mobilizadas do cliente no cadastro". Medido em
    05/10: as 128 mobilizadas têm cliente; Thopen 61 de 80 (76%) em 30 dias.
  - **Quem ronda por cluster** (`visao._por_cluster`; Levi, 05/10: "seria melhor por cluster, aí nesse cluster clicando
    apareceria as mesmas informações porém por pessoa"): o cluster é o do cadastro pela usina, numa grafia só
    (`nome_cluster`: "SP OESTE" e "SP Oeste" eram dois no banco). **Pendentes de ronda** = usinas mobilizadas do cluster
    que pedem ronda pela regra da Central (`_pendente`: 7 dias ou mais, nunca, ou a longa pendente). Abre em **blocos**
    (08/10: "traga também uma visão em blocos para que fique mais visual para os supervisores!"; `ver=tabela` volta à
    tabela): um cartão por cluster com a cobertura (usinas com ronda no período ÷ usinas, a mesma conta do indicador;
    barra com ronda × sem), os pendentes, as rondas, a qualidade e os técnicos que rondaram; a borda pela cobertura
    (80% ok, 50% alerta). Clicar abre as pessoas (`cluster=`), com as mesmas colunas; o pendente da pessoa é o da
    equipe em que ela mais ronda, e **clicar na linha do técnico abre quais são** (08/10: "clicando na linha tem que
    aparecer quais são essas 5"; `_item_pendente`): a usina (link ao histórico), há quanto tempo e o status e a
    observação escritos como a Central escreve. A faixa do cluster tem "Ver as N usinas pendentes" (só as do cluster).
    Conferido em 08/10 (7, 14 e 30 dias): 40 clusters; soma = 128 usinas, 82 pendentes (igual à regra direta) e as
    rondas do total; cada técnico com a lista do tamanho do número dele (56 técnicos em 30 dias, 44 com pendentes).
  - **Histórico da usina** (`/rondas/usina/<usina_id>`, `visao.historico_usina`; Levi, 05/10: "quando clicarmos no
    nome da usina já aparece o histórico de rondas com data e sujidade e vegetação"): o nome da usina é link nas abas
    Registros, Sujidade e Sem ronda e nos pendentes do Quem ronda. Todas as rondas do livro (90 dias), a mais recente
    primeiro, com sujidade (número só com a cor da fonte, como na aba),
    vegetação, vala e sensores da OS (em verificação e aprovadas dos 90 dias; OS ainda não lida aparece "não lida",
    ronda sem OS fica "—"), e a evolução em gráfico quando há duas leituras ou mais. Passar o mouse (ou o foco do teclado) num ponto
    mostra a OS, quem fez, o dia com a hora (início e fim) e os dois níveis (Levi, 06/10). A data do eixo vai em meia
    fonte e, com muitas rondas, uma a cada tantos pontos (a última sempre; Crateús, 25 rondas, encavalava); o texto entra por
    `textContent`, nunca como HTML, porque vem do livro do App.
    **Fotos** (`nexus/campo/ronda_fotos.py`; Levi, 06/10: "ao clicar no botão aparecer os anexos, separando vegetação e
    sujidade, aparece pequeno e se eu clicar expande!"; 08/10: "quero que tenha como clicar em um botão de fotos que
    nem no histórico da usina", então também na aba Registros, pelo MESMO componente `_ronda_fotos_caixa.html`, que as
    duas páginas incluem; ronda sem OS ou avulsa fica sem botão, com o porquê no `title`; medido em 08/10: 288 botões
    nas 300 linhas de 30 dias): o botão Fotos de cada ronda com OS carrega os anexos da OS no
    Fracttal (1 pedido por OS, guardado 20 min; o link assinado fica no servidor e o Nexus entrega a imagem). Separação
    pela descrição que o App escreve ("Sujidade dos módulos — 4", "Altura da vegetação — 5"); as demais vêm recolhidas
    e, abertas, por tipo (sensores, vala, infraestrutura, pragas/dejeto/trincado, zonas, capa), com o nome curto do
    item na miniatura ("deixe recolhido, quando expandir quero que mostre por tipo, o que é piranômetro e etc"). A 1ª
    foto o App descreve como a capa da ronda. Miniatura de 240 px pelo Pillow (medido em 06/10: 7 a 14 kB contra 182 a
    690 kB a foto inteira), feitas em paralelo assim que a grade é pedida; a mesma foto pedida duas vezes baixa uma vez
    (a chave de "em andamento" leva a cache: com a mesma chave a miniatura esperava por si mesma 60 s). Clicar amplia,
    com setas dentro do grupo e Esc. OS sem anexo existe (15055: as fotos não subiram); ronda sem OS: fotos só no App.
  - **As rondas feitas saíram da Central de atenção** (Levi, 05/10: "na parte de atenção quero só o que for pendente"):
    na aba Registros, o filtro de pendência (Sem OS no Fracttal, Evidência incompleta) e a coluna Pendências.
  - **Sujidade e vegetação** (Levi, 05/10: "é importante!"; `nexus/campo/ronda_checklist.py`): o livro de rondas não
    traz o checklist, mas o App escreve cada resposta no texto da OS de ronda no Fracttal ("Sujidade dos módulos: 2;
    Altura da vegetação: 3; Sujidade da vala de drenagem: Parcial; Piranômetro IPOA ...: Limpo"). As listagens do REST
    trazem esse texto em lote: as em verificação já estão na fila da Aprovação; as aprovadas (que não mudam mais)
    ficam em `<pasta de dados>/campo/rondas_aprovadas.json` (fora do git; no PC, `C:\GridcoAuto\nexus`). A primeira
    leitura vai até 90 dias (e, se o Fracttal recusar no meio, continua da página em que parou); depois, a cada 10 min
    no máximo, só o que foi aprovado depois da última leitura completa menos 3 dias (1 a 2 páginas), com 0,5 s entre
    páginas. **Por quê (06/10):** antes era tudo ou nada, ~30 páginas a cada reinício e a cada 30 min; no reinício das
    10:09 o 429 descartou a leitura inteira e Matões 200 mostrou "—" em OS aprovadas que tinham a resposta (15055:
    sujidade 2, vegetação 3, vala obstruída). A tela agora diz quando a leitura falhou ou não terminou
    (`_aviso_checklist.html`). Nada disso vai para o banco. **Ronda sem OS** (não há texto da OS para ler): as de
    11/08 a 06/10 vêm da carga única `nexus_rondas_checklist` (06/10, ver `nexus/dados/CLAUDE.md`), ligadas à ronda
    por `usina_id` + `inicio` (`visao._checklist_sem_os`, `resposta_da_ronda`). Por usina: a
    última leitura no período e a anterior (a seta); nível 1 a 5, acima de 3 pede ação (o `alerta_acima` do App);
    distribuição por nível; vala, sombreamento e sensores sujos. O caminho limpo é o App mandar essas colunas no livro
    de rondas (mudança no App).
    **A tabela (08/10):** colunas Data, Técnico, Usina, Equipe, Região (do Brasil, pela UF), Tipo (curta/longa e o selo
    Avulsa: era uma marca solta sob a data), Sujidade, Vegetação, Sombreamento, Vala, Sensores, OS e **Status**, nessa
    ordem (a pedida pelo Levi; o Status entrou no fim). O número de sujidade e vegetação vai **só com a cor da fonte**
    (`cn-nivel-txt`; 1-2 verde, 3 azul, 4 âmbar, 5 vermelho; vale também no histórico da usina). **Ordem = o mais
    crítico primeiro** ("não fique ordenado pela data e sim pelo que está mais crítico, um balanço entre vegetação,
    sujidade, vala e sensores"; `visao.criticidade`): nível 5 vale 5, nível 4 vale 3, nível 3 vale 1 (sujidade e
    vegetação); vala obstruída 4 (o "suja" do formulário de 07/10 da avulsa também vale 4 no `visao.PESO_VALA`; desde
    08/10 a avulsa usa o "Obstruída" do App), parcial 2; cada sensor sujo 2; o sombreamento não
    pesa (1 resposta em 804 rondas lidas, texto livre). Assim vegetação 5 + vala obstruída (9) vem antes de sujidade 5
    sozinha (5), e tudo no 4 (6) antes de uma vala só obstruída (4). Empate: o maior nível, depois a mais recente. O
    **Status** diz o porquê na cor da gravidade: Vegetação/Sujidade muito alta e Vala obstruída (vermelho), Vegetação/
    Sujidade alta, Vala parcial e Sensor sujo (IPOA...) (âmbar), Sombreamento (azul); sem nada, "Sem alerta". **Os
    botões de filtro saíram** ("se a pessoa quiser ordenar ela clica na coluna que ordena e já era!"): `sv=` não filtra
    mais. Medido em 08/10 (30 dias): 98 de 128 usinas com leitura; nota de 0 a 12 (2 usinas com 10, 1 com 12); Status:
    vala parcial 38, vala obstruída 12, sujidade alta 12, muito alta 7, vegetação alta 10, muito alta 5, sensor sujo 1;
    33 sem alerta. Conferido com a conta antiga sobre a mesma leitura (7, 14 e 30 dias): as mesmas linhas e o mesmo
    resumo; muda só a ordem.
  - **Validação por foto** (Levi, 08/10/2026; `visao.validacoes_por_foto`): a linha do livro da avulsa com
    `origem = "validacao_foto"` (a criticidade revisada por um colega a partir das fotos das rondas do App, importada
    de planilha: ver "Importação da validação por foto" abaixo). **Não é ronda:** fica fora do `fato_ronda`, de
    Registros, cobertura, Quem ronda, Painel, duração e dos indicadores. Entra só na Sujidade e vegetação e no Histórico
    da usina, como a leitura daquela usina naquele dia, em nome de quem validou, com o selo **Validada por foto**
    (`title`: níveis revisados pela foto, não é ronda nova; e qual ronda ela revisou). Havendo ronda no mesmo dia na
    mesma usina, vale o validado para a usina (é a leitura da aba e o ponto da evolução) e a linha da ronda no histórico
    leva a marca **revisada** (`title` com quem validou e os níveis validados). Duas validações da mesma usina no mesmo
    dia: vale a última lançada. A avulsa sem `origem` (ou com `origem` vazia) continua ronda avulsa, e conta.
- **Ronda avulsa** (Levi, 07/10/2026: "a pessoa loga pelo fractal dela ... não terá imagens, só informações da
  tabela, salva nome da pessoa, data e hora e diz que foi avulso, quando passa o mouse em cima de avulso explica o que
  é"; `nexus/campo/ronda_avulsa.py`, botão "+ Ronda avulsa" na aba Registros). Quem entrou com o login do Fracttal
  lança usina mobilizada, data (até 30 dias atrás, nunca no futuro), início e fim (até 8 h), tipo, sujidade e
  vegetação 1 a 5, vala, sombreamento, os três sensores e um comentário livre opcional (até 1.000 caracteres). Com a
  senha geral do Nexus não lança (não dá para saber quem fez). **Conta na cobertura** (decisão do Levi, 07/10) e
  entra na Sujidade e vegetação; não tem nota (sem foto nem GPS), então o veredito é "—", nunca o "Não está bom" de
  nota zero, e não é a pendência "sem OS no Fracttal". O selo **Avulsa** tem `title` com `EXPLICACAO` (mouse e foco
  do teclado) na tabela, no histórico da usina e na sujidade. A mesma pessoa não lança duas vezes a mesma usina no
  mesmo início. Errou: anula (só quem lançou, pelo código do e-mail) e lança de novo; a anulação é OUTRA linha, que só
  aponta a anulada (`anula_id`, quem anulou e quando; sem dia nem usina: com eles, um COUNT por usina e dia no livro
  aberto contava 2 para uma ronda anulada), e o banco não apaga. No banco (`nexus_rondas_avulsas · fato_ronda_avulsa`,
  ver `nexus/dados/CLAUDE.md`) só IDs: nome e e-mail cifrados em `quem_cifrado`, comentário em `comentario_cifrado`
  (Cofre com `NEXUS_CHAVE_CADASTRO`), pessoa como `pessoa_id` + `pessoa_hmac`. **Precisa das duas chaves no `.env`:**
  sem `NEXUS_PESSOA_HMAC` ou sem `NEXUS_CHAVE_CADASTRO` o lançamento é recusado com o motivo na tela (07/10: o servidor
  ainda não tem a `NEXUS_PESSOA_HMAC`). O livro que ainda não existe lê vazio (conferido no banco real em 07/10 e 08/10).
  - **Domínio do App** (08/10, decisão 3 do Levi, antes da 1ª gravação do livro; spec Kimball, seção 9): a vala tem as
    opções do App (`dominios.VALA_OPCOES`: Limpa, Parcial, Obstruída, Não se aplica), com "escolha" de saída (antes o
    "Limpa" ia marcado sem ninguém escolher); o "Suja" de 07/10 não existia no App e não somava com "Obstruída". Cada
    sensor (IPOA, albedômetro, GHI) tem três estados, com **"Não verifiquei" marcado de saída**, que vai VAZIO ao banco;
    "Limpo" e "Sujo" vão como a palavra (`dominios.SENSOR_ROTULO`). O formulário de 07/10 gravava 0 para o sensor não
    marcado, que contava como limpo sem ninguém ter olhado. A palavra também separa as duas formas no livro: um Nexus
    que subiu antes desta mudança (o local da 5070, por exemplo) grava o 1/0 de 07/10 até ser reiniciado, e
    `dominios.sensor_avulsa` lê esse 0 como não verificado. O sombreamento continua sim/não com o "não"
    marcado de saída (a auditoria não o apontou).
  - **Importação da validação por foto** (Levi, 08/10: "Use esse arquivo em excel para subir as rondas avulsas dessas
    usinas, utilize a data de vegetação e sujidade, escolha a data mais recente entre as duas, suba no nome de ...";
    `ferramentas/importar_avulsas_planilha.py <planilha> --pessoa "<nome>" --comentario "<texto>" [--gravar]`, ensaio
    por padrão; a pessoa e o texto vão por argumento: o repositório é público). Cada linha da planilha vira UM
    lançamento pelo MESMO caminho da tela (`montar_linha` + `acrescentar`), com `origem = "validacao_foto"`, que não é
    ronda realizada (fora do `fato_ronda` e da cobertura; as telas a mostram como níveis validados pela foto). Usina pelo
    de-para "Fracttal · Classificação 1" com o texto EXATO (a que não casa sai na lista "fora", dizendo com qual usina
    casaria pelo nome normalizado: o conserto é no cadastro); data = a mais recente entre as datas das fotos de
    sujidade e de vegetação, nunca no futuro, sem o limite de 30 dias; "Sem foto" = vazio; vala, sombreamento,
    sensores e tipo vazios; início = a data às 00:00 de Brasília. A pessoa é achada no cadastro pelo nome ou nome
    padrão (decifrados na memória); se não for exatamente UMA ficha com e-mail, para. Idempotente (mesma usina, data,
    pessoa e origem já válida = pula) e, depois de gravar, relê e bate linha a linha (níveis, datas, origem, pessoa,
    cifras decifrando, nada em claro, as linhas que já estavam no livro continuam). **1º ensaio (08/10, a planilha
    de criticidade validada das rondas Thopen):** 63 linhas, 61 casam (as 2 de fora têm no de-para do Fracttal dois
    espaços que a planilha não tem: "Thopen - Belo Jardim  1 - PE" e "Thopen - Saturnino 1  - RJ"), datas de 20/08 a
    06/10 (3 com as duas datas diferentes), 60 com sujidade e 61 com vegetação; **não gravou**: a pessoa pedida não tem
    ficha no cadastro (0 fichas pelo nome e nenhuma com o sobrenome). Para gravar: a ficha entrar no cadastro, rodar de
    novo com `--gravar`.
- **Cache quente** (Levi, 06/10: "O carregamento das abas está sendo muito lento... O certo seria carregar e ficar
  carregado no cache!"; `visao._ler`, `manter_quente`): medido em 06/10, frias, Central 4,6 s, Rondas 3,0 s, Ranking
  3,1 s (13, 7 e 8 leituras do banco; o Ranking saiu em 08/10); quentes, < 0,05 s. Agora: ao subir, as contas principais são feitas (3,8 s,
  por trás); a cópia vencida (5 min) volta na hora e se refaz em segundo plano; a cada minuto, o que alguém usou nas
  últimas 2 h é refeito antes de vencer; o mesmo livro do banco é lido uma vez por ciclo (2 min). Medido: abas em
  0,01 a 0,13 s, também com as cópias vencidas. Só lê o banco do Nexus (nada de Fracttal), então fica **sempre ligado,
  em toda máquina** (09/10/2026, `nexus/campo/instalar`): o `NEXUS_CAMPO_AQUECER=0` desliga só as leituras do Fracttal
  ao subir (fila da Aprovação, rondas aprovadas, OS de falha e Quadro da equipe da Engenharia). Até 09/10 a chave
  desligava as duas coisas, e o PC, que sobe com ela em 0, ficava sem: a 1ª visita à Central depois de cada reinício
  levava 9,7 s e a hora da leitura era a do clique (Levi, 09/10: "quando clico em Central de atenção ... a hora fica
  praticamente a hora que cliquei").
  Medido no PC depois, na 1ª visita de cada aba, 45 s após subir: Central 0,09 s, Rondas 0,19 s, PT 0,07 s, Zeladoria
  0,01 s, com a hora da pré-carga. Prova: `tests/test_campo_instalar.py`.
- **Quem entra já vem filtrado** (Levi, 06/10: "Quando um supervisor logar, o filtro supervisor já fica para a pessoa
  automaticamente, mas ela pode mudar o filtro se quiser"): no login pelo Fracttal (`nexus/auth/__init__.py`),
  `visao.papel_no_campo` acha a pessoa no cadastro (`pessoa_do_login`: pelo e-mail da ficha; sem ele, pelo nome
  completo, curto ou o do e-mail, só quando é de UMA pessoa) e guarda o PAPEL dela em `supervisor_padrao`
  ({pessoa_id, nome, papel, regioes ou gestor}; `papel_da_pessoa`, nesta ordem): **Coordenador de Campo** = todas as
  regiões (sem filtro); **Supervisor de Campo** = a região dele (a 1ª pela ordem, se cobrir mais de uma); **Gestor de
  contrato** = as usinas dele (o filtro de gestor). Central, PT, Rondas e Aprovação usam `_regiao_campo()` e
  `_gestor()`: sem filtro na URL, o do papel; "Todas"/"Todos" vai como `*`. Sessão de antes (o nome do supervisor em
  texto) não vale como papel. Medido em 06/10: nenhum dos supervisores de então tinha e-mail no cadastro; o e-mail do
  Fracttal na ficha é o caminho seguro (o nome só vale se for de UMA pessoa).
- **PT:** fila "aguardando" da mais antiga para a mais nova; espera = da criação à decisão; parada = mais de 2 h.
- **"Esperando o De acordo" é a MESMA tela da Central > Permissões de trabalho** (Levi, 05/10): as duas incluem
  `templates/campo/_pt_esperando.html` (cartões compactos por equipe, por região de campo ou por gestor de contrato;
  tabela com a OS em verde,
  Equipamento, Espera no fim e a linha que abre o detalhe). Mudou uma, mudou a outra (o teste compara os cartões das
  duas).
- **Tela de PT** (Levi, 05/10): abas "Esperando o De acordo" (cartões por equipe, por região de campo, por gestor de
  contrato ou tabela) e "Histórico" (decididas, período 7/30/90 dias, por situação; só tabela). Filtros de região de
  campo e de gestor; o cartão leva à tabela da equipe, da região ou do gestor. Na tabela: só o número da OS, em verde Grid, no lugar do número da PT (abre a aprovação); Equipamento no
  lugar do Estado; Espera na última coluna; clicar na linha abre o detalhe (PT, equipamento, equipe, região de campo
  com o Supervisor de Campo, gestor de contrato,
  atividades críticas com sim/não/NA, respostas NÃO, 1º aviso, decisão e motivo). O cartão inteiro leva à tabela
  da equipe, com a faixa de quem ela é (região de campo e Supervisor de Campo, técnicos, PT esperando e paradas).
- **PDF e assinatura do técnico pelo Fracttal, sem App e sem Azure** (`nexus/campo/pt_fracttal.py`, 05/10):
  - **PDF** (Histórico e aprovação): no De acordo o App gera o PDF com as duas assinaturas e anexa na tarefa
    ("Permissão de Trabalho <número>"). O REST de anexos (credencial do OS Creator) traz o link já assinado (24 h); o
    Nexus baixa e entrega (`/t/campo/pt/<n>/pdf`), o link não vai ao navegador. Medido: PT-15457-0510-1751, 26,9 KB em
    1,8 s. PT não autorizada não tem PDF.
  - **Assinatura do técnico ao lado de "A PT"**: a da APR (`filled_by_signature`), pelo RPC
    `tasks.work_order_offline_ptw_download` com o login do Fracttal (OS Creator) de quem olha; caminho de arquivo se
    assina com `companies.s3_object_get`. A tarefa da PT sai do REST da OS (a única, ou a de mesma descrição; duas
    candidatas = não chuta). Guardada 1 h em memória, nunca no banco. **Sem prova com login real ainda** (os testes
    usam o RPC falso): o Levi entra com o login dele e abre uma PT.
- **Central de atenção, só o que está pendente** (as rondas feitas foram para a tela Rondas em 05/10; o texto abaixo descreve a origem) (Levi, 05/10: "separar Rondas feitas (histórico de rondas) e rondas
  pendentes, dando bastante atenção nas pendentes"; "separe o que é ronda e o que é Permissão de Trabalho"):
  - **Rondas pendentes** (abre nela, com números grandes que filtram): uma linha por usina mobilizada que pede ronda:
    nunca teve, sem ronda há 7 dias ou mais, ou ronda longa pendente pela última ronda (o App repete o aviso em toda
    ronda curta). Colunas: Há, Status, Usina, Equipe, Estado, Região, Observação. Medido em 05/10: 86 (21 nunca, 45 há 7 d ou
    mais, 20 longa pendente).
  - **Rondas feitas:** o histórico do período, com "Feito por" (só aqui aparece quem fez), Status (Sem OS no
    Fracttal, Evidência incompleta, Sem pendência), Observação, OS e nota. Medido: 232 em 14 dias (178, 39 e 15).
  - **Permissões de trabalho:** as PT esperando, Técnico e a OS em verde, que abre a aprovação. Medido: 22 (21 paradas).
  - **Três visões em cada aba** (Levi, 05/10: "tem que ter a visão por equipe (CARDS grandes agrupados) e a visão
    da tabela!"; 08/10: "além de por equipe e tabela, adicione mais um botão (por supervisor). Faça o mesmo na tela
    permissões de trabalho"): abre nos **cartões por equipe** (`visao.por_equipe`): usinas pendentes de ronda, % feitas
    (= usinas da equipe que não estão pendentes ÷ usinas da equipe, com a barra feitas × pendentes), o detalhe por
    status, as rondas do período e as PT esperando. O cartão leva à tabela da equipe (`?equipe=`). **Por região de
    campo** (era "por supervisor"; `modo=regioes`, e o endereço antigo `modo=supervisores` cai aqui;
    `visao.por_regiao`): os cartões de equipe já filtrados, somados pela região de campo da equipe; o % e as feitas
    refeitos sobre a soma; o Supervisor de Campo e o Coordenador (ou "vaga"), a base, as equipes (com o código) e os
    técnicos. **Alternância "Agrupar por"** para **Gestor de contrato (Supervisor PM)** (`modo=gestores`,
    `visao.por_gestor`): pelas USINAS do gestor (o gestor é da usina, não da equipe), com as equipes delas e os técnicos
    de cada equipe uma vez. Na aba PT, só os grupos com PT esperando. **"Sem região de campo"** (equipe de fora da
    estrutura) e **"Sem gestor de contrato"** são cartões próprios, tracejados, sempre por último; a linha sem região
    ou sem gestor (PT sem usina ligada) conta como deles (`_do_papel`), para o clique achar as mesmas linhas. O cartão
    leva à tabela da região ou do gestor (`?modo=tabela&regiao_campo=` / `&gestor=`). Filtro pela **região do Brasil**
    no lugar do estado. Medido em 05/10: 53 equipes; PR Norte 02 com 6 de 6 usinas pendentes. Conferido em 08/10
    (cadastro do ensaio da publicação): as somas dos cartões por equipe, por região e por gestor batem (128 usinas, 82
    pendentes; 37 PT).
  - Todas as colunas e cabeçalhos das tabelas do campo **centralizados** (Levi, 05/10).
  - **No cartão, do cadastro de pessoas** (`visao._Base._time`): o ícone de homem de capacete com o número de
    técnicos (colaborador de campo da equipe que não está Desligado: os 28 sem status estão todos em equipes sem
    nenhum Ativo) e, da estrutura de O&M de 10/2026, o código da equipe, a região de campo dela e o Supervisor de Campo
    (o "Nome padrão" da ficha, decifrado com `NEXUS_CHAVE_CADASTRO`; sem a chave, "Supervisor <id>"; ninguém = "vaga").
    O "supervisor" de antes (o `supervisor_id` dos técnicos, que na prática é o gestor de contrato) saiu das telas. O
    Levi pediu emoji; é ícone desenhado, pela regra sem emoji na interface. **Filtros de região de campo e de gestor**
    ao lado da região do Brasil. Embaixo da barra, número em cima e o que ele é embaixo ("feitas", "pendentes",
    "total"), para um leigo ler. Medido em 05/10: SP Oeste 03, PI Leste 01, MS Leste 01 sem técnico no cadastro.
  - Os filtros (status) são só a palavra colorida, sem fundo (`.cn-st`). "Detalhe" virou "Observação"; "O quê" virou
    "Status"; a coluna "Quem" saiu. **Nota baixa de fechamento não entra:** é a fila da Aprovação, e o fechamento
    aprovado direto no Fracttal nunca tem decisão no painel, o que dava ponto falso.
- Cópia de 5 min por tela; banco fora do ar = a tela avisa "Não consegui ler o banco do Nexus" e não some. Nos testes,
  sem `app.extensions["nexus_dados_sessao"]`, nunca vai à rede.

## Estrutura de O&M de 10/2026: região de campo e gestor de contrato (08/10/2026)

Levi, 08/10, sobre a "Nova Estrutura O&M Equipe": "pode adaptar, deixa as vagas preparadas". O antigo "Supervisor de
O&M" virou duas figuras: o **Supervisor de Campo** (1 por região de campo; lidera as equipes da região e aprova e fecha
as OS) e o **Supervisor PM** = o Gestor de contrato do BD_Operações (cliente, contrato, SLA), por usina. As pessoas que
eram "supervisor" (o `supervisor_id` dos técnicos) são, na prática, os gestores de contrato. Cadastro:
`nexus/cadastro/CLAUDE.md`.
- **De onde vem** (`visao._Base`): `cadastro_nexus` · `regioes_campo` (nome, base, `supervisor_campo_id`,
  `coordenador_campo_id`, `ordem`), `equipes.regiao_campo_id` e `equipes.codigo`, e `usinas.gestor_contrato_id`. A
  região da usina é a da EQUIPE dela; o gestor é da USINA. Nome de pessoa só pela ficha (`b.nomes`); ninguém = "vaga"
  (`VAGA`), desenhado no azul tracejado (`.cn-vaga`), nunca como erro.
- **Antes da publicação** (o banco sem a aba `regioes_campo`; ela entra quando o Levi publicar o cadastro): a tela não
  quebra, diz "Estrutura de campo ainda não publicada" (`_aviso_estrutura.html`), tudo cai em "Sem região de campo" e
  **só um administrador aprova OS** (o filtro e os cartões de gestor já valem: o gestor está no banco desde 07/10).
  **Ordem:** publicar o cadastro antes do (ou junto com o) push deste código; senão, até publicar, só admin aprova.
- **Filtros** (`_filtros_papeis.html`, Central, PT, Rondas e Aprovação): "Região de campo" (as regiões na ordem da
  estrutura, com o supervisor: "Nordeste 02 · vaga") e "Gestor de contrato (Supervisor PM)"; parâmetros
  `regiao_campo=` e `gestor=` (`*` = todas). O de região do Brasil (`regiao=`) continua, com o rótulo "Região do
  Brasil".
- **Cartões** (`_cartoes_papeis.html`): por região de campo (Supervisor de Campo, Coordenador, base, equipes com o
  código) e, pela alternância, por gestor de contrato. Somas conferidas iguais às dos cartões por equipe.
- **Quem aprova** (`_Base._aprovador`, a mesma para a tela e o portão): Supervisor de Campo da região; vaga aberta =
  Coordenador de Campo da região; sem os dois, ou usina sem região, ou estrutura não publicada = só administrador.
  Administrador aprova sempre. O texto do botão apagado e o do 403 dizem quem aprova aquela OS.
- **Prova:** `test_campo_central_supervisor.py`, `test_campo_aprovacao_supervisor.py`, `test_campo_visao.py` (o
  papel no login) e `test_campo_rondas_pedido_0810.py` (Painel e Sem ronda); mutações (coordenador aprovando com
  supervisor no cargo, gestor aprovando, vaga que não passa ao coordenador, supervisor que não entra filtrado) acusadas.
- **Falta:** a ficha do Supervisor de Campo e do Coordenador com o e-mail do Fracttal (é como o login acha a pessoa); o
  App de Campo ainda escreve a "Região" dele (a equipe), sem a região de campo.

## Aprovação de PT no Nexus (05/10/2026)

A OS da PT (verde) abre `/t/campo/pt/<número>`: a PT inteira (tarefa, ativo, técnico, atividades da APR com sim/não/NA,
respostas NÃO, falta, forçada) e a decisão.
- **Quem assina: o login do Fracttal do OS Creator** (Levi: "utilize o login do fractal do OS Creator Web que já dá
  certo!"). O OS Creator roda dentro do Nexus com sessão própria (cookie `os_sessao`, só em /os); por isso as rotas de
  assinatura moram em `/os/_nexus/...` (`assinatura.py`): `quem` (o e-mail de quem entrou), `pt/<n>/decidir` (POST) e
  `pt/<n>/voltar` (o OS Creator só devolve para /os depois do login). Token do Fracttal vencido (`exp`) não assina;
  pedido de outra origem leva 403.
- **Debaixo do `/nexus`** (porta única, 10/10/2026; no servidor o Nexus mora em `/nexus`, e endereço cru cai na
  plataforma de Performance): o `volta` do formulário de decidir é o `request.full_path` da tela, SEM o prefixo;
  `assinatura._volta` confere sem ele (`sem_raiz`) e devolve com ele (`na_raiz`). O `next` do login do OS Creator
  (`_login`) vai sem o prefixo (é o caminho que o clone entende) e o endereço do login, com ele. A aprovação de OS chama
  o clone com `request.url_root` (o cookie que o clone renovar fica no `/nexus/os`). Todo redirecionamento à lista
  (`TELA_PT`) passa pelo `na_raiz`. Prova: `tests/test_prefixo_sair_fracttal.py` e `tests/test_prefixo.py`.
- **Fica salvo:** `nexus_pt_decisoes · decisoes` (`nexus/campo/decisao_pt.py`; registrado no `catalogo.py` como
  `decisao_pt`). Grão: 1 linha = 1 decisão. Pessoa só como HMAC do e-mail (o mesmo código do App); motivo mascarado. O
  primeiro que decide vale: PT que já tem decisão do Nexus, ou que o livro do App já mostra decidida, recusa.
- **Quem pode decidir** (Levi, 09/10/2026): o Supervisor de Campo da região da usina (com a vaga aberta, o
  Coordenador), o gestor de contrato da usina, quem tem o vínculo COS no cadastro e um administrador do Nexus
  (`decisao_pt.aprovadores` / `pode_decidir`, conferido no `decidir`; a recusa diz quem pode). A pessoa é a do login
  do Fracttal, achada no cadastro pelo e-mail ou pelo nome de UMA pessoa.
- **Falta o App aplicar** (próxima versão do App, decisão de publicar é do Levi): ler `nexus_pt_decisoes` a cada
  minuto; para cada decisão nova, conferir pelo HMAC se quem assinou pode assinar aquela PT (`_pt_pode_assinar`, que
  precisa aceitar o mesmo conjunto: supervisor de campo, gestor de contrato, COS e administrador), se a
  PT ainda está aguardando e se a decisão é recente (sugestão: 30 min; decisão velha não libera ninguém), aplicar como
  o `gestao/pt/decidir` (pausa no Fracttal, anexo) e devolver o resultado no `pt_app_campo`. E mandar a PT ao banco na
  hora em que nasce, não só no timer de hora em hora (hoje a PT chega ao Nexus com até 1 h de atraso). Até isso, a
  tela diz: "O App ainda não lê esta decisão".

## As contas copiadas do App (`nexus/campo/regras_app.py`)

Aprovação e Triagem usam a lógica do App copiada, não refeita, para o número bater com o painel dele.
- `ferramentas/extrair_regras_campo.py` copia do `function_app.py` do App o fecho das funções das rotas
  `gestao/supervisao/fila` e `gestao/prioridades` e as duas réguas da nota. **Atenção e PT saíram da cópia em 05/10**
  (717 linhas a menos): agora são contas nossas. **A `gestao/os` (`_gestao_os`) saiu das raízes em 09/10**, um dia
  depois da tela Ordens de serviço: levou junto só os dois tetos dela; o `test_campo_livros_app.py` prova o livro de
  fechamentos pela Triagem. A cópia leva só a lógica (`ast.unparse`, sem comentários: o repositório é público e os
  comentários do App citam colegas pelo nome).
- `tests/test_campo_regras_app.py` compara cada função com o App pela árvore do código. Falhou = o App mudou: rode o
  extrator e confira a tela. Em 05/10 o v230 mudou `_qualidade_v2` (GPS do início vale como prova); recopiado, código
  `68d4d468251f7d6a`.
- **06/10, App v235 (código `e41fbad895cc8ff4`):** o teste acusou 15 nomes novos no fecho (`_varredura_carregar`,
  `_aplicar_varredura`, `_DONOS`, `_pessoal_fx`, `VARREDURA_CONTAINER`...). Todos vinham de UMA linha nova do
  `_fila_bruta`: antes de ler o Fracttal, ele pega a fila que o relógio do App guarda a cada 5 min no blob do Azure
  para todas as cópias dele. Copiar arrastava o cliente do blob (que abre a conexão do App) e a tabela `fxpessoal`.
  Decisão: `_varredura_carregar` entrou em `FORA` e o Nexus responde `False`, que é o que o App faz numa cópia sem
  armazenamento ("cada cópia lê sozinha, como antes"); o Nexus já relê a própria fila em segundo plano. A assinatura
  dela no App fica em `ASSINATURAS_TROCADAS`. O v235 também mudou:
  - **o relógio da fila:** o `_fila_bruta` mede a idade por `_FILA_CACHE["t"]` (segundos desde 1970), não mais pelo
    `ts` em datetime. O `aprovacao.py` passou a gravar e ler `t` (e `ts` igual, como o App). Sem isso, cada visita da
    Aprovação achava a fila velha e relia as 55 páginas do Fracttal na hora da tela (7 testes acusaram).
  - **página recusada tenta de novo** (`_fx_wo_paralelo`), em vez de jogar a fila inteira fora por uma página. Desde o
    v236: 2 rodadas, UMA espera por rodada (a maior que as recusas pediram, de 5 a 30 s) e depois todas as páginas
    recusadas de novo (no v235 eram 5 s por página, até 60 s somados). No Nexus isso só roda na releitura em segundo
    plano, por cima das esperas do `fracttal.py` (5 s e 10 s); o `Recusado` do Nexus não diz a espera, então o App
    espera 5 s por rodada.
  - Conferido com o banco real, cópia antiga × nova sobre a mesma leitura: Triagem (7, 30 e 90 dias), Ordens com a
    nota de cada OS (2.564 OS em 90 dias, nota média 79) e o veredito das 783 rondas da tela Rondas iguais, valor a
    valor. A fila da Aprovação (balde `_triagem`) não foi lida de verdade: pediria as 55 páginas no horário de campo;
    a função é a mesma árvore de código (o teste confere).
- **09/10, App v256 (código `92772066214dff23`, o mesmo que o `/api/health` do App mostrava às 17:40; o que mudou no
  fecho veio até a v255, a v256 não mexeu nele):** o teste acusou três nomes novos no fecho, `_VARR`, `FxLimite` e `VARREDURA_ESPERA_S`, todos puxados pelo `_fx_wo_paralelo` (v236 e v243), que
  o Nexus chama direto (`aprovacao._reler`). Atrás dessa 1ª asserção havia mais: `SUP_CAP_BACKLOG`, `_qualidade_v2`,
  `_rondas_os_pares` e a `_varredura_carregar` do App (a trocada). Decisão: **as três entram na cópia.** São um
  dicionário, uma subclasse do `ApiError` e uma constante lida do ambiente; nada de Azure (o `_VARR["cli"]` só é
  preenchido pelo `_blob_varredura`, que fica fora do fecho). Só agem no modo `paciente` do relógio do App, que o Nexus
  não usa, e o `fx` do Nexus levanta `fracttal.Recusado`, nunca `FxLimite`. Trocar o `_fx_wo_paralelo` por um nosso
  seria reinterpretar a regra.
  - **O teto da fila:** `SUP_CAP_BACKLOG` foi de 6.000 para 20.000 (v243). O `/api/health` do App dizia, em 09/10 às
    17:22, 6.177 tarefas em verificação; a cópia do v235 lia 6.000. O corte leva o FIM da lista, e com
    `sort=final_date` o Fracttal a devolve da mais recente para a mais antiga (medido na fila real às 18:06: a 1ª linha
    de hoje, a 6.000ª de 02/06; o comentário do App diz que o corte leva as mais recentes, a medida diz o contrário):
    **sumiam da Aprovação do Nexus as mais ANTIGAS**, 175 das 178 tarefas cortadas com 30 dias ou mais, e 18 OS
    paradas há 30 dias ou mais. Prova: `test_fila_de_mais_de_6_mil_tarefas_vem_inteira` (com a cópia velha, 6.000
    contra 6.177).
  - `_varredura_carregar` continua `False`: a do App passou a conferir o blob no máximo a cada 30 s e a trazer o teto
    do relógio, mas sem armazenamento o `_varredura_props` dela devolve None, e ela, `False`. Assinatura nova em
    `ASSINATURAS_TROCADAS`.
  - `_qualidade_v2` (`gps_ronda`, v241) e `_rondas_os_pares` (`respostas`): parâmetro novo, com padrão que mantém o
    resultado; o Nexus chama sem eles.
  - Conferido com o banco real só por GET, as mesmas respostas para as duas cópias: Triagem de 7, 30 e 90 dias igual
    valor a valor (913, 2.243 e 3.168 OS). Aprovação com a fila real lida UMA vez fora do horário de campo (09/10,
    18:02: 6.178 tarefas em 16,8 s, as mesmas 6.178 do `/api/health` do App) e o relógio da conta congelado: cópia
    velha × nova sobre a mesma fila iguais valor a valor nas cinco visões (cartões por região de campo e por gestor, o
    CSV, `idade=30-` e `ver=Sem cadastro`): 2.235 OS, 6.134 tarefas (as 44 sem `final_date` a conta do App não conta),
    661 prontas, 505 pedem olho, 1.069 fora do App, 784 paradas há 30 dias. A velha com o teto de 6.000 mostrava 2.217
    OS, 5.956 tarefas e 766 paradas. O script ficou fora do repositório (ver o fim deste arquivo).
- Trocados pelo Nexus no fim do arquivo gerado: `_tabela` e `tabela_qlog` (leem pela fonte do Nexus, `tabelas.py`),
  `tabela` (a dos tokens do Fracttal: só a partição `cadastro`; `tok` e `pt` recusadas), `fx` (Fracttal só GET,
  `fracttal.py`), `ident` (`pessoas.ident`) e `_varredura_carregar` (sempre `False`: sem blob do App).
- O código do App que vale é o da pasta `App_Campo\middleware` do SharePoint. Para saber se é o que está no ar: o
  `codigo` do `/api/health` do App (aberto, só números) tem de ser igual ao `CODIGO_APP` que o extrator grava na
  cópia. O mesmo `/api/health` diz, em `varredura.status`, quantas tarefas o Fracttal tem em verificação (`"2"`) e se
  o teto cortou.
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
- A Aprovação de OS lê a fila do Fracttal (55 páginas, ~5.500 tarefas, 0,5 s entre pedidos), mas **a tela nunca
  espera** (Levi, 05/10: "fica carregando infinito"; o log mostrava a leitura de 1 min ou mais e, à noite, 4 a 26
  páginas recusadas com 429, e cada visita recomeçava do zero). `aprovacao.py` relê em segundo plano, uma leitura por
  vez, quando a fila tem mais de 10 min; mostra a última fila boa e quando foi lida; depois de recusa, 5 min sem
  tentar. A cópia do App nunca relê na hora da tela (`FILA_TTL_S` vai para "sempre" a cada visita). Medido em 05/10:
  a visita responde em 0,01 s. Não abra essa tela em teste no horário de campo.
  - **O gargalo** (Levi, 05/10: "por que demora se o histórico do OS Creator carrega tão rápido?"): o REST do Fracttal
    entrega no máximo 100 tarefas por pedido (limit=1000 devolve 99) e a fila tem ~5.500, então são 55 páginas de
    ~1,1 s; até 05/10 saíam uma por vez com 0,5 s de folga (~90 s). O histórico do OS Creator pergunta outra coisa: o RPC
    com o login da pessoa, com período e "criado por" filtrados no servidor (poucas OS). Agora `fracttal.py` deixa 4
    pedidos ao mesmo tempo, no máximo 4 por segundo, e em segundo plano tenta de novo depois de um 429 (5 s, 10 s); a
    fila é lida ao subir o Nexus (`aprovacao.aquecer`, 20 s depois; `NEXUS_CAMPO_AQUECER=0` desliga). Medido: fila
    inteira em ~20 s.
  - **Tela para insight** (Levi, 05/10: "refaça essa parte de aprovação de OS para retirada de bons insights";
    `aprovacao.fila_toda` + `_agrupa_os`): a fila pela conta do App (a cópia devolve 200 linhas por chamada; as páginas
    são juntadas, ~4 s na 1ª, e a conta fica pronta logo depois de cada releitura). **A fila INTEIRA, sem período**
    (Levi, 08/10: "não deve ter filtro 'OS fechadas nos X dias' ... ficar preso nessa visão é foda"): a conta do App só
    conta por janela, e `aprovacao.FILA_INTEIRA` = 3650 dias (o teto do `_janela`), que pega toda OS em verificação; é
    essa a conta que a releitura deixa pronta (antes, a de 30 dias). Seis indicadores (esperando, prontas para aprovar,
    pedem olho, paradas há 30 dias, espera máxima, uso do App) e a barra da idade da fila: os números são da fila toda;
    o clique filtra os cartões e a tabela, sempre as MESMAS OS que o número conta ("paradas há 30 dias" = `idade=30-`,
    30 dias ou mais; até 08/10 levava à faixa 31 a 60 e, com a fila inteira, escondia as mais antigas). **Uma visão só,
    a dos cartões** (08/10: "a visão de por técnico e fila pode matar"), hoje **por região de campo** (estrutura de O&M
    de 10/2026; alternância "por gestor de contrato", `por=gestor`), o que mais tem parada há 30 dias primeiro: a
    equipe, a região e o gestor saem do cadastro pela usina do Fracttal; o cartão da região diz o Supervisor de Campo, o
    Coordenador e quem aprova ali; OS de usina sem de-para cai no cartão "Sem cadastro" e a de equipe fora da estrutura
    em "Sem região de campo", os dois por último. **O cartão abre a tabela das OS dele** (`?ver=`;
    08/10: "quando clica aparece a OS, dia, data da criação da OS, data fim, supervisor, prontas, pedem olho, fora do
    App, uso do App, nota média e devolvidas"), nessa ordem, uma linha por OS: Dia = dias esperando (a tarefa mais
    antiga); criação = `creation_date` da OS, que vem na MESMA linha do REST que a fila já lê (sem pedido novo;
    conferido em 08/10 nas 1.583 linhas em verificação guardadas pela Engenharia, todas com a data); datas em Brasília
    (o Fracttal fala UTC); Prontas, Pedem olho e Fora do App = tarefas da OS em cada grupo; Uso do App = % das tarefas
    pelo App; Nota média = das tarefas pelo App; Devolvidas = tarefas já devolvidas. A coluna "supervisor" é hoje o
    **Supervisor de campo** da região da usina (ou "vaga"). CSV com as mesmas colunas, mais região de campo, gestor de
    contrato e "Quem aprova" (do cartão aberto, ou de todos). Medido em 05/10 (90 dias): 1.827 OS e 4.736 tarefas esperando; 937 prontas; 1.780
    tarefas paradas há 30 dias ou mais; uso do App 41%; o supervisor com mais fila tinha 1.373 tarefas (uso do App 29%).
  - **Contada por OS, não por tarefa** (Levi, 05/10: "ele não consegue aprovar uma tarefa em si, e sim uma PT ou uma
    OS"; `_por_os`, `_agrupa_os`): a OS fica no pior grupo das tarefas dela (olho > fora do App > completa), a espera é
    a da tarefa mais antiga, a nota é a pior; indicadores, idade, cartões e técnicos em OS. A linha aberta mostra cada
    tarefa com o grupo e os motivos dela.
  - **A linha aberta diz o porquê do grupo e aprova** (Levi, 05/10): `aprovacao.motivos` = a regra `_triagem` do App
    mostrando TODOS os motivos que valem (nota abaixo de 80, ronda com pendência, já devolvida, tempo fora por causa
    do técnico, foto divergente; ou por que está completa). **Aprovar = o Concluir do OS Creator Web** ("usando o
    mesmo caminho que o OS Creator Web"), com o login do Fracttal de quem clica (status 3 + recalculate +
    reconferência da data de fim; IRREVERSÍVEL, pede confirmação). O id da OS vem da fila crua.
  - **Só quem aprova a OS ou um administrador aprova** (Levi, 08/10: "deve ser possível só o supervisor ou ADM
    conseguir aprovar a OS logando pelo Fracttal"; com a estrutura de O&M de 10/2026, "o supervisor" é o **Supervisor de
    Campo da região da usina da OS**; com a vaga aberta, o **Coordenador de Campo** da região; sem os dois, só um
    administrador; o Gestor de contrato NÃO aprova; `nexus/torres/campo/aprovar_os.py`). A regra é no SERVIDOR: o botão
    chama `POST /os/_nexus/aprovacao/<id>/aprovar` (mora em /os porque só lá chega o cookie `os_sessao` do login do
    Fracttal, como a assinatura da PT), que recusa: outra origem (403); sem login do Fracttal (401, a tela leva ao login
    e volta por `/os/_nexus/voltar?para=`, só /t/campo/); OS fora da fila guardada (404); e quem não é admin nem quem
    aprova a OS (403 com o texto de quem aprova aquela OS, inclusive "Vaga aberta de supervisor de campo na região X:
    aprova o coordenador de campo (Y)", também para quem montar o pedido à mão). Quem aprova = `aprovador` da região
    da usina do Fracttal de cada tarefa pelo cadastro (`visao._Base._aprovador`, a mesma conta da tela; OS em duas
    regiões é das duas); quem clicou = `visao.pessoa_do_login` do e-mail e nome do login do Fracttal, comparado por
    `pessoa_id` (vale quem entrou no Fracttal, não o filtro da sessão do Nexus). Admin = sessão de admin do Nexus
    (NEXUS_ADMINS ou a senha de admin, como o Cadastro) ou o e-mail do Fracttal em NEXUS_ADMINS. Passou: o portão
    repassa ao clone o MESMO POST de antes (`/os/api/os/<id>/concluir`, número da OS pela fila do servidor, cookie de
    quem clicou) e, aprovada, tira a OS da fila guardada na hora (a rota `/t/campo/aprovacao/<id>/tirar` saiu: deixava
    qualquer um esconder OS da fila). Na tela, quem não pode vê o botão apagado com o texto de quem aprova
    (`pode_na_tela`, pela sessão do Nexus: admin ou o `pessoa_id` do papel igual ao de quem aprova a OS). **Fica aberta** a rota do clone
    `/os/api/os/<id>/concluir` para o próprio OS Creator (o Concluir do card dele): o portão vale para a Aprovação do
    Nexus, não para o OS Creator. Testes com Fracttal e Concluir falsos (`test_campo_aprovacao_supervisor.py`).
    **Até 08/10 o script desta tela não rodava**: o `confirm()` do Aprovar tinha uma quebra de linha dentro da string
    (SyntaxError no navegador), então nem a linha abria nem o Aprovar funcionava; um teste roda `node --check` no script.
    **Cuidado com a cota:** cada reinício do Nexus relê a fila (55 páginas; as rondas aprovadas vêm do arquivo desde 06/10); em 05/10, com
    muitos reinícios seguidos, o Fracttal passou a recusar (429). Em desenvolvimento, `NEXUS_CAMPO_AQUECER=0`.
  - **Filtro de equipe, de região de campo e de gestor** pelo cadastro: as usinas da equipe (ou da região, ou do
    gestor) pelo nome no Fracttal
    (de-para "Fracttal · Classificação 1", `visao.usinas_do_fracttal`) viram o escopo de usinas da conta do App
    (`_area_ok`, `clusters.usinas`): grupos, números e lista saem já filtrados. Usina sem de-para do Fracttal não entra
    em filtro nenhum (a lista sai em `sem_de_para`).

## Peças em `nexus/campo/`

- `visao.py`: as contas nossas (acima), sobre os fatos (`_fato`, `_rondas_ligadas`, `pts`, `_ultima_os_por_usina`) e
  a validação por foto (`validacoes_por_foto`). `decisao_pt.py`: a decisão da PT no banco (acima).
- `livros_app.py`, `fonte_pg.py`, `tabelas.py`: os livros do App no formato que as regras copiadas consultam
  (`query_entities`, `get_entity`); erro de leitura fica anotado e vira aviso.
- `aprovacao.py`, `triagem.py`: as telas pelas regras copiadas (`aprovacao.os_na_fila` e `tirar_da_fila` servem ao
  portão do Aprovar, `nexus/torres/campo/aprovar_os.py`). `leitura.py`: cópia de 5 min e `limpar_cache()` (que também
  recarrega a cópia das regras).
- `pessoas.py`: `identidades.json` e a tabela dos tokens só na partição `cadastro`.
- `nota_fracttal.py`, `coletor.py`, `banco_campo.py`: o caminho do coletor aposentado.

Telas: `templates/campo/*.html` + `static/campo.css`; filtros pela URL.

Prova: `tests/test_torre_campo.py` (nenhuma tela com Azure, moldura ou "Abrir no App"), `test_campo_visao.py` (as
contas nossas, a Central em três visões e a aprovação da PT com o login do OS Creator, banco falso), `test_campo_ronda_avulsa.py` (lançar, cobertura, selo, recusas, anulação, catálogo; 08/10: vala do App, sensor em três estados, anulação sem dia nem usina, o caminho de gravação que a importação usa), `test_campo_importar_avulsas.py` (a importação da validação por foto com planilha sintética: de-para exato, data mais recente, "Sem foto", a pessoa que tem de ser uma ficha com e-mail, gravação, conferência linha a linha, idempotência, fora do fato de ronda), `test_campo_rondas_pedido_0810.py` (Rondas de 08/10: colunas e dica da duração, Fotos na tabela, nunca tiveram ronda, Sem ronda, criticidade, Quem ronda em blocos com as pendentes, Painel), `test_campo_sujidade.py`, `test_campo_regras_app.py`, `test_campo_aprovacao.py`, `test_campo_fila_rapida.py`,
`test_campo_aprovacao_supervisor.py` (08/10: fila inteira, cartões por região e por gestor, a tabela, o portão do
Aprovar: supervisor de campo, coordenador com a vaga aberta, só admin sem os dois ou sem a estrutura publicada, gestor
não aprova, sessão antiga, script válido),
`test_campo_central_supervisor.py` (08/10: Central e PT por região de campo e por gestor de contrato, "Sem região de
campo" e "Sem gestor de contrato", estrutura não publicada, filtros e CSV das Rondas, detalhe da PT e histórico),
`test_campo_telas_pg.py`, `test_campo_livros_app.py`, `test_campo_fonte_pg.py`, `test_campo_nota_fracttal.py`,
`test_campo_coletor.py` (`tests/pg_falso.py`), `test_campo_fatos_nas_telas.py` (08/10: o técnico pelo nome e pelo
código no mesmo livro, a coluna nova sem a chave, o fato do banco da mesma versão vale e o velho não, a carga que
falhou, a ronda repetida que não conta em dobro, o dia de Brasília, a pessoa pelo cadastro, a PT e a última OS pelo
fato, a validação por foto fora das rondas e no lugar da ronda do mesmo dia) e `tests/test_sem_nomes_no_repositorio.py`
(nenhum nome de técnico ou supervisor nos arquivos versionados: cite pelo papel).
**A prova antes × depois do passo 4** (as telas com o banco real por GET, as mesmas respostas para as duas versões) foi
feita com scripts fora do repositório (gravam o dado real com nome de pessoa): para repetir, rode as telas pelo
`test_client` logado com `app.extensions["nexus_dados_sessao"]` = uma sessão só de GET, `visao._agora` congelado e
`ronda_checklist.pedir_releitura`/`aprovacao._pedir_releitura` desligados (não ler o Fracttal), e compare o contexto dos
templates (`flask.template_rendered`) da versão antiga com a nova. **Para a recópia das regras do App** (09/10), três
armadilhas: as duas cópias rodam no mesmo processo por um `sys.meta_path` que entrega a fonte escolhida ao
`importlib.reload` do `leitura.limpar_cache`, sem trocar o arquivo do working tree (outras sessões trabalham nele); o
relógio da conta do App só congela trocando `datetime.datetime` no módulo `datetime`, porque as regras fazem
`from datetime import datetime` dentro da função (sem isso, com 6 mil tarefas, alguma vira de dia entre uma tela e a
outra); e com `TESTING` ligado o `credencial()` do Fracttal só olha a credencial de teste. O receptor do
`template_rendered` precisa de `weak=False` (o blinker guarda referência fraca e a lambda some).
