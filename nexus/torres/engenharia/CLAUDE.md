# CLAUDE.md — torre Engenharia

Engenharia de manutenção: confiabilidade dos ativos, criticidade, FMEA e causa raiz, laudos. Hoje são telas de verdade
a **Mesa do engenheiro** (a primeira da torre, 18/10/2026), a **Confiabilidade** (com o **acompanhamento** dos ativos
com sinal desde 18/10/2026) e o **Quadro da equipe**; as outras caem no placeholder da casca.

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
  a ação é recusada. Quem só vê a tela lê tudo, sem botões. Encaminhar é só para pessoas do setor Engenharia (o nome vem
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
  do cartão também responde na gaveta. O ativo é casado pelo código canônico (`equipamento.canon`): o Fracttal e o livro
  escrevem o mesmo ativo de jeitos diferentes. Da revisão final (18/10/2026), no molde do card das Contestações:
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
- **Leitura (medido em 06/10):** o REST filtra pelo nome do responsável (`personnel_description`, por trecho) e
  IGNORA `id_personnel`. O nome vira a pessoa pela lista `personnel` (só se for UMA; guardada 24 h) e as OS vindas
  pelo nome são conferidas pelo `id_personnel` (homônimo fora). Eram 55 linhas para os 6 (~8 pedidos), guardadas
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
- **Clique no cartão abre o card da OS do OS Creator, o mesmo do Histórico** (Levi, 08/10/2026: "Ao clicar na OS quero
  que abra o mesmo card que aparece quando clicamos em uma OS no histórico do OS Creator Web ... precisamos fazer os
  setores se conversarem"). É o componente da torre OS Creator (`oscreator/card_os_abrir.html`, regra no README de lá),
  com as ações dele: trocar o responsável, etiquetas, notas, concluir, cancelar, clonar. O id da OS (`wid`) e o status
  com o nome do OS Creator (`STATUS_OS` = `api.WO_STATUS`) já vêm do REST, sem pedido a mais. O nº da OS é o link de
  `/os/os/<id>?status=` (Ctrl+clique abre a página inteira numa aba nova). Sem o login do Fracttal (senha de admin), o
  card diz para entrar pelo Fracttal. Quem mudou a OS pelo card volta com `?atualizar=1`: o quadro relê o Fracttal na
  hora (`pedir_releitura(forcar=True)`, no máximo uma a cada 5 s). A gaveta própria (descrição, tarefas, link no
  Fracttal) saiu. O mouse parado 250 ms no cartão já pede o card (`NexusOsCard.prepararAoParar`, 09/10/2026): o clique
  pega a leitura pronta (regras e teto no README da torre OS Creator).

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
