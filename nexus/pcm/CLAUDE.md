# CLAUDE.md — PCM (programação semanal e Gestão PCM)

A programação semanal do PCM dentro do Nexus. O desenho e as etapas estão em
`docs/superpowers/specs/2026-09-30-pcm-no-nexus-design.md`; leia antes de mexer. A tela Gestão PCM (acompanhamento das
manutenções) tem seção própria abaixo.

**Regra de ouro:** o sistema atual segue no ar e intocado até o Nexus bater número a número com ele. Isso vale para o
gerador no PC do programador do PCM, o robô do GitHub, o painel pcm.gridco.com.br e o `banco_dados.json` que o App de Campo lê.
**A troca (Levi, 09/10/2026: "semana que vem já quero full nexus sem falta"):** a partir da W43 o Nexus gera E publica.
Gerar continua sendo sombra (não muda nada no campo); a semana só vai ao App pelo **Publicar no App** da rodada (seção
abaixo), um passo à parte, só de administrador, com a tela de conferência. Duas publicações da mesma semana (o PC do PCM
e o Nexus) se atropelam: na semana da troca, o PC do PCM não publica.

**A programação publicada também está no banco (08/10/2026):** o `banco_dados.json` vira o fato
`nexus_programacao · fato_programacao` (1 linha = 1 bloco de agenda), que a carga de hora em hora mantém pela mescla por
semana (o arquivo guarda só 4 semanas); as semanas antigas, desde a W21, vieram do histórico do git do PCM
(`ferramentas/carregar_programacao_historica.py`). Só lê o arquivo do robô, não muda nada desta pasta. Regras, a versão
escolhida de cada semana e os números: `nexus/dados/CLAUDE.md`.

## Os módulos

| Arquivo | O que faz |
|---|---|
| `fonte.py` | lê o `banco_dados.json` do App (a semana que está valendo) e, para a Gestão PCM, o `gestao_pcm.json` e o `mpas.json`; cópia de 5 min e, passado isso, confere pelo ETag (304 = segue a cópia, sem baixar de novo) |
| `gestao.py` | as contas da Gestão PCM (Plano & Fila), transcritas do `js/preventivas.js` do painel |
| `prova_gestao.py` + `.js` | a prova de que a Gestão PCM bate célula a célula com o painel (roda o JS dele no node) |
| `semana.py` | as contas das telas Semana e Tarefas e OS: aderência, horas por equipe, fora da jornada |
| `geracao.py` | roda o motor numa pasta por rodada, num subprocesso, a 1 pedido por segundo ao Fracttal; `gerar_com_foto`, o mesmo com a FOTO do Fracttal e sem credencial (a prova) |
| `insumos.py` | os insumos do motor guardados no Nexus, escritos na rodada no formato que o motor lê |
| `historico_banco.py` | o histórico das programações que o motor lê, montado do `fato_programacao` do banco (desde 08/10/2026); o plano publicado da semana em andamento vem da reserva, do REPOSITÓRIO do PCM ou da pasta do PCM |
| `comparar.py` | compara a semana do Nexus com a oficial (a do PCM), linha a linha; `conferir`: a conferência da semana gerada (dentro da semana, horas por equipe e dia, fora da jornada, repetidas, e `excede_hh_os`: a OS cuja corretiva o motor forçou além das horas do dia) |
| `publicar.py` | **Publicar no App** (09/10/2026): a planilha e as observações da rodada vão para o repositório do PCM, conferidas relendo, e o plano vai para a reserva do histórico |
| `telas.py` | as telas, penduradas na torre PCM (`registrar_pcm(bp)`) |
| `motor/` | **cópia idêntica** do motor do PCM: **não edite** (veja o `README.md` de lá) |

## Insumos: no Nexus, não em arquivo

Prioridades, Confiabilidade, Feriados e Observações (por semana) moram em `insumos.py`; o Histórico sai do BANCO
(`historico_banco.py`, desde 08/10/2026, abaixo). A cada geração, o Nexus escreve os arquivos na pasta da rodada, com a
mesma aba, a mesma linha de cabeçalho e a mesma posição de coluna do original. A AUXILIAR sai do cadastro do Nexus
(`auxiliar.py`, desde 02/10/2026). Da pasta do PCM só vem ainda o `duracoes_aprendidas.json` (sombra: não muda a
agenda).

- **AUXILIAR:** o motor lê seis colunas dela (UFV, RESPONSÁVEL O&M, CIDADE, a 1ª com "MWp", Equipe Cluster, Base
  Equipe). O MWp é a potência contratual. Equipe Cluster fora do padrão "UF Região NN" vai vazia: era uma aba vazia
  por usina com equipe local. Prova da S41 (02/10), com a mesma foto do Fracttal da geração oficial: agenda e pendentes
  idênticos; 48 linhas ganharam Responsável; mudam só as colunas de sombra (RPN novo e Desloc). **RESPONSÁVEL O&M
  sem pessoa** (estrutura de O&M de 10/2026): o BD_Operações traz a REGIÃO onde a vaga de Supervisor de Campo está
  aberta ("NE · Fortaleza-CE e Teresina-PI"); o cadastro guarda a pessoa vazia e a região em `responsavel_om_vaga`, e
  a AUXILIAR escreve a região, como a AUXILIAR do BD escreveria.
- **Provar mudança no motor ou nos insumos: rode com a FOTO do Fracttal**, nunca lendo o Fracttal de novo (horas depois
  a semana muda: S41, 157 tarefas a mais e 280 horários). `python ferramentas/gerar_semana_foto.py --semana 2026-W42
  [--historico banco|nexus] [--rotulo x] [--contra <rodada ou planilha>]` (`geracao.gerar_com_foto`): os mesmos
  insumos da tela; da pasta do PCM (só lida) vêm os caches que o motor gravou ao ler o Fracttal (`.cache_semanal_api.pkl`,
  obrigatório, e `.cache_hist_api.pkl`, `.cache_bd_api.pkl`, `_ativos_classificacao_cache.json`,
  `_usinas_coordenadas_cache.json`), copiados com a idade; TTLs de ~100 anos; credencial VAZIA e o Fracttal numa porta
  fechada (se o motor tentar ler, falha); no fim, a rodada confere o sha da foto ("intacta": o motor regrava o cache
  quando lê). A rodada leva "-foto" no nome e fica fora da lista da tela. Imprime a `comparar.conferir` da semana e o
  que continua da semana anterior. 1ª vez: W42, 09/10 00:16, foto de 08/10 21:46, 10 s.

- **Feriados do ano seguinte (09/10/2026):** a planilha do PCM só tem 2026 e a W53 de 2026 vai de 28/12 a 01/01/2027.
  A rodada escreve, no MESMO arquivo que o motor lê (ele só olha a data), o ano seguinte ao da semana projetado
  (`insumos.com_feriados_ate`): data fixa repetida; Carnaval (-47), Paixão (-2) e Corpus Christi (+60) pela Páscoa do
  ano (`insumos.pascoa`), e o estadual do ES (Nossa Senhora da Penha, Páscoa + 8). Os municipais ficam na data: a
  planilha não diz qual seria móvel. O ano que a planilha já tem não se projeta. 2027: 100 datas (Carnaval 09/02,
  Paixão 26/03, Corpus Christi 27/05, ES 05/04). O carimbo da rodada diz "2027 projetado"; conferir com o calendário
  oficial quando sair.
- **Armazém:** `C:\GridcoAuto\nexus\pcm\insumos.json`, fora do OneDrive, com a versão anterior ao lado. Trocar pela
  API de dados é mexer só em `insumos.py`.
- **Na sombra:** "Importar da pasta do PCM" traz prioridades, confiabilidade, feriados e as observações da semana, para as
  duas semanas partirem do mesmo dado. **"Importar observações do repositório do PCM"** (09/10/2026) traz o
  `Observacoes_Semana.txt` que o PC do PCM ou o painel mandou por último (funciona no servidor); o leitor do Nexus
  entende as 60 linhas do arquivo de 08/10 (49 `@usina`, 3 OS fora, 8 OS com dia fixo, com tarefa, turno e "só:").
  No full Nexus, as observações da semana se escrevem no bloco 2, não no arquivo. **O histórico NÃO** (desde 08/10/2026): o arquivo do PC punha por cima a W41 das
  duas gerações. A tela avisa quando um arquivo da pasta mudou depois da importação.
- **Prova obrigatória** a cada mudança no formato: o que o motor lê do arquivo gerado pelo Nexus tem de ser igual ao
  que ele lia do original, com as mesmas leituras do `programacao_v7.py`. `tests/test_pcm_insumos.py` faz isso com
  dado de mentira (e `tests/test_pcm_historico_banco.py`, para o histórico do banco); com os arquivos reais, rode a
  mesma comparação fora do repositório.

## Histórico das programações: do banco (Levi, 08/10/2026: "PUXE O HISTÓRICO")

O motor lê do `Historico_Programacoes.xlsx` só `task_key` (OS + código do equipamento, SEM a tarefa), `count` e
`weeks`: "Nº vezes programada" = `count + 1`, "Reprogramada" = `count > 0`, o ÚLTIMO desempate da fila
(`programacao_v7` l.2081, depois de tier, aging, sigla e RPN), e 0,75 × `count` no RPN dinâmico (sombra). Uma semana
conta para a chave quando a chave teve bloco na AGENDA dela (o motor não grava as pendentes).

- **De onde:** a geração monta o arquivo do `nexus_programacao · fato_programacao` (GET, `historico_banco.py`), só com as
  semanas ANTES da gerada (gerar de novo a mesma semana não a conta). O banco começa na W21: a W20 do arquivo do PC não
  entra. A chave é a do motor: o `codigo_ativo` do fato é canônico (maiúsculo, sem espaço) e, nas chaves do arquivo do
  PC, igual ao texto do Fracttal; na foto de 08/10, 3 de 6.226 códigos têm espaço ou minúscula, nenhum na agenda nem nas
  pendentes da W42. Código assim programado um dia não acharia o histórico (contaria como 1ª vez).
- **Semana que o banco ainda não fechou** (terminou depois do `atualizacao.gerado_em` do livro): vale o PLANO PUBLICADO
  dela: o da reserva (o Nexus põe lá o que ele publica); senão a `Programação Semana NN.xlsx` do REPOSITÓRIO do PCM (o
  que foi ao App, publicado pelo PC do PCM ou pelo Nexus; funciona no servidor; só vale se o dia da semana bater com o
  dd/mm, porque o nome não tem ano); senão a da pasta do PCM; sem nenhum, a do banco, com aviso. Medido em 09/10 (GET):
  o repositório dá a W40 com 1.109 chaves e a W41 com 1.119, as publicadas. Por quê: no App a semana ATIVA muda toda noite (a "Rolagem" tira da agenda o que não coube no dia e põe nas
  pendentes; Nova OS entra) e o robô só a refaz pelo plano quando ela fecha (W40: 858 chaves em 02/10 19:30, 1.356 às
  22:10). O motor gera a semana N durante a N-1: a N-1 do banco é sempre um retrato do meio dela. A W41 gravada em
  08/10 17:05 tinha 971 chaves contra 1.119 da S41 publicada: 159 de OS canceladas e 247 de OS vivas (229 nas pendentes
  com "Rolagem: sem capacidade").
- **Reserva:** o histórico guardado no Nexus (`insumos.json`; a W41 de lá é a S41 publicada, corrigida em 05/10). Vale se
  o banco não responder (a rodada carimba com aviso) e dá o plano da semana em andamento. Sem banco e sem reserva, não
  gera. `--historico nexus` na ferramenta da foto usa a reserva direto, para comparar.
- **Banco × reserva × arquivo do PC (09/10, histórico da W42):** banco 7.999 chaves (W21-W41), reserva 7.865, PC 7.963.
  Semana fechada no banco = plano publicado menos OS canceladas depois (W36-W39 só diferem disso: 64, 70, 133 e 174
  chaves; a OS cancelada não volta ao Fracttal, não muda geração). O arquivo do PC (e a reserva, que é cópia dele) guarda
  a UNIÃO das gerações (W40: 1.306 contra 799; 142 de outra geração e 365 de OS canceladas; W33: 180 de outra geração;
  W41: 1.286 contra 1.119), não tem a W35 (o banco tem 890 chaves) e tem 377 linhas com `first_week`/`last_week` fora
  de ordem (o motor não os usa). O banco tem 1.189 chaves de Nova OS que o robô deixava na semana fechada até agosto
  (W22-W28, W32, W34, W35).
- **Efeito na W42** (mesma foto, `--historico nexus` × `banco`): agenda e pendentes IGUAIS (924 blocos, 1.246 pendentes,
  todas as colunas); mudam o "Nº vezes programada" em 65 linhas de 64 chaves (por causa, e uma chave pode ter mais de
  uma: +1 pela W35 em 39; -1 por outra geração da W40 em 25, da W33 em 9 e da W27 em 1; W34 -1 em 7 e +1 em 1), a
  "Reprogramada" em 9 (Sim -> Não: OS que só estavam na 1ª geração da W40, que não foi a campo) e o RPN (novo), em
  sombra, em 15. O desempate não mexeu em nenhum horário nesta semana.

## Publicar no App (`publicar.py`, `templates/pcm/publicar.html`, `/t/pcm/gerar/publicar`; 09/10/2026)

O mesmo caminho do PC do PCM (`publicar_semana_github.py` do repositório do PCM): PUT na API de conteúdo do GitHub da
`Programação Semana NN.xlsx` (a `saida/sombra.xlsx` da rodada) e do `Observacoes_Semana.txt` da rodada, na raiz do
repositório (`NEXUS_PCM_REPO`, padrão `fillipefigueiro-source/gridco-pcm-data`, ramo `main`). O push dispara o
`semanal.yml` do PCM na hora (gatilho `Programa*.xlsx` e `Observacoes_Semana*.txt`, sem o descanso de 30 min), que
roda o `atualizacao_semanal.py` e o `gerar_pcm_json.py` e regrava o `banco_dados.json` do App em 5 a 10 min. O robô
escolhe a semana ativa pela data de hoje: a W43 publicada na quinta vira a do App na segunda. Nada muda no App.

- **Não manda** o `Observacoes_Semana_Atual.txt` (os ajustes da semana EM CURSO, gravados pelo painel do PCM): a tela
  mostra o que está lá para a pessoa pedir a limpeza no painel.
- **Barra** (`motivos_para_nao_publicar`): rodada que não terminou bem, rodada com a foto do Fracttal (prova), semana que
  já acabou, rodada sem a conferência da semana (as de antes de 09/10), bloco fora da semana, arquivo que falta.
- **Pede confirmação a mais:** a semana já começou (troca a programação no meio dela); o repositório já tem a planilha
  da semana (mostra quando e por quem foi gravada). Avisa: geração com mais de 24 h (o Fracttal mudou), corretiva
  forçada além das horas do dia (`excede_hh_os`), observações sem nenhuma OS fora ou com dia fixo.
- **Depois:** relê cada arquivo do repositório e compara o sha256 (conferir depois de gravar); grava `publicacao.json`
  na rodada e o `status.json`; põe o plano na reserva do histórico (`insumos.registrar_plano_publicado`: a semana
  publicada de novo troca o plano). A rodada mostra "Publicada no App" e se o `banco_dados.json` já tem a semana.
- **Só administrador** (`session["admin"]`: a senha de admin ou um e-mail de `NEXUS_ADMINS`). O commit não leva o
  e-mail de quem publicou (o repositório é público); quem foi fica no `publicacao.json` da rodada.
- **Token:** `NEXUS_PCM_GITHUB_TOKEN` (ambiente ou `.env` do Nexus; no servidor, um token só deste repositório, com
  escrita de conteúdo). Sem ele, no PC, o login do `gh` da máquina (`gh auth token`). Nunca é impresso.
- **Testar sem publicar:** a tela de confirmação lê o repositório de verdade (só GET). A cópia de conferência do
  Claude troca a sessão do GitHub por uma que recusa gravar. Testes: `tests/test_pcm_publicar.py` (GitHub falso).
- **OS 14331 (W42, 09/10):** 4 corretivas "Teste de comando remoto" de 6 h cada (a duração estimada no Fracttal; o
  total de horas da OS é 1,5 h por tarefa) que o motor forçou numa quarta da PR Norte 01: 24,5 h. O conserto é na
  origem (a duração no Fracttal) ou fixar as tarefas em dias diferentes no bloco 2; a conferência aponta a OS.

## A tela Gerar (`templates/pcm/gerar.html` + `_observacoes.html`, estilo em `static/pcm.css`)

Desde 05/10/2026 (Levi: "está confuso, separe por blocos"), em quatro blocos numerados, na ordem do trabalho: **1** o
que o motor precisa (insumos, em duas colunas, e "Importar da pasta do PCM"), **2** observações da semana (dias por
usina, OS fora, OS com dia fixo), **3** gerar em sombra, **4** últimas gerações. A semana se escolhe uma vez, no topo.

- **Dia de atendimento é verde SUAVE.** Tinta verde clara com texto verde = atende; contorno apagado = não atende.
  Até 05/10 o "atende" sem regra era cinza e a lista parecia desligada ("está tudo cinza"); o verde cheio que entrou
  no lugar, com borda e faixa verdes em toda usina, acendeu a lista inteira ("muito estourado, suavize"). Sem borda
  verde no cartão: a lista já é só de usinas marcadas.
- **A lista mostra só as usinas marcadas** (com dia restrito). As outras ficam na página, escondidas, e entram pelo
  "Adicionar usina" com os cinco dias: desmarcar um dia cria a regra `@usina` (Levi, 05/10: "quero que apareça só o
  que está marcado, o que não estiver só vai aparecer por um botão adicionar"). Usina mexida fica à vista até recarregar.
- **O padrão da semana é a última programação** (`insumos.observacoes_efetivas`). Semana sem nada salvo herda, da
  semana salva mais recente antes dela, só os dias por usina; OS fora e OS com dia fixo não passam. Semana salva,
  mesmo vazia, vale o que foi salvo. É herança de DADO: o `materializar` entrega ao motor o mesmo texto que a tela
  mostra, e a tela avisa "herdados da W41". Antes, a semana nova começava vazia e o PCM refazia as 46 restrições.
- O JavaScript do editor depende dos ids e classes (`#obs`, `#obs-form`, `.obs-ufr`, `.obs-dia`, `#obs-por-dia`,
  `.obs-bloco--usinas`...): a legenda usa `.obs-amostra` de propósito, porque um `.obs-dia` fora de uma regra vira
  clique de edição.
- Ver a tela sem login no navegador: renderize no processo (`test_client` + `session_transaction`, logado) e abra o
  HTML ao lado de uma cópia do `static/`. O Nexus em produção não recarrega template: depois de mudar, reinicie.

## Gestão PCM (`gestao.py`, `templates/pcm/gestao.html`, `/t/pcm/gestao`)

Levi (07/10 e 08/10/2026): "traga a visão de acompanhamento de manutenção do aplicativo para o Nexus conforme prints".
É o bloco **"Manutenções — Plano & Fila"** da aba Gestão PCM do painel do PCM (`js/preventivas.js` do gridco-pcm-data),
com os filtros de cima da aba (Cliente, Usina, Equipe cluster, Responsável; um de cada, sem diferenciar maiúscula). Só
lê: nada vai ao banco nem ao Fracttal. Os controles vão pela URL (`modo`, `tipo`, `dim`, `col`, `val`, `mes`, `q`,
`ordem`/`desc`, `pend`, `ordemf`/`descf`; o drill da fração é `drill` + `dt`, porque `usina` é o filtro de cima).

- **De onde vem:** o `gestao_pcm.json` (as tarefas do Fracttal desde 01/01, que o robô do repositório do PCM regrava;
  14,7 MB e 28,6 mil tarefas em 08/10) e a planilha da Gerencial, o `mpas.json` do mesmo repositório, **cifrado**
  (AES-GCM + PBKDF2; o repositório é público). A Gerencial abre com `NEXUS_PCM_MPAS_SENHA` (a mesma senha que o painel
  pede; quem tem é o dono do painel do PCM, e hoje está vazia), decifrada só em memória.
- **Regra de ouro (do painel):** concluída é o **estado da TAREFA** ("Finalizada"), nunca o status da OS.
- **Plano:** % de tarefas finalizadas por grupo ▸ usina, nos três últimos meses. Preventiva conta no mês da Data
  Programada; demanda (corretiva, emergencial, religamento com o remoto, inspeção, preditiva, administrativa, zeladoria,
  handover) no mês da **criação**; "Teste" e preventiva sem sigla ficam fora. **MPA e MPS em fração** feitas/total (50%
  de 4 anuais não é 50% de 200 mensais), e a fração abre a Fila daquela usina. Geral = as quatro preventivas (as
  Corretivas ficam fora). Faixas: abaixo de 40% vermelho, 40% a 99% amarelo, 100% verde.
- **Fila:** o envelhecimento das MPA e MPS. Com a Gerencial: Prevista × Programada, atraso pela Prevista (1–30, 31–90,
  mais de 90 dias), criticidade, última observação datada do log, e os KPIs são filtros. **Sem a chave** é o lado do
  Fracttal (uma linha por OS, atraso pela Programada) e a tela diz isso numa nota informativa, não num aviso: falta de
  chave não é falha. Chave que não abre ou arquivo fora do ar é falha, e vai em amarelo.
- **Par do topo** (nunca média única): Rotina (MPM + MPT do mês corrente), grandes atrasadas e a mais antiga, críticas
  sem data futura. Sem a Gerencial, as atrasadas e as concluídas do lado do Fracttal (o painel só mostra o cadeado).
- **Diferenças de propósito com o painel:** a OS sem "#"; o "hoje" em Brasília (o painel usa o dia UTC para
  "atrasada": entre 21h e meia-noite ele já conta o dia seguinte); e a hora do "atualizado em" em Brasília (o robô
  grava o `geradoEm` em UTC sem fuso e o painel o mostra como hora local: 12:42 lá é 09:42 aqui). Dois defeitos do
  painel que o Nexus não copia (revisão de 08/10): a dica "sem preventiva no período" nas células de grupo e do TOTAL,
  que têm tarefa (aqui ficam sem dica), e o cabeçalho Tipo da Fila, que lá não ordena nada (aqui ordena pelo tipo).
- **Fila: ordem do Atraso** é a do painel: a 1ª ordem (seta para cima) já põe a MAIS VELHA no alto
  (`?modo=fila&pend=atraso&ordemf=atraso`); `descf=1` inverte e põe a mais nova primeiro.

**A prova** (rode a cada mudança no `gestao.py` ou no `preventivas.js` do painel; precisa do node):

```
python -m nexus.pcm.prova_gestao                      # JS e JSON do repositório do PCM
python -m nexus.pcm.prova_gestao --painel C:/caminho/gridco-pcm-data --dados gestao_pcm.json
```

Roda o próprio `preventivas.js` (mais o recorte do `app.js` que ele usa) num `vm` isolado do node, contra o mesmo JSON,
com o relógio dos dois lados parado no mesmo instante, e compara linha, célula, faixa, fração e dica do mouse (Plano),
linhas na ordem, colunas e KPIs (Fila) e o par do topo: 178 casos sem a Gerencial e 178 com. Sem a senha, a Gerencial
da prova é **sintética** (feita das OS de MPA/MPS do JSON, com todos os casos da regra): prova a transcrição; os números
reais da Fila com a Gerencial só se provam com a senha. Nunca imprime nome de pessoa.
- **08/10/2026:** gestao_pcm.json de 08/10 12:42 (28.641 tarefas), `preventivas.js` sha256 `1ff54695d5a5`: 448.575
  valores comparados, **0 divergências**. Ela achou duas diferenças, já corrigidas: o navegador lê 30/02 como 02/03 (o
  Python recusava a data) e o KPI "concluídas" (`pend=concl`), que a URL descartava. Mudar a faixa de 40% para 41%
  dá 3 divergências: a prova pega. Depois da revisão (dica do grupo e ordem por Tipo, acima), rodada de novo com o
  mesmo JSON e o mesmo JS: 356 casos, 429.055 valores, **0 divergências** (150 s; sem a ordem "tipo", que é diferença
  de propósito).

**Desempenho** (08/10, `test_client`, JSON do GitHub, quatro rodadas): fria 1,3 a 2,5 s, conforme a rede (baixar
~0,9 s ou mais + `json.loads` 0,32 s + contas ~0,1 s); quente 6 a 33 ms; um filtro de cima novo, 110 a 190 ms na primeira
vez; a conferência de 5 em 5 minutos, com o 304 do GitHub, 34 a 73 ms (antes do ETag, os mesmos 1,3 s da fria). Com
`NEXUS_PCM_GESTAO_FONTE` num arquivo LOCAL não há cópia em memória: cada clique relê os 14,7 MB (~0,4 s), então medir
com arquivo local não diz nada do servidor. As contas ficam guardadas pela versão do arquivo (`dataHash`) e pelos
filtros de cima (`telas._G_CACHE`); a Fila, por meio dia (o atraso conta do meio-dia). Versão nova do arquivo limpa
tudo da velha: cada uma prende ~49 MB de tarefas.

**Não veio (a aba Gestão PCM do painel tem mais blocos; esperam o Levi dizer se eram os dos prints):** os KPIs do topo
da aba (Visíveis, Finalizadas, Em aberto, Atrasadas), a árvore Cliente ▸ Usina ▸ Tipo das tarefas (com "Não
finalizadas no período" e a lista "Só atrasadas"), "Confiabilidade por ativo" (MTBF, MTTR, disponibilidade, do
`confiabilidade.json`), "Tempo médio de reparo por Equipe Cluster" e o Relatório Executivo. Dos filtros de cima, não
vieram Tipo, Etiqueta, Estado, OS, Solicitação e Período.

## Armadilhas já vividas

- **Gerar duas vezes a mesma semana distorcia tudo:** na S40, 415 tarefas viraram reprogramadas, e todas ganharam +1
  no "Nº vezes". Por isso a rodada parte do histórico de **antes** da semana (`historico_banco.montar`: só as semanas
  anteriores; na reserva, `geracao.preparar_historico`).
- **O arquivo de histórico do PC não é registro do que foi a campo:** guarda toda geração (a S41 de 02/10 08:26, que
  nunca foi ao campo, está lá), perdeu a W35 inteira e não se corrige sozinho. Daí o histórico vir do banco.
- **Cota do Fracttal:** 200 pedidos por minuto para a **empresa inteira**, divididos com o App de Campo. O motor anda
  a 1 por segundo, e a tela pede confirmação no horário de campo (seg a sex, das 06h às 18h).
- **Dois Fracttal no mesmo processo se quebram:** o `FRACTTAL_BASE_URL` do motor tem `/api/` e o do OS Creator não.
  Por isso o motor roda em subprocesso, com ambiente próprio e sem as variáveis `NEXUS_*`.
