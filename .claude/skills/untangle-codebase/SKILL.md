---
name: untangle-codebase
description: Use quando pedirem para desembaraçar, organizar, refatorar, limpar ou fazer faxina no código do Nexus - arquivo gigante para quebrar, função repetida, uma área importando da outra, ciclo de import, código que "ninguém usa", import sem uso (ruff, vulture, pyflakes), mover função ou rota de arquivo.
---

# Desembaraçar o código do Nexus

Desembaraçar é mudar o **lugar** do código, nunca o **comportamento**. A prova é a foto de antes igual à de depois e a
suíte igual. Apagar é outra coisa: precisa do OK do Levi, item por item ("não desfaça nada feito no Nexus").

A ferramenta é `foto.py`, nesta pasta. Rode da raiz da worktree: não precisa do `.env` e leva ~15 s.

```
F=.claude/skills/untangle-codebase/foto.py
python $F tirar <scratchpad>/antes.json     # rotas, nomes de cada módulo e quem lê cada nome (sobe o app: ciclo de import quebra aqui)
python $F mapa  <scratchpad>/antes.json     # a 1ª entrega de uma faxina
python $F quem  <arquivo> [...]             # outra sessão mexendo nele?
python $F comparar <antes.json> <depois.json>
```

## No começo, antes de mexer

1. Worktree nova do `origin/main` (`CLAUDE.md`, "Antes de começar"). Rode `gh pr list` e
   `git branch -r --no-merged origin/main`. Neste PC, o "Permission denied" de worktree antiga no `git fetch` é ruído.
2. Para cada arquivo que vai mexer, rode `quem`. Com TRABALHO ABERTO, o trecho que o outro ramo mexe fica onde está
   (`git -C <worktree> diff origin/main...HEAD -- <arquivo>` mostra qual é). O resto do arquivo pode sair, com rebase
   antes de cada push. Se o trabalho aberto pega quase o arquivo todo, ele fica para depois.
3. COS, Engenharia e Segurança têm programador próprio (entram por pull request). A pasta deles entra no mapa, mas só se
   mexe nela combinado com o Levi.
4. Diga a previsão. Pedido amplo ("faxina geral"): o mapa leva cerca de 1 h, e as horas de cada fatia saem do mapa.
   Pedido de um arquivo: dê as fatias e as horas já de cara. Prazo curto ("hoje ainda") corta fatias, nunca a prova:
   diga quais cabem hoje. Avise se a previsão estourar.
5. Uma fatia é um assunto de uma área, um commit, cerca de 1 h. O push junta as fatias prontas da entrega (cada push
   reinicia o servidor e esfria as telas por ~5 min), nunca uma fatia sem foto e sem teste.

## O mapa (a 1ª entrega de uma faxina, sem mudar código)

Rode `tirar` e depois `mapa`. A saída vai para o chat em três listas, para o Levi escolher, e não para o repositório:

- **Mover**: os gigantes e a seta invertida (área lendo torre).
- **Unificar**: os grupos de corpo idêntico.
- **Apagar**: função ou classe que ninguém chama no Python. Cada item só entra na lista depois do grep em templates, JS,
  `deploy/`, `ferramentas/` e `.github/`.

Em cada item, anote o dono (pasta com programador próprio?), o `quem` e quantos `monkeypatch` o módulo tem. Não instale
ruff nem vulture: o mapa já faz o levantamento, e `--fix` em lote é proibido (veja abaixo).

## O que a suíte não pega no Nexus

- **Reexportar no módulo antigo não salva o `monkeypatch`.** A foto acha ~800 `monkeypatch.setattr(módulo, "nome")`
  nos testes. A troca vale para quem lê o nome pelo módulo antigo. Quem chama da casa nova segue com a função de verdade, e
  o teste passa sem testar o que diz, ou vai ao banco.
- **Import "sem uso" é lido por outro arquivo.** `auth/chaves.py` lê `contestacoes.livros` dentro de um
  `try/except Exception`: tirar o import vira "não consegui conferir" na tela, sem erro.
- **Import dentro de função só quebra quando a função roda.** Só o `__init__` da torre Engenharia tem ~100 (ciclos contornados).
  Não suba um para o topo para "arrumar".
- **Rota sem chamador no repositório não está morta.** O App de Campo (Android, outro repositório), a Performance, o OS
  Creator Web e os timers do servidor chamam rotas que nenhum teste chama.
- **Função "sem uso" pode ser chamada pelo nome**: Jinja, `getattr`, `ferramentas/`, `deploy/`.
- **A ordem dos `from . import x_tela` no fim do `__init__` da torre** registra as rotas no `bp`: mantenha a ordem.
- **Homônimos não são iguais.** São 27 `_norm` e 14 `_sem_acento`, que diferem em acento, `None` e maiúscula. Só o
  corpo idêntico (o grupo do mapa) se unifica.

## Como mover

- Recorte por número de linha com script (`ast`: `lineno` até `end_lineno`), nunca redigitando. Só mover: renomear,
  reformatar ou "melhorar" é outra fatia.
- O assunto vai inteiro (a função, quem a chama e as constantes dela), para o `PATCH` não aparecer. Quem chama o quê
  dentro do arquivo sai do `ast` (os `Name` de cada função) e, de fora, do `consumo` da foto.
- Ler um nome pelo módulo antigo (`M.x`, `from M import x`) se resolve reexportando no fim do módulo antigo. Só o
  `monkeypatch` não se resolve assim.
- Partir o `__init__` de uma torre: as telas vão para `x_tela.py`, e o que várias telas usam vai para um `comum.py` da
  torre. O `__init__` define `TORRE` e `bp` antes de importar as telas, no fim (o molde de `torres/campo`), e `x_tela`
  importa `bp` do `__init__` sem ciclo.
- Seta invertida: a peça que a área lê da torre desce para a área, e a torre passa a importar dela. A seta muda de
  sentido sem criar ciclo.
- Unificar: a cópia comum vai para um módulo que não importa nada do Nexus (só a biblioteca padrão), para não criar
  ciclo, e cada módulo fica com o nome antigo apontando para ela (`_norm = sem_acento`), para o teste e o `monkeypatch` seguirem valendo.

## Fechar a fatia

`comparar` com grave, a fatia não fecha:

| Grave | O que fazer |
|---|---|
| `ROTA` sumiu ou mudou | Volte. Rota não sai em faxina. |
| `QUEBRA`: alguém lê um nome que sumiu | Devolva o nome, ou mude o leitor no mesmo commit. |
| `PATCH` que não pega mais | Leve quem chama junto com a função, ou mude o teste para a casa nova no mesmo commit (e diga). |

`CONFIRA` não barra a fatia, mas pede olho: um módulo deixou de ler o nome que um teste troca. Ou o teste nem passa por
ele, ou ele lê agora outra função que usa aquela por dentro (`livros.abas_conferidas` chama `livros.abas`). Se não for
nenhum dos dois, é um `PATCH`. Os avisos `SAIU` vão para a lista de apagar.

Para fechar:
- Por fatia: os testes da área (`tests/test_<area>*`) e a foto. Antes do push: a suíte inteira, em segundo plano e com
  timeout (são ~7 mil testes), com o mesmo número de testes da linha de base. Copie o `.env` antes, para o teste dos
  nomes rodar.
- O `CLAUDE.md` da área diz onde mora cada coisa agora (corrija a linha velha).
- Se moveu view ou template: tela na cópia de prova (5170), desktop e 375 px.
- `git diff --stat` lido. Push só com o OK, ou com "sobe direto" no pedido (vale para a entrega pedida). Rebase antes,
  `/saude` depois.
- Feche com Problema, Resolvido e Pendente.

## Pare se pensar

| Pensamento | Realidade |
|---|---|
| "Reexporto no antigo e os testes seguem passando" | É o `PATCH`: rode a foto. |
| "O ruff diz que não é usado" | Outro arquivo lê através dele: é a `QUEBRA`. |
| "Ninguém chama essa rota" | O App de Campo chama. |
| "Já que estou aqui, renomeio" | Outra fatia. |
| "Faço tudo de uma vez e subo" | Push é produção. Fatias, com previsão. |
