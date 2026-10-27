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
   rodada (a "sombra": a planilha `saida/sombra.xlsx` e a conferência). Nada vai ao campo. A planilha da rodada **baixa
   pela tela** (Levi, 19/10/2026: "tem que ter a opção de baixar!"): "Baixar a planilha" na rodada aberta e "Baixar" em
   cada linha das Últimas gerações (`/t/pcm/gerar/planilha?rodada=`, `geracao.planilha`; o arquivo sai como
   "Programação Semana NN - rodada AAAAMMDD-HHMMSS.xlsx"). Ela mora em `dados/pcm/geracoes/<rodada>/saida/` no servidor.
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
| `fonte.py` | lê o `banco_dados.json` do App (a semana que está valendo) e, para a Gestão PCM, o `gestao_pcm.json` e o `mpas.json`; cópia de 5 min e, passado isso, confere pelo ETag (304 = segue a cópia, sem baixar de novo); na cópia em memória, o `cliente` já vem pelo nome do cadastro (`clientes.py`) |
| `clientes.py` | **o nome do cliente é o do cadastro do Nexus** (18/10/2026, seção abaixo) |
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
| `inventario/` | **o inventário do almoxarifado** (26/10/2026, em construção): `estoque.py` é o adaptador do estoque do Fracttal, a única porta de leitura e gravação de saldo, régua e peça; `contas.py` são as contas (situações, contado efetivo, substituição, janela de aprovação; puro); `leitura.py` lê as contagens do App e o estado de cada uma pelos eventos; `revisao.py` é a aba Inventário (a lista, a contagem aberta com o Sistema × Contado × Δ e a revisão do PCM), com as rotas em `__init__.py`; `gravacao.py` grava o lote aprovado no Fracttal em segundo plano, por sessão de ajuste; `regua.py` é a régua de mínimo e máximo e `curadoria.py` o fora do catálogo; a auditoria é o `revisao.montar_auditoria`; `ponte_os.py` é a ponte com o login do Fracttal (as rotas de `/os/_nexus/inventario`, a ÚNICA porta de tudo o que lê ou grava no Fracttal: o lote, gravar, continuar, encerrar, a régua acordada, cadastrar a peça); o livro `nexus_almoxarifado_inventario` (eventos, régua e curadoria) é o `nexus/dados/fato_inventario.py`. As seções abaixo |
| `motor/` | **cópia idêntica** do motor do PCM: **não edite** (mudança de regra entra no repositório do PCM e é copiada; veja o `README.md` de lá); hoje a do `cb8239c` (23/10/2026: a MPM da última semana do mês vai para os dias livres antes de ser forçada no dia da usina, e o preenchimento dos dias livres respeita o dia fixo da usina e o feriado municipal) |

## O nome do cliente é o do cadastro do Nexus (`clientes.py`; 18/10/2026)

Levi: "Use o nome do cliente no Nexus como principal". Os arquivos do PCM tiram o cliente do nome do site no Fracttal
("Cliente - Usina - UF"), e a grafia de lá não é a do cadastro: "Utragaz", "RenoGrid", "Greenyellow" e "Semp" (no
cadastro, Ultragaz, Renogrid, GreenYellow e SEMP). Achado ao provar a semana da Visão do responsável contra o Fechamento
do PCM: os números batiam cliente a cliente, o nome não.
- **Como troca:** o mesmo nome do cadastro sem diferenciar maiúscula, acento e espaço; e o erro de grafia pelo de-para
  do Fracttal no cadastro (o site liga à usina, e a ficha da usina tem o cliente), só quando todas as usinas com aquele
  começo de site são do mesmo cliente. O que não casa fica como veio (o nome composto da planilha de operações,
  "Thopen;#Renogrid", e os clientes que não estão no cadastro). Por ID, não por palpite.
- **Onde:** o `fonte` troca o campo `cliente` na cópia em memória de todos os arquivos (Gestão PCM, Fora da
  programação, relatórios, Acompanhamento, relatório executivo); o Quadro da semana na semana da rodada; as Observações
  da semana; e a marca antiga do Fora da programação, que guarda o cliente de quando foi feita.
- **Só o que o Nexus mostra:** o arquivo do PCM e o que o Nexus manda ao App e ao PCM (a planilha da rodada, o
  `Fora_da_programacao.json`) não passam por aqui. O filtro de cliente que alguém guardou com a grafia antiga ("Utragaz")
  deixa de achar a usina.
- **Sem o banco** (teste sem o banco falso, falha de rede): os nomes ficam como vieram; o banco que falhou é tentado de
  novo em 5 min. O mapa fica 10 min em memória por app. **Medido em 18/10:** 17 nomes em 1,6 s; a única troca pelo site
  é "Utragaz"; os arquivos lidos já saem só com os nomes do cadastro.

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
  mudou, e mudar o "tira" de motivo com tarefas pede confirmação. **A etiqueta do Fracttal de cada motivo** (Levi,
  19/10/2026: "ligar a uma etiqueta do Fracttal para quando o técnico justificasse etiquetaria aquela OS"): a coluna
  "Etiqueta no Fracttal" guarda o NOME (`dim_motivo.etiqueta_fracttal`, no fim), com as etiquetas que já estão nas OS
  (o gestao_pcm.json) de sugestão e qualquer nome aceito. A sugestão é uma lista do Nexus (`static/pcm-etiqueta.js`:
  filtra sem acento, setas, Enter, Esc, "Sem etiqueta" limpa), não o `<datalist>` do navegador, que abria fora do estilo
  e torto (Levi, 19/10: "tá bugadasso"); vai no `Fora_da_programacao.json` (`motivos[].etiqueta`).
  Quem etiqueta é o App, com o login do técnico (a justificativa chega ao Nexus pelo servidor do App, sem esse login):
  ao justificar, põe a do motivo; ao trocar ou tirar a justificativa, tira a antiga (decisões do Levi, 19/10); só a
  justificativa do técnico etiqueta (a marca do PCM no Nexus, não). O contrato: `app-campo-docs/_propostas/etiqueta-motivo/LEIA.md`.
  **A nota da OS ao escolher o motivo** (20/10/2026, Levi: "quando selecionar o motivo vai preencher na nota da OS a
  data, o nome da tarefa, o ativo e o motivo de não fazer a tarefa"; "a justificativa do técnico também deve estar na
  OS"): uma linha no FIM da nota da OS no Fracttal, o que já existe fica. O formato é o do Levi (25/10/2026), uma linha
  por justificativa: `[21/10/2026 14:32] - [<tarefa da programação>] - <motivo>`, mais ` - [<justificativa>]` só quando
  há texto (quebra de linha e espaço repetido viram um espaço). O ativo não entra. As justificativas se juntam com uma
  quebra de linha, sem linha em branco entre elas; as notas antigas, no formato de 3 linhas, ficam como estão. O App
  escreve a MESMA linha (`_fora_nota_linha`/`_fora_nota_juntar`, v300), e os dois testes usam os mesmos exemplos. Ao escolher (marcar ou trocar)
  no Nexus, o Nexus escreve (`nota_os.py`, na janela do Quadro e na troca do Painel) com o login do Fracttal de quem
  marcou: o login do Nexus pelo Fracttal abre a sessão do OS Creator da pessoa (`ponte.sessao_do_os`), e o
  `api.editar_nota_os` reescreve a nota inteira, por isso lê a atual antes. A observação editada e o motivo tirado não
  escrevem; quem entra pela senha não tem o login e a resposta diz que a nota não saiu; a falha na nota nunca derruba a
  marca (a janela e o aviso dizem o resultado). A justificativa do técnico, o App escreve com o login dele, com a mesma
  linha (`app-campo-docs/_propostas/nota-motivo/LEIA.md`). Prova: `tests/test_pcm_nota_os.py`. A lista do
  backoffice, de quem abre o Gerar a semana (como as observações).
- **Pelo App** (`motivos_app.py`, a rota `POST /t/pcm/motivos/app`, pública só para quem assina, como a das fotos dos
  extintores): corpo JSON {os, codigo, tarefa, motivo (id; null = tirar), obs, tecnico_hmac, tecnico_nome}; cabeçalhos
  `X-Nexus-Ts` (epoch) e `X-Nexus-Assinatura` = HMAC-SHA256 de "<ts>." + o corpo cru, com a chave derivada da
  `NEXUS_PESSOA_HMAC` (rótulo `nexus:pcm:motivos-app`; nenhuma configuração nova); janela de 15 min. A tarefa tem de
  estar na programação publicada (comparada como o motor: sem acento, caixa e espaço a mais) ou aberta na Gestão PCM (a OS
  avulsa do App, com o código que o App mandou); senão 404. Grava com origem `app` e quem marcou pelo `tecnico_hmac` (o
  nome só cifrado; o painel e a janela mostram "(App)"), mexe na marca da OS quando é ela que vale (como a janela do
  Quadro) e agenda o arquivo do robô (fora do pedido, abaixo). Respostas: 200 {ok, gravou, marca, arquivo ("em
  instantes" ou "sem mudança"), arquivo_em_dia (null, por compatibilidade)}; 400 pedido fora do
  formato ou motivo que não existe; 401 assinatura ou hora; 404 tarefa; 503 sem a chave, banco fora ou a
  justificativa na fila (abaixo: ela é gravada assim mesmo). Testes:
  `test_o_tecnico_marca_pelo_app` e `test_o_app_sem_assinatura_ou_com_tarefa_que_nao_existe_nao_grava`.
  **O App não segura o Nexus** (22/10/2026; `motivos_app.entregar`, `tests/test_pcm_motivos_app_sem_travar_22_10.py`):
  das 13:51 às 14:08, com o servidor no swap, cada gravação no livro levava minutos, o servidor do App desiste em 20 s
  e manda de novo, e 7 justificativas viraram 46 envios, cada um numa das 8 threads do Nexus esperando a vez de gravar
  (Raio-X das 14:02: 6 de 8 threads nesta rota; o Nexus parou para todo mundo). Agora a justificativa entra numa FILA
  na 1ª tentativa e um gravador por trás (a thread `nexus-motivos-do-app`) grava as que esperam juntas, numa leitura e
  numa gravação do livro (`motivos.marcar_lote`; a recusa ou o defeito de uma não derruba as outras). O pedido espera a resposta
  até 15 s (o App desiste em 20) e, com dois já esperando, responde 503 na hora; nos dois casos a justificativa é
  gravada assim mesmo. O reenvio (o mesmo envio: OS, ativo, tarefa, motivo, observação e técnico) não entra de novo na
  fila: espera a mesma, ou recebe a resposta guardada dela (só a boa, por 30 min). A leitura que falha DENTRO da
  gravação também é 503 (`motivos.BancoFora`): era 400, que o App toma por recusa definitiva e tira a justificativa do
  aparelho. E o reenvio do que o mesmo técnico já gravou HOJE pelo App volta `gravou: true` sem gravar nada (`marcar`,
  `repetida`; vale depois de um reinício, quando a resposta guardada se perde): o App só escreve a nota e a etiqueta no
  Fracttal com `gravou`, e naquele dia as 7 foram gravadas pelo envio que ele já tinha dado por perdido e nenhuma
  ganhou a nota nem a etiqueta (a linha que já está na nota ele não repete). Pelo Nexus (Quadro, painel) nada mudou.
  Simulado em escala (as 7, o banco lento, o App desistindo e reenviando até 8 vezes): antes 56 threads presas e o
  Nexus livre só em 85 s, nenhuma com "gravou" no Sincronizar; depois 3 threads, livre em 8 s, as 7 com "gravou".
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
  o painel mostrava 0; o Levi escolheu listá-las aqui). **A que não tira fica no painel só no dia em que foi
  justificada** (20/10/2026, Levi: "Se o motivo não tira da programação deve ir para o painel só se o motivo for no
  mesmo dia que eu estou vendo, se já passou e a tarefa já voltou para programação deve ir apenas para histórico"): pela
  justificativa mais nova do motivo (`telas._ultima_justificativa`, no relógio das marcas, `M._agora`); no dia seguinte
  ela sai do painel e o Histórico diz "Seguiu na programação"; justificada de novo hoje, volta. "Do App" é pelo MOTIVO (`origem_motivo`/`quem_motivo` de
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
semana, Gestão PCM, PCM 52 Semanas, Torre de controle e Almoxarifado (Insights, 52 Semanas e Torre de controle ainda
são placeholder; o Almoxarifado, desde 25/10/2026, ocupa o lugar do placeholder "Peças e sobressalentes", com o mesmo
endereço `/t/pcm/pecas`). **A Semana saiu em 12/10/2026
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

## Almoxarifado (`almoxarifado.py`, `templates/pcm/almoxarifado.html`, `/t/pcm/pecas`; 25/10/2026)

Levi, 25/10/2026: "No fractall temos almoxarifado, gostaria de uma visão para a gestão desse almoxarifado na parte de
PCM"; a prévia com os dados reais foi aprovada no mesmo dia. Desenho e plano: `docs/superpowers/specs/` e
`docs/superpowers/plans/2026-10-25-almoxarifado*`. Do setor PCM (outros pela marca em Base → Acessos).

- **De onde vem:** o saldo do Fracttal só sai item a item (574 chamadas por leitura); o App de Campo já faz essa
  varredura uma vez por dia, a partir de 00:00 de Brasília, e publica 4 livros (o pacote
  `app-campo-docs/_propostas/almoxarifado-nexus`). O Nexus não chama o Fracttal. As contas e o contrato estão em
  `nexus/dados/almoxarifado.py`, os MESMOS da carga do histórico (`nexus/dados/CLAUDE.md`, linha Almoxarifado).
- **O que a tela mostra:** 6 números (almoxarifados, peças com saldo, abaixo do mínimo e no limite, sem mínimo,
  avariadas, lançadas pelo App com as recusadas) e 5 abas: Reposição, Por almoxarifado, Catálogo e saldo, Consumo nas OS
  (tudo desde o início, Levi 25/10/2026) e Cadastro a corrigir. Desde 26/10/2026, as quatro partes do inventário (Inventário, Mínimo e máximo, Curadoria e Auditoria) vêm logo depois, juntas, como links para outras páginas (as seções do inventário, abaixo). Filtro na própria página (`filtro-local.js`).
- **As contas:** abaixo = mínimo > 0 e saldo < mínimo; **no limite** = saldo igual ao mínimo, separado porque o Fracttal
  costuma ter o mínimo igual ao saldo (25/10: 0 abaixo, 54 no limite); sem mínimo = mínimo 0; zerada = saldo 0.
- **Número pela metade não vai:** o saldo é o do ciclo mais novo do App só com Ciclo, Itens e Saldo do mesmo ciclo e 90%
  da lista lidos; senão, o último ciclo aplicado no histórico do Nexus, com o aviso; sem ele (o ensaio), só o aviso.
  Ciclo com mais de 36 h: o aviso com a data. Item com Lido = Não: "não lido neste ciclo", nunca "sem saldo". O consumo
  vem do `fato_peca_lancada`; enquanto ele não existe, do livro Peças do App (90 dias), com a nota.
- **A revisão de 25/10/2026** (cada item com teste em `tests/test_pcm_almoxarifado.py`, `test_rev_*`): livros do App que
  chegaram pela metade e o ciclo anulado no Nexus também vão para o último ciclo bom, com o aviso; saldo vazio é "não
  informado" (fora da Reposição e das contas; o cartão conta à parte); na reserva, o catálogo é só o dos itens da foto
  (a dimensão guarda todo item já visto); o Fracttal listando menos de 90% dos itens do ciclo anterior dá um aviso; a
  busca compara sem acento e sem caixa (o `data-f-busca` vai normalizado, como nas outras telas).
- **O almoxarifado de teste fica de fora (26/10/2026):** a chave `NEXUS_ALMOX_TESTE_IDS` (IDs do Fracttal separados por
  vírgula; a prova das gravações do inventário é num almoxarifado de teste, nunca num de usina: o `TESTE-INVENTARIO`, id
  134082) tira as linhas dele do Saldo, nas telas (`_do_app`, `_do_nexus`), na Base → Ligações (`ligacoes.fontes`) e no
  histórico (`carga.gerar_almoxarifado`). O filtro vem DEPOIS da conferência dos livros (`conferir_ciclo` conta as
  `Linhas de saldo` do livro inteiro, as do teste incluídas). **O consumo (`_consumo`, o livro Peças) NÃO é filtrado:** o
  almoxarifado de teste é só para ajuste de inventário, e uma peça lançada nele por uma OS entraria nas contas
  (lançadas e recusadas). Prova: `tests/test_pcm_inventario_contrato.py`. O contrato do livro das contagens do
  inventário (`almoxarifado_contagens_app_campo`, 14 colunas, a última o `ID da linha`, a chave da linha junto da
  contagem) mora em `nexus/dados/almoxarifado.py` (`COLUNAS_CONTAGENS`, `contado`).
- **Como provar:** `tests/test_pcm_almoxarifado.py`; no navegador, a cópia de prova com os 4 livros montados na memória
  a partir de uma cópia da tabela do App (fora do repositório) e o cadastro real por GET (25/10: 12 almoxarifados, 218
  peças com saldo, 54 no limite, 22 sem mínimo, 5 avariadas, 3 lançadas e 13 recusadas).

## Inventário do almoxarifado: o fluxo, as regras, a chave de teste e como provar (`inventario/`; 26/10/2026)

Levi, 26/10/2026: o técnico conta as peças no App, o PCM revisa e aprova no Nexus, e o Nexus grava o saldo contado no
Fracttal, no login de quem aprova. Desenho: `docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md`; o que o
Fracttal aceita de verdade: `...-passo0.md`. Cada parte tem a seção dela abaixo; aqui, o caminho inteiro.

**O fluxo:**
1. **O App** (a sessão do App, pelo contrato de 14 colunas): o técnico conta às cegas (sem ver o saldo) e o App publica
   `almoxarifado_contagens_app_campo`. O que ele acha fora do catálogo e o genérico que identifica vão como linhas próprias.
2. **Inventário** (`/t/pcm/pecas/inventario`): a lista das contagens, com o estado de cada uma pelos eventos do livro. Abrir uma
   mostra o que o técnico contou; o Sistema (lido NA HORA no Fracttal), o Δ, a situação e os seis grupos chegam pela ponte
   (`GET /os/_nexus/inventario/<id>/lote`), com o botão "Gravar N alterações".
3. **Revisão:** tirar uma peça do lote, corrigir o número ou pedir a recontagem, sempre com o motivo (cifrado). Só grava no
   livro do inventário. **Curadoria** (`.../curadoria`): o achado fora do catálogo (cadastrar no Fracttal pela ponte, é a peça X,
   descartar) e o genérico (confirmar o específico); a quantidade entra no lote da contagem.
4. **Gravar:** a ponte confere o N e a assinatura do lote que a tela mostrou, relê o saldo e começa a gravação em segundo plano,
   por sessão de ajuste do almoxarifado (lotes de 50; a peça que se moveu depois da contagem vira conflito e não grava). A página
   acompanha pelo `estado.json`; a parada mostra o "Continuar" a quem aprovou (e o aviso forte se o almoxarifado ficou travado),
   e o "Encerrar" fecha a que ninguém vai continuar.
5. **Mínimo e máximo** (`.../regua`): a sugestão, o recomendado (Grid, só no livro) e o acordado (cliente), o único que vai ao
   Fracttal, pela ponte.
6. **Auditoria** (`.../auditoria`): todos os eventos do livro, com o filtro por tipo e a busca.

**As regras que valem em todas as partes:** tudo o que lê ou grava no Fracttal roda na ponte `/os/_nexus/inventario/...` (o cookie
do login dele só chega em /os); só o administrador e o setor PCM (`pode_programar`) leem o saldo, revisam e gravam, e só de uma
página do Nexus; quem entrou pela senha de administrador não é uma pessoa e não revisa nem grava (a auditoria ficaria sem dono);
tudo o que grava no Fracttal (gravar, continuar, encerrar, a régua, o cadastro) confere a pessoa (`ponte_os._estoque_da_pessoa`: a
senha 409, a conta do Fracttal do cookie que não é a pessoa da sessão do Nexus 409; a régua e o cadastro não conferiam até a
revisão final de 27/10/2026);
número pela metade não vai à tela (sem o Sistema, só o contado); o motivo e o texto livre vão só cifrados (a API do banco é
aberta), e a pessoa como código (`pessoa_hmac`) e `pessoa_id`; a contagem com mais de 90 dias, do futuro ou fora do contrato não
se aprova; o deploy espera o lote aberto (`DEPLOY.md`, seção 8).

**A chave de teste: `NEXUS_ALMOX_TESTE_IDS`** (IDs do Fracttal, por vírgula; no servidor, `134082`, o almoxarifado
`TESTE-INVENTARIO`, com a peça `SP-TST-001`, id 53248312). O almoxarifado de teste fica FORA das telas (o Saldo, a lista do
Inventário, a régua e a Auditoria) e do histórico, e é o único onde a curadoria aceita a sigla `TST`. Consequência: **a prova no
Fracttal de verdade não passa pelas telas do servidor**; ela roda numa cópia de prova em que o almoxarifado de teste aparece (o
script desliga o filtro só na cópia e deixa a sigla `TST` para ele), com o livro do inventário num arquivo
(`NEXUS_ALMOX_INVENTARIO_ARQUIVO`) e a contagem de mentira injetada só na cópia, nunca no banco.

**Como provar:**
- Os testes: `tests/test_pcm_inventario_*.py` (o adaptador, as contas, o contrato, o livro, a leitura, as telas, a gravação, a
  ponte, a régua e a curadoria) e `tests/test_deploy_espera_gravacao.py`. O `EstoqueFalso` (`tests/estoque_falso.py`) é o Fracttal
  na memória, com os defeitos pelo construtor; toda tarefa que usa o Fracttal tem o teste que manda o cookie `os_sessao` com
  `Path=/os` pelo `estoque_da_sessao` de verdade.
- No navegador, uma cópia de prova com o `EstoqueFalso` (script fora do repositório): a `ferramentas/subir_copia_de_prova.py`
  numa porta livre, o banco falso dos testes (`tests/pg_falso.py`, semeado pelos ajudantes dos testes), o livro do inventário num
  arquivo, a pasta de dados (`NEXUS_DADOS`) numa pasta temporária (a padrão, no Windows, é a do Nexus do PC), o
  `estoque._estoque_do_clone` trocado pelo `EstoqueFalso` e uma rota só da cópia que abre a sessão de uma pessoa do PCM com o cookie
  do Fracttal em `/os` (a cópia recusa todo POST para fora, e o login do Fracttal é um POST).
  A prova de 26/10/2026 achou o `}` do `@media` do fim do inventário perdido no `pcm.css` (a régua e a curadoria sem estilo na
  tela larga): `test_o_css_do_pcm_fecha_toda_chave`. As nove abas cabem a 1366 px com o menu aberto; no celular a fila rola por
  dentro e a aba de agora vem para o meio ao abrir.
- No Fracttal de verdade: a mesma cópia sem o `EstoqueFalso`, liberando o POST só para `app.fracttal.com` e `one.fracttal.com`, o
  login do Fracttal de quem prova e a contagem de mentira da `SP-TST-001` (contado 3 contra o saldo 5) mais uma linha
  `fora_do_catalogo`.

**Falta:**
- A foto da curadoria: a rota assinada App→Nexus, como a do extintor (`hseq/fotos.receber`), combinada com a sessão do App (a seção
  da curadoria).
- A tela da contagem no App (a sessão do App constrói pelo contrato).
- O que só o Fracttal de verdade responde (vira "provado em DD/MM" depois da prova no almoxarifado de teste): voltar ao modo 0
  numa sessão aberta sem finalizar; finalizar uma sessão vazia; se o histórico (`movement_history_list_new`) mostra o finalize
  na hora; repetir o `warehouse_change_mode` no 429; ligar a peça duas vezes; mover em modo 2; o `field_1` (o nome) na lista de
  peças; a régua acordada relida.

## Inventário do almoxarifado: o adaptador do estoque (`inventario/estoque.py`; 26/10/2026)

Levi, 26/10/2026: o técnico conta as peças no App, o PCM revisa e aprova, e o Nexus grava o saldo contado no Fracttal.
Desenho e plano: `docs/superpowers/specs/2026-10-26-inventario-almoxarifado-design.md` e `docs/superpowers/plans/2026-10-26-
inventario-almoxarifado.md`; o que o Fracttal aceita de verdade (métodos, corpos, respostas, lidos da própria tela em 26/10):
`docs/superpowers/specs/2026-10-26-inventario-almoxarifado-passo0.md`.

- **Para que serve:** é a ÚNICA porta de leitura e gravação de estoque no Fracttal. A gravação, a régua e a curadoria só
  chamam os métodos do `Estoque` (o contrato; a `EstoqueFracttal` o cumpre, e o `EstoqueFalso` dos testes também); nenhuma
  tela fala `inventories.*` direto. Todo id é texto; `ler` devolve `{id_item: {saldo, minimo, maximo, ligacao, codigo}}`,
  com o que o Fracttal não disse como None, nunca 0.
- **O ajuste é uma SESSÃO do almoxarifado, não um movimento por peça:** `abrir_ajuste` (modo 2) → `gravar_saldo` (o saldo
  ABSOLUTO de cada peça, idempotente) → `fechar_ajuste(referencia)` (a referência `INVENTARIO-<contagem>` vai na
  `description`). Ao fechar, o Fracttal gera, por peça mexida, um par de movimentos do tipo 15 (saída do saldo antigo
  inteiro, entrada do novo). **Enquanto o modo está aberto o almoxarifado trava Entradas, Saídas e Pedidos de compra** (no
  passo 0, o `ATHN-MTS200` estava em inventário físico, modo 3, com as duas travadas): quem abre fecha no mesmo trabalho, e
  a retomada começa pelo `modo`, fechando o que ficou aberto. Resposta perdida (a conexão cai depois do Fracttal gravar):
  confere pelo `ler` (o saldo) e pelo `achar_movimento(referencia, desde_iso)` antes de repetir; o `desde_iso` (o começo da
  gravação) faz o "não achei" parar na primeira linha mais velha, em vez de ler o histórico inteiro da cota de todos.
- **O fechamento são DOIS pedidos, e a gravação (`gravacao.py`) trata o estado do meio como um estado próprio:**
  `fechar_ajuste` faz o `finalize` e depois chama `voltar_ao_normal` (o `warehouse_update` do modo 0). Se o 2º falhar
  (429, rede, login), o fechamento JÁ VALEU: os movimentos existem e o almoxarifado segue em modo 2, travado para Entradas
  e Saídas ("fechamento feito, modo 0 pendente"). A recuperação é SÓ `voltar_ao_normal`, nunca um segundo `fechar_ajuste`
  (geraria outro par de movimentos por cima). Como reconhecer: `modo` == 2 e `achar_movimento(referencia, desde_iso)` acha
  o movimento. `voltar_ao_normal` é só para o que o Nexus abriu: nunca para o modo 3 (inventário físico, de outra pessoa).
- **Erros:** `Limite` (HTTP 429: a cota de 200/min é da EMPRESA inteira), `SemLogin` (sem login, recusado ou expirado) e
  `ErroFracttal` (o `success: false` com HTTP 200 que o `_rpc_call` do OS Creator DEVOLVE em vez de levantar; a mensagem
  é o código do Fracttal, ex. `ASSET_CANNOT_BE_DESABLED_STOCK`). Rede fora e 500 passam como vieram: a resposta pode ter
  se perdido depois de gravar, e quem grava decide. **Lista pela metade é `ErroFracttal`:** `data` que não é lista, ou
  página vazia com `start < total` (caso da revisão: `ler` devolvia 1 peça de `total: 5`), nunca uma lista curta; vale
  para `ler`, `codigos`, `achar_movimento`, `mexidas_desde`, `ultimo_movimento`, `ajustes_depois` e `modo`, que passam
  pela mesma paginação. `modo` sem o `mode` também é erro: é a conferência da trava, e vazio nunca é "0 = normal".
- **O que o adaptador lê do `api.py` do OS Creator, e o que está provado contra ele:** o marcador `session_expired` da
  `SessionExpired` (HTTP 401/403 e o `USER_NOT_LOGIN` no corpo), o texto "HTTP 429", e as frases "não está logado no
  Fracttal" (sem JWT na sessão) e "JWT do login do Fracttal expirou" (vencido e sem renovar). Os quatro casos têm teste com
  o `api` DE VERDADE do clone (só o `requests.post` trocado); se o `api.py` mudar um deles, o teste cai.
- **Ritmo e login:** 1 pedido por segundo, do início de um ao início do outro, num relógio e numa trava DO MÓDULO (`RITMO`)
  que todas as instâncias dividem: a cota é da empresa, e duas pessoas gravando juntas, cada uma com a instância dela,
  somam 1 por segundo, não 2 (é por processo e só dos pedidos do adaptador: os do OS Creator e os dos robôs não passam
  por ali). O teste dá o `ritmo` (ou o relógio e o `dormir`) e não espera de verdade. `estoque_da_sessao(app)` pega o login
  do Fracttal de quem está no pedido (`ponte.sessao_do_os`; sem ele, `SemLogin`: quem entra pela senha não grava estoque); o
  JWT e o e-mail vivem só na memória da instância, que roda cada pedido dentro de `os_web.sessao.contexto` e guarda o token
  que o `api` renovar no meio, para um trabalho de minutos não renovar a cada pedido. Chamar dentro do pedido; a instância
  pode seguir numa thread. **Chama o `api._rpc_chamar`, não o `_rpc_call`** (o `api.py` não se edita: o clone fica idêntico
  ao do oem): o `_rpc_call` trata como "gravação de OS" todo método que não é "_list", "get", "details" ou "load_" e limpa o
  cache de leituras de OS do processo inteiro a cada um; `warehouses_items_stock` e toda gravação de estoque caem aí, e cada
  pedido do adaptador esvaziaria o cache dos cards de todo mundo. Nenhum pedido daqui toca numa OS.
- **Nome de gente não entra:** o `responsible_description` do histórico de movimentos é nome de pessoa; o adaptador projeta
  só `folio`, `id_item`, `date_create`, `description`, `id_movements` e `id_movement_type`, e nunca o guarda nem o devolve.
- **O marco da retomada** (27/10/2026): `ultimo_movimento` é o maior `id_movements` (numérico e crescente, provado na prova
  real) da 1ª página do histórico, num pedido só; `ajustes_depois(marco, desde_iso, ignorar_prefixo)` dá as peças dos
  movimentos de AJUSTE (tipo 15, `TIPO_AJUSTE`) com id maior que o marco, sem as sessões da contagem. Entrada e saída comuns não
  contam (com o modo aberto não acontecem), e o movimento sem id ou sem tipo legível conta (na dúvida, para).
- **A régua** (`definir_regua`) manda só o mínimo e o máximo que vieram (como texto, o que a tela e a prova de 26/10
  mandaram), fora do modo de ajuste, sem mexer em saldo nem gerar movimento. **Conflito** (`mexidas_desde`): o histórico
  vem do mais novo ao mais velho e se lê até passar da data (a cota é de todos); data ilegível numa linha conta como
  mexida. Sem a `ignorar_referencia` (uma referência exata) nem o que começa pelo `ignorar_prefixo` (todas as sessões de uma
  contagem, `INVENTARIO-<contagem>-`, que a gravação passa).
- **O falso** (`tests/estoque_falso.py`): na memória, com o modo, o par de movimentos ao fechar, o fechamento em dois
  passos (`finalizado, modo 0 pendente`) e os defeitos pelo construtor (`perder_resposta`, uma vez por operação: grava e
  levanta `ConnectionError`; `limite_em`: a N-ésima chamada só; `expirar_em`: da N-ésima em diante TODA chamada da
  instância é `SemLogin`, como o adaptador de verdade, que reenvia o JWT morto). `voltar_ao_normal` é uma operação à parte
  para os defeitos, e `mover` (uma OS que lança peça) é recusado com o almoxarifado em modo 2 ou 3. O que o passo 0 não
  provou e o falso supõe (gravar fora do modo, ligar duas vezes, código repetido, abrir em modo 3, um 2º finalize, mover em
  modo 2) está no cabeçalho dele: conferir na prova no Fracttal de verdade (a seção do fluxo, "Falta").
- **Provar:** `tests/test_pcm_inventario_estoque.py`: os corpos e a ordem do passo 0, a paginação (inclusive a lista pela
  metade), o ritmo (uma instância e duas), os erros, o histórico sem nome, o fechamento em dois passos, o cache das OS
  intacto e o `api` de verdade do clone com só o `requests.post` trocado. Mutações nas regras de cada item acima (ritmo,
  nulo que vira 0, `success`, lista curta, corte da data, token renovado, nome guardado, 429, volta ao modo 0, `mode` vazio,
  `_rpc_call`), todas pegas.

## Inventário do almoxarifado: as contas (`inventario/contas.py`; 26/10/2026)

Puro (dicts entram, dicts saem): a leitura do livro, a tela do PCM, a gravação e a curadoria chamam estas contas, e só elas,
para o número não mudar de uma tela para a outra. Provado em `tests/test_pcm_inventario_contas.py` (com mutações em cada regra).

- **As seis situações** (`SITUACOES`; só `MEXEM` = para cima, para baixo e zerar grava no Fracttal): `sem_alteracao`,
  `nao_tocada` (em branco) e `curadoria` (o que o PCM ainda decide) não mexem. **Em branco não é zero:** o livro volta da API
  todo como texto ("3,0", "" e "None" no lugar do vazio) e o vazio é "não contei"; só o 0 digitado NA LINHA DA PRÓPRIA PEÇA
  é `zerar` (0 unidades achadas, ou 0 de genérico confirmado, que a curadoria atribui a uma peça em branco não a contam: foi
  o caso da peça em branco com saldo 8 que virava `zerar` por um achado de 0 unidades). **Saldo não
  informado** (peça ligada com o saldo vazio no Fracttal) vale 0 na conta, mas contar 0 nela é `sem_alteracao`, e o `sistema`
  do lote segue None para a conferência da gravação comparar igual com igual. **Peça fora da leitura de estoque** (nunca
  ligada ao almoxarifado) entra com `sistema` 0 e `ligada` falso: a gravação a liga antes. Saldo "nan" ou "inf" é "não
  informado" (None), nunca NaN no lote. **Contado negativo** nunca mexe: a peça entra como não contada e `invalido`. O 0.1 +
  0.2 do metro não vira "ajuste" (soma arredondada, comparação com folga).
- **O contado efetivo** (`contado_efetivo`, a chave da linha é o "ID da linha"): a peça vale o "Contado" da linha; "é a peça
  X" e "cadastrar" SOMAM as unidades achadas ao contado de X nessa contagem (X em branco vira só as achadas) e o total substitui
  o saldo; o genérico (`identificar`) confirmado tira as unidades do genérico e as põe no específico. Sem decisão (ou com
  uma que não é do tipo da linha), o genérico e o achado ficam na `curadoria` e não gravam; em branco não há o que decidir
  (o genérico em branco é `nao_tocada` e o achado em branco nem entra no lote). O genérico entra só como linhas
  `identificar`: se o App mandar também uma linha `item` dele, as duas somam. A mesma linha reenviada pela fila offline do
  App (mesmo "ID da contagem" e "ID da linha") conta uma vez, vale a última.
- **QUEM GRAVA parte do `itens_do_lote` e só leva `not tirada and situacao in MEXEM`, nunca o `contado_efetivo` direto:** ele
  devolve o genérico por identificar como um número (as unidades dele, ainda sem dono), e gravá-lo ajustaria o estoque com
  unidades que talvez sejam de outra peça.
- **`itens_do_lote`:** uma entrada por peça, na ordem do livro (`contado_campo` é o do campo já com a curadoria; `contado`, o
  que vai ao Fracttal, é o corrigido pelo PCM quando há; `tirada` fica de fora da gravação mas mantém a situação). O achado
  fora do catálogo por decidir é uma entrada à parte, sem `id_item`, na `curadoria`, com a linha em `pendentes`.
- **`substituidas`:** por almoxarifado vale a contagem mais nova pelo "Contada em" (o instante: -03:00 e Z se comparam); as
  velhas não gravadas ficam substituídas. Quem chama passa só as contagens VIVAS (nem a `recontagem pedida` nem a
  `substituída`: uma recontagem recusada como "a mais nova" substituiria as boas sem número para gravar no lugar); a que
  vem sem almoxarifado não entra. **`aprovavel`: 90 dias, não 7.** Os 7 dias do desenho valiam enquanto não houvesse
  jeito de saber o que se moveu depois da contagem; o passo 0 achou o histórico do almoxarifado (`mexidas_desde`) e o conflito
  sai dele, peça a peça, na gravação. Os 90 dias (`APROVAVEL_DIAS`) são só o teto: a janela do livro do App e do histórico a
  ler (que gasta da cota do Fracttal, de toda a empresa). Data ilegível ou do futuro (relógio do celular adiantado além de 1
  h, que esconderia todo movimento real) não se aprova.

## Inventário do almoxarifado: as contagens e o estado de cada uma (`inventario/leitura.py`; 26/10/2026)

`leitura.contagens(cfg)` é a lista que a tela do PCM mostra: uma contagem por "ID da contagem" do livro que o App publica
(`almoxarifado_contagens_app_campo`, o contrato de 14 colunas), da mais nova para a mais velha, sem o almoxarifado de teste.
Cada uma traz `contagem_id`, `id_almox` e `almox` (o nome), `usina`/`usina_id` (o nome do cadastro quando a de-para do Fracttal
liga; senão o do Fracttal e `usina_id` None), `contada_em`, `enviada_em`, `linhas` (as do App), `n_contadas`, `n_em_branco`,
`n_curadoria`, `estado`, `aprovavel`, `motivo_nao_aprovavel` e `aviso`. `livro_existe(cfg)` diz se o App já publicou o livro (sem
ele a tela diz que o App ainda não publica, e não "nenhuma contagem"); `ler(cfg)` devolve os dois com o nome de cada peça.

- **Duas fontes, dois relógios:** o livro do App vem pela cópia de 5 min do `visao._ler` (lê e liga a usina uma vez); o ESTADO sai
  dos eventos do livro do inventário e é calculado a CADA chamada: o `acrescentar` renova a cópia do livro, e a tela mostra a
  recontagem pedida na hora (com o estado guardado 5 min, o PCM a pediria de novo). **Falha de leitura (do App ou do livro do
  inventário) levanta `fato_inventario.Recusada`:** nunca devolve lista vazia nem contagem `nova`, senão a já gravada
  apareceria como a aprovar.
- **Os estados** (`ESTADOS`): `nova` (nenhum evento que mude o estado), `revisada` (`peca_tirada` ou `numero_corrigido`),
  `recontagem_pedida`, `substituida`, `gravando`, `gravada`, `gravada_com_conflitos`. **O lote é o conjunto de `id_item` dos
  eventos `aprovada`: a gravação (`gravacao.py`) grava UM `aprovada` por peça do lote.** Sem as peças a leitura não sabe o que falta e
  fica em `gravando`; só vira `gravada` quando toda peça do lote tem `peca_gravada`, e `gravada_com_conflitos` quando alguma tem
  `conflito` no lugar. O `erro` não encerra a peça. O `gravando` daqui é "aprovada e sem o fim nos eventos"; a gravação refina
  em andamento ou parada com o controle dela (o `estado.json`).
- **A substituição sai da conta, a leitura não escreve:** `contas.substituidas` recebe só as contagens VIVAS (nem
  `recontagem_pedida`, nem `substituida`; uma recontagem recusada como "a mais nova" substituiria as boas sem número para gravar
  no lugar) e BOAS (sem `aviso` e com um "Contada em" legível e que não passa do relógio adiantado, `_pode_substituir`: a mais nova
  que não se aprova, por contrato violado ou por relógio de celular no futuro, tirava do caminho as que se aprovam, e o almoxarifado
  ficava sem nenhuma contagem para revisar), e, como `gravadas`, as em `gravando`, `gravada` e `gravada_com_conflitos`. O evento
  `substituida`, se alguém o gravar, também vale.
- **Contrato violado vira aviso, não número pela metade:** "ID da linha" vazio ou o texto "None" (o `sync-xlsx` escreve o vazio
  assim) junta duas linhas numa nas contas (`contas._unicas`) e perde unidades contadas; contagem sem o ID do almoxarifado não tem
  saldo do sistema para ler. Os dois dão `aviso` e `aprovavel` falso (a tela não mostra comparação).
- **`motivo_nao_aprovavel`** (a tela mostra o porquê): "já gravada" (gravando, gravada e com conflitos), "substituída",
  "recontagem pedida", "contagem sem almoxarifado", "linha sem ID da linha", "data da contagem ilegível", "contada no futuro: o
  relógio do celular" e "mais de 90 dias" (`contas.aprovavel`, `APROVAVEL_DIAS`).
- **As contas de linhas** contam depois do dedupe da fila offline (mesmo "ID da contagem" e "ID da linha"), e somam as linhas de
  peça: `n_em_branco` (sem número, o achado em branco inclusive), `n_curadoria` (com número e ainda por decidir: o genérico por
  identificar e o achado fora do catálogo, descontadas as decisões já gravadas na curadoria) e `n_contadas` (o resto).
- **O que o PCM já fez** (`revisao_da`, `curadoria_da`) vem na forma que as contas pedem: `tiradas` {id_item: motivo},
  `corrigidos` {id_item: número} (vale a última) e as decisões da curadoria `{ID da linha: {decisao, id_item, codigo}}` (vale a
  última). O motivo só existe cifrado no livro; é aqui que se abre, e só quando `motivos=True` (quem não vai mostrar o texto não o
  decifra).
- **Provar:** `tests/test_pcm_inventario_leitura.py` (os estados, a substituição, o livro que não existe e o que não lê, a janela de
  90 dias, o contrato violado, a cópia que ninguém estraga); mutações no lote vazio, nas contagens vivas, nas gravadas, na cópia
  das linhas e na falha de leitura, todas pegas.

## Inventário do almoxarifado: a aba Inventário (`inventario/revisao.py`, `ponte_os.py` e as rotas em `inventario/__init__.py`; 26/10/2026)

Levi, 26/10/2026: o técnico conta no App e o PCM revisa e aprova no Nexus. A aba é um LINK na fila das abas do Almoxarifado (depois
das cinco), com quantas contagens esperam o PCM; é outra página, `pcm/inventario.html` (a lista) e `pcm/inventario_contagem.html`
(a contagem aberta). **As quatro partes do inventário ficam juntas na fila das abas** (Inventário, Mínimo e máximo, Curadoria e
Auditoria): as páginas delas incluem `pcm/_almox_abas.html` (as cinco voltam à tela principal, em `?aba=`; a de agora é a
`aba_inventario` que a página põe antes de incluir), e a tela principal as põe como links. A régua e a curadoria tinham um menu
próprio, que saiu. As páginas são sub-rotas
da tela `pecas`, que é do setor PCM (outros, pela marca em Base → Acessos): `GET /t/pcm/pecas/inventario`, `GET .../<contagem_id>` e
`POST .../<contagem_id>/revisar` (JSON). O código das telas é o `revisao.py`, sem Flask (as rotas só passam a configuração, a
função que lê o saldo e a pessoa); a leitura das contagens e o estado de cada uma é o `leitura.py` (seção acima).

- **O login do Fracttal só chega em `/os` (revisão das Tasks 5 e 6, provada com o app de verdade).** O cookie `os_sessao`, onde mora o
  JWT, é gravado com `Path=<raiz>/os` (`nexus.auth.os_cookie_path`: "só os pedidos de /os trazem o cookie do OS Creator"): o
  navegador NÃO o manda para `/t/pcm/...`, e o `estoque_da_sessao(app)` numa rota do PCM dava `SemLogin` SEMPRE em produção. Os
  testes não pegaram porque trocavam o `estoque_da_sessao` ou mandavam o cookie à mão. **Regra: toda operação que precisa do
  Fracttal (ler o saldo, gravar a contagem, continuar, gravar a régua, cadastrar a peça na curadoria) roda numa rota de
  `/os/_nexus/inventario/...`** (`ponte_os.py`, um blueprint na RAIZ do app, registrado junto com a torre como o `bp_raiz` do OS
  Creator; a Engenharia faz igual em `/os/_nexus/engenharia/...`). O portão de login do Nexus vale (nada é público), mas o portão
  por setor só olha `/t/...`: a ponte confere sozinha `pode_programar()` (403 para os outros setores; sem isso qualquer pessoa
  logada leria o saldo da empresa) e `_de_outro_site()` (um site de fora não gasta a cota do Fracttal). O que NÃO precisa do
  Fracttal fica em `/t/pcm/...`: a lista, a revisão, o `estado.json` da gravação, as decisões que só gravam no livro. Nos pedidos
  de `/os` o portão do Nexus também confere o cookie: a sessão que nasceu do login do Fracttal e já não tem o JWT é ENCERRADA
  (401 JSON com `sessao_encerrada` e `entrar` para o fetch); a que nasceu da Microsoft não cai, e é ela que chega ao 401 da ponte
  com o link do `/os/login`.
- **A página e o lote.** A PÁGINA (`revisao.montar`) mostra o que o técnico contou, o estado, os avisos, o "Pedir recontagem" e o
  painel de revisão, e NÃO lê o Fracttal. O que depende dele (`revisao.montar_lote`, desenhado pelo parcial
  `pcm/_inventario_lote.html`: os seis números, o Sistema × Contado × Δ × Situação, os seis grupos e o botão de gravar) a página busca
  por `fetch(nexusRota(...))` em **`GET /os/_nexus/inventario/<id>/lote`** (HTML pronto, `Cache-Control: no-store`), dizendo "lendo o
  saldo do Fracttal…" enquanto espera, e troca o que o técnico contou por ele. O Sistema é lido NA HORA, não o da varredura da
  madrugada (o saldo muda durante o dia): uma leitura do almoxarifado inteiro pelo adaptador, com o login de quem pede. Respostas da
  ponte: 200 o HTML; **401** sem o login do Fracttal (`{"erro": "Para ler o saldo e gravar, entre pelo Fracttal.", "login": o
  /os/login com a volta para a página}`; a página mostra "entre pelo Fracttal para ver o saldo do sistema e gravar" com o link); 403
  de outro site ou de quem não é do setor PCM; 404 contagem que não existe; **409** contagem que não se aprova ou fora do contrato
  (nada a ler: velha, substituída, gravada e recontagem pedida não gastam a cota da empresa, que é de 200/min para todos); **429** a
  pausa do Fracttal ("o Fracttal pediu uma pausa; tente de novo em 1 minuto"); 502 o Fracttal que falhou ou os livros que não
  leram. Nunca 500, e a página segue de pé com o contado. A leitura do Sistema é só do setor PCM: os outros veem o contado, e a
  tela diz que o saldo do sistema também é do PCM.
- **Provar a ponte:** `test_a_ponte_ve_o_login_do_fracttal_e_a_rota_do_pcm_nao` usa o `estoque_da_sessao` DE VERDADE e o cookie
  `os_sessao` com `Path=/os`, e só troca o `requests.post` do `api` do clone: a rota da ponte vê o login e lê o Sistema, uma rota
  `/t/pcm/...` não (e com o `Path=/` de controle ela veria). Toda tarefa nova que use o Fracttal deve ter um teste assim.
- **Os seis grupos da confirmação** (`contas.SITUACOES`): para cima, para baixo, zerar, sem alteração, não será tocada e curadoria;
  só os três primeiros mexem no estoque, e o botão "Gravar N alterações" conta só eles, sem a peça tirada. **O zerar abre aberto e
  destacado** (é a única ação que apaga estoque). A peça tirada do lote vai a "não será tocada" com o motivo; a de contado negativo
  também, com "contado inválido" até o PCM corrigir (corrigida, ela entra no lote e a nota diz "o técnico contou um valor inválido;
  o PCM corrigiu para X"). A peça nunca ligada ao almoxarifado mostra no Sistema "não ligada (0)" e a nota "será ligada ao gravar";
  a ligada com o saldo vazio, "não informado", sem Δ (um "+5" contra um 0 que o Fracttal não disse seria inventado; a nota diz que
  vale 0 na conta, e contar 0 nela não é zerar). **O botão "Gravar N alterações"** vem no pedaço da ponte, com o N e a assinatura
  do lote que ele mostra, e chama a ponte do Fracttal (a seção da gravação, abaixo).
- **Curadoria aberta avisa e não bloqueia:** "N achados por decidir na curadoria; decidir depois soma ao contado da peça escolhida" (e o
  mesmo, dizendo o genérico, quando ele tem unidades ainda por identificar). O genérico por identificar e o achado não têm Δ: as
  unidades ainda não têm dono.
- **O motivo do PCM só vai a quem pode revisar** (`pode_programar`): a nota da peça tirada e do número corrigido leva o texto para o
  PCM e, para os outros setores, só "tirada do lote" e "corrigida pelo PCM" (o motivo é texto livre e pode citar gente; nem o
  decifra para eles, `revisao_da(motivos=False)`).
- **A hora na tela é a da janela de aprovação:** `revisao._hora` usa o `estoque.instante` (um texto sem fuso é UTC, como o App
  grava) e escreve "contada em 26/10/2026 às 09:00 (Brasília)". Antes lia pelo `visao._dt` (sem fuso = Brasília) e mostrava 12:00
  onde a janela contava 09:00.
- **Revisar** (`POST .../revisar`, `{"acao": "tirar" | "corrigir" | "recontagem", "id_item", "valor", "motivo", "sistema"?,
  "confirmo"?}`): só quem `telas.pode_programar()` (administrador e setor PCM) e de uma página deste mesmo endereço, senão 403. O
  motivo é OBRIGATÓRIO nas três (o desenho: "cada um com o motivo, na auditoria") e vai só cifrado (`dados={"motivo": ...}`; a API do
  banco é aberta). `corrigir` aceita número de zero para cima, com vírgula ou ponto (o 0 vale: a peça acabou; negativo, vazio, texto e
  notação científica, 400). **O exagero pede confirmação:** número acima de 10 vezes o maior entre o contado e o saldo do sistema (e
  de 1000) é quase sempre um zero a mais e iria ao estoque da empresa: 400 com `confirmar: true`, e o `"confirmo": true` do corpo
  aceita (o saldo do sistema é o que a página mostrou e vai no corpo como `sistema`, porque revisar não lê o Fracttal: é uma trava
  contra o erro de digitação, não uma defesa). Contagem que não se aprova, 409 com o `motivo_nao_aprovavel`; peça que não é da
  contagem, 400; peça já tirada, 409; corrigir peça com unidades por identificar, 409 (decide a curadoria antes). **Nada disso fala
  com o Fracttal:** grava UM evento no livro do inventário (`peca_tirada`, `numero_corrigido` com `de_qtd` = o do campo, `para_qtd` = o
  corrigido e `contado_qtd` = o do campo, ou `recontagem_pedida`), com a usina pela de-para do Fracttal (`usina_id` +
  `usina_ligada_por`) e a pessoa como `pessoa_hmac` (o código do e-mail) e `pessoa_id` (quando a ficha do cadastro a acha). **Quem
  entrou pela senha de administrador não revisa** (409 "entre com o seu login do Fracttal"): não é uma pessoa, e a revisão ficaria
  sem dono na auditoria; e com a `NEXUS_PESSOA_HMAC` faltando no servidor o 409 diz que o servidor não está configurado e manda
  avisar a T.I. (a pessoa já entrou: mandá-la entrar de novo não resolve).
- **Por que a lista não guarda o estado:** a cópia de 5 min é do livro do App; o estado sai dos eventos a cada abertura, e a revisão
  renova a cópia dos eventos. Pedir a recontagem e ver "nova" por mais 5 min faria o PCM pedir de novo.
- **Provar:** `tests/test_pcm_inventario_telas.py` (a lista; a página sem o Fracttal e o lote pela ponte, com os seis grupos e os
  números certos; o login que falta, o 429 e a queda; a ponte com o cookie de verdade; cada ação com o evento e o motivo só cifrado,
  as recusas, o exagero, o 403 dos outros setores e de outro site, a aba, as cores só por token e os endereços pela `{{ raiz }}`);
  mutações em cada regra acima, todas pegas. Provada no navegador em 26/10/2026 numa cópia de prova com o `EstoqueFalso` (a seção do
  fluxo, "Como provar"), a 1366 e 375 px, escuro e claro: o lote pela ponte, o painel de revisão, a correção que muda a situação.

## Inventário do almoxarifado: o livro (`nexus/dados/fato_inventario.py`; 26/10/2026)

Onde o PCM deixa o rastro do inventário: `nexus_almoxarifado_inventario` com `fato_evento_inventario` (a auditoria),
`fato_regua_minimo` (a régua) e `fato_curadoria_inventario`. As regras de governança, as colunas e o porquê estão em
`nexus/dados/CLAUDE.md` (linha "Inventário do almoxarifado"); aqui, o que a tela e a gravação em segundo plano precisam saber
para usar:

- **Tudo grava por `fato_inventario.acrescentar(cfg, aba, linhas)`** (uma lista de dicts pelas colunas do `CAB_*`); a leitura
  é `ler(cfg)` (as três abas, cópia de 2 min) e o motivo se abre com `decifrar(cfg, aba, linha)`. Nunca escreva no livro por
  outro caminho: a gravação relê e troca o livro inteiro, e só o `acrescentar` faz isso com a trava.
- **O motivo é `dados={"motivo": ...}`** (no evento e na curadoria; a régua não tem texto): o módulo o cifra, e o
  `dados_cifrados` não se passa pronto. `motivo=`, nome, e-mail ou `dados_cifrados` como coluna é `ValueError` (erro de quem
  chama). A pessoa vai como `pessoa_hmac` (sempre, os 24 hexadecimais do `codigo_da_pessoa`) e `pessoa_id` (quando o
  cadastro a acha). Só entra o que cabe na coluna: `situacao` é uma das seis da peça (`dominios.SITUACAO_INVENTARIO`, igual a
  `contas.SITUACOES`), `id_item`, `id_almoxarifado` e `movimento_fracttal` (o folio) são dígitos, `contagem_id`, `chave_linha`
  e `evento_id` não levam espaço.
- **A usina vai com a linhagem:** `usina_id` e `usina_ligada_por` (hoje só "de-para do Fracttal", o `LIGADA_DE_PARA` do
  `fato_almoxarifado`) juntos, ou os dois vazios (almoxarifado que não liga a usina nenhuma: a Nobres, por exemplo). A
  curadoria também leva `id_almoxarifado`, `usina_id` e `data_id`.
- **`fato_inventario.Recusada` é a exceção desta camada** (as Tasks 6 a 9 a importam de lá): nada foi gravado, e o texto é para
  a tela mostrar (o banco não deixou reler, o evento já está, falta `GRIDCO_SQL_TOKEN` ou `NEXUS_CHAVE_CADASTRO`). `ler`
  também a levanta quando não consegue ler: nunca devolve vazio no lugar do que não leu, senão a contagem já gravada
  apareceria como `nova`.
- **O módulo põe o que falta:** o `evento_id`, a hora (`quando` / `decidida_em`, UTC com Z; outro fuso é convertido e sem fuso
  é recusado) e o `data_id` (o dia de Brasília dessa hora; um `data_id` trazido que não bata é `ValueError`). O que o chamador
  traz pronto (a retomada de uma gravação) vale. O `evento_id` repetido é `Recusada` (é a chave do fato). A leitura que volta
  com menos linhas do que a listagem do banco diz (página curta) não grava e não é devolvida: `Recusada`.
- **Na cópia de prova e nos testes:** `NEXUS_ALMOX_INVENTARIO_ARQUIVO` (um JSON); teste sem ele lê vazio e não grava. Prova:
  `tests/test_pcm_inventario_livro.py` (inclusive o banco falso com `como_texto=True`, a leitura que falha, a listagem
  incompleta e as mutações nas regras).

## Inventário do almoxarifado: a régua de mínimo e máximo (`inventario/regua.py`; 26/10/2026)

Levi, 26/10/2026: a régua é "sugestão ajustável": o Nexus propõe pela régua de 14/10 e o PCM muda peça a peça. Tela
`/t/pcm/pecas/inventario/regua?almox=<id>` (a tela dona é o `pecas`, do setor PCM; quem a vê por outro setor só lê). Por peça de
cada almoxarifado, TRÊS números de mínimo e máximo, e só um vai ao Fracttal:

- **Sugestão** (`sugestao`, pura): mínimo = 20% do saldo, máximo = 2x; a avariada (`-AV` no fim do código, ou a marca
  "Avariado" do catálogo do App) fica sem mínimo e com 3x. Unidade inteira arredonda PARA CIMA (saldo 3 dá mínimo 1, e não 0); METRO
  e MASSA (o `units_description` do Fracttal) têm duas casas. Saldo 0 (ou negativo) dá (0, 0); **saldo não informado dá
  (None, None)**: em branco nunca é zero. O `15 x 0,2` do ponto flutuante dá 3,0000000000000004: a conta divide e arredonda
  antes do teto.
- **Recomendado** (a Grid): decisão do PCM, só no livro (`fato_regua_minimo`), é o histórico com que se defende o mínimo.
- **Acordado** (o cliente): decisão do PCM e o ÚNICO que vai ao Fracttal (`definir_regua`, fora da sessão de ajuste: sem
  movimento, sem mexer no saldo). Leva os DOIS números; o recomendado pode ficar sem mínimo. Mínimo acima do máximo é
  recusado (400) antes de qualquer pedido. **O acordado com casa decimal só em METRO e MASSA** (400): a unidade da varredura vale ao
  registrar, e a que o Fracttal diz (`Estoque.ler()["unidade"]`) vale antes do `definir_regua`; a unidade que ninguém disse é
  inteira.

- **Cada linha do livro é o RETRATO da decisão**, porque vale a última de cada almoxarifado e peça: decidir só o recomendado
  leva junto o acordado de antes (senão a última linha apagaria o que o cliente acordou), e a sugestão do momento fica ao lado
  (o histórico do mínimo). `gravado_fracttal` só continua 1 se o acordado não mudou. A decisão lê o livro de novo (`ler(forcar)`)
  sob uma trava POR PEÇA (almoxarifado + peça, `travas.Travas`): duas pessoas na mesma peça esperam uma pela outra, e a gravação lenta
  no Fracttal de uma peça não segura as outras (a 1ª versão tinha uma trava do módulo inteiro, segurada durante o pedido ao Fracttal).
- **De onde vem o saldo:** o da última contagem GRAVADA (o `para_qtd` do evento `peca_gravada` mais novo); sem ela, o da
  varredura do App (`almoxarifado.montar`). A peça vem do saldo do almoxarifado, nunca do ID que a página mandou (outro
  almoxarifado ou ID chutado é 400). O almoxarifado de teste não tem linha na varredura (fica fora das telas): a prova dele passa
  a `varredura=` à mão.
- **Gravar roda na PONTE `/os/_nexus/inventario/regua/gravar` (`ponte_os.py`), não em `/t/pcm`:** o login do Fracttal é o cookie
  `os_sessao`, gravado com `Path=<raiz>/os`, e o navegador não o manda para `/t/pcm/...`; `estoque_da_sessao` numa rota de `/t/pcm`
  seria sempre `SemLogin` em produção (os testes que trocam a função não pegam isso: o teste `test_o_login_do_fracttal_so_chega_na_ponte`
  usa a função de verdade, o cookie com `Path=/os`, e mostra a ponte vendo o login e uma rota de `/t/pcm` não). A página fica em
  `/t/pcm`, e o botão "Gravar no Fracttal" (formulário `data-ponte`) vai por `fetch` (`static/pcm-ponte-inventario.js`); a ponte
  responde JSON (`{ok, mensagem, volta}` ou `{erro, login?}`) e deixa o aviso na sessão, que a página mostra ao recarregar. Registrar
  (`/t/pcm/.../regua/decidir`) só grava no livro e fica em `/t/pcm`. **O formulário de gravar leva o acordado que a tela
  mostrava** (`aco_min`, `aco_max`, só para conferir; o que vai ao Fracttal é o do livro): se o registrado agora é outro (outra pessoa
  do PCM mexeu com a tela aberta), 409 "a régua mudou desde que você abriu a tela; recarregue", nenhum pedido. Sem esses campos, 400.
- **`gravar_acordado`** (no login de quem apertou, `estoque_da_sessao`): lê o almoxarifado (a leitura guarda a ligação),
  `definir_regua`, relê, e SÓ ENTÃO anota o evento `regua_gravada` (o mínimo de -> para; o máximo fica no retrato) e o retrato
  `gravado_fracttal`. A releitura que não bate é um evento `erro` e `NaoConfere` (502): o livro nunca diz que o Fracttal tem o
  que não tem. Uma linha do livro com só um dos números acordados (a API aceita linha à mão) é `Conflito` ("incompleto"), nunca
  um `TypeError` na conferência. O evento sai antes do retrato: se o retrato falhar, a peça segue "não gravada" e o PCM grava de novo (idempotente).
  Sem acordado, ou peça não ligada ao almoxarifado: `Conflito` (409), nenhum pedido. Quem entrou pela senha de administrador
  registra, mas não grava: 409 (não é uma pessoa; o `os_sessao` que estiver no navegador seria o login de outra), e a tela diz por
  quê; a conta do Fracttal do cookie que não é a pessoa da sessão: 409 com o link para entrar de novo; sem o cookie (quem entrou pela
  Microsoft): 401 com o link do `/os/login` e a volta à página. Quem entrou pelo Fracttal e chega à ponte sem o cookie dele tem a
  sessão do Nexus encerrada pelo portão ("caiu").
  Limite do Fracttal: 429. Rede que cai: 502 com "grave de novo, é o mesmo número" (só na régua: `erros.resposta(ex, ao="regua")`).
- **Peças de apoio:** `quem.py` (a pessoa nas colunas do livro: `pessoa_hmac` pelo e-mail da sessão, e `pessoa_id` quando o
  cadastro a acha; sem e-mail, vazio), `erros.py` (`Conflito`, `NaoConfere` e a tabela erro -> status HTTP, a mesma da curadoria; o erro
  de REDE, com um texto para cada operação, não se confunde com o de ARQUIVO local, 500, que não fala do Fracttal), `travas.py` (uma trava
  por chave) e `ponte_os.py` (o blueprint `/os/_nexus/inventario`, registrado na raiz do app como o `bp_raiz` do OS Creator, com
  `registrar` idempotente; cada tarefa põe as rotas dela num bloco próprio; `tests/test_pcm_inventario_ponte.py` prova o registro duas
  vezes e as duas rotas debaixo do `NEXUS_PREFIXO=/nexus`). `Estoque.ler` passou a devolver também a `unidade`.
- **Provar:** `tests/test_pcm_inventario_regua.py` (a conta, o quadro, o retrato, só o acordado ao Fracttal, a releitura, o 403
  de quem não é PCM, o 400, o 409, o 401, o 429, a resposta perdida) com mutações nas regras (manda o recomendado, não confere a
  releitura, teto vira piso, avariada com mínimo, gravado sobrevive ao acordado novo, perde o acordado de antes, aceita mínimo
  acima do máximo, ignora a contagem gravada, vale a primeira decisão, peça de qualquer almoxarifado, os dois gates), todas pegas. A
  revisão de 27/10 acrescentou: o acordado que mudou desde que a tela abriu, o decimal em unidade inteira (no registro e na gravação), o
  acordado incompleto, a trava por peça (duas pessoas na mesma peça; a gravação lenta de uma não segura a outra) e o erro de rede.

## Inventário do almoxarifado: a curadoria (`inventario/curadoria.py`; 26/10/2026)

Levi, 26/10/2026: a peça que o técnico acha fora do catálogo vira pendência; o campo descreve, fotografa e conta, e quem decide é o
PCM. Tela `/t/pcm/pecas/inventario/curadoria` (decide só quem `pode_programar`: administrador e setor PCM; **os outros veem só a
lista, com "achado fora do catálogo", a quantidade e a usina: o que o técnico escreveu e a foto dele são de quem decide**, e a rota da
foto também é 403 para eles).
Duas pendências, só nas contagens que ainda NÃO foram gravadas: o **achado fora do catálogo** (cadastrar, é a peça X, descartar) e o
**genérico a identificar** (confirmar o específico que o técnico escolheu, ou outro). O achado em branco não é pendência.

- **A decisão é uma linha do livro** (`fato_curadoria_inventario`, chave `contagem_id` + "ID da linha") mais o evento `curadoria` na
  auditoria, e entra no lote pela `contas.contado_efetivo`: "é a peça X" e "cadastrar" SOMAM as achadas ao contado da peça NESSA
  contagem (o total substitui o saldo); o genérico confirmado tira do genérico e põe no específico. `decisoes(cfg, contagem)` devolve
  `{ID da linha: {decisao, id_item, codigo}}`, o formato que `contado_efetivo` e `itens_do_lote` pedem. A peça cadastrada é ligada ao
  almoxarifado e ajustada na gravação da contagem, não aqui.
- **Uma linha decidida não se decide de novo** (`Conflito`, 409: dois do PCM com a tela aberta não cadastram a mesma peça duas
  vezes), e **a decisão só vale até a contagem ser gravada**: gravada, aprovada (a gravação começou), recusada ou substituída pela
  mais nova do almoxarifado = 409 com "faça uma nova contagem" (decidir depois não mudaria o que já foi gravado). Quem sabe o que já
  foi gravado é `_estados` (os eventos do livro): é o ponto único para trocar pela leitura da lista de contagens (`leitura.py`). **O estado é
  conferido DE NOVO, no livro de agora, logo antes de escrever**: o cadastro pagina o catálogo e cria a peça (segundos) depois da
  primeira leitura, e a gravação da contagem pode chegar nesse intervalo. Se a contagem já não está aberta, 409, nada é escrito, e para o
  cadastro a mensagem diz o código que ficou criado no Fracttal ("a peça SP-XXX-NNN foi criada no Fracttal, mas a contagem já tinha sido
  gravada"); a reserva continua, para o código não ser escolhido de novo.
- **As travas são por chave, nunca uma do módulo** (`travas.Travas`): por (contagem, linha) para ler, conferir e escrever a decisão (duas
  pessoas na mesma linha: uma ganha, a outra leva 409), por sigla para escolher o código e reservá-lo (duas linhas da mesma sigla não
  escolhem o mesmo número) e por arquivo de controle para regravar as reservas, nessa ordem. O `criar_peca` e as páginas do catálogo
  levam segundos: um cadastro lento não segura a decisão de outra linha. Por último, só em volta da conferência final e da escrita,
  a trava da contagem (`travas.CONTAGEM`, a mesma da aprovação, seção da gravação): a decisão que chega durante a aprovação espera e
  é recusada, em vez de gravada e ignorada pelo lote já montado.
- **Cadastrar sem duplicar:** o `criar_peca` pode criar e perder a resposta. O código escolhido vai ANTES para
  `<NEXUS_DADOS>/almox_inventario/curadoria_<contagem>.json` (sem login, sem nome); na nova tentativa da mesma linha, o código
  reservado é o dela: se já existe no Fracttal (`Estoque.peca`), não cria de novo, acha o ID e só grava a decisão; se não existe,
  cria com ele (o 013 não fica vazio). A reserva vale também para as outras linhas da sigla (a peça recém-criada pode não aparecer
  ainda na lista). Arquivo de controle que não se lê PARA o cadastro (ignorá-lo escolheria o código de novo).
  **A reserva guarda a sigla, o nome e a unidade pedidos, e a nova tentativa tem de vir com os MESMOS dados** (o nome sem ligar para
  caixa nem espaço): com outro, `Conflito` antes de qualquer pedido ("repita com os dados da reserva"), porque com a peça já criada a
  decisão ficaria ligada a uma peça com o nome errado, e sem ela criaria uma diferente da que a pessoa acha ter pedido. A tela volta
  preenchida com a reserva (`pendencias`, `reserva`). **Quando o código reservado é achado no Fracttal, o NOME da peça (`field_1`) é
  conferido com o da reserva**: outro nome é `Conflito` (o código foi usado por outra pessoa depois), a decisão não é ligada àquela
  peça, e a reserva continua; a saída é decidir de outro jeito (é a peça de tal código, ou descartar). O nome que o Fracttal não diz
  não bloqueia (a presença do `field_1` na lista de peças é para a prova no Fracttal de verdade).
- **O código:** `SP-<sigla>-NNN`, o número seguinte ao maior que existe (`Estoque.codigos` traz as peças DESATIVADAS também: a lista
  de Peças e Suprimentos do Fracttal as mostra com "Não" em "Habilitado", então o código de peça desativada não é reaproveitado;
  `-AV` no fim não tira o número). As siglas são as 12 do catálogo; `TST` só no almoxarifado de teste (`ids_de_teste`).
- **O destino da peça** ("é a peça X", "confirmar") tem de existir no catálogo do App (ou ter sido cadastrado por aqui: a varredura
  diária ainda não o viu); a tela aceita o CÓDIGO (o PCM conhece o código, não o ID) e converte. Sem o catálogo inteiro, não decide.
- **O motivo** (texto livre) só cifrado, em `dados={"motivo": ...}` (o Cofre do cadastro; a API do banco é aberta); descartar o exige.
  A pessoa vai como código (`quem.colunas`); a usina, pela de-para do Fracttal (`usina_ligada_por`).
- **A foto** fica fora do banco: `<NEXUS_DADOS>/almox_inventario/fotos/<nome_da_foto(chave)>.jpg` (SHA-1 da chave que o App põe em
  `Foto`; o nome nunca é caminho), servida em `.../curadoria/foto/<nome>.jpg` atrás do login, só para quem `pode_programar`. Sem a
  foto, a tela diz "sem foto".
  **Pendente (decisão de 27/10): a foto da curadoria: falta a rota assinada App→Nexus, como a do extintor (`hseq/fotos.receber`),
  combinada com a sessão do App.** O App ainda não manda as fotos; o transporte (a rota, o rótulo da chave de assinatura e o esquema
  do nome da foto) é um contrato a fechar com a sessão do App, e o Nexus não tem a rota de recebimento. Até lá, "sem foto".
- **Lembrete na tela:** grupo, criticidade e Curva ABC da peça nova não se gravam pela API (testado em 09/10): completar na tela do
  Fracttal.
- **Cadastrar roda na PONTE `/os/_nexus/inventario/curadoria/cadastrar` (`ponte_os.py`), não em `/t/pcm`:** ele cria a peça no Fracttal
  com o login de quem decide, e esse login (o cookie `os_sessao`, `Path=<raiz>/os`) não chega às rotas de `/t/pcm`. A página fica em
  `/t/pcm`, o formulário do cadastro (`data-ponte`) vai por `fetch` (`static/pcm-ponte-inventario.js`) e a ponte responde JSON. As
  outras três decisões (é a peça X, confirmar, descartar) só gravam no livro e ficam em `/t/pcm/.../curadoria/decidir`, que recusa
  `cadastrar` (400). Quem entrou pela senha de administrador decide as três e no cadastro leva 409 (não é uma pessoa); a conta do
  Fracttal do cookie que não é a pessoa da sessão, 409; sem o cookie, 401 com o link do login do Fracttal. 429 do Fracttal e rede que cai também têm texto (`erros.resposta(ex, ao="cadastro")`: o código ficou reservado, repetir
  com os mesmos dados não cria outra peça; não diz "é o mesmo número", que é da régua). Prova com o `estoque_da_sessao` DE VERDADE e o
  cookie com `Path=/os`: `test_o_login_do_fracttal_so_chega_na_ponte` (régua e curadoria).
- **Provar:** `tests/test_pcm_inventario_curadoria.py` (o código novo, as pendências, cadastrar com a resposta perdida e com o pedido
  que nem chegou, a reserva entre linhas, "é a peça X" no lote, o genérico, o motivo cifrado, a linha decidida, a contagem gravada,
  o 403 de quem não é PCM, os status, a foto) com mutações em cada regra acima, todas pegas. A revisão de 27/10 acrescentou: a
  contagem gravada durante o cadastro, a reserva com outros dados, a peça achada com outro nome, as travas (a mesma linha, o cadastro
  lento, a mesma sigla) e a tela de quem só olha sem descrição nem foto.

## Inventário do almoxarifado: a gravação no Fracttal (`inventario/gravacao.py`, a ponte em `inventario/ponte_os.py`; 26/10/2026)

O "Gravar N alterações" da contagem aberta grava o saldo CONTADO no Fracttal, no login de quem aprovou, numa thread (como o
"Gerar a semana"); a tela olha o `estado.json` a cada 3 s. O Fracttal não ajusta por peça: abre-se uma SESSÃO do almoxarifado
(modo 2), grava-se o saldo absoluto de cada peça e fecha-se com a referência (finalizar + voltar ao modo 0). **Com a sessão
aberta o almoxarifado fica travado** (nem entrada, nem saída, nem pedido de compra; o ATHN-MTS200 ficou assim em 26/10, em
inventário físico). Tudo no módulo existe para nunca deixar um almoxarifado travado sem aviso.

- **Onde mora cada rota:** o cookie do Fracttal (`os_sessao`) tem `Path=/os`, e o navegador não o manda para `/t/pcm/...`:
  `estoque_da_sessao` numa rota da tela dá sempre `SemLogin` em produção. Por isso `POST /os/_nexus/inventario/<id>/gravar`,
  `.../continuar` e `.../encerrar` moram na ponte (`ponte_os.bp`, registrado na raiz pelo `registrar`, como o `bp_raiz` do OS
  Creator): outro site 403, quem não `pode_programar` 403, a senha de administrador 409 (não é uma pessoa), sem o JWT 401 com
  o link do `/os/login` e a volta à contagem, a conta do Fracttal do cookie que não é a pessoa da sessão do Nexus 409 ("a
  sessão do Fracttal é de outra conta"; o cookie do OS Creator sobrevive à troca de pessoa no mesmo navegador), o controle
  ilegível 409 com o texto dele (não "só quem aprovou"). Quem entrou pelo Fracttal e perdeu o cookie nem chega à ponte: o
  portão do Nexus encerra a sessão junto (401 `sessao_encerrada`, com `login: true` e o endereço em `entrar`; as telas da ponte
  tratam esse 401 à parte e só usam o `login` quando ele é texto: antes o `true` virava o endereço e a página ia para /true). `GET /t/pcm/pecas/inventario/<id>/estado.json` fica na
  tela (não fala com o Fracttal).
- **Aprovar** (`aprovar`, o que a ponte chama): relê o livro, lê o saldo NA HORA com o login de quem aprova, monta o lote pelas
  contas (só `not tirada and situacao in MEXEM`) e confere o que a tela mostrou: o N e a `assinatura` (o hash de id_item,
  sistema e contado de cada peça do lote, posta como `data-assinatura` no botão, que vem no pedaço do `lote` da ponte junto do
  Sistema que ele confere; a página só ouve o clique), os dois obrigatórios (400 sem eles). O N
  igual não basta: o saldo que foi de 10 para 11 com o contado 12 segue "para cima". Mudou: 409 "a contagem mudou desde que
  você abriu a tela; recarregue". `iniciar` grava UM `aprovada` por peça (a leitura sabe o lote por eles), e o específico cujo
  genérico ainda tem linhas por identificar na curadoria vira `conflito` já ali (as unidades pendentes talvez sejam dele; o
  "confirmar" sem alvo é pendente, como em `contas._ler`). **A contagem tem UMA trava** (`travas.CONTAGEM`, um processo só):
  `aprovar` a segura das leituras até o registro da aprovação; `revisar` e `curadoria.decidir`, da conferência do estado até a
  escrita. Caso da revisão final de 27/10/2026: o "tirar" ou o "é a peça X" que caía entre a leitura do livro e o `aprovada` era
  gravado e ignorado pelo lote já montado; agora espera e é recusado (409, a contagem já está gravando). Prova:
  `test_a_revisao_durante_a_aprovacao_espera_e_e_recusada` e `test_a_curadoria_durante_a_aprovacao_espera_e_e_recusada`.
- **Por lote de 50, uma sessão** (`INVENTARIO-<contagem>-L<n>`; a 2ª sessão do mesmo lote, depois de uma parada, é `-S<k>`,
  para o "achar o fechamento pela referência" nunca confundir as duas): modo → o que se moveu desde o "Contada em" (sem as
  sessões da própria contagem: `mexidas_desde(..., ignorar_prefixo="INVENTARIO-<contagem>-")`) → ler → ligar as nunca ligadas
  (ANTES de abrir: ligar no modo 2 não foi provado) → modo DE NOVO (ninguém abriu no meio) → o marco → abrir → ler (com o modo aberto
  nada se move: é a leitura que vale) → cada peça: saldo diferente do aprovado ou mexida depois da contagem é `conflito` e não
  grava; senão grava o saldo absoluto → fechar → achar o movimento pela referência (o `movimento_fracttal` do evento é o folio
  dele, nos dois caminhos, e não o `folio_return`) → reler fora da sessão (bate: `peca_gravada`; não bate: `erro`). Modo 3:
  para sem mexer. Modo 2 que o controle não diz que é nosso: para sem mexer.
- **O 2 que o controle diz ser nosso, numa retomada, é conferido:** logo antes de abrir, o controle guarda o `marco` (o id do
  movimento mais novo do almoxarifado, `ultimo_movimento`); na retomada, um AJUSTE (tipo 15) sem a nossa referência com id
  maior que ele (`ajustes_depois`) é alguém que finalizou a nossa e abriu a dela: para com "o almoxarifado está em ajuste por
  outra pessoa ou outra tela: feche o ajuste na tela do Fracttal e depois clique em Continuar ou Encerrar". Compara id, não
  relógio, e só ajuste: a 1ª versão contava todo movimento sem a nossa referência desde o `aberto_em` (cortado no segundo), e a
  prova de 27/10/2026 parou uma retomada, para sempre, por um movimento do mesmo segundo da abertura; entrada e saída comuns não
  acontecem com o modo aberto, então a que aparece é de antes. **QUASE nunca se finaliza a sessão dos outros, e não nunca:**
  quem só solta o modo no Fracttal, sem finalizar, não deixa rastro, e uma sessão aberta por outra pessoa logo depois pareceria a
  nossa.
- **O finalizar nunca se repete às cegas.** O fechamento são dois pedidos. O 429 no fechar espera 62 s e PROCURA o fechamento
  pela referência (`achar_movimento` desde a hora em que a sessão abriu, menos 10 min de folga de relógio): achou, só volta ao
  modo 0. A resposta perdida (não o 429) espera os mesmos 62 s antes de procurar (o histórico pode ainda não mostrar o
  finalize). Toda retomada com o modo 2 e alguma peça escrita procura antes de gravar mais ou de finalizar (cobre o disco que
  falhou ao parar junto com o 2º passo do fechamento). A sessão em que nada se gravou não tem movimento para achar: só volta ao
  modo 0 (um 2º finalizar é erro no Fracttal).
- **Parar:** 429 de novo depois dos 62 s → espera mais 62 s, fecha com o que gravou e para ("limite do Fracttal"); erro
  inesperado → fecha, registra `erro` com o TIPO (nunca o texto do Fracttal) e para; login expirado → para sem poder fechar. Se a
  sessão ficou aberta, a contagem E a lista das contagens mostram o aviso forte "X ficou travado em ajuste no Fracttal; quem
  aprovou precisa continuar para destravar". Releitura que não bateu → para; o "Continuar" só relê (bate: gravada; não bate:
  `conflito`). O disco que falha enquanto para não segura o fechamento no Fracttal. O Nexus que reinicia no meio: a tela vê
  "parada" (e o aviso, se aberta). Os logs levam só o tipo do erro.
- **Continuar:** só quem aprovou (pelo `pessoa_hmac`; o controle não guarda e-mail), no login dele. A retomada parte do controle e
  do modo: a sessão `aberto` com modo 2 regrava o que faltava (absoluto) e fecha; `fechando` procura antes de finalizar; com
  modo 0 a releitura decide cada peça.
- **Encerrar** (Levi, 26/10/2026): a gravação parada que ninguém vai continuar. Quem aprovou, a qualquer hora; o administrador
  do Nexus, depois de 24 h parada. Só com o almoxarifado FORA do modo 2, lido na hora pela ponte (encerrar com a sessão aberta
  largaria o almoxarifado travado sem dono). Motivo obrigatório, só cifrado. As peças já conferidas ficam `peca_gravada`; cada
  uma das outras vira `conflito` com o motivo, no nome de quem encerrou (a contagem sai de "gravando" e fica "gravada com
  conflitos"); o controle fica `encerrada` e a vez do almoxarifado é solta.
- **O controle** `<NEXUS_DADOS>/almox_inventario/<contagem>.json` (o estado de cada lote e de cada peça, a hora da sessão) e
  **a vez** `trava-<almoxarifado>.json`: uma gravação por almoxarifado ("já tem uma gravação em andamento neste almoxarifado"),
  e a parada no meio segura a vez até quem aprovou continuar ou alguém encerrar (o arquivo segura a reinicialização). **Nunca
  o login:** o JWT e o e-mail vivem só na instância do `Estoque`. Os eventos vão ao livro SEMPRE com a sessão fechada (o banco
  lento não segura o almoxarifado travado), com o `evento_id` tirado da contagem, do tipo e da peça: registrar de novo não
  duplica a auditoria.
- **O deploy espera o lote aberto** (Levi, 26/10/2026): o `deploy/atualizar.sh` pergunta ao `ferramentas/gravacao_aberta.py`
  (`gravacao.com_lote_aberto`: "gravando", um lote em sessão, salvo há menos de 5 min) e deixa o restart para a rodada seguinte,
  por no máximo 10 min contados da 1ª espera (`DEPLOY.md`, seção 8). Qualquer falha do ajudante deixa o deploy seguir.
- **Provar:** `tests/test_pcm_inventario_gravacao.py` (o `EstoqueFalso`, com o `"finalizar"` como ponto de defeito à parte, e
  um relógio de mentira: nada espera de verdade) e `tests/test_deploy_espera_gravacao.py` (o ajudante e o script); mutações nas
  regras acima, todas pegas. O teste da ponte manda o `os_sessao` com `Path=/os` pelo `estoque_da_sessao` de verdade: a ponte
  vê o login, a rota `/t/pcm/...` não. Provada no navegador em 26/10/2026 numa cópia de prova com o `EstoqueFalso` (1366 e 375 px,
  escuro e claro): o "Gravar" pelo pedaço do lote, a peça mexida depois da contagem em conflito, o login que expira com a sessão
  aberta (o aviso forte na contagem e na lista), o "Encerrar" recusado em modo 2 e o "Continuar" que termina (6 gravadas, 1 em
  conflito, o par de movimentos com `INVENTARIO-C-1-L1`, o almoxarifado de volta ao modo 0). A página da contagem gravada com
  conflito aponta as peças na Auditoria (filtrada pela contagem). A prova no almoxarifado de teste do Fracttal de verdade é a
  seção do fluxo, "Falta".

## Inventário do almoxarifado: a auditoria (`revisao.montar_auditoria`, `templates/pcm/inventario_auditoria.html`; 26/10/2026)

O desenho (4.6): uma linha por evento, que nunca muda, e o histórico com que o PCM defende o mínimo. Tela
`/t/pcm/pecas/inventario/auditoria` (sub-rota da tela `pecas`, do setor PCM; outros, pela marca).

- **O que mostra:** os eventos do `fato_evento_inventario`, do mais novo ao mais velho: a hora de Brasília, o tipo
  (`ROTULO_EVENTO`, um nome para cada `fato_inventario.TIPOS_EVENTO`; a cor só reforça a palavra: verde o que foi ao Fracttal,
  âmbar o conflito e a recontagem, vermelho o erro), o almoxarifado e a peça (os nomes vêm dos livros do App, numa cópia de 5 min;
  sem eles, o ID), a contagem (link para ela) e os números (de para; na régua, o mínimo; o movimento do Fracttal e o lote).
- **O motivo nunca:** é texto livre e mora só cifrado no livro; a linha diz "motivo cifrado", e a contagem aberta o mostra a quem
  revisa. **Quem fez, só para quem pode revisar** (`pode_programar`): o nome sai da ficha do cadastro pelo `pessoa_id` (sem a
  ficha, "ficha N do cadastro" ou "sem ficha no cadastro"); para os outros setores a coluna nem existe, e o nome não entra na busca.
- **O almoxarifado de teste fica de fora**, como nas outras telas.
- **O filtro:** tipo e busca na própria página (`filtro-local.js`: cada linha leva `data-f-tipo` e `data-f-busca` sem acento nem
  caixa); o endereço com `?tipo=` e `?busca=` já chega com as outras linhas escondidas.
- **Não fala com o Fracttal.** O livro que não se lê vira o aviso, nunca "nenhum evento".
- **Provar:** `test_auditoria_lista_e_filtra` e `test_auditoria_sem_livro_diz_e_nao_quebra` (`tests/test_pcm_inventario_telas.py`),
  com mutações no filtro do teste, na ordem, no `?tipo=`, na busca sem acento e no nome na busca de quem só olha, todas pegas
  (tirar o `pode` do `quem` escapa de propósito: a coluna também só existe para o PCM, defesa em dobro). As quatro abas juntas:
  `test_as_abas_do_inventario_ficam_juntas`.

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
  **A SUBTAREFA: a tarefa num ativo** (19/10/2026; o programador do PCM tirou UM inversor da OS 16739 e a confirmação
  disse que saíam os 15: "parece que está puxando pelo nome"). Só pelo nome, o `sem:` e o "Mover" levavam todas as
  linhas de mesmo nome (W43: 138 OS + nome em mais de um ativo; a linha `16739; ter; ... Inversor` empilhou os 15 na
  terça até "31:27"). O `banco_dados.json` não traz o id da subtarefa do Fracttal; a identidade dela é OS + código do
  ativo + tarefa, a mesma do STEP A2 do robô e do `fonte_bd_api`. A palavra pode ser `nome @ CÓDIGO`
  (`16739; sem: [GreenYellow] - MPT - Inversor @ MCB100-INVR2.7`, `16739; qua; ... Inversor @ MCB100-INVR2.6; tarde`,
  `só: Inversor @ CÓDIGO`): casa só a linha com aquele código (exato, sem caixa) cujo nome contém o nome; sem `@`, o
  nome como sempre. Quem casa: `_casa_tarefa` no robô (STEP A2, A3 exclusões, pins e pendentes) e no motor
  (`_tarefa_excluida`, `_tarefa_matches_pin`, o "só:" do modo A), e `geracao.casa_tarefa` no `aplicar_sem`; o
  `test_subtarefa_o_motor_e_o_nexus_casam_igual` prende o motor e o Nexus. A janela da OS oferece no **"O que"** a
  subtarefa do cartão (o padrão), cada subtarefa, a tarefa "em todos os N ativos" (pelo nome, com o aviso das de nome
  parecido) e a OS inteira; `oss` leva os ativos de cada tarefa (`cods`), e a OS com uma tarefa só em vários ativos
  também ganha o "O que" (antes o "Tirar da semana" dela virava `não`). A fila manda o `codigo` e o servidor confere
  que a tarefa da SEMANA está naquele ativo. A mescla: subtarefas são alvos próprios; a que volta para um dia sai do
  `sem:` sozinha; se o `sem:` tirava a tarefa em todos os ativos e UMA volta, ele vira uma subtarefa por ativo que
  continua fora (`tarefas_por_os` da semana). Prova no robô (planilha real da W43, OS 15968 com 12 QGBTs): só o QGBT1
  saiu (o QGBT10 a 12 ficaram) e só o QGBT2 foi para a quarta; as linhas só por nome deram a planilha idêntica, célula a
  célula, à do robô de antes, e o robô de antes ignora o `@` (não casa nada): sobe primeiro o robô, depois o Nexus.
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
  público). Quem gravou o quê: `reprogramacoes.jsonl` na pasta de trabalho, À VISTA DE TODOS (só gravar é do PCM):
  na semana em curso, em "Quem gravou nesta semana", dentro do bloco abaixo; nas outras, em "Já gravadas para esta
  semana", cada uma com o lugar onde foi parar.
- **Reprogramações da semana em curso** (19/10/2026; o programador do PCM: "eu não achei isso da reprogramação", "ainda
  tá meio que fantasma pra mim, sem poder editar"). A fila só ACRESCENTA linhas; o bloco `#reprogramacoes`, no fim do
  Quadro da semana em curso (no lugar de "Já gravadas"; Levi escolheu "Dentro do Quadro" entre página própria, bloco e
  item de menu), mostra o `Observacoes_Semana_Atual.txt` INTEIRO, cada linha editável e removível, e o botão
  "Reprogramações da semana em curso" no topo do Quadro leva a ele. O bloco vem depois da página
  (`/t/pcm/quadro/reprogramacoes?parte=1`, `static/pcm-reprogramacoes.js`): ler o GitHub (até 60 s) não atrasa o
  Quadro. Cada linha mostra o que faz em palavras e a usina, pela semana (`quadro.descrever`), e avisa a OS que a semana
  não tem. Gravar (`quadro.regravar_semana_em_curso`, POST no mesmo endereço) é de `pode_programar`, só de segunda a
  sexta da semana publicada no App (`telas._semana_em_curso`, a regra do `destino`), com o "Confirmo", o sha que a
  pessoa viu (mudou: 409), relê e confere o sha256; grava o arquivo como ficou na tela, com o cabeçalho da semana em
  curso (cabeçalho de outra semana ou sem cabeçalho: o bloco avisa antes). Barra a gravação inteira
  (`quadro.problemas_das_linhas`): a linha que o robô não entende (texto livre, `@usina`, sábado, turno errado, sem dia
  nem "não" nem "sem:", mais de 300 caracteres), a repetida e a que outra da mesma OS, mais abaixo, anula pela regra do
  `mesclar` (o motor e o robô leriam cada um de um jeito); duas `sem:` da mesma OS vão numa linha só. Barrada, o Quadro
  volta com o bloco aberto, o que a pessoa escreveu e o problema de cada linha. **Tirar uma linha desfaz o que ela
  fazia na rodada seguinte**: o robô refaz a semana a cada rodada a partir da planilha publicada (o `semanal.yml` só
  commita o `banco_dados.json`; a planilha só muda pela publicação) e aplica o arquivo inteiro de novo. Até 19/10 o
  bloco dizia o contrário. No
  registro, `acao: "edicao"` com o que entrou ou mudou e o que saiu.
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
- **Provar:** `tests/test_pcm_quadro.py` (60 testes; 24 mutações em 09/10 e mais 12 no tirar tarefa em 15/10, todas
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

## O processador por visita (19/10/2026)

Levi, 19/10/2026: "faça 2 e 3" (o PCM entre os pesos do Nexus). Medido no PC com o cadastro e o banco reais, cada visita
ao Gerar a semana gastava 0,34 a 0,39 s de processador e o Quadro 0,14 s; no notebook do servidor isso é várias vezes
mais, e enquanto uma tela é montada as outras esperam (o Python faz uma coisa de cada vez).

- **O serviço do cadastro é um só por arquivo e chave** (`auxiliar.servico`, `_SERVICOS`): cada visita montava um
  `Servico` novo, e o novo decifrava de novo as ~570 fichas (0,27 s). O serviço guarda o que decifrou até o arquivo do
  cadastro mudar (a marca do armazém).
- **As usinas por dia** (`observacoes.usinas_por_dia`): cada nome do Fracttal normalizado uma vez e cada regra
  compilada uma vez (`_casador`); eram ~28 mil normalizações por visita (a comparação de todos com todos). O resultado é
  o mesmo do `casa` (o teste compara com a conta de antes).
- **O tipo do Fracttal no Quadro** (`quadro._indice_de_tipo`): o índice (OS, tarefa) -> tipo das tarefas da Gestão PCM
  é feito uma vez por leitura dela (a mesma lista enquanto vale a cópia do `fonte.ler_gestao`).
- Depois: Gerar a semana 0,12 a 0,16 s e Quadro 0,05 s por visita, as páginas iguais byte a byte às de antes. Prova:
  `tests/test_pcm_e_registro_leves_19_10.py`.

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
