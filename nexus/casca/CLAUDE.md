# CLAUDE.md — casca (moldura, login, menu e tema)

O que envolve todas as torres: o layout, o portão de login, a troca de cadeira, o tema (escuro ou claro) e o `/saude`.

## Os arquivos

| Arquivo | O que faz |
|---|---|
| `nexus/__init__.py` | `create_app`: lê o `.env`, instala o portão e o contexto, descobre as torres |
| `nexus/config.py` | `OBRIGATORIAS` (sem elas o app não sobe e diz qual falta) e `OPCIONAIS` |
| `nexus/casca/__init__.py` | `/` (Início), `/cadeira` (troca), `/tema` (troca sem JavaScript), `/saude` (`{"commit", "ok"}`) e o contexto dos templates (menu, `tema`) |
| `nexus/auth/__init__.py` | `/entrar`, `/sair` e o portão (`before_request`) |
| `nexus/auth/fracttal.py` | o login pelo Fracttal: o `api.fracttal_login` do clone do OS Creator; abre também o cookie `os_sessao` (/os) |
| `nexus/cadeiras.py` | as 10 cadeiras; diretoria e chefia caem na torre Comando |
| `nexus/templates/base.html` | a moldura: menu lateral, recolher (`[` ou botão, lembrado em `localStorage` `nexus.menu`), menu do celular, botão do tema (que troca também as molduras do OS Creator abertas) |
| `nexus/templates/_tema_cabeca.html` | o script do tema no `<head>` (base e entrar): a reserva do `localStorage` antes de pintar |
| `nexus/static/nexus.css` | os tokens do Design System Grid Co. nos dois temas e o subconjunto `gc-*` |
| `app.py` / `servir.py` | desenvolvimento (5070, IPv4 e IPv6, cookie sem Secure) / produção (atrás do proxy, cookie Secure) |

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

- **Rota pública é decisão consciente:** só o que está em `ROTAS_PUBLICAS` (entrar, saude, static). O teste
  `test_toda_rota_nao_publica_exige_login` pega rota nova esquecida.
- **Limite de senha:** 5 erros em 15 min por IP, guardado em `app.extensions` (estado global vazava entre testes).
- **Login pelo Fracttal** (Levi, 06/10/2026: "Ao invés de uma senha difícil, no início faça a pessoa logar com
  fractall"): e-mail e senha do Fracttal (a senha vai transformada ao Fracttal e não é guardada; só a conta da Grid Co.
  entra). Um login abre o Nexus e o OS Creator: o JWT vai no cookie `os_sessao` (path /os, 12 h), assinado com a
  chave do clone, e `/sair` apaga os dois. Sessão do Nexus: `logado`, `usuario` {email, nome, perfil} (o nome aparece
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
- **`next_seguro`:** o `?next=` só aceita caminho interno; nada de `//site` nem URL completa.
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
- Edge "localhost recusou": o waitress tem de escutar em `127.0.0.1` **e** `[::1]`.
