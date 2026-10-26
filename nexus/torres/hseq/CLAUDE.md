# CLAUDE.md — Segurança · HSEQ

Torre do menu "Segurança · HSEQ". Telas vivas: a **Mesa da Segurança** (a primeira, 24/10/2026), **Extintores** (com o
relatório de cada cliente e usina em PDF e Excel), **EPI e EPC** e **APR e PT** (09/10/2026). Riscos da semana, DSS e
Incidentes ainda são placeholder (a view com a mesma rota vence a genérica). As contas moram em `nexus/hseq/`; a view e o
template, aqui.

**O desenho da Segurança (24/10/2026, escolhido pelo Levi numa amostra com dado real).** Os filtros em squircle; os
cartões de responsável, a caixa dos não reconhecidos e o aviso do fim da tela em bevel (`corner-shape` em `hseq.css`; o
navegador que ainda não o desenha mostra o arredondado de sempre); o resto como no Campo. O aviso do fim da tela
(`_legenda.html`, macros `legenda` e `termo`) é a caixa com a borda amarela da dos não reconhecidos: o título, cada termo
com a cor dele e o que quer dizer, e o pé ("Esses avisos no final da tela pode ficar como bevel mas com uma borda
parecida com o aviso de extintores não reconhecidos"). Até ali era o parágrafo corrido do `cn-nota`. Em Extintores
o aviso ("Como cada extintor entra") fica numa exclamação amarela ao lado do título, que abre a caixa por cima da tela
(macro `aviso`; Levi, 24/10/2026: "deve ficar compactado em um símbolo de exclamação amarelo, quando a pessoa clica
aparece o comunicado"); clicar fora ou Esc fecha; no celular a caixa vem presa à tela.

## Mesa da Segurança (24/10/2026)

Levi: "Criação de mesa da segurança, como PTs atrasadas, extintores vencidos, usinas sem luvas"; e, no mesmo dia, "quero
duas visões: Por responsável e cliente (...) não queria em formato de lista mas em agrupamentos para o TST saber onde
atacar!". A primeira tela da torre, do setor Segurança (`Tela.do_setor`: quem é dele a vê sem marcar em Base → Acessos).
Rota `/t/hseq/mesa` (`mesa()`), template `mesa.html`; as contas em `_pendencias()` e `_cartoes()` na torre.
- **A faixa** (`kb-kpis`) com os quatro números de agora: **PTs paradas** (esperando o De acordo há mais de 2 h, a régua
  do Campo), **Extintores vencidos** (e em quantas usinas), **Não reconhecidos** (já sem os excluídos) e **Usinas sem
  luvas**. Embaixo, a linha **Atenção** (Levi, na visão geral: "Os quatro + os de atenção"): extintor perto de vencer,
  sem atualização (só o que não está vencido nem perto de vencer, para não contar duas vezes), usina sem verificar as
  luvas e nova ronda pedida que a equipe ainda não refez.
- **Agrupar por Responsável UFV** (o padrão) ou **Cliente** (`?ver=cliente`): um cartão por grupo (bevel), com o total do
  que pede ação agora, os quatro números e, no pé, os de atenção que ele tem; o que tem mais primeiro, o "Sem
  responsável O&M / Sem cliente" por último. Nenhum caso aparece um por um na tela.
- **A visão geral** (a TST, 24/10/2026: "Adicionar uma opção de visão geral (um resumo com todas as pendências, sendo
  possível filtrar por cliente, por UFV e por supervisor) e ter a opção de baixar"): os filtros **Cliente, UFV e
  Responsável UFV** (`FILTROS_MESA`; o supervisor é o Responsável UFV, o mesmo dos cartões), em cascata como os de
  Extintores (`_opcoes_ext`, com as listas tiradas das pendências), valem na faixa, na linha de atenção, nos cartões e
  na planilha. **Baixar planilha** (`/t/hseq/mesa/pendencias.xlsx`, `planilha.gerar_pendencias`): a aba Resumo (uma
  linha por responsável ou cliente, os oito números) e uma aba por pendência, caso a caso (`ABAS_PENDENCIAS`), com os
  filtros e a fonte que não foi lida no topo. Medido no banco real em 24/10: 42 KB.
- Cada número leva à tela de origem filtrada pelo grupo e pelos filtros do alto (`_links`): Extintores com o Status
  (Atrasados, Não reconhecidos, Perto de vencer, Sem atualização), EPI na tabela com "Sem luvas" ou "Sem verificação"
  (a UFV vai na busca dele, que não tem o filtro de usina); a PT ainda não tem o filtro de responsável nem de cliente, e
  o número leva a APR e PT inteira.
- Só lê; a fonte que falha diz e o número dela vira "—", sem derrubar as outras. Não lê o Fracttal.
Prova: `tests/test_hseq_mesa.py` (os grupos, os filtros em cascata, os de atenção e a planilha).

**O e-mail semanal das pendências** (24/10/2026; `nexus/hseq/email_semanal.py`, livro
`nexus_hseq_email · fato_email_pendencias`, no catálogo antes da 1ª gravação). A TST: "Receber report semanal das pendências por email, pra mim e pro
supervisor responsável"; Levi escolheu mandar pelo App de Campo, que já manda e-mail. Toda segunda depois das 07:00 de
Brasília o Nexus monta o e-mail de cada destinatário com as mesmas contas da Mesa (`_pendencias(fl)`) e publica uma
linha por destinatário, uma vez por semana; o App lê, manda e diz o que mandou.
- **Quem recebe:** a TST (as pessoas do setor Segurança em Base → Acessos → Pessoas e setores, pelo código do e-mail) com todas
  as usinas, e cada Responsável UFV com pendência, só com as usinas dele, pelo código do usuário do Fracttal ligado a ele
  ou, sem ele, do e-mail da ficha (`destinatarios`). Sem código, não recebe: a prévia lista quem ficou de fora (medido
  no banco real em 24/10: 1 da TST e 5 responsáveis recebem, 2 responsáveis sem código).
- **O que vai no livro** (a API é compartilhada, regra 8): o código (HMAC) e o número da pessoa, nunca nome nem e-mail.
  O assunto e o corpo (texto e HTML) levam os quatro de agora, os de atenção, as usinas com mais pendências (até 25) e
  o link para a Mesa e a planilha filtradas pelo número da pessoa (`?r=`, que a Mesa traduz no Responsável UFV dela).
  Cada linha assinada (HMAC, rótulo `nexus:hseq:email`).
- **O App** (contrato fechado com a sessão do App de Campo em 24/10/2026, a construir com o OK do Levi): acha o e-mail
  pelo código (o cadastro e as atribuições que ele conhece; a TST sem código casa no e-mail do aviso das luvas), manda
  pelo Microsoft Graph com fila e reenvio, e confirma no livro `email_app_campo · Envios` (no catálogo: Semana,
  Destinatário (HMAC), Papel, Enviado em, Via, Tentativas, Erro e Situação; o que não sai até a segunda seguinte vence).
  **Hoje nada sai:** o tenant barra o Graph do App ("AppOnly AccessPolicy", desde 23/09; o aviso das luvas também está
  parado) até a T.I. liberar.
- **Ligar:** `NEXUS_HSEQ_EMAIL_AUTO=1` no `.env` do servidor (sem ela, desligado: o livro só nasce quando o App estiver
  pronto para ler). A **prévia** (`/t/hseq/mesa/email`, o botão "Prévia do e-mail semanal" da Mesa, só para quem decide
  na Segurança) mostra quem recebe nesta semana e o e-mail de cada um, com os nomes, que o livro não leva.
Prova: `tests/test_hseq_email.py` (quem recebe, o e-mail sem nome de pessoa e assinado, o link `?r=`, a prévia e quem a
vê, a publicação uma vez por semana, o catálogo).

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
  Cliente, Usina, Responsável UFV, Equipe, a busca e, desde 24/10/2026, o **Status** (`f`, o mesmo da faixa:
  Atrasados, Perto de vencer, Sem validade, Em dia, Sem atualização e Não reconhecidos; Levi: "Adicione também um
  filtro de status (...) Insira não reconhecidos no status também!"). Com "Não reconhecidos", a tabela fica só com as
  usinas que têm não reconhecido e, nelas, só eles (`_lista` na torre: o não reconhecido não tem situação). Os cinco
  primeiros: **em cascata** como a tela Técnicos por usina do PCM (cada lista traz o que existe com os outros filtros;
  a escolhida fica mesmo sem resultado), com o "Sem cliente / Sem responsável O&M / Sem equipe" no fim
  (`extintores.valor_do_filtro`). O Responsável UFV é o Responsável O&M da ficha da usina (o setor "Responsáveis
  UFV"). Saíram a região do Brasil, a região de campo e o gestor, e com eles o filtro que vinha do login (o Supervisor
  de Campo abria na região dele): **ninguém abre filtrado**. Valem na faixa, na caixa, na tabela, nos cartões e no
  "Baixar". O cliente vale também no EPI, que segue com os filtros do Campo.
- **Agrupar por Cliente** (o padrão; Levi, 18/10: "Quero agrupado por Cliente, abrindo o cliente terá as usinas desse
  cliente. É importante ter a coluna do responsável desse usina e o ou os técnicos da usina!";
  `extintores.por_cliente`) e **por Extintor** (`ver=extintor`: o mais grave primeiro; no filtro "sem atualização", a
  conferência mais antiga primeiro). Colunas: Situação, Última conferência, Cliente e usina, Responsável, Técnicos,
  Quantidade de extintores (só o total, centrada), Recarga mais próxima (a vencida há mais tempo ou, sem vencida, a
  próxima; a data em cima e o "venceu há" embaixo, centrados: "como as linhas são grossas da para botar"), **Status**
  e os três pontos. O Status (24/10/2026, no lugar do "Status da TST": "vai quebrar o texto a cada assuntos (...) A
  ideia é ficar algo bem mais visual") é uma linha por situação com a cor dela (a barra das proporções em cima saiu no
  mesmo dia: "Tira essa barra de cores da coluna de status"; "116 atrasados", "40 perto de vencer", "77 sem validade",
  "335 em dia", "13 não reconhecidos"). **Última conferência, Responsável e Técnicos só aparecem com um cliente
  aberto** (Levi: "não precisa das colunas responsável e técnico na primeira visão, só ao clicar na linha"; e "a coluna
  de última conferência (...) também só deve aparecer no drill down"): a tabela leva `hs-fechada` enquanto nenhum
  cliente está aberto (as colunas `hs-col-aberta` somem), e o clique a tira. A linha do cliente abre as usinas dele **na mesma tabela**
  (UMA linha por usina, `por_usina`: a última conferência é a mais recente dos extintores dela), e a usina abre os
  extintores numa tabela menor, cada um com a conferência dele. Ordem: o mais grave primeiro, depois a recarga mais
  próxima; "Sem cliente" por último. Com o filtro de cliente o cliente já abre; com o de usina, a usina também.
- **Os técnicos** vêm da tela Técnicos por usina do PCM (`extintores.tecnicos_por_usina`, livro `nexus_pcm_atribuicoes`:
  quem vê e ronda a usina no App, um embaixo do outro; o apoio agendado para depois de hoje ainda não conta). Lista que
  não foi lida: a coluna diz "não lido" e a tela avisa, e nunca "sem técnico". Medido em 18/10: 174 usinas com técnico,
  68 com dois.
- **A página é leve: o resumo vem nela, os extintores só ao abrir a usina e a foto só no clique** (19/10/2026). O
  Raio-X do servidor às 17:15 pegou a tela 21 s montando a página (o servidor é um notebook que também roda o banco, e
  enquanto isso o resto do Nexus fica lento): a visão por cliente levava TODOS os extintores, escondidos (897 KB, 1.105
  linhas), e abrir uma usina pedia todas as miniaturas juntas. Levi: "primeiro mostra a informação e só quando a pessoa
  clica que começa a carregar as imagens". Agora a página leva só as linhas de cliente e de usina, com todos os campos
  de antes; a linha da usina busca os extintores dela na 1ª vez que abre (rota `extintores_usina`, o pedaço
  `_extintores_usina.html`, os mesmos filtros da tela e o da faixa, a usina com o cliente) e os guarda na página
  ("Carregando os N extintores...", e na falha o "Tentar de novo"); com o filtro de usina (o clique num não
  reconhecido) eles já vêm na página. Nenhuma lista leva `<img>` de extintor: no lugar da miniatura, o botão "Foto" com o
  dia da foto, e a caixa das Rondas pede a imagem no clique. As linhas do extintor moram em `_extintores_linha.html`
  (a tela e o pedaço usam as mesmas). Cada linha de cliente e de usina vai numa linha só do HTML (o recuo pesava ~20 KB).
  Medido no banco real (só leitura, no PC): de 897 KB e 1.105 linhas para 199 KB e 207; quente, de 0,16 s para 0,05 s;
  o pedaço de uma usina, 1 a 10 KB em 0,01 s. Os testes do orçamento: nenhuma `<img>` de foto nas listas, a página sem
  linha de extintor, com 810 extintores abaixo de 200 KB, o pedaço só com a usina dele e a linha da usina com os campos.
- **Cabe a 1440 px** com as usinas e os extintores abertos (medido no banco real, 18/10: a caixa tem 1.168 px). O cliente
  abrindo uma tabela dentro da linha e a usina outra dentro dela pedia 1.212 px; com as listas "N atrasados · ..." numa
  parte só, 1.391. Por isso: cliente e usinas na mesma tabela, as listas quebram entre os itens (`ext-lista`) e o nome da
  usina, do cliente e do responsável quebram entre as palavras (cada técnico numa linha). A 375 px a tabela rola dentro
  da caixa e a página não passa da largura.
- **Por responsável** (`modo=responsaveis`; o filtro da faixa volta à tabela): um cartão por Responsável O&M da usina,
  como a Central de atenção, com os mesmos números dos cartões de antes; o clique leva à tabela filtrada por ele.
- A usina vai **sem a região ao lado** (Levi, 11/10: "Em usina pode tirar a região do lado, fica estranho!"). 300 linhas
  na visão por extintor. O CSS é o `campo.css` e o `hseq.css` (a tabela, os filtros e a caixa).
- **Os três pontos da linha** (Levi, 24/10/2026: "ao invés da coluna relatório, pode substituir para três pontos ao
  passar o mouse na linha, aí clicando nos três pontos tem duas opções: Exportar PDF, Exportar planilha"): a última
  coluna, sem nome ("tira esse nome ações de uma coluna que não existe"), tem o botão que aparece ao passar o mouse (no
  celular, sempre). O menu é UM só, no fim da tabela: o clique o leva para a linha e põe nele os endereços dela
  (`data-args`, os filtros da linha; `nexusRota`); com um menu por linha a página passava dos 200 KB do orçamento. Na
  usina, para a Segurança, o menu tem também **Pedir nova ronda** (`data-ronda`), ver abaixo.
- **O relatório é só unitário, de cada cliente e de cada usina, em PDF e em Excel** (nos três pontos). Levi, 18/10: "O
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
(a usina aberta e a visão por extintor), o extintor com foto ganha o botão "Foto" com o dia dela (até 19/10/2026, uma
miniatura: ver "A página é leve"); o clique abre a caixa das fotos da ronda e só então pede a imagem (setas andam entre
as fotos da usina). O PDF põe a mesma foto ao lado do extintor. No servidor (19/10): a listagem da pasta
(`fotos.disponiveis`) fica guardada 30 s e o `receber` a renova; a miniatura da rota `?mini=1` (que a tela não usa mais)
vem da memória ou da cópia de 160 px em `mini/<código>.jpg` e só a 1ª vez lê a foto inteira, reduzida com o `draft`.

**O App envia desde a v265 (14/10/2026).** Até ali a foto ficava só no App: o técnico fotografava, e o PDF de 13/10 saía
sem foto (Levi, 14/10: "o Nexus precisa receber a foto!"). Um timer do App, a cada 10 min (minutos 4, 14, 24...), manda
as conferências com foto que o Nexus ainda não aceitou, da mais velha para a mais nova; a conferência refeita com outra
foto vai de novo. A 1ª volta (03:54Z) mandou as 90 pendentes desde a v257, todas "200 foto guardada". Conferido no
Nexus de produção: 90 extintores com miniatura, em 16 usinas, e o PDF da Aquiraz 2 (CRS200-INFC1-PPCI-EXT01) de 13/10
com a foto ao lado. Prova de uma foto: `GET /t/hseq/extintores/foto/<código>.jpg` (com login) e o botão "Foto" na
Tabela (os cartões Por responsável não têm foto).

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
  antes), e a faixa ganha o número "Não reconhecidos", que leva a ela; a caixa recolhe pelo título (Levi, 24/10/2026:
  "ser possível encolher essa informação para ter o foco na tabela"), aberta na 1ª vez, e cada navegador lembra a
  última escolha (`localStorage`, `nexus.hseq.naorec`); a linha (e o nome da usina, pelo teclado) leva à
  tabela filtrada naquela usina, com o cliente e a usina abertos (Levi, 18/10/2026: "ao clicar na linha já encaminhe
  para a tabela filtrando aquela usina");
- o PDF de todos põe uma seção à parte no fim e o número na casa que sobrava do resumo; o "Baixar" de uma usina leva
  os daquela usina (com o `dia` do link de antes, os marcados naquele dia); o de só críticos/atenção/OK e o da faixa,
  não;
- livro sem as duas colunas (o App antes da versão que as publica): ninguém é não reconhecido.
Prova: `tests/test_hseq_extintores.py` (os testes do não reconhecido).

**A Segurança decide na usina** (24/10/2026; `nexus/hseq/decisoes.py`, o livro `nexus_hseq_extintores`, registrado no
catálogo antes da 1ª gravação). Levi: a pessoa da Segurança pode aceitar o não reconhecido "e aí o extintor vai sumir ou
solicitar que o técnico faça uma nova ronda"; "ao ir para a usina a TST resolve"; e, na 2ª rodada, "pedir uma nova
ronda é uma nova ronda do zero então será por usina, por extintor é só o botão de aceitar, quando a TST aceita o
extintor é excluído e vai para um histórico de extintores excluídos com o motivo 'Não reconhecido em campo'".
- **Onde:** na usina, na tabela geral. Os não reconhecidos dela vêm em cima dos outros extintores (fundo âmbar, situação
  "Não reconhecido"), fora das contas; a linha da usina diz "N não reconhecidos", e a usina em que a equipe não achou
  nenhum extintor também aparece. A caixa âmbar do alto só aponta para a usina.
- **Excluir** (`fato_exclusao_extintor`), por extintor, de dois jeitos: o **Aceitar** do não reconhecido (pergunta
  antes; motivo "Não reconhecido em campo", responde à marca daquele dia) e o **botão direito** na linha de qualquer
  extintor (Levi: "o técnico pode ir na linha do extintor, clicar com o botão direito e poder excluir o extintor"; a
  caixa pede o motivo, Retirado da usina, Duplicado no cadastro ou Outro, este com a observação, que vai só cifrada).
  O excluído sai das contas, da faixa, da tabela, da Mesa, do PDF e do Excel (`decisoes.separar`) e vai para
  **Excluídos** (`modo=excluidos`, o mais novo primeiro, com o motivo e quem). **Volta** se a equipe o conferir numa
  ronda de um dia depois da exclusão (existe), e o histórico diz "voltou: conferido em dd/mm".
- **Pedir nova ronda** (`fato_pedido_ronda`), da usina inteira, do zero, nos três pontos da linha da usina. A linha
  mostra "nova ronda pedida em dd/mm · N de M refeitos" e o item do menu diz que já foi pedida. A ronda é do zero e
  vale pela hora (combinado com o App de Campo em 24/10/2026, v296, que aplica a MESMA regra e mostra a ronda pendente
  à equipe): o pedido sai quando TODOS os extintores atuais da usina, sem os excluídos, chegam conferidos depois dele
  (a "Recebida em", UTC, do livro `extintores_conferencias_app_campo · Conferências`, lido só quando há pedido:
  `extintores.recebidas`) ou marcados como não reconhecidos depois dele; pedido às 10h e ronda às 14h do mesmo dia é
  atendido. A marca de não reconhecido conta pela hora a partir da v296 do App (o "Não reconhecido em" passa a vir com a hora UTC
  em que o servidor a recebeu); antes, só com o dia, ela conta do dia seguinte ao pedido em diante; usina sem extintor segue
  pendente. Grava também o nome da usina que o App usa (`usina_app`).
- Saiu a "Editar quantidade de extintores" (Levi: "como cada extintor tem um cadastro unitário então o certo seria" a
  exclusão por extintor).
- **Editar o extintor** (`fato_edicao_extintor`; a TST, 24/10/2026: "Eu consigo editar o cadastro de extintores?"), no
  mesmo botão direito ("Editar extintor"): a caixa vem com o que a tela mostra (local, posição, classe, peso e as duas
  validades; o código não muda, nem se cadastra extintor novo, que entra pelo App) e grava só o que mudou
  (`decisoes.editar`, `campos` = JSON {coluna do livro do App: valor novo}). As validades no formato da etiqueta
  (recarga MM/AAAA ou Sem data; hidrostático AAAA, MM/AAAA ou Sem selo), o peso em kg (vazio não mexe: há extintor
  sem peso no cadastro). A tela mostra o editado na hora, com a situação refeita (`extintores.editado`, por cima da
  linha do livro guardada em `_bruto`) e a marca "editado dd/mm", em todas as contas (a Mesa, o PDF e o Excel
  também, porque a edição entra no `decisoes.separar`), até uma conferência num dia depois da edição; aí vale o que o
  App publicar.
- **Quem:** o administrador e quem é do setor Segurança (`decisoes.pode_decidir`), sempre com um login de pessoa (a
  senha de administrador vê os botões e é recusada: o histórico guarda quem fez). Os outros veem a situação sem botões
  nem botão direito. Gravar: POST com a trava `_de_outro_site`, 303 de volta à usina com o aviso (`?ok=`/`?erro=`, que
  não seguem nos links).
- **O App lê o livro desde a v296 (24/10/2026)**, a cada 5 min: aplica as exclusões e os pedidos de ronda (as mesmas
  regras daqui). A edição entra no App quando ele ler o `fato_edicao_extintor` (o contrato foi mandado à sessão do App
  de Campo); até lá, ela vale só no Nexus. O contrato: as linhas do `fato_exclusao_extintor` (código, motivo,
  `marca_dia`), do `fato_pedido_ronda` (`usina_id`, `usina_app`) e do `fato_edicao_extintor` (código, `campos`), cada
  uma assinada com HMAC (rótulo `nexus:hseq:extintores`, a chave derivada da NEXUS_PESSOA_HMAC, como as atribuições do
  PCM; os textos assinados em `decisoes.assinatura`): o App aplica só a linha assinada.
Prova: `tests/test_hseq_decisoes.py` (as regras da volta e da ronda pendente, quem pode, a assinatura, o Aceitar e o
histórico, o botão direito com o motivo, a ronda da usina, a edição e a régua dela, a senha de administrador, o filtro
de Status, o catálogo).

**Pendências.** O App gravar a edição no cadastro dele (`fato_edicao_extintor`). A cobrança mensal por usina (ronda de extintor feita ou não no mês) e o painel da TST (confirmação dos
extintores novos) são do App; entram aqui quando houver o livro e o pedido.

## EPI e EPC

Levi, 09/10/2026: "Gostaria que criasse um campo de EPI / EPC começando apenas por EPI, puxando as luvas das rondas
diárias". A tela (`/t/hseq/epi`, contas em `nexus/hseq/epi.py`) tem a aba **EPI · luvas isolantes**; a aba **EPC** fica
apagada até haver de onde ler.

**Por responsável** (24/10/2026, Levi: "tirar visão de região de campo e gestor de contrato, tem que ser por
responsável da usina, aí mostra as usinas"): um cartão por Responsável O&M da ficha da usina (`epi.por_responsavel`),
com os números e as usinas dele, as sem luvas primeiro (em vermelho), depois as sem verificação (em azul); o cartão leva
à tabela filtrada por ele. Filtros: região do Brasil, cliente, responsável UFV e a busca; saíram a região de campo e o
gestor de contrato, e com eles o filtro que vinha do login. Na tabela, a usina diz o responsável.

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
os cartões por responsável com as usinas, os filtros, a tabela com o botão de fotos, o aviso quando a pergunta some).

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
- **Só por responsável, e os filtros de cliente, usina e responsável** (24/10/2026, Levi: "Tire por equipe e por região
  de campo e deixe apenas por responsável"; "Em tabela tire a coluna região e coloque a coluna responsável"; "Tire o
  filtro de região e gestor de contrato e região do brasil. Quero filtro para cliente, usina e responsável com contador
  para cada! Quero os mesmos filtros no histórico!"). A aba Esperando abre nos cartões por Responsável UFV (o mesmo
  `visao.pt_por_responsavel` da Central; o cartão leva à tabela dele) ou na Tabela, que leva a coluna Responsável no
  lugar da região (`coluna_responsavel`: o pedaço é o mesmo da Central, que segue com a região). Os filtros
  (`FILTROS_PT`: Cliente, Usina, Responsável UFV) vão em cascata, cada opção com quantas PT tem com os outros filtros
  ("Thopen (12)"), nas duas abas; a busca fica (o número da OS acha a PT: a TST procurou a da OS 16866 no Fracttal, onde
  só vai o PDF da APR). Os endereços de antes (por equipe, região ou gestor, `regiao`, `regiao_campo`, `gestor`) caem no
  Por responsável e não filtram.
- **A aba Sem APR ou PT** (a TST, 24/10/2026: "preciso de uma visibilidade de atividades realizadas sem APR e sem PT";
  `nexus/hseq/apr.py`): do livro `apr_app_campo · APR` que o App publica desde a v298 do servidor (no catálogo antes da
  1ª gravação, fato `apr`; contrato com a sessão do App de Campo), duas listas de 20 em 20 com os mesmos filtros:
  **APR que pedia PT e ficou sem** ("Precisa de PT" = sim e PT vazia; vazio = ainda não medido, não entra) e **OS
  fechada sem APR** (a tarefa do `fato_fechamento` desde 10/10/2026 sem APR da mesma OS no mesmo dia ou no anterior,
  nem APR da tarefa com a mesma OS e tarefa; por OS e dia, com a coluna "APR da OS", a última antes do fechamento, ou
  "nenhuma", e a "OS criada em", do `fato_tarefa_os` (Levi, 26/10: "quero uma coluna de data de criação da OS"; a OS
  em processo ou em verificação, onde ela fica depois de o App fechar a tarefa: 50 das 52 em 26/10; a finalizada fica
  "—"); a régua não olha o técnico). Medido no livro real em 25/10 (875 APRs, 149 já medidas): 2 APRs pediam PT e
  ficaram sem (a mesma conta do App) e 39 OS fechadas sem APR, 12 sem APR nenhuma; a régua começou com 138, dos quais
  48 eram de 09/10 (o dia da troca para a v251) e 89 tinham a APR no dia anterior (a tarefa da noite fecha depois da
  meia-noite). Sem o livro, a aba diz que ele ainda não chegou.
  Caso que motivou: a OS 16866 tinha PT (PT-16866-2010-1457, da APR do dia); a TST a procurou no Fracttal.
- **O histórico inteiro, de 20 em 20** ("Em histórico quero todo o período mostrando de 20 em 20 para não pesar tanto";
  saiu o período 7/30/90 dias): `POR_PAGINA_PT`, `?pag=`, com "1–20 de N" e as páginas em volta da atual; leva a coluna
  Responsável depois da Usina. Medido no banco real em 24/10: 598 decididas, 74 KB a página; com 13 colunas a tabela
  passa ~130 px da caixa a 1440 px e rola dentro dela (com 12 já passava 18).
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
  login de quem olha, carregada ao abrir; desde 26/10/2026 a da APR feita no App sai do PDF dela, sem login; a da
  aprovação, esperando) e a decisão ali mesmo (De acordo / Não autorizo
  com o motivo, Ver PT, Baixar APR), que volta para a lista com os filtros dela. É o mesmo pedaço da Central de atenção
  > Permissões de trabalho (`campo/_pt_esperando.html`); desde 19/10/2026 a Central e, desde 24/10, esta tela só
  pedem dele o Por responsável (o modo `responsaveis`) e a tabela.
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

