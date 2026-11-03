# CLAUDE.md — torre Zeladoria (o Radar de Fornecedores dentro do Nexus)

Levi, 03/11/2026: trazer a plataforma de zeladoria inteira para o Nexus, "com a mesma lógica e caminhos do BD, só que
ao invés de Supabase virá tudo para o Nexus". Desenho: `docs/superpowers/specs/2026-11-03-zeladoria-no-nexus-design.md`.
Plano e registro: `docs/superpowers/plans/2026-11-03-zeladoria-etapas-1-e-2.md`.

## Como funciona

- **O app é um clone:** `clone/radar.html`, a versão `f0b4cac` do Radar, limpa de nomes e do Supabase (`clone/ORIGEM.md`).
  O Radar congela ao fim da etapa 2. Daí em diante este arquivo é a casa da zeladoria e se edita direto.
- **Telas:** cada uma das 18 abas do Radar é uma tela no menu do Nexus (`ABAS`: id da tela → id da aba do clone).
  - A tela é a moldura da porta única (`.porta`) com o clone num iframe (`/t/zeladoria/app?aba=...`).
  - A barra lateral do clone some; o menu é o do Nexus.
  - Quem vê a torre é o setor (Base → Acessos). Dentro dela, o papel e as permissões por aba do Radar decidem, como lá.
- **A ponte** (`nexus/static/zeladoria/ponte.js`) é o `window.supabase` do clone e fala com as rotas da torre:
  - `GET /api/rf/<view>` aceita `eq`/`neq`/`order`;
  - `GET /api/eu` devolve `{"user": {"id", "email"}}`;
  - `POST /api/funcao/fracttal-fotos` traz as fotos;
  - `GET /foto/<folio>/<i>`.

  Até a troca, gravar e as `fin_*` voltam `SOMENTE_LEITURA`. Com a gravação ligada, `POST /api/gravar`,
  `POST /api/funcao/fin_*` e `GET /api/situacao` (seção "A gravação"). A sessão vencida volta `SESSAO` e recarrega o
  Nexus, nunca um Radar vazio.
- **O dado** vem de três livros (`nexus_zeladoria_app`, `_fracttal` e `_historico`), lidos e decifrados por
  `nexus/zeladoria/leitura.py`, com cache de 5 min.
  - Livro, aba ou contagem faltando: a tela diz que a cópia não foi feita (`CopiaAusente`).
  - Banco que não responde: a tela diz isso e pede para recarregar (`BancoFora`). Caso: em 03/11/2026 a API da T.I. deu
    502 em dois de cada três pedidos, e a tela caía em erro 500.
  - Quem não está aprovado no `perfis` do Radar só vê a própria linha. A pessoa é casada pelo e-mail do login do
    Nexus, e o administrador sem linha vale HEAD.
- **As fotos da ronda** vêm do Fracttal, no clique, pelo `nexus/campo/ronda_fotos.py`: o link assinado fica no
  servidor, e nada vai para o bucket do Supabase.

## A cópia (até a troca)

1. **Exportar no SQL Editor do Supabase:** a consulta sai de
   `python ferramentas/copiar_zeladoria.py --sql --nomes <de_para_nomes.json>`. Ela é montada na hora porque cita as
   tabelas pelo nome do supervisor, e por isso não fica no repositório. É um SELECT só, que devolve uma célula com o JSON
   dos dados, dos tipos e das chaves; essa célula se salva como arquivo, fora do repositório. Não há papel nem senha no
   banco do Radar.
2. **Ensaiar:** `python ferramentas/copiar_zeladoria.py --arquivo <exportação.json> --nomes <de_para_nomes.json>`. Imprime
   só contagens.
3. **Gravar:** o mesmo comando com `--gravar`, sempre na mesma máquina.

O `de_para_nomes.json` (nomes de colegas → papel) fica fora do repositório, que é público. É o mesmo da limpeza do clone.
Os valores renomeados nos dados são as chaves `previsto_decidido_*` do config, as ações `*equipe` do log e a origem
`planilha_historica`.

O que vai cifrado: todo texto, menos a lista `_CLARO` de `nexus/zeladoria/tabelas.py` (ids, datas, status, usina,
cliente, lugar). Por quê: a API do banco tem leitura aberta, e fornecedor MEI tem nome de pessoa.

## A gravação (etapa 4, 03/11/2026; desligada até a troca)

Liga só onde `NEXUS_ZELADORIA_GRAVA=1`: o servidor, no dia da troca. Uma máquina grava; dois Nexus com estados
diferentes apagariam um ao outro. Levi escolheu "Salvo em 1 s, banco logo depois": gravar e conferir o livro do app leva
~8 s (medido), e esperar isso a cada clique travaria a tela.
- **Na hora** (`nexus/zeladoria/gravacao.py`, `Gravador.aplicar`): a mudança entra no estado em memória e no diário
  `<NEXUS_DADOS>/zeladoria/diario.jsonl`, cifrado linha a linha, e o "Salvo" do app acende. Diário que não gravou = 503,
  e a mudança não entrou (o pedaço escrito sai). Ao reler, a última linha pela metade é ignorada (o acréscimo que não
  terminou, sem "Salvo"); linha ruim no meio não se adivinha, e a torre não sobe.
- **Em lote** (`persistir`, pelo laço em thread: 2 s sem mudança ou 20 s seguidos): grava no banco os livros que
  mudaram, pelo `livros.publicar`, e só então esvazia o diário até aquela versão. Banco fora: o diário segura, a
  situação mostra o erro, e o laço tenta de novo, esperando mais a cada falha (até 60 s).
- **Ao subir** (`carregar`): o diário se reaplica por cima do banco, livro a livro pela versão de cada um (a coluna
  `versao` da aba `atualizacao`). Assim, o banco que gravou o livro do app e caiu antes do histórico não perde o
  histórico.
- **Só a diferença** (`ponte.js`): o Radar salva o estado inteiro a cada mudança (o `syncTudo` faz upsert de todas as
  tabelas). A ponte guarda uma cópia PROFUNDA do que leu e manda só as colunas que mudaram, das linhas que mudaram. A
  cópia é profunda porque o Radar muda o JSON no lugar (as pendências do dano, o escopo do contrato, as etapas da rota):
  com a cópia rasa, a pendência marcada não ia ao servidor e o "Salvo" acendia (a revisão de 03/11/2026 achou; provado
  na página real depois da correção). O histórico de valores,
  que o Radar apaga e regrava, vira a diferença das linhas. Na 1ª gravação, a rota da equipe vai uma vez (o Radar
  normaliza as etapas); a prova mostrou que da 2ª em diante só vai o que mudou.
- **Conflito simples:** a mudança de outra pessoa numa linha que você não mexeu fica. Na linha que os dois mexeram, vale
  a última, e o aviso aparece no `showToast` do Radar ("Você e outra pessoa mudaram o mesmo registro"). A versão base é
  a da página aberta (de `/api/eu`).
- **Quem grava:** só quem está aprovado no `perfis`, como no RLS do Supabase. O `perfis` e as `fin_*`, só o HEAD; o
  administrador do Nexus sem linha vale HEAD. A pessoa nova que abre a torre ganha a linha "pendente" (`garantir_perfil`).
  POST de outro site, 403 (a régua `_de_outro_site` da moldura).
- **Como o Postgres do Radar:** coluna que a tabela não tem e valor fora do tipo (texto em número, "8.5" em bigint) são
  recusados. Sem isso, a coluna sumia calada no lote, e o texto em número derrubava a leitura no boot seguinte.
- **Exclusão:** a definitiva deixa uma linha no `log` (`acao` "excluir-definitivo", `alvo` "<tabela>:<id>", quem, e em
  `obs` o que foi junto). O `ON DELETE` do banco do Radar vale aqui (`CASCATA` em `gravacao.py`): o fornecedor leva as
  cotações, os documentos e os apelidos, e solta (nulo) o fornecedor dos itens e das provisões do financeiro; o
  colaborador leva os documentos; a rodada solta as cotações; o cenário leva os itens. O clone conta com isso: ao
  excluir o fornecedor, ele tira as cotações só do estado dele.
- **O histórico só recebe linha nova:** `log`, `financeiro_historico` e `cronograma_alteracoes` aceitam só linha nova (do
  cronograma, também o `motivo`, que o app preenche depois); o `fin_provisao_historico`, só pelas funções do
  financeiro (no Supabase o insert era revogado). Excluir no histórico é recusado: a trava do catálogo recusaria o lote
  no banco para sempre.
- **Padrões que o banco do Radar dava:** id `bigint` novo = o maior + 1, contando as linhas do mesmo salvamento e sem
  reaproveitar o número que saiu (a resposta devolve os ids, e a ponte os guarda); `criado_em`, o `em` do log e
  `excluido` falso.
- **Leitura e lote sem trava longa:** a mudança troca a lista da tabela em vez de mudá-la (quem lê a antiga não a vê
  mudar), o lote cifra fora da trava, e a carga que falhou (banco fora) volta a mesma recusa por 30 s, em vez de reler
  os três livros a cada pedido.
- **Ficou de fora (baixo):** a linha excluída por uma pessoa e editada por outra, com a página velha, volta só com as
  colunas editadas (no Supabase voltava inteira).
- **As funções do financeiro** (`nexus/zeladoria/financeiro.py`): `fin_promover`, `fin_definir_fornecedor` e
  `fin_editar_provisao`, portadas do SQL do Radar (`docs/financeiro/*.sql`), com a mesma regra e a mesma mensagem. Cada
  uma vira um salvamento só (`Gravador.chamar`): tudo ou nada.
- **A cópia não passa por cima:** depois que a torre gravou (versão do banco acima de 0), `copiar_zeladoria.py --gravar`
  recusa. O `--forcar` só com o servidor parado e o diário vazio; senão o diário se reaplica por cima da cópia.

## Como provar

- `python -m pytest tests/test_zeladoria_*.py -q`, com o `.env`, para o `test_sem_nomes_no_repositorio.py` rodar junto.
  `tests/zeladoria_ponte_node.js` prova a ponte no node, nos dois modos.
- A gravação na cópia de prova: suba com `NEXUS_ZELADORIA_GRAVA=1` e `NEXUS_DADOS` numa pasta de rascunho. A cópia de
  prova recusa toda gravação fora da máquina, então o banco de verdade não é tocado, e a prova mostra também o banco
  fora do ar: o "Salvo" acende, a situação diz o erro, e o diário segura e se reaplica ao reiniciar. 1ª prova
  (03/11/2026): editar um fornecedor mandou só `id,obs` (124 bytes); reiniciar manteve a versão 3; editar provisão com o
  dado real gravou as duas linhas do histórico, e a terceira chamada, igual, voltou "nada mudou".
- A tela na cópia de prova (`ferramentas/subir_copia_de_prova.py`), em desktop e em 375 px.
- Os totais da Visão Geral, do Financeiro e do Farol Contratual iguais aos do Radar no ar, com a mesma exportação.

## A 1ª medida (03/11/2026)

- **Cópia:** a exportação das 17:07 UTC, 4.756 linhas nas 39 tabelas mais 117 últimas rondas, gravada em 13,8 s; as 40 abas têm no Nexus as mesmas linhas da origem. A maior célula é a do retrato do cronograma (86 mil caracteres), que vai partida em 3. 86 valores com nome foram renomeados (config 2, log 7, origem dos serviços 77).
- **Tela:** na cópia de prova (porta 5172), a Visão Geral, o Financeiro e a Criticidade abriram com o dado real, sem erro no console. Em 375 px, o menu do Nexus vira o botão Menu, e o clone se ajusta.

## O visual (etapa 3, 03/11/2026)

- **Paleta:** as três cores do Levi (preto `#030407`, azul `#1558c9` e lima `#d4ff24`) ficam numa paleta própria, dentro do clone: o bloco `zeladoria-paleta`, que redefine as variáveis do Radar nos dois temas. No claro, o lima é só superfície, com texto preto em cima; o texto de destaque é um lima escuro, e a informação é o azul.
- **Tema:** o `<html>` do clone nasce com o `data-theme` do tema do Nexus, e o botão do topo troca ao vivo (o aviso `nexus.tema` no navegador).
- **Fontes:** as do Nexus (Poppins, Raleway nos títulos e IBM Plex Mono).
- **Cores fixas:** a do CSS e a de aviso dos estilos do JavaScript viraram variável. A cor de DADO (o avatar de cada pessoa, a escala de dias de atraso, o calor da criticidade) e o CSS do relatório de impressão (papel branco) ficam como estavam.
- **Emojis:** saíram. O que era o botão inteiro virou palavra (Excluir, Editar, Fotos, Simular...).
- **Celular:** a 375 px nenhuma das 18 telas rola de lado. A tabela larga rola dentro dela, a grade fixa cai para uma coluna e a linha de botões quebra.
- **Como se faz:** tudo pela `ferramentas/zeladoria_limpar_clone.py` (a função `vestir`), que roda de novo sobre o Radar original. Prova: `tests/test_zeladoria_clone.py`.

## O que falta (etapas do desenho)

- **5:** o Fracttal (rondas) e a rota do cronograma.
- **6:** as usinas ligadas ao cadastro, e a troca.
