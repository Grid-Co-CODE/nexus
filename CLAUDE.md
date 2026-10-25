# CLAUDE.md — Nexus

Casca única da operação O&M da Grid Co. (specs de produto R00 a R13 do Fillipe Figueiró, no SharePoint
`Gridco/4. O&M/6.Gerencial/10. Nexus`). Responsável: Levi Maia. Repositório **PÚBLICO** desde 30/09
(`Grid-Co-CODE/nexus`): nenhum dado pessoal (CPF, telefone, e-mail, endereço), dado de cliente ou de contrato,
print nem segredo em commit. Dado real mora em `dados/` e no armazém local, ambos fora do git.

## Visão: os setores ligados pela base de dados (Levi, 05/10/2026)

"Quero que veja o Nexus como um projeto onde todos os setores se interligam pela base de dados da API; a ideia é unir
informações para conseguirmos fazer previsões e diagnósticos de forma que faça sentido. Sempre vamos focar em
confiabilidade e governança dos dados, não podemos fazer nada nas coxas."
- Todo setor grava e lê pela API de dados (PostgreSQL da T.I., `db_performace`), ligado por ID: o `cadastro_nexus` é a
  chave comum (usina_id, pessoa_id, ...). Nada de JSON como banco, planilha no OneDrive nem Azure. Exceção consciente
  (11/10/2026): quem é administrador pela tela Base → Acessos mora num JSON da pasta de dados, porque é configuração de
  acesso desta instalação, não dado de negócio (`nexus/casca/CLAUDE.md`, seção "Acessos").
- Confiabilidade antes de tela: conferir antes e depois de gravar; número pela metade não vai para a tela (a torre
  Campo · App só sai da moldura com a coleta completa).
- Governança: dado pessoal e sensível vai cifrado (cofre do cadastro); coluna nova em claro na API é revisada antes
  (o endereço da usina foi em claro na 1ª carga do Campo · App, 04/10, e saiu no mesmo dia).

## PRIORIDADE 0: governança e controle de dados (Levi, 05/10/2026)

"Prioridade 0 para a governança e controle de dados"; "precisamos construir e manter uma base sólida para futuras
análises correlacionadas". O modelo é o de **Kimball** (fato com IDs, dimensão única, grão escrito), e mora em
`nexus/dados/` — **leia `nexus/dados/CLAUDE.md` antes de pôr qualquer dado novo no banco** (chamados, engenharia, PCM,
segurança, mais inversores). Em uma linha: fonte nova entra primeiro no catálogo (`nexus/dados/catalogo.py`) com o grão
e as dimensões declarados; o fato vai ao banco com `data_id`, `usina_id`, `pessoa_id`…, nunca com nome em claro nem ID
chutado; a qualidade da ligação é medida e aparece em Base → Governança de dados. **Toda tabela do banco tem dono no
catálogo** (Levi, 09/10/2026: "verifique se aparece a cada tabela nova que aparece!"): o radar da Governança compara o
banco com o catálogo e a tabela nova aparece sozinha, contada no alto do organograma, até virar fato, entrar no `LIVROS`
ou ser declarada em `CONHECIDAS`.

## REGRA: um `.md` por área, sempre em dia (Levi, 03/10/2026)

Toda alteração em qualquer área atualiza o `CLAUDE.md` da pasta dela **no mesmo trabalho**; área sem `CLAUDE.md`
ganha um. É ele que o Claude lê antes de mexer: lendo o `.md` da pasta, não precisa varrer o código (economiza token).
- Escreva o que o código não diz sozinho: para que serve, de onde vem o dado, a regra e o caso real que a criou,
  como provar que funciona. Nada de repetir o código nem de diário de sessão.
- Regra que mudou: **corrija** a linha velha, não acrescente outra ao lado. Curto e atual vale mais que completo.
- Área nova: acrescente na tabela abaixo.

| Área | `.md` |
|---|---|
| Casca, login (Fracttal; a conta Microsoft da Grid, pronta em 14/10/2026 e desligada no servidor até a T.I. pôr as `NEXUS_MS_*`), quem é administrador (Base → Acessos), menu, tema (escuro e claro), servidor local, o endereço (raiz desde a fase 4; o prefixo `/nexus` é a volta), o cookie `nexus_sessao`, as Chaves do Nexus e o Raio-X | `nexus/casca/CLAUDE.md` |
| Torres (como criar tela; a tabela de cada torre, inclusive Chamados, Pessoas e Comando, que ainda são atalho ou placeholder) | `nexus/torres/CLAUDE.md` |
| Base (Registro mestre, Integração Fracttal, Equipamentos das usinas, Chaves das fontes; Acessos na casca, Governança nos dados) | `nexus/cadastro/CLAUDE.md` |
| Relatórios (Central de emissão: os quatro do PCM, o executivo do PCM e os da Performance; o setor de cada relatório) | `nexus/pcm/relatorios/CLAUDE.md`, `nexus/pcm/relatorio_exec/CLAUDE.md` e `nexus/torres/CLAUDE.md` |
| Contratos e clientes (Contestações do cliente, vindas do Dashboard Thopen) | `nexus/torres/contratos/CLAUDE.md` |
| COS | `nexus/torres/cos/CLAUDE.md` |
| Campo · App (modo gerencial do App de Campo) | `nexus/torres/campo/CLAUDE.md` |
| OS Creator embutido | `nexus/torres/oscreator/README.md` |
| Performance (porta única: as telas da Plataforma de Performance numa moldura, com o passe `NEXUS_SSO_CHAVE`, o mapa das telas e a ponte de 04/10 como reserva do Tempo real; Clima e risco, alertas públicos por usina em quatro níveis: Agir agora, Atenção, Acompanhar e Sem alerta; Mapa de risco com camadas de calor e modo TV) | `nexus/performance/CLAUDE.md` e `nexus/torres/performance/CLAUDE.md` |
| PCM (programação semanal: gerar e, desde 09/10/2026, Publicar no App; Quadro da semana com a reprogramação de tarefas e, desde 19/10/2026, o arquivo da semana em curso editável; Gestão PCM, o Plano & Fila das manutenções; Acompanhamento PCM, desde 14/10/2026: MPA, MPS, Radar de Backlog, Mapa e One Page; Técnicos por usina, desde 17/10/2026: quem vê e pode rondar cada usina no App, editado pelo PCM) | `nexus/pcm/CLAUDE.md`, `nexus/pcm/motor/README.md` e `nexus/pcm/acompanhamento/CLAUDE.md` |
| Engenharia (Mesa do engenheiro, a primeira tela desde 18/10/2026: o que me encaminharam, o que está comigo e os críticos sem dono; Confiabilidade dos ativos, pelas OS de falha do Fracttal, com o acompanhamento dos ativos com sinal desde 18/10/2026: pegar, encaminhar, diagnóstico, comentários e os encerrados; Quadro da equipe, com a página da OS desde 24/10/2026: status e prioridade da engenharia, comentários na nota da OS, Solicitar OS com a OS pai e o pulso das paradas) | `nexus/torres/engenharia/CLAUDE.md` |
| Segurança · HSEQ (Mesa da Segurança, desde 24/10/2026, por responsável ou por cliente, com a visão geral: filtros de cliente, UFV e Responsável UFV, a planilha de todas as pendências e o e-mail semanal, que o App de Campo manda; Extintores: por cliente, com o responsável e os técnicos de cada usina, por responsável, o relatório de cada cliente e usina em PDF e Excel, o Status por situação com o filtro, e a Segurança excluindo e editando extintores (o histórico de Excluídos) e pedindo nova ronda da usina; EPI e EPC: as luvas isolantes pela ronda diária, por responsável; APR e PT: as Permissões de trabalho que vieram do Campo, com a PT e a APR) | `nexus/torres/hseq/CLAUDE.md` |
| Cadastro (BD_Operações) | `nexus/cadastro/CLAUDE.md` |
| **Camada de dados: fatos, dimensões, qualidade (PRIORIDADE 0)** | `nexus/dados/CLAUDE.md` |
| **Desempenho (Nexus lento: como ler o Raio-X, as regras de prova, o que já foi corrigido e a fila do chat de desempenho)** | `DESEMPENHO.md` |
| Servidor da T.I. | `DEPLOY.md` |

Desenho da fase atual: `docs/superpowers/specs/2026-09-29-casca-nexus-design.md`; a porta única da Performance (o Nexus
como porta, a plataforma como motor): `docs/superpowers/specs/2026-10-09-performance-no-nexus-design.md`.

## Antes de começar: o estado de verdade (14/10/2026)

O trabalho não acontece só nesta pasta. As sessões trabalham em worktrees (`C:/GridcoAuto/wt/*`,
`C:/GridcoAuto/setores/<setor>/nexus`) e sobem direto à `main`; a pasta aberta pode estar dias atrás. Caso que criou a
regra: em 14/10/2026 esta pasta estava 26 commits atrás do GitHub, e o Clima de 10 a 13/10 existia só no disco dela.
- **Antes de dizer o que existe ou o que falta:** `git fetch`, e olhe `git log origin/main` (não o `main` local),
  `git worktree list` e `git branch --no-merged origin/main` (o que está em andamento noutro ramo).
- **Trabalho solto na pasta:** compare cada arquivo com o `origin/main` antes de commitar; o que outra sessão já subiu
  vence o solto, e o solto que não existe em lugar nenhum é o que precisa de commit.
- **O que está no ar:** `curl -s https://app.gridco.com.br/saude` dá o commit. Produção segue o `origin/main` sozinha: o
  timer `deploy/nexus-atualizar.timer` roda o `deploy/atualizar.sh` a cada 2 min (busca, confere o boot fora da pasta do
  serviço, anda e reinicia; `DEPLOY.md`, seção 8). Push na `main` = produção reiniciada em ~2 min.
- **No Git Bash do Windows o `git` não lê `<(...)`** (substituição de processo): o `git diff --no-index <(...) arquivo`
  sai vazio, e vazio parece "igual". Compare com `cmp`, arquivo temporário ou Python.

## Rodar

```
copie .env.example para .env e preencha
python app.py                 -> http://localhost:5070
python -m pytest -q
```

Sem o `.env` completo o app não sobe, e diz qual variável falta.

**A Performance no PC (10/10/2026).** Com `NEXUS_PLATAFORMA_LOCAL=http://127.0.0.1:5050` e a `NEXUS_PLATAFORMA_URL`
vazia no `.env`, a 5070 junta o Nexus e a plataforma local num endereço só (a mesma divisão do Caddy com o Nexus na raiz,
`app.juntar_com_a_plataforma`), e as 14 telas da Performance abrem em `localhost:5070`. Precisa da MESMA `NEXUS_SSO_CHAVE`
no `.env` do Nexus e no `tokens.txt` da plataforma, e a 5050 no código da porta única. Sem a variável, a 5070 é só o Nexus,
e a moldura diz "configurada em outra origem" (o caso que motivou: o Levi abriu o Tempo real e viu esse aviso).

**Para provar uma mudança, não reinicie a 5070** (é o Nexus que o Levi usa): suba a worktree noutra porta com
`python ferramentas/subir_copia_de_prova.py --porta 5170 --plataforma http://127.0.0.1:5150` (sem carga no banco, sem ler
o Fracttal ao subir; nada sai para SunOp/API PV nem grava fora da máquina; entra-se pela senha de administrador). O que
depende da MESMA origem do servidor (moldura da plataforma, cookies, `postMessage`) se prova com as duas cópias atrás de
`python ferramentas/porta_local.py` (o papel do Caddy: `--modo raiz` é o servidor de hoje, a fase 4; o padrão,
`--modo prefixo`, com a cópia subida com `--prefixo /nexus`, prova a volta, e `--reescrita-do-servidor` imita a camada
que o servidor teve até a fase 4, ver `nexus/casca/CLAUDE.md`; para a moldura da Performance, com
`--plataforma ""` e a mesma `NEXUS_SSO_CHAVE` pelo ambiente nas duas cópias, entrando por um nome `*.localhost` para os
cookies não se misturarem com os da 5050 e da 5070). A cópia da plataforma é a `plataforma/subir_copia_de_prova.py` do
PerformancePainel.

## Como o código está organizado

**Leia o `.md` da área em que for mexer** (tabela acima).

- `nexus/torres/<torre>/__init__.py` — uma pasta por torre. Declara `TORRE` e `bp`; é descoberta sozinha.
  **Para construir uma tela**, crie uma view no `bp` da torre com a mesma rota da tela
  (`@bp.route("/mesa")`); ela vence o placeholder. Templates da torre em `nexus/torres/<torre>/templates/<torre>/`.
- `nexus/torres/oscreator/` — além da torre, traz o **clone do OS Creator Web** (cópia do `oem`) e a ponte
  `/os/*` (`ponte.py`), a única rota fora de `/t/<torre>`. Leia o `README.md` de lá antes de mexer: o clone fica
  idêntico ao do oem de propósito.
- `nexus/auth/` — o portão de login. Toda rota exige sessão, exceto as de `ROTAS_PUBLICAS`.
  Rota pública nova entra ali, conscientemente; o teste `test_toda_rota_nao_publica_exige_login` pega o esquecimento.
- `nexus/casca/` — Início, troca de tema, `/saude`, contexto dos templates (menu, setor, tema). A cadeira saiu em
  12/10/2026: o que cada pessoa vê é o setor dela (`nexus/auth/setor_telas.py`, Base → Acessos; `nexus/casca/CLAUDE.md`).
- `nexus/static/nexus.css` — tokens do Design System Grid Co. nos dois temas (escuro, o padrão, e claro).

## Regras

- **Endereço do Nexus nunca a partir da raiz** (09/10/2026): ele pode rodar debaixo de um prefixo (`NEXUS_PREFIXO`). No
  servidor foi `/nexus` até a fase 4; hoje está na raiz de `app.gridco.com.br`, e o prefixo é a volta. Template
  `{{ raiz }}/...`, `url_for` ou `|na_raiz`; Python `na_raiz()`; JavaScript `nexusRota()` (`nexus/casca/CLAUDE.md`).
- **Origem de dado:** nada de Excel nem OneDrive. Dado vem da API `db_performace` (PostgreSQL da T.I.).
  A API é compartilhada por vários sistemas: nada que identifique pessoa vai para ela em claro
  (cifrado ou como HMAC).
- **Sempre pt-BR**, inclusive comentários. **Sem emoji na interface**; severidade por cor e palavra.
- Tema escuro **navy** (`#090d18` / `#161d30`) + verde Grid, o padrão, que não muda. Nunca lilás (o `#191528` do mockup não
  entra). O claro (08/10/2026) é escolha da pessoa, pelo botão do topo. **Cor só por token**, nos dois temas do
  `nexus.css`: nada de `#hex` ou `rgba()` em regra de CSS nem em template (`nexus/casca/CLAUDE.md`, seção Tema).
- Comentário de código explica **por quê**, de preferência com o caso real que motivou a regra.
- **Nome de colega não entra em arquivo versionado** (o repositório é público; nome de técnico ou supervisor ao lado de
  nota, ronda ou pendência é dado pessoal ligado a desempenho): cite pelo papel ("um técnico", "o supervisor da equipe
  X", "o programador do PCM"); fixture de teste com nome fictício. `tests/test_sem_nomes_no_repositorio.py` monta a
  lista de nomes só na memória (cadastro, App, livro de rondas) e falha com `caminho:linha`. **Ele só roda com o
  `.env`** (sem ele, pula): numa worktree, copie o `.env` antes da suíte (em 18/10/2026 três arquivos com nome passaram
  assim, pelas worktrees sem `.env`). O histórico do git
  anterior a 08/10/2026 ainda tem nomes (não se reescreve).
- **Segredos** só no `.env` (gitignorado). Nunca imprima `NEXUS_SENHA_ADMIN` nem `NEXUS_SECRET_KEY`,
  nunca desligue o portão de login. Para validar tela atrás da senha, faça login por sessão lendo o `.env`.
- Commit só quando pedido. Há deploy automático: push na `main` vai para produção em ~2 min, com restart.
- **Quem sobe o quê:** os administradores (Levi) commitam direto na `main`. O programador do COS entra por pull
  request, e a conferência `pasta-do-cos` só aprova o que mexe na área dele (`nexus/torres/cos/CLAUDE.md`, "Como
  entregar"). Quem obriga é a regra da `main` no GitHub (ruleset "main: pull request e pasta do COS"); mudar a área é
  mexer no `.github/workflows/pasta-do-cos.yml`.
- Antes de dar algo por pronto: testes passando e a tela conferida no navegador (desktop e 375 px).
