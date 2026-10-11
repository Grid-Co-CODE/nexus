"""Sobe o Nexus local em http://localhost:5070.

No servidor o app é criado por create_app() atrás de um servidor WSGI e HTTPS; aqui é só para
desenvolvimento, por isso o cookie de sessão perde o Secure (em http o navegador o descartaria).

Escuta em IPv4 E IPv6: o Edge resolve "localhost" para ::1 primeiro, e com o servidor só em
127.0.0.1 a página dava "localhost se recusou a se conectar" (29/09/2026).

Com `NEXUS_PLATAFORMA_LOCAL` (ex.: http://127.0.0.1:5050, no .env do PC), a 5070 faz também o papel do Caddy do
servidor: os caminhos do Nexus ficam neste processo e o resto vai à plataforma local, como em app.gridco.com.br com o
Nexus na raiz. Por quê (Levi, 10/10/2026, com o print do Tempo real dizendo "configurada em outra origem"): a moldura
da Performance só abre na MESMA origem do Nexus (a plataforma manda `frame-ancestors 'self'`), e no PC cada porta é
outra origem; antes era preciso abrir outro endereço (ferramentas/porta_local.py). Assim o localhost:5070 de sempre
abre as 13 telas da Performance. Sem a variável, nada muda.
"""
import sys

from waitress import serve

from nexus import create_app
from nexus.campo import instalar as instalar_campo
from nexus.dados import instalar as instalar_dados
from nexus.engenharia import instalar as instalar_engenharia
from nexus.config import ConfigErro, ler_ambiente

PORTA = 5070


def juntar_com_a_plataforma(nexus_wsgi, plataforma: str):
    """Um WSGI só: caminho do Nexus (a mesma divisão do Caddy na raiz, `ferramentas/porta_local.destino`) vai ao
    Nexus deste processo, sem salto de rede; o resto vai à plataforma pelo repasse da porta local (cookies do navegador
    como vieram, nada guardado aqui)."""
    from ferramentas.porta_local import criar_app, destino

    repasse = criar_app("http://127.0.0.1:9", plataforma, "raiz", False)   # o lado Nexus do repasse nunca é usado

    def wsgi(environ, start_response):
        quem, _ = destino(environ.get("PATH_INFO") or "/", "raiz")
        return (nexus_wsgi if quem == "nexus" else repasse)(environ, start_response)

    return wsgi


if __name__ == "__main__":
    try:
        app = create_app()
    except ConfigErro as erro:
        sys.exit(f"Nexus não subiu: {erro}")
    app.config["SESSION_COOKIE_SECURE"] = False
    instalar_campo(app)
    instalar_dados(app)
    instalar_engenharia(app)
    plataforma = (ler_ambiente().get("NEXUS_PLATAFORMA_LOCAL") or "").strip()
    alvo, threads = app, 8
    if plataforma:
        # a plataforma tem pedidos longos (trackers de um dia passam de minutos): mais threads para eles não segurarem o Nexus
        alvo, threads = juntar_com_a_plataforma(app, plataforma), 32
        print(f"Nexus em http://localhost:{PORTA}, com a plataforma de {plataforma} no mesmo endereço", flush=True)
    else:
        print(f"Nexus em http://localhost:{PORTA}", flush=True)
    serve(alvo, listen=f"127.0.0.1:{PORTA} [::1]:{PORTA}", threads=threads)
