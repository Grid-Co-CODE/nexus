# CLAUDE.md — torre Campo · App

A visão do Nexus sobre o trabalho de campo. **Nenhuma tela abre o painel do App nem aponta para o Azure** (Levi,
05/10/2026: "quero parar de referenciar o Azure e ter uma visão nossa!"): todas leem o banco do Nexus (API db_performace).
Leia também o `CLAUDE.md` da raiz e, antes de pôr dado novo no banco, o `nexus/dados/CLAUDE.md` (PRIORIDADE 0).

## Regra: tudo em paralelo (Levi, 04/10/2026)

"Por hora todas as decisões para o Nexus são paralelas, não deve afetar o funcionamento atual." Nada aqui escreve no
App nem no Fracttal. Aprovar e devolver OS e encaminhar ponto continuam no App. Sem link para o painel do App e sem
"Abrir no App". **A OS aparece só com o número, sem "#"** (Levi, 05/10: "Em OS tira esse #").

**Exceção: a decisão da PT** (Levi, 05/10: "Técnico faz APR e PT -> Chega no PG -> Atualiza para os steakholders ->
Atualiza na aprovação de PT -> Supervisor faz -> Fica salvo!"). Ver "Aprovação de PT no Nexus" abaixo.

## As telas

| Tela | De onde vem | Quem calcula |
|---|---|---|
| Central de atenção | rondas e PT do App + cadastro do Nexus | `visao.atencao` (conta nossa) |
| Aprovação de OS | fila de verificação do Fracttal ao vivo (só GET) + nota do livro do App | regras copiadas do App |
| Permissões de trabalho | `pt_app_campo`; a OS abre a aprovação (`/t/campo/pt/<número>`) | `visao.pts` (conta nossa) |
| Ordens de serviço | `fechamentos_app_campo` | regras copiadas do App |
| Rondas | `rondas_app_campo` + usinas mobilizadas do cadastro | `visao.rondas` (conta nossa) |
| Zeladoria | `zeladoria_app_campo` | `visao.zeladoria` (conta nossa) |
| Ranking | `fechamentos_app_campo` + cobertura de ronda | `visao.ranking` (conta nossa) |
| Triagem de qualidade | `fechamentos_app_campo` + rondas | regras copiadas do App |
| Imagens da ronda | placeholder: a foto ainda não chega ao banco | — |
| Rotas do dia | placeholder: programação do PCM + localização das usinas | — |

Fora daqui: a "APR e PT" da torre HSEQ responde outra pergunta (OS de risco sem APR ou PT assinada).

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
- **Usina e equipe ligam ao cadastro pelo `Ligador`** da camada de dados (`nexus/dados/fatos.py`): de-para "Fracttal ·
  Classificação 1" (a parte depois de " · "), de reserva o código da usina dentro do código do ativo (só se for
  único). A base da cobertura, do ranking e da Central são as **usinas mobilizadas**: status `OPERAÇÃO` E data de
  mobilização já passada (Levi, 05/10: "tem usina que nem mobilizada está"; medido: das 177 em OPERAÇÃO, 49 sem data
  de mobilização e nenhuma delas com ronda pelo App; as 107 com ronda têm a data). A PT não passa por esse filtro: PT
  esperando decisão aparece sempre. Onde a tela mostra a usina, mostra **Equipe, Estado e Região do Brasil** do
  cadastro, nunca a "Região" que o App escreve (Levi: "uma hora é '-' outra é o nome da UFV, outra é o nome do
  cluster"). A **região do Brasil sai da UF** (`visao.REGIAO_DA_UF`), não da coluna `regiao` do cadastro: medido em
  05/10, ela diz "Sudeste" para Alto Paraná 1 e 2 (PR), "Nordeste" para Ponto Belo 1 (ES), está vazia em Aquiraz e
  Cascavel (CE) e mistura "Centro Oeste" com "Centro-Oeste". Conserto da coluna é no cadastro. Pessoa aparece pelo **nome resumido** (`visao.nome_curto` = o "Nome padrão" do cadastro: primeiro e último
  nome). A Aprovação de OS e as Ordens seguem com a região do Fracttal/App, porque a fila não traz a usina. Região que o App
  escreve e o cadastro não tem (medido em 05/10: "MT Sul 02", 15 fechamentos; "Grid Co.", 1) vai para "fora do
  cadastro", não some. Conserto é no cadastro.
- **O que o livro ainda não traz:** a situação da OS no Fracttal, as durações do Fracttal, a aprovação e a avaliação (o
  App guarda de madrugada, `_enriquecer_qlog`, e não manda). Ficam desconhecidas, não aproximadas: "Em verificação" e
  "Tempo real" saem "—" (`ordens._ajuste_da_fonte`; com a duração do celular dava 5.726%, com a situação pela revisão
  do painel, 402 de 447 "em verificação"). Para ter: o App mandar essas colunas (mudança no App).
- **Zeladoria vazia é real:** em 90 dias o App não registrou nenhuma etapa de zeladoria. A tela diz isso.

## As contas nossas (`nexus/campo/visao.py`)

As constantes ficam no topo do arquivo; cada função diz a regra no docstring.
- **Rondas** (05/10, no estilo do painel de rondas que o Levi mostrou): seis indicadores do período (`painel_rondas`,
  depois dos filtros de região e supervisor) e quatro abas: Registros (a tabela "Rondas diárias": iniciais do
  técnico, tipo, início e fim em Brasília, duração "27 min"/"1h04", qualidade com barra, veredito em selo; filtro
  de duração; até 300 linhas com o aviso; Exportar CSV com BOM para o Excel), Cobertura (usinas mobilizadas, a mais
  esquecida primeiro), Trackers (rondas com trackers apontados e a devolutiva) e Quem ronda (por técnico).
  - Cobertura = usinas mobilizadas com ronda no período ÷ mobilizadas; a seta compara com o período anterior de
    mesmo tamanho. Duração = fim − início carimbados pelo aparelho (0 a 8 h; fora disso, sem duração; o livro não
    traz a pausa). **Veredito = o `_veredito_ronda` do App, na mesma ordem, com os limites dele** (`LIMIARES_PADRAO`:
    60/85/95 e 10 min); o GPS só aparece como a falha "sem GPS". "Ronda longa pendente" é pendência para o App
    (vira Atenção). Medido em 05/10, 30 dias: 455 rondas, cobertura 80% (102 de 128; antes 65%), qualidade 96%,
    duração média 45 min, 36 abaixo de 10 min.
  - **Os seis indicadores filtram a tabela** (Levi, 05/10): Rondas finalizadas = as de hoje (`ind=hoje`); Cobertura =
    as usinas sem ronda no período (`aba=cobertura&cob=sem`); Qualidade = abaixo do limite (`ind=qualidade`); Duração =
    da mais longa para a mais curta (`ind=duracao`); Abaixo de 10 min = `dur=curta`; Usina mais atrasada = as há 7 dias
    ou mais (`cob=atrasadas`). O cartão ativo fica marcado; clicar de novo, ou no × do filtro, tira.
  - **Ronda sem OS, o motivo em português** (`visao.motivo_sem_os`; Levi, 05/10: "não entendi essa observação, minha
    conta fracttal já está conectada"): o App cria a OS de ronda com a conta Fracttal do TÉCNICO; "Conecte sua conta
    Fracttal" é a mensagem do App para o técnico. Medido em 05/10: 114 de 771 rondas (90 dias) sem OS por isso (Daniel
    Paula 22, Manuel Silva 14 + 8, Frank Melo 10, Isake Costa 12, Valmir Junior 8...). O App tenta 5 vezes, uma por
    minuto, e desiste (`RONDA_OS_FILA_MAX`, `_MAX_H` 24 h): a ronda antiga não ganha OS quando o técnico conecta depois.
  - **As rondas feitas saíram da Central de atenção** (Levi, 05/10: "na parte de atenção quero só o que for pendente"):
    na aba Registros, o filtro de pendência (Sem OS no Fracttal, Evidência incompleta) e a coluna Pendências.
  - **Sujidade e vegetação** (Levi, 05/10: "é importante!"; `nexus/campo/ronda_checklist.py`): o livro de rondas não
    traz o checklist, mas o App escreve cada resposta no texto da OS de ronda no Fracttal ("Sujidade dos módulos: 2;
    Altura da vegetação: 3; Sujidade da vala de drenagem: Parcial; Piranômetro IPOA ...: Limpo"). As listagens do REST
    trazem esse texto em lote: as em verificação já estão na fila da Aprovação; as aprovadas, ~30 páginas (45 dias),
    relidas em segundo plano no máximo a cada 30 min (e 90 s depois de subir). Nada vai para o banco. Por usina: a
    última leitura no período e a anterior (a seta); nível 1 a 5, acima de 3 pede ação (o `alerta_acima` do App);
    distribuição por nível; vala, sombreamento e sensores sujos. Medido em 05/10 (30 dias): 96 de 128 usinas com
    leitura, 382 de 417 rondas com OS lidas; sujidade média 2,5 (21 usinas em 4 ou 5), vegetação 2,4 (16), vala suja
    ou parcial em 47. O caminho limpo é o App mandar essas colunas no livro de rondas (mudança no App).
- **PT:** fila "aguardando" da mais antiga para a mais nova; espera = da criação à decisão; parada = mais de 2 h.
- **"Esperando o De acordo" é a MESMA tela da Central > Permissões de trabalho** (Levi, 05/10): as duas incluem
  `templates/campo/_pt_esperando.html` (cartões compactos por equipe; tabela com a OS em verde, Equipamento, Espera no fim
  e a linha que abre o detalhe). Mudou uma, mudou a outra.
- **Tela de PT** (Levi, 05/10): abas "Esperando o De acordo" (cartões por equipe com a lista das PT de cada uma, ou
  tabela) e "Histórico" (decididas, período 7/30/90 dias, por situação). Filtro de supervisor; o cartão leva à tabela
  da equipe. Na tabela: só o número da OS, em verde Grid, no lugar do número da PT (abre a aprovação); Equipamento no
  lugar do Estado; Espera na última coluna; clicar na linha abre o detalhe (PT, equipamento, equipe e supervisor,
  atividades críticas com sim/não/NA, respostas NÃO, 1º aviso, decisão e motivo). O cartão inteiro leva à tabela
  da equipe, com a faixa de quem ela é (supervisor, técnicos, PT esperando e paradas).
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
- **Ranking por região:** 60% nota média dos fechamentos + 40% cobertura de ronda (usinas da equipe com ronda nos
  últimos 14 dias), a régua do painel do App. **Só pontua quem tem as duas partes:** região sem fechamento no período
  ganhava 100 só pela cobertura (erro meu, corrigido em 05/10). Colaboradores: nota, fechamentos, pontualidade e
  devolvidas.
- **Central de atenção, só o que está pendente** (as rondas feitas foram para a tela Rondas em 05/10; o texto abaixo descreve a origem) (Levi, 05/10: "separar Rondas feitas (histórico de rondas) e rondas
  pendentes, dando bastante atenção nas pendentes"; "separe o que é ronda e o que é Permissão de Trabalho"):
  - **Rondas pendentes** (abre nela, com números grandes que filtram): uma linha por usina mobilizada que pede ronda:
    nunca teve, sem ronda há 7 dias ou mais, ou ronda longa pendente pela última ronda (o App repete o aviso em toda
    ronda curta). Colunas: Há, Status, Usina, Equipe, Estado, Região, Observação. Medido em 05/10: 86 (21 nunca, 45 há 7 d ou
    mais, 20 longa pendente).
  - **Rondas feitas:** o histórico do período, com "Feito por" (só aqui aparece quem fez), Status (Sem OS no
    Fracttal, Evidência incompleta, Sem pendência), Observação, OS e nota. Medido: 232 em 14 dias (178, 39 e 15).
  - **Permissões de trabalho:** as PT esperando, Técnico e a OS em verde, que abre a aprovação. Medido: 22 (21 paradas).
  - **Duas visões em cada aba** (Levi, 05/10: "tem que ter a visão por equipe (CARDS grandes agrupados) e a visão
    da tabela!"): abre nos **cartões por equipe** (`visao.por_equipe`): usinas pendentes de ronda, % feitas (= usinas da
    equipe que não estão pendentes ÷ usinas da equipe, com a barra feitas × pendentes), o detalhe por status, as rondas
    do período e as PT esperando. O cartão leva à tabela da equipe (`?equipe=`). Filtro pela **região do Brasil** no
    lugar do estado. Medido em 05/10: 53 equipes; PR Norte 02 com 6 de 6 usinas pendentes.
  - Todas as colunas e cabeçalhos das tabelas do campo **centralizados** (Levi, 05/10).
  - **No cartão, do cadastro de pessoas** (`visao._Base._time`): o ícone de homem de capacete com o número de
    técnicos (colaborador de campo da equipe que não está Desligado: os 28 sem status estão todos em equipes sem
    nenhum Ativo) e o supervisor (o `supervisor_id` dos técnicos; o nome é o "Nome padrão" da ficha, decifrado com
    `NEXUS_CHAVE_CADASTRO`; sem a chave, "Supervisor <id>"). O Levi pediu emoji; é ícone desenhado, pela regra sem
    emoji na interface. **Filtro de supervisor** ao lado da região. Embaixo da barra, número em cima e o que ele é
    embaixo ("feitas", "pendentes", "total"), para um leigo ler. Medido em 05/10: 6 supervisores; SP Oeste 03, PI Leste
    01, MS Leste 01 sem técnico no cadastro (6 usinas sem supervisor).
  - Os filtros (status) são só a palavra colorida, sem fundo (`.cn-st`). "Detalhe" virou "Observação"; "O quê" virou
    "Status"; a coluna "Quem" saiu. **Nota baixa de fechamento não entra:** é a fila da Aprovação, e o fechamento
    aprovado direto no Fracttal nunca tem decisão no painel, o que dava ponto falso.
- Cópia de 5 min por tela; banco fora do ar = a tela avisa "Não consegui ler o banco do Nexus" e não some. Nos testes,
  sem `app.extensions["nexus_dados_sessao"]`, nunca vai à rede.

## Aprovação de PT no Nexus (05/10/2026)

A OS da PT (verde) abre `/t/campo/pt/<número>`: a PT inteira (tarefa, ativo, técnico, atividades da APR com sim/não/NA,
respostas NÃO, falta, forçada) e a decisão.
- **Quem assina: o login do Fracttal do OS Creator** (Levi: "utilize o login do fractal do OS Creator Web que já dá
  certo!"). O OS Creator roda dentro do Nexus com sessão própria (cookie `os_sessao`, só em /os); por isso as rotas de
  assinatura moram em `/os/_nexus/...` (`assinatura.py`): `quem` (o e-mail de quem entrou), `pt/<n>/decidir` (POST) e
  `pt/<n>/voltar` (o OS Creator só devolve para /os depois do login). Token do Fracttal vencido (`exp`) não assina;
  pedido de outra origem leva 403.
- **Fica salvo:** `nexus_pt_decisoes · decisoes` (`nexus/campo/decisao_pt.py`; registrado no `catalogo.py` como
  `decisao_pt`). Grão: 1 linha = 1 decisão. Pessoa só como HMAC do e-mail (o mesmo código do App); motivo mascarado. O
  primeiro que decide vale: PT que já tem decisão do Nexus, ou que o livro do App já mostra decidida, recusa.
- **Falta o App aplicar** (próxima versão do App, decisão de publicar é do Levi): ler `nexus_pt_decisoes` a cada
  minuto; para cada decisão nova, conferir pelo HMAC se quem assinou pode assinar aquela PT (`_pt_pode_assinar`), se a
  PT ainda está aguardando e se a decisão é recente (sugestão: 30 min; decisão velha não libera ninguém), aplicar como
  o `gestao/pt/decidir` (pausa no Fracttal, anexo) e devolver o resultado no `pt_app_campo`. E mandar a PT ao banco na
  hora em que nasce, não só no timer de hora em hora (hoje a PT chega ao Nexus com até 1 h de atraso). Até isso, a
  tela diz: "O App ainda não lê esta decisão".

## As contas copiadas do App (`nexus/campo/regras_app.py`)

Aprovação, Ordens e Triagem usam a lógica do App copiada, não refeita, para o número bater com o painel dele.
- `ferramentas/extrair_regras_campo.py` copia do `function_app.py` do App o fecho das funções das rotas
  `gestao/supervisao/fila`, `gestao/os` e `gestao/prioridades` e as duas réguas da nota. **Atenção e PT saíram da
  cópia em 05/10** (717 linhas a menos): agora são contas nossas. A cópia leva só a lógica (`ast.unparse`, sem
  comentários: o repositório é público e os comentários do App citam colegas pelo nome).
- `tests/test_campo_regras_app.py` compara cada função com o App pela árvore do código. Falhou = o App mudou: rode o
  extrator e confira a tela. Em 05/10 o v230 mudou `_qualidade_v2` (GPS do início vale como prova); recopiado, código
  `68d4d468251f7d6a`.
- Trocados pelo Nexus no fim do arquivo gerado: `_tabela` e `tabela_qlog` (leem pela fonte do Nexus, `tabelas.py`),
  `tabela` (a dos tokens do Fracttal: só a partição `cadastro`; `tok` e `pt` recusadas), `fx` (Fracttal só GET,
  `fracttal.py`) e `ident` (`pessoas.ident`).
- O código do App que vale é o da pasta `App_Campo\middleware` do SharePoint.
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
  - **O gargalo** (Levi, 05/10: "por que demora se o histórico do OS Creator carrega tão rápido?"): o REST do Fracttal
    entrega no máximo 100 tarefas por pedido (limit=1000 devolve 99) e a fila tem ~5.500, então são 55 páginas de
    ~1,1 s; até 05/10 saíam uma por vez com 0,5 s de folga (~90 s). O histórico do OS Creator pergunta outra coisa: o RPC
    com o login da pessoa, com período e "criado por" filtrados no servidor (poucas OS). Agora `fracttal.py` deixa 4
    pedidos ao mesmo tempo, no máximo 4 por segundo, e em segundo plano tenta de novo depois de um 429 (5 s, 10 s); a
    fila é lida ao subir o Nexus (`aprovacao.aquecer`, 20 s depois; `NEXUS_CAMPO_AQUECER=0` desliga). Medido: fila
    inteira em ~20 s.
  - **Tela para insight** (Levi, 05/10: "refaça essa parte de aprovação de OS para retirada de bons insights";
    `aprovacao.fila_toda` + `_agrupa_fila`): a fila inteira pela conta do App (a cópia devolve 200 linhas por chamada;
    as páginas são juntadas, ~4 s na 1ª, e a conta do período padrão fica pronta logo depois de cada releitura).
    Seis indicadores que filtram (esperando, prontas para aprovar, pedem olho, paradas há 30 dias, espera máxima, uso do
    App), a barra da idade da fila (cada faixa filtra) e três visões: por supervisor (cartões, o que mais tem parada há
    30 dias primeiro; o supervisor e a equipe saem do cadastro pela usina do Fracttal), por técnico e a fila; CSV.
    Medido em 05/10 (90 dias): 1.827 OS e 4.736 tarefas esperando; 937 prontas; 1.780 tarefas paradas há 30 dias ou
    mais; uso do App 41%; Camila Viana 1.373 tarefas (uso do App 29%), Vitor Valadares 829 (12%).
  - **Contada por OS, não por tarefa** (Levi, 05/10: "ele não consegue aprovar uma tarefa em si, e sim uma PT ou uma
    OS"; `_por_os`, `_agrupa_os`): a OS fica no pior grupo das tarefas dela (olho > fora do App > completa), a espera é
    a da tarefa mais antiga, a nota é a pior; indicadores, idade, cartões e técnicos em OS. A linha aberta mostra cada
    tarefa com o grupo e os motivos dela.
  - **A linha aberta diz o porquê do grupo e aprova** (Levi, 05/10): `aprovacao.motivos` = a regra `_triagem` do App
    mostrando TODOS os motivos que valem (nota abaixo de 80, ronda com pendência, já devolvida, tempo fora por causa
    do técnico, foto divergente; ou por que está completa). **Aprovar = o Concluir do OS Creator Web** ("usando o
    mesmo caminho que o OS Creator Web"): o botão chama `POST /os/api/os/<id_work_order>/concluir`, a rota do clone,
    com o login do Fracttal de quem clica (status 3 + recalculate + reconferência da data de fim; IRREVERSÍVEL, pede
    confirmação). Sem login: 401, a tela leva ao login e volta (`/os/_nexus/voltar?para=`, só /t/campo/). Aprovada,
    a OS sai da fila guardada na hora (`POST /t/campo/aprovacao/<id>/tirar`). O id da OS vem da fila crua.
    **Cuidado com a cota:** cada reinício do Nexus relê a fila (55 páginas) e as rondas aprovadas (~30); em 05/10, com
    muitos reinícios seguidos, o Fracttal passou a recusar (429). Em desenvolvimento, `NEXUS_CAMPO_AQUECER=0`.
  - **Filtro de equipe e de supervisor** pelo cadastro: as usinas da equipe (ou do supervisor) pelo nome no Fracttal
    (de-para "Fracttal · Classificação 1", `visao.usinas_do_fracttal`) viram o escopo de usinas da conta do App
    (`_area_ok`, `clusters.usinas`): grupos, números e lista saem já filtrados. Usina sem de-para do Fracttal não entra
    em filtro nenhum (a lista sai em `sem_de_para`).

## Peças em `nexus/campo/`

- `visao.py`: as contas nossas (acima). `decisao_pt.py`: a decisão da PT no banco (acima).
- `livros_app.py`, `fonte_pg.py`, `tabelas.py`: os livros do App no formato que as regras copiadas consultam
  (`query_entities`, `get_entity`); erro de leitura fica anotado e vira aviso.
- `aprovacao.py`, `ordens.py`, `triagem.py`: as telas pelas regras copiadas. `leitura.py`: cópia de 5 min e
  `limpar_cache()` (que também recarrega a cópia das regras).
- `pessoas.py`: `identidades.json` e a tabela dos tokens só na partição `cadastro`.
- `nota_fracttal.py`, `coletor.py`, `banco_campo.py`: o caminho do coletor aposentado.

Telas: `templates/campo/*.html` + `static/campo.css`; filtros pela URL.

Prova: `tests/test_torre_campo.py` (nenhuma tela com Azure, moldura ou "Abrir no App"), `test_campo_visao.py` (as
contas nossas, a Central em três visões e a aprovação da PT com o login do OS Creator, banco falso), `test_campo_regras_app.py`, `test_campo_aprovacao.py`, `test_campo_ordens.py`,
`test_campo_telas_pg.py`, `test_campo_livros_app.py`, `test_campo_fonte_pg.py`, `test_campo_nota_fracttal.py`,
`test_campo_coletor.py` (`tests/pg_falso.py`).
