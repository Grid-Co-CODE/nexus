# CLAUDE.md — Comando: motor de insights, Caixa de entrada e sino

Os setores conversando (Levi, 03/11/2026: "Preciso pensar em uma forma dos setores conversarem entre si de forma
rastreável e clara com chats, notificações..."; sobre a tela de Insights do mockup R18: "essa parte de insights também é
muito boa"; e "construa o que você sugere"). PRD e tarefas no formato do Taskmaster: `.taskmaster/docs/prd.txt` e
`.taskmaster/tasks/tasks.json` (escritos à mão: a CLI do Taskmaster chama IA paga para gerar; a casa é custo zero).

## As fases (uma de cada vez, mostrada ao Levi antes de seguir)
1. **Insights + sino + Caixa de entrada** (esta pasta + `nexus/torres/comando/`): NO AR 03/11/2026 (3cd7564).
2. **Conversa com @menção em cada insight, OS e usina** (`conversa.py`): NO AR 03/11/2026 (b01a060).
3. **Pedidos às áreas com prazo + Tempo de resposta** (`pedidos.py`): ver a seção abaixo.
4. O Início novo ("Pede você agora", paleta preto #030407, azul #1558c9, lima #D4FF24): decidir antes se a paleta vale
   para o Nexus inteiro.

## Os arquivos
| Arquivo | O que é |
|---|---|
| `regras.py` | As regras, PURAS (recebem listas já lidas, devolvem insights). O catálogo `REGRAS` (nome, torre dona, KPI, fonte) |
| `motor.py` | Lê as fontes que o Nexus JÁ lê (uma função por regra em `FONTES`), roda as regras, cópia de 5 min pelo `visao._ler` |
| `estado.py` | Quem assumiu, concluiu ou reabriu, as áreas notificadas e o retorno de cada uma: o livro `nexus_insights · fato_evento_insight` |
| `../torres/comando/__init__.py` | As telas Comando → Insights e Caixa de entrada, o miolo de um insight (`GET /t/comando/insight/corpo`) e o POST `/t/comando/insight/acao` (os endereços antigos `/insights/...` seguem valendo) |
| `../torres/comando/templates/comando/_insight.html` + `static/comando/insights.js` | A linha do insight (`cartao`) e o miolo (`corpo`), que vem só ao abrir |
| `pedidos.py` | O pedido a uma área com prazo e o retorno: o livro `nexus_pedidos · fato_pedido_area`, o prazo (`situacao`), a ordem do mais urgente e o painel do Tempo de resposta (`painel`) |
| `../torres/comando/templates/comando/_pedidos.html` + `tempo_de_resposta.html` | O bloco dos pedidos (no insight e na página do objeto) e a tela do painel; `POST /t/comando/pedido/acao` |
| `conversa.py` | A conversa presa ao objeto com @menção: o livro `nexus_conversas · fato_mensagem`, as menções não lidas (`para_mim`) e a lista do @ (`pessoas_mencionaveis`) |
| `../torres/comando/templates/comando/_conversa.html` + `static/comando/conversa.js` | O componente da conversa (dentro de cada insight e na página da OS e da usina) e o @ |
| `../casca/__init__.py` (`_sino`) + `base.html` | O sino do topo |
| `avisos.py` + `../casca/__init__.py` (`_avisos_do_sino`, `POST /t/comando/aviso/lida`) | Os avisos das OS de cada pessoa no sino ("OS x concluída pelo técnico", "Sua solicitação gerou uma OS" e, desde 08/11/2026, "OS x criada para você"; desde 11/11/2026, tudo da OS da solicitação, com a cancelada) e o Marcar como lida: o livro `nexus_avisos · fato_evento_aviso` |
| `solicitacoes_fracttal.py` | As solicitações do Fracttal que viraram OS (REST `work_requests`, por trás, a cada 5 min, na memória) e o motivo das OS delas canceladas, para os avisos de quem pediu (11/11/2026) |

## As regras da Fase 1 (e de onde cada uma lê)
| Regra | Torre dona | Fonte |
|---|---|---|
| R03 religamento repetido na mesma cabine (3+ em 30 dias) | cos | `cos/religamentos.painel` sobre `andamento.ler_ocorrencias` de cada cliente |
| R05 sem comunicação há mais de 24 h | cos | o banco: `nexus_cos_normalizacoes · fato_ocorrencia_aberta` (só Thopen) |
| R06* OS corretiva aberta em ativo que já tem chamado de garantia | chamados | o banco: `nexus_os · fato_tarefa_os` × `nexus_chamados · fato_chamado` (pelo `equipamento_id`) |
| R07 extintor vencido | hseq | `hseq/extintores.extintores` + `decisoes.separar` (sem os excluídos) + `por_usina` |
| R09 equipe acima da capacidade na semana | pcm | o banco do robô do PCM (`pcm/fonte.ler`): `resumo` da `semana_ativa`, `hh_util > hh_disp` |
| R11 usina sem ronda há mais de 7 dias | campo | `campo/visao.rondas().cobertura` |
| R13 chamado aguardando o fabricante há 5 dias ou mais | chamados | `campo/responsaveis.chamados` (o fato + a troca de status da tela de Garantias) |
| N01 normalizada com a OS aberta 7+ dias / hora a corrigir | cos | `cos/normalizacoes.ler` + `_item` |

**Fora da Fase 1, e por quê:** R01 (a anomalia sem OS é calculada pela plataforma, numa moldura; não passa pelo Nexus),
R02, R04 e R08 (pedem ajuste), a R06 completa (falta a vigência da garantia: nenhuma tela tem "garantia até"), R10 e
R12 (sem fonte). **Nenhuma regra lê o Fracttal, a SunOp ou a PV Operation**: as OS e os chamados são os livros que o
Nexus publica de hora em hora.

## Pedidos às áreas, com prazo, e o Tempo de resposta (Fases 1 e 3, 03/11/2026)
Levi: "religamentos em 30 dias e etc é coisa da engenharia, já está com eles... pode aparecer tipo 'notificar
engenharia'"; "o manager quer algo como notificar as áreas e saber como está e receber retornos dessas áreas"; e, na
Fase 3: o prazo, "Quem pede sempre escolhe" (sem prazo padrão), e o pedido vale para o insight, a OS e a usina.
- **O livro é `nexus_pedidos · fato_pedido_area`** (`pedidos.py`): `pediu` e `respondeu`, um `pedido_id` por área (quem
  pede a três áreas grava três; cada área responde e é medida sozinha). O notificar e o responder moravam no livro dos
  insights até 03/11/2026, que nunca gravou nenhum (conferido no banco antes da troca): não há o que migrar.
- **Pedir:** dentro do insight, na página da OS e na da usina (`_pedidos.html`, "Pedir retorno a uma área"): as áreas
  (as torres de operação, fora o Comando e o OS Creator; no insight, as de `regras.REGRAS[...]["avisar"]` já marcadas:
  R03 → Engenharia, R07 → Segurança e Campo...), o **prazo obrigatório** (de hoje a um ano) e o que precisa. A área com
  pedido aberto sobre o mesmo objeto não ganha outro; resolvida, pode.
- **Responder:** só quem é da área (o setor vê a torre; `MO.torres_da_pessoa`): Recebido, Em andamento ou Resolvido, com
  o texto. Vale o último; o tempo até a 1ª resposta é o do 1º `respondeu`, e até resolver, o do 1º `resolvido`.
- **Prazo:** atrasado = aberto depois do dia do prazo; vence hoje; no prazo = resolvido até o fim do dia do prazo
  (Brasília). A cor diz isso (crítico, alerta, info) e a palavra também.
- **Onde aparece:** a Caixa ("Pedidos para o seu setor", o atrasado primeiro, e "Pedidos que você fez"); o sino (o pedido
  sem resposta ou atrasado para as áreas da pessoa; o atrasado conta como crítico); a linha do insight (a área com
  "Atrasado" ou "Vence hoje"); e Comando → **Tempo de resposta** (por área: pedidos, abertos, sem resposta, atrasados, %
  no prazo e as medianas; e a lista dos atrasados). Sem filtro de período e sem meta de % por enquanto: perguntar ao Levi
  antes de pôr.
- O link de todo pedido é a página do objeto (`/t/comando/conversa/<tipo>/<id>`), que mostra os pedidos e a conversa e
  abre para quem só tem a Caixa. O pedido sobre um insight que a regra parou de apontar continua (o título diz "a regra
  não aponta mais"): a área ainda responde.

## A conversa com @menção (Fase 2, 03/11/2026)
Levi: "pode seguir para a fase 2". A conversa mora NO objeto (`tipo:id`: `insight:R07:2`, `os:16702`, `usina:12`),
como fazem ServiceNow, Jira e Linear, não num chat solto.
- **Onde aparece:** dentro de cada insight (a lista dos Insights e a Caixa), e na página `/t/comando/conversa/<tipo>/<id>`
  (a OS e a usina; a conversa nova sai da Caixa: "Começar uma conversa sobre uma OS ou uma usina").
- **@menção:** digitar @ abre a lista das áreas (as torres de operação) e das pessoas com setor (Base → Acessos → Pessoas e
  setores; o nome do pessoal do Fracttal, 1 h na memória). A lista é pedida ao servidor só no 1º @
  (`/t/comando/conversa/pessoas`), nunca ao abrir a página. A pessoa vai pelo código do e-mail (`pessoa_hmac`), a área
  pela torre; o `@Nome` que sai do texto não vai. Sem JavaScript, as áreas se marcam em "Mencionar áreas".
- **Quem é avisado:** a pessoa mencionada e todo mundo cujo setor vê a torre mencionada. Aparece na Caixa ("Menções
  para você", uma linha por conversa) e no sino, até a pessoa marcar como lida ou escrever na conversa (escrever conta
  como ler). Quem escreveu não se avisa.
- **O sino só lê as cópias** (`conversa.copias()`): com a cópia vencida (1 min) ou vazia, a leitura das conversas e dos
  eventos dos insights começa por trás, e o mencionado vê o número sem precisar abrir a Caixa antes.
- **Acesso (03/11/2026, Levi: "libera a caixa para todos os setores"):** a Caixa de entrada é de todo setor
  (`Tela.de_todos`, entra no `setor_telas.das_do_setor` como a tela do dono), então todo mencionado vê o aviso. O miolo e
  as ações do insight moram em `/t/comando/insight/` (singular): `/insights/...` casa com a tela Insights no portão, e quem
  só tem a Caixa não abriria o insight. Quem só tem a Caixa abre o miolo dos insights das torres dele e dos que pedem
  retorno a ele (`_ve_o_insight`); a tela Insights continua pela marca.

## Os avisos das OS de cada pessoa (04/11/2026)
Levi: "notificações para OSs abertas por mim que tiveram resposta ... tem que ter um botão de marcar como lida!"; "penso
tanto em execução de OS quanto solicitação ... aí clica na notificação e aparece a OS, pode ter um botão para fazer
download do pdf da OS". No quiz, "resposta" é o técnico executar a OS.
- **"OS x concluída pelo técnico":** as OS que a pessoa criou (o "Criado por", pelo nome, com a regra do homônimo do
  `os_central.filtrar`) que foram para Em Verificação ou Concluída nos últimos 7 dias, pela data de fim; quem executou é o
  atribuído, e a OS que a própria pessoa executou não avisa. Vem da lista central de OS do OS Creator: nenhum pedido ao
  Fracttal, com o atraso dela (minutos). Nunca é gravado: só o lido dele.
- **"Sua solicitação gerou uma OS":** por dois caminhos, que dão o mesmo aviso (`S:<código da solicitação>`, uma vez só).
  O evento `gerou_os`, gravado na hora em que o PCM aprova na Fila do OS Creator (`rotas_solic.AO_APROVAR`, que a ponte
  liga; por trás, no contexto do Nexus), para quem pediu pelo código do NOME (prefixo `nome:`, separado do código do
  e-mail). E, desde 11/11/2026 (Levi: "também deve mostrar quando uma solicitação feita gera OS e deve chegar todas as
  notificações dessa OS!"), as solicitações lidas no Fracttal pelo REST (`solicitacoes_fracttal.py`: `GET
  /api/work_requests?since=`, os últimos 30 dias, a cada 5 min, POR TRÁS, na memória; nada vai ao banco): a aprovada
  direto no Fracttal também avisa, com até ~10 min de atraso (a leitura e a lista central). Quem pediu, pela conta do
  Fracttal (`id_account`), pelo e-mail de quem pediu ou, sem a conta no catálogo, pelo nome. A hora é a da criação da OS.
- **Tudo da OS da solicitação chega a quem pediu** (11/11/2026, `avisos.da_solicitacao`): a ida para Em Verificação e a
  conclusão ("OS x da sua solicitação concluída pelo técnico", o mesmo `E:` de quem criou) e o cancelamento ("OS x da sua
  solicitação foi cancelada", `C:<id da OS>`, selo "Cancelada", com o motivo, que o leitor lê uma vez por OS pelo REST da
  OS; o Fracttal não guarda a hora do cancelamento, e o aviso leva a hora em que o leitor o viu). Vale para as OS geradas
  de `SEGUIR_DESDE` (11/11/2026) em diante: sem isso a 1ª leitura avisaria o mês de uma vez. A solicitação pedida há mais
  de 30 dias e aprovada agora fica de fora. Nos testes o leitor não vai ao Fracttal (`NEXUS_SOLICITACOES_FRACTTAL=1` liga).
- **"OS x criada para você"** (08/11/2026, a sugestão de uma colega do PCM, "Criação de OS direcionada ao usuário", que o
  Levi aprovou): as OS em processo atribuídas à pessoa (pelo id dela no Fracttal) e criadas por OUTRA pessoa, de
  `ATRIBUIDAS_DESDE` (08/11/2026) em diante e nos últimos 7 dias, da mesma lista central (nada vai ao Fracttal). A que a
  própria pessoa criou para si não avisa. **O lote vira um aviso só:** 3 ou mais da mesma pessoa no mesmo minuto (a
  programação semanal, as clonagens) dão "N OS novas para você", que leva à visão "Atribuídas a mim" do Histórico daquele
  dia (sem o card; o `aviso_id` é `L:<quem criou>:<minuto>`, com o id de quem criou ou um código curto do nome, nunca o
  nome). O selo é "Para você". Os técnicos de campo usam o App: o aviso serve a quem trabalha no Nexus.
- **Quem a pessoa é no Fracttal** (08/11/2026, `avisos._do_fracttal`, guardado 1 minuto): o id dela pela ligação de Base →
  Acessos → Pessoas e setores (a última decisão com o código do e-mail do login, a mesma que dá o setor), e a conta e o nome
  que o Fracttal grava pelo catálogo de pessoas do OS Creator (pelo id; sem a ligação, pelo e-mail). Até então o aviso de
  execução casava só pelo nome da sessão: quem entra pela conta Microsoft com o nome escrito de outro jeito que o "Criado
  por" do Fracttal ficava sem aviso, e a solicitação aprovada casa agora pelo nome do Fracttal ou pelo da sessão. Sem a
  ligação nem o catálogo, vale o nome da sessão, como antes. Medido no PC em 08/11/2026: as 37 pessoas com setor, todas
  achadas no catálogo pelo id.
- **No sino:** a parte "avisos das suas OS", no alto; o clique abre o card da OS (`oscreator/card_os_abrir.html`, com o
  botão do PDF) por cima da tela, e sem JavaScript a página da OS. "Marcar como lida" e "Marcar todas como lidas" são
  formulários (`POST /t/comando/aviso/lida`) que o script do sino manda por fetch pedindo JSON, **sem recarregar a tela**
  (Levi, 05/11/2026: "cada vez que clico em marcar como lida a tela atualiza... atrapalha a experiência do usuário"): o
  aviso sai da lista, o número do botão e o do título descem, e o sino fica aberto; o que não gravou diz "Não marcou:
  tente de novo". Sem JavaScript (ou sem resposta que se leia, como o login vencido), o formulário volta para a mesma tela,
  como antes. O lido vale em qualquer computador (o banco). **Mora em `/t/comando/`** porque o Caddy do servidor só manda ao Nexus a raiz, `/t/*` e poucos outros
  caminhos: nasceu em `/avisos/lida` (04/11/2026), que no servidor caía na plataforma, e o Marcar como lida não gravava
  (`tests/test_rotas_no_caminho_do_nexus.py` pegou; regra em `nexus/casca/CLAUDE.md`, "Regras que já custaram caro").
  O portão por setor abre o caminho a quem tem uma tela do Comando, e a Caixa de entrada é de todo setor; "aviso" no
  singular, como `insight/acao`: uma tela "avisos" casaria com o caminho e trancaria quem não a tem.
- **O botão do topo leva o ícone do OS Creator** do menu lateral (lido da torre `os`), no lugar do sino (Levi,
  04/11/2026: "quero que troque esse símbolo de sino pelo símbolo do OS Creator"). As classes seguem `sino-*`.
- O sino só lê a cópia de 1 minuto do livro (`avisos.copia`) e a conta da lista central da pessoa (1 minuto, por versão
  da lista): nenhuma página espera o banco.

## Comando > Usinas e o prontuário (11/11/2026)

Levi: "Em comando quero a mesma visão de Início > Usinas do mockup" (o R18). A tela era o lugar reservado da casca; virou
`/t/comando/usinas` (`usinas.py` + `torres/comando/templates/comando/usinas.html`, `static/comando-usinas.js`): a faixa
com uma barra por usina na cor do estado de agora, a legenda, os filtros na própria página (`filtro-local.js`: cliente,
estado e a busca) e a tabela das 138 mobilizadas, que ordena pelo cabeçalho. Cada coluna vem da tela dona, nada se
inventa: usina, cliente e cluster da Visão do responsável; código, MWp (`potencia_contratual`, a única preenchida nas
138) e tipologia ("SOLO TRACKER" = Tracker) do cadastro; Agora do tempo real (a ponte da Visão do cliente); Atingimento
e PR / meta da meta do mês da Visão; OS abertas e atrasadas do bloco Manutenção dela; Insights = os do motor que não
foram concluídos, ligados pelo nome da usina; Conformidade = extintores vencidos (o PPCI) e sem luvas na última ronda (o
EPC). A fonte que não lê vira "sem leitura" na coluna dela, nunca 0. A ordem: o estado mais grave agora e, dentro dele,
o pior atingimento.

**Fora, por decisão do Levi (11/11/2026):** o Score de saúde do mockup ("Fora por agora": o Nexus não tem essa nota, e
criar uma é regra nova). **O clique na usina** abre o prontuário no próprio Comando ("No próprio Comando"),
`/t/comando/usinas/<id>`: a linha dela, a Central da usina da Usinas 360° em leitura (a mesma conta,
`torres.campo._central_da_usina(todas, usina_id)`), no desenho dela, e os insights vivos da usina. As janelas da Central
(o dia a dia, a ronda, a PT, o relatório) são sub-rotas da Usinas 360°: o pé do prontuário leva até lá para quem tem
acesso. A linha do tempo e o "Em três frases" do mockup não estão: o Nexus ainda não junta os eventos de todas as
fontes numa linha só. O CSS da tela usa o prefixo `cmu-` (o `cu-` é da Central, no campo.css).

Prova: `tests/test_comando_usinas.py` (as colunas, a fonte que falta sem 0, os insights vivos, a lista e o prontuário) e a
renderização com o banco de produção, só leitura, pelo cliente de teste (138 usinas, prontuário sem erro).

## O visual
Uma lista numa superfície só, uma linha por insight que abre ao clicar (Levi: "não sou muito fã dessa barra lateral em
vermelho, temos muito dela... poderia fazer algo diferente?"): a gravidade é um selo (ponto + palavra), sem faixa nem
borda colorida; à direita, com quem está (as áreas avisadas e o retorno, ou o dono). Aberta: o que a regra viu, o que
fazer, as áreas e os retornos, e as ações.

## As regras da casa aqui
- **A lista vem leve; o miolo vem ao abrir** (03/11/2026, Levi: "cliquei em nexus insights e travou tudo"). Medido com o
  dado real: 327 insights, a página com todos os miolos dava 2 MB, 1.310 formulários e 12.544 campos, e o navegador
  travava. Agora a linha vem na página e o miolo (5,5 KB) vem por `/t/comando/insight/corpo` quando a pessoa abre
  (`insights.js`); a página caiu para 320 KB e 4 campos. Só os "Pedidos para o seu setor" da Caixa vêm abertos. O
  endereço com `#ins-...` ou `#conv-insight-...` (o sino, a volta de uma ação) abre o dele; sem JavaScript, `?abrir=<id>`.
- **Insights e Caixa nunca esperam a conta** (`motor.sem_esperar`): sem a cópia (o Nexus acabou de subir, e todo push
  reinicia), a conta começa por trás e a tela diz que está calculando e se atualiza em 10 s; o Assumir recusa até a
  lista existir. A conta fria levou 19 s no PC (sem o Andamento, que no servidor soma) e segurava a página.
- **O id do insight é estável** (`regra:objeto`, ex.: `N01:16702`, `R07:<usina_id>`): é por ele que o Assumir sobrevive
  à próxima conta. Mudar o objeto de uma regra solta o que foi assumido.
- **A torre é o dono** (o setor vê as torres liberadas em Base → Acessos): sem cadastro de cadeira. A Caixa de entrada e
  o sino filtram por `motor.torres_da_pessoa()` (`setor_telas.acesso`; o administrador vê tudo).
- **Fonte que falha não derruba as outras**: vira `regras[id]["erro"]`, a tela de Insights diz "não leu" e a Caixa avisa.
- **O sino nunca calcula na página** (as cópias do motor, das conversas, dos pedidos e dos avisos): sem nenhuma cópia,
  não sai número e a conta começa por trás. Conta os avisos das OS da pessoa, as menções sem ler e os pedidos de retorno
  pendentes para as áreas dela. **Os insights sem dono não entram no sino** (Levi, 04/11/2026: "tira insights sem dono
  do sino"; eram mais de mil e escondiam o resto): ficam na Caixa de entrada.
- **Concluído some da Caixa** e fica concluído enquanto a regra seguir apontando (alguém já tratou); Reabrir
  volta. O livro só acrescenta; quem e a nota só cifrados.
- Escrever regra nova: a função pura em `regras.py` (com teste de dado inventado: o caso e o vizinho que fica fora),
  a entrada em `REGRAS` e a leitura em `motor.FONTES`. Fonte nova no banco: governança antes (nexus/dados/CLAUDE.md).

## Prova
`tests/test_comando_insights.py` (cada regra com o caso e o vizinho; o motor com uma fonte quebrada; o Assumir cifrado e
sem repetir; a Caixa só das torres do setor; o sino sem os insights e sem cópia; a lista leve com o miolo ao abrir; a tela
sem cópia que não espera; a Caixa de todo setor). Os testes da torre (`test_torres.py`,
`test_casca_inicio.py`) passaram a esperar o Comando com a Caixa de entrada e os Insights prontos.
`tests/test_comando_pedidos.py` (Fase 3: um pedido por área com prazo obrigatório, só a área responde, o prazo
(atrasado, vence hoje, no prazo) e as medianas do painel com linhas inventadas, a Caixa, o sino, a página da OS e o
Tempo de resposta); `tests/test_comando_conversa.py` (Fase 2); `tests/test_comando_avisos_atribuidas.py` (a OS criada
para a pessoa, o lote e quem a pessoa é no Fracttal); `tests/test_comando_avisos.py` (os avisos das OS: a
execução pela lista central de mentira, a solicitação com os nomes cifrados, o sino com o card e o Marcar como lida
(os dois formulários no caminho da rota), o "Marcar todas", o caminho aberto no portão de todo setor e o gancho da
aprovação) e o `test_aprovar_chama_o_gancho_do_aviso_de_quem_pediu` do
`tests/test_oscreator_solic_pcm.py`.
