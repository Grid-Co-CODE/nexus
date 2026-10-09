"""O que cada fato do catálogo é, em linguagem de quem não é da área de dados.

Levi, 09/10/2026, sobre o detalhe do organograma: "Deixe a linguagem do card mais amigável e entendível para alguém que
quer saber para o que essa tabela serve, o que ela faz, de onde vem etc!". O catálogo (`catalogo.py`) é o contrato
técnico (grão, chave, tipo, medidas, por onde liga cada dimensão) e continua a fonte única disso; aqui mora só o "para
que serve", que nenhum campo do catálogo dizia. O resto do texto amigável da tela (de onde vem, quem grava, como liga)
sai do próprio catálogo em `telas.py`, para não haver duas versões da mesma regra.

Cada fato que a tela mostra (todo fato que não se aposentou) tem as duas frases: `RESUMO`, uma linha no cartão do
organograma, e `PARA_QUE`, o parágrafo da gaveta. Fato novo no catálogo sem texto aqui derruba
`test_todo_fato_mostrado_tem_o_texto_amigavel`. Sem nome de colega (o repositório é público): papel, nunca pessoa.
"""

RESUMO = {
    # ── Campo · App ──
    "fechamento": "Cada tarefa que o técnico fecha no App, com a nota do painel",
    "ronda": "Cada ronda feita nas usinas, pelo App ou lançada no Nexus",
    "ronda_checklist": "As respostas das rondas antigas que ficaram sem OS",
    "ronda_avulsa": "Ronda lançada à mão no Nexus e o nível validado pela foto",
    "decisao": "O que o painel do App decidiu: aprovar, tratar ou devolver",
    "zeladoria": "Cada etapa da vistoria de zeladoria feita pelo App",
    # ── Segurança · HSEQ ──
    "pt": "Cada Permissão de Trabalho pedida no App, por equipamento",
    "decisao_pt": "A decisão sobre uma PT tomada no Nexus pelo supervisor",
    "extintor": "Cada extintor das usinas, com as validades e a última conferência",
    "conferencia_extintor": "Cada conferência mensal de extintor feita pelo App",
    # ── Performance ──
    "geracao_usina_dia": "Quanto cada usina gerou por dia, com a irradiação",
    "geracao_inversor_dia": "Quanto cada inversor gerou por dia",
    "geracao_thopen": "A planilha de geração das usinas Thopen, uma aba por usina",
    "geracao_demais": "A planilha de geração das demais usinas, uma aba por usina",
    "meta_mensal": "A meta de geração de cada usina por mês e o histórico",
    "falha_string": "O registro antigo das falhas de string, hoje em duas tabelas",
    "falha_string_episodio": "Cada vez que uma string parou, até voltar, e a perda",
    "falha_string_inversor_dia": "A perda por strings fora, por inversor e por dia",
    "falha_tracker": "Cada vez que um tracker parou, quanto tempo e a perda",
    "falha_tracker_dia": "Quantos trackers ficaram parados por usina e por dia",
    "cobertura_falhas": "Que usinas a plataforma de fato monitorou em cada mês",
    "os_string": "Cada OS de recomposição de string aberta no Fracttal",
    "parada_tracker": "Cada parada de tracker registrada pela plataforma",
    "perda_equipamento": "Quanto cada equipamento deixou de gerar por dia",
    # ── Chamados ──
    "ticket": "Os tickets de performance abertos para cada falha",
    # ── PCM ──
    "programacao": "A agenda semanal de manutenção montada pelo PCM",
}

PARA_QUE = {
    "fechamento": "Guarda cada tarefa de manutenção que o técnico fecha no App de Campo, com a nota que o painel deu, "
                  "as fotos, as peças e o tempo gasto. Serve para acompanhar a qualidade e a produção do campo por "
                  "usina, equipe, técnico e equipamento, e para ligar o que foi feito ao que o PCM programou.",
    "ronda": "Junta todas as rondas feitas nas usinas: as do App (com e sem OS no Fracttal), as respostas antigas que "
             "ficaram sem OS e as rondas avulsas lançadas no Nexus. Serve para saber que usina foi visitada, quando, e "
             "o que a ronda encontrou: vegetação, sujidade, vala, sensores e falhas.",
    "ronda_checklist": "Guarda, de uma vez só, as respostas do checklist das rondas do App que ficaram sem OS no "
                       "Fracttal (de 11/08 a 06/10/2026). Alimenta a tabela de Ronda, para que essas respostas não se "
                       "percam quando o App apagar o que passa de 90 dias.",
    "ronda_avulsa": "Recebe a ronda lançada à mão no Nexus por quem a fez (sem o App), o nível de vegetação e "
                    "sujidade validado pela foto e a anulação de um lançamento. A ronda avulsa válida entra na tabela "
                    "de Ronda e conta na cobertura; a validação pela foto fica fora, porque não é uma ronda feita.",
    "decisao": "Registra as decisões tomadas no painel do App de Campo: a aprovação de uma tarefa, o tratamento de um "
               "alerta da Central de atenção e a devolução de uma tarefa ao técnico. Serve para saber quem decidiu o "
               "quê, quando e sobre qual OS.",
    "zeladoria": "Guarda cada etapa da vistoria de zeladoria feita pelo App, com as fotos e as respostas do "
                 "checklist. Serve para acompanhar a conservação das usinas e o que ficou com resposta \"não\".",
    "pt": "Guarda cada Permissão de Trabalho (PT) pedida pelo técnico no App, uma linha por equipamento: quem pediu, "
          "quem decidiu, quanto tempo esperou e se o equipamento precisou parar. Serve para acompanhar a segurança e "
          "o tempo de liberação do trabalho no campo.",
    "decisao_pt": "Guarda cada decisão (De acordo ou Não autorizo) sobre uma PT tomada no Nexus pelo supervisor. O "
                  "App de Campo lê esta tabela e aplica a decisão na PT do técnico. O motivo é gravado sem dado "
                  "pessoal, porque o técnico o lê.",
    "extintor": "Lista cada extintor das usinas (o cadastro da TST e os que o técnico acha na ronda), com onde ele "
                "fica, a classe, o peso, as duas validades (recarga e teste hidrostático) e a última conferência. "
                "Serve para saber o que está vencido, o que vence nos próximos 30 dias e o que ninguém confere há mais "
                "de 30 dias, por supervisor de campo e por gestor de contrato (a tela Extintores, em Segurança).",
    "conferencia_extintor": "Guarda cada conferência de extintor feita na ronda mensal do App: a carga, os itens "
                            "com \"não\", as validades lidas na etiqueta e quem conferiu. Serve para acompanhar, mês a "
                            "mês, se a ronda de extintores está sendo feita e o que ela encontrou.",
    "geracao_usina_dia": "A energia que cada usina gerou em cada dia (kWh), com a irradiação e a chuva, tirada das "
                         "planilhas do coletor e posta uma linha por dia. É a base da análise de performance: comparar "
                         "com a meta, achar os dias ruins e calcular as perdas.",
    "geracao_inversor_dia": "A energia que cada inversor gerou em cada dia. Serve para achar o inversor que gera "
                            "menos que os vizinhos da mesma usina. São cerca de 700 mil linhas, por isso onde gravar "
                            "ainda é uma decisão.",
    "geracao_thopen": "É a planilha de geração das usinas da carteira Thopen como o coletor da API PV grava: uma aba "
                      "por usina, um dia por linha e um inversor por coluna. Alimenta as duas tabelas de geração do "
                      "Nexus (por usina e por inversor), onde a usina e o inversor ganham os IDs.",
    "geracao_demais": "É a planilha de geração das demais usinas (fora da carteira Thopen) como o coletor da API PV "
                      "grava: uma aba por usina, um dia por linha e um inversor por coluna. Alimenta as duas tabelas "
                      "de geração do Nexus, onde a usina e o inversor ganham os IDs.",
    "meta_mensal": "A meta de geração de cada usina em cada mês, com o PR e a irradiação esperados, e o histórico do "
                   "que foi gerado. Serve para dizer se a usina está acima ou abaixo do esperado no mês.",
    "falha_string": "É como as falhas de string eram catalogadas até 08/10/2026: um registro só para dois tipos de "
                    "linha. Os dados são os mesmos das duas tabelas que ficaram no lugar dele (o episódio e o "
                    "inversor por dia), gravados pela plataforma de performance.",
    "falha_string_episodio": "Guarda cada vez que uma string parou de gerar, de quando saiu até quando voltou, e "
                             "quanta energia se perdeu (kWh). Serve para priorizar o reparo e medir a perda por usina, "
                             "inversor e string.",
    "falha_string_inversor_dia": "Soma, por inversor e por dia, a energia perdida com strings fora. Serve para ver a "
                                 "perda do mês por usina e por inversor.",
    "falha_tracker": "Guarda cada vez que um tracker parou, de quando parou até quando voltou, quanto tempo ficou "
                     "parado e quanta energia se perdeu. Diz também em quantos dias a usina estava comunicando, para "
                     "separar a falha de verdade da falta de dado.",
    "falha_tracker_dia": "Conta, por usina e por dia, quantos trackers ficaram parados enquanto a usina comunicava. "
                         "É a tabela do diário de trackers do Dashboard Thopen.",
    "cobertura_falhas": "Diz, mês a mês, que usinas a plataforma de performance de fato monitorou e em quantos dias. "
                        "Serve para separar \"sem falha\" de \"sem monitoramento\": a usina sem linha aqui não está "
                        "sendo medida.",
    "os_string": "Guarda cada OS de recomposição de string do Fracttal, pela data do evento, com quantas strings ela "
                 "cita. É de onde o Dashboard Thopen tira as strings do mês; a OS sem quantidade fica vazia, nunca "
                 "zero.",
    "parada_tracker": "Guarda cada parada de tracker que a plataforma de performance registrou, com a duração. Serve "
                      "para acompanhar a disponibilidade dos trackers de cada usina.",
    "perda_equipamento": "O gêmeo digital calcula, para cada dia, quanto cada equipamento deixou de gerar em cada "
                         "parcela da cascata de perdas. Serve para saber onde está a energia perdida em cada usina.",
    "ticket": "Guarda os tickets de performance: cada problema aberto para acompanhamento, com o início, o tempo de "
              "indisponibilidade e a energia perdida. Serve para acompanhar o problema até fechar e medir o impacto "
              "de cada falha.",
    "programacao": "A agenda semanal de manutenção que o PCM monta: que tarefa, em que usina, com qual equipe e em "
                   "que dia e hora. Serve para comparar o planejado com o que o campo fez e ver a carga de cada "
                   "equipe. O Nexus guarda as semanas desde a W21 de 2026, além das 4 que o arquivo do PCM guarda.",
}
