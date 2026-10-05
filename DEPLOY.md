# Nexus no servidor: passo a passo para a T.I.

O Nexus é um app Flask (Python), servido pelo waitress, atrás de um proxy com HTTPS. Um processo só: não tem banco
próprio nem fila. O estado fica em arquivos na pasta `dados/` do projeto; o dado compartilhado vai para a API
db_performace (PostgreSQL da Grid Co.).

**O código vem do GitHub** (`github.com/Grid-Co-CODE/nexus`, público: o clone não precisa de chave). **O que não está
no GitHub** vem num pacote à parte que o Levi envia por canal privado, o `nexus-acessos-AAAA-MM-DD.zip`:

| Caminho no pacote | O que é |
|---|---|
| `.env` | os segredos do Nexus: chave da sessão, senha de entrada, chave da cifra do cadastro, token de escrita na API db_performace. Também leva o endereço e a chave só de leitura da plataforma de Performance (`NEXUS_PLATAFORMA_URL`, `NEXUS_PLATAFORMA_TOKEN`) e a chave do código da pessoa do App de Campo (`NEXUS_PESSOA_HMAC`) |
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
  `app.fracttal.com` e `one.fracttal.com` (Fracttal), `raw.githubusercontent.com` (banco do PCM).
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
2. Entrar com a senha de admin (a `NEXUS_SENHA_ADMIN` do `.env`; o Levi tem).
3. **Base → Registro mestre** abre a lista de usinas: a chave da cifra está certa.
4. **PCM → Gerar a semana**: a lista de conferência diz "pronto" (motor, credencial do Fracttal, cadastro e insumos).
   A "Pasta do PCM" e as durações aprendidas aparecem como opcionais ausentes: é o esperado no servidor.
5. **OS Creator → Início** abre a entrada do OS Creator: cada pessoa entra com o próprio usuário do Fracttal, e
   depois disso **Ativos Fracttal** lista os ativos.
6. **Campo · App → Ordens de serviço** mostra as OS da semana com a nota do painel do App (a fonte é o livro que o
   App grava no banco; precisa da `NEXUS_PESSOA_HMAC` no `.env`, ver o passo 7).

## 7. Campo · App: o Nexus lê o que o App grava

As telas Aprovação de OS, Ordens de serviço e Triagem leem o registro de cada fechamento **que o próprio App de Campo
grava no banco** (API db_performace, livros `fechamentos_app_campo` e `rondas_app_campo`, de hora em hora). O técnico
vem como código (HMAC do e-mail): o `.env` do pacote já traz a `NEXUS_PESSOA_HMAC`, a MESMA chave da configuração do
App. Sem ela, as telas seguiriam com o livro antigo do coletor (dados parados).

**O coletor do Fracttal está aposentado:** não ponha `NEXUS_CAMPO_COLETOR=1` no servidor (o pacote não tem). Ele lia o
Fracttal com a cota da empresa inteira para recalcular uma nota que o App já grava.

A tela **Aprovação de OS** lê a fila do Fracttal ao vivo quando alguém a abre: ~55 pedidos de uma vez, no máximo a
cada 10 minutos por servidor (os filtros reusam a mesma leitura). Em hora de pico da cota ela mostra o aviso de fila
incompleta; a tela continua de pé.

## 7b. Servidor da PLATAFORMA (app.gridco.com.br): uma linha para ligar o Tempo real

A aba Performance → Tempo real do Nexus mostra a plataforma de Performance por uma chave só de leitura. O Nexus já leva a
chave; a plataforma precisa da mesma. No pacote vem à parte o arquivo `plataforma-tokens-nexus.txt`, com UMA linha
`NEXUS_LEITURA_TOKEN=...`: acrescente no `tokens.txt` da raiz da plataforma, no servidor dela, e reinicie a plataforma.
Conferir: no Nexus, **Performance → Tempo real** abre a Entrada da plataforma (antes disso, a aba diz "A plataforma
recusou a chave"; o resto do Nexus não depende dela). Pelo Nexus, a API PV fica de fora por enquanto: só o que a
plataforma já tem guardado.

## 8. Atualizar

```
cd /opt/nexus && sudo -u nexus git pull && sudo systemctl restart nexus
```

O git não toca nos `.env` nem na `dados/`.

**Depois da 1ª subida, a `dados/` do servidor é a original**: o que se edita no Nexus (cadastro, decisões do de-para,
observações e gerações do PCM) mora lá. Se o Levi mandar um pacote novo, descompacte **só os `.env`**, a menos que ele
diga o contrário:

```
sudo unzip -o nexus-acessos-*.zip .env nexus/torres/oscreator/os_creator/.env -d /opt/nexus && sudo systemctl restart nexus
```

## 9. Cópia de segurança

Copie todo dia a pasta `/opt/nexus/dados/` e guarde os dois `.env` num cofre. **Sem a `NEXUS_CHAVE_CADASTRO`, o
dado cifrado do cadastro (CPF, telefone, endereço, receita) não volta.**

## O que ainda não funciona no servidor

- **"Importar da pasta do PCM"**: a pasta é o OneDrive do PCM. Os insumos já moram no Nexus
  (`dados/pcm/insumos.json`) e a AUXILIAR sai do cadastro, então gerar a semana não depende mais da pasta. Só as
  durações aprendidas (opcionais, em sombra) ficam de fora.
- **Login:** é por senha de admin. O login Microsoft ainda não está ligado.

- **Campo · App, ligação técnico ↔ cadastro pelo e-mail:** espera a `NEXUS_PESSOA_HMAC` (a mesma chave do App de Campo),
  que o Levi gera quando o App passar a mandar os dados. Até lá, o mapa dos técnicos vem vazio e as telas funcionam.
- **Base → Ligações:** o pacote já traz o de-para calculado. O Fracttal entra pela foto da última semana gerada no
  Nexus (`dados/pcm/geracoes/*/`): só use "Ler as bases de novo" depois da 1ª geração no servidor. Antes dela, o
  Fracttal liga só pelo nome das usinas (sem o código do equipamento, liga menos).
- **Cadastro em dia:** os responsáveis ainda atualizam o BD_Operações no Excel. Para o Nexus acompanhar, use
  **Base → Importar do Excel** com a planilha atual (mostra a prévia antes de gravar).
