# Desempenho do Nexus: o roteiro do chat de desempenho

Levi, 20/10/2026: "O que você acha de um chat só para essas otimizações de performance da plataforma? Acho que com a
construção constante do nexus sempre vai ter algo para revisar e corrigir!". Este arquivo é o ponto de partida desse
chat: como investigar, as regras de prova, o que já foi corrigido (para não refazer) e a fila. Correção feita: a linha
da fila sai e entra uma linha em "O que já foi feito", no mesmo commit.

## Como começa cada pedido

- **O print do Raio-X** (`/t/base/raio-x`, só administrador) NA HORA da lentidão, a tela ou a ação e a hora. Sem o
  print, pedir: em 20/10 ele mostrou que dois casos que pareciam "conta fria" eram outra coisa.
- **Houve deploy nos 5 min antes?** `curl https://app.gridco.com.br/saude` dá o commit no ar e `git log origin/main` a
  hora. Todo push na main reinicia o servidor em 1 a 5 min, e a pré-carga só passa 5 min depois: nesse intervalo, a 1ª
  abertura de cada tela é fria (até ~15 s nas pesadas).

## Como ler o Raio-X

| O que aparece | Quer dizer | Onde olhar primeiro |
|---|---|---|
| Pedido parado numa linha `with <trava>` | trava no caminho de todo pedido | quem mais pega a trava e o que faz dentro dela (disco? rede?). Caso de 20/10: o portão esperava a trava presa no `fsync` de cada login |
| "esperando a rede" no Fracttal (`api.*`) | o Fracttal lento, ou a tela pedindo demais | dá para servir a cópia guardada e reler por trás? o mesmo pedido repetido por pessoa ou por visita? |
| "esperando a rede" no banco (`livros.*`, `banco_campo`) | o banco (a API `db_performace` mora na MESMA máquina) | contas frias juntas, renovações por trás demais, `VAGAS_BANCO` |
| "trabalhando" e o Processador do Nexus perto de 100% | o processo segura o GIL: um laço Python | a tarefa "trabalhando" (pré-carga, PDF, renovar) e o laço dela |
| "trabalhando" com o Nexus baixo e, no Raio-X, esperando o disco alto, swap trocando ou memória parada | a MÁQUINA (disco, memória), não o código | a seção "Quem ocupa a memória da máquina" do Raio-X diz de quem é a memória; sendo a máquina mesmo, os números vão ao Levi para a T.I. Caso de 20/10: o PDF das 13:45 ficou 1 min "trabalhando" no desenho do logo (milissegundos) com a máquina no swap |
| Lento só nos ~5 min depois de um push | conta fria pós-deploy | a fila, item "Conta fria pós-deploy" |
| Seção **Uso do OS Creator** (últimos 7 dias; só no servidor, que é quem grava) | o que as pessoas abrem, a que hora e quanto isso pede ao Fracttal: o ANTES e o DEPOIS de cada mudança do canto central do OS Creator (desde 31/10/2026) | veja abaixo, "Como ler o Uso do OS Creator" |

O Raio-X e o que cada número quer dizer: `nexus/casca/CLAUDE.md`, seção "Nexus lento".

### Como ler o Uso do OS Creator (a seção do Raio-X, desde 31/10/2026)

Os números vêm de duas medidas que o servidor faz na memória (`nexus/casca/CLAUDE.md`, "Uso das telas do OS Creator por
hora"): quantas vezes cada tela foi aberta, quanto demorou e quanto pediu ao Fracttal, e quantos pedidos o Nexus fez ao
Fracttal por minuto contra a cota de 200 para a empresa toda. **De hora em hora (:05) as horas fechadas vão para o disco do
servidor, e ao banco elas vão em uma gravação por dia às 03:45** (gravar o livro do mês inteiro custa ~7 s de processador, e o
Nexus é um processo só). O banco guarda 1 hora por linha, num livro por mês (`nexus_oscreator_uso_AAAA_MM`, três abas: o uso por
tela, o detalhe do Fracttal por origem e método e o total da hora). A seção lê de ontem para trás do banco (cópia de 10 min),
põe por cima o pendente do disco (o que ainda não foi às 03:45) e a memória (a hora aberta): o que você vê de hoje é do
disco e da memória do servidor, e amanhã, depois das 03:45, está no banco.

| O que aparece | Quer dizer | O que fazer |
|---|---|---|
| **Por dia:** "maior pico por minuto" com "perto da cota" (amarelo, a partir de 160) ou "na cota" (vermelho, 200 ou mais) e recusados (406/429) acima de zero | naquele minuto o Nexus sozinho encostou na cota do Fracttal, e o App de Campo e os robôs ainda dividem os mesmos 200: o Fracttal passou a recusar | olhar a hora do pico em "Por hora do dia" e as telas dela em "As 15 telas": quem faz a rajada é a tela com mais pedidos ao Fracttal por clique (pedidos ao Fracttal ÷ cliques) |
| **Por hora do dia:** os cliques e o pico por minuto de cada hora (soma dos 7 dias, hora de Brasília) | a forma do dia: as horas em que o OS Creator pesa e as em que a cota aperta | trocar um horário de carga ou de varredura para fora da hora de pico; o :05 da gravação do próprio uso já está fora dos laços de hora em hora do Nexus |
| **Por dia e por hora do dia:** "Esperaram a vez" acima de zero | o porteiro do Nexus (`casca/fracttal_conta.py`, desde a etapa 5) segurou pedidos ao Fracttal: o Nexus chegou a 150 no último minuto (sobram 50 dos 200 para o App de Campo e os robôs) ou o fundo a 90. O clique espera no máximo 2 s e segue; o fundo espera a vez, sem limite | ver a hora em "Por hora do dia" e quem esperou no banco (`fato_fracttal_hora`, por origem: fundo é só o laço que se declara, os da lista do `nexus/casca/CLAUDE.md`; a `fundo:<thread>` fora dela, um pool ou a releitura por trás de uma tela, foi tratada como clique). Espera de fundo é o porteiro trabalhando (a leitura só demora mais); espera de clique em hora de trabalho é lentidão que a pessoa sente: tirar laço ou leitura daquela hora |
| **As 15 telas:** muitos "Automáticos" e poucos "Cliques" | a tela pede sozinha (a sessão a cada 5 min, o Histórico a cada 10, as Solicitações a cada 15), e cada aba aberta soma | é custo fixo de quem deixa a aba aberta, não de quem usa: não conta como uso, e o que reduz é pedir menos vezes ou só com a aba à frente |
| **As 15 telas:** mediana baixa e p95 muito mais alto | a tela é rápida quando o Fracttal responde e lenta quando ele demora ou recusa | cruzar com "Ocupado (503)" (o teto de 16 threads recusou) e com os recusados do dia |
| **As 15 telas:** "Pedidos ao Fracttal" alto para poucos cliques | uma abertura da tela faz muitos pedidos (o catálogo de ativos pedia ~110 pelo RPC) | é o candidato à cópia guardada e à releitura por trás (as etapas seguintes do canto central). O catálogo de ativos já é (31/10/2026): o servidor o lê às 02:15 (`fundo:nexus-ativos-leitor`, ~270 pedidos a 1 por segundo) e os novos de 30 em 30 min; um RPC de ~110 pedidos numa tela depois disso é a noite que não entrou (README do OS Creator, "O leitor do servidor"). O histórico de OS também se lê sozinho desde 31/10/2026, em faixas (`fundo:nexus-os-leitor:<faixa>`: novas, sete_dias, abertas, finalizadas, noite, pendentes; na escala do AC, ~99 OS por dia: ~92 a 110 pedidos por hora de dia útil, a noite às 03:21 com ~190 a 210, no domingo ~750 a 830; o pico de memória da noite de domingo ~150 MB, o da de todo dia ~40 MB, com cada página cortada no que a lista lê), e as telas leem dele desde a 3.3 (o Histórico e as visões, o Garantias, a marcação verde dos Ativos, o Investigar, o nº → id e a 1ª pintura do card: a Visão COS de 26 pedidos na 1ª visita para 1, a conferência de cada pessoa; README do OS Creator, "As telas leem da lista central de OS"). Um Histórico que volta a pedir a lista inteira é a pessoa que o Raio-X conta como divergência ou "sem resposta pela página" ("Conferências das telas"; a conferência é uma por pessoa e período, até a marca d'água da lista), a lista que não cobre o período, ou o campo que o REST não trouxe. A faixa que o Raio-X diz "recusada" (a trava de encolhimento) ou "não devolveu pela criação" não mexeu na lista: as telas seguem como estavam; a recusa que se repete igual na leitura seguinte passa ("aceita na 2ª leitura", o apagamento de verdade) |
| **Antes e depois:** o mesmo dia da semana, comparando o total de pedidos ao Fracttal e o maior pico | se a mudança aliviou a cota de verdade, em número e não em sensação | anotar o dia do deploy; a etapa 0 dá o antes |
| "Sem medição ainda" | o servidor ainda não guardou a 1ª hora (ela chega ao disco no :05 da hora seguinte ao deploy, e ao banco às 03:45), o banco não respondeu ou é o PC (que não mede) | a frase diz qual; com o banco fora, a seção mostra só o que o servidor guarda, o disco e a memória |

Limites: a mediana e o p95 de vários dias são aproximados (cada hora guarda só os dela; a seção junta pelo quantil dos
quantis, pesado pelos pedidos atendidos). O corte por setor vem da memória do servidor e só mostra os 7 dias (o disco dele
guarda 30); nunca está no banco. **O que ainda não foi às 03:45 está só no disco do servidor** (`casca/uso_os_pendente.json`,
até 3 dias): sobrevive ao reinício, mas não a perder o disco, e se o banco ficar fora por mais de 3 dias as horas mais
velhas saem do pendente (aviso no log). **O que um reinício perde** é só a hora aberta do contador do Fracttal (ele não
guarda parcial em disco; o do uso das telas guarda, de 5 em 5 min): **a hora em que o servidor reiniciou** (todo deploy)
tem os pedidos ao Fracttal só de depois do reinício, o total e o pico por minuto dessa hora podem estar abaixo do real, e o
"antes e depois" deve comparar dias inteiros, não a hora do deploy. O total do Fracttal e o pico por minuto são da aba do
total da hora (1 linha por hora), e o pico do total não é a soma dos picos de cada tela.

## Regras de prova de toda correção

1. Achar ONDE o pedido espera antes de mexer (o Raio-X, a pilha, uma medida). Nada de corrigir por palpite.
2. Um teste que reproduz: falha no código de antes e passa no novo. O Fracttal, o banco e o disco são de mentira; o
   `conftest.py` recusa a rede e as fontes pagas.
3. Mutação: desfazer cada parte da correção derruba o teste dela.
4. Medir antes e depois e dizer o número (num processo novo, com o mesmo dado). Mudou a leitura de um dado: comparar
   valor a valor (confiabilidade de dado é a prioridade 1).
5. Suíte inteira (`python -m pytest -q`) antes do push. No OS Creator, a prova é a suíte do Nexus: desde 31/10/2026 ele
   é a casa do OS Creator Web, não há mais sincronia com o oem e a pasta do oem não se toca.
6. Push é deploy: conferir o `/saude` com o commit. Juntar as correções do dia num push quando der (cada push esfria o
   servidor).
7. O `.md` da área tocada é atualizado no mesmo commit, e este arquivo também.

## Convivência com as outras frentes

- Este chat mexe no código das outras frentes só para deixar mais rápido, SEM mudar o que a tela faz ou mostra. Se a
  correção muda comportamento (o que aparece, quando atualiza), avisar o Levi antes.
- Mudança visual: mostrar ao Levi (print) antes de subir.
- Commit só dos próprios arquivos, num worktree do `origin/main` atualizado, com rebase antes do push.
- A cota do Fracttal é de 200 pedidos por minuto para a EMPRESA (o App de Campo vive dela): cópia guardada e releitura
  por trás, nunca pedido a mais.
- **APIs avançadas do Fracttal** (add-on pago; avaliadas em 21/10/2026, Levi: "podem ajudar a gente a melhorar o
  desempenho do OS Creator?"): quase nada. Criar OS, atualizar tarefa, tarefa não planejada e tarefa pendente o OS
  Creator já faz com 1 pedido cada, pelo RPC do site com o login da pessoa (pela API oficial quem grava é a chave da
  integração, e o Fracttal perde quem fez). Só a consulta de anexos da OS (`GET /api/work_orders_attachments/<folio>/`)
  ajuda: até 100 anexos num pedido, já com a URL assinada do S3 (24 h), no lugar de 1 pedido por tarefa, 1 por
  subtarefa com anexo e 1 `s3_object_get` por arquivo (a lista de anexos do card e o PDF da OS). A documentação não
  diz se ela traz os anexos das subtarefas (o checklist do App): conferir num teste do add-on antes de comprar. A
  versão grátis (`work_orders_tasks_files`) traz só nota e link. O add-on não aumenta os 200/min (página "Limites de
  Requests": a empresa inteira, todas as integrações; o 429 pede 1 min de espera; mais que isso é pedido ao
  representante). Alternativa grátis, não testada: o RPC já recebe uma lista JSON-RPC (sempre com 1 item); se
  aceitar vários, os links das fotos de uma OS iriam numa chamada só.

## O que já foi feito (não refazer; o porquê está no commit)

| Data | Sintoma | Causa | Correção | Commit |
|---|---|---|---|---|
| 12/10 | telas lentas no 1º clique | as cópias do servidor vazias | pré-carga das telas de quem tem setor | `8188864` |
| 13/10 | travamentos sem rastro | nada registrava o pedido preso | registro dos pedidos presos | `905347d` |
| 14/10 | `/saude` até 60 s | o OS Creator esperando o Fracttal segurava as threads | Raio-X; teto de 16 threads para o OS Creator, servidor com 32 | `cbed995`, `948af6d` |
| 14/10 | "clico no OS Creator e fica carregando" | a tela inicial esperava o selo da Performance no Fracttal | a tela sai sem esperar; contagens 6 h na memória | `bb91eb0` |
| 14/10 | PDF dos extintores pesado | cada foto inteira | cópia de 600 px de cada foto, feita uma vez | `d8f8d85` |
| 19/10 | Visão do responsável fria de 26 a 46 s | 23 a 27 listagens e abas página por página | pré-leitura numa listagem só, páginas em paralelo | `43b5a93` |
| 19/10 | o filtro da Visão relia o banco | ocorrências e sites relidos a cada filtro | o filtro não espera o banco | `695b487` |
| 19/10 | Nexus travado das 14:47 às 15:06 | gravações zeravam TODO o Campo; contas frias em dobro | só o que mudou sai; uma conta fria por chave; teto de 6 leituras do banco | `c77da9b` |
| 19/10 | Extintores pesado | todas as fotos de uma vez | página leve, foto só no clique | `bfab36f` |
| 19/10 | Histórico do OS Creator, 2.000 OS por pessoa, 43 s | a lista repetida por pessoa e a cada 10 min | lista dividida, soma só as novas, linhas montadas uma vez; catálogos 10 min; catálogo de ativos na memória | `e5e3e02` |
| 19/10 | Gerar a semana, Quadro e Registro mestre lentos | a conta refeita a cada visita | serviço e índices reaproveitados, linhas montadas uma vez por versão | `e52cde5` |
| 19/10 | Acompanhamento relido por pessoa; anexos pelo id errado | cópia por pessoa; o id do modelo da tarefa | quadro dividido por quem vê o mesmo; id da tarefa da OS | `6bab274` |
| 20/10 | Visão do responsável "um parto" (08:56) | o portão esperava a trava presa no `fsync` de cada login | leitura sem trava, trava por arquivo | `1889303` |
| 20/10 | tela de um chamado em 39 s (09:56) | relia a lista inteira na frente de quem abriu | cópia vencida e releitura por trás, sem reler as fechadas | `c70d778` |
| 20/10 | `GET /os/` em 18 s (10:08) com o Nexus a 13% | a máquina engasgada, sem número para provar | o Raio-X mostra memória, swap e espera do disco | `65c25e7` |
| 20/10 | PDF da OS ~2 min (09:56), em `gerar` | o reportlab decodificava cada foto em RGB só para dar nome a ela (2,25 MB por foto até o fim: +1 GB com 200) | o JPEG do `reduzir` entra como veio; 200 fotos no PC: `gerar` de 3,2 a 4,0 s para 0,3 s, rota de +1.068 MB para +128 MB, o mesmo PDF | `23c3c73` |
| 20/10 | o 2º PDF da mesma OS reduzia todas as fotos de novo | o `reduzir` (~90 ms de CPU por foto no PC) a cada PDF | a cópia de 1000 px guardada pelo hash da foto original (o caminho no S3 pode voltar com outra foto); 200 fotos no PC: o 2º PDF de 5,1 a 5,5 s para 0,8 s | `8ec1999` |
| 20/10 | volta da tela de um chamado ao Acompanhamento "travada" | quadro de 3 min, e cada gravação da tela (ticket, finalizar, responsável) apagava o quadro: a volta relia a lista e os tickets do Fracttal | quadro de 30 min (Levi: "só pesquisar caso a singrid clique em atualizar"), a gravação ajusta a cópia, o teto da memória a tira por último | `d59aef1` (chat de chamados) |
| 20/10 | 3 testes do oem falhando desde 14/10; com a sessão do Fracttal caída, a tela inicial do OS Creator não voltava ao login | `bb91eb0` tirou o selo de dentro da tela (ela não espera o Fracttal) e o 401 do `/os/api/selo` era ignorado | o script do selo leva ao login com o 401 (como o `acomp.js`), conferido no navegador; os 3 testes do oem cobram o selo pelo `/os/api/selo` (no disco do oem, sem commit lá: decisão do Levi) | `39f806d` |
| 20/10 | Raio-X das 14:17: 0,2 GB livres de 7,1 GB, 3,2 GB no swap trocando 4,5 MB/s, disco 60% do tempo, com o Nexus em 690 MB | a máquina sem memória, e a página não dizia de quem eram os outros ~6 GB | a seção "Quem ocupa a memória da máquina" (somada por programa, pelo /proc de cada processo) | `57d5217` |
| 20/10 | travada das 16:12 (GET /os/ ~4 min em linhas de microssegundos) e o próprio Raio-X 4 min 18 s preso em `_ler_proc` | a máquina trocando com o disco (o Nexus com 1,5 GB no swap); ler a linha de comando de um processo no swap espera o disco | a lista da memória numa thread à parte com prazo de 2 s, uma leitura presa por vez, o nome de cada processo lido uma vez | `7d9de73` |
| 20/10 | o worker da plataforma de 3,7 para 5,0 GB (com o swap) em 26 min (16:12 a 16:38), e o que crescia no servidor ninguém via (a medição de dentro só dava no PC, sem os backfills de lá) | — | o worker grava a cada 10 min, em /dev/shm, quanto cada variável ocupa (por amostra, últimas 3 h; PerformancePainel), e o Raio-X mostra "Dentro do worker da plataforma", agora × 1 h antes | `2137e2d`; `62a00c2` na plataforma |
| 21/10 | Raio-X das 14:36: "pedido preso 24 vezes em 24 h", o último um GET /os/historico de 45 s esperando o Fracttal (45 s é o tempo-limite) | a busca da lista (`api.list_minhas_os`, Histórico e quadro do Acompanhamento) engolia o erro de cada página e lote: sem a 1ª página, a lista VAZIA ficava guardada sem aviso; sem uma do meio, sumiam até 200 OS; e a vazia de "Todos" fazia cada pessoa buscar a sua inteira até o reinício | a busca em que o Fracttal não entregou algum pedido falha inteira (`_lista_pela_metade`): nada é guardado, a tela avisa e fica com a lista anterior e a hora dela; 3 pessoas depois de um estouro: 30 pedidos → 11 | `dadae16` |
| 21/10 | Raio-X das 14:55: o web da plataforma (`app.py`) de 0,8 GB (14:36) para 3,1 GB + 0,7 GB no swap; a máquina com 0,2 GB livres, 2,9 GB no swap e o disco 71% do tempo; às 15:00 um POST do Registro mestre 3,5 min preso | o relatório por dentro e a devolução de memória só rodavam no worker: o que o web guarda ninguém via | o web grava o mesmo relatório (`gridco_plataforma_web.json`), devolve a memória livre a cada 10 min e usa no máximo 2 arenas de malloc (sem descartar cache: trackers); o Raio-X mostra "Dentro do web da plataforma" | `1853a39`; `0a83c8a` na plataforma |
| 22/10 | relatório do web às 08:51: o dia de trackers da API PV 545 MB (19 dias de usina) e o dia de strings da API PV 493 MB (3 dias), parados desde antes das 07:59, com a máquina em 0,5 GB livres e 3,6 GB no swap | a poda do dia de trackers só rodava no worker (a aba Perdas, que lia esse cache no web, saiu em 12/10), e o dia de strings só tinha o teto de 3 dias (o código contava ~6 MB por dia; usina grande dá ~165 MB) | o dia de strings sai com 20 min sem releitura e tem teto de 30 mil registros; a poda do dia de trackers (2 h parado, 1,5 milhão de pontos) vale também no web; as duas a cada 10 min no web e na hora de guardar | `a3e3cc1` na plataforma |
| 22/10 | Raio-X das 08:57: o próprio GET /t/base/raio-x 1 min 15 s preso em `_threads` | para cada thread, o `extract_stack` lia no disco o código de todas as linhas da pilha (o rótulo só usa a de dentro), com a máquina no swap | pilha sem o código (`presos.pilha`, também na ronda dos presos) e a lista de threads com o prazo de 2 s das outras seções | `e5a7259` |
| 22/10 | Raio-X das 14:02: 6 de 8 threads em POST /t/pcm/motivos/app (a justificativa do App), de 3,5 a 6 min cada, e o Nexus parado para todos | com o servidor no swap, cada gravação no livro dos motivos levava minutos; o servidor do App desiste em 20 s e manda de novo, e cada reenvio esperava numa thread a vez de gravar (7 justificativas, 46 envios das 13:51 às 14:08); os reenvios voltavam "sem mudança", e o App não escreveu a nota nem a etiqueta no Fracttal de nenhuma | a justificativa entra numa fila e um gravador por trás grava as que esperam juntas (uma leitura e uma gravação do livro); o pedido espera até 15 s e só dois esperam; o reenvio pega a resposta guardada ou volta "gravou" (`repetida`); a leitura que falha na gravação é 503, não 400 (que o App descarta) | `15537dc` |
| 23/10 | Raio-X das 10:44: um Criar OS da Performance 3 min 51 s em `get_assets` e o Histórico 1 min 52 s esperando o mesmo download | o catálogo de ~22 mil ativos passou das 24 h e o 1º a precisar dele o baixou dentro do pedido (~110 pedidos ao Fracttal) | vencido, o de ontem volta na hora e o novo vem por trás, uma vez só, com a sessão de quem pediu; só a aprovação espera o novo; o botão "Atualizar ativos" (Ativos) baixa na hora para todos | `4c027f3` |
| 23/10 | Raio-X das 08:41: a 1ª abertura do dia do Acompanhamento de chamados 42 s | a cópia passava de 2 h (`VELHA_MAX`) e a tela esperava a leitura nova do Fracttal | abre com a de ontem (a hora à vista) para quem vê o mesmo total no Fracttal, relê por trás e troca sozinha quando a nova chega | `4c027f3` |
| 29/10 | COS > Normalizações "carrega sempre que clico": cada filtro recarregava a página inteira (1,1 MB com ~1.000 no mês) e, passado o minuto da cópia, o clique esperava a Ronda COS (a 3 s, o filtro levava 3,2 s, todos juntos na trava) | o filtro no servidor e a releitura dentro do clique | o filtro na própria página (`static/cos/normalizacoes.js`, as contas iguais às do servidor) e a cópia vencida na hora, com a releitura por trás: 3,2 s → 0,15 s no clique que caía no minuto, e o filtro sem ir ao servidor | este |
| 29/10 | Raio-X das 10:53: o Nexus com 707 MB na memória e 1.481 MB no swap (930 MB às 09:59), 7,0 GB livres na máquina, trocando 10,6 MB/s, a API do banco em 502 às 09:51 e Normalizações do COS 1 min 19 s; em cinco leituras de dois dias o Nexus sempre em ~700 MB | com memória sobrando o Linux só troca assim se o grupo do processo tiver teto, e ninguém de fora via o serviço | o cartão da memória diz o teto do Nexus pelo cgroup do próprio processo (o limite, o swap permitido, quantas vezes apertou, onde) | este |
| 30/10 | Raio-X das 10:48: o Nexus com 671 MB na memória e 2.847 MB no swap, 6,8 GB livres, "o Linux apertou o Nexus 132.576 vezes" (51.280 às 08:55), o "clonar OS" do OS Creator 13 min 43 s preso; às 15:13, com a 1ª correção no ar (42e506c, só o set-property), o teto seguia lá (18.802 apertos desde o restart das 14:38) | o `nexus.service` com MemoryHigh=700M e MemoryMax=1024M, posto no servidor (não no `deploy/nexus.service`), e ninguém via o que o deploy fazia com ele | o `deploy/atualizar.sh` (root, a cada 2 min) tira o teto abaixo de 4 GB pelo drop-in `zz-` com daemon-reload, pelo set-property e pelo `max` direto no cgroup, e grava o que viu em `.git/nexus-teto`, que o Raio-X mostra; teto acima do piso fica (é da T.I.) | este |
| 24/10 | Raio-X das 12:05 (máquina nova, 16 GB): o Nexus com 682 MB e 1.917 MB no swap, sem saber de quê | o Raio-X media por dentro só a plataforma | "Dentro do Nexus": as variáveis e as extensões do app, por amostra, a cada 10 min (`casca/memoria_nexus.py`) | `4c027f3` |
| 25/10 | Base → Integração Fracttal: cada busca e cada filtro recarregavam a página (319 KB com 180 pessoas) e a 1ª abertura fria levava ~2,4 s | o filtro ia ao servidor, o campo Setor de cada linha levava a lista toda e o Fracttal ligado às fichas era refeito quando a cópia vencia | a tela virou a aba Pessoas e setores de Acessos; filtro na página, o campo Setor enche ao tocar, a ligação guardada 2 min e renovada por trás; no celular, o filtro dos Cadastros não fica mais com 140 px de altura | este |
| 31/10 | os três "Atualizar ativos" do OS Creator (Ativos, o ↻ do Criar OS, o "Recarregar o catálogo" da Fila) seguravam quem clicou por minutos, e o catálogo só se renovava com a sessão da 1ª pessoa do dia (etapa 2 do canto central) | o catálogo inteiro (~110 pedidos ao Fracttal) baixado pelo RPC dentro do pedido, pela sessão de quem clicou | o servidor lê os ativos sozinho às 02:15 (REST, ~270 pedidos a 1 por segundo, conferido contra o catálogo) e os novos às :08 e :38 (1 ou 2 pedidos); o botão pede só os novos por trás e volta na hora com "ativos de HH:MM", e a lista seguinte espera essa leitura (até 6 s); sem o leitor (o PC), como antes | este |

## A fila

1. **Push só de documentação também reinicia o servidor** (`deploy/atualizar.sh`): pular o restart quando o commit novo
   só muda `.md`, para um documento não esfriar as telas de todo mundo. Mexe no deploy do servidor: prova com cuidado.
2. **A memória do servidor:** em 23/10/2026 o servidor trocou para uma máquina de 16 GB e 8 núcleos (era 7,1 GB e 4).
   Raio-X das 12:05 de 24/10: 6,9 GB livres, disco ocupado 0,7% do tempo; o worker da plataforma com 4,5 GB (o dia de
   trackers da API PV, 1,5 GB em 217 dias de usina, dentro do teto de 1,5 milhão de pontos) e o Nexus com 1,9 GB ainda
   no swap da máquina velha (some no próximo reinício ou com `swapoff -a && swapon -a`). **Próximo passo:** ler o
   "Dentro do Nexus" do Raio-X (24/10) e cortar o que for cópia esquecida; o roteiro da T.I. (tetos da plataforma,
   proteção do Nexus) não foi aplicado.
3. **Clima e risco:** 21 s de processador na 1ª carga (o LZW do GeoTIFF do INPE em Python puro, 183 pedidos; volta a cada
   6 h, a cada deploy e a cada 15 min com o INPE atrasado). Proposta: o decodificador do Pillow (em C) por tile e uma
   cópia em disco.
4. **Conta fria pós-deploy** (~15 s na 1ª abertura de uma tela nos ~5 min depois de cada push). Opções: agrupar os
   deploys (no máximo um reinício a cada 30 min, por exemplo) ou uma cópia em disco das abas lidas (servir a última com
   a hora dela e renovar por trás). É parâmetro: perguntar ao Levi antes.
5. **O deploy não pode cortar uma gravação no meio** (21/10/2026, pedido pelo chat Nexus com o OK do Levi): o push das
   09:57 (`dc60042`) reiniciou o servidor às ~10:03 no meio de um "Criar OS" do OS Creator (Performance › Trackers): a
   OS nasceu no Fracttal às 10:03:19, mas o ticket da aba Trackers, gravado depois no mesmo pedido
   (`api.create_performance_os` → `nascer_ticket`), não chegou, e a tela recebeu a resposta vazia do proxy. Proposta: o
   `deploy/atualizar.sh`, antes do `systemctl restart`, espera os pedidos em andamento terminarem (até ~60 s), pelo
   registro do `casca/presos.py` (os `em_curso`). Mexe no deploy do servidor: prova com cuidado. A tela já avisa a
   gravação sem resposta (`carga.js`, chat Nexus).
6. **A justificativa do App com o banco lento, do lado do App** (22/10/2026; é do chat do App de Campo): o aparelho
   para depois de 8 envios ("Parei de tentar sozinho"), e a justificativa fica nele até o técnico tocar em Sincronizar,
   mesmo quando o Nexus já a tem (na fila ou gravada). O reenvio no MESMO dia volta "gravou" e o App escreve a nota e a
   etiqueta; no dia seguinte, o Nexus grava como justificativa nova (conta de novo nas Vezes), porque a hora que vale é
   a da chegada, não a do técnico. Proposta: o App manda a hora em que o técnico justificou (a `ts` do evento, que ele
   já usa na linha da nota) e o Nexus decide o "mesmo dia" por ela. Das 7 de 22/10, 2 da OS 13473 voltaram "sem
   mudança" e ficaram sem a nota e a etiqueta; as outras 5 estão nos aparelhos.
7. **PCM → Almoxarifado, aba Avariadas** (30/10/2026): o `_paradas` (`nexus/pcm/almoxarifado.py`) lê o Saldo de TODOS os meses do
   histórico a cada recálculo de 5 min; cresce ~30 ciclos por mês. Corrigir quando aparecer no Raio-X: ler do ciclo mais novo para
   trás e parar quando todas as chaves já tiverem quebrado a corrida.

## Onde está cada peça

- Raio-X `nexus/casca/raio_x.py` e `nexus/templates/raio_x.html`; pedidos presos `nexus/casca/presos.py`; teto do OS
  Creator `nexus/casca/teto_os.py`. Regras em `nexus/casca/CLAUDE.md`.
- O uso do OS Creator e os pedidos ao Fracttal por hora: o contador `nexus/casca/fracttal_conta.py` (e, no mesmo gancho, o
  porteiro: o Nexus até 150 pedidos por minuto, o fundo até 90, o clique nunca recusado), a medida das telas e o
  laço (o disco no :05, o banco às 03:45) `nexus/casca/uso_os.py`, o fato e o livro `nexus/dados/fato_uso_os.py` (regras em
  `nexus/dados/CLAUDE.md`), e a seção do Raio-X em `raio_x.py` (`montar_uso_os`).
- Contas do Campo: `nexus/campo/visao.py` (`_ler`: a cópia de 5 min sai na hora e se refaz por trás; `_fria`: uma conta
  fria por chave; `VAGAS_BANCO`; `manter_quente`; `carregar`: a pré-leitura).
- Pré-carga `nexus/auth/pre_carga.py`; portão e acessos `nexus/auth/__init__.py` e `nexus/auth/acessos.py`.
- OS Creator: `nexus/torres/oscreator/os_creator/` (`api.py` fala com o Fracttal; `os_web/rotas.py` e o `_memo`;
  `historico_store.py`; `rotas_acomp.py`; o catálogo de ativos central `ativos_central.py` e o leitor do servidor
  `ativos_leitor.py`, que lê os ativos de madrugada; a lista central de OS `os_central.py`, o leitor em faixas `os_leitor.py` e
  as telas que leem dela `os_web/lista_central.py`, com o estado das duas no Raio-X, seção "Uso do OS Creator"). Regras no `nexus/torres/oscreator/README.md`. Os minutos de
  hora em hora que já têm dono: `nexus/casca/minutos_ocupados.py` (o laço novo pede o próximo livre).
- Medir uma tela fria: num processo novo, `create_app` com o `.env` do Nexus vivo e uma senha de administrador
  descartável, contando o `requests.Session.request` e recusando o Fracttal (só leitura no banco).
- A skill `desempenho` (`.claude/skills/desempenho/SKILL.md`, desde 30/10/2026): o gatilho e o atalho `/desempenho`
  dos chats de lentidão. Só leva a este arquivo, pela versão do `origin/main`; a regra mora aqui, não nela. No teste de
  30/10, dois agentes sem a skill já chegaram a este arquivo pelo `CLAUDE.md`: ela não é a única guarda.
