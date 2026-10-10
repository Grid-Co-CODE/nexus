# CLAUDE.md — Performance (regra da torre, sem Flask)

## Porta única (09/10/2026): as telas da plataforma numa moldura do Nexus

Levi: "a partir de segunda quero o Nexus como link principal; o Nexus será o centro de tudo, precisamos trazer o tempo
real de performance painel para o Nexus". Desenho "uma porta, dois motores"
(`docs/superpowers/specs/2026-10-09-performance-no-nexus-design.md`): o Nexus é a porta (menu, login, endereço); a
Plataforma de Performance (repositório PerformancePainel) continua o motor e desenha as próprias telas, com leitura e
gravação, dentro de uma moldura (iframe) do Nexus. Nada da plataforma passa pelo processo do Nexus (a ponte passava): o
navegador fala com cada sistema.

- **O mapa** (`porta.py`, `MAPA`): as 13 telas, `torre · tela -> caminho na plataforma`. Fonte única: o Nexus é o dono;
  a plataforma tem a cópia em `plataforma/porta_nexus.py`. Os dois comparam o mesmo texto canônico
  (`texto_canonico_do_mapa`; `tests/test_porta_mapa.py` aqui e o teste da porta lá): mudou um, muda o outro e o texto dos
  dois testes. Com `PLATAFORMA_REPO=<clone do PerformancePainel>` o teste daqui abre o módulo de lá e compara o mapa, a
  regra do destino e o passe de verdade. O mesmo mapa dá o destino que o passe aceita (`destino_permitido`, a MESMA regra
  da plataforma: só caminho local do mapa, sem aspas, espaço, controle, barra invertida nem fragmento; nada de
  redirecionamento aberto), o `?p=` que o Nexus aceita e o item do menu que acende.

  | torre · tela | plataforma |
  |---|---|
  | performance · `tempo-real` | `/tempo-real` (e `/tempo-real/<fonte>`, `/monitor`) |
  | performance · `noc` | `/painel` |
  | performance · `diagnostico` | `/painel/usina/<id>`, pelo seletor de usina |
  | performance · `strings-trackers` | `/painel/falhas` |
  | performance · `gerencial` e `disponibilidade` | `/gerencial` e `/gerencial/disponibilidade` |
  | performance · `relatorio` e `relatorio-semanal` | `/relatorio` e `/relatorio/semanal` |
  | performance · `gemeo` | `/gemeo/` (e tudo debaixo dele) |
  | performance · `historico-plataforma` e `monitor-ronda` | `/historico-plataforma` e `/ronda/monitor` |
  | cos · `acompanhamento` | `/cos` |
  | base · `chaves-fontes` (só admin) | `/tokens` |

  Os ids que já existiam no menu não mudaram (viraram endereço). Clima e risco e Mapa de risco são do Nexus e ficam fora.
- **O passe** (`montar_passe`): `base64url(json) + "." + base64url(HMAC-SHA256(json))` com a `NEXUS_SSO_CHAVE` (a MESMA
  no `.env` da plataforma; com menos de 32 caracteres vale como ausente, nos dois lados). O JSON leva `v`, `email`,
  `nome`, `admin` (o `session["admin"]` do Nexus: `NEXUS_ADMINS` ou a senha de administrador), `destino`, `vence` (60 s)
  e `numero` (novo a cada abertura; a plataforma recusa o repetido). Vai por **POST** no campo `passe` de
  `/painel/nexus/entrar`, nunca na URL (leva o e-mail). Quem entrou pela senha de administrador não é uma pessoa: vai com
  `admin@nexus.invalid` (domínio que não existe); com `PLATAFORMA_ANALISTAS=*` ele entra como analista.
- **A tela** (`nexus/torres/moldura.py`, `registrar_molduras`): uma view por item do mapa, nas torres Performance, COS e
  Base; o template `performance/moldura.html` (faixa fina e a moldura ocupando a tela, o padrão `.conteudo--moldura`) e o
  `nexus/static/porta.js`. A página traz o formulário escondido (alvo = a moldura; o `porta.js` o envia ao carregar; sem
  JavaScript, o botão "Abrir") e sai com `Cache-Control: no-store` (o passe vale 60 s e uma vez: voltar pelo navegador
  gera outro). A plataforma confere, abre a sessão DELA (12 h) e responde 303 para a tela, no modo Nexus.
- **O endereço acompanha:** a página da plataforma, em modo Nexus, manda `postMessage({tipo: "nexus:rota", caminho})` a
  cada troca de caminho. O `porta.js` só aceita o aviso da própria moldura e da origem da plataforma; troca o endereço
  (`history.replaceState`: o item dono do caminho, com `?p=` quando não é a entrada padrão dele), acende o item no menu e
  leva o endereço novo ao "voltar" da cadeira e do tema e ao "Abrir em outra aba". Abrir com `?p=` (F5, favorito): do
  mapa e do item, abre ali; de OUTRO item, 302 para o item dono; fora do mapa, a tela padrão do item (spec 7).
- **A sessão da plataforma vence em 12 h e a moldura a renova** (auditoria A5 da porta única, 10/10/2026). O caso: a
  sessão que o passe abre vale 12 h fixas (`SESSAO_DO_PASSE_S` da plataforma); depois, o `/api/macro` do Painel NOC dava
  401 e o painel, que relê a cada 60 s, desenhava "Energia perdida 0,0 MWh", número falso numa tela de NOC ou de TV. O
  protocolo combinado entre os dois lados (mude nos dois juntos):
  - a página da plataforma em modo Nexus, ao receber 401 numa chamada de dado, manda à moldura
    `postMessage({tipo: "nexus:sessao-vencida", caminho: location.pathname + location.search}, <origem do Nexus>)`;
  - o `porta.js` confere fonte e origem como no `nexus:rota`, pede um passe NOVO ao Nexus (`POST <tela>/passe` com
    `p=<caminho>`, o endereço vem em `dados.renovar`) e reabre a mesma tela pelo formulário do passe. Caminho fora do
    mapa (o `/login` dela): reabre o último que a moldura avisou. **No máximo 1 vez a cada 60 s**: se vencer de novo logo
    depois, a faixa de alerta manda clicar no item do menu (sem laço);
  - com a aba aberta, a cada 11 h (pelo relógio de parede, conferido a cada minuto e ao voltar à aba: um `setTimeout`
    atrasa com o computador dormindo) o passe novo vai por `fetch` a `/painel/nexus/entrar` (o 303 não é seguido, como no
    Diagnóstico) e a plataforma abre outra sessão de 12 h, sem recarregar a tela; falhou, tenta em 10 min;
  - a rota do passe novo (`moldura._passe_novo`, uma por item, só POST, dentro de `/t/*` para o Caddy da raiz mandá-la ao
    Nexus): o mesmo passe da abertura (60 s, uso único, quem está logado) para qualquer caminho do MAPA (a moldura pode ter
    ido do Painel NOC ao diagnóstico de uma usina); Chaves das fontes só para admin; 400 fora do mapa, 404 sem a chave, 403
    de outro site (`Sec-Fetch-Site` só `same-origin`; sem ele, o `Origin` deste host), `Cache-Control: no-store`. Sessão
    do Nexus encerrada: o portão responde antes (401 em JSON, ou o salto ao Entrar) e o `porta.js` leva a JANELA ao
    login (`nexusEntrarDeNovo`), que volta para a mesma tela.
- **Diagnóstico:** sem `?p=` a página mostra o seletor e "Escolha uma usina". A lista vem da PLATAFORMA, pelo navegador
  (o processo do Nexus não busca): o mesmo `/api/macro` e `/api/gerencial` do Painel NOC, com a regra dele (o `FMAP` e o
  `drillUrl` de `painel_portfolio.html`, copiados no `porta.js`: a usina de fonte ao vivo abre com `?fonte=`, a que só
  existe no Gerencial abre com `?hist=1`; mudou lá, muda aqui e no `tests/test_porta_js.py`). Sem a sessão da plataforma
  (401), o `porta.js` abre a sessão por `fetch` com um passe próprio da página (`passe_lista`, destino `/painel`, o 303
  não é seguido) e lê de novo. Escolher a usina recarrega a página do Nexus com `?p=/painel/usina/<id>?...` (passe novo
  para aquele destino).
- **Tempo real:** a visão "Ao vivo" é a moldura. A alternância "Ao vivo | Pelo banco" (spec 5.7) está pronta em
  `moldura.VISOES_DO_TEMPO_REAL` com a "Pelo banco" em `pronta=False`: só aparece quando a Operação em tempo real
  (branch `operacao-tempo-real`) entrar, DEPOIS que a Ao vivo estiver no servidor. Até a `NEXUS_SSO_CHAVE` chegar, o
  Tempo real cai na ponte de 04/10 (a reserva, abaixo), se ela estiver configurada: nada afeta o que funciona hoje.
- **Chaves das fontes** (`/tokens`): só admin do Nexus; quem não é recebe 403 com o porquê (como as telas do Cadastro), e
  a plataforma recusa de novo pelo `admin` do passe.
- **Sem configuração:** sem a chave, com chave curta ou com a `NEXUS_PLATAFORMA_URL` inválida, cada item diz "Performance
  ainda não ligada neste servidor"; o que falta (nunca o valor) só para admin, e no menu as molduras ficam sem o verde
  (`moldura.SO_COM_A_PORTA` em `telas_com_conteudo`; o Tempo real, que tem a ponte de reserva, segue verde). Revisão
  de 10/10/2026: antes os 12 itens ficavam verdes e o aviso mostrava a variável a qualquer um, técnico inclusive. O
  resto do Nexus segue. A plataforma, sem a chave,
  responde 404 em `/painel/nexus/*`: as duas pontas ficam inertes até a T.I. pôr a MESMA chave nas duas (`DEPLOY.md`,
  seção 7e).
- **Onde está a plataforma para o navegador** (`base_da_plataforma`): a `NEXUS_PLATAFORMA_URL`, a mesma da ponte. No
  servidor ela FICA `https://app.gridco.com.br` (a mesma origem do Nexus): vazia também serviria à moldura, mas a ponte
  perderia o endereço e tirar a chave deixaria o Nexus sem Tempo real (revisão de 10/10/2026, DEPLOY 7e). A moldura
  **só abre na mesma origem**: a plataforma manda `frame-ancestors 'self'` e o aviso de rota vai só à origem dela. No PC
  as duas cópias ficam atrás da `ferramentas/porta_local.py`, com a URL vazia (`subir_copia_de_prova.py --plataforma
  ""`). Em outra origem NADA sai do navegador (o `porta.js` não envia o passe nem lê a lista do Diagnóstico, e o Sair
  não faz o POST): só o aviso. E a base em loopback (`http://127.0.0.1:...`, o endereço interno) com o Nexus aberto por
  fora desliga a porta no servidor (`porta.motivo_da_origem`): sem isso o navegador de quem visita mandaria o passe, com o
  e-mail, à própria máquina. http só na máquina local.
- **O Sair** (`nexus/auth`): com a chave, `/sair` encerra a sessão do Nexus e mostra uma página que faz POST em
  `/painel/nexus/sair` (a plataforma encerra a sessão do passe; a da senha fica) e segue ao Entrar em até 4 s, responda a
  plataforma ou não; sem JavaScript, um botão. Sem a chave, o `/sair` de sempre (302).
- **O Entrar** (revisão de 10/10/2026): com a chave, a página do Entrar também faz o POST em `/painel/nexus/sair`
  (`auth._tela_entrar`; só na mesma origem). Num PC compartilhado, A não clicava em Sair, a sessão dele no Nexus vencia, B
  entrava, e a sessão do passe de A na plataforma (12 h) seguia valendo para todo acesso direto: o diário gravava A.
- **A camada da T.I. e o calço do `fetch`:** no servidor, uma camada fora do repositório põe `/nexus` em todo `fetch`
  começado por "/" (`nexus/casca/CLAUDE.md`). Por isso o `porta.js` e o Sair pedem a plataforma por URL COMPLETA
  (`new URL(..., location.href)`); os endereços da plataforma no HTML (`/painel/nexus/...`, `/tempo-real`...) não são
  caminhos do Nexus e a camada não os toca (`test_a_camada_do_servidor_nao_mexe_nos_enderecos_da_plataforma`).
- **Prova:** `tests/test_porta_mapa.py` (mapa e passe; com `PLATAFORMA_REPO`, contra a plataforma de verdade),
  `tests/test_porta_moldura.py` (cada tela nos dois modos, `?p=`, sem login, sem chave, só admin, Tempo real com e sem a
  chave, Sair), `tests/test_porta_js.py` (no node: o seletor, o item que acende, o endereço, a reabertura pela sessão
  vencida e a renovação de 11 h, com o relógio da página andando em `tests/porta_pagina_falsa.js`),
  `tests/test_porta_renovar.py` (a rota do passe novo) e
  `tests/test_prefixo.py::test_com_a_porta_da_performance_ligada_tambem` (o rastreador com a porta ligada; os endereços
  da plataforma escritos de propósito ficam em `Rastreio.da_plataforma`). No navegador: as duas cópias de prova atrás da
  `porta_local.py` (o Nexus com `--prefixo /nexus --plataforma ""` e a plataforma na raiz, as duas com a mesma
  `NEXUS_SSO_CHAVE` pelo ambiente e `PLATAFORMA_ANALISTAS=*` na plataforma), entrando por um nome `*.localhost` para os
  cookies não se misturarem com os da 5050 e da 5070 em 127.0.0.1.
- **Provado de ponta a ponta no PC (10/10/2026)**, a cópia de prova do Nexus e a da plataforma (as duas branches da porta
  única) atrás de um proxy que imita o Caddy nos dois modos (prefixo `/nexus` cortado, o servidor de hoje, também com a
  camada de reescrita da T.I. junto; e raiz, a fase 4), Chrome sem janela a 1440 px:
  - entrar pela senha de administrador (o login do Fracttal NÃO: a cópia barra o POST ao Fracttal; quem não é admin foi
    provado com uma sessão de teste no mesmo formato); `nexus_sessao` (em `/nexus` ou `/`) e o `session` da plataforma
    vivem juntos, entrar num não derruba o outro;
  - as 13 telas abrem na moldura em `modo-nexus`, com o item aceso; os números da moldura são os MESMOS da plataforma
    direta no mesmo minuto (7 telas comparadas número a número); o endereço acompanha o clique dentro da tela (Tempo real
    -> fonte com `?p=`; "investigar" do Painel NOC -> item Diagnóstico, com o seletor marcando a usina; "Visão Gerencial"
    da Disponibilidade -> item Gerencial) e o F5 volta ao lugar; `?p=` de outro item vai ao dono, fora do mapa abre o
    padrão; o `voltar` do tema leva o `?p=`;
  - perfis: o analista grava (numa cópia de estado da plataforma), o gestor lê as 11 telas e leva 403 ao gravar, Chaves
    das fontes só admin (aqui e na plataforma), fora das listas "Sem acesso"; os passes que o Nexus gera valem 60 s e uma
    vez: repetido, adulterado, vencido, fora do mapa, na URL e de outro site são recusados sem abrir sessão;
  - o Sair encerra as duas sessões (GET `/nexus/sair` e o POST em `/painel/nexus/sair`); sem a chave, as 13 telas avisam,
    o Tempo real cai na ponte (com a ponte configurada, mostra a plataforma) e a plataforma responde 404;
  - 100 páginas do Nexus (Início e todo o menu) e 12.744 endereços: no modo prefixo nenhum fora do `/nexus` (fora os da
    plataforma escritos de propósito), com a camada da T.I. nenhum `/nexus/nexus`, no modo raiz nenhum `/nexus`; nenhum
    erro de JavaScript; a 375 px nenhuma página do Nexus rola de lado;
  - abrir pela moldura custa ~100 ms a mais que direto (a página do Nexus, o POST do passe e o 303); o Diagnóstico pronto
    em ~5 s pelos dois caminhos (as leituras da própria tela). O gêmeo deu 503 (não está de pé no PC). Nenhuma das duas
    páginas declara ícone: o navegador pede `/favicon.ico`, que cai na plataforma (404, ou 403 para o gestor); é ruído
    de console, não erro.
- **Revisão adversarial, provada de novo no PC (10/10/2026, de madrugada)**, as mesmas cópias e o mesmo proxy, modos
  prefixo e raiz:
  - as 13 telas, o analista que grava, o gestor, o Sair e os passes (válido, repetido, adulterado, vencido, fora do
    mapa, na URL, de outro site) seguem como na véspera;
  - a página do Entrar encerra a sessão do passe na plataforma (`/api/state` 200 -> 401);
  - com um `nexus_sessao` velho em `Path=/` ao lado do de `/nexus`, o Sair apaga os dois e `/nexus/t/cos/mesa` volta ao
    Entrar;
  - OS Creator embutido (sessão de teste do clone, a cópia sem saída para fora da máquina): o item Histórico e o item
    Ativos da torre abrem a aba da tela, debaixo do `/nexus` e na raiz. Com a ponte de antes da correção, debaixo do
    `/nexus`, só o Início abria e `ehTela` dava `false`;
  - com a `NEXUS_PLATAFORMA_URL` em outra origem (`http://127.0.0.1:5052`, a plataforma direta), nenhum pedido sai
    para ela (o passe, a lista do Diagnóstico, o Sair e o Entrar), e o aviso aparece; aberto por um endereço de fora
    (cabeçalho Host), o servidor desliga a porta, diz por quê e o Tempo real cai na ponte;
  - sem a chave: só o Tempo real fica verde no menu; o técnico lê "ainda não ligada" sem o nome da variável e o Tempo
    real dele é a ponte sem a faixa; o admin vê o que falta.

## Ponte para a Plataforma de Performance (04/10/2026): hoje só a reserva do Tempo real

Desde a porta única (09/10/2026, acima) a ponte saiu do menu: com a `NEXUS_SSO_CHAVE` o Tempo real abre a moldura. Ela fica no código como a RESERVA do Tempo real enquanto a chave não chega ao servidor, e sai de vez quando a Operação em tempo real entrar (spec 2026-10-09, fase 2).

A aba Performance → Tempo real mostra a Entrada e o Monitoramento da própria plataforma (Levi: "tudo da plataforma,
só leitura", "em paralelo por enquanto"). Fase 1 de cinco para a plataforma morar 100% no Nexus: ver o spec
`docs/superpowers/specs/2026-10-04-tempo-real-no-nexus-design.md`, seção 10.

- O navegador fala só com o Nexus. `ponte.py` leva o pedido à plataforma com `X-Nexus-Leitura`
  (`NEXUS_PLATAFORMA_TOKEN` = `NEXUS_LEITURA_TOKEN` da plataforma) e `X-Forwarded-Prefix: /t/performance/plataforma`
  (com o prefixo em que o Nexus roda na frente: `/nexus/t/performance/plataforma` no servidor; o guarda de leitura usa o
  mesmo, 09/10/2026).
  A plataforma devolve as páginas com o prefixo (`_SHIM_PREFIXO` + atributos): a ponte não reescreve HTML, só injeta
  o visual (`#nexus-visual`) e o guarda (`#nexus-leitura`).
- **Só leitura em três camadas:** portão da plataforma (403 com a chave), `pode_passar` aqui, guarda no navegador.
  Os únicos POSTs: `POSTS_DE_CONSULTA` (a mesma lista do `leitura_nexus.py` da plataforma — mudou lá, muda aqui).
- **Os parâmetros que disparam trabalho saem de todo pedido** (`PARAMETROS_QUE_DISPARAM`: `force`, `forcar`, `run`, `backfill` — a mesma lista do `leitura_nexus.py` da plataforma, que recusa esses nomes com a chave): o "Atualizar" das páginas leria a SunOp na hora (cota). Pelo Nexus, lê-se o que o motor já montou.
- **A API PV fica de fora, por enquanto** (Levi, 05/10/2026: "por hora não puxa nada da API da thopen, estou tentando
  economizar requests e tenho medo que duplique as chamadas"). A API PV (`*.pvoperation.com*`) atende Thopen, SEMP, Alves
  Lima e 2C-API. O detalhe que abre a usina nela na hora (`NEGADOS_API_PV`: inversores da usina, drill/curva/CSV de
  trackers, a lista de trackers de SEMP/Alves Lima/2C, strings de uma usina, curva da estação) é 403 com `AVISO_API_PV`
  e nem sai do Nexus; o que a plataforma já tem guardado (tabela, lista de trackers da Thopen, acervo) passa. A
  plataforma faz o mesmo do lado dela (`leitura_nexus.NEGADOS_API_PV`, mesma lista) e, além disso, não fala com a API PV
  em pedido do Nexus nem monta cache por ele (`instalar_trava_api_pv`, `_swr`, Entrada) — prova com a rede cortada em
  `tests/test_nexus_sem_api_pv.py` da plataforma. Para liberar depois: tirar a rota das DUAS listas.
- **Caminho com "?" ou "#" é recusado (400)**: o Flask decodifica `%3F`/`%23` dentro do caminho, e a query escondida passaria por fora do filtro. O caminho à plataforma sempre começa com "/" (com `@host` sem barra, a chave iria para outro servidor).
- **Cabeçalhos em qualquer caixa**: `ajustar_resposta` casa por minúsculo e devolve os nomes canônicos; sem isso, um `content-type` minúsculo (Cloudflare, HTTP/2) mandaria o HTML sem o guarda.
- Não passa `Set-Cookie` nem o cookie do Nexus; tempo-limite 150 s (o drill da API PV leva até 120 s).
- **No máximo 4 pedidos ao mesmo tempo** (`_VAGAS`, espera de 2 s, depois `Ocupada` → 503 "Ponte ocupada"): cada pedido
  segura uma thread do Nexus por até 150 s, e sem teto uma plataforma lenta esgota as threads e trava a casca inteira.
  A vaga volta num `finally`; uma única `requests.Session` (`_SESSAO`) reaproveita a conexão.
- **Salto (3xx) só no mesmo servidor, até 3** (`allow_redirects=False` no pedido; `enviar` segue sozinha): o `requests`
  seguiria para qualquer host levando `X-Nexus-Leitura`. Outro esquema/host/porta → `RedirecionamentoRecusado`
  (`ForaDoAr`); salto para `/login` volta como está e a rota diz "a plataforma recusou a chave" (sem sessão e sem a chave
  valendo, a plataforma manda o pedido para o login dela). `NEXUS_PLATAFORMA_URL` com `http://` fora de
  localhost/127.0.0.1/::1 é recusada antes de qualquer rede: a chave iria em texto puro.
  `Location` com `\`, espaço ou controle é recusada (crua, antes do `urljoin`, que engole tabulação) e a origem é
  conferida pela URL que o `requests` vai usar (`Request.prepare()`, lida pelo `urllib3.parse_url` E pelo `urlparse` do
  adaptador do requests 2.34; se os dois discordam, recusa), não pelo `urlsplit`
  (04/10/2026: `//evil.com\@plat/x` passava pelo `urlsplit` e o urllib3 conectava em evil.com, com a chave). URL
  malformada (porta inválida, colchete solto: o `urljoin` do Python 3.14 levanta `ValueError`) é
  `RedirecionamentoRecusado`, nunca `ValueError`/500. A exceção traz o `motivo` (outro servidor, redirecionamentos
  demais, endereço inválido) e a rota o mostra.
  **O `requests` lê a Location sozinho no `Session.send`, mesmo com `allow_redirects=False`** (preenche `r._next`): o
  `urlparse` e o `latin1 -> utf8` dele levantam `ValueError` (`UnicodeDecodeError` incluso) DENTRO de `_SESSAO.request`,
  antes de a ponte ver a resposta; `_seguir` captura esse `ValueError` em volta do envio e recusa (502, não 500). A
  ponte relê a Location em UTF-8 como o requests (`encode("latin-1").decode("utf-8")`) antes das travas. **Teste
  de salto com sessão falsa não vê isso** (04/10/2026: os testes passavam e a rota dava 500): use
  `tests/sessao_real_sem_rede.py` (`requests.Session` real com adaptador falso montado, sem rede).
- **A `NEXUS_PLATAFORMA_URL` é lida do mesmo jeito** (`ponte.origem_configurada`, usada pela rota): barra invertida,
  espaço ou controle, ou URL que não é http(s), vira a página "Ponte não configurada" sem nenhuma chamada de rede; a
  regra "http só em localhost/127.0.0.1/::1" usa esquema e host dessa leitura, não do `urlsplit`
  (04/10/2026: `http://evil.com\@localhost:5050` parecia localhost e o `requests` ia para evil.com em texto puro).
- **Falha fechada se a plataforma não cumpre a chave:** resposta 2xx sem `X-Nexus-Leitura-Ok: 1` (cabeçalho que o
  `_auth_gate` da plataforma só põe quando aceitou a chave) não é mostrada. Plataforma sem `NEXUS_LEITURA_TOKEN` ignora
  a chave e deixa passar até gravação, e a ponte não tinha como saber.
- `montar_pedido` recusa (`ValueError`) caminho sem "/" inicial ou com "?"/"#", além do 400 da rota: a regra vale
  também para quem chamar a função sem passar pela rota.
- Controle de gravação que aparecer na tela (seletor novo na plataforma): acrescentar em `_VISUAL`, com o atributo REAL
  da página (`onclick`, `onchange` ou `oninput`; confira no HTML da plataforma) e só o controle, nunca um contêiner de
  dado. Mesmo sem isso, o guarda não deixa gravar.

## Risco conhecido (fase 1): mesma origem

O HTML da plataforma roda na origem do Nexus, com a sessão do administrador. O guarda (`#nexus-leitura`) só embrulha
`fetch`: um script injetado numa página da plataforma (texto de terceiro ou de usuário que chegue ao HTML sem escape)
poderia usar a sessão do Nexus por outros caminhos (`XMLHttpRequest`, formulário, `window.open`). A correção de verdade é
servir a ponte em **outra origem** (subdomínio ou porta, cookie próprio), antes do login por pessoa (fase 3). Até lá,
todo texto de terceiro ou de usuário nas páginas da plataforma passa por `_he`. Levi aceitou o risco por agora
(04/10/2026); a origem separada entra antes do login por pessoa (fase 3).

Como provar: `tests/test_performance_ponte.py`, `tests/test_torre_performance.py` e, na tela, o Nexus local contra a
plataforma local — mesmo número do card nos dois no mesmo minuto.

## Clima e risco (06/10/2026): alertas públicos por usina, só leitura

Aba Performance → Clima e risco (`/t/performance/clima`). O Levi trouxe o pacote `gridco_meteo` (referência, fora do
repositório) e escolheu (06/10) começar pelos **alertas**: avisos do INMET, focos de queimada do INPE e risco de fogo do
INPE, todos públicos e de uso livre. A tela cruza isso com as usinas em operação do cadastro e se atualiza sozinha
(recarrega a cada 60 s; o que vai à rede é decidido pelo cache, não pela recarga). A **página de cada usina**
(`/t/performance/clima/usina/<id>`, 07/10) acrescenta a irradiação diária da NASA POWER (ver abaixo); a tela principal nunca
chama a NASA.

**Fonte por extenso, de um lugar só (09/10/2026, Levi, olhando o bloco "Fontes" do mapa: "Quero as fontes por extenso também, não
só sigla").** O nome de cada fonte mora em `fontes.NOMES` e sai por `fontes.extenso()`: "Instituto Nacional de Meteorologia
(INMET)", "Instituto Nacional de Pesquisas Espaciais (INPE)", "Prediction Of Worldwide Energy Resources, projeto da NASA (NASA
POWER)" e "Instituto Brasileiro de Geografia e Estatística (IBGE)". A lista, a página da usina, o mapa (fontes, legendas, dicas,
rodapé) e o modo TV escrevem por ele: no Python, `visao.NOME_LONGO` e `visao.ROTULO_DA_FONTE` (a linha de cada fonte começa pelo
nome por extenso, "... (INMET) · avisos: lido às ..."); nos templates da torre, `fonte_nome.<fonte>` (context processor de
`clima_tela.py`) e, no mapa, `v.nomes`. O qualificador dos números da faixa também ("avisos do ... (INMET): parcial"). A sigla
sozinha só fica em mensagem de erro e no log (a linha da fonte que a mostra já começa pelo nome). `tests/test_clima_nomes.py` falha
se o nome por extenso aparecer escrito à mão em outro arquivo do `nexus/` e confere, nas telas, que a primeira sigla vem com o nome.
A citação que a NASA pede ("NASA LaRC POWER") continua no rodapé da página da usina.

**A tela (leitura rápida, aprovada pelo Levi em 07/10/2026; didática desde 09/10/2026), na ordem:** cabeçalho (filtro de
cliente, "atualizada às HH:MM"); **faixa de 4 números** (Agir agora, Atenção, Sem alerta, Cobertura), cada nível com "O que
fazer" quando tem usina (com zero ou com "—" não diz nada); o link "Como ler esta tela"; **Agir agora**, um cartão por usina
(pílula, frase principal, "Quando:", "O que pode acontecer" e "O que conferir" do motivo principal, os outros motivos e o
"Também"); **Por estado**, uma grade de 27 quadrados (cada quadrado é um estado, não é um mapa; o número é de usinas com alerta
no estado e a cor, a do pior nível); **De onde vêm os dados** (de quando é cada um); **Atenção**, a tabela usina x "Por quê" x
avisos x fogo a até 5 km x os quatro dias do risco de fogo (as 20 primeiras; "Ver todas (N)" é `?todas=1`); **Entenda os
alertas** (os três níveis da tela com o que fazer, os níveis do INMET, foco, risco de fogo com a escala, os eventos que estão
valendo agora e, recolhidos, os outros que o INMET publica). A grade de estados e a tabela rolam DENTRO da caixa em 375 px,
nunca a página. Cada cartão e cada linha levam à página da usina.

**Didática (09/10/2026, Levi: "estou achando um pouco limitado e pouco entendível para um leigo, deixe mais didático").** A tela
dizia o QUE havia ("Tempestade · vermelho", "1,00") e não o que quer dizer nem o que conferir, e repetia o mesmo aviso (três
"Baixa Umidade" numa usina). Regras:
- **Os textos moram em `clima/explica.py`, uma vez só** (a lista, a página da usina e o mapa leem dali): o que é cada evento, o
  que pode acontecer NA USINA e o que conferir (nunca ordem de serviço nem procedimento de segurança, que são do HSEQ e do
  supervisor); evento que o INMET publicar e não estiver lá cai no texto genérico e continua aparecendo. Todo evento de
  `alertas.EVENTOS_QUE_ESTRAGAM_USINA` tem texto próprio (teste).
- **Nível pela palavra do INMET, nunca pela cor** (Perigo Potencial, Perigo, Grande Perigo, com o que cada um quer dizer); a
  cor fica no desenho.
- **Avisos iguais juntos:** `visao.agrupar_avisos` (mesmo evento e mesmo nível: a janela vai do primeiro início ao último fim,
  com quantos são) e `visao.por_evento` (o mesmo evento em níveis diferentes vira um: o nível mais alto, a janela de todos e
  quando vale cada nível no balão). O cartão tem UM motivo por evento que manda agir; os outros níveis vão para o "Também".
- **Motivo resumido** (`visao.motivo_curto`): fogo perto, os eventos (os que mandam agir antes) e o risco de fogo alto, cortado
  nos dois primeiros com "e mais N". É a coluna "Por quê" da Atenção e o motivo da tabela do mapa.
- **Risco de fogo em palavra** (Mínimo, Baixo, Médio, Alto, Crítico) na célula; o número do INPE e o dia ficam no balão. Os dias
  com o nome que se fala (`visao.dias_amigaveis`: "hoje", "amanhã", "sáb 11/10"; "ontem" com o arquivo de ontem); os rótulos
  internos "D+1" seguem em `rotulos_dos_dias` para as regras de frescor.
- Célula da Atenção que leu e não achou diz com palavra ("nenhum", "não"); sem leitura continua "sem leitura".

| Fonte | O que traz | Cache | Endereço (troca por `NEXUS_CLIMA_*_URL`) |
|---|---|---|---|
| INMET avisos | JSON `{hoje, futuro}`; cada aviso com evento, severidade, início, fim e polígono (texto de JSON) | 30 min | `apiprevmet3.inmet.gov.br/avisos/ativos` (não documentado oficialmente) |
| INPE focos | CSV de 10 em 10 min (`lat,lon,satelite,data`, hora em UTC); vale a última hora = os 6 últimos arquivos | 10 min | `dataserver-coids.inpe.br/queimadas/queimadas/focos/csv/10min/` |
| INPE risco de fogo | GeoTIFF por dia, `RF.PREV.T0..T3.tif` (hoje e D+1 a D+3), 0 a 1, pixel de ~1 km | 6 h se o T0 é o de hoje (sai ~06:30); **15 min enquanto não é** (pela data do arquivo, em Brasília: lido às 05:00, o arquivo de ontem não fica até as 11:01) | `dataserver-coids.inpe.br/.../riscofogo_meteorologia/previsto/risco_fogo/RF.PREV.T{d}.tif` |
| NASA POWER (só a página da usina) | JSON `properties.parameter.ALLSKY_SFC_SW_DWN` = {AAAAMMDD: kWh/m²/dia} (GHI), `-999` = não publicado | **12 h por usina** (um cache por usina; uma busca por vez em cada) | `power.larc.nasa.gov/api/temporal/daily/point?...` (`NEXUS_CLIMA_POWER_URL` leva `{lat}`, `{lon}`, `{inicio}`, `{fim}`) |
| NASA FIRMS (10/10/2026) | 4 CSV de focos ativos da América do Sul (VIIRS S-NPP, NOAA-20, NOAA-21; MODIS Aqua/Terra), as últimas passagens (24 a 40 h), com FRP e confiança; colunas lidas pelo NOME | **30 min**; a releitura pergunta com HEAD e só baixa o arquivo cujo ETag mudou | `firms.modaps.eosdis.nasa.gov/data/active_fire/...` (`NEXUS_CLIMA_FIRMS_URL` = a base; `fontes.FIRMS_ARQUIVOS` vão depois dela) |

O código (sem Flask) está em `nexus/performance/clima/`: `geometria` (ponto em polígono e haversine), `geotiff` (leitor do
COG), `fontes` (os quatro clientes), `alertas` (as regras e os níveis), `leitura` (cache por fonte; o da NASA, por usina),
`irradiacao` (a série de 30 dias, o mês até agora e a geometria do gráfico), `usinas` (cadastro), `explica` (o que cada alerta
quer dizer, em linguagem de quem não é da meteorologia), `visao` (o que a tela e a página da usina escrevem). As rotas são de
`nexus/torres/performance/clima_tela.py`; o CSS, `nexus/static/clima.css`. Provas da didática: `tests/test_clima_explica.py`.

**Regras que custaram caro**
- **O Pillow não abre o GeoTIFF do INPE.** É um COG de 64 bits (BitsPerSample 64, LZW, tiles de 256, 8699 x 8899): o plugin
  TIFF do Pillow só tem modo para float de 32 bits (`UnidentifiedImageError`, "unknown pixel mode", medido com o 12.2), e
  rasterio e shapely estão vetados (sem dependência nova). `geotiff.py` lê só o cabeçalho e a tile de cada usina, por `Range`,
  e decodifica o LZW em Python puro (bytes idênticos aos do Pillow nas 1190 tiles do T0). Aceita **só o formato medido**
  (little-endian, tiles, LZW sem predictor, float64, EPSG:4326, PixelIsArea, escala + tiepoint no canto); o que mudar vira
  `GeoTiffErro` dizendo o que achou, e a tela diz que o formato do INPE mudou. Custo medido (160 usinas, 4 dias em paralelo):
  ~7 s e ~4,6 MB na leitura fria, uma vez a cada 6 h (ou quando o conjunto de usinas muda).
- **O arquivo do INPE troca todo dia, às ~06:30, e o leitor sabe disso:** o cabeçalho (os offsets das tiles) é de um arquivo, e
  as tiles saem por `Range` com `If-Range` = o Last-Modified da 1ª resposta. Se o arquivo mudar no meio, o servidor manda o
  novo inteiro (200) e o leitor levanta `GeoTiffErro` ("foi trocado no meio da leitura"), em vez de decodificar a tile de um
  arquivo pelos offsets de outro (lixo ou, pior, um número plausível de outro dia). Conferido ao vivo: o servidor do INPE
  responde 206 ao `If-Range` com o Last-Modified exato. Sem Last-Modified a leitura funciona, e a fonte fica em atenção.
- **Pixel sem dado (-999):** o INPE não calcula onde não há vegetação (cidades, água e, às vezes, a própria usina: 1 de 40
  coordenadas de referência). Vale o MAIOR valor do quadrado de 5 x 5 pixels (~2 km), com a nota "entorno"; se nem o
  entorno tem dado, "sem dado (sem vegetação no entorno)" (não é alerta, e a tela lista essas usinas). Valor NEGATIVO que
  não é o nodata (-999) também é "sem dado", só naquele ponto (`GeoTiff.piso`): vale o entorno, e o dia não cai. Uma usina
  fora da grade do INPE nos quatro dias entra na mesma lista, com o motivo "fora da grade do INPE".
- **Faixas do risco de fogo** (as do `config.ALERTA` do pacote): mínimo < 0,15 ≤ baixo < 0,4 ≤ médio < 0,7 ≤ alto ≤ 0,95 <
  crítico; o valor é arredondado a 9 casas antes de comparar (o 0,70 em double pode chegar 0,6999999999999). Valor ACIMA de 1
  derruba o dia: uma escala trocada (0 a 100) acenderia o "crítico" em toda usina.
- **A borda do polígono conta como dentro** (o `contains` do shapely a exclui): um aviso que encosta na usina vale.
- **Os três níveis da usina (07/10/2026), regra em `alertas.py`:** o caso que os criou foi 06/10, na seca: 145 das 154
  usinas apareciam "com alerta" (baixa umidade e risco de fogo alto cobrindo o Nordeste e o Centro-Oeste) e só 3 pediam ação.
  **Agir agora** = foco a até 5 km (é evento, não previsão); OU aviso do INMET "Grande Perigo" de qualquer evento; OU aviso
  "Perigo" de tempestade, chuvas intensas, acumulado de chuva, vendaval, ventos costeiros ou granizo (comparados sem acento,
  sem caixa e pelo nome inteiro; evento fora da lista em Perigo vai para Atenção, nunca some). **Atenção** = qualquer outro
  aviso, em vigor ou futuro; OU risco de fogo alto ou crítico em algum dos quatro dias. **Sem alerta** = nada disso, e só se
  diz com as TRÊS fontes lidas. Aviso futuro conta (a tela diz quando começa). Dentro de cada nível, a ordem é a gravidade que já
  existia (3 = Grande Perigo, foco ou risco crítico; 2 = Perigo ou risco alto; 1 = Perigo Potencial) e, no empate: tem foco,
  mais tipos de alerta, foco mais perto, aviso mais grave, nome. Risco médio não é alerta. Com o arquivo de ontem do INPE (lido
  antes das ~06:30) o dia "Ontem" ainda conta como um dos quatro (a fonte já está em atenção e o rótulo diz o dia certo).
- **A tela não pode parecer "tudo bem" quando a fonte não foi lida inteira** (revisão de 06/10/2026). Fonte fora: a última
  leitura boa é servida com o erro e a hora ("INMET fora agora; última leitura boa às HH:MM"), nunca como fresca; sem leitura
  boa, o número é "—" (nunca 0). "Sem alerta" só é contado com as três fontes lidas (senão "—" e "não dá para dizer"); "Agir
  agora" vive de avisos e focos, "Atenção" de avisos e risco de fogo, e cada um só vira "—" quando NENHUMA das suas fontes foi
  lida. Seção vazia sem ter lido o que ela usa NÃO diz "nenhuma usina para agir agora": diz "Sem leitura de X: não dá para
  dizer que não há alerta" (só das fontes que ELA usa: o risco de fogo velho não tira o "agir agora"). A nota separa "Lendo
  agora: X" (a fonte ainda está sendo lida pela primeira vez; a tela volta em 10 s, não em 60) de "Os números da faixa e as
  listas não incluem: X" (a fonte está fora). Fonte lida só em parte (aviso sem polígono, arquivo de focos que falhou,
  linhas ilegíveis, dia do risco sem leitura), velha ou com o dado atrasado (focos parados há mais de 30 min, previsão de
  outro dia, sem Last-Modified) fica em atenção, nunca "ok": os números da faixa que dependem dela repetem o qualificador
  ("INMET: parcial", "focos: arquivos até 14:10", "INMET: dado de HH:MM") e, quando o número é 0, ficam âmbar em vez de
  verdes; na matriz, a célula de uma fonte sem leitura diz "sem leitura" (o "—" é "li e não há"). Uma
  fonte que "lê" mas não entende nada é erro, não "0": focos com todas as linhas ilegíveis, ou INMET com avisos e nenhum
  localizável, caem na última leitura boa com o erro. Depois de uma falha, 60 s sem insistir; uma busca por vez (quem chega
  no meio recebe a última boa, sem esperar a rede); cada falha vai ao log (WARNING `clima: <fonte> fora: <motivo curto>`,
  uma linha por falha, sem dado de usina), e uma busca interrompida (Ctrl+C) solta a trava.
- **Irradiação diária: NASA POWER (07/10/2026).** Escolhida pela medida contra as ETMs de 40 usinas (maio a setembro/2026, 2.642
  dias válidos): erro mediano de 7,4% no dia e de 3,9% no mês, 84% dos meses dentro de 10%; melhor que o satélite cru do
  Open-Meteo (5,7% no mês), grátis, sem chave e de uso livre (citar "NASA LaRC POWER"). A grade é de cerca de 50 km: vale para
  o total do mês e para achar ETM fora, não para analisar uma hora; revalidar de outubro a março (a medida é de seca).
  Formato conferido ao vivo: `properties.parameter.ALLSKY_SFC_SW_DWN` com chaves AAAAMMDD, a unidade em
  `parameters.ALLSKY_SFC_SW_DWN.units` ("kW-hr/m^2/day") e `header.fill_value` -999. **A NASA atrasa uns 5 dias** (em 07/10, o último
  dia era 02/10) e o que não saiu vem -999, que aqui é `None`, NUNCA zero; também vem um -999 ISOLADO no meio da série (visto em
  07/09), que é buraco: parte a linha do gráfico e a soma do mês diz quantos dias faltaram. Um fim no futuro ela corta em hoje;
  data ou latitude inválida volta HTTP 422. Formato diferente (não JSON, sem a série, data fora de AAAAMMDD, valor que não é
  número, fora de 0 a 15 kWh/m²/dia, unidade que não é kWh/m²/dia, outro valor de preenchimento) é erro explícito, nunca número lido do jeito
  errado. A coordenada vai no pedido com 2 casas (~1 km: a posição exata da usina não precisa chegar a um servidor de fora) e
  nunca aparece na página nem no log. Só a página da usina chama (um pedido por usina, 12 h de cache, os 40 dias que terminam
  hoje), com última leitura boa servida com a hora e 60 s sem insistir depois de falha, como as outras fontes.
- **A página da usina:** cabeçalho (nome, cliente, UF, nível), os alertas dela (por que agir, avisos com a vigência, foco, risco dos
  quatro dias), a irradiação (gráfico SVG feito no servidor com a conta do desenho aprovado, mês até agora com "até que dia a
  NASA publicou" e quantos dias faltaram no meio, tabela dia a dia recolhida) e as fontes com a hora de cada uma. O que a NASA
  ainda não publicou é uma FAIXA no fim do gráfico, nunca uma queda a zero. Usina que não existe: 404; sem coordenada ou com
  coordenada fora do Brasil: 200 dizendo o que falta, sem ir a fonte nenhuma. NASA fora ou com formato diferente: a página
  responde e os alertas seguem.
- **Comparação com a ETM: próxima etapa (investigado em 07/10/2026, só leitura da API de dados).** O GHI medido da usina EXISTE:
  a coluna `GHI (kWh/m²)` é a mesma nas abas por usina de `bd_thopen` (108 abas) e `bd_performance` (63), gravada pelo
  coletor com o GHI integrado no dia da estação (`docs/api-pv-operation.md`: `day_meteo` hoje, `custom_query meteo` nos dias
  passados), em kWh/m² por dia. A coluna e a unidade são certas (a coluna do IPOA, ao contrário, muda de nome: `IPOA (kWh/m²)`,
  `... DEF`, `... ETM`). O que NÃO é certo é a **ligação usina do cadastro x aba**: no `bd_performance`, nenhuma das 136 chaves
  ligadas do de-para (o código com prefixo do cliente, no formato `XXXX-ABC100`) é o nome de uma aba, e o nome da usina na Base UFV
  só é o de uma aba em 17 de 122; no `bd_thopen`, 79 das 89 chaves ligadas são o nome exato de uma aba e 10 não (o nome com
  número no de-para e a aba sem ele, ou o contrário), e 5 usinas têm duas chaves. Sem a ligação a tela NÃO compara: um "conferir a
  ETM" na usina errada seria pior do que nenhum. Para fechar: guardar no de-para (ou numa decisão da tela Ligações) a aba do GHI
  de cada usina; o resto é barato (a coluna, a unidade e o limite de 10% já estão decididos). Dado a ter em conta: o dia de hoje
  é parcial, e a leitura vazia, zero ou acima de 12 kWh/m² não vale.
- **Hoje, D+1, D+2 e D+3 pela data do calendário:** a data do arquivo (Last-Modified, em Brasília) mais k. Com o arquivo de
  ontem (lido antes das ~06:30), o T0 é "Ontem" e o T1 é "Hoje": chamar de "Hoje" a previsão de ontem seria mentir sobre o dia.
- **Usinas e coordenadas** vêm do cadastro (`nexus/cadastro/`): em operação, latitude e longitude cifradas e abertas só no
  processo do Nexus. A coordenada **nunca** vai à tela, ao log nem ao `repr` da usina (a única saída dela é o pedido à NASA, com 2
  casas). Usina em operação sem coordenada
  utilizável, ou com coordenada fora do Brasil (0 e 0, sinal ou latitude e longitude trocadas), aparece numa linha própria:
  nunca some. O risco de fogo é lido para TODAS as usinas com coordenada (o cache vale pelo conjunto de pontos); o filtro
  por cliente é só da tela.
- **O texto do aviso é de terceiros:** só entra escapado, e a cor do aviso nem é lida. Aviso sem polígono utilizável é
  contado e dito na fonte (atenção), não some. O mesmo aviso nas duas listas (`hoje` e `futuro`) conta uma vez; a chave é
  (id, polígono, início, fim), porque o mesmo id com polígono ou vigência diferente é OUTRO aviso. Início e fim vêm em horário
  de Brasília (UTC-3, sem horário de verão desde 2019) e sem fuso no texto; uma data sem hora no FIM vale até 23:59:59 daquele
  dia, e não até 00:00.
- **Focos:** a hora vem da coluna `data` (UTC), não do nome do arquivo (satélite polar chega atrasado); sem arquivo novo há
  mais de 30 min, a fonte fica em atenção, assim como arquivo que falhou ou linha ilegível (contadas e ditas). Um foco é um
  pixel com fogo detectado, não um incêndio confirmado.
- **Nenhum teste vai à rede:** `leitura.usar_sessao` e `leitura.usar_relogio` injetam a sessão falsa e o relógio; com
  `TESTING` e sem sessão injetada a fonte diz "sem fonte nos testes". O COG dos testes é montado no próprio teste
  (`tests/clima_cog.py`: contêiner à mão, LZW comprimido pelo Pillow), sem binário no repositório; a NASA é
  `tests/clima_power.py` (a série inventada, no formato real medido) e a tela e a página da usina dividem o mundo inventado de
  `tests/clima_mundo.py`. Teste sem `NEXUS_ARMAZEM_LOCAL` se recusa a abrir o cadastro de verdade.

**Fase 1 só lê, e nada é gravado no banco.** Histórico de aviso, foco ou risco seria fato novo da governança de dados
(`nexus/dados/CLAUDE.md`: entra primeiro no catálogo, com grão e dimensões): é outra fase.

**Fase 2 (fora desta entrega) e por quê:** a irradiação DIÁRIA por usina entrou em 07/10 pela NASA POWER (grátis, sem licença
a decidir); continuam fora a previsão de vento, chuva e convecção, os testes T1 a T5 de confiabilidade do POA e do GHI e a
substituição de ETM do `gridco_meteo`, que dependem do Open-Meteo, cuja API grátis é só para uso não comercial. Antes de ligar
isso, decidir a licença: plano pago, ou servidor interno do Open-Meteo (ERA5 e previsão, uso comercial livre) mais o CAMS/SoDa
para a radiação de satélite. Cada troca de fonte pede recalibrar os parâmetros. A comparação com a ETM de cada usina também é
próxima etapa (ver "Comparação com a ETM", acima).

**Fogo das últimas 24 h: NASA FIRMS (10/10/2026).** Levi trouxe um roteiro de outra conversa ("Integrar NASA FIRMS ao
monitoramento de incêndio das usinas") e pediu: "veja se é viável para o que fazemos agora, se sim melhore e inclua coisas no
mapa". Viável, de graça e SEM chave: os arquivos públicos de focos ativos da América do Sul, um por satélite. O roteiro foi
adaptado ao que esta tela é (só leitura, cache por fonte, os três níveis aprovados):
- **Por que vale:** o foco do INPE conta só na última hora (os arquivos de 10 min): um fogo visto às 13h30 some da tela às 14h30,
  queimando ou não, e o satélite polar só volta umas 12 h depois. O FIRMS guarda as últimas passagens com a FORÇA (FRP, MW) e a
  CONFIANÇA de cada foco, que o INPE não publica. Para os satélites polares os focos são os MESMOS do INPE (o FIRMS não detecta
  mais; ele qualifica).
- **A regra (alertas.py):** fogo da NASA a até 5 km nas últimas 24 h é **Atenção** (nunca "Agir agora" sozinho: agir continua sendo
  o foco da última hora do INPE). Dentro da Atenção, o fogo forte (20 MW ou mais) ou a até 2 km com confiança nominal ou alta pesa 3
  na ordem, o resto 2. Fraco < 5 MW <= médio < 20 MW <= forte (na seca de 10/10/2026: mediana de 6 MW, 90% abaixo de 25 MW).
- **A confirmação:** o foco do INPE que manda agir ganha, na prova, "confirmado pela NASA (VIIRS NOAA-20, confiança alta, força 35 MW
  (forte))" quando há foco da NASA a até 1 km e 1 h dele; sem ele, "ainda sem confirmação dos satélites da NASA (eles passam perto das
  13h30 e da 01h30)". O mesmo fogo confirmado não se repete no "Também".
- **A própria usina:** foco (do INPE ou da NASA) a até 400 m do ponto da usina leva "pode ser a própria usina (reflexo do sol nos
  módulos ou telhado quente); confira antes de acionar" (o FAQ do FIRMS cita telhado metálico e reflexo solar). NÃO tira o nível: fogo
  dentro da usina também existe. O roteiro mandava excluir; aqui marca.
- **Honestidade:** a NASA é a quarta fonte do painel e entra no "Sem alerta" (a faixa diz "nas quatro fontes lidas"). Sem a leitura
  dela a usina NÃO fica cinza (o agir e o resto da atenção não dependem dela): o verde vira "sem alerta nas fontes lidas", a faixa
  qualifica ("sem leitura de fogo das últimas 24 h da ... (NASA FIRMS)") e a célula "Fogo a até 5 km" diz "não na última hora". A
  escolha é de propósito: até a T.I. liberar `firms.modaps.eosdis.nasa.gov`, o servidor não lê a NASA, e o mapa inteiro cinza
  esconderia o que as outras três fontes sabem. Sem foco novo há 18 h (as passagens são às ~13h30 e ~01h30, o dado chega em até
  3 h), a fonte fica em atenção ("passagens até ..."); satélite que não veio é "parcial".
- **O formato (medido em 10/10/2026):** VIIRS `latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,
  version,bright_ti5,frp,daynight` (satélite N, N20, N21; confiança low/nominal/high); MODIS com `brightness`/`bright_t31` no meio
  (satélite A/T; confiança 0 a 100: < 30 baixa, < 80 nominal). A hora é UTC (`acq_date` + `acq_time` HHMM). As colunas são achadas
  pelo nome; faltou uma das lidas, `FonteErro`. Só a caixa do Brasil fica na memória (~100 mil focos em 40 h na seca, ~20 MB); a
  janela de 24 h é de quem usa (`alertas.focos_nasa_24h`), e o índice das 24 h sai uma vez por leitura e por 5 min
  (`visao.indice_nasa`). **O servidor da NASA IGNORA o If-None-Match e o If-Modified-Since** (200 com o arquivo inteiro, conferido
  ao vivo): a releitura faz um HEAD por arquivo e só baixa o que mudou (4 HEADs em 0,25 s; a leitura fria, 4 arquivos em paralelo,
  ~9 MB em ~3 s).
- **O mapa:** os focos da NASA a até 25 km de alguma usina (o que interessa e o peso: 25 km pegam uns poucos milhares dos ~50 mil
  do Brasil), um ponto por detecção, o tamanho pela força (3 caminhos `mp-na-fraco/medio/forte`), numa cor própria (`--cl-nasa`,
  rosa-avermelhado: não é o laranja da última hora nem o vermelho do agir), ATRÁS dos focos do INPE e dos anéis. O botão "Focos"
  liga e desliga as duas camadas. A legenda tem a seção "Fogo nas últimas 24 h" com a contagem (a até 25 km e a até 5 km) e o que é
  a força; a dica da usina tem a linha da NASA; a tabela, o motivo ("Fogo a 3,0 km há 6 h").
- **Fora desta entrega, e por quê:** o histórico por usina (VIIRS desde 2012, MODIS desde 2000, para planejar roçagem e aceiro antes
  do pico) precisa da API por área com MAP_KEY (grátis, pedida com o e-mail de quem for dono) ou do download em lote, e de guardar no
  banco: é fato novo da governança de dados (catálogo antes). A máscara de fontes de calor fixas (olaria, indústria) precisa desse
  histórico. O vento contra a usina depende da decisão de licença do Open-Meteo (ver "Fase 2"). O relatório diário das 7h é outra
  entrega.
- **Ao vivo (10/10/2026, 00:45, seca, 154 usinas):** 48.632 focos da NASA no Brasil nas últimas 24 h; 9 usinas com fogo a até 5 km
  (4 forte, 5 médio), todas já em Atenção por outro motivo (baixa umidade e risco de fogo): a faixa ficou a mesma (3 agir, 151
  atenção), e o fogo virou o primeiro motivo delas.
- Prova: `tests/test_clima_firms.py` (o leitor, o HEAD, a regra, a confirmação, a própria usina, a honestidade, a camada e as telas).

**Servidor da T.I.:** precisa de saída para `apiprevmet3.inmet.gov.br`, `dataserver-coids.inpe.br`, `power.larc.nasa.gov` e, desde
10/10/2026, `firms.modaps.eosdis.nasa.gov` (`DEPLOY.md`, seções 0 e 7c); sem elas a tela abre e mostra as fontes como "fora agora".

Como provar: `python -m pytest -q tests/test_clima_*.py tests/test_torre_performance_clima*.py`. Ao vivo (06/10/2026, 40
coordenadas de referência, só leitura): 25 usinas dentro de algum aviso, 1 com foco a 1,9 km, 18 com risco alto ou crítico;
1,6 s e 0,7 MB por dia de risco. Mudou o leitor do GeoTIFF? Confira as tiles contra o Pillow (monte um mini-TIFF de uma faixa
com `int32` no lugar de `double`: os bytes são os mesmos) antes de confiar.

## Mapa de risco (07/10/2026): o Clima e risco num mapa do Brasil, só leitura

Aba Performance → Mapa de risco (`/t/performance/clima/mapa`, filha da lista; o cabeçalho tem "Ver a lista" e "Modo TV", e o da lista tem "Ver no mapa"). Pedido do Levi
(07/10), como tela à parte: a lista segue sendo a leitura detalhada, o mapa mostra ONDE. **Não é outra conta:**
lê as MESMAS três fontes pelo MESMO cache (visitar a lista e o mapa não faz pedido a mais à rede) e o nível de cada usina vem da
mesma regra (`alertas.nivel_da_usina`: Agir agora = vermelho, Atenção = amarelo, Sem alerta = verde).

Código: `clima/mapa.py` (sem Flask: contorno, projeção, recorte, caminho, o estado da tela e `montar`), `clima/calor.py` (as
camadas de calor, 09/10), `torres/performance/mapa_tela.py` (rota; `?tv=1` troca o template), os templates
`performance/mapa.html` (com a casca) e `mapa_tv.html` (sem), que dividem os pedaços `_mapa_barra.html`, `_mapa_legenda.html`,
`_mapa_svg.html` e `_mapa_tabela.html`, `static/clima-mapa.css` (soma-se ao `clima.css`, que traz os tokens `--cl-*`, o
cabeçalho, o painel das fontes e o rodapé) e `static/clima-mapa.js` (a interação, 09/10). Provas: `tests/test_clima_mapa.py`
(contorno, projeção, vista, caminho), `test_clima_mapa_camadas.py` e `test_clima_mapa_calor.py` (o modelo), `test_clima_calor.py`
(a leitura da área no COG, as classes, a densidade, a máscara, as faixas e as rampas de cor), `test_torre_performance_mapa.py` e
`test_torre_performance_mapa_tv.py` (a tela, o modo TV e a cadeia de verdade, por sessão falsa), `test_clima_mapa_js.py` (as contas
do JavaScript, no node) e o mundo inventado de `tests/clima_mapa_mundo.py`. O id da `Tela` é `clima/mapa`, **com barra**, para o endereço ser esse (o
placeholder `/<tela_id>` não casa com barra, e a view própria responde); por isso a vitrine estática exporta
`t/performance/clima/mapa/index.html`, um nível abaixo, e o teste da vitrine conta `t/**/index.html`.

**O contorno: fonte e licença.** IBGE, Malhas territoriais, API de malhas v3, divisão por UF, resolução mínima:
`https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?formato=application/vnd.geo+json&qualidade=minima&intrarregiao=UF`
(só leitura, sem chave). Baixado UMA vez em 07/10/2026 e guardado como veio em `nexus/static/clima/ibge-ufs-minima.geojson`
(98.502 bytes, 27 UFs, ~5.500 vértices com 4 casas, sha256 `07c671aa…e7c0f`), abaixo dos 300 KB do pedido, então sem
simplificar. **Nada é buscado no IBGE em tempo de execução.** Dado público do IBGE, de uso livre com citação da fonte: a tela
diz "Dados: IBGE, INMET, INPE (Programa Queimadas)" e o rodapé cita as Malhas territoriais. *Atenção: o texto oficial da licença
não foi conferido (o único acesso à rede foi o download); antes de redistribuir o arquivo fora deste repositório, confirme os
termos em `https://www.ibge.gov.br/acesso-informacao/dados-abertos.html`.* O IBGE manda só `codarea` (código da UF), sem sigla
nem nome: a tabela `mapa.UFS` é a da divisão política. **Refazer o arquivo** (o IBGE publica uma malha por ano): o mesmo `curl`
no mesmo caminho e `python -m pytest -q tests/test_clima_mapa.py`, que confere as 27 UFs, o tamanho, anéis fechados, só o
continente e o rótulo de cada estado dentro dele. O teste do continente existe porque `qualidade=minima` não traz Trindade nem
Fernando de Noronha: uma malha com ilhas alargaria o recorte do Brasil em ~15% de oceano, e quem trocou decide.

**Regras do desenho**
- **SVG do servidor, sem biblioteca de mapa, sem mapa de terceiros, sem CDN novo.** O viewBox tem SEMPRE 1000 de largura e a
  altura sai da geografia: o CSS decide raios em unidades do SVG e traços em pixels de tela (`vector-effect:non-scaling-stroke`), e
  o contorno fica fino em qualquer largura. O SVG ocupa 100% da largura (`height:auto`, `max-height:84vh` no desktop); abaixo de
  820 px entram o `--mp-k` e o fim do `max-height`. O `clima-mapa.js` (09/10) só ENFEITA: sem ele, o mapa é o do servidor, os
  controles são links e a página se recarrega (o `<meta refresh>` foi para dentro de `<noscript>`).
- **Legenda à esquerda, mapa no meio, tabela à direita** (Levi, 09/10/2026: "jogue essa visão do anexo para a esquerda do mapa e
  na direita uma tabela com o nome das usinas, os riscos e uma forma resumida do motivo do risco"). Container query no `.mp`
  (conta a largura da tela, não a da janela): o padrão é uma coluna com o mapa primeiro; a partir de 760 px, legenda e mapa lado a
  lado e a tabela embaixo; a partir de 1120 px, as três lado a lado, e a tabela rola por dentro na altura da linha (o
  `contain:size` impede as 154 linhas de esticarem a página). A página do mapa vai até 1720 px (a lista fica nos 1280 do `.cl`),
  e a tabela tem até 400 px; com 1300 px de tela útil ou mais, até 520 px, e o motivo cabe numa linha (Levi, 09/10: "aumente o
  tamanho de usinas em risco um pouco para a direita"). Só com folga: a 1440 px com o menu aberto, 520 px deixavam o mapa com
  uns 390 px; com o limite, ele fica com uns 520. A tabela (`m["tabela"]`) tem uma linha por usina do recorte, na
  ordem Agir agora, Atenção, Sem leitura completa, Sem alerta e, dentro do nível, da mais grave para a menos (depois o nome); o
  risco vai na cor, na bolinha e na palavra; o motivo é o `visao.motivo_curto` da lista ("Nada previsto" com as três fontes
  lidas, "Sem leitura de X" sem elas); o nome leva à página da usina.
- **Projeção equiretangular com a correção de cos(latitude média).** Cada recorte (Brasil e as cinco regiões, `?regiao=norte|
  nordeste|centro-oeste|sudeste|sul`; vazio ou desconhecido cai no Brasil) usa a latitude do MEIO dele e refaz o viewBox: com o
  cosseno do país inteiro (14 graus) o Sul (28) ficaria 10% largo demais. O seletor são links (`<a href="?regiao=...">`), então
  funciona sem JS. O recorte é uma MOLDURA, não uma lista por UF: uma usina de São Paulo aparece no recorte do Centro-Oeste se a
  moldura a pega, e a legenda diz quantas ficaram de fora.
- **O caminho SVG vai em deslocamentos** medidos do ponto JÁ arredondado (uma casa), sem deriva, com os vértices que arredondam
  para o mesmo ponto fora: o Brasil inteiro pesa 42 mil caracteres (a metade do absoluto). A página do Brasil, com 154 usinas,
  5 mil focos e 60 avisos (dado inventado do tamanho do real, 07/10): 36 ms no servidor, 200 KB (49 KB comprimido); uma região,
  de 11 a 22 ms. A primeira visita depois do boot soma ~25 ms (lê o JSON e escreve os caminhos, que ficam guardados por vista).
- **O fogo das últimas 24 h da NASA (10/10/2026)** entra entre as siglas e os focos do INPE (ver "Fogo das últimas 24 h: NASA FIRMS").
- **Camadas, de trás para frente:** estados (com a sigla, que some no celular na visão do Brasil) → a camada de calor (quando é
  ela o fundo) e as divisas por cima dela → avisos do INMET → siglas → focos do INPE → anéis → usinas → o aro da usina escolhida. O aviso é um grupo por nível, e a transparência é do GRUPO: polígonos do mesmo nível não se somam onde se
  cruzam (cem avisos de baixa umidade virariam uma mancha opaca). O aviso que AINDA VAI COMEÇAR vai só no contorno tracejado: a
  usina em Atenção por aviso futuro precisa ter o motivo visível. O vencido não desenha. Os focos são pontos de ponta redonda
  (`M x y h.01` num `<path>` só: 5 mil focos pesam 70 KB, como `<circle>` seriam 190 KB; foco em cima de foco, no desenho, vira um
  ponto, e a contagem da legenda continua a da fonte). **O anel vai no FOCO, não na usina:** nos focos a até 5 km de ALGUMA
  usina do cadastro (`IndiceFocos.no_raio`, que o `perto` também usa).
- **Usina:** `<a href="/t/performance/clima/usina/<id>">` (id escapado, `quote(safe="")`) com `<title>` de quatro linhas (nome,
  cliente, nível, motivo; no máximo 3 motivos, os que mandam agir primeiro, para o "e mais N" nunca esconder a causa). Desenhada
  por nível, o que pede ação por cima e maior (cor, tamanho e palavra: nunca só a cor), com um círculo transparente de 2,2 raios
  que aumenta a área de toque. No celular o `--mp-k` (1,5) escala pontos, alvos e anéis.
- **Honestidade, a mesma da lista.** Fonte sem leitura (fora ou lendo): a camada some e a legenda diz por quê ("sem leitura
  boa" ou "lendo agora"); a usina que ficaria "Sem alerta" fica CINZA ("Sem leitura completa", e a linha "Sem alerta" da legenda
  some): sem ler os avisos, não dá para dizer que não há aviso. Fonte lida só em parte, velha ou atrasada: a camada fica, o verde
  vira "Sem alerta nas fontes lidas" e a legenda traz o qualificador ("parcial", "dado de HH:MM", "N avisos sem polígono utilizável
  não aparecem"). O painel de frescor é o MESMO CÓDIGO da lista (`visao._fonte_inmet/_fonte_focos/_fonte_risco`), e há teste que
  compara os dois. O risco de fogo entra na cor da usina (Atenção, se alto ou crítico em algum dos 4 dias) e, desde 09/10, também é
  uma camada de fundo (abaixo); a leitura da camada diz a hora dela na própria legenda, não no painel.
- **Contorno que não abre** (arquivo ausente ou quebrado: `estados()` levanta `ValueError` ou `OSError`): a tela NÃO dá 500. O
  mapa sai sem as divisas e sem o recorte por região (a vista do Brasil vem de `LIMITES_BRASIL`, números fixos que um teste
  confere contra o arquivo), com a nota "O contorno dos estados não abriu...", e o motivo vai ao log (`clima: o contorno dos
  estados do IBGE não abriu`). As usinas, os avisos e os focos continuam, como em qualquer camada que perde a fonte.
- **Coordenada:** a POSIÇÃO é permitida (atrás do login, como o cadastro); o NÚMERO de latitude ou longitude nunca vira texto (nem
  no `<title>`, nem em atributo com nome de coordenada). O teste olha número de 3 casas ou mais NO TEXTO, e a fixture usa
  coordenadas com 5 casas para o vazamento do número inteiro ser achado.
- **Escape:** nome de usina e de cliente e evento do INMET só entram por `{{ }}` (autoescape do Jinja), nunca por `|safe`;
  o `<title>` do polígono e o da usina têm teste com `<script>` e aspas.

**Dependência que o mapa tem da tela principal (conferir ao mexer em `visao.py`):** `visao._fonte_inmet/_fonte_focos/
_fonte_risco/_arquivo_t0/_validade` (privadas) e `visao.rotulos_dos_dias/celula_de_risco/numero/hora/agora` (públicas). Se uma
for renomeada ou mudar de forma, quem quebra é `tests/test_clima_mapa_camadas.py` (e o `test_o_painel_das_fontes_e_o_mesmo_da_tela_
principal` diz se os dois painéis divergiram). O CSS usa os tokens `--cl-*` do `clima.css` e os do `nexus.css`: renomear um deles
quebra `test_o_css_do_mapa_so_usa_cores_que_o_clima_css_ou_o_nexus_css_definem`.

**Dois temas (08/10/2026):** `clima.css` e `clima-mapa.css` não têm cor fixa; os `--cl-*` apontam para o semáforo do
`nexus.css` (no escuro, os mesmos valores de antes), e o mar, a terra, a borda e a sigla do estado são `--mapa-*`. No claro,
o Perigo Potencial do mapa usa o âmbar de área (`--alerta-cheio`): o `--cl-atencao` do claro é o âmbar escuro de texto, e a 24%
virava mancha marrom. A regra geral (cor só por token) está em `nexus/casca/CLAUDE.md`, seção Tema.

**Interação, camadas e modo TV (09/10/2026).** Levi: "Quero o mapa mais interativo", "Além de tempestade conseguimos uma outra
visão tipo um mapa de calor no mapa? quanto mais versatilidade melhor!" e "Quero visão de tela cheia para colocar no video wall".
Celular ficou fora (Levi, 09/10: "não precisa de no celular, por hora"): nada foi feito só para ele, e o que já funcionava continua
(o toque na usina abre a página, a página rola, sem rolagem lateral).
- **O estado mora no endereço** (`mapa.estado_da_tela`, validado: o desconhecido cai no padrão): `fundo` (avisos, o padrão; risco;
  densidade; nenhum), `ver` (usinas, focos, siglas; ausente = todos), `dia` (0 a 3, o dia do risco; ausente = o "Hoje" do arquivo),
  `cliente` (o mesmo filtro da lista), `ocultar` (níveis escondidos), `sem_eventos` (eventos do INMET escondidos), `regiao`, `tv` e
  `girar`. Cada controle é um link com o resto do estado (`mapa.parametros`; o estado padrão é o endereço puro, e os links de
  região são os de antes). Com JavaScript, o clique muda o desenho na hora e relê a página no endereço novo.
- **A camada de FUNDO é uma por vez:** duas camadas de área juntas (o vermelho do aviso e o do calor) viram uma mancha só. Por cima,
  usinas, focos e siglas ligam e desligam à vontade. Os níveis (legenda) e os eventos dos avisos também escondem e mostram, no mapa
  e na tabela (`:has()` no CSS).
- **Risco de fogo do INPE em quadrados** (`calor.py`, `fontes.inpe_risco_grade`, `GeoTiff.somar_em_blocos`): o MESMO arquivo do risco
  por usina, lido na área do Brasil (só as tiles que encostam no contorno: 148 de 289 em 09/10/2026, 8,1 MB), em blocos de 0,08 grau
  (8 pixels); no Brasil inteiro, 2 x 2 (0,16 grau, ~18 km). A cor é a MÉDIA dos pixels com dado (soma e contagem, nunca média de
  médias), nas cinco classes da régua das usinas (`alertas.classe_risco_fogo`); quadrado com menos de 1/4 dos pixels com dado fica
  SEM COR (cidade, água: o INPE não calcula), e a legenda diz quanto da área ficou assim. A usina usa o pixel dela, então a cor do
  ponto pode ser outra que a do quadrado (a legenda diz). Lido AO FUNDO (`leitura.risco_grade`, um cache por dia, TTL do risco): a
  primeira visita diz "lendo" e o mapa volta em 10 s. Medido em 09/10/2026 no arquivo real: 10,5 s e 7,1 s de CPU (o LZW em Python)
  numa thread, uma vez por arquivo; ao vencer, relê só o cabeçalho (64 KB) e, com o mesmo Last-Modified, não baixa tile nenhuma.
  Só é lido quando alguém liga a camada (ou o modo TV gira por ela); os quatro dias são arquivos à parte, lidos só se escolhidos.
- **Densidade de focos** (`calor.densidade`): os MESMOS focos da camada de pontos, num núcleo quártico (50 km no Brasil inteiro, 25 km
  numa região: com 25 km no Brasil cada foco virava um pontinho de 2 pixels), em focos por 1.000 km², em cinco classes fixas (0,5,
  2, 5 e 20). Sem foco no raio, zero e sem cor ("nenhum foco a até X km"). A legenda diz quanto um foco sozinho dá no centro.
- **O desenho do calor** é vetorial: uma classe é UM `<path>` de faixas horizontais (`M x y h w`, as seguintes da linha por `m dx 0 h
  w`, medidas do ponto já arredondado), com o traço da altura do quadrado mais 0,3 (`calor.SOBREPOR`: sem isso ficava uma fresta
  escura entre linhas, vista em 09/10), recortado pelo contorno (`<clipPath>` com `<use>` de cada estado); a máscara do Brasil
  (varredura por linha, dilatada em 1 quadrado) tira do desenho o que é mar ou vizinho. O desenho de cada leitura e recorte fica
  guardado (`mapa._guardado`): 0,14 s no Brasil inteiro com o arquivo real, uma vez. As rampas de cor (`--calor-risco-1..5`,
  `--calor-densidade-1..5`, nos dois temas) passaram no validador do skill de dataviz em modo ordinal (um matiz, luminosidade
  monótona, passo >= 0,06; o primeiro passo encosta na terra de propósito, mas distinto dela); `test_clima_calor.py` repete a conta.
  Sobre o risco, o foco vai em cinza (o laranja sumia no laranja).
- **A interação** (`clima-mapa.js`): roda do mouse aproxima em volta do ponto, arrastar move, botões + / − / enquadrar / voltar, setas,
  + − 0 e Backspace no teclado (o mapa recebe foco); clique no estado aproxima (a caixa dele, em unidades do desenho, vem no JSON da
  página); a dica (usina: nome, nível, motivo e o que pesou, com a fonte por extenso; aviso, quadrado de calor, foco e estado também);
  clique na usina marca a linha da tabela e o segundo clique abre a página (ctrl/cmd abre em outra aba; no celular o toque abre, como
  antes); clique na linha (fora do link) marca a usina no mapa e a traz para a vista; o foco do teclado faz o mesmo; a busca leva até
  a usina. O zoom só troca o viewBox; os pontos e as siglas não crescem com ele (`--mp-zp`, `--mp-zt`), e num mapa estreito (a 1440 px
  ele tem ~390 px, com a tabela de 520) o ponto cresce até 1,8x (`--mp-k`). A dica não fica presa no mapa (cobria metade dele).
- **A releitura sem recarregar, no ritmo dos caches:** cada `Leitura` diz quando vence (`vence_em`), e `visao.proxima_leitura_s` dá o
  `data-proxima-s` da página (o vencimento do primeiro cache usado, mais 5 s; 10 s enquanto uma fonte é lida pela primeira vez; nunca
  mais que 30 min). O JavaScript relê a MESMA URL com `redirect: "manual"` e troca só os pedaços `data-parte`, sem perder o zoom nem a
  usina escolhida. Redirecionamento (o portão mandou para o Entrar) ou página sem o mapa = "a sessão terminou"; erro ou sem resposta =
  "o Nexus não respondeu": a faixa diz desde quando é o dado e um véu (`--veu`) cobre o mapa, até a próxima leitura boa. A resposta vai
  com `Cache-Control: no-store`.
- **Tela cheia** (Fullscreen API): o palco (controles, legenda, mapa, tabela) ocupa a tela; o botão só aparece onde o navegador deixa.
- **Modo TV** (`?tv=1`, `mapa_tv.html`): sem a casca (sem menu e sem topo; guarda anti-moldura e tema como na casca), sem rolagem,
  a letra segue a altura da tela (`html.mp-tv-html{font-size:2.2vh}`: ~24 px em 1920 x 1080, ~48 px em 3840 x 2160), relógio, o
  título da camada com a fonte por extenso, os três números (Agir agora, Atenção, Sem alerta), a tabela com as linhas que cabem e "e
  mais N", e as fontes com "lido às" no rodapé. `girar=N` (10 a 600 s) alterna avisos, risco e densidade sozinho, sem pedir nada ao
  servidor (as três vêm na página). Os controles aparecem ao mexer o mouse ou apertar uma tecla e somem em 6 s; o cursor some junto.
  O login vale igual (a mesma rota; sem sessão vai para o Entrar e volta), e cada releitura renova a sessão de 12 h.

**O que o mapa não faz, de propósito:** mostrar a coordenada; ilhas oceânicas (o contorno mínimo não as tem: uma usina ali cai em
"fora deste recorte"); pinça no celular (fora do escopo de 09/10); a NASA POWER no mapa (um pedido por usina, 12 h: só na página da
usina); quadrado de calor mais fino ao aproximar (o zoom do navegador amplia o desenho do recorte; uma região do servidor tem
quadrados de 0,08 grau).

Como provar: `python -m pytest -q tests/test_clima_mapa.py tests/test_clima_mapa_camadas.py tests/test_clima_mapa_calor.py
tests/test_clima_calor.py tests/test_clima_nomes.py tests/test_clima_mapa_js.py tests/test_torre_performance_mapa.py
tests/test_torre_performance_mapa_tv.py` (sem rede; os do JavaScript precisam do node). Na tela, com as fontes inventadas (o
"mundo falso" da conferência, porta 5077): `/t/performance/clima/mapa` a 1440 px nos dois temas (zoom pela roda, dica, clique na
usina e na linha, clique no estado, risco de fogo com a dica do quadrado, densidade, busca, teclado, filtro de nível, tela cheia) e
`?tv=1` a 1920 x 1080 e 3840 x 2160 (sem rolagem, `?girar=15`, a sessão que cai), medindo os erros de JavaScript e a rolagem
lateral. Abrir o mapa, medido em 09/10 com as mesmas fontes inventadas: servidor 24,7 -> 30,5 ms (HTML 201 -> 252 KB, 34 -> 42 KB
com gzip); no navegador, DOMContentLoaded 578 -> 590 ms e load 742 -> 759 ms (o mapa fica pronto para a interação no próprio
DOMContentLoaded).
