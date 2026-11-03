"""App de Campo no Nexus: a visão do Nexus sobre o campo. Sem Azure: o dado são os livros que o App grava no banco
(livros_app.py). Atenção, PT, Rondas e Zeladoria são contas nossas (visao.py); Aprovação e Triagem usam
as regras do App copiadas (regras_app.py), que leem os livros pela fonte do banco (fonte_pg.py -> tabelas.py). O
coletor do Fracttal (coletor.py, banco_campo.py) está aposentado. As telas moram na torre Campo · App
(nexus/torres/campo/). Leia nexus/torres/campo/CLAUDE.md antes de mexer.
"""


def instalar(app):
    """Liga a fonte do banco nas telas e, só onde NEXUS_CAMPO_COLETOR=1, o coletor (uma máquina só: duas leriam a
    mesma fila e gastariam a cota do Fracttal em dobro). Quem chama é o app.py e o servir.py, nunca o create_app: os
    testes não podem ligar nada que fale com a rede."""
    import logging
    import threading
    from . import aprovacao, coletor, fonte_pg, tabelas
    tabelas.usar_fornecedor(fonte_pg.Fornecedor(app.config))
    from . import visao
    # as telas do Campo · App prontas na memória, e renovadas antes de vencer. SEMPRE ligado, em toda máquina: lê só o
    # banco do Nexus, nada de Fracttal. Até 09/10/2026 vinha junto com as leituras do Fracttal abaixo, e o PC (que sobe
    # com NEXUS_CAMPO_AQUECER=0 para não gastar a cota em dobro com o servidor) ficava sem: a 1ª visita à Central de
    # atenção depois de cada reinício levava 9,7 s e a hora da leitura era a do clique (Levi, 09/10: "quando clico em
    # Central de atenção ... a hora fica praticamente a hora que cliquei")
    threading.Timer(5, lambda: visao.manter_quente(app)).start()
    # a cópia em disco das fotos da ronda (13/10/2026): a dados/ do Nexus, que sobrevive ao reinício de cada deploy.
    # Nos testes, só a memória: a 1ª versão gravava as fotos falsas na dados/ de verdade do PC e um teste lia a do outro
    from pathlib import Path
    from ..cadastro.ligacoes import DADOS_PADRAO
    from . import ronda_fotos
    ronda_fotos.configurar(None if app.config.get("TESTING")
                           else Path(app.config.get("NEXUS_DADOS") or DADOS_PADRAO) / "cache_fotos_ronda")
    # os chamados de garantia no banco (12/10/2026): as OS de acompanhamento de chamado do Fracttal em
    # `nexus_chamados · fato_chamado`, de hora em hora, uma máquina por vez (NEXUS_CHAMADOS_PUBLICAR=0 desliga)
    from . import chamados_acompanhamento
    chamados_acompanhamento.ligar(app)
    # as tarefas das OS do Fracttal no banco (18/10/2026): `nexus_os · fato_tarefa_os`, de hora em hora (:10), uma
    # máquina por vez (NEXUS_OS_PUBLICAR=0 desliga). É a fonte do bloco Manutenção da Visão do responsável
    from . import tarefas_os
    tarefas_os.ligar(app)
    # o Responsável UFV de cada usina no livro de técnicos por usina (30/10/2026, a fase 3): de hora em hora, para o App
    # mandar e assinar a PT pelo responsável do Nexus (NEXUS_RESPONSAVEIS=0 desliga numa máquina)
    from ..pcm import responsaveis
    responsaveis.ligar(app)
    # a última fila boa da Aprovação, do disco, já no boot e em toda máquina: não vai ao Fracttal (13/10/2026)
    threading.Thread(target=lambda: aprovacao.carregar_do_disco(app), daemon=True, name="nexus-fila-disco").start()
    # NEXUS_CAMPO_AQUECER=0 desliga só o que vai ao Fracttal ao subir (a cota é de 200/min para a empresa inteira)
    if str(app.config.get("NEXUS_CAMPO_AQUECER", "1")) != "0":
        from . import ronda_checklist
        threading.Timer(20, lambda: aprovacao.aquecer(app)).start()
        # as OS de ronda aprovadas (sujidade e vegetação), depois da fila: as duas leituras não saem juntas
        threading.Timer(90, lambda: ronda_checklist.pedir_releitura(app)).start()
        # a Zeladoria no banco para o dashboard do cliente (26/10/2026): só aqui, onde o checklist das rondas é relido
        # (regra 12 do nexus/dados: o arquivo local das aprovadas mudaria o conteúdo conforme a máquina).
        # NEXUS_ZELADORIA_PUBLICAR=0 desliga
        from . import zeladoria_banco
        zeladoria_banco.ligar(app)
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
