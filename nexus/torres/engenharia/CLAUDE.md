# CLAUDE.md — torre Engenharia

Engenharia de manutenção: confiabilidade dos ativos, criticidade, FMEA e causa raiz, laudos. Hoje só a
**Confiabilidade** é tela de verdade; as outras caem no placeholder da casca.

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
