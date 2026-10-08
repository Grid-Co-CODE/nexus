# OS Creator Web — clone dentro da torre OS Creator

Cópia do OS Creator Web que roda no supervisório de O&M: o serviço `os_creator/os_web` do repositório `oem`,
na porta 5090, publicado em `/os/*` pela plataforma. Foi trazida para cá em 30/09/2026, a pedido do Levi: "clone o
OS Creator Web que está no meu supervisório de OEM para a pasta do OS Creator do Nexus".

## De onde veio

- A origem é `C:\GridcoBuild\oem`, branch `pcm-no-oem`, **com o que ainda não foi commitado lá**: 35 arquivos nunca
  commitados e 32 alterados. É a versão que está no ar no supervisório, e não a do `main` do oem.
- O caminho relativo é o mesmo dos dois lados: `oem/<x>` → `nexus/torres/oscreator/<x>`. Por isso o código roda sem
  mudança:
  - o serviço sobe com a pasta atual em `os_creator`;
  - o `chamado_insp_spec` acha o `chamado_garantia` na pasta de cima.

## O que veio (120 arquivos, 1,6 MB)

- O `os_web` inteiro: 35 módulos, os templates, o static e o relay.
- Os 23 módulos do OS Creator que ele importa, direta ou indiretamente (inclusive dentro de função):
  - `api.py`;
  - as specs de chamado, inspeção, COS e solicitação;
  - os stores de modelos, observações e temas;
  - `gridco_abas`;
  - os `tickets_*`;
  - `steps/engenharia` e `steps/ui.py`.
- O pacote `chamado_garantia`, com o `assets/` (ícone, logo e fontes) e o `requirements.txt`.

## O que ficou de fora de propósito

| Arquivo | Por quê |
|---|---|
| `fracttal_login.txt` | é o login salvo do desktop |
| `assets_cache.json` | é o catálogo de ativos, dado que já vazou uma vez por instalador público |
| `tokens.txt`, `gridco_sql_token.txt` | são segredo; o código lê da variável `GRIDCO_SQL_TOKEN` ou de `%APPDATA%` |
| `app.py`, `main.py`, as outras telas de `steps/` | são o app de desktop (PyQt), e a web não usa |
| `.bat`, `.spec`, documentos | não fazem parte do serviço |

## Como foi conferido

- Original e clone foram rodados lado a lado, cada um num processo limpo:
  - os 58 módulos importam;
  - as 111 rotas são iguais;
  - `/os/login` responde 200, `/os/` responde 302 (vai para o login), e ícone e CSS respondem 200;
  - o clone não carrega nada de fora desta pasta.
- A suíte do Nexus continua com 206 testes passando.
- O repositório é público, então a cópia passou antes por uma varredura:
  - não achou CPF, telefone, token nem chave;
  - os únicos e-mails são 6 contatos de garantia de fabricantes, que já estão públicos no oem.

## Ligado ao Nexus (30/09/2026)

O Nexus serve o clone em `/os/*`, **dentro do próprio processo**, sem segundo serviço. A ponte fica em `ponte.py`,
nesta pasta.

- **Login:** a ponte é uma rota do Nexus, então quem não entrou no Nexus para no portão dele. Depois disso, o login
  do Fracttal é o do próprio OS Creator, por pessoa. Quando o JWT do Fracttal vence e não renova, o clone respondia com o aviso do app de
  desktop ("cole um novo em fracttal_login.txt"); a ponte troca isso por voltar ao login do OS Creator, limpando o
  cookie dele, e depois volta à mesma tela (pedido de dados recebe 401 com `login: true`). Levi, 05/10/2026.
- **Telas da torre:** cada uma (`/t/os/<tela>`) leva ao OS Creator na seção dela.

  | Tela da torre | Abre em |
  |---|---|
  | Início | `/os/` |
  | Histórico de OS | `/os/historico` |
  | Ativos Fracttal | `/os/ativos` |
  | Performance | `/os/performance` |
  | COS | `/os/cos` |
  | PCM | `/os/setor/pcm` |
  | Chamados | `/os/chamados` |
  | Engenharia | `/os/engenharia` |
  | Solicitação | `/os/solicitacao` |
  | Clonagem de OS | `/os/clonar` |

  O "Setores" virou um item por setor e entrou "Ativos Fracttal" (Levi, 04/10/2026). Cada setor abre o mesmo
  endereço do card dele na tela inicial do OS Creator. Com `?abrir=/os/...`, a moldura abre nesse endereço (só
  `/os/...`; o resto cai no destino da tela) e a casca do OS Creator o põe numa aba: é por onde o card da OS aberto em
  outra torre leva ao "Clonar esta OS" e ao "Abrir chamado" (seção "O card da OS em qualquer torre").
- **Menu lateral → aba nova** (Levi, 04/10: "os botões laterais devem contribuir em adicionar novas abas também na
  tela acima"). Com a casca do OS Creator de pé, o clique no menu não recarrega a página: manda à casca
  `{nexusOs: 1, url, rotulo}` e ela abre a tela numa aba nova (ou reativa a que já existe). A porta é posta no
  `abas.js` pela ponte (`_OUVIR_NEXUS`) e só ouve a janela-mãe; a ETag do abas.js ajustado leva o hash do conteúdo,
  para o navegador largar a versão anterior. Sem a casca (login do Fracttal na tela), o clique abre a página normal.
  Provado num ensaio com o abas.js ajustado de verdade: 2 abas novas, repetir não duplica, "/os/" volta ao Início.
- **Toda troca da ponte passa por `_trocar`**, que acha o trecho com LF ou CRLF. Num clone do Windows (git com
  `core.autocrlf`) o clone sai em CRLF, e a troca com LF não achava nada, sem erro: no ensaio da T.I. de 05/10, a
  porta do menu lateral não entrava no abas.js. Trecho novo com quebra de linha? Use `_trocar`, nunca `replace`.

- **Dentro da casca do Nexus, com o menu lateral** (Levi, 30/09). Cada tela da torre mostra o OS Creator numa
  moldura. Até então abria em tela cheia, porque o clone usa `window.top` para saber se é a casca. Numa moldura, isso
  quebrava duas coisas: as abas dele não ligavam, e o login dele tomava a janela. A ponte troca, na resposta,
  `window.top` por `window.__osTopo()`, que é a janela mais alta que ainda é do OS Creator. Fora do Nexus, essa
  janela é o próprio `window.top`, então nada muda no supervisório. Se o oem mudar esses trechos, os testes da
  moldura acusam.
- **Topo do OS Creator no Nexus** (Levi, 04/10): sem o "← Plataforma" (o menu lateral já leva a qualquer lugar) e sem
  o símbolo e o "Grid Co." (o topo do Nexus já tem); fica só o "Sistema de Ordens de Serviço", centralizado. As
  páginas do Nexus também saem de qualquer moldura. A troca é feita na resposta, pela ponte, para o clone continuar
  idêntico ao do oem.
- **Sincronizado com o oem em 04/10:** `os_web/templates/solic_fila.html` (a Fila do PCM dava 500: pedia
  `p.id_account`, campo que a lista de responsáveis não tem; o oem corrigiu em 02/10 para `id_personnel`). Era o
  único arquivo diferente entre o clone e o oem.
- **Sessão:** a chave da sessão do clone é derivada da `NEXUS_SECRET_KEY`. Não é a do supervisório e não precisa de
  segredo novo. O cookie continua `os_sessao`, só em `/os`.
- **Quando sobe:** o clone só sobe na primeira visita ao `/os/`. Se ele quebrar (faltou PyQt6, por exemplo), o
  `/os/*` mostra um aviso e o resto do Nexus segue.
- **Testes:** `tests/test_torre_oscreator.py`, `tests/test_oscreator_solic_engenharia.py`,
  `tests/test_oscreator_busca_digitavel.py`, `tests/test_oscreator_desempenho.py` e `tests/test_oscreator_card_tarefas.py`.
  Nenhum teste fala com o Fracttal.
- **O que não funciona igual:**
  - o login pelo OAuth do Fracttal tem a volta configurada para o supervisório; e-mail e senha funcionam normal;
  - gravar ticket precisa do `GRIDCO_SQL_TOKEN`, que vem da variável ou do `%APPDATA%` da máquina.

## Nova solicitação: PCM ou Engenharia (06/10/2026)

O pedido do Levi, de 06/10: em "Nova solicitação" aparecem duas opções. **PCM** continua criando a solicitação do
Fracttal (`/os/solicitacao`). **Engenharia** é uma tela nova (`/os/solicitacao/engenharia`), no estilo de
Performance > Geração e ETM > ETM, só que liberada para todos os ativos. As duas telas têm no topo o seletor
PCM | Engenharia. As duas são do mesmo setor das abas (`/os/solicitacao`), então o seletor troca a tela na mesma
aba, sem abrir outra.

- **O que a Engenharia cria:** uma OS por ativo marcado (o padrão) ou, desde 08/10, uma OS com todos os ativos, uma
  atividade por ativo (seção "Engenharia: OS agrupada e anexos"). **Não** cria uma solicitação. Segue o molde da OS de
  análise (`api.create_os_analise`):
  - tipo de tarefa `Administrativa` e **só a Classificação 1, `Programada`** (pelo nome, via `_classif_ids`), sem
    plano. Levi, 06/10: "o tipo de tarefa seria administrativa e class1 é programada!". A Classificação 2 fica vazia: a
    tela vale para qualquer ativo, e "Elétrica" não serve a uma cerca;
  - **as etiquetas `Remoto` e `ENGENHARIA`, sempre, e só elas** (os nomes como estão no catálogo; o Levi confirmou que
    a "Remoto" existe). Nem `PERFORMANCE` nem `Dar prioridade` no urgente. Levi, 06/10: "Etiqueta de remoto e
    engenharia fixas sempre! só essas etiquetas viu, sem performance".
    - Casam pelo nome **exato** (`solic_eng_web.etiquetas`), sem acento e sem caixa. A busca por trecho do
      `label_id_por_nome` tomaria a "Religamento Remoto" pela "Remoto".
    - As etiquetas são conferidas **antes** de criar. Faltando uma no Fracttal, nenhuma OS sai, e a tela diz "Não achei
      no Fracttal a etiqueta Remoto. Nenhuma OS foi criada.";
  - título `[Ativo] - Descrição`, montado pelo `perf_os_nome` em cada ativo (na OS agrupada, o de cada atividade);
  - a "Descrição" é a atividade que o solicitante escreve, com o subtexto "Atividade a ser realizada (de forma
    direta)";
  - o "Descreva o problema" (obrigatório) vai na observação (`note`); na OS agrupada, na de cada atividade, que é o que
    o `create_work_orders_agrupada` grava (como no Tradicional).

  O plano ficou de fora porque as telas da Performance dependem do plano do Fracttal, que só inversor, ETM e usina
  têm.
- **Bloco 1:** Cliente | Usina, e embaixo Filtrar | Tipo de ativo, cada um da largura do de cima.
  - O tipo de ativo aceita digitação (`data-busca`).
  - A sigla do cadastro aparece com o nome, por exemplo NBRK → Nobreak. O mapa é `NOME_TIPO`, em `solic_eng_web.py`,
    e foi tirado dos rótulos dos próprios ativos: 57 tipos numa usina do catálogo.
  - Ficaram com a sigla NCU e RSU, dos trackers, porque o cadastro não dá nome a eles. Tipo novo com sigla aparece
    como veio; para dar nome, é uma linha no `NOME_TIPO`.
- **Data do evento: editável, com o padrão "agora", como na ETM** (Levi, 06/10: "você sumiu com data do evento, tem
  que ter data do evento"). Ela vai no `event_date`. O servidor recusa data inválida e evento no futuro (com folga de
  5 min), porque o evento já aconteceu. A programada **não** conta do evento: conta da criação.
- **Data programada: 7 dias depois da criação, ou 2 com o "Urgente" (em vermelho), e NÃO se edita** (Levi, 06/10:
  "data programada não deve ser possível editar!").
  - A tela só mostra a data: não há campo. A base é a hora do servidor quando a página abriu, e o relógio dela anda a
    cada 30 s, para a data mostrada continuar sendo a que vai valer.
  - Quem põe a data é o servidor, na hora de criar (`data_padrao`). Uma `programada` que venha no pedido é ignorada.
  - A resposta diz a data posta: "… — programada(s) para 13/10/2026 17:51.".
- **Responsável:** digitável (o componente comum, seção abaixo), só entre os nomes da Engenharia. Os nomes ficam no `.env` (`OS_WEB_ENGENHARIA_RESPONSAVEIS`,
  separados por `;`), **nunca no código**, porque o repositório é público.
  - O nome casa pelo primeiro nome igual e por todos os pedaços dele como palavras inteiras, sem acento: "Ana Teste"
    casa com "Ana Teste da Silva", e "Bruno" não casa com "Brunoso".
  - O servidor confere o responsável de novo no criar.
  - Sem a variável, a tela avisa. Nome sem ninguém no Fracttal aparece como "Não achei no Fracttal: …".
  - Nome que casar com duas pessoas põe as duas no menu. Aí basta escrever o nome completo no `.env`.
- **No servidor da T.I.:** o `.env` do OS Creator precisa da linha `OS_WEB_ENGENHARIA_RESPONSAVEIS=...`. Sem ela, a
  tela abre mas não deixa escolher responsável.
- **Arquivos:**
  - `os_web/solic_eng_web.py`: as regras, puras, sem Flask;
  - `os_web/rotas_solic_eng.py`: a tela, a cascata e o criar;
  - `templates/solic_eng.html`, `static/solic_eng.js` e `static/solic_eng.css`;
  - o seletor no `templates/solic.html`;
  - no `static/os.css`, a linha do topo que quebra no celular. Com o seletor, 375 px cortavam o "Engenharia".
- **Como provar:** `tests/test_oscreator_solic_engenharia.py` (catálogo e pessoas sintéticos, sem rede; os testes da OS
  agrupada e dos anexos estão na seção seguinte). Na bancada, com o criar de mentira, foram conferidos (06/10):
  - 353 ativos de uma usina do catálogo;
  - "nob" no tipo → Nobreak;
  - a data só exibida, com o Urgente trocando 13/10 por 08/10;
  - o pedido saindo sem data e a resposta com a data do servidor;
  - as recusas do servidor (sem ativo, sem nome, sem problema, responsável de fora);
  - o seletor nas duas telas.

  **Falta a prova ao vivo** pedida no `CLAUDE.md` do OS Creator: uma OS de verdade em `TESTE - PA`, conferida campo a
  campo no Fracttal e cancelada no fim.

## Engenharia: OS agrupada e anexos (08/10/2026)

Os pedidos do Levi, de 08/10: "Agrupar ativos em atividades por OS" e "Engenharia poder anexar arquivos".

- **Uma OS por ativo × uma OS com todos os ativos:** a escolha fica no bloco 2, antes da tabela (numa usina grande são
  centenas de linhas), com o padrão em "Uma OS por ativo", o comportamento de antes.
  - A agrupada sai pelo `api.create_work_orders_agrupada`, o mesmo do "Agrupar em UMA OS" do Tradicional: cada ativo
    vira uma atividade (tarefa) com o seu `[Ativo] - Descrição`, todas numa OS só. As regras da seção acima valem
    iguais: Administrativa, só a Classificação 1, só `Remoto` + `ENGENHARIA`, as duas datas e o responsável do `.env`.
  - Com um ativo só, as duas escolhas dão a mesma OS: vai pelo caminho de sempre.
  - A OS que não fecha (o Fracttal recusa o `work_order_insert`) deixa as atividades pendentes lá. A tela diz isso e
    manda gerar a OS no Fracttal; a resposta é 200, para os ativos saírem da seleção (um 2º clique criaria tudo de novo).
- **Anexos:** PDF; imagem (JPG, JPEG, PNG, WEBP, GIF, BMP); planilha (XLSX, XLS, CSV, ODS); documento (DOCX, DOC, ODT,
  TXT). Até 5 arquivos, 10 MB cada e 20 MB no total. A tela mostra os tipos e os limites, com os números do servidor
  (`solic_eng_web.py`), que confere tudo de novo. Tipo novo é uma linha no `TIPOS_ANEXO`.
  - Sobem pelo **mesmo caminho do anexo de hoje**, o `api.attach_imagem_os` (s3_object_post, S3,
    `work_orders_tasks_files_insert`; o das imagens da Performance e do Tradicional), **depois** de a OS existir, na 1ª
    tarefa de cada OS. Uma OS por ativo: cada anexo vai para cada OS. Agrupada: uma vez, na OS (o card junta as tarefas).
  - **Nada é criado antes de os anexos passarem:** tipo, tamanho, quantidade, total e o conteúdo. O conteúdo é conferido
    porque a extensão é só o nome: um executável chamado `.pdf` iria para o Fracttal, onde qualquer um baixa. O `.xls` e
    o `.doc` antigos aceitam também texto (sistema que exporta HTML com nome de `.xls`).
  - O nome vira a chave no S3 (`.ot/<OS>/<nome>`): barra, `#`, `?`, `%` e `+` viram `_`, e o repetido ganha " (2)" (o
    segundo apagaria o primeiro).
  - **Limite de envios:** com uma OS por ativo, cada anexo sobe para cada OS, e cada envio custa 2 pedidos ao Fracttal
    (cota da empresa) mais o arquivo. Até 30 envios e 100 MB por criação; passou, a tela pede a agrupada ou menos anexos,
    e nada é criado. Os envios vão 4 de cada vez, pelo `_ExecutorComContexto` (leva a sessão para as threads).
  - **A tela diz o que subiu e o que falhou**, arquivo por arquivo e OS por OS ("• relatório.pdf (293 KB): subiu nas OS
    15000 e 15001; falhou na OS 15002 (…)"), em vermelho se algo falhou. Anexo que falha não desfaz a OS, e nenhum erro
    escapa: uma sessão que cai no meio vira a falha daquele envio, e a resposta continua dizendo quais OS nasceram.
  - **O tamanho do pedido:** o app aceita 4 MB (`MAX_CONTENT_LENGTH`, das imagens do Tradicional). Só o criar da
    Engenharia abre para 21 MB, por pedido (`request.max_content_length`, do Flask 3.1). No Nexus, a ponte não lê o
    corpo, e os 25 MB dele não atrapalham. Num Flask mais velho valem os 4 MB, e a recusa sai em JSON.
- **Sincronizar sem reiniciar:** a ferramenta troca os arquivos, mas o serviço (5090 ou Nexus) segue com o Python e o
  HTML de antes na memória até reiniciar, e o `.js` já é o novo. O `.js` só liga a agrupada e os anexos quando o HTML
  trouxe os limites do servidor (`NOVO`); até lá a tela funciona como antes. Sem isso, um elemento que faltasse parava a
  tela inteira, e o "Uma OS com todos os ativos" iria a um servidor que não o conhece (sairia uma OS por ativo).
- **Como provar:** `tests/test_oscreator_solic_engenharia.py`, 36 testes, com o Fracttal falso e a rede bloqueada (pedido
  que escapasse dos dublês derrubaria o teste): tipos e conteúdo, limites, nome seguro, limite de envios, a falha de um
  anexo na tela, a OS sem número que fica sem anexo, o anexo recusado sem OS nenhuma, a agrupada com as regras de
  sempre, a que não fecha, o 413 em JSON, os 9 MB que passam do limite do app e o multipart pela ponte do Nexus. A
  suíte do oem (`test_os_web_*.py` e `test_anexo_documento.py`, 681) passa com os arquivos novos, numa cópia fora dele. Na bancada (o clone sozinho em `127.0.0.1:5097`,
  Fracttal falso e rede bloqueada), num navegador a 1280 e a 375 px: 3 OS × 2 anexos (6 envios, nome com acento, bytes
  conferidos), a agrupada com um anexo que falha (tela vermelha), as recusas do navegador (`.exe`, 11 MB, o 6º arquivo,
  40 envios), o tirar com o foco no lugar, sem rolagem lateral, e os dois casos de servidor não reiniciado (HTML de antes
  com o `.js` novo; HTML novo sem os limites): a tela cria como antes, sem erro de JavaScript.

  **Falta a prova ao vivo:** uma OS por ativo e uma agrupada de verdade em `TESTE - PA`, com um anexo de verdade,
  conferidas no Fracttal (o anexo abre no card) e canceladas no fim. E o 5090 precisa ser reiniciado para valer.

## Digitar para achar: responsável e usina (08/10/2026)

O pedido do Levi, de 08/10: "Conseguir digitar no responsável na criação de OS" e "Conseguir digitar o nome da usina no
filtro do histórico".

- **Um componente só, o `static/os_busca.js`** (o CSS é o bloco "busca dentro do <select>" do `static/os.css`). O
  `base.html` o carrega em toda tela. A tela não tem busca própria: marca o `<select>` com `data-busca="1"`, e ele
  ganha a caixa por cima. O `<select>` continua no formulário, escondido, com o mesmo id, name e values: o que vai ao
  servidor não mudou.
- **Por que não digitava:** o responsável chega por fetch, depois da tela pronta. O `<select>` nascia com uma opção só
  ("carregando…"), e a regra "6 opções ou mais vira busca" não o pegava. Ficava o nativo, sem digitar, em Performance
  (Geração e ETM e os outros planos), em Nova solicitação · Engenharia e no "trocar" responsável do card da OS. A
  Clonagem tinha um filtro dela, separado do `<select>`: com a busca comum por cima, eram duas caixas. Saiu.
- **Onde vale:** Performance, Engenharia, Clonagem, Inspeção de chamados, PCM, COS ("Requerido por"), a Fila do PCM
  (aprovar e criar), a Solicitação (técnico sugerido) e o trocar responsável. A Tradicional segue com a lista dela no
  Passo 4, que já se via inteira: passou a casar do mesmo jeito (`OsBusca.casa`) e a aceitar setas e Enter. O Enter só
  escolhe; quem gera as OS continua sendo o botão.
- **Regras da busca:**
  - casa sem acento, sem caixa, palavra por palavra e em qualquer ordem: "joao" acha "João", "silva ana" acha
    "Ana … Silva";
  - texto que não é de ninguém NÃO vale. Ao sair do campo, só vale o nome exato. Qualquer outro texto volta para a
    escolha que valia, e a tela avisa em âmbar ("Nenhuma opção tem “xyz”. Continua valendo: …"). Sem responsável, o
    Criar de cada tela recusa, como antes;
  - sair do campo resolve **na hora** (no `blur`, sem atraso). Até a revisão de 08/10 resolvia 120 ms depois, e o clique
    no "Criar OS" chegava antes: com o nome exato de outra pessoa digitado por cima da escolha, a OS saía com a
    escolha anterior (reproduzido no Chrome sem janela). Agora o clique já acha a caixa com quem vai;
  - teclado: setas, Enter (escolhe e nunca envia o formulário por baixo), Tab depois de digitar (aceita a marcada) e Esc
    (volta). No diálogo de trocar responsável, o 1º Esc fecha a lista e o 2º fecha o diálogo (`os_acoes.js` deixa passar
    o Esc da busca aberta). O `<select>` escondido sai do Tab, e o clique no rótulo cai na busca;
  - código da tela que faz `sel.value = x` (sugestão do deep link, reset) atualiza o texto, mesmo sem o `change`;
  - a opção vazia ("— selecione —", "carregando…") vira o texto de fundo, apagado, e a caixa fica livre para digitar.
- **Histórico:** toda lista de marcar com 6 opções ou mais ganha a caixa no topo. A de Usina tem sempre, porque o
  macro `multi` a marca com `data-busca="1"` (sem a marca, catálogo fora do ar e período curto a deixariam sem busca).
  Lista curta fica sem ela.
  - Esconde o que não casa pela classe `osm-fora`, **nunca** por `[hidden]`. O hidden é a cascata cliente → usina, e o
    resumo e o filtro do Histórico ignoram o que está hidden. Assim, a usina marcada continua valendo mesmo fora da
    busca.
  - Enter marca ou desmarca a linha em destaque; Esc limpa a busca, o segundo Esc fecha; fechar a lista limpa a busca.
  - A caixa não tem `name`: não vai no formulário. No celular, ela não toma o foco ao abrir a lista: o teclado cobriria
    metade dela.
- **Performance:** o rótulo "Responsável" aponta para o campo (`for="cb_resp"`). Sem isso, o primeiro controle
  dentro dele era o botão ↻, e clicar no texto recarregava a lista e apagava a escolha feita.
- **No diálogo do card** (trocar responsável), a lista entra no fluxo (`.acoes-dlg .osb-lista`). Solta por cima, ela
  era cortada pelo diálogo, que rola, e deixava 2 nomes à vista.
- **Como provar:**
  - `tests/test_oscreator_busca_digitavel.py`, 16 testes: cada tela marca o campo; o `<select>` sai com os mesmos
    values; o Histórico sai com os mesmos valores e a Usina marcada; o `blur` sem atraso; o Esc do diálogo; as regras
    de casar rodam no próprio `os_busca.js`, pelo node. Nenhum vai à rede.
  - O comportamento foi conferido num Chrome sem janela, com perfil próprio, sobre as telas do clone com dados de
    mentira e a rede bloqueada. Foram 88 conferências a 1280 px e 88 numa moldura de 375 px: sem rolagem lateral, as
    listas dentro da tela e nenhum erro de JavaScript. Falta o olho do Levi nas telas de verdade.

## Desempenho: Acompanhamento de chamados e o card da OS (08/10/2026)

O pedido do Levi, de 08/10: "O carregamento de: Acompanhamento de chamados e a tela que abre quando clica na OS está
demorando um pouco para carregar, verificar se dá para melhorar!". A cota do Fracttal é da empresa (200/min, dividida
com o App de Campo): nada aqui faz pedido a mais, e o que fica guardado é **por pessoa**.

- **O detalhe da OS em duas levas paralelas** (`api.get_os_detalhes`: o card do Histórico, a tela de um chamado e a
  conferência antes de gravar o ticket). Eram até 5 pedidos em fila. Tarefas, subtarefas e cabeçalho vão juntos;
  solicitação, OS pai e motivo do cancelamento vão juntos depois. Os mesmos pedidos; a ordem das subtarefas é a da
  seção "O card da OS com várias tarefas".
- **Leitura enxuta, por contexto:** `with api.enxuta("vinculos")` pula a 2ª leva (a tela de um chamado não mostra
  solicitação nem OS pai); `with api.enxuta("url")` traz as listas de anexos sem a URL pré-assinada. É por contexto, e
  não por argumento, porque as rotas chamam essas funções com um argumento só e os testes do oem as trocam por
  `lambda wid: ...`: um argumento novo quebrava 11 deles (conferido).
- **A contagem dos anexos do card não paga a URL de cada foto:** era um `s3_object_get` por arquivo só para mostrar o
  número. A conta casa pelo caminho do arquivo, que vem sem a URL: o número é o mesmo. A lista (o clique) continua
  com as URLs. As duas listas (subtarefas e OS) vão ao mesmo tempo, nas duas rotas.
- **Acompanhamento de chamados** (`rotas_acomp.py`), tudo em `rotas._MEMO`, por pessoa:
  - `("acomp_linhas", pessoa)`: as OS de acompanhamento sem os tickets, 3 min. A tela de um chamado usa só isto.
    Antes, com o quadro vencido, ela relia o ticket de TODAS as OS para abrir uma. O quadro reaproveita estas linhas;
  - `("acomp_tk", pessoa)`: o ticket das OS **concluídas**, 30 min. Concluída não volta e o Fracttal recusa editar OS
    fechada (`api.editar_nota_os`). Então o "Atualizar" relê a lista, as abertas e as em verificação, e não as
    concluídas dos 90 dias. Gravar ticket ou finalizar tira a OS da memória (`_esquecer(wid)`);
  - na tela de um chamado, a lista, o detalhe e as observações (banco da Gridco) vão ao mesmo tempo. O id da OS vem
    de uma leitura anterior da própria pessoa, mesmo vencida (o id de um nº não muda), e o detalhe é conferido pelo nº;
  - os cartões dos "outros chamados" são montados uma vez por leitura (eram ~0,2 s de CPU a cada chamado aberto);
  - **leitura feita com a sessão do Fracttal morta não fica na memória** (`_sessao_viva`, `_conferir_sessao`). A
    listagem engole o erro de cada página e devolve vazio, e o quadro vazio ficaria 3 min guardado. Até 08/10 a busca
    da etiqueta acusava a sessão morta; com a lista reaproveitada, o quadro pode nem passar por ela. Pelo mesmo motivo
    o id da etiqueta CHAMADOS não é guardado (`api._label_id`).
- `api.list_minhas_os` só busca quem é o logado quando o filtro é dele. "TODOS" (o Acompanhamento, a Visão COS) não
  usa, e a primeira busca da pessoa no processo lia o pessoal inteiro do Fracttal para nada.

**Medido** com um Fracttal falso a 300 ms por pedido: 150 OS com a etiqueta CHAMADOS, 80 de acompanhamento e 65
tickets a ler; servidor de pé, memória vazia, mediana de 3. O de antes é o `HEAD` c12e0a9. As telas saíram **iguais
byte a byte** nas duas versões, nos 9 passos:

| Passo | Antes | Depois |
|---|---|---|
| Quadro, 1ª visita | 4,24 s / 71 pedidos | 3,65 s / 70 |
| Quadro, "Atualizar" | 3,96 s / 70 | 2,44 s / 45 |
| Quadro, depois de 3 min | 4,00 s / 70 | 2,53 s / 45 |
| Tela de um chamado (quadro na memória) | 1,52 s / 5 | 0,32 s / 3 |
| Tela de um chamado (quadro vencido) | 5,52 s / 75 | 0,95 s / 8 |
| Card da OS (Histórico) | 1,51 s / 5 | 0,65 s / 5 |
| Contagem dos anexos do card | 2,44 s / 20 | 0,61 s / 7 |
| Lista dos anexos (o clique) | 2,44 s / 20 | 1,21 s / 20 |

O que sobra na 1ª visita do quadro são os tickets, 8 de cada vez (2,7 s dos 3,65 s): é um pedido por OS, porque a
subtarefa do ticket só vem por OS. Ler 16 de cada vez cortaria ~1,2 s com os mesmos pedidos, mas numa rajada maior na
cota da empresa. Não foi feito: é decisão do Levi.

**Como provar:** `tests/test_oscreator_desempenho.py` (7 testes, que falham todos no código de antes) e a suíte do oem
(`tests/test_os_web_*.py` e `test_anexo_documento.py`, 681 testes) passando com os arquivos novos, numa cópia fora do
oem.

## O card da OS em qualquer torre do Nexus (08/10/2026)

O pedido do Levi, de 08/10: "NEXUS > ENGENHARIA > QUADRO DE EQUIPE — Ao clicar na OS quero que abra o mesmo card que
aparece quando clicamos em uma OS no histórico do OS Creator Web. Como fazem parte do mesmo ambiente compartilhado
(Nexus) precisamos fazer os setores se conversarem."

- **É o mesmo card, sem cópia:** o fragmento `/os/os/<id>?parcial=1` do clone, as ações do `os_acoes.js` (trocar o
  responsável, etiquetas, notas, fazer a tarefa, concluir, cancelar, fluxo, anexos), o `os.css` e o `os_acoes.css`,
  dentro da mesma `.os-modal` do Histórico.
- **Numa moldura própria:** `/os/_nexus/card/<id>?status=...&de=...` (`ponte.card_os`, template
  `oscreator/card_os.html`). Ela cobre a janela, transparente, por cima da tela que a abriu. Assim o CSS do OS Creator
  não vaza para o Nexus, os diálogos do card cobrem a tela inteira, e o cookie do Fracttal (`os_sessao`, só em `/os`)
  vai junto, porque a moldura mora em `/os/_nexus`. Aberta sozinha, ela vira a página da OS no OS Creator.
- **Para usar em outra tela:** `{% include "oscreator/card_os_abrir.html" %}` e
  `NexusOsCard.abrir(id_work_order, {status, folio, aoFechar(mudou)})`. O status vai como na linha do Histórico (o selo
  e a regra do "Editar" das notas saem dele). `mudou` diz se o card mudou a OS no Fracttal: a tela relê. Fecha pelo X,
  pelo escuro em volta, pelo Fechar do card ou pelo Esc (com um diálogo aberto, o Esc é do diálogo).
- **Sem o login do Fracttal** (entrou pela senha de admin), a moldura não busca a OS: diz "Para abrir a OS, entre pelo
  Fracttal", com o botão para `/entrar?next=<a tela>`. Se a sessão do Fracttal vencer no meio, a ponte manda o pedido
  do card para o login, e a moldura diz que venceu.
- **Links do card** para outras telas do OS Creator ("Clonar esta OS", "Abrir chamado") passam por `/os/_nexus/ir`,
  que abre a torre OS Creator do Nexus com a tela numa aba (`tela_do_endereco`). Com Ctrl, numa aba nova.
- **O X do card** ficava escondido atrás do cabeçalho fixo dele, também no Histórico (`.os-modal-x` com z-index 2, o
  `.det-top` com 3, e o clique caía no cabeçalho). Passou a 4, no `os.css`.
- **Como provar:** `tests/test_torre_oscreator.py` (a moldura, o aviso sem login, o `ir`) e
  `tests/test_engenharia_equipe.py` (o quadro carrega o componente; o nº aponta para `/os/os/<id>?status=`). Também foi
  conferido num Chrome sem janela, sobre um Nexus de ensaio com o Fracttal falso:
  - o card do quadro abre com os anexos contados;
  - o diálogo de trocar o responsável tem a busca;
  - o Esc fecha o diálogo e depois o card;
  - concluir (de mentira) relê o quadro;
  - "Clonar esta OS" abre `/t/os/clonagem` com a aba;
  - sem login, aparece o aviso.

  Tudo a 1280 e a 375 px, sem rolagem lateral e sem erro de JavaScript. Falta o olho do Levi com OS de verdade.

## O card da OS com várias tarefas (08/10/2026)

O pedido do Levi, de 08/10: "Nas OSs que aparecem no OS Creator Web quando a OS tem mais que uma tarefa está duplicando
as subtarefas e não aparecendo as tarefas, tem que dividir por tarefa quando clicar!"

- **A causa, provada no REST do Fracttal** (só leitura, 5 GETs, 08/10): o `order_number` da subtarefa recomeça em 1 em
  cada tarefa (OS 8709: 13 tarefas e 45 subtarefas, cada tarefa de 1 a n), e o `api.get_os_detalhes` ordenava as
  subtarefas da OS inteira só por ele. As tarefas se intercalavam. Numa OS aberta em 08/10 com 8 tarefas iguais (a coleta
  de geração, uma por inversor: 16 subtarefas, 16 ids diferentes, 2 por tarefa), o card mostrava a 1ª pergunta 8 vezes
  seguidas e depois a 2ª, mais 8, sem dizer de qual tarefa era cada uma. Não era a mesma subtarefa repetida. E o card
  nunca agrupou: as tarefas só apareciam numa tabela solta, depois da lista.
- **Não veio das duas levas paralelas** (ced4a6b): o `api.py` de c12e0a9 e o de bc2ad06 intercalam igual. É assim desde
  que o card nasceu na web (13/09, no oem). O app de desktop escondia o defeito com o seletor de tarefa, que a web não
  trouxe.
- **O que mudou:**
  - `api.get_os_detalhes`: as subtarefas vêm agrupadas pela tarefa, na ordem das tarefas, e pelo `order_number` dentro de
    cada uma. Subtarefa de tarefa que não veio vai para o fim, sem sumir. Cada tarefa e cada subtarefa entram uma vez,
    pelo id (`id` da tarefa, `id_work_orders_tasks_form_items`). Os pedidos ao Fracttal são os mesmos;
  - o card (`os_detalhe_conteudo.html`), com mais de uma tarefa: a seção vira "TAREFAS (n)", uma linha por tarefa com o
    número, o título, o ativo, a situação e "x de y concluídas". O clique, o Enter ou o Espaço abrem as subtarefas DELA,
    com o tipo, a programada e a execução da tarefa. É `<details>`, sem JS. A barra e o "x de y subtarefas concluídas"
    contam a OS inteira, e o rodapé diz "N subtarefa(s) em M tarefas". A tabela solta saiu. Com uma tarefa só, nada
    mudou;
  - a situação sai das datas de execução que o card já lê (`os_acoes_web.situacao_tarefa`): com fim, Finalizada (verde);
    só com início, Iniciada (âmbar); sem as duas, Não iniciada (cinza). O `task_status` do REST não foi usado porque
    não se sabe se o RPC do card o traz;
  - no Concluir, cada pendência diz de qual tarefa é. Os botões "Fazer a tarefa" e o aviso das tarefas sem data de fim
    levam o ativo quando o título se repete (`os_acoes_web.rotulos_tarefas`): eram 8 "Coleta de Dados de Geração"
    iguais;
  - o CSS é o bloco `.det-tarefa` do `os.css`. No celular, a subtarefa dentro da tarefa fica com a largura: a descrição
    ocupa a 1ª linha, e o tipo e a seta descem para a 2ª. Sem isso, a 375 px a descrição virava uma coluna de uma
    palavra por linha.
- **Vale depois de reiniciar** o 5090 e o 5070 (ou do deploy): o Python novo só entra no reinício. Até lá, o template
  pede as duas funções novas com `is defined`. Sem essa guarda, o serviço que lesse o template novo com o Python antigo
  daria erro em todo card (`'acoes_grupos_tarefas' is undefined`, reproduzido); com ela, fica a lista de antes. O CSS
  novo vale na hora e não muda o card antigo, fora a tabela de tarefas, que perde 8 px de margem.
- **O que não deu para provar:** o RPC do card (`tasks.work_orders_task_form_items_list` com o `id_work_order`) usa a
  sessão da pessoa e não foi chamado. O REST, que lê a mesma tabela, não repete subtarefa (16 em 16, 45 em 45), e a
  conferência ao vivo do RPC registrada no `api.py` (commit de 03/08 no oem) casou 45 de 45 na 8709. A guarda por id
  cobre o caso de o RPC repetir, sem custo.
- **Como provar:**
  - `tests/test_oscreator_card_tarefas.py`, 12 testes. 11 falhavam no código de antes; o da OS de uma tarefa passa nos
    dois (é a garantia de que ali nada mudou).
  - Na bancada: Nexus de ensaio com o Fracttal falso e a rede bloqueada, e um Chrome sem janela com clique e teclado de
    verdade. Foram usadas a OS de 8 tarefas iguais e uma de 13 tarefas (preventiva, títulos longos, uma sem subtarefa),
    a 1280 e a 375 px. Conferido: sem rolagem lateral; nada fora do card; Enter e Espaço abrem e fecham a tarefa; o
    Concluir; o "Fazer a tarefa" com o checklist da tarefa certa; os anexos abrindo; nenhum erro de JavaScript.
  - A suíte do oem (681 testes) passa com os arquivos novos, numa cópia.
  - Falta o olho do Levi numa OS de verdade (a 8709, ou uma das de 08/10 com várias tarefas).

## Rodar sozinho (sem o Nexus e sem mexer no 5090)

```
cd nexus/torres/oscreator/os_creator
set OS_WEB_PORTA=5091
python -m os_web.servir
```

Depois abra `http://127.0.0.1:5091/os/login`. O login no Fracttal é por pessoa, como no supervisório.

## Antes de mexer

- **O Nexus é a referência; o oem acompanha** (Levi, 06/10/2026: "sincronize a ferramenta usando o do nexus como
  referência"). Mudança no OS Creator: faça aqui, na cópia, prove aqui, e leve ao oem (o 5090 do supervisório):

  ```
  python ferramentas/sincronizar_oscreator.py              mostra o que mudou
  python ferramentas/sincronizar_oscreator.py --aplicar    leva ao oem o que mudou só no Nexus
  python ferramentas/sincronizar_oscreator.py --trazer     traz ao Nexus o que mudou só no oem
  ```

  A regra é de três lados (`sincronia.py`, com o hash de cada arquivo na última sincronia em `sincronia.json`): o que
  mudou só no Nexus vai; o que mudou só no oem não é atropelado (aparece na lista); o que mudou nos dois é conflito e
  fica para resolver à mão. O que o destino tinha antes vai para `<pasta de dados>/oscreator_backup/`. Só vão os
  arquivos da cópia que estão no git (o `os_creator/.env`, com a credencial do Fracttal, fica fora sempre). Copiar
  não reinicia o 5090 nem faz commit no oem (público: commit lá é decisão do Levi). Depois, commit do
  `sincronia.json` no Nexus. Sincronia inicial (06/10, 15:58): 120 arquivos, todos iguais.
- **Levar só os seus arquivos.** O `--aplicar` leva tudo o que está em "levar". Com outra sessão mexendo na cópia ao
  mesmo tempo, ele levaria o trabalho dela pela metade ao 5090. Foi o caso de 08/10: o card da OS com várias tarefas
  estava em andamento em `api.py`, `os_acoes_web.py` e `os_detalhe_conteudo.html`, enquanto a Engenharia ia ao oem.
  O mesmo vale para um arquivo novo, que ainda não está no git do Nexus. Nesses casos:
  - confira com `S.estado` que os seus estão em "levar";
  - rode `S.importa_o_nexus` e copie com `S._copiar`, guardando o de antes em `<pasta de dados>/oscreator_backup/`;
  - grave no `sincronia.json` o hash **só desses arquivos** (`S._hash`), para os outros continuarem em "levar".
- **O que é só do Nexus vai na `ponte.py`, nunca na cópia** (a cópia vai para o supervisório, que não tem o Nexus):
  a cópia não pode importar o pacote `nexus`, e a ferramenta recusa se importar. O
  `tests/test_torre_oscreator.py` acusa quando a cópia e o oem divergem (só na máquina que tem o oem).
- Usa a mesma pasta de dados do OS Creator (`%APPDATA%\CriarOS-Fracttal`). Na mesma máquina, ele divide com o
  supervisório a chave da sessão e o token do banco.
- Precisa do PyQt6 instalado, porque a tela de Engenharia importa `steps/engenharia`, que puxa `steps/ui.py`.
