"""Mapa de equipe (08/11/2026): onde cada técnico de campo está durante o dia, no mapa do Nexus, e o rastro dos
deslocamentos entre usinas.

O celular (Nexus Field, casca Android) manda os pontos de posição; o Nexus guarda a coordenada SÓ cifrada (Cofre, contexto
`equipe/ponto/<ponto_id>`), desenha o mapa dentro da janela de trabalho e fecha os deslocamentos (saída de uma usina,
chegada na outra). Este pacote é a casa única das réguas e dos nomes dos livros: as rotas, o armazenamento e a tela
importam daqui, para um número ou um nome nunca divergir entre eles.

Spec:  C:/GridcoAuto/app-campo-android/docs/superpowers/specs/2026-11-08-mapa-de-equipe-design.md
Plano: docs/superpowers/plans/2026-11-08-mapa-de-equipe.md

O dado está no catálogo (nexus/dados/catalogo.py) ANTES de existir, como manda a regra 10 da casa.
"""
from datetime import date

# Os pontos: um livro POR DIA, para a T.I. apagar o arquivo do dia inteiro depois de 7 dias (LGPD: a trilha de
# localização não fica além do necessário). Os deslocamentos (sem coordenada) ficam 1 ano, um livro por mês.
LIVRO_PONTOS_MOLDE = "nexus_equipe_pontos_AAAA_MM_DD"
ABA_PONTOS = "fato_ponto_equipe"
CAB_PONTOS = ("ponto_id", "data_id", "instante", "pessoa_id", "cifra")

LIVRO_DESLOC_MOLDE = "nexus_equipe_deslocamentos_AAAA_MM"
ABA_DESLOC = "fato_deslocamento_equipe"
CAB_DESLOC = ("deslocamento_id", "data_id", "pessoa_id", "usina_id_saida", "usina_id_chegada", "saida", "chegada",
              "duracao_min", "distancia_km")

# Aparelho do técnico que recebeu ou perdeu a chave do mapa (`evento` = emitida | revogada)
LIVRO_APARELHOS, ABA_APARELHOS = "nexus_equipe_aparelhos", "fato_evento_aparelho"
CAB_APARELHOS = ("evento_id", "instante", "data_id", "pessoa_id", "aparelho", "evento", "chave_hash", "app")

# Quem entrou no piloto (ou saiu) e quem decidiu; o decisor só por HMAC
LIVRO_PILOTO, ABA_PILOTO = "nexus_equipe_piloto", "fato_decisao_piloto"
CAB_PILOTO = ("decisao_id", "instante", "data_id", "pessoa_id", "no_piloto", "decidida_por_hmac")

# Auditoria (LGPD): quem abriu o mapa ou a rota de quem (`acao` = abriu_mapa | abriu_rota)
LIVRO_ACESSOS, ABA_ACESSOS = "nexus_equipe_acessos", "fato_acesso_mapa"
CAB_ACESSOS = ("acesso_id", "instante", "data_id", "pessoa_id", "pessoa_hmac", "acao", "alvo_pessoa_id", "usina_id")

# As réguas do desenho, num lugar só
JANELA_H = (6, 22)            # só se rastreia no expediente: [6h, 22h) na hora do técnico (o `fuso` do lote)
GUARDA_PONTOS_DIAS = 7        # o livro do dia some pela T.I. depois disso; o diário em disco se poda sozinho
GUARDA_DESLOC_DIAS = 365
MAX_PONTOS = 200              # teto de pontos por envio do celular
SEM_SINAL_MIN = 30            # sem ponto há mais que isto = "sem sinal" no mapa
RAIO_USINA_KM = 1.0           # até onde o técnico conta como "dentro" da usina (confirmado pelo Levi em 08/11/2026)
ORIGEM_APP = "https://gridco-campo-mw.azurewebsites.net"


def livro_pontos(dia: date) -> str:
    """O livro dos pontos do dia (AAAA_MM_DD)."""
    return f"nexus_equipe_pontos_{dia:%Y_%m_%d}"


def livro_deslocamentos(dia: date) -> str:
    """O livro dos deslocamentos do mês do dia (AAAA_MM)."""
    return f"nexus_equipe_deslocamentos_{dia:%Y_%m}"
