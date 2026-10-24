# CLAUDE.md — torre Engenharia

Engenharia de manutenção: confiabilidade dos ativos, criticidade, FMEA e causa raiz, laudos. Hoje são telas de verdade
a **Mesa do engenheiro** (a primeira da torre, 18/10/2026), a **Confiabilidade** (com o **acompanhamento** dos ativos
com sinal desde 18/10/2026) e o **Quadro da equipe** (com a **página da OS** desde 24/10/2026); as outras caem no
placeholder da casca.

Endereços nunca a partir da raiz (porta única, 09/10/2026: o Nexus pode rodar debaixo de `/nexus`, como no servidor até a fase 4): o link da OS na
Confiabilidade sai com `|na_raiz` e o do cartão do Quadro da equipe com `nexusRota` (regra das torres em
`nexus/torres/CLAUDE.md`; o esquecimento quebra `tests/test_prefixo.py`).

## Mesa do engenheiro (18/10/2026)

O Levi escolheu, no rascunho aprovado, a primeira tela da Engenharia ("Sim, a primeira"), do setor Engenharia
(`Tela.do_setor`: quem é dele a vê sem marcar em Base → Acessos). Cada um vê a sua mesa ("Cada um vê a sua"), e só o
administrador escolhe de quem ver (`?pessoa=<código>`; para os demais o parâmetro é ignorado). O administrador fora da
Engenharia (o da Performance) não está na lista: a 1ª opção do seletor é "A sua mesa", escolhida quando ninguém da lista
está, e a volta a ela; a mesa de outra pessoa diz o nome dela nos títulos e nos números ("Com <nome da pessoa>"), e sem pessoa
escolhida (a senha de administrador) os dois números dela são "—". A rota é `/t/engenharia/mesa`
(`mesa()` em `__init__.py`), o template é `templates/engenharia/mesa.html` e as classes são as `eg-mesa-*` em
`engenharia.css`. Ela entra na `FORA` da pré-carga, porque lê as OS de falha ao abrir.
- **Encaminhados para você:** o que outra pessoa passou e quem recebeu ainda não mexeu (Levi: "Até eu mexer nele"). Sai
  quando a pessoa comenta ou salva (`respondeu` no `acompanhamento.estado`), e o mais antigo vem primeiro. Esses ativos
  não aparecem de novo em "Com você".
- **Com você:** os outros acompanhamentos abertos da pessoa, com falha nova primeiro, depois o nível.
- **Críticos sem dono:** os da lista Ativos com sinal com nível crítico, com o Pegar e o Encaminhar ali mesmo.
- **A faixa:** Encaminhados para você (âmbar quando há), Com você e Críticos sem dono (vermelho quando há), no modelo do
  Acompanhamento de chamados (`kb-kpis`). Cada número é o da lista de mesmo nome (o encaminhado conta só na caixa: o
  número diferente da lista é antiobjetivo do desenho). Sem ler o livro, os números dizem "—" e as listas dizem que não
  leram; com as OS de falha lidas pela metade, os avisos são os da Confiabilidade e o número dos críticos é "—".
- **O clique:** abre a mesma gaveta da Confiabilidade (`_gaveta.html`), com as mesmas ações e rotas. O JS da gaveta
  mora em `static/engenharia-gaveta.js` (`egGaveta.ligar()`), e as duas telas o usam. Por isso a Confiabilidade também é
  do setor Engenharia: o portão do setor pede a marca da tela dona da rota, e sem ela o Pegar da Mesa voltava HTTP 403.
- **Como provar:** `python -m pytest -q tests/test_engenharia_mesa.py`.

## Acompanhamento dos ativos com sinal (18/10/2026)

Levi: "os membros de engenharia ou administradores pegar aqueles ativos com sinal para acompanhar ou alguém da
engenharia poder encaminhar para a pessoa ver!" e "o que está sendo acompanhado sai de ativos com sinal e passam para em
acompanhamento". É o começo de um ecossistema da Engenharia que depois vai aos outros setores ("vamos começar pelo setor
de engenharia para aplicar nos demais setores"). Desenho, decisões e o rascunho aprovado:
`docs/superpowers/specs/2026-10-18-engenharia-acompanhamento-design.md` e `docs/mockups/engenharia-acompanhamento.html`.

| Peça | Onde |
|---|---|
| Regras e o livro | `nexus/engenharia/acompanhamento.py` (o molde é o "Pegar para mim" das Contestações e o cadastro dos motivos do PCM) |
| As falhas de cada ativo | `confiabilidade.calcular(...)["falhasEm"]` (pelo código canônico, todo o período, a regra do sinal) |
| Tela e ações | `__init__.py` (`_gavetas_e_listas`, `_gaveta_de` e as rotas `confiabilidade/acompanhamento/*` e `confiabilidade/diagnosticos/*`), `templates/engenharia/confiabilidade.html` e `_gaveta.html`, classes `eg-acomp*`, `eg-cartao`, `eg-diag*` em `engenharia.css` |

- **Abas:** Ativos com sinal · Em acompanhamento · Encerrados · Indicadores · Diagnósticos (esta só para quem age). O
  ativo com acompanhamento aberto sai de Ativos com sinal; o encerrado também, e **só volta com falha nova** depois do
  fim da análise (a partir do dia seguinte ao fim, no dia de Brasília), com a etiqueta "já acompanhado · <diagnóstico>
  em <fim>". O painel ao lado e a faixa de números continuam sobre todos os ativos com sinal (descrevem a frota).
- **Filtros:** os de hoje valem nas três listas; "Quem acompanha" (Em acompanhamento) e "Quem acompanhava" (Encerrados),
  o parâmetro `quem` (o código da pessoa, nunca o nome). O nível é o de agora em Em acompanhamento e o da entrada em
  Encerrados. Nenhum filtro entra sem o Levi pedir (o de diagnóstico ele não quis).
- **Quem age** (pega, encaminha, salva, comenta, mexe no cadastro): o setor Engenharia (Base → Integração Fracttal; o
  nome do setor, sem acento nem caixa) e o administrador, com login de pessoa: a senha de administrador não diz quem é, e
  a ação é recusada. Quem só vê a tela lê tudo, sem botões. Na lista Ativos com sinal o cartão só abre a gaveta, e o
  Pegar e o Encaminhar ficam nela (Levi, 18/10/2026: "tire esses botões ... da tela inicial, deixe apenas quando clica no
  ativo com sinal!"). Encaminhar é só para pessoas do setor Engenharia (o nome vem
  do pessoal do Fracttal). Qualquer um da Engenharia comenta e muda datas e diagnóstico (o Levi não quis "só quem
  acompanha escreve"). Não há "soltar": quem pegou por engano encaminha ou encerra.
- **Datas:** o início começa no dia do Pegar e pode mudar; o **fim é o dia em que a análise terminou**: preenchê-lo, com o
  diagnóstico, encerra (não há outro botão). Fim antes do início ou depois de hoje, data fora do calendário ou antes de
  20/10/2025 (`acompanhamento.PISO`, o começo das contas; revisão final: "0202-10-15" virava um data_id de 7 dígitos,
  para sempre no livro) é recusado.
  Encerrado fica só para ler e não reabre. Se o fim escolhido é anterior a uma falha, a gaveta avisa na hora (pelo
  `data-falhas`) que o ativo volta para Ativos com sinal, só quando ele ainda tem o sinal de 30 dias (sem sinal, não
  volta, e o aviso não vale).
- **Diagnóstico:** o "A definir" da gaveta manda 0 e limpa o diagnóstico (o Levi, 18/10/2026; o histórico guarda a
  troca); o vazio, que só a API manda, quer dizer "manter". Encerrar exige um diagnóstico escolhido. O nome e a descrição
  do cadastro vão em claro e recusam e-mail ("@"), como o nome do setor.
- **Falha nova** é a do sinal (corretiva e corretiva emergencial, sem o serviço registrado como corretiva): "desde que
  entrou" conta da gravação do Pegar (o início pode ser anterior), e o retorno conta do dia seguinte ao fim.
- **A gaveta grava sem sair dela:** cada ação é POST (`_de_outro_site` → 403) e responde a própria gaveta relida do banco
  com o aviso ou o erro (`_gaveta.html`, a mesma peça da página); ao fechar depois de gravar, a página recarrega. O Pegar
  do cartão da Mesa (Críticos sem dono) também responde na gaveta. O ativo é casado pelo código canônico
  (`equipamento.canon`): o Fracttal e o livro escrevem o mesmo ativo de jeitos diferentes. Da revisão final (18/10/2026), no molde do card das Contestações:
  - a resposta passa por `static/engenharia-gaveta.js`: sessão vencida (o 302 do portão até o Entrar, ou o 401 do fim
    da sessão do Fracttal) recarrega a página; HTTP de erro mostra a falha sem trocar a gaveta (o texto fica);
  - a recusa e o banco fora devolvem o que foi digitado (o comentário, as datas e o diagnóstico escolhidos);
  - página velha: o Pegar diz com quem o ativo já está (a regra 1), e o Encaminhar da gaveta que viu o ativo livre
    (`livre=1`) não passa adiante o acompanhamento que outra pessoa abriu depois;
  - livro ilegível: as abas Em acompanhamento e Encerrados dizem "—" (não 0), a gaveta não diz "Ninguém acompanha" nem
    oferece o Pegar, a aba Diagnósticos não mostra o cadastro inicial; a cópia velha diz a hora da última leitura boa;
  - "Com <pessoa> desde" é quando a pessoa recebeu o ativo (`com_desde`), não o começo do acompanhamento (`desde`);
  - salvar e comentar conferem a origem antes de qualquer leitura do banco, e o código do ativo vem da própria gaveta;
  - a conferência que falha DEPOIS da troca (`GravacaoErro`) não diz "Nada mudou": a troca já foi feita, e a gaveta pede
    para conferir a lista antes de repetir.
- **O dado:** livro `nexus_engenharia_acompanhamento` (`dim_diagnostico` e `fato_acompanhamento_ativo`, 1 linha = 1
  evento), registrado no catálogo antes da 1ª gravação; regra em `nexus/dados/CLAUDE.md`. Nasce na 1ª gravação depois
  do deploy (o 1º Pegar ou a 1ª mudança no cadastro dos diagnósticos), com o cadastro inicial (Comunicação, Disjuntor).
  Com o livro no banco, o cadastro que não vem na releitura é leitura incompleta e a gravação é recusada
  (`livros.existe`): o inicial tem as mesmas 2 linhas, passaria pela trava e desfaria o diagnóstico mexido (auditoria
  da trava, 18/10/2026).
  Quem, o nome de quem acompanha e o comentário só cifrados.
- **Como provar:** `python -m pytest -q tests/test_engenharia_acompanhamento.py tests/test_engenharia_gaveta_js.py`
  (o livro, as regras, a separação das abas, a tela e as ações, no banco falso; inclusive a API devolvendo tudo como
  texto, o código com caixa e espaço, o comentário com HTML, o banco fora e cada achado da revisão final; o JS da
  resposta, no node). A prova não grava no banco de verdade: o livro é para sempre.

## Quadro da equipe (06/10/2026)

Levi: "uma tela que fique no setor de engenharia que agregue todas as OSs que estão abertas ou já foram fechadas ou que
serão abertas para essas pessoas" e "FAÇA UMA TELA DINÂMICA, ESTILO KANBAN E SUPERCARDS, DEIXE ALGO BOM DE GERENCIAR!".
`/t/engenharia/equipe`; leitura em `nexus/engenharia/os_equipe.py`; supercards em `supercards()` e a faixa de números em
`faixa_kpis()` (torre); quadro em `templates/engenharia/equipe.html` (montado no navegador a partir de um JSON; classes
`kb-*` em `engenharia.css`).

- **Quem é da equipe:** os mesmos nomes da Nova solicitação | Engenharia do OS Creator (`OS_WEB_ENGENHARIA_RESPONSAVEIS`
  no .env do OS Creator; `NEXUS_ENGENHARIA_RESPONSAVEIS` no .env do Nexus vale por cima). Nomes nunca no código
  (repositório público). No servidor, a linha tem de estar no .env do OS Creator de lá.
- **Leitura (medido em 06/10):** o REST filtra pelo nome do responsável (`personnel_description`, por trecho e
  literal: um espaço a mais já não casa) e IGNORA `id_personnel`. O nome vira a pessoa pela lista `personnel` (só se for
  UMA; guardada 24 h), as OS são pedidas pelo nome do .env e pelo nome como o Fracttal escreve hoje (`grafias`, sem o
  que um trecho mais curto já cobre) e conferidas pelo `id_personnel` (homônimo fora). Caso que criou a regra
  (18/10/2026): o Fracttal passou a escrever o nome de um engenheiro com dois espaços, e o quadro só achava as duas OS
  antigas dele (de quando era escrito com um); faltavam 20, entre elas as duas abertas na semana. Eram 55 linhas para os 6 (~8 pedidos), guardadas
  5 min; a cópia vencida abre na hora e é relida por trás. Linha do REST é por tarefa; o cartão é por OS.
- **Pronto antes de abrir** (Levi, 09/10/2026: "talvez um carregamento periódico que carregue em segundo plano e deixe
  todos prontos"; `os_equipe.manter_quente`, `_tique`, `marcar_uso`): a cada minuto, se alguém abriu a tela nas últimas
  2 h e a cópia passou dos 5 min, ela é relida por trás (~1,6 pedido por minuto, menos de 1% da cota da empresa);
  ninguém em 2 h, para. Liga em toda máquina (só lê com alguém usando). No servidor o quadro também é lido ao subir,
  210 s depois, após as OS de falha (`nexus/engenharia/instalar`; o PC, com `NEXUS_CAMPO_AQUECER=0`, não lê). Medido
  no PC, 1ª visita depois de subir: 5,98 s lendo o Fracttal na hora; com a cópia pronta, 0,01 s. Prova:
  `tests/test_engenharia_quente.py`.
- **Colunas:** A fazer (status 1, nada começou; a data programada diz atrasada, vence em 2 dias ou "abre em" = as que
  vão abrir), Em execução (alguma tarefa começou), Em verificação (2; mostra a programada, não "atrasada": já foi
  feita), Concluídas (3; as de 30 dias ou todas), Canceladas (4; escondidas).
- **Faixa de números, no modelo do Acompanhamento de chamados do OS Creator** (Levi, 08/10/2026: "Precisamos padronizar
  a estética para que coisas parecidas não pareçam completamente diferentes, nesse caso gostei mais da estética do da
  engenharia porém o card de KPIS eu gostei mais do de chamados"). Era número em cima e rótulo embaixo; agora é o rótulo
  em cima e, na mesma linha, o número colorido pela gravidade e o detalhe que diz por onde começar (classes `kb-kpi*`):
  Em aberto (quantas a fazer, em execução e em verificação), Atrasadas (vermelho; a mais atrasada e há quantos dias),
  Vencem em 2 dias (âmbar; a próxima), Esperando verificação (âmbar quando a mais antiga espera há mais de 7 dias,
  `ESPERA_VERIFICACAO`, contados do fim da execução; sem ele vale a data programada, e a nota diz "programada") e
  Fechadas em 30 dias (verde; a última). As contas são as dos supercards. Não filtram (nunca filtraram). Os 7 dias da
  verificação foram escolha nossa (o mesmo corte do "HÁ MAIS DE 7 DIAS" dos chamados), mostrada ao Levi e aprovada com a
  padronização (09/10). A nota usa o `--mudo` (AA nos dois temas), o mesmo tom da nota do OS Creator (`--mu`).
  A faixa de antes (`.kb-resumo`) ficou no `engenharia.css` e no template (quando o Python não manda `kpis`) só porque o
  5070 segue com o template e o Python de antes na memória até reiniciar, e o CSS vem do disco na hora: sai no primeiro
  ajuste depois do reinício.
- **O quadro é o padrão de quadro de OS:** o Acompanhamento de chamados do OS Creator copia as colunas e os cartões daqui
  (`chamados.css` espelha o `kb-*`, porque o OS Creator não carrega o CSS do Nexus). Mudou o desenho do quadro aqui,
  leve lá (regra em `nexus/torres/oscreator/README.md`).
- **Supercards:** um por pessoa, com a cor dela; em aberto, a trilha por etapa, atrasadas, fechadas em 30 dias e a
  faixa dos próximos 14 dias (um degrau por dia, um ponto por OS programada; fim de semana vazado, hoje marcado). O
  clique filtra o quadro. Busca, Quadro/Por pessoa, concluídas de todo o período e canceladas sem recarregar.
- **Como provar:** `python -m pytest -q tests/test_engenharia_equipe.py` (a faixa: número, gravidade e nota de cada um, e
  a tela com rótulo + número + explicação nos cinco).
- **O clique no cartão abre a página da OS da engenharia** (24/10/2026, seção abaixo; de 08/10 até então era o card do
  OS Creator, que segue no Histórico de lá). O nº da OS é o link dela (Ctrl+clique abre numa aba nova). O cartão mostra
  a prioridade e o status da engenharia, e **pulsa em laranja** a OS aberta (a fazer, em execução, em verificação) sem
  atualização há mais de 7 dias: a sombra em camadas que o Levi mandou ("QUERO O CRISPY PULSANDO DE 0.5 A 1"), numa
  camada por cima do cartão que vai de 0,5 a 1 de opacidade, pelos tokens `--pulso-a71` a `--pulso-a14` (o laranja do
  Nexus nos dois temas; o teste do tema lê todo token como cor, então a sombra mora no `engenharia.css`). Com "reduzir
  movimento", fica parada. Sem ler o livro da engenharia, nenhum pulso (não se sabe se ela mexeu), e o rodapé diz.
  Quem mudou a OS e volta com `?atualizar=1` faz o quadro reler o Fracttal na hora (`pedir_releitura(forcar=True)`, no
  máximo uma a cada 5 s).

## A OS do Quadro da equipe (24/10/2026)

Levi: "Ao clicar quero uma visão parecida com o que aparece quando clica na OS da parte de CHAMADOS > GARANTIA", com os
KPIs da engenharia, o status dela no lugar do ticket do fornecedor, a prioridade (média, alta, urgente), todo comentário
na nota da OS com a data e a hora, o "Solicitar OS" no lugar do "Abrir OS" e, no "Demais respostas do técnico", a
resposta de "Descreva a atividade realizada" da OS filha. Desenho em
`docs/superpowers/specs/2026-10-24-engenharia-os-do-quadro-design.md`.

- **A página:** `/t/engenharia/equipe/os/<nº>` (`equipe_os`, template `os_quadro.html`, classes `eg-os-*`), lida na hora
  no Fracttal (`os_equipe.ler_os`, só leitura: a OS de todas as tarefas, com a nota inteira). Em cima, a etiqueta da
  coluna, o "Solicitar OS" e os quatro números: Status e Prioridade da engenharia ("—" sem escolha: não há padrão),
  Programada (atrasada, vence ou abre em) e Última atualização (o mais novo entre o registro da engenharia, o início e o
  fim das tarefas no Fracttal e a criação; laranja a partir de 7 dias, a mesma conta do pulso). À esquerda o que a
  engenharia faz (Status e prioridade, Dados, OS filhas); à direita o que ela lê (Na nota da OS, Demais respostas do
  técnico, Comentários com a linha do tempo).
- **Status e prioridade** moram no livro `nexus_engenharia_os` (`nexus/engenharia/os_acompanhamento.py`; regra no
  `nexus/dados/CLAUDE.md`): os oito do time (Análise de Solução, Atividade em Andamento, Diagnóstico em Andamento,
  Agendamento de OS, Tratativa com Equipe de Campo, Validação Final, Stand-By, Diagnóstico Concluído; o id é a ordem do
  pedido, nunca reordenar) e Média, Alta, Urgente. A prioridade é a da engenharia, não a criticidade do Fracttal (que
  aparece nos Dados): o caminho do OS Creator não muda a criticidade de OS criada. O salvar é formulário com volta e o
  aviso no endereço; a OS é conferida no Fracttal, não no que o formulário diz.
- **O comentário vai para a nota da OS** pela ponte do OS Creator (`/os/_nexus/engenharia/os/<id>/comentar`, em
  `oscreator/ponte.py`, porque o cookie do Fracttal só vai para /os), na sessão do Fracttal da pessoa: a linha
  `[24/10/2026 14:32] Nome (Engenharia): texto` entra no fim da nota (`api.editar_nota_os`, relida na hora, uma escrita
  por vez). A regra medida do card vale: OS concluída, cancelada ou de várias tarefas não deixa editar a nota (com
  várias, sobrescreveria a observação da tarefa errada); aí o comentário fica só no Nexus e a linha do tempo diz por
  quê. Da revisão final (24/10/2026): a OS que o Fracttal devolve sem tarefas (a leitura que falha "mole") não é
  gravada, porque a nota inteira viraria a linha nova; e a nota que a página mostra tem de estar no que vai ser
  regravado (o Fracttal tem a nota da OS e a da tarefa, e a OS 12191 tinha as duas diferentes), senão o comentário fica
  só no Nexus. Sem a sessão do Fracttal (quem entrou pela Microsoft), a resposta traz o login do Fracttal, que volta
  para a página; a sessão cassada antes do vencimento encerra o Nexus de quem entrou pelo Fracttal (o /os/login, com o
  JWT morto no cookie, voltava direto para a página) e tira o cookie do OS Creator de quem entrou pela Microsoft. Erro
  do Fracttal não grava nada. O comentário também fica no livro (texto e nome cifrados).
- **O banco no caminho do clique:** o quadro e a página leem o livro com prazo curto (`PRAZO_S`, 8 s) e guardam a
  falha pelo minuto da cópia; o livro que existe e veio sem a aba dos eventos é leitura incompleta, não "nada". Sem ler
  o livro, nem pulso no quadro nem "Última atualização" na página (só as datas do Fracttal chutariam a parada).
- **Solicitar OS:** a Nova solicitação do OS Creator com o ativo marcado e esta OS como OS pai
  (`/os/solicitacao?ativo=&os_pai=&os_pai_folio=`, pelo `/os/_nexus/ir`; regra no README do OS Creator). O PCM cria a OS
  filha pela Fila, ligada a esta.
- **OS filhas e Demais respostas do técnico:** o REST filtra por `id_parent_wo` (medido em 24/10/2026; a leitura para em
  3 páginas, para um filtro ignorado não virar o Fracttal inteiro), e de cada filha a resposta de "Descreva a atividade
  realizada" (`work_orders_subtasks`; toda OS que nasce de solicitação tem a subtarefa).
- **Quem mexe:** o setor Engenharia e o administrador, com login de pessoa; os demais leem, sem formulários.
- **Como provar:** `python -m pytest -q tests/test_engenharia_os_quadro.py tests/test_engenharia_equipe.py
  tests/test_oscreator_solic_pcm.py -k "os_quadro or quadro or sugestao"` e a página na cópia de prova.

## Confiabilidade (06/10/2026)

Levi: "traga a aba Confiabilidade do https://pcm.gridco.com.br/, não referenciando diretamente esse caminho mas
construindo algo nosso!". Então o Nexus **não lê o site nem o JSON dele**: lê o Fracttal e faz as contas.

| Peça | Onde | O que faz |
|---|---|---|
| Leitura | `nexus/engenharia/os_falhas.py` | as OS de falha do Fracttal, guardadas em `<pasta de dados>/engenharia/os_falhas.json` |
| Contas | `nexus/engenharia/confiabilidade.py` | sinais dos 30 dias, nível, P90, criticidade, MTBF/MTTR/disponibilidade, indicadores |
| Tela | `__init__.py` + `templates/engenharia/confiabilidade.html` + `nexus/static/engenharia.css` | abas Ativos e Indicadores |

### A leitura (por que é leve)
- O REST filtra pelo **tipo da tarefa** (`tasks_log_task_type_main`). Medido em 06/10: a conta tem 37.960 linhas de OS;
  os quatro tipos de falha somam 13.666 (Corretiva 6.189, Corretiva Emergencial 954, Religamento 4.789, Religamento
  Remoto 1.734). Data não filtra, mas ordena.
- **Vivas** (status 1 e 2): relidas inteiras a cada passada (~2.100 linhas). **Concluídas** (status 3): a 1ª leitura vai
  até 20/10/2025 e fica no arquivo; depois, por `final_date` decrescente, só o que fechou desde a última leitura
  completa menos 3 dias. **Canceladas** (4): fora. 429 no meio: o que veio fica e continua de onde parou.
- 1 pedido por segundo (a cota de 200/min é da empresa toda), releitura no máximo a cada 30 min, primeira leitura 150 s
  depois de subir (`nexus/engenharia/instalar`, desliga com `NEXUS_CAMPO_AQUECER=0`). **O reinício não relê o que
  acabou de ler (13/10/2026)**: o `pedir_releitura` decidia antes de carregar o arquivo, e cada deploy relia tudo; agora
  carrega antes, e a idade é a da última leitura das vivas (`vivas_em`, no arquivo), não "agora".
- O robô do PCM (`gerar_engenharia_json.py`) pagina a conta INTEIRA a cada rodada; aqui não.

### As regras (as do robô do PCM, para os números baterem)
- **Sinal** (só corretiva e corretiva emergencial, criadas nos últimos 30 dias): A = falhas em 30 dias; B = falhas em 7
  dias; D = falhas acima do P90 da família (`sorted(n)[round(.9*(len-1))]`, padrão 2).
- **Serviço registrado como corretiva** (`RX_SERVICO`: limpeza, ensaio, teste, revisão, readequação, projeto, AVCB,
  ajuste de antena, reset, vistoria, inventário, levantamento, instalação de, treinamento, acompanhamento) não conta como
  falha. Só serviço (nenhuma falha e 2 OS ou mais) = monitorar, para reclassificar.
- **Nível:** crítico se A >= 4 ou B >= 3; atenção se A >= 3 ou B >= 2 ou acima do P90; monitorar se A >= 2; criticidade A
  sobe monitorar para atenção. Ordem: nível, só serviço, -falhas, -OS.
- **Família** pelo código e nome (INV, TRK/ETKR, CAB, TRF/SKID, QGBT, Outros); **criticidade** por família
  (`CRIT_PROXY`, 5 notas multiplicadas: 0-55 A, 56-161 B, 162-243 C) enquanto a matriz real não existe.
- **Método do Power BI** (por ativo, os 4 tipos, desde 20/10/2025): MTBF = (horas desde a mobilização efetiva - horas
  paradas) / nº de falhas com início >= 20/10/2025; MTTR = média do incidente ao fim (até 1 dia, horas corridas; acima,
  dias x 12); disponibilidade = MTBF / (MTBF + MTTR). KPIs = medianas sobre os ativos com histórico; meta 85%.

### A tela (o visual, 06/10)
Levi: "acho essa estética bem mais atrativa, o nosso está pouco criativo" (mostrando o pcm.gridco.com.br). Ficou:
abas em pílula; faixa de 5 indicadores; **Ativos** = lista em cartões (selo do nível, título com código e usina,
etiquetas A/B/D/Disp, o número de falhas grande à direita) e, ao clicar, a **gaveta lateral** (`<template>` por
ativo, copiado para a gaveta; Esc ou o véu fecham) com MTBF/MTTR/Disp, "Por que acendeu" e as OS; ao lado, "Onde
está o problema" (falhas por família, com P90), "Criticidade" (A/B/C clicáveis) e "Clientes com sinal" (filtra).
**Indicadores** = painel "Estatísticas" com "Ver por" cliente/usina, filtro de texto, ordenação pelo cabeçalho e
barras dentro das colunas (disponibilidade com o marco de 85%). Classes `eg-*` em `nexus/static/engenharia.css`;
cuidado com `.m` (do campo.css, é fonte de código).

### O que muda em relação ao PCM (de propósito)
- **O ativo é o código** (IBI200-INVR1.3, com a usina dentro). No PCM o MTBF era casado pelo NOME (26 letras), sem a
  usina: o Inversor 1.3 de Ibirapuã 2 saía com 8.406 h, o do Inversor 1.3 de Cipó Guaçu (o certo é 466 h); 318 dos
  1.338 nomes se repetem entre usinas.
- **Usina, cliente, cluster e mobilização vêm do cadastro do Nexus** (registro mestre), pelo de-para do Fracttal
  (`visao._Base().lig`); sem ligação, o texto do Fracttal ("Cliente - Usina - UF"). No PCM a mobilização vinha da
  planilha AUXILIAR.
- **Cancelada não entra** (no PCM entrava nos sinais dos 30 dias, porque ele lia todas as OS).
- **Indicadores por cliente/usina = mediana dos ativos.** No PCM a disponibilidade agregada somava as falhas da frota
  toda e dava Athon 14% (o próprio site avisava).
- Ainda não tem: Tickets, Matriz de criticidade (formulário), E-mail automático e Relatórios FMEA/RCA. No PCM, tickets
  e relatórios gravam num arquivo do GitHub, a matriz é um mockup e o e-mail está sem SMTP (`smtpConfigurado:false`).
  Aqui, quando vierem, vão para o banco (ler `nexus/dados/CLAUDE.md` antes).

### Como provar
- `python -m pytest -q tests/test_engenharia_confiabilidade.py`
- A tela chama `calcular` sem `agora`: os 30 e os 7 dias contam do relógio de verdade. Teste da tela com OS de data fixa
  fixa o relógio do `confiabilidade` (`monkeypatch.setattr(C, "datetime", ...)`); sem isso o `test_tela_de_confiabilidade`
  caiu sozinho em 10/10/2026, quando as OS da fixture (de 03 a 05/10) saíram dos 7 dias.
- Comparar com o `engenharia.json` do PCM (só para conferir, nunca como fonte): os níveis e as contagens dos 30 dias
  devem bater, salvo as OS canceladas e os ativos que o PCM casava errado pelo nome.
