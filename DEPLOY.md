# Nexus no servidor: passo a passo para a T.I.

O Nexus é um app Flask (Python), servido pelo waitress, atrás de um proxy com HTTPS. Um processo só: não tem banco
separado nem fila; o estado fica em arquivos na pasta `dados/` do projeto.

**O código vem do GitHub** (`github.com/Grid-Co-CODE/nexus`, público: o clone não precisa de chave). **O que não está
no GitHub** vem num pacote à parte que o Levi envia, o `nexus-acessos-AAAA-MM-DD.zip`:

| Caminho no pacote | O que é |
|---|---|
| `.env` | os segredos do Nexus: chave da sessão, senha de entrada, chave da cifra do cadastro, o token de escrita na API db_performace (publicar o cadastro no banco), `NEXUS_PLATAFORMA_URL` (no servidor, `https://app.gridco.com.br`) e `NEXUS_PLATAFORMA_TOKEN` (a mesma `NEXUS_LEITURA_TOKEN` do `.env` da plataforma no servidor) |
| `nexus/torres/oscreator/os_creator/.env` | a credencial do Fracttal (OS Creator e motor do PCM) |
| `dados/cadastro_ensaio.json` | o cadastro do BD_Operações (o sensível vai cifrado; a chave está no `.env`) |
| `dados/pcm/insumos.json` | os insumos da programação semanal do PCM |
| `dados/de_para_regras.json` | as decisões que tiram linhas do de-para (teste, tarefa interna, usina que não entra no BD) |
| `dados/pcm/_ativos_classificacao_cache.json` | a lista de usinas do Fracttal (a tela de observações do PCM usa) |

O pacote é descompactado **na raiz do clone**: cada arquivo cai no lugar certo. Os dois `.env` e a `dados/` nunca vão
para o git (o `.gitignore` já barra) nem para pasta compartilhada.

## 1. Clone, acessos e dependências

Testado com **Python 3.14**. Em `/opt/nexus` (ou onde preferir; ajuste o caminho no `deploy/nexus.service`):

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
`NEXUS_PORTA` e `NEXUS_HOST` no `nexus.service`.

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

## 6. Atualizar

```
cd /opt/nexus && sudo -u nexus git pull && sudo systemctl restart nexus
```

O git não toca nos `.env` nem na `dados/`. Se o Levi mandar um pacote de acessos novo, descompacte de novo na raiz
(passo 1) e reinicie.

## O que ainda não funciona no servidor

- **"Importar da pasta do PCM"** não funciona lá: a pasta é o OneDrive do PCM. Os insumos já moram no Nexus
  (`dados/pcm/insumos.json`) e a AUXILIAR sai do cadastro (`dados/cadastro_ensaio.json`), então gerar a semana não
  depende mais da pasta. Só as durações aprendidas (opcionais, em sombra) ficam de fora.
- **Login:** é por senha de admin (a `NEXUS_SENHA_ADMIN` do `.env`). O login Microsoft ainda não está ligado.
