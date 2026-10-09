# CLAUDE.md — Segurança · HSEQ

Torre do menu "Segurança · HSEQ". Tela viva: **Extintores** (09/10/2026). Riscos da semana, APR e PT, DSS e Incidentes
ainda são placeholder (a view com a mesma rota vence a genérica). As contas moram em `nexus/hseq/`; a view e o template,
aqui.

## Extintores

Levi, 09/10/2026: "Gostaria de adicionar no Nexus algo que inseri no app: Extintores. Ficará no módulo de segurança.
Nele será possível ver a tabela dos extintores com uma visão do que está atrasado, perto de atrasar e sem atualização a
mais de 30 dias. Preciso da visão por supervisor."

**De onde vem.** A ronda de extintores do App de Campo (v247, 08/10/2026) substituiu o Microsoft Forms da TST. O
cadastro inicial é a planilha de controle da TST (773 extintores em 81 usinas; 7 usinas sem par no Fracttal ficaram
fora, 58 extintores) e fica **fora do Fracttal** (código próprio `<cb>-INFC1-PPCI-EXTnn`). O App publica no banco o
livro `extintores_app_campo`, de hora em hora com os outros livros dele (timer `nexus_workbooks_sync`, aos :25). Nada
de Azure. **Até o App publicar, a tela diz que os extintores ainda não chegaram** (o livro não existia em 09/10).

**O contrato** (`nexus/hseq/extintores.py`, `COLUNAS`; coluna nova só no FIM). Aba `Extintores`, 1 linha = 1 extintor
com a última conferência: `Código`, `Usina` (nome do Fracttal), `Código da usina`, `Tipo de ativo`, `Ativo` (código do
Fracttal de onde ele fica), `Local`, `Posição`, `Classe`, `Peso (kg)`, `Validade da recarga` e `Validade do
hidrostático` (`MM/AAAA`, só o ano, `Sem data`, `Sem selo`), `Última conferência` (`AAAA-MM-DD`, dia de Brasília),
`Origem da conferência` (`App` ou `Forms da TST`), `Conferido por (HMAC)`, `Carga`, `Itens NÃO` (as chaves do App
separadas por `; `), `Fotos`, `Tem informação adicional` (sim/não: a observação do técnico **não** vai, a API tem
leitura aberta), `Status` e `Motivo` (os do App na hora da publicação) e `Origem do cadastro`. O histórico (1 linha =
1 extintor × mês) vai num livro próprio, `extintores_conferencias_app_campo` · `Conferências` (o App sobe uma aba por
livro: o sync-xlsx com replace troca o livro inteiro): registrado no catálogo, a tela ainda não usa. Os dois fatos
(`extintor`, `conferencia_extintor`) estão em `nexus/dados/catalogo.py`, estado origem. Sem uma das colunas da conta (`ESSENCIAIS`)
a tela diz qual falta e não mostra número.

**As contas** (nossas, no dia de Brasília; o status que o App manda não entra):
- **Atrasado**: a recarga (2º nível) ou o teste hidrostático (3º nível) venceu. A etiqueta vale até o último dia do mês;
  só o ano, até 31/12.
- **Perto de vencer**: não está atrasado e uma das duas vence em até 30 dias.
- **Sem validade**: a recarga sem data e nada vencido nem a vencer em 30 dias (nunca vira "em dia").
- **Em dia**: o resto. As quatro são exclusivas e somam o total.
- **Sem atualização**: última conferência há mais de 30 dias, ou nunca. Soma-se às outras: a faixa não fecha o total.
- **Status da TST** (crítico, atenção, ok, ok sem validade): a regra da aba Legenda da planilha da TST, a MESMA do App
  (`_ext_status`), com a carga e os 9 itens. Sem conferência nenhuma, não há status.

**A tela.** Faixa de números (cada um filtra a tabela), "Por supervisor" (cartões por região de campo, com o Supervisor
de Campo e o Coordenador ou a vaga, e a alternância para o gestor de contrato, como a Central de atenção) e Tabela (o
mais grave primeiro; no filtro "sem atualização", a conferência mais antiga primeiro; 300 linhas). Filtros: região do
Brasil, região de campo, gestor e busca. Quem entra pelo Fracttal já vem filtrado (o papel da sessão). Os filtros, os
cartões e o aviso da estrutura são os do Campo (`nexus/torres/campo/__init__.py` e os pedaços `campo/_*.html`): mudou
lá, muda aqui. O CSS é o `campo.css` e o `hseq.css` (só a tabela).

**Na tabela, as partes de cada célula ficam lado a lado** (Levi, 09/10/2026, sobre a 1ª versão, que punha o detalhe
sempre na linha de baixo: "se tem espaço para botar paralelo então deixe paralelo"). A parte é inteira e só desce de
linha quando a coluna não comporta. Medido em 09/10 com os 773: a 1920 px, 0 de 2.100 células quebram (41 px por
linha); a 1440 px, a tabela cabe na largura e as partes descem onde falta espaço. Para caber a 1920: o código do ativo
fica no title do Local, a validade distante não ganha frase, o status da TST não repete a validade (só a carga e os
itens com NÃO; o motivo inteiro no title, com teto de 240 px), a região sem nada vira "sem região" e a origem do Forms,
"Forms". As partes são `inline-block`, não flex: com `flex-wrap` o Chrome mede a coluna como se cada parte fosse uma
linha e quebrava 718 células a 1920 px.

**Números de 09/10/2026** (cópia de conferência com o cadastro da TST no lugar do livro): 773 extintores em 81 usinas,
**260 atrasados** (37 usinas), 29 perto de vencer, 121 sem validade, 363 em dia, **698 sem atualização** (a última
conferência do Forms é de março a agosto). 149 extintores (22 usinas) caem em "Sem região de campo": usinas de equipes
que não estão em nenhuma região da estrutura de O&M (o conserto é no cadastro, como na Central). Todas as 81 usinas
ligaram ao cadastro do Nexus; todas as regiões estavam com supervisor e coordenador em vaga.

**Como provar.**
- `python -m pytest -q tests/test_hseq_extintores.py`: as regras num dia fixo (inclusive a virada do mês e os limites
  de 30 dias) e a tela com o banco falso do Campo (livro ausente, faixa, cartões, tabela e ordem, filtros, login de
  supervisor, coluna faltando).
- Regra igual à do App (fora do repositório: o cadastro tem nome de usina e o repositório é público): extrair
  `_ext_status` e `_ext_validade_fim` do `function_app.py` pelo AST e rodar as duas no `extintores_cadastro.json`. Em
  09/10: 424.377 comparações (773 × 549 dias, 01/08/2026 a 31/01/2028), 0 diferença; o status gravado no cadastro,
  773 de 773.

**Pendências.** O App publicar o livro (pedido à sessão do App de Campo em 09/10, com este contrato). A cobrança mensal
por usina (ronda de extintor feita ou não no mês) e o painel da TST (baixa e confirmação dos extintores novos) são do
App; entram aqui quando houver o livro e o pedido.
