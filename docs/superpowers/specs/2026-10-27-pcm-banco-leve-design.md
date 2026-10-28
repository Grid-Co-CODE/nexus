# O banco mais leve para o PCM — desenho (27/10/2026)

Origem: a ronda de dados do PCM de 27/10/2026. O Levi escolheu "Desempenho do banco". A API do banco (`db_performace`)
mora na mesma máquina do Nexus, só lê por página (`limit` e `offset`, sem filtro do lado do servidor) e só grava trocando o
livro inteiro (`sync-xlsx?replace=true`). O desenho não depende de a API mudar.

## 1. O problema, com os números

- **A programação é um livro só, e cresce ~1.000 linhas por semana** (17.344 linhas em 27/10, W21 a W44). Em cada hora em
  que o arquivo do robô mudou (quase toda hora útil), a carga lê o fato inteiro, mescla, regrava o livro inteiro e relê
  tudo para conferir: ~2 leituras e 1 gravação completas para trocar 4 semanas.
- **Ler "a semana atual" depende da ordem física das linhas** (as 4 semanas do arquivo vão para o fim). Técnicos por usina e
  a Visão do responsável leem do fim por isso.
- **Cada leitor do PCM lista o banco sozinho** (`/api/sheets`, ~0,5 s e 95 KB) e lê as páginas uma depois da outra, sem o
  teto de leituras que o Campo usa (`_VAGAS_BANCO`) e com uma conexão nova a cada vez. O Almoxarifado frio chega a ~20
  listagens em série.
- **Caches que vencem sem o dado mudar:** o do Acompanhamento é chaveado pelo `lido_em` da curadoria, que se renova a cada
  2 min. Os relatórios do PCM recalculam as ~28 mil tarefas a cada folha.

## 2. Decisões

1. **Um leitor comum do banco** (`nexus/dados/livros.py`):
   - uma listagem por processo, reaproveitada por 60 s;
   - uma sessão HTTP reaproveitada;
   - as páginas em paralelo, com o teto de 6 leituras simultâneas (o `_VAGAS_BANCO` do Campo passa a morar aqui, um só
     para o Nexus inteiro).
   Os leitores do PCM passam a usá-lo: motivos, atribuições, curadoria, inventário, `historico_banco`, Técnicos por usina e
   Almoxarifado. A conferência de sempre continua: as linhas lidas batem com o `row_count` da listagem, senão a leitura
   falha.
2. **Caches pela versão do conteúdo.**
   - Acompanhamento: chave pelo sha das linhas da curadoria, não pelo `lido_em`.
   - Relatórios: a folha guardada pela versão dos arquivos (`dataHash` e `baixado_em`).
   - Motivos: a decifragem das marcas vigentes guardada pela versão do livro.
3. **A programação em livros por mês:** a família `nexus_programacao_AAAA_MM`, pelo mês da segunda-feira da semana.
   - A carga regrava só os meses das 4 semanas do arquivo (1 ou 2 livros, ~4 mil linhas) e relê só eles.
   - As semanas antigas nunca mais são regravadas, o que também as protege do arquivo degradado.
   - "A semana atual" passa a ser o livro do mês, sem depender da ordem das linhas.
   - **Migração sem desfazer nada:** o livro de hoje, `nexus_programacao`, fica como está (a API não apaga livro) e é
     declarado congelado no catálogo. A 1ª vez divide o histórico nos livros de mês, conferido semana a semana (contagem
     e sha) antes de a carga trocar de livro. Os leitores (`historico_banco`, Técnicos por usina, a Visão do responsável,
     a prévia da Governança) passam a ler a família.
4. **Pedido à T.I., sem depender dele:** filtro por coluna na leitura de linhas da API (por exemplo, a semana). Com ele,
   ler uma semana deixa de baixar um mês.

## 3. Medir antes e depois

No Raio-X e no relatório da carga:
- Técnicos por usina fria (hoje 3,3 s);
- o POST do Gerar (hoje ~4 s só de leitura do fato);
- o tempo da carga das :40;
- o Almoxarifado frio;
- as listagens por minuto.

Cada fase só fica se o número melhorar.

## 4. Fases

1. **O leitor comum**, com o menor risco e o ganho imediato.
2. **Os caches pela versão do conteúdo.**
3. **A programação por mês:** o ensaio da divisão (contagem e sha por semana), a gravação dos meses, a troca da carga e
   dos leitores, e o livro antigo congelado no catálogo.

Cada fase é um commit, com a suíte passando e a tela conferida (desktop e 375 px) onde ela muda.

## 5. Fora deste desenho

- As telas do PCM deixarem os JSON do robô.
- Outros fatos grandes (geração, ronda) por mês: o mesmo molde, depois, se os números pedirem.
