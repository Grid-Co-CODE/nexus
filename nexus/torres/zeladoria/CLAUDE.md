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

  Até a troca, gravar e as `fin_*` voltam `SOMENTE_LEITURA`. A sessão vencida volta `SESSAO` e recarrega o Nexus,
  nunca um Radar vazio.
- **O dado** vem de três livros (`nexus_zeladoria_app`, `_fracttal` e `_historico`), lidos e decifrados por
  `nexus/zeladoria/leitura.py`, com cache de 5 min.
  - Livro, aba ou contagem faltando: a tela diz que a cópia não foi feita (`CopiaAusente`).
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

## Como provar

- `python -m pytest tests/test_zeladoria_*.py -q`, com o `.env`, para o `test_sem_nomes_no_repositorio.py` rodar junto.
  `tests/zeladoria_ponte_node.js` prova a ponte no node.
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

- **4:** a gravação com a versão do livro e as `fin_*` em Python.
- **5:** o Fracttal (rondas) e a rota do cronograma.
- **6:** as usinas ligadas ao cadastro, e a troca.
