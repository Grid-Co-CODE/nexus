"""Sobe o Nexus em PRODUÇÃO (servidor), atrás de um proxy com HTTPS (Caddy, nginx).

Diferente do app.py, que é para desenvolvimento local:
- o cookie de sessão sai com Secure (o proxy fala HTTPS com o navegador);
- escuta só na própria máquina (127.0.0.1) por padrão: quem fala com a internet é o proxy;
- porta e endereço vêm do ambiente (NEXUS_PORTA, NEXUS_HOST);
- o caminho em que ele é servido vem de NEXUS_PREFIXO (/nexus em app.gridco.com.br/nexus; vazio = a raiz). Quem o aplica
  é o create_app (nexus/prefixo.py): o mesmo para o servir.py, o app.py e os testes.

Uso:  python servir.py        (o serviço do systemd chama assim; ver deploy/nexus.service e DEPLOY.md)
"""
import os
import sys

from waitress import serve

from nexus import create_app
from nexus.campo import instalar as instalar_campo
from nexus.dados import instalar as instalar_dados
from nexus.engenharia import instalar as instalar_engenharia
from nexus.config import ConfigErro

if __name__ == "__main__":
    try:
        app = create_app()
    except ConfigErro as erro:
        sys.exit(f"Nexus não subiu: {erro}")
    instalar_campo(app)
    instalar_dados(app)
    instalar_engenharia(app)
    host = os.environ.get("NEXUS_HOST", "127.0.0.1")
    porta = int(os.environ.get("NEXUS_PORTA", "5070"))
    prefixo = app.config.get("NEXUS_PREFIXO") or "(raiz)"
    print(f"Nexus em produção: {host}:{porta}, servido em {prefixo} (cookie seguro, atrás do proxy HTTPS)", flush=True)
    # trusted_proxy: o IP do visitante vem do proxy; sem isso o limite de tentativas de senha contaria todo mundo
    # como 127.0.0.1 e bloquearia a empresa inteira depois de 5 erros de uma pessoa.
    serve(app, host=host, port=porta, threads=8, trusted_proxy="127.0.0.1",
          trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto"}, clear_untrusted_proxy_headers=True)
