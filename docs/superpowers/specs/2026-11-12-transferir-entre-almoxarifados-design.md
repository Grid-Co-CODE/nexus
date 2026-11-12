# Transferir peça entre almoxarifados (PCM → Almoxarifado) — desenho curto

Pedido do PCM (Spare Parts), de 04/11/2026, validado pela coordenação. Aprovado pelo Levi em 12/11/2026 ("Sim, segue";
no quiz: o vínculo com 0 e 0, a prova nos dois almoxarifados de teste, o desenho aprovado).

## Por quê
Desde 04/11/2026 toda usina tem almoxarifado no Fracttal, e os novos nasceram vazios: a peça passou a circular entre
usinas do mesmo cliente. O Fracttal só transfere para um almoxarifado onde a peça já está vinculada (recusa com "Alguns
itens não foram ligados ao almoxarifado de destino"). Sem o vínculo, o campo improvisou com saída "Geral" e ajuste de
inventário, que tiram a peça de um almoxarifado sem entrada em nenhum outro.

A peça **instalada** em outra usina é baixa na OS, pelo App de Campo ("Peça de outro almoxarifado", no ar na v339). Esta
tela é para a peça **guardada** em outra usina: ela mudou de lugar e continua em estoque.

## O que entra
- Uma aba **Transferir** em PCM → Almoxarifado, ao lado de Requisições e de Usinas e almoxarifados.
- O PCM escolhe a origem, a peça (só as que têm saldo na origem), o destino (só os almoxarifados do mesmo cliente), a
  quantidade e, se quiser, a OS ou a referência.
- **Conferir** mostra o que vai acontecer antes de gravar: o saldo da origem e do destino de agora, o de depois, e se o
  Nexus vai vincular a peça ao destino.
- **Transferir** grava no Fracttal com o login de quem clica: relê os dois saldos, vincula a peça se faltar, lança a
  Transferência entre almoxarifados e relê os dois saldos. O destino que exige aprovação de transferência fica de fora (as
  regras, abaixo).
- Os almoxarifados das listas são os do Fracttal, lidos na hora (a lista dos almoxarifados, com o login de quem está na
  tela): o livro Saldo da varredura do App só tem os almoxarifados com peça, e o destino típico é o novo, vazio. O
  inativo não aparece.
- A auditoria guarda o vínculo criado, a transferência e o saldo antes e depois de cada almoxarifado.
- O livro de peças do App ganha, no Nexus, a 15ª coluna ("ID do almoxarifado da usina da OS") e a marca "de outro
  almoxarifado" onde o PCM vê as peças usadas.

## O que não entra
- Transferência entre clientes diferentes: é empréstimo e passa pela coordenação. A tela recusa com o motivo.
- Várias peças numa transferência só: uma por vez, como o pedido.
- Mexer no inventário ou no App.

## O que seria um fracasso mesmo funcionando
- A peça sair da origem e não entrar no destino sem a tela dizer.
- A mesma transferência lançada duas vezes porque a resposta do Fracttal demorou.
- O Nexus dizer que o Fracttal tem o que ele não tem.

## Caminhos considerados
1. **Aba com formulário e histórico (o escolhido).** O saldo é lido no Fracttal na hora, e o histórico fica na mesma tela.
2. **Botão "Transferir" em cada peça da tabela de saldo.** A tabela vem da varredura diária do App: o saldo dela pode
   ter até um dia, e a transferência pede o saldo da hora. Pode virar atalho para a aba depois.
3. **O Nexus só vincula, e o PCM transfere pela tela do Fracttal.** Mais barato, mas mantém os dois passos e não deixa a
   auditoria com os saldos.

## As regras
- **Mesmo cliente:** o primeiro nó do caminho do local do almoxarifado no Fracttal (`location_description`, "// Cliente/
  Cliente - Usina - UF/ "), comparado sem acento e sem caixa (`transferencia.cliente_do_caminho`; não o
  `almox_usinas.cliente_do_local`, que corta o nome da usina). O almoxarifado de um nó só (o de teste) tem o próprio nó como
  cliente; o sem nó (o desativado) é cliente desconhecido. Cliente desconhecido de qualquer um dos dois lados é recusa.
- **A aprovação no destino:** medido no Fracttal de verdade em 12/11/2026, nenhum dos 183 almoxarifados tem o
  `transfer_approval` ligado, e a aprovação da entrada não tem como ser provada. O Nexus não a faz: se o destino exige
  aprovação de transferência, o Conferir e o Transferir recusam antes de qualquer gravação ("O almoxarifado de destino exige
  aprovação de transferência no Fracttal, e o Transferir do Nexus ainda não cobre esse caso: faça pela tela do Fracttal.").
- **Inativo:** o almoxarifado inativo no Fracttal não entra como origem nem como destino.
- **Quantidade:** maior que zero e no máximo o saldo lido na hora; inteira na unidade inteira e com duas casas em METRO e
  MASSA (a mesma leitura da régua).
- **Vínculo com 0 e 0** (Levi, 12/11/2026): o pedido falava em mínimo e máximo pela régua de 14/10, mas a decisão de
  26/10/2026 segue valendo: só o acordado vai ao Fracttal. A sugestão da régua aparece na aba Mínimo e máximo.
- **A aprovação no destino:** o Fracttal deixa cada almoxarifado exigir a aprovação da transferência que chega. Onde
  exigir, o Nexus aprova logo depois de lançar, com a mesma conta, pela regra do aceite das requisições (um clique faz
  tudo). É escolha de quem desenhou, achada depois da aprovação do desenho: a confirmar com o Levi e na prova.
- **Uma de cada vez** por peça em cada um dos dois almoxarifados: outra transferência da mesma peça que toque a origem
  ou o destino espera, senão a releitura da primeira não bateria. Almoxarifado em sessão de ajuste (o inventário gravando) recusa.
- **A resposta incerta não se repete:** cada transferência leva um código do Nexus na nota do movimento. Se a resposta
  não vier, o Nexus procura o código no histórico do almoxarifado: achou, registra como feita; não achou, libera de novo.
  Enquanto não souber, a tela diz "pode ter feito: confira no Fracttal" e não manda outra.
- **Só no servidor** e só o PCM e o administrador, pela ponte do inventário (`/os/_nexus/inventario`), como as
  requisições.

## Os dados (PRIORIDADE 0)
Os eventos vão para o `fato_evento_inventario`, que já é "1 linha = 1 evento de um almoxarifado e peça", com tipos novos
no fim da lista: o vínculo criado no destino, a saída na origem e a entrada no destino (cada uma com o saldo de antes e
de depois e o movimento do Fracttal), a falha e a trava. As linhas de uma transferência levam o mesmo código no `lote`.
Nenhuma coluna nova. O catálogo e o `nexus/dados/CLAUDE.md` são corrigidos no mesmo trabalho.

## A prova
- Testes com o Fracttal simulado, inclusive a resposta incerta, a peça sem vínculo e a recusa do destino que exige aprovação.
- No Fracttal de verdade, só nos dois almoxarifados de teste, com a peça de teste: transferir, ler de volta e desfazer.
- A tela em desktop e 375 px.

## O que fica com quem constrói
Os nomes dos tipos de evento, o texto do "!" e o desenho fino do formulário, dentro do `DESIGN.md`.
