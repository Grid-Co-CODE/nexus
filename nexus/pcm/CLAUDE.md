# CLAUDE.md — PCM (programação semanal e Gestão PCM)

A programação semanal do PCM dentro do Nexus. O desenho e as etapas estão em
`docs/superpowers/specs/2026-09-30-pcm-no-nexus-design.md`; leia antes de mexer. A tela Gestão PCM (acompanhamento das
manutenções) tem seção própria abaixo.

**Regra de ouro:** o sistema atual segue no ar e intocado até o Nexus bater número a número com ele. Isso vale para o
gerador no PC do programador do PCM, o robô do GitHub, o painel pcm.gridco.com.br e o `banco_dados.json` que o App de Campo lê.
**A troca (Levi, 09/10/2026: "semana que vem já quero full nexus sem falta"):** a partir da W43 o Nexus gera E publica.
Gerar continua sendo sombra (não muda nada no campo); a semana só vai ao App pelo **Publicar no App** da rodada (seção
abaixo), um passo à parte, com a tela de conferência. Duas publicações da mesma semana (o PC do PCM e o Nexus) se
atropelam: na semana da troca, o PC do PCM não publica.

**O fluxo da semana, do Gerar ao App** (o que responder a "após a sombra, o que acontece?", Levi, 16/10/2026):
1. **Gerar a semana** (bloco 3): o Nexus roda o motor do PCM com os insumos e as observações da semana e grava uma
   rodada (a "sombra": a planilha `saida/sombra.xlsx` e a conferência). Nada vai ao campo.
2. **Revisar**: a rodada abre no Quadro da semana como "rascunho do Nexus"; o que mudar vira linha nas observações da
   semana (pelo Quadro ou pelo bloco 2) e vale na PRÓXIMA geração: gera de novo. Cada geração é uma rodada nova, e o
   Quadro mostra a mais recente.
3. **Publicar no App** (o botão da rodada, com a tela de conferência): manda a `Programação Semana NN.xlsx` e o
   `Observacoes_Semana.txt` ao repositório do PCM, relê e confere, e põe o plano na reserva do histórico.
4. **O robô do PCM** roda com o push (5 a 10 min) e regrava o `banco_dados.json`; a semana vira a do App na segunda
   (ele escolhe a semana ativa pela data). Na semana em curso, o robô roda a cada 15 a 30 min (OS nova, ajustes do
   `Observacoes_Semana_Atual.txt` que o Quadro grava, rolagem).
**Quem pode (16/10/2026, Levi: "mude as configurações para administradores e pessoas do setor de PCM conseguir gerar uma
programação semanal!" e, sobre gerar e as observações, "tanto PCM quanto supervisores! Vou criar um setor de
Responsáveis UFV"):** Gerar a semana e o Quadro da semana são telas de DOIS setores, o PCM e o Responsáveis UFV
(`do_setor=("PCM", "Responsáveis UFV")`, pelo nome, sem acento nem caixa: quem é deles as vê sem marcar em Base →
Acessos; os outros setores, só se marcadas); dentro delas, gerar e mexer nas observações é de quem abre a tela;
publicar no App e gravar a reprogramação do Quadro é do administrador ou de quem é do setor PCM (`telas.pode_programar`,
pelo setor da pessoa do login): os supervisores montam a fila e copiam para o PCM. Testes: `test_o_setor_pcm_gera_e_publica`
e `test_o_setor_pcm_grava_a_reprogramacao`.

**A programação publicada também está no banco (08/10/2026):** o `banco_dados.json` vira o fato
`nexus_programacao · fato_programacao` (1 linha = 1 bloco de agenda), que a carga de hora em hora mantém pela mescla por
semana (o arquivo guarda só 4 semanas); as semanas antigas, desde a W21, vieram do histórico do git do PCM
(`ferramentas/carregar_programacao_historica.py`). Só lê o arquivo do robô, não muda nada desta pasta. Regras, a versão
escolhida de cada semana e os números: `nexus/dados/CLAUDE.md`.

## Os módulos

| Arquivo | O que faz |
|---|---|
| `fonte.py` | lê o `banco_dados.json` do App (a semana que está valendo) e, para a Gestão PCM, o `gestao_pcm.json` e o `mpas.json`; cópia de 5 min e, passado isso, confere pelo ETag (304 = segue a cópia, sem baixar de novo) |
| `gestao.py` | as contas da Gestão PCM (Plano & Fila), transcritas do `js/preventivas.js` do painel |
| `prova_gestao.py` + `.js` | a prova de que a Gestão PCM bate célula a célula com o painel (roda o JS dele no node) |
| `semana.py` | as regras da semana que as telas Tarefas e OS, Quadro e Gerar usam: achar a semana, dia, situação, fora da jornada, filtros (a tela Semana saiu em 12/10/2026) |
| `geracao.py` | roda o motor numa pasta por rodada, num subprocesso, a 1 pedido por segundo ao Fracttal; depois do motor, tira da planilha as tarefas do `sem:` das observações (`aplicar_sem`, 15/10/2026: o motor só o aplica nas OS de plano; seção do Quadro); `gerar_com_foto`, o mesmo com a FOTO do Fracttal e sem credencial (a prova) |
| `insumos.py` | os insumos do motor guardados no Nexus, escritos na rodada no formato que o motor lê |
| `historico_banco.py` | o histórico das programações que o motor lê, montado do `fato_programacao` do banco (desde 08/10/2026); o plano publicado da semana em andamento vem da reserva, do REPOSITÓRIO do PCM ou da pasta do PCM |
| `comparar.py` | compara a semana do Nexus com a oficial (a do PCM), linha a linha; `conferir`: a conferência da semana gerada (dentro da semana, horas por equipe e dia, fora da jornada, repetidas, e `excede_hh_os`: a OS cuja corretiva o motor forçou além das horas do dia) |
| `publicar.py` | **Publicar no App** (09/10/2026): a planilha e as observações da rodada vão para o repositório do PCM, conferidas relendo, e o plano vai para a reserva do histórico |
| `quadro.py` | **Quadro da semana** (09/10/2026): a semana em colunas por dia, a janela da OS e a reprogramação (a linha do motor, a mescla nas observações, o arquivo da semana em curso) |
| `telas.py` | as telas, penduradas na torre PCM (`registrar_pcm(bp)`) |
| `relatorios/` | **os quatro relatórios do PCM** na Central de emissão (14/10/2026): diário, recuperação da tarde, fechamento da semana e alerta da programação, cópia do Python do PCM, com a emissão automática nos horários de lá; regras e prova no `relatorios/CLAUDE.md` |
| `relatorio_exec/` | **o Relatório executivo do PCM** na Central de emissão (14/10/2026): Interno Grid, Cliente e Abertura da Semana, CÓPIA do `js/relatorio_exec.js` do painel (hash conferido no teste), com o gestao_pcm.json, o banco_dados.json e o confiabilidade.json servidos ao lado e a Gerencial aberta pelo servidor (`NEXUS_PCM_MPAS_SENHA`, o "MPA/MPS atrasadas"); na estrutura de toda a Central (os tipos no bloco "Relatório Gerencial PCM", o período e o escopo na coluna, a folha à direita); regras e como atualizar no `relatorio_exec/CLAUDE.md` |
| `acompanhamento/` | **o Acompanhamento do PCM** (14/10/2026, PCM → Acompanhamento PCM): as cinco abas do painel de acompanhamento do PCM O&M (MPA, MPS, Radar de Backlog, Mapa e One Page) com as estruturas de lá e o desenho do Nexus, montadas com as fontes que o Nexus já usa (Gestão PCM, banco_dados, Gerencial, cadastro) e a curadoria da reunião de PCM no livro `nexus_pcm_curadoria` (cifrado); a coordenada da usina não sai do servidor; regras e prova no `acompanhamento/CLAUDE.md` |
| `motivos.py` | **os motivos das tarefas e a lista do backoffice** (16/10/2026, seção abaixo): o livro `nexus_pcm_motivos` (cadastro, marcas, backoffice; cifrado), o `Fora_da_programacao.json` da rodada e do repositório do PCM |
| `atribuicoes.py` | **os técnicos por usina** (17/10/2026, seção abaixo): o livro `nexus_pcm_atribuicoes` (decisões que só acrescentam, vale a última de cada usina × pessoa × papel; apoio com datas; cada linha assinada para o App) |
| `tecnicos_usina.py` | a visão da tela Técnicos por usina: o cadastro do banco, a evidência de campo (rondas, fechamentos, programação), os avisos, os filtros em cascata, a carga inicial pela regra da equipe e a comparação com a foto do App |
| `motor/` | **cópia idêntica** do motor do PCM: **não edite** (veja o `README.md` de lá); hoje a do `bd4f673` + `fora_da_programacao.py` (16/10/2026, seção dos motivos) |

## Horas por tarefa e zeladoria no motor (15/10/2026)

Levi: "as tarefas estão vindo com horas previstas para a mesma quantidade de horas da OS [...] a OS 15596 de Elias
Fausto, a OS toda tem 25 Horas, porém por tarefa está somando 25 horas por tarefa, o que causa quase 750 hora de
tarefas pendentes [...] O mesmo está acontecendo com a OS 14331" e "gostaria que o tipo zeladoria só puxasse quando o
tipo de tarefa fosse de fato zeladoria, não só pelo nome, tem corretiva sendo reconhecida como zeladoria".

- **A causa das horas:** a view `work_orders` do Fracttal devolve em `duration` a duração da OS repetida em cada
  tarefa. O `fonte_bd_api.df_semanal` (o leitor do motor e do robô do PCM desde que a fonte trocou da planilha BD para a
  API) não corrigia; o conserto antigo do PCM (`enriquecer_com_duracoes_subtarefas`) pede o JWT e não roda ali. A
  duração da tarefa vem na mesma linha, em `tasks_duration` ("Total de Horas"). Conferido no retrato de 14/10: a
  duração da OS é igual em todas as tarefas de 1.694 de 1.694 OS; a 15596 tem 25 h e as 43 tarefas somam 25 h; a 14331
  tem 6 h = 4 × 1,5 h.
- **De onde vinham os números da W42:** a 15596 com 25 h POR TAREFA (741 h na agenda, 660 pendentes, 15 mil horas)
  foi o ROBÔ do PCM (`atualizacao_semanal`), que incorpora OS nova com a duração do leitor e empurra o que estiver no
  caminho; e cada vez que uma OS nova cai no horário de uma linha já deslocada, ela vira mais uma pendente (480 do
  mesmo inversor). A 14331 (4 × 6 h na mesma segunda) foi o MOTOR: fora das MPx, ele usa a duração do leitor.
- **A regra agora:** nas OS de mais de uma tarefa, a duração é a da tarefa; sem ela, a da OS dividida pelas tarefas; OS
  de uma tarefa não muda (`fonte_bd_api._duracao_da_tarefa`). No motor, a hora da tarefa vale para TODO tipo, também
  nas MPx (Levi, sobre a 15596 com 43 × 4 h = 172 h: "Tem que ser de acordo com nova regra"): as horas fixas por sigla
  da calibração de 31/07 (MPM 1,1 h, MPA 4 h...) só valem para a tarefa sem duração, e saiu o piso de 1 h das
  preventivas (`programacao_v7.estimate_h` e `_estimate_h_sem_fracttal`). No Fracttal a MPM típica tem 10 min: se o
  campo levar mais que o plano, o conserto é no plano do Fracttal. Zeladoria é o "Tipo de tarefa" Zeladoria
  (`programacao_v7.is_zeladoria`); pelo nome, "roça" sem acento casava com "troca" e "Sorocaba", e 150 das 186 tarefas
  abertas marcadas não eram zeladoria (113 corretivas).
- **As semanas já geradas com a regra velha** gravaram "Zeladoria" no tipo (o motor escreve o rótulo dele na coluna
  Tipo, e o tipo do Fracttal se perde). Levi, 15/10, com o cartão da OS 15290 ("troca de módulos danificados") na W42:
  "Zeladoria ainda está aparecendo em corretivas na parte de PCM do Nexus". O Quadro e Tarefas e OS trocam esse
  rótulo pelo tipo do Fracttal das tarefas da Gestão PCM (`gestao_pcm.json`), pela OS e pelo nome da tarefa, quando o
  Fracttal diz outro tipo (`quadro.tipo_do_fracttal`, `telas._tipo_do_fracttal`; só lê a Gestão PCM quando a semana tem
  zeladoria; fora do ar, fica o da planilha). Na W42 real: 26 linhas Zeladoria, 9 voltam ao tipo do Fracttal (8
  corretivas e 1 administrativa); das 17 que ficam, 16 são Zeladoria no Fracttal e 1 não está mais no arquivo. Só o
  rótulo muda: o "Em paralelo" da janela continua o que a planilha planejou, e o App de Campo segue com o arquivo dele.
- **No robô do PCM:** OS nova acima de 8 h usa a duração fixa da sigla; a mesma tarefa não se repete na `_Pendentes`;
  e o passo A2 (incorporar OS nova) não reincorpora o que o `Observacoes_Semana_Atual.txt` tira (`não` e `sem:`). O A2
  roda ANTES do A3, que apaga: a cada rodada a OS tirada voltava, deslocava o que estivesse no horário dela e só então
  saía (15/10 12:24: a 15596, tirada pelo PCM às 09:42, deslocou 19 tarefas e mandou 9 para as pendentes).
- **Onde está:** nos dois lados, com a cópia idêntica: repositório do PCM `fd39672` (11:54) e `bd4f673` (a pedido do
  Levi) e a cópia do motor do Nexus (a semana que o Nexus gera, desde a W43). As linhas que o robô já tinha gravado na
  W42 (as 25 h da 15596, as pendentes repetidas) ficam como estavam: ele não recalcula linha antiga (Levi: "As
  antigas infelizmente já era").
- **Prova:** W43 com a mesma foto (`ferramentas/gerar_semana_foto.py`, 14/10 15:06): duração por tarefa e zeladoria
  pelo tipo: maior dia de equipe 24,2 h → 10,3 h; 14331 24 h → 6 h; zeladoria terceirizada 31 → 18 linhas. Com a hora
  da tarefa também nas MPx: a 15596 cabe inteira (43 tarefas, 25 h; antes 10 na agenda e 33 pendentes); agenda 1.052
  → 1.586 linhas e 1.598 → 1.133 h; pendentes 2.255 → 651 h. Testes: `tests/test_pcm_motor_regras.py` (7 mutações,
  todas pegas). O A2 do robô, num caso montado (o "não" e o "sem:" ficam de fora, o resto entra). No robô, a 1ª rodada
  de verdade com o `fd39672` (15/10 12:24, Brasília) mudou a W42 do `banco_dados.json`: pendentes 2.222 linhas e
  20.955 h → 1.246 e 1.516 h; linhas de 8 h ou mais 695 → 15; pendentes repetidas 1.326 → 423 (as antigas).

## Motivos das tarefas, Fora da programação e o backoffice (`motivos.py`; 16/10/2026)

Levi, 16/10/2026, com a lista de 11 motivos (Engenharia, Chamados (garantia), Performance, Aguardando Cliente, Aguardando
Concessionária, Aguardando Material, Aguardando Fabricante/Terceiro, Condições Climáticas Adversas, Prioridade, Sinistro,
Pendente recurso), "temos que montar um painel de acompanhamento as OSs que saíram da programação por esses motivos!",
"Também temos que ter um canto no PCM onde podemos controlar todos esses motivos" e, à parte, "Quando a OS estiver
atrelada como responsável para alguém do time de backoffice, desconsiderar para a programação da semana". Cada regra
abaixo foi decisão dele (perguntada antes, pela regra "me pergunte antes de botar qualquer filtro ou parâmetro"):

- **O motivo se marca só no Nexus** (não vai ao Fracttal); o App de Campo só mostra. **Por TAREFA e UM por tarefa**
  (marcar outro troca). A tarefa = OS + código do ativo + nome (`motivos.item_id`); a marca feita pelo número da OS
  (painel) vem da Gestão PCM, que não traz o código, e vale para a tarefa em todos os ativos da OS; a do ativo vence a da
  OS (`motivo_de`). As comparações: OS como inteiro, código maiúsculo sem espaço, nome sem acento, sem caixa, espaço
  único (as mesmas no motor e no robô: o teste de contrato roda o módulo deles).
- **Quem:** marcam e tiram o administrador, o setor PCM e o setor Responsáveis UFV (`telas.pode_marcar`) e o TÉCNICO
  pelo App de Campo, com qualquer motivo do cadastro, valendo na hora como a do PCM (Levi, 16/10/2026, depois da 1ª
  versão: "Sim, e já vale" e "Todos do cadastro"); o cadastro dos motivos (incluir, editar, dizer se tira, tirar) é do
  administrador e do setor PCM (`pode_programar`). **O Cadastro de motivos edita na própria linha** (Levi, 18/10/2026:
  o Editar abria "um card nada a ver abaixo"; o nome, a descrição e o "tira" se mudam na coluna deles): o `<form>` de
  cada linha fica na célula das ações e os campos se ligam a ele pelo atributo `form`; o Salvar só aparece na linha que
  mudou, e mudar o "tira" de motivo com tarefas pede confirmação. A lista do backoffice, de quem abre o Gerar a semana
  (como as observações).
- **Pelo App** (`motivos_app.py`, a rota `POST /t/pcm/motivos/app`, pública só para quem assina, como a das fotos dos
  extintores): corpo JSON {os, codigo, tarefa, motivo (id; null = tirar), obs, tecnico_hmac, tecnico_nome}; cabeçalhos
  `X-Nexus-Ts` (epoch) e `X-Nexus-Assinatura` = HMAC-SHA256 de "<ts>." + o corpo cru, com a chave derivada da
  `NEXUS_PESSOA_HMAC` (rótulo `nexus:pcm:motivos-app`; nenhuma configuração nova); janela de 15 min. A tarefa tem de
  estar na programação publicada (comparada como o motor: sem acento, caixa e espaço a mais) ou aberta na Gestão PCM (a OS
  avulsa do App, com o código que o App mandou); senão 404. Grava com origem `app` e quem marcou pelo `tecnico_hmac` (o
  nome só cifrado; o painel e a janela mostram "(App)"), mexe na marca da OS quando é ela que vale (como a janela do
  Quadro) e agenda o arquivo do robô (fora do pedido, abaixo). Respostas: 200 {ok, gravou, marca, arquivo ("em
  instantes" ou "sem mudança"), arquivo_em_dia (null, por compatibilidade)}; 400 pedido fora do
  formato ou motivo que não existe; 401 assinatura ou hora; 404 tarefa; 503 sem a chave ou banco fora. Testes:
  `test_o_tecnico_marca_pelo_app` e `test_o_app_sem_assinatura_ou_com_tarefa_que_nao_existe_nao_grava`.
- **O nome do motivo** segue a regra do Levi (16/10/2026, "Padronizar texto: sempre a primeira letra maiúscula o resto
  minúscula conforme regra gramatical"), a MESMA do App: tudo minúsculo menos a sigla de 2 a 4 letras escrita em
  maiúsculas (PCM, COS, UFV), e a 1ª letra maiúscula (`motivos.padronizar`). O cadastro inicial já nasce assim
  ("Aguardando concessionária", "Condições climáticas adversas"); o que se cria ou edita na tela é padronizado ao gravar.
  O 12º do cadastro inicial, "Vegetação alta impossibilitando ação", tira da programação (Levi, 16/10: "Sim, tira").
  O App escolhe a frase do técnico pelo id (1, 3 e 9; o `FORA_FRASE` do campo.html): renomear aqui não muda o
  Justificar. **No Nexus os três são Engenharia, Performance e Prioridade; no App, as frases do técnico** (Levi,
  18/10/2026, que desfez a troca de 16/10, quando o cadastro de produção tinha ganhado as frases "Preciso de apoio do
  setor engenharia", "Preciso de apoio do setor performance" e "Priorizei outras atividades"). Renomeados no banco em
  18/10, 03:47Z, pelo `motivos.cadastro`; o selo das marcas de outros no App lê o nome do arquivo do robô, que o servidor
  manda de novo na próxima marca. O `CADASTRO_INICIAL` guarda os nomes do nascimento do livro (o banco manda).
- **Os que tiram da programação** (o cadastro inicial: os quatro Aguardando, Condições Climáticas Adversas e Pendente
  recurso; os outros não mudam a geração: com "Priorizei outras atividades", o 9, a tarefa NÃO sai da programação e
  continua sendo cobrada nos outros dias, Levi 16/10/2026): a geração não programa a tarefa e, na semana em curso, o robô do PCM apaga as
  linhas dela (agenda e `_Pendentes`, STEP A3b) e o STEP A2 não a inclui de novo. Tirar o motivo: a tarefa volta na
  PRÓXIMA geração (o robô não a recoloca na semana em curso).
- **Backoffice:** a OS cujo responsável no Fracttal (o `Responsável` da OS, o `user_assigned`) é um nome da lista (sem
  acento e sem caixa) não entra na geração, e o robô não a inclui como OS nova; a que já está na semana em curso fica (a
  escolha dele foi "geração e robô"). Não aparece no painel, e no App não tira nada. Em 16/10 a lista do Levi casava 286 tarefas
  abertas (208 de uma pessoa só); um dos 11 nomes não aparece como responsável de OS no Fracttal. Os nomes vão ao robô
  em claro, no arquivo do repositório do PCM ("precisa disso não, faz o simples").
- **O painel Fora da programação** (`/t/pcm/fora-da-programacao`, `templates/pcm/fora.html`): as tarefas com motivo
  que tira e TODA justificativa que veio do App, de qualquer motivo, com o texto do técnico, quem e desde quando; a
  marca do PCM que não tira não aparece (16/10/2026: as 10 justificativas "Prioridade" de um técnico estavam gravadas e
  o painel mostrava 0; o Levi escolheu listá-las aqui). "Do App" é pelo MOTIVO (`origem_motivo`/`quem_motivo` de
  `motivos.vigentes`: a 1ª decisão da sequência com o mesmo motivo), não pela última decisão: o PCM que edita a
  observação não tira a justificativa daqui nem troca quem marcou (antes ela sumia e virava do PCM). A FINALIZADA no
  Fracttal sai sozinha (pelo estado da tarefa na Gestão PCM; a marca fica no histórico). **Filtros** (Levi, 16/10:
  "aumente a quantidade de filtros — Técnico, equipe, OS, Usina, Responsável"; as definições foram escolha dele, com o
  dado do dia, e valem também no Histórico; `telas.FILTROS_FORA`, `_campos_de_filtro`, `_filtrar`, o pedaço
  `pcm/_fora_filtros.html`): Motivo; Técnico = quem justificou (quem pôs o motivo); Equipe = a equipe da tarefa na
  programação (o `cluster` da linha da semana, gravado na marca) ou, sem ela, na Gestão PCM: é a mesma da usina no
  cadastro do Nexus (14 de 14 em 16/10); Usina (o nome); Responsável = o responsável da OS no Fracttal (a Gestão PCM; em
  16/10, dois gestores de contrato); OS = o número digitado (só os dígitos, igual). As
  listas mostram só o que existe, com quantas linhas têm cada um; os filtros somam; cada formulário da tabela leva os
  que valem (`v_<filtro>`), e a tela volta filtrada depois de salvar. Seis filtros e o Limpar cabem numa linha a 1366 px. A tabela (Levi,
  16/10, 2ª e 3ª rodadas), tudo centrado menos a Tarefa e sem a coluna Editar que abria a linha. **No estilo da tela de
  PT do Campo** (Levi, 17/10/2026: "Quero mesmo estilo de tabela em Fora da programação"; o `campo.css`, como o Técnicos
  por usina): o cabeçalho com a hora da leitura, os números do topo (fora da programação, só justificativa do App, a mais
  antiga, justificativas, finalizadas; o que está na tabela, com os filtros), as abas Painel, Histórico e Cadastro de
  motivos (`_fora_topo.html`, no lugar dos botões de cada visão) e os filtros e a tabela do Campo:
  - a usina só com o nome ("Thopen - Parelhas 1 - RN" vira "Parelhas 1"; o nome inteiro no title); o "Desde" com a
    hora; abaixo da tarefa só o tipo e a situação no Fracttal (o código do ativo, ou "todos os ativos da OS", no title:
    é o que separa duas linhas iguais da mesma OS);
  - a OS e todo nº de 5 a 6 dígitos da observação ("OS16290") em verde Grid abrem o card da OS do OS Creator por cima
    da tela, o mesmo do Histórico (`oscreator/card_os_abrir.html`): pelo id do Fracttal quando a OS está na Gestão PCM
    (`idWO`, com o status do card), senão pelo número (`NexusOsCard.abrirFolio`, `/os/_nexus/card/folio/<nº>`);
  - o motivo do técnico NÃO se troca ("se o técnico disse tá dito"; a rota recusa); o do PCM troca na própria célula
    (o selo é a lista; o que não tira pede confirmação, porque a tarefa sai do painel);
  - a observação se edita na própria célula (lápis ou clique no texto; o campo ocupa a largura da célula e não
    alarga a tabela: a 1366 px ela cabe inteira, editando ou não);
  - os três pontos do fim da linha abrem o menu com "Retornar à programação" (tira o motivo, com confirmação; o menu é
    fixo na tela, para a rolagem da tabela não o cortar);
  - a coluna **Vezes** (16/10/2026, Levi: "é bom no nexus termos o histórico de quantas vezes uma OS teve um motivo
    diferente"; escolhas dele: "cada justificativa, 1 por dia", "por tarefa", no painel) conta as justificativas da
    tarefa (a do ativo e a da tarefa em todos os ativos da OS), uma por dia e motivo (`motivos.historico`): a mesma
    justificativa no dia seguinte conta de novo, e por isso o `marcar` passou a GRAVAR a repetição em outro dia (no
    mesmo dia, não grava); só editar o texto no mesmo dia não conta; tirar o motivo não conta. O número abre, logo abaixo
    da linha, a lista com a data e hora, o motivo, quem justificou (da 1ª decisão do dia) e o texto (o mais novo);
  - saíram o "Marcar pela OS" ("atrapalha mais que ajuda": marca-se no Quadro e pelo App; a rota só aceita a tarefa
    que já tem motivo, `item`) e a nota de como o painel funciona; o aviso do arquivo do robô só aparece quando ele
    não está em dia.
  **Histórico** em `?ver=historico` (`motivos_historico.html`; Levi, 16/10/2026: "mas salva um histórico de motivos
  no fora da programação > histórico"): cada PERÍODO de motivo de cada tarefa (`motivos.episodios`: as decisões
  seguidas com o mesmo motivo; editar o texto ou repetir a justificativa não abre outro, e a contagem por dia continua a
  do `historico`, da coluna Vezes), do mais novo ao mais antigo, com de quando até quando, os dias, quem pôs o motivo e
  como saiu: "Retornou à programação" (com quem tirou; "(App)" quando foi o técnico), "Trocou para <motivo>", "Finalizada
  no Fracttal", "Motivo tirado do cadastro" ou "Ainda no painel". Nada se apaga (o livro só acrescenta decisões); o
  mesmo recorte do painel (o motivo que tira e a justificativa do App, pela origem de quem pôs o motivo) e os mesmos
  filtros do painel. O botão "Histórico" fica ao lado do "Cadastro de motivos". Cabe a 1366 px.
  Cadastro em `?ver=cadastro` (`motivos_cadastro.html`): tirar não apaga, marca `excluido` e o ID não volta, e as
  tarefas com ele perdem o motivo (a confirmação diz quantas).
- **No Quadro** (a janela da OS, também das pendentes, que agora abrem a janela pelo nome): a seção Motivo mostra o de
  agora (desde quando, quem, a observação) e marca, troca ou tira por `POST /t/pcm/quadro/motivo` (JSON; a tarefa vem da
  SEMANA, a página só diz qual). O cartão e a pendente ganham o selo (vermelho: tira; laranja: não tira — Levi, 16/10: "vermelho o que sai da
  programação, laranja o que não sai"). Nas telas do Fora da programação (painel, histórico, cadastro) o selo é só a
  letra na cor, sem o fundo (Levi, 18/10: "Tire as bordas vermelhas e laranjas, deixe só as fontes!", `q-mp--texto`);
  no Quadro segue com o fundo. Com a marca da OS
  valendo na linha, trocar ou tirar mexe nela (em todos os ativos).
- **O dado:** livro `nexus_pcm_motivos` (registrado no catálogo antes de existir; nasce com a 1ª gravação, que leva o
  cadastro inicial junto): `dim_motivo`, `fato_decisao_motivo` (só acrescenta, vale a última de cada tarefa) e
  `fato_decisao_backoffice` (vale a última de cada nome). Tarefa, usina, observação, nome do backoffice e quem marcou só
  cifrados (Cofre); em claro a OS, o código, o `equipamento_id`, o `tarefa_chave` e o código de quem decidiu. Gravar
  troca o livro inteiro (as três abas), relido antes; leitura que falha não grava. Cópia de prova e testes:
  `NEXUS_PCM_MOTIVOS_ARQUIVO` (o livro num arquivo).
- **O arquivo `Fora_da_programacao.json`** (`motivos.arquivo`): o cadastro, as tarefas com motivo (sem observação e sem
  quem marcou: o repositório é público) e os nomes do backoffice; `hash` = o do conteúdo. **Contrato com o App de Campo**
  (o chat do App, 16/10): o servidor do App lê da mesma pasta do `banco_dados.json` (nome e pasta fixos); é o estado de
  AGORA (a desmarcada sai); `os`, `codigo` e `tarefa` como nas linhas do `banco_dados.json` (o texto da marca é o da
  linha, só sem espaço nas pontas; código vazio = todos os ativos da OS); `usina`, `cluster` e `data_prog` (o dia em que
  estava na agenda quando foi marcada; vazio na pendente e na marca pela OS) para o App agrupar; `motivo` = o id;
  `origem` = por onde o MOTIVO foi posto, "app" (o técnico pelo App) ou "nexus" (Quadro e painel; a observação editada
  no painel não muda), sem pessoa, pedido do App para mostrar "marcado
  pelo PCM" ou "no App"; todo
  motivo das tarefas está em `motivos` (`ativo` sempre verdadeiro: tirar do cadastro tira as marcas). **O App NÃO filtra
  a programação** (Levi, 16/10: "se a programação semanal já estiver filtrada não tem necessidade de filtrar duas vezes
  no app"; v281 no ar 16/10 17:27Z): quem tira a tarefa da semana é o robô (A3b), e até ele rodar o App mostra a tarefa
  com o selo âmbar; o servidor do App tira das "OS avulsas" e dos religamentos (que o robô não alcança) a tarefa com
  motivo que tira e ainda não iniciada; a lista do backoffice NÃO tira nada no App (só a geração e o robô). O Justificar
  do App lê o cadastro do arquivo: **o arquivo tem de existir**, mesmo sem marca (o painel mostra "não existe" e o botão
  de mandar). Em 16/10 ele nasceu com a lista do backoffice (os 11 nomes do Levi, gravados pelo Claude a pedido dele;
  commit `3b3efae` no repositório do PCM). Vai (1) para
  a pasta de cada rodada (`motivos.materializar` no `geracao._preparar`; banco fora do ar = a última cópia boa da máquina, com aviso; sem
  cópia a rodada não sai) e (2) para a raiz do repositório do PCM a cada marca, cadastro e backoffice
  (`publicar_arquivo`, o PUT do `publicar.py` com `NEXUS_PCM_GITHUB_TOKEN`; igual ao de lá = não grava), **fora do
  pedido** (`publicar_depois`: 3 s depois da marca, e as marcas seguidas vão juntas numa publicação só; o botão "Mandar o
  arquivo de novo" espera e diz o resultado). Por quê: no 1º uso real do Justificar do App (16/10, 6 marcas de um
  técnico em 4 min), 3 pedidos passaram de 20 s ou deram 502: cada marca lia o livro três vezes e esperava quatro
  chamadas ao GitHub. Agora a gravação deixa a leitura guardada com o estado novo e a rota do App decide pela leitura
  guardada (a gravação relê o banco). Falhar o GitHub não desfaz a marca: o log diz e o painel mostra "desatualizado"
  com o botão de mandar de novo. Não dispara o robô: ele lê na rodada seguinte.
- **No motor e no robô do PCM** (`fora_da_programacao.py`, cópia em `motor/`): o `programacao_v7` tira da lista antes de
  montar a semana (log `[FORA DA PROGRAMAÇÃO]`); o `atualizacao_semanal` pula no A2 e apaga no A3b; o
  `gerar_pcm_json` passou a mandar o `codigo` da pendente (o Quadro marca a pendente pelo ativo). Sem o arquivo, nada
  muda.
- **Prova (16/10):** W43 com a mesma foto, motor sem marcas = o de antes (agenda 1.629 e pendentes 736, coluna a
  coluna); com 3 marcas que tiram, 1 que não tira e os 11 nomes: saíram as 3 tarefas e as 33 tarefas de 33 OS do
  backoffice que a semana teria, ficou a que não tira (agenda 1.629 → 1.606, pendentes 736 → 726). Robô, na planilha
  real da W42: o A3b tirou exatamente as 4 linhas marcadas (o ativo com marca própria que não tira ficou), o A2 só deixou
  entrar o que devia, e as 1.038 pendentes ganharam o código. Testes: `tests/test_pcm_motivos.py` (17; 19 mutações,
  todas pegas).

## Técnicos por usina (`atribuicoes.py`, `tecnicos_usina.py`, `templates/pcm/tecnicos.html`; 17/10/2026)

Levi, 17/10/2026: "cria uma estrutura que liga usina e técnico e o PCM pode editar a vontade"; "é normal usinas terem
dois técnicos e receberem de vez em quando mais técnicos"; "quero tirar do site de gestão"; "vamos deixar redondo,
depois tiramos 100% do site de gestão". Desenho: `docs/superpowers/specs/2026-10-17-tecnicos-por-usina-design.md`.

- **O que a lista quer dizer:** quem VÊ e pode rondar a usina no App de Campo. No App é o papel `executa` da tabela
  `atribuicoes` (modelo de escopo "novo", ligado em produção), que decide as usinas da aba Ronda; hoje ele vem da tela
  Organização do site de gestão e do `espelhar_bd_operacoes.py` (a regra da equipe). Não é "o designado": o
  `tecnico_om_id` do cadastro (um por usina) continua como está.
- **O dado:** livro `nexus_pcm_atribuicoes · fato_decisao_atribuicao` (catálogo: `decisao_atribuicao_pcm`). 1 linha = 1
  decisão de pôr ou tirar 1 pessoa de 1 usina num papel; só acrescenta; vale a última de cada (`usina_id`, `pessoa_id`,
  `papel`). Fixo = sem datas; apoio = `ate_data_id` (vale até o último dia, sai sozinho); agendado = `de_data_id` no
  futuro. Em claro os IDs, o `usina_fracttal` (o nome que o App usa para achar a usina) e os códigos HMAC; a observação
  só cifrada. A mesma decisão não grava de novo; o nome do Fracttal ou o código da pessoa diferentes contam como
  mudança (a reemissão), mas a reemissão nunca troca um código bom por vazio (sem o código de hoje vai o gravado). O
  tirar leva o nome e o código da linha que pôs (é por eles que o App acha o que tirar). Sem a `NEXUS_PESSOA_HMAC` nada
  se grava (a linha iria sem assinatura e o App a descartaria).
- **A tela** (PCM → Técnicos por usina), no estilo da tela de PT do Campo (Levi, 17/10: "quero que a tabela seja no
  mesmo estilo de PT e APR"; usa o `campo.css`): os números do topo (usinas, sem técnico, pessoas de campo, apoios,
  com aviso), as abas Por usina, Por técnico e, com a foto do App, Comparação com o App (outra página: as duas
  primeiras trocam na própria página só onde a seção delas está; na Comparação o link navega, 18/10/2026, o Levi
  clicava em Por usina ali e a tela não voltava; `tests/test_pcm_tecnicos_js.py`), os chips das situações (com
  técnico, sem técnico, com aviso) e a linha que abre o detalhe com o histórico e o "Pôr técnico" (Levi, 17/10, 2ª
  rodada: a coluna Cliente antes da Usina, sem a Região de campo; os técnicos um embaixo do outro, sem borda; sem o
  botão "Técnico" na célula). Veem os setores PCM e
  Responsáveis UFV; põe e tira quem `pode_programar`; a **carga inicial** (só administrador, só com o livro vazio) é a
  regra da equipe do App aplicada ao cadastro do Nexus, só nas usinas EM OPERAÇÃO (cada pessoa de campo recebe as
  usinas em operação com o mesmo `equipe_id`; medido em 17/10: a regra dava 53 de 227 usinas fora de operação). Ao lado de cada usina, sem gravar nada: quem rondou
  e fechou tarefa ali em 30 dias, quem é técnico na programação da semana e o técnico do cadastro. Avisos (não travam):
  sem técnico, sem nome do Fracttal, duas grafias, técnico sem e-mail (o App não o reconhece), quem esteve lá e não está
  na lista, o nome ou o código que mudou ("Reenviar ao App"). Filtros (decididos pelo Levi): equipe, cliente,
  responsável, situação e busca, em cascata; `todas=1` mostra as usinas fora de operação. **O filtro de cliente
  substituiu o de região de campo** (Levi, 17/10: "troque o filtro de região e coloque o de cliente"); na visão por
  técnico, o cliente filtra quem tem usina dele. **Tempo** (medido no banco real, 17/10): a 1ª abertura levava 11,6 s
  (cada livro pedia de novo a lista de todas as tabelas, ~0,6 s, e a programação inteira, 16,5 mil linhas, era lida
  para achar a semana em curso); agora uma listagem só (`campo.visao.carregar`), as leituras em paralelo, a programação
  lida do FIM (a semana em curso está entre as do arquivo do robô, no fim do fato) e a evidência guardada por 10 min:
  3,3 s fria, 0,02 a 0,06 s quente. Visão por técnico. Sem o
  cadastro do banco, a tela abre com o aviso e nada grava.
- **O App: A1–A3 no ar na v283 (17/10/2026), com o interruptor `NEXUS_ATRIBUICOES` AUSENTE** (a aba Ronda ainda
  segue a Organização do site de gestão). O contrato: `C:\GridcoBuild\app-campo-docs\_propostas\atribuicoes-nexus\LEIA.md`.
  A1: o App publica a foto `organizacao_app_campo · Atribuicoes` aos :25, que a tela compara NO IDIOMA DO APP — a grafia
  da usina e o código que vão na linha, não os IDs do Nexus — e de onde saem as pendências para a troca (inclusive a
  linha que vai sem nome do Fracttal ou sem código). A2: de 5 em 5 min o App lê este livro, confere a assinatura e, com
  `NEXUS_ATRIBUICOES=ligado`, substitui o `executa` (`simular` só conta no `/health` → `nexusAtribuicoes`: `a_por`,
  `a_tirar`). A3: ligado, a Organização recusa o "Marcar que executa" e o espelho do BD deixa o `executa` em paz. A
  assinatura é HMAC com a chave derivada da `NEXUS_PESSOA_HMAC` (rótulo `nexus:pcm:atribuicoes`); o vetor de teste está
  nos dois lados. **Do lado do App, a usina casa EXATO pelo nome do Fracttal** (não por "contém"), a linha vigente que
  não é a última do seu par assinado (usina_fracttal, pessoa_hmac) não vale (os IDs não são assinados), e **com
  qualquer pendência (sem código, sem usina) o App não tira ninguém** de usina, só põe: por isso se liga com as
  pendências em zero. A reemissão daqui (mesmos IDs, código novo) é a forma certa de corrigir uma linha.
- **Fases:** o Nexus e o App prontos (nada muda no campo); o PCM zera as pendências → o Levi confere o `simular` e liga;
  por fim o responsável da usina e a hierarquia (papel `responsavel`) e o site de gestão sai 100% da organização de
  campo.
- **Provar:** `tests/test_pcm_atribuicoes.py` (o livro: vigência, dia de Brasília, mesma decisão, assinatura),
  `tests/test_pcm_tecnicos_usina.py` (a visão: regra da equipe, evidência, avisos, cascata, foto do App) e
  `tests/test_pcm_tecnicos_tela.py` (quem vê e edita, carga inicial, reenviar, tirar, banco fora); 11 mutações, todas
  pegas. A tela: renderizar com o banco de mentira dos testes e servir a pasta (1366 e 375 px, escuro e claro).

## O menu da torre PCM (`nexus/torres/pcm/__init__.py`)

Quadro da semana, Fora da programação (16/10/2026, dos mesmos setores do Quadro), Técnicos por usina (17/10/2026, dos
mesmos setores; edita o PCM), Insights do PCM, Tarefas e OS, Gerar a
semana, Gestão PCM, PCM 52 Semanas, Torre de controle e Peças e sobressalentes (Insights, 52 Semanas, Torre de controle e
Peças ainda são placeholder). **A Semana saiu em 12/10/2026
com o código dela** (Levi: "PCM > Semana -> pode excluir essa seção e o código dela!"): a rota, o `semana.html`, o
`resumo` e o `por_equipe` do `semana.py` (aderência e horas por equipe e dia, contra as 7 h) e o CSS só dela; as regras
que as outras telas usam ficaram no `semana.py`. O 1º item do PCM (e o cartão do PCM no Início) passou a ser o Quadro
da semana. **Chamados por etiqueta e Disponibilidade saíram em 11/10/2026** (Levi: "tire essas seções"); a Disponibilidade da Performance (porta única com a
plataforma) é outra tela e continua. A **Torre de controle** seria o painel das rotinas do PCM: a planilha "Controles PCM
(editar aqui).xlsx" (pasta do PCM, 09. Programação Semanal/00. Torre de Controle PCM, 19/08/2026) lista 24 controles com
cadência, prazo e quem marca (gerar e publicar a semana toda sexta, inspeções semanais da GreenYellow toda quinta, subir
as preventivas do mês seguinte, relatório mensal aos clientes no 5º dia útil, fechamento de KPIs, auditoria do Fracttal,
MPS do semestre, MPA do ano, nova usina e saída de contrato...), e a página HTML de lá marcava o feito num `estado.json`
que nunca recebeu marca (vazio desde 17/08). **Não montar por enquanto** (Levi, 11/10/2026: "Não acho que valha a pena
montar essa torre agora, vou falar com o time de PCM"): a tela segue placeholder no menu até ele decidir.

## Filtros em cascata (todas as telas do PCM com filtro; 09/10/2026)

**O filtro na própria página** (Levi, 17/10/2026: "sempre que vou puxar um filtro ele carrega o site de novo, deveria só
filtrar os dados direto"): no Técnicos por usina e no Fora da programação (painel e histórico) as linhas vão TODAS à
página, cada uma com o que cada filtro olha (`data-f-<chave>`), e o `static/filtro-local.js` só mostra e esconde,
refaz as contas das listas em cascata (cada lista com os OUTROS filtros, a mesma regra do servidor) e troca o endereço
(`history.replaceState`), sem ir ao servidor; as abas Por usina e Por técnico e o "Todas" do Técnicos por usina também.
O servidor continua entendendo o endereço: a página aberta já filtrada chega com as linhas certas escondidas, e os
formulários de gravar levam os filtros de agora (`v_<chave>`), para a tela voltar como estava. Tela nova com filtro usa
o mesmo script (o formulário `data-filtro-local`, as linhas `data-fl-linha`; o cabeçalho do arquivo diz o resto).

Levi: "Os filtros tem que se auto filtrar também, pelo o que vi nenhum tem relação alguma com outro, está só buscando
uma string". Cada filtro lista só o que existe com os OUTROS filtros aplicados (escolhida a equipe, o Responsável e o
Cliente só listam os dela); o filtro não restringe a si mesmo (dá para trocar de equipe sem limpar o resto); a opção
escolhida fica na lista mesmo quando a combinação não tem nada (a tela não esconde o filtro que está valendo). Vale para:
Quadro da semana (`quadro.opcoes`, com quantas tarefas cada opção tem), Tarefas e OS (`semana.facetas`, com as contas) e
os filtros de cima da Gestão PCM (`gestao.escolhas_topo(tarefas, topo)`, sem contas: o número da matriz diz o resto).
Testes: `test_filtros_de_tarefas_em_cascata`, `test_filtros_do_quadro_em_cascata`,
`test_filtros_de_cima_em_cascata`.

## Insumos: no Nexus, não em arquivo

Prioridades, Confiabilidade, Feriados e Observações (por semana) moram em `insumos.py`; o Histórico sai do BANCO
(`historico_banco.py`, desde 08/10/2026, abaixo). A cada geração, o Nexus escreve os arquivos na pasta da rodada, com a
mesma aba, a mesma linha de cabeçalho e a mesma posição de coluna do original. A AUXILIAR sai do cadastro do Nexus
(`auxiliar.py`, desde 02/10/2026). Da pasta do PCM só vem ainda o `duracoes_aprendidas.json` (sombra: não muda a
agenda).

- **AUXILIAR:** o motor lê seis colunas dela: UFV; o responsável (desde o motor `3ce6205`, 09/10/2026, a coluna
  `Gestor de Contrato`; sem ela, a que tem RESPONSÁVEL O&M); CIDADE; o porte (a coluna `POTÊNCIA CONTRATUAL (MWp)`;
  sem ela, a 1ª com "MWp"; vazio e zero não entram: 67 usinas sem MWp derrubaram a W42 do PC do PCM em 08/10); Equipe
  Cluster e Base Equipe. A AUXILIAR do Nexus escreve as duas colunas novas do cadastro (`gestor_contrato`,
  `potencia_contratual`) e mantém as antigas. Equipe Cluster fora do padrão "UF Região NN" vai vazia: era uma aba vazia
  por usina com equipe local. Prova da S41 (02/10), com a mesma foto do Fracttal da geração oficial: agenda e pendentes
  idênticos; 48 linhas ganharam Responsável; mudam só as colunas de sombra (RPN novo e Desloc). **RESPONSÁVEL O&M
  sem pessoa** (estrutura de O&M de 10/2026): o BD_Operações traz a REGIÃO onde a vaga de Supervisor de Campo está
  aberta ("NE · Fortaleza-CE e Teresina-PI"); o cadastro guarda a pessoa vazia e a região em `responsavel_om_vaga`, e
  a AUXILIAR escreve a região, como a AUXILIAR do BD escreveria (o motor não a usa mais para o Responsável).
- **Provar mudança no motor ou nos insumos: rode com a FOTO do Fracttal**, nunca lendo o Fracttal de novo (horas depois
  a semana muda: S41, 157 tarefas a mais e 280 horários). `python ferramentas/gerar_semana_foto.py --semana 2026-W42
  [--historico banco|nexus] [--rotulo x] [--contra <rodada ou planilha>]` (`geracao.gerar_com_foto`): os mesmos
  insumos da tela; da pasta do PCM (só lida) vêm os caches que o motor gravou ao ler o Fracttal (`.cache_semanal_api.pkl`,
  obrigatório, e `.cache_hist_api.pkl`, `.cache_bd_api.pkl`, `_ativos_classificacao_cache.json`,
  `_usinas_coordenadas_cache.json`), copiados com a idade; TTLs de ~100 anos; credencial VAZIA e o Fracttal numa porta
  fechada (se o motor tentar ler, falha); no fim, a rodada confere o sha da foto ("intacta": o motor regrava o cache
  quando lê). A rodada leva "-foto" no nome e fica fora da lista da tela. Imprime a `comparar.conferir` da semana e o
  que continua da semana anterior. 1ª vez: W42, 09/10 00:16, foto de 08/10 21:46, 10 s.

- **Feriados do ano seguinte (09/10/2026):** a planilha do PCM só tem 2026 e a W53 de 2026 vai de 28/12 a 01/01/2027.
  A rodada escreve, no MESMO arquivo que o motor lê (ele só olha a data), o ano seguinte ao da semana projetado
  (`insumos.com_feriados_ate`): data fixa repetida; Carnaval (-47), Paixão (-2) e Corpus Christi (+60) pela Páscoa do
  ano (`insumos.pascoa`), e o estadual do ES (Nossa Senhora da Penha, Páscoa + 8). Os municipais ficam na data: a
  planilha não diz qual seria móvel. O ano que a planilha já tem não se projeta. 2027: 100 datas (Carnaval 09/02,
  Paixão 26/03, Corpus Christi 27/05, ES 05/04). O carimbo da rodada diz "2027 projetado"; conferir com o calendário
  oficial quando sair.
- **Armazém:** `C:\GridcoAuto\nexus\pcm\insumos.json`, fora do OneDrive, com a versão anterior ao lado. Trocar pela
  API de dados é mexer só em `insumos.py`.
- **Na sombra:** "Importar da pasta do PCM" traz prioridades, confiabilidade, feriados e as observações da semana, para as
  duas semanas partirem do mesmo dado. **"Importar observações do repositório do PCM"** (09/10/2026) traz o
  `Observacoes_Semana.txt` que o PC do PCM ou o painel mandou por último (funciona no servidor); o leitor do Nexus
  entende as 60 linhas do arquivo de 08/10 (49 `@usina`, 3 OS fora, 8 OS com dia fixo, com tarefa, turno e "só:").
  No full Nexus, as observações da semana se escrevem no bloco 2, não no arquivo. **O histórico NÃO** (desde 08/10/2026): o arquivo do PC punha por cima a W41 das
  duas gerações. A tela avisa quando um arquivo da pasta mudou depois da importação.
- **Prova obrigatória** a cada mudança no formato: o que o motor lê do arquivo gerado pelo Nexus tem de ser igual ao
  que ele lia do original, com as mesmas leituras do `programacao_v7.py`. `tests/test_pcm_insumos.py` faz isso com
  dado de mentira (e `tests/test_pcm_historico_banco.py`, para o histórico do banco); com os arquivos reais, rode a
  mesma comparação fora do repositório.

## Histórico das programações: do banco (Levi, 08/10/2026: "PUXE O HISTÓRICO")

O motor lê do `Historico_Programacoes.xlsx` só `task_key` (OS + código do equipamento, SEM a tarefa), `count` e
`weeks`: "Nº vezes programada" = `count + 1`, "Reprogramada" = `count > 0`, o ÚLTIMO desempate da fila
(`programacao_v7` l.2081, depois de tier, aging, sigla e RPN), e 0,75 × `count` no RPN dinâmico (sombra). Uma semana
conta para a chave quando a chave teve bloco na AGENDA dela (o motor não grava as pendentes).

- **De onde:** a geração monta o arquivo do `nexus_programacao · fato_programacao` (GET, `historico_banco.py`), só com as
  semanas ANTES da gerada (gerar de novo a mesma semana não a conta). O banco começa na W21: a W20 do arquivo do PC não
  entra. A chave é a do motor: o `codigo_ativo` do fato é canônico (maiúsculo, sem espaço) e, nas chaves do arquivo do
  PC, igual ao texto do Fracttal; na foto de 08/10, 3 de 6.226 códigos têm espaço ou minúscula, nenhum na agenda nem nas
  pendentes da W42. Código assim programado um dia não acharia o histórico (contaria como 1ª vez).
- **Semana que o banco ainda não fechou** (terminou depois do `atualizacao.gerado_em` do livro): vale o PLANO PUBLICADO
  dela: o da reserva (o Nexus põe lá o que ele publica); senão a `Programação Semana NN.xlsx` do REPOSITÓRIO do PCM (o
  que foi ao App, publicado pelo PC do PCM ou pelo Nexus; funciona no servidor; só vale se o dia da semana bater com o
  dd/mm, porque o nome não tem ano); senão a da pasta do PCM; sem nenhum, a do banco, com aviso. Medido em 09/10 (GET):
  o repositório dá a W40 com 1.109 chaves e a W41 com 1.119, as publicadas. Por quê: no App a semana ATIVA muda toda noite (a "Rolagem" tira da agenda o que não coube no dia e põe nas
  pendentes; Nova OS entra) e o robô só a refaz pelo plano quando ela fecha (W40: 858 chaves em 02/10 19:30, 1.356 às
  22:10). O motor gera a semana N durante a N-1: a N-1 do banco é sempre um retrato do meio dela. A W41 gravada em
  08/10 17:05 tinha 971 chaves contra 1.119 da S41 publicada: 159 de OS canceladas e 247 de OS vivas (229 nas pendentes
  com "Rolagem: sem capacidade").
- **Reserva:** o histórico guardado no Nexus (`insumos.json`; a W41 de lá é a S41 publicada, corrigida em 05/10). Vale se
  o banco não responder (a rodada carimba com aviso) e dá o plano da semana em andamento. Sem banco e sem reserva, não
  gera. `--historico nexus` na ferramenta da foto usa a reserva direto, para comparar.
- **Banco × reserva × arquivo do PC (09/10, histórico da W42):** banco 7.999 chaves (W21-W41), reserva 7.865, PC 7.963.
  Semana fechada no banco = plano publicado menos OS canceladas depois (W36-W39 só diferem disso: 64, 70, 133 e 174
  chaves; a OS cancelada não volta ao Fracttal, não muda geração). O arquivo do PC (e a reserva, que é cópia dele) guarda
  a UNIÃO das gerações (W40: 1.306 contra 799; 142 de outra geração e 365 de OS canceladas; W33: 180 de outra geração;
  W41: 1.286 contra 1.119), não tem a W35 (o banco tem 890 chaves) e tem 377 linhas com `first_week`/`last_week` fora
  de ordem (o motor não os usa). O banco tem 1.189 chaves de Nova OS que o robô deixava na semana fechada até agosto
  (W22-W28, W32, W34, W35).
- **Efeito na W42** (mesma foto, `--historico nexus` × `banco`): agenda e pendentes IGUAIS (924 blocos, 1.246 pendentes,
  todas as colunas); mudam o "Nº vezes programada" em 65 linhas de 64 chaves (por causa, e uma chave pode ter mais de
  uma: +1 pela W35 em 39; -1 por outra geração da W40 em 25, da W33 em 9 e da W27 em 1; W34 -1 em 7 e +1 em 1), a
  "Reprogramada" em 9 (Sim -> Não: OS que só estavam na 1ª geração da W40, que não foi a campo) e o RPN (novo), em
  sombra, em 15. O desempate não mexeu em nenhum horário nesta semana.

## Publicar no App (`publicar.py`, `templates/pcm/publicar.html`, `/t/pcm/gerar/publicar`; 09/10/2026)

O mesmo caminho do PC do PCM (`publicar_semana_github.py` do repositório do PCM): PUT na API de conteúdo do GitHub da
`Programação Semana NN.xlsx` (a `saida/sombra.xlsx` da rodada) e do `Observacoes_Semana.txt` da rodada, na raiz do
repositório (`NEXUS_PCM_REPO`, padrão `fillipefigueiro-source/gridco-pcm-data`, ramo `main`). O push dispara o
`semanal.yml` do PCM na hora (gatilho `Programa*.xlsx` e `Observacoes_Semana*.txt`, sem o descanso de 30 min), que
roda o `atualizacao_semanal.py` e o `gerar_pcm_json.py` e regrava o `banco_dados.json` do App em 5 a 10 min. O robô
escolhe a semana ativa pela data de hoje: a W43 publicada na quinta vira a do App na segunda. Nada muda no App.

- **Não manda** o `Observacoes_Semana_Atual.txt` (os ajustes da semana EM CURSO, gravados pelo painel do PCM): a tela
  mostra o que está lá para a pessoa pedir a limpeza no painel.
- **Barra** (`motivos_para_nao_publicar`): rodada que não terminou bem, rodada com a foto do Fracttal (prova), semana que
  já acabou, rodada sem a conferência da semana (as de antes de 09/10), bloco fora da semana, arquivo que falta.
- **Pede confirmação a mais:** a semana já começou (troca a programação no meio dela); o repositório já tem a planilha
  da semana (mostra quando e por quem foi gravada). Avisa: geração com mais de 24 h (o Fracttal mudou), corretiva
  forçada além das horas do dia (`excede_hh_os`), observações sem nenhuma OS fora ou com dia fixo.
- **Depois:** relê cada arquivo do repositório e compara o sha256 (conferir depois de gravar); grava `publicacao.json`
  na rodada e o `status.json`; põe o plano na reserva do histórico (`insumos.registrar_plano_publicado`: a semana
  publicada de novo troca o plano). A rodada mostra "Publicada no App" e se o `banco_dados.json` já tem a semana.
- **Administrador ou setor PCM** (`telas.pode_programar`, desde 16/10/2026; antes só `session["admin"]`: a senha de
  admin ou um e-mail de `NEXUS_ADMINS`). O commit não leva o e-mail de quem publicou (o repositório é público); quem
  foi fica no `publicacao.json` da rodada.
- **Token:** `NEXUS_PCM_GITHUB_TOKEN`. Desde 16/10/2026 o administrador cola em Base → Chaves das fontes, aba Nexus
  (`auth/chaves.py`; vence o ambiente e o `.env`, vale na hora, conferido no GitHub ao colar): o servidor não tinha
  nenhum, e a tela de publicar a W43 mostrava "sem token do GitHub" (o aviso agora diz onde colar: `publicar.SEM_TOKEN`).
  Depois, o ambiente e o `.env` do Nexus; no PC, o login do `gh` da máquina (`gh auth token`). Nunca é impresso. O
  mesmo token serve ao Quadro (semana em curso) e ao arquivo dos motivos.
- **Testar sem publicar:** a tela de confirmação lê o repositório de verdade (só GET). A cópia de conferência do
  Claude troca a sessão do GitHub por uma que recusa gravar. Testes: `tests/test_pcm_publicar.py` (GitHub falso).
- **OS 14331 (W42, 09/10):** 4 corretivas "Teste de comando remoto" de 6 h cada (a duração estimada no Fracttal; o
  total de horas da OS é 1,5 h por tarefa) que o motor forçou numa quarta da PR Norte 01: 24,5 h. O conserto é na
  origem (a duração no Fracttal) ou fixar as tarefas em dias diferentes no bloco 2; a conferência aponta a OS.

## Quadro da semana (`quadro.py`, `templates/pcm/quadro.html` e `reprogramar.html`, `static/pcm-quadro.js`; 09/10/2026)

Levi: "Eles tem essa visão [...] no site de PCM, gostaria que tenhamos uma visão dessa no Nexus também e consigamos
reprogramar tarefas que nem na imagem 1". É o quadro da aba Semana do painel do PCM (`novo.html`: `vSemana`, `cardHTML`,
`abrirDet`, a fila `rp*`), com as mesmas contas: colunas pelos dias que a semana tem, contagem e horas do conjunto
FILTRADO, cartões na ordem do relógio (40 por coluna; "mostrar todas" põe `todos=1`), turno pela hora de início (manhã
07–12, tarde 12–17, noite 17–07), "Nª sem" pelo campo de vezes, trajetória da tarefa pelas semanas do arquivo (OS + 60
caracteres da tarefa; vale a última da semana, como o `Map` do painel). Filtros: equipe, responsável, cliente, tipo,
situação, turno e busca, em cascata (seção acima). O gestor de contrato que entra pelo Fracttal já vem filtrado nele
(quando o nome casa com a coluna Responsável). Semanas: as do `banco_dados.json` e os rascunhos do Nexus (a rodada mais recente de cada semana que
ainda não começou e não foi ao App; `?rodada=` abre qualquer rodada, também as de prova).

- **A janela da OS** (Levi, 18/10/2026; `tests/test_pcm_quadro_janela_js.py` a abre no node): os cartões do topo são
  Tipo, Situação, Criticidade, Semanas na fila e Reprogramada (a seção "Situação da OS" de baixo saiu, e com ela o
  Status da OS, Em paralelo, Termografia, Origem e Etiqueta); Onde e Quem lado a lado e o Quando embaixo (o dia da
  semana com a data entre parênteses: "Terça (13/10)"); o motivo tem o título "Técnico não consegue fazer?", sem o
  "Sem motivo.", e o botão "Salvar motivo". A lista de motivos é como a do Fora da programação: só o nome (saiu o
  "(tira da programação)" do lado), o campo na cor do escolhido (vermelho tira, laranja não) e, quando tira, a linha
  "Tira a tarefa da programação." embaixo. As colunas dos cartões seguem o conteúdo (`repeat(5,auto)`): com cinco
  iguais, REPROGRAMADA passava da borda na janela de 580 px.

- **A semana do PCM vai do sábado 00:00 à sexta** (o processo, Levi com o programador do PCM: a programação nasce na quinta;
  supervisor e gestor de contrato olham e passam ao PCM; o PCM altera; no fim da sexta ela é gerada de novo e substitui;
  "o ideal é que inicie da meia-noite de sábado e finalize na sexta"). **Criadas após o plano** = OS com `dataCriacao`
  do sábado antes da segunda até a sexta (a data basta: o arquivo traz a hora de Brasília sem fuso; as criações se
  concentram das 8h às 17h). O painel corta na DATA da geração ou na sexta anterior, e contava a OS da sexta, que a
  geração da sexta já levou: W41 pelo painel 81/104/126/125/249 por dia, pelo sábado 46/84/112/111/180 (533).
- **Reprogramar = linha de observação**, a do `rpLinha` do painel (contrato com o motor e com o robô do PCM):
  `OS; não` (sempre a OS inteira), `OS; sem: nome da tarefa` (só aquela tarefa sai da semana; abaixo),
  `OS; dia[; ; turno]` (a OS inteira), `OS; dia; SIGLA; turno; só: equipamento` (MPA, MPS, MPT, MPM, MPQ e Handover: o
  nome do equipamento depois do último " - "), `OS; dia; nome da tarefa; turno` (as outras: o nome até a 1ª vírgula).
  Só segunda a sexta: o motor e o robô não entendem sábado (o painel oferece, e a linha volta "dia não reconhecido").
  `static/pcm-quadro.js` monta a mesma linha para mostrar na fila; o teste roda as duas (node) com os mesmos casos.
- **Tirar da semana = a TAREFA, não a OS** (Levi, 15/10/2026, urgente: "quando o PCM tenta tirar da semana uma tarefa
  aparece uma notificação de tirar todas as tarefas da OS, isso não pode acontecer"). O botão gravava sempre
  `OS; não`, copiado do painel do PCM (lá também só sai a OS inteira; "para tirar só uma parte usa-se sem:", que o
  PCM nunca usou nos dois arquivos). Agora vale o que está no **"O que"** da janela: a tarefa (o padrão é a do cartão)
  vira `OS; sem: nome da tarefa` (o nome até a 1ª vírgula: a vírgula separa palavras no `sem:`); "a OS inteira"
  continua `OS; não`; a OS com uma tarefa só na semana também sai pelo `não`. A confirmação diz o que sai e o que fica.
  **O `sem:` acha a tarefa pelo NOME** (contém a palavra, sem diferenciar maiúscula): tarefas de mesmo nome na OS saem
  juntas, e são muitas (W42: 92 das 128 OS com mais de uma tarefa repetem nome; a OS 15067 tem "MPM - QGBT" nas linhas
  do QGBT1, QGBT2 e QGBT3). A janela avisa ("está em 3 linhas da semana") e lista as de nome parecido que saem junto.
  Separar por equipamento pediria mudar o robô e o motor do PCM.
  Quem aplica: **semana em curso**, o robô (`atualizacao_semanal`, STEP A3) apaga as linhas da tarefa (agenda e
  `_Pendentes`), em qualquer OS, e não reposiciona nada (a linha não tem dia nem turno); e desde o `bd4f673` (15/10) o
  passo A2 dele não reinclui a tarefa tirada (nem a OS do `não`) como OS nova (seção "Horas por tarefa e zeladoria no
  motor"). **Semana que o Nexus gera**, o
  motor (`programacao_v7`) só aplica o `sem:` nas OS de plano (modo A: a tarefa nem é programada) e, como toda linha da
  OS vira "pin", a OS entra na semana e o resto dela ganha prioridade na fila da usina; na OS comum (modo B) ele ignora
  o `sem:` e programa a tarefa. Por isso a rodada roda o `geracao.aplicar_sem` depois do motor: a mesma exclusão do
  robô na planilha gerada (na OS comum fica o horário vazio na agenda; falhar ali derruba a rodada, para não publicar
  a semana com a tarefa que o PCM tirou). A tela Gerar mostra a linha em "OS com dia fixo", coluna "Tirar as tarefas
  com". Prova de 15/10 com o código REAL do PCM (os parsers do robô e do motor tirados do repositório pelo `ast`) e a
  `Programação Semana 42.xlsx` real numa cópia: `15067; sem: [Grid Co.] - MPM - QGBT, [Grid Co.] - MPM - Tracker` →
  o robô tira as duas e não move nada; o motor (modo A) tira QGBT ×3 e Tracker ×1; o `aplicar_sem` apagou 4 linhas, só
  da 15067 (1.986 → 1.982). Testes: `test_mescla_tirar_uma_tarefa`, `test_fila_tirar_uma_tarefa`,
  `test_tela_quadro_tira_uma_tarefa_da_semana_em_curso` e, no `test_pcm_geracao.py`,
  `test_sem_das_observacoes_tira_a_tarefa_da_planilha_gerada` e `test_rodada_aplica_o_sem_das_observacoes`.
- **A fila** fica no navegador (localStorage, por semana), como no painel. Ao gravar, a página manda só {os, tarefa,
  dia, turno}; o servidor refaz a linha com a tarefa e o tipo da SEMANA (`linhas_da_fila`): OS ou tarefa que a semana
  não tem, dia ou turno inválido barram a gravação inteira (nenhum texto livre chega ao arquivo do motor).
- **Para onde vai** (`destino`): semana em curso (de segunda a sexta dela) -> `Observacoes_Semana_Atual.txt` do
  repositório do PCM, que o robô aplica na rodada seguinte (reposiciona e empurra as conflitantes, tira a OS, puxa das
  pendentes); semana que o Nexus gera e ainda não começou (rascunho, ou com rodada do Nexus) -> as observações da semana
  no Nexus (bloco 2 da tela Gerar), que valem na próxima geração; semana gerada no PC do PCM (a W42) -> só "Copiar
  tudo", para o painel do PCM; semana que acabou -> só ver.
- **A mescla** (`mesclar`): a linha nova substitui a do MESMO alvo (OS, tarefas e "só:"); `OS; não` tira todas as
  linhas da OS; a OS inteira num dia tira as linhas por tarefa dela e o `sem:`; a linha por tarefa tira o `não` e, do
  `sem:`, a tarefa que ela põe de volta num dia (pelo "só:" na OS de plano, pelo nome na comum). O `OS; sem:` não mexe
  nas outras linhas da OS nem no `não`: junta as tarefas tiradas da OS numa linha só, a última da OS, levando o `sem:`
  escrito à mão numa linha de dia (o motor guarda só o `sem:` da ÚLTIMA linha da OS que tem um; o robô soma todos).
  A fila que volta da página já sai mesclada (`linhas_da_fila`), e na página a OS inteira apaga da fila o que havia
  por tarefa dela. O resto do texto fica igual e na mesma ordem.
- **O arquivo da semana em curso** vale para qualquer semana que estiver em curso: linha da semana passada se aplicaria
  à nova. O Nexus escreve a semana no cabeçalho (`# Semana 2026-W42: ...`); cabeçalho de outra semana = o que estava lá
  sai. Sem cabeçalho (gravado pelo painel do PCM): fica, a não ser que a pessoa marque para apagar. Em 09/10 ele tinha
  3 linhas `OS; não` do painel, sem semana.
- **Gravar é do PCM** (`telas.pode_programar`: administrador ou quem é do setor PCM, desde 16/10/2026); os outros
  montam a fila e copiam para mandar ao PCM ("passa para o PCM").
  A semana em curso passa por `reprogramar.html` (o que entra, o que o arquivo tem, como fica) e grava com o sha que a
  pessoa conferiu (mudou no meio: não grava, 409), relê e confere o sha256. O commit não leva e-mail (repositório
  público). Quem gravou o quê: `reprogramacoes.jsonl` na pasta de trabalho, e "Já gravadas para esta semana" na tela,
  À VISTA DE TODOS (só gravar é do PCM), cada uma com o lugar onde foi parar.
- **Onde o PCM vê a reprogramação** (Levi, 09/10: "Onde o PCM tem essa informação?", sobre a frase "vira linha de
  observação, que só o PCM grava"): a frase da fonte do quadro diz o lugar pelo nome, conforme a semana. Semana em
  curso: o `Observacoes_Semana_Atual.txt` do repositório do PCM (o robô aplica). Semana que o Nexus gera: as
  observações da semana no Nexus (Gerar a semana, bloco 2, com link). No painel do PCM a fila é só do navegador: vira
  texto que o PCM cola no painel do PC, que grava os arquivos de observação da pasta do PC e os manda ao repositório
  (`publicar_observacoes_github.py`) **sem ler o que está lá**: publicar ajustes pelo PC depois que o Nexus gravou apaga
  as linhas do Nexus (a confirmação avisa). Com o Nexus gravando, os ajustes saem só do Nexus.
- **Peso da página** (09/10, W41 real): 339 KB e ~160 ms com 200 cartões; as pendentes (1.697 na W41) vêm linha a linha
  só filtradas (até 150) ou a pedido (`pend=1`, 1,4 MB): os seletores de dia e turno saem de um `<template>` clonado pelo
  JS, e a lista de tarefas de cada OS vai uma vez em `oss` (antes, em cada cartão: 4,4 MB).
- **Provar:** `tests/test_pcm_quadro.py` (35 testes; 24 mutações em 09/10 e mais 12 no tirar tarefa em 15/10, todas
  pegas; o `aplicar_sem` está no `test_pcm_geracao.py`). Ver a tela: a cópia de conferência do
  Claude, com o armazém do PCM numa CÓPIA (`NEXUS_PCM_TRABALHO` no `app.config`: não é chave do `.env`, e sem isso ela
  lia o armazém real) e o GitHub que recusa gravar. Nunca testar clicando em Aplicar na semana em curso.

## A tela Gerar (`templates/pcm/gerar.html` + `_observacoes.html`, estilo em `static/pcm.css`)

Desde 05/10/2026 (Levi: "está confuso, separe por blocos"), em quatro blocos numerados, na ordem do trabalho: **1** o
que o motor precisa (insumos, em duas colunas, e "Importar da pasta do PCM"), **2** observações da semana (dias por
usina, OS fora, OS com dia fixo), **3** gerar em sombra, **4** últimas gerações. A semana se escolhe uma vez, no topo.

- **Dia de atendimento é verde SUAVE.** Tinta verde clara com texto verde = atende; contorno apagado = não atende.
  Até 05/10 o "atende" sem regra era cinza e a lista parecia desligada ("está tudo cinza"); o verde cheio que entrou
  no lugar, com borda e faixa verdes em toda usina, acendeu a lista inteira ("muito estourado, suavize"). Sem borda
  verde no cartão: a lista já é só de usinas marcadas.
- **A lista mostra só as usinas marcadas** (com dia restrito). As outras ficam na página, escondidas, e entram pelo
  "Adicionar usina" com os cinco dias: desmarcar um dia cria a regra `@usina` (Levi, 05/10: "quero que apareça só o
  que está marcado, o que não estiver só vai aparecer por um botão adicionar"). Usina mexida fica à vista até recarregar.
- **O padrão da semana é a última programação** (`insumos.observacoes_efetivas`). Semana sem nada salvo herda, da
  semana salva mais recente antes dela, só os dias por usina; OS fora e OS com dia fixo não passam. Semana salva,
  mesmo vazia, vale o que foi salvo. É herança de DADO: o `materializar` entrega ao motor o mesmo texto que a tela
  mostra, e a tela avisa "herdados da W41". Antes, a semana nova começava vazia e o PCM refazia as 46 restrições.
- O JavaScript do editor depende dos ids e classes (`#obs`, `#obs-form`, `.obs-ufr`, `.obs-dia`, `#obs-por-dia`,
  `.obs-bloco--usinas`...): a legenda usa `.obs-amostra` de propósito, porque um `.obs-dia` fora de uma regra vira
  clique de edição.
- Ver a tela sem login no navegador: renderize no processo (`test_client` + `session_transaction`, logado) e abra o
  HTML ao lado de uma cópia do `static/`. O Nexus em produção não recarrega template: depois de mudar, reinicie.

## Gestão PCM (`gestao.py`, `templates/pcm/gestao.html`, `/t/pcm/gestao`)

Levi (07/10 e 08/10/2026): "traga a visão de acompanhamento de manutenção do aplicativo para o Nexus conforme prints".
É o bloco **"Manutenções — Plano & Fila"** da aba Gestão PCM do painel do PCM (`js/preventivas.js` do gridco-pcm-data),
com os filtros de cima da aba (Cliente, Usina, Equipe cluster, Responsável; um de cada, sem diferenciar maiúscula, em
cascata desde 09/10/2026). Só
lê: nada vai ao banco nem ao Fracttal. Os controles vão pela URL (`modo`, `tipo`, `dim`, `col`, `val`, `mes`, `q`,
`ordem`/`desc`, `pend`, `ordemf`/`descf`; o drill da fração é `drill` + `dt`, porque `usina` é o filtro de cima).

- **O aviso de onde vêm os dados** (o `gestao_pcm.json` e, sem a chave, a nota da Gerencial) mora num ícone à direita
  do topo e abre ao clicar (Levi, 18/10/2026); o que é falha de verdade (a última leitura boa, a chave que não abriu)
  segue à vista, em amarelo.
- **A célula tem altura fixa** (18/10/2026): o `<button>` da pendente na linha da usina herdava o `font` e perdia o
  `line-height`, e o fundo no tom ficava com 19 px no meio da célula de 34 ("parece que aparece só no meio").
- **De onde vem:** o `gestao_pcm.json` (as tarefas do Fracttal desde 01/01, que o robô do repositório do PCM regrava;
  14,7 MB e 28,6 mil tarefas em 08/10) e a planilha da Gerencial, o `mpas.json` do mesmo repositório, **cifrado**
  (AES-GCM + PBKDF2; o repositório é público). A Gerencial abre com `NEXUS_PCM_MPAS_SENHA` (a mesma senha que o painel
  pede; quem tem é o dono do painel do PCM, e hoje está vazia), decifrada só em memória.
- **Regra de ouro (do painel):** concluída é o **estado da TAREFA** ("Finalizada"), nunca o status da OS.
- **Plano:** % de tarefas finalizadas por grupo ▸ usina, nos três últimos meses. Preventiva conta no mês da Data
  Programada; demanda (corretiva, emergencial, religamento com o remoto, inspeção, preditiva, administrativa, zeladoria,
  handover) no mês da **criação**; "Teste" e preventiva sem sigla ficam fora. **MPA e MPS em fração** feitas/total (50%
  de 4 anuais não é 50% de 200 mensais), e a fração abre a Fila daquela usina. Geral = as quatro preventivas (as
  Corretivas ficam fora). Faixas do `preventivas.js` (no dado, na `faixa`, e na prova): abaixo de 40% vermelho, 40% a
  99% amarelo, 100% verde. **A célula na tela** (09/10/2026, Levi, com o print do painel NOVO do PCM, o `novo.html`:
  "uma visão parecida com essa, tanto percentual quanto acompanhamento e destacado por cor") segue o `gpCel` do painel
  novo: o % em negrito e, ao lado, feitas/total (inclusive MPA, MPS, Corretivas e Geral); o fundo é o `tom` (90% ou
  mais verde, 50% a 89% âmbar, abaixo de 50% vermelho) a 15% sobre a superfície, com o texto neutro; Pendentes em
  vermelho quando há; números à direita. Antes disso, a 1ª tentativa do dia (fundo translúcido e texto colorido) virou
  uma colcha de bege, vinho e oliva nos dois temas, e a 2ª (só o número colorido e uma barra) não era a visão que ele
  queria. No escuro o âmbar é o laranja (o amarelo a 15% sobre o navy dá oliva); o verde é o do semáforo (`--ok`),
  também na Fila (selo Concluída, KPI, o check).
- **Fila:** o envelhecimento das MPA e MPS. Com a Gerencial: Prevista × Programada, atraso pela Prevista (1–30, 31–90,
  mais de 90 dias), criticidade, última observação datada do log, e os KPIs são filtros. **Sem a chave** é o lado do
  Fracttal (uma linha por OS, atraso pela Programada) e a tela diz isso numa nota informativa, não num aviso: falta de
  chave não é falha. Chave que não abre ou arquivo fora do ar é falha, e vai em amarelo.
- **Par do topo** (nunca média única): Rotina (MPM + MPT do mês corrente), grandes atrasadas e a mais antiga, críticas
  sem data futura. Sem a Gerencial, as atrasadas e as concluídas do lado do Fracttal (o painel só mostra o cadeado).
- **Diferenças de propósito com o painel:** a OS sem "#"; o "hoje" em Brasília (o painel usa o dia UTC para
  "atrasada": entre 21h e meia-noite ele já conta o dia seguinte); e a hora do "atualizado em" em Brasília (o robô
  grava o `geradoEm` em UTC sem fuso e o painel o mostra como hora local: 12:42 lá é 09:42 aqui). Dois defeitos do
  painel que o Nexus não copia (revisão de 08/10): a dica "sem preventiva no período" nas células de grupo e do TOTAL,
  que têm tarefa (aqui ficam sem dica), e o cabeçalho Tipo da Fila, que lá não ordena nada (aqui ordena pelo tipo).
- **As tarefas da célula** (Levi, 12/10/2026: "Na versão antiga ao clicar em cima do % do que tem pendente aparecia
  as tarefas pendentes, resolva isso por gentileza no Nexus! Faça maior e mais bonito"; 18/10/2026: a de 100% "ia para
  essa tela confusa", que pedia "uma barra lateral com uma informação mais fácil de ler"): na linha da usina, TODA célula
  com tarefa (a de 100% também; MPA e MPS inclusive; o Geral) e o número da coluna Pendentes abrem um **painel lateral**
  (640 px; no celular, a tela toda). Em cima, as que não estão Finalizadas, por OS: as atrasadas primeiro, depois pela
  Data Programada; embaixo, as **Finalizadas** por OS, da que terminou por último (a `dataFinal`), recolhidas quando há
  pendente e abertas quando a célula está em 100%; o status da OS (na grafia do card do OS Creator: "Em processo" → Em Processo, "Verificação" → Em
  Verificação, "Finalizados" → Concluída, com o aviso "OS finalizada no Fracttal com a tarefa em aberto"), Atrasada,
  a programada e o Fracttal no ícone; a OS abre o **card dela no Nexus** (`oscreator/card_os_abrir.html`). O nome da
  tarefa sem o "[Grid Co.] - MPM - " (o inteiro no title); a mesma atividade repetida na OS (uma por ativo: o arquivo
  não traz o ativo) vira uma linha com "×4". **MPA e MPS abrem o painel, e a Fila daquela usina é o link "Ver na
  Fila" dele** (o `data-fila` da célula; antes a fração ia direto à Fila), e grupo e TOTAL não abrem lista. A conta é `gestao.pendentes` (a regra `classificar`, a mesma da `base`, e os mesmos recortes da matriz:
  tipo, mês, busca e os filtros de cima): o número da lista é o da célula, conferido em toda célula de usina pelo teste.
  Endereço: o da própria tela com `pu` (usina) e `pc` (coluna; `*` = Pendentes), pedido por fetch; coluna que a matriz
  não tem = 404. A `classificar` saiu da `base` sem mudar conta: a prova de 12/10 (356 casos, 434.725 valores) bateu
  célula a célula. Prova: `tests/test_pcm_gestao_pendentes.py`.
- **Fila: ordem do Atraso** é a do painel: a 1ª ordem (seta para cima) já põe a MAIS VELHA no alto
  (`?modo=fila&pend=atraso&ordemf=atraso`); `descf=1` inverte e põe a mais nova primeiro.

**A prova** (rode a cada mudança no `gestao.py` ou no `preventivas.js` do painel; precisa do node):

```
python -m nexus.pcm.prova_gestao                      # JS e JSON do repositório do PCM
python -m nexus.pcm.prova_gestao --painel C:/caminho/gridco-pcm-data --dados gestao_pcm.json
```

Roda o próprio `preventivas.js` (mais o recorte do `app.js` que ele usa) num `vm` isolado do node, contra o mesmo JSON,
com o relógio dos dois lados parado no mesmo instante, e compara linha, célula, faixa, fração e dica do mouse (Plano),
linhas na ordem, colunas e KPIs (Fila) e o par do topo: 178 casos sem a Gerencial e 178 com. Sem a senha, a Gerencial
da prova é **sintética** (feita das OS de MPA/MPS do JSON, com todos os casos da regra): prova a transcrição; os números
reais da Fila com a Gerencial só se provam com a senha. Nunca imprime nome de pessoa.
- **08/10/2026:** gestao_pcm.json de 08/10 12:42 (28.641 tarefas), `preventivas.js` sha256 `1ff54695d5a5`: 448.575
  valores comparados, **0 divergências**. Ela achou duas diferenças, já corrigidas: o navegador lê 30/02 como 02/03 (o
  Python recusava a data) e o KPI "concluídas" (`pend=concl`), que a URL descartava. Mudar a faixa de 40% para 41%
  dá 3 divergências: a prova pega. Depois da revisão (dica do grupo e ordem por Tipo, acima), rodada de novo com o
  mesmo JSON e o mesmo JS: 356 casos, 429.055 valores, **0 divergências** (150 s; sem a ordem "tipo", que é diferença
  de propósito).

**Desempenho** (08/10, `test_client`, JSON do GitHub, quatro rodadas): fria 1,3 a 2,5 s, conforme a rede (baixar
~0,9 s ou mais + `json.loads` 0,32 s + contas ~0,1 s); quente 6 a 33 ms; um filtro de cima novo, 110 a 190 ms na primeira
vez; a conferência de 5 em 5 minutos, com o 304 do GitHub, 34 a 73 ms (antes do ETag, os mesmos 1,3 s da fria). Com
`NEXUS_PCM_GESTAO_FONTE` num arquivo LOCAL não há cópia em memória: cada clique relê os 14,7 MB (~0,4 s), então medir
com arquivo local não diz nada do servidor. As contas ficam guardadas pela versão do arquivo (`dataHash`) e pelos
filtros de cima (`telas._G_CACHE`); a Fila, por meio dia (o atraso conta do meio-dia). Versão nova do arquivo limpa
tudo da velha: cada uma prende ~49 MB de tarefas.

**Não veio (a aba Gestão PCM do painel tem mais blocos; esperam o Levi dizer se eram os dos prints):** os KPIs do topo
da aba (Visíveis, Finalizadas, Em aberto, Atrasadas), a árvore Cliente ▸ Usina ▸ Tipo das tarefas (com "Não
finalizadas no período" e a lista "Só atrasadas"), "Confiabilidade por ativo" (MTBF, MTTR, disponibilidade, do
`confiabilidade.json`), "Tempo médio de reparo por Equipe Cluster" e o Relatório Executivo. Dos filtros de cima, não
vieram Tipo, Etiqueta, Estado, OS, Solicitação e Período.

## Armadilhas já vividas

- **Endereço nunca a partir da raiz** (porta única, 09/10/2026): debaixo do `/nexus` (o servidor até a fase 4; hoje na raiz, e o prefixo é a volta) um
  `/t/pcm/...` cru caía na plataforma de Performance. Os links e formulários de Gerar, Publicar, Quadro, Reprogramar e
  Semana saem com `{{ raiz }}`/`url_for`/`|na_raiz`; os redirecionamentos de `telas.py`, com `na_raiz` (só a parte do
  caminho: a consulta montada por `urlencode` vem depois).
  Regra completa em `nexus/casca/CLAUDE.md` (o prefixo `/nexus`); o esquecimento quebra `tests/test_prefixo.py`.
- **Gerar duas vezes a mesma semana distorcia tudo:** na S40, 415 tarefas viraram reprogramadas, e todas ganharam +1
  no "Nº vezes". Por isso a rodada parte do histórico de **antes** da semana (`historico_banco.montar`: só as semanas
  anteriores; na reserva, `geracao.preparar_historico`).
- **O arquivo de histórico do PC não é registro do que foi a campo:** guarda toda geração (a S41 de 02/10 08:26, que
  nunca foi ao campo, está lá), perdeu a W35 inteira e não se corrige sozinho. Daí o histórico vir do banco.
- **Carga máxima do dia: 70% (16/10/2026, já na W43, que o PCM regera pelo Nexus à noite; Levi: "70% HH por dia" e
  "quero que funcione para o w43"):** o motor do PCM
  (`CARGA_MAX_DIA`) programa até 6,15 h por equipe e dia (era 80%, 7 h); a noite segue em 80%. A conferência
  (`comparar.CARGA_MAX_DIA`, `CAPACIDADE_H`, `DIA_DO_MOTOR_MIN`) usa a mesma conta, e o teste de contrato prende as duas.
  Na W43 com a leitura das 12:23: de 1.232 para 1.220 blocos e 10 tarefas a mais na pendente (a maioria dos dias de
  equipe já não enchia; 19 passam de 6,15 h pelas corretivas forçadas). Junto, o robô do PCM deixou de mudar a tarefa de
  dia (rolagem desligada, cascata da OS nova só no mesmo dia): a tarefa de sexta fica no dia dela até o fechamento.
- **Cota do Fracttal:** 200 pedidos por minuto para a **empresa inteira**, divididos com o App de Campo. O motor anda
  a 1 por segundo, e a tela pede confirmação no horário de campo (seg a sex, das 06h às 18h). Cada leitor do motor tem
  a sua variável de ritmo: o `gerar_bd_via_api` lê a `FRACTTAL_INTERVALO_S` e o `fonte_bd_api` (a leitura da semana,
  5 páginas em paralelo) a `PROG_API_INTERVALO_S`, que sem valor fica em 0,42 s (~143/min). Até 16/10/2026 o Nexus só
  mandava a primeira, e a W43 de prova das 15:14 levou HTTP 429 em 9 s, com a cota já quase cheia de outros: o
  `_ambiente` manda as duas, e o teste confere toda variável `*_INTERVALO_S` que os leitores leem. Motor novo do PCM com
  outra variável de ritmo quebra o teste.
- **Dois Fracttal no mesmo processo se quebram:** o `FRACTTAL_BASE_URL` do motor tem `/api/` e o do OS Creator não.
  Por isso o motor roda em subprocesso, com ambiente próprio e sem as variáveis `NEXUS_*`.
