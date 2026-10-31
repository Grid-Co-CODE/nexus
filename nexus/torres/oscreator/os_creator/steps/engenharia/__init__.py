"""Descritor da área de Engenharia: o título, a descrição e o ícone que a tela dela no OS Creator Web lê.

A rota `/os/engenharia` (`os_web/rotas_engenharia.py`) importa este módulo, e é a única coisa de `steps/` que a web usa.
O descritor nasceu no app de mesa (o oem), onde o launcher do `app.py` o lia para montar o card da área e o `abrir()`
montava a tela em PyQt6. Essa tela (`tela.py`), o `steps/ui.py` e o `abrir()` (o único elo deste módulo com o PyQt6, que
a web nunca chamava) saíram da cópia do Nexus em 31/10/2026: o caminho web não importa PyQt6
(`tests/test_oscreator_sem_pyqt.py`).
"""

TITULO = "Engenharia"
DESCRICAO = "OS de ETM e as análises da Engenharia"

ICONE = "etm"
ICONES = {
    # estação meteorológica: mastro, sensor no topo e as duas hastes da medição
    "etm": '<path d="M12 21V10"/><path d="M8 21h8"/><circle cx="12" cy="7" r="3"/>'
           '<path d="M5 7a7 7 0 0 1 2-4.9"/><path d="M19 7a7 7 0 0 0-2-4.9"/>',
}
