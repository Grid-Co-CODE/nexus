# CLAUDE.md — torre COS

A torre do Centro de Operações: a mesa do operador, o ciclo da ocorrência e a comunicação com o cliente. É a pasta
do programador do tempo real/COS. Leia também o `CLAUDE.md` da raiz (convenções e regras da casa).

## O que a torre vai ser

As telas estão declaradas em `__init__.py`. Ronda padronizada, Parede de eventos, Ocorrências, Religamentos e
Acionamentos já leem o Andamento da Ronda COS, a Passagem de turno grava no banco do Nexus e OS em aberto é o Panorama da
Ronda COS (seções abaixo); as outras são placeholder (cada uma diz a pergunta que vai responder e a fonte prevista). A base de produto são as specs do Fillipe, no SharePoint `Gridco/4. O&M/6.Gerencial/10. Nexus`:

- **R04, COS como visão global:**
  - **Mesas:** cada operador tem uma carteira de clientes, e o líder enxerga todas.
  - **Ciclo da ocorrência em cinco etapas:** detectada → cliente informado (até 15 min) → campo acionado (até
    30 min) → normalizada → encerrada.
  - **Ronda padronizada:** nove verificações, às 08h, 12h e 16h, e de noite às 20h, 00h e 04h.
  - **Desempenho por mesa:** MTTA, informado no prazo e religamento remoto.
- **R05, régua de devolutivas:** o aviso ao cliente sai sozinho no prazo, conforme a severidade. O operador pode
  segurar ou antecipar.
- **R12, passagem de turno:** a passagem é registrada no sistema; sem registro, ela não aconteceu.
- **R13, perfil de comunicação por cliente:** o que o cliente quer receber, quando e por onde, mais as regras dele
  (religamento suspenso, contato único). O mockup `Nexus_Mockup_GridCo_R13.html` mostra as telas.

**Acompanhamento COS** (09/10/2026, porta única; não é para construir aqui): é a tela `/cos` da Plataforma de Performance (MTTA das OS), aberta numa moldura do Nexus. O `__init__.py` só declara a `Tela("acompanhamento")` e chama `registrar_molduras(bp, TORRE)`; a regra mora fora da área do COS (`nexus/torres/moldura.py` e `nexus/performance/porta.py`). Não renomeie o id: ele é o mesmo na plataforma.

## Como construir uma tela

Crie uma view no `bp` desta torre **com a mesma rota da tela**. Ela vence o placeholder sozinha:

```python
from flask import render_template

@bp.route("/mesa")
def mesa():
    return render_template("cos/mesa.html", torre=TORRE, tela=TORRE.tela("mesa"))
```

- O template vai em `templates/cos/<tela>.html` e estende `base.html`. Login, menu (pelo setor) e tema vêm prontos.
- Tela nova: acrescente um `Tela(...)` em `TORRE.telas`. O id publicado não muda depois, porque vira endereço.
- **A regra fica fora daqui**: leitura de dado, cálculo do ciclo e prazos vão num módulo sem Flask (por exemplo,
  `nexus/cos/`), testável sem subir o servidor. É o padrão de `nexus/cadastro/` e `nexus/pcm/`. Esta pasta fica com
  as rotas e os templates.

## Como entregar (trava da área do COS, desde 05/10/2026)

Quem programa o COS tem escrita no repositório, mas a `main` só aceita o trabalho dele por **pull request**:

1. Crie um ramo (`cos/<assunto>`), commite e faça push dele.
2. Abra o pull request para a `main`. A conferência **pasta-da-area** (`.github/workflows/pasta-da-area.yml`, a do COS
   até 27/10/2026, quando ganhou a Engenharia) aprova se o pedido mexe só na área do COS e reprova, listando os
   arquivos, se mexe fora dela. Quem é do COS: a variável `LOGINS_COS` do repositório. O programador do COS é admin
   no GitHub por decisão do Levi (27/10/2026), e o admin passa por cima da regra da `main`: para ele a conferência só
   avisa.
3. Verde: pode juntar (merge). O servidor recebe na próxima atualização (`git pull`, ver `DEPLOY.md`).

**Área do COS:** `nexus/torres/cos/`, `nexus/cos/`, `nexus/static/cos.css` (ou `nexus/static/cos/`), `tests/cos/` e
`tests/test_cos*.py`. Precisou mexer fora (menu, casca, cadastro, `requirements.txt`)? Abra o pedido assim mesmo e
peça ao Levi: ele revisa e junta.

## Ronda padronizada e Parede de eventos: o Andamento da Ronda COS (22/10/2026)

As duas telas leem o **Andamento**, o sistema da Ronda COS que tira a fotografia da operação de hora em hora, manda o
flash de desligou e religou ao cliente e guarda os eventos das ocorrências. Decisão do dono: *"o ANDAMENTO e o RONDA COS
vão ser somente base de dados pra esse NEXUS"*. O Nexus **só lê e mostra**: o que é ocorrência, o problema, a cor da
usina e o que entra nos eventos (só o que já tem OS) são regra do Andamento, e reescrevê-las aqui daria duas respostas.

- **De onde:** `GET <Andamento>/api/nexus/<cliente>` e `GET <Andamento>/api/nexus/clientes`, com a chave de máquina
  no cabeçalho `X-Nexus-Chave`. O contrato é versionado (`versao: 1`): outro número é recusado com aviso na tela, em vez
  de mostrar campo errado. Sem nome de pessoa na resposta.
- **Configuração** (opcional; sem ela as telas dizem que a fonte não está ligada): `NEXUS_COS_ANDAMENTO_URL` (a porta
  3002 do servidor da Ronda COS) e `NEXUS_COS_ANDAMENTO_CHAVE` (a mesma do `ANDAMENTO_NEXUS_CHAVE` de lá; quem a tem é o
  dono da Ronda COS, e ela nunca vai a commit nem a mensagem). **O caminho é a tela Base → Chaves do Nexus** (desde
  22/10/2026): um administrador cola os dois, sem T.I. e sem reiniciar; o endereço é conferido falando com ele e a chave
  pedindo a lista de clientes com ela (`conferir_para_a_tela`). O `.env` e o ambiente continuam valendo, abaixo da tela.
  Se quiser fixar a ordem dos clientes, `NEXUS_COS_ANDAMENTO_CLIENTES` (senão a lista vem do Andamento).
- **A leitura** (`nexus/cos/andamento.py`): 5 s de teto, 30 s de cópia em memória por cliente, e na falha a última
  leitura boa continua na tela, dita velha. Nos testes, sem a chave na config do app, não se vai à rede.
- **A fotografia dos clientes vai ao WhatsApp pelo Andamento**, não pelo Nexus. A tela mostra o estado de cada envio
  (enviada, retida até zerar as pendências, sem grupo, falhou).
- ⚠ **A "Ronda padronizada" da spec R04 (nove verificações às 08h, 12h, 16h, 20h, 00h e 04h) ainda não tem de onde
  ler.** A pergunta da tela foi trocada pelo que ela responde hoje (a fotografia da hora e o que está aberto); as nove
  verificações são decisão de produto em aberto.
- ⚠ **O Andamento fala http**, sem TLS: a chave atravessa a internet em claro até haver HTTPS (ou rede privada) lá. Ela
  só abre leitura.

## Ocorrências: o ciclo de cada ocorrência no prazo da R04 (22/10/2026)

*"Cada ocorrência cumpriu as cinco etapas no prazo?"* — detectada → cliente informado (15 min) → campo acionado (30 min)
→ normalizada → encerrada. Só lê: agir na ocorrência é na Ronda COS, pelo link de cada linha.

- **De onde:** `GET <Andamento>/api/nexus/<cliente>/ocorrencias?dias=N` (1, 7 ou 30 na tela; contrato próprio,
  `versao: 1`), lido em `andamento.ler_ocorrencias` com 60 s de cópia. O Andamento diz QUANDO cada etapa aconteceu e por
  qual caminho (sem nome de pessoa); **o prazo e o veredito são daqui** (`nexus/cos/ocorrencias.py`), porque a spec mora
  no Nexus. Os prazos são dado (`PRAZOS`, com o porquê) e a origem do relógio também (`CONTA_DE`).
- **O que o Andamento já separou e a tela não junta de volta:** "cliente informado" é o primeiro flash ou fotografia que
  nomeou a ocorrência ao grupo do CLIENTE (a cópia do COS não conta, e a ocorrência sem OS não é nomeada); antes de o
  Andamento mandar a um cliente, isso não se mede. "Campo acionado" é a primeira passagem a "Técnico acionado" feita por
  pessoa ou pela OS aberta com religamento local. A passagem automática da Ronda COS (quando a tratativa remota passa do
  tempo) não é ninguém acionando o campo: aparece como **só automático**, em âmbar, e fica fora da conta. Medido em
  22/10/2026: 80 de 195 entradas em "Técnico acionado" em 7 dias foram esse escalonamento.
- **Decisões tomadas na construção, para o dono revisar** (cada uma é uma linha em `ocorrencias.py`):
  1. os prazos contam do **início da falha** (`CONTA_DE = "inicio"`), o mesmo relógio do escalonamento a campo e do MTTA
     da Ronda COS. A outra leitura é a hora em que a Ronda COS registrou a ocorrência — mediana de 24 min depois do início
     na Thopen, e é essa demora que empurra o flash para depois dos 15 min;
  2. no **religamento remoto** o cliente sabe pelo aviso da volta (decisão de 21/10/2026: "pode ser só a normalização"):
     quando a volta foi avisada antes da ocorrência, é essa a hora de "cliente informado";
  3. normalizada **sem ir a campo**: dentro dos 30 min, "não precisou"; depois, "sem campo", em âmbar, fora da conta;
  4. o prazo se compara em **minutos inteiros** (o início é digitado em minutos; "em 30 min (prazo 30 min)" lido como fora
     por causa de segundos seria a tela se contradizendo);
  5. o link "abrir na Ronda COS" sai do endereço do Andamento, na porta 3000 (`PORTA_DA_PLATAFORMA`), como o painel do
     próprio Andamento faz; o endereço não entra no repositório.
- A tela vem **depois do Acompanhamento** no menu, como a Ronda e a Parede: o cartão do COS na página inicial leva à
  primeira tela pronta, e ela continua sendo o Acompanhamento.
- Testes: `tests/test_cos_ocorrencias.py`, com controle positivo (o escalonamento contado, "só automático" e "não
  precisou" contados como cumpridos, a régua de "antes do envio" desligada e a porta do link trocada: vermelhos).

## Religamentos: onde o remoto resolve e onde se repete (26/10/2026)

*"Onde o religamento remoto resolve e onde se repete na mesma cabine?"* Lê a rota das Ocorrências (30 dias por padrão;
7 no filtro), com quatro campos que o Andamento passou a mandar para esta tela, sem mudar a versão do contrato:
`ativos` (as tags, na ordem de `equipamentos`), `tipo_falha_codigo`, `protecoes` e `religamento` (`remoto`, `local`).
O desfecho e a repetição são daqui (`nexus/cos/religamentos.py`).

- **O desfecho:** com remoto, **resolveu** (fechou sem ir a campo), **foi a campo depois** (veio a OS com religamento
  local ou o campo foi acionado por pessoa) ou **ainda aberta**; só com local, **só local**. A passagem automática a
  "Técnico acionado" não é ida a campo (a mesma regra das Ocorrências). O "Persistiu"/"Parcial" do religamento remoto
  fica só no checklist da OS na Ronda COS: a tela não o inventa.
- **A repetição** é pela tag do equipamento (a ocorrência de vários conta em cada um; sem equipamento, a usina inteira):
  repete com `REPETE_A_PARTIR` (2) e fica vermelho com `REINCIDENTE_A_PARTIR` (3), a régua de reincidência do RDO.
- **Andamento antigo** (sem os campos novos): conta o remoto que normalizou pela plataforma e a OS com religamento local,
  agrupa pelo nome, e a tela diz que está incompleta.
- Testes: `tests/test_cos_religamentos.py` (controle positivo: contando o escalonamento automático como campo, vermelho).

## Acionamentos e distribuidoras: quem aciono e o canal da distribuidora (26/10/2026)

*"Quem aciono e qual o canal da distribuidora desta UF?"* Duas metades, duas fontes (`nexus/cos/acionamentos.py`):

- **Quem aciono** é do cadastro do Nexus: o Supervisor de Campo da região da usina (ou "vaga"), o Responsável O&M e o
  técnico, o eletricista e o mantenedor da usina, com o contato que o cadastro guarda cifrado (o da ficha da usina, ou o
  corporativo da pessoa, ou o pessoal). Decifrado só para a tela, com link `tel:`; nada disso é gravado nem vai ao
  Andamento. Sem `NEXUS_CHAVE_CADASTRO`, a tela diz e não mostra contato.
- **A distribuidora** é do Andamento: `GET <Andamento>/api/nexus/<cliente>/distribuidoras` (`ler_distribuidoras`,
  `versao: 1`, 60 s de cópia): a UC de cada usina (a planilha do cliente que a Ronda COS usa para abrir o chamado; sem
  titular nem CNPJ), o canal de cada concessionária (o SMS de registro com o formato e a confiança, e o canal para abrir
  à mão, que a Ronda COS declara em código) e os chamados de 30 dias com o protocolo (o "por" só como sistema ou pessoa).
  Usina sem UC lá usa a concessionária do cadastro, casada ao canal pela mesma chave da Ronda COS
  (`chave_da_concessionaria`); nome que não casa fica "canal não levantado", sem chute.
- **A ligação** da usina do Andamento ao cadastro é pelo código (o `Ligador` dos fatos). A que tem UC lá e não liga aqui
  é listada no pé da tela, para o conserto no cadastro (Base → Ligações).
- **Número pela metade não vai à faixa:** sem a leitura do Andamento de todos os clientes, "com canal", "chamados" e
  "pedem ação" saem como "—". O Andamento de antes da rota responde 404, e a tela diz por cliente.
- Testes: `tests/test_cos_acionamentos.py` (controle positivo: sem o telefone pessoal como reserva, vermelho).

## Passagem de turno: a R12 no banco do Nexus (26/10/2026)

*"O que o próximo turno precisa saber e quem assumiu?"* — R12: a passagem é registrada no sistema; sem registro, ela não
aconteceu. Nada disso existia: a Ronda COS só sabe os turnos e deduz o plantonista pelas ações nas ocorrências. **O Nexus
é a fonte**: livro `nexus_cos_turno` · `fato_passagem_turno` (`nexus/cos/turno.py`, no catálogo antes da 1ª gravação),
1 linha = 1 evento (`passagem` ou `assumiu`) sobre 1 troca, só acrescenta. Quem e o texto vão cifrados (o Cofre, como o
acompanhamento das Contestações); a pessoa liga pelo `pessoa_hmac`. Por mexer em `nexus/dados/` (catálogo e
`explica.py`), o pedido sai da área do COS e precisa da revisão do Levi.

- **Os turnos** são os da Ronda COS (`TURNOS`: dia das 06:00, noite das 18:00; `turnoInicio` de lá). Mudou lá, muda aqui.
- **A troca de cada passagem** (`destino`): a do fim do turno em curso, ou a que acabou de acontecer se escrita até
  `TOLERANCIA_MIN` (60 min) depois dela, com o atraso dito na tela. Quem já assumiu essa troca está no turno novo e
  escreve para a seguinte. Mais de um operador escreve na mesma troca (cada um a sua carteira).
- **Assumir:** só a troca que começou o turno em curso (ou a seguinte, a menos de 60 min), só com passagem e nunca a
  própria passagem. A senha de administrador lê e não grava (não diz quem é a pessoa).
- **A situação de cada troca:** sem passagem 60 min depois da hora, **sem registro** (vermelho: não aconteceu); com
  passagem e ninguém assumindo, **ninguém assumiu** (âmbar). A faixa conta só as trocas que já fecharam, em 7 dias.
- **O que estava aberto** na hora da passagem (`abertas_qtd`, `criticas_qtd`) é a soma do Andamento entre os clientes;
  com um cliente sem leitura, vai vazio (número pela metade não se grava). Sem o Andamento ligado, a passagem vai sem ele.
- Testes: `tests/test_cos_turno.py` (o relógio, a situação, a gravação cifrada, as recusas e a tela), com controle
  positivo (sem a trava da própria passagem ou sem o "sem registro", vermelhos).

## OS em aberto: o Panorama da Ronda COS (27/10/2026)

*"Que OS o COS abriu e seguem abertas no Fracttal, e há quanto tempo?"* — a tela "OS em aberto" da Ronda COS (o Panorama),
no Nexus, logo depois da Passagem de turno (pedido do dono). Só lê.

- **De onde:** `GET <Andamento>/api/nexus/os-abertas` (`ler_os_abertas`, `versao: 1`, 60 s de cópia), um retrato de TODOS
  os clientes numa resposta (a varredura da Ronda COS lê o Fracttal inteiro de 30 em 30 min). O Andamento de antes da rota
  responde 404, e a tela diz que ele ainda não a tem.
- **O que entra é regra de lá**, e o Nexus não refaz: só corretiva emergencial, religamento e religamento remoto (o que o
  COS abre); fora a classificação programada (a vazia fica), a usina de teste e o assunto encerrado (normalizada na Ronda
  COS **e** 100% no Fracttal; a normalizada abaixo de 100% fica). A situação (`pendente` ou `concluida` = feita, falta
  finalizar) e o alerta (pendente há mais de 1 h sem reconhecimento) também vêm prontos. A tela diz quantas cada corte tirou.
- **Daqui** (`nexus/cos/os_abertas.py`): os filtros (situação, com a pendente no padrão; cliente, tipo, idade, só sem
  registro, busca pelo nº, usina ou ativo), a idade na hora em que a tela abre (em horas até 48 h, como o Panorama conta)
  e as contas. As pílulas de cliente, tipo e idade contam sobre a situação, ANTES dos outros filtros; o alerta é do painel
  inteiro. A varredura parada há mais de 90 min (três passagens) acende o aviso: uma OS fechada pode seguir na lista.
- **Sem nome de pessoa e sem texto livre:** quem abriu, o responsável, a descrição, a nota e quem reconheceu ficam na
  Ronda COS. O detalhe abre no **card da OS** do OS Creator (`oscreator/card_os_abrir.html`, com o login do Fracttal de
  quem clica); reconhecer o alerta é na Ronda COS.
- Testes: `tests/test_cos_os_abertas.py` (controle positivo: a pílula contando depois do filtro, o padrão em "todas", o
  alerta pela situação e o 404 sem a frase própria, vermelhos).

## Normalizações: a hora da volta pela Ronda COS (27/10/2026)

*"Quando cada usina voltou, e a OS dela já fechou no Fracttal?"* — Levi: "Gostaria de inserir no COS" a API de
normalizações da Ronda COS (o guia `API-NORMALIZACOES.md`, do dono da Ronda COS). Por que importa: o Fracttal só encerra a
OS quando o técnico fecha, muitas vezes dias depois da volta; na semana até 27/10/2026, 208 de 341 normalizações tinham a
OS aberta no Fracttal (a OS 16702, de Mandaguaçu, normalizada em 19/10 às 05:53, seguia "em processo" oito dias depois).
Só lê; nada vai ao banco (decisão do Levi, 27/10/2026: a tela, sem guardar).

- **De onde:** `GET <Andamento>/api/normalizacoes?desde=&limite=` (contrato `versao: 1`, a mesma chave `X-Nexus-Chave`). A
  API é **incremental**: devolve `cursor` e `mais`. O Nexus guarda em memória (`nexus/cos/normalizacoes.py`) desde o
  1º dia do mês mais antigo da tela (em 27/10: desde 01/08), **por `registro`** (o mesmo registro volta com o estado novo e SUBSTITUI: o cursor fica 2 min atrás do
  relógio de propósito), e pergunta pelo cursor a cada minuto. A 1ª carga vem em páginas de 500 com 15 s de teto (lá,
  360 itens levam ~2,4 s); no máximo 4 páginas por pedido da tela, e o resto no pedido seguinte, com o aviso "carregando".
  Falhou: a memória continua, dita velha, e a próxima tentativa espera 1 minuto. O processo reiniciado (deploy) carrega
  de novo. 404 = o Andamento sem a rota.
- **O que é regra de lá:** o que é normalização, a hora da volta (`normalizado_em`, já a corrigida), `fora_min`,
  `hora_real` e a OS aberta no Fracttal (a varredura de 30 em 30 min de lá; `varrida_em`). **Daqui:** **o mês** pela hora
  da volta (o corrente no padrão e os 2 anteriores, `MESES`; os 1, 7 e 30 dias saíram no mesmo dia: "Pode tirar esses
  filtros de 7, 30 dias ou último dia"), os filtros, a faixa e "há quantos dias da volta a OS segue aberta" (7 dias ou
  mais em vermelho).
- **A tela, como o Levi pediu (27 e 28/10/2026, da 2ª à 4ª rodada):** as colunas OS, **Indisp.** (do início da falha
  até a normalização, em minutos e horas, nunca em dias: "Conta em minutos e horas"; "sem hora real" quando a volta não
  tem hora), Início, Normalização (com por onde foi registrada), Cliente, Usina (com a falha e os equipamentos embaixo),
  **Operador**, **Técnico** e No Fracttal, nessa ordem; sem a severidade (só no CSV). Filtros: cliente, usina (as do
  cliente escolhido), criado por (o operador), técnico, status no Fracttal (em processo, em verificação, fechada) e um
  texto livre (OS, usina, falha, equipamento, operador, técnico, informe). O "Como se conta" é a exclamação amarela ao
  lado do título, a macro `aviso` de `hseq/_legenda.html` (a mesma dos Extintores). As letras são 20% menores
  (`zoom:.8` no `.cos-norm`, "diminua o tamanho de todas as fontes em 20%"). **Exportar CSV** = `?formato=csv` com os
  filtros da tela (`;`, com BOM para o Excel; o texto que começa com `=`, `+`, `-` ou `@` vai com apóstrofo, para o
  Excel não o executar).
- **Operador e Técnico vêm da API** (desde 28/10/2026, `os_aberta_por` e `tecnico`; Levi: "boa, inclui lá"). Operador =
  quem abriu a OS, o operador de plantão (pela Ronda COS ou direto no Fracttal), em branco quando a OS já existia e só
  foi ligada; Técnico = o responsável atribuído no Fracttal, quem RECEBEU a OS (não prova quem foi ao local). São os
  únicos nomes de pessoa da API: só na tela e no CSV, o Nexus não os guarda (a memória é a do processo). **Nunca ler o
  Fracttal OS a OS para isso:** a 2ª rodada (27/10, `a37eeb7`) lia o `created_by` do REST, 30 OS por minuto, e saiu na 3ª
  ("Não precisa trazer o operador se for ficar puxando um a um no fractal, isso vai pesar muito nas requisições!"). As
  normalizações lidas antes de 28/10 não voltam sozinhas com os dois campos (a linha só volta quando muda): o Nexus relê
  desde o 1º dia do mês mais antigo a cada reinício, então o deploy os preenche. O "registrada pelo COS" embaixo da
  Normalização é o `declarada_por: pessoa` (até 27/10 dizia "Operador" ali, e confundia).
- **Proteções, Geração parou e Conferência da OS** (29/10/2026, Levi: "quero proteções, geração_parou e conferência da OS
  na tabela, quero que seja exportável também"), campos que a API passou a mandar em 29/10: `protecoes` (como o time
  escreve), `geracao_parou` (só na falha de comunicação, desde 28/10: Sim vermelho, Não verde) e `conferencia_da_os` (a
  Ronda COS relê a OS no Fracttal de 10 em 10 min: Aguardando técnico, Hora a corrigir (com os minutos da conclusão),
  Hora confere (falta finalizar), Finalizada, Travada, Ainda não lida; "—" = a OS não foi criada pela Ronda COS).
  Colunas depois da Usina (as duas primeiras) e no fim (a conferência); no CSV, todas as partes da conferência (tarefas,
  Data do Evento e conclusão no Fracttal, as duas diferenças em minutos, finalizada e lida em). Sem filtro novo (não foi
  pedido). Com 12 colunas, cada célula tem 7 px de folga dos lados e a Usina 150 px de mínimo: cabe em 1366 px.
  `impacto` e `detalhes` (texto livre do time, com nome e telefone às vezes) NÃO entraram; se entrarem, só na tela e no
  CSV, e nunca texto real em teste (o guia da API, seção 2.3).
- **As contas:** as opções dos filtros contam o mês, antes dos filtros; a faixa conta a lista filtrada SEM o status
  (senão a fatia aberta seria sempre 100%). A desfeita (`normalizada: false`) sai da lista e é dita à parte; a sem hora
  real fica na lista, marcada, e fora da mediana.
- **A chave e o endereço** só na tela Base → Chaves (o repositório é público).
- Testes: `tests/test_cos_normalizacoes.py` (o upsert pelo registro, a paginação que continua, a pausa de 1 min depois
  da falha e a desfeita fora: mutados, vermelhos; os filtros, as colunas, a Indisp., o operador e o técnico e o CSV).

## Regras desta torre

- Prazo e meta (15 min, 30 min, horários de ronda) são **dado**, e não número solto no código: um só lugar, com o
  porquê ao lado.
- Hora sempre no fuso da usina e de Brasília. O servidor de produção roda em UTC.
- Mensagem ao cliente: só texto público, nunca dado interno. O que sai fica registrado na ocorrência.
- Nome e telefone de pessoa vêm do cadastro (`nexus/cadastro/`), que já cifra. Não guarde cópia em outro lugar.
- O repositório é público: dado real (print, planilha, JSON exportado) não entra em commit, nem em teste.
