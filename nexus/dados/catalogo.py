"""O catálogo dos dados do Nexus: a matriz de barramento (método Kimball) como DADO, e não como desenho.

Levi, 05/10/2026: "prioridade 0 para a governança e controle de dados"; "precisamos construir e manter uma base sólida
para futuras análises correlacionadas". Cada processo que gera dado (um FATO: um fechamento, uma ronda, a geração de um
dia) se liga aos cadastros de referência (as DIMENSÕES: usina, pessoa, data...) por ID. Este arquivo é a fonte única:
a tela Base → Governança de dados, os testes e o CLAUDE.md da área leem daqui. Fonte nova entra AQUI primeiro (ver
`nexus/dados/CLAUDE.md`, "Como entra um dado novo").

Estados de cada ligação fato × dimensão:
  id      liga pelo ID do cadastro do Nexus (o certo)
  cod     código de um sistema (código da usina, plant_id, código do ativo, data, número da OS): liga pelo de-para
  hmac    a pessoa como código do e-mail (HMAC, NEXUS_PESSOA_HMAC): liga com a chave
  nome    texto livre: junção frágil
  largo   um equipamento por coluna (formato largo): precisa virar linhas
  prop    cadastro próprio, que só aquele livro usa
  nao     não tem
"""
from dataclasses import dataclass, field

ESTADOS = {"id": "ID", "cod": "código", "hmac": "código da pessoa", "nome": "nome", "largo": "em colunas",
           "prop": "cadastro próprio", "nao": "—"}

# As dimensões conformadas: UMA de cada, com o mesmo ID para todos os setores.
DIMENSOES = (
    ("data", "Data", "nexus_dimensoes · dim_data", "data_id (AAAAMMDD)"),
    ("usina", "Usina", "cadastro_nexus · usinas (+ de_para)", "usina_id"),
    ("cliente", "Cliente", "cadastro_nexus · clientes", "cliente_id"),
    ("equipe", "Equipe / região", "cadastro_nexus · equipes", "equipe_id"),
    ("pessoa", "Pessoa", "cadastro_nexus · pessoas (+ nexus_dimensoes · pessoas_historico)", "pessoa_id"),
    ("equipamento", "Equipamento", "ainda não existe (nasce do gemeo_digital · equipamento)", "equipamento_id"),
    ("os", "OS", "o número no próprio fato (dimensão degenerada)", "os"),
)
DIM_IDS = tuple(d[0] for d in DIMENSOES)


@dataclass(frozen=True)
class Fato:
    id: str
    nome: str
    area: str                  # o setor dono (a torre do Nexus)
    livro: str                 # onde mora no banco (workbook · aba), ou "fora do banco"
    grao: str                  # o que é UMA linha: sem isto escrito, dois relatórios contam coisas diferentes
    dims: dict                 # {dimensão: (estado, coluna/observação)}
    estado: str = "origem"     # origem (como chega) | conformado (o Nexus grava com os IDs) | aposentado | fora
    conformado_em: str = ""    # o livro do Nexus que já tem o fato com os IDs
    observacao: str = ""


def _d(**kw):
    out = {d: ("nao", "") for d in DIM_IDS}
    out.update({k: (v if isinstance(v, tuple) else (v, "")) for k, v in kw.items()})
    return out


FATOS = (
    # ── Campo · App: o App grava de hora em hora (aos :25) ───────────────────────────────────────────────────────
    Fato("fechamento", "Fechamento de OS", "campo", "fechamentos_app_campo · Fechamentos",
         "1 linha = 1 tarefa fechada pelo App (o registro da nota do painel)",
         _d(data=("cod", "Registrado em"), usina=("nome", "Usina (cliente · nome do Fracttal)"),
            equipe=("nome", "Região"), pessoa=("hmac", "Técnico (HMAC)"), equipamento=("cod", "Código do ativo"),
            os=("cod", "OS")),
         estado="conformado", conformado_em="nexus_fatos · fato_fechamento"),
    Fato("ronda", "Ronda", "campo", "rondas_app_campo · OS de ronda", "1 linha = 1 OS de ronda",
         _d(data=("cod", "Data"), usina=("cod", "Ativo da usina no Fracttal"), equipe=("nome", "Região"),
            pessoa=("nome", "Técnico (nome em claro)"), os=("cod", "OS"))),
    Fato("pt", "Permissão de trabalho", "hseq", "pt_app_campo · PT", "1 linha = 1 PT",
         _d(data=("cod", "Criada em"), usina=("nome", "Usina"), equipe=("nome", "Região"),
            pessoa=("hmac", "Solicitante, quem decidiu"), equipamento=("cod", "Código do ativo"), os=("cod", "OS"))),
    Fato("decisao", "Decisão do painel", "campo", "decisoes_app_campo · Decisões",
         "1 linha = 1 decisão, tratamento ou devolução",
         _d(data=("cod", "Quando"), usina=("nome", "Usina (só Central de atenção)"), pessoa=("hmac", "3 papéis"),
            equipamento=("cod", "Código do ativo (devolução)"), os=("cod", "OS"))),
    Fato("zeladoria", "Zeladoria", "campo", "zeladoria_app_campo · Zeladoria", "1 linha = 1 etapa registrada",
         _d(data=("cod", "Data"), usina=("nome", "Usina"), pessoa=("hmac", "Registrado por"), os=("cod", "OS")),
         observacao="vazio até 05/10: a tela é da v226 e ninguém registrou ainda"),
    Fato("fechamento_coletor", "Fechamento pelo coletor", "campo", "campo_nexus · fechamentos",
         "1 linha = 1 tarefa da fila do Fracttal",
         _d(data=("cod", "fim"), usina=("id", "usina_id"), equipe=("nome", "regiao"), pessoa=("id", "pessoa_id"),
            equipamento=("cod", "codigo"), os=("cod", "os")),
         estado="aposentado",
         observacao="aposentado em 05/10: a nota batia com a do painel do App em só 14% das tarefas"),
    # ── Performance ────────────────────────────────────────────────────────────────────────────────────────────
    Fato("geracao_thopen", "Geração diária (Thopen)", "performance", "bd_thopen · 1 aba por usina",
         "1 linha = usina × dia",
         _d(data=("cod", "Data"), usina=("nome", "Usina (aba)"), equipamento=("largo", "SKID 1…, Inversor 1.1…"))),
    Fato("geracao_demais", "Geração diária (demais)", "performance", "bd_performance · 1 aba por usina",
         "1 linha = usina × dia",
         _d(data=("cod", "Data"), usina=("cod", "aba = código (MAB100)"), equipamento=("largo", "Inversor 1.1…"))),
    Fato("meta_mensal", "Meta e histórico mensal", "performance", "bd_thopen · Dados Mensais, Historico",
         "1 linha = usina × mês", _d(data=("cod", "Mês"), usina=("nome", "Usina"))),
    Fato("falha_string", "Falha de string", "performance",
         "falhas_performance · strings_episodios, strings_inversor_dia", "1 linha = 1 episódio · inversor × dia",
         _d(data=("cod", "saiu / dia"), usina=("nome", "usina (+ fonte)"), cliente=("nome", "cliente"),
            equipamento=("nome", "inversor, string"))),
    Fato("falha_tracker", "Falha de tracker", "performance", "falhas_performance · trackers_episodios",
         "1 linha = 1 episódio",
         _d(data=("cod", "parou"), usina=("nome", "usina"), cliente=("nome", "cliente"),
            equipamento=("nome", "tracker, inversor"))),
    Fato("parada_tracker", "Parada de tracker", "performance", "plataforma_series · trk_eventos",
         "1 linha = 1 parada", _d(data=("cod", "dia"), usina=("cod", "plant_id da fonte"),
                                  equipamento=("nome", "tracker"))),
    # ── Gêmeo digital ──────────────────────────────────────────────────────────────────────────────────────────
    Fato("perda_equipamento", "Perda por equipamento", "performance",
         "gemeo_digital · perda_dia, cascata_dia, evento", "1 linha = usina × dia × equipamento × parcela",
         _d(data=("cod", "dia"), usina=("prop", "usina (25, do gêmeo)"),
            equipamento=("prop", "equipamento (9.918 + apelidos)"))),
    # ── Tickets ────────────────────────────────────────────────────────────────────────────────────────────────
    Fato("ticket", "Ticket de performance", "chamados",
         "tickets_performance · Tickets de Performance, Trackers, Strings indisp", "1 linha = 1 ticket",
         _d(data=("cod", "Início da ocorrência"), usina=("cod", "Código da usina"), cliente=("nome", "Cliente"),
            pessoa=("nome", "Supervisor(a), Responsável"), equipamento=("nome", "Equipamento, Inversor, Tracker"),
            os=("cod", "N° OS"))),
    # ── PCM ────────────────────────────────────────────────────────────────────────────────────────────────────
    Fato("programacao", "Programação semanal", "pcm", "fora do banco: Nexus local + GitHub do PCM",
         "1 linha = tarefa × semana",
         _d(data=("cod", "semana ISO"), usina=("nome", "Classificação 1 do Fracttal"),
            cliente=("nome", "no nome da usina"), equipe=("nome", "Equipe Cluster"),
            pessoa=("nome", "técnico do Fracttal"), equipamento=("cod", "código do equipamento"), os=("cod", "OS")),
         estado="fora"),
)
POR_ID = {f.id: f for f in FATOS}


def conformado(f: Fato) -> bool:
    return f.estado == "conformado"


def resumo() -> dict:
    """Os números do topo da tela: quantos fatos, quantos já ligados por ID, quantos fora do banco."""
    ativos = [f for f in FATOS if f.estado != "aposentado"]
    return {"fatos": len(ativos), "dimensoes": len(DIMENSOES), "conformados": sum(conformado(f) for f in ativos),
            "fora": sum(f.estado == "fora" for f in ativos)}
