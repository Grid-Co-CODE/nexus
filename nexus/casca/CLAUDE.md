# CLAUDE.md — casca (moldura, login, menu e tema)

O que envolve todas as torres: o layout, o portão de login, a troca de cadeira, o tema (escuro ou claro) e o `/saude`.

## Os arquivos

| Arquivo | O que faz |
|---|---|
| `nexus/__init__.py` | `create_app`: lê o `.env`, o cookie `nexus_sessao`, o prefixo, instala o portão e o contexto, descobre as torres |
| `nexus/prefixo.py` | o caminho em que o Nexus é servido (`NEXUS_PREFIXO`): o middleware, `na_raiz`/`sem_raiz` e o cookie no caminho certo |
| `nexus/templates/_raiz_js.html` | `window.NEXUS_RAIZ` e `nexusRota()` para o JavaScript, no `<head>` de base, entrar, modo TV e card da OS |
| `nexus/config.py` | `OBRIGATORIAS` (sem elas o app não sobe e diz qual falta) e `OPCIONAIS` |
| `nexus/casca/__init__.py` | `/` (Início), `/cadeira` (troca), `/tema` (troca sem JavaScript), `/saude` (`{"commit", "ok"}`) e o contexto dos templates (menu, `tema`) |
| `nexus/auth/__init__.py` | `/entrar`, `/sair` (com a porta única ligada, passa pela plataforma: `templates/sair.html`) e o portão (`before_request`) |
| `nexus/auth/fracttal.py` | o login pelo Fracttal: o `api.fracttal_login` do clone do OS Creator; abre também o cookie `os_sessao` (/os) |
| `nexus/cadeiras.py` | as 10 cadeiras; diretoria e chefia caem na torre Comando |
| `nexus/templates/base.html` | a moldura: menu lateral, recolher (`[` ou botão, lembrado em `localStorage` `nexus.menu`), menu do celular, botão do tema (que troca também as molduras do OS Creator abertas) |
| `nexus/templates/_tema_cabeca.html` | o script do tema no `<head>` (base e entrar): a reserva do `localStorage` antes de pintar |
| `nexus/static/nexus.css` | os tokens do Design System Grid Co. nos dois temas e o subconjunto `gc-*` |
| `app.py` / `servir.py` | desenvolvimento (5070, IPv4 e IPv6, cookie sem Secure) / produção (atrás do proxy, cookie Secure) |
| `ferramentas/subir_copia_de_prova.py` / `ferramentas/porta_local.py` | cópia de prova noutra porta (sem carga, sem Fracttal ao subir, trava de rede) / o papel do Caddy no PC, Nexus e plataforma numa origem só; só repassa, sem pote de cookies (10/10/2026: o pote guardava o `session` de uma resposta e o dava a quem chegasse sem cookie; `tests/test_porta_local.py`) |

## O prefixo `/nexus` e o cookie próprio (porta única, 09/10/2026)

Levi: "a partir de segunda quero o Nexus como link principal; o Nexus será o centro de tudo". O servidor serve o Nexus em
`app.gridco.com.br/nexus`, ao lado da plataforma de Performance na raiz (spec `docs/superpowers/specs/2026-10-09-performance-no-nexus-design.md`,
seções 2 e 5.1). Até 09/10 o código não sabia do `/nexus`: o menu, o Início, o Sair e os `fetch` saíam da raiz e caíam
na plataforma, e o cookie `session` dos dois sistemas (mesmo nome, mesmo caminho) se apagava a cada login.

- **Cookie (passo 0):** `nexus_sessao` (nunca mais `session`, o da plataforma), no caminho em que o Nexus roda
  (`SessaoNoPrefixo`: `/nexus` no servidor, `/` na raiz); o `os_sessao` do OS Creator embutido em prefixo + `/os`
  (`auth.os_cookie_path`, e o `_SessaoDoClone` da ponte). Efeito único da troca: quem estava logado entra de novo uma vez.
  Debaixo do prefixo, o Sair e o Entrar apagam também um `nexus_sessao` de `Path=/` que tenha sobrado da janela entre
  publicar o código e pôr a variável (`auth._sem_a_sessao_velha_da_raiz`; revisão de 10/10/2026: ele seguia válido e a
  pessoa saía e continuava logada).
- **Prefixo:** `NEXUS_PREFIXO` (`.env` ou ambiente; vazio = raiz, o PC e a fase 4, cujo Caddy está pronto no
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
  nada sai `/nexus/nexus` (`test_com_a_reescrita_do_servidor_ligada_nada_sai_com_o_prefixo_dobrado`). Depois de ligar a
  variável a camada vira inútil e a T.I. pode tirá-la (`DEPLOY.md`, seção 5). Local: `ferramentas/porta_local.py
  --reescrita-do-servidor` a imita. O `/saude` do servidor já respondeu um commit enquanto os estáticos eram de outro: lá ele
  não prova versão sozinho.
- **O `nexus_tema` fica em `/`** (o botão grava pelo navegador; nome próprio, não colide).
- **Endereço da PLATAFORMA é outra coisa** (porta única, 09/10/2026): as molduras da Performance escrevem, de propósito, endereços da plataforma na raiz (`/painel/nexus/entrar`, `/painel/nexus/sair` e as telas do mapa, como `/tempo-real` no "Abrir em outra aba"), porque ela mora na raiz ao lado do Nexus. Esses não levam `{{ raiz }}`: no template a variável se chama `plataforma` (`{{ plataforma }}/painel/nexus/entrar`, que o varredor estático aceita) e o rastreador os separa (`da_plataforma`). No JavaScript, a plataforma se pede por URL completa (o calço da camada da T.I. poria `/nexus` num `fetch("/api/...")`). Regra em `nexus/performance/CLAUDE.md`, seção "Porta única".
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
  1180 px e no celular fica só o ícone; de 821 a 1180 px o seletor de cadeira é quem encolhe (sem isso o topo passava
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

## Regras que já custaram caro

- **Endereço do Nexus nunca a partir da raiz** (09/10/2026): `href="/t/..."`, `redirect("/t/...")` ou `fetch("/os/...")`
  crus caem na plataforma debaixo do `/nexus`. Use `{{ raiz }}`, `url_for`, `|na_raiz`, `na_raiz()` e `nexusRota()` (seção
  do prefixo); `tests/test_prefixo.py` pega o esquecimento.
- **Rota pública é decisão consciente:** só o que está em `ROTAS_PUBLICAS` (entrar, saude, static). O teste
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
  no topo), `admin` (só se o e-mail estiver em `NEXUS_ADMINS`) e `supervisor_padrao`: desde a estrutura de O&M de
  10/2026, o PAPEL de quem entrou no Campo · App ({pessoa_id, nome, papel: supervisor_campo | coordenador | gestor,
  regioes ou gestor}; o filtro que já vem marcado e quem vê o Aprovar; ver `nexus/torres/campo/CLAUDE.md`). Sessão de
  antes, com o nome do supervisor em texto, não vale como papel. A
  senha de admin segue em "Entrar com a senha de administrador" (`/entrar?admin=1`) e é a porta do Cadastro. Quem
  tem conta no Fracttal entra, técnico inclusive: restringir por perfil, se o Levi pedir, é aqui.
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
  casca tem `window.nexusEntrarDeNovo(url)` para as telas que recebem o 401. Sessão de antes desta regra (sem
  `fracttal_exp`) ganha o prazo no primeiro pedido de /os. Prova: `tests/test_auth_sair_fracttal.py`; na tela, uma
  cópia em 127.0.0.1 com o Fracttal simulado (09/10: sair do OS Creator, token derrubado e token de 45 s vencendo, os
  três levando a janela ao login com o aviso certo).
  **Debaixo do `/nexus`** (a regra nasceu na raiz e entrou na porta única em 10/10/2026): o `encerrar` apaga o
  `os_sessao` em `os_cookie_path()` (com `/os` fixo o delete não casava e o OS Creator ficava logado) e o `nexus_sessao`
  velho de Path=/, e põe no `next` o caminho como o navegador o vê; o `/os/login` do clone já sai como
  `/nexus/os/login` e conta como "caiu" (`sem_raiz` no `_fim_na_resposta`); o `entrar.html`, o
  `nexusEntrarDeNovo` e a conferência da sessão pedem os endereços pelo `nexusRota`. Prova debaixo do prefixo, com o
  Caddy cortando: `tests/test_prefixo_sair_fracttal.py`.
- **`next_seguro`:** o `?next=` (e o `voltar` do tema e da cadeira, e o `/os/login?next=` de quem já entrou) só aceita
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
  tela, ela fica verde sozinha. A torre da cadeira deixou de ser verde (era o mesmo sinal); fica só a etiqueta "sua".
  Exceção: as molduras da Performance (porta única) só contam com a `NEXUS_SSO_CHAVE` (`moldura.SO_COM_A_PORTA`):
  sem ela abrem o aviso "ainda não ligada" e o verde mentiria (revisão de 10/10/2026).
- **O Início conta pela mesma régua** (auditoria A3 da porta única, 10/10/2026): é a primeira página de todos, e dizia
  "fase 0" e "Com dado real: 0" com 40 telas prontas no ar. O número é "Telas prontas" (o tamanho de
  `telas_com_conteudo`, o verde do menu); cada cartão leva à 1ª tela PRONTA da torre (no COS, com a porta ligada, o
  Acompanhamento, e não a Mesa em construção), com "N de M prontas"; torre sem nenhuma (Comando, Contratos, Relatórios)
  vira um cartão que não é link, tracejado, com "Em construção". Prova: `tests/test_casca_inicio.py`.
- Edge "localhost recusou": o waitress tem de escutar em `127.0.0.1` **e** `[::1]`.
