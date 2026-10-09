# Motor da programação semanal (cópia)

Estes três arquivos são uma cópia **idêntica** do motor do PCM, tirada do repositório `fillipefigueiro-source/gridco-pcm-data`
no commit `3ce6205` (09/10/2026 09:09; antes, `8ee58d9` de 30/09):

| Arquivo | O que faz |
|---|---|
| `programacao_v7.py` | o gerador (motor v9): escolhe, ordena e distribui as tarefas da semana |
| `fonte_bd_api.py` | lê as ordens e tarefas do Fracttal |
| `gerar_bd_via_api.py` | lê as ordens e tarefas do Fracttal |

Conferido pelo hash (SHA-256):

| Arquivo | Hash |
|---|---|
| `programacao_v7.py` | `af884da8319c…` |
| `fonte_bd_api.py` | `d8fb8806b1e8…` |
| `gerar_bd_via_api.py` | `6c580738ab5e…` |

## Por que uma cópia, e não um motor novo

O Nexus precisa gerar a **mesma** semana que o PCM gera, para a comparação linha a linha provar que pode
substituir. Reescrever o motor tornaria a comparação inútil.

**Não edite estes arquivos.** Mudança de regra entra no repositório do PCM e é copiada de novo. Enquanto os dois
sistemas rodarem juntos, as duas cópias precisam ser iguais.

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
