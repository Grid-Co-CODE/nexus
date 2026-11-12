# Guia do GitHub para quem programa a Zeladoria

Para o HEAD da zeladoria, que desde 11/11/2026 programa a Zeladoria do Nexus e sobe as próprias mudanças (o Radar parou
junto com o Supabase, e o Nexus virou a casa da zeladoria). As regras da área estão no `CLAUDE.md` desta pasta (seção
"Como entregar"); este guia é o passo a passo do dia a dia, no Windows.

> **Importante:** o repositório `Grid-Co-CODE/nexus` é **público**, e você é **administrador** dele. Tudo o que subir na
> `main` vai para produção (app.gridco.com.br) sozinho em ~2 minutos, com o servidor reiniciando. Não há revisão no
> meio: o cuidado é seu.

## 1. Primeira vez (uma vez só)

### 1.1 Aceitar o convite
1. Entre no GitHub com a **sua conta de trabalho** (a que recebeu o convite). O erro mais comum é abrir o convite logado
   em outra conta.
2. Abra https://github.com/Grid-Co-CODE/nexus/invitations e clique em **Accept invitation**.

### 1.2 Instalar
- **Git para Windows**: https://git-scm.com/download/win (pode aceitar o padrão em tudo).
- **GitHub CLI**: https://cli.github.com (o comando `gh`).
- **Python 3.14** (o mesmo do servidor): https://www.python.org/downloads/ (marque "Add python.exe to PATH").
- Um editor: o VS Code, ou o Claude Code (seção 6).

### 1.3 Entrar no GitHub pelo terminal
No PowerShell:

```powershell
gh auth login
```

Escolha **GitHub.com**, **HTTPS**, **Login with a web browser**, e confirme o código no navegador. Depois:

```powershell
gh auth setup-git
git config --global user.name "Seu Nome"
git config --global user.email "seu-email-do-github"
```

### 1.4 Baixar o Nexus
Numa pasta **fora do OneDrive** (o OneDrive sincroniza a pasta `.git` e corrompe o repositório):

```powershell
mkdir C:\dev; cd C:\dev
gh repo clone Grid-Co-CODE/nexus
cd nexus
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 1.5 O `.env`
O Nexus só roda com o arquivo `.env` (as chaves do banco, a chave de cifra, a senha de administrador). Ele **não está
no GitHub** e nunca vai estar. Peça ao Levi por um canal privado e salve como `C:\dev\nexus\.env`.
- Nunca mande o `.env` por e-mail, grupo ou print, e nunca o suba no GitHub (o `.gitignore` já o protege; não force).
- Sem o `.env`, a trava de nomes dos testes não roda, e nome de colega pode passar.

## 2. O dia a dia

### 2.1 Antes de começar: pegar o que os outros subiram
Outras pessoas sobem na `main` o tempo todo. Sempre comece com:

```powershell
cd C:\dev\nexus
git pull
```

### 2.2 Onde mexer
A área da Zeladoria (leia o `CLAUDE.md` desta pasta antes):

| O quê | Onde |
|---|---|
| O app (as 18 telas, que era o Radar) | `nexus/torres/zeladoria/clone/radar.html` (edite direto) |
| As rotas e a página da troca | `nexus/torres/zeladoria/__init__.py` e `templates/zeladoria/` |
| O dado: leitura, gravação, financeiro, rondas do Fracttal, cronograma | `nexus/zeladoria/` |
| A ponte (o `supabase` falso que o app usa) e os filtros | `nexus/static/zeladoria/` |
| Os testes | `tests/test_zeladoria_*.py` |

**Fora da Zeladoria** (menu, login, cadastro, as outras torres): fale com o Levi antes. Ser administrador deixa subir,
mas o resto do Nexus é de outras pessoas.

**Tabela nova** no banco: entra em `nexus/zeladoria/tabelas.py` e no catálogo antes da 1ª gravação (`nexus/dados/CLAUDE.md`).

### 2.3 Ver funcionando no seu PC
Use a **cópia de prova**: ela lê o banco de verdade, mas **não grava nada fora da sua máquina**, então dá para testar à
vontade:

```powershell
python ferramentas/subir_copia_de_prova.py --porta 5170 --plataforma ""
```

Abra http://127.0.0.1:5170/entrar?admin=1, entre com a senha de administrador do `.env`, e vá em Zeladoria. Confira a
tela no computador e no tamanho de celular (375 px: F12 no navegador, ícone de celular). Para parar, Ctrl+C.

### 2.4 Rodar os testes
Com o `.env` no lugar:

```powershell
python -m pytest tests/test_zeladoria_*.py tests/test_sem_nomes_no_repositorio.py -q
```

Tudo verde antes de subir. Teste vermelho é sinal para parar, não para subir assim mesmo.

### 2.5 Subir
```powershell
git status                      # o que mudou
git diff                        # releia o que vai subir
git add nexus/torres/zeladoria/clone/radar.html     # só os arquivos que você mexeu, um por um
git commit -m "feat(zeladoria): o que mudou, em português"
git pull                        # junta o que os outros subiram enquanto você trabalhava
git push
```

- **Mensagem do commit:** `feat(zeladoria): ...` para coisa nova, `fix(zeladoria): ...` para conserto,
  `docs(zeladoria): ...` para texto. Diga o que mudou para quem usa, em português.
- **Nunca** `git add .` sem olhar o `git status`: é assim que arquivo pessoal, planilha ou print vaza no repositório
  público.

### 2.6 Conferir que entrou no ar
Em ~2 minutos:

```powershell
curl.exe -s https://app.gridco.com.br/saude
```

O `commit` que aparece tem de ser o seu (os 7 primeiros caracteres de `git log -1 --format=%h`). Abra a tela em
app.gridco.com.br e confira.

## 3. As regras que não podem falhar (o repositório é público)

- **Nada de nome de pessoa, e-mail, CPF, telefone, dado de cliente ou de contrato, print ou senha** em arquivo do
  repositório, nem em comentário. Cite pelo papel: "o HEAD", "o analista", "o supervisor da equipe", "um fornecedor".
- **Cor só por token** (`var(--...)`), nunca `#hex` nem `rgba()` solto; **sem emoji** na tela; tudo em **português**.
- **Dado só no banco do Nexus**: nada de Supabase, planilha no OneDrive ou JSON fazendo papel de banco.
- **Nunca** `git push --force`, nunca apagar a `main`, e nada de mexer nas configurações do repositório (Settings).

## 4. Quando algo dá errado

| Situação | O que fazer |
|---|---|
| `git push` recusado ("rejected", "fetch first") | Alguém subiu antes. `git pull` e `git push` de novo. |
| `git pull` deu **conflito** | O Git marca o trecho com `<<<<<<<` e `>>>>>>>`. Arrume o arquivo, `git add` nele e `git commit`. Na dúvida, `git merge --abort` e chame o Levi. |
| Subiu e a tela quebrou | Desfaça na hora: `git revert HEAD` e `git push`. O servidor volta ao anterior em ~2 min. Depois conserte com calma. |
| Subiu um arquivo que não devia (nome, e-mail, planilha) | Avise o Levi **na hora**. Apagar num commit novo não basta: o histórico é público. |
| `/saude` não mostra o seu commit depois de 5 min | O servidor recusou subir (erro ao iniciar). Avise o Levi. |

## 5. Comandos que você vai usar

| Comando | Para quê |
|---|---|
| `git pull` | Trazer o que os outros subiram |
| `git status` | Ver o que você mudou |
| `git diff` | Ver as linhas que mudaram |
| `git add <arquivo>` | Escolher o arquivo que vai no commit |
| `git commit -m "..."` | Guardar a mudança com a mensagem |
| `git push` | Subir (vai para produção) |
| `git log --oneline -10` | Os últimos 10 commits |
| `git revert HEAD` | Desfazer o último commit com um commit novo (seguro) |
| `git restore <arquivo>` | Jogar fora o que você mudou num arquivo (antes do commit) |

## 6. Com o Claude Code

Abra o Claude Code na pasta `C:\dev\nexus`. Ele lê sozinho o `CLAUDE.md` da raiz e o desta pasta. Peça do jeito de
sempre ("na Zeladoria, quero que..."), e no fim peça para rodar os testes, conferir a tela na cópia de prova e só então
commitar e subir. Ele conhece as regras do repositório público. Mesmo assim, releia o `git diff` antes do `git push`.
