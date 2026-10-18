# A Visão geral na Visão do responsável (desenho)

Levi, 18/10/2026, olhando a Visão do responsável: "consegue criar uma visão onde unifica todas as usinas? aí teria os
KPIs de performance, manutenção e acompanhamento em bloco, ao clicar nesses blocos de KPI já filtra as usinas em atenção
daquele bloco". O protótipo foi aprovado ("Pode construir a Visão geral no Nexus, depois que o ranking subir (é a mesma
tela)"), com um pedido a mais: "centralize o cabeçalho e todas as colunas exceto Usina".

## O que é

- **A 4ª aba** da Visão do responsável: Por responsável · Onde focar · Ranking das equipes · **Visão geral**.
- **Em cima, os três blocos** (Performance, Acompanhamento, Manutenção), lado a lado, com os MESMOS números do resumo
  de hoje (`soma`) e a triagem de cada bloco (focar, acompanhar, em dia).
- **Embaixo, uma lista só** com todas as usinas do filtro da tela (responsável, cliente, busca, equipe): uma linha por
  usina, com as colunas principais dos três blocos; ao abrir, o detalhe dos três.
- **Clicar filtra a lista:** o nome do bloco ("N pedem atenção") mostra as usinas em focar ou acompanhar naquele bloco;
  "focar" ou "acompanhar" do bloco, só aquele nível; um número, as usinas que entram nele. Clicar de novo, ou no ×,
  tira o filtro.

## Decisões do Levi

- O protótipo como está: os três blocos em cima, a lista única embaixo e o filtro pelo clique.
- **Cabeçalho e colunas centralizados, menos Usina**, na lista da Visão geral e também nas tabelas dos três blocos de
  Onde focar (é a mesma tela; ficam iguais).
- Construir depois que o Ranking das equipes subir (mexe na mesma tela).

## Decisões do construtor

- **Nenhuma régua nova:** os números são os do resumo de hoje (`soma`) e as células, os `valores` de cada bloco, com a
  mesma cor. O filtro de cada número usa a mesma condição que conta aquele número.
- **O filtro vai no endereço** (`?modo=geral&filtro=manut.atrasadas`), como os outros filtros da tela: funciona sem
  JavaScript, volta com o botão do navegador e dá para mandar o link. Filtro que não existe é ignorado.
- **Os números que filtram:** Meta do mês e Abaixo da meta (usinas abaixo de 97%), PR abaixo, Disponibilidade (usinas
  abaixo da régua da disponibilidade), Rondas pendentes, PT esperando, Chamados, Extintores, Tarefas atrasadas, Tarefas
  paradas e Semana passada (usinas abaixo de 85%). OS abertas não filtra: quase toda usina tem OS aberta. Número zero não
  é link.
- **O número conta o que conta hoje** (tarefas, PT, chamados); o filtro diz quantas usinas: "Tarefas atrasadas · 5
  usinas".
- **As colunas da lista:** Meta e Disp. (Performance); Ronda, Limpeza e PT (Acompanhamento); Atrasadas, Paradas e
  Semana (Manutenção). O resto fica no detalhe. As colunas do bloco filtrado ficam realçadas.
- **A ordem da lista** é a de Onde focar (`ordem_do_foco`, o peso dos três blocos).
- **O limite das atrasadas** (o campo do bloco Manutenção, guardado no navegador) vale também aqui, e o campo aparece no
  bloco Manutenção da Visão geral.
- **No celular** (até 760 px), a lista vira cartões: a usina, três etiquetas (P, A e M) na cor do nível de cada bloco com
  o alerta principal, e o detalhe ao tocar.

## Fora

- Nenhum dado novo, nenhum livro novo no banco, nenhuma régua nova.
