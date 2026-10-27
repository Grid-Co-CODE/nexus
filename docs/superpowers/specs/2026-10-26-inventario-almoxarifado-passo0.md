# Inventário do almoxarifado: o resultado do passo 0 (a API do estoque do Fracttal)

Feito em 26/10/2026, com o Levi logado no Fracttal no navegador do app, lendo as requisições da própria tela
(`POST /rpc/proxy`, JSON-RPC 2.0 em lote: `[{"id", "jsonrpc": "2.0", "method", "params"}]`). As gravações foram todas no
almoxarifado de teste, cada uma com o OK do Levi ("Pode, já entrei"). Desenho: `2026-10-26-inventario-almoxarifado-design.md`
(seção 6, que este arquivo substitui na parte dos métodos).

## O que se decidiu

- **Há ajuste absoluto: sim.** Mas não é um movimento por peça: é um **modo do almoxarifado** ("Ajuste de inventário",
  modo 2). Com o modo aberto, o saldo de cada peça é gravado como número (`stock: 5`); ao concluir, o Fracttal gera, para
  cada peça mexida, um par de movimentos do tipo 15 ("Ajuste de inventário"): uma **saída do saldo antigo inteiro** e uma
  **entrada do saldo novo** (3 → 2 virou saída de 3 e entrada de 2), todos com a `description` passada no fechamento.
  É o preferido do desenho (seção 4.3): gravar é idempotente (gravar 5 duas vezes dá 5) e a referência
  `INVENTARIO-<contagem>` vai na `description` do fechamento.
- **Enquanto o modo está aberto, o almoxarifado trava Entradas, Saídas e Pedidos de compra** (a tela some com eles e
  avisa "você pode fazer movimentos uma vez que o processo está completo"). A gravação abre, grava e fecha no mesmo
  trabalho, e a retomada começa fechando um modo que ficou aberto. **Caso real:** o `ATHN-MTS200` (Athon - Matões 200)
  estava em 26/10 em "Inventário físico" (modo 3), com Entradas e Saídas travadas (não foi esta prova que o abriu).
- **Há leitura de movimentos por data: sim** (`inventories.movement_history_list_new`, ordenada por `date_create`). O
  conflito "a peça se moveu depois da contagem" sai dela, e não da janela de 7 dias do desenho.
- **Os erros vêm no corpo, com HTTP 200:** `result.success = false` e `result.message` (ex.: `ASSET_CANNOT_BE_DESABLED_STOCK`).
  O adaptador confere o `success` de toda resposta.
- **Peça com saldo não se desativa** (`ASSET_CANNOT_BE_DESABLED_STOCK`): para desativar, zera-se antes pelo ajuste.

## O almoxarifado e a peça de teste

| O quê | Valor |
|---|---|
| Almoxarifado de teste | `TESTE-INVENTARIO`, id **134082**, local `TESTE - PA` (id 43128211), `visible_to_all: false` |
| Peça de teste | `SP-TST-001` ("Peça de teste do inventário (Nexus)", UNIDADE), id do item **53248312** |
| Ligação peça × almoxarifado | id **15535397** (ligada com mín. 1 e máx. 4; depois da prova da régua, mín. 2 e máx. 6); saldo 5 |
| Movimentos da prova | MOV-1/MOV-2 (0 → 3), MOV-3/MOV-4 (3 → 2), MOV-5/MOV-6 (2 → 5), todos do tipo 15 |

`NEXUS_ALMOX_TESTE_IDS=134082` no `.env` do Nexus (e a App Setting equivalente no App) tira esse almoxarifado das telas.
A peça **continua ativa**: o Fracttal recusou desativá-la com saldo 5 (ver acima).

## Os métodos, por operação do adaptador (Task 2)

Todas as chamadas abaixo são as que a tela do Fracttal faz; o corpo mostrado é o mínimo que a tela mandou.

### Ler os almoxarifados — `inventories.warehouses_list`

`{"filter": [], "sort": [], "page": 1, "limit": 200, "start": 0, "is_tree": false, "node": null}` →
`data[]`: `id`, `code`, `description`, `id_location`, `location_description` (`"// Cliente/ Cliente - Usina - UF/ "`),
`code_location`, `mode` (0 normal, 2 ajuste de inventário, 3 inventário físico), `active`, `allow_negative_stock`; `total`.
23 almoxarifados em 26/10 (os da Athon estão com `active: false` e mesmo assim têm estoque e movimentos).

### Ler o saldo de um almoxarifado — `inventories.warehouses_items_stock`

`{"filter": [], "sort": [], "page": 1, "limit": 200, "start": 0, "is_tree": false, "node": null, "id_warehouse": 134082}` →
`data[]` (uma linha por peça ligada): `id` (**a ligação**, usada para gravar), `id_item`, `code`, `field_1` (o nome),
`id_type_item` (4 = peça), `active`, `stock`, `min_stock_level`, `max_stock_level`, `reorder_level`, `stock_temp`,
`qty_assigned`, `lots[]`; `total`. Exemplo (a peça de teste depois da prova):

```json
{"id": 15535397, "id_item": 53248312, "code": "SP-TST-001", "id_type_item": 4, "active": true,
 "id_warehouse": 134082, "stock": 5, "min_stock_level": 1, "max_stock_level": 4, "reorder_level": 0,
 "stock_temp": 0, "qty_assigned": 0, "units_description": "UNIDADE"}
```

Uma leitura traz o almoxarifado inteiro (até 200 por página): é a leitura "na hora" da revisão e a releitura depois de
gravar. A peça que nunca foi ligada ao almoxarifado não vem.

### Ligar a peça ao almoxarifado — `inventories.associate_warehouses_insert`

`{"id_warehouse": 134082, "id_item": 53248312, "location": "", "stock": 0, "min_stock_level": "1",
"max_stock_level": "4", "reorder_level": 0}` (a tela manda também um `id`/`idInternal` UUID, a descrição do almoxarifado,
custos zerados e datas) → `data.id` = a ligação (15535397), com `stock: 0`. O saldo entra depois, pelo ajuste. Lista das
ligações de uma peça: `inventories.associate_warehouses_list` (`{"id_item": ...}`).

### Ajustar o saldo (absoluto) — a sessão de ajuste

1. Abrir: `inventories.warehouse_change_mode` `{"id_warehouse": 134082, "mode": 2}` e, logo depois,
   `inventories.warehouse_update` `{"id": 134082, "mode": 2}` (a tela chama os dois, nessa ordem).
2. Para cada peça: `inventories.warehouses_items_update` `{"id": <ligação>, "stock": 5}` → `data: null`. O `stock` da
   leitura já mostra o número novo antes do fechamento.
3. Fechar: `inventories.warehouse_finalize_mode` `{"id_warehouse": 134082, "description": "INVENTARIO-<contagem>"}` →
   `data: {"folio_return": 7, "total": 0}` (o próximo número de movimento do almoxarifado), e depois
   `inventories.warehouse_update` `{"id": 134082, "mode": 0}`.

A tela manda como `description` o nome do almoxarifado; o campo é texto livre (os ajustes por API de 08/10 têm
descrições próprias, e o `document` deles também veio preenchido, ex. `MESCLA-DUPLICATAS-0810`; mandar o `document` no
fechamento **não foi provado**). **O fechamento só gera par para a peça mexida** (provado em 27/10: com a SP-TST-002 ligada
e parada, zerar só a SP-TST-001 deu o par MOV-9/MOV-10 só dela). Num fechamento com várias peças, todas as saídas levam o
MESMO folio e todas as entradas o seguinte (a gravação do Nexus de 27/10 deu MOV-7 nas duas saídas e MOV-8 nas duas
entradas), com a `description` = a referência.

### A prova pelo Nexus no Fracttal de verdade (27/10/2026, com o login do Levi, só no almoxarifado de teste)

Numa cópia de prova com uma contagem de mentira (nunca no banco da API): a curadoria cadastrou a peça nova pelo Nexus
(`SP-TST-002`, id 53279817: `companies.units_list`, `inventories.items_list` e `item_insert` provados); a gravação abriu a
sessão, ligou a peça nova, gravou 5 → 3 e 0 → 1, fechou com `INVENTARIO-PROVA-TST-1-L1`, voltou ao modo 0 e a releitura
confirmou as duas (eventos `peca_gravada` com o movimento 7); a régua mandou só o acordado (mínimo 1, máximo 5), conferido na
releitura e na tela do Fracttal. Depois, pela tela do Fracttal, as duas peças de teste foram zeradas e desativadas.

### Achar o movimento e o que se moveu — `inventories.movement_history_list_new`

`{"sort": [{"property": "date_create", "direction": "desc"}], "page": 1, "limit": 200, "start": 0, "is_tree": false,
"node": null, "id_warehouse": 134082}` → `data[]`: `id_movements`, `folio` (`MOV-6`), `id_item`, `code`,
`id_movement_type` (15 = ajuste de inventário; aparecem também 1, 2, 4, 5 e 14), `id_movement_state` (1 = entrada,
2 = saída), `id_warehouse_source`/`id_warehouse_target`, `qty`, `date` (dia), `date_create` (ISO com fuso),
`description`, `document`, `responsible_description` (**nome de pessoa: nunca guardar**), `total`. Exemplo:

```json
{"folio": "MOV-6", "id_movements": 84367873, "id_item": 53248312, "code": "SP-TST-001",
 "id_movement_type": 15, "id_movement_state": 1, "id_warehouse_source": null, "id_warehouse_target": 134082,
 "qty": 5, "date": "2026-10-26", "date_create": "2026-10-26T15:00:16.570424+00:00",
 "description": "teste - pa - Inventário (teste do Nexus)", "document": "---", "responsible_description": "PESSOA"}
```

- `achar_movimento(referencia)`: o movimento com `description == referencia` (confirma um fechamento cuja resposta se
  perdeu).
- `mexidas_desde(desde)`: as peças com `date_create` depois do "Contada em", tirando os movimentos do próprio ajuste.
  A lista vem do mais novo para o mais velho: lê página a página até passar da data. Filtro por data no pedido não foi
  testado.

### Criar a peça — `inventories.item_insert`

`{"id_type_item": 4, "field_1": "<nome>", "code": "SP-TST-001", "id_unit": 362334, "units_description": "UNIDADE",
"active": true, "description": "", "is_serial_control": false, "is_lot_control": false, "visible_to_all": false,
"ids_batch": [], "associate_warehouses": [], "associate_third_parties": [], "attached": [], "files": [],
"custom_fields": []}` → `data: {"id": 53248312, "description": "<nome>    { SP-TST-001 }"}`. As unidades vêm de
`companies.units_list` (`UNIDADE` = 362334, a das peças do catálogo).

### Desativar a peça — `inventories.item_update`

`{"id": 53248312, "active": false, ...}` → com saldo, `success: false`, `message: "ASSET_CANNOT_BE_DESABLED_STOCK"`.

### Os códigos que já existem — `inventories.items_list`

`{"filter": [], "sort": [], "page": 1, "limit": 200, "start": 0, "is_tree": false, "node": 0, "id_type_item": 4}` (o que
a tela de Peças e Suprimentos chama; o App já usa o mesmo método) → `data[].code`; 629 peças em 26/10.

### Mudar a régua (mínimo e máximo) — `inventories.warehouses_items_update`

`{"id": 15535397, "min_stock_level": "2", "max_stock_level": "6"}` → `data: null`. Provado em 26/10 (com o OK do Levi),
**fora do modo de ajuste**: não gera movimento, e a releitura deu mínimo 2, máximo 6 e saldo 5. É a tela Estoque →
a peça, com o saldo bloqueado e os dois níveis editáveis.
