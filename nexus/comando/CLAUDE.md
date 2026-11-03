# CLAUDE.md — Comando: motor de insights, Caixa de entrada e sino

Os setores conversando (Levi, 03/11/2026: "Preciso pensar em uma forma dos setores conversarem entre si de forma
rastreável e clara com chats, notificações..."; sobre a tela de Insights do mockup R18: "essa parte de insights também é
muito boa"; e "construa o que você sugere"). PRD e tarefas no formato do Taskmaster: `.taskmaster/docs/prd.txt` e
`.taskmaster/tasks/tasks.json` (escritos à mão: a CLI do Taskmaster chama IA paga para gerar; a casa é custo zero).

## As fases (uma de cada vez, mostrada ao Levi antes de seguir)
1. **Insights + sino + Caixa de entrada** (esta pasta + `nexus/torres/comando/`): NO AR 03/11/2026 (3cd7564).
2. **Conversa com @menção em cada insight, OS e usina** (`conversa.py`): ver a seção abaixo.
3. Pedidos entre setores com prazo e o painel de tempo de resposta.
4. O Início novo ("Pede você agora", paleta preto #030407, azul #1558c9, lima #D4FF24): decidir antes se a paleta vale
   para o Nexus inteiro.

## Os arquivos
| Arquivo | O que é |
|---|---|
| `regras.py` | As regras, PURAS (recebem listas já lidas, devolvem insights). O catálogo `REGRAS` (nome, torre dona, KPI, fonte) |
| `motor.py` | Lê as fontes que o Nexus JÁ lê (uma função por regra em `FONTES`), roda as regras, cópia de 5 min pelo `visao._ler` |
| `estado.py` | Quem assumiu, concluiu ou reabriu, as áreas notificadas e o retorno de cada uma: o livro `nexus_insights · fato_evento_insight` |
| `../torres/comando/__init__.py` | As telas Comando → Insights e Caixa de entrada, o miolo de um insight (`GET /t/comando/insight/corpo`) e o POST `/t/comando/insight/acao` (os endereços antigos `/insights/...` seguem valendo) |
| `../torres/comando/templates/comando/_insight.html` + `static/comando/insights.js` | A linha do insight (`cartao`) e o miolo (`corpo`), que vem só ao abrir |
| `conversa.py` | A conversa presa ao objeto com @menção: o livro `nexus_conversas · fato_mensagem`, as menções não lidas (`para_mim`) e a lista do @ (`pessoas_mencionaveis`) |
| `../torres/comando/templates/comando/_conversa.html` + `static/comando/conversa.js` | O componente da conversa (dentro de cada insight e na página da OS e da usina) e o @ |
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

## A conversa com @menção (Fase 2, 03/11/2026)
Levi: "pode seguir para a fase 2". A conversa mora NO objeto (`tipo:id`: `insight:R07:2`, `os:16702`, `usina:12`),
como fazem ServiceNow, Jira e Linear, não num chat solto.
- **Onde aparece:** dentro de cada insight (a lista dos Insights e a Caixa), e na página `/t/comando/conversa/<tipo>/<id>`
  (a OS e a usina; a conversa nova sai da Caixa: "Começar uma conversa sobre uma OS ou uma usina").
- **@menção:** digitar @ abre a lista das áreas (as torres de operação) e das pessoas com setor (Base → Acessos → Pessoas e
  setores; o nome do pessoal do Fracttal, 1 h na memória). A lista é pedida ao servidor só no 1º @
  (`/t/comando/conversa/pessoas`), nunca ao abrir a página. A pessoa vai pelo código do e-mail (`pessoa_hmac`), a área
  pela torre; o `@Nome` que sai do texto não vai. Sem JavaScript, as áreas se marcam em "Mencionar áreas".
- **Quem é avisado:** a pessoa mencionada e todo mundo cujo setor vê a torre mencionada. Aparece na Caixa ("Menções
  para você", uma linha por conversa) e no sino, até a pessoa marcar como lida ou escrever na conversa (escrever conta
  como ler). Quem escreveu não se avisa.
- **O sino só lê as cópias** (`conversa.copias()`): com a cópia vencida (1 min) ou vazia, a leitura das conversas e dos
  eventos dos insights começa por trás, e o mencionado vê o número sem precisar abrir a Caixa antes.
- **Acesso (03/11/2026, Levi: "libera a caixa para todos os setores"):** a Caixa de entrada é de todo setor
  (`Tela.de_todos`, entra no `setor_telas.das_do_setor` como a tela do dono), então todo mencionado vê o aviso. O miolo e
  as ações do insight moram em `/t/comando/insight/` (singular): `/insights/...` casa com a tela Insights no portão, e quem
  só tem a Caixa não abriria o insight. Quem só tem a Caixa abre o miolo dos insights das torres dele e dos que pedem
  retorno a ele (`_ve_o_insight`); a tela Insights continua pela marca.

## O visual
Uma lista numa superfície só, uma linha por insight que abre ao clicar (Levi: "não sou muito fã dessa barra lateral em
vermelho, temos muito dela... poderia fazer algo diferente?"): a gravidade é um selo (ponto + palavra), sem faixa nem
borda colorida; à direita, com quem está (as áreas avisadas e o retorno, ou o dono). Aberta: o que a regra viu, o que
fazer, as áreas e os retornos, e as ações.

## As regras da casa aqui
- **A lista vem leve; o miolo vem ao abrir** (03/11/2026, Levi: "cliquei em nexus insights e travou tudo"). Medido com o
  dado real: 327 insights, a página com todos os miolos dava 2 MB, 1.310 formulários e 12.544 campos, e o navegador
  travava. Agora a linha vem na página e o miolo (5,5 KB) vem por `/t/comando/insight/corpo` quando a pessoa abre
  (`insights.js`); a página caiu para 320 KB e 4 campos. Só os "Pedidos para o seu setor" da Caixa vêm abertos. O
  endereço com `#ins-...` ou `#conv-insight-...` (o sino, a volta de uma ação) abre o dele; sem JavaScript, `?abrir=<id>`.
- **Insights e Caixa nunca esperam a conta** (`motor.sem_esperar`): sem a cópia (o Nexus acabou de subir, e todo push
  reinicia), a conta começa por trás e a tela diz que está calculando e se atualiza em 10 s; o Assumir recusa até a
  lista existir. A conta fria levou 19 s no PC (sem o Andamento, que no servidor soma) e segurava a página.
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
sem repetir; a Caixa só das torres do setor; o sino sem dono e sem cópia; a lista leve com o miolo ao abrir; a tela
sem cópia que não espera; a Caixa de todo setor). Os testes da torre (`test_torres.py`,
`test_casca_inicio.py`) passaram a esperar o Comando com a Caixa de entrada e os Insights prontos.
