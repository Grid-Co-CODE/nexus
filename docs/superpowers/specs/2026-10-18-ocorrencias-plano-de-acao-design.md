# As ocorrências com plano de ação (desenho)

Levi, 18/10/2026: "Próximas peças: o mapa das usinas e as ocorrências com plano de ação. siga!". A origem é o painel
próprio de um supervisor (o Painel de Ocorrências: a ocorrência, o histórico, as anotações e o plano de ação, em Quadro e
Lista, com filtros). O objetivo é o de toda a Visão do responsável: o responsável largar o painel próprio e usar só o Nexus.

## Decisões do Levi (quiz de 18/10/2026)

- **Lugar:** uma tela própria, "Ocorrências", no Campo · App (lista e quadro, criar e editar); na Visão geral, quantas
  ocorrências abertas cada usina tem, com link para a tela.
- **Quem cria e edita:** o Responsável O&M (pelo login do Fracttal) e os administradores; os outros só veem.
- **Campos (os essenciais):** título, usina, equipamento, criticidade (baixa, média, alta, muito alta), status (em
  andamento, pausado, finalizado), início e fim, descrição, OS do Fracttal e chamado.
- **Plano de ação:** cada ação com responsável, prazo e situação (a fazer, em andamento, concluída), e um histórico de
  andamento com data.

## Decisões do construtor

- **O Nexus é a fonte, no banco:** o livro `nexus_ocorrencias`, registrado no catálogo antes da 1ª gravação (regra 10),
  com a trava de livro que só cresce. Nada de planilha nem arquivo da máquina: o PC e o servidor leem o mesmo livro.
- **Só acrescenta, vale a última** (como os motivos do PCM e o acompanhamento da Engenharia): cada salvamento é uma
  decisão; o estado de uma ocorrência e de uma ação é a última decisão delas; o andamento é uma linha por registro.
  Nada se apaga nem se reescreve.
- **Texto livre só cifrado** (o Cofre, a chave do cadastro, como a observação do responsável): o título, a descrição, o
  chamado, o texto da ação, o andamento e o nome de quem escreveu. Em claro, só IDs, códigos e datas: `ocorrencia_id`,
  `usina_id`, `equipamento_id` e o código do ativo, `pessoa_id` (e o `pessoa_hmac`), a criticidade, o status, a
  situação, os dias (`data_id`) e o número das OS do Fracttal.
- **O responsável da ação** é escolhido numa lista das pessoas do cadastro (fica o `pessoa_id`), não digitado.
- **O equipamento** é o código do ativo (opcional), ligado ao `equipamento_id` da dimensão quando bate.
- **A lista** fica na ordem do prazo da próxima ação em aberto (sem prazo no fim), como no painel do supervisor; **o
  quadro** tem uma coluna por status. Filtros: usina, responsável O&M, status, criticidade.
- **Na Visão geral:** uma etiqueta no nome da usina ("2 ocorrências"), na cor da criticidade mais alta das abertas
  (aberta = status diferente de finalizado), com link para a tela filtrada pela usina.
- **Fora, por agora:** as anotações privadas, exportar para .xlsx, o comunicado por IA e a importação do painel antigo.
