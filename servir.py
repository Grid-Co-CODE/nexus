"""Sobe o Nexus em PRODUÇÃO (servidor), atrás de um proxy com HTTPS (Caddy, nginx).

Diferente do app.py, que é para desenvolvimento local:
- o cookie de sessão sai com Secure (o proxy fala HTTPS com o navegador);
- escuta só na própria máquina (127.0.0.1) por padrão: quem fala com a internet é o proxy;
- porta e endereço vêm do ambiente (NEXUS_PORTA, NEXUS_HOST).

Uso:  python servir.py        (o serviço do systemd chama assim; ver deploy/nexus.service e DEPLOY.md)
"""
import os
import sys

from waitress import serve

from nexus import create_app
from nexus.campo import instalar as instalar_campo
from nexus.config import ConfigErro

if __name__ == "__main__":
    try:
        app = create_app()
    except ConfigErro as erro:
        sys.exit(f"Nexus não subiu: {erro}")
    instalar_campo(app)
    host = os.environ.get("NEXUS_HOST", "127.0.0.1")
    porta = int(os.environ.get("NEXUS_PORTA", "5070"))
    print(f"Nexus em produção: {host}:{porta} (cookie seguro, atrás do proxy HTTPS)", flush=True)
    # trusted_proxy: o IP do visitante vem do proxy; sem isso o limite de tentativas de senha contaria todo mundo
    # como 127.0.0.1 e bloquearia a empresa inteira depois de 5 erros de uma pessoa.
    serve(app, host=host, port=porta, threads=8, trusted_proxy="127.0.0.1",
          trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto"}, clear_untrusted_proxy_headers=True)
