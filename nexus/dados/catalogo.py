"""O catálogo dos dados do Nexus: a matriz de barramento (método Kimball) como DADO, e não como desenho.

Levi, 05/10/2026: "prioridade 0 para a governança e controle de dados"; "precisamos construir e manter uma base sólida
para futuras análises correlacionadas". Cada processo que gera dado (um FATO: um fechamento, uma ronda, a geração de um
dia) se liga aos cadastros de referência (as DIMENSÕES: usina, pessoa, data...) por ID. Este arquivo é a fonte única:
a tela Base → Governança de dados, os testes e o CLAUDE.md da área leem daqui. Fonte nova entra AQUI primeiro (ver
`nexus/dados/CLAUDE.md`, "Como entra um dado novo"), e livro novo entra em `LIVROS` ANTES de existir no banco.

08/10/2026 (auditoria Kimball, passos 2 a 6): nenhum fato dizia o TIPO nem as MEDIDAS. Sem o tipo, ninguém sabe se
somar duas cargas conta em dobro (foto acumulada) ou não (transação); sem a soma de cada medida, a média da nota vira
soma e a irradiação de duas usinas vira "irradiação total". Todo fato ativo declara agora `tipo`, `chave`, `medidas`
(com a unidade e se soma), `fontes` e `janela_origem` (quanto a fonte guarda: o que sai da janela sai do fato enquanto
a carga for troca integral, o passo 0 adiado pelo Levi em 08/10).

Estados de cada ligação fato × dimensão:
  id      liga pelo ID do cadastro do Nexus (o certo)
  cod     código de um sistema (código da usina, plant_id, código do ativo, data, número da OS): liga pelo de-para
  hmac    a pessoa como código do e-mail (HMAC, NEXUS_PESSOA_HMAC): liga com a chave
  nome    texto livre: junção frágil
  largo   um equipamento por coluna (formato largo): precisa virar linhas
  prop    cadastro próprio, que só aquele livro usa
  nao     não tem

Estados de cada fato (`ESTADOS_FATO`):
  origem      só existe como a fonte grava (sem os IDs do Nexus)
  montado     o Nexus já monta o fato com os IDs (medido no `carregar_dados.py --ensaio`), mas a gravação espera
              decisão do Levi; `conformado_em` = o destino registrado em `LIVROS` (vazio se o destino é a decisão)
  conformado  o Nexus grava o fato com os IDs (`conformado_em` = onde)
  parte       virou FONTE de outro(s) fato(s) do catálogo (`parte_de`); a história fica, com a observação
  aposentado  a fonte não vale mais
  fora        fora do banco e sem montagem
"""
import re
from dataclasses import dataclass

from . import fato_chamado, fato_pt, fato_ronda, fato_tarefa_os, fatos, geracao, programacao

ESTADOS = {"id": "ID", "cod": "código", "hmac": "código da pessoa", "nome": "nome", "largo": "em colunas",
           "prop": "cadastro próprio", "nao": "—"}
ESTADOS_FATO = {"origem": "como a fonte grava", "montado": "montado, sem gravar", "conformado": "com IDs",
                "parte": "fonte de outro fato", "aposentado": "aposentado", "fora": "fora do banco"}
# Os tipos de fato do Kimball. Transação: 1 linha por acontecimento, nunca muda. Foto periódica: o estado no fim de
# cada período (dia, semana, mês). Foto acumulada: 1 linha por coisa que anda (a PT aguardando e depois decidida) e
# MUDA até fechar. Sem medida: só registra que aconteceu (conta-se linhas).
TIPOS_FATO = ("transacao", "snapshot_periodico", "snapshot_acumulado", "sem_medida")
TIPO_ROTULO = {"transacao": "transação", "snapshot_periodico": "foto periódica",
               "snapshot_acumulado": "foto acumulada", "sem_medida": "sem medida"}
# Como a medida soma. aditiva: em qualquer corte. semi: num eixo só (a irradiação soma no tempo de UMA usina, não
# entre usinas). nao: nunca (nota, percentual, RPN: média, mínimo, máximo).
SOMA = ("aditiva", "semi", "nao")
SUFIXOS_UNIDADE = ("_min", "_kwh", "_kwh_m2", "_mm", "_pct", "_qtd", "_pts", "_nivel")


@dataclass(frozen=True)
class Medida:
    coluna: str     # com a unidade no nome (SUFIXOS_UNIDADE); indicador sem sufixo, só 1/0
    unidade: str    # "min", "kWh", "kWh/m²", "mm", "%", "qtd", "pts", "nível 1-5", "1/0"
    soma: str       # SOMA


def medida_valida(m: Medida) -> bool:
    """A regra 3 da casa: a unidade está no nome da coluna, ou é indicador 1/0."""
    return m.soma in SOMA and (m.coluna.endswith(SUFIXOS_UNIDADE) or m.unidade == "1/0")


def _m(tuplas) -> tuple:
    return tuple(Medida(*t) for t in tuplas)


def _fontes(pares) -> tuple:
    return tuple(f"{l} · {a}" for l, a in pares)


# As dimensões conformadas: UMA de cada, com o mesmo ID para todos os setores.
DIMENSOES = (
    ("data", "Data", "nexus_dimensoes · dim_data", "data_id (AAAAMMDD)"),
    # HIST-10 (auditoria 08/10): a usina tem histórico (equipe, responsáveis, região "da época") e a dimensão não o citava
    # a estrutura física da usina (13/10/2026) é hierarquia da MESMA dimensão (usina -> chave do supervisório, cabine,
    # inversor), não um segundo cadastro de equipamento: o inversor aponta o ativo do Fracttal pelo equipamento_id
    ("usina", "Usina", "cadastro_nexus · usinas (+ de_para; nexus_dimensoes · usinas_historico; nexus_estrutura_usina: "
     "chaves do supervisório, cabines e inversores)", "usina_id"),
    ("cliente", "Cliente", "cadastro_nexus · clientes", "cliente_id"),
    # a região de campo (estrutura de O&M de 10/2026) é da EQUIPE: hierarquia da mesma dimensão (equipe -> região, com o
    # Supervisor de Campo e o Coordenador por pessoa_id), não uma dimensão à parte; o fato chega à região pelo equipe_id.
    # (O "região" do nome é a "Região" que o App escreve, que é a equipe; a região de campo é outra coisa.)
    ("equipe", "Equipe / região", "cadastro_nexus · equipes (+ regioes_campo: a região de campo da equipe)",
     "equipe_id (→ regiao_campo_id)"),
    # o setor (12/10/2026) é atributo da PESSOA, como a região de campo é da equipe: a lista em nexus_setores · dim_setor
    # e o setor de cada pessoa do Fracttal em nexus_setores · fato_decisao_setor (vale a última decisão de cada uma)
    ("pessoa", "Pessoa", "cadastro_nexus · pessoas (+ nexus_dimensoes · pessoas_historico; + nexus_setores: o setor "
     "do pessoal do Fracttal)", "pessoa_id"),
    ("equipamento", "Equipamento", "nexus_equipamentos · dim_equipamento (+ equipamento_apelido)",
     "equipamento_id (sha1 do código do ativo do Fracttal)"),
    ("os", "OS", "o número no próprio fato (dimensão degenerada)", "os"),
)
DIM_IDS = tuple(d[0] for d in DIMENSOES)


@dataclass(frozen=True)
class Fato:
    id: str
    nome: str
    area: str                  # o setor dono (a torre do Nexus)
    livro: str                 # de onde vem no banco (workbook · aba), ou "fora do banco: ..."
    grao: str                  # o que é UMA linha: sem isto escrito, dois relatórios contam coisas diferentes
    dims: dict                 # {dimensão: (estado, coluna/observação)}
    tipo: str = ""             # TIPOS_FATO (obrigatório em todo fato: o teste exige)
    chave: tuple = ()          # a(s) coluna(s) que identificam a linha; vazio só em fato de origem que diz por quê
    medidas: tuple = ()        # (Medida, ...): no fato de origem, as que o fato conformado vai ter
    fontes: tuple = ()         # "livro · aba" de cada fonte (o fato único de ronda tem três)
    janela_origem: str = ""    # quanto a fonte guarda ("90 dias (App)", "4 semanas (PCM)"); vazio = tudo
    estado: str = "origem"     # ESTADOS_FATO
    conformado_em: str = ""    # o livro do Nexus que tem (conformado) ou terá (montado) o fato com os IDs
    parte_de: tuple = ()       # estado "parte": os fatos de que este virou fonte
    observacao: str = ""


def _d(**kw):
    out = {d: ("nao", "") for d in DIM_IDS}
    out.update({k: (v if isinstance(v, tuple) else (v, "")) for k, v in kw.items()})
    return out


FATOS = (
    # ── Campo · App: o App grava de hora em hora (aos :25) ───────────────────────────────────────────────────────
    Fato("fechamento", "Fechamento de OS", "campo", "fechamentos_app_campo · Fechamentos",
         "1 linha = 1 tarefa fechada pelo App (o registro da nota do painel)",
         _d(data=("id", "data_id (Registrado em, dia de Brasília)"),
            usina=("id", "usina_id (de-para do Fracttal; código do ativo)"), equipe=("id", "equipe_id (Região)"),
            pessoa=("id", "pessoa_id (Técnico HMAC)"), equipamento=("id", "equipamento_id (Código do ativo)"),
            os=("cod", "os, id_os_fracttal")),
         tipo=fatos.TIPO_FECHAMENTO, chave=("fechamento_id",), medidas=_m(fatos.MEDIDAS_FECHAMENTO),
         fontes=("fechamentos_app_campo · Fechamentos",), janela_origem="90 dias (App)",
         estado="conformado", conformado_em="nexus_fatos · fato_fechamento",
         observacao="08/10: + equipamento_id e tarefa_chave (a mesma da programação); medidas com a unidade no nome. "
                    "Foto acumulada, não transação: a revisão (aprovada, devolvida, nota corrigida) muda a linha "
                    "depois (o passo 0 terá de ATUALIZAR pela chave, não só acrescentar)"),
    # o fato ÚNICO de ronda (08/10/2026, auditoria GR-1): antes, três livros com três grãos e domínios diferentes
    Fato("ronda", "Ronda", "campo", "rondas_app_campo · OS de ronda", fato_ronda.GRAO,
         _d(data=("id", "data_id (Início, dia de Brasília)"),
            usina=("id", "usina_id (de-para do Fracttal; código; checklist)"),
            equipe=("id", "equipe_id: papel registro (a Região do App); vazio na avulsa"),
            pessoa=("id", "pessoa_id; pessoa_hmac (hoje o App manda o NOME: liga só nome de 1 pessoa)"),
            equipamento=("id", "equipamento_id (o ativo-usina da OS)"),
            os=("cod", "os, id_os_fracttal (vazio sem OS)")),
         tipo=fato_ronda.TIPO, chave=fato_ronda.CHAVE, medidas=_m(fato_ronda.MEDIDAS),
         fontes=_fontes(fato_ronda.FONTES), janela_origem=fato_ronda.JANELA_ORIGEM,
         estado="conformado", conformado_em="nexus_fatos · fato_ronda",
         observacao="até 08/10 o catálogo dizia '1 linha = 1 OS de ronda': 124 de 867 linhas não têm OS. Une o App "
                    "(com e sem OS), o checklist da carga única e a avulsa válida; vala e sensor num domínio só "
                    "(dominios.py). O App guarda 90 dias: sem o passo 0, a ronda de 11/08 sai do fato em ~09/11"),
    # carga ÚNICA (Levi, 06/10/2026: "Atualize o banco de dados com essas rondas passadas sem OS, mas não será rotina")
    Fato("ronda_checklist", "Checklist da ronda sem OS", "campo", "nexus_rondas_checklist · fato_checklist_ronda",
         "1 linha = 1 ronda do App que ficou sem OS no Fracttal, com as respostas do checklist",
         _d(data=("id", "data_id"), usina=("id", "usina_id"), equipe=("id", "equipe_id"), pessoa=("id", "pessoa_id")),
         tipo="transacao", chave=("ronda_id",), estado="parte", parte_de=("ronda",),
         observacao="carga única de 06/10 (rondas de 11/08 a 06/10), do registro da ronda no App. Desde 08/10 é fonte "
                    "do fato_ronda (casa pelo Início): a resposta fica no fato mesmo depois que a ronda sai da janela "
                    "de 90 dias do App"),
    # o Nexus é a FONTE deste (Levi, 07/10/2026): ronda lançada à mão por quem a fez, entrando com o login do Fracttal
    Fato("ronda_avulsa", "Ronda avulsa", "campo", "nexus_rondas_avulsas · fato_ronda_avulsa",
         "1 linha = 1 lançamento no Nexus: ronda avulsa, nível validado pela foto (origem validacao_foto) ou a "
         "anulação de um deles (anula_id preenchido)",
         _d(data=("id", "data_id"), usina=("id", "usina_id"),
            equipe=("id", "equipe_id (a equipe da usina, não a da ronda)"),
            pessoa=("id", "pessoa_id; pessoa_hmac quando o cadastro não acha a pessoa")),
         tipo="transacao", chave=("id",), estado="parte", parte_de=("ronda",),
         observacao="sem fotos, GPS nem OS; conta na cobertura. Nome e comentário só cifrados (Cofre). Entra no "
                    "fato_ronda só a avulsa válida (fora: a anulada, a linha de anulação e a validação por foto). "
                    "Domínio do App desde 08/10, antes da 1ª gravação (decisão 3 do Levi): vala sem 'Suja', sensor "
                    "'Sujo'/'Limpo'/vazio (não verificado) e a anulação só com anula_id. No banco desde 08/10: as 63 "
                    "linhas da validação por foto (GET em 09/10)"),
    # o Nexus é a FONTE deste (Levi, 13/10/2026): a observação do Responsável O&M sobre a usina, escrita na janela da Meta
    # da Visão do responsável, "salvo em algum canto do Nexus para posteriormente poder juntar esse comentário para
    # relatórios"
    Fato("observacao_responsavel", "Observação do responsável", "campo", "nexus_observacoes · fato_observacao_responsavel",
         "1 linha = 1 observação escrita no Nexus por 1 Responsável O&M sobre 1 usina",
         _d(data=("id", "data_id (o dia de Brasília em que foi escrita; mes_id = o mês que a janela mostrava)"),
            usina=("id", "usina_id"), pessoa=("id", "pessoa_id; pessoa_hmac quando o cadastro não acha a pessoa")),
         tipo="sem_medida", chave=("id",), fontes=("nexus_observacoes · fato_observacao_responsavel",),
         janela_origem="o Nexus é a fonte",
         observacao="o texto e o nome de quem escreveu só cifrados (Cofre, a chave do cadastro); do_responsavel = sim "
                    "quando quem escreveu é o Responsável O&M da usina, não quando cobria outro (férias). Só "
                    "responsável escreve (pelo login do Fracttal). O banco não apaga: nada se edita"),
    # Contratos e clientes → Contestações (Levi, 13/10/2026: "contestação ligada ao Nexus"; "ficaria na API do PG"). O
    # Dashboard Thopen (5080) é a FONTE: grava 1 linha por contestação × setor, a mesma divisão das mensagens do Teams.
    # Registrado antes da 1ª gravação. O que é do cliente vai só cifrado com a chave PÚBLICA (o 5080 não abre nada)
    # o acompanhamento de cada contestação (Levi, 15/10/2026: "um botão 'Pegar para mim' (...) onde o responsável poderá
    # inserir atualizações sobre a demanda com data e hora salva"). O Nexus é a FONTE; registrado antes da 1ª gravação
    Fato("tratamento_contestacao", "Acompanhamento da contestação", "contratos",
         "nexus_contestacoes_tratamento · fato_tratamento_contestacao",
         "1 linha = 1 evento (responsável que pegou, ou atualização escrita) sobre 1 contestação × 1 setor",
         _d(data=("id", "data_id (o dia de Brasília do evento)"),
            pessoa=("cod", "pessoa_hmac (o código do e-mail de quem pegou ou escreveu)")),
         tipo="sem_medida", chave=("id",), fontes=("nexus_contestacoes_tratamento · fato_tratamento_contestacao",),
         janela_origem="o Nexus é a fonte",
         observacao="contestacao_linha_id liga à linha do thopen_contestacoes (o id dela, 1 contestação × 1 setor); "
                    "evento = responsavel (o responsável de agora é o do último) ou atualizacao. Quem (nome e e-mail) e "
                    "o texto só cifrados (Cofre, a chave do cadastro). Só acrescenta: nada se edita nem se apaga"),
    Fato("contestacao_cliente", "Contestação do cliente", "contratos", "thopen_contestacoes · contestacoes",
         "1 linha = 1 contestação de 1 cliente sobre 1 dia (ou intervalo) de 1 usina × 1 setor (Performance, COS "
         "ou Zeladoria)",
         _d(data=("cod", "data_id_recebida; data_id_contestada_ini e _fim (papéis)"),
            usina=("id", "usina_id (o de-para do 5080; vazio quando a usina tem dois ids, como Primavera); usina em "
                         "nome")),
         tipo="sem_medida", chave=("id",), fontes=("thopen_contestacoes · contestacoes",),
         janela_origem="o 5080 é a fonte (tudo desde a 1ª contestação)",
         observacao="contestacao_id junta as linhas de uma contestação que foi aos dois setores. Nome, contato, "
                    "mensagem e o que o cliente via só em dados_cifrados (X25519 + AES-GCM; abre com "
                    "NEXUS_CONTESTACAO_CHAVE_PRIVADA, no Nexus). avisado_teams = sim/não: o Teams do setor recebeu. "
                    "O livro é trocado inteiro a cada contestação, relido antes e conferido depois"),
    Fato("pt", "Permissão de trabalho", "hseq", "pt_app_campo · PT", fato_pt.GRAO,
         _d(data=("id", "data_id_criacao, data_id_decisao (papéis)"), usina=("id", "usina_id"),
            equipe=("id", "equipe_id: papel registro (Região)"),
            pessoa=("id", "solicitante_pessoa_id, decisor_pessoa_id (+ os HMAC)"),
            equipamento=("id", "equipamento_id (Código do ativo)"), os=("cod", "os, pt")),
         tipo=fato_pt.TIPO, chave=fato_pt.CHAVE, medidas=_m(fato_pt.MEDIDAS), fontes=_fontes(fato_pt.FONTES),
         janela_origem=fato_pt.JANELA_ORIGEM, estado="conformado", conformado_em="nexus_fatos · fato_pt",
         observacao="até 08/10: '1 linha = 1 PT', mas eram 233 linhas para 227 números (o App decide por linha). PTs "
                    "= SUM(primeira_linha_da_pt). O decisor liga 0%: as 6 contas Admin estão fora do cadastro "
                    "(decisão 4). Sem o passo 0, a PT de 28/09 sai do fato em ~27/12"),
    # o Nexus é a FONTE deste: a decisão da PT assinada no Nexus com o login do Fracttal do OS Creator (05/10/2026);
    # quem aplica no campo é o App (nexus/campo/decisao_pt.py). Decisão 4 do Levi (11/10/2026): POR LINHA, como o App
    # decide (a PT × ativo do pt_app_campo), na aba fato_decisao_pt (era "decisoes", nunca gravada) com o codigo_ativo
    Fato("decisao_pt", "Decisão de PT no Nexus", "hseq", "nexus_pt_decisoes · fato_decisao_pt",
         "1 linha = 1 decisão (De acordo ou Não autorizo) sobre 1 linha da PT (PT × ativo, como o App decide), tomada "
         "no Nexus",
         _d(data=("id", "data_id"), usina=("id", "usina_id"), pessoa=("hmac", "decidida_por_hmac"),
            equipamento=("cod", "codigo_ativo (o Código do ativo da linha no pt_app_campo; vazio na PT sem ativo, "
                                "como a da APR do dia)"),
            os=("cod", "os, pt")),
         tipo="sem_medida", chave=("decidida_em", "pt", "codigo_ativo"),
         fontes=("nexus_pt_decisoes · fato_decisao_pt",), janela_origem="o Nexus é a fonte",
         observacao="decisão 4 do Levi (11/10/2026): o contrato com o App, que lê este livro, é a PT pelo número e a "
                    "linha pelo codigo_ativo (as colunas de 05/10, o codigo_ativo e a assinatura no fim: o App v257 só aplica a "
                    "linha assinada, HMAC da NEXUS_PESSOA_HMAC, decisao_pt.assinatura); o motivo vai mascarado, "
                    "porque o técnico lê; quem decidiu só em HMAC. Até 11/10 gravava só o número e pegava a 1ª linha "
                    "(GR-4: numa PT de 3 ativos não dizia a qual valia). O primeiro que decide a linha vale (o App "
                    "aplica só a 1ª de cada linha). Quem pediu a PT não a decide (decidida_por_hmac nunca é o "
                    "solicitante_hmac da linha no fato pt; o App descarta essa decisão). O App (v257) não confere "
                    "quem pode decidir: a trava é do Nexus, antes de gravar"),
    # a ronda de extintores do App (v247, 08/10/2026), que substituiu o Forms da TST; registrados antes de o App
    # publicar o livro (09/10/2026, a tela Extintores do HSEQ). O extintor é cadastro próprio do App, fora do Fracttal
    # (a planilha da TST + os achados pelo técnico); o `Ativo` é o código do Fracttal de ONDE ele fica. Dois grãos, dois
    # fatos, e um livro para cada um: o App sobe uma aba por livro (sync-xlsx com replace troca o livro inteiro)
    Fato("extintor", "Extintor (situação)", "hseq", "extintores_app_campo · Extintores",
         "1 linha = 1 extintor do cadastro, com a última conferência e as duas validades",
         _d(data=("cod", "Última conferência (dia de Brasília); papel 2: Não reconhecido em"),
            usina=("nome", "Usina (nome do Fracttal; de reserva, o código do Ativo e o Código da usina)"),
            pessoa=("hmac", "Conferido por; papel 2: Não reconhecido por"),
            equipamento=("cod", "Ativo: o código do Fracttal de onde o extintor fica (ele mesmo é cadastro próprio)")),
         tipo="snapshot_acumulado", chave=("Código",),
         medidas=_m((("itens_nao_qtd", "qtd", "aditiva"), ("fotos_qtd", "qtd", "aditiva"))),
         fontes=("extintores_app_campo · Extintores",), janela_origem="o cadastro inteiro, com a última conferência",
         observacao="a linha muda a cada conferência e nunca fecha. Atrasado, perto de vencer e sem atualização são "
                    "conta do Nexus no dia (nexus/hseq/extintores.py, a mesma regra da TST que o App usa); o Status do "
                    "livro é o do App na hora da publicação. A observação do técnico não vai (só 'Tem informação "
                    "adicional', sim/não). Carga única em 09/10/2026 pelo Nexus, do cadastro do App (773, "
                    "ferramentas/carregar_extintores_cadastro.py), até o App publicar (v257, que a substitui). Não "
                    "reconhecido em/por (14/10/2026, duas colunas no fim): a equipe não achou o extintor na usina; "
                    "conferência depois da marca a desfaz, e o Nexus o tira de todas as contas e o lista à parte para "
                    "a TST conferir o cadastro"),
    Fato("conferencia_extintor", "Conferência de extintor", "hseq", "extintores_conferencias_app_campo · Conferências",
         "1 linha = 1 extintor conferido num mês (reenviar no mesmo mês regrava a linha)",
         _d(data=("cod", "Dia (de Brasília)"), usina=("nome", "Usina (nome do Fracttal; Código da usina)"),
            pessoa=("hmac", "Conferido por"),
            equipamento=("prop", "Código do extintor (cadastro próprio do App, fora do Fracttal)")),
         tipo="snapshot_periodico", chave=("Código", "Mês"),
         medidas=_m((("itens_nao_qtd", "qtd", "aditiva"), ("fotos_qtd", "qtd", "aditiva"))),
         fontes=("extintores_conferencias_app_campo · Conferências",),
         janela_origem="todas as conferências feitas pelo App",
         observacao="o histórico das conferências pelo App (as do Forms da TST, antes dele, ficaram na planilha da "
                    "TST). Mesma regra da observação: só sim/não. Até o App publicar, o livro não existe"),
    Fato("decisao", "Decisão do painel", "campo", "decisoes_app_campo · Decisões",
         "1 linha = 1 decisão, tratamento ou devolução",
         _d(data=("cod", "Quando"), usina=("nome", "Usina (só Central de atenção)"), pessoa=("hmac", "3 papéis"),
            equipamento=("cod", "Código do ativo (devolução)"), os=("cod", "OS")),
         tipo="sem_medida", fontes=("decisoes_app_campo · Decisões",), janela_origem="90 dias (App)",
         observacao="sem chave: mistura 3 eventos (decisão, tratamento, devolução: GR-3); dividir antes de conformar"),
    Fato("zeladoria", "Zeladoria", "campo", "zeladoria_app_campo · Zeladoria", "1 linha = 1 etapa registrada",
         _d(data=("cod", "Data"), usina=("nome", "Usina"), pessoa=("hmac", "Registrado por"), os=("cod", "OS")),
         tipo="transacao", medidas=_m((("fotos_qtd", "qtd", "aditiva"), ("respostas_nao_qtd", "qtd", "aditiva"))),
         fontes=("zeladoria_app_campo · Zeladoria",), janela_origem="90 dias (App)",
         observacao="sem chave: definir quando houver linha (vazio até 05/10: a tela é da v226 e ninguém registrou)"),
    # o placar do ciclo de pontos do App (13/10/2026, Levi: "traga o ranking de pontos dos técnicos para o Nexus"): quem
    # calcula é o App (`_ciclo_v2`, régua PLACAR_V2), que publica o mês corrente e o anterior de hora em hora; a linha do
    # mês corrente muda a cada publicação até o mês fechar (foto acumulada). Tela: Campo · App > Ranking de pontos
    Fato("ranking_pontos", "Ranking de pontos do ciclo", "campo", "ranking_app_campo · Ranking",
         "1 linha = 1 técnico × 1 mês do ciclo de pontos (o placar como o App o calculou na hora da publicação)",
         _d(data=("cod", "Mês (AAAA-MM)"), pessoa=("hmac", "Técnico (HMAC)"), equipe=("nome", "Região")),
         tipo="snapshot_acumulado", chave=("Mês", "Técnico (HMAC)"),
         medidas=_m((("total_pts", "pts", "aditiva"), ("tarefas_pts", "pts", "aditiva"), ("rondas_pts", "pts", "aditiva"),
                     ("bonus_pts", "pts", "aditiva"), ("tarefas_qtd", "qtd", "aditiva"), ("rondas_qtd", "qtd", "aditiva"),
                     ("devolvidas_qtd", "qtd", "aditiva"), ("nota_media_pts", "pts", "nao"),
                     ("cumprimento_pct", "%", "nao"), ("pontualidade_pct", "%", "nao"))),
         fontes=("ranking_app_campo · Ranking",), janela_origem="o mês corrente e o anterior (App)",
         observacao="quem calcula é o App; o Nexus mostra, não recalcula (recalcular a nota deu 14% de acerto em 05/10). "
                    "A régua do mês vem nas colunas do próprio livro. Até o App publicar, o livro não existe"),
    Fato("fechamento_coletor", "Fechamento pelo coletor", "campo", "campo_nexus · fechamentos",
         "1 linha = 1 tarefa da fila do Fracttal",
         _d(data=("cod", "fim"), usina=("id", "usina_id"), equipe=("nome", "regiao"), pessoa=("id", "pessoa_id"),
            equipamento=("cod", "codigo"), os=("cod", "os")),
         tipo="transacao", chave=("id_tarefa",), estado="aposentado",
         observacao="aposentado em 05/10: a nota batia com a do painel do App em só 14% das tarefas. Os códigos de "
                    "ativo dele ainda alimentam a dimensão de equipamento"),
    # ── Performance ────────────────────────────────────────────────────────────────────────────────────────────
    # geração em linhas (08/10/2026, passo 6c): a fonte larga (um inversor por coluna) vira dois fatos
    # Fontes do tempo real (11/10/2026, Levi: "um espaço para administração do que entra no tempo real onde eu possa
    # através da fonte permitir qual usina entra e qual não entra"). Quem grava é a tela da plataforma (/admin/tempo-real,
    # só admin; plataforma/cobertura.py no PerformancePainel); a plataforma do PC e a do servidor leem com cache de 60 s e
    # filtram a lista de cada fonte ANTES da coleta (Tempo real, Monitoramento, Painel NOC e ronda).
    Fato("decisao_cobertura", "Decisão de cobertura do tempo real", "performance",
         "nexus_tempo_real · fato_decisao_cobertura",
         "1 linha = 1 decisão de incluir ou excluir 1 usina (a chave nativa da fonte) de 1 fonte do tempo real",
         _d(data=("id", "data_id (o dia de Brasília da decisão)"),
            usina=("nao", "a chave nativa da fonte (plant_id da API PV, id da SunOp, site da SolarEdge, power_plant_id "
                          "do banco, id do scadaGridco): o plant_id por fonte ainda não está no de_para (pendência 10)")),
         tipo="sem_medida", chave=("decidida_em", "fonte", "chave"),
         fontes=("nexus_tempo_real · fato_decisao_cobertura",),
         janela_origem="o Nexus é a fonte (só acrescenta: o vigente é a última decisão de cada fonte e chave)",
         observacao="fonte = a chave da aba do Monitoramento (pv, pg, sunop, axis, solaredge, semp, alveslima, 2capi, "
                    "greenyellow, salenergia); origem 'migracao' = a foto do dia em que a fonte passou a ser controlada "
                    "pela tela, 'tela' = a decisão de um administrador. Quem decidiu fica no log da máquina "
                    "(logs/cobertura.log da plataforma), não no banco (regra 8)"),
    # De-para de equipamentos (11/10/2026, Levi: "quero que o de-para da equipamentos seja feito na plataforma de forma
    # intuitiva"): a tela /admin/de-para da plataforma liga a usina que a API renomeou (pelo id) e o inversor que a fonte
    # não nomeia (conta oem@ da API PV, scadaGridco) ao cadastro. A decisão vence o de-para em código da plataforma.
    # 12/10/2026 (Levi: "precisamos trazer para o Nexus e deixar mais dinâmico com a plataforma"): também o APELIDO da
    # usina que a fonte manda só pelo nome (Athon, Axis: a chave é o nome), que antes exigia editar o Excel do cadastro.
    Fato("decisao_depara", "Decisão de de-para de equipamento", "performance",
         "nexus_depara · fato_decisao_depara",
         "1 linha = 1 decisão de ligar 1 usina (o id dela na fonte, ou o nome nas fontes que mandam só o nome) ou 1 "
         "inversor (o id dele na fonte) de 1 fonte ao cadastro (aba Equipamentos do BD_Performance)",
         _d(data=("id", "data_id (o dia de Brasília da decisão)"),
            usina=("nao", "usina_fonte (o id na fonte) + usina_supervisorio (chave de negócio do Equipamentos); o "
                          "plant_id por fonte ainda não está no de_para (pendência 10)"),
            equipamento=("nao", "inversor_fonte (o id na fonte) + equipamento_supervisorio (chave de negócio do "
                                "Equipamentos)")),
         tipo="sem_medida", chave=("decidida_em", "fonte", "usina_fonte", "inversor_fonte"),
         fontes=("nexus_depara · fato_decisao_depara",),
         janela_origem="o Nexus é a fonte (só acrescenta: o vigente é a última decisão de cada fonte, usina e inversor)",
         observacao="fonte = a chave da aba do Monitoramento; a usina liga nas contas da API PV (pv, semp, alveslima, "
                    "2capi) e o inversor na conta principal (pv, desde 12/10/2026), na conta oem@ (semp, alveslima, 2capi) e no scadaGridco (greenyellow, "
                    "salenergia); o apelido pelo nome, nas fontes que mandam a usina só pelo nome (sunop, axis: "
                    "usina_fonte = o nome exatamente como a fonte escreve). inversor_fonte vazio = a linha é da usina. "
                    "Valor vazio = desfaz (vale o nome da API ou "
                    "o de-para em código). O cadastro entra pela chave de negócio, que a plataforma confere antes de "
                    "gravar (nunca texto livre). Quem decidiu fica no log da máquina (logs/depara.log da plataforma), "
                    "não no banco (regra 8)"),
    # Setor do pessoal do Fracttal (12/10/2026, Levi: "Como faço para definir um setor???? tem que dar possibilidade"):
    # o Fracttal não tem setor e ainda não há base; a tela Base > Integração Fracttal cria a lista (dim_setor, no mesmo
    # livro) e põe cada pessoa num setor.
    Fato("decisao_setor", "Decisão de setor do pessoal", "base", "nexus_setores · fato_decisao_setor",
         "1 linha = 1 decisão de pôr 1 pessoa do Fracttal em 1 setor, ou de tirá-la (setor_id vazio), tomada por um "
         "administrador na tela Integração Fracttal",
         _d(data=("id", "data_id (o dia de Brasília da decisão)"),
            pessoa=("id", "pessoa_id quando a pessoa do Fracttal tem ficha (o critério do login; pessoa_ligada_por diz "
                          "como; vazio = sem ficha) + fracttal_id (o id_personnel) + pessoa_hmac (o código do e-mail)")),
         tipo="sem_medida", chave=("decidida_em", "fracttal_id"),
         fontes=("nexus_setores · fato_decisao_setor",),
         janela_origem="o Nexus é a fonte (só acrescenta: o setor de cada pessoa é a última decisão dela)",
         observacao="o setor liga pelo setor_id à dim_setor do mesmo livro (a lista nasce na tela; excluir marca "
                    "excluido = sim e o ID não volta). As duas abas vão juntas a cada gravação (gravar sem uma a "
                    "apagaria). Nada de nome nem e-mail (regra 8): quem decidiu vai em decidida_por_hmac e no log da "
                    "máquina"),
    # O que cada setor vê no Nexus (12/10/2026, Levi: "uma seção no BASE > ACESSOS onde eu possa controlar o que cada
    # pessoa de setor pode ver ao logar no Nexus"): a matriz setor × tela do menu, marcada na tela Base > Acessos.
    Fato("decisao_tela_setor", "Decisão de tela por setor", "base", "nexus_setor_telas · fato_decisao_tela_setor",
         "1 linha = 1 decisão de liberar (liberada = sim) ou fechar (nao) 1 tela do menu do Nexus para 1 setor, tomada "
         "por um administrador na tela Acessos",
         _d(data=("id", "data_id (o dia de Brasília da decisão)")),
         tipo="sem_medida", chave=("decidida_em", "setor_id", "tela"),
         fontes=("nexus_setor_telas · fato_decisao_tela_setor",),
         janela_origem="o Nexus é a fonte (só acrescenta: o que vale é a última decisão de cada setor × tela)",
         observacao="o setor liga pelo setor_id à nexus_setores · dim_setor; a tela é o endereço do menu "
                    "(torre/tela, o mesmo de /t/torre/tela). Tela nunca marcada = fechada; administrador do Nexus vê "
                    "tudo sem precisar de marca (setor nenhum dá administrador). Nada de nome nem e-mail (regra 8): quem decidiu vai em "
                    "decidida_por_hmac e no log da máquina"),
    # O setor dono de cada relatório da Central de emissão (14/10/2026, Levi: "adicione a opção de eu escolher de qual
    # setor é o relatório! Apenas administradores podem editar!"): por cima do padrão do código (Tela.do_setor).
    Fato("decisao_dono_relatorio", "Setor dono de cada relatório", "base",
         "nexus_relatorio_setor · fato_decisao_dono_relatorio",
         "1 linha = 1 decisão do setor dono de 1 relatório da Central de emissão (setor vazio = nenhum setor), tomada "
         "por um administrador na própria Central",
         _d(data=("id", "data_id (o dia de Brasília da decisão)")),
         tipo="sem_medida", chave=("decidida_em", "tela"),
         fontes=("nexus_relatorio_setor · fato_decisao_dono_relatorio",),
         janela_origem="o Nexus é a fonte (só acrescenta: o que vale é a última decisão de cada relatório)",
         observacao="o setor liga pelo setor_id à nexus_setores · dim_setor; a tela é o endereço do relatório "
                    "(relatorios/<tela>). O setor dono vê o relatório sem marca na matriz de Base > Acessos; sem "
                    "decisão vale o setor padrão do código, pelo nome. Nada de nome nem e-mail (regra 8): quem decidiu "
                    "vai em decidida_por_hmac e no log da máquina"),
    # A curadoria do PCM no Acompanhamento (14/10/2026, Levi, com o pacote do painel de acompanhamento do PCM O&M: "Quero
    # que libere na seção de PCM essa visão de acompanhamento"): o que a reunião de PCM decide sobre cada MPA e MPS
    # acompanhada (grupo, prazo do relatório, o que falta); no painel era um arquivo num computador.
    Fato("decisao_curadoria_pcm", "Curadoria das MPAs e MPSs do PCM", "pcm",
         "nexus_pcm_curadoria · fato_decisao_curadoria",
         "1 linha = 1 decisão da reunião de PCM sobre 1 MPA ou MPS acompanhada (item_id), ou sobre a regra do "
         "responsável da Manutenção (item_id manutencao); ativo \"não\" tira o item do painel",
         _d(data=("id", "data_id (o dia de Brasília da decisão)")),
         tipo="sem_medida", chave=("decidida_em", "item_id"),
         fontes=("nexus_pcm_curadoria · fato_decisao_curadoria",),
         janela_origem="o Nexus é a fonte (só acrescenta: o que vale é a última decisão de cada item)",
         observacao="o conteúdo (usina, OS, responsável, o que falta, observação) vai cifrado com a chave do cadastro em "
                    "dados_cifrados (regra 8: a API tem leitura aberta e ali há nome de gente); em claro só o item, o "
                    "tipo e o grupo. As pendências e o progresso não são da curadoria: o Acompanhamento recalcula pelo "
                    "Fracttal (o gestao_pcm.json) a cada leitura. A 1ª carga veio do arquivo do painel do PCM de "
                    "14/10/2026 (ferramentas/carregar_curadoria_pcm.py)"),
    # Os motivos das tarefas do PCM e o backoffice (16/10/2026, Levi, com a lista dos 11 motivos e "Quando a OS estiver
    # atrelada como responsável para alguém do time de backoffice, desconsiderar para a programação da semana"): o
    # Nexus é a FONTE; o cadastro dos motivos (dim_motivo) mora no mesmo livro. Registrado antes da 1ª gravação.
    Fato("decisao_motivo_pcm", "Motivo das tarefas do PCM", "pcm", "nexus_pcm_motivos · fato_decisao_motivo",
         "1 linha = 1 decisão sobre o motivo de 1 tarefa (OS + código do ativo + nome; item_id): marcar um motivo "
         "(motivo_id) ou tirá-lo (motivo_id vazio); um motivo por tarefa, vale a última decisão de cada tarefa",
         _d(data=("id", "data_id (o dia de Brasília da decisão)"),
            equipamento=("id", "equipamento_id (o código do ativo; vazio na marca feita pelo número da OS, que vale "
                               "para a tarefa em todos os ativos dela)"),
            pessoa=("cod", "decidida_por_hmac (o código do e-mail de quem marcou no Nexus, ou o código do técnico "
                           "que marcou pelo App, origem app; vazio com a senha de administrador)"),
            os=("cod", "os")),
         tipo="sem_medida", chave=("decidida_em", "item_id"),
         fontes=("nexus_pcm_motivos · fato_decisao_motivo",),
         janela_origem="o Nexus é a fonte (só acrescenta: o que vale é a última decisão de cada tarefa)",
         observacao="o motivo liga pelo motivo_id à dim_motivo do mesmo livro (o cadastro: excluir marca excluido = "
                    "sim e o ID não volta; a marca de motivo excluído deixa de valer). tira_da_programacao = sim: a "
                    "geração da semana não programa a tarefa e o robô do PCM a tira da semana em curso. A tarefa entra "
                    "como tarefa_chave (a mesma conta da programação e do fechamento) e o texto, a usina, a observação "
                    "e quem marcou vão só cifrados em dados_cifrados (regra 8). As três abas vão juntas a cada "
                    "gravação. O Nexus publica o estado no Fora_da_programacao.json do repositório do PCM (o robô e o "
                    "App leem)"),
    Fato("decisao_backoffice_pcm", "Lista do backoffice do PCM", "pcm", "nexus_pcm_motivos · fato_decisao_backoffice",
         "1 linha = 1 decisão de pôr ou tirar 1 nome da lista do backoffice (nome_hmac); vale a última decisão de "
         "cada nome",
         _d(data=("id", "data_id (o dia de Brasília da decisão)"),
            pessoa=("cod", "nome_hmac (o código do nome, como ele aparece no responsável da OS do Fracttal) e "
                           "decidida_por_hmac (quem decidiu)")),
         tipo="sem_medida", chave=("decidida_em", "nome_hmac"),
         fontes=("nexus_pcm_motivos · fato_decisao_backoffice",),
         janela_origem="o Nexus é a fonte (só acrescenta)",
         observacao="a OS cujo responsável no Fracttal é um nome da lista (sem acento e sem caixa) fica fora da "
                    "geração da semana e o robô do PCM não a inclui como OS nova. O nome vai só cifrado "
                    "(dados_cifrados); o arquivo do robô, no repositório do PCM, leva os nomes em claro (decisão do "
                    "Levi, 16/10/2026: \"faz o simples\")"),
    # Os técnicos por usina (17/10/2026, Levi: "cria uma estrutura que liga usina e técnico e o PCM pode editar a
    # vontade" e "quero tirar do site de gestão"): o Nexus é a FONTE de quem cobre cada usina; o App de Campo lê daqui o
    # papel executa (as usinas da aba Ronda). Registrado antes da 1ª gravação.
    Fato("decisao_atribuicao_pcm", "Técnicos por usina", "pcm", "nexus_pcm_atribuicoes · fato_decisao_atribuicao",
         "1 linha = 1 decisão de pôr ou tirar 1 pessoa de 1 usina num papel (executa); vale a última decisão de cada "
         "usina, pessoa e papel",
         _d(data=("id", "data_id (o dia de Brasília da decisão; de_data_id e ate_data_id, o período do apoio)"),
            usina=("id", "usina_id (+ usina_fracttal, o nome da usina no Fracttal, por onde o App a acha)"),
            pessoa=("id", "pessoa_id + pessoa_hmac (o código do e-mail, por onde o App acha a pessoa) e "
                          "decidida_por_hmac (quem decidiu)")),
         tipo="sem_medida", chave=("decidida_em", "usina_id", "pessoa_id", "papel"),
         fontes=("nexus_pcm_atribuicoes · fato_decisao_atribuicao",),
         janela_origem="o Nexus é a fonte (só acrescenta: o que vale é a última decisão de cada usina, pessoa e papel)",
         observacao="executa = quem vê e pode rondar a usina no App de Campo (a aba Ronda). O apoio é a mesma ligação "
                    "com de_data_id e ate_data_id: vale do 1º ao último dia, sem ninguém precisar tirar. Cada linha "
                    "vai assinada (assinatura, HMAC com a chave derivada da NEXUS_PESSOA_HMAC): o App lê o livro pela "
                    "leitura aberta da API e só aplica a linha assinada, quando o interruptor dele "
                    "(NEXUS_ATRIBUICOES) estiver ligado. A observação do PCM vai só cifrada (dados_cifrados, regra 8). "
                    "A carga inicial (origem carga_inicial) é a regra da equipe do cadastro: cada pessoa de campo "
                    "recebe as usinas da equipe dela"),
    Fato("geracao_usina_dia", "Geração diária por usina", "performance",
         "bd_thopen · bd_performance (1 aba por usina)", geracao.GRAO_USINA,
         _d(data=("id", "data_id"),
            usina=("id", "usina_id pelo de-para 'BD_Thopen · aba' / 'BD_Performance · aba' (vazio = usina_motivo)")),
         tipo=geracao.TIPO, chave=geracao.CHAVE_USINA, medidas=_m(geracao.MEDIDAS_USINA),
         fontes=("bd_thopen · 1 aba por usina", "bd_performance · 1 aba por usina"),
         estado="conformado", conformado_em="nexus_geracao · fato_geracao_usina_dia",
         observacao="produto dos BDs, que seguem a fonte: grava depois de cada subida do bd_thopen ou do bd_performance "
                    "(decisão 8 do Levi, 11/10/2026: de-para das abas publicado, teto = potência × 24 h, IPOA do "
                    "bd_performance só o DEF). Aba que perde dias recusa a gravação. Os 3 agregados do inversor × dia "
                    "não se somam com ele"),
    Fato("geracao_inversor_dia", "Geração diária por inversor", "performance",
         "bd_thopen · bd_performance (1 aba por usina)", geracao.GRAO_INVERSOR,
         _d(data=("id", "data_id"), usina=("id", "usina_id (o da aba)"),
            equipamento=("id", "equipamento_id pelo apelido 'BD_* · coluna'")),
         tipo=geracao.TIPO, chave=geracao.CHAVE_INVERSOR, medidas=_m(geracao.MEDIDAS_INVERSOR),
         fontes=("bd_thopen · 1 aba por usina", "bd_performance · 1 aba por usina"), estado="conformado", conformado_em="nexus_geracao_inversor_AAAA_MM · fato_geracao_inversor_dia",
         observacao="~700 mil linhas (29 a 36 MB de xlsx) não cabiam em troca integral: um livro por mês, nexus_geracao_inversor_AAAA_MM (decisão 8 do Levi, 11/10/2026), e só o mês que mudou é regravado"),
    Fato("geracao_thopen", "Geração diária (Thopen)", "performance", "bd_thopen · 1 aba por usina",
         "1 linha = usina × dia",
         _d(data=("cod", "Data"), usina=("nome", "Usina (aba)"), equipamento=("largo", "SKID 1…, Inversor 1.1…")),
         tipo="snapshot_periodico", chave=("aba", "Data"), estado="parte",
         parte_de=("geracao_usina_dia", "geracao_inversor_dia"),
         observacao="desde 08/10 vira linhas (regra 1: fonte larga vira linhas antes de entrar)"),
    Fato("geracao_demais", "Geração diária (demais)", "performance", "bd_performance · 1 aba por usina",
         "1 linha = usina × dia",
         _d(data=("cod", "Data"), usina=("nome", "aba: nome da usina em 43, código em 10"),
            equipamento=("largo", "Inversor 1.1…")),
         tipo="snapshot_periodico", chave=("aba", "Data"), estado="parte",
         parte_de=("geracao_usina_dia", "geracao_inversor_dia"),
         observacao="até 08/10 o catálogo dizia 'aba = código (MAB100)': vale em 10 das 53 abas de geração. Desde "
                    "08/10 a aba liga pelo de-para 'BD_Performance · aba' (o Código Fractal da Info Geral)"),
    Fato("meta_mensal", "Meta e histórico mensal", "performance", "bd_thopen · Dados Mensais, Historico",
         "1 linha = usina × mês", _d(data=("cod", "Mês"), usina=("nome", "Usina")),
         tipo="snapshot_periodico", chave=("Usina", "Mês"),
         medidas=_m((("meta_kwh", "kWh", "aditiva"), ("pr_pct", "%", "nao"), ("ipoa_meta_kwh_m2", "kWh/m²", "semi"))),
         fontes=("bd_thopen · Dados Mensais", "bd_thopen · Historico")),
    # plant_id no FIM das abas de episódio (08/10/2026, Operação no Mês do Dashboard Thopen): pelo nome, a Brodowski
    # junta os dois cadastros dela na API PV (uma metade com 52 trackers parados, a outra com 51) e dá 52 trackers em
    # vez de 103. Por isso a chave dos episódios é pelo plant_id: pelo nome, a do tracker repetia (medido nos pacotes
    # do PC em 08/10: 243 chaves em setembro e 132 em outubro, Brodowski, Fernandópolis, Barretos, Assis; pelo
    # plant_id, 0). O strings_inversor_dia agrega usina × inversor × dia e continua sem plant_id.
    # Campo novo vazio é NÃO MEDIDO (mês montado antes do deploy da plataforma; a janela está em nexus/dados/CLAUDE.md,
    # "Falhas da plataforma com plant_id"): lido como 0, viraria o "nenhum tracker parou com a usina comunicando" ou o
    # "nenhuma usina monitorada" que o spec da Operação no Mês manda barrar
    # GR-2 (auditoria 08/10): um registro só para dois grãos; virou fonte dos dois fatos abaixo, sem apagar a história
    Fato("falha_string", "Falha de string", "performance",
         "falhas_performance · strings_episodios, strings_inversor_dia", "1 linha = 1 episódio · inversor × dia",
         _d(data=("cod", "saiu / dia"), usina=("cod", "plant_id nos episódios (08/10/2026); usina em nome"),
            cliente=("nome", "cliente"), equipamento=("nome", "inversor, string")),
         tipo="snapshot_acumulado", estado="parte", parte_de=("falha_string_episodio", "falha_string_inversor_dia"),
         observacao="até 08/10 um registro só para dois grãos (GR-2): episódio e inversor × dia são dois fatos"),
    Fato("falha_string_episodio", "Falha de string (episódio)", "performance", "falhas_performance · strings_episodios",
         "1 linha = 1 episódio de string fora (saiu → voltou)",
         _d(data=("cod", "saiu"), usina=("cod", "plant_id nos episódios (08/10/2026); usina em nome"),
            cliente=("nome", "cliente"), equipamento=("nome", "inversor, string")),
         tipo="snapshot_acumulado", chave=("fonte", "plant_id", "inversor", "string", "saiu"),
         medidas=_m((("perda_kwh", "kWh", "aditiva"),)), fontes=("falhas_performance · strings_episodios",),
         observacao="o episódio aberto muda até voltar (foto acumulada). plant_id em todo mês publicado (o pacote do "
                    "mês já o trazia)"),
    Fato("falha_string_inversor_dia", "Falha de string (inversor × dia)", "performance",
         "falhas_performance · strings_inversor_dia", "1 linha = 1 inversor × 1 dia com string fora",
         _d(data=("cod", "dia"), usina=("nome", "usina (+ fonte)"), cliente=("nome", "cliente"),
            equipamento=("nome", "inversor")),
         tipo="snapshot_periodico", chave=("fonte", "usina", "inversor", "dia"),
         medidas=_m((("perda_kwh", "kWh", "aditiva"),)), fontes=("falhas_performance · strings_inversor_dia",),
         observacao="agrega usina × inversor × dia e continua sem plant_id (liga só pelo nome)"),
    Fato("falha_tracker", "Falha de tracker", "performance", "falhas_performance · trackers_episodios",
         "1 linha = 1 episódio",
         _d(data=("cod", "parou"), usina=("cod", "plant_id da fonte (08/10/2026); usina em nome"),
            cliente=("nome", "cliente"), equipamento=("nome", "tracker, inversor")),
         tipo="snapshot_acumulado", chave=("fonte", "plant_id", "tracker", "parou"),
         medidas=_m((("perda_kwh", "kWh", "aditiva"), ("duracao_min", "min", "aditiva"))),
         fontes=("falhas_performance · trackers_episodios",),
         observacao="dias_comunicou: dias do episódio, no mês, em que a USINA (qualquer fonte e cadastro dela) leu "
                    "string ou gerou. dias_sem_prova: dias do episódio ainda não fechados e sem prova (volta a 0 quando "
                    "o dia fecha). Vazio = não medido, nunca 0"),
    # tracker × dia (08/10/2026, revisão da tarde: a análise de performance pediu a tabela do Diário por dia). Grão
    # diferente do episódio:
    # outro fato (regra 1, como a falha de string), e o falha_tracker fica com o id dele
    Fato("falha_tracker_dia", "Falha de tracker (usina × dia)", "performance", "falhas_performance · trackers_dia",
         "1 linha = 1 usina × fonte × plant_id × 1 dia com tracker parado e a usina comunicando",
         _d(data=("cod", "dia"), usina=("cod", "plant_id da fonte; usina em nome"), cliente=("nome", "cliente"),
            equipamento=("nome", "trackers (lista)")),
         tipo="snapshot_periodico", chave=("fonte", "plant_id", "dia"), fontes=("falhas_performance · trackers_dia",),
         # na fonte a coluna é qtd; conformada vira trackers_qtd. Soma entre plant_id e usinas no mesmo dia; no tempo dá
         # tracker × dia, e não trackers distintos (o card do Dashboard Thopen conta os distintos pela lista)
         medidas=_m((("trackers_qtd", "qtd", "semi"),)),
         observacao="comunicou: 'sim' (a usina leu string ou gerou) ou 'sem prova' (dia corrente sem geração "
                    "fechada); o dia em que a usina não comunicou não entra. Trackers distintos no mês pela lista, "
                    "nunca pela soma da qtd"),
    # Levi, 08/10/2026: usina sem linha nos episódios não é "usina sem falha" — pode ser usina que a plataforma nem
    # mede. Sem esta aba, o card do Dashboard Thopen mostraria 0 onde o certo é "sem monitoramento"
    Fato("cobertura_falhas", "Cobertura do registro de falhas", "performance", "falhas_performance · cobertura",
         "1 linha = mês × fonte × plant_id (dias medidos de strings e de trackers)",
         _d(data=("cod", "mes"), usina=("cod", "plant_id da fonte; usina em nome"), cliente=("nome", "cliente")),
         tipo="snapshot_periodico", chave=("mes", "fonte", "plant_id"), fontes=("falhas_performance · cobertura",),
         # na fonte a coluna é dias_comunicou; conformada vira dias_comunicou_qtd (regra 3: unidade no nome). É da usina,
         # repetida em cada plant_id dela: não soma entre linhas
         medidas=_m((("dias_comunicou_qtd", "dias", "nao"),)),
         observacao="Separa 'sem falha' de 'sem monitoramento'. atualizacao.cobertura vazio = não medido; com número, "
                    "o plant_id sem linha = sem monitoramento. dias_comunicou é da USINA, repetido em cada plant_id "
                    "dela: não somar entre linhas"),
    # "Strings é OS" (Levi, 08/10/2026, revisão da tarde): a string do Dashboard Thopen vem da OS de recomposição do
    # Fracttal, pela data do evento, e não da régua de 2 h da plataforma. Outro processo (a ordem de serviço, não o
    # episódio medido): outro fato. 'texto' é a linha "Strings sem corrente: N (Ipv3, ...)" que o OS Creator escreve
    # nas observações; 'estimado' é a Grid completando as OS de outubro/2026 pelo monitoramento, sem tocar no Fracttal
    Fato("os_string", "OS de string", "performance", "falhas_performance · strings_os",
         "1 linha = 1 OS de recomposição de string do Fracttal com a data do evento no mês",
         _d(data=("cod", "data_evento (event_date do Fracttal, dia de Brasília)"),
            usina=("cod", "plant_id; usina em nome"), cliente=("nome", "cliente"),
            equipamento=("nome", "inversor; strings (lista)"), os=("cod", "os (dimensão degenerada)")),
         tipo="snapshot_acumulado", chave=("mes", "os"), fontes=("falhas_performance · strings_os",),
         # na fonte a coluna é qtd; conformada vira strings_qtd. A soma é strings × OS: a mesma string em duas OS conta
         # duas vezes (strings distintas saem da lista)
         medidas=_m((("strings_qtd", "qtd", "aditiva"),)),
         observacao="origem: texto, citadas, estimado ou sem_quantidade. Sem quantidade = qtd vazio, nunca 0. A OS "
                    "muda até fechar (status; a quantidade escrita depois troca a origem)"),
    # Rodada 4 do Dashboard Thopen (Levi, 09/10/2026): a coluna Disp (%) da tabela do Diário "calculada pelo Fracttal, da
    # mesma forma que calculamos pelo gerencial da plataforma". A plataforma publica o diário do índice do Gerencial ›
    # Disponibilidade (frac_disp_index.json), sem chamada nova ao Fracttal; o dia sem OS vem escrito (100 e 0 h). Desde
    # 15/10/2026 (Levi): de 10/2026 em diante só as OS do Fracttal, isolada da geração; setembro para trás, a
    # "Disponibilidade Usina (%)" do BD_Thopen, só as usinas da Thopen
    Fato("disponibilidade_dia", "Disponibilidade da usina por dia (Gerencial)", "performance",
         "falhas_performance · disponibilidade_dia",
         "1 linha = 1 usina do catálogo do Gerencial × 1 dia fechado do mês",
         _d(data=("cod", "dia"), usina=("nome", "usina (nome do Gerencial); usina_fracttal liga pelo de_para "
                                                "(Fracttal · Classificação 1)"),
            cliente=("nome", "cliente")),
         tipo="snapshot_periodico", chave=("mes", "dia", "usina"), fontes=("falhas_performance · disponibilidade_dia",),
         # na fonte: disp (%) e h_perdidas (horas equivalentes das OS, ponderadas pela potência). A % não soma; as horas
         # somam no tempo de uma usina, não entre usinas
         medidas=_m((("disp_pct", "%", "nao"), ("indisponibilidade_min", "min", "semi"))),
         janela_origem="o mês corrente e o anterior (o índice do Gerencial); mês que sai fica como foi publicado",
         observacao="disp = 100·(1 − h_perdidas/12); o 5080 calcula pelas horas (o disp de 1 casa desviava a média do "
                    "mês). De 10/2026 em diante só as OS do Fracttal (a geração não entra); setembro para trás, a "
                    "Disponibilidade Usina (%) do BD_Thopen, só a Thopen. Um site do Fracttal pode ser de duas usinas "
                    "(Aparecida do Taboado 1 e 2): ligar pelo nome primeiro"),
    Fato("parada_tracker", "Parada de tracker", "performance", "plataforma_series · trk_eventos",
         "1 linha = 1 parada", _d(data=("cod", "dia"), usina=("cod", "plant_id da fonte"),
                                  equipamento=("nome", "tracker")),
         tipo="transacao", chave=("plant_id", "tracker", "parada"), medidas=_m((("duracao_min", "min", "aditiva"),)),
         fontes=("plataforma_series · trk_eventos",)),
    # ── Gêmeo digital ──────────────────────────────────────────────────────────────────────────────────────────
    Fato("perda_equipamento", "Perda por equipamento", "performance",
         "gemeo_digital · perda_dia, cascata_dia, evento", "1 linha = usina × dia × equipamento × parcela",
         _d(data=("cod", "dia"), usina=("prop", "usina (25, do gêmeo)"),
            equipamento=("prop", "equipamento (9.918 + apelidos)")),
         tipo="snapshot_periodico", chave=("usina", "dia", "equipamento", "parcela"),
         medidas=_m((("perda_kwh", "kWh", "aditiva"),)), fontes=("gemeo_digital · perda_dia",),
         observacao="o tracker e o inversor do gêmeo já têm apelido na dimensão de equipamento (Gêmeo · equipamento)"),
    # ── Meta do mês por usina (Gerencial da plataforma) ────────────────────────────────────────────────────────────
    # Visão do responsável (12/10/2026, Levi: "construa a visão dos responsáveis da usina!"): a meta do mês de cada usina
    # sai do Gerencial da plataforma, a MESMA conta da Visão gerencial (`_gerencial_payload`), publicada pelo worker do
    # servidor de hora em hora e só quando muda (plataforma/gerencial_publicar.py). O Nexus só lê (Campo · App > Visão
    # do responsável), ligando o nome à usina do cadastro na hora.
    Fato("meta_usina_mes", "Meta do mês por usina (Gerencial)", "performance",
         "nexus_performance · fato_meta_usina_mes",
         "1 linha = 1 usina do Gerencial (a aba do BD ou a carteira do banco da Thopen) × 1 mês",
         _d(data=("cod", "mes_id (AAAAMM)"),
            usina=("nome", "usina (nome do Gerencial); a Visão do responsável liga pelo de_para das abas (BD_Thopen · "
                           "aba, BD_Performance · aba e as duas de cadastro) e, sem ele, pelo nome do cadastro"),
            cliente=("nome", "cliente, carteira")),
         tipo="snapshot_acumulado", chave=("mes_id", "usina"),
         medidas=_m((("prod_kwh", "kWh", "aditiva"), ("meta_kwh", "kWh", "aditiva"), ("atingimento_pct", "%", "nao"),
                     ("pr_pct", "%", "nao"), ("pr_meta_pct", "%", "nao"), ("ipoa_kwh_m2", "kWh/m²", "semi"),
                     ("ipoa_meta_kwh_m2", "kWh/m²", "semi"), ("dias_cobertos_qtd", "qtd", "nao"),
                     ("dias_mes_qtd", "qtd", "nao"), ("meta_dias_qtd", "qtd", "nao"), ("full_om", "1/0", "nao"))),
         fontes=("nexus_performance · fato_meta_usina_mes",),
         janela_origem="os meses publicados desde 10/2026: o corrente se refaz de hora em hora e o anterior até o dia "
                       "5; os outros ficam como foram publicados",
         observacao="a meta é a do mês até os dias cobertos (o Gerencial prorrateia: atingimento = produção ÷ meta). "
                    "fonte = de onde veio a produção (pg = banco da Thopen, bd = BD_Performance); meta_fonte = de onde "
                    "veio a meta (BD_Thopen, Info Mensal ou o P50 anual ÷ 12). A energia vai em kWh (o Gerencial mostra "
                    "MWh com 1 casa). O motivo do PR sem confiança (texto) fica de fora (regra 8). Grava só o worker do "
                    "servidor (Linux); GER_PUBLICAR=1 força numa máquina"),
    # As janelas da Visão do responsável (12/10/2026, Levi: "PR ao clicar aparece um card (...) essa mesma visão do PAINEL
    # NOC > HISTÓRICO > PR > PR DIÁRIO EXPANDIDO"; a meta "com uma tabelinha de dia do mês, geração meta, geração real"):
    # o dia a dia do Gerencial (a geração que fecha no atingimento, 13/10/2026) com o POA e o PR do PR diário do Painel
    # NOC (`/api/g/diario`), publicado com a meta do mês pelo worker do servidor
    Fato("desempenho_usina_dia", "Desempenho da usina por dia (Gerencial e Painel NOC)", "performance",
         "nexus_performance · fato_desempenho_usina_dia",
         "1 linha = 1 usina do Gerencial × 1 dia que o Gerencial conta no atingimento (ou com PR no PR diário)",
         _d(data=("cod", "data_id (o dia; mes_id = AAAAMM)"),
            usina=("nome", "usina (nome do Gerencial); a Visão do responsável liga pelo de_para das abas e pelo nome do "
                           "cadastro, como a meta do mês")),
         tipo="snapshot_acumulado", chave=("mes_id", "usina", "data_id"),
         medidas=_m((("geracao_kwh", "kWh", "aditiva"), ("meta_kwh", "kWh", "aditiva"), ("ipoa_kwh_m2", "kWh/m²", "semi"),
                     ("ipoa_meta_kwh_m2", "kWh/m²", "semi"), ("pr_pct", "%", "nao"), ("pr_meta_pct", "%", "nao"))),
         fontes=("nexus_performance · fato_desempenho_usina_dia",),
         janela_origem="os meses publicados desde 10/2026 (o corrente de hora em hora; o anterior até o dia 5)",
         observacao="geracao_kwh = a geração do dia que o Gerencial conta no atingimento: a soma dos dias fecha no "
                    "prod do mês (vazio = dia só do PR diário, fora da conta); meta_kwh = a meta do mês ÷ os dias do mês "
                    "(a do Gerencial, sem arredondar); POA e PR = os do PR diário do Painel NOC (vazios no dia com POA até "
                    "0,3 na Thopen). Até 13/10/2026 a geração vinha do PR diário e a soma não fechava em 78 de 131 "
                    "usinas. Grava o worker do servidor junto com a meta do mês"),
    # O que formou a disponibilidade (12/10/2026, Levi: "Quero também que apareça todas as OSs listadas que formaram
    # aquele valor"): as OS da conta do Gerencial › Disponibilidade, publicadas com o diário pela plataforma. A perda de
    # cada linha é a da OS naquela usina desde 13/10/2026 (`kwh_usina` do índice da Disponibilidade): repartida pela
    # potência, a OS de duas usinas punha a perda na usina errada quando o teto de 100% pegava uma e não a outra (e, até
    # 15/10/2026, quando a geração desmentia o dia numa só)
    Fato("disponibilidade_os", "OS que formaram a disponibilidade (Gerencial)", "performance",
         "falhas_performance · disponibilidade_os",
         "1 linha = 1 OS da conta da disponibilidade × 1 usina do escopo dela, no mês",
         _d(data=("cod", "inicio, fim (hora de Brasília)"),
            usina=("nome", "usina (nome do Gerencial); usina_fracttal liga pelo de_para (Fracttal · Classificação 1)"),
            equipamento=("cod", "codigo_ativo"), os=("cod", "os")),
         tipo="snapshot_acumulado", chave=("mes", "os", "usina"),
         medidas=_m((("duracao_sol_min", "min", "aditiva"), ("perda_kwh", "kWh", "aditiva"))),
         fontes=("falhas_performance · disponibilidade_os",),
         janela_origem="o mês corrente e o anterior (o índice do Gerencial); mês que sai fica como foi publicado",
         observacao="tipo = o tipo da tarefa (Religamento, Religamento Remoto, Corretiva Emergencial); origem = queda ou "
                    "equipamento; escopo = usina inteira, cabine N ou inversor N.M; duracao_sol_min = as horas de sol "
                    "(06–18 h) da OS dentro do mês, as mesmas em cada usina dela; perda_kwh = a perda da OS naquela "
                    "usina pela régua do Gerencial (kWp afetado × horas de sol, sem a irradiação; só o Fracttal, a "
                    "geração não entra desde 15/10/2026): as linhas de uma usina somam a perda dela no Gerencial, e a "
                    "usina do escopo em que a OS não tem hora de sol fica com 0. Até 13/10/2026 era a perda da OS "
                    "repartida pela potência (setembro: 47.893 kWh na usina errada entre Rodrigues 1 e 2). Mês de "
                    "setembro para trás vem do BD_Thopen, sem OS: a aba fica sem linha. Sem a descrição nem quem "
                    "criou (regra 8)"),
    # A parcela de cada OS em cada dia (14/10/2026, Dashboard Thopen, Levi: "A partir de outubro quero os comentários 100%
    # OS Fracttal. Comentários e disponibilidade!"): sai da MESMA varredura da disponibilidade_dia (disponibilidade._varrer
    # da plataforma), por isso as linhas de uma usina num dia somam o h_perdidas dela. É o que o 5080 escreve no
    # comentário de cada dia. Registrado antes da 1ª gravação (nasce na 1ª volta do worker depois do deploy da plataforma)
    Fato("disponibilidade_os_dia", "Parcela de cada OS na disponibilidade do dia (Gerencial)", "performance",
         "falhas_performance · disponibilidade_os_dia",
         "1 linha = 1 OS da conta da disponibilidade × 1 usina × 1 dia em que ela tirou disponibilidade",
         _d(data=("cod", "dia; inicio, fim da OS (hora de Brasília)"),
            usina=("nome", "usina (nome do Gerencial); usina_fracttal liga pelo de_para (Fracttal · Classificação 1)"),
            os=("cod", "os")),
         tipo="snapshot_periodico", chave=("mes", "dia", "usina", "os"),
         # na fonte: h_perdidas (horas equivalentes da OS no dia). Somam entre as OS de uma usina no dia e no tempo de
         # uma usina, não entre usinas (a mesma regra da disponibilidade_dia)
         medidas=_m((("indisponibilidade_min", "min", "semi"),)),
         fontes=("falhas_performance · disponibilidade_os_dia",),
         janela_origem="o mês corrente e o anterior (o índice do Gerencial); mês que sai fica como foi publicado",
         observacao="h_perdidas = as horas equivalentes que a OS tirou da usina naquele dia (fração da potência × "
                    "horas de sol, 06–18 h), na mesma conta da disponibilidade_dia: somadas, as linhas de uma usina num "
                    "dia dão o h_perdidas dela, e a disponibilidade do dia é 100 × (1 − h ÷ 12). trechos = os horários "
                    "do dia em que a OS foi dona da perda (\"06:00-08:06; 10:55-12:05\"): a OS de cabine coberta por "
                    "uma de usina inteira só conta fora dela (até 15/10/2026 o dia que a geração desmentia também não "
                    "tinha linha; desde então a geração não entra). tipo, origem, escopo e kWp são os da OS naquela "
                    "usina. Sem a descrição nem quem criou (regra 8)"),
    # ── Tickets ────────────────────────────────────────────────────────────────────────────────────────────────
    Fato("ticket", "Ticket de performance", "chamados",
         "tickets_performance · Tickets de Performance, Trackers, Strings indisp", "1 linha = 1 ticket",
         _d(data=("cod", "Início da ocorrência"), usina=("cod", "Código da usina"), cliente=("nome", "Cliente"),
            pessoa=("nome", "Supervisor(a), Responsável"), equipamento=("nome", "Equipamento, Inversor, Tracker"),
            os=("cod", "N° OS")),
         tipo="snapshot_acumulado", chave=("ID",),
         medidas=_m((("indisponibilidade_min", "min", "aditiva"), ("impacto_kwh", "kWh", "aditiva"))),
         fontes=("tickets_performance · Tickets de Performance", "tickets_performance · Trackers",
                 "tickets_performance · Strings indisp"),
         observacao="o ID falta em 57 de 774 tickets; as abas Trackers e Strings indisp não têm ID"),
    # Chamados de garantia no banco (12/10/2026, Levi: "O nexus é um ambiente centralizado e precisamos ter os dados se
    # conversando!"): as OS de acompanhamento de chamado do Fracttal (o quadro Acompanhamento de chamados do OS Creator),
    # publicadas pelo Nexus de hora em hora (nexus/campo/chamados_acompanhamento.py). Quem só conta chamados (a Visão do
    # responsável) lê daqui; o quadro continua ao vivo (é nele que se escreve o ticket e se finaliza)
    Fato("chamado", "Chamado de garantia (OS de acompanhamento)", "chamados",
         "fora do banco: API REST do Fracttal (OS de acompanhamento de chamado, tarefa Administrativa)",
         fato_chamado.GRAO,
         _d(data=("id", "data_id_abertura, data_id_fim (dia de Brasília)"),
            usina=("id", "usina_id (de-para do Fracttal pelo site da OS; código do ativo)"),
            equipamento=("id", "equipamento_id (o código do ativo na dimensão de equipamento)"),
            os=("cod", "os (o nº da OS de acompanhamento)")),
         tipo=fato_chamado.TIPO, chave=fato_chamado.CHAVE, medidas=_m(fato_chamado.MEDIDAS),
         fontes=_fontes(fato_chamado.FONTES), janela_origem=fato_chamado.JANELA_ORIGEM,
         estado="conformado", conformado_em="nexus_chamados · fato_chamado",
         observacao="situacao = aberto (em processo), verificacao ou concluido; cancelada fica fora, como no quadro. O "
                    "REST não traz a subtarefa do ticket (testado em 12/10/2026): 'aguardando ticket' × 'com o "
                    "fabricante' só no quadro. fabricante e componente saem da marca da nota (categorias), nunca a "
                    "nota; sem pessoa (regra 8)"),
    # ── PCM ────────────────────────────────────────────────────────────────────────────────────────────────────
    Fato("programacao", "Programação semanal", "pcm", "fora do banco: banco_dados.json do PCM (GitHub público)",
         programacao.GRAO,
         _d(data=("id", "data_id_semana, data_id_programada (+ criação da OS, fim da execução)"),
            usina=("id", "usina_id (Classificação 1 do Fracttal; código)"),
            equipe=("id", "equipe_id (Equipe Cluster)"),
            pessoa=("id", "pessoa_id_tecnico, pessoa_id_responsavel (pelo nome, só de 1 pessoa)"),
            equipamento=("id", "equipamento_id"), os=("cod", "os")),
         tipo=programacao.TIPO, chave=programacao.CHAVE, medidas=_m(programacao.MEDIDAS),
         fontes=_fontes(programacao.FONTES), janela_origem=programacao.JANELA_ORIGEM,
         estado="conformado", conformado_em="nexus_programacao · fato_programacao",
         observacao="até 08/10: '1 linha = tarefa × semana'; o grão medido é o bloco de agenda. As linhas foraDoPlano "
                    "são execução, outro grão: ficam fora. Decisão 7 (08/10, o Levi quer as semanas antigas): a fonte "
                    "guarda 4 semanas, então a carga grava pela mescla por semana (troca só as semanas do arquivo) e "
                    "não grava com a leitura do banco vazia ou que falha; as semanas desde a W21 vieram do git do PCM "
                    "(carga única, ferramentas/carregar_programacao_historica.py). Usina e equipe são as ATUAIS do "
                    "ativo (o robô reescreve): a da época sai do usinas_historico"),
    # As tarefas das OS do Fracttal lidas pelo próprio Nexus (18/10/2026, Levi: "pegando tudo do Fracttal ou Nexus, sem
    # fontes externas!"): o que o gestao_pcm.json do robô do PCM dava às telas, agora no banco, de hora em hora
    # (nexus/campo/tarefas_os.py). Registrado antes de existir: o livro nasce na 1ª gravação, depois do ensaio
    Fato("tarefa_os", "Tarefa de OS do Fracttal", "pcm",
         "fora do banco: API REST do Fracttal (work_orders, uma linha por tarefa)", fato_tarefa_os.GRAO,
         _d(data=("id", "data_id_criacao, data_id_programada, data_id_fim (dia de Brasília)"),
            usina=("id", "usina_id (de-para do Fracttal pelo site da OS; código do ativo)"),
            equipamento=("id", "equipamento_id (o código do ativo na dimensão de equipamento)"),
            os=("cod", "os (o nº da OS) e fracttal_os_id (o id da OS no Fracttal, para abrir o card)")),
         tipo=fato_tarefa_os.TIPO, chave=fato_tarefa_os.CHAVE, medidas=_m(fato_tarefa_os.MEDIDAS),
         fontes=_fontes(fato_tarefa_os.FONTES), janela_origem=fato_tarefa_os.JANELA_ORIGEM,
         estado="conformado", conformado_em="nexus_os · fato_tarefa_os",
         observacao="foto de hora em hora do que está aberto (status 1 e 2) e da zeladoria feita em 90 dias; "
                    "cancelada fica fora. O nome da tarefa vira tarefa_chave (a mesma conta da programação e dos "
                    "motivos); o responsável da OS só vira do_backoffice (1/0, pelo HMAC do nome contra a lista do "
                    "PCM), nunca o nome (regra 8). Leitura do Fracttal incompleta não grava"),
)
POR_ID = {f.id: f for f in FATOS}


@dataclass(frozen=True)
class Livro:
    nome: str
    abas: tuple
    cadencia: str
    quem_grava: str
    no_banco: bool             # já existe no banco (False = registrado antes de existir: regra 10)
    observacao: str = ""


# Os livros que o NEXUS grava (regra 10: nome `nexus_<assunto>`, para sempre; registrar AQUI antes de criar).
LIVROS = (
    Livro("nexus_dimensoes", ("dim_data", "feriados_locais", "pessoas_historico", "usinas_historico",
                              "qualidade_historico", "atualizacao"),
          "de hora em hora (:40)", "nexus/dados/carga.py", True,
          "qualidade_historico e as colunas novas do histórico (versao, *_id, inicio_presumido) entram na 1ª carga "
          "do servidor com o código de 08/10"),
    Livro("nexus_fatos", ("fato_fechamento", "fato_ronda", "fato_pt", "qualidade", "atualizacao"),
          "de hora em hora (:40)", "nexus/dados/carga.py", True,
          "fato_ronda e fato_pt entram na 1ª carga do servidor com o código de 08/10"),
    # no_banco conferido por GET na listagem do banco em 11/10/2026 (aqui e nos três abaixo)
    Livro("nexus_equipamentos", ("dim_equipamento", "equipamento_apelido", "qualidade", "atualizacao"),
          "de hora em hora (:40); grava só quando o sha das linhas muda", "nexus/dados/carga.py + equipamento.py",
          True, "no banco (GET em 11/10/2026: dim_equipamento 8.395, equipamento_apelido 4.619, última gravação às "
                "20:42, antes da foto_ativos): só os códigos dos livros do banco e do PCM. Com a foto gravada (21:06), "
                "a carga seguinte lê a foto do banco e a dimensão cresce (medido em 08/10 com as fotos locais: "
                "22.356)"),
    Livro("nexus_ativos_fracttal", ("foto_ativos", "atualizacao"), "carga única (quem grava é o Levi)",
          "ferramentas/carregar_ativos_fracttal.py --gravar", True,
          "gravada em 11/10/2026 (GET: foto_ativos 22.357 linhas, última gravação às 21:06). Renovar a foto exige "
          "ler o Fracttal: fora do horário de campo"),
    Livro("nexus_programacao", ("fato_programacao", "qualidade", "atualizacao"),
          "de hora em hora (:40), pela mescla por semana; grava só quando o sha das linhas muda",
          "nexus/dados/carga.py + programacao.py (o histórico: ferramentas/carregar_programacao_historica.py)", True,
          "criado em 08/10/2026 pela carga única: W21 a W41, 14.276 blocos (W21 a W37 do git do PCM + as 4 semanas "
          "do arquivo), conferido por GET semana a semana"),
    Livro("nexus_geracao", ("fato_geracao_usina_dia", "qualidade", "atualizacao", "meses"),
          "depois de cada subida do bd_thopen ou do bd_performance (a carga de hora em hora confere o updated_at deles)",
          "nexus/dados/carga.py (gerar_geracao) + geracao.py; à mão: ferramentas/carregar_geracao.py --gravar", True,
          "produto DERIVADO dos BDs, que seguem a fonte (Levi, 11/10/2026: preenchidos por API e à mão e subidos ao PG; "
          "nada do Nexus os substitui). Decisão 8 tomada em 11/10: de-para das abas publicado, teto = potência × 24 h, "
          "IPOA do bd_performance só o DEF, inversor × dia em um livro por mês"),
    # a família do inversor × dia: um livro por mês, nome nexus_geracao_inversor_AAAA_MM (o radar casa pelo padrão,
    # `da_familia`); só o mês que mudou é regravado (a aba `meses` do nexus_geracao guarda o sha de cada um)
    Livro("nexus_geracao_inversor_AAAA_MM", ("fato_geracao_inversor_dia",), "com o nexus_geracao, só o mês que mudou",
          "nexus/dados/carga.py (gerar_geracao) + geracao.py", True,
          "~700 mil linhas no total (29 a 36 MB num livro só não cabiam na troca integral); ~32 mil por mês"),
    Livro("nexus_rondas_checklist", ("fato_checklist_ronda", "qualidade", "atualizacao"), "carga única (06/10/2026)",
          "ferramentas/carregar_checklist_rondas_sem_os.py", True,
          "a aba qualidade existe no banco desde a carga única e só entrou aqui em 09/10, quando o radar a achou"),
    Livro("nexus_rondas_avulsas", ("fato_ronda_avulsa",),
          "a cada lançamento no Nexus; importação da validação por foto (só a pedido)",
          "nexus/campo/ronda_avulsa.py + ferramentas/importar_avulsas_planilha.py --gravar", True,
          "criado em 08/10/2026 pela importação da validação por foto: 63 linhas (origem validacao_foto, usina_id "
          "63/63; a pessoa, fora do cadastro, só com o nome cifrado), conferido por GET em 09/10"),
    Livro("nexus_contestacoes_tratamento", ("fato_tratamento_contestacao",),
          "a cada \"Pegar para mim\" e a cada atualização na tela Contestações",
          "nexus/contratos/tratamento.py, pela tela Contratos e clientes > Contestações", False,
          "registrado em 15/10/2026 antes da 1ª gravação (regra 10): nasce na 1ª demanda que alguém pega"),
    Livro("nexus_observacoes", ("fato_observacao_responsavel",), "a cada observação escrita no Nexus",
          "nexus/campo/observacao_responsavel.py", False,
          "registrado em 13/10/2026 antes da 1ª gravação (regra 10): nasce na 1ª observação de um responsável"),
    Livro("nexus_pt_decisoes", ("fato_decisao_pt",), "a cada decisão no Nexus", "nexus/campo/decisao_pt.py", False,
          "o livro não existe no banco (GET em 11/10/2026): nenhuma decisão gravada. A aba era 'decisoes' até a "
          "decisão 4 (11/10/2026), nunca gravada; o App lê a fato_decisao_pt"),
    Livro("nexus_tempo_real", ("fato_decisao_cobertura",), "a cada decisão na tela Fontes do tempo real",
          "plataforma/cobertura.py (PerformancePainel), pela tela /admin/tempo-real da plataforma", True,
          "no banco desde 11/10/2026 (conferido por GET; a cada decisão cresce); a plataforma lê com cache de 60 s, "
          "no PC e no servidor"),
    Livro("nexus_depara", ("fato_decisao_depara",), "a cada decisão na tela De-para de equipamentos",
          "plataforma/depara.py (PerformancePainel), pela tela /admin/de-para da plataforma", True,
          "no banco desde 11/10/2026 (conferido por GET; a cada decisão cresce); a plataforma lê com cache de 60 s, "
          "no PC e no servidor"),
    Livro("nexus_performance", ("fato_meta_usina_mes", "fato_desempenho_usina_dia"), "de hora em hora, e só quando muda",
          "plataforma/gerencial_publicar.py (worker do servidor, `_ger_publicar` no app.py)", True,
          "no banco desde 12/10/2026 19:55 (1ª volta do worker do servidor depois do deploy da plataforma, conferida "
          "por GET). A Visão do responsável do Nexus lê; sem o livro, ela diz que a meta ainda não chegou"),
    Livro("nexus_chamados", ("fato_chamado",), "de hora em hora (:50), uma máquina por vez",
          "nexus/campo/chamados_acompanhamento.py (laço do Campo; NEXUS_CHAMADOS_PUBLICAR=0 desliga numa máquina)", True,
          "no banco desde 12/10/2026 (1ª gravação pelo Nexus do PC, conferida por GET: 18 linhas, 17 abertas e 1 em "
          "verificação, todas com usina); grava se a última gravação tiver mais de 50 min"),
    Livro("nexus_os", ("fato_tarefa_os", "qualidade"), "de hora em hora (:10), uma máquina por vez",
          "nexus/campo/tarefas_os.py (laço do Campo; NEXUS_OS_PUBLICAR=0 desliga numa máquina)", False,
          "registrado em 18/10/2026 antes de existir: nasce na 1ª gravação, feita à mão depois do ensaio "
          "(ferramentas/ensaio_tarefas_os.py --gravar); grava só a leitura inteira do Fracttal e se a última "
          "gravação tiver mais de 50 min"),
    Livro("nexus_setores", ("dim_setor", "fato_decisao_setor"), "a cada mudança na tela Integração Fracttal",
          "nexus/cadastro/setores.py, pela tela Base > Integração Fracttal", False,
          "registrado em 12/10/2026 antes de existir: nasce com o 1º setor criado na tela; a tela lê com cache de "
          "1 minuto e relê o banco antes de cada gravação"),
    Livro("nexus_estrutura_usina", ("dim_supervisorio", "dim_cabine", "dim_inversor", "aba_equipamentos"),
          "a cada ligação de chave e a cada Salvar da tela Equipamentos das usinas",
          "nexus/cadastro/estrutura_usina.py, pela tela Base > Equipamentos das usinas", False,
          "registrado em 13/10/2026 antes de existir: nasce com a 1ª chave do supervisório ligada na tela. Substitui, no "
          "Nexus, a aba Equipamentos do bd_performance (que segue como referência e não muda); a tela lê com cache de "
          "1 minuto e relê o banco antes de cada gravação. Quem mudou, só como HMAC (alterado_por_hmac). A aba "
          "aba_equipamentos é a VISÃO no formato da aba Equipamentos das chaves marcadas \"no lugar da aba\", refeita a "
          "cada gravação: a plataforma, o gêmeo, as Ligações e o coletor (quando ligado nele) trocam as linhas dessas "
          "chaves por ela"),
    Livro("nexus_setor_telas", ("fato_decisao_tela_setor",), "a cada Salvar da seção Telas por setor (Base > Acessos)",
          "nexus/auth/setor_telas.py, pela tela Base > Acessos", False,
          "registrado em 12/10/2026 antes de existir: nasce com o 1º Salvar na tela; o portão de cada pedido e a "
          "tela leem com cache de 1 minuto, e a gravação relê o banco antes"),
    Livro("nexus_relatorio_setor", ("fato_decisao_dono_relatorio",),
          "a cada Salvar da seção Setor de cada relatório (Relatórios > Central de emissão)",
          "nexus/auth/dono_relatorio.py, pela Central de emissão", False,
          "registrado em 14/10/2026 antes de existir: nasce com o 1º Salvar; livro próprio porque gravar troca o livro "
          "inteiro (no nexus_setor_telas uma gravação apagaria a outra aba); o portão e a Central leem com cache de 1 "
          "minuto, e a gravação relê o banco antes"),
    Livro("nexus_pcm_curadoria", ("fato_decisao_curadoria",),
          "a cada carga da curadoria do PCM (ferramentas/carregar_curadoria_pcm.py; a tela de edição vem depois)",
          "nexus/pcm/acompanhamento/curadoria.py", False,
          "registrado em 14/10/2026 antes de existir: nasce com a 1ª carga do arquivo do painel do PCM; o Acompanhamento "
          "lê com cache de 2 minutos, e a gravação relê o banco antes (troca o livro inteiro)"),
    Livro("nexus_pcm_motivos", ("dim_motivo", "fato_decisao_motivo", "fato_decisao_backoffice"),
          "a cada marca de motivo (Quadro da semana e Fora da programação), a cada mudança no cadastro dos motivos e na "
          "lista do backoffice (Gerar a semana)",
          "nexus/pcm/motivos.py, pelas telas do PCM", False,
          "registrado em 16/10/2026 antes de existir: nasce com a 1ª gravação (o cadastro inicial, os 12 motivos do "
          "pedido do Levi, entra junto). As telas leem com cache de 1 minuto e a gravação relê o banco antes (troca o "
          "livro inteiro, as três abas juntas)"),
    # o login por pessoa do Dashboard Thopen (14/10/2026): o Nexus é a fonte das contas; a senha, o 5080 grava no livro
    # dele (thopen_acessos · senhas, em CONHECIDAS)
    Livro("nexus_acessos_clientes", ("dim_conta_cliente",), "a cada ação na tela Acessos dos clientes",
          "nexus/contratos/acessos_clientes.py, pela tela Contratos e clientes > Acessos dos clientes", False,
          "registrado em 14/10/2026 antes de existir: nasce com a 1ª conta criada na tela. 1 linha = 1 conta (o estado "
          "atual; o livro é trocado inteiro sob a trava, relido antes e conferido depois). Nome e e-mail só cifrados, "
          "duas vezes: dados_5080 (selado para a pública do Dashboard Thopen, que lê a cada 2 min) e dados_nexus "
          "(Cofre, a chave do cadastro); o link de definir senha só como sha256; quem mudou só como HMAC"),
    # os técnicos por usina (17/10/2026): o PCM põe e tira técnicos de cada usina; o App de Campo lê o executa daqui
    Livro("nexus_pcm_atribuicoes", ("fato_decisao_atribuicao",), "a cada decisão na tela Técnicos por usina",
          "nexus/pcm/atribuicoes.py, pela tela Técnicos por usina do PCM", False,
          "registrado em 17/10/2026 antes de existir: nasce com a 1ª decisão ou com a carga inicial (a regra da equipe "
          "do cadastro). A tela lê com cache de 1 minuto e a gravação relê o banco antes (troca o livro inteiro)"),
)
LIVRO_POR_NOME = {l.nome: l for l in LIVROS}
# Famílias de livro (um por período): o nome real casa pelo padrão, e as abas são as do Livro de molde no LIVROS.
FAMILIAS = {re.compile(r"^nexus_geracao_inversor_\d{4}_\d{2}$"): "nexus_geracao_inversor_AAAA_MM"}


def da_familia(livro: str, aba: str) -> bool:
    """A aba é de um livro de família registrado (ex.: nexus_geracao_inversor_2026_10 · fato_geracao_inversor_dia)."""
    for padrao, molde in FAMILIAS.items():
        if padrao.match(livro or ""):
            return aba in LIVRO_POR_NOME[molde].abas
    return False
# As abas que não são fato_/dim_/<dimensão>_historico/qualidade/atualizacao, e por quê (regra 10).
ABAS_FORA_DA_REGRA = {
    "feriados_locais": "a lista de feriados estaduais e municipais (a dim_data só tem os nacionais)",
    "qualidade_historico": "a qualidade do histórico (SCD2): sobreposição, buraco e membro sem vigente",
    "equipamento_apelido": "o que cada sistema chama de cada equipamento (o modelo do de_para das usinas)",
    "foto_ativos": "a foto dos ativos do Fracttal: insumo da dimensão de equipamento, carga única",
    "meses": "a lista dos livros do mês do inversor × dia, com o sha de cada um (a geração regrava só o mês que mudou)",
    "aba_equipamentos": "a visão da estrutura das usinas no formato da aba Equipamentos do bd_performance (as mesmas "
                        "colunas, com os IDs no fim), só das chaves marcadas \"no lugar da aba\": é o que deixa cada "
                        "leitor antigo da aba trocar a fonte sem ser reescrito (nexus/cadastro/estrutura_usina.py)",
}


# As tabelas do banco que NÃO são fato nem livro do Nexus, cada uma com o papel e o porquê (Levi, 09/10/2026: "verifique
# se aparece a cada tabela nova que aparece"). O radar da Governança de dados (`radar.py`) compara a listagem do banco
# com o catálogo: aba que não é fonte ou destino de fato (FATOS), nem aba de livro do Nexus (LIVROS), nem aba de usina
# dos livros "1 aba por usina", nem está aqui, aparece como NOVA, sozinha. Para tirá-la de nova: vira fato, entra no LIVROS
# ou é declarada aqui dizendo o que é. A declaração é aba por aba (a aba nova num livro conhecido também aparece); "*"
# só no livro de teste. Nos livros "1 aba por usina", a aba declarada aqui não é aba de usina (a prévia não a lista).
PAPEIS_CONHECIDA = {"dimensao": "dimensão ou de-para", "controle": "controle da carga",
                    "apoio": "apoio do sistema de origem", "candidata": "candidata a fato",
                    "aposentada": "aposentada", "teste": "teste"}


@dataclass(frozen=True)
class Conhecida:
    livro: str
    abas: tuple                # os nomes exatos das abas; ("*",) = o livro inteiro (só teste)
    papel: str                 # PAPEIS_CONHECIDA
    motivo: str


CONHECIDAS = (
    Conhecida("cadastro_nexus", ("clientes", "equipes", "pessoas", "usinas", "de_para", "regioes_campo"), "dimensao",
              "o cadastro do Nexus: de onde saem as dimensões usina, cliente, equipe (com a região de campo) e pessoa, "
              "e o de-para dos sistemas"),
    Conhecida("cadastro_nexus", ("atualizacao",), "controle", "quando e de onde o cadastro foi publicado"),
    Conhecida("de_para_trackers", ("De-Para Trackers", "Resumo por usina", "Pendências"), "dimensao",
              "o de-para dos trackers do supervisório; a dimensão de equipamento lê dele o apelido 'Supervisório · "
              "tracker'"),
    Conhecida("falhas_performance", ("atualizacao",), "controle",
              "o controle da publicação da plataforma: as linhas de cada aba no mês"),
    Conhecida("campo_nexus", ("rondas", "atualizacao"), "aposentada",
              "do coletor do Fracttal do Nexus, desligado em 05/10/2026 (o fato dele se aposentou); fica no banco "
              "porque a API não apaga livro"),
    Conhecida("gemeo_digital", ("usina", "equipamento", "alias", "modelo"), "apoio",
              "o cadastro próprio do gêmeo digital: as 25 usinas, os equipamentos, os apelidos e os modelos dele"),
    Conhecida("gemeo_digital", ("cascata_dia", "evento"), "candidata",
              "o detalhe do cálculo de perda do gêmeo (a cascata por dia e os eventos); o fato catalogado é a "
              "perda_dia"),
    Conhecida("plataforma_series", ("trk_cobertura", "issues_history", "issues_active", "perdas_strings",
                                    "paradas_book", "perdas_dias", "paradas_fontes"), "candidata",
              "séries que a plataforma de performance grava e lê de volta (cobertura dos trackers, alertas, perdas de "
              "string, paradas do book); o fato catalogado é a trk_eventos"),
    Conhecida("plataforma_series", ("_meta",), "controle", "o controle da gravação das séries da plataforma"),
    Conhecida("plataforma_estado", ("strings_trancadas", "verified", "manutencao", "tracking", "etm_tickets",
                                    "os_atribuidas", "comentarios", "comments", "trackers_notas", "trackers_garantia",
                                    "trackers_notas_local"), "apoio",
              "o estado das telas da plataforma de performance (marcações, comentários e notas dos analistas)"),
    Conhecida("plataforma_estado", ("_meta",), "controle", "o controle da gravação do estado da plataforma"),
    Conhecida("tickets_performance", ("Home", "Aux", "Check", "Comentários", "Resumo - Trackers",
                                      "Base de dados - Dashboard", "Base de dados - Usinas",
                                      "Base de dados - Usinas (desatu)", "Tracker", "Edicoes do app",
                                      "Edicoes do app v2", "Edicoes do app v3"), "apoio",
              "abas de apoio da planilha de tickets: painéis, listas, cadastro de usinas e o histórico das edições"),
    Conhecida("tickets_performance", ("Desligamentos", "Inv. com baixa perfor.", "Inv. com lim. de potência"),
              "candidata", "listas de acompanhamento da planilha de tickets (desligamentos, inversores com baixa "
                           "performance ou com limitação de potência), ainda sem fato no catálogo"),
    Conhecida("bd_thopen", ("Dados Gerais Usinas", "Clientes", "zz Caroá - Cliente"), "apoio",
              "o cadastro das usinas e dos clientes na planilha do coletor; o cadastro que vale é o do Nexus"),
    Conhecida("bd_thopen", ("Dados Mensais 2026", "Histórico Carteira", "Histórico Polaris"), "candidata",
              "históricos mensais (2026, por carteira, Polaris) que o fato Meta e histórico mensal ainda não lê"),
    Conhecida("bd_performance", ("Info Geral", "Base UFV", "Equipamentos", "BD_Trackers", "Aux"), "apoio",
              "o cadastro da planilha do coletor: as usinas (a Info Geral dá o Código Fractal das abas), os "
              "equipamentos e os trackers"),
    Conhecida("bd_performance", ("Info Mensal",), "candidata",
              "os dados mensais das usinas do BD_Performance, ainda sem fato no catálogo"),
    Conhecida("bd_performance", ("Ibirapuã I - Backup", "Falhas", "Trackers", "PVSyst", "Acumulado Anual"), "apoio",
              "abas ocultas da planilha (cópia de segurança, falhas antigas, PVSyst, acumulado)"),
    Conhecida("os_creator", ("temas", "plataforma", "chamados_obs"), "apoio",
              "a configuração do OS Creator (temas, plataforma, observações dos chamados)"),
    Conhecida("thopen_acessos", ("senhas",), "apoio",
              "as senhas do login por pessoa do Dashboard Thopen (14/10/2026): o 5080 grava 1 linha a cada senha "
              "definida pelo link (o hash scrypt, cifrado com a chave dele); o Nexus lê só quando cada conta definiu"),
    Conhecida("organizacao_app_campo", ("Atribuicoes",), "apoio",
              "a foto das atribuições do App de Campo (usina × pessoa em HMAC × papel), publicada pelo App para o PCM "
              "comparar na tela Técnicos por usina antes de o App passar a ler o nexus_pcm_atribuicoes (17/10/2026); "
              "sai quando a troca estiver feita"),
    Conhecida("zz_teste_claude_apagar", ("*",), "teste",
              "livro de teste da API, criado para provar a gravação; nunca é dado (a API não apaga livro)"),
)


def conhecida(livro: str, aba: str):
    """A declaração da aba em CONHECIDAS, ou None."""
    for c in CONHECIDAS:
        if c.livro == livro and (aba in c.abas or c.abas == ("*",)):
            return c
    return None


def aba_segue_a_regra(aba: str) -> bool:
    return (aba.startswith(("fato_", "dim_")) or aba.endswith("_historico") or aba in ("qualidade", "atualizacao")
            or aba in ABAS_FORA_DA_REGRA)


def conformado(f: Fato) -> bool:
    return f.estado == "conformado"


def ativos() -> list:
    """Os fatos que contam: sem os aposentados e sem os que viraram fonte de outro (`parte`)."""
    return [f for f in FATOS if f.estado not in ("aposentado", "parte")]


def resumo() -> dict:
    """Os números do topo da tela: quantos fatos, quantos já ligados por ID, quantos montados, quantos fora."""
    at = ativos()
    return {"fatos": len(at), "dimensoes": len(DIMENSOES), "conformados": sum(conformado(f) for f in at),
            "montados": sum(f.estado == "montado" for f in at), "fora": sum(f.estado == "fora" for f in at),
            "livros": len(LIVROS)}
