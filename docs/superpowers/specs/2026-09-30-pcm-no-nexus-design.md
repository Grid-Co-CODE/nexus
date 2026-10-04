# Programação semanal do PCM no Nexus

**Pedido do Levi (30/09/2026):** "quero passar toda a programação semanal e autonomia para o projeto nexus [...] não
derruba a atual, quando eu ver que está funcional a gente substitui completamente."

**Estrutura** (a mesma aprovada em 30/09 para o PCM, igual ao cadastro):

| Pasta | O que tem |
|---|---|
| `nexus/pcm/` | a regra, sem Flask |
| `nexus/pcm/telas.py` | as telas, penduradas na torre PCM |
| `nexus/templates/pcm/` + `nexus/static/pcm.css` | o layout |

**Regra de ouro:** o sistema atual segue no ar e intocado até o Nexus bater número a número. Isso vale para o
gerador no PC do Fabrício, o robô do GitHub, o painel pcm.gridco.com.br e o `banco_dados.json` que o App de Campo lê.

## Etapas

1. **Ler a semana que está valendo — FEITA em 30/09.**
   - As telas Semana e Tarefas e OS leem o mesmo `banco_dados.json` do App (`fonte.py`, cópia de 5 min, aviso se cair).
   - O que a tela mostra:
     - aderência;
     - horas por equipe e dia contra a capacidade de 7 h, com a MPA à parte na janela da noite;
     - pendentes, reprogramadas e OS novas;
     - tarefas fora da jornada: 264 de 1.373 na semana 40.
   - Só leitura.
2. **Gerar a semana no Nexus, em sombra — FEITA em 30/09, esperando a credencial.**
   - O motor atual vem para `nexus/pcm/motor/` como cópia idêntica, do mesmo jeito que o OS Creator. São 3
     arquivos, do commit `8ee58d9`, conferidos pelo hash.
   - `geracao.py` roda o motor num subprocesso, numa pasta por rodada em `C:\GridcoAuto\nexus\pcm\geracoes\`:
     - com cópia dos insumos da pasta do PCM;
     - com o histórico de antes da semana, o que resolve o "tudo reprogramado" da 2ª geração;
     - a 1 pedido por segundo;
     - com o ambiente próprio.
   - A tela "Gerar a semana" mostra o que falta, a rodada, o log e a comparação linha a linha com a semana do
     Fabrício (`comparar.py`).
   - Credencial: a do OS Creator, sem login (decisão do Levi). Basta o `.env` dele em
     `nexus/torres/oscreator/os_creator/.env`, que o git ignora.
3. **Ajustes no Nexus — 1ª fatia FEITA em 30/09 (`insumos.py`).**
   - Prioridades, Confiabilidade, Histórico, Feriados e Observações moram no Nexus (armazém local em
     `C:\GridcoAuto\nexus\pcm\insumos.json`, com a versão anterior ao lado; a API de dados vem depois, só neste módulo).
   - A cada geração o Nexus escreve os cinco arquivos na pasta da rodada, no formato exato do motor. Da pasta do PCM
     só vêm a AUXILIAR e as durações aprendidas.
   - Na sombra, "Importar da pasta do PCM" traz os arquivos do Fabrício; a tela avisa quando um deles muda depois.
   - Observações por semana, editáveis na tela "Gerar a semana".
   - Prova com os arquivos REAIS: o que o motor lê do arquivo gerado pelo Nexus é igual ao original (38 prioridades,
     15 categorias, 7.301 tarefas do histórico, 12 + 16 + 46 feriados, 57 observações com o nº da linha).
   - Falta: telas de edição para Feriados, Prioridades e Confiabilidade (hoje se edita importando de novo).
   Plano original desta etapa:
   - Fixar dia, tirar OS, "só:" e "sem:", com a gramática de hoje, guardados no Nexus em vez do arquivo de texto.
   - O histórico passa a morar no Nexus, na API de dados, cifrado onde tiver pessoa (decisão do Levi).
   - Lista de Prioridades e Planilha Confiabilidade viram cadastro no Nexus. O mockup está em
     https://claude.ai/artifact/8iep7XvZBcoLV48zP6qLv3.
4. **Cadastro direto.**
   - O motor lê as usinas do cadastro do Nexus (a base original do BD_Operações), casando pelo CÓDIGO, e a AUXILIAR
     sai.
   - Medido na semana 40: sem responsável eram 297 linhas, e passam a 79.
   - **1ª fatia FEITA em 02/10:** o Nexus escreve a AUXILIAR a partir do cadastro (`auxiliar.py`), no formato que o
     motor lê, sem mexer no motor. S41 com a mesma foto do Fracttal: idêntica à oficial; 48 linhas ganharam
     Responsável. Falta o casamento pelo CÓDIGO (pede mudança no motor).
5. **Autonomia e troca.**
   - O Nexus no servidor, gerando sozinho na quinta e atualizando durante a semana.
   - Ele publica um `banco_dados.json` no mesmo formato.
   - O App troca o `PROG_URL` por configuração (v200), e o painel antigo sai.

## Decisões do Levi (30/09)

1. **Fracttal:** a credencial do OS Creator, a mesma lógica sem a parte de login.
   - Falta só copiar o `.env` dele para a pasta do clone.
2. **Servidor:** terá. Primeiro a montagem.
3. **Prioridades e Confiabilidade:** viram cadastro no Nexus. Veja o mockup.
4. **Estado da programação:** API de dados.
5. **Fabrício:** continua gerando no PC por enquanto.

## Riscos conhecidos

- **pandas 3:** o motor nunca rodou com o pandas 3.0.3 desta máquina, que se saiba. A primeira rodada de verdade
  mostra.
- **Cota do Fracttal:** o motor lê o Fracttal inteiro. A tela pede confirmação no horário de campo (seg a sex, das
  06h às 18h).
