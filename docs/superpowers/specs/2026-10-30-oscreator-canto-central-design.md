# O OS Creator com um canto central de dados (desenho, 30/10/2026)

## 1. Para que serve

Levi, 30/10/2026, depois de uma conversa com um dev de backend sobre o OS Creator: "percebo que temos um padrão, para
abrir uma solicitação precisamos de ativos, para criar OS é preciso carregar os ativos, para abrir o histórico acabamos
vendo os ativos, o mesmo acontece muitas vezes com o histórico de OSs. Minha proposta: termos um canto centralizado para
atualização de ativos e históricos de OSs que irão se atualizar em horários que não são de pico, o histórico de OS pega
só os mais recentes, atualizando os mais antigos 1 vez por dia pela noite, o histórico de ativo faz o mesmo." E: "A
ideia é não ter um carregamento novo por atividade e sim um ecossistema onde as coisas se aproveitam e não precisamos
ficar fazendo novas requisições sempre!". Em etapas. Ele também marcou, como motivos: sair do clone do oem, quebrar o
`api.py` e ficar mais rápido pedindo menos ao Fracttal.

O que muda para quem usa: as telas abrem com o que já está no Nexus, sem esperar o Fracttal; o que alguém cria ou muda
pelo OS Creator aparece na hora para todos; o reinício do Nexus (cada push) não custa nada a ninguém.

## 2. O que existe hoje (lido no código em 30/10/2026, `origin/main` 0394f89)

- **Não existe registro de uso.** Nada guarda qual tela do OS Creator foi aberta, quando nem por quem: o waitress não
  registra acessos, o Raio-X (`nexus/casca/raio_x.py`) só mostra o momento, os pedidos presos (`casca/presos.py`) só
  acima de 30 s, o journal só erro. Não há como dizer hoje "o que as pessoas mais fazem".
- **Um processo só:** waitress com 32 threads (`servir.py`), o OS Creator com no máximo 16 (`casca/teto_os.py`, que já
  vê todo pedido de `/os/*` e `/t/os/*`). Uma cópia em memória serve a todas as telas. **Cada push na `main` reinicia o
  serviço** (~10 por dia útil, de 13 a 30/10) e apaga tudo o que está só na memória. A memória do servidor está
  apertada (`DESEMPENHO.md`; em 30/10 ainda ia para o swap).
- **Ativos:** carga completa pelo RPC (`inventories.items_list`, com o login da pessoa), ~110 pedidos, 200 por página,
  6 de uma vez (`api.py` ~336), gravada em `assets_cache.json`, vale 24 h; vencida, devolve a de ontem e baixa por trás
  com a sessão de quem pediu. ~22 a 26 mil ativos. Três caminhos com cópia ou índice próprio (`load_assets_cached`, que
  copia a lista inteira a cada chamada; `rotas_solic._indice_ativos`, com o seu renovador; `_code_loc`, montado uma vez
  por processo e nunca refeito), e `_asset_by_code` percorre uma cópia a cada código. Três botões ("Atualizar ativos" em
  Ativos, Criar OS e Solicitação) baixam os ~110 pedidos na frente de quem clicou.
- **Histórico de OS:** `historico_store` (19/10/2026, README "O Histórico sem repetir o Fracttal"): a lista "Todos" é
  uma só para quem tem a mesma visão no Fracttal (conferido com 1 pedido na sessão de cada pessoa; a visão restrita
  segue com a dela); "criadas por mim" e "atribuídas a mim", uma por pessoa. Vencida (3 min), lê só as novas; a lista
  inteira a cada 10 min (~26 pedidos para "Todos 30 dias"). A chave inclui o período, então a virada do dia relê tudo na
  frente da pessoa. Nenhuma gravação do OS Creator atualiza a lista (o card alterado força `atualizar=1`). A OS do
  Fracttal **não tem data de alteração** (conferido no REST em 19/10: só criação, programada, evento, início, fim e
  revisão): status, responsável e datas das OS antigas só mudam numa releitura.
- **Repetições:** pessoas (`personnel_list`) lidas por 7 caminhos; etiquetas com 4 caches; tipos e classificações com
  3; o nº da OS → id (`os_por_folio`, 1 a 5 pedidos) refeito sem guardar no card, Clonar, COS, Inspeção, PDF e Garantias;
  a marcação verde dos Ativos relê a janela de 30 dias que a lista "Todos" já tem; Garantias (365 dias) e Histórico com
  duas listas sobre as mesmas OS; a Performance lê os planos de cada inversor (1 pedido por inversor) a cada usina
  escolhida; o PDF e a nota releem o detalhe que a mesma ação acabou de ler.
- **Nada roda fora do pico no OS Creator:** toda releitura nasce de uma visita, com o JWT de quem abriu. O RPC não
  funciona sem a sessão de uma pessoa (`os_web/sessao.py`).
- **O que o Nexus já tem fora do OS Creator** (reaproveitar, não duplicar):
  - o leitor REST do Nexus com a credencial da empresa (`nexus/campo/fracttal.py`: só GET, até 4 por segundo; o REST
    entrega no máximo 100 por página e não filtra por data, mas ordena);
  - as tarefas das OS abertas no banco, de hora em hora: `nexus_os · fato_tarefa_os` (`nexus/campo/tarefas_os.py`,
    status 1 e 2, ~85 páginas, leitura incompleta não grava, uma máquina por vez);
  - a foto dos ativos no banco, `nexus_ativos_fracttal · foto_ativos` (carga única de 11/10/2026, 22.357 linhas, feita
    do `assets_cache.json`), de onde sai a `dim_equipamento` do Nexus inteiro, parada desde então;
  - o desenho das OS finalizadas do PCM, `nexus_os_finalizadas_AAAA_MM · fato_tarefa_finalizada`
    (`docs/superpowers/specs/2026-10-27-pcm-tarefa-e-executado-design.md`, lido no mesmo `tarefas_os.py`; não
    construído, em revisão noutro ramo);
  - o molde das OS de falha (`nexus/engenharia/os_falhas.py`): as vivas relidas inteiras, as concluídas só desde a
    última leitura.

## 3. Metas, não metas e o que seria fracasso

**Metas**
1. Nenhuma tela do OS Creator espera o Fracttal para mostrar ativos ou o histórico de OS: lê do canto central.
2. Os pedidos de leitura ao Fracttal por dia caem, medidos (etapa 0 dá o antes), e as rajadas somem: o pico por minuto
   fica longe da cota de 200/min da empresa.
3. O reinício não custa pedido nenhum ao Fracttal nem espera a ninguém.
4. Uma regra só por assunto: um catálogo de ativos, uma lista de OS, um cache de pessoas, etiquetas, tipos e planos, e
   um caminho só para criar OS.
5. O Nexus é a única casa do OS Creator web.

**Não metas**
- Mudar o que as telas mostram ou o jeito de usar. É a estrutura por baixo.
- Gravar no Fracttal de outro jeito: criar, clonar, aprovar, cancelar e editar seguem com o login de quem usa (a autoria
  no Fracttal fica certa).
- Juntar agora os depósitos de OS dos outros setores (o quadro da equipe, as ETMs, a Aprovação, as OS de falha). O canto
  nasce pronto para eles e cada um muda depois, com a sua prova.
- Um usuário de serviço no Fracttal para o RPC.

**Seria fracasso, mesmo funcionando**
- Lista pela metade mostrada como inteira ("número pela metade não vai para a tela").
- Pessoa de visão restrita no Fracttal vendo OS que o Fracttal não mostra a ela.
- Texto de OS, nome ou observação em claro no banco (a API tem leitura aberta).
- O canto central estourar a cota da empresa e derrubar o App de Campo.
- OS criada pelo OS Creator sumindo do histórico até a próxima volta.
- Mais uma cópia das OS ao lado das que já existem.
- O Nexus indo mais para o swap por causa do canto central.

## 4. Restrições

- Repositório público: nada de nome, e-mail, segredo nem dado de cliente em arquivo versionado. pt-BR, sem emoji, cor
  só por token.
- Dado novo no banco segue o `nexus/dados/CLAUDE.md`: grão e tipo escritos, registrado no `catalogo.py` antes de
  gravar, IDs (`usina_id`, `equipamento_id`, `pessoa_id`), nada pessoal em claro (regra 8), conferir antes e depois de
  gravar, uma máquina grava por vez (regra 11), a carga só lê o que as duas máquinas leem igual (regra 12).
- O PC do Levi roda outro Nexus (a 5070, que ele usa). O canto central roda nas duas máquinas, cada uma com a sua
  memória e a sua cópia em disco; o que vai ao banco segue a regra de uma máquina por vez. O PC não faz a leitura da
  madrugada: sobe pela cópia em disco dele e pelo banco (ativos pela `foto_ativos`; status das abertas pelo
  `fato_tarefa_os`) e lê só as faixas leves enquanto está ligado. Sem cópia nenhuma, enche por trás, e até lá as telas
  usam a leitura ao vivo pela sessão da pessoa (o mesmo caminho que a visão restrita usa, que continua existindo).
- Cota do Fracttal: 200 pedidos por minuto para a empresa toda, dividida com o App de Campo e os robôs. Em segundo
  plano, 1 pedido por segundo, como as outras leituras do Nexus; o 406/429 espera e tenta de novo; leitura incompleta
  não troca o que existe.
- Os horários de hora em hora que já existem: tarefas :10–:20, normalizações :22, sync do App :25, zeladoria :32,
  carga :40, chamados :50. O canto central não cai em cima deles.
- Push na `main` = produção em ~2 min. Cada etapa sobe com o OK do Levi.

## 5. O desenho, etapa por etapa

Cada etapa é uma entrega própria, com testes, a tela conferida (desktop e 375 px) e o README do OS Creator em dia. Cada
uma tira do `api.py` o pedaço que ela refaz, num módulo próprio: no fim o `api.py` vira um arquivo pequeno ou some.

### Etapa 0 — Medir o uso (antes de tudo, pequena)

- No `casca/teto_os.py` (já vê todo `/os/*` e `/t/os/*`): cada pedido soma, na memória, numa linha por **hora × rota
  normalizada**: pedidos, pessoas distintas (contadas na memória; a pessoa nunca é guardada), duração mediana e p95,
  erros, e os pedidos que aquele pedido fez ao Fracttal.
- **O setor não vai ao banco.** Há setor com uma ou duas pessoas: hora × rota × setor com "1 pessoa" diria o que ela fez
  e quando, num banco de leitura aberta que não apaga. O corte por setor fica só no Raio-X, no disco do servidor, para
  o administrador, guardado 30 dias.
- Rota normalizada: números viram `<n>` (`/os/os/16995` → `/os/os/<n>`); a query sai.
- Clique e automático separados: o que a tela pede sozinha (Histórico a cada 10 min, Solicitação a cada 15, o
  `acompanhamento/estado`, a sessão a cada 5) entra marcado como automático.
- Um contador de pedidos ao Fracttal no ponto por onde todos passam (`_rpc_call`, `_react_insert_post`, o POST do
  `create_os_rpc`, o `_req` do REST e o `nexus/campo/fracttal.py`), atribuído à rota do pedido em curso ou ao trabalho de
  fundo que pediu; por hora: total, recusas (406/429) e o **máximo num minuto** (a vigia da cota).
- Grava de hora em hora no banco, numa família por mês (`nexus_oscreator_uso_AAAA_MM`, abas `fato_uso_hora` e
  `fato_fracttal_hora`), registrada no catálogo antes. Grava só o servidor. Sem nome, e-mail nem setor: rota, hora e
  contagens.
- Uma seção no Raio-X: as rotas mais pedidas nos últimos 7 dias, por hora do dia, com cliques e automáticos separados,
  e os pedidos ao Fracttal por hora. É ela que dá o antes e o depois de cada etapa e mostra os horários de pico de
  verdade.

### Etapa 1 — O Nexus como casa única (pequena)

- O OS Creator web deixa de ser um clone do oem. O app de mesa (`C:\GridcoBuild\oem`) fica **congelado** como está:
  segue funcionando com a cópia dele, sem novidades.
- Saem o `ferramentas/sincronizar_oscreator.py` e o `sincronia.json`, e o README deixa de mandar "ficar idêntico".
- O caminho web deixa de depender do PyQt (os testes hoje pulam sem ele: `pytest.importorskip("PyQt6")`); o que for só
  do app de mesa sai do caminho web.

### Etapa 2 — Os ativos centrais

- **Leitor:** o REST `items` pela credencial da empresa (`nexus/campo/fracttal.py`), 1 pedido por segundo, só no
  servidor. **Completo de madrugada** (entre 01:00 e 05:00 de Brasília, longe dos minutos ocupados). **Durante o dia,
  só os novos**: ordenado do mais novo para o mais velho, para quando uma página inteira já é conhecida (1 ou 2 pedidos),
  a cada 30 min.
- **Antes de construir, uma sondagem:** os campos que o OS Creator usa do ativo (id, código, descrição, tipo de item,
  grupo de tarefas, caminho/local, de onde sai cliente e usina) vêm iguais no REST e no RPC? O que só o RPC tiver decide
  o desvio, levado ao Levi antes de seguir.
- **Destinos:**
  1. A `foto_ativos` do banco renovada (troca só quando o sha das linhas muda; leitura incompleta ou que encolhe mais
     que um piso não grava). Ela já alimenta a `dim_equipamento`: o Nexus inteiro passa a ter os ativos em dia, não só
     o OS Creator. O código que saiu do Fracttal **fica** na foto (os fatos antigos ligam por ele, como a carga única de
     11/10 já fez com os 719 códigos de junho), marcado como fora do Fracttal desde a data em que sumiu; as telas do OS
     Creator mostram só os que estão no Fracttal.
  2. Uma cópia em memória, uma só para todas as telas, com os índices por código, por id e por cliente e usina,
     montados uma vez por versão. No boot vem do banco (sem Fracttal). Troca inteira, de uma vez, quando chega versão
     nova.
- **Quem passa a ler dela:** `load_assets_cached`, `_indice_ativos`, `_code_loc`, `_asset_by_code`, `ativos_do_cliente`
  e o que mais ler o catálogo. O `assets_cache.json` deixa de ser fonte.
- **Os botões "Atualizar ativos"** pedem ao canto central a leitura dos novos agora (poucos pedidos, em segundo plano) e
  a tela diz "ativos de HH:MM". O completo fica para a madrugada.
- **Se a sondagem mostrar campo que só o RPC dá:** o completo segue pelo RPC, mas central (por trás, com a sessão da 1ª
  pessoa do dia, como hoje, uma vez por dia para todos), e o REST só acrescenta os novos.

### Etapa 3 — O histórico de OS central

- **Uma lista só, de todas as OS, para todos.** As visões ("Todos", "criadas por mim", "atribuídas a mim", o período)
  viram filtros sobre ela. A janela guardada cobre o que as telas leem hoje (o Garantias lê 365 dias); o tamanho exato
  sai da medida de memória.
- **Leitor:** o mesmo do `fato_tarefa_os` (`nexus/campo/tarefas_os.py`), estendido. Não nasce outro leitor de OS. Em
  faixas (os números são o ponto de partida; o construtor ajusta pela etapa 0):
  - **as novas:** criadas desde a mais nova conhecida, a cada 3 min no horário de trabalho e a cada 15 fora (1 ou 2
    pedidos);
  - **os últimos 7 dias, relidos inteiros, a cada 10 min:** status, responsável e datas das recentes em dia (o que hoje
    a lista inteira de 10 min faz);
  - **as abertas, de hora em hora:** a leitura que o `fato_tarefa_os` já faz (status 1 e 2), aproveitada também pela
    lista;
  - **as finalizadas:** a leitura incremental desenhada pelo PCM (status 3, pela data de fim, desde a mais nova menos a
    margem). Se ao começar a etapa 3 ela ainda não existir no `origin/main`, esta frente constrói a **leitura** no
    `tarefas_os.py`, no desenho do PCM, e **não publica o fato** `fato_tarefa_finalizada`: o fato, o ensaio dele e a
    carga desde 01/01/2026 seguem com o PCM, que passa a ler da mesma leitura;
  - **de madrugada:** a reconciliação da janela (as antigas mudam sem data de alteração).
- **O que o OS Creator faz entra na hora:** criar, clonar, aprovar a SS, cancelar, finalizar, trocar responsável,
  editar. A ação já relê a OS com a sessão da pessoa; essa leitura entra na lista central. O card deixa de forçar
  `atualizar=1`.
- **Visão restrita:** fica a regra de 19/10. A 1ª visita de cada pessoa confere com 1 pedido na sessão dela; quem vê o
  mesmo total usa a lista central; quem vê outro segue com a dela, lida ao vivo.
- **Quem passa a ler dela:** Histórico (todas as visões), Garantias, a marcação verde dos Ativos, Investigar ativo, o nº
  → id (índice permanente, com a leitura ao vivo só para o que não estiver nela) e a 1ª pintura do card (subtarefas e
  anexos seguem ao vivo).
- **Destinos:**
  1. Memória: só os campos que as telas usam.
  2. Uma cópia em disco na pasta de dados do servidor, só para o reinício voltar sem reler (é cache do Fracttal, refeito
     a qualquer hora, nunca fonte; tem texto da OS e nome, por isso não vai ao banco nem ao git).
  3. Banco: o `fato_tarefa_os` (como já é) e o fato das finalizadas: só IDs, datas e status, nunca texto (regra 8).
- **Lista pela metade:** uma volta que falha no meio não troca a lista; a tela segue dizendo "lista das HH:MM".

### Etapa 4 — Os catálogos pequenos num lugar só

- Pessoas, etiquetas, tipos e classificações, falhas, status e os planos (eventos e detalhes de cada modelo): um cache
  por assunto, um prazo por assunto, aquecido no boot por trás e renovado fora do pico. Pessoas pelo REST que o
  cadastro já usa (`nexus/cadastro/fracttal_pessoal.py`); os outros pelo REST se a sondagem achar, senão pela 1ª sessão
  do dia, uma vez para todos.
- Os planos deixam de ser lidos por inversor a cada usina escolhida na Performance: o plano de cada modelo e grupo fica
  guardado e muda de madrugada.
- Somem as cópias soltas (os 7 caminhos de pessoas, os 4 de etiquetas, os 3 de tipos).
- Cada catálogo guarda uma cópia em disco na pasta de dados, para o reinício não custar pedido nenhum (meta 3).

### Etapa 5 — Um caminho só para criar OS, e um porteiro do Fracttal

- **Um caminho de criação** (tarefas → kanban → OS numerada com a soma do tempo das tarefas → etiquetas → anexos) usado
  por Criar OS do zero, Clonar, PCM (com e sem plano), a Fila do PCM, a Performance, o COS e a Engenharia. Hoje são
  vários, cada um com a sua regra: o tempo da OS de 30/10/2026 (10 min fixos em quatro caminhos) foi esse erro.
- **Um porteiro do Fracttal** para o Nexus inteiro: o RPC do OS Creator e o REST do Nexus passam por uma conta só por
  minuto, com a vez de quem está clicando antes do trabalho de fundo, e folga para o App de Campo.
- O que sobrar do `api.py` vai para os módulos de cada assunto.

## 6. O que fica para o construtor

- Os nomes dos módulos, o formato dos registros em memória, os minutos exatos de cada faixa e da madrugada, o tamanho
  da janela da lista, o piso de encolhimento dos ativos, a forma de marcar o pedido automático.
- Medir a memória antes e depois de cada etapa (o cartão de memória do Raio-X) e enxugar o registro até caber.
- A ordem dos commits dentro de cada etapa.

## 7. Como provar

- **Testes que contam cada ida ao Fracttal**, no molde do `tests/test_oscreator_historico_compartilhado_19_10.py`:
  - a tela que lê do canto central não pede nada;
  - o reinício não pede nada;
  - a ação do OS Creator aparece na lista sem releitura;
  - a visão restrita segue com a dela;
  - a leitura que falha no meio não troca a lista.
- **Antes de gravar no banco**, o ensaio (`ferramentas/carregar_dados.py --ensaio` ou o ensaio próprio do leitor):
  linhas, chave repetida, % ligado. Só grava depois de o Levi ver os números.
- **Pela etapa 0:** os pedidos ao Fracttal por dia e o pico por minuto antes e depois de cada etapa, e o tempo das telas
  mais usadas.
- A tela conferida no navegador (desktop e 375 px, escuro e claro) e a suíte inteira passando.

## 8. Ordem e tamanho

| Etapa | Tamanho | Depende de |
|---|---|---|
| 0 Medir | pequena | nada; começa já e coleta enquanto as outras andam |
| 1 Casa única | pequena | nada |
| 2 Ativos centrais | média | 1 (o código deixa de ser igual ao oem) |
| 3 Histórico central | grande | 1; conversa com o fato das finalizadas do PCM |
| 4 Catálogos pequenos | média | 1 |
| 5 Um caminho e o porteiro | grande, aos poucos | 2, 3 e 4 |

## 9. Riscos e o que ainda não se sabe

- A paridade de campos entre o REST e o RPC (ativos, OS, etiquetas, tipos): decidida pela sondagem de cada etapa,
  antes de construir.
- Memória do servidor: o canto central troca várias cópias (uma lista por pessoa, três índices de ativos) por uma só,
  mas precisa ser medido.
- O fato das finalizadas está em revisão noutro ramo (`pcm-dados-ronda`): a etapa 3 começa conferindo o estado dele no
  `origin/main`.
- Sem data de alteração no Fracttal, a mudança numa OS antiga feita fora do OS Creator aparece na volta das abertas (de
  hora em hora) ou na da madrugada.

## 10. Escolhas deste desenho (decididas pelo Claude, a conferir pelo Levi)

1. O app de mesa (oem) fica congelado: segue funcionando, sem novidades e sem a sincronia.
2. Só o OS Creator agora; o canto nasce como peça do Nexus (banco e catálogo) para os outros setores mudarem depois.
3. A leitura central é pela credencial da empresa (REST), sem usuário de serviço no Fracttal.
4. Gravar no Fracttal segue com o login de quem usa.
5. O banco guarda IDs, datas e status; o texto da OS e os nomes ficam na memória e numa cópia em disco do servidor.
6. A medição de uso vai ao banco sem setor; o corte por setor fica só no Raio-X, 30 dias.
7. O PC roda o mesmo canto, sem a leitura da madrugada (seção 4).
8. Se a leitura das finalizadas não existir quando a etapa 3 começar, ela é construída aqui; o fato segue com o PCM.
9. As faixas: novas a cada 3 min no horário de trabalho, últimos 7 dias a cada 10 min, abertas de hora em hora, o
   resto de madrugada (01:00–05:00); ajustadas pela etapa 0.
