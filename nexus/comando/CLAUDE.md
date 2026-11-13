# CLAUDE.md — Comando: motor de insights, Caixa de entrada, demandas entre setores e sino

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
| `demandas_regras.py` + `demandas.py` + `../torres/comando/demandas_tela.py` | As demandas entre setores (12/11/2026): a regra do prazo e dos avisos, o livro `nexus_demandas` e as telas (o bloco da Caixa, a Nova demanda, os Temas do setor e o sininho); ver a seção abaixo |
| `solicitacoes_fracttal.py` | As solicitações do Fracttal que viraram OS (REST `work_requests`, por trás, a cada 5 min, na memória) e o motivo das OS delas canceladas, para os avisos de quem pediu (11/11/2026); desde 12/11/2026 também o mapa OS → quem pediu, da leitura inteira (~400 dias, 100 por página, uma vez por dia), para o filtro Solicitante do Histórico de OS (`ligar_historico`, o gancho da ponte) |

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
138) e tipologia ("SOLO TRACKER" = Tracker) do cadastro; Agora do COS (a fotografia da Ronda COS; ver abaixo); Atingimento
e PR / meta da meta do mês da Visão; OS abertas e atrasadas do bloco Manutenção dela; Insights = os do motor que não
foram concluídos, ligados pelo nome da usina; Conformidade = extintores vencidos (o PPCI) e sem luvas na última ronda (o
EPC). A fonte que não lê vira "sem leitura" na coluna dela, nunca 0. A ordem: o estado mais grave agora e, dentro dele,
o pior atingimento.

**A coluna Agora pelo COS (11/11/2026; até ali era o tempo real).** Levi escolheu "Coluna Agora pelo COS" e, no mesmo
dia, deu a régua: "quando tiver religamento com OS aberta em campo tem que estar como crítico", "atenção vai ser inversor
desligado", "falha de comunicação é sem comunicação e etc". O tipo da falha não vem nas OS em aberto do COS: a fonte é a
fotografia da Ronda COS de cada cliente do Andamento (`cos.andamento.ler`, a mesma do COS > Ronda padronizada, cópia de
30 s por cliente), em que cada ocorrência aberta traz o tipo da tarefa, o tipo da falha, a OS e a etapa; a usina liga
pelo código do Andamento (`b.lig.usina(nome, codigo)`). `classificar` faz a régua: religamento (não remoto) com OS =
Crítico "Religamento em campo"; falha de comunicação (ou o problema "com") = Sem comunicação; inversor desligado (ou "inv")
= Atenção; o "etc", na mesma ideia: o que para a usina (usina, cabine, SKID ou QGBT desligados, proteção, concessionária,
o problema "rede") = Crítico, e o resto = Atenção com o nome da falha. A usina mostra a pior (crítico > atenção > sem
comunicação; no empate, a mais antiga) com a OS, a idade, a etapa e quantas mais. Sem ocorrência: "Sem ocorrência"
(Normal). A usina que nenhuma fotografia trouxe (o cliente cujo Andamento caiu) é "Sem leitura", nunca Normal. O
prontuário mostra as ocorrências abertas no cartão do COS, com o link para a Ronda padronizada do cliente.
**A cor do Sem comunicação é o roxo (12/11/2026, Levi: "Quando for falha de comunicação [...] Na cor precisa estar
roxo").** O tom do grupo `sem_com` em `usinas.ESTADOS` é `semcom` (o roxo do semáforo do Nexus, `--semcom`), e não mais o
azul de informação: o selo, a barra da faixa e a legenda da lista, o ponto do prontuário, o Mapa de equipe
(`campo-mapa.js`, `a_semcom`) e o vídeo wall (`equipe/parede.py`) pegam a cor daqui.
**Como a fotografia do COS liga à usina do cadastro (12/11/2026).** Pelo ligador geral dos fatos
(`dados.fatos.Ligador.usina`, o `b.lig`): primeiro o nome do Fracttal pelo de-para; depois o código pela regra da casa
(`dados.equipamento.usina_do_codigo`, a mesma das normalizações do COS): o código cheio igual ao do cadastro, ou a
terminação que é de UMA usina, e nunca o código com o prefixo de outro cliente. Até 12/11/2026 o ligador geral só olhava
a terminação. **O caso que mudou a regra** (Levi pediu a análise das usinas "Sem leitura"; medido no banco, pelos
códigos que o COS mandou nas ocorrências desde 01/10): o `E1EN-PCN100`, a Poconé da E1 (sem código no cadastro), caía
na Poconé 1 da Thopen (`THPN-PCN100`), e as ocorrências de uma apareciam na outra; e as duas Ipixuna (`2C-IPX100` e
`THPN-IPX100`, a mesma terminação em dois clientes) não ligavam em nenhuma e ficavam "Sem leitura". A mudança foi no
ligador geral (a regra e a medida estão em `nexus/dados/CLAUDE.md`, regra 4): vale também para o Mapa de equipe, a Visão
do cliente, os Acionamentos e a ficha do COS, que ligam a fotografia por ele.
**O que continua "Sem leitura" e por quê (12/11/2026):** as 11 usinas SEM CÓDIGO no cadastro (Apolo: Gravatá II, Iramaia
II, Rio do Peixe I e II; E1: Barra das Garças, Boituva II, Chapada dos Guimarães, Nova Xavantina, Poconé; Elis: Máquinas
1 a 2; Qair: Aquiraz e Cascavel), que só ligariam pelo nome do Fracttal — o conserto é preencher o código no cadastro (o
COS já manda `APOL-GVT200`, `APOL-IRM200`, `APOL-RDP100` e `E1EN-PCN100`) —, e as que o COS nunca mandou pelo código do
cadastro (GD Energy: Sol do Norte 1 e 2; Sal Energia: Cascavel Sunpower), que dependem de o COS confirmar o cadastro
delas na Ronda COS. A usina cujo cliente não respondeu na hora também fica "Sem leitura" (o aviso amarelo diz qual).
**Quem mais lê esta régua (12/11/2026):** o Mapa de equipe da Usinas 360° pinta as usinas pelo `agora_pelo_cos` e o vídeo
wall dele agrupa as ocorrências pelo `classificar` (`campo/equipe/parede.py`); mudou a régua aqui, muda lá sozinho. Cada
ocorrência do `cos_por_usina` leva também o `usina_cod` (o código curto da usina no Andamento, "APR100"), o do cartão
do vídeo wall.

**A faixa, os filtros e a tabela (12/11/2026, Levi, com a referência do mockup).** A faixa do alto é uma barra por usina (todas as mobilizadas, mesmo com filtro) na cor do grupo da coluna Agora, na ordem da tabela; a legenda conta cada grupo. Os filtros seguem o modelo do Histórico de OS do OS Creator Web ("Quero os filtros conforme referência Histórico de OS"): o `campo-filtros.js` monta a busca, o botão Filtros com o painel (Cliente e Agora, que só valem no Aplicar e filtram no servidor) e uma etiqueta por filtro aplicado; a busca filtra as linhas enquanto se digita (`comando-usinas.js`). O cabeçalho da tabela é mais escuro (`--barra`) e as linhas visíveis alternam a cor (`cmu-par`, refeita a cada busca e ordem): "Gostaria do cabeçalho um pouco mais escuro que as linhas" e "uma cor alterando entre as linhas". O `filtro-local.js` saiu desta tela (ele barra o envio do formulário, e o Aplicar envia).

**A 2ª rodada (12/11/2026, Levi, com o print da tabela).** A etiqueta do Agora é o GRUPO (Normal, Atenção, Crítico, Sem comunicação, Sem leitura) e embaixo, numa linha só, o motivo (`usinas.motivo`: "Desligamento", "Inversor em falha", "Tracker parado", "String sem corrente", "Falha de comunicação"...); a OS, a idade e a etapa saíram da célula e ficam no prontuário. O Agora e a Conformidade centralizados; na coluna Usina só o código da UFV, sem o prefixo do cliente ("THPN-FRN100" vira "FRN100"). O quadradinho da faixa mostra na hora a usina e o motivo da cor. Os filtros viraram o modelo do Histórico de OS de verdade ("o cliente seja digitável tal qual é em histórico de OS [...] no mesmo estilo e mesmas funções"): desde o mesmo dia é o componente do Nexus (`static/filtros-os.js`, `fo-*`; ver `nexus/casca/CLAUDE.md`), montado sobre as `<select multiple>` do formulário `data-fo` desta tela (a cópia própria, `cmu-fl-*`, saiu). Os filtros (`usinas.FILTROS`, vários valores por filtro): Cliente, Responsável da UFV (o Responsável O&M da ficha), Agora, Meta do mês (a régua da Visão gerencial: na meta 97% ou mais, atenção 90 a 97%, abaixo de 90%, sem meta) e Conformidade (com pendência, em dia, sem leitura). As "OS atrasadas" são as do bloco Manutenção da Visão do responsável: OS com tarefa aberta e a Data Programada vencida há mais de 10 dias (a régua do PCM), do retrato das OS do Fracttal no banco; a etiqueta diz isso ao passar o mouse.

**Fora, por decisão do Levi (11/11/2026):** o Score de saúde do mockup ("Fora por agora": o Nexus não tem essa nota, e
criar uma é regra nova). **O clique na usina** abre o prontuário no próprio Comando ("No próprio Comando"),
`/t/comando/usinas/<id>` (a seção abaixo). O CSS da lista usa o prefixo `cmu-` (o `cu-` é da Central, no campo.css).

Prova: `tests/test_comando_usinas.py` (as colunas, a fonte que falta sem 0, os insights vivos, a lista e o prontuário) e a
renderização com o banco de produção, só leitura, pelo cliente de teste (138 usinas, prontuário sem erro).

## O prontuário da usina (12/11/2026)

**Para que serve.** Levi: "A ideia do prontuário da UFV é juntar todas as informações daquela usina para que o
supervisor/gestor fique ciente do que está acontecendo na UFV como métricas, pendências, insights e etc. Deixe forma
visual agradável e direta!". É UMA página com duas portas: o clique na usina em Comando > Usinas
(`/t/comando/usinas/<id>`) e a aba "Prontuário da usina" da Usinas 360° > Visão do responsável (`modo=usina`), que era a
Central da usina e foi substituída por ela ("essa visão irá substituir a central da usina, a central da usina! Também
deve ser possível criar OS para a UFV, criar ticket!").

**A forma, e o caso que criou cada regra.** A 1ª versão vinha com tudo aberto (4.775 px) e o Levi cortou: "quanto mais
direto formos, melhor [...] a ideia não é essa página ser uma caixa de texto infinita [...] Primeiramente, dando um
parecer geral, e quando a pessoa quiser se aprofundar, se aprofunda [...] Sejamos assertivos". A 2ª, enxuta, ele aprovou
e pediu o visual: "ficou legal essa parte mais enxuta. Mas eu creio que dá para colocar um pouquinho mais de números
[...] Pelo menos os KPIs principais de performance, meta, OS, pendências [...] e deixar de uma forma mais visual. Então,
o visual na frente, o que está mais importante na frente, e ali aprofundando abaixo [...] mesmo dando drill down, a
informação direta ali na lata [...] E aí a pessoa consiga também clicar e já se encaminhando para aquela informação.
Aquela informação aparecer na tela dela". Por isso a página é, de cima para baixo:
1. **O cabeçalho**: o nome, o estado de agora (o do COS), a ficha numa linha, as pessoas e as ações (Criar OS, Criar
   ticket, Relatório, Conversa).
2. **O parecer numa linha** (`prontuario.parecer`): "Pede ação agora" havendo um ponto crítico, "Pede acompanhamento"
   havendo outro, "Em dia" sem nenhum; a frase conta os pontos e diz o principal. Não é opinião: é a contagem do que as
   telas donas apontam.
3. **O painel, o visual na frente** (`prontuario.painel`), três blocos numa superfície só: a **Performance do mês** em
   medidores (a meta, o PR e a disponibilidade: o número e a cor da Visão do responsável, a barra contra a marca de cada
   um — a meta em 100% numa escala até 120%, o PR previsto, os 99% da régua da disponibilidade —, o que explica o número
   e o mês anterior) e a geração de cada dia do mês em barras contra a meta do dia; as **OS** (as abertas repartidas
   pelo estado no Fracttal, num tom só, porque estado de OS não é semáforo; as tarefas atrasadas, as pausadas, as que
   vencem até amanhã, a semana passada do plano e, havendo, a parada de agora); e as **Pendências** (a contagem, as 4
   mais graves e o resto abrindo na tela; embaixo, o que está em dia).
4. **A faixa do resto**: última ronda, sujidade e vegetação (1 a 5, em casas), chamados, segurança, COS e insights.
5. **Um cartão FECHADO por assunto**, com o estado dele numa linha (`prontuario.resumos`): Performance, OS e
   manutenção, Rondas e zeladoria, Segurança do trabalho, COS, Chamados e garantias, Insights do Nexus, Demandas e
   conversa. Cada número do painel, cada casa da faixa e cada pendência abrem o cartão deles e fecham os outros
   (`static/comando/prontuario.js`; o endereço com `#pu-<cartão>` também). Dentro, a informação direta: a Performance
   abre pelo gráfico do mês e o mês a mês (com a barra do atingimento), sem repetir o painel; as OS, pelo que pede ação
   (`prontuario.os_grupos`: as atrasadas com os dias e o tipo, as pausadas com o motivo, e as OS de cada estado pelo
   número), cada OS abrindo o card dela por cima.
6. **A linha do tempo** (30 dias, por dia, com filtro por fonte) **e a composição** (a ficha do cadastro e a estrutura
   do Nexus), fechadas, na largura inteira.
Um nível de superfície; a cor só carrega estado (o ponto, não a faixa lateral).

**De onde vem cada dado (nada se inventa; a fonte que não abre fica de fora com o aviso).** A conta é pura
(`nexus/comando/prontuario.py`, o cabeçalho dele lista parte a parte); quem lê é
`torres/comando/prontuario_dados.py`: a linha da lista do Comando (`_usinas_montadas`) e a Central da usina
(`torres.campo._central_da_usina`, a conta da Usinas 360°) dão o estado, a linha da Visão do responsável e as pessoas;
o que vem do banco para TODAS as usinas (o mês a mês da meta e da disponibilidade, as normalizações do COS, a zeladoria
semanal, as tarefas das OS abertas, os chamados, os nomes dos equipamentos e a estrutura) é lido uma vez e guardado na
cópia de 5 min do Campo (`visao._ler`, a chave `comando_prontuarios`): a 1ª abertura fria leva uns 6 s, as seguintes
0,1 s. As OS de cada estado vêm da tela dona: `campo/manutencao.tarefas_por_usina` passou a dar as listas
(`os_verificacao`, `os_em_execucao`, `os_nao_iniciadas`) além das contagens, pela MESMA regra (a contagem é o tamanho
da lista). Nada aqui lê o Fracttal.

**As ações.** Criar OS abre um menu com cinco formas (Levi, 12/11/2026: "na parte de criar OS, vai ter as opções que é
possível hoje. Então, OS avulsa, OS de performance, OS de engenharia, inspeção de chamados, solicitação de OS. E aí o
ticket pode tirar o botão de ticket"): a lista é `prontuario_dados.CRIAR_OS`. **Quem usa o prontuário é quem DEMANDA**
(o alinhamento dele no mesmo dia: "a OS Performance seria mais o caminho para OS Creator Web Solicitação. Aí tem uma
abinha de performance, uma abinha de engenharia. Tendo em conta que quem está mexendo aí vai ser uma pessoa que vai
demandar coisas [...] Essa OS de performance tem string, tracker e outras coisas, quem cria [é] a performance"): por
isso a **OS de Performance** e a **OS de Engenharia** abrem a aba delas na Nova solicitação
(`/os/solicitacao/performance` e `/os/solicitacao/engenharia`, em que a OS vai direto para a equipe do setor), e não a
tela em que o próprio setor cria as OS dele (`/os/performance`, com os planos de string, tracker e inversor;
`/os/engenharia`). A **OS avulsa** (o "Criar OS do zero" de lá, `/os/tradicional`) e a **Solicitação de OS** ao PCM
(`/os/solicitacao`) abrem com a usina já escolhida (`?ativo=<o código da usina no cadastro>`, que é o do ativo dela no
Fracttal; `tradicional_web.sugestao`); as abas da Performance e da Engenharia e a **Inspeção de chamados**
(`/os/chamados/inspecao`, que pede o ativo pelo id do Fracttal) abrem sem a usina. O botão "Criar ticket" da 1ª versão
(os planos da Performance direto) saiu no mesmo dia. Relatório = o PDF do
cliente da Usinas 360° (`campo/relatorio_usina.py`), também pelo endereço do Comando
(`/t/comando/usinas/<id>/relatorio.pdf`, que chama a rota de lá), para quem tem o Comando e não a Visão do responsável.
A janela pergunta o mês e **o que entra** (Levi: "eu quero o relatório de forma profissional, que dê para editar os
campos que eu quero que apareça"): cada tema com os campos dele, todos marcados (a regra está em
`nexus/torres/campo/CLAUDE.md`, "Os campos do relatório").

**O que muda entre as duas portas** (`comando/_prontuario.html`, o `pu_na_aba`): na aba da Usinas 360° a página usa a
janela daquela tela (`cr-modal`, o `data-cr-painel`): o dia a dia da meta, do PR e da disponibilidade, os extintores e a
**decisão da PT** abrem por cima; no Comando, a PT esperando o De acordo leva à aba. O título é `h2` na aba (a tela já
tem o `h1`). O card da OS (`oscreator/card_os_abrir.html`) vem de quem inclui, uma vez só.

**O que a pessoa sem a tela não vê** (`prontuario_dados._pode`, a régua do portão, `setor_telas.pode`): sem tela do OS
Creator, sem o Criar OS; sem tela do Comando, sem a conversa; o "abrir" do pé de cada cartão só aparece
para quem abre a tela dele. As demandas são só as que a pessoa pode ver.

**O que o Nexus ainda NÃO tem, e por isso não está na página** (pedidos do mockup da Ana Barros, 12/11/2026): o
responsável de performance por usina; a saúde das strings e o PR por inversor (a geração por inversor está no banco, mas
nenhuma tela a lê; as correntes das strings só existem na moldura da plataforma); as OS concluídas em geral (o banco só
tem as abertas; as concluídas estão no Histórico de OS do OS Creator); as características da UFV (pediria um livro
novo no cadastro). Entram quando a fonte existir, cada uma pela tela dona.

**Prova.** `tests/test_comando_prontuario.py` (a conta do parecer, do painel e do cartão das OS; as OS de cada estado na
tela dona; as formas do Criar OS apontando para rotas que o OS Creator tem; o ligador geral ligando o código pela regra da casa; a página nas
duas portas, o relatório pelo Comando e o que a pessoa sem a tela não vê), `tests/test_campo_central_usina_0411.py` (a aba) e `tests/test_comando_usinas.py`. E a renderização com o
banco de produção, só leitura, pelo cliente de teste (12/11/2026: a Mandaguaçu com 55% da meta, PR 54,6% contra 73,2%,
disponibilidade 58,2%, 41 OS abertas = 8 não iniciadas + 2 em execução + 31 em verificação, 40 tarefas atrasadas em 9
OS; a Crateús 1 com 18% da meta; os mesmos números da Visão do responsável; tema escuro e claro; a página fechada com
1.463 px a 1.440 de largura).

## As demandas entre setores (12/11/2026)

Levi: "algo parecido com criação de chamados [...] os setores consigam conversar entre si sem ter que especificamente
criar um OS". Desenho aprovado depois de uma rodada de perguntas, com a prévia (`docs/mockups/demandas-entre-setores` no
repositório da plataforma): `docs/superpowers/specs/2026-11-12-demandas-entre-setores-design.md` e o plano em
`docs/superpowers/plans/2026-11-12-demandas-entre-setores.md`. O modelo é o dos times de serviço (Jira Service
Management, ServiceNow): catálogo de temas por setor com o prazo por tema, "respondida" separada de "concluída", a
conclusão sozinha e o vencido que sobe para o setor; no O&M, a demanda fica presa ao que o campo enxerga (a usina e a OS).

**As regras (todas do Levi):**
- A pessoa e o setor de quem recebe são obrigatórios; um setor só por demanda ("Esquece essa parte de indicar mais de um
  setor"). O setor vê o que todo mundo dele recebe (a aba "Do meu setor", com o filtro por pessoa e por tema).
- Cada setor monta os seus temas, cada um com o prazo em dias úteis (1 a 30; sem sábado, domingo e feriado nacional):
  Comando → Temas do setor (`de_todos`). O prazo da demanda é o do tema na hora em que foi aberta.
  Na tela, o campo do tema se chama `tema` e vai com `autocomplete="off"` (12/11/2026, Levi, com o print: "o campo que
  aparece quando vou digitar está mal formatado, conserte!"): chamado `nome`, o Edge abria por cima da tabela a lista do
  que já foi digitado em qualquer campo `nome` do Nexus (o nome da pessoa, "Chamados", "Administrador", "Responsável
  UFV", dos Acessos). A rota ainda aceita `nome` (a página que ficou aberta de antes). **Campo de texto novo num
  formulário do Nexus: nome próprio do que ele guarda e `autocomplete="off"` quando o histórico do navegador não ajuda.**
- A OS, as usinas e os anexos são opcionais. A OS tem de existir e ser de uma das usinas escolhidas (o retrato do
  Fracttal no banco, `nexus_os · fato_tarefa_os`: as abertas e em verificação), e abre o card do OS Creator ao clicar
  (`NexusOsCard.abrirFolio`). Os anexos seguem a regra das Sugestões (5 arquivos, 5 MB cada, 15 MB juntos, o conteúdo
  conferido pelo começo do arquivo), no disco do servidor em `demandas/<id>/`.
- Situações: Nova → Em análise → (Aguardando quem pediu ↔) → Finalizada (quem recebeu respondeu) → Concluída (o ok de quem
  pediu) ou Devolvida (com justificativa obrigatória; o prazo recomeça do dia da devolução). "Pedir informação" PARA o
  prazo até quem pediu responder: os dias úteis parados somam ao prazo. Finalizada sem o ok nem a devolução em 3 dias
  úteis vira "Concluída sozinha" (só na leitura, nada se grava).
- Quem faz cada passo: quem recebeu (em análise, pedir informação, responder); quem pediu (informar, concluir, devolver).
  O colega do setor vê e não responde no lugar (`demandas.PASSOS`).
- A lista: o nome de quem pediu, o setor dele, o título e as 6 primeiras palavras da descrição ("estilo Next, só que
  limpo"); o tema aparece uma vez só (Levi: "O tema está se repetindo no título e nas linhas de baixo"). O selo da
  esquerda é o prazo; o da direita, a situação.
- O sininho (bandeja, ao lado do botão do OS Creator): para quem recebeu, a nova, o prazo apertando (faltam 2 dias,
  falta 1, vence hoje), a vencida e a devolvida; para o setor de quem recebeu, a vencida ("Quem recebeu + todo o setor");
  para quem pediu, a respondida e o pedido de informação. A nova vence o prazo de 2 dias na ordem (a prévia mostrava
  "Nova demanda"). Só da cópia do livro (`demandas.copia`, 1 minuto, relida por trás): nenhuma página espera o banco.

**Os dados** (`nexus_demandas`, registrado no catálogo antes da 1ª gravação; o Nexus é a fonte, só acrescenta):
`dim_tema` (1 versão de 1 tema; vale a última por `tema_id`), `fato_demanda`, `fato_demanda_usina` e
`fato_evento_demanda`. Em claro só ids, códigos (`*_hmac`), setores, prazo, OS e datas; o nome do tema, o título, a
descrição, os textos dos passos, os nomes e os anexos só cifrados (o Cofre, amarrado à linha). O `novo_id` do formulário
torna o 2º envio (o duplo clique, o F5) inofensivo. O setor da pessoa vem das decisões de Base → Acessos → Pessoas e
setores (`setor_telas.setor_da_pessoa`), e não do `acesso()`, que só diz o setor com o portão por setor ligado.

**Os arquivos:** `demandas_regras.py` (o prazo, a situação e os avisos, sem Flask nem banco), `demandas.py` (a gravação,
a leitura decifrada, as três abas e os filtros), `../torres/comando/demandas_tela.py` (as rotas, debaixo de
`/t/comando/caixa-de-entrada/demandas/...` para herdar a Caixa, que é de todos), `templates/comando/_demandas.html` (o
bloco no alto da Caixa e a Nova demanda), `temas_setor.html`, `static/comando/demandas.js` (aba, filtro e demanda aberta
sem recarregar; a pessoa e o tema pelo setor; as OS das usinas marcadas) e o CSS `dm-` no `comando.css`. O sininho é o
`_sino_demandas` da casca.

**A revisão independente de 12/11/2026 (antes de subir) deixou estas regras:** a pausada não dá "Vence hoje" nem entra no "Vencem até amanhã" (a vez é de quem pediu); a Nova demanda confere o tamanho ANTES de ler o corpo (`max_content_length`, como as Sugestões); a gravação que entrou no banco e respondeu com erro vale, com os anexos (só a que não entrou os leva embora); a leitura é conferida (`abas_conferidas`) e a que começou antes de uma gravação não fica na cópia (`_GERACAO`); só vale o passo de quem tem o papel dele (`passos_validos`: uma linha posta no banco por fora não muda a situação); a cifra da demanda amarra também o setor de quem recebe; o `?d=` só entra se tiver a forma do id; o tema novo leva `novo_id`. **A Caixa não lê o Fracttal ao abrir:** a lista de quem recebe (os nomes vêm do pessoal do Fracttal) chega ao abrir a Nova demanda (`GET .../demandas/pessoas`); a tela que lê o Fracttal sai da pré-carga e gasta a cota da empresa.

**Fora, por agora:** a demanda para mais de um setor; o e-mail; o painel de tempo de resposta por setor (os passos já
guardam o dia de cada um para medir).

Prova: `tests/test_comando_demandas.py` (o prazo, a pausa, a conclusão sozinha e os avisos com datas inventadas; o livro no
catálogo; o texto só cifrado; o duplo envio; a OS da usina; o papel e a vez; o anexo; as três abas; a Caixa para quem
recebe, quem pediu, o colega e quem não tem nada a ver; a Nova demanda pela tela; os passos pela tela; os Temas do setor;
o sininho).

## O dossiê da usina para a IA (12/11/2026)

Levi, 12/11/2026: "Monte o dossiê da usina inteira, para a gente usar com a IA futuramente, do jeito que uma IA possa ver
facilmente"; e "A ideia é a pessoa ir no prontuário da usina e perguntar [...] por que a usina está com baixa
performance, enfim, quais são os problemas dela, e já aparece. Então, use tudo que tem no prontuário da usina, tá? Todas
as informações de todos os setores".

**O que é.** O prontuário inteiro escrito em texto (Markdown), que o Nexus IA vai mandar junto da pergunta de quem
estiver no prontuário. `nexus/comando/dossie.py` (`montar(ctx, agora, com_pessoas=False)`) recebe o MESMO contexto da
página (`prontuario_dados.contexto`) e devolve `{"texto", "secoes", "caracteres", "palavras", "tokens_estimados"}`.
**Nada é lido de novo nem calculado ali**: o número do dossiê é o da tela dona. A chamada à API ainda não existe (a tela
Base › Nexus IA segue reservada); o que existe é o texto pronto.

**Onde se vê.** `/t/comando/usinas/<id>/dossie` (a página: o texto, o tamanho, Copiar e Baixar) e
`/t/comando/usinas/<id>/dossie.md` (o texto puro, `text/markdown`, sem cache; `?baixar=1` baixa). Abre para quem abre o
prontuário (é o mesmo dado); o atalho "Dossiê para a IA" no prontuário aparece só para o administrador enquanto a
pergunta não existe na tela.

**As regras do texto** (o que faz uma IA ler bem e errar menos; mexeu no formato, sobe a `VERSAO`):
- 14 seções, sempre na mesma ordem e com o mesmo título (`SECOES`): Identificação, Parecer e o que pede atenção,
  Performance (com o mês a mês e a geração de cada dia), COS, OS e manutenção, Equipamentos, Chamados de garantia, Rondas
  e zeladoria, Segurança, Insights, Demandas e conversa, Linha do tempo, Composição, O que ficou de fora. Cada uma abre
  com a `Fonte:` (a tela do Nexus de onde o dado saiu), para a resposta citar de onde tirou;
- **o que falta está escrito**: "sem dado" (a fonte não tem o valor: não é zero), "sem leitura" (a fonte não respondeu;
  as OS sem leitura dizem "Não quer dizer zero", o COS sem leitura "Não quer dizer normal") e a última seção com as
  fontes que não abriram. Nenhuma seção fica em branco. É a regra "sem dado não se inventa" levada à IA: ela não pode ler
  a falta como "está tudo bem";
- a gravidade em palavras (crítico, atenção, em dia), a mesma cor da tela dona;
- nada do desenho da tela (largura de barra, coordenada de gráfico, classe de cor, endereço): o teste barra;
- **as pessoas pelo papel, sem o nome** (o padrão): o texto é feito para sair do Nexus, e nome de pessoa é dado pessoal.
  "Responsável O&M: definido" ou "não definido" fica, porque "ninguém cuida" é informação. O texto livre que alguém
  escreveu (a descrição da demanda, a última mensagem da conversa) vai como foi escrito. O cliente e o código da usina
  ficam: não são dado pessoal, e o código já traz o cliente. `com_pessoas=True` existe para quando o Levi decidir que os
  nomes podem ir; hoje nenhuma rota o usa;
- os tokens são ESTIMATIVA (4 caracteres por token): a conta exata só a API dá.

**Seção nova no prontuário entra no dossiê no mesmo trabalho** (senão a IA responde sem ela): a função da seção, a linha
em `SECOES` e o teste. Prova: `tests/test_comando_dossie.py`.

## Contestações e Prévia: visão do contrato (no Comando desde 12/11/2026)

Vieram da torre Contratos e clientes, que saiu do menu (Levi, 12/11/2026: "contestações, você vai jogar para o comando,
prévia visão do contrato, você vai jogar no comando"). São as duas últimas telas da torre: `/t/comando/contestacoes` e
`/t/comando/visao-do-contrato` (esta, de todos). As views e os templates moram aqui
(`nexus/torres/comando/contestacoes_tela.py`, importado no fim do `__init__` como as demandas); **as regras, a chave, o
que cada setor vê e o desenho da Prévia estão em `nexus/contratos/CLAUDE.md`: leia lá antes de mexer.** Os endereços
antigos (`/t/contratos/...`) redirecionam e a marca do setor na tela antiga vale na nova (`setor_telas.RENOMEADAS`).

## O visual
**A ordem da Caixa de entrada (Levi, 12/11/2026):** o título só (sem a pergunta da tela e sem o "todas as torres · conta das HH:MM", "inútil"); os números dos insights no alto, como KPI, antes das demandas ("não faz sentido ter criar demanda de setores e depois seus insights"), cada número leva à sua lista; o **Sem dono vem recolhido**, só com o contador ("senão a rolagem é infinita"), e abre pelo número do alto, pelo clique ou pelo endereço de um insight dele (`insights.js`); o botão "Temas do meu setor" ao lado da Nova demanda ("eu não achei um de cadastro os temas").

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
