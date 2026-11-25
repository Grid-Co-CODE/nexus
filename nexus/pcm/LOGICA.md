# A lógica da programação semanal e da confiabilidade do PCM

Pedido da reunião do PCM de 24/11/2026: "um .md com toda a lógica de confiabilidade e programação semanal", para o
agendamento viver no Nexus e parar de depender de script em PC. Aqui está o que acontece, em que ordem, quem roda, e o
que ainda depende de alguém. O detalhe de cada peça está no `CLAUDE.md` desta pasta, no `motor/README.md`, em
`relatorio_exec/CLAUDE.md`, em `relatorios/CLAUDE.md` e em `nexus/engenharia/confiabilidade.py`.

## 1. Quem roda o quê, e quando

| O quê | Onde roda | Quando | Sai |
|---|---|---|---|
| Robô semanal (`semanal.yml` do repositório do PCM) | GitHub Actions | acorda a cada 15 min, roda com 30 min de descanso; na hora, quando a semana é publicada | `banco_dados.json` (a semana do App) e `etiquetas.json` |
| Confiabilidade (passo do robô semanal, desde 24/11/2026) | GitHub Actions | 1x por dia (UTC), pelo cache que o robô acabou de ler | `confiabilidade.json` |
| Robô da Gestão PCM (`gestao-pcm.yml`) | GitHub Actions | a cada 15 min, com descanso | `gestao_pcm.json` (as tarefas do ano, com a marca `bo`), `engenharia.json` |
| Durações aprendidas (`duracoes.yml`) | GitHub Actions | sexta 08:00 UTC, antes da geração | `duracoes_aprendidas.json` |
| Gerar a semana e Publicar no App | Nexus (PCM → Gerar a semana) | quando o PCM manda; desde a W43 é o Nexus que gera e publica | a rodada; a `Programação Semana NN.xlsx` e as observações no repositório do PCM |
| Relatórios do PCM no Nexus | Nexus (Relatórios → Central de emissão) | diário 06:00, tarde 13:00, fechamento sexta 17:00, alerta ao publicar; executivo sob demanda | as folhas |
| Conferência das cópias (`copias_pcm.py`) | Nexus | a cada 6 h | o aviso nas telas quando o motor ou o executivo daqui ficam diferentes dos do PCM |
| Controle Semanal (`controle_semanal.py`, a planilha com as observações do time) | **PC do PCM** | todo dia 06:00 e sexta 12:00 | `PCM_Controle_Semanal_GridCo.xlsx` no OneDrive |

O Fracttal é lido só pelos robôs (cota de 200 pedidos por minuto para a empresa inteira, dividida com o App de Campo).
O Nexus lê os JSON publicados (cópia de 5 min) e o próprio banco.

## 2. A programação semanal (o motor, `motor/programacao_v7.py`)

O motor é o do PCM, copiado sem mudança no Nexus; a regra nova entra no repositório do PCM e é copiada.

**Entradas:** as tarefas abertas do Fracttal; a Lista de Prioridades (o RPN de cada atividade); a Planilha de
Confiabilidade; a AUXILIAR do cadastro (equipe, cluster, responsável de cada usina); os feriados; as observações da
semana (pins, `sem:`, `só:`); o histórico das semanas; o Fora da programação (os motivos e o backoffice, ambos editados
no Nexus); as durações aprendidas.

**Quais tarefas entram na semana:**
- a Data Programada de segunda a sexta da semana;
- as vencidas "Em processo" das 2 semanas anteriores (carry-over) e as paradas há 10 a 60 dias (aging);
- a fila de reprogramação: as vencidas com sigla de preventiva (MPA, MPS sempre; MPM só no mês da semana), corretivas e
  inspeções;
- as OS pinadas nas observações, com qualquer data;
- ficam fora: religamentos, as OS do backoffice, as tarefas com motivo que tira da programação.

**A ordem na fila de cada usina:** religamento, corretiva emergencial, corretiva, inspeção/preditiva, preventivas
(MPA > MPS > MPT > MPM > MPQ), administrativas e handover; dentro do grupo, a idade, o RPN e a reprogramada. Na última
semana do mês a MPM do mês sobe.

**Os dias:**
1. zeladoria: na segunda, em paralelo;
2. MPA: na janela noturna (15:30 a 01:30), uma OS por noite;
3. o resto: a usina ganha dias pela carga em horas; depois os pins das observações (no dia pedido; a OS de bloco se
   espalha pelos dias permitidos e, se não couber, entra forçada com [EXCEDE HH]); depois a **coleta de dados de
   geração, no dia da Data Programada e nunca antes** (24/11/2026; dia cheio, forçada; feriado, o próximo dia útil;
   sem dia útil depois da data, a próxima semana); depois a fila normal; por fim o preenchimento dos dias livres;
4. a corretiva respeita 70% do dia; o que não cabe vira pendência, com o motivo.

**Saída:** uma aba por equipe (dia, hora, OS, tarefa, marcação), as pendências com o motivo e a aba `_Qualidade`.
O Nexus confere a rodada contra a semana oficial (`comparar.py`) e só manda ao App pelo Publicar.

## 3. As marcas que os relatórios leem

Regra (24/11/2026): toda mudança na programação vira MARCA no dado, que todos os relatórios leem, nunca conta solta num
relatório só.
- `foraDoPlano` (linha da semana): o que não estava no plano. Desde 16/11/2026 a preventiva fora da planilha sai com
  `false` e `prevForaPlanilha: true`: preventiva conta sempre no plano (ela vem do PCM 52 Semanas).
- `bo` (tarefa da Gestão PCM): a OS cujo responsável é do backoffice, pela lista do Nexus. Sai de todos os relatórios.
- o status da tarefa (Finalizada, Verificação): o executado.

## 4. A confiabilidade (duas contas, para dois usos)

**A do Relatório Executivo** (`confiabilidade.json`, `gerar_confiabilidade_json.py` do PCM), o método do Power BI, por
ativo, desde 20/10/2025, com as falhas Corretiva, Corretiva Emergencial, Religamento e Religamento Remoto:
- MTBF = (horas desde a mobilização da usina − horas paradas) ÷ número de falhas;
- MTTR = média por falha, do incidente ao fim (dias × 24 até 1 dia; dias × 12 acima: 12 h de sol por dia);
- disponibilidade = MTBF ÷ (MTBF + MTTR);
- a mobilização vem da AUXILIAR; sem data, 20/10/2025.

Ficou parada de 08/10 a 23/11/2026, porque quem a publicava era um script num PC. Desde 24/11 está no robô semanal,
uma vez por dia.

**A da Engenharia e da Gestão PCM no Nexus** (`nexus/engenharia/confiabilidade.py`): as mesmas regras, lidas das OS
de falha do Fracttal pelo Nexus. Duas diferenças de propósito:
- o ativo é o código (com a usina), e não o nome; no PCM, 318 nomes se repetem entre usinas e herdavam o MTBF de outra;
- a OS cancelada não entra.

Os sinais dos 30 dias (crítico, atenção, monitorar) são só dela. Ela é viva: atualiza sozinha.

## 5. O que ainda depende de pessoa ou de PC

- **O Controle Semanal** (`controle_semanal.py`) roda num PC e grava a planilha no OneDrive, com a coluna "Observações
  do time". Para sair do PC: virar uma tela do Nexus com as mesmas abas, e as observações no banco. A reunião pediu
  usar a planilha como base de ideias para os insights do PCM.
- **O e-mail manual de atualização da confiabilidade** pode parar quando o passo diário estiver no ar, conferido pelo
  `geradoEm` do `confiabilidade.json`.
- **A Gerencial (`mpas.json`)** continua sem publicador automático.
