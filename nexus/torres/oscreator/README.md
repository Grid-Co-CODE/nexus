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
  endereço do card dele na tela inicial do OS Creator.
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
- **Testes:** `tests/test_torre_oscreator.py`, `tests/test_oscreator_solic_engenharia.py` e
  `tests/test_oscreator_busca_digitavel.py`. Nenhum teste fala com o Fracttal.
- **O que não funciona igual:**
  - o login pelo OAuth do Fracttal tem a volta configurada para o supervisório; e-mail e senha funcionam normal;
  - gravar ticket precisa do `GRIDCO_SQL_TOKEN`, que vem da variável ou do `%APPDATA%` da máquina.

## Nova solicitação: PCM ou Engenharia (06/10/2026)

O pedido do Levi, de 06/10: em "Nova solicitação" aparecem duas opções. **PCM** continua criando a solicitação do
Fracttal (`/os/solicitacao`). **Engenharia** é uma tela nova (`/os/solicitacao/engenharia`), no estilo de
Performance > Geração e ETM > ETM, só que liberada para todos os ativos. As duas telas têm no topo o seletor
PCM | Engenharia. As duas são do mesmo setor das abas (`/os/solicitacao`), então o seletor troca a tela na mesma
aba, sem abrir outra.

- **O que a Engenharia cria:** uma OS por ativo marcado. **Não** cria uma solicitação. Segue o molde da OS de análise
  (`api.create_os_analise`):
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
  - título `[Ativo] - Descrição`, montado pelo `perf_os_nome` em cada ativo;
  - a "Descrição" é a atividade que o solicitante escreve, com o subtexto "Atividade a ser realizada (de forma
    direta)";
  - o "Descreva o problema" (obrigatório) vai na observação da OS (`note`).

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
- **Como provar:** `tests/test_oscreator_solic_engenharia.py` (12 testes, catálogo e pessoas sintéticos, sem rede).
  Na bancada, com o criar de mentira, foram conferidos:
  - 353 ativos de uma usina do catálogo;
  - "nob" no tipo → Nobreak;
  - a data só exibida, com o Urgente trocando 13/10 por 08/10;
  - o pedido saindo sem data e a resposta com a data do servidor;
  - as recusas do servidor (sem ativo, sem nome, sem problema, responsável de fora);
  - o seletor nas duas telas.

  **Falta a prova ao vivo** pedida no `CLAUDE.md` do OS Creator: uma OS de verdade em `TESTE - PA`, conferida campo a
  campo no Fracttal e cancelada no fim.

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
- **O que é só do Nexus vai na `ponte.py`, nunca na cópia** (a cópia vai para o supervisório, que não tem o Nexus):
  a cópia não pode importar o pacote `nexus`, e a ferramenta recusa se importar. O
  `tests/test_torre_oscreator.py` acusa quando a cópia e o oem divergem (só na máquina que tem o oem).
- Usa a mesma pasta de dados do OS Creator (`%APPDATA%\CriarOS-Fracttal`). Na mesma máquina, ele divide com o
  supervisório a chave da sessão e o token do banco.
- Precisa do PyQt6 instalado, porque a tela de Engenharia importa `steps/engenharia`, que puxa `steps/ui.py`.
