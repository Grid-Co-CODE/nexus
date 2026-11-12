# CLAUDE.md — torre Zeladoria (o Radar de Fornecedores dentro do Nexus)

Levi, 03/11/2026: trazer a plataforma de zeladoria inteira para o Nexus, "com a mesma lógica e caminhos do BD, só que
ao invés de Supabase virá tudo para o Nexus". Desenho: `docs/superpowers/specs/2026-11-03-zeladoria-no-nexus-design.md`.
Plano e registro: `docs/superpowers/plans/2026-11-03-zeladoria-etapas-1-e-2.md`.

## Como funciona

- **O app é um clone:** `clone/radar.html`, o Radar como estava no ar em 11/11/2026, limpo de nomes, e-mails e do
  Supabase (`clone/ORIGEM.md`). O Radar congelou nesse dia, junto com o Supabase (seção "A troca"): desde então **o clone
  é a casa da zeladoria e se edita direto**, como o OS Creator desde 31/10. A `ferramentas/zeladoria_limpar_clone.py`
  fica como registro de como ele nasceu.
- **Telas:** cada uma das 18 abas do Radar é uma tela no menu do Nexus (`ABAS`: id da tela → id da aba do clone).
  - A tela é a moldura da porta única (`.porta`) com o clone num iframe (`/t/zeladoria/app?aba=...`).
  - A barra lateral do clone some; o menu é o do Nexus.
  - Quem vê a torre é o setor (Base → Acessos) e, desde 11/11/2026, quem está aprovado no Radar (seção "A troca").
    Dentro dela, o papel e as permissões por aba do Radar decidem, como lá.
- **A ponte** (`nexus/static/zeladoria/ponte.js`) é o `window.supabase` do clone e fala com as rotas da torre:
  - `GET /api/rf/<view>` aceita `eq`/`neq`/`order`;
  - `GET /api/eu` devolve `{"user": {"id", "email"}}`;
  - `POST /api/funcao/fracttal-fotos` traz as fotos;
  - `POST /api/funcao/fracttal-os` traz a OS pelo número (até 10 por pedido; `nexus/zeladoria/fracttal_os.py`, os campos
    da antiga função do Radar: técnico, datas, situação, área, usina, serviço);
  - `POST /api/funcao/fracttal-sync` é o botão "Sincronizar com Fracttal" (seção "O Fracttal e o cronograma");
  - `GET /api/contrato-pdf?caminho=` é o `storage.createSignedUrl` do arquivo `contratos-zeladoria` (abaixo);
  - `GET /foto/<folio>/<i>`.

  Até a troca, gravar e as `fin_*` voltam `SOMENTE_LEITURA`. Com a gravação ligada, `POST /api/gravar`,
  `POST /api/funcao/fin_*` e `GET /api/situacao` (seção "A gravação"). A sessão vencida volta `SESSAO` e recarrega o
  Nexus, nunca um Radar vazio.
- **O dado** vem de três livros (`nexus_zeladoria_app`, `_fracttal` e `_historico`), lidos e decifrados por
  `nexus/zeladoria/leitura.py`, com cache de 5 min.
  - Livro, aba ou contagem faltando: a tela diz que a cópia não foi feita (`CopiaAusente`).
  - Banco que não responde: a tela diz isso e pede para recarregar (`BancoFora`). Caso: em 03/11/2026 a API da T.I. deu
    502 em dois de cada três pedidos, e a tela caía em erro 500.
  - Quem não está aprovado no `perfis` do Radar só vê a própria linha. A pessoa é casada pelo e-mail do login do
    Nexus, e o administrador sem linha vale HEAD.
- **As fotos da ronda** vêm do Fracttal, no clique, pelo `nexus/campo/ronda_fotos.py`: o link assinado fica no
  servidor, e nada vai para o bucket do Supabase. O `storage` da ponte devolve o arquivo `rondas-fotos` vazio, e o Radar
  oferece buscar no Fracttal.
- **Os PDFs dos contratos** (06/11/2026, Levi: "Servidor do Nexus"): os 105 arquivos (442 MB) do arquivo privado
  `contratos-zeladoria` do Supabase moram no disco do servidor, `<NEXUS_DADOS>/zeladoria/contratos/<caminho>`, com o
  caminho que a tabela `zeladoria_contratual_docs` cita (`nexus/zeladoria/contratos_pdf.py`). Grande demais para o banco,
  que guarda planilhas. Quem envia: só o administrador, pela página `/t/zeladoria/contratos-pdf` (escolhe a pasta, cada
  arquivo vai para o caminho que termina igual; só PDF, até 60 MB: a única rota acima do limite geral de 25 MB do Nexus,
  porque dois contratos têm 27,5 MB e voltavam 413). Quem abre: quem está aprovado, e só o caminho que a cópia cita. O
  PDF que ainda não veio diz isso no botão. **Os 105 estão no servidor desde 06/11/2026** (baixados do Supabase, conferidos
  com o bucket, e enviados pela página; a cópia de garantia fica em `Downloads\Deploy\radar_contratos` no PC do Levi).
  PDF novo de contrato, depois da troca, entra pela mesma página.

## A cópia (até a troca)

1. **Exportar no SQL Editor do Supabase:** a consulta sai de
   `python ferramentas/copiar_zeladoria.py --sql --nomes <de_para_nomes.json>`. Ela é montada na hora porque cita as
   tabelas pelo nome do supervisor, e por isso não fica no repositório. É um SELECT só, que devolve uma célula com o JSON
   dos dados, dos tipos e das chaves; essa célula se salva como arquivo, fora do repositório. Não há papel nem senha no
   banco do Radar.
2. **Ensaiar:** `python ferramentas/copiar_zeladoria.py --arquivo <exportação.json> --nomes <de_para_nomes.json>`. Imprime
   só contagens.
3. **Gravar:** o mesmo comando com `--gravar`, sempre na mesma máquina.

O `de_para_nomes.json` (nomes de colegas → papel) fica fora do repositório, que é público. É o mesmo da limpeza do clone.
Os valores renomeados nos dados são as chaves `previsto_decidido_*` do config, as ações `*equipe` do log e a origem
`planilha_historica`.

O que vai cifrado: todo texto, menos a lista `_CLARO` de `nexus/zeladoria/tabelas.py` (ids, datas, status, usina,
cliente, lugar). Por quê: a API do banco tem leitura aberta, e fornecedor MEI tem nome de pessoa.

## A gravação (etapa 4, 03/11/2026; desligada até a troca)

Liga pelo botão da página da troca (`/t/zeladoria/troca`, só o administrador; seção "A troca"), que guarda a escolha na
pasta de dados da máquina. A variável `NEXUS_ZELADORIA_GRAVA` vence o botão onde existir (`1` liga, `0` desliga). Uma
máquina grava; dois Nexus com estados diferentes apagariam um ao outro. Levi escolheu "Salvo em 1 s, banco logo depois": gravar e conferir o livro do app leva
~8 s (medido), e esperar isso a cada clique travaria a tela.
- **Na hora** (`nexus/zeladoria/gravacao.py`, `Gravador.aplicar`): a mudança entra no estado em memória e no diário
  `<NEXUS_DADOS>/zeladoria/diario.jsonl`, cifrado linha a linha, e o "Salvo" do app acende. Diário que não gravou = 503,
  e a mudança não entrou (o pedaço escrito sai). Ao reler, a última linha pela metade é ignorada (o acréscimo que não
  terminou, sem "Salvo"); linha ruim no meio não se adivinha, e a torre não sobe.
- **Em lote** (`persistir`, pelo laço em thread: 2 s sem mudança ou 20 s seguidos): grava no banco os livros que
  mudaram, pelo `livros.publicar`, e só então esvazia o diário até aquela versão. Banco fora: o diário segura, a
  situação mostra o erro, e o laço tenta de novo, esperando mais a cada falha (até 60 s).
- **Ao subir** (`carregar`): o diário se reaplica por cima do banco, livro a livro pela versão de cada um (a coluna
  `versao` da aba `atualizacao`). Assim, o banco que gravou o livro do app e caiu antes do histórico não perde o
  histórico.
- **Só a diferença** (`ponte.js`): o Radar salva o estado inteiro a cada mudança (o `syncTudo` faz upsert de todas as
  tabelas). A ponte guarda uma cópia PROFUNDA do que leu e manda só as colunas que mudaram, das linhas que mudaram. A
  cópia é profunda porque o Radar muda o JSON no lugar (as pendências do dano, o escopo do contrato, as etapas da rota):
  com a cópia rasa, a pendência marcada não ia ao servidor e o "Salvo" acendia (a revisão de 03/11/2026 achou; provado
  na página real depois da correção). O histórico de valores,
  que o Radar apaga e regrava, vira a diferença das linhas. Na 1ª gravação, a rota da equipe vai uma vez (o Radar
  normaliza as etapas); a prova mostrou que da 2ª em diante só vai o que mudou.
- **Conflito simples:** a mudança de outra pessoa numa linha que você não mexeu fica. Na linha que os dois mexeram, vale
  a última, e o aviso aparece no `showToast` do Radar ("Você e outra pessoa mudaram o mesmo registro"). A versão base é
  a da página aberta (de `/api/eu`).
- **Quem grava:** só quem está aprovado no `perfis`, como no RLS do Supabase. O `perfis` e as `fin_*`, só o HEAD; o
  administrador do Nexus sem linha vale HEAD. A pessoa nova que abre a torre ganha a linha "pendente" (`garantir_perfil`).
  POST de outro site, 403 (a régua `de_outro_site` de `nexus/auth/origem.py`, que morava na moldura até 08/11/2026).
- **Como o Postgres do Radar:** coluna que a tabela não tem e valor fora do tipo (texto em número, "8.5" em bigint) são
  recusados. Sem isso, a coluna sumia calada no lote, e o texto em número derrubava a leitura no boot seguinte.
- **Exclusão:** a definitiva deixa uma linha no `log` (`acao` "excluir-definitivo", `alvo` "<tabela>:<id>", quem, e em
  `obs` o que foi junto). O `ON DELETE` do banco do Radar vale aqui (`CASCATA` em `gravacao.py`): o fornecedor leva as
  cotações, os documentos e os apelidos, e solta (nulo) o fornecedor dos itens e das provisões do financeiro; o
  colaborador leva os documentos; a rodada solta as cotações; o cenário leva os itens. O clone conta com isso: ao
  excluir o fornecedor, ele tira as cotações só do estado dele.
- **O histórico só recebe linha nova:** `log`, `financeiro_historico` e `cronograma_alteracoes` aceitam só linha nova (do
  cronograma, também o `motivo`, que o app preenche depois); o `fin_provisao_historico`, só pelas funções do
  financeiro (no Supabase o insert era revogado). Excluir no histórico é recusado: a trava do catálogo recusaria o lote
  no banco para sempre.
- **Padrões que o banco do Radar dava:** id `bigint` novo = o maior + 1, contando as linhas do mesmo salvamento e sem
  reaproveitar o número que saiu (a resposta devolve os ids, e a ponte os guarda); `criado_em`, o `em` do log e
  `excluido` falso.
- **Leitura e lote sem trava longa:** a mudança troca a lista da tabela em vez de mudá-la (quem lê a antiga não a vê
  mudar), o lote cifra fora da trava, e a carga que falhou (banco fora) volta a mesma recusa por 30 s, em vez de reler
  os três livros a cada pedido.
- **Ficou de fora (baixo):** a linha excluída por uma pessoa e editada por outra, com a página velha, volta só com as
  colunas editadas (no Supabase voltava inteira).
- **As funções do financeiro** (`nexus/zeladoria/financeiro.py`): `fin_promover`, `fin_definir_fornecedor` e
  `fin_editar_provisao`, portadas do SQL do Radar (`docs/financeiro/*.sql`), com a mesma regra e a mesma mensagem. Cada
  uma vira um salvamento só (`Gravador.chamar`): tudo ou nada.
- **A cópia não passa por cima:** depois que a torre gravou (versão do banco acima de 0), `copiar_zeladoria.py --gravar`
  recusa. O `--forcar` só com o servidor parado e o diário vazio; senão o diário se reaplica por cima da cópia.

## Como provar

- `python -m pytest tests/test_zeladoria_*.py -q`, com o `.env`, para o `test_sem_nomes_no_repositorio.py` rodar junto.
  `tests/zeladoria_ponte_node.js` prova a ponte no node, nos dois modos.
- A gravação na cópia de prova: suba com `NEXUS_ZELADORIA_GRAVA=1` e `NEXUS_DADOS` numa pasta de rascunho. A cópia de
  prova recusa toda gravação fora da máquina, então o banco de verdade não é tocado, e a prova mostra também o banco
  fora do ar: o "Salvo" acende, a situação diz o erro, e o diário segura e se reaplica ao reiniciar. 1ª prova
  (03/11/2026): editar um fornecedor mandou só `id,obs` (124 bytes); reiniciar manteve a versão 3; editar provisão com o
  dado real gravou as duas linhas do histórico, e a terceira chamada, igual, voltou "nada mudou".
- A tela na cópia de prova (`ferramentas/subir_copia_de_prova.py`), em desktop e em 375 px.
- Os totais da Visão Geral, do Financeiro e do Farol Contratual iguais aos do Radar no ar, com a mesma exportação.

## A 1ª medida (03/11/2026)

- **Cópia de 06/11/2026:** a exportação das 12:16 UTC, 5.148 linhas nas 41 tabelas mais 120 últimas rondas, gravada em 20 s; as 42 abas iguais à origem. O Radar NÃO congelou: ganhou as tabelas `zeladoria_contratual` (o que o contrato de cada cliente pede: lavagens e roçagens por ano, a regra) e `zeladoria_contratual_docs` (o índice dos PDFs dos contratos), que o Radar no ar já usa e o clone ainda não mostra. A cópia parou nelas (tabela fora do mapa não entra calada); foram registradas no `tabelas.py` para o dado ficar no Nexus antes da restrição do Supabase em 10/11.
- **Cópia de 03/11/2026:** a exportação das 17:07 UTC, 4.756 linhas nas 39 tabelas mais 117 últimas rondas, gravada em 13,8 s; as 40 abas têm no Nexus as mesmas linhas da origem. A maior célula é a do retrato do cronograma (86 mil caracteres), que vai partida em 3. 86 valores com nome foram renomeados (config 2, log 7, origem dos serviços 77).
- **Tela:** na cópia de prova (porta 5172), a Visão Geral, o Financeiro e a Criticidade abriram com o dado real, sem erro no console. Em 375 px, o menu do Nexus vira o botão Menu, e o clone se ajusta.

## O visual (etapa 3, 03/11/2026)

- **Paleta: a do Nexus.** A 1ª versão tinha as três cores do Levi (preto, azul e lima); vendo a tela, ele pediu (03/11/2026) "bote aquele azul nexus para ficar no padrão nexus de planilha e cards". A rota `/app` põe no clone os blocos de token do próprio `nexus.css` (`tokens_do_nexus`, com o seletor do clone para vencer o CSS dele), e o bloco `zeladoria-paleta` aponta cada variável do Radar para um token (`--bg` = `--fundo`, `--surface` = `--superficie`, `--accent` = `--verde`); o `--info` tem o mesmo nome nos dois e vem do Nexus. Token que muda no `nexus.css` muda aqui junto. O botão é o retângulo do `gc-btn`, não a pílula do Radar.
- **Tema:** o `<html>` do clone nasce com o `data-theme` (o do Radar) e, no claro, o `data-tema="claro"` (o do Nexus), e o botão do topo troca os dois ao vivo (o aviso `nexus.tema` no navegador).
- **Fontes:** as do Nexus (Poppins, Raleway nos títulos e IBM Plex Mono).
- **Cores fixas:** a do CSS e a de aviso dos estilos do JavaScript viraram variável. A cor de DADO (o avatar de cada pessoa, a escala de dias de atraso, o calor da criticidade) e o CSS do relatório de impressão (papel branco) ficam como estavam.
- **Emojis:** saíram. O que era o botão inteiro virou palavra (Excluir, Editar, Fotos, Simular...).
- **Visão de 75% no desktop** (Levi, 05/11/2026: "a mesma visão que tenho quando o zoom está em 75%, fica tudo bem mais encaixado"): `zoom: 0.75` no `<html>` do clone a partir de 1000 px; a casca do Nexus fica como está, e o tablet e o celular ficam no tamanho de sempre.
- **Carregamento discreto:** a tela inteira com o G do Radar saiu (Levi, 05/11/2026: "tire esse carregamento feio"); no lugar, a linha "Carregando a Zeladoria…". Cada tela do menu abre o clone de novo, então ela aparece a cada troca de tela (~0,6 s na cópia local).
- **Card do fornecedor:** a coluna da grade foi de 272 para 320 px, o nome quebra a linha e os botões descem quando não cabem (o texto passava do card).
- **Celular:** a 375 px nenhuma das 18 telas rola de lado. A tabela larga rola dentro dela, a grade fixa cai para uma coluna e a linha de botões quebra.
- **Como se faz:** tudo pela `ferramentas/zeladoria_limpar_clone.py` (a função `vestir`), que roda de novo sobre o Radar original. Prova: `tests/test_zeladoria_clone.py`.
- **Os filtros num painel suspenso** (Levi, 06/11/2026: "quero que todos os filtros sejam suspensos alá histórico de OS do
  OS Creator!"): o modelo A do Histórico de OS (`nexus/torres/oscreator/README.md`, "Os filtros do Histórico só valem no
  Aplicar"). Na barra ficam a busca (filtra enquanto se digita) e o botão Filtros com a contagem; o painel tem cada filtro
  numa lista digitável (sem acento nem caixa), o ponto verde no que mudou, o Limpar e o Aplicar; nada filtra antes do
  Aplicar; as etiquetas azuis dos aplicados ficam abaixo, o × tira um na hora, e o "Limpar tudo" é o "Limpar filtros" do
  próprio Radar. Fechar sem aplicar (Esc, clique fora) descarta. No celular, folha de baixo para cima.
  - **De fora do clone, pelo DOM** (`nexus/static/zeladoria/filtros.js` e `.css`, que a rota `/app` põe depois da ponte):
    o estado do Radar mora dentro de uma função, então a peça esconde os `<select id="flt-*">` e as listas de vários
    valores (`.msf`), monta o painel com cópias, e no Aplicar escreve nos campos escondidos e dispara o `change`, um por
    vez (o Radar refaz o `#app` a cada um; um MutationObserver remonta a barra). Filtro novo com id `flt-*` entra sozinho.
  - **Ficam fora:** a busca de texto, e os campos que escolhem o que a tela mostra (`FORA`: o usuário em Permissões, o
    "Previsto adotado" e o mês da simulação de repasse).
  - **O desenho é o do Histórico com as cores do Nexus** (`zf-*` espelha o `fl-*` do `os.css`): mudou o modelo de lá,
    leve aqui. Prova: `tests/test_zeladoria_filtros.py` (o que a peça supõe do clone e a cor só por token) e as 18 telas
    na cópia de prova (abrir, digitar, aplicar, etiqueta, ×, Esc, Limpar tudo e as listas de vários valores do Financeiro).

## O Fracttal e o cronograma (etapa 5, 06/11/2026)

O Radar tinha duas funções no Supabase que não são do app: a `fracttal-sync` (lê as rondas no Fracttal a cada 2 h) e a
`cronograma-api` (o link do cronograma para o app central). As duas passam para o Nexus.
- **As rondas** (`nexus/zeladoria/rondas_fracttal.py`): a mesma regra da `fracttal-sync`. A cada 2 h relê as OS criadas
  desde o último corte menos 1 dia até amanhã (`work_orders`, 100 por página, até 12 páginas), fica com as que são ronda
  (`eh_ronda`: "ronda" na descrição, ou "inspeção" com a tarefa de zeladoria), grava só as rondas que mudaram e refaz a
  última de cada usina (a view `rf_fracttal_ultimas`: a última não cancelada, a nota da última com nível e o total). A
  linha `fracttal_sync` guarda o corte, a última volta e o último erro. Grava pelo gravador (`interno`, quem é o
  sistema), num salvamento só; as três tabelas não deixam rastro de exclusão nem aviso de "mexeram no mesmo registro".
  - **Só com a gravação ligada.** O laço sobe com o gravador (olha a cada 10 min, `fundo:nexus-zeladoria-rondas` no
    porteiro do Fracttal, porque a cota de 200 pedidos por minuto é da empresa). Até a troca, as rondas são as da cópia
    do Radar, e o botão do app diz isso no aviso dele.
  - **Limite do Fracttal** ("excesso de pedidos"): a volta para, o erro fica na linha `fracttal_sync`, e o corte não
    anda (nada se perde; a próxima volta relê). Outro erro: "O Fracttal não respondeu agora".
  - **Prova com o dado real (06/11/2026):** a regra da última de cada usina deu as 120 linhas da view do Radar, coluna a
    coluna; a chave da usina, 1.416 de 1.416; uma leitura de verdade no Fracttal trouxe 41 rondas, e as 28 que a cópia
    também tinha saíram iguais.
- **O cronograma** (`nexus/zeladoria/cronograma_api.py`, rota `GET /t/zeladoria/api/cronograma`, pública em
  `auth.ROTAS_PUBLICAS`): a mesma resposta da `cronograma-api`, campo a campo (fonte, atualizado_em, serviços, usinas
  com histórico e próximos, a situação em_execucao, confirmado ou previsto e o atrasado pelo dia de Brasília), e os
  mesmos filtros (`usina` contém, `cliente` e `uf` iguais, sem acento; `historico_desde`). Vale a chave no header
  `x-api-key`, igual à `NEXUS_ZELADORIA_CRONOGRAMA_CHAVE` (Base → Chaves das fontes → aba Nexus, ou o .env). Sem a chave,
  503 "ainda não configurada", como no Radar. Não mostra quem executa, valor, fornecedor nem documento.
  - **De onde vem:** do retrato que o próprio app publica em `cronograma_publico` (as regras do cronograma vivem no
    clone, `snapshotCronograma`). O clone publica a cada página aberta, com a hora nova: o gravador só regrava quando o
    cronograma muda (`gravacao.RETRATO`), senão cada clique no menu gravaria 86 mil caracteres.
  - **Quem lê:** em 06/11/2026 ninguém. A chave nunca foi posta no Supabase (a função respondia 503), então não há quem
    trocar de endereço. Quem for ler recebe o endereço do Nexus e a chave; perguntar ao supervisor que pediu o link quem
    é o app central. Prova com o dado real: o retrato do banco do Nexus deu 91 usinas.

## A troca (11/11/2026)

O Supabase do Radar estourou a cota de arquivos grátis (3,1 GB de 1,1 GB, pelas fotos e vídeos dos outros apps da mesma
organização) e passou a recusar todo pedido (402) até 10/12/2026: login, banco e arquivos. O site
`zeladoria.gridco.com.br` ainda abre, mas não entra. O painel do Supabase continua lendo o banco pelo SQL Editor.
- **A última cópia:** a exportação de 12/11/2026 às 02:29 UTC, pelo SQL Editor, no Chrome do Levi: 6.210 linhas nas 41
  tabelas mais 121 últimas rondas (em 06/11 eram 5.148), sem tabela nova; o cronograma tinha sido publicado às 19:40 UTC
  de 11/11, minutos antes de o Supabase parar. A exportação e o Radar original desse dia ficam fora do repositório
  (`Downloads\Deploy
adar_2026-10-28
  (`Downloads\Deploy
adar_2026-10-28
  (`Downloads\Deploy\radar_2026-10-28\radar_exportacao_2026-11-11.json` e `Downloads\Deploy\radar_2026-11-11\`).
adar_2026-11-11\`).
adar_2026-11-11\`).
- **O nome que a trava pegou:** a cópia parou num investimento do financeiro com o nome de uma pessoa ("… (anual)", 12
  parcelas), num campo que ia em claro. O `investimento` passou a cifrado (`tabelas._CLARO`); a leitura aceita o texto em
  claro da cópia antiga (só decifra o que está cifrado), então o código novo sobe ANTES da cópia nova.
- **O Radar de 11/11 no clone:** o Financeiro abre na Visão executiva, o relatório dos primarizados, o lançar no
  financeiro, a vala de drenagem e a mudança de nível na Criticidade, entre outros (1.181 linhas novas). Duas trocas novas
  na ferramenta: a lista de e-mails que mostrava o "Mês a mês - Geral" a uma pessoa virou "só o HEAD" (o e-mail não entra
  no repositório; a ferramenta para se sobrar e-mail da empresa), e a cor de reserva em `rgb()` sai como a em `#hex`.
- **A função nova do financeiro:** `fin_editar_motivo` (corrigir o motivo de uma alteração já feita; o 1º motivo fica em
  `motivo_original`; quem fez edita a dela, o HEAD qualquer uma), em `financeiro.py`, com a mesma regra e a mesma
  mensagem do banco. As outras três foram conferidas com o banco de 11/11: iguais às portadas.
- **A página da troca** (`/t/zeladoria/troca`, só o administrador, com o atalho "Ligar a gravação" na faixa da tela): a
  gravação nesta máquina, a cópia do banco (de quando é o dado) e o estado do gravador. Ligar exige a cópia inteira e
  legível, e sobe o gravador na hora (com ele, as rondas do Fracttal). Ligue no servidor, não na 5070.
- **Quem entra** (Levi, 11/11/2026: "Aprovado no Radar entra"): quem está aprovado no `perfis` da cópia vê a Zeladoria
  no Nexus sem precisar de setor (`nexus/zeladoria/acesso.py`, chamado pelo portão em `nexus/auth/setor_telas.acesso`):
  sem setor, vale como do setor Zeladoria; com outro setor, ganha as telas da Zeladoria. O HEAD aprova na tela Usuários,
  como no Radar. O portão nunca espera o banco: usa a cópia em memória e recarrega por trás (15 min sem a gravação).
  Ainda depende de a pessoa entrar no Nexus (login do Fracttal, ou a conta Microsoft quando a T.I. ligar).
- **Feita em 12/11/2026:** o código subiu (`afad133`), a cópia de 11/11 foi gravada (42 abas iguais à origem, conferidas
  lendo de volta) e a gravação foi ligada no servidor às 03:33 UTC. A 1ª volta das rondas do Fracttal rodou na hora, sem
  erro (o livro `_fracttal` foi à versão 1). Desde então o Nexus é a casa da zeladoria, e a cópia do Supabase recusa
  passar por cima.

## Como entregar (quem programa a Zeladoria)

O HEAD da zeladoria (quem criou o Radar) programa a Zeladoria no Nexus desde 11/11/2026, com o papel **admin** no
GitHub, por decisão do Levi ("Direto na main"): sobe direto na `main`, sem pull request, e a `main` vai para produção
sozinha em ~2 min, com o servidor reiniciando. Antes de subir:
1. Leia este `CLAUDE.md` e o `CLAUDE.md` da raiz (as regras do Nexus inteiro).
2. `python -m pytest tests/test_zeladoria_*.py -q` passando (com o `.env`, para a trava de nomes rodar junto), e a tela
   conferida no navegador, no computador e a 375 px.
3. O repositório é público: nada de nome de colega, e-mail, dado de cliente ou segredo em arquivo versionado (cite pelo
   papel: "o HEAD", "o supervisor da equipe"); cor só por token; sem emoji; tudo em pt-BR.
4. O clone (`clone/radar.html`) agora se edita direto. O dado mora no banco do Nexus (os três livros `nexus_zeladoria_*`,
   pelo gravador): nada de Supabase, planilha ou JSON como banco. Tabela nova entra em `nexus/zeladoria/tabelas.py` e no
   catálogo antes da 1ª gravação (`nexus/dados/CLAUDE.md`).

## O que falta

- **Usinas ligadas ao cadastro** (a etapa 6 do desenho): a usina do Radar casada com a do `cadastro_nexus` pelo ID.
- **O endereço antigo:** `zeladoria.gridco.com.br` ainda serve o Radar, que não entra mais. Quem cuida da hospedagem dele
  (o HEAD da zeladoria) troca a página por um redirecionamento para `app.gridco.com.br/t/zeladoria/visao-geral`.
- **Pessoa nova do time:** quem nunca abriu a Zeladoria não está no `perfis`; sem setor no Nexus, não chega à torre para
  pedir acesso. Por enquanto o administrador põe o setor Zeladoria em Base → Acessos.
