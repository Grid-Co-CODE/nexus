# Engenharia: a OS do Quadro da equipe (24/10/2026)

## O pedido

Levi, em Engenharia > Quadro da equipe: "Ao clicar quero uma visão parecida com o que aparece quando clica na OS da parte
de CHAMADOS > GARANTIA", com as diferenças:

1. os KPIs do início adaptados à engenharia;
2. no lugar do "Ticket de fornecedor", a pessoa da engenharia edita um status, entre os oito do anexo: Análise de
   Solução, Atividade em Andamento, Diagnóstico em Andamento, Agendamento de OS, Tratativa com Equipe de Campo,
   Validação Final, Stand-By, Diagnóstico Concluído;
3. todo comentário da engenharia vai para a nota da OS, com a data e a hora do comentário;
4. a prioridade: média, alta e urgente;
5. a OS sem atualização nos últimos 7 dias pulsa em laranja, com a sombra em camadas que ele mandou
   (`--shadow-elevation-medium`), "o crispy pulsando de 0.5 a 1";
6. no lugar do "Abrir OS", o "Solicitar OS": a Nova solicitação já com o ativo da OS (dá para trocar) e esta OS como
   OS pai;
7. o "Demais respostas do técnico" mostra a resposta da subtarefa "Descreva a atividade realizada" da OS filha (a do
   item 6).

## Como fica (decisões tomadas pelo jeito que o Nexus já faz)

- **A tela:** `/t/engenharia/equipe/os/<nº da OS>`, página inteira como a do chamado da Garantia (cabeçalho com a etiqueta
  e o botão, os quatro números, à esquerda o que a engenharia FAZ e à direita o que ela LÊ), no desenho do Nexus (tokens,
  os dois temas, 375 px). O clique no cartão do quadro abre esta página no lugar do card do OS Creator.
- **Os números:** Status (o da engenharia), Prioridade, Programada (com atrasada, vence ou abre em) e Última atualização
  (há quantos dias; laranja a partir de 7).
- **Status e prioridade moram no banco do Nexus**, num livro novo, `nexus_engenharia_os` (registrado no catálogo antes de
  existir, só cresce): `fato_acompanhamento_os` (1 linha = 1 evento numa OS: status, prioridade ou comentário), com os
  IDs da OS, do ativo e da usina e quem fez como HMAC; o texto do comentário e o nome vão cifrados. As listas fixas
  vão no próprio livro (`dim_status_os` e `dim_prioridade_os`), para o banco dizer o que cada número quer dizer. Sem
  padrão: a OS sem escolha mostra "—".
- **A prioridade é a da engenharia**, não a criticidade do Fracttal (o Fracttal não deixa mudá-la depois de criada pelo
  caminho que o OS Creator usa); a do Fracttal aparece nos Dados.
- **O comentário vai para a nota da OS no Fracttal** pelo caminho do card do OS Creator (`api.editar_nota_os`, na sessão
  do Fracttal da pessoa), acrescentado no fim: `[24/10/2026 14:32] Nome (Engenharia): texto`. Sem o login do Fracttal,
  a tela pede para entrar por ele e nada é gravado. OS concluída, cancelada ou de várias tarefas o Fracttal não deixa
  editar (a regra medida do OS Creator: com várias tarefas a nota sobrescreveria a tarefa errada): aí o comentário
  fica só no Nexus, e a tela diz por quê. Erro do Fracttal: nada gravado.
- **Última atualização** = o mais novo entre o último evento da engenharia na OS, a criação da OS e as datas de início e
  fim das tarefas dela no Fracttal. Pulsa só a OS aberta (a fazer, em execução, em verificação).
- **O pulso:** a sombra em camadas do Levi com a cor por token (`--pulso`, em H S L, nos dois temas), numa camada por
  cima do cartão cuja opacidade vai de 0,5 a 1 e volta; com "reduzir movimento", fica parada em 1.
- **Solicitar OS:** abre `/os/solicitacao?ativo=<código>&os_pai=<id>&os_pai_folio=<nº>`; a Nova solicitação do OS
  Creator passa a aceitar a sugestão (cliente, usina e o ativo marcado; a OS pai escolhida). Vai ao oem pela
  `sincronizar_oscreator` com o OK do Levi.
- **Demais respostas do técnico:** as OS filhas (o REST filtra por `id_parent_wo`, medido em 24/10) e, de cada uma, a
  resposta de "Descreva a atividade realizada" (`work_orders_subtasks`). Sem filha: o aviso de usar o Solicitar OS.
- **Quem mexe:** o setor Engenharia e o administrador, com login de pessoa (como no acompanhamento dos ativos); os demais
  leem.

## Fora

- Trocar a criticidade do Fracttal, e as ações do card do OS Creator (trocar o responsável, concluir, cancelar) nesta
  página: o card continua no Histórico do OS Creator, e os Dados têm o link da OS no Fracttal.
