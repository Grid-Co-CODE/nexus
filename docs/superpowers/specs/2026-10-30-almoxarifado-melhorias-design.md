# Almoxarifado: as nove melhorias de 30/10/2026 (desenho)

Pedido: a lista "Almoxarifado Nexus - Melhorias" do Levi (itens 1 a 5, do uso da tela e do App) e as sugestões 6 a 9 da
análise da pasta de Spare Parts. As escolhas que não eram óbvias, decididas pelo Levi em 30/10/2026 (quiz):
item 1 = as peças do almoxarifado; item 5 = os avariados entram na contagem; itens 8 e 9 = o App passa a trazer o custo,
a criticidade e a Curva ABC **do Fracttal** (o campo que o PCM preenche no cadastro da peça; o Nexus não calcula curva);
item 4 = o resto da contagem segue. O que o Nexus decide sozinho está marcado **(decisão)**.

Telas de hoje: `/t/pcm/pecas` (`nexus/pcm/almoxarifado.py`, `templates/pcm/almoxarifado.html`, seção "Almoxarifado" do
`nexus/pcm/CLAUDE.md`) e o inventário (`nexus/pcm/inventario/`, as seções "Inventário do almoxarifado" do mesmo `.md`).
Leia os dois antes. Regras da casa valem todas (cor só por token, `{{ raiz }}`, sem emoji, pt-BR, 375 px, nada de nome de
colega, governança do `nexus/dados/CLAUDE.md`).

## Por que

O PCM usa a tela para decidir compra e conferir estoque, e hoje ela engana em três pontos: o filtro mostra números de
outra aba (7), o "no limite" é quase todo ruído de peça de saldo 1 (8) e a avariada com saldo aparece como erro de
cadastro quando é uma peça esperando destino (6). Os outros itens fecham buracos do inventário que o uso mostrou: recontar
só o que está duvidoso (4), a curadoria sem dado para decidir (2, 3) e o avariado sem caminho (5).

**Falha mesmo funcionando:** número inventado (custo ou curva que o Fracttal não deu virando zero ou "C"), a recontagem
parcial substituindo a contagem inteira, ou uma peça boa virando avariada sem o PCM ver.

## Partes do Nexus (tela principal do Almoxarifado)

### 7. O filtro conta a aba que está à vista
Causa achada: o script das abas dispara `input` no formulário, mas o `filtro-local.js` só escuta `change` dos `select` e
`input` dos campos de texto; trocar de aba não refaz as contas, e os números ficam os da aba anterior. Conserto: a troca de
aba chama `window.FiltroLocal['alm-f'].aplicar()`. **(decisão)** Nas abas sem tabela filtrável (Por almoxarifado,
Cadastro a corrigir, Avariadas quando não for tabela) a barra de filtro some; nas outras, conta a tabela da aba.
Prova no navegador: em Reposição, a opção de um almoxarifado com N peças no limite mostra N.

### 1. Abrir um almoxarifado mostra as peças dele
Cada cartão da aba Por almoxarifado ganha "Ver peças" (botão com `aria-expanded`). As peças chegam no clique, de uma rota
que desenha o pedaço a partir da MESMA conta guardada de 5 min (`montar()`), sem ler o Fracttal **(decisão: a página não
engorda; é o padrão das usinas dos extintores)**. Colunas: Código · Peça · Crit. · Curva · Saldo · Mínimo · Situação, em
ordem de gravidade (abaixo, no limite, saldo unitário, sem mínimo, ok) e, dentro dela, criticidade e curva. Sem
criticidade ou curva: "–". Abaixo de 640 px vira cartão como as outras tabelas.

### 8. "No limite" sem o ruído do saldo unitário
Peça com mínimo 1 e saldo 1 sai do "no limite" e vai para um grupo próprio, **saldo unitário**, fechado por padrão, com a
frase "uma peça e mínimo 1: a próxima saída zera, mas não é pedido de compra por si". O número do alto vira "N no limite
(+M de saldo unitário)". A Reposição ordena por criticidade (1.Crítico primeiro), depois curva (A, B, C), depois a falta.
**(decisão)** O grupo vem antes: abaixo do mínimo primeiro, depois no limite, depois saldo unitário; a criticidade, a curva
e a falta ordenam DENTRO de cada grupo (um crítico no limite não passa à frente de um comum abaixo; a ajuda da tela diz a
ordem). As colunas Crit. e Curva entram na Reposição. Enquanto o App não manda criticidade e curva, a ordem é a de hoje e
as colunas mostram "–".

### 6. Avariadas: há quanto tempo sem destino
**Avariada é uma definição só, a do `regua.avariada`** (a marca "Avariado" do livro Itens OU o código terminado em `-AV`),
usada aqui, no item 5 e no número do alto. A avariada com saldo sai da "Cadastro a corrigir" e ganha a aba **Avariadas**. O
número do alto passa a contar o que a aba lista (avariada × almoxarifado com saldo, nota "com saldo"; hoje conta o catálogo
inteiro) e leva a ela. Por peça ×
almoxarifado: peça, saldo, **parada há N dias** e, com o custo, o valor. "Parada" = há quantos dias o saldo dela naquele
almoxarifado está acima de zero sem interrupção, pelos ciclos aplicados do histórico (`nexus_almoxarifado`, a foto do
Saldo de cada mês). Se ela já tinha saldo no primeiro ciclo do histórico, a tela diz "há pelo menos N dias (o histórico
começa em dd/mm/aaaa)" **(decisão: nunca inventar a data de entrada)**. Ordem: a mais parada primeiro.

### 9. Por almoxarifado: última contagem gravada e valor por curva
Cada cartão mostra a **última contagem gravada** (a data da contagem mais nova daquele almoxarifado em estado `gravada` ou
`gravada_com_conflitos`, pela leitura do inventário; sem nenhuma, "nunca contado pelo inventário") e o **valor em
estoque** por curva: "R$ total (A R$ · B R$ · C R$)", saldo × custo unitário. Peça sem custo não entra na soma e o cartão
diz "N peças sem custo no Fracttal" **(decisão: soma pela metade avisa, não esconde)**.

### A Curva ABC e a criticidade (base dos itens 1, 8 e 9)
As duas são as do cadastro da peça no Fracttal (a criticidade é o `groups_1_description`, "1.Crítico", "2.Necessário"...;
a curva é o campo de Curva ABC que o PCM preenche à mão; a API não grava nenhuma das duas, `curadoria.py`), trazidas pela
varredura diária do App. O Nexus não calcula curva (Levi, 30/10/2026: o histórico de peças lançadas é curto e quase tudo
sairia C). Peça sem curva no Fracttal: "sem curva", nunca C; a aba Cadastro a corrigir ganha a linha "N peças com saldo sem
Curva ABC no Fracttal" (e o mesmo para a criticidade), porque completar é no Fracttal.

## Partes do Nexus (inventário)

### 4. Pedir recontagem só dos itens marcados
Na etapa 2 · Aprovação, a tabela ganha uma caixa de marcar por peça (e "marcar todas"), e o botão **"Pedir recontagem
das marcadas (N)"**, com um motivo para todas (obrigatório, cifrado, como hoje).
- **(decisão)** Só se marca o que hoje já aceita ação (`revisao.py`, a peça com `id_item` fora da curadoria); o achado fora
  do catálogo e o genérico por identificar não têm `id_item` e seguem na curadoria. "Marcar todas" marca as marcáveis e é
  sempre PARCIAL. O "Pedir recontagem" da contagem inteira de hoje (`recontagem_pedida`, que mata a contagem) continua como
  botão à parte, com o nome "Recontar a contagem inteira".
- Parcial = um evento `recontagem_item_pedida` por peça (com `id_item`, `codigo`, `id_almoxarifado`, o motivo só
  cifrado, `pessoa_hmac`, `usina_id`), no livro `nexus_almoxarifado_inventario`, na contagem em que foi pedido. A peça vai
  para "não será tocada" com "recontagem pedida em dd/mm" e sai do N do "Gravar". **O resto da contagem segue** e pode ser
  aprovado e gravado.
- O App lê esses eventos (o contrato do App, abaixo) e o técnico reconta só aquelas peças; a contagem nova chega com a
  coluna nova **"Recontagem de"** = o ID da contagem em que o pedido foi feito (se o PCM pede de novo numa recontagem R1, a
  R2 aponta para a R1).
- **Atendida** = existe contagem com "Recontagem de" = aquela contagem, contendo a peça, com "Contada em" depois do
  evento. Pedir de novo a mesma peça pedida e não atendida: 409.
- **A recontagem não substitui ninguém:** hoje `contas.substituidas` (contas.py:260-283) escolhe UMA "nova" por almoxarifado
  e marca as outras não gravadas como velhas. A regra nova: a recontagem fica FORA da escolha da nova (nunca substitui, e
  a original mais velha também não a substitui); ela só é substituída por uma contagem inteira com "Contada em" depois da
  dela. Teste com a ordem: original pendente, recontagem chega, as duas vivas; uma inteira nova chega, as duas
  substituídas.
- A recontagem é uma contagem como as outras: mesma aprovação, mesmo conflito pelo histórico do Fracttal desde a hora dela.

### 2 e 3. Curadoria com fabricante, modelo, número de série e as fotos
- Colunas novas no FIM do livro das contagens: **"Fabricante"**, **"Modelo"**, **"Número de série"** (texto; "n/a" quando
  o técnico marca que a peça não tem) e **"Fotos dos dados"** (as chaves das fotos, `fabricante:<chave>|modelo:<chave>|
  serie:<chave>`, só das que existem). A coluna "Foto" de hoje continua sendo a foto da peça.
- **Uma rota só recebe todas as fotos do inventário**, a "Foto" da peça (hoje "Pendente" em `curadoria.py`) e as dos
  dados: `POST` assinado por HMAC no molde do extintor (`nexus/hseq/fotos.py`, `receber`; a rota dele em
  `nexus/torres/hseq/__init__.py`), mas com a validação própria: a chave é a que o App pôs na coluna (a "Foto" ou uma das
  "Fotos dos dados"), sem o `CODIGO` em maiúsculas nem o `dia` do extintor, e a mesma chave reenviada substitui. A pasta
  é a de hoje, `<NEXUS_DADOS>/almox_inventario/fotos/<nome_da_foto(chave)>.jpg`, com a miniatura. Rota pública declarada
  em `ROTAS_PUBLICAS` com o teste (o precedente no PCM é o `torre_pcm.motivo_do_app`). Servidas só com login e só a quem
  pode revisar (`pode_programar`), pela rota de hoje (`.../curadoria/foto/<nome>.jpg`).
- Na Curadoria, cada achado mostra os três dados (ou "n/a") e as miniaturas; o clique **amplia** a foto por cima da
  tela (Esc fecha, setas passam entre as fotos do mesmo achado, foco preso na caixa e devolvido ao fechar). Sem a foto no
  Nexus ainda: "foto ainda não chegou".
- Ao cadastrar no Fracttal pela curadoria, fabricante, modelo e série vão para os campos do item que o Fracttal tiver
  para isso; se não tiver, para a descrição do item **(o builder confere no `item_insert` do passo 0 e escreve no
  passo 0 o que achou; sem campo nenhum, não grava e a tela diz)**.

### 5. Avariados na contagem
- Tipo novo no livro das contagens: **`avariado`**. A linha traz o item BOM (`ID do item`, `Código`) e no "Contado" as
  unidades avariadas que o técnico achou.
- O Nexus acha o avariado pelo código: o item do catálogo com o código `<código do bom>-AV` (sem caixa e sem espaço),
  pelo adaptador na ponte (`achar_peca`). Achou: a linha conta para o -AV, como uma peça qualquer da contagem (ligar ao
  almoxarifado se preciso, contagem absoluta, em branco não zera). Não achou: vai para a Curadoria como **"avariada sem
  cadastro"**, com o "cadastrar" já preenchido (`<código>-AV`, o nome no padrão dos -AV que já existem no catálogo, a
  unidade do bom; o builder confere o padrão nos -AV de hoje) ou "é a peça X" ou descartar.
- A mesma contagem com o -AV contado direto (tipo `item`) E pela aba Avariados: **"contado em dobro"**, fora do lote até
  o PCM corrigir (como o "contado inválido" de hoje) **(decisão: somar contaria duas vezes a mesma peça)**.
- Avariado nunca tira do bom sozinho: a contagem do bom é a da linha dele. O técnico conta as boas na lista e as
  avariadas na aba; o grupo "para baixo" da Aprovação mostra a queda do bom como qualquer outra.

## O que muda para o App (contrato; o trabalho é da sessão do App)

Atualizar `C:\GridcoBuild\app-campo-docs\_propostas\inventario-contagens\CONTRATO.md` e a proposta da varredura
(`_propostas/almoxarifado-nexus`). Coluna nova só no FIM, dos dois lados; o teste do pacote do App compara.
1. **Contagens** (`almoxarifado_contagens_app_campo`): colunas novas no fim, nesta ordem: "Fabricante", "Modelo",
   "Número de série", "Fotos dos dados", "Recontagem de". Tipo novo `avariado`. Na tela do App: na peça fora do catálogo
   (e no genérico a identificar), fabricante, modelo e número de série, cada um com "n/a"; foto obrigatória de cada um
   que não for n/a; a aba **Avariados** na contagem; a lista das **recontagens pedidas** (os eventos
   `recontagem_item_pedida` do livro do inventário que o App ainda não atendeu) para os técnicos da usina.
2. **Fotos**: o envio para o Nexus pela rota assinada nova (o mesmo segredo e o mesmo formato do extintor).
3. **Varredura diária**: "Criticidade" e "Curva ABC" no fim do livro Itens (os campos do cadastro da peça no Fracttal;
   vazio se a peça não tiver) e "Custo unitário" no fim do livro Saldo (o custo da peça naquele almoxarifado, como o
   Fracttal dá; vazio se não der, nunca 0).

O Nexus fica pronto ANTES do App e aguenta os livros sem as colunas novas (o que falta mostra "–" ou nada), como fez com
o livro das contagens.

## Governança (PRIORIDADE 0)

- Criticidade, curva e custo entram no histórico do banco: criticidade e curva na dimensão do item, custo no fato do saldo (o
  `nexus/dados/CLAUDE.md` e o `catalogo.py` primeiro, com o grão escrito). Custo em claro está ok (não é dado pessoal).
- Os eventos novos (`recontagem_item_pedida`) seguem o livro do inventário: motivo só cifrado, `pessoa_hmac`, `usina_id`
  com `usina_ligada_por`, `data_id`.
- As fotos ficam no disco do servidor, nunca no banco nem no git. Fabricante, modelo e série vão em claro no livro do App
  (dado de peça, como a "Descrição").

## Fora deste trabalho

Mudar a régua de 20% do Mínimo e máximo; ler requisições e saídas do Fracttal na tela; calcular curva no Nexus; o
destino da avariada (reparo, sucata) como fluxo.

## Prova

Testes em `tests/test_pcm_almoxarifado.py` e `tests/test_pcm_inventario_*.py` para cada regra acima (com o livro sem as
colunas novas e com elas), `test_prefixo`, nomes, cor por token. Os testes que fixam o contrato mudam junto (o
`test_dados_almoxarifado.py` fixa a última coluna do Saldo; o `test_pcm_inventario_contrato.py` fixa as 14 colunas).
Navegador: a cópia de prova com o `EstoqueFalso`, desktop
e 375 px, escuro e claro: as abas com as contas certas, o cartão aberto, Avariadas, a recontagem parcial, a curadoria com
as fotos ampliadas, a linha avariada e a "avariada sem cadastro". Atualizar o `nexus/pcm/CLAUDE.md` (seções do
Almoxarifado e do inventário) no mesmo trabalho.
