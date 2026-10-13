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

from . import fato_chamado, fato_pt, fato_ronda, fatos, geracao, programacao

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
    ("usina", "Usina", "cadastro_nexus · usinas (+ de_para; nexus_dimensoes · usinas_historico)", "usina_id"),
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
         _d(data=("cod", "Última conferência (dia de Brasília)"),
            usina=("nome", "Usina (nome do Fracttal; de reserva, o código do Ativo e o Código da usina)"),
            pessoa=("hmac", "Conferido por"),
            equipamento=("cod", "Ativo: o código do Fracttal de onde o extintor fica (ele mesmo é cadastro próprio)")),
         tipo="snapshot_acumulado", chave=("Código",),
         medidas=_m((("itens_nao_qtd", "qtd", "aditiva"), ("fotos_qtd", "qtd", "aditiva"))),
         fontes=("extintores_app_campo · Extintores",), janela_origem="o cadastro inteiro, com a última conferência",
         observacao="a linha muda a cada conferência e nunca fecha. Atrasado, perto de vencer e sem atualização são "
                    "conta do Nexus no dia (nexus/hseq/extintores.py, a mesma regra da TST que o App usa); o Status do "
                    "livro é o do App na hora da publicação. A observação do técnico não vai (só 'Tem informação "
                    "adicional', sim/não). Carga única em 09/10/2026 pelo Nexus, do cadastro do App (773, "
                    "ferramentas/carregar_extintores_cadastro.py), até o App publicar (v257, que a substitui)"),
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
    # GR-2 (auditoria 08/10): um registro só para dois grãos; virou fonte dos dois fatos abaixo, sem apagar a história
    Fato("falha_string", "Falha de string", "performance",
         "falhas_performance · strings_episodios, strings_inversor_dia", "1 linha = 1 episódio · inversor × dia",
         _d(data=("cod", "saiu / dia"), usina=("nome", "usina (+ fonte)"), cliente=("nome", "cliente"),
            equipamento=("nome", "inversor, string")),
         tipo="snapshot_acumulado", estado="parte", parte_de=("falha_string_episodio", "falha_string_inversor_dia"),
         observacao="até 08/10 um registro só para dois grãos (GR-2): episódio e inversor × dia são dois fatos"),
    Fato("falha_string_episodio", "Falha de string (episódio)", "performance", "falhas_performance · strings_episodios",
         "1 linha = 1 episódio de string fora (saiu → voltou)",
         _d(data=("cod", "saiu"), usina=("nome", "usina (+ fonte)"), cliente=("nome", "cliente"),
            equipamento=("nome", "inversor, string")),
         tipo="snapshot_acumulado", chave=("fonte", "usina", "inversor", "string", "saiu"),
         medidas=_m((("perda_kwh", "kWh", "aditiva"),)), fontes=("falhas_performance · strings_episodios",),
         observacao="o episódio aberto muda até voltar (foto acumulada)"),
    Fato("falha_string_inversor_dia", "Falha de string (inversor × dia)", "performance",
         "falhas_performance · strings_inversor_dia", "1 linha = 1 inversor × 1 dia com string fora",
         _d(data=("cod", "dia"), usina=("nome", "usina (+ fonte)"), cliente=("nome", "cliente"),
            equipamento=("nome", "inversor")),
         tipo="snapshot_periodico", chave=("fonte", "usina", "inversor", "dia"),
         medidas=_m((("perda_kwh", "kWh", "aditiva"),)), fontes=("falhas_performance · strings_inversor_dia",)),
    Fato("falha_tracker", "Falha de tracker", "performance", "falhas_performance · trackers_episodios",
         "1 linha = 1 episódio",
         _d(data=("cod", "parou"), usina=("nome", "usina"), cliente=("nome", "cliente"),
            equipamento=("nome", "tracker, inversor")),
         tipo="snapshot_acumulado", chave=("fonte", "usina", "tracker", "parou"),
         medidas=_m((("perda_kwh", "kWh", "aditiva"), ("duracao_min", "min", "aditiva"))),
         fontes=("falhas_performance · trackers_episodios",)),
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
    Livro("nexus_performance", ("fato_meta_usina_mes",), "de hora em hora, e só quando o mês muda",
          "plataforma/gerencial_publicar.py (worker do servidor, `_ger_publicar` no app.py)", True,
          "no banco desde 12/10/2026 19:55 (1ª volta do worker do servidor depois do deploy da plataforma, conferida "
          "por GET). A Visão do responsável do Nexus lê; sem o livro, ela diz que a meta ainda não chegou"),
    Livro("nexus_chamados", ("fato_chamado",), "de hora em hora (:50), uma máquina por vez",
          "nexus/campo/chamados_acompanhamento.py (laço do Campo; NEXUS_CHAMADOS_PUBLICAR=0 desliga numa máquina)", True,
          "no banco desde 12/10/2026 (1ª gravação pelo Nexus do PC, conferida por GET: 18 linhas, 17 abertas e 1 em "
          "verificação, todas com usina); grava se a última gravação tiver mais de 50 min"),
    Livro("nexus_setores", ("dim_setor", "fato_decisao_setor"), "a cada mudança na tela Integração Fracttal",
          "nexus/cadastro/setores.py, pela tela Base > Integração Fracttal", False,
          "registrado em 12/10/2026 antes de existir: nasce com o 1º setor criado na tela; a tela lê com cache de "
          "1 minuto e relê o banco antes de cada gravação"),
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
