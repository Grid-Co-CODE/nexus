"""A foto dos ativos do Fracttal no banco, lida para o catálogo central do OS Creator (31/10/2026, etapa 2 do canto central).

`nexus_ativos_fracttal · foto_ativos` (renovada toda noite, `nexus/dados/foto_ativos.py`) é a 3ª fonte do boot do
catálogo (`os_creator/ativos_central.py`), depois da cópia em disco dele e do `assets_cache.json` antigo: um pedido ao banco da
Gridco, nenhum ao Fracttal. O catálogo central não conhece a configuração do banco (ele mora no clone do OS Creator, que não
conhece o app do Nexus): a ponte entrega a função daqui ao criar o clone (`ponte._criar_clone`,
`ativos_central.ligar_fonte_do_banco`), e o leitor dos ativos do servidor, ao ligar (`ativos_leitor.ligar`).

Lê as 22 mil linhas em ~3 s (23 páginas de 1.000, medido em 31/10/2026). Quem converte as linhas em registros do catálogo, e
recusa a foto que não serve, é o `ativos_foto.registros_da_foto` (a foto de 22/09 não traz a raiz de cada cliente: ver o topo
dele; a renovada toda noite pelo leitor do servidor, desde 31/10/2026, traz). Teste sem a sessão do banco
(`app.extensions["nexus_dados_sessao"]`) nunca vai à rede."""
import requests

from ...cadastro.ligacoes import BASE_API
from ...dados import equipamento, livros


def leitor(app):
    """A função sem argumentos que o `ativos_central` chama: as linhas da foto (dicionários com as colunas de
    `equipamento.CAB_FOTO`). Levanta se o banco não responde; quem chama (`ativos_central.garantir`) guarda o motivo e o catálogo
    vem do Fracttal."""
    def ler() -> list:
        sessao = app.extensions.get("nexus_dados_sessao")
        if sessao is None:
            if app.config.get("TESTING"):
                raise RuntimeError("teste sem banco")
            sessao = requests.Session()
        base = (app.config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")
        return livros.ler(base, sessao, equipamento.LIVRO_FOTO, equipamento.ABA_FOTO)
    return ler
