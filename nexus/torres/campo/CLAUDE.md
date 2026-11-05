# CLAUDE.md — torre Usinas 360° (o id `campo`)

**O nome (05/11/2026):** a torre se chamava "Campo · App". Levi, pelo Scrum master: "Quero ideias de nomes
alternativos para o campo 'Campo app'. Como ele engloba pendências e visão geral do supervisor queria que tivesse um
nome mais aberto, até para botar a visão do cliente também junto!"; depois, "Usinas 360°" e "Mande!". Só o nome que
aparece mudou (`TORRE.nome`, a descrição do Início e os textos das telas que diziam o nome): o id `campo`, o
`/t/campo`, as chaves `campo/<tela>` dos Acessos e os livros ficaram, para nenhum link, favorito, acesso ou teste de
rota quebrar. No menu, logo abaixo de Comando (`ordem=5`; no mesmo dia: "usina 360 abaixo de Comando"), e a
Zeladoria logo abaixo de Chamados (`ordem=55`). O Nexus não tem busca no menu: nada a normalizar no "°".
Abaixo, "Campo · App" é o nome de quando cada coisa foi feita.

A visão do Nexus sobre o trabalho de campo. **Nenhuma tela abre o painel do App nem aponta para o Azure** (Levi,
05/10/2026: "quero parar de referenciar o Azure e ter uma visão nossa!"): todas leem o banco do Nexus (API db_performace).
Leia também o `CLAUDE.md` da raiz e, antes de pôr dado novo no banco, o `nexus/dados/CLAUDE.md` (PRIORIDADE 0).

## Regra: tudo em paralelo (Levi, 04/10/2026)

"Por hora todas as decisões para o Nexus são paralelas, não deve afetar o funcionamento atual." Nada aqui escreve no
App nem no Fracttal. Devolver OS e encaminhar ponto continuam no App. Sem link para o painel do App e sem
"Abrir no App". **A OS aparece só com o número, sem "#"** (Levi, 05/10: "Em OS tira esse #").

**Exceções: a decisão da PT** (Levi, 05/10: "Técnico faz APR e PT -> Chega no PG -> Atualiza para os steakholders ->
Atualiza na aprovação de PT -> Supervisor faz -> Fica salvo!"; ver "Aprovação de PT no Nexus" abaixo) **e a
Aprovação de OS** (desde 05/11/2026 o quadro por fatos, com o Aprovar no cartão e em lote: o Concluir do OS Creator, com
o login do Fracttal de quem clica, como no OS Creator Web; ver "Aprovação de OS").

## As telas

| Tela | De onde vem | Quem calcula |
|---|---|---|
| **Visão do responsável** (12/10/2026, a 1ª do Campo) | o **Painel** (28/10/2026, a tela inicial de um responsável: seis quadros, ver "O Painel do responsável" abaixo) e três blocos: Performance (meta do Gerencial publicada, diário da disponibilidade, sinais da Confiabilidade), Acompanhamento (Central e PT, a limpeza das Rondas, chamados de `nexus_chamados`, extintores do HSEQ) e, desde 18/10/2026, Manutenção (as tarefas das OS do Fracttal em `nexus_os`, os motivos do PCM, a programação); e a aba **Ranking das equipes** (18/10/2026: as notas do App em `fato_fechamento` e `fato_ronda`) | `campo/responsaveis.py` (junta; cada número é da tela dona), `campo/manutencao.py` (a conta do bloco Manutenção) e `campo/ranking_equipes.py` (a régua do ranking por região do App) |
| **Visão do cliente** (05/11/2026) | o tempo real da plataforma (a Entrada, pela ponte só de leitura) + o Gerencial (a meta, a mesma linha da Visão do responsável) + o Andamento da Ronda COS (os chamados à distribuidora) + `fato_tarefa_os` (as OS) + `fato_programacao` (a próxima visita) | `campo/visao_cliente.py` (junta; nenhuma conta nova, ver "Visão do cliente" abaixo) |
| **Ocorrências** (18/10/2026) | o livro `nexus_ocorrencias` (escrito nesta tela) + cadastro do Nexus | `campo/ocorrencias.py` (ver "Ocorrências com plano de ação" abaixo) |
| Central de atenção | `fato_ronda` e `fato_pt` (passo 4, ver "De onde vem o dado") + cadastro do Nexus | `visao.atencao` (conta nossa) |
| Aprovação de OS (quadro por fatos desde 05/11/2026) | fila de verificação do Fracttal INTEIRA (só GET) + nota e fechamento do livro do App + os anexos das OS (1 GET por OS, lido por trás, e as fotos pelo S3) + o Responsável O&M da usina (cadastro); aprovar é o Concluir do OS Creator, no cartão ou em lote | `campo/prefiltro.py` (as colunas) sobre a conta pronta das regras copiadas do App; `campo/prefiltro_fundo.py` (as fotos) |
| Permissões de trabalho → **em Segurança · HSEQ > APR e PT desde 09/10/2026** (`/t/hseq/apr-pt`; `/t/campo/pt` leva para lá). O código continua aqui (`pagina_pt`, a aprovação `/t/campo/pt/<número>`, os PDFs da PT e da APR); a regra de lá está em `nexus/torres/hseq/CLAUDE.md` | `fato_pt` (+ `pt_app_campo` para o texto) | `visao.pts` (conta nossa) |
| Rondas | `fato_ronda` (App, checklist da carga única, avulsa) + usinas mobilizadas do cadastro + `fato_fechamento` (última OS da usina) + a validação por foto (só sujidade e vegetação) | `visao.rondas` (conta nossa) |
| Ronda avulsa (`/t/campo/rondas/avulsa`) | lançada à mão no Nexus, com o login do Fracttal | `campo/ronda_avulsa.py` |
| **Zeladoria** (26/10/2026) | as rondas (o checklist da OS de ronda, a carga, a avulsa e a validação por foto, como na aba Sujidade e vegetação) + as tarefas de Zeladoria do Fracttal (`nexus_os · fato_tarefa_os`) + `zeladoria_app_campo` (os serviços de terceiros, no fim da tela) | `campo/zeladoria.py` (conta nossa; ver "Zeladoria" abaixo) |
| Triagem de qualidade | `fechamentos_app_campo` + rondas | regras copiadas do App |
| **Ranking de pontos** (13/10/2026) | `ranking_app_campo` (o placar do ciclo, que o App publica) | **o App** (`_ciclo_v2`); o Nexus só mostra (ver "Ranking de pontos" abaixo) |
| Rotas do dia | placeholder: programação do PCM + localização das usinas | — |

**Saíram em 08/10/2026: Ordens de serviço, Imagens da ronda e Ranking** (Levi: "ordens de serviço e imagens da ronda e
ranking são redundantes"): a nota do fechamento está na Aprovação e na Triagem, a comparação por região, equipe e
supervisor no Painel das Rondas, as fotos no histórico da usina. Saíram do menu, com rota, template, `campo/ordens.py`,
`visao.ranking` e os testes delas; `/t/campo/os` e `/imagens` levam à Central (`TELAS_QUE_SAIRAM`, para quem guardou o
endereço). O `/ranking` voltou em 13/10/2026 com OUTRA tela, o Ranking de pontos (abaixo); a comparação por região e
equipe não voltou. O `_gestao_os` (a conta da antiga Ordens) saiu da cópia das regras do App na recópia de 09/10
(ver "As contas copiadas do App").

Fora daqui: a "APR e PT" da torre HSEQ responde outra pergunta (OS de risco sem APR ou PT assinada).

## Ranking de pontos (13/10/2026)

Levi: "Quero que traga o ranking de pontos dos técnicos para o Nexus. Cria uma seção de Ranking de Pontos no App de
Campo!". É o placar do CICLO do App: a régua de 01/09/2026 revista em 30/09 (`_ciclo_v2` no `function_app.py`; o App
Setting `PLACAR_V2` diz se é ela que o técnico vê), a mesma da aba "Ranking por colaborador" do painel do App.

- **Quem calcula é o App, e o Nexus não recalcula** (`visao.ranking_pontos`, `campo/ranking.html`): o App publica o
  placar no livro `ranking_app_campo` (aba `Ranking`), de hora em hora aos :25, junto com os outros livros: 1 linha =
  1 técnico × 1 mês (o corrente e o anterior), com quem está FORA DO CICLO (o motivo, sem posição). Recalcular já deu
  errado aqui: a nota do coletor batia com a do painel do App em 14% das tarefas (05/10).
- **Pessoa só pelo HMAC do e-mail** (`Técnico (HMAC)`, a API é de leitura aberta); o nome sai do cadastro do App na hora,
  e código sem dono fica "—" (a tela diz quantas linhas vieram sem nome), nunca o código.
- **O nome é o "Nome padrão" do cadastro, e o pódio traz o e-mail** (03/11/2026, Fillipe Figueiró: o 3º de outubro saiu
  com o nome curto igual ao de outro técnico, e o pódio vira pagamento no Caju). O `livros_app.pessoas_por_codigo` dá o
  `nomePadrao` do cadastro e, só na falta dele, o nome completo, que o `nome_curto` corta no primeiro e no último nome
  (o nome longo de um técnico virava o nome curto de outro). Vale para toda tela do Campo que acha a
  pessoa pelo código do App. O e-mail vai no pódio (`rk-email`) e no título da célula do nome nas tabelas.
- **A região é a de MAIS fechamentos do técnico no mês**, e quem diz é o App (a v320, 03/11; até a v319 era a do último
  fechamento: um técnico fez quase tudo na SP Leste 02 e saiu na SP Leste 05, onde fechou 3 tarefas).
- **As colunas são um contrato**: a tela lê pelo NOME, e `tests/test_campo_ranking_pontos.py` (`COLUNAS_DO_APP`) tem a
  mesma lista do `NEXUS_COLUNAS["ranking"]` do App, na ordem dele. A régua do mês (piso, teto, anulação, teto das
  rondas, mínimos, bônus) vem nas oito últimas colunas, e o "Como o App calcula" da tela usa esses números. Coluna nova
  só no FIM, dos dois lados.
- **Tela:** o mês (o corrente e o anterior) e a região que o App escreve; o pódio (os três primeiros), os números, a
  classificação e o "Fora do ciclo". Com uma região escolhida, a posição continua a do mês inteiro ("3º lugar no
  mês"): é a que o técnico vê no App. Desde 18/10/2026 (Levi: "a classificação é mensal, estamos no mês de outubro") a
  tela fala do mês ("Classificação de outubro de 2026", o filtro "Mês"; o App chama o mês de ciclo); o "Fora do ciclo"
  fica com o nome do App e a explicação no mouse, montada da régua que ele publicou ("O que significa fora do ciclo?
  quero que apareça a explicação ao passar o mouse nesse nome"); e o pódio é o das olimpíadas ("1°, 2° e 3° lugar quero
  estilo podium das olimpíadas"): o 1º no meio e no degrau mais alto, o 2º à esquerda, o 3º à direita, em ouro, prata e
  bronze (`--ouro`, `--prata`, `--bronze`); a página segue 1º, 2º e 3º para quem lê a tela.
- **As OS que não pontuaram cheio (18/10/2026)** (Levi: "Quando tiver OSs devolvidas ou anuladas quero que dê para
  clicar na linha e mostre qual foi a OS e o motivo!"): a linha da pessoa com devolvida, abaixo do piso ou anulada abre a
  lista do mês, com a OS, a tarefa, a situação, a nota, os pontos, o motivo e quando foi registrada. Abre na
  classificação **e no "Fora do ciclo"** (19/10/2026: no 1º livro, 12 dos 17 técnicos de outubro com lista estavam fora,
  e a linha deles não abria). A OS vai em verde e abre o card do OS Creator pelo número (`NexusOsCard.abrirFolio`; Levi,
  18/10/2026: "ao citar uma OS tem que ficar verde grid e deve ser possível clicar e ver o card da OS"). Quem lista é o
  **App**, no livro `ranking_tarefas_app_campo · Tarefas` (fato `ranking_tarefas` no catálogo; no banco desde a v287,
  19/10/2026, e o número de linhas por situação bate com as colunas do placar): pelo banco não fecha (a sessão do App,
  18/10/2026: o extrato do App não vai ao banco e a anulação depende da ordem por pontos; em outubro, 17 devolvidas nos
  fechamentos contra 43 no placar). O motivo é o do App: o texto da devolução pelo painel (a feita direto no Fracttal,
  quase todas hoje, vem "Devolvida no Fracttal: o motivo não passou pelo App."), o porquê da nota, ou "anulada por N
  tarefa(s) abaixo do piso no mês"; o "Registrado em" chega em UTC e a tela mostra em Brasília. Sem o livro, a linha diz
  que a lista ainda não chegou do App. A regra do "fora do
  ciclo" no mouse é a que a sessão do App confirmou: menos tarefas registradas que o mínimo (contam todas, inclusive as
  devolvidas e as de 0 ponto; ronda não), ou, tendo o mínimo, cumprimento abaixo do mínimo (só os dias já vencidos; sem
  nada programado, 0%). Régua em `sombra` no App = aviso de que o técnico ainda vê a pontuação de antes.
  Sem o livro, a tela diz que o ranking ainda não chegou.
- **A quantidade em cima e o "!" do título (29/10/2026).** Levi estranhou "280 rondas" e "2.000 tarefas" no mês:
  eram os pontos em cima.
  - **Tarefas e Rondas:** em cima vem quantas (tarefas registradas, rondas); embaixo, os pontos ("2.736 pts · 70
    contam", "280 pts · no teto"). Pedido dele: "acho bom botar primeiro a quantidade real e abaixo vir os pontos".
  - **O "!" ao lado do título** (`como_ler()`, `.rk-info`) explica cada coluna com a régua do mês, uma métrica por
    linha, com um fio entre elas ("separe os tópicos em linhas"). Fechado ao abrir a tela, abre por cima e fecha no
    clique fora e no Esc. O "Como o App calcula" do pé da tela foi para dentro dele.
  - **As contas citadas são as do App:**
    - tarefa = `max(0, nota - 60)` com nota no piso e GPS;
    - pontualidade = início até o programado + 30 min (`PONTUAL_GRACE_MIN`), uma marca por OS por dia, só nas OS da
      programação; a OS sem horário na programação conta como fora do horário (o `bool(None)` do App) e não soma
      ponto.
    Mudou lá, muda o texto aqui.
  - **Em aberto:** tirar da pontualidade a OS sem horário programado, que é decisão do Levi (medir antes).
- **O lado do App é o pacote** `C:\GridcoBuild\app-campo-docs\_propostas\ranking-pontos-nexus\` (`LEIA.md`,
  `aplicar.py --conferir`, o `.diff` contra a v262 que casa também na v263, e o teste do App). Enquanto o App não
  publicar com ele, o livro não existe e a tela diz isso; nada aqui depende da ordem.
- **Prova:** `tests/test_campo_ranking_pontos.py` (18 desde 29/10/2026; 7 mutações pegas na 1ª versão, uma delas a
  coluna com nome errado, e 2 em 29/10: os pontos de volta em cima e o "!" fora do título). No navegador, com o
  banco falso dos testes: escuro, claro, região e 390 px. A prévia de 29/10 usou os números reais de outubro do
  livro.

## Ocorrências com plano de ação (18/10/2026)

Levi: "Próximas peças: o mapa das usinas e as ocorrências com plano de ação. siga!". A origem é o painel próprio de um
supervisor (a ocorrência, o histórico e o plano de ação, em quadro e lista); o objetivo é largar o painel próprio e usar
só o Nexus. Desenho e as decisões dele no quiz: `docs/superpowers/specs/2026-10-18-ocorrencias-plano-de-acao-design.md`.

- **O Nexus é a fonte, no banco:** `nexus_ocorrencias · fato_evento_ocorrencia` (`nexus/campo/ocorrencias.py`), um
  evento por linha (`criou`, `dados`, `acao`, `andamento`), só acrescenta; o estado sai dos eventos (`estado`: vale a
  última decisão da ocorrência e de cada ação; o andamento, o mais novo em cima). O título, a descrição, o chamado, o
  texto da ação, o andamento e quem fez vão só cifrados (o Cofre); em claro, IDs, códigos e datas (regra 8).
- **Quem grava:** o Responsável O&M (o login de pessoa, em qualquer usina, como a observação: quem cobre as férias de
  outro registra nas usinas dele) e o administrador, sempre com um login de pessoa (a senha de administrador vê o aviso
  "entre com o seu login": o histórico guarda quem fez). Os outros só veem (sem botões; o POST é 403). A permissão sai
  do cadastro de AGORA a cada pedido; na sessão fica só o `pessoa_id` (o nome guardado por 12 h travava quem pegou uma
  leitura vazia do cadastro). Sem as chaves de gravar no .env (`faltam_chaves`), nenhum formulário, e a tela diz qual
  falta. A tela é dos **Responsáveis UFV sem marcar** em Base → Acessos (`Tela.do_setor`, como o Gerar e o Quadro do
  PCM); os outros setores, pela marca.
- **Página velha e clique duplo** (revisão final de 18/10/2026): o formulário de editar leva a `versao` (o id do último
  evento da ocorrência ou da ação) e a gravação recusa se ela mudou ("mudou depois que você abriu a página": a página
  velha reabria a ocorrência que outro finalizou). O de criar leva o id do que vai nascer (`novo_id`, `nova_acao_id`,
  `evento_id`): o 2º envio acha o id no livro e não grava de novo (o livro é para sempre). O botão se desliga no envio.
- **Os ids** têm a letra do que são (`o` ocorrência, `a` ação, `e` evento) e 11 hexadecimais: a API infere o tipo da
  coluna, e um id só de algarismos voltaria como número. A cifra é amarrada à linha inteira (ocorrência, evento, ação,
  id). O estado aplica o `criou` primeiro e o resto pela hora com milissegundos: o PC e o servidor gravam o mesmo livro,
  e o evento da máquina de relógio atrasado não some.
- **A tela** (`nexus/torres/campo/ocorrencias_tela.py`, `templates/campo/ocorrencias.html`, `ocorrencia.html`,
  `ocorrencia_nova.html`, `static/ocorrencias.css`): a lista abre nas abertas, na ordem do prazo da próxima ação em
  aberto (sem prazo depois, a mais crítica primeiro; as finalizadas no fim); o quadro tem uma coluna por status (as 20
  finalizadas mais novas; o resto pela lista). Filtros: usina, Responsável O&M (o logado abre nas usinas dele; "Todos"
  vai como `*`), status e criticidade. A página da ocorrência tem os dados (editar), o plano de ação (cada ação com o
  responsável escolhido na lista do cadastro, o prazo e a situação; a vencida em vermelho) e o andamento.
- **As recusas dizem o porquê e guardam o que foi digitado** (título vazio ou comprido, data inválida ou antes de
  01/01/2024, início ou fim depois de hoje, fim antes do início, fim sem o status Finalizado, OS com letra ou com
  algarismo de outra escrita, código do ativo fora do formato do Fracttal ou de outra usina, responsável fora da lista,
  prazo vazio ou além de 3 anos, "Nada mudou"). O prazo da ação é obrigatório (o desenho: "cada ação com responsável,
  prazo e situação"). Finalizada sem o fim termina hoje; a ação esquecida aberta na finalizada não fica "atrasada". A
  ocorrência de usina que saiu da operação continua editável (só não muda PARA usina fora da operação), e a ação de
  quem saiu da lista do cadastro fecha sem trocar a pessoa. Gravar volta pela página (303, `?ok=`), para o F5 não
  gravar de novo; a falha que não é recusa vai ao log da máquina (503).
- **O ativo** é o código do Fracttal (opcional, canônico) e vai em claro: só letras, números e hífen (`COD_RE`; um
  nome, um telefone ou uma fórmula da planilha não passam) e só desta usina: o que está na dimensão de equipamento
  (que não seja de outra usina) ou o que leva o código da usina (a regra do `equipamento.valido`). Liga ao
  `equipamento_id` só quando está na dimensão (não liga = vazio; `equipamento_ligado_por`).
- **Na Visão geral**, a etiqueta "N ocorrências" no nome da usina (as abertas: status diferente de finalizado), na cor da
  criticidade mais alta delas (`COR_ETIQUETA`: muito alta vermelha, alta amarela, média e baixa neutras), leva à tela
  filtrada pela usina (para quem abre a tela Ocorrências; para o setor sem ela, a etiqueta sem link). O livro que não
  abre deixa a Visão geral sem as etiquetas, nunca quebrada, e a leitura que falhou espera 1 minuto antes de tentar de
  novo (a Visão geral não fica esperando o banco lento a cada carga). Depois de gravar, a cópia de 1 minuto já tem o
  que foi gravado; a página que não acha a ocorrência relê o livro antes do 404 (gravada noutro processo). **A Visão
  geral não espera a releitura** (19/10/2026, `ocorrencias.ler_sem_esperar`): a cópia vencida volta na hora e o livro
  é relido por trás, uma releitura por vez (só a 1ª vez depois de subir lê no pedido). A tela Ocorrências segue no
  `ler` (espera a cópia nova).
- **Fora, por agora:** as anotações privadas, exportar para .xlsx, o comunicado por IA e a importação do painel antigo.
- **Prova:** `tests/test_campo_ocorrencias.py` (o estado, a ordem, o catálogo, gravar e ler no banco falso com o texto
  cifrado, as recusas, a releitura que falha não grava, a tela inteira, a etiqueta da Visão geral e, da revisão final,
  a página velha, o clique duplo, a usina que saiu da operação, o código do ativo, o relógio de duas máquinas e o banco
  que devolve tudo como texto).

## Zeladoria (26/10/2026)

Levi, com o modelo "Rondas Sujidade e Vegetação" (um HTML de visão do cliente): "Quero algo nesses padrões para a parte
de zeladoria da seção campo app do nexus. deixe no estilo do Nexus porém nesse padrão! a evolução por usina deve ser por
cliente!". A tela de antes (os serviços de terceiros que o App registra, `zeladoria_app_campo`) estava vazia desde
05/10 e ficou no fim, recolhida. A conta é `nexus/campo/zeladoria.py`; a rota, `zeladoria` e `zeladoria_usina` (a
gaveta) em `__init__.py`.

- **Sem fonte nova.** A leitura de vegetação e de sujidade é a das Rondas, pela regra da aba Sujidade e vegetação
  (`zeladoria.leituras`, a mesma de `visao.sujidade_vegetacao`): o texto da OS de ronda no Fracttal
  (`ronda_checklist.respostas`), o checklist do fato (a carga das rondas sem OS, a avulsa), e a validação por foto do dia
  no lugar das rondas daquele dia. A zeladoria feita e a programada são as tarefas do tipo Zeladoria do `nexus_os ·
  fato_tarefa_os` (as abertas e as finalizadas de 90 dias, as mesmas da Visão do responsável). Nada escreve.
- **As três tarefas de zeladoria são conhecidas pelo texto** (`TAREFAS_DE_ZELADORIA`): o fato guarda a tarefa como
  `tarefa_chave` (sha1 do texto normalizado, `fatos.tarefa_chave`), e as chaves das três do plano foram achadas pelos
  textos do `banco_dados.json` do PCM: "Acompanhamento - Limpeza de Módulos (Termografia se aplicável)" (atende a
  sujidade), "Acompanhamento - Supressão Vegetal" e "Acompanhamento - Poda Química" (atendem a vegetação). Medido em
  26/10/2026: 76 tarefas de zeladoria no fato, 36 de limpeza, 33 de supressão e 7 de poda, uma linha por OS; 18 usinas
  com limpeza feita em 90 dias, 26 com supressão, 3 com poda. **O PCM renomear a tarefa no Fracttal muda a chave**: a
  tarefa cai em "Outra tarefa de zeladoria" e não atende recomendação nenhuma até o texto novo entrar na lista.
- **Semana** = segunda a domingo (`2026-W43`, a do PCM). A evolução mostra as 8 semanas (as do modelo) que terminam na
  semana escolhida; o filtro oferece a corrente e as 4 anteriores (`SEMANAS_NO_FILTRO`, a janela que o checklist de 90
  dias ainda cobre). A semana corrente fica "em andamento" (célula vazia com contorno, não o tracejado de "sem leitura").
  **Semana com mais de uma leitura** (`REGRA_DA_SEMANA`): a última, como a aba Sujidade e vegetação e a Visão do
  responsável (medido em 26/10: 206 usina×semana com 2 ou mais leituras em 9 semanas; a última abaixo da maior em 27 na
  sujidade e 28 na vegetação). **Decisão do Levi (26/10/2026): a última** (a outra opção era a pior da semana).
- **A evolução por cliente** (`por_cliente`): os clientes em ordem alfabética, recolhíveis (o nome, ou "Recolher os
  clientes"); a linha do cliente diz, em cada semana, quantas usinas ficaram acima de 3 sobre quantas tiveram leitura.
  Dentro do cliente, o nível mais alto na ÚLTIMA leitura primeiro (pela semana escolhida, na segunda-feira a ordem virava
  a alfabética). Vegetação ou Sujidade no seletor (`modulo=`). Cor da célula = a régua da aba Sujidade e vegetação em tom
  de fundo (1 e 2 verde, 3 azul, 4 âmbar, 5 vermelho); a dica da célula traz as leituras da semana.
- **Situação por usina:** a última leitura até o fim da semana escolhida (na corrente, até hoje), com a seta para a
  anterior; leitura com 7 dias ou mais (a régua de ronda pendente, `DIAS_SEM_RONDA_ALERTA`) com a data em âmbar. A ordem
  é a criticidade das Rondas (`visao.criticidade`). Colunas: usina (cliente · UF), leitura, vegetação, sujidade, vala,
  sensores, última supressão (supressão ou poda), última limpeza e a recomendação.
- **Recomendação** (`recomendacoes`): vegetação acima de 3 na última leitura pede supressão vegetal; sujidade acima de 3,
  limpeza de módulos. A situação no Fracttal: "feita" (tarefa do tipo terminada DEPOIS da leitura, inclusive a OS em
  verificação; a feita antes não conta), "aberta" (programada ou em execução; a programada vencida diz "atrasada") ou
  "sem_os". **Sem as OS no banco** (o fato vazio ou a leitura que falhou), "sem_dado" e o aviso: a tela não acusa falta
  de OS que ela não viu. O prazo conta da leitura (`PRAZO_DIAS`: nível 5 imediato, nível 4 em até 7 dias, os do modelo;
  **decisão do Levi, 26/10/2026**; as outras opções eram sem prazo ou 7 e 14 dias); vencido sem a feita = "atrasada
  N d". A fila das Recomendações traz as não feitas, o nível 5 primeiro, sem OS antes de aberta, a leitura mais antiga
  antes.
- **Os números de cima** (sobre cliente, usina, região de campo e gestor; a situação não, é o que eles contam): com
  leitura na semana, vegetação acima de 3, vegetação média, sujidade acima de 3, sujidade média e recomendações sem OS;
  os de contagem filtram a tabela (`situacao=`). O modelo tinha altura média em cm e perda estimada em %: o App não mede
  nenhum dos dois (o nível é de 1 a 5 pela foto de referência), e a tela mostra a média dos níveis no lugar.
- **A gaveta** (o clique na linha, na célula ou na recomendação; `/zeladoria/usina/<id>`, carregada no clique): os seis
  fatos, as 8 semanas nos dois campos, a recomendação, as leituras da semana clicada (sem a célula, a semana da última
  leitura), a zeladoria do Fracttal da usina e o botão das fotos da última ronda com OS (o `ronda_fotos` das Rondas: o
  Fracttal só é lido no clique). Sessão vencida recarrega a página (o portão leva ao Entrar), como a gaveta da Engenharia.
- **Filtros:** semana, cliente, usina, situação, região de campo e gestor de contrato (o supervisor entra filtrado, como
  nas Rondas). **Decisão do Levi (26/10/2026)**, como o limiar acima de 3 (o modelo dizia "nível ≥ 3": seriam 57
  usinas na vegetação e 46 na sujidade, 103 recomendações, contra 30, 21 e 51); a semana padrão é a corrente.
- **Medido na bancada em 26/10/2026** (o banco real e as respostas como a produção as tinha, sem ir ao Fracttal): 131
  usinas mobilizadas de 13 clientes, 21 com leitura na W44 (segunda-feira) e 69 na W43; vegetação acima de 3 em 30
  usinas (6 no nível 5), sujidade em 21 (5 no nível 5); 51 recomendações, 40 sem OS, 10 com OS aberta, 1 feita. Página:
  481 KB (40 KB com gzip), 0,07 s com a conta das Rondas pronta; a gaveta, 4,5 KB em 0,02 s.
- **No banco, para o dashboard do cliente** (26/10/2026, Levi: "agora faz a mesma tela no dashboard do cliente"; a
  decisão dele, pelo chat do Dashboard Thopen: o Nexus publica a visão pronta e o 5080 só mostra, agrupando pela
  carteira): `zeladoria_banco.py` grava `nexus_zeladoria · zeladoria_semana` (1 linha = usina × semana com leitura, 12
  semanas, a recomendação e a situação da zeladoria em palavras do cliente, sem nome) e `atualizacao`, de hora em hora,
  só no servidor (o PC sobe com `NEXUS_CAMPO_AQUECER=0` e não relê o checklist) e só com o checklist inteiro e novo. O
  contrato e as recusas estão no `nexus/dados/CLAUDE.md` (linha "Zeladoria para o dashboard do cliente"). **No ar:**
  1ª gravação em 27/10/2026 às 08:48 (687 linhas, os totais iguais aos da tela) e a aba Zeladoria do 5080 lendo desde
  09:02 (PerformancePainel `e648dc1`, conferida pelo chat do Dashboard Thopen com os mesmos números). Das 131 usinas,
  80 têm a linha "BD_Thopen · Dados Gerais Usinas" no de-para (a que o 5080 usa para o nome): só a Ouro Branco, das 81
  da Thopen, não tem.
- **Prova:** `tests/test_campo_zeladoria_semanal.py` (as semanas, as leituras pela regra da aba com a validação por foto,
  a última × a pior, as três tarefas e as situações, a feita antes × depois da leitura, a aberta, o "sem_dado", a conta
  da tela com a semana passada, a evolução por cliente e a ordem, a situação, os números, a fila, a tela e a gaveta com o
  banco falso; mutações 5/5).

## As explicações das telas (05/11/2026)

Em todas as telas da torre (Usinas 360°), "De onde vem", "Como ler", "Entenda esta tela" e afins moram no "!" amarelo ao lado do
título (`explica` de `nexus/templates/_explica.html`, o padrão do Nexus): Aprovação de OS, Central de atenção, PT, a
decisão da PT, Ranking, Triagem, Zeladoria, Responsáveis e Rondas. Fica fora dele o que muda com o dado (a nota do
Ranking com as linhas sem nome, os avisos de dado faltando, as usinas sem mobilização da Central de atenção). A
legenda do semáforo dos cartões (`cr-rk-leg`) e a das cores da Zeladoria (`zl-legenda`) ficam junto do que colorem.

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
- **Os serviços de terceiros do App estão vazios de verdade:** em 90 dias o App não registrou nenhuma etapa de zeladoria (`zeladoria_app_campo`). Desde 26/10/2026 eles ficam no fim da tela Zeladoria, recolhidos, com o aviso.

## As contas nossas (`nexus/campo/visao.py`)

As constantes ficam no topo do arquivo; cada função diz a regra no docstring.
- **A cópia dos livros** (`_livro`, 2 min) e o **`carregar(pares)`** (17/10/2026): põe na cópia, com UMA listagem do
  banco e as leituras em paralelo, os livros pedidos que faltam. Cada `livros.ler` pede de novo a lista de todas as
  tabelas (~0,6 s): a tela que lê vários livros chama o `carregar` antes (Técnicos por usina do PCM: 11,6 s → 3,3 s).
  **Desde 19/10/2026 as páginas também vão juntas:** a listagem diz quantas linhas cada aba tem, e as páginas de todas
  as abas pedidas saem no mesmo grupo de 6 (o `dim_equipamento`, 23 páginas, era lido uma depois da outra). A aba que
  cresceu depois da listagem segue página a página até a incompleta; a que encolheu para na 1ª incompleta; `(livro,
  None)` é a 1ª aba do livro. A mesma listagem enche o `_ciclo` das abas de cada livro (`_abas_dos_fatos`). Conferido
  no banco real: 20 abas, 48 mil linhas, iguais linha a linha à leitura de sempre. Prova:
  `tests/test_campo_pre_leitura_19_10.py`.
- **Rondas** (05/10, no estilo do painel de rondas que o Levi mostrou; refeita em 08/10; **enxuta em 03/11/2026**: Levi,
  "tem filtro em cima e filtro na tabela, tá uma bagunça", "Menos é mais!"): sete indicadores dos últimos 30 dias, juntos
  numa faixa (`cn-numeros`, "no padrão de tudo junto"), e duas abas, **Registros** e **Trackers**. **O período é fixo em
  30 dias** (`DIAS_RONDAS`; "Tire os filtros de dias, até pq carrega só de 300 em 300"; o `dias=` de link antigo não muda
  nada) e a tabela vem **de 300 em 300** (`pag=`, `LIMITE_LINHAS`). Saíram o Painel, a Sujidade e vegetação e o Quem
  ronda; o endereço de cada aba que saiu cai nos Registros (`aba=sem` e `aba=cobertura` caem no filtro Sem ronda). As
  contas deles seguem no `visao` (`comparativos`, `sujidade_vegetacao`, `_por_cluster`), que outras telas usam.
  - **A barra de uma linha, no modelo do Histórico do OS Creator Web** ("deixe escondido no padrão OS Creator Web >
    Histórico"): o **Buscar por usina** (a lista `rd-usinas` com TODAS as usinas da tela, sem os filtros, no estilo do
    Nexus e não a do navegador, que veio "mal formatada": o nome e, embaixo, o cliente e a UF; abre no foco, filtra
    enquanto se digita sem acento nem caixa, setas e Enter escolhem, Esc fecha; escolher leva à página da usina; sem o
    script, `/rondas/buscar-usina?nome=` acha pelo nome igual, sem acento nem caixa, ou pelo único que contém, senão
    volta com `q=`), a busca da tabela (`q`), o botão **Filtros** com a contagem e, na ponta, Exportar
    CSV e + Ronda avulsa. O painel dos Filtros (Mostrar, Região do Brasil, Cliente, Usina, Responsável O&M, Equipe,
    Região de campo, Gestor de contrato; `FILTROS_DO_PAINEL`) só vale no Aplicar; fechar (×, Esc, clique fora) descarta;
    Limpar volta cada lista ao "todos"; o endereço leva só o escolhido; no celular o painel sobe de baixo. Cada filtro
    aplicado vira uma **etiqueta com o ×** (`rd-etiqueta`), que tira só aquele, na hora; a região de campo e o gestor que
    vêm do login saem com o `*`. A duração, a pendência, o indicador e a busca também viram etiqueta.
  - **O "como ler" e de onde vem o dado** moram na exclamação amarela ao lado do título (o `aviso` de
    `hseq/_legenda.html`, o mesmo dos Extintores; a página carrega o `hseq.css`).
  - **Os testes de página olham a tabela** (`<section class="cn-painel">`): a lista do Buscar por usina leva o nome de
    todas as usinas, e "a usina X não aparece" na página inteira sempre falharia.
  - **Registros** (a tabela "Rondas diárias"; 08/10: "tira as colunas região, início e fim", "bote a coluna duração ao
    lado de data"): Data, Duração, Técnico, Usina, Equipe, Tipo, Qualidade, Veredito, Pendências, Trackers, OS, Fotos.
    O mouse (ou o foco do teclado) na duração mostra "Iniciou às 07:00 · terminou às 08:00 (Brasília)" numa dica fixa
    na tela (a rolagem da tabela cortaria uma dica presa à célula). O CSV continua com início, fim, estado e região.
    De 300 em 300; Exportar CSV com BOM para o Excel. **A linha abre a barra lateral da ronda** (03/11/2026: "Tira esse
    botão 'Fotos' ao clicar na linha já abre uma barra lateral mostrando tudo da ronda, a barra pode representar 1/3 do
    tamanho da tela. Ficará do lado direito! Não irá mais abrir abaixo da linha"): `_ronda_gaveta.html`, 1/3 da tela à
    direita (a tela inteira abaixo de 900 px), sem véu (a tabela segue clicável; a linha aberta fica marcada), Esc ou ×
    fecha. Ela busca o pedaço `_ronda_detalhe.html` (rota `rondas_detalhe`, `/rondas/usina/<id>/ronda?os=&data=&ini=`: a
    ronda pela OS e, sem OS, pelo dia e pela hora do início, no `historico_usina`): quem fez, quando (início e fim em
    Brasília, duração), nota, veredito, OS, trackers, o checklist, as pendências e as fotos, que vêm depois pela rota das
    fotos da OS (o 429 do Fracttal tenta sozinho em 1 minuto). **Enxuta no mesmo dia** ("Checklist pode ficar mais
    simples. Sujidade, Vegetação, Vala de Drenagem, Sensores. Tente aproveitar melhor o espaço e focar nas imagens";
    "aproveite mais o espaço para ter mais espaço vertical e melhor aproveitamento horizontal"): sem a faixa de cima (o ×
    no canto), os dados em grade de três colunas (rótulo em cima, valor embaixo), o checklist numa linha de quatro,
    centralizado ("centralize as colunas cabeçalho e valores"; rótulo e valor nas linhas de uma subgrid, para o "Vala de
    drenagem" que quebra em duas linhas não desalinhar o valor dele dos outros) e as
    fotos com o resto do espaço (miniaturas de ~130 px que enchem a largura, só na barra: a grade das outras telas não
    muda); o "Ver o histórico da usina" saiu ("deixe completo"). **A OS da barra abre o card da OS** ("quero que a OS
    seja clicável"): o do OS Creator, pelo número (`NexusOsCard.abrirFolio`, o clone acha o id), como na Visão do
    responsável e no Ranking; o `card_os_abrir.html` entra no fim do `_ronda_gaveta.html`, DEPOIS do script da barra,
    para o Esc com o card aberto fechar só o card. "A OS não tem fotos anexadas" com a ronda completa no App não é o
    técnico: conferir no Fracttal se a tarefa da OS está Não iniciada e com o resumo vazio, que é o fechamento da OS da
    ronda que não rodou no servidor do App (OS 18407, 03/11/2026: a OS nasceu da fila e a leitura seguinte foi adiada
    pela reserva da cota da v317; as fotos ficaram no servidor do App). A
    coluna Fotos e a linha que abria embaixo saíram dos Registros e do histórico da usina; a caixa que amplia a foto
    (`_ronda_fotos_caixa.html`) segue, com o botão, na Zeladoria, no EPI e nos Extintores. **A duração e a pendência se escolhem no cabeçalho** (03/11/2026:
    "ao clicar em 'Duração' no cabeçalho, aí vai ter essas opções ou 'ordenar'"): o menu da Duração ordena (mais longa
    ou mais curta primeiro, pelo `th._ordenar` do `_ordenar.html`, o `<th data-ordem-menu>`) e filtra (toda, abaixo de
    10 min, acima de 2 h); o da Pendências filtra (toda ronda, sem OS no Fracttal, evidência incompleta, com a conta). A
    caixa do menu fica presa à tela (a rolagem da tabela a cortaria).
  - Cobertura = usinas mobilizadas com ronda no período ÷ mobilizadas; a seta compara com o período anterior de
    mesmo tamanho. Duração = fim − início carimbados pelo aparelho (0 a 8 h; fora disso, sem duração; o livro não
    traz a pausa). **Veredito = o `_veredito_ronda` do App, na mesma ordem, com os limites dele** (`LIMIARES_PADRAO`:
    60/85/95 e 10 min); o GPS só aparece como a falha "sem GPS". "Ronda longa pendente" é pendência para o App
    (vira Atenção). Medido em 08/10, 30 dias: 527 rondas, cobertura 83% (106 de 128), qualidade 96%, duração média
    47 min; 7 dias: 149 rondas, 66% (84 de 128).
  - **Os sete indicadores filtram a tabela** (Levi, 05/10): Rondas finalizadas = as de hoje (`ind=hoje`); Cobertura =
    o filtro Sem ronda (`cob=sem`); **Nunca tiveram ronda** = `cob=nunca`; Qualidade = abaixo do limite
    (`ind=qualidade`); Duração = da mais longa para a mais curta (`ind=duracao`); Abaixo de 10 min = `dur=curta`; Usina
    mais atrasada = as há 7 dias ou mais (`cob=atrasadas`). O cartão ativo fica marcado; clicar de novo, ou no
    × do filtro, tira.
  - **Nunca tiveram ronda** (08/10: "em KPIs coloque mais um, quantas usinas nunca tiveram ronda";
    `visao._registro_da_cobertura`): usina mobilizada sem nenhuma ronda em TODO o registro do Nexus, não só no período:
    o livro de rondas do App, as avulsas e a carga `nexus_rondas_checklist`. O `title` do cartão diz desde quando vai o
    registro (a data mais antiga das três). Medido em 08/10: registro desde 11/08/2026; 19 de 128 mobilizadas nunca
    tiveram ronda (igual à conta antiga "999 dias": a carga só tem rondas que o livro também tem).
  - **Sem ronda** (08/10: "troque por uma tabela chamada 'Sem ronda' que mostrará usina, equipe, técnicos, supervisor e
    última OS feita na usina (para conseguir rastrear a última vez que o técnico foi lá)"; **desde 03/11/2026 um filtro
    dos Registros**, o "Mostrar" do painel, `cob=`: "Sem ronda some e vira um filtro de registros"): as mobilizadas sem ronda no
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
  - **Painel** (08/10) **saiu em 03/11/2026** (Levi: "Tire o painel, ele não serve"). A conta (`visao.comparativos`,
    Índice das rondas = 60% da nota das rondas + 40% cobertura) segue no visao, provada em
    `test_painel_compara_regiao_equipe_cliente_regiao_de_campo_e_gestor`.
  - **Ronda sem OS, o motivo em português** (`visao.motivo_sem_os`; Levi, 05/10: "não entendi essa observação, minha
    conta fracttal já está conectada"): o App cria a OS de ronda com a conta Fracttal do TÉCNICO; "Conecte sua conta
    Fracttal" é a mensagem do App para o técnico. Medido em 05/10: 114 de 771 rondas (90 dias) sem OS por isso (os
    cinco técnicos com mais somavam 74). O App tenta 5 vezes, uma por
    minuto, e desiste (`RONDA_OS_FILA_MAX`, `_MAX_H` 24 h): a ronda antiga não ganha OS quando o técnico conecta depois.
  - **Usina, Responsável O&M e equipe** (Levi, 13/10/2026: "deve dar para filtrar cliente, usina, responsável
    e equipe!"; desde 03/11/2026 no painel dos Filtros): três listas ao lado da de cliente (`usina=` pelo id do cadastro; `responsavel=` é o Responsável O&M da
    ficha da usina, o mesmo da Central, com "Sem responsável O&M" e `*` = todos; `equipe=` virou lista, no lugar do
    filtro que só vinha do clique no Painel). Filtram as rondas E a base da cobertura (os sete indicadores e as seis
    abas, inclusive a Sem ronda e o CSV). A lista de usinas encolhe com os outros filtros (as mobilizadas e as que
    tiveram ronda que passam por eles; a escolhida fica sempre). Prova: `tests/test_campo_rondas_filtros_1310.py` (três
    mutações pegas).
  - **Filtro por cliente** (Levi, 05/10: "a cobertura das rondas das UFVs do cliente. Essas usinas tem que bater com
    as mesmas do registro mestre!"): o cliente vem de `usinas.cliente_id` → `clientes.nome` do `cadastro_nexus`
    (`_Base.nome_cliente`), nunca do nome da usina no livro. Filtra as rondas E a base da cobertura; com cliente
    escolhido aparece a faixa "cobertura das rondas: N%, X de Y usinas mobilizadas do cliente no cadastro". Medido em
    05/10: as 128 mobilizadas têm cliente; Thopen 61 de 80 (76%) em 30 dias.
  - **Quem ronda por cluster** (05/10 e 08/10) **saiu em 03/11/2026** (Levi: "Pode tirar quem ronda também! Menos é
    mais!"). A conta (`visao._por_cluster`, os pendentes de cada técnico pela regra da Central) segue no visao, provada
    em `test_quem_ronda_mostra_quais_sao_as_pendentes_e_abre_em_blocos`.
  - **Histórico da usina** (`/rondas/usina/<usina_id>`, `visao.historico_usina`; desde 03/11/2026 também pelo Buscar
    por usina). **03/11/2026:** a evolução vem dos **últimos 30 dias** (o filtro de mês da 1ª rodada saiu no mesmo dia:
    "Quando clica na usina deixa os últimas 30 dias, melhor que por mês"; sem leitura no período, diz isso; uma leitura
    só fica no meio), os números ficam juntos numa faixa, o "De onde vem" (do fim da página e do canto) virou a
    exclamação amarela ao lado do nome ("conforme segurança > extintores"), e a linha da ronda abre a barra lateral,
    como nos Registros; a tabela segue com os 90 dias. Levi, 05/10: "quando clicarmos no
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
    pela descrição que o App escreve ("Sujidade dos módulos — 4", "Altura da vegetação — 5"); as demais vêm **abertas,
    por tipo** (sensores, vala, infraestrutura, pragas/dejeto/trincado, zonas, capa), cada tipo com o título no nível
    de Sujidade e Vegetação e o nome curto do item embaixo da miniatura. Eram um "Demais fotos da ronda" recolhido (06/10:
    "deixe recolhido, quando expandir quero que mostre por tipo"); desde 05/11/2026, abertas ("Ao clicar na ronda tire
    esse 'demais fotos' quero tudo expandido"). A etiqueta da resposta ("limpo") mora na própria foto (`cn-foto-img`) e a
    legenda fica embaixo: presa a 24 px do fim do cartão, ela caía em cima da legenda quando a barra lateral esticava o
    cartão para quadrado ("O texto não está encaixando onde deveria encaixar, conserte!"); na barra, a foto é que fica
    quadrada e o cartão cresce com a legenda (`tests/test_campo_ronda_fotos_0511.py`). A 1ª
    foto o App descreve como a capa da ronda. Miniatura de 240 px pelo Pillow (medido em 06/10: 7 a 14 kB contra 182 a
    690 kB a foto inteira), feitas em paralelo assim que a grade é pedida; a mesma foto pedida duas vezes baixa uma vez
    (a chave de "em andamento" leva a cache: com a mesma chave a miniatura esperava por si mesma 60 s). Clicar amplia,
    com setas dentro do grupo e Esc. OS sem anexo existe (15055: as fotos não subiram); ronda sem OS: fotos só no App.
    **Ampliar rápido (13/10/2026, Levi: "pré carrega bem pequeno porém na hora de ver expandido demora muito"):** a
    memória guardava só 40 fotos inteiras e a ronda tem 45 a 50; o `preparar` baixava todas para as miniaturas e, na
    última, as primeiras (sujidade, vegetação) já tinham saído: ampliar ia ao Fracttal (S3) a cada clique. Agora a
    ampliada é a **versão de tela** (`tela`: lado maior 1.600 px, JPEG progressivo; a inteira com `?original=1`), feita
    pelo `preparar` logo depois das miniaturas; as três (inteira, tela, miniatura) ficam **em disco**
    (`dados/cache_fotos_ronda`, pelo arquivo do Fracttal sem a assinatura do link: sobrevive ao reinício de cada deploy;
    passou de 6.000 arquivos, saem os mais antigos; nos testes, só a memória: app com `TESTING` não liga o disco, e o
    `test_campo_instalar` dubla o `configurar`, senão as fotos falsas iam para a `dados/` de verdade do PC) e o endereço
    leva a versão do arquivo (`?v=`), que o navegador guarda 7 dias. A caixa pede a anterior e a próxima, e a ampliada da
    miniatura em que o mouse passa.
    **Fracttal recusou (429):** o pedaço vem com `data-erro` e o botão "Tentar de novo"; a linha não fica "carregada"
    (fechar e abrir busca de novo) e, aberta, tenta sozinha em 1 minuto (Levi: "atualmente só fica nessa mensagem até
    não sei quando").
  - **As rondas feitas saíram da Central de atenção** (Levi, 05/10: "na parte de atenção quero só o que for pendente"):
    na aba Registros, o filtro de pendência (Sem OS no Fracttal, Evidência incompleta) e a coluna Pendências.
  - **Sujidade e vegetação** (Levi, 05/10: "é importante!"; `nexus/campo/ronda_checklist.py`; **a aba saiu em
    03/11/2026**: "também é redundante pois os registros já mostram"; a leitura segue no histórico da usina, na Zeladoria
    e na Visão do responsável): o livro de rondas não
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
- **A PT da APR do dia** (App v246; para todos desde a v256, 10/10/2026): uma APR e uma PT por técnico, OS e dia; o
  App manda no livro de PT a tarefa "APR do dia AAAA-MM-DD" e o ativo vazio (29 das 315 PT em 11/10). O `visao.pts`
  completa com as tarefas da OS no Fracttal (`nexus/campo/apr_dia.py`): as feitas no dia da APR (iniciadas ou finalizadas
  nele), sem nenhuma as abertas no dia, sem nenhuma todas; o equipamento sai do colchete do nome da tarefa ("[Cabine 2] -
  ..."; no "[Grid Co.] - MPM - X", o X). Fonte: o `gestao_pcm.json` da Gestão PCM (`pcm/fonte.ler_gestao`, o mesmo cache),
  porque 25 das 29 OS eram do fim de semana, fora da programação. A linha mostra a 1ª tarefa (+ quantas mais), os
  equipamentos e "APR do dia dd/mm" embaixo; o detalhe lista as tarefas com o estado. OS que ainda não chegou ao arquivo
  fica como o App mandou, com o dia marcado. Levi, 11/10: "aparece como 'APR do dia'? sendo que está ligado a atividade de
  um ativo no fractal".
- **"Esperando o De acordo" é a MESMA tela da Central > Permissões de trabalho** (Levi, 05/10): as duas incluem
  `templates/campo/_pt_esperando.html` (desde 24/10/2026 as duas só pedem os cartões por responsável e a tabela; a da
  APR e PT leva a coluna Responsável no lugar da região, `coluna_responsavel`; tabela com a OS em verde,
  Equipamento, Espera no fim e a linha que abre o detalhe). Mudou uma, mudou a outra (o teste compara os cartões das
  duas).
- **Tela de PT** (Levi, 05/10; desde 24/10/2026 a regra está em `nexus/torres/hseq/CLAUDE.md`, "APR e PT"): abas
  "Esperando o De acordo" (cartões por responsável ou tabela) e "Histórico" (todas as decididas, de 20 em 20, por
  situação; só tabela). Filtros de cliente, usina e Responsável UFV com a conta de cada opção, nas duas abas; o cartão
  leva à tabela do responsável. Na tabela: só o número da OS, em verde Grid, no lugar do número da PT (abre a aprovação); Equipamento no
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
  - **A tarefa da PT (13/10/2026, PT-15067-1310-1106, "não achei a tarefa desta PT na OS do Fracttal"):** o REST de
    work_orders traz o nome da tarefa em `description` ("[Grid Co.] - MPM - QGBT"); o `tasks_description` vem VAZIO, e
    por ele nenhuma PT de OS com mais de uma tarefa achava a sua. A preventiva tem uma tarefa por ativo com a mesma
    descrição (a OS 15067: 21 tarefas, QGBT 1, 2 e 3 iguais, só o 3 finalizado, o da PT; a PT diz só "QGBT", sem
    código). `pt_fracttal.tarefas_candidatas`: o código do ativo (quando a linha da PT tem), a única da OS, ou as de
    mesma descrição com a finalizada primeiro (depois a em andamento); a assinatura vem da 1ª candidata que a tiver (no
    máximo 4 pedidos com o login de quem olha, `assinatura_das_candidatas`).
- **A assinatura da APR feita no App** (26/10/2026, Levi: "Como tem a mensagem 'o Fracttal não entregou a APR desta
  tarefa'? sendo que a APR nem mais via fractall é, é via app de campo"): a APR do App não fica no formulário de
  Compliance do Fracttal, então o caminho do formulário dizia "não entregou". Agora a rota da assinatura tenta primeiro
  o PDF que o App anexa na OS (o mesmo do Baixar APR, `pt_fracttal.apr_pdf`) e tira dele a imagem PNG da página da
  "Assinatura" (`assinatura_do_pdf`, com o `pypdf`; a foto da equipe é JPEG), pela credencial da empresa, sem pedir o
  login de quem olha; a legenda diz "(App)". Só sem esse PDF (a APR de antes da v251) vale o formulário, com o login.
  Guardada 1 h em memória, nunca em disco nem no banco. Medido em 26/10 nas OS 16982 e 16866: o PDF tem 3 páginas e
  duas imagens (a foto, 900 × 1200 JPEG, e a assinatura, ~660 × 240 PNG RGBA).
- **Central de atenção, só o que está pendente** (as rondas feitas foram para a tela Rondas em 05/10; o texto abaixo descreve a origem) (Levi, 05/10: "separar Rondas feitas (histórico de rondas) e rondas
  pendentes, dando bastante atenção nas pendentes"; "separe o que é ronda e o que é Permissão de Trabalho"):
  - **Rondas pendentes** (abre nela, com números grandes que filtram): uma linha por usina mobilizada que pede ronda:
    nunca teve, sem ronda há 7 dias ou mais, ou ronda longa pendente pela última ronda (o App repete o aviso em toda
    ronda curta). Colunas: Há, Status, Usina, Equipe, Estado, Região, Observação. Medido em 05/10: 86 (21 nunca, 45 há 7 d ou
    mais, 20 longa pendente).
  - **Rondas feitas:** o histórico do período, com "Feito por" (só aqui aparece quem fez), Status (Sem OS no
    Fracttal, Evidência incompleta, Sem pendência), Observação, OS e nota. Medido: 232 em 14 dias (178, 39 e 15).
  - **Permissões de trabalho:** as PT esperando, Técnico e a OS em verde, que abre a aprovação. Medido: 22 (21 paradas).
  - **Só Por responsável e a tabela, nas duas abas** (Levi, 19/10/2026: "tire essa visão por região, e gestor de
    contrato. Uma visão só por responsável serve! tanto em Rondas pendentes quanto permissão de trabalho ... A tabela
    mantém"). Saíram os cartões por equipe, por região de campo e por gestor de contrato (seguem em HSEQ › APR e PT, que
    usa o mesmo `_pt_esperando.html` com os modos dela); os endereços de antes (`modo=equipes`, `regioes`, `gestores`,
    `supervisores`) abrem Por responsável (`_modo_central`). O responsável é o **Responsável UFV**, o Responsável O&M da
    ficha da usina (`usinas.responsavel_om_id`; confirmado pelo Levi em 12/10: "é o Responsável O&M mesmo"), não o
    gestor de contrato. **Os cartões por responsável são limpos** (Levi, 03/11/2026: "quero mais minimalista... já tem um
    vermelho na lateral e a barra também fica vermelha... dói é os olhos!"; `cn-equipe--min`, nas duas abas e na APR
    e PT): sem a borda colorida, sem o vermelho na barra e sem o número colorido; a cor fica num ponto pequeno ao lado
    da palavra ("48% feitas", "7 paradas"; a cor nunca sozinha), e a barra, neutra, mostra só o que foi feito.
    Prova: `tests/test_campo_central_cartoes_limpos_0311.py`. **Rondas pendentes:** um cartão por responsável (`visao.por_responsavel`: as usinas dele,
    pendentes por status, feitas = as não pendentes, o %), e o responsável escolhido (no cartão ou no filtro) abre o
    **kanban** (`visao.kanban`, `COLUNAS_KANBAN`): Nunca teve ronda | Ronda pendente (com o motivo e quem fez a última) |
    Ronda feita (a usina em dia). Cada usina do kanban diz a **equipe** com o rótulo ("pode ser uma ou mais": a do
    cadastro e as dos técnicos que a tela Técnicos por usina do PCM põe nela, `visao.equipes_das_usinas`, na conta
    guardada da Central; medido em 19/10: as 131 usinas com equipe no cadastro, 125 com técnico, nenhuma com duas). O
    cartão da usina leva ao histórico de rondas dela. **Permissões de trabalho:** um cartão por responsável com as PT
    esperando nas usinas dele (`visao.pt_por_responsavel`: quantas, quantas paradas há mais de 2 h, as usinas e as
    equipes; a soma bate com as 24 PT de 19/10); o cartão leva à tabela das PT dele. "Sem responsável O&M" tem cartão
    próprio, por último.
  - **Os filtros** (Levi, 19/10/2026: "tire o filtro de região do brasil, região de campo, gestor de contrato e
    responsável O&M. Deixe responsável UFV, cliente, UFV, equipe e o canto para escrever", nas duas abas): Responsável
    UFV, Cliente, UFV e Equipe (`FILTROS_CENTRAL`) e a busca, em cascata como em Extintores (cada lista com o que existe
    com os outros filtros, `_opcoes_central`), sem padrão pelo login (o Supervisor de Campo abria na região dele); `*`
    no responsável vale como todos. O cliente entrou nas linhas de ronda da Central (`visao.atencao`). Prova:
    `tests/test_campo_central_responsavel.py`.
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

## Visão do responsável (12/10/2026)

Levi: "Precisamos criar uma visão que os supervisores irão usar, uma visão que ele olha as usinas, as metas, os
problemas, onde ele deve focar, no que ele deve deixar. No caso seria separado por responsável". Depois do 1º desenho:
"aposte em um formato reduzido que quando eu expanda aparece mais informações / Separe a visão em dois blocos (...)
Seria interessante também incluir os extintores", aprovado no protótipo com "só tira a parte de Tempo do COS". E: "O
nexus é um ambiente centralizado e precisamos ter os dados se conversando!". `/t/campo/responsaveis`, a 1ª tela do
Campo. Conta em `nexus/campo/responsaveis.py`.

- **A 1ª abertura depois de cada deploy e a pré-leitura** (Levi, 19/10/2026: "as vezes abre rápido e as vezes é um
  parto para abrir"): a conta fica pronta na memória (`visao._ler`, 5 min, renovada por trás) e a tela abre em 0,01 s,
  também depois de 1, 2 e 5 min parada (medido). A demora era só a conta fria: o servidor reinicia a cada push no Nexus
  (12 a 22 vezes por dia útil na semana de 12/10; 38 no dia 18/10), a memória zera, e a pré-carga só passa 5 min depois
  de subir (a cota do Fracttal, `auth/pre_carga.py`). Quem abria antes disso esperava a conta inteira: 26 s com a
  Central, as Rondas e as PT já prontas e 46 s sem elas, no banco real, com as abas lidas uma a uma (23 a 27 listagens
  do banco, ~0,5 s cada) e as páginas uma depois da outra. Agora a conta começa pela **pré-leitura**
  (`responsaveis.pre_leitura` → `visao.carregar`): as 20 abas das fontes numa listagem só, com as páginas em paralelo;
  a programação do PCM aproveita a mesma listagem. Medido duas vezes, cada par na mesma hora e no mesmo banco:
  **44,6 s → 15,2 s** e **38,1 s → 18,5 s** (o banco lento, na carga das 11:10), com a conta igual (131 usinas). Falhou a pré-leitura, cada fonte lê a sua, como antes. **Fonte nova que lê um livro pelo
  `_livro` entra na `pre_leitura`** (o `test_a_pre_leitura_cobre_as_fontes` cobra). O resto da espera fria é o banco
  (as 62 páginas, 8 a 12 s com ele lento) e a Manutenção (a programação do fim para trás e os motivos do PCM, ~5 s).
  **O filtro também não espera o banco** (Levi, 19/10/2026: "quando eu já filtrei o responsável e vou filtrar o cliente
  carrega de novo ... e acaba demorando"): cada filtro é um pedido novo e a conta vem da memória, mas o pedido relia as
  duas cópias curtas quando venciam (quem olhava a tela mais de um minuto antes de filtrar): as ocorrências abertas
  (1 min) e o de-para dos sites do Fracttal (2 min). Medido no banco real, trocando o cliente: depois de 1 min parado
  0,97 s → 0,02 s, depois de 2 min 1,47 s → 0,04 s, sem nenhuma leitura no pedido (o site agora vem na conta; as
  ocorrências voltam na hora e se releem por trás). Prova: `tests/test_campo_filtro_responsavel_19_10.py`.
- **O Nexus travado de 19/10/2026 e as três travas contra a avalanche** (Levi: "o nexus travou foi tudo não carrega
  nada"; das 14:47 às 14:55 até o /saude estourava 40 s, e o Raio-X das 15:06 mostrou duas Visões do responsável frias
  calculando juntas, presas lendo o banco, e o Desempenho esperando a listagem dele). O banco mora no mesmo servidor
  (app.gridco.com.br; a máquina com carga 3,8 de 4 núcleos), e tudo que o Nexus pede a ele junto vira fila:
  1. **A decisão de PT e a ronda avulsa zeravam TODAS as contas do Campo** (`visao.limpar()`, desde 05/10 e 08/10):
     cada tela voltava do zero na visita seguinte, todas juntas. Agora sai só o que mudou (`visao.esquecer_pt`,
     `esquecer_ronda`): a decisão relê só a conta das PT e os livros dela (a decisão do Nexus aparece na página pelo
     `decisao_pt.da_pt`, e o livro do App só muda quando o App a processa); a avulsa refaz as Rondas na hora (quem
     lançou se vê) e deixa a Central e a Visão do responsável com a cópia, refeitas por trás (`_VENCIDAS`).
  2. **Uma conta fria por tela** (`visao._fria`): quem chega enquanto ela roda (outra pessoa, quem recarregou a página,
     a renovação por trás) espera a mesma, até `ESPERA_S` (60 s; depois, a tela diz que a conta está sendo feita). As
     contas guardadas não se pedem em círculo (a Visão usa a Central, as PT e as Rondas; a Central usa as PT).
  3. **Teto de páginas do banco no processo inteiro** (`VAGAS_BANCO` = 6, no `carregar`): antes eram 6 por conta.
  Medido no banco real, três aberturas frias da Visão ao mesmo tempo: o que estava no ar fazia 3 contas, 238 pedidos ao
  banco (até 18 juntos) e levava 52 s; agora 1 conta, 80 pedidos (no máximo 6 juntos), 18 s. Prova:
  `tests/test_campo_sem_avalanche_19_10.py`.
- **Três blocos, uma lista** (desde 18/10/2026 na Visão geral, que tirou Onde focar; seção própria abaixo):
  **Performance** (meta, PR, disponibilidade; os ativos falhando como etiqueta no nome), **Manutenção** (seção própria
  abaixo) e **Acompanhamento** (rondas, limpeza, PT, chamados, extintores). Acima, a faixa **Parada agora**. Cada usina
  é uma linha compacta com os valores coloridos pela régua; clicar abre o detalhe dos três blocos (`<details>`, sem
  script), com os títulos no centro e sem os links das telas donas no fim (Levi, 18/10/2026: "Esses links no final com
  palavras em verde grid pode tirar, a ideia é resolver a maior parte por essa tela"): o que se resolve dali abre por
  cima, na janela de fundo desfocado (o dia a dia, os ativos, a PT, o card da OS, o card da ronda). Cada bloco tem a própria triagem (focar = crítico ou PT parada; acompanhar = só
  atenção; em dia) e **todas as usinas viram linha, inclusive as em dia** (Levi, 13/10/2026: "Tem que aparecer todas as
  usinas do responsável inclusive as que estão em dia"). **A ordem de cada bloco** (o clique no nome do bloco ordena por
  ela; "Ordene da pior meta para a melhor em performance e em acompanhamento ordene pelas rondas"): a Performance pela
  meta do mês, da pior para a melhor, sem meta no fim (`ordem_da_meta`); a Manutenção pelo nível e pelas atrasadas
  (`ordem_da_manutencao`); o Acompanhamento pela ronda, a pior em cima (`ordem_da_ronda`: nunca teve; sem ronda há 7
  dias ou mais, mais dias primeiro; longa pendente; em dia, a mais antiga primeiro; sem dado). As réguas de cada alerta
  ficam no "!" amarelo ao lado do título (o `explica` de `_explica.html`, desde 05/11/2026; de 18/10 a 05/11 ficavam
  atrás de um "!" abaixo da tabela), fechado ao abrir a tela, com a hora da leitura (a caixa "Gerencial, Confiabilidade
  (...) lido às" do canto do cabeçalho saiu no mesmo dia; Levi: "pode ficar nos disclaimers"); o que muda com o dado
  (usinas sem de-para, livro que não chegou) segue numa nota no pé.
- **Nenhum indicador refeito com régua nova.** Cada número vem da tela dona, pela MESMA fonte que o Nexus já usa, e cada
  alerta usa a régua de lá (`REGUAS`, mostradas na nota da tela, por bloco).
  - Meta do mês: `nexus_performance · fato_meta_usina_mes`, o `_gerencial_payload` da plataforma publicado pelo worker
    do servidor (`plataforma/gerencial_publicar.py`). < 90% crítico, < 97% atenção (o `atgTag` da Visão gerencial); PR
    abaixo do previsto, atenção. **O número anômalo** (Levi, 18/10/2026: "apenas sinalize que o número está anômalo e o
    dado pode estar errado, temos que sinalizar pela plataforma e não ficar travando a construção!"): a plataforma marca
    a coluna `anomalia` do fato com códigos de `dominios.ANOMALIA_META` (`meta_baixa`, `meta_alta`: a régua única que o
    Levi escolheu na plataforma, a meta do mês fora de 2 a 8 kWh por kWp por dia; `geracao_impossivel`: dia tirado da
    conta pelo filtro de geração acima da potência × 12 h, o da Ibirapuã II); a Visão mantém o número e a cor e põe
    "anômalo" ao lado, com a frase na dica e no detalhe. Código desconhecido aparece como "número anômalo (a plataforma sinalizou)", nunca some.
    Caso que criou: Santo Anastácio e Álvares Machado com 217% e 331% em 10/2026 (a meta de outubro baixa no BD_Thopen). Usina com duas linhas no Gerencial (Santarém 1 e 2): produção e meta somam,
    atingimento refeito sobre a soma, PR pesado pela meta.
  - Disponibilidade: `falhas_performance · disponibilidade_dia`; o mês é a média dos dias fechados (a régua de lá é
    `12 h × dias`); duas usinas do Gerencial na mesma do cadastro, pesadas pela potência. < 80% crítico, < 99% atenção.
    Provado em 12/10: 129 de 130 usinas iguais à tela da plataforma.
  - Ativos: os `sinais` da Engenharia › Confiabilidade (`engenharia._dados()`), o nível de lá; "monitorar" não alerta.
  - Rondas e PT: `visao.atencao(14)` e `visao.pts()`. **PT parada de HOJE = "agora"** (topo do foco: técnico parado no
    campo); parada de dias anteriores = crítico "sem decisão desde DD/MM" (33 de 34 eram de 1 a 6 dias atrás em 12/10).
  - **Chamados: `nexus_chamados · fato_chamado`** (abaixo), o mesmo dado do quadro Acompanhamento de chamados: em aberto
    com o fabricante = atenção; o nome do equipamento pela dimensão de equipamento. **Até 12/10 vinham da planilha de
    tickets** (mais de 1.000 "abertos", sem fim desde junho, contra 18 do quadro): o Levi pediu a troca.
  - Extintores: a conta do HSEQ (`nexus/hseq/extintores.py`): vencido = crítico; vence em 30 dias ou sem conferência há
    mais de 30 dias = atenção (a "sem conferência" só alerta se nada venceu nem vai vencer: o mesmo extintor não alerta
    duas vezes).
  - **O Tempo do COS saiu** no protótipo aprovado (12/10): a régua continua na tela do COS.
- **A usina do nome** (`Nomes`, para a meta e a disponibilidade): o de-para publicado dos sistemas de nome, depois o nome
  do cadastro, por fim o Fracttal ou o código. Nome sem acento, sem caixa, romano vira número. Nome de duas usinas não
  liga. Medido em 12/10 com o Gerencial: 139 de 161 ligam; as 22 que sobram não estão mobilizadas.
- **Cartões por responsável** (o padrão de quem não é responsável): os dois blocos, cada um com a triagem e os números
  do grupo (meta, abaixo da meta, disponibilidade; rondas, PT paradas, chamados, extintores vencidos). Responsável O&M
  = `usinas.responsavel_om_id`, o mesmo da Central.
- **O responsável que entra pelo Fracttal vai direto para o Painel dele** (Levi, 12/10/2026: "caso a pessoa que logue
  seja algum desses responsáveis não vai aparecer por responsável, já vai direto para Onde Focar!"; Onde focar virou a
  Visão geral em 18/10/2026, e o Painel passou a ser a tela inicial em 28/10/2026): `_responsavel_do_login`
  (guardado em `session["responsavel_padrao"]`) marca o filtro nele, a aba "Por responsável" some e o `modo=cartoes` do
  endereço não vale para ele (o Ranking das equipes, desde 18/10/2026, ele vê, com as equipes dele); o filtro continua (para olhar as usinas de quem ele estiver cobrindo; "Todos" mostra as
  de todos, ainda na Visão geral). Quem não é responsável (admin, coordenador) segue com os cartões; o clique no cartão
  de um responsável abre o Painel dele.
- **Esperando o De acordo é só PT** (Levi, 12/10: "na verdade esperando de acordo é só PT então mostra só PT"): o rótulo
  é "PT".
- **As janelas por cima da tela** (Levi, 12/10/2026: "precisamos mostrar para o supervisor de onde está vindo!"; "ao
  clicar aparece um card sobrepondo a tela dando um blur de fundo"). O valor da Performance (Meta, PR, Disp.) e o "dia a
  dia" do detalhe abrem um `<dialog>` (fundo `--veu` com `backdrop-filter: blur`), com o pedaço de página da rota
  `/t/campo/responsaveis/usina/<usina_id>/<meta|pr|disp>` (`responsaveis_painel`, template `_resp_painel.html`, sem a
  moldura; o script da tela busca e põe no `<dialog>`). **Nunca um 500 cru** (13/10/2026: no servidor recém-subido, no
  9ec8fe3, toda janela da Meta dava "HTTP 500" e a mesma versão abria no PC com o mesmo banco; sem o texto do erro não
  havia como achar a diferença): o que quebra ao montar vira, dentro da janela, "Não consegui montar esta janela" com o
  tipo e o texto do erro, e o traceback vai ao log (`nexus.campo`); a leitura que falha diz também o texto do erro.
  - **Meta**: a tabela do dia a dia (geração da meta, geração real, diferença, % do dia) e o total = a soma dos dias
    contra a meta dos mesmos dias (a conta do Gerencial). Fonte: `nexus_performance · fato_desempenho_usina_dia`. As
    linhas são os dias que o **Gerencial** conta no atingimento, com a geração dele (`ger_dia` do `_gerencial_payload` da
    plataforma, 13/10/2026), e a meta do dia exata dele (a do mês ÷ os dias do mês): fecha nas 135 usinas com série
    (produção, dias e %, provado com o Gerencial de outubro). Até 13/10 a geração vinha do PR diário e não fechava em 78
    de 131 (a Thopen pula o dia com POA até 0,3: Indaiatuba 5 dias e 87% contra 12 dias e 66%; o BD_Performance escreve
    0 no dia em branco: Castelo do Piauí 31 dias e 54,9% contra 9 e 189,1%). O dia só do PR diário (geração vazia) não
    entra na tabela. A janela só mostra o mês corrente (no mês fechado o Gerencial cobra o mês inteiro). E o porquê de
    cada dia (Levi, 13/10/2026: "na tabelinha da meta por dia você adicione o POA DEF e a disponibilidade!"): o POA do
    dia (o da série; vazio quando o sensor não leu) e a disponibilidade do dia fechado (`disp_diaria`, o mapa da janela
    da Disponibilidade; vazia até o dia fechar ou na usina fora do Gerencial › Disponibilidade), na régua 99/80 dela. No
    total, o POA é a soma dos dias da tabela e a disponibilidade é a do mês (o mesmo número da coluna Disp.).
  - **PR**: "essa mesma visão do PAINEL NOC > HISTÓRICO > PR > PR DIÁRIO EXPANDIDO PORÉM UMA MELHORIA": as barras da
    geração com a linha do POA (eixo da direita) e as metas tracejadas e, embaixo, a curva do PR com a meta. SVG montado no
    servidor (`nexus/campo/responsaveis_graficos.py`, sem biblioteca, como o resto do Nexus); a barra pela meta do dia
    (97/90, a régua do Gerencial); dia sem valor quebra a linha; a dica de cada dia no `<title>` da coluna. A barra é a
    geração do Gerencial; o POA e o PR, os do PR diário (o dia com POA até 0,3 fica com barra e sem PR).
  - **Disponibilidade**: o mapa diário da usina (a legenda do Gerencial › Disponibilidade: 100% sem evento, 99–100,
    95–99, 80–95, 50–80, abaixo de 50) e as OS que formaram o valor (`falhas_performance · disponibilidade_os`, publicada
    com o diário): OS, tipo, o que parou, início, fim, duração (do início ao fim), horas de sol (as que contam, da OS no
    mês: as mesmas em cada usina dela) e perda. **A perda é a da OS NESTA usina** (a régua do Gerencial: kWp afetado ×
    horas de sol, sem a irradiação), e o total da janela é a perda da usina no Gerencial. **Desde 15/10/2026 a
    disponibilidade é só do Fracttal, isolada da geração** (Levi: "a geração não deve afetar a disponibilidade"): a OS
    aberta conta, e a nota da janela diz isso; até ali a geração "desmentia" dias e a OS podia ficar com 0. Até 13/10/2026
    a plataforma repartia a perda da OS de duas usinas pela potência (setembro: 47.893 kWh na usina errada entre
    Rodrigues 1 e 2).
  - **PT**: a OS da PT no detalhe abre a PT por cima para aprovar sem sair da tela (Levi: "não tirar a pessoa da tela pois
    ela vai ter que voltar para ver mais usinas"): `/t/campo/responsaveis/pt/<numero>?ativo=&volta=`
    (`responsaveis_pt`, `_resp_pt.html`), a mesma linha e a mesma decisão da tela da PT, assinada com o login do
    Fracttal; o `volta` (só /t/campo/) traz de volta à Visão com os filtros. A página do Nexus não abre em iframe
    (`base.html` sai do iframe): por isso o pedaço de página, e o script da tela busca a assinatura e quem assina. É o
    mesmo card que o Levi pediu de novo em 18/10/2026 ("Em PT, quando tiver, quero a mesma solução do card com blur para
    a pessoa conseguir assinar a PT alí mesmo!"): De acordo e Não autorizo, com o login do Fracttal.
  - **Ronda e Limpeza** (Levi, 18/10/2026: "Deixe a informação da última ronda apenas em limpeza pois está redundante";
    "ao clicar na última ronda aparece um card sobreposto sobre a tela com um blur de fundo mostrando como foi a última
    ronda, fotos, data, quem fez"): a data da ronda aparece uma vez só. Se a leitura da Limpeza é da última ronda, a
    data fica na Limpeza ("ronda de 07/10"); se a última ronda veio sem a limpeza, fica na Ronda ("última ronda em
    15/10"). A data abre o card da ronda: `/t/campo/responsaveis/usina/<id>/ronda?os=&data=` (`_resp_ronda`,
    `_resp_ronda.html`), a ronda do histórico da usina (o mesmo do Rondas › usina) pela OS ou, sem OS, pelo dia: data e
    hora, quem fez, tipo, qualidade, sujidade, vegetação, vala, sensores, pendências e as fotos da OS no Fracttal (o
    pedaço `ronda_fotos_os`, pedido pela janela só quando ela abre; a miniatura amplia dentro do card, porque a caixa de
    foto das Rondas ficaria por baixo da janela). Na cópia de prova as fotos não vêm (a trava recusa o pedido de token do
    Fracttal) e o card mostra o "Tentar de novo" de sempre.
  - **Ativos falhando** (Levi, 13/10/2026: "Para esses ativos falhando da engenharia, conseguimos criar uma visão?"):
    a etiqueta "N ativo(s) crítico(s)/em atenção" da linha e o "ver os ativos" do detalhe abrem a janela `ativos`
    (`ativos_da_usina`): os sinais da Engenharia › Confiabilidade da usina em crítico e atenção (os mesmos do detalhe,
    na régua de lá; os em monitorar só contados), a **linha do tempo das OS dos 30 dias** (ativo × dia: a OS de falha
    cheia, a de serviço vazada, o número quando há mais de uma no dia) e, de cada ativo, o que a gaveta de lá mostra: o
    porquê, falhas em 30 e 7 dias, o P90 da família, MTBF, MTTR, a disponibilidade do ativo e as últimas OS (link do
    Fracttal). Lê o que a Confiabilidade já leu (`engenharia._dados()`), sem ler o Fracttal de novo e sem mexer no cache
    de lá; a data da OS vem sem o ano ("13/10 09:30": `_dia_da_os` põe o ano de hoje, ou o anterior se cair no futuro).
  - **Observação do responsável** (Levi, 13/10/2026: "um campo para Observação do Responsável ... ficará salvo o dia e
    hora, só os responsáveis podem comentar, incluindo responsáveis de outras usinas ... para caso de férias! ... salvo
    em algum canto do Nexus para posteriormente poder juntar esse comentário para relatórios"): embaixo da tabela da
    Meta, a lista (a mais nova em cima: quem, dia e hora; "cobrindo" quando quem escreveu não era o responsável da
    usina) e o campo para escrever. Grava em `nexus_observacoes · fato_observacao_responsavel`
    (`nexus/campo/observacao_responsavel.py`, o mesmo caminho da ronda avulsa): no BANCO, para o PC e o servidor
    gravarem e lerem o mesmo livro; o texto e o nome só cifrados (o Cofre da chave do cadastro), a pessoa por
    `pessoa_id` + `pessoa_hmac`, `do_responsavel` sim/não. **Quem escreve:** quem entrou pelo Fracttal e é Responsável
    O&M de alguma usina, em qualquer usina; o administrador pela senha não escreve. A gravação devolve a janela da
    Meta de novo (o script da tela envia sem sair da janela; recusa volta com o motivo e o texto digitado); pedido de
    outro site é 403 (a régua da moldura). Para relatório: `para_relatorio(de, ate)` decifra no Nexus. O livro nasce na
    1ª observação de um responsável (registrado no catálogo antes). Nada se edita nem se apaga.
  - Sem o dado no banco (a série ou as OS antes da 1ª publicação; a usina sem aba no BD), a janela diz por quê.
- **Isolamento** (regra 13): cada fonte em `_ler_fonte`; a que falha volta vazia e a tela diz qual. Sem o livro da meta
  ou o dos chamados (antes da 1ª publicação), a tela avisa e não cobra por eles.
- Custo: cópia de 5 min por `visao._ler`, refeita em segundo plano. Fria, medida no banco real em 18/10/2026 (PC, com
  as fontes novas da Manutenção e da Limpeza): ~24 s antes de ler a programação do fim; as partes: cadastro 3,2 s,
  Central 4,0 s, Rondas (a Limpeza) 4,6 s, chamados 4,7 s, a programação inteira 4,4 s (agora 1,3 s, do fim), a conta da
  Manutenção 3,1 s. NÃO entra no aquecimento do `manter_quente` (a conta chama a Confiabilidade, que pede a releitura das
  OS de falha ao Fracttal, e o PC sobe com `NEXUS_CAMPO_AQUECER=0`).
- Prova: `tests/test_campo_responsaveis.py` e `tests/test_campo_manutencao.py`. Protótipo e ensaio com o banco real:
  `create_app()` + `app_context()`, `os_falhas.pedir_releitura` desligado e `responsaveis.visao_responsaveis()` (fora do
  repositório: o resultado tem nome de responsável). A tela inteira sem senha no navegador: o `test_client` com
  `session_transaction` (`logado` e `admin`), a trava da cópia de prova (`subir_copia_de_prova.instalar_trava`: nada
  que não seja GET sai) e o HTML salvo com o `static` ao lado, servido por `python -m http.server` (18/10/2026).

### O Painel do responsável (28/10/2026)

Levi: "com base no que já temos no acompanhamento do responsável quero uma tela feita mesmo para o responsável que não
seja um tabelão. Então eu escolheria o responsável, vai ter o nome do responsável como [título] e mostrará: Usinas abaixo
da performance, chamados abertos, PTs pendentes, Ranking das equipes do maior para menor, acompanhamento de rondas! (...)
uma tela inicial claro, se for para se aprofundar aí é outro nível". A aba **Painel** (`modo=painel`), a conta em
`nexus/campo/painel_responsavel.py` (pura) e o bloco `{% if modo == 'painel' %}` do `responsaveis.html`.
**O link do e-mail semanal da Segurança** abre aqui (03/11/2026, Levi: "tem que ser o nexus > campo app > painel (filtrado
no responsável)"): `/t/campo/responsaveis?r=<número da pessoa>&modo=painel`. O `r` vira o responsável pelo
`responsaveis_por_pessoa` da visão (o livro do e-mail fica na API compartilhada e não leva o nome); o número de quem não
é responsável não filtra nada. Prova: `test_o_link_do_email_da_seguranca_abre_o_painel_pelo_numero_da_pessoa`.

- **A tela inicial de um responsável:** é o padrão quando há um escolhido (pelo login do Fracttal, pelo cartão do
  responsável ou pelo filtro); sem escolha, quem não é responsável segue nos cartões e o responsável logado com "Todos"
  na Visão geral, como antes. O `modo=painel` com "Todos" mostra o painel de todas as usinas. O título é o nome do
  responsável, com as usinas, os clientes e as equipes embaixo.
- **Nenhum número novo, nenhuma régua nova:** cada quadro reorganiza o que a Visão já calcula por usina (`montar`) e o
  Ranking (`ranking_equipes.cartoes`, sobre as mesmas usinas). A meta é a régua da Visão gerencial (97/90), a ronda a
  da Central (7 dias), a cor da cobertura a das Rondas (80/50, o `cor_pct` do Painel delas) e a nota a do App (85/70).
- **O desenho (4ª rodada, 29/10/2026):** cinco quadros com a **mesma altura** ("Padronize o tamanho do card para todas
  as modalidades": `--pn-card` fixo, o número guarda o lugar de duas linhas e a lista encolhe e rola se faltar lugar) e
  as **PT num número à esquerda da faixa "Parada agora"** ("PTs pendentes pode ficar como um KPI que quando o
  supervisor clicasse ele veria quais são as PTs, não precisa ser algo aberto toda hora"; e "faça caber ao lado esquerdo
  de parado agora"; ao ver o 1º botão, "que botão escroto é esse? melhore o design": o ícone num quadrado com a cor
  da situação, o rótulo, o número e a seta). O botão `data-pn-pts` (no `.pn-topo`, com a faixa) abre a lista
  `#pn-pts-lista` na janela, e a PT dela abre a decisão ali mesmo. O espaço que as PT deixaram foi para a
  **Performance, com duas colunas de largura** ("Aproveita o espaço para dar um destaque nas usinas abaixo da
  performance"): 1ª linha, a Performance e os Chamados; 2ª, o Ranking, as Rondas e os Extintores. Os números ficaram
  diretos: "N chamados em aberto", "N equipes", "N extintores vencidos e M a vencer"; saíram a barra das Rondas e o
  aviso do Ranking ("os supervisores não são crianças!"). A **página do Painel é 20% menor** ("reduza a fonte de toda a página em 20%": o
  `zoom:.8` nos filhos de `.pn-pagina`, o cabeçalho, as abas, os filtros, a faixa e os quadros na mesma proporção;
  as janelas por cima ficam no tamanho de sempre).
- **Cada quadro com o total e a lista inteira:**
  - Usinas abaixo da performance: todas as usinas, da pior meta para a melhor, sem meta no fim; em colunas, a meta do
    mês (a barra e o número), o PR contra o previsto e a disponibilidade, com a cor que a Visão já dá na linha da usina
    (`linha_performance`, nenhuma régua nova); depois da disponibilidade, a **última sujidade e vegetação** (Levi,
    29/10/2026: "em performance mostre última sujidade e vegetação de todas as usinas. Pode aparecer depois de
    disponibilidade": a leitura que a Visão já tem, `responsaveis.limpeza`, a conta das Rondas em 90 dias, na régua
    delas, `visao.criticidade`: o 5 crítico, o 4 atenção; a data da leitura na dica). Os números do topo numa linha só, cada um com o rótulo ("tem um espaço
    grande, dá para fazer o texto caber melhor na parte de performance"): abaixo de 97%, abaixo de 90%, a meta do
    grupo, na meta e sem meta publicada.
  - Chamados abertos **por usina** (2ª rodada, Levi: "pode só botar o nome da UFV uma vez e dizer qual os ativos daquela
    UFV"): a usina do chamado mais antigo primeiro, o nome dela preso no alto enquanto os ativos rolam; cada ativo sem a
    marca ("Não precisa mostrar a marca do ativo": `responsaveis.nome_do_ativo`, medido nos 184 ativos dos chamados
    abertos: "Inversor 1.7", "Estrutura de Trackers", "Usina inteira") com o **status do chamado** ("Seria bom mostrar
    o status do chamado": o da tela de Garantias, no fato desde 28/10/2026, ver `nexus/dados/fato_chamado.py`; a troca
    feita na tela depois da última publicação vale por cima, lida de `os_creator · chamados_obs`) e os dias. Concluído
    não entra ("As concluídas não mostra"); os em verificação só na contagem.
  - PTs pendentes (no número à esquerda da faixa "Parada agora"; a lista na janela): todas; a parada de hoje primeiro, depois as paradas de
    outros dias, depois as que esperam há menos de 2 h. O número diz só "PTs esperando o De acordo" (2ª rodada: "pode
    enxugar o texto").
  - Ranking das Equipes - <mês> (2ª rodada: "sempre o mês vigente"; a conta passou ao mês, ver "O Ranking das
    equipes"): todas as equipes das usinas, **pela posição** do ranking de todas (3ª rodada: "O ranking também tem que
    ordenar por posição aqui o 4° lugar está acima do 2°, não faz sentido!": a nota da tela é arredondada, e no empate
    de 98 a 98 o nome punha a 4ª em cima; agora decide o desempate do ranking); as usinas sem equipe no fim.
  - Acompanhamento de rondas: todas as usinas na ordem que o Levi pediu (29/10/2026: "priorize a que nunca teve
    ronda, depois sem ronda a 7 dias ou mais, depois longa pendente depois as em dia"; é a `ordem_da_ronda`, conferida
    nos 8 responsáveis), a sem ronda com mais dias primeiro, as em dia no fim (a barra colorida saiu em
    29/10/2026: "Tire essa barra colorida de acompanhamento de rondas"). O número é o das usinas **sem ronda há 7 dias ou mais, somadas as que nunca tiveram**
    ronda pelo App (2ª rodada: "o número do KPI deve falar quantas usinas estão sem ronda a 7 dias ou mais"; decisão
    dele: "Somar as que nunca tiveram"); embaixo, no formato dos números da Performance ("gostei, faça algo
    parecido com a parte de rondas"), as que nunca tiveram ronda, as em dia e as longas pendentes, numa linha.
  - Extintores vencidos (o 6º, Levi no mesmo dia: "quero que mostre também as usinas com extintores vencidos daquele
    supervisor"): só as usinas com vencido, a com mais vencidos primeiro, o pior extintor e os a vencer na linha (a
    conta do HSEQ que a Visão já lê). A linha abre a janela da usina `painel=extintores` (vencidos, a vencer, sem
    conferência). Na janela (3ª rodada): a **última ronda de extintores** ao lado do nome da usina ("acrescentado
    última ronda de extintores da UFV ao lado do nome": a conferência mais recente dos extintores dela, a "última
    conferência" do HSEQ) e o **relatório da usina em PDF e em Excel, o mesmo do Segurança · HSEQ** ("que nem acontece
    na parte de segurança": os links levam a `/t/hseq/extintores/relatorio.pdf|.xlsx?usina=&cliente=`, com o nome e o
    cliente como a Segurança os escreve, guardados em `responsaveis.extintores` como `rel_usina`/`rel_cliente`; o setor
    Supervisão Campo abre as telas da Segurança, conferido nos Acessos em 28/10). Os botões ficam no alto da janela.
- **Nada fica de fora, 6 por vez** (Levi, ao ver a 1ª versão com 5 linhas e "e mais N": "poderia ter um scroll para o
  que não cabe no card, scroll alá Nexus (...) Tem que ter todas as usinas e equipes daquele supervisor, não podemos
  deixar nada de fora"; e, ao ver o quadro com a metade da tela: "Ficou mt grande! Limite de 6 em 6 com um scroll"): a
  lista mostra 6 linhas (`--pn-linha`, altura fixa) e rola por dentro, na barra de rolagem do Nexus; a faixa "Parada
  agora" também mostra todas no Painel (nas outras visões, as 6 mais antigas). Conferido na bancada com o banco real
  (28/10): nos 8 responsáveis, a Performance e as Rondas trazem exatamente as usinas do título.
- **O outro nível:** o "ver todas" de cada quadro abre a Visão geral com o filtro dele (`perf.abaixo_meta`,
  `acomp.chamados`, `acomp.pts`, `acomp.rondas`, `acomp.ext`) ou o Ranking; cada linha abre a janela que a Visão já
  tem: o dia a dia da meta, a PT para decidir, o motivo da nota da equipe, a última ronda, os extintores da usina. O
  **chamado abre a tela dele de Garantias por cima** (2ª rodada: "Não deve direcionar, apenas sobrepor a tela como uma
  meio que janela dando um blur de fundo"): o `<dialog id="cr-chamado">` (o mesmo fundo desfocado das outras janelas)
  com a moldura `/os/_nexus/chamado/<nº>` (`ponte.chamado_os`), que traz a MESMA tela do OS Creator numa moldura dentro
  dela (assim ela se vê embutida, sem o cabeçalho e as abas do OS Creator); sem o login do Fracttal, a moldura diz como
  entrar e volta ao Painel. O **"← Acompanhamento" da tela do chamado abre o quadro no supervisor do Painel** (3ª
  rodada: "gostaria que já viesse com o supervisor filtrado"): no clique do chamado, o Painel guarda o Responsável UFV
  nos filtros que o quadro relê NESTA aba (`sessionStorage["acomp.filtros"].ufv`, o `acomp.js` do OS Creator, sem
  mexer na cópia); o Responsável UFV do quadro é o Responsável O&M da ficha da usina, o mesmo do Painel. Com "Todos",
  o filtro do supervisor sai. O setor Supervisão Campo tem telas do OS Creator (o portão por setor abre `/os/...` só a
  quem tem uma: conferido nos Acessos em 28/10).
- **OSs em verificação** (6ª rodada, 29/10/2026: "ao lado de PTS PENDENTES quero um 'OSs em verificação' irá contar as
  OSs em verificação que não tem etiqueta da performance, chamados, engenharia e não foi criada por ninguém do time do
  COS. Pense em como fazer isso sem pesar todo carregamento"): o número à direita das PT, a lista na janela.
  - **A regra** (`campo/verificacao.py`):
    - **A fila:** a da Aprovação de OS, relida em segundo plano e guardada (`regras_app._FILA_CACHE`).
    - **A usina:** a do cadastro, pelo nome do Fracttal, a MESMA ligação da Aprovação (`visao.usinas_do_fracttal`).
    - **A OS:** junta as tarefas dela. O título, a criação e o técnico são da OS; os ativos são os `id_item` distintos.
    - **A espera:** é a da tarefa terminada há mais tempo, como a Aprovação conta (a cor é a régua dela, 7 e 30 dias).
    - **Ficam de fora:**
      - as etiquetas PERFORMANCE, CHAMADOS e ENGENHARIA (o `labels`; nomes conferidos na fila de 29/10);
      - as criadas por alguém do setor COS (`nexus_setores`), pelo código da pessoa no Fracttal (`code_create_by`) ou
        pelo nome (`created_by`): o código casa 8 de 9, o nome 7.
    - **O código da pessoa:** vem do `ler_pessoal`, guardado à parte em `codigos`, fora da linha da tela de Pessoas.
  - **Sem pesar o Painel:**
    - O número chega por `fetch` depois da página: `/t/campo/responsaveis/verificacao?so=n`, em JSON.
    - A lista é o pedaço da mesma rota (`_resp_verificacao.html`), aberto pelo `data-cr-painel` de sempre.
    - Medido na bancada com a fila real (6.550 tarefas): o número em 0,5 s e a lista em 0,1 s.
    - Fila ainda não lida no servidor: "—", e a página pede de novo em 30 s.
  - **As colunas** (as do pedido): OS (abre o card do OS Creator), Criação, Título, Ativos, Técnico, Cliente, Usina,
    Sem conclusão, o Concluir e o PDF, este ao passar o mouse na linha.
  - **Concluir e PDF:** são os do OS Creator, com a sessão do Fracttal da pessoa.
    - O Concluir é `POST /os/api/os/<id>/concluir`, irreversível, com a confirmação antes. O PDF é `POST /os/api/os/pdf`
      e depois o download.
    - Sem a sessão do Fracttal (401), a janela manda entrar no Fracttal pelo OS Creator.
    - **"Concluída" só com o ok do OS Creator** (revisão de 05/11/2026, achado na Aprovação por fatos, que usa a mesma
      rota): `r.ok && !r.redirected && r.j.ok === true`, com a frase da rota (`mensagem`), em âmbar quando o `aviso`
      (um booleano: fechou sem a data de fim) vem ligado. Antes, a sessão do Nexus vencida (12 h, ou o Sair noutra aba)
      fazia o portão responder 302 para /entrar, o fetch seguia, recebia 200 em HTML e a tela dizia "OS X concluída."
      sem nada ter ido ao Fracttal; e o aviso saía como "concluída. true". Redirecionado, ou resposta sem JSON: "A sua
      sessão do Nexus acabou: recarregue a página e entre de novo." O PDF segue a mesma regra. Prova na bancada (fila
      real de 29/10): o Concluir depois do /sair deu o aviso da sessão, e a resposta simulada da rota (com e sem o
      aviso, o erro e sem o ok) deu a frase certa em cada caso. No ar (05/11/2026, 15:11 de Brasília, e4df64a): o POST
      sem sessão na produção volta 302 para /entrar e, seguido, 200 em HTML (o caso do defeito), e a página no ar traz o
      script novo. A OS de TESTE - PA não aparece nesta lista (não é usina da Visão), então o Concluir de verdade pela
      tela pediria uma OS de cliente: não foi feito; a mesma rota respondendo `ok: true` com o status 3 lido de volta foi
      provada no Fracttal pela Aprovação de OS (OS 18630, acima).
    - A OS concluída, ou mudada no card, sai da fila guardada pela conferência da Aprovação
      (`/t/campo/aprovacao/<id>/conferir`: só sai o que o Fracttal confirma).
  - **Exemplo:** na bancada, um responsável com 26 usinas tinha 212 esperando; ficaram de fora 69 por etiqueta e 95
    criadas pelo COS.
- **O relatório em PDF** (6ª rodada: "Botão de baixar relatório: ao extremo lado direto da mesma linha dos filtros (...)
  em PDF com basicamente o que tem focado no que falta para o supervisor (...) um resumo no início e depois
  aprofunda!"). O botão "Exportar relatório" fica na ponta direita dos filtros, só no Painel. A rota é
  `/t/campo/responsaveis/relatorio.pdf`, com os filtros da tela (`campo/painel_relatorio.py`, reportlab como o relatório
  dos extintores).
  - **O dado é o do Painel:** o `montar`, a faixa "Parada agora" e as OSs em verificação. Nada é recalculado.
  - **A ordem:**
    1. a faixa com o nome;
    2. o resumo com os 8 números;
    3. "O que cobrar primeiro", em frases, nesta ordem: o parado, o vencido, o que falta (abaixo de 90%, sem ronda,
       extintores, OSs, o chamado mais antigo, a equipe de menor nota);
    4. o detalhe de cada quadro, só o que falta: as usinas abaixo da meta, as paradas, as PT, as OSs em verificação,
       os chamados, as rondas que faltam (nunca, 7 dias ou mais, longa pendente), os extintores vencidos e o ranking.
  - **Os temas (7ª rodada, 30/10: "a pessoa possa marcar o tema que ela quer levar, as vezes não quer algo, tem que
    ter a opção de tirar"):** o Exportar abre uma janela com os 8 temas de `painel_relatorio.TEMAS`, todos marcados,
    "Marcar todos · Tirar todos" e o Baixar PDF (trava, com o aviso, sem nenhum marcado). Os marcados vão como `tema`
    repetido no endereço; o tema tirado sai do resumo, de "O que cobrar primeiro" e do detalhe, e o PDF diz no topo
    quais temas leva. Sem `tema` (ou só valores que não existem) o PDF sai inteiro, como o link antigo. As OSs em
    verificação só são montadas se o tema estiver marcado.
- **Prova da 6ª e da 7ª rodada:** `tests/test_campo_verificacao_painel.py` (a junção das tarefas, as etiquetas e o COS,
  a rota do número e da lista, o script do Concluir e do PDF, o PDF do relatório, o placar da equipe, o ativo limpo, as
  partes da nota com o peso e o que fazer, e os temas tirados do resumo e das frases).
- **Prova:** `tests/test_campo_painel_responsavel.py` (a ordem e a completude de cada quadro, o nome do ativo, o número
  das rondas, os extintores, o padrão de quem entra, o "Todos", o CSS das 6 linhas com a rolagem e da janela do
  chamado), `tests/test_dados_fato_chamado_status.py` (o status no fato) e `tests/test_oscreator_chamado_por_cima.py`
  (a moldura). Conferido na bancada com o banco real (28/10, 2ª rodada, com o status que a publicação nova grava): nos
  8 responsáveis e em "Todos", cada número igual às linhas do quadro (todos: 254 chamados em 63 usinas, 47 sem status;
  71 usinas sem ronda há 7 dias ou mais, 14 nunca; 36 usinas com extintor vencido).

### O bloco Manutenção, a Limpeza e a faixa "Parada agora" (18/10/2026)

Um supervisor montou um painel próprio (planilha, robô do Fracttal, WhatsApp) porque a Visão não mostrava a manutenção
das usinas dele. Levi, 18/10/2026: o objetivo é os responsáveis largarem os painéis próprios e usarem só o Nexus,
"pegando tudo do Fracttal ou Nexus, sem fontes externas!". Desenho e decisões:
`docs/superpowers/specs/2026-10-18-visao-responsavel-manutencao-design.md`.

- **De onde vem:** as tarefas das OS do Fracttal no banco (`nexus_os · fato_tarefa_os`, lidas pelo próprio Nexus de
  hora em hora: `nexus/campo/tarefas_os.py` e `nexus/dados/CLAUDE.md`), os motivos do Fora da programação do PCM
  (`motivos.vigentes`, decifrados na conta: a marca guarda a usina e a tarefa cifradas), as OS de chamado
  (`nexus_chamados`), a programação (`nexus_programacao`, lida do FIM para trás: a carga põe as 4 semanas do arquivo do
  PCM no fim, `_programacao_recente`), as OS de parada abertas (`falhas_performance · disponibilidade_os`) e a limpeza
  das Rondas (`visao.sujidade_vegetacao`, a última leitura em 90 dias, sem pedir releitura ao Fracttal). A única fonte
  externa é a programação (cópia do `banco_dados.json` do PCM), e o bloco diz isso.
- **O que conta (`nexus/campo/manutencao.py`, puro):** OS abertas = OS não finalizadas, em processo e em verificação;
  no detalhe, as que esperam a aprovação: TODA OS em verificação, com as tarefas feitas ou não (é a fila da Aprovação;
  a revisão de 18/10/2026 achou que só a tarefa ainda aberta contava, e a OS que o técnico terminou sumia). No detalhe,
  uma linha por situação (Levi, 18/10/2026: "separe por linha, o que está dependendo de aprovação e o que não foi
  iniciado"): esperando a aprovação, **não iniciada** (OS em processo sem nenhuma tarefa em progresso, pausada no App ou
  feita) e em execução (com uma); as três somam as abertas. A não iniciada é um link para o Quadro da semana com o
  cliente e a usina filtrados ("filtrando o cliente com o nome da usina pesquisada"): a busca vai pelo site do Fracttal
  do de-para ("Cliente - Usina - UF", o nome do arquivo do PCM; `sites_fracttal`, feito na conta da tela desde
  19/10/2026, e não no pedido), e sem ele, ou com o provisório
  "(sem Classificação 1) ...", pelo nome do cadastro. Medido em 18/10/2026: 72 dos 80 links acham tarefa na semana ou nas
  que não couberam. **Atrasada é a régua do PCM** (Levi: "Régua do PCM: +10 dias"; o
  `DIAS_ALERTA` do robô da Gestão PCM): tarefa aberta com a Data Programada há MAIS de 10 dias, contada por tarefa, como
  o PCM conta. Ficam fora de OS abertas e atrasadas, para nada contar duas vezes: o backoffice (decisão do Levi: o
  supervisor não age sobre elas), a tarefa com motivo do recorte do painel (motivo que tira ou justificativa do App:
  conta em Pausadas), a OS do `fato_chamado` (conta em Chamados), a Zeladoria (no detalhe, e a etiqueta "zeladoria vencida" no nome) e o Teste. Vencem até
  amanhã só informa. A marca casa com a tarefa pela OS, o código canônico (código vazio = todos os ativos da OS) e a
  `tarefa_chave`. **Semana** = a semana passada, FECHADA, pela conta do Fechamento do PCM (linhas do plano finalizadas
  ÷ linhas do plano): na semana corrente a rolagem da noite tira da agenda o que não foi feito (vai às pendentes, fora
  do fato) e o "até hoje" saía inflado; o dia de hoje até agora (as linhas cujo `hora_inicio` passou) só informa.
  Zeladoria: a próxima programada, a vencida e a última feita (tipo de tarefa Zeladoria no Fracttal).
- **As réguas** (`REGUAS`, bloco manut, e as decisões do Levi de 18/10): qualquer OS de parada aberta (usina inteira
  ou equipamento) é crítico e vai para a faixa; tarefa atrasada é atenção, e crítico quando a mais antiga passa do
  **limite de quem olha**; tarefa parada, semana passada abaixo de 85% e zeladoria vencida são atenção. A ordem do
  bloco: o nível; dentro dele, parada, mais tarefas atrasadas, mais paradas, a semana mais baixa.
- **O limite** (Levi: "o supervisor decide, começa com 30 dias mas pode alterar"; "no navegador dele"): o campo do
  bloco manda `?limite=`, e a rota grava o cookie `nexus_resp_limite` (1 ano, no caminho do prefixo); sem o parâmetro
  vale o cookie; sem os dois, 30. Número fora de 10 a 365 vai ao mais perto; texto vale 30 (`limite_do_pedido`). Como o
  nível depende de quem olha, ele sai NO PEDIDO (`com_manutencao`, cópias rasas: a cópia de 5 min é comum a todos).
- **A Limpeza** (Acompanhamento): "S2 V5" na cor do achado mais grave da régua das Rondas (nível 5 ou vala obstruída é
  crítico; nível 4, vala parcial ou sensor sujo é atenção); no detalhe, sujidade, vegetação, vala, sensores e o dia da
  ronda. A **faixa Parada agora**: as OS de parada abertas nas usinas DO FILTRO, a mais antiga primeiro, 6 e "e mais N".
- **Avisos:** sem o `nexus_os` no banco, "As OS do Fracttal ainda não chegaram ao banco" e o bloco não cobra por elas;
  a última leitura do Fracttal desta máquina que falhou ou se recusou a gravar (`tarefas_os.estado()`, lido no pedido)
  aparece no topo, com o motivo e de quando são as OS que valem. A foto das OS diz o dia quando não é de hoje
  (`foto_das_os`, pelo `gerado_em` da qualidade, gravado por qualquer máquina) e, passada de 2 h, avisa ("As OS da tela
  são da leitura de 17/10 às 09:10"): a tela dizia só a hora, e a foto de ontem passava por de hoje. Sem os motivos do
  PCM (nenhuma cópia boa) ou com marca que não abre com a chave desta máquina, a tela avisa: essas tarefas contam como
  atrasadas, não como paradas. **Provado em 18/10/2026:** a semana passada (W41) da Visão, pela cópia do banco, bate com
  o "Por cliente" do Fechamento do PCM, cliente a cliente (958 linhas do plano, 958 com usina; só a grafia do nome do
  cliente difere entre o arquivo do PCM e o cadastro).
- **O card da OS:** o item de OS do detalhe usa a chave `os_card` (`{"wid", "folio"}`) e abre o card do OS Creator
  (`oscreator/card_os_abrir.html`; sem o id, pelo número). **Nunca `numero`**: no template, `numero` vira o botão da PT.
- **Prova:** `tests/test_campo_manutencao.py` (as regras num dia fixo) e os testes do bloco em
  `tests/test_campo_responsaveis.py` (a tela, o limite e o cookie, o cookie com lixo, a faixa com o filtro, o aviso sem
  o fato, a leitura que falhou, o card da OS, o motivo que tira das atrasadas, os cartões com os três blocos, a
  programação lida do fim). Na tela, com o dado real (18/10/2026, só GET): 8.737 tarefas, 334 OS abertas, 1.023 tarefas
  atrasadas, 19 paradas, a semana passada (W41) em 52%, 31 OS de parada abertas; 60 usinas em Focar, 35 em Acompanhar e
  36 em dia com o limite de 30; a 1920, 1536, 1440, 1366, 1024 e 375 px, escuro e claro, sem rolagem lateral.

### O Ranking das equipes (18/10/2026)

A peça 2 da Visão (Levi: os responsáveis largarem os painéis próprios). Responde "qual equipe cobrar": a aba `modo=ranking`
mostra um cartão por equipe das usinas do filtro (o responsável logado vê as dele; quem não é responsável, todas), da pior
para a melhor. Desenho e decisões: `docs/superpowers/specs/2026-10-18-visao-responsavel-ranking-equipes-design.md`.
- **Filtrado, o ranking é o mesmo** (Levi, 18/10/2026: "O ranking das equipes tem que permancer mesmo filtrados, o que
  está acontecendo agora é que se eu filtro [um responsável] vai contar de 1 a 11"): `ranking_equipes.classificar` faz a
  nota, a posição, o "de N" e a seta sobre TODAS as equipes; o filtro (responsável, cliente, busca, equipe) só escolhe os
  cartões, e o cartão é o da equipe inteira. Os números de cima são os dos cartões que aparecem. O "Sem equipe" fica com
  as usinas do filtro (é a lista do conserto no cadastro). Medido em 18/10/2026: nenhuma das 55 equipes tem usina de dois
  responsáveis; o responsável com 12 equipes passou de 1º a 12º para 7º a 42º de 52.
- **A janela da equipe** (Levi, 18/10/2026: "Clicando na equipe deve dar um breve resumo do motivo da pontuação da
  equipe estar abaixo para que o supervisor possa cobrar a equipe"; depois, "quero ao clicar na equipe um detalhamento
  melhor [do Em quê cobrar], não cheio de informações mas quero a informação, ao resumido e direto onde o supervisor
  bata o olho e possa cobrar o técnico com dados!"; no quiz, "Item a item com a prova" e, nas OS mais baixas, "Faltou
  os pontos"): o clique no cartão abre `/t/campo/responsaveis/equipe?equipe=` (o pedaço `_resp_equipe.html`).
  - No topo, os técnicos da equipe pelo nome (`responsaveis.tecnicos_da_equipe`, o cadastro), a posição e a nota.
  - **Em quê cobrar** (`ranking_equipes.cobrar`): as MESMAS áreas e níveis das etiquetas do cartão (Focar = crítico,
    Acompanhar = atenção; as usinas da equipe com o bloco Manutenção no limite de quem olha, o cookie da Visão), cada
    uma com até 3 provas, uma por linha, a pior primeiro: a OS e os dias (parada, atrasadas, pausadas, chamados), a PT e
    quem pediu (o `solicitante` entra na lista da PT em `montar`), o extintor, o ativo; nas áreas sem lista (ronda,
    limpeza, meta, semana, zeladoria), o título do alerta da usina; a disponibilidade, a usina e o valor. A OS atrasada
    não tem técnico no banco (o `fato_tarefa_os` não guarda pessoa, regra 8): ela cobra a equipe, cujos técnicos estão
    no topo.
  - **O Focar em tabela e o "e mais" que abre** (Levi, 28/10/2026, na janela de uma equipe: "ao clicar nas equipes
    aparece esse 'e mais x' tem que dar para expandir esses 'e mais' o supervisor deve saber o que é. Consegue trazer em
    um formato melhor? Usinas em linhas e essas linhas em coluna. pelo menos no focar"): o Focar é a tabela de
    `ranking_equipes.matriz`, as áreas em crítico nas colunas e as usinas com algum alerta delas nas linhas (a com mais
    áreas em crítico primeiro); a célula traz a prova sem o nome da usina (`_provas(..., com_usina=False)`), 2 à vista
    e o resto no "e mais" dela, e a usina em crítico naquela área leva a borda vermelha. Com a tabela, a janela fica
    mais larga (`.cr-modal:has(.cr-rk-j-mat)`). O Acompanhar segue em lista, com o "e mais N" que abre o `resto` ali
    mesmo. Para abrir TUDO, as atrasadas e as pausadas vêm inteiras (`manutencao`: `todas_atrasadas`/`todas_paradas`;
    a linha da Visão geral segue com as 5 piores, `lista_*`).
  - **O "e mais" aberto, em linhas, e o ativo limpo** (6ª rodada).
    - **O "e mais":** "o e mais 2 não sumiu, os mais dois não quebraram como os demais, vieram juntos numa linha só".
      Aberto, o resumo some, e as provas ficam numa lista dentro do `<details>` (`.cr-rk-j-mais-lista`): o `<details>`
      não arruma os filhos em grade no Chrome.
    - **O ativo:** "o nome do ativo pode aparecer sem nome de fabricante, modelo ou código do ativo. Só o nome limpo".
      Os chamados e os ativos das provas passam pelo `responsaveis.nome_do_ativo`, o mesmo do quadro de chamados.
  - **A pontuação do mês** (6ª rodada: "quero uma explicação da pontuação mensal daquela equipe, pontos por ronda, bonus,
    quantidade de tarefas etc, um resumo do que temos no ranking das equipes"). Fica embaixo do cabeçalho.
    - **A conta da nota:** "97 = 60% da qualidade 95 + 40% da cobertura 100%".
    - **Três números:** a qualidade (a média de N notas: tarefas e rondas), a cobertura (usinas com ronda) e a posição
      com a seta.
    - **O placar do ciclo do App, por técnico:** sai de `ranking_equipes.placar_da_equipe` sobre o
      `visao.ranking_pontos` do mês, casado pelo nome do cadastro. As colunas são posição, pontos, tarefas (registradas,
      pontos, quantas contam, nota média), rondas (pontos, no teto), bônus e devolvidas.
    - **A régua:** a frase do piso, do teto e do bônus, com os números que o App publicou.
  - **Nota do App** (`ranking_equipes.motivos`): o que ela perde, uma linha por motivo. Desde a 6ª rodada ("-1 oq? -1
    ponto? 1 OS anulada? explique melhor e explique o que impacta, o supervisor não tem uma cristal ball"), cada linha
    diz:
    - quantos pontos da nota da equipe, de 100;
    - onde aconteceu ("em 58 de 125 tarefas");
    - quanto o critério vale em cada tarefa (o peso da composição);
    - o que o técnico faz para não perder (`ranking_equipes.COMO_RECUPERA`).

    A cobertura diz as usinas sem ronda e que ela vale 40%. A nota perde 100 − nota pontos: a qualidade tira 0,6 × (100 − qualidade), a cobertura o resto; a parte
    da qualidade vai a cada critério (a "Composição da nota" de cada tarefa, no livro cru pela chave do fato: subtarefas
    25, fotos 20, descrição das fotos 10, assinatura 10, observação 15, GPS 20, que somam a nota; medido em 18/10/2026,
    fecha em 3.790 de 3.790 tarefas) e às rondas. Os inteiros são repartidos pelo maior resto e sempre fecham com a nota
    (provado nas 52 equipes). Depois, as 5 OS com nota mais baixa: a nota, a OS, a usina, quem fez, o dia e os pontos de
    cada critério que perdeu ("Fotos 0/20 · Observações 0/15"; a ronda, as falhas); tarefas iguais da mesma OS numa
    linha ("7 tarefas iguais").
  - **A OS citada é o botão verde que abre o card dela** (Levi, 19/10/2026: "ao citar uma OS tem que ficar verde grid e
    deve ser possível clicar e ver o card da OS que nem quando clicamos em uma OS no OS Creator Web"): nas provas
    (parada, atrasadas, chamados, pausadas) e nas OS com nota mais baixa, `cr-os` com o número e o id do Fracttal quando
    o dado tem (a atrasada e a pausada pelo `fato_tarefa_os`, a tarefa pelo `fato_fechamento.id_os_fracttal`; a parada,
    o chamado e a ronda só com o número, e o card acha a OS por ele). A janela é um `<dialog>` modal, na camada do topo, e
    cobriria o card: o clique fecha a janela, abre o card (`NexusOsCard`) e a reabre como estava quando o card fecha
    (`aoFechar`), no script da Visão. A PT segue pelo número dela.
  - **Focar e Acompanhar encolhem** (Levi, 19/10/2026: "eles aparecem expandidos que nem estão agora mas deve ser
    possível encolher!"): `<details open>`, o título com a seta e quantos itens.
  - `responsaveis.ranking_detalhe` lê as MESMAS linhas da conta (o número de notas bate com o do cartão nas 52
    equipes). A janela leva 0,1 a 0,2 s; sem as notas do App, diz, e o "Em quê cobrar" continua.

- **A posição é a régua do App** ("de acordo com as regras do ranking do app de campo"): o Ranking por região do painel
  do App (`_ranking_regioes`), a única conta por equipe que o App tem (o placar do ciclo é só por técnico). Nota = 60%
  qualidade + 40% cobertura, no **mês vigente** (do dia 1º até hoje; Levi, 28/10/2026: "Ranking das Equipes - Outubro,
  sempre o mês vigente", no Painel e no Ranking; até então, os últimos 30 dias, porque o App não tem janela oficial; no
  começo do mês a nota tem poucos dias, e ele aceitou). Qualidade = a média
  simples das notas das tarefas fechadas pelo App (`fato_fechamento.nota_pts`) e das rondas do App (`fato_ronda.nota_pts`);
  cobertura = usinas da equipe com ronda ÷ usinas. A cor é a escala do painel do App (85 verde, 70 âmbar), não régua da
  nota. Empate: qualidade, cobertura, volume, nome (a tela diz). Sem nota (nenhuma OS nem ronda do App): sem posição,
  antes das ranqueadas; "Sem equipe" no fim. A seta compara com o mesmo trecho do mês anterior (do dia 1º ao mesmo dia,
  ou ao último dia do mês passado quando ele é mais curto: `ranking_equipes.periodos`; a mesma lista de equipes); a usina
  mobilizada depois do fim do período anterior fica fora dele (revisão de 18/10/2026: contava como "sem ronda" de antes,
  e a seta "subia" sem a equipe ter melhorado).
  A régua da tela diz as datas dos dois períodos e, quando o fato de fechamento saiu na hora (o banco sem a carga desta
  versão do livro do App), diz isso; a dica do "base pequena" usa o `visao.BASE_PEQUENA`.
- **Diferenças contra o painel do App** (a tela diz): a equipe da usina é a do cadastro do Nexus (no App, a OS vai ao
  cluster da tarefa na programação do PCM ou da usina no catálogo dele); a base da cobertura são as usinas mobilizadas; o
  dia é o de Brasília; a ronda avulsa do Nexus conta na cobertura.
- **Em quê cobrar** (`ranking_equipes.etiquetas`): uma etiqueta por área com alerta nas usinas da equipe, tirada dos
  MESMOS alertas que fazem o semáforo do cartão (os três blocos, no limite de quem olha), no nível do pior: "nada a
  cobrar" só com o semáforo todo em dia (revisão de 18/10/2026: saíam de 12 números à parte, e uma equipe só com um ativo
  em crítico mostrava "nada a cobrar"). O crítico primeiro, até 4 no cartão; **não mudam a posição** (decisão do Levi). A
  meta conta usinas abaixo de 97%, nunca a meta somada do grupo (uma usina com a meta errada no Gerencial punha a equipe
  em 2.207%); a disponibilidade conta usinas, não a média do grupo. Uma legenda diz o que são os três números do
  semáforo (cor e palavra).
- **De onde vem:** `responsaveis.ranking_fonte` agrega por usina, nos dois períodos, na cópia de 5 min da Visão (as duas
  leituras já estão no ciclo quando a Visão é feita); `ranking_equipes.cartoes` agrupa no pedido, porque os filtros e o
  limite das atrasadas são de quem olha. Nada novo no banco. Sem as notas, a aba diz e não mostra cartão.
- **O filtro `equipe=`**: o endereço do cartão (quem abre noutra aba) e o link da janela do motivo levam à Visão geral só
  com as usinas da equipe (o nome exato do cadastro), com o "×"; a volta aos cartões dos responsáveis tira o filtro
  (revisão de 18/10/2026: ele vazava escondido para lá).
- **Prova:** `tests/test_campo_ranking_equipes.py` (a régua, igual à aritmética do App, as etiquetas, os cartões, a seta,
  a posição com filtro, o motivo que fecha com a nota; mutações pegas; os testes que leem as notas da fixture usam a
  `tela_no_mes`, que leva as rondas e os fechamentos para perto de 18/10 e dubla o dia do ranking, porque no começo do
  mês a ronda de "3 dias atrás" é do mês passado e sai, como deve: em 03/11/2026 dois falharam assim) e os testes da aba e da janela em
  `tests/test_campo_responsaveis.py` (`duas_equipes`: a SC Oeste 01 com nota, 2ª de 2 com qualquer filtro). Com o banco real (18/10/2026, só GET, o
  `test_client` com a sessão de administrador e o HTML servido local): em "Todos", 55 cartões (52 ranqueadas, notas de 41
  a 98; 2 sem nota; 1 "Sem equipe"); o responsável com mais equipes vê 12. O agrupamento no pedido leva 7 a 8 ms para as
  55; a conta fria da Visão ficou em 22 a 24 s, como antes (as leituras do ranking já estão no ciclo). A 1440 e a 375 px,
  escuro e claro, sem rolagem lateral; o "Acompanhamento" do mini-bloco vira "Acompanh." (a palavra inteira cortava).

### Os chamados de garantia no banco (`nexus_chamados · fato_chamado`, 12/10/2026)

- O quadro **Acompanhamento de chamados** (OS Creator, `/os/chamados/acompanhamento`; no Nexus, Chamados › Garantias)
  lê o Fracttal AO VIVO com a sessão de quem entrou: é nele que a analista de chamados escreve o ticket e finaliza. Quem
  só CONTA chamados lê o fato, publicado por `nexus/campo/chamados_acompanhamento.py` (o fato puro e as regras:
  `nexus/dados/fato_chamado.py`).
- O que entra: as OS de acompanhamento de chamado (a "OS 3" do chamado de garantia: tipo Administrativa, a marca
  "[CHAMADO] Acompanhamento — fabricante · componente" na nota; a mesma regra do quadro, `acomp_web.eh_os3`) em
  processo (`aberto`), em verificação (`verificacao`) e concluídas nos últimos 90 dias (`concluido`). Cancelada fora.
  Medido em 12/10/2026: 17 em processo e 1 em verificação.
- **Limite**: a API REST do Fracttal (a credencial do Nexus) NÃO traz a subtarefa do ticket (os endpoints de subtarefa
  dão 400 e o `completed_percentage` fica 0): "aguardando ticket" × "com o fabricante" só no quadro.
- Fora da carga de hora em hora de propósito (aquela não toca no Fracttal). Laço próprio no `campo.instalar`: 1ª volta 2
  min depois de subir, depois aos :50. Grava a máquina que chegar primeiro (regra 11: a última gravação do livro tem de
  ter mais de 50 min). `NEXUS_CHAMADOS_PUBLICAR=0` desliga numa máquina. Fracttal que devolve 0 com o livro cheio não
  apaga o livro. Enquanto o servidor não atualiza, quem publica é o Nexus do PC.
- Sem pessoa e sem a nota (regra 8): o fabricante e o componente saem da marca (categorias).
- Prova: `tests/test_campo_chamados_acompanhamento.py`.

### A Visão geral, no lugar de Onde focar (18/10/2026)

Levi: "uma visão onde unifica todas as usinas", com os KPIs dos três blocos que, ao clicar, "já filtra as usinas em
atenção daquele bloco"; "centralize o cabeçalho e todas as colunas exceto Usina"; e, no mesmo dia, "A IDEIA É QUE A VISÃO
GERAL SEJA UMA MELHORIA DO ONDE FOCAR, ENTÃO PODE TIRAR O ONDE FOCAR", "AO CLICAR NO BLOCO EM VISÃO GERAL DESTAQUE AS
COLUNAS DAQUELE BLOCO E ORDENE DE ACORDO COM AQUELE BLOCO" e "deixe mais adaptável". Desenho:
`docs/superpowers/specs/2026-10-18-visao-responsavel-visao-geral-design.md`.
- **As abas:** Por responsável, Visão geral e Ranking das equipes. Onde focar saiu: escolhido o responsável (ou o
  responsável logado), abre a Visão geral; o endereço antigo `modo=foco` também.
- **Em cima, os três blocos** na ordem Performance, Manutenção e Acompanhamento (`BLOCOS_GERAL`), com os MESMOS números
  do resumo (`soma`) e a triagem de cada um; o campo do limite das atrasadas e a nota de onde vem a semana e as OS ficam
  no bloco Manutenção.
- **O filtro de Cliente** lista só os clientes das usinas do responsável escolhido (Levi, 18/10/2026: "O filtro de
  cliente deve filtrar de acordo com o responsável"); o cliente que não é dele deixa de valer, e a tela não esvazia.
- **Embaixo, uma lista só** com as usinas do filtro da tela (responsável, cliente, busca, equipe), com as colunas na
  ordem do Levi: Meta, PR / prev. e Disp.; OS abertas, Atrasadas, Pausadas e Semana passada; Ronda, Limpeza, PT, Chamados
  e Extintores. As células são os `valores` de cada bloco, com a mesma cor; o valor da Performance abre o dia a dia; a
  etiqueta de cada bloco (parada, ativos) vai no nome; ao abrir, o detalhe dos três blocos (o macro `det_bloco`).
  "Pausadas" (o nome do Levi) é a tarefa fora da programação; "parada" fica para a usina parada.
- **O clique:** o bloco (o cartão inteiro, não só o nome: "deve ser possível clicar no bloco (...) inteiro, e não só no
  título"; o link do nome cobre o cartão pelo `::after`, sem sublinhar o nome nem o ícone ao passar o mouse: "Tire esse underline dos blocos"; o sinal é a borda do cartão) ORDENA a lista pela régua do bloco (`bloco=perf`: a pior meta;
  `manut`: `ordem_da_manutencao`; `acomp`: a pior ronda) e destaca as colunas dele (`lista_geral`, `bloco_geral`);
  clicar de novo volta à ordem geral (a do foco). O "pedem atenção", "focar", "acompanhar" e cada número, por cima do
  link do bloco, FILTRAM ("funcionará como filtro os KPIs do bloco"; `filtro=`; `FILTROS_GERAL` guarda a condição de
  cada um, a MESMA que conta o número no `soma`, nenhuma régua nova: o "Abaixo da meta: 80" mostra as 80 usinas) e
  destacam o bloco deles, MAS a lista segue na ordem do foco (revisão de 18/10/2026: "PT esperando" ordenado pela ronda
  jogava a PT parada hoje para o fim, contra a regra da tela). Chave que não existe é ignorada; número zero não é link;
  o OS abertas filtra as usinas com OS em processo ou em verificação (`manut.os`); o × limpa. O filtro e o bloco seguem quando se troca o responsável, o cliente ou a busca; o "Todos os
  responsáveis ×" fica na Visão geral, e o cartão de um responsável abre sem filtro. A bolinha da linha é o nível do
  bloco destacado (sem bloco, o da usina); a zeladoria vencida (fora das colunas) vai como etiqueta no nome.
- **A largura:** as colunas dividem a largura em frações (a Usina com 160 px no mínimo e duas partes), e o valor quebra
  a linha se precisar. De 1181 a 1366 px (o notebook comum) ficam as colunas principais: Meta, Disp., Atrasadas,
  Pausadas, Semana passada, Ronda e PT (o resto no detalhe). Até 1180 px a lista vira cartões, com as etiquetas P, M e A
  na cor do nível de cada bloco e o alerta principal (a do bloco destacado, com contorno).
- **O destaque do bloco** (Levi, 18/10/2026: "esse destaque em azul tá feio (...) Mude para um verde grid com uma
  transparência de 70% pegando cabeçalho e célula pegando a área do bloco toda!"; visto na tela, "o verde está muito
  forte, deixe 1/3 do que está" e "tem que ser uma cor só destacando a área inteira (...) discreto mas que mostre!"): uma
  área `--faixa-verde` (o verde Grid a 10% já misturado na superfície, opaco) do nome do grupo à última usina, nas
  colunas do bloco e no espaço entre elas. É o `::before` de cada linha da grade, posto nas colunas do bloco pelo
  `data-bloco` da lista e por cima da linha que separa as usinas (por isso opaco: translúcido, as linhas apareciam como
  listras). A 1366 px, nas colunas que sobram; nos cartões, sai. Com o verde fraco, o "em dia" verde segue legível (o
  porquê do cinza que havia antes, quando o realce era o verde-suave).
- **O centro das colunas:** o cabeçalho e as células `cr-col-*` ficam no centro (`.cr-g > [class*="cr-col-"]`); a Usina,
  à esquerda.
- **Prova (18/10/2026, o banco real só lido):** 131 usinas; o clique em Manutenção pôs as críticas da Manutenção em cima,
  com as colunas realçadas; a 1920, 1440, 1300 e 375 px, nos dois temas, sem rolagem de lado. Na mesma noite, o bloco
  inteiro: o clique no vazio do cartão ordena e cada um dos 12 números leva ao filtro dele (OS abertas: 2.697 OS em 127
  usinas, a lista com as 127); a faixa verde a 1440 e 1300 px nos dois temas, fora a 375 px.

### O mapa das usinas na Visão geral (18/10/2026)

Levi: "Para o mapa podemos usar o IBGE como a performance faz". Desenho e decisões dele (Lista | Mapa na Visão geral, a cor
pelo bloco clicado, o resumo ao lado, só as usinas): `docs/superpowers/specs/2026-10-18-visao-responsavel-mapa-design.md`.
- **`?ver=mapa`** troca a lista pelo mapa, com as MESMAS usinas (os filtros e o clique dos blocos valem); o filtro do
  topo leva o `ver` junto. O ponto é um link (`usina=<id>`) que abre ao lado o resumo da usina (os alertas dos três
  blocos, ou o que está bem) e o "Ver na lista" (`#u-<id>`, a linha da lista tem esse `id`).
- **O desenho** é o do Mapa de risco (`performance/clima/mapa.py`: o contorno do IBGE, a projeção, `ufs_da_vista`),
  feito no servidor (`nexus/campo/mapa_responsaveis.py`). O recorte são os estados com usina na lista, no mínimo 3
  graus; o ponto crítico é desenhado por último (fica por cima). A cor: o nível do bloco destacado, ou o da usina.
- **A coordenada nunca vira texto:** abre só no servidor (`performance/clima/usinas.do_app`, cópia de 5 min por app) e o
  navegador recebe o x e o y do desenho. Sem endereço nem "como chegar". Usina sem coordenada vai para a lista "Sem
  coordenada no cadastro"; sem o cadastro na máquina (teste, PC sem o armazém), o mapa diz por quê.
- **Prova (18/10/2026, o cadastro e o banco reais, só lidos):** 127 usinas no mapa e 4 sem coordenada; o resumo da usina
  clicada; o mapa recolorido pela Manutenção; a 1440 e a 375 px, nos dois temas, sem rolagem de lado.

### A Central da usina, aba da Visão do responsável (04/11/2026)

Levi: "Como temos uma visão para os supervisores em Central do Responsável podemos ter como pesquisar a usina e ter uma
central de informações daquela usina, performance, disponibilidade, sujidade, pendências, chamados, PTs etc"; "inclua
junto da central dos responsáveis, como aba alternativa". Decisões dele (04/11/2026): a aba no Campo · App (`modo=usina`,
ao lado de Ranking das equipes); o **mês corrente** na performance, na disponibilidade e no histórico de chamados e de PT;
nas **pendências**, as rondas, as OS atrasadas e pausadas, as ocorrências abertas e a Segurança; a busca com **todas** as
usinas mobilizadas, para quem abre a Visão (sem o filtro de responsável, de cliente e da busca da lista, que somem na aba).
- **Nenhuma conta nova.** A usina é a MESMA linha da Visão (`montar` + `com_manutencao`, no limite das atrasadas de quem
  olha): a faixa de números (meta, PR × previsto, disponibilidade, limpeza, ronda, chamados, PT, OS atrasadas) e as linhas
  do detalhe (`det_linhas`, o miolo do `det_bloco` da Visão geral) com os mesmos botões: o dia a dia, os ativos, o card da
  ronda, o card da OS, a janela da PT, os extintores. O que a linha não traz vem da tela dona
  (`nexus/campo/central_usina.py`): os técnicos de hoje (PCM › Técnicos por usina, `atribuicoes.atuais`), as ocorrências
  abertas (`ocorrencias.estado` + `ordenar`, com o cofre), as pendências da Segurança (`hseq._pendencias`, a conta da Mesa,
  só as linhas da usina), os chamados finalizados no mês (`responsaveis.chamados_finalizados`, o fato do quadro
  Acompanhamento de chamados pelo dia do fim) e as PT esperando o De acordo na lista do Painel
  (`painel_responsavel.pts([u])`).
- **A busca** é a das Rondas, num pedaço só (`_busca_usina.html`, a lista do Nexus com nome e cliente · UF; a rota e o
  endereço de cada usina vêm de quem inclui). Sem o script, o `nome` acha a usina pela regra das Rondas (`CU.achar`: o
  nome igual sem acento nem caixa, ou o único que contém).
- **A fonte que não abre fica de fora com o aviso** ("Não consegui ler ..."); o resto da página vale. Os links para
  Ocorrências, Mesa da Segurança e Rondas só aparecem para quem abre essas telas (`setor_telas.liberadas_do_menu`).
- **Extintores (achado da Central, 04/11/2026):** a Visão contava o livro do App cru, e a Mesa, o HSEQ e o Comando, com as
  exclusões e as edições da Segurança. `responsaveis.extintores` agora passa pelo `decisoes.separar`: as duas telas dão o
  mesmo número.
- **Prova (04/11/2026, bancada só leitura com o banco real):** a Coração 1 e 2 com 102% da meta, PR 100,1% (previsto
  74,4%), disponibilidade 100,0%, S3 V3, ronda longa pendente, 7 OS atrasadas (a mais antiga há 72 dias), sem luvas desde
  03/11, a PT 15688 De acordo; a busca com 131 usinas, "coracao" leva à usina; a janela do PR e o card da OS abrem; a 375
  px uma coluna, sem rolagem de lado. Testes: `tests/test_campo_central_usina_0411.py`.
- **2ª rodada (04/11/2026):** "Deixar a lista de 'buscar usina' já no estilo nexus" (a lista aberta em grade que entrou
  aqui saiu na 3ª rodada: só o campo). "Melhore o visual dos cards, está simples demais e as linhas estão muito
  coladas": o cabeçalho com as pessoas em selos (as iniciais, o papel e o nome), o quadro com o ícone num selo verde, as
  linhas separadas por um fio com 13 px de respiro, o ponto da situação nas pendências (`det_linhas(..., marca=)`, a cor
  da régua da Visão) e a contagem nas linhas de chamados. Só `.cu-*`: a Visão geral não muda.
- **O relatório da usina para o cliente (2ª rodada):** "é interessante que dê para baixar um relatório da usina também!
  Algo bem profissional para o cliente!". O "Baixar relatório" do cabeçalho abre a janela do mês e dos temas (a do
  Painel: "Tem que poder escolher que nem é no painel"); a rota `responsaveis_usina_relatorio`
  (`/responsaveis/usina/<id>/relatorio.pdf?mes=&tema=`) monta o PDF em `nexus/campo/relatorio_usina.py`. Decisões do
  Levi: o **mês escolhido, o anterior (fechado) de início**, o corrente sai parcial até ontem (os três últimos meses: as
  rondas, os chamados e as tarefas ficam 90 dias no banco); os temas Performance e disponibilidade, Rondas e limpeza,
  Manutenção e Chamados de garantia, todos marcados; **PT, Segurança e nomes de técnicos não entram** (são internos). O
  dado é o das telas donas: a meta, o PR e o dia a dia do Gerencial e a disponibilidade com os eventos (os leitores das
  janelas), as rondas do mês (`historico_usina`), as tarefas feitas pelo App (`fato_fechamento`, sem as devolvidas), as OS
  abertas (`fato_tarefa_os`, a regra do bloco Manutenção) e os chamados (`fato_chamado`). O PDF: a faixa navy com o logo
  e o mês, os quatro números com a cor da régua, o resumo em frases, o gráfico da geração do dia contra a meta e as
  tabelas; o evento de disponibilidade da usina que junta duas do Gerencial (Coração 1 e 2) diz a parte
  (`os_disponibilidade` leva a `usina` do Gerencial). Prova: o de outubro da Coração 1 e 2 (671,4 MWh, 72% da meta, PR
  101,9%, 99,1%, 4 eventos, 5 tarefas, 0 ronda no mês: a usina só tem a ronda de 03/11 nos 90 dias) em 0,9 s.
- **3ª rodada (05/11/2026), nove pedidos do Levi:**
  1. "Nesses KPIS quero campos separados por linhas invisíveis separando cabeçalho e valor / quero que centralize
     horizontal e verticalmente": cada número da faixa ocupa três linhas da grade (o nome, o valor, o complemento), as
     MESMAS em todos (`grid-template-rows:subgrid`), cada pedaço no meio da casa; o complemento longo quebra parelho
     (`text-wrap:balance`).
  2. e 3. O cabeçalho da Visão (todas as abas) sem a caixa "lido às" do canto: a hora da leitura foi para o "!" amarelo
     ao lado do título, que outra frente do mesmo dia pôs como padrão do Nexus (`_explica.html`, acima, na Visão do
     responsável).
  4. "Quando não tem nenhum usina não precisa amontoar um monte de card de usinas, deixa só a parte de pesquisar
     mesmo!": a lista aberta em grade da 2ª rodada saiu (e o `busca_aberta` do `_busca_usina.html` com ela); a lista
     abre no foco, por cima, como nas Rondas.
  5. "Quero o 'Buscar usinas' do lado direito paralelizando com os botões a visão dos responsáveis!": a busca fica na
     linha das abas, à direita (`.cu-topo`); abaixo de 700 px, embaixo das abas, na largura toda.
  6. "Quando clicar em baixar relatórios: escolher qual o mês!": a janela do relatório pergunta primeiro "Qual mês?",
     com os três meses em botões (o anterior marcado), e depois "Quais temas?".
  7. "Quero que o gráfico de geração também apareça na visão do responsável > central da usina": o gráfico da janela do
     PR (a mesma macro, `campo/_graficos.html` · `geracao`) no quadro da Performance, do mesmo leitor
     (`serie_diaria` + `responsaveis_graficos.geracao`); sem a série no banco, o quadro fica sem ele. Na meia largura os
     eixos crescem e o valor em cima de cada barra sai (encavalava; o valor do dia fica na dica da coluna). Achado no
     caminho: o eixo de passo 2,5 escrevia "2" e "8" nas marcas 2,5 e 7,5 (0 casa); agora o eixo com marca quebrada leva
     uma casa em todas (`_casas`), na janela do PR também.
  8. "SE NÃO TIVER VERIFICAÇÃO OU CONCLUSÃO NÃO PRECISA APARECER NA TELA": no quadro Chamados só aparece a linha que tem
     chamado (a dos abertos também, pela mesma regra); sem nenhum, uma frase só.
  9. "o KPI de PT já tem a informação, ao clicar no KPI aparece o mesmo card que aparece em visão do responsável >
     painel": o quadro da PT saiu (com ele, as "Pedidas no mês" e o `central_usina.pts_do_mes`); o número da PT abre na
     janela a lista do Painel, da mesma macro (`lista_pts`), só da usina.
  Prova (05/11/2026, bancada só leitura com o banco real): a Altair e a Nova Xavantina 2 a 1440 px e a 375 px (sem
  rolagem de lado; a exclamação no celular presa à tela), a PT de 29 d 22 h na janela do número, o relatório com
  outubro marcado.

## Visão do cliente (05/11/2026)

De onde veio: a sugestão "Visão do cliente" (Início → Sugestões, 04/11/2026, com o mockup). O Levi decidiu a **fase 1**
("Sim, fase 1"; "cuida, começa e já vai cuidando"): a tela para a Grid (COS, PCM e Performance), com o login de hoje, em
Usinas 360° › Visão do cliente (`/t/campo/cliente`), para responder o cliente em segundos, sem abrir cinco telas. A fase 2
(o cliente entra com o login dele e vê a mesma síntese, só do `cliente_id` dele) e a fase 3 (a equipe saiu da base, a
hora prevista de chegada, pelo App) estão FORA.

- **O recorte é o `cliente_id` da usina** (o cadastro do Nexus): "contrato" não existe como entidade, e a fase 2 filtra
  pelo mesmo campo. A conta é feita por cliente, no servidor, e já sai **sem o que é interno**: nada de nome ou telefone
  de técnico, custo, horas, comentário interno da OS nem causa de falha (a plataforma diz o sintoma, não a causa). O teste
  `test_a_sintese_nao_leva_nada_interno` trava as chaves que saem. O lugar da usina é só a cidade, **sem o nome da
  equipe**: o PCM avisou (05/11/2026) que ele pode ser o de uma pessoa (`test_o_nome_da_equipe_nao_sai`).
- **Nenhuma conta nova; cada número é o da tela dona**:
  - Status: o tempo real da plataforma (`/api/entrada/tempo-real`) pela ponte SÓ DE LEITURA (`ler_tempo_real`, guardado
    2 min): a plataforma serve o que já montou e não fala com a API PV (a SunOp é paga). A resposta sem o
    `X-Nexus-Leitura-Ok: 1` não vale. Usina que o tempo real não traz é "Sem leitura", nunca parada. À noite a plataforma
    manda status ok com a causa "Sem sol (fora da janela solar)": aqui fica "Sem sol", nunca "Gerando" (na bancada às
    18:15, as 10 usinas da Athon). A última leitura de outro dia leva a data ("04/11 22:43"; sem ela, parecia de hoje).
  - Performance do mês: o Gerencial, a mesma linha da Visão do responsável (`meta.prod_kwh` e `meta_kwh`). O do cliente é
    a **soma** da geração sobre a soma da meta, não a média dos % (a usina grande pesa mais).
  - Chamados na distribuidora: o Andamento da Ronda COS (a tela Acionamentos), 30 dias, com o protocolo, sem os
    DISPENSADOS. O Andamento não diz quando a distribuidora resolveu: a tela escreve "nos últimos 30 dias", não "abertos".
  - OSs: `fato_tarefa_os` pela régua do quadro "OS e manutenção" da Visão (`manutencao.tarefas_por_usina`): fora o
    backoffice, o Teste, a zeladoria e as OS de chamado. O número é o que **ainda vai ser feito** (a fazer + em
    execução); a concluída que espera a conferência da Grid fica à parte, porque na bancada a Athon tinha 382 de 422 em
    conferência: o número do cliente não pode ser a nossa fila de aprovação.
  - Próxima visita: a programação do PCM (`fato_programacao`, a semana corrente e a próxima), o bloco não finalizado
    mais cedo de hoje em diante; de hoje, só o que ainda vai começar (o bloco das 09:00 visto às 18:00 já foi feito ou
    está em execução, não é "a próxima"). O código de plano do PCM ("MPA") vira "preventiva (MPA)".
- **Fonte que não respondeu = "sem leitura", nunca 0**, com o aviso amarelo no topo dizendo qual; o resto da tela vale.
  No PC o Andamento não está ligado (os chamados ficam "sem leitura"); no servidor está.
- A ordem da tabela: quem pede atenção primeiro (parada, sem comunicação, com perda, sem leitura; depois mais chamados,
  pior %, mais OS a fazer). As sem pendência (gerando ou sem sol, sem chamado, sem OS a fazer e % ≥ 90) ficam dobradas
  em "+ N usinas sem pendência". A cor da performance é a régua do Gerencial: ≥ 97% verde, ≥ 90% amarelo, abaixo vermelho.
- No menu, logo depois das Ocorrências (a Visão do responsável e as Ocorrências ficam juntas, regra do teste delas). Sem
  o cadastro (o banco fora), a tela abre com o aviso, como as outras do Campo, nunca o erro 500.
- Acesso: a tela é `campo/cliente` em Base › Acessos; tela nova nasce fechada para os setores (só o administrador vê) e
  quem libera para COS, PCM e Performance é o Levi.

Prova (05/11/2026): `tests/test_campo_visao_cliente_0511.py` (13 testes; e 11 quebras de propósito na conta, todas pegas:
média no lugar da soma, sem sol vira gerando, sem leitura vira zero, chamado leva tudo, ordem invertida, dispensado
entra, visita já feita conta, OS de chamado entra, visita de hoje que já passou, tipo sem normalizar, conferência conta
como aberta) e a bancada só leitura com o banco real e o tempo real de produção: a Thopen (81 usinas, 80 com o status
igual ao da Entrada; a que a Entrada não trouxe, "Sem leitura") e a Athon (10 usinas, 101,4%), a 1440 px e a 375 px (a
tabela desliza dentro do quadro; a página não rola de lado).

**O detalhe da usina** (a entrega 2, 05/11/2026, como no mockup): o painel ao lado da tabela (a partir de 1280 px; abaixo
dela na tela estreita, e a página desce até ele sem ficar sob o topo fixo). Abre na primeira usina que pede atenção; o
clique na linha troca o painel sem recarregar e o endereço guarda a escolha (`&usina=`, que só vale para usina DESTE
cliente; a de outro cliente volta para a primeira). Todos os painéis vêm na página (escondidos), da mesma conta: nenhuma
leitura a mais por clique. O painel tem:
- o status e a última leitura do monitoramento; as **paradas abertas** (as OS de parada da disponibilidade, a mesma
  fonte da faixa "Parada agora" da Visão: o escopo, desde quando, o tipo e a OS; sem o código do ativo); a próxima visita;
- **Hoje**, a linha do dia, só com o que a fonte guarda COM HORA: a parada que começou hoje, o chamado aberto na
  distribuidora (o envio; sem envio, quando foi registrado) e o protocolo, os blocos de hoje da programação (um por hora e
  tipo, com a situação pelas tarefas do bloco: em execução, feita, pausada, **não iniciada** quando a hora passou sem
  começar, ou programada; na bancada da Athon, às 18:50, o bloco das 09:00 dizia "programada"). A OS aberta hoje vai no
  fim com "hoje" (o fato das OS guarda o dia, não a hora), e a que já está em conferência diz "aberta e concluída" (na
  bancada, duas OS de religamento abertas no dia já estavam concluídas);
- os chamados na distribuidora de 30 dias, com o protocolo (ou "sem protocolo ainda"), a distribuidora, a UC, quando
  abriu e a situação. **Um protocolo de várias UCs é um item só, com as UCs** (`chamados_agrupados`), e na linha do dia
  uma linha só com "· N UCs": em produção (05/11/2026, Mandaguaçu) a COPEL deu um protocolo para as 4 UCs e o painel
  repetia a mesma linha 4 vezes. A contagem da tabela e do topo segue por chamado, como a tela Acionamentos;
- as OS a fazer com a situação, e a contagem das concluídas em conferência.

Defeito achado e corrigido na entrega 2: o instante do Andamento vem com fuso, e a ordem dos chamados usava o
`datetime.min` sem fuso: um chamado sem `criado_em` derrubava a leitura inteira dos chamados ("sem leitura" na tela).

Prova da entrega 2 (05/11/2026): 23 testes no mesmo arquivo e 21 quebras de propósito, todas pegas (as 12 da entrega 1,
com a equipe de volta ao lugar, e 9 do detalhe: parada, chamado e protocolo de outro dia no dia, o envio ignorado, o
bloco que passou como programada, a OS concluída como só aberta, o bloco "feita" com uma tarefa só, o código do ativo e
a ordem sem fuso); a bancada com o banco real a 1440 px (a tabela de 6 colunas cabe ao lado do painel: 711 px por
dentro do quadro) e a 375 px (sem rolagem de lado; o clique desce ao painel).

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

A OS da PT (verde) abre `/t/campo/pt/<número>?ativo=<código do ativo>`: a linha da PT (tarefa, ativo, técnico,
atividades da APR com sim/não/NA, respostas NÃO, falta, forçada) e a decisão dela. **A decisão é por linha** (decisão 4
do Levi, 11/10/2026): o App decide cada PT × ativo à parte, e a PT de 3 ativos tem 3 linhas e 3 decisões. Todo link à
tela e todo formulário de decidir levam a linha (`ativo` no link, `codigo` no formulário; "" = a linha sem ativo, como a
da APR do dia); a tela da PT de mais de uma linha lista as outras para trocar (`visao.pt_linhas`). **Sem a linha** (link
ou formulário de antes, ou um código que a PT não tem), a PT de uma linha abre a dela e a de mais de uma **só lista os
equipamentos para escolher**, sem formulário; o `decidir` sem a linha também só aceita a PT de uma linha. Na de mais,
escolher a 1ª seria chutar a qual ativo a decisão vale (revisão adversarial de 11/10/2026: a tela abria calada a 1ª e
o formulário mandava o código dela, por fora da recusa do `decidir`).
- **Quem assina: o login do Fracttal do OS Creator** (Levi: "utilize o login do fractal do OS Creator Web que já dá
  certo!"). O OS Creator roda dentro do Nexus com sessão própria (cookie `os_sessao`, só em /os); por isso as rotas de
  assinatura moram em `/os/_nexus/...` (`assinatura.py`): `quem` (o e-mail de quem entrou), `pt/<n>/decidir` (POST) e
  `pt/<n>/voltar` (o OS Creator só devolve para /os depois do login). Token do Fracttal vencido (`exp`) não assina;
  pedido de outro site leva 403 ("Origem recusada."), pela régua da moldura da Performance, a mesma dos POST da Base
  e dos Acessos (`assinatura._de_outro_site`: o `Sec-Fetch-Site` do navegador, só `same-origin`; sem ele, o `Origin`).
  **Não comparar o `Origin` com o `request.host`**: no servidor da T.I. o Nexus não recebe o endereço público no Host,
  e até 30/10/2026 toda decisão pelo navegador levava 403 (uma Responsável UFV, no 1º dia do card de assinar; o mesmo
  POST com `Origin: https://app.gridco.com.br` dava 403 em produção). Prova:
  `test_a_decisao_passa_atras_do_proxy_que_troca_o_host` (falha com a regra antiga).
- **A ida e a volta do login levam a linha** (revisão adversarial de 11/10/2026: só com o número no `next`, quem abria
  a linha do 2º equipamento sem a sessão do Fracttal voltava do login para a 1ª, com o código dela no formulário, e o
  clique seguinte decidia o outro equipamento; num Não autorizo, o App pausaria a tarefa errada). `_login(número,
  código)` põe a linha no `next` (`/os/_nexus/pt/<n>/voltar?ativo=<código>`, que o `_destino_local` do clone aceita) e
  o `voltar` devolve a ela. Levam a linha: o `decidir` sem login (o `codigo` do formulário), o "entre com o seu login do
  Fracttal" da tela (montado no servidor) e o da assinatura do técnico (`assinatura-tecnico?ativo=`, na tela e no
  detalhe da lista do HSEQ). Prova: `test_a_volta_do_login_do_fracttal_traz_a_mesma_linha_da_pt`.
- **Debaixo do `/nexus`** (porta única, 10/10/2026; o servidor até a fase 4, hoje na raiz; com o prefixo, endereço cru cai na
  plataforma de Performance): o `volta` do formulário de decidir é o `request.full_path` da tela, SEM o prefixo;
  `assinatura._volta` confere sem ele (`sem_raiz`) e devolve com ele (`na_raiz`). O `next` do login do OS Creator
  (`_login`) vai sem o prefixo (é o caminho que o clone entende) e o endereço do login, com ele. A aprovação de OS chama
  o clone com `request.url_root` (o cookie que o clone renovar fica no `/nexus/os`). Todo redirecionamento à lista
  (`TELA_PT`) passa pelo `na_raiz`. Prova: `tests/test_prefixo_sair_fracttal.py` e `tests/test_prefixo.py`.
- **Fica salvo:** `nexus_pt_decisoes · fato_decisao_pt` (`nexus/campo/decisao_pt.py`; registrado no `catalogo.py` como
  `decisao_pt`, com o contrato). Grão: 1 linha = 1 decisão sobre 1 linha da PT: as colunas de 05/10 e o `codigo_ativo`
  (o Código do ativo da linha no `pt_app_campo`) e a **`assinatura`** no fim. Pessoa só como HMAC do e-mail
  (`decidida_por_hmac`, o mesmo código do App); motivo mascarado. **Assinatura** (prova do contrato, 11/10/2026: sem ela o
  App v257 leu as duas decisões e não aplicou nenhuma): HMAC-SHA256 com a `NEXUS_PESSOA_HMAC` do texto
  `decisao_pt|pt|codigo_ativo|os|decisao|decidida_em|decidida_por_hmac|motivo` (`decisao_pt.assinatura`, a mesma conta do
  `_nexus_pt_assinatura` do App; mudou num, muda no outro). O primeiro que decide a linha vale: linha que já tem decisão
  do Nexus, ou que o livro do App já mostra decidida, recusa — **menos quando o App recusou a decisão do Nexus**: o App
  escreve no `pt_app_campo` "Decisão do Nexus" = recusada, "Decisão do Nexus em" e "Motivo da recusa"; se nenhuma decisão
  daqui for mais nova que a recusa, a tela mostra o porquê e libera uma decisão nova (`decisao_pt.recusada_pelo_app`). A
  aba `decisoes` de antes (nunca gravada) não é lida.
- **Quem pode decidir** (Levi, 09/10/2026): o Supervisor de Campo da região da usina (com a vaga aberta, o
  Coordenador), o gestor de contrato da usina, quem tem o vínculo COS no cadastro e um administrador do Nexus
  (`decisao_pt.aprovadores` / `pode_decidir`, conferido no `decidir`; a recusa diz quem pode). **Desde 30/10/2026, o
  Responsável UFV da ficha da usina** (`usinas.responsavel_om_id`, papel "responsável UFV", o 1º da lista de quem
  pode): é a quem o App manda o aviso e a assinatura da PT desde a v314 (30/10, 04:39Z). A pessoa é a do login
  do Fracttal, achada no cadastro pelo e-mail ou pelo nome de UMA pessoa. **Quem pediu a PT nunca a decide**, nem sendo
  administrador: `pode_decidir` compara o código do e-mail de quem assina com o `solicitante_hmac` da linha e, desde
  11/10/2026, também a pessoa do cadastro (`solicitante_pessoa_id`: quem tem um e-mail no Microsoft e outro no Fracttal
  passava)
  (`visao.pts`, o `Solicitante (HMAC)` do `pt_app_campo`, o mesmo código que o App compara). É a regra do painel do App
  desde a 1ª PT real (28/09/2026, aprovada pelo próprio técnico, que também era administrador); o App descarta calado
  a decisão de quem pediu e, como só a 1ª decisão de cada linha vale, a de outra pessoa gravada depois também nunca
  chegaria ao campo (revisão adversarial de 11/10/2026: a supervisora que pediu dava o De acordo, o Nexus dizia
  "salva", o gestor de contrato era recusado com "já tem decisão" e o técnico ficava esperando). Prova:
  `test_quem_pediu_a_pt_nao_a_decide`.
- **Quem aplica é o App, a partir da v257** (pronta numa cópia do middleware; o deploy é do Levi): um timer de 2 em 2
  minutos lê `nexus_pt_decisoes · fato_decisao_pt` (GET aberto) e aplica como o painel dele (o mesmo status, a validade
  de 7 dias a partir da decisão, o PDF anexado no De acordo e a pausa no Não autorizo). As regras dele: (1) vale a 1ª
  decisão de cada PT × `codigo_ativo` (a mais antiga do livro; as outras nunca são aplicadas), decisão aplicada não se
  desfaz e, se o painel decidiu antes, vale a do painel; (2) a linha é achada pela PT, pelo `codigo_ativo` e pela OS, e
  tem de ser uma só; (3) quem pediu a PT não a decide; (4) decisão com mais de 7 dias não é aplicada; (5) **quem pode
  decidir o App NÃO confere** (não tem os papéis da estrutura de O&M): a única trava é o `pode_decidir` do Nexus. Por
  isso o Nexus recusa, antes de gravar, o que o App descartaria e já se sabe na hora (a linha, quem pediu, a 1ª
  decisão): decisão gravada que o App descarta trava a linha aqui e deixa o técnico esperando. Até a v257 entrar no ar, a
  tela diz: "O App ainda não lê esta decisão". Falta no App: mandar a PT ao banco na hora em que nasce, não só no timer
  de hora em hora (hoje a PT chega ao Nexus com até 1 h de atraso).

### O card de assinar a PT (30/10/2026)

Pedido do Levi, pelo chat do App de Campo: "a parte de abrir PT e assinar no e-mail automático deve encaminhar para o
Nexus para eles assinarem por lá ... um layout próprio como se fosse um card no meio da tela dando um blur no fundo e o
supervisor pode assinar, ao assinar ele vê também se tem mais alguma aberta para alguma usina dele".
- **O endereço é contrato com o App** (não muda): `/t/campo/pt/<número>/assinar?ativo=<Código do ativo>` (rota
  `pt_assinar`, template `pt_assinar.html`), o botão do e-mail de PT aguardando da v315, atrás de um interruptor do
  App. O `ativo` vem sempre (vazio = a linha sem ativo); sem ele, a PT de mais de uma linha só lista os equipamentos,
  como a tela da PT. Debaixo do `/nexus` também abre (`https://app.gridco.com.br/nexus/t/campo/...`).
- **O card**: por cima do Nexus desfocado (o véu e o blur da janela da Visão do responsável), uma superfície só, feito
  para o celular (no estreito o card desce até o fim e o fundo rola; botões e linhas com 44 px). Mostra quem pediu,
  quando e há quanto espera, a OS, a tarefa, a usina, o ativo, as atividades críticas e os itens marcados NÃO.
- **Os itens NÃO**: a coluna `Itens NÃO` no fim do `pt_app_campo` (pedida ao App em 30/10: os títulos dos itens
  respondidos NÃO, separados por "; ", sem texto livre; `visao.pts` → `itens_nao`). Sem ela, a contagem
  (`Respostas NÃO`), como antes.
- **A decisão é a de sempre** (`/os/_nexus/pt/<n>/decidir`, o login do Fracttal do OS Creator): o formulário leva
  `volta` (o card, sem o prefixo) e `card=1`; sem o login do Fracttal, o script troca os botões por "Entrar com o
  Fracttal para assinar", e o login volta ao card (`assinatura._login(..., card=True)`, `voltar?...&card=1`). O Não
  autorizo pede o motivo antes (o 1º clique abre a caixa).
- **Quem pode** é conferido com a pessoa da sessão do Nexus (a conta Microsoft; o e-mail é o mesmo do Fracttal, que o
  portão de setor já usa), e o `decidir` confere de novo com a do Fracttal. Quem não pode lê o porquê, sem botão; quem
  o Nexus não acha no cadastro lê também que falta o e-mail na ficha. Medido em 30/10: 6 dos 7 Responsáveis UFV sem
  e-mail na ficha, achados pelo nome (o do e-mail, fulano.souza@); os 5 que o App passou a avisar na v314 são achados e
  estão no setor Supervisão Campo, que abre o card.
- **Depois** (assinada, decidida antes ou sem permissão): "Outras PTs esperando nas suas usinas", da mais antiga para a
  mais nova, cada uma no próprio card (`decisao_pt.assinaveis`: as linhas esperando que a pessoa pode decidir, sem as
  que o Nexus já decidiu, menos a que o App recusou). Sem nenhuma: "Nenhuma outra PT esperando nas suas usinas".
- **A PT que acabou de nascer**: o App publica o livro antes do e-mail (v315), mas a cópia do Nexus é de 5 min; o card
  que não acha a PT relê o livro na hora, no máximo uma vez por minuto (`_RELIDA_PT`).
- Prova: `tests/test_campo_pt_assinar.py`. Bancada de 30/10 (dados reais, só leitura, decisão só na memória): 39 PT
  esperando, 38 com o Responsável UFV na ficha; De acordo e Não autorizo de ponta a ponta, a lista das outras, e o
  celular a 375 px sem rolagem lateral.

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
- **15/10, App v269 (código `024648983354f613`, o mesmo do `/api/health` do App às 00:40; a pasta já tinha até a v274,
  que não mexe no fecho):** o teste acusou `_foto_campo_descrita`, nome novo puxado pelo `_contar_fotos`. A v269
  (14/10) mudou a régua da nota em quatro pontos: a foto de campo vale como descrita pela `nota` que o App novo manda à
  parte (o "campo — nota" cortado em 80 caracteres levava a nota inteira em campo longo); `_v2_pede_foto` lê também o
  `fotoReq`, que é como o celular manda (antes a foto pedida nunca disparava); o "não se aplica" não pede foto; e TODO
  campo de texto preenchido conta como observação, não só os com "observ" ou "coment" no nome. Decisão: recópia
  inteira, nada em `FORA` (nada de Azure). **As telas não mudam:** só `_qualidade_os` e `_qualidade_v2` alcançam o
  que mudou, e no Nexus só o `nota_fracttal.py` (o coletor aposentado) as chama; o fecho das raízes da Aprovação e da
  Triagem (74 nomes) é a mesma árvore de código na cópia velha e na nova. Elas mostram a nota que o App grava, e essa
  segue a régua nova sozinha. No `nota_fracttal.py` o item ganhou o `fotoReq` do tipo 9: o `work_orders_subtasks` do
  REST não traz o `attachments_required` (medido em 15/10, 1 GET fora do horário de campo), e a spec do fabricante
  mora numa tabela do App (o porquê na docstring dele).
- **03/11, App v317 (código `3451c2ca3893f6eb`, o mesmo da pasta `app-campo-v317`):** o teste acusou só a assinatura
  do `fx` (as 80 copiadas iguais). A v317 pôs no `fx` do App a reserva da cota para os registros dos técnicos: a leitura
  de fundo é adiada (levanta `FxLimite`) quando a cota está na reserva, cada pedido é contado, e o 429 só espera e tenta
  de novo no pedido crítico. Decisão: **o substituto fica.** É controle de ritmo do processo do App, não conta: o pedido,
  a resposta e o `ApiError` são os mesmos; o Nexus tem o próprio teto (`casca/fracttal_conta.py`: 150 dos 200/min, 90 no
  fundo, sobrando 50 para o App e os robôs) e o `fx` dele segue levantando `fracttal.Recusado`, nunca `FxLimite`.
  Recópia pelo extrator: muda só o cabeçalho, a assinatura e dois imports da biblioteca padrão que a cópia não usa.
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
  - **Sem rajada e sem reler a cada deploy (13/10/2026)**: com o deploy automático, cada push reinicia o servidor. A
    releitura saía em 6 de uma vez (no teto de 4 por segundo do `fracttal.py`: ~60 páginas em ~15 s, acima dos 200 por
    minuto da empresa: o 429 do App, do OS Creator e das fotos), ao subir e a cada 10 min com alguém em Rondas ou
    Aprovação. Agora sai `paciente` (2 de uma vez, 1 min de pausa depois de uma recusa), e a última fila boa fica em
    `dados/campo/fila_aprovacao.json.gz` (com a hora da leitura; a OS aprovada pelo Nexus sai dela também): o boot a
    põe na memória em toda máquina, sem Fracttal, e o `aquecer` só relê se ela tem mais de 10 min. Prova:
    `tests/test_subida_sem_rajada_13_10.py`.
  - **O gargalo** (Levi, 05/10: "por que demora se o histórico do OS Creator carrega tão rápido?"): o REST do Fracttal
    entrega no máximo 100 tarefas por pedido (limit=1000 devolve 99) e a fila tem ~5.500, então são 55 páginas de
    ~1,1 s; até 05/10 saíam uma por vez com 0,5 s de folga (~90 s). O histórico do OS Creator pergunta outra coisa: o RPC
    com o login da pessoa, com período e "criado por" filtrados no servidor (poucas OS). Agora `fracttal.py` deixa 4
    pedidos ao mesmo tempo, no máximo 4 por segundo, e em segundo plano tenta de novo depois de um 429 (5 s, 10 s); a
    fila é lida ao subir o Nexus (`aprovacao.aquecer`, 20 s depois; `NEXUS_CAMPO_AQUECER=0` desliga). Medido: fila
    inteira em ~20 s.
  - **A fila INTEIRA, sem período** (Levi, 08/10: "não deve ter filtro 'OS fechadas nos X dias' ... ficar preso nessa
    visão é foda"): a conta do App (`aprovacao.fila_toda`; a cópia devolve 200 linhas por chamada e as páginas são
    juntadas) só conta por janela, e `aprovacao.FILA_INTEIRA` = 3650 dias (o teto do `_janela`) pega toda OS em
    verificação. **Contada por OS** (05/10: "ele não consegue aprovar uma tarefa em si, e sim uma PT ou uma OS";
    `_por_os`): a espera é a da tarefa mais antiga, a nota é a pior. A criação é o `creation_date` da OS, que vem na mesma
    linha do REST; datas em Brasília (o Fracttal fala UTC). Medido em 05/10 (90 dias): 1.827 OS e 4.736 tarefas.
  - **O quadro por fatos (05/11/2026)** (Levi, 04/11: "No nexus, em campo app crie uma aba de aprovação de OS. Pode fazer
    por cima da aba Aprovação de OS, refaça com essas regras e deixe algo bem fácil e dinâmico para os supervisores!"; no
    quiz: todos os supervisores veem; "uma a uma pelo card, tem que ter um botão de aprovar logo após todo o score e
    avisos, deve ser possível também aprovar mais que uma de uma vez!"; três colunas). A lista por usina, os seis
    indicadores e a barra da idade (18/10) saíram; o endereço velho (`ver=`, `por=`, `balde=`, `idade=`, `vista=`) abre
    o quadro. Desenho: `docs/superpowers/specs/2026-11-05-aprovacao-por-fatos-design.md`.
    - **As colunas** (`nexus/campo/prefiltro.py`, `classificar`; medidas nas 30 OS de 26/10, relatório "Pré-filtro da
      Verificação: fatos primeiro"). **Não OK**: foto anexada mais de `NEXUS_PREFILTRO_HORAS_TARDE` (24) h depois do
      último fechamento da OS no App; pegou 4 devolvidas e nenhuma aprovada. A anexação é o `Last-Modified` do arquivo no
      S3 (o REST de anexos não dá data); o fechamento, em cada linha do `qualidadelog` da OS, a maior entre a hora do
      celular (`dev_ts`) e a da chegada no servidor (`server_ts`), e a última das linhas (`fechado_app` na conta pronta;
      sem ela, a anexação não é julgada). A chegada conta porque o celular sem sinal sobe o fechamento e as fotos juntos
      dias depois (era Não OK falso). Só as fotos das tarefas do App são julgadas, pelo id da tarefa: na OS mista, a tarefa
      fechada fora do App tem as fotos anexadas na hora dela. **Em dúvida**: foto repetida (dHash de 256 bits dos 75% de
      cima, SEM o carimbo do App, que muda a cada anexo; diferença até `NEXUS_PREFILTRO_DIF` 12; captura de tela, sem
      "GPS " na descrição, só até `NEXUS_PREFILTRO_DIF_PRINT` 4, porque telas parecidas enganam), tarefa fechada fora do
      App ou foto que não abriu no Nexus (upload cortado). **Pronta**: nenhum fato. A OS fica na pior coluna; um fato
      com fotos ainda por ler já a põe na coluna pior, com "Faltam fotos por ler"; sem fato e sem as fotos lidas, ela
      fica em **Ainda conferindo** (abaixo do quadro: aprova pelo cartão, não entra no lote). A regra do App de antes
      (nota abaixo de 80, já devolvida, foto divergente, ronda; `aprovacao.motivos`) virou só aviso, sem mudar a coluna.
      "Menos de 5 min no App" e "subtarefas respondidas" não separaram na medição e ficaram de fora.
    - **Fora do pré-filtro** (abaixo do quadro, com o motivo; aprova pelo cartão; **não entra na conta** das OS
      esperando, Levi 05/11/2026: "O que tiver fora do pré filtro não é contabilizado"): religamento, pelo tipo ou pela
      tarefa, e a etiqueta PERFORMANCE (Levi, 04/11: "religamento remoto ou religamento real não entra, nem OSs com
      etiqueta de performance!"); a etiqueta CHAMADOS e as OS criadas pelo COS, como nas OSs em verificação do Painel.
      **A ENGENHARIA entra no pré-filtro** (Levi, 05/11/2026: "Engenharia entra no pré filtro"; `prefiltro.ETIQUETAS_FORA`
      olha todas as etiquetas da OS); no Painel ela segue de fora (`verificacao.etiqueta_fora`, a regra de 29/10). Com
      isso a leitura de fundo passa a conferir também as OS da Engenharia (um GET por OS). Quem é do COS vem da última
      conta (`verificacao.cos_guardado`, a da volta).
    - **As fotos, por trás** (`nexus/campo/prefiltro_fundo.py`): depois de cada releitura da fila (`aprovacao._reler`) e
      no boot com a fila do disco (`_preparar`), uma thread `nexus-prefiltro` declarada de fundo no porteiro confere as
      OS do escopo sem fatos (ou cujas tarefas mudaram), a mais nova primeiro: UM GET de anexos por OS no Fracttal
      (`work_orders_attachments?folio=`, 100 por página) e as imagens pelo S3, fora da cota de 200/min; no máximo
      `NEXUS_PREFILTRO_POR_VOLTA` (150) OS por volta e `NEXUS_PREFILTRO_PAUSA_S` (2) s entre elas (também depois de um
      erro); o 429 para a volta e guarda o que leu. **A OS conferida é relida** (revisão de 05/11/2026): ela é lida
      minutos depois de entrar na verificação, e a foto anexada dias depois só existe depois; relê uma vez quando a janela
      de 24 h desde o fim no Fracttal fecha e, depois, uma vez por dia enquanto espera, baixando só as fotos novas (o id é
      o caminho no S3). As OS novas passam na frente das relidas. Foto que não baixou deixa a OS sem fatos (meia leitura
      nunca vira Pronta); três falhas seguidas e ela espera 6 h. Foto que baixou e não abre fica "não abriu", sem hash.
      Fica o hash, a hora de anexação e o campo, nunca os bytes. **Sem miniatura** desde 05/11/2026 (Levi: "nem
      precisa mostrar a foto de cara não... pode mostrar o nome das fotos e se a pessoa clicar ela vai abrir o card da
      OS"): a imagem ainda é baixada, porque a repetida compara a própria imagem (a mesma foto em dois campos ganha nome
      e carimbo diferentes), mas não se guarda miniatura e a rota `/t/campo/aprovacao/foto/<id>` saiu; as miniaturas de
      antes (`dados/campo/prefiltro_fotos/`) saem quando a OS deixa a fila.
      Memória e `dados/campo/prefiltro.json.gz`, gravada a cada 10 OS (cada push reinicia o servidor); a volta carrega o
      disco antes de ler, a OS que sai da fila sai dali com as miniaturas e a fila vazia (soluço) não apaga nada. Medido
      nas 476 fotos da medição: 10 ms de CPU e 144 KB por foto, 16 fotos por OS. **Onde roda** (`prefiltro_fundo.ligado`):
      `NEXUS_PREFILTRO` decide quando dito (0 desliga); sem ele, segue o `NEXUS_CAMPO_AQUECER` (o servidor lê, o PC não;
      a cópia de prova põe 0). **A visita só lê memória** (nem Fracttal, nem banco, nem S3).
    - **O cartão** (2ª rodada, 05/11/2026: o modelo do cartão do Quadro da equipe da Engenharia, "porém com o botão
      aprovar"; a coluna e o cartão com o fio na cor da coluna, o cartão na superfície 2), nesta ordem: no topo a OS em
      **verde Grid, sem sublinhado** ("tire esse underline estranho!"; abre o card do OS Creator, `NexusOsCard.abrir`,
      status "Em Verificação") e os dias; logo abaixo o **motivo da coluna em destaque** (`apq-motivo`: "Sempre destacar
      o motivo de estar em dúvida ou não OK! tem que estar bem visual e acessível"): o fundo e o fio na cor, o ícone e a
      palavra NÃO OK ou EM DÚVIDA (a cor nunca sozinha) e os fatos que puseram a OS ali (`prefiltro.TIPOS_DO_MOTIVO`:
      tarde, repetida, não abriu, fora do App), com a prova (da repetida, o nome das duas fotos, o número e o campo,
      que abre o card da OS, como no Histórico do OS Creator); em Fora do pré-filtro e
      Ainda conferindo, o mesmo bloco, neutro, com o motivo; depois a tarefa (a 1ª, "e mais N"), o ativo, a UFV e o
      cliente; o **score** (a nota do App, a pior das tarefas; "Fora do App" sem ela); os outros avisos (a regra do App,
      as fotos por ler); no pé o técnico (as iniciais), as tarefas e quando as fotos foram conferidas; e logo depois o
      **Aprovar** = o Concluir do OS Creator (`POST /os/api/os/<id>/concluir` com
      `{folio}`, a rota do Painel do responsável e do OS Creator Web: status 3 + recalculate + reconferência da data de
      fim), com o login do Fracttal de quem clica; IRREVERSÍVEL, pede confirmação; o 401 vira "Entre no OS Creator com a
      sua conta do Fracttal". Aprovada só com `ok: true` na resposta: sem a sessão do Nexus, o portão dá 302 para /entrar
      e o fetch recebe 200 em HTML, que NÃO é aprovada ("A sua sessão do Nexus acabou"). A conferência
      (`POST /t/campo/aprovacao/<id>/conferir`: só sai da fila guardada o que o Fracttal já não tem em verificação, 1
      pedido de leitura; ninguém esconde OS da fila) tira o cartão, e a cópia da fila em disco é regravada uma vez por vez
      (`aprovacao._regravar`: a que chega durante outra só marca que falta). A leitura (a fila de verificação, a hora em
      que foi lida, as notas do App e quantas OS tiveram as fotos conferidas) fica no "!" amarelo do título, não no canto
      (Levi, 05/11/2026: "pode deixar no disclaimer da exclamação em amarelo").
    - **O lote**: caixa de marcar só em Pronta e Em dúvida (não na OS com "Faltam fotos por ler", que pode virar Não OK),
      "Selecionar todas" por coluna e "Aprovar as marcadas (N)", com a confirmação que diz quantas e de que coluna. Uma OS
      a cada 4 s (`PAUSA_LOTE_MS`: cada aprovação custa 5 a 7 pedidos ao Fracttal), com o andamento; para no que se
      repetiria em todas (401 do Fracttal, 403, 429 e 5xx, a sessão do Nexus e 3 erros seguidos), e o outro erro fica no
      cartão e o lote segue. O quadro é montado na visita e não muda sozinho na frente da pessoa.
    - **Prova no Fracttal de verdade (05/11/2026)**: a OS 18630 (TESTE - PA, TESTE100-CHSC1), criada pela rota da OS
      tradicional com 3 fotos (duas iguais), posta em Em Verificação e lida numa cópia local do código novo (a fila só com
      ela, sem ler a fila inteira no horário de campo): caiu em Em dúvida com "Foto repetida: p03 é a mesma imagem de p01"
      (as duas miniaturas baixadas do S3) e "fechada fora do App"; o Aprovar do cartão concluiu, a conferência tirou o
      cartão e o REST leu de volta o status 3. Para pôr uma OS de teste em verificação: a OS "já realizada" com
      `to_in_review` nasce Em Processo (o Fracttal ignora calado); vale `api.mudar_status_os(wid, 2)` na sessão de quem
      entrou (rota de prova só da cópia).
    - **Pendente** (05/11/2026): o veredito no banco (o fato `fato_prefiltro_os`, a medida da sombra contra a decisão do
      supervisor; a Task 6 do plano); e, para as capturas de tela do mesmo layout (que só mudam os números), um hash maior
      (32×32), a medir nas 30 OS antes de mudar a regra.
    - **Filtros**: o Responsável O&M da usina vai ao servidor (`responsavel=`, "*" = todos; quem entrou pelo Fracttal e é
      responsável já vem nele, `_responsavel_logado_pelo_cadastro`; o responsável e o cliente vêm do cadastro pela usina
      do Fracttal, `visao.usinas_do_fracttal`); cliente e busca (OS, UFV, técnico, sem acento) filtram na página e
      recontam as colunas. CSV: OS, dias, criação, fim, Responsável O&M, usina, cliente, técnicos, tarefas, nota do App,
      a coluna ("Fora do pré-filtro (motivo)") e os motivos. No celular as colunas deslizam de lado dentro do quadro.
      Prova: `test_campo_aprovacao_responsavel.py`, `test_campo_aprovacao_visual_0511.py` (a 2ª rodada),
      `test_campo_prefiltro.py` e `test_campo_prefiltro_fundo.py`.
  - **A conta pronta (18/10/2026, "Está demorando muito para carregar")**: a regra do App sobre a fila inteira leva uns
    3,5 s só de conta (medido em 18/10 com uma fila falsa de 5.500 tarefas), mais a leitura das notas no banco, e a
    cópia de 5 min (`leitura.ler`) vencia entre uma releitura e outra: quase toda visita pagava, e cada filtro de região
    fazia a sua. Agora `aprovacao.fila_toda` guarda a conta da fila inteira até a fila mudar (`_PRONTA`, pela hora da
    leitura), feita logo depois da releitura e ao subir com a fila do disco (`_preparar`), e a tela filtra sobre ela. A OS
    que sai da fila (`tirar_da_fila`) sai da conta pronta também. Prova: `test_a_visita_nao_refaz_a_conta_da_fila`.
  - **O portão do Aprovar do Nexus saiu (18/10/2026, Levi: "pode tirar a rota antiga!")**: de 08/10 a 18/10 o Aprovar
    chamava `POST /os/_nexus/aprovacao/<id>/aprovar`, que só deixava o Supervisor de Campo da região da usina ou um
    administrador; a rota, o `aprovar_os.py` e a conta de quem aprova por região saíram do servidor. Desde então aprova
    quem o Fracttal deixar, pelo Concluir do OS Creator (o do cartão, acima). O papel de quem entrou pelo Fracttal, que as
    outras telas usam para vir filtradas, mora em `papel.py`. **Até 08/10 o script desta tela não rodava** (um
    `confirm()` com quebra de linha dentro da string): um teste roda `node --check` no script.
    **Cuidado com a cota:** cada reinício do Nexus relê a fila (55 páginas; as rondas aprovadas vêm do arquivo desde 06/10); em 05/10, com
    muitos reinícios seguidos, o Fracttal passou a recusar (429). Em desenvolvimento, `NEXUS_CAMPO_AQUECER=0`.

## Peças em `nexus/campo/`

- `visao.py`: as contas nossas (acima), sobre os fatos (`_fato`, `_rondas_ligadas`, `pts`, `_ultima_os_por_usina`) e
  a validação por foto (`validacoes_por_foto`). `decisao_pt.py`: a decisão da PT no banco (acima).
- `responsaveis.py`: a Visão do responsável (acima): `Nomes`, um leitor por fonte, os alertas e a linha de cada bloco,
  `montar`, `bloco`, `soma`, e os leitores das janelas (`serie_diaria`, `tabela_meta`, `disp_diaria`,
  `os_disponibilidade`); desde 18/10/2026, a Limpeza (`limpeza`), as paradas abertas (`paradas_abertas`) e o bloco
  Manutenção (`manutencao_fonte`, `alertas_manutencao`, `linha_manutencao`, `com_manutencao`, `limite_do_pedido`).
- `central_usina.py`: a Central da usina (04/11/2026, acima): a busca, os técnicos, as ocorrências e a Segurança da
  usina escolhida; o resto é a linha dela na Visão.
- `visao_cliente.py`: a Visão do cliente (05/11/2026, acima): o recorte por `cliente_id`, o status pelo tempo real,
  as OS, os chamados e a próxima visita por usina, os 5 números e a ordem; a leitura do tempo real pela ponte.
- `relatorio_usina.py`: o relatório da usina em PDF para o cliente (04/11/2026, acima): os meses, os temas, os dados
  das telas donas e o PDF (reportlab, a paleta e a fonte dos outros relatórios).
  `manutencao.py`: a conta pura do bloco Manutenção. `tarefas_os.py`: o laço que lê as tarefas das OS do Fracttal e
  grava o `nexus_os` (acima); desde 31/10/2026 é também o leitor de OS que a lista central do OS Creator usa (as mesmas
  funções e a mesma paginação, e a volta entrega a ela as abertas que leu; regra no `nexus/dados/CLAUDE.md`). `responsaveis_graficos.py`: a geometria dos gráficos das janelas (SVG).
  `chamados_acompanhamento.py`: os chamados de garantia no banco (acima). `ocorrencias.py`: as ocorrências com plano
  de ação (o livro `nexus_ocorrencias`, acima). `zeladoria.py`: a Zeladoria (acima), pura: as leituras, a zeladoria
  do Fracttal pelas três tarefas, as recomendações, a evolução por cliente, a situação, os números e a fila.
- `livros_app.py`, `fonte_pg.py`, `tabelas.py`: os livros do App no formato que as regras copiadas consultam
  (`query_entities`, `get_entity`); erro de leitura fica anotado e vira aviso.
- `aprovacao.py`, `triagem.py`: as telas pelas regras copiadas (`aprovacao.os_na_fila` e `tirar_da_fila` servem à
  conferência da OS que o card aprovou, `aprovacao_conferir`). `leitura.py`: cópia de 5 min e `limpar_cache()` (que também
  recarrega a cópia das regras).
- `pessoas.py`: `identidades.json` e a tabela dos tokens só na partição `cadastro`.
- `nota_fracttal.py`, `coletor.py`, `banco_campo.py`: o caminho do coletor aposentado.
- `fracttal.py` e o **porteiro do Fracttal** (31/10/2026): cada pedido do `ler` tira a vez no porteiro do Nexus ANTES de
  pegar uma das 4 `_VAGAS` (`fracttal_conta.reservar_vez()`), e os laços do Campo que leem o Fracttal por trás se
  declaram fundo no alvo da thread (`fracttal_conta.de_fundo`: `nexus-tarefas-os-banco`, `nexus-chamados-banco`,
  `nexus-fila-fracttal` e `nexus-ronda-checklist`); laço novo que lê o Fracttal se declara do mesmo jeito, senão conta
  como clique. Regras em `nexus/casca/CLAUDE.md`, "Pedidos ao Fracttal: o contador e o porteiro".

Telas: `templates/campo/*.html` + `static/campo.css`; filtros pela URL.

Prova: `tests/test_torre_campo.py` (nenhuma tela com Azure, moldura ou "Abrir no App"), `test_campo_responsaveis.py`
(a Visão do responsável), `test_campo_ocorrencias.py` (as ocorrências com plano de ação), `test_campo_visao_cliente_0511.py` (a Visão do cliente), `test_campo_chamados_acompanhamento.py` (os chamados no banco), `test_campo_visao.py` (as
contas nossas, a Central em três visões e a aprovação da PT com o login do OS Creator, banco falso), `test_campo_ronda_avulsa.py` (lançar, cobertura, selo, recusas, anulação, catálogo; 08/10: vala do App, sensor em três estados, anulação sem dia nem usina, o caminho de gravação que a importação usa), `test_campo_importar_avulsas.py` (a importação da validação por foto com planilha sintética: de-para exato, data mais recente, "Sem foto", a pessoa que tem de ser uma ficha com e-mail, gravação, conferência linha a linha, idempotência, fora do fato de ronda), `test_campo_rondas_pedido_0810.py` (Rondas de 08/10: colunas e dica da duração, Fotos na tabela, nunca tiveram ronda, Sem ronda, criticidade, Quem ronda em blocos com as pendentes, Painel), `test_campo_sujidade.py`, `test_campo_zeladoria_semanal.py` (a Zeladoria de 26/10/2026), `test_campo_regras_app.py`, `test_campo_aprovacao.py`, `test_campo_fila_rapida.py`,
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
