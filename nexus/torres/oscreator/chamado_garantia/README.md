# chamado_garantia

A lógica de abertura de **chamado de garantia**, sem interface e sem rede. Feita para ser usada por
mais de um app: o **OS Creator** (desktop, o supervisor abre a inspeção) e o **app de campo**
(celular, o técnico clica em "Necessário abrir chamado" dentro da OS que está preenchendo).

O `os_creator/chamado_insp_spec.py` é só uma ponte para cá. **Regra nova entra aqui**, nunca lá —
duas cópias divergindo significam a OS do supervisor e a do técnico pedindo coisas diferentes ao
mesmo fabricante, que é o problema que este projeto veio resolver.

## O fluxo, em três OS

| # | OS | Tipo de tarefa | Etiqueta | Quem |
|---|---|---|---|---|
| 1 | De campo | Corretiva | — | técnico, em campo |
| 2 | **De chamados** | **Inspeção** | **Aguardando Garantia** | técnico, em campo |
| 3 | De acompanhamento | Administrativa | CHAMADOS | equipe de chamados |

Este pacote monta a **2** e, desde a **1.3.0** (08/11/2026), também a **3** (`acompanhamento.py`).

## A OS de acompanhamento (1.3.0, 08/11/2026)

A administrativa do time de chamados nasce quando a Inspeção é **realizada**, com as respostas do técnico na nota (Levi,
08/11/2026: "quero que a administrativa só nasça quando a de inspeção é realizada!"; o desenho do mesmo dia a fazia nascer
junto com a Inspeção, e foi revertido). O App cria a dele no fechamento; o OS Creator, a da Inspeção realizada que ficou
sem (a do supervisor, a fechada na web). Até a 1.2.0 isso morava só no servidor do App (`_acompanhamento_se_chamado` e
`_mapa_chaves`).

```python
d = cg.montar_acompanhamento(inspecao, fabricante,
                             cg.respostas_de(checklist, itens))         # a Inspeção realizada: as respostas do técnico
# inspecao = {"folio", "code", "nome_ativo", "tipo", "os_pai", "event_date"}
# d = {"titulo", "nota", "tipo_tarefa", "etiqueta", "subtarefas", "campos", "extras", "aguardando"}
```

- A nota sai **igual** à do App de hoje: a 1ª linha "[CHAMADO] Acompanhamento — <marca> · <tipo>" (o quadro do
  Acompanhamento de chamados do OS Creator a lê), a OS de campo, a Inspeção e o ativo, a data da falha, e os campos do
  formulário do fabricante (pela `chave`, `mapa_chaves`) mais as demais respostas; até 3800 caracteres, cada resposta até
  300. Sem respostas (`respostas=None`): "Campos do formulário do fabricante: aguardando a inspeção" (`nota_aguardando`
  reconhece), do desenho revertido; ninguém usa hoje.
- A subtarefa única é "Nº do ticket / protocolo aberto no fabricante": o quadro acha o ticket por "ticket"/"protocolo".
- Fica fora daqui: o payload do RPC, os ids do Fracttal e o responsável (cada lado tem o seu).
- O App copia a pasta inteira para `middleware/chamado_garantia`; as duas pontas sobem a 1.3.0 juntas.
- Prova: `tests/test_chamado_garantia_acompanhamento.py` (a nota comparada com a cópia do laço do App v332).

## Uso no app de campo

```python
import chamado_garantia as cg

# o botão "Necessário abrir chamado" só aparece para ativo que tem modelo
if cg.pode_abrir(ativo):
    ...

# ao clicar: monta tudo o que a OS de inspeção precisa
d = cg.montar(ativo, fabricante="", catalogo=todos_os_ativos)

d["tipo_tarefa"]   # "Inspeção"
d["classif_1"]     # "Programada"
d["classif_2"]     # "Elétrica"
d["etiqueta"]      # "Aguardando Garantia"
d["fabricante"]    # descoberto sozinho quando o cadastro permite
d["titulo"]        # "[Ativo] - Inspeção para chamado <marca>"
d["subtarefas"]    # já no formato do RPC do Fracttal
d["resumo"]        # "8 subtarefas · 6 obrigatórias · 2 com anexo obrigatório"
```

**O que o app de campo fornece**, porque já está na OS aberta na mão do técnico:

- o **ativo** (clonado da OS atual);
- a **data do incidente** (clonada da OS atual);
- o **responsável** (o próprio técnico, ou quem a OS atual indicar);
- a **OS pai** (a OS atual).

**O que este pacote resolve sozinho**: marca, tipo de tarefa, classificação, etiqueta, título e as
subtarefas do fabricante.

## Descoberta da marca

`cg.descobrir_marca(ativo, catalogo)` tenta em duas etapas:

1. **texto do ativo** — acerta 94% dos inversores e 85% das estruturas de tracker (medido no
   catálogo inteiro em 29/07). A marca vale como **palavra inteira** (20/10/2026: como pedaço de
   palavra, o "STI" achava o "sti" de uma "Rua Celestino" ou de uma "Rua Faustino" (exemplos
   inventados) no endereço de 16 cabines, skids e estações, e o código de uma usina, que começa
   com STI, fazia os trackers dela virarem STI), e conta também como o Fracttal a escreve (`APELIDOS_NO_FRACTTAL`: "CANANDIAN SOLAR", o modelo "SUN2000", "HUAWEII",
   "AXIALtracker"). O nome do fornecedor vale antes do apelido;
2. **ativos irmãos da usina** — para NCU, RSU e sensores da estação, que se chamam só "NCU 1" ou
   "Piranômetro 1". A NCU de uma planta de trackers STI é STI. Só vale com o `catalogo`: sem ele, a
   tela pergunta.

Devolve `""` quando não dá para saber — e aí a tela **tem** de perguntar. Nunca chuta.

## A lista de fornecedores é a do Nexus (`registro.py`, 20/10/2026)

A tela **Nexus > Chamados > Fabricantes** (o Controle de fornecedores do OS Creator) grava na aba
`os_creator · chamado_modelos` do banco da Gridco, um bloco por linha (`BASE`, `TIPO:<tipo>`,
`MARCA:<fornecedor>` com as perguntas, o canal, os tipos que ele atende e se está arquivado). Quem
monta a inspeção lê a aba e chama:

```python
banco = cg.registro.de_linhas(linhas)   # [{"chave", "valor"}] da aba → {chave: valor}
cg.registro.aplicar(banco)              # por cima do código, em memória, no lugar
cg.marcas_para("Inversor")              # a lista do técnico: só quem atende o tipo
```

Fornecedor novo entra na lista dos tipos que atende e passa a ser reconhecido no nome do ativo;
arquivado sai da lista. Bloco sem linha no banco vale o do código (`registro.semente`). O OS Creator
aplica assim desde 27/09 (`chamado_modelos_store`, que agora chama o pacote); o App de Campo passa a
aplicar igual desde a v290 (20/10/2026), relendo a aba de 5 em 5 minutos. **O nome do fornecedor tem de ser como o Fracttal escreve**
(é por ele que a marca vem marcada sozinha); grafia diferente que já existe no Fracttal vai no
`APELIDOS_NO_FRACTTAL`.

## Campos que o app preenche no lugar do técnico

`cg.derivados(ativo, data_do_incidente)` devolve o que não faz sentido perguntar em campo:

- `data_falha` — a data do incidente da própria OS;
- `unidades` / `quantidade` — 1, porque a OS é de um ativo;
- `menos_7d` — calculado da data do incidente, **recalculado a cada chamada** (a equipe de chamados
  abre o ticket dias depois, e a resposta muda).

> ⚠️ No formulário da Huawei, "menos de 7 dias" é sobre a **idade do equipamento**, não a da falha.
> Está calculado pela data do incidente porque foi o pedido; se a leitura mudar, é uma conta só.

## Cobertura

11 marcas, 26 combinações de tipo de ativo × marca, extraídas dos nove processos de abertura em
`4. O&M/11.Pré-Operação/2. Controle/13. Gestão de Chamados/02. Processos de Abertura e
Acompanhamento`.

Tipos de ativo atendidos: **Inversor · Estrutura Trackers · NCU · RSU · Estação Meteorológica ·
Cabine · Skid**, mais os sensores da estação por alias (**PRN** piranômetro, **SDT** sensor de
temperatura, **FDL** fieldlogger).

Sem processo escrito ainda: **Sparkin** (195 trackers) e **MTR** (149 trackers).

## Tipos de subtarefa do Fracttal

Sondados ao vivo na conta 4987 — a documentação REST **está errada** para esta conta:

| id | é | doc REST dizia |
|---|---|---|
| 1 | Texto | Texto |
| 2 | Sim / Não | Número |
| 3 | **Número** | **Data** |
| 4 | Verificação (Aprovado/Alerta/Falhou) | Checkbox |
| 7 | **Lista** (traz `dropdown_options`) | **Foto** |

**Não existe tipo Data.** Data e hora vão como texto, com o formato na própria pergunta.

`is_required` e `attachments_required` funcionam por subtarefa — é o que permite exigir o número de
série digitado **e** a foto da etiqueta.
