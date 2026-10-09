"""Engenharia de manutenção no Nexus: a confiabilidade dos ativos pelas OS de falha do Fracttal (06/10/2026).

- `os_falhas.py` lê do Fracttal as OS de falha (corretiva, corretiva emergencial, religamento e religamento remoto),
  guarda em arquivo e relê só o que mudou;
- `confiabilidade.py` faz as contas: os sinais por ativo dos últimos 30 dias, o nível, e o MTBF, o MTTR e a
  disponibilidade pelo método do Power BI da Grid Co.

As telas moram na torre Engenharia (`nexus/torres/engenharia/`). Leia o CLAUDE.md de lá antes de mexer.
"""


def instalar(app):
    """Na subida (app.py e servir.py, nunca o create_app: teste não fala com a rede), a leitura das OS de falha e, depois
    dela, a do Quadro da equipe, depois da fila da Aprovação (20 s) e das rondas aprovadas (90 s): as leituras não saem
    juntas. A mesma chave das leituras do Fracttal do Campo ao subir desliga as duas numa máquina
    (NEXUS_CAMPO_AQUECER=0). O Quadro da equipe pronto enquanto alguém o usa (`os_equipe.manter_quente`) liga sempre:
    só lê quando alguém abriu a tela nas últimas 2 h (Levi, 09/10/2026)."""
    import threading
    from . import os_equipe
    os_equipe.manter_quente(app)
    if str(app.config.get("NEXUS_CAMPO_AQUECER", "1")) != "0":
        from . import os_falhas
        threading.Timer(150, lambda: os_falhas.pedir_releitura(app)).start()
        # o quadro já lido quando a 1ª pessoa abrir depois de um reinício (no servidor, o deploy)
        threading.Timer(210, lambda: os_equipe.pedir_releitura(app)).start()
