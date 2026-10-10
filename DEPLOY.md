# Nexus no servidor: passo a passo para a T.I.

O Nexus é um app Flask (Python), servido pelo waitress, atrás de um proxy com HTTPS. Um processo só: não tem banco
próprio nem fila. O estado fica em arquivos na pasta `dados/` do projeto; o dado compartilhado vai para a API
db_performace (PostgreSQL da Grid Co.).

**O código vem do GitHub** (`github.com/Grid-Co-CODE/nexus`, público: o clone não precisa de chave). **O que não está
no GitHub** vem num pacote à parte que o Levi envia por canal privado, o `nexus-acessos-AAAA-MM-DD.zip`:

| Caminho no pacote | O que é |
|---|---|
| `.env` | os segredos do Nexus: chave da sessão, senha de entrada, chave da cifra do cadastro, token de escrita na API db_performace, o token do repositório do PCM para Publicar no App (`NEXUS_PCM_GITHUB_TOKEN`, desde 09/10/2026). Também leva o endereço e a chave só de leitura da plataforma de Performance (`NEXUS_PLATAFORMA_URL`, `NEXUS_PLATAFORMA_TOKEN`) e a chave do código da pessoa do App de Campo (`NEXUS_PESSOA_HMAC`) |
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

**Use um subdomínio próprio**, por exemplo `nexus.gridco.com.br`, e não um caminho dentro de `app.gridco.com.br`:
o Nexus usa `/`, `/t/...`, `/os/...` e `/static/...`, que colidem com a plataforma. No Caddy:

```
nexus.gridco.com.br {
    reverse_proxy 127.0.0.1:5070
}
```

O cookie de sessão sai com `Secure`: o Nexus **precisa** de HTTPS na frente. O proxy tem de repassar
`X-Forwarded-For` (o Caddy repassa por padrão): é por ele que o limite de tentativas de senha conta cada pessoa, e não
o servidor inteiro como uma só.

## 6. Conferir depois de subir

1. `https://nexus.gridco.com.br/saude` responde `{"ok": true, "commit": "..."}` com o commit do GitHub.
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

A aba Performance → Tempo real do Nexus mostra a plataforma de Performance por uma chave só de leitura. O Nexus já leva a
chave; a plataforma precisa da mesma. No pacote vem à parte o arquivo `plataforma-tokens-nexus.txt`, com UMA linha
`NEXUS_LEITURA_TOKEN=...`: acrescente no `tokens.txt` da raiz da plataforma, no servidor dela, e reinicie a plataforma.
Conferir: no Nexus, **Performance → Tempo real** abre a Entrada da plataforma (antes disso, a aba diz "A plataforma
recusou a chave"; o resto do Nexus não depende dela). Pelo Nexus, a API PV fica de fora por enquanto: só o que a
plataforma já tem guardado.

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

Ele puxa do GitHub (`git pull --ff-only`, como o dono do clone), instala as dependências só quando o `requirements.txt`
mudou, reinicia o serviço e confere no `/saude` que o commit novo está no ar. Sem commit novo, não reinicia; com
`--forcar`, reinicia assim mesmo. Qualquer erro (por exemplo, arquivo mexido à mão no servidor) para tudo antes do
restart, e o Nexus segue no ar com o código de antes. **O restart é obrigatório:** o Nexus não relê as telas com o
processo rodando. Em 06/10, o servidor ficou com a tela antiga do PCM depois de só um `git pull`.

**Na primeira vez** o clone do servidor ainda não tem o script. Puxe uma vez à mão e rode-o:

```
sudo -u nexus git -C /opt/nexus pull --ff-only && sudo bash /opt/nexus/deploy/atualizar.sh --forcar
```

O git não toca nos `.env` nem na `dados/`. Em 06/10 entrou o `pillow` no `requirements.txt` (miniaturas das fotos da
ronda; sem ele as fotos aparecem do mesmo jeito, só mais pesadas): o script instala sozinho.

**Deploy por push (09/10/2026, Levi: "não dá para subir com o commit?").** O timer `deploy/nexus-atualizar.timer` roda o
mesmo `atualizar.sh` a cada 2 minutos: push na `main` entra no ar em até ~3 min, sem ninguém rodar nada; sem commit
novo, não reinicia. Instala uma vez (o 1º comando já sobe o que estiver no GitHub):

```
sudo /opt/nexus/deploy/atualizar.sh && sudo cp /opt/nexus/deploy/nexus-atualizar.service /opt/nexus/deploy/nexus-atualizar.timer /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now nexus-atualizar.timer
```

Conferir: `systemctl list-timers nexus-atualizar.timer` (a próxima rodada) e `journalctl -u nexus-atualizar -n 30` (o
que cada rodada fez). Desligar: `sudo systemctl disable --now nexus-atualizar.timer`. Não há suíte de testes no
servidor: ela roda antes de cada push, na máquina de quem empurra. Commit que não sobe (o `/saude` não responde com ele)
deixa o Nexus fora até o próximo commit consertar, como na plataforma.

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
