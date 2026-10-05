# CLAUDE.md — torre Campo · App

O modo gerencial do App de Campo dentro do Nexus. As telas espelham as abas do painel de gestão do App
(`https://gridco-campo-mw.azurewebsites.net/api/gestao`, servido pelo `gridco-campo-mw`). Leia também o `CLAUDE.md`
da raiz.

## Regra: tudo em paralelo (Levi, 04/10/2026)

"Por hora todas as decisões para o Nexus são paralelas, não deve afetar o funcionamento atual." Nada aqui escreve no
App nem no Fracttal. Aprovar, devolver, encaminhar e decidir PT continuam no painel do App: a tela do Nexus mostra e
leva até lá.

## Encaixe: aba do painel do App → tela daqui

| Tela do Nexus | Aba do painel do App |
|---|---|
| Central de atenção | Atenção (Pontos) + Encaminhamentos |
| Aprovação de OS | Supervisão (fila de verificação por supervisor) |
| Permissões de trabalho | Atenção, sub-aba PT (criada em 04/10 a pedido do Levi) |
| Ordens de serviço | Ordens de serviço |
| Rondas | Rondas (do período + ronda longa) |
| Zeladoria | Zeladoria (criada em 04/10 a pedido do Levi) |
| Ranking | Desempenho (regiões 60% qualidade + 40% cobertura; colaboradores) |
| Triagem de qualidade | Triagem de qualidade |
| Imagens da ronda | Imagens |
| Rotas do dia | não existe no App: tela nova (programação do PCM + localização das usinas) |

Fora daqui: a "APR e PT" da torre HSEQ responde outra pergunta (OS de risco sem APR ou PT assinada). A Configuração
do App fica para o Levi decidir (organização, alocação, vínculo e acessos já são do cadastro do Nexus; tempos
previstos são do PCM). O Canal do App não tem tela.

## De onde vem o dado

**Sem Azure** (Levi, 04/10/2026: "não quero ligação com Azure, quero que seja direto pelo GitHub pois subirei para um
servidor que Azure não existe"). O Nexus não lê o Storage do App; a leitura por chave SAS foi feita e REMOVIDA no mesmo
dia (biblioteca, gerador de chaves e testes). `tests/test_campo_atencao.py` trava: nenhum módulo do Nexus importa o
SDK do Azure. **Destino do que o Nexus calcula: a API do PG** (`GRIDCO_DB_API`, gravação com `GRIDCO_SQL_TOKEN`),
nunca arquivo JSON (Levi, 04/10: "não aceito esse JSON como banco de dados pois temos a API do PG").

**Está no Fracttal** (Levi, 04/10: "tá óbvio que vem do Fracttal com métricas bem estabelecidas, é só copiar a
regra"). Medido no código do App (v225) e na leitura do Fracttal: no fechamento o App grava lá quase tudo, e o Nexus
lê com a régua copiada:
- respostas do checklist: `work_orders_subtasks` (valor, `is_required`, tipo). O "Não se aplica" vai escrito no valor;
- fotos: `work_orders_attachments`, descrição "desc · GPS lat,lon · hora". A foto de campo também é anexo da tarefa,
  com a descrição começando pelo nome do campo;
- tempos (início, fim, duração prevista e real, `review_date`) e a fila de verificação (status 2);
- ronda: a OS dela leva no `note` o dia, a usina, a qualidade, a duração real com o horário (a do celular) e as
  respostas do checklist; a subtarefa "Pendências e ocorrências" leva falhas, itens sem resposta, trackers com
  desvio e achados (`_pendencias_ronda`), mas nem sempre: medido em 05/10, das 3 rondas mais recentes uma estava
  vazia e outra repetia o resumo (o supervisor preenche à mão para conseguir aprovar). Fotos da ronda: nenhuma
  nas 3 (ficam no blob do App).

**O que só o App sabe, vindo do próprio App (v226, no ar desde 05/10 12:03, mas o envio está DESLIGADO até a chave
`NEXUS_PESSOA_HMAC` entrar no App Setting; a chave é o interruptor):** o timer `nexus_workbooks_sync`
do `function_app.py` (aos :25) sobe `fechamentos_app_campo` (nota do painel, caixa de observação, GPS no início e no
fim, pontualidade), `pt_app_campo`, `zeladoria_app_campo` e `decisoes_app_campo` para a API de planilhas. Pessoa só
como HMAC do e-mail (`NEXUS_PESSOA_HMAC`, a mesma chave no App Setting e no `.env` daqui): `ligacao_cadastro` troca o
código pelo `pessoa_id` (e-mail do cadastro decifrado na hora). O livro `rondas_app_campo` (v210) já existia: falhas,
trackers, início e fim de cada ronda. **Falta:** as telas daqui lerem esses livros (a nota do App no lugar da calculada,
a pontualidade, a PT e a zeladoria).

**Não está no Fracttal:**
- da nota: a caixa "Registre observações" do App (até 15 pontos), o GPS do fechamento (vale o das fotos) e os
  `intocados`. A assinatura o REST não devolve (`signature` vazio em 100 de 100 OS em verificação), mas o App não deixa
  concluir sem ela (campo.html, `travasSheet`): entra como dada. A pontualidade (hora de início no celular contra a
  programação) também não: na tela vira traço, não 0%;
- telas inteiras: decisões do painel (encaminhamentos, tratamentos), "De acordo" da PT, diárias e EPI da Zeladoria,
  análise das imagens, rondas inteiras. Para essas o dado precisa chegar à API do PG: (A) o App manda, com nome e
  e-mail cifrados; (B) o servidor do App sai do Azure. Decisão do Levi. A fonte entra em `nexus/campo/tabelas.py`
  (`usar_fornecedor`, mesmo jeito de consultar: `query_entities` com "PartitionKey eq", `get_entity`); a partição
  `tok` nunca vem.

**O caminho do dado (04/10, Levi: "pode gravar na API do PG e ligar as telas"):** Fracttal -> `coletor.py` (só GET,
devagar) -> API do PG, workbook `campo_nexus`, aba `fechamentos` (uma linha por tarefa da fila de verificação, status
2, e das aprovadas, status 3, com fim nos últimos 90 dias; aba `atualizacao` com a hora da coleta e a cobertura) ->
`fonte_pg.py` -> as regras copiadas do App, no formato das tabelas dele (`qualidadelog`; o par `rondaos`/`rondas` só
para a OS de ronda na fila) -> telas.
- **Cobertura completa** (`completa` na aba `atualizacao`) = a fila inteira e as aprovadas da janela lidas sem 429 e
  todas calculadas. As telas só saem da moldura do App com ela. Motivo (04/10, 1ª carga): com 40 de ~2.900 OS
  calculadas, a Aprovação punha 2.846 tarefas em "fora do App" e a de OS contava 33 fechamentos em 7 dias, só porque o
  coletor não tinha chegado ao resto; e as OS aprovadas antes da coleta começar nem estão na fila.
- Aprovadas: `sort=final_date:desc` devolve da mais recente para a mais antiga, mas só aproximadamente (medido em
  04/10: 22.304 no total, dias fora de ordem dentro da página). A leitura para quando a página INTEIRA passou do piso
  de 90 dias: na 1ª carga, 5.646 aprovadas na janela, ~63 páginas. Custo fixo de cada rodada: ~118 pedidos de lista
  (55 da fila + ~63 das aprovadas), uns 5 min; de 30 em 30 min, ~4 pedidos por minuto em média.
- **Fechada pelo App** (`pelo_app`) = a marca das fotos que o App sobe: descrição com a hora `toISOString` ou o GPS, ou o
  nome de arquivo do `subir_fotos` ("desc-1a2b3c4d.jpg", "OS15377-foto2-..."). Sem a marca, a tarefa não tem nota e cai
  em "Fechadas fora do App", como no painel. Fechamento pelo App sem nenhuma foto não é reconhecido (fica fora).
- OS de ronda: a nota é a que o App escreveu no texto da OS ("Ronda <dia> · <usina> · qualidade 87%"); não entra no
  registro, como no App, e não vem como ronda finalizada (a Triagem não a conta).
- **Aba `rondas`** (Levi, 05/10: "esses dados de ronda têm sim que ir para a API, guardados como informação de ronda,
  salvando o número da OS e todas essas informações"): uma linha por OS de ronda, com dia, usina, equipe, região,
  técnico (id + nome cifrado), qualidade, duração real e horário, respostas do checklist, pendências e achados, fotos
  no Fracttal (quantas e se têm GPS), situação e datas. Custa 2 pedidos por OS (fotos e subtarefas). A ronda gravada
  antes disso (só a nota) é relida uma vez (`ronda_lida`). O que NÃO tem: tracker a tracker, zonas, o trajeto de GPS e
  as fotos em si: nascem no App e não vão ao Fracttal.
- **Devolvida** = a tarefa voltou ao técnico (status 1) ou foi fechada de novo (a data de fim mudou) DEPOIS que o
  coletor passou a acompanhá-la; o histórico de antes não existe no Fracttal.
- Nome do técnico: CIFRADO no banco (`NEXUS_CHAVE_CADASTRO`, o cofre do cadastro, contexto
  `campo_nexus/fechamentos/<id_tarefa>/tecnico`); decifrado na hora pela fonte. E-mail e supervisor: pelo cadastro do
  App (`identidades.json`), por nome, como o `_pessoa_por_nome` da fila. Sem e-mail no banco.
- A linha só muda (e só ganha `lido_em` novo) quando algo do Fracttal mudou: a API guarda histórico por linha.
- **Ligado ao cadastro por ID** (Levi, 05/10: "pode ligar ao usina_id e pessoa_id do cadastro"; `ligacao_cadastro.py`):
  `usina_id` pelo `de_para` do `cadastro_nexus` (sistema "Fracttal · Classificação 1", chave = `groups_1_description`,
  hífen sem espaço em volta conta igual); `pessoa_id` pelo nome do técnico contra o nome e o nome padrão da ficha,
  decifrados na hora (homônimo não liga). Cadastro fora do ar = os IDs ficam como estavam. A aba `atualizacao` diz
  quantas linhas ficaram sem ID (`sem_usina_id`, `sem_pessoa_id`): 1ª medida (05/10, 00:55) 400 e 982 de 5.025; as
  usinas sem de-para eram "Grid Co.", RenoGrid Colíder 1 e 2, Solier Cascavel e Thopen Coração 1. Conserto de lacuna é
  no cadastro (de-para), não aqui.
- `ativo` = usina (`groups_1_description`) · código do ativo. NUNCA a descrição inteira do Fracttal
  (`items_log_description`): ela traz o ENDEREÇO da usina, que no cadastro do Nexus é sensível e vai cifrado. A 1ª
  carga gravou o endereço em claro em ~4.500 linhas (04/10 20:55 a 05/10 00:10); a rodada das 00:10 regravou todas
  sem ele, mas o histórico por linha da API pode guardar o valor antigo. Antes de pôr coluna de texto nova no banco,
  confira o que o Fracttal manda nela.

**Cota do Fracttal:** 200 pedidos por minuto para a EMPRESA inteira, a mesma do App (domingo 04/10, perto das 20h, já
estava esgotada: 429). **O coletor NÃO roda no horário de campo** (seg a sex, 6h às 18h; `deve_rodar`): segunda,
05/10, a cota ficou esgotada das 07:12 em diante e a OS 15423, criada às 09:53, não aparecia para o técnico no App (a
lista dele, `/minhas-os`, lê o Fracttal a cada 10 min e, com 429, serve a última lista boa; saída na hora: "Buscar OS
pelo número" no App). Fora do horário, 1 s antes de cada pedido (rodada que chega às 6h de dia útil para e grava); a fila inteira (~55 páginas) a cada rodada; por OS nova,
as fotos (1 pedido) e, só se for do App, as subtarefas (mais 1); no máximo 40 OS novas por rodada no horário de campo
(seg a sex, 6h às 18h) e 1.000 fora dele, gravando a cada 100 OS; fora do horário de campo, com pendência e sem
429, a próxima rodada emenda em 1 min (`espera_s`); de madrugada, um 429 espera 90 s e repete o MESMO pedido (até 3
vezes, `ESPERA_429_S`), em vez de encerrar a rodada e reler a fila (~118 pedidos): na 1ª carga, com a rodada
encerrando a cada 429, o ritmo caiu de 43 para 17 tarefas/min; erro passageiro (a API do PG deu 502 por 1 min em
05/10, 00:04) espera 2 min de madrugada e 30 de dia; a 1ª carga tinha 10.896
tarefas (fila + aprovadas), ~1,4 tarefa por OS; o relatório de cada rodada vai para `logs/nexus.log`
(`nexus.campo.coletor`, só contagens); as aprovadas da janela (~15 páginas) a cada rodada; saídas da fila (devolvida, cancelada ou aprovada antes do piso)
até 60 por rodada; fila ou aprovadas lidas pela metade = a rodada para ali; para no primeiro 406/429 e grava o que já
calculou. 1ª rodada real (04/10, 20:55): fila de 5.411 tarefas, 40 OS, 122 pedidos, 5 min 11 s, 45 linhas gravadas e
conferidas; 3 OS recalculadas por outro caminho bateram com o banco.

**Rodar o coletor:** dentro do Nexus, a cada `NEXUS_CAMPO_COLETOR_MIN` minutos (30), só onde `NEXUS_CAMPO_COLETOR=1`
(UMA máquina: duas leriam a mesma fila e gastariam a cota em dobro). À mão: `python ferramentas/coletar_campo.py
[--max-os N]`, que imprime só contagens. Grava com `GRIDCO_SQL_TOKEN`; sem ele, calcula e não grava. Depois de gravar,
lê de volta e confere linha a linha (diferença = erro no relatório).

A moldura (iframe do painel do App) continua onde a tela não tem fonte: é o navegador que abre o painel do App.

## Estado (04/10/2026)

- As 9 telas que têm aba no App abrem o **próprio painel do App, na aba delas**, dentro do Nexus (moldura
  `templates/campo/painel.html`). Motivo: o Levi viu as telas vazias ("construiu as abas mas ainda não vejo nada").
- Abre direto na aba pelo deep-link do painel: `/api/gestao#ir=<aba>` (atn, su, pt, os, ro, zl, des, vg, img). O
  painel não manda `X-Frame-Options` e faz o login Microsoft por popup (`redirectUri` fixo em `/api/app`), por isso
  funciona em moldura. Na moldura quem age é o painel do App, com o login dele: o Nexus não lê nem grava nada.
- Endereço do painel: `NEXUS_CAMPO_PAINEL` na config (padrão: produção).
- **Só o menu do Nexus aparece** (Levi, 04/10: "está duplicando a barra lateral"). O Nexus não mexe no HTML do
  App (outro endereço), então a moldura fica 224 px mais larga e a faixa do menu do App fica fora da vista
  (`.campo-recorte` no `nexus.css`). Medidas do gestao.html v225: `.sb{width:224px}` e, com 900 px ou menos, o
  próprio painel esconde o menu; por isso o recorte só vale com 677 px ou mais de área visível (container query).
  Conferido: 1440 px, 820 px (recorta 224) e 375 px (não recorta, sem rolagem lateral).
  **Se o App mudar a largura do menu ou o ponto de 900 px, o recorte corta conteúdo ou mostra a beira do menu:**
  mude o CSS e o `tests/test_torre_campo.py` juntos. A saída robusta é o App ganhar um modo "sem menu" numa versão
  futura, quando houver publicação dele de qualquer forma.
- Sem o menu do App, o que só ele alcançava vem pela faixa acima da moldura: abas (Central de atenção = Atenção +
  Encaminhamentos, `?aba=`) e "Abrir no App" (painel inteiro em outra aba: Conta Fracttal, sair, Configuração,
  Canal do App).
- "Rotas do dia" não existe no App e segue placeholder.
- **Aprovação de OS, Ordens de serviço e Triagem saem do banco do Nexus** (04/10) assim que a coleta estiver completa:
  a fonte (`fonte_pg.Fornecedor`, ligada por `nexus.campo.instalar` no `app.py`/`servir.py`) liga a tela nativa
  sozinha; coleta incompleta, banco vazio ou fora do ar = moldura do App. Atenção e PT continuam na moldura: o dado
  delas nasce no App. A 1ª carga roda na noite de 04 para 05/10 na 5070 do Levi (o processo foi reiniciado com
  `NEXUS_CAMPO_COLETOR=1`; o `Iniciar Nexus.bat` não liga o coletor). Andamento: a aba `atualizacao` do `campo_nexus`
  (leitura pública: `pendentes`, `completa`).

## Telas do Nexus (aba por aba, Levi aprova cada uma antes)

O Levi pediu as telas "ala Nexus" (04/10: o painel do App puxa um roxo, `#0f0d17`/`#1c1830`/`#191528`, que o Nexus
não pode repintar porque vem de outro endereço). Cada aba vira tela própria, com proposta aprovada antes.

| Aba | Estado |
|---|---|
| Central de atenção | **No Nexus** (proposta aprovada: https://claude.ai/artifact/SBPyaREFJpHAEKimd7xnHv) |
| Aprovação de OS | **No Nexus** (proposta aprovada: https://claude.ai/artifact/UqLiJApqDHA7bVqD59hPFY) |
| Permissões de trabalho | **No Nexus** (proposta aprovada: https://claude.ai/artifact/DjP2sXABw5rz5FFjVFNKBu) |
| Ordens de serviço | **No Nexus** (Levi, 04/10: "passa para o Nexus logo"; daqui em diante sem proposta) |
| Triagem de qualidade | **No Nexus** (04/10, pelo banco): OS e supervisores; rondas e usinas sem ronda seguem no App |
| as outras 4 | moldura do App até a vez delas |

Cada tela do Nexus liga sozinha quando tem o que precisa (`TELAS_DO_NEXUS` em `__init__.py`; `configurado()` pede só a
tabela que a tela EXIGE, e a fonte do banco diz o que serve). Sem isso, a moldura do App continua. Aprovação, OS e
Triagem rodam com dado real do banco; **bater nota a nota com o painel do App** é a conferência que falta (o Levi vê o
painel do App; eu não).

**As contas são as do App, copiadas, não refeitas** (`nexus/campo/regras_app.py`):
- `ferramentas/extrair_regras_campo.py` copia do `function_app.py` do App o fecho das funções das rotas (150 itens em
  04/10, com as duas réguas da nota e a Triagem). Variável local de função não puxa nada (análise de escopo pelo `symtable`): o `app`
  local do `_obs_do_fechamento` trazia o `app = func.FunctionApp()` do Azure. A cópia
  leva **só a lógica** (`ast.unparse`, sem comentários nem docstrings): o repositório é público e os comentários do
  App citam colegas pelo nome completo. A fidelidade é pela árvore do código: `tests/test_campo_atencao.py` compara
  cada item com o App e acusa qualquer diferença; aí é rodar o extrator de novo.
- Trocados pelo Nexus (fim do arquivo gerado, e o teste vigia se o App mudar a versão dele de cada um): `_tabela` e
  `tabela_qlog` (leem pela fonte do Nexus, `tabelas.py`), `tabela` (a tabela dos tokens, só as partições `cadastro` e `pt`, por
  `pessoas.tabela_dos_tokens`; a dos tokens, `tok`, recusada), `fx`
  (Fracttal só GET, `fracttal.py`) e `ident` (`pessoas.ident`, a mesma mescla do App). O extrator recusa copiar
  qualquer função que abra a conexão do App.
- O código do App que vale é o da pasta `App_Campo\middleware` do SharePoint (o mesmo `codigo` do `/api/health`; em
  04/10, `9662733fd7381fa1` = v225).

Peças em `nexus/campo/`:
- `tabelas.py`: a porta das tabelas do App para as regras copiadas (`usar_fornecedor`; `TabelaSoLeitura` na ordem do
  Azure, recusa filtro que as regras não mandavam e qualquer gravação). Erro de leitura fica anotado e a tela avisa
  "Não consegui ler", em vez da fila vazia que as regras do App devolvem.
- `coletor.py`, `banco_campo.py`, `fonte_pg.py`: o caminho do dado (acima). `ferramentas/coletar_campo.py`: rodada à
  mão.
- `fracttal.py`: credencial do OS Creator (`pcm.geracao.credencial`), um pedido por vez com 0,5 s de intervalo
  (o App busca 6 páginas de uma vez), recusa 406/429 sem insistir, nunca escreve. O `_fila_bruta` do App guarda a
  fila crua por 10 min: filtros diferentes não pedem de novo.
- `pessoas.py`: o `identidades.json` vem de `NEXUS_CAMPO_IDENTIDADES` (servidor: `dados/campo/`, fora do git) ou da
  pasta do App na máquina do Levi.
- `leitura.py`: cópia de 5 min; leitura com erro não fica guardada.
- `nota_fracttal.py`: a nota do fechamento com o que o Fracttal guarda. Traduz subtarefas e anexos para o fechamento
  que o App monta e chama as DUAS réguas copiadas: a do PAINEL, `_qualidade_os` (subtarefas 25, fotos 20 com 3 dando o
  total, descrição 10, assinatura 10, observação 15, GPS 20: é a `qualidade` que o App grava no registro e que as telas
  mostram) e a do PLACAR, `_qualidade_v2` (pontos do ranking). **Erro meu corrigido em 04/10:** a 1ª prova mostrou ao
  Levi a do placar como se fosse a do painel. Foto pedida: nem o App enxerga (o checklist do fechamento vai sem
  `anexo`/`anexoApp`), então as duas notas tratam a foto igual.
- `atencao.py` (tabelas `rondas`, `atencaoos`, `decisoes`, `rondaativos`; sem o "Em campo agora", que o App lê do
  Fracttal ao vivo), `aprovacao.py` (fila do Fracttal + `qualidadelog`, `rondas`, `rondaativos`, `rondaos` e a
  partição `cadastro`) e `pt.py` (partições `pt` e `cadastro` + `acessos`, `atribuicoes`; a PT sai SEM o modo
  "completo" do App: nada de assinatura nem respostas da APR) e `ordens.py` (`qualidadelog` + `cadastro`; período e
  janela anterior como o `janelaAnterior` do painel). Escopo de Admin (vê tudo).
- O cartão "Tempo vs. previsto" do App mostra "+66%", mas a conta é real ÷ previsto: no Nexus o mesmo número sai
  como "66% do previsto".

- `triagem.py`: o `_gestao_prioridades` do App (rota gestao/prioridades), com os limiares PADRÃO (o ajuste do painel do
  App mora numa tabela dele). O motivo vem com `<b>`: a tela escapa tudo e devolve só o negrito.

Telas: `templates/campo/atencao.html`, `aprovacao.html`, `pt.html`, `ordens.html`, `triagem.html` + `static/campo.css`;
filtros pela URL.
Encaminhar, resolver, aprovar, devolver e decidir PT continuam no App: o botão de ação leva até lá.

Conferência visual sem a fonte: `scratchpad/nexus_verif_campo.py` da sessão 4422a302 sobe uma cópia na 5075 com
tabelas e Fracttal falsos (dados de exemplo).

Prova: `tests/test_torre_campo.py`, `test_campo_atencao.py`, `test_campo_aprovacao.py`, `test_campo_pt.py`,
`test_campo_ordens.py`, `test_campo_nota_fracttal.py`, `test_campo_coletor.py`, `test_campo_fonte_pg.py`,
`test_campo_telas_pg.py` (Fracttal e API do PG falsos: `tests/pg_falso.py`).
