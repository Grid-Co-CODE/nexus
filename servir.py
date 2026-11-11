"""Sobe o Nexus em PRODUÇÃO (servidor), atrás de um proxy com HTTPS (Caddy, nginx).

Diferente do app.py, que é para desenvolvimento local:
- o cookie de sessão sai com Secure (o proxy fala HTTPS com o navegador);
- escuta só na própria máquina (127.0.0.1) por padrão: quem fala com a internet é o proxy;
- porta e endereço vêm do ambiente (NEXUS_PORTA, NEXUS_HOST);
- o caminho em que ele é servido vem de NEXUS_PREFIXO (/nexus em app.gridco.com.br/nexus; vazio = a raiz). Quem o aplica
  é o create_app (nexus/prefixo.py): o mesmo para o servir.py, o app.py e os testes.

Uso:  python servir.py        (o serviço do systemd chama assim; ver deploy/nexus.service e DEPLOY.md)
"""
import logging
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
    # o contador de pedidos ao Fracttal (31/10/2026, etapa 0 do canto central do OS Creator) e, no mesmo gancho do
    # Session.send, o porteiro (etapa 5: o Nexus até 150 pedidos por minuto, o fundo até 90, o clique nunca recusado),
    # ligados ANTES dos instalar_* abaixo, que já abrem laços que pedem ao Fracttal ao subir
    from nexus.casca import fracttal_conta
    fracttal_conta.ligar()
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
    # o e-mail semanal das pendências da Segurança, que o App de Campo manda (24/10/2026; ligado desde 30/10, NEXUS_HSEQ_EMAIL_AUTO=0 desliga)
    from nexus.hseq import email_semanal
    email_semanal.ligar(app)
    # as telas quentes depois de cada deploy (13/10/2026: a 1ª abertura do servidor recém-subido levou 27 s; 5 min)
    from nexus.auth import pre_carga
    pre_carga.aquecer_ao_subir(app)
    # as OS da FAMA do Quadro da semana, por trás e na hora (11/11/2026: só o banco, sem os 5 min da volta acima;
    # sem ela, quem abria o Quadro depois do deploy via "Lendo as OS da FAMA")
    from nexus.pcm import fama_quadro
    fama_quadro.aquecer_ao_subir(app)
    # o que cada pedido esperava quando o Nexus parou de responder (13/10/2026: das 16:50 às 16:53 nem o /saude
    # respondia, e de fora não dava para ver esperando o quê); o administrador vê no cartão da versão do Início
    # o OS Creator com teto de threads (14/10/2026, Levi: "pq depende da TI se o OS Creator Web faz parte do Nexus???"):
    # antes do registro dos pedidos, que fica por fora e vê todos
    from nexus.casca import teto_os
    teto_os.ligar(app, teto=THREADS // 2)
    # o uso das telas do OS Creator por hora, e a rota de cada pedido como origem do Fracttal (31/10/2026, etapa 0 do canto
    # central), e, com gravar=True, o laço que guarda as horas fechadas dos dois contadores no disco a cada hora (:05) e as
    # leva ao banco uma vez por dia, às 04:45 (só o servidor): DEPOIS do teto (é ele que avisa o 503 recusado) e antes do
    # registro dos pedidos presos
    from nexus.casca import uso_os
    uso_os.ligar(app, gravar=True)
    from nexus.casca import presos
    presos.ligar(app, THREADS)
    # o Nexus por dentro no Raio-X (24/10/2026: 2,6 GB, 1,9 no swap, e a página não dizia de quê), a cada 10 min
    from nexus.casca import memoria_nexus
    memoria_nexus.ligar(app)
    # os ativos do Fracttal lidos pelo próprio servidor (31/10/2026, etapa 2 do canto central do OS Creator): o Fracttal
    # inteiro às 02:15 e os novos de 30 em 30 min, pela credencial da empresa, e a foto dos ativos no banco renovada toda
    # noite. Só aqui (o app.py e os testes seguem pelo RPC); sem a credencial REST ele não liga, e o estado diz por quê
    # Cada leitor liga dentro de um try (`ligar_leitor_do_clone`): importar o leitor é importar o clone, e o clone quebrado não
    # derruba o Nexus (31/10/2026, revisão final: antes o clone só carregava no 1º pedido ao /os/, dentro de um try). O Nexus
    # sobe sem o leitor, o log tem a pilha e o Raio-X diz que ele não ligou; o portão do deploy pega o clone quebrado antes
    from nexus.torres.oscreator import ponte as ponte_os
    ponte_os.ligar_leitor_do_clone(app, "ativos_leitor")
    # o histórico de OS central lido pelo próprio servidor (31/10/2026, etapa 3 do canto central): as novas de 3 em 3 min, os 7
    # dias de 10 em 10, as finalizadas de hora em hora, a janela de madrugada (03:21), e as abertas que o laço do tarefas_os
    # (ligado acima, no instalar_campo) já lê, entregues sem pedido a mais. Só aqui; sem a credencial REST ele não liga
    ponte_os.ligar_leitor_do_clone(app, "os_leitor")
    # os catálogos pequenos do OS Creator (31/10/2026, etapa 4 do canto central): a cópia em disco de cada um (o reinício não
    # pede nada) e as pessoas pelo REST da empresa às 05h, 11h, 17h e 23h, no minuto que a lista de minutos ocupados lhes dá.
    # Só aqui; sem a credencial REST não liga, e as pessoas seguem pelo RPC, com a sessão de quem usa (como no app.py)
    ponte_os.ligar_leitor_do_clone(app, "catalogos_leitor")
    # os chamados de garantia em aberto para o App de Campo (08/11/2026): a foto de 10 em 10 min, da lista central de OS acima
    # (sem pedido ao Fracttal), no livro nexus_chamados_abertos. Ligado desde 08/11/2026 (`chamados_abertos.LIGADO_PADRAO`)
    try:
        from nexus.torres.oscreator import chamados_abertos
        chamados_abertos.ligar(app)
    except Exception:                       # noqa: BLE001 — o Nexus sobe sem ele; o log tem a pilha
        logging.exception("OS Creator: os chamados em aberto para o App não ligaram")
    host = os.environ.get("NEXUS_HOST", "127.0.0.1")
    porta = int(os.environ.get("NEXUS_PORTA", "5070"))
    prefixo = app.config.get("NEXUS_PREFIXO") or "(raiz)"
    print(f"Nexus em produção: {host}:{porta}, servido em {prefixo} (cookie seguro, atrás do proxy HTTPS)", flush=True)
    # trusted_proxy: o IP do visitante vem do proxy; sem isso o teto por IP do Entrar e o contador da senha de
    # administrador (nexus/auth) contariam todo mundo como 127.0.0.1, e a empresa inteira dividiria um contador só.
    serve(app, host=host, port=porta, threads=THREADS, trusted_proxy="127.0.0.1",
          trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto"}, clear_untrusted_proxy_headers=True)
