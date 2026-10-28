# A tarefa como chave e o executado no banco (PCM) — desenho (27/10/2026)

Origem: a ronda de dados do PCM de 27/10/2026 (números medidos no banco às 23:15, só leitura). O Levi escolheu "Chave da
tarefa e executado": é o que destrava o planejado × executado × motivo × peça, a base das previsões e diagnósticos que a
visão do Nexus pede. Regras da casa: `nexus/dados/CLAUDE.md` (Kimball, catálogo antes, só acrescenta, número pela metade
não grava).

## 1. O problema, com os números de 27/10

- **Não há uma chave da tarefa comum aos fatos.** O id da tarefa no Fracttal (`fracttal_tarefa_id`) só existe no
  `fato_tarefa_os`. Os outros cruzam pela trinca OS + código do ativo + `tarefa_chave`, que repete (2 trincas, 8 linhas no
  `fato_tarefa_os`), com a OS em texto num fato e inteiro no outro e o código canônico num e cru no outro.
- **O executado quase não está no banco.** A tarefa finalizada no Fracttal não é fato (o `fato_tarefa_os` guarda as
  abertas e só a zeladoria feita em 90 dias). O `fato_fechamento` do App é trocado inteiro pela janela de 90 dias: o que
  passa dela some. Na programação, 76% dos blocos com a tarefa finalizada estão sem data de fim, e só 50 a 54% das
  tarefas finalizadas acham o fechamento do App.
- **A peça lançada não diz o ativo** (16 de 16 sem o código): cruza só por OS + tarefa.
- **A pessoa da programação liga pelo nome** (técnico 63,8%, responsável 78,2%), embora o id do Fracttal da pessoa já
  exista no Nexus (`nexus_setores`).

## 2. Decisões

1. **A chave da tarefa é o `fracttal_tarefa_id`.** Todo fato de tarefa ganha a coluna, no FIM do cabeçalho (o BI e os
   leitores leem por posição), com a linhagem `tarefa_ligada_por`: `fracttal` (veio do próprio Fracttal), `os+ativo+tarefa`
   (busca que achou exatamente uma tarefa) ou vazio (não achou, ou achou mais de uma: nunca escolher, regra 4).
2. **Cruzar só por ID.** Nenhuma coluna existente muda de tipo nem de nome (só acrescentar). Quem cruza usa
   `fracttal_tarefa_id` ou `equipamento_id`, nunca o texto da OS ou do código.
3. **O executado do Fracttal vira fato**, numa família de livros por mês da data de fim:
   `nexus_os_finalizadas_AAAA_MM · fato_tarefa_finalizada`.
   - **Grão:** 1 linha = 1 finalização de 1 tarefa no Fracttal. Transação: só acrescenta; a tarefa reaberta e finalizada de
     novo é outra linha, e vale a última de cada `fracttal_tarefa_id`.
   - **Colunas:** as do `fato_tarefa_os` (IDs, datas por papel, tipo, `equipamento_id`, `usina_id` com a linhagem,
     `do_backoffice`), `data_id_fim` obrigatório, a pessoa que executou (`pessoa_id` pelo id do Fracttal, decisão 6) e as
     medidas que o REST trouxer, conferidas no ensaio (nenhuma coluna de medida entra sem o dado medido antes).
   - **Leitura:** no mesmo publicador do `fato_tarefa_os` (`nexus/campo/tarefas_os.py`), que já lê o REST de hora em hora
     com a espera do limite de 200/min. Acrescenta a leitura incremental das finalizadas (status 3, todo tipo), da data de
     fim mais nova já gravada menos 2 dias de margem (a ordem do REST é só aproximada), parando quando uma página INTEIRA
     passa do piso: a técnica da zeladoria. Custo esperado: 1 a 3 páginas por hora, a confirmar no ensaio.
   - **Carga inicial:** uma vez, desde 01/01/2026, fora do horário de campo, a 1 pedido por segundo, com o ensaio antes
     (páginas, linhas, % ligado) e a gravação só depois de você ver os números.
4. **O fechamento do App deixa de se apagar.** A carga mescla como a programação já faz: troca as linhas da janela do App
   e mantém as mais velhas. É o "passo 0" adiado em 08/10, agora pedido. A trava `so_cresce` passa a valer para a aba.
5. **Programação, fechamento, motivos e peças ganham o `fracttal_tarefa_id`** pela busca da trinca (OS, `equipamento_id`,
   `tarefa_chave`) nas tarefas abertas e finalizadas. A peça herda o ativo da tarefa achada. A qualidade de cada fato passa
   a medir o % ligado à tarefa.
6. **A pessoa pelo Fracttal.** Na programação, além do nome do cadastro, o nome da pessoa no Fracttal leva ao id do
   Fracttal e, por ele, ao `pessoa_id` (`nexus_setores`), com a linhagem `pessoa_ligada_por`. O mesmo id liga quem
   executou a tarefa finalizada. O % de antes e de depois vai no relatório da carga.

## 3. Fases

1. **Fato das finalizadas:** catálogo e `explica.py` antes; o ensaio sem gravar; a carga inicial; a gravação de hora em
   hora. Prova: `tests/test_dados_tarefa_finalizada.py`, com o REST falso: leitura incompleta não grava, página repetida,
   limite de 200/min e a margem de 2 dias.
2. **A chave nos quatro fatos** (`fracttal_tarefa_id` + `tarefa_ligada_por`) e o % na qualidade. Prova: a busca única
   liga e a ambígua fica vazia.
3. **O fechamento permanente** (mescla + `so_cresce`). Prova: a linha que sai da janela do App fica.
4. **A pessoa pelo Fracttal** na programação.
5. **O primeiro uso:** a aderência ao plano por semana (planejado × executado × motivo), numa tela que você escolher.

Cada fase é um commit, com a suíte passando e o ensaio no banco de verdade antes de ligar a gravação.

## 4. Governança e riscos

- **Cota do Fracttal:** a leitura incremental custa 1 a 3 páginas por hora, dentro do laço que já existe. A carga inicial
  roda uma vez, de noite. Nada novo bate no Fracttal fora desse laço.
- **Nada pela metade:** leitura incompleta, total menor que o informado pelo REST ou página repetida não gravam (as regras
  do `tarefas_os.py`).
- **Pessoa:** só `pessoa_id` e HMAC, nunca nome nem e-mail (regra 8).
- **O App não manda o código do ativo da peça.** O Nexus herda o ativo da tarefa (decisão 5). Se você quiser o código
  vindo do próprio App, o pedido vai para a sessão do App de Campo.

## 5. Fora deste desenho

- Mudar tipo ou nome de coluna que já existe.
- As telas do PCM passarem a ler os fatos em vez dos JSON do robô (vem depois, tela a tela).
- O backlog no tempo (uma foto diária das tarefas abertas) e o plano publicado congelado por semana: o próximo passo,
  depois deste.
