"""O mapa das tabelas do Radar para os livros do Nexus, e quais colunas vão cifradas.

O Radar guardava 39 tabelas no esquema `radar_fornecedores` do Supabase, cada uma vista pelo app como `public.rf_<x>`,
mais a view `rf_fracttal_ultimas` (a última ronda de cada usina). Elas vêm com o MESMO nome (Levi, 03/11/2026: "com a
mesma lógica e caminhos do BD"), em três livros: o estado do app, o que vem do Fracttal e os históricos, que só crescem.

A exceção são as seis tabelas da equipe primarizada, que levavam o primeiro nome do supervisor (`gastos_<nome>`,
`orcamento_<nome>_semanal`...). O repositório é público e nome de colega não entra nele: elas viram `*_equipe` e casam
por padrão, sem o nome escrito aqui.

Coluna cifrada: a API do banco tem leitura aberta (regra 8 de `nexus/dados/CLAUDE.md`). Desde a revisão final de
03/11/2026 vai cifrado POR PADRÃO todo texto, JSON e lista, porque a lista do que é pessoal sempre esquece uma coluna
(justificativa, causa do dano, o apelido do fornecedor MEI). Fica em claro só o que está em `_CLARO`: ids, datas,
estados e o que dá nome a usina e cliente. Número, booleano, data e hora também ficam: valor de contrato e de
pagamento, sem o nome, não é dado pessoal, e é a razão de o dado estar no Nexus.
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


def mapa_de_tabelas(nomes_supabase) -> dict:
    """{tabela do Supabase: aba do Nexus} para a lista inteira do esquema, conferida em conjunto.

    O padrão da equipe primarizada sozinho aceitaria uma tabela nova parecida (`gastos_fornecedor` cairia calada em
    cima de `gastos_equipe`, revisão final de 03/11/2026). Por isso as seis têm de levar o MESMO primeiro nome, e cada
    aba tem uma tabela de origem só; senão, TabelaDesconhecida e nada é copiado."""
    mapa, origem, nomes_equipe = {}, {}, set()
    for nome in nomes_supabase:
        aba = nome_no_nexus(nome)
        m = _EQUIPE.match(str(nome).strip().lower())
        if m and str(nome).strip().lower() not in TABELAS:
            nomes_equipe.add(m.group(2))
        if aba in origem:
            raise TabelaDesconhecida(f"duas tabelas do Radar caem na mesma aba {aba!r}: {origem[aba]!r} e {nome!r}")
        origem[aba] = nome
        mapa[nome] = aba
    if len(nomes_equipe) > 1:
        raise TabelaDesconhecida(f"as tabelas da equipe primarizada não levam o mesmo nome ({len(nomes_equipe)} "
                                 "nomes diferentes): uma delas é tabela nova; registre antes de copiar")
    return mapa


def aba_da_view(view: str) -> str:
    """'rf_<tabela>' (o nome que o app do Radar usa) -> a aba do Nexus."""
    v = str(view or "").strip().lower()
    if not v.startswith("rf_"):
        raise TabelaDesconhecida(f"{view!r} não é uma view do Radar (rf_<tabela>)")
    return nome_no_nexus(v[3:])


# ── colunas cifradas ────────────────────────────────────────────────────────────────────────────────────────────
# Cifrado por padrão (revisão final de 03/11/2026: a lista do que é pessoal deixava em claro justificativa, causa do
# dano, apelido do fornecedor, o JSON extra da usina...). Todo texto, JSON e lista vai cifrado, menos o que está abaixo:
# os ids, as datas, os estados e o que dá nome a usina e cliente, que é o que liga a zeladoria ao resto do Nexus. Número,
# booleano, data e hora nunca são cifrados (o tipo vem do Postgres, anotado pela cópia).
_TABELA_INTEIRA = {"colaboradores"}       # pessoa física: só os ids ficam em claro
_CLARO = {
    # ids e chaves de negócio
    "id", "chave", "usina_chave", "folio", "codigo", "numero_os", "numero_nota_fiscal", "classe_contabil",
    # datas guardadas como texto
    "data", "mes", "semana", "ano", "periodo", "inicio", "fim", "validade", "vencimento",
    "de_inicio", "de_fim", "para_inicio", "para_fim",
    # estado, tipo e classificação
    "status", "status_manual", "tipo", "servico", "servicos", "papel", "origem", "escopo", "prioridade", "nivel",
    "criticidade", "categoria", "unidade", "via", "forma_pagamento", "investimento", "alinhamento_semanal",
    # onde: usina, cliente e lugar (o que liga ao cadastro do Nexus)
    "usina", "usinas", "ufv", "cliente", "estado", "uf", "regiao", "cluster", "base_equipe", "equipe_cluster",
    "cidade", "concessionaria", "fabricante_modulos",
    # o maps_link fica cifrado: é a localização da usina (o endereço saiu da API em 04/10/2026 pela mesma razão)
}
_CLARO_PREFIXOS = ("status_", "tipo_", "data_", "forma_pagamento")
_CLARO_SUFIXOS = ("_id", "_ids", "_em", "_data")
_NAO_TEXTO = ("integer", "bigint", "smallint", "numeric", "real", "double precision", "boolean", "date", "time",
              "timestamp", "interval", "uuid")


def _eh_id(coluna: str) -> bool:
    return coluna == "id" or coluna.endswith(("_id", "_ids"))


def coluna_cifrada(aba: str, coluna: str, tipo: str | None = None) -> bool:
    """`tipo` é o do Postgres; sem ele (None), a coluna conta como texto."""
    c = str(coluna or "").strip().lower()
    t = str(tipo or "").strip().lower()
    if t.startswith(_NAO_TEXTO):
        return False
    if aba in _TABELA_INTEIRA:
        return not _eh_id(c)
    return not (c in _CLARO or c.startswith(_CLARO_PREFIXOS) or c.endswith(_CLARO_SUFIXOS))
