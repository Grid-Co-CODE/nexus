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
do PCM fora do banco e a geração em formato largo. Os passos 3, 5 e 6 foram feitos em 08/10 (desenho:
`docs/superpowers/specs/2026-10-08-kimball-passos-2-a-6-design.md`), e no mesmo dia o passo 4 (as telas do Campo leem
os fatos, linha "Telas do Campo" abaixo) e o lado do Nexus do passo 2 (pendência 2); os passos 0 e 1 foram **adiados pelo Levi** (ver
"O que herda" e "Pendências"). Nada disso foi gravado daqui: entra no banco quando o código for ao servidor (a carga de
hora em hora do servidor passa a gravar o que está marcado "grava"). A exceção é a programação do PCM: o histórico
(W21 a W41) foi gravado UMA vez em 08/10 pela carga única, a pedido do Levi; mantê-lo em dia é da carga do servidor.

| Peça | Onde | Grava? | O que é |
|---|---|---|---|
| Catálogo (a matriz de barramento) | `catalogo.py` | — | os fatos ativos (a conta viva é a do `catalogo.resumo()`, que a tela mostra; os dois de extintor do HSEQ entraram em 09/10, antes de o App publicar o livro) + os que viraram fonte de outro, 7 dimensões e os **livros do Nexus** (`LIVROS`, registrados antes de existir: 28 em 20/10/2026, com o `nexus_falhas`, que a plataforma grava; `no_banco` diz quais já existiam quando foram conferidos por GET). Todo fato declara `tipo`, `chave`, `medidas` (`Medida`: coluna com a unidade, unidade, soma `aditiva`/`semi`/`nao`), `fontes` e `janela_origem`. Mais as `CONHECIDAS` (09/10): as tabelas do banco que não são fato nem livro do Nexus, aba por aba, com o papel e o porquê (o radar). **Fonte única** da tela, dos testes e desta página |
| Domínios | `dominios.py` | — | a lista fechada de cada atributo (vala 1 limpa, 2 parcial, 3 obstruída; sensor 1 sujo, 0 VERIFICADO limpo, vazio = não verificado; situação da OS da ronda; as 6 falhas; situação da PT). Valor fora = vazio + conta na qualidade. `MAPA_ANTIGO` traduz o que cada fonte grava (inclusive o formulário da avulsa de 07/10, que nunca chegou ao banco). A avulsa usa as opções de vala do App (`VALA_OPCOES`) e grava o sensor como a palavra (`SENSOR_ROTULO`: "Sujo", "Limpo"; vazio = não verificado) desde 08/10. A anomalia da meta do Gerencial (`ANOMALIA_META`, 18/10/2026): os códigos que a plataforma põe na coluna `anomalia` do `fato_meta_usina_mes`; a frase é do Nexus. A linhagem da estrutura das usinas (`POTENCIA_REGRA`, `FRACTTAL_LIGADO_POR`, 20/10/2026: de onde veio o kWp e como o ativo do Fracttal foi ligado; `da_lista` lê vazio o que estiver fora) |
| Calendário | `calendario.py` → `nexus_dimensoes · dim_data` | hora em hora | 1 linha por dia, 2025 a 2027: `data_id` (AAAAMMDD), semana ISO, mês, trimestre, fim de semana, feriado nacional, dia útil |
| Feriados locais | → `nexus_dimensoes · feriados_locais` | hora em hora | estaduais e municipais (UF, município), cruzam com a usina pela cidade |
| Histórico (SCD tipo 2) | `historico.py` → `pessoas_historico`, `usinas_historico`, `qualidade_historico` | hora em hora | **1 linha = 1 versão de 1 membro, troca no dia de Brasília.** Cabeçalho `<id>, <rastreados…>, versao, valido_de, valido_ate, valido_de_id, valido_ate_id, vigente, inicio_presumido`. A 1ª versão vale "desde sempre" (19000101) com `inicio_presumido = 1`. 1ª medida (08/10): fechamentos que acham exatamente 1 versão, pessoa 25,4% → 100%, usina 26,4% → 100%; checklist 6,2% → 100%. As 135 + 258 linhas gravadas migram sozinhas na 1ª carga com este código |
| Equipamento (dimensão) | `equipamento.py` → `nexus_equipamentos · dim_equipamento`, `equipamento_apelido` | hora em hora, **só quando o sha das linhas muda** e o PCM foi lido | **1 linha = 1 código de ativo do Fracttal** (canônico). `equipamento_id = int(sha1("fracttal:"+código)[:13 hex]) >> 3` (49 bits, no máximo 15 dígitos: com 52 bits 77% tinham 16 e o Excel trocava o último dígito; Levi, 08/10): o mesmo número em qualquer máquina, sem registro; 0 colisões nos 22.353 códigos das fotos. Apelidos: `Supervisório · tracker`, `Gêmeo · equipamento`, `BD_Thopen · coluna`, `BD_Performance · coluna`. 1ª medida (08/10, sem a foto no banco): 8.314 membros, 98,9% com `usina_id`, 4.619 apelidos (tracker 4.287, gêmeo 332; coluna 0 até o de-para das abas). Com as duas fotos locais (medido pelo construtor): 22.356 membros, 87,6% com usina, 6.118 apelidos. **No banco** (GET em 11/10/2026: 8.395 membros e 4.619 apelidos, gravados às 20:42, antes da foto; a carga seguinte já lê a foto) |
| Foto dos ativos do Fracttal | `ferramentas/carregar_ativos_fracttal.py` → `nexus_ativos_fracttal · foto_ativos` | carga única, quem grava é o Levi: **gravada em 11/10/2026** (GET: 22.357 linhas, às 21:06) | as fotos do OS Creator (22/09 + os 719 códigos que só a de 21/06 tem): 22.357 linhas. A carga de hora em hora lê a foto do banco para a dimensão de equipamento. Renovar exige ler o Fracttal (fora do horário de campo) |
| Fechamento | `fatos.py` → `nexus_fatos · fato_fechamento` | hora em hora | 1 linha = 1 tarefa fechada pelo App. Foto acumulada (a revisão, aprovada/devolvida/nota corrigida, muda a linha depois: não é transação). 08/10: + `equipamento_id`/`equipamento_ligado_por`, + `tarefa_chave` (a mesma da programação), medidas com unidade (`nota_pts`, `fotos_qtd`, `pecas_qtd`, `xp_pts`; `vezes_programada_qtd`, que é o "Nº vezes programada" do PCM e conta a 1ª vez). Ensaio 08/10: 2.955 linhas, data 100%, usina 99,7%, equipe 97,7%, pessoa 94,4%, equipamento 99,7%, versão da época 100/100. Comparado valor a valor com o publicado às 12:40: 2.955 em comum, **0 diferenças** |
| Ronda (fato único) | `fato_ronda.py` → `nexus_fatos · fato_ronda` | hora em hora | **1 linha = 1 ronda realizada**: App com e sem OS (`rondas_app_campo`), checklist da carga única e avulsa válida. Foto acumulada (a situação da OS anda de "em verificação" para "criada"), `ronda_id = sha1("app\|"+Início)`. Ensaio 08/10: 874 linhas (749 com OS, 125 sem), data 100%, usina 99,8%, equipe 98,7%, pessoa 91,8% (689 pelo nome de UMA pessoa, 113 pelo checklist), equipamento 85,7% (749/749 com OS; sem OS não há ativo), checklist 125, 1 rótulo de falha fora do domínio. A validação por foto do livro da avulsa (`origem = "validacao_foto"`) fica FORA (`fato_ronda.eh_validacao_foto`: outro grão, não é ronda realizada; a qualidade conta quantas em `extra.validacao_foto`). A pessoa vem do `Técnico (HMAC)` quando o App mandar (passo 2) e as telas do Campo leem este fato (passo 4) |
| PT | `fato_pt.py` → `nexus_fatos · fato_pt` | hora em hora | **1 linha = 1 PT × ativo** (o App decide por linha). Foto acumulada. PTs = `SUM(primeira_linha_da_pt)`. Ensaio 08/10: 238 linhas = 232 PTs, data 100%, usina 99,2%, equipe 97,9%, solicitante 89,9%, decisor 0/201 (as 6 contas Admin estão fora do cadastro), equipamento 99,6%, paradas 132 |
| Qualidade da ligação | → `nexus_fatos · qualidade` | hora em hora | 1 linha por fato: quanto ligou a cada dimensão (1 casa decimal), `com_equipamento`, `pct_usina_versao`/`pct_pessoa_versao` (acham exatamente 1 versão) e `extra` (JSON com o que só aquele fato tem e `linhas_na_carga_anterior`) |
| Programação do PCM | `programacao.py` → `nexus_programacao · fato_programacao` | hora em hora, **pela mescla por semana** (decisão 7, 08/10); só quando o sha das linhas muda | **1 linha = 1 bloco de agenda** de uma tarefa planejada; as linhas `foraDoPlano` (execução, outro grão) ficam fora. Foto periódica semanal. O arquivo guarda 4 semanas: a carga (`carga._programacao`) lê o fato do banco, troca só as semanas do arquivo e mantém as outras; leitura que falha ou volta vazia com o livro existente não grava; a linha que não mudou guarda o `lido_em` de antes (`manter_lido_em`: a API guarda o histórico de cada linha que muda). **Gravado em 08/10 (17:05)** pela carga única (`ferramentas/carregar_programacao_historica.py`): W21 a W41, 21 semanas, **14.276 blocos** = 14.104 tarefas, 0 IDs repetidos; data 100%, usina 99,8%, equipe 99,0%, equipamento 99,9%, técnico 57,7% e responsável 73,5% (os campos não existiam no arquivo: técnico só desde a W30, 86–98% dali; responsável vazio em W21–W27, salvo 201 linhas da W24); conferido por GET semana a semana e pelo sha das linhas relidas |
| Geração em linhas | `geracao.py` (`carga.montar_geracao`) → `nexus_geracao · fato_geracao_usina_dia` | **grava depois de cada subida dos BDs** (decisão 8 tomada em 11/10/2026; inversor × dia em `nexus_geracao_inversor_AAAA_MM`, um livro por mês) | **1 linha = 1 aba de usina × 1 dia** (dia futuro fora) + o inversor × dia (1 linha por célula com número, só em memória). Ensaio 08/10: 42.550 usina × dia (646 dias, 01/01/2025 a 08/10/2026), 701.936 inversor × dia, 3.499 linhas de dia futuro fora; `usina_id` 0% **de propósito** (o de-para das abas não está publicado; calculado sem publicar: 87,8%); 3,0 MB |
| Checklist da ronda sem OS (carga única) | `fatos.py` → `nexus_rondas_checklist · fato_checklist_ronda` | não (carga única de 06/10) | as respostas das 125 rondas sem OS (11/08 a 06/10). Desde 08/10 é **fonte** do `fato_ronda` |
| Ronda avulsa | `campo/ronda_avulsa.py` (+ `ferramentas/importar_avulsas_planilha.py`) → `nexus_rondas_avulsas · fato_ronda_avulsa` | a cada lançamento; a importação, só a pedido | o Nexus é a FONTE (Levi, 07/10). **1 linha = 1 lançamento**: ronda avulsa, nível validado pela foto (`origem = "validacao_foto"`, importado de planilha pelo MESMO caminho de gravação; não é ronda) ou anulação. Desde 08/10 é **fonte** do `fato_ronda` (só a avulsa válida: fora a anulada, a anulação e a validação por foto). Domínio do App desde 08/10, antes da 1ª gravação (decisão 3): vala sem "Suja", sensor em 3 estados, anulação só com `anula_id` (sem `data_id`/`usina_id`). **No banco desde 08/10** (GET em 09/10): a 1ª gravação, a criticidade validada das rondas Thopen, 63 linhas `validacao_foto` (14/08 a 06/10), `usina_id` 63/63 (os 2 nomes com espaço duplo no de-para casam pelo `_espacos` da importação), a pessoa fora do cadastro (`--fora-do-cadastro`: só o nome cifrado, `pessoa_id` vazio) |
| Observação do responsável | `campo/observacao_responsavel.py` → `nexus_observacoes · fato_observacao_responsavel` | a cada observação | o Nexus é a FONTE (Levi, 13/10/2026: "salvo em algum canto do Nexus para posteriormente poder juntar esse comentário para relatórios"). **1 linha = 1 observação de 1 Responsável O&M sobre 1 usina**, escrita na janela da Meta da Visão do responsável. Sem medida; chave `id`; `data_id` = o dia de Brasília em que foi escrita, `mes_id` = o mês da janela. Texto e nome só cifrados (o Cofre, como a avulsa); pessoa por `pessoa_id` + `pessoa_hmac`; `do_responsavel` = sim/não (não = cobria outro, férias). Só responsável escreve, em qualquer usina. Para relatório: `observacao_responsavel.para_relatorio(de, ate)` decifra no Nexus. Registrado em 13/10 antes da 1ª gravação |
| Ocorrências com plano de ação | o Nexus grava (`campo/ocorrencias.py`, tela Campo · App → Ocorrências) → `nexus_ocorrencias · fato_evento_ocorrencia` | a cada ocorrência criada ou mudada, ação do plano e andamento | o **Nexus é a FONTE** (Levi, 18/10/2026: "as ocorrências com plano de ação. siga!"). **1 linha = 1 evento** (`criou`, `dados`, `acao`, `andamento`) sobre 1 ocorrência (`ocorrencia_id`) de 1 usina; sem medida, só acrescenta, o estado sai dos eventos na ordem da gravação (vale a última da ocorrência e de cada ação, pelo `acao_id`). Em claro: `usina_id` (escolhida na tela; `usina_ligada_por` = `tela`, ou `ocorrencia` nos eventos da ação e do andamento), o código canônico do ativo e o `equipamento_id` quando o código está na dimensão (`equipamento_ligado_por`), `pessoa_id` + `pessoa_hmac` de quem fez, `responsavel_pessoa_id` da ação, os códigos de criticidade, status e situação, as datas por papel (`data_id_inicio`, `data_id_fim`, `data_id_prazo`) e o número das OS (`os`, separadas por vírgula). Título, descrição, chamado, texto da ação, andamento, o nome do responsável da ação e quem só cifrados (Cofre). Registrado em 18/10 antes da 1ª gravação, com a trava de livro que só cresce; regras em `nexus/torres/campo/CLAUDE.md` |
| Curadoria do PCM | `pcm/acompanhamento/curadoria.py` → `nexus_pcm_curadoria · fato_decisao_curadoria` | a cada carga (`ferramentas/carregar_curadoria_pcm.py`; a tela de edição vem depois) | o Nexus é a FONTE (Levi, 14/10/2026, com o painel de acompanhamento do PCM O&M: "Quero que libere na seção de PCM essa visão de acompanhamento"). **1 linha = 1 decisão da reunião de PCM sobre 1 MPA/MPS acompanhada** (`item_id` = sha1 de tipo, usina e OS) ou sobre a regra do responsável da Manutenção (`item_id` manutencao). Sem medida; só acrescenta, vale a última de cada item; `ativo` "não" tira o item. O conteúdo (usina, OS, responsável, o que falta, observação) vai só CIFRADO em `dados_cifrados` (o Cofre, contexto `pcm/curadoria/<item>`); em claro só item, tipo e grupo. As pendências e o progresso não são guardados: o Acompanhamento recalcula pelo `gestao_pcm.json`. Registrado em 14/10 antes da 1ª gravação |
| Motivos das tarefas do PCM e o backoffice | `pcm/motivos.py` → `nexus_pcm_motivos · dim_motivo`, `fato_decisao_motivo`, `fato_decisao_backoffice` | a cada marca (Quadro da semana, Fora da programação), cadastro e lista do backoffice (Gerar a semana) | o Nexus é a FONTE (Levi, 16/10/2026: os 11 motivos, o painel das tarefas que saíram da programação e "Quando a OS estiver atrelada como responsável para alguém do time de backoffice, desconsiderar para a programação da semana"). `dim_motivo`: 1 linha = 1 motivo do cadastro (`tira_da_programacao` sim/não; excluir marca `excluido = sim` e o ID não volta; `etiqueta_fracttal`, no fim desde 19/10/2026: o nome da etiqueta do Fracttal que o App põe na OS quando o técnico justifica com o motivo). `fato_decisao_motivo`: **1 linha = 1 decisão sobre o motivo de 1 tarefa** (OS + código do ativo + nome, `item_id`; motivo vazio = tirou), sem medida, só acrescenta, vale a última de cada tarefa (um motivo por tarefa). `fato_decisao_backoffice`: 1 linha = 1 decisão de pôr ou tirar 1 nome (`nome_hmac`). Em claro só a OS, o código do ativo, o `equipamento_id`, o `tarefa_chave` (a conta da programação e do fechamento) e os códigos de quem decidiu; a tarefa, a usina, a observação e os nomes só em `dados_cifrados` (Cofre). As três abas vão juntas a cada gravação, sobre o livro relido. O estado vai ao `Fora_da_programacao.json` do repositório do PCM (público: sem observação nem quem marcou; os nomes do backoffice em claro, decisão do Levi) e à pasta de cada rodada do motor. Registrado em 16/10 antes da 1ª gravação; regras no `nexus/pcm/CLAUDE.md` |
| Técnicos por usina | `pcm/atribuicoes.py` → `nexus_pcm_atribuicoes · fato_decisao_atribuicao` | a cada decisão (tela Técnicos por usina do PCM) | o Nexus é a FONTE (Levi, 17/10/2026: "cria uma estrutura que liga usina e técnico e o PCM pode editar a vontade"). **1 linha = 1 decisão de pôr ou tirar 1 pessoa de 1 usina num papel** (`executa`: quem vê e pode rondar a usina no App de Campo); sem medida, só acrescenta, vale a última de cada usina × pessoa × papel; o apoio pelas datas (`de_data_id`, `ate_data_id`). `usina_id` e `pessoa_id` do cadastro, mais o `usina_fracttal` e o `pessoa_hmac` (o que o App usa para achar a usina e a pessoa); a observação só cifrada; cada linha assinada (o App só aplica a assinada). A foto do App, `organizacao_app_campo · Atribuicoes`, está em `CONHECIDAS` (apoio, para a comparação antes da troca). Registrado em 17/10 antes da 1ª gravação; regras no `nexus/pcm/CLAUDE.md` |
| Contestação do cliente | o 5080 grava (`thopen/contestacao_banco.py` da plataforma) → `thopen_contestacoes · contestacoes`; o Nexus lê em `contratos/contestacoes.py` | a cada contestação | o **5080 é a FONTE** (Levi, 13/10/2026: "contestação ligada ao Nexus"; "ficaria na API do PG"). **1 linha = 1 contestação × 1 setor** (Performance, COS desde 15/10, Zeladoria: as mesmas mensagens do Teams); chave `id`, `contestacao_id` junta as duas; papéis de data `data_id_recebida`, `data_id_contestada_ini/_fim`; `usina_id` do de-para (vazio com dois ids). Nome, contato, mensagem e o que o cliente via só em `dados_cifrados`, com cifra **assimétrica** (X25519 + AES-GCM): o 5080 tem só a pública e não abre nada; o Nexus abre com `NEXUS_CONTESTACAO_CHAVE_PRIVADA` (colada em Base → Chaves do Nexus desde 14/10, sem a T.I.; ou no .env). Registrado em 13/10 antes da 1ª gravação; **no banco desde 13/10** (a 1ª, TESTE, 2 linhas, conferida pela API aberta: nada em claro) |
| Acompanhamento da contestação | o Nexus grava (`contratos/tratamento.py`, tela Contratos e clientes → Contestações) → `nexus_contestacoes_tratamento · fato_tratamento_contestacao` | a cada "Pegar para mim" e a cada atualização | o **Nexus é a FONTE** (Levi, 15/10/2026: "Pegar para mim" e as atualizações do responsável com data e hora). **1 linha = 1 evento** (`responsavel` ou `atualizacao`) sobre 1 contestação × 1 setor (`contestacao_linha_id` = o `id` do `thopen_contestacoes`); o responsável é o do último `responsavel`, pela ordem de gravação. Quem e o texto só cifrados (Cofre); a pessoa pelo `pessoa_hmac`. Só acrescenta. Registrado em 15/10 antes da 1ª gravação |
| Acompanhamento dos ativos da Engenharia | o Nexus grava (`engenharia/acompanhamento.py`, tela Engenharia → Confiabilidade) → `nexus_engenharia_acompanhamento · fato_acompanhamento_ativo` e `dim_diagnostico` | a cada pegar, encaminhar, salvar e comentário, e a cada mudança no cadastro dos diagnósticos | o **Nexus é a FONTE** (Levi, 18/10/2026: "os membros de engenharia ou administradores pegar aqueles ativos com sinal para acompanhar ou alguém da engenharia poder encaminhar para a pessoa ver!"). **1 linha = 1 evento** (`pegou`, `encaminhou`, `dados`, `comentario`, `encerrou`) sobre 1 acompanhamento (`acompanhamento_id`) de 1 ativo; transação, só acrescenta, o estado sai dos eventos na ordem da gravação. Em claro: o código canônico e o `equipamento_id` do ativo, o `usina_id` (a ligação da Confiabilidade, com `usina_ligada_por`), `pessoa_hmac` e `responsavel_hmac`, o `diagnostico_id` e as datas por papel (`data_id_inicio_analise`, `data_id_fim_analise`); medidas só no evento que começa (a foto do sinal: `falhas_30d_qtd`, `falhas_7d_qtd`, e o `nivel_na_entrada`). Quem, o nome de quem acompanha e o comentário só cifrados (Cofre). `dim_diagnostico` é o cadastro (como o `dim_motivo` do PCM: excluir marca `excluido = sim` e o ID não volta; o inicial, Comunicação e Disjuntor, entra com a 1ª gravação). As duas abas vão juntas, sobre o livro relido. Registrado em 18/10 antes da 1ª gravação; regras em `nexus/torres/engenharia/CLAUDE.md` |
| Contas dos clientes no Dashboard Thopen (livro, não fato) | o Nexus grava (`contratos/acessos_clientes.py`, tela Contratos e clientes → Acessos dos clientes) → `nexus_acessos_clientes · dim_conta_cliente`; o 5080 lê a cada 2 min (`thopen/acessos.py` da plataforma) e grava as senhas em `thopen_acessos · senhas` (em `CONHECIDAS`, apoio) | a cada ação na tela | login por pessoa (Levi, 14/10/2026). O **Nexus é a FONTE das contas**, o **5080 das senhas**: um livro por sistema que grava, nenhum sobrescreve o do outro. **1 linha = 1 conta** (o estado atual; trocado inteiro sob a trava, relido antes, conferido depois). Nome e e-mail só cifrados, duas vezes: `dados_5080` selado para a pública do painel (`NEXUS_ACESSOS_5080_PUBLICA`; contexto `nexus_acessos_clientes/<conta_id>/dados_5080`) e `dados_nexus` no Cofre (a chave do cadastro). O link de definir senha só como sha256 (`convite_hash`, 72 h, uso único: o 5080 marca usado pela linha de senha com o mesmo hash). Quem mudou só como HMAC. A senha é hash scrypt cifrado com a chave do painel (`cs1:`). Registrado em 14/10 antes da 1ª gravação; **no banco desde 14/10** (a conta TESTE do ensaio, conferida pela API aberta: nada em claro; DESATIVADA no fim do ensaio) |
| Carga | `carga.py` (+ `ferramentas/carregar_dados.py`) | — | de hora em hora, aos :40. Ordem: dimensão de equipamento (antes dos fatos), histórico, fatos; cada peça nova isolada (regra 13). Montar levou 11–14 s em 08/10 (antes 3,6–4,5 s: o tempo novo é ler ~32 mil linhas a mais, sobretudo `campo_nexus` e `de_para_trackers`, e montar a dimensão, ~2,7 s) |
| Tela | `telas.py` (+ `templates/dados/governanca.html`, `_organograma.html`), Base → **Governança de dados** | — | duas visões, a escolha na URL. **Organograma** (o padrão desde 09/10, Levi: "Deixe organograma como padrão, Matriz em segundo"; `?ver=organograma` segue valendo): a raiz com as contas do `resumo()` (+ os de origem), os setores (o `area`, com o nome da torre), os fatos com o estado em palavra e tom e uma linha de para que servem, quem grava cada livro (`LIVROS.quem_grava`, dito "Nexus" no cartão; senão a família do nome em `telas.QUEM_GRAVA_ORIGEM`; família nova aparece "a declarar"), as fontes de outro fato **abertas** no rodapé do setor (estado "fonte", com o que alimentam: os dados são usados, a ligação por ID é feita no fato que elas alimentam), a faixa das dimensões e a gaveta do fato. **Matriz** (`?ver=matriz`): tipo, chave e medidas; as barras de qualidade; a saúde do histórico; a dimensão de equipamento; os livros do Nexus. **O aposentado não aparece em nenhuma das duas** (09/10: "se ele é inútil deixe em sua inutilidade"); continua no catálogo. Tudo do catálogo, nada à mão; prova: `tests/test_dados_organograma.py` |
| Gaveta do fato (09/10) | `_organograma.html`, `telas._cartao`, `explica.py` | — | fala para quem não é da área de dados (Levi: "para o que essa tabela serve, o que ela faz, de onde vem"): a situação numa frase (`ESTADO_FRASE`), **para que serve** (`explica.PARA_QUE`; o cartão usa `explica.RESUMO`), o que cada linha guarda (o grão sem o "1 linha =", e o tipo em `TIPO_FRASE`), de onde vem e quem grava, como se liga (só as dimensões que o fato tem, com a legenda `LIGA_FRASE` dos jeitos que ele usa; as que faltam numa linha), o que dá para medir ("pode somar?") e a qualidade da carga; o técnico (grão, tipo Kimball, chave, observação) fica em "Para quem mantém o dado". **Fato novo sem texto em `explica.py` derruba o teste.** A largura acompanha o conteúdo, de 520 a 940 px: quem manda são as tabelas da gaveta (`.dd-gav-largo`), o texto corrido tem `contain:inline-size` e só quebra (antes: 560 px fixos, a coluna "por onde liga" quebrava em 3 linhas; medido em 09/10 a 1440 px: 520 a 782 px conforme o fato, nenhuma linha quebrada) |
| Radar do banco (09/10) | `radar.py` + `templates/dados/_radar.html` (nas duas visões) e `catalogo.CONHECIDAS` | — | Levi: "verifique se aparece a cada tabela nova que aparece!". **Toda tabela do banco tem dono no catálogo, e a nova aparece sozinha.** O radar compara a listagem do banco (`/api/sheets`) com o catálogo e põe cada aba numa caixa: **fato** (fonte ou destino de um fato, ou aba de livro do Nexus no `LIVROS`), **usina** (aba de usina dos livros "1 aba por usina", visível e não declarada), **conhecida** (`CONHECIDAS`: aba por aba, com o papel — dimensão, controle, apoio, candidata a fato, aposentada, teste — e o porquê) ou **nova** (nenhuma delas: contada no alto do organograma, em vermelho, com a gaveta dizendo o que fazer; as linhas, só para administrador). A aba de livro do Nexus fora do `LIVROS` é nova (regra 10 furada): foi assim que o radar achou a `nexus_rondas_checklist · qualidade`, no banco desde 06/10 e fora do `LIVROS` até 09/10. 1ª medida (09/10, banco real): 452 tabelas, 31 de fato, 152 de usina, 269 conhecidas (197 delas do livro de teste e do coletor aposentado, que só entram na conta) e **0 novas**. Limite: aba nova e visível no BD_Thopen/BD_Performance conta como de usina (saber se é de geração pede o cabeçalho, uma leitura por aba); se não for, a prévia recusa as linhas e ela deve ser declarada em `CONHECIDAS` |
| Tabela, só para ler (09/10) | `previa.py` + `templates/dados/_tabela.html`, rota `/t/base/governanca/tabela?fato=&t=&aba=&ini=` | — | o botão de tabela ao lado do X abre à esquerda da gaveta a tabela de verdade (Levi: "importante para os stakeholders entenderem o funcionamento e quais dados estão sendo salvos"). **Só tabelas do catálogo**: o livro do Nexus (`conformado_em`) e as fontes do fato; a URL só leva o fato e o número da tabela na lista, nunca nome de livro; a aba de usina (BD_Thopen/BD_Performance, "1 aba por usina") é a visível que o catálogo não declara como outra coisa (`CONHECIDAS`) e só mostra linha se o cabeçalho for de geração (`geracao.abas_de_geracao`): a aba "Clientes" não sai. A exceção é a tabela **nova** do radar (`?nova=1&livro=&aba_nova=`): só administrador e só se o radar, relido na hora, ainda a classificar como nova. Lê **só a página** (50 linhas, `rows?limit=&offset=` com o `row_count` da listagem; `trk_eventos` tem 119 mil), abre no **fim da tabela**, na ordem dela, e pagina pela 1ª linha mostrada (Início = 1 a 50); não diz "as mais novas": o `fato_programacao` termina na W38, e-mail vira "[e-mail]". Cache: listagem 5 min, página 2 min. Tabela que ainda não está no banco, fora do banco (o arquivo do PCM) ou vazia diz isso |
| Telas do Campo (passo 4, **feito em 08/10**) | `nexus/campo/visao.py` (`_fato`) + `carga.montar_ronda`, `montar_pt`, `montar_fechamento`, `carga.ligador`, `carga.mapas_das_linhas` | — | Rondas, Central de atenção e PT tiram a contagem e a ligação (`usina_id`, `pessoa_id`, `data_id`) do `fato_ronda`, `fato_pt` e `fato_fechamento`; o livro cru só dá o que o fato não tem, juntado pela chave do fato. Fato do banco da MESMA versão do livro de origem (`qualidade.origem_atualizada_em` = `updated_at`) ou montado NA HORA pela MESMA função da carga, com aviso discreto na tela: uma regra só. Prova (08/10, banco real por GET, 368 páginas antes × depois, 7/14/30 dias): números iguais salvo 3 diferenças da ligação do fato (1 ronda no dia de Brasília do início; 1 resposta da carga única casada pelo Início numa ronda que ganhou OS depois; o nome pela ficha do cadastro, 192 de 874 rondas, sem mudar número); tela quente igual. Detalhe em `nexus/torres/campo/CLAUDE.md` |
| Ler e gravar livros | `livros.py` | — | ler: `ler` (a aba inteira), `abas` (a listagem de um livro) e `pagina` (uma página de `PAGINA` = mil linhas; a que vem com menos é a última); gravar: `publicar`, com a conferência antes e depois (regra 9). Cada `ler` pede a listagem do banco de novo (~0,5 s) e as páginas uma depois da outra: a tela que lê várias abas usa o `visao.carregar` do Campo (UMA listagem e as páginas de todas as abas em paralelo, 19/10/2026; ver `nexus/torres/campo/CLAUDE.md`) |

**Falhas da plataforma com `plant_id` (08/10/2026, Operação no Mês do Dashboard Thopen):** o livro
`falhas_performance` é da plataforma de performance (o Nexus só cataloga; quem consome é o 5080). Contrato: Tasks 1 e 2
e "Rodada 2" de `docs/superpowers/plans/2026-10-08-thopen-operacao-no-mes.md`, no repositório da plataforma (em 08/10
ainda sem push). Coluna nova só no FIM (o BI e o Nexus leem por posição):

- `strings_episodios` e `trackers_episodios` ganham `plant_id`: a usina liga por código. Pelo nome, a Brodowski junta os
  dois cadastros da API PV (uma metade com 52 trackers parados, a outra com 51) e dá 52 em vez de 103. Por isso a chave
  dos episódios é pelo `plant_id`: pelo nome, a do tracker repetia (pacotes do PC, 08/10: 243 chaves em setembro e 132
  em outubro, Brodowski, Fernandópolis, Barretos, Assis; pelo `plant_id`, 0).
- `trackers_episodios` ganha `dias_comunicou` (dias do episódio, no mês, em que a USINA leu string ou gerou) e
  `dias_sem_prova` (dia ainda não fechado e sem prova; volta a 0 quando o dia fecha).
- Abas novas: `cobertura` (fato `cobertura_falhas`, mês × fonte × `plant_id`: separa "sem falha" de "sem
  monitoramento"), `strings_os` (fato `os_string`, 1 linha = 1 OS de recomposição de string do Fracttal pela data do
  evento; `origem` texto, citadas, estimado ou sem_quantidade; `qtd` vazio = sem quantidade, nunca 0) e `trackers_dia`
  (fato `falha_tracker_dia`, usina × fonte × `plant_id` × dia com tracker parado e a usina comunicando; `comunicou` sim
  ou "sem prova"). A `atualizacao` ganha no fim `cobertura`, `strings_os` e `trackers_dia` (linhas de cada aba no mês).
- 09/10 (rodada 4 do Dashboard Thopen): aba `disponibilidade_dia` (fato `disponibilidade_dia`, 1 linha = usina do
  catálogo do Gerencial × dia fechado; `disp` e `h_perdidas` do índice do Gerencial › Disponibilidade, o 100 do dia sem
  OS escrito) e a coluna `disponibilidade_dia` no fim da `atualizacao`. Liga pelo nome do Gerencial e, sem ele, pelo
  nome do Fracttal no `de_para` — nunca só pelo site: um site do Fracttal pode ser de duas usinas. Desde 15/10/2026
  (Levi): de 10/2026 em diante só as OS do Fracttal, isolada da geração; setembro para trás, a "Disponibilidade Usina
  (%)" do BD_Thopen, só a Thopen, e as abas de OS desse mês ficam sem linha.
- Estado `origem`: nenhum deles tem `usina_id` ainda (pendência 10).

**Janela (é condição, não data):** o workbook leva todos os meses publicados, mas o worker só remonta o mês corrente
(sempre), o anterior até o dia 2 e os mais velhos só se o pacote do mês sumir do cache. Mês montado antes do deploy da
plataforma fica sem os campos novos até ser remontado: `dias_comunicou` e `dias_sem_prova` vazios, nenhuma linha
daquele mês em `cobertura`, `strings_os` e `trackers_dia`, e `atualizacao.cobertura` **vazia** (não 0) — vazio é
**não medido**, nunca 0 nem "sem monitoramento"; com número ali, o `plant_id` sem linha na `cobertura` é sem
monitoramento. O `plant_id` não tem esse buraco (o pacote do mês já o trazia: setembro no PC, 579 de 579 episódios de
string e 6.034 de 6.034 de tracker). Caso de 08/10: setembro, montado pela última vez em 02/10, fica sem os campos
novos; outubro só os tem se a plataforma subir até 02/11. O `dias_comunicou` da `cobertura` é da USINA (nome
canônico), repetido em cada `plant_id` dela: não somar entre linhas; conta de `periodo_inicio` a `periodo_fim` (no mês
corrente, até o último dia montado). As observações da matriz (`catalogo.py`) guardam só a regra; a janela fica aqui.

**O Nexus como fonte (05/10/2026):** a decisão da PT assinada no Nexus (`nexus/campo/decisao_pt.py`) grava
`nexus_pt_decisoes · fato_decisao_pt` (grão: 1 linha = 1 decisão sobre 1 linha da PT, a PT × ativo do `pt_app_campo`).
Já nasce com `data_id`, `usina_id` e a pessoa como HMAC (`decidida_por_hmac`); o motivo vai mascarado (e-mail e número
viram marcador), porque o técnico lê e a API é de leitura aberta. **Decisão 4 do Levi (11/10/2026), o contrato com o
App, que lê este livro:** a PT pelo número e a linha pelo `codigo_ativo` (o Código do ativo daquela linha; vazio na PT
sem ativo, como a da APR do dia), as colunas de 05/10 e o `codigo_ativo` no fim. Antes gravava só o número e pegava a
1ª linha (GR-4: numa PT de 3 ativos não dizia a qual valia); a aba se chamava `decisoes`, nunca foi gravada (o livro não
existe no banco, GET de 11/10) e não é mais lida: linha que aparecer nela (um Nexus velho decidindo antes do deploy)
não vale e o radar a mostra como tabela nova. Sem a linha, a PT de mais de um ativo não se decide (escolher a 1ª seria
chutar, regra 4); a tela dela, sem a linha, só deixa escolher o equipamento, e a ida e a volta do login do Fracttal
levam a linha. **O que o App descarta não se grava** (revisão adversarial de 11/10/2026): o App (v257) aplica só a 1ª
decisão de cada linha, e não a de quem pediu a PT; gravada, essa linha travava aqui e nunca chegava ao campo. Por isso
`decidida_por_hmac` nunca é o `solicitante_hmac` da linha no `fato_pt`, e o primeiro que decide a linha vale. Quem pode
decidir, o App não confere: a trava é do Nexus, antes de gravar. Prova: `tests/test_campo_visao.py` (as decisões) e
`tests/test_dados_camada.py` (o catálogo).

**Fontes do tempo real (11/10/2026):** a tela da plataforma `/admin/tempo-real` (no Nexus, Base · Fontes do tempo real, só
admin) grava `nexus_tempo_real · fato_decisao_cobertura` (grão: 1 linha = 1 decisão de incluir ou excluir 1 usina de 1
fonte; só acrescenta, o vigente é a última de cada fonte e chave). A usina vai pela chave NATIVA da fonte (plant_id da
API PV, código da SunOp, site da SolarEdge, power_plant_id do banco, id do scadaGridco) e o `usina_id` fica vazio até o
plant_id por fonte entrar no de_para (pendência 10). Sem pessoa no banco: quem decidiu fica no log da máquina da
plataforma. Origem `migracao` = a foto do dia em que a fonte passou a ser controlada pela tela. Quem lê é a plataforma (PC
e servidor), com cache de 60 s; a regra e as travas moram no `plataforma/CLAUDE.md` (seção "Fontes do tempo real").
No banco desde 11/10/2026 (conferido por GET).

**De-para de equipamentos (11/10/2026):** a tela da plataforma `/admin/de-para` (no Nexus, Base · De-para de
equipamentos, só admin) grava no livro `nexus_depara · fato_decisao_depara` (`catalogo.py`, sem medida): 1 linha = 1
decisão de ligar 1 usina (id na fonte) ou 1 inversor (id na fonte) ao cadastro, pela chave de negócio do Equipamentos
(Usina Supervisório, Equipamento Supervisório), que a plataforma confere antes de gravar. Vence o de-para em código da
plataforma; livro ilegível = vale o código. Quando o de_para do cadastro ganhar o sistema plant_id (pendência 10), a ponte
da usina migra para lá; a regra mora no `plataforma/CLAUDE.md` (seção "De-para de equipamentos"). No banco desde
11/10/2026 (conferido por GET).

**Vínculo de OS às falhas (20/10/2026):** Levi: "Opção de vincular OS, eu clico no botão e buscas as OSs de
recomposição de string desse inversor" ("faça algo parecido com os trackers!"). Até aqui a falha medida e a OS não se
ligavam em lugar nenhum. A tela da plataforma `/painel/falhas` (no Nexus, Performance · Strings e trackers) grava no
livro `nexus_falhas · fato_decisao_vinculo_os` (`catalogo.py`, sem medida, só acrescenta), pela mesma
`cobertura.Decisoes` dos dois livros acima: 1 linha = 1 decisão de vincular ou desvincular 1 OS do Fracttal a 1
ocorrência de string (o inversor) ou 1 parada de tracker; o vigente é a última decisão de cada (tipo, fonte, plant_id,
equipamento, data_id_inicio, os). Colunas: `decidida_em`, `data_id` (o dia de Brasília da decisão), `tipo`
(`strings`/`trackers`), `fonte` e `plant_id` (os dos episódios das falhas; a usina liga quando o de_para ganhar o
plant_id, pendência 10), `equipamento` (o inversor ou o tracker como a tela os nomeia, sem `equipamento_id`: regra 4),
`data_id_inicio` (o dia em que a falha começou, AAAAMMDD: a 2ª data vai como papel, regra 7; com tipo, fonte,
plant_id e equipamento, a chave de negócio dela), `os` (o
número: dimensão degenerada), `decisao` (`vincular`/`desvincular`) e `origem` (`tela`, a OS da busca no ativo; `forcado`, o número digitado à
mão no "Forçar vínculo" desde 22/10/2026, que pode não ser do ativo). Sem pessoa nem texto livre
(regra 8): quem vinculou fica no log da máquina da plataforma (`logs/falhas_vinculos.log`) e a descrição da OS não vai.
É daqui que a tela mostra a OS vinculada sem pedir nada ao Fracttal (a busca lá só acontece no clique em Vincular OS);
quem lê é só a própria plataforma (PC e servidor, cache de 60 s). Registrado em 20/10/2026 antes da 1ª gravação (regra
10): nasce no 1º vínculo. A regra mora no `plataforma/CLAUDE.md` (Strings e trackers, Vincular OS).

**Setor do pessoal (12/10/2026):** Levi: "Como faço para definir um setor???? tem que dar possibilidade". O Fracttal não
diz o setor de ninguém e ainda não há base, então a lista nasce no Nexus: a tela Base · Integração Fracttal (só admin)
grava o livro `nexus_setores` (`nexus/cadastro/setores.py`), com `dim_setor` (1 linha = 1 setor; excluir marca
`excluido = sim` e o ID não volta) e `fato_decisao_setor` (1 linha = 1 decisão de pôr 1 pessoa do Fracttal num setor, ou
de tirá-la; só acrescenta, vale a última de cada pessoa). O setor é atributo da **pessoa** (como a região de campo é da
equipe), não uma dimensão à parte. A pessoa vai pelo `fracttal_id` (o id_personnel, o mesmo `tecnico_id` do coletor do
Campo), pelo `pessoa_id` quando tem ficha (critério do login, `pessoa_ligada_por`) e pelo `pessoa_hmac`; nome e e-mail
nunca (regra 8). As duas abas vão juntas a cada gravação (gravar sem uma a apagaria), sobre o livro relido do banco na
hora (leitura que falha não grava). Registrado antes de existir: nasce com o 1º setor criado na tela.

**Estrutura das usinas (13/10/2026):** a tela Base · Equipamentos das usinas (só admin) grava o livro
`nexus_estrutura_usina` (`nexus/cadastro/estrutura_usina.py`): `dim_supervisorio` (1 linha = 1 chave do supervisório
ligada a 1 usina; a chave é de uma usina só), `dim_cabine` (1 linha = 1 cabine da usina, com kWp) e `dim_inversor` (1
linha = 1 inversor da usina: a chave por onde chega, a cabine, kWp, strings esperadas e o `equipamento_id` do ativo do
Fracttal). É a estrutura física da USINA, hierarquia da mesma dimensão (usina → chave, cabine, inversor), e não um
segundo cadastro de equipamento: o inversor aponta a dimensão de equipamento pelo `equipamento_id`. Estado atual (troca
integral relida do banco antes de gravar), ID = maior + 1 que não volta, `excluido = sim`, quem mudou só como HMAC.
Substitui no Nexus a aba Equipamentos do `bd_performance`, que segue como referência. A 4ª aba, `aba_equipamentos`
(exceção à regra 10, declarada em `ABAS_FORA_DA_REGRA`), é a VISÃO no formato da aba Equipamentos das chaves marcadas "no
lugar da aba", refeita a cada gravação: os leitores antigos da aba (a plataforma, o gêmeo, as Ligações e o coletor,
quando ligado nele) trocam as linhas dessas chaves por ela. Registrado antes de existir: nasce com a 1ª chave ligada na
tela. **Segundo caminho de gravação (20/10/2026): o de-para do tempo real** (o "Modo de-para" da plataforma, pelas rotas
JSON da tela, `estrutura_usina.salvar_depara`; regras em `nexus/cadastro/CLAUDE.md`), um remendo que liga o ativo do
Fracttal ao inversor e à cabine e recalcula o kWp pela regra do Levi (a chave que o livro não tem nasce semeada pela
aba, a chave fora da aba e do livro é recusada, e só passa a valer no lugar da aba a que difere dela apenas pela regra,
com as outras chaves da mesma usina juntas: a usina vale por inteiro ou nada, 21/10; nunca vazio por cima do kWp
gravado). Por
ele vieram três colunas no FIM das dimensões
(como o `banco.COLUNAS_NO_FIM`; a linha de antes lê vazio), a linhagem da regra 5: `potencia_regra` no `dim_cabine` e no
`dim_inversor` (`real_por_string`, `contratual_por_string`, `informada`), `fracttal_ligado_por` (`conferido`,
`sugestao`) e `conferido_em` no `dim_inversor`, com as listas em `dominios.py`. O `equipamento_id` do inversor e da cabine
é derivado do código e o código tem de ser membro da `dim_equipamento` (regra 4: até 20/10 o Salvar aceitava o ID que
viesse no pedido). A visão ganhou o "Código Fracttal" (inversor e UG) depois dos IDs. Livro, não fato: o histórico das
conferências é o histórico por linha da API; fato próprio (`fato_decisao_conferencia`) só se o Levi pedir.

**Meta do mês por usina (12/10/2026):** para a Visão do responsável (Campo · App; Levi: "construa a visão dos
responsáveis da usina!"), a plataforma publica o Gerencial no livro `nexus_performance · fato_meta_usina_mes`
(`catalogo.py`, foto acumulada, chave `mes_id` + `usina`): 1 linha = 1 usina do Gerencial × 1 mês, com produção e meta em
kWh (regra 3: o Gerencial mostra MWh), atingimento, PR e PR previsto, IPOA e os dias cobertos. Quem grava é o worker do
servidor (`plataforma/gerencial_publicar.py` + `_ger_publicar` no app.py), de hora em hora e só quando o mês muda; o mês
corrente se refaz até fechar e o anterior até o dia 5. O nome da usina é o do Gerencial (origem: a Visão do responsável
liga pelo de-para das abas e pelo nome do cadastro, na hora). Sem pessoa nem texto livre (o motivo do PR sem confiança
fica de fora). Registrado antes de existir: nasce na 1ª volta do worker depois do deploy da plataforma.

**As OS da disponibilidade (12/10/2026):** a plataforma publica com o diário da disponibilidade o
`falhas_performance · disponibilidade_os` (`plataforma/falhas_publicar.py`, `_disp_os_linhas`): 1 linha = 1 OS × 1 usina
do escopo, no mês, lido pela janela de Disponibilidade da Visão do responsável. **O `perda_kwh` é a perda da OS NAQUELA
usina** (13/10/2026: o `kwh_usina` do índice da Disponibilidade da plataforma), pela régua do Gerencial (kWp afetado ×
horas de sol, sem a irradiação; só o Fracttal, a geração não entra desde 15/10/2026): as linhas de uma usina somam a
perda dela no Gerencial, e a usina do escopo em que a OS não perdeu nada fica com 0. Antes era a perda da OS repartida
pela potência, que errava quando o teto de 100% pegava uma e não a outra (e, até 15/10, quando a geração desmentia o
dia numa usina só) (setembro: 47.893
kWh na usina errada entre Rodrigues 1 e 2; outubro: ~2,5 MWh na Boa Esperança do Sul 1 e 2 e ~5,2 MWh na Rodrigues). O
índice publicado antes do campo ainda reparte pela potência. Mudou a regra lá, muda a `observacao` do catálogo junto.

**A parcela de cada OS em cada dia (14/10/2026):** `falhas_performance · disponibilidade_os_dia` (fato
`disponibilidade_os_dia`, `plataforma/falhas_publicar.py`, `_disp_os_dia_linhas`): 1 linha = 1 OS × 1 usina × 1 dia em
que ela tirou disponibilidade, com os trechos das 06–18 h em que foi dona da perda e as horas equivalentes. Sai da MESMA
varredura da `disponibilidade_dia` (`disponibilidade._varrer`): as linhas de uma usina num dia somam o `h_perdidas` dela
(provado no índice real de 14/10: 1.203 dias-usina com perda em setembro e outubro, todos fechando). O Dashboard Thopen
escreve com ela o comentário de cada dia (Levi, 14/10/2026: "A partir de outubro quero os comentários 100% OS Fracttal.
Comentários e disponibilidade!"). Índice de antes do código conta VAZIO na `atualizacao` (não publicada), nunca 0.

**Chamados de garantia (12/10/2026):** Levi: "O nexus é um ambiente centralizado e precisamos ter os dados se
conversando!". O Nexus publica as OS de acompanhamento de chamado do Fracttal (o quadro Acompanhamento de chamados do OS
Creator) no livro `nexus_chamados · fato_chamado` (`fato_chamado.py`, conformado, foto acumulada, chave `os`): 1 linha =
1 OS de acompanhamento em processo, em verificação ou concluída nos últimos 90 dias, com `data_id_abertura`,
`data_id_fim`, `usina_id` (de-para do Fracttal pelo site; código do ativo) e `equipamento_id` (o código na dimensão de
equipamento), com a linhagem, o fabricante e o componente da marca da nota e a `duracao_min` da concluída. Quem grava é
`nexus/campo/chamados_acompanhamento.py`, FORA da carga de hora em hora (aquela não toca no Fracttal): aos :50, uma
máquina por vez (a última gravação do livro tem de ter mais de 50 min); `NEXUS_CHAMADOS_PUBLICAR=0` desliga. O REST não
traz a subtarefa do ticket: "aguardando ticket" × "com o fabricante" fica só no quadro. A Visão do responsável lê daqui
(até 12/10 contava pela planilha de tickets). **A OS retroativa (20/10/2026):** a criada à mão para um chamado que já
existia traz na nota a "Data da ocorrência / abertura do chamado"; o `data_id_abertura` e a `duracao_min` contam dela
(Levi: "A abertura do chamado"), se for data de verdade e não depois da criação da OS, e `abertura_por` diz `nota` ou
`os` (linhagem, regra 5). A 1ª, de um chamado de 21/08, entraria com 0 dias.

**As tarefas das OS do Fracttal (18/10/2026):** Levi: "pegando tudo do Fracttal ou Nexus, sem fontes externas!". As
telas do PCM leem as tarefas do `gestao_pcm.json` que o robô do PCM regrava no GitHub dele; para a Visão do responsável
(bloco Manutenção) o Nexus lê o Fracttal ele mesmo, no livro `nexus_os · fato_tarefa_os` (`fato_tarefa_os.py`,
conformado, foto periódica, chave `fracttal_tarefa_id`): 1 linha = 1 tarefa de OS em processo ou em verificação, e a
zeladoria finalizada nos últimos 90 dias, com `data_id_criacao`/`_programada`/`_fim`, `usina_id` (de-para do Fracttal pelo
site; código do ativo), `equipamento_id`, o tipo, o status da OS, o estado da tarefa, `tarefa_chave` (a mesma conta da
programação e dos motivos) e `do_backoffice` (1/0: o HMAC do responsável da OS contra a lista do PCM; o nome nunca vai).
Quem grava é `nexus/campo/tarefas_os.py`, fora da carga de hora em hora: cada máquina no :10 mais um atraso sorteado
de até 10 min, uma por vez (mais de 50 min desde a última, conferido também logo antes de gravar: a leitura leva ~2 min),
`NEXUS_OS_PUBLICAR=0` desliga; lê o banco ANTES do Fracttal (se o banco cai, a cota não se gasta). Leitura incompleta
não grava: página recusada 3 vezes, mais de 150 páginas, resposta sem a lista ou com `success: false`, página repetida
ou a leitura abaixo do total que o REST informa (`limit=1`; a sonda de 18/10 mostrou que a página depois da última vem
com `data: None`, e é o total que separa o fim do corte). Até 1% do total pode faltar (a OS que muda de status durante a
leitura pula as linhas dela numa borda de página): fica no `faltaram` da qualidade. E não grava o que sairia chutado
(`recusou`): sem a `NEXUS_PESSOA_HMAC` ou a lista do backoffice (o `do_backoffice` iria 0 para todas), com a usina ou o
de-para do cadastro vazios, ou com menos de 90% das tarefas ligadas a uma usina. Grava também a `qualidade` do livro
(`linha_qualidade`), que a Governança lê.
**O radar da usina trocada (20/10/2026):** o programador do PCM viu a OS de "Apolo - Iramaia II - BA" como Ibipeba no
App e no programador. Os ativos ficam na localização de Iramaia II, mas a Classificação 1 deles (a usina do robô do PCM,
do App e do `Ligador` daqui, que liga primeiro por ela) dizia Ibipeba: 21 dos 29 ativos de Iramaia II com tarefa, na foto
de 15/10. A mesma linha do REST traz os dois (`groups_1_description` e `parent_description`, cujo 2º trecho é a usina):
`fato_tarefa_os.radar_usina_trocada` liga cada nome ao Registro mestre pelo de-para (`Ligador.usina_do_fracttal`) e
separa "trocada" (usinas diferentes) de "conferir" (nomes diferentes, um sem de-para). A grafia diferente da mesma usina
não entra, e o que tem "teste" também não. Ele não muda a usina do fato: só mostra. Vai no `extra` da qualidade: as
contagens `usina_trocada_ativos` e `usina_a_conferir_ativos`, e a lista `usina_trocada` (até 30 ativos e 10 OS por par).
A Governança mostra o quadro "Ativo com a Classificação 1 de outra usina", para quem administra o Fracttal corrigir na
origem: o Nexus não escreve no Fracttal. O robô do PCM relê o cadastro dos ativos a cada rodada na nuvem (o cache não
fica entre as execuções), então a correção chega ao App em até ~30 min. Na foto de 15/10 havia 10 pares e 217 ativos;
duas eram trocas de verdade (Ibipeba × Iramaia 2, Tucano 1 × Tucano 2), e as outras, grafias da mesma usina. Prova:
`tests/test_dados_tarefa_os.py::test_radar_da_classificacao_1_de_outra_usina` e
`tests/test_dados_camada.py::test_governanca_mostra_a_classificacao_1_de_outra_usina`.
**1º ensaio (18/10/2026, ~02:50, só GET, `ferramentas/ensaio_tarefas_os.py`):** 89 páginas em 118 s (status 1: 29;
status 2: 59; zeladoria finalizada: 1); 8.737 tarefas, nenhuma repetida, nenhuma fora do domínio; usina ligada 98,6%
(de-para 8.367, código 251), equipamento e data programada 100%; 65 do backoffice. Os tipos no REST: Preventiva 4.180,
Handover 1.125, Corretiva 898, Religamento 856, Inspeção 729, Administrativa 464, Corretiva Emergencial 302, Religamento
Remoto 121, Zeladoria 62 (a grafia "Zeladoria" do filtro confere). Sites sem usina (consertar no de-para do cadastro):
Apolo Rio do Peixe 1 e 2 (48), Apolo Gravatá 2 (29), Apolo Ibipeba (21), Solier Cascavel (9), Apolo Iramaia 2 (8),
"Grid Co." (2). Contra o `gestao_pcm.json` das 01:42 (sem exclusão dos dois lados, Data Programada desde 01/01):
abertas 2.236 × 2.218 e atrasadas (mais de 10 dias) 1.073 × 1.071. As diferenças: Colíder 1 e 2 (22 abertas) caem em
"sem usina" do lado do PCM (o arquivo dele dá a usina pelo nome atual do ativo, e o nome não liga pelo de-para);
Brodowski, 42 × 26 abertas com as atrasadas iguais (3 × 3): provavelmente OS nova depois do arquivo do PCM (o ensaio
é de uma hora depois e nenhuma das 16 a mais está atrasada); não conferido OS a OS. Das 2.236 abertas, a Visão tira 56 do backoffice, 19 com motivo, 23 de chamado e 17 de zeladoria; Teste, 0.
**No banco desde 18/10/2026 (~10:45):** a 1ª gravação, à mão (`--gravar`, com o OK do Levi), já com a leitura
conferida contra o total do REST: 92 pedidos ao Fracttal (3 totais e 89 páginas), 8.746 tarefas gravadas e as mesmas
8.746 relidas por GET depois de gravar, nenhuma faltando, 119 sem usina (98,6% ligadas).

**Carga única do checklist das rondas sem OS (06/10/2026).** Levi: "Atualize o banco de dados com essas rondas passadas
sem OS, mas não será rotina". A ronda sem OS não tem o texto da OS no Fracttal; as respostas só existiam no registro da
ronda no App, exportadas UMA vez (pela conta do Levi; o Nexus não lê o Azure) e gravadas por
`ferramentas/carregar_checklist_rondas_sem_os.py` num livro próprio (o `nexus_fatos` é regravado a cada hora). Ronda
sem OS depois de 06/10 não entra ali.

**Endereços das telas (porta única, 09/10/2026).** O Nexus pode rodar debaixo de um prefixo (`/nexus` no servidor até a fase 4; hoje na raiz, e o prefixo é a volta): a Governança de dados e
o organograma escrevem os endereços com `{{ raiz }}`/`url_for`/`|na_raiz`, nunca a partir da raiz (cairiam na
plataforma de Performance). Regra em `nexus/casca/CLAUDE.md`; o esquecimento quebra `tests/test_prefixo.py`.

## As regras (valem para todo dado novo)

1. **Grão e tipo escritos antes de tudo** ("1 linha = …"; transação, foto periódica, foto acumulada ou sem medida).
   Fonte larga (um inversor por coluna, como o BD_Thopen) vira linhas antes de entrar. Fonte que mistura grãos são
   dois fatos (o PCM põe execução `foraDoPlano` na semana do plano: ficou fora da programação).
2. **Dimensão é uma só.** Mestres: `cadastro_nexus` (usina, cliente, equipe, pessoa, a região de campo da equipe, aba
   `regioes_campo` da estrutura de O&M de 10/2026, e o `de_para` com o que cada
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
9. **Conferir antes e depois de gravar:** `livros.publicar` relê cada aba e compara a contagem; diferença é erro. ANTES
   de trocar um livro que só cresce (`Livro.so_cresce` no catálogo: as abas que nunca encolhem; `True` = todas), ele
   recusa (`GravacaoRecusada`, nada gravado) a listagem incompleta, a aba declarada no catálogo que sumiria (a
   desconhecida, como a antiga `decisoes` das decisões de PT, sai como sempre saiu) e a aba que encolheria (Levi,
   18/10/2026: "Proteger os livros do Nexus de gravar sobre leitura vazia"). Sem ficar cega: o livro que não veio na
   listagem de livros mas tem abas listadas é recusado (antes era "criado" e trocado), e sem o `sheet_count` e sem
   nenhuma aba listada também (o 0 dito pelo banco, livro criado e nunca gravado, segue). O caso que motivou: a gravação troca o livro
   inteiro; se a listagem do banco omitir as abas por um instante, quem relê recebe vazio e a troca apagaria o histórico
   para sempre. A conta usa o `sheet_count` do livro e o `row_count` de cada aba (medido em 18/10: o `row_count` é o que
   a leitura devolve). Ligado nos 14 livros dos módulos que só acrescentam (setores, telas por setor, dono dos
   relatórios, estrutura das usinas sem a `aba_equipamentos`, que é visão, decisão da PT, observação do responsável,
   ronda avulsa, contas dos clientes, Contestações, curadoria, técnicos por usina, motivos do PCM, o acompanhamento da
   Engenharia e as ocorrências com plano de ação). O `nexus_falhas` (20/10/2026) também declara, porque a aba só cresce,
   mas quem grava é a plataforma, pela `cobertura.Decisoes`, que não passa pelo `livros.publicar`: lá a declaração não
   liga trava nenhuma; a `Decisoes.acrescentar` tem a dela desde 20/10/2026 (livro que existe e relido vazio ou menor
   que a última leitura boa não é gravado; vale também para o `nexus_tempo_real` e o `nexus_depara`). A carga de hora em hora fica sem trava: encolhe de propósito, pela janela da fonte. A trava não
   vê a troca com a mesma contagem: o módulo que põe uma lista de partida no lugar da aba que veio vazia confere antes
   com `livros.existe` que o livro ainda não existe (o acompanhamento da Engenharia confere; os motivos do PCM, com o
   `dim_motivo` de 12 linhas, ainda não, 18/10/2026). Prova: `tests/test_dados_livros_trava.py`.
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
   `janela_origem`) e, se for livro novo, em `LIVROS` (com `so_cresce` quando o módulo só acrescenta: regra 9); e o
   "para que serve" em `explica.py` (`RESUMO` e `PARA_QUE`; o
   teste cobra). A tela já passa a mostrar a lacuna. Tabela que não é fato (cadastro, controle, apoio de outro sistema)
   entra em `CONHECIDAS`, com o porquê. Sem isso, a tabela aparece como **nova** no radar da Governança.
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
- **Programação (decisão 7 resolvida em 08/10: mescla por semana):** a semana que sai do arquivo fica no banco como
  estava na última leitura. Herda: a semana que o arquivo ainda traz é trocada INTEIRA, inclusive se o robô a regerar
  depois de fechada (a W35 em 31/08 mudou 105 tarefas de dia ou hora) ou a publicar pela metade; recusar isso é o
  passo 1. A semana fechada perde, de propósito, o bloco da OS cancelada depois (o robô tira; é o que o painel mostra:
  W40 1.112 → 808 blocos, 304 de 19 OS que não estão mais no `gestao_pcm.json`). A semana ATIVA é um retrato do meio
  dela (medido em 09/10 no git do PCM): à noite a "Rolagem" tira da agenda o que não coube no dia (vai às pendentes, que
  não entram no fato) e o robô só refaz a semana pelo plano publicado quando ela fecha (W40: 858 → 1.356 chaves em 02/10
  22:10; a W41 gravada em 08/10 tinha 971 das 1.119 publicadas). Quem usa o fato como histórico do motor do PCM
  (`nexus/pcm/historico_banco.py`) toma o plano publicado da semana que não tinha fechado na gravação.
- **Geração:** a fonte guarda tudo, mas aba regravada menor encolhe o fato (`geracao.encolhidas` só mostra). O inversor
  × dia (~29–36 MB/dia de xlsx) não cabe em troca integral. Uma publicação antiga do de-para tiraria os sistemas de
  aba e zeraria o `usina_id`.

## Pendências, em ordem

0. **Passo 0** (carga incremental, nunca encolhe) — **adiado pelo Levi em 08/10**.
1. **Passo 1** (um dono só do cadastro, desligar a carga do PC, reler o cadastro, recusar carga encolhida) —
   **adiado pelo Levi em 08/10**.
2. **Passo 2 — técnico das rondas em HMAC:** o pacote do App está pronto (`C:\GridcoBuild\app-campo-docs\_propostas\
   rondas-tecnico-hmac\LEIA.md`: 'Técnico' vira 'Técnico (HMAC)', e o erro da 'Situação da OS' deixa de citar o nome).
   O `fato_ronda` já lê o HMAC primeiro. **Lado do Nexus feito em 08/10** (vai ao servidor ANTES do App): a tela
   (`campo/visao`), a fonte das regras copiadas (`campo/fonte_pg._do_app("rondas")`) e `campo/livros_app.ronda` aceitam
   `Técnico` e `Técnico (HMAC)`, inclusive no mesmo livro (`livros_app.nome_do_tecnico`); sem `NEXUS_PESSOA_HMAC` a
   tela diz que falta a chave. Falta: o cadastro receber as 4 pessoas de ronda sem ficha; o App publicar o pacote
   depois do deploy do Nexus; o pedido à T.I. para apagar o histórico por linha da aba 446. **2b (08/10):** os nomes
   de técnico e supervisor saíram dos arquivos versionados do repositório público (`tests/test_sem_nomes_no_repositorio.py`
   guarda); o histórico do git continua com eles (não se reescreve).
3. **Passo 3 — feito** (`fato_ronda`, `fato_pt`, `dominios.py`). A (1), o checklist das rondas com OS, foi **decidida e
   feita em 09/10** (Levi: "faz meu mano"): o App manda as respostas na própria linha do `rondas_app_campo` (v249 do
   App, colunas novas no fim, com e sem OS) e o `fato_ronda` as lê com `checklist_fonte = app`, que vence a carga única
   (`fato_ronda.APP_CHECKLIST`; linha sem resposta, de antes da v249, segue com a carga única). Decisões do Levi que
   faltam: (2) chave durável de quem só vem por nome (`fato_ronda.codigo_do_nome`, pronto e desligado); (4) quem são as
   6 contas Admin (decisor 0%). A outra metade da (4), a decisão da PT do Nexus por ativo ou pela PT inteira, foi
   **decidida em 11/10**: por linha, como o App (`fato_decisao_pt` com o `codigo_ativo`, "O Nexus como fonte" acima). A
   (3), a avulsa antes da 1ª gravação, foi **feita em 08/10** (vala do App, sensor em 3 estados, anulação sem
   `data_id`/`usina_id`).
   Falta para a 1ª gravação da validação por foto: a ficha de quem validou no cadastro (e o de-para do Fracttal, se
   as 2 usinas com espaço duplo devem entrar).
4. **Passo 5 — feito** (SCD2). Falta: decisão 5 (aceitar o início presumido), HIST-4 (o fato é rechaveado pelo cadastro
   atual) e HIST-6 (tipo 2 para capacidade, mantenedor e eletricista).
5. **Passo 6a — feito** (dimensão de equipamento). A foto foi **gravada em 11/10/2026** (`python
   ferramentas/carregar_ativos_fracttal.py "<deploy-os-creator-web>\os_creator\assets_cache.json"
   "<oem>\os_creator\assets_cache.json" --gravar`; GET: 22.357 linhas) e o ID tem 49 bits (13 hex >> 3, no máximo 15
   dígitos, decidido em 08/10). Falta: renovar a foto (ler o Fracttal, fora do horário de campo); no cadastro, 15
   códigos de usina fora (1.908 membros) e 1 código de usina de dois clientes (170).
6. **Passo 6b — feito** (programação no banco, decisão 7 resolvida em 08/10). A carga única leu as 5.901 versões do
   `banco_dados.json` no git do PCM (clone em `C:\GridcoAuto\nexus\pcm_git`, fora do OneDrive) e, por semana, ficou com
   a ÚLTIMA versão em que ela estava no arquivo; depois de fechada a semana só pode perder bloco (OS cancelada), então
   a versão com bloco que não existia no fim da semana é regeração e não conta (W25: 464 linhas de 19 tarefas em 29/06;
   W35: 105 tarefas mudadas de dia em 31/08; W26 e W27 com OS criadas depois). Prova: as 4 semanas do arquivo, montadas
   pelo git e pelo arquivo (a mesma publicação), deram 0 diferenças; dos blocos que saíram de semanas fechadas, 740 de
   786 são de OS que não estão no `gestao_pcm.json` (canceladas). Exceção: a W29 perdeu 46 blocos de OS vivas (35 "Nova
   OS") na 1ª rodada depois dela (o robô de julho só deixava a Nova OS na semana ativa). Falta: o código no servidor (a
   carga que mantém a mescla); a dimensão de equipamento ler o `codigo_ativo` do fato como fonte "pcm" (456 blocos das
   semanas antigas estão "fora da dimensão"); no cadastro, 1 cluster e os técnicos sem ficha.
7. **Passo 6c — geração: GRAVA desde 11/10/2026** (decisão 8 do Levi: "pode seguir com as 4 recomendações"). É um
   PRODUTO dos BDs: o `bd_thopen` e o `bd_performance` seguem a FONTE (preenchidos por API e à mão, o Levi sobe ao PG) e
   o Nexus só lê deles ("se você quer matar BD_Performance e BD_Thopen, para o cenário atual eu não aprovo"). A carga de
   hora em hora (`carga.gerar_geracao`) monta só quando o `updated_at` de um dos dois mudou; aba com menos dias que a
   gravada recusa a gravação inteira (`recusou`); o inversor × dia vai em um livro por mês e só o mês que mudou é
   regravado (aba `meses` do `nexus_geracao`, com o sha de cada mês). As 4 decisões: (a) o de-para das abas publicado pela
   seção Ligações da Governança (22 das 23 abas que o ciclo não fechava ligam por outro caminho ou são fora da operação;
   a "zz Rodrigues", cópia arquivada, fica ignorada); (b) teto = potência × 24 h (`geracao.tetos`, já no código); (c) IPOA
   do `bd_performance` só o "IPOA (kWh/m²) DEF" (`COLUNAS_DA_FONTE`: aba sem ele fica com o IPOA vazio); (d) inversor ×
   dia em `nexus_geracao_inversor_AAAA_MM` (o radar casa a família pelo padrão, `catalogo.da_familia`). À mão:
   `python ferramentas/carregar_geracao.py --gravar [--forcar]`.
8. **Lacunas do cadastro** (05/10, ainda abertas): 1 equipe da região do App fora do cadastro; 1 usina do Fracttal e
   o ativo "Grid Co." sem de-para.
9. **Fatos ainda de origem:** decisão do painel (dividir os 3 eventos), zeladoria, tickets, falhas de string e de
   tracker (episódios, tracker × dia, cobertura, OS de string), parada de tracker, perda por equipamento (o gêmeo ainda
   tem usina própria), meta mensal.
10. **De-para do `plant_id` (08/10):** o estado `cod` de `falha_string_episodio`, `falha_tracker`, `falha_tracker_dia`,
   `cobertura_falhas`, `os_string`, `parada_tracker` e `decisao_vinculo_os` (20/10) quer dizer "liga pelo de-para", mas
   o `de_para` do cadastro ainda não tem sistema de `plant_id` (API PV, SunOp, scadaGridco; hoje só Fracttal,
   BD_Performance, Tickets e BD_Thopen, em `cadastro/ligacoes.py`). Entra como sistema novo no
   `cadastro_nexus · de_para` (tela Base → Ligações). Cada grão já é um fato (regra 1), sem trocar id: a `falha_string`
   (dois grãos num registro) virou `falha_string_episodio`, que liga por `plant_id`, e `falha_string_inversor_dia`, que
   só tem o nome da usina (auditoria de 08/10, GR-2); o id antigo ficou como `parte`, com a história. O tracker × dia
   entrou como `falha_tracker_dia`, ao lado do `falha_tracker` (episódio), que não mudou de id.

## Como provar

- `python -m pytest -q tests/test_dados_camada.py tests/test_dados_historico.py tests/test_dados_ronda_pt.py
  tests/test_dados_equipamento.py tests/test_dados_programacao.py tests/test_dados_geracao.py` (catálogo com tipo,
  chave, medidas e livros; a carga que grava só os livros registrados, a dimensão só quando muda, segura o histórico,
  não grava com chave repetida e mostra o que encolheu; cada fato com as regras dele).
- `python -m pytest -q tests/test_campo_fatos_nas_telas.py` (passo 4: as telas do Campo sobre os fatos, o do banco da
  mesma versão do livro, o montado na hora, o grão quebrado, a validação por foto fora da ronda).
- `python ferramentas/carregar_dados.py --ensaio` mede com o dado real sem gravar (o que grava e o que só é montado:
  linhas, chave repetida, % de cada ID, xlsx). `--sem-geracao` pula a leitura das 171 abas de geração (~30–60 s).
- `python ferramentas/carregar_geracao.py --ensaio [--de-para-local] [--xlsx PASTA]` e
  `python ferramentas/carregar_ativos_fracttal.py <fotos>` (sem `--gravar`) medem a geração e a foto.
- `python ferramentas/carregar_programacao_historica.py` (sem `--gravar`, ~10 min) refaz a escolha da versão de cada
  semana no git do PCM e imprime, por semana, a versão, a regra, os blocos do fim da semana e os que saíram depois, e a
  prova git × arquivo (tem de dar 0 diferenças). Com `--gravar` ele mescla com o que está no banco e confere por GET.
- `python ferramentas/importar_avulsas_planilha.py <planilha> --pessoa "<nome>"` (sem `--gravar`) mede a importação da
  validação por foto (linhas, usinas que casam e as de fora com o porquê, a pessoa só pelo `pessoa_id`, datas, níveis);
  com `--gravar`, grava e confere linha a linha. Testes: `tests/test_campo_ronda_avulsa.py` e
  `tests/test_campo_importar_avulsas.py`.
- Base → Governança de dados: as barras da última carga e a hora dela; o radar do banco (no alto do organograma)
  tem de dar **0 novas**. `python -m pytest -q tests/test_dados_organograma.py` (o organograma, a gaveta, a prévia da
  tabela e o radar: tabela nova aparece nas duas visões, a conhecida não, a nova só abre para administrador).
