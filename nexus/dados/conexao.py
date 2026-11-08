"""A conexão com o banco do Nexus (a API `db_performace` da T.I.): o endereço e a sessão HTTP de cada pedido.

Morava em `nexus/campo/visao.py` (a conta das telas do Campo) até 08/11/2026. O mapa do desembaraço (skill
untangle-codebase) mediu que 13 áreas importavam a tela do Campo só para falar com o banco, e que essa ida ao Campo
fechava um ciclo de 92 módulos de 19 áreas: quem só quer o banco passa a vir aqui, na camada de dados. O `visao._base`, o
`visao._sessao` e o `visao.SemBanco` seguem valendo (chamam estes), para quem lê o Campo e para os testes.
"""
from flask import current_app


class SemBanco(RuntimeError):
    """Sem a sessão do banco: o teste (que nunca vai à rede) ou a leitura que não pôde ir."""


def sessao():
    """A sessão HTTP do banco que o app instalou (`app.extensions["nexus_dados_sessao"]`); no teste, sem ela, `SemBanco`."""
    s = current_app.extensions.get("nexus_dados_sessao")
    if s is None and current_app.config.get("TESTING"):
        raise SemBanco("teste sem banco")          # teste nunca vai à rede
    if s is None:
        import requests
        s = requests.Session()
    return s


def base_de(config) -> str:
    """O endereço da API do banco pela configuração dada (a carga e os laços de fundo, fora de um pedido):
    `GRIDCO_DB_API`, ou o padrão do cadastro. Eram cinco cópias de `_base(config)` até 08/11/2026."""
    from ..cadastro.ligacoes import BASE_API
    return (config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")


def base() -> str:
    """O endereço da API do banco, no pedido."""
    return base_de(current_app.config)


def banco() -> tuple:
    """(base, sessao), o par que `livros.ler` e as leituras de cada área pedem."""
    return base(), sessao()


def banco_de(cfg) -> tuple:
    """(base, sessao) pela configuração dada, dentro ou fora de um pedido: a sessão do app quando há um, senão uma
    própria (a ferramenta da foto, a carga). Eram duas cópias de `_banco(cfg)` (o inventário e os motivos do PCM)."""
    base = str(base_de(cfg))
    s = None
    try:
        s = current_app.extensions.get("nexus_dados_sessao")
    except RuntimeError:            # fora de um pedido: sessão própria
        pass
    if s is None:
        import requests
        s = requests.Session()
    return base, s
