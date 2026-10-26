# Inventário do almoxarifado no PCM — desenho (26/10/2026)

Levi, 26/10/2026, com o mockup Spare Parts R01 do PCM (as 4 telas: contagem, aprovação, gravação, auditoria):
"gostaria dessa visão de almoxarifado no nexus pcm"; e, sobre o celular do mockup: "a minha ideia é que a pessoa vá
na parte de ronda, selecione a usina e tenha a opção de fazer inventário de almoxarifado".

Este desenho é a continuação do Almoxarifado do PCM (`2026-10-25-almoxarifado-design.md`, no ar em ensaio): aquela
tela mostra o saldo que o Fracttal tem; esta acerta o saldo do Fracttal com o que o campo conta, com aprovação do PCM e
rastro de cada mudança.

## 1. Por que

O saldo do Fracttal não é confiável e nunca foi conferido em campo: o projeto Spare Parts do PCM mediu 17 saldos em
275 peças em 08/2026 (hoje são 222 peças com saldo em 12 almoxarifados, por cargas iniciais e ajustes feitos à mão pelo
conector do Claude). Sem inventário, o mínimo, a reposição e o consumo nas OS são contas em cima de um número que
ninguém viu na prateleira. O inventário põe o número contado no Fracttal, no nome de quem aprovou, com o antes e o
depois guardados.

O que já existe e este desenho reaproveita:
- **O projeto Spare Parts** (pasta `5.Documentos Técnicos/14. Spare Parts`, fora do repositório): o mockup, o catálogo
  limpo, a régua de estoque, as decisões de processo e as armadilhas da busca. As decisões de processo dele valem aqui
  (seção 3), menos duas que o Levi mudou em 26/10 (onde o painel fica e quem grava).
- **O App de Campo**: login, fila offline, a Ronda por usina, o catálogo dos itens e o almoxarifado de cada usina.
- **O Nexus**: o OS Creator já grava no Fracttal com o login da própria pessoa; o Almoxarifado do PCM já lê o saldo; o
  "Gerar a semana" já roda trabalho longo em segundo plano com o progresso na tela.

## 2. O que o Levi decidiu (26/10/2026)

| Ponto | Decisão |
|---|---|
| Onde se conta | No App de Campo: **Ronda → usina → "Inventário de almoxarifado"**. O App não grava estoque no Fracttal. |
| Onde se aprova e quem grava | No **Nexus**, PCM → Almoxarifado. O Nexus grava no Fracttal **com o login do Fracttal de quem aprovou** (como o OS Creator). |
| Quem aprova e grava | **Só o setor PCM** (outros setores só veem, pela marca em Base → Acessos). |
| 1ª entrega | Contagem, aprovação e gravação; régua de mínimo e máximo; curadoria do fora do catálogo; auditoria. |
| Régua | **Sugestão ajustável**: o Nexus propõe pela régua de 14/10 e o PCM muda peça a peça antes de gravar. |
| Curadoria | Aprovar a peça fora do catálogo **cadastra no Fracttal** (código, nome, unidade) e a liga ao almoxarifado com a quantidade contada. |
| Mínimo | **Recomendado pela Grid e acordado com o cliente são registros separados**; só o acordado vai ao Fracttal (`min_stock_level`, que dispara o alarme). |
| Acordado | **Mínimo e máximo**: o PCM registra os dois acordados, e os dois vão ao Fracttal; o recomendado da Grid também tem os dois, só no Nexus. |
| Inventário substitui | **O contado substitui o saldo, como num inventário normal** (Levi: "se a peça foi achada com 2 unidades e depois contada com 3 vai substituir [...] vira 3 ao invés de 2"): nunca soma ao saldo do Fracttal; a contagem mais nova de um almoxarifado vale sobre a mais velha. |
| Revisão do lote | O PCM pode **tirar uma peça do lote**, **pedir recontagem** (recusa a contagem inteira) e **corrigir o número contado**; cada um com o motivo, na auditoria. |
| Gravação que parou | **Só quem aprovou retoma**, e o resto continua no nome dela; nenhum login do Fracttal fica guardado no disco. |
| MCP | O Nexus não usa o conector MCP do Claude: chama direto a mesma API que o conector usa. |

## 3. Regras de processo (do Spare Parts, mantidas)

1. **Contagem cega**: o App não mostra o saldo do Fracttal; a divergência nasce no Nexus.
2. **Em branco não é zero**: só o zero digitado zera; a peça em branco não é tocada.
3. **Lista com busca**, sem cartões; a busca respeita os dígitos (2" não acha 4"; "1,2 kVA" não vira "1" e "2").
4. **Sem prateleira nem localização** (o estoque é do cliente).
5. **Fora do catálogo vira pendência** de curadoria: o campo descreve, fotografa e conta; quem cadastra é o PCM.
6. **Genérico com saldo** (hoje o SP-GER-003) entra como "identificar": o técnico, com a peça na mão, diz qual é.
7. **Aprovação antes de gravar**; toda gravação segue: mostrar antes, reler depois e registrar.
8. Código da peça nova: `SP-<SIGLA>-NNN` (as siglas do catálogo: PEL, PME, CAB, SEN, CTR, COM, INS, ARM, EAX, HSE,
   CSM, GER), no próximo número livre da sigla.

## 4. O fluxo

### 4.1 Contagem (App de Campo; quem constrói é a sessão do App)

A tela do celular é a tela 1 do mockup (as cores do mockup são de rascunho: no App valem as do App). A demanda foi
passada à sessão do App em 26/10. O que importa ao Nexus é o que chega pelo banco:

**`almoxarifado_contagens_app_campo` · `Contagens`** — 1 linha = 1 peça de uma contagem enviada (inclusive a pendência
fora do catálogo). Janela: a dos outros livros do App (90 dias); o Nexus guarda o resto.

| Coluna | O que é |
|---|---|
| ID da contagem | um por envio (o App gera; idempotente no reenvio da fila offline) |
| Enviada em | ISO UTC, a hora em que o servidor recebeu |
| Contada em | ISO UTC, a hora do celular em que a contagem foi aberta (a fila offline atrasa o "Enviada em"; é contra esta hora que se olha o que se moveu depois) |
| ID do almoxarifado | o do Fracttal |
| Usina | o nome da usina no Fracttal (como os outros livros) |
| Tipo | `item` (peça do catálogo), `identificar` (genérico com saldo), `fora_do_catalogo` |
| ID do item | vazio no fora do catálogo |
| Código | idem |
| Contado | número; **vazio = não contei** (nunca 0) |
| Identificado como | no genérico: o ID do item específico que o técnico escolheu (vazio se não soube) |
| Descrição | só no fora do catálogo: o que o técnico escreveu (descrição de peça, não de gente) |
| Foto | só no fora do catálogo: a chave da foto no App (o Nexus mostra pela rota de fotos do App, como as do extintor) |
| Contou (HMAC) | HMAC do e-mail de quem contou; nunca o e-mail |

Uma contagem "enviada" está completa (o App manda tudo de uma vez, no botão "Enviar contagem"); o Nexus não mostra
contagem pela metade. O genérico com saldo que o técnico achou ser de mais de um específico vai em uma linha por
específico (o mesmo código do genérico, com o "Identificado como" e o "Contado" de cada um). *Decisão do construtor.*

### 4.2 Aprovação (Nexus, PCM → Almoxarifado, aba "Inventário")

- A lista das contagens recebidas: usina, almoxarifado, quando, quantas peças contadas, em branco e na curadoria, e a
  situação (`nova`, `revisada`, `gravada`, `gravada com conflitos`).
- Abrir uma contagem: **Sistema × Contado × Δ × Situação**, como a tela 2 do mockup. O "Sistema" é o saldo do Fracttal
  **lido na hora** (uma leitura do almoxarifado inteiro), não o da varredura da madrugada: o saldo muda durante o dia.
- As seis situações: ajuste para cima, ajuste para baixo, zerar (0 digitado em peça com saldo), sem alteração, não será
  tocada (em branco) e curadoria (identificar e fora do catálogo).
- "Revisar lote" abre a confirmação nos seis grupos; só os três primeiros mexem no estoque. O botão diz "Gravar N
  alterações". O zerar fica aberto e destacado para conferência.
- Na revisão, o PCM pode **tirar uma peça do lote** (não grava; fica com o motivo), **pedir recontagem** (recusa a
  contagem inteira com o motivo; nada é gravado e o App pode contar de novo) e **corrigir o número contado** (o
  Fracttal recebe o número corrigido; a auditoria guarda o contado no campo, o corrigido, quem corrigiu e o motivo).
- A contagem mais nova de um almoxarifado **substitui** as mais velhas que ainda não foram gravadas (elas ficam como
  `substituída`, e não se aprovam mais): aprovar a velha depois da nova desfaria a nova.
- **O que se moveu depois da contagem** (uma peça lançada numa OS, uma entrada pela tela do Fracttal): a peça com
  movimento depois do "Contada em" vira **conflito** e não é gravada, para o ajuste não desfazer um movimento real. Como
  achar o movimento é parte do passo 0 (seção 6); enquanto não houver um jeito, a contagem só se aprova até 7 dias depois
  do "Contada em" e as peças lançadas pelo App depois dela (o `fato_peca_lancada`) viram conflito. *Decisão do
  construtor.*
- Situações da contagem: `nova`, `revisada`, `recontagem pedida`, `substituída`, `gravando`, `gravada`, `gravada com
  conflitos`.

### 4.3 Gravação (Nexus → Fracttal)

- **No nome de quem aprova**: pela sessão do Fracttal da pessoa (o login do Nexus pelo Fracttal abre a do OS Creator,
  `ponte.sessao_do_os`). Quem entrou pela senha de administrador não grava (a tela diz por quê).
- **Em segundo plano, com o progresso na tela**, como o "Gerar a semana" (uma gravação por vez por almoxarifado).
- **Em lotes de 50**, no ritmo da cota da empresa (o limite de 200/min é de toda a Grid: a gravação anda a ~1 pedido
  por segundo e para no 429, retomando depois).
- **Por peça**, antes de gravar: confere o saldo lido no início do lote com o saldo da aprovação; mudou → **conflito**,
  não grava e devolve ao PCM. A peça sem vínculo com o almoxarifado é ligada primeiro.
- **O movimento é de ajuste de inventário**, nunca de consumo nem de devolução (o consumo do Fracttal é a base da régua
  medida do Spare Parts; ajuste misturado com uso estraga o histórico do cliente). Se o Fracttal tiver um ajuste que
  grava o **saldo absoluto** (inventário físico), é o preferido: a gravação e a retomada ficam simples. Senão, entrada
  (para cima) e saída (para baixo e zerar) pelo Δ, com a referência `INVENTARIO-<contagem>` em cada movimento. O passo 0
  decide qual. *Decisão do construtor.*
- **Idempotente** por (contagem, código): o lote que cair recomeça da peça seguinte à última confirmada, nunca do
  início. Com movimento pelo Δ, antes de regravar uma peça "sem resposta" o Nexus procura no Fracttal o movimento com a
  referência dela: achou, está gravada; não achou, grava (sem isso, a resposta perdida duplicaria o movimento).
- **Só quem aprovou retoma** a gravação que parou (o servidor reinicia a cada subida): o login do Fracttal fica só na
  memória do trabalho; parado, o almoxarifado espera a pessoa voltar ao Nexus e apertar "Continuar", e o resto vai no
  nome dela.
- **Depois**: relê o almoxarifado e só marca a peça como gravada quando o saldo novo é o contado.

### 4.4 Régua de mínimo e máximo (aba "Mínimo e máximo")

- Por peça × almoxarifado: o saldo (da última contagem gravada; sem ela, o da varredura), a **sugestão** da régua de
  14/10 e dois números editáveis: o **recomendado** (Grid) e o **acordado** (cliente).
- A régua de 14/10: mínimo = 20% do saldo, máximo = 2× o saldo; a peça avariada (`-AV`) fica sem mínimo e com máximo
  3× o saldo.
- O recomendado (mínimo e máximo) fica no banco do Nexus (com quem e quando). **Só o acordado (mínimo e máximo) vai ao
  Fracttal**, no vínculo da peça com o almoxarifado; enquanto o PCM não registra o acordado, o Fracttal não muda.
- A mesma regra de gravação: mostrar, aprovar, gravar no nome de quem aprova, reler, registrar.

### 4.5 Curadoria (aba "Curadoria")

- Fora do catálogo: a descrição, a foto e a quantidade contada. O PCM decide: **cadastrar** (o Nexus cria a peça no
  Fracttal com código `SP-<SIGLA>-NNN`, nome e unidade, liga ao almoxarifado e dá a entrada da quantidade contada),
  **é a peça X** ou **descartar** (com o motivo). No "é a peça X", as unidades achadas são unidades de X contadas nessa
  mesma contagem: o contado de X passa a ser a linha dela mais as achadas, e esse total **substitui** o saldo de X no
  Fracttal (o inventário substitui, não soma). *Decisão do construtor, pela regra do Levi.*
- Genérico a identificar: o específico que o técnico escolheu, para o PCM confirmar; confirmado, as unidades **saem do
  genérico e entram no específico** (somadas ao contado dele nessa contagem), para o estoque não ficar em dobro.
  *Decisão do construtor.*
- Grupo e criticidade da peça e a Curva ABC **não** se gravam pela API (o conector descarta; testado pelo PCM em 09/10):
  a tela lembra o PCM de completar na tela do Fracttal.

### 4.6 Auditoria (aba "Auditoria")

Uma linha por evento, que nunca muda: contagem recebida, aprovação, peça gravada (de → para e o número do movimento
devolvido pelo Fracttal), conflito, erro, curadoria decidida, régua gravada. Filtro por tipo e busca. É também o
histórico que o PCM usa para defender o mínimo recomendado.

## 5. A base no Nexus (governança)

Registrar no `catalogo.py` antes de gravar (a regra da casa):
- **Fonte** `contagem_inventario` (o livro do App, seção 4.1): estado `origem`; usina pelo nome do Fracttal; pessoa pelo
  HMAC; item como `prop` (o mesmo do Almoxarifado).
- **Livro novo do Nexus `nexus_almoxarifado_inventario`**, só cresce (`so_cresce`):
  - `fato_evento_inventario`: 1 linha = 1 evento (seção 4.6), com `data_id`, `usina_id`, `pessoa_id` (de quem
    aprovou ou contou), `id_almoxarifado`, `id_item`, `de_qtd`, `para_qtd`, `movimento_fracttal`, `contagem_id`, o tipo
    do evento e a situação; nada de nome, e-mail nem texto livre (a descrição do fora do catálogo fica só no livro do
    App).
  - `fato_regua_minimo`: 1 linha = 1 decisão do PCM sobre o recomendado ou o acordado de uma peça num almoxarifado
    (vale a última), com quem e quando.
  - `fato_curadoria`: 1 linha = 1 decisão de curadoria (cadastrar, é a peça X, descartar), com o código criado.
  - Os eventos da revisão também vão ao `fato_evento_inventario`: peça tirada do lote, recontagem pedida, número
    corrigido (o contado no campo e o corrigido), contagem substituída.
  - `qualidade` e `atualizacao`.
- O estado do trabalho em andamento (o lote, o ponto de retomada) fica na pasta de dados do Nexus, não no banco: é
  controle, não dado de negócio.
- Nome de colega em lugar nenhum do repositório (os documentos do Spare Parts citam pessoas: aqui, só o papel).

## 6. A API do Fracttal (o passo 0)

O conector MCP do Claude usa a mesma API JSON-RPC que o App e o OS Creator já chamam: os nomes das ferramentas são os
métodos com "_" no lugar do ponto (`inventories_items_list` = `inventories.items_list`, que o App usa todo dia). O que
este desenho usa, **inferido dos nomes, a confirmar antes do plano**:

| Para | Método provável | Situação |
|---|---|---|
| Os almoxarifados | `warehouses.list` | a confirmar (leitura) |
| O saldo, o mínimo e o máximo de um almoxarifado inteiro | `warehouses.items_stock` (`id_warehouse`) | a confirmar (leitura); o conector já usou |
| O catálogo de peças | `inventories.items_list` (`id_type_item = 4`) | **em uso** pelo App |
| Ligar a peça ao almoxarifado, com mínimo e máximo | `warehouse.item_stock_associate` | a confirmar (gravação) |
| Entrada de estoque | `warehouses.entries` | a confirmar (gravação); o PCM já gravou `INVENTORY_INITIAL` e `RETURN` |
| Saída de estoque | `output.insert` | a confirmar (gravação); o PCM já gravou uma saída de ajuste |
| Peça nova | `inventories.item_insert` | a confirmar (gravação); o PCM já cadastrou peça |

O passo 0 confirma as leituras com 2 ou 3 chamadas, com o login do Fracttal de quem é do PCM, e descobre:
- o formato exato de cada gravação, pela tela do Fracttal (como o OS Creator descobriu os dele);
- se existe um ajuste de inventário que grava o saldo absoluto (seção 4.3);
- se existe uma leitura dos movimentos de um almoxarifado por data (para o conflito do que se moveu depois da contagem).

**A prova das gravações é num almoxarifado de teste**, nunca num de usina, debaixo do cliente de teste que o Fracttal
já tem (o "teste - pa", que o OS Creator esconde). Ele fica fora das contas e das telas pelo ID (no Nexus, numa chave do
`.env`; no App, numa App Setting), e a peça de teste usa a sigla `SP-TST-NNN` e é desativada depois. Criar esse
almoxarifado e essa peça no Fracttal pede o OK do Levi. *Decisão do construtor.*

## 7. Ordem da entrega

1. **Passo 0**: a API confirmada (seção 6) e o almoxarifado de teste.
2. **O contrato** do livro das contagens (4.1), combinado com a sessão do App antes de qualquer um construir.
3. **O Nexus**: catálogo; as abas Inventário, Mínimo e máximo, Curadoria e Auditoria; a gravação em segundo plano;
   testes com o Fracttal de mentira; a prova da gravação no almoxarifado de teste.
4. **O App**: a tela da contagem (a sessão do App, com o OK do Levi para o deploy).
5. **Piloto** num almoxarifado de usina que o PCM escolher; depois, os outros.

Push na `main` e deploy do App, cada um só com o OK do Levi.

## 8. O que fica de fora (e por quê)

- **O resumo semanal ao cliente por e-mail** (decidido no Spare Parts; não está na 1ª entrega).
- **A baixa de material obrigatória no fechamento da OS** (anda sozinha, no App).
- **Entrada por compra, transferência entre almoxarifados e custo**.
- **Grupo, criticidade e Curva ABC da peça** (a API não grava; na tela do Fracttal).
- **Consulta de estoque pelo campo** (o campo consome peça pelo Fracttal; o Spare Parts decidiu não fazer).
- **Tornar a varredura do App mais barata** com o `warehouses.items_stock` (12 chamadas no lugar de 574): melhora a
  cota, mas é trabalho do App, depois do passo 0.
