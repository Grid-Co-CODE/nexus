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
  chave comum (usina_id, pessoa_id, ...). Nada de JSON como banco, planilha no OneDrive nem Azure.
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
| Casca, login, menu, tema (escuro e claro), servidor local, o prefixo `/nexus` e o cookie `nexus_sessao` | `nexus/casca/CLAUDE.md` |
| Torres (como criar tela) | `nexus/torres/CLAUDE.md` |
| COS | `nexus/torres/cos/CLAUDE.md` |
| Campo · App (modo gerencial do App de Campo) | `nexus/torres/campo/CLAUDE.md` |
| OS Creator embutido | `nexus/torres/oscreator/README.md` |
| Performance (porta única: as telas da Plataforma de Performance numa moldura, com o passe `NEXUS_SSO_CHAVE`, o mapa das telas e a ponte de 04/10 como reserva do Tempo real; Clima e risco, alertas públicos por usina; Mapa de risco com camadas de calor e modo TV) | `nexus/performance/CLAUDE.md` e `nexus/torres/performance/CLAUDE.md` |
| PCM (programação semanal: gerar e, desde 09/10/2026, Publicar no App; Quadro da semana com a reprogramação de tarefas; Gestão PCM, o Plano & Fila das manutenções) | `nexus/pcm/CLAUDE.md` e `nexus/pcm/motor/README.md` |
| Engenharia (Confiabilidade dos ativos, pelas OS de falha do Fracttal) | `nexus/torres/engenharia/CLAUDE.md` |
| Segurança · HSEQ (Extintores: por usina e dia, por supervisor e o relatório em PDF; EPI e EPC: as luvas isolantes pela ronda diária; APR e PT: as Permissões de trabalho que vieram do Campo, com a PT e a APR) | `nexus/torres/hseq/CLAUDE.md` |
| Cadastro (BD_Operações) | `nexus/cadastro/CLAUDE.md` |
| **Camada de dados: fatos, dimensões, qualidade (PRIORIDADE 0)** | `nexus/dados/CLAUDE.md` |
| Servidor da T.I. | `DEPLOY.md` |

Desenho da fase atual: `docs/superpowers/specs/2026-09-29-casca-nexus-design.md`.

## Rodar

```
copie .env.example para .env e preencha
python app.py                 -> http://localhost:5070
python -m pytest -q
```

Sem o `.env` completo o app não sobe, e diz qual variável falta.

**A Performance no PC (10/10/2026).** Com `NEXUS_PLATAFORMA_LOCAL=http://127.0.0.1:5050` e a `NEXUS_PLATAFORMA_URL`
vazia no `.env`, a 5070 junta o Nexus e a plataforma local num endereço só (a mesma divisão do Caddy com o Nexus na raiz,
`app.juntar_com_a_plataforma`), e as 13 telas da Performance abrem em `localhost:5070`. Precisa da MESMA `NEXUS_SSO_CHAVE`
no `.env` do Nexus e no `tokens.txt` da plataforma, e a 5050 no código da porta única. Sem a variável, a 5070 é só o Nexus,
e a moldura diz "configurada em outra origem" (o caso que motivou: o Levi abriu o Tempo real e viu esse aviso).

**Para provar uma mudança, não reinicie a 5070** (é o Nexus que o Levi usa): suba a worktree noutra porta com
`python ferramentas/subir_copia_de_prova.py --porta 5170 --plataforma http://127.0.0.1:5150` (sem carga no banco, sem ler
o Fracttal ao subir; nada sai para SunOp/API PV nem grava fora da máquina; entra-se pela senha de administrador). O que
depende da MESMA origem do servidor (moldura da plataforma, cookies, `postMessage`) se prova com as duas cópias atrás de
`python ferramentas/porta_local.py` (o papel do Caddy: Nexus em `/nexus`, plataforma na raiz; `--modo raiz` é a fase 4;
`--reescrita-do-servidor` imita a camada que o servidor tem hoje, ver `nexus/casca/CLAUDE.md`; para o Nexus se ver
debaixo do `/nexus` como no servidor, suba a cópia com `--prefixo /nexus`; para a moldura da Performance, com
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
- `nexus/cadeiras.py` — catálogo de cadeiras. Cadeira nova no fim; id publicado nunca muda.
- `nexus/casca/` — Início, troca de cadeira e de tema, `/saude`, contexto dos templates (menu, tema).
- `nexus/static/nexus.css` — tokens do Design System Grid Co. nos dois temas (escuro, o padrão, e claro).

## Regras

- **Endereço do Nexus nunca a partir da raiz** (09/10/2026): no servidor ele mora em `/nexus` (`NEXUS_PREFIXO`). Template
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
  lista de nomes só na memória (cadastro, App, livro de rondas) e falha com `caminho:linha`. O histórico do git
  anterior a 08/10/2026 ainda tem nomes (não se reescreve).
- **Segredos** só no `.env` (gitignorado). Nunca imprima `NEXUS_SENHA_ADMIN` nem `NEXUS_SECRET_KEY`,
  nunca desligue o portão de login. Para validar tela atrás da senha, faça login por sessão lendo o `.env`.
- Commit só quando pedido. Quando houver deploy automático, push na `main` vai para produção.
- **Quem sobe o quê:** os administradores (Levi) commitam direto na `main`. O programador do COS entra por pull
  request, e a conferência `pasta-do-cos` só aprova o que mexe na área dele (`nexus/torres/cos/CLAUDE.md`, "Como
  entregar"). Quem obriga é a regra da `main` no GitHub (ruleset "main: pull request e pasta do COS"); mudar a área é
  mexer no `.github/workflows/pasta-do-cos.yml`.
- Antes de dar algo por pronto: testes passando e a tela conferida no navegador (desktop e 375 px).
