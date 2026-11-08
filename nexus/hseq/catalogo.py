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
)

RESUMO = {
    "exclusao_extintor": "Os extintores que a Segurança excluiu, e por quê",
    "pedido_ronda_extintor": "As novas rondas de extintores que a Segurança pediu, por usina",
    "edicao_extintor": "As edições que a Segurança fez no cadastro dos extintores",
    "email_pendencias_seguranca": "O e-mail semanal das pendências da Segurança, por destinatário",
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
}
