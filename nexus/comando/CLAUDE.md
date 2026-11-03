# CLAUDE.md — Comando: motor de insights, Caixa de entrada e sino

Os setores conversando (Levi, 03/11/2026: "Preciso pensar em uma forma dos setores conversarem entre si de forma
rastreável e clara com chats, notificações..."; sobre a tela de Insights do mockup R18: "essa parte de insights também é
muito boa"; e "construa o que você sugere"). PRD e tarefas no formato do Taskmaster: `.taskmaster/docs/prd.txt` e
`.taskmaster/tasks/tasks.json` (escritos à mão: a CLI do Taskmaster chama IA paga para gerar; a casa é custo zero).

## As fases (uma de cada vez, mostrada ao Levi antes de seguir)
1. **Insights + sino + Caixa de entrada** (esta pasta + `nexus/torres/comando/`): NO AR quando o Levi aprovar a prévia.
2. Conversa com @menção em cada insight, OS e usina.
3. Pedidos entre setores com prazo e o painel de tempo de resposta.
4. O Início novo ("Pede você agora", paleta preto #030407, azul #1558c9, lima #D4FF24): decidir antes se a paleta vale
   para o Nexus inteiro.

## Os arquivos
| Arquivo | O que é |
|---|---|
| `regras.py` | As regras, PURAS (recebem listas já lidas, devolvem insights). O catálogo `REGRAS` (nome, torre dona, KPI, fonte) |
| `motor.py` | Lê as fontes que o Nexus JÁ lê (uma função por regra em `FONTES`), roda as regras, cópia de 5 min pelo `visao._ler` |
| `estado.py` | Quem assumiu, concluiu ou reabriu, as áreas notificadas e o retorno de cada uma: o livro `nexus_insights · fato_evento_insight` |
| `../torres/comando/__init__.py` | As telas Comando → Insights e Caixa de entrada, e o POST `/t/comando/insights/acao` |
| `../casca/__init__.py` (`_sino`) + `base.html` | O sino do topo |

## As regras da Fase 1 (e de onde cada uma lê)
| Regra | Torre dona | Fonte |
|---|---|---|
| R03 religamento repetido na mesma cabine (3+ em 30 dias) | cos | `cos/religamentos.painel` sobre `andamento.ler_ocorrencias` de cada cliente |
| R05 sem comunicação há mais de 24 h | cos | o banco: `nexus_cos_normalizacoes · fato_ocorrencia_aberta` (só Thopen) |
| R06* OS corretiva aberta em ativo que já tem chamado de garantia | chamados | o banco: `nexus_os · fato_tarefa_os` × `nexus_chamados · fato_chamado` (pelo `equipamento_id`) |
| R07 extintor vencido | hseq | `hseq/extintores.extintores` + `decisoes.separar` (sem os excluídos) + `por_usina` |
| R09 equipe acima da capacidade na semana | pcm | o banco do robô do PCM (`pcm/fonte.ler`): `resumo` da `semana_ativa`, `hh_util > hh_disp` |
| R11 usina sem ronda há mais de 7 dias | campo | `campo/visao.rondas().cobertura` |
| R13 chamado aguardando o fabricante há 5 dias ou mais | chamados | `campo/responsaveis.chamados` (o fato + a troca de status da tela de Garantias) |
| N01 normalizada com a OS aberta 7+ dias / hora a corrigir | cos | `cos/normalizacoes.ler` + `_item` |

**Fora da Fase 1, e por quê:** R01 (a anomalia sem OS é calculada pela plataforma, numa moldura; não passa pelo Nexus),
R02, R04 e R08 (pedem ajuste), a R06 completa (falta a vigência da garantia: nenhuma tela tem "garantia até"), R10 e
R12 (sem fonte). **Nenhuma regra lê o Fracttal, a SunOp ou a PV Operation**: as OS e os chamados são os livros que o
Nexus publica de hora em hora.

## Notificar as áreas e o retorno de cada uma (03/11/2026)
Levi: "religamentos em 30 dias e etc é coisa da engenharia, já está com eles... pode aparecer tipo 'notificar
engenharia'"; "extintores pode ser tanto equipe de segurança quanto supervisor o manager quer algo como notificar as
áreas e saber como está e receber retornos dessas áreas".
- Cada regra tem `avisar` (`regras.REGRAS`): as áreas que o botão "Notificar ..." já traz (R03 → Engenharia; R07 →
  Segurança e Campo; R11 → Campo e PCM...). "Notificar outras áreas" escolhe qualquer torre de operação (fora o Comando
  e o OS Creator), com uma mensagem.
- A área avisada vê o pedido na Caixa de entrada ("Pedidos para o seu setor") e no sino, e responde: Recebido, Em
  andamento ou Resolvido, com o texto. Só quem é da área (o setor vê a torre) responde por ela. Quem notificou vê o
  retorno de cada área no insight; resolvida, a área pode ser notificada de novo.
- Se a regra para de apontar (a condição sumiu), o insight sai da lista, e os pedidos dele junto: está resolvido na
  fonte.

## O visual
Uma lista numa superfície só, uma linha por insight que abre ao clicar (Levi: "não sou muito fã dessa barra lateral em
vermelho, temos muito dela... poderia fazer algo diferente?"): a gravidade é um selo (ponto + palavra), sem faixa nem
borda colorida; à direita, com quem está (as áreas avisadas e o retorno, ou o dono). Aberta: o que a regra viu, o que
fazer, as áreas e os retornos, e as ações.

## As regras da casa aqui
- **O id do insight é estável** (`regra:objeto`, ex.: `N01:16702`, `R07:<usina_id>`): é por ele que o Assumir sobrevive
  à próxima conta. Mudar o objeto de uma regra solta o que foi assumido.
- **A torre é o dono** (o setor vê as torres liberadas em Base → Acessos): sem cadastro de cadeira. A Caixa de entrada e
  o sino filtram por `motor.torres_da_pessoa()` (`setor_telas.acesso`; o administrador vê tudo).
- **Fonte que falha não derruba as outras**: vira `regras[id]["erro"]`, a tela de Insights diz "não leu" e a Caixa avisa.
- **O sino nunca calcula na página** (`motor.do_cache` + `estado._CACHE`): sem a cópia do motor, não sai número e a
  conta começa por trás. Conta o crítico e o de atenção SEM DONO das torres da pessoa e os pedidos de retorno pendentes
  para as áreas dela.
- **Concluído some da Caixa e do sino** e fica concluído enquanto a regra seguir apontando (alguém já tratou); Reabrir
  volta. O livro só acrescenta; quem e a nota só cifrados.
- Escrever regra nova: a função pura em `regras.py` (com teste de dado inventado: o caso e o vizinho que fica fora),
  a entrada em `REGRAS` e a leitura em `motor.FONTES`. Fonte nova no banco: governança antes (nexus/dados/CLAUDE.md).

## Prova
`tests/test_comando_insights.py` (cada regra com o caso e o vizinho; o motor com uma fonte quebrada; o Assumir cifrado e
sem repetir; a Caixa só das torres do setor; o sino sem dono e sem cópia). Os testes da torre (`test_torres.py`,
`test_casca_inicio.py`) passaram a esperar o Comando com a Caixa de entrada e os Insights prontos.
