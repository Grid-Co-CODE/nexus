# Motor da programação semanal (cópia)

Estes três arquivos são uma cópia do motor do PCM, tirada do repositório `fillipefigueiro-source/gridco-pcm-data`
no commit `3ce6205` (09/10/2026 09:09; antes, `8ee58d9` de 30/09), **com as duas correções de 15/10/2026** (seção
abaixo), que ainda esperam subir no repositório do PCM:

| Arquivo | O que faz |
|---|---|
| `programacao_v7.py` | o gerador (motor v9): escolhe, ordena e distribui as tarefas da semana |
| `fonte_bd_api.py` | lê as ordens e tarefas do Fracttal |
| `gerar_bd_via_api.py` | lê as ordens e tarefas do Fracttal |

Conferido pelo hash (SHA-256):

| Arquivo | Hash |
|---|---|
| `programacao_v7.py` | `2da686620987…` (no `3ce6205`: `af884da8319c…`) |
| `fonte_bd_api.py` | `b81d2c394d67…` (no `3ce6205`: `d8fb8806b1e8…`) |
| `gerar_bd_via_api.py` | `6c580738ab5e…` |

## Por que uma cópia, e não um motor novo

O Nexus precisa gerar a **mesma** semana que o PCM gera, para a comparação linha a linha provar que pode
substituir. Reescrever o motor tornaria a comparação inútil.

**Não edite estes arquivos.** Mudança de regra entra no repositório do PCM e é copiada de novo. Enquanto os dois
sistemas rodarem juntos, as duas cópias precisam ser iguais. A exceção é a de 15/10/2026 (abaixo): o Nexus gera a
semana desde a W43, e o conserto não podia esperar; a mesma mudança está pronta para o repositório do PCM.

## As correções de 15/10/2026 (aqui; no repositório do PCM, ainda não)

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
  tarefas abertas 176.427 h → 13.189 h. No motor isso vale para o que não é MPx: as MPx seguem com as horas fixas da
  calibração do PCM (`estimate_h`: MPM 1,1 h, MPA 4 h por tarefa), então a 15596 sai com 43 × 4 h no motor.
- **Zeladoria pelo TIPO** (`programacao_v7.is_zeladoria`, que agora recebe o "Tipo de tarefa"): pelo nome,
  "limpeza" pegava corretiva ("Corretiva - Limpeza de ventoinha de inversor": 82 abertas) e "roça" sem acento casava
  com "troca" e "Sorocaba": das 186 tarefas abertas que o nome marcava, 150 não eram do tipo Zeladoria (113
  corretivas). Zeladoria vai paralela na segunda, fora da capacidade da equipe; o resto agora ocupa a equipe.
- **Prova** (`ferramentas/gerar_semana_foto.py`, W43, a mesma foto de 14/10 15:06 com o motor antes e depois): o maior
  dia de uma equipe caiu de 24,2 h para 10,3 h; a 14331 de 24 h (4 tarefas na segunda) para 6 h; zeladoria
  terceirizada de 31 para 18 linhas; agenda 1.622 h → 1.598 h. Testes: `tests/test_pcm_motor_regras.py`.
- **Falta no repositório do PCM**, onde roda o robô (`atualizacao_semanal.py`, a cada 15 min): as duas mudanças acima
  e duas do robô: OS nova com duração implausível (vazia ou acima de 8 h) usa a fixa da sigla, como a promoção de
  pendentes já faz; e a mesma tarefa deslocada de novo só atualiza o motivo na `_Pendentes`, sem linha nova (na W42 a
  15596 chegou a 660 pendentes, 480 do mesmo inversor, 15 mil horas: a linha deslocada fica na aba da equipe e volta a
  ser deslocada a cada OS nova). Até subir lá, o robô ainda põe a duração da OS em cada tarefa de OS nova. Quando
  subir, confira: sem o CR do Windows, os três arquivos daqui iguais aos de lá.

## Como o Nexus roda (`nexus/pcm/geracao.py`)

- **Processo:** um subprocesso com o mesmo Python do Nexus.
- **Pasta de trabalho:** uma por rodada, em `C:\GridcoAuto\nexus\pcm\geracoes\`, fora do OneDrive. Leva os insumos do
  Nexus, a AUXILIAR do cadastro e o histórico de antes da semana, tirado do banco (`historico_banco.py`).
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
- **Conferido em 09/10/2026:** sem o CR do Windows, os três arquivos são iguais aos do repositório do PCM no commit
  `3ce6205` (09/10 09:09). O hash da tabela acima é o da cópia com CRLF.
- **O que mudou em `3ce6205` (09/10/2026):** a W42 do PC do PCM quebrou na quinta (08/10 21:46, `ValueError: cannot
  convert float NaN to integer` no RPN dinâmico): a AUXILIAR atualizada naquele dia tinha 67 usinas sem MWp, e o motor
  guardava o vazio como NaN. O motor passou a ler o porte da coluna `POTÊNCIA CONTRATUAL (MWp)` (vazio e zero não
  entram) e o responsável da coluna `Gestor de Contrato` (o RESPONSÁVEL O&M virou a região da vaga). A AUXILIAR do
  Nexus (`auxiliar.py`) escreve as duas colunas.
