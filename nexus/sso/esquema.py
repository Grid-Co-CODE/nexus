"""O que o Postgres e o RLS do Supabase garantiam ao SSO, agora no Nexus: as views, os padrões, as obrigatórias, as listas
fechadas, quem pode o quê e os arquivos aceitos.

Copiado do `database/schema_sso_atual.sql` do pacote de migração (fora do repositório, `Downloads\\Deploy\\
sso_pacote_2026-11-12`) e da matriz de RLS da seção 7.2 do README de lá. O app do SSO conta com isto: a presença nasce
"pendente" porque o banco punha o padrão, o fornecedor não lê nada porque o RLS barrava, a linha sem o campo obrigatório
voltava erro. Sem este arquivo, a API do Nexus abriria o que o Supabase fechava.
"""
from __future__ import annotations

from . import tabelas as T

# a view que o app pede -> a aba do livro do Nexus (a aba tem o nome da view; a vistoria era a tabela solta
# `public.checklists`, que o app pede como "checklists")
VIEWS = {aba: aba for aba in T.TABELAS if aba != T.ABA_ARQUIVOS} | {"checklists": "vistoria_checklists"}
VIEWS.pop("vistoria_checklists")


from ..zeladoria.gravacao import Recusa  # noqa: E402 — a MESMA recusa do gravador: o pedido fere o esquema ou a
# permissão, e a mensagem volta ao app como o `error.message` do Supabase


def aba_da_view(view: str) -> str:
    aba = VIEWS.get(str(view or ""))
    if not aba:
        raise Recusa(f"a tabela {view} não existe no SSO")
    return aba


AGORA = "__agora__"          # o now() do Postgres
UUID = "__uuid__"            # o gen_random_uuid()

_CONTEUDO = [
    {"tema": "Conhecimento da UFV e Regras de Segurança",
     "descricao": "Apresentação da usina, áreas restritas, circulação, sinalização, condutas e regras de acesso."},
    {"tema": "Riscos da Atividade e Uso de EPIs",
     "descricao": "Riscos elétricos, quedas, cortes, animais peçonhentos, condições climáticas, exposição ao sol e uso "
                  "correto dos EPIs."},
    {"tema": "Produtos, Ferramentas e Equipamentos",
     "descricao": "Manuseio seguro de produtos químicos, FDS/FISPQ, ferramentas, equipamentos e cuidados durante as "
                  "atividades de limpeza e conservação."},
    {"tema": "Emergências, Acidentes e Comunicação",
     "descricao": "Procedimentos de emergência, incêndio, primeiros atendimentos, abandono de área e comunicação de "
                  "acidentes, incidentes e condições inseguras."},
    {"tema": "Meio Ambiente e Boas Práticas Operacionais",
     "descricao": "Gestão de resíduos, prevenção de impactos ambientais, preservação das instalações, convivência com "
                  "equipes de O&M e cumprimento dos procedimentos da UFV."},
]

# os DEFAULT do esquema, por aba
PADROES = {
    "vistoria_checklists": {"id": UUID, "created_at": AGORA},
    "iv_sessoes_video": {"id": UUID, "perguntas_quiz": [], "ativo": True, "criado_em": AGORA, "atualizado_em": AGORA,
                         "nome_curso_certificado": "Integração de Saúde e Segurança Ocupacional - Zeladoria",
                         "carga_horaria_texto": "2 horas", "cidade_realizacao": "Fortaleza/CE",
                         "conteudo_programatico": _CONTEUDO},
    "iv_visualizacoes": {"id": UUID, "progresso_max_segundos": 0, "concluido": False, "iniciado_em": AGORA,
                         "atualizado_em": AGORA},
    "iv_presencas": {"id": UUID, "concluido_em": AGORA, "criado_em": AGORA, "atualizado_em": AGORA,
                     "status_aprovacao": "pendente", "origem": "app"},
    "iv_perfis": {"status": "pendente", "criado_em": AGORA},
    "apr_submissoes": {"atividades": [], "instalacoes_desenergizadas": [], "epis": [], "riscos": {},
                       "assinaturas_urls": [], "desvios_urls": [], "criado_em": AGORA, "assinaturas": []},
    "epi_submissoes": {"id": UUID, "itens": [], "pendencias": 0, "criado_em": AGORA},
    "diario_registros": {"fotos": [], "videos": [], "criado_em": AGORA},
    "cronograma_periodos": {"servicos": [], "status": "planejado", "status_manual": False, "ordem": 0,
                            "criado_em": AGORA, "atualizado_em": AGORA, "vinculos_manuais": {}},
    "cronograma_historico": {"id": UUID, "alterado_em": AGORA},
}

# NOT NULL sem padrão: a linha nova sem elas é recusada, como no Postgres
OBRIGATORIAS = {
    "vistoria_checklists": ("fase", "dados"),
    "iv_sessoes_video": ("titulo",),
    "iv_visualizacoes": ("sessao_id",),
    "iv_presencas": ("sessao_id", "nome_completo", "cpf"),
    "iv_perfis": ("user_id", "email"),
    "apr_submissoes": ("id", "usina", "numero_os", "data_liberacao", "empresa_contratada", "responsavel",
                       "descricao_tarefa"),
    "epi_submissoes": ("servico", "empresa", "colaborador", "data"),
    "diario_registros": ("id", "usina", "data", "servico", "empresa", "responsavel"),
    "diario_usinas": ("nome",),
    "cronograma_periodos": ("id", "usina", "fornecedor", "data_inicio", "data_fim"),
    "cronograma_historico": ("acao",),
    "cronograma_fornecedores": ("nome",),
}

# os CHECK do esquema (lista fechada)
LISTAS = {
    ("cronograma_periodos", "status"): {"planejado", "em_andamento", "concluido", "cancelado"},
    ("epi_submissoes", "servico"): {"poda_quimica", "rocagem", "limpeza_modulos"},
    ("iv_perfis", "status"): {"pendente", "aprovado", "rejeitado"},
    ("iv_presencas", "origem"): {"app", "planilha"},
    ("iv_presencas", "status_aprovacao"): {"pendente", "aprovado", "rejeitado"},
}

# ── quem pode o quê (a matriz de RLS da seção 7.2) ──────────────────────────────────────────────────────────────────
TUDO = frozenset({"select", "insert", "update", "delete"})
# o fornecedor, sem login: só envia. Lê só o que o formulário precisa (a sessão ativa, a própria visualização pelo id e
# a lista de usinas do diário), como o RLS deixava
DO_FORNECEDOR = {
    "iv_sessoes_video": {"select"},
    "iv_visualizacoes": {"select", "insert"},
    "iv_presencas": {"insert"},
    "apr_submissoes": {"insert"},
    "epi_submissoes": {"insert"},
    "vistoria_checklists": {"insert"},
    "diario_registros": {"insert"},
    "diario_usinas": {"select", "insert"},
}
# a Gestão aprovada (o `is_gestao_aprovada()` do Supabase)
DA_GESTAO = {
    "iv_sessoes_video": TUDO,
    "iv_visualizacoes": {"select", "insert"},
    "iv_presencas": {"select", "insert", "update"},
    "iv_perfis": TUDO,
    "apr_submissoes": {"select", "insert", "update"},
    "epi_submissoes": TUDO,
    "vistoria_checklists": {"select", "insert", "update"},
    "diario_registros": TUDO,
    "diario_usinas": {"select", "insert"},
    "cronograma_periodos": TUDO,
    "cronograma_historico": {"select", "insert"},
    "cronograma_fornecedores": TUDO,
}
# o que o servidor decide na linha que o fornecedor manda (o resto vem do padrão): a presença nasce pendente, sem
# aprovação nem certificado, e ninguém de fora escreve a data de criação nem a marca de edição da vistoria
DO_SERVIDOR = {
    "iv_presencas": ("status_aprovacao", "aprovado_em", "aprovado_por", "motivo_rejeicao", "certificado_url",
                     "pdf_gerado_em", "origem", "criado_em", "atualizado_em", "concluido_em"),
    "iv_visualizacoes": ("progresso_max_segundos", "concluido", "iniciado_em", "atualizado_em"),
    "vistoria_checklists": ("created_at", "editado_em", "editado_por", "excluido_em", "excluido_por"),
    "apr_submissoes": ("criado_em",),
    "epi_submissoes": ("criado_em",),
    "diario_registros": ("criado_em",),
}


def pode(papel: str, aba: str, op: str) -> bool:
    """`papel`: "fornecedor" (sem login) ou "gestao" (aprovada). O pendente só mexe no próprio perfil (`api.py`)."""
    tabela = DO_FORNECEDOR if papel == "fornecedor" else DA_GESTAO if papel == "gestao" else {}
    return op in tabela.get(aba, ())


# ── os arquivos (os buckets do Storage) ─────────────────────────────────────────────────────────────────────────────
IMAGEM = frozenset({"image/jpeg", "image/png", "image/webp", "image/heic"})
VIDEO = frozenset({"video/mp4", "video/quicktime", "video/3gpp", "video/webm"})
PDF = frozenset({"application/pdf"})
MB = 1024 * 1024
# `fornecedor`: o fornecedor envia sem login (nunca por cima de um arquivo que já existe). Os tetos: a foto comprimida no
# celular passa pouco de 1 MB, e a que não comprime (HEIC) chegou a 8 MB; o vídeo do diário chegou a 45,8 MB, abaixo
# dos 50 MB do Supabase grátis; o vídeo da integração tem 28 MB
BUCKETS = {
    "apr-arquivos": {"fornecedor": True, "tipos": IMAGEM | PDF, "max": 15 * MB},
    "epi-fotos": {"fornecedor": True, "tipos": IMAGEM, "max": 15 * MB},
    "checklist-fotos": {"fornecedor": True, "tipos": IMAGEM | VIDEO, "max": 50 * MB},
    "diario-midia": {"fornecedor": True, "tipos": IMAGEM | VIDEO, "max": 50 * MB},
    "certificados-integracao-video": {"fornecedor": False, "tipos": PDF, "max": 15 * MB},
    "integracao-video-midia": {"fornecedor": False, "tipos": VIDEO, "max": 200 * MB},
}
MAIOR = max(b["max"] for b in BUCKETS.values())
MAIOR_FORNECEDOR = max(b["max"] for b in BUCKETS.values() if b["fornecedor"])


def tipo_do_arquivo(cabeca: bytes) -> str | None:
    """O tipo pelos primeiros bytes (nunca pelo nome nem pelo que o navegador diz): HTML ou script disfarçado de foto
    não entra, e o Nexus serve cada arquivo com o tipo que ele é."""
    c = cabeca[:32]
    if c.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if c.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if c[:4] == b"RIFF" and c[8:12] == b"WEBP":
        return "image/webp"
    if c.startswith(b"%PDF"):
        return "application/pdf"
    if c.startswith(b"\x1a\x45\xdf\xa3"):
        return "video/webm"
    if c[4:8] == b"ftyp":
        marca = c[8:12]
        if marca in (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"):
            return "image/heic"
        if marca.startswith(b"3g"):
            return "video/3gpp"
        if marca == b"qt  ":
            return "video/quicktime"
        return "video/mp4"
    return None
