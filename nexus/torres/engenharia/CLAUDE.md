# CLAUDE.md — torre Engenharia

Engenharia de manutenção: confiabilidade dos ativos, criticidade, FMEA e causa raiz, laudos. Hoje só a
**Confiabilidade** é tela de verdade; as outras caem no placeholder da casca.

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
  5 min; a primeira visita lê na hora. Linha do REST é por tarefa; o cartão é por OS.
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
  Fracttal) saiu.

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
  depois de subir (`nexus/engenharia/instalar`, desliga com `NEXUS_CAMPO_AQUECER=0`).
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
- Comparar com o `engenharia.json` do PCM (só para conferir, nunca como fonte): os níveis e as contagens dos 30 dias
  devem bater, salvo as OS canceladas e os ativos que o PCM casava errado pelo nome.
