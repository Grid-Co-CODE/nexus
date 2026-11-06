# OS Creator Web — dentro da torre OS Creator

O OS Creator Web nasceu no supervisório de O&M: o serviço `os_creator/os_web` do repositório `oem`, na porta 5090,
publicado em `/os/*` pela plataforma. Foi trazido para cá em 30/09/2026, a pedido do Levi: "clone o OS Creator Web que
está no meu supervisório de OEM para a pasta do OS Creator do Nexus".

**Desde 31/10/2026 o Nexus é a casa dele** (etapa 1 do canto central,
`docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`). De 06/10 a 30/10/2026 o clone era mantido
idêntico ao do oem por uma ferramenta de sincronia; ela saiu (`ferramentas/sincronizar_oscreator.py`, o `sincronia.py` e
o `sincronia.json`), e o oem (`C:\GridcoBuild\oem`) ficou **congelado** como estava: segue servindo o 5090 com a cópia
dele, sem novidades, e ninguém escreve nele. Onde esta página fala em "levar ao oem", "sincronia", "`--aplicar`", "suíte
do oem" ou em manter o clone "idêntico", é o registro daquele tempo.

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
  - `steps/engenharia` e `steps/ui.py`: o descritor da Engenharia (título, descrição e ícone), que a web usa; o `steps/ui.py`
    (PyQt6) veio sem a web nunca importá-lo, e saiu em 31/10/2026 (seção "Antes de mexer").
- O pacote `chamado_garantia`, com o `assets/` (ícone, logo e fontes) e o `requirements.txt`.

## O que ficou de fora de propósito

| Arquivo | Por quê |
|---|---|
| `fracttal_login.txt` | é o login salvo do desktop |
| `assets_cache.json`, `ativos.json.gz` | são o catálogo de ativos (o arquivo antigo e a cópia em disco do catálogo central), dado que já vazou uma vez por instalador público |
| `tokens.txt`, `gridco_sql_token.txt` | são segredo; o código lê da variável `GRIDCO_SQL_TOKEN` ou de `%APPDATA%` |
| `app.py`, `main.py`, as outras telas de `steps/` | são o app de desktop (PyQt), e a web não usa |
| `steps/ui.py`, `steps/engenharia/tela.py`, `assets/chamados.qss`, `assets/fonts/LEIA-ME.txt` | vieram junto e eram só do app de mesa (PyQt6); saíram em 31/10/2026 |
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
  `/os/...`; o resto cai no destino da tela) e a casca do OS Creator o põe numa aba: era por onde o card da OS aberto
  em outra torre levava ao "Clonar esta OS" e ao "Abrir chamado", que saíram do card em 29/10/2026.
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
  janela é o próprio `window.top`, então nada muda no supervisório.
- **Topo do OS Creator no Nexus** (Levi, 04/10): sem o "← Plataforma" (o menu lateral já leva a qualquer lugar) e sem
  o símbolo e o "Grid Co." (o topo do Nexus já tem); fica só o "Sistema de Ordens de Serviço", centralizado. As
  páginas do Nexus também saem de qualquer moldura. A troca é feita na resposta, pela ponte, e o arquivo do clone não
  muda.
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
- **Quando sobe:** o clone só sobe na primeira visita ao `/os/`. Se ele quebrar (faltou o `requests`, por exemplo), o
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

- **Um ativo, uma OS; mais de um, uma OS só** (sem escolha desde 06/11/2026, Levi: "UM ATIVO UMA OS, SE FOR MAIS QUE UM
  ATIVO JÁ VIRA UMA OS com mais ativos!"; até ali a tela tinha "Uma OS por ativo" × "Uma OS com todos os ativos", com o
  padrão em uma por ativo). O servidor decide (`montar`: `agrupar = len(ativos) > 1`) e ignora um `agrupar` no pedido.
  - Mais de um ativo sai pelo `api.create_work_orders_agrupada`, o mesmo do "Agrupar em UMA OS" do Tradicional: cada
    ativo vira uma atividade (tarefa) com o seu `[Ativo] - Descrição`, todas numa OS só. As regras da seção acima valem
    iguais: Administrativa, só a Classificação 1, só a etiqueta do setor, as duas datas e o responsável.
  - Um ativo só vai pelo caminho de sempre, o `api.create_work_orders_bulk`.
  - A OS que não fecha (o Fracttal recusa o `work_order_insert`) deixa as atividades pendentes lá. A tela diz isso e
    manda gerar a OS no Fracttal; a resposta é 200, para os ativos saírem da seleção (um 2º clique criaria tudo de novo).
- **Anexos:** PDF; imagem (JPG, JPEG, PNG, WEBP, GIF, BMP); planilha (XLSX, XLS, CSV, ODS); documento (DOCX, DOC, ODT,
  TXT). Até 5 arquivos, 10 MB cada e 20 MB no total. A tela mostra os tipos e os limites, com os números do servidor
  (`solic_eng_web.py`), que confere tudo de novo. Tipo novo é uma linha no `TIPOS_ANEXO`.
  - Sobem pelo **mesmo caminho do anexo de hoje**, o `api.attach_imagem_os` (s3_object_post, S3,
    `work_orders_tasks_files_insert`; o das imagens da Performance e do Tradicional), **depois** de a OS existir, na 1ª
    tarefa da OS: uma vez, na OS (o card junta as tarefas).
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

## A OS de Performance criada vira comentário na usina (03/11/2026)

Levi: "quando eu crio uma OS de performance já vira um comentário automático: '<Levi> criou uma OS de <String> para o
<inversor X>' + 'Observação da OS'". A resposta do `/os/api/performance/criar` leva `comentario` =
`perf_web.criadas_para_comentario` (`{tipo, criadas: [{folio, ativo, observacao}]}`, só as que saíram COM nº; a agrupada
é uma OS, com os ativos juntos e a observação da OS), e o `perf.js` (`comentarNaPlataforma`) manda isso à Plataforma de
Performance (`POST /api/state/comment/os`, por URL completa, mesma origem no servidor) com a chave da conversa que o Tempo
real pôs no link (`?comentario=pv:22854`). O texto, o autor (a sessão da plataforma) e o "um por nº" são de lá
(`plataforma/CLAUDE.md`, seção "Comentários das usinas"). Sem nº, nada vai; sem a plataforma, a OS segue criada e só não
comenta. Prova: `tests/test_oscreator_perf_comentario.py`.

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
  (aprovar e criar), a Solicitação (técnico sugerido) e o trocar responsável. A Tradicional segue com a lista dela (no
  Passo 2 desde 26/10/2026), que já se via inteira: passou a casar do mesmo jeito (`OsBusca.casa`) e a aceitar setas e Enter. O Enter só
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
- **Histórico:** desde 03/11/2026 **toda** lista do painel de filtros ganha a caixa no topo (Levi: "todas as opções do filtro
  digitáveis"): o macro `multi` marca todas com `data-busca="1"`, mesmo a de 2 ou 3 opções (até então só a de Usina, e as de 6 ou
  mais). Criado por e Etiqueta (um valor só) usam a mesma lista, com um botão de escolha por linha (seção "Os filtros do Histórico só
  valem no Aplicar").
  - Esconde o que não casa pela classe `osm-fora`, **nunca** por `[hidden]`. O hidden é a cascata cliente → usina, e o
    resumo e o filtro do Histórico ignoram o que está hidden. Assim, a usina marcada continua valendo mesmo fora da
    busca.
  - Enter marca ou desmarca a linha em destaque (ou escolhe, na lista de um valor só); Esc limpa a busca, o segundo Esc fecha
    (dentro de um `[data-esc-fecha]`, como o painel do Histórico, um Esc só já fecha); fechar a lista limpa a busca.
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
- **A nota em dois campos (05/11/2026):** `api.get_os_detalhes` devolve `notas`, a `note` e a `task_note` de cada tarefa
  sem repetir a que já está DENTRO de outra (`os_detalhe.juntar_notas`), e, crus, `nota_gravada` (a `note` da 1ª tarefa,
  o que o `editar_nota_os` grava) e `nota_da_tarefa` (a `task_note`, a nota com que a OS nasceu). Quem regrava a nota parte
  do cru, nunca da junção (a ponte da Engenharia, `ponte._base_da_nota`): regravar a junção repetia a nota de entrada a
  cada comentário (prova no Fracttal da OS 18591 de TESTE - PA). A prova: `tests/test_engenharia_nota_da_os.py`.
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
- **Links do card** para outras telas do OS Creator passam por `/os/_nexus/ir`, que abre a torre OS Creator do Nexus
  com a tela numa aba (`tela_do_endereco`). Com Ctrl, numa aba nova. O "Clonar esta OS" e o "Abrir chamado" saíram do
  rodapé em 29/10/2026 (seção "O card sem Abrir chamado e Clonar, com o PDF").
- **A tela do chamado de Garantias por cima** (28/10/2026, Levi, no Painel do responsável: "Ao clicar no chamado deve
  aparecer a tela que aparece quando clicamos na OS de chamados na parte de garantias. Não deve direcionar, apenas
  sobrepor a tela como uma meio que janela dando um blur de fundo"): `/os/_nexus/chamado/<nº>?de=<a tela>`
  (`ponte.chamado_os`, template `oscreator/chamado_os.html`) é a moldura do MEIO, que a tela do Nexus põe num `<dialog>`
  com o fundo desfocado. Dentro dela vem a tela inteira do clone (`/os/chamados/acompanhamento/<nº>`, sem cópia) numa
  moldura própria: com a página do meio entre ela e o Nexus, o `window.__osTopo()` da tela para na do meio (ela não tem o
  `data-nexus`), a tela se vê embutida (`os-embutido`) e sai sem o cabeçalho e as abas. Sem o login do Fracttal, a do
  meio diz "Para abrir o chamado, entre pelo Fracttal", com a mesma volta do card (`/os/_nexus/card/voltar`). O Esc
  dentro dela avisa o Nexus para fechar (`{nexusChamado: 1, tipo: 'fechar'}`), salvo com um diálogo da tela aberto.
  Os links da tela (o "← Acompanhamento", a OS, os outros chamados do ativo) andam dentro da janela.
- **O X do card** ficava escondido atrás do cabeçalho fixo dele, também no Histórico (`.os-modal-x` com z-index 2, o
  `.det-top` com 3, e o clique caía no cabeçalho). Passou a 4, no `os.css`.
- **Como provar:** `tests/test_torre_oscreator.py` (a moldura, o aviso sem login, o `ir`) e
  `tests/test_engenharia_equipe.py` (o quadro carrega o componente; o nº aponta para `/os/os/<id>?status=`). Também foi
  conferido num Chrome sem janela, sobre um Nexus de ensaio com o Fracttal falso:
  - o card do quadro abre com os anexos contados;
  - o diálogo de trocar o responsável tem a busca;
  - o Esc fecha o diálogo e depois o card;
  - concluir (de mentira) relê o quadro;
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
    mudou. **Com mais de um ativo (28/10/2026)**, a seção vira "SUBTAREFAS POR ATIVO (n)" e cada linha abre pelo ATIVO,
    com o título embaixo; o banner do topo diz "N ativos: …"; até 4 ativos as subtarefas de cada um já vêm abertas
    (Levi: "quando a OS tem mais de um ativo e eu abro o card da OS não diferencia. Tem que dar para ver as subtarefas por
    ativo", a "Verificação de Tracker Parado" em dois trackers, o mesmo título nas duas tarefas). Várias tarefas no mesmo
    ativo seguem pela tarefa. Prova: `tests/test_oscreator_card_por_ativo_28_10.py`; conferido no Chrome sem janela a
    1280 px e numa moldura de 375 px (escuro e claro, 375 de 375 sem rolagem);
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
- **Onde mora a cor: no clone.** Cada `.css` do `os_web/static` ganhou no fim o par do
  claro de cada cor do escuro, em `:where(html[data-tema="claro"]) <o mesmo seletor>`; o bloco TEMA CLARO do fim do
  `os.css` tem a paleta, `--osc-*`, que é a do tema claro do Nexus (`nexus.css`), e as variáveis de cada folha no claro.
  Sem o Nexus em cima (a página aberta sozinha, como no 5090 do oem congelado) ninguém põe o atributo: nada disso vale, e
  a tela é a de sempre.
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
  (`ATALHOS`). O oem não perde a tela: o 5090 segue com ela.
- **Os arquivos que ficaram não mudaram**: o `lancador.py`, o `performance.html` e o `os.css` ainda desenham o card
  "Tickets" da Performance, a pílula dele no card do setor (Início) e as regras `tk-*`. Os links saem na ponte, na
  resposta (`_SEM_TICKETS`: todo `<a href="/os/tickets...">`); as regras `tk-*` ficam sem uso.
- **Fica** a linha de ticket que nasce junto da OS da Performance (a caixa "Gerar ticket", `api.nascer_ticket` →
  `tickets_nasce`, que usa `tickets_api`, `tickets_diario`, `tickets_escrita` e `tickets_spec`): é da criação de OS, não
  da tela. O `/os/api/acomp/<folio>/ticket` é o nº do chamado no fabricante (Acompanhamento de chamados) e também fica.
- **Sem a faixa de abas dentro do Nexus** (Levi: "quero que mantenha esse carregamento mas tire a visão de abas da parte
  de cima pois como já temos as abas laterais, fica redundante, para um sistema separado, quero passar a impressão de
  unidade!"). A ponte põe `.os-tabs{display:none}` no `_ESTILO_NEXUS` (some a faixa da casca e a da tela aberta
  sozinha); a casca continua guardando cada tela aberta, viva, e o menu lateral acende a de cada item já carregada. Sem
  o X de fechar, a ponte põe um teto no `abas.js` (`_ABAS_MAX` = 12 além do Início: os 9 itens da torre e mais três): ao
  abrir a 13ª, sai a acesa há mais tempo, nunca a ativa. Tudo na ponte: o arquivo do clone não muda, e no 5090 (o oem) a
  faixa continua. Prova: `test_dentro_do_nexus_sem_a_faixa_de_abas_e_as_telas_seguem_vivas`.

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
ponte (`ponte.area_pcm`): administrador passa sem ler nada; o resto, pelo setor de Base → Acessos → Pessoas e setores, pelo setor_id
(`SID.PCM`, `cadastro/setor_ids.py`; pelo nome até 04/11/2026). Sem saber o setor (banco fora, Nexus sem a `NEXUS_PESSOA_HMAC`), fecha — só o
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
- Painel, Fila e Histórico leem a MESMA lista, guardada por `LISTA_TTL` (120 s) por pessoa; os catálogos pelo dono deles
  (`catalogos.py`, desde 31/10/2026; eram 30 min aqui, `CATALOGO_TTL`); quem grava (criar, aprovar, status, observação,
  cancelar, tema) esquece a lista;
- a carga fria pede tudo ao mesmo tempo (`_ao_mesmo_tempo`, com o executor que leva a sessão do Fracttal para as
  threads): custa a leitura mais lenta, não a soma;
- o catálogo de ativos VENCIDO (mais de 24 h) não segura mais a página: o nome das solicitações vem do catálogo central
  como estiver e o download dos ~22 mil ativos (mais de cem pedidos, minutos) vai para uma thread (`_indice_ativos` pede ao
  `api._renovar_catalogo_por_tras`; até 31/10/2026 ele tinha o renovador dele). Quem resolve o ativo da OS na aprovação
  continua com o catálogo em dia (espera o download que já está em curso, sem começar outro);
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
(templates, `.js` e o JSON das rotas): ao pé da letra, levavam ao `/os/` da PLATAFORMA. O arquivo do clone não muda
(roda sozinho na raiz, no 5090 do oem); quem põe o prefixo é a ponte, na resposta, só quando há prefixo:

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

- **O Nexus é a casa do OS Creator Web** (31/10/2026, etapa 1 do canto central; de 06/10 a 30/10 ele era a referência e o
  oem acompanhava, por uma ferramenta de sincronia). Mudança no OS Creator: faça aqui, na cópia, e prove aqui, com a
  suíte do Nexus (`python -m pytest -q -k oscreator`). Não há o que levar ao oem, e não se escreve em
  `C:\GridcoBuild\oem`: ele fica congelado como estava, servindo o 5090. O custo do jeito de antes apareceu em 30/10/2026:
  a cópia já passava do oem (os arquivos do cabeçalho de pedido automático não tinham sido levados) e o teste que cobrava
  a igualdade estava vermelho nesta máquina.
- **O que é só do Nexus (o portão, o topo, a moldura, o menu lateral, o tema, o prefixo) vai na `ponte.py`, na resposta**,
  e não nos arquivos do clone: segue assim. A regra "a cópia não importa o pacote `nexus`" era para o supervisório não
  quebrar ao receber a cópia, e saiu com a sincronia. Só os dois leitores do servidor importam o `nexus` (31/10/2026): o dos
  ativos (`os_creator/ativos_leitor.py`: o cliente REST do Fracttal, a credencial, a foto do banco e os minutos ocupados,
  `nexus.casca.minutos_ocupados`) e o das OS (`os_creator/os_leitor.py`: o leitor de OS do Nexus, `nexus.campo.tarefas_os`, o
  `nexus.campo.fracttal`, os minutos ocupados e o contador `nexus.casca.fracttal_conta`). Só o `servir.py` os carrega (o
  catálogo, a lista de OS e as telas os chamam pelo que eles registram em `ativos_central.ligar_leitor` e
  `os_central.ligar_leitor`, sem importá-los); o resto do clone, a lista de OS inclusive (`os_central.py`, `os_registro.py`,
  `os_disco.py`), segue sem o `nexus`, e é por isso que o "Rodar sozinho", acima, funciona. Os catálogos pequenos (etapa 4)
  são o mesmo par: o `catalogos.py` e o `catalogos_planos.py` seguem sem o `nexus` (servidos sozinhos, pela sessão de quem
  usa), e o laço das pessoas pelo REST mora no `catalogos_leitor.py` (o cadastro, o cliente REST, a credencial, o contador e
  o minuto da lista de minutos ocupados), que só o `servir.py` carrega e que se registra em `catalogos.ligar_leitor`.
- **Onde está cada função** (31/10/2026, etapa 5.3): o `api.py` é só o cliente do Fracttal e a fachada; cada assunto mora no
  módulo dele (seção "O mapa dos módulos"). Código novo vai no módulo do assunto; o que ele chama vai pelo `api.`, e o teste
  troca `api.X`. O `tests/test_oscreator_fachada.py` acusa a chamada pelo nome local.
- O `os_creator/.env` (a credencial do Fracttal da máquina) é do `.gitignore`: nunca entra no git.
- Usa a mesma pasta de dados do OS Creator (`%APPDATA%\CriarOS-Fracttal`). Na mesma máquina, ele divide com o
  supervisório a chave da sessão e o token do banco. A cópia em disco do catálogo de ativos mora nela, em
  `oscreator\ativos.json.gz` (o `assets_cache.json` de lá é do supervisório e do oem; o Nexus só o lê, uma vez, para migrar), e
  a dos catálogos pequenos em `oscreator\catalogos\` (um arquivo por catálogo, sem e-mail).
- **Não usa PyQt6** (31/10/2026, etapa 1 do canto central). A ponte, o `api` e todo `os_web.*` importam sem ele: o rastro
  dos imports (estático, com os de dentro de função, e dinâmico, com o PyQt6 bloqueado) mostrou um elo só, o `abrir()` do
  descritor `steps/engenharia`, que importava a tela de mesa e, por ela, o `steps/ui.py`, e que a web nunca chamou (a rota
  `/os/engenharia` lê só título, descrição e ícone). Saíram o `steps/ui.py`, o `steps/engenharia/tela.py` e o `abrir()`;
  o PyQt6 saiu do `requirements.txt`. Os testes do OS Creator abriam com `pytest.importorskip("PyQt6")` por um motivo
  que não era verdade ("o clone importa o `steps/ui.py` ao montar a tela de Engenharia"), e numa máquina sem PyQt6 a
  suíte inteira do OS Creator pulava em silêncio; o `importorskip` saiu de todos. Prova: `tests/test_oscreator_sem_pyqt.py`
  (num subprocesso com o PyQt6 bloqueado, o Nexus e o clone sobem, o login e a Engenharia abrem; nada do repositório
  importa nem pede PyQt; nenhum `requirements.txt` o traz). Voltou um `import PyQt6`? O teste diz o arquivo e a linha.

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
  do card: OS concluída, cancelada ou de várias tarefas não deixa). A linha do motivo do PCM vai pelo mesmo caminho
  (`/os/_nexus/pcm/nota`, `ponte.pcm_nota`, desde 26/10/2026; a regra no `nexus/pcm/CLAUDE.md`, "A nota da OS ao
  escolher o motivo"): rota do Nexus que precisa do login do Fracttal mora em `/os/_nexus`, porque o `os_sessao` só vai
  para `/os`. Desde 29/10/2026 as ações da gaveta do ativo da Confiabilidade também
  (`/os/_nexus/engenharia/acompanhamento/pegar`, `/encaminhar`, `/<id>/salvar`, `/<id>/comentar`): o Pegar cria a OS
  de análise do acompanhamento no nome da pessoa, o encerrar conclui a OS e o comentário vai à nota dela (as regras em
  `nexus/engenharia/os_analise.py` e no `nexus/torres/engenharia/CLAUDE.md`). Nada disso muda a cópia: só chama o `api`.
- **Criar OS do zero (25/10/2026):** o mesmo endereço em `/os/tradicional?` (o "Criar OS" da OS do Quadro da equipe;
  Levi: "Fará os mesmos preenchimentos automáticos que já faz na solicitação"): o Passo 1 abre com o cliente, a usina e
  o ativo marcados (a busca mostra o ativo) e a data do incidente no campo; a OS pai vem escolhida no campo do Passo 1,
  ao lado das datas desde 26/10/2026 (`sugerir`), e a OS seguinte, depois de gerar, não herda a OS pai (como na
  Solicitação).
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

## Criar OS do zero: a tela de uma vez, sem os "Próximo" (26/10/2026)

Levi, no mesmo dia: "1 - Tirar esses botões de Próximo"; "2 - Ao lado de data do incidente e data programada inclua OS
pai"; "3 - Em etiquetas não precisa ficar mostrando as opções ... o ideal é quando a pessoa for pesquisar aparece a lista";
"4 - ... troque por Título da tarefa ... [Ativo(APENAS NOME DO ATIVO ... SE FOR O ATIVO DA USINA ENTÃO FICARÁ Usina se for
inversor ficará Inversor 1.1 ...)] - Título"; "5 - Abaixo de classificação adicione a parte de adicionar o técnico".

- **Sem os "Próximo"** (Passos 1 e 2): os passos já estão todos na página. O "Passo N de 4" segue o card em que a pessoa
  mexe (`focusin`); o "Voltar" dos Passos 2 e 3 ficou. Quem valida é o "Concluir e Gerar OS": ativo, tipo, título, técnico,
  OS pai digitada e não escolhida, subtarefa.
- **A OS pai no Passo 1**, ao lado das duas datas (`.trad-linha3`, uma embaixo da outra a menos de 900 px), com a mesma
  busca de antes (`/os/api/tradicional/os-pai`; a escolha agora no `mousedown`, e o `blur` fecha a lista). A sugestão pelo
  endereço (`?os_pai=<id>&os_pai_folio=<nº>`, o "Criar OS" do Quadro da equipe da Engenharia) já a deixa escolhida.
  Saiu do Passo 4.
- **Etiquetas:** a lista só aparece com texto na busca (casa como a busca comum, `OsBusca.casa`); as marcadas ficam embaixo,
  cada uma um botão "nome ✕" (`os-btn secondary mini`) que a tira; Esc limpa a busca.
- **"Título da tarefa"** (era "Descrição da tarefa", e o campo virou uma linha): cada OS sai "[Ativo] - Título" pelo
  `tradicional_web.titulo_da_os`, e o nome do ativo é o `nome_no_titulo`: o item da planta (tipo "Usina") vira "Usina";
  os outros, o nome curto do catálogo ("Inversor 1.1"). A cascata manda o mesmo nome (`nome_titulo`) para a prévia. A Nova
  solicitação segue com o nome dela (no ativo da usina, o nome da usina).
- **O técnico no Passo 2**, embaixo da Classificação: a mesma lista com a busca (`resp_busca`, `resp_lista`), carregada ao
  abrir a tela, e "Escolhido: …" embaixo. O duplo clique que gerava saiu (geraria sem a conferência). A OS seguinte começa
  sem técnico e sem OS pai.
- **O Passo 4 é a conferência:** quantas OS, o responsável, a OS pai, o título com o 1º ativo, o aviso das usinas, "já
  realizada" e agrupar, Cancelar/Gerar. O rótulo do passo continua o do app ("Responsável", `STEP_LABELS`, que o teste do
  oem compara com o app de mesa).
- **Prova:** `tests/test_oscreator_criar_os_titulo_26_10.py` (o "Usina" e a tela pedida, item a item) e
  `tests/test_oscreator_criar_os_25_10.py` (a OS pai da sugestão no Passo 1). Na bancada (o Criar OS do fixture com a
  cascata e as buscas de mentira), a 1024 e a 375 px, no escuro e no claro: o "Criar OS" com a sugestão abre com a OS pai
  16784 no Passo 1; datas e OS pai na mesma linha; a etiqueta pela busca vira o botão e a lista some; o técnico escolhido
  no Passo 2; a conferência; o pedido com a OS pai, o técnico e a etiqueta; a tela zerada depois; as travas (sem técnico;
  OS pai digitada e não escolhida); "[Usina] - Limpeza da subestação"; sem rolagem lateral. No oem, o
  `test_os_web_tradicional.py` cobra os textos novos (cópia de trabalho; sem commit lá).

## Clonagem de planos: a Noite (17:00) na programação em massa (28/10/2026)

Levi: "Em OS Creator > PCM > Clonagem de Planos > Em 'Plano de tarefas' quero a opção Noite 17:00". Na "Programação em
massa" do card Plano de tarefas (`pcm.html`, `/os/pcm`), ao lado de Manhã (07:00) e Tarde (13:00): o botão Noite (17:00)
põe 17:00 em todas as linhas marcadas e mantém o dia de cada uma (`pcm.js`, o mesmo `editores` dos outros dois). O app de
mesa não tem o botão. Prova: `tests/test_oscreator_card_por_ativo_28_10.py::test_a_clonagem_de_planos_tem_a_noite_17h`.

## Nova solicitação e Criar OS: os ativos do cliente numa leitura só, e a Engenharia de 10 em 10 (28/10/2026)

Levi: "Em solicitação > PCM, quando pesquisa o cliente carrega, quando pesquiso a usina carrega novamente. na minha cabeça
os ativos devem carregar apenas 1 vez e depois é mais fluido" e "em solicitação > engenharia: tá mostrando todos os ativos
de uma vez, o certo é de 10 em 10".

- **PCM:** escolher o cliente pede `/os/api/tradicional/catalogo?cliente=<x>&ativos=1`, que traz as usinas e os ativos de
  todas elas (`tradicional_web.ativos_do_cliente`: os campos do `ativos_de`, mais a `usina`); a usina, o tipo e a busca
  filtram na tela, sem novo pedido nem o círculo de carga. O cliente que já veio fica na memória da página (`porCliente`);
  erro não fica. A resposta vem comprimida (gzip no servidor). A sugestão pelo endereço segue igual (`sugerir` espera as
  duas etapas). **O Criar OS faz o mesmo** (Levi, no mesmo dia: "Aplique o mesmo carregamento único dos ativos no Criar
  OS"): `tradicional.js`, `doCliente` e `porCliente`; o ↻ relê o catálogo e esquece o que já veio; o marcado de outra
  usina segue marcado (o aviso das usinas de 26/10 não mudou).
- **Engenharia:** a tabela mostra 10 e o rodapé "Mostrando N de M ativos" com "Mostrar mais 10" e "Mostrar todos (M)", o
  mesmo da Nova solicitação PCM; o marcado fora da tela continua valendo (o rodapé conta), e trocar a usina, o tipo ou a
  busca volta aos 10. "Selecionar todos" marca todos os do filtro, como antes.
- **Prova:** `tests/test_oscreator_solic_ativos_28_10.py`. No Chrome sem janela (fixture com 2 usinas, 25 ativos na 2ª):
  na PCM e no Criar OS, um pedido só para o cliente, e trocar de usina não pediu de novo (no Criar OS o ↻ pediu de novo, e
  o "Criar OS" da Engenharia abriu com o ativo marcado e a OS pai); na Engenharia,
  10 → 20 → 25, a busca filtra e limpar volta aos 10 com o marcado mantido; a 375 px, no claro, sem rolagem lateral.

## Performance: a Inspeção Geral do Inversor sai Corretiva (29/10/2026)

Levi: "No OS CREATOR PERFORMANCE > INSPEÇÃO DO INVERSOR QUERO O TIPO DA TAREFA COMO CORRETIVA!". O tipo vinha do plano
do Fracttal ("[Grid Co.] - Inspeção Geral do Inversor"), que o `create_planned_os` copia. Agora o app troca na hora de
criar (`api.TIPO_TAREFA_DO_PLANO` e `api.com_tipo_da_tarefa`, casados pelo trecho do nome do plano, como as
`SUBTAREFAS_EXTRA`): `id_task_type_main` = Corretiva (43885) e o nome dele. Vale na OS por ativo
(`create_performance_os`) e na agrupada (`create_performance_os_agrupada`), e o resumo do plano na tela diz "Tipo:
Corretiva" (`/os/api/performance/plano`). O plano do Fracttal não muda (é de outra área e vale para quem cria por fora);
os outros planos seguem com o tipo deles, e a Clonagem de planos do PCM não passa por aqui. Prova:
`tests/test_oscreator_perf_tipo_corretiva_29_10.py`. Falta conferir numa OS real.

## O card sem Abrir chamado e Clonar, com o PDF; a Zeladoria na Fila; os anexos da Nova solicitação (29/10/2026)

Levi, no card da OS: "A palavra 'Ordem de serviço' abaixo do número da OS não cabe nas bordas ... pode tirar essa borda";
"tire o botão abrir chamado ele não servirá mais"; "Ao lado esquerdo do card de solicitação tem que ter um símbolo de
baixar para pessoa baixar um PDF da OS"; "Tire o botão clonar esta OS". Na Fila: "Não consegui aprovar a solicitação 4126.
Falha ao criar as tarefas: ?: Tipo de tarefa desconhecido: Zeladoria". Na Solicitação: "quero que seja possível
adicionar anexos como PDFS e fotos. E quando o PCM gere uma OS pela fila de PCM com aquela solicitação o anexo vá junto!"

- **O card** (`os_detalhe_conteudo.html`): o "Ordem de serviço" usava a classe `det-sub`, a mesma da caixa de cada
  subtarefa, e herdava a borda e o fundo dela; agora é `det-num-sub`, só o texto. O botão "PDF" (`.det-pdf`, a seta de
  baixar) fica à esquerda da pílula da Solicitação e usa o mesmo PDF da cadeia do chamado (`[data-os-pdf]` no
  `os_acoes.js`, `POST /os/api/os/pdf`); o aviso vai para o `[data-pdf-msg]` do card. Saíram do rodapé o "Clonar esta OS"
  (a Clonagem segue no menu) e o "Abrir chamado".
- **Os anexos do card** (a pergunta do Levi): `.mp4` e PDF entram em "documentos", com "Abrir" (o vídeo toca e o PDF abre
  no navegador) e "Baixar" (a rota renova o link do Fracttal); o "Baixar todos" os põe no .zip.
- **A Zeladoria:** o `create_os_rpc` resolvia o tipo pelo NOME só na lista fixa `TASK_TYPE_MAIN` (Corretiva, Preventiva,
  Inspeção…), e a Fila do PCM oferece os tipos ao vivo do Fracttal. Agora, fora da lista fixa, procura no catálogo vivo
  (`api.tipo_main_ao_vivo`, relido uma vez se não achar); só recusa o nome que não existe em lugar nenhum. Vale para a
  Fila e para qualquer caminho que mande o tipo pelo nome.
- **Os anexos da Nova solicitação** (o Levi escolheu "No Nexus até aprovar"): nenhuma ferramenta nossa sabe gravar anexo
  numa solicitação do Fracttal (só ler). Até 5 arquivos (PDF, imagem, planilha, documento; 10 MB cada, 20 MB no total),
  conferidos como na Solicitação de Engenharia (`solic_eng_web.anexos`, com a frase "Nenhuma solicitação foi criada.");
  vão em multipart (`payload` + `anexos`) e ficam no servidor, na pasta de dados do OS Creator, com o nº de cada
  solicitação criada (`os_web/solic_anexos.py`). O bloco [PCM] da observação ganha "Anexos no Nexus: …". A Fila mostra
  "Anexos que vão para a OS" (com link) e a confirmação diz quantos vão; ao aprovar, cada um sobe na tarefa da OS pelo
  `solic_eng_web.anexar` (o caminho dos anexos da Engenharia) e o que subiu sai do servidor; o que falhou fica guardado e
  a mensagem diz. O Histórico de solicitações lista os guardados (`/os/api/solic/<nº>/anexo-guardado`). Na solicitação
  vista no Fracttal web o arquivo não aparece; quem aprova pelo app de mesa ou pelo Fracttal não leva o anexo.
- **Prova:** `tests/test_oscreator_card_e_anexos_29_10.py`. No Chrome sem janela, com o fixture: o card a 1280 px e a
  375 px no claro (o "Ordem de serviço" sem borda, o PDF à esquerda da Solicitação, o rodapé com Fluxo, Concluir, Cancelar
  e Fechar, 365 de 375 sem rolagem); a Nova solicitação aceitando o PDF e a foto, recusando o .exe com o aviso em âmbar e
  tirando um anexo; a Fila com os dois anexos e a confirmação "levando 2 anexo(s)". Falta a prova ao vivo (uma
  solicitação com anexo em TESTE - PA aprovada na Fila, o anexo no card da OS).

## O tempo na Clonagem e o tempo da OS = a soma das tarefas (30/10/2026)

O time do PCM: "quando clonamos uma OS ela está vindo com horário padrão de 10minutos por tarefa... gostaria que o tempo
que viesse fosse o cadastrado do plano, que seria atualizado no 'Atualizar todas do modelo'" e "nas SSs [Solicitações de
Serviço] o tempo que aparece na OS do Fracttal permanece 10 min, porém nas tarefas aparece o tempo que foi solicitado,
quando criada pela Fila do PCM".

- **A Clonagem:** cada tarefa leva o tempo da tarefa de origem (`get_os_para_clonar` → `duracao`, o `duration` dela),
  mostrado na coluna Tempo (HH:mm). O "Atualizar do modelo" e o "Atualizar todas do modelo" trazem, junto com as
  subtarefas, o tempo cadastrado no modelo (`_duracao_do_modelo`: o do evento da lista de modelos; sem ele, o do detalhe
  do modelo, pelo valor cru, porque o `get_plan_details` põe 900 quando falta; sem tempo no modelo, a tarefa fica com o
  que tinha). O servidor só aceita de 1 min a 24 h (`clonar_web.preparar_tarefas`); fora disso, os 10 min de sempre.
- **A OS:** o `_work_order_insert` (a fase que junta as tarefas numa OS numerada) punha `duration=600` fixo. O
  `clonar_os` (a Clonagem e a Fila do PCM) passa a soma do tempo das tarefas criadas; a retomada da Fila (a tarefa que
  ficou de uma tentativa anterior), o tempo dessa tarefa. No mesmo dia o PCM voltou: "o clonador deu certo tanto na
  tarefa como na OS ... agora criando do zero o tempo na OS continua 10 min, só na tarefa que o tempo é o que a gente
  colocou" (a Clonagem de planos, com o tempo editado na linha). Agora **toda OS que junta tarefas tem a soma do tempo
  delas** (`_tempo_da_os`): a Clonagem de planos do PCM (`create_planned_os_multi`, e o `create_planned_os_one_wo`), a
  agrupada do Criar OS do zero e da Engenharia (`create_work_orders_agrupada`) e a agrupada da Performance. O
  `create_os_rpc` e o `create_planned_os` devolvem o `duracao` com que a tarefa nasceu; a tarefa sem tempo conta os
  10 min. A OS de uma tarefa só (o Criar OS do zero de uma OS por ativo, as datas, a Performance de uma OS por ativo)
  já saía com o tempo da tarefa. **A conta mora em UM lugar desde 31/10/2026**, no `os_juntar.juntar_em_os` (seção "Um
  caminho só para juntar as tarefas numa OS"): os caminhos acima só criam as tarefas e o entregam.
- **Prova:** `tests/test_oscreator_tempo_clonar_e_fila_30_10.py`. No Chrome sem janela, a tela de Clonar com duas
  tarefas (uma com 1h30, outra sem tempo): 01:30 e 00:10; depois do "Atualizar todas do modelo", 02:00 e 01:00. Ao vivo,
  o PCM conferiu o clone (a tarefa e a OS com o tempo total); falta a OS da Clonagem de planos e a de uma SS da Fila.

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

## Incluir anexo e as ações da OS nas telas que abrem a OS (06/11/2026)

Levi: "poderia incluir um botão de incluir anexo? Aí incluiria um anexo na OS e será possível ver o anexo e baixar os
anexos conforme já temos quando clicamos na OS no histórico de OS. Bote isso em Chamados > Garantias, Performance >
Quadro de equipe, Engenharia > Quadro de equipe"; "Nessas telas devem ter essas opção também: Enviar para verificação,
concluir e cancelar!".
- **Incluir anexo** (`POST /os/api/os/<id>/anexos`, `rotas_os_acoes.api_anexos_incluir`): as regras e o envio dos
  anexos da Solicitação de Engenharia (`solic_eng_web.anexos`: o tipo conferido pelo conteúdo, 10 MB cada, 20 MB juntos, 5
  por vez; `solic_eng_web.anexar`: o S3 do Fracttal e a 1ª tarefa da OS). Numa OS que já existe: o nome que já está nela
  ganha " (2)" (a chave no S3 é `.ot/<OS>/<nome>`, e o novo apagaria o antigo), e os anexos são relidos depois do envio,
  sem as URLs pré-assinadas (`_nomes_na_os`): o que não aparece na OS volta como falha (o Fracttal aceita calado).
- **No card** (o que o Quadro da Performance e o Histórico abrem): o "Incluir anexo" embaixo dos dois cards de anexos
  (`data-acao="anexo-incluir"`, o seletor com o accept, `acoes_anexo_aceitar`); a frase das regras
  (`acoes_anexo_regra`) vai na dica do botão, e não à vista (06/11/2026: "tire o texto [...] e organize melhor a
  informação"). A tela do chamado de Garantias, igual.
- **Os diálogos das ações** (Concluir, Fazer a tarefa, Cancelar e Anexos) moram em `templates/_dlg_acoes_os.html`, que o
  card e a tela do chamado incluem; ele tira do `d` as contas do Concluir, como o card.
- **Enviar para verificação** (`POST /os/api/os/<id>/verificacao`): o status 2 pelo `api.mudar_status_os(wid, 2)`
  (`tasks.work_orders_change_status`), o caminho que a revisão das OS provou no ar (OS 18630 e 18635; o `to_in_review`
  só vale ao CRIAR a OS). Só a OS Em Processo vai; o status é lido antes e depois (o Fracttal aceita calado), e o quadro
  de Garantias recebe o status novo (`_no_quadro_de_garantias`, o `rotas_acomp._ajustar` do Finalizar de lá; o Cancelar
  também). Ele só muda o status: o diálogo (`verificacao`, como o do Concluir) mostra as subtarefas sem resposta e
  oferece o "Fazer a tarefa" antes (o executar sozinho não muda o status). No card, o botão sai na OS que não está Em
  Verificação, Concluída nem Cancelada.
- **Na tela do chamado de Garantias** (`acomp_os.html`, que recebe o `d` da OS): a caixa "Ações da OS" com os anexos (a
  contagem do card), o Incluir anexo, o Enviar para verificação (OS em processo) e o Cancelar (OS aberta), com
  `data-os-acoes data-no-lugar`. Sem o Concluir: o "Finalizar chamado" do topo já conclui a OS no Fracttal e ajusta o
  quadro, e dois finalizar confundiriam. O que muda o status relê a página (`relerPagina` no `os_acoes.js`); o anexo só
  relê a contagem.
- **A moldura do card abre numa ação** (`/os/_nexus/card/<id>?acao=`, só as do card: `anexos-os`, `anexos-sub`,
  `concluir`, `cancelar`, `verificacao`): o `card_os.html` clica no botão do próprio card depois de carregar. O
  `NexusOsCard.abrir(id, {acao})` manda; é assim que a página da OS da Engenharia abre o Concluir, o Cancelar e os anexos.
  O Incluir anexo não vai por aí: o seletor de arquivos não abre dentro da moldura com o clique da tela de baixo.
- **Colar para anexar** (Levi: "anexar com CTRL + V OU WINDOWS + V"): o arquivo ou a imagem da área de transferência
  (o Win+V cola do histórico pelo mesmo evento `paste`) espera um "Anexar à OS" à vista, para colar sem querer não subir
  nada; colar num campo de texto segue sendo texto. A imagem colada chega como "image.png" e ganha o nome com a data e a
  hora (`nomeColado`), para não virar "image (7).png" na OS.
- **As tarefas da OS, uma a uma** (Levi, 06/11/2026, na página da OS da Engenharia: o check, as subtarefas de cada
  ativo, "Iniciar atividade" com pausa, "Anexar" na tarefa e "x anexos"):
  - `GET /os/api/os/<id>/tarefas`: cada tarefa com o ativo, `feita` (a data de fim no Fracttal, `situacao_tarefa`), as
    subtarefas respondidas e o cronômetro (`execucao_atual`, as tarefas em paralelo).
  - `POST /os/api/os/<id>/tarefa/<tid>/cronometro` (`acao`: iniciar, pausar com `motivo` de `/os/api/execucao/motivos`,
    retomar, concluir): as regras do `os_execucao` (a pausada é retomada antes de encerrar), o estado relido depois de
    cada passo (o Fracttal aceita calado: 502 quando não mudou) e a tarefa tem de ser da OS (404). O concluir pede as
    obrigatórias respondidas e só encerra o tempo (`finalizar_execucao`): o `/executar` lança outro registro, e as horas
    dobrariam.
  - `POST /os/api/os/<id>/tarefa/<tid>/respostas`: grava as respostas (`salvar_subtarefas`) sem lançar execução e diz
    quantas obrigatórias faltam, relidas.
  - O Incluir anexo aceita `tarefa`: o arquivo vai para a aba Anexos daquela tarefa, e não para a 1ª. A contagem
    (`/os/os/<id>/anexos`) passa a trazer `arquivos_por_tarefa` (o `get_os_anexos` diz a tarefa de cada arquivo); o
    `por_tarefa` segue sendo o das fotos das subtarefas, que o botão dos anexos da tarefa no card mostra.
  - A provar no TESTE - PA antes de abrir para a equipe (`TAREFAS_PARA_A_EQUIPE` na torre da Engenharia): se encerrar o
    cronômetro grava a data de fim da tarefa (o check), se as horas não dobram (`historico_execucao`) e se o anexo da
    tarefa aparece nela.
- Prova: `tests/test_oscreator_anexo_incluir.py`, `tests/test_oscreator_acoes_nas_telas.py` e
  `tests/test_oscreator_tarefas_da_os.py`.

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

- **Desde 31/10/2026 este é o CAMINHO DE HOJE** (tarefa 3.3 do canto central, seção "As telas leem da lista central de
  OS"): as visões leem primeiro da lista central, depois da conferência da pessoa no período (a dela, exata, até a marca
  d'água), e vêm para cá quando ela não cobre o período, não tem um campo que a tela mostra, ou a pessoa não passou (e no PC,
  sem leitor). Com a lista central cobrindo o período, a "Todos" de baixo não é dividida: quem chega aqui segue com a lista
  DELA (Ruling BU da rodada 2 da 3.3: quem vê tudo lê da lista central e não ancorava a dividida, e a lista da 1ª restrita
  virava a de todos, herdada por outra restrita com o mesmo total).
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

## Os filtros do Histórico só valem no Aplicar (03/11/2026)

Levi, 03/11/2026: "quero que consigamos selecionar os filtros sem carregar a cada filtro, pode aparecer um botão discreto de
Aplicar sempre que selecionar algum filtro, aí só filtra mesmo se aplicar". Antes, Criado por, Etiqueta e Período buscavam no
servidor a cada troca, e Status, Cliente, Usina e Tipos filtravam a tabela na hora: montar três filtros custava três buscas.
No mesmo dia ele pediu o visual: "refaz esse modelo de filtros [...] algo minimalista e moderno ao mesmo tempo", "use as cores
Black: 030407, Blue: 1558c9, lime: D4FF24", "opção A, suspenso com um botão de aplicar no final" e "quero que todas as opções do
filtro sejam digitáveis para facilitar encontrar o que quero". A maquete aprovada é o **modelo A**, e a tela é ela
(`templates/historico.html`; o CSS na seção "os filtros no modelo A" do `static/os.css`; a busca no `static/os_busca.js`).
- **A barra, numa linha só** (no celular quebra em linhas curtas: as abas, as duas buscas, e o período com o Filtros e os
  ícones): as abas Histórico Geral, Atribuídas a mim e Visão COS (controle segmentado, a ativa em azul); a busca por texto (filtra
  enquanto se digita, sem Aplicar); o "Buscar OS" pelo nº, compacto (abre a OS direto); o botão do **período**, que mostra o aplicado
  ("04/10 – 03/11") e abre o painel; o botão **Filtros**, com a contagem em lima dos filtros aplicados (o período não conta); e os
  ícones de Exportar (Ctrl+E) e Atualizar (F5), só ícone, com `title`. O "Lista das HH:MM · atualiza a cada 10 min" ficou em texto
  apagado na linha do resumo da tabela.
- **As etiquetas**, abaixo da barra: uma azul por filtro aplicado ("Status Em Processo", "Usina 3 selecionadas", "Criado por …").
  O × tira aquele filtro e **aplica na hora** (pelo mesmo caminho do Aplicar: o da tabela sem pedido, o do servidor com a busca).
  O "Limpar tudo" faz o que o Limpar filtros de antes fazia: sai o resto e a busca, e ficam a visão, o Criado por e o período (a
  tela volta pelo endereço limpo). Ele só aparece quando há o que limpar. Sem filtro aplicado, a linha não existe. O Criado por vira
  etiqueta sempre que não é "Todos os usuários": no Histórico Geral o padrão é a própria pessoa, e a etiqueta já está lá (a lista é
  mesmo só das OS dela).
- **O painel suspenso**, preso ao botão do período ou ao Filtros (o mesmo painel): o período primeiro (os atalhos 7 dias, 30 dias e
  Este mês só **preenchem as duas datas** e esperam o Aplicar; "7 dias" é de 7 dias atrás até hoje, como os 30 do padrão da tela) e
  depois Criado por, Etiqueta, Status, Cliente, Usina, Tipo de ativo e Tipo de tarefa, em 2 colunas (1 no celular). O campo que mudou
  em relação ao aplicado ganha um ponto lima. No rodapé: **Limpar** (zera Etiqueta, Status, Cliente, Usina e os Tipos e espera o
  Aplicar; Criado por e o período são o escopo da lista e ficam, como no Limpar de antes), "N alterações" e o **Aplicar** em lima,
  apagado sem alteração. Com menos de 640 px o painel vira uma folha de baixo para cima, na largura toda, com o rodapé fixo, um véu
  atrás e as listas no fluxo (solta por cima, a lista seria cortada pela rolagem da folha).
- **Fechar sem aplicar descarta** (Esc, clique fora, o botão de novo ou o × da folha): os campos voltam ao aplicado. O clique fora
  vale na captura, antes de qualquer outro clique da página: o que manda o formulário (as abas da visão, o ↻, o F5, o × de uma
  etiqueta, o Limpar tudo) descarta o que estava no painel antes de mandar. Enter numa data é o Aplicar; nos outros campos do painel
  não manda nada (o Enter solto mandaria o formulário pelo 1º botão de envio, o ↻, que busca tudo de novo e levaria as escolhas sem
  o Aplicar). A atualização de 10 min espera com o painel aberto. Período sem as duas datas, ou com a inicial depois da final, não
  aplica e avisa dentro do painel.
- **A regra do Aplicar** não mudou: Criado por, Etiqueta e Período buscam no servidor; o resto (Cliente, Usina, os Tipos e o Status)
  só filtra a tabela que já está na tela, sem pedido. Os filtros da tabela que não vão ao servidor atravessam a busca guardados no
  `sessionStorage` da aba e remarcados ao chegar (o Aplicar que muda o período e a usina juntos não perde a usina, e a atualização de
  10 min não zera os filtros da tabela); a troca de aba da visão e o Limpar tudo os zeram. **Exceção, achada ao fazer o ×:** a
  página que chegou com Status no endereço já veio CORTADA pelo servidor (ele filtra por status), então nela o Status conta como
  campo do servidor; só pela tabela, tirar a etiqueta mostraria as mesmas OS e diria que são todas.
- **Tudo digitável.** Abrir um campo mostra a lista com a caixa de busca no topo (no PC já com o cursor; no celular não, porque o
  teclado cobriria metade da lista): digitar filtra sem distinguir acento nem caixa ("sao" acha "São"), as setas andam, Enter marca
  (as de vários valores: Status, Cliente, Usina e os Tipos, com o resumo "3 selecionadas", no feminino da Usina) ou escolhe (as de um
  valor só, Criado por e Etiqueta, que fecham ao escolher), e o Esc fecha só a lista, de uma vez, com o texto digitado saindo
  junto (com a lista fechada, o Esc fecha o painel; o painel marca isso com `data-esc-fecha`: nas outras telas o 1º Esc continua
  limpando a busca e o 2º fecha). O `<select name="pessoa">` e o `<select name="etiqueta">` seguem no formulário, escondidos
  (`display:none` dentro do `.fl-cel[data-campo-proprio]`, e é ele que o servidor lê); a lista que a pessoa vê é um `<details
  class="os-multi fl-uni">` com um botão de escolha por linha, e o `os_busca.js` a trata como as outras (a caixa de busca, o teclado)
  e deixa o `<select>` em paz. A cascata Cliente → Usina continua, e o descartar devolve o que ela desmarcou.
- **Cores só por token** (`--fl-*`, no `:root` do `os.css`): o lima `#D4FF24` (a ação: o Aplicar, a contagem e o ponto do que mudou),
  o azul `#1558c9` (o que está escolhido) e o preto `#030407` (o texto sobre o lima), com os "suaves" e as "bordas" em rgba. O par do
  claro está no bloco de variáveis que já existia: o texto azul é o próprio `#1558c9`, o botão lima segue lima com texto escuro, e o
  ponto lima vira o musgo. O fundo da página e o resto do OS Creator não mudaram. O botão Aplicar de hoje de manhã tinha `hidden` e
  aparecia sempre (o `.os-btn{display:inline-flex}` vence o `hidden` do navegador): os controles novos que nascem escondidos
  dizem `[hidden]{display:none}` no CSS.
- **Prova:** `tests/test_oscreator_historico_aplicar.py` roda a página de verdade no node (`tests/historico_pagina_falsa.js`: o HTML
  que o servidor monta é lido por um DOM de mentira que executa o script dela e o `os_busca.js`), com a troca que não filtra, o
  descartar, o × que aplica, o atalho do período, a busca sem acento e o Enter que escolhe. A tela foi conferida no navegador, nos
  dois temas, a 1280 e a 375 px, sobre a bancada do clone com dados inventados.

## O catálogo de ativos central: um só para todas as telas (31/10/2026, etapa 2 do canto central)

Levi, 30/10/2026: "para abrir uma solicitação precisamos de ativos, para criar OS é preciso carregar os ativos, para abrir o
histórico acabamos vendo os ativos [...] a ideia é não ter um carregamento novo por atividade e sim um ecossistema onde as
coisas se aproveitam e não precisamos ficar fazendo novas requisições sempre!" (desenho:
`docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`; esta é a tarefa 2.1 da etapa 2).

**Antes:** três caminhos sobre o mesmo `assets_cache.json`, cada um com a sua cópia: o `load_assets_cached` copiava a lista
inteira (~26 mil dicionários, uns 12 MB de lixo) a CADA chamada; o `rotas_solic._indice_ativos` tinha o índice e o renovador
dele; o `_code_loc` era montado uma vez por processo e nunca refeito (ativo novo sem nome nas OS até o reinício); e o
`_asset_by_code` percorria uma cópia nova por código. Cada push na `main` (uns 10 por dia útil) reinicia o serviço.

**Agora** (`os_creator/ativos_central.py`): UM `Catalogo` por versão, pronto e imutável, para todas as telas e pessoas.
- **O que ele guarda:** a lista (tupla, ordenada por cliente, usina e código), os índices por id, por código, por cliente e por
  cliente + usina, o mapa código -> (cliente, usina curta, tipo) (o antigo `api._code_loc`, que o `api._code_to_loc` devolve) e
  a contagem por tipo; mais `versao` (o sha das linhas ordenadas), `lido_em` e `fonte` (banco, rest, rpc ou disco). Montado UMA
  vez quando a versão chega; trocado inteiro (`trocar`), de uma vez, nunca um pedaço.
- **Quem lê dele:** `api.load_assets_cached` (devolve a MESMA tupla, sem copiar), `_asset_by_code` (uma cópia, pelo índice),
  `_code_to_loc`, `_read_asset_cache` (a lista como está, sem a trava das 24 h), `assets_cache_info`, o índice da Solicitação
  (`rotas_solic._indice_ativos`, sem arquivo nem renovador próprios), o "Investigar ativo", o lugar do ativo no PDF da OS, a
  contagem da tela inicial e a cascata do Criar OS e da Nova solicitação (`tradicional_web`: `usinas_de`, `tipos_de`,
  `ativos_de`, `ativos_do_cliente` usam o índice por cliente e usina quando a lista é a do catálogo, e varrem como sempre
  qualquer outra).
- **O registro é só de leitura.** Cada ativo é o MESMO objeto para todo mundo: `Registro` (um `dict` de verdade para `get`,
  json e Jinja) levanta `TypeError` em qualquer escrita. A auditoria de todos os chamadores (31/10/2026) não achou nenhum que
  mexa num registro nem na lista; o guarda existe para o próximo que mexer não corromper o ativo de todas as pessoas, sem erro
  nenhum. Quem precisa mexer pede a cópia: `ativos_central.registro(codigo)` ou `dict(r)`. A auditoria: leitura de cada ponto
  de uso e uma rodada do grupo `-k "oscreator or chamados or engenharia or pcm_nota or prefixo"` com todo catálogo de dublê
  entregue como tupla de `Registro` (31/10/2026: 103 listas congeladas, nenhum `TypeError`).
- **O boot nunca pergunta ao Fracttal.** Em ordem: (1) a cópia em disco, `<pasta de dados do clone>/oscreator/ativos.json.gz`
  (gravada ao lado e trocada de uma vez; a gravação escreve o catálogo VIGENTE quando a trava do disco chega, e não o que a
  pediu, e só pula o que o disco já tem, a mesma versão, `lido_em` e `novos_em`: uma troca e os novos do dia terminando em
  ordem trocada não deixam a versão velha no disco, e o `acrescentar` sem novos, que põe no lugar outro objeto da mesma
  versão, não faz a gravação pendente ser pulada (revisão 2 da 2.2); o formato vai escrito dentro; a ilegível, cortada
  ou de outro formato é ignorada, e o motivo fica em `estado()["disco"]["erro"]`; a cópia, o `ativos_estado.json` e a leitura
  do arquivo antigo moram em `os_creator/ativos_disco.py` desde a revisão 1 da 2.2); (2) o `assets_cache.json` antigo, lido UMA vez como migração se a cópia nova
  não existe (já grava a nova); (3) a foto dos ativos no banco, `nexus_ativos_fracttal · foto_ativos`, pela função que a
  `ponte.py` entrega (`ativos_banco.leitor`; o catálogo não conhece a configuração do banco). Sem nenhuma, o catálogo nasce do
  primeiro download (RPC, com a sessão de quem pediu, como sempre). Quem chega com o boot em curso espera nele: o "feito" só vale
  depois (um teste de 8 pedidos juntos achou o erro, que mandaria o pedido dos primeiros décimos de segundo baixar os ~22 mil
  ativos do Fracttal).
- **A troca recusa** a lista vazia, a que encolhe mais de 5% (`ENCOLHE_MAX`) e, só da foto do banco e do disco (a data veio
  escrita), a leitura mais velha que o catálogo de agora com outro conteúdo (a foto do banco de ontem não vence o RPC de agora;
  a leitura rest ou rpc é feita agora e nunca é "velha": pelo relógio de parede, um download que terminou um segundo depois de
  outro perderia dele): o download do RPC por páginas perde 200 ativos em silêncio quando uma página vem sem lista. Recusada,
  fica o catálogo de antes e o motivo (com a hora) vai para `estado()["recusa"]`. A versão (o sha das linhas) sai ANTES de montar qualquer coisa: a mesma lista lida de novo (a renovação
  diária) só renova o `lido_em` (e regrava o disco se o dele ficou mais de 1 h para trás), e a recusada não monta nada. Só o
  que veio do Fracttal (rpc, rest) vai para o disco.
- **A recusa é lembrada** (revisão 1 da tarefa 2.1). A leitura completa que o catálogo recusou por ter encolhido foi uma ida de
  ~110 pedidos ao Fracttal: `ativos_central.conferido_em(cat)` é o mais novo entre o `lido_em` e essa leitura, e o
  `api.catalogo_vencido` decide por ele. Então duas aprovações da Fila seguidas, depois das 24 h, baixam UMA vez (antes, cada uma
  baixava os ~110 pedidos, minutos na frente de quem aprovava, e o download por trás repetia de 10 em 10 min); quem esperou a vez
  na trava usa a leitura de quem baixou, entrando ou não; o botão "Atualizar ativos" (`force`) dentro de
  `ASSETS_ESPERA_TENTATIVA` (10 min) depois de uma recusa devolve o catálogo de agora sem baixar; passadas as 24 h da recusa, tenta
  de novo. A lista vazia NÃO entra (não é leitura completa, custa 1 pedido). Desde a 2.2 a recusa sobrevive ao reinício
  (`ativos_estado.json`, ao lado da cópia em disco, com a última paridade do REST): o servidor reinicia ~10 vezes por dia, e
  só na memória cada deploy releria o Fracttal uma vez e a confirmação abaixo nunca chegaria. A falha do download (exceção:
  Fracttal fora, cota estourada) também é lembrada (`ativos_central.anotar_falha`): quem esperava a vez na trava não tenta de
  novo em fila, e o `force` e o `em_dia` dentro de `ASSETS_ESPERA_TENTATIVA` devolvem o catálogo de agora e os botões dizem por
  quê (`api.aviso_da_falha`, campo `falha`; a renovação por trás tem a janela dela). A sessão recusada de UMA pessoa
  (`SessionExpired`: 401/403, o login que caiu) não é falha do Fracttal e não segura o download de mais ninguém.
- **O encolhimento confirmado** (2.2): o Fracttal que perdeu ativos de verdade (uma usina que saiu da carteira) seria recusado
  para sempre. A troca que encolhe passa quando o MESMO conjunto de ativos sai do catálogo em duas leituras completas, de
  caminhos diferentes (REST e RPC) ou do mesmo com 20 h ou mais entre elas, sem leitura aceita no meio; o
  `estado()["encolhimento"]` diz. O conjunto é o que SAI, e não a lista inteira: os novos do dia entram no catálogo entre as
  duas leituras, e a lista inteira nunca seria a mesma.
- **Os botões levam o motivo:** `POST /os/api/ativos/atualizar` e `GET /os/api/tradicional/catalogo?recarregar=1` respondem com
  `recusa` (texto curto com a hora, ou "") e `falha`; o link `/os/solicitacao/atualizar`, que navega, volta à Fila só com o
  SINAL (`recusa=1`, `falha=1`), e a Fila mostra o texto do servidor (`api.aviso_da_recusa`, `api.aviso_da_falha`): nada escrito
  na URL vai à tela (revisão 1 da 2.2: qualquer link punha qualquer frase na faixa). As três telas o mostram (seção "Os botões
  Atualizar ativos sem esperar o Fracttal", abaixo).
- **Fresco ou vencido** é decidido por quem usa, por `conferido_em` (`api.catalogo_vencido`: 24 h; com o leitor do servidor
  pronto, 26 h, para a leitura da noite de ontem não vencer em cima da de hoje e um pedido nesse minuto não disparar o RPC junto
  com o REST): vencido, o catálogo serve e é renovado por trás pelo RPC, como em 24/10. O que veio da foto do banco está sempre
  vencido (é o socorro da máquina sem cópia: o código da foto é o canônico, e a 1ª leitura do Fracttal a troca). Com o leitor
  pronto (seção abaixo), `force=True` pede só os ativos novos, por trás, e volta na hora, e `em_dia=True` volta com o catálogo
  como está: a aprovação da Fila que NÃO acha o ativo da solicitação nele espera os novos (6 s no máximo) e procura de novo
  (`rotas_solic._ativo_para_aprovar`); a que acha não espera nada. Sem ele (o PC, os testes, o leitor fora da prontidão), os
  dois seguem como eram (RPC com a sessão da pessoa), e o que baixam entra no catálogo central. O "desatualizado" da tela inicial segue pelo `lido_em` (o dado é de
  ontem, mesmo conferido hoje).
- **Medido** (catálogo de 28/10, 26.620 ativos): 30 MB na memória com todos os índices (a lista decodificada sozinha eram 33 MB, e
  cada chamada copiava mais ~12 MB); subir pela cópia em disco 0,5 s (o arquivo tem 0,9 MB); montar uma versão 0,4 s; trocar pela
  MESMA lista (a renovação diária) 0,35 s e pico de 15 MB (eram 0,45 s e 44 MB: montava tudo para depois ver que era igual); achar
  um código 1,5 µs.
- **Na ponte:** `ponte.ligar_catalogo_de_ativos(app)`, ao criar o clone, diz onde mora a cópia e de onde ler a foto. Nos testes
  o disco não é tocado (a pasta é a do usuário da máquina): o catálogo vive só na memória, e o teste que quer o disco passa a
  pasta de teste (`ativos_central.reiniciar(pasta=...)`).

**A foto do banco como catálogo** (a conversão e o caminho pela cadeia de pais moram em `os_creator/ativos_foto.py` desde a
2.2). A da carga única não servia (o limite medido): ela foi carregada do `assets_cache.json` em 11/10/2026, e aquele arquivo
já tinha jogado fora a raiz de cada cliente (o item sem pai, que o `montar_registros` ignora): das 22.357 linhas, 15 pais não
estão na foto, e nenhuma linha chega à raiz pela cadeia de `pai_item_id`. O nome do cliente (o 1º trecho do
`parent_description`) só existe na raiz; tirá-lo do prefixo do nome da usina acerta 74% dos ativos (128 das 189 usinas com
equipamento) e erra 6 dos 16 clientes (a carteira com outro nome), e o Almoxarifado e o "TESTE - PA" (`CLIENTES_OCULTOS`)
deixariam de ser reconhecidos e apareceriam nas cascatas com nomes inventados. Por isso `registros_da_foto` recusa a foto em
que mais de 1% das linhas não chega à raiz pela cadeia de pais (`FotoIncompleta`; a de 22/09 não chega em nenhuma): a fonte
fica ligada, o motivo aparece em `estado()["banco"]`, e a foto renovada toda noite pelo leitor do servidor (2.2), com as raízes
e as colunas novas, passa a servir sozinha. Com a raiz, a cadeia monta o MESMO cliente, usina e tipo que o RPC
dá (o teste compara com registros de caminho conhecido; sobre o catálogo de 28/10 reconstruído com as raízes: cliente 100%,
usina 99,98%, tipo 100% e o caminho `parent_description` igual ao do RPC em 97,7% dos ativos). O nome de cada item no
caminho sai da descrição dele, que traz o endereço da usina atrás: na usina o corte é na sigla do estado (acertou as 189 com
equipamento), nos níveis de dentro tira-se a cauda de endereço da usina ou corta-se no 1º espaço duplo. Da foto renovada vêm o
`id_type_item` e o `id_group_task` (as colunas novas; a criação de OS usa os dois, e o `create_os_rpc` poria `id_type_item or 1`
sem eles); a linha marcada `fora_do_fracttal_desde` não entra; e, na foto de 11/10 (sem essas colunas), só a foto mais nova
entra (a de 21/06 que a carga levou junto tem códigos que o Fracttal já não tem).

**O leitor do servidor (tarefa 2.2, 31/10/2026; `os_creator/ativos_leitor.py`).** O catálogo deixa de depender da sessão da 1ª
pessoa do dia: o próprio servidor lê os ativos pela credencial da empresa (o REST `items`, o cliente e o ritmo de
`nexus/campo/fracttal.py`). Só o `servir.py` liga (`ativos_leitor.ligar`, pelo `ponte.modulo_do_clone`); o `app.py` (o PC) e os
testes seguem pelo RPC; sem a credencial REST (`FRACTTAL_CLIENT_ID`), não liga e o estado diz por quê.
- **No porteiro do Fracttal (31/10/2026, etapa 5):** o laço `nexus-ativos-leitor` (a noite e os novos das :08 e :38) se
  declara fundo no alvo da thread (`fracttal_conta.de_fundo`: no máximo 90 pedidos por minuto, e depois do clique); os
  novos que o botão pede (`nexus-ativos-novos`) seguem clique, porque quem clicou espera por eles. A leitura passa pelo
  `campo/fracttal.ler`, que tira a vez no porteiro antes de pegar uma das 4 `_VAGAS`. Regras em `nexus/casca/CLAUDE.md`,
  "Pedidos ao Fracttal: o contador e o porteiro".
- **De madrugada (02:15 de Brasília), o Fracttal inteiro** (`ler_completo`): ordenado pelo id (`items?sort=id:asc`: o
  deslocamento de cada página só é estável sobre uma ordem declarada), 100 itens por página, 1 pedido por segundo, até o `total`
  que a 1ª página informa (~270 pedidos, ~5 min). O 4xx na 1ª página (o motivo diz qual, revisão 2 da 2.2: o 400 e o 422 são
  a ordem recusada; o 401 e o 403, a credencial da empresa; o resto, o HTTP), a página curta antes do total, os itens
  distintos a menos ou nada: `LeituraIncompleta`, com o motivo, e nada muda (tudo segue pelo RPC). Só o erro de
  passagem se repete (`_transitorio`: o 406/429 que o cliente já esperou 5 s e 10 s, a conexão que caiu, o tempo esgotado e o
  5xx): o leitor espera o castigo de 1 min do Fracttal e pede a mesma página de novo, duas vezes; o 400, o 401, o 403 e o 404
  falham na hora. Só os campos do registro ficam (`CAMPOS_REST`).
- **Do REST ao registro** (`para_registro`): o formato cru do RPC. O `parent_description` é o do item, se o REST o der; senão,
  montado pela cadeia de `id_parent` (`ativos_foto.caminhos`, o mesmo da foto). O `id_group_task` é o do item; senão o do
  catálogo de antes pelo mesmo id (na 1ª noite, o do RPC); senão o da foto; senão vazio. O item cujo pai não se acha fica de
  fora do catálogo (a leitura seguinte o traz), e a foto o guarda: a foto leva o catálogo que entrou e, pela DIFERENÇA de ids, o
  que ele não tem (as raízes dos clientes, os sem pai, o caminho sem trecho como "// / "), sem repetir a regra do
  `montar_registros`. A `descricao` da foto vai SEM endereço, em toda linha (Rulings AK e AN), porque a API do banco tem
  leitura aberta e o endereço da usina já saiu dela uma vez, no mesmo dia em que entrou (04/10/2026): a linha lida hoje
  leva o nome do item no caminho (`ativos_foto.nomes_no_caminho`); a que não veio (o código que saiu do Fracttal) é
  recalculada pela própria descrição e pelo próprio pai (`ativos_foto.nome_pelo_pai`, sobre `_grafo_de_quem_saiu`: a cadeia
  dela no que se leu hoje e nas linhas antigas que também não vieram); e a foto passa toda descrição pelo detector de
  endereço (`nexus/dados/foto_ativos.sem_endereco`, regra e marcadores no `nexus/dados/CLAUDE.md`). O detector NÃO entra no
  caminho do catálogo: o cliente e a usina das telas e a paridade com o RPC não mudam. Quantas ele cortou na última foto
  (o número, até 5 ids e a hora, nunca o texto) fica no `ativos_central` (`anotar_descricao_cortada`, e no `estado()`) e
  no `ativos_estado.json`, para sobreviver ao deploy (item 0 da 3.1+3.2), e vai a uma linha de log no fim da
  noite ("a foto da noite: N linhas, N mudaram, N entraram, N saíram, N descrições cortadas (ids ...)"). **Onde se vê** (o
  Levi não tem acesso ao servidor, e a 1ª noite só se confere pela tela): Raio-X (Base → Raio-X, só administrador) → a seção
  "Uso do OS Creator" → o bloco **"Ativos centrais"** (`nexus/casca/raio_x.py`, `_secao_canto_central`): o catálogo (fonte,
  lido em, versão), se o leitor está pronto, a paridade (quando, as coberturas `cob_ref`/`cob_rest`, se valeu), o REST (a
  última leitura boa e a última falha), **a última noite** (a hora, quanto levou, se o catálogo aceitou, os pedidos, as
  contagens e a foto do banco: gravou, linhas, mudaram, entraram, saíram, o erro; guardada no `ativos_estado.json` por
  `ativos_central.anotar_noite`, para sobreviver ao reinício), a troca recusada, as descrições cortadas (o número e os ids) e a
  cópia em disco. A usina cujo nome
  fechou no padrão "Cliente - Usina -
  UF" NÃO passa pelo detector (Ruling AQ, revisão 3): o leitor diz quais (`nomes_no_caminho(..., usinas_no_padrao=)` e o
  `nome_pelo_pai` da linha que saiu), e a foto só as isenta se o nome termina na sigla do estado. Sem isso, a usina de
  fazenda ("CL - UFV Fazenda X - MT", comum na carteira) virava "CL - UFV", e a foto servindo de catálogo (a máquina sem
  cópia nenhuma, `registros_da_foto`) juntava duas usinas de fazenda numa só na cascata. A usina FORA do padrão segue pelo
  detector, e nessa foto ela aparece sem o endereço até a 1ª leitura do Fracttal.
- **A conferência** (`conferir_paridade`, contra o catálogo de agora: na 1ª noite o do RPC, a sondagem REST x RPC de verdade;
  depois, a leitura anterior): >= 99% dos códigos em comum com o mesmo cliente e usina, os campos obrigatórios (`id`,
  `id_parent`, `id_type_item`) em >= 99% dos ativos e >= 95% dos códigos da leitura no catálogo. Na 1ª conferência (o REST
  ainda não valeu, ou a última que valeu passou de 30 h), >= 99% nos DOIS sentidos, e o motivo diz até 5 códigos dos que
  faltam de cada lado (revisão 1 da 2.2: com 95%, até 5% dos códigos do RPC podiam faltar no REST, saíam do catálogo e a foto os
  marcava "fora do Fracttal" sem estarem). O resultado vai a `estado()["paridade_rest"]` e ao `ativos_estado.json`, dizendo
  contra qual fonte e de quando, com as coberturas de toda noite (`cob_ref`: % dos códigos do catálogo na leitura; `cob_rest`:
  % dos da leitura no catálogo).
  **Falhou:** nada troca, nada se acrescenta pelo REST, e o catálogo vence nas 24 h de sempre: a 1ª sessão do dia o renova
  pelo RPC, por trás, uma vez para todos (o renovador de antes). **Valeu:** `ativos_central.trocar(..., "rest", lido_em=` o
  fim da leitura `)`, que ainda recusa a que encolhe; aceita, a foto do banco é renovada (`nexus/dados/foto_ativos.py`: só
  quando o sha das linhas muda; o código que saiu do Fracttal fica marcado). Uma guarda só para os dois.
- **De dia, só os novos** (às :08 e :38 das 06h às 22h, `ler_novos`, só com a paridade valendo e de no máximo 30 h):
  `items?sort=id:desc`, do maior id para o menor, até a 1ª página INTEIRA de ids que o catálogo já tem (1 pedido sem novidade,
  2 com). A página fora de ordem (o `sort` ignorado) não acrescenta nada e é falha do REST; mais de 400 novos ficam para a noite
  (não é falha: o REST respondeu); o novo cujo pai não está no catálogo nem nos novos também. O caminho dos novos sai do catálogo, e a raiz do cliente do próprio catálogo (o item-usina, com um
  trecho só no caminho, é filho dela). Eles entram por `ativos_central.acrescentar`, sem mexer no `lido_em` da lista inteira
  (o catálogo vence pelas 24 h dela, e a confirmação do encolhimento segue valendo); anda o `novos_em`, e a tela diz "ativos
  de HH:MM" pelo mais novo dos dois (`visto_em`).
- **Quem pede os novos:** `pedir_novos` (por trás; a leitura de menos de 1 min serve, e dez cliques são um pedido) e
  `esperar_novos` (a tela que volta com `?novos=1` e a aprovação que não achou o ativo; teto de 6 s), que devolve o DESFECHO
  da leitura: `terminou` (dentro da espera), `acrescentados`, `sem_pai`, `muitos`, `muitos_mais` (a leitura parou no teto com
  a última página toda de novos: havia mais do que ela viu) e `erro`. O desfecho de leitura que terminou há mais de 2 min
  (`DESFECHO_VALE_S`, o dobro do frescor) não é o de agora: None, e a tela não diz nada dos novos (revisão 2 da 2.2: o F5 da
  Fila com `?novos=1` repetia o de uma leitura antiga). Uma leitura do Fracttal por vez: os novos pulam enquanto a noite
  corre.
- **A prontidão expira** (`ativos_central.leitor_pronto`, revisão 1 da 2.2): o leitor só está pronto (os botões pedem os novos
  a ele) com a conferência da leitura REST que VALEU há no máximo 30 h (`paridade_recente`) e nenhuma leitura REST falhando
  depois da última boa (`anotar_leitura_rest`: a dos novos ou a da noite; a exceção do cliente, a leitura incompleta e a página
  fora de ordem são falha; os novos demais, não). A prontidão que nunca expirava deixava os botões no REST com toda leitura
  falhando, sem o socorro do RPC, e a Fila sem o ativo de hoje por um dia. Fora dela, `force` e `em_dia` voltam ao caminho do
  PC (o RPC com a sessão da pessoa); a leitura boa seguinte a devolve; a última boa e a última falha vão ao
  `ativos_estado.json` (o reinício não esquece) e ao `estado()["rest"]`.
- **Medido** (27 mil itens sintéticos com a forma da árvore do Fracttal: 16 clientes, 190 usinas, cabines e inversores):
  `para_registro` + `montar_registros` 0,25 a 0,3 s; a noite inteira sem a rede (a leitura, a foto de 27 mil linhas do banco
  devolvida como texto, a conferência, a troca e a foto sem mudança) 7 a 9 s e pico de ~53 MB a mais (eram 72 MB antes de cada passo largar o
  que já serviu e de a foto do banco virar listas logo depois de lida; o maior pedaço é o `montar_registros`, com a lista crua
  e os registros juntos; o nome sem endereço de cada item, da revisão 1, vem depois dele e não sobe o pico); os novos (30, pelo
  catálogo de 27 mil) 0,1 s mais 0,4 s para somar. A noite em que a foto MUDA (a 1ª renovação, que troca todas as linhas de
  11/10) grava as 27 mil linhas pelo `livros.publicar`, e o xlsx dele pesa mais que tudo isso: olhar o Raio-X nessa noite.
  Pedidos: a noite, 1 por página de 100 (~270); os novos, 1 ou 2.
- **Os campos do REST que o leitor supõe** (a sondagem do `items` não pôde ser feita antes de construir): `id`, `code`,
  `description`, `id_parent`, `id_type_item`, `id_group_task` e, se vier, `parent_description` (os nomes do RPC
  `inventories.items_list`, que o `get_assets` usa), e o envelope `{"data", "total"}` (o do `fonte_bd_api` do PCM, com o
  `total` às vezes em texto). O que faltar aparece na conferência da 1ª noite, que então falha e diz o campo.

**Prova:** `tests/test_oscreator_ativos_central.py` (47 testes: nenhuma ida ao Fracttal nas telas, nem depois do reinício;
o boot em ordem, a cópia ilegível, o boot concorrente (8 pedidos juntos, com o leitor lento); o registro só de leitura e a
cópia; a busca por índice, sem varrer; a troca recusada, a mesma lista sem montar nada e a leitura mais velha; a recusa lembrada
(duas aprovações e cinco pedidos juntos baixam uma vez, o botão na janela não baixa e leva o motivo, passadas as 24 h tenta de
novo); a conta de códigos igual nas duas telas; a foto do banco contra o caminho do RPC; a ponte), os testes de catálogo de
19/10 e 24/10 sobre o novo dono e `tests/test_oscreator_ativos_leitor.py` (a 2.2: a leitura inteira para no total, com 1 s entre
os pedidos; a incompleta não troca; a recusa espera e tenta; os novos param na página conhecida, a fora de ordem não entra, o
sem pai fica para a noite e os novos voltam do disco; o caminho pelos pais igual ao do RPC e o grupo que cai no catálogo e na
foto; a paridade que passa e a que falha, que deixa o catálogo pelo RPC, uma vez; a foto que guarda o código que saiu, só
grava quando muda, não grava sobre a leitura curta e só depois que o catálogo aceitou; o encolhimento confirmado, que
sobrevive ao reinício; a falha do download que vale para quem esperava; só o servidor liga, e sem a credencial não liga) e
`tests/test_oscreator_ativos_prontidao.py` (a revisão 1: a prontidão que expira pela idade e pela falha e volta com a leitura
boa, também depois do reinício; a noite que falha derruba; a 1ª conferência com 99% nos dois sentidos e os códigos que faltam;
só o erro de passagem se repete; a noite ordenada pelo id e o `sort` recusado; a foto pela diferença de ids e sem o endereço
da usina; o núcleo concorrente dos novos com as funções de verdade; o disco com a versão vigente; as 26 h com o leitor; e a
revisão 2: o 4xx da 1ª página que diz o que houve e a gravação pendente que escreve o vigente) e
`tests/test_oscreator_ativos_descricao_no_banco.py` (a revisão 2, Ruling AN: a linha que saiu perde o endereço, a partir de
uma foto de 11/10 com endereço, e a 2ª noite não muda nada; a linha já marcada também; o detector na usina fora do padrão,
no nível de dentro e no endereço próprio, e os marcadores um a um; o caminho do catálogo que não passa por ele; a contagem
sem o texto; e a revisão 3, Ruling AQ: a usina de fazenda que fechou no padrão sem passar pelo detector, também a que
saiu, e a foto servindo de catálogo com as usinas de fazenda separadas).

## Os botões "Atualizar ativos" sem esperar o Fracttal (31/10/2026, tarefa 2.3 do canto central)

Os três botões (OS Creator -> Ativos, o ↻ do Criar OS e o "Recarregar o catálogo de ativos" da ficha da Fila do PCM) baixavam o
catálogo inteiro pelo RPC NA FRENTE de quem clicou: ~110 pedidos, minutos, e a página parada. Agora, com o leitor do servidor
pronto (seção acima: ligado pelo `servir.py` e com a leitura REST da noite conferida), eles pedem só os ativos NOVOS
(`api.load_assets_cached(force=True)` -> `ativos_central.pedir_novos`, por trás) e respondem na hora.
- **O que a tela recebe:** `ativos_de` ("ativos de HH:MM", Brasília, `api.ativos_de`: a última vez que a lista foi comparada
  com o Fracttal, a lista inteira de madrugada ou os novos do dia, o mais novo dos dois, Ruling AL; de outro dia, "ativos de
  dd/mm HH:MM", porque à 01:00 "de 02:20" seria lido como a de hoje), com as duas horas no `title` (`api.ativos_de_titulo`:
  "lista completa de dd/mm HH:MM; novos até HH:MM"; sem novos, só a primeira), `novos` (True quando o leitor foi chamado),
  `recusa` e `falha`.
- **E a lista seguinte já vem com os novos:** a tela que acabou de apertar o botão pede a lista com `?novos=1`
  (`/os/api/ativos/catalogo?novos=1`, `/os/api/tradicional/catalogo?novos=1`, e o link volta à Fila com `novos=1`), e essa
  rota espera a leitura em curso até 6 s (`api.esperar_os_novos`; estourou, segue com o que há) e devolve o desfecho dela
  (`novos_desfecho`, com o `texto` de `api.texto_dos_novos`). Quem espera é o pedido seguinte, não o botão. A tela diz, nesta
  ordem: não terminou ("a busca no Fracttal ainda não terminou: os ativos novos aparecem em instantes"); falhou ("não consegui
  buscar os ativos novos no Fracttal: o motivo"); deixou ativos para a noite ("N ativos novos ficam para a leitura da noite";
  "mais de N" quando a leitura parou no teto e havia mais); terminou bem sem nada ("nenhum ativo novo no Fracttal", e só
  então); terminou bem com N (na tela de Ativos, a conta da lista). Revisão 1 da 2.2: a frase "nenhum ativo novo" saía de
  qualquer conta igual, também quando a busca estourava ou falhava. Revisão 2: o desfecho de mais de 2 min não aparece.
- **Onde aparece:** na tela de Ativos, a linha de cima ("N ativos · M usinas · ativos de HH:MM"; o rodapé diz o desfecho, a
  recusa e a falha; abaixo de 480 px a busca desce para a linha de baixo, inteira: a 375 px a linha espremia o subtítulo em 4
  linhas e a busca cortava em "códi"); no Criar OS, ao lado do ↻ (a hora, o desfecho e, se houver, a recusa e a falha); na
  Fila, no aviso do ativo que não se acha ("busca no Fracttal os ativos novos, em segundos; ativos de HH:MM") e, na volta do
  link, em faixas de alerta no alto (o desfecho, a recusa e a falha, com o texto do servidor).
- **Sem o leitor pronto** (o PC, `app.py`; a paridade que falhou, envelheceu ou ainda não houve; o REST falhando): os botões
  seguem pelo RPC com a sessão de
  quem clicou, como antes, para dentro do catálogo central; a tela diz "leva alguns minutos" e mostra a mesma hora. A
  renovação por trás do catálogo vencido é sempre pelo RPC (`_renovar_catalogo_por_tras` marca o contexto dela, `_POR_TRAS`,
  e o `load_assets_cached(True)` dela não chama o leitor).
- O erro do ↻ do Criar OS diz em palavras ("Não consegui recarregar os ativos: ..."), sem o sinal de alerta.
- **Prova:** `tests/test_oscreator_ativos_botao.py` (os três botões voltam antes de a leitura dos novos acabar, sem o RPC, e
  a lista com `?novos=1` já traz o ativo novo; "ativos de HH:MM", com a data quando é de outro dia, nas respostas e nas
  páginas; sem o leitor, ou com a paridade que falhou, o RPC com a sessão da pessoa; e a revisão 1: o desfecho dos novos
  (terminou bem sem nada e com N, sem o pai, não terminou e falhou) com o leitor de verdade, a Fila com o desfecho, a falha
  lembrada nos botões e a sessão de uma pessoa que não é falha de todos, a Fila que não ecoa a URL, a aprovação que só espera
  sem o ativo, o `title` com as duas horas e o cabeçalho a 375 px; e a revisão 2: o desfecho de mais de 2 min que não
  aparece e o "mais de N" só quando a leitura parou no teto).

## A lista central de OS e o leitor em faixas (31/10/2026, tarefas 3.1 e 3.2 do canto central)

Levi, 30/10/2026: "o histórico de OS pega só os mais recentes, atualizando os mais antigos 1 vez por dia pela noite" (desenho:
`docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`, "Etapa 3"). Até a 3.3 cada visão do Histórico era uma
lista no `historico_store` (a de "Todos" por quem vê o mesmo; "criadas por mim" e "atribuídas a mim" por pessoa), o Garantias
tinha a dele (365 dias), a marcação verde dos Ativos relia 30 dias e o nº da OS virava id com 1 a 5 pedidos. A 3.1 e a 3.2
construíram a lista UMA, de todas as OS, e quem a enche; as telas leem dela desde a 3.3 (a seção seguinte).

**A lista (`os_creator/os_central.py`; o registro e quem o monta em `os_registro.py`, a cópia em disco em `os_disco.py`).**
- **O que guarda (decisão AC):** as OS CRIADAS nos últimos 365 dias (`JANELA_DIAS`: o Garantias lê 365 e o REST não filtra pela
  etiqueta) mais toda OS aberta (status 1 e 2) de qualquer idade. Um registro por OS (`RegistroOS`, uma tupla com nome, só
  leitura, a mesma para todas as telas; `linha()` dá o dicionário novo, no formato do `api.list_minhas_os`, com o cliente, a
  usina e o tipo tirados do catálogo de ativos na hora). Os índices por id, por nº (`por_folio`) e por código de ativo
  (`por_codigo_ativo`), a ordem pela criação, e a janela lida inteira (`janela`, decisão AC: a tela que pede um período fora
  dela vai ao vivo, `Lista.cobre`; o 1º dia dela é a data LOCAL menos 365 dias, a das telas, desde a rodada 2 da 3.3). A
  marca d'água (`marca`, rodada 2 da 3.3): a criação da OS mais nova de uma leitura até o topo; toda OS criada antes dela está
  na lista, e é até ela que as telas conferem. Troca-se a versão inteira; a ação refaz só os pedaços da OS dela nos índices
  (`_aplicar`, o mesmo resultado da montagem inteira, um teste confere).
- **Os campos e de onde vêm.** Das linhas do REST `work_orders` (uma por TAREFA, juntadas pelo `id_work_order`, a tarefa
  repetida uma vez só): `wo_folio` (nº), `description` (a descrição, as das tarefas juntas e cortadas em 90, como o
  `_shape_wo_row`), `items_log_description` (o ativo, cortado em 60, e os códigos entre chaves; sem chaves, o `code`),
  `created_by` e `code_create_by` (quem criou e o código da pessoa no Fracttal), `user_assigned`/`personnel_description` e
  `id_personnel` (o responsável), `labels` (as etiquetas, id e nome), `creation_date`, `date_maintenance` (programada, a mais
  cedo), `event_date` (a mais cedo; sem ela, a programada), `initial_date` (o início, o mais cedo), `wo_final_date` (senão a
  data fim mais nova das tarefas), `tasks_log_task_type_main` (o tipo, "A / B" como o meta das tarefas),
  `id_status_work_order`, e `task_note`/`note` só no texto que traz o bloco do chamado (o Garantias lê a OS de acompanhamento
  por ele; o texto sem o bloco não fica na memória, nem ao lado de um com o bloco: assim o `api.parse_bloco_chamado` não lê
  linha de outra nota como campo). Os outros campos que o Nexus já lê do REST servem à montagem e não ficam
  (`id_work_order`, `id_work_orders_tasks`, `code`) ou não são mostrados pela lista (`parent_description`: o cliente e a usina
  saem do catálogo pelo código; `id_parent_wo`, `tasks_duration` e `id_task`: o card lê ao vivo). **O que a tela usa e o REST
  não traz** (fica vazio na lista; o card lê ao vivo):
  o gatilho (`trigger_description`: nenhum leitor do REST no Nexus o lê hoje, e não se sabe se o `work_orders` o traz; se
  vier, entra), o id da CONTA de
  quem criou (o `id_created_by` do RPC: a lista guarda o código da pessoa, e "criadas por mim" casa por ele), a nota das OS
  sem o bloco do chamado, as subtarefas, os anexos, a OS pai e a solicitação. A 1ª noite no servidor diz quanto de cada campo
  o REST trouxe (o estado da lista, "Campos que o REST trouxe" no Raio-X): é a sondagem que não pôde ser feita antes de
  construir (o auto-mode desta máquina não lê o Fracttal com a credencial).
- **A faixa que sai.** Cada leitura diz o que cobre (`receber(linhas, faixa)`): a OS que a lista tinha dentro da faixa e que não
  veio nela mudou (de status, ou sumiu) e fica **"a conferir"** (`Lista.a_conferir`: a tela diz e o card lê ao vivo; o filtro
  por status não a conta, porque o status dela é velho) até uma faixa trazê-la de novo; a noite tira de vez o que não voltou.
  As novas só somam (as conhecidas da página que encerra podem vir pela metade); os 7 dias e a noite trocam as criadas desde o
  piso (a linha mais velha que ele, da página da borda, não entra); as abertas trocam as que vieram e marcam a aberta que não
  veio; as finalizadas só anotam o status e a data fim nas OS que a lista já tem (a leitura é pela data de fim de cada TAREFA).
  E a leitura só julga o que existia quando ELA começou (a noite inteira leva minutos, e a ação e a entrega das abertas não
  esperam por ela): a OS que a ação mexeu depois do começo não volta ao status velho que a leitura leu, e a criada depois do
  começo (com 2 min de folga para o relógio do Fracttal) não sai nem fica "a conferir" por não ter vindo.
- **A trava de encolhimento** (Ruling AU, rodada 1 da revisão; o `ENCOLHE_MAX` dos ativos): a noite que tiraria, ou os 7 dias
  que marcariam "a conferir", mais que 5% das OS que a leitura cobre e mais que 10 OS, não trocam NADA (páginas perdidas em
  silêncio, o REST que devolve só uma parte). O motivo vai a `estado()["recusas"]`, ao log, à faixa do leitor (o erro dela) e
  ao Raio-X ("Trava de encolhimento"), até a faixa passar de novo. Os 5% são os dos ativos; o mínimo de 10 é porque os 7 dias
  cobrem ~700 OS na escala do AC, e na lista pequena 5% seriam uma ou duas OS apagadas de verdade. **A saída** (rodada 2, a
  dupla confirmação dos ativos, `ativos_central._confirma`): a recusa que se repete IGUAL na leitura seguinte da mesma faixa (os
  mesmos ids saindo, ou ao menos 90% deles: a interseção sobre a união das duas) é o apagamento de verdade e passa, e o estado
  guarda "aceita na 2ª leitura" (`estado()["confirmadas"]`, também no Raio-X). Uma leitura só que encolhe pode ser página
  perdida; duas iguais seguidas são o Fracttal de verdade. Sem a saída, o apagamento de verdade acima de 5% seria recusado
  toda noite, para sempre; a 2ª leitura diferente é recusada de novo e vira a recusa que a 3ª confere. A recusa (com os ids,
  que só a lista lê) e a confirmação vão ao cabeçalho da cópia em disco: o servidor reinicia a cada push na `main` e a noite
  roda uma vez por dia, e só na memória a recusa sumiria entre duas noites de dia útil. A 1ª carga (a lista vazia) não tem o
  que encolher.
- **A ação entra na hora** (`atualizar_os(id, registro=None)`): com o registro (as linhas do REST, a linha do Histórico ou a
  linha crua do RPC), na hora; sem ele, dentro de um pedido do OS Creator, lê a OS pela sessão da pessoa com o que o card já lê
  (as tarefas, `_leitura_da_os`, e o cabeçalho: 1 a 3 pedidos); fora de um pedido, ou com o Fracttal recusando, a OS fica "a
  conferir" e pendente, e o leitor a relê pelo nº na próxima faixa (a que o nº não traz mais, apagada no Fracttal, sai da
  fila e segue "a conferir" até a noite a tirar; a que derruba a leitura sai depois de 5 falhas). As ações do OS Creator a
  chamam desde a 3.3 (criar, clonar, aprovar, cancelar, finalizar, responsável, etiquetas, nota, fazer a tarefa:
  `lista_central.mudou` e `criadas`, só com a lista em uso); a 5.1 faz o caminho único de criar OS.
- **As visões viram filtros** (`filtrar(visao, pessoa, de, ate, etiqueta=, status=)`, `contar(...)`; a conferência da 3.3
  conta pelo índice da criação, `contar_criadas`): "todos"; "atribuidas" pelo `id_personnel`; "criadas" pelo
  id da conta quando os dois lados o têm, senão pelo código da pessoa, senão pelo nome sem homônimo. None quando a lista não
  responde e a tela vai ao vivo: o período fora da janela, a pessoa sem o que a identifique, o nome com dois códigos, o nome
  que não casou com nada. `folio_para_id(nº)` sem pedido nenhum.
- **O disco (decisão AH):** `<pasta de dados do clone>/oscreator/os_central.json.gz`, uma linha JSON por OS entre o cabeçalho e
  o fecho (a escrita e a leitura em fluxo, nunca o arquivo inteiro na memória), trocado de uma vez (`canto_disco.py`, a mesma
  troca da cópia dos ativos; no Windows, o arquivo que o antivírus segura por um instante é tentado de novo antes de desistir,
  `ESPERAS_DA_TROCA`, rodada 1 da revisão), no máximo uma escrita a cada 30 s (as ações seguidas viram uma; a última chega em
  até 30 s; a fila das pendentes, a recusa da trava e a confirmação, que mudam sem a versão mudar, também regravam a cópia:
  a pendente que saiu não volta, e a recusa sobrevive ao reinício). O
  boot só lê o disco; a cópia ilegível, cortada ou de outro formato é ignorada, e a lista começa vazia (as telas vão ao vivo).
  `ponte.ligar_lista_de_os` diz a pasta (nas duas máquinas; nos testes, não). É cache do Fracttal, com texto de OS e nomes:
  nunca vai ao banco nem ao git.
- **Medido** (36 mil OS sintéticas com a forma real: ~150 pessoas, 190 usinas com 130 ativos cada, os tipos, as etiquetas, 2,3
  tarefas por OS, descrições de 60 a 200 caracteres; `tracemalloc`): **23,9 MB na memória (695 bytes por OS)**, 26,8 MB depois
  de subir pelo disco, dentro do orçamento de 30 MB (a 1ª versão, com as datas em texto e uma tabela de textos para tudo, deu
  49,5 MB: as cinco datas de cada OS foram para 20 bytes e a tabela guardada ficou só com os textos de pouca variedade). O
  `receber` da noite inteira (81 mil tarefas) 1,5 s; os 7 dias (683 OS, todas mudadas) 0,08 s; as abertas (7.534 OS) 0,3 s; a
  ação (`atualizar_os`) 25 ms; montar os índices das 36 mil 0,2 s; `filtrar` 30 dias 2 ms; a cópia em disco 2,6 MB (76 bytes por
  OS), gravada em 0,4 s e lida no boot em 0,5 s.
- **O pico da noite** (Ruling AV, rodada 1 da revisão; medido com 36 mil OS sintéticas, ~99 por dia, 2,3 tarefas por OS, e a
  linha do REST na LARGURA REAL: 67 campos, os que a lista lê e os que ela joga fora, custos, grupos, a nota da tarefa, datas e
  ids; 2.371 bytes em JSON e ~4,3 KB na memória cada; `tracemalloc` na leitura inteira, a junção e o `receber`): a noite de 365
  dias (a 1ª carga e o domingo, 83 mil tarefas) juntava as linhas inteiras antes do `receber`, **387 MB** de pico; com cada
  página cortada ao chegar no que a lista lê (`os_registro.enxuta`, o `projetar` do `tarefas_os._paginas`: 18,5 campos, sem os
  vazios e com os textos de pouca variedade num objeto só, ~1,3 KB), **152 MB**. A noite de 90 dias (a de todo dia, com a
  lista cheia), de 98 para **39 MB**. O que sobra é a leitura cortada guardada até o fim (a faixa só julga com ela inteira).

**O leitor em faixas (`os_creator/os_leitor.py`, só o `servir.py` liga).** Pela credencial da empresa, 1 pedido por segundo, pelas
MESMAS funções e pela mesma paginação do `nexus/campo/tarefas_os.py` (`ler_criadas`, `ler_abertas`, `ler_finalizadas`, `ler_os`;
não nasceu outro leitor de OS). Os minutos fixos moram na lista dos minutos ocupados do Nexus (`nexus/casca/minutos_ocupados.py`,
as constantes `OS_*`, como as `ATIVOS_*` dos ativos; um teste cruza a lista com o `MINUTO_DA_HORA` de cada laço de verdade).
Cada página chega cortada no que a lista lê (`os_registro.enxuta`), e as abertas entregues pelo `tarefas_os` também.
- **As novas:** da criação mais nova para trás até a 1ª página inteira de OS conhecidas, sem o pedido do total (1 pedido sem
  novidade, 2 com), a cada 3 min das 06:00 às 20:00 de segunda a sexta e a cada 15 fora disso, em qualquer minuto. Mais de 4
  páginas de novas: nada entra, ficam para os 7 dias. A lista sem uma leitura até o topo espera os 7 dias ou a noite.
- **Os 7 dias:** relidos inteiros (até uma página INTEIRA mais velha que o piso; sem o pedido do total no começo, que no
  `work_orders` sem filtro é o de todas as OS) a cada 10 min das 06:00 às 20:00, nos minutos :00, :21, :30, :41 e :51 (o :10, o
  :20, o :40 e o :50 têm dono).
- **As abertas:** entregues pela volta de hora em hora do `tarefas_os` (`ligar_entrega_das_abertas`; o fato e os pedidos dela
  não mudam). Ela só lê na máquina que vai gravar: sem entrega em 70 min, o leitor as lê pela mesma função, no máximo uma vez
  por hora, no :55.
- **As finalizadas:** status 3 pela data de fim, desde a mais nova que a lista conhece (nunca depois de agora: a data fim no
  futuro, dado ruim, travaria a faixa até passar) menos 2 dias, parando numa página INTEIRA além do piso, no :46 de toda hora
  (o :45 é do `uso_os` às 04:45; o desenho do PCM de 27/10; o `fato_tarefa_finalizada` não é publicado aqui).
- **A noite (03:21; o 03:20 do desenho é minuto das tarefas):** os últimos 90 dias inteiros, sem o pedido do total no começo;
  no domingo, ou sem a janela lida inteira (a 1ª carga, a cópia de janela menor), a janela toda. As antigas mudam sem data de
  alteração: é ela que as põe em dia.
- **A leitura que acaba ANTES do piso pede o total no fim** (rodada 2; `tarefas_os._paginas(total_no_fim=True)`, que os 7 dias
  e a noite passam): a página curta ou vazia antes do piso confere o total do REST ("vieram X de N") e, faltando mais que a
  folga de 1%, a faixa falha e nada muda. Sem isso, um REST que devolve a página vazia com `success: true` (o Fracttal já
  devolveu 0 registros calado: a rodada do robô do PCM de 26/10, no `nexus/dados/CLAUDE.md`) ou que tem um teto no `start`
  passava calado, e na 1ª carga, com a lista vazia (a trava não tem o que encolher), o pedaço lido seria instalado como os
  365 dias lidos inteiros. A página vazia é o fim, não "a página toda velha". Em produção a leitura acaba no piso: zero
  pedido a mais (a conta de pedidos abaixo não mudou).
- **A ordem do REST é conferida** (Ruling AU, rodada 1 da revisão; `tarefas_os.ler_criadas`, como o `ForaDeOrdem` dos ativos):
  com o `sort=creation_date:desc` ignorado (sem filtro de status ninguém o conferiu) ou mal aplicado, "a página conhecida" e "a
  página toda velha" não querem dizer nada: em ordem crescente a noite tiraria de vez as OS dos 90 dias, os 7 dias marcariam a
  semana "a conferir" e as novas levariam o fim da janela até agora sem as OS novas. As três faixas pela criação levantam
  `ForaDeOrdem` e não trocam nada quando a 1ª página não chega à criação mais nova que a lista conhece menos 3 dias (a lista
  vazia: o próprio começo menos 3 dias; o Fracttal da empresa cria ~99 OS por dia; o `topo_minimo` é obrigatório com o piso
  ou a página conhecida, rodada 2: sem ele a regra sumia calada) ou quando mais linhas que o maior dos dois, 5 ou 1% das
  lidas, vêm criadas mais de 1 h depois da linha anterior (a ordem qualquer inverte metade delas). A folga de 1 h e a conta
  deixam passar a linha fora do lugar que o REST pode trazer (o `sort` é da OS e a linha é da tarefa; a ordem das finalizadas
  já se mostrou só aproximada, `nexus/campo/coletor.py`): duas linhas dias fora do lugar passam, um teste prova.
- **As pendentes:** a OS que a ação deixou para a próxima faixa, pelo nº (até 5 por vez, as de menos falhas primeiro), depois
  das novas e dos 7 dias, cada pedido depois da pausa de 1 s (o 1º também: nunca 2 pedidos colados). A que o nº não traz mais
  (apagada no Fracttal) sai da fila e do disco e segue "a conferir" até a noite; a leitura que falha conta uma falha para
  aquela OS e encerra a volta (a rede caída não vira cinco esperas seguidas), e na 5ª ela sai da fila (segue "a conferir": a
  próxima faixa que a cobre a traz). Assim as pendentes mortas não travam a fila.
- **Leitura que falha no meio não chama o `receber`** (a `LeituraIncompleta` do `tarefas_os`, a fora de ordem, a recusa três
  vezes, a conexão que cai), e a leitura que a trava de encolhimento recusa não troca nada: a lista fica como estava, e o
  estado diz a faixa e o motivo. Qualquer outra exceção é **defeito do leitor**: vai ao log com a pilha, e a faixa diz
  `defeito` (o Raio-X escreve "DEFEITO do leitor"). Cada faixa conta no contador do Fracttal com o nome dela
  (`fundo:nexus-os-leitor:<faixa>`).
- **Pedidos** (medidos pelas funções de verdade, num Fracttal de mentira na escala do AC: ~99 OS criadas por dia, 36 mil por
  ano, 2,1 a 2,3 tarefas por OS, ~4.600 abertas; rodada 1 da revisão, a 1ª medida foi com 67 por dia): as novas 1 ou 2; os 7
  dias ~15; as finalizadas 1 a 3 por hora; a noite de 90 dias ~190 a 210, a da janela inteira ~750 a 830; as abertas, 0
  (entregues), ou ~98 quando o leitor as lê. **Por hora** (os compromissos contados pelo `proximo_passo`): em dia útil das 06h
  às 20h, ~92 a 110 (16 vezes as novas, 5 vezes os 7 dias, as finalizadas); no fim de semana das 06h às 20h, ~78 a 82 (as
  novas de 15 em 15 min, 2 delas fora dos minutos dos 7 dias); das 20h às 06h, ~5 a 11 (às 03h, mais a noite); e ~98 a mais na
  hora em que as abertas não chegam do `tarefas_os`. Num dia útil, ~1.500 a 1.850. **O pico por minuto** é 60 (1 por segundo) nas
  leituras longas, a noite (03:21; ~3 min, no domingo 19 a 29: ~830 páginas a ~1,35 s, a medida do ensaio de 18/10/2026 do
  `tarefas_os`) e as abertas lidas aqui (:55), como a volta do próprio `tarefas_os`;
  de dia, a dos 7 dias faz ~15 em ~15 s. A cota é de 200 por minuto para a empresa toda.
- **Onde se vê** (o Levi não tem acesso ao servidor): Raio-X → seção "Uso do OS Creator" → o bloco do canto central, peça
  **"Lista central de OS"**: quantas OS e quantas abertas, a janela lida inteira, a última entrega de cada faixa (e quem entregou
  as abertas), as falhas (e o defeito), a leitura que a trava de encolhimento recusou, os campos que o REST trouxe, as
  conferências das telas (3.3), o disco e a memória (medida uma vez por versão; a falha da medida vai ao log)
  (`raio_x._linhas_da_lista_de_os`). **Depois de um reinício** (revisão final): a última leitura de cada faixa, ok ou falha
  (a hora, os pedidos, o resultado e o erro; `os_central.anotar_leitura`, no cabeçalho da cópia em disco, em `leituras`)
  volta do disco: a noite que falhou deixa de sumir com o deploy. A leitura da noite e a que muda de situação (a 1ª falha de uma
  faixa, a 1ª boa depois de uma falha) regravam o cabeçalho; as de rotina (as novas) e a falha que se repete vão junto da
  próxima gravação. **O leitor que não ligou**: o `servir.py`
  liga cada leitor num try (`ponte.ligar_leitor_do_clone`); o clone que quebrou ao importar deixa o Nexus no ar, sem o leitor, e a
  peça diz "NÃO LIGOU, o clone quebrou ao subir" com o erro (o portão do deploy, `deploy/conferir_boot.py`, importa os mesmos
  módulos antes do restart).

**Prova:** `tests/test_oscreator_os_central.py` (a 3.1: as tarefas juntadas por OS e os índices; a faixa que troca só o que
cobre e a noite que tira o que não voltou; a ação na hora, com o registro, ao vivo pela sessão e fora de um pedido; o nº sem
pedido; os filtros das visões e o que vai ao vivo; o disco atômico, em fluxo, uma escrita por vez, e o corrompido; a cópia para
quem muda; os índices por partes iguais aos inteiros; a leitura que não desfaz o que mudou durante ela; e, da rodada 1 da
revisão, a trava de encolhimento, a memória medida uma vez por versão, a linha enxuta que monta o mesmo registro, a troca
no disco que tenta de novo o arquivo preso e a espera das duas gravações que se sobrepõem; da rodada 2, o apagamento confirmado
na 2ª leitura),
`tests/test_oscreator_os_leitor.py` (a 3.2: cada faixa contando os
pedidos, a falha no meio que não troca nada, os horários, o `tarefas_os` igual, o contador por faixa, as pendentes pelo nº, só
o servidor liga; e, da rodada 1, o REST que ignora o `sort` em ordem crescente e qualquer, as linhas fora do lugar que passam,
a leitura que encolheria a lista, a projeção por página, as pendentes mortas, a pausa antes de cada OS pelo nº, a data fim no
futuro, o defeito separado da falha e os minutos na lista única; da rodada 2, a leitura que acaba antes do piso e o topo
obrigatório) e `tests/test_oscreator_canto_no_raio_x.py` (as duas peças no
Raio-X, sem texto de OS nem nome).

## As telas leem da lista central de OS (31/10/2026, tarefa 3.3 do canto central)

O Histórico (todas as visões), o Garantias, a marcação verde dos Ativos, o Investigar ativo, o nº da OS → id e a 1ª pintura do
card leem da lista central (`os_web/lista_central.py`), e o que o OS Creator cria ou muda entra nela na hora. A lista é lida
pela credencial da EMPRESA e vê TODAS as OS; o que guarda cada tela (decisões AZ a BG da 3.3, os Rulings BP a BR da rodada 1,
o Ruling BU da rodada 2 e o Ruling BX da rodada 4 de correções, que fecharam os vazamentos para a visão restrita provados pelas
sondas das revisões):

- **A 1ª barreira: a lista central só para quem o Levi liberou** (Ruling BX, rodada 4). Provar por contagem que a pessoa vê o
  mesmo que a lista teve buracos raros a cada rodada de sonda; a segurança passa a depender de uma decisão de governança, e a
  contagem fica como 2ª barreira (e como a guarda da lista pela metade).
  - Quem está liberado: o administrador do Nexus (a NEXUS_ADMINS, a lista de Base → Acessos, a senha de administrador),
    sempre; e quem é de um setor de `ponte.SETORES_COM_LISTA_CENTRAL` (o setor_id do setor de Base → Acessos → Pessoas e
    setores, desde 04/11/2026; era o nome). Nasceu VAZIA (só os administradores); desde 03/11/2026 vale o `TODOS_OS_SETORES` ("*"):
    o Levi liberou todos ("Todos os setores veem todas as OSs" no Fracttal), e qualquer pessoa com setor no Nexus lê. A pessoa
    sem setor segue fechada.
  - Como mudar: um commit na `SETORES_COM_LISTA_CENTRAL` (`nexus/torres/oscreator/ponte.py`), com "*" para todos ou os nomes
    dos setores; a trilha fica no git. Não é uma caixa de Base → Acessos: lá cada item é uma tela do menu (abre uma página, conta no "vê N de
    M telas", entra no "Marcar tudo" e no "Copiar de", e a tela "por dentro" libera a de fora), e uma liberação que não é tela
    não cabe nele de forma limpa (o plano B do Ruling BX).
  - Como o clone sabe: a ponte põe a marca em todo pedido ao OS Creator (`request.environ["os_web.lista_central"]`,
    `ponte.lista_central`), e o `lista_central.liberada` a lê; a releitura do quadro de Garantias por trás leva a de quem a
    abriu (`lista_central.liberacao`). Sem a marca (o OS Creator servido sozinho, o PC, os testes, a ponte que não disse):
    ninguém está liberado. Sem saber o setor (o banco fora, o Nexus sem a NEXUS_PESSOA_HMAC, a pessoa sem setor): não.
  - Quem não está liberado não MONTA nada da lista em tela nenhuma (o Histórico e as visões, o Garantias, o Investigar, a
    marcação verde dos Ativos, a 1ª pintura e o nº → id), nem paga a conferência: segue pelo caminho de hoje, com a sessão dela.
    As ações dela seguem pondo na lista a OS que ela mudou (é escrita, não leitura).
  - **A exceção é o Garantias, e já era de 19/10:** quem não foi liberado pode RECEBER a cópia "TODOS" do quadro que um liberado
    montou da lista (`rotas_acomp._dono`: o Fracttal lhe dá o mesmo total de OS com a etiqueta CHAMADOS, com a folga de 1% ou 2
    OS, e ela fica na cópia dividida). É a exposição de 19/10 (a cópia dividida entre quem vê o mesmo total, "quebre essa
    regra"), e a lista central não a piora: a cópia só tem as OS que a conferência de quem a montou provou, o total dela é o do
    Fracttal de quem a monta, pedido a CADA montagem (`HS.total_conferido(..., max_idade=0)`, 1 pedido; a sonda V1b da revisão
    final: o total guardado por 30 min era o de quando a cópia anterior foi montada, e a restrita com 3 OS visíveis ficava a 2 da
    cópia de 5 e caía nela, com as 4 que o Fracttal esconde dela), e a restrita fora dessa folga segue com a dela.
- **A visibilidade não muda (fail-closed).** A tela que mostrava as OS pela sessão da pessoa só lê da lista depois da
  conferência DELA (`lista_central.conferir`), UMA por pessoa e período, sem visão, status nem etiqueta (Ruling BU): o "Todos"
  do período da tela; no Garantias, os 365 dias que ele lê (até amanhã: o "até" é a data local, e a criação é em UTC).
- **A conferência prova o CONJUNTO, não o número.** As duas contas param na **marca d'água** da lista
  (`os_central.Lista.marca`): a criação da OS mais nova que uma leitura até o topo trouxe (os 7 dias e a noite; as novas, só
  emendadas com o que a lista já leu; nunca para trás; a data no futuro não conta; vai na cópia em disco). Toda OS criada
  antes dela está na lista: a pessoa vê um pedaço do que a lista tem antes da marca, e as contas iguais dizem que ela vê todas.
  - O lado da lista: as OS do período criadas antes da marca, pelo índice da criação (`os_central.contar_criadas`, sem
    percorrer a lista: o Garantias são 365 dias).
  - O lado da pessoa: 1 pedido na sessão dela, `api.list_minhas_os_pagina("criadas", "TODOS", ...)`, com a página das 200
    mais novas (`CONFERE_LINHAS`, do tamanho das do `list_minhas_os`; era 50 até a rodada 4, e a OS antiga inserida depois
    ficava fora dela, a sonda Q): o total, menos as OS da página criadas na marca ou depois. O RPC ordena pelo id; o "até" dele
    ganha "T23:59:59" (não aceita data e hora), e o "de" vai como veio (a data e hora no "de" não foi provada no Fracttal, e
    seriam 2 pedidos): por isso a página. Ela tem de vir da criação mais nova para trás (o id do Fracttal cresce com a
    criação) e tem de chegar a uma OS de antes da marca, ou trazer todas; senão não dá para saber, e a tela vai ao vivo. E toda
    OS da página de antes da marca tem de estar na lista: a criada antes e inserida no Fracttal depois da leitura (o App
    offline, uma importação) a lista não tem, e ela compensaria uma escondida sem tirar a página da ordem. E, quando a página
    não traz todas, a lista não pode ter uma OS do período depois da marca com o id abaixo do menor da página (`Medida.id_min`):
    a criação fora da ordem do id (a OS do App offline com o relógio adiantado, a sonda R1) a pessoa conta, e a página não traz.
  - A regra é a IGUALDADE EXATA, em toda tela, com ou sem o ↻. A regra de uma mão da rodada 1 comparava números: a sonda
    mostrou a pessoa com H OS escondidas empatando com X ≥ H OS novas que a lista ainda não lera, ou com a mudança de status
    ou de etiqueta não lida quando a conferência levava o filtro da tela (no "Todos" padrão, no "Criado por", no Garantias e
    com status e etiqueta). A visibilidade no Fracttal não depende de status nem de etiqueta: passou, a visão, o "criado por",
    as atribuídas, o status e a etiqueta são filtros DA LISTA.
- **A tela mostra só o que a conferência provou** (`Prova`): as OS criadas antes da marca, as da página dela depois da marca,
  e as que a ação dela leu na sessão dela (`_vistas`: a OS que ela acabou de criar aparece na hora). A OS que entrou na lista
  depois da marca por outro caminho (a ação de outra pessoa, as abertas) só aparece a quem a página a trouxe.
- **A medida da pessoa fica 30 min por pessoa e período** (`_MEDIDAS`) e é conferida contra a lista de agora a cada visita, sem
  pedido. Ela guarda a conta da lista de quando foi pedida (`Medida.lista_n`, rodada 4): a lista que mudou depois tira a prova
  dela (a sonda S2: a OS que a pessoa via, apagada no Fracttal e tirada pela noite, empatava a conta com a escondida). É pedida
  de novo: no ↻; quando a lista mudou; quando a marca chega a uma OS que a página dela não trouxe (a faixa das novas leu OS
  novas: 1 pedido, e quem as vê, vê).
  - Quem não passa vai ao vivo em TODAS as visões daquele período.
  - Com a lista tendo MAIS que ela (o sinal da visão restrita), não é conferida de novo por 30 min (`_DIVERGIU`); o Raio-X a
    conta uma vez por janela. Com a lista tendo MENOS (atrasada), a visita seguinte confere de novo (Minor 2 da rodada 2).
  - A que falha (o Fracttal fora, a sessão caída) não passa; a medida guardada que provava segue provando. A sessão sem e-mail
    ("?") nunca passa (Minor 6).
- **A lista "Todos" dividida de 19/10 sem herança entre pessoas** (Rulings BU e BX). Com a lista central EM USO PARA O PERÍODO
  (o servidor, e a janela lida inteira começa no dia do início do período ou antes: `lista_central.em_uso(de)`, `janela[0] <=
  de`), coberta ou vencida, a "Todos" dividida do caminho de hoje só é dividida entre quem passou há pouco na conferência do
  período (`lista_central.divide_a_todos`); os outros (quem não passou, quem não foi liberado) seguem com a lista DELES,
  `("hist", pessoa)`, no Histórico e no Investigar (`rotas.ler_lista`). Quem vê tudo lê da lista central e não ancorava a
  dividida; a 1ª restrita que não passava a achava vazia, e a lista dela virava a de todos: a sonda mostrou outra restrita,
  com o mesmo total (30) e outro conjunto, vendo as 30 OS da usina que o Fracttal esconde dela; e a lista vencida (a última
  leitura até o topo passou dos 30 min) a devolvia (a sonda T3). Sem a lista em uso PARA O PERÍODO (o PC, a lista vazia, e a
  janela que começa depois do período, como a de 7 dias do dia do deploy, que nunca serve o Histórico de 30), a regra de 19/10
  fica como estava: a "Todos" dividida entre quem vê o mesmo total, e não uma lista de ~26 pedidos por pessoa (revisão final).
  A ação (`mudou`, `pendente`, `criadas`) também só lê a OS com a lista em uso, para o período padrão do Histórico (os 30 dias).
  A cópia dividida do Garantias (o `_dono`) também, e o total dela é o do Fracttal de quem a monta (o
  `total_chamados`, na chave do `_dono`), como no caminho de hoje: o da lista não tinha as OS de chamado novas, e a restrita
  com 2 a menos caía na cópia TODOS pela folga de 19/10 (a sonda V1).
- **O período tem de ser válido** (Ruling BP): duas datas 'AAAA-MM-DD' com o início até o fim (`periodo_valido`, na rota do
  Histórico e dentro da lista). O invertido dava 0 OS na lista e 0 no Fracttal, e a conferência "batia": vai ao caminho de hoje.
- **O dia de cada período é o do caminho ao vivo, e a janela começa pela data local** (rodada 2). O Fracttal toma a data da
  tela como o dia UTC dela (`creation_date >= de`, `<= até + "T23:59:59"`), e o `filtrar` também: a OS criada depois das
  21:00 de Brasília já é do dia seguinte, nas duas. O 1º dia da janela (`os_central._piso_da_janela`) é o da data LOCAL do
  servidor menos 365 dias, a das telas, e não o da data UTC: das 21:00 à meia-noite a data UTC já é a de amanhã, a janela
  começava um dia depois do `de` do Garantias, e o quadro ia ao vivo sem precisar (os testes falhavam nessa hora; um deles
  congela o relógio às 22:00 de Brasília).
- **O nº → id e a 1ª pintura do card só para quem conferiu tudo, e só dentro do que conferiu** (Ruling BP e o item 4 do BU). Os
  dois abrem uma OS qualquer pelo id, sem filtro para conferir. Só valem para quem passou na conferência dos 30 dias padrão até
  hoje (qualquer tela desse período, com filtro ou sem, ou o Investigar dentro dele), com pelo menos 20 OS na lista antes da
  marca (`liberado`, 30 min da medida), e só para a OS CRIADA nesses 30 dias e ANTES da marca, com a lista tendo no escopo a
  mesma conta de quando liberou (a sonda U1: a OS de 3 dias inserida depois, escondida, chegava pelos 7 dias e saía na 1ª
  pintura): a mais velha, a mais nova e a da lista mudada vão ao vivo, e o Fracttal decide. O "Buscar OS pelo nº"
  (`/os/os/folio/<nº>`) que não abre diz o nº, e não o id que a lista deu. A sonda liberava a pessoa restrita por um período
  invertido, por um dia quieto (0 e 0), por um dia em que todas as OS eram dela e pelo Investigar fora dos 30 dias.
- Tela por tela:

  | Tela | Antes | Agora | A conferência | O que libera o nº → id |
  |---|---|---|---|---|
  | Histórico, "Todos" (Visão COS, "Criado por: Todos") | a lista de "Todos" do `historico_store`, dividida por quem dá o mesmo total | a lista central | a do período (o "Todos" dela até a marca, exata) | os 30 dias padrão, com 20 OS ou mais antes da marca |
  | Histórico, "criadas por mim" e "Criado por" alguém | a lista dela, pela sessão dela | a lista central, pela conta, o código no pessoal e o nome | a mesma do período (o homônimo e quem não se identifica vão ao vivo sem conferir) | a mesma |
  | Histórico, "atribuídas a mim" | a lista dela | a lista central, pelo id da pessoa | a mesma do período | a mesma |
  | Histórico com status ou etiqueta | a lista daquele filtro | a lista central, o filtro na lista | a mesma do período | a mesma |
  | Garantias | a cópia "TODOS" (ou a dela), pela sessão de quem a montou | a mesma cópia, montada da lista central | a dos 365 dias de quem monta a cópia; o Atualizar e a releitura por trás medem de novo | nunca |
  | Investigar ativo | a lista de "Todos" do Histórico | a lista central, pelo índice por código de ativo | a do período carregado (a mesma medida da Visão COS) | os 30 dias padrão |
  | Marcação verde dos Ativos | uma para todos (`("cat", "os_recentes")`), pela sessão de quem chegou 1º | a lista central | nenhuma: já era dividida e segue dividida | — |
  | Nº da OS → id (`api._wo_id_por_folio`) | 1 a 5 pedidos pela sessão da pessoa | o índice por nº, sem pedido | — | a pessoa liberada, e só a OS dos 30 dias e de antes da marca |
  | 1ª pintura do card | (não havia: "Carregando a OS…") | a linha da lista, na hora | — | a mesma do nº → id; o card inteiro segue ao vivo |

- **A guarda da lista pela metade.** A mesma conferência. Cada uma que foi ao Fracttal conta no estado da lista, por tela
  ("histórico", "garantias", "investigar": `os_central.anotar_conferencia`, em `estado()["conferencias"]`: quantas, quantas
  divergiram, falharam e ficaram sem resposta pela página, e a última divergência com as duas contas até a marca) e no Raio-X,
  peça "Lista central de OS", linha "Conferências das telas" (a marca d'água vai na linha "Janela lida inteira"). A visão
  restrita de alguém também diverge (é ela que a guarda manda ao vivo); muitas divergências de quem vê tudo é sinal de lista
  errada, e muitas "sem resposta", de que a página não basta.
- **Os campos que o REST não trouxe (Ruling AT).** A tela só lê da lista os campos que a última leitura do período inteiro
  trouxe (`os_central.campos_medidos`; a medida vai também na cópia em disco, em `campos_rest`, para o deploy não mandar as
  telas ao vivo até a próxima). Só os 7 dias e a noite medem (rodada 3): a entrega das abertas, de hora em hora e com centenas
  de OS, media a data fim em 0% (OS aberta não tem data fim), e as telas iam ao vivo até a próxima leitura dos 7 dias ou das
  finalizadas; as finalizadas, as novas, as pendentes e as ações também não medem. A 3.3 acrescentou a data fim, o início e a nota do chamado, a rodada 1 a descrição, o
  ativo escrito, a equipe, o "atribuído a" e o status, e a rodada 2 a programada (a data do evento cai nela) no Histórico e no
  Investigar e a data fim, com quem está, quem criou e o tipo na 1ª pintura (as telas os mostravam sem medida). Com 0% (ou sem
  medida) num campo que a tela mostra ou filtra, a tela vai ao vivo:

  | Tela | Os campos que ela usa | Com 0% |
  |---|---|---|
  | Histórico Geral, Atribuídas | nº, criação, código do ativo (cliente, usina e tipo), ativo, descrição, status, tipo da tarefa (o filtro local), com etiqueta, data fim, programada (a data do evento) | a tela ao vivo |
  | Visão COS | os do Histórico, mais início, gatilho, equipe e quem criou | a Visão COS ao vivo (o Histórico Geral segue da lista) |
  | "criadas" | quem criou ou o código de quem criou | ao vivo sem os dois |
  | "atribuídas" | responsável (id) | ao vivo |
  | O filtro de etiqueta | etiqueta com id | pelo nome (o catálogo de etiquetas), se veio ao menos o nome; senão ao vivo |
  | Garantias | nº, criação, código do ativo, tipo da tarefa, com etiqueta, data fim, responsável (id), atribuído a, descrição, status, e a nota do chamado (conferida nas OS da etiqueta: nenhuma com a nota = o REST não a trouxe; uma cortada no teto também) | o quadro ao vivo |
  | Marcação dos Ativos | criação, código do ativo | ao vivo |
  | Investigar | os do Histórico | ao vivo |
  | Nº → id | nº e criação | ao vivo |
  | 1ª pintura | nº, criação, descrição, ativo, status, data fim, atribuído a, quem criou, tipo da tarefa | o "Carregando" de sempre |

  O card completa ao vivo o que a lista não tem (as subtarefas, os anexos, a OS pai, a solicitação, as notas), como sempre.
- **A nota do chamado com teto de 16.000 caracteres** (Ruling BR; era 4.000, `os_registro.NOTA_MAX`). O "parado há N dias" do
  Garantias sai das linhas do histórico da retroativa, que ficam no FIM da nota, e a de ~10 mil caracteres perdia o fim sem aviso:
  o quadro via a última atualização de um mês atrás e pulsava. A que ainda passa do teto fica marcada (`RegistroOS.nota_cortada`;
  a de exatamente 16.000 também, o lado seguro), e o quadro vai ao vivo. Medido (`sys.getsizeof`; a nota tem "—", e o texto
  fica com 2 bytes por caractere): 300 notas do App de ~1.500 caracteres, 0,87 MB; com 30 retroativas de 10.000 entre elas,
  1,36 MB (com o teto de 4.000 eram 1,02 MB, e as 30 saíam cortadas); 300 notas no teto, 9,17 MB (2,31 MB com o de 4.000). O
  pior caso é a nota com um caractere fora do BMP (um emoji no texto do App): o Python guarda a string INTEIRA com 4 bytes por
  caractere, ~18 MB para 300 notas no teto (Minor 5 da rodada 2). São poucas centenas de OS com a marca.
- **Onde a lista não cobre, tudo segue como hoje** (BC): o período inválido ou fora da janela lida inteira, a lista sem marca
  d'água (a cópia em disco de antes da rodada 2, até a 1ª leitura até o topo), o `filtrar` que dá None, o PC sem leitor (a
  lista vazia) — o `historico_store`, o `list_minhas_os` com o `meta_ja`, o `list_chamados`, o `codigos_os_recentes`, o
  `os_por_folio`, sem mudança nenhuma. A ordem: o período é válido, a lista o cobre, tem os campos e responde; só então a
  conferência (no PC e nos testes antigos, nenhum pedido a mais).
- **"a conferir".** A OS que uma faixa deveria ter trazido e não trouxe (o status pode ser velho) diz "a conferir" ao lado do
  nº no Histórico e no Investigar, e na 1ª pintura do card (o Exportar sai sem a marca); o card lê na hora. O filtro de status
  não a mostra (o status dela pode ser velho); a conferência a conta (o "Todos" não depende do status). O quadro do Garantias,
  que põe cada OS numa coluna pelo status, vai ao vivo enquanto uma OS dele estiver "a conferir".
- **As ações entram na lista** (BD): o Concluir, o Cancelar, o responsável, as etiquetas, a nota e o "fazer a tarefa" do card
  (`rotas_os_acoes`), o finalizar do Garantias, e as telas de criar (Criar OS do zero, Performance, Clonar, COS, a Área PCM, a
  aprovação da Fila do PCM, a Nova solicitação da Engenharia, a Inspeção de chamados) chamam `lista_central.mudou(id)` /
  `criadas(resultado)` DEPOIS de o Fracttal confirmar: a OS é lida pela sessão da pessoa (`os_central.atualizar_os`: as tarefas
  e o cabeçalho, 2 pedidos) e entra na lista, e na prova dela (`_vistas`).
  - Das criadas, as 3 primeiras dentro do pedido, juntas; as outras, a faixa das novas traz (até 3 min, 1 ou 2 pedidos). Até a
    rodada 1 elas eram lidas por trás, 2 pedidos cada, sem origem declarada (~94 pedidos numa criação de 50 OS do COS).
  - O "fazer a tarefa" sem o registro de execução confirmado não relê (seriam 2 pedidos que nada provam): a OS fica "a
    conferir" e pendente para a faixa das pendentes (`lista_central.pendente`, Minor 3 da rodada 2).
  - A releitura tem prazo: no máximo 5 s além da gravação (`RELEITURA_MAX_S`). O prazo é por fora (as releituras correm numa
    thread com a sessão copiada), porque as leituras do card (`_leitura_da_os`, `_cabecalho_os`) não recebem um: o `_rpc_call`
    aceita o `timeout`, elas não o passam. Passou do prazo: a resposta sai, a OS fica "a conferir" e pendente
    (`os_central.marcar_pendente`) para a faixa das pendentes; a releitura que já lia termina depois e a põe na lista do mesmo
    jeito, e a que nem começou (as 4 threads ocupadas) sai da fila (`cancel`, Minor 1 da rodada 2).
  - O finalizar do Garantias usa o status dessa releitura (sem reler o cabeçalho de novo).
  - A falha da lista nunca derruba a ação (vai ao log; a próxima faixa traz a OS). Só com a lista EM USO (a janela já lida: o
    servidor): no PC sem leitor a ação não gasta a leitura (caso que criou a regra: na 1ª rodada dos testes da 3.3, a leitura
    saiu da máquina nos testes antigos do quadro, que não trocam o `_rpc_call`, e a recusa derrubou o login).
- **O card não força mais o `atualizar=1`.** Ao fechar o card que mudou a OS, o Histórico e o Investigar voltam com `mudou=1`:
  da lista central, a linha já está lá (nenhum pedido); no caminho de hoje, a lista vem de novo, como vinha.
- **O ↻** mede de novo (1 pedido, a página) e mostra a lista central. A OS mudada fora do OS Creator aparece na faixa que a traz
  (os últimos 7 dias de 10 em 10 min de dia; as abertas de hora em hora; as antigas de madrugada). A tela diz de onde veio
  ("Lista das HH:MM", com o título da lista central).
- **A 1ª pintura do card** (`/os/api/os/<id>/previa`, `_os_previa.html`): o Histórico e o Investigar pedem, junto com o card, o
  que a lista sabe da OS (o nº, o tipo, o status, o ativo, as datas, com quem está, quem criou, o título), e a pintam até o card
  inteiro chegar, sem o círculo de carga. 204 = o "Carregando" de sempre. Vai com o `X-Nexus-Auto` (o clique já contou no card).
- **O que sobra (rodada 4, corrigido na revisão final).** A contagem é a 2ª barreira; os buracos que ela ainda tem, para quem
  foi liberado:
  - uma OS criada há mais de 7 dias (fora da faixa dos 7 dias, que relê a semana a cada 10 min), inserida no Fracttal depois da
    leitura (o App offline, uma importação) e além das 200 linhas da página da pessoa: a lista não a tem até a faixa que a
    traz, e ela compensaria uma escondida. O buraco vale para TODA OS fora dos 7 dias, e não só para as de 90 a 365 dias: no pior
    caso, até a noite que relê o dia dela (a de dia útil, às 03:21, relê os últimos 90 dias; a de domingo, a janela inteira: a
    de 90 a 365 dias espera o domingo). As faixas das abertas e das finalizadas (de hora em hora) podem trazê-la antes, quando
    o status ajuda;
  - a premissa de que o id do Fracttal cresce com a criação: a página confere a ordem nas linhas que traz e o menor id dela
    contra a lista, não o resto;
  - **a troca com a conta igual:** a medida da pessoa e o `liberado` comparam a CONTA da lista no período (`Medida.lista_n`) e as
    OS da página dela, não o conjunto inteiro. Para uma pessoa liberada (medida há menos de 30 min), uma OS apagada no Fracttal e
    uma inserção tardia (a OS antiga que entrou depois e que ela não vê) trocadas pela MESMA noite deixam a conta igual; se a
    apagada está além das 200 linhas da página dela, nada denuncia a troca, e a medida segue valendo, com a OS escondida na
    lista, até os 30 min. Precisa de tudo junto: uma pessoa liberada medida nos 30 min antes da noite (03:21), um apagamento e
    uma inserção tardia nessa mesma leitura. É raro.
  - O custo de uma OS apagada no Fracttal e ainda na lista: quem vê tudo vai ao vivo naquele período até a noite a tirar (a
    lista tem uma a mais); no Garantias (365 dias), até a noite das 03:21.
- **Pedidos ao Fracttal, medidos** (o Fracttal de mentira no nível do `api._rpc_call`, 3 mil OS em 30 dias, ~99 por dia; as
  páginas de 200 e os lotes de tarefas de 130; a lista central cheia):

  | Tela | Antes da 3.3 | Rodada 1 | Agora (rodadas 2 a 4, quem foi liberado) |
  |---|---|---|---|
  | Visão COS, 1ª visita da pessoa | 26 (10 páginas, 16 lotes) | 1 (a conferência) | 1 (a conferência do período) |
  | Visão COS, de novo / 3 min depois sem OS nova / a de 10 min | 1 / 2 (as novas) / 21 (a inteira) | 0 / 0 / 0 | 0 / 0 / 0 |
  | Visão COS depois de a faixa das novas trazer 1 OS | — | 1 (a lista com mais que o total guardado) | 1 (a marca chegou a uma OS que a página dela não trouxe) |
  | No mesmo período: "criadas por mim", "Criado por" alguém, atribuídas, a Visão COS com um status, com uma etiqueta | a lista de cada um (2 a 26) | 1 cada (a conferência era por visão e filtros) | 0 (a conferência é do período) |
  | Visão COS, o ↻ / a volta do card que mudou uma OS / a virada do dia | 21 / 21 / 26 | 1 / 0 / 1 | 1 / 0 / 1 |
  | Garantias, 1ª visita / o Atualizar | 3 + os tickets / 3 + os tickets | 2 (o `total_chamados`, que o `_dono` também usava) + os tickets / 2 + os tickets | 3 (a página dos 365 dias e o `total_chamados` de quem monta a cópia, o total dela: rodada 4) + os tickets / 3 (o Atualizar pede os dois de novo) + os tickets |
  | Marcação verde dos Ativos (30 dias) / Investigar ativo (depois da Visão COS) | 31 páginas / 0 a 2 | 0 / 0 | 0 / 0 |
  | Nº → id / a 1ª pintura do card | 1 a 5 / — | 0 / 0 (a pessoa liberada) | 0 / 0 (a pessoa liberada, a OS de antes da marca) |
  | Ação do card (concluir, cancelar...) | a gravação + o card (5) + a lista na volta (21 ou 2) | a gravação + 2 (a OS na lista) + o card (5) | o mesmo |
  | A visão restrita: a 1ª visita / 2 min depois / o "Criado por" alguém do mesmo período / a Visão COS com um status | 26 / 0 / 2 / 26 (a lista dela) | 27 (a conferência e a lista dela) / 0 / 3 / 27 (a conferência daquela visão e a lista dela) | 27 / 0 / 2 / 26 (só a lista dela: a conferência do período já divergiu) |

  Desde a etapa 4 o pessoal e o id da etiqueta vêm dos catálogos (`catalogos.py`, seção "Os catálogos pequenos num lugar
  só"): no caminho ao vivo, o "criadas por mim" e o Garantias deixaram de pagar 1 a 2 pedidos a mais por leitura.

  Medido com o relógio das 18:00: das 21:00 à meia-noite, até a rodada 2, o Garantias ia ao vivo (a janela pelo dia UTC; ver
  acima). A conferência pede 200 linhas em vez de 1: o mesmo pedido, maior. Quem não foi liberado (rodada 4) paga o caminho de
  hoje, como antes da 3.3; com a lista em uso, a "Todos" dele é a lista dele (a dividida só entre quem passou na conferência),
  como a visão restrita da última linha: 26 na 1ª visita do período (medido), as novas depois (0 a 2), e a marcação verde dos
  Ativos, o Garantias e o nº → id ao vivo, como antes.

- **Memória.** As visões prontas (as até 2.000 linhas e o HTML delas) ficam só para a VERSÃO de agora da lista, no máximo 8
  (`VISOES_GUARDADAS`), e só são montadas de novo quando a versão muda (a leitura que não trouxe nada não muda a versão; a hora
  "Lista das HH:MM" acompanha a última leitura). Medido com 36 mil OS (tracemalloc, o retido): a Visão COS de 30 dias 7,3 MB (o
  caminho de hoje, 7,1 MB), o Histórico Geral de Todos depois dela 4,5 MB (4,5), as criadas por mim 0,3 MB (0,4); o caminho de
  hoje guarda as listas do `historico_store` por pessoa e período, e a que ninguém lê há 30 min sai quando outra é lida
  (`LISTA_VIDA_S`, revisão final: sem isso elas cresciam até o reinício, ~10 por dia; a que está sendo lida fica, mesmo velha),
  e a lista central não cria nenhuma. As medidas das pessoas são poucas e pequenas (a marca, a conta e até 50 ids; no máximo
  4.000).
- **Prova:** `tests/test_oscreator_historico_central.py`:
  - a 3.3: a página sem pedido depois da conferência; a visão restrita com a dela, a divergência no estado, a conferência que
    falha; "criadas por mim", "atribuídas" e o homônimo; a virada do dia; o campo que o REST não trouxe; o Garantias, os Ativos
    e o Investigar da mesma lista, e o quadro com a OS "a conferir"; a 1ª pintura; a ação do card sem releitura; as ações e a
    criação que entram na lista, e a falha que não derruba; o PC ao vivo, e a ação que não lê a OS para a lista fora de uso; a
    medida dos campos na cópia em disco; as conferências no Raio-X;
  - a rodada 1, com os casos da sonda: o período invertido, o dia quieto, o dia em que todas as OS são dela e o Investigar fora
    dos 30 dias não liberam; só os 30 dias padrão liberam; o escopo com menos de 20 OS não libera; a prévia e o nº de uma OS de
    mais de 30 dias vão ao vivo mesmo liberada; o "Criado por" outra pessoa não mostra a OS escondida; a visão por pessoa e o ↻
    com 1 OS a menos vão ao vivo; a "Todos" com o Fracttal dando 1 a mais passa e com a lista tendo 1 a mais vai ao vivo; os
    campos novos na medida; a nota longa do chamado sem o "parado" errado, e a cortada ao vivo; as criadas além das 3 sem a
    thread; o prazo da releitura; quem diverge sem reconferir por 30 min; a visão refeita só por versão; o finalizar e o "fazer
    a tarefa" sem pedido a toa;
  - a rodada 2, com as sondas da re-revisão: a "Todos", o "Criado por" e o Garantias com (H, X) = (1, 1), (2, 2), (2, 4) e
    (1, 3) não mostram a OS escondida nem liberam; o status e a etiqueta com a mudança não lida; quem vê tudo com 4 OS novas
    depois da marca passa; a página toda depois da marca, a página fora da ordem da criação e a OS antiga que a lista não tem
    vão ao vivo; a OS que entrou depois da marca só para quem a página trouxe; o nº e a prévia só antes da marca; duas
    restritas com o mesmo total não trocam de lista (o Histórico e o Investigar); a fila da releitura sem começar sai; a lista
    com menos não prende 30 min; o "fazer a tarefa" sem confirmação fica pendente; a programada e os campos da prévia
    medidos; a sessão sem e-mail não passa; a marca d'água (as faixas que a mexem, a que não, a data no futuro, nunca para
    trás, a cópia em disco); e o relógio congelado às 22:00 de Brasília, com o Histórico e o Garantias lendo da lista;
  - a rodada 4: quem não foi liberado nunca lê da lista (o Histórico, o Garantias, o Investigar, os Ativos, a 1ª pintura e o
    nº → id), mesmo vendo tudo; sem a marca no pedido, fechado; a ponte libera o administrador e os setores da lista, e não
    os outros; de ponta a ponta no Nexus, o setor não liberado vai ao vivo e o liberado e o administrador leem da lista; e as
    sondas Q1 e Q2 (a OS antiga além da página), R1 (o id baixo com a criação depois da marca), S2 (a medida com a lista
    mudada), U1 (o liberado com a lista mudada), T3 (a lista vencida e a "Todos" dividida) e V1 (o total da cópia TODOS),
    e o nº que não abre sem mostrar o id;
  - a revisão final: a V1b (a cópia TODOS remontada 10 min depois pede o total de novo, e a restrita com 3 visíveis não vê as
    escondidas); a guarda `liberada()` da prévia e do nº com a pessoa liberada há pouco e um pedido da mesma conta sem a marca
    (204, e o nº vai ao vivo; sem a guarda, a medida sozinha abria as duas); a janela de 7 dias do dia do deploy, que deixa a
    regra de 19/10 e não lê a OS da ação; a lista do Histórico que ninguém lê há 30 min sai; o arquivo estático sem a leitura
    do setor; o gancho do nº só na cópia do clone; e a `HOJE` por teste.

  Os testes de 19/10 (`test_oscreator_historico_compartilhado_19_10.py`) e de 21/10 (`test_oscreator_lista_pela_metade_21_10.py`)
  seguem provando o caminho de hoje (a lista central vazia, como no PC: a montagem deles diz isso). O universo dos testes tem o
  id crescendo com a criação, como no Fracttal, e nenhum depende da hora em que roda: a OS "nova" é de 6 h atrás (a de 1 min,
  depois das 21:00, é do dia UTC seguinte e fica fora do período padrão, nos dois caminhos).

## Os catálogos pequenos num lugar só (31/10/2026, etapa 4 do canto central)

Levi, 30/10/2026: "a ideia é não ter um carregamento novo por atividade e sim um ecossistema onde as coisas se aproveitam e não
precisamos ficar fazendo novas requisições sempre!" (desenho: `docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`,
"Etapa 4"; tarefa 4.1).

**Antes:** o pessoal era lido por 7 caminhos, as etiquetas por 4, os tipos e as classificações por 3 (duas cópias que NUNCA
venciam: o tipo novo do Fracttal só aparecia no reinício, e o conjunto vazio de quem não tinha a permissão ficava para sempre),
as falhas do COS numa cópia que nunca vencia, e os planos da Performance eram relidos inversor por inversor a cada usina
escolhida. Tudo só na memória: cada push na `main` reinicia o serviço e cada tela pagava de novo.

**Agora** (`os_creator/catalogos.py`): UM dono por assunto, com prazo próprio (`PRAZO_S`), uma cópia em disco e a MESMA forma de
antes para as telas (as funções devolvem cópias, no formato do `api` de antes). Os planos da Performance moram ao lado, em
`catalogos_planos.py` (por ativo), e o laço das pessoas pelo REST em `catalogos_leitor.py` (o par como o dos ativos: o catálogo
guarda e entrega; o leitor, que importa o `nexus`, só o servidor liga).

| Assunto | Prazo | Quem lê do Fracttal | Arquivo em `<dados>/oscreator/catalogos/` |
|---|---|---|---|
| Pessoas | 6 h | o REST da empresa no servidor (se trouxer os campos) ou o RPC pela sessão (`api.ler_pessoal`) | `pessoas.json` (sem e-mail) |
| Etiquetas | 6 h | RPC (`api.get_labels`) | `etiquetas.json` |
| Tipos e classificações da OS | 24 h | RPC (`api.get_tipos_classif`) | `tipos.json` |
| Grupo e classificações da solicitação | 24 h | RPC (`api.get_request_types`) | `tipos_solicitacao.json` |
| Falhas do COS | 24 h | RPC (`api.get_falha_listas`) | `falhas.json` |
| Status da solicitação | 24 h | RPC (`api.status_solicitacao_catalogo(levantar=True)`) | `status.json` |
| Motivos de cancelamento | 24 h | RPC (`api.get_cancel_motivos`) | `motivos.json` |
| Planos da Performance, por ativo | 24 h | RPC (`api.ler_planos_do_ativo`, `api.get_plan_details`) | `planos.json`, `planos_detalhe.json` |

- **O boot só lê o disco**, nunca o Fracttal, nem com a cópia vencida (`aquecer`, por trás, quando a ponte liga:
  `ponte.ligar_catalogos`, nas duas máquinas; e a 1ª leitura de cada assunto, se o aquecimento ainda não chegou). A cópia é
  escrita ao lado e trocada de uma vez (`canto_disco`), com o formato e o nome dentro; a ilegível, cortada, de outro formato,
  de outra forma ou vazia é ignorada, e o motivo vai a `estado()` (e ao Raio-X). A gravação escreve o valor VIGENTE e pula só
  a leitura que o disco já tem (um contador de leituras, não o `lido_em`).
- **Quem renova.** As pessoas têm o leitor da empresa: o REST `personnel` do cadastro (`cadastro/fracttal_pessoal.ler_paginas`),
  pela credencial da empresa, 1 pedido por segundo, às 05h, 11h, 17h e 23h no :04 (`minutos_ocupados.CATALOGOS_PESSOAS`; só o
  `servir.py` liga, `catalogos_leitor.ligar`; no contador do Fracttal, `fundo:nexus-catalogos:pessoas`). Com o REST valendo, as pessoas
  vencem 1 h depois do prazo (`FOLGA_REST_S`: o laço pode atrasar) e o RPC não as renova; o laço que parou ou o REST falhando
  devolvem as pessoas ao socorro pelo RPC. O resto não tem leitor da empresa (o RPC exige a sessão de uma pessoa,
  `os_web/sessao.py`): a 1ª sessão que acha o catálogo vencido o renova POR TRÁS, uma vez para todos, com a cópia do contexto
  (o JWT dela e a rota dela no contador do Fracttal), como o `api._renovar_catalogo_por_tras` dos ativos (uma função só para
  os assuntos, os planos e os detalhes: `catalogos.renovar_por_tras`); quem chega com a renovação em curso usa a cópia velha e
  não espera; a renovação que falhou espera 10 min (`ESPERA_TENTATIVA_S`), e a sessão caída de UMA pessoa não segura ninguém.
  A renovação por trás roda com um estado de sessão PRÓPRIO (`os_web.sessao.propria`, pelo `api._na_sessao_propria`, também no
  catálogo de ativos): a cópia do contexto levava o mesmo estado do pedido de quem pediu, e um 401 por trás o mandava ao
  login. E tem ritmo: 1 pedido por segundo entre as chaves (`PAUSA_S`), o 406/429 espera 5 s e 10 s e tenta a mesma chave de
  novo (`ESPERAS_COTA_S`), a cota que não voltou para a renovação, e a sessão que caiu também (as chaves que faltaram voltam a
  ser de quem chegar, já). Sem cópia nenhuma (a máquina nova, o disco ilegível), a 1ª tela lê na hora, e quem
  chega junto espera a MESMA leitura (uma trava por assunto: a carga fria da Fila segue paralela).
- **O erro e o vazio não ficam guardados** (a regra de 20/10/2026): a lista vazia da sessão de alguém sem a permissão esvaziaria
  a tela de todo mundo pelo prazo inteiro. **Nem a leitura pela metade**: as falhas do COS só valem com as três listas (o
  `get_falha_listas(levantar=True)` sobe o erro de cada uma; antes, um 429 nas causas guardava `{"causas": []}` por 24 h e o
  COS recusava toda OS de falha), e o erro de verdade vai ao estado e à tela. Os status sem o Fracttal, ou com o Fracttal
  respondendo a lista vazia, voltam a lista local, que NÃO fica guardada (até 31/10 ela ficava 30 min na cópia da Fila como se
  fosse o que o Fracttal aceita); sem catálogo nenhum, a falha só é tentada de novo depois de 10 min (cada Fila aberta com o
  Fracttal fora não vira um pedido).
- **Quem não acha o que procura relê** (`reler=True`, no máximo uma vez por minuto, `RELER_NA_FALTA_S`, com a sessão de quem
  pediu): o tipo de tarefa pelo nome (`api.tipo_main_ao_vivo`, a Zeladoria criada hoje), a etiqueta pelo nome (`api._label_id`,
  `api.label_id_por_nome`) e a pessoa logada que não está no catálogo (`da_pessoa`, abaixo).
- **A gravação não confia no catálogo.** O que o catálogo tem e o Fracttal tirou nas últimas horas (a etiqueta apagada, a pessoa
  desligada) segue na TELA até a renovação. A criação da Engenharia confere a pessoa e a etiqueta ENGENHARIA AO VIVO, uma
  leitura de cada por gravação, com a sessão de quem cria (`api.responsaveis_ao_vivo`, `api.get_labels`): a regra de 19/10 é
  que, faltando uma delas no Fracttal, nenhuma OS sai, e a sessão morta é acusada ali, antes de gravar (401 e o login, e não
  um "Relogue" por ativo). A etapa 4 a tinha posto no catálogo e a revisão da 4.1 a tirou. Nas outras gravações que levam um
  id do catálogo (a etiqueta da criação da Performance, o tipo pelo nome) o que o Fracttal faz com o id que deixou de valer não
  foi medido: não se presume que ele recuse.
- **A pessoa logada sem o e-mail.** `catalogos.da_pessoa(email)` acha (id_personnel, id_account, nome) pelo HMAC do e-mail
  (`email_h`, com a chave que a ponte deriva da do Nexus: `ponte.chave_dos_catalogos`); nem a memória nem o disco guardam o
  e-mail. A cópia feita com outra chave (a `NEXUS_SECRET_KEY` trocou) não acharia ninguém: é ignorada, com o motivo no estado, e
  o pessoal é relido uma vez. A pessoa sem nome no Fracttal aparece nas telas pelo e-mail (o `full_name` dela é o e-mail):
  esse nome não vai ao disco em claro, e depois de um reinício ela some das listas até a próxima leitura. A pessoa logada que
  não está no catálogo (a conta nova no Fracttal) relê o pessoal pelo RPC, com a sessão DELA, na hora, uma vez por pessoa a
  cada 10 min, e não com o catálogo recém-lido: com o REST valendo a renovação das pessoas é só do laço do servidor, e a conta
  nova ficava até 6 h sem "criadas por mim". A 2ª tela dela que chega com a releitura em curso (duas abas) espera a mesma
  leitura: a vez de 10 min é marcada depois dela. A conta que NUNCA está no pessoal (quem cria OS sem ser cadastrado como
  pessoa) paga essa releitura também na 1ª tela depois de cada reinício (a vez de 10 min é da memória): 2 pedidos, as ~150
  pessoas em duas páginas, que renovam o catálogo para todos.
- **O `_label_id` não vai mais ao Fracttal.** Ele era relido a cada lista de propósito (08/10/2026): era o 1º pedido das listas
  por etiqueta e acusava a sessão morta, porque a listagem engolia o erro das páginas. Desde 21/10/2026 a página que falha
  derruba a busca inteira (`_lista_pela_metade`): a lista acusa sozinha. A conferência do Garantias (`total_chamados`) passou
  de 2 pedidos para 1.

**Os caminhos, de onde liam e de onde leem** (a forma que a tela recebe não mudou em nenhum):

| Caminho | Antes | Agora |
|---|---|---|
| Pessoas 1. `rotas.responsaveis_fracttal` (`/os/api/responsaveis`: Performance, PCM, Tradicional; Clonagem, Inspeção, a Engenharia na tela) | `_memo(("cat", "responsaveis"))`, 10 min, sobre `api.get_responsaveis` (RPC) | `catalogos.pessoas()` |
| Pessoas 2. o "Criado por" e o "eu" do Histórico (`rotas.historico`, `_contas_do_filtro`) | `_memo(("pessoas", pessoa))`, 10 min POR PESSOA, sobre `api.get_pessoas_contas` (RPC) | o mesmo, POR PESSOA (`rotas._contas_da_pessoa`): não é do catálogo, ver "Visibilidade" |
| Pessoas 3. o técnico sugerido da Solicitação e da Fila (`rotas_solic._pessoas`) | `_memo(("solic_cat", "pessoas"))`, 30 min (RPC) | `catalogos.pessoas()` |
| Pessoas 4. a pessoa logada (`api._current_user_info`: "criadas por mim", "atribuídas", a lista central) | `_user_ids_cache` por e-mail, até o reinício, relendo o pessoal até achá-la (RPC) | `catalogos.da_pessoa(email)` |
| Pessoas 5. o nome do responsável no card (`api._personnel_nome_por_id`) | `_personnel_name_cache`, até o reinício (RPC) | `catalogos.nome_por_id()` |
| Pessoas 6. o Requerido por do COS (`rotas_cos.api_listas`) | `api.get_responsaveis` a cada abertura (RPC) | `catalogos.pessoas()` |
| Pessoas 7. a criação da Engenharia (`rotas_solic_eng.api_criar`) | `api.get_responsaveis` a cada criação (RPC) | ao vivo, uma leitura por gravação (`api.responsaveis_ao_vivo`): não é do catálogo |
| Etiquetas 1. `rotas.etiquetas_fracttal` (Histórico, card, Criar OS, a lista central) | `_memo(("cat", "etiquetas"))`, 10 min | `catalogos.etiquetas()` |
| Etiquetas 2. a Fila e a Solicitação (`rotas_solic._etiquetas`) | `_memo(("solic_cat", "etiquetas"))`, 30 min | `catalogos.etiquetas()` |
| Etiquetas 3. o id pelo nome (`api.label_id_por_nome`: a criação da Performance, a OS em execução) | `_LABEL_IDS`, com o "não existe" até o reinício | `catalogos.etiquetas()`, e `reler=True` para quem falta |
| Etiquetas 4. o id das listas por etiqueta (`api._label_id`: Garantias, Performance, a análise da Engenharia) | `api.get_labels` a cada lista (RPC) | `catalogos.etiquetas()`, e `reler=True` para quem falta |
| Etiquetas (a criação da Engenharia) | `api.get_labels` a cada criação | ao vivo, uma por gravação (`api.get_labels`): não é do catálogo |
| Tipos 1. `api._lista_tipos` (o COS, o Criar OS, a Fila) | `_TIPOS_CACHE`, uma vez por processo, nunca vencia | `catalogos.tipos_classif()` (o `api.get_tipos_classif` é só o leitor) |
| Tipos 2. a Fila (`rotas_solic._tipos`) | `_memo(("solic_cat", "tipos"))`, 30 min | `catalogos.tipos_classif()` |
| Tipos 3. a classificação e o tipo pelo nome (`api._classif_ids`, `api.tipo_main_ao_vivo`) | `_CLASSIF_CACHE`, nunca vencia (o vazio também) | `catalogos.tipos_classif()`, e `reler=True` no tipo que falta |
| Falhas do COS (`rotas_cos.api_listas`, `_falhas_para_criar`) | `_falha_listas_cache`, nunca vencia | `catalogos.falhas()` |
| Status da solicitação (`rotas_solic._status_cat`) | `_memo(("solic_cat", "status"))`, 30 min, com a lista local guardada quando falhava | `catalogos.status()` (a lista local não fica) |
| Grupo e classificações da solicitação (`rotas_solic.solicitacao`) | `_memo(("solic_cat", "tipos_solicitacao"))`, 30 min | `catalogos.tipos_solicitacao()` |
| Motivos de cancelamento (`rotas.motivos_cancelamento`, o card) | `_memo(("cat", "cancel_motivos"))`, 10 min | `catalogos.motivos()` |
| Planos da Performance (`api.get_performance_alvos`, `rotas.api_plano`) | `task_events_list` por ativo e `tasks_details` a cada usina escolhida | `get_plans_for_assets(..., guardados=True)` → `catalogos_planos.planos_dos_ativos`; `catalogos_planos.detalhe_do_plano` |

  Fica de fora de propósito: o login (`oauth_fracttal._pessoa_no_personnel`), que acha a pessoa pelo token e precisa do e-mail
  em claro (o catálogo não o guarda); a Clonagem de planos do PCM (`get_plans_for_assets` sem `guardados`), que mexe nos planos e
  os quer como estão agora; e a criação de OS pelos planos (`get_plan_details` ao vivo, a cada criação).

- **Os planos da Performance ficam por ATIVO**, e não por grupo de tarefas (`id_group_task`): o RPC é perguntado por `id_item`
  (os eventos são do ativo), o plano do tracker mora só no generalizado (`get_performance_alvos`), a estação tem planos que o
  inversor não tem, e nada no código mostra dois ativos do mesmo grupo respondendo o mesmo; o `perf_web.contar_subtarefas`
  amostra um ativo por tipo só para contar subtarefas. Guardar por grupo poderia oferecer a um ativo um plano que ele não tem.
  O detalhe do plano (o resumo da tela) fica por plano e ativo, SEM o `raw` (o resumo não o usa e ele repetiria as subtarefas);
  até `PLANOS_MAX` ativos e `DETALHES_MAX` detalhes, os de 7 dias sem uso saem. A lista vazia não fica (pode ser a sessão sem a
  permissão; o ativo sem plano é relido a cada escolha). A cópia em disco é montada e escrita uma por vez (`_TRAVA_DISCO`):
  duas gravações juntas montavam a cópia na trava e escreviam fora dela, e a montada antes podia cobrir a nova. **Medido** (`tracemalloc`, dados sintéticos na forma do RPC): a
  carteira inteira (~2.850 inversores e estações, 8 planos cada) 5,7 MB na memória com um objeto só para cada nome de plano
  (7,4 MB sem isso) e 1,7 MB em disco; um detalhe com 30 subtarefas ~25 KB (150 detalhes, 3,6 MB). Os outros catálogos são
  de dezenas a ~150 linhas.
- **As pessoas pelo REST, os campos.** O cadastro conhece do REST `personnel` o `id_personnel`, o `code`, o `full_name`/`name`, o
  `email`, o `groups_permissions_description` e o `account_active` (`fracttal_pessoal.da_api`). As telas do OS Creator usam o id,
  o código, o nome, o `active` (o pessoal ATIVO: a conta ativa é outra coisa), o `id_account` (quem criou a OS) e o e-mail. O
  `active` e o `id_account` nunca foram vistos no REST, e este computador não lê o Fracttal com a credencial da empresa: a
  sondagem é a conferência de cada leitura (`campos_que_faltam`: cada campo em >= 99% das linhas). Faltou um, nada muda, o
  estado diz qual, e as pessoas seguem pelo RPC. A 1ª leitura REST contra um catálogo do RPC confere ainda a lista de
  responsáveis (>= 95% em comum nos dois sentidos: o mesmo campo com outro sentido mudaria quem as telas mostram) e, das
  pessoas em comum, a conta (`id_account`: o dono do "criadas por mim") e o e-mail (`email_h`: quem a pessoa logada é), >= 95%
  iguais cada um (revisão da 4.1: o mesmo id com outra conta passava); a 1ª que
  vale PRECISA desse catálogo (a 1ª noite dos ativos, REST x RPC: na máquina sem cópia, espera a 1ª tela que o lê pela
  sessão de alguém); e nenhuma leitura REST que encolhe mais de 10% troca o catálogo.
- **Visibilidade.** Nenhum destes catálogos depende de quem pergunta no código: eles já eram um para todos desde 19/10/2026
  (`("cat", ...)`, `("solic_cat", ...)`) ou por processo (`_TIPOS_CACHE`, `_falha_listas_cache`, `_CLASSIF_CACHE`). O único sinal
  de diferença por pessoa é a lista VAZIA de quem não tem a permissão, que não é guardada. A pessoa logada sai por pessoa do
  catálogo comum (`da_pessoa`, pelo HMAC do e-mail dela). O "Criado por" do Histórico (as contas e o "eu") NÃO: ele era por
  pessoa, com a sessão dela, e segue assim (`rotas._contas_da_pessoa`, 10 min para cada uma, sobre `api.get_pessoas_contas`):
  quem não tem a permissão de pessoal no Fracttal recebe a lista vazia, e no catálogo comum veria as contas da empresa (a
  etapa 4 o tinha posto no catálogo, e a revisão da 4.1 o devolveu).

**Pedidos ao Fracttal** (pela conta do código e pelos testes; o pessoal tem ~150 pessoas, 2 páginas de 100):

| Catálogo | Antes | Agora: a 1ª abertura do dia | Agora: as seguintes, de qualquer pessoa |
|---|---|---|---|
| Pessoas | 2 por tela a cada 10 min, POR PESSOA no Histórico, a cada abertura do COS e criação da Engenharia, e 1 ou 2 por pessoa a cada reinício (no teste, 3 pessoas pelos 7 caminhos: 15) | 0 na tela; 2 por trás se a cópia passou das 6 h (ou 0: o REST das 05h) | 0 nos caminhos do catálogo (no teste: 1 leitura para os 5 caminhos e 3 pessoas); fora dele, como antes: o "Criado por", 2 por pessoa a cada 10 min no Histórico, e a criação da Engenharia, 2 por gravação |
| Etiquetas | 1 a cada 10 min e a cada 30 min nas telas, 1 a cada lista por etiqueta e a cada criação da Engenharia (no teste: 6) | 0 na tela; 1 por trás se passou das 6 h | 0 (no teste: 1); a criação da Engenharia, 1 por gravação, como antes |
| Tipos e classificações | 3 a cada reinício (~10 por dia útil), e nunca mais | 0 na tela; 3 por trás se passou das 24 h | 0 |
| Falhas do COS | 3 a cada reinício, e nunca mais | 0; 3 por trás passadas as 24 h | 0 |
| Status, grupo e classificações da solicitação, motivos | 1, 3 e 1 a cada 30, 30 e 10 min de uso | 0; 1, 3 e 1 por trás passadas as 24 h | 0 |
| Planos da Performance | N eventos (um por inversor e estação) + 1 detalhe a CADA usina escolhida | a 1ª escolha de cada usina: N + 1 | 0 (e, vencidos, 0 na tela e N + 1 por trás) |
| O reinício (cada push) | relia os tipos, as falhas, a pessoa de cada um, o nome do card | 0 (a cópia em disco), menos para quem não está no pessoal: 2 na 1ª tela dela depois de cada reinício (a releitura da conta nova, `da_pessoa`, que renova o pessoal para todos) | 0 |

**Onde se vê:** Raio-X → seção "Uso do OS Creator" → o bloco do canto central, peça **"Catálogos pequenos"**: uma linha por
catálogo (quantos, a fonte, lido em, a idade contra o prazo, VENCIDO e se está renovando, a última falha, as leituras do
Fracttal neste processo, o disco), a linha "Pessoas pelo REST" (o laço: ligado, a próxima, se vale, a última boa e a falha com
o campo que faltou) e a "Planos da Performance" (`raio_x._linhas_dos_catalogos`). Nunca nome nem e-mail.

**Prova:** `tests/test_oscreator_catalogos.py` (`test_um_pedido_para_todas_as_telas` por catálogo, os caminhos das pessoas que são do catálogo, os
das etiquetas, dos tipos, das falhas, do status, do grupo da solicitação e dos motivos, com 3 pessoas: uma leitura;
`test_as_telas_veem_o_mesmo_de_antes`; `test_reinicio_sem_pedido`, com a cópia vencida (e a releitura de quem não está no
pessoal); `test_disco_corrompido` por catálogo e
os planos corrompidos; `test_performance_segunda_vez_sem_pedido` e a vencida que volta e renova por trás;
`test_prazo_vencido_renova_por_tras`, uma vez para duas pessoas, com o JWT de quem achou; o erro e o vazio que não ficam; o
status local que não fica; quem chega junto na 1ª leitura; o e-mail fora do disco; as pessoas pelo REST com os campos, sem
eles, sem bater com o RPC e valendo; só o servidor liga; o minuto na lista única; a ponte; o Raio-X). A rodada 1 da revisão
(31/10/2026), um teste vermelho para cada achado: `test_a_criacao_da_engenharia_confere_ao_vivo`,
`test_as_falhas_pela_metade_nao_trocam_as_completas`, `test_o_criado_por_e_de_cada_pessoa`,
`test_o_rest_com_a_conta_ou_o_email_trocados_nao_troca`, `test_a_renovacao_por_tras_nao_derruba_a_sessao_de_quem_pediu` (e o
dos ativos), `test_a_conta_nova_com_o_rest_valendo_e_achada_pelo_rpc`, `test_o_nome_que_e_um_email_nao_vai_ao_disco`,
`test_a_renovacao_dos_planos_por_tras_tem_ritmo`, `test_o_status_com_o_rpc_vazio_e_a_lista_local_e_nao_fica` e
`test_a_copia_dos_planos_em_disco_nao_volta_atras`; e, da re-revisão, `test_a_conta_nova_em_duas_telas_juntas_espera_a_mesma_leitura`.
Os testes de antes que injetavam o pessoal pelo `api.get_responsaveis` passaram a injetá-lo pelo leitor
(`api.ler_pessoal`); o `test_oscreator_card_e_anexos_29_10` não zera mais o `_CLASSIF_CACHE`, que saiu.

## Um caminho só para juntar as tarefas numa OS (31/10/2026, etapa 5.1 do canto central)

O desenho (`docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`, "Etapa 5"): "hoje são vários [caminhos de
criação], cada um com a sua regra: o tempo da OS de 30/10/2026 (10 min fixos em quatro caminhos) foi esse erro". Todo caminho
que junta tarefas numa OS numerada tinha a sua cópia da **fase 2** (ler o kanban, inserir a OS, pôr as etiquetas, anexar as
fotos). Agora a fase 2 é uma só: `os_creator/os_juntar.py`.

- **`juntar_em_os(id_tasks, duracoes, id_responsible, responsible_name, *, id_parent, note, etiqueta_ids, imagens, registros,
  frases)`**: o registro de cada tarefa no kanban (`_kanban_records`; o que o chamador já leu vai em `registros` e não é lido de
  novo) → a OS (`_work_order_insert`) com o tempo igual à **soma do tempo das tarefas que ENTRARAM nela** (`_tempo_da_os`) →
  as etiquetas → as fotos, cada uma na tarefa do ativo dela. Devolve `{id_tasks, id_work_order, wo_folio, nao_entraram[,
  etiquetas][, aviso][, n_img_ok, img_erro]}`; **sem `id_work_order` a OS NÃO saiu** (o kanban caiu, ou não trouxe nenhuma
  tarefa): as tarefas ficam pendentes no Fracttal e o `aviso` diz o que fazer. A OS que não fecha (`work_order_insert`
  recusado) sobe como `FracttalError`: o Criar OS agrupado a transforma em aviso ("a OS não fechou"), os outros mostram o erro.
- **`uma_os_por_tarefa(fase1, ...)`**: a fase 2 de "uma OS por ativo" e "por data" (`create_work_orders_bulk` e
  `create_work_orders_datas`, que tinham o mesmo bloco copiado): o kanban é lido UMA vez para todas (50 OS do COS não são 50
  leituras) e cada OS sai pelo `juntar_em_os` com o registro já lido.
- **Quem passa por ele** (oito caminhos): a Clonagem de planos do PCM (`create_planned_os_multi`) e o um-plano-vários-ativos
  (`create_planned_os_one_wo`); o Criar OS agrupado e a Engenharia agrupada (`create_work_orders_agrupada`); a Performance
  agrupada (`create_performance_os_agrupada`); a Clonagem de OS (`clonar_os`) e, por ela, a Fila do PCM (`aprovar_solicitacao`) e a
  OS sem plano (`create_os_sem_plano`); a **retomada** da Fila (a tarefa que ficou de uma tentativa que parou no meio; o registro
  dela já veio da busca, sem ler o kanban de novo); e o Criar OS de uma OS por ativo / por data, o COS e a Engenharia
  (`uma_os_por_tarefa`). O `convert_task_to_wo`, que punha os 600 s fixos, saiu: ninguém o chamava mais.
- **O que cada chamador ainda é dono de**: criar as tarefas pendentes (a fase 1, que muda de caminho para caminho: o plano, a
  clonagem, o título por ativo), conferir o responsável (sem ele as tarefas ficam pendentes e nem o kanban é lido), o formato do
  resultado que a tela lê e **as frases dos avisos**. A mesma falha era dita de quatro jeitos (o "não gerei" / "não consegui gerar"
  a OS, a etiqueta de um jeito em cada tela), e mudar o que as telas mostram não é desta etapa: o padrão (`FRASES`) é o do Criar OS e
  da Clonagem de planos, e a Clonagem de OS, a Performance e o uma-OS-por-tarefa passam as suas em `frases`.
- **O que ele NÃO faz.** Não põe a OS na lista central de OS (`os_central.atualizar_os`): as telas de criar chamam
  `lista_central.criadas`, que tem a guarda de "lista em uso" e o limite por pedido (3.3), e chamar daqui a pularia. E não
  confere a pessoa nem a etiqueta ao vivo: a criação da Engenharia faz isso na rota, ANTES da primeira tarefa
  (`api.responsaveis_ao_vivo` e `api.get_labels`, a regra de 19/10/2026), e continua assim. As fotos da Performance agrupada
  seguem na `create_performance_os_agrupada` (`os_criar.py`), casadas pelo ativo (`id_item`) com as tarefas relidas da OS: o juntar
  casa pela ordem, e mudar a Performance para ela mudaria o que ela lê e como casa.
- **O que mudou de verdade (dois casos de borda, os dois com teste):** (1) a OS da Clonagem de OS somava o tempo das tarefas
  CRIADAS, mesmo as que o kanban não trouxe e que portanto não estão nela; agora soma as que entraram (como já faziam as outras
  quatro). (2) A foto do Criar OS agrupado era casada pela ordem das tarefas criadas: se o kanban não trazia a 1ª, a foto do ativo 1
  ia para a tarefa do ativo 2; agora é casada com a ordem das que entraram. O resto é igual ao de antes, pedido por pedido.
- **Prova:** `tests/test_oscreator_os_juntar.py`. O Fracttal é de mentira no nível do HTTP (cada pedido ao rpc/proxy fica guardado,
  na ordem), e `test_payload_igual_ao_de_antes` compara 41 cenários (os oito caminhos, e para cada um a falha do kanban, a tarefa
  não achada, a etiqueta que falha, a OS que não fecha, a tarefa que não nasceu) com o que o código de ANTES mandou e devolveu
  (`oscreator_payloads_antes_da_5_1.json`, gravado no d18ce7b, com o SHA-1 do corpo de cada pedido). Mais:
  `test_todos_os_caminhos_passam_pelo_juntar` (e o pedido que insere a OS só sai de dentro dele),
  `test_so_o_juntar_chama_o_insert_da_os` (nenhum arquivo do OS Creator chama o `_work_order_insert` fora do `os_juntar.py`),
  `test_tempo_e_a_soma_em_todos`, `test_avisos_de_hoje`, o kanban lido uma vez para as N OS, a criação da Engenharia que confere a
  pessoa e a etiqueta ao vivo antes do primeiro pedido de gravação e chega pelo juntar, e a lista central que ele não toca. Doze
  mutações do `os_juntar.py` (tempo fixo, a nota que some, o kanban lido por OS, a OS pai procurada antes do kanban, a etiqueta que
  derruba...) são pegas.

## O mapa dos módulos: o que sobra do api.py (31/10/2026, etapa 5.3 do canto central)

O `api.py` chegou à etapa 5 com 6.631 linhas (6.504 depois da 5.1) e uns quinze assuntos dentro: criar OS, o Histórico, o card, as
solicitações, o cronômetro, os planos, os chamados... Cada assunto foi para o módulo do dono dele, e o `api.py` ficou com 1.239
linhas (uns 60 de fachada). **Só o lugar mudou**: nenhuma linha de código, só o prefixo `api.` (as regras, abaixo). Prova: a árvore de cada
uma das 292 funções, classes e constantes que saíram foi comparada com a do `api.py` de antes (o 4133f34, no git), e a única
diferença era o `api.` na frente dos nomes; os 406 nomes que o `api` tinha seguem nele, com os mesmos tipos.

| Módulo | Linhas | O que mora nele | Quem chama de fora |
|---|---:|---|---|
| `api.py` | 1.239 | o cliente do Fracttal: login e sessão, o RPC (`_rpc_call`, `_rpc_chamar`, o cache das leituras de uma OS), a tarefa que nasce (`create_os_rpc`, `_react_insert_post`), o S3 (`attach_imagem_os`, `s3_get_url`, `baixar_imagem`), a configuração e a fachada | tudo |
| `fracttal_erro.py` | 15 | `FracttalError` e `SessionExpired` (o `api` os reexporta: o MESMO objeto) | todos os módulos |
| `os_juntar.py` | 184 | a fase 2 de todo caminho que junta tarefas numa OS (seção anterior) | `os_criar` |
| `os_criar.py` | 1.070 | os caminhos que CRIAM OS: a Clonagem de planos e de OS, a OS sem plano, o Criar OS do zero (por ativo, agrupada, por data), a Performance, a OS de análise e as do chamado; a leitura do kanban e a inserção da OS (`_kanban_records`, `_work_order_insert`), `apply_labels`, `nascer_ticket` | as rotas de Criar OS, COS, Clonagem, PCM, Performance e Engenharia (`nexus/engenharia/os_analise.py`) |
| `os_historico.py` | 563 | a lista de OS: a linha de cada OS (`_shape_wo_row`), a leitura por período e por página, a meta de cada tarefa, o "Criado por" (`get_pessoas_contas`) | o Histórico, o COS, Garantias, Investigar ativo e a lista central de OS (`os_central`, `lista_central`) |
| `os_detalhe.py` | 421 | a OS aberta no card: cabeçalho, tarefas, subtarefas com respostas, solicitação de origem, OS pai (`buscar_os_pai`), a OS para clonar | o card, o PDF, a Clonagem, o `os_registro` |
| `os_estado.py` | 471 | cancelar, trocar o responsável, a nota, o status, concluir, o fluxo da OS, achar a OS pelo número (`os_por_folio`, `_wo_id_por_folio`) | o card, Garantias, a Engenharia |
| `os_anexos.py` | 331 | LER as fotos e os arquivos: imagens, recursos, anexos por tarefa e por subtarefa, os da solicitação, `_ids_tarefas_da_os` | o card, o PDF, a Nova solicitação |
| `os_execucao.py` | 573 | o cronômetro (iniciar, pausar, retomar, finalizar, o motivo de pausa, o tempo trabalhado) e o checklist da tarefa (subtarefas, respostas, validação de segurança) | o card, a Engenharia, Garantias |
| `os_planos.py` | 416 | os planos (modelos de tarefa): por ativo e o detalhe, os da Performance, as subtarefas que o app acrescenta, a contagem e o tempo de cada plano, os modelos da Clonagem | o PCM, a Performance, a Clonagem, `catalogos_planos` |
| `perf_alvos.py` | 167 | os tipos de ativo da Performance, o nome curto do ativo e da usina para o título, `get_performance_alvos` | a Performance, o COS, a Engenharia |
| `os_chamados.py` | 377 | o bloco "CHAMADO" da observação, a lista de chamados, o status em massa, a OS 3 (tickets), as últimas OS de um ativo, as respostas da inspeção | Chamados, Garantias |
| `os_solicitacoes.py` | 431 | as solicitações de serviço: criar, listar, status, observação, cancelar e APROVAR em OS numerada (`aprovar_solicitacao`) | a Nova solicitação, a Fila do PCM |
| `ativos_carga.py` | 344 | a cola do `api` com o catálogo central de ativos (`load_assets_cached`, a recarga pelo RPC, a renovação por trás, os textos dos três "Atualizar ativos") | toda tela que lista ativos |
| `catalogos_rpc.py` | 226 | os leitores dos catálogos pequenos pelo RPC (`ler_pessoal`, `get_labels`, os tipos, as falhas, `_classif_ids`) que o `catalogos.py` chama pelo nome | `catalogos`, a criação da Engenharia (que confere ao vivo), o COS |
| `os_tempo.py` | 126 | a data do Fracttal em Brasília, o tempo entre datas, as horas de sol, `_tempo_da_os` | tudo que formata data |
| `dash_os.py` | 80 | a fila de OS sugeridas do dashboard de O&M (a configuração mora no `api`: `DASH_CONFIG_FILE`) | `tickets_escrita` |

Os módulos que as etapas 1 a 4 criaram (`ativos_central`, `ativos_leitor`, `ativos_disco`, `ativos_foto`, `os_central`, `os_leitor`,
`os_registro`, `os_disco`, `catalogos`, `catalogos_leitor`, `catalogos_planos`, `canto_disco`) não mudaram.

**As regras do código que mudou de lugar** (`tests/test_oscreator_fachada.py` confere):
- **`api.X` é a fachada.** Todo nome de antes segue no `api` (no fim do arquivo, um `from <módulo> import (...)` por módulo), e é
  por ele que a ponte, as rotas, os outros setores (`nexus/pcm`, `nexus/engenharia`, `nexus/auth`) e os testes chamam e TROCAM as
  funções (`monkeypatch.setattr(api, "_rpc_call", ...)`). Onde este README diz "no `api.py`" para uma função que a tabela leva a
  outro módulo, o endereço `api.X` segue valendo; o código mora no módulo.
- **Toda função que um módulo chama vai pelo `api.`**, a dele e a dos outros (`api._rpc_call(...)`, `api.get_os_detalhes(...)`), e
  também o número ajustável (um prazo, um teto: `api.ESPERA_NOVOS_S`). Senão o teste que troca `api.X` não é visto por quem chama
  pelo nome local, e passa sem testar nada. Só as outras constantes (os nomes dos métodos do RPC) e o estado do próprio módulo são
  usados direto. Um módulo novo, ou uma função nova num módulo, segue a mesma regra, e o teste da fachada acusa a chamada pelo nome
  local.
- **Os 14 módulos que o `api` reexporta terminam com `import api`**, e o `api` os importa no fim do arquivo (a fachada): o
  círculo se fecha na hora de carregar e as funções só usam o `api` na hora da chamada. Qualquer módulo pode ser importado
  antes do `api`. As duas exceções: o `fracttal_erro` não importa nada do OS Creator, e o `os_juntar` não é importado pelo `api`
  (é o `os_criar` que o importa) e chama o `api` na hora, por uma função (`_api()`), que o importa dentro. Toda função que um
  módulo importa de OUTRO módulo do clone (o `montar_registros` do `ativos_central`, que o `ativos_carga` chamava como
  `_build_records`) também vai pelo `api.`, e o teste da fachada acusa a que fica pelo nome local.
- **O que o Python executa na hora de definir** (o valor padrão de um argumento, uma constante calculada) não pode usar o `api.`;
  por isso o `HISTORICO_CAP` usado como padrão fica sem o prefixo, e o que depende de `_data_dir()` na hora de carregar
  (`ASSETS_CACHE_LEGADO`, `DASH_CONFIG_FILE`) ficou no `api`.

**O que ficou no `api.py`, e por quê**
- **Quem fala com a rede direto** (`_get_token`, `_req`, `fracttal_login`, `_rpc_try_refresh`, `_rpc_chamar`, `create_os_rpc`,
  `_react_insert_post`, `s3_get_url`, `baixar_imagem`, o S3 e o `attach_imagem_os`): o Raio-X rotula o pedido preso pelo arquivo da
  linha NOSSA mais de dentro (`nexus/casca/presos.py`: `os_creator/api.py` e os módulos que saíram dele nas etapas 5.1 e 5.3,
  os 14 de `_MOVIDOS_DO_API`, = "Fracttal (OS Creator)"; o `dash_os`, que fala com o dashboard, e o resto da pasta = "OS Creator").
  Antes de a revisão final pôr os módulos movidos na regra, a espera de uma thread em código que saiu do `api.py` (o `get_assets`
  esperando as 6 threads dele, agora no `ativos_carga`) passou a ser rotulada "OS Creator", e o Raio-X e o log deixaram de dizer
  "Fracttal (OS Creator)". Se os pedidos à rede saíssem do `api.py`, o `onde` do episódio mudaria de arquivo.
- **A sessão** (`_save_jwt`, `_read_jwt`, `_clear_jwt`, `current_user`, `_sessao_propria`...): o `os_web.sessao.instalar` troca essas
  funções do `api` por outras, por nome, uma vez por processo.
- **O RPC e o cache das leituras de uma OS** (`_rpc_call`, `_leitura_da_os`, `_LEITURAS_OS`): os testes trocam o `_rpc_call` em 25
  lugares, e o cache é estado global que se zera quando ele é trocado.
- **O que é trocado de fora**: `ID_PELA_LISTA` (a lista central de OS o instala no `api`), `_CODE_LOC_TENTOU`,
  `_current_user_info`, `_current_user_ids`.

**Dois acertos no caminho:** os erros foram para o `fracttal_erro.py` (os módulos novos dizem `except FracttalError` e não podem
importar o `api` ao carregar), e o `import os_juntar` do `api` saiu (quem o usa é o `os_criar`).

**Como foi conferido:** (1) o AST de cada função, classe e constante movida contra o `api.py` de antes; (2) nenhum nome indefinido
nos módulos (um `api.` esquecido ou um nome local que ficou para trás); (3) os 461 `api.X` escritos nos módulos existem no `api`;
(4) cada módulo importado primeiro, num interpretador limpo; (5) `test_payload_igual_ao_de_antes` (a seção anterior) e o recorte da suíte
`oscreator or cos or solic or casca or cadastro or historico or garantia or acomp or prefixo or engenharia or pcm` (3.133 testes, que
trocam o `api.X` de dezenas de funções). Quatro mutações do `test_oscreator_fachada.py` (chamada pelo nome
local, nome fora da fachada, `api.X` que não existe, módulo sem o `import api`) são pegas.

## O catálogo de ativos vencido por trás (24/10/2026)

Em 23/10/2026 às 10:44 o catálogo de ~22 mil ativos passou das 24 h (`api.ASSETS_TTL`) e o 1º a precisar dele o baixou
DENTRO do pedido (~110 pedidos ao Fracttal, 6 de cada vez): um "Criar OS" da Performance ficou 3 min 51 s em
`get_assets`, e o Histórico 1 min 52 s esperando o mesmo download. Levi, 24/10: "deixe um botão de atualizar ativos e
quando atualizar vai atualizar a lista de todos, não só daquela pessoa".

- **Vencido, o de ontem volta na hora** (`api.load_assets_cached`) e o novo é baixado por trás
  (`_renovar_catalogo_por_tras`, a thread `os-catalogo-por-tras`), com a sessão de quem pediu (a cópia do contexto leva o
  JWT). Uma tentativa a cada `ASSETS_ESPERA_TENTATIVA` (10 min): a que falhou deixa o de ontem. A que veio e foi recusada
  (encolheu) conta como conferida, e o retry de 10 em 10 min acabou para ela (31/10/2026, seção do catálogo central).
- **Espera o novo** só quem precisa dele em dia: `em_dia=True` (resolver o ativo da OS na aprovação,
  `rotas_solic._catalogo_para_aprovar`); e quem não tem catálogo nenhum na máquina.
- **O botão "Atualizar ativos"** (OS Creator → Ativos, `/os/api/ativos/atualizar`) vale para todos: o catálogo é um só (desde
  31/10/2026 o central, seção acima; antes, o arquivo `assets_cache.json`). Ativo cadastrado hoje que não aparece: é ele. Com o
  leitor do servidor (31/10/2026), ele busca só os ativos novos e volta na hora (seção "Os botões Atualizar ativos sem esperar o
  Fracttal"); sem ele (o PC), baixa o catálogo inteiro na hora, como antes.
- Prova: `tests/test_oscreator_catalogo_por_tras_24_10.py` (7; 6 falham no código de antes, o outro segura o "sem
  catálogo, espera"); 5 mutações, todas pegas. Desde 31/10/2026 os mesmos cenários rodam sobre o catálogo central (o
  download troca o catálogo da memória e a cópia em disco).

## Os catálogos e o catálogo de ativos uma vez para todos (19/10/2026)

O mesmo superplano (o mapa de cada pedido ao Fracttal, por tela, que a sessão fez em 19/10/2026):

- **Pessoal ativo, etiquetas, motivos de cancelamento, tipos de solicitação e as OS recentes da tinta dos Ativos**
  (`rotas.responsaveis_fracttal`, `etiquetas_fracttal`, `motivos_cancelamento`, `os_recentes`; os tipos da
  solicitação no `("solic_cat", "tipos_solicitacao")`): iguais para todos, eram relidos a cada tela e a cada clique, por cada pessoa (o pessoal são
  2 pedidos; as OS recentes, 17 a 40 pedidos em sequência a cada visita aos Ativos). Ficaram 10 min na memória, um para
  todos; o erro não fica guardado, e o catálogo vazio também não (`_memo(..., guardar=)`, 20/10/2026: a lista vazia da
  sessão de alguém sem a permissão esvaziaria a tela de todo mundo pelo TTL). **Desde 31/10/2026 o pessoal, as etiquetas, os
  motivos e os tipos da solicitação têm um dono só** (`catalogos.py`, seção "Os catálogos pequenos num lugar só", acima: o
  prazo de cada um, a cópia em disco, a renovação por trás; a mesma regra do erro e do vazio). A criação da Engenharia segue
  lendo o pessoal e as etiquetas AO VIVO, uma leitura de cada por gravação (a gravação não confia no catálogo), e o "Criado
  por" do Histórico segue por pessoa. As OS recentes seguem aqui, quando a lista central de OS não cobre o período.
- **O catálogo de ~22 mil ativos** (`api.load_assets_cached`): lido do disco uma vez por versão do arquivo (antes cada
  uma das 26 chamadas decodificava o JSON inteiro, a prévia do COS a cada 120 ms de digitação), entregue em cópia por
  registro; e a recarga do Fracttal (~110 pedidos) é uma por vez: quem acha o catálogo vencido junto espera a mesma. O
  resumo "N ativos, catálogo de quando" (`api.assets_cache_info`, da tela inicial e da de Ativos) usa o mesmo catálogo
  (20/10/2026: decodificava o arquivo inteiro, 10,5 MB, a cada chamada). **Desde 31/10/2026 é o catálogo central** (seção
  "O catálogo de ativos central"): na memória uma vez por processo e entregue SEM cópia (os registros são só de leitura); a
  recarga de uma por vez segue igual, e o `_catalogo_cru` saiu.
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

- **A regra mora no pacote** `chamado_garantia` (o do OS Creator; o App de Campo carrega a sua cópia, e a do oem ficou
  congelada): `registro.py` põe a aba
  `os_creator · chamado_modelos` (a que a tela Fabricantes grava) por cima do código. O `chamado_modelos_store` do OS
  Creator passou a chamar o pacote (o canal de abertura continua só aqui); os nomes públicos dele não mudaram.
- **A marca no nome do ativo** (`spec.marca_do_ativo`, a única: a de `regras` chama esta) vale como palavra inteira e
  pelos apelidos do Fracttal (`APELIDOS_NO_FRACTTAL`). No catálogo de 14/10: +80 Canadian ("CANANDIAN SOLAR"), +169
  Huawei (só o modelo SUN2000), os 131 Axial grudados ("AXIALtracker") seguem Axial, e saem os falsos STI (16
  cabines, skids e estações pelo "sti" no meio de uma palavra do endereço, como numa "Rua Celestino" ou numa "Rua
  Faustino", exemplos inventados; os 43 trackers de uma usina pelo código dela, que começa com STI).
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

## A OS pai vai no pedido que cria a OS numerada (04/11/2026)

Uma colega avisou ao Levi: "o OS Creator do nexus não tá puxando a OS pai". Provado no ar no mesmo dia, em TESTE - PA: a OS
18561, criada pelo Criar OS com a 18560 de pai, nasceu sem pai (o card sem "OS pai" e o Fluxo só com ela).
- **A causa:** a OS pai só vale no pedido que cria a OS numerada (`_work_order_insert`, sondado em 26/08/2026); na tarefa
  pendente (o `create_os_rpc` e o `create_planned_os` sem `to_work_order`) o Fracttal a ignora. A fase 2 de todos
  (`os_juntar.juntar_em_os`) aceitava a OS pai, mas só a Performance agrupada a passava: o Criar OS (uma por ativo,
  agrupado e por data), a Fila do PCM (aprovar e retomar), a Clonagem de OS, a OS sem plano e a Clonagem de planos
  mandavam a OS pai só na tarefa, e as OS nasciam sem pai. O seletor e o "puxar" das telas (a OS pai da Engenharia no Criar
  OS e na Nova solicitação, a da solicitação na Fila) estavam certos: a OS pai chegava ao servidor e se perdia na criação.
- **A correção:** todo caminho que recebe a OS pai a passa ao `juntar_em_os` (e o `uma_os_por_tarefa` a repassa). O
  `oscreator_payloads_antes_da_5_1.json` foi regravado: a única mudança nos 41 cenários é a OS pai no pedido da OS.
- **Os caminhos que criam a OS de uma vez** (`to_work_order=True`: a OS já realizada, a Performance de uma OS por ativo e a
  inspeção do chamado) mandam a OS pai no mesmo pedido que cria a OS, e ela fica: provado no ar em 04/11/2026 em TESTE - PA,
  a OS 18564 (realizada) e a 18571 (Performance de uma OS por ativo) nasceram com a 18560 de pai, no card e no Fluxo.
- **Conferir depois de gravar** (`os_juntar.conferir_os_pai`, 1 leitura do cabeçalho, só com OS pai): a fase 2 e os
  caminhos de uma vez leem a OS criada e, se o Fracttal não gravou a OS pai, a tela diz. Foi o silêncio que deixou o defeito
  passar semanas. Os de uma vez ganharam a conferência no mesmo dia, depois do pedido do Levi ("Performance e engenharia
  também tem OS pai, veja se está funcionando normalmente!"); a OS já realizada do COS por data, em 05/11/2026.
- **A Performance de uma OS por ativo diz o que houve:** o nº de OS pai digitado que não existe no Fracttal vira "OS X criada
  sem a OS pai" (a agrupada já dizia), e as ressalvas de cada OS (essa, a OS pai não gravada e as perguntas de fim de
  atividade recusadas, que se perdiam dentro do `create_performance_os`) chegam à tela em "Atenção:", com o resultado em
  cor de alerta. A inspeção do chamado mostra a OS pai não gravada junto do aviso da etiqueta.
- **A Engenharia:** o Solicitar OS e o Criar OS da página da OS (e da gaveta do acompanhamento) abrem a Nova solicitação e o
  Criar OS do zero com a OS já escolhida como OS pai (conferido no ar com a 18567), e a criação segue os caminhos acima.
- Prova: `test_a_os_pai_vai_no_pedido_que_cria_a_os_numerada` (vermelho nos 7 caminhos antes da correção),
  `test_a_os_que_nasce_numerada_tambem_confere_a_os_pai` e `test_a_performance_diz_a_os_pai_que_nao_achou_e_a_tela_mostra`
  (vermelhos antes da conferência), em `tests/test_oscreator_os_juntar.py`.

## A OS já realizada vai feita aos dois destinos (05/11/2026)

A revisão das OS achou, na prova no Fracttal de verdade: a OS 18630 (TESTE - PA), criada como "já realizada" com "enviar
para Verificação", nasceu Em Processo, sem fim e com "0 de 1" subtarefas, e o Fracttal não disse nada.
- **A causa:** o `create_os_rpc` mandava `work_done` False sempre que o destino era a Verificação (`to_in_review`), e o
  Fracttal tratava a tarefa como não feita. Agora ela vai feita (`work_done` True) nos dois destinos; o `to_in_review` diz
  qual.
- **Conferir depois de gravar** (`api._conferir_ja_realizada`, 1 leitura do cabeçalho por OS já realizada): o status tem de
  ser o pedido (Em Verificação ou Concluída). A de Verificação que ficou Em Processo vai para Em Verificação pelo
  `mudar_status_os` e é lida de novo. O resto (a dos Finalizados que ficou Em Processo, a de Verificação que o Fracttal
  concluiu) vira o aviso da OS na tela, sem mexer: concluir daqui fecharia a OS sem a pessoa ver, e fechar é irreversível.
  Cabeçalho sem status ou leitura que falhou: sem aviso (a OS existe).
- Vale para o Criar OS do zero (uma OS por ativo, também o da Engenharia) e o COS (uma por ativo e "várias datas"), que
  chegam ao `create_os_rpc` pelo `create_work_orders_bulk` e pelo `create_work_orders_datas`. Os avisos de cada OS se somam
  (o do status, o da etiqueta que falhou e o da OS pai); até aqui o da etiqueta apagava o que vinha antes.
- **Provado no ar** em 05/11/2026, em TESTE - PA: a OS 18635, criada pelo Criar OS do zero como já realizada com "enviar
  para Verificação", nasceu Em Verificação, com a data de fim e "1 de 1" subtarefas, sem aviso (lida de volta pelo Fluxo e
  pelo card), e foi cancelada. Os Finalizados não foram criados no ar (a OS concluída não se cancela): o pedido deles não
  mudou, o `work_done` já ia True; só ganhou a leitura do cabeçalho.
- Prova: `test_a_os_ja_realizada_vai_feita_aos_dois_destinos`, `test_a_verificacao_que_ficou_em_processo_vai_para_a_verificacao`,
  `test_o_destino_que_nao_ficou_vira_aviso`, `test_sem_o_status_no_cabecalho_nao_ha_aviso` e
  `test_o_aviso_do_status_fica_junto_do_da_etiqueta_e_do_da_os_pai`, em `tests/test_oscreator_os_juntar.py`. O ouro
  (`oscreator_payloads_antes_da_5_1.json`) foi regravado: a única mudança é a leitura do cabeçalho no
  `uma_os_por_ativo_ja_realizada`.

## A OS de vários ativos: ordem natural, anexos por tarefa e "Vários" no Histórico (04/11/2026)

Levi, 04/11/2026: "quero que os ativos fiquem mais organizados"; "quero que dê para ver o anexo especificamente daquela
tarefa e dê para baixar tudo de uma vez, o download sai com o nome do ativo!"; e "no Histórico ... no ativo apareça
'VÁRIOS' ao invés de aparecer o 1° ativo".
- **Ordem natural** (`os_acoes_web.ordem_natural`): com mais de um ativo, as tarefas do card vão por ativo, 1.1, 1.2 ...
  1.10 (o Fracttal devolvia 1.1, 1.10, 1.2), e o número da tarefa acompanha. O banner virou etiquetas (`.det-ativo`), na
  mesma ordem, no lugar da frase corrida.
- **Anexos por tarefa:** cada anexo de subtarefa sabe a tarefa dele (`id_tarefa` no `os_anexos.get_os_subtarefa_anexos`,
  `tarefa` no JSON); a contagem do card (`/os/os/<id>/anexos`) diz quantos de cada tarefa (`por_tarefa`), o ativo mostra
  "N anexos" e o botão "Ver os anexos desta tarefa" abre a mesma janela dos anexos só com os dele.
- **O nome do ativo no arquivo:** o card manda `{id da tarefa: ativo}` (lido das tarefas dele) ao `anexos-zip`, e o
  `plano_do_zip` põe cada arquivo na pasta do ativo, começando pelo nome dele ("Inversor 1.2/Inversor 1.2 - 01 -
  print.jpg"); com `tarefa`, o .zip leva só os daquela tarefa ("OS 15900 - Inversor 1.2 - anexos.zip"). O "Baixar" de um
  anexo também sai com o nome do ativo. Sem ativos (OS de um ativo só), a arrumação de antes, pela subtarefa.
- **"Vários" no Histórico** (`rotas.preparar_linhas`): a OS com mais de um código de ativo mostra "Vários" na coluna (e
  "Vários (N)" no Exportar); a de um ativo, o nome curto de sempre.
- Prova: `tests/test_oscreator_card_ativos_anexos_04_11.py`; os 2 testes de `test_oscreator_card_por_ativo_28_10.py`
  aceitam o `data-ativo` novo na tarefa.

## A Nova solicitação para a Performance (06/11/2026)

Levi, 06/11/2026: "adicione mais um em solicitações agora performance, será a mesma coisa porém com etiqueta de
performance!"; e, no quiz do responsável, "Só a equipe da Performance".
- **A mesma tela da Engenharia, com o setor no endereço** (`/os/solicitacao/performance`; as rotas `/os/api/solicitacao/
  <engenharia|performance>/...`): os mesmos campos, regras, datas, anexos e a mesma regra (um ativo, uma OS; mais de
  um, uma OS só); tipo Administrativa e só a Classificação 1, Programada. O que muda vem de `solic_eng_web.SETORES`: a
  etiqueta **PERFORMANCE**, sempre e só ela (faltando no Fracttal, nenhuma OS sai), a lista de responsáveis e
  "Performance" nas frases. A Nova solicitação tem agora três abas: PCM, Engenharia e Performance.
- **Os responsáveis:** só a equipe da Performance, que é quem está no setor Performance em Base → Acessos → Pessoas e
  setores (Levi: "Já tem no setor da performance em base > acessos"): o gancho `solic_eng_web.MEMBROS_DO_SETOR`, que a
  ponte liga (`ponte.membros_do_setor`), lê a última decisão de cada pessoa no livro `nexus_setores` (1 min de cópia) e
  dá os ids do Fracttal, que são o `id_personnel` do responsável. Ninguém do setor no Fracttal, ou o livro fora, a tela
  abre e diz. Nada no `.env` nem no código. A da Engenharia segue nos nomes do .env (`OS_WEB_ENGENHARIA_RESPONSAVEIS`).
- Prova: `tests/test_oscreator_solic_performance_06_11.py` (e os da Engenharia, `test_oscreator_solic_engenharia.py`,
  seguem verdes); conferido na bancada (desktop e 375 px).

## O card diz a usina, a data de criação e quanto já foi feito (05/11/2026)

Levi, 05/11/2026, em várias voltas na bancada e no ar: "as vezes clico na OS sem contexto e não sei que usina é. adicione
também data de criação da OS"; "Usina sempre acima dos ativos! pois a usina é mais importante"; uma barra "tipo barra de
bateria do celular"; na OS de 14 ativos, "Está ocupando muito espaço na tela", "Quero os ativos fiquem recolhidos e que
seja expansível!" e "Tire esse emoji"; "Bora aproveitar esse espaço!"; e, por fim, "separe data de criação, deixe ao lado
direito de duração total" e "a barra tente colocar em outro canto, pode ser deitada horizontal mesmo".
- **O banner** (sem o ícone), em campos lado a lado numa faixa só, separados por um traço (no celular, um embaixo do
  outro): a USINA primeiro (`os_detalhe._usinas_da_os`: a mesma da coluna Usina do Histórico, o nome curto, pelo código de
  cada ativo das tarefas no catálogo central em memória, `ativos_central.atual().local_por_codigo`, cada uma uma vez;
  "Usina" ou "Usinas"); depois o ATIVO e o CÓDIGO, ou "ATIVOS (N)" do tamanho do "USINA", recolhido num `<details>` que
  abre as etiquetas no clique; e o FEITO no fim, à direita. Sem o catálogo carregado, o card não espera a carga: sem o
  campo da usina.
- **O Feito**: a barra deitada, com os segmentos inclinados de uma barra de carga (a máscara corta o recheio em faixas),
  a porcentagem e o "X de Y subtarefas": as subtarefas concluídas, a mesma conta da barra das subtarefas. O recheio é o
  da barra (`det-prog-f`, verde completa e laranja em andamento, nos dois temas); vazia sem nada feito e tracejada, com
  "—", na OS sem subtarefas.
- **O card da duração** em dois quadrados e um retângulo: a duração e, ao lado direito, a data de criação (`criada`: o
  `creation_date` do cabeçalho da OS, ou da 1ª tarefa, em Brasília: o dia grande e "às HH:MM" embaixo), cada uma no meio
  do seu quadrado, e a etiqueta embaixo das duas. A 1ª pintura do card (`_os_previa.html`) mostra a usina e a data de
  criação pela linha da lista central (`usina` e `data`).
- Prova: `tests/test_oscreator_card_usina_criacao_05_11.py`; conferido na bancada (desktop e 375 px).

## A solicitação aprovada avisa quem pediu (04/11/2026)

O aviso "Sua solicitação gerou uma OS" do sino do Nexus (`nexus/comando/avisos.py`): o `api_aprovar` do `rotas_solic`
chama o `AO_APROVAR` (que a ponte liga) com a solicitação, quem pediu (`criado_por`), a OS nascida e quem aprovou. O gancho
grava por trás e nunca derruba a aprovação; sozinho (o oem), sem gancho, nada muda. O aviso de OS executada vem da lista
central de OS (`os_central.filtrar("criadas", ...)`), sem tocar no clone.

## O Garantias sobrevive ao reinício (03/11/2026)

Levi, 03/11/2026: "Nexus > Chamados > Garantias demora muito para carregar na 1ª vez e ele é 99% Fracttal" e "tem que ser
como no OS Creator... pega a informação de um canto centralizado e mitiga essas perdas por reinício". O servidor reinicia a
cada push na `main`, e a 1ª pessoa depois dele esperava a leitura inteira (p95 de 94 s).
- **As cópias divididas vão ao disco** (`rotas_acomp`, dono "TODOS": o quadro, a lista e os tickets das concluídas), em
  `<pasta de dados do clone>/oscreator/garantias/`, que a `ponte.ligar_garantias` liga (não nos testes), escritas ao lado e
  trocadas de uma vez (`canto_disco`). Voltam no 1º uso depois do reinício com a idade que tinham, e valem as regras de
  sempre: a recente abre direto, a vencida abre e relê por trás, e quem vê outro total no Fracttal lê a dele. A cópia de uma
  pessoa só (a visão restrita) fica só na memória. Gravar nesta tela atualiza o disco; o `_esquecer` o apaga.
- **O ticket da OS concluída é lido uma vez** (`TTL_TICKET_FIM`, os 90 dias em que ela aparece, mais 1; era 30 min): concluída
  não volta e o Fracttal não aceita mais editar, e a que reabre é lida de novo.
- A lista das OS vem da lista central quando ela cobre os 365 dias (a 1ª noite depois do deploy lê a janela inteira); até lá,
  ao vivo. Prova: `tests/test_oscreator_garantias_disco.py`.

## Uma leitura só por chave, e a releitura do quadro como fundo (03/11/2026)

O Raio-X de 03/11 mostrou 828 pedidos ao Fracttal num minuto às 10h, com a cota em 200 para a empresa toda, e o
Acompanhamento de chamados com 1.851 pedidos em 49 cliques. Desde então:
- **`rotas._memo` lê uma vez por chave:** quem chega com a leitura da mesma chave em curso (o quadro logo depois de um
  deploy, que esvazia a memória) espera por ela e leva o mesmo resultado. A leitura que falha, ou que o `guardar` não guarda,
  não serve a quem esperou: ele lê com a sessão dele. O `forcar` (o Atualizar) lê sempre.
- **A releitura de 30 em 30 min do quadro é fundo declarado** (`fundo:os-web-acomp-renovar`): espera a vez do fundo no
  porteiro do Nexus e cede a vaga a quem clica; ninguém a espera, porque a tela mostra a cópia anterior.
- Até a lista central cobrir os 365 dias que o quadro lê (a 1ª noite depois do deploy lê a janela inteira), o quadro segue
  lendo a lista ao vivo. Prova: `tests/test_oscreator_memo_uma_leitura.py` e `tests/test_oscreator_acomp_renovar.py`.

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
- Na lista central de OS (31/10/2026, tarefa 3.3) a mesma regra vale de outro jeito: a leitura do servidor que falha no meio não
  troca a lista (o `os_leitor`), e cada tela confere o "Todos" que o Fracttal dá à pessoa no período, até a marca d'água,
  contra o da lista antes de mostrá-la (seção "As telas leem da lista central de OS"); a diferença manda a tela ao vivo e conta
  no Raio-X.

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
- **De onde vem o histórico (nenhuma busca a mais no Fracttal):** desde 31/10/2026 (tarefa 3.3), da lista central de OS pelo
  índice por código de ativo (`lista_central.investigar`: as OS do código do ativo e as dos códigos da usina, pelo catálogo,
  no período), depois da conferência do período carregado (a MESMA medida da Visão COS: quem abriu uma não confere de novo na
  outra), e só as que ela provou; o recorte, o "este ativo" e o "da usina" seguem as regras de baixo. Quem não passou segue
  com a lista DELA (Ruling BU da rodada 2 da 3.3). Onde a lista não cobre, como antes: a lista de "Todos" dos últimos 30 dias,
  a MESMA da
  Visão COS e do "Criado por: Todos" (`rotas.ler_lista`, que saiu de dentro do `historico` para as duas usarem a mesma
  leitura: a chave `("hist", "TODOS", "criadas", "TODOS", None, de, ate, ())` do `historico_store`, a conferência da
  mesma visão e a renovação por trás). Quem abriu a Visão COS deixa a janela pronta; a 1ª janela deixa a Visão COS
  pronta. O período DENTRO dos 30 dias é recortado da lista (pela data de criação, como o Histórico), sem pedido; fora
  deles, a lista daquele período (a régua do Histórico, guardada para quem vier depois), com o aviso na tela e o do teto
  de 2.000 quando a lista corta as mais antigas. O ↻ é o do Histórico.
- **O ativo, pelo catálogo central** (`ativos_central.atual()`, vencido também serve; nunca o Fracttal): o código que a
  plataforma manda (o gravado no de-para ou o derivado do nome) quando está no catálogo; senão, o inversor da usina com o
  mesmo número (`INVR` + N.M, sem zero à esquerda; 1.1 não casa com 1.10), com o aviso de que o código não existe (o
  derivado erra onde a árvore do Fracttal mudou, a Pharma II); sem inversor, a usina inteira, com o aviso.
- **A OS é do ativo** quando o código dele está entre os itens dela: a linha do Histórico ganhou `codigos`
  (`api._extrai_codigos`, todos os `{ ... }` dos itens; o `_extrai_code` fica só com o último), e a OS agrupada de dois
  inversores aparece nos dois. "Da usina", pelo nome curto, o do Histórico (inclui as do item da usina: religamento).
- **Os filtros da janela:** "Este ativo N | A usina inteira N", Status e Tipo de tarefa (as opções que existem nas OS da
  usina no período) e a busca por texto são locais, sobre as linhas da usina que vieram; o período re-lê no servidor. O
  nº abre o card da OS do Histórico (o mesmo `os_acoes.js`, com a 1ª pintura da lista central); a ação que muda a OS volta
  com `mudou=1` ao fechar (da lista central, sem pedido; no caminho de hoje, relê). O Esc sem card aberto
  fecha a janela do Tempo real (`{gc: "depara-fechar"}` à página de baixo).
- **Prova:** `tests/test_oscreator_investigar_ativo_26_10.py` (14: o catálogo, o número, os códigos dos itens, o
  período, a janela sem busca a mais depois da Visão COS e o contrário, o recorte, o período fora, os campos guardados,
  a usina inteira, o login e o Histórico igual depois da `ler_lista`). Na bancada (o clone sozinho em `127.0.0.1:5097`,
  Fracttal falso, rede bloqueada, dentro de uma moldura com o fundo desfocado): o escopo, o status, a busca, o vazio e o
  período (recorte sem pedido) funcionando; a caixa da busca crescia 460 px de altura (flex-basis do Histórico numa
  coluna), corrigida no `investigar.css`.
- **Levado ao oem em 26/10/2026** pela `ferramentas/sincronizar_oscreator.py --aplicar`, com o OK do Levi ("sincroniza o
  oem"): `api.py`, `rotas.py` e os quatro arquivos novos (sem commit lá: o oem é público). O 5090 só passa a servir a
  janela depois de reiniciado. Falta o olho do Levi com uma OS de verdade.

## Garantias: status do chamado, tabela, texto que quebra e quem criou (27/10/2026)

- **O status do chamado** (Levi: "Gostaria de poder mudar os status, pode ter essas opções", a lista da analista de
  chamados): `acomp_web.STATUS_CHAMADO`, na grafia dela (Testes em campo, Aguardando retorno do Cliente, do Supervisor,
  do Fabricante, Pré - Operação, Aguardando Abertura de OS, Standby, Aguardando coleta do equipamento defeituoso), mais
  o "Sem status". Mora no banco da Gridco como as observações (`chamados_obs_store`, tipo `status`: uma linha por troca,
  com quem e quando, o status em `extra` e a frase no texto, "Status: Standby", que o código de antes mostra como
  observação comum). O atual é o da última troca (`status_por_os`); sem troca nenhuma, o "Status atual" da nota da
  retroativa (`acomp_web.status_atual`). Não vai ao Fracttal. A tela do chamado tem o bloco "Status do chamado" (só no
  aberto; `POST /os/api/acomp/<nº>/status`, que recusa o que não é da lista e não regrava o mesmo), a troca entra na
  linha do tempo como evento, e conta como atualização para o pulso das paradas. No quadro, o status é o 1º chip do
  cartão.
- **A vista em tabela** (Levi: "Em garantias quero uma visão de tabela o mais enxuta e direta possível"): a troca
  Quadro | Tabela ao lado dos filtros, guardada neste navegador (`localStorage`, `acomp.vista`, posta antes da 1ª
  pintura). Uma linha por chamado, na ordem das colunas do quadro: OS, Ativo, Usina, Fornecedor, Status, Ticket,
  Situação (a coluna e os dias, curta: "Sem ticket · 35 d", "Com o fornecedor · 8 d", "Fechado 26/09"; a frase inteira
  no title) e Responsável. As linhas têm os mesmos `data-*` do cartão, e os filtros (e o filtro guardado) valem nas duas
  vistas; o clique na linha abre o chamado; a parada tem o ponto laranja que pulsa. No celular, a tabela rola dentro da
  caixa dela. Ao voltar ao quadro, as colunas são medidas de novo (escondidas, mediriam zero).
- **O texto do cartão quebra** (Levi: "não quero as OSs quebrando para os lados, pode quebrar o texto"; o ticket com a
  descrição longa fazia a coluna rolar para o lado): o `.k-chip` quebra (`overflow-wrap:anywhere`), a coluna não rola
  na horizontal, e o ticket do topo da tela do chamado também quebra.
- **Quem criou e quando** (Levi: "Em dados inclua um 'Criado por' ... e data da criação da OS"): nos Dados da tela do
  chamado, "Criado por" (o `criado_por` do detalhe da OS) e "Criada em" (a criação no Fracttal, em Brasília).
- Prova: `tests/test_oscreator_garantias_27_10.py` e `tests/test_oscreator_acomp_tabela_js_27_10.py` (o script no
  node). Na bancada (Fracttal e banco falsos): a troca do status gravada e na linha do tempo, os status no cartão e na
  tabela, o ticket longo quebrando no cartão, na célula e no topo, a 1440 e a 375 px, no escuro e no claro.

## Garantias: status geral, relatório ao cliente, exportar tabela e os filtros novos (28/10/2026)

- **O status geral é automático** (Levi: "Os gerais serão automáticos"), pelo status: Grid (Testes em campo, Aguardando
  Abertura de OS, Aguardando retorno Pré - Operação, Aguardando retorno do Supervisor), Cliente (Aguardando retorno do
  Cliente), Fabricante (Aguardando coleta do equipamento defeituoso, Aguardando retorno do Fabricante) e Standby ("stand
  by deixa de ser status comum e vira status geral", escolhido no mesmo seletor). `acomp_web.GERAL_DO_STATUS` e
  `status_geral`; o status que não é da lista (o "Status atual" da planilha antiga) fica sem geral. A tela do chamado o
  mostra embaixo do seletor; o quadro e a tabela o levam (`data-geral`, a coluna Geral).
- **Os filtros:** entra o Status geral (com "Sem status"); o Responsável (equipe ou outra pessoa) sai, e entra o
  Responsável UFV, o supervisor da usina: o Responsável O&M da ficha da usina no cadastro do Nexus. O OS Creator não
  sabe: a ponte põe em `rotas_acomp.RESPONSAVEL_UFV` a função do Nexus (`nexus/torres/chamados/ufv.py`), que roda no
  app do Nexus (o nome vem do cofre do cadastro), liga a usina pelo nome do Fracttal ou pelo código do ativo (`Ligador`,
  o código entrou na linha da lista, `api`) e guarda o cadastro 10 min. **Nunca na frente do quadro** (29/10/2026: o
  Raio-X pegou o quadro preso 30 vezes em 24 h, até 40 s, lendo o cadastro dentro do pedido): o cadastro é lido por
  trás, numa thread no app do Nexus, e o quadro só consulta a memória; sem leitura ainda, sai sem o supervisor; vencida,
  sai com a de antes e relê. A ponte pede a 1ª leitura ao criar o clone. Sozinho (o oem), sem a função, o filtro não
  aparece. O "Limpar filtros" saiu ("Tire o botão de limpar filtros"); o filtro guardado na aba do navegador continua.
- **O Status do chamado** (04/11/2026, Levi: "inclua uma filtros de status do chamado"), ao lado do Status geral: os 8
  da lista na ordem dela, o status de fora dela que estiver no quadro (o "Status atual" da planilha antiga) no fim, e
  "Sem status" (`opcoes.status` em `montar_quadro`, `data-st` no cartão e na linha, `st` no `acomp.js`). Vale no quadro e
  na tabela, e o Exportar tabela leva só o que o filtro deixa.
- **Os avisos numa exclamação** ao lado do título (o "Não consegui ler as observações" e o "N de M no nome de outra
  pessoa"), o desenho do `.hs-aviso` de Segurança > Extintores; o clique fora e o Esc fecham. O erro do Fracttal (o
  quadro sem OS) continua à vista.
- **Sem o "← Chamados" no Nexus:** a ponte tira o voltar do quadro (`ponte._SEM_VOLTAR_CHAMADOS`); no oem ele fica. O
  "← Acompanhamento" da tela de um chamado fica nos dois.
- **Exportar relatório** (`relatorio_chamados.py`, `POST /os/chamados/acompanhamento/relatorio`): um checkbox por
  cliente com chamado em andamento (o cliente do filtro vem marcado); um PDF por cliente, dois ou mais num .zip. O
  modelo é a "Atualização dos chamados de garantia" que a gestão de chamados mandava ao cliente: o resumo executivo
  (em andamento, aguardando o cliente, o fabricante, em tratativa pela Grid Co., em standby), a visão por usina com o
  supervisor, os chamados por quem precisa agir (o ticket, a usina e o ativo, o status, a última observação escrita na
  tela com a data, os dias em aberto) e os próximos passos, no visual do PDF da OS. A última observação vai ao cliente:
  quem escreve sabe disso.
- **Exportar tabela** (`POST /os/chamados/acompanhamento/tabela`, na vista de tabela): as linhas que os filtros deixam,
  na ordem da tela, numa planilha (o cabeçalho congelado e o filtro do Excel), com o cliente, o Responsável UFV e os
  dias em aberto e sem atualização a mais.
- **As observações não esperam o banco lento** (`chamados_obs_store.listar`): vencida (60 s), a leitura de antes sai na
  hora e a aba é relida por trás, uma releitura por vez, e a que falha fica com a de antes. Medido em 28/10/2026: 20,2 s
  com erro, 21,4 s e 0,8 s em três leituras seguidas; o quadro esperava isso a cada minuto, e no erro mostrava o "Read
  timed out" e desligava o pulso e o status. Só a 1ª leitura (sem nada guardado) e o Atualizar esperam.
- Prova: `tests/test_oscreator_garantias_28_10.py`, `tests/test_oscreator_acomp_tabela_js_27_10.py` (os filtros no
  node). Na bancada: a exclamação, os filtros (Fabricante, Standby, um supervisor), o diálogo com um checkbox por
  cliente, o relatório (um PDF; dois clientes, um .zip) e a planilha; a 375 px a página não rola para o lado e a caixa
  dos avisos fica na tela.

## Garantias: os filtros no modelo do Histórico (05/11/2026)

Levi: "quero que os filtros dos chamados sejam no estilo OS CREATOR WEB > HISTÓRICO", "algo suspenso e moderno, do jeito
que está está ocupando muito espaço na tela!". A linha de seis `<select>` sublinhados virou o modelo A do Histórico (seção
"Os filtros do Histórico só valem no Aplicar"), com o MESMO CSS (`os.css`, as classes `fl-*` e as cores `--fl-*`, nos dois
temas): nenhuma cor nova, e o `chamados.css` só põe o respiro, o foco azul da barra (o `body.cham :focus-visible` verde
venceria) e o celular.
- **A barra, numa linha:** a busca (filtra enquanto se digita, sem Aplicar), o botão **Filtros** com a contagem em lima dos
  campos aplicados (a busca não conta) e, à direita, o Quadro | Tabela (o controle segmentado, a vista de agora em azul) e o
  Exportar tabela (só na tabela). A 375 px: a busca na 1ª linha; Filtros, Quadro | Tabela e o Exportar só com o ícone na 2ª.
- **O painel suspenso**, preso ao botão Filtros (a borda esquerda na dele), com Fornecedor, Cliente, Tipo de ativo, Status
  geral, Status do chamado e Responsável UFV em 2 colunas: listas de MARCAR VÁRIOS (vários valores num campo = qualquer um
  deles), todas digitáveis (`data-busca="1"`: o `os_busca.js` põe a caixa de busca). "Sem status" e "Sem responsável UFV"
  (`_sem`) no fim da lista deles. O campo que mudou ganha o ponto lima; o rodapé diz "N alterações" e o **Aplicar** só
  acende com alteração. Fechar sem aplicar (clique fora, na captura; Esc, que fecha antes a lista aberta; o botão de novo; o
  × da folha) DESCARTA. Com menos de 640 px o painel vira a folha de baixo para cima do Histórico.
- **As etiquetas** (uma por campo aplicado: "Fornecedor STI", "Status do chamado 2 selecionados") ficam abaixo da barra, e o
  × tira aquele campo e aplica na hora. **Sem o Limpar** do Histórico (28/10/2026: "Tire o botão de limpar filtros").
- **Guardado na aba** como antes (`acomp.filtros` no `sessionStorage`), agora com uma lista por campo; o guardado de antes
  (um valor por campo) vale como lista de um, e o valor que saiu da lista não vira filtro. O Exportar relatório abre com os
  clientes do filtro aplicado marcados.
- **Prova:** `tests/test_oscreator_garantias_filtros_05_11.py` roda a página de verdade no node, com o DOM de mentira do
  Histórico (`tests/historico_pagina_falsa.js`, que ganhou o `script_js`: o script da página num arquivo, o `acomp.js`). Os
  testes de filtro do DOM montado à mão (24/10 e 27/10) foram para lá; a rolagem, a troca de vista e o clique na linha
  ficaram onde estavam. A tela foi conferida na bancada, a 1280 e a 375 px.

## Garantias: editar e excluir as observações (29/10/2026)

Levi: "Em garantias > clico na OS > Em observações da OS gostaria de poder excluir a observação e editar a observação";
quem pode: "qualquer um que é ADM ou do setor de chamados".

- **O banco continua só acrescentando** (`chamados_obs_store`): editar grava uma linha `edicao` com o texto novo e excluir
  uma `exclusao`, as duas apontando a original em `extra.de`; a original nunca muda. A tela mostra a versão em vigor
  (`vigentes`: a editada com o texto da última edição e a marca "editada dd/mm HH:MM por …", na data em que foi escrita;
  a excluída some). O quadro (a última atualização, o pulso), o status e o relatório ao cliente leem a versão em vigor.
- **Só a observação escrita** muda; ticket, status, finalizado e a chegada da OS, os automáticos, não têm os botões, e a
  rota recusa (400). Editar ou excluir a que já foi excluída: 404.
- **O histórico importado da retroativa também** (Levi, no mesmo dia: "não foi viu", no clique numa linha "Histórico
  importado na nota"): a linha vem da nota da OS no Fracttal, que não muda; cada linha tem a chave da data e do texto
  (`acomp_web.chave_do_historico`, "h-...") e a edição ou a exclusão fica no banco do Nexus por cima dela
  (`chamados_obs_store.ajustes_do_historico`; `rotas_acomp._mexer_historico` confere que a chave está na nota de agora).
  Se a nota mudar a linha, a chave muda e o ajuste de antes deixa de valer para ela.
- **Quem pode** o Nexus decide (`ponte.obs_chamados`: o administrador ou quem é do setor Performance, a mesma regra da
  Área PCM, `ponte._do_setor_ou_admin`; até 05/11/2026 era o setor Chamados, que o Levi excluiu, pondo as pessoas dele
  na Performance: "Sim, passa", para o setor inteiro) e põe no pedido (`os_web.obs_chamados`), só na tela de um chamado e nas rotas de
  editar e excluir (`ponte._ROTA_OBS`: o quadro não paga a leitura do setor). Quem não pode não vê os botões e recebe 403
  com o aviso. Sem a chave (o oem, sozinho), fica aberto, como a Área PCM.
- **A tela:** o clique na observação escrita mostra o "editar" e o "excluir" dela (Levi: "clica no comentário e aparece
  esses botões"; outro clique esconde, e a outra aberta fecha); o editar abre a caixa no lugar (salvar ou cancelar), o
  excluir pergunta antes; gravado, a tela relê. A observação nova (salva sem recarregar) já vem com os
  botões.
- Prova: `tests/test_oscreator_garantias_obs_29_10.py`. Na bancada: editar (o texto novo e a marca "editada") e excluir
  (some da tela, as duas linhas gravadas no banco falso), a 1440 e a 375 px.
- **Os arquivos da tela com a versão no endereço** (`estatico()`, um global do Jinja em `os_web/__init__.py`): o
  `acomp.js`, o `chamados.css` e o `os_acoes.*` das telas de Garantias vão com `?v=<a hora em que o arquivo mudou>`. O
  /os/static sai sem prazo de cache e o navegador chutava um: em 29/10/2026 o editar e o excluir subiram e a tela do Levi
  seguiu com o acomp.js de antes até o Ctrl+Shift+R. Tela nova com JavaScript que muda, use `estatico()`.

## O que a tela pede sozinha leva o X-Nexus-Auto (31/10/2026, etapa 0 do canto central)

O Nexus mede o uso das telas do OS Creator por hora (`nexus/casca/uso_os.py`, seção "Uso das telas do OS Creator por hora"
do `nexus/casca/CLAUDE.md`) e separa o clique da pessoa do que a tela pede sozinha. Quem se renova sozinho avisa:
- **`acomp.js`** (`esperarANova`, de 5 em 5 s por até 3 min) manda `X-Nexus-Auto: 1` no `fetch` do
  `/os/chamados/acompanhamento/estado`;
- **`solic_pcm.js`** `pedir(url, corpo, texto, auto)` põe o cabeçalho só com `auto === true` (um evento de clique repassado
  sem querer não vale), e o **`solic_hist.js`** chama `recarregar(true)` só na atualização de 15 min; o ↻ é `recarregar(false)`.
  A página `solic_hist.html` chama os dois arquivos por `estatico()` (com a versão), senão o navegador seguiria com os de antes;
- **`historico.html`** (a atualização de 10 min é `form.submit()`, e um formulário não manda cabeçalho): `enviar(forcar, auto)`
  põe o campo escondido `nx_auto=1` só nesse envio e o tira em todo outro; a página carregada apaga o `nx_auto` do endereço
  (`history.replaceState`), para o recarregar do navegador ou o link copiado serem cliques;
- **`carga.js`**, o círculo de carga, pergunta o `/os/historico/progresso` de 350 em 350 ms enquanto o Histórico busca: o
  `fetch` leva o cabeçalho (sem ele seria, por folga, a rota mais clicada);
- a conferência da sessão de 5 min (`/os/_nexus/sessao`) é do Nexus (`nexus/templates/_confere_sessao_js.html`).
O oem (congelado) não recebe estes arquivos: nada muda no 5090. Tela nova que
se renova sozinha põe o cabeçalho; sem ele conta como clique.

## As subtarefas padrão de cada atividade da Performance (05/11/2026)

Levi: "Quero que no OS Creator > Performance tenha um campo para subtarefas, que vamos poder editar as subtarefas padrões de
cada atividade!"; "Quando criamos uma OS as atividades já vem com aquelas subtarefas"; quem muda: "Qualquer um"; e no mesmo
dia, "quero que dê para editar o tipo de tarefa também!".
- **A tela:** o card 4 da tela de criar OS da Performance, "Tipo e subtarefas da atividade", mostra o tipo de tarefa e a
  lista que a OS leva e de onde vêm ("Do plano do Fracttal" ou "Padrão do Nexus, salvo por X em ..."). O Editar muda o tipo de
  tarefa (os do `api.TASK_TYPE_MAIN`; sem padrão, o do plano com o do app: a inspeção do inversor, Corretiva) e, em cada
  subtarefa, o texto, o tipo (os do editor de Temas: texto, sim/não, verificação, numérico; o que o editor não monta, como a
  lista de opções, fica "do plano"), o "exige anexo" e a ordem, tira e acrescenta. **Salvar padrão** vale para toda OS nova
  da atividade, para todo mundo (escrito ao lado do botão, sem janela de confirmação); **Voltar ao do Fracttal** desfaz. O
  resumo do plano (card 3) diz o tipo do padrão.
- **A tela inicial da Performance:** o card da atividade conta o padrão salvo, e o "ver lista" (onde o Levi procurou o
  editor) mostra o tipo e a lista em vigor e o botão **Editar as subtarefas**, que abre a atividade com o editor já aberto
  (`?subtarefas=editar`).
- **Onde mora:** o livro `nexus_subtarefas_performance · fato_versao_subtarefas`
  (`nexus/torres/oscreator/subtarefas_padrao.py`, no catálogo de dados), uma linha por versão salva, com quem salvou (o
  código do e-mail; o nome só cifrado). A ponte liga o gancho (`perf_web.SUBTAREFAS_PADRAO`); sem ele, a lista é a do plano e
  não se salva (503). O plano do Fracttal não muda: ele é de outra área e vale para quem cria OS por fora.
- **Na criação** (uma OS por ativo e agrupada): o padrão salvo vai no lugar das subtarefas do plano e das do app
  (`os_planos.com_subtarefas_padrao`), cada uma na forma da subtarefa do plano de onde veio (a `origem`: o tipo, as opções e
  a unidade ficam quando o tipo não mudou), o tipo de tarefa do padrão no lugar do do plano (`os_planos.com_tipo_padrao`; a
  coluna `tipo_tarefa` do livro, vazia = o do plano), e a OS segue ligada ao plano. Se o Fracttal recusar, a OS sai com as do plano e
  a tela diz (a rede de segurança das extras). Sem conseguir ler o padrão, a OS sai com as do plano e a tela também diz.
- Prova: `tests/test_oscreator_perf_subtarefas.py`; a tela conferida numa bancada (desktop e 375 px); e no ar, em
  05/11/2026, em TESTE - PA: com um padrão de teste da Inspeção Geral do Inversor (a 1ª renomeada, a 2ª de Verificação para
  Sim/Não, a última do plano fora e uma nova no fim), a OS 18600 nasceu com essa lista, na ordem, lida de volta; o padrão
  voltou ao do Fracttal e a OS foi cancelada. O plano real tem 9 subtarefas, todas com `origem` (o `id` do item do plano).
  O tipo de tarefa, no mesmo dia: com o padrão de teste em Inspeção (o do app é Corretiva), o resumo do plano disse "Tipo:
  Inspeção" e a OS 18625 nasceu com o tipo Inspeção, lido de volta; o padrão voltou e a OS foi cancelada. A 1ª gravação
  depois da coluna `tipo_tarefa` regravou o livro com ela, sem recusa.
