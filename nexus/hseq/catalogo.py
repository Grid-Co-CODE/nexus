"""O catálogo de dados da Segurança · HSEQ: os fatos e os livros que o Nexus grava pela Segurança, com os textos que
a Governança de dados mostra.

Mora aqui, na pasta da Segurança, desde 05/11/2026 (Levi: "eu quero deixar ela independente, não podemos deixar travas
com ela"; "independente no setor dela, claro"): quem programa a Segurança registra os dados novos dela sem esperar o
administrador, num pedido que a conferência `pasta-da-area` aprova. O catálogo central (`nexus/dados/catalogo.py`)
junta estes com os de todas as áreas, e as regras e as provas de lá continuam valendo para os daqui. Leia
`nexus/dados/CLAUDE.md` antes de pôr um dado novo no banco. Em resumo:
- registre aqui ANTES da 1ª gravação (o radar da Governança acusa a tabela do banco que não está no catálogo);
- o livro se chama `nexus_hseq_<assunto>`, para sempre, e o fato diz o grão (o que é UMA linha), o tipo e a chave;
- pessoa só por `pessoa_id` do cadastro ou pelo código (HMAC), nunca pelo nome nem pelo CPF; o texto livre e o dado
  pessoal vão cifrados (a API do banco tem leitura aberta);
- todo fato ganha as duas frases para quem não é da área de dados: `RESUMO` (uma linha) e `PARA_QUE` (o parágrafo).
"""
from ..dados.modelo import Fato, Livro, _d

FATOS = (
    # as decisões da Segurança sobre os extintores (24/10/2026, Levi: "quando a TST aceita o extintor é excluído e vai
    # para um histórico de extintores excluídos"; "pedir uma nova ronda é uma nova ronda do zero então será por usina"):
    # o Nexus é a FONTE; o App de Campo lê daqui a baixa e o pedido de ronda. Registrado antes da 1ª gravação.
    Fato("exclusao_extintor", "Exclusão de extintor (Segurança)", "hseq",
         "nexus_hseq_extintores · fato_exclusao_extintor",
         "1 linha = 1 exclusão (a baixa) de 1 extintor pela Segurança, com o motivo; vale a última de cada extintor",
         _d(data=("id", "data_id (o dia de Brasília da exclusão; marca_dia, o dia do Não reconhecido aceito)"),
            usina=("id", "usina_id (vazio para extintor de usina fora do cadastro)"),
            pessoa=("hmac", "decidida_por_hmac (quem excluiu; o nome só cifrado)"),
            equipamento=("prop", "codigo: o código do extintor (cadastro próprio do App, fora do Fracttal)")),
         tipo="sem_medida", chave=("decidida_em", "codigo"),
         fontes=("nexus_hseq_extintores · fato_exclusao_extintor",),
         janela_origem="o Nexus é a fonte (só acrescenta)",
         observacao="motivo (domínio): nao_reconhecido (o Aceitar do não reconhecido, com a marca do App em marca_dia), "
                    "retirado, duplicado ou outro (pelo botão direito na linha do extintor). O excluído some das telas e "
                    "das contas do Nexus e vai para o histórico de excluídos; volta sozinho se aparecer uma conferência "
                    "num dia depois da exclusão. Quem excluiu e a observação só cifrados (dados_cifrados, regra 8). "
                    "Cada linha vai assinada (assinatura, HMAC com a chave derivada da NEXUS_PESSOA_HMAC, rótulo "
                    "nexus:hseq:extintores): o App lê pela leitura aberta da API e só aplica a linha assinada"),
    Fato("pedido_ronda_extintor", "Pedido de nova ronda de extintores", "hseq",
         "nexus_hseq_extintores · fato_pedido_ronda",
         "1 linha = 1 pedido da Segurança de uma nova ronda de extintores, do zero, em 1 usina",
         _d(data=("id", "data_id (o dia de Brasília do pedido)"),
            usina=("id", "usina_id (+ usina_app, o nome que o App usa para a usina)"),
            pessoa=("hmac", "decidida_por_hmac (quem pediu; o nome só cifrado)")),
         tipo="sem_medida", chave=("decidida_em", "usina_id"),
         fontes=("nexus_hseq_extintores · fato_pedido_ronda",),
         janela_origem="o Nexus é a fonte (só acrescenta)",
         observacao="o App mostra à equipe da usina a ronda pendente (\"O TST solicitou uma nova ronda\"); o Nexus o "
                    "dá por atendido, como o App, quando TODOS os extintores da usina chegam conferidos (a 'Recebida em' "
                    "do livro de conferências, pela hora) ou marcados como não reconhecidos depois do pedido. Assinado "
                    "como a exclusão"),
    # a edição do cadastro de um extintor pela Segurança (24/10/2026, a TST: "Eu consigo editar o cadastro de
    # extintores?"): o Nexus é a FONTE; o App grava a edição no cadastro dele
    Fato("edicao_extintor", "Edição do cadastro de extintor (Segurança)", "hseq",
         "nexus_hseq_extintores · fato_edicao_extintor",
         "1 linha = 1 edição do cadastro de 1 extintor pela Segurança, só com os campos que mudaram",
         _d(data=("id", "data_id (o dia de Brasília da edição)"),
            usina=("id", "usina_id (vazio para extintor de usina fora do cadastro)"),
            pessoa=("hmac", "decidida_por_hmac (quem editou; o nome só cifrado)"),
            equipamento=("prop", "codigo: o código do extintor (cadastro próprio do App, fora do Fracttal)")),
         tipo="sem_medida", chave=("decidida_em", "codigo"),
         fontes=("nexus_hseq_extintores · fato_edicao_extintor",),
         janela_origem="o Nexus é a fonte (só acrescenta)",
         observacao="campos: JSON {coluna do livro do App: valor novo} com Local, Posição, Classe, Peso (kg), Validade "
                    "da recarga e Validade do hidrostático (o código não muda); são dados do equipamento, em claro. "
                    "O Nexus mostra o editado por cima do livro do App até uma conferência num dia depois da edição. "
                    "Quem editou e a observação só cifrados. Assinado como a exclusão (o texto leva o campos como "
                    "está gravado)"),
    # o e-mail semanal das pendências da Segurança (24/10/2026, a TST: "Receber report semanal das pendências por
    # email, pra mim e pro supervisor responsável"): o Nexus monta e publica, o App de Campo manda
    Fato("email_pendencias_seguranca", "E-mail semanal das pendências da Segurança", "hseq",
         "nexus_hseq_email · fato_email_pendencias",
         "1 linha = 1 e-mail de 1 destinatário numa semana (a TST, com todas as usinas, ou um Responsável UFV, com as "
         "usinas dele)",
         _d(data=("id", "data_id (o dia de Brasília em que foi montado; semana = a semana ISO)"),
            pessoa=("id", "pessoa_id (o número no cadastro) + destinatario_hmac (o código do e-mail, como o do login)")),
         tipo="sem_medida", chave=("semana", "destinatario_hmac"),
         fontes=("nexus_hseq_email · fato_email_pendencias",),
         janela_origem="o Nexus é a fonte (só acrescenta, uma vez por semana)",
         observacao="papel tst ou responsavel; assunto, corpo_texto e corpo_html com usinas, clientes e números, nunca "
                    "nome nem e-mail de pessoa (o link da Mesa leva o número da pessoa, ?r=). Assinado (assinatura, HMAC "
                    "com a chave derivada da NEXUS_PESSOA_HMAC, rótulo nexus:hseq:email): o App só manda a linha "
                    "assinada e acha o e-mail pelo código"),
    # a documentação de segurança de cada colaborador (06/11/2026, a Segurança: "puxar os dados dos colaboradores de
    # acordo com a base já utilizada, porém quero editar/incluir esses itens da planilha"): o Nexus é a FONTE; a tela
    # Colaboradores edita e carrega a planilha. Registrado antes da 1ª gravação
    Fato("documentacao_colaborador", "Documentação de segurança do colaborador", "hseq",
         "nexus_hseq_documentacao · fato_documentacao",
         "1 linha = 1 registro da situação de 1 item de documentação (ASO, NR, integração, anuência, documento) de 1 "
         "pessoa; vale o último de cada pessoa e item",
         _d(data=("id", "data_id (o dia de Brasília do registro)"),
            pessoa=("id", "pessoa_id (a ficha do cadastro; a planilha casa pelo nome, na memória, e nunca chuta) + "
                          "registrado_por_hmac (quem registrou; o nome só cifrado)")),
         tipo="sem_medida", chave=("registrado_em", "pessoa_id", "item"),
         fontes=("nexus_hseq_documentacao · fato_documentacao",),
         janela_origem="o Nexus é a fonte (só acrescenta)",
         observacao="item (domínio: documentacao.ITENS) e origem (tela ou planilha) em claro. A situação (Válido, Falta, "
                    "Pendente assinatura, Solicitado, Não se aplica), a data (de realização nas NRs, de validade no ASO "
                    "e na CNH) e quem registrou só cifrados (dados_cifrados, o Cofre do cadastro): o ASO é dado de "
                    "saúde e a API tem leitura aberta. A validade das NRs sai da periodicidade da norma, na tela. A "
                    "planilha só grava o que muda o último registro da pessoa"),
    # a foto diária dos extintores fora do em dia (24/11/2026, o mockup de Extintores aprovado pela Segurança: "hoje o
    # Nexus só guarda a última conferência de cada extintor, então não dá para saber o que estava vencido num dia
    # passado"): o Nexus é a FONTE. Só as mudanças, com a foto completa no 1º dia do mês (a escolha da Segurança depois
    # da medida: 516 linhas por dia, ~188 mil por ano, se cada dia fosse uma foto inteira). Registrado antes da 1ª gravação
    Fato("extintor_dia", "Extintor fora do em dia, por dia (foto diária)", "hseq",
         "nexus_hseq_extintores_historico · fato_extintor_dia",
         "1 linha = 1 extintor num dia: na foto completa (tipo completa, no 1º dia de cada mês), cada extintor fora do "
         "em dia; nos outros dias (tipo mudanca), só o que entrou, saiu ou mudou de situação desde o dia anterior",
         _d(data=("id", "data_id (o dia de Brasília da foto)"),
            usina=("id", "usina_id (vazio para extintor de usina fora do cadastro)"),
            equipamento=("prop", "codigo: o código do extintor (cadastro próprio do App, fora do Fracttal)")),
         tipo="sem_medida", chave=("data_id", "codigo"),
         fontes=("extintores_app_campo · Extintores", "nexus_hseq_extintores · fato_exclusao_extintor",
                 "nexus_hseq_extintores · fato_edicao_extintor"),
         janela_origem="o Nexus é a fonte (só acrescenta, uma vez por dia depois das 06:00)",
         observacao="situacao (domínio): atrasado, perto, sem_validade, em_dia; na mudança também fora (saiu da tela: "
                    "excluído, não reconhecido ou fora do livro do App). sem_atualizacao sim/não soma às outras, como "
                    "na tela. venceu: recarga ou hidrostático, no atrasado. A situação de um dia = a completa mais "
                    "perto antes dele + as mudanças até ele; é a mesma conta da tela, com as exclusões e as edições da "
                    "Segurança. Sem pessoa nem cliente"),
    Fato("foto_extintores_dia", "Dia com a foto dos extintores", "hseq",
         "nexus_hseq_extintores_historico · fato_foto_dia",
         "1 linha = 1 dia em que a foto dos extintores foi gravada, com os totais",
         _d(data=("id", "data_id (o dia de Brasília da foto)")),
         tipo="sem_medida", chave=("data_id",),
         fontes=("nexus_hseq_extintores_historico · fato_extintor_dia",),
         janela_origem="o Nexus é a fonte (só acrescenta, uma vez por dia)",
         observacao="completa sim/não; extintores (os da tela), fora_do_em_dia e linhas (as gravadas no dia). Dia sem "
                    "esta linha é dia sem foto (a API fora o dia inteiro): a tela mostra a lacuna, sem inventar"),
    # as tratativas dos extintores (24/11/2026, o mockup de Extintores aprovado pela Segurança, entrega 2): o que a
    # Segurança fez com o cliente ou a usina que tem extintor vencido. Num livro só delas (25/11/2026: o App de Campo lê o
    # das decisões, e não deu para confirmar no código dele que ignora uma aba nova). Registrado antes da 1ª gravação
    Fato("tratativa_extintor", "Tratativa da Segurança sobre os extintores", "hseq",
         "nexus_hseq_extintores_tratativas · fato_tratativa_extintor",
         "1 linha = 1 tratativa da Segurança, que vale para o cliente inteiro ou para uma usina dele",
         _d(data=("id", "data_id (o dia da tratativa, que a pessoa escolhe; nunca no futuro)"),
            usina=("id", "usina_id (no escopo usina; vazio no escopo cliente)"),
            cliente=("id", "cliente_id (o cliente do cadastro, nos dois escopos; nunca o nome)"),
            pessoa=("hmac", "decidida_por_hmac (quem registrou; o nome só cifrado)")),
         tipo="sem_medida", chave=("decidida_em", "escopo", "cliente_id", "usina_id"),
         fontes=("nexus_hseq_extintores_tratativas · fato_tratativa_extintor",),
         janela_origem="o Nexus é a fonte (só acrescenta)",
         observacao="escopo (domínio): cliente ou usina. tipo (domínio): email, recarga_agendada, os_recarga, troca, "
                    "aguardando ou outro. Quem registrou e a observação (até 300 letras) só cifrados (dados_cifrados, "
                    "regra 8). Assinada (assinatura, HMAC com a chave derivada da NEXUS_PESSOA_HMAC, rótulo "
                    "nexus:hseq:tratativas)"),
)

LIVROS = (
    # as decisões da Segurança sobre os extintores (24/10/2026): a exclusão de extintor (o não reconhecido aceito e o
    # botão direito) e o pedido de nova ronda por usina; o App de Campo lê os dois daqui
    Livro("nexus_hseq_email", ("fato_email_pendencias",),
          "toda segunda depois das 07:00, no servidor (NEXUS_HSEQ_EMAIL_AUTO=0 desliga)", "nexus/hseq/email_semanal.py", False,
          "registrado em 24/10/2026 antes de existir: nasce com a 1ª semana publicada, quando o App de Campo estiver "
          "pronto para ler e mandar. NÃO só cresce (exceção declarada, 08/11/2026): é a fila dos e-mails, o App lê a "
          "semana, manda e confirma, e a linha que não sai vence na segunda seguinte; semana velha não serve, e o "
          "`publicar` guarda só as 4 últimas semanas ISO (a corrente nunca sai)"),
    Livro("nexus_hseq_extintores", ("fato_exclusao_extintor", "fato_pedido_ronda", "fato_edicao_extintor"),
          "a cada decisão na tela de Extintores", "nexus/hseq/decisoes.py, pela tela Extintores da Segurança", False,
          "registrado em 24/10/2026 antes de existir: nasce com a 1ª decisão. A tela lê com cache de 1 minuto e a "
          "gravação relê o banco antes (troca o livro inteiro, as abas juntas)",
          so_cresce=True),
    Livro("nexus_hseq_documentacao", ("fato_documentacao",),
          "a cada registro na tela Colaboradores e a cada carga da planilha da Segurança",
          "nexus/hseq/documentacao.py, pela tela Colaboradores da Segurança", False,
          "registrado em 06/11/2026 antes de existir: nasce com o 1º registro. A gravação relê o banco antes e troca o "
          "livro inteiro",
          so_cresce=True),
    Livro("nexus_hseq_extintores_historico", ("fato_extintor_dia", "fato_foto_dia"),
          "uma vez por dia, depois das 06:00, no servidor (NEXUS_HSEQ_EXT_FOTO_AUTO=0 desliga)",
          "nexus/hseq/extintores_historico.py, pelo laço do e-mail semanal da Segurança", False,
          "registrado em 24/11/2026 antes de existir: nasce com a 1ª foto (completa). Só as mudanças, com a foto "
          "completa no 1º dia de cada mês; a gravação relê o banco antes e troca o livro inteiro",
          so_cresce=True),
    Livro("nexus_hseq_extintores_tratativas", ("fato_tratativa_extintor",),
          "a cada tratativa registrada na tela de Extintores",
          "nexus/hseq/tratativas.py, pela tela Extintores da Segurança", False,
          "registrado em 25/11/2026 antes de existir: nasce com a 1ª tratativa. A tela lê com cache de 1 minuto e a "
          "gravação relê o banco antes e troca o livro inteiro",
          so_cresce=True),
)

RESUMO = {
    "exclusao_extintor": "Os extintores que a Segurança excluiu, e por quê",
    "pedido_ronda_extintor": "As novas rondas de extintores que a Segurança pediu, por usina",
    "edicao_extintor": "As edições que a Segurança fez no cadastro dos extintores",
    "email_pendencias_seguranca": "O e-mail semanal das pendências da Segurança, por destinatário",
    "documentacao_colaborador": "A documentação de segurança de cada colaborador (ASO, NRs)",
    "extintor_dia": "Os extintores fora do em dia, dia a dia, pelas mudanças",
    "foto_extintores_dia": "Os dias em que a foto dos extintores foi gravada",
    "tratativa_extintor": "O que a Segurança fez com os extintores vencidos de cada cliente",
}

PARA_QUE = {
    "exclusao_extintor": "Guarda cada extintor que a Segurança excluiu na tela Extintores, com o motivo: o que a "
                         "equipe não achou na usina (o Aceitar) ou o que saiu pelo botão direito (retirado, duplicado, "
                         "outro). O excluído sai das telas e vai para o histórico de excluídos; volta se a equipe o "
                         "conferir numa ronda depois.",
    "pedido_ronda_extintor": "Guarda cada nova ronda de extintores, do zero, que a Segurança pede numa usina. É para o "
                             "App de Campo mostrar à equipe como ronda pendente; vale até a equipe refazer a ronda inteira.",
    "edicao_extintor": "Guarda cada edição que a Segurança fez no cadastro de um extintor na tela Extintores (local, "
                       "posição, classe, peso e as validades), só com o que mudou. A tela mostra o editado na hora, e o "
                       "App de Campo grava no cadastro dele. Quem editou vai cifrado.",
    "email_pendencias_seguranca": "Guarda o e-mail de cada segunda com as pendências da Segurança: um para a TST, "
                                  "com todas as usinas, e um para cada Responsável UFV, com as usinas dele. O Nexus "
                                  "monta e o App de Campo manda. Não leva nome nem e-mail de pessoa, só o código.",
    "documentacao_colaborador": "Guarda a situação de cada item de documentação de segurança de cada colaborador do "
                                "cadastro (ASO, NR-10, NR-35 e as outras NRs, integrações, anuências e documentos), "
                                "registrada pela Segurança na tela Colaboradores ou carregada da planilha dela. A tela "
                                "mostra o que venceu, o que falta e o que espera assinatura. A situação e a data vão "
                                "cifradas.",
    "extintor_dia": "Guarda, dia a dia, os extintores que não estão em dia (atrasados, perto de vencer, sem validade e "
                    "sem atualização), com a mesma conta da tela Extintores. Grava a foto inteira no 1º dia do mês e, "
                    "nos outros dias, só o que mudou. É o histórico para ver o que venceu e o que foi resolvido.",
    "foto_extintores_dia": "Guarda cada dia em que a foto dos extintores foi gravada, com quantos estavam fora do em "
                           "dia. O dia que não está aqui ficou sem foto, e a tela mostra a lacuna em vez de inventar.",
    "tratativa_extintor": "Guarda cada tratativa que a Segurança registra sobre os extintores de um cliente ou de uma "
                          "usina (cliente notificado, recarga agendada, OS de recarga aberta, troca realizada, "
                          "aguardando o cliente). A tela Extintores mostra a última e o histórico. Quem registrou e a "
                          "observação vão cifrados.",
}
