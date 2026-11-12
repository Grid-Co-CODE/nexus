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
# as abas que nunca encolhem (12/11/2026, com o SSO gravando pelo Nexus): o RLS do Supabase não deixava apagar linha nelas
# (a presença, a visualização, a APR e a vistoria, que só ganha a marca de excluída), e o inventário dos arquivos só
# cresce. A trava do `livros.publicar` recusa a gravação que as encolheria. A lista de usinas do diário fica de fora: o
# fornecedor escreve nela sem lista fechada (já escreveu o nome de uma pessoa), e o administrador tira o que não é usina
SO_CRESCE = HISTORICO + ("iv_visualizacoes", "iv_presencas", "apr_submissoes", "vistoria_checklists", ABA_ARQUIVOS)

# ── colunas cifradas ────────────────────────────────────────────────────────────────────────────────────────────────
# Cifrado por padrão, como na Zeladoria (regra 8 de nexus/dados/CLAUDE.md): todo texto, JSON e lista. O SSO guarda CPF,
# telefone, e-mail, nome de quem assina e a própria assinatura em base64 dentro das linhas. Fica em claro só o que liga o
# dado ao tempo: ids, datas, estados, serviço e fase. Número, booleano, data, hora e uuid nunca são cifrados (o tipo vem
# do Postgres, anotado na exportação).
# A USINA VAI CIFRADA (12/11/2026, na volta do SSO a funcionar): no SSO ela é texto que o fornecedor DIGITA, e um
# fornecedor digitou o nome de uma pessoa como usina (5 vistorias e a lista de usinas do diário), que a 1ª cópia deixou
# em claro na API de leitura aberta. Ligar a usina do SSO ao cadastro, quando vier, é pelo de-para, não pelo texto em
# claro. A leitura aceita o texto em claro da cópia antiga (só decifra o que está cifrado); a página do administrador
# (`/t/sso/admin`, "Regravar cifrado") regrava os livros com a regra de agora.
# A revisão do mesmo dia achou a mesma porta em outros textos que o fornecedor escreve sem lista fechada (o número da OS,
# o serviço da vistoria e do diário, o número do certificado): também cifrados. Em claro, só o que é lista fechada e
# conferida (os estados, a origem, a fase da vistoria, que a API só aceita "antes" ou "depois", o serviço do EPI, com o
# CHECK do esquema) e o que o sistema escreve (o bucket e o tipo do inventário, a ação do cronograma, da Gestão).
_CLARO = {"id", "status", "status_aprovacao", "fase", "origem", "acao", "bucket", "tipo"}
_CLARO_SUFIXOS = ("_id", "_em", "_at")
_CLARO_PREFIXOS = ("data_", "status_")
# a usina do diário e o fornecedor do cronograma são a chave da linha e são texto digitado (o MEI é pessoa): cifrados,
# com o contexto da chave (`sso/<aba>/-/<coluna>`, o `guardar`)
_CLARO_POR_ABA = {("epi_submissoes", "servico")}
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
