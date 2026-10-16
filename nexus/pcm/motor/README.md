# Motor da programação semanal (cópia)

Estes quatro arquivos são uma cópia **idêntica** do motor do PCM, tirada do repositório
`fillipefigueiro-source/gridco-pcm-data` no commit `6215ceb` (16/10/2026, a carga de 70%; antes, `fdad64e` de 16/10,
`bd4f673` e `fd39672` de 15/10, `3ce6205` de 09/10 e `8ee58d9` de 30/09):

| Arquivo | O que faz |
|---|---|
| `programacao_v7.py` | o gerador (motor v9): escolhe, ordena e distribui as tarefas da semana |
| `fonte_bd_api.py` | lê as ordens e tarefas do Fracttal |
| `gerar_bd_via_api.py` | lê as ordens e tarefas do Fracttal |
| `fora_da_programacao.py` | lê o `Fora_da_programacao.json` do Nexus (16/10/2026): o que fica fora da programação |

Conferido pelo hash (SHA-256 da cópia com CRLF):

| Arquivo | Hash |
|---|---|
| `programacao_v7.py` | `8f8d807ffe3b…` |
| `fonte_bd_api.py` | `b81d2c394d67…` |
| `gerar_bd_via_api.py` | `6c580738ab5e…` |
| `fora_da_programacao.py` | `91f9a81140c0…` |

## Por que uma cópia, e não um motor novo

O Nexus precisa gerar a **mesma** semana que o PCM gera, para a comparação linha a linha provar que pode
substituir. Reescrever o motor tornaria a comparação inútil.

**Não edite estes arquivos.** Mudança de regra entra no repositório do PCM e é copiada de novo. Enquanto os dois
sistemas rodarem juntos, as duas cópias precisam ser iguais.

## O que mudou em 16/10/2026 (`6215ceb`): carga máxima do dia a 70%

Levi, 16/10/2026: "carga máxima no programador de sexta de 70% HH por dia". `CARGA_MAX_DIA = 0.70` no
`programacao_v7.py`: o dia útil (`USEFUL_DAY_MIN`) e o dia com MPA (`MPA_DAY_USEFUL_MIN`) passam de 80% para 70% das
8,8 h líquidas (422 → 369 min, 7 → 6,15 h por equipe e dia), da W44 em diante; a janela da noite segue em 80%. A
conferência do Nexus (`comparar.py`) usa a mesma conta, presa por teste. No mesmo commit, só no robô do PCM (que o
Nexus não copia): a tarefa de sexta não muda mais de dia (rolagem desligada, cascata da OS nova só no mesmo dia).

## O que mudou em 16/10/2026 (`fdad64e`): fora da programação pelo Nexus

Levi, 16/10/2026: os motivos das tarefas (o que "tira da programação": Aguardando Material, Aguardando Cliente...) e
"Quando a OS estiver atrelada como responsável para alguém do time de backoffice, desconsiderar para a programação da
semana". O Nexus grava o `Fora_da_programacao.json` (`nexus/pcm/motivos.py`) na pasta da rodada e na raiz do repositório
do PCM; o `fora_da_programacao.py` lê com a mesma regra do Nexus (OS, código do ativo e nome; a marca do ativo vence a da
OS; o backoffice pelo nome sem acento e sem caixa: o teste de contrato do Nexus roda este arquivo).

- **No motor** (`programacao_v7.py`, junto das OS "não" das observações): a tarefa com motivo que tira e a OS do
  backoffice saem da lista antes de montar a semana, também as fixadas nas observações; o log diz quantas
  (`[FORA DA PROGRAMAÇÃO]`). Sem o arquivo, nada muda.
- **No robô** (`atualizacao_semanal.py`, fora desta cópia): o STEP A2 não inclui como OS nova; o STEP A3b apaga da
  semana em curso (agenda e `_Pendentes`) a tarefa com motivo que tira; a OS do backoffice já na semana fica. O
  `gerar_pcm_json.py` manda o `codigo` da pendente.
- **Prova** (W43, a mesma foto): sem marcas, agenda e pendentes idênticas às do motor `bd4f673` (1.629 e 736, coluna a
  coluna); com 3 marcas que tiram, 1 que não tira e os 11 nomes do backoffice, saíram as 3 tarefas e as 33 tarefas de 33
  OS do backoffice, e a que não tira ficou. No robô, na planilha real da W42: o A3b tirou exatamente as 4 linhas
  marcadas. Detalhe no `nexus/pcm/CLAUDE.md`, seção dos motivos.

## O que mudou em 15/10/2026 (`fd39672` e `bd4f673`)

Levi, 15/10/2026: "as tarefas estão vindo com horas previstas para a mesma quantidade de horas da OS. Por exemplo, a
OS 15596 de Elias Fausto, a OS toda tem 25 Horas, porém por tarefa está somando 25 horas por tarefa [...] O mesmo está
acontecendo com a OS 14331" e "gostaria que o tipo zeladoria só puxasse quando o tipo de tarefa fosse de fato
zeladoria, não só pelo nome".

- **Duração da TAREFA, não da OS** (`fonte_bd_api._duracao_da_tarefa`, aplicada no `df_semanal`, também no cache): a
  view `work_orders` do Fracttal devolve em `duration` a duração da OS repetida em cada tarefa (o defeito que o
  `enriquecer_com_duracoes_subtarefas` corrige pelo RPC, que pede o JWT e não roda no `df_semanal`). Nas OS de mais de
  uma tarefa, a duração passa a ser a da tarefa (`tasks_duration`, a coluna "Total de Horas"); sem ela, a da OS
  dividida pelas tarefas. OS de uma tarefa não muda (em 113 o Fracttal guarda na tarefa outro valor, para os dois
  lados). No retrato de 14/10: 15596 = 43 tarefas que somam 25 h (antes 1.075 h); 14331 = 4 × 1,5 h (antes 4 × 6 h);
  tarefas abertas 176.427 h → 13.189 h.
- **A hora da tarefa vale para todo tipo, também nas MPx** (`estimate_h`, `bd4f673`; Levi: "Tem que ser de acordo
  com nova regra"): as horas fixas por sigla da calibração de 31/07 (MPM 1,1 h, MPA 4 h...) só valem para a tarefa
  sem duração no Fracttal (`_estimate_h_sem_fracttal`), e saiu o piso de 1 h das preventivas; o teto de 8 h continua.
  Antes, a 15596 saía com 43 × 4 h = 172 h; agora 25 h, a da OS. No Fracttal a MPM típica tem 10 min (a calibração
  dizia 1,1 h pela execução real): se o campo levar mais que o plano, o conserto é no plano do Fracttal.
- **Zeladoria pelo TIPO** (`programacao_v7.is_zeladoria`, que agora recebe o "Tipo de tarefa"): pelo nome,
  "limpeza" pegava corretiva ("Corretiva - Limpeza de ventoinha de inversor": 82 abertas) e "roça" sem acento casava
  com "troca" e "Sorocaba": das 186 tarefas abertas que o nome marcava, 150 não eram do tipo Zeladoria (113
  corretivas). Zeladoria vai paralela na segunda, fora da capacidade da equipe; o resto agora ocupa a equipe.
- **Prova** (`ferramentas/gerar_semana_foto.py`, W43, a mesma foto de 14/10 15:06 com o motor antes e depois): o maior
  dia de uma equipe caiu de 24,2 h para 10,3 h; a 14331 de 24 h (4 tarefas na segunda) para 6 h; zeladoria
  terceirizada de 31 para 18 linhas; agenda 1.622 h → 1.598 h. Com a hora da tarefa também nas MPx (`bd4f673`, a
  mesma foto): a 15596 cabe inteira (43 tarefas na agenda, 25 h; antes 10 na agenda e 33 pendentes); agenda 1.052 →
  1.586 linhas e 1.598 → 1.133 h; pendentes 2.255 → 651 h; dias acima da capacidade 11 → 8. Testes:
  `tests/test_pcm_motor_regras.py`.
- **No robô do PCM** (`atualizacao_semanal.py`, a cada 15 min, fora desta cópia): OS nova com duração implausível
  (vazia ou acima de 8 h) usa a fixa da sigla, como a promoção de pendentes já fazia; a mesma tarefa deslocada de novo
  só atualiza o motivo na `_Pendentes`, sem linha nova (na W42 a 15596 chegou a 660 pendentes, 480 do mesmo inversor,
  15 mil horas) (`fd39672`); e o STEP A2 (OS nova) não reincorpora o que o `Observacoes_Semana_Atual.txt` tira ("não" e
  "sem:"): o A3 apaga, mas roda depois, e a cada rodada a OS tirada voltava e deslocava o que estivesse no horário (às
  12:24 a 15596 deslocou 19 tarefas e mandou 9 para as pendentes) (`bd4f673`). A 1ª rodada com o `fd39672` (12:24) deixou
  a W42 do App com 1.516 h de pendentes (eram 20.955 h) e 15 linhas de 8 h ou mais (eram 695).

## Como o Nexus roda (`nexus/pcm/geracao.py`)

- **Processo:** um subprocesso com o mesmo Python do Nexus.
- **Pasta de trabalho:** uma por rodada, em `C:\GridcoAuto\nexus\pcm\geracoes\`, fora do OneDrive. Leva os insumos do
  Nexus, a AUXILIAR do cadastro, o histórico de antes da semana, tirado do banco (`historico_banco.py`), e o
  `Fora_da_programacao.json` (os motivos e o backoffice, do banco: `motivos.materializar`).
- **Ambiente próprio:**
  - a credencial do Fracttal, a mesma do OS Creator, sem login;
  - `FRACTTAL_BASE_URL` com `/api/`;
  - 1 pedido por segundo;
  - nenhuma variável `NEXUS_*`.
- **Com a foto** (`geracao.gerar_com_foto`, `ferramentas/gerar_semana_foto.py`): os caches que o motor gravou na pasta
  do PCM vão para a rodada, os TTLs (`PROG_API_TTL_MIN`, `PROG_HIST_TTL_H`, `GESTAO_ATIVOS_TTL_H`) ficam em ~100 anos, a
  credencial vai VAZIA (o `carregar_env` do `gerar_bd_via_api` usa `setdefault`: a variável vazia também barra um
  `.env` achado no caminho) e o `FRACTTAL_BASE_URL` aponta para uma porta fechada. O motor lê a foto; se tentar o
  Fracttal, falha.
- **Saída:** a planilha fica em `saida/sombra.xlsx` e é comparada com a `Programação Semana NN.xlsx` oficial.
- **Conferido em 16/10/2026:** sem o CR do Windows, os quatro arquivos são iguais aos do repositório do PCM no commit
  `6215ceb` (16/10). O hash da tabela acima é o da cópia com CRLF.
- **O que mudou em `3ce6205` (09/10/2026):** a W42 do PC do PCM quebrou na quinta (08/10 21:46, `ValueError: cannot
  convert float NaN to integer` no RPN dinâmico): a AUXILIAR atualizada naquele dia tinha 67 usinas sem MWp, e o motor
  guardava o vazio como NaN. O motor passou a ler o porte da coluna `POTÊNCIA CONTRATUAL (MWp)` (vazio e zero não
  entram) e o responsável da coluna `Gestor de Contrato` (o RESPONSÁVEL O&M virou a região da vaga). A AUXILIAR do
  Nexus (`auxiliar.py`) escreve as duas colunas.
