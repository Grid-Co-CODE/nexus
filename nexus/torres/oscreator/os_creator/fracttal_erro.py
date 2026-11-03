"""fracttal_erro.py: os dois erros que todo módulo do OS Creator conhece (31/10/2026, etapa 5.3 do canto central).

Moraram no `api.py` até a etapa 5.3 repartir o arquivo: cada módulo novo precisa deles para dizer `except FracttalError`, e um
módulo que importa o `api` ao carregar o importaria em círculo (o `api` importa os módulos novos no fim). Os dois ficam aqui, sem
importar nada do OS Creator; o `api.py` os reexporta (`api.FracttalError`, `api.SessionExpired`: o MESMO objeto, e é por ele que
as rotas, a ponte e os testes os conhecem)."""


class FracttalError(Exception):
    """Erro de API com mensagem amigável (já tratada) para exibir na UI."""


class SessionExpired(FracttalError):
    """Sessão do Fracttal morta (token rotacionado/expirado). O app detecta e força novo login."""
    session_expired = True       # marcador lido pelo ApiWorker (sem precisar importar a classe)
