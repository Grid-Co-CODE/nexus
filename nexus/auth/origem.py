"""O pedido veio de outra página? A regra que toda gravação do Nexus confere antes de mexer em dado.

Morava em `nexus/torres/moldura.py` (a moldura das telas da Performance) até 08/11/2026: o mapa do desembaraço (skill
untangle-codebase) achou 37 lugares de 16 arquivos, do cadastro ao PCM, importando a regra de segurança de dentro de uma
torre. Ela é do portão, e mora aqui. O `moldura._de_outro_site` segue valendo (chama esta).
"""
from urllib.parse import urlsplit

from flask import request


def de_outro_site() -> bool:
    """O pedido NÃO veio de uma página deste mesmo endereço. A mesma regra do `_de_outra_origem` da plataforma: pelo
    Sec-Fetch-Site, só 'same-origin' (o fetch do porta.js; 'same-site' não, porque todo subdomínio de gridco.com.br é
    'same-site'); sem ele, o Origin tem de ser deste host ('null' não); sem os dois não é navegador, e não há cookie de
    vítima para usar. A resposta é JSON que outro site não lê (sem CORS); isto fecha também o pedido às cegas."""
    sfs = (request.headers.get("Sec-Fetch-Site") or "").strip().lower()
    if sfs:
        return sfs != "same-origin"
    origem = request.headers.get("Origin")
    if origem is None:
        return False
    try:
        de = urlsplit(origem.strip()).netloc.lower()
    except ValueError:
        return True
    return not de or de != (request.host or "").lower()
