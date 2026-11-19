"""O canal de abertura dos fabricantes que traz e-mail, lido do banco do Nexus para o OS Creator (19/11/2026).

Levi, 19/11/2026: "OS Creator: os e-mails dos fabricantes vão para uma tabela de cadastro no banco" e "quem tiver um acesso
do Nexus vai ter a informação completa". O texto de cada canal mora cifrado no livro `nexus_textos_reservados`, área
`oscreator_canal` (a chave é o fabricante; `nexus/dados/textos_reservados.py`). O OS Creator chega aqui pela ponte
(`ligar`), como as subtarefas padrão: o `chamado_modelos_store.CANAIS_RESERVADOS`.
"""
from ...dados import textos_reservados as TR

AREA = "oscreator_canal"


def ligar(app):
    """() -> {fornecedor: canal}, no contexto do Nexus (a tela roda no app do clone). A leitura tem cópia de 5 minutos e
    fica com a última boa quando o banco falha (`textos_reservados.ler`)."""
    def canais() -> dict:
        with app.app_context():
            return dict(TR.ler(AREA)["textos"])
    return canais
