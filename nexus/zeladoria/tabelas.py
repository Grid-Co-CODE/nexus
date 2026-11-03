"""O mapa das tabelas do Radar para os livros do Nexus, e quais colunas vão cifradas.

O Radar guardava 39 tabelas no esquema `radar_fornecedores` do Supabase, cada uma vista pelo app como `public.rf_<x>`,
mais a view `rf_fracttal_ultimas` (a última ronda de cada usina). Elas vêm com o MESMO nome (Levi, 03/11/2026: "com a
mesma lógica e caminhos do BD"), em três livros: o estado do app, o que vem do Fracttal e os históricos, que só crescem.

A exceção são as seis tabelas da equipe primarizada, que levavam o primeiro nome do supervisor (`gastos_<nome>`,
`orcamento_<nome>_semanal`...). O repositório é público e nome de colega não entra nele: elas viram `*_equipe` e casam
por padrão, sem o nome escrito aqui.

Coluna cifrada: a API do banco tem leitura aberta (regra 8 de `nexus/dados/CLAUDE.md`). Vai cifrado o que identifica
pessoa (contato, telefone, PIX, e-mail, quem fez), o texto livre (pode ter nome) e o nome do fornecedor, porque há
fornecedor MEI com nome de pessoa e não há como separar com segurança. Valor de contrato e de pagamento fica em claro:
sem o nome, não é dado pessoal, e é a razão de o dado estar no Nexus.
"""
import re

LIVRO_APP = "nexus_zeladoria_app"
LIVRO_FRACTTAL = "nexus_zeladoria_fracttal"
LIVRO_HISTORICO = "nexus_zeladoria_historico"

_APP = (
    # cadastros
    "usinas", "fornecedores", "colaboradores", "tipos_documento", "documentos", "regras_cliente_zeladoria",
    # cotação e aprovação
    "fila_prioridade", "periodos", "cotacoes", "historico_valor", "simulacoes_aprovacao",
    # contratos e OS
    "contratos_anuais", "contrato_os", "ordens_servico", "servicos_zeladoria", "danos_modulos",
    # financeiro
    "financeiro_parcelas", "fin_cenario", "fin_cenario_item", "fin_provisao", "fin_provisao_vinculo",
    "fin_fornecedor_alias",
    # criticidade e cronograma
    "criticidade_rondas", "cronograma_publico",
    # equipe primarizada
    "tipos_gasto_equipe", "gastos_equipe", "orcamento_equipe", "orcamento_equipe_semanal", "simulacao_repasse_equipe",
    "rota_equipe",
    # acesso
    "perfis", "config",
)
_FRACTTAL = ("fracttal_rondas", "fracttal_fotos", "fracttal_sync", "fracttal_ultimas")
# o que só cresce: o registro de ações, as alterações das parcelas e das provisões e as remarcações do cronograma
HISTORICO = ("log", "financeiro_historico", "fin_provisao_historico", "cronograma_alteracoes")

TABELAS = {**{a: LIVRO_APP for a in _APP}, **{a: LIVRO_FRACTTAL for a in _FRACTTAL},
           **{a: LIVRO_HISTORICO for a in HISTORICO}}

# a equipe primarizada: <tabela>_<primeiro nome>[_semanal] -> <tabela>_equipe[_semanal]
_EQUIPE = re.compile(r"^(tipos_gasto|gastos|orcamento|simulacao_repasse|rota)_([a-z]+)(_semanal)?$")


class TabelaDesconhecida(ValueError):
    """Tabela do Radar que o mapa não conhece: a cópia para em vez de pular (dado que some calado é o pior caso)."""


def nome_no_nexus(nome_supabase: str) -> str:
    nome = str(nome_supabase or "").strip().lower()
    if nome in TABELAS:
        return nome
    m = _EQUIPE.match(nome)
    if m and m.group(2) not in ("equipe", "semanal"):
        novo = f"{m.group(1)}_equipe{m.group(3) or ''}"
        if novo in TABELAS:
            return novo
    raise TabelaDesconhecida(f"a tabela {nome_supabase!r} do Radar não está no mapa da zeladoria (nexus/zeladoria/"
                             "tabelas.py): registre antes de copiar")


def aba_da_view(view: str) -> str:
    """'rf_<tabela>' (o nome que o app do Radar usa) -> a aba do Nexus."""
    v = str(view or "").strip().lower()
    if not v.startswith("rf_"):
        raise TabelaDesconhecida(f"{view!r} não é uma view do Radar (rf_<tabela>)")
    return nome_no_nexus(v[3:])


# ── colunas cifradas ────────────────────────────────────────────────────────────────────────────────────────────
# a tabela inteira é de pessoa física (o cadastro da equipe primarizada): só os ids ficam em claro
_TABELA_INTEIRA = {"colaboradores"}
_PESSOAIS = {"empresa", "contato", "telefone", "pix", "email", "email_contrato", "responsavel_om", "tecnico_om",
             "eletricista_om", "mantenedor_om", "tecnico", "avaliacao_colaboradores", "equipe", "pendencias", "quem",
             "fornecedor", "fornecedor_nome", "alias"}
_TEXTO_LIVRE = {"obs", "observacao", "motivo", "resumo", "descricao", "comentario", "nota"}
# JSON inteiros que guardam tabelas antigas do app (o config) e o retrato do cronograma: podem ter nome em qualquer campo
_PARES = {("config", "valor"), ("cronograma_publico", "dados")}


def _eh_id(coluna: str) -> bool:
    return coluna == "id" or coluna.endswith("_id")


def coluna_cifrada(aba: str, coluna: str) -> bool:
    c = str(coluna or "").strip().lower()
    if aba in _TABELA_INTEIRA:
        return not _eh_id(c)
    return (c in _PESSOAIS or c in _TEXTO_LIVRE or c.startswith("contato_") or c.endswith("_por")
            or (aba, c) in _PARES)
