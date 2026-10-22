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

O Raio-X e o que cada número quer dizer: `nexus/casca/CLAUDE.md`, seção "Nexus lento".

## Regras de prova de toda correção

1. Achar ONDE o pedido espera antes de mexer (o Raio-X, a pilha, uma medida). Nada de corrigir por palpite.
2. Um teste que reproduz: falha no código de antes e passa no novo. O Fracttal, o banco e o disco são de mentira; o
   `conftest.py` recusa a rede e as fontes pagas.
3. Mutação: desfazer cada parte da correção derruba o teste dela.
4. Medir antes e depois e dizer o número (num processo novo, com o mesmo dado). Mudou a leitura de um dado: comparar
   valor a valor (confiabilidade de dado é a prioridade 1).
5. Suíte inteira (`python -m pytest -q`) antes do push. No OS Creator: `python ferramentas/sincronizar_oscreator.py
   --aplicar` só quando o "vai para o oem" lista só os seus arquivos, e a suíte do oem na pasta dele (`cd
   C:\GridcoBuild\oem` e `python -m pytest -rN tests`).
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
| 22/10 | Raio-X das 14:02: 6 de 8 threads em POST /t/pcm/motivos/app (a justificativa do App), de 3,5 a 6 min cada, e o Nexus parado para todos | com o servidor no swap, cada gravação no livro dos motivos levava minutos; o servidor do App desiste em 20 s e manda de novo, e cada reenvio esperava numa thread a vez de gravar (7 justificativas, 46 envios das 13:51 às 14:08); os reenvios voltavam "sem mudança", e o App não escreveu a nota nem a etiqueta no Fracttal de nenhuma | a justificativa entra numa fila e um gravador por trás grava as que esperam juntas (uma leitura e uma gravação do livro); o pedido espera até 15 s e só dois esperam; o reenvio pega a resposta guardada ou volta "gravou" (`repetida`); a leitura que falha na gravação é 503, não 400 (que o App descarta) | este |

## A fila

1. **Push só de documentação também reinicia o servidor** (`deploy/atualizar.sh`): pular o restart quando o commit novo
   só muda `.md`, para um documento não esfriar as telas de todo mundo. Mexe no deploy do servidor: prova com cuidado.
2. **A memória do servidor (o notebook, 4 núcleos, 7,1 GB):** os programas pedem mais do que a máquina tem (22/10
   08:55: o worker da plataforma 5,1 GB com o swap, o web dela 1,9, o Nexus 1,8 e o Gêmeo 0,6: 9,5 GB; 3,6 GB no swap
   e o disco ocupado até 61% do tempo). No ar: as strings da 2C 35% menores e a memória solta devolvida no worker
   (`f3a8200`); o relatório por dentro do worker (`62a00c2`) e do web (`0a83c8a`) no Raio-X; os caches da API PV com
   prazo e teto também no web (`a3e3cc1`). **Próximo passo:** no worker, as variáveis somam 1,3 dos 4,2 GB (08:46 de
   22/10); o resto está em tarefas rodando (variáveis locais de thread) ou preso no alocador, e o relatório deve medir
   também o que cada thread segura. O Nexus em si (1,8 GB, 1,1 no swap) ainda não tem o "por dentro". O dia de
   trackers compacto no worker (~400 a 570 MB) espera o OK do Levi. Para a T.I. (o que mais resolve, grátis): limitar
   a memória da plataforma e proteger a do Nexus no systemd (MemoryHigh e MemoryMax nela, MemoryLow no Nexus) e religar
   o worker sozinho (Restart=always); depois, mais memória (16 GB) ou a plataforma numa máquina à parte.
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

## Onde está cada peça

- Raio-X `nexus/casca/raio_x.py` e `nexus/templates/raio_x.html`; pedidos presos `nexus/casca/presos.py`; teto do OS
  Creator `nexus/casca/teto_os.py`. Regras em `nexus/casca/CLAUDE.md`.
- Contas do Campo: `nexus/campo/visao.py` (`_ler`: a cópia de 5 min sai na hora e se refaz por trás; `_fria`: uma conta
  fria por chave; `VAGAS_BANCO`; `manter_quente`; `carregar`: a pré-leitura).
- Pré-carga `nexus/auth/pre_carga.py`; portão e acessos `nexus/auth/__init__.py` e `nexus/auth/acessos.py`.
- OS Creator: `nexus/torres/oscreator/os_creator/` (`api.py` fala com o Fracttal; `os_web/rotas.py` e o `_memo`;
  `historico_store.py`; `rotas_acomp.py`). Regras no `nexus/torres/oscreator/README.md`.
- Medir uma tela fria: num processo novo, `create_app` com o `.env` do Nexus vivo e uma senha de administrador
  descartável, contando o `requests.Session.request` e recusando o Fracttal (só leitura no banco).
