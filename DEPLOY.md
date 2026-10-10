# Nexus no servidor: passo a passo para a T.I.

O Nexus é um app Flask (Python), servido pelo waitress, atrás de um proxy com HTTPS. Um processo só: não tem banco
próprio nem fila. O estado fica em arquivos na pasta `dados/` do projeto; o dado compartilhado vai para a API
db_performace (PostgreSQL da Grid Co.).

**O código vem do GitHub** (`github.com/Grid-Co-CODE/nexus`, público: o clone não precisa de chave). **O que não está
no GitHub** vem num pacote à parte que o Levi envia por canal privado, o `nexus-acessos-AAAA-MM-DD.zip`:

| Caminho no pacote | O que é |
|---|---|
| `.env` | os segredos do Nexus: chave da sessão, senha de entrada, chave da cifra do cadastro, token de escrita na API db_performace, o token do repositório do PCM para Publicar no App (`NEXUS_PCM_GITHUB_TOKEN`, desde 09/10/2026). Também leva o endereço e a chave só de leitura da plataforma de Performance (`NEXUS_PLATAFORMA_URL`, `NEXUS_PLATAFORMA_TOKEN`), a chave do passe da porta única (`NEXUS_SSO_CHAVE`, desde 09/10/2026, a MESMA da plataforma; seção 7e) e a chave do código da pessoa do App de Campo (`NEXUS_PESSOA_HMAC`) |
| `nexus/torres/oscreator/os_creator/.env` | a credencial do Fracttal (OS Creator, motor do PCM e a fila da Aprovação de OS usam a mesma) |
| `dados/cadastro_ensaio.json` | o cadastro do BD_Operações (o sensível vai cifrado; a chave está no `.env`) |
| `dados/de_para_regras.json` e `dados/de_para_atual.json` | as decisões e o estado da tela Base → Ligações (o de-para entre as bases) |
| `dados/pcm/insumos.json` | os insumos da programação semanal do PCM (prioridades, confiabilidade, feriados e o histórico, já com a S41 publicada) |
| `dados/pcm/_ativos_classificacao_cache.json` | a lista de usinas do Fracttal (a tela de observações do PCM usa) |
| `dados/campo/identidades.json` | o cadastro do App de Campo (nome, e-mail e supervisor de cada técnico): **dado pessoal** |

Os dois `.env` e a `dados/` nunca vão para o git (o `.gitignore` já barra), nem para pasta compartilhada, e-mail aberto
ou grupo de conversa.

## 0. O que o servidor precisa

- Linux com **Python 3.14**, `git` e `unzip`. Proxy com HTTPS na frente (exemplo abaixo com o Caddy).
- Saída para a internet: `github.com` (código), `app.gridco.com.br` (API db_performace e plataforma de Performance),
  `app.fracttal.com` e `one.fracttal.com` (Fracttal), `raw.githubusercontent.com` (banco do PCM), `api.github.com`
  (Publicar no App: grava a semana no repositório do PCM),
  `apiprevmet3.inmet.gov.br` (avisos meteorológicos do INMET), `dataserver-coids.inpe.br` (focos de queimada e risco
  de fogo do INPE), `power.larc.nasa.gov` (irradiação diária da NASA POWER) e `firms.modaps.eosdis.nasa.gov` (fogo das
  últimas 24 h dos satélites da NASA, desde 10/10/2026): os quatro últimos são da tela Performance → Clima e risco, só HTTPS
  (443), leitura pública, sem chave. A NASA só é chamada pela PÁGINA de uma usina (um pedido por
  usina, guardado por 12 h), nunca pela tela principal. Sem eles a tela abre e mostra as fontes como "fora agora". O mapa de
  calor do risco de fogo (Mapa de risco, 09/10/2026) usa o mesmo `dataserver-coids.inpe.br`: nenhuma saída nova.
- Disco: cada geração da programação semanal guarda ~65 MB em `dados/pcm/geracoes/` (uma por semana).
- Fuso `America/Sao_Paulo` (o `deploy/nexus.service` já define).

## 1. Clone, acessos e dependências

Em `/opt/nexus` (ou onde preferir; ajuste o caminho no `deploy/nexus.service`):

```
sudo useradd --system --home /opt/nexus nexus
sudo git clone https://github.com/Grid-Co-CODE/nexus.git /opt/nexus
sudo unzip nexus-acessos-*.zip -d /opt/nexus          # os .env e a dados/ entram no lugar
cd /opt/nexus
sudo python3.14 -m venv .venv
sudo .venv/bin/pip install -r requirements.txt
```

O ponto de entrada de produção é o `servir.py`. Não use o `app.py`: ele é só para desenvolvimento (desliga o cookie
seguro).

O OS Creator embutido importa o PyQt6 (tela de Engenharia). Num servidor sem tela, se o `/os/` acusar falta de
biblioteca gráfica, instale: `sudo apt install libgl1 libegl1 libxkbcommon0 libfontconfig1`. Sem elas, só o `/os/*`
fica fora; o resto do Nexus funciona.

## 2. Conferir antes de subir

```
.venv/bin/python -m pytest -q          # todos devem passar
```

## 3. Permissões

```
sudo chown -R nexus:nexus /opt/nexus
sudo chmod 600 /opt/nexus/.env /opt/nexus/nexus/torres/oscreator/os_creator/.env
sudo chmod -R go-rwx /opt/nexus/dados
```

## 4. Serviço

```
sudo cp /opt/nexus/deploy/nexus.service /etc/systemd/system/nexus.service
sudo systemctl daemon-reload
sudo systemctl enable --now nexus
curl -s http://127.0.0.1:5070/saude      # {"commit": "...", "ok": true}
journalctl -u nexus -f                  # log
```

O Nexus escuta só em `127.0.0.1:5070`. Quem fala com a internet é o proxy. Porta e endereço mudam com as variáveis
`NEXUS_PORTA` e `NEXUS_HOST` no `nexus.service`. O `WorkingDirectory` tem de ser a raiz do clone: o `.env` aponta
para `dados/campo/identidades.json` por caminho relativo.

## 5. Endereço com HTTPS

O Nexus está em **`https://app.gridco.com.br/nexus`**, ao lado da plataforma de Performance (na raiz do mesmo endereço).
O cookie de sessão sai com `Secure`: o Nexus **precisa** de HTTPS na frente. O proxy tem de repassar `X-Forwarded-For`
(o Caddy repassa por padrão): é por ele que o limite de tentativas de senha conta cada pessoa, e não o servidor inteiro
como uma só.

### 5a. O prefixo `/nexus` no próprio Nexus (`NEXUS_PREFIXO`, desde 09/10/2026)

Até 09/10/2026 o Nexus não sabia que mora em `/nexus`: menu, Início, Sair e `fetch` saíam da raiz e caíam na plataforma,
e quem consertava era uma reescrita das respostas no servidor (fora do repositório). Agora o Nexus põe o prefixo sozinho
em todo link, redirecionamento e cookie, e o cookie de sessão tem nome próprio (`nexus_sessao`; o da plataforma é
`session`), então entrar num não derruba mais o outro.

**O que a T.I. faz, nesta ordem** (sem a variável, o código novo se comporta como sempre). **Ponha a variável no MESMO
reinício em que o código novo sobe**: quem entrasse entre um e outro ganharia o cookie em `Path=/` e, depois da
variável, um segundo em `Path=/nexus`. Desde 10/10/2026 o Sair e o Entrar apagam também o de `Path=/` (revisão: antes
a pessoa saía e seguia logada pelo velho, por até 12 h), mas não há por que abrir essa janela.

1. No `.env` do Nexus (ou como `Environment=NEXUS_PREFIXO=/nexus` no `nexus.service`), acrescente:
   ```
   NEXUS_PREFIXO=/nexus
   ```
   e reinicie: `sudo systemctl restart nexus`. O log diz `servido em /nexus`.
2. Confira de fora:
   ```
   curl -sI https://app.gridco.com.br/nexus/ | grep -i '^location'
   ```
   tem de responder `location: /nexus/entrar?next=/nexus/`, **nunca** `/nexus/nexus/...`. Entre no Nexus: o cookie
   `nexus_sessao` aparece com `Path=/nexus`; o menu, o Sair e o OS Creator abrem dentro de `/nexus/...`.
3. Se dobrar (`/nexus/nexus`): tire a linha e reinicie; volta ao de antes. Avise o Levi.
4. Com o passo 2 certo, a reescrita das respostas do Nexus no servidor (a camada que põe `/nexus` no `Location`, no HTML e
   no JavaScript, e o calço do `fetch` no `<head>`) fica sem trabalho: pode ser tirada. Sem ela o Nexus segue igual;
   com ela também (o Nexus não dobra o que ela reescreve).

Todo mundo entra de novo **uma vez** depois do passo 1 (o cookie mudou de nome e de caminho). Debaixo do prefixo, o
Sair e o Entrar apagam também o `nexus_sessao` de `Path=/` que tenha sobrado (`auth._sem_a_sessao_velha_da_raiz`).

O Caddy pode cortar o `/nexus` antes de repassar (`handle_path`, como hoje) ou não (`handle`): o Nexus aceita os dois.
O que ele **não** usa é cabeçalho de prefixo (`X-Forwarded-Prefix`): o prefixo vem só da variável. Exemplo do bloco:

```
app.gridco.com.br {
    redir /nexus /nexus/ 308
    handle_path /nexus/* {
        reverse_proxy 127.0.0.1:5070
    }
    # ... o resto continua indo para a plataforma de Performance
}
```

**Na raiz** (a fase 4 do spec da porta única: o Nexus em `app.gridco.com.br`, dividindo os caminhos com a plataforma), é
só tirar a `NEXUS_PREFIXO` e mudar o Caddy (seção 5b). Num subdomínio próprio (`nexus.gridco.com.br`,
`reverse_proxy 127.0.0.1:5070`), também sem ela.

### 5b. Fase 4: o Nexus na raiz de `app.gridco.com.br` (quando o Levi e a T.I. decidirem)

Levi, 09/10/2026: "qnd tudo ficar pronto passar apenas para https://app.gridco.com.br". O Nexus passa a responder na
raiz e a plataforma de Performance fica onde está: o Caddy divide **por caminho** (os caminhos dos dois foram medidos em
09/10 e só colidem em `/`, `/os` e `/static`). Nenhuma linha de código muda; provado no PC em 10/10/2026 com um proxy que
faz esta mesma divisão (as 13 telas da porta única, as duas sessões juntas, o Sair, os passes).

- Para o **Nexus**: `/` (só a raiz exata), `/t/*`, `/entrar`, `/sair`, `/saude`, `/tema`, `/cadeira`, `/os` e `/os/*`, e
  `/static/*` **menos** os três estáticos da plataforma (`/static/fonts/*`, `/static/logos/*`, `/static/notif.js`; estático
  novo na plataforma pede uma linha aqui).
- Para a **plataforma**, como hoje: todo o resto, inclusive `/api/*`, `/versao`, `/healthz` e `/painel/nexus/*`. O
  `/os/` dela (o proxy do OS Creator Web) deixa de ser alcançado: o `/os/` passa a ser o OS Creator do Nexus.
- O `/nexus/...` antigo (favoritos, e-mails, o App de Campo) vai para o mesmo caminho na raiz (308, que mantém o POST).

Trecho do Caddyfile (troca o bloco do `/nexus` e o que manda o resto à plataforma; os outros blocos que existem hoje, como
o do `/db_performace` e os caminhos que o Caddy responde sozinho, ficam como estão; `<plataforma>` é o mesmo destino que
a plataforma usa hoje):

```
app.gridco.com.br {
    # o endereço antigo do Nexus leva ao mesmo lugar na raiz
    redir /nexus / 308
    @nexus_antigo path_regexp antigo ^/nexus(/.*)$
    redir @nexus_antigo {re.antigo.1}{?query} 308

    @nexus {
        path / /entrar /sair /saude /tema /cadeira /os /t/* /os/* /static/*
        not path /static/fonts/* /static/logos/* /static/notif.js
    }
    handle @nexus {
        reverse_proxy 127.0.0.1:5070
    }

    handle {
        reverse_proxy <plataforma>
    }
}
```

Não foi validado com o próprio Caddy (o PC de desenvolvimento não tem): rode `caddy validate` antes do `caddy reload` e
guarde o Caddyfile de antes, que é a volta.

**Ordem:** (1) no `.env` do Nexus, **sem** `NEXUS_PREFIXO` (tire a linha, se houver) e reinicie; (2) troque o Caddy (a
reescrita das respostas do Nexus, que existia para o `/nexus`, sai junto); (3) na plataforma, a fase 3 é
`NEXUS_PORTA_PRINCIPAL=https://app.gridco.com.br/` (endereço completo: `/` sozinho levaria o `/` ao próprio `/`, em laço,
para quem chegasse direto à porta da plataforma). Todo mundo entra de novo uma vez no Nexus (o cookie passa a `Path=/`).

**O que não pode cair: o `/db_performace`** (o App de Campo, o coletor e a carga do Nexus gravam nele). O bloco dele
fica como está e tem de continuar sendo avaliado antes do `handle` sem filtro: se hoje ele usa `handle_path` ou outra
forma, mantenha a estrutura que já funciona e confira pelo `curl` abaixo (Levi, 10/10/2026: "o que está pode cair",
menos o banco). Conferido em 10/10/2026: as 122 rotas do Nexus caem todas no `@nexus`, e a plataforma perde só o `/`
e o `/os/`. A `NEXUS_PORTA_PRINCIPAL` entra **depois** do Caddy: antes dele, o `/` da plataforma levaria a ela mesma.

**Conferir:**
```
curl -s  https://app.gridco.com.br/db_performace/health                   # {"status":"ok",...}  (PRIMEIRO)
curl -sI https://app.gridco.com.br/ | grep -i '^location'                # /entrar?next=/  (o Nexus)
curl -s  https://app.gridco.com.br/saude                                  # {"ok": true, "commit": ...}
curl -sI https://app.gridco.com.br/nexus/t/cos/mesa | grep -i '^location' # /t/cos/mesa (308)
curl -s -o /dev/null -w '%{http_code}\n' https://app.gridco.com.br/static/notif.js   # 200 (da plataforma)
curl -s -o /dev/null -w '%{http_code}\n' https://app.gridco.com.br/static/nexus.css  # 200 (do Nexus)
curl -s https://app.gridco.com.br/versao                                  # a plataforma, como antes
```
E no navegador: entrar no Nexus, abrir as telas da Performance (moldura), o OS Creator e o Sair.

**Voltar:** o Caddyfile de antes, `NEXUS_PREFIXO=/nexus` no `.env` do Nexus e reiniciar (seção 5a); na plataforma, a
`NEXUS_PORTA_PRINCIPAL` volta a `/nexus/` (ou sai).

## 6. Conferir depois de subir

1. `https://app.gridco.com.br/nexus/saude` responde `{"ok": true, "commit": "..."}` com o commit do GitHub.
2. Entrar com o login do Fracttal (e-mail e senha de quem vai usar; desde 06/10/2026). A senha de admin (a
   `NEXUS_SENHA_ADMIN` do `.env`; o Levi tem) segue em "Entrar com a senha de administrador" e é ela que abre o
   Cadastro, além dos e-mails em `NEXUS_ADMINS` (opcional, separados por vírgula).
3. **Base → Registro mestre** abre a lista de usinas: a chave da cifra está certa.
4. **PCM → Gerar a semana**: a lista de conferência diz "pronto" (motor, credencial do Fracttal, cadastro e insumos).
   A "Pasta do PCM" e as durações aprendidas aparecem como opcionais ausentes: é o esperado no servidor.
5. **OS Creator → Início** abre a entrada do OS Creator: cada pessoa entra com o próprio usuário do Fracttal, e
   depois disso **Ativos Fracttal** lista os ativos.
6. **Campo · App → Triagem de qualidade** mostra as OS do período com a nota do painel do App (a fonte é o livro que o
   App grava no banco; precisa da `NEXUS_PESSOA_HMAC` no `.env`, ver o passo 7). A tela Ordens de serviço saiu em
   08/10/2026.
7. **Performance → Clima e risco** abre com as três fontes em verde (INMET, focos e risco de fogo do INPE). A primeira
   visita leva uns 10 s (lê o risco de fogo de todas as usinas); depois a tela é imediata. Fonte "fora agora": confira a
   saída para os dois endereços da seção 0 (ver a seção 7c).
8. **OS Creator → Solicitação → Engenharia** mostra a escolha "Uma OS por ativo" × "Uma OS com todos os ativos" e o
   campo de anexos (desde 08/10/2026), e o menu de Responsável traz os nomes da linha `OS_WEB_ENGENHARIA_RESPONSAVEIS`
   do `.env` do OS Creator (06/10/2026; o Levi manda a linha, os nomes não vão ao GitHub). Menu vazio = falta a linha.
   O envio com anexos aceita até 21 MB: o Nexus aceita 25 MB por pedido e o Caddy não limita; outro proxy na frente
   precisa de pelo menos 25 MB de corpo.

## 7. Campo · App: o Nexus lê o que o App grava

As telas Aprovação de OS e Triagem leem o registro de cada fechamento **que o próprio App de Campo
grava no banco** (API db_performace, livros `fechamentos_app_campo` e `rondas_app_campo`, de hora em hora). O técnico
vem como código (HMAC do e-mail): o `.env` do pacote já traz a `NEXUS_PESSOA_HMAC`, a MESMA chave da configuração do
App. Sem ela, as telas seguiriam com o livro antigo do coletor (dados parados).

**Ordem com o App (08/10/2026):** o livro de rondas do App ainda traz o nome do técnico; o pacote do App que passa a
gravar só o código (`Técnico (HMAC)`) só pode ser publicado **depois** que o servidor do Nexus estiver no commit
`371eb44` ou mais novo, que lê as duas colunas. Na ordem inversa, as telas de Rondas do servidor ficam sem o nome do
técnico até a atualização.

**O coletor do Fracttal está aposentado:** não ponha `NEXUS_CAMPO_COLETOR=1` no servidor (o pacote não tem). Ele lia o
Fracttal com a cota da empresa inteira para recalcular uma nota que o App já grava.

A tela **Aprovação de OS** lê a fila do Fracttal ao vivo quando alguém a abre: ~55 pedidos de uma vez, no máximo a
cada 10 minutos por servidor (os filtros reusam a mesma leitura). Em hora de pico da cota ela mostra o aviso de fila
incompleta; a tela continua de pé.

## 7d. PCM: publicar a semana no App (09/10/2026)

Desde a W43 o Nexus gera E publica a programação semanal (Levi: "semana que vem já quero full nexus"). **PCM → Gerar a
semana → a rodada → Publicar no App** manda a `Programação Semana NN.xlsx` e as observações para o repositório do PCM
(`github.com/fillipefigueiro-source/gridco-pcm-data`), como o PC do PCM fazia; o robô do PCM leva ao App em 5 a 10 min.
Só administrador, com uma tela de conferência antes. Precisa de:

- `NEXUS_PCM_GITHUB_TOKEN` no `.env` (o Levi manda no pacote): token do GitHub só deste repositório, com escrita de
  conteúdo. Sem ele o botão mostra "sem token" e nada é enviado.
- Saída para `api.github.com` (seção 0).
- **Nunca teste clicando em Publicar:** publicar troca a semana de todo o campo. A tela de confirmação já mostra o que o
  repositório tem (só leitura); pare nela.
- O `dados/pcm/insumos.json` do pacote é o do PC na data do pacote. Depois que o servidor publicar, a reserva do
  histórico do servidor passa a ter as semanas que ele publicou; o histórico também lê o plano publicado direto do
  repositório do PCM, então PC e servidor geram com o mesmo histórico.

## 7a. Camada de dados: a carga de hora em hora

O Nexus grava, aos :40 de cada hora, na API do banco: `nexus_dimensoes` (calendário, feriados, histórico de pessoas e
usinas), `nexus_fatos` (fechamento, ronda e PT com os IDs do cadastro, e a qualidade da ligação), `nexus_equipamentos`
(a dimensão de equipamento, só quando muda) e `nexus_programacao` (a programação do PCM, juntando semana a semana: a
semana que o arquivo do PCM ainda traz é trocada, as antigas ficam). Liga sozinho onde há o `GRIDCO_SQL_TOKEN` no `.env`
(o pacote tem). Precisa também da `NEXUS_CHAVE_CADASTRO` (sem ela o técnico e o responsável da programação saem vazios)
e da `NEXUS_PESSOA_HMAC` (sem ela a pessoa dos fatos do App não liga).

**Na 1ª carga depois da atualização de 08/10/2026** entram no banco, pela primeira vez, o `fato_ronda`, o `fato_pt`, o
livro `nexus_equipamentos` e a mescla da programação; o histórico de pessoas e usinas passa a começar "desde sempre"
(`inicio_presumido = 1` na 1ª versão de cada uma). Conferir em Base → Governança de dados, uma hora depois do restart:
a hora da carga com a máquina "servidor", as barras de ligação de cada fato e a programação com 21 semanas ou mais. Com o PC do Levi e o servidor no ar ao mesmo
tempo, só um grava por hora (o outro vê a hora da última carga no próprio livro e pula). Desligar numa máquina:
`NEXUS_CARGA_DADOS=0`. Conferir: Base → **Governança de dados** mostra a hora da última carga e a máquina.

**Pré-carga das telas (09/10/2026): nada a fazer no servidor.** O Nexus deixa as telas do Campo · App prontas na memória
logo depois de subir e as renova antes de vencer, lendo só o banco. No servidor **não** ponha `NEXUS_CAMPO_AQUECER` no
`.env`: sem ela, o servidor também lê do Fracttal, ao subir, a fila da Aprovação, as rondas aprovadas, as OS de falha da
Engenharia e o Quadro da equipe. `NEXUS_CAMPO_AQUECER=0` é só para o PC do Levi, para os dois não gastarem a cota do
Fracttal em dobro.

## 7b. Servidor da PLATAFORMA (app.gridco.com.br): uma linha para ligar o Tempo real

*Desde 09/10/2026 esta é só a RESERVA do Tempo real: com a porta única ligada (seção 7e) o Tempo real abre a tela da plataforma numa moldura. A `NEXUS_PLATAFORMA_URL` fica como está no servidor (`https://app.gridco.com.br`): é ela que faz esta ponte voltar se a chave sair, e a moldura usa o mesmo endereço.*

A aba Performance → Tempo real do Nexus mostra a plataforma de Performance por uma chave só de leitura. O Nexus já leva a
chave; a plataforma precisa da mesma. No pacote vem à parte o arquivo `plataforma-tokens-nexus.txt`, com UMA linha
`NEXUS_LEITURA_TOKEN=...`: acrescente no `tokens.txt` da raiz da plataforma, no servidor dela, e reinicie a plataforma.
Conferir: no Nexus, **Performance → Tempo real** abre a Entrada da plataforma (antes disso, a aba diz "A plataforma
recusou a chave"; o resto do Nexus não depende dela). Pelo Nexus, a API PV fica de fora por enquanto: só o que a
plataforma já tem guardado.

## 7e. Porta única: as telas da Performance dentro do Nexus (09/10/2026)

Levi: "a partir de segunda quero o Nexus como link principal; o Nexus será o centro de tudo". O menu Performance do Nexus
(e o Acompanhamento COS e as Chaves das fontes) abre as telas da plataforma de Performance numa moldura, com o login do
Nexus: a página do Nexus manda um passe assinado (POST, vale 60 s, uma vez) a `/painel/nexus/entrar` da plataforma, que
abre a sessão dela e mostra a tela. Os dois sistemas continuam onde estão (Nexus em `/nexus`, plataforma na raiz).

**Tudo fica desligado até a T.I. pôr a chave nos DOIS.** Sem ela, no Nexus cada item diz "Performance ainda não ligada
neste servidor" (o que falta só aparece para admin) e fica como "em construção" no menu, sem o verde; o Tempo real
segue pela leitura de 04/10 (seção 7b), como hoje. Na plataforma, `/painel/nexus/*` responde 404. O que muda para quem
usa o Nexus antes da chave: o menu ganha 6 itens novos em construção (Disponibilidade, Relatório semanal, Histórico da
plataforma, Monitor da ronda, COS · Acompanhamento COS e Base · Chaves das fontes) e o Início conta 6 telas previstas a
mais. Na plataforma, nada muda para ninguém.

**O que a T.I. faz, nesta ordem** (o código dos dois já no ar):

1. Gerar UMA chave aleatória de 32 caracteres ou mais (no próprio servidor; não mande por e-mail aberto nem grupo):
   ```
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
2. No `.env` do **Nexus**: `NEXUS_SSO_CHAVE=<a chave>`. **Não mexa na `NEXUS_PLATAFORMA_URL`**: ela fica
   `https://app.gridco.com.br`, a mesma origem do Nexus, que é onde a moldura abre (vazia também serviria à moldura,
   mas aí a ponte de 04/10, seção 7b, perde o endereço e a volta do passo 5 deixa o Nexus sem Tempo real). Nunca um
   endereço interno (`http://127.0.0.1:...`): com ele o Nexus desliga a porta e diz por quê. Com a chave, o Tempo real
   já é a moldura e a ponte sai do menu. Reinicie: `sudo systemctl restart nexus`.
3. No `.env` (ou `tokens.txt`) da **plataforma**: a MESMA `NEXUS_SSO_CHAVE=<a chave>` e `PLATAFORMA_ANALISTAS=*` (decisão
   do Levi, 09/10: todo login do Nexus entra como analista; restringir depois é trocar o `*` por e-mails). Reinicie a
   plataforma.
4. Conferir:
   - `curl -s -D - -o /dev/null -X POST https://app.gridco.com.br/painel/nexus/entrar` responde da plataforma
     (`Server: waitress`, com `Via` do Caddy), e não 502 vazio do Caddy: sem passe, 403 com a chave e 404 sem ela;
   - entrar no Nexus, abrir **Performance → Tempo real**: a Entrada da plataforma aparece dentro do Nexus, sem o menu
     dela, e o endereço segue o que se abre lá dentro (`?p=...`); **Performance → Diagnóstico** lista as usinas;
   - o Nexus e a plataforma abertos juntos no mesmo navegador sem um derrubar o login do outro (`nexus_sessao` em
     `/nexus`, `session` da plataforma em `/`);
   - **Sair** do Nexus volta ao Entrar e encerra também a sessão aberta na plataforma.
5. Se algo der errado: tirar a `NEXUS_SSO_CHAVE` dos dois e reiniciar volta tudo ao de antes (o Tempo real volta pela
   ponte de 04/10, porque a `NEXUS_PLATAFORMA_URL` ficou como estava; revisão de 10/10/2026).

Trocar a chave derruba as sessões abertas pelo passe (todos abrem de novo pelo menu), não a senha da plataforma.

## 7c. Performance → Clima e risco: só leitura de fontes públicas

A tela cruza as usinas em operação do cadastro (a latitude e a longitude são campos cifrados, abertos só no processo do
Nexus com a `NEXUS_CHAVE_CADASTRO`, e nunca aparecem na tela) com os avisos do INMET, os focos de queimada e o risco de
fogo do INPE. **Não grava nada**: nem em `dados/`, nem no banco; cada fonte fica só na memória do processo (avisos 30 min,
focos 10 min, risco de fogo 6 h, ou 15 min enquanto o arquivo do INPE não é o de hoje: ele sai por volta das 06:30; depois
de uma falha, 60 s sem insistir). Reiniciar o Nexus esvazia o cache e a primeira visita relê tudo (~10 s). O **Mapa de risco**
(`/t/performance/clima/mapa`, e o modo TV `?tv=1` para o video wall) lê as mesmas fontes; a camada "Risco de fogo" lê a área do Brasil
no mesmo arquivo do INPE, numa thread ao fundo, só quando alguém a liga (ou o modo TV gira por ela): ~8 MB e ~10 s (7 s de CPU) por
dia de previsão escolhido, uma vez por arquivo (o INPE publica uma vez por dia); depois, a cada 6 h, só o cabeçalho (64 KB) para
ver se o arquivo mudou. Fica na memória (até ~10 MB com os quatro dias); nada vai para o disco nem para o banco. A PÁGINA de cada
usina (`/t/performance/clima/usina/<id>`) acrescenta a irradiação diária da **NASA POWER** (`power.larc.nasa.gov`): um pedido
por usina, só quando alguém abre a página dela, guardado por 12 h na memória (a tela principal nunca chama a NASA); a latitude
e a longitude vão no pedido com 2 casas. Cada falha de fonte vai ao log (`journalctl -u nexus`) como uma linha de aviso,
`clima: INMET (avisos) fora: sem conexão com o servidor`, sem dado de usina. Precisa da saída para `apiprevmet3.inmet.gov.br`,
`dataserver-coids.inpe.br`, `power.larc.nasa.gov` e `firms.modaps.eosdis.nasa.gov` (seção 0) e do cadastro no servidor
(`dados/cadastro_ensaio.json`). O fogo das últimas 24 h da NASA (FIRMS, 10/10/2026) são 4 arquivos públicos de ~3 MB (~9 MB
juntos), lidos a cada 30 min só quando mudaram (um HEAD por arquivo antes); ficam na memória (~20 MB na seca), nada vai ao disco
nem ao banco. Os endereços têm padrão e só se trocam para apontar a um espelho: `NEXUS_CLIMA_INMET_URL`, `NEXUS_CLIMA_FOCOS_URL`,
`NEXUS_CLIMA_RISCO_URL` (este leva `{d}`, o dia de 0 a 3), `NEXUS_CLIMA_POWER_URL` (leva `{lat}`, `{lon}`, `{inicio}` e `{fim}`,
as datas em AAAAMMDD) e `NEXUS_CLIMA_FIRMS_URL` (a base dos arquivos do FIRMS), no `.env`.

## 8. Atualizar

Um comando, no servidor (desde 06/10/2026):

```
sudo /opt/nexus/deploy/atualizar.sh
```

Ele busca no GitHub (`git fetch`, como o dono do clone), confere o commit novo **fora da pasta do serviço** (dependências
e boot), só então anda com a pasta (`git merge --ff-only`), reinicia o serviço e confere no `/saude` que o commit novo
está no ar. Qualquer erro antes do restart (pip, conferência, arquivo mexido à mão no servidor) para tudo com a pasta do
serviço no commit que está no ar: o Nexus de antes segue no ar, e um reboot ou um `systemctl restart nexus` sobe o mesmo
Nexus. **O restart é obrigatório:** o Nexus não relê as telas com o processo rodando. Em 06/10, o servidor ficou com a
tela antiga do PCM depois de só um `git pull`.

**Dependências e boot, antes de todo restart e antes de mexer na pasta (auditoria A6 e revisão adversarial da porta
única, 10/10/2026).** Até a A6 o pip só rodava quando o `requirements.txt` mudava entre o commit de antes e o de depois
do pull: se ele falhasse na 1ª rodada (o `reportlab`, novo e importado no boot, sem saída para o pypi), a 2ª via o mesmo
commit e dizia "nada a fazer", e com `--forcar` pulava o pip e reiniciava, deixando o Nexus fora. A A6 pôs o pip e a
conferência antes do restart, mas o `git pull` continuava antes dos dois: com um deles falhando, o script parava sem
reiniciar e a pasta já estava no commit que não sobe. O processo velho seguia lendo do disco novo (templates, o clone do
OS Creator na 1ª visita a /os/), e qualquer restart fora do script (reboot, queda com `Restart=always`, o DESFAZER do
5b) subia o código que não monta, com a raiz de app.gridco.com.br em 502. Agora, em toda rodada que vai reiniciar:
1. `git fetch` e o commit do GitHub extraído numa pasta temporária (`git archive`); a pasta do serviço não muda;
2. `pip install -q -r <pasta temporária>/requirements.txt` roda **sempre**, no `.venv` do serviço (é idempotente: sem
   nada novo, só confere, em segundos; ele só acrescenta ou atualiza pacotes, como antes). Falhou, para ali;
3. `<pasta temporária>/deploy/conferir_boot.py` importa, com o Python do `.venv`, as dependências e o Nexus DO COMMIT
   NOVO como o `servir.py` o monta (sem ler o `.env`, sem rede, sem gravar). Falhou, para ali;
4. aprovado: `git merge --ff-only` até o commit conferido (nem um a mais), o restart, e o commit fica marcado como
   instalado (`.git/nexus-instalado`).

Se o pip ou a conferência falham e a pasta do serviço estava fora do commit que está no ar (um `git pull` à mão, ou o
script antigo, que puxava antes de conferir), ela **volta** a ele (`git reset --keep`): o que está no ar é a marca e, sem
ela (a 1ª rodada depois do script antigo, que não a gravava), o commit que o `/saude` do processo rodando diz. O `--keep`
não apaga arquivo mexido à mão (se houver conflito, recusa e avisa "Não reinicie o serviço até resolver").

"Nada a fazer" é quando o commit do GitHub é o último **instalado** e a pasta está nele: a rodada que parou no pip ou na
conferência é completada pela seguinte (o timer, 2 min depois), sem ninguém rodar `--forcar`. `--forcar` instala e
reinicia mesmo sem nada novo. A 1ª rodada com este script (ainda sem a marca) instala e reinicia uma vez. Para conferir
à mão se o servidor tem tudo, sem reiniciar nada:
`sudo -u nexus /opt/nexus/.venv/bin/python -B /opt/nexus/deploy/conferir_boot.py` (diz o que falta na pasta do serviço;
o pip precisa de saída para `pypi.org` e `files.pythonhosted.org`).

**Na primeira vez** o servidor ainda tem o script antigo, que puxa antes de conferir. Não puxe à mão: tire o script novo
do commit buscado e rode-o de fora, apontando para a pasta do serviço (`NEXUS_RAIZ`), e a primeira rodada já é conferida:

```
sudo -u nexus git -C /opt/nexus fetch && sudo -u nexus git -C /opt/nexus show origin/main:deploy/atualizar.sh > /tmp/atualizar.sh
sudo env NEXUS_RAIZ=/opt/nexus bash /tmp/atualizar.sh --forcar
```

Se alguém já rodou o antigo e o pip dele falhou (a pasta ficou no commit novo, o processo velho no ar), a rodada
seguinte do novo põe a pasta de volta no commit do `/saude`.

O git não toca nos `.env` nem na `dados/`. Dependência nova no `requirements.txt` (o `pillow` em 06/10, o `reportlab` em
09/10) o script instala sozinho.

**Deploy por push (09/10/2026, Levi: "não dá para subir com o commit?").** O timer `deploy/nexus-atualizar.timer` roda o
mesmo `atualizar.sh` a cada 2 minutos: push na `main` entra no ar em até ~3 min, sem ninguém rodar nada; sem commit
novo (e com o último já instalado), não reinicia. Instala uma vez (o 1º comando já sobe o que estiver no GitHub):

```
sudo /opt/nexus/deploy/atualizar.sh && sudo cp /opt/nexus/deploy/nexus-atualizar.service /opt/nexus/deploy/nexus-atualizar.timer /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now nexus-atualizar.timer
```

Conferir: `systemctl list-timers nexus-atualizar.timer` (a próxima rodada) e `journalctl -u nexus-atualizar -n 30` (o
que cada rodada fez). Desligar: `sudo systemctl disable --now nexus-atualizar.timer`. Não há suíte de testes no
servidor: ela roda antes de cada push, na máquina de quem empurra. Commit que não monta (import quebrado, dependência que
não instalou) para na conferência do boot, sem restart e sem mexer na pasta do serviço. Commit que monta e mesmo assim não sobe (o `/saude` não responde
com ele; o `.env`, por exemplo) deixa o Nexus fora até o próximo commit consertar, como na plataforma: ele já ficou
marcado como instalado, para o timer não reiniciar a cada 2 min (cada boot relê a Aprovação no Fracttal).

**Depois da 1ª subida, a `dados/` do servidor é a original**: o que se edita no Nexus (cadastro, decisões do de-para,
observações e gerações do PCM) mora lá. Se o Levi mandar um pacote novo, descompacte **só os `.env`**, a menos que ele
diga o contrário:

```
sudo unzip -o nexus-acessos-*.zip .env nexus/torres/oscreator/os_creator/.env -d /opt/nexus && sudo systemctl restart nexus
```

**Estrutura de campo (08/10/2026):** as 8 regiões de campo, as vagas de Supervisor de Campo e de Coordenador e a região
de cada equipe foram carregadas no cadastro do PC do Levi e publicadas no banco (`cadastro_nexus · regioes_campo`). O
cadastro do servidor (`dados/cadastro_ensaio.json`) **não tem** essa estrutura: **não use "Publicar no banco" (Base →
Ligações) no servidor** até o Levi mandar o cadastro novo, senão a publicação de lá apaga as regiões do banco. As telas
do Campo do servidor leem o cadastro do banco e já mostram as regiões.

## 9. Cópia de segurança

Copie todo dia a pasta `/opt/nexus/dados/` e guarde os dois `.env` num cofre. **Sem a `NEXUS_CHAVE_CADASTRO`, o
dado cifrado do cadastro (CPF, telefone, endereço, receita) não volta.**

## O que ainda não funciona no servidor

- **"Importar da pasta do PCM"**: a pasta é o OneDrive do PCM. Os insumos já moram no Nexus
  (`dados/pcm/insumos.json`) e a AUXILIAR sai do cadastro, então gerar a semana não depende mais da pasta. Só as
  durações aprendidas (opcionais, em sombra) ficam de fora. As observações vêm pelo **"Importar observações do
  repositório do PCM"** (funciona no servidor) ou se escrevem no bloco 2 da tela.
- **Login:** é pelo Fracttal (o mesmo do OS Creator: entra quem tem conta da Grid Co. no Fracttal; um login abre o
  Nexus e o OS Creator). A senha de admin ficou como reserva. O login Microsoft não está ligado.

- **Base → Ligações:** o pacote já traz o de-para calculado. O Fracttal entra pela foto da última semana gerada no
  Nexus (`dados/pcm/geracoes/*/`): só use "Ler as bases de novo" depois da 1ª geração no servidor. Antes dela, o
  Fracttal liga só pelo nome das usinas (sem o código do equipamento, liga menos).
- **Cadastro em dia:** os responsáveis ainda atualizam o BD_Operações no Excel. Para o Nexus acompanhar, use
  **Base → Importar do Excel** com a planilha atual (mostra a prévia antes de gravar).
