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
  segredo novo. O cookie continua `os_sessao`, só no `/os` do Nexus (prefixo + `/os`: `/nexus/os` no servidor; seção
  "Debaixo do /nexus").
- **A sessão do Fracttal leva a do Nexus junto** (Levi, 09/10/2026: "quando deslogar do Fracttal deslogue do Nexus").
  A regra mora no portão (`nexus/casca/CLAUDE.md`, "Sair do Fracttal = sair do Nexus"); a ponte faz a parte dela:
  - o "sair" do clone (`/os/logout`) nem chega a ele: o portão encerra as duas sessões e leva a janela ao login (o
    `os_sessao` é apagado no caminho do prefixo, `os_cookie_path()`; e o login do clone na resposta, `/os/login`, é
    reconhecido com ou sem o `/nexus` na frente);
  - para quem entrou pelo Fracttal, a resposta do clone que tira o JWT do cookie, manda ao `/os/login` ou responde 401
    pedindo login encerra o Nexus (`_fim_na_resposta`: "caiu"; o aviso do JWT vencido do app de mesa: "venceu"); o
    token que o clone renovou estica o `fracttal_exp` da sessão do Nexus junto. Com a senha de administrador fica o de
    antes (`_de_volta_ao_login`, só o OS Creator volta ao login dele);
  - `/os/_nexus/sessao`: a página do Nexus pergunta se o token ainda vale; o servidor pergunta ao Fracttal no máximo uma
    vez a cada 5 minutos por token (`vivo_no_fracttal`, o mesmo pedido barato do `api.is_logged_in`; a cota é de 200
    pedidos por minuto para a EMPRESA). Só a resposta "sessão morta" (`SessionExpired`) derruba; 429, rede ou token a 2
    minutos de vencer não decidem nada (o prazo resolve, e perguntar faria o clone tentar renovar o token).
- **Quando sobe:** o clone só sobe na primeira visita ao `/os/`. Se ele quebrar (faltou PyQt6, por exemplo), o
  `/os/*` mostra um aviso e o resto do Nexus segue.
- **Tema do Nexus (escuro e claro):** o OS Creator segue o botão do tema do Nexus, na moldura da torre, no card da OS e
  em qualquer página `/os/` (seção "Tema claro, com o botão do Nexus").
- **Testes:** `tests/test_torre_oscreator.py`, `tests/test_oscreator_solic_engenharia.py`,
  `tests/test_oscreator_busca_digitavel.py`, `tests/test_oscreator_desempenho.py`, `tests/test_oscreator_card_tarefas.py`,
  `tests/test_oscreator_acomp_quadro.py`, `tests/test_oscreator_acomp_renovar.py`, `tests/test_oscreator_card_preparo.py`,
  `tests/test_oscreator_tema_claro.py` e `tests/test_auth_sair_fracttal.py` (a sessão do Fracttal que acaba leva a do
  Nexus). Nenhum teste fala com o Fracttal.
- **O que não funciona igual:**
  - o login pelo OAuth do Fracttal tem a volta configurada para o supervisório; e-mail e senha funcionam normal;
  - gravar no banco da Gridco (observações dos chamados, modelos do Controle de fornecedores, temas) precisa do
    `GRIDCO_SQL_TOKEN`. Sozinho, o clone o lê da variável ou do `%APPDATA%` da máquina; no Nexus, é o do `.env` do Nexus,
    que a ponte põe no ambiente ao criar o clone (`ponte.token_do_banco_para_o_clone`, 19/10/2026: até então o servidor
    abria tudo isso só para ler).

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
  - **a etiqueta `ENGENHARIA`, sempre, e só ela.** Nem `PERFORMANCE` nem `Dar prioridade` no urgente, nem a `Remoto`,
    nem a `Backoffice`. Levi, 06/10: "Etiqueta de remoto e engenharia fixas sempre! só essas etiquetas viu, sem
    performance"; 13/10: "SOLICITAÇÃO ENGENHARIA INVÉS DE REMOTO É Backoffice"; e 21/10: "tire a obrigatoriedade da
    etiqueta backoffice, deixe só a etiqueta engenharia mesmo" (de 13/10 a 21/10 ia também a `Backoffice`, que era
    obrigatória; até 13/10, a `Remoto`).
    - Casa pelo nome **inteiro** (`solic_eng_web.etiquetas`), sem acento, sem caixa e sem espaço, hífen, ponto ou
      sublinhado ("ENGENHARIA", "Engenharia" e " engenharia " são a mesma). A busca por trecho do `label_id_por_nome`
      tomaria a "Religamento Remoto" pela "Remoto".
    - A etiqueta é conferida **antes** de criar. Faltando no Fracttal, nenhuma OS sai, e a tela diz "Não achei no
      Fracttal a etiqueta ENGENHARIA. Nenhuma OS foi criada.";
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
    iguais: Administrativa, só a Classificação 1, só a `ENGENHARIA`, as duas datas e o responsável do `.env`.
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

## Performance: agrupar em UMA OS com várias tarefas (13/10/2026)

O pedido do Levi, de 13/10: "No OS Creator Web não tem o mecanismo de quando é selecionado vários ativos, agrupar em uma
só tarefa e vira uma atividade que nem no OS Creator Desktop! Veja o OS Creator Desktop e replique para o web". O
Tradicional e a Engenharia da web já agrupavam; o Performance (todos os planos: Geração e ETM, Inspeção Geral do
Inversor, Recomposição de String, Tracker parado) criava sempre uma OS por ativo (`perf_web.montar_itens` dizia
"agrupar entra desligado"). Agora é o porte do `PerfCriar` do app de mesa (steps/performance.py):

- **A caixa** "Agrupar em UMA OS com várias tarefas", no cartão do responsável, aparece com 2+ ativos marcados e **liga
  sozinha** (`_auto_agrupar`, Levi 26/08: uma OS por ativo virou a exceção) **enquanto a pessoa não clicar nela**: o
  clique é a decisão dela, e a tela não remarca o que ela desmarcou; tirar ativos não desliga o modo.
- **Agrupado** (`_on_agrupar`): o nome digitado vale para a OS e para TODAS as tarefas, sem o prefixo [Ativo] (o Fracttal
  ignora o título da OS e copia o da 1ª tarefa: é o único jeito de a OS se chamar assim); some a coluna OS Pai por ativo
  e aparecem a **OS pai** e a **Observação da OS**, uma só para a OS inteira (a observação de cada ativo continua na
  tabela, na tarefa dele); o contador diz "1 OS com N tarefas"; a confirmação diz o que muda (a OS só fecha quando
  todas as tarefas forem concluídas; as tarefas nascem sem data de início/fim, o cronômetro preenche).
- **No servidor:** `perf_web.quer_agrupar` (2+ ativos e a caixa), o título e a OS pai únicos no `montar_itens`, e a rota
  `/os/api/performance/criar` chama o `api.create_performance_os_agrupada` (o mesmo do app: tarefas pendentes, uma OS,
  etiquetas, imagens na tarefa de cada ativo e o ticket POR ATIVO) com a `note_os`; `perf_web.mensagem_agrupada` diz
  "OS N criada com N tarefa(s)" ou que as tarefas existem SEM número (a tela limpa a seleção do mesmo jeito, para a
  pessoa não criar tudo de novo).
- **Prova (13/10):** `tests/test_oscreator_perf_agrupar.py` (payload, rota, mensagem, tela) e um ensaio num Chrome sem
  janela com o Fracttal dublado, fora da suíte: 1 ativo, sem caixa; 2, a caixa liga e a tela muda; a pessoa desmarca e
  o 3º ativo não religa; religada, o Criar chama a agrupada com os 3 títulos iguais, a OS pai e a observação da OS.
  **Falta a prova ao vivo** numa usina de `TESTE - PA` (criar e cancelar). O 5090 só pega no próximo reinício.

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
com o App de Campo): nada aqui faz pedido a mais. O que fica guardado era **por pessoa**; desde 19/10/2026 o quadro do
Acompanhamento é dividido entre quem vê o mesmo no Fracttal (seção "O quadro do Acompanhamento dividido").

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
- **Acompanhamento de chamados** (`rotas_acomp.py`), tudo em `rotas._MEMO`, por dono da cópia (`_dono`: "TODOS" para
  quem vê o mesmo no Fracttal, ou a pessoa; ver "O quadro do Acompanhamento dividido"):
  - `("acomp_linhas", dono)`: as OS de acompanhamento sem os tickets, 30 min (era 3 até 20/10/2026, ver "O quadro
    só relê no Atualizar ou a cada 30 min"). A tela de um chamado usa só isto.
    Antes, com o quadro vencido, ela relia o ticket de TODAS as OS para abrir uma. O quadro reaproveita estas linhas;
  - `("acomp_tk", "TODOS")`: o ticket das OS **concluídas**, 30 min, um para todos (é da OS). Concluída não volta e o Fracttal recusa editar OS
    fechada (`api.editar_nota_os`). Então o "Atualizar" relê a lista, as abertas e as em verificação, e não as
    concluídas dos 90 dias. Gravar ticket ou finalizar tira a OS da memória (`_esquecer(wid)`); trocar o responsável
    (no card ou na tela do chamado) também, mas só quando a OS está num quadro guardado (`esquecer_se_no_quadro`);
  - na tela de um chamado, a lista, o detalhe e as observações (banco da Gridco) vão ao mesmo tempo. O id da OS vem
    de uma leitura anterior da cópia que a pessoa vê, mesmo vencida (o id de um nº não muda), e o detalhe é conferido
    pelo nº. **A lista vencida (até `VELHA_MAX`) serve na hora e se relê por trás**, como no quadro (20/10/2026, Raio-X
    das 09:56: a tela de um chamado ficou 39 s relendo a lista inteira, com as tarefas de todas as OS, na frente de quem
    abriu); a situação, o fim e o responsável vêm do detalhe, lido na hora (`_com_o_detalhe`: responsável trocado tira o
    id da lista, e a equipe é conferida pelo nome). Prova: `tests/test_oscreator_acomp_tela_vencida_20_10.py`;
  - **a releitura não relê as tarefas das OS que já estavam fechadas** (`_fechadas_ja_lidas` → `api.list_chamados
    (meta_ja=...)`, a mesma regra do Histórico de 19/10): concluída não volta e o Fracttal não deixa editar;
  - os cartões dos "outros chamados" são montados uma vez por leitura (eram ~0,2 s de CPU a cada chamado aberto);
  - **leitura feita com a sessão do Fracttal morta não fica na memória** (`_sessao_viva`, `_conferir_sessao`). Os
    tickets engolem o erro de cada pedido, e o quadro vazio ficaria guardado. Até 08/10 a busca da etiqueta acusava a
    sessão morta; com a lista reaproveitada, o quadro pode nem passar por ela. Pelo mesmo motivo o id da etiqueta
    CHAMADOS não é guardado (`api._label_id`). A página da listagem que falha derruba a busca inteira desde 21/10/2026
    (seção "A lista pela metade não vai para a tela").
  - **Passados os 30 min, o quadro abre na hora com a leitura anterior e relê por trás** (Levi, 09/10/2026: "teria
    como utilizarmos essas requisições de forma mais inteligente?"; `_renovar_por_tras`). Ao lado da hora da leitura
    aparece "· atualizando", e a tela troca sozinha quando a nova chega (`acomp.js`, `esperarANova`: pergunta ao
    `/os/chamados/acompanhamento/estado` de 5 em 5 s, por até 3 min; o Atualizar lê na hora). A releitura roda numa
    thread com o JWT e o e-mail de quem abriu (`sessao.contexto`: a thread nasce sem o contexto da requisição), uma
    por cópia, com os mesmos pedidos que a tela faria na frente da pessoa: nada a mais na cota. **Também a de ontem**
    (mais velha que `VELHA_MAX`, 2 h; 24/10/2026, Levi escolheu abrir a 1ª vez do dia com ela em vez de esperar ~40 s o
    Fracttal), mas só para quem vê no Fracttal o mesmo total da cópia (`_mesma_visao_da_velha`: a cópia largada pode ser
    de outra visão; quem tem a visão restrita lê a dela na frente). A tela de UM chamado segue com o `VELHA_MAX` (lê na
    frente passadas as 2 h). Provas: `tests/test_oscreator_acomp_troca_sozinha_24_10.py` (o script no node) e os
    testes da de ontem em `test_oscreator_acomp_renovar.py` e `test_oscreator_acomp_dividido_19_10.py`. Erro do Fracttal: fica a leitura
    anterior. Sessão caída: a cópia sai, e a próxima visita volta ao login. Gravação no meio da releitura (ticket,
    finalizar): a cópia dela sai (`_ESQUECIDO`). Medido com o Fracttal falso a 300 ms por pedido (65 chamados): quadro
    vencido de 4,8 s para 0,007 s. Prova: `tests/test_oscreator_acomp_renovar.py` (8 testes).
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

## O card começa a carregar antes do clique (09/10/2026)

Levi, 09/10: "teria como utilizarmos essas requisições de forma mais inteligente?". O mouse que PARA 250 ms em cima de um
cartão pede o detalhe da OS por trás; o clique que vem depois pega essa leitura, ou espera a que já está em curso.

- **Onde:** o Quadro da equipe da Engenharia do Nexus (`NexusOsCard.prepararAoParar(el, wid)`, no
  `oscreator/card_os_abrir.html`, que chama `/os/api/os/<id>/preparar`) e o quadro do Acompanhamento de chamados
  (`static/acomp.js`, que chama `/os/chamados/acompanhamento/<nº>/preparar`, lido enxuto e só com o id que o quadro da
  própria pessoa já leu). O clique: `rotas.os_detalhe` (o card) e `rotas_acomp._detalhe_enxuto` (a tela de um chamado),
  pelo `rotas.preparado`.
- **Regras** (`rotas.preparar`), pela confiabilidade e pela cota da empresa:
  - vale `PREPARO_S` (30 s) e UMA vez: o clique seguinte lê de novo, e o card mostra o que a pessoa acabou de mudar;
  - toda rota POST com o id da OS (concluir, nota, responsável, etiquetas, tarefa, cancelar) joga fora o que foi lido
    antes dela (`_gravou_esquece_preparo`, `after_app_request`); o ticket e o finalizar do Acompanhamento, pelo
    `_esquecer(wid)`;
  - teto por minuto: 6 por pessoa e 12 no total (no pior caso ~60 pedidos/min somando todo mundo; no uso normal, o que o
    clique já faria). O mesmo cartão não pede duas vezes, e o navegador pede uma vez por cartão até abrir;
  - com a sessão DA PESSOA no Fracttal (`sessao.contexto`), numa thread de 3 (`_executor_preparo`).
- **Medido** com o Fracttal falso a 300 ms por pedido: clique sem o mouse parar antes, 0,67 s; com a leitura pedida
  0,3 s antes do clique, 0,30 s; pedida 0,8 s antes, 0,00 s.
- **Como provar:** `tests/test_oscreator_card_preparo.py` (10 testes).

## Acompanhamento de chamados com o quadro da Engenharia (08/10/2026)

O pedido do Levi, de 08/10: "Precisamos padronizar a estética para que coisas parecidas não pareçam completamente
diferentes, nesse caso gostei mais da estética do da engenharia porém o card de KPIS eu gostei mais do de chamados, faça
essas substituições". Aqui mudou o QUADRO; a faixa de números ficou como estava (é a que o Levi gosta, e virou o modelo da
faixa do Quadro da equipe da Engenharia, `nexus/torres/engenharia/CLAUDE.md`).

- **O desenho é o do Quadro da equipe** (`kb-*` em `nexus/static/engenharia.css`), espelhado no bloco "o quadro" do
  `static/chamados.css` com a paleta daqui: o OS Creator não carrega o CSS do Nexus e roda sozinho no 5090. Mudou o quadro
  da Engenharia, traga para cá.
  - Coluna: um cartão com a faixa da cor no topo (Chegaram vermelho, Ticket aberto âmbar, Finalizados verde), o título,
    a pílula da contagem e, à direita, o subtítulo de antes. No computador a coluna rola por dentro, com 6 cartões à
    vista (20/10/2026; até então 72vh, como na Engenharia); no celular (uma coluna embaixo da outra) quem rola é a página.
  - Cartão: "OS 12875" em verde, mono; o estado no canto, colorido pela idade (`tempo_curto`: "35 d", "8 d sem
    atualização", "atualizado hoje", "fechado 26/09", "em verificação 26/09"); o ativo em negrito; onde (código ·
    cliente · usina); as etiquetas (fornecedor, tipo de ativo, inspeção de origem, ticket); o responsável com o avatar
    das iniciais (cor fixa por pessoa, `acomp_web.cor_avatar`); "no nome de …" em âmbar quando não é da equipe; "não
    consegui ler o ticket" como antes. O fio à esquerda segue a mesma régua da idade (`acomp_web.urgencia`).
  - A frase inteira continua em `tempo` (o title do cartão e a tela do chamado).
- **O que funciona hoje não mudou:** o `acomp.js` é o mesmo e acha tudo pelos mesmos ganchos (`.col`, `.card`,
  `[data-n]`, `[data-vazio]` e os `data-*` do cartão); o cartão inteiro é o link do chamado. O vazio passou para dentro
  da coluna. Filtros, Limpar filtros, busca, contagem, Atualizar e o clique conferidos iguais, antes e depois.
- **Contraste:** o texto miúdo do quadro e a nota da faixa de números passaram do `--fa` (3,5:1) para o `--mu`
  (5,9:1), o mesmo tom da nota da faixa do Quadro da equipe (mostrado ao Levi e aprovado com a padronização, 09/10). O
  "lido do Fracttal às" continua no `--fa` (4,1:1).
- **Sem reiniciar:** o CSS vem do disco na hora, e o 5090 e o 5070 seguem com o `acomp.html` e o `acomp_web.py` de antes
  na memória até reiniciar. Para o cartão de antes não ficar sem estilo nesse meio-tempo, o `chamados.css` guarda as
  regras dele (bloco "o cartão de antes"), que saem no primeiro ajuste depois do reinício. O HTML novo com o Python de
  antes também funciona (o estado sai com o texto de antes, "35 dias").
- **No oem:** o `tests/test_os_web_acomp.py` de lá (que não está no git do oem) conferia o estado de antes
  (`<span class="tag u-a">7 dias</span>`); a linha passou a `7 d` junto com a sincronia.
- **Como provar:** `tests/test_oscreator_acomp_quadro.py` (6 testes, com o Fracttal falso; todos falham no código de
  antes): os campos do cartão, o que os filtros e o clique usam, a faixa de números intacta, o estado curto e a cor do
  avatar, e que toda classe nova do cartão tem regra no CSS. A suíte do oem passa numa cópia com os arquivos novos (1.283).
  Na bancada (o clone sozinho, Fracttal falso com 31 chamados inventados, rede bloqueada e relógio parado), num Chrome sem
  janela a 1440, 1240 e 375 px: sem rolagem lateral, sem erro de JavaScript, e filtros, vazio, busca digitada, Limpar
  filtros, Atualizar e o clique (abre o chamado numa aba) com o mesmo resultado no antes e no depois. Falta o olho do Levi
  com os chamados de verdade.

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
- **Sem o id do Fracttal, pelo número da OS** (16/10/2026, o nº citado na observação do Fora da programação do PCM):
  `NexusOsCard.abrirFolio(nº, {status, aoFechar})` → `/os/_nexus/card/folio/<nº>` (`ponte.card_os_folio`), a mesma
  moldura com o fragmento `/os/os/folio/<nº>?parcial=1`: quem acha o id é o clone (o "Buscar OS pelo nº" do Histórico),
  com um pedido a mais ao Fracttal, e o nº que não existe aparece como "Não achei nenhuma OS com o nº" dentro da moldura.
  Tendo o id, prefira o `abrir` (sem o pedido a mais, e com a leitura antecipada do `prepararAoParar`).
- **Sem o login do Fracttal** (entrou pela conta Microsoft ou pela senha de admin), a moldura não busca a OS: diz
  "Para abrir a OS, entre pelo Fracttal", com o botão para o login do PRÓPRIO OS Creator (`/os/login`), que volta à
  tela de onde se veio por `/os/_nexus/card/voltar?de=<a tela>` (o clone só devolve para `/os/...`; o `/os/_nexus/voltar`
  é o da assinatura da PT, só do Campo). Até 18/10/2026 o botão ia ao `/entrar` do Nexus, que com a conta Microsoft
  ligada é a porta dela: o Levi clicava em "Entrar com o Fracttal" e caía na Microsoft. Se a sessão do Fracttal vencer
  no meio, a ponte manda o pedido do card para o login, e a moldura diz que venceu.
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

## Telas do OS Creator com o atalho em outra torre (08/10/2026)

Levi: "Controle de fornecedores do OS Creator Web tem que estar no NEXUS > CHAMADOS > FABRICANTE"; "o mesmo com
Acompanhamento de chamados, tem que estar em GARANTIAS"; "não que vão sair da visão do OS Creator Web, porém, quando for
abrir essa janela o atalho deve ficar para a parte de CHAMADOS". Em `ponte.ATALHOS`: Chamados → Fabricantes abre
`/os/chamados/fornecedores` e Chamados → Garantias abre
`/os/chamados/acompanhamento`, na mesma moldura da torre OS Creator (`abrir_em`), com o menu lateral marcando a torre
Chamados; entre os atalhos o clique abre aba nova na casca já aberta. As telas continuam no OS Creator (mesmo endereço; o
setor Chamados dele não mudou). Atalho novo para outra torre = uma linha em `ATALHOS` (a torre Chamados registra a
rota de cada uma sozinha). Prova: `tests/test_torre_chamados.py`.

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

## Tema claro, com o botão do Nexus (09/10/2026)

O pedido do Levi, de 09/10: "faltou o tema claro do OS Creator Web, não está sincronizando com o botão do Nexus". Com o
Nexus no claro, as telas do OS Creator continuavam navy. O escuro ficou exatamente como era.

- **Como o tema chega, sem piscar.** O clone não lê o cookie do Nexus: quem decide é o Nexus, pelo mesmo
  `casca.tema_do_pedido` (cookie `nexus_tema`).
  - **A ponte** (`ponte._com_o_tema`): com o Nexus no claro, o `<html>` da página do clone sai com `data-tema="claro"`;
    no escuro (o padrão, cookie ausente ou desconhecido) o atributo não entra, e o HTML é o de sempre. Toda página leva
    o `oscreator/_tema_os.html` logo depois do `<meta charset>` (o `_tema_cabeca.html` do Nexus e o evento `storage`):
    ele refaz a conta antes de pintar, para a página que demorou (o Fracttal leva segundos e o tema pode ter mudado no
    meio) e a que volta do cache, e acompanha a troca feita em outra aba do navegador.
  - **O card da OS** (`card_os.html`, template do Nexus) desenha o mesmo atributo e inclui o mesmo script.
  - **Ao vivo:** o botão do tema (`base.html`, `temaNasMolduras`) troca o atributo nas molduras abertas da mesma origem
    cujo endereço é `/os/`, moldura dentro de moldura (a da torre, a casca e as abas dela; o card do Quadro da equipe).
    A página da Plataforma no Tempo real (outro sistema) e moldura de outra origem ficam como estão. Página do OS
    Creator aberta depois já nasce no tema novo: o cookie já mudou.
- **Onde mora a cor: no clone**, e vai ao oem com a sincronia. Cada `.css` do `os_web/static` ganhou no fim o par do
  claro de cada cor do escuro, em `:where(html[data-tema="claro"]) <o mesmo seletor>`; o bloco TEMA CLARO do fim do
  `os.css` tem a paleta, `--osc-*`, que é a do tema claro do Nexus (`nexus.css`), e as variáveis de cada folha no claro.
  No oem sozinho (5090) ninguém põe o atributo: nada disso vale, e a tela é a de sempre.
  - `:where()` não soma especificidade: o par do claro vence o escuro só por vir depois, e o estado mais específico do
    escuro (`.on`, `.sel`, `:hover`, `:focus`) continua vencendo. Com `html[data-tema="claro"] .x` solto, o `.x` do
    claro passaria por cima do `.x.on` e do `:focus` (a borda de foco do campo sumia). Hover reescrito no claro leva
    junto, depois dele, o estado que vinha depois no escuro (o foco depois do hover, o marcado depois do hover).
  - Verde Grid (lima `#a9db21`) só como SUPERFÍCIE (botão, barra, marcação cheia) com texto escuro; verde em texto, foco
    e borda de escolha é o musgo (`#566610`): o lima dá 1,6:1 no branco. As variáveis que o escuro usa para os dois
    (`--f-green`, `--verde`, `--gr`) são o musgo no claro, e cada fundo verde ganhou o lima no par.
  - Borda de campo (input, select, busca) a 3:1 contra o branco e o cinza de seção (`--osc-campo`).
  - O conteúdo não esmaece por opacidade no claro (a pergunta de fora, o cartão finalizado, o setor que não chegou à
    web, o detalhe da pendência): vira cinza de seção ou texto mudo. O controle desligado (`:disabled`) segue com a
    opacidade do escuro.
  - **Cor do dado** no `style` (o status do Fracttal no selo, a etiqueta, o placar dos Tickets, o status do ativo, o do
    nó do Fluxo, o ciclo do painel de tickets): ela foi escolhida para o navy (o verde `#48D07A` dá 2:1 no branco). No
    claro o texto é pintado com a mesma cor e a luminosidade do oklch no teto de 0,46
    (`-webkit-text-fill-color: oklch(from currentColor min(l,.46) c h)`): a matiz e a saturação ficam (o vermelho segue
    vermelho), só a cor clara demais escurece. Medido no Chrome: de 5,5:1 a 7,7:1 no fundo do selo com as cores do
    Fracttal e do OS Creator, 4,9:1 no pior caso inventado (vermelho puro). Navegador sem a cor relativa fica na linha de
    antes: a cor misturada meio a meio com o preto (a luminância por 8, acima de 6:1), legível mas quase preta. A borda e
    o fundo do selo seguem os do dado.
  - Ícones: o traço vem no `stroke="#…"` do `<svg>` (`lancador.icone`); o `os.css` remapeia cada cor no claro
    (`svg[stroke="#A6E22E" i]` → musgo, o cinza-claro → o cinza do texto, o branco → a tinta).
  - Cor fixa escrita num template (`engenharia.html`): o elemento ganhou uma classe (`eng-sup-nome`, `eng-titulo`,
    `eng-sup-quadro`) e a classe ganhou o claro em `!important`; o `style` e o escuro não mudaram.
  - A foto ampliada (o visor do card) fica escura nos dois temas, como a do Nexus: dentro dele as variáveis voltam ao
    escuro.
- **REGRA para quem mexer no CSS do clone:** cor nova no escuro ganha o par do claro no fim da mesma folha, por `--osc-*`;
  cor nova de ícone ganha o `svg[stroke]` no `os.css`; `style` com cor num template ganha a classe com o claro em
  `!important`; cor do dado no `style` ganha a regra `[style]` com o `-webkit-text-fill-color`. O
  `tests/test_oscreator_tema_claro.py` cobra tudo isso.
- **Vale quando:** o CSS vem do disco na hora, mas sem o atributo ele não muda nada; a ponte, o `card_os.html` e o
  `base.html` valem depois de reiniciar o Nexus (5070) ou do deploy. No 5090 do supervisório nada muda.
- **Como provar:**
  - `tests/test_oscreator_tema_claro.py`: a ponte põe o atributo pelo cookie e não põe no escuro (o HTML do escuro não
    depende do cookie); o card idem; o botão chama a troca, e a função dele, no node sobre um DOM falso, troca a casca,
    a aba e o card e não a Plataforma nem a moldura de outra origem; o clone não importa o nexus; toda cor fixa do escuro
    de cada folha tem o par do claro (vale a última declaração de cada seletor), toda variável de cor tem o valor do
    claro, toda cor de ícone tem a do claro, toda cor escrita em template ou JS tem o gancho; o claro só existe em
    `:where(html[data-tema="claro"])`; a paleta é a do Nexus; o contraste AA do texto do claro, regra a regra; a borda de
    campo a 3:1. Doze mutações (tirar um par, cor nova sem par, claro sem `:where`, texto em lima, variável sem claro,
    cor de dado e cor fixa em template, cor de dado no JS, ícone novo, a ponte e o card sem o atributo, a paleta
    divergente) fazem o teste falhar.
  - Na bancada (09/10): um Nexus de ensaio com o Fracttal falso e a rede bloqueada, no Chrome sem janela, 42 telas,
    diálogos e estados do OS Creator (pela torre, pelos atalhos de Chamados e o card do Quadro da equipe), nos dois temas,
    a 1440 e a 375 px, com o código de antes e o de depois. No claro, de 15.196 textos medidos, os abaixo de 4,5:1 foram
    de 168 (o OS Creator navy dentro do Nexus claro) a 0; o menor é o "!" branco no círculo vermelho do painel de tickets
    (4,8:1, igual nos dois temas). No escuro, as cores computadas de 32.006 elementos são as mesmas de antes, e os prints
    só diferem no relógio (a hora da leitura, o "agora" das datas) e em 1 unidade de anti-serrilhado. Nenhum erro de
    JavaScript. A troca ao vivo: o botão com o card aberto, aba nova depois da troca, a volta ao escuro igual ao de antes,
    o card do Quadro da equipe e a outra aba do navegador.
  - O oem sozinho (o clone sem o Nexus, como o 5090), com o cookie `nexus_tema=claro` no navegador (o mesmo host em outra
    porta recebe o cookie): nunca ganha o atributo; 10.724 elementos com as mesmas cores do código de antes. A suíte web
    do oem (`test_os_web_*.py` e `test_anexo_documento.py`, 681) passa com os arquivos novos, numa cópia fora dele.
  - Já era assim antes, nos dois temas, e ficou de fora (mexer muda o oem): a 375 px a aba rola de lado na Visão COS (o
    "N OS exibidas"), na Nova solicitação PCM (a grade da classificação), na tela de um chamado (a tabela), na Clonagem
    (os campos) e no COS (a linha das datas); e o escuro tem 168 textos abaixo de 4,5:1 (a etiqueta do Fracttal com a
    cor escura do dado, como ENGENHARIA a 2,5:1 e Remoto a 1,6:1; o `--fa` dos chamados, do Controle de fornecedores e
    do Início, a 3,5–4,1:1; o texto de exemplo do login, cinza padrão do navegador).
  - Falta o olho do Levi com os dados de verdade.

## Sem Tickets e sem a faixa de abas (12/10/2026)

- **A tela de Tickets saiu do Nexus, com o código dela** (Levi: "Chamados > Tickets de Performance -> pode excluir essa
  seção e o código dela!"; perguntado sobre o 5090: "Isso você não levará para o oem"). Saíram da cópia os arquivos só
  da tela: `os_web/rotas_tickets.py` (as 10 rotas `/tickets` e `/api/tickets/...`; o registro automático das telas não
  acha mais o arquivo), `os_web/tickets_web.py`, `os_web/tickets_painel.py`, `tickets_calc.py`, `templates/tickets.html`
  e `tickets_painel.html`, `static/tickets_painel.js` e `.css`; e, no Nexus, o item Chamados → Tickets de performance
  (`ATALHOS`). A sincronia lista os 8 como "apagado no Nexus" e não os apaga no oem: o 5090 segue com a tela.
- **A cópia segue igual à do oem nos arquivos que ficaram**: o `lancador.py`, o `performance.html` e o `os.css` do oem
  ainda desenham o card "Tickets" da Performance, a pílula dele no card do setor (Início) e as regras `tk-*`. Os links
  saem na ponte, na resposta (`_SEM_TICKETS`: todo `<a href="/os/tickets...">`); as regras `tk-*` ficam sem uso.
- **Fica** a linha de ticket que nasce junto da OS da Performance (a caixa "Gerar ticket", `api.nascer_ticket` →
  `tickets_nasce`, que usa `tickets_api`, `tickets_diario`, `tickets_escrita` e `tickets_spec`): é da criação de OS, não
  da tela. O `/os/api/acomp/<folio>/ticket` é o nº do chamado no fabricante (Acompanhamento de chamados) e também fica.
- **Sem a faixa de abas dentro do Nexus** (Levi: "quero que mantenha esse carregamento mas tire a visão de abas da parte
  de cima pois como já temos as abas laterais, fica redundante, para um sistema separado, quero passar a impressão de
  unidade!"). A ponte põe `.os-tabs{display:none}` no `_ESTILO_NEXUS` (some a faixa da casca e a da tela aberta
  sozinha); a casca continua guardando cada tela aberta, viva, e o menu lateral acende a de cada item já carregada. Sem
  o X de fechar, a ponte põe um teto no `abas.js` (`_ABAS_MAX` = 12 além do Início: os 9 itens da torre e mais três): ao
  abrir a 13ª, sai a acesa há mais tempo, nunca a ativa. Tudo na ponte: a cópia segue igual à do oem, e no 5090 a faixa
  continua. Prova: `test_dentro_do_nexus_sem_a_faixa_de_abas_e_as_telas_seguem_vivas`.

## A Área PCM como no app: Painel, Fila, Histórico e Temas (13/10/2026)

Levi: "Fila do PCM não está levando para a fila do PCM, referência é a fila do app desktop, nem painel do PCM nem
histórico nem temas. Também está demorando demais para carregar! Resolva". Desde 21/09 a web juntava o Painel e a Fila
numa tabela com um painel de aprovação menor que a ficha do app; o Histórico era uma tabela sem filtro; os Temas não
existiam. Agora são as páginas da `SolicPcmTab` (`steps/solic_pcm.py`, `historico_solic.py`, `temas.py` do app), com a
barra dela no alto de cada uma (`_solic_nav.html`: "‹ PCM", Nova solicitação, Painel, Fila do PCM, Histórico, Temas):

- **Portas do setor PCM** (`lancador.PORTAS_SETOR["pcm"]`, com os textos e os selos da Área PCM do app): Painel, Fila do
  PCM, Histórico de solicitações, Temas e a Clonagem de planos. O card PCM da tela inicial ganhou Painel e Temas.
- **Painel** (`/os/solicitacao/painel`): o kanban de três colunas com a régua do app (`coluna_de`), até 40 cartões por
  coluna (a contagem diz o total), a busca na tela (250 ms), as devolvidas para refazer contadas no alto. O cartão
  inteiro abre a Fila nele (`?sel=`): pendente para analisar, das outras colunas só para ler.
- **Fila do PCM** (`/os/solicitacao/fila`, `static/solic_fila.js`): a lista "AGUARDANDO APROVAÇÃO" à esquerda (nº,
  status, usina, ativo, quem e "há quanto", o tema) e a ficha à direita: o título no padrão do tema (clique edita; o
  escrito à mão não é trocado pelo tema), "o supervisor escreveu: ~~…~~", O PEDIDO (a observação: só o relato, grava ao
  sair do campo, com o bloco [PCM] de volta depois de uma linha em branco, como o app) e A DECISÃO (o técnico sugerido
  pré-escolhido, a data pretendida, as etiquetas do tema marcadas "(tema)" e a regra da PERFORMANCE, Tipo de tarefa,
  Classificação 1 = Programada e 2 = a disciplina do tema só em campo vazio, o Tema e a OS pai pela busca do
  `buscar_os_pai`, que guarda o ID, já escolhida quando veio da Nova solicitação, seção "Nova solicitação: o título é
  só o motivo, e a OS pai"); as subtarefas editáveis em faixa inteira; Aprovar (e passa para a próxima), Devolver
  ao supervisor e Mudar status (motivo obrigatório).
- **Histórico** (`/os/solicitacao/historico`, `static/solic_hist.js`): Criado por, a busca direta pelo nº (ignora os
  filtros; fora das 400 carregadas, busca no Fracttal), a busca ampla, Cliente / Usina em cascata / Tipo de ativo /
  Status, o Período (últimos 30 dias), Exportar (CSV com ; e BOM), Limpar filtros, ↻ e a atualização de 15 em 15
  minutos (por JSON: os filtros ficam); o Nº abre a ficha da solicitação (anexos, abrir a OS ligada, cancelar com nota) e
  a OS ligada abre o card da OS, o mesmo do Histórico de OS.
- **Temas** (`/os/solicitacao/temas`, `static/solic_temas.js`): a lista, a busca, "+ novo tema" e o cadastro do app
  (nome, tipo de equipamento do cadastro de ativos, tipo de OS, motivo, Classificação 1, etiquetas, subtarefas);
  Salvar / Descartar / Arquivar gravam pelo `temas_store`, o mesmo livro do app (o que se salva aqui vale para o app). As
  validações do app (nome obrigatório, a chave nasce do nome e nunca muda, nome repetido não entra) estão no
  `solic_web.tema_para_salvar`. Sem o `GRIDCO_SQL_TOKEN` a tela abre e não grava (403, com o motivo); no Nexus ele vem
  do `.env` do Nexus desde 19/10/2026 (seção "Trocar o responsável na tela do chamado").

**A mais que o app, de propósito:** as datas em horário de Brasília nas quatro páginas (o app mostra a do Fracttal crua
no Painel e na Fila, 3 h adiantada); o "só para ler" vale para a solicitação aberta do Painel, não para a Fila inteira;
o Devolver ao supervisor é a mudança para "Reaberta (refazer)" com o motivo (no app ele dizia "Ainda não implementado");
trocar o tema traz as subtarefas dele (a lista editada só sai com a pessoa dizendo que sim — no app ela ficava);
GARANTIA posta à mão traz a PERFORMANCE na hora; a OS pai digitada e não escolhida avisa em vez de sumir; o anexo
obrigatório vai na aprovação (`solic_web.subs_para_api`: a web o perdia); Temas mostra o valor fora da lista fixa (o
"Limpeza e Conservação" da Vegetação: no app o combo caía no vazio e salvar apagava) e pergunta antes de descartar
alteração não salva.

**Quem entra na Área PCM** (Levi, 13/10/2026: "Só o setor PCM ou administrador! Quem não é nenhum dos dois recebe a
notificação!"). A Fila do PCM (aprovar, devolver, mudar status, gravar a observação, recarregar o catálogo) e os Temas
(salvar, arquivar) são do setor PCM e dos administradores do Nexus; no app essa área pede a senha do PCM. Quem decide é a
ponte (`ponte.area_pcm`): administrador passa sem ler nada; o resto, pelo setor de Base → Acessos → Pessoas e setores, pelo NOME
("PCM", sem acento nem caixa). Sem saber o setor (banco fora, Nexus sem a `NEXUS_PESSOA_HMAC`), fecha — só o
administrador passa. A decisão vai ao clone no pedido (`request.environ["os_web.area_pcm"]`): no lugar da Fila e dos
Temas vem o aviso (`solic_sem_acesso.html`, com a barra de sempre e o setor da pessoa), e as gravações voltam 403 com o
mesmo aviso (a tela mostra no aviso de canto). O Painel, o Histórico e a Nova solicitação seguem abertos (são a Área do
Solicitante do app); fora da Área PCM o cartão do Painel abre a ficha no Histórico (`?ficha=`), e não a Fila. Sem a
chave no pedido (o OS Creator sozinho, o 5090), a área fica aberta como sempre foi. Prova: os testes
`test_fora_da_area_pcm_*`, `test_a_regra_do_nexus_setor_pcm_ou_administrador` e
`test_pela_ponte_quem_nao_e_do_pcm_recebe_o_aviso` (cinco mutações, todas pegas).

**A velocidade** (o "demorando demais"): cada abertura da Fila fazia de 7 a 10 pedidos ao Fracttal, um depois do outro
e sem memória (as 400 solicitações, o pessoal de 100 em 100, as etiquetas, o catálogo de status), e o Histórico baixava
as 400 de novo. Agora (`rotas_solic.py`):
- Painel, Fila e Histórico leem a MESMA lista, guardada por `LISTA_TTL` (120 s) por pessoa; os catálogos por
  `CATALOGO_TTL` (30 min); quem grava (criar, aprovar, status, observação, cancelar, tema) esquece a lista;
- a carga fria pede tudo ao mesmo tempo (`_ao_mesmo_tempo`, com o executor que leva a sessão do Fracttal para as
  threads): custa a leitura mais lenta, não a soma;
- o catálogo de ativos VENCIDO (mais de 24 h) não segura mais a página: o nome das solicitações vem do arquivo como
  estiver e o download dos ~22 mil ativos (mais de cem pedidos, minutos) vai para uma thread (`_indice_ativos`,
  `_renovar_por_tras`). Quem resolve o ativo da OS na aprovação continua com o catálogo em dia (espera o download que
  já está em curso, sem começar outro);
- a página do setor PCM pede a lista ao abrir (`/os/api/solic/aquecer`): a porta escolhida já abre com ela.

Prova: `tests/test_oscreator_solic_pcm.py` (29 testes: as páginas, as gravações, a lista pedida uma vez para as três
páginas, a carga fria paralela — cinco leituras de 0,3 s em menos de 1 s —, o catálogo vencido que não segura a
página; seis mutações, todas pegas). As telas foram conferidas no Chrome sem janela, no escuro, no claro e a 760 px,
com o Fracttal de mentira, e os cliques (aprovar, mudar tema, observação, OS pai, devolver) pelo próprio JavaScript da
página. Falta o olho do Levi com os dados de verdade (a sessão do Fracttal é dele).

## Sem o topo do OS Creator dentro do Nexus (13/10/2026)

Levi, com o print do topo ("LM Levi Maia ADMINISTRATOR sair") embaixo do topo do Nexus: "Quero que essa visão de
cabeçalho ao lado de sair vá para o cabeçalho do Nexus e suma esse 2° cabeçalho ... Dá a impressão que é uma tela dentro
de uma tela!". A ponte põe no `<head>` o `_MARCA_NO_NEXUS`: a tela cujo pai é o Nexus (`<html data-nexus>`: a casca `/os/`,
o login, o card da OS) ganha `os-no-nexus` antes de pintar, e o `_ESTILO_NEXUS` some com o `.os-header` e o `.os-sep` dela.
O avatar, o nome, o perfil do Fracttal e o Sair moram no topo do Nexus (`nexus/casca/CLAUDE.md`, "Um cabeçalho só"). O
"topo sempre à mostra" de quem o tinha recolhido vale só fora do Nexus. Aberto sozinho no navegador (sem o Nexus em
cima), o OS Creator segue com o topo: é o único lugar com o nome e o "sair". O HTML do clone não muda (o oem segue igual).
Prova: `tests/test_sem_segundo_cabecalho_13_10.py`.

## O círculo de carga tem prazo (13/10/2026)

Levi: "As vezes o OS Creator Web fica em um loop infinito, isso é por causa do fractal?". O print era o "Carregando…" do
`carga.js` sobre o Performance, depois do clique num cartão. Não é laço: o círculo espera a página seguinte e não tinha
prazo. Naquela tarde, das 16:50 às 16:53, o Nexus do servidor não respondeu nem o `/saude` (as 16 threads presas; desde
então o `casca/presos.py` do Nexus anota em quê, e o administrador vê no Início). As contagens dos cartões já tinham
chegado, então o catálogo de ativos não era a espera daquele clique.

- **Aos 15 s** a caixa conta: "Esperando o servidor há N s" (numa linha própria, `.carga-espera`: a `.carga-sub` é do
  progresso do Histórico).
- **Aos 45 s** (o prazo de uma chamada ao Fracttal no `api._rpc_call`): "Está demorando mais que o normal ... O Fracttal
  pode estar lento ou o Nexus, ocupado.", com **Tentar de novo** só onde repetir é seguro (abrir uma página por link;
  formulário e `OsCarga.buscar` nunca, para não gravar duas vezes) e **Fechar** (o pedido segue; se a resposta chegar, a
  página segue normal). Tentar de novo zera a conta.
- **No Histórico**, que mostra o progresso, o prazo conta do último pedido ao Fracttal que terminou: busca grande andando
  não é demora.
- Onde o Fracttal segura uma página (para quem for mexer): a tela inicial (`/os/`) espera o selo
  `api.contar_minhas_analises()` (até 2 chamadas de 45 s) antes de desenhar. O catálogo de ativos vencido não segura
  mais o pedido desde 24/10/2026 (seção "O catálogo de ativos vencido por trás").
- **Prova** (13/10/2026): Nexus descartável com o RPC do Fracttal mudo, clique no cartão do Performance dentro do Nexus
  (a moldura `/os/performance` dentro da casca `/os/`): aos 20 s "Esperando o servidor há 20 s"; aos 50 s a mensagem e os
  dois botões; Tentar de novo zerou a conta e o círculo seguiu; aos 48 s de novo os botões; Fechar escondeu o círculo.
  Testes do tema claro e da torre verdes; oem: `--aplicar` levou `carga.js` e `os.css`, 680 testes web verdes lá.

- **A gravação sem resposta** (21/10/2026): Levi criou uma OS pelo Performance › Trackers às 10:03 e a tela disse
  "SyntaxError: Failed to execute 'json' on 'Response': Unexpected end of JSON input". O deploy das 09:57 reiniciou o
  servidor no meio do pedido, o proxy devolveu a resposta vazia, e a OS tinha sido criada no Fracttal (o ticket da aba
  Trackers, que vem depois, não). Quem lê "erro" cria de novo e duplica. Agora o `OsCarga.buscar`, numa GRAVAÇÃO (método
  que não é GET), troca a resposta vazia, o erro sem JSON (o 502 do proxy, a página de erro) e a rede que caiu por uma
  resposta em JSON com `erro` = "O servidor não respondeu (pode ter sido reiniciado agora). A gravação pode ter sido
  feita: confira no Fracttal antes de tentar de novo." e `sem_resposta: true`. Todas as telas que gravam passam por ele
  e já mostram o `erro` do JSON. A leitura e a resposta da própria rota (o erro dela em JSON, o PDF) passam como vieram.
  Prova: `tests/test_oscreator_sem_resposta_21_10.py` (o `carga.js` no node com uma página de mentira). O que corta o
  pedido, o restart do deploy no meio de uma gravação, está na fila do `DESEMPENHO.md`.

## Debaixo do /nexus (porta única, 09/10/2026)

Levi: "a partir de segunda quero o Nexus como link principal". O servidor serviu o Nexus em `app.gridco.com.br/nexus` até a
fase 4 (hoje na raiz; `NEXUS_PREFIXO=/nexus` é a volta, `nexus/casca/CLAUDE.md`), e o clone escreve `/os/...` a partir da raiz em ~220 lugares
(templates, `.js` e o JSON das rotas): ao pé da letra, levavam ao `/os/` da PLATAFORMA. O clone continua idêntico ao do
oem (roda sozinho na raiz, no 5090); quem põe o prefixo é a ponte, na resposta, só quando há prefixo:

- o clone recebe o `SCRIPT_NAME` do Nexus: o `url_for` dele já sai com `/nexus`, e o cookie dele fica em `/nexus/os`
  (`_SessaoDoClone`, que troca o `/os` fixo do `criar_app`);
- HTML, JavaScript e JSON: `"/os`, `'/os`, `` `/os `` e `(/os` ganham o prefixo (`_no_prefixo`). Fica de fora o
  `value="/os/..."`, que é o `next` do formulário de login: o clone só aceita `next` sem prefixo (`_destino_local`). O
  `next=/os/...` dentro de um endereço também fica (vem depois de `=`);
- as expressões regulares do clone que testam o caminho (`/^\/os\/[^/]/` e afins no `abas.js`, `/^\/os(\/|$)/` no
  `carga.js`) também ganham o prefixo, escrito como na expressão (`^\/nexus\/os`). Revisão de 10/10/2026: só as aspas
  e o parêntese eram cobertos, e debaixo do `/nexus` as regras das abas diziam "não é tela nossa": todo item da torre
  OS Creator abria o Início, os cartões não abriam aba e o "Clonar esta OS" caía no Início
  (`test_as_abas_do_os_creator_funcionam_debaixo_do_prefixo`, que roda as regras do `abas.js` servido no node);
- todo `.js` do clone sai reescrito com marca de versão própria (a pergunta "mudou?" vale para a versão reescrita, como
  já era com o `abas.js`);
- o `Location` que começa por `/os` ganha o prefixo; o `next` da consulta que chega com ele (o JavaScript do clone monta
  o `next` com o `location.pathname`) sai dele antes de ir ao clone;
- as páginas do Nexus que falam com o clone (o menu da torre, o card da OS, a Aprovação de OS, a PT) mandam o endereço
  com o prefixo e o `next` do login do OS Creator sem ele.

Na raiz nada disso roda: a resposta é a de sempre, byte a byte (`test_todo_js_do_clone_sai_com_o_prefixo_e_na_raiz_sai_igual`).
Prova: `tests/test_prefixo.py` (o rastreador entra no OS Creator embutido com um login de mentira e confere cada página e
cada `.js` do clone).

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

## A tela inicial não espera o Fracttal (14/10/2026)

Levi, 14/10/2026 às 09:30: "quando clico no OS Creator, fica carregando por um bom tempo". No mesmo minuto o /saude do
Nexus do servidor (que não lê nada) levou de 0,5 a 17 s e chegou a estourar 60 s, com a plataforma e a API do banco, no
mesmo servidor, em 0,2 s: as threads do Nexus estavam presas. A tela inicial (`/os/`) só saía depois do selo "N
atribuídas a você" do card Performance, um pedido ao Fracttal (até 45 s com ele lento), e cada abertura da Performance
pedia de novo os planos e as subtarefas (o "GET /os/api/performance/contagens, 2 min 50 s" dos pedidos presos de 13/10).

- A tela inicial sai na hora: o selo vem da memória (2 min por pessoa, `rotas._selo_guardado`) e, sem ele, o navegador o
  pede depois em `/os/api/selo`; o selo nunca segura a tela nem a derruba.
- **A sessão do Fracttal caída leva ao login pelo selo** (20/10/2026). Antes, era a própria tela inicial que pedia o selo e
  voltava ao login com o aviso; com o selo depois da tela, o 401 dele era ignorado, e a pessoa ficava na tela inicial
  até o clique seguinte (achado pelos 3 testes do oem que falhavam desde 14/10). O script do `home.html` faz como as
  outras telas (`acomp.js`): 401 com `login` leva ao `/os/login?next=...`, que mostra "A sessão do Fracttal caiu"; no
  Nexus, a ponte já encerrou a sessão e o portão leva ao Entrar. Conferido no navegador numa cópia com o Fracttal falso:
  `GET /os/` 200, `/os/api/selo` 401, `/os/login?next=/os/` com o aviso. Sem o selo pedido (o da memória ainda vale),
  quem descobre a queda é o próximo pedido ao Fracttal, como em qualquer tela.
- As subtarefas de cada plano da Performance (os "N subtarefas" dos cards) ficam 6 h na memória (`CONTAGENS_TTL_S`): são
  as mesmas para todo mundo e só mudam quando o PCM mexe num plano. Erro não fica guardado.
- Levado ao oem pela `ferramentas/sincronizar_oscreator.py --aplicar` (sem commit lá: o oem é público).
- Prova: `tests/test_oscreator_abre_sem_esperar_14_10.py` (a tela não pede nada ao Fracttal; o selo uma vez a cada 2 min;
  o Fracttal fora não fica guardado; a contagem uma vez em 6 h; o script do selo rodado no node com a resposta da rota:
  401 vai ao login, o selo que chega aparece). No oem, `test_os_web_home::test_selo_do_card_performance` e os dois de
  `test_os_web_sessao` (o JWT da pessoa no selo, a sessão caída) cobram o selo pelo `/os/api/selo` desde 20/10/2026.

## Fila do PCM: a OS nasce programada na data sugerida (15/10/2026)

Levi, 15/10/2026: "No OS Creator em fila a OS programada do PCM tem que ser a data sugerida da solicitação!". Até então a
data que o supervisor sugere (o bloco [PCM] da observação) só aparecia na ficha da Fila e a OS nascia programada na hora
da aprovação, como no app de mesa.

- Ao APROVAR, o servidor lê a data sugerida da própria solicitação (`solic_web.data_sugerida_dt`: com hora, ou só o dia,
  que vira 08:00 como no app; horário de Brasília) e a manda como data PROGRAMADA da OS (`api.aprovar_solicitacao(...,
  prog_date=)` → `clonar_os` → `create_os_rpc(prog_date=)`: `date_maintenance`, `initial_date` e o fim 20 min depois).
  A data do evento segue sendo a da aprovação. Sem data sugerida legível, como antes: programada agora.
- A confirmação e o aviso de "OS criada" dizem para quando ela ficou programada.
- **O PCM troca a data na decisão (20/10/2026).** O programador do PCM: "não consigo alterar a data, o campo não abre
  mais". No app de mesa o "Data:" da decisão é um `_CampoClicavel` com o calendário, que começa na sugerida; na web
  ele era só texto. Agora é o `<input type=datetime-local id=fl_data>` no mesmo traço tracejado dos outros valores,
  com a sugerida (`data_sug_iso`); o aprovar manda `data_programada` e o servidor usa a do campo no lugar da sugerida
  (`solic_web.data_programada_escolhida`: só o formato do campo, data que existe e até um ano de hoje; fora disso, 400
  e nada é criado). Vazio, a sugerida (ou agora, sem sugerida). A confirmação diz "(data trocada na decisão)".
- **Os dois jeitos de escrever a data (19/10/2026).** A Nova solicitação web gravava "2026-10-21 08:00" (o valor do campo
  de data) e a leitura só entendia o do app ("21/10/2026 08:00"): a SS 3944 ficou sem data, a OS 16784 nasceu programada
  na hora da aprovação, e a confirmação dizia "programada para 2026-10-21 08:00" (o texto cru). Agora a leitura entende
  os dois (`solic_web._FORMATOS_SUG`; vale para as solicitações que já estão na fila), a Nova solicitação grava como o app
  (`solic_web.observacao`), e a confirmação só promete a data que o servidor leu (`data_sug_iso`); a que não foi
  entendida aparece como tal. A OS que já nasceu com a data errada se acerta à mão no Fracttal web (a API não edita data
  de OS criada).
- O app de mesa (`steps/solic_pcm.py`) não mudou. Prova: `tests/test_oscreator_solic_pcm.py`.

## Fila do PCM: o tempo estimado na decisão (21/10/2026)

Levi: "Gostaria que o PCM conseguisse mudar o tempo estimado para cada atividade na fila de PCM". Cada solicitação da
Fila vira uma OS de uma tarefa, e a tarefa nascia sempre com 10 min (o `duration: 600` do `create_os_rpc`, o que o web
manda no formulário da tarefa não planejada; `api.DURACAO_OS_AVULSA`). As subtarefas do Fracttal não têm tempo: o tempo é
da tarefa.

- **O campo:** "Tempo estimado:" logo abaixo da Data, em HH:mm, começando em 00:10 a cada solicitação; a seta (e as
  teclas para cima e para baixo) anda de 30 em 30 min, como o tempo da linha na tela PCM (`pcm.js`, o `_TempoTarefa` do
  app); o que não é tempo volta ao último válido. Vai de 00:01 a 23:59.
- **O caminho:** o aprovar manda `duracao` em segundos só quando o PCM mudou o tempo (`null` sem mexer); o servidor confere
  (`solic_web.duracao_escolhida`: número inteiro de 60 a 23:59; fora disso, 400 e nada é criado) e passa
  `api.aprovar_solicitacao(..., duracao=)` → `clonar_os` → `create_os_rpc(duracao=)`: `duration` e `real_duration` com o
  tempo (o web manda os dois iguais) e o fim da janela da programação = início + tempo, como o `create_planned_os` (14/09).
  Sem o tempo, o pedido de sempre (10 min, a janela de 20), e nenhum outro caminho (COS, Chamados, PCM, Clonar) muda.
- A confirmação e o aviso de "OS criada" dizem o tempo estimado. Na retomada (a tarefa da solicitação já existia de uma
  tentativa anterior), o tempo dela fica o da primeira tentativa.
- **Prova:** `tests/test_oscreator_solic_pcm.py::test_o_pcm_troca_o_tempo_estimado_na_decisao` (a rota) e
  `::test_o_tempo_estimado_vai_na_tarefa_da_os` (o pedido ao Fracttal, de mentira). No app de mesa a Fila não tem o campo.

## Nova solicitação: o título é só o motivo, e a OS pai (24/10/2026)

Levi: "o título está com um subtexto de "[Ativo] - Motivo": O certo seria só motivo pois o ativo já tem que ir no título
automático!" e "ao lado de buscar ativo deixe um espaço do lado direito para "OS Pai" quando preenchido e o PCM for criar
a OS na fila do PCM já vai vincular aquela OS como OS pai!".

- **O título:** a pessoa escreve só o motivo (o tema põe o motivo dele, sem a marca). O servidor põe o nome curto de CADA
  ativo na frente (`solic_web.titulo_do_ativo`: "Troca do cabo" → "[Inversor 1.5] - Troca do cabo"), uma chamada por
  ativo. Até 24/10 só a marca `[Ativo]` virava o nome, e o título escrito sem ela saía sem o ativo. A marca ainda vale (uma
  tela aberta antes do deploy), e o título que já começa por "[o ativo]" não o repete. A prévia embaixo do campo usa a
  mesma regra.
- **A OS pai:** no bloco 1, à direita do Buscar ativo (2/3 e 1/3; abaixo dele a menos de 900 px), opcional. É a busca da
  Fila (`/os/api/pcm/os-pai`): digitou → 300 ms → a lista; escolher (clique, setas e Enter) guarda o id; digitar de novo
  desfaz; número digitado e não escolhido não deixa criar. Usa as classes da busca comum (`.osb-*`): nada de cor nova.
- **O caminho até a Fila:** a solicitação do Fracttal não tem campo para isso, então a OS pai vai no bloco [PCM] da
  observação de cada solicitação, como o tema e a data sugerida: "OS pai: 16784 (id 555)" (o nº para quem lê no Fracttal
  web, o id para a Fila mandar no `id_parent` sem buscar de novo; `solic_spec._CAMPOS`). O servidor recusa (400, nada
  criado) a OS pai torta (`solic_web.os_pai_escolhida`). A Fila lê de volta (`solic_web.os_pai_do_bloco`, a `ficha` com
  `os_pai` e `os_pai_id`) e abre com ela escolhida; o PCM troca ou apaga, e a confirmação do Aprovar diz "filha da OS N".
  Só o nº na linha (escrito à mão no Fracttal web): o campo vem com ele e o Aprovar pede a escolha na lista. O app de mesa
  ignora a linha (rótulo que ele não conhece).
- **Prova:** `tests/test_oscreator_solic_pcm.py` (os testes de 24/10: o título, um título por ativo, a OS pai no bloco de
  cada solicitação, a torta que não cria nada, o bloco lido de volta, a Fila com ela escolhida e o aprovar com o
  `id_parent`, a tela). Na bancada (as páginas do fixture, a busca de mentira), a 1280 e a 375 px, no escuro e no claro: a
  prévia "[Inversor 1.5] - Troca de ventilador", a OS pai escolhida pelo teclado indo no corpo do criar, o nº não
  escolhido barrado, a Fila com a 16784 e a confirmação "filha da OS 16784", sem rolagem lateral. No oem, o
  `test_os_web_solic_27_09.py` (fora do git de lá) passou a cobrar a regra nova junto com a sincronia.

## Nova solicitação e Criar OS do zero com a sugestão pelo endereço (24 e 25/10/2026)

Levi, sobre a OS do Quadro da equipe da Engenharia: "Ao invés do botão "Abrir OS" bote um botão de "Solicitar OS" que já
vai preencher o ativo pelo o da OS original, a pessoa pode até mudar o ativo mas sai como aquela OS como OS pai".

- **O endereço:** `/os/solicitacao?ativo=<código>&os_pai=<id>&os_pai_folio=<nº>&data=<AAAA-MM-DDTHH:MM>` abre a Nova
  solicitação com o cliente, a usina e o ativo marcados, a OS pai escolhida e a data do incidente dela (Levi, 24/10/2026:
  "a data do incidente deve ser a mesma da OS pai"; `tradicional_web.data_sugerida`: torta ou no futuro fica de fora, e
  o campo começa em agora) (`tradicional_web.sugestao`, uma regra só para as duas telas, e `onde_do_ativo`; na página,
  o `#sug` com os `data-sug-*` e o `sugerir()` no fim do script). A cascata virou duas funções que devolvem a promessa
  (`carregarUsinas`, `carregarAtivos`), para a sugestão esperar cada etapa.
- **O que fica de fora:** o ativo que o catálogo não tem e a OS pai torta (o criar recusa a torta de qualquer jeito); sem
  nada no endereço, a tela abre como sempre (o oem usa a mesma página).
- **Quem chama:** a página da OS do Quadro da equipe (`/t/engenharia/equipe/os/<nº>`), pelo `/os/_nexus/ir` (abre na
  torre OS Creator do Nexus). O comentário daquela página vai à nota da OS pela ponte
  (`/os/_nexus/engenharia/os/<id>/comentar`, só do Nexus, na sessão do Fracttal da pessoa; `editar_nota_os` com a regra
  do card: OS concluída, cancelada ou de várias tarefas não deixa).
- **Criar OS do zero (25/10/2026):** o mesmo endereço em `/os/tradicional?` (o "Criar OS" da OS do Quadro da equipe;
  Levi: "Fará os mesmos preenchimentos automáticos que já faz na solicitação"): o Passo 1 abre com o cliente, a usina e
  o ativo marcados (a busca mostra o ativo) e a data do incidente no campo; o Passo 4 abre com a OS pai escolhida
  (`ospaiSug`), e a OS seguinte, depois de gerar, não herda a OS pai (como na Solicitação).
- **As subtarefas padrão do Criar OS do zero (25/10/2026):** Levi: "quero que essas subtarefas já fiquem como padrão na
  parte de criação de OS do zero!". O Passo 3 abre, e volta depois de gerar, com "Descreva a atividade realizada" e
  "Ficou alguma pendência? Se sim, descreva" (`tradicional_web.SUBS_PADRAO`, no `data-subs-padrao` da página); a pessoa
  edita, tira (fica o mínimo de 1) ou põe mais. São as mesmas palavras da `BASE` do `solic_spec`, e a primeira é a que a
  página da OS da Engenharia lê nas OS filhas. Vão como as outras do Tradicional: tipo Texto, sem obrigatoriedade.
- **Prova:** `tests/test_oscreator_solic_pcm.py` (os de 24/10 da sugestão) e `tests/test_oscreator_criar_os_25_10.py`.
  Levado ao oem em 24/10/2026 pela `ferramentas/sincronizar_oscreator.py --aplicar`, com o OK do Levi (rotas_solic.py,
  tradicional_web.py e solic.html); o de 25/10 (rotas_solic.py, rotas_tradicional.py, tradicional_web.py,
  tradicional.html e tradicional.js) vai com o OK dele.

## Criar OS: o ativo no título de cada OS e o aviso das usinas (26/10/2026)

O caso: as OS 16995 (um inversor de uma usina) e 16996 (um tracker de OUTRA usina) nasceram no mesmo minuto, da mesma
pessoa, com o mesmo responsável, programada, duração e etiqueta, e o título "[<código da usina do inversor>] - Inspeção do
Inversor com alarme de Ventoinha" nas duas. Foi uma geração só no Criar OS (Tradicional): o ativo marcado continua
marcado quando se troca de usina (o `Step1._checked` do app de mesa, de propósito), a descrição digitada ia igual para
cada OS, e o tracker marcado em outra usina levou o título escrito para o inversor. Levi escolheu: o ativo entra sozinho
no título e a tela avisa quando os marcados são de mais de uma usina.

- **O título:** a pessoa escreve só a ação; cada OS (e cada tarefa, na agrupada) sai "[Ativo] - descrição", com a regra da
  Nova solicitação (`solic_web.titulo_do_ativo`: o nome curto do catálogo, a marca `[Ativo]` vale, o que já começa pelo
  ativo não repete). Vai pelo `por_ativo` do `create_work_orders_bulk` e do `create_work_orders_agrupada` (o mesmo caminho
  do COS e da Engenharia); o `desc` posicional segue o digitado (`tradicional_web.montar_payload`, com as frases do tipo
  que a rota já guarda por 1 h). O Passo 2 mostra "Vai sair “[Inversor 5.1] - …”" com o 1º marcado.
- **As usinas:** cada marcado guarda a usina em que foi marcado (`comUsina`). Com mais de uma, o Passo 1 diz "N
  marcado(s) em K usinas diferentes", o Passo 4 mostra em âmbar (`.osb-aviso`, sem cor nova) quais ativos de quais usinas,
  e a confirmação repete a lista antes de criar. A marcação entre usinas continua valendo (é o app de mesa).
- **Prova:** `tests/test_oscreator_criar_os_titulo_26_10.py` (uma OS por ativo e a agrupada com o título de cada ativo, a
  marca e o título que já tem o ativo, o payload puro, a tela). Na bancada (o Criar OS do fixture, a cascata de mentira
  com duas usinas), a 1280 e a 375 px, no escuro e no claro: o inversor marcado na usina A segue marcado na B, o Passo 1
  com "2 marcado(s) em 2 usinas diferentes", a prévia do título, o aviso âmbar do Passo 4 e a confirmação com as duas
  usinas, sem rolagem lateral. No oem, o `test_os_web_tradicional.py` passou a cobrar o `por_ativo` junto com a sincronia
  (cópia de trabalho; sem commit lá).

## Trocar o responsável na tela do chamado (Garantias, 19/10/2026)

Levi, 19/10/2026, em Nexus > Chamados > Garantias: "ao clicar na OS em responsável dê para alterar o responsável da OS que
nem fazemos no card da OS no histórico de OS Creator!"

- Nos Dados da tela do chamado (`acomp_os.html`), o "trocar" ao lado do nome abre o MESMO diálogo do card: o
  `<template data-dlg="responsavel">` saiu do `os_detalhe_conteudo.html` para `templates/_dlg_responsavel.html`, que as duas
  telas incluem (mudou o diálogo, muda nos dois). A busca digitável, o Esc e o "Atribuir" são os de sempre.
- As ações são as do `os_acoes.js`: além do `.det` (o card), ele acha uma caixa com `data-os-acoes` (e `data-wid`,
  `data-folio`). Com `data-no-lugar`, a troca é escrita ali mesmo (`trocouNoLugar`: o nome, o "Hoje está com" do
  diálogo e a mensagem), porque não há card para recarregar. A cor de "no nome de outra pessoa" vem do servidor
  (`da_equipe` na resposta de `/os/api/os/<id>/responsavel`, a regra do quadro, `acomp_web.da_equipe`).
- A rota do responsável ajusta o quadro guardado que mostra a OS com quem ficou (`rotas_acomp.esquecer_se_no_quadro`;
  até 20/10/2026 ele saía da memória, e a volta ao quadro relia o Fracttal). OS que não está em nenhum quadro guardado (a
  troca pelo card do Histórico, numa OS que não é de chamado) não faz ninguém esperar a releitura. A troca já está no
  Fracttal quando isso roda: erro aqui não vira erro na tela.
- Conferido numa bancada local com o Fracttal falso: duas trocas seguidas (para a equipe, nome sem cor; para outra
  pessoa, âmbar), o "Hoje está com" do diálogo acompanhando, o quadro e a tela relidos com o nome novo.
- **As observações não abriam para escrever** (Levi, no mesmo dia: "também não está sendo possível digitar
  observações"). A tela dizia "Este servidor não tem a credencial de escrita do banco da Gridco": o Nexus lê o `.env`
  para o `app.config` e não mexe no ambiente (`nexus.config.ler_ambiente`), e o clone procura o `GRIDCO_SQL_TOKEN` no
  ambiente (`tickets_escrita._token`: ambiente, cofre do Windows, pasta do usuário, tokens.txt). No servidor não há cofre
  nem pasta do usuário, e o `.env` do clone só traz a credencial do Fracttal. Desde 30/09 (o clone no servidor) as
  observações, os modelos do Controle de fornecedores e os temas abriam só para ler. A ponte agora põe o token do Nexus
  no ambiente ao criar o clone (`ponte.token_do_banco_para_o_clone`; o que já estiver no ambiente vale mais). Nos testes
  não (o ambiente é do processo inteiro), e o envio dos tickets não muda: direto só com `RELAY_DIRETO_ENV=1`.
- Prova: `tests/test_oscreator_garantia_responsavel.py`.

## O PDF da OS, com a seta na cadeia do chamado (Garantias, 19/10/2026)

Levi, 19/10/2026: "Gostaria de incluir a opção de baixar o mesmo PDF que o fractall gera" ("pelo o que entendo ele baixa
várias imagens e incluir no PDF") e "inclua a opção de baixar na cadeia de chamado, uma seta de download!".

- **Não há PDF pronto no Fracttal para buscar:** a web dele monta o PDF no navegador, com os pedidos do curl do Levi
  (o cabeçalho, as tarefas, as subtarefas, as fotos das subtarefas, os arquivos de cada tarefa, os recursos e cada foto
  baixada do S3). O servidor junta o mesmo com o que o card da OS já lê: `api.get_os_detalhes` (agora com o `status_id`),
  os anexos do card (`_anexos_da_os`) e `api.get_os_recursos` (novo: `tasks.work_orders_resources_all_list`, o pedido do
  print; os campos são os do lançamento que o App de Campo copia desde a v274). Recurso que o Fracttal não devolveu sai
  no PDF como "não consegui ler", e não como "nenhum".
- **O PDF** (`os_web/os_pdf.py`, reportlab): faixa navy com o logo e a OS; o status com a cor do card; os dados da OS;
  cada tarefa com as subtarefas e as respostas, na ordem do card; os recursos; as observações da OS; as fotos, duas por
  linha, num quadro da mesma altura (as das subtarefas com a subtarefa embaixo; a foto da OS que já é de subtarefa não
  repete), reduzidas a 1000 px (JPEG 72, deitada pelo EXIF fica em pé); os outros anexos pelo nome. Foto que não veio
  do S3 sai com o quadro vazio dizendo isso; mais de 200 fotos, o PDF diz quantas ficaram de fora. `modelo()` é o
  conteúdo (os testes conferem nele) e `gerar()` desenha; o reportlab e o Pillow só são importados ali.
- **A foto entra no PDF como saiu do `reduzir`** (20/10/2026; Raio-X das 09:56: um PDF ~2 min no servidor, em `gerar`).
  Dada como `Image(BytesIO)`, o reportlab decodificava cada foto em RGB só para dar nome a ela e guardava o RGB até o
  fim (2,25 MB por foto). `os_pdf._JpegPronto` entrega o JPEG pelo caminho que o reportlab usa para JPEG de arquivo
  (`jpeg_fh`, embutido como veio, DCTDecode) com o hash do JPEG como nome (a mesma foto duas vezes vai uma vez). Medido
  no PC, com o reportlab já carregado: 200 fotos, `gerar` de 3,2 a 4,0 s e +1 GB para 0,3 s e +20 a 27 MB; a rota
  inteira, com o Fracttal falso e sem rede, de 7,7 a 8,3 s e +1.068 MB para 5,2 s e +128 MB. O PDF é o mesmo: páginas,
  texto, as imagens byte a byte e o desenho de cada página (só o nome interno das imagens muda). Se um dia o reportlab
  mudar esse caminho, o teste quebra: `test_o_pdf_embute_a_foto_como_veio_sem_decodificar_de_novo`.
- **A cópia reduzida de cada foto fica guardada** (20/10/2026; Levi: "se a saída for óbvia, faça"):
  `os_pdf.reduzir_guardada`, na pasta `os_pdf_fotos` do `api._data_dir()`. Reduzir custa ~90 ms de CPU por foto no PC,
  e a mesma foto volta noutro PDF (a mesma OS de novo; a foto que o OS Creator subiu em várias OS). A chave é o hash da
  foto ORIGINAL, e não o caminho no S3: outro arquivo com o mesmo nome na mesma OS apaga o primeiro (os Anexos da
  Solicitação da Engenharia, acima), e o caminho voltaria com a foto errada. Por isso a foto ainda é baixada a cada PDF;
  só não é reduzida de novo.
  A cópia é gravada com outro nome e trocada de uma vez (o reinício de cada push não deixa JPEG pela metade); a foto que
  já cabe não é guardada. A cada PDF, a rota varre as cópias sem uso há 30 dias e segura a pasta em 1 GB, as mais
  antigas primeiro. Medido no PC, sem rede: 200 fotos, o 2º PDF da mesma OS de 5,1 a 5,5 s para 0,8 s (CPU de 19 a 20 s
  para 0,9 s); o 1º, 0,3 a 0,8 s mais lento (o hash e as cópias, 18,9 MB). Prova: os testes de "a cópia reduzida
  guardada" e `test_o_segundo_pdf_da_mesma_os_nao_reduz_as_fotos_de_novo`.
- **A tela:** em "A cadeia do chamado" (`acomp_os.html`), uma seta em cada OS (de campo, inspeção e o acompanhamento).
  O clique (`os_acoes.js`, `[data-os-pdf]`) faz como o "Baixar todos": `POST /os/api/os/pdf` com o nº (e o id, quando a
  tela já sabe) monta o PDF no disco com o círculo de carga, e o arquivo baixa por `GET /os/api/os/pdf/<token>` (10
  minutos, só para quem pediu; o link do .zip não o entrega). O aviso (foto que não veio, OS que não existe) aparece
  embaixo da cadeia, em vermelho, nunca em alert().
- Conferido numa bancada local com o Fracttal falso (as três setas, o download, o aviso de OS que não existe) e numa
  amostra de 3 páginas com 7 fotos. Falta o olho do Levi com uma OS de verdade (o Fracttal só abre com a sessão de cada
  pessoa). Prova: `tests/test_oscreator_os_pdf.py`.


## O Histórico sem repetir o Fracttal (19/10/2026)

Levi, 19/10/2026: "o que causa essa busca de 2.000, todas as buscas são necessárias?" e "tem como atualizar só o dia
somando com o que já carregou ou tem que carregar tudo de novo?". No Raio-X do servidor (17:15) o `GET /os/historico`
ficou 43 s montando a página e outro ficou 2 min esperando o Fracttal. A Visão COS (e o "Criado por: Todos") pede as OS
de todos os criadores em 30 dias, que passam de 2.000: cada carga eram ~26 pedidos (10 páginas de 200 OS e 16 lotes
com as tarefas de 130 OS), repetidos para cada pessoa (a memória era por pessoa), a cada atualização automática de
10 min de cada aba (que passava por cima da memória) e a cada ↻; e as 2.000 linhas eram montadas a cada pedido.

- **Uma lista para quem vê o mesmo** (`os_web/historico_store.py`): a de "Todos" é uma só; a 1ª visita de cada pessoa
  confere, com 1 pedido de 1 linha na sessão DELA, se o Fracttal dá a ela o mesmo total (±1%, ou 2 OS); quem vê outro
  total (visão restrita no Fracttal) segue com a lista dela. As listas de cada pessoa ("criadas por mim", "atribuídas
  a mim") seguem por pessoa.
- **A lista guardada abre na hora**; vencida (3 min), se renova por trás, uma renovação por vez: só as OS criadas
  desde a mais nova guardada (menos 10 min de margem; 1 ou 2 pedidos) e, a cada 10 min, a lista inteira. A OS do
  Fracttal não diz quando foi alterada (conferido no REST em 19/10/2026: só criação, programada, evento, início, fim e
  revisão), então o status, o responsável e a data fim das OS antigas só mudam na busca inteira.
- **O ↻** busca a lista inteira na hora, uma busca por vez (quem aperta junto espera a mesma); até 1 min depois da
  última inteira, só as novas. A atualização automática de 10 min usa a lista guardada. Etiquetas e pessoas não são
  relidas no ↻ (10 min na memória).
- **As tarefas das OS fechadas não são relidas** (`api.list_minhas_os(meta_ja=...)`): Concluída ou Cancelada com o
  mesmo status de antes guarda o tipo, as datas e o gatilho.
- **As linhas são montadas uma vez por versão da lista** (`_historico_linhas.html`, guardado na lista): medido com
  2.000 OS, cada pedido gastava ~0,25 s de processador no PC; agora a 1ª monta (0,38 s) e as seguintes levam
  0,05–0,07 s, de qualquer pessoa.
- A tela mostra "Lista das HH:MM" (quando a lista guardada veio). Erro do Fracttal por trás mantém a lista guardada.
- Prova: `tests/test_oscreator_historico_compartilhado_19_10.py` (conta cada ida ao Fracttal: uma busca para várias
  pessoas, a visão restrita com a dela, a vencida que soma só as novas, a inteira a cada 10 min sem reler as tarefas
  das fechadas, o ↻, três pessoas ao mesmo tempo, o Fracttal fora, as linhas montadas uma vez).

## O catálogo de ativos vencido por trás (24/10/2026)

Em 23/10/2026 às 10:44 o catálogo de ~22 mil ativos passou das 24 h (`api.ASSETS_TTL`) e o 1º a precisar dele o baixou
DENTRO do pedido (~110 pedidos ao Fracttal, 6 de cada vez): um "Criar OS" da Performance ficou 3 min 51 s em
`get_assets`, e o Histórico 1 min 52 s esperando o mesmo download. Levi, 24/10: "deixe um botão de atualizar ativos e
quando atualizar vai atualizar a lista de todos, não só daquela pessoa".

- **Vencido, o de ontem volta na hora** (`api.load_assets_cached`) e o novo é baixado por trás
  (`_renovar_catalogo_por_tras`, a thread `os-catalogo-por-tras`), com a sessão de quem pediu (a cópia do contexto leva o
  JWT). Uma tentativa a cada `ASSETS_ESPERA_TENTATIVA` (10 min): a que falhou deixa o de ontem.
- **Espera o novo** só quem precisa dele em dia: `em_dia=True` (resolver o ativo da OS na aprovação,
  `rotas_solic._catalogo_para_aprovar`); e quem não tem catálogo nenhum na máquina.
- **O botão "Atualizar ativos"** (OS Creator → Ativos, `/os/api/ativos/atualizar`) baixa na hora; o arquivo do catálogo
  é um só (`assets_cache.json`), então vale para todos. Ativo cadastrado hoje que não aparece: é ele.
- Prova: `tests/test_oscreator_catalogo_por_tras_24_10.py` (7; 6 falham no código de antes, o outro segura o "sem
  catálogo, espera"); 5 mutações, todas pegas.

## Os catálogos e o catálogo de ativos uma vez para todos (19/10/2026)

O mesmo superplano (o mapa de cada pedido ao Fracttal, por tela, que a sessão fez em 19/10/2026):

- **Pessoal ativo, etiquetas, motivos de cancelamento, tipos de solicitação e as OS recentes da tinta dos Ativos**
  (`rotas.responsaveis_fracttal`, `etiquetas_fracttal`, `motivos_cancelamento`, `os_recentes`; os tipos da
  solicitação no `("solic_cat", "tipos_solicitacao")`): iguais para todos, eram relidos a cada tela e a cada clique, por cada pessoa (o pessoal são
  2 pedidos; as OS recentes, 17 a 40 pedidos em sequência a cada visita aos Ativos). Agora 10 min na memória, um para
  todos; o erro não fica guardado, e o catálogo vazio também não (`_memo(..., guardar=)`, 20/10/2026: a lista vazia da
  sessão de alguém sem a permissão esvaziaria a tela de todo mundo pelo TTL). Na CRIAÇÃO (uma gravação) o pessoal e as etiquetas seguem lidos na hora
  (`rotas_solic_eng.criar`).
- **O catálogo de ~22 mil ativos** (`api.load_assets_cached`): lido do disco uma vez por versão do arquivo (antes cada
  uma das 26 chamadas decodificava o JSON inteiro, a prévia do COS a cada 120 ms de digitação), entregue em cópia por
  registro; e a recarga do Fracttal (~110 pedidos) é uma por vez: quem acha o catálogo vencido junto espera a mesma. O
  resumo "N ativos, catálogo de quando" (`api.assets_cache_info`, da tela inicial e da de Ativos) usa o mesmo
  decodificado (`_catalogo_cru`, 20/10/2026: decodificava o arquivo inteiro, 10,5 MB, a cada chamada).
- **`_code_to_loc` sem catálogo não tenta de novo por 10 min**: é chamado por linha do Histórico, e com a recarga
  falhando eram 2.000 tentativas numa lista.
- **A OS pelo número num pedido só** (`api.os_por_folio`): sem o status, a lista traz os quatro; eram até 4 pedidos em
  sequência (o "Buscar OS", o card pelo nº, a cadeia do chamado, o PDF). Sem achar, a varredura de antes, status por
  status.
- **A chave que colidia (20/10/2026).** O programador do PCM: "não consigo solicitar pelo nexus porque a classificação 1
  não abre opção de preencher". Os tipos da Nova solicitação (`get_request_types`: grupo, classif1, classif2) ficaram
  na chave `("solic_cat", "tipos")`, a mesma do Tipo de tarefa e das Classificações da OS da Fila do PCM
  (`get_tipos_classif`: tipos, c1, c2). Quem abria a Fila primeiro deixava a Solicitação sem Grupo e sem Classificação
  por 30 min, e o contrário esvaziava a Fila. Cada um na sua chave agora.
- Prova: `tests/test_oscreator_catalogos_19_10.py`.

## O quadro do Acompanhamento dividido e os anexos do card (19/10/2026)

O que tinha ficado de fora do superplano. Levi, 19/10/2026: "1 - quebre essa regra 2 - resolva!".

- **O quadro do Acompanhamento de chamados é um só para quem vê o mesmo no Fracttal** (`rotas_acomp._dono`). Caiu a
  regra de 08/10 ("uma pessoa nunca vê a cópia de outra"): cada pessoa com o quadro aberto relia a lista e os tickets a
  cada 3 min, para o mesmo quadro. A cópia é de "TODOS" para quem o Fracttal dá o mesmo total de OS com a etiqueta
  CHAMADOS (±1%, ou 2 OS). A conferência é na sessão da pessoa (`api.total_chamados`: a etiqueta e 1 página de 1
  linha) e vale 30 min; quem acabou de ler a lista já tem o total dela anotado (`historico_store.anotar_total`, a
  mesma conta). Quem vê outro total (visão restrita) ou não conseguiu conferir segue com a cópia dela, como antes.
  - O que vale 30 min é o TOTAL da pessoa, e não o veredito (`historico_store.mesma_visao`, que serve também ao
    Histórico): a comparação é com a cópia de AGORA. A cópia sai da memória a cada ticket gravado, e a próxima pode ser
    de quem vê outra coisa; com o veredito guardado, a visão restrita veria por até 30 min o quadro de quem vê tudo.
  - Cópia sem uso há mais de 2 h (`VELHA_MAX`: quem a usa relê a cada 3 min) vira a de quem chega. Sem a etiqueta no
    Fracttal (é da empresa) o total é 0 para todos, e o quadro vazio é um só.
  - O ticket das concluídas é um para todos (`("acomp_tk", "TODOS")`): é da OS, e cada um só pede o das OS da lista
    que vê. A releitura por trás é uma por cópia, com a sessão de quem abriu. O detalhe que o mouse parado prepara
    segue sendo da pessoa (lido com a sessão dela).
  - Prova: `tests/test_oscreator_acomp_dividido_19_10.py` (9 cenários, com um Fracttal falso por pessoa) e os testes de
    antes ajustados (`acomp_renovar`, `card_preparo`, `desempenho`: os dublês da lista dão o total, como a função real).
- **Os anexos do card pelo id certo da tarefa** (`api._ids_tarefas_da_os`). Na lista de tarefas da OS o id da tarefa
  DESTA OS é o `id`; o `id_task` é o MODELO da tarefa. O código caía no `id_task` (a lista não traz
  `id_work_order_task`): a tarefa sem foto ficava sem os arquivos lidos (as com foto vinham pelo endpoint das imagens),
  e o número do modelo é o de uma tarefa antiga de outra OS, cujos arquivos podiam aparecer na OS errada. Conferido
  numa OS real de ronda em 19/10/2026 (REST, só leitura): os 31 anexos estão no id da tarefa da OS
  (`id_work_orders_tasks`), e o `id_task` dela é outro número. A mesma diferença já tinha derrubado o 1º teste ao vivo
  do cronômetro (`api.id_tarefa_da_os`).
- **A contagem de anexos não relê o que o card acabou de ler** (`api._leitura_da_os`): as tarefas e as subtarefas da OS
  ficam 20 s na memória, por OS. O card sempre lê na hora (e guarda); a contagem, ~1 s depois, usa a guardada: 2
  pedidos a menos por card aberto. Toda gravação pelo `_rpc_call` (o que não é leitura: `_eh_leitura`) tira as leituras
  da OS dela, ou todas quando não diz a OS; o anexo enviado também (`attach_imagem_os`).
  - Prova: `tests/test_oscreator_anexos_19_10.py`.
- As 10 partes das duas frentes foram desfeitas uma a uma, e cada uma derrubou o teste dela.
- **A suíte do próprio oem, rodada com a cópia nova, achou duas falhas do superplano de 19/10** (a suíte do Nexus não
  as via), corrigidas aqui:
  - o círculo de carga do Histórico (`api.list_minhas_os`) recalculava o total depois das páginas (com as fechadas já
    sabidas há menos lotes de tarefas); o total volta a ser o dito depois da 1ª página, e os lotes que não vão ao
    Fracttal contam como feitos logo depois das páginas: o círculo anda e fecha em 100%
    (`test_o_circulo_de_carga_nao_muda_o_total_no_meio`, o mesmo contrato do teste do oem);
  - os catálogos "um para todos" (`("cat", ...)`, `("solic_cat", ...)`) passavam de um teste para outro (o pessoal de
    mentira de um aparecia no seguinte): o app de teste (`criar_app(testing=True)`) começa sem eles, como já começava
    sem as listas do Histórico. No servidor o app é um só por processo.
  - Ficam 3 falhas na suíte do oem que não são destas mudanças: `test_os_web_home::test_selo_do_card_performance` e
    duas de `test_os_web_sessao`, que ainda cobram o selo da Performance na página e a volta ao login pela 1ª chamada
    ao Fracttal da tela inicial; desde 14/10 (`bb91eb0`) a tela inicial abre sem esperar o Fracttal.

## A lista de fabricantes do chamado é a do Nexus (Chamados > Fabricantes, 20/10/2026)

Levi, 20/10/2026: "1 - corrija canadian 2 - insira NCU e RSU 3 - Essa lista tem que ser a mesma do nexus > fabricantes:
ele escolhe o fabricante o app já filtra se é inversor, cabine etc 4 - Se a lista de fabricantes do chamados >
fabricantes tiver nome diferentes do fractall altere o nome em fabricante!" e "quando a singrid adicione novos
fabricantes em chamados > fabricantes apareça atualizado no app".

- **A regra mora no pacote** `chamado_garantia` (o mesmo no OS Creator, no oem e no App): `registro.py` põe a aba
  `os_creator · chamado_modelos` (a que a tela Fabricantes grava) por cima do código. O `chamado_modelos_store` do OS
  Creator passou a chamar o pacote (o canal de abertura continua só aqui); os nomes públicos dele não mudaram.
- **A marca no nome do ativo** (`spec.marca_do_ativo`, a única: a de `regras` chama esta) vale como palavra inteira e
  pelos apelidos do Fracttal (`APELIDOS_NO_FRACTTAL`). No catálogo de 14/10: +80 Canadian ("CANANDIAN SOLAR"), +169
  Huawei (só o modelo SUN2000), os 131 Axial grudados ("AXIALtracker") seguem Axial, e saem os falsos STI (16
  cabines, skids e estações pelo endereço "Justiniano"/"Sebastião"; os 43 trackers de Santo Inácio pelo código STI100).
- **Os nomes da tela contra o Fracttal** (o item 4): dos 11 fornecedores, só a Canadian difere, e o erro é do Fracttal
  ("CANANDIAN"): o nome fica certo na tela e a grafia do Fracttal entra como apelido. Hukseflux e Romiotto não
  aparecem no nome de nenhum ativo (o nome da estação é o endereço). O campo de fornecedor novo pede o nome como está no
  Fracttal.
- **O App de Campo** lê a aba e aplica pelo pacote desde a v290 (20/10/2026 15:06Z, servidor `26d79be6f7506438`; o
  pedido e o código testado em `app-campo-docs/_propostas/fabricantes-do-nexus`): a lista do técnico é a da tela,
  filtrada pelo tipo do ativo, relida de 5 em 5 minutos (`/health` → `chamadoGarantia.fabricantes`). A NCU e a RSU
  pegam a marca dos trackers da usina depois do catálogo da ronda rodar (segunda 04:30 UTC). O aviso do topo da tela
  saiu; a linha de baixo do título diz que o App usa a mesma lista.
- Prova: `tests/test_chamado_garantia_fabricantes.py` (aqui) e os testes do oem (`test_chamado_modelos_store.py`,
  `test_modelos_na_abertura.py`, `test_os_web_fornecedores.py`), rodados com a cópia sincronizada.

## A OS de acompanhamento retroativa (Garantias, 20/10/2026)

A analista de chamados passou a criar à mão no Fracttal a OS de acompanhamento (a OS 3) dos chamados que só existiam na
planilha de gestão de chamados, e a 1ª (16858) saiu errada na tela: cadeia e ativo vazios, "chegou hoje ... nasceu
sozinha no fechamento da inspeção" e nada do histórico. A OS estava certa no Fracttal (marca, etiqueta CHAMADOS, OS mãe,
ativo); a tela só entendia a nota escrita pelo App. Levi, no mesmo dia: a nota dela vale como ela escreve, e sem a cadeia
na nota entra a OS mãe do Fracttal; no banco, o chamado abre na data da nota.

- **A nota dela** (`acomp_web.ler_nota`): a linha da cadeia é lida em qualquer ordem. "OS de abertura: 11199 · OS de
  campo: 12565" quer dizer OS de campo 11199 (a corretiva onde a falha apareceu, a OS mãe que ela vinculou) e inspeção
  12565 (do tipo Inspeção); sem "OS de abertura", "OS de campo" e "Inspeção" são os do App. "Data da ocorrência / abertura
  do chamado" (ou "Abertura do chamado") é a `abertura`, que também vale como a data da falha. As outras linhas "rótulo:
  valor" (Status atual, Ticket, S/N, Título do e-mail, Solicitação, UFV…) vão para `info`, o bloco "Na nota da OS"; o
  "Histórico (...):" vira `historico`, uma entrada por "dd/mm - texto", com o ano da abertura (o seguinte quando a data
  cai antes dela).
- **A idade** (`cartao`, `abertura_valida`): com a abertura válida (data de verdade, não depois da criação da OS), o
  chamado conta dela (`retroativa`, `chegou` = o dia da abertura, `criada` = quando a OS entrou no Fracttal); a última
  data do histórico conta como atualização. No topo da tela, "Aberto em" no lugar de "Chegou".
- **A linha do tempo**: "Criada à mão no Fracttal em … : o chamado é de …" no lugar do "nasceu sozinha", e o histórico
  da nota depois dela, do mais novo ao mais antigo ("Histórico importado na nota").
- **Sem a cadeia na nota** (`rotas_acomp._os_mae`, `acomp_web.cadeia_pela_mae`): o id da OS mãe já vem no detalhe
  enxuto (`os_pai_id`); só nesse caso a tela lê a mãe (1 detalhe a mais) e a põe pelo tipo: Inspeção é a inspeção; outra
  é a OS de campo. Fracttal que recusa deixa "—". O Ativo sem a nota é o código da própria OS (`det["code"]`).
- **No banco** (`nexus/dados/fato_chamado.py`): `data_id_abertura` e `duracao_min` contam da abertura da nota, e a coluna
  nova `abertura_por` diz `nota` ou `os`.
- Prova: `tests/test_oscreator_chamado_retroativo.py` (a nota dela com nomes e números de mentira, a nota do App lida
  igual, a idade, a linha do tempo, a OS mãe, a tela e o fato). Conferido numa bancada local com o Fracttal falso, a 1440
  e a 375 px.

## O quadro só relê no Atualizar ou a cada 30 min, com 6 cartões à vista (Garantias, 20/10/2026)

Levi, 20/10/2026: "aumente o tamanho em acompanhamento de chamados para mostrar 6 usinas nas colunas kanban" e "quando
tento voltar para acompanhamento dá uma travada, faz outra pesquisa no fractal? ... só pesquisar caso a singrid clique em
atualizar, fora isso fica mostrando o que já carregou ou carrega a cada 30 min".

- **O quadro guardado vale 30 min** (`TTL_QUADRO`, era 3): a volta da tela de um chamado ao quadro sai da memória. Depois
  dos 30 min, abre na hora com a leitura anterior e relê por trás, como antes; o Atualizar relê na hora. Até `VELHA_MAX`
  (2 h), sem mudança.
- **A gravação ajusta o quadro em vez de apagá-lo** (`rotas_acomp._ajustar`): o ticket (a OS passa a "Ticket aberto"), o
  finalizar (pelo status que o Fracttal deu depois de concluir, `_status_depois_de_concluir`, 1 pedido na própria
  gravação; sem ele, o quadro sai da memória como antes) e o responsável (`esquecer_se_no_quadro`, com o nome que a
  rota do responsável mandou). Até então cada uma apagava o quadro, e a volta esperava a lista e os tickets do
  Fracttal. A releitura que começou antes da gravação e termina depois leva a gravação por cima (`_AJUSTES`,
  `_reaplicar`); a idade da cópia não muda com o ajuste.
- **O teto da memória tira o quadro por último** (`rotas.MEMO_FICA`): com 30 min ele seria o guardado há mais tempo, e
  os anexos dos cards do Histórico (uma entrada por card aberto) o tirariam primeiro.
- **6 cartões à vista** (`acomp.js`, `CARTOES_A_VISTA`): a coluna vai até o fim do 6º cartão visível, medido na tela
  (o cartão cresce com o título e as etiquetas), e é refeita no filtro, na troca de largura e quando a fonte chega; o
  CSS usa a medida (`--cards-max`, 72vh antes do JavaScript). Até 6 cartões, sem teto; no celular, sem teto, como antes.
- Prova: `tests/test_oscreator_acomp_30min_20_10.py` (30 min, depois dos 30, o Atualizar, ticket, finalizar com e sem o
  status, responsável, a releitura no meio da gravação, o teto da memória); a releitura e o teto conferidos por mutação.
  Na bancada local (Fracttal falso, 1545 px): 6 cartões inteiros em cada coluna (966 px), a ida e volta a um chamado
  sem nenhuma leitura da lista, o ticket gravado e o cartão já em "Ticket aberto" na volta; a 375 px, sem teto e sem
  rolagem lateral.

## A lista pela metade não vai para a tela (21/10/2026, chat de desempenho)

Raio-X do servidor às 14:36 de 21/10: "Pedido preso 24 vezes em 24 h", o último um `GET /os/historico` de 45 s
esperando o Fracttal (`api._rpc_chamar`); 45 s é o tempo-limite do pedido. A busca da lista (`api.list_minhas_os`, que
serve o Histórico e o quadro do Acompanhamento de chamados) engolia o erro de cada página e de cada lote das tarefas:
- sem a 1ª página, a lista saía VAZIA, sem aviso, e ficava guardada como se não houvesse OS no período (no
  Acompanhamento, por 30 min);
- sem uma página do meio, sumiam até 200 OS sem aviso; sem um lote das tarefas, 130 OS ficavam sem o tipo e as datas
  (as fechadas, para sempre: o `meta_ja` não as relê), e a Visão COS, que filtra pelo tipo, as escondia;
- a lista vazia de "Todos" fazia cada pessoa buscar a dela inteira dali em diante (o total dela não batia com o 0
  guardado, `historico_store.mesma_visao`), até o Nexus reiniciar: mais carga no Fracttal, mais chance de outro estouro.

Agora a busca em que o Fracttal não entregou algum pedido (tempo esgotado, 429, erro) falha INTEIRA
(`api._lista_pela_metade`; o lote das tarefas avisa pelo `falhas` do `_MetaLida`, atributo e não argumento, porque os
testes do oem trocam o `_meta_tarefa_por_os` por `lambda ids: {...}`). Nada é guardado, a sessão caída numa página do
meio leva ao login, e a tela diz "O Fracttal não respondeu a tempo em N de M pedidos da lista. Para não mostrar OS pela
metade, a lista não foi atualizada; tente de novo em instantes." O ↻ do Histórico e o Atualizar do quadro ficam com a
lista que já estava, com a hora dela (o quadro, até `VELHA_MAX`). Sem a 1ª página, nem pede as outras; sem uma do meio,
não lê as tarefas.
- Medido com o Fracttal de mentira (650 OS; a 1ª pessoa sem resposta, depois mais 3 abrindo a Visão COS): antes, a lista
  vazia sem aviso e 30 pedidos para as 3 (uma cópia inteira para cada, e a vazia de "Todos" guardada); depois, o aviso
  e 11 pedidos (uma lista para todos).
- Prova: `tests/test_oscreator_lista_pela_metade_21_10.py` (a busca, o Histórico e o quadro); as 7 mutações (página
  engolida, sem conferir as páginas, sem conferir o meta, lote engolido, sessão caída como erro comum, Histórico e
  quadro sem a lista anterior) derrubam cada uma o seu teste. Na bancada (o clone sozinho, Fracttal falso, sem rede),
  a 1280 e a 375 px: o aviso, a lista anterior com a hora dela no Histórico e no quadro.

## O filtro do quadro fica na volta, e o checklist sem permissão diz o que fazer (Garantias, 24/10/2026)

- **O filtro e a rolagem do Acompanhamento de chamados ficam** (Levi: "Quando eu faço um filtro em garantias >
  acompanhamento de chamados e clico na os, ao voltar para o acompanhamento o filtro se desfaz e carrega novamente,
  quero que mantenha o filtro anterior!"). O `acomp.js` guarda o filtro a cada mudança e a rolagem da página e de cada
  coluna ao sair (`pagehide`), no `sessionStorage` desta aba do navegador (`acomp.filtros`, `acomp.rolagem`), e põe de
  volta quando o quadro abre: na volta de um chamado, no Atualizar e quando a tela troca sozinha (`esperarANova`). O que
  saiu da lista (uma marca sem chamado no quadro) não vira filtro; o Limpar filtros limpa o guardado. Prova:
  `tests/test_oscreator_acomp_filtro_guardado_24_10.py` (o script no node); na bancada, Fornecedor = Sungrow, um chamado
  aberto e a volta com o mesmo filtro e os mesmos 6 de 16 cartões.
- **"O Fracttal recusou o checklist: WITHOUT PERMITS"** ao salvar o ticket (uma analista de chamados; outra, na mesma
  tela, salvava): o ticket é a subtarefa da OS, e a gravação (`api.salvar_subtarefas`) vai com a conta de QUEM ESTÁ
  LOGADO no Fracttal. O perfil dessa conta não pode responder subtarefas: não é o OS Creator nem o Nexus que libera, é o
  administrador do Fracttal (o perfil do usuário). A tela passa a dizer isso (`_CHECKLIST_SEM_PERMISSAO`, com o código
  entre parênteses), como o `WITHOUT_PERMITS` de criar OS (`_RPC_MSG`). Prova: `tests/test_chamados_ordem_icone_permissao_24_10.py`.
- No Nexus, a torre Chamados ficou na ordem Garantias, Fabricantes e Solicitações de clientes (`nexus/torres/chamados`).

## O pulso laranja nas OS de Garantias paradas (25/10/2026)

Levi, pelo chat da Engenharia: "sabe o pulsar que temos no quadro de equipe? passe instruções para o chat de Nexus
(Chamados) implementar nas OSs de garantias porém quando a OS ficar a partir de 5 dias sem comentário de atualização!".

- **A regra** (`acomp_web.parada`, `DIAS_PARADA = 5`): pulsa o cartão da OS ABERTA do quadro (Chegaram e Ticket aberto;
  em verificação, finalizada e cancelada não) com 5 x 24 h ou mais desde o último comentário de atualização: a última
  observação da tela (as do banco da Gridco, inclusive a anotação do ticket gravado) ou, na retroativa, a última data do
  histórico da nota. Sem comentário nenhum, conta da abertura: a OS esquecida desde o início também pulsa. Sem as
  observações lidas (o banco fora), nada pulsa e o aviso do quadro diz que o pulso fica desligado.
- **O desenho é o do Quadro da equipe da Engenharia** (`nexus/static/engenharia.css`, `.kb-card--parada`, que usa 7 dias):
  a camada `::after` de 0,5 a 1 de opacidade, com o contorno de 1,5 px e o halo, que pulsa mesmo com "reduzir movimento".
  Aqui é `.card.parada` e `@keyframes ac-pulso`, com os tokens `--pulso-a71` a `--pulso-a14` no `chamados.css`, nos dois
  temas (os mesmos valores do `nexus.css`, que não chega ao OS Creator). Mudou a sombra lá, traga para cá: o teste
  compara as duas.
- O cartão ganha no `title` "5 dias ou mais sem comentário".
- Prova: `tests/test_oscreator_acomp_pulso_25_10.py` (4 d 23 h não, 5 d sim, as duas colunas abertas, as fechadas não,
  sem comentário desde a abertura, o histórico da retroativa, o banco fora, a tela e o CSS). Na bancada (Fracttal
  falso, metade das OS comentada na véspera): só as paradas pulsam, a 1440 e a 375 px, no escuro e no claro.

## Investigar ativo: o histórico de OS de um ativo, para o Tempo real (26/10/2026)

Levi: "Gostaria de poder clicar com botão direito do mouse em cima do inversor e ter a opção 'Investigar ativo'. Vai
aproveitar o pré carregamento de histórico de OS do OS Creator filtrando esse ativo, deve mostrar o período filtrado e eu
devo conseguir fazer novos filtros e pesquisas pela visão. Vai abrir uma sub janela sobrepondo a tela dando um blur de
fundo que nem quando vamos criar OS." O menu e a janela são da plataforma (Monitoramento, `plataforma/CLAUDE.md`, seção
"Investigar ativo"); a visão mora aqui, onde a lista do Histórico já está carregada.

- **O endereço:** `/os/historico/ativo?codigo=<código do Fracttal>&usina=<usina>&nome=<inversor>[&rotulo=&de=&ate=]`
  (`os_web/rotas_investigar.py`; as regras, puras, em `os_web/investigar_web.py`; a tela em `templates/historico_ativo.html`
  e `static/investigar.css`). A plataforma abre com `janela=1` (a ponte tira o topo, como no Criar OS), e o formulário
  guarda o `janela` e o pedido a cada nova busca. Fica debaixo do `/os/`: o portão do Nexus pede uma tela da torre OS
  (`setor_telas.pode`), e o Caddy já manda o `/os/*` ao Nexus. Sem a sessão do Fracttal, o login do OS Creator, como
  em qualquer tela (`exige_sessao`).
- **De onde vem o histórico (nenhuma busca a mais no Fracttal):** a lista de "Todos" dos últimos 30 dias, a MESMA da
  Visão COS e do "Criado por: Todos" (`rotas.ler_lista`, que saiu de dentro do `historico` para as duas usarem a mesma
  leitura: a chave `("hist", "TODOS", "criadas", "TODOS", None, de, ate, ())` do `historico_store`, a conferência da
  mesma visão e a renovação por trás). Quem abriu a Visão COS deixa a janela pronta; a 1ª janela deixa a Visão COS
  pronta. O período DENTRO dos 30 dias é recortado da lista (pela data de criação, como o Histórico), sem pedido; fora
  deles, a lista daquele período (a régua do Histórico, guardada para quem vier depois), com o aviso na tela e o do teto
  de 2.000 quando a lista corta as mais antigas. O ↻ é o do Histórico.
- **O ativo, pelo catálogo do disco** (`api._catalogo_cru`, vencido também serve; nunca o Fracttal): o código que a
  plataforma manda (o gravado no de-para ou o derivado do nome) quando está no catálogo; senão, o inversor da usina com o
  mesmo número (`INVR` + N.M, sem zero à esquerda; 1.1 não casa com 1.10), com o aviso de que o código não existe (o
  derivado erra onde a árvore do Fracttal mudou, a Pharma II); sem inversor, a usina inteira, com o aviso.
- **A OS é do ativo** quando o código dele está entre os itens dela: a linha do Histórico ganhou `codigos`
  (`api._extrai_codigos`, todos os `{ ... }` dos itens; o `_extrai_code` fica só com o último), e a OS agrupada de dois
  inversores aparece nos dois. "Da usina", pelo nome curto, o do Histórico (inclui as do item da usina: religamento).
- **Os filtros da janela:** "Este ativo N | A usina inteira N", Status e Tipo de tarefa (as opções que existem nas OS da
  usina no período) e a busca por texto são locais, sobre as linhas da usina que vieram; o período re-lê no servidor. O
  nº abre o card da OS do Histórico (o mesmo `os_acoes.js`); a ação que muda a OS relê ao fechar. O Esc sem card aberto
  fecha a janela do Tempo real (`{gc: "depara-fechar"}` à página de baixo).
- **Prova:** `tests/test_oscreator_investigar_ativo_26_10.py` (14: o catálogo, o número, os códigos dos itens, o
  período, a janela sem busca a mais depois da Visão COS e o contrário, o recorte, o período fora, os campos guardados,
  a usina inteira, o login e o Histórico igual depois da `ler_lista`). Na bancada (o clone sozinho em `127.0.0.1:5097`,
  Fracttal falso, rede bloqueada, dentro de uma moldura com o fundo desfocado): o escopo, o status, a busca, o vazio e o
  período (recorte sem pedido) funcionando; a caixa da busca crescia 460 px de altura (flex-basis do Histórico numa
  coluna), corrigida no `investigar.css`.
- **Falta:** levar ao oem (`api.py`, `rotas.py` e os quatro arquivos novos), com o OK do Levi (o oem é público); até lá,
  a plataforma do PC aberta direto (o `/os/*` dela vai ao 5090) dá 404 na janela. E o olho do Levi com uma OS de verdade.
