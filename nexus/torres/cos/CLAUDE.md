# CLAUDE.md — torre COS

A torre do Centro de Operações: a mesa do operador, o ciclo da ocorrência e a comunicação com o cliente. É a pasta
do programador do tempo real/COS. Leia também o `CLAUDE.md` da raiz (convenções e regras da casa).

## O que a torre vai ser

As oito telas estão declaradas em `__init__.py` e hoje são placeholder (cada uma diz a pergunta que vai responder e
a fonte prevista). A base de produto são as specs do Fillipe, no SharePoint `Gridco/4. O&M/6.Gerencial/10. Nexus`:

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

- O template vai em `templates/cos/<tela>.html` e estende `base.html`. Login, menu, cadeira e tema vêm prontos.
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

## Regras desta torre

- Prazo e meta (15 min, 30 min, horários de ronda) são **dado**, e não número solto no código: um só lugar, com o
  porquê ao lado.
- Hora sempre no fuso da usina e de Brasília. O servidor de produção roda em UTC.
- Mensagem ao cliente: só texto público, nunca dado interno. O que sai fica registrado na ocorrência.
- Nome e telefone de pessoa vêm do cadastro (`nexus/cadastro/`), que já cifra. Não guarde cópia em outro lugar.
- O repositório é público: dado real (print, planilha, JSON exportado) não entra em commit, nem em teste.
