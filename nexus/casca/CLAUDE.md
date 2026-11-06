# CLAUDE.md — casca (moldura, login, menu e tema)

O que envolve todas as torres: o layout, o portão de login, quem é administrador e o que cada setor vê (a tela
Base → Acessos), o tema (escuro ou claro) e o `/saude`. A cadeira saiu em 12/10/2026: os setores a substituíram.

## Os arquivos

| Arquivo | O que faz |
|---|---|
| `nexus/__init__.py` | `create_app`: lê o `.env`, o cookie `nexus_sessao`, o prefixo, instala o portão e o contexto, descobre as torres |
| `nexus/prefixo.py` | o caminho em que o Nexus é servido (`NEXUS_PREFIXO`): o middleware, `na_raiz`/`sem_raiz` e o cookie no caminho certo |
| `nexus/templates/_raiz_js.html` | `window.NEXUS_RAIZ` e `nexusRota()` para o JavaScript, no `<head>` de base, entrar, modo TV e card da OS |
| `nexus/config.py` | `OBRIGATORIAS` (sem elas o app não sobe e diz qual falta) e `OPCIONAIS` |
| `nexus/casca/__init__.py` | `/` (Início, só com as torres do setor, e o cartão "Versão no ar"), `/tema` (troca sem JavaScript), `/saude` (`{"commit", "ok"}`) e o contexto dos templates (menu pelo setor, `setor`, `tema`) |
| `nexus/casca/versao.py` + `templates/atualizacoes.html` | o cartão "Versão no ar" do Início (a hora do commit, o commit, desde quando está no ar) e a aba Atualizações (`/?aba=atualizacoes`, só novidade, correção e desempenho dos últimos 60 dias, por dia); seção "Versão no ar e Atualizações" abaixo |
| `nexus/casca/sugestoes.py` + `templates/sugestoes.html` | a aba Sugestões (`/?aba=sugestoes`): o formulário de todos e a lista do administrador, o livro `nexus_sugestoes` e os anexos no disco; seção "Sugestões no Início" abaixo |
| `nexus/casca/presos.py` | os pedidos presos: o que cada pedido esperava quando o Nexus parou de responder, no log (o cartão do Início saiu em 13/10; seção "Pedidos presos" abaixo) |
| `nexus/casca/fracttal_conta.py` | o contador de pedidos ao Fracttal (31/10/2026): um gancho no `Session.send` que soma, por hora de Brasília × origem × método, os pedidos, as recusas (406/429), os erros, o pico por minuto e as esperas; e, no mesmo gancho, o porteiro (etapa 5): o Nexus até 150 pedidos por minuto, o fundo até 90; seção "Pedidos ao Fracttal" abaixo |
| `nexus/casca/minutos_ocupados.py` | os minutos de toda hora que já têm dono no Nexus, num lugar só (31/10/2026, etapa 3 do canto central), e os de uma vez por dia (`DIARIOS`): o laço novo pede o próximo minuto livre (`proximo_livre`); bullet "Os minutos ocupados" na seção do Raio-X abaixo |
| `nexus/casca/uso_os.py` | o uso das telas do OS Creator (31/10/2026): por hora × rota × automático, os pedidos, as pessoas distintas, a mediana e o p95, os erros, os 503 do teto e os pedidos ao Fracttal; marca a rota de TODO pedido do Flask como origem do contador do Fracttal; e, no servidor, guarda as horas fechadas dos dois contadores no disco a cada hora (:05) e as leva ao banco UMA vez por dia, às 04:45 (`nexus/dados/fato_uso_os.py`); seção "Uso das telas do OS Creator" abaixo |
| `nexus/auth/__init__.py` | `/entrar` (a porta, a senha de administrador e a ida e a volta da Microsoft), `/sair` (com a porta única ligada, passa pela plataforma: `templates/sair.html`) e o portão (`before_request`) |
| `nexus/auth/microsoft.py` | o login pela conta Microsoft da Grid (Entra ID), desligado sem as quatro `NEXUS_MS_*` (seção "Entrar com a Microsoft" abaixo) |
| `nexus/auth/fracttal.py` | o login pelo Fracttal: o `api.fracttal_login` do clone do OS Creator; abre também o cookie `os_sessao` (/os) |
| `nexus/auth/acessos.py` + `telas_acessos.py` | os administradores dados pela tela Base → Acessos, a auditoria e quem entrou em 30 dias (`templates/acessos/acessos.html`; seção "Acessos" abaixo) |
| `nexus/auth/telas_admins_app.py` + `templates/acessos/_admins_app.html` (+ `_admins_app_explica.html`, o "!" do título) + `static/acessos-admins-app.js` | a aba Administradores do App de Campo de Base → Acessos (05/11/2026; o dado em `nexus/pcm/admins_app.py`; seção "Acessos" abaixo) |
| `nexus/auth/setor_telas.py` + `templates/sem_setor.html` | o que cada setor vê: o portão por setor e o menu filtrado (seção "Telas por setor" abaixo) |
| `nexus/auth/pre_carga.py` | a pré-carga das telas de quem tem setor (seção "Pré-carga" abaixo) |
| `nexus/templates/base.html` | a moldura: o topo (a ação da tela no bloco `topo_acoes`, o sino e quem entrou, que abre o menu da conta com o Setor, o Tema e o Sair; seção "Um cabeçalho só"), menu lateral, recolher (`[` ou botão, lembrado em `localStorage` `nexus.menu`; no trilho recolhido, passar o mouse
ou focar o ícone abre ao lado a caixa `menu-voo` com o nome da torre e as telas dela, os mesmos links do menu,
e o clique no ícone segue levando à 1ª tela; 05/11/2026, Levi: "ao passar o mouse aparecesse as opções daquela
área"), menu do celular, botão do tema (que troca também as molduras do OS Creator abertas) |
| `nexus/templates/_icone.html` + `static/grid-icone-branco.png` | o ícone da aba do navegador (24/10/2026, Levi: "o logo branco da grid"): o símbolo branco sobre o navy do Nexus (só branco sumiria na aba clara do navegador), no `<head>` de base, entrar, sair e os dois modos TV; feito do `grid-icon.png` do OS Creator, 256 px |
| `nexus/templates/_tema_cabeca.html` | o script do tema no `<head>` (base, entrar e os dois modos TV): a reserva do `localStorage` antes de pintar |
| `nexus/templates/_entrar_de_novo_js.html` e `_confere_sessao_js.html` | o `window.nexusEntrarDeNovo` (a janela ao login quando a sessão acaba) e a conferência da sessão do Fracttal a cada 5 minutos (só `session.usuario`). Saíram do `base.html` sem mudar (11/10/2026) para o modo TV do Painel NOC, que não tem a casca, valer igual: a TV de quem saiu do Fracttal vai ao login |
| `nexus/static/nexus.css` | os tokens do Design System Grid Co. nos dois temas e o subconjunto `gc-*` |
| `app.py` / `servir.py` | desenvolvimento (5070, IPv4 e IPv6, cookie sem Secure) / produção (atrás do proxy, cookie Secure) |
| `ferramentas/subir_copia_de_prova.py` / `ferramentas/porta_local.py` | cópia de prova noutra porta (sem carga, sem Fracttal ao subir, trava de rede) / o papel do Caddy no PC, Nexus e plataforma numa origem só; só repassa, sem pote de cookies (10/10/2026: o pote guardava o `session` de uma resposta e o dava a quem chegasse sem cookie; `tests/test_porta_local.py`) |

## O prefixo `/nexus` e o cookie próprio (porta única, 09/10/2026)

Levi: "a partir de segunda quero o Nexus como link principal; o Nexus será o centro de tudo". O servidor serviu o Nexus em
`app.gridco.com.br/nexus`, ao lado da plataforma de Performance na raiz, até a fase 4: **hoje ele está na raiz de
`app.gridco.com.br`** (sem `NEXUS_PREFIXO`; o `/nexus/...` antigo devolve 308 para o mesmo caminho na raiz; conferido de
fora em 14/10/2026, `DEPLOY.md` seção 5b). O prefixo segue no código porque é a volta (spec `docs/superpowers/specs/2026-10-09-performance-no-nexus-design.md`,
seções 2 e 5.1). Até 09/10 o código não sabia do `/nexus`: o menu, o Início, o Sair e os `fetch` saíam da raiz e caíam
na plataforma, e o cookie `session` dos dois sistemas (mesmo nome, mesmo caminho) se apagava a cada login.

- **Cookie (passo 0):** `nexus_sessao` (nunca mais `session`, o da plataforma), no caminho em que o Nexus roda
  (`SessaoNoPrefixo`: `/nexus` no servidor, `/` na raiz); o `os_sessao` do OS Creator embutido em prefixo + `/os`
  (`auth.os_cookie_path`, e o `_SessaoDoClone` da ponte). Efeito único da troca: quem estava logado entra de novo uma vez.
  Debaixo do prefixo, o Sair e o Entrar apagam também um `nexus_sessao` de `Path=/` que tenha sobrado da janela entre
  publicar o código e pôr a variável (`auth._sem_a_sessao_velha_da_raiz`; revisão de 10/10/2026: ele seguia válido e a
  pessoa saía e continuava logada).
- **Prefixo:** `NEXUS_PREFIXO` (`.env` ou ambiente; vazio = raiz: o PC e o servidor desde a fase 4,
  `DEPLOY.md`, seção 5b). O `create_app` põe o middleware
  `Prefixo`: `SCRIPT_NAME` = prefixo, e o prefixo sai do `PATH_INFO` só quando vem (serve com o Caddy cortando o `/nexus`,
  `handle_path`, e sem cortar). O `X-Forwarded-Prefix` do pedido NUNCA é lido (o Caddy repassa o do cliente). Sem a
  variável, a resposta na raiz é a de antes: conferido em 09/10 página por página (135 páginas, mesmo status, mesmo
  Location, mesmos href/src/action; só o JavaScript do `nexusRota` e o nome do cookie mudaram).
- **Como cada endereço sai com ele:** template = `{{ raiz }}/t/...`, `url_for` ou `{{ x.url|na_raiz }}` (o que vem
  montado do Python); Python = `na_raiz("/t/...")` em todo `redirect` (e `destino_seguro` para `next`/`voltar`);
  JavaScript = `nexusRota("/t/...")`. Os três são IDEMPOTENTES: o que já começa com o prefixo não ganha outro. O `next`
  do portão vai como o navegador vê (`/nexus/t/...`); um `next` sem o prefixo também volta certo.
- **A camada da T.I.:** o servidor tem, FORA do repositório, uma camada que reescreve a resposta (o `Location` e os
  caminhos do Nexus no HTML e no JavaScript ganham `/nexus`, e um calço põe `/nexus` em todo `fetch`). Ela não mexe no
  que já sai com `/nexus`, e o `nexusRota` não dobra o que ela reescreveu: com a variável ligada e a camada ainda ativa,
  nada sai `/nexus/nexus` (`test_com_a_reescrita_do_servidor_ligada_nada_sai_com_o_prefixo_dobrado`). Na fase 4 ela
  saiu junto (em 14/10/2026 o HTML do servidor já não trazia `/nexus/`). Local: `ferramentas/porta_local.py
  --reescrita-do-servidor` a imita. O `/saude` do servidor já respondeu um commit enquanto os estáticos eram de outro: lá ele
  não prova versão sozinho.
- **O `nexus_tema` fica em `/`** (o botão grava pelo navegador; nome próprio, não colide).
- **Endereço da PLATAFORMA é outra coisa** (porta única, 09/10/2026): as molduras da Performance escrevem, de propósito, endereços da plataforma na raiz (`/painel/nexus/entrar`, `/painel/nexus/sair` e até 11/10/2026 as telas do mapa, como `/tempo-real` no "Abrir em outra aba", que saiu), porque ela mora na raiz ao lado do Nexus. Esses não levam `{{ raiz }}`: no template a variável se chama `plataforma` (`{{ plataforma }}/painel/nexus/entrar`, que o varredor estático aceita) e o rastreador os separa (`da_plataforma`). No JavaScript, a plataforma se pede por URL completa (o calço da camada da T.I. poria `/nexus` num `fetch("/api/...")`). Regra em `nexus/performance/CLAUDE.md`, seção "Porta única".
- **Prova:** `tests/test_prefixo.py` (o rastreador `tests/rastreador_de_links.py` percorre todas as páginas a partir do
  Início, logado como admin e no OS Creator embutido, nos modos Caddy cortando, sem cortar, `SCRIPT_NAME` por outro meio e
  raiz, e falha com qualquer endereço interno fora do prefixo; mais o varredor estático de templates, `.js` e `redirect`).

## Tema escuro (padrão) e claro (08/10/2026)

Levi: "Construa um visual claro, está com um dark navy, acho foda, porém precisamos de um tema claro também, faça com
calma para que não ocorra bugs!". O escuro navy segue o padrão e **não mudou nada**; o claro é escolha de cada pessoa.

- **Tokens:** dois blocos no `nexus.css`. `:root,:root[data-tema="claro"] .topo` é o escuro (o `.topo` repete o escuro
  dentro do claro: o cabeçalho fica navy com o logo branco nos dois temas) e `:root[data-tema="claro"]` é o claro, na
  identidade do site (texto #1f2937). Desde 04/11/2026 o cartão é cinza sobre a página branca, o espelho do escuro (Levi:
  "o fundo claro podemos ter o fundo claro e os cards um pouco mais escuros, indico um cinza claro"; e "um cinza um pouco
  mais escuro"): página #ffffff, cartão #e9ecf1, hover #e3e7ed, o tom mais fundo #dde2e9; o mudo, o fraco e as palavras
  do semáforo (ok, crítico, info, sem comunicação) escurecidos para seguir em 4,5:1 nesses cinzas (o test_tema cobra).
  Comparar os dois temas: **Paleta Nexus** (`/t/base/paleta`: o Caddy só manda ao Nexus a raiz, `/t/*` e poucos outros; só administradores, no menu da conta; `paleta_tokens.py` lê os
  dois blocos do nexus.css a cada abertura). Todo token tem valor nos dois. As
  outras folhas (`campo`, `pcm`, `cadastro`, `dados`, `engenharia`, `clima`, `clima-mapa`) não têm cor nenhuma, só
  `var(--token)`; os tokens locais delas (`--cl-*`, `--pg-*`, `--mp-*`) apontam para os globais.
- **REGRA: cor só por token.** Cor nova = token novo nos DOIS blocos, com o valor do escuro e o do claro; nada de
  `#hex`/`rgba()` em regra de CSS nem em `style=`, `<style>` ou `fill=` de template. No escuro, cada transparência que
  uma tela usava virou token com o alfa no nome (`--alerta-a08` é o âmbar a 8%): foi assim que o escuro ficou idêntico.
  Severidade como TEXTO usa o token simples (`--critico`); como ÁREA (barra, borda grossa de destaque, preenchimento com
  texto escuro em cima) usa o `-cheio` (no escuro é o mesmo valor; no claro, o tom médio, porque o de texto é escuro
  demais e o âmbar virava marrom). Verde em texto no claro é o musgo `--verde-texto` (#566610); o #a9db21 só como
  superfície (o puro dá 1,6:1 no branco).
- **No claro nada esmaece por opacidade** (linha concluída, aposentada ou aprovada, cartão cancelado, nível não marcado):
  a opacidade do escuro derrubava o texto a 2,4–3,5:1 no branco. Vira cinza de seção (`--superficie-2`) com texto
  `--mudo`, numa regra `:root[data-tema="claro"] ...` ao lado da do escuro em cada `.css`.
- **Como o tema chega:** cookie `nexus_tema` (`escuro` ou `claro`; 1 ano, `Path=/`, `SameSite=Lax`, sem `HttpOnly`
  porque o botão grava pelo navegador). O servidor desenha o `<html data-tema>` (`casca.tema_do_pedido`, no contexto
  de todo template, inclusive `/entrar` e o erro da ponte da Performance): a página já nasce no tema certo, sem piscar.
  Reserva: `localStorage` `nexus.tema`, aplicada pelo `_tema_cabeca.html` antes de pintar quando o cookie sumiu (e o
  cookie volta). Cookie desconhecido ou ausente = escuro. Não segue o tema do sistema operacional, de propósito.
- **O botão:** no menu da conta (desde 03/11/2026; seção "Um cabeçalho só"), "Tema: Escuro" / "Tema: Claro" (diz o
  de agora; o ícone, um meio círculo, é desenhado no CSS, `.tema-icone`), sempre com o rótulo. Troca na hora, sem
  recarregar e sem fechar o menu, grava cookie e `localStorage`, e outra aba aberta acompanha (evento `storage`). Sem
  JavaScript é um formulário: `POST /tema` (`tema`, `voltar` com os filtros da tela) grava o cookie e volta. Com o
  movimento reduzido do sistema a troca é seca; sem ele, um esmaecer de 0,18 s (View Transitions).
- **O OS Creator embutido segue o tema** (Levi, 09/10/2026: "faltou o tema claro do OS Creator Web, não está
  sincronizando com o botão do Nexus"): a ponte desenha o `data-tema="claro"` no `<html>` das páginas do clone pelo mesmo
  `tema_do_pedido` (no escuro, sem o atributo), o card da OS (`card_os.html`) idem, e o botão troca ao vivo as molduras
  abertas do `/os/` (`temaNasMolduras`, no `base.html`; moldura dentro de moldura). As cores do claro moram no próprio
  clone, no par `:where(html[data-tema="claro"])` de cada `.css` dele, com a paleta `--osc-*` igual à do claro daqui (o
  oem sozinho nunca recebe o atributo). Como e por quê: `nexus/torres/oscreator/README.md`, seção "Tema claro".
- **Fica no escuro, de propósito:** a página da Plataforma no Tempo real (é outro sistema). A foto ampliada é sempre
  escura (no Nexus e no visor do card da OS) e a assinatura sempre em papel branco, nos dois temas (`--foto-*`,
  `--papel-*`). Cores de DADO (a da pessoa no Quadro da equipe, a da etiqueta do Fracttal) são as mesmas nos dois
  temas, com texto escuro por cima; no OS Creator, a cor do dado usada como TEXTO é pintada no claro com a luminosidade
  no teto (o README de lá).
- **Prova:** `tests/test_tema.py` (cookie e atributo, botão, `POST /tema`, os dois blocos com os mesmos tokens, o escuro
  congelado em `ESCURO_DE_SEMPRE`, nenhuma cor fixa nos `.css` e templates, todo `var()` existe, contraste AA de cada par
  de texto do claro) e, para o OS Creator, `tests/test_oscreator_tema_claro.py`. Na tela, ao mexer em cor: as telas
  principais nos dois temas, a 1440 e a 375 px, no Chrome sem janela, medindo o contraste de todo texto visível contra o
  fundo efetivo, a rolagem lateral e os erros de JavaScript, e as cores computadas do escuro comparadas com as de antes,
  elemento a elemento.

## Acessos: quem é administrador (Base → Acessos, 11/10/2026)

**Três abas:** Telas e administradores (o que está abaixo), Pessoas e setores (desde 25/10/2026, a antiga Base →
Integração Fracttal: o pessoal do Fracttal e o setor de cada um; regras em `nexus/cadastro/CLAUDE.md`) e Administradores
do App de Campo (desde 05/11/2026, `?aba=admins_app`; bloco no fim desta seção). A segunda lê o Fracttal; a terceira usa só a
cópia dela (`telas_fracttal.copia_sem_esperar`: nunca lê na hora, pede a leitura nova por trás); a primeira não lê. O
"Como vale." da aba de telas e o da dos administradores do App (e o da tela Chaves do Nexus) moram no "!" do título
(2ª revisão de 05/11/2026: eram avisos soltos na tela; `tests/test_explica_padrao.py` pega o `<strong>` agora).

Pedido de 11/10/2026, na véspera de o Nexus virar a porta principal: "Tem algum canto do Nexus onde eu posso administrar
isso?". Até então administrador era só a `NEXUS_ADMINS` do `.env` do servidor (pôr ou tirar alguém = a T.I. editar e
reiniciar) ou a senha de administrador. A tela `/t/base/acessos` (só administrador; quem não é vê a página "só para
administradores" do Cadastro, `cadastro/sem_permissao.html` com `area`) mostra e muda:

- **Administradores = `NEXUS_ADMINS` ∪ a lista da tela** (`auth._admins`). Os do servidor aparecem "do servidor", só
  leitura, e a tela não os tira (são a garantia de que sempre há administrador, mesmo com o arquivo apagado). Os da tela
  ("pela tela") têm quem deu e quando, e o botão Tirar. Quem tira a si mesmo marca a confirmação, e não pode se for o
  último da tela. A senha de administrador não é pessoa: vale sempre, até o Sair.
- **Vale no próximo clique da pessoa**, sem sair e entrar: o portão confere o `admin` da sessão que nasceu do Fracttal
  contra a lista de AGORA a cada pedido (`auth._admin_em_dia`; um `stat` por pedido, o arquivo só é relido quando muda).
  Antes, o `admin` era gravado só no login e durava a sessão (12 h). Limite conhecido: nas telas da Performance, a sessão
  que o passe já abriu na plataforma guarda o `admin` de antes até a moldura renovar (no máximo 11 h). Vale também para a
  NEXUS_ADMINS: tirada do `.env` e reiniciado o serviço, a pessoa deixa de ser admin no clique seguinte.
- **Registro (auditoria)** de quem deu ou tirou, quando (UTC no arquivo, Brasília na tela), as últimas 1.000.
- **Quem entrou nos últimos 30 dias:** todo login certo grava só o e-mail (ou "senha de administrador") e a hora, no
  `acessos_logins.json`; o mais antigo que 30 dias sai, e o teto é de 500 pessoas (as mais recentes). Falha ao gravar
  nunca impede a entrada (vai ao journal).
- **Onde mora:** `acessos.json` e `acessos_logins.json` na pasta de dados do Nexus (`NEXUS_DADOS`; sem ela, a mesma
  padrão do cadastro e do de-para: `C:\GridcoAuto\nexus` no PC, `dados/` no servidor), fora do git. **Não vai ao banco,
  de propósito:** é configuração de acesso desta instalação, não dado de negócio para cruzar com os setores; no banco
  compartilhado ela seria lida por outros sistemas e o Nexus dependeria dele no ar para alguém conseguir administrar. É a
  exceção consciente à regra "nada de JSON como banco" da raiz. Entra na cópia diária da `dados/` (`DEPLOY.md`).
- **Escrita atômica e com trava:** temporário na mesma pasta + `fsync` + `os.replace` (com 5 tentativas no
  `PermissionError` do Windows), dentro de uma `RLock` POR ARQUIVO (`acessos._trava`) que cobre o ler-mudar-gravar
  inteiro (as threads do waitress; um processo só, como o servidor roda). Falhou no meio: o arquivo de antes fica intacto
  e o temporário sai.
- **O portão não espera o disco** (20/10/2026): a leitura da lista a cada pedido (`admins_da_tela` pelo `_admin_em_dia`)
  é um `stat` e a cópia da memória, SEM trava, quando o arquivo não mudou; a trava só entra para reler o que mudou (e
  confere de novo lá dentro: quem grava troca o arquivo e a memória juntos). O caso: Raio-X das 08:56 de 20/10, a Visão
  do responsável e a conferência de 5 min de outra aba paradas havia 2 s na trava, que era UMA para tudo e ficava presa
  durante o `fsync` de cada login (`registrar_login`) e de cada mudança da lista; com o disco do servidor ocupado (o
  banco na mesma máquina), um login segurava as telas de todo mundo. O registro de logins tem a trava dele. Prova:
  `tests/test_base_acessos_portao_sem_fila_20_10.py` (o `fsync` preso de propósito: o portão e uma tela de quem já
  entrou respondem em menos de 1-2 s; a lista de antes vale até a troca, a nova logo depois).
- **Arquivo que não abre FECHA:** JSON corrompido = nenhum admin da tela (só os do servidor), a tela mostra o aviso
  crítico e se recusa a gravar por cima (409), porque gravar apagaria o que estava nele. Erro de disco passageiro não fica
  no cache: o próximo pedido tenta de novo.
- **A leitura da lista nunca derruba o portão** (revisão de 11/10/2026). `acessos._ler` só levanta `Ilegivel`: o `stat`
  e a leitura que dão qualquer `OSError` (a pasta de dados sem permissão de busca para o usuário do serviço; a
  `NEXUS_DADOS` apontando para um arquivo, `NotADirectoryError` no Linux), bytes que não são UTF-8 (`UnicodeDecodeError`)
  e JSON aninhado a fundo (`RecursionError`) viram "não abriu" ou "corrompido". O caso que criou a regra: só o
  `FileNotFoundError` era tratado no `stat`, e o `PermissionError` subia por `admins_da_tela` → `_admin_em_dia` →
  portão, 500 em TODO pedido de toda sessão do Fracttal (o Início e o login incluídos); a senha de administrador não
  passa por `_admin_em_dia`, por isso quem testava com ela não via. `admins_da_tela` ainda tem um `except Exception` de
  garantia, que fecha do mesmo jeito. O erro que persiste vai ao journal **uma vez** (`_avisar_uma_vez`), não a cada
  pedido. Se o `stat` falhar depois de o arquivo já ter sido trocado, a gravação conta como feita (o cache sai), para a
  tela não dizer "nada mudou" com a mudança no disco.
- **POST só da própria página:** `Sec-Fetch-Site`/`Origin` com a régua da moldura (`moldura._de_outro_site`) e um código do
  formulário guardado na sessão (o login troca). E-mail validado: sem espaço nas pontas, minúsculas, nenhum espaço ou
  vírgula no meio, `nome@dominio.tld`, até 254 caracteres. Gravou: 303 de volta à tela (F5 não repete).
- **Em teste sem `NEXUS_DADOS`** nada é lido nem gravado (`acessos.pasta` = None), como o de-para: um teste não pode
  escrever na pasta de verdade.
- **Prova:** `tests/test_base_acessos.py` (admin vê e grava; não-admin barrado e nada gravado; o do servidor não sai;
  dar acesso vira admin no login seguinte e já no próximo pedido; tirar vale no próximo pedido; auditoria e teto dela;
  escrita atômica com a troca falhando e com a escrita parando no meio; 20 threads sem perder mudança; corrompido fecha
  e não é sobrescrito; e-mails inválidos; POST de outro site ou sem o código; ninguém se tira sozinho por engano; o
  registro de logins com teto e janela, e que falha sem barrar a entrada; a pasta sem permissão, o arquivo que não é
  UTF-8 e o aninhado a fundo deixam o Início em 200 e fecham, com o aviso na tela e uma linha só no journal).

**A aba Administradores do App de Campo (05/11/2026, `telas_admins_app.py`).** Levi: "os administradores do App de Campo
e os técnicos por usina têm de ser escolhidos no Nexus". Quem administra o App passa a ser decidido aqui, e o App lê a
lista de 5 em 5 min. **Ao contrário da lista de administradores do Nexus, esta mora no BANCO**, num livro só dela
(`nexus_acessos_app_campo · fato_admin_app`; dado, assinatura e vigente em `nexus/pcm/CLAUDE.md`, Técnicos por usina):
é o App que a aplica, e ele só lê o banco.
- **Quem vê e grava:** só o administrador do Nexus (a trava da rota de Acessos). O Pôr e o Tirar vêm pelo POST da página,
  com o código do formulário e a régua do `_de_outro_site` (`acao` `admin_app_por`, `admin_app_por_email`, o avulso, e
  `admin_app_tirar`); recusa volta à aba com o motivo e 409 (a pessoa sem código, a fora da lista, o e-mail de outro
  domínio ou fora do formato, o código que já vale na lista por outra ficha, a lista que mudou, sem a
  NEXUS_PESSOA_HMAC), outro site ou o formulário vencido dão 403, a pessoa ou o e-mail que faltou 400; gravou, 303 de
  volta à aba. O nome da pessoa sai ANTES da gravação, no Pôr e no Tirar (revisão de 05/11/2026: a leitura
  do cadastro que falhasse depois de gravar viraria um erro com a linha já no livro).
- **A aba:** o "!" do título (`acessos/_admins_app_explica.html`; 2ª revisão de 05/11/2026: o "Como vale." era um aviso
  solto na tela) com o "Como vale." ("O App de Campo lê esta lista de 5 em 5 min; com a lista vazia ele não tira ninguém
  (não tranca o App)"), quem o App reconhece, o outro domínio e quem fica sem escolha; os números, os que valem hoje (o nome e o setor, ou "ficha de campo"; o avulso pelo e-mail, "avulso (sem
  ficha)"; desde quando, quem decidiu, Tirar com confirmação), o Pôr administrador (a lista, com a busca da própria
  página, e o avulso pelo e-mail; observação opcional, cifrada) e o histórico, o mais novo primeiro. Sem a chave HMAC,
  sem o token do banco ou com a leitura falhando, a aba só mostra. Com o JavaScript, os rádios perdem o `required` e o
  envio confere a escolha: sem pessoa, o aviso vai à linha `aria-live` da contagem e o foco volta à busca (o `required`
  num rádio que a busca escondeu barrava o envio calado; `tests/test_acessos_admins_app_js.py`). Sem JavaScript, o
  `required` vale.
- **Quem dá para escolher** (2ª volta de 05/11/2026, Levi, olhando a aba no ar: "Só tá aparecendo os técnicos, tem que
  aparecer todos do pessoas e setores!"; a maioria dos administradores do App é do escritório, sem ficha): a união, sem
  repetir pessoa, das fichas não desligadas e não excluídas com as pessoas de Pessoas e setores (o pessoal do Fracttal,
  pela cópia daquela aba). Cada usuário do Fracttal vale pela ligação de hoje (a última decisão de cada `fracttal_id`): o
  código, a ficha e o setor dela; sem ligação, só o palpite da aba pelo e-mail junta à ficha, o pelo nome não (2ª
  revisão de 05/11/2026: o analista do escritório com o primeiro e último nome de um técnico seria a ficha do técnico, e
  o Pôr faria o técnico administrador), e quem fica sem ficha vai com o código do e-mail do Fracttal (a conta que a
  ligação gravaria). A mesma pessoa aparece uma vez: pela ficha para onde a ligação (ou o e-mail) aponta, ou pelo código
  (o mesmo e-mail é a mesma pessoa para o App); o nome é o da ficha, senão o de Pessoas e setores.
  Cada uma com o setor, ou "ficha de campo" (ou "sem setor"), e a busca vale para o nome e o setor. O rádio `pessoa`
  leva o número da ficha ou `codigo:<código>` de quem não tem ficha (o `pessoa_id` da página de antes ainda vale). A aba
  lê só a cópia de Pessoas e setores, nunca o Fracttal na hora, num GET ou num POST (nem na subida): a cópia vencida
  mostra a idade da leitura do Fracttal ("lido há N min", pelo `lido_em`: o pessoal fica guardado 1 hora) e pede a nova
  por trás; sem cópia, as ligações de hoje seguem na lista pelo número do usuário ("Usuário do Fracttal 510"), sem
  rádio. Sem cópia porque a 1ª leitura ainda vem vindo (todo deploy começa assim; 3ª revisão de 05/11/2026: a 1ª tela
  depois do push dizia que o Fracttal não respondeu), a aba e essas linhas dizem "a leitura do Fracttal ainda está
  chegando: recarregue a página em alguns segundos", em azul; "o Fracttal não respondeu" só quando a última leitura
  falhou de verdade (`telas_fracttal` anota a falha até a próxima leitura boa). A contagem `aria-live` debaixo da lista
  conta só quem tem rádio, como o card. Sem o livro dos setores, a lista mostra só as fichas e o Pôr trava (o código das fichas
  ligadas sairia errado).
- **Quem fica sem rádio** (2ª revisão de 05/11/2026), na lista com o porquê, e o POST feito à mão recusa com 409: a
  ligação ou o palpite que aponta para uma ficha desligada ou excluída ("a ficha está desligada ou excluída no cadastro"
  e, da ligação, "a ligação em Pessoas e setores aponta para uma ficha desligada: refaça a ligação"; o recontratado entra
  pela ficha nova, que fica com o código pelo e-mail); o usuário do Fracttal sem nome ("o Fracttal não respondeu: sem o
  nome, não dá para conferir quem é", ou "ainda está chegando": nunca se dá acesso pela lista a quem não se confere); e,
  sem a chave do cadastro, quem não tem ficha (a ficha e a conta com o mesmo e-mail apareceriam duas vezes, e a linha iria
  sem `pessoa_id`). O avulso com o mesmo código recusa na ficha desligada e sem a chave; no sem nome ele passa (3ª
  revisão: o e-mail digitado já diz quem é), e a linha vai sem ficha, com o e-mail cifrado.
- **Os marcadores, que só avisam** (a pessoa segue escolhível): "outro domínio: o App não o reconhece como
  administrador" para o e-mail que não é @gridco.com.br, comparado exato com o `admins_app.DOMINIO_AVULSO` (Levi,
  05/11/2026: "Deixar aparecer"; o gridco.com sem o .br também é outro), na lista e nos que valem; e "conta do Fracttal
  desativada" (o login do App é pela Microsoft); e, no palpite pelo nome para uma ficha desligada, "o nome bate com uma
  ficha desligada: confira se é a mesma pessoa" (3ª revisão: pode ser um homônimo, então não trava). Nos que valem, "esta pessoa tem ficha agora: tire e ponha de novo para
  ligar à ficha" para quem foi posto sem ficha e ganhou ficha depois (o inverso do "Nada mudou").
- **O avulso pelo e-mail** (Levi: "tem que ter como fazer avulso também so digitando o e-mail"): o segundo formulário da
  caixa do Pôr (`acao` `admin_app_por_email`). O e-mail perde os espaços das pontas, vai para minúsculas e tem o formato
  conferido (a régua de `acessos.email_normal`), e **só @gridco.com.br** entra (decisão do Levi: o administrador do App
  entra pela conta Microsoft da Grid, e outro domínio nunca casaria; a recusa diz isso). O código é o `codigo_da_pessoa`,
  o mesmo do App. Se é o código de alguém da lista, a linha vai para essa pessoa (com o `pessoa_id` quando ela tem
  ficha) e sem o e-mail; o código que saiu de duas fichas recusa; o de ninguém vai com o `pessoa_id` vazio e o e-mail SÓ
  no `dados_cifrados` (com a observação; sem a chave do cadastro, o formulário não aparece). Na tela, o avulso aparece
  pelo e-mail decifrado, "avulso (sem ficha)", nos que valem e no histórico (a linha do tirar não leva o e-mail: vem pelo
  código da que pôs). O Tirar é o de todos, pelo código. Na recusa, o e-mail digitado volta ao campo. O número dos que
  valem sem ficha (e quantos pelo e-mail) vai no detalhe de "Administradores do App": é onde a ligação à dimensão pessoa
  se conta.
- **O código da ficha** é o do `responsaveis.conta_dos_codigos`: o do usuário do Fracttal ligado à pessoa em Pessoas e
  setores (só a ligação de hoje de cada usuário: o religado da ficha 11 para a 10 deixava o código nas duas) e, sem ele,
  o do e-mail da ficha (a desligada ou excluída não entra nem pelo e-mail nem pela ligação). Sem código, a etiqueta "sem código" e a recusa
  "sem e-mail na ficha nem usuário do Fracttal ligado: o App não a reconheceria; corrija o cadastro antes" (sem ficha:
  "sem e-mail no usuário do Fracttal"). O código que cai em duas fichas: vence a ligação do Fracttal, e a outra fica "sem
  código: o e-mail dela é o do usuário do Fracttal ligado a outra ficha"; sem ligação a desempatar, sai das duas ("o
  mesmo código está em mais de uma ficha"), e quem chega com ele sem ficha (Pessoas e setores, o avulso) também não
  entra (o `antes` da conta); a recusa do Pôr diz o mesmo. O código que já vale na lista por uma ficha é recusado com o
  nome dela, venha a outra pessoa com ficha ou sem; o que vale sem ficha e hoje é o de uma ficha é a mesma pessoa
  ("Nada mudou").
- **O aviso da linha** ("o código desta linha já não é o desta ficha… tire e, se for o caso, ponha de novo"): só quando
  o código de hoje da ficha existe e é outro (o e-mail mudou) ou quando a ficha perdeu o código (está entre as sem
  código com o porquê). Sem a chave do cadastro, nenhuma linha o leva (o Nexus não lê o e-mail das fichas, e toda linha
  posta pelo e-mail avisava em falso: re-revisão de 05/11/2026), e a aba diz "Sem a chave do cadastro, o Nexus não
  confere os códigos".
- **Quem decidiu** é o código do e-mail do login: o nome da pessoa da lista que o tem (a ficha ou Pessoas e setores)
  ou o e-mail que este Nexus conhece (administradores e quem entrou em 30 dias); vazio = a senha.
- **Prova:** `tests/test_base_acessos_admins_app.py` (só administrador; pôr, tirar e histórico com quem decidiu; a 409
  sem código; o código pelo Fracttal ligado; o religado da 11 para a 10 e a ligação que vence o e-mail de outra ficha;
  o aviso da linha, com e sem a chave do cadastro; o nome antes da gravação; só fichas ativas; outro site, formulário vencido e sem a chave; banco fora; nenhum e-mail das fichas na
  página; e, da 2ª volta, a união sem repetir, o setor na busca, o pôr e o tirar sem ficha, o avulso pôr e tirar, o
  domínio recusado, o avulso com o código de alguém da lista e o de duas fichas, nenhum e-mail em claro na linha, o
  campo de antes; e, da 2ª revisão, o palpite pelo nome que não junta, a ligação e o palpite para a ficha desligada sem
  rádio e o recontratado pela ficha nova, a conta desativada, o Fracttal fora sem rádio, a aba que nunca lê o Fracttal na
  hora e a idade da cópia, sem a chave do cadastro, o `codigo:` forjado e o `fracttal:` sem e-mail, o marcador de outro
  domínio, a explicação no "!" e o aviso de quem ganhou ficha; e, da 3ª revisão, o avulso que passa no sem nome, a
  leitura que ainda está chegando e a que falhou, a idade pela leitura do Fracttal, o nome de uma ficha desligada e a
  contagem só das escolhíveis), `tests/test_pcm_admins_app.py` (o `pessoa_id` vazio, o
  e-mail só cifrado e amarrado à linha, o domínio, sem a chave do cadastro, a chave HMAC aparada nos dois vetores),
  `tests/test_explica_padrao.py` (a marca em `<strong>` e o "Como vale") e `tests/test_acessos_admins_app_js.py` (o envio
  sem pessoa, a busca pelo setor, o avulso, a linha sem rádio e a contagem só de quem tem rádio, no node). No navegador, a cópia de prova com dados de mentira, com o Fracttal de mentira em Pessoas e
  setores (1366 e 375 px).

## Nexus lento: Raio-X e o teto do OS Creator (14/10/2026)

Levi, 14/10/2026 às 09:20: "O nexus está muito lento"; "quando clico no OS Creator, fica carregando por um bom tempo"; e
"pq depende da TI se o OS Creator Web faz parte do Nexus???". Medido de fora: o /saude do Nexus de 0,5 a 30 s (às vezes 60
s), a plataforma e a API do banco, no mesmo servidor, em 0,2 s: as threads do waitress presas esperando o Fracttal pelo
OS Creator, que roda DENTRO do processo do Nexus (a ponte, sem proxy).
- **Raio-X** (`/t/base/raio-x`, `casca/raio_x.py`; só administrador, sem item no menu): os pedidos em andamento e onde
  cada um espera, as tarefas de fundo, o processador, a carga da máquina, o teto do OS Creator e os travamentos de 24 h
  e, desde 31/10/2026, **o uso do OS Creator nos últimos 7 dias** (a seção "Uso do OS Creator", mais abaixo).
  Nexus lento de novo = pedir o print dele na hora. **Desde 20/10/2026 diz também onde a MÁQUINA engasga** (pelo /proc do
  Linux, só leitura, quando a página abre): na "Carga da máquina", o processador da máquina inteira e o tempo esperando o
  disco na mesma janela de 1 s; no cartão "Memória da máquina", a memória livre, o swap em uso e se está trocando agora
  (MB/s), o quanto o Nexus ocupa (e dele no swap) e, com a PSI do kernel, o tempo com algo parado esperando memória ou
  disco. **E o teto do Nexus** (`raio_x._teto_nexus`, 29/10/2026), no mesmo cartão: o `MemoryHigh`/`MemoryMax` e o swap
  permitido pelo grupo do próprio processo (cgroup v2 do systemd ou do contêiner, ou v1), quantas vezes o Linux o
  apertou (`memory.events`) e onde está posto; "nenhum" quando não há. Desde 30/10/2026 o `deploy/atualizar.sh` tira
  sozinho o teto abaixo de 4 GB do serviço (DEPLOY.md, seção 8) e grava o que viu e fez em `.git/nexus-teto`; o
  cartão mostra (`raio_x._teto_do_deploy`, "o deploy conferiu em ...": tirou, sem teto, só no cgroup ou o erro, com o
  arquivo onde o teto está escrito). Prova: `tests/test_raio_x_teto_deploy_30_10.py`. O caso: em cinco leituras de dois dias o Nexus
  ficou sempre com ~700 MB na memória e o resto no swap, com 5,7 a 7 GB livres na máquina, e o Levi não tem acesso ao
  servidor para ler o serviço. Prova: `tests/test_raio_x_teto_memoria_29_10.py`. O caso de antes: Raio-X das 10:08 de 20/10, `GET /os/` há 18 s numa cópia de 17 ms com o Nexus a 13% e carga 2,5 a 3,9:
  a carga do Linux soma quem espera o disco, e a página não dizia qual era o gargalo. Leitura: "esperando o disco" alto
  ou swap trocando = a máquina (disco, memória), não o código; Nexus a ~100% = o processo (o GIL). Prova:
  `tests/test_raio_x_maquina_20_10.py`. **E quem ocupa a memória da máquina** (`raio_x._quem_ocupa`, 20/10/2026), somado
  por programa pelo /proc de cada processo: a memória própria (RssAnon) somada, a compartilhada uma vez só (RssShmem: os
  buffers do PostgreSQL aparecem em todo processo dele) e o swap (VmSwap); o Nexus é "este processo", e do Python sai só
  o arquivo do script e a pasta dele, nunca a linha de comando (pode ter senha). O caso: Raio-X das 14:17 de 20/10, 0,2
  GB livres de 7,1 GB e 3,2 GB no swap com o Nexus em 690 MB, e o PDF das 13:45 1 min "trabalhando" no desenho do logo.
  **A lista sai de uma thread à parte, com prazo de 2 s** (`_memoria_por_programa`): na travada das 16:12 de 20/10 o
  próprio Raio-X ficou 4 min 18 s preso em `_ler_proc`, porque ler a linha de comando de um processo que está no swap faz
  o kernel trazê-la do disco, e com o disco tomado ela não volta. Passou do prazo, a página diz que o /proc não respondeu
  e mostra a última lista; enquanto a leitura presa não volta, nenhuma outra é aberta; o nome de cada processo é lido uma
  vez só (`_ROTULOS`). Prova: `tests/test_raio_x_memoria_por_programa.py`. **E dentro do worker da plataforma**
  (`_worker_plataforma`, 20/10/2026): a cada 10 min o worker da plataforma de Performance grava em
  `/dev/shm/gridco_plataforma_worker.json` (`RELATORIO_WORKER`) quanto cada variável dele ocupa, por amostra, com as
  últimas 3 h (PerformancePainel, `_relatorio_memoria_worker`); o Raio-X mostra agora × ~1 h antes, com o mesmo prazo de
  2 s, e avisa quando o relatório tem mais de 30 min (o worker parou de anotar). O caso: no servidor o worker foi de 3,7
  para 5,0 GB (com o swap) entre 16:12 e 16:38 de 20/10, e a medição de dentro só dava no PC, que não roda os backfills do
  servidor. Prova: `tests/test_raio_x_worker_plataforma.py`. **E dentro do web da plataforma** (`_web_plataforma`,
  21/10/2026): o processo web grava o mesmo relatório em `/dev/shm/gridco_plataforma_web.json` (`RELATORIO_WEB`;
  PerformancePainel, `_memoria_web_loop`), e o Raio-X o mostra igual, com o prazo e o estado próprios (um relatório preso
  não prende o outro; as duas seções saem da macro `dentro` do `raio_x.html`). O caso: Raio-X das 14:55 de 21/10, o web
  de 0,8 GB (14:36) para 3,1 GB e 0,7 GB no swap, com 0,2 GB livres na máquina, e por dentro só se via o worker. Prova:
  `tests/test_raio_x_web_plataforma.py`. **E a lista de threads também tem prazo** (22/10/2026): às 08:57 de 22/10, com a
  máquina em 3,6 GB de swap, o próprio Raio-X ficou 1 min 15 s preso em `_threads`, porque o `traceback.extract_stack`
  lia no disco o código de todas as linhas de cada pilha, e o rótulo só usa a de dentro. As pilhas saem de
  `presos.pilha` (sem o código; também na ronda dos presos), e os pedidos em andamento e as tarefas de fundo saem com o
  mesmo prazo de 2 s (`_THREADS`): passou dele, a página mostra a última lista, com a hora dela. Prova:
  `tests/test_raio_x_threads_sem_disco_22_10.py`. **E dentro do próprio Nexus** (`casca/memoria_nexus.py`, 24/10/2026):
  na máquina nova (16 GB) o Raio-X das 12:05 mostrou o Nexus com 682 MB na memória e 1.917 MB no swap, e a página não
  dizia de quê. A mesma conta da plataforma, por amostra, das variáveis dos módulos do Nexus (e do clone do OS Creator)
  e das extensões do app (medidas uma a uma; o app do Flask nunca como um bloco só), a cada 10 min numa thread
  (`nexus-memoria`, ligada no servir.py e no app.py; a 1ª 90 s depois de subir), com teto de 3 s (a medida segura as
  outras threads: o GIL). O Raio-X só mostra a última, sem medir nada ao abrir, na seção "Dentro do Nexus" (a mesma macro
  `dentro`). Prova: `tests/test_raio_x_dentro_do_nexus_24_10.py`.
- **Teto do OS Creator** (`casca/teto_os.py`, ligado no servir.py antes do presos): o servidor sobe com 32 threads e
  `/os/*` + `/t/os/*` usam no máximo 16 ao mesmo tempo; o seguinte espera 3 s por uma vaga e volta 503 (a tela se
  recarrega em 8 s; o pedido de dados recebe o recado em JSON). Os estáticos do OS Creator e a pré-carga não contam. O
  resto do Nexus nunca fica sem thread por causa dele. Separar o OS Creator num serviço próprio pediria a T.I. (serviço e
  Caddy); o teto dá o mesmo efeito sem ela. O 503 nasce antes do Flask, então o uso das telas (`casca/uso_os.py`) não o vê
  pelos ganchos do pedido: o `uso_os.ligar` pendura `uso_os.recusado` em `Teto.ao_recusar` (por isso liga DEPOIS do teto), e
  `teto_os.do_os_creator(environ)` é a régua única de "pedido do OS Creator" (do teto e do uso).
- **No OS Creator** (README da torre, 14/10/2026): a tela inicial não espera mais o selo do Fracttal, e as contagens da
  Performance ficam 6 h na memória.
- **O leitor dos ativos do OS Creator** (`os_creator/ativos_leitor.py`, 31/10/2026, etapa 2 do canto central; regras no
  README da torre, "O leitor do servidor"): ligado no servir.py, pelo `ponte.modulo_do_clone` (o MESMO módulo
  que as telas importam; por outro caminho seria um segundo catálogo na memória). Sem a credencial REST do Fracttal não
  liga, e o estado diz por quê. Duas threads: `nexus-ativos-leitor` (o laço: o Fracttal inteiro às 02:15, ~270 pedidos a 1
  por segundo, e os novos às :08 e :38 das 06h às 22h) e `nexus-ativos-novos` (os novos que os botões pedem). No contador
  do Fracttal elas aparecem como `fundo:nexus-ativos-leitor` e `fundo:nexus-ativos-novos`. Nunca o `app.py` nem os testes.
- **O leitor da lista central de OS do OS Creator** (`os_creator/os_leitor.py`, 31/10/2026, etapa 3; regras no README da
  torre, "A lista central de OS e o leitor em faixas"): ligado no servir.py, por último, depois do dos ativos e do
  `instalar_campo` (o laço do `tarefas_os`, que lhe entrega as abertas), pelo `ponte.modulo_do_clone`. Sem a credencial REST
  não liga, e o estado diz por quê. Uma thread, `nexus-os-leitor`, uma faixa por vez, 1 pedido por segundo: as novas de 3 em
  3 min (06h às 20h de segunda a sexta; de 15 em 15 fora disso; em qualquer minuto, 1 ou 2 pedidos), os 7 dias às :00, :21,
  :30, :41 e :51 (06h às 20h, ~15 pedidos), as finalizadas às :46 (1 a 3), a conferência das abertas às :55 (lê ~98 só se o
  `tarefas_os` não entregou em 70 min) e a noite às 03:21 (90 dias, ~190 a 210 pedidos; a janela inteira no domingo e na 1ª
  carga, ~750 a 830): os números na escala do AC, ~99 OS por dia (rodada 1 da revisão da 3.1+3.2; ~92 a 110 pedidos por hora
  de dia útil). No contador do Fracttal, `fundo:nexus-os-leitor:<faixa>`. A cópia em disco da lista é gravada numa thread de
  uma vez (`nexus-os-central-disco`, no máximo uma escrita a cada 30 s). O pico de memória da noite de 365 dias é de ~150 MB
  (a leitura cortada por página, guardada até o fim; eram ~390 MB com as linhas inteiras), e o da de 90 dias, ~40 MB
  (README da torre, "O pico da noite"). Nunca o `app.py` nem os testes.
- **O laço das pessoas dos catálogos pequenos do OS Creator** (`os_creator/catalogos_leitor.py`, o par do `catalogos.py`,
  31/10/2026, etapa 4; regras no
  README da torre, "Os catálogos pequenos num lugar só"): ligado no servir.py, por último, pelo `ponte.modulo_do_clone`. Sem a
  credencial REST não liga, e o estado diz por quê. Uma thread, `nexus-catalogos`: o REST `personnel` do cadastro
  (`cadastro/fracttal_pessoal.ler_paginas`), 2 pedidos a 1 por segundo, às 05h, 11h, 17h e 23h no :04
  (`CATALOGOS_PESSOAS`), só aceito com os campos que as telas usam. No contador do Fracttal,
  `fundo:nexus-catalogos:pessoas`. Os outros catálogos (etiquetas, tipos, falhas, status, motivos, planos da Performance) não
  têm leitor da empresa: a 1ª sessão que os acha vencidos os renova por trás, uma vez para todos, e esses pedidos contam na
  rota dela. Nunca o `app.py` nem os testes (no PC, as pessoas também seguem pela sessão).
- **Os minutos ocupados, num lugar só** (`casca/minutos_ocupados.py`, 31/10/2026, decisão AF da etapa 3): os minutos de toda
  hora que já têm dono (:04 as pessoas dos catálogos pequenos do OS Creator, às 05h, 11h, 17h e 23h; :08 e :38 os ativos
  novos, :10 a :20 as tarefas das OS, :22 as normalizações, :25 o sync do App, :32 a zeladoria, :40 a carga, :50 os chamados;
  e os da lista central de OS: :00, :21, :30, :41 e :51 os 7 dias, :46 as finalizadas, :55 a conferência das abertas), e os
  de uma vez por dia (`DIARIOS`: os ativos inteiros às 02:15, a noite da lista de OS às 03:21 e o uso do OS Creator no banco
  às 04:45; era 03:45 até a revisão final de 31/10/2026: a noite de domingo da lista lê os 365 dias, ~830 páginas a 1 por
  segundo, de 19 a 29 min a partir das 03:21, e podia passar das 03:45; `test_a_noite_de_domingo_acaba_antes_da_gravacao_do_uso_no_banco`).
  O laço novo que precisa de um horário fixo pede o próximo minuto livre (`proximo_livre`; `livre(minuto, hora)`
  olha os diários também) em vez de chutar, e quem muda o minuto de um laço muda a lista no mesmo trabalho: dois donos no
  mesmo minuto não passam (`_ocupar` acusa ao montar). Os ativos, a lista de OS e as pessoas dos catálogos leem os horários
  dela (`ATIVOS_*`, `OS_*`, `CATALOGOS_PESSOAS`); os outros laços têm o `MINUTO_DA_HORA` deles, e
  `tests/test_oscreator_os_leitor.py::test_os_minutos_moram_na_lista_unica` cruza cada um com a lista (rodada 1 da revisão
  da 3.1+3.2: as finalizadas saíram do :45, que às 04:45 é do `uso_os`; o das pessoas,
  `tests/test_oscreator_catalogos.py::test_o_minuto_das_pessoas_mora_na_lista_unica`).

**Os leitores do canto central na subida (31/10/2026, revisão final).** O `servir.py` liga os três leitores do clone do OS Creator
(`ativos_leitor`, `os_leitor`, `catalogos_leitor`) por `ponte.ligar_leitor_do_clone`, cada um num try: importar o leitor é importar o
clone, e isso acontece na SUBIDA (antes o clone só carregava no 1º pedido ao `/os/`, dentro de um try). O erro de import ou do
`ligar` vai ao log com a pilha, o Nexus sobe sem aquele leitor (as telas leem ao vivo) e o Raio-X diz "NÃO LIGOU, o clone quebrou
ao subir" na peça dele (`ponte.FALHOS`, em `app.extensions`). O portão do deploy (`deploy/conferir_boot.py`) importa, sem ligar, o
contador do Fracttal, o uso do OS Creator e os três leitores, para barrar o commit com o clone quebrado antes do restart.

## Pedidos ao Fracttal: o contador e o porteiro (31/10/2026)

Etapa 0 do canto central do OS Creator (`docs/superpowers/specs/2026-10-30-oscreator-canto-central-design.md`). A cota
do Fracttal é de 200 pedidos por minuto para a empresa toda, e ninguém sabia quanto o Nexus gasta dela, a que hora nem
quem pede. `casca/fracttal_conta.py` é UM gancho no `requests.sessions.Session.send` (`ligar()`, idempotente; quem liga
é o `servir.py`, logo depois do `create_app` e antes dos `instalar_*`, que já abrem laços que pedem ao Fracttal ao subir;
nunca o `create_app`: o PC e os testes seguem sem ele). Todo pedido do processo a um
host `fracttal.com` ou `*.fracttal.com` (o RPC do OS Creator, o REST do `campo/fracttal.py`, o token) é somado na
memória, sem mudar quem pede. O resto da internet passa sem contar (`notfracttal.com` também: o domínio começa no ponto).
- **A linha** é hora × origem × método: `pedidos_qtd`, `recusas_qtd` (406/429), `erros_qtd` (exceção ou 5xx),
  `pico_minuto_qtd` (o maior número de pedidos num mesmo minuto, o número que se compara com a cota) e `esperas_qtd` (os
  que esperaram a vez no porteiro, abaixo), mais uma linha
  `*`/`*` por hora com o total e o pico de tudo junto (o pico do total NÃO é a soma dos picos; no banco ela vai para a
  aba própria do total, 1 linha por hora, e o detalhe fica sem ela: `fato_uso_os.separar_total`). A hora é a de Brasília,
  UTC-3 fixo: `hora_id` = `AAAAMMDDHH`, e a virada do dia cai às 03:00 UTC.
- **Origem** = `origem(rota)` (o `casca/uso_os.py` marca TODO pedido do Flask, não só o `/os/*`, com a rota normalizada:
  o que as telas do Campo, da Engenharia e do PCM pedem ao Fracttal cai na rota delas, e não em `fundo:waitress`) e, sem
  marca, `fundo:<nome da thread SEM o contador de instância>`: `ThreadPoolExecutor-137_0` vira `ThreadPoolExecutor`,
  `waitress-12` vira `waitress` e `Thread-5 (alvo)` vira `Thread (alvo)`. O `campo/regras_app._fx_wo_paralelo` abre um
  executor NOVO a cada chamada, e com o nome cru cada rodada
  criaria origens novas na tabela da hora, sem fim. **No máximo 50 origens de FUNDO (`fundo:...`) distintas por hora**
  (`MAX_ORIGENS_DE_FUNDO`): a 51ª e as seguintes dessa hora entram em `fundo:outros`, e as 50 que já existem seguem
  contando nas suas; a hora seguinte recomeça a conta. **A rota não tem teto** nem gasta vaga do fundo: quem a marca
  (o gancho do pedido) passa a rota normalizada, limitada pelo conjunto de rotas do app; só o nome que ganha número novo
  a cada vez precisava de freio.
  A marca viaja pelo CONTEXTO (`contextvars`, como o JWT do OS Creator), não pela thread: o `api._ExecutorComContexto`
  copia o contexto para as tarefas do fan-out (o catálogo de ativos pede ~110 vezes, 6 de uma vez), que ficam na rota que
  as chamou e somam na conta do pedido (`pedidos_desta_thread()`, a da marca em que a thread está). **A marca só chega às
  tarefas de um executor que COPIA o contexto:** no `ThreadPoolExecutor` comum e na thread aberta à mão a tarefa começa
  sem contexto, a marca de quem a abriu NÃO chega lá, e a origem tem de ser posta dentro da tarefa (`with origem(...)` na
  função que vai ao executor); sem isso ela é `fundo:ThreadPoolExecutor`.
  **Método** = o `method` do corpo do RPC (em lista vale o 1º que traz um; corpo que não é JSON = `rpc`), o 1º segmento
  depois de `/api/` no REST (`work_orders`), `token` no OAuth e na renovação do JWT, e `outro` no resto.
- **Quem lê:** `instantaneo()` (o Raio-X, sem tirar nada) e `drenar(hora_aberta)`, que devolve e TIRA as linhas das
  horas ANTERIORES a ela (passe a hora de agora, `hora_id_de()`). A gravação regrava a mesma chave trocando a linha,
  então a resposta que volta depois da hora drenada não a recria (uma linha de 0 pedidos e 1 recusa apagaria a certa).
- **Nunca derruba o pedido:** a falha do contador vai ao log em debug e a resposta, ou a exceção, volta como veio. Com
  redirecionamento cada salto conta uma vez (o `requests` refaz o pedido pelo mesmo `send`), e a recusa ou o erro é da
  resposta daquele salto, não da final.
- **Memória:** do minuto só o corrente fica; do resto, uma linha de cinco números por hora, origem e método, e a janela do
  porteiro guarda só o último minuto. Se ninguém drena, as horas se acumulam: quem drena é o laço do `uso_os` no :05 de
  toda hora (para o disco), da mesma etapa 0. **O contador não guarda nada em disco:** um reinício perde a hora aberta
  dele (o que já saiu para o pendente está salvo).
- **O porteiro (etapa 5), no mesmo gancho** (o embrulho do `Session.send` mora só aqui). Estourar a cota derruba o App de
  Campo, que vive dela: o desenho do canto central chama isso de fracasso, mesmo com tudo funcionando. Todo pedido do
  processo ao Fracttal (RPC e REST, toda origem) entra numa conta deslizante de 60 s, contado na hora em que sai: **o
  Nexus até 150 por minuto** (`TETO_POR_MINUTO`: sobram 50 dos 200 para o App de Campo e os robôs) e **o fundo até 90**
  (`TETO_FUNDO_POR_MINUTO`). Outro domínio não passa por ele.
  - **Clique ou fundo: só a origem DECLARADA é fundo.** Fundo é a `fundo:` que o laço declara: `origem("fundo:...")` ou,
    no alvo da thread, `de_fundo("fundo:<a thread>", fn)` (a declaração vale só dentro de `fn`). Todo o resto é clique: a
    rota do pedido, inclusive o que a tela pede sozinha (`X-Nexus-Auto`), e a thread sem declaração (a tarefa do pool
    comum, a thread aberta à mão por uma tela), que leva ao fato o nome de sempre, `fundo:<thread>` (`_Marca.declarada`).
    O caso que criou a regra (a revisão da 1ª versão do porteiro, 31/10/2026, antes de ir ao ar): como fundo, a pessoa
    esperaria a vez do fundo, sem limite, no card do OS Creator (o detalhe lido por trás, `os-web-preparo`) e na
    Aprovação (as páginas da fila num pool).
  - **O clique nunca é recusado:** com 150 no último minuto, cada PEDIDO dele espera no máximo 2 s
    (`ESPERA_CLIQUE_MAX_S`, medidos no relógio monotônico) e segue assim mesmo, com ou sem vaga: a tela que faz 5 pedidos
    em fila pode esperar até 10 s, e as tarefas que um pool faz juntas esperam juntas. Nenhuma thread do waitress fica
    presa no porteiro sem prazo.
  - **O fundo espera a vez, sem limite:** passa só com menos de 90 de fundo E menos de 150 no total, e cede a vaga ao
    clique que estiver esperando. A leitura dele segue em curso (é só um pedido mais lento; o `timeout` do requests nem
    começa, porque a espera é antes do adaptador).
  - **Quem segura um recurso enquanto pede tira a vez antes** (`reservar_vez()`): no `campo/fracttal.py`,
    `with fracttal_conta.reservar_vez(), _VAGAS:`. Todo pedido espera a vez ali, sem uma das 4 vagas na mão (o fundo
    declarado sem limite, o resto no máximo 2 s), e já entra na janela; o 1º pedido dentro do bloco não espera nem conta
    de novo (a hora e a espera vão à linha dele). Nas versões de antes (31/10/2026, antes de ir ao ar), quem esperava a
    vez segurava a vaga: 4 leitores de fundo parados no porteiro prendiam o clique que lê pelo mesmo arquivo, e, com o
    minuto cheio, o 12º clique da fila somava 6 s. Sem o gancho (o PC, os testes) não faz nada; a reserva que sobrou
    morre no fim do bloco. A reserva vale para o 1º salto: se o Fracttal redirecionar algum destes caminhos (não se
    conferiu, para não ir ao Fracttal), o 2º salto sai sem ela e espera a vez com a vaga na mão (o aviso está no
    `campo/fracttal.py`; o `allow_redirects=False` faria essa leitura falhar).
  - **Ninguém dorme segurando a trava:** a espera é na `Condition` da trava (`_esperar`), no máximo 1 s por vez
    (`PASSO_DA_ESPERA_S`) e conferindo de novo; o clique que sai acorda o fundo que cedeu a vaga a ele. O relógio de
    parede que volta (o NTP) não prende a janela: o que ficou "no futuro" passa a ser de agora.
  - **A conta é deste processo:** o PC não liga o gancho e o App de Campo é outro sistema; a folga de 50 é deles.
  - **As esperas:** o pedido que esperou soma `esperas_qtd` na linha dele, na hora em que SAIU; a coluna vai ao banco no
    fim das duas abas do Fracttal (`nexus/dados/CLAUDE.md`), e o Raio-X a mostra por dia e por hora (seção "Uso do OS
    Creator"). `estado()` diz o que saiu no último minuto, quem espera agora e as esperas de cada hora guardada, de
    clique e de fundo como o porteiro as tratou (no fato, o nome `fundo:<thread>` não diz se a thread se declarou).
  - **Os laços do servidor que pedem ao Fracttal declaram o fundo** (31/10/2026), no ALVO da thread deles e com o nome que
    o fato já mostrava: `fundo:nexus-os-leitor:<faixa>` (o `os_leitor`, que já declarava, por `origem`),
    `fundo:nexus-ativos-leitor` (o laço da noite e dos novos das :08 e :38), `fundo:nexus-tarefas-os-banco`,
    `fundo:nexus-chamados-banco`, `fundo:nexus-fila-fracttal` (a releitura da Aprovação por trás),
    `fundo:nexus-ronda-checklist` (no `pedir_releitura`, não no `em_segundo_plano`, que também abre as fotos da ronda),
    `fundo:nexus-os-falhas`, `fundo:nexus-os-equipe`, `fundo:nexus-etm` (só a thread por trás: com `esperar=True` a
    releitura roda na thread do clique e segue clique) e `fundo:os-web-acomp-renovar` (a releitura de 30 em 30 min do
    Acompanhamento de chamados, desde 03/11/2026: era clique, e às 10h desse dia o Nexus chegou a 828 pedidos num minuto).
    A zeladoria, as normalizações, a carga, os responsáveis e os
    relatórios do PCM não pedem ao Fracttal na thread deles (a zeladoria pede as releituras acima). **Laço novo que pede
    ao Fracttal declara o fundo do mesmo jeito**, senão ele é clique: sem o teto de 90 e na frente do fundo.
  - **O que segue clique sem ser clique, de propósito (31/10/2026):** a cópia do catálogo de ativos que o OS Creator baixa
    por trás pelo RPC (`os-catalogo-por-tras`, no `ativos_carga.py` do clone desde a 5.3) leva a cópia do contexto do pedido e conta como a
    rota que a pediu: com o leitor do servidor ligado ela só roda como socorro da noite que não entrou (o catálogo
    vencido), então fica como está. Também as páginas da releitura da Aprovação, num pool comum do
    `campo/regras_app._fx_wo_paralelo` (cópia fiel do App, não se mexe: só o 1º pedido, o do total, sai na thread
    declarada), e os novos de ativos que o botão pede (`nexus-ativos-novos`: quem clicou espera por eles). Como clique,
    eles NÃO têm teto: cada pedido conta na janela dos 150 e, com ela cheia, espera no máximo 2 s e sai; só o fundo
    declarado para nos 90 e nos 150. Fora da conta e do porteiro, como o PC e o App de Campo: a geração do PCM, que roda
    o motor num processo à parte (`pcm/geracao._executar`, `subprocess`).
- **Prova:** `tests/test_casca_fracttal_conta.py` (o adaptador falso numa `requests.Session` de verdade, sem rede;
  mutações no gancho pegas uma a uma) e `tests/test_casca_porteiro.py` (o relógio na mão, e a espera anda o relógio em
  vez de dormir: um minuto de espera leva um instante; os testes com threads e a `Condition` de verdade, inclusive o
  clique pelo `campo/fracttal.py` com 4 fundos parados no porteiro e os 12 cliques na fila das vagas; a lista dos laços
  que declaram). Os relógios dos testes que ligam o gancho (o deste arquivo, o do contador, o do uso e o do fato) andam
  na espera do porteiro em vez de dormir, e o `parado` (a espera de verdade) tem prazo: o teste que passa de 90 de fundo
  no minuto parado falha ou termina, nunca trava a suíte. Nenhum teste fala com o Fracttal de verdade: o
  `tests/conftest.py` bloqueia, no adaptador do requests, o pedido a um host que termina em `fracttal.com`
  (`tests/test_sem_rede_do_fracttal.py`). Mutações pegas uma a uma, em 31/10/2026: 23 no `fracttal_conta.py`, 1 no
  `campo/fracttal.py`, 1 na declaração de um laço, 6 na coluna `esperas_qtd` (o fato e o Raio-X), 4 nos relógios dos
  testes (pegas pelo tempo esgotado: sem a espera que anda o relógio, o teste trava) e 2 no bloqueio do `conftest`.

## Uso das telas do OS Creator por hora (31/10/2026)

Etapa 0 do canto central do OS Creator, a outra metade do contador acima. Em 13 e 14/10/2026 o OS Creator prendeu as
threads do Nexus e ninguém soube dizer quais telas as pessoas abrem, a que hora, em quantas, quanto cada uma demora nem
quanto pede ao Fracttal. `casca/uso_os.py` mede isso, na memória, por **hora (de Brasília) × rota × automático**, e é o
que dá o "antes e depois" de cada etapa seguinte. Liga no `servir.py` DEPOIS do `teto_os` (`uso_os.ligar(app,
gravar=True)`); o `create_app`, o PC e os testes seguem sem ele.
- **Os ganchos** (`ligar`): o `before_request` entra na FRENTE do portão (vê também o que ele recusa e mede o tempo dele),
  o `after_request` na ponta de trás (vê a resposta que sai) e o `teardown_request` fecha a conta, mesmo se o pedido
  quebrou. O pedido em curso guarda a medição no próprio `environ` (`nexus.uso_os`), não no `g`. Nenhum deles levanta: a
  falha da medição vai ao log em debug.
- **Toda rota do Flask marca a origem do contador do Fracttal** (`fracttal_conta.origem(rota normalizada)`), e a marca sai
  no `teardown`, mesmo se o pedido quebrar (senão a thread do waitress levaria a rota ao pedido seguinte). Já o uso só
  mede `/os/*` e `/t/os/*` de quem entrou (`teto_os.do_os_creator`: sem os estáticos, a pré-carga e quem não tem sessão).
- **Rota normalizada** (`normalizar_rota`): sem a query; segmento só de dígitos vira `<n>` (`/os/os/16995` → `/os/os/<n>`)
  e id opaco (uuid, hex de 8 ou mais, `s` + hex, token de `token_urlsafe` com dígito) vira `<id>`. Palavra de rota não
  muda: `tests/test_casca_uso_os.py::test_nenhuma_palavra_de_rota_vira_id` varre todo trecho fixo das rotas do Nexus e
  do clone (um nome de rota novo só com letras de a a f e 8 ou mais caracteres, ou com 16 ou mais caracteres e um dígito,
  quebra esse teste). No máximo 200 rotas distintas por hora (`MAX_ROTAS`); as seguintes entram em `(outras)`.
- **Clique ou automático.** Automático é o que a tela pede sozinha: o cabeçalho `X-Nexus-Auto: 1` (a conferência da sessão
  de 5 min em `_confere_sessao_js.html`, o `acompanhamento/estado` do `acomp.js` e a atualização de 15 min do Histórico de
  solicitações, `solic_pcm.js`/`solic_hist.js`); ou `?nx_auto=1` no endereço, porque a atualização de 10 min do Histórico
  de OS é `form.submit()` e um formulário não manda cabeçalho (o `historico.html` põe o campo escondido só nesse envio, o
  tira em todo outro e apaga a marca do endereço ao carregar, para o recarregar do navegador ser um clique); ou uma das
  `ROTAS_AUTOMATICAS` (`/os/_nexus/sessao`, `/os/chamados/acompanhamento/estado` e `/os/historico/progresso`), para a aba
  aberta que ainda roda o JavaScript de antes. O `progresso` é o círculo de carga (`carga.js`) perguntando de 350 em 350
  ms enquanto o Histórico busca (o `X-Nexus-Auto` também vai nele): fora da lista seria a "rota mais clicada" por uma
  folga enorme. Só o valor `1` marca. **Tela nova que se renova sozinha põe o cabeçalho**, senão conta como clique.
- **Pessoas distintas, sem guardar quem:** o HMAC do e-mail da sessão (`codigo_da_pessoa`, com a `NEXUS_PESSOA_HMAC` ou, sem
  ela, a chave do app) num conjunto SÓ na memória, por balde. Nem o código vai a disco ou ao banco: o parcial leva só a
  contagem. A senha de administrador não traz pessoa.
- **Duração:** um histograma de faixas de 3% por balde (só contagens, que somam entre reinícios e cabem no arquivo sem
  guardar um tempo por pedido); mediana e p95 pelo centro da faixa (erro até 1,5%). Medida do `before_request` ao
  `teardown`: é até a resposta estar montada, não o envio do corpo. O pedido que o teto recusou não tem duração
  (`duracao_p50_ms`/`p95` = `None` num balde sem pedido atendido; quem grava deixa a célula vazia, não zero).
- **`erros_qtd`** é a resposta 5xx ou a exceção da tela; **`ocupado_qtd`** é o 503 do teto, e os dois entram em
  `pedidos_qtd` mas não se somam (o recusado não é erro do servidor). A hora é a do FIM do pedido, lida DENTRO da trava (como
  no `fracttal_conta`): o balde de uma hora que o laço já tirou nunca renasce. Lida antes da trava, o `drenar` podia
  passar no meio da conta (achar o setor demora), o pedido recriava a hora com 1 pedido e o próximo `drenar` devolvia a
  mesma chave com o número errado, que a gravação por chave poria no lugar da linha certa.
- **`fracttal_qtd`:** os pedidos ao Fracttal que o pedido fez (`pedidos_desta_thread()`, com os das tarefas do fan-out que
  herdam o contexto). A rota é a mesma `origem` do contador do Fracttal: dá para cruzar o uso com a cota.
- **O reinício não perde a hora:** a cada 5 min (`PASSO_S`; só fora dos testes, thread `nexus-uso-os`) os baldes vão a
  `<NEXUS_DADOS>/casca/uso_os_parcial.json` (atômico: rascunho + `os.replace`) e voltam no boot. Perde-se no máximo os
  últimos 5 min de um reinício bruto. **`pessoas_qtd` depois de um reinício é aproximado:** soma dos dois lados, no
  máximo `pedidos_qtd` (quem veio antes e depois conta duas vezes). Arquivo quebrado ou fora da forma é ignorado (aviso no
  log), um balde ruim não leva os bons, e a gravação seguinte o conserta. Quem drena (`drenar`) chama `salvar()` depois de
  gravar no banco; sem isso o arquivo parcial ainda tem a hora e um reinício a traz de volta.
- **O corte por setor** (`<NEXUS_DADOS>/casca/uso_os_setor.json`): pedidos por **dia × setor × rota**, cliques e
  automáticos, o setor da pessoa como o menu o acha (`setor_telas.acesso()`, que já vem guardado no pedido e relê o banco só
  pela cópia de 1 min; sem setor ou sem como saber, `(sem setor)`). **Só no disco do servidor e por 30 dias, nunca no
  banco:** há setor de uma ou duas pessoas, e "hora × rota × setor" diria o que ela fez e quando, num banco de leitura
  aberta que não apaga. Fica fora dele o pedido que o teto recusou (não tem sessão). Dia, não hora, de propósito.
- **A memória não cresce:** as horas guardadas têm teto (`MAX_HORAS` = 48: o PC, ou o banco fora por dias, não pode
  acumular os conjuntos de pessoas), e as rotas, os setores e o tamanho da rota também.
- **Quem lê:** `instantaneo()` (`{"linhas", "setor"}`, o Raio-X, sem tirar nada) e `drenar(hora_aberta)`, EXCLUSIVO como o
  do contador do Fracttal: devolve e tira as horas anteriores a ela.
- **O laço: o disco de hora em hora, uma gravação por dia às 04:45** (Ruling M da controladora, 31/10/2026; a thread
  `nexus-uso-os-banco`, só com `gravar=True`: o servidor; nunca o PC nem os testes). O motivo: gravar o livro do mês inteiro
  no banco custa ~7 s de processador (medido: o `xlsx` sozinho 5,7 s, no mês cheio), e o Nexus é UM processo com o servidor
  já apertado: de hora em hora isso travaria os pedidos uma vez por hora. Dois passos (`proximo_passo`):
  1. **No :05 de toda hora** (`drenar_para_o_disco`) tira as horas FECHADAS dos dois contadores (`drenar`, com a hora aberta
     lida UMA vez, antes dos dois) e as guarda no **pendente** em disco, `<NEXUS_DADOS>/casca/uso_os_pendente.json`
     (atômico: rascunho + `os.replace`); depois `salvar()`, para o parcial não trazer essas horas de volta. Nunca vai ao
     banco. A memória dos contadores fica limitada.
  2. **Às 04:45 de Brasília, uma vez por dia** (`gravar_no_banco`) leva ao banco TUDO o que está pendente, agrupado pelo
     livro do mês de cada hora (`nexus_oscreator_uso_AAAA_MM`, **três abas**: `fato_uso_hora`, `fato_fracttal_hora` e
     `fato_fracttal_total_hora`; registrado no catálogo, `so_cresce`): relê o mês, troca as linhas de mesma chave
     (regravar a mesma hora não duplica) e publica pelo `livros.publicar`. Na primeira gravação depois da virada do mês, o
     mês que fechou ganha as últimas horas (o pendente atravessa a virada; os dois livros saem juntos). **Deu certo:** anota
     `gravou_em`, as linhas gravadas saem do pendente (memória e disco) e `salvar()` roda. **Deu errado** (banco fora,
     leitura curta do livro, sem a `GRIDCO_SQL_TOKEN`): o pendente fica no disco e a gravação do dia seguinte leva tudo.
  O 04:45 e o :05 não caem em cima de nenhum laço de hora em hora do Nexus (tarefas :10 a :20, normalizações :22, sync do App
  :25, zeladoria :32, carga :40, chamados :50; os ativos do OS Creator às :08 e :38 das 06h às 22h e às 02:15). **O pendente tem teto de 3 dias** (`MAX_HORAS_PENDENTES` = 72 horas, as mais
  novas): as mais velhas saem, com aviso no log. **Reinício:** o pendente é relido no boot (arquivo quebrado é ignorado, com
  aviso, e a linha ruim é ignorada sem levar as boas; a mesma chave que o parcial velho traz de volta fica uma só, a mais
  nova: sem isso o grão quebraria e a gravação subiria para sempre). **O que um reinício perde:** só a hora aberta do contador
  do Fracttal (ele não guarda parcial em disco) e até 5 min do uso (o parcial é de 5 em 5); o que já saiu dos contadores está
  no disco. Teste sem sessão não tira nada dos contadores. No banco entram a rota, a hora e contagens: nunca o e-mail, o nome
  nem o setor (a rota que traz um `@` no caminho vira `<id>`; o corte por setor fica só no disco, acima). Regras do fato, da
  chave e da leitura segura: `nexus/dados/CLAUDE.md`, linha "Uso do OS Creator e pedidos ao Fracttal".
- **Prova:** `tests/test_casca_uso_os.py` (um Flask de mentira com rotas `/os/...`, o Fracttal falso do `requests`, o relógio
  na mão e, para o JavaScript, o `node` rodando o `enviar` do Histórico, o `pedir` e o `acomp.js` de verdade) e, para a
  gravação e o laço, `tests/test_dados_fato_uso_os.py` (a API do banco de mentira, inclusive a que devolve tudo como texto;
  o disco de hora em hora, as 04:45, a virada do mês, o pendente que sobrevive ao reinício, quebrado e com teto de 3 dias).

### A seção "Uso do OS Creator" do Raio-X (31/10/2026)

O antes e o depois de cada etapa do canto central do OS Creator, e os horários de pico de verdade (`raio_x.montar_uso_os`,
`_uso_do_banco`, `_secao_uso_os`; `templates/raio_x.html`, âncora `#uso-os-creator`, link no alto da página; só administrador,
como o resto do Raio-X). Quatro quadros, todos da janela de 7 dias de Brasília que termina hoje:
- **Por dia:** cliques, pedidos que as telas fazem sozinhas, pedidos ao Fracttal, recusados (406/429), os que esperaram a
  vez no porteiro (etapa 5) e o maior pico por minuto, com a hora dele. É o quadro do "antes e depois": o mesmo dia da
  semana, antes e depois de uma mudança.
- **Por hora do dia** (a soma dos 7 dias): cliques (com barra), automáticos, pedidos ao Fracttal, os que esperaram a vez e
  o maior pico por minuto **ao lado da cota de 200** (`fracttal_conta.COTA_POR_MINUTO`; o porteiro segura o Nexus em 150,
  `TETO_POR_MINUTO`): a partir de 80% a palavra é "perto da cota" (amarelo), a partir de 100% "na cota" (vermelho), sempre
  palavra e cor por token. As esperas vêm do mesmo total da hora que os pedidos (`esperas_qtd`); a hora de antes do
  porteiro, com a célula vazia no banco, conta 0 (ninguém esperava), e o resumo só fala delas quando houve alguma.
- **As 15 telas mais pedidas** (por pedidos, cliques mais automáticos): cliques e automáticos em colunas separadas (sem
  isso a "tela mais clicada" seria o `/os/_nexus/sessao` de cada aba aberta), a mediana e o p95, os pedidos que a tela faz
  ao Fracttal, os erros e os 503 do teto.
- **Por setor:** cliques, automáticos e as 3 telas mais clicadas de cada setor.

**De onde vem** (três camadas, a mais nova vence): **de ontem para trás, o banco** (`fato_uso_os.ler_dias`, lê o livro de
cada mês que a janela toca, dois na virada, e só as abas do uso e do total da hora: o detalhe do Fracttal é a aba maior e a
seção não o mostra); **o que ainda não foi às 04:45, o pendente no disco do servidor** (`uso_os.linhas_pendentes()`, que é o
arquivo `uso_os_pendente.json` relido no boot); **a hora aberta, a memória dos contadores**. O corte por setor vem de
`uso_os.instantaneo()["setor"]` (o arquivo do disco mais o que entrou depois do último salvamento; **nunca vem do banco**).
Na mesma chave (hora × rota × automático, ou a hora do total) o pendente vence o banco e a memória vence o pendente, e a
linha que está nos dois lados (o processo morreu entre gravar e limpar o pendente) não conta duas vezes. **A gravação das
04:45 invalida a cópia de 10 min** (`_uso_do_banco`: a leitura que começou antes de `uso_os.gravou_em()` é velha): o que saiu
do pendente para o banco não estaria na cópia de antes, e o dia de ontem sumiria por até 10 min. **A página nunca espera o
banco:** a leitura roda numa thread à parte (`nexus-raio-x-uso`),
**guardada 10 min** (`CACHE_USO_S`); a página espera no máximo 2 s por uma leitura nova (`PRAZO_USO_S`) e, passou disso,
mostra a cópia de antes (com a hora dela) ou "sem medição ainda, lendo o banco"; leitura presa não abre outra, e depois de uma
falha só tenta de novo passado 1 min. Banco fora com a memória cheia mostra a memória e diz que é só ela, desde o último
reinício. Teste sem a sessão do banco (`app.extensions["nexus_dados_sessao"]`) nunca vai à rede.

**A conta.** O total do Fracttal e o pico por minuto vêm da aba do total da hora (1 linha por hora; no pendente e na
memória é a linha `*` que o contador entrega, separada por `fato_uso_os.separar_total`): o detalhe por origem não entra, e
somaria em dobro. A
mediana e o p95 de vários dias são **aproximados**: cada hora guarda só os dela, e juntar horas é o quantil dos quantis,
pesado pelos pedidos atendidos (os recusados pelo teto não têm duração); a página diz isso. **A hora do reinício** (todo
deploy) tem os pedidos ao Fracttal só de depois dele: o contador do Fracttal não guarda parcial em disco (o do uso das
telas guarda), então o total e o pico por minuto dessa hora podem estar abaixo do real. **Sem dado** (o PC sem o
servidor, o banco fora sem nada no disco nem na memória, o servidor que ainda não guardou a 1ª hora): "Sem medição ainda", com o
motivo, e a página abre igual; a conta que quebrar vai ao log e a seção diz que não montou, nunca derruba o Raio-X.
Prova: `tests/test_casca_raio_x_uso_os.py` (7 dias gravados pelo `fato_uso_os.gravar` num banco de mentira, o pendente e a
memória dublados, o relógio na mão; cada número da conta, o pendente que vence o banco sem contar em dobro, a cópia de 10 min
e a gravação das 04:45 que a invalida, a aba do detalhe que não se lê, o banco fora, lento e vazio, e as cores só por token).

**O canto central na mesma seção (31/10/2026, item 0 da 3.1+3.2; âncora `#canto-central`, link no alto).** O Levi não tem
acesso ao servidor: a 1ª noite do leitor dos ativos do OS Creator (a paridade REST x RPC, as descrições que o detector da foto
cortou) só se confere pela tela. Depois dos quatro quadros do uso, cada peça do canto central diz o seu estado em linhas
(rótulo e frase, montadas em `raio_x._secao_canto_central`; a macro `peca` do template só as lista): **"Ativos centrais"**
(`ativos_central.estado()`): o catálogo (quantos, fonte, lido em, os novos do dia, a versão), se o leitor do servidor está
ligado e pronto, a paridade do REST (quando, se valeu, as coberturas `cob_ref` e `cob_rest`, e o motivo se não valeu), o REST
(a última leitura boa e a falha que veio depois dela), **a última noite** (revisão final: a hora e quanto levou, se o catálogo
aceitou ou "NÃO TROCOU O CATÁLOGO", os pedidos e as contagens, o resultado e a foto do banco: gravou, linhas, mudaram, entraram,
saíram, o erro; `ativos_central.anotar_noite`, no `ativos_estado.json`, para sobreviver ao reinício), a troca recusada, as
descrições cortadas da última noite (o número e até 5 ids) e a cópia em disco; e **"Lista central de OS"** (3.2, `os_central.estado(medir_memoria=True)`): quantas OS e quantas abertas, as "a
conferir" e as pendentes, a janela lida inteira e a marca d'água (a criação mais nova lida até o topo: até onde as telas
conferem, rodada 2 da 3.3), se o leitor está ligado, a última entrega de cada faixa (com quem entregou as
abertas: o `tarefas_os` ou o próprio leitor) e a última leitura dela (os pedidos, ou a falha com o motivo; "DEFEITO do
leitor" quando foi exceção que não é de leitura, com a pilha no log; depois de um reinício a última leitura de cada faixa, ok ou
falha, volta do cabeçalho da cópia em disco, `os_central.anotar_leitura`, em `leituras`), a leitura que a trava de encolhimento recusou ("Trava de
encolhimento": a faixa, a hora e o motivo, só com contagens, até a faixa passar de novo) e a última que ela aceitou na 2ª
leitura igual ("aceita na 2ª leitura": o apagamento de verdade, rodada 2), os campos que o REST trouxe (a
sondagem da 1ª noite), as conferências das telas que leem da lista ("Conferências das telas", 3.3, `_conferencias_das_telas`:
por tela, histórico, garantias e investigar, quantas foram ao Fracttal desde o último reinício, quantas divergiram, falharam e
ficaram "sem resposta pela página" (mais OS depois da marca do que a página da conferência traz, ou fora da ordem da
criação), e a última divergência com as duas contas até a marca; desde a rodada 2 a conferência é UMA por pessoa e período,
sem visão, status nem etiqueta, e exata; quem diverge com a lista tendo MAIS que ela não é conferido de novo por 30 min, então
cada pessoa restrita conta uma vez por janela; muitas divergências de quem vê tudo é sinal de lista errada, e muitas "sem
resposta", de que a página não basta), a cópia em disco e a memória
(`os_central.memoria_estimada`: cada registro e texto contados uma vez;
~0,4 s com 36 mil OS, medida UMA vez por versão da lista, e a falha da medida vai ao log; 25,8 MB contra os 23,9 MB do
tracemalloc); e **"Catálogos pequenos"** (4.1, `catalogos.estado()`, `raio_x._linhas_dos_catalogos`): uma linha por catálogo
(pessoas, etiquetas, tipos e classificações da OS, grupo e classificações da solicitação, falhas do COS, status da
solicitação, motivos de cancelamento) com quantos itens, de onde veio (o REST da empresa ou o RPC pela sessão de quem usa),
quando foi lido, a idade contra o prazo, VENCIDO e se está renovando, a última falha, as leituras do Fracttal neste processo e
a cópia em disco (o que o boot leu, quando gravou, o erro); a linha **"Pessoas pelo REST"** (o laço do servidor: ligado ou
por que não, a próxima leitura, se está valendo, a última boa e a falha depois dela, com o campo que o REST não trouxe); e a
**"Planos da Performance"** (quantos ativos com os planos guardados, os vencidos, os detalhes, a falha e o disco). Só
contagens, datas, ids e motivos: nunca o texto de um ativo ou de uma OS, nem nome nem e-mail de pessoa. **O Raio-X não
importa o OS Creator:** lê o módulo de `sys.modules` (no PC, sem ninguém ter aberto o OS Creator, ele nem está na memória, e
a peça diz isso), e a peça que quebrar vai ao log e diz que não montou, nunca derruba a página. Prova:
`tests/test_oscreator_canto_no_raio_x.py` e, para os catálogos, `tests/test_oscreator_catalogos.py::test_os_catalogos_no_raio_x`.

## Chaves do Nexus (Base → Chaves das fontes → aba Nexus, 14/10/2026)

Levi, sobre pôr a chave das contestações no servidor pela T.I.: "Se precisa de TI então vou ter que mandar um arquivo novo
de deploy para a TI ué!". Depois de colar a 1ª ("deu certo"): "bote essa informação na seção Chave das fontes!" — a
página é a aba **Nexus** de Base → Chaves das fontes (`/t/base/chaves-fontes?aba=nexus`, ao lado da aba "Fontes da
Performance", a tela /tokens da plataforma; as abas saem do `registrar_molduras(..., abas=...)`). O `/t/base/chaves-nexus`
recebe o formulário (POST, só administrador; o GET leva à aba). Código em `nexus/auth/chaves.py`: a chave colada é
conferida e gravada em `chaves.json` na pasta de dados (`NEXUS_DADOS`, fora do git), CIFRADA com AES-256-GCM
numa chave derivada da `NEXUS_SECRET_KEY` (HKDF) e presa ao nome. Vale na hora (relida a cada 30 s e logo depois de
gravar) e VENCE a do .env; "Apagar" volta à do .env. A tela nunca mostra o valor; o log diz quem gravou qual, sem o valor.
- **Só as chaves de `chaves.CHAVES`**, cada uma com a conferência dela: a `NEXUS_CONTESTACAO_CHAVE_PRIVADA` (32 bytes
  em base64 que viram X25519 e, havendo contestação no banco, abrem pelo menos uma; a de outro par é recusada) e, desde
  14/10, a `NEXUS_ACESSOS_5080_PUBLICA` (a pública do Dashboard Thopen: 32 bytes que viram X25519; não há como conferir
  contra o painel, a prova é a pessoa entrar) e, desde 16/10, o `NEXUS_PCM_GITHUB_TOKEN` (o token do repositório do
  PCM: o servidor não tinha, e a tela de publicar a W43 dizia "sem token do GitHub"; a conferência só LÊ o GitHub: o token
  tem a forma ghp_/github_pat_, o GitHub o aceita, ele enxerga o repositório, a conta pode gravar e, sendo clássico, tem o
  escopo repo ou public_repo; `pcm/publicar.token` usa o da tela primeiro) e, desde 06/11, a
  `OS_WEB_PERFORMANCE_RESPONSAVEIS` (a equipe da Performance na Nova solicitação do OS Creator: uma lista de nomes, a única
  com `texto` — os espaços de dentro ficam; ao menos um nome, sem dígito nem "@"; a ponte do OS Creator a lê pelo gancho
  `solic_eng_web.LER_NOMES`, por cima do .env do OS Creator). A tela não edita o .env: nome fora da lista é recusado.
- **Quem lê usa `chaves.valor(nome)`** (a da tela e, sem ela, a do .env), nunca `config.get` direto: as Contestações
  (`nexus/contratos/contestacoes.py`) e os Acessos dos clientes (`nexus/contratos/acessos_clientes.py`) leem assim.
- **NEXUS_SECRET_KEY trocada:** a gravada não abre; vale a do .env (ou nenhuma), e a tela diz "não abre, cole de novo".
- **Chave nova na tela:** uma entrada em `CHAVES` com o nome, o para quê, o arquivo de onde vem e a conferência, e quem
  lê passa a usar `chaves.valor`. Prova: `tests/test_chaves_nexus_14_10.py`.

## Telas por setor: o que cada pessoa vê (Base → Acessos, 12/10/2026)

Pedido do Levi (12/10/2026): "gostaria de uma seção no BASE > ACESSOS onde eu possa controlar o que cada pessoa de setor
pode ver ao logar no Nexus. A que não tiver setor vai aparecer a mensagem 'Sem setor, fale com o responsável' [...]
Criarei um setor chamado 'Administrador' onde será liberado todas as seções para essas contas! Exclua a parte de
cadeiras já que os setores irão substituir!". No mesmo dia ele voltou atrás no setor "Administrador": "não acho legal
deixar como setores pois eu por exemplo sou da performance mas também sou administrador". A cadeira (o seletor do topo,
que só reordenava o menu) saiu: no lugar dela o topo mostra "Setor: X". O código: `nexus/auth/setor_telas.py` (regras e portão) e `telas_acessos.py` (a seção).

- **O setor da pessoa** é o da tela Base → Acessos → Pessoas e setores (`nexus/cadastro/setores.py`, livro `nexus_setores`). A
  pessoa do login se acha pelo código do e-mail (`pessoa_hmac`, com a `NEXUS_PESSOA_HMAC`), o mesmo que a decisão de
  setor grava; nome e e-mail nunca vão ao banco (regra 8).
- **A matriz** setor × tela mora no livro `nexus_setor_telas · fato_decisao_tela_setor` (catálogo: fato
  `decisao_tela_setor`): só acrescenta, e vale a última decisão de cada setor × tela; a tela é `torre/tela`, o endereço
  do menu. Setor novo nasce sem nada marcado. O Salvar relê o banco, grava só o que mudou e troca a aba inteira (o
  `livros.publicar` confere a contagem). O portão e a tela leem com cópia de 1 minuto.
- **Tela que mudou de endereço e tela de dentro (13/10/2026, os relatórios na Central de emissão).** A decisão gravada
  com o nome antigo vale para o novo (`setor_telas.RENOMEADAS`: `performance/relatorio` → `relatorios/relatorio`, e o
  semanal), e a mais nova ganha, como sempre; quem já via o relatório na Performance continua vendo. A tela que abre por
  dentro de outra (`Tela.dentro_de`) não é item do menu, mas é marcada na matriz como qualquer tela; quem tem ela
  liberada vê a de fora sem marcá-la (`setor_telas.com_as_de_fora`, no `acesso`): o relatório liberado traz a Central.
- **Tela do setor (13/10/2026).** `Tela.do_setor` = o setor dono, pelo `setor_id` (`cadastro/setor_ids.py`; até
  04/11/2026 era o nome, sem acento nem caixa, e renomear o setor tirava a tela dele calado; o "Responsável UFV" do banco
  já não casava com o "Responsáveis UFV" do código): quem é dele vê a tela SEM marca (`setor_telas.das_do_setor`, somada
  às marcas no `acesso`). Setor que o código conhece, só pelo ID: o nome fica para mostrar, e
  `tests/test_setor_por_id.py` cobra. Pode ser mais de um (uma tupla de IDs,
  `setor_telas.donos_do_codigo`, 16/10/2026: o Gerar a semana e o Quadro da semana do PCM são do PCM e do Responsáveis
  UFV, os supervisores); a Central, que mostra um dono por relatório, usa o primeiro. Os três relatórios da plataforma na Central
  são da Performance (Levi: "Potência ativa faz parte da performance!", "Esses dois são do setor performance") e os quatro
  do PCM, do PCM. Na matriz a caixa dela aparece marcada e presa, com "do setor", e o Salvar não grava decisão para ela;
  outro setor segue pela marca. **O dono de cada relatório se escolhe na Central** (14/10/2026, Levi: "adicione a opção
  de eu escolher de qual setor é o relatório! Apenas administradores podem editar!"): a seção "Setor de cada relatório",
  só para administrador, grava no livro PRÓPRIO `nexus_relatorio_setor` (`auth/dono_relatorio.py`; não no
  `nexus_setor_telas`, porque gravar troca o livro inteiro e uma gravação apagaria a outra aba). A escolha vale por cima do
  `do_setor` do código, pelo `setor_id` (o setor renomeado continua dono; `setor_telas.escolhas_de_dono`, cópia de 1 min
  como a das telas); "Nenhum setor" = só o administrador e os marcados. Prova: `tests/test_relatorios_dono_setor.py`.
- **Quem vê o quê.** Administrador é **só** a lista de Administradores (`NEXUS_ADMINS`, a lista desta tela, a senha):
  vê tudo, com ou sem setor, porque é quem configura e não pode ficar trancado fora. **Setor nunca dá administrador**:
  um setor chamado "Administrador" é setor como os outros (existiu assim por algumas horas em 12/10/2026 e saiu), e o
  administrador que tem setor (o Levi, na Performance) segue vendo tudo; o setor dele só aparece no menu da conta e na lista de
  Administradores. Os setores veem só as telas marcadas, no menu e no Início (os cartões e os
  números contam só elas); setor sem nenhuma tela vê o Início com o aviso. Sem setor (ou com o setor excluído): toda
  página dá 403 com "Sem setor, fale com o responsável." (`templates/sem_setor.html`) e todo pedido de dados, 403 em
  JSON; abrem só entrar, sair, tema, saúde e static (`setor_telas.LIVRES`).
- **O portão** (`setor_telas.portao`, no fim do `instalar_portao`; só a sessão que nasceu do Fracttal passa por ele): a
  rota de uma tela segue a marca dela (o id mais longo que casa: `performance/clima/mapa` tem barra); o resto da torre
  (dados, sub-rotas, o `/passe` da moldura) abre para quem tem ao menos uma tela da torre; `/os/*` é a torre OS (as telas
  `/t/os/*` abrem nele), menos as ações `/os/_nexus/*`, que são do Campo e do HSEQ e seguem a régua de cada uma. A
  sessão que o passe já abriu na plataforma (telas da Performance) segue o login de lá até a moldura renovar.
- **Banco que não responde não é "sem setor":** sem nenhuma leitura boa, a página diz "Não consegui ler o seu setor
  agora" (o administrador entra igual); com a cópia velha, vale ela.
- **A leitura nunca prende o clique** (`setor_telas._no_clique`). O portão lê os setores e as telas a cada clique de
  toda sessão do Fracttal (o `_admin_em_dia` também), e os livros esperam até 60 s por pedido, sem renovar a cópia
  quando falham: com o banco lento, todo clique, até o do administrador, ficaria preso. Por isso: cópia fresca (1 min),
  ela; cópia vencida, ela na hora e a releitura em segundo plano (uma de cada vez, no máximo a cada 30 s); sem cópia, lê
  com prazo de 8 s por pedido (`_Curta`), e a falha faz os cliques dos 30 s seguintes responderem "não consegui ler" sem
  ir ao banco. A tela Acessos lê do jeito normal (é de administrador e precisa do dado de agora).
- **Liga e desliga:** `NEXUS_ACESSO_POR_SETOR` (vazio = ligado; `0` = todos veem tudo nesta máquina). Sem a
  `NEXUS_PESSOA_HMAC` fica desligado, porque sem ela ninguém teria setor e todos ficariam trancados fora. A seção diz
  qual é o caso. Nos testes (TESTING) só liga quando o teste pede.
- **O acesso de cada pedido fica no próprio pedido, não no `g`** (12/10/2026): o `g` é do contexto da aplicação, e um
  contexto já aberto (o do teste com o banco falso, um job) é emprestado a vários pedidos. Guardado no `g`, o acesso do
  administrador vazou para o pedido da pessoa do setor, que viu tudo; o teste pegou.
- **A seção:** os setores em botões (quantas telas e quantas pessoas), o escolhido com a árvore do menu em caixas (a caixa
  da torre marca a torre inteira; "Copiar de" outro setor; Marcar tudo e Limpar; aviso de mudanças não salvas, e trocar
  de setor com elas pergunta antes), e o Salvar. Os números do topo ganharam "Setores" e "Entraram sem setor"; a
  lista de quem entrou e a de Administradores, a coluna Setor (pelo código do e-mail).
- **Ao ligar num servidor** quem não tem setor passa a ver só a mensagem, e o setor sem telas marcadas, só o Início.
  Antes de o código novo subir, ponha as pessoas nos setores (Acessos → Pessoas e setores) e marque as telas de cada setor.
- **Prova:** `tests/test_setor_telas.py` (a matriz e o setor pela última decisão; o caminho segue a tela, a torre e o OS
  Creator; sem setor só a mensagem; o setor vê só o marcado, em página e dados, e fechar vale no clique seguinte; setor
  nenhum dá administrador e o administrador com setor vê tudo; banco fora não vira "sem setor"; desligado ou sem a chave,
  todos veem tudo; a seção grava só o que mudou e recusa setor excluído, tela desconhecida, sem token e sem o código; quem
  entrou e cada administrador aparecem com o setor; o livro no catálogo, sem nada pessoal) e `tests/test_torres.py` (o menu só com as telas
  do setor).

## Pré-carga das telas de quem tem setor (12/10/2026)

Levi (12/10/2026): "para esses que tem setores, exceto sem setores e administradores - assim que entrar já pré carrega
tudo o que está disponível para aquela pessoa, pode fazer por partes mas é interessante que fique cada vez mais leve da
pessoa abrir uma informação e analisar!". O código e as regras: `nexus/auth/pre_carga.py`.

- **Por que funciona:** medido em 12/10/2026 num processo novo, o 1º clique é que pesa (Clima e risco 9,8 a 15,9 s,
  Visão do responsável 9,7 a 10,8 s, Confiabilidade 3,0 s, Rondas 2,6 a 2,9 s, Governança 2,4 s, Gestão PCM 0,9 a 1,0 s);
  aberta de novo, toda tela fica abaixo de 0,1 s. O peso é encher as cópias do servidor (banco, INPE, INMET, NASA), e as
  cópias são de todos.
- **Quando e como:** o portão chama `pre_carga.lembrar` a cada pedido de quem tem setor e não é administrador (no máximo
  uma vez por minuto por conjunto de telas). Uma thread só abre por dentro as telas liberadas que esfriaram (o
  `test_client` do app, sessão interna de administrador sem login do Fracttal, com o cookie no cabeçalho e
  `use_cookies=False`: com o pote, o Werkzeug apaga o cabeçalho e a sessão não chega), uma por vez e com 0,3 s entre
  elas, a 1ª tela de cada torre primeiro. Enquanto a pessoa usa, repete a cada 2 min: a cópia que venceu é refeita por
  trás (com 4 min, a cópia de 5 min revista aos 4 vencia aos 5 e só seria refeita no clique de alguém).
- **Fora:** administradores e quem não tem setor (pedido do Levi); as telas que leem o Fracttal ao abrir (`FORA`:
  Confiabilidade, Quadro da equipe e Aprovação de OS; a cota de 200/min é da empresa e o App vive
  dela); o OS Creator; e as telas da plataforma na moldura (o peso é da plataforma, que tem pré-carga própria). Tela que
  leia o Fracttal na pré-carga assim mesmo é anotada pelo `campo.fracttal.marcar_pre_carga`, sai da volta até o Nexus
  reiniciar e o log pede para pô-la na `FORA` (regra em `nexus/torres/CLAUDE.md`).
- **Medido antes e depois** (12/10/2026, dado real, uma pessoa da Supervisão Campo com as 50 telas que o Levi marcou, o
  Fracttal bloqueado): sem a pré-carga, os 40 primeiros cliques somaram 35,3 s (8 acima de 0,5 s); com ela, a volta abriu
  35 telas em 39 s de relógio, sem erro e sem Fracttal, e os 40 cliques somaram 1,0 s (nenhum acima de 0,5 s; Clima
  15,9 → 0,08 s).
- **Onde ver:** a seção Telas por setor (Base → Acessos) diz se está ligada, se está aquecendo e a última volta (quantas
  telas, quanto tempo, a mais lenta). `NEXUS_PRE_CARGA=0` desliga numa máquina; nos testes só liga quando pedido e roda
  na hora, sem thread.
- **Ao subir, para todo mundo (13/10/2026, Levi: "o link do servidor demorou muito para carregar"):** cada deploy
  reinicia o Nexus e esfria as cópias (no servidor recém-subido a 1ª janela da Meta levou 27 s). O `servir.py` e o
  `app.py` chamam `pre_carga.aquecer_ao_subir`: **5 min** depois do boot, uma volta inteira pelas mesmas telas. Não
  30 s: a 1ª volta abre também as telas que pedem leitura ao Fracttal, e aos 30 s ela juntava as leituras que a subida
  espaça de propósito (20 s a 210 s), estourando a cota da empresa (o 429 das fotos das rondas). Máquina com
  `NEXUS_CAMPO_AQUECER=0` não roda. O `servir.py` passou de 8 para 16 threads (os pedidos esperam a rede; com 8 presos numa tela lenta,
  o resto esperava na fila).
- **O estático com versão (13/10/2026):** todo `url_for('static', ...)` sai com `?v=<commit>` e, com ele, o navegador
  guarda o arquivo 1 ano (`public, max-age=31536000, immutable`, em `create_app._instalar_cache_estatico`); antes cada
  página reconfirmava cada arquivo (`no-cache`). Commit novo = endereço novo; sem o commit ("local") ou sem o `v`, fica
  como antes.
- **Prova:** `tests/test_pre_carga.py` e `tests/test_nexus_servidor_13_10.py`.

## Versão no ar e Atualizações no Início (13/10/2026)

À tarde, Levi: "Quero que no início do Nexus diga quando foi o último commit para eu acompanhar se está realmente subindo
automático para o server". À noite, o cartão foi enxugado ("tire as informações de github, preso em 24hrs e essas
observações abaixo do commit") e ganhou a aba ("Inclua no início uma sub aba de atualizações mostrando as últimas
atualizações dos commits e o que mudou! Ao clicar em versão no ar já leva para lá!"). Em `casca/versao.py`:

- **O cartão "Versão no ar"** (o 4º dos números do Início): a hora do commit em execução (grande), o commit curto (o mesmo
  do `/saude`) e "no ar desde" (a hora em que este processo subiu, o import da casca; cada deploy reinicia o Nexus, então
  é a hora em que a versão entrou). O cartão inteiro é o link para as Atualizações. Saíram o semáforo com o GitHub (e a
  conferência por trás dele: API do GitHub e `git ls-remote`), o assunto do commit e os pedidos presos.
- **As abas do Início** (`gc-subabas`, um só `_inicio_abas.html` incluído em `inicio.html`, `atualizacoes.html` e `sugestoes.html`): Visão geral | Atualizações | Sugestões.
- **A aba Atualizações** (`/?aba=atualizacoes`, exige login como o Início; era `/atualizacoes`, que no servidor ia à plataforma, ver "Regras que já custaram caro"): **só as novidades, as correções e as melhorias de desempenho (`feat`, `fix` e `perf`) dos últimos 60 dias** (o
  `perf` desde 24/10/2026: o Levi não achou ali a correção da lentidão do dia, um `perf`; 19/10/2026,
  Levi: "deixe só novidade e correção, sempre os últimos 60 dias!"; até então eram os últimos 60 commits de todo tipo). O
  `git log` lê 61 dias (no máximo 3.000 commits), uma vez por processo (o deploy reinicia e a lista nova vem junto); o
  corte dos 60 dias e dos tipos é na hora do pedido (`versao.da_aba`), porque o processo pode ficar dias no ar. Em
  19/10/2026: 427 commits lidos, 304 na aba (207 novidades, 97 correções). Por dia ("Hoje", "Ontem", dd/mm/aaaa), do
  mais novo; desde 29/10/2026 só Hoje vem aberto e os dias antes dele recolhidos (Levi: "gostaria que os dias que
  fossem anteriores a hoje ficassem recolhidos e contando a quantidade de correção, novidade e desempenho"): o
  cabeçalho do dia diz quantos de cada tipo (`versao.contagem`, só os que têm item), o "no ar", se o dia o tem,
  e o total do dia na ponta direita, sem fundo ("bota o total sem fundo colorido bem sólido mesmo")
  (o clique no cartão da versão acha o dia mesmo recolhido); abre com um clique, sem JavaScript (`<details>`). Cada um: o tipo, a área (o que vem entre parênteses), o commit, a manchete (o texto antes do " - ") e o
  resto, e o corpo em tópicos num "O que mudou", sem a prova nem a coautoria. Sem horários. O "no ar" vai no commit EM
  EXECUÇÃO, que pode nem estar na lista (uma documentação, um merge): aí nenhum item leva. Nenhuma novidade nem correção
  no período: a aba diz isso (diferente de "sem git").
- Sem git (a vitrine estática, uma pasta copiada): o cartão diz "—" e a aba diz que não há histórico. O `/saude` segue
  enxuto (`{"ok", "commit"}`: o `deploy/atualizar.sh` lê o commit dele).
- **Prova:** `tests/test_casca_versao.py` (o git dublado).

## Sugestões no Início (24/10/2026)

Levi: "em início quero uma sub aba chamada 'Sugestões'. Vai ter uma tela para a pessoa sugerir, os administradores verão
em lista a pessoa que pediu, o que pediu e anexos ... Bote um limite no tamanho desses arquivos para não pesar tanto no
server".

- **Onde**: `/?aba=sugestoes` (o Caddy só manda a raiz exata ao Nexus). O envio é `POST /?aba=sugestoes`, o único POST da
  raiz (`POST /` sem a aba = 405). Rota em `casca/__init__.py` (`_sugestoes`), regra em `casca/sugestoes.py`.
- **Quem manda**: qualquer pessoa com login (Microsoft ou Fracttal). A senha de administrador não diz quem é: lê a lista,
  mas não manda. **Quem lê**: só `session["admin"]` vê "Sugestões recebidas" e baixa os anexos (o resto, 403).
- **Campos**: título (120), descrição (4.000, guarda as quebras de linha), área = as torres que a pessoa vê
  (`_torres_da_pessoa`, a mesma conta dos cartões do Início; vazio = "Nenhuma em especial"; área fora delas é recusada)
  e anexos.
- **Limites dos anexos**: 5 arquivos, 5 MB cada, 15 MB juntos; `.md .txt .pdf .doc .docx .png .jpg .jpeg .webp`, e o
  conteúdo confere pelo começo do arquivo (executável renomeado não passa). Pedido com corpo acima de 16 MB é recusado
  pelo tamanho declarado, antes de ler o formulário (`request.max_content_length` segura o que vem sem tamanho). A tela
  confere no navegador antes de enviar; o servidor confere de novo. Anexo recusado recusa a sugestão inteira, com o
  motivo.
- **Onde fica**: o livro `nexus_sugestoes · fato_sugestao` (registrado no catálogo, `so_cresce`; 1 linha por sugestão;
  em claro só `id`, o dia, a `area` e a pessoa por `pessoa_id` + `pessoa_hmac`; título, descrição, nome, e-mail e os
  nomes dos anexos cifrados pelo Cofre). Os anexos no disco: `<pasta de dados>/sugestoes/<id>/1.pdf` (nome neutro; o
  original só no livro). O banco que recusa apaga os anexos já gravados (nada órfão). O `novo_id` do formulário
  segura o duplo clique.
- **Proteção**: `moldura._de_outro_site()` + o código do formulário na sessão (`sugestoes_codigo`). Anexo servido com
  `nosniff` e `no-store`; imagem abre no navegador, o resto baixa.
- **Baixar arquivos** (24/10/2026, Levi: "gostaria a opção 'Baixar arquivos' baixa todos os arquivos da sugestão"):
  `/?aba=sugestoes&anexo=<id>&n=todos` devolve um .zip com todos os anexos (o nome original; repetido ganha " (2)"),
  chamado pelo título da sugestão. Montado na memória (15 MB no máximo); só o administrador; sem anexo, sem o botão.
- **Status, Minhas sugestões e o contador** (28/10/2026, Levi: "Do lado direito tem um espaço para 'Minhas sugestões'";
  "opção de mudar o status da solicitação: Iniciada, Em verificação e Conclusão"; "As sugestões recebidas devem ficar
  recolhidas"; "um contador no cabeçalho ao lado de Sugestões mostrando quantas sugestões ainda não estão concluídas"):
  - o status é a 2ª aba do livro, `fato_status_sugestao` (1 linha por mudança, só acrescenta, vale a última; sem linha =
    **Nova**). Só o administrador muda, pelo `POST /?aba=sugestoes&acao=status` (a ação no endereço, e não no corpo: ler o
    corpo antes tiraria do envio das sugestões a recusa do pedido grande sem ler). A mesma mudança repetida não grava.
    **As duas abas vão juntas em toda gravação** (livro que só cresce recusa gravar sem uma aba que o banco tem);
  - **Minhas sugestões**, à direita do formulário (embaixo no celular): as da pessoa pelo `pessoa_hmac` (o código do
    e-mail, em claro no livro), com o status;
  - as recebidas vêm **recolhidas** (`<details>`): a linha diz o status, o título, quem e quando; aberta, o texto, os
    anexos e a troca do status. As que faltam concluir primeiro;
  - o **contador** ao lado de "Sugestões" nas três abas do Início = as não concluídas: de todos para o administrador, as
    da pessoa para ela. Sai da cópia de 1 minuto; velha ou ausente, a releitura vai **por trás** (`contador`) e a aba
    sai sem número: o Início é a primeira página de todos e nunca espera o banco por causa dele.
- **Prova**: `tests/test_casca_sugestoes_24_10.py`.

## Um cabeçalho só: quem entrou no topo do Nexus (13/10/2026)

Levi, com o print do topo do OS Creator dentro do Nexus: "Quero que essa visão de cabeçalho ao lado de sair vá para o
cabeçalho do Nexus e suma esse 2° cabeçalho tanto de OS Creator Web quanto de plataforma de performance! Dá a impressão
que é uma tela dentro de uma tela!".

- **Quem entrou** (`base.html`, `.usuario-*` no `nexus.css`): na ponta direita do topo, o avatar com as iniciais
  (filtro `iniciais` do `create_app`: primeiro + último nome, como o do OS Creator), o nome e o perfil do Fracttal (o
  `session.usuario`, o mesmo `get_conta_info` que o OS Creator mostrava; o e-mail no `title`). Sem perfil, só o nome. Quem
  entrou pela senha de administrador não tem nome: no lugar, só um ícone de pessoa (`.conta-sem-nome`). No celular, só o
  avatar (a regra que esconde o nome fica DEPOIS das `.usuario-*`: dentro do bloco do celular, lá em cima, ela perdia e
  o nome seguia).
- **O menu da conta** (03/11/2026, Levi: "esse negócio de tema e setor fique oculto nessa barra inicial, que só apareça
  quando clica no nome; aí vai ter: Setor, tema e sair"): quem entrou é o `<summary>` de um `<details class="conta-topo">`,
  e a caixa (`.conta-caixa`, navy como o topo e o sino nos dois temas) traz o Setor (só quem tem um), o Tema e o Sair. Na
  barra ficam só a marca, a ação da tela, o sino e o nome; o `.topo-espaco` vazio empurra o resto para a direita. Sem
  JavaScript abre e fecha no clique; com ele, fecha ao clicar fora, no Esc, e o sino e o menu da conta não ficam abertos
  juntos. No celular: linha 1 a marca e o Menu, linha 2 o sino e o avatar (numa linha só, a 375 px, o "Nexus" da marca
  entrava por baixo do Menu).
- **A ação da tela no topo:** o bloco `topo_acoes`, antes do sino. Hoje só o "Modo TV" do Painel NOC
  (`performance/moldura.html`); no celular ele some.
- **O OS Creator dentro do Nexus sem o topo dele:** a ponte (`torres/oscreator/ponte.py`, `_MARCA_NO_NEXUS`) marca com
  `os-no-nexus` a tela logo abaixo do Nexus (a casca, o login, o card da OS) antes de pintar, e o topo some. Aberto sozinho
  no navegador, o OS Creator fica com o topo (é o único lugar com o nome e o "sair").
- **A criação de OS numa janela por cima do Tempo real (13/10/2026)**, Levi: "Em performance > tempo real > criar OS ao
  invés de direcionar para o OS Creator aparece a tela de criação de OS sobrepondo toda a tela dando um blur de fundo,
  assim que a pessoa finaliza a OS só aparece a notificação de criação!". A plataforma abre `/os/performance/criar` com
  `?janela=1` num iframe que cobre a tela; a ponte (`_JANELA_OS`) a entrega sem o topo e embrulha o `fetch`: o POST de
  `/os/api/<x>/criar` que responde ok manda `{gc: "os-criada", mensagem, detalhes}` à página de baixo, que fecha a janela
  e mostra a notificação. O código do OS Creator não muda: quem embrulha o fetch é a ponte.
- **As telas da Plataforma de Performance sem a faixa** "<tela> · Plataforma de Performance": a faixa só nasce com
  controle (o seletor de usina do Diagnóstico). Ver `nexus/performance/CLAUDE.md`.
- **Prova:** `tests/test_sem_segundo_cabecalho_13_10.py` (7; 6 mutações pegas) e `tests/test_porta_tv.py`; no navegador,
  uma cópia de prova com uma pessoa de mentira e a plataforma do PC: o topo com "PE Pessoa Exemplo ADMINISTRATOR", o
  Performance do OS Creator começando no "← Voltar", o Tempo real e o Painel NOC sem a faixa (o "Modo TV" no topo), o
  Diagnóstico só com o seletor, o OS Creator aberto sozinho com o topo dele, 375 px só com o avatar, escuro e claro.
  O menu da conta (03/11/2026): `test_setor_tema_e_sair_so_no_menu_da_conta` (nada de Setor, Tema e Sair na barra) e o
  Setor dentro dele em `tests/test_setor_telas.py`; no navegador, numa bancada com uma pessoa de mentira no setor
  Performance, a 1440, 1024 e 375 px, escuro e claro: abre no nome, troca o tema sem fechar, fecha no clique fora e no
  Esc, e o celular sem rolagem lateral.

## Pedidos presos: o que o Nexus esperava quando parou (13/10/2026)

Levi: "As vezes o OS Creator Web fica em um loop infinito, isso é por causa do fractal?". No print o círculo "Carregando…"
girava sobre o Performance do OS Creator, e das 16:50 às 16:53 o Nexus do servidor não respondeu NEM o `/saude` (que não
lê nada), com a plataforma, no mesmo servidor, em 0,2 s. Não era deploy (o último push foi às 16:02; o deploy por push
entra em 1 a 5 min, conferido pelo `Last-Modified` dos estáticos do servidor) nem laço no código: o círculo do OS Creator
não tem limite e espera a página seguinte, e o waitress tem 16 threads; com as 16 presas, todo pedido novo espera na
fila. De fora não se vê ESPERANDO O QUÊ. O `casca/presos.py` vê de dentro:

- **registro:** o `ligar` embrulha o `wsgi_app` (método, caminho SEM a query, início, thread; sai no `close()` da
  resposta). A pré-carga fica de fora (cabeçalho `X-Nexus-Pre-Carga`: ela roda no `test_client`, fora das threads do
  waitress). Quem liga é o `servir.py` (com `THREADS` = 16, o mesmo número do `serve`) e o `app.py` (8, ou 32 com a
  plataforma no PC; lá a conta das threads divide com a plataforma, então "fila cheia" é aproximada); o `create_app`
  nunca liga, e os testes ficam sem.
- **ronda:** a cada 5 s; pedido com mais de 30 s é PRESO. A pilha da thread dele (`sys._current_frames`) vira
  `quem` (a linha NOSSA mais de dentro: Fracttal (OS Creator) no `os_creator/api.py` e nos módulos que saíram dele na
  etapa 5 do canto central, `_MOVIDOS_DO_API` (o `get_assets` esperando as 6 threads dele, no `ativos_carga`; o `dash_os`,
  que fala com o dashboard, e o resto da pasta são "OS Creator"), Fracttal (Campo), fotos das rondas, login do Fracttal,
  ou `arquivo:função`), `como` (a linha mais de dentro de todas: esperando a rede, outra
  thread, o banco, em pausa, trabalhando) e `onde` (`arquivo:linha função`). Vai ao log (WARNING `Pedido preso há N s:
  GET /caminho - quem, como (onde)`) quando prende e quando o rótulo muda. **O gancho do contador de pedidos ao Fracttal
  (`contado`, em `casca/fracttal_conta.py`) fica ENTRE quem pede e o requests e `_nossa` o ignora** (`_GANCHOS`): sem isso o
  `quem` de todo pedido esperando o Fracttal virava `nexus/casca/fracttal_conta.py:contado`, no log e no Raio-X.
- **episódio:** do 1º preso até 15 s sem nenhum; começa no início do preso mais antigo. Guarda o máximo de presos
  juntos, se a fila encheu (ocupadas >= threads) e os 40 pedidos que mais esperaram. Os últimos 30 ficam em
  `dados/casca/pedidos_presos.json`, gravado também a cada 30 s DURANTE o episódio: se o processo cair no meio, o boot
  seguinte o lê como "cortado" ("acabou com o Nexus reiniciando").
- **o resumo (`presos.cartao`)**: "Nenhum pedido preso em 24 h"; "Travou N vezes em 24 h" quando a fila encheu (ninguém
  mais era atendido) ou "Travado agora"; "Pedido preso N vezes em 24 h" quando só a pessoa do pedido sentiu; com o último
  (hora, duração, quantos juntos e onde a maioria esperava) e os pedidos com a linha de cada um. **Saiu do cartão do
  Início em 13/10/2026, à noite** (Levi: "tire as informações de github, preso em 24hrs"): o resumo segue para quem for
  diagnosticar (os testes o chamam direto), e o episódio vai ao log e ao `pedidos_presos.json` como antes.
- **O próprio waitress avisa a fila:** `waitress.queue WARNING Task queue depth is N` no log quando há pedido esperando
  thread. No servidor, `journalctl -u nexus | grep "queue depth"` diz se um travamento antigo (de antes deste registro)
  foi fila cheia.
- **Prova:** `tests/test_casca_presos.py` (11; 7 mutações pegas) e, de ponta a ponta, um Nexus descartável com 4
  threads e o RPC do Fracttal apontado para um servidor que aceita e nunca responde: 4 `GET /os/api/performance/contagens`
  com o catálogo de ativos vencido ficaram 45 s presos no `_rpc_call`, o `/saude` ficou sem resposta dos 7 s aos 42 s, a
  ronda escreveu "Fracttal (OS Creator), esperando a rede (nexus/torres/oscreator/os_creator/api.py:1093 _rpc_call)" e
  o cartão disse "Travou 1 vez em 24 h ... durou 45 s: até 4 pedidos presos juntos, com as 4 threads ocupadas; todos em
  Fracttal (OS Creator), esperando a rede".

## Entrar com a Microsoft da Grid Co. (14/10/2026)

Levi, 13/10/2026: "Conseguimos fazer o login do Nexus ser via microsoft só aceitando quem é da grid?". O fluxo e as
conferências moram em `nexus/auth/microsoft.py`; a ida, a volta e a sessão, no portão (`nexus/auth/__init__.py`). Prova:
`tests/test_auth_microsoft.py` (em 14/10, 25 de 25 mutações das conferências pegas, depois da revisão adversarial). Passo a passo da T.I.: DEPLOY.md, 7g.

- **Liga com quatro variáveis:** `NEXUS_MS_CLIENT_ID`, `NEXUS_MS_TENANT_ID` (o GUID do diretório), `NEXUS_MS_CLIENT_SECRET`
  e `NEXUS_MS_VOLTA`. Faltando uma, ou com o diretório escrito como domínio (nunca casaria com o `tid`), fica desligada
  e a porta é a do Fracttal, como antes.
- **Ligada, o Fracttal sai da porta**, também no servidor: o POST com e-mail dá 403, sem ir ao Fracttal e sem contar
  como senha errada. Ele fica no OS Creator: quem entrou pela Microsoft abre o OS Creator e o clone pede o login do
  Fracttal, como já pedia para a senha de administrador. A OS continua nascendo no nome de quem a cria (decisão de
  09/2026 para a plataforma: dois logins, "faz parte!"; o id_token da Microsoft não vale no Fracttal). Quem estava
  dentro pelo Fracttal quando a Microsoft ligou sai no próximo clique (`MOTIVOS["porta_microsoft"]`, também a sessão de
  antes, sem `via`): sem isso, ela seguia até o fim do token (que o clone renova), inclusive a de quem não é da Grid.
- **A volta é o próprio `/entrar`** (`?code=&state=`), porque o Caddy só manda ao Nexus o `/entrar` exato (regra "Rota
  nova só nos caminhos que o Caddy manda ao Nexus", abaixo). `response_mode=query`: com `form_post` a volta seria um POST
  de outro site, e o cookie Lax da sessão não iria junto.
- **Quem é da Grid:** o registro é de locatário único (o Entra recusa conta de outro diretório), e o Nexus confere de
  novo: `tid` e `iss` do diretório; não convidado (`idp` de outra casa, `#EXT#` no nome de usuário ou a declaração
  opcional `acct` diferente de 0, que pega o convidado criado dentro do diretório; a T.I. a liga no registro); e-mail de um
  domínio de `NEXUS_MS_DOMINIOS` (padrão gridco.com.br), comparado inteiro. Também confere `aud`, `nonce` e o prazo. A
  assinatura do id_token não é conferida porque ele vem direto do endpoint de token, por TLS, em troca do código, do
  segredo e do verificador PKCE (OpenID Connect Core, 3.1.3.7, item 6). Nada aceita id_token vindo do navegador.
- **Cada ida vale uma volta:** `state`, `nonce` e o verificador PKCE ficam em `ms_pedidos` na sessão (até 3 idas, 10 min
  cada), e a volta tira a dela, dê certo ou não. Uma volta sem a ida neste navegador (o código de outra pessoa num link)
  nem vai à Microsoft.
- **A sessão:** `via` = "microsoft", `usuario` {email, nome, perfil ""} e `ms_ate` = login + 12 h (`MOTIVOS["expirou"]`).
  Passa pelo `_admin_em_dia` e pelo portão de setor, como a do Fracttal, e NÃO cai com o Fracttal: `via_fracttal()` é
  falso para ela, e o `_fim_do_fracttal`, a ponte, a aprovação de OS, a assinatura da PT e a conferência de 5 minutos só
  derrubam quem entrou pelo Fracttal. Sessão de antes, sem `via`, é do Fracttal. O "sair", de qualquer lugar (o do OS
  Creator inclusive), sai de tudo. O login apaga o `os_sessao`: o Fracttal de quem usou o navegador antes não passa
  para quem entrou. O prazo da TV vem de `auth.prazo_da_sessao()` (o `fracttal_exp` ou o `ms_ate`).
- **`prompt=login`: toda entrada pede a senha da Microsoft**, como o Fracttal já pedia. A primeira versão usava o
  `select_account`, e a revisão adversarial de 14/10/2026 mostrou o furo: no PC da sala do NOC, A (administrador) sai,
  a conta de A segue no navegador e B a escolhe na lista e entra como A, sem senha. O Sair do Nexus não sai da
  Microsoft do navegador (sairia também do Outlook e do Teams da pessoa), e com a senha pedida não precisa.
- **Teto da volta por rede** (`("ms", ip)`, 50 em 15 min): só conta a recusa que custou uma ida ao endpoint de token por
  causa de quem tentou (código de lixo, conta de fora). Segredo vencido (`invalid_client`, AADSTS7000215/7000222) e
  Microsoft fora não contam, porque aí todo mundo falharia e a rede do escritório trancaria. Nada disso tranca a senha
  de administrador, que tem o contador dela.
- **Journal:** "Entrar com a Microsoft recusado: <motivo>", com o código AADSTS e o domínio, nunca o e-mail. O
  `error` da volta é texto de quem chama (qualquer um tem uma ida pelo `/entrar?ms=1`): só vai ao journal no formato da
  especificação (`[a-z_]`, até 40, inteiro), senão "desconhecido", e a volta com erro conta no teto.
- **HEAD é GET:** o Werkzeug põe HEAD em toda rota GET, e o `/entrar` só olhava `== "GET"`: o HEAD caía no ramo da
  senha de administrador, respondia 401 e contava erro (5 HEAD de uma rede, um `curl -I` ou a prévia de link de um
  chat, trancavam a reserva por 15 min). Desde 14/10 o `/entrar` trata HEAD como GET.
- **Antes de ligar:** o administrador, o setor e o papel no Campo são achados pelo e-mail. Quem usa no Fracttal um
  e-mail diferente do da Microsoft cai em "Sem setor" depois da troca: conferir em Base → Acessos.
- **O segredo vence** (até 24 meses no Entra): no dia, a tela diz "A chave do Nexus na Microsoft venceu..." e só a
  senha de administrador entra até a T.I. trocar a `NEXUS_MS_CLIENT_SECRET`.

## Regras que já custaram caro

- **Rota nova só nos caminhos que o Caddy manda ao Nexus** (13/10/2026, "Atualizações não carrega"): no servidor o
  Caddy divide por caminho (DEPLOY.md, 5b) e só a raiz exata, `/t/*`, `/entrar`, `/sair`, `/saude`, `/tema`, `/os/*` e
  `/static/*` (menos os três da plataforma) chegam ao Nexus. A aba Atualizações nasceu em `/atualizacoes`: abria nos testes
  e na 5070 direta, e no servidor caía na plataforma ("Not Found"). Virou `/?aba=atualizacoes`. A aba do Início é
  `/?aba=...`; tela de torre é `/t/<torre>/<tela>`; segmento novo na raiz pede a linha do Caddy com a T.I. e o
  `SEGMENTOS_NEXUS` da `ferramentas/porta_local.py` no mesmo trabalho. `tests/test_rotas_no_caminho_do_nexus.py` passa
  cada rota pela `porta_local.destino` (a mesma divisão) e pega a rota que o servidor não entregaria.
- **Endereço do Nexus nunca a partir da raiz** (09/10/2026): `href="/t/..."`, `redirect("/t/...")` ou `fetch("/os/...")`
  crus caem na plataforma debaixo do `/nexus`. Use `{{ raiz }}`, `url_for`, `|na_raiz`, `na_raiz()` e `nexusRota()` (seção
  do prefixo); `tests/test_prefixo.py` pega o esquecimento.
- **Rota pública é decisão consciente:** só o que está em `ROTAS_PUBLICAS` (entrar, saude, static e as quatro que o App de
  Campo chama assinadas com a chave derivada da `NEXUS_PESSOA_HMAC`, cada uma com o seu rótulo: a foto do extintor,
  `torre_hseq.extintores_foto_receber`, o texto da informação adicional da conferência, `torre_hseq.extintores_info_receber`
  (26/10/2026), a marca de motivo do técnico, `torre_pcm.motivo_do_app` (16/10/2026), e as fotos do inventário do
  almoxarifado, `torre_pcm.inventario_foto_receber` (30/10/2026, `nexus/pcm/inventario/fotos_app.py`)). O teste
  `test_toda_rota_nao_publica_exige_login` pega rota nova esquecida.
- **Limite de tentativas do Entrar** (auditoria A2 e revisão adversarial da porta única, 10/10/2026). Era 5 erros por
  IP: um colega errando a senha cinco vezes trancava o Entrar da sala inteira por 15 min (o escritório sai por um IP
  público só), inclusive a senha de administrador, e até o 429 do Fracttal contava. A A2 passou a contar só por e-mail, e
  a revisão achou o avesso: quem soubesse o e-mail de alguém (nome.sobrenome é previsível) mandava 5 senhas erradas de
  qualquer rede e o dono ficava 15 min de fora com a senha certa (provado: 5 erros de 203.0.113.9, e o dono, de
  198.51.100.7, recebia 429); repetindo, o dia todo. Agora (`nexus/auth/__init__.py`):
  - por **e-mail e rede**: 5 senhas erradas do mesmo e-mail (sem espaço, sem diferença de maiúscula) a partir do mesmo IP
    em 15 min trancam só esse par; a 6ª nem vai ao Fracttal (que tem o bloqueio da conta dele, de ~30 min). O dono, de
    outra rede, entra;
  - por **e-mail**, um teto de 20 em 15 min (`TETO_POR_EMAIL`), de qualquer rede, contra tentativas espalhadas;
  - o **navegador conhecido** (cookie `nexus_dispositivo`, assinado com a `NEXUS_SECRET_KEY`, gravado em todo login certo
    pelo Fracttal, 90 dias, até 8 contas por navegador, só com um HMAC do e-mail e não o e-mail) não é barrado pelas duas
    travas do e-mail: tem um contador só dele (5). É o "device cookie" da OWASP: o atacante não tem esse cookie para o
    e-mail de outro. O Sair não o apaga (ele não abre sessão);
  - por **IP**, um teto alto (`TETO_POR_IP` = 50 em 15 min) contra força bruta de muitos e-mails, para todos, com cookie
    ou sem; um login certo no meio não o zera. O IP é o do visitante: o `trusted_proxy` do `servir.py` lê o
    X-Forwarded-For do Caddy;
  - acertar zera os contadores DESTE e-mail (o par com a rede, o teto e o do navegador);
  - a **senha de administrador** tem o próprio contador (5 por IP): o Fracttal dos colegas não a tranca, e ela não tranca o
    Fracttal de ninguém;
  - **senha não conferida não conta**, e o motivo aparece. `fracttal.FracttalOcupado` (429/406, 5xx, limite, rede fora;
    lido da mensagem que o clone monta, porque ele não devolve o status) leva `motivo` (DNS, certificado, proxy, tempo,
    sem conexão, limite, Fracttal fora), `limite` e `detalhe` (a classe e a mensagem originais do `requests`, sem o
    e-mail). A tela diz "Fracttal ocupado (limite de pedidos da empresa), tente em instantes" no limite, e "Sem resposta
    do Fracttal: <motivo> ... se continuar, avise a T.I." no resto (503); o journal recebe um WARNING do logger
    `nexus.auth` com o erro original. Até a revisão de 10/10 tudo virava "ocupado" e o erro era descartado: com a saída
    do servidor para o Fracttal quebrada, todos veriam "tente em instantes" para sempre, sem log. A senha que passou com
    o JWT que não chegou à sessão do clone é `fracttal.SessaoNaoVeio` (era um "ocupado" mudo): 500, a tela diz e o
    journal registra um ERROR com de onde veio o `api._save_jwt` em uso. E-mail ou senha vazios nem vão ao Fracttal (400).
  Em memória, em `app.extensions` (estado global vazava entre testes): zera no restart. Prova: `tests/test_auth_limite.py`
  (inclusive pelo `api.fracttal_login` de verdade do clone, só com o `requests.post` falso: SSLError, DNS, proxy e
  tempo esgotado chegam ao log).
- **Login pelo Fracttal** (Levi, 06/10/2026: "Ao invés de uma senha difícil, no início faça a pessoa logar com
  fractall"): e-mail e senha do Fracttal (a senha vai transformada ao Fracttal e não é guardada; só a conta da Grid Co.
  entra). Um login abre o Nexus e o OS Creator: o JWT vai no cookie `os_sessao` (caminho prefixo + `/os`,
  12 h), assinado com a chave do clone, e `/sair` apaga os dois. Sessão do Nexus: `logado`, `usuario` {email, nome, perfil} (o nome aparece
  no topo), `admin` (o e-mail em `NEXUS_ADMINS` ou na lista da tela Base → Acessos, conferido a cada pedido: seção
  "Acessos") e `supervisor_padrao`: desde a estrutura de O&M de
  10/2026, o PAPEL de quem entrou na torre Usinas 360° (ex-Campo · App) ({pessoa_id, nome, papel: supervisor_campo | coordenador | gestor,
  regioes ou gestor}; o filtro que já vem marcado e quem vê o Aprovar; ver `nexus/torres/campo/CLAUDE.md`). Sessão de
  antes, com o nome do supervisor em texto, não vale como papel. A
  senha de admin segue em "Entrar com a senha de administrador" (`/entrar?admin=1`) e é a porta do Cadastro. **O login
  pela senha apaga o `os_sessao`**, como o da Microsoft (revisão final do inventário, 27/10/2026): o Fracttal de quem
  usou o navegador antes não passa para quem entrou, e nem o OS Creator nem a ponte do inventário falam com o Fracttal no
  login de outra pessoa; quem entrou pela senha e precisa do Fracttal entra nele pelo `/os/login`. Prova:
  `test_a_senha_de_administrador_apaga_o_fracttal_de_quem_usou_o_navegador_antes`. Quem
  tem conta no Fracttal entra, técnico inclusive: restringir por perfil, se o Levi pedir, é aqui. Com a Microsoft
  ligada (seção "Entrar com a Microsoft"), o Fracttal sai da porta e só entra quem é da Grid.
  Em produção o IP vem do `X-Forwarded-For` do proxy, por isso o `trusted_proxy` do `servir.py`.
- **Sair do Fracttal = sair do Nexus** (Levi, 09/10/2026: "quando deslogar do Fracttal deslogue do Nexus, tem que pedir
  para logar de novo"). A sessão que nasceu do login do Fracttal (a que tem `usuario`) acaba junto com a dele, e a tela
  de entrada diz por quê (`auth.MOTIVOS`: saiu, caiu, venceu; o `?motivo=` só aceita essas chaves). Quem encerra é
  `auth.encerrar` (limpa a sessão do Nexus e apaga o `os_sessao`; página = redirect ao login, fetch = 401 em JSON com
  `sessao_encerrada` e o endereço do login). Os quatro gatilhos:
  - o "sair" do OS Creator (`/os/logout`, "Sair do Fracttal nesta área"): o portão encerra antes do clone. Vale também
    para a senha de administrador: sair, de qualquer lugar, sai de tudo (o Sair do Nexus já saía do OS Creator);
  - o token venceu: o login guarda o `exp` do JWT em `fracttal_exp`, e o portão confere em TODO pedido;
  - num pedido de /os (o único caminho que recebe o cookie do OS Creator) sem o JWT ou com ele vencido. O `/os/login`
    de quem já entrou nos dois segue direto para o `next` (o login do OS Creator é o do Nexus);
  - o Fracttal recusou o token: a ponte lê a resposta do clone (`ponte._fim_na_resposta`, também na aprovação de OS e
    na assinatura da PT) e a página pergunta ao abrir, ao voltar a ficar à vista e a cada 5 minutos
    (`/os/_nexus/sessao`, ver o README do OS Creator). Aba escondida não pergunta.
  A senha de administrador não depende do Fracttal: só o sair a encerra. O login nunca fica numa moldura do Nexus (o
  OS Creator, o card da OS): o `entrar.html` leva a JANELA ao login, com o `next` da página de cima e o mesmo motivo; a
  casca tem `window.nexusEntrarDeNovo(url)` para as telas que recebem o 401 (`_entrar_de_novo_js.html`; o modo TV do
  Painel NOC, sem a casca, inclui o mesmo e a conferência de 5 minutos). Sessão de antes desta regra (sem
  `fracttal_exp`) ganha o prazo no primeiro pedido de /os. Prova: `tests/test_auth_sair_fracttal.py`; na tela, uma
  cópia em 127.0.0.1 com o Fracttal simulado (09/10: sair do OS Creator, token derrubado e token de 45 s vencendo, os
  três levando a janela ao login com o aviso certo).
  **Debaixo do `/nexus`** (a regra nasceu na raiz e entrou na porta única em 10/10/2026): o `encerrar` apaga o
  `os_sessao` em `os_cookie_path()` (com `/os` fixo o delete não casava e o OS Creator ficava logado) e o `nexus_sessao`
  velho de Path=/, e põe no `next` o caminho como o navegador o vê; o `/os/login` do clone já sai como
  `/nexus/os/login` e conta como "caiu" (`sem_raiz` no `_fim_na_resposta`); o `entrar.html`, o
  `nexusEntrarDeNovo` e a conferência da sessão pedem os endereços pelo `nexusRota`. Prova debaixo do prefixo, com o
  Caddy cortando: `tests/test_prefixo_sair_fracttal.py`.
- **`next_seguro`:** o `?next=` (e o `voltar` do tema, e o `/os/login?next=` de quem já entrou) só aceita
  caminho interno: começa com uma barra só, sem caractere de controle (0x00-0x20, 0x7f) nem barra invertida em lugar
  nenhum, e sem esquema nem servidor. O resto volta ao Início. Revisão adversarial de 10/10/2026: só se recusava `//` e
  `/\` no começo, e `/` + TAB + `/outro.site/x` passava; o Werkzeug monta o Location pelo `urlsplit`, que tira TAB, LF e
  CR, e o cabeçalho saía `//outro.site/x` (na raiz, a pessoa entrava com a senha do Fracttal e caía num site de fora;
  debaixo do /nexus o prefixo escondia). LF e CR davam 500. Prova: `tests/test_auth_next.py`, nos dois modos. O
  `_login_next` da plataforma tinha a mesma régua (o lado de lá se alinha à parte).
- **`[hidden]{display:none!important}`** no CSS: um `display:flex` vencia o `hidden` e o filtro "não filtrava" (01/10).
  Visível se confere pela geometria (`getBoundingClientRect`), não pelo atributo.
- **`<html data-nexus>`** + script anti-moldura: o OS Creator embutido não pode abrir o Nexus dentro do iframe dele.
- **Nada de `<svg>` no topo:** as telas com gráfico procuram o primeiro `<svg>` da página; o ícone do tema em SVG
  derrubou 24 testes do Mapa de risco (08/10/2026). Ícone do topo é da fonte de ícones ou desenhado no CSS.
- **Servidor local some com a sessão do Claude que o subiu.** Para ficar no ar: `Iniciar Nexus.bat` (pythonw
  escondido, log em `logs/`) e `Parar Nexus.bat` (só o processo da porta 5070).
- **Verde no menu = tela com conteúdo** (Levi, 04/10/2026, "para eu ir vendo o progresso"): torre com ao menos uma
  tela pronta fica verde, e a tela pronta também. "Pronta" = a rota `/t/<torre>/<tela>` cai numa view própria, não no
  `placeholder` da torre (`telas_com_conteudo`, calculado uma vez no primeiro pedido). Ninguém marca à mão: construiu a
  tela, ela fica verde sozinha.
  Exceção: as molduras da Performance (porta única) só contam com a `NEXUS_SSO_CHAVE` (`moldura.SO_COM_A_PORTA`):
  sem ela abrem o aviso "ainda não ligada" e o verde mentiria (revisão de 10/10/2026).
- **O Início conta pela mesma régua** (auditoria A3 da porta única, 10/10/2026): é a primeira página de todos, e dizia
  "fase 0" e "Com dado real: 0" com 40 telas prontas no ar. O número é "Telas prontas" (o tamanho de
  `telas_com_conteudo`, o verde do menu); cada cartão leva à 1ª tela PRONTA da torre (no COS, com a porta ligada, o
  Acompanhamento, e não a Mesa em construção), com "N de M prontas"; torre sem nenhuma (Comando, Contratos, Relatórios)
  vira um cartão que não é link, tracejado, com "Em construção". Prova: `tests/test_casca_inicio.py`.
- Edge "localhost recusou": o waitress tem de escutar em `127.0.0.1` **e** `[::1]`.
