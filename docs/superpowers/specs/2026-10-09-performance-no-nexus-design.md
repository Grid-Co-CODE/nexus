# Performance no Nexus: uma porta, dois motores — desenho (09/10/2026)

Torre **Performance** inteira (e as telas da plataforma que moram em outras torres). O Nexus vira a porta, o menu e o
login; a Plataforma de Performance (repositório PerformancePainel) continua sendo o motor e desenha as próprias telas,
dentro do Nexus. O dado das duas passa a seguir o Kimball do Nexus.

## 1. Decisões do Levi (09/10/2026)

- "A minha ideia é matar uma parte da visão que temos da plataforma painel [...] basicamente a visão inicial agora
  viraria o nexus e separaria a performance nesses pontos [...] de tempo real até gêmeo digital"; "bem mais fácil que
  codar tudo ou trazer tudo para o repositório do Nexus"; "a ideia é que todo o ambiente kimball seja funcional e
  utilizado também no performance painel"; "futuramente interligar todas essas informações para fazermos análises
  rápidas e utilizarmos IAs".
- Abordagem escolhida entre três (ponte só leitura, uma porta com dois motores, reescrever no Nexus): **uma porta, dois
  motores**, porque permite "tanto os gestores olharem quanto o analista fazer tudo pelo nexus".
- Endereço: o Nexus está em `https://app.gridco.com.br/nexus`; "qnd tudo ficar pronto passar apenas para
  https://app.gridco.com.br" (fase 4).
- (1) "Deixa todos com visão de tudo por enquanto": todo login do Nexus entra como **analista** (faz tudo); as listas
  de perfil ficam prontas para quando ele quiser separar.
- (2) "Tem que ter as visões para tudo no nexus": **toda** tela da plataforma ganha lugar no Nexus (não só as 7 do
  menu de hoje), e a Operação em tempo real de código próprio também fica, como a visão "pelo banco" do Tempo real.
- (3) Diagnóstico = o diagnóstico da usina, aberto por um seletor de usina ("OK, cuida!").
- O que muda da decisão de 05/10 ("não gostaria que ficasse apontando para um link e sim tenhamos um código próprio"):
  as telas ficam no PerformancePainel; o que passa a ser do Nexus é a porta, o login e o dado (trilha K, seção 6).

## 2. O que existe hoje (medido em 09/10)

- **Nexus** em `app.gridco.com.br/nexus` (servidor da T.I., atrás do Caddy). `/nexus/saude` respondeu o commit
  `086da57`, 58 commits atrás da `main` do GitHub: o deploy pendente com a T.I. vem antes de tudo isto.
- **Plataforma** na raiz de `app.gridco.com.br`, deploy automático por push. Login por senha única (`DASH_PASSWORD`),
  sessão de 30 dias; o login Microsoft existe no código e está desligado.
- **Mesma origem**: os dois estão no mesmo endereço, atrás do mesmo Caddy. O Caddy responde sozinho (502 vazio, sem
  repassar) em `/auth` e `/monitoramento`; por isso rota nova da plataforma mora debaixo de um caminho que já passa
  (`/painel/...`) e é sondada antes de alguém depender dela.
- **Cookies**: nenhum dos dois define nome de cookie; os dois usam o padrão do Flask, `session`, no caminho `/`. Para o
  navegador é o mesmo cookie: entrar num apaga a sessão do outro (seção 5.1).
- **Links do Nexus debaixo de `/nexus`** (pelo código da versão do servidor, `086da57`, e sondado de fora em 09/10): o
  formulário de entrar e os estáticos saem com o prefixo (`/nexus/entrar`, `/nexus/static/...`), mas o menu
  (`/t/<torre>/<tela>`, montado em `nexus/torres/__init__.py`), o Início e a marca (`/`), o Sair (`/sair`) e os cartões
  do Início são escritos a partir da raiz: no servidor caem na plataforma (`/t/...` e `/sair` respondem 302 para o
  `/login` dela). Na raiz (seção 10, fase 4) esses links passam a valer sem mudar nada; por decisão do Levi (09/10:
  "não altere nenhum link agora"), nenhum link muda antes da conversa com a T.I.
- **Caminhos de cada um** (primeiro segmento, 09/10). Nexus: `/`, `/cadeira`, `/entrar`, `/os`, `/sair`, `/saude`,
  `/static`, `/t`, `/tema`. Plataforma: `/`, `/api`, `/auth`, `/cos`, `/gemeo`, `/gerencial`, `/healthz`,
  `/historico-plataforma`, `/login`, `/logout`, `/monitor`, `/monitoramento`, `/os`, `/painel`, `/relatorio`, `/ronda`,
  `/tempo-real`, `/teste`, `/tokens`, `/v2`, `/versao`, `/static`. Colidem só `/`, `/os` e `/static`; nos estáticos, os
  da plataforma são só `fonts/`, `logos/` e `notif.js`, e o Nexus não tem nenhum desses nomes.
- **Ponte de 04/10** (`/t/performance/plataforma/<caminho>`): só leitura (chave `X-Nexus-Leitura`, lista
  `leitura_nexus.permitido`), mostra o Tempo real; cada pedido segura uma thread do Nexus (até 150 s, 4 vagas).
- **Operação em tempo real** (código próprio, 05 a 07/10): pronta e sem push (Nexus, branch `operacao-tempo-real`;
  plataforma, branch `operacao-tempo-real` no worktree `plat-otr`). A plataforma publica o livro `operacao_tempo_real`
  a cada 30 min e o Nexus desenha a tela lendo o banco. A branch do Nexus já retira a ponte.
- **Torre Performance do Nexus**: Tempo real (pela ponte), Clima e risco e Mapa de risco (do Nexus), e Painel NOC,
  Diagnóstico, Strings e trackers, Visão gerencial, Criador de relatório e Gêmeo digital em placeholder.

## 3. Escopo

**Dentro:** o passo 0 dos cookies; o passe, os perfis e o modo Nexus na plataforma; a moldura do Nexus para todas as
telas da plataforma (mapa da seção 5.6); o Tempo real com duas visões; a página inicial da plataforma levando ao Nexus
(fase 3); a retirada da ponte; a trilha K (Kimball na plataforma); o desenho da fase 4 (o Nexus na raiz).

**Fora:** reescrever telas da plataforma; tema claro nas telas da plataforma; permissão por tela além dos dois perfis;
registrar o autor de cada ação da plataforma (fica possível, não entra agora); a IA (vai ler o banco que a trilha K
monta); mudar o motor de lugar (a plataforma continua coletando).

## 4. Arquitetura

```
navegador
  app.gridco.com.br/nexus/t/performance/<tela>   página do Nexus: casca (menu, login) + moldura (iframe)
        │ 1. formulário escondido, POST, alvo = a moldura
        ▼
  app.gridco.com.br/painel/nexus/entrar          a plataforma confere o passe e abre a sessão DELA
        │ 2. 303 para a tela
        ▼
  app.gridco.com.br/<rota da tela>               a tela da plataforma em modo Nexus, leitura e gravação
                                                 (os dados vêm do /api/... dela, como hoje)
```

- O navegador fala com cada sistema direto. Nada da plataforma passa por dentro do processo do Nexus (a ponte passava).
- A plataforma continua o **motor**: coleta, caches, réguas e gravações. O Nexus é a **porta** (menu, login, endereço)
  e, pela trilha K, o dono das **dimensões** (usina, data, equipamento) que os dois usam.

## 5. Componentes

### 5.1 Passo 0: cada sistema com o seu cookie

- Problema: mesmo nome (`session`), mesmo caminho (`/`), mesmo endereço. O navegador guarda um só; o login do Nexus
  apaga o da plataforma e vice-versa. Com a moldura (os dois abertos ao mesmo tempo) a pessoa cairia no login a cada
  clique.
- Correção: o Nexus passa a usar `nexus_sessao` (`SESSION_COOKIE_NAME`), no caminho do prefixo em que roda. A
  plataforma fica com o dela. Efeito único: quem está no Nexus entra de novo uma vez.
- O `os_sessao` do OS Creator embutido tem caminho `/os`: debaixo de `/nexus` ele não casa com `/nexus/os/...` e casa
  com o `/os/` da **plataforma** (o proxy do OS Creator Web dela). Conferir no servidor e levar o caminho para o prefixo.
- O `servir.py` do repositório não trata prefixo, mas os redirecionamentos de `/nexus/` já saem com ele: descobrir como
  o servidor põe o `/nexus` e fixar isso no repositório (`NEXUS_PREFIXO`), para cookie e link saírem do mesmo lugar.

### 5.2 O passe do Nexus para a plataforma (login único)

- A página da tela no Nexus tem um formulário escondido que faz POST para `/painel/nexus/entrar`, com alvo na moldura.
  Sem JavaScript, um botão "Abrir".
- O passe é `base64url(json) + "." + base64url(HMAC-SHA256(json))` com a chave `NEXUS_SSO_CHAVE` (32 bytes ou mais,
  aleatória; no `.env` do Nexus e no `.env`/`tokens.txt` da plataforma; nunca no git: os dois repositórios são
  públicos). Leva o e-mail, o nome, se a pessoa é admin do Nexus (`NEXUS_ADMINS`), o destino, o vencimento (60 s) e um
  número único.
- A plataforma confere a assinatura (`compare_digest`), o vencimento, que o número não foi usado (guarda os dos últimos
  2 min) e que o destino está no mapa (seção 5.6; nada de redirecionamento aberto). Abre a sessão dela com `auth`,
  `auth_kind = "nexus"`, `user` (o e-mail), `perfil` e `admin_nexus`, valendo **12 h** (como a do Nexus), e não os 30
  dias da senha.
- POST, nunca na URL: o passe leva o e-mail e não pode ficar em log de proxy nem no histórico do navegador.
- O "Sair" do Nexus passa por `/painel/nexus/sair` antes de terminar: sai das duas.
- Sem `NEXUS_SSO_CHAVE` nos dois lados, `/painel/nexus/*` responde 404 e nada muda (desligado por padrão).
- A senha da plataforma continua valendo (reserva e acesso direto) até a fase 3.

### 5.3 Perfis

- **analista**: faz tudo o que a sessão por senha faz hoje.
- **gestor**: só leitura, pela mesma lista que a ponte já usa (`leitura_nexus.permitido`), ampliada para as rotas de
  todas as telas do mapa: sem gravação, sem os parâmetros que disparam coleta (`force`, `forcar`, `run`, `backfill`),
  sem abrir a API PV na hora.
- Quem é quem: `PLATAFORMA_ANALISTAS` e `PLATAFORMA_GESTORES` no `.env` da plataforma (e-mails separados por vírgula,
  ou `*`). Pela decisão (1), começa com `PLATAFORMA_ANALISTAS=*`.
- Registrado: o Nexus aceita qualquer conta do Fracttal da Grid Co., técnico inclusive. Com `*`, todos gravam na
  plataforma, inclusive criar OS de tracker no Fracttal. Restringir depois é uma linha no `.env`, sem código.
- Fora das duas listas: a página "sem acesso à Performance", dentro da moldura.
- `/tokens` (grava as chaves das fontes SunOp, Axis e Plataforma) é administração: só `admin_nexus`, em qualquer perfil.

### 5.4 Modo Nexus na plataforma

- Página aberta dentro da moldura com sessão do passe (`auth_kind = "nexus"` e `Sec-Fetch-Dest: iframe`) sai com a
  classe `modo-nexus` no `<html>`, posta pelo servidor (sem piscar). O CSS esconde só o que é navegação da plataforma
  (a marca "Plataforma de Performance", os links "‹ Entrada", o sair), que cada template marca com `data-casca`. O
  resto da tela não muda. Navegador que não manda o `Sec-Fetch-Dest` mostra a tela com a navegação da plataforma:
  funciona igual, só com dois menus.
- Em modo Nexus, cada página avisa a moldura do caminho em que está (`postMessage`, `{tipo: "nexus:rota", caminho}`).
- `Content-Security-Policy: frame-ancestors 'self'` em toda resposta HTML: só o próprio endereço emoldura a plataforma
  (hoje ela não manda trava nenhuma).
- `/` dentro da moldura leva a `/tempo-real` (quem faz o papel da Entrada é o menu do Nexus).

### 5.5 A moldura no Nexus

- Uma view por tela, no template `performance/moldura.html`, com a moldura ocupando a área da tela (o padrão
  `.conteudo--moldura` do OS Creator embutido).
- O endereço acompanha: ao receber `nexus:rota`, o Nexus troca a URL (`history.replaceState`, `?p=<caminho>`) e acende
  o item do menu pela tabela de prefixos do mapa. Abrir com `?p=` (favorito, F5) abre a moldura no mesmo lugar, se o
  caminho estiver no mapa; fora dele, a tela padrão do item.
- Configuração: `NEXUS_PLATAFORMA_URL` (já existe, hoje exigindo https ou localhost por causa da chave da ponte; no
  servidor passa a aceitar vazia = a própria origem; no PC, a cópia da plataforma em outra porta) e `NEXUS_SSO_CHAVE`.

### 5.6 Mapa das telas (todas as visões)

| Nexus (torre · tela) | Plataforma | Observação |
|---|---|---|
| Performance · Tempo real | `/tempo-real` | os cards por fonte; a fonte embute `/monitor?fonte=…&embed=1`. Duas visões (5.7) |
| Performance · Painel NOC | `/painel` | |
| Performance · Diagnóstico | `/painel/usina/<id>` | seletor de usina no Nexus: a lista da plataforma até a K1, depois pelo `usina_id` |
| Performance · Strings e trackers | `/painel/falhas` | |
| Performance · Visão gerencial | `/gerencial` | |
| Performance · Disponibilidade (nova) | `/gerencial/disponibilidade` | hoje só se chega pelo Gerencial |
| Performance · Criador de relatório | `/relatorio` | |
| Performance · Relatório semanal (nova) | `/relatorio/semanal` | hoje só se chega pelo Relatório |
| Performance · Gêmeo digital | `/gemeo/` | também `/gemeo/usina/<id>`, que o Painel NOC abre |
| Performance · Histórico da plataforma (nova) | `/historico-plataforma` | |
| Performance · Monitor da ronda (nova) | `/ronda/monitor` | |
| COS · Acompanhamento COS (nova) | `/cos` | torre COS: entra pela regra de entrega dela (pull request) |
| Base · Chaves das fontes (nova) | `/tokens` | só admin (5.3) |

- Ficam como estão: Clima e risco e Mapa de risco (do Nexus); Criar OS é o OS Creator do Nexus (o `/os/` da plataforma
  sai na fase 4).
- **Fonte única:** a mesma tabela dá o destino permitido do passe (5.2), o `?p=` e o item que acende (5.5). Ela mora no
  Nexus e tem cópia na plataforma, com teste dos dois lados (como as listas da ponte); outro teste quebra se uma rota
  HTML da plataforma ficar sem lugar no mapa.

### 5.7 Tempo real: duas visões

- **Ao vivo** (o padrão): a moldura da plataforma, com tudo (drill, curvas, trava, comentário).
- **Pelo banco**: a tela da Operação em tempo real (código próprio de 05 a 07/10), lendo `operacao_tempo_real`. Abre
  mesmo com a plataforma fora do ar e é a mesma leitura que a IA vai fazer.
- Alternância no topo da tela, escolhida na URL (`?ver=banco`), como a Matriz | Organograma da Governança.
- A branch da Operação em tempo real entra **depois** que a visão Ao vivo estiver no servidor: o Tempo real nunca fica
  sem a leitura ao vivo.

## 6. Trilha K: o Kimball na plataforma

1. **K1. O `plant_id` no de-para.** Sistemas novos no `cadastro_nexus · de_para` para os `plant_id` de cada fonte da
   plataforma (API PV, SunOp, Athon e Axis, scadaGridco, 2C), propostos pela tela Base → Ligações a partir da lista que
   a plataforma publica e confirmados lá; usina sem ligação aparece. É a pendência 10 de `nexus/dados/CLAUDE.md`.
2. **K2. A plataforma lê as dimensões.** Módulo `dimensoes_nexus.py` na plataforma: lê `cadastro_nexus · usinas` e
   `de_para` (só leitura, cache de 10 min; sem banco, o comportamento de hoje, com aviso) e troca a junção por nome pela
   junção por `usina_id`, começando pelas que já quebraram (no Histórico PR do Painel NOC, 38 de 116 usinas sumiam pelo
   nome, 28/09). Cada troca roda a junção nova e a antiga e compara valor a valor antes de valer.
3. **K3. Os fatos da plataforma no banco com os IDs.** (a) `operacao_tempo_real` (pronto); (b) `falhas_performance`
   (episódios de string e de tracker, tracker × dia, cobertura, OS de string) ganha `usina_id`, `data_id` e, onde houver,
   `equipamento_id`, como colunas novas no FIM (o BI e o Nexus leem por posição); (c) o gêmeo. Cada fato entra antes no
   catálogo (`nexus/dados/catalogo.py`); o estado passa de `origem` a `conformado` quando a plataforma gravar com os IDs.
4. **K4. A qualidade medida.** A carga do Nexus mede a ligação desses fatos (`nexus_fatos · qualidade`) e a Governança
   de dados mostra, como já faz com o Campo.

- Coordenação: há trabalho em andamento de outra frente no mesmo livro (`falhas_performance` com `plant_id`, da
  Operação no Mês do Dashboard Thopen). A K3(b) começa depois que ele entrar.
- Resultado: um banco só, em que fechamento, ronda, PT, programação, falha, geração e tempo real se cruzam por
  `usina_id` e `data_id`. É a base da análise rápida e da IA.

## 7. Erros

- Passe vencido, adulterado ou repetido: página da plataforma "Abra de novo pelo Nexus", com o motivo; 403; nenhuma
  sessão aberta.
- Sem a chave: 404 (desligado).
- Plataforma fora do ar: a moldura mostra o erro; o Nexus em volta segue (menu, outras torres) e o Tempo real "Pelo
  banco" continua.
- Fora das listas: "sem acesso à Performance", dizendo a quem pedir.
- `?p=` fora do mapa: abre a tela padrão do item, sem seguir o caminho.

## 8. Segurança

- **Mesma origem já é a situação de hoje** (Nexus em `/nexus`, plataforma na raiz): um script injetado num alcança o
  outro. Mitigações: cookies `HttpOnly` com nomes próprios; escape de todo texto de terceiro (`_he` na plataforma, o
  Jinja no Nexus); `frame-ancestors 'self'`; passe de uso único e 60 s. A ponte sai, e com ela o HTML da plataforma
  rodando servido pelo processo do Nexus.
- Gravação por todos (decisão 1), mas com a pessoa conhecida: a sessão do passe guarda o e-mail.
- A chave do passe só abre sessão na plataforma; não entra no Nexus. Trocar a chave derruba as sessões abertas pelo
  passe, não a senha.
- Chave, listas de e-mail e endereços internos só no `.env`.

## 9. Como provar

- **Plataforma (pytest):** passe válido, vencido, adulterado e repetido; destino fora do mapa; analista grava; gestor
  recebe 403 ao gravar e passa nas leituras de cada tela do mapa (teste que varre as rotas de cada página, como o
  `test_a_lista_cobre_as_rotas_das_paginas` da ponte); `/tokens` só admin; sem chave, 404; `frame-ancestors` em todo
  HTML; modo Nexus só com sessão do passe dentro da moldura; `/` na moldura leva a `/tempo-real`.
- **Nexus (pytest):** cada tela do mapa abre a moldura com o formulário certo; o passe assina com a chave, vence em 60 s
  e muda a cada abertura; sem login, vai ao entrar; sem configuração, avisa; cookie `nexus_sessao` no caminho do
  prefixo; o mapa cobre toda rota HTML da plataforma.
- **No navegador (Chrome sem janela, no PC):** Nexus 5070 e uma cópia da plataforma em outra porta (a 5050 do PC é a
  ponte do OS Creator e não reinicia); as duas sessões vivas ao mesmo tempo (o passo 0); as 13 telas com o mesmo número
  da plataforma direta no mesmo minuto; uma gravação de analista numa cópia de estado; o gestor barrado; 1440 e 375 px;
  tempo de abertura de cada tela pelo Nexus e direto.
- **No servidor (fase 2):** sondar `/painel/nexus/entrar` (tem de responder `Server: waitress` com `Via: Caddy`, e não
  502 vazio); as duas sessões juntas; uma tela de cada torre.

## 10. Fases (nada afeta o que funciona hoje)

0. **Cookies distintos** no Nexus (5.1), no próximo deploy com a T.I.
1. **Passe, perfis, modo Nexus e `frame-ancestors`** na plataforma (desligados sem a chave) e **moldura e mapa** no
   Nexus; provado no PC. Sobe primeiro a plataforma (deploy automático, inerte sem a chave), depois o Nexus.
2. **Servidor em paralelo:** a T.I. põe `NEXUS_SSO_CHAVE` nos dois e `PLATAFORMA_ANALISTAS=*`. Os analistas usam pelo
   Nexus; a Entrada da plataforma segue no ar. A Operação em tempo real entra aqui (5.7) e a ponte sai.
3. **Com o ok do Levi:** o `/` da plataforma leva a `/nexus/`; a senha da plataforma vira reserva de admin; sai o
   `X-Nexus-Leitura` da plataforma (a lista de leitura fica, para o gestor).
4. **O Nexus na raiz** (`app.gridco.com.br`), **dividindo por caminho no Caddy**, sem mudar a plataforma de lugar
   (revisto em 09/10, depois de medir os caminhos dos dois; a plataforma num sub-caminho exigiria fechar as lacunas do
   modo sub-caminho dela e mexer nas integrações de fora):
   - para o Nexus: `/` (só a raiz exata), `/t/*`, `/entrar`, `/sair`, `/saude`, `/tema`, `/cadeira`, `/os/*` e
     `/static/*`, menos os estáticos da plataforma;
   - para a plataforma, como hoje: todo o resto, inclusive `/static/fonts/*`, `/static/logos/*` e `/static/notif.js`
     (estático novo na plataforma passa a pedir uma linha no Caddy) e as integrações de fora (`/api/*`, `/versao`,
     `/healthz`);
   - `/db_performace` não muda;
   - o `/os/` passa a ser só o OS Creator do Nexus (o proxy da plataforma para o OS Creator Web sai);
   - antes de virar: o cookie próprio do Nexus (5.1, sem ele os dois logins se apagam) e o menu do Nexus levando às
     telas da plataforma (a moldura deste desenho ou, provisoriamente, o link direto), senão os analistas perdem a
     Entrada da plataforma, que deixa de responder no `/`.
   Se a T.I. trocar a raiz antes das fases 1 e 2, a ordem vira: fase 0, menu com os links diretos, troca da raiz,
   depois moldura e passe.

A trilha K anda em paralelo a partir da fase 1: K1, K2, K3, K4.

## 11. Riscos e pendências

- O servidor do Nexus está 58 commits atrás (`086da57`): o deploy pendente com a T.I. vem antes da fase 0.
- O Caddy responde sozinho em alguns caminhos (`/auth`, `/monitoramento`): toda rota nova da plataforma é sondada antes.
- Gêmeo no servidor: em 22/09 o `/gemeo/` dava 503 (o serviço do gêmeo não estava de pé lá). Conferir antes de abrir
  o item.
- O tema claro do Nexus não chega às telas da plataforma, que só têm o escuro.
- Telas da plataforma que não foram feitas para celular continuam assim dentro da moldura.
- Com `PLATAFORMA_ANALISTAS=*`, todo login do Nexus grava na plataforma (decisão 1).

## 12. Planos

Grande demais para um plano só. Quatro, nesta ordem, cada um com spec → plano → execução e a prova dele:

1. **Porta única:** fases 0, 1 e 2 (cookies, passe, perfis, modo Nexus, moldura e mapa das 13 telas, Tempo real com as
   duas visões, saída da ponte). Os dois repositórios.
2. **K1 e K2:** o `plant_id` no de-para e a plataforma lendo as dimensões, com a comparação valor a valor.
3. **K3 e K4:** os fatos da plataforma com os IDs no catálogo e no banco, e a qualidade na Governança.
4. **Troca da porta e raiz:** fases 3 e 4 (depende do ok do Levi e da mudança do Caddy pela T.I.; o Levi leva o
   assunto à T.I. em 09/10, e pode vir antes dos planos 1 a 3, na ordem alternativa da fase 4).
