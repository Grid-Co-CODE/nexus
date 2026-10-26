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
| `nexus/auth/__init__.py` | `/entrar` (a porta, a senha de administrador e a ida e a volta da Microsoft), `/sair` (com a porta única ligada, passa pela plataforma: `templates/sair.html`) e o portão (`before_request`) |
| `nexus/auth/microsoft.py` | o login pela conta Microsoft da Grid (Entra ID), desligado sem as quatro `NEXUS_MS_*` (seção "Entrar com a Microsoft" abaixo) |
| `nexus/auth/fracttal.py` | o login pelo Fracttal: o `api.fracttal_login` do clone do OS Creator; abre também o cookie `os_sessao` (/os) |
| `nexus/auth/acessos.py` + `telas_acessos.py` | os administradores dados pela tela Base → Acessos, a auditoria e quem entrou em 30 dias (`templates/acessos/acessos.html`; seção "Acessos" abaixo) |
| `nexus/auth/setor_telas.py` + `templates/sem_setor.html` | o que cada setor vê: o portão por setor e o menu filtrado (seção "Telas por setor" abaixo) |
| `nexus/auth/pre_carga.py` | a pré-carga das telas de quem tem setor (seção "Pré-carga" abaixo) |
| `nexus/templates/base.html` | a moldura: o topo (o setor, a ação da tela no bloco `topo_acoes`, o Tema, quem entrou e o Sair; seção "Um cabeçalho só"), menu lateral, recolher (`[` ou botão, lembrado em `localStorage` `nexus.menu`), menu do celular, botão do tema (que troca também as molduras do OS Creator abertas) |
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
  identidade do site (página #fcfcfc, cartão branco, seções #f5f6f8, texto #1f2937). Todo token tem valor nos dois. As
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
- **O botão:** no topo, "Tema: Escuro" / "Tema: Claro" (diz o de agora; o ícone, um meio círculo, é desenhado no CSS,
  `.tema-icone`). Troca na hora, sem recarregar, grava cookie e `localStorage`, e outra aba aberta acompanha (evento
  `storage`). Sem JavaScript é um formulário: `POST /tema` (`tema`, `voltar` com os filtros da tela) grava o cookie e
  volta. Com o movimento reduzido do sistema a troca é seca; sem ele, um esmaecer de 0,18 s (View Transitions). Até
  1180 px e no celular fica só o ícone; de 821 a 1180 px o setor do topo é quem encolhe (sem isso o topo passava
  da borda de 821 a 845 px).
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

**Duas abas desde 25/10/2026:** Telas e administradores (o que está abaixo) e Pessoas e setores (a antiga Base →
Integração Fracttal: o pessoal do Fracttal e o setor de cada um; regras em `nexus/cadastro/CLAUDE.md`). Só a segunda lê o
Fracttal.

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

## Nexus lento: Raio-X e o teto do OS Creator (14/10/2026)

Levi, 14/10/2026 às 09:20: "O nexus está muito lento"; "quando clico no OS Creator, fica carregando por um bom tempo"; e
"pq depende da TI se o OS Creator Web faz parte do Nexus???". Medido de fora: o /saude do Nexus de 0,5 a 30 s (às vezes 60
s), a plataforma e a API do banco, no mesmo servidor, em 0,2 s: as threads do waitress presas esperando o Fracttal pelo
OS Creator, que roda DENTRO do processo do Nexus (a ponte, sem proxy).
- **Raio-X** (`/t/base/raio-x`, `casca/raio_x.py`; só administrador, sem item no menu): os pedidos em andamento e onde
  cada um espera, as tarefas de fundo, o processador, a carga da máquina, o teto do OS Creator e os travamentos de 24 h.
  Nexus lento de novo = pedir o print dele na hora. **Desde 20/10/2026 diz também onde a MÁQUINA engasga** (pelo /proc do
  Linux, só leitura, quando a página abre): na "Carga da máquina", o processador da máquina inteira e o tempo esperando o
  disco na mesma janela de 1 s; no cartão "Memória da máquina", a memória livre, o swap em uso e se está trocando agora
  (MB/s), o quanto o Nexus ocupa (e dele no swap) e, com a PSI do kernel, o tempo com algo parado esperando memória ou
  disco. O caso: Raio-X das 10:08 de 20/10, `GET /os/` há 18 s numa cópia de 17 ms com o Nexus a 13% e carga 2,5 a 3,9:
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
  Caddy); o teto dá o mesmo efeito sem ela.
- **No OS Creator** (README da torre, 14/10/2026): a tela inicial não espera mais o selo do Fracttal, e as contagens da
  Performance ficam 6 h na memória.

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
  escopo repo ou public_repo; `pcm/publicar.token` usa o da tela primeiro). A tela não edita o .env: nome fora da lista é
  recusado.
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
- **Tela do setor (13/10/2026).** `Tela.do_setor` = o setor dono, pelo nome (sem acento nem caixa): quem é dele vê a
  tela SEM marca (`setor_telas.das_do_setor`, somada às marcas no `acesso`). Pode ser mais de um (uma tupla de nomes,
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
  administrador que tem setor (o Levi, na Performance) segue vendo tudo; o setor dele só aparece no topo e na lista de
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
  mais novo; cada um: o tipo, a área (o que vem entre parênteses), o commit, a manchete (o texto antes do " - ") e o
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
- **Prova**: `tests/test_casca_sugestoes_24_10.py`.

## Um cabeçalho só: quem entrou no topo do Nexus (13/10/2026)

Levi, com o print do topo do OS Creator dentro do Nexus: "Quero que essa visão de cabeçalho ao lado de sair vá para o
cabeçalho do Nexus e suma esse 2° cabeçalho tanto de OS Creator Web quanto de plataforma de performance! Dá a impressão
que é uma tela dentro de uma tela!".

- **Quem entrou** (`base.html`, `.usuario-*` no `nexus.css`): entre o Tema e o Sair, o avatar com as iniciais (filtro
  `iniciais` do `create_app`: primeiro + último nome, como o do OS Creator), o nome e o perfil do Fracttal (o
  `session.usuario`, o mesmo `get_conta_info` que o OS Creator mostrava; o e-mail no `title`). Sem perfil, só o nome. Quem
  entrou pela senha de administrador não tem nome: nada aparece. No celular, só o avatar, entre o Tema e o Sair (a regra
  que esconde o nome fica DEPOIS das `.usuario-*`: dentro do bloco do celular, lá em cima, ela perdia e o nome seguia).
- **A ação da tela no topo:** o bloco `topo_acoes`, antes do Tema. Hoje só o "Modo TV" do Painel NOC
  (`performance/moldura.html`); no celular ele some.
- **O OS Creator dentro do Nexus sem o topo dele:** a ponte (`torres/oscreator/ponte.py`, `_MARCA_NO_NEXUS`) marca com
  `os-no-nexus` a tela logo abaixo do Nexus (a casca, o login, o card da OS) antes de pintar, e o topo some. Aberto sozinho
  no navegador, o OS Creator fica com o topo (é o único lugar com o nome e o "sair").
- **A criação de OS numa janela por cima do Tempo real (13/10/2026)**, Levi: "Em performance > tempo real > criar OS ao
  invés de direcionar para o OS Creator aparece a tela de criação de OS sobrepondo toda a tela dando um blur de fundo,
  assim que a pessoa finaliza a OS só aparece a notificação de criação!". A plataforma abre `/os/performance/criar` com
  `?janela=1` num iframe que cobre a tela; a ponte (`_JANELA_OS`) a entrega sem o topo e embrulha o `fetch`: o POST de
  `/os/api/<x>/criar` que responde ok manda `{gc: "os-criada", mensagem, detalhes}` à página de baixo, que fecha a janela
  e mostra a notificação. O código do OS Creator não muda (a cópia segue igual à do oem).
- **As telas da Plataforma de Performance sem a faixa** "<tela> · Plataforma de Performance": a faixa só nasce com
  controle (o seletor de usina do Diagnóstico). Ver `nexus/performance/CLAUDE.md`.
- **Prova:** `tests/test_sem_segundo_cabecalho_13_10.py` (7; 6 mutações pegas) e `tests/test_porta_tv.py`; no navegador,
  uma cópia de prova com uma pessoa de mentira e a plataforma do PC: o topo com "PE Pessoa Exemplo ADMINISTRATOR", o
  Performance do OS Creator começando no "← Voltar", o Tempo real e o Painel NOC sem a faixa (o "Modo TV" no topo), o
  Diagnóstico só com o seletor, o OS Creator aberto sozinho com o topo dele, 375 px só com o avatar, escuro e claro.

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
  `quem` (a linha NOSSA mais de dentro: Fracttal (OS Creator) no `os_creator/api.py`, Fracttal (Campo), fotos das
  rondas, login do Fracttal, ou `arquivo:função`), `como` (a linha mais de dentro de todas: esperando a rede, outra
  thread, o banco, em pausa, trabalhando) e `onde` (`arquivo:linha função`). Vai ao log (WARNING `Pedido preso há N s:
  GET /caminho - quem, como (onde)`) quando prende e quando o rótulo muda.
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
- **Prova:** `tests/test_casca_presos.py` (10; 7 mutações pegas) e, de ponta a ponta, um Nexus descartável com 4
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
- **Rota pública é decisão consciente:** só o que está em `ROTAS_PUBLICAS` (entrar, saude, static e as duas que o App de
  Campo chama assinadas com a chave derivada da `NEXUS_PESSOA_HMAC`: a foto do extintor, `torre_hseq.extintores_foto_receber`,
  e a marca de motivo do técnico, `torre_pcm.motivo_do_app`, 16/10/2026). O teste
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
  10/2026, o PAPEL de quem entrou no Campo · App ({pessoa_id, nome, papel: supervisor_campo | coordenador | gestor,
  regioes ou gestor}; o filtro que já vem marcado e quem vê o Aprovar; ver `nexus/torres/campo/CLAUDE.md`). Sessão de
  antes, com o nome do supervisor em texto, não vale como papel. A
  senha de admin segue em "Entrar com a senha de administrador" (`/entrar?admin=1`) e é a porta do Cadastro. Quem
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
