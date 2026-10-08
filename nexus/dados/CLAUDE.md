# CLAUDE.md — camada de dados (governança: PRIORIDADE 0)

Levi, 05/10/2026: **"prioridade 0 para a governança e controle de dados"**; "precisamos construir e manter uma base
sólida para futuras análises correlacionadas" — e vão entrar dados de chamados, engenharia, mais PCM, segurança, mais
inversores. Esta pasta é o lugar onde esses dados viram uma base só, ligada por ID, no método **Kimball**:

- **Fato** = um acontecimento por linha (um fechamento, uma ronda, um chamado, a geração de um dia). Tem as medidas
  (nota, kWh, minutos) e os IDs de quando, onde, quem e em quê.
- **Dimensão** = o cadastro de referência, com ID numérico. **Uma só por assunto** (conformada): a mesma usina para todos
  os setores. É ela que deixa cruzar Campo × Performance × PCM × Chamados sem conversão.
- **Grão** = o que exatamente é UMA linha do fato. Sem ele escrito, dois relatórios contam coisas diferentes.
- **Tipo** = transação (1 linha por acontecimento, nunca muda), foto periódica (o estado no fim do dia/semana/mês),
  foto acumulada (a linha muda até fechar: a PT aguardando e depois decidida) ou sem medida (só registra que aconteceu).

**Leia esta página antes de mexer em qualquer dado que vá para o banco.** Fonte nova segue o passo a passo abaixo.

## O que existe (08/10/2026)

A auditoria Kimball de 08/10 achou ronda em 3 fatos com domínios diferentes, PT com o grão errado, histórico que só
achava versão para 1 de cada 4 fatos, nenhum fato com tipo nem medidas, nenhuma dimensão de equipamento, a programação
do PCM fora do banco e a geração em formato largo. Os passos 2 a 6 foram feitos em 08/10 (desenho:
`docs/superpowers/specs/2026-10-08-kimball-passos-2-a-6-design.md`); os passos 0 e 1 foram **adiados pelo Levi** (ver
"O que herda" e "Pendências"). Nada disso foi gravado daqui: entra no banco quando o código for ao servidor (a carga de
hora em hora do servidor passa a gravar o que está marcado "grava").

| Peça | Onde | Grava? | O que é |
|---|---|---|---|
| Catálogo (a matriz de barramento) | `catalogo.py` | — | 16 fatos ativos (3 com IDs, 3 montados) + os que viraram fonte de outro, 7 dimensões e os **9 livros do Nexus** (`LIVROS`, registrados antes de existir). Todo fato declara `tipo`, `chave`, `medidas` (`Medida`: coluna com a unidade, unidade, soma `aditiva`/`semi`/`nao`), `fontes` e `janela_origem`. **Fonte única** da tela, dos testes e desta página |
| Domínios | `dominios.py` | — | a lista fechada de cada atributo (vala 1 limpa, 2 parcial, 3 obstruída; sensor 1 sujo, 0 VERIFICADO limpo, vazio = não verificado; situação da OS da ronda; as 6 falhas; situação da PT). Valor fora = vazio + conta na qualidade. `MAPA_ANTIGO` traduz o que já está gravado |
| Calendário | `calendario.py` → `nexus_dimensoes · dim_data` | hora em hora | 1 linha por dia, 2025 a 2027: `data_id` (AAAAMMDD), semana ISO, mês, trimestre, fim de semana, feriado nacional, dia útil |
| Feriados locais | → `nexus_dimensoes · feriados_locais` | hora em hora | estaduais e municipais (UF, município), cruzam com a usina pela cidade |
| Histórico (SCD tipo 2) | `historico.py` → `pessoas_historico`, `usinas_historico`, `qualidade_historico` | hora em hora | **1 linha = 1 versão de 1 membro, troca no dia de Brasília.** Cabeçalho `<id>, <rastreados…>, versao, valido_de, valido_ate, valido_de_id, valido_ate_id, vigente, inicio_presumido`. A 1ª versão vale "desde sempre" (19000101) com `inicio_presumido = 1`. 1ª medida (08/10): fechamentos que acham exatamente 1 versão, pessoa 25,4% → 100%, usina 26,4% → 100%; checklist 6,2% → 100%. As 135 + 258 linhas gravadas migram sozinhas na 1ª carga com este código |
| Equipamento (dimensão) | `equipamento.py` → `nexus_equipamentos · dim_equipamento`, `equipamento_apelido` | hora em hora, **só quando o sha das linhas muda** e o PCM foi lido | **1 linha = 1 código de ativo do Fracttal** (canônico). `equipamento_id = int(sha1("fracttal:"+código)[:13 hex]) >> 3` (49 bits, no máximo 15 dígitos: com 52 bits 77% tinham 16 e o Excel trocava o último dígito; Levi, 08/10): o mesmo número em qualquer máquina, sem registro; 0 colisões nos 22.353 códigos das fotos. Apelidos: `Supervisório · tracker`, `Gêmeo · equipamento`, `BD_Thopen · coluna`, `BD_Performance · coluna`. 1ª medida (08/10, sem a foto no banco): 8.314 membros, 98,9% com `usina_id`, 4.619 apelidos (tracker 4.287, gêmeo 332; coluna 0 até o de-para das abas). Com as duas fotos locais (medido pelo construtor): 22.356 membros, 87,6% com usina, 6.118 apelidos |
| Foto dos ativos do Fracttal | `ferramentas/carregar_ativos_fracttal.py` → `nexus_ativos_fracttal · foto_ativos` | **carga única, quem grava é o Levi** | as fotos do OS Creator (22/09 + os 719 códigos que só a de 21/06 tem): 22.357 linhas. Renovar exige ler o Fracttal (fora do horário de campo) |
| Fechamento | `fatos.py` → `nexus_fatos · fato_fechamento` | hora em hora | 1 linha = 1 tarefa fechada pelo App. Foto acumulada (a revisão, aprovada/devolvida/nota corrigida, muda a linha depois: não é transação). 08/10: + `equipamento_id`/`equipamento_ligado_por`, + `tarefa_chave` (a mesma da programação), medidas com unidade (`nota_pts`, `fotos_qtd`, `pecas_qtd`, `xp_pts`; `vezes_programada_qtd`, que é o "Nº vezes programada" do PCM e conta a 1ª vez). Ensaio 08/10: 2.955 linhas, data 100%, usina 99,7%, equipe 97,7%, pessoa 94,4%, equipamento 99,7%, versão da época 100/100. Comparado valor a valor com o publicado às 12:40: 2.955 em comum, **0 diferenças** |
| Ronda (fato único) | `fato_ronda.py` → `nexus_fatos · fato_ronda` | hora em hora | **1 linha = 1 ronda realizada**: App com e sem OS (`rondas_app_campo`), checklist da carga única e avulsa válida. Foto acumulada (a situação da OS anda de "em verificação" para "criada"), `ronda_id = sha1("app\|"+Início)`. Ensaio 08/10: 874 linhas (749 com OS, 125 sem), data 100%, usina 99,8%, equipe 98,7%, pessoa 91,8% (689 pelo nome de UMA pessoa, 113 pelo checklist), equipamento 85,7% (749/749 com OS; sem OS não há ativo), checklist 125, 1 rótulo de falha fora do domínio |
| PT | `fato_pt.py` → `nexus_fatos · fato_pt` | hora em hora | **1 linha = 1 PT × ativo** (o App decide por linha). Foto acumulada. PTs = `SUM(primeira_linha_da_pt)`. Ensaio 08/10: 238 linhas = 232 PTs, data 100%, usina 99,2%, equipe 97,9%, solicitante 89,9%, decisor 0/201 (as 6 contas Admin estão fora do cadastro), equipamento 99,6%, paradas 132 |
| Qualidade da ligação | → `nexus_fatos · qualidade` | hora em hora | 1 linha por fato: quanto ligou a cada dimensão (1 casa decimal), `com_equipamento`, `pct_usina_versao`/`pct_pessoa_versao` (acham exatamente 1 versão) e `extra` (JSON com o que só aquele fato tem e `linhas_na_carga_anterior`) |
| Programação do PCM | `programacao.py` → `nexus_programacao · fato_programacao` | **montado, NÃO grava** (decisão 7) | **1 linha = 1 bloco de agenda** de uma tarefa planejada; as linhas `foraDoPlano` (execução, outro grão) ficam fora. Foto periódica semanal. Ensaio 08/10: 3.744 blocos = 3.705 tarefas (W38–W41), 2.174 `foraDoPlano` fora, usina 100%, equipe 98,7%, técnico 89,7%, equipamento 100%, 0 blocos repetidos; 0,55 MB |
| Geração em linhas | `geracao.py` (`carga.montar_geracao`) → `nexus_geracao · fato_geracao_usina_dia` | **montado, NÃO grava** (decisão 8) | **1 linha = 1 aba de usina × 1 dia** (dia futuro fora) + o inversor × dia (1 linha por célula com número, só em memória). Ensaio 08/10: 42.550 usina × dia (646 dias, 01/01/2025 a 08/10/2026), 701.936 inversor × dia, 3.499 linhas de dia futuro fora; `usina_id` 0% **de propósito** (o de-para das abas não está publicado; calculado sem publicar: 87,8%); 3,0 MB |
| Checklist da ronda sem OS (carga única) | `fatos.py` → `nexus_rondas_checklist · fato_checklist_ronda` | não (carga única de 06/10) | as respostas das 125 rondas sem OS (11/08 a 06/10). Desde 08/10 é **fonte** do `fato_ronda` |
| Ronda avulsa | `campo/ronda_avulsa.py` → `nexus_rondas_avulsas · fato_ronda_avulsa` | a cada lançamento | o Nexus é a FONTE (Levi, 07/10). Desde 08/10 é **fonte** do `fato_ronda` (só as válidas). 0 linhas no banco em 08/10 |
| Carga | `carga.py` (+ `ferramentas/carregar_dados.py`) | — | de hora em hora, aos :40. Ordem: dimensão de equipamento (antes dos fatos), histórico, fatos; cada peça nova isolada (regra 13). Montar levou 11–14 s em 08/10 (antes 3,6–4,5 s: o tempo novo é ler ~32 mil linhas a mais, sobretudo `campo_nexus` e `de_para_trackers`, e montar a dimensão, ~2,7 s) |
| Tela | `telas.py`, Base → **Governança de dados** | — | a matriz com tipo, chave e medidas; as barras de qualidade (inclusive equipamento e versão da época); a saúde do histórico; a dimensão de equipamento; os livros do Nexus |

**O Nexus como fonte (05/10/2026):** a decisão da PT assinada no Nexus (`nexus/campo/decisao_pt.py`) grava
`nexus_pt_decisoes · decisoes` (grão: 1 linha = 1 decisão). Já nasce com `data_id`, `usina_id` e a pessoa como HMAC;
o motivo vai mascarado (e-mail e número viram marcador), porque o técnico lê e a API é de leitura aberta. Ela grava
por número e pega a 1ª linha da PT: antes da 1ª gravação, levar o `codigo_ativo` e a aba `fato_decisao_pt` (decisão 4).

**Carga única do checklist das rondas sem OS (06/10/2026).** Levi: "Atualize o banco de dados com essas rondas passadas
sem OS, mas não será rotina". A ronda sem OS não tem o texto da OS no Fracttal; as respostas só existiam no registro da
ronda no App, exportadas UMA vez (pela conta do Levi; o Nexus não lê o Azure) e gravadas por
`ferramentas/carregar_checklist_rondas_sem_os.py` num livro próprio (o `nexus_fatos` é regravado a cada hora). Ronda
sem OS depois de 06/10 não entra ali.

## As regras (valem para todo dado novo)

1. **Grão e tipo escritos antes de tudo** ("1 linha = …"; transação, foto periódica, foto acumulada ou sem medida).
   Fonte larga (um inversor por coluna, como o BD_Thopen) vira linhas antes de entrar. Fonte que mistura grãos são
   dois fatos (o PCM põe execução `foraDoPlano` na semana do plano: ficou fora da programação).
2. **Dimensão é uma só.** Mestres: `cadastro_nexus` (usina, cliente, equipe, pessoa, e o `de_para` com o que cada
   sistema chama de cada usina), `nexus_dimensoes` (data e os históricos) e `nexus_equipamentos` (o equipamento e os
   apelidos de cada sistema). Cópia de cadastro em outro livro (o "Dados Gerais Usinas" do BD_Thopen, a usina do
   gêmeo, a aba de usinas dos tickets) não é fonte: aponta para o ID.
3. **O fato guarda IDs, medidas e chaves de negócio.** IDs: `data_id`, `usina_id`, `equipe_id`, `pessoa_id`,
   `equipamento_id`. Medidas numéricas com a unidade no nome (`_min`, `_kwh`, `_kwh_m2`, `_mm`, `_pct`, `_qtd`, `_pts`,
   `_nivel`) e declaradas no catálogo com a soma (a nota não soma; a irradiação soma no tempo de uma usina, não entre
   usinas). Indicador sim/não como 1/0. Número da OS fica no fato (dimensão degenerada). Texto que identifica uma
   coisa (a tarefa) entra como chave (`tarefa_chave`, sha1 do texto normalizado), nunca o texto.
4. **Não liga = vazio. Nunca chutar ID.** Código que é de duas usinas não liga (há código de usina que é de dois
   clientes). Nome que é de duas pessoas não liga. A lacuna aparece na qualidade e se conserta **no cadastro** (de-para, equipe que falta),
   nunca no fato. Valor fora do domínio (`dominios.py`) = vazio + conta.
5. **Linhagem:** o fato diz por onde ligou (`usina_ligada_por`, `equipamento_ligado_por`, `pessoa_ligada_por`). A
   qualidade diz quantos por cada caminho. Chave repetida (`GraoDuplicado`) não grava AQUELE fato: a aba dele fica como
   está no banco nesta hora (gravar o livro sem a aba a apagaria, troca integral) e a qualidade dele diz o erro
   (`extra.falhou_nesta_carga`). O resto da carga anda (regra 13).
6. **Histórico:** atributo que muda e muda a análise (equipe/supervisor da pessoa, responsável/equipe da usina) vai no
   `*_historico`. A versão "da época": `valido_de_id <= data_id < valido_ate_id` (vigente = 99991231; `da_epoca`). A
   troca vale no dia de Brasília do `alterado_em`; só `excluido = sim` fecha (ausência na leitura não); cadastro lido
   vazio não anda. Quem quer só o visto filtra `inicio_presumido = 0`.
7. **Data:** sempre o dia de Brasília (o App grava em UTC: 02:30Z é o dia anterior). Fato com mais de uma data usa
   "papéis": `data_id_criacao`, `data_id_decisao`, `data_id_semana`, `data_id_programada`.
8. **Segurança:** a API do banco tem LEITURA ABERTA. No fato: nada de nome, e-mail, telefone nem texto livre (a
   observação do App, o motivo da PT, a tarefa do PCM ficaram fora). Pessoa só como `pessoa_id`; vinda de fora, como
   HMAC do e-mail (`NEXUS_PESSOA_HMAC`). O nome em claro de uma fonte (as rondas, hoje) só serve para ligar, na memória.
   Sensível do cadastro, só cifrado (`sensivel_cifrado`).
9. **Conferir depois de gravar:** `livros.publicar` relê cada aba e compara a contagem; diferença é erro.
10. **Livro no banco é para sempre** (a API não apaga): nome `nexus_<assunto>`, abas `fato_<processo>`,
    `dim_<assunto>`, `<dimensão>_historico`, `qualidade`, `atualizacao`; exceção só com motivo em
    `catalogo.ABAS_FORA_DA_REGRA`. **Registre em `catalogo.LIVROS` antes de criar** (o teste cobra).
11. **Uma carga por hora, uma máquina por vez:** grava só se a última tiver mais de 50 min. PC e servidor podem estar no
    ar juntos sem gravar em dobro. `NEXUS_CARGA_DADOS=0` desliga numa máquina. Livro grande que muda pouco (a dimensão
    de equipamento) grava só quando o sha das linhas muda; tudo sai ORDENADO, senão o sha muda de máquina para máquina.
12. **A carga só lê o que as duas máquinas leem igual** (o banco e o `banco_dados.json` público do PCM). Arquivo local
    do PC (as fotos do OS Creator, o `os_falhas.json`, o `rondas_aprovadas.json`) nunca entra na carga de hora em hora:
    o fato trocaria de conteúdo conforme a máquina. Arquivo local entra por carga única, num livro próprio.
13. **Isolamento: peça nova não para a que funciona** (revisão de 08/10: a ronda com o mesmo Início duas vezes, ou um
    500 no `de_para_trackers`, parava o `fato_fechamento`). Fato novo que falha (grão, fonte fora do ar) fica como está
    no banco e a qualidade dele diz `falhou_nesta_carga` (só o TIPO do erro: a API é aberta; a mensagem completa vai ao
    log); a dimensão de equipamento que falha não grava e os fatos ligam pelo índice da dimensão GRAVADA; o histórico
    que falha segura o `nexus_dimensoes`; cada livro grava sozinho e o erro de um sobe no fim, depois dos outros
    (`rel["falhou"]`, `rel["erro_gravacao"]`). Só a fonte do fato que já existia (o fechamento) e o cadastro derrubam
    a carga inteira, como antes.

## Como entra um dado novo (o passo a passo do Claude)

1. **Entender o processo:** o que acontece, quem é o dono (a torre), de onde vem (App, Fracttal, planilha, API de
   fornecedor), com que frequência, quantas linhas por dia, **quanto a fonte guarda** (janela).
2. **Declarar o grão e o tipo.** Uma linha = um quê? Medir a chave na fonte (repetição = grão errado: a PT era
   "1 linha = 1 PT" e tinha 233 linhas para 227 números).
3. **Mapear cada dimensão** (data, usina, cliente, equipe, pessoa, equipamento, OS): o que a fonte traz, a chave de cada
   uma e por onde vai ligar. Sistema novo chamando usina de outro jeito = entra no `de_para` do cadastro (tela Base →
   Ligações), não num mapa escondido no código. Equipamento novo de outra fonte = apelido em `equipamento_apelido`.
4. **Registrar no `catalogo.py`** (`Fato`, estado `origem`, com `tipo`, `chave`, `medidas`, `fontes`,
   `janela_origem`) e, se for livro novo, em `LIVROS`. A tela já passa a mostrar a lacuna.
5. **Pessoa?** Confirmar que nada pessoal vai em claro (regra 8).
6. **Construir o fato conformado** num módulo puro (`fato_<processo>.py`, com `CAB_`, `TIPO`, `GRAO`, `CHAVE`,
   `FONTES`, `MEDIDAS`, a linha de qualidade e `conferir_grao`) e ligar em `carga.montar` (estado `montado` enquanto a
   gravação espera decisão; `conformado` quando grava).
7. **Testes** (`tests/test_dados_camada.py` para catálogo e carga; um `tests/test_dados_<processo>.py` por fato): a
   ligação (inclusive o "não chuta"), o grão, o domínio, nenhum nome no fato, a qualidade e a carga com o
   `tests/pg_falso.py` (inclusive `como_texto=True`: a API pode devolver tudo como texto).
8. **Medir com o dado real ANTES de gravar:** `python ferramentas/carregar_dados.py --ensaio` (linhas, chave repetida,
   % de cada ID, tamanho do xlsx). Abaixo de 98% em data ou usina: achar o porquê e consertar no cadastro antes.
9. **Gravar e conferir:** `python ferramentas/carregar_dados.py --forcar`; a tela mostra as barras.
10. **Atualizar** o catálogo (estado `conformado`, `conformado_em`) e esta página (o que existe, a 1ª medida).

### O que olhar em cada frente que vem

- **Chamados** (tickets de performance, solicitações do Fracttal): 1 linha = 1 chamado, foto acumulada. Duas datas
  (`data_id_abertura`, `data_id_fim`). Usina pelo "Código da usina" (o de-para "Tickets · Base de dados - Usinas" já
  existe). Supervisor e responsável vêm em NOME: ligar ao `pessoa_id` só nome de UMA pessoa. O ID falta em 57 de 774
  tickets: a chave é o 1º problema. Equipamento em texto: vira apelido na dimensão de equipamento.
- **Engenharia** (garantias, laudos, projetos): o centro é o EQUIPAMENTO, e a dimensão existe (`nexus_equipamentos`).
  O `os_falhas.json` (2.337 códigos) já está 99,7% nela: o fato de falha liga pelo código do ativo.
- **Mais PCM**: a programação está montada (`programacao.py`); backlog (`pendentes`) e execução (`foraDoPlano`) são
  outros fatos (outro grão). O técnico do Fracttal vem em nome: o ID de pessoa do Fracttal no cadastro resolveria.
- **Segurança** (PT, APR, incidentes, EPI): a PT está conformada (`fato_pt`). Incidente: 1 linha = 1 ocorrência;
  pessoas envolvidas só por ID; tipo e gravidade como lista pequena em `dominios.py`.
- **Mais inversores e fontes de equipamento:** cada fonte registra o código que ela usa para cada equipamento como
  apelido (`equipamento_apelido`: sistema, chave externa, `casou_por`). Série de 5 min ou de hora fica na fonte ou no
  gêmeo; no banco do Nexus entra o agregado diário (inversor × dia), com `equipamento_id`.

## O que herda dos passos 0 e 1 (adiados pelo Levi em 08/10/2026)

Passo 0 = carga incremental que nunca encolhe o fato. Passo 1 = um dono só do cadastro, desligar a carga do PC, reler o
cadastro, recusar carga encolhida. **Nada disto está feito**; onde cada peça herda o risco:

- **Tudo é troca integral** (`sync-xlsx?replace=true`) refeita da origem a cada hora. Os livros do App guardam 90 dias:
  a ronda de 11/08 sai do `fato_ronda` em ~**09/11/2026**, a PT de 28/09 sai do `fato_pt` em ~**27/12/2026**, o
  fechamento sai com 90 dias. Checklist (carga única) e avulsa (o Nexus é a fonte) não se perdem.
- **Origem lida vazia ou menor encolhe o fato e é gravada** (o `livros.ler` devolve [] para livro que sumiu): o
  `rondas_app_campo` lido vazio deixaria o `fato_ronda` só com as 125 do checklist. A carga só MOSTRA
  (`rel["encolheram"]`, `extra.linhas_na_carga_anterior`); recusar é o passo 1.
- **Histórico:** refeito de si mesmo e regravado inteiro. Leitura PARCIAL que volte com 200 não é pega: o membro cujas
  linhas faltaram renasce em 1900 e perde as versões fechadas. Com dois donos do cadastro, publicação antiga vira
  mudança real (as regras 3 e 4 do `historico.py` amortecem, não impedem). Aba lida vazia com o livro gravado: o
  `nexus_dimensoes` não é gravado na hora (`segurar_dimensoes`) até alguém agir.
- **Equipamento:** a dimensão é refeita inteira; membro que só existe numa fonte de janela curta (App 90 dias, PCM 4
  semanas) some e volta com o mesmo ID. Com a foto gravada, uma foto lida vazia encolhe a dimensão de ~22 mil para ~8
  mil e grava (o sha muda). Única guarda própria: PCM não lido = a dimensão não é gravada naquela hora.
- **Programação:** a fonte guarda 4 semanas; com troca integral o fato nunca passaria disso. Por isso NÃO grava sem a
  decisão 7 (passo 0, ou `programacao.mesclar_semanas`, que existe e tem teste mas não está ligada).
- **Geração:** a fonte guarda tudo, mas aba regravada menor encolhe o fato (`geracao.encolhidas` só mostra). O inversor
  × dia (~29–36 MB/dia de xlsx) não cabe em troca integral. Uma publicação antiga do de-para tiraria os sistemas de
  aba e zeraria o `usina_id`.

## Pendências, em ordem

0. **Passo 0** (carga incremental, nunca encolhe) — **adiado pelo Levi em 08/10**.
1. **Passo 1** (um dono só do cadastro, desligar a carga do PC, reler o cadastro, recusar carga encolhida) —
   **adiado pelo Levi em 08/10**.
2. **Passo 2 — técnico das rondas em HMAC:** o pacote do App está pronto (`C:\GridcoBuild\app-campo-docs\_propostas\
   rondas-tecnico-hmac\LEIA.md`: 'Técnico' vira 'Técnico (HMAC)', e o erro da 'Situação da OS' deixa de citar o nome).
   O `fato_ronda` já lê o HMAC primeiro. **Falta o lado do Nexus, que vai ao servidor ANTES do App:**
   `campo/visao._rondas_ligadas`, `campo/livros_app.ronda` e `campo/fonte_pg._do_app("rondas")` aceitarem a coluna
   nova, e o cadastro receber as 4 pessoas de ronda sem ficha. Depois: o pedido à T.I. para apagar o histórico por
   linha da aba 446.
3. **Passo 3 — feito** (`fato_ronda`, `fato_pt`, `dominios.py`). Decisões do Levi que faltam: (1) checklist das rondas
   com OS (o App mandar as respostas, recomendado, e/ou carga única das 602 do arquivo local: hoje 125/874 têm
   checklist); (2) chave durável de quem só vem por nome (`fato_ronda.codigo_do_nome`, pronto e desligado); (3) a
   avulsa antes da 1ª gravação (vala sem "Suja", sensor em 3 estados, anulação sem `data_id`/`usina_id`); (4) a
   decisão da PT do Nexus por ativo ou pela PT inteira, e quem são as 6 contas Admin (decisor 0%).
4. **Passo 5 — feito** (SCD2). Falta: decisão 5 (aceitar o início presumido), HIST-4 (o fato é rechaveado pelo cadastro
   atual) e HIST-6 (tipo 2 para capacidade, mantenedor e eletricista).
5. **Passo 6a — feito** (dimensão de equipamento). Falta: o Levi gravar a foto (`python
   ferramentas/carregar_ativos_fracttal.py "<deploy-os-creator-web>\os_creator\assets_cache.json"
   "<oem>\os_creator\assets_cache.json" --gravar`); renovar a foto (ler o Fracttal, fora do horário de campo); decidir
   13 × 12 hex (77,4% dos IDs têm 16 dígitos e o Excel mostra o último errado; é a hora barata: livro e ID no banco são
   para sempre); no cadastro, 15 códigos de usina fora (1.908 membros) e 1 código de usina de dois clientes (170).
6. **Passo 6b — montado** (programação). Falta: decisão 7 (gravar com o passo 0 ou com a mescla por semana); carga única
   W22–W37 do git público do PCM; no cadastro, 1 cluster (50 linhas) e 15 técnicos sem ficha (382 linhas).
7. **Passo 6c — montado** (geração). Falta a decisão 8: publicar o de-para com `BD_Thopen · aba` e `BD_Performance ·
   aba` (tela Ligações), conferir as 5 abas cópia, as 2 abas de 2 usinas, a sem par e a ligada por "nome sem número";
   o teto de kWh/dia; o IPOA do BD_Performance (DEF); onde vai o inversor × dia (passo 0 ou livros mensais
   `nexus_geracao_inversor_AAAA_MM`); ligar o laço diário (~01:40).
8. **Lacunas do cadastro** (05/10, ainda abertas): 1 equipe da região do App fora do cadastro; 1 usina do Fracttal e
   o ativo "Grid Co." sem de-para.
9. **Fatos ainda de origem:** decisão do painel (dividir os 3 eventos), zeladoria, tickets, falhas de string e de
   tracker, parada de tracker, perda por equipamento (o gêmeo ainda tem usina própria), meta mensal.

## Como provar

- `python -m pytest -q tests/test_dados_camada.py tests/test_dados_historico.py tests/test_dados_ronda_pt.py
  tests/test_dados_equipamento.py tests/test_dados_programacao.py tests/test_dados_geracao.py` (catálogo com tipo,
  chave, medidas e livros; a carga que grava só os livros registrados, a dimensão só quando muda, segura o histórico,
  não grava com chave repetida e mostra o que encolheu; cada fato com as regras dele).
- `python ferramentas/carregar_dados.py --ensaio` mede com o dado real sem gravar (o que grava e o que só é montado:
  linhas, chave repetida, % de cada ID, xlsx). `--sem-geracao` pula a leitura das 171 abas de geração (~30–60 s).
- `python ferramentas/carregar_geracao.py --ensaio [--de-para-local] [--xlsx PASTA]` e
  `python ferramentas/carregar_ativos_fracttal.py <fotos>` (sem `--gravar`) medem a geração e a foto.
- Base → Governança de dados: as barras da última carga e a hora dela.
