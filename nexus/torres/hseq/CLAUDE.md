# CLAUDE.md — Segurança · HSEQ

Torre do menu "Segurança · HSEQ". Telas vivas: **Extintores** (com o relatório em PDF), **EPI e EPC** e **APR e PT**
(09/10/2026). Riscos da semana, DSS e Incidentes ainda são placeholder (a view com a mesma rota vence a genérica). As contas moram em `nexus/hseq/`; a view e o template,
aqui.

## Extintores

Levi, 09/10/2026: "Gostaria de adicionar no Nexus algo que inseri no app: Extintores. Ficará no módulo de segurança.
Nele será possível ver a tabela dos extintores com uma visão do que está atrasado, perto de atrasar e sem atualização a
mais de 30 dias. Preciso da visão por supervisor."

**De onde vem.** A ronda de extintores do App de Campo (v247, 08/10/2026) substituiu o Microsoft Forms da TST. O
cadastro inicial é a planilha de controle da TST (773 extintores em 81 usinas; 7 usinas sem par no Fracttal ficaram
fora, 58 extintores) e fica **fora do Fracttal** (código próprio `<cb>-INFC1-PPCI-EXTnn`). O App publica no banco o
livro `extintores_app_campo`, de hora em hora com os outros livros dele (timer `nexus_workbooks_sync`, aos :25). Nada
de Azure. **Carga única em 09/10/2026, 22:54** (Levi: "traga para o banco do nexus agora"): o livro foi criado pelo
Nexus, do próprio cadastro do App (`ferramentas/carregar_extintores_cadastro.py <extintores_cadastro.json> --gravar`:
773 linhas, conferidas valor a valor depois de gravar, 0 diferença; o status da TST calculado no dia da carga). Até o
App publicar, a conferência de todos é a do Forms da TST; quando o App publicar (v257, sync-xlsx com replace), a
gravação dele substitui esta e traz as conferências feitas no App. Sem o livro, a tela diz que os extintores ainda não
chegaram.

**O contrato** (`nexus/hseq/extintores.py`, `COLUNAS`; coluna nova só no FIM). Aba `Extintores`, 1 linha = 1 extintor
com a última conferência: `Código`, `Usina` (nome do Fracttal), `Código da usina`, `Tipo de ativo`, `Ativo` (código do
Fracttal de onde ele fica), `Local`, `Posição`, `Classe`, `Peso (kg)`, `Validade da recarga` e `Validade do
hidrostático` (`MM/AAAA`, só o ano, `Sem data`, `Sem selo`), `Última conferência` (`AAAA-MM-DD`, dia de Brasília),
`Origem da conferência` (`App` ou `Forms da TST`), `Conferido por (HMAC)`, `Carga`, `Itens NÃO` (as chaves do App
separadas por `; `), `Fotos`, `Tem informação adicional` (sim/não: a observação do técnico **não** vai, a API tem
leitura aberta), `Status` e `Motivo` (os do App na hora da publicação) e `Origem do cadastro`. O histórico (1 linha =
1 extintor × mês) vai num livro próprio, `extintores_conferencias_app_campo` · `Conferências` (o App sobe uma aba por
livro: o sync-xlsx com replace troca o livro inteiro): registrado no catálogo, a tela ainda não usa. Os dois fatos
(`extintor`, `conferencia_extintor`) estão em `nexus/dados/catalogo.py`, estado origem. Sem uma das colunas da conta (`ESSENCIAIS`)
a tela diz qual falta e não mostra número.

**As contas** (nossas, no dia de Brasília; o status que o App manda não entra):
- **Atrasado**: a recarga (2º nível) ou o teste hidrostático (3º nível) venceu. A etiqueta vale até o último dia do mês;
  só o ano, até 31/12.
- **Perto de vencer**: não está atrasado e uma das duas vence em até 30 dias.
- **Sem validade**: a recarga sem data e nada vencido nem a vencer em 30 dias (nunca vira "em dia").
- **Em dia**: o resto. As quatro são exclusivas e somam o total.
- **Sem atualização**: última conferência há mais de 30 dias, ou nunca. Soma-se às outras: a faixa não fecha o total.
- **Status da TST** (crítico, atenção, ok, ok sem validade): a regra da aba Legenda da planilha da TST, a MESMA do App
  (`_ext_status`), com a carga e os 9 itens. Sem conferência nenhuma, não há status.

**A tela** (o desenho de 18/10/2026; o de antes, por usina e dia com cartões por região de campo e gestor, saiu). De
cima para baixo: a faixa de números (cada um filtra a tabela), a caixa dos não reconhecidos, os **filtros** e, logo abaixo
deles, a Tabela (o padrão) ou os cartões **Por responsável**.
- **Filtros** (Levi, 18/10: "Quero os filtros que estão antes de extintores não reconhecidos, acima da tabela"; "De
  filtros quero apenas cliente, usina, responsável UFV, equipe e o campo para digitar!"; `FILTROS_EXT` na torre):
  Cliente, Usina, Responsável UFV, Equipe e a busca, **em cascata** como a tela Técnicos por usina do PCM (cada lista
  traz o que existe com os outros filtros; a escolhida fica mesmo sem resultado), com o "Sem cliente / Sem responsável
  O&M / Sem equipe" no fim (`extintores.valor_do_filtro`). O Responsável UFV é o Responsável O&M da ficha da usina (o
  setor "Responsáveis UFV"). Saíram a região do Brasil, a região de campo e o gestor, e com eles o filtro que vinha do
  login (o Supervisor de Campo abria na região dele): **ninguém abre filtrado**. Valem na faixa, na caixa, na tabela,
  nos cartões e no "Baixar". O cliente vale também no EPI, que segue com os filtros do Campo.
- **Agrupar por Cliente** (o padrão; Levi, 18/10: "Quero agrupado por Cliente, abrindo o cliente terá as usinas desse
  cliente. É importante ter a coluna do responsável desse usina e o ou os técnicos da usina!"; `extintores.por_cliente`)
  e **por Extintor** (`ver=extintor`: o mais grave primeiro; no filtro "sem atualização", a conferência mais antiga
  primeiro). Colunas: Situação, Última conferência, Cliente e usina, Responsável, Técnicos, Quantidade de extintores
  (e quantos em cada situação), Recarga mais próxima (a vencida há mais tempo ou, sem vencida, a próxima), Status da
  TST (o mais grave, e quantos em cada) e PDF. A linha do cliente abre as usinas dele **na mesma tabela** (UMA linha por
  usina, `por_usina`: a última conferência é a mais recente dos extintores dela), e a usina abre os extintores numa
  tabela menor, cada um com a conferência dele. Ordem: o mais grave primeiro, depois a recarga mais próxima; "Sem
  cliente" por último. Com o filtro de cliente o cliente já abre; com o de usina, a usina também.
- **Os técnicos** vêm da tela Técnicos por usina do PCM (`extintores.tecnicos_por_usina`, livro `nexus_pcm_atribuicoes`:
  quem vê e ronda a usina no App, um embaixo do outro; o apoio agendado para depois de hoje ainda não conta). Lista que
  não foi lida: a coluna diz "não lido" e a tela avisa, e nunca "sem técnico". Medido em 18/10: 174 usinas com técnico,
  68 com dois.
- **Cabe a 1440 px** com as usinas e os extintores abertos (medido no banco real, 18/10: a caixa tem 1.168 px). O cliente
  abrindo uma tabela dentro da linha e a usina outra dentro dela pedia 1.212 px; com as listas "N atrasados · ..." numa
  parte só, 1.391. Por isso: cliente e usinas na mesma tabela, as listas quebram entre os itens (`ext-lista`) e o nome da
  usina, do cliente e do responsável quebram entre as palavras (cada técnico numa linha). A 375 px a tabela rola dentro
  da caixa e a página não passa da largura.
- **Por responsável** (`modo=responsaveis`; o filtro da faixa volta à tabela): um cartão por Responsável O&M da usina,
  como a Central de atenção, com os mesmos números dos cartões de antes; o clique leva à tabela filtrada por ele.
- A usina vai **sem a região ao lado** (Levi, 11/10: "Em usina pode tirar a região do lado, fica estranho!"). 300 linhas
  na visão por extintor. O CSS é o `campo.css` e o `hseq.css` (a tabela, os filtros e a caixa).
- **O relatório é só unitário, de cada cliente e de cada usina, em PDF e em Excel** (coluna Relatório). Levi, 18/10: "O
  relatório quero a opção de ser unitário (...), pode tirar esse RELATÓRIO EM PDF que tira em massa!" (o formulário do
  PDF de todos saiu da tela); a TST, 19/10: "tem como eu baixar um relatório dos extintores por cliente?" e "e excel
  tbm? pq às vezes o cliente pede". A linha do cliente leva `cliente`, a da usina leva `cliente` e `usina` (o nome da
  usina sozinho não basta, ver abaixo), sempre com os filtros da tela e o da faixa; o cliente ou a usina inteira, todos
  os dias, como anexo (`extintores-<cliente ou usina>-<hoje>.pdf|.xlsx`). O PDF e o Excel saem do MESMO recorte
  (`_do_relatorio` na torre). A rota do PDF ainda aceita `dia` (o link de antes) e, sem `usina` nem `cliente`, gera o de
  todos. **Excel** (`nexus/hseq/planilha.py`, rota `/t/hseq/extintores/relatorio.xlsx`): aba "Extintores", uma linha por
  extintor na ordem da tabela (cliente, usina, responsável, técnicos, o extintor, as validades como a etiqueta diz e o
  dia em que vencem como data, a situação, a conferência como data, quem conferiu pelo nome, a carga, os itens com NÃO,
  o status da TST e o motivo), com o título, quando foi gerado e os filtros em cima, o cabeçalho congelado e o filtro do
  Excel; aba "Não reconhecidos" quando o recorte os leva (a regra do PDF). Sem cor nem fórmula. Medido em 19/10 no banco
  real (só leitura): os 11 clientes com o Excel igual à tela, extintor por extintor contado; o da Thopen (550
  extintores) em 0,5 s, o PDF dela em 3,4 s.
- **A usina se separa pelo ID do cadastro, não pelo nome** (`extintores.chave_usina`): o cadastro tem duas "Linhares 1"
  (ES), uma da Axis e outra da Thopen, e pelo nome as duas se juntavam (achado em 19/10/2026 conferindo o Excel com a
  tela: 13 extintores da Thopen estavam na Axis). Vale nos grupos, na contagem de usinas da faixa e nos cartões; os
  links da usina levam também o cliente.

**Na tabela, as partes de cada célula ficam lado a lado** (Levi, 09/10/2026, sobre a 1ª versão, que punha o detalhe
sempre na linha de baixo: "se tem espaço para botar paralelo então deixe paralelo"). A parte é inteira e só desce de
linha quando a coluna não comporta. Medido em 09/10 com os 773: a 1920 px, 0 de 2.100 células quebram (41 px por
linha); a 1440 px, a tabela cabe na largura e as partes descem onde falta espaço. Para caber a 1920: o código do ativo
fica no title do Local, a validade distante não ganha frase, o status da TST não repete a validade (só a carga e os
itens com NÃO; o motivo inteiro no title, com teto de 240 px) e a origem do Forms, "Forms". As partes são `inline-block`, não flex: com `flex-wrap` o Chrome mede a coluna como se cada parte fosse uma
linha e quebrava 718 células a 1920 px.

**Números de 09/10/2026** (cópia de conferência com o cadastro da TST no lugar do livro): 773 extintores em 81 usinas,
**260 atrasados** (37 usinas), 29 perto de vencer, 121 sem validade, 363 em dia, **698 sem atualização** (a última
conferência do Forms é de março a agosto). 149 extintores (22 usinas) caem em "Sem região de campo": usinas de equipes
que não estão em nenhuma região da estrutura de O&M (o conserto é no cadastro, como na Central). Todas as 81 usinas
ligaram ao cadastro do Nexus; todas as regiões estavam com supervisor e coordenador em vaga.

**Como provar.**
- `python -m pytest -q tests/test_hseq_extintores.py`: as regras num dia fixo (inclusive a virada do mês e os limites
  de 30 dias) e a tela com o banco falso do Campo (livro ausente, faixa, cartões por responsável, a tabela por cliente
  com o responsável e os técnicos e a que abre sozinha, a ordem, os cinco filtros em cascata acima da tabela, ninguém
  abre filtrado pelo login, os técnicos não lidos, coluna faltando, o Baixar de cada usina e o não reconhecido que leva
  à usina).
- Regra igual à do App (fora do repositório: o cadastro tem nome de usina e o repositório é público): extrair
  `_ext_status` e `_ext_validade_fim` do `function_app.py` pelo AST e rodar as duas no `extintores_cadastro.json`. Em
  09/10: 424.377 comparações (773 × 549 dias, 01/08/2026 a 31/01/2028), 0 diferença; o status gravado no cadastro,
  773 de 773.

**Relatório em PDF** (`nexus/hseq/relatorio.py`, rota `/t/hseq/extintores/relatorio.pdf`; Levi, 09/10, com as
observações da TST: "TODOS OS EXTINTORES, CRÍTICOS, ATENÇÃO, OK · DETALHES DO EXTINTOR · o padrão será as fotos ao lado
de cada extintor, mas será possível puxar relatório só dos críticos"). Desde 18/10/2026 a tela só pede o de cada usina
(o "Baixar"; o de todos saiu da tela, ver "A tela"). Dentro do PDF, o agrupamento é por usina e dia, com os filtros da
tela; o filtro do relatório é o status da TST (`status=todos|criticos|atencao|ok`; o OK leva o "OK sem
validade"; nunca conferido só entra em "todos"). Com fotos (o padrão): cada extintor num quadro, a foto ao lado dos
detalhes; `fotos=0`: uma tabela por usina e dia. A FOTO é a cópia de 600 px em
`<dados>/hseq/extintores/fotos/pdf/<código>.jpg` (`fotos.foto_pdf`), feita UMA vez por foto recebida e refeita quando o
App manda outra (a inteira fica mais nova que a cópia); extintor sem foto sai com "Sem foto no Nexus". O PDF vai em
binário (`rl_config.useA85 = 0`): o ASCII85 padrão do reportlab, em Python puro (sem o acelerador em C), custava ~20 ms
por foto e +25% no arquivo. Por quê (14/10, com as 90 primeiras fotos da v265 do App): o PDF de todos reduzia as 90
fotos de 1600 px a cada pedido — 64,7 s no servidor, crescendo a cada conferência. Medido no PC com os 778 e 90 fotos
diferentes: todos, de 6,9 s e 3,5 MB para 4,6 s e 2,7 MB (o 1º pedido depois de foto nova, 5,5 s: faz as cópias); só os
críticos, de 2,0 s para 1,6 s; ~4,0 s do PDF de todos é a montagem das 108 páginas, com ou sem foto. Biblioteca:
reportlab (BSD, no `requirements.txt`). Sem o livro do App, a rota volta para a tela.

**Fotos** (`nexus/hseq/fotos.py`; Levi, 09/10: "quando tiver foto (ronda de extintor feita no app) ao expandir a usina e
aparecer os extintores deve ter a opção de visualizar foto"). A foto mora no App e o Nexus não lê o Azure: **o App envia**
a foto de cada conferência num `POST /t/hseq/extintores/foto` (multipart: `codigo`, `dia` AAAA-MM-DD, `ts` epoch,
`assinatura`, arquivo `foto`). Assinatura = HMAC-SHA256 hex de `"código|dia|ts|sha256 hex da foto"` com a chave
`HMAC-SHA256(NEXUS_PESSOA_HMAC, "nexus:hseq:fotos-extintor")`: a chave que o App e o Nexus já têm, nenhuma configuração
nova (sem ela a rota responde 503). O Nexus confere a assinatura e a hora (15 min), abre a imagem, regrava em JPEG de
até 1600 px e guarda a mais recente de cada extintor em `<dados>/hseq/extintores/fotos/<código>.jpg` (+ `.json` com o
dia); foto de dia mais velho não substitui. É a única rota sem login (`auth.ROTAS_PUBLICAS`), e só por POST. Na tabela
(a linha da usina aberta e a visão por extintor), o extintor com foto ganha a miniatura antes do código; o clique abre a
caixa das fotos da ronda (setas andam entre as fotos da usina). O PDF põe a mesma foto ao lado do extintor.

**O App envia desde a v265 (14/10/2026).** Até ali a foto ficava só no App: o técnico fotografava, e o PDF de 13/10 saía
sem foto (Levi, 14/10: "o Nexus precisa receber a foto!"). Um timer do App, a cada 10 min (minutos 4, 14, 24...), manda
as conferências com foto que o Nexus ainda não aceitou, da mais velha para a mais nova; a conferência refeita com outra
foto vai de novo. A 1ª volta (03:54Z) mandou as 90 pendentes desde a v257, todas "200 foto guardada". Conferido no
Nexus de produção: 90 extintores com miniatura, em 16 usinas, e o PDF da Aquiraz 2 (CRS200-INFC1-PPCI-EXT01) de 13/10
com a foto ao lado. Prova de uma foto: `GET /t/hseq/extintores/foto/<código>.jpg` (com login) e a miniatura na Tabela
(os cartões Por responsável não têm foto).

**Não reconhecido em campo** (Levi, 14/10/2026). Na Axis Linhares 1 - ES a equipe fez a ronda e só achou 4 dos 17
extintores do cadastro, e o App não tinha como dizer isso ("pode ter um botão no app de campo de 'Não reconhecido' para
o extintor e aí apareceria para a pessoa da Segurança"). O contrato com o App, duas colunas no FIM do livro
`Extintores`: `Não reconhecido em` (AAAA-MM-DD de Brasília, a marca que vale) e `Não reconhecido por (HMAC)` (a pessoa,
como o `Conferido por`); vazias quando não há marca ou quando uma conferência depois dela a desfez (o App limpa;
`extintores.nao_reconhecido` é a defesa: conferência depois da marca ganha, no mesmo dia vale a marca). O que o Nexus
faz:
- o não reconhecido sai de TODAS as contas: situações, sem atualização, cartões, Visão do responsável e o PDF por
  status (pode não existir);
- a tela o lista numa caixa âmbar logo abaixo da faixa (a marca mais nova primeiro, com quem marcou e a conferência de
  antes), e a faixa ganha o número "Não reconhecidos", que leva a ela; a linha (e o nome da usina, pelo teclado) leva à
  tabela filtrada naquela usina, com o cliente e a usina abertos (Levi, 18/10/2026: "ao clicar na linha já encaminhe
  para a tabela filtrando aquela usina");
- o PDF de todos põe uma seção à parte no fim e o número na casa que sobrava do resumo; o "Baixar" de uma usina leva
  os daquela usina (com o `dia` do link de antes, os marcados naquele dia); o de só críticos/atenção/OK e o da faixa,
  não;
- livro sem as duas colunas (o App antes da versão que as publica): ninguém é não reconhecido.
A TST resolve no cadastro (dar baixa, mudar de usina ou corrigir o código), que hoje é do App. Prova:
`tests/test_hseq_extintores.py` (os três testes do não reconhecido).

**Pendências.** A cobrança mensal por usina (ronda de extintor feita ou não no mês) e o painel da TST (baixa e
confirmação dos extintores novos) são do App; entram aqui quando houver o livro e o pedido. A baixa do não reconhecido
pela TST no Nexus (como a decisão da PT, assinada, que o App lê) fica para quando o Levi pedir.

## EPI e EPC

Levi, 09/10/2026: "Gostaria que criasse um campo de EPI / EPC começando apenas por EPI, puxando as luvas das rondas
diárias". A tela (`/t/hseq/epi`, contas em `nexus/hseq/epi.py`) tem a aba **EPI · luvas isolantes**; a aba **EPC** fica
apagada até haver de onde ler.

**De onde vem.** A ronda diária pergunta "As luvas isolantes estão disponíveis?" (item `infra_luvas` do App, v207,
29/09/2026: Sim ou Não, foto sempre, sem "Não se aplica"; o Não já vira ponto na Central do App e e-mail à TST). Desde a
v249 o App manda o checklist no `rondas_app_campo` (coluna "Checklist da ronda", "rótulo: valor; ..."), e a resposta sai
do texto (`epi.resposta`). A ronda (dia, usina, OS, quem fez) é a do fato único de ronda (`visao._rondas_ligadas`),
juntada ao livro cru pelo `Início`, como no Campo. A resposta ainda NÃO está no `fato_ronda`: se o App mudar o rótulo da
pergunta, nenhuma casa e a tela avisa. As fotos são as dos anexos da OS da ronda no Fracttal (o botão Fotos, o mesmo das
Rondas; a das luvas fica em Infraestrutura); ronda sem OS não tem foto no Nexus.

**As contas** (por usina mobilizada, como a Central): **sem luvas** = a última ronda respondeu Não ("desde" = o 1º Não da
sequência até ela; vale mesmo antiga, porque é o último dado); **sem verificação** = nenhuma resposta há 7 dias ou mais
(a régua da ronda pendente), ou nunca; **com luvas** = a última respondeu Sim há menos de 7 dias. Na linha, as 8 últimas
respostas (quadradinho verde = Sim, vermelho = Não) e quantos Não.

**Números de 09/10/2026** (banco real): 240 respostas de 28/09 a 09/10 (188 Sim, 52 Não); 128 usinas mobilizadas, **18
sem luvas**, 34 sem verificação, 76 com luvas.

**Como provar.** `python -m pytest -q tests/test_hseq_epi.py` (a resposta pelo texto, a situação por usina, o Sim antigo,
os cartões, a tabela com o botão de fotos, o aviso quando a pergunta some).

## APR e PT

Levi, 09/10/2026: "quero que esse visual e caminho vá para APR e PT de Segurança · HSEQ ... precisamos ter a visão
também de APR". A tela das Permissões de trabalho do Campo · App veio para cá (`/t/hseq/apr-pt`; o `/t/campo/pt` leva
para cá com os filtros). O código continua em `nexus/torres/campo` (`pagina_pt`, a aprovação `/t/campo/pt/<número>`,
os PDFs) e em `nexus/campo` (`visao.pts`, `pt_fracttal`, `decisao_pt`): a regra das contas é a de
`nexus/torres/campo/CLAUDE.md`.
- **Debaixo do `/nexus`** (porta única, 10/10/2026): o detalhe da PT esperando pede a assinatura, o `decidir` e o
  `quem` com o prefixo (`{{ raiz }}` e `nexusRota`), e a volta depois da decisão sai do `na_raiz` (o `volta` do
  formulário vem sem o prefixo; `nexus/torres/campo/CLAUDE.md`, "Debaixo do /nexus"). Os redirecionamentos da torre
  (Extintores, relatório) também passam pelo `na_raiz`: regra das torres em `nexus/torres/CLAUDE.md`.
- **Título:** "Permissões de trabalho e Análise Preliminar de Risco" (no menu, "APR e PT").
- **Colunas PT e APR** no lugar do "PDF", cada uma com o Baixar dela: a PT é o PDF que o App anexa no De acordo
  ("Permissão de Trabalho <número>"; PT negada não tem); a APR é o PDF que o App anexa desde a v251 ("APR OS 15223
  09-10-2026 07h42", + " v2" no Novo risco da APR do dia), e na OS com mais de uma APR vale a de horário mais perto da
  criação da PT (`pt_fracttal.apr_pdf`, rota `/t/campo/pt/<número>/apr.pdf`). Na aba Esperando a PT ainda não tem PDF
  (sai no De acordo); a APR já tem.
- **A APR do dia** (11/10/2026, Levi: "Por qual motivo algumas tarefas aparece como 'APR do dia'?"): a PT da APR por OS
  e dia chega do App sem tarefa nem ativo; a tela mostra as tarefas da OS no dia e os equipamentos, pelas tarefas do
  Fracttal (regra e fonte em `nexus/torres/campo/CLAUDE.md`, "A PT da APR do dia").
- **O detalhe da PT esperando** (a linha abre; "estou achando o atual muito cru"): o cabeçalho da PT (número, OS,
  tarefa, equipamento, técnico, equipe, usina, aberta), as atividades críticas, as respostas NÃO e o que falta, a
  região de campo e o gestor, **quem assina**, as duas assinaturas lado a lado (a do técnico na APR, do Fracttal pelo
  login de quem olha, carregada ao abrir; a da aprovação, esperando) e a decisão ali mesmo (De acordo / Não autorizo
  com o motivo, Ver PT, Baixar APR), que volta para a lista com os filtros dela. É o mesmo pedaço da Central de atenção
  > Permissões de trabalho (`campo/_pt_esperando.html`); desde 19/10/2026 a Central só pede dele o Por responsável
  (o modo `responsaveis`, só dela) e a tabela, e esta tela segue com os cartões por equipe, região e gestor.
- **Quem pode dar o De acordo** (Levi, 09/10): o Supervisor de Campo da região da usina (com a vaga aberta, o
  Coordenador de Campo), o gestor de contrato da usina, quem é do COS e um administrador do Nexus
  (`decisao_pt.aprovadores` / `pode_decidir`, conferido no servidor; quem não pode recebe a recusa dizendo quem pode).
  **Quem pediu a PT nunca a decide**, nem sendo administrador (o App descarta essa decisão: regra e caso em
  `nexus/torres/campo/CLAUDE.md`). **Quem é do COS** é o vínculo "COS" no cadastro de pessoas (Pessoas > Colaborador):
  é o "campo onde fazemos essa relação". O responsável e o técnico da usina se trocam na ficha da usina (Base > Registro
  mestre).
- **A decisão é por linha** (decisão 4 do Levi, 11/10/2026): cada linha da lista é uma PT × equipamento, e o De acordo
  ou o Não autorizo dela vale para aquele equipamento (o formulário manda o código do ativo; no banco, `codigo_ativo`
  em `nexus_pt_decisoes · fato_decisao_pt`). A assinatura do técnico é pedida pela linha (`?ativo=`): o "entre com o
  seu login do Fracttal" que sai dela volta para a mesma linha. Regra e contrato com o App em
  `nexus/torres/campo/CLAUDE.md` ("Aprovação de PT no Nexus") e em `nexus/dados/CLAUDE.md` ("O Nexus como fonte").
- **O App ainda não lê a decisão do Nexus** (`nexus_pt_decisoes · fato_decisao_pt`): até a v257 entrar no ar, quem
  libera o técnico é o De acordo dado pelo App, e a tela diz isso no detalhe. A v257 (pronta; o deploy é do Levi) NÃO
  confere quem pode decidir: confia no `pode_decidir` do Nexus, a única trava de quem pode.
- **O que o detalhe ainda não tem** (o painel do App mostra): riscos marcados, a atividade escrita, EPI e equipamentos
  com e sem, envolvidos, foto da equipe, aptidão e clima e o checklist item a item. Esses dados moram no App; entram
  quando o App mandar no livro de PT (sem nome em claro: a API tem leitura aberta).

**Como provar.** `python -m pytest -q tests/test_hseq_apr_pt.py` (a tela no HSEQ com o título e as colunas, o detalhe
com a assinatura e a decisão que volta, quem pode e quem não pode, o PDF da APR mais perto da PT, o vínculo COS) e os
testes de PT do Campo (`test_campo_visao.py`, `test_campo_central_supervisor.py`), que agora abrem `/t/hseq/apr-pt`.

