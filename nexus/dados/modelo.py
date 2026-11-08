"""O modelo do catálogo de dados: o que é um fato, uma medida, uma dimensão e um livro, e as regras que valem para todos.

Saiu do `catalogo.py` em 05/11/2026 para cada área poder declarar os próprios fatos e livros na pasta dela sem importar
o catálogo inteiro (o catálogo importa as áreas: a Segurança em `nexus/hseq/catalogo.py`). O catálogo reexporta tudo
daqui; quem usa `catalogo.Fato`, `catalogo.Livro` ou `catalogo.DIMENSOES` não muda nada.
"""
from dataclasses import dataclass

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
# `_ms` entrou em 31/10/2026 com o tempo de resposta das telas do OS Creator (fato_uso_os: mediana e p95 em milissegundos)
# `_km` entrou em 08/11/2026 com a distância entre usinas do Mapa de equipe (fato_deslocamento_equipe)
SUFIXOS_UNIDADE = ("_min", "_kwh", "_kwh_m2", "_mm", "_pct", "_qtd", "_pts", "_nivel", "_brl", "_ms", "_km")


@dataclass(frozen=True)
class Medida:
    coluna: str     # com a unidade no nome (SUFIXOS_UNIDADE); indicador sem sufixo, só 1/0
    unidade: str    # "min", "kWh", "kWh/m²", "mm", "%", "qtd", "pts", "nível 1-5", "R$", "ms", "km", "1/0"
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


@dataclass(frozen=True)
class Livro:
    nome: str
    abas: tuple
    cadencia: str
    quem_grava: str
    no_banco: bool             # já existe no banco (False = registrado antes de existir: regra 10)
    observacao: str = ""
    # as abas que só crescem (18/10/2026): o livros.publicar recusa gravar se a listagem vier incompleta, se uma aba do
    # banco ficar de fora ou se uma destas encolher. Vazio = livro sem trava (a carga, que encolhe pela janela da fonte);
    # True = todas as abas do livro
    so_cresce: tuple = ()

    def __post_init__(self):
        if self.so_cresce is True:
            object.__setattr__(self, "so_cresce", tuple(self.abas))
