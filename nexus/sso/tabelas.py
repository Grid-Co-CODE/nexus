"""O mapa das tabelas do SSO: de onde cada uma veio no Supabase, a aba e o livro do Nexus, e o que vai cifrado.

A aba tem o nome da view que o app do SSO usa (`public.iv_presencas` etc.), para a futura ponte do app falar com o Nexus
sem tradução; a vistoria, que no Supabase era a tabela solta `public.checklists`, vira `vistoria_checklists` (o nome
"checklists" sozinho não diz de quê). Um livro por módulo: o banco recebe um arquivo por livro, e as assinaturas dentro
das linhas pesam (o APR passa de 4 MB).
"""
LIVRO_INTEGRACAO = "nexus_sso_integracao"
LIVRO_APR = "nexus_sso_apr"
LIVRO_EPI = "nexus_sso_epi"
LIVRO_VISTORIA = "nexus_sso_vistoria"
LIVRO_DIARIO = "nexus_sso_diario"
LIVRO_CRONOGRAMA = "nexus_sso_cronograma"
LIVRO_ARQUIVOS = "nexus_sso_arquivos"

# tabela do Supabase (esquema.tabela) -> (aba no Nexus, livro)
ORIGEM = {
    "integracao_video.sessoes_video": ("iv_sessoes_video", LIVRO_INTEGRACAO),
    "integracao_video.visualizacoes": ("iv_visualizacoes", LIVRO_INTEGRACAO),
    "integracao_video.presencas": ("iv_presencas", LIVRO_INTEGRACAO),
    "integracao_video.perfis": ("iv_perfis", LIVRO_INTEGRACAO),
    "apr.submissoes": ("apr_submissoes", LIVRO_APR),
    "epi.checklists": ("epi_submissoes", LIVRO_EPI),
    "public.checklists": ("vistoria_checklists", LIVRO_VISTORIA),
    "diario.registros": ("diario_registros", LIVRO_DIARIO),
    "diario.usinas": ("diario_usinas", LIVRO_DIARIO),
    "cronograma.periodos": ("cronograma_periodos", LIVRO_CRONOGRAMA),
    "cronograma.periodos_historico": ("cronograma_historico", LIVRO_CRONOGRAMA),
    "cronograma.fornecedores": ("cronograma_fornecedores", LIVRO_CRONOGRAMA),
}
# o inventário dos arquivos do Storage (fotos, PDFs, vídeo): o arquivo em si ficou travado no Supabase em 11/11/2026; a
# lista diz o que existia, para resgatar depois sem perder a referência de nenhum
ABA_ARQUIVOS = "arquivos"
COLUNAS_ARQUIVOS = [("chave", "text"), ("bucket", "text"), ("caminho", "text"), ("bytes", "bigint"), ("tipo", "text"),
                    ("criado_em", "timestamp with time zone")]

TABELAS = {aba: livro for aba, livro in ORIGEM.values()} | {ABA_ARQUIVOS: LIVRO_ARQUIVOS}
LIVROS = (LIVRO_INTEGRACAO, LIVRO_APR, LIVRO_EPI, LIVRO_VISTORIA, LIVRO_DIARIO, LIVRO_CRONOGRAMA, LIVRO_ARQUIVOS)
NOMES_LIVROS = {LIVRO_INTEGRACAO: "SSO · integração de segurança", LIVRO_APR: "SSO · APR", LIVRO_EPI: "SSO · EPI",
                LIVRO_VISTORIA: "SSO · vistoria", LIVRO_DIARIO: "SSO · diário de obra",
                LIVRO_CRONOGRAMA: "SSO · cronograma", LIVRO_ARQUIVOS: "SSO · inventário dos arquivos"}
# só cresce: o registro das alterações do cronograma
HISTORICO = ("cronograma_historico",)

# ── colunas cifradas ────────────────────────────────────────────────────────────────────────────────────────────────
# Cifrado por padrão, como na Zeladoria (regra 8 de nexus/dados/CLAUDE.md): todo texto, JSON e lista. O SSO guarda CPF,
# telefone, e-mail, nome de quem assina e a própria assinatura em base64 dentro das linhas. Fica em claro só o que liga o
# dado ao resto do Nexus e ao tempo: ids, datas, estados, usina, serviço e fase. Número, booleano, data, hora e uuid nunca
# são cifrados (o tipo vem do Postgres, anotado na exportação).
_CLARO = {"id", "usina", "numero_os", "numero_certificado", "status", "status_aprovacao", "servico", "servicos", "fase",
          "origem", "acao", "bucket", "tipo"}
_CLARO_SUFIXOS = ("_id", "_em", "_at")
_CLARO_PREFIXOS = ("data_", "status_")
# a usina do diário tem o nome como chave: é lugar, fica em claro; o fornecedor do cronograma também é chave, mas é nome
# (de empresa ou de pessoa, no MEI): vai cifrado
_CLARO_POR_ABA = {("diario_usinas", "nome")}
_NAO_TEXTO = ("integer", "bigint", "smallint", "numeric", "real", "double precision", "boolean", "date", "time",
              "timestamp", "interval", "uuid")


def coluna_cifrada(aba: str, coluna: str, tipo: str | None = None) -> bool:
    c = str(coluna or "").strip().lower()
    t = str(tipo or "").strip().lower()
    if t.startswith(_NAO_TEXTO):
        return False
    if (aba, c) in _CLARO_POR_ABA or c == "data":
        return False
    return not (c in _CLARO or c.endswith(_CLARO_SUFIXOS) or c.startswith(_CLARO_PREFIXOS))
