# CLAUDE.md — Contratos e clientes (as regras; a torre saiu do menu)

**A torre "Contratos e clientes" saiu do menu em 12/11/2026** (Levi: "Outro ponto, contratos e clientes. Joga o acesso
cliente lá para bases, contestações, você vai jogar para o comando, prévia visão do contrato, você vai jogar no comando
[...] Essa parte de contrato e clientes aqui vai sumir, vai ser absorvido por outras seções"). O que era dela:

| Tela | Onde está | View e template |
|---|---|---|
| **Contestações** (13/10/2026) | Comando, `/t/comando/contestacoes` | `nexus/torres/comando/contestacoes_tela.py`, `comando/contestacoes.html` e `_contestacao_card.html` |
| **Contratos** (a Prévia: visão do contrato de 12/11/2026; editável desde 18/11/2026) | Comando, `/t/comando/contratos`, de todos (o endereço `/t/comando/visao-do-contrato` leva a ele) | `nexus/torres/comando/contratos_tela.py`, `comando/contratos.html`, `static/contratos.js` e `contratos.css` |
| **Acessos dos clientes** (14/10/2026) | Base → Acessos, a aba "Acessos do cliente" (`/t/base/acessos-clientes`, desde 13/11/2026 fora do menu; as outras abas de Acessos são outra coisa: o que cada setor do Nexus vê) | `nexus/torres/base/acessos_clientes_tela.py`, `nexus/templates/acessos_dos_clientes.html` |
| Clientes, Onboarding de cliente, Comunicação por cliente, Portal do cliente | saíram: eram só o aviso de "em construção" | — |

- **As regras não mudaram de lugar**: esta pasta (`contestacoes.py`, `tratamento.py`, `acessos_clientes.py`) e este
  arquivo, que veio de `nexus/torres/contratos/`.
- **O endereço antigo não vira 404**: `nexus/torres/contratos/__init__.py` ficou só com um `bp` (sem `TORRE`: não entra no
  menu, no Início nem na lista de telas dos setores) que responde 308 para a tela nova, com o resto do caminho e o
  filtro (`?setor=`); 308 e não 302 para o formulário de uma aba aberta no endereço antigo ainda gravar. A tela sem
  sucessora leva ao Início.
- **A marca do setor vale na tela nova** (`setor_telas.RENOMEADAS`: `contratos/contestacoes` → `comando/contestacoes`,
  `contratos/previa` e `comando/visao-do-contrato` → `comando/contratos`, `contratos/acessos` → `base/acessos-clientes`): ninguém perdeu o que
  via, e o banco não foi regravado. O portão por setor deixa o endereço antigo passar (`setor_telas.TORRES_EXTINTAS`);
  quem decide é a tela de destino.
- Prova: `tests/test_contratos_torre_saiu.py`. O menu passou de 14 para 13 torres.

## Comando › Contratos: editável, com histórico (18/11/2026; `edicao.py`)

Era a **Prévia: visão do contrato** (12/11/2026): um mockup numa moldura, que passou a mostrar a planilha de controle
(16/11) e as fichas dos PDFs (18/11), as duas subidas por campos de importação. Levi, 18/11/2026: "Tire essas opções de
subir arquivos. Primeiro que o arquivo JSON você mesmo criou [...] Eu quero que essas informações sejam editáveis [...]
Só gestores de contrato ou administradores podem editar, e tudo com histórico. Nesse histórico deve ter quem mudou, o
que mudou, quando mudou, o motivo porque mudou, anexar alguma coisa [...] um e-mail, uma mensagem, algo" e "deixar muita
informação em cima [...] rouba metade do espaço da tela [...] Arrume isso". Escolhas dele no mesmo dia: o anexo é
OBRIGATÓRIO (arquivo ou o texto colado), o administrador liga o gestor a uma pessoa, tudo é editável, o nome é Contratos.

- **Sem importação.** As duas importações saíram da tela. O que tinha sido importado (`contratos/controle_obrigacoes.json`
  e `contratos/fichas_contratos.json` na pasta de dados) é a **carga inicial**, e não muda mais; daí em diante tudo muda
  na própria tela. Cada coisa editável é um ITEM com id fixo tirado da carga: `cliente` (os dados do contrato da
  planilha), `contrato` (cada PDF lido), `regra`, `obrigacao`, `adicional` e `parametros` (as metas da Cadastros).
- **O registro.** Livro `nexus_contratos_edicoes` · `fato_edicao_contrato` (no catálogo antes da 1ª gravação; só
  acrescenta). 1 linha = 1 mudança de 1 item (incluir, alterar, retirar). O estado de agora = a carga + as mudanças na
  ordem. Retirar esconde o item; a história fica. O conteúdo (o que era, o que ficou, o motivo, a prova, quem) vai só
  CIFRADO (Cofre); os arquivos da prova no disco do servidor (`contratos_edicoes/<id>/`). A mesma mudança em vários
  itens (a regra igual nos seis contratos da 2C) é um lote: uma linha por item, a prova guardada uma vez, e uma entrada
  no histórico.
- **Mais PDFs depois (18/11/2026 à tarde).** O Levi mandou os PDFs de mais clientes depois que a importação saiu da
  tela. As fichas novas entram por um caminho interno do administrador, sem botão na tela
  (`POST /t/comando/contratos/carga-fichas`, `edicao.juntar_fichas`): cliente novo entra na carga; cliente que já tinha
  ficha é trocado só se ninguém editou um contrato lido ou uma regra dele (a troca muda os ids). A data de cada cliente
  fica em `por_cliente`, e a história diz quando os PDFs dele foram lidos.
- **Quem edita.** O administrador, e o gestor do contrato daquele cliente: a pessoa ligada pelo administrador (Editar
  dados → Gestor do contrato) ou, enquanto ninguém escolheu, a ÚNICA pessoa com setor cujo nome é igual ao da planilha
  (nunca se chuta). Trocar o gestor e as metas é só do administrador. A página só mostra o lápis para quem pode, e o
  servidor confere de novo (`edicao.pode_editar`).
- **O que é obrigatório.** Motivo (5 caracteres ou mais) e prova: o arquivo (PDF, imagem, .eml, .msg, .doc(x), .xlsx,
  .txt; até 5 arquivos, 10 MB cada, o conteúdo tem de bater com a extensão) ou o texto colado do e-mail ou da mensagem.
  "Nada mudou" também não grava.
- **A tela.** O topo é UMA linha (a troca de contrato é o título; o gestor e o Editar dados na mesma linha), a linha de
  fatos é curta, o atraso é um chip, e não há título repetido, linha de "de onde vêm os dados" nem rodapé. As abas:
  Regras (as categorias, com Incluir regra, e os Dados do contrato no fim), **Pontos** (seção abaixo), Calendário,
  Atendimento, Entregáveis, Metas, Financeiro, **Histórico** e **Indicadores** (seção abaixo) (quem, quando, o que era e o que ficou, o motivo e a prova; a carga inicial no
  fim). A linha editada leva a marca "editado" (quem e quando no título).
- **O retorno da gestora que pediu a visão do contrato (chamada de 18/11/2026; Levi escolheu: comenta quem vê o contrato; prioridade e comentário
  sem prova, só quem e quando; recorrências sugeridas e o gestor confirma; Atendimento e Histórico depois dos exemplos de
  relatório dela):**
  - **Prioritárias:** a estrela do gestor (campo `prioritaria` da regra, sem prova) põe a regra no alto das Regras;
    "Prioritárias" é a 2ª opção do controle.
  - **O que se repete vira um item:** dentro da categoria, as regras de um mesmo tema (expurgo, multa, exclusão,
    disponibilidade; 2 ou mais) ficam num subgrupo recolhido (`tema` no JS). O atributo é `data-subgrupo`: o `data-tema`
    é o do tema claro/escuro no `<html>` e pegava todo clique.
  - **Comentário na regra** (pedido da área de Contratos): item `comentario`, de quem vê o contrato, sem prova; sai só pelo autor ou
    pelo administrador; a linha mostra quantos.
  - **Calendário:** item `recorrencia` (semanal com o dia da semana; mensal no Nº dia útil ou no dia do mês; trimestral,
    semestral e anual a partir de um mês), com os feriados nacionais no dia útil. As **sugeridas** saem das regras com
    frequência escrita; "Confirmar" grava com a regra como prova (o servidor tira o trecho) e "descartar" grava um
    `descarte`. Cada data tem o **check de entregue** (item `entrega`, sem prova). O mês anda (‹ ›).
  - **Entregáveis:** o código do contrato (MPLP.3, MPCP.1, P52S) vira etiqueta depois do nome; as regras se dividem em
    Recorrentes e Entrega única.
  - **Financeiro mês a mês:** a mensalidade do contrato, os adicionais do mês, e os `lancamento` do gestor (acréscimo,
    penalidade, desconto; com motivo e prova), com o total previsto.
- Prova: `tests/test_contratos_editavel_18_11.py`.

## Pontos de atenção e de divergência, o setor e a cláusula (19/11/2026; `pontos.py`)

O pedido de 19/11/2026, olhando o painel "Zeladoria Contratual por Cliente" do Radar da Zeladoria: "a parte por setor (oq
performance atende, o que zeladoria etc)" e "ponto de atenção e pontos de divergência do contrato". O Levi, no mesmo dia:
"uma tagzinha [...] da cláusula do contrato [...] uma forma mais resumida"; "separar por setor [...] ordenar por setor
[...] e aí botar uma linha grossa"; e o pedido da área de Contratos para recolher os blocos de Entregáveis. Escolhas dele:
**vencendo = 60 dias** (o Radar usa 90), o setor **só dentro do contrato**, resolver um ponto **com motivo e prova**, e
em Entregáveis só os lançados abertos na 1ª vez.
- **A aba Pontos** junta, sem copiar: as **contas** (Atenção: vigência vencida ou que vence em até 60 dias; o prazo de
  avisar a renovação que passou ou chega nesses dias; o cliente sem contrato ou aditivo ASSINADO na pasta, só minuta ou só
  anexo; o cliente sem PDF lido), os **leitores dos PDFs** (Divergência: o `divergencias` de cada contrato, com o que cada
  documento diz e qual prevalece; os da 1ª leva ficaram no texto das `observacoes` e entram à mão, por "Incluir ponto"), a
  **planilha × o PDF** (Divergência: fim, aviso prévio e índice; era o bloco "não batem" do fim das Regras) e o **Radar da
  Zeladoria** (as linhas de `zeladoria_contratual` com alerta, lidas na hora pela `zeladoria.leitura`; o mesmo motivo em
  várias usinas vira um ponto). O Radar casa com o contrato pelo nome do cliente sem acento e sem caixa, nunca por
  palpite: o cliente do Radar sem contrato de mesmo nome aparece numa linha em Todos os contratos, para alguém acertar o
  nome. Radar fora: a aba diz que os dele não vieram, e o resto aparece.
- **Resolver** grava o item `resolucao` (o que se decidiu, com motivo e prova, no Histórico); **reabrir** é retirar a
  resolução (motivo e prova também). O item `ponto` é o incluído à mão (Atenção ou Divergência, o texto e o setor). O id
  do ponto leva o dado que o criou (`c:vigencia:<fim>`, `d:<contrato>:<n>`, `p:<contrato>:fim:<data>`, `z:<hash>`):
  mudou o dado, nasce outro ponto, e a resolução velha não esconde o novo. Resolvido vai para "Resolvidos", recolhido.
- **Na tela:** o número de abertos na aba (vermelho com Atenção, amarelo só com Divergência) e a coluna Pontos em Todos
  os contratos, que leva à aba. "De onde" mostra a etiqueta curta da cláusula; a referência inteira na dica. No celular
  (até 640 px) a linha empilha: o tipo e o Resolver em cima, o ponto e a origem embaixo.
- **O setor de cada regra** vem dos leitores dos PDFs (9 nomes fixos, `edicao.SETORES`; em 19/11/2026, 3 de 3.905
  regras sem setor). Regras ganhou **Por setor** no mesmo controle (Por categoria | Por setor | Prioritárias | Mudadas
  por aditivo): cada setor abre o que o contrato pede dele, na ordem das categorias. Atendimento, Entregáveis e Metas
  vêm **por setor**, na ordem da operação (`SETORES` do `contratos.js`), com uma linha grossa e neutra (`--tinta-2`; cor
  só para estado) e o nome do setor abrindo cada um.
- **A etiqueta da cláusula** (`fichas.clausula_curta`, posta em `ref.curta` pelo `edicao.visao`): o documento abreviado
  e o 1º item ("Anexo II (Proposta Técnica), 4.7.2" → `Anx II · 4.7.2`; "Cláusula Vigésima Primeira, iii" → `Cl. 21 ·
  iii`; "9 (c)" → `Cl. 9 (c)`). Medida em 19/11/2026 nas 3.978 regras lidas: nenhuma vazia, a maior com 20 caracteres.
- **Entregáveis** abre e fecha cada bloco pelo título (Recorrentes, Entrega única, Entregáveis e medições lançados); na
  1ª vez só os lançados abertos, e o navegador lembra (`localStorage` `nexus.contratos.dobras`).
- **A coluna Contratos** (a regra igual em vários contratos) quebrava a linha: a célula tinha a classe `.sub`, que é
  `display:block`, e numa `<td>` isso tira a célula da tabela. A célula de texto miúdo é `td.ctr-quais`.
- Prova: `tests/test_contratos_pontos_19_11.py` (dados inventados). A prévia com os PDFs reais: a cópia de prova com
  `NEXUS_DADOS` numa pasta de rascunho com as fichas e uma planilha mínima (nunca no repositório).

## A aba Indicadores e o aniversário do contrato (26/11/2026; `indicadores.py`)

A sugestão de 26/11/2026 (com mockup): "Uma aba Indicadores no contrato [...] meses do ano contratual nas colunas, usinas nas
linhas", com MPM, MPS e MPA feitas sobre as planejadas, a supressão vegetal e a lavagem com a data, o PR e a
disponibilidade expurgada contra a meta, e o contrato inteiro no alto. O Levi, junto: "ANIVERSÁRIO DE CONTRATO, RELATÓRIO
DE ANIVERSÁRIO DE CONTRATO". Escolhas dele no mesmo dia: o ano conta do **início da vigência** (não da data-base);
entram **todas as usinas do cliente no cadastro** (como a Visão gerencial); o mês sem dado no banco diz **"s/d"** (o
histórico anterior a 10/2026 é a fase 2); o relatório de aniversário é **interno, para o gestor do contrato**; o aviso,
**30 dias** antes; a régua de cor **da sugestão**: verde na meta, amarelo até 2 pontos abaixo, vermelho abaixo disso,
sem cor sem meta. **A visão é gerencial, para o CEO e os heads** (Levi, 27/11/2026: "Pense que a gente está fazendo uma
visão gerencial para o CEO, para os heads darem uma olhada, vai ser muito importante").
- **A janela padrão são os ÚLTIMOS 12 MESES até o mês de hoje** (`indicadores.ultimos_12_meses`; Levi, vendo o ano
  contratual no ar: "puxa pelos últimos 12 meses até atualmente [...] sempre vai se atualizando, do que tá projetando um
  futuro que não tem dado"): anda sozinha a cada mês e vale também para o contrato sem início da vigência. O ano
  contratual fica na lista da barra (`?ano=N`), para consultar um ano que fechou (o do relatório de aniversário).
- **O ano contratual e o aniversário** (`controle.ano_contratual` e `proximo_aniversario`, no `com_datas`): o 1º ano vai
  do início ao dia antes do 1º aniversário; 29/02 vira 28/02. O contrato leva `aniversario`, `dias_aniversario` e
  `ano_contratual`; a linha de fatos mostra o aniversário, e a aba Pontos ganha a Atenção 30 dias antes
  (`pontos.ANIVERSARIO_DIAS`). Sem início da vigência, a aba diz que falta.
- **De onde vem cada linha** (as fontes que as telas donas já usam, juntadas em `contratos_tela._fontes_da_ligacao`):
  - **PR e disponibilidade, cada um em duas linhas, sem e com o expurgo do contrato** (Levi, 27/11/2026: "Eu tô sentindo
    falta do PR ponderado, PR expurgado"; "Disponibilidade expurgada também, mesma lógica"): na usina, PR, PR expurgado,
    Disponibilidade e Disponibilidade expurgada; no contrato, as quatro pela potência ("PR ponderado"). Cada linha contra
    a meta; o "fora da meta" e os cartões do alto contam o EXPURGADO (o número do contrato), com o sem expurgo ao lado. O
    expurgo é o `com_expurgo` da Visão gerencial (`comando/expurgos.py`: a queda da rede e a limitação imposta saem da
    conta, `pr × (prod + E) ÷ prod`); a sujidade e a vegetação não entram (o chat da Performance, 26/11/2026);
  - **de onde vem o PR e a disponibilidade: o livro `nexus_kpi_usina_mes`** (`comando/kpi_mes.py`; Levi: "Pode até
    criar um book sobre isso para você não ficar carregando, calculando toda vez que abre"): a conta da Visão gerencial
    já feita, por usina e mês, gravada de hora em hora (:47) pelo laço do app, só quando muda; o mês fechado congela no
    dia 11 do seguinte. A aba junta pelo `_usinas_kpi`: o mês fechado vem do livro; o mês em curso, da conta de agora
    quando ela está pronta; sem a conta (o Nexus acabou de subir), as usinas e os números saem só do livro e a aba abre
    na hora, sem o "montando" (a conta fria levou 29 s no PC em 27/11). Sem o livro nem a conta, volta `montando` e a
    página pede de novo a cada 3 s. O banco de performance só tem os meses desde 10/2026 (`diagnostico_mes.
    PRIMEIRO_MES`); antes, "s/d". Medido em 27/11: 266 linhas (133 usinas × out e nov/26); o expurgo mudou o PR em 26 e
    a disponibilidade em 193;
  - MPM, MPS e MPA: as tarefas do ano do PCM (`pcm.fonte.ler_gestao_sem_esperar` e `pcm.gestao.classificar`: a sigla no
    nome, o mês da Data Programada, feita = Finalizada), ligadas à usina pelo nome (`responsaveis.Nomes`);
  - supressão vegetal (roçagem e poda química) e lavagem (limpeza de módulos), de duas fontes juntas
    (`contratos_tela._servicos_feitos`). O Radar da Zeladoria, como o Histórico de Serviços o junta (Levi, 26/11/2026: "a
    lavagem de módulos está na parte de zeladoria [...] em histórico de serviços"; `indicadores.servicos_do_radar`, o
    `analiseTimelinePorUsina` do clone): o histórico de serviços, a cotação com a execução terminada, a rota da equipe e
    a OS de contrato, o mesmo serviço no mesmo dia uma vez; a usina liga pelo nome ou pelo código. E as OS finalizadas do
    Fracttal (o arquivo do ano do PCM: "Acompanhamento - Limpeza de Módulos", "Acompanhamento - Supressão Vegetal";
    `indicadores.tipo_da_tarefa`, a inspeção pré-lavagem fica fora), porque o Radar sozinho é ralo: em 26/11 ele tinha 18
    lavagens no ano, o Fracttal 49 tarefas de lavagem e 186 de supressão, todas ligadas a uma usina. A OS a até 10 dias
    de um serviço do mesmo tipo já contado é o mesmo serviço (`indicadores.juntar_servicos`). Com as duas, a Thopen foi
    de 14 para 27 usina·mês com lavagem e de 65 para 108 com supressão. O mínimo do ano, o `zeladoria_contratual` do
    Radar por UFV (só o "fixo"); a linha do portfólio ("82 UFVs") vale para as usinas sem linha própria;
  - **a data feita, e a atrasada pelo prazo do contrato** (Levi, 27/11/2026: "tem que ser a data que foi feita [...] E
    não feita, a depender do prazo do contrato"): o mês com o serviço mostra a data (a dica, a próxima pelo prazo); sem
    ele, **"atrasada"** (vermelho) quando o prazo do contrato da zeladoria venceu desde a última (`passo_do_contrato`: o
    mínimo do ano vira o intervalo, 2 por ano = uma a cada 6 meses, 4 = a cada 3; sem nenhuma registrada, conta do 1º
    mês do arquivo do PCM); senão "—", com a última e o vencimento na dica. A usina sem prazo no contrato só mostra as
    datas. Antes do 1º mês do arquivo do PCM (`_zel_desde`, 01/2026 em 26/11) é "s/d": sem as OS do Fracttal o atraso
    seria chute. A linha do contrato diz "N atras." no mês e a gaveta lista as usinas. O rótulo diz o que é o número
    (Levi, 27/11/2026: "se esse número aí for o dia [...] tem que ter um disclaimer falando que é dia"): na usina, "dia
    feita (dia/mês)"; no contrato, "nº de usinas feitas"; e a legenda tem os dois. Até 27/11 o "não" vinha do PR
    expurgado abaixo da meta com a ronda em 4 ou 5: saiu com a ronda;
  - a meta de PR (26/11/2026, Levi: "As metas de PR, você vai entrar na BD Performance"): por usina e mês, o "PR Previsto
    1° Ano" da aba Info Mensal da BD Performance e o "PR (2026)" da aba Dados Mensais 2026 da BD Thopen
    (`contratos_tela._metas_pr_bd`, ligados pelo nome); o PR do contrato no mês compara com a meta do mês pela potência. O
    número dos Dados do contrato (`meta_pr`, editável com prova) vence. O PR lido do PDF saiu (numa ficha, outra regra virou
    um PR de 98%). Medido em 26/11: na Thopen, 72 das 84 usinas com meta; na Athon, 10 de 10;
  - a garantia de disponibilidade: a dos Dados do contrato (`meta_disp`), ou a lida do PDF, ou **99%** (Levi: "As que
    faltam, bota 99%"; `indicadores.DISP_PADRAO`);
  - **a vegetação e a sujidade da ronda saíram em 27/11/2026** (Levi: "Sobre sujidade e vegetação na ronda, não importa
    isso daí não"); tinham entrado em 26/11.
  A ligação pelo nome é medida: as tarefas do PCM e as usinas do Radar do cliente que não ligaram aparecem numa linha da
  aba, com quantas de quantas.
- **A tela, no desenho do mockup** (a 1ª versão subiu enxuta, numa linha de fatos; o Levi, vendo no ar: "eu queria no
  mesmo estilo, pintadinho lá do mockup [...] Antes da usina, é bom mostrar também o cliente [...] Eu tô sentindo falta
  desses KPIs de cima"): a barra com o Ano contratual (a lista dos anos), as Metas (de onde vêm), a Visão (Completa |
  Só KPIs | Só manutenções) e o Exportar (o PDF da aba no papel claro, `window.print` sem a casca); os quatro cartões
  (o PR e a disponibilidade expurgada do contrato com a meta e o mês a mês em barrinhas, os meses abaixo da meta e a
  disponibilidade sem o expurgo; as preventivas e os serviços do ano; o que ficou fora da meta e a usina que mais
  pesa, com o atalho para Pontos); a tabela começa pelo **cliente** (o contrato inteiro: preventivas somadas, serviços
  como usinas feitas no mês, PR e disponibilidade pela potência) e segue pelas usinas (as três primeiras com problema
  abertas, o resto numa linha "Mais N usinas"); a célula é pintada pelo estado (fundo, borda e texto da mesma cor,
  só tokens). As colunas dos meses e do acumulado são centralizadas, o cabeçalho e o valor; só a dos nomes fica à
  esquerda. O cartão das preventivas e serviços é de cinco colunas iguais, o nome em cima e o valor embaixo, sem texto (a
  explicação na dica). O mês em curso não pinta de vermelho a preventiva ainda não feita; o nome do indicador fica preso à
  esquerda quando a tabela rola de lado.
- **A gaveta da célula** (Levi, 26/11/2026: "esses botões coloridos aí fossem clicáveis e aparecesse a confirmação da
  resposta no card lateral [...] qual é a OS e tudo mais. A OS clicável para eu conseguir abrir o card da OS"): toda célula
  (da usina ou do contrato inteiro, de um mês ou do acumulado) é um botão que abre uma gaveta à direita, deslizando (o
  desenho da gaveta da Engenharia; sem animação para quem pede movimento reduzido), pela
  `/t/comando/contratos/indicadores/celula.json?cliente=&ano=&uid=&linha=&mes=` (uid `t` = o contrato; mes `acum` = a
  janela). MPM, MPS e MPA: as OS do mês, uma vez cada, com as tarefas dentro (o PCM conta TAREFA a tarefa: uma OS de MPM
  traz a cabine, o inversor, a segurança…), quantas feitas, e a OS abre o card do Fracttal (`NexusOsCard.abrir`, pelo id;
  sem id, pelo número). Supressão e lavagem: os serviços com a data, a origem (rota da equipe, OS de contrato, OS do
  Fracttal…) e a OS clicável, e as usinas com o serviço atrasado (na usina, os meses sem ele, com a última). PR e
  disponibilidade (as quatro linhas): usina a usina, com a meta, o número sem o expurgo na linha expurgada e o texto do
  expurgo (o mesmo da nota da Visão gerencial). Toda gaveta diz de onde vem.
- **A legenda** são amostras do mesmo tamanho, com o valor no meio, em colunas iguais.
- **O PR acima de 100% é leitura errada** (`indicadores.PR_MAX`, a régua da Visão gerencial): na prévia de 26/11/2026,
  uma usina da Thopen com PR de mais de 1.000% fazia o PR do contrato dar 730,5%. A célula diz "s/d" com a dica.
- **Os buracos, medidos em 26/11/2026:** o "s/d" de PR e disponibilidade são os meses antes de 10/2026 (o banco não
  tem) e, na Thopen, cerca de 22 usina·mês sem PR publicado; o "—" de MPM é a MPM que o arquivo do PCM não tem
  planejada no mês (na Thopen, 83 de 252 usina·mês; a ligação pelo nome está boa, 3.702 de 3.721 tarefas); MPS, MPA,
  supressão e lavagem só aparecem no mês em que acontecem.
- **Medido em 26/11/2026** com os dados reais, na cópia de prova: cerca de 1 s por contrato; na 2C, as 661 tarefas do PCM
  e as 5 usinas do Radar ligaram todas.
- **Falta (fase 2):** o relatório de aniversário em PDF, guardado congelado no ano que fechou; o histórico de PR e
  disponibilidade antes de 10/2026 (a Performance); MPM, MPS e MPA no banco (hoje o arquivo do PCM, por nome); o Radar
  ligado ao cadastro; o planejado do Radar (diarista), que não está nas tabelas copiadas; a ligação contrato × usina para o cliente com vários contratos.
- Prova: `tests/test_contratos_indicadores_26_11.py` e `tests/test_comando_kpi_mes_27_11.py` (o livro).

## Quem cuida de quê: a visão reduzida por setor (26/11/2026; `setores.py`)

Em Todos os contratos, a vista "Quem cuida de quê" (`#/quem`): as regras de Atendimento, Entregáveis, Metas e Financeiro de
todos os contratos juntadas em ATIVIDADES, cada uma com um setor dono e quem também vê; o número da matriz setor × tema abre
as atividades, a atividade abre os clientes e o cliente abre as regras com o prazo, o que vale hoje e a cláusula. Pedidos do
Levi: "uma visão reduzida"; "um drill [...] clicar na atividade, ver quantas regras são, ver quais são as regras por cliente
e ver quais são os prazos"; "no mesmo formato que estava o PDF [...] para eu ir só abrindo ali" (o protótipo foi um HTML
fora do repositório, com as fichas de 18/11).
- **A distribuição** (o setor não está escrito nos contratos, que dizem "a CONTRATADA"; sai do que a regra é, pelo nome e
  pelo que vale hoje, sem acento): o **COS** fica com o tempo real (usina ou equipamento parado, perda de comunicação,
  monitoramento 24 h, avisar a falha e abrir a OS), "acompanha, abre a OS e avisa a manutenção"; a **Performance**, com a
  baixa geração, o desvio de produção, os alarmes e o evento menor sem perda de energia nem de comunicação ("essas coisas
  pequenas são mais da performance hoje em dia"); a **Manutenção (Supervisão de Campo)**, com o sobreaviso, o plantão, o
  horário da equipe e a chegada ao local ("esse setor de supervisão de campo é um setor de manutenção"), e "também vê" o
  que é acompanhamento de manutenção; o **PCM**, com a resposta à falha, a correção e o reparo; a **Segurança**, com a
  falha que ameaça bens e pessoas. Entregáveis, Metas e Financeiro são proposta (marcada "proposta" na tela); a do Levi,
  "definida".
- **A conta**: no servidor (`setores.montar`, puro), junto do `dados.json` (`quem_cuida`): só os ids das regras por
  atividade e cliente; o texto vem das fichas que a página já tem. A mesma regra em mais de um contrato do cliente (mesma
  categoria, nome e o que vale) conta uma vez. A 1ª atividade que casa vence, então a ordem da lista importa: o sobreaviso
  vem antes do "avisar a falha" (a palavra "sobreaviso" contém "aviso" e caía no COS). Em 26/11 o `` de quatro regras
  da zeladoria estava gravado como caractere de controle e "roçada" nunca casava (a zeladoria foi de 25 para 33 regras).
- **Medido em 26/11/2026** (as fichas da tela): 963 regras de 15 clientes; no Atendimento, COS 53, Manutenção 54, PCM 67,
  Performance 13.
- **Falta**: os comentários da área sobre a distribuição (o Levi vai mandar o arquivo); confirmar as "propostas".
- Prova: `tests/test_contratos_quem_cuida_26_11.py`.

## A planilha de controle de obrigações na visão do contrato (16/11/2026; `controle.py`)

O pedido veio do retorno do supervisor de contratos na prévia: "Só não encontrei algum setor que fale sobre renovação
contratual e/ou ajuste contratual de 12 meses. Essas datas são importantes para a gestão de contratos". O Levi, com a
pasta do Backoffice: "ATUALIZE AGORA COM DADOS REAIS!".

- **A fonte é a planilha da própria área:** `Controle_Obrigacoes_Contratos_GridCo_R00.xlsx`, no SharePoint (Gridco › 4.
  O&M › 17. Backoffice › 2. Contratos). Ela tem 8 abas. As que entram:
  - **Carteira:** uma linha por cliente e recorte, com o supervisor, a vigência, a data-base e o índice do reajuste, o
    aviso prévio de renovação, o SLA, a pasta e as observações, tirados dos contratos pela área;
  - **Calendario:** uma linha por obrigação, com o vencimento, o alerta, o executor e o status. A linha **sem vencimento
    entra** (a planilha a leva à pauta como SEM DATA);
  - **Usinas:** as usinas de cada cliente, do Fracttal;
  - **Adicionais** (desde 17/11/2026): a memória de cobrança (E-CTR-04), um serviço feito fora do valor fixo por linha,
    com o valor, a resposta do cliente, o BM e a NF;
  - **Cadastros** (desde 17/11/2026): as metas da Estrutura R02 (entregáveis no prazo 95%, vencidas em aberto 0,
    adicionais faturados 90%, cobertura de escopo 100%), a antecedência padrão do alerta (7 dias) e o prazo da memória
    (10 dias).

  Adicionais e Cadastros são opcionais: a planilha sem elas ainda importa. **A Pauta_Semanal e a Indicadores_Mes não se
  leem:** são somas por supervisor das colunas do Calendario e da Adicionais, e o Nexus soma as mesmas colunas por
  contrato. O LEIA-ME é texto.

  **Como isso foi descoberto (17/11/2026):** a tela dizia "Sem dado real ainda" em Atendimento, Entregáveis, Metas e
  Financeiro, porque só 3 das 8 abas eram lidas. Levi: "na fonte que eu mandei não tem nada de atendimento, entregáveis,
  metas e financeiro???????????". Tinha, menos o atendimento por usina. Antes de dizer que a fonte não traz, abra a fonte
  inteira.

  O Nexus acha as colunas pelo nome, então a coluna pode mudar de lugar. A linha "— EXEMPLO" da planilha não entra.
- **Onde mora.** Foi importada pelo administrador em 16/11/2026 (reimportada em 17/11 com as 8 abas) e ficou na pasta de
  dados do servidor, `contratos/controle_obrigacoes.json`, como a carga inicial da tela Contratos. A importação saiu
  da tela em 18/11/2026: daí em diante, o que muda se edita na tela, com histórico (seção acima).
  - **NUNCA no repositório**, que é público, e nunca no banco de leitura aberta: a planilha tem nomes, valores e cláusulas.
  - A planilha errada é recusada e a que estava fica.
  - `GET .../dados.json` entrega o importado, com as contas de hoje; a conta do cliente e o Modo cliente não leem (403).
- **As contas (`com_datas`), as duas que a área pediu:**
  - **Renovação:** avisar até o fim da vigência menos o aviso prévio.
  - **Próximo reajuste:** o 1º aniversário da data-base, contado a partir de 12 meses dela, que ainda não passou. Hoje
    conta, e 29/02 vira 28/02.
  - Com elas vêm os dias até cada data e as obrigações em atraso.
  - **As colunas que a planilha calcula por fórmula são refeitas no Nexus**, com o hoje de quem abre, porque as fórmulas
    usam o HOJE() e o valor guardado pelo Excel é o do dia em que alguém salvou. Cada regra cita a fórmula em
    `controle.py`:
    - o semáforo (`tom`): entregue; cancelada; sem data; vencida; dentro do alerta da linha (sem ele, o da Cadastros);
      no prazo;
    - "conta no KPI de entregáveis" (`entregavel`): tipo Entregável ou Medição, e não cancelada;
    - "entregue no prazo" (`no_prazo`): a entrega até o vencimento;
    - a situação do adicional: Faturado; Reprovado; Memória atrasada ou a enviar (a execução mais 10 dias); Aprovado,
      faturar; Aguardando cliente. O valor é o aprovado, ou o estimado.
  - **Prova de 17/11/2026** com a planilha real e o hoje que o Excel usou (10/11/2026): 75 de 75 obrigações e 8 de 8
    adicionais iguais às colunas da planilha. Outubro somado por supervisor bate com a Indicadores_Mes (um supervisor com 1 entregável e 0 no prazo,
    outro com 3 adicionais).
  - O gestor do contrato é o supervisor da linha "Contrato (nível geral)"; sem essa linha, o supervisor único do cliente.
    As outras linhas viram as carteiras, cada uma com o supervisor e as usinas dela.
- **A página** (desde 18/11/2026 a tela Contratos, `static/contratos.js`; o exemplo fictício da prévia saiu) pede os
  dados ao Nexus e:
  - abre em **Todos os contratos**: uma tabela com o gestor, a vigência, até quando avisar a renovação, o próximo
    reajuste e as obrigações em atraso. Em cima a vigência (ou o aviso) vencida, depois quem tem atraso, depois a data mais
    perto;
  - cada contrato traz na linha de fatos **Vigência, Renovação (avisar até), Próximo reajuste e Usinas**, e a ficha da
    planilha;
  - **Regras** traz as quatro que a planilha tem (vigência, renovação, reajuste, SLA); **Calendário** traz as obrigações
    reais (o mês, as atrasadas, as próximas e a lista inteira);
  - **Entregáveis:** as linhas que contam no KPI de entregáveis, com a situação e a data de entrega;
  - **Financeiro:** os serviços adicionais (executado, faturado, a faturar, memória atrasada) e as medições (BM). A
    planilha não traz a mensalidade nem o valor do contrato, e a tela diz isso;
  - **Metas:** as contas da Indicadores_Mes só do contrato, mês a mês (o entregável no mês do vencimento, o adicional no da
    execução), contra as metas da Cadastros, e as vencidas em aberto hoje. A cobertura de escopo é manual na planilha,
    por supervisor, e não entra;
  - **Atendimento:** a planilha não tem o atendimento por usina, e a tela diz isso e aponta onde está o que ela tem;
  - a importação de antes de 17/11/2026 não tem Adicionais nem Cadastros: Financeiro e Metas pedem para importar de novo.
- **Navegar (17/11/2026, Levi: "ARRUME ESSA LISTA FEIA, DEIXE NO PADRÃO NEXUS", "Não tá pegando tema claro" e "As
  linhas de clientes devem ser clicáveis com um botão de voltar!")**:
  - a troca de contrato é a lista do Nexus (a da busca de usina), não a nativa do navegador: o cliente, o gestor embaixo,
    o atraso à direita, a busca sem acento quando passa de 8, e setas, Enter e Esc;
  - a linha inteira do cliente em Todos os contratos abre o contrato (o nome é link, para o teclado); o contrato aberto
    tem o botão **Voltar para todos os contratos**;
  - o contrato e a aba vão no endereço da moldura (`#/c/<cliente>/<aba>`; `#/` é Todos os contratos), então o Voltar do
    navegador também volta à lista. Os endereços antigos (`#/regras`, `#/contrato/regras`) seguem abrindo;
  - **tema**: a página é um documento à parte e não herda o `data-tema` da casca. Ela lê o da casca antes da 1ª pintura e
    acompanha a troca ao vivo (MutationObserver); em tela cheia, o cookie `nexus_tema`. Os tokens do claro são cópia do
    bloco `:root[data-tema="claro"]` do `nexus.css`: mudou lá, muda aqui. Cor fixa não entra (nem nos gráficos SVG do
    exemplo: a cor vai no `style`, com `var()`).
- **Medido em 16/11/2026** com a planilha real: 16 contratos e 60 obrigações com vencimento (75 com as 15 sem data, que
  entraram em 17/11/2026), e 8 serviços adicionais. Batem com as colunas automáticas da planilha (a vigência vencida e
  o próximo reajuste, contrato a contrato; as datas de cada cliente ficam na planilha e no banco, não aqui).
- Prova: `tests/test_contratos_controle.py`, com uma planilha inventada (mesmas abas e colunas, nada real).

## As fichas dos contratos, lidas dos PDFs (18/11/2026; `fichas.py`)

Levi, 17/11/2026, depois da tabela do que a planilha tem por cliente: "e se eu salvar os PDFs dos contratos para você
analisar e fazer algo melhor?", "completa tudo!" e "faça por subagentes para melhor confiabilidade".

- **De onde vem.** Os PDFs (contrato, aditivos e anexos) de cada cliente foram lidos FORA do Nexus, um leitor por
  cliente, num formato único: cada regra com a categoria (11: SLA, Entregáveis, Rotinas, Disponibilidade e desempenho,
  Penalidades, Benefícios, Medição e faturamento, Adicionais e hora extra, Rescisão, Seguros e documentação, Outras
  obrigações), o que vale hoje (`vigente`), o que era antes quando um aditivo mudou (`contratual` + `alterado_por`), o
  setor que executa e a prova: arquivo, página, cláusula e trecho literal. O que o contrato não diz vem em `lacunas`.
- **Como se confiou.** Um script procura cada trecho no texto da página citada. O que não bate (tabela que no PDF é
  imagem, transcrita) vai a um revisor que tenta derrubar o item olhando a imagem da página.
- **Onde mora.** Foi importado uma vez, em 18/11/2026, e ficou em `contratos/fichas_contratos.json` na pasta de dados
  (NUNCA no repositório, que é público), como parte da carga inicial da tela Contratos; a importação saiu da tela no
  mesmo dia (Levi: "o arquivo JSON você mesmo criou. Então alguém teria que transformar em JSON [...] isso não faz
  sentido"). O `fichas.ler` segue conferindo o formato; a ficha casa com o cliente da planilha pelo nome sem acento e
  sem caixa (`fichas.por_cliente`).
- **Na tela.** Regras: as 11 categorias recolhidas (ou os setores, desde 19/11/2026); a linha abre o trecho e a página;
  um controle só (Por categoria | Por setor | Prioritárias | Mudadas por aditivo). Cliente com vários contratos do mesmo
  modelo: a regra igual em todos aparece uma vez com "todos". Embaixo, "O que o contrato não
  diz"; a planilha × o PDF (fim da vigência, aviso prévio, índice) está na aba Pontos desde 19/11/2026. Nas outras abas, o que o contrato pede: SLA no Atendimento, Rotinas no Calendário, Entregáveis,
  Metas (disponibilidade, bônus, penalidades) e Financeiro (valor mensal, medição, adicionais). Todos os contratos ganha
  a coluna "Regras do contrato" (ou "PDF não lido").
- **O contrato completa a planilha (18/11/2026, Levi: "faça um rework lá nos contratos e bote os dados que
  faltam!"; `fichas.completar`).** Só o VAZIO da planilha: início e fim da vigência (o mais cedo entre os contratos do
  cliente), aviso prévio e índice (só quando os contratos que trazem dizem o mesmo), data-base (só se for data) e o valor
  mensal (a soma dos contratos que trazem, com quantos trazem e se há minuta). Quando a planilha tem o dado, vale o dela
  e a diferença vai para "A planilha de controle e o contrato não batem". Cada campo completado leva `origem` (contrato e
  página) e a tela marca "do contrato". A renovação e o reajuste são calculados depois, com o dado completado. A página
  da prova mostra o intervalo (`ref.pagina_fim`) quando a tabela continua na página seguinte (achado da revisão).
- **18/11/2026, os 5 clientes com PDF** (quais são, a tela Todos os contratos diz): o que cada leitor achou que o Levi ou a
  área de Contratos precisa decidir está nas `lacunas` e nas `observacoes` de cada ficha. Os outros 11 clientes não
  mandaram PDF.

Quando a visão do contrato virar tela de verdade, ela entra na tela Clientes (a "Gestão de contratos (a estruturar)") e a
prévia sai.

**Enxuta desde a noite de 12/11/2026** (Levi: "pode tirar o prontuário, tá? Não tem nada a ver" e "É quase a tela
inteira, só de nada com nada [...] A gente está vendo o quê? Regras do contrato. Então, tem que mostrar regras do
contrato. Aí tem um filtro para isso, um filtro para aquilo. Aí uma porrada de KPI. Aí tem outro filtro lá em cima de
contrato. Aí tem um botão de nova regra. Se decida, enxugue"). Antes, a 1ª regra aparecia a 780 px do alto de uma tela de
853; hoje, a uns 330. O Prontuário da usina saiu do mockup (o de verdade mora no Comando > Usinas). **A regra para toda
aba da visão do contrato, que vale também quando ela virar tela de verdade:**
- o contrato em **duas linhas**: o nome do cliente (que é a troca de contrato: não há seletor à parte), o código e o
  tipo; e uma linha de fatos (vigência, mensalidade, usinas, gestora). A ficha inteira (CNPJ, aditivos, reajuste,
  substituta, as usinas) só no clique em "Dados do contrato";
- a aba **não repete o título nem se explica**: abre no conteúdo. O período ou a contagem à esquerda da régua;
- **no máximo um controle por aba**, e só quando muda o que se vê: Todas | Acordadas (Regras), Por usina | Por cliente
  (Atendimento), Por usina | Contrato inteiro (Entregáveis), o agrupamento no próprio gráfico (Metas). Saíram os oito
  filtros por categoria (a tabela já vem agrupada), o filtro de frequência do calendário e os seletores de mês e de ano
  que não faziam nada;
- **Regras mostra o que VALE hoje**: uma coluna só, com a acordada no lugar da contratual, o selo "acordada" e a do
  contrato riscada embaixo; a regra que nunca mudou não leva selo nem autor (14 das 18);
- **o que acrescenta é a última linha da tabela** (a regra nova, a entrada nova), não um botão verde no alto;
- o cabeçalho da moldura no Nexus é **uma linha**: o título e o aviso de dados fictícios; sem a pergunta e sem a faixa
  amarela (o teste do mockup saiu com ele).

**3ª rodada, na mesma noite** (Levi: "esse scroll branco aí é zoado [...] deixa no estilo Nexus. E todas essas regras aí,
deixa recolhido [...] eu quero ver entregáveis, quero ver SLA, a pessoa vai clicando [...] seria bom se fosse separado
para o cliente [...] E aí seria bom para os gestores de contrato [...] recebendo as notificações [...] tem tantos em
atraso, isso está sempre para ele [...] Sempre"; do calendário: "ótimo também, gostei"):
- **a barra de rolagem é a do Nexus** (os tokens `--rolagem` do nexus.css copiados no mockup, com `color-scheme:dark`
  para os controles do navegador): página numa moldura não herda o estilo da casca, tem de trazer o dela;
- **as Regras abrem recolhidas**: uma linha por categoria, com quantas regras e quantas acordadas; o clique abre. O
  filtro "Acordadas" abre todas (são poucas e é o que se pediu para ver). O cabeçalho das colunas só aparece com alguma
  categoria aberta;
- **cada cliente tem o contrato dele**: o nome no alto troca o contrato (no mockup só o primeiro tem dados, e os outros
  dizem isso);
- **o gestor do contrato aparece quando o contrato tem um** (Levi: "Caso tenha gestor do contrato, também quero que
  apareça"): na 1ª linha do cabeçalho, ao lado do código e do tipo (antes era o 4º fato da linha de baixo, e sumia para
  o cliente sem dados), no aviso de atraso (é no sino dele que cai) e numa coluna do Atendimento por cliente. Contrato
  sem gestor não mostra campo vazio: a linha fica sem ele, o aviso de atraso diz que vai para o setor Contratos e a
  tabela diz "sem gestor" (o 3º contrato do mockup é assim, de propósito);
- **o que está em atraso fica numa linha no cabeçalho do contrato, em TODA aba**, com o que é e o atalho para o
  calendário, e diz que o gestor do contrato recebe o aviso no sino do Nexus, todo dia, até resolver. **Pendente para a
  tela de verdade:** a notificação ao gestor (o sino e o `nexus/notificacoes/`) e a conta de "tantos em atraso" somando
  os contratos dele; no mockup isso é só desenho.
As regras moram em `nexus/contratos/` (`contestacoes.py`, `acessos_clientes.py`); a view e o template, aqui.

## Contestações

Levi, 13/10/2026: "Contestação ligada ao Nexus: em contratos e clientes no Nexus pode ter um lugar para essas
contestações separando setores!"; "ficaria na API do PG, pode aplicar e construir!".

**De onde vem.** O cliente contesta um dia no Dashboard Thopen (5080): clica na barra do dia no gráfico Energia ×
Irradiação e marca geração, disponibilidade, desligamento, string, tracker e/ou ronda. O 5080 grava no banco o livro
`thopen_contestacoes` · `contestacoes` (`thopen/contestacao_banco.py` do repositório da plataforma), **e esta tela é o
destino** (Levi, 19/10/2026: "vai direto para contestações do Nexus e a gente resolve lá, esquece teams" — o COS não
tinha fluxo do Teams, e Disponibilidade e Desligamento nem marcavam no 5080): o 5080 grava na hora e só diz "enviada"
depois de o livro conferir. O Teams é um aviso a mais onde o setor tem fluxo (O&M › Performance e O&M › Zeladoria; o
COS não tem). O 5080 é a FONTE; no catálogo, fato
`contestacao_cliente` (área `contratos`), registrado antes da 1ª gravação; "quem grava" = Dashboard Thopen (5080)
(`telas.QUEM_GRAVA_ORIGEM`).

**Grão.** 1 linha = 1 contestação × 1 setor (as mesmas mensagens do Teams). Colunas: `id`, `contestacao_id` (junta as
duas linhas quando o cliente marcou dos dois lados), `recebida_em` (UTC), `data_id_recebida`, `data_id_contestada_ini` e
`_fim`, `usina` (o nome do 5080), `usina_id` (o de-para do 5080; vazio quando a usina tem dois ids, como Primavera),
`setor`, `itens` (só os do setor, `;`), `avisado_teams` ("sim" o Teams do setor recebeu, "não" recusou, "sem canal" o
setor não tem fluxo do Teams, desde 19/10/2026), `origem`
(`dashboard_thopen`) e `dados_cifrados`.

**O que é do cliente vai só cifrado** (regra 8: a API do banco tem leitura aberta): nome, contato, mensagem e o que ele
via na tela naquele dia (geração, irradiação, disponibilidade, trackers, strings, comentário, ronda) num JSON em
`dados_cifrados`. Cifra **assimétrica** (X25519 + HKDF-SHA256 com a pública efêmera de sal + AES-256-GCM; prefixo
`cx1:`): o 5080, público, tem só a chave PÚBLICA (`THOPEN_CONTESTACAO_CHAVE_PUBLICA`) e não abre nada, nem o que ele
mesmo gravou; o Nexus abre com a PRIVADA (`NEXUS_CONTESTACAO_CHAVE_PRIVADA`, opcional no `config.py`): a que o administrador cola em Base → Chaves das fontes,
aba Nexus (14/10/2026: cifrada na pasta de dados do servidor, sem a T.I. e sem reiniciar) e, sem ela, a do `.env`
(`auth.chaves.valor`; regra em `nexus/casca/CLAUDE.md`, "Chaves do Nexus"). A tela sem chave leva a esse lugar. A cifra é presa à
linha (contexto `thopen_contestacoes/<id>/dados` como dado associado): copiada para outra linha, "não abre". O decifrado
vive só na memória da tela. Sem a chave, a tela lista as contestações com "cifrado" no lugar do cliente e diz por quê.
**O par de 13/10/2026** está em `C:\GridcoAuto\entrega-ti\contestacoes-chaves-2026-10-13\` (a privada no
`.segredo`, nunca impressa): perder a privada é perder o que já foi gravado; a cópia em cofre é item da virada.

**A tela (o redesenho de 16/11/2026, Levi: "Sobre contestações quero um rebranding! Tire esse 'Pegar pra mim' qualquer
um daquele setor pode editar e salvar por tanto que salve quem foi que fez isso! deixe mais utilizável").** Uma fila por
setor, sem dono, num nível de superfície (os itens da lista e o card são os únicos cartões; a cor é só da situação):
- **as abas dos setores** só quando a sessão vê mais de um (o administrador), com as **abertas** de cada um;
- **os números do alto**: Sem resposta (alerta), Em andamento (info), Resolvidas (ok) e a mais antiga sem resposta (há
  quantos dias, e a usina); cada um leva à lista dele (a mais antiga, direto ao card dela);
- **a lista à esquerda**: Abertas | Resolvidas; nas abertas, a sem resposta primeiro, e cada grupo com a mais nova em
  cima. O item mostra a situação, há quanto tempo chegou, a usina, o dia e o que contesta, e a última atualização com
  quem escreveu (ou "Ninguém do setor respondeu ainda"; na resolvida, quem resolveu e quando);
- **o card à direita** (`_contestacao_card.html`, também pela rota `/card`, que a lista troca sem reler a página:
  `static/comando-contestacoes.js`): a usina, o dia contestado, quando chegou, o Teams ("recebeu"; "o Teams recusou o
  aviso" em vermelho; "só no Nexus" = o setor não tem fluxo, o caso do COS, e não é falha: `_avisado`), a situação com
  Marcar como resolvida / Reabrir, o que o cliente disse, o que ele via na tela naquele dia, o campo de escrever ("Fica
  registrada como <nome>, com a data e a hora") e a história, a mais nova em cima;
- **o endereço guarda a escolhida** (`?setor=&ver=&c=`): o aviso do topo leva direto a ela, e a aba do setor é a dela. No
  celular (até 899px) o card vem abaixo da lista e só aparece quando a pessoa escolhe uma;
- **sem JavaScript** tudo funciona por link e formulário (volta com o aviso, 303); com ele, a gravação é por JSON
  (`X-Nexus-Parte`), a recusa aparece no próprio formulário sem perder o texto, e o que gravou relê a página na
  contestação (os números, a lista e o aviso do topo em dia).
Tela nova nasce FECHADA para os setores (Base → Acessos): o administrador vê; marcar "Contestações" para Performance, COS
e Zeladoria. **Que setor recebe o quê** (o 5080 decide, `thopen/contestacao.py`): geração, string e tracker →
Performance; disponibilidade e desligamento → COS (Levi, 15/10/2026: "Disponibilidade e desligamento vão para o setor de
COS"); ronda → Zeladoria.

**Cada setor vê só a sua** (Levi, 15/10/2026: "O setor só vê a contestação do próprio setor, exceto administrador"):
`_setores_visiveis` — administrador (a lista de agora; o Nexus recalcula `session["admin"]` a cada pedido), todas; quem
tem setor, só a de mesmo nome (os setores do Nexus são "Performance", "COS" e "Zeladoria", como os das contestações); outro
setor, nenhuma ("Nenhuma contestação para o seu setor"); portão por setor desligado (`NEXUS_ACESSO_POR_SETOR=0`,
testes), todas. **O servidor barra**, não só a tela: o card e as ações de uma contestação de outro setor dão 404.

**O acompanhamento** (`nexus/contratos/tratamento.py`). Nasceu em 15/10/2026 com dono (o "Pegar para mim": só o
responsável escrevia; o administrador "Assumia"). **Desde 16/11/2026 o setor inteiro responde**: quem vê a contestação (o
setor dela, ou o administrador) e entrou com um login de pessoa (Fracttal ou Microsoft; a senha de administrador não diz
quem é, e por isso não escreve) escreve a atualização, marca como resolvida e reabre. Cada evento guarda quem e quando; nada
se edita nem se apaga. O POST do "Pegar para mim" de uma aba antiga não grava: volta à contestação com o aviso.
- **A situação** (a escolha do Levi no mesmo dia: "Sim, com Resolvida"): **resolvida** = o último `resolvida`/`reaberta`
  é um `resolvida`; senão **em andamento** = já tem atualização; senão **sem resposta**. Resolver sem escrever vale (o
  setor decide); reaberta sem atualização volta a sem resposta (e ao aviso). Resolver a resolvida, ou reabrir a aberta, é
  recusado (o livro é relido sob a trava antes de gravar).
- **O dado**: livro `nexus_contestacoes_tratamento` · `fato_tratamento_contestacao` (fato `tratamento_contestacao` no
  catálogo, registrado antes da 1ª gravação). 1 linha = 1 evento (`atualizacao`, `resolvida`, `reaberta` e, só na
  história, o `responsavel` gravado até 15/11/2026, que aparece como "Ficou com a demanda" e não dá nem tira nada) sobre
  a linha do `thopen_contestacoes` (`contestacao_linha_id`); só acrescenta, sob a trava, relido antes e conferido depois.
  A ordem é **a da gravação** (`_em_ordem`: pela hora e, no mesmo segundo, pela posição no livro; pelo id, resolver e
  reabrir no mesmo segundo ficavam ao acaso). Quem (nome e e-mail) e o texto só cifrados (Cofre, a chave do cadastro); a
  pessoa pelo `pessoa_hmac`; o `evento` em claro, que é o que o aviso do topo lê (`situacoes`).
- **No banco em 16/11/2026** havia 9 contestações (2 da Performance, 3 do COS, 3 da Zeladoria abertas sem resposta; a da
  Altair com o "Pegar para mim" e sem atualização; só a TESTE de 13/10 da Guaratinguetá V com uma atualização).

**O aviso do topo** (16/11/2026, Levi: "as contestações também devem notificar nas notificações lá de cima, a que não é do
OS Creator!"; `nexus/contratos/aviso.py` e `casca._contestacoes_do_sino`): a bandeja das demandas, ao lado do botão do OS
Creator, traz as contestações **sem resposta** do setor da pessoa, a mais nova em cima, com o que contesta, o dia e há
quantos dias espera; o clique leva ao card. **As escolhas do Levi**: sai para o setor inteiro, ao mesmo tempo, na 1ª
atualização de qualquer um dele ou quando alguém resolve ("1ª resposta do setor"); o administrador recebe só a do setor
dele ("Só a do setor dele"); o administrador sem um setor de contestação recebe as três (minha leitura: é quem coordena, e
não tem "o dele"). Só para quem abre a tela Contestações; a senha de administrador (sem pessoa) não tem bandeja. A cópia
dos dois livros dura 1 minuto e é relida por trás (nenhuma página espera o banco); quem grava pela tela já vê o aviso
sumir na página seguinte (`aviso.anotar`). Nada se decifra para o aviso: a usina, o dia e os itens vão em claro.

**Ainda não tem** (fica para quando o Levi pedir): filtro por usina ou cliente, editar uma atualização já gravada, aviso
por e-mail ou Teams, outros dashboards.

**Como provar.** `python -m pytest -q tests/test_contratos_contestacoes.py` (banco falso: o setor que escreve sem dono,
Resolvida e Reabrir, a ordem no mesmo segundo, o setor que só vê a sua, o aviso do topo e o administrador; com
`PLATAFORMA_REPO=<clone da plataforma>` o teste cruzado cifra com o código do 5080 e abre aqui). Em 13/10/2026, ponta a
ponta no banco de verdade: uma contestação TESTE pelo clique no gráfico do 5080 de ensaio (Guaratinguetá V, 06/10,
Geração + Ronda) gravou 2 linhas (Performance e Zeladoria); lida pela API aberta, nenhum nome, e-mail, mensagem ou kWh
em claro; esta tela, com a privada, abriu as duas. Essa linha TESTE ficou no livro (mensagem "Pode desconsiderar").

## Acessos dos clientes

Levi, 14/10/2026: "É possível implementarmos uma visão de login e senha para o dashboard thopen?" — contas **por pessoa,
ligada a um cliente**, administradas **aqui**; o painel sobe no servidor da T.I. em
`https://app.gridco.com.br/performance/` (entrada em `/performance/login`). Spec no repositório da plataforma:
`docs/superpowers/specs/2026-10-14-thopen-login-por-pessoa-design.md`.

**Quem grava o quê.** O Nexus grava as contas (`nexus_acessos_clientes` · `dim_conta_cliente`, no `catalogo.LIVROS`); o
5080 grava as senhas (`thopen_acessos` · `senhas`, em `CONHECIDAS`) e lê as contas a cada 2 min. Um livro por sistema:
nenhum sobrescreve o do outro. Esta tela só lê das senhas QUANDO cada conta definiu (nunca a senha).

**Grão e colunas.** 1 linha = 1 conta, o estado atual (o livro é trocado inteiro sob a trava, relido antes e conferido
depois pelo `livros.publicar`): `conta_id`, `carteiras` (`;`, na ordem Thopen, Copel, Matrix, Polaris; o papel `grid`
leva todas), `papel` (`cliente` ou `grid`: só a Grid força a releitura e grava os Comentários adicionais no painel),
`status` (`ativa`/`desativada`), `convite_hash` (sha256 do token), `convite_expira` (UTC, 72 h), `criada_em`,
`alterada_em`, `alterada_por_hmac` (`NEXUS_PESSOA_HMAC` do e-mail; "admin" na senha de administrador), `dados_5080` e
`dados_nexus`.

**Usuário de entrar** (15/10/2026, Levi: o cliente segue com "o acesso atual que utilizam" — o login da T.I. em
`/performance` pede Usuário e Senha — "Mesmo usuário e senha de hoje"): a conta guarda `usuario` (um e-mail ou um nome
de usuário de 3 a 60 letras, números, ponto, hífen ou sublinhado, sem caixa) e `email` (só quando o usuário é um
e-mail; a contestação do painel usa como contato). As contas de antes (só `email`) entram pelo e-mail. Repetido =
recusado. A senha de hoje a pessoa define pelo link (o painel aceita a partir de 6 caracteres).

**O que é da pessoa vai só cifrado** (regra 8), duas vezes: `dados_5080` selado para a PÚBLICA do painel
(`NEXUS_ACESSOS_5080_PUBLICA`, colada em Base → Chaves do Nexus; X25519 + HKDF-SHA256 + AES-256-GCM, a receita do
`thopen/acessos.py`, info `thopen-acessos/v1`, contexto `nexus_acessos_clientes/<conta_id>/dados_5080`) e `dados_nexus`
no Cofre (a chave do cadastro), para esta tela. O espelho das contestações: lá o Nexus tem a privada; aqui, a pública.
Sem a pública, a tela avisa e não cria conta nem link.

**O link.** Uso único, 72 h, `<NEXUS_THOPEN_URL>/convite/<token>` (padrão `https://app.gridco.com.br/performance`). O
token só aparece uma vez, na tela (guardado na sessão até a volta do 303; `Cache-Control: no-store`), para mandar pelo
Teams ou WhatsApp (o e-mail do servidor está barrado no tenant); no banco, só o sha256. "Gerar link" troca o anterior e
sela o nome e o e-mail de novo para a pública EM USO: trocado o par do painel, é assim que a conta volta a abrir lá. Link
usado = o 5080 achou a linha de senha com o mesmo hash. Desativar apaga o link pendente e tira a pessoa do painel em até
2 min (a releitura do 5080).

**Quem pode.** Ver a lista: quem tem a tela (tela nova nasce FECHADA para os setores; o administrador vê). Agir (nova
conta, gerar link, desativar, reativar): só administrador (`session["admin"]`), POST só da própria página
(`_de_outro_site`) e com o código do formulário guardado na sessão. E-mail repetido é recusado ("gere um link novo").

**Como provar.** `python -m pytest -q tests/test_contratos_acessos_clientes.py` (banco falso; com
`PLATAFORMA_REPO=<clone da plataforma>` o teste cruzado sela aqui e abre com o código do 5080, e confere livro, aba,
carteiras, contexto e o hash do token). Em 14/10/2026, ponta a ponta no banco de verdade (Nexus de ensaio na 5072 e 5080
com `THOPEN_LOGIN=1` em `/performance` na 5088): conta TESTE criada nesta tela → lida pela API aberta, nada em claro →
o link abriu "Definir senha" com o nome (o 5080 abriu o selo) → senha definida, a linha de senha gravada (`cs1:`) → o
painel com só a carteira Thopen; outra usina, outra carteira e o Atualizar deram 403 → o mesmo link de novo: "já foi
usado" → sair e entrar pelo e-mail → desativada aqui às 14:11:02, fora do painel às 14:11:39. A conta TESTE ficou no
livro, DESATIVADA (a API não apaga).
