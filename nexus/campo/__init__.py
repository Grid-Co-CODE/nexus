"""App de Campo no Nexus: as contas do painel de gestão do App, refeitas com as regras dele (cópia fiel em
regras_app.py). Sem Azure: o dado vem do Fracttal (coletor.py calcula a nota de cada fechamento e grava na API do PG,
banco_campo.py) e chega às regras pela fonte do banco (fonte_pg.py -> tabelas.py). As telas moram na torre Campo · App
(nexus/torres/campo/). Leia nexus/torres/campo/CLAUDE.md antes de mexer.
"""


def instalar(app):
    """Liga a fonte do banco nas telas e, só onde NEXUS_CAMPO_COLETOR=1, o coletor (uma máquina só: duas leriam a
    mesma fila e gastariam a cota do Fracttal em dobro). Quem chama é o app.py e o servir.py, nunca o create_app: os
    testes não podem ligar nada que fale com a rede."""
    import logging
    from . import coletor, fonte_pg, tabelas
    tabelas.usar_fornecedor(fonte_pg.Fornecedor(app.config))
    # o relatório de cada rodada (só contagens) vai para o log do processo: sem isto, um 429 ou um erro de gravação
    # ficava só na memória (1ª carga, 04/10: a rodada parou e ninguém via por quê)
    log = logging.getLogger("nexus.campo")
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
    if str(app.config.get("NEXUS_CAMPO_COLETOR") or "").strip() == "1":
        coletor.ligar(app)
