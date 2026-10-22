# CLAUDE.md — torre COS

A torre do Centro de Operações: a mesa do operador, o ciclo da ocorrência e a comunicação com o cliente. É a pasta
do programador do tempo real/COS. Leia também o `CLAUDE.md` da raiz (convenções e regras da casa).

## O que a torre vai ser

As telas estão declaradas em `__init__.py`. Ronda padronizada, Parede de eventos e Ocorrências já leem o Andamento da
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
2. Abra o pull request para a `main`. A conferência **pasta-do-cos** (`.github/workflows/pasta-do-cos.yml`) aprova se
   o pedido mexe só na área do COS e reprova, listando os arquivos, se mexe fora dela.
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

## Regras desta torre

- Prazo e meta (15 min, 30 min, horários de ronda) são **dado**, e não número solto no código: um só lugar, com o
  porquê ao lado.
- Hora sempre no fuso da usina e de Brasília. O servidor de produção roda em UTC.
- Mensagem ao cliente: só texto público, nunca dado interno. O que sai fica registrado na ocorrência.
- Nome e telefone de pessoa vêm do cadastro (`nexus/cadastro/`), que já cifra. Não guarde cópia em outro lugar.
- O repositório é público: dado real (print, planilha, JSON exportado) não entra em commit, nem em teste.
