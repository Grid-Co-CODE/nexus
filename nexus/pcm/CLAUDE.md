# CLAUDE.md — PCM (programação semanal e Gestão PCM)

A programação semanal do PCM dentro do Nexus. O desenho e as etapas estão em
`docs/superpowers/specs/2026-09-30-pcm-no-nexus-design.md`; leia antes de mexer. A tela Gestão PCM (acompanhamento das
manutenções) tem seção própria abaixo.

**Regra de ouro:** o sistema atual segue no ar e intocado até o Nexus bater número a número com ele. Isso vale para o
gerador no PC do Fabrício, o robô do GitHub, o painel pcm.gridco.com.br e o `banco_dados.json` que o App de Campo lê.
Até a troca, tudo aqui é **sombra**: nada é publicado.

## Os módulos

| Arquivo | O que faz |
|---|---|
| `fonte.py` | lê o `banco_dados.json` do App (a semana que está valendo) e, para a Gestão PCM, o `gestao_pcm.json` e o `mpas.json`; cópia de 5 min e, passado isso, confere pelo ETag (304 = segue a cópia, sem baixar de novo) |
| `gestao.py` | as contas da Gestão PCM (Plano & Fila), transcritas do `js/preventivas.js` do painel |
| `prova_gestao.py` + `.js` | a prova de que a Gestão PCM bate célula a célula com o painel (roda o JS dele no node) |
| `semana.py` | as contas das telas Semana e Tarefas e OS: aderência, horas por equipe, fora da jornada |
| `geracao.py` | roda o motor numa pasta por rodada, num subprocesso, a 1 pedido por segundo ao Fracttal |
| `insumos.py` | os insumos do motor guardados no Nexus, escritos na rodada no formato que o motor lê |
| `comparar.py` | compara a semana do Nexus com a do Fabrício, linha a linha |
| `telas.py` | as telas, penduradas na torre PCM (`registrar_pcm(bp)`) |
| `motor/` | **cópia idêntica** do motor do PCM: **não edite** (veja o `README.md` de lá) |

## Insumos: no Nexus, não em arquivo

Prioridades, Confiabilidade, Histórico, Feriados e Observações (por semana) moram em `insumos.py`. A cada geração, o
Nexus escreve os arquivos na pasta da rodada, com a mesma aba, a mesma linha de cabeçalho e a mesma posição de coluna
do original. A AUXILIAR sai do cadastro do Nexus (`auxiliar.py`, desde 02/10/2026). Da pasta do PCM só vem ainda o
`duracoes_aprendidas.json` (sombra: não muda a agenda).

- **AUXILIAR:** o motor lê seis colunas dela (UFV, RESPONSÁVEL O&M, CIDADE, a 1ª com "MWp", Equipe Cluster, Base
  Equipe). O MWp é a potência contratual. Equipe Cluster fora do padrão "UF Região NN" vai vazia: era uma aba vazia
  por usina com equipe local. Prova da S41 (02/10), com a mesma foto do Fracttal da geração oficial: agenda e pendentes
  idênticos; 48 linhas ganharam Responsável; mudam só as colunas de sombra (RPN novo e Desloc).
- **Provar mudança no motor ou nos insumos:** rode com a FOTO do Fracttal da pasta do PCM (`.cache_semanal_api.pkl`,
  `.cache_hist_api.pkl`, `_ativos_classificacao_cache.json`, `_usinas_coordenadas_cache.json`, TTLs altos, sem
  credencial). Ler o Fracttal horas depois muda a semana (S41: 157 tarefas a mais e 280 horários) e não prova nada.

- **Armazém:** `C:\GridcoAuto\nexus\pcm\insumos.json`, fora do OneDrive, com a versão anterior ao lado. Trocar pela
  API de dados é mexer só em `insumos.py`.
- **Na sombra:** "Importar da pasta do PCM" traz os arquivos do Fabrício antes de gerar, para as duas semanas partirem
  do mesmo dado. A tela avisa quando um arquivo dele mudou depois da importação.
- **Prova obrigatória** a cada mudança no formato: o que o motor lê do arquivo gerado pelo Nexus tem de ser igual ao
  que ele lia do original, com as mesmas leituras do `programacao_v7.py`. `tests/test_pcm_insumos.py` faz isso com
  dado de mentira; com os arquivos reais, rode a mesma comparação fora do repositório.

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
  no "Nº vezes". Por isso a rodada parte do histórico de **antes** da semana (`geracao.preparar_historico`).
- **Cota do Fracttal:** 200 pedidos por minuto para a **empresa inteira**, divididos com o App de Campo. O motor anda
  a 1 por segundo, e a tela pede confirmação no horário de campo (seg a sex, das 06h às 18h).
- **Dois Fracttal no mesmo processo se quebram:** o `FRACTTAL_BASE_URL` do motor tem `/api/` e o do OS Creator não.
  Por isso o motor roda em subprocesso, com ambiente próprio e sem as variáveis `NEXUS_*`.
