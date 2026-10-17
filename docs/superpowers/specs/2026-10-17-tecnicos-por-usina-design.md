# Técnicos por usina no Nexus (PCM) — desenho

Data: 17/10/2026. Dono: Levi. Torre: PCM. Status: aprovado pelo Levi em 17/10/2026 ("desenvolva").

## 1. Para que serve e por quê

Levi, 17/10/2026: "vamos criar uma estrutura em PCM [...] que liga usina e técnico e o PCM pode editar à vontade";
"é normal usinas terem dois técnicos e receberem de vez em quando mais técnicos"; "dá para trazer para o Nexus esse
controle? quero tirar do site de gestão"; "vamos deixar redondo, depois tiramos 100% do site de gestão".

Hoje a ligação usina × técnico existe em dois lugares que não se falam, e nenhum dos dois bate com o campo:

- **Nexus:** `cadastro_nexus · usinas.tecnico_om_id`, UM técnico por usina, automático (1º técnico ativo da equipe) ou
  digitado na ficha da usina (só admin, vai a um JSON local e ao banco só no "Publicar no banco"). 102 de 180 usinas em
  operação têm técnico.
- **App de Campo:** tabela `atribuicoes` do Azure (modelo de escopo "novo", ligado em produção, conferido no `/health`
  em 17/10), N pessoas por usina com papel `executa` ou `responsavel`, editada na tela Organização do site de gestão
  (admin com login Microsoft) e pelo script manual `espelhar_bd_operacoes.py` (que apaga o que não está no BD). É ela
  que decide quais usinas o técnico vê na aba Ronda (`_ronda_usinas_do_tecnico`).
- **O campo:** das 1.027 rondas do `fato_ronda`, 664 foram do técnico do cadastro e 280 em usina sem técnico no
  cadastro; na programação das últimas 4 semanas, 303 blocos têm técnico diferente do cadastro e 17 usinas tiveram dois.

O objetivo é o Nexus virar **o único lugar** onde se decide quem cobre cada usina, editado pelo PCM, e o App passar a
ler dali. É a primeira peça de tirar o controle da organização de campo do site de gestão do App.

## 2. Metas, o que não é, e o que seria fracasso

**Metas**
1. Uma tela no PCM onde o PCM põe e tira técnicos de cada usina, à vontade: vários por usina, fixos ou de apoio com data
   para acabar.
2. A ligação gravada no banco do Nexus, por `usina_id` e `pessoa_id` do `cadastro_nexus`, com o histórico de quem mudou
   o quê e quando (governança, prioridade 0).
3. O contrato para o App ler essa ligação e aplicar na aba Ronda, e o pacote de mudança do App descrito para o chat do
   App executar.
4. Ajudar o PCM a acertar a lista: mostrar, por usina, quem de fato rondou e fechou tarefa ali e quem está na
   programação, e (quando o App publicar) o que o App usa hoje.

**Não é (agora)**
- O responsável (supervisor) da usina e a hierarquia (quem responde a quem): ficam para a fase 3, mas o dado já nasce
  com a coluna `papel` para recebê-los sem refazer nada.
- A agenda de rondas (`rondas/programacao`) e a programação semanal do motor do PCM: não mudam aqui.
- O `tecnico_om_id` do cadastro: não muda (decisão de depois: derivar dele ou aposentá-lo).
- Acesso ao App (bloqueio, admin, quem entra): continua no App.

**Seria fracasso, mesmo funcionando**
- No dia em que o App passar a ler o Nexus, um técnico perder usina na aba Ronda sem o PCM ter decidido isso.
- Nome, e-mail ou texto livre em claro no banco (a API é de leitura aberta; o repositório é público).
- Um segundo cadastro de usina ou de pessoa: a tela só aponta para os IDs do `cadastro_nexus`.
- Depois da troca, a ligação continuar editável em dois lugares (Nexus e site de gestão).

## 3. Restrições (da casa)

- `nexus/dados/CLAUDE.md` inteiro, em especial as regras 1 a 13 e "Como entra um dado novo": livro registrado em
  `catalogo.LIVROS` antes de existir, fato no `catalogo.py` com grão, tipo e chave, texto em `explica.py`, radar com 0
  tabelas novas, conferir depois de gravar, pessoa só por `pessoa_id` e `pessoa_hmac`, texto livre só cifrado (Cofre).
- Leitura só do que as duas máquinas leem igual (regra 12): o banco, nunca o armazém local do cadastro.
- Repositório público: nada de nome de colega em código, teste, doc ou commit (`tests/test_sem_nomes_no_repositorio.py`).
- Endereços com `{{ raiz }}`/`url_for`/`na_raiz`; cor só por token nos dois temas; pt-BR; sem emoji; tela conferida
  a 1366 px e a 375 px; o `nexus/pcm/CLAUDE.md` atualizado no mesmo trabalho.
- O App é outro projeto e outro chat: daqui sai o pacote descrito (pasta `_propostas` do App), não mensagem para a
  sessão do App. "Tudo em paralelo": nada muda no campo até o App ligar a leitura.

## 4. O que foi decidido

### 4.1 O dado

Livro `nexus_pcm_atribuicoes` (o mesmo nome que o App usa, `atribuicoes`), uma aba:

**`fato_decisao_atribuicao`** — **1 linha = 1 decisão de pôr ou tirar 1 pessoa de 1 usina num papel.** Sem medida; só
acrescenta; vale a última decisão de cada (`usina_id`, `pessoa_id`, `papel`). O modelo é o do "Setor do pessoal" e dos
motivos do PCM (livro relido antes de gravar, troca integral sob trava, conferido depois).

Colunas (ordem final é do construtor; coluna nova só no fim depois da 1ª gravação):

| Coluna | O quê |
|---|---|
| `decidida_em`, `data_id` | hora ISO de Brasília e o dia (`data_id` AAAAMMDD) |
| `usina_id` | do `cadastro_nexus · usinas` |
| `usina_fracttal` | o nome da usina no Fracttal (a chave do `de_para` "Fracttal · Classificação 1" naquele momento): é por ele que o App acha a usina (`_casar_usina`) |
| `pessoa_id` | do `cadastro_nexus · pessoas` |
| `pessoa_hmac` | HMAC do e-mail da pessoa (`ligacao_cadastro.codigo_da_pessoa`): é por ele que o App acha a pessoa |
| `papel` | `executa` nesta fase; `responsavel` reservado para a fase 3 |
| `na_usina` | `sim` (pôr) ou `nao` (tirar) |
| `de_data_id` | vazio = vale já; com data = começa nesse dia (o apoio das férias da semana que vem já pode ser lançado) |
| `ate_data_id` | vazio = fixo; com data = apoio, que deixa de valer depois desse dia sem ninguém precisar tirar |
| `origem` | `tela` (o PCM na tela), `carga_inicial` (a regra da equipe, abaixo) |
| `decidida_por_hmac` | quem decidiu (HMAC do e-mail do login) |
| `dados_cifrados` | a observação opcional do PCM ("apoio nas férias do titular"), no Cofre |
| `assinatura` | HMAC da linha com uma chave derivada da `NEXUS_PESSOA_HMAC` (rótulo `nexus:pcm:atribuicoes`), no padrão da `decisao_pt`: sem ela o App não aplica |

Vigente = a última decisão de cada chave com `na_usina = sim`, (`de_data_id` vazio ou `<=` hoje) e (`ate_data_id`
vazio ou `>=` hoje), no dia de Brasília. Tirar o titular só durante as férias não entra agora: tira-se e põe-se de
volta.

**O que o `executa` quer dizer** (conferido no código do App, 17/10): no App, `executa` é **a lista de usinas que a
pessoa vê na aba Ronda** (curta, longa e extintores), não "o designado". Hoje ela sai do BD_Operações pela regra da
equipe: cada pessoa da equipe recebe todas as usinas da equipe (`espelhar_bd_operacoes.py`, 299 linhas em 02/09). Na
base do Nexus, 53 equipes têm 1 pessoa e 24 têm 2: a regra da equipe já dá "dois técnicos por usina" na maioria.
Por isso, no Nexus, **a lista de uma usina é exatamente quem vê e pode rondar aquela usina no App** (pendente de
confirmação do Levi, seção 6).

**A carga inicial** (`origem = carga_inicial`, uma vez, pela tela, só administrador): a mesma regra do App aplicada às
bases do Nexus — cada pessoa de campo ativa do `cadastro_nexus · pessoas` recebe as usinas do `cadastro_nexus · usinas`
com o mesmo `equipe_id`. Assim a lista nasce perto do que o campo vê hoje, e o PCM tira e põe a partir daí.

### 4.2 A tela

PCM → **Técnicos por usina** (`/t/pcm/tecnicos-por-usina`), no menu da torre PCM.

- **Quem vê:** setores PCM e Responsáveis UFV (`do_setor`, como o Quadro). **Quem edita:** `telas.pode_programar`
  (administrador ou setor PCM).
- **Visão por usina (padrão):** uma linha por usina do cadastro (não excluída; o filtro já abre em "em operação"):
  usina, equipe, os técnicos vigentes (fixos e apoios, o apoio com "de dd/mm até dd/mm"), e ao lado o que ajuda a
  decidir:
  - quem rondou ou fechou tarefa ali nos últimos 30 dias (`fato_ronda`, `fato_fechamento`, por `pessoa_id`);
  - quem está como técnico na programação da semana em curso (`fato_programacao.pessoa_id_tecnico`);
  - o técnico do cadastro (`tecnico_om_id`);
  - quando o App publicar a foto dele (seção 4.4), quem o App tem hoje, com a diferença destacada.
- **Visão por técnico:** uma linha por pessoa de campo, com as usinas dela (para ver carga e quem está sem usina).
- **Editar:** pôr um técnico (busca entre as pessoas de campo ativas do cadastro; no alto, as que têm evidência ali,
  com a conta: "4 rondas e 2 fechamentos em 30 dias", "na programação da semana", "técnico do cadastro"), tirar (×),
  marcar como apoio com datas, observação opcional. Uma pessoa por clique: não há "aceitar todas as sugestões" (uma
  ronda de cobertura viraria técnico fixo).
- **Pendências para a troca** (bloco à parte, quando a foto do App existir): o que o App tem e o Nexus não consegue
  dizer — pessoa do App cujo HMAC não casa com nenhuma ficha (sem ficha, sem e-mail, ou e-mail do login diferente do
  e-mail do cadastro), usina do App sem `de_para` do Fracttal. O conserto é no cadastro (regra 4 da governança), não
  aqui; a lista tem de chegar a zero antes de ligar a leitura no App.
- **Avisos na linha** (não travam a gravação): usina sem técnico; técnico sem e-mail no cadastro (sem HMAC o App não
  o reconhece); usina sem nome do Fracttal no `de_para` (o App não a acha); técnico que rondou ali e não está na lista.
- **Histórico da usina:** quem pôs e tirou quem, quando, do `fato_decisao_atribuicao`.
- Nomes e e-mails vêm decifrados do cadastro na memória (`NEXUS_CHAVE_CADASTRO`), só para mostrar.

### 4.3 O contrato com o App (o que o Nexus garante)

- O App lê `nexus_pcm_atribuicoes · fato_decisao_atribuicao` pela leitura aberta da API, como já lê o
  `nexus_pt_decisoes` (lista de livros pelo `updated_at`, linhas só quando muda).
- Cada linha vem assinada; o App descarta a sem assinatura válida.
- Usina pelo `usina_fracttal` (nome do catálogo do App), pessoa pelo `pessoa_hmac` (o App reverte testando os e-mails
  que conhece, como no `_nexus_pt_nome`).
- O conjunto vigente de `executa` que vem do Nexus é o que vale no App para quem executa.

### 4.4 O pacote do App (para o chat do App; Levi entrega)

Escrito em `C:\GridcoBuild\app-campo-docs\_propostas\atribuicoes-nexus\LEIA.md`, no formato dos pacotes anteriores
(`ranking-pontos-nexus`, `rondas-tecnico-hmac`). Três passos, nesta ordem:

1. **A1 — a foto do App:** o App publica, com os outros livros (timer aos :25), o livro `organizacao_app_campo` com as
   `atribuicoes` vigentes (usina do catálogo, pessoa em HMAC, papel, de, até, origem). Só leitura. O Nexus mostra a
   diferença na tela e o PCM acerta a lista antes da troca.
2. **A2 — o App lê o Nexus:** um timer lê o livro do Nexus, confere a assinatura e aplica o `executa` vigente em
   `atribuicoes` com origem `nexus`: o conjunto do Nexus SUBSTITUI o `executa` (encerra com `ate` o que o Nexus não
   tem). Interruptor App Setting `NEXUS_ATRIBUICOES` (ausente = desligado). Só se liga com o Levi, com as "Pendências
   para a troca" em zero e a diferença do A1 conferida pelo PCM: assim ninguém perde usina sem decisão do PCM.
   O e-mail do login e o do cadastro serem o mesmo é medido aqui: o HMAC do App que não casar entra nas pendências.
3. **A3 — um lugar só:** com o interruptor ligado, a tela Organização recusa `executa_add`/`executa_del` ("editado no
   Nexus") e o `espelhar_bd_operacoes.py` deixa de tocar no `executa`.

### 4.5 Fases

1. **F1 (Nexus, agora):** livro, catálogo, tela, sugestões e avisos. Nada muda no campo.
2. **F2 (App + PCM):** A1 → o PCM acerta a lista olhando a diferença → A2 e A3 → o Levi liga o interruptor.
3. **F3 (depois):** responsável da usina e hierarquia no Nexus (papel `responsavel`), e o site de gestão sai 100% da
   organização de campo.

## 5. Calls do Claude (o Levi confere)

- Nome do livro e da tela ("Técnicos por usina"), e o termo `atribuicoes` igual ao do App.
- Apoio = o mesmo vínculo com data de início e de fim, e não um papel à parte.
- Responsáveis UFV veem, só PCM e administrador editam.
- A evidência ao lado vem de 30 dias de rondas e fechamentos, da programação da semana e do cadastro; não grava nada
  sozinha.
- Aviso não trava: o PCM pode gravar técnico sem e-mail ou usina sem nome do Fracttal (a tela diz que o App não vai
  receber).
- Usinas = todas as não excluídas do cadastro, abrindo em "em operação"; pessoas = vínculo "Colaborador de campo"
  ativas.
- O A2 substitui o `executa` do App inteiro, e o interruptor só liga com as pendências em zero.

## 6. Decidido com o Levi (17/10/2026, "desenvolva", sobre as duas propostas)

1. A lista do Nexus é exatamente quem vê e pode rondar a usina no App, e nasce da regra da equipe (seção 4.1).
2. Os filtros da tela: equipe, região de campo, responsável, situação (sem técnico, com aviso) e busca, em cascata
   como as outras telas do PCM.

## 7. Fica para o construtor

- A ordem final das colunas, o desenho fino da tela dentro do Design System, paginação e o que vai por fetch.
- Os filtros já decididos (seção 6): equipe, região de campo,
  responsável, situação e busca; o desenho fino deles é do construtor.
- Como reemitir as linhas vigentes de uma usina quando o nome dela no Fracttal mudar no `de_para` (o App acha pela
  grafia do catálogo).
- Os testes (catálogo, grão, vigente com apoio vencido, assinatura igual à do App, nenhum nome no livro, permissão) e as
  mutações, no hábito da casa.
