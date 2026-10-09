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
from dataclasses import dataclass

from . import fato_pt, fato_ronda, fatos, geracao, programacao

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
    ("pessoa", "Pessoa", "cadastro_nexus · pessoas (+ nexus_dimensoes · pessoas_historico)", "pessoa_id"),
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
                    "'Sujo'/'Limpo'/vazio (não verificado) e a anulação só com anula_id. Livro ainda inexistente em "
                    "08/10 (GET)"),
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
    # quem aplica no campo é o App (nexus/campo/decisao_pt.py)
    Fato("decisao_pt", "Decisão de PT no Nexus", "hseq", "nexus_pt_decisoes · decisoes",
         "1 linha = 1 decisão (De acordo ou Não autorizo) de uma PT, tomada no Nexus",
         _d(data=("id", "data_id"), usina=("id", "usina_id"), pessoa=("hmac", "decidida_por_hmac"),
            os=("cod", "os")),
         tipo="sem_medida", chave=("decidida_em", "pt"), fontes=("nexus_pt_decisoes · decisoes",),
         janela_origem="o Nexus é a fonte",
         observacao="PT pelo número (a chave do pt_app_campo); o motivo vai mascarado, porque o técnico lê. Pega a 1ª "
                    "linha da PT (GR-4): numa PT de 3 ativos não diz a qual vale. Antes da 1ª gravação: levar o "
                    "codigo_ativo e a aba fato_decisao_pt (decisão 4 do Levi)"),
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
    Fato("geracao_usina_dia", "Geração diária por usina", "performance",
         "bd_thopen · bd_performance (1 aba por usina)", geracao.GRAO_USINA,
         _d(data=("id", "data_id"),
            usina=("id", "usina_id pelo de-para 'BD_Thopen · aba' / 'BD_Performance · aba' (vazio = usina_motivo)")),
         tipo=geracao.TIPO, chave=geracao.CHAVE_USINA, medidas=_m(geracao.MEDIDAS_USINA),
         fontes=("bd_thopen · 1 aba por usina", "bd_performance · 1 aba por usina"),
         estado="montado", conformado_em="nexus_geracao · fato_geracao_usina_dia",
         observacao="montado e medido no --ensaio; grava (diária, ~01:40) depois das decisões do Levi (8): publicar o "
                    "de-para das abas, o teto de kWh/dia, o IPOA do BD_Performance. Até lá usina_id 0% de propósito. "
                    "Os 3 agregados do inversor × dia não se somam com ele"),
    Fato("geracao_inversor_dia", "Geração diária por inversor", "performance",
         "bd_thopen · bd_performance (1 aba por usina)", geracao.GRAO_INVERSOR,
         _d(data=("id", "data_id"), usina=("id", "usina_id (o da aba)"),
            equipamento=("id", "equipamento_id pelo apelido 'BD_* · coluna'")),
         tipo=geracao.TIPO, chave=geracao.CHAVE_INVERSOR, medidas=_m(geracao.MEDIDAS_INVERSOR),
         fontes=("bd_thopen · 1 aba por usina", "bd_performance · 1 aba por usina"), estado="montado",
         observacao="~700 mil linhas (29 a 36 MB de xlsx): não cabe em troca integral. O destino é decisão do Levi: "
                    "o passo 0 (acréscimo por dia) ou livros mensais nexus_geracao_inversor_AAAA_MM"),
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
    Livro("nexus_equipamentos", ("dim_equipamento", "equipamento_apelido", "qualidade", "atualizacao"),
          "de hora em hora (:40); grava só quando o sha das linhas muda", "nexus/dados/carga.py + equipamento.py",
          False, "sem a foto_ativos gravada, só os códigos dos livros do banco e do PCM (~8 mil)"),
    Livro("nexus_ativos_fracttal", ("foto_ativos", "atualizacao"), "carga única (quem grava é o Levi)",
          "ferramentas/carregar_ativos_fracttal.py --gravar", False,
          "renovar a foto exige ler o Fracttal: fora do horário de campo"),
    Livro("nexus_programacao", ("fato_programacao", "qualidade", "atualizacao"),
          "de hora em hora (:40), pela mescla por semana; grava só quando o sha das linhas muda",
          "nexus/dados/carga.py + programacao.py (o histórico: ferramentas/carregar_programacao_historica.py)", True,
          "criado em 08/10/2026 pela carga única: W21 a W41, 14.276 blocos (W21 a W37 do git do PCM + as 4 semanas "
          "do arquivo), conferido por GET semana a semana"),
    Livro("nexus_geracao", ("fato_geracao_usina_dia", "qualidade", "atualizacao"),
          "diária (~01:40) quando ligar; só --ensaio até a decisão 8", "ferramentas/carregar_geracao.py + geracao.py",
          False),
    Livro("nexus_rondas_checklist", ("fato_checklist_ronda", "atualizacao"), "carga única (06/10/2026)",
          "ferramentas/carregar_checklist_rondas_sem_os.py", True),
    Livro("nexus_rondas_avulsas", ("fato_ronda_avulsa",),
          "a cada lançamento no Nexus; importação da validação por foto (só a pedido)",
          "nexus/campo/ronda_avulsa.py + ferramentas/importar_avulsas_planilha.py --gravar", False,
          "não existe no banco em 08/10 (GET): a importação de 08/10 parou no ensaio (a pessoa pedida não tem ficha "
          "no cadastro)"),
    Livro("nexus_pt_decisoes", ("decisoes",), "a cada decisão no Nexus", "nexus/campo/decisao_pt.py", False,
          "0 linhas em 08/10"),
)
LIVRO_POR_NOME = {l.nome: l for l in LIVROS}
# As abas que não são fato_/dim_/<dimensão>_historico/qualidade/atualizacao, e por quê (regra 10).
ABAS_FORA_DA_REGRA = {
    "feriados_locais": "a lista de feriados estaduais e municipais (a dim_data só tem os nacionais)",
    "qualidade_historico": "a qualidade do histórico (SCD2): sobreposição, buraco e membro sem vigente",
    "equipamento_apelido": "o que cada sistema chama de cada equipamento (o modelo do de_para das usinas)",
    "foto_ativos": "a foto dos ativos do Fracttal: insumo da dimensão de equipamento, carga única",
    "decisoes": "nasceu antes da regra (05/10); vira fato_decisao_pt antes da 1ª gravação (GS-6, decisão 4)",
}


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
