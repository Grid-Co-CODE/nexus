"""Sobe o Nexus local em http://localhost:5070.

No servidor o app é criado por create_app() atrás de um servidor WSGI e HTTPS; aqui é só para
desenvolvimento, por isso o cookie de sessão perde o Secure (em http o navegador o descartaria).

Escuta em IPv4 E IPv6: o Edge resolve "localhost" para ::1 primeiro, e com o servidor só em
127.0.0.1 a página dava "localhost se recusou a se conectar" (29/09/2026).
"""
import sys

from waitress import serve

from nexus import create_app
from nexus.campo import instalar as instalar_campo
from nexus.dados import instalar as instalar_dados
from nexus.engenharia import instalar as instalar_engenharia
from nexus.config import ConfigErro

PORTA = 5070

if __name__ == "__main__":
    try:
        app = create_app()
    except ConfigErro as erro:
        sys.exit(f"Nexus não subiu: {erro}")
    app.config["SESSION_COOKIE_SECURE"] = False
    instalar_campo(app)
    instalar_dados(app)
    instalar_engenharia(app)
    print(f"Nexus em http://localhost:{PORTA}", flush=True)
    serve(app, listen=f"127.0.0.1:{PORTA} [::1]:{PORTA}", threads=8)
