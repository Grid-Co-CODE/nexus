# Aprovação de OS por fatos: desenho (05/11/2026)

Levi, 04/11/2026: "No nexus, em campo app crie uma aba de aprovação de OS. Pode fazer por cima da aba Aprovação de OS,
refaça com essas regras e deixe algo bem fácil e dinâmico para os supervisores!". "Essas regras" são as do pré-filtro da
Verificação medidas na sessão de 28/10 a 04/11 (relatório "Pré-filtro da Verificação: fatos primeiro"): só fatos, sem IA.

## Por quê

O back-office não dá conta de abrir toda OS em verificação (~2.200 OS esperando, 1.850 tarefas por mês no escopo). Nas
30 OS da medição de 26/10, dois fatos separaram o que o supervisor devolve do que ele aprova: no escopo (16 OS), as regras
seguraram as 5 devolvidas e liberaram 6 das 11 aprovadas, sem erro, sem custo e sem ler foto. A pessoa continua
decidindo (opção A); a tela entrega a fila já separada, com a prova de cada aviso, e deixa aprovar rápido.

## Objetivos

- A Aprovação de OS (Campo · App) vira um **quadro de três colunas**: Pronta, Em dúvida, Não OK. Cada OS cai na pior
  situação entre as tarefas dela.
- **Todos os supervisores** veem o quadro; cada um abre nas UFVs em que é o Responsável O&M (o filtro de hoje), com
  "Todos", filtro de cliente e busca que respondem na hora (sem recarregar).
- **O cartão da OS** mostra, nesta ordem: OS, UFV, cliente, tarefas e dias esperando; o score (a nota do fechamento do
  App, a pior das tarefas); os avisos com a prova (as duas fotos repetidas lado a lado; "6 fotos anexadas 2 dias depois
  do fechamento"); e logo depois o botão **Aprovar**. A OS também abre o card do OS Creator, como hoje.
- **Aprovar várias:** caixa de marcar nos cartões de Pronta e Em dúvida, "Selecionar todas" por coluna e o botão
  "Aprovar as marcadas (N)", com confirmação, uma OS depois da outra, andamento na tela e o erro de cada uma.
- Uma linha "Fora do pré-filtro: N OS" abre essas OS sem as regras, cada uma aprovável pelo cartão.

## Não objetivos

- Nenhuma IA lendo foto ou texto.
- O Nexus não aprova sozinho (a opção B fica para depois) e não devolve OS (o devolver segue no App).
- Não muda a nota do técnico nem o placar.

## Antiobjetivos (fracasso mesmo funcionando)

- A tela esperar o Fracttal ou ficar lenta: a fila e os fatos são lidos por trás; a visita só lê memória.
- Gastar a cota de 200 pedidos/min da empresa: um pedido de leitura por OS nova, pelo porteiro, como leitura de fundo.
- Aprovar em lote a OS errada calado: só aprova o que está marcado, com confirmação que diz quantas e de que coluna, e
  cada falha fica à vista.
- Aviso sem prova: todo aviso diz a foto, a hora ou o motivo.

## As regras (parâmetros no `config`, com padrão)

| Fato | Medida | Coluna |
|---|---|---|
| Foto anexada depois | hora de anexação (o `Last-Modified` do arquivo no S3; o REST de anexos do Fracttal não dá data) mais de `NEXUS_PREFILTRO_HORAS_TARDE` (24) horas depois do último fechamento da OS no App (a hora do celular do livro de fechamentos) | Não OK |
| Foto repetida | a mesma imagem duas vezes na OS, comparada SEM o carimbo do App: dHash de 256 bits da parte de cima da foto (75%), diferença até `NEXUS_PREFILTRO_DIF` (12); captura de tela (sem GPS na descrição) só com diferença até 4, porque telas parecidas enganam | Em dúvida |
| Fechada fora do App | a tarefa não está no registro do App: sem fotos e horários do App para conferir | Em dúvida |
| Nenhum dos três | | Pronta |
| Fotos ainda não lidas | | "Ainda conferindo" (aparece, abre e aprova pelo cartão; não entra no lote) |

**Fora do pré-filtro** (não entram nas colunas): religamento (tipo Religamento ou Religamento Remoto, ou tarefa de
religamento) e OS com a etiqueta PERFORMANCE (Levi, 04/11: "religamento remoto ou religamento real não entra, nem OSs
com etiqueta de performance!"). *Decisão minha:* também as etiquetas CHAMADOS e ENGENHARIA e as OS criadas pelo COS, a
mesma regra das "OSs em verificação" do Painel do responsável (Levi, 29/10), para os dois números baterem.

Avisos sem mudar a coluna (*decisão minha*): nota do App abaixo de 80, já devolvida antes, foto marcada como divergente
pelo App, ronda com pendência (os motivos da regra do App de hoje, `aprovacao.motivos`).

## Como funciona por trás

- **A fila** é a de hoje (`nexus/campo/aprovacao.py`: relida por trás a cada 10 min, guardada em disco).
- **Os fatos** (`nexus/campo/prefiltro.py`, novo): depois de cada releitura da fila, um laço de fundo
  (`fracttal_conta.de_fundo`) pega as OS do escopo ainda não conferidas (ou cujas tarefas mudaram), a mais nova
  primeiro, e para cada uma faz UM pedido de leitura (`work_orders_attachments?folio=`), baixa as imagens do S3 (fora da
  cota), calcula o hash e guarda a hora de anexação. Ritmo: no máximo 1 OS a cada 2 s e um teto por volta. Fica em
  memória e em disco (`dados/campo/prefiltro.json.gz`, cópia de trabalho, como a fila); a miniatura das fotos repetidas
  (240 px) em `dados/campo/prefiltro_fotos/`, servida por rota com login.
- **O fechamento no App** vem do livro de fechamentos que o App grava no banco (`tabela_qlog`, a mesma das regras).
- **Aprovar** é a rota do OS Creator que o Painel do responsável já usa (`POST /os/api/os/<id>/concluir`, com o login
  do Fracttal de quem clica); depois, a conferência de hoje (`/t/campo/aprovacao/<id>/conferir`) tira a OS da fila.
- **O veredito no banco** (para medir a sombra contra a decisão do supervisor): livro novo `nexus_prefiltro`, fato
  `fato_prefiltro_os` (1 linha = 1 OS conferida: dia, OS, usina_id, coluna, fatos em número, versão das regras; sem
  nome), declarado antes no catálogo. *Decisão minha:* entra por último; se o tempo apertar, vira a próxima entrega.

## Prova

- Testes das regras (hash com e sem carimbo, captura de tela, anexada depois, fora do App, escopo, pior tarefa),
  do laço de fundo com Fracttal e S3 falsos (ritmo, teto, cópia em disco, OS que mudou), da tela com fila falsa (colunas,
  contas, filtros, cartão, fora do pré-filtro, ainda conferindo) e `node --check` do script.
- Navegador na cópia de prova (porta 5170), computador e 375 px.
- O aprovar em lote reaproveita a rota de concluir já usada no Painel; a prova no Fracttal de verdade (TESTE - PA,
  lendo de volta o status) fica dita na entrega se não for feita.

## Decisões minhas depois da revisão (05/11/2026)

- **A hora do fechamento é a da OS:** o último fechamento das tarefas dela no App (a hora do celular do livro), não o
  da tarefa. Casar a tarefa do anexo com a do livro do App pelo nome é frágil, e nas 30 OS da medição dá o mesmo.
- **Fato antes de todas as fotos lidas:** a OS vai para a coluna pior assim que houver um fato (fora do App ou foto
  anexada depois já lida), com o aviso "faltam fotos por ler"; sem fato nenhum e com fotos por ler, "Ainda conferindo".
- **A tela de hoje sai inteira** (a lista por usina, os indicadores e a barra da idade): o quadro entra no lugar, no
  mesmo endereço, com o filtro de responsável, o CSV (com a coluna e os motivos) e a conferência de depois do Concluir.
  Os motivos da regra do App (`aprovacao.motivos`) viram só avisos. Devolver nunca existiu no Nexus: segue no App.
- **Sem sessão do Fracttal:** o Aprovar responde como o Concluir do Painel: 401 vira o aviso "Entre no OS Creator com a
  sua conta do Fracttal", e o lote para na primeira recusa de login; outros erros ficam no cartão da OS e o lote segue.
- **O quadro não muda sozinho na frente da pessoa:** é montado na visita; a marcação vive na página. Depois do lote, cada
  OS aprovada sai do quadro pela conferência de hoje (o Fracttal confirma), e as que falharam ficam marcadas com o erro.
- **Veredito no banco sem `usina_id`:** grava com a usina vazia e a ligação é medida, como os outros fatos do Nexus.

## Deixado para quem constrói

Nomes, CSS (só tokens do `nexus.css`), o desenho do cartão no celular, o teto de OS por volta e a ordem exata dos avisos.
