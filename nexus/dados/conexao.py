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


def base() -> str:
    """O endereço da API do banco: `GRIDCO_DB_API` da configuração, ou o padrão do cadastro."""
    from ..cadastro.ligacoes import BASE_API
    return (current_app.config.get("GRIDCO_DB_API") or BASE_API).rstrip("/")


def banco() -> tuple:
    """(base, sessao), o par que `livros.ler` e as leituras de cada área pedem."""
    return base(), sessao()
