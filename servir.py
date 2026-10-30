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

# 32 threads (eram 16, e 8 antes de 13/10/2026): os pedidos esperam a rede (banco, Fracttal, as fotos do S3). Em 14/10 o
# OS Creator, que roda dentro do Nexus, prendia as 16 esperando o Fracttal e o /saude chegou a 60 s; agora o OS Creator usa
# no máximo 16 (casca/teto_os.py) e as outras ficam para o resto do Nexus. A mesma conta vai aos pedidos presos.
THREADS = 32

if __name__ == "__main__":
    try:
        app = create_app()
    except ConfigErro as erro:
        sys.exit(f"Nexus não subiu: {erro}")
    instalar_campo(app)
    instalar_dados(app)
    instalar_engenharia(app)
    # as normalizações da Ronda COS no banco, de hora em hora, para a disponibilidade da Thopen (29/10/2026; só grava
    # onde a chave do Andamento está, o servidor; NEXUS_NORMALIZACOES_PUBLICAR=0 desliga)
    from nexus.cos import normalizacoes_banco
    normalizacoes_banco.ligar(app)
    # os relatórios do PCM nos horários de lá: diário 06:00, tarde 13:00, fechamento sexta 17:00 e alerta ao publicar a
    # semana (14/10/2026; NEXUS_PCM_RELATORIOS_AUTO=0 desliga)
    from nexus.pcm.relatorios import agenda as relatorios_pcm
    relatorios_pcm.ligar(app)
    # o e-mail semanal das pendências da Segurança, que o App de Campo manda (24/10/2026; só com NEXUS_HSEQ_EMAIL_AUTO=1)
    from nexus.hseq import email_semanal
    email_semanal.ligar(app)
    # as telas quentes depois de cada deploy (13/10/2026: a 1ª abertura do servidor recém-subido levou 27 s; 5 min)
    from nexus.auth import pre_carga
    pre_carga.aquecer_ao_subir(app)
    # o que cada pedido esperava quando o Nexus parou de responder (13/10/2026: das 16:50 às 16:53 nem o /saude
    # respondia, e de fora não dava para ver esperando o quê); o administrador vê no cartão da versão do Início
    # o OS Creator com teto de threads (14/10/2026, Levi: "pq depende da TI se o OS Creator Web faz parte do Nexus???"):
    # antes do registro dos pedidos, que fica por fora e vê todos
    from nexus.casca import teto_os
    teto_os.ligar(app, teto=THREADS // 2)
    from nexus.casca import presos
    presos.ligar(app, THREADS)
    # o Nexus por dentro no Raio-X (24/10/2026: 2,6 GB, 1,9 no swap, e a página não dizia de quê), a cada 10 min
    from nexus.casca import memoria_nexus
    memoria_nexus.ligar(app)
    host = os.environ.get("NEXUS_HOST", "127.0.0.1")
    porta = int(os.environ.get("NEXUS_PORTA", "5070"))
    prefixo = app.config.get("NEXUS_PREFIXO") or "(raiz)"
    print(f"Nexus em produção: {host}:{porta}, servido em {prefixo} (cookie seguro, atrás do proxy HTTPS)", flush=True)
    # trusted_proxy: o IP do visitante vem do proxy; sem isso o teto por IP do Entrar e o contador da senha de
    # administrador (nexus/auth) contariam todo mundo como 127.0.0.1, e a empresa inteira dividiria um contador só.
    serve(app, host=host, port=porta, threads=THREADS, trusted_proxy="127.0.0.1",
          trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto"}, clear_untrusted_proxy_headers=True)
