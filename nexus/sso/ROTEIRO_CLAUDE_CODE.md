# Roteiro: o SSO da zeladoria no Claude Code (para o HEAD da zeladoria)

O Supabase parou em 11/11/2026. Desde 12/11/2026 o SSO (a Integração de Segurança) tem **duas casas**:

- **O site**, no seu repositório e no seu Cloudflare, com a mesma cara de sempre (`sso-zeladoria.gridco.com.br`).
- **Os dados**, no Nexus: o banco (os livros `nexus_sso_*`, cifrados), a API que o site chama
  (`https://app.gridco.com.br/t/sso`) e os arquivos (fotos, vídeos, certificados) no disco do servidor.

O que liga as duas é um arquivo só, o `shared/supabase-client.js` do site. Ele faz o papel do Supabase e fala com o
Nexus.

Antes de tudo, faça o `GUIA_GITHUB.md` da Zeladoria (`nexus/torres/zeladoria/GUIA_GITHUB.md`): o acesso ao repositório
do Nexus, a instalação, o `.env` e o dia a dia de subir. Este roteiro supõe o Nexus em `C:\dev\nexus`.

## 1. A primeira vez: pôr o site para falar com o Nexus

Abra o Claude Code **na pasta do repositório do site** (a que tem a `integracao-seguranca/`) e cole:

> Troque o arquivo `integracao-seguranca/shared/supabase-client.js` pelo conteúdo de
> https://raw.githubusercontent.com/Grid-Co-CODE/nexus/main/nexus/sso/site/supabase-client.js (baixe e salve igual,
> sem mudar nada). Não mexa em nenhum outro arquivo. Me mostre o `git diff`, faça o commit "o SSO grava pelo Nexus no
> lugar do Supabase" e suba na main (o GitHub Actions publica o worker).

Depois, confira no celular e no computador:
- `/campo/`: o vídeo toca, o quiz e a assinatura enviam, e aparece "Integração concluída". O vídeo só toca depois que o
  administrador do Nexus enviá-lo (seção 5). Se você tem o `integracao-zeladoria.mp4` original, mande ao Levi.
- `/apr/`, `/epi/`, `/vistoria/` e `/diario/`: envie um de cada, com foto.
- "Sou da gestão": leva ao login do Nexus (o mesmo do Fracttal) e volta à Gestão já logado.

## 2. Onde fica cada coisa

| O que você quer mudar | Onde mexer |
|---|---|
| O visual, os textos, os campos e as validações dos formulários; a Gestão; os PDFs e o Excel | No **site** (`integracao-seguranca/...`) |
| Quem pode ler e gravar o quê; os padrões, as obrigatórias, as listas fechadas | Nexus: `nexus/sso/esquema.py` e `nexus/sso/regras.py` |
| Os tetos (tamanho, limite por hora) | Nexus: `nexus/sso/esquema.py` (`BUCKETS`) e `nexus/sso/limite.py` |
| A gravação no banco e o que vai cifrado | Nexus: `nexus/sso/gravacao.py` e `nexus/sso/tabelas.py` |
| Os arquivos (onde ficam, quem abre) | Nexus: `nexus/sso/arquivos.py` |
| As rotas da API e a página do administrador | Nexus: `nexus/sso/api.py` e `nexus/sso/templates/sso/admin.html` |
| O `supabase-client.js` | Nexus: `nexus/sso/site/supabase-client.js`. Mudou ali, copie de novo para o site e suba lá também |
| Os testes | Nexus: `tests/test_sso_*.py` e `tests/sso_ponte_node.js` |

Mudança só de tela, que não muda o que é gravado, é só no site: não precisa do Nexus.

## 3. Mexer no Nexus pelo Claude Code

1. **Comece atualizado:** no PowerShell, `cd C:\dev\nexus` e `git pull`.
2. **Abra o Claude Code em `C:\dev\nexus`** e comece o pedido assim:

   > Leia o `CLAUDE.md` da raiz e o `nexus/sso/CLAUDE.md`. No SSO da zeladoria, quero que (...). No fim, rode os testes
   > do SSO, prove na cópia de prova com o site local (seção 3 do `nexus/sso/ROTEIRO_CLAUDE_CODE.md`) e me mostre o
   > `git diff` antes de subir.

3. **As regras que o Claude já conhece, e que você confere no `git diff`:**
   - O repositório é **público**: nada de nome de pessoa, e-mail, CPF, telefone, dado de cliente ou senha, nem em
     comentário nem em teste. Nos testes, use pessoas e usinas fictícias.
   - **Todo texto que o fornecedor escreve vai cifrado.** Em claro, só lista fechada e conferida (o estado, a fase da
     vistoria). Foi assim que um nome de pessoa digitado como usina parou em claro no banco, que tem leitura aberta.
   - **O fornecedor só envia:** nada de rota que deixe o anônimo ler presença, APR ou qualquer outro formulário.
   - **Rota pública nova** entra em `ROTAS_PUBLICAS` (`nexus/auth/__init__.py`) com o motivo escrito, e com limite.
   - **O gravador é o mesmo da Zeladoria** (`nexus/zeladoria/gravacao.py`). Mexeu nele, rode também os testes da
     Zeladoria.
4. **Rodar os testes** (com o `.env` no lugar):

   ```powershell
   python -m pytest tests/test_sso_api.py tests/test_sso_copia.py tests/test_sso_ponte.py tests/test_zeladoria_gravacao.py tests/test_sem_nomes_no_repositorio.py -q
   ```

5. **Ver funcionando no PC, de ponta a ponta.** São duas janelas do PowerShell, e nada é gravado fora da sua máquina.
   - **Janela 1, a cópia de prova do Nexus:**

     ```powershell
     cd C:\dev\nexus
     $env:NEXUS_SSO_GRAVA = "1"
     $env:NEXUS_SSO_ORIGENS = "http://sso-prova.localhost:5187"
     $env:NEXUS_DADOS = "C:\dev\rascunho_sso"
     $env:NEXUS_SECRET_KEY = "qualquer-texto-longo-so-desta-prova"
     python ferramentas/subir_copia_de_prova.py --porta 5171 --plataforma ""
     ```

     A `NEXUS_SECRET_KEY` própria serve para o login tirado na cópia não valer em produção. A 1ª leitura do banco leva
     ~1 minuto: até lá a API responde "carregando".
   - **Janela 2, o site:**
     1. Copie a pasta `integracao-seguranca` do seu site para `C:\dev\site_prova`.
     2. Nessa cópia, troque o `shared/supabase-client.js` pelo de `C:\dev\nexus\nexus\sso\site\` e mude só a linha
        `var NEXUS = ...` para `var NEXUS = "http://nexus-prova.localhost:5171";`.
     3. Rode:

        ```powershell
        python -m http.server 5187 --bind 127.0.0.1 --directory C:\dev\site_prova
        ```

   - **No navegador:** entre primeiro em `http://nexus-prova.localhost:5171/entrar?admin=1`, com a senha de
     administrador do `.env`. Depois abra `http://sso-prova.localhost:5187/`, envie os formulários e use "Sou da
     gestão".
   - Os nomes `*.localhost` impedem o login da prova de se misturar com outro Nexus aberto no mesmo navegador.
6. **Subir:** como no guia (seção 2.5), com os arquivos um por um (`git add nexus/sso/...`) e a mensagem
   `feat(sso): ...` ou `fix(sso): ...`. A `main` vai para produção em ~2 minutos. Para conferir:

   ```powershell
   curl.exe -s https://app.gridco.com.br/saude
   curl.exe -s "https://app.gridco.com.br/t/sso/api/v/iv_sessoes_video?eq=ativo:true&select=titulo"
   ```

   O 1º comando mostra o seu commit. O 2º devolve o título da sessão (logo depois de subir, pode dizer "carregando"
   por ~1 minuto).

## 4. Pedidos comuns (para colar no Claude Code do Nexus)

- **Mudar quem pode o quê:**

  > No SSO, a Gestão aprovada também pode (ou deixa de poder) [ação] em [formulário]. Mude a matriz em
  > `nexus/sso/esquema.py` e ponha o teste em `tests/test_sso_api.py`.

- **Aceitar outro tipo de arquivo ou outro tamanho:**

  > No SSO, o bucket [nome] passa a aceitar [tipo] até [N] MB. O tipo é conferido pelos primeiros bytes
  > (`esquema.tipo_do_arquivo`); ponha o teste.

- **Campo novo que é gravado (uma coluna nova).** Hoje o Nexus recusa coluna que o livro não tem, como o Postgres
  recusava, então esta mudança é no Nexus e no site. **Combine com o Levi antes de subir**, porque mexe no banco:

  > No SSO, o formulário [qual] ganha o campo [nome] ([texto, número, data, sim/não]), gravado na aba [aba]. Faça o
  > caminho de coluna nova no Nexus: o tipo das colunas vem da aba `atualizacao` de cada livro (`nexus/sso/leitura.py`,
  > e o gravador regrava a `atualizacao`), cifrado se for texto. Ponha os testes e me mostre o `git diff`.

- **Outro endereço para o site** (um domínio novo): ele tem de entrar na lista `NEXUS_SSO_ORIGENS` do servidor, que é
  do Levi, ou no padrão `ORIGENS_PADRAO` de `nexus/sso/api.py`.

## 5. A página do administrador do Nexus

`https://app.gridco.com.br/t/sso/admin`, só para o administrador do Nexus (o Levi). Mostra se o servidor está gravando
o SSO, o disco livre e os arquivos que ficaram no Supabase. Também:
- recebe o vídeo da integração e os arquivos antigos (uma pasta baixada de um bucket; cada arquivo vai para o caminho
  do inventário);
- tira da lista de usinas do diário o que não é usina;
- regrava os livros cifrados.

## 6. Quando algo dá errado

| O site mostra | O que é |
|---|---|
| "Sem conexão com o servidor" | O Nexus está fora do ar, ou o endereço do site não está na lista do CORS (seção 4) |
| "o Nexus está lendo os dados do SSO agora" | Logo depois de subir: espere 1 minuto |
| "este Nexus não guarda o SSO" | A gravação está desligada no servidor (o botão da página da troca da Zeladoria): avise o Levi |
| "falta [campo]", "não é permitido", "envio grande demais" | O Nexus recusou a linha (obrigatória, lista fechada, tamanho): o texto diz o motivo |
| "muitos envios" ou "muitos arquivos" | O limite por hora do IP: espere, ou ajuste em `nexus/sso/limite.py` |
| A Gestão volta sempre ao login | O login do Nexus (Fracttal) não passou, ou a pessoa não tem conta lá |
| A foto antiga aparece quebrada | O arquivo ficou no Supabase e ainda não foi resgatado (seção 5) |
| Subiu e quebrou | `git revert HEAD` e `git push` (guia, seção 4), depois conserte com calma |
