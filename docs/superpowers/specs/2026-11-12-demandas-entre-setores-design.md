# Demandas entre setores — desenho (12/11/2026)

Aprovado pelo Levi em 11-12/11/2026 ("desenho aprovado"), a partir da prévia navegável
`Projeto API PV/docs/mockups/demandas-entre-setores/index.html` (v2). Este documento é o que um construtor precisa para
planejar sem voltar ao Levi.

## Para que serve (o porquê)

Hoje um setor cobra o outro pelo WhatsApp, pelo Teams e de boca, sem prazo nem registro. Os casos que servem de régua:

- **Dúvida que pede análise:** o supervisor pergunta à Performance por que um dado não bate, ou por que uma usina não
  está no registro mestre.
- **Aviso para acompanhar:** a Engenharia terminou uma OS e o supervisor precisa acompanhá-la; hoje nada chega a ele (a
  OS vai para o técnico e para a Engenharia).
- **Cobrança:** o gestor cobra o supervisor porque há extintores vencidos.

A **demanda** é o jeito de um setor pedir algo a outro dentro do Nexus, **sem abrir uma OS**, com prazo, registro, vai
e volta e aviso.

## Objetivos

1. Qualquer pessoa do Nexus abre uma demanda para **uma pessoa** de **um setor** (os dois obrigatórios), sobre um
   **tema** da lista daquele setor.
2. Cada setor mantém a **sua lista de temas**, cada tema com o **prazo de resposta em dias úteis**.
3. Quem pede vê, ao abrir, "Resposta até <dia>".
4. A demanda pode levar **uma ou mais usinas**, **uma OS** (só uma OS existente daquelas usinas) e **anexos**.
5. Quem recebe trabalha a demanda (situações abaixo); quem pediu conclui ou devolve com justificativa.
6. Tudo aparece na **Caixa de entrada do Comando** e num **sininho próprio** no topo.

## Não-objetivos (agora)

- Mais de um setor por demanda (Levi: "Esquece essa parte de indicar mais de um setor").
- Avisos automáticos de outros sistemas no sininho (a OS terminada pela Engenharia, por exemplo): o sininho nasce para as
  demandas e cresce depois.
- E-mail, Teams ou celular: o aviso é dentro do Nexus.
- Juntar com o "Pedir a uma área" dos Insights (`nexus/comando/pedidos.py`): continua como está.

## Antiobjetivos (o que faria isto falhar mesmo funcionando)

- Linha da Caixa cheia de informação: a linha mostra **quem pediu, o setor dele, o título e as primeiras palavras**; o
  resto fica no detalhe (Levi: "não seja tanta informação de primeira").
- Repetir o tema no título e nas linhas (Levi apontou na v1).
- OS vinculada que não existe ou não é da usina citada.
- Texto livre, nome ou e-mail em claro no banco (o banco tem leitura aberta).

## Regras decididas pelo Levi

| Regra | Decisão |
|---|---|
| Destinatário | pessoa do Nexus **e** setor, obrigatórios; se não sabe a pessoa, descobre antes |
| Quem vê | quem pediu, quem recebeu e **todo o setor** de quem recebeu ("Do meu setor", com filtro por pessoa e por tema) |
| Temas | cada setor edita os seus; cada tema tem o prazo em dias úteis; dá para desativar sem apagar |
| Prazo | do tema; dias úteis (sem sábado, domingo e feriado nacional, `nexus/dados/calendario.nacionais_calculados`) |
| Situações | **Nova** → **Em análise** → (**Aguardando quem pediu**) → **Finalizada** (respondida) → **Concluída** (ok de quem pediu); **Devolvida** (por quem pediu, com justificativa obrigatória) volta a quem recebeu com **novo prazo** do tema |
| Pedir informação | quem recebe pergunta algo a quem pediu: a demanda fica "Aguardando quem pediu" e **o prazo para** até quem pediu responder (os dias parados somam ao prazo) |
| Conclusão sozinha | Finalizada sem o ok nem a devolução em **3 dias úteis** vira Concluída sozinha; a linha do tempo diz isso |
| Vencida | avisa **quem recebeu + todo o setor dele** no sininho (até o cadastro ter o gestor de cada setor; aí, só ele) |
| Avisos no sininho | demanda nova para mim; faltam 2 dias e falta 1 dia; vence hoje; vencida (para o setor também); devolvida; respondida (para quem pediu); pediu informação (para quem pediu) |
| OS | só uma OS **existente** de uma das usinas escolhidas (a lista vem do retrato das OS do Fracttal no banco, `nexus_os · fato_tarefa_os`); no detalhe, o número abre o **card da OS** do OS Creator, por cima da tela |
| Anexos | a regra das Sugestões (`nexus/casca/sugestoes.py`): até 5 arquivos, 5 MB cada, 15 MB juntos; imagem, PDF, Word, .md, .txt; conteúdo conferido pelo começo do arquivo; no disco do servidor (pasta de dados do Nexus), nome neutro; o nome original só cifrado |
| Nome | "Demandas" (o Nexus já tem a torre Chamados e as Ocorrências) |

## Telas

- **Comando › Caixa de entrada**: o bloco das demandas no alto, com três abas — **Para mim**, **Que eu pedi**, **Do meu
  setor** — e a faixa de filtros (Abertas, Vencem até amanhã, Vencidas, Finalizadas, Concluídas; em "Do meu setor",
  também por pessoa e por tema). Cada linha: o prazo em selo (Vence hoje / Faltam 2 dias / Vencida há 1 dia), **quem
  pediu**, **o setor dele**, **o título** e **as primeiras ~6 palavras** da descrição; à direita a situação e o tema. O
  clique abre o detalhe ao lado: a situação, o tema (uma vez, acima do título), o título, de/para, prazo, usinas, OS
  (clicável, abre o card), o texto, os anexos, a linha do tempo e os botões do papel de quem olha. Os blocos de hoje da
  Caixa (pedidos dos Insights, menções, com você, sem dono) continuam abaixo, como estão.
- **Nova demanda** (botão no alto da Caixa, abre uma janela): para quem (a pessoa, com busca), setor (o da pessoa, já
  preenchido), tema (os do setor, com o prazo; mostra "Resposta até <dia>"), título, descrição, usinas (uma ou mais),
  OS (só as da usina escolhida), anexos.
- **Comando › Temas do setor**: a lista do setor da pessoa (tema, prazo em dias úteis, em uso); novo tema, editar o
  prazo, desativar. Quem é do setor edita os do próprio setor; o administrador edita todos (escolhe o setor).
- **Sininho "Demandas"** no topo, à esquerda do botão de avisos do OS Creator, com o número e a lista curta; cada item
  leva à demanda na Caixa.

Visual: o da prévia v2 (à la Nexus, navy, um nível de superfície, sem emoji, status pela cor).

## Dados (regras de `nexus/dados/CLAUDE.md`)

Livro novo **`nexus_demandas`**, registrado em `catalogo.LIVROS` antes da 1ª gravação, `so_cresce=True` (só acrescenta;
a situação de agora é o último evento). Pessoa só por código (`pessoa_hmac`, o HMAC do e-mail com `NEXUS_PESSOA_HMAC`, e
`pessoa_id` quando o cadastro liga); texto livre e nomes só cifrados (o Cofre, `NEXUS_CHAVE_CADASTRO`, como as
Sugestões).

| Aba | 1 linha = | Em claro | Cifrado (`dados_cifrados`) |
|---|---|---|---|
| `dim_tema` | 1 versão de 1 tema de 1 setor (vale a última por `tema_id`) | `tema_id`, `setor_id`, `prazo_dias_uteis`, `ativo`, `registrado_em`, `data_id`, quem mudou por código | o nome do tema (texto livre do setor) e o nome de quem mudou |
| `fato_demanda` | 1 demanda aberta | `demanda_id`, `registrado_em`, `data_id_criacao`, `de_hmac`, `de_pessoa_id`, `de_setor_id`, `para_hmac`, `para_pessoa_id`, `para_setor_id`, `tema_id`, `prazo_dias_uteis` (o do tema na hora), `os` (o número, dimensão degenerada) | o título, a descrição, os nomes de quem pediu e de quem recebe, os anexos (nome original, arquivo neutro, tamanho) |
| `fato_demanda_usina` | 1 usina de 1 demanda | `demanda_id`, `usina_id` | — |
| `fato_evento_demanda` | 1 passo de 1 demanda | `id`, `demanda_id`, `evento` (`em_analise`, `pediu_informacao`, `informou`, `respondeu`, `devolveu`, `concluiu`, `concluiu_sozinha`), `registrado_em`, `data_id`, quem fez por código | o texto (resposta, pergunta, justificativa) e o nome de quem fez |

- O prazo de agora é **calculado**, não gravado: a data de abertura (ou da última devolução) + os dias úteis do tema +
  os dias úteis parados em "Aguardando quem pediu".
- A conclusão sozinha é calculada na leitura (Finalizada há 3 dias úteis sem ok nem devolução) e gravada como evento
  `concluiu_sozinha` na próxima gravação de qualquer demanda (ou mostrada como concluída sem gravar; o construtor
  escolhe, desde que a tela e o banco não discordem por mais de uma leitura).
- O "lido" do sininho: o construtor decide (por pessoa no navegador ou um evento `leu`); o número do sininho é "o que
  pede a minha ação": as demandas para mim abertas + as que eu pedi e estão Finalizadas ou Aguardando a minha resposta.
- `fato_demanda` não muda depois de gravado (a situação vem dos eventos); a devolução não reescreve a demanda.
- As abas vão juntas a cada gravação (livro que só cresce recusa gravar sem uma aba que o banco tem), relidas do banco
  antes (`livros.publicar`), com a trava de 1 gravação por vez (`threading.Lock`), como as Sugestões.
- Catálogo (`Fato` de cada aba, `Livro`), `explica.RESUMO`/`PARA_QUE` de cada fato e a linha em `nexus/dados/CLAUDE.md`
  no mesmo commit.

## Quem é quem

- **A pessoa do Nexus e o setor dela**: as decisões de setor (`nexus/cadastro/setores.py`, `setor_telas.setor_de_cada_
  codigo`) dão o setor de cada `pessoa_hmac`; o nome e o e-mail vêm do pessoal do Fracttal (`cadastro.fracttal_pessoal.
  ler_pessoal`). A lista de destinatários = as pessoas com setor ativo; ao escolher a pessoa, o setor vem preenchido.
- **Eu** = o `pessoa_hmac` do e-mail do login (`codigo_da_pessoa`). A senha de administrador (sem pessoa) vê tudo e não
  abre demanda.

## O que fica com o construtor

- A divisão em módulos (sugestão: `nexus/comando/demandas.py` com a conta pura, rotas na torre Comando, templates em
  `nexus/torres/comando/templates/comando/`, CSS no `comando.css`, JS próprio sem handler inline).
- O formato exato das rotas (POST com o código da sessão contra outro site, como as Sugestões).
- A ordem das linhas (sugestão: a mais perto de vencer primeiro).
- Testes: um `tests/test_comando_demandas.py` com a conta (prazo com feriado e pausa, situações, conclusão sozinha,
  avisos), as telas (logado como quem pede, quem recebe e alguém do setor), a OS fora da usina recusada, o anexo fora do
  limite recusado, nada em claro no banco; banco falso do `test_campo_visao`.

## Como provar

- `python -m pytest -q` sem falha nova.
- A prévia local com o banco falso: abrir, receber, pedir informação (o prazo para), responder, devolver (novo prazo),
  concluir; o sininho e as três abas; o card da OS abre.
- No banco de produção, só leitura: a lista de pessoas e setores e as OS por usina saem certas.
