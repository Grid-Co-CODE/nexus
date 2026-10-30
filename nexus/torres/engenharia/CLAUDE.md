# CLAUDE.md — torre Engenharia

Engenharia de manutenção: confiabilidade dos ativos, criticidade, FMEA e causa raiz, laudos. Hoje são telas de verdade
a **Mesa do engenheiro** (a primeira da torre, 18/10/2026), a **Confiabilidade** (com o **acompanhamento** dos ativos
com sinal desde 18/10/2026), o **Quadro da equipe** (com a **página da OS** desde 24/10/2026), as **ETMs**
(26/10/2026) e o **FMEA e causa raiz** (29/10/2026); as outras caem no placeholder da casca.

## Como entregar (trava da área da Engenharia, desde 27/10/2026)

Levi, 27/10/2026: "gostaria que ele pudesse editar somente a parte de engenharia". Quem programa a Engenharia tem o
papel **write** no repositório (nunca admin: o admin passa por cima da regra da `main`), e a `main` só aceita o trabalho
dele por **pull request**:

1. Crie um ramo (`engenharia/<assunto>`), commite e faça push dele.
2. Abra o pull request para a `main`. A conferência **pasta-da-area** (`.github/workflows/pasta-da-area.yml`) aprova se
   o pedido mexe só na área da Engenharia e reprova, listando os arquivos, se mexe fora dela.
3. Verde: pode juntar (merge). Produção segue a `main` sozinha: em ~2 min o servidor reinicia com o pedido (teste
   antes de juntar: `python -m pytest -q`, e a tela no navegador, desktop e 375 px).

**Área da Engenharia:** `nexus/torres/engenharia/` (rotas, templates e este `.md`), `nexus/engenharia/` (a regra sem
Flask), `nexus/static/engenharia*` (o estilo e o JS), `tests/test_engenharia*.py` e o desenho e o plano em
`docs/superpowers/specs/` e `docs/superpowers/plans/` com "engenharia" no nome. Fora dela, com o Levi: o catálogo dos
dados (`nexus/dados/`: livro novo entra primeiro no catálogo), a ponte do OS Creator (`nexus/torres/oscreator/`), o
menu, a casca, o `requirements.txt` e a própria conferência. Precisou mexer fora? Abra o pedido assim mesmo e peça ao
Levi: ele revisa e junta. Quem é da área: a variável `LOGINS_ENGENHARIA` do repositório (os logins do GitHub ficam
fora do código, que é público).

Endereços nunca a partir da raiz (porta única, 09/10/2026: o Nexus pode rodar debaixo de `/nexus`, como no servidor até a fase 4): o link da OS na
Confiabilidade sai com `|na_raiz` e o do cartão do Quadro da equipe com `nexusRota` (regra das torres em
`nexus/torres/CLAUDE.md`; o esquecimento quebra `tests/test_prefixo.py`).

## Mesa do engenheiro (18/10/2026)

- **As OS e as ETMs da pessoa (29/10/2026):** o Quadro da equipe lê só os responsáveis do `.env`
  (`OS_WEB_ENGENHARIA_RESPONSAVEIS`), não o setor: quem é do setor e está fora dessa lista vê "não está na equipe do
  Quadro da equipe" no lugar de um zero falso; a leitura velha (o Fracttal não respondeu) diz a hora; as ETMs ainda sem
  leitura dizem que estão lendo (o bloco some depois, se a pessoa não tiver ETM).

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
- **Críticos sem dono:** os da lista Ativos com sinal com nível crítico, com o Pegar e o Encaminhar ali mesmo. Desde
  29/10/2026 o cartão é enxuto (Levi: "pode tirar o código do ativo, deixa só ativo e usina"): o nome, a usina embaixo,
  os critérios do sinal sem a borda ("só a palavra pintada", `eg-tag--sem`) e os botões 30% menores
  (`eg-mesa-sem-dono`). Nos cartões de Encaminhados e Com você, o código e a usina ficam embaixo do nome.
- **As OS de <pessoa>** (29/10/2026, Levi: "Quero informações das OSs daquela pessoa"): as do Quadro da equipe com a
  pessoa da mesa (o `fid` da lista do setor, o id do Fracttal; sem ele, o nome), os cinco números do quadro só com as dela
  e as abertas (a atrasada primeiro), cada uma abrindo a página da OS. A leitura é a do Quadro, relida por trás; sem
  leitura ainda, a Mesa não espera: diz que está lendo.
- **As ETMs de <pessoa>** ("Se a pessoa tiver ETM atrelada, tem que ter uma visão de ETM"): as OS de ETM com ela, os
  quatro números da tela ETMs e as abertas, abrindo a OS da ETM. Quem não tem ETM não vê o bloco.
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
- **Quem age** (pega, encaminha, salva, comenta, mexe no cadastro): o setor Engenharia (Base → Acessos → Pessoas e setores; o
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
  do cadastro vão em claro e recusam e-mail ("@"), como o nome do setor. **O diagnóstico novo pela própria gaveta**
  (29/10/2026: "gostaria que abaixo tivesse um botão para adicionar diagnósticos"): o "Novo diagnóstico" embaixo da
  escolha manda o formulário inteiro (o botão tem o `formaction`) para `/acompanhamento/<id>/diagnostico-novo`, que põe o
  nome no cadastro e devolve a gaveta com ele escolhido e as datas digitadas; o acompanhamento só muda no Salvar.
- **Os chamados de garantia do ativo** (29/10/2026: "mostrasse as OSs com etiqueta de chamados, caso tenha"): o bloco
  da gaveta com as OS de acompanhamento de chamado dele (`nexus_chamados · fato_chamado`, pelo código canônico, o aberto
  primeiro), cada uma abrindo a página da OS. O banco dos chamados fora tira o bloco, e a gaveta segue.
- **A gaveta acompanha o nome do ativo** (29/10/2026: "o texto do ativo está quebrando, a barra lateral pode se adaptar"):
  o `engenharia-gaveta.js` mede o título numa linha só e abre a gaveta até 860 px (no celular, a tela toda); os quatro
  números dela ficam centrados.
- **Falha nova** é a do sinal (corretiva e corretiva emergencial, sem o serviço registrado como corretiva): "desde que
  entrou" conta da gravação do Pegar (o início pode ser anterior), e o retorno conta do dia seguinte ao fim.
- **A OS de análise no Fracttal** (29/10/2026: "quando eu clico em pegar para acompanhar criar uma OS para a pessoa que
  pegou a atividade"; "Ao encaminhar gera uma OS no nome daquela pessoa da engenharia"). O Pegar e o Encaminhar do ativo
  livre criam a OS (`nexus/engenharia/os_analise.py`): o título "[<nome curto do ativo>] - Análise de recorrência de
  falhas" (o `os_web.ativo_curto.curto` do clone, sem marca, modelo nem endereço), o tipo Administrativa com a
  classificação Programada / Elétrica (a OS de análise do clone, como as de ETM; decisão do quiz), a etiqueta ENGENHARIA
  (sem ela no Fracttal a OS sai e a gaveta avisa), o responsável pelo id do Fracttal da pessoa (a lista do setor; sem o id,
  recusa), a data do evento na 2ª falha dos 30 dias (a que acendeu o sinal), a nota com o dia, a hora, quem assumiu (ou
  quem encaminhou para quem) e as falhas até ali, e a subtarefa "Diagnóstico". Encerrar (o fim com o diagnóstico) responde
  a subtarefa com o nome do diagnóstico, lança a execução das 8h do início às 18h do fim (nunca depois de agora) e CONCLUI
  a OS, o que não volta: as regras do salvar são conferidas antes (`acompanhamento.conferir_encerrar`), e a OS que outra
  tentativa já concluiu (`ERROR_WO_FINISHED`) segue para o Nexus. Encaminhar um acompanhamento com OS troca o responsável
  dela (`mudar_responsavel`, a nota fica) e escreve a linha na nota; o comentário vai para a nota da OS, como no Quadro da
  equipe (a mesma `_acrescentar_na_nota` e a mesma trava). Com a OS, a gaveta mostra o número (a página dela no Quadro) e o
  Solicitar OS e o Criar OS com ela como OS pai e a data do evento dela, como a página da OS do Quadro. As ações da gaveta
  (e o Pegar do cartão da Mesa) vão para a ponte do OS Creator (`/os/_nexus/engenharia/acompanhamento/...`, em
  `nexus/torres/oscreator/ponte.py`), porque o cookie do Fracttal só vai para /os; o Fracttal vem ANTES do livro (o que ele
  recusa não entra no Nexus), e o livro que falha depois diz o número da OS e pede para não repetir. Sem a sessão do
  Fracttal (quem entrou pela Microsoft), a recusa traz o "Entrar pelo Fracttal", que volta à tela; a sessão vencida no
  meio tira do Nexus quem entrou pelo Fracttal (a regra do comentário da OS). O acompanhamento aberto antes de 29/10/2026
  fica sem OS e segue só no Nexus (o quiz: "Ficam sem OS"). As rotas antigas da Confiabilidade continuam, sem o
  Fracttal, mas recusam encerrar, comentar e encaminhar um acompanhamento COM OS ("recarregue a página"): a página aberta
  antes do deploy posta nelas, e o Fracttal ficaria para trás. Da revisão independente de 29/10/2026:
  - nada vai ao Fracttal sem o livro lido agora (`_livro_lido`: a leitura que falhou ou a cópia velha não confere quem
    está com o ativo); um ativo por vez (`ponte._trava_do_ativo`, o servidor é um processo só: o segundo ouve "agora
    mesmo");
  - a OS criada que o livro não gravou fica em `ponte._OS_SEM_LIVRO`, e a tentativa seguinte (Pegar ou Encaminhar) usa a
    MESMA, passando o responsável se for outra pessoa: repetir não cria outra OS;
  - a OS concluída ou cancelada no próprio Fracttal (`os_analise.situacao`, pelo `status_da_os`) não recebe nada: o
    encerrar, o comentário e o encaminhar seguem só no Nexus e dizem isso; o erro de OS fechada casa com ou sem o "_";
  - encerrar não lança uma execução a cada tentativa (a tarefa que já tem execução não ganha outra), e sem a subtarefa
    Diagnóstico nada é concluído; o aviso diz o que de fato foi feito;
  - o encaminhar da OS nova recusa se o ativo ganhou dono no meio (`acompanhamento.encaminhar` com `os`), e a linha do
    encaminhar vai à nota sob a mesma trava do comentário;
  - o "Salvar diagnóstico" é `type="button"` com `data-eg-acao` (o `engenharia-gaveta.js` manda): como botão de enviar,
    ele recebia o Enter dos campos de data e, no navegador sem `submitter`, o clique ia ao Salvar, que com o fim conclui a
    OS. O Enter no nome do diagnóstico novo vai a ele, nunca ao Salvar.
  Prova: `tests/test_engenharia_os_analise.py` (o Fracttal falso; o clone de verdade, sem rede).
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
- **Como provar:** `python -m pytest -q tests/test_engenharia_acompanhamento.py tests/test_engenharia_gaveta_js.py
  tests/test_engenharia_os_analise.py`
  (o livro, as regras, a separação das abas, a tela e as ações, no banco falso; inclusive a API devolvendo tudo como
  texto, o código com caixa e espaço, o comentário com HTML, o banco fora e cada achado da revisão final; o JS da
  resposta, no node). A prova não grava no banco de verdade: o livro é para sempre.

## FMEA e causa raiz (29/10/2026)

Levi: "Tem que ter emitir FEMEA emitir causa raiz do pcm.gridco.com.br use como referência e implemente". A referência é
o módulo Confiabilidade do painel do PCM (`novo.html` do `gridco-pcm-data`: as funções `fmea(a)`, `rca(a)`, a `BIB` e o
`pre(a)`); aqui as mesmas duas folhas, na mesma ordem, e o emitido vai para o banco (lá ia para um arquivo do GitHub).

| Peça | Onde |
|---|---|
| A biblioteca de modos de falha | `nexus/engenharia/biblioteca_falhas.py` (`BIBLIOTECA`, `pre`, `ocorrencia`, `funcao`) |
| O livro e as regras | `nexus/engenharia/fmea.py` (`emitir`, `relatorios`, `por_ativo`, `proximo_numero`, `limpar_campos`) |
| Tela e rotas | `__init__.py` (`fmea`, `fmea_novo`, `fmea_emitir`, `fmea_ver`, `_sugestoes`, `_folha`), `templates/engenharia/fmea.html` (a lista), `fmea_folha.html` (a folha, de emitir e de ver), o bloco "FMEA e causa raiz" do `_gaveta.html`; `nexus/static/engenharia-folha.css` |

- **Onde se emite:** na gaveta do ativo (Confiabilidade e Mesa), "Emitir FMEA" e "Emitir causa raiz" abrem a folha
  (`/t/engenharia/fmea/novo?tipo=fmea|rca&ativo=<código>`), já com o que o Nexus mede (negrito: as OS da janela, as
  falhas de 30 dias, MTBF, MTTR, disponibilidade, a ocorrência), o que a biblioteca sugere (verde, com o selo) e o resto
  a preencher (amarelo). O ativo precisa estar na Confiabilidade (Ativos com sinal ou a conta de disponibilidade); fora
  dela, a lista diz por quê (404). A tela FMEA e causa raiz é a lista (a última revisão de cada número; Todos, FMEA,
  Causa raiz e a busca) e é do setor Engenharia (`do_setor`): sem isso, com o portão ligado, o Emitir da gaveta voltava
  403 (o caso do Pegar da Mesa, 18/10/2026).
- **As folhas (as do PCM):** FMEA = cabeçalho, ponto da falha (com o tipo de falha, que o PCM não tinha), análise
  (modo, efeito e causa, duas linhas), avaliação do risco (OCC medida pelas falhas de 30 dias, `ocorrencia`: 5 ou mais
  = 10, 4 = 8, 3 = 6, 2 = 4, senão 2; SEV e DET de 1 a 10; RPN = OCC x SEV x DET, alto a partir de 150, médio a partir
  de 60) e três ações com o RPN depois. Causa raiz = evento (com o acompanhamento aberto do ativo no lugar do ticket do
  PCM), descrição, os cinco porquês, a causa raiz, a classificação (tipo de falha em lista fechada), três ações com a
  matriz GUT (1 a 5) e a verificação. Sem padrão da biblioteca, a severidade parte da criticidade (A = 8, B = 6, C = 4)
  e a detecção de 6, como no PCM, sem pintar de verde. A norma no rodapé é a de cada folha (IEC 60812, IEC 62740; o PCM
  citava a IEC 60300-3-11 nas duas).
- **A biblioteca:** o padrão é o MAIS FREQUENTE nas falhas do ativo (3 strings sem corrente e 1 religamento é problema de
  string), casado pela tarefa e pela nota da OS; o serviço registrado como corretiva é a marca da Confiabilidade
  (`servico`, `soServico`), e a folha avisa "Isto parece não ser falha". O padrão novo entra em `BIBLIOTECA` com o caso.
  O rascunho por IA do PCM era um exemplo fixo (mockup) e não veio.
- **Número e revisão:** FMEA-AAAA-NNNN e RCA-AAAA-NNNN, o maior do tipo no ano + 1, sob a trava da gravação. O livro só
  acrescenta: corrigir é "Nova revisão" (R01, R02...), com a folha da anterior e o que ELA mediu (a foto do ativo e das
  OS, a ocorrência, o padrão; revisão de 29/10/2026: medir de novo trocava o RPN de quem só corrigia um texto); a revisão
  de outro tipo ou de outro ativo é recusada. A folha emitida mostra o padrão da biblioteca que foi gravado, não o que
  ela acharia de novo na foto (que não guarda a nota do técnico). A página do emitido (`/t/engenharia/fmea/<número>`, `?rev=N` para uma anterior) é só leitura; "Imprimir /
  PDF" é a impressão do navegador (só a folha, em A4).
- **O livro:** `nexus_engenharia_relatorios` · `fato_relatorio_falha`, 1 linha = 1 emissão (uma revisão), registrado no
  catálogo antes da 1ª gravação (`so_cresce`). Em claro só os IDs (ativo, usina, quem emitiu, o acompanhamento aberto),
  o número, o tipo, a revisão, o padrão da biblioteca, o tipo de falha e as notas do RPN; o texto da análise, a equipe e
  os responsáveis (nomes), quem emitiu e a FOTO do ativo e das OS (sem quem atendeu nem a nota do técnico) só cifrados.
  A foto é o que a folha mostra depois: a janela de 30 dias anda, e o relatório não muda com ela. Campo que a folha não
  tem fica fora; texto acima de 300 letras (a descrição, 2.000), data fora de AAAA-MM-DD e nota fora da escala são
  recusados com o porquê (nada se corta calado).
- **Quem:** emite quem age no acompanhamento (administrador e setor Engenharia, com login de pessoa: a senha de
  administrador não diz quem é); lê quem vê a tela.
- **Como provar:** `python -m pytest -q tests/test_engenharia_fmea.py` (a biblioteca, o livro no banco falso, a
  numeração, a revisão, as recusas, as telas, a gaveta, o outro site e o portão do setor). Na cópia de prova
  (`ferramentas/subir_copia_de_prova.py`, banco falso): emitir pela gaveta, conferir a página, a lista, o celular (375
  px, a tabela rola dentro da folha) e os dois temas (a folha é papel branco nos dois).

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
  OSs sem atualização (âmbar; a mais parada e há quantos dias; "—" sem ler o livro da engenharia: Levi, 24/10/2026,
  "tire o VENCEM EM 2 DIAS e bote OSs sem atualização"), Esperando verificação (âmbar quando a mais antiga espera há mais de 7 dias,
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
  Nexus nos dois temas; o teste do tema lê todo token como cor, então a sombra mora no `engenharia.css`), com um
  contorno de 1,5 px e um halo por cima, pulsando juntos (Levi, 24/10/2026: "algo mais forte que destacasse um pouco
  mais porém sem destacar tanto"). Pulsa também
  com "reduzir movimento" (Levi, 24/10/2026: "a sombra não está pulsando": o Windows dele está sem os efeitos de
  animação, e o nexus.css tira toda animação nesse caso; o pulso só muda a opacidade de uma sombra, sem movimento).
  Sem ler o livro da engenharia, nenhum pulso (não se sabe se ela mexeu), e o rodapé diz.
  Quem mudou a OS e volta com `?atualizar=1` faz o quadro reler o Fracttal na hora (`pedir_releitura(forcar=True)`, no
  máximo uma a cada 5 s).

## A OS do Quadro da equipe (24/10/2026)

Levi: "Ao clicar quero uma visão parecida com o que aparece quando clica na OS da parte de CHAMADOS > GARANTIA", com os
KPIs da engenharia, o status dela no lugar do ticket do fornecedor, a prioridade (média, alta, urgente), todo comentário
na nota da OS com a data e a hora, o "Solicitar OS" no lugar do "Abrir OS" (e, desde 25/10, o "Criar OS") e, no
"Demais respostas do técnico", a
resposta de "Descreva a atividade realizada" da OS filha. Desenho em
`docs/superpowers/specs/2026-10-24-engenharia-os-do-quadro-design.md`.

- **A página:** `/t/engenharia/equipe/os/<nº>` (`equipe_os`, template `os_quadro.html`, classes `eg-os-*`), lida na hora
  no Fracttal (`os_equipe.ler_os`, só leitura: a OS de todas as tarefas, com a nota inteira). **O topo é o da tela do
  chamado da Garantia** (Levi, 24/10/2026: "quero quase idêntico na estrutura mesmo então essa parte de cima quero na
  mesma estrutura e fonte os botões quero nas mesmas posições"): as medidas do `chamados.css` do OS Creator copiadas em
  `eg-ac-*`, com os tokens do Nexus e a Inter de lá. Numa linha a volta, a pílula do estado (`_topo_da_os`: vermelho
  atrasada, âmbar aberta, com "há N dias sem atualização" quando parada, verde concluída, apagada cancelada) e o título
  da OS; embaixo a OS e o ativo em verde (Levi, 24/10/2026: "No título invés de OS e ativo bote o título da OS, no
  lugar do título da OS bote OS e ativo"; com mais de um ativo, "N ativos", e o bloco Ativos lista os de cada tarefa,
  em cima da nota, de 5 em 5 com o "Mostrar mais", como a tabela de ativos da Nova solicitação; Levi, 24/10/2026: "no
  ativos também quero que limite a 5 por vez!"), e o cliente · usina, o tipo e o status no Fracttal; à direita, no lugar do "Abrir a OS", o
  "Solicitar OS" e o "Criar OS"; e a faixa dos quatro números no desenho da de lá (o valor de texto comprido quebra, em vez de cobrir o
  vizinho). Os quatro números: Status e Prioridade da engenharia ("—" sem escolha: não há padrão),
  Programada (atrasada, vence ou abre em) e Última atualização (o mais novo entre o registro da engenharia, o início e o
  fim das tarefas no Fracttal e a criação; laranja a partir de 7 dias, a mesma conta do pulso). O corpo também é o da tela do chamado (`.ac-det`, `.bloco`, `ol.cadeia`, `dl.dados`, `.tl`,
  copiados em `eg-ac-det`, `eg-bloco`, `eg-cadeia`, `eg-ac-dados`, `eg-tl`): à esquerda, em 310 px, o que a engenharia
  faz (Status e prioridade; A cadeia da OS; Dados, só ativo, usina, responsável, quem criou a OS no Fracttal, o
  `created_by`, desde 27/10/2026, criação e etiquetas); à direita o que
  ela lê (Na nota da OS; Demais respostas do técnico, numa tabela por OS de campo; Comentários, na linha do tempo das
  Observações de lá: a data e o ano à esquerda, o mais novo em verde, a mudança de status ou prioridade com o ponto
  âmbar). **A nota da OS** é a que o card do OS Creator lê (`os_equipe._nota_da_os`: a da tarefa, `task_note`, senão a
  `note`; Levi, 24/10/2026: "não está puxando a nota da OS da engenharia", a página mostrava só a `note`).
- **Trocar o responsável** (Levi, 24/10/2026: "em responsável quero a opção de mudar de responsável que nem é feito
  no chamados"): o "trocar" ao lado do nome nos Dados, só para a Engenharia, abre o diálogo da tela do chamado (Hoje
  está com..., a busca pelo nome, Atribuir), pela API do OS Creator (`/os/api/responsaveis` e
  `/os/api/os/<id>/responsavel`, a mesma do `os_acoes.js`), na sessão do Fracttal da pessoa; sem ela, o aviso traz o
  login do Fracttal. O nome muda ali mesmo, e a volta ao quadro passa a levar `?atualizar=1`: o quadro guarda a leitura
  do Fracttal por até 5 min, e a OS seguiria com quem estava.
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
- **Solicitar OS:** a Nova solicitação do OS Creator com o ativo marcado, esta OS como OS pai e a data do incidente dela
  (`/os/solicitacao?ativo=&os_pai=&os_pai_folio=&data=`, pelo `/os/_nexus/ir`; regra no README do OS Creator). A data é
  o `event_date` do Fracttal, guardado em UTC, levado a Brasília (o campo da Nova solicitação é de Brasília; a OS 16502
  de 08/10 às 09:00 UTC vai como 06:00). O PCM cria a OS
  filha pela Fila, ligada a esta.
- **Criar OS** (Levi, 25/10/2026: "ao lado do botão de solicitação quero um botão de 'Criar OS'. Fará os mesmos
  preenchimentos automáticos que já faz na solicitação"): o Criar OS do zero do OS Creator (o Tradicional,
  `/os/tradicional?` com o mesmo endereço do Solicitar OS) com o cliente, a usina e o ativo marcados, a data do
  incidente desta OS e ela como OS pai no Passo 1 (ao lado das datas desde 26/10/2026), e as subtarefas "Descreva a atividade realizada" e "Ficou alguma
  pendência? Se sim, descreva", que viraram o padrão do Criar OS do zero para todos (`tradicional_web.SUBS_PADRAO`,
  as mesmas palavras da base da Solicitação; regra no README do OS Creator). A engenharia cria a OS de campo direto,
  sem passar pela Fila do PCM, e a resposta dela entra em Demais respostas do técnico.
- **A cadeia da OS e Demais respostas do técnico:** a OS da engenharia é a 1ª da cadeia e as OS de campo que nascem dela
  pelo Solicitar OS ou pelo Criar OS vêm depois (Levi: "o ideal é que essa OS da engenharia se torne OS pai de OSs de campo
  futuramente"), cada uma com o nº e a seta do PDF da cadeia do chamado (o `/os/api/os/pdf` do OS Creator, com as
  fotos; sem a sessão do Fracttal, o aviso traz o login dele, que volta para a página). O REST filtra as filhas por
  `id_parent_wo` (medido em 24/10/2026; a leitura para em 3 páginas, para um filtro ignorado não virar o Fracttal
  inteiro), e de cada filha a resposta de "Descreva a atividade realizada" (`work_orders_subtasks`; toda OS que nasce
  de solicitação tem a subtarefa).
- **Quem mexe:** o setor Engenharia e o administrador, com login de pessoa; os demais leem, sem formulários.
- **Como provar:** `python -m pytest -q tests/test_engenharia_os_quadro.py tests/test_engenharia_equipe.py
  tests/test_oscreator_solic_pcm.py -k "os_quadro or quadro or sugestao"` e a página na cópia de prova.

## ETMs (26/10/2026)

Levi, com o zip do app de ETM da Engenharia (desktop, FastAPI, um .exe por máquina): "Quero que inclua essa visão de
ETMs no Nexus, engenharia, aba própria. Deixe o design alá Nexus!". No quiz: o histórico do app vem uma vez, e nas OS
em aberto os comentários vão também para a nota da OS; entrega por partes; o comentário da ETM vai para a nota da OS,
como no Quadro da equipe. Desenho em `docs/superpowers/specs/2026-10-26-engenharia-etm-design.md`; plano em
`docs/superpowers/plans/2026-10-26-engenharia-etm.md`.

- **A tela:** `/t/engenharia/etm` (`etm()`, `etm.html`, do setor Engenharia), as abas do app no desenho do Nexus
  (Levi, 26/10/2026: "o deploy que te mandei tinham abas só disso!"): **Planner**, **Histórico**, **Estações em
  Aberto** e **Fechamentos**, com a faixa de números em cima. A aba, a usina aberta e os filtros ficam no `sessionStorage` da aba do
  navegador: a volta da OS (`?atualizar=1`) cai no mesmo lugar; o endereço leva a aba (`#historico`, `#abertas`).
- **O Planner:** à esquerda a coluna de filtros do Acompanhamento PCM (Levi, 26/10/2026: "o estilo de lista dos filtros
  está todo bugado e torto, deixe no nível do nexus!" e "tem um espaço livre do lado esquerdo que está sendo mau
  utilizado"): a pesquisa geral, os seletores Cliente, Usina, Tipo de trabalho, Status da OS, Criado por e Responsável
  (a busca, as caixas de marcar com a conta de cada opção com os outros filtros, Selecionar todos e Limpar; o painel
  abre dentro da coluna, que rola sozinha), o período e "Redefinir filtros"; à direita o quadro, com as colunas Não
  iniciadas, Em andamento, Finalizadas e Canceladas (a coluna do quadro levada à do app: a verificação ainda está em
  andamento) e, na coluna Em andamento, as etiquetas da Engenharia. **O clique filtra** (Levi: "não precisa desse botão
  "aplicar" clicou já filtrou!"): a caixa marcada vale na hora e o painel fica aberto, na mesma busca e rolagem; nada
  ou tudo marcado é Todos. O Solicitante saiu ("tire o filtro do solicitante!"; segue na pesquisa geral). A **usina vai
  curta** ("o nome da usina está vindo completo, o ideal seria sem a informação do nome do cliente e estado!",
  `etm.usina_curta`: do "Cliente - Usina - UF" fica o meio; se não sobra nada, o nome inteiro); o filtro guarda o nome
  inteiro, porque duas usinas de clientes diferentes podem ter o mesmo nome curto (aí a opção leva o cliente). O
  **Status da OS** (o do Fracttal: Em Processo, Em Verificação, Concluída, Cancelada) entrou no lugar do "mostrar
  canceladas": sem marcar, as canceladas ficam de fora. Abaixo de 1100 px a coluna sobe para cima do quadro, com os
  seletores em duas colunas. Faixa: Abertas no Fracttal, Abertas para a Engenharia (a regra das "Estações em Aberto" do
  app: a OS só sai com o diagnóstico ou o finalizado, não quando o Fracttal fecha), Em acompanhamento e Finalizadas em
  30 dias. Sem ler o livro das marcações, a tela diz e as duas contas dele ficam "—".
- **O Histórico** (a visão histórica do app): os clientes, as usinas de cada um (pelas ETMs, com quantas ETMs e OS; a
  usina sem OS também aparece, como no app) e a lista das OS da usina, a mais nova primeiro, com o status do Fracttal,
  as marcações e quantos comentários cada uma tem (contados pelas linhas do `nexus_engenharia_os`, sem abrir a cifra),
  o período, as canceladas e o **Chat da usina** (os comentários da Engenharia em todas as OS dela, numa gaveta, lidos no
  clique pelo `/etm/usina/comentarios`: a cifra abre só para as OS da usina; o comentário cuja cifra não abre, de outra
  chave do cofre, é contado e a gaveta diz). A busca acha a usina em todos os clientes, sem acento nem caixa. Sem a
  coluna de filtros: a navegação é a do app.
- **As Estações em Aberto** (a visão atual do app): as usinas com OS aberta para a Engenharia (a mesma regra da faixa),
  com quantas OS e há quanto tempo (a OS mais antiga; alerta a partir de 7 dias), e as **Estações em Acompanhamento**
  (as usinas com OS marcada Em acompanhamento). A coluna de filtros vale aqui também, menos o Status da OS (a regra é a
  da aba). O clique abre o quadro da usina, com **Finalizar pela Engenharia** em lote (só quem é da Engenharia ou
  administrador): as OS da coluna Finalizadas que a pessoa vê, conferidas no servidor (`/etm/finalizar`) na última
  leitura do Fracttal (da usina e finalizadas nele) e no livro (sem diagnóstico nem o finalizado), numa gravação só
  (`etm_marcas.finalizar_lote`); a resposta diz as que já estavam encerradas e as que não estão mais finalizadas. O
  pedido torto (sem a usina, a lista que não é lista, mais de 500 OS) volta 400; enquanto o pedido está no ar o botão
  fica desligado, e a resposta só aparece na usina do pedido. E **Ver histórico desta usina**, que abre a usina no
  Histórico. As duas rotas (`/etm/finalizar` e `/etm/usina/comentarios`) respondem 503 "lendo" com a cópia ainda
  vazia, logo depois de subir: "nenhum comentário" ou "não está mais finalizada" seria mentira. Sem o livro das marcações, a aba diz e não lista nada
  (não dá para saber o que está aberto para a Engenharia).
- **A leitura** (`nexus/engenharia/etm.py`, medida em 26/10/2026, só leitura): `items?field_1=Estação Meteorológica` dá
  as 172 ETMs (a descrição confere) e `work_orders?items_log_description=Estação Meteorológica` as 1213 OS delas: 15
  pedidos, contra os 172 do app (um por ETM). Fica a OS cujo código é de ETM, uma por número, no cartão do Quadro
  (`os_equipe._cartao`). A usina de cada ETM (`groups_1_description` do ativo) dá as usinas do Histórico; a da OS
  usa o mesmo nome limpo ("Usina não identificada" sem o grupo), senão o espaço dobrado separava uma usina em duas. No teto de páginas a leitura é recusada (um filtro ignorado viraria o Fracttal inteiro). Cópia
  de 5 min, relida por trás enquanto a tela é usada e 270 s depois de subir (`etm.manter_quente`, no `instalar`).
- **Engenharia, Chamados e Campo** (Levi, 26/10/2026: "Engenharia e Chamados vai pelas pessoas dos setores, Campo é o
  restante!"): o setor de quem está com a OS, pelo id do Fracttal, nos setores de Base → Acessos → Pessoas e setores
  (`nexus_setores`, a última decisão de cada pessoa; os nomes "Engenharia" e "Chamados", sem acento nem caixa). Cada
  cartão tem o selo (azul, verde, neutro), os três filtram e a faixa conta as abertas de cada um. Sem o banco dos
  setores, a Engenharia vem da lista do Quadro da equipe (pelo nome), Chamados não se separa e a tela diz. Medido em
  26/10/2026: 7 pessoas na Engenharia e 2 em Chamados, 260 OS na tela (54, 1 e 205).
- **Quais OS entram:** a regra do app sem nome no código. Corretivas e Administrativas de ETM, mais as de responsável ou
  solicitante da Engenharia ou de Chamados (o solicitante é texto livre: casa pelo nome do Fracttal das pessoas dos
  setores, `fracttal_pessoal`).
- **A OS de ETM:** `/t/engenharia/etm/os/<nº>`, a mesma página da OS do Quadro (`_pagina_da_os`, uma só para as duas
  telas) com o painel "Marcações da Engenharia" no lugar de Status e prioridade (o diagnóstico e o status pós-OS num
  formulário; a etiqueta, o acompanhamento e o finalizado um botão cada; só a Engenharia grava, pelo
  `/etm/os/<nº>/marcar`), o "Checklist da OS" (as subtarefas e as respostas, na ordem do Fracttal), as marcações na
  linha do tempo junto dos comentários e os números Diagnóstico, Status pós-OS, Em aberto e Última atualização. A volta
  e a troca de responsável voltam para ETMs; a OS que não é de ETM abre a página comum.
- **O livro das marcações:** `nexus_engenharia_etm` (`nexus/engenharia/etm_marcas.py`; regra no `nexus/dados/CLAUDE.md`),
  um evento por marcação, as listas do app nas três dim. Os comentários são os da OS da Engenharia
  (`nexus_engenharia_os`), que vão para a nota da OS com as mesmas travas do Quadro.
- **O histórico do app, uma vez:** o painel "Trazer o histórico do app de ETM" (só o administrador, no pé da tela) lê o
  repositório privado do app no GitHub (`NEXUS_ETM_GITHUB_TOKEN` e `NEXUS_ETM_GITHUB_REPO` no .env: o nome do
  repositório traz o de uma pessoa), mostra a prévia e grava por trás (`nexus/engenharia/etm_historico.py`; a ponte
  `/os/_nexus/engenharia/etm/historico`, porque a nota vai na sessão do Fracttal de quem importa). Os comentários
  ("**Autor:**\ntexto" no app) entram com o autor e a data de lá (`origem` "app_etm" e o id do comentário); as labels
  viram as marcações atuais, com a data em que foram postas. Nas OS em aberto, os comentários vão para a nota da OS numa
  escrita por OS, do mais antigo ao mais novo; a nota que falha deixa os comentários daquela OS para a próxima. Trazer
  de novo não repete nada (o id no livro e a linha que já está na nota).
- **Segurança:** o Nexus não usa nenhuma credencial do app de ETM: lê o Fracttal com a dele e o GitHub com o token do
  .env.
- **Os Fechamentos** (Levi, 26/10/2026: "Pode fazer a aba Fechamentos por semana, como no app."): quantas OS fecharam
  em cada semana (de segunda a domingo, a conta em UTC para o fuso não mudar o dia), da mais nova para a mais velha,
  com a barra do tamanho de cada semana perto da maior; a semana abre no clique e mostra os cartões, com o dia do
  fechamento. Duas visões, como no app: **no Fracttal** (as finalizadas, pelo dia do fim) e **pela Engenharia** (o dia
  em que ela encerrou a OS: o diagnóstico ou o finalizado, o que veio por último, de qualquer status no Fracttal;
  `etm_marcas.encerrada_em`, e desligado o finalizado vale o diagnóstico). A coluna de filtros vale aqui, menos o
  Status da OS, e o período passa a ser o da data do fechamento. Sem o livro das marcações, a visão pela Engenharia diz
  e não lista nada.
- **Prova:** `tests/test_engenharia_etm.py` e `tests/test_engenharia_etm_historico.py` (Fracttal, banco e GitHub falsos).

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
- Ainda não tem: Tickets, Matriz de criticidade (formulário) e E-mail automático. No PCM, tickets gravam num arquivo
  do GitHub, a matriz é um mockup e o e-mail está sem SMTP (`smtpConfigurado:false`). Aqui, quando vierem, vão para o
  banco (ler `nexus/dados/CLAUDE.md` antes). O FMEA e a causa raiz vieram em 29/10/2026 (seção acima).

### Como provar
- `python -m pytest -q tests/test_engenharia_confiabilidade.py`
- A tela chama `calcular` sem `agora`: os 30 e os 7 dias contam do relógio de verdade. Teste da tela com OS de data fixa
  fixa o relógio do `confiabilidade` (`monkeypatch.setattr(C, "datetime", ...)`); sem isso o `test_tela_de_confiabilidade`
  caiu sozinho em 10/10/2026, quando as OS da fixture (de 03 a 05/10) saíram dos 7 dias.
- Comparar com o `engenharia.json` do PCM (só para conferir, nunca como fonte): os níveis e as contagens dos 30 dias
  devem bater, salvo as OS canceladas e os ativos que o PCM casava errado pelo nome.
